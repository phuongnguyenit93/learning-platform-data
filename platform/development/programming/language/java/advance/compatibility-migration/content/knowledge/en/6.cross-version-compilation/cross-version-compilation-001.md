# Distinguishing the build-tool JDK, compiler JDK, and application runtime JDK

## 1. Why distinguish the three Java environments?

When a project declares “uses Java 21”, that information is not enough to know which JDK every step of building and running the application uses. One project might launch Gradle or Maven with JDK 17, use JDK 21 as the compiler toolchain, emit Java 17-compatible bytecode, run tests on Java 17, and deploy the artifact on a separate Java 17 runtime. Another project might use JDK 21 across all three stages. These two configurations have different goals and compatibility boundaries.

In a Java workflow, at least three roles must be distinguished:

1. **JDK running the build tool (build JVM):** the JVM launching Gradle, Maven, and plugins executing inside the build process. It determines whether the build tool and plugins can start and execute.
2. **JDK used to compile (compiler JDK/toolchain):** the JDK providing `javac` and compiler tools needed to turn source code into bytecode. Together with release/source/target configuration, it determines syntax, Java SE APIs, and the class file format emitted by the compiler.
3. **JDK/JVM running the application (application runtime):** the JVM that actually loads and executes the artifact in test, staging, or production. It must understand the bytecode, provide required APIs, and satisfy runtime requirements of dependencies.

These three roles may use the same version, yet do not have to be identical. Choosing a version for each role must be based on requirements of the build tool, compiler, dependencies, deployment environment, and the lowest Java level the product commits to supporting.

Distinguishing them accurately helps avoid common false conclusions:

- “The machine has JDK 21 installed” does not prove Gradle/Maven is running on JDK 21.
- “The build runs on JDK 21” does not prove the compiler also uses JDK 21; the build tool may select a separate toolchain.
- “Compiled successfully with JDK 21” does not prove the artifact runs on Java 17.
- “Unit tests pass on a developer machine” does not prove the test JVM and production runtime in CI/containers are identical.
- “Setting target 17” does not make third-party dependencies automatically compatible with Java 17.

## 2. Three roles and responsibilities of each JDK

### 2.1. JDK running the build tool

Gradle and Maven are Java programs. When invoking `./gradlew`, `gradlew.bat`, `mvn`, or Maven Wrapper, a JVM must launch to execute the build tool. This JVM is typically selected from `JAVA_HOME`, `PATH`, or IDE/CI agent configurations.

The build JVM performs tasks such as:

- Loading and running Gradle/Maven core, daemon, and lifecycle.
- Loading build scripts, plugins, extensions, and build tasks written in Java/Groovy/Kotlin.
- Executing plugins for code generation, dependency verification, packaging, and artifact creation.
- Orchestrating compilers, test runners, code generators, and child processes.
- Accessing the filesystem, repositories, certificates, network, and CI environment according to build configuration.

Because plugins typically run inside the same build process or interact closely with build-tool APIs, plugins also have JVM and Gradle/Maven version requirements. A newer compiler toolchain cannot help the build start if Gradle itself or a plugin already fails on the build JVM.

For example, a developer machine has JDK 21 installed, yet the terminal uses `JAVA_HOME` pointing to JDK 17. `./gradlew` may start Gradle on Java 17. If the current Gradle version requires a newer JVM, the error occurs before the project is configured and before compile tasks select a compiler toolchain.

### 2.2. JDK used for compiling

The compiler JDK provides `javac`, compiler libraries, and related tools. In Gradle, Java Toolchains can select the JDK for `JavaCompile`. In Maven, Maven Toolchains and toolchain-aware plugins can select a JDK different from the JVM running Maven.

The compiler JDK affects:

- The compiler implementation and ability to understand language features.
- Compiler APIs used by annotation processors or compiler plugins.
- Tools running during compilation, such as annotation processors, code generators, and compile-time bytecode instrumentation.
- Support for using `--release`, `--source`, and `--target` to define the artifact's Java contract.

Distinguish the **compiler's JDK version** from the **artifact's release target**. JDK 21 can compile source code targeting release 17 using `--release 17`. In that case, the compiler runs on JDK 21 while class files are generated in Java 17 format and the compiler restricts Java SE API usage to Java 17.

Conversely, using only `-source 17 -target 17` does not provide the same API control as `--release 17`. Source code can accidentally reference a Java SE API present only in JDK 21, producing target 17 bytecode that fails to run on JVM 17.

### 2.3. JDK/JVM running the application

The application runtime is the JVM that actually loads and runs the artifact. The runtime may be a full JDK, a JRE distribution, a custom runtime image built with `jlink`, or a container-provided runtime environment. What matters is that the JVM and required modules/APIs satisfy application requirements.

The runtime needs to:

- Support the class-file version of all classes in the application and dependencies.
- Provide the Java SE APIs used by source code and libraries.
- Have required modules, providers, native libraries, certificates, and configurations.
- Be compatible with frameworks, drivers, agents, instrumentation, and native libraries.
- Meet operational requirements for TLS, charsets, timezones, memory, GC, CPU, and operating system.

The unit test runtime may differ from the production runtime. A project can compile with JDK 21, run unit tests on Java 17 to verify minimum compatibility, and then run additional integration tests on Java 21. If a product supports only Java 21, primary tests must run on a Java 21 runtime matching production.

## 3. Relationship between JDK, Java release, and bytecode

To understand why the three JDKs can differ, separate three concepts that are often conflated:

| Concept | Meaning | Example |
| --- | --- | --- |
| Compiler JDK | The JDK supplying the compiler performing compilation | JDK 21 |
| Java release/language level | Language level and Java SE APIs allowed during compilation | `--release 17` |
| Class-file target | Generated bytecode format | Major version 61 for Java 17 |

Some common class-file major versions:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Example: compiler JDK 21 produces class file major version 61. A Java 17 JVM can load this format. If the compiler emits class file major version 65, a Java 17 JVM cannot load it and typically throws `UnsupportedClassVersionError`.

However, matching class-file version alone is not enough to guarantee runtime compatibility. A class may carry major version 61 yet call an API existing only on Java 21, or depend on a third-party library compiled solely for Java 21. Therefore, both Java SE APIs and the dependency graph must be controlled.

### 3.1. Meaning of `--release`

The `--release` option of `javac` sets the language level, class-file target, and Java SE API set corresponding to the chosen release simultaneously. When using JDK 21 to build an artifact running on Java 17, compiler config should use release 17.

Example:

```bash
javac --release 17 -d build/classes src/main/java/com/example/Main.java
```

The command uses `javac` from whichever JDK is invoked, yet compiles under the Java 17 contract. You can verify the class file via:

```bash
javap -verbose build/classes/com/example/Main.class
```

Look for the `major version: 61` line to confirm a Java 17 class file. If using `--release 21`, the major version corresponds to Java 21.

`--release` controls only Java SE source checked by the compiler. It does not downgrade dependency bytecode, does not confirm a framework supports Java 17, does not restrict internal APIs accessed by libraries via reflection, and does not guarantee identical runtime behavior.

### 3.2. When to compile with a newer JDK while targeting an older release?

This pattern is useful during transition phases when an organization wants to standardize on a newer build environment yet must still support consumers running on older JVMs. For example:

- CI has moved to JDK 21 because build tools/plugins require it or to use the newer compiler.
- The artifact must still run on Java 17 while support contracts remain active.
- The team wants early source checking on the JDK 21 compiler before upgrading production runtimes.
- Target libraries and frameworks still have versions supporting Java 17.

Do not keep an old target purely out of habit. If the target framework or dependencies already require Java 21, compiling with target 17 will not produce a truly Java 17-compatible product.

## 4. Examples with Gradle Java Toolchains

Gradle Java Toolchains let you specify the JDK used for Java tasks without forcing the JVM running Gradle to have the same version. This is a clean way to separate the build JVM from the compiler/test JVM.

### 4.1. Building with JDK 21, producing a Java 17 artifact

Example `build.gradle` using Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

In this configuration:

- The Gradle daemon still runs on the JVM chosen when launching Gradle.
- `JavaCompile` uses the JDK 21 compiler selected by the toolchain.
- The compiler generates class files for Java 17 and restricts Java SE APIs to release 17.
- Unless configured separately, tasks such as test typically use a launcher matching the Java plugin's default toolchain.

Therefore, to test a Java 17 runtime explicitly, a separate test launcher can be configured.

### 4.2. Selecting a separate JVM to run tests

Example compiling with JDK 21, targeting Java 17, and running tests on JDK 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

This pattern verifies the artifact on the lowest committed runtime. If the application must run Java 21 in production, there should also be a test task using Java 21 to verify behavior on the actual deployment runtime. Separate test tasks can be created or tasks configured via a CI matrix.

### 4.3. Selecting a launcher for JavaExec and locally run apps

Tasks that run applications or Java tools may need a separate launcher. Example with `JavaExec` tasks:

```groovy
tasks.withType(JavaExec).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Plugins such as Spring Boot may provide their own run tasks based on `JavaExec` or similar mechanisms. Check task types and how plugins support toolchains in the version in use; do not assume every third-party task automatically uses the same launcher.

### 4.4. Identifying which JVM Gradle is using

Useful commands:

```bash
java -version
./gradlew --version
./gradlew -q javaToolchains
```

- `java -version` shows the Java invoked from `PATH` in the current terminal.
- `./gradlew --version` shows the JVM Gradle is running on during that command session, along with the Gradle version.
- `./gradlew -q javaToolchains` lists the toolchains Gradle detects.

If the IDE has its own Gradle JVM setting, results in the terminal and IDE can differ. Check the Gradle JVM setting in the IDE and the JVM used by CI.

## 5. Examples with Maven Toolchains

Maven also runs inside a JVM. That JVM is chosen when the Maven Wrapper or `mvn` command starts. Maven Toolchains enable certain plugins to use a JDK different from the JVM running Maven.

### 5.1. Declaring installed JDKs in `toolchains.xml`

A `~/.m2/toolchains.xml` file can declare JDKs available on the machine:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>any</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-21</jdkHome>
        </configuration>
    </toolchain>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>any</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Paths in the example must be replaced with actual JDK locations on the machine or agent. Do not check a developer's local path into the repository if other CI/developer machines do not share that layout. Standardize JDK installations or supply matching configurations per environment.

### 5.2. Selecting a toolchain and configuring compiler release

Example configuring Maven Toolchains Plugin to pick JDK 21 while using Maven Compiler Plugin to emit a Java 17 artifact:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.2.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>toolchain</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <toolchains>
                    <jdk>
                        <version>21</version>
                        <vendor>any</vendor>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

This is an illustrative configuration example; plugin versions must be verified against the project's Maven and JDK versions. Maven Toolchains selects a JDK for plugins that support toolchains. The Maven process itself still runs on the JVM chosen when launching Maven.

### 5.3. Running tests on another JDK

Maven Surefire/Failsafe can use the selected toolchain when supported by the plugin version. Read the specific plugin documentation and check logs to confirm which JVM actually starts the forked test process. If no toolchain is configured for tests, tests may run on Maven's JVM or a default plugin-selected JVM.

To inspect the Maven JVM:

```bash
mvn -version
```

The output reports the Java version and Java home Maven is using. It does not itself prove whether the compiler/test plugin used that same JDK or a different toolchain.

## 6. Three-JDK matrix example

A project might be organized as follows while still needing to support Java 17:

| Stage | Version | How to confirm |
| --- | --- | --- |
| JVM running Gradle/Maven | JDK 21 | `./gradlew --version` or `mvn -version` |
| Compiler toolchain | JDK 21 | Gradle `javaToolchains`, Maven toolchain/plugin logs |
| Artifact Java release | 17 | `options.release = 17` or Maven Compiler `<release>17</release>` |
| Minimum unit test runtime | JDK 17 | Test launcher/toolchain and test process JVM logs |
| Integration test runtime | JDK 21 | Test container/agent configured with JDK 21 |
| Production runtime | JDK 17 during transition | Image/deployment config and runtime `java -version` |

This matrix is only an example. If the product target is Java 21, change Java release and production runtime to 21, then confirm all dependencies and environments support it. Do not change only one cell in the table while ignoring constraints in the remaining cells.

### 6.1. Minimum runtime and target runtime matrix

If a library is distributed to multiple applications, testing on both the lowest supported runtime and recommended runtime may be needed. For example, a library compiled with JDK 21 using `--release 17` can run on Java 17 and Java 21 if dependencies are compatible. CI should run tests on both JVMs to detect behavioral differences.

For an application deployed exclusively on Java 21, maintaining a Java 17 test matrix is unnecessary once the product has officially dropped Java 17 support. However, if any build plugins, tools, or libraries require Java 17, their specific requirements must still be checked.

## 7. Common errors when the three roles are not clearly configured

### 7.1. Build tool fails to start even though a new JDK is installed

The cause may be `JAVA_HOME`, `PATH`, the Gradle JVM in the IDE, or CI configuration still pointing to an old JDK. It may also be that the Gradle/Maven version or a plugin does not support the JVM in use.

Investigation steps:

1. Run `java -version` in the exact terminal/agent.
2. Run `./gradlew --version` or `mvn -version` to check the build tool's JVM.
3. Inspect the Gradle JVM in the IDE and JDK configuration of the CI runner.
4. Check build tool/plugin versions against the Java compatibility matrix.
5. Investigate compiler toolchains only after the build tool starts stably.

### 7.2. Build tool starts, yet compile tasks use an unwanted JDK

If no toolchain is declared, the compiler may be picked from the build environment or default config. Developer machines and CI can then use different compilers.

Declare toolchains explicitly, check compile task logs, and inspect the selected `javac`/JDK path. Do not use `java -version` output to infer the compiler toolchain.

### 7.3. Compilation succeeds, yet the application fails in production

Common causes:

- Compiler emitted bytecode newer than the production JVM.
- Artifact uses Java SE APIs absent in the old runtime.
- A transitive dependency was compiled with a higher Java version than the application's target.
- The runtime image lacks modules, certificates, or native libraries.
- Frameworks/drivers have unmet runtime-specific requirements.

Inspect `major version`, dependency graphs, runtime images, and the process's actual JVM. Running the packaged artifact inside the exact production image is necessary evidence; running classes from the IDE does not replace this step.

### 7.4. Unit tests pass, yet production still fails

Tests may be running on a newer JDK while production uses an older JDK, or tests use a different classpath configuration from the actual artifact. Some differences only emerge with TLS, charsets, timezones, native libraries, container memory, or external services.

Explicitly record test JVM and production JVM, run integration tests on matching images, and compare runtime configurations. If a product supports multiple JVMs, test at least each committed JVM.

### 7.5. Plugins or annotation processors incompatible with the compiler

Build plugins run on the build JVM, whereas annotation processors are usually loaded inside the compiler process and may depend on `javac` APIs. A plugin might run on JVM 17 while its processor fails when compiler JDK 21 changes APIs.

Separate build-tool startup logs, compiler logs, and processor logs. Pinpoint the exact failing component before upgrading the entire plugin/dependency graph.

## 8. Checking actual versions in each environment

Do not record only a single “Java version” value in project documentation. Gather details from each process.

| Component | How to check | What to record |
| --- | --- | --- |
| Terminal JDK | `java -version`, `where java` (Windows) or `which java` (Unix) | JDK invoked from PATH |
| Gradle JVM | `./gradlew --version` | JVM running Gradle |
| Gradle toolchain | `./gradlew -q javaToolchains` | JDKs detected and selectable by Gradle |
| Maven JVM | `mvn -version` | Maven's Java version and Java home |
| Compiler | Build logs, toolchain configuration, `javac -version` from selected JDK | JDK performing compilation |
| Test process | JVM logs, test launcher/toolchain config | JDK running unit/integration tests |
| Running application | `java -version` in container/host, process command line, startup logs | Service's actual JVM |
| Artifact | `javap -verbose`, SBOM, and dependency reports | Class-file versions and packaged dependencies |

`where java`/`which java` only reveals the executable found via PATH. If a build tool, IDE, or container has its own configuration, inspect that configuration directly.

### 8.1. Recording versions in the assessment report

A migration report should include a table similar to:

```text
Build JVM:          Eclipse Temurin 21.x
Build tool:         Gradle wrapper 8.x
Compiler toolchain: JDK 21.x
Java release:       17
Unit test JVM:      JDK 17.x
Integration JVM:    JDK 21.x
Production runtime: JRE/runtime image 17.x
Artifact target:    Java 17 / class-file major 61
```

The versions above only illustrate recording format. In real reports, take numbers from actual build logs, toolchains, and images. Do not record an estimated version based on desired configuration.

## 9. Configuration principles in CI/CD and development environments

### 9.1. Standardize the build JVM

CI should explicitly select the JDK used to launch Gradle/Maven. With Gradle, configure `JAVA_HOME` or runner JDK selection; similarly with Maven. Ensure the Gradle daemon does not retain an old JVM after environment changes; when needed, stop the daemon and restart it in the properly configured environment.

IDEs should align Gradle JVM/Maven runner JDK with project requirements. A setup working in the terminal yet failing when clicking Build in the IDE usually stems from two different JVMs.

### 9.2. Declare compiler toolchains instead of relying on personal machines

Gradle should declare `java.toolchain` in build scripts. Maven should use Toolchains Plugin and configure JDKs per agent. CI can pre-install JDKs or let a toolchain resolver download JDKs according to organizational policy.

Do not hard-code local JDK paths in build scripts. Paths like `/opt/jdks/jdk-21` or `C:\Program Files\Java\jdk-21` may not exist on other machines. Use standardized toolchain and provisioning mechanisms.

### 9.3. Control runtime via container images or deployment configuration

Production runtime is typically defined by container images, VM images, or service configurations. Record image tag/digest, vendor, JDK/JRE version, and required runtime modules.

Do not infer production runtime from CI's JDK. A build agent may use JDK 21 while the Dockerfile still picks a Java 17 image. Conversely, the production image may already have upgraded to Java 21 while the test pipeline still runs Java 17.

### 9.4. Keep version matrices synchronized with support policy

If the organization supports multiple runtimes, clearly define the lowest version and recommended version. CI must test on committed runtimes. When dropping support for a version, update documentation, artifact metadata, container images, pipelines, and notify consumers.

Keeping an overly broad matrix carries costs: longer CI times, more configurations to support, and slower adoption of new APIs. Maintain only versions with clear demand and support timelines.

## 10. Phased transition plan for the three roles

When upgrading from Java 17 to Java 21, you do not have to switch build JVM, compiler, and application runtime in a single commit. A phased roadmap might look like:

### Phase A: Assess and lock baseline

- Record the JDK currently running Gradle/Maven locally and in CI.
- Record the actual compiler, release target, and class-file version.
- Record the test JVM and production image.
- Check build tool/plugin and dependency support matrices.
- Save baseline build/test results for comparison.

### Phase B: Upgrade build JVM if required by build tool

- Verify Gradle/Maven versions supporting the target JDK.
- Upgrade necessary wrappers/plugins along supported paths.
- Run a clean build and verify plugins, code generators, and annotation processors.
- Do not change the application runtime yet if not ready.

### Phase C: Select compiler toolchain and release target

- Declare JDK 21 as compiler toolchain.
- Choose `--release 17` if the artifact must still support Java 17.
- Run tests on Java 17 and Java 21 according to the support matrix.
- Inspect dependency bytecode/APIs and compiler plugins.

### Phase D: Upgrade application runtime

- Update image/runtime to JDK/JRE 21.
- Run integration/contract tests on the target image.
- Measure startup, latency, throughput, GC, memory, and external connections.
- Roll out via canary or staged groups if the platform supports it.
- Confirm rollback or roll-forward alongside data changes.

### Phase E: Simplify configuration

Once consumers have moved to Java 21 and Java 17 is no longer required, raise `--release` to 21, retire old test matrix entries if no longer needed, update documentation, and remove obsolete workarounds.

Not every project requires all phases above. If build tool, compiler, and runtime already use Java 21 together, still verify each configuration and piece of evidence individually rather than assuming uniformity.

## 11. Pre-release control checklist

Before concluding a migration succeeded, confirm:

- [ ] Identified the JVM running Gradle/Maven in terminal, IDE, and CI.
- [ ] Build tools and plugins support the JVM launching the build.
- [ ] Compiler toolchain is explicitly declared and logs confirm the right JDK.
- [ ] `--release` or equivalent compiler config matches the lowest runtime needing support.
- [ ] Direct and transitive dependencies do not require a higher Java version than the committed runtime.
- [ ] Annotation processors, code generators, and compiler plugins run on the compiler JDK.
- [ ] Unit tests run on the minimum JVM needing support.
- [ ] Integration tests run on the target runtime/image.
- [ ] Packaged artifact was inspected for class-file versions and dependencies.
- [ ] Production image/service uses the approved runtime.
- [ ] Monitoring and rollback/roll-forward align with data and runtime changes.
- [ ] Developer/CI documentation explicitly lists each version and how to verify it.

A checklist is a tool for recording evidence. An item is marked complete only when matching verification results exist, not merely because a config file was edited.

## 12. Conclusion

The build-tool JDK, compiler JDK, and application runtime JDK are three distinct roles. The build JVM determines whether Gradle/Maven and plugins can start; the compiler toolchain determines which compiler generates bytecode and checks APIs; the application runtime determines whether the artifact can load and operate in the deployment environment.

During migration, record and verify each role with the right tools: `./gradlew --version` or `mvn -version` for the build JVM, toolchain/compiler logs for the compiler JDK, and actual images/processes for the application runtime. Combined with `--release`, dependency analysis, and tests across committed JVMs, the team can clearly control compatibility instead of relying on a single generic “Java version” label for the entire project.
