# Synchronizing the JDK Across IDE, Terminal, Build Tools, and Tests in Java 17

A Java 17 project can run cleanly in the terminal yet fail in the IDE; compile with Gradle yet fail with Maven; or compile properly for Java 17 while the test suite runs on Java 21. The root cause is usually that **each component is selecting a different JDK**.

Synchronizing the JDK means clearly defining **which JDK compiles the code, which JDK runs the program, which JDK runs the build tool, and which JDK executes tests**. These four roles can share the same JDK 17 installation or intentionally use different JDKs. For learners starting Java 17, the easiest setup to control is using JDK 17 across every project task, then encoding the version rules in the build tool so teammates and CI behave identically.

## 1. Distinguishing Every Place Where a JDK Is Chosen

| Component | What Role Does the JDK Play? | Primary Way to Check |
| --- | --- | --- |
| **Terminal** | Runs `java`, `javac`, and CLI tools. | `java -version`, `javac -version`, resolved executable paths. |
| **IDE** | Analyzes code, selects API/language level, compiles, and runs its own configurations. | Project SDK, module SDK, language level, Run/Debug configuration. |
| **Gradle or Maven** | Runs the build tool itself and selects the compiler to produce `.class` files. | `./gradlew --version` / `mvn -version`, compiler and toolchain settings. |
| **Test suite** | Runs tests on the JVM launched by the IDE or build tool. | Print `java.version` and `java.home` directly inside the test process. |
| **CI** | Runs builds/tests on a machine separate from the developer's workstation. | JDK setup step, version logs, and build/test output. |

An easy point of confusion is that **the JDK running a tool is not necessarily the JDK that tool uses to compile the project**. For example, Gradle can run on JVM 21 while using a Java 17 toolchain to invoke the Java 17 compiler. Conversely, Maven running on JDK 21 with `--release 17` produces Java 17-compatible bytecode, yet tests may still execute on JDK 21 unless a separate JVM is configured for the test runner.

Visualize the version selection paths as follows:

```text
Terminal
  ├─ PATH  ───────────────────────────> resolved java / javac commands
  └─ JAVA_HOME ───────┐
                      ├───────────────> JVM running Maven or Gradle (*)
IDE ─────────────────┤
  ├─ IDE Runtime ─────────────────────> JVM running the IDE itself
  ├─ Project / Module SDK ────────────> SDK for IDE analysis and compilation
  ├─ Build tool JVM ──────────────────> JVM running Maven / Gradle from the IDE
  └─ Run / Test configuration ────────> JVM running apps and tests in the IDE

Build configuration
  ├─ Java release / compiler options ─> Target language, APIs, and bytecode
  ├─ Java toolchain ──────────────────> JDK used by toolchain-aware tasks
  └─ Test runtime / launcher ─────────> JVM actually executing tests

(*) Also depends on build tool configuration and launch environment.
```

Therefore, merely seeing **Project SDK = 17** in the IDE or `java -version` printing **17** is not enough to conclude the whole project uses Java 17.

## 2. Establishing a Clear Version Contract

Before configuring anything, lock down the project's target:

- **Java 17 source code:** uses language syntax finalized in Java 17.
- **Java 17 platform APIs:** avoids accidentally calling APIs introduced only in newer JDKs.
- **Java 17 bytecode:** `.class` files use class-file major version **61**.
- **Java 17 runtime:** the application and tests must run on JVM 17 if Java 17 is the supported deployment target.

These are four related but distinct conditions. For example, `sourceCompatibility = 17` does not always prevent referencing newer APIs from the JDK currently performing compilation. When you need to enforce Java 17 language, API, and bytecode rules together, use **`javac --release 17`** (or the equivalent Maven/Gradle configuration).

For a pure Java 17 practice exercise, a straightforward target setup looks like:

```text
Installed machine JDK:  17
Terminal java/javac:    17
IDE Project SDK:        17
Gradle/Maven compiler:  --release 17
Application JVM:        17
Unit-test JVM:          17
CI test JVM:            17
```

This is a **configuration target**, not a requirement that every modern IDE or build tool must itself run on JDK 17. Some IDE versions, extensions, or newer Gradle releases require a newer runtime; in that case, let the tool run on its required JDK while keeping the project's toolchain and test JVM at 17.

## 3. Installing JDK 17 and Recognizing a Valid JDK

Java 17 is an **LTS** release. You can use an OpenJDK 17 distribution suited to your OS, CPU architecture, and practice environment policy, such as Eclipse Temurin, Amazon Corretto, Microsoft Build of OpenJDK, or Oracle JDK. Clearly distinguish a **JDK** from a runtime-only Java installation: exercises involving compilation require `javac`.

A JDK root directory typically has the structure:

```text
<JDK_17_HOME>/
├── bin/
│   ├── java      (or java.exe on Windows)
│   ├── javac     (or javac.exe on Windows)
│   └── javap     (or javap.exe on Windows)
├── conf/
├── jmods/
└── release
```

`JAVA_HOME` must point to **the JDK root directory**, not `bin`, `java.exe`, or `javac.exe`. Example paths are illustrative: replace them with the actual JDK 17 path installed on your machine.

### Windows PowerShell

Check versions and locations resolved by the OS:

```powershell
java -version
javac -version
$env:JAVA_HOME
where.exe java
where.exe javac
Get-Command java -All | Select-Object Name, Source
Get-Command javac -All | Select-Object Name, Source
```

To select JDK 17 **for the current PowerShell session only**:

```powershell
# Replace with your actual JDK 17 installation directory.
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
java -version
javac -version
```

`Test-Path` must return `True`. This setting lasts only for the current terminal window. For persistent usage, set `JAVA_HOME` in Windows **Environment Variables** and place `%JAVA_HOME%\bin` in `Path` in the desired order; then **open a new terminal** to pick up the updated environment variables. Re-check `where.exe java` because the machine may have multiple Java folders in `Path`.

Note: an IDE window opened before editing environment variables may still hold the old environment; restart the IDE or adjust the JDK directly in its settings.

### macOS

On macOS you can list installed JDKs and select version 17:

```bash
/usr/libexec/java_home -V
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"

echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
```

If `java_home -v 17` finds no JDK, install JDK 17 for the right architecture and try again. To persist across new terminals, place the `export` commands in your shell startup file, such as `~/.zshrc` for common Zsh setups. Only add them to the file matching how your shell is actually launched.

### Linux

On Linux, JDK paths vary across distributions and installation methods. Locate the actual path before configuring:

```bash
type -a java
type -a javac
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
java -version
javac -version
```

Once the JDK 17 root directory is identified:

```bash
# Example; adjust the path to match your machine's installation.
export JAVA_HOME=/usr/lib/jvm/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"

test -x "$JAVA_HOME/bin/javac" && echo "JDK is ready"
"$JAVA_HOME/bin/java" -version
java -version
javac -version
```

On some Linux distributions, `update-alternatives` or `alternatives` manages default `java`/`javac` links. Do not assume changing `java` automatically updates `javac`; check both. On shared machines or multi-project setups, prefer shell/project-level configuration over needlessly changing the system-wide default JDK.

### When `java` and `javac` Outputs Differ

Example:

```text
java -version   -> 21
javac -version  -> 17.0.x
JAVA_HOME       -> JDK 17 directory
```

This usually occurs because `PATH` prioritizes another `bin` folder. Inspect the resolved command paths rather than reading `JAVA_HOME` alone. Even when both commands print `17`, they may still originate from different distributions or installations; when exact reproducibility matters, inspect the path and vendor with `java -XshowSettings:properties -version` and check properties like `java.home` and `java.vendor`.

## 4. Synchronizing the JDK in the IDE

An IDE typically separates **the JVM running the IDE itself**, **the JDK assigned to the project**, **the JVM running the build tool**, and **the JVM for Run/Test configurations**. These locations can be independent. The goal is for the project to be analyzed under Java 17 and for actual executions to use the right JDK.

### IntelliJ IDEA

For a Java 17 project:

1. Go to **File → Project Structure → SDKs** and add the JDK 17 path if missing.
2. Under **Project**, set **Project SDK = JDK 17** and **Language level = 17** (or the matching SDK-derived level).
3. Check **Modules → Dependencies** to ensure the module uses the Project SDK or an explicitly selected SDK 17.
4. For Gradle projects, go to **Settings → Build, Execution, Deployment → Build Tools → Gradle** and check **Gradle JVM**. This is the JVM running Gradle from the IDE; also check **Build and run using** and **Run tests using** to see whether the IDE delegates execution to Gradle.
5. For Maven projects, inspect **Maven Runner → JRE** and the **Importer** JDK setting if your IDEA version exposes it.
6. Open **Run → Edit Configurations** and verify the JRE/JDK in application and JUnit run configurations. Configurations using the Gradle test runner may obtain their JVM from the Gradle toolchain rather than purely from Project SDK.

Menu labels may vary across IntelliJ IDEA versions. What to check are **source SDK**, **Gradle/Maven process JVM**, and **Run/Test JVM**, rather than searching for a single setting box. IntelliJ's own bundled runtime (often JetBrains Runtime) may differ in version from your project's JDK 17; do not force the IDE's own runtime to 17 if your IDE version requires a newer JDK.

### Visual Studio Code with Java Extension Pack

In VS Code, open **Command Palette → Java: Configure Java Runtime** to inspect Java runtimes detected by the Java extension and configured for the project. For plain Java folders not managed by Maven/Gradle, you can specify Java 17 in `settings.json`:

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "C:\\Java\\jdk-17",
      "default": true
    }
  ]
}
```

This is a Windows path example; on macOS/Linux use the OS-appropriate JDK path. For Maven/Gradle projects, **`pom.xml`/`build.gradle` and toolchains must still be properly configured** because they govern many actual build and test tasks.

Some versions of the Java Language Server require a JDK newer than 17 to **run the language server**, while still compiling the project for Java 17. The `java.jdt.ls.java.home` property (when supported by your installed extension) selects the JDK that launches the language server; it does not replace `java.configuration.runtimes` or Maven/Gradle compiler settings. Pick the extension runtime required by your **installed extension version**, and configure the project JDK as 17.

### Eclipse IDE

In Eclipse, inspect these locations:

1. **Preferences → Java → Installed JREs**: add the **JDK 17** path and select it for the project.
2. **Project → Properties → Java Build Path → Libraries**: check `JRE System Library` or the execution environment matching **JavaSE-17**.
3. **Project → Properties → Java Compiler**: verify compiler compliance level 17 and source/target settings if the project overrides them.
4. **Run Configurations / Debug Configurations → JRE**: choose JDK 17 for application or JUnit launches when running directly from Eclipse.
5. If imported via Maven/Gradle, check the build tool settings as well and refresh/update the project configuration after editing `pom.xml`/`build.gradle`.

The `JavaSE-17` execution environment describes the project's Java 17 environment; the JVM running Eclipse itself may be different. Across all IDEs, **clicking Run in the IDE** and **running `gradlew test`/`mvn test` in the terminal** do not automatically guarantee the same test JVM is used.

## 5. Gradle: Distinguishing the Gradle JVM from the Java Toolchain

Gradle involves at least two independent decisions:

1. **Gradle JVM/daemon JVM:** the JVM running Gradle itself. This JVM must satisfy the compatibility requirements of the project's Gradle version.
2. **Java toolchain:** the JDK that toolchain-aware Java tasks use to compile, run tests, and generate documentation.

Use the project's **Gradle Wrapper** to pin the Gradle version instead of relying on a globally installed Gradle:

```bash
# macOS/Linux, when the project has a Gradle Wrapper
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
```

On Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat clean test
```

The `--version` output shows the Gradle version and information about the JVM launching Gradle; exact formatting may vary by Gradle release. The `javaToolchains` task displays which JDKs Gradle can detect and use as toolchains. **Do not deduce the compilation JDK from `./gradlew --version` alone**.

### Configuring Gradle Groovy DSL for Java 17

In `build.gradle`:

```groovy
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
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()  // When the project uses JUnit Jupiter/JUnit Platform.
}
```

Meaning:

- `java.toolchain` instructs toolchain-aware Java tasks to use a JDK with **feature version 17**. It does not require the Gradle daemon to run on JDK 17.
- `options.release = 17` passes `--release 17` to the Java compiler, safeguarding Java 17 syntax, bytecode, and platform APIs simultaneously.
- The standard `Test` task from the Java plugin normally selects its Java launcher from the declared toolchain. Custom `Test`/`JavaExec` tasks or specialized plugins may configure a different launcher; check their individual configurations.
- `useJUnitPlatform()` is only needed when running JUnit on JUnit Platform; appropriate test dependencies must be declared separately. Do not use this setting to infer the test JDK.

If you want to explicitly state **the test JVM is Java 17** directly on `Test` tasks, configure the Java launcher in the same `build.gradle`:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

This snippet makes it immediately visible in the build script that unit tests must run on JDK 17, especially in projects with multiple JVMs or multiple test tasks.

For projects using **Gradle Kotlin DSL**, the corresponding configuration in `build.gradle.kts` is:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

### When Gradle Cannot Find JDK 17

Messages like **"No matching toolchains found"** indicate Gradle has not discovered a toolchain satisfying the requirements. Check:

- Whether JDK 17 is installed with a valid `bin/javac` path.
- Whether `./gradlew -q javaToolchains` detects JDK 17.
- Whether criteria such as `languageVersion`, `vendor`, and `implementation` (if additionally constrained by the project) match the installed JDK.
- Whether the project actively configures automatic toolchain provisioning. **Do not assume** Gradle always auto-downloads missing JDKs: toolchain provisioning depends on the Gradle version and repository/resolver configuration.

When needed, you can specify JDK discovery locations via `org.gradle.java.installations.paths` in `gradle.properties` following your Gradle version's syntax and conventions. Avoid committing a hardcoded personal machine path into shared team config; prefer toolchain detection, CI installation conventions, or user-level configuration.

### When the Gradle Daemon Still Runs Another JDK

`JAVA_HOME` is one source for choosing the JVM that launches Gradle, but Gradle also has its own JVM settings: **Gradle JVM in the IDE**, `org.gradle.java.home`, and, in supported versions, the project's **Daemon JVM criteria**. As a result, `java -version` in the terminal may report 17 while the Gradle daemon runs on another JDK.

To resolve this, check `./gradlew --version`, the IDE's Gradle JVM setting, project and user `gradle.properties`, and—if the project uses daemon JVM criteria—`gradle/gradle-daemon-jvm.properties`. Choose a JVM to run Gradle matching **your Gradle version's compatibility matrix**, while keeping **Java toolchain 17** for compilation and testing. Do not rush to switch your entire machine to a newer JDK just because a Gradle version requires a newer runtime.

## 6. Maven: `JAVA_HOME`, `--release`, and Maven Toolchains

Maven normally runs on whichever JDK the `mvn` command inherits from its launch environment; check with:

```bash
mvn -version
mvn clean test
```

If the project provides a **Maven Wrapper**, use the project's wrapper to keep the Maven version consistent:

```bash
# macOS/Linux
./mvnw -version
./mvnw clean test
```

```powershell
# Windows PowerShell
.\mvnw.cmd -version
.\mvnw.cmd clean test
```

`mvn -version` prints the Maven version along with the **Java version / Java home Maven is running on**. If Maven reports JDK 11 when the project needs a Java 17 compiler, merely setting `release=17` in `pom.xml` will not enable JDK 11 to compile Java 17.

### Configuring the Java 17 Level in `pom.xml`

For a standard Maven project, set:

```xml
<project>
    <!-- Project elements: modelVersion, groupId, artifactId, etc. -->
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

This is an **illustrative snippet** to insert into an existing valid `pom.xml` (do not replace the whole POM with this snippet). `maven.compiler.release` is supported by the Maven Compiler Plugin and passes `--release 17`; the project must use an appropriate compiler plugin version and a JDK compiler capable of targeting 17.

If you run Maven on JDK 17 with no custom overrides, aligning `JAVA_HOME`, `mvn -version`, and `maven.compiler.release=17` is usually sufficient for simple projects. However, if Maven runs on a newer JDK, unit tests may run on Maven's JVM or another JVM depending on Surefire/Failsafe settings.

### Maven Toolchains When a Machine Has Multiple JDKs

Maven Toolchains allow toolchain-aware plugins to use a selected JDK without depending solely on the JDK running Maven. Example user file `~/.m2/toolchains.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

The path is a Unix example; replace it with your actual JDK directory. This file lives on the user/CI machine, so teammates do not have to share identical paths. For Maven to **select** JDK 17, add the Maven Toolchains Plugin under `<build><plugins>` in your POM:

```xml
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
                <version>17</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Maven Toolchains is not a switch that immediately forces **every plugin** to run on Java 17: only toolchain-aware plugins and goals honor that selection. Ensure the Maven Compiler Plugin and test plugins are compatibly configured. With a supporting Maven Surefire Plugin version, you can explicitly specify the JDK for the test process:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <!-- Use the project-managed Surefire version that supports jdkToolchain. -->
    <configuration>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

If using the Maven Failsafe Plugin for integration tests, inspect **Failsafe's** JVM/toolchain configuration separately. Surefire's configuration does not automatically ensure integration tests run on the same JVM. When Maven has multiple toolchains available, inspect plugin logs and verify inside the test JVM itself which JDK was actually chosen.

## 7. Verifying the JDK Actually Running the Application and Tests

`java -version`, IDE displays, and `--release 17` show only **part of the picture**. To know which JDK a program is truly running on, print information from **inside that process**.

### Checking from a Java Program

Save as `RuntimeProbe.java`:

```java
public class RuntimeProbe {
    public static void main(String[] args) {
        System.out.println("Java version: " + System.getProperty("java.version"));
        System.out.println("Feature version: " + Runtime.version().feature());
        System.out.println("Java home: " + System.getProperty("java.home"));
        System.out.println("Java vendor: " + System.getProperty("java.vendor"));
        System.out.println("Class format: " + System.getProperty("java.class.version"));
    }
}
```

Compile and run in the terminal:

```bash
javac --release 17 RuntimeProbe.java
java RuntimeProbe
```

Example output when **actually running on JDK 17**:

```text
Java version: 17.0.x
Feature version: 17
Java home: <path to running JDK 17>
Java vendor: <JDK vendor>
Class format: 61.0
```

The `java.home` value reveals where the running runtime resides; do not automatically assume it equals `$JAVA_HOME` or the JDK path shown in the editor. Here `java.class.version` describes the current JVM; to check the **major version of a compiled `.class` file**, inspect the class file with `javap -verbose` and look for `major version` (61 for Java 17).

### Checking in JUnit 5

When a project already uses JUnit Jupiter and runs tests via Gradle/Maven/IDE, you can add a **temporary environment check**:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TestRuntimeProbe {
    @Test
    void testJvmMustBeJava17() {
        System.out.println("Test java.version = " + System.getProperty("java.version"));
        System.out.println("Test java.home = " + System.getProperty("java.home"));

        assertEquals(17, Runtime.version().feature(),
                "This test must run on JVM 17");
    }
}
```

Run the test **once in the IDE and once via the build command**, then compare `Test java.home`. If the two outputs differ, the two test paths are selecting different JVMs.

`assertEquals(17, ...)` is an appropriate check when **an exercise or deployment target strictly requires a Java 17 runtime**. If a project intentionally tests compatibility across multiple JDKs (such as 17 and 21), do not keep this hardcoded assertion in the shared suite; replace it with goal-appropriate compatibility checks and a CI matrix if needed.

Note: many test runners hide or capture `System.out` into reports. If you do not see output on the console, inspect Gradle/Maven test reports or test logging settings; **a passing test does not prove the right JVM was used unless you verified the runtime**.

## 8. Maintaining the Same Configuration in CI

On a CI machine, the runner's default `java` command may differ from a developer's laptop. Provision or select the JDK matching the project contract in the pipeline, then invoke the build tool wrapper:

```text
CI job
  ├─ Provision/select JDK 17
  ├─ Print java -version, javac -version, JAVA_HOME
  ├─ Gradle: ./gradlew --version && ./gradlew clean test
  │           or
  └─ Maven:  ./mvnw -version   && ./mvnw clean verify
```

If using toolchains, the build tool may intentionally run on a JDK other than 17; in that case, provision **both the JDK running Gradle/Maven and the JDK 17 required by the toolchain/test launcher**, and log them for traceability. With Maven Failsafe, `verify` is typically the lifecycle phase that runs configured integration tests; with Gradle, run the project's relevant test tasks, because `test` does not necessarily include every custom integration test task.

Items that belong in the repository for reproducibility:

- **Gradle Wrapper/Maven Wrapper** and associated configuration files to lock the build tool version.
- **Java release 17 configuration** (`options.release` or `maven.compiler.release`).
- **Toolchain/test launcher configuration** if the project needs to run across multiple JDKs.
- **JDK 17 setup instructions**, environment verification steps, and CI requirements.

Do not commit absolute JDK paths specific to one developer's machine or personal environment details into shared settings. Files like `.java-version`, `.sdkmanrc`, or `mise.toml` can be helpful if the team agrees on a JDK manager; they are **version selectors**, not replacements for proper compiler and test runtime settings in Gradle/Maven.

## 9. Common Errors and How to Trace Them

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `java -version` is 17 but `javac -version` is 21 | `PATH` points to two different installations. | `where.exe` or `type -a`/`command -v`; reorder `PATH`. |
| `JAVA_HOME` is 17 but `mvn -version` reports another Java | Maven was launched from another environment, IDE runner, or runtime config prioritizes a different JDK. | `mvn -version`, actual Maven path, Maven Runner JRE in IDE. |
| `release version 17 not supported` or `invalid target release: 17` | The running compiler does not support target 17 (e.g., an older JDK). | JDK used by `javac`/Maven compiler or Gradle toolchain. |
| `No matching toolchains found` | Toolchain asks for Java 17 but no matching JDK was detected. | JDK paths, `javaToolchains`, toolchain criteria, and provisioning settings. |
| Gradle fails to start with the chosen JDK | Gradle version and the JVM running Gradle are incompatible. | Gradle Wrapper, `./gradlew --version`, Gradle JVM/daemon JVM criteria. |
| Compiles with `--release 17` but fails when running on JDK 17 | Different actual runtime, incompatible dependency, or runtime behavior outside compiler checks. | `java.home` at runtime, dependency versions, full logs, and real JDK 17 test run. |
| IDE shows Java 17 syntax errors while terminal builds cleanly | IDE Project SDK, module SDK, or language level is out of sync. | Project/Module SDK, Java compiler settings, Maven/Gradle import settings. |
| Tests pass in IDE, fail in CI | Different test JVM, environment variables, dependencies, OS, or task configuration. | `java.home` from both test processes, wrapper commands, and CI logs. |
| Tests compile but are not discovered or not run | JUnit engine/dependencies or test runner setup mismatch; not necessarily a JDK issue. | JUnit Platform, Surefire/Gradle `Test`, test names, test execution reports. |
| `UnsupportedClassVersionError` | The running JVM does not support the generated class's major version. | Actual major version via `javap -verbose` and running JVM version. |

**Layered diagnosis approach:** find the **first command or task that fails**, identify whether it runs in the terminal, IDE, Gradle daemon, Maven process, or test JVM; inspect **that exact process** before changing settings. A compiler error caused by selecting the wrong JDK will not be cleanly solved by only changing a Run configuration's JRE.

### Distinguishing Bytecode Compatibility Errors from Missing API Errors

Suppose a `.class` file is compiled on a newer JDK and then run on Java 17. If the class file has a major version above **61**, JVM 17 refuses to load it with `UnsupportedClassVersionError`. Even if source and target are both 17, a compiler using an API introduced only in a newer JDK can still cause failures upon deployment; hence **`--release 17` and running tests on JDK 17** solve two complementary layers of the problem.

## 10. End-to-End Synchronization Checklist

For a new Java 17 project or one freshly imported onto another machine, follow this sequence:

1. **Install JDK 17**. Verify `java` and `javac` exist in the same JDK directory.
2. **Configure the terminal**. Check `JAVA_HOME`, `PATH`, `java -version`, `javac -version`, and the OS-resolved command paths.
3. **Configure the build script**. With Gradle, declare toolchain 17 and `options.release = 17`. With Maven, declare `maven.compiler.release=17`; use toolchains if decoupling Maven's JVM from the compiler JDK.
4. **Use the wrapper** (`gradlew` or `mvnw` if present in the repo) so the whole team uses the same build tool version. Check which JVM the build tool uses.
5. **Configure the IDE**. Set Project/Module SDK 17 and language level 17, then check Gradle JVM/Maven Runner and Run/Test configurations.
6. **Compile, run the app, and run tests**. Print `java.version` and `java.home` from the app/test process to verify the real runtime.
7. **Mirror the setup in CI**. Have CI run the wrapper and supply JDK 17 to tasks that require it; compare version logs between local and CI when behavior differs.

Example output of a system **properly synchronized for Java 17** might look like:

```text
Terminal java/javac   : 17 / 17
IntelliJ Project SDK  : 17
Gradle toolchain      : 17
Compiler --release    : 17
JUnit test java.home  : <JDK 17 path>
CI compiler/test JDK  : 17
```

If Gradle or the Java Language Server uses a newer JVM due to its own tool requirements, the setup still satisfies the Java 17 target as long as **the compiler, target APIs, bytecode, and test/deployment runtime** are properly configured and verified. The key is **role-based synchronization backed by evidence from the actual running process**, rather than forcing every piece of software on the machine to share one `JAVA_HOME` value.
