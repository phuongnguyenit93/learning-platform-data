# Java Toolchains and Selecting GraalVM for Native Builds

In the **Gradle** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module, we need to answer a practical question: **which Java installation does Gradle use to compile the Spring Boot application, and which GraalVM installation does it use to build the native executable?** These two choices are related, yet not identical. A single machine can have Temurin JDK, GraalVM JDK, and multiple Java versions installed simultaneously; without controlling the toolchain, the JVM build may succeed while `nativeCompile` fails or picks the wrong tool.

This lesson walks through configuring **Gradle Java Toolchains** and **GraalVM Native Build Tools** to run Spring AOT and produce a GraalVM Native Image. It establishes the foundation for handling reflection/resource metadata, compatibility testing, container packaging, and measuring startup time and memory footprint for Spring Boot native applications.

> **Version scope:** the examples use Java 21 and common Gradle/GraalVM Native Build Tools DSL syntax. In a real project, you must select compatible versions of Java, Gradle, Spring Boot, and the Native Build Tools plugin. The sample configuration assumes the project has already applied the required plugins; any differences in plugin APIs or toolchain detection must be verified against the exact version your project uses.

## 1. Learning Outcomes

Upon completion, you will be able to:

1. Distinguish between the **JVM running Gradle**, the **JDK selected by Java Toolchains**, and the **GraalVM JDK providing the Native Image tool**.
2. Declare the Java language version and GraalVM vendor in `build.gradle` or `build.gradle.kts`.
3. Understand the role of `graalvmNative.toolchainDetection` and how to verify which tool was actually selected.
4. Configure multi-JDK environments on local machines or CI without relying on guesswork from `java -version`.
5. Diagnose common errors: wrong Java version, GraalVM not found, missing `native-image` executable, or missing OS compiler/linker.

## 2. Three Layers of Java Selection in a Gradle Build

Gradle does not have just one single notion of "which JDK is being used." You must distinguish:

| Layer | Component | Responsibility | Common Configuration Sources |
|---|---|---|---|
| **A. Gradle JVM** | Java running the Gradle daemon/build logic | Runs Gradle, build scripts, and plugins | `JAVA_HOME`, IDE Gradle JVM, `org.gradle.java.home`, or Daemon JVM configuration |
| **B. Java Toolchain** | JDK for Java tasks | Runs the compiler or related Java tasks matching version/vendor requirements | `java { toolchain { ... } }` block and Java Toolchains service |
| **C. Native Image toolchain** | GraalVM JDK with `native-image` | Analyzes the application and compiles the native executable | JDK detection/selection mechanism in the GraalVM Native Build Tools plugin |

All layers can point to **a single GraalVM JDK**, though that is not mandatory. For example:

~~~text
Gradle daemon       -> Temurin JDK 21
Java compile/test   -> GraalVM JDK 21
Native Image        -> GraalVM JDK 21, with native-image
Native linker       -> Linux C/C++ toolchain
~~~

Or a setup that is simpler to manage:

~~~text
Gradle daemon       -> GraalVM JDK 21
Java compile/test   -> GraalVM JDK 21
Native Image        -> GraalVM JDK 21, with native-image
Native linker       -> OS C/C++ toolchain
~~~

### Relationship Diagram

~~~mermaid
flowchart TD
    S["Spring Boot source"] --> G["Gradle daemon + plugins"]
    A["JDK running Gradle"] -. "Runs build logic" .-> G
    G --> J["Java compile + Spring AOT"]
    B["Gradle Java Toolchain"] -. "Selects compiler and Java launcher" .-> J
    J --> I["Class files, AOT code, metadata"]
    I --> N["nativeCompile / GraalVM Native Image"]
    C["GraalVM JDK with native-image"] -. "Selects native compilation tool" .-> N
    D["OS C/C++ compiler and linker"] -. "Builds platform executable" .-> N
    N --> E["Native executable"]
~~~

**A Java Toolchain is not the Native Image tool.** A standard JDK can satisfy `languageVersion = 21` without providing `native-image`. Conversely, a GraalVM JDK can provide both the Java compiler and Native Image if the proper version and components are installed.

## 3. What Problem Do Java Toolchains Solve?

Suppose developer A uses JDK 21 to run Gradle, developer B runs Gradle with JDK 22, and CI has JDK 17. If the project relies solely on each machine's default Java, compilation results can be inconsistent.

Gradle Java Toolchains allow the project to **declare the JDK that Java tasks need**, instead of assuming every task uses the JVM running Gradle:

~~~groovy
// build.gradle (Groovy DSL)
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

With Kotlin DSL:

~~~kotlin
// build.gradle.kts
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

This configuration means **toolchain-aware Java tasks** require Java 21 tools. It does NOT mean:

- The Gradle daemon will switch to running on Java 21.
- Gradle will automatically install Java 21 in every environment. Automatic JDK downloading depends on a configured toolchain resolver and support in your Gradle version.
- The selected Java 21 JDK is guaranteed to be **GraalVM**.
- The selected JDK is guaranteed to contain the `native-image` executable.

Therefore, declaring only `languageVersion` is insufficient for a native build pipeline where you need explicit control over the GraalVM distribution.

### Java Version, Vendor, and Implementation

Java Toolchains can describe multiple JDK attributes. The two most important attributes in this lesson are:

- **`languageVersion`:** e.g., Java 21; corresponds to the Java release generation required by the tasks.
- **`vendor`:** the JDK publisher or distribution, such as GraalVM rather than any arbitrary JDK.

In Gradle versions that support the `JvmVendorSpec.GRAAL_VM` constant:

~~~groovy
// build.gradle
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}
~~~

~~~kotlin
// build.gradle.kts
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}
~~~

In environments where vendor identification strings differ, some Gradle versions allow using `JvmVendorSpec.matching("...")` with the actual vendor string. To know which string is detected, **inspect the output of `javaToolchains` before filling in a name**. Requiring the right vendor filters out standard JDKs from Java Toolchain selection, but you must still confirm that the Native Image tool is present and that the native plugin is using that exact JDK.

### How Do `sourceCompatibility` and `options.release` Differ from Toolchains?

Example:

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Source/target compatibility settings or `--release` describe **the language level and target API/bytecode to emit**. They do not automatically choose **which installed JDK** runs the compiler. A compiler that is too old might not support `--release 21`; and a newer compiler can emit Java 21 bytecode without being GraalVM.

For native builds, choose the toolchain first, then add release rules if the project needs to explicitly constrain APIs and bytecode.

## 4. How Does GraalVM Native Build Tools Select the Tool?

When a project applies the **`org.graalvm.buildtools.native`** plugin, Gradle gains tasks like `nativeCompile` to build the native executable. The plugin needs to locate a **GraalVM JDK with Native Image**.

A common configuration is:

~~~groovy
// build.gradle
graalvmNative {
    toolchainDetection = true
}
~~~

~~~kotlin
// build.gradle.kts
graalvmNative {
    toolchainDetection = true
}
~~~

When toolchain detection is enabled, the plugin integrates with Gradle's Java Toolchains discovery according to the API of the **Native Build Tools version in use**. Paired with the GraalVM vendor configuration from the previous section, the project's intent becomes clearer: Java 21 from GraalVM is required, rather than any Java 21.

Do not assume that enabling `toolchainDetection` means the environment is already verified. If the machine lacks a matching GraalVM, Gradle may report a missing toolchain or missing Native Image. If the machine has multiple GraalVM installations, read the logs to verify **which executable is actually invoked**.

### Difference from `JAVA_HOME` and `PATH`

`JAVA_HOME` and `PATH` are process environment variables. They are convenient for quick developer machine setup, but they do not represent the full Java Toolchains mechanism:

- `JAVA_HOME` typically affects the JVM used to launch the Gradle wrapper, unless a higher-priority option is set.
- `PATH` determines which `java` or `native-image` command the shell finds when invoked directly.
- Gradle Java Toolchains can discover JDKs in many other directories and select based on `languageVersion`/`vendor`.
- The GraalVM Native Build Tools plugin has its own rules for choosing the launcher/executable, depending on the plugin version and detection mode.

Example:

~~~text
JAVA_HOME=/opt/jdks/temurin-21
PATH contains /opt/jdks/temurin-21/bin

Gradle java.toolchain:
  Java 21, vendor GraalVM

Installed GraalVM:
  /opt/jdks/graalvm-jdk-21
~~~

If Gradle discovers GraalVM and the native plugin selects the right toolchain, `nativeCompile` can still use GraalVM even though `java -version` in the terminal displays Temurin. **The true value must be verified in Gradle's toolchain output and build logs.**

## 5. Complete Gradle Configuration Examples

The following snippets focus on the **toolchain configuration portion** of a Spring Boot project that already declares the Spring Boot and GraalVM Native Build Tools plugins. They do not pin specific plugin versions, as compatible versions must be chosen for your actual project.

### 5.1. Groovy DSL — `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'org.graalvm.buildtools.native'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}

graalvmNative {
    toolchainDetection = true
}
~~~

In this example, the plugin declarations **assume versions are managed outside this block** (for example, via `pluginManagement` or the project's plugin management mechanism). If initializing a standalone Gradle project, declare appropriate plugin versions where Gradle can resolve them. In addition, the Spring Boot application must still have its required dependencies and source code.

Meaning:

1. The Java plugin provides Java tasks and the `java.toolchain` extension.
2. The Java Toolchain requests **Java 21, vendor GraalVM** for supporting tasks.
3. The GraalVM Native Build Tools plugin creates native tasks and locates the Native Image tool per the configuration.
4. The Spring Boot plugin participates in the build lifecycle and wires the Spring AOT flow needed for native applications.

When a project already has a `plugins` block, **add or adjust only the missing blocks**; avoid declaring the same plugin twice.

### 5.2. Kotlin DSL — `build.gradle.kts`

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
    id("org.graalvm.buildtools.native")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}

graalvmNative {
    toolchainDetection = true
}
~~~

Both styles express the same intent. Plugin resolution syntax, property types, and DSL details must match the Gradle/plugin versions in use. If the project already applies the native plugin via a convention plugin or defines versions in a version catalog, **preserve that management mechanism**.

### 5.3. When You Only Want One GraalVM JDK on the Machine

For a first hands-on exercise, the easiest reproducible setup is installing **one GraalVM JDK 21** compatible with the project, ensuring the `native-image` command is present, using it to run Gradle, and declaring the Java Toolchain with the same version/vendor:

~~~bash
# Linux/macOS: replace the path with your actual GraalVM installation
export JAVA_HOME=/opt/jdks/graalvm-jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

java -version
native-image --version
./gradlew --version
./gradlew javaToolchains
~~~

Each line verifies a different aspect: Java found by the shell, Native Image directly, the JVM running Gradle, and the list of toolchains known to Gradle.

On PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\jdks\graalvm-jdk-21'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

java -version
native-image --version
.\gradlew.bat --version
.\gradlew.bat javaToolchains
~~~

The environment variable changes here apply only to **the current terminal session**. When running from IntelliJ IDEA or CI, the Gradle JVM and toolchain paths may be configured separately.

## 6. Verifying Which JDK Is Actually Selected

### Step 1: Check the JVM Running Gradle

~~~bash
./gradlew --version
~~~

The output shows the Gradle version and JVM information. In Gradle versions that separate launcher/daemon JVMs, read the corresponding lines carefully; some older versions use a different format. Never treat the shell's `java -version` as your only evidence.

### Step 2: List Java Toolchains Detected by Gradle

~~~bash
./gradlew javaToolchains
~~~

This task lists the JDKs detected by Gradle along with attributes such as path, Java language version, and vendor. Illustrative output:

~~~text
Detected toolchains (illustrative):
  /opt/jdks/temurin-21      -> Java 21, Eclipse Adoptium
  /opt/jdks/graalvm-jdk-21  -> Java 21, GraalVM
~~~

Every machine's output does not need to match the example verbatim. The goal is to confirm Gradle sees **the exact GraalVM installation you intend to use**. If GraalVM is absent from the list, first check the installation directory and how Gradle discovers JDKs.

### Step 3: Run the Native Build Task with Verbose Output

~~~bash
./gradlew nativeCompile --info
~~~

The task executes the steps required to produce a native executable when the application and plugins are properly configured. Logs show the toolchain path and the Native Image command executed. On failure, add `--stacktrace` for full context:

~~~bash
./gradlew nativeCompile --info --stacktrace
~~~

Read the log to answer:

- From **which path** is the `native-image` tool being invoked?
- Which **GraalVM/Java version** does it belong to?
- Are Spring AOT processing, metadata handling, and native compilation running as expected?
- Did the failure occur in **Gradle configuration**, **Java compilation**, **Spring AOT**, **Native Image analysis**, or **native linking**?

If the build completes, run the executable and execute functional tests before comparing startup/memory with the JVM build. **A passing build** does not guarantee all reflection, resources, serialization, or endpoints behave correctly at runtime.

### Step 4: Check the Gradle Daemon When Changing JDKs

If you just switched the Gradle JVM and the output still looks confusing, stop the daemon and re-run the verification commands:

~~~bash
./gradlew --stop
./gradlew --version
./gradlew javaToolchains
~~~

`--stop` eliminates stale daemons of the same Gradle version still running in the background. It **does not install JDKs, fix toolchain configuration**, or replace reading the build logs.

## 7. Multi-JDK Machines: Proactively Locating GraalVM

Developer and CI machines often host multiple JDKs of the same major version. For instance, two Java 21 directories:

~~~text
/opt/jdks/temurin-21
/opt/jdks/graalvm-jdk-21
~~~

To make Gradle aware of a specific JDK installation directory, you can configure **Java installation paths** in `gradle.properties`:

~~~properties
# Illustrative Linux path; adjust for your machine or CI.
org.gradle.java.installations.paths=/opt/jdks/graalvm-jdk-21
~~~

This property **adds a location for JDK discovery**; it does not force every task to use that JDK, nor does it prove that the JDK includes Native Image. If multiple installations match, use `vendor` and verify the selection. On Windows, pay close attention to path syntax in `.properties` files regarding backslashes and path separators.

Another option is configuring Gradle with a toolchain resolver to download JDKs in permitted environments. Automatic toolchain downloading depends on **the Gradle version, configured repositories/resolvers, and CI network policies**. Do not assume Gradle will automatically download GraalVM solely because of `vendor = JvmVendorSpec.GRAAL_VM`.

### What Configuration Should Be Committed to the Repository?

You should commit:

- Versions of the Gradle Wrapper, Spring Boot plugin, and GraalVM Native Build Tools.
- The Java version required by the project; and the vendor filter when the project intentionally requires GraalVM.
- Configuration required for native builds/tests and Spring AOT.

Think carefully before committing machine-specific paths like `/Users/username/graalvm` or `C:\jdks\graalvm`, as they are not portable. In CI, install the JDK at a standard path or let the pipeline inject environment-specific paths.

### When You Want Gradle to Run on a Different JDK Than the Java Toolchain

Example:

~~~text
Gradle daemon JVM: Temurin 21
Java Toolchain:    GraalVM 21
Native Image:      GraalVM 21
~~~

This is a valid setup **when supported by your Gradle/plugin versions**. You do not have to force the daemon onto GraalVM just for the Native Image task to pick GraalVM. However, avoid assuming that changing `JAVA_HOME` alone overrides a declared Java Toolchain.

In an IDE, the **Gradle JVM** setting can be independent of both the project JDK and your terminal. To investigate discrepancies between the IDE and command line, compare the Gradle daemon JVM, Java installations, and native task logs in both environments.

## 8. Connection to Spring AOT and the `nativeCompile` Task

Spring AOT analyzes application configuration and prepares code and metadata to reduce reliance on certain dynamic JVM behaviors. When the Spring Boot Gradle plugin and GraalVM Native Build Tools are properly combined, the native build pipeline consumes that output to build the executable.

A typical logical sequence:

~~~text
Java source / resources
    ↓
Java compilation, dependency resolution
    ↓
Spring AOT processing and generated sources/resources
    ↓
GraalVM Native Image reachability analysis
    ↓
Native compiler/linker
    ↓
Native executable
~~~

**Picking the right GraalVM does not solve every AOT error.** If a library accesses classes via reflection that Native Image cannot observe through static analysis, the application may require **Runtime Hints/reachability metadata**. Likewise, resources must be declared appropriately if Native Image does not include them automatically. These are **compatibility and metadata issues**, distinct from Gradle picking the wrong JDK.

In many Spring Boot projects, the primary command for a native build is:

~~~bash
./gradlew nativeCompile
~~~

If Gradle reports that this task does not exist, check whether the Native Build Tools plugin is applied in the right place (root or subproject) and verify the plugin version. Do not conclude GraalVM is installed incorrectly simply because the task does not exist.

### Multi-Module Projects

In projects with multiple subprojects, `java.toolchain` and `graalvmNative` blocks may live in the application module or a convention plugin. Adding configuration to the root project does not mean **every subproject automatically inherits it**. Check which module applies the Java/Spring Boot/Native Build Tools plugins and invoke the task via its module path, for example:

~~~bash
./gradlew :application:nativeCompile --info
~~~

The name `application` here is only an example; replace it with your project's module name.

## 9. Direct Native Builds vs. `bootBuildImage`

Two build paths are frequently confused:

| Build Path | Where Does Native Image Run? | What Is the Host JDK's Role? |
|---|---|---|
| `nativeCompile` | Typically runs directly in the Gradle task execution environment | Gradle/plugin locates GraalVM and uses the machine's native toolchain |
| `bootBuildImage` with native buildpack | Runs inside the Cloud Native Buildpacks **builder image** | The host JDK runs Gradle; the GraalVM/Native Image inside the builder may differ |

With the Spring Boot Gradle plugin, enabling native mode in buildpacks can be done via the buildpack environment if the builder supports it:

~~~groovy
// Groovy DSL example, in a project that already has the bootBuildImage task.
tasks.named('bootBuildImage') {
    environment = ['BP_NATIVE_IMAGE': 'true']
}
~~~

In projects that already configure other environment variables on this task, **merge** the new entry instead of overwriting the existing environment map. The exact API for the `environment` property can vary by Spring Boot Gradle plugin version; check the DSL for the version you run.

When using buildpacks, `./gradlew javaToolchains` on the host **does not necessarily** reflect the GraalVM used inside the builder. Inspect the **builder image logs and configuration**. Native binaries are built for the OS/architecture of their build environment; you cannot assume a Windows native executable will run inside a Linux container.

## 10. Why Can Native Builds Still Fail with the Right Java Version?

### 10.1. Toolchain Selects Java 21, but It Is a Standard JDK

**Symptom:** Gradle compiles Java successfully, yet `nativeCompile` cannot find Native Image or a compatible GraalVM installation.

**Cause:** `languageVersion = 21` may select Temurin 21, whereas the native plugin requires a GraalVM JDK. **Fix:** specify the toolchain vendor and inspect the native task log; add a GraalVM constraint if the project needs it.

### 10.2. Gradle Does Not Detect Installed GraalVM

**Symptom:** GraalVM is installed in a local directory, yet `javaToolchains` does not list it or the plugin reports no matching toolchain found.

**Possible causes:** wrong directory depth for the JDK, restricted JDK discovery, Gradle cannot access the path, vendor/version mismatch, or unconfigured resolver. **Fix:** run `javaToolchains`, configure `org.gradle.java.installations.paths` if needed, and inspect Gradle logs.

### 10.3. GraalVM JDK Selected, but Missing `native-image`

**Symptom:** `java -version` shows GraalVM, yet the native task reports it cannot find the Native Image executable.

**Cause:** the installed GraalVM distribution does not include the Native Image component, or the plugin is pointing at a different directory. Depending on the GraalVM release, Native Image may be bundled or require separate installation. **Do not apply a single installation command blindly across all GraalVM generations.**

**Fix:** inspect executables inside the `bin` directory of the selected JDK, run `native-image --version` directly from that directory, and compare against the plugin log.

### 10.4. Java Class File Version / Unsupported Release Errors

**Symptom:** messages about unsupported class file major version, invalid source release, or tools not supporting the Java level.

**Cause:** the compiler JDK or Native Image is too old for the project's bytecode/source level. **Fix:** compare Java source/target/release settings, the toolchain JDK, the Native Image version, and Spring Boot/plugin requirements.

### 10.5. Missing C/C++ Compiler, Linker, or OS Libraries

**Symptom:** Java compilation and Spring AOT succeed, but Native Image reports missing `cc`, `ld`, `cl.exe`, headers, or SDK.

**Cause:** GraalVM Native Image depends on the OS native toolchain during compilation/linking. **Fix:** install the appropriate toolchain for Linux/macOS/Windows; ensure the terminal/CI has loaded the compiler environment. This is not a Gradle Java Toolchains bug.

### 10.6. Native Build Succeeds, but Application Fails at Runtime

**Symptom:** the executable launches but fails during deserialization, reflection, or resource loading.

**Common causes:** missing Runtime Hints/resource metadata, assumptions about dynamic class loading, or incompatible libraries. **Fix:** test the native build and add metadata as needed. Do not keep swapping JDKs once you have confirmed the toolchain is selected correctly.

### Quick Troubleshooting Table

| Failing Step | Evidence to Inspect | Area to Fix |
|---|---|---|
| Gradle fails to start | `./gradlew --version`, daemon Java | Gradle JVM / Gradle version |
| Cannot select Java compiler | `./gradlew javaToolchains` | Java Toolchain version/vendor/discovery |
| Missing `nativeCompile` | Task list and applied plugins | Gradle Native Build Tools configuration |
| Missing GraalVM/`native-image` | `nativeCompile --info` log and GraalVM directory | Native toolchain detection/installation |
| Native compiler/linker error | Native build log | OS C/C++ toolchain/SDK |
| Executable behaves incorrectly | Runtime tests, stack traces, metadata | Spring AOT, reflection/resources, libraries |

## 11. CI Strategy for Reproducible Builds

A reliable native build pipeline should explicitly specify:

1. The **Gradle Wrapper** is used, avoiding reliance on a pre-installed Gradle on the agent.
2. The **Java version/vendor** required for the compiler and Native Image is declared in the project.
3. CI installs a **compatible GraalVM JDK version** and ensures `native-image` is present.
4. The environment provides the right **C/C++ compiler/linker** and platform libraries.
5. The pipeline logs `./gradlew --version`, `./gradlew javaToolchains`, and `native-image --version` where applicable; the native task log confirms which executable is actually invoked.
6. The native executable passes smoke tests or integration tests on an OS/architecture matching the deployment target.

An illustrative sequence:

~~~bash
./gradlew --version
./gradlew javaToolchains
native-image --version
./gradlew clean nativeCompile --info
~~~

This is a **reference sequence** when Native Image runs on the host. In real CI pipelines, clearly specify where GraalVM/Native Image is set up; `native-image --version` from `PATH` does not replace verifying the native task log. `clean` can significantly increase build time, so use it only when a clean build or comparison baseline is needed.

**Build reproducibility** does not mean binaries must have identical checksums across every machine. Output can be affected by toolchain versions, OS/architecture, native libraries, and other build factors. The immediate goal is controlling critical inputs and measuring performance under consistent conditions.

## 12. Guided Practice

Suppose you have a Spring Boot project supporting Java 21, already configured with the Spring Boot and GraalVM Native Build Tools plugins. The machine has:

~~~text
JDK A: /opt/jdks/temurin-21
JDK B: /opt/jdks/graalvm-jdk-21
~~~

**Requirement:** use JDK B to compile Java and build the native executable, regardless of which JDK currently runs the Gradle daemon.

**Step 1.** In `build.gradle`, declare:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.GRAAL_VM
    }
}
graalvmNative {
    toolchainDetection = true
}
~~~

**Step 2.** Run:

~~~bash
./gradlew --version
./gradlew javaToolchains
~~~

Record the **JVM running Gradle** and the **path to JDK B** in the toolchains list. If JDK B is not detected, adjust JDK discovery (for example, Java installation paths) and re-verify.

**Step 3.** Verify Native Image inside JDK B itself:

~~~bash
/opt/jdks/graalvm-jdk-21/bin/native-image --version
~~~

If this command fails, check how Native Image is packaged in your GraalVM distribution before attempting a native build.

**Step 4.** Once the OS C/C++ tools are ready:

~~~bash
./gradlew nativeCompile --info
~~~

Observe the Native Image executable path in the log. If it differs from JDK B, do not rush to change `JAVA_HOME`; first inspect the plugin/toolchain configuration and discovery mechanism.

**Step 5.** Run the generated native executable and perform a smoke test. Then compare the native build against `java -jar` with the same functionality, conditions, and workload if you want to evaluate startup time/memory.

### Three Scenarios to Reason Through

**Scenario 1:** `./gradlew --version` reports Temurin 21, `./gradlew javaToolchains` shows both Temurin 21 and GraalVM 21, and `vendor = JvmVendorSpec.GRAAL_VM` is configured. Must you switch the Gradle daemon to GraalVM?

**Answer:** Not necessarily. The daemon can run on another compatible JDK while the Java Toolchain selects GraalVM. You must confirm the native task uses the right GraalVM executable and that versions are compatible.

**Scenario 2:** Only `languageVersion = 21` is set on a machine with two Java 21 JDKs. The native build reports it cannot find `native-image`. Can you conclude all Gradle configuration is wrong?

**Answer:** Not enough evidence. You must check which vendor the Java Toolchain selected and where the native plugin looks for Native Image. Adding a vendor constraint and checking tool paths may resolve the wrong-JDK selection.

**Scenario 3:** `bootBuildImage` builds a native container successfully, yet the `native-image` command does not exist on your laptop. Is something wrong?

**Answer:** Not necessarily. Buildpacks can use Native Image inside the builder image. That is a different build environment from running `nativeCompile` directly on the host.

## 13. Checklist Before Concluding the Toolchain Is Correct

- [ ] Know the Java version required by the Spring Boot project.
- [ ] Pin and use the project's Gradle Wrapper.
- [ ] Verify the JVM running Gradle via `./gradlew --version`.
- [ ] Java Toolchain declares the right `languageVersion`; `vendor` matches native requirements.
- [ ] `./gradlew javaToolchains` lists the expected GraalVM JDK and path.
- [ ] The selected GraalVM JDK has a working `native-image`.
- [ ] The GraalVM Native Build Tools plugin is applied to the right project/subproject.
- [ ] The `nativeCompile --info` log confirms the plugin invokes the right Native Image executable.
- [ ] Native compiler/linker and OS libraries are complete.
- [ ] Smoke tests pass on the native executable; reflection/resources are tested separately.
- [ ] If using buildpacks, verify the toolchain **inside the builder image**, without confusing it with the host JDK.

**Remember:** **Gradle JVM** runs the build tool; **Gradle Java Toolchain** selects the JDK for Java tasks; **GraalVM Native Image** compiles bytecode into a native executable. Declare version/vendor explicitly, inspect the toolchain list, and verify the Native Image path in logs. That is how you prevent wrong-JDK errors when building and running Spring Boot Native Image across local machines, CI, and containers.
