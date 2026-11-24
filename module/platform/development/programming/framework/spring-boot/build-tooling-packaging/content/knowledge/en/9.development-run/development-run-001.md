# Running the Application During Development with `spring-boot:run` and `bootRun`

## 1. Two Commands with the Same Goal, Two Different Build Mechanisms

When developing a Spring Boot application, developers often need to start it directly from compiled code, inspect logs, call endpoints, attach a debugger, and edit code quickly. There are two approaches corresponding to the project's build tool:

- **Maven:** `./mvnw spring-boot:run` invokes the `run` goal of `spring-boot-maven-plugin`.
- **Gradle:** `./gradlew bootRun` invokes the `bootRun` task created by the Spring Boot Gradle plugin when combined with the Java plugin.

Both run **the application from classes/resources and runtime dependencies prepared by the build tool**, usually without needing to create an executable JAR first. They are intended for the **local development loop**, as opposed to testing a packaged artifact with `java -jar`.

A successful `spring-boot:run` or `bootRun` shows that the application can start on the **development classpath** with the currently applied configuration. It **does not** automatically prove that unit tests pass, the JAR contents are correct, the production environment is compatible, or an executable archive has been created.

| Criterion | Maven: `spring-boot:run` | Gradle: `bootRun` |
| --- | --- | --- |
| Nature | Goal of the Spring Boot Maven Plugin. | Task of type `BootRun` extending `JavaExec`. |
| Build definition | `pom.xml`. | `build.gradle` / `build.gradle.kts`. |
| Command | `./mvnw spring-boot:run`. | `./gradlew bootRun`. |
| Runtime | The application JVM is forked by the Maven plugin; the goal usually holds the terminal while the web app is running. | `JavaExec` runs a child JVM; the task usually holds the terminal while the web app is running. |
| Classpath | Classes/resources and runtime dependencies resolved by Maven. | Main source set runtime classpath. |
| Passing Spring arguments | `-Dspring-boot.run.arguments="--server.port=18085"`. | `--args="--server.port=18085"`. |
| Selecting profiles | `-Dspring-boot.run.profiles=dev`. | `--args="--spring.profiles.active=dev"`. |
| JVM arguments | `-Dspring-boot.run.jvmArguments="..."`. | `jvmArgs(...)`, `systemProperty(...)`, `debugOptions`. |
| Main class | Auto-detected by the plugin or configured via `mainClass`. | Auto-detected by the task or configured via `bootRun.mainClass`. |
| Resource reload | DevTools, `addResources` option. | DevTools, `sourceResources` option. |
| Packaging | `mvn package` + Boot `repackage` is a separate step. | `bootJar`/`build` is a separate step. |

**How to choose:** use the Wrapper chosen by the repository. A Maven project does not need Gradle; a Gradle project does not need Maven. This guide uses the same Java application for comparison, but each build definition is an independent choice.

### 1.1. Three Parameter Layers to Distinguish

~~~text
Shell / build-tool command
   |-- Maven -D... or Gradle -P...       -> configures the build tool/plugin/task
   |-- plugin/task passes JVM arguments  -> application JVM: -Xmx, -Dfoo=bar, JDWP
   '-- plugin/task passes app arguments  -> main(String[] args): --server.port, --spring.profiles.active
                                         |
                                     Spring Boot Environment
~~~

- **A build tool property** is not automatically a Java system property of the app.
- **A JVM argument** affects the Java process running the application, such as heap, debug, or `-Ddemo.mode=local`.
- **An application argument** is a string passed to `main(String[] args)`; Spring Boot processes `--server.port` and `--spring.profiles.active` as configuration properties.
- **An environment variable** is inherited by the child JVM from the shell if present, and Spring Boot can read it as a property source.

Confusing these layers is a common reason why adding `-Dserver.port=18085` or `-Pport=18085` still leaves the server listening on another port.

## 2. Preparing the Right Toolchain and Test Model

The examples use **Spring Boot 3.3.13 and Java 17** as a fixed version set so the exercises are easy to reproduce. These are illustrative versions only, not a claim about the latest or currently supported release line. For real projects, choose the Spring Boot, Maven/Gradle, and JDK versions supported by your organization.

Requirements:

1. Have a real Java entrypoint calling `SpringApplication.run(...)`.
2. Have the appropriate Spring Boot build plugin and starter. The build plugin and starter dependency serve two different functions.
3. Have the Maven/Gradle Wrapper present in the source repository and executable.
4. Have a build and runtime JDK compatible with Spring Boot and the classfile version.
5. For Web apps, have an available HTTP port (for example, **18085**); for Batch/CLI apps, verify job execution or exit code instead of HTTP.
6. If the app depends on a DB, broker, or external service, the local environment must have those dependencies or suitable test doubles.

### 2.1. Common Code Structure

In the project, choose **one of the two** formats, POM or Gradle:

~~~text
dev-run-demo/
  pom.xml                       # Maven, if Maven is chosen
  # or:
  settings.gradle               # Gradle, if Gradle is chosen
  build.gradle
  src/main/java/com/example/devrun/DevRunApplication.java
  src/test/java/com/example/devrun/DevRunApplicationTest.java
~~~

Maven requires `mvnw`/`mvnw.cmd` and `.mvn/wrapper/...`; Gradle requires `gradlew`/`gradlew.bat` and `gradle/wrapper/...`. The wrapper is part of the project and is not automatically generated from `pom.xml` or `build.gradle`.

File `src/main/java/com/example/devrun/DevRunApplication.java`:

~~~java
package com.example.devrun;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DevRunApplication {
    private final Environment environment;

    public DevRunApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(DevRunApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/active-profiles")
    public String activeProfiles() {
        String[] active = environment.getActiveProfiles();
        return active.length == 0 ? "default" : String.join(",", active);
    }
}
~~~

This is a **complete Java class in a Spring Boot project that already has its dependencies**, not a standalone file run with `javac` without a classpath. `@SpringBootApplication` configures the application, and `@RestController` exposes two HTTP handlers. `/ping` returns the body **`pong`**. `/active-profiles` reads the active profiles from the Spring `Environment`: if there are no active profiles, it returns the string `default` according to the handler logic; when only the `dev` profile is enabled, it returns `dev`.

File `src/test/java/com/example/devrun/DevRunApplicationTest.java`:

~~~java
package com.example.devrun;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DevRunApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

The test initializes the Spring test context and simulates HTTP via **MockMvc**: it checks mappings/responses **without opening a real HTTP port**. Therefore, you also need to test the development run command and call `curl` from another terminal.

## 3. Maven: Complete POM and How to Invoke `spring-boot:run`

With `spring-boot-starter-parent`, Maven manages compatible dependency and plugin versions. Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dev-run-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

Explanation:

- Starter Web brings Spring MVC and the embedded web server onto the runtime classpath; starter Test provides JUnit and MockMvc tools in test scope.
- The parent manages compatible dependency versions and many plugin defaults, including `repackage` capability when the plugin is declared.
- `spring-boot-maven-plugin` provides the `run` goal. There is no Maven lifecycle phase named `run`: invoke **`spring-boot:run`**, not `mvn run`.
- If your company uses a corporate parent and **only imports the BOM**, the BOM mainly manages dependency versions and **does not automatically declare the Spring Boot Maven plugin**. You must configure the plugin and version in your POM or custom parent.

### 3.1. Run Commands and Configuration Adjustments

~~~bash
# macOS/Linux; at the application root containing the Maven Wrapper
./mvnw -version

# Default run (Spring Boot Web typically uses 8080 unless configured otherwise)
./mvnw spring-boot:run

# Choose HTTP port
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"

# Enable the dev profile using the dedicated shortcut
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev

# Change both the port and enable the dev profile
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.profiles.active=dev"
~~~

Run only **one instance on the same port**. Each line is an alternative invocation; stop the previous run before starting the next. On Windows, change `./mvnw` to `mvnw.cmd`; quote escaping may differ between PowerShell and cmd, so inspect the actual string Maven receives.

After a successful startup log, in a second terminal:

~~~bash
curl -i http://localhost:18085/ping
curl -i http://localhost:18085/active-profiles
~~~

When running with `--spring.profiles.active=dev`, expect HTTP 200 with bodies **`pong`** and **`dev`** respectively, assuming no other active profile is added by environment configuration. HTTP headers, startup PID, and timestamps are not fixed outputs. If the app runs on the default port 8080, use 8080 in the URL.

### 3.2. Maven JVM Arguments Are Not Maven User Properties

The Spring Boot Maven Plugin runs the app in a **forked JVM**. Use:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx512m -Ddemo.mode=local"
~~~

Here `spring-boot.run.jvmArguments` is a Maven property read by the **plugin**, which then passes `-Xmx512m` and `-Ddemo.mode=local` to the application JVM. Conversely:

~~~bash
./mvnw spring-boot:run -Ddemo.mode=local
~~~

`-Ddemo.mode=local` only goes directly to **Maven user properties** and does not guarantee that the forked app JVM receives that value. To pass properties into the app, use `spring-boot.run.jvmArguments`, configure `systemPropertyVariables`, environment variables, or application args depending on your purpose.

Select multiple Spring profiles with `-Dspring-boot.run.profiles=dev,local` (comma-separated). Do not confuse this with `mvn -Pdev`: that is a **Maven build profile** and does not automatically activate `spring.profiles.active=dev` unless the POM explicitly maps it.

### 3.3. Configuring the Goal via POM

The following fragment can be added **inside** the `<plugin>` declaration for the Spring Boot Maven plugin:

~~~xml
<configuration>
    <arguments>
        <argument>--server.port=18085</argument>
    </arguments>
    <profiles>
        <profile>dev</profile>
    </profiles>
    <jvmArguments>-Xmx512m</jvmArguments>
</configuration>
~~~

This is a **configuration fragment**, not a standalone `pom.xml`. It sets defaults for the `run` goal in the project. Do not hardcode passwords or secrets in the POM. For environment settings that change frequently, prefer CLI/env over committing personal ports or profiles into source control.

## 4. Gradle: Build Script and How to Invoke `bootRun`

With the Gradle Groovy DSL, `bootRun` is a task subclassing `JavaExec`; it uses the **main source set runtime classpath** and can automatically locate the class containing `public static void main(String[])`. The Boot plugin must be applied together with the Java plugin in the application module.

`settings.gradle`:

~~~groovy
rootProject.name = 'dev-run-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Java plugin creates compile/test source sets and the task graph. The Spring Boot plugin creates `bootRun`/`bootJar`; the dependency-management plugin coordinates with Boot to manage starter versions. The Java toolchain requires a compatible JDK 17 or appropriate Gradle toolchain provisioning. The `bootRun` task is different from the `run` task of the Gradle Application plugin.

### 4.1. Gradle Commands

~~~bash
./gradlew --version
./gradlew tasks --all

# Run the application from the main classpath
./gradlew bootRun

# Change the HTTP port
./gradlew bootRun --args="--server.port=18085"

# Enable the dev profile
./gradlew bootRun --args="--spring.profiles.active=dev"

# Change both the port and profile
./gradlew bootRun --args="--server.port=18085 --spring.profiles.active=dev"
~~~

`--args` is an option belonging to `JavaExec/BootRun`, not Maven's `spring-boot.run.arguments`. Gradle apps use `gradlew.bat` on Windows. In PowerShell, quotes must be passed properly to Gradle; watch the startup log to confirm the args took effect.

If there are multiple main classes, add this Groovy DSL block:

~~~groovy
tasks.named('bootRun') {
    mainClass = 'com.example.devrun.DevRunApplication'
}
~~~

Or set it in the Spring Boot DSL to share it with supporting tasks:

~~~groovy
springBoot {
    mainClass = 'com.example.devrun.DevRunApplication'
}
~~~

These are **two alternative ways**; you do not need to declare both at the same time. The class name is the FQCN including the package, not a filename ending in `.java`.

### 4.2. Configuring the App JVM, Gradle Properties, and Kotlin DSL

In `build.gradle`:

~~~groovy
tasks.named('bootRun') {
    jvmArgs '-Xmx512m'
    systemProperty 'demo.mode', (project.findProperty('demoMode') ?: 'local')
}
~~~

Then:

~~~bash
./gradlew bootRun -PdemoMode=experimental
~~~

`-PdemoMode=experimental` is primarily a **Gradle project property**. The `systemProperty` configuration is what forwards it into the `demo.mode` Java system property of the app JVM. Without this mapping, `-P...` does not automatically become a Spring property.

**Distinguishing from the Gradle JVM:** `-Dorg.gradle.jvmargs=...` typically controls the Gradle daemon; it does not automatically alter `bootRun.jvmArgs`. Similarly, Gradle `--debug` only increases build logging; to debug the **app JVM**, use `bootRun --debug-jvm` (Section 8).

For Kotlin DSL `build.gradle.kts`, the equivalent snippet is:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    mainClass.set("com.example.devrun.DevRunApplication")
    jvmArgs("-Xmx512m")
    systemProperty("demo.mode", "local")
}
~~~

This is a **Kotlin DSL snippet**, used when the project already declares the Boot/Java plugins in `build.gradle.kts`. Do not copy Groovy syntax like `mainClass = '...'` verbatim into a Kotlin file.

## 5. Passing Spring Profiles, Ports, and Environment Variables

Both tools run the **same Spring Boot code**. Therefore, once application arguments are passed into `main`, the Spring `Environment` rules are the same.

| Task | Maven | Gradle |
| --- | --- | --- |
| Run app | `./mvnw spring-boot:run` | `./gradlew bootRun` |
| Run on 18085 | `-Dspring-boot.run.arguments="--server.port=18085"` | `--args="--server.port=18085"` |
| Select dev | `-Dspring-boot.run.profiles=dev` | `--args="--spring.profiles.active=dev"` |
| Select dev,local | `-Dspring-boot.run.profiles=dev,local` | `--args="--spring.profiles.active=dev,local"` |
| JVM heap | `-Dspring-boot.run.jvmArguments="-Xmx512m"` | `bootRun { jvmArgs '-Xmx512m' }` |
| Main class | `-Dspring-boot.run.main-class=com.example.devrun.DevRunApplication` | `bootRun.mainClass` or `springBoot.mainClass` |
| View tool docs | `./mvnw spring-boot:help -Ddetail=true -Dgoal=run` | `./gradlew help --task bootRun` |

### 5.1. Using Environment Variables

Spring Boot typically maps `SERVER_PORT` to `server.port` and `SPRING_PROFILES_ACTIVE` to `spring.profiles.active`. Example on macOS/Linux:

~~~bash
export SERVER_PORT=18085
export SPRING_PROFILES_ACTIVE=dev
./mvnw spring-boot:run
# For another Gradle project: ./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
$env:SERVER_PORT = "18085"
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw.cmd spring-boot:run
# For Gradle: .\gradlew.bat bootRun
~~~

Environment variables are passed by the shell to the child process, so the same mechanism works for both Maven and Gradle. If you also pass `--server.port=18086` in application arguments, Spring Boot generally prioritizes command-line arguments over environment variables, so the app uses the higher-precedence value. When debugging configuration, check the **actual port logged** and send requests to that port.

Do not pass secrets on the CLI or commit them in `application.yml` when an appropriate environment variable or secret store can be used. Profiles such as `dev`, `test`, and `prod` are **Spring profiles**; Maven `-Pdev` and Gradle `-Penv=dev` are separate build mechanisms and do not automatically enable a Spring profile.

### 5.2. When the App Has No HTTP Server

A Spring Batch job or CLI app may finish running and **return control to the terminal** very quickly. That is not necessarily an error in `run`/`bootRun`. In that case, verification criteria are exit code, job execution status, and records/output matching the contract—not having a server listening on port 8080.

## 6. The Development Loop: Startup, Inspection, Change, Stop

A consistent workflow:

1. Open a terminal at the application module and run **one** Maven or Gradle command.
2. Observe the logs: main class, active profiles, HTTP port, startup success message, or stack trace.
3. Use another terminal to run `curl`; do not type requests into the terminal holding the foreground app.
4. When code changes are needed, compile or let the IDE update the classpath; observe whether DevTools detects it.
5. Stop the previous run with **Ctrl+C** in the terminal holding the invocation. Wait for the app JVM to stop and the port to be freed before rerunning on the same port.
6. Before handoff, run **tests + packaging + `java -jar` smoke test** separately; do not treat a development run as a release gate.

~~~bash
# Terminal 1 (Maven)
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.profiles.active=dev"
# Or Terminal 1 (Gradle)
# ./gradlew bootRun --args="--server.port=18085 --spring.profiles.active=dev"
~~~

~~~bash
# Terminal 2, after the application starts
curl -i http://localhost:18085/ping
curl -i http://localhost:18085/active-profiles
~~~

**Expected:** `/ping` returns status 200 and body `pong`; `/active-profiles` returns `dev` if only `dev` is enabled. Headers, `content-length`, and status line depend on the HTTP stack; do not hardcode a specific log/stdout snapshot as a pass condition. Run tests and capture real logs when evaluating.

### 6.1. Stopping Properly

- Both development run commands usually hold the invocation while the server is alive; **Ctrl+C** is the standard interactive way to stop them.
- `spring-boot:stop` belongs to the `spring-boot:start`/`stop` pair intended for the integration-test lifecycle with JMX; **do not use it as a "universal stop button"** for `spring-boot:run` or Gradle `bootRun`.
- If Ctrl+C does not terminate it, identify the exact PID/port and clean it up in a controlled manner; do not kill all `java` processes, as that could terminate your IDE, other builds, or colleagues' services.
- For apps with shutdown hooks or database connections, check the shutdown logs rather than concluding it stopped solely because the terminal prompt returned.

## 7. DevTools, Java Class Changes, and Resource Reloading

`spring-boot-devtools` improves development by detecting **changes in classpath output** and restarting or refreshing as configured. It **does not automatically compile** every `.java` file as soon as it is saved; the IDE or build must regenerate `.class` files so the watcher sees the change.

### 7.1. Maven DevTools

Add to `pom.xml` inside `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Use the parent's dependency management for the version. When the classpath changes, DevTools can restart the application. `optional` prevents DevTools from being pulled transitively when this artifact is used as a dependency; Spring Boot repackaging normally excludes DevTools from the executable package by default. Still verify the actual archive when needed.

If you want Maven `run` to use source resources directly:

~~~xml
<!-- Snippet added to the spring-boot-maven-plugin configuration -->
<configuration>
    <addResources>true</addResources>
</configuration>
~~~

**Trade-off:** source resources can be served immediately during development, but resource filtering may be bypassed, so behavior is not completely identical to the packaged artifact. Only enable this when the project genuinely needs it.

### 7.2. Gradle DevTools

Add to `dependencies` in `build.gradle`:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`developmentOnly` is recognized by the Boot Gradle plugin for development-only dependencies. When static resources need to be loaded from the source path, you can add:

~~~groovy
tasks.named('bootRun') {
    sourceResources sourceSets.main
}
~~~

Enabling `sourceResources` can change how `processResources` and filtering affect the runtime environment; verify again with `bootJar` when evaluating the artifact. `devtools` does not mean every Java change hot-swaps directly; when the IDE has not compiled the new class yet, a restart has no input to trigger on.

### 7.3. If DevTools Does Not Restart

Check in order: is the dependency present on the development classpath → did `.class`/resource output change → is the IDE configured to build/compile properly → are there restart exclusions or a trigger-file policy → what do the DevTools logs say? For static resources, browser cache or template cache can hide changes; do not rush to change the JVM or plugin version.

## 8. Debugging the Application JVM

Both Maven and Gradle have a **process running the build tool** and a **process running the Spring app**. Proper debugging must attach to the **application JVM**.

### 8.1. Maven JDWP

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
~~~

Meaning: `server=y` opens the debug listener, `suspend=y` makes the JVM wait for a debugger, and `address=127.0.0.1:5005` restricts listening to loopback. Create a Remote JVM debug configuration in your IDE with host `localhost` and port `5005`. Once the debugger attaches, `main` continues; not seeing the HTTP server before attaching is expected behavior. Do not expose the debug port to public networks.

### 8.2. Gradle `--debug-jvm`

Because `BootRun` extends `JavaExec`:

~~~bash
./gradlew bootRun --debug-jvm
~~~

Gradle starts the app JVM in debug mode, typically waiting to attach on port 5005 by default. **Do not confuse** this option with `-Dorg.gradle.debug=true`, which targets the Gradle daemon/build process.

When you need to change the port or suspend behavior, add this to `build.gradle`:

~~~groovy
tasks.named('bootRun') {
    debugOptions {
        enabled = true
        host = '127.0.0.1'
        port = 5006
        server = true
        suspend = true
    }
}
~~~

Enable debug rules only when needed; do not apply them by default across all CI workflows. An application suspended waiting for a debugger not accepting HTTP traffic yet is completely normal.

## 9. Why Does `run`/`bootRun` Differ from `java -jar`?

During a development run, the application uses **exploded classes/resources and a classpath constructed by the build tool**. During a packaged run, `java -jar` uses the **actual archive built and distributed**. Differences can exist in resource filtering, manifest/launcher, dependency scope, working directory, active profiles, or runtime JDK.

### 9.1. Maven: Build and Run the Artifact

~~~bash
# Run tests standalone
./mvnw test

# Run through package/verify (parent + Boot plugin bind repackage)
./mvnw clean verify

# JAR name is an example; use the actual file in target/
jar tf target/dev-run-demo-0.0.1-SNAPSHOT.jar
java -jar target/dev-run-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

An executable Spring Boot JAR typically contains `BOOT-INF/classes`, `BOOT-INF/lib`, and the proper launcher manifest. If `jar tf` does not show this structure or `java -jar` reports `no main manifest attribute`, check whether `spring-boot-maven-plugin`'s `repackage` goal ran and whether you chose the right JAR file.

### 9.2. Gradle: Build and Run the Artifact

~~~bash
./gradlew test
./gradlew clean build

# File path matches the example configuration; verify the real name in build/libs
jar tf build/libs/dev-run-demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/dev-run-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

`bootJar` generates the executable Spring Boot archive; the Java plugin's `jar` task may produce a plain JAR `*-plain.jar`. Choosing the executable JAR lets you test `java -jar`. Do not run a development instance simultaneously on the same port while testing the packaged JAR.

### 9.3. Two Groups of Verification Gates

| Group | Evidence | Do Not Infer |
| --- | --- | --- |
| Development run | Startup log, HTTP/job smoke on the app classpath. | That the artifact is packaged correctly. |
| Test & packaging | Surefire/Gradle Test report, build exit code, archive. | That the app will definitely run in the real runtime. |
| Packaged runtime | `java -jar`, right profile, status/body or job output. | That the system is production ready if security, observability, resilience, etc. are missing. |

**Both `BUILD SUCCESS` and a "Started" log are local evidence**—not sufficient to conclude every dependency or use case has been tested. When releasing, retain the commit, JDK, build command, reports, artifact name, and checksum/digest.

## 10. Running in a Multi-Module Repository

A Maven reactor or Gradle multi-project build may contain library modules and application modules. **Only modules with an entrypoint and the Spring Boot plugin should be run**.

### 10.1. Maven Multi-Module

~~~bash
# Assuming service is the application module listed in the reactor
./mvnw -pl service spring-boot:run
~~~

If `service` depends on library modules not yet built/installed in the local repository, prepare dependency modules through the reactor workflow before running. Avoid blindly invoking `-am spring-boot:run` assuming the goal only runs on `service`: selecting library modules too can make Maven try to run the Boot goal where there is no main class. When needed, configure skip/plugin executions accurately for library modules.

### 10.2. Gradle Multi-Project

~~~bash
# Assuming the app module is named service
./gradlew :service:bootRun
~~~

The Gradle task graph can build project dependencies as needed. If the root has no `bootRun` but `:service` does, invoke the exact task path. Do not apply the Spring Boot plugin to every library module just for the convenience of running a single root command.

### 10.3. Main Class and Classpath Options

When the Boot plugin cannot uniquely determine the main class, declare the FQCN explicitly: Maven `mainClass` or Gradle `bootRun.mainClass`. Gradle with Boot 3.3 also provides `bootTestRun` for a main class in the test source set (for special test scenarios). Maven `useTestClasspath` is another option, though **not default**. Including test dependencies in the development runtime can mask missing production dependencies, so enable it only when you understand why.

## 11. Common Errors and How to Verify

| Symptom | Common Cause | Resolution Step |
| --- | --- | --- |
| Maven reports `Unknown lifecycle phase "run"`. | Typed `mvn run` instead of the plugin goal. | Use `./mvnw spring-boot:run`. |
| `No plugin found for prefix 'spring-boot'`. | Missing plugin or unable to resolve plugin prefix. | Check `pom.xml`, repositories, Maven settings; use `spring-boot:help`. |
| Gradle `Task 'bootRun' not found`. | Boot plugin + Java plugin not applied to the invoked module. | `./gradlew tasks --all` or `:service:tasks --all`. |
| Gradle `Task 'run' not found`. | Confused with the Application plugin's `run` task. | Invoke `bootRun` explicitly. |
| App reports `Port 8080 was already in use`. | Old instance still running, or port occupied by another process. | Stop the right process, change `server.port`, call `curl` on the right port. |
| Maven `-Dserver.port=...` has no effect. | Maven property does not automatically reach the app JVM. | Use `spring-boot.run.arguments` or plugin JVM property config. |
| Gradle `-Pport=...` has no effect. | Project property does not automatically reach the app. | Use `--args` or map via `systemProperty`/`args` in `bootRun`. |
| `-Pdev` passed, but Spring does not use `dev`. | Confused Maven build profile with Spring profile. | Use `spring-boot.run.profiles=dev`. |
| `bootRun` has multiple main classes and fails. | Boot plugin cannot pick a single entrypoint. | Set the FQCN in `mainClass`. |
| `curl` connection refused. | App has not started, wrong port/path, already exited, or different host. | Read startup log, check port, active profile, and route. |
| DevTools does not restart on Java source edit. | Source has not been compiled to classpath output. | Configure IDE compile/build, inspect DevTools logs. |
| Development resources differ from artifact. | Enabling `addResources`/`sourceResources` bypasses resource filtering. | Check `processResources`, packaged archive, and `java -jar`. |
| Debug command does not serve HTTP. | JVM is in `suspend=y` waiting for debugger. | Attach IDE debugger on the right port, then test HTTP. |
| Works in IDE/`bootRun`, fails in JAR. | Different archive/launcher/runtime dependencies/Java target. | Run `bootJar`/`repackage`, `jar tf`, `java -jar`. |
| Increased Gradle JVM heap, app still OOMs. | Modified the Gradle daemon JVM instead of the app JVM. | Use `bootRun.jvmArgs`. |
| Root build picks wrong module/main. | Invoked goal/task on aggregator or library module. | Select `-pl service` or `:service:bootRun`, check entrypoint. |

### Useful Diagnostic Sequence

1. Identify the right **build tool** and plugin version.
2. Read the selected **main class/module**.
3. Check **port, profile, and config sources** (CLI, environment, POM/Gradle, application files).
4. Determine **which JVM receives** heap, system, and debug arguments.
5. Read the **root-cause exception** and check whether external dependencies/services are available.
6. Run an actual request or job smoke test.
7. Before handoff, run **test/package/binary smoke** separately.

Do not hide errors by disabling tests, removing security, or randomly deleting caches before knowing where the failure comes from.

## 12. Hands-on Exercises, Evidence, and Self-Assessment Questions

### Exercise A — Maven

1. Use the `pom.xml` from Section 3 with the two Java files from Section 2. Confirm `./mvnw -version` runs with a compatible JDK.
2. Run `./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.profiles.active=dev"`.
3. In another terminal, call `curl -i http://localhost:18085/ping` and `curl -i http://localhost:18085/active-profiles`.
4. Record the **actual** status/body: expect `200/pong` and `200/dev`. Press Ctrl+C to stop.
5. Run `./mvnw test`; inspect `target/surefire-reports` to verify JUnit tests were discovered.
6. Run `./mvnw clean package`, inspect the executable JAR, and test an actual `java -jar` invocation.

### Exercise B — Gradle

1. Use `settings.gradle`/`build.gradle` from Section 4 with the same Java source/test. Confirm `./gradlew --version` and that `./gradlew tasks --all` lists `bootRun`.
2. Run `./gradlew bootRun --args="--server.port=18085 --spring.profiles.active=dev"`.
3. Perform the two requests as in Exercise A and check whether the active profile and port are correct.
4. Press Ctrl+C, run `./gradlew test`; read `build/test-results/test` or `build/reports/tests/test`.
5. Run `./gradlew clean bootJar`, then inspect and run the executable JAR in `build/libs`.

### Exercise C — Comparing Incorrect vs. Correct Commands

Test with an available port:

- Maven: compare `-Dserver.port=18085` with `-Dspring-boot.run.arguments="--server.port=18085"`.
- Gradle: compare `-Pport=18085` (when no mapping is configured) with `--args="--server.port=18085"`.

Observe the **actual** port, not just the command line. If the project already defines a custom mapping, describe that mapping rather than concluding `-P...` never works.

### Completion Checklist

- [ ] Distinguish Maven goal `spring-boot:run` from Gradle `bootRun` task/`JavaExec`.
- [ ] Run the proper Wrapper and choose the application module containing the main class.
- [ ] Have a Java 17+ project with a verifiable endpoint.
- [ ] Pass port/profile using the right Maven/Gradle syntax.
- [ ] Explain build property ≠ JVM property ≠ app argument.
- [ ] Distinguish a Maven build profile from a Spring profile.
- [ ] Configure app JVM heap/debug without confusing it with the build daemon JVM.
- [ ] Observe logs, make requests, and stop the specific running instance.
- [ ] Understand that DevTools only restarts when classpath output changes.
- [ ] Do not conflate a development run with a packaged archive.
- [ ] Run tests, build an executable archive, and run a `java -jar` smoke test separately.
- [ ] Know how to diagnose port conflicts, missing plugins, wrong main classes, and resource differences.
- [ ] For Batch/CLI, use job results/exit code instead of an HTTP smoke test.

**Completion criteria:** submit a two-row Maven/Gradle table containing the run command, JDK/Wrapper, profile, HTTP port, responses from `/ping` and `/active-profiles`, stop method, test report, artifact path, and `java -jar` result. Explain why these two commands provide fast feedback during development while release verification must test the packaged artifact.

## Official References

- [Spring Boot 3.3 Maven Plugin — Running your Application](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html)
- [Spring Boot 3.3 Gradle Plugin — Running your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html)
- [Spring Boot — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Gradle — JavaExec API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

The commands and expected outcomes are presented for practice; this guide **does not claim to have run Maven/Gradle or observed logs on the learner's machine**. Use your project's actual configuration, versions, source code, and artifacts to verify.