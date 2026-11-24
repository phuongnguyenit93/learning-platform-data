# Launching a Spring Boot Application from IDE, Gradle bootRun, and Executable JAR

## 1. What Same Task Are the Three Launch Methods Solving?

A Spring Boot application starts from the `main(String[] args)` method. The `SpringApplication.run(...)` call creates the Spring context, registers beans, applies configuration, initializes required components, and, if suitable Web libraries are present, starts an embedded HTTP server. The three launch methods — **IDE**, **Gradle `bootRun`**, and **`java -jar`** — all bring the application to that process, but differ in how code, libraries, configuration, and deployment artifacts are prepared.

- **IDE:** open the class with `main` and Run/Debug. Suitable for writing code, setting breakpoints, inspecting variables, and fixing bugs during development.
- **`bootRun`:** uses the Gradle task provided by the Spring Boot Gradle plugin. Gradle compiles and runs from the project's `runtimeClasspath`. Suitable for reproducing the project's run configuration from the command line, even without opening an IDE.
- **`java -jar`:** launches an **executable JAR** built with `bootJar`. Suitable for verifying the exact release artifact and running the application on a server/container.

Flow diagram:

```text
src/main/java + src/main/resources + dependencies
                |
        +-------+-------+
        |               |
   IDE / bootRun      Gradle bootJar
        |               |
  Runtime classpath    build/libs/*.jar
        |               |
        |           java -jar ...
        +-------+-------+
                |
        main() -> SpringApplication.run(...)
                |
       Spring context and (if Web) HTTP server
```

**Important distinction:** `bootRun` normally uses compiled classes and resources in the build directory along with dependency JARs; `java -jar` runs the contents of the JAR file at packaging time. Editing source code after creating a JAR does **not** automatically update the old JAR.

## 2. Prerequisites and Demo Application

You need a Spring Boot project applying the `org.springframework.boot` Gradle plugin, with the Java version required by the project and an identified main class. Spring Boot 3.x requires at least Java 17; the example below uses **Java 21**, Gradle 8.5 or later in a compatible line, and Spring Boot 3.3.x. Real projects must use the versions declared in their repository rather than upgrading/downgrading just to run an example.

Minimal structure for practice:

```text
launch-demo/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat              (Gradle Wrapper if already generated in the project)
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   └── PingController.java
    └── resources/
        └── application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'launch-demo'
```

`build.gradle` (standalone example using Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

`src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/com/example/demo/PingController.java`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

`src/main/resources/application.properties`:

```properties
spring.application.name=launch-demo
server.port=8080
```

`@SpringBootApplication` enables Spring Boot auto-configuration and component scanning in package `com.example.demo` and its subpackages. `PingController` is discovered, so when the Web application runs, a `GET /ping` request returns the string `pong`. This example is runnable once the Gradle Wrapper is present and dependencies can be downloaded. If the project does not have a Wrapper yet, generate a project via Spring Initializr/IDE or use an installed Gradle to generate the Wrapper; `./gradlew` commands do not exist when the Wrapper files are missing.

Verify tools before running:

```bash
java -version
./gradlew --version
```

On Windows PowerShell, replace the second command with `.\gradlew.bat --version`. The Java version of the **IDE Project SDK**, **Gradle Java toolchain**, and the `java` command in the terminal may differ; check each one when version errors arise.

## 3. Method 1: Run Directly from the IDE

In IntelliJ IDEA, Eclipse/STS, or an IDE with Spring Boot support:

1. Open the **correct Gradle project directory**, wait for dependency sync and JDK configuration.
2. Open `DemoApplication.java`, locate the `public static void main(String[] args)` method.
3. Choose **Run DemoApplication** (or create a Java/Spring Boot Run Configuration pointing to `com.example.demo.DemoApplication`).
4. Observe the Run window. With `spring-boot-starter-web`, the HTTP server will listen on port 8080 if the port is free and no other configuration overrides it.
5. Open `http://localhost:8080/ping` to verify; stop the application using the IDE's Stop button.

A Run Configuration typically has:

| Field | Purpose |
|---|---|
| Main class | Class with `main` used to launch, here `com.example.demo.DemoApplication` |
| JDK / Java runtime | JVM executing the program; must be compatible with bytecode |
| Working directory | Working directory for relative paths, such as external files |
| Program arguments | Arguments passed to `main`, such as `--server.port=9090` |
| VM options | JVM arguments, such as `-Xmx512m` or `-Dspring.profiles.active=dev` |
| Environment variables | Environment variables, such as `SPRING_PROFILES_ACTIVE=dev` |

**Do not confuse Program arguments and VM options.** `--server.port=9090` is an application argument; `-Xmx512m` is a JVM option. An IDE may run the classpath it compiled itself or delegate running to Gradle depending on configuration; therefore, when comparing against `bootRun`, check the IDE's actual execution mode.

To debug, set a breakpoint in `PingController.ping()`, choose **Debug** instead of Run, and send a `GET /ping` request. The IDE pauses at the breakpoint so you can inspect the stack and variables. Click Resume to complete the HTTP response.

## 4. Method 2: Run with Gradle bootRun

In the directory containing the Wrapper and `build.gradle` of the standalone project, run:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Gradle will download missing plugins/dependencies (the first run needs repository access), execute necessary compilation/resource tasks, and then launch the `main` class with the runtime classpath. The **`bootRun`** task exists when the Spring Boot Gradle plugin is applied to the relevant project; not every Gradle module has this task.

### Passing Application Arguments

Change the listening port from 8080 to 9090:

```bash
./gradlew bootRun --args='--server.port=9090'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--server.port=9090"
```

Multiple arguments are separated by spaces inside the same `--args` value:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --server.port=9090'
```

These are **application arguments**, not Gradle build flags. If you already ran `bootRun` in a terminal, you must **stop the previous session with Ctrl+C** before relaunching on the same port. Do not confuse an active Gradle daemon process with the Web process serving requests.

### Multi-Module Projects

In a multi-project Gradle repository, run from the root directory containing the Wrapper and use the **exact Gradle project path** (take the actual name from the project configuration):

```bash
./gradlew :app:bootRun
./gradlew :app:bootJar
```

`:app` is only an example. `:app:bootRun` runs a subproject; if you run `bootRun` at the root when the root does not apply the Spring Boot plugin, Gradle may report that the task was not found. Do not infer the Gradle project path solely from folder names.

### Debugging When Running with Gradle

`bootRun` inherits Gradle's Java execution capabilities. When you want to attach an IDE debugger, you can use:

```bash
./gradlew bootRun --debug-jvm
```

The application JVM normally waits for a debugger connection on port 5005; create a **Remote JVM Debug** configuration in your IDE to connect. This is a **debug port**, distinct from Spring Boot's HTTP port. If your Gradle/plugin version or project setup alters the debug mechanism, check the actual options of the `bootRun` task.

## 5. Method 3: Package and Run an Executable JAR

In the same project:

```bash
./gradlew clean bootJar
```

Windows PowerShell:

```powershell
.\gradlew.bat clean bootJar
```

`clean` deletes previous build outputs and is optional when you want a clean package; it is not mandatory every time. `bootJar` creates a **Spring Boot executable JAR** containing application classes, resources, runtime dependencies, and Spring Boot's loader. With the example above, the default name is typically:

```text
build/libs/launch-demo-0.0.1-SNAPSHOT.jar
```

Check the actual filename before running:

```bash
ls build/libs/
```

Windows PowerShell:

```powershell
Get-ChildItem .\build\libs\*.jar
```

Run the corresponding JAR:

```bash
java -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar
```

Windows PowerShell:

```powershell
java -jar .\build\libs\launch-demo-0.0.1-SNAPSHOT.jar
```

To change the port or profile:

```bash
java -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar --server.port=9090 --spring.profiles.active=dev
```

JVM options must come **before** `-jar`, whereas application arguments come **after** the JAR name:

```bash
java -Xmx512m -Dspring.profiles.active=dev -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

With Spring Boot 3.3.x, an executable JAR typically has a manifest distinguishing the loader and the application class: `Main-Class` points to Spring Boot's `JarLauncher`; `Start-Class` points to `DemoApplication`. Because of this, running `java -jar` does not require manually listing every dependency JAR on the classpath.

**Do not confuse `jar` and `bootJar`.** The Java plugin's `jar` task can produce a plain JAR (sometimes suffixed `-plain.jar`) that lacks dependencies/the loader to run this way. For a Spring Boot Web application needing an executable archive, use the output of `bootJar`. A library module may be configured to disable `bootJar` or have no Web server; in that case do not force Web startup commands onto that module.

Unlike `bootRun`, an already packaged JAR does not automatically update when you edit `src/main/java` or `src/main/resources`. To release a fix, re-run `bootJar`, verify the right file, and restart the new JAR process.

## 6. Verify That the Application Is Running Properly

After each launch method, look for completion signs in the logs, such as the Tomcat initialization message and `Started DemoApplication`. Log lines may vary by version, logging configuration, and Web library; the **`Started ...` line does not mean every business feature is healthy**.

In a second terminal on macOS/Linux:

```bash
curl -s http://localhost:8080/ping
```

HTTP response body of the demo program:

```text
pong
```

In PowerShell:

```powershell
Invoke-RestMethod http://localhost:8080/ping
```

The corresponding result is `pong`. When `--server.port=9090` is used, change the URL to `http://localhost:9090/ping`. If the HTTP response is 404, recheck the path, port, and controller; 404 differs from a connection failure caused by the process not running.

To stop an application running directly in a terminal, press **Ctrl+C** and wait for the process to exit. In an IDE, use Stop. Before running via another method, ensure the old process is no longer occupying the port.

## 7. Is Configuration Identical Across All Three Launch Methods?

Spring Boot uses the same configuration-reading mechanism, but the **supplied configuration sources** may differ. `application.properties`/`application.yml` are packaged on the classpath; external config files, profiles, command-line arguments, environment variables, and JVM options can change the startup result.

For example, enabling the `dev` profile:

- **IDE:** set Program arguments to `--spring.profiles.active=dev`, or configure the environment variable `SPRING_PROFILES_ACTIVE=dev`.
- **Gradle:** `./gradlew bootRun --args='--spring.profiles.active=dev'`.
- **JAR:** `java -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev`.

When `application-dev.properties` exists in `src/main/resources`, Spring Boot can load configuration for the active profile. Do not create a `dev` profile just to run the application if the real project does not need it; when a profile requires a database, secrets, or external services, those dependencies must be provided.

Similarly, the working directory and external files are not necessarily identical. For instance, a relative path string like `./config/settings.json` is resolved relative to the **process** working directory; running from the IDE and running a JAR from another directory can point to two different files. For real deployments, explicitly declare profiles, environment variables, config locations, and the working directory rather than relying on a developer's local machine setup.

## 8. Comparison Table

| Criterion | IDE Run/Debug | Gradle `bootRun` | Executable JAR + `java -jar` |
|---|---|---|---|
| Execution source | IDE classpath or delegated through Gradle per configuration | Build classes/resources + runtime dependencies | Contents of packaged JAR |
| Must build JAR first? | No | No | Yes, via `bootJar` |
| Best suited for | Development, breakpoints | Command-line execution, dev/integration | Verifying release artifact, deployment |
| After editing code | Recompile/rerun via IDE | Rerun task; Gradle compiles | Rebuild JAR and run new JAR |
| Runtime configuration | Run Configuration | `--args`, env, Gradle configuration | JVM options, env, application args |
| Common prerequisites | Correct IDE SDK and dependencies | Correct Wrapper, Gradle plugin, dependencies | Compatible JVM and valid executable JAR |

No single method is automatically "more correct" in every situation. What matters when comparing bugs is using **the same built code, same Java, same profile, same arguments, and same dependent services**.

## 9. Common Errors and How to Trace Their Cause

| Symptom | Check and Resolution |
|---|---|
| `Task 'bootRun' not found` | Does the target project apply the Spring Boot Gradle plugin? In a multi-project build, call `:module:bootRun`; check the project's task list. |
| `Could not find or load main class` | Check package, class name, compilation output, and IDE Main class. For JARs, verify `bootJar` was used and the main class is configured. |
| `no main manifest attribute` with `java -jar` | You may be running a plain JAR or wrong file. Use the executable JAR created by `bootJar`. |
| `UnsupportedClassVersionError` | The Java used to **run** is older than the compiled bytecode version. Compare `java -version` in terminal, IDE JDK, and Gradle toolchain. |
| `Port 8080 was already in use` | Another process occupies the port. Stop the old process or run with `--server.port=9090`. |
| `Connection refused` on `/ping` | Application is not running, exited, or is listening on a different port/host; check logs and URL. |
| HTTP 404 at `/ping` | Server may be running without this mapping. Check controller, path, context path, and port. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Check runtime dependencies, JAR contents, and build configuration; do not use a `-plain` JAR instead of the executable JAR. |
| Bean initialization, database, or missing config error | Find the **first meaningful `Caused by:`** in the stack trace; check profile, env, service endpoints/credentials, and related beans. |
| Process starts and exits immediately | Check error logs; if it is an application **without a Web server and without tasks keeping the process alive**, exiting after startup completes may be normal. |

A consistent diagnostic workflow is: **(1)** identify the exact command and module being run, **(2)** identify Java/runtime arguments, **(3)** read the root error in the logs, **(4)** check ports and profiles, **(5)** rerun after fixing the actual cause. Do not change multiple factors at once before knowing where the error comes from.

## 10. Suggested Practice Workflow

1. Run the application from the IDE on port 8080; verify with `/ping` and Debug inside `ping()`.
2. Stop the IDE, switch to `./gradlew bootRun` (or `.\gradlew.bat bootRun` on Windows); verify the `pong` response. Try rerunning on port 9090 with `--args` and use the new URL.
3. Stop `bootRun`, execute `bootJar`; observe the executable JAR name in `build/libs`. Launch with `java -jar` and test `/ping`.
4. Change the controller return value from `pong` to `pong-v2`. Observe that the **old JAR still returns `pong`**, then rebuild the JAR and verify the new one returns `pong-v2`. This is direct proof of the difference between running compiled source and running a finalized package.
5. Deliberately occupy port 8080 with a running session and start another session on the same port; read the error, stop the extra session or switch ports. Never let two processes pretend to be a single application.

**Key takeaway:** IDE supports development/debugging, `bootRun` runs via the build system, and `bootJar` + `java -jar` verifies the exact release artifact. All three still depend on the same application's startup class, JVM, classpath/dependencies, and Spring Boot configuration.