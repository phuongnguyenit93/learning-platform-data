# Using a Different JDK During Build: Controlling the Java Version Across the Entire Build

This lesson belongs to the **Tooling Anti-Patterns** group. Using a different JDK across developer machines, IDEs, Maven/Gradle, CI, and the application runtime environment is not automatically wrong. It becomes an anti-pattern when the difference happens unintentionally, is not declared in the build, and is not tested. In that situation, the same commit may compile against different APIs, produce different bytecode, run tests on different runtimes, or build successfully only on one person's machine.

Four Java versions should be distinguished within a workflow:

1. **Build JVM:** the JDK/JRE running Maven or Gradle and the build tool's plugins.
2. **Compiler/test toolchain:** the JDK providing `javac`, `javadoc`, and the Java launcher for tests/tasks.
3. **Target release:** the Java version whose APIs the source is allowed to use and with which class files must be compatible.
4. **Production runtime:** the JRE/JDK that actually runs the application after deployment.

These four values can differ intentionally. For example, Maven/Gradle runs on JDK 24, the compiler uses JDK 24 with `--release 17`, and the application is tested and deployed on Java 17. What matters is that each role is explicitly configured, documented, and tested.

This lesson uses Java 17 as the illustrative target. The practical verification was run on Windows 11 with Zulu/OpenJDK 24.0.2, Maven 3.9.12, and Gradle 9.2.1.

## 1. What Is the Anti-Pattern?

A project may encounter the following situations:

- Developer A uses JDK 17, while Developer B uses JDK 21.
- The IDE compiles using Project SDK 21, while the terminal runs Maven using JDK 17.
- Maven runs on JDK 24, the compiler plugin uses JDK 17, and tests fork using JDK 21 unintentionally.
- The Gradle daemon uses JDK 21, but the project has not declared a toolchain, so the compiler defaults to the JDK running Gradle.
- CI uses JDK 17, while the local machine uses JDK 24; the source accidentally calls an API introduced in Java 19.
- The Maven Wrapper or Gradle Wrapper has been committed, but the team assumes the wrapper also pins the JDK. Wrappers only pin the build tool version.
- The machine has multiple JDKs in `PATH`; `java` and `javac` are resolved from two different directories.
- `JAVA_HOME` points to one JDK, but the IDE or Gradle Tooling API launches the build with a different JDK.

Consequences often do not appear immediately. A build may pass locally but fail on CI, tests may pass on a newer JDK but fail on the minimum supported runtime, or a released binary may have bytecode/APIs higher than the promised support level.

**The core anti-pattern is letting the environment pick a JDK arbitrarily.** Declaring a JDK toolchain different from the JDK running the build is a valid design if there is a reason and appropriate testing.

## 2. Distinguishing the Four Java Versions

| Component | Question to Answer | How to Control |
|---|---|---|
| Build JVM | Which JDK is Maven/Gradle running on? | `JAVA_HOME`, IDE runner, Gradle daemon JVM criteria |
| Compiler toolchain | Which `javac`/`javadoc` is invoked? | Maven Toolchains, Gradle Java Toolchains |
| Target release | Which Java version's APIs and class file format are targeted? | `javac --release`, Maven `maven.compiler.release`, Gradle `options.release` |
| Runtime | Which JDK are the application and tests running on? | Test launcher/toolchain, CI matrix, production image |

Example of a valid policy:

| Stage | JDK |
|---|---:|
| Running Gradle daemon | 17 |
| Compiling source | 21 |
| Target API/bytecode | 17 |
| Running unit tests | 17 |
| Running production | 17 |

Another example: Maven runs on JDK 24, the compiler also uses JDK 24, but `--release 17` restricts APIs and bytecode to Java 17. This is a way to build a library supporting Java 17 from a newer build machine. However, tests still need to be run on Java 17 to verify the actual runtime.

## 3. When Is Using Different JDKs Reasonable?

Using multiple JDKs intentionally is appropriate in the following cases:

- The project must support multiple runtimes, for example Java 17 and Java 21.
- A newer JDK is used as the build JVM because the Maven/Gradle version or a plugin requires it, while the product still supports an older runtime.
- A newer JDK compiler is needed for a compiler feature, while `--release` keeps the target API at a lower level.
- The test suite runs on multiple runtimes to detect JVM behavior changes.
- A separate task requires a different JDK, such as running `javadoc`, `jdeps`, `jlink`, `jpackage`, `jarsigner`, or native integration testing.
- A multi-release JAR has separate source sets for different Java versions.

Each difference should have a specific goal, be configured in the build or CI, and have logs showing the actual JDK used. Do not select a JDK based on installation order on a machine or unshared personal configuration.

## 4. Why `source`/`target` Do Not Solve the Whole Problem

The legacy options:

~~~text
javac -source 17 -target 17 ...
~~~

`-source` selects syntax/language rules; `-target` selects the class file format. When using a newer JDK compiler, these two options do not automatically restrict the entire platform API to the target version.

For example, the JDK 24 compiler can see `Thread.threadId()`, an API introduced in Java 19. If only `-source 17 -target 17` is set, the source may still reference the new API and compile successfully, but running on Java 17 will fail during linking or execution.

For Java 9 and later, prefer:

~~~text
javac --release 17 ...
~~~

`--release 17` combines language rules, the target class file format, and the published API surface for Java 17. It does not change the JDK running `javac`; it controls the platform version that the source is compiled against.

Do not combine `--release` with `-source` or `-target` in the same command. Choose one explicit target configuration.

## 5. Reading the Actual JDK on a Machine

`java -version` only tells you the first `java` executable found by the shell. It is not necessarily the JDK that the IDE, Maven compiler, or Gradle toolchain is using.

On Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java, javac
where.exe java
where.exe javac
java -version
javac -version
mvn -version
gradle -version
~~~

On Linux/macOS:

~~~sh
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
mvn -version
gradle -version
~~~

On macOS, you can list installed JDKs:

~~~sh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
~~~

To inspect the JVM properties of the Java process invoked from the shell:

~~~text
java -XshowSettings:properties -version
~~~

Look for `java.home`, `java.version`, and `java.vendor` in the output. For Maven and Gradle, check the output of `mvn -version` and `gradle -version` directly; do not infer the build JDK solely from `java -version`.

## 6. `JAVA_HOME` and `PATH` Can Mismatch

`JAVA_HOME` is commonly used by Maven, Gradle, and Java scripts as the default JDK location. `PATH` determines which executable is invoked when typing `java` or `javac`.

A machine can be in this state:

~~~text
JAVA_HOME = C:\jdks\jdk-17
PATH      = C:\jdks\jdk-24\bin;...
~~~

In this case, `mvn` may run on JDK 17 via `JAVA_HOME`, while `java -version` displays JDK 24 from `PATH`. The diagnostic output looks contradictory, but the two commands are actually selecting Java through two different mechanisms.

To align them in a PowerShell terminal:

~~~powershell
$env:JAVA_HOME = 'C:\jdks\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
mvn -version
gradle -version
~~~

In Bash:

~~~sh
export JAVA_HOME=/opt/jdks/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
mvn -version
gradle -version
~~~

This configures the current shell process. How environment variables are persisted depends on the OS, shell, and CI. Avoid committing personal JDK paths into build scripts.

## 7. Maven: The JDK Running Maven and the Compiling JDK Are Separate

Maven typically launches on the JDK selected by `JAVA_HOME` or the launcher environment. Without a toolchain configured, plugins may use the Maven process's JDK for tasks such as compile, Javadoc, test, or signing.

Check the JVM running Maven:

~~~text
mvn -version
~~~

Example output:

~~~text
Apache Maven 3.9.12
Java version: 24.0.2, vendor: Azul Systems, Inc.
OS name: "windows 11", arch: "amd64"
~~~

This output shows that the Maven process is running on Java 24. It does not prove that the project is producing Java 24 bytecode; the compiler may be configured with `--release 17` or use a different JDK toolchain.

The Maven Wrapper (`mvnw`, `mvnw.cmd`) pins the Maven distribution version. It does not automatically pin the JDK running Maven. CI must still install/select the appropriate JDK.

## 8. Maven: Setting Target Release with the Compiler Plugin

For a Java library supporting Java 17, declare the release explicitly in the POM:

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

You can keep `maven.compiler.release` in properties so modules inherit the same policy. If `<release>17</release>` is configured directly in the plugin, avoid setting a different value elsewhere.

Run:

~~~text
mvn -B -ntp clean verify
~~~

The Compiler Plugin passes the release target to the compiler. If Maven is running on JDK 24, the default compiler may still be the JDK 24 compiler; the output is restricted to Java 17 thanks to `--release`.

## 9. Maven Toolchains: Selecting a Separate Compile JDK

When you need the compiler/Javadoc/tests to run with a JDK different from the JVM running Maven, use Maven Toolchains.

There are two parts:

1. The POM requests a toolchain.
2. The build machine provides the JDK path in `toolchains.xml`.

Example configuration in `pom.xml`:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>

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
            <version>[17,18)</version>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

On a developer machine, create `~/.m2/toolchains.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17.0.12</version>
    </provides>
    <configuration>
      <jdkHome>C:\jdks\temurin-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

The `jdkHome` path must point to the root of a JDK containing `bin/java` and `bin/javac`, not the `bin` directory and not a JRE missing the compiler.

The POM uses the version range `[17,18)` to accept JDK 17 with different patch versions. If using a literal version, the `<version>` value in the toolchains metadata must match exactly according to Maven's matching rules. You can add `<vendor>` when you want to constrain the vendor; this token is matched exactly against the metadata, so verify the actual value.

`toolchains.xml` usually contains local paths and should not be committed to the source repository. CI needs to install the JDK and generate/configure the corresponding toolchains.

## 10. Maven Toolchains Does Not Change the JVM Running Maven

After selecting a toolchain, the Maven process still runs on the JVM that started Maven. The toolchain is passed to plugins that understand Maven Toolchains, such as the Compiler, Surefire, Failsafe, and Javadoc plugins.

This allows:

- Maven to run on JDK 24.
- The compiler to use JDK 17.
- Surefire to run tests with JDK 17 if the plugin picks up the toolchain.
- Javadoc to use JDK 17 if the plugin picks up the toolchain.

Not every third-party plugin supports toolchains. A plugin that does not recognize toolchains may continue using the JVM running Maven or require its own executable configuration. Read the plugin documentation and check the logs.

The Maven Compiler Plugin also has its own `jdkToolchain` parameter. When configured, the compiler's own toolchain can override the shared toolchain selected by `maven-toolchains-plugin`. Only use it when you truly need a different compiler for a specific plugin/execution; otherwise, select a single shared toolchain for consistent compile/test/Javadoc behavior.

## 11. Gradle: Distinguishing Client JVM, Daemon JVM, and Project Toolchain

Gradle has at least three JVM roles to distinguish:

- **Client JVM:** the process that launches the `gradle` or `gradlew` command.
- **Daemon JVM:** the background process that executes the build and holds cache/configuration state.
- **Project toolchain:** the JDK used for compile, test, JavaExec, and Javadoc tasks.

The client and daemon can use different JDKs. The project toolchain can also differ from both.

`gradle -version` displays Gradle's JVM information. In recent outputs, you may see `Launcher JVM` and `Daemon JVM`. When a build runs from an IDE, the Tooling API/IDE can decide the daemon JVM, so the terminal and IDE may pick different daemons.

Do not take `java -version` as the sole evidence for Gradle's compile JDK. Check `gradle -version`, the toolchain configured in the build script, and the list of toolchains discovered by Gradle.

## 12. Gradle Java Toolchains: Pinning the Project JDK

Example `build.gradle` using JDK 17 for default Java tasks:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

The Java Plugin will use this toolchain for the compile, test launcher, and Javadoc tasks it manages. Gradle can detect installed JDKs or download a matching JDK if toolchain provisioning is configured.

If you need the JDK 21 compiler while keeping Java 17 API/bytecode:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

This is a valid configuration: the toolchain selects the JDK 21 compiler; `options.release` restricts the target API and class files to Java 17. Do not use `sourceCompatibility`/`targetCompatibility` instead when strict API compatibility is needed.

## 13. Gradle: Selecting a Separate Runtime for Tests

You can use a different JDK for the test launcher without changing the compiler toolchain:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

For example, compile with JDK 21 using `options.release = 17`, but run unit tests on JDK 17. This is useful to verify that the library actually works on the minimum runtime.

If you need to test on both Java 17 and 21, create two `Test` tasks or use a CI matrix. Each test task should specify its launcher explicitly so results do not depend on the machine's default JDK.

Gradle also allows individual tasks to obtain `JavaCompiler`, `JavaLauncher`, or `JavadocTool` from `javaToolchains`. Use this approach when a custom task needs to invoke the right JDK instead of manually assembling `JAVA_HOME/bin` paths.

## 14. Gradle Daemon JVM: Controlling the JDK Running the Build

`org.gradle.java.home` in `gradle.properties` can specify the JVM for the Gradle daemon:

~~~properties
org.gradle.java.home=C:/jdks/temurin-17
~~~

Absolute path values are better suited for personal machine configurations or managed build environments; do not commit a path that only exists on a single workstation.

Gradle versions that support Daemon JVM criteria can generate `gradle/gradle-daemon-jvm.properties` with the task:

~~~text
./gradlew updateDaemonJvm --jvm-version=17
~~~

The criteria file can be committed so the team and CI share the JVM requirement for running Gradle. Gradle will select a matching daemon JVM according to the criteria; when criteria are used, they take precedence over `JAVA_HOME` and `org.gradle.java.home`.

When changing JDKs or daemon configuration, you can stop the old daemon:

~~~text
./gradlew --stop
~~~

Then re-run the build and check `./gradlew -version`. Do not stop the daemon as a cure-all for compiler errors; only use it when you need to clear a daemon process holding old JVM configuration or for diagnostics.

## 15. IDEs Can Use a Different JDK Than the Terminal

IDEs often have multiple independent Java settings:

- Project SDK: the JDK used to index/compile the project in the IDE.
- Maven Runner JRE: the JVM launching Maven from the IDE.
- Gradle JVM: the JVM launching the Gradle daemon via the IDE.
- Module language level: the source language level checked by the IDE.
- Build delegation: whether the IDE builds by itself or delegates to Maven/Gradle.

A project may compile successfully using the Build button in the IDE but fail with `./mvnw verify` or `./gradlew check` in the terminal.

How to configure:

- Set the Project SDK to a JDK supported by the project.
- Set the Maven Runner JRE to be compatible with Maven and the build configuration.
- Set the Gradle JVM to match the Gradle version/daemon criteria.
- Let the Maven/Gradle toolchain determine the project's compiler/test runtime.
- Use wrapper commands from the terminal to verify the build independently of the IDE.

IDE settings do not replace build configuration. Other team members and CI cannot rely on your personal IDE configuration.

## 16. Maven Wrapper and Gradle Wrapper Do Not Pin the JDK

The Maven Wrapper stores the Maven distribution and the Gradle Wrapper stores the Gradle distribution. Neither wrapper automatically installs or selects the same JDK across all machines.

For example:

~~~text
Windows:
mvnw.cmd -version
gradlew.bat -version

Linux/macOS:
./mvnw -version
./gradlew -version
~~~

Wrappers help the team use the same Maven/Gradle version, but build results can still differ if the JDK, toolchain, OS, architecture, or dependencies differ.

For better reproducibility, combine:

- Committed wrappers with distribution checksum verification.
- Declared JDK/toolchain versions.
- Explicitly set `--release`.
- Pinned plugin/build logic versions.
- Locked or version-controlled dependencies.
- CI using the same policy as developers.

## 17. CI: Pin the JDK Explicitly

Example GitHub Actions workflow running Maven on Java 17:

~~~yaml
name: Java 17 build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Show Java and Maven
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Verify
        run: ./mvnw -B -ntp clean verify
~~~

For Gradle, replace the verify step with:

~~~yaml
      - name: Verify
        run: ./gradlew --no-daemon clean check
~~~

If a library supports multiple runtimes, create a CI matrix running tests on each supported JDK, such as 17 and 21. Keep the target release at the lowest committed compatibility level; the test matrix verifies runtime behavior across those versions.

Do not simply install the latest JDK and let the build choose automatically. Specify the vendor/version, and print `java -version`, `mvn -version`, or `gradle -version` in the logs. On self-hosted runners, check for stale daemons and toolchain caches after changing JDKs.

## 18. Checking the Target API and Bytecode

A `.class` file has a major version corresponding to the Java release. For example, Java 17 produces class files with major version `61`. Use `javap` to inspect:

~~~text
javap -verbose -classpath target/classes com.example.ToolchainDemo
~~~

Look for the line:

~~~text
major version: 61
~~~

This confirms that the class file targets Java 17. It does not by itself prove that all dependencies in the application also support Java 17; dependency bytecode and runtime must also be checked.

You can inspect a JAR with:

~~~text
jar --describe-module --file target/library.jar
jdeps --multi-release 17 --jdk-internals target/library.jar
~~~

`jdeps` helps analyze dependencies at the class/module level. It complements `--release` checks; it does not replace testing on the target runtime.

## 19. Example Controlling the JDK with `javac`

Create `ToolchainDemo.java`:

~~~java
public final class ToolchainDemo {
    private ToolchainDemo() {
    }

    public static void main(String[] args) {
        System.out.println(
                "JAVA_RUNTIME_FEATURE=" + Runtime.version().feature());
        System.out.println(
                "STRING_IS_BLANK=" + "   ".isBlank());
    }
}
~~~

Compile for Java 17 using the installed compiler:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out ToolchainDemo.java
~~~

Run:

~~~text
java -cp out ToolchainDemo
~~~

If run with JDK 24:

~~~text
JAVA_RUNTIME_FEATURE=24
STRING_IS_BLANK=true
~~~

Inspect bytecode:

~~~text
javap -verbose -classpath out ToolchainDemo
~~~

The output should contain:

~~~text
major version: 61
~~~

The runtime feature shows 24 because the `java` executable running it is JDK 24; the class file is still compiled for Java 17. When run with Java 17, the first line will be `JAVA_RUNTIME_FEATURE=17`.

## 20. Negative Test: Detecting APIs Newer Than the Target

`Thread.threadId()` was added in Java 19. Create a separate fixture:

~~~java
public final class NewApiProbe {
    public static void main(String[] args) {
        System.out.println(Thread.currentThread().threadId());
    }
}
~~~

Compile with a newer JDK while targeting Java 17:

~~~text
javac --release 17 NewApiProbe.java
~~~

The compiler must report that `threadId()` cannot be found in `Thread`, because that API does not belong to Java 17.

Compile the same source with the JDK 24 compiler without a release restriction:

~~~text
javac NewApiProbe.java
~~~

This command may succeed, but the class file will target the current JDK and will not be suitable for a Java 17 runtime. This is a common bug when builds are only verified on a newer JDK.

This negative test is useful to prove that `--release` is being applied. Place the fixture in a separate test or compile-failure test directory; do not put it in the main source set because it must fail when the target is Java 17.

## 21. Verifying the Actual Build

Cross-check the results:

| Command | Information to Confirm |
|---|---|
| `java -version` | Runtime found by the shell |
| `javac -version` | Compiler found by the shell |
| `mvn -version` | Maven distribution and JVM running Maven |
| `gradle -version` | Gradle version, launcher JVM, and daemon JVM |
| `./gradlew -q javaToolchains` | JDKs detected by Gradle |
| `javap -verbose` | Class file major version |
| `jar --describe-module` | Module descriptor in JAR |

For Maven Toolchains, check the `toolchain` goal log and `toolchains.xml` configuration; `mvn -version` only displays the JVM running Maven. For Gradle, check the project `java.toolchain` and the daemon JVM separately.

Record key versions in the build log or build scan so there is sufficient evidence when comparing local and CI builds.

## 22. Common Errors and How to Handle Them

### `UnsupportedClassVersionError`

**Cause:** The runtime is older than the bytecode version of a class or dependency.

**Resolution:** Inspect with `javap -verbose`, confirm the target release, check all dependencies, and run on the minimum supported runtime.

### `NoSuchMethodError` or `NoClassDefFoundError` on an Older Runtime

**Cause:** Compilation succeeded against a newer API, but the runtime lacks that method/class, or runtime dependencies differ from compile dependencies.

**Resolution:** Use `--release`, inspect the dependency tree, and run tests on the target runtime.

### IDE Build Succeeds but Maven/Gradle CLI Fails

**Cause:** Project SDK, Maven Runner JRE, or Gradle JVM differs from the terminal configuration.

**Resolution:** Check each IDE setting separately, run the wrapper from the terminal, check `mvn -version`/`gradle -version`, and configure toolchains in the build.

### `JAVA_HOME` Is Correct but `java -version` Is Wrong

**Cause:** `PATH` has another JDK listed before `JAVA_HOME/bin`.

**Resolution:** Check `where.exe java` or `command -v java`, reorder `PATH`, and open a new terminal.

### Maven Runs on the Right JDK but the Compiler Uses the Wrong JDK

**Cause:** Maven Toolchains was not selected, a plugin does not recognize toolchains, or a separate `jdkToolchain` configuration overrides the shared toolchain.

**Resolution:** Check `toolchains.xml`, the POM, plugin versions, and selection logs. Confirm that compiler, Surefire/Failsafe, and Javadoc plugins support toolchains.

### Gradle Uses an Old Daemon JVM

**Cause:** The IDE/daemon still has a running process from a previous configuration, or daemon criteria differ from `JAVA_HOME`.

**Resolution:** Check `gradle -version`, inspect `gradle.properties` and daemon criteria, run `./gradlew --stop`, and rebuild.

### Local Build Passes but CI Fails

**Cause:** Local uses a newer JDK, while CI uses an older target runtime; or vendor, patch, OS, or architecture differs.

**Resolution:** Pin the JDK/toolchain, keep `--release`, add a runtime matrix, and print versions in CI logs.

### `mvnw`/`gradlew` Still Uses an Unwanted JDK

**Cause:** Wrappers only select the build tool distribution.

**Resolution:** Configure `JAVA_HOME`, Maven Toolchains, Gradle Daemon JVM criteria, and the project toolchain according to each role.

### Annotation Processor or Plugin Only Works on One JDK

**Cause:** The processor/plugin runs in its own JVM/compiler environment and may depend on internal APIs or a specific JDK.

**Resolution:** Pin processor/plugin versions, check the provider's compatibility matrix, configure the right toolchain, and test on the actual CI JDK.

## 23. JDK Support Matrix Should Be Written as Policy

A policy table helps developers and CI share the same contract:

| Attribute | Example Policy |
|---|---|
| Build tool | Maven Wrapper 3.9.12 |
| Build JVM | JDK 17 |
| Compiler toolchain | JDK 17 |
| `--release` | 17 |
| Unit test runtime | JDK 17 and 21 |
| Production runtime | JDK 17 |
| JDK vendor | Temurin or organization-approved vendor |
| Architecture | x86_64 and AArch64 if supported by the product |
| Encoding | UTF-8 |
| CI | Matrix across supported runtimes |

If the build JVM must be newer due to Gradle/Maven/plugins, document the build JVM and project toolchain separately. Do not force every role to use the same version number when there is a clear technical reason.

## 24. Reproducibility: Do Not Pin Only the Major Version

The same major version does not necessarily mean an identical environment. When reproducible builds are needed, consider:

- JDK vendor and patch version.
- OS and CPU architecture.
- Maven/Gradle Wrapper version.
- Plugin versions and dependency resolution.
- Compiler flags, annotation processors, and encoding.
- Locale, timezone, file permissions, and line endings.
- Environment variables used by build scripts.
- Docker base image or runner image.
- Build timestamps and generated metadata.

For general-purpose libraries, pinning major/toolchain versions and matrix testing is usually sufficient. For native builds, signing, byte-for-byte reproducible builds, or compliance, tighter pinning of vendor/patch/architecture and image digests is needed.

Do not hardcode a workstation's absolute JDK path into the POM or `build.gradle`. Use toolchain requirements and let each machine/CI provide the appropriate installation path.

## 25. Recommended Workflow When Changing JDKs

1. Check compatibility of the Maven/Gradle wrapper and plugins.
2. Choose the JDK running the build tool.
3. Choose the compiler/test/Javadoc toolchain.
4. Declare the target release explicitly.
5. Configure the IDE to match the command-line policy.
6. Update the CI JDK and runtime matrix.
7. Run compile, test, Javadoc, packaging, and static analysis.
8. Inspect bytecode with `javap` and dependencies with `jdeps` when needed.
9. Run the consumer/application on the minimum runtime.
10. Record the version/toolchain in the release log.

When changing JDKs, delete or rebuild outputs/caches only when needed to clear stale compiled classes or daemon state; do not treat wiping all caches as the default fix. First identify which process is still using the old JDK.

## 26. Checklist Against JDK Mismatches

- [ ] Distinguished build JVM, compiler toolchain, target release, and production runtime.
- [ ] `JAVA_HOME`, `PATH`, and IDE settings do not conflict unintentionally.
- [ ] `mvn -version` or `gradle -version` is checked in logs.
- [ ] Maven/Gradle Wrapper is committed and version-pinned.
- [ ] Maven Toolchains or Gradle Java Toolchains are configured when a separate JDK is needed.
- [ ] `--release` is set explicitly instead of relying only on `source`/`target`.
- [ ] Tests run on the minimum supported runtime.
- [ ] CI has a matrix for committed JDK runtimes.
- [ ] JDK vendor/patch/architecture are specified if required.
- [ ] Compiler, tests, Javadoc, and plugins actually use the right toolchain.
- [ ] No personal workstation absolute JDK paths are committed.
- [ ] Class files and dependencies are checked when upgrading the JDK.
- [ ] Release artifacts are tested on the production runtime.

## 27. References

- Oracle JDK 24 — `javac --release`, source/target, and cross-compilation: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven — Compiling Sources Using a Different JDK: https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html
- Apache Maven — Maven Toolchains Plugin: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Apache Maven — Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Gradle — Toolchains for JVM Projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Gradle Daemon and Daemon JVM Criteria: https://docs.gradle.org/current/userguide/gradle_daemon.html
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- GitHub Actions — Building and testing Java with Maven: https://docs.github.com/en/actions/use-cases-and-examples/building-and-testing/building-and-testing-java-with-maven

Using a different JDK during a build is valid if the difference is intentionally configured. The anti-pattern is letting the shell, IDE, Maven, Gradle, CI, and production pick inconsistent JDKs without a policy. Pin toolchains for each stage, use `--release` to lock the API/bytecode target, and run tests on the actual supported runtimes.