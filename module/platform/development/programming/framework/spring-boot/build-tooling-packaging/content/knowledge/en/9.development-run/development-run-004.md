# Passing Spring Profiles, Environment Variables, and Working Directory at Runtime

## 1. Purpose and Context

When developing a Spring Boot application, you often run **the exact same source code** across multiple contexts: a personal workstation, an integration environment, CI, or production. These contexts differ in database URLs, HTTP ports, logging, data paths, and external services. Instead of editing Java source code before every run, Spring Boot lets you configure applications via **Spring profiles**, **OS environment variables**, **JVM system properties**, **application arguments**, and **directory-based configuration files**.

This lesson focuses on **passing the right configuration to the application process at runtime**, whether using `java -jar`, `spring-boot:run`, Gradle `bootRun`, or the IDE Run button. In particular, the **working directory** affects how Java and Spring Boot resolve relative paths.

After this lesson, you will be able to:

- Enable one or more Spring profiles using `--spring.profiles.active=...`, `SPRING_PROFILES_ACTIVE`, and JVM `-Dspring.profiles.active=...`.
- Distinguish a **Spring profile**, a **Maven build profile**, and a **Gradle project property**.
- Pass OS env vars appropriately in Bash/zsh, Windows PowerShell, Command Prompt, and IDE configurations.
- Pass application arguments properly as distinct from JVM options and Maven/Gradle launcher properties.
- Specify the actual working directory of the application JVM, understanding `user.dir`, `Path.of(".")`, and file paths `file:./...`.
- Run the application with Maven/Gradle so that profiles, env vars, and working directory reach the **application's forked JVM**, not just the build tool's JVM.
- Recognize the precedence order among `application.properties`, profile-specific files, OS environment, Java system properties, and CLI arguments.
- Verify configuration safely via code/logs and diagnose failures to load the intended profile or file.

**Assumptions:** Java 17+, Spring Boot 3.5.x; the POM example uses Spring Boot **3.5.16** solely as a concrete release for hands-on practice, not to imply every project must use that exact version. Real projects should use the version approved by the development team and consult the corresponding documentation.

## 2. Distinguishing Four Layers: Profile, OS Env, JVM, and Cwd

### 2.1. Spring Profile

A **profile** is a context label such as `dev`, `test`, `prod`, or `local`. When the `dev` profile is active, Spring Boot considers configurations targeted to it, such as `application-dev.properties`, as well as beans annotated with `@Profile("dev")` if present.

Example:

~~~properties
# application.properties — base configuration
demo.message=base
~~~

~~~properties
# application-dev.properties — evaluated when the dev profile is active
demo.message=development
~~~

**Profile names do not automatically imply enforced environment guarantees:** `dev` or `prod` only have meaning according to the files, beans, and conventions your project defines. Enabling `prod` does not automatically turn an underconfigured application into a production-ready one.

### 2.2. OS Environment Variable

An environment variable is a name/value pair belonging to the environment of an **operating system process**. For example:

~~~text
SPRING_PROFILES_ACTIVE=dev
DEMO_MESSAGE=from-env
~~~

Spring Boot uses relaxed binding to interpret `SPRING_PROFILES_ACTIVE` as `spring.profiles.active` and `DEMO_MESSAGE` as `demo.message` when properties are read via `Environment` or bound to `@ConfigurationProperties`. Setting a variable in a shell **after** a process has already started does not automatically update the environment of the running Java process.

CI environments, IDEs, containers, and process managers also have their own mechanisms for declaring env vars. Do not set env vars in one terminal and expect an IDE-launched Java process to pick them up automatically.

### 2.3. JVM System Property and Application Argument

A **Java system property** is handled by the JVM via `-Dkey=value` before the main class name or `-jar`:

~~~bash
java -Dspring.profiles.active=dev -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

An **application argument** is passed to the program after the archive name:

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
~~~

In an application calling `SpringApplication.run(..., args)` without disabling command-line properties, Spring Boot parses arguments starting with `--` as configuration in `Environment`. Both approaches can activate a profile, yet **their position on the command line and their precedence differ**.

Do not mistakenly write:

~~~bash
# Wrong: placing -D after -jar and the archive path; the JVM does not treat it
# as a launcher system property in standard usage.
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar -Dspring.profiles.active=dev
~~~

The latter snippet merely illustrates an incorrect syntax for passing a JVM option; Spring Boot does not automatically treat `-Dspring.profiles.active=dev` as an application configuration argument equivalent to `--spring.profiles.active=dev`.

### 2.4. Working Directory

The **working directory / cwd** is the directory the operating system associates with the **Java process** at runtime. It affects relative paths such as:

- `Path.of("data/input.csv")` or `new File("data/input.csv")`.
- Spring Boot external config lookups in `./application.properties` and `./config/`.
- `file:./secrets/local.properties`, `file:./config/`, and paths defined by internal code.
- Certain libraries writing logs or temp files using relative paths.

The cwd is **not automatically the directory containing the JAR file**, not necessarily the repository root, and not the directory containing `pom.xml` if a build tool or IDE configures it otherwise.

## 3. Comparison Table of Configuration Mechanisms

| Mechanism | Example | Who Reads It? | When to Use |
| --- | --- | --- | --- |
| Profile via application argument | `--spring.profiles.active=dev` | Spring Boot app | Choosing a profile for a single run |
| Profile via OS env | `SPRING_PROFILES_ACTIVE=dev` | Spring Boot app | CI, containers, shell, IDE |
| Profile via JVM system property | `-Dspring.profiles.active=dev` | App JVM → Spring `Environment` | When controlling JVM options |
| Other app config via env | `DEMO_MESSAGE=hello` | Spring `Environment`/binder | Changing values without editing files |
| Configuration via CLI | `--demo.message=hello` | Spring Boot command-line property source | Per-invocation overrides |
| Working directory | `cd /workspace/run` before `java -jar ...` | OS/JVM and libraries using relative paths | Controlling `./config/`, `data/` |
| Maven run profile shortcut | `-Dspring-boot.run.profiles=dev` | Maven Spring Boot Plugin → app | When running `spring-boot:run` |
| Gradle `bootRun` application args | `--args='--spring.profiles.active=dev'` | Gradle `BootRun` task → app | When running `bootRun` |

**Note on similar names:** `spring-boot.run.profiles` is a **Maven plugin user property**, not a Spring `Environment` property. `spring.profiles.active` is a **Spring Boot application property**. Meanwhile, Maven's `-Pdev` selects a Maven build profile named `dev`; it does not automatically activate the Spring profile `dev`.

## 4. Profile-Based Configuration Model and Precedence Rules

Suppose the project has three files under `src/main/resources/`:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
~~~

Contents:

~~~properties
# application.properties
spring.application.name=launch-context-lab
demo.message=base
~~~

~~~properties
# application-dev.properties
demo.message=development
~~~

~~~properties
# application-prod.properties
demo.message=production
~~~

When no profile is active, `demo.message` equals `base`. When `dev` is enabled, the configuration from `application-dev.properties` overrides the base value to `development`, unless a higher-precedence configuration source overrides it.

### 4.1. Common Precedence Order

In a standard Spring Boot application, for the same key, the following sources typically increase in precedence:

~~~text
application.properties / application-{profile}.properties
                  <
OS environment variable
                  <
Java system property (-D...)
                  <
Spring Boot command-line option (--key=value)
~~~

For example, when the app reads `demo.message`:

- `application-dev.properties` has `development`.
- OS env `DEMO_MESSAGE=from-env` → the value read by the app is `from-env`.
- If the app JVM also has `-Ddemo.message=from-jvm` → `from-jvm` beats env.
- If an application argument `--demo.message=from-cli` is added → `from-cli` beats the sources above.

This is a **simplified order for the illustrative sources**. Spring Boot also supports other sources such as `SPRING_APPLICATION_JSON`, servlet config, test property sources, `@DynamicPropertySource`, and devtools settings; additionally, an application can customize how command-line options are handled. When resolving complex conflicts, inspect the actual `PropertySources` list rather than applying this diagram to every scenario.

### 4.2. Multiple Profiles and the Default Profile

Multiple profiles can be enabled:

~~~text
spring.profiles.active=dev,local
~~~

Spring Boot evaluates matching files such as `application-dev.properties` and `application-local.properties`. For properties with the same key, **a later profile can override an earlier one** according to config data and location group rules, so the order `dev,local` can matter.

If **no active profile is set**, Spring uses the default profile (named `default` by default). The file `application-default.properties` may be evaluated then. In Java, `environment.getActiveProfiles()` may return an empty array even while the `default` profile is in effect: **active profiles** and **default profiles** are two distinct concepts.

### 4.3. Do Not Misplace `spring.profiles.active`

`spring.profiles.active`, `spring.profiles.default`, and `spring.profiles.group.*` **must only be placed in profile-independent configuration documents**. Do not put `spring.profiles.active=prod` inside `application-dev.properties`, nor inside a YAML document gated with `spring.config.activate.on-profile`. Spring Boot may fail with a configuration error because this creates an invalid activation cycle.

Need to add profiles cumulatively in a regular file? Use `spring.profiles.include` or profile groups per the official documentation. These must also be placed in documents without profile activation conditions. Never assume `spring.profiles.active` merges across two sources: a higher-precedence property source usually **replaces** the lower-precedence value rather than concatenating strings.

## 5. Standalone Runnable Spring Boot Maven Example

The example below requires no web server or database; the application simply prints **active profiles, a demo property, and the working directory**, so you can verify everything directly in the terminal.

### 5.1. Project Structure

~~~text
launch-context-lab/
├── pom.xml
├── mvnw                       # If generated with Spring Initializr/Maven Wrapper
├── mvnw.cmd
└── src/
    └── main/
        ├── java/com/example/launchcontext/
        │   └── LaunchContextApplication.java
        └── resources/
            ├── application.properties
            ├── application-dev.properties
            └── application-prod.properties
~~~

### 5.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>launch-context-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

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
~~~

Using the starter parent manages dependency/plugin versions and binds `repackage`. Projects with a corporate parent can import the Spring Boot BOM and configure the plugin equivalently, but **that is a separate build decision** and does not affect how profiles, env vars, or working directory syntax work for the application.

### 5.3. `LaunchContextApplication.java`

Create `src/main/java/com/example/launchcontext/LaunchContextApplication.java`:

~~~java
package com.example.launchcontext;

import java.nio.file.Path;
import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LaunchContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(LaunchContextApplication.class, args);
    }

    @Bean
    ApplicationRunner printLaunchContext(Environment environment) {
        return args -> {
            System.out.println("activeProfiles="
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("demo.message="
                    + environment.getProperty("demo.message", "<unset>"));
            System.out.println("workingDirectory="
                    + Path.of("").toAbsolutePath().normalize());
            System.out.println("exampleRelativeFile="
                    + Path.of("data", "input.txt").toAbsolutePath().normalize());
        };
    }
}
~~~

This is a complete Java 17+ class for a Maven project configured with the Spring Boot starter. `@SpringBootApplication` initializes the context; `ApplicationRunner` executes after the context is built. The code **does not require `data/input.txt` to exist**: it only prints the absolute path to which that relative path would resolve. Thus you can experiment with changing the cwd without creating files first.

`Environment.getActiveProfiles()` returns the **list of active profiles**, while `Environment.getProperty("demo.message")` returns the final resolved value according to property source precedence. The code does not read passwords or print the entire `System.getenv()`, avoiding exposure of sensitive information.

### 5.4. Configuration Files

~~~properties
# src/main/resources/application.properties
spring.application.name=launch-context-lab
demo.message=base
~~~

~~~properties
# src/main/resources/application-dev.properties
demo.message=development
~~~

~~~properties
# src/main/resources/application-prod.properties
demo.message=production
~~~

### 5.5. Building with Maven

Linux/macOS, with the Maven Wrapper generated by Spring Initializr:

~~~bash
./mvnw clean package
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
~~~

If you created the project manually and **have no Wrapper**, substitute `mvn clean package` with an installed Maven and compatible JDK. Both require repository access on the first run if dependencies are not cached. The executable artifact per the sample POM is:

~~~text
target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

From here onward, the `java -jar` examples run the **application JVM directly** (as opposed to running via a plugin). Because the Spring Boot Maven Plugin runs `repackage`, the file can be executed with `java -jar`.

## 6. Running `java -jar` with Spring Profiles and Application Arguments

### 6.1. Linux/macOS — Command-Line Arguments

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev
~~~

The lines to observe printed by `ApplicationRunner` (listing only the predictable part):

~~~text
activeProfiles=[dev]
demo.message=development
~~~

The `workingDirectory=...` and `exampleRelativeFile=...` lines depend on the **machine's actual path** and do not have a universal fixed value across environments. Spring Boot startup logs may appear alongside them, so do not expect the entire stdout to match the example verbatim.

Set a configuration value directly from the CLI as well:

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev --demo.message=from-cli
~~~

Runner output for the two relevant lines:

~~~text
activeProfiles=[dev]
demo.message=from-cli
~~~

### 6.2. Windows PowerShell

~~~powershell
java -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
~~~

To add a second argument, place it after the JAR path:

~~~powershell
java -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev --demo.message=from-cli
~~~

The JAR filename must match the actual built artifact. If the Maven POM version or archive name configuration differs, use the real filename in `target/`.

### 6.3. Java System Properties (`-D`) Must Precede `-jar`

Linux/macOS:

~~~bash
java -Dspring.profiles.active=prod \
  -Ddemo.message=from-jvm \
  -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
java "-Dspring.profiles.active=prod" "-Ddemo.message=from-jvm" -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Runner lines:

~~~text
activeProfiles=[prod]
demo.message=from-jvm
~~~

A single command can include both JVM properties and application arguments; for the same key `demo.message`, the Spring Boot CLI option `--demo.message=...` generally has higher precedence than `-Ddemo.message=...`.

**Remember to distinguish:** `-Dspring.profiles.active=dev` before `-jar` is a JVM option. `--spring.profiles.active=dev` **after** the JAR is an application argument processed by Spring Boot.

## 7. Passing Environment Variables from the Terminal

### 7.1. Linux/macOS — Single Invocation Only

~~~bash
SPRING_PROFILES_ACTIVE=dev DEMO_MESSAGE=from-env \
  java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

This POSIX shell syntax sets environment variables **only for the invoked command's process**. Assuming the three config files from Section 5 are not overridden by another source, the runner lines are:

~~~text
activeProfiles=[dev]
demo.message=from-env
~~~

You can `export` them so subsequent child processes spawned by the shell inherit them:

~~~bash
export SPRING_PROFILES_ACTIVE=dev
export DEMO_MESSAGE=from-export
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

After practicing, clean up to avoid accidentally affecting other commands in the same shell:

~~~bash
unset SPRING_PROFILES_ACTIVE DEMO_MESSAGE
~~~

`export` affects only the current shell and its child processes; it **does not update the entire system**, other open terminals, or an IDE running in a separate process.

### 7.2. Windows PowerShell

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DEMO_MESSAGE = "from-powershell"
java -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Processes launched from this PowerShell session can receive the variables. Remove temporary variables from the shell environment afterward:

~~~powershell
Remove-Item Env:\SPRING_PROFILES_ACTIVE
Remove-Item Env:\DEMO_MESSAGE
~~~

`$env:NAME` is distinct from a regular PowerShell variable `$NAME`. Unix syntax `export NAME=value` **does not work like that in PowerShell**.

### 7.3. Windows Command Prompt (`cmd.exe`)

~~~bat
set SPRING_PROFILES_ACTIVE=dev
set DEMO_MESSAGE=from-cmd
java -jar target\launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Clear the variables after testing:

~~~bat
set SPRING_PROFILES_ACTIVE=
set DEMO_MESSAGE=
~~~

In CMD, `set NAME=value` differs from `setx`. `setx` persists variables for **future** processes/terminals and **does not update the current `cmd.exe` session**, so do not use it in place of `set` when testing a single run.

### 7.4. Mapping Variable Names to Spring Properties

Spring Boot relaxed binding supports canonical environment variable names derived from property names: replace dots with underscores, **remove dashes**, and convert to uppercase. Examples:

| Spring property (canonical) | OS env variable |
| --- | --- |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `demo.message` | `DEMO_MESSAGE` |
| `server.port` | `SERVER_PORT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `my.service[0].other` | `MY_SERVICE_0_OTHER` |

Do not automatically replace every `-` with an underscore when using `@ConfigurationProperties`: under the canonical rule, dashes are **removed**. Certain Spring properties have aliases or variants, so follow the documented convention to avoid hard-to-diagnose mismatches.

### 7.5. Environment Variables Apply Only from Parent Process at Startup

Each process receives a snapshot of its environment when created. If the application is already running and you open another terminal and type `export SPRING_PROFILES_ACTIVE=prod`, the running application **does not switch profiles automatically**. You generally must stop and restart the application. Spring profiles are resolved during context startup, not as a live runtime environment toggle.

## 8. Running via Maven `spring-boot:run`

When using Maven, `spring-boot:run` compiles and runs the application during development. The Spring Boot Maven Plugin has **dedicated** parameters to pass configuration to the application process.

### 8.1. Standard Way to Pass Profiles via Maven Plugin

Linux/macOS (in the module containing the Spring Boot app):

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=dev"
~~~

**`-Dspring-boot.run.profiles=dev` is a parameter for the Maven plugin**, which then forwards the profile to the app. Do not confuse it with `-Dspring.profiles.active=dev` on the Maven command line: the latter is primarily a system property of the **Maven JVM** and is not guaranteed to pass properly to the forked application JVM.

To enable multiple profiles:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev,local
~~~

Even if the project has no `application-local.properties`, you can still activate `local`; its effect depends on your actual configurations and beans.

### 8.2. Passing Application Arguments via Maven

~~~bash
./mvnw spring-boot:run \
  "-Dspring-boot.run.arguments=--spring.profiles.active=dev --demo.message=from-maven-args"
~~~

In Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.arguments=--spring.profiles.active=dev --demo.message=from-maven-args"
~~~

The plugin takes the arguments string, splits it according to its syntax, and passes it to the application. Use quotes so an argument containing spaces is sent as **one Maven `-D` property** instead of being split by the shell into multiple Maven goals. If an app argument value has spaces or nested quotes, test a simple argument first and check quoting rules for your plugin and shell.

### 8.3. Passing JVM Arguments to the Application JVM

~~~bash
./mvnw spring-boot:run \
  "-Dspring-boot.run.jvmArguments=-Dspring.profiles.active=dev -Ddemo.message=from-jvm"
~~~

`spring-boot.run.jvmArguments` passes JVM flags to the Java process forked by the plugin. This differs from passing `-Dspring.profiles.active` directly to the **Maven launcher**.

### 8.4. Passing OS Env to Maven and the App

~~~bash
SPRING_PROFILES_ACTIVE=dev DEMO_MESSAGE=from-env ./mvnw spring-boot:run
~~~

The Maven process starts with these environment variables, and `spring-boot:run` normally forks a child process that inherits the environment. You can also declare env vars **specifically for the app** in the plugin configuration if stable values are needed.

Example snippet in `pom.xml`, placed inside the `<plugin>` block of `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <environmentVariables>
        <DEMO_MESSAGE>from-plugin-env</DEMO_MESSAGE>
    </environmentVariables>
    <workingDirectory>${project.basedir}/run-data</workingDirectory>
</configuration>
~~~

This is an **XML snippet**, not a complete POM. The `run-data` directory must exist beforehand, or process creation may fail. Plugin configuration can override the parent process environment for identical variable names. **Do not hardcode passwords or tokens in `pom.xml`**; use proper secret management or CI injection.

### 8.5. Changing Working Directory with the Maven Plugin

The Spring Boot Maven Plugin supports the `spring-boot.run.workingDirectory` user property. On Linux/macOS, assuming the directory already exists:

~~~bash
mkdir -p run-data
./mvnw spring-boot:run \
  "-Dspring-boot.run.workingDirectory=${PWD}/run-data"
~~~

Note: the line above uses the POSIX shell expression `${PWD}`, which differs from Maven's `${project.basedir}` inside the POM. Content inside **double quotes** in bash/zsh is interpolated by the shell before being passed to Maven. If you need a guaranteed absolute path, run `pwd` and supply the literal path rather than relying on shell environment expansion.

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\run-data | Out-Null
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.workingDirectory=$((Resolve-Path .\run-data).Path)"
~~~

The Maven plugin itself sets **`workingDirectory`** for the application run process. If unconfigured, according to the plugin documentation, it defaults to the **Maven project/module `basedir`**; this may differ from your current directory if you are at the repository root of a multi-module build.

**Important distinction:** running `cd ..` changes the shell's current directory before invoking Maven; the plugin may still choose the module `basedir` as the app's cwd. For consistency, use `spring-boot.run.workingDirectory` or configure it on the plugin.

### 8.6. Equivalent Usage in Multi-Module Maven

Suppose the repository has a `service` module containing the Spring Boot main class:

~~~bash
./mvnw -pl service spring-boot:run -Dspring-boot.run.profiles=dev
~~~

`-pl` selects the module; the project build must have the plugin configured and dependencies ready. For internal dependencies not yet built/installed to the local repo, run an appropriate reactor build first. The `run` plugin relies on the actually selected module and does not run every main class across the repository.

## 9. Running via Gradle `bootRun`

The Spring Boot Gradle Plugin creates the `bootRun` task when the Java plugin is applied. `bootRun` inherits `JavaExec` behavior: **application args**, **JVM system props**, **environment variables**, and **`workingDir`** can all be set for the application process.

### 9.1. Passing Application Arguments

Linux/macOS:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=dev'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun "--args=--spring.profiles.active=dev"
~~~

Add another property inside the same arguments string:

~~~bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --demo.message=from-gradle-args'
~~~

These are **arguments for the Java application**, not JVM options for the Gradle process. `--args` is the Gradle `JavaExec` mechanism used by the Spring Boot Gradle Plugin.

### 9.2. Passing Env Variables from the Terminal

Linux/macOS:

~~~bash
SPRING_PROFILES_ACTIVE=dev DEMO_MESSAGE=from-env ./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DEMO_MESSAGE = "from-env"
.\gradlew.bat bootRun
~~~

By default, a `JavaExec` task uses the build process's environment, and you can add or override specific values via `environment(...)`. When a Gradle daemon or build tool is already running, still verify the actual environment `bootRun` receives; if local/IDE/CI discrepancies occur, set them explicitly in the task configuration.

### 9.3. Gradle Groovy DSL Configuration

In `build.gradle` of the **Spring Boot application module**, for example:

~~~groovy
tasks.named('bootRun') {
    systemProperty 'spring.profiles.active', 'dev'
    environment 'DEMO_MESSAGE', 'from-gradle-task'
    workingDir = file('run-data')
}
~~~

The `run-data` directory must exist; create it beforehand with `mkdir -p run-data` on Linux/macOS or via File Explorer/PowerShell on Windows. `workingDir = file('run-data')` sets the cwd of the **application JVM**; `JavaExec` defaults to the project directory if left unconfigured.

### 9.4. Gradle Kotlin DSL Configuration

In `build.gradle.kts`:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    systemProperty("spring.profiles.active", "dev")
    environment("DEMO_MESSAGE", "from-gradle-task")
    workingDir = file("run-data")
}
~~~

This is a **Gradle build configuration** snippet, not a standalone Kotlin program. Ensure the Spring Boot Gradle plugin is applied so the `bootRun` task actually exists.

### 9.5. Gradle Project Properties Differ from Spring Properties

The command:

~~~bash
./gradlew bootRun -Pmode=dev
~~~

only sets a **Gradle project property** named `mode`. It **does not automatically** enable a Spring profile. If you explicitly bridge the Gradle property to the application JVM, you can configure:

~~~groovy
tasks.named('bootRun') {
    systemProperty 'spring.profiles.active', findProperty('mode') ?: 'dev'
}
~~~

Only then does `-Pmode=prod` take effect via that Gradle configuration. If the task already sets `systemProperty('spring.profiles.active','dev')` and you also pass CLI app args `--spring.profiles.active=prod`, Spring Boot's command-line property source usually takes higher precedence than JVM properties, so the app uses `prod`.

### 9.6. Gradle and Maven Launcher `-D` Flags Do Not Auto-Forward to the App

With build-tool commands:

~~~bash
# Do not use the commands below as the standard way to set an app profile:
./gradlew bootRun -Dspring.profiles.active=dev
./mvnw spring-boot:run -Dspring.profiles.active=dev
~~~

`-D` in this position is interpreted by the build tool as a system property of the **Gradle/Maven launcher**. Because `bootRun`/`spring-boot:run` use separate fork/process mechanisms, do not assume it behaves like `java -D... -jar ...`. Use `--args`, task `systemProperty`, or Maven plugin `spring-boot.run.profiles` / `spring-boot.run.jvmArguments`.

## 10. Running in an IDE: Working Directory, VM Options, Environment

IDEs like IntelliJ IDEA, Eclipse/STS, and VS Code with Java/Spring extensions have different configuration UIs, yet the general meaning of a **Run Configuration** includes:

- **Main class:** the `@SpringBootApplication` class with `public static void main`.
- **Program arguments:** strings passed to `String[] args`, e.g., `--spring.profiles.active=dev --demo.message=from-ide`.
- **VM options / JVM arguments:** e.g., `-Dspring.profiles.active=dev -Dfile.encoding=UTF-8`.
- **Environment variables:** e.g., `SPRING_PROFILES_ACTIVE=dev` and `DEMO_MESSAGE=from-ide-env`.
- **Working directory:** choose the project/module/`run-data` directory where relative files and `./config/` are searched.
- **Module/classpath/JDK:** choose the right module and compatible JDK, without confusing it with the Gradle/Maven import JDK or the IDE runtime JDK.

Crucially, open the **Run Configuration for the Spring Boot process itself**, rather than only changing Maven/Gradle Runner VM options in the IDE. An IDE might run via a Spring Boot Run Configuration, a Gradle task, or a Maven plugin; each path uses its own mechanism for args, env, and cwd.

### Comparison Example

In the application's Run Configuration:

~~~text
Program arguments: --spring.profiles.active=dev
VM options:        -Ddemo.message=from-ide-jvm
Environment:       DEMO_MESSAGE=from-ide-env
Working directory: /absolute/path/to/launch-context-lab/run-data
~~~

With `application-dev.properties`, the application runner prints profile `[dev]` and `demo.message=from-ide-jvm` (the JVM property beats env, and no `--demo.message` overrides it), while the cwd points to the selected `run-data` directory. If you add `--demo.message=from-cli` under Program arguments, the value changes to `from-cli`.

Never commit Run Configurations containing secrets or plaintext credentials to a shared repository. If the team shares run configs, store variable names or external references; supply secret values through secure local or CI mechanisms.

## 11. Working Directory and How Spring Boot Discovers Config

### 11.1. The JAR Directory Differs from the Working Directory

Suppose the executable file is at:

~~~text
/workspace/launch-context-lab/target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

You create a separate run directory and place external config files outside the JAR:

~~~text
/workspace/run-local/
├── application.properties
├── config/
│   └── application-dev.properties
└── data/
    └── input.txt
~~~

On Linux/macOS:

~~~bash
cd /workspace/run-local
java -jar /workspace/launch-context-lab/target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev
~~~

Here the working directory is **`/workspace/run-local`**, not the JAR's `target` directory. `Path.of("data/input.txt")` resolves under `/workspace/run-local/data`. Spring Boot can find external config outside the JAR at `./application.properties` and `./config/application-dev.properties` according to its default config locations.

If `demo.message` in the external config differs from the file packaged inside the JAR, the profile-specific external file can override the value inside the JAR, unless a higher-precedence source such as OS env, JVM, or CLI overrides it.

**Note:** on Windows, do not copy the POSIX paths in this example literally; use actual Windows directory paths and quote them if they contain spaces.

### 11.2. How Java Verifies the Cwd

Java API:

~~~java
Path workDir = Path.of("").toAbsolutePath().normalize();
System.out.println(workDir);
~~~

This is a **Java snippet inside a class/method** (not a standalone full Java file); the sample class in Section 5 has the complete code. `System.getProperty("user.dir")` typically reflects the JVM's directory at startup, but **do not use `-Duser.dir=...` as a substitute for actually changing the process's cwd**. Change the working directory using shell `cd`, IDE Run Configuration, or the build tool's plugin/task option.

Meanwhile, `classpath:application.properties` is a resource on the Java classpath (usually inside the JAR), not a filesystem path relative to the cwd. Do not confuse `classpath:...` with `file:./...`.

### 11.3. Default Configuration Search Locations

Spring Boot looks for `application.properties`/`application.yaml` across several classpath and filesystem locations, including:

- Classpath root and `classpath:/config/`.
- Current working directory `./`.
- The `./config/` directory.
- Immediate subdirectories under `./config/` (wildcard locations) per config data rules.

When a profile is enabled, Spring Boot also considers `application-{profile}.properties`/`.yaml` variants. **External profile-specific config can override packaged base config**; exact ordering also depends on location groups and multiple config sources. Do not guess solely based on "the file closest to the JAR."

### 11.4. Specifying External Config Paths

There are two key properties, read **very early at startup**:

- `spring.config.location`: **replaces** the default search locations.
- `spring.config.additional-location`: **adds** locations in addition to the default locations.

Example adding an external config directory on Linux/macOS:

~~~bash
java -jar /absolute/path/app.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=optional:file:/workspace/run-local/custom-config/
~~~

`/absolute/path/app.jar` here is an **illustrative path** that must be replaced with a real artifact. The trailing `/` on directory locations is important so Boot appends `application*.properties` properly. The `optional:` prefix permits a missing directory without failing; **do not use `optional:` if missing config must cause the application to fail-fast**.

A relative example tied to the cwd:

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./local-config/ \
  --spring.profiles.active=dev
~~~

The second command assumes you are at the root containing `target/...jar` and optionally `./local-config/`. If you change the cwd, both the JAR path and `./local-config/` resolve relative to the new cwd. Do not alter source code to work around a problem that is purely caused by the working directory.

With env vars:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:./local-config/ \
  SPRING_PROFILES_ACTIVE=dev \
  java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

**Do not place `spring.config.location` or `spring.config.additional-location` inside the profile-specific file expected to be loaded by it**. Because Boot needs to resolve locations early, supply them via OS env, JVM system property, or command-line arguments at startup.

## 12. Configuration Result Verification Matrix

Consider the sample `application.properties` and `application-dev.properties` in Section 5, with no other external config and command-line properties still enabled.

| Run Scenario | Active Profiles | `demo.message` Read by App |
| --- | --- | --- |
| No profile/env passed | `[]` (empty active array) | `base` |
| CLI `--spring.profiles.active=dev` | `[dev]` | `development` |
| Env `SPRING_PROFILES_ACTIVE=dev` | `[dev]` | `development` |
| Env `SPRING_PROFILES_ACTIVE=dev` + `DEMO_MESSAGE=from-env` | `[dev]` | `from-env` |
| App JVM `-Dspring.profiles.active=prod` | `[prod]` | `production` |
| Env `DEMO_MESSAGE=from-env` + App JVM `-Ddemo.message=from-jvm` | Per active profile | `from-jvm` |
| App JVM `-Ddemo.message=from-jvm` + CLI `--demo.message=from-cli` | Per active profile | `from-cli` |
| CLI `--spring.profiles.active=dev,prod` | `[dev, prod]` | `production` for the same key under normal location-group rules |

The table assumes the app has no additional property sources or overrides in tests or `SpringApplication` customizations. The multi-profile row illustrates the "last profile wins" rule under standard config locations. If external files or `spring.config.import` are used, ordering can be more nuanced.

### 12.1. Verifying in Code Instead of Guessing

In the sample application:

~~~java
environment.getActiveProfiles();
environment.getProperty("demo.message");
Path.of("").toAbsolutePath().normalize();
~~~

are three valuable observations to separate:
1. **Which profiles are actually active?**
2. **Which Spring property value is ultimately resolved?**
3. **In which directory is the app JVM running?**

To inspect which source provided a property during development, you can enable the Actuator `env` endpoint in a **controlled manner** and check origins/property sources. **Do not expose the Actuator `env` endpoint publicly or dump the entire environment in production**: it can contain sensitive information even when some values are masked.

## 13. Security and Safe Operations

Environment variables are convenient but **not inherently secret**. Values can leak through logs, crash reports, debugging tools, process inspection, or environment management policies. Command-line options in particular can remain in shell history and appear in process listings.

Recommendations:

- Use non-sensitive examples like `DEMO_MESSAGE` for learning and testing.
- Use a secret manager, credential store, or CI secret injection for database passwords and API tokens; do not commit them in `pom.xml`, `build.gradle`, `application-prod.properties`, or shared IDE Run Configurations.
- Distinguish `@Profile("prod")` from security controls: profiles only conditionalize configs and beans; they **do not prove** an application is secure for deployment.
- Avoid setting `prod` as the default when running locally; use safe development config and validate external dependencies.
- If config must be stored outside the JAR, restrict filesystem permissions and ensure a trusted working directory. Relative paths can shift when a startup script or process manager uses a different cwd.
- Log profiles, cwd, and **non-sensitive** properties for debugging instead of dumping `System.getenv()` or the full Spring `Environment`.

## 14. Troubleshooting: Profile, Env, and Working Directory Errors

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `application-dev.properties` is not loaded | `dev` is not active, or wrong filename/path | Print `getActiveProfiles()`, check `src/main/resources` and the JAR |
| `SPRING_PROFILES_ACTIVE` set, still running `prod` | Higher-precedence CLI/JVM property, or env set on wrong process | Check arguments, JVM options, and the app process environment |
| Maven `-Dspring.profiles.active=dev` has no effect | Property placed on Maven launcher while app runs forked | Use `-Dspring-boot.run.profiles=dev` or plugin `jvmArguments` |
| Gradle `-Dspring.profiles.active=dev` has no effect | Gradle JVM != `BootRun` app JVM | Use `bootRun --args` or task `systemProperty` |
| Spring profile differs from Maven profile | Confused `mvn -Pdev` with `spring.profiles.active` | Inspect Maven POM profiles and pass the Spring profile explicitly |
| IDE shows `dev` while terminal runs `base` | Run Configuration applies only to the IDE | Put flags/env into terminal command or centralize launch config |
| IDE does not see newly `export`ed env vars | IDE launched from another process and did not inherit the shell | Declare env in IDE Run Configuration or launch IDE from that environment |
| `FileNotFoundException` for `data/input.txt` | Cwd differs from expectation | Print `Path.of("").toAbsolutePath()`, select the right working directory |
| `spring.config.location` drops config packaged in JAR | That property replaces default locations | Use `spring.config.additional-location` to append instead |
| Boot throws `ConfigDataLocationNotFoundException` | Required location does not exist | Check path/cwd; use `optional:` only if missing config is allowed |
| `DEMO_MESSAGE` env set, `demo.message` unchanged | Wrong shell syntax, overridden by higher-precedence source, or wrong process | Check process env, CLI/JVM properties, and Spring output |
| Windows `export` command fails | Shell is PowerShell or CMD | Use `$env:VAR` or `set VAR=value` |
| Maven/Gradle cannot find module/main class | Running in wrong module/root or plugin unconfigured | Confirm build working dir, module, main class, and plugin |
| Enabling `dev,prod` gives unexpected value | Multiple profiles, external locations, location groups | Check profile order and property-source origins |
| Changing `SPRING_PROFILES_ACTIVE` while running does nothing | OS env is captured at process start; context already initialized | Restart the process with the new configuration |
| `-Duser.dir=/path` does not help find relative files | Does not reliably change the OS-level cwd | Use `cd`, IDE working directory, or plugin/task `workingDir` |

### Short Diagnostic Workflow

**Step 1 — Identify the launch path:** `java -jar`, Maven plugin, Gradle task, or IDE? Each passes arguments and JVM options differently.

**Step 2 — Verify what the app actually received:** Print `Environment.getActiveProfiles()`, a sample config property, and `Path.of("").toAbsolutePath()`. Do not inspect only the build command flags.

**Step 3 — Trace property sources:** If the value is wrong even though the profile is right, trace CLI → app JVM `-D` → OS env → external config → packaged config. Watch for `spring.config.import`, external locations, and multiple profiles.

**Step 4 — Check the filesystem:** Print the cwd and verify the file exists at the path **relative to the app's cwd**, not merely the cwd of a terminal opened later.

**Step 5 — Compare local vs. CI:** align JDK, Spring Boot plugin version, shell, working dir, environment variables, file permissions, and deployment conventions. Do not modify source code to mask a launch configuration error.

## 15. Practice Exercises

**Exercise 1 — Basic Profile:** Build the project from Section 5 and run it with `--spring.profiles.active=dev`. Verify `activeProfiles=[dev]` and `demo.message=development`. Switch to `prod` and predict `demo.message=production`.

**Exercise 2 — Env Beats File:** In Bash/PowerShell, set `SPRING_PROFILES_ACTIVE=dev` and `DEMO_MESSAGE=from-env` before running the JAR. Record both output lines; explain why `development` is no longer shown even though the `dev` profile is active.

**Exercise 3 — Comparing JVM and CLI:** Run `java -Ddemo.message=from-jvm -jar ... --demo.message=from-cli`. Predict the final value and explain the precedence order. Remember that JVM `-D` must precede `-jar`.

**Exercise 4 — Working Directory:** Create a `run-data` directory and run the application from inside it using an **absolute path** to the JAR. Observe how `exampleRelativeFile` changes. Prove that the JAR path and the working directory are independent.

**Exercise 5 — Maven Plugin:** Run `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev` at the project root. Try `spring-boot.run.workingDirectory` and observe the cwd. Do not pass a system property only to the Maven launcher expecting the app to inherit it.

**Exercise 6 — Gradle Plugin:** In an equivalent Spring Boot Gradle project, use `bootRun --args='--spring.profiles.active=dev'`. Then declare task `environment` and `workingDir`, and compare against running from the IDE.

**Exercise 7 — External Config:** Create `run-data/config/application-dev.properties` containing `demo.message=external-dev`, run the JAR with cwd `run-data`, and pass no CLI/JVM/env override for that key. Verify the external value overrides the packaged config. Then add `--demo.message=explicit` and verify CLI wins.

## 16. Checklist Before Finalizing Launch Configuration

- [ ] Selected the right launch method: JAR, Maven plugin, Gradle task, or IDE.
- [ ] Passed the Spring profile **to the application**, not confused with a build-tool profile/property.
- [ ] Placed `-D...` on the right JVM (before `-jar` when invoking Java directly).
- [ ] Used the proper env syntax for Bash/zsh, PowerShell, or CMD.
- [ ] Confirmed the Java process actually receives env vars; did not rely on another terminal/IDE.
- [ ] Identified the actual working directory and all critical relative paths.
- [ ] Distinguished `spring.config.location` (replaces) from `spring.config.additional-location` (adds).
- [ ] Verified precedence across CLI/JVM/env/files and multiple profiles.
- [ ] Did not put `spring.profiles.active` inside a profile-specific document.
- [ ] Did not hardcode or log secrets in committed config or logs.
- [ ] When errors occurred, checked the app's `activeProfiles`, `demo.message`, and `workingDirectory` output.

## 17. Official Documentation

- Spring Boot 3.5 — Profiles: https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html
- Spring Boot 3.5 — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot Maven Plugin — Running Your Application: https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html
- Spring Boot Gradle Plugin — Running Your Application: https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html
- Gradle JavaExec — workingDir, environment, args, systemProperty: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html
- Spring Boot 3.5 — Running Your Application: https://docs.spring.io/spring-boot/3.5/reference/using/running-your-application.html

**Core takeaway:** Spring profiles are **application-level** configuration; OS environment, JVM system properties, and CLI options are **delivery channels for values**; and the working directory is a **property of the running process**. During development, verify which profile, env, and cwd the application actually receives through observed logs and runtime behavior, rather than merely inspecting the Maven, Gradle, or IDE launch command.