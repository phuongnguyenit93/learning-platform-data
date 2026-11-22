# Java Toolchains in Gradle

Gradle Java Toolchains let you explicitly declare the JDK that each part of a build requires. A project can be compiled with JDK 17, run tests with JDK 21, and still run the Gradle Daemon on JDK 24. This configuration ensures every developer machine and CI environment selects the same compiler/runtime required by the project, reducing errors caused by different Java installations across machines.

A toolchain is the set of JVM tools a task needs: the Java compiler `javac`, the Java launcher `java`, or the Javadoc tool. With the Java plugin, Gradle can apply a toolchain to compile, test, and Javadoc tasks. You can also select a separate toolchain per task or define custom tasks that use a specific JDK.

## 1. Why Java Toolchains Are Needed

Without a toolchain, Gradle typically uses the environment's default JDK to compile and run code. Developer A's machine has JDK 17, Developer B has JDK 21, and CI has JDK 24; the same build command can produce different behavior or fail when newer APIs or language features are used.

For example, a project might want to:

- Compile code with Java 17.
- Only use APIs available in Java 11 or earlier so the artifact runs on Java 11.
- Run an additional test suite on Java 21.
- Generate Javadoc with JDK 17.
- Run the Gradle Daemon on JDK 24.

If you only change `JAVA_HOME`, every Java tool launched from the environment can be affected. Toolchains let you declare requirements directly in the build script, while Gradle selects the right compiler/launcher for each corresponding task.

### 1.1. Three JVMs/JDKs to Distinguish

A Gradle build can involve three separate Java roles:

| Role | Responsibility | Common Selection Method |
|---|---|---|
| Gradle Client JVM | Runs the `gradle` or `gradlew` script and sends build requests to the Daemon | `JAVA_HOME`, `PATH`, or IDE |
| Gradle Daemon JVM | Runs the Gradle build engine, configures the project, and executes tasks | Default `JAVA_HOME`, `org.gradle.java.home`, or Daemon JVM criteria |
| Project Toolchain | Provides `javac`, `java`, and `javadoc` for project tasks | `java.toolchain` or per-task configuration |

The toolchain in `build.gradle` does not automatically change the JVM running the Gradle Daemon. Conversely, choosing a JDK for the Daemon does not guarantee the project's compiler uses that same JDK.

For example: the terminal launches Gradle with JDK 24; the Gradle Daemon runs on JDK 24; `compileJava` uses the JDK 17 compiler; the `run` task uses Java 17; the `runOn21` task uses Java 21. This is a valid configuration as long as the Gradle version supports running on JDK 24 and the requested JDKs are available or can be provisioned.

## 2. Configuring Toolchains at the Project Level

With the Java plugin and Kotlin DSL, the minimal configuration in `build.gradle.kts` is:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

With Groovy DSL in `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

When the build runs, Gradle searches for a JDK matching Java 17. If found, toolchain-aware Java plugin tasks will use that tool. If not found, Gradle only downloads a JDK automatically when an appropriate download repository/resolver has been configured in the build.

### 2.1. Which Tasks Use the Toolchain?

With the Java plugin, the toolchain supplies tools to the following tasks:

| Task | Tool | Role |
|---|---|---|
| `compileJava` | `JavaCompiler` | Compiles main source into bytecode |
| `compileTestJava` | `JavaCompiler` | Compiles test source |
| `test` | `JavaLauncher` | Launches the test JVM |
| `run` (Application plugin) | `JavaLauncher` | Launches the application |
| `javadoc` | `JavadocTool` | Generates API documentation |

Gradle also uses the toolchain for other JVM tasks supported by built-in plugins. A custom task does not automatically use the toolchain just because the project declares `java.toolchain`; that task must receive `JavaCompiler`, `JavaLauncher`, `JavadocTool`, or the corresponding executable path.

### 2.2. Selecting by Java Version, Vendor, and Implementation

The basic configuration only requires a major language version:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

If your organization requires a specific JDK distribution, add a vendor:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
~~~

Some commonly used vendors:

| JvmVendorSpec | Distribution/Vendor |
|---|---|
| `ADOPTIUM` | Eclipse Temurin |
| `AMAZON` | Amazon Corretto |
| `AZUL` | Azul Zulu |
| `MICROSOFT` | Microsoft Build of OpenJDK |
| `ORACLE` | Oracle JDK |
| `IBM` | IBM Semeru |

If a vendor is not in the standard list, you can use `JvmVendorSpec.matching("...")` to match the `java.vendor` string.

You can also restrict the JVM implementation. For example, selecting only OpenJ9/J9:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.IBM)
        implementation.set(JvmImplementation.J9)
    }
}
~~~

Gradle also provides the `nativeImageCapable` property when you need a JDK with GraalVM Native Image support:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
        nativeImageCapable.set(true)
    }
}
~~~

Important rule: if you specify a vendor or implementation, you must also specify `languageVersion`. An empty `JavaToolchainSpec` means using the current build's toolchain; a spec with a vendor or implementation but no language version is invalid.

### 2.3. Major Version vs. Patch Version Selection

`languageVersion` selects the Java major version, such as 17. It is not a way to pin an exact patch release like 17.0.15. When multiple installed JDKs satisfy the criteria, Gradle applies a priority order to pick one.

If your build depends on vendor- or implementation-specific behavior, declare those criteria explicitly. If you need strict patch-level control, manage the images/toolchains in CI or provisioning infrastructure according to your organization's policy; do not assume `JavaLanguageVersion.of(17)` guarantees a specific patch version.

## 3. Toolchain and `--release`: Two Different Purposes

A toolchain selects the actual JDK used to compile or run a task. The compiler option `--release` restricts the language level, bytecode target, and Java API surface that the code is allowed to reference.

For example, using JDK 17 while only allowing Java 11-compatible code:

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
~~~

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
~~~

The compiler runs from JDK 17, but `--release 11` prevents source code from using APIs introduced in Java 12 or later and emits Java 11-compatible class files. This is useful when CI standardizes on a newer compiler while the product still supports an older runtime.

### 3.1. Comparing Ways to Set the Java Version

| Configuration | Selects actual JDK? | Restricts APIs by release? | Scope |
|---|---|---|---|
| Java Toolchains | Yes | Not automatically | Project/task |
| `options.release` | No | Yes | `JavaCompile` task |
| `sourceCompatibility` + `targetCompatibility` | No | Not as completely as release | `JavaCompile`/project |
| `JAVA_HOME` | Selects environment default | No | Environment/process |
| IDE Gradle JVM | Selects JVM running the build in IDE | No | IDE |

`sourceCompatibility` controls the Java syntax level the compiler accepts; `targetCompatibility` controls the bytecode version generated. Neither property selects the compiler JDK nor guarantees that code does not call newer APIs present in the active JDK.

With Java 9 and later compilers, `--release` is usually the stricter choice for cross-compilation. Do not set `options.release` higher than what the compiler JDK supports. Toolchain and `--release` can be combined to pin both the compiler and the target platform.

### 3.2. Do Not Confuse Bytecode Version with Runtime Version

Class files have their own major version. Common milestones include:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

You can inspect a class file with:

~~~bash
javap -verbose build/classes/java/main/demo/ToolchainProbe.class
~~~

Look for the `major version` line. If built with JDK 17 and `--release 11`, the class file must have major version 55. Running the compiler on Java 17 does not mean the output has to be Java 17 bytecode.

## 4. Selecting a Separate Toolchain per Task

A project can use a default JDK and override specific tasks. Gradle provides the `javaToolchains` extension with three main providers:

- `compilerFor` returns a `JavaCompiler`.
- `launcherFor` returns a `JavaLauncher`.
- `javadocToolFor` returns a `JavadocTool`.

### 4.1. Compile with Java 17, Run Tests with Java 21

Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    javaCompiler.set(javaToolchains.compilerFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
}
~~~

Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

When running `test`, Gradle launches the test JVM with Java 21. Compilation of main and test sources still uses Java 17. If the project needs testing across multiple runtimes, register separate `Test` tasks such as `testOn17` and `testOn21` and wire them into `check` as needed by your team.

### 4.2. Running an Application with a Different JDK

With the Application plugin:

~~~kotlin
tasks.register<JavaExec>("runOn21") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("demo.ToolchainProbe")
}
~~~

The `runOn21` task runs the application's classpath using Java 21, even when the default project toolchain is Java 17.

### 4.3. Selecting the Javadoc Tool

If Javadoc needs to be generated by a specific JDK version:

~~~kotlin
tasks.withType<Javadoc>().configureEach {
    javadocTool.set(javaToolchains.javadocToolFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

### 4.4. Using Toolchains in Custom Tasks

A custom task that needs a Java executable should accept the provider lazily:

~~~kotlin
val java21 = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(21))
}

tasks.register<JavaExec>("inspectWith21") {
    javaLauncher.set(java21)
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("demo.ToolchainProbe")
}
~~~

Keep the provider rather than calling `get()` eagerly during configuration. Gradle can then resolve or provision the JDK only when the task actually needs to run. Resolving a toolchain too early can cause the build to download a JDK even when that task is never executed.

## 5. Gradle Auto-Detection of Installed JDKs

Gradle automatically scans for local JDKs/JREs by default. Commonly recognized sources include:

- Standard installation locations on Windows, Linux, and macOS.
- The `JAVA_HOME` environment variable.
- Package managers such as SDKMAN!, asdf-vm, and Jabba.
- Maven toolchains specifications.
- JDKs installed alongside IntelliJ IDEA.

Gradle prefers a JDK when both a JDK and a JRE satisfy the criteria, because compile tasks require the `javac` compiler.

### 5.1. Listing Toolchains Detected by Gradle

Run:

~~~bash
./gradlew -q javaToolchains
~~~

On Windows:

~~~powershell
.\gradlew.bat -q javaToolchains
~~~

The `javaToolchains` task displays:

- Whether auto-detection is enabled.
- Whether auto-download is enabled.
- Language version.
- Vendor.
- Architecture.
- Whether it is a JDK or JRE.
- The source from which Gradle detected it.

This is the first command to run when Gradle reports that no matching JDK can be found.

### 5.2. Adding Custom JDK Paths

If a JDK is outside Gradle's auto-detection locations, add its path in `gradle.properties`:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

That example is for Linux. On Windows, use the actual paths of the installed JDKs:

~~~properties
org.gradle.java.installations.paths=C:/Java/jdk-17,C:/Java/jdk-21
~~~

Gradle can combine custom paths with default auto-detection. Configuring paths does not install JDKs automatically; the directories must exist and contain the required executables.

### 5.3. Disabling Auto-Detection

In `gradle.properties`:

~~~properties
org.gradle.java.installations.auto-detect=false
~~~

Or pass a system property when invoking Gradle:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-detect=false build
~~~

Only disable auto-detection when the build environment explicitly manages all toolchain paths. Otherwise, the build may fail to find a JDK even though one is installed on the machine.

## 6. Auto-Provisioning: Gradle Automatic JDK Downloads

Toolchain auto-provisioning allows Gradle to download a matching JDK when no local installation is found. Downloaded JDKs are stored in the Gradle User Home, typically under the `jdks` directory, and can be reused across subsequent builds.

There are two distinct steps:

1. The build declares a JDK requirement, such as Java 17.
2. A toolchain resolver plugin provides a repository for Gradle to look up and download the corresponding JDK.

Gradle does not know where to download JDKs on its own unless the build configures a resolver.

### 6.1. Using the Foojay Toolchain Resolver

A popular option is the Foojay Toolchains Resolver. Example in `settings.gradle.kts`:

~~~kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention").version("1.0.0")
}
~~~

Once the resolver is declared, the project can request a toolchain as usual:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

If no matching JDK 17 is available locally, Gradle can query the resolver and download an appropriate GA JDK. Plugin version `1.0.0` is used in the current Gradle User Manual; verify the plugin version, security policies, and organization-approved distribution sources before upgrading.

### 6.2. Limitations of Auto-Provisioning

- Gradle only auto-downloads Java GA releases; early-access releases are not auto-provisioned by this mechanism.
- Downloaded JDKs are not automatically updated when new patches are released.
- Auto-provisioning only runs when auto-detection finds no matching toolchain.
- The resolver requires network/repository access; proxies, TLS inspection, or firewalls can cause downloads to fail.
- Downloaded JDKs are shared in Gradle User Home across subsequent builds.

Do not let CI silently download from unapproved sources. Pin the resolver plugin, manage caches, restrict vendors when necessary, and use an internal mirror/repository if required by your organization.

### 6.3. Disabling Auto-Download

In `gradle.properties`:

~~~properties
org.gradle.java.installations.auto-download=false
~~~

Or:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-download=false build
~~~

When auto-download is disabled, all required toolchains must be available locally or via custom paths. After changing toolchain configuration, you can stop the daemon so Gradle refreshes cached metadata:

~~~bash
./gradlew --stop
~~~

## 7. How Gradle Orders and Selects Toolchains

When multiple JDKs match, Gradle sorts the installations by priority rules and selects the first one. Key factors include:

1. The JDK currently running Gradle is preferred in certain cases.
2. JDKs are preferred over JREs.
3. Vendors follow a preference order recognized by Gradle.
4. Newer matching versions are preferred.
5. Installation path acts as the final tie-breaker for deterministic selection when other criteria are equal.

Therefore, declaring only `languageVersion = 17` does not guarantee the same vendor is chosen on every machine. If you need a specific vendor, declare `vendor`; if you need a specific implementation, declare `implementation`.

Gradle tracks the major version and any declared vendor/implementation properties as inputs to compile and test tasks. This helps the build cache and up-to-date checks distinguish between different toolchains. If your build depends on a specific patch or vendor without declaring those criteria, manage the CI environment more tightly and avoid assuming all JDKs of the same major version behave identically.

## 8. Project Toolchain vs. Gradle Daemon JVM

This is the most common source of confusion when configuring builds.

### 8.1. `JAVA_HOME` and `org.gradle.java.home`

`JAVA_HOME` typically determines the Java executable used to launch the Gradle Client and serves as the default for the Gradle Daemon if no other configuration is present.

You can set a dedicated JVM for the daemon using `org.gradle.java.home` in `gradle.properties`:

~~~properties
org.gradle.java.home=/opt/jdks/jdk-21
~~~

On Windows:

~~~properties
org.gradle.java.home=C:/Java/jdk-21
~~~

This setting affects the JVM running the Gradle Daemon. It does not replace `java.toolchain` in the build script.

### 8.2. Daemon JVM Criteria

Gradle versions that support Daemon JVM criteria allow storing the Gradle Daemon's JVM requirements in the repository. For example:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17
~~~

You can also specify a vendor:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17 --jvm-vendor=adoptium
~~~

This task creates or updates:

~~~text
gradle/gradle-daemon-jvm.properties
~~~

This file describes the JDK that the Gradle Daemon should use. When criteria are present, they take precedence over `JAVA_HOME` and `org.gradle.java.home`. Provisioning URL generation requires a configured toolchain download repository. You can commit this file to standardize the daemon JVM across machines.

Daemon JVM criteria remain distinct from the project toolchain: one runs the build engine, while the other provides the compiler and launcher for project code.

### 8.3. Gradle Wrapper Selects the Gradle Version, Not the Project JDK

The Wrapper stores the Gradle version in:

~~~text
gradle/wrapper/gradle-wrapper.properties
~~~

For example, generating the wrapper for a specific Gradle version:

~~~bash
gradle wrapper --gradle-version 9.2.1
~~~

The team then uses `./gradlew` or `gradlew.bat` to run the same Gradle distribution. The Wrapper standardizes the build tool version; the JDK running Gradle is still chosen by the environment or daemon criteria, while the JDK compiling and running the application is chosen by the toolchain.

## 9. Compatibility Between Gradle and Java

You need to check two separate questions:

1. Which JDKs are supported to run Gradle/the Daemon itself?
2. Which JDKs are supported as a toolchain for compiling or testing?

A Java release may be supported as a toolchain before it is supported as the JVM running Gradle. For example, Gradle's compatibility matrix notes Java 17 toolchain and runtime support starting from Gradle 7.3; Java 21 toolchain from Gradle 8.4 and running Gradle from 8.5; Java 24 toolchain and runtime from Gradle 8.14. The matrix changes with each Gradle release, so always check the exact version your project uses.

Gradle 9.x requires a more modern JVM than older branches; you cannot take a new JDK and assume every Gradle version will launch on it. If a build reports an unsupported class file version or unsupported JVM, check:

- Gradle Wrapper version.
- Java version launching the Gradle Client.
- JVM of the Gradle Daemon.
- Java toolchain requested by the task.
- Official Gradle Compatibility Matrix.

Do not upgrade Gradle solely to change a toolchain if other plugins in the build do not yet support the newer Gradle version. Check the Gradle version, Java version, and Android/Kotlin/Scala/Groovy plugin compatibility together.

## 10. Toolchains in Multi-Project Builds and Other JVM Language Plugins

In multi-project builds, use a shared convention so all subprojects have consistent Java requirements. You can place the configuration in a convention plugin or apply it to each subproject using the Java plugin.

Example shared configuration in a Kotlin DSL convention plugin:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Subprojects applying this convention plugin will all use Java 17 unless a task or subproject explicitly overrides it.

Gradle supports toolchains for the Java plugin. The Groovy plugin supports compile toolchains, though Groovydoc has limitations according to the Gradle User Manual. The Scala plugin supports compilation and Scaladoc. The Kotlin Gradle plugin has its own toolchain API, typically configured with `kotlin { jvmToolchain(17) }`; check the documentation and version of the Kotlin Gradle plugin you are using.

Do not assume a single Java toolchain declaration automatically configures every third-party compiler. Plugins may need to receive a toolchain provider or separate configuration for their own compilers and tasks.

## 11. Java 17+ Practice: Build with JDK 17, Run with JDK 21

This example demonstrates three things:

- The Gradle Daemon can run on a different JDK than the project toolchain.
- Compilation uses JDK 17 while `--release 11` produces Java 11 bytecode.
- The `runOn21` task uses JDK 21 while the default `run` task uses JDK 17.

Create the structure:

~~~text
toolchain-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── ToolchainProbe.java
~~~

### 11.1. `settings.gradle.kts`

~~~kotlin
rootProject.name = "toolchain-demo"
~~~

### 11.2. `build.gradle.kts`

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.ToolchainProbe")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}

tasks.register<JavaExec>("runOn21") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("demo.ToolchainProbe")
}

tasks.register("showToolchain") {
    doLast {
        val compiler = javaToolchains.compilerFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }.get()
        println("COMPILER_FEATURE=" + compiler.metadata.languageVersion.asInt())
    }
}
~~~

### 11.3. `ToolchainProbe.java`

~~~java
package demo;

public final class ToolchainProbe {
    public static void main(String[] args) {
        System.out.println(
            "RUNTIME_FEATURE=" + Runtime.version().feature()
        );
    }
}
~~~

### 11.4. Build and Verify

Ensure both JDK 17 and JDK 21 are installed. Verify that Gradle detects them:

~~~bash
./gradlew -q javaToolchains
~~~

Run the build, the application with the default toolchain, and the custom task with Java 21:

~~~bash
./gradlew --no-daemon --console=plain clean build run runOn21 showToolchain
~~~

Key output:

~~~text
> Task :run
RUNTIME_FEATURE=17

> Task :runOn21
RUNTIME_FEATURE=21

> Task :showToolchain
COMPILER_FEATURE=17

BUILD SUCCESSFUL
~~~

The line `COMPILER_FEATURE=17` confirms the provider selected the Java 17 compiler. The `run` task uses Java 17 per the project toolchain; `runOn21` uses the dedicated Java 21 launcher.

Inspect the bytecode produced by `--release 11`:

~~~bash
javap -verbose build/classes/java/main/demo/ToolchainProbe.class
~~~

Look for:

~~~text
major version: 55
~~~

Major version 55 confirms the class file is Java 11-compatible. This example was compiled and run successfully with Gradle 9.2.1; the Gradle Daemon ran on JDK 24.0.2, the compiler toolchain was Amazon Corretto 17, and the custom task ran on Microsoft JDK 21. Actual JDK versions and vendors detected by Gradle depend on the host machine.

## 12. Using Toolchains in CI/CD

A reliable pipeline should make each Java layer explicit:

1. Use the Gradle Wrapper to pin the Gradle version.
2. Choose the JVM running Gradle/the Daemon according to the compatibility matrix and policy.
3. Declare the project toolchain in the build script.
4. Use an approved resolver or pre-install the required JDKs on the runner.
5. Cache Gradle User Home if provisioned JDKs need to be reused.
6. Run `javaToolchains` as a diagnostic step when a runner cannot find a JDK.
7. Run builds and tests against the same toolchain spec across developer machines and CI.
8. If multiple runtimes must be verified, create separate test tasks per Java version.
9. Save `--info` output and Gradle daemon logs when investigating failures.

Example workflow on Linux:

~~~bash
./gradlew -q javaToolchains
./gradlew clean check
~~~

If the runner does not have internet access, pre-install the JDKs into the image or mount them into configured toolchain paths. Do not rely on downloading JDKs on every build in CI environments with restricted network policies.

## 13. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No matching toolchains found | No JDK matches language version/vendor/implementation | Run `javaToolchains`; install the JDK or configure a resolver |
| Gradle does not detect an installed JDK | Path is outside auto-detection locations or auto-detect is disabled | Add `org.gradle.java.installations.paths` and verify `bin/java`/`bin/javac` |
| Gradle fails to start on a newer Java | Gradle version does not support that JVM yet | Check the Gradle Wrapper and compatibility matrix |
| Compile uses an unexpected JDK | Task does not use the project toolchain or custom task lacks provider wiring | Check `JavaCompile.javaCompiler` and task-specific configuration |
| Tests run on a different Java than compilation | `Test.javaLauncher` is overridden or IDE configuration differs | Check the `Test` task and the IDE's Gradle JVM |
| Auto-download fails and build breaks | No resolver configured, network/proxy/TLS issue, or no matching GA release | Check settings plugins, repositories, proxy, and download logs |
| Gradle selects an unintended vendor | Only major version is declared and multiple matching JDKs exist | Declare `vendor` or `implementation` |
| Toolchain changed but Gradle keeps old selection | Daemon still holds cached metadata/configuration | Run `./gradlew --stop` and rebuild |
| `--release` does not change the runtime when running the app | Release only restricts compilation/bytecode/APIs | Configure `Test.javaLauncher` or `JavaExec.javaLauncher` |
| Installed Java is a JRE so compilation fails | Missing `javac` compiler | Install a JDK, not just a JRE |
| IDE and terminal pick different JDKs | IDE Gradle JVM differs from `JAVA_HOME` or toolchain | Configure the IDE Gradle JVM and verify the build toolchain |
| Alpine/musl misdetects multiple toolchains | JVM detection limitations in musl environments | Pin a single toolchain or use a tested glibc environment |

### 13.1. Inspecting Detailed Diagnostics on Failure

List toolchains:

~~~bash
./gradlew -q javaToolchains
~~~

View detailed logs when Gradle resolves tasks:

~~~bash
./gradlew --info compileJava
~~~

Check the Gradle runtime:

~~~bash
./gradlew --version
~~~

Check the shell's default Java:

~~~bash
java --version
echo "$JAVA_HOME"
~~~

Stop the Daemon if you recently changed paths or toolchains:

~~~bash
./gradlew --stop
~~~

In PowerShell, inspect environment variables:

~~~powershell
java --version
$env:JAVA_HOME
~~~

Do not wipe the entire Gradle cache just because a toolchain is not found. First check paths, version, vendor, auto-detection, resolver, and the daemon.

## 14. Reproducibility and Security Notes

Toolchains make builds more consistent, but they do not lock down the entire environment on their own. Results also depend on:

- Gradle Wrapper version.
- JVM running the Gradle Daemon.
- Selected JDK major version, vendor, and implementation.
- Dependency and plugin versions.
- OS, architecture, locale, and environment variables.
- Compiler flags, annotation processors, and native tools.

When using auto-provisioning, JDKs are downloaded from the resolver repository. Only configure trusted resolvers, pin plugin versions, and follow your organization's vendor/license policies. Do not hardcode repository credentials in build scripts; use Gradle credentials or secret stores per CI policy.

Provisioned toolchains reside in Gradle User Home and can be shared across other builds on the machine. Manage file permissions, cache size, and JDK update/removal policies on runners accordingly.

## 15. Pre-Completion Checklist for Build Integration

- [ ] Gradle Wrapper version is pinned.
- [ ] JVM running the Gradle Daemon is supported by the Gradle version.
- [ ] Client JVM, Daemon JVM, and project toolchain are clearly distinguished.
- [ ] `java.toolchain.languageVersion` is declared.
- [ ] Vendor/implementation is specified if required by the build.
- [ ] `javaToolchains` has been checked to see which JDK Gradle selects.
- [ ] Compile, Test, JavaExec, and Javadoc tasks use the intended toolchains.
- [ ] `options.release` is configured if target APIs/bytecode must be restricted.
- [ ] Resolver plugin and download repositories are approved if using auto-provisioning.
- [ ] CI has local JDKs or appropriate download permissions.
- [ ] Gradle compatibility matrix has been verified for both Java runtime and toolchain.
- [ ] Build has been tested in both IDE and terminal.
- [ ] Daemon has been stopped after significant toolchain configuration changes.
- [ ] Toolchain/JDK details are recorded in build logs for troubleshooting.

## 16. Key Takeaways

Java Toolchains for Gradle provide a declarative way to specify the JDK needed by a project and its individual tasks. Use `java.toolchain.languageVersion` to standardize compile/test/Javadoc tasks, and use `javaToolchains.compilerFor` or `launcherFor` when a specific task needs a different JDK.

Combine toolchains with `options.release` to control both the selected compiler and the target API/bytecode level. Use `javaToolchains` to inspect detected JDKs, the Foojay resolver when auto-provisioning is needed, and Daemon JVM criteria to standardize the JVM running Gradle. Always verify the compatibility matrix for your exact Gradle release, especially when upgrading JDKs or plugins.

References:

- [Toolchains for JVM projects — Gradle User Manual](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle Daemon and Daemon JVM criteria](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Foojay Toolchains Resolver Plugin](https://github.com/gradle/foojay-toolchains)