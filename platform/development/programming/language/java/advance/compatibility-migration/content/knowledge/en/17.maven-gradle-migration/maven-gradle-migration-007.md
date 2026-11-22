# Configuring the JVM for Unit Tests, Integration Tests, and JavaExec Tasks

In a Java project, `mvn test` or `./gradlew test` may finish successfully without any guarantee that the tests actually ran on the exact JDK the product must support. One reason is that the **JVM running the build tool**, the **JDK used to compile**, and the **JVM executing tests or the application** do not have to be the same Java installation.

This becomes especially critical when migrating from an older JDK to a newer JDK. A team might build using JDK 21 yet need to verify artifacts on Java 17; unit tests might require a small heap and a fixed timezone, while integration tests require separate environment variables; a `JavaExec` task might need to run on Java 21 rather than the JVM hosting Gradle. Changing only `JAVA_HOME` or setting `--release` can easily produce untrustworthy test results.

This lesson explains the JVM layers in Maven and Gradle, how to select JDKs for unit tests, integration tests, and Java execution tasks, how to pass JVM arguments, system properties, and environment variables, and a workflow to verify the actual runtime on developer machines and in CI.

## 1. One Project Can Use Multiple JVMs

Picture a pipeline:

```text
                      CI agent / developer shell
                                 |
                     +-----------+-----------+
                     |                       |
                  Maven JVM              Gradle JVM
                     |                       |
             Compiler / toolchains    Compiler / toolchains
                     |                       |
               Test JVM fork            Test JVM fork
                     |                       |
                Integration              Integration
                 Test JVM                 Test JVM
                                             |
                                      JavaExec JVM
```

This is a conceptual model; not every build always spawns each separate process. Maven Surefire/Failsafe supports forked or non-forked modes; Gradle `Test` and `JavaExec` normally run Java code in separate JVM processes, whereas certain other tasks execute logic directly inside Gradle's JVM.

Roles to distinguish:

| Role | Example | Question to verify |
|---|---|---|
| **Build-tool JVM** | JVM running Maven or the Gradle Daemon. | Which JDK launched Maven/Gradle? |
| **Compiler JDK** | `javac`, toolchain, or compiler plugin. | Which compiler is compiling class files? |
| **Unit-test JVM** | Forked process of Surefire or Gradle `Test`. | Are unit tests truly running on Java 17 or 21? |
| **Integration-test JVM** | Fork of Failsafe or custom Gradle `Test`. | Which JDK, flags, credentials, and endpoints do integration tests use? |
| **Application JVM** | Process running the service in production. | Does the artifact actually run on the committed runtime baseline? |
| **JavaExec JVM** | `JavaExec` task running a main class from Gradle. | Which launcher runs the business/data task? |

**Rule:** Knowing the compiler JDK does not mean knowing the runtime execution JDK. Knowing the JDK running Maven/Gradle also does not mean every test and `JavaExec` task uses that JDK.

## 2. Three Configuration Layers: Executable, JVM Options, and Application Options

Many errors happen from confusing these three kinds of parameters.

### 2.1. Choosing the Java Executable or Launcher

Example:

```text
C:/jdks/jdk-17/bin/java.exe
C:/jdks/jdk-21/bin/java.exe
```

This decides **which JDK runs the process**. In Gradle, prefer Java Toolchains and `javaLauncher`; in Maven, use Toolchains or the plugin's dedicated JVM setting, depending on the goal.

### 2.2. Choosing JVM Arguments

Example:

```bash
-Xms128m
-Xmx512m
-Duser.timezone=UTC
--add-opens=java.base/java.lang=ALL-UNNAMED
```

These are JVM flags and must be delivered to the **exact process running the code**. If tests run inside a forked JVM, adding `-Xmx512m` to the Maven/Gradle process itself does not necessarily affect that fork.

Flags such as `--add-opens` are workarounds opening packages for reflection; use them only when strictly necessary and plan to eliminate dependencies on JDK internals.

### 2.3. Choosing Application Arguments

Example:

```bash
--config=config/test.yml
--dry-run
--limit=100
```

These strings are passed to `main(String[] args)`, not as JVM options. With Gradle `JavaExec`, use `args(...)` for these; use `jvmArgs(...)` for JVM flags.

### 2.4. System Properties Differ from Environment Variables

```java
String profile = System.getProperty("app.profile");
String serviceUrl = System.getenv("SERVICE_URL");
```

They come from two distinct configuration namespaces:

- System property: typically set via `-Dapp.profile=test`, Gradle `systemProperty(...)`, or Maven plugin settings.
- Environment variable: inherited from the parent process or configured via `environment(...)` / `environmentVariables`.

Do not assume `-Dapp.profile=test` creates `APP_PROFILE`; nor assume every environment variable automatically turns into a system property.

## 3. Printing the Actual Runtime from Inside Tests

To confirm which JDK a test is using, the most direct approach is printing or asserting values **inside the JVM running the test**:

```java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class RuntimeDiagnostics {
    public static void print() {
        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("java.vendor = "
                + System.getProperty("java.vendor"));
        System.out.println("java.home = "
                + System.getProperty("java.home"));
        System.out.println("java.vm.name = "
                + System.getProperty("java.vm.name"));
        System.out.println("java.class.version = "
                + System.getProperty("java.class.version"));
        System.out.println("file.encoding = "
                + System.getProperty("file.encoding"));
        System.out.println("default charset = "
                + Charset.defaultCharset());
        System.out.println("timezone = " + ZoneId.systemDefault());
        System.out.println("locale = " + Locale.getDefault());
        System.out.println("profile = "
                + System.getProperty("app.profile"));
        System.out.println("service url = "
                + System.getenv("SERVICE_URL"));
    }
}
```

With JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class RuntimeTest {
    @Test
    void usesJava17() {
        RuntimeDiagnostics.print();

        assertEquals(17, Runtime.version().feature());
    }
}
```

Assert Java 17 only if this test suite is **genuinely configured to run on Java 17**. If the goal is multi-JDK testing, use an appropriate compatibility constraint or parameterization instead.

A single `java -version` output outside in the terminal does not replace checking inside the test process. What matters is `System.getProperty("java.home")` and `Runtime.version()` inside the exact process.

## 4. Maven: The JDK Running Maven Differs from the JVM Running Surefire

Maven starts with the Java executable chosen by the Maven launcher/environment. Inspect with:

```bash
mvn -version
```

The output shows the Maven version, Java version, Java home, and OS. However, when Maven Surefire Plugin forks a separate JVM, `mvn -version` is **not sufficient** to verify the unit test JDK.

Configuration sources serve different roles:

| Setting | Primary Effect |
|---|---|
| `JAVA_HOME` / PATH | Affects how the launcher selects the JVM starting Maven, depending on environment. |
| `MAVEN_OPTS` | JVM arguments for the Maven process; not a reliable way to configure every test fork individually. |
| `.mvn/jvm.config` | JVM arguments for the Maven process via the Maven launcher; should not be treated as Surefire-specific settings. |
| Maven Compiler Plugin | Controls compilation and can select a JDK/toolchain. |
| Maven Surefire Plugin | Executes unit tests according to fork settings, JVM, `argLine`, and properties. |
| Maven Failsafe Plugin | Executes integration tests in the `integration-test` and `verify` lifecycle phases. |
| Maven Toolchains | Lets supporting plugins select a JDK via metadata instead of relying solely on Maven's JVM. |

### 4.1. `--release` Does Not Pick the Test JVM

Example:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

This property instructs compilation to emit code compatible with release 17 when Maven Compiler Plugin supports the setting. It **does not ensure** that unit tests, integration tests, or the application run on Java 17.

If Maven runs on Java 21 and Surefire has no dedicated toolchain selected, tests can still run inside Java 21 even though the code was compiled for Java 17.

## 5. Maven Surefire: JVM for Unit Tests

Maven Surefire Plugin is commonly used to execute unit tests in Maven's `test` phase. Sample configuration:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <argLine>-Xmx512m -Duser.timezone=UTC</argLine>
        <systemPropertyVariables>
          <app.profile>unit-test</app.profile>
        </systemPropertyVariables>
        <environmentVariables>
          <SERVICE_URL>http://localhost:18080</SERVICE_URL>
        </environmentVariables>
      </configuration>
    </plugin>
  </plugins>
</build>
```

The plugin version here is an example illustrating syntax, not a claim that it is the latest version. In real use, pick a version supported by your project and target JDK.

Explanation:

- `forkCount=1`: allows at most one forked JVM to run tests at a time for that module.
- `reuseForks=true`: reuses forks according to Surefire's policy.
- `argLine`: passes JVM options to the **forked JVM**.
- `systemPropertyVariables`: sets system properties in the test process.
- `environmentVariables`: configures environment variables for the forked process.

`forkCount` can accept values such as `1C` depending on plugin support to scale forks by CPU cores. Increase fork count only after verifying test, database, port, and CI resource isolation.

### 5.1. Should You Set `forkCount=0`?

With `forkCount=0`, Surefire runs tests directly inside Maven's JVM instead of forking a separate JVM. You lose process isolation, and several fork-only settings (such as choosing an executable or `argLine`) cease to behave as expected.

During migration, prefer separate forked test JVMs when you need to:

- Verify a JDK runtime distinct from Maven's JVM.
- Isolate system properties or classloaders.
- Apply test-specific `--add-opens` or heap flags.
- Prevent leaks, shutdown hooks, or crashes from affecting the Maven process.

Do not set `forkCount=0` merely to work around launch errors; investigate why the JVM/toolchain configuration failed.

### 5.2. Selecting a Fork JDK with `jdkToolchain`

Surefire supports selecting a JDK toolchain for forks:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.5.2</version>
  <configuration>
    <forkCount>1</forkCount>
    <jdkToolchain>
      <version>17</version>
    </jdkToolchain>
    <argLine>-Xmx512m</argLine>
  </configuration>
</plugin>
```

The prerequisite is that Maven can locate a matching toolchain, such as via `~/.m2/toolchains.xml` or toolchain discovery supported by the chosen plugin/toolchain version. Selecting the JDK via toolchains avoids depending on the shell's `JAVA_HOME`.

If an explicit JVM executable is also set via plugin configuration, check the precedence rules of your exact Surefire version; never configure two conflicting JVM selection sources and guess the outcome.

### 5.3. Specifying a JVM Executable with `jvm`

Another option when you strictly want to pin the executable path:

```xml
<configuration>
  <forkCount>1</forkCount>
  <jvm>/opt/jdks/jdk-17/bin/java</jvm>
</configuration>
```

The path above is a Linux example. This approach may fit a fixed environment, yet is brittle across Windows, Linux, and diverse CI agents. Generally prefer Toolchains when portability is needed.

## 6. Maven Failsafe: JVM for Integration Tests

Maven Failsafe Plugin is designed for integration tests and normally binds to two phases:

- `integration-test`: runs integration tests and records results.
- `verify`: evaluates results and fails the build if tests failed.

Critically, run through `verify`, e.g., `mvn verify`. Calling only `mvn integration-test` may skip full result verification in the way users expect.

### 6.1. Configuring Failsafe

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.5.2</version>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <jdkToolchain>
          <version>21</version>
        </jdkToolchain>
        <argLine>-Xmx1g -Duser.timezone=UTC</argLine>
        <systemPropertyVariables>
          <app.profile>integration-test</app.profile>
        </systemPropertyVariables>
        <environmentVariables>
          <SERVICE_URL>http://localhost:19090</SERVICE_URL>
        </environmentVariables>
      </configuration>
    </plugin>
  </plugins>
</build>
```

This example intentionally picks Java 21 for the integration-test fork to illustrate how unit tests and integration tests can run on two different JDKs. Not every project needs this split; it is meaningful only when there is a specific testing goal.

Under Failsafe conventions, names like `*IT.java`, `IT*.java`, or `*ITCase.java` are recognized as integration tests. This can be customized with `includes` and `excludes`. Ensure your project naming conventions align with the plugin to avoid a "green build because zero tests were found."

### 6.2. Do Not Let Unit Tests and Integration Tests Unintentionally Share Configuration

Unit tests typically need:

- Fast execution, isolated from networks and databases.
- In-memory fixtures or test doubles.
- Stable configuration with minimal environmental coupling.

Integration tests typically need:

- Real databases/services or test containers.
- Test-environment variables and credentials.
- Larger timeouts; possibly more memory.
- Resource cleanup after each test or suite.

Define a clear policy: what is shared (e.g., timezone, encoding) and what stays separate (service endpoints, credentials, heap, parallelism). Never put real secrets inside `pom.xml`; supply them via secret managers/CI environments and avoid printing them into logs.

### 6.3. Separating Maven Lifecycle from Service Startup Timing

If integration tests expect a running server, ensure the service/database starts in the appropriate phase and tears down even when tests fail. Do not merely launch a background shell process without readiness checks and cleanup.

Some projects use container orchestration, Testcontainers, or specialized Maven plugins. Exact mechanisms vary by architecture, yet the goal is always deterministic test inputs and endpoints without accidentally hitting production.

## 7. Maven Toolchains: Declaring Multiple JDKs

Maven Toolchains allow supporting plugins to use a different JDK from the one that started Maven. Example `~/.m2/toolchains.xml` structure:

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
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-21</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
```

Paths are illustrative. In real projects, the toolchains file must reflect actual JDK installations on each machine or runner. Some newer Maven Toolchains Plugin releases offer different discovery capabilities; confirm your plugin and JDK discovery approach in your organization.

In `pom.xml`, Maven Toolchains Plugin can select a toolchain for integrating plugins. Example:

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

This configuration specifies the **default toolchain selected for compatible plugins**; Surefire and Failsafe can specify their own `jdkToolchain` to pick another JDK if supported by the plugin. Thus, when seeing three versions in a build, identify which plugin uses which version rather than assuming the compiler toolchain is used by all tests.

**Key limitation:** A Maven plugin does not automatically honor Toolchains merely because a `toolchains.xml` file exists. The plugin must explicitly support it, or an executable must be configured directly.

## 8. Maven: Distinguishing `exec:java` and `exec:exec`

In Maven, the Apache Exec Maven Plugin offers two goals frequently confused:

| Goal | Execution model | Picks an independent JVM process? |
|---|---|---|
| `exec:java` | Runs the main class inside Maven's JVM, using the plugin's classloader/thread handling. | Does not fork a new Java JVM the way `exec:exec` does. |
| `exec:exec` | Runs an external executable specified by the plugin. | Can run a specific `java` executable to create a dedicated JVM. |

This resembles Gradle's `JavaExec` yet is **not identical**. In Gradle, `JavaExec` is designed to launch a separate Java process, whereas Maven `exec:java` runs inside Maven's JVM.

### 8.1. `exec:java` and Maven JVM Impact

```xml
<plugin>
  <groupId>org.codehaus.mojo</groupId>
  <artifactId>exec-maven-plugin</artifactId>
  <version>3.5.1</version>
  <configuration>
    <mainClass>com.example.tools.MigrationTool</mainClass>
  </configuration>
</plugin>
```

When invoking:

```bash
mvn exec:java
```

the main class runs on Maven's JVM. JVM arguments such as heap size or `--add-opens` must be given to Maven's JVM at startup; `exec:java` cannot be treated as a fully isolated JVM fork with its own runtime flags.

To run a tool needing another JDK, or to separate memory/flags from Maven, launch an external process.

### 8.2. `exec:exec` Launching a Separate `java`

Example configuring an external Java invocation:

```xml
<plugin>
  <groupId>org.codehaus.mojo</groupId>
  <artifactId>exec-maven-plugin</artifactId>
  <version>3.5.1</version>
  <configuration>
    <executable>${env.MIGRATION_JAVA_HOME}/bin/java</executable>
    <arguments>
      <argument>-Xmx512m</argument>
      <argument>-Dapp.mode=dry-run</argument>
      <argument>-classpath</argument>
      <classpath/>
      <argument>com.example.tools.MigrationTool</argument>
      <argument>--dry-run</argument>
    </arguments>
  </configuration>
</plugin>
```

`MIGRATION_JAVA_HOME` is an example environment variable pointing to the tool's JDK directory. `<classpath/>` is a special Exec Plugin element letting the plugin assemble the appropriate project classpath. In a real build, specify classpath scope and ensure `MigrationTool` is compiled before calling the goal.

When launching an external Java process, parameter ordering is:

```text
java [JVM options] -classpath [classpath] MainClass [application args]
```

If the project is modular, you may need `--module-path` and `--module module/mainClass` instead of classpath. Do not assume the plugin automatically constructs the right module path from a classpath configuration.

## 9. Gradle: The JVM Running Gradle Differs from Java Toolchains

Gradle can run inside the Gradle Daemon JVM, while Java compilation/test/execution tasks can use different JDKs via Java Toolchains.

Check Gradle:

```bash
./gradlew --version
```

The output reports the Gradle version and Gradle's related JVM info. On newer Gradle releases, "Launcher JVM" and "Daemon JVM" reporting may differ, so read the full output. Even then, this command **does not confirm the JVM of each test task**.

### 9.1. Ways to Choose JVMs in Gradle

| Mechanism | Primarily Affects |
|---|---|
| `JAVA_HOME` / PATH | How the Gradle wrapper/client is launched, depending on environment. |
| `org.gradle.java.home` | JDK running the Gradle Daemon in supported setups. |
| Gradle Daemon JVM criteria | Daemon JVM selection criteria in supporting Gradle versions. |
| `java.toolchain` | Compiler, launcher, and toolchain used by integrating Java tasks. |
| `Test.javaLauncher` | JDK running the forked test process of a `Test` task. |
| `JavaExec.javaLauncher` | JDK running the Java process created by a `JavaExec` task. |
| `Test.jvmArgs` / `JavaExec.jvmArgs` | JVM flags for the corresponding task. |

Your Gradle version must be compatible with the JDK running the Gradle Daemon. **You cannot pick an arbitrary JDK solely because a toolchain target supports it**; check the Gradle Java compatibility matrix for your exact Gradle release.

### 9.2. Setting Up a Toolchain for a Java Project

Example `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

This selects JDK 17 as the project's default Java toolchain. The compiler and toolchain-aware Java tasks generally inherit this version unless overridden.

When you need to constrain the target API while compiling on a newer JDK:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

`options.release` controls language/bytecode/API targets via `javac --release`; it **does not choose the JVM executing unit tests or JavaExec**.

## 10. Gradle `Test`: JVM for Unit Tests

Kotlin DSL configuration example:

```kotlin
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    java
}

tasks.test {
    useJUnitPlatform()

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )

    jvmArgs("-Xmx512m")
    systemProperty("app.profile", "unit-test")
    systemProperty("user.timezone", "UTC")
    environment("SERVICE_URL", "http://localhost:18080")

    maxParallelForks = 1
}
```

Details:

- `useJUnitPlatform()`: selects JUnit Platform for tests written with JUnit 5 or compatible frameworks; the project must declare matching JUnit dependencies/engine.
- `javaLauncher`: selects the Java executable for the `Test` task's fork.
- `jvmArgs(...)`: JVM options.
- `systemProperty(...)`: system properties for the test process.
- `environment(...)`: environment variables for the test process.
- `maxParallelForks`: maximum number of test forks the task may run in parallel.

Do not also add `-Dapp.profile=unit-test` to `jvmArgs` if you already set `systemProperty("app.profile", "unit-test")`. Both work, yet duplicating them easily causes conflicting configuration; choose one style consistently.

### 10.1. Configuring All Tasks of Type `Test`

When a project has multiple `Test` tasks:

```kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("-Xmx768m")
    systemProperty("user.timezone", "UTC")
}
```

This applies to every `Test` task Gradle registers in the project, including custom integration-test tasks of type `Test`. Use it for shared baseline settings; if specific tasks require different runtime targets, override intentionally per task.

### 10.2. `forkEvery` and State Isolation

Gradle supports `forkEvery` to control how many test classes run before replacing the fork with a fresh one. Example:

```kotlin
tasks.test {
    forkEvery = 100
    maxParallelForks = 2
}
```

This helps limit static state or native resource leaks in large suites, at the cost of extra JVM startup overhead. It does not replace writing independent tests and cleaning up resources properly.

When setting `maxParallelForks=2`, ensure databases, ports, file paths, and mock servers support concurrent usage. Two JVMs can still overwrite the same external resource if tests are not isolated.

## 11. Gradle: Creating a Dedicated Integration-Test Task

Gradle can organize integration tests using a dedicated source set/task or the JVM Test Suites plugin. Below is a direct declaration showing **classpath** and **JVM launcher** explicitly.

### 11.1. Project Structure

```text
src/
├── main/java/...
├── test/java/...                 # unit tests
└── integrationTest/java/...      # integration tests
```

### 11.2. Creating the Source Set and Configuring Dependencies

Example `build.gradle.kts`:

```kotlin
plugins {
    java
}

val integrationTestSourceSet = sourceSets.create("integrationTest") {
    java.srcDir("src/integrationTest/java")
    resources.srcDir("src/integrationTest/resources")

    compileClasspath += sourceSets["main"].output
    runtimeClasspath += output + compileClasspath
}

configurations[
    integrationTestSourceSet.implementationConfigurationName
].extendsFrom(configurations["testImplementation"])

configurations[
    integrationTestSourceSet.runtimeOnlyConfigurationName
].extendsFrom(configurations["testRuntimeOnly"])
```

This creates a separate source set while letting integration tests reuse base dependencies from unit tests. In real projects, add integration-test-only dependencies or tailor the classpath to your architecture. Avoid adding `sourceSets["test"].output` if you want to keep both suites' helper classes/fixtures independent.

### 11.3. Creating the `integrationTest` Task

Continuing in the same `build.gradle.kts`:

```kotlin
val integrationTestTask = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = integrationTestSourceSet.output.classesDirs
    classpath = integrationTestSourceSet.runtimeClasspath

    useJUnitPlatform()

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )

    jvmArgs("-Xmx1g")
    systemProperty("app.profile", "integration-test")
    environment("SERVICE_URL", "http://localhost:19090")

    shouldRunAfter(tasks.test)
}

tasks.named("check") {
    dependsOn(integrationTestTask)
}
```

This example picks Java 21 for the integration-test process, whereas the unit test example picked Java 17. Real setups must ensure both JDKs are installed or toolchain provisioning is configured in Gradle.

`shouldRunAfter(tasks.test)` only specifies **ordering preference when both tasks are in the execution graph**; it does not create a task dependency. `check.dependsOn(integrationTestTask)` ensures integration tests execute when running `check`.

If integration tests require a live service at `localhost:19090`, provide service startup, readiness, and teardown automation. Setting an endpoint string alone does not launch the service.

### 11.4. JVM Test Suites

In Gradle versions supporting JVM Test Suites, an alternative is declaring suites via `testing { suites { ... } }`. This API conveniently wires standard Gradle test source sets and targets. Regardless of approach, focus on the JVM of the **resulting `Test` task**, because that is where Java test code runs.

Do not manually register an `integrationTest` task with the same name as one created by JVM Test Suites without understanding the task graph; doing so can cause duplicates or conflicts.

## 12. Gradle `JavaExec`: JVM for Standalone Java Programs

`JavaExec` is a Gradle task type for launching a Java application in a **new JVM process**. Common uses include:

- Running a data migration tool.
- Executing import/export commands or batch jobs.
- Running code generators or command-line applications.
- Running a main class for smoke tests.
- Executing helper tasks using the project's runtime classpath.

Example:

```kotlin
tasks.register<JavaExec>("runMigration") {
    group = "application"
    description = "Runs the data migration command."

    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.example.tools.DataMigration")

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )

    jvmArgs("-Xmx512m")
    systemProperty("migration.mode", "dry-run")
    environment("APP_ENV", "staging")
    args("--dry-run", "--limit=100")
}
```

Command:

```bash
./gradlew runMigration
```

Notice the two completely distinct settings:

- `jvmArgs("-Xmx512m")` configures the JVM launched by `JavaExec`.
- `args("--dry-run", "--limit=100")` is passed into `DataMigration.main(String[] args)`.

`javaLauncher` selects the desired JDK without tying execution to the Gradle Daemon JVM. If the task must use the module path rather than classpath, configure the modular task/application accordingly and check how plugins/Java tasks support JPMS.

### 12.1. Verifying Inside the Main Class

```java
package com.example.tools;

import java.util.Arrays;

public final class DataMigration {
    public static void main(String[] args) {
        System.out.println("Java: "
                + Runtime.version().feature());
        System.out.println("Java home: "
                + System.getProperty("java.home"));
        System.out.println("Mode: "
                + System.getProperty("migration.mode"));
        System.out.println("Environment: "
                + System.getenv("APP_ENV"));
        System.out.println("Arguments: "
                + Arrays.toString(args));
    }
}
```

When running the sample task, console output must report Java feature 21 if the right launcher and JDK 21 are available. Otherwise, verify that the task is configured in the right subproject, not overridden by another plugin, and using the intended Java executable.

## 13. Comparing Key Mechanisms: Maven vs. Gradle

| Need | Maven | Gradle |
|---|---|---|
| Build-tool JVM | `mvn -version`, launcher/`JAVA_HOME`, Maven options. | `./gradlew --version`, daemon JVM, JVM criteria. |
| Compile for Java 17 | Compiler Plugin `<release>17</release>` or matching property. | `options.release.set(17)`. |
| Pick unit-test JDK | Surefire `jdkToolchain`/`jvm` with forking. | `Test.javaLauncher`. |
| Unit-test JVM flags | Surefire `argLine`. | `Test.jvmArgs(...)`. |
| Unit-test system properties | Surefire `systemPropertyVariables`. | `Test.systemProperty(...)`. |
| Integration tests | Failsafe `integration-test` + `verify`. | Custom `Test` task or JVM Test Suite. |
| Pick integration-test JDK | Failsafe `jdkToolchain`/`jvm`. | `integrationTest.javaLauncher`. |
| Run Java main outside build JVM | Exec Maven Plugin `exec:exec` with `java` executable. | `JavaExec` with `javaLauncher`. |
| Run main inside build JVM | Exec Maven Plugin `exec:java`. | Certain tasks/plugins run code inside daemon; not equivalent to `JavaExec`. |
| Verify runtime | Print `java.home`/`Runtime.version()` from test/process. | Same, inside `Test`/`JavaExec` process. |

Do not confuse plugin names with the JVM itself. Simply using Maven or Gradle across two projects does not guarantee identical forking and runtime behavior.

## 14. Migration Scenario: Building on JDK 21, Testing on JDK 17

Suppose a library must support Java 17 while the team wants to build with a newer toolchain.

One layout:

```text
Maven / Gradle Daemon  -> JDK 21 (if supported by the build tool)
Compiler              -> JDK 21, --release 17
Unit-test runtime     -> JDK 17
Integration tests     -> JDK 17 + JDK 21 in CI matrix
Application runtime   -> Java 17 minimum
```

This verifies two guarantees:

1. The compiler emits no bytecode/API beyond Java 17 per `--release 17`.
2. Tests genuinely execute on Java 17, catching runtime issues that compilation cannot catch.

Even so, also check external dependencies: `--release 17` does not magically make a dependency JAR compiled for Java 21 compatible with Java 17.

### 14.1. Why Running Tests Only on Java 21 Is Insufficient

Classes using reflection, `ServiceLoader`, native libraries, class loading, or JDK-dependent behaviors can behave differently across JDKs. If tests run solely on Java 21, the library can still ship bugs that occur only on Java 17.

A CI matrix can test:

```text
Build artifact once (release 17)
          |
          +--> Test on JDK 17
          |
          +--> Test on JDK 21
```

Depending on product requirements, you can also build separately on each JDK, while explicitly stating the goal: checking compiler compatibility vs. runtime behavior.

## 15. Migration Scenario: Integration Tests Requiring a Newer JDK

Suppose integration tests use a test utility library requiring Java 21 while production code must run on Java 17.

You can configure:

```text
Production classes  -> target Java 17
Unit tests          -> Java 17
Integration tests   -> Java 21
```

Yet exercise caution: integration tests running on Java 21 **do not prove** production behavior has been verified on Java 17. If the product commits to a Java 17 runtime, at least one representative suite must still execute on Java 17—especially covering serialization, JDBC, reflection, TLS, and module access.

Additionally, test code compiled for Java 21 cannot execute on a Java 17 JVM. When two suites use separate source sets/toolchains, check the release target of **test classes** as well, not only main classes.

## 16. Why `JAVA_HOME` and `PATH` Easily Cause Confusion

On a machine with multiple JDKs:

```text
JAVA_HOME -> JDK 17
PATH      -> JDK 21/bin before other directories
```

How `java`, `javac`, the Maven launcher, and the Gradle wrapper choose a JVM may differ. For instance, a wrapper script may prioritize `JAVA_HOME`, whereas invoking `java -version` directly runs the first executable in `PATH`.

Checks worth running:

```bash
java -version
javac -version
mvn -version
./gradlew --version
```

On Linux/macOS:

```bash
which java
which javac
```

On Windows PowerShell:

```powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
```

Then confirm **inside the test/`JavaExec` process**. If toolchains are configured, changing `JAVA_HOME` may leave the launcher chosen by Gradle `Test` or Maven Surefire unchanged.

## 17. JVM Flags Affect Only the Process That Receives Them

Common option groups:

| Group | Example | Considerations |
|---|---|---|
| Heap | `-Xms128m -Xmx512m` | Test fork heap is separate from Gradle/Maven JVM heap. |
| GC | `-XX:+UseG1GC` | Supported GC flags and defaults vary across JDK versions. |
| System property | `-Duser.timezone=UTC` | Understand how it affects formatters/timezones in code. |
| Reflective access | `--add-opens=module/package=target` | Keep scope as narrow as possible and plan removal. |
| Export internal package | `--add-exports=module/package=target` | May be needed by legacy dependencies; not a stable API. |
| Assertions | `-ea` | Some tests/frameworks rely on assertions being enabled. |
| JVM logging | `-Xlog:gc*` | Unified logging syntax differs from old-JDK GC flags. |
| Charset | `-Dfile.encoding=UTF-8` | Does not replace explicit charsets in I/O calls. |
| Locale | `-Duser.language=en -Duser.country=US` | Use only when a fixed environment is needed; still test locale logic. |

Do not pass JVM flags unsupported by a target JDK into every test job. For instance, a flag available in JDK 21 may not exist in JDK 8, failing the build before tests even begin. When running a test matrix, configure flags per runtime and document why each flag exists.

### 17.1. `MAVEN_OPTS` and `org.gradle.jvmargs` Do Not Replace Test JVM Config

Example:

```text
MAVEN_OPTS=-Xmx2g
org.gradle.jvmargs=-Xmx2g
```

These primarily control the build tool's JVM. They are not a direct mechanism for setting heap sizes on individual test forks or `JavaExec` JVMs. In Gradle, `org.gradle.jvmargs` lives in `gradle.properties`; in Maven, `MAVEN_OPTS` is a launcher environment variable.

Giving `-Xmx2g` to the Gradle Daemon does not give Gradle `Test` a 2 GiB heap. To control test forks, explicitly set `Test.maxHeapSize` or `Test.jvmArgs`. Likewise, Surefire/Failsafe use the plugin's fork configuration.

## 18. Java Agents, Coverage, and `argLine`

In Maven, agents such as JaCoCo often inject `-javaagent:...` into the test JVM. If a coverage plugin generates an `argLine` property, carelessly overwriting `<argLine>...</argLine>` can silently drop the Java agent.

With Surefire, late property evaluation such as `@{argLine}` works in supported configs:

```xml
<configuration>
  <argLine>@{argLine} -Xmx512m</argLine>
</configuration>
```

When using this, verify that the property is initialized properly and assigned by the coverage plugin; otherwise, an unexpanded placeholder literal may reach the command line. Another option is naming a dedicated agent property and referencing it consistently from JaCoCo and Surefire.

In Gradle, the JaCoCo plugin attaches its agent to `Test` tasks via plugin integration. Verify the agent is attached to the **test fork** rather than only the Gradle Daemon, and confirm the agent supports the test JDK.

## 19. Environment Isolation and Secret Handling

Integration tests often need credentials, service URLs, and resource names. Never commit real secrets into `pom.xml`, `build.gradle.kts`, or command examples.

Guidelines:

- Pass secrets via a CI secret store or approved mechanism.
- Grant secrets only to tasks that need them, not the whole build process unnecessarily.
- Never print raw environment blocks or system properties containing secrets.
- Use dedicated test databases/schemas; prevent port/bucket name collisions across parallel jobs.
- Validate values like `SERVICE_URL` so they never point to production accidentally.
- Clean up test resources after job completion, even when tests fail.

### 19.1. Gradle Provider API for External Configuration

Example using a Gradle property as input:

```kotlin
tasks.named<Test>("integrationTest") {
    val endpoint = providers.gradleProperty("itServiceUrl")
        .orElse("http://localhost:19090")

    systemProperty("it.service.url", endpoint.get())
}
```

A default value only makes sense if the test environment actually hosts a service there. In strict CI, prefer requiring the property instead of falling back so misconfigurations fail fast.

### 19.2. Passing Maven System Properties via the Command Line

When overriding a property used in tests:

```bash
mvn verify -Dit.service.url=http://localhost:19090
```

Depending on Surefire/Failsafe configuration, Maven user properties may be forwarded into the test process by plugin rules. Under strict security policies, explicitly map properties via `systemPropertyVariables` or property configuration instead of relying solely on default forwarding behavior.

Paths, URLs, and values in examples are illustrative, not live endpoints.

## 20. Testing Across Multiple JDKs Without Uncontrolled Config Duplication

A common strategy:

```text
                      Shared source code
                             |
                    Build artifact (17)
                             |
         +-------------------+-------------------+
         |                                       |
      JDK 17                                  JDK 21
         |                                       |
  Unit + integration                         Unit + smoke
         |                                       |
         +-------------------+-------------------+
                             |
                         Compare
```

Every job does not have to run the exact same suite size. Heavy suites can target the minimum supported JDK while smoke/compatibility checks target newer JDKs, provided risks and coverage remain documented.

### 20.1. Differences Worth Testing Between JDKs

- Default charset and locale.
- Reflection/JPMS `opens` and `exports`.
- TLS truststores and security providers.
- Java serialization/JSON/XML and timezones.
- JDBC drivers, native libraries, and compression.
- GC, JVM flags, and memory behavior.
- `ServiceLoader`/automatic modules.
- Class file major versions and API availability.

Running the same built artifact across multiple runtimes uncovers runtime incompatibilities. To catch compiler or annotation processor behavioral changes across JDKs, also consider separate compilation jobs per toolchain.

## 21. Debugging When Unit Tests Pass Yet Integration Tests Fail

A typical scenario:

```text
Unit tests PASS on developer machine
Integration tests FAIL in CI
Error: UnsupportedClassVersionError
```

Steps:

1. Print `java.version` and `java.home` from both the unit-test JVM and the integration-test JVM.
2. Check class file major versions of test classes and dependencies.
3. Inspect Failsafe `jdkToolchain` or Gradle's integration-test `javaLauncher`.
4. Confirm CI has the required JDK version installed and discoverable.
5. Check whether an integration-test dependency requires a newer JDK than the runtime.

Do not only adjust `maven.compiler.release` or `options.release` for main sources; integration-test classes might compile under a different configuration, or a test library might be the culprit.

### 21.1. Class Not Found Because Classpaths Differ

If unit tests find a class while integration tests throw `ClassNotFoundException`:

- Maven: inspect test classpaths, scopes, exclusions, and dependency resolution in that module.
- Gradle: inspect `integrationTestSourceSet.runtimeClasspath`, `integrationTestImplementation`, and `integrationTestRuntimeOnly`.
- JPMS: inspect module paths, module names, and runtime module resolution.

Do not blindly dump the entire unit-test classpath into integration tests if doing so pulls in mock dependencies that distort the integration environment.

### 21.2. Tests Run on the Right JVM Yet Yield Different Results

When `java.version` proves the runtime matches yet output differs, compare:

- System properties and environment variables.
- Timezone, default charset, and locale.
- Service endpoints, database state, and fixtures.
- Parallelism, thread scheduling, and GC.
- Per-task JVM flags/agents.

Do not assume a JDK difference is the cause while tests run against different data or external configuration.

## 22. Common Error Messages

| Message / Symptom | Likely Cause | Resolution |
|---|---|---|
| `UnsupportedClassVersionError` | Test JVM is older than test or dependency bytecode. | Check test JVM's `java.home` and bytecode `major version`. |
| `NoClassDefFoundError` in fork | Missing runtime dependency or module. | Inspect classpath/module path and actual artifact. |
| `InaccessibleObjectException` | JPMS blocks reflection. | Upgrade library or pass narrowly scoped `--add-opens` to the right fork. |
| `The forked VM terminated without properly saying goodbye` | JVM crash, `System.exit`, OOM, or invalid agent/flag. | Inspect fork logs, dumps, heap, and crash report. |
| Unit tests use JDK 21 despite targeting 17 | Set only compiler release without picking runtime toolchain. | Configure Surefire/Gradle `Test` launcher. |
| Integration tests do not run | Wrong goal/phase or include patterns. | Run Maven `verify`, check Failsafe includes; inspect Gradle task graph. |
| `JavaExec` uses wrong JVM | Task inherits default/Daemon launcher instead of intended JDK. | Set `javaLauncher` and print version from main. |
| JVM unrecognized flag error | Flag removed/renamed in newer JDK. | Validate options against the fork's actual JDK. |
| Port/address already in use | Parallel test forks share the same port. | Isolate ports/data or limit parallelism. |
| `NoSuchMethodError` only in integration tests | Runtime dependencies differ from unit tests. | Compare resolved dependency graphs and classpaths. |

The "forked VM terminated" message does not uniquely identify one root cause. Inspect `hs_err_pid*.log` on crashes, process output, OOM diagnostics, and actual flags before simply raising memory or disabling forks.

## 23. Inspecting Fork Command Lines When Necessary

In Maven, run with verbose/debug options while investigating:

```bash
mvn -X test
mvn -X verify
```

In Gradle:

```bash
./gradlew test --info --stacktrace
./gradlew integrationTest --info --stacktrace
./gradlew runMigration --info --stacktrace
```

Debug flags produce very long logs, and command lines/environments can contain secrets. Share or archive logs strictly within approved boundaries, redact sensitive contents, and avoid unnecessary verbose logging in production.

Additionally, temporarily printing `Runtime.version()` and `java.home` from **inside** tests or main classes provides direct proof of the JVM executing your code.

### 23.1. Build Cache and Up-to-Date Checks

Gradle may skip tasks when outputs are up-to-date or cached, meaning console logs might omit fresh test output. When confirming the active process during an investigation, deliberately force re-execution with flags such as `--rerun-tasks`, strictly during diagnostics rather than changing permanent config.

Similarly, Maven or CI caches may hold artifacts compiled on an older JDK. Whenever behavior mismatches configuration, verify output class files and build provenance first.

## 24. Common Configuration Design Mistakes

**Changing only `JAVA_HOME` and assuming the entire toolchain changed.** Maven/Gradle plugins may pick JDKs via Toolchains; forked JVMs can still differ.

**Using `--release` as a runtime selector.** `--release` does not force test processes to execute on the target JDK.

**Putting test heap settings in `MAVEN_OPTS` or `org.gradle.jvmargs`.** Those mainly control the build tool process, not test fork memory.

**Putting `--dry-run` inside `jvmArgs`.** That is a program argument belonging after the main class or inside `args`.

**Using `exec:java` to run a tool requiring a different JDK than Maven.** This goal does not spawn a separate JVM like `exec:exec`.

**Stopping Maven short of `verify`.** Failsafe may record errors during `integration-test` without failing the build until `verify`.

**Adding a Gradle `integrationTest` task without wiring it to `check`.** CI invoking `check` may skip integration tests altogether.

**Raising fork count when tests share ports or databases.** Tests will fail intermittently, especially on multi-core CI runners.

**Putting secrets directly into build scripts.** Values can be committed or leaked through logs and configuration caches.

**Keeping flags opening all JDK internals permanently.** Workarounds mask incompatible dependencies and increase security risk.

**Running integration tests only on a newer JDK and claiming older baselines are supported.** Always test on the lowest committed runtime.

## 25. Configuration Workflow When Migrating JDKs

A workflow applicable to both Maven and Gradle:

### Step 1 — Define the Requirements Matrix

Record the minimum runtime, compiler JDK, unit-test JDK, integration-test JDK, and batch/`JavaExec` JDK. Where identical, state it explicitly; where different, document why.

### Step 2 — Check Build Tool Compatibility

Check whether your Maven/Gradle version, Surefire/Failsafe, Compiler Plugin, and other plugins support the new JDK. For Gradle, check the compatibility matrix for both the Daemon JVM and Toolchains.

### Step 3 — Configure Compiler Target

Set `--release` or equivalent when producing bytecode/API targeting an older JDK; do not confuse it with test runtime selection.

### Step 4 — Configure the Unit-Test JVM Explicitly

Use Surefire `jdkToolchain`/`jvm` or Gradle `Test.javaLauncher`. Configure heap, timezone, locale, and system properties matching the suite's contract.

### Step 5 — Configure Integration Tests Separately

Use Failsafe or a custom Gradle `Test` suite; set runtime launcher, classpath, endpoints, credentials, parallelism, and environment startup/teardown.

### Step 6 — Configure `JavaExec` or Process Runners

In Gradle, configure `JavaExec.javaLauncher` and separate `args` from `jvmArgs`. In Maven, distinguish in-process `exec:java` from external `exec:exec`.

### Step 7 — Verify from Inside Each Process

Print `Runtime.version()`, `java.home`, active profiles, and non-sensitive properties from unit/integration/`JavaExec` processes. Never conclude solely from shell `java -version`.

### Step 8 — Run Suites on Committed Runtimes

Ensure both the minimum supported JDK and key target JDKs are covered. Separate class-file/API issues, dependency resolution errors, config bugs, and integration-environment failures.

### Step 9 — Record Configuration in CI

Pin wrapper and plugin versions, define toolchain provisioning, and archive non-sensitive runtime diagnostics. Avoid configurations relying on a single developer's local paths.

## 26. Checklist for Configuring Build and Test JVMs

- [ ] Know the exact JDK running Maven or the Gradle Daemon.
- [ ] Know the compiler JDK and `--release`/source compatibility settings.
- [ ] Identified the JDK for unit-test JVM forks.
- [ ] Identified the JDK for integration-test JVM forks.
- [ ] Identified the JDK for `JavaExec` or external process runners.
- [ ] Configured JVM flags and application arguments separately.
- [ ] System properties and environment variables reach the intended process.
- [ ] No secrets embedded in build scripts or public command logs.
- [ ] Maven Surefire/Failsafe fork settings configured appropriately.
- [ ] Maven integration tests verified via the `verify` phase.
- [ ] Gradle `integrationTest` wired into the task graph where required.
- [ ] Test forks have isolated ports, databases, and file paths.
- [ ] Java Toolchains properly configured and target JDKs available.
- [ ] Never confuse `org.gradle.jvmargs`/`MAVEN_OPTS` with test JVM arguments.
- [ ] Logged/verified Java versions from inside each test/`JavaExec` process.
- [ ] Tested on the minimum runtime committed for the product.
- [ ] Any `--add-opens`/`--add-exports` flags are justified and scheduled for removal.
- [ ] Diagnostic logs and instructions exist for fork launch failures.

## 27. References

- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): unit test execution, forking, and JVM option configuration.
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration tests and the `integration-test` and `verify` goals.
- [Maven Surefire — Fork Options and Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html): `forkCount`, `reuseForks`, and parallel execution options.
- [Maven Surefire — Java Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html): selecting a dedicated JDK for test forks.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): managing JDK toolchains for supporting plugins.
- [MojoHaus Exec Maven Plugin](https://www.mojohaus.org/exec-maven-plugin/): differences between `exec:java` and `exec:exec`.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): Java Toolchains and Java launchers.
- [Gradle — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): configuring `Test` tasks, forks, and execution.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): declaring multiple test suites.
- [Gradle — JavaExec](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html): `mainClass`, `javaLauncher`, JVM arguments, and program arguments.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): supported JDKs for Gradle runtime and toolchains.
- [Java Toolchain and `javac --release`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): distinguishing compiler target from Java runtime.

## Conclusion

Reliable Java migration requires configuring and observing the **exact JVM executing each type of work**. Maven provides Surefire for unit tests, Failsafe for integration tests, Toolchains for compatible plugins, and Exec Plugin for running Java code in Maven's JVM or externally. Gradle provides Java Toolchains, `Test.javaLauncher`, and `JavaExec.javaLauncher` to pick JVMs per task. `--release` addresses compilation compatibility, while `jvmArgs`, system properties, environment variables, classpaths, and module paths govern actual execution. Verifying `java.home`/`Runtime.version()` inside test and `JavaExec` processes, isolating configurations per suite, and running on the minimum supported JDK will catch compatibility bugs before production deployment.
