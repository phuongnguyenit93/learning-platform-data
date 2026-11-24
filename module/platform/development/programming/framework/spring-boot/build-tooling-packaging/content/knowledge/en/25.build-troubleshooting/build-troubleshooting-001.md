# Reading Logs to Distinguish Build Configuration, Compilation, Testing, and Packaging Errors

## 1. Goal: Identify the Exact Stage Causing the Error

When running a Spring Boot build command, Maven or Gradle can print hundreds of log lines. The last line usually only says **BUILD FAILURE** or **BUILD FAILED**. It confirms that the build did not succeed, but does not point out the root cause.

To resolve it quickly, determine which stage the error appeared in:

1. **Build configuration:** the build tool reads the POM/build script, loads plugins, profiles, repositories, toolchains, and creates the model/task graph.
2. **Compilation:** the compiler processes Java/Kotlin source and generates bytecode.
3. **Testing:** the test engine runs unit/integration tests and reports assertions, exceptions, or test initialization errors.
4. **Packaging:** the build tool creates a JAR/WAR; the Spring Boot plugin may repackage the archive into an executable JAR/WAR, adding the loader, dependencies, and manifest.

An error can appear before phases/tasks start, for example when Maven cannot read the parent POM or Gradle cannot parse `build.gradle`. Other errors appear in a specific task such as `compileJava`, `test`, `bootJar`, or Maven `repackage`.

**Log reading rule:** find the phase/goal/task that is running, read the first meaningful error message, and trace the cause beneath it. The summary line at the end of the log is usually just the consequence.

### 1.1. Quick Identification Map

| Stage | Common in Maven | Common in Gradle | Typical Symptoms |
|---|---|---|---|
| Configuration | Model building, validate, plugin/dependency resolution, profile | Initialization/configuration, reading settings/build script | Invalid POM/XML, unresolved plugin, non-existent method/property, repository/auth |
| Compilation | maven-compiler-plugin:compile or testCompile | compileJava, compileTestJava | cannot find symbol, package does not exist, incompatible types, invalid source/release |
| Testing | maven-surefire-plugin:test, maven-failsafe-plugin | test, integrationTest if the project defines the task | Failures, Errors, assertion mismatch, test engine/discovery, forked JVM |
| Packaging | maven-jar-plugin:jar, maven-war-plugin:war, spring-boot-maven-plugin:repackage | jar, war, bootJar, bootWar | archive cannot be created, wrong main class/manifest, missing resource, confusing plain JAR and executable JAR |

Actual phase/task names depend on plugins and project configuration. The table above serves as a directional guide, not a fixed string for every project.

## 2. Preparing Diagnostic-Ready Logs

Before reading line by line, record the exact command that failed and the execution environment. Two machines can run the same commit yet use different JDKs, Maven/Gradle versions, profiles, or environment variables.

### 2.1. Checking Java and the Build Tool

Maven:

```bash
java -version
javac -version
mvn -version
```

Gradle:

```bash
java -version
javac -version
./gradlew --version
```

On Windows PowerShell, use `.\gradlew.bat --version`. With Maven Wrapper, use `.\mvnw.cmd -version`.

Distinguish between:

- `java -version` shows the Java that the shell finds via PATH.
- `mvn -version` shows the Java currently running Maven.
- `gradlew --version` shows the Gradle version and the launcher/daemon JVM.
- Maven Toolchains or Gradle Java Toolchains can select a different JDK for compiler/test tasks.

Therefore, the JVM running the build tool and the JDK used to compile are not necessarily the same. If the log reports incompatible source/release, check both the build JVM and the compiler toolchain.

### 2.2. Maven: Increasing Detail Step by Step

Start with batch mode and stack traces:

```bash
mvn -B -Dstyle.color=never clean verify -e
```

- `-B`: batch mode, suitable for CI.
- `-Dstyle.color=never`: reduces color codes so logs are easier to save and compare.
- `-e`: prints more detailed exception stack traces.

Once you know which goal failed but still do not understand what the plugin is processing, re-run with `-X`:

```bash
mvn -B -Dstyle.color=never clean verify -e -X
```

`-X` produces very long logs and can expose internal repository URLs, properties, paths, configurations, or credentials depending on the plugin. Do not post raw debug logs to public issues; review and redact sensitive information before sharing.

Save logs in Bash/Linux/macOS:

```bash
mvn -B -Dstyle.color=never clean verify -e > build.log 2>&1
```

In PowerShell:

```powershell
mvn -B -Dstyle.color=never clean verify -e *> build.log
```

### 2.3. Gradle: Stacktrace, Info, and Plain Console

Start with:

```bash
./gradlew clean build --stacktrace --info --console=plain
```

- `--stacktrace`: displays stack traces for build errors, including user errors such as compile errors.
- `--info`: provides additional information about configuration and task execution.
- `--console=plain`: disables rich console/progress bars, making CI logs easier to read.

If more detail is needed:

```bash
./gradlew clean build --full-stacktrace --debug --console=plain
```

Gradle `--debug` can log environment variables, repository credentials, and build cache credentials. Only enable it when truly needed, restrict log access, and inspect the content before sending.

Save logs:

```bash
./gradlew clean build --stacktrace --info --console=plain > build.log 2>&1
```

### 2.4. Do Not Look Only for the Word ERROR

The following lines are common classification indicators:

```text
[FATAL] Non-resolvable parent POM
[ERROR] Failed to execute goal ... maven-compiler-plugin ...:compile
[ERROR] COMPILATION ERROR
[ERROR] Tests run: 12, Failures: 1, Errors: 0, Skipped: 0
[ERROR] Failed to execute goal ... maven-surefire-plugin ...:test
[ERROR] Failed to execute goal ... spring-boot-maven-plugin ...:repackage
> Task :compileJava FAILED
> Task :test FAILED
> Task :bootJar FAILED
* What went wrong:
BUILD FAILURE
BUILD FAILED
```

The line `Failed to execute goal` or `Execution failed for task` usually indicates which goal/task failed. The detailed cause may appear right above it, in compiler output, or in the `Caused by` section below.

**Do not draw conclusions from BUILD FAILURE alone.** Read the goal/task name and the first error explaining why it failed.

## 3. Understanding Execution Order Before Reading Logs

### 3.1. Maven Default Lifecycle

Key Maven phases:

```text
validate
   |
compile
   |
test-compile
   |
test
   |
package
   |
integration-test
   |
verify
   |
install
   |
deploy
```

Maven executes phases preceding the requested phase. For example:

- `mvn compile` runs preceding phases up to compile; it does not run unit tests.
- `mvn test` runs compile, test-compile, and test.
- `mvn package` runs the preceding steps and then creates the JAR/WAR.
- `mvn verify` passes through package and runs checks bound to verify.
- `mvn install` also installs the artifact into the local Maven repository.
- `mvn deploy` further publishes the artifact according to repository configuration.

When you need to verify a full build, `mvn verify` is a good choice for most projects. Integration tests only run if the project has configured the corresponding plugin, such as Maven Failsafe.

### 3.2. Gradle Has Configuration and Task Execution

Gradle has three main steps:

1. **Initialization:** determines the build and participating projects.
2. **Configuration:** reads settings/build scripts, applies plugins, configures projects, and builds the task graph.
3. **Execution:** executes the tasks in the graph according to dependencies/order.

Unlike Maven, Gradle does not have a fixed sequence of phases corresponding to validate → compile → test → package. The task graph is built from plugins and build scripts.

A useful test is:

```bash
./gradlew help
```

The help task does not run compile/test/package, yet Gradle still has to configure the build scripts. If **help also fails**, investigate `settings.gradle`, `build.gradle`, plugin resolution, and configuration. If help succeeds but the build fails, focus on the task reported as failing.

## 4. Identifying Build Configuration Errors

Configuration errors usually appear before the compiler or test runner does any work.

### 4.1. Maven: POM, Parent, Plugin, and Repository

| Log Indicator | Common Meaning | Check |
|---|---|---|
| Non-parseable POM | Invalid XML syntax, mismatched opening/closing tags, or invalid POM structure | Line and column in the POM |
| Non-resolvable parent POM | Maven cannot find/download the parent or relativePath is wrong | groupId/artifactId/version, relativePath, repository |
| Could not resolve dependencies | Cannot download dependency or metadata | Repository URL, proxy, credentials, version |
| Plugin not found / No plugin found for prefix | Plugin not declared, prefix unresolved, or repository unreachable | Plugin coordinates, pluginRepositories, network |
| Unknown lifecycle phase | Typo in phase or misplaced parameter/goal | The Maven command executed |
| Invalid POM / Missing artifactId or version | Missing required field or unresolved property | POM and effective POM |
| Failed to read artifact descriptor | Cannot read dependency POM/metadata | Repository, dependency's parent, network/auth |

**Illustrative** log example:

```text
[FATAL] Non-resolvable parent POM for com.example:diagnostic-log-lab:1.0.0
Could not transfer artifact org.springframework.boot:spring-boot-starter-parent:pom:3.5.16
from/to central (https://repo.maven.apache.org/maven2):
Connect timed out
```

This is a parent/repository resolution error, not a Java source error. Changing code will not fix a timeout.

Another error:

```text
[ERROR] Plugin org.springframework.boot:spring-boot-maven-plugin:... or one of its dependencies could not be resolved
```

Check the plugin version, configured repositories, proxy, credentials, and repository accessibility. If the plugin is managed by the Spring Boot parent, verify that the parent is actually inherited.

### 4.2. Checking Maven Configuration After Inheritance

```bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn help:active-profiles
mvn help:effective-settings -Doutput=target/effective-settings.xml
```

These commands help determine:

- The actual parent/BOM and plugin versions.
- Which profiles are active.
- Which properties are inherited or overridden.
- Which repositories and mirrors are being used.

**`effective-settings.xml` may contain sensitive or internal information.** Do not post this file publicly; extract only the necessary sections and redact credentials.

If you need to run a single module in a Maven reactor:

```bash
mvn -pl service-api -am validate
```

`-pl` selects the module; `-am` also builds the modules it depends on in the reactor. Use the exact module name/path for your project.

### 4.3. Gradle: Configuration Errors Before Tasks

Example:

```text
FAILURE: Build failed with an exception.

* Where:
Build file '.../build.gradle' line: 18

* What went wrong:
Could not find method implementation() for arguments [...]
on object of type org.gradle.api.internal.artifacts.dsl.dependencies.DefaultDependencyHandler.
```

This is an error while Gradle reads the build script. Possible causes include:

- The Java/Java Library plugin has not been applied yet, but a configuration created by that plugin is used.
- Wrong Groovy/Kotlin DSL syntax.
- Plugin version incompatible with the Gradle wrapper.
- Calling a non-existent extension/task/property.
- Plugin cannot be downloaded from the plugin portal or repository.

Use:

```bash
./gradlew help --stacktrace
./gradlew tasks --all
./gradlew help --task bootJar
```

If help fails, fix configuration first. If help succeeds, inspect the task graph and the task running when the error appears.

### 4.4. Distinguishing Configuration Errors from Dependency Resolution Errors Inside a Task

Dependencies can be resolved during the configuration phase or when a task needs its classpath. Therefore, do not look only at the message “Could not resolve” and conclude it is a POM/build script error.

Ask:

1. Does the `help` command run (Gradle)?
2. Has Maven finished reading the POM and which goal/phase did it start?
3. Does the log name a failing plugin/task?
4. Is the dependency being resolved for a plugin, compile classpath, test runtime, or packaging?
5. Is the error network/credentials, a non-existent version, or a conflict in build logic?

If the log shows Maven downloading the compiler plugin or Gradle resolving `compileClasspath`, it is a dependency resolution error at the step serving that task.

## 5. Identifying Java Compilation Errors

Compilation errors occur when the compiler cannot turn source code into bytecode.

### 5.1. Common Compiler Messages

| Message | Meaning | Resolution Approach |
|---|---|---|
| cannot find symbol | Cannot find class, method, field, or variable | Check name, import, dependency, source set |
| package ... does not exist | Missing package/class on the compile classpath | Check dependency, scope, import, and version |
| incompatible types | Data types are incompatible | Fix generics, method signature, or conversion |
| method ... cannot be applied | No overload matches the arguments | Compare parameter types and counts |
| invalid source release: 21 | Current JDK/compiler does not support the requested source/release | Check build JDK and compiler toolchain |
| release version 17 not supported | Selected compiler/JDK is too old for the release target | Choose an appropriate JDK |
| duplicate class | Same fully qualified class appears from multiple sources/dependencies | Check source roots and dependencies |
| unmappable character / illegal character | Invalid encoding or source character | Check UTF-8, encoding, and source file |

Maven example:

```text
[INFO] --- maven-compiler-plugin:...:compile (default-compile) @ diagnostic-log-lab ---
[ERROR] COMPILATION ERROR
[ERROR] .../GreetingService.java:[8,16] cannot find symbol
  symbol:   method greeting(java.lang.String)
  location: class GreetingService
[ERROR] Failed to execute goal ... maven-compiler-plugin:...:compile
```

This is a main source compile error. Maven may not have reached test or package yet. Read the file, line, column, and symbol reported by the compiler before changing the POM.

### 5.2. Test Source Compilation Errors Differ from Test Failures

Maven has a `test-compile` step before `test`. If test code fails to compile, the log usually indicates `maven-compiler-plugin` running `testCompile` or paths under `src/test/java`.

Example:

```text
[ERROR] .../src/test/java/com/example/GreetingServiceTest.java:[14,9]
cannot find symbol
  symbol: method assertEquals(...)
```

This is still a **compile error**, not an assertion failure. Check test dependencies, JUnit imports, and test source.

Gradle can also fail at **compileTestJava** before the **test** task is executed.

### 5.3. Verifying JDK and Compiler Target

Maven:

```bash
java -version
mvn -version
mvn help:effective-pom -Doutput=target/effective-pom.xml
```

Check properties such as `java.version`, `maven.compiler.release`, `maven-compiler-plugin`, and Maven Toolchains if the project configures them.

Spring Boot parent example:

```xml
<properties>
    <java.version>17</java.version>
</properties>
```

Gradle Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Check the Gradle JVM:

```bash
./gradlew --version
./gradlew -q javaToolchains
```

**Do not check Java only in the terminal.** The Maven/Gradle daemon may run with one JDK, while the compiler toolchain may select a separate JDK.

### 5.4. Separating Compilation from Subsequent Steps

Maven:

```bash
mvn -pl service-api -am compile
mvn -pl service-api -am test-compile
```

Gradle:

```bash
./gradlew :service-api:compileJava
./gradlew :service-api:compileTestJava
```

If `compileJava`/`testCompile` fails, there is no need to investigate Spring Boot repackage or Docker images yet. Fix the compiler error first, then re-run full verify/build.

## 6. Identifying Testing Errors

Testing only begins after test sources have compiled and the test engine can start.

### 6.1. Distinguishing Failure and Error

- **Failure:** the test ran, but an assertion did not match the actual result.
- **Error:** the test encountered an exception or error during setup/teardown/execution, not a simple assertion mismatch.
- **Skipped:** the test was skipped due to an annotation, assumption, configuration, or execution condition.
- **No tests found / No tests were executed:** the test runner did not discover matching tests or the filter/provider is misconfigured.

Maven example:

```text
[INFO] Running com.example.diagnostic.GreetingServiceTest
[ERROR] Tests run: 2, Failures: 1, Errors: 0, Skipped: 0
[ERROR] greetReturnsGreeting -- expected: <Hello, An> but was: <Hi, An>
[ERROR] Failed to execute goal ... maven-surefire-plugin:...:test
There are test failures.
```

Here the compiler finished; Surefire ran the test; a failing assertion caused the `test` phase to fail. Do not modify compiler config or Spring Boot packaging to fix this error.

### 6.2. Maven Test Reports

Surefire saves reports by default at:

```text
target/surefire-reports/
├── TEST-com.example.diagnostic.GreetingServiceTest.xml
└── com.example.diagnostic.GreetingServiceTest.txt
```

Open the TXT file to see stack traces/console output and the XML file for structured data for CI.

Run a single test class:

```bash
mvn -Dtest=GreetingServiceTest test
```

Run a single test method (if the Surefire version/provider supports the corresponding syntax):

```bash
mvn -Dtest=GreetingServiceTest#greetReturnsGreeting test
```

If the project uses Maven Failsafe for integration tests, also inspect **target/failsafe-reports/**. Failsafe typically runs at `integration-test` and `verify`; looking only in `surefire-reports` can miss integration test failures.

### 6.3. Gradle Test Failure

Example:

```text
> Task :test FAILED

GreetingServiceTest > greetReturnsGreeting() FAILED
    org.opentest4j.AssertionFailedError:
    expected: <Hello, An> but was: <Hi, An>

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':test'.
> There were failing tests.
```

The message **Execution failed for task ':test'** identifies the failing task; the assertion and report reveal which test case is wrong.

Gradle Java testing generates HTML reports and XML results by default. For a default project, check:

```text
build/reports/tests/test/
build/test-results/test/
```

Run a single test class:

```bash
./gradlew test --tests com.example.diagnostic.GreetingServiceTest
```

Run with more test output:

```bash
./gradlew test --info --stacktrace --console=plain
```

### 6.4. Test Failure or Test Infrastructure Failure?

Not every error under Surefire/Gradle `test` is an assertion failure.

| Indicator | Could Be | What to Inspect |
|---|---|---|
| expected ... but was ... | Assertion failure | Test case and actual data |
| NullPointerException in test | Test/setup/runtime error | Stack trace, fixture, dependency injection |
| No tests were executed | Discovery/filter/provider | Class name, annotations, engine, and include/exclude |
| NoClassDefFoundError at test runtime | Test runtime classpath | Test scope, dependency version, JUnit engine |
| Forked VM terminated without properly saying goodbye | Test JVM process crashed/killed | Heap, OOM, System.exit, CI timeout, dump file |
| Port already in use | Integration test needs a port that is already occupied | Test server/parallelism/port config |
| Connection refused / timeout | Dependent service is not running or unreachable | Testcontainers, database, service endpoint, network |
| Test skipped | Skipped by config/condition | Annotations, assumptions, skip property |

**Read the report before increasing the log level.** The stack trace in the report is usually enough to tell whether the error lies in an assertion, test fixture, or test runner startup.

### 6.5. Do Not Use skip-tests to Hide Errors

Maven has two flags that are easily confused:

```bash
# Skip running tests while still compiling test sources:
mvn package -DskipTests

# Skip both compiling test sources and running tests:
mvn package -Dmaven.test.skip=true
```

This is a temporary diagnostic technique to determine whether the error lies in tests or in steps after tests. It **does not fix tests** and does not prove the build meets quality gates. Do not use skip flags in a release pipeline if policy requires tests.

Gradle can exclude the test task from the build:

```bash
./gradlew build -x test
```

Also use this only when isolating the cause; explicitly note that tests were skipped. A build succeeding with tests excluded from the task graph does not mean the test suite passed.

## 7. Identifying JAR/WAR Packaging Errors

Packaging turns bytecode/resources into a distributable artifact. For Spring Boot, distinguish between a **plain JAR** and an **executable Boot JAR**.

### 7.1. Maven Package and Spring Boot Repackage

Maven typically invokes `maven-jar-plugin` to create the initial JAR. Spring Boot Maven Plugin uses the **repackage** goal to turn that JAR/WAR into an archive with the loader, dependencies, and manifest needed to run via `java -jar`.

For projects using `spring-boot-starter-parent`, the `repackage` execution is pre-configured; declaring the Spring Boot Maven Plugin runs the goal during the `package` phase per the parent configuration. If not using the parent, you must declare the appropriate execution in the POM.

Plugin declaration example:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

If Maven reports an error in goal `spring-boot-maven-plugin:repackage`, compilation/tests may have passed, yet the archive was not repackaged into an executable. Read that goal's error rather than assuming a Java compiler error.

### 7.2. Packaging Failure Indicators

Illustrative log example:

```text
[INFO] --- maven-jar-plugin:...:jar (default-jar) @ diagnostic-log-lab ---
[INFO] Building jar: target/diagnostic-log-lab-1.0.0.jar

[INFO] --- spring-boot-maven-plugin:...:repackage (repackage) @ diagnostic-log-lab ---
[ERROR] Failed to execute goal ... spring-boot-maven-plugin:...:repackage
[ERROR] Unable to find a suitable main class
```

This is an executable Boot archive packaging error. Compilation/tests may have passed; the plugin could not find a suitable entry point or the `mainClass` configuration is incorrect.

Check:

- Is there a main class containing `public static void main(String[] args)`?
- Was that class compiled into the output directory?
- Are there multiple main classes preventing the plugin from auto-selecting?
- Is `mainClass` misconfigured in Spring Boot Maven Plugin?
- Is the `repackage` plugin execution actually running?

When explicitly specifying the main class, configure it in **spring-boot-maven-plugin**, not mistakenly in `maven-jar-plugin`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.diagnostic.DiagnosticApplication</mainClass>
    </configuration>
</plugin>
```

### 7.3. Build Succeeds, but `java -jar` Reports an Error

An important case: Maven/Gradle reports build success, yet running:

```bash
java -jar target/diagnostic-log-lab-1.0.0.jar
```

returns:

```text
no main manifest attribute, in target/diagnostic-log-lab-1.0.0.jar
```

This usually indicates you are running a **plain JAR** without a proper manifest entry point or selected the wrong artifact, such as a classifier/plain JAR. It is not a compilation or test error.

Inspect the contents:

```bash
jar tf target/diagnostic-log-lab-1.0.0.jar
```

An executable Spring Boot JAR typically contains:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/...
BOOT-INF/lib/...
```

Open the manifest to check `Main-Class` and `Start-Class`; verify the filename generated by Maven. With Spring Boot, `Main-Class` is usually the Boot Loader launcher and `Start-Class` is the application main class. When the plugin is configured with a classifier, both the original artifact and the executable artifact with the classifier suffix may exist. Make sure to run the right file.

### 7.4. Maven Original Artifact and Classifier

Spring Boot `repackage` replaces the main artifact with the executable archive by default and renames the original file with a `.original` suffix. When using a classifier, the plugin can create a separate executable artifact while preserving the original JAR.

Example you might see:

```text
target/
├── diagnostic-log-lab-1.0.0.jar
└── diagnostic-log-lab-1.0.0.jar.original
```

If configured with classifier `exec`, filenames may look like:

```text
target/
├── diagnostic-log-lab-1.0.0.jar
└── diagnostic-log-lab-1.0.0-exec.jar
```

Actual names depend on `finalName`, `classifier`, and `packaging`. Do not assume every project has a `.original` file or `-exec` suffix.

### 7.5. Gradle: `jar` vs. `bootJar`

In a Spring Boot Gradle project:

- **jar** is the Java plugin task that creates a plain JAR.
- **bootJar** is provided by the Spring Boot Gradle Plugin to create an executable Boot JAR.
- **bootWar** creates an executable WAR when the project is configured for WAR packaging.

Run:

```bash
./gradlew clean bootJar
./gradlew tasks --all
```

Check the output in **build/libs/**. Both a plain archive and an executable archive may exist; exact filenames depend on classifier/version/configuration. If you accidentally run the plain JAR, `java -jar` may report a missing main manifest.

If `bootJar` fails, read the **What went wrong** section, the task name, and the main class/resources error. If `bootJar` does not appear in `tasks`, check whether the Spring Boot Gradle Plugin has been applied and whether the plugin version resolved successfully.

### 7.6. WAR Packaging and Provided Dependencies

In a Spring Boot executable WAR, libraries may be located in:

- `WEB-INF/lib/`
- `WEB-INF/lib-provided/`

If deploying to an external servlet container, you must understand which dependencies belong to the container and which are packaged into the WAR for embedded execution. A WAR that builds successfully does not automatically mean it is compatible with every servlet container; verify the manifest, layout, and runtime deployment target.

## 8. Java 17 Hands-On Example: A Small Project to Reproduce the Four Stages

The example uses Spring Boot 3.5.16 and Java 17. The goal is a simple Maven project with a main class, a service, and a JUnit test to distinguish compile/test/package.

### 8.1. Directory Structure

```text
diagnostic-log-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/diagnostic/
    │   ├── DiagnosticApplication.java
    │   └── GreetingService.java
    └── test/java/com/example/diagnostic/
        └── GreetingServiceTest.java
```

### 8.2. Minimal POM

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>diagnostic-log-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The parent manages plugin and dependency versions. For this project, declaring the Spring Boot Maven Plugin uses the `repackage` execution pre-configured by the parent in the `package` lifecycle.

### 8.3. Main Class

`src/main/java/com/example/diagnostic/DiagnosticApplication.java`:

```java
package com.example.diagnostic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticApplication.class, args);
    }
}
```

### 8.4. Service

`src/main/java/com/example/diagnostic/GreetingService.java`:

```java
package com.example.diagnostic;

public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

### 8.5. JUnit Test

`src/test/java/com/example/diagnostic/GreetingServiceTest.java`:

```java
package com.example.diagnostic;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void greetReturnsGreeting() {
        GreetingService service = new GreetingService();

        assertEquals("Hello, An", service.greet("An"));
    }
}
```

The valid test will pass. To simulate a test failure, temporarily change the expected value to `Hello, Binh`; the compiler will still succeed, but the assertion will fail. Restore the expected value before building a release.

### 8.6. Running Step by Step to Locate the Error

From the project root:

```bash
# Check environment and POM:
java -version
mvn -version
mvn validate

# Compile main source only:
mvn compile

# Compile and run unit tests:
mvn test

# Package JAR/WAR:
mvn package

# Run checks up to verify:
mvn verify
```

When a command fails, stop at that stage and read the goal/plugin. There is no need to investigate repackage if compilation has not finished. Once fixed, re-run the failed phase and then verify with full `verify`.

### 8.7. What Does a Successful Log Look Like?

Illustrative log:

```text
[INFO] --- maven-compiler-plugin:...:compile (...) @ diagnostic-log-lab ---
[INFO] Compiling ... source files with javac [debug release 17]

[INFO] --- maven-compiler-plugin:...:testCompile (...) @ diagnostic-log-lab ---
[INFO] Compiling ... test source files

[INFO] --- maven-surefire-plugin:...:test (...) @ diagnostic-log-lab ---
[INFO] Running com.example.diagnostic.GreetingServiceTest
[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0

[INFO] --- maven-jar-plugin:...:jar (...) @ diagnostic-log-lab ---
[INFO] Building jar: target/diagnostic-log-lab-1.0.0.jar

[INFO] --- spring-boot-maven-plugin:...:repackage (...) @ diagnostic-log-lab ---
[INFO] Replacing main artifact with repackaged archive

[INFO] BUILD SUCCESS
```

Plugin versions, file counts, timings, and exact log phrasing depend on plugin versions. What you need to recognize is the sequence `compile → testCompile → test → jar → repackage` and the final outcome.

### 8.8. Inspecting the Artifact

```bash
jar tf target/diagnostic-log-lab-1.0.0.jar
java -jar target/diagnostic-log-lab-1.0.0.jar
```

The executable JAR should contain the Boot loader, application classes, and dependencies. The example application has no web server and does not print a greeting on its own; the goal of `java -jar` is to verify the manifest/loader and Spring Boot startup.

## 9. Gradle: Tasks to Inspect When Building Spring Boot

| Goal | Commonly Used Task |
|---|---|
| List available tasks | tasks, tasks --all |
| Compile main Java | compileJava |
| Compile test Java | compileTestJava |
| Run unit tests | test |
| Run quality checks | check |
| Create plain JAR | jar |
| Create executable Spring Boot JAR | bootJar |
| Create executable WAR | bootWar |
| Standard build | build |

Run tasks independently:

```bash
./gradlew help
./gradlew compileJava --stacktrace
./gradlew compileTestJava --stacktrace
./gradlew test --stacktrace --info
./gradlew bootJar --stacktrace --info
./gradlew build --stacktrace --info
```

In a multi-project build, use the full task path:

```bash
./gradlew :service-api:compileJava
./gradlew :service-api:test
./gradlew :service-api:bootJar
```

Reading task prefixes in logs:

- `> Task :compileJava FAILED`: main source compile task.
- `> Task :compileTestJava FAILED`: test source compile task.
- `> Task :test FAILED`: test execution/reporting.
- `> Task :bootJar FAILED`: Spring Boot archive packaging.
- `BUILD FAILED`: aggregate result.

Tasks with **UP-TO-DATE**, **FROM-CACHE**, or **NO-SOURCE** status are not necessarily errors. They indicate that the task was skipped/reused/had no input sources in that run. Read task statuses alongside the task graph and build goal.

## 10. Troubleshooting Matrix by Log Message

| Log/Symptom | Classification | First Action |
|---|---|---|
| Non-parseable POM | Maven configuration | Fix XML, check line/column |
| Non-resolvable parent POM | Parent/repository | Check coordinates, relativePath, mirror, credentials |
| Plugin could not be resolved | Plugin/repository | Check plugin version, pluginRepositories, and network |
| Could not find method/property in build.gradle | Gradle configuration | Check plugins, DSL, and versions |
| Invalid source release | Compilation/toolchain | Compare build JDK with compiler release/toolchain |
| cannot find symbol | Compilation | Read symbol/file/line and compile classpath |
| compileTestJava/testCompile failure | Test source compilation | Check JUnit imports, test dependencies, and test code |
| Tests run, Failures > 0 | Test assertion | Open test report, compare expected/actual |
| Tests run, Errors > 0 | Test runtime/setup | Inspect stack trace, fixtures, test context |
| No tests found | Test discovery/config | Check naming, annotations, filters, engine |
| Forked VM terminated | Test process/infrastructure | Check OOM, JVM crash, timeout, fork logs |
| repackage cannot find main class | Spring Boot packaging | Check main class and plugin `mainClass` |
| No main manifest attribute on java -jar | Wrong artifact/packaging selected | Check repackage/bootJar and manifest |
| Missing BOOT-INF/lib in executable JAR | Packaging | Might be running plain JAR or repackage plugin did not run |
| JAR/WAR created but missing resource | Packaging/resource processing | Check resource directories, filtering, and plugin config |
| BUILD SUCCESS but app fails to start | Runtime/deployment | Read application exception after packaging |

## 11. Errors Easily Misclassified

### 11.1. Build Config vs. Dependency Resolution

An unresolved plugin error may occur before the compile task. However, application dependencies are only resolved when the compile/test task needs its classpath. Use the goal/task name in the log to see which part the dependency is serving.

### 11.2. Test Compile vs. Test Execution

If the compiler fails during `testCompile`/`compileTestJava`, the test runner has not executed yet. If the test report shows Failures/Errors, sources have compiled and the test runner has executed at least partially.

### 11.3. Packaging vs. Runtime Startup

If Maven/Gradle builds the archive successfully yet `java -jar` throws an error, the build may have completed according to the task graph, but either the artifact is not an executable Boot archive or a runtime error occurred. Check:

1. Is it the right JAR/WAR file?
2. Does it have the proper manifest?
3. Does it have the Boot loader and nested dependencies?
4. Does the main class exist?
5. Did the error happen when the JVM loaded the archive or after Spring `ApplicationContext` started?

### 11.4. Warnings Are Not Always Failures

Some warnings only indicate deprecated APIs, unchecked operations, soon-to-fail plugin configurations, or resource filtering. They may not fail the build yet. However, warnings about version/JDK compatibility can foretell errors when upgrading the build tool. Gradle has `--warning-mode=all` to view details; Maven uses logs and corresponding plugin reports.

Do not enable fail-on-all-warnings just to “clean up logs” if the project has no plan to address warnings and does not know their impact scope.

## 12. Standard Diagnostic Workflow in CI

1. **Record the command:** Maven/Gradle command, module, profile, properties, and commit SHA.
2. **Record the environment:** Java/JDK, Maven/Gradle Wrapper, OS, and architecture.
3. **Save full logs:** prefer stacktrace and plain console; only enable debug when needed.
4. **Find the failing phase/goal/task:** configuration, compile, test, or package.
5. **Isolate reproduction steps:** run validate/help, compile, test, package/bootJar separately.
6. **Open the right report:** Maven Surefire/Failsafe or Gradle test report.
7. **Inspect the artifact:** filename, size, manifest, loader, dependencies, and classifier.
8. **Fix the root cause:** build config, source, test, or packaging plugin at the right layer.
9. **Re-run the failed layer:** verify the error message disappears.
10. **Run full verify/build:** ensure preceding and subsequent steps still pass.
11. **Archive artifacts/logs:** keep the exact files produced by the verified commit and build.

### 12.1. Maven CI Command Example

```bash
mvn -B -Dstyle.color=never clean verify -e
```

If it fails, archive `build.log`, `target/surefire-reports/`, `target/failsafe-reports/` (if present), `target/*.jar` or `target/*.war` if packaging created an artifact, and `effective-pom.xml` when inherited configuration is suspected.

### 12.2. Gradle CI Command Example

```bash
./gradlew clean build --stacktrace --info --console=plain
```

Archive `build.log`, `build/reports/tests/`, `build/test-results/`, `build/reports/problems-report.html` if generated by Gradle, and `build/libs/*.jar` or `*.war` if the packaging task completed.

Do not upload debug logs containing credentials to public CI artifacts. Keep logs and reports tied to the same build ID/commit to avoid misreading results from an older run.

## 13. 60-Second Log Reading Checklist

- [ ] Identify the exact failing command and module.
- [ ] Check Java and Maven/Gradle versions.
- [ ] Find the last goal/task that started running.
- [ ] Classify the error as configuration, compile, test, or package.
- [ ] Read the first meaningful error and `Caused by` section.
- [ ] If compilation, open the exact source file and line/column.
- [ ] If testing, open Surefire/Failsafe or Gradle HTML/XML reports.
- [ ] If packaging, check which JAR/WAR/plain/boot archive was produced.
- [ ] If `java -jar` fails, inspect the manifest and Boot loader.
- [ ] Only enable debug when stacktrace/info is insufficient and logs can be protected.
- [ ] After fixing, re-run the failed phase/task and then run full verify/build.
- [ ] Save logs and artifacts for the exact verified commit.

**Conclusion:** Build logs tell you where an error lies if read in execution order. Maven shows phases and plugin goals; Gradle shows configuration and tasks. POM/build script errors occur before compilation; compiler errors appear in `compile`/`testCompile`; assertions or exceptions appear in the test runner; and executable JAR/WAR errors are usually tied to `jar`/`war`/`repackage`/`bootJar` and the manifest. When classified accurately, you can choose the right command to reproduce, open the right report, and fix the right layer of configuration/source/test/packaging.

### Official Documentation

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Running Maven](https://maven.apache.org/ref/current/maven-embedder/cli.html)
- [Maven Surefire Plugin — Introduction and test reports](https://maven.apache.org/components/surefire/maven-surefire-plugin/)
- [Maven Failsafe Plugin — Integration tests](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Gradle — Command-Line Interface and debugging options](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Logging and Output](https://docs.gradle.org/current/userguide/logging.html)
- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html)
- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
