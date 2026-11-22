# Bundled JRE and Custom Runtime with jlink

When migrating a Java application from an older JDK to a modern JDK, **packaging the runtime environment** can be just as important as fixing source code or upgrading frameworks. An application distributed as a JAR may run on a developer's machine yet fail on a client machine because Java is not installed, the wrong version is installed, JDK modules are missing, native libraries are missing, or an outdated JRE without security updates is being used.

One solution is to **distribute the application bundled with a Java runtime** that has already been selected and tested, instead of requiring users to install a JDK themselves. From Java 9 onward, the `jlink` tool also makes it possible to create a **custom runtime image** containing only the required Java modules, helping control the size and composition of the runtime environment. However, the more minimal an image is, the easier it is to omit a module invoked via reflection, a service provider, or infrequently tested code paths.

This lesson explains the differences among a prebuilt JRE, a full JDK, a runtime created by `jlink`, and an installer created by `jpackage`; guides how to identify modules, build an image, run modular and classpath applications, handle Java agents, TLS, locales, native libraries, cross-platform packaging, patching updates, and design a safe migration pipeline.

> **Scope:** Examples in this lesson illustrate deployment models for modern Java and assume you have the rights to use and distribute the corresponding JDK/runtime. Commands, plugins, and components may differ across JDK versions or vendors. For production releases, you must check the documentation of the JDK distribution, license, operating system, and toolchain chosen by your organization.

## 1. Problems solved by a bundled runtime

### 1.1. The model that depends on Java installed on the machine

A traditional application can be distributed as follows:

```text
Developer side
  source -> javac -> application.jar
                         |
                         v
                   Distribute JAR
                         |
                         v
Client machine: java -jar application.jar
                  ^
                  |
         Pre-installed Java on machine
```

This is a simple model, suitable when runtime management is centralized. However, it makes many assumptions:

- Does the `java` command exist in `PATH`?
- Is the actual JVM Java 8, 11, 17, 21, or another version?
- Which vendor was Java installed from, and does it still receive security updates?
- Does the user have permissions to install or upgrade Java?
- Is the machine running Windows, macOS, or Linux; x86_64 or ARM64?
- Does the runtime contain the modules and security providers the application requires?
- Has the environment been configured with the appropriate truststore, locale, timezone, and encoding?

If these assumptions are not managed, a Java upgrade can turn into a deployment issue across thousands of machines.

### 1.2. The bundled-runtime distribution model

An alternative approach:

```text
CI / Release pipeline
  |
  +--> Build application.jar
  |
  +--> Select runtime version/vendor
  |
  +--> Package application + runtime
  |
  v
Release bundle
  app/
    application.jar
    lib/
    runtime/
      bin/java
      lib/...
    bin/start
```

At startup, the script uses the release's `runtime/bin/java` instead of the `java` version found on the system.

Benefits:

- Proactively choose the Java runtime supported by the application.
- Reduce errors caused by users installing the wrong Java.
- Enable testing on a runtime equivalent to the distributed bundle.
- Allow deployment to environments without a system-wide JDK.
- Manage updates and rollbacks together with the application.
- Gain the opportunity to reduce size using a custom runtime.

In return, the development team **must take responsibility for updating the runtime** in every release. Even if the JAR is unchanged, a runtime containing a vulnerability still needs to be rebuilt and redistributed.

## 2. JDK, JRE, runtime image, and packaged applications

### 2.1. Full JDK

A **Java Development Kit (JDK)** typically includes the runtime and development tools such as the compiler, debugger, archiver, and analysis tools:

```text
jdk/
  bin/
    java
    javac
    jar
    jlink
    jdeps
    ...
  conf/
  legal/
  lib/
  jmods/ ... (depending on distribution and release)
```

The exact structure varies by vendor, operating system, and version. A JDK is suitable for build and development machines. Not every production application needs to carry the entire compiler and development tools.

### 2.2. JRE in older Java

In Java generations prior to the module system, many environments used a **separately distributed JRE** to run applications:

```text
Application -> Installed or bundled JRE -> JVM
```

This was a separate product/runtime distribution from the full JDK in versions and vendors that supported that model.

When upgrading from Java 8 to a modern JDK, you should not assume the `$JAVA_HOME/jre` path or a `jre` directory inside the JDK still exists as before. Starting from JDK 9, the JDK is organized into modules and runtime images; following changes in newer JDK generations, not every vendor publishes a standalone downloadable JRE under the old convention.

**Important:** "A JRE is no longer the default distribution of some JDKs" does not mean Java can only run with a full JDK. Vendors may distribute dedicated runtimes, and `jlink` allows creating a custom runtime image from supported modules.

### 2.3. Custom runtime image with jlink

`jlink` is a tool in the Java module ecosystem, introduced in Java 9. It links a set of modules into a structured **runtime image** used to launch Java code, for example:

```text
custom-runtime/
  bin/
    java
    keytool
    ...
  conf/
  legal/
  lib/
  release
```

The file list depends on modules, plugins, and JDK version. This runtime does not necessarily contain a compiler or `jlink` inside.

### 2.4. jpackage

`jpackage` handles the step of packaging an **application** into an application image or native installer for the target platform. It can use a generated runtime image or one supplied via the appropriate option.

Distinction:

| Component | Primary role | Example usage |
|---|---|---|
| Full JDK | Compile, package, debug, and run Java | CI build machine |
| JRE/runtime distribution | Run the application using a vendor-packaged runtime | Production machine using a pre-supplied runtime |
| `jlink` | Create a runtime image from Java modules | Minimize the runtime environment per application |
| `jpackage` | Create an application image or installer | Desktop app for Windows/macOS/Linux |
| JAR/WAR | Package application classes, resources, and metadata | Java service, CLI, library |
| OCI container image | Distribute filesystem, runtime, and application | Server/container deployments |

`jlink` is not a complete installer-building tool, and `jpackage` does not replace the Java compiler. Usually these tools are combined in a release pipeline.

## 3. Why can jlink reduce size?

### 3.1. The JDK consists of multiple modules

With JPMS, the Java runtime is divided into modules with explicit dependency descriptions. A program that only needs core APIs, logging, and an HTTP client may not need most Java Desktop, XML, SQL, or development tool modules.

Example graph:

```text
com.example.cli
   |
   +--> java.base
   +--> java.logging
   +--> java.net.http
             |
             +--> required platform modules
```

`jlink` uses module graph information to include only the required modules, rather than copying the entire JDK.

### 3.2. jlink is not just ZIP compression

There are three distinct operations:

1. **Module selection:** removing modules that are not needed in the runtime image.
2. **Image optimization:** optionally stripping debug symbols, man pages, header files, or applying compression mechanisms supported by the runtime.
3. **Distribution compression:** compressing the entire image directory into a ZIP, TAR, installer, or container layer for transfer.

These operations are not synonymous. A runtime image with a small size on disk does not necessarily produce the smallest compressed download, and vice versa.

### 3.3. Do not minimize at all costs

If modules are trimmed too aggressively, the application may:

- Fail to find logging, JNDI, or XML APIs.
- Lack charsets for data outside UTF-8.
- Lack full locale data.
- Fail to load required TLS/security providers.
- Fail to instantiate service providers.
- Lack JFR, management, or the Attach API when SREs need them.
- Fail to open a desktop UI.
- Only fail when an infrequently used feature is triggered.

A reasonable goal is **a runtime that is sufficiently small yet functionally complete and easy to maintain**, not just minimizing the byte count.

## 4. Prerequisites before using jlink

### 4.1. Use a JDK that includes the jlink tool

Check:

```shell
java -version
jlink --version
jlink --help
```

The JDK must include `jlink` and the required module resources. If you are using an already stripped-down runtime image, it may not contain `jlink`; you need to use an appropriate JDK build toolchain.

### 4.2. Understand module path and classpath

- **Classpath:** the traditional class loading mechanism, which can contain many JARs without a module descriptor.
- **Module path:** used to resolve named modules according to JPMS.
- **Module descriptor:** `module-info.class` declaring module name, dependencies, exports, and service usage.
- **Automatic module:** a JAR without an explicit module descriptor may be treated as an automatic module when placed on the module path in certain runtime situations.

`jlink` links **named modules that have an appropriate module descriptor**, and does not support linking automatic modules in the same way as explicit modules. Therefore, you cannot simply put arbitrary classpath libraries onto `--module-path`, run `jlink`, and expect every Java artifact to be embedded into the runtime.

If an application is not yet modularized, you can still create a **runtime containing the required JDK modules**, and distribute the application JAR/classpath libraries separately. This is often a more practical and less disruptive migration path.

### 4.3. Inventory the application and dependencies

Before selecting modules, you need to know:

- Is the application modular or classpath-based?
- Is the entry point a `main class`, main module, framework launcher, or native launcher?
- Which Java SE modules are used directly?
- Is JDBC, HTTP client, XML, GUI, JNDI, or scripting used?
- Is there runtime reflection, `ServiceLoader`, dynamic proxies, custom classloaders, or plugins?
- Are there Java agents, JVMTI, JNI, or JFR?
- Do dependencies include OS/arch-specific native assets?
- Which locales, timezones, charsets, or crypto providers does the application need?
- What is the minimum supported runtime version of the application and third-party libraries?

A module graph determined solely from source code is usually insufficient; you must exercise the application's actual execution paths.

## 5. jlink and basic options

### 5.1. Command pattern

A simple example creating a runtime containing a few Java modules:

```shell
jlink \
  --add-modules java.base,java.logging,java.net.http \
  --output build/runtime
```

Line continuation with `\` is Unix-like shell syntax. In PowerShell, you can write it on a single line:

```powershell
jlink --add-modules java.base,java.logging,java.net.http --output build/runtime
```

`jlink` obtains Java module definitions from the corresponding JDK/toolchain according to how it is configured. For a custom modular application, you must supply a module path containing both application modules and the appropriate Java platform modules.

### 5.2. Running the generated runtime

Unix-like:

```shell
./build/runtime/bin/java --list-modules
./build/runtime/bin/java -version
```

Windows:

```powershell
.\build\runtime\bin\java.exe --list-modules
.\build\runtime\bin\java.exe -version
```

The module list helps verify which Java modules are present in the image, while `java -version` shows the runtime corresponds to the JDK used to build the image.

### 5.3. Common options

| Option | Purpose |
|---|---|
| `--module-path` | Specifies paths containing modules participating in linking |
| `--add-modules` | Specifies root modules to include in the image |
| `--output` | Specifies the output image directory |
| `--launcher` | Creates a launcher for the specified main module |
| `--bind-services` | Includes service provider modules matching the module graph |
| `--strip-debug` | Strips debug information according to plugin capability |
| `--no-header-files` | Excludes header files from the image |
| `--no-man-pages` | Excludes man pages from the image |
| `--compress` | Compresses image contents using a JDK-supported plugin/mode |
| `--list-plugins` | Lists available plugins |

The exact syntax of some plugins, especially `--compress` and newer options, may vary across JDK releases. You should run `jlink --help` and `jlink --list-plugins` from the exact toolchain instead of copying a configuration from a different JDK.

### 5.4. Creating a minimal image without specialized compression options

A commonly used example:

```shell
jlink \
  --add-modules java.base,java.logging,java.net.http \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
```

Then measure size, run smoke tests, and compare against the unoptimized version. These resource-removal options are packaging decisions; if a tool is found to require debug symbols or a removed component, adjustments must be made.

### 5.5. Do not overwrite an old image without clear output handling

`--output` points to a destination directory. The build process should create the new image in a managed directory or remove the previous output in a controlled manner before regenerating.

You should not directly overwrite a runtime directory while an application is actively running from it. A runtime image used by another process should be treated as an immutable artifact; update by deploying a new version, then switch the launcher/installation to that new version.

## 6. Modular project: jlink including application modules

### 6.1. Declaring module-info.java

Example of a minimal modular Java application:

```text
src/
  com.example.hello/
    module-info.java
    com/example/hello/Main.java
```

`module-info.java`:

```java
module com.example.hello {
    requires java.logging;
}
```

`Main.java`:

```java
package com.example.hello;

import java.util.logging.Logger;

public final class Main {
    private static final Logger LOG =
        Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Hello from custom runtime");
    }
}
```

### 6.2. Compiling the module

Illustrative example from the root directory on Unix-like systems:

```shell
mkdir -p mods/com.example.hello

javac \
  -d mods/com.example.hello \
  src/com.example.hello/module-info.java \
  src/com.example.hello/com/example/hello/Main.java
```

Paths and `javac` must match the actual source directory. With Maven/Gradle, the compiler task typically handles this step; there is no need to abandon your build tool for manual commands.

### 6.3. Linking a runtime with the application

Example with a JDK distribution containing `jmods`:

```shell
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.hello \
  --launcher hello=com.example.hello/com.example.hello.Main \
  --output build/hello-runtime
```

In the Unix-like example, `:` is the module-path separator. On Windows, the separator is `;`; the `jmods` path and environment variable syntax also differ.

`--launcher hello=module/mainClass` creates an application launcher inside the image if supported by the JDK/linker and the module declares an appropriate main class. It can be run with:

```shell
./build/hello-runtime/bin/hello
```

Or using the Java launcher:

```shell
./build/hello-runtime/bin/java \
  --module com.example.hello/com.example.hello.Main
```

This CLI form is suitable for a **modular application** that already has a module descriptor. It does not apply directly as-is to a classpath JAR without an explicit module.

### 6.4. JPMS descriptors must be accurate

If the application module `requires com.example.database`, but this module is not on the module path or lacks an appropriate explicit module descriptor, `jlink` may report module not found or fail to process an automatic module.

Distinguish among:

- Application module not yet compiled.
- Wrong module path.
- Module name mismatch with actual artifact.
- Third-party library is an automatic module.
- A module dependency is declared but not provided.
- Invalid module descriptor.

Do not simply add every JAR in `lib` to the module path and expect `jlink` to automatically convert them into native image modules.

## 7. Non-modular applications: jlink is still useful

### 7.1. No need to convert the entire project to JPMS immediately

A Spring/Java CLI/service running on the classpath can use a custom runtime containing the required JDK modules while keeping the application JAR and dependencies outside the runtime.

Example:

```text
dist/
  runtime/
    bin/java
    lib/...
  app/
    application.jar
  lib/
    dependency-a.jar
    dependency-b.jar
  bin/
    start.sh
    start.ps1
```

`jlink` generates the `runtime/` portion. The `app/` and `lib/` portions continue to be packaged by Maven or Gradle.

### 7.2. Example of launching a classpath application

Unix-like:

```shell
./dist/runtime/bin/java \
  -cp "dist/app/application.jar:dist/lib/*" \
  com.example.Main
```

Windows:

```powershell
.\dist\runtime\bin\java.exe -cp "dist\app\application.jar;dist\lib\*" com.example.Main
```

This example is for a JAR with a main class and dependencies on the classpath. If the artifact is an executable fat JAR packaged by a framework with its own launcher, `-jar application.jar` and a layout matching that framework's launcher may be needed.

The classpath separator differs between Windows and Unix-like systems. To reduce errors, provide an OS-specific launcher script or use a packager that generates the appropriate launcher.

### 7.3. Why not link all dependencies directly?

`jlink` requires a clear module graph. Many third-party JARs are published for the traditional classpath without an explicit module descriptor. Automatic modules can be useful on the runtime module path, but are not handled by `jlink` like standard explicit modules.

For large applications, a maintainable strategy is:

```text
jlink(JDK modules)
       +
application JAR
       +
third-party JARs
       =
self-contained application distribution
```

This approach removes the dependency on a system-installed Java without forcing the entire framework to be modularized in a single migration step.

## 8. Finding required modules with jdeps

### 8.1. What does jdeps do?

`jdeps` analyzes static class/JAR dependencies, helping identify which Java modules are referenced by code. It is a useful starting point for building the `--add-modules` list.

Example for an application JAR:

```shell
jdeps \
  --print-module-deps \
  --ignore-missing-deps \
  application.jar
```

The output might be a comma-separated list:

```text
java.base,java.logging,java.net.http
```

This is an example output, not a fixed result for every application.

### 8.2. Including third-party libraries in analysis

If the application JAR references classes from dependencies:

```shell
jdeps \
  --multi-release 21 \
  --ignore-missing-deps \
  --print-module-deps \
  --class-path "lib/*" \
  application.jar
```

`--multi-release 21` is relevant when analyzing multi-release JARs for target runtime 21. For a different runtime, select the corresponding release within what the tool supports.

`--ignore-missing-deps` allows printing information even when some dependencies cannot be resolved, but **it is not proof that all dependencies are complete**. You should not rely on this option to overlook a missing library in production packaging.

### 8.3. Analyzing all relevant artifacts

If you only run `jdeps` on the main JAR, the result may miss JDK modules used by third-party JARs. You need to account for dependency JARs and dynamically loaded artifacts as far as tooling allows.

Some frameworks package dependency JARs nested inside an executable archive; `jdeps` cannot always process nested JARs directly in that layout. You may need to extract runtime dependencies as separate JARs for analysis or use specialized tooling.

### 8.4. Limitations of static analysis

`jdeps` cannot completely prove module requirements when the program uses:

- Reflection with class names as strings.
- `Class.forName`.
- `ServiceLoader` and provider modules only selected at runtime.
- JDBC drivers self-registered via the service mechanism.
- Plugin JARs loaded by a custom classloader.
- JNI/native integration.
- Script engines.
- Framework code generation.
- JNDI or modules used on rarely executed code paths.
- Multi-release class selection and framework-specific launchers.

Therefore, `jdeps` output is an **initial suggestion**, not a guaranteed complete list.

## 9. Adding modules for reflection and ServiceLoader

### 9.1. Dynamic features may require additional modules

An application that appears to only use `java.base` may actually need:

| Module | Situations to consider |
|---|---|
| `java.logging` | Java Util Logging or framework bridges |
| `java.net.http` | JDK HTTP Client API |
| `java.sql` | JDBC APIs |
| `java.naming` | JNDI, directory services |
| `java.xml` | XML processing |
| `java.desktop` | AWT, image processing, or UI APIs |
| `java.management` | MXBeans/management APIs |
| `jdk.management` | Certain JDK management extensions |
| `jdk.jfr` | Java Flight Recorder |
| `java.instrument` | Java instrumentation agents |
| `jdk.attach` | Attach API tooling |
| `jdk.unsupported` | Certain legacy APIs such as `sun.misc.Unsafe`, requires review |
| `jdk.charsets` | Charset providers beyond core charsets |
| `jdk.localedata` | Extended locale data |
| `jdk.crypto.ec` | Security provider supporting corresponding algorithms |

The table lists **candidates to evaluate**, not advice to always add every module. Some modules are pulled in transitively, some providers must be properly selected/bound, and the module set can change across JDK versions.

### 9.2. Example of expanding the module list

```shell
jlink \
  --add-modules java.base,java.logging,java.sql,java.naming,jdk.crypto.ec \
  --output build/runtime
```

Do not infer that this list is sufficient for a specific framework. Use `jdeps`, framework/vendor documentation, and integration tests running on the actual image.

### 9.3. Using --bind-services

`jlink --bind-services` can include modules that provide service implementations matching the module graph according to JDK behavior.

Example:

```shell
jlink \
  --add-modules java.base,java.net.http \
  --bind-services \
  --output build/runtime-with-providers
```

The advantage is reducing the risk of missing a service provider, while the downside can be a **much larger image** because many provider modules are pulled in. Do not treat this as always optimal.

After generating the image, inspect `--list-modules` and test actual behaviors. If the application uses third-party providers in JARs outside the image, `--bind-services` does not automatically turn all classpath libraries into linked modules.

### 9.4. Dynamically configured services

Some features only activate under specific configuration:

```text
App start -> does not use XML -> startup succeeds
User export report -> requires XML -> error due to missing module
```

Hence, a minimal runtime image must test all critical business flows, not just the healthcheck.

## 10. Security providers, TLS, and truststore

### 10.1. A small runtime still needs secure communication

A service might just send an HTTPS request, yet actually require these components:

- TLS implementation and cryptography providers.
- Root certificates to verify server certificates.
- Security policies.
- Supported algorithms/cipher suites.
- Truststore or custom CA configuration.
- HTTP client and hostname verification.

If a custom runtime lacks the required provider or has an incompatible truststore, errors may appear such as:

```text
javax.net.ssl.SSLHandshakeException
java.security.NoSuchAlgorithmException
java.security.KeyStoreException
```

Do not rush to add every `--add-modules`. You must check the root cause: untrusted certificate chain, missing provider, disabled protocol, hostname mismatch, or network error.

### 10.2. jdk.crypto.ec and other providers

Some minimal runtime images may omit provider modules such as `jdk.crypto.ec` if not selected via the module graph or proper service binding.

In applications using TLS, verify that the required algorithms/security providers work on the final runtime. Specific configuration depends on the JDK distribution, provider, and version.

### 10.3. Truststore is security data with its own lifecycle

A bundled runtime may carry a default certificate store, typically managed inside the Java runtime or system configuration depending on the distribution.

When updating the runtime, the truststore can change due to root CA and security policy updates. If the application uses a custom truststore, you must have a process to:

1. Securely manage CA/keystore files.
2. Never commit private keys or passwords directly into the repository.
3. Check process read permissions.
4. Define how `javax.net.ssl.trustStore` is configured if applicable.
5. Test actual HTTPS/JDBC/TLS connections.
6. Have a plan for certificate rotation.

Do not freeze an unpatched runtime version merely because "the current certificates still work".

## 11. Locale, timezone, charset, and Unicode

### 11.1. Locale data is not only for UI

Applications may format dates, numbers, and currencies according to locale:

```java
import java.text.NumberFormat;
import java.util.Locale;

var fmt = NumberFormat.getCurrencyInstance(
    Locale.forLanguageTag("vi-VN")
);

System.out.println(fmt.format(123456.78));
```

If a custom runtime lacks the appropriate locale data or exhibits different behavior due to JDK version/tzdb/locale providers, the output may change.

### 11.2. jdk.localedata

The `jdk.localedata` module provides extended locale data in JDKs that include this module. When an application requires multiple locales, verify whether it is present in the image and whether `jlink`'s locale-filtering option should be used on the target JDK.

Illustrative example:

```shell
jlink \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,vi \
  --output build/runtime-localized
```

The `--include-locales` option is provided by a plugin in supporting JDKs; exact syntax and locale coverage should be verified using `jlink --list-plugins` of the target toolchain.

### 11.3. Timezone database

The Java runtime provides timezone rules. Applications scheduling by local timezone may be affected by tzdb data updates.

Required tests:

- `ZoneId.of("Asia/Ho_Chi_Minh")` is supported.
- Date-time parsing/formatting matches expected locale behavior.
- Scheduled jobs run in the actual production timezone.
- Timezones with DST are handled properly if the application serves international users.
- The new runtime contains up-to-date timezone data.

### 11.4. Charset and default encoding

Modern JDKs have changes related to the default charset, notably JEP 400 making UTF-8 the default in Java 18 in most cases. However, applications should still specify the charset explicitly when reading/writing contracted data:

```java
String text = java.nio.file.Files.readString(
    path,
    java.nio.charset.StandardCharsets.UTF_8
);
```

A custom runtime missing a charset provider may fail on legacy-encoding paths even while regular UTF-8 tests pass.

## 12. Java agents, JFR, and diagnostic tooling

### 12.1. Instrumentation in a custom runtime

If the application uses an agent at startup:

```shell
./runtime/bin/java \
  -javaagent:agents/apm.jar \
  -jar application.jar
```

The runtime image must support instrumentation and the modules/capabilities required by the agent. For example, the `java.instrument` module may need to be included in the image.

Do not assume every agent works just because the `java` launcher is present. An agent may rely on additional classloading, JDK internals, JVMTI, native libraries, or module access controls.

### 12.2. jdk.jfr and management

For production observability, the SRE team may need:

- Java Flight Recorder.
- Thread dumps.
- Heap dumps.
- GC logging.
- MXBeans/JMX.
- Attach API and `jcmd` in certain environments.
- Native profilers or APM agents.

A minimal runtime image might not carry every JDK tool. If these tools are part of incident response workflows, determine how to provide them — inside the image, in a companion diagnostic environment, or via another vendor-supported approach.

### 12.3. Dynamic attach differs from startup agent

Since newer JDKs introduce warnings or restrictions on dynamic agent loading, this issue must be evaluated separately from whether the `java.instrument` module is present.

A runtime containing `java.instrument` does not automatically guarantee:

- The Attach Mechanism is enabled.
- `jdk.attach` is present in the required image.
- OS/process namespaces permit attaching.
- Dynamic agent loading is permitted by the target JVM.
- The agent is compatible with the application's class-file versions.

For runtimes using JDK 21 or later, review the target JDK version's dynamic agent loading policy and choose startup agent vs. dynamic agent based on operational needs.

### 12.4. Do not strip diagnostic capabilities just to save a few MB

A production service that is hard to diagnose can incur higher operational costs than a small disk space saving. Before removing JFR, management, or observability components, walk through an incident scenario:

```text
Service experiences increased latency
    |
    v
Can thread/GC/JFR data be collected?
    |
    +-- Yes --> investigable
    |
    +-- No --> must rebuild/redeploy runtime?
```

This is a product/SRE decision that should be documented, not purely a technical `jlink` choice.

## 13. Cross-platform packaging: do not copy one image everywhere

### 13.1. A runtime image is an OS/architecture-specific artifact

A typical Java JAR can be relatively portable, whereas a `jlink` image contains the platform-specific JVM launcher and native runtime components.

Therefore:

```text
runtime-windows-x64  != runtime-linux-x64
runtime-linux-x64    != runtime-linux-aarch64
runtime-macos-arm64  != runtime-windows-arm64
```

Do not build an image on Linux and assume it runs directly on Windows. Normally you need to build the image using the appropriate toolchain for the target platform; cross-targeting depends on tool capabilities and corresponding module sets, and should not be assumed to be supported by default.

### 13.2. Build artifact matrix

| Target | Runtime image | Distribution package |
|---|---|---|
| Windows x64 | Windows x64 JVM and native components | ZIP/application image/installer |
| Windows ARM64 | Windows ARM64 JVM and native components | Corresponding ZIP/installer |
| Linux x64 | Linux x64 JVM and native components | TAR/OCI layer |
| Linux ARM64 | Linux ARM64 JVM and native components | TAR/OCI layer |
| macOS x64 | macOS x64 JVM and native components | Application bundle/installer |
| macOS ARM64 | macOS ARM64 JVM and native components | Application bundle/installer |

This matrix only outlines packaging possibilities per target; it does not assert that every JDK vendor provides binaries for every platform.

### 13.3. Linux libc and native dependencies

On Linux, you need to determine:

- glibc vs. musl environment.
- CPU architecture.
- Native dependencies used by JNI/frameworks.
- Base container image.
- File permissions.
- Runtime linker and system libraries.
- Security policies or FIPS requirements.

A runtime built for one Linux environment is not guaranteed to work across all distros and different libc implementations.

### 13.4. Windows and macOS

On Windows, launchers typically have `.exe` and scripts use `.bat`/PowerShell; path formats and separators differ from Unix-like systems.

On macOS, application bundles, code signing, and notarization can be important for desktop distributions. A `jlink` runtime image alone does not solve the full installation/signing distribution workflow; `jpackage` and platform tooling serve their own roles.

## 14. Creating launchers that avoid PATH dependency

### 14.1. Unix-like launcher

Example `bin/start.sh`:

```sh
#!/bin/sh
set -eu

APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

exec "$APP_HOME/runtime/bin/java" \
  -cp "$APP_HOME/app/application.jar:$APP_HOME/lib/*" \
  com.example.Main "$@"
```

This script assumes:

- `bin/start.sh` resides inside the bundle.
- `runtime/bin/java` exists for the corresponding OS.
- The main class is `com.example.Main`.
- Dependencies reside in `lib/*`.
- `APP_HOME` resolves to the bundle root directory.

`"$@"` forwards each received argument to the Java application without joining them into a single string that loses argument boundaries.

### 14.2. Windows PowerShell launcher

Example `bin/start.ps1`:

```powershell
$ErrorActionPreference = "Stop"

$appHome = Split-Path -Parent $PSScriptRoot
$java = Join-Path $appHome "runtime\bin\java.exe"
$appJar = Join-Path $appHome "app\application.jar"
$lib = Join-Path $appHome "lib\*"
$classPath = "$appJar;$lib"

& $java -cp $classPath com.example.Main @args
exit $LASTEXITCODE
```

This is a simple launcher example. If the target application requires specialized paths or argument-passing conventions, test on an actual Windows machine. Do not depend on a system-wide `java` command.

### 14.3. Do not mix shell quoting into Java arguments

If startup scripts encounter paths with spaces, quote them properly according to the operating system's shell. In Java code using `ProcessBuilder`, paths and arguments are separate elements; do not manually embed quote characters as data.

Within the bundle, keep directory names clear and avoid depending on whatever working directory the user launches from in the terminal.

### 14.4. Versioned launchers

A convenient structure for rollback:

```text
releases/
  2.1.0/
    runtime/
    app/
    bin/
  2.2.0/
    runtime/
    app/
    bin/
current -> releases/2.2.0
```

Depending on the OS, `current` can be managed via symlink, junction, config, or a supported installer mechanism. When updating, do not overwrite runtime files of a running process in an uncontrolled manner; deploy a new bundle, switch the startup target, and roll back using a verified release.

## 15. jpackage: from custom runtime to installer

### 15.1. When to use jpackage?

If end users need to install a desktop/CLI application in a manner native to their operating system, `jpackage` can generate an application image or installer. It works with the application input and a runtime image supplied or generated through supported mechanisms.

Example approach:

```text
Compile Java source
       |
       v
Create application JAR
       |
       v
Build custom runtime with jlink
       |
       v
jpackage creates app image / installer
       |
       v
Sign, publish, test install/uninstall
```

### 15.2. Example using a prebuilt runtime image

```shell
jpackage \
  --type app-image \
  --name ExampleApp \
  --input build/app \
  --main-jar application.jar \
  --main-class com.example.Main \
  --runtime-image build/runtime \
  --dest build/package
```

This example requires `build/app/application.jar` and the runtime image to already exist. Options, image layout, dependency packaging, signing, and installer types depend on OS/JDK version.

Do not treat an illustrative command as a complete production configuration. You also need to verify installer behavior, icons, versioning, file associations, OS permissions, and update strategy.

### 15.3. Do not mix two runtime-generation mechanisms inconsistently

If `jpackage` generates a runtime via its own configuration, running `jlink` separately beforehand is not strictly necessary. If your organization needs control over the module list, you can build the runtime image with `jlink` and pass it via `--runtime-image` when supported by the tool version.

What must be decided is **who is responsible for selecting modules and producing the final runtime artifact**. Avoid having two steps independently generate runtimes with different settings and accidentally using the wrong image.

### 15.4. Releases with multiple native artifacts

A desktop application may be accompanied by:

- Java runtime image.
- Main application JAR.
- Dependency JARs.
- Native libraries.
- Resource files.
- Configuration templates.
- Launcher and installer metadata.

Some assets need to be updated independently while others must stay coupled with the runtime; specify this clearly in the release manifest.

## 16. Container images and jlink

### 16.1. When is a custom runtime useful in containers?

In containerized services, an image commonly contains a JDK/JRE base image and the application JAR:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY application.jar /app/application.jar
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
```

This is a conceptual pattern. An image using a `jlink` runtime can help reduce size and control contents, especially if the application uses only a small set of JDK modules.

### 16.2. Multi-stage Dockerfile

Illustrative example for a classpath application and a runtime created from the JDK in the build stage:

```dockerfile
FROM eclipse-temurin:21-jdk AS runtime-builder

RUN jlink \
    --add-modules java.base,java.logging,java.net.http,jdk.crypto.ec \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output /opt/custom-runtime

FROM debian:bookworm-slim

WORKDIR /app

COPY --from=runtime-builder /opt/custom-runtime /opt/java
COPY application.jar /app/application.jar

ENV PATH="/opt/java/bin:$PATH"

ENTRYPOINT ["/opt/java/bin/java", "-jar", "/app/application.jar"]
```

This is a Dockerfile illustrating two stages, **not a complete security or distribution configuration**. In production, you must:

- Pin the base image by digest and patch policy.
- Choose a runtime base image compatible with libc/native dependencies.
- Enforce a non-privileged user.
- Verify certificates/truststore and DNS/TLS behavior.
- Retain license notices as required by distribution obligations.
- Update the runtime whenever the JDK releases security fixes.
- Verify required modules for frameworks, JDBC, JFR, and agents.
- Build and test on the exact target CPU architecture.

### 16.3. Distroless and runtime dependencies

A minimal or distroless base image can be used when appropriate. However, the JVM and native code still have OS/platform dependencies. You cannot assume copying a runtime image into a `scratch` image is sufficient for every JDK/build.

A small base image missing certificate data, locale files, or native libraries can cause failures that only appear in production. Test the exact final container image, not just the runtime builder stage.

### 16.4. Multi-layer container images

A potential benefit of OCI images is caching and layering. If the runtime changes less often than the application, you can place the runtime in an earlier layer and the JAR in a later layer; CI/registries can reuse layers.

However, when a JDK security update arrives, the runtime layer **must be rebuilt**. Do not leave a cached layer holding an old JVM just because application code has not changed.

## 17. Runtime security patching and support lifecycle

### 17.1. Bundling a runtime means owning patching responsibility

When users install Java through IT channels, the platform team may manage JRE updates. When an application ships its own bundled runtime, the release team must track:

- JDK vendor security updates.
- CVEs affecting JVM/runtime modules.
- Root CA updates and truststore.
- tzdb/locale data updates.
- Native runtime libraries.
- Whether the release line is still under maintenance or EOL.
- Container base image vulnerabilities if applicable.

An unchanged application.jar may still require a new release solely to update the runtime.

### 17.2. Patch level matters more than the major label

Example:

```text
Java 21 runtime A: older patch release
Java 21 runtime B: newer patch release
```

Both may report Java major 21, yet differ in security fixes, truststore, and behavior. Release metadata should record the JDK vendor, full version/build number, OS/arch, and runtime image checksum.

### 17.3. Do not silently update the runtime without testing

Patching the runtime is necessary, yet still carries regression risk:

- TLS/crypto policy changes.
- Timezone/locale data changes.
- JVM bug fixes exposing behavior that relied on an old bug.
- GC or performance behavior differences.
- Native library/agent compatibility differences.

Maintain a CI test matrix for patch upgrades, canary deployments, and rollback. Do not skip validation simply because the new version shares the same major number.

### 17.4. SBOM and provenance workflow

A release can record:

```text
Application version
Source commit
Application artifact SHA-256
JDK vendor
JDK full runtime version
Runtime image target OS/architecture
List of Java modules
Third-party dependency inventory/SBOM
Container image digest
Build tool version
Build timestamp/provenance
Test report
```

This information helps determine which releases are affected by a vulnerability and rebuild artifacts when needed.

### 17.5. License and notice obligations

Not all JDK distributions share the same commercial distribution terms or notice requirements. Before bundling, check the license for the **exact vendor, version, and binary**. A JDK-derived runtime image may also need to retain license notices provided by the JDK.

`jlink --no-man-pages` or `--no-header-files` is not a way to eliminate license obligations. Legal documentation/notices must be handled according to the applicable license.

## 18. Size, startup, and performance: measure instead of guessing

### 18.1. Disk size is not the only metric

When comparing bundled runtimes:

| Metric | Question |
|---|---|
| Runtime image size | How much space does it consume on disk? |
| Download size | How large is the compressed ZIP/installer/container layer? |
| Application startup | How long until it is ready to handle requests? |
| RSS/memory | Does it change significantly compared to the full runtime? |
| CPU | Does real-world workload performance differ? |
| TLS/locale behavior | Are any required providers/data omitted? |
| Diagnostics | Are needed JFR/management/attach paths still available? |
| Update footprint | How many bytes must be re-downloaded per runtime patch? |
| Operational complexity | Does it introduce OS/architecture packaging failures? |

A smaller runtime can reduce disk footprint and unused modules, but you should not claim it always runs faster or significantly lowers RSS without measuring.

### 18.2. Measuring on Unix-like systems

```shell
du -sh build/runtime
du -sh build/app-bundle
```

`du` is an OS utility, not a `jlink` option. Results depend on filesystem, block size, and packaging layout.

### 18.3. Measuring in PowerShell

```powershell
$bytes = (
    Get-ChildItem "build\runtime" -Recurse -File |
    Measure-Object -Property Length -Sum
).Sum

"{0:N2} MiB" -f ($bytes / 1MB)
```

When comparing across CI runners, record both distributed package size and extracted size; the two metrics have different meanings.

### 18.4. Benchmarks must be comparable

When comparing a custom runtime image against a full JDK, keep constant:

- Application code and dependencies.
- JVM flags.
- JDK vendor/full patch version if possible.
- OS/architecture.
- Workload and warm-up policy.
- Sample count and median/percentile calculation method.
- Filesystem/container/network conditions.

Do not compare a custom Java 21 build against an old JDK 8 and attribute the entire performance difference to `jlink`.

## 19. Updating the JDK version when using jlink

### 19.1. Not just changing a directory name

When migrating from Java 17 to Java 21:

1. Select a supported JDK 21 distribution.
2. Update build tool/compiler/toolchain if needed.
3. Check source/bytecode dependencies and framework support.
4. Run `jdeps` with the appropriate toolchain.
5. Review the `--add-modules` list and providers.
6. Build a new runtime image using `jlink` from the target JDK.
7. Package the application and new runtime.
8. Test on the target OS/architecture.
9. Record runtime checksum/provenance.
10. Deploy canary and keep the previous release for rollback.

Merely copying the JAR from an older release into a new runtime may still start, yet fail to address API/behavior changes, agent compatibility, and environment configuration.

### 19.2. The module graph can change

A JDK release may organize modules or provider implementations differently from the previous release. Therefore, do not assume `jdeps` output from an older JDK is sufficient for the newer JDK.

Re-run analysis in the build pipeline, review the module list diff, and run the required integration tests.

### 19.3. Minimum runtime of third-party libraries

An application compiled with `--release 17` does not guarantee a newer dependency still supports Java 17. If a dependency JAR contains class-file major version 65, a Java 17 runtime cannot load that class.

For a runtime image linked from Java 17, verify the entire runtime dependency closure is Java 17-compatible. If the image uses Java 21, confirm the app and libraries run on Java 21, not just check class-file major versions.

## 20. Diagnosing common errors

### 20.1. `java: command not found` after installation

**Cause:** the launcher script still invokes global `java` instead of the bundled runtime, or the bundle path is wrong.

**Resolution:** explicitly reference `runtime/bin/java` relative to the launcher location; verify execute permissions and correct OS binary.

### 20.2. `Module ... not found` when running jlink

**Cause:** the module path is missing the module, the module name is wrong, the application module is not built yet, or the JAR is only an automatic module.

**Resolution:** check `--module-path`, `jar --describe-module`, output modules, and explicit module descriptors. For non-modular dependencies, consider a runtime containing only JDK modules and distribute JARs separately.

### 20.3. `java.lang.NoClassDefFoundError` when running the application

**Cause:** a runtime dependency JAR is missing, the classpath is wrong, or a Java module was omitted.

**Resolution:** distinguish whether the class belongs to a JDK module or a third-party JAR. Use `jdeps`, dependency reports, and startup logs; do not add all JDK modules when the error is actually a missing application library.

### 20.4. `java.lang.module.FindException`

**Cause:** inconsistent JPMS module path/descriptor, missing module, or incorrect launcher configuration.

**Resolution:** cross-check `requires` and module path against linked modules, test `--list-modules`, `jar --describe-module`, and exact startup command.

### 20.5. `UnsupportedClassVersionError`

**Cause:** the application or a dependency has higher bytecode than the JVM in the runtime image.

**Resolution:** identify the runtime Java version, class-file major version, and source dependency. `jlink` does not automatically downgrade application bytecode target.

### 20.6. `NoSuchAlgorithmException` or TLS handshake failure

**Possible causes:** missing security provider, truststore, disabled protocol, or untrusted certificate.

**Resolution:** inspect the image's security providers and truststore, verify CA/hostname/protocol, add required modules based on evidence, and run HTTPS integration tests.

### 20.7. `UnsupportedCharsetException`

**Cause:** the application uses a legacy charset but the runtime lacks the corresponding provider.

**Resolution:** verify the actual charset of the data and needed module/provider such as `jdk.charsets` where applicable. Where feasible, standardize protocols onto UTF-8 with a clear migration plan.

### 20.8. Locale or date/currency formatting changes

**Cause:** missing `jdk.localedata` or locale/tzdb differences across JDK versions.

**Resolution:** inspect locale/timezone configuration, image modules, locale-filtering plugins, and golden fixtures for date/number formatting.

### 20.9. Java agent does not work

**Possible causes:** missing `java.instrument`, incompatible JDK/bytecode agent, wrong `-javaagent` path, dynamic attach policy, or OS permissions.

**Resolution:** determine startup vs. dynamic agent, check modules, manifest, logs, and JDK support matrix. Do not blindly enable `jdk.attach` when the agent needs a different mechanism.

### 20.10. JFR or `jcmd` is unavailable

**Cause:** the runtime was stripped down or lacks required serviceability tools.

**Resolution:** define the diagnostic workflow, include needed modules/tools in the build as appropriate, or provide a companion environment with appropriate permissions. Do not treat a custom image as a full JDK.

### 20.11. Running a Linux image on Windows fails

**Cause:** the runtime image contains OS/architecture-specific native components.

**Resolution:** create separate packages for each supported platform and verify native dependencies.

### 20.12. Native library fails to load in a container

**Cause:** mismatched CPU architecture, libc, runtime linker, permissions, or classifier.

**Resolution:** align JDK/container base image/native library ABI. `jlink` does not automatically resolve native compatibility.

### 20.13. Small image builds cleanly, yet the app fails only in production

**Cause:** a module used indirectly via reflection/ServiceLoader/JDBC/feature flag was never tested.

**Resolution:** add the runtime module with justification, expand test paths, and run the full acceptance matrix against the **final distributed image**.

## 21. Designing a Maven pipeline

### 21.1. Parts Maven should manage

In a Maven project, responsibilities can be split as:

```text
validate / compile / test
         |
         v
package application JAR
         |
         v
resolve runtime dependencies
         |
         v
analyze JDK modules
         |
         v
jlink runtime image
         |
         v
assemble distribution
         |
         v
verify / integration tests / publish
```

Not every step has to reside in a single Maven plugin. Some organizations use version-controlled packaging scripts and CI orchestration.

### 21.2. Controlling the toolchain

Example compile target property:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

This sets the target for application code, not an instruction for `jlink` to automatically choose the right JDK. The toolchain running `jlink` must be pinned by policy and matched against the target JDK runtime.

### 21.3. Application dependencies must be packaged

If the application still uses the classpath, Maven dependency/plugin configuration must supply all runtime-scope JARs for the distribution. Do not copy only the application JAR and runtime image if the runtime image does not contain required dependencies.

For JARs using an uber-JAR plugin, verify resource merging, service descriptors, and nested JAR behavior. `jlink` does not replace dependency packaging.

### 21.4. Reproducibility

Pin Maven Wrapper/compiler/plugin versions, dependency versions, and JDK vendor/full version. Store the module list, runtime image checksum, and license notices alongside the release.

The same `pom.xml` built with a different JDK patch release can yield a byte-different runtime image; do not assume pinning Maven alone is sufficient.

## 22. Designing a Gradle pipeline

### 22.1. Gradle Java toolchains

Example Groovy DSL:

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'com.example.Main'
}
```

Toolchains help Gradle select the JDK for integrated tasks. If using `jlink` via a plugin or custom task, verify which JDK that tool pulls `jlink` from; do not assume every task automatically uses the configured toolchain.

### 22.2. Task to link the runtime

A Gradle build can use a dedicated jlink plugin or a custom task invoking the `jlink` executable from the provisioned JDK. Define clear inputs and outputs:

```text
Inputs:
  Java modules selected
  Toolchain JDK version/vendor
  Application JAR
  Dependencies / module descriptors
  jlink plugin options

Outputs:
  build/custom-runtime/
  build/distribution/
```

Avoid tasks that implicitly rely on `JAVA_HOME` on developer machines while CI uses a different JDK.

### 22.3. Version catalogs, BOMs, and locks

Tools like version catalogs, Gradle platforms/BOMs, and dependency locking control the dependency graph, but do not verify modules inside the runtime image.

Whenever frameworks are upgraded, `jdeps` and integration tests must be re-run; a lockfile cannot prove the application needs no additional JDK modules.

### 22.4. Do not force custom runtime into every test task

You can use a full JDK in unit tests for fast development feedback, but there must be **at least one test tier** executing against the final custom runtime. Testing exclusively on a full JDK will hide missing modules.

## 23. Reproducibility and runtime image caching

### 23.1. Inputs affecting a runtime image

To reproduce an image:

- JDK vendor/distribution.
- JDK full build version.
- OS/architecture.
- Selected JDK modules.
- `jlink` options and plugin versions.
- Build environment.
- External application modules if linked together.
- Certificates/configuration added later by packaging steps.
- File timestamps/permissions and archive packaging settings.

### 23.2. Image checksums must attach to a clear scope

A runtime image is a multi-file directory. For checksum comparison, you can archive it with controlled file ordering/timestamps, or produce a per-file checksum manifest. If computing a checksum solely on a distributed ZIP, control ZIP metadata to achieve byte-for-byte reproducibility.

Do not naively compare a Windows image with a Linux image and treat a different SHA-256 as a build failure.

### 23.3. Build cache must invalidate when the JDK changes

An overly simplistic cache key:

```text
cache-key = application-commit
```

can reuse an outdated runtime image when a JDK security patch changes. A sound key should include JDK version/vendor, target platform, and jlink module/configuration fingerprint.

### 23.4. Immutable releases

Once published:

```text
ExampleApp-2.4.0-linux-x64.tar.gz
SHA-256: ...
Runtime JDK: ...
Application commit: ...
```

Do not overwrite the same name/version with a different artifact if update and caching systems rely on versions. Bump the release version or use content-addressed artifacts and store provenance.

## 24. Rollback capability and runtime updates

### 24.1. Runtime is part of the application version

If an app version was tested against a specific Java 21.0.x build, rolling back the app while keeping the new release's runtime may fail to restore the verified environment.

A safe strategy is versioning the entire bundle:

```text
Release 3.1.0:
  app.jar v3.1.0
  runtime JDK version A

Release 3.2.0:
  app.jar v3.2.0
  runtime JDK version B
```

Bundle rollback restores both app and runtime. However, if data schemas have been upgraded, rollback still requires a separate data policy.

### 24.2. Atomic updates

For desktop/service distributions, the update workflow should avoid half-old, half-new states:

1. Download/copy the new bundle into a temporary directory.
2. Verify checksum/signature.
3. Validate file layout and permissions.
4. Stop or drain traffic away from the old process per procedure.
5. Switch the launcher/version target path atomically or via a supported installer mechanism.
6. Start up, healthcheck, and monitor.
7. Roll back if needed.

Never overwrite binaries inside a runtime directory actively used by a running process.

### 24.3. Data and protocols still require compatibility

`jlink` only controls the execution environment; it does not automatically keep JSON, database schemas, Java Serialization, or message protocols compatible.

If the new app version wrote data the older version cannot read, rolling back the runtime/JAR can still fail. This is a separate migration axis requiring testing.

## 25. Custom runtime test matrix

A useful test table:

| Group | Test scenario | Reason |
|---|---|---|
| Startup | Launch via `runtime/bin/java` | No reliance on global Java |
| Java modules | `--list-modules` and real execution paths | Detect missing modules |
| Dependency | Class loading, SPI, JDBC driver | Detect missing JAR/service providers |
| Networking | HTTP/HTTPS, proxy, DNS | TLS/crypto/truststore |
| Data | JDBC, XML, JSON, timezone | APIs and providers |
| Locale | vi-VN, en-US, and Unicode | Locale/charset behavior |
| File I/O | Read/write/temp, permissions | OS-specific paths |
| Security | Auth, certificates, cryptography | Providers and trust policies |
| Observability | Logs, JFR, agents, management | Diagnostic capability |
| Native | JNI, image codecs if used | ABI/OS/architecture |
| Performance | Startup, RSS, latency | Evaluate trade-offs |
| Deployment | ZIP/installer/container image | Final artifact |
| Update | Patch JDK, install/uninstall, rollback | Runtime lifecycle |

### 25.1. Testing on the lowest declared JDK

If the application JAR targets Java 17 while the runtime is linked from Java 21, the **packaged release** only runs on the bundled Java 21 runtime. If your organization simultaneously publishes a standalone JAR for users bringing their own Java 17, a separate Java 17 test path is required.

Do not conflate "bytecode supports Java 17" with "a bundle containing only a Java 21 runtime was tested on Java 17".

### 25.2. Testing by platform

Example deployment targets:

```text
Windows x64      : app + runtime Windows x64
Linux x64 glibc  : app + runtime Linux x64
Linux ARM64      : app + runtime Linux ARM64
macOS ARM64      : app + runtime macOS ARM64
```

Do not infer compatibility across all targets from success on one target. In particular, run native integration tests on real hardware architectures when JNI is involved.

### 25.3. Testing in an environment without Java pre-installed

If the product requirement is self-contained, test on a clean VM/container with no global `java`. Startup must use the bundled runtime and must not implicitly depend on system `JAVA_HOME`.

## 26. Common mistakes

**Merely copying the `jre` directory from JDK 8 into a new release.** Runtime layout and the module system have changed; use a JDK/runtime distribution suited to the target version.

**Assuming jlink only works with modular applications.** `jlink` links Java modules; classpath applications can still use a custom runtime containing JDK modules and be packaged separately.

**Assuming jlink embeds all external JARs.** Many third-party JARs are not explicit modules and cannot be directly linked under the standard JPMS model.

**Relying completely on jdeps.** Static analysis can miss reflection, ServiceLoader, JDBC, plugins, or framework-specific code paths.

**Creating a tiny java.base-only image without testing.** Startup may succeed while HTTPS/JDBC/locale/diagnostics fail.

**Forgetting security and locale modules/providers.** TLS, encoding, or date/currency formatting can fail in production.

**Assuming a custom runtime runs across every OS/architecture.** Images contain platform-specific native components.

**Dropping all diagnostic tools to save a few MB.** SREs may lose JFR/JMX/attach paths required for incident response.

**Assuming jlink automatically ensures Java source/dependency compatibility.** It does not downgrade application bytecode or fix removed frameworks/APIs.

**Only updating application.jar when a JDK security patch lands.** The bundled runtime must also be updated and re-released.

**Bundling a runtime without checking licenses.** Distribution rights and notices depend on binary/vendor/license.

**Testing on a full JDK without testing the final image.** This is the most common source of missing-module bugs.

## 27. Practical migration workflow from legacy JRE to jlink

### Phase 1: Baseline inventory

Collect:

```text
Application:
  version
  main class/module
  framework
  package format
  runtime dependencies

Existing Java:
  vendor
  full version
  OS/architecture
  installation/distribution model
  JVM flags
  truststore/custom CA

Operations:
  diagnostic tools
  agents/JFR
  deployment/update/rollback
  license policy
```

You do not need to read every file on production machines if a managed inventory exists, yet you must confirm the exact runtime the application is using.

### Phase 2: Choose a distribution model

Options:

- Keep system-managed JDK/runtime if infrastructure already manages Java centrally.
- Bundle a vendor runtime distribution if minimal customization is desired.
- Use `jlink` when control over module list and image size is needed.
- Combine `jlink` + `jpackage` for desktop installers.
- Put a `jlink` runtime into an OCI image for containerized services.

These are architectural options, not a mandatory sequence where every step must be executed.

### Phase 3: Identify Java modules and dependencies

1. Build the application using the standard toolchain.
2. Export the dependency graph/packaged JAR list.
3. Run `jdeps --print-module-deps` with the appropriate classpath.
4. Add modules for reflection, services, JDBC, locales, crypto, and JFR/agents.
5. Verify explicit module descriptors if linking application modules.
6. Record the module list as part of release configuration.

### Phase 4: Build the runtime image

General example for a classpath application using JDK modules:

```shell
jlink \
  --add-modules java.base,java.logging,java.net.http,java.sql,jdk.crypto.ec \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
```

This is a hypothetical configuration, **not a sufficient module list for every application**.

### Phase 5: Assemble the distribution

```text
build/dist/
  runtime/
  app/
    application.jar
  lib/
    ...
  agents/
    ... (if any)
  bin/
    start.sh
    start.ps1
  licenses/
    ...
  manifest.json
```

The launcher must target the OS-appropriate runtime and application layout. The manifest can record application version, JDK version, and checksums.

### Phase 6: Test with the final runtime

Execute `build/dist/runtime/bin/java` itself or the launcher inside the final distribution, not solely the CI build JVM.

Verify the test matrix: startup, TLS, JDBC, locale, reflection/SPI, native, agents/JFR, performance, OS/architecture, and rollback.

### Phase 7: Release and patch governance

1. Pin JDK vendor/full version and base image.
2. Store artifact checksums/provenance.
3. Publish immutable bundle/installer/OCI image.
4. Deploy canary.
5. Monitor runtime exceptions, startup time, and resource usage.
6. Keep the previous release for rollback.
7. Track JDK security updates and rebuild the runtime periodically.

## 28. Hands-on exercises

### Exercise 1: Build a runtime for a CLI

A Java 21 CLI uses `java.logging` and `java.net.http`, has no GUI, and has no native dependencies.

Tasks:

1. Build the application JAR.
2. Run `jdeps --print-module-deps`.
3. Create an image with `jlink`.
4. Package the app JAR and runtime into one directory.
5. Write a launcher without relying on Java in PATH.
6. Compare the image size with a full JDK.
7. Run HTTP/HTTPS smoke tests on the custom runtime.

### Exercise 2: Detecting an omitted module

A JDBC app runs on a full JDK yet fails when opening a reporting screen on a custom runtime.

Determine:

- Is this a missing Java module or a missing third-party driver JAR?
- Is `ServiceLoader`/JDBC auto-registration used?
- Did `jdeps` see this code path?
- What test should be added to catch this prior to release?

### Exercise 3: Cross-platform runtimes

A desktop app must ship on Windows x64 and macOS ARM64. Design the build matrix, explain why a Windows runtime image cannot simply be reused as a macOS runtime, and propose `jpackage`/installer signing steps for each target.

### Exercise 4: Java agent and JFR

A service needs an APM agent at startup and JFR during incident investigation. List the modules/capabilities to verify when creating a runtime with `jlink`, explicitly noting factors that cannot be concluded from `jdeps` alone.

### Exercise 5: Security patch

Release 2.4.0 bundles a JDK runtime with a newly disclosed vulnerability while application source code has not changed. Build a workflow to regenerate the bundle with the patched JDK, verify checksums, test TLS/database connectivity, and deploy/roll back.

## 29. Pre-release checklist for bundled runtimes

### Architecture and modules

- [ ] Decided whether to bundle a runtime or continue using system-managed Java.
- [ ] Distinguished among JDK, JRE/runtime distribution, `jlink`, and `jpackage`.
- [ ] Know whether the application is modular or classpath-based.
- [ ] Checked Java modules using `jdeps` and real execution tests.
- [ ] Did not attempt to link automatic modules as explicit modules where unsupported.
- [ ] Reviewed reflection, ServiceLoader, JDBC, and plugin loading.
- [ ] Verified the module list in the final image.

### Runtime behavior

- [ ] Launcher uses `runtime/bin/java`, without relying on global Java.
- [ ] App and dependencies are completely packaged.
- [ ] HTTPS/truststore/security providers work.
- [ ] Charset, locale, and timezone are appropriate.
- [ ] Java agents, JFR, management, and diagnostic workflows remain functional.
- [ ] JNI/native dependencies match target OS/architecture.
- [ ] Minimum runtime and dependency class-file versions verified.

### Release

- [ ] JDK vendor/full patch version is pinned.
- [ ] Separate bundles exist for each supported OS/architecture.
- [ ] Licenses and notices have been checked.
- [ ] Runtime/image checksums and provenance are recorded.
- [ ] Installer/container image tested against the exact final artifact.
- [ ] Process exists to update the runtime when JDK security patches arrive.
- [ ] Rollout/canary/rollback and monitoring data are in place.
- [ ] Never overwrite a runtime directory actively used by a running process.

## Conclusion

**Bundled JREs** and **custom runtimes built with `jlink`** both address the need to control the Java execution environment, yet at two different levels of control. Bundling a vendor runtime is a direct way to eliminate dependence on client-installed Java. `jlink` goes further by linking only the needed Java modules into a runtime image distributable with the application.

To use `jlink` sustainably in Java Advance Compatibility Migration, understand JPMS and the limits of automatic modules, treat `jdeps` as a starting point rather than the sole source of truth, verify reflection/SPI/JDBC/security/locale/agents, and test the final runtime image directly on the target OS/architecture. Size optimization must be balanced against diagnosability, correctness, and security updates. When a runtime ships alongside an application, **the runtime is also part of the product**, requiring versioning, testing, patching, signing/verification, and rollback with the same discipline as the application artifact.
