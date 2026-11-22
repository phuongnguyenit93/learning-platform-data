# Configuring a Java 21 Toolchain for a Pattern Matching Project

## 1. Why configure the toolchain instead of just writing Java 21 code?

Java 21 finalized **pattern matching for `switch`** (JEP 441) and **record patterns** (JEP 440). Syntax such as `case String s`, `case Point(int x, int y)`, `when` guards, `case null`, and pattern switches over sealed hierarchies can compile **without `--enable-preview`** when using the right Java 21 JDK/source level.

However, syntactically valid code can still fail to build if one part of the toolchain is not configured properly:

- The terminal runs `java` 21, but `javac` is actually 17.
- Maven starts on JDK 17, and the compiler plugin uses a different `javac` or does not set `release`.
- Gradle runs on one JVM, while `JavaCompile` uses a different JVM/toolchain.
- The IDE allows selecting Language Level 21, yet CI still compiles with JDK 17.
- A build succeeds on JDK 24 with `source`/`target` 21, but accidentally calls an API that only exists in JDK 24.
- The application is compiled to Java 21 bytecode, but deployed on JVM 17.
- Tests run on a different JVM than production, leading to different results or errors.

A **toolchain** is how you declare **which JDK executes build tasks** such as compiling, running tests, and generating Javadoc. A solid configuration needs consistency across the **JDK chosen to build**, the **language level and APIs to support**, the **execution runtime**, the **IDE**, and **CI**.

For a project using Java 21's finalized pattern switch, the recommended setup includes:

1. **Provide a JDK 21** (not just a JRE) to Maven/Gradle or the build system.
2. **Declare a Java 21 toolchain** at the project level.
3. **Compile with `--release 21`** to lock the source language, JDK APIs, and class-file target to Java 21.
4. **Run unit/integration tests on Java 21**; if production uses a different JDK version, test on that environment as well.
5. **Keep CI, the IDE, and Docker/runtime in sync**, avoiding hidden configuration mismatches.
6. **Do not enable preview unnecessarily**: pattern switch and record patterns have been final since Java 21.

*Scope of this article:* Configuring Java 21 for pure Java projects using Maven/Gradle. Android Gradle Plugin, Spring Boot, Kotlin/JVM, Scala, native image, and certain compilers/plugins have their own compatibility matrices; always check against specific tool versions rather than assuming all ecosystems share the same matrix.

## 2. Distinguishing the four version layers

A common mistake is seeing the number `21` in one config file and assuming every stage is already using Java 21.

| Component | Example | What does it guarantee? | What does it NOT guarantee? |
| --- | --- | --- | --- |
| **JDK running the build tool** | `mvn -version` or `./gradlew --version` | The JVM running Maven/Gradle and the build logic | Not necessarily the JDK selected by compiler/test tasks |
| **Java toolchain** | Maven Toolchains Plugin, Gradle `java.toolchain` | Selects the JDK for compile/test/javadoc if the task/plugin supports it | Does not automatically restrict using older Java APIs when compiling with a newer JDK |
| **`--release 21`** | Maven `maven.compiler.release=21`, Gradle `options.release=21` | The syntax level, bytecode target, and Java SE APIs visible to the compiler | Does not download/install a JDK and does not determine the JVM running the build tool |
| **Runtime** | `java -version` in container/production | The JVM that will execute the built classes/JAR | Does not automatically fix code compiled against the wrong API or class-file target |

**Intentional example:** Maven runs under JDK 17, but selects a **JDK 21 toolchain** to compile. This can be completely valid if the plugins support toolchains. Conversely, setting `maven.compiler.release=21` in the POM while the compiler is JDK 17 will **not turn JDK 17 into JDK 21**.

With Gradle, you must distinguish between the **JVM running the Gradle daemon** and the **JDK for Java tasks**. According to Gradle's official compatibility matrix, **Gradle 8.4** added Java 21 support for toolchains (compile/test), while **Gradle 8.5** added support for **running Gradle itself on JDK 21**. Therefore, if `JAVA_HOME` points to JDK 21, do not use a Gradle Wrapper older than 8.5 to run directly on Java 21 and expect the toolchain to rescue the Gradle daemon.

## 3. Installing and verifying JDK 21

You can choose a JDK distribution supported by your project, such as **Eclipse Temurin 21** or another suitable OpenJDK 21 build. The team should standardize on the major version and security patch update policy. There is no need to force everyone onto the exact same installation path.

### 3.1. Checking the active commands

In a terminal:

```bash
java -version
javac -version
```

Valid output for a local JDK 21 target looks like:

```text
openjdk version "21.0.x" ...
javac 21.0.x
```

The `...` and `x` only **illustrate the output format**, not the exact stdout of a specific patch version. Actual output varies by vendor and patch level.

On macOS/Linux:

```bash
command -v java
command -v javac
echo "$JAVA_HOME"
```

On PowerShell (Windows):

```powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
where.exe java
where.exe javac
```

If `java` and `javac` do not come from the same JDK, check `JAVA_HOME` and the order of entries in `PATH`. A JRE can run programs, but it does not include `javac`; development projects require a **JDK**.

### 3.2. Setting JAVA_HOME

macOS/Linux example (replace the path with the actual JDK 21 location):

```bash
export JAVA_HOME=/absolute/path/to/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
```

PowerShell example (**sample path only**, do not run without replacing the path):

```powershell
$env:JAVA_HOME = "C:\Path\To\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

These commands set variables **for the current shell only**; configure persistent environment settings via your OS mechanism or a JDK manager if you want them to apply across sessions. On Windows, some already-open terminal/IDE applications keep the old environment variables until restarted.

**Important:** `JAVA_HOME` is a global mechanism for a session, not a tool for locking every project to JDK 21. When working on multiple Java 17, 21, and 25 projects on the same machine, declaring toolchains **per project** is more reliable.

## 4. Maven: the simplest setup with JDK 21 and --release

If the team only has JDK 21, you can run Maven on JDK 21 and lock `release`.

Minimal `pom.xml` example for a Java application:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>java21-patterns</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`maven.compiler.release=21` is how you configure `javac --release 21` through the Compiler Plugin. This is a stable parameter supported by the Maven Compiler Plugin documentation. `--release` has three main effects:

1. The compiler accepts Java 21 language syntax, such as finalized pattern switch and record patterns.
2. The compiler generates **class-file version 65** (Java 21).
3. The compiler checks Java SE APIs against Java 21; you will not accidentally use Java SE APIs that only exist in newer JDKs when the compiler runs from JDK 24/25.

`sourceCompatibility/targetCompatibility` or `-source/-target` alone do not replace the Java API constraints enforced by `--release`.

Run at the project root containing `pom.xml`:

```bash
mvn -version
mvn -B -ntp clean verify
```

If using a Maven Wrapper provided by the project:

```bash
./mvnw -B -ntp clean verify
```

On Windows PowerShell, use `.\mvnw.cmd -B -ntp clean verify`. The wrapper must be generated and managed in the repository beforehand; **this article does not assume a `mvnw` file automatically exists**.

**Limitation of the simple approach:** if Maven is running on JDK 17, merely adding `release=21` can fail with `release version 21 not supported`. When you want the **Maven JVM to differ from the compiler JDK**, use the Maven Toolchains Plugin in the next section.

## 5. Maven Toolchains Plugin: selecting JDK 21 independently of Maven's JVM

### 5.1. Selecting a JDK via discovery

Maven Toolchains Plugin **3.2.0+** supports auto-discovering JDKs in standard locations; plugin **3.3.0** provides the `select-jdk-toolchain` goal. **Complete** POM example for this option:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>java21-toolchain</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <!-- Only accept JDKs from major version Java 21 -->
        <toolchain.jdk.version>[21,22)</toolchain.jdk.version>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>select-jdk-toolchain</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Explanation:**

- `<toolchain.jdk.version>[21,22)</toolchain.jdk.version>` requires a Java 21 JDK, accepting `21.0.x` patches and excluding Java 22+.
- The `select-jdk-toolchain` goal binds to the `validate` phase by default, finds a compatible JDK, and places the toolchain into the build context for supporting plugins.
- If the JVM running Maven **already** satisfies the constraint, the plugin can use that JDK directly by default without selecting a separate toolchain, avoiding unnecessary forks.
- `maven.compiler.release` is still needed to explicitly specify the Java language/API target even when the compiler is chosen from JDK 21.
- If no matching JDK is found, the build should fail with an error; it should not silently compile with an older JDK.

To inspect the JDKs discovered by Maven, run:

```bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
```

Run this in a directory containing a Maven POM. For deeper debugging, check the build log and the JDK used by the compiler/test plugins; looking only at `mvn -version` is not enough, as it reports the **Maven process JVM**.

### 5.2. Manual configuration via ~/.m2/toolchains.xml

In isolated environments or when you want to declare JDKs explicitly, use `toolchains.xml` in the Maven user home directory:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/absolute/path/to/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

**Replace** `/absolute/path/to/jdk-21` with an existing JDK directory on your machine. On Windows, the path may be a directory on drive C; do not run with the literal example path. `<version>` and `<vendor>` inside `<provides>` are **user-declared metadata**, so they must accurately match the actual JDK.

With the manual mechanism, Maven Toolchains Plugin uses the `toolchain` goal and its corresponding configuration:

```xml
<!-- <plugin> snippet inside pom.xml only -->
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
                <version>[21,22)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

**Do not put both discovery and manual configurations in the POM just because you saw two examples.** Pick one suitable strategy. Discovery is usually more convenient; manual fits environments with tightly controlled JDK paths. Toolchain lookup goals **do not automatically download JDK 21** if no JDK is installed or configured.

### 5.3. Compile toolchain and test runner JVM

Maven Toolchains can be used by plugins such as Compiler, Surefire, and Javadoc to select a JDK. However, not every custom plugin is toolchain-aware. For the test JVM, you can configure the **Maven Surefire Plugin** explicitly if needed:

```xml
<!-- <plugin> snippet inside <build><plugins> -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <jdkToolchain>
            <version>[21,22)</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

This configuration requests a JDK in the 21 range for the test JVM when Surefire selects the corresponding toolchain. Ensure test dependencies (such as JUnit/JUnit Platform if used) are also declared and plugin versions match your system. In projects with integration tests or custom forks/plugins, verify **each** test group's execution JVM separately.

**Do not confuse:** toolchains solve **JDK selection**, not whether every dependency supports Java 21; code generation, annotation processors, frameworks, and libraries still need compatible versions.

## 6. Gradle: Java 21 toolchain and options.release

### 6.1. build.gradle.kts (Kotlin DSL)

Example for a Java project using Gradle:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
    options.encoding = "UTF-8"
}
```

**Explanation:**

- `java.toolchain.languageVersion=21` tells Gradle that Java tasks require JDK 21.
- `options.release=21` for `JavaCompile` requests `javac --release 21`, locking Java 21 language/API/bytecode.
- `options.encoding="UTF-8"` standardizes source file encoding; it is not a fix for all runtime data encoding issues.
- With the `java` toolchain configured, Gradle also coordinates the JDK for Java tasks like test and Javadoc according to each task's support.
- External plugins may create their own `JavaExec`/worker tasks; check whether they use the toolchain.

### 6.2. build.gradle (Groovy DSL)

Equivalent:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.encoding = 'UTF-8'
}
```

**Do not** use Kotlin DSL syntax `tasks.withType<JavaCompile>()` in a Groovy `build.gradle`, or copy Groovy syntax `id 'java'` into Kotlin DSL and expect it to compile. Match the project's DSL file.

### 6.3. Gradle Wrapper and compatibility thresholds

Gradle has two separate compatibility columns:

| What you need | Documented Gradle threshold for Java 21 |
| --- | --- |
| Compile/run tests using **Java 21 toolchains**, even if the Gradle daemon runs on another JDK | **Gradle 8.4+** |
| Run the **Gradle process itself on JDK 21** | **Gradle 8.5+** |

Source: [Gradle Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html).

If `JAVA_HOME=JDK 21` and the wrapper is too old, you may see errors from Groovy/ASM/Gradle build logic **before** `JavaCompile` even runs. Use a maintained Gradle Wrapper version compatible with your team's JDK and all plugins. Do not blindly upgrade a build that has Android/Spring/Kotlin plugins to the latest Gradle without checking plugin compatibility matrices.

Verify (at the root containing the Gradle Wrapper):

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --no-daemon clean test
```

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat` as appropriate.

`javaToolchains` lists the JDKs detected by Gradle, whereas `--version` shows the JVM running Gradle. The two commands **do not necessarily report the same JDK**.

### 6.4. Missing JDK: auto-detection and auto-provisioning

Gradle can auto-detect installed JDKs. If JDK 21 is not found, auto-provisioning **only works when a toolchain download repository is configured** (such as an appropriate resolver plugin) and the system has network download access. You cannot simply declare `languageVersion=21` and expect every offline machine to automatically download the right JDK.

One option supported by Gradle is the **Foojay Toolchains Resolver Convention** (configured in `settings.gradle.kts`):

```kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}
```

This is an **example resolver mechanism** from the Gradle documentation; when applying it in practice, confirm the plugin version is compatible with your Gradle Wrapper and your organization's JDK provisioning policy. If builds must run offline, install and point to JDK 21 explicitly rather than relying on network downloads.

When you only want to use pre-installed JDKs, you can declare environment variables or paths for Gradle to discover. Example in `gradle.properties` (illustrative):

```properties
org.gradle.java.installations.fromEnv=JAVA21_HOME
```

Then set `JAVA21_HOME` to point to the JDK 21 installation directory. This property **adds** a JDK source for Gradle to search; it does not replace the `java.toolchain.languageVersion` definition in the project.

## 7. Java 21 smoke test code to catch misconfigurations

Once the toolchain is configured, do not just trust the build file. Use a class with **real Java 21 syntax** to verify the compiler, tests, and runtime.

Save **`Java21ToolchainSmoke.java`** under `src/main/java` in your Maven/Gradle project (if the project uses a named package, add a `package` declaration and place it in the matching directory). The example below requires no external dependencies:

```java
public class Java21ToolchainSmoke {
    sealed interface Result permits Ok, Error {}

    record Customer(String name) {}
    record Ok(Customer customer) implements Result {}
    record Error(int code) implements Result {}

    static String describe(Result result) {
        return switch (result) {
            case Ok(Customer(String name))
                    when name != null && !name.isBlank() ->
                    "OK:" + name;

            case Ok(var customer) ->
                    "OK_NO_NAME";

            case Error(int code) when code >= 500 ->
                    "SERVER_ERROR";

            case Error(int code) ->
                    "ERROR:" + code;

            case null -> "MISSING";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Ok(new Customer("Ada"))));
        System.out.println(describe(
                new Ok(new Customer(" "))));
        System.out.println(describe(new Ok(null)));
        System.out.println(describe(new Error(503)));
        System.out.println(describe(new Error(404)));
        System.out.println(describe(null));
    }
}
```

Compile directly with JDK 21 or a newer JDK that supports `--release 21`:

```bash
javac --release 21 Java21ToolchainSmoke.java
java Java21ToolchainSmoke
```

**Exact stdout:**

```text
OK:Ada
OK_NO_NAME
OK_NO_NAME
SERVER_ERROR
ERROR:404
MISSING
```

This sample code was executed with JDK 24 JShell under Java 21 syntax, producing the six lines above. It uses:

- A **sealed interface** to define the `Result` set.
- **Nested record patterns** `Ok(Customer(String name))`.
- **`when` guards**.
- A **specific fallback** `Ok(var customer)` to handle a null customer or blank name.
- **`case null`** at the selector level.
- An **exhaustive switch expression**, requiring no `default` because all `Result` variants are handled.

One thing worth verifying in a real environment: `case Ok(Customer(String name))` **does not match** when `Customer` itself is null, whereas `case Ok(var customer)` still catches `Ok(null)`. Keeping this fallback branch prevents runtime errors from an unmatched nested record pattern.

### 7.1. Checking the class-file version

When code is compiled with `--release 21`, the main class file has **major version 65**. Inspect it using JDK tools:

```bash
javap -verbose Java21ToolchainSmoke
```

The output includes:

```text
major version: 65
```

This command assumes you are in the directory containing the class file; for Maven, compiled classes are typically in `target/classes`, and for Gradle in `build/classes/java/main`. When inspecting a JAR, pass the appropriate classpath to `javap -classpath ...`. `javap` must be from a JDK new enough to read the class file.

**Do not confuse:** class-file 65 indicates Java 21 bytecode; it does not guarantee the application has been tested on Java 21, nor does it prove all dependencies run on JVM 21.

### 7.2. Why is this demo stronger than a "Hello World"?

A Java 8 `Hello World` compiles under many compiler levels, so it fails to catch an IDE or CI accidentally using Java 17. A class with `switch` type patterns and `when` will **not compile as final Java 17 source**; if a pipeline lacks a Java 21 toolchain, the error usually surfaces immediately.

Still, a smoke test is a **quick sanity check**, not a substitute for unit/integration tests covering exceptions, nullable nested records, sealed exhaustive switches, domain logic, and dependency compatibility.

## 8. IDE: syncing Project SDK and build toolchain

Whether using IntelliJ IDEA, Eclipse, or VS Code, keep three settings distinct:

- **Project SDK/JDK**: used by the IDE for code analysis, autocomplete, and its internal compiler.
- **Language level / source level**: whether the IDE accepts Java 21 syntax.
- **Build tool settings**: Maven/Gradle can use their own JDK. Configuration in `pom.xml` or `build.gradle(.kts)` should be the version-controlled source of truth.

Verification steps:

1. Ensure the IDE has a **JDK 21** registered and Java 21 language level enabled for the relevant module.
2. If using Maven, check the **Maven Runner JRE** and project import settings; it may differ from the Project SDK. Even if the POM uses Maven Toolchains, verify which compiler JDK is actually selected.
3. If using Gradle, check the **Gradle JVM** (the JVM running the Gradle daemon) and the `java { ... }` toolchain. Do not treat a single Gradle JVM dropdown as proof that every `JavaCompile` uses the right JDK.
4. **Reimport/sync** the project after editing build files. If the IDE still reports `patterns in switch are not supported`, check the source language level instead of just restarting the IDE.
5. Do not tweak IDE settings manually while neglecting to update POM/Gradle: teammates and CI will lose that configuration.

**Avoid toggling preview arbitrarily.** When code only uses finalized Java 21 pattern switch/record patterns, neither the IDE nor the build needs `--enable-preview`. If the IDE prompts for preview, the project may be set to an older source level or the code may be using a different preview feature.

## 9. CI: GitHub Actions locking Java 21

CI should prove the build environment is **reproducible** without depending on whatever JDK happens to be on a developer's machine.

Maven workflow example (placed at `.github/workflows/java21.yml`):

```yaml
name: Java 21 Verify

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Check Java
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Build and test
        run: ./mvnw -B -ntp clean verify
```

This workflow snippet assumes the repository **already has an executable Maven Wrapper `mvnw`** and the POM configuration from the earlier section. If the project has no wrapper, you can use `mvn` available on the runner or generate/commit the wrapper through your team's standard process.

The workflow uses `actions/setup-java@v6` as the latest stable action generation at the time of writing; if using self-hosted runners, verify that the GitHub Actions Runner version is compatible with the actions v6 Node runtime. GitHub-hosted runners are updated without requiring manual maintenance. If the project pins action commit SHAs for supply-chain security, continue using the team-approved SHAs instead of switching to tag names.

**Gradle variant:** replace `cache: maven` with `cache: gradle`, and run:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --no-daemon clean test
```

In Gradle CI, use a version-locked **Gradle Wrapper**, and configure the Java 21 Gradle JVM/toolchain as in Section 6. If tests require JDK 21, verify that the Gradle test task uses that toolchain.

### 9.1. What should CI verify?

- `java -version` and `javac -version` to check PATH/JAVA_HOME on the runner.
- `mvn -version` or `./gradlew --version` to see the build tool's JVM.
- Maven Toolchains/Gradle `javaToolchains` to see available JDKs and the JDK actually used for tasks.
- Compilation of classes using **pattern switch + record patterns**, not just older Java classes.
- Unit/integration tests on Java 21.
- The final artifact (JAR, class files, container image) actually running on JVM 21.
- Dependency caching speeds up builds; it is **not** proof that the JDK version is right.

You can add a job running another JDK version to test compatibility, but only when that is an actual support target. **Do not** run a Java 21 JAR on JVM 17 and treat the failure as a flaky test.

## 10. Docker and execution runtime

The build container and runtime container are two separate environments. A Java 21 project needs both to stay consistent:

```dockerfile
# Multi-stage structure example; adjust to fit your project.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -ntp clean package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This is a **Dockerfile template**, not a standalone build: it requires `mvnw` in the repo, a POM configured to package an **executable JAR**, and an actual output named `target/app.jar`. If Maven produces a JAR with a different name, update the `COPY` path. For production services, apply your team's policies for pinning image digests, security updates, and base image governance.

**Note:** the build stage needs a **JDK** because it includes the compiler; the runtime stage can use a **Java 21 JRE** if the application does not need compilation tools at runtime. A Java 17 runtime will not run Java 21 classes with **major version 65**.

A good CI pipeline should test the final image directly under realistic conditions, because a JAR running on the host does not by itself prove the Docker image contains the right runtime.

## 11. Common build errors and how to fix them

| Symptom | Common cause | How to diagnose and fix |
| --- | --- | --- |
| `release version 21 not supported` or `invalid target release: 21` | `javac` compiler is too old | Check `javac -version`, Maven/Gradle toolchain; select JDK 21+ |
| `patterns in switch statements are a preview feature` | Compiler/source level is Java 17–20 or an old preview config | If targeting final Java 21, upgrade JDK and set `release=21`; do not enable preview to mask misconfiguration |
| `No matching toolchain` (Maven) | No JDK matching the criteria was found | Check `toolchains.xml`/discovery, `jdkHome`, version range, vendor |
| `No matching toolchains found for requested specification` (Gradle) | Gradle could not find JDK 21 or resolver is not configured | Run `./gradlew -q javaToolchains`; install JDK 21 or configure provisioning |
| `Unsupported class file major version 65` during build | Gradle/Groovy/ASM/plugin is too old to read Java 21 bytecode | Upgrade Gradle Wrapper and compatible plugins |
| `UnsupportedClassVersionError` when running JAR | Runtime JVM is lower than the class-file target | Check `java -version` on the actual machine/container; run on JVM 21+ |
| IDE flags `case Type variable`, while CLI build succeeds | IDE Project SDK/language level is set to an older version | Sync project, set module language level to 21, check plugin/IDE version |
| Build uses Java 24 APIs, but fails on Java 21 production | Only `-source`/`-target` 21 was set using a newer JDK | Use `--release 21`, check dependencies and runtime |
| Builds on one machine, missing JDK on another | Different `JAVA_HOME`/toolchain discovery, missing declared config | Pin toolchain in project; document JDK provisioning; use wrapper and CI |
| Tests fail even though compilation succeeds | Different test JVM, non-toolchain-aware test plugin, or incompatible dependency | Check Surefire/Gradle Test task, plugin/test dependencies, and actual test JVM |
| Enabling `--enable-preview` still gives syntax errors | Preview feature does not belong to that release/JDK or syntax changed | Confirm target release; use final Java 21 syntax for pattern switch |

**Two errors often conflated:**

- `Unsupported class file major version 65` can come from a **build tool/plugin** unable to read Java 21 bytecode, not necessarily the production JVM refusing to run the app.
- `UnsupportedClassVersionError` happens when the runtime JVM does not support the class-file version; for example, Java 17 only supports up to major 61, whereas Java 21 is major 65.

Read the **stack trace and failure phase**: IDE import, compile, test, package, or startup. Do not "fix" it by downgrading every `target` to 17 if the source genuinely uses Java 21 pattern matching.

## 12. Configuring release in multi-module projects

A repository may contain both legacy Java 17 modules and new Java 21 modules:

- Java 17 modules need `--release 17`, an appropriate compiler/JDK, and must not import Java 21 APIs.
- Java 21 modules need `--release 21` and plugins that handle Java 21 source/bytecode.
- If a Java 17 module **depends on a Java 21 class**, redesign the dependency boundary; a module running on JVM 17 cannot load Java 21 class files.
- When compiling Java 17 source with JDK 21, `--release 17` restricts Java SE 17 APIs, but you must also verify that **external library dependencies** have compatible bytecode.
- Do not set `release=21` in a parent POM if child modules still need to emit Java 17 bytecode without intentional overrides.

In Maven, `maven.compiler.release` can be declared per module or via profiles, though profiles should not subtly alter the build environment in hard-to-spot ways. In Gradle, each subproject can configure its own `java.toolchain` and `options.release`. Tests and cross-module dependencies must reflect the actual **runtime matrix to support**.

**Principle:** the Java version in build files is a **support contract**, not a knob just to make the build green on your current machine.

## 13. Pre-merge checklist for Java 21 configuration

- [ ] JDK **21** is installed and `java -version` / `javac -version` are valid locally or via toolchain discovery.
- [ ] Maven `maven.compiler.release=21` or Gradle `options.release=21` is explicitly set.
- [ ] Maven Toolchains Plugin or Gradle `java.toolchain.languageVersion=21` selects the right JDK, not just changing `JAVA_HOME`.
- [ ] Gradle Wrapper is compatible with the **JVM running Gradle** (at least 8.5 if the daemon runs on JDK 21).
- [ ] Compiler/test/Javadoc/codegen plugins are compatible with Java 21.
- [ ] IDE has synced the JDK, language level, and build tool version; CI does not rely on IDE settings.
- [ ] CI installs JDK 21, logs versions, and runs unit/integration tests.
- [ ] Actual runtime/container uses Java 21+ and the artifact has been verified to have **class-file major 65**.
- [ ] Final Java 21 pattern switch/record patterns **do not depend on `--enable-preview`**.
- [ ] A Java 21 smoke test exists covering `case Type`, `when`, record patterns, null, and sealed exhaustiveness.
- [ ] API/runtime targets of modules that still need Java 17 support have not been accidentally changed.
- [ ] Builds use Maven/Gradle Wrapper and a dependency/plugin version pinning policy for team reproducibility.

**Conclusion:** Properly configuring a Java 21 toolchain is more than picking "Project SDK = 21". Declare the **build JDK** (Maven Toolchains/Gradle Java Toolchains), the **language + API target** (`--release 21`), and the **test and production JVMs**, then verify with a class containing a **real Java 21 pattern switch**. This keeps JEP 440/441 code building consistently across developer machines, IDEs, CI, and containers while catching incompatible toolchains, plugins, and runtimes early.

### References

- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- Apache Maven Compiler Plugin — Setting --release: https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- Apache Maven Toolchains Plugin — JDK Discovery: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven Surefire — Test JVM toolchain: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo
- Gradle — Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Java Compatibility Matrix: https://docs.gradle.org/current/userguide/compatibility.html
- GitHub Actions — setup-java: https://github.com/actions/setup-java
