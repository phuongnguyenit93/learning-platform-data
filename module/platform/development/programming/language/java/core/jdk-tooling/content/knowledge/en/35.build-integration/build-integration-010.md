# Synchronizing JDK Between Development Machines and CI

## 1. Purpose of JDK Synchronization

A Java project is typically built across multiple environments: developer machines, IDEs, CI runners, containers, and production hosts. If these environments use different JDKs or build tools, the same commit can produce different results or build successfully only on certain machines.

**Synchronizing the build JDK** means explicitly defining which JDK runs the build tool, which JDK compiles the source, which JDK runs the tests, and which JDK runs the application. These choices must be declared, verified, and applied consistently.

A reliable build configuration must control at least:

- The JDK running Maven or Gradle.
- The JDK toolchain used for compiling, testing, and javadoc.
- The target Java language level and platform API.
- The Maven or Gradle version used via the Wrapper.
- The versions of plugins, annotation processors, and related build tools.
- The JDK runtime in the container or deployment environment.

You should not simply set `JAVA_HOME` and assume every tool uses the same JDK. IDEs, Maven Toolchains, and Gradle Java Toolchains can select a JDK different from the one running the build process.

## 2. Distinguishing Java Version Layers

| Layer | Question | How to control |
|---|---|---|
| Build JVM | Which JDK runs Maven or Gradle? | JAVA_HOME, PATH, IDE build JVM, Enforcer, or Gradle daemon JVM criteria. |
| Compiler toolchain | Which javac compiles the source? | Maven Toolchains or Gradle Java Toolchains. |
| Compile release | Up to which version of Java syntax and API is the source allowed to use? | javac --release, Maven compiler release, Gradle options.release. |
| Test runtime | Which JVM runs unit/integration tests? | Toolchain-aware Surefire/Failsafe or Gradle Test javaLauncher. |
| Application runtime | Which JVM runs the artifact after deployment? | Selected container image, VM image, or runtime package. |
| Build tool | Which Maven/Gradle version runs the lifecycle? | Maven Wrapper or Gradle Wrapper. |

These layers are related but do not replace one another.

For example, Maven can run on JDK 24, use Maven Toolchains to invoke `javac` 17, and produce Java 17 bytecode. Maven Wrapper can pin Maven 3.9.12, but it does not automatically install or select JDK 17. Compiler `release` 17 restricts the API and bytecode, but it does not determine where the compiler executable is located.

## 3. Choosing a Java Baseline for the Project

Before configuring, the team needs to agree on:

1. The minimum Java major version that the source code is allowed to use.
2. The JDK used to compile and run tests.
3. The minimum JDK runtime of the artifact.
4. Whether the vendor and patch version need to be pinned or only the major version.
5. The Maven/Gradle version and required plugins.
6. The JDK upgrade policy and support duration for older versions.

The examples in this article use Java 17 as the baseline for illustration. A project may choose 21 or another version depending on product requirements and dependencies.

Java major version and patch version solve two different problems. Toolchain `languageVersion=17` usually only requires major version 17. If a specific vendor or patch release is needed, you must additionally control the vendor, JDK installation, or CI image.

Do not upgrade the production JDK just because developer machines have installed a newer JDK. Check dependencies, frameworks, plugins, bytecode target, and runtime support before changing the baseline.

## 4. Checking Which JDK Is Currently in Use

On Windows PowerShell:

~~~powershell
java -version
javac -version
mvn -version
gradle --version
where.exe java
where.exe javac
Write-Output $env:JAVA_HOME
~~~

On Linux or macOS:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
which java
which javac
echo "$JAVA_HOME"
~~~

`mvn -version` shows the Maven version and the Java runtime running Maven. `gradle --version` shows the Gradle version, launcher JVM, and daemon JVM.

`java -version` only shows the first `java` command found in `PATH`. `javac -version` shows the compiler executable found by the shell. These two commands can point to different JDKs if `PATH` is misconfigured.

On Windows, you can temporarily switch the JDK for the current terminal:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
mvn -version
~~~

On Linux:

~~~bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
mvn -version
~~~

Replace the example paths with where the JDK is actually installed. Open a new terminal or restart the IDE if needed to apply environment changes.

## 5. Pinning Maven with Maven Wrapper

Maven Wrapper provides the `mvnw` and `mvnw.cmd` scripts so everyone uses the same Maven distribution. Users do not need to manually install the exact Maven version before building; the wrapper downloads the distribution specified in the project if the machine does not have it yet.

Create or update the wrapper:

~~~bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.12 -Dtype=only-script
~~~

Files typically committed to source control include:

~~~text
mvnw
mvnw.cmd
.mvn/
  wrapper/
    maven-wrapper.properties
~~~

After creating the wrapper, build with:

~~~bash
./mvnw clean verify
~~~

On Windows:

~~~powershell
.\mvnw.cmd clean verify
~~~

The `maven-wrapper.properties` file contains `distributionUrl` to specify the Maven distribution. For example:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.12/apache-maven-3.9.12-bin.zip
~~~

The wrapper pins the Maven version, not the JDK runtime. You still need to configure `JAVA_HOME`, toolchains, or the CI image to standardize the JDK.

You should configure `distributionSha256Sum` with the official SHA-256 of the Maven distribution in use. If using a wrapper binary, you can configure `wrapperSha256Sum` for the wrapper JAR. Do not generate checksums yourself; obtain the values from a trusted release source and verify them before committing.

## 6. Using Maven Compiler Plugin and --release

In Maven, the `maven.compiler.release` property specifies the Java release that the compiler must target.

Example:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`javac --release 17` controls the source language, target class file, and Java 17 platform API. This prevents compiling successfully on a newer JDK while accidentally calling APIs that only exist in newer JDKs.

Separate `source` and `target` options do not provide the same API protection as `--release`. With JDK 9 and later, prefer `release` when cross-compiling for a specific Java platform.

`--release` does not select the JDK executable. The compiler can still be `javac` from JDK 24, instructed to produce Java 17-compatible output. To select the exact JDK compiler, use Maven Toolchains or Gradle Java Toolchains.

## 7. Configuring Maven Toolchains on Each Machine

Maven Toolchains allow compatible plugins to use a different JDK from the one running Maven.

Typically, the toolchain descriptor is located at:

- Linux/macOS: `~/.m2/toolchains.xml`
- Windows: `%USERPROFILE%\.m2\toolchains.xml`

Example `toolchains.xml` for JDK 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Replace `C:/Java/jdk-17` with the JDK 17 path on that machine. Each developer and CI environment may have different installation paths, so do not commit a `toolchains.xml` file containing personal machine paths to the repository.

If you need to use a toolchain file in a location other than the default, Maven supports the `-t` option:

~~~bash
mvn -t ./ci/toolchains.xml clean verify
~~~

In CI, you can generate `toolchains.xml` from `JAVA_HOME` after installing the JDK. This approach keeps the same version configuration in the project while obtaining the actual path from the CI environment.

## 8. Requiring a Toolchain in pom.xml

Add the Maven Toolchains Plugin to the build:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-toolchains-plugin</artifactId>
      <version>3.3.0</version>
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
            <version>17</version>
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
        <fork>true</fork>
        <encoding>UTF-8</encoding>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

The Maven Toolchains Plugin reads the list of toolchains on the machine and finds a JDK matching the version 17 requirement in the POM.

The compiler plugin receives the selected toolchain. `fork=true` instructs the compiler plugin to invoke the toolchain's `javac` executable. If `fork` is omitted, the compiler plugin may use the Java compiler API of the JVM running Maven, so you should verify the behavior based on the plugin version and project configuration.

When no matching toolchain is found, the build must fail with a message stating there is no matching JDK. This is a useful signal: either the machine does not have the required JDK installed, or `toolchains.xml` specifies the wrong version/path.

The toolchain descriptor can contain other `provides` attributes such as `vendor`. These attributes are metadata for the plugin to match against. The `jdkHome` path must still point to the JDK with the right vendor/version; verify it using `java -version` and `javac -version` at that exact path.

## 9. Distinguishing Maven Enforcer from Maven Toolchains

The Maven Enforcer Plugin can check the Maven version and the Java runtime running Maven.

Example:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.7.0</version>
  <executions>
    <execution>
      <id>enforce-build-runtime</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <requireMavenVersion>
            <version>[3.9.12,4.0)</version>
          </requireMavenVersion>
          <requireJavaVersion>
            <version>[17,18)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

In the example, Maven must run on Maven 3.9.12 or higher but lower than Maven 4, and the JVM running Maven must be Java 17.

**RequireJavaVersion checks Maven's Java runtime**, not the selected compiler toolchain. If Maven runs on JDK 24 while the compiler toolchain is JDK 17, the rule `[17,18)` will still fail. In that case, set the runtime policy to match the JDKs on which Maven is allowed to run, or omit this rule if the build intentionally allows multiple Maven runtimes.

Maven Toolchains controls the JDK used by compatible plugins. Enforcer checks the conditions of the build process. The two tools complement each other and should be configured according to their respective purposes.

You can add `RequireMavenVersion`, `RequireJavaVersion`, `RequireJavaVendor`, or `RequirePluginVersions` according to project policy. Pinning plugin versions prevents the build from silently changing behavior when default plugins are upgraded.

## 10. Synchronizing Maven in a Multi-Module Project

For multi-module Maven projects, place properties and plugin versions in the parent POM for child modules to inherit.

Values that should be centralized in the parent:

- `maven.compiler.release`.
- `project.build.sourceEncoding`.
- `maven-toolchains-plugin` version and JDK requirement.
- `maven-compiler-plugin` version and configuration.
- `maven-surefire-plugin` and `maven-failsafe-plugin` versions.
- Enforcer rules.

Place shared plugin versions and configurations in `pluginManagement`. Place `maven-toolchains-plugin` in `build/plugins` of the parent if you want the toolchain selection goal to run during the lifecycle of all modules.

Modules should not individually set different releases or toolchains if they belong to the same product and need to be built with the same baseline. If a module genuinely has a different Java requirement, declare the exception explicitly and test it separately.

When upgrading the baseline, check all modules, annotation processors, plugins, and test runtimes. A module using JDK 17 does not guarantee every plugin running in the same build is compatible with JDK 17.

## 11. Pinning Gradle with Gradle Wrapper

Gradle Wrapper provides `gradlew` and `gradlew.bat` so the entire team uses the same Gradle distribution.

Create the wrapper:

~~~bash
gradle wrapper --gradle-version 9.2.1
~~~

Files to commit:

~~~text
gradlew
gradlew.bat
gradle/
  wrapper/
    gradle-wrapper.jar
    gradle-wrapper.properties
~~~

Run the build with:

~~~bash
./gradlew clean check
~~~

On Windows:

~~~powershell
.\gradlew.bat clean check
~~~

The `gradle-wrapper.properties` file contains `distributionUrl`, for example:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
~~~

Gradle Wrapper pins the Gradle distribution; it does not automatically pin the JDK used to run the Gradle daemon or the compiler JDK toolchain. Those two layers must be controlled separately.

You can configure `distributionSha256Sum` with the official checksum of the Gradle distribution so the wrapper verifies the downloaded file. Keep wrapper scripts, properties, and checksums synchronized when upgrading Gradle.

## 12. Using Gradle Java Toolchains

In `build.gradle` Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Java toolchain instructs Gradle to find a matching JDK 17 for Java tasks. `JavaCompile` uses the toolchain's compiler; `Test` and `Javadoc` tasks also use the default toolchain configured by the Java plugin.

You can restrict the vendor if the project requires a specific provider:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

Only set `vendor` when it is an actual project requirement. A vendor filter does not replace patch version checks. If an exact patch release is required, install or provision the exact JDK and verify its metadata.

You can select a separate runtime for a specific `Test` task:

~~~groovy
tasks.register('testsOn17', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Gradle Toolchains decouple the compile/test JDK from the JDK running the Gradle daemon. Gradle can run on JDK 24 while compiling and testing use JDK 17.

## 13. Gradle Auto-Detection and Auto-Provisioning

Gradle automatically detects JDKs in common locations such as `JAVA_HOME`, package managers, and standard installation directories.

List detected toolchains:

~~~bash
./gradlew -q javaToolchains
~~~

If a JDK is in a custom directory, you can add its path to the user's `gradle.properties`:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17
~~~

On Windows, use appropriate Windows paths or forward slashes in the property. Machine-specific paths should be placed in user-level Gradle configuration, not committed to the project if developers have different directory structures.

Gradle can automatically download toolchains when a suitable toolchain download repository/resolver is configured. For example, you can use the Foojay toolchain resolver convention plugin in `settings.gradle.kts`:

~~~kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention").version("1.0.0")
}
~~~

Auto-downloading helps onboarding, but you still need to control the JDK source, vendor, version, and checksum according to organizational policy. If you change paths or the list of JDKs, you may need to stop the daemon:

~~~bash
./gradlew --stop
~~~

## 14. Distinguishing Gradle Daemon JVM from Compiler Toolchain

`gradle --version` displays the Launcher JVM and Daemon JVM. The Launcher JVM starts the Gradle client; the daemon JVM runs most of the build logic. Meanwhile, the Java toolchain determines the compiler/launcher used by tasks.

Example:

~~~text
Gradle 9.2.1
Launcher JVM: 24.0.2
Daemon JVM: 24.0.2
Compiler home: /opt/jdks/jdk-17
Compiler language version: 17
~~~

This is a valid configuration if the Gradle version supports running on JDK 24 and the project requires compiling with JDK 17.

If Gradle runs on a JDK not supported by that Gradle version, the build may fail before the Java toolchain is applied. Therefore, check both Gradle compatibility and the project toolchain.

IDEs can also configure a separate Gradle JVM. When a command-line build succeeds but the IDE fails, check the Gradle JVM in the IDE and compare it with `gradlew --version`.

## 15. Configuring CI for Maven

CI should install the JDK matching the same baseline, invoke the Maven Wrapper, and generate `toolchains.xml` if the POM requires Maven Toolchains.

GitHub Actions example:

~~~yaml
name: Java build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Configure Maven toolchain
        shell: bash
        run: |
          mkdir -p "$HOME/.m2"
          cat > "$HOME/.m2/toolchains.xml" <<EOF
          <toolchains>
            <toolchain>
              <type>jdk</type>
              <provides>
                <version>17</version>
              </provides>
              <configuration>
                <jdkHome>$JAVA_HOME</jdkHome>
              </configuration>
            </toolchain>
          </toolchains>
          EOF

      - name: Verify build environment
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Build and test
        run: ./mvnw -B -ntp clean verify
~~~

`actions/setup-java` installs the JDK and configures `JAVA_HOME`. The step generating `toolchains.xml` helps Maven Toolchains find the installed JDK. Maven Wrapper selects the project's Maven distribution.

If the POM has Enforcer `requireJavaVersion` `[17,18)`, `setup-java` must actually run Maven on JDK 17. If CI intentionally runs Maven on another JDK while compiling with toolchain 17, set the rule to match the runtime policy.

In organizations requiring strict supply chain control, pin GitHub Actions by commit SHA and use managed runners/container images.

## 16. Configuring CI for Gradle

GitHub Actions example for Gradle:

~~~yaml
name: Gradle build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle

      - name: Verify JDK
        run: |
          java -version
          javac -version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Build and test
        run: ./gradlew --no-daemon clean check
~~~

If `build.gradle` requires toolchain 17, Gradle will locate the installed JDK 17. If no matching toolchain is found and auto-provisioning is configured, Gradle can download the JDK via the selected resolver.

Keep the Gradle Wrapper and Java toolchain declaration in the repository. CI only needs to install the JDK per policy and invoke the wrapper; there should not be a CI command that differs from how developers build locally.

## 17. Synchronizing the IDE with the Command Line

IDEs often have multiple different JDK configuration fields:

| IDE/tool | Configuration to check |
|---|---|
| IntelliJ IDEA | Project SDK, language level, Maven Runner JRE, and Gradle JVM. |
| Eclipse | Installed JREs, compiler compliance, and execution environment. |
| VS Code Java | Java runtime configuration and build tool wrapper. |
| Maven CLI | JAVA_HOME, PATH, mvnw, and Maven Toolchains. |
| Gradle CLI | JAVA_HOME, Gradle Wrapper, and Java Toolchains. |

IntelliJ's Project SDK is not necessarily the JDK running Maven or Gradle. If the build tool declares a toolchain, compile/test tasks may use a different JDK from the Project SDK.

After changing the JDK in the IDE, verify again via the terminal:

~~~bash
./mvnw -version
./gradlew --version
./gradlew -q javaToolchains
~~~

A build succeeding via the wrapper in the terminal is an important signal because CI also typically runs the wrapper rather than IDE-specific configurations.

## 18. Multi-Module Gradle and Convention Plugins

For multi-project Gradle builds, place the Java toolchain and release policy in a convention plugin or shared build logic. This prevents module A from using Java 17 while module B accidentally uses the daemon's default JDK.

Simple example in a convention plugin:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Apply the convention plugin to Java modules that need the same baseline. Do not apply the Java plugin to modules containing only documentation or scripts if unnecessary.

If a module has a different Java requirement, declare it separately and add a test matrix to confirm that the module's artifact is compatible with its expected runtime.

## 19. Verifying Bytecode and the Actually Selected JDK

Do not just look at the configuration; inspect the build output.

With Maven:

~~~bash
mvn -version
mvn -X -DskipTests compile
~~~

In the debug log, look for lines similar to:

~~~text
Required toolchain: jdk [ version='17' ]
Found matching toolchain for type jdk: JDK[/opt/jdks/jdk-17]
Toolchain in maven-compiler-plugin: JDK[/opt/jdks/jdk-17]
Compiling 1 source file with javac [forked debug release 17]
~~~

With Gradle:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --info compileJava
~~~

You can inspect the class file using `javap`:

~~~bash
javap -verbose target/classes/example/BuildInfo.class
~~~

A Java 17 class file has major version 61. If the source uses release 17, the class file must be Java 17-compatible.

Run the artifact with the exact target runtime to confirm:

~~~bash
java -cp target/classes example.BuildInfo
~~~

In the verification test, running with JDK 17 produces the output:

~~~text
runtime.feature=17
compiled.release=17
~~~

Checking only the major version is not enough to confirm the entire application runs. You need to run unit tests, integration tests, and smoke tests on the target runtime.

## 20. Testing on Multiple Runtime Versions

Some projects compile once with JDK 17 but must run on multiple supported runtimes. In that case, separate the compile toolchain from the test runtime matrix.

With Gradle, you can create multiple `Test` tasks, each selecting a different `JavaLauncher`:

~~~groovy
tasks.register('testOn21', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

With Maven, toolchain-aware Surefire/Failsafe plugins can use the selected JDK for tests. Check the plugin logs to confirm the JVM actually running the tests.

The test matrix can include Java 17, 21, and the production runtime. You should not compile on one JDK and assume all runtimes are compatible.

## 21. Annotation Processors and Tools Outside the Compiler

A build may also use annotation processors, Kotlin, Scala, Groovy, Javadoc, JNI, GraalVM Native Image, or code generation tools.

Not every plugin automatically uses the Maven/Gradle Java toolchain. Check the plugin documentation and configure it separately if the plugin has an independent compiler or launcher.

Annotation processors run inside the compiler environment. An older processor may be incompatible with a newer JDK even if the project source still compiles. Conversely, a source-generating plugin may require its own JDK.

For multi-language builds, explicitly specify the toolchain for each task and verify the executable in the logs. Do not assume a single Java toolchain declaration controls every external executable outside the build system.

## 22. Pinning Plugins, Dependencies, and Build Configuration

A synchronized JDK is only part of a reproducible build. You also need to pin:

- Maven plugin versions in the POM.
- Gradle plugin versions in the `plugins` block or version catalog.
- Maven/Gradle Wrapper distribution.
- Dependency versions and repository policy.
- Annotation processor and code generator versions.
- JVM arguments and encoding if they affect build output.
- Container image or runner version when exact reproducibility is required.

Avoid using `LATEST`, `RELEASE`, or dynamic dependency versions in production builds. With Gradle, you can use dependency locking and dependency verification. With Maven, use explicit versions and Enforcer rules to detect plugin/dependency drift.

Maven local repository and Gradle cache speed up builds, but they do not replace version pinning. Caching cannot fix differences between JDKs, compiler releases, or runtimes.

## 23. Pinning Patch Version and Vendor

Java toolchain `languageVersion=17` typically allows any JDK major 17 to satisfy the condition. Maven toolchain requirement version 17 also usually represents the major version.

If you only need the same Java API level, major version 17 and release 17 may suffice. If exact reproducibility is needed—for example, due to vendor patch differences—control:

- JDK vendor.
- Specific patch release.
- CPU architecture.
- OS or container base image.
- JDK distribution checksum.
- Native libraries and system dependencies.

You can use a container image pinned by digest or an internal CI image with a specific JDK pre-installed. In the pipeline, print `java -version` and `javac -version` to record evidence.

Do not hardcode personal JDK paths into `pom.xml` or `build.gradle`. Use toolchain criteria and let each machine provide the appropriate installation path.

## 24. Common JDK Synchronization Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Maven runs with an unexpected JDK | JAVA_HOME or PATH points to a different JDK. | Check mvn -version and configure JAVA_HOME. |
| Maven reports toolchain not found | Missing toolchains.xml or provides does not match POM. | Check the toolchains file and required version. |
| Maven uses the Maven JVM's javac | Compiler plugin has not picked up the toolchain or is not forking as configured. | Check maven-toolchains-plugin, compiler plugin, and debug logs. |
| Build reports release version not supported | Compiler JDK is too old for the requested release. | Install a matching toolchain or lower the release per policy. |
| Artifact fails with UnsupportedClassVersionError | Runtime is lower than the bytecode target. | Check major version and deployment runtime. |
| IDE build differs from CLI | Different IDE SDK, Maven Runner JRE, or Gradle JVM. | Run the wrapper and synchronize IDE configuration. |
| Gradle reports JDK not found | Toolchain is not installed or Gradle cannot detect it. | Run javaToolchains, configure installation path or resolver. |
| Gradle still uses an old daemon | Daemon retains previous toolchain metadata. | Run gradlew --stop and rebuild. |
| Unit tests run on an unexpected JDK | Test plugin or launcher has not picked up the toolchain. | Check Surefire/Failsafe or Gradle Test javaLauncher. |
| CI succeeds but local fails | Different JDK, vendor, Maven/Gradle, or environment. | Compare version output, toolchain selection, and wrapper. |
| One module uses a different release | Child configuration overrides parent or convention plugin. | Centralize release/toolchain in parent or convention plugin. |
| New build fails after upgrading JDK | Plugin or annotation processor does not yet support the new JDK. | Upgrade plugins in a controlled manner and verify compatibility. |

## 25. Repeatable JDK Synchronization Workflow

1. Choose the Java baseline and minimum runtime.
2. Choose the JDK vendor/patch policy based on product requirements.
3. Pin Maven or Gradle using the Wrapper.
4. Declare the compiler release in Maven or Gradle.
5. Configure Maven Toolchains or Gradle Java Toolchains.
6. Configure the build JVM policy with Enforcer or CI runtime setup when needed.
7. Put shared configuration in the parent POM or Gradle convention plugin.
8. Install the right JDK on developer machines and CI.
9. Generate Maven `toolchains.xml` on CI if required by the POM.
10. Configure the IDE to use the right project SDK and build JVM.
11. Run the wrapper build, unit tests, and integration tests.
12. Inspect toolchain logs, `javac` version, and class file major version.
13. Record JDK, Maven/Gradle, plugin, and OS versions in the build report.
14. Re-run tests on the production runtime or test matrix.
15. Only upgrade the baseline after dependencies and plugins are confirmed compatible.

## 26. Verification Results on JDK 24.0.2

An independent Maven project was built with Maven 3.9.12 running on Azul JDK 24.0.2. Maven Toolchains Plugin 3.3.0 selected Corretto JDK 17.0.15; Maven Compiler Plugin 3.13.0 used `javac` from the toolchain with release 17.

Verification log:

~~~text
Required toolchain: jdk [ version='17' ]
Found matching toolchain for type jdk: JDK[...corretto-17.0.15]
Toolchain in maven-compiler-plugin: JDK[...corretto-17.0.15]
Compiling 1 source file with javac [forked debug release 17]
BUILD SUCCESS
~~~

An independent Gradle project also built successfully with Gradle 9.2.1 running on Azul JDK 24.0.2 and compiler toolchain Corretto 17.0.15:

~~~text
Compiler language version: 17
BUILD SUCCESSFUL
~~~

For both projects, `javap` reported major version 61 and running the class with JDK 17 produced the output:

~~~text
runtime.feature=17
compiled.release=17
~~~

Maven Enforcer Plugin 3.7.0 successfully verified `RequireMavenVersion` and `RequireJavaVersion` against the Maven runtime in the test run. Maven Wrapper Plugin 3.3.4 generated a wrapper pinning Maven 3.9.12 and `mvnw.cmd -version` ran successfully. Gradle Wrapper generated a wrapper pinning Gradle 9.2.1 and `gradlew.bat --version` ran successfully.

These test runs confirm that the toolchain selection and wrapper mechanisms work. They do not prove that every plugin or dependency of a real-world application is compatible with JDK 17; projects need to run their own test suites and dependency checks.

## 27. Checklist Before Considering a Build Synchronized

- [ ] Agreed on the Java baseline for source and runtime.
- [ ] Identified the JDK running Maven/Gradle.
- [ ] Identified the JDK toolchain used for compiling.
- [ ] Set `--release` or `maven.compiler.release`.
- [ ] Pinned Maven/Gradle using the Wrapper.
- [ ] Pinned plugin versions.
- [ ] Configured Maven Toolchains or Gradle Java Toolchains.
- [ ] Avoided committing personal JDK paths.
- [ ] Configured CI to install the JDK under the same policy.
- [ ] Configured `toolchains.xml` in CI if using Maven Toolchains.
- [ ] Verified the test runtime.
- [ ] Synchronized Project SDK and build JVM in the IDE.
- [ ] Checked `javac` version and class file major version.
- [ ] Ran tests on the production runtime.
- [ ] Recorded JDK, build tool, plugin, and environment versions.
- [ ] Verified checksums if pinning distributions or container images.

## 28. References

- Apache Maven Toolchains Plugin — Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Apache Maven Compiler Plugin — compiler:compile: https://maven.apache.org/components/plugins/maven-compiler-plugin/compile-mojo.html
- Apache Maven Enforcer — Built-in Rules: https://maven.apache.org/enforcer/enforcer-rules/index.html
- Apache Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven Wrapper Plugin — Usage: https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html
- Gradle — Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- GitHub Actions setup-java: https://github.com/actions/setup-java

JDK synchronization requires controlling the build JVM, compiler toolchain, release, test runtime, and deployment runtime as separate layers. Maven/Gradle Wrapper pins the build tool; Toolchains select the JDK for compiling/testing; `--release` restricts the API and bytecode; Enforcer checks build process conditions. When these layers are declared and verified on both developer machines and CI, builds become consistent and more reproducible.
