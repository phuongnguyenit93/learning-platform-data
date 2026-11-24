# Distinguishing JVM Options, System Properties, and Application Arguments When Running Spring Boot

## 1. Three Kinds of Parameters Pass Through Three Different Layers

When developing or running a Java/Spring Boot application, a single command line can contain **JVM options**, **Java system properties**, and **application arguments**. They differ in position, scope, and how they are read. A program can compile cleanly yet behave incorrectly if a valid setting is placed in the wrong position.

Example:

```bash
java -Xms128m -Xmx256m -Ddemo.mode=jvm -jar target/argument-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli hello
```

Reading from left to right:

| Command Part | Kind | Who Handles It? |
|---|---|---|
| `java` | Java launcher | Creates the JVM and selects how to launch the program |
| `-Xms128m` | JVM option | Sets initial heap size to roughly 128 MiB |
| `-Xmx256m` | JVM option | Sets maximum heap limit to roughly 256 MiB |
| `-Ddemo.mode=jvm` | **Java system property** (passed via the launcher's `-D` option) | Sets `System.getProperty("demo.mode")` in the application JVM |
| `-jar` | Java launcher option | Runs a JAR with an appropriate entry point |
| `target/argument-lab-0.0.1-SNAPSHOT.jar` | Artifact path | The JAR to be executed |
| `--demo.mode=cli` | **Application argument**, and by default a Spring Boot command-line property | Reaches `main(String[] args)` and Spring `Environment` |
| `hello` | Regular (non-option) **application argument** | Reaches `main(String[] args)` / `ApplicationArguments` |

According to Java launcher syntax, when running a JAR:

```text
java [JVM/launcher options] -jar file.jar [application arguments...]
     └─ before -jar ──────┘            └─ after file.jar ─┘
```

**The most important rule:** everything appearing **after the JAR filename** is passed to the application and is no longer interpreted by the Java launcher as a JVM option. For example, `java -jar app.jar -Xmx256m` does not set a 256 MiB heap; the string `-Xmx256m` is merely an application argument. Likewise, `java -jar app.jar -Ddemo.mode=jvm` **does not** set a Java system property. Place `-D...` before `-jar`.

## 2. What Are JVM Options?

**JVM options** control the Java execution environment or how the launcher locates and loads the application. Some common categories:

| Example | Effect | When Needed |
|---|---|---|
| `-Xms128m` | Initial heap size | Memory tuning during benchmarking or limit testing |
| `-Xmx512m` | Maximum heap size | Controlling the Java heap region |
| `-XX:+HeapDumpOnOutOfMemoryError` | Creates a heap dump on OOME per JVM policy | Diagnosing out-of-memory errors |
| `-XX:HeapDumpPath=./heap.hprof` | Location where the heap dump is saved | Memory error analysis |
| `-ea` | Enables Java assertions | Testing code that uses `assert` |
| `-Dfile.encoding=UTF-8` | Sets a JVM system property | When there is a clear encoding reason to avoid environment dependence |
| `-agentlib:jdwp=...` | Enables Java Debug Wire Protocol (JDWP) | Attaching a debugger to a JVM |
| `-cp out` / `--class-path out` | Sets the classpath when running a main class | Running external bytecode/JARs |

Note that `-D...` is **both a Java launcher option and the mechanism for supplying a system property**. Consequently, learners often call `-Ddemo.mode=jvm` a "JVM argument," though in terms of **configuration semantics** it belongs to Java system properties, distinct from memory flags like `-Xmx`.

Never assume that setting `-Xmx512m` keeps the Java process's entire RSS under 512 MiB. The JVM also uses metaspace, stacks, native memory, direct buffers, and other memory regions. Optimization requires measuring actual memory usage.

For Java 17+, a debug example listening only on loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

This is **illustrative syntax**, used only when you actually have `app.jar` and need debugging. Avoid opening JDWP ports to public networks. Spring Boot's `--debug` flag only increases Spring Boot diagnostic output and is completely different from the JVM's JDWP debugger.

## 3. What Is a Java System Property?

**Java system properties** are key–value pairs within a **JVM process**. They can come from `-Dname=value`, JVM defaults, or Java code calling `System.setProperty`. Read with:

```java
String mode = System.getProperty("demo.mode");
String fallback = System.getProperty("demo.mode", "default");
```

Examples include `file.encoding`, `user.dir`, `java.version`, `spring.profiles.active`, or a custom property `demo.mode`.

Distinguish:

- `System.getProperty("demo.mode")` reads from **Java system properties** in the current JVM.
- `System.getenv("DEMO_MODE")` reads from the process's **OS environment variables**, not Java system properties. An environment variable named `DEMO_MODE` does not automatically become `System.getProperty("demo.mode")`.
- `environment.getProperty("demo.mode")` in Spring reads across **multiple PropertySources** such as command-line arguments, Java system properties, OS environment, and application config.
- `System.setProperty("demo.mode","x")` modifies the property in the current JVM; it does not change the operating system or any other JVM, nor does it necessarily refresh beans that have already been bound.

Example:

```bash
java -Ddemo.mode=local -jar app.jar
```

If the application has not overridden the property in code, `System.getProperty("demo.mode")` returns `local`. However, Spring `Environment` may return a different value if a command-line argument `--demo.mode=...` or a higher-precedence property source defines the same key.

A Maven/Gradle process and a Java application process are **two separate JVMs** when the build tool forks a JVM to run the app. Passing `-Ddemo.mode=...` to the **Maven/Gradle JVM** does not mean it automatically propagates to the JVM running Spring Boot; you must use plugin/task parameters dedicated to the child process.

## 4. What Are Application Arguments?

**Application arguments** are the strings passed by the Java launcher to `public static void main(String[] args)`. They appear after the main class name or after the JAR path. The Java launcher itself **does not require** arguments to follow `--name=value`; that is simply a convention of the framework or application.

Example:

```bash
java -jar app.jar --demo.mode=cli hello --dry-run
```

The `args` array receives the strings:

```text
[--demo.mode=cli, hello, --dry-run]
```

In Spring Boot, `SpringApplication` by default converts option arguments starting with `--` into **command-line properties** of the Spring `Environment`:

- `--server.port=9090` typically sets the web application's HTTP port.
- `--spring.profiles.active=dev` activates the `dev` runtime profile.
- `--demo.mode=cli` puts the key `demo.mode` into the Spring `Environment`.
- `hello` remains a non-option argument and does not automatically become a property.
- `--dry-run` may be recognized as an option without a value by `ApplicationArguments`, but that **does not** mean Spring Boot automatically implements "dry run" behavior; the application must handle it itself.

If `SpringApplication.setAddCommandLineProperties(false)` is used, Spring Boot will not automatically add command-line options to the `Environment`; however, code can still read the raw arguments. Examples in this guide assume the default behavior is **enabled**.

### Spring Boot `ApplicationArguments` API

Spring provides the `org.springframework.boot.ApplicationArguments` interface:

| Method | Purpose |
|---|---|
| `getSourceArgs()` | Returns the original raw `String[]` |
| `containsOption("demo.mode")` | Checks whether the option is present |
| `getOptionNames()` | Set of option names |
| `getOptionValues("demo.mode")` | Option values; may be null if the option is absent |
| `getNonOptionArgs()` | Arguments not starting with the `--...` option syntax |

`ApplicationRunner` receives `ApplicationArguments` in its `run` method; `CommandLineRunner` receives `String... args` directly. Both are hooks executed after the Spring `ApplicationContext` is initialized; choose whichever API fits whether you need raw args or parsed options.

## 5. Pure Java 17 Experiment: Seeing Both Channels Firsthand

This example has no dependency on Spring Boot, Maven, or Gradle. Create `src/demo/ArgsBasics.java`:

```java
package demo;

import java.util.Arrays;

public final class ArgsBasics {
    public static void main(String[] args) {
        System.out.println("System property: "
                + System.getProperty("demo.mode", "unset"));
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
```

In the root directory containing `src`, using JDK 17 or later:

```bash
javac -d out src/demo/ArgsBasics.java
java -Xmx256m -Ddemo.mode=jvm -cp out demo.ArgsBasics --demo.mode=cli hello
```

**Exact stdout of the `java ...` command:**

```text
System property: jvm
Arguments: [--demo.mode=cli, hello]
```

Why? `-Ddemo.mode=jvm` sets the system property in the JVM, while `--demo.mode=cli` and `hello` are passed intact into `args`. `-Xmx256m` is a JVM option and therefore **does not** appear in the `args` array.

To prove the difference when reversing positions:

```bash
java -cp out demo.ArgsBasics -Ddemo.mode=late
```

**Exact stdout** (assuming the environment does not preset `demo.mode`):

```text
System property: unset
Arguments: [-Ddemo.mode=late]
```

Here `-Ddemo.mode=late` is placed **after the main class**, so it is merely an application argument. If the machine has `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` presetting `demo.mode`, the property output may differ; check those environment variables when diagnosing.

### Classpath Syntax Differences Between Operating Systems

The example above only needs one `out` directory, so the command works the same across operating systems. If there are two classpath entries:

- Linux/macOS: `-cp "out:lib/demo.jar"`.
- Windows: `-cp "out;lib/demo.jar"`.

The `:` / `;` separator belongs to **classpath syntax** and is unrelated to categorizing JVM, system, and application arguments.

## 6. Runnable Spring Boot 3.x Hands-on Lab

This example uses **Java 17**, Spring Boot **3.5.0** (a pinned illustrative version, not claiming to be the latest), and Maven. Create the structure:

```text
argument-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/argumentlab/ArgumentLabApplication.java
    │   └── resources/application.properties
    └── test/
```

### 6.1. Complete POM

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>argument-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

`spring-boot-starter-parent` manages compatible dependency and plugin versions in this example. `spring-boot-maven-plugin` creates the executable JAR when the `package` phase runs using the execution inherited from the parent. No web starter is needed since we only print information to the console.

### 6.2. Complete Java Class

Create `src/main/java/com/example/argumentlab/ArgumentLabApplication.java`:

```java
package com.example.argumentlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ArgumentLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ArgumentLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showArguments(Environment environment) {
        return arguments -> {
            System.out.println("JVM property: "
                    + System.getProperty("demo.mode", "unset"));
            System.out.println("Spring property: "
                    + environment.getProperty("demo.mode", "unset"));
            System.out.println("CLI option: "
                    + arguments.getOptionValues("demo.mode"));
            System.out.println("Non-options: "
                    + arguments.getNonOptionArgs());
        };
    }
}
```

The application intentionally reads **two different APIs** for the same key `demo.mode`. `System.getProperty` inspects the property in the JVM itself; `Environment` applies Spring's configuration source precedence rules. `ApplicationRunner` receives parsed options and non-options.

Create `src/main/resources/application.properties`:

```properties
demo.mode=file
spring.main.banner-mode=off
```

### 6.3. Build and Run with `java -jar`

At the root:

```bash
# For projects with Maven Wrapper:
./mvnw clean package

# Or with Maven installed in PATH:
mvn clean package

# Run the executable JAR:
java -Xmx256m -Ddemo.mode=jvm -jar target/argument-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli hello
```

In Windows PowerShell, if the project has a Maven Wrapper, use `.\mvnw.cmd clean package`; the `java` command uses the exact same argument order. You only need to run **one** of the two equivalent build commands; if using the wrapper, there is no need to run `mvn` again.

Upon successful build/run, the console may also show Spring, Maven, or environment logs, but the **four lines printed by `ApplicationRunner`** are strictly:

```text
JVM property: jvm
Spring property: cli
CLI option: [cli]
Non-options: [hello]
```

Explanation:

1. `-Ddemo.mode=jvm` sets `System.getProperty("demo.mode") = "jvm"`.
2. `--demo.mode=cli` creates a command-line property for Spring `Environment`; by default it **takes precedence over** a Java system property with the same key and `application.properties`.
3. `ApplicationArguments.getOptionValues("demo.mode")` returns a single-element list `[cli]`.
4. `hello` is a non-option and is returned as `[hello]`.

Change one parameter to experiment:

```bash
java -Ddemo.mode=jvm -jar target/argument-lab-0.0.1-SNAPSHOT.jar hello
```

When `--demo.mode=...` is **absent**, both `System.getProperty` and `Environment` read `jvm` (because Java system properties take precedence over `application.properties`). `CLI option` prints `null`, while `Non-options` remains `[hello]`. This clearly reveals each configuration source.

If you run:

```bash
java -jar target/argument-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli
```

`JVM property` is `unset` unless another source sets the system property, `Spring property` is `cli`, and `CLI option` is `[cli]`. You neither need nor should try to convert every Spring property into `-D`.

## 7. Configuration Precedence Order in Spring Boot

Spring Boot's `Environment` combines multiple **PropertySources**. For a typical launch (without test overrides or higher-priority custom property sources), which source generally overrides which?

```text
Higher precedence (for the case under consideration)
    --demo.mode=cli                  # command-line property
    -Ddemo.mode=jvm                  # Java system property
    DEMO_MODE=from-env               # OS environment variable
    application.properties           # config data
Lower precedence
```

This diagram compares only **four common sources**. Spring Boot also includes `SPRING_APPLICATION_JSON`, profile-specific files, test property sources, config imports, and more. To determine a value definitively, inspect the running application's full list of `PropertySource`s.

| Source | Example | How to Read |
|---|---|---|
| Application config | `demo.mode=file` in `application.properties` | `Environment.getProperty("demo.mode")` |
| OS environment | `DEMO_MODE=env` | `System.getenv("DEMO_MODE")`; can also bind into `Environment` via relaxed binding |
| Java system property | `-Ddemo.mode=jvm` before `-jar` | `System.getProperty("demo.mode")` and `Environment` |
| Spring command-line option | `--demo.mode=cli` after JAR | `ApplicationArguments`, `Environment.getProperty` |
| Raw non-option argument | `hello` after JAR | `String[] args`, `getNonOptionArgs()` |

**Do not confuse property names with where properties are stored:** `spring.profiles.active` can be supplied via `-Dspring.profiles.active=dev` (Java system property), via `--spring.profiles.active=dev` (application argument processed by Spring), or via `SPRING_PROFILES_ACTIVE=dev` (OS environment variable). They can produce the same Spring profile outcome, yet travel through different channels with different precedence, and `System.getProperty("spring.profiles.active")` only sees the Java system property form.

If you want to **disable** Spring's addition of CLI options into `Environment`, the application can call:

```java
SpringApplication application =
        new SpringApplication(ArgumentLabApplication.class);
application.setAddCommandLineProperties(false);
application.run(args);
```

This is a **replacement snippet for the `main` method body** in the Java example above, not a standalone file. With this setup, `ApplicationArguments` still reads raw options, while `Environment` will not automatically pull `--demo.mode=...` from the command line. Change this only when there is a clear reason.

## 8. Maven `spring-boot:run`: Separating Maven's JVM from the App's JVM

`mvn spring-boot:run` or `./mvnw spring-boot:run` is commonly used to run the application during development without building an executable JAR first. The Spring Boot Maven Plugin executes the application in a **separate forked process**, so you must separate:

1. **Maven arguments**: e.g., `-DskipTests`, `-Pdev`, `-Dsome.build.property`.
2. **Application JVM options**: plugin `spring-boot.run.jvmArguments` or `spring-boot.run.systemPropertyVariables`.
3. **Application arguments**: plugin `spring-boot.run.arguments`, or `spring-boot.run.profiles` to activate Spring profiles.

Linux/macOS example (one command, wrapped for readability):

```bash
./mvnw spring-boot:run \
  -Dspring-boot.run.jvmArguments="-Xmx256m -Ddemo.mode=jvm" \
  -Dspring-boot.run.arguments="--demo.mode=cli hello"
```

The four lines printed by `ApplicationRunner` match Section 6.3:

```text
JVM property: jvm
Spring property: cli
CLI option: [cli]
Non-options: [hello]
```

Here, parameters beginning with `-Dspring-boot.run....` are **Maven user properties configuring the plugin**. The plugin reads those values and forwards the JVM/app portions to the Spring Boot process. Do not assume these are Java system properties of the same name read directly by the application.

Single-line PowerShell command to avoid Bash line-continuation differences:

```powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.jvmArguments=-Xmx256m -Ddemo.mode=jvm" "-Dspring-boot.run.arguments=--demo.mode=cli hello"
```

Quoting syntax for parameters containing spaces varies across shells and tool versions; if the app appears to miss part of an argument, inspect the logs and run on a single line with quoting suitable for your shell.

To enable a Spring runtime profile via the Maven plugin:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Note that `-Pdev` is a **Maven build profile**, not equivalent to `spring.profiles.active=dev` at Spring runtime. Similarly, the command:

```bash
./mvnw spring-boot:run -Ddemo.mode=jvm
```

only sets a user property for the **Maven process**; it does not guarantee that the Java system property `demo.mode` exists in the **application JVM**. If truly needed, use `-Dspring-boot.run.jvmArguments="-Ddemo.mode=jvm"` or configure the plugin's `systemPropertyVariables`.

### `MAVEN_OPTS` Is Not Application Args

`MAVEN_OPTS` affects the JVM **running Maven**, whereas `spring-boot.run.jvmArguments` controls the application JVM launched by the plugin. `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` may be picked up by the Java launcher or multiple JVMs and can affect both Maven and the application; therefore, their scope is broad and can surprise you when debugging. Never use them casually to pass arguments containing sensitive data.

## 9. Gradle `bootRun`: App Runs in a JVM Forked by Gradle

The Spring Boot Gradle Plugin adds the `bootRun` task of type `BootRun`, which extends `JavaExec`. Therefore, you have distinct configuration methods for **JVM**, **system properties**, and **application arguments**.

Complete **Groovy DSL `build.gradle` build example**, using the same illustrative Spring Boot version as the Maven section:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('bootRun') {
    jvmArgs '-Xmx256m'                // JVM option
    systemProperty 'demo.mode', 'jvm' // Application JVM system property
    args '--demo.mode=cli', 'hello'   // Application args
}
```

Reuse the **same Java class** and `application.properties` from Section 6, running via Gradle instead (do not mix `pom.xml` and `build.gradle` expecting them to stay in sync automatically). Minimal `settings.gradle`:

```groovy
rootProject.name = 'argument-lab'
```

When the project has a Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows uses `gradlew.bat bootRun`. The application runs in the JVM spawned by `bootRun`; the four lines printed by the Java class remain `jvm`, `cli`, `[cli]`, `[hello]`. You need a Gradle version compatible with Spring Boot Gradle Plugin 3.5 and JDK 17+; if your machine only has an older Gradle, update the Wrapper per project instructions.

### Passing Application Args from the Gradle Command Line

```bash
./gradlew bootRun --args="--demo.mode=cli hello"
./gradlew bootRun --args="--spring.profiles.active=dev"
```

The `--args` option of the `JavaExec/BootRun` task passes arguments to the **application**, without changing JVM heap. When `--args` is supplied, it replaces the arguments configured on the task with the command-line values according to Gradle's mechanism. To set default arguments, put `args` in the task as shown above; to override on a specific run, pass `--args`.

Specifically avoid:

```bash
./gradlew bootRun -Ddemo.mode=jvm
```

Here `-Ddemo.mode=jvm` is primarily a **Gradle system property** for the Gradle/daemon process and is not guaranteed to be forwarded automatically to the application JVM. To pass a value from the command line to `bootRun`, define a project property and map it into the child JVM:

```groovy
tasks.named('bootRun') {
    systemProperty 'demo.mode', providers.gradleProperty('appMode').orElse('local').get()
}
```

This is an **addition/replacement for the `systemProperty` line** in the `bootRun` task; do not keep two conflicting lines in the file expecting a single value. Then:

```bash
./gradlew bootRun -PappMode=jvm --args="--demo.mode=cli hello"
```

`-PappMode=jvm` is a **Gradle project property**; the script converts it into a **Java system property inside the application JVM**. `--demo.mode=cli` remains an **app argument**, and by default Spring `Environment` prioritizes `cli` over `jvm`.

In a Kotlin DSL build, the syntax differs (`tasks.named<BootRun>("bootRun") { ... }` with the appropriate imports/classes); do not mix Groovy and Kotlin syntax in the same file.

## 10. Running from IDE, Containers, and Scripts: Know Which Process Receives Which Parameters

### IDE

In an IDE's Run/Debug configuration, there are typically dedicated fields:

- **VM options / JVM arguments**: `-Xmx512m -Ddemo.mode=jvm`.
- **Program arguments / application arguments**: `--demo.mode=cli hello`.
- **Environment variables**: `DEMO_MODE=env`, `SPRING_PROFILES_ACTIVE=dev`.
- **Working directory**: affects relative paths when the app opens files; not a command-line parameter.

If configuring a Maven Run or Gradle Task in the IDE, be sure whether the IDE is configuring the **build process** or the **Spring Boot application process**; a "VM options" box might apply to Maven/Gradle before the app is forked. To be certain, check with `System.getProperty` inside the Spring Boot JVM itself.

### Docker/Container

A container running an executable JAR via Java follows the exact same rules:

```dockerfile
# Illustrates the ENTRYPOINT section when the image already has a JRE and app.jar
ENTRYPOINT ["java", "-Xmx256m", "-Ddemo.mode=jvm", "-jar", "/app/app.jar"]
```

If running the container with extra arguments:

```bash
docker run --rm example/argument-lab:demo --demo.mode=cli hello
```

With the JSON/exec-form ENTRYPOINT above, arguments after the image name are appended after the JAR and become **application arguments**. Here `example/argument-lab:demo` is a **hypothetical** image name that must be built first; the Dockerfile snippet is not a complete Dockerfile and does not imply that image exists.

To configure the JVM in a container, place JVM options **before** `-jar` in `ENTRYPOINT` or use a controlled configuration mechanism. Do not expect an `-Xmx` flag at the end of `docker run ... image ...` to affect the JVM when the entrypoint already runs `-jar`.

### Start Scripts and CI

A script might contain:

```bash
java -Xmx512m -Ddemo.mode=ci -jar build/libs/argument-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=ci
```

Notice that `build/libs` here is the **Gradle convention**, whereas Maven typically uses `target/`. Both are only valid once the corresponding task has created an executable JAR with that name. CI should log/verify the exact command executed, JDK version, and actual artifact version to avoid swapping parameter order by mistake.

## 11. Common Mistakes

| Symptom | Likely Cause to Check | How to Fix |
|---|---|---|
| `-Xmx512m` has no effect when running JAR | Placed after `app.jar` | Move `-Xmx512m` before `-jar` |
| `System.getProperty("demo.mode")` returns `null` despite `--demo.mode=cli` | `--...` is a Spring app argument and does not create a Java system property | Read `Environment` or pass `-Ddemo.mode=...` before `-jar` |
| Spring `Environment` returns `cli` despite `-Ddemo.mode=jvm` | CLI properties take precedence over Java system properties by default | Check source precedence; remove or change `--demo.mode` |
| `System.getenv("DEMO_MODE")` is empty when only `-Ddemo.mode=...` is used | Environment variables differ from Java system properties | Set an OS env var or read `System.getProperty` |
| Maven `-Ddemo.mode=x` does not reach Spring Boot | Build tool and app run in separate JVMs | Use `spring-boot.run.jvmArguments` or plugin `systemPropertyVariables` |
| Gradle `-Ddemo.mode=x` does not reach `bootRun` | Daemon JVM differs from application JVM | Use `bootRun.systemProperty`, mapped from `-P...` |
| `--spring.profiles.active=dev` has no effect | Put in JVM options/Gradle options or not forwarded to app | Place after JAR, use Maven run arguments or Gradle `--args` |
| Maven/Gradle `-Pprod` does not enable Spring profile | Build profile/project property is not a Spring runtime profile | Pass `--spring.profiles.active=prod` or `-Dspring.profiles.active=prod` to the right process |
| Option missing from `ApplicationArguments` | Not passed to the app, or malformed non-option syntax | Print `getSourceArgs()`/`getOptionNames()` and re-check command |
| IDE configuration differs from terminal | IDE uses different JVM/working dir/env or app args | Compare VM options, program args, environment, JDK |
| `Unrecognized VM option` error | JVM flag invalid for the JDK or placed incorrectly | Check `java -version`, test the option on the actual JDK |
| `--debug` passed, but debugger cannot attach | Spring Boot debug logging differs from JDWP | Configure JVM/IDE debugging via JDWP |
| App port change has no effect | No web server present or property overridden | Check web starter, Spring `Environment`, and property sources |
| Docker JVM option treated as app argument | `ENTRYPOINT` already placed `-jar` before appended args | Adjust `ENTRYPOINT` or appropriate JVM configuration variable |

### Quick Diagnostic Strategy

1. **Identify the process:** is the application JVM actually running, or only the Maven/Gradle JVM?
2. **Print raw args:** temporarily log `Arrays.toString(args)` or `ApplicationArguments.getSourceArgs()`.
3. **Print Java property:** `System.getProperty("demo.mode")`.
4. **Print Spring property:** `Environment.getProperty("demo.mode")` or Actuator `/actuator/env` if Actuator is present and access is appropriately secured.
5. **Inspect JVM settings** with an appropriate tool (such as `jcmd <pid> VM.flags` on supported JDKs), or JVM logs/options, instead of expecting `-Xmx` to appear in `args`.
6. **Verify ordering:** `java [options] -jar app.jar [args]`, and plugin/task parameters when running through Maven/Gradle.
7. In environments with multiple profiles/property sources, determine **which source wins** in the running application rather than looking only at `application.properties`.

When enabling diagnostic Actuator endpoints, configure access controls and sanitization/masking for sensitive values; do not expose all configuration or environment variables externally.

## 12. Cheat Sheet and Exercises

| What Do You Want to Do? | Correct Example | Where to Read It? |
|---|---|---|
| Change JVM heap limit | `java -Xmx512m -jar app.jar` | JVM/runtime settings, not in `args` |
| Set a Java system property | `java -Ddemo.mode=jvm -jar app.jar` | `System.getProperty("demo.mode")` |
| Pass a Spring configuration value | `java -jar app.jar --demo.mode=cli` | Spring `Environment` / `ApplicationArguments` |
| Pass a non-option argument | `java -jar app.jar hello` | `main(args)` / `getNonOptionArgs()` |
| Enable a Spring runtime profile | `java -jar app.jar --spring.profiles.active=dev` | Spring `Environment` |
| Set an OS environment variable | `DEMO_MODE=env java -jar app.jar` (Unix shell) | `System.getenv("DEMO_MODE")` and Spring `Environment` |
| Run app via Maven | `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev` | Spring Boot Maven Plugin passes profile to app |
| Run app via Gradle | `./gradlew bootRun --args="--spring.profiles.active=dev"` | Gradle `BootRun` passes app args |

**Self-check exercises:**

- Predict `System.getProperty("demo.mode")` and `Environment.getProperty("demo.mode")` when passing both `-Ddemo.mode=jvm` before the JAR and `--demo.mode=cli` after the JAR.
- Try running `ArgsBasics` with `-Ddemo.mode=late` before and after the main class; compare `args`.
- Run Spring Boot via Maven/Gradle, then change a value in turn at the **build tool property**, **child JVM system property**, and **application arguments**; observe which line changes.
- Change `--demo.mode=cli` to `--demo.mode=preview` while keeping `-Ddemo.mode=jvm`; verify why `System.getProperty` stays unchanged while Spring `Environment` changes.

**Key takeaway:** JVM options control the **Java Virtual Machine**, Java system properties are **key–value pairs inside the running JVM**, and application arguments are **strings passed to the `main` method**. Spring Boot also converts `--key=value` application arguments into prioritized configuration inside `Environment`. When running via Maven or Gradle, always determine first **whether a parameter is going to the build tool or the application JVM**.

### Official References

- [Java launcher — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot Maven Plugin — Running Your Application](https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html)
- [Spring Boot Gradle Plugin — Running Your Application](https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html)
- [Gradle — JavaExec task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html)