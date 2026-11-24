# Running a Spring Boot Application with an IDE, Gradle Wrapper, or Maven Wrapper

After creating your first Spring Boot project, the next step is to **start the application**, inspect the logs, and try sending an HTTP request. There are three common ways: running directly from an IDE, using the **Gradle wrapper**, or using the **Maven wrapper**. All three can launch the same application, though environment preparation and commands differ slightly.

This lesson walks through each method, how to verify the application is running, how to change the port or profile, and how to handle common errors. The examples use a Spring Boot application with a simple HTTP endpoint.

## 1. Preparation before running

You need:

1. **A JDK compatible with the project's Spring Boot version.** For Spring Boot 3.x or 4.x projects, Java 17 is the minimum baseline; verify the exact version required by your project and configure `JAVA_HOME` or Project SDK accordingly.
2. **The project source code** fully generated or downloaded.
3. **A development tool** if running from an IDE: IntelliJ IDEA, Eclipse/Spring Tools, or Visual Studio Code with appropriate Java/Spring extensions.
4. **Network access on the first run** if the wrapper needs to download a Gradle/Maven version and dependencies not yet cached.

In your terminal, check Java:

```bash
java -version
javac -version
```

The `java` command shows the Java runtime used by the shell; `javac` shows the JDK compiler. If the terminal finds one Java version while the IDE uses another JDK, the application may behave differently between the two environments.

### 1.1. Identifying whether a project uses Gradle or Maven

Open the **project root directory** (containing the build configuration file) and check:

| Indicator in Root Directory | Project Uses | Appropriate Way to Run |
| --- | --- | --- |
| `build.gradle` or `build.gradle.kts` | Gradle | `gradlew` / `gradlew.bat` |
| `pom.xml` | Maven | `mvnw` / `mvnw.cmd` |
| `gradle/wrapper/gradle-wrapper.properties` | Gradle wrapper | Wrapper downloads and selects the configured Gradle version |
| `.mvn/wrapper/maven-wrapper.properties` | Maven wrapper | Wrapper downloads and selects the configured Maven version |

Example structure of a Gradle project:

```text
demo/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        ├── java/com/example/demo/DemoApplication.java
        └── resources/application.properties
```

A Maven project typically has `pom.xml`, `mvnw`, `mvnw.cmd`, `.mvn/wrapper/`, and the same `src/main/...` layout.

**Note:** normally a project chooses only **one** build tool. If `pom.xml` is present, follow the Maven instructions; if `build.gradle` or `build.gradle.kts` is present, follow Gradle. You do not need to install both Gradle and Maven globally just to run a project with a wrapper.

### 1.2. Example application

Suppose the project includes the **Spring Web** dependency (typically `spring-boot-starter-web`) and `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello Spring Boot";
    }
}
```

`@SpringBootApplication` marks the startup class and enables core Spring Boot configuration; `SpringApplication.run(...)` creates and starts the application context. `@RestController` combined with `@GetMapping("/hello")` declares an endpoint returning a string on `GET /hello`.

The example class places the controller inside the main class for easy observation. In larger projects, controllers are usually separated into their own files. Ensure the file path matches the `package` declaration and Spring Boot dependencies are declared in the build file.

Once the HTTP application starts successfully with default configuration, open:

```text
http://localhost:8080/hello
```

Expected output:

```text
Hello Spring Boot
```

If you generated a Spring Boot project without a web dependency, the application can still start, but it will **not** automatically open an HTTP server on port 8080. Not seeing an HTTP port in that scenario is not necessarily an error.

## 2. Method 1 — Running directly from an IDE

An IDE is convenient while writing code: it provides Run/Debug buttons, breakpoints, a console, code navigation tools, and variable inspection while the program executes.

### 2.1. General steps

1. Open the IDE and choose **Open/Import Project** from the **root directory** containing `pom.xml` or `build.gradle`.
2. Wait for the IDE to import the Maven/Gradle project, resolve dependencies, and index source code.
3. Select a **Project SDK/JDK** matching the requirements of Spring Boot and the build tool.
4. Open the class with `@SpringBootApplication` and `public static void main(String[] args)`, such as `DemoApplication`.
5. Choose **Run** on the `main` method or create a Java/Spring Boot Application run configuration.
6. Watch the **Run/Console** window; once the application is ready, test the `/hello` endpoint.
7. When you need to stop it, click **Stop** in the Run window.

Example from `DemoApplication`:

```java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class, args);
}
```

The IDE invokes `main` just like running a standard Java program. Spring Boot proceeds to initialize the context, configure beans, and start the web server if the application has a corresponding web stack.

### 2.2. Working with popular IDEs

| IDE | How to Start | Where to View Output |
| --- | --- | --- |
| **IntelliJ IDEA** | Open project, choose JDK, click the Run icon next to `main()` or use a Run Configuration | **Run** or **Debug** tool window |
| **Eclipse / Spring Tools** | Import Maven/Gradle project, open main class, choose **Run As → Java Application** or **Spring Boot App** with Spring Tools | **Console** |
| **Visual Studio Code** | Install appropriate Java/Spring support, open project folder, wait for import, click **Run Java** at `main()` | **Terminal**, **Debug Console**, or corresponding Java Run output |

If the IDE reports missing `org.springframework...` packages, first check that you opened the right project root folder and that dependency import/sync has finished. Opening a single `.java` file alone is usually not enough for the IDE to recognize the build configuration.

### 2.3. How do Run and Debug differ?

- **Run:** starts the application for interaction and viewing logs.
- **Debug:** also starts the application, while allowing you to set breakpoints, pause at specific lines, inspect variable values, and trace the call stack.

For example, place a breakpoint at:

```java
@GetMapping("/hello")
public String hello() {
    return "Hello Spring Boot";
}
```

Launch in Debug mode and visit `http://localhost:8080/hello`. When the request is processed, the IDE can pause at the breakpoint so you can inspect the execution flow. Note: each time you start a new process on the same port, the previous process occupying that port must be stopped first.

### 2.4. What to check in a Run Configuration

A run configuration typically includes:

- **Main class:** `com.example.demo.DemoApplication`.
- **JDK/runtime:** compatible Java version.
- **Working directory:** usually the project root directory.
- **Program arguments:** arguments passed into `main(String[] args)`, such as `--server.port=8081`.
- **Environment variables:** such as `SPRING_PROFILES_ACTIVE=dev`.
- **VM options:** JVM flags, such as `-Xmx512m`; **different** from program arguments.

Arguments like `--server.port=8081` are Spring Boot application properties, not VM options. VM options like `-Xmx512m` must be configured for the JVM. Putting an argument in the wrong field can prevent it from taking effect.

## 3. Method 2 — Running with the Gradle wrapper

The **Gradle wrapper** consists of scripts stored with the project to use the exact Gradle version configured. The wrapper helps teams and CI use the same build tool version without requiring every person to install Gradle manually.

Common files:

```text
gradlew                         # Unix/macOS/Linux script
gradlew.bat                     # Windows script
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

`gradle-wrapper.properties` contains the Gradle version and distribution URL, typically via the `distributionUrl` property. The wrapper may download that Gradle distribution on the first run; afterward it usually reuses the cached copy.

### 3.1. Running on macOS or Linux

Open a terminal in the root directory containing `gradlew`:

```bash
./gradlew bootRun
```

If a permission-denied error occurs:

```bash
chmod +x ./gradlew
./gradlew bootRun
```

### 3.2. Running on Windows

In **PowerShell**:

```powershell
.\gradlew.bat bootRun
```

In **Command Prompt (cmd.exe)**:

```bat
gradlew.bat bootRun
```

The `bootRun` command is provided by the Spring Boot Gradle plugin to run the application. Gradle resolves dependencies, compiles needed components, and launches the application with the right classpath. The process usually keeps running in the terminal until you stop it.

To stop an application running in the terminal, press **Ctrl+C**. This sends a stop signal to the process or process group controlled by the terminal; check the logs to confirm the application has terminated.

### 3.3. When is the `bootRun` task available?

The project must apply a compatible Spring Boot Gradle plugin. An illustrative snippet in Groovy DSL syntax:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'SPRING_BOOT_VERSION'
}
```

In a real project, replace the placeholder string `SPRING_BOOT_VERSION` with a valid plugin version and use the project's corresponding dependency management configuration. If the project was generated from Spring Initializr, this configuration is usually already present.

To view the project's tasks:

```bash
./gradlew tasks
```

If there is no `bootRun` task, check whether the project is a Spring Boot Gradle application and whether the Spring Boot plugin has been applied. For Maven projects, `bootRun` is not the right command.

### 3.4. Passing application arguments

In Unix shells, you can pass program arguments to the application via `bootRun`:

```bash
./gradlew bootRun --args='--server.port=8081'
```

In PowerShell:

```powershell
.\gradlew.bat bootRun --args="--server.port=8081"
```

`--server.port=8081` is the **Spring Boot application** argument; `--args` is an option of Gradle's Java execution task. After changing the port to 8081, the URL to test becomes `http://localhost:8081/hello`.

### 3.5. Creating a JAR file with Gradle

When you want to package the application to run standalone:

```bash
./gradlew bootJar
```

The JAR is typically created in the `build/libs/` directory. Example:

```bash
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

The actual JAR name depends on the project name, version, and build configuration; select the exact file generated by `bootJar`. Unlike `bootRun`, the `java -jar` command runs the packaged artifact; if you edit source code, you need to rebuild the JAR for those changes to appear.

## 4. Method 3 — Running with the Maven wrapper

The **Maven wrapper** serves the same purpose: using the Maven version specified by the project through bundled scripts, reducing reliance on a globally installed Maven version.

Common files:

```text
mvnw                         # Unix/macOS/Linux script
mvnw.cmd                     # Windows script
.mvn/wrapper/maven-wrapper.properties
```

Depending on wrapper version and type, `.mvn/wrapper/` may also contain a wrapper JAR file. If required wrapper files are missing, restore them from the project source rather than copying just the script from another project.

### 4.1. Running on macOS or Linux

Open a terminal in the root directory containing `pom.xml` and `mvnw`:

```bash
./mvnw spring-boot:run
```

If the script lacks execute permissions:

```bash
chmod +x ./mvnw
./mvnw spring-boot:run
```

### 4.2. Running on Windows

In **PowerShell**:

```powershell
.\mvnw.cmd spring-boot:run
```

In **Command Prompt (cmd.exe)**:

```bat
mvnw.cmd spring-boot:run
```

`spring-boot:run` is a goal of the **Spring Boot Maven plugin**. The plugin starts the Spring Boot application directly from the project with the required classpath. Like running via an IDE or Gradle, the terminal stays occupied while the application runs; use **Ctrl+C** to stop it.

### 4.3. Required Maven plugin

In `pom.xml` of a standard Spring Boot Maven application, there is configuration such as:

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

The plugin version is usually managed by the Spring Boot parent POM or the project's dependency/plugin management. The XML snippet above is part of `pom.xml`, not the full build file.

If Maven does not recognize the `spring-boot` prefix, check whether the plugin is properly declared or managed and whether you are running from the directory containing the right `pom.xml`.

### 4.4. Running with profiles or arguments

The Spring Boot Maven plugin can accept profile configuration via a plugin property:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

In PowerShell, if parsing arguments with dots or equals signs causes errors, pass the string intact:

```powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=dev"
```

The value `dev` here is a Spring profile name. Only activate a profile if the application has corresponding configuration or beans. A common approach across IDE, Gradle, and Maven is setting the `SPRING_PROFILES_ACTIVE` environment variable.

### 4.5. Packaging with Maven

To compile, run build lifecycle tests, and package:

```bash
./mvnw package
```

When the Spring Boot Maven plugin is configured to **repackage** an executable JAR (usually already set up in Spring Boot projects using an appropriate parent), the file may reside at `target/demo-0.0.1-SNAPSHOT.jar`. Run it:

```bash
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

The `target/` directory is Maven's typical output folder, analogous to Gradle's `build/`. If `java -jar` reports a missing main manifest attribute or missing libraries, check whether the project built an **executable Spring Boot JAR** or only a plain Java JAR.

## 5. Observing and confirming the application is running

Regardless of how you start it, what matters is inspecting **output from the application itself**, not just seeing a build command complete.

An application using Spring MVC with embedded Tomcat may log lines similar to:

```text
... Tomcat started on port 8080 (http) with context path '/'
... Started DemoApplication in ... seconds
```

Exact log text varies by Spring Boot version, logging configuration, and web server. With a WebFlux app using Netty or an app without a web dependency, you will not necessarily see a `Tomcat started` line.

Test a request from a browser or terminal:

```bash
curl http://localhost:8080/hello
```

Example response:

```text
Hello Spring Boot
```

You can also try `curl -i http://localhost:8080/hello` to inspect the HTTP status and headers, typically `200 OK` for a working endpoint.

If the application runs on a different port or uses `server.servlet.context-path`, adjust the URL accordingly. If you changed `@GetMapping("/hello")`, use the new path.

### 5.1. Meaning of common observations

| Observation | Possible Meaning | What to Check |
| --- | --- | --- |
| `Started DemoApplication ...` and request returns data | The application and example endpoint are ready | Continue development or try other requests |
| Logs report startup succeeded but `localhost:8080` fails to connect | May lack a web server, use another port, or have exited | Check web dependency, `server.port`, trailing logs, and process status |
| `404 Not Found` | Server responded, but no matching route was found | Check `@GetMapping`, package scanning, and context path |
| `500 Internal Server Error` | Request reached the server, but internal handling threw an error | Check the stack trace and request logs |
| `Port 8080 was already in use` | Another process is holding the port or an instance is already running | Stop the older process or change the port |

A successful build only proves that the build phase completed; it does not guarantee an HTTP endpoint works. Conversely, a terminal process still running does not by itself prove the application is ready to serve requests.

## 6. Configuring ports and profiles consistently

Spring Boot supports many configuration sources. In a first lesson, the two easiest settings to observe are **HTTP port** and **profile**.

### 6.1. Changing the port in `application.properties`

Create or edit `src/main/resources/application.properties`:

```properties
spring.application.name=demo
server.port=8081
```

Restart the application. Then use:

```text
http://localhost:8081/hello
```

Note that the configuration file must be included on the application classpath. After editing a configuration file, restart to ensure the new value takes effect. In applications without an HTTP server, `server.port` does not create an HTTP endpoint.

### 6.2. Using environment variables

To temporarily change the port without editing configuration files, set `SERVER_PORT`:

**Linux/macOS — example with Gradle:**

```bash
SERVER_PORT=8082 ./gradlew bootRun
```

**Windows PowerShell — example with Maven:**

```powershell
$env:SERVER_PORT = "8082"
.\mvnw.cmd spring-boot:run
```

The `SERVER_PORT` environment variable maps to the Spring Boot property `server.port`. Environment variable values override values in `application.properties` according to Spring Boot's standard configuration precedence.

Activating the `dev` profile works similarly:

**Linux/macOS:**

```bash
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun
```

**Windows PowerShell:**

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw.cmd spring-boot:run
```

When the `dev` profile is active, Spring Boot can additionally load `application-dev.properties` or `application-dev.yml` if present. Use profiles to separate environment-specific configuration such as integration endpoints or log levels; never hard-code secrets into shared repository files.

In PowerShell, `$env:...` variables are set for the **current shell session**; they can affect subsequent commands in that same session. When you want to return to default configuration, close that shell or remove the variable, e.g. `Remove-Item Env:SERVER_PORT`.

### 6.3. Program arguments and JVM options

These two argument types are not the same:

```text
--server.port=8083    → Spring Boot property (program argument)
-Xmx512m              → JVM option (heap limit)
```

In an IDE, enter `--server.port=8083` in the **Program arguments** field. When running an executable JAR:

```bash
java -Xmx512m -jar build/libs/demo-0.0.1-SNAPSHOT.jar --server.port=8083
```

This example uses the Gradle JAR path. For Maven, replace the path with the file in `target/`. Do not put `-Xmx512m` after the JAR name expecting the JVM to recognize it as a VM option.

## 7. Comparing the three ways to run

| Criterion | IDE | Gradle Wrapper | Maven Wrapper |
| --- | --- | --- | --- |
| How to start | Run/Debug on the main class | `./gradlew bootRun` | `./mvnw spring-boot:run` |
| Main prerequisites | IDE, JDK, and properly imported project | Gradle project with wrapper and Spring Boot plugin | Maven project with wrapper and Spring Boot Maven plugin |
| Viewing logs | IDE Run/Console view | Terminal | Terminal |
| Debugging with breakpoints | Convenient, built-in | Requires debugger configuration if attaching to the process | Requires debugger configuration if attaching to the process |
| Best suited for | Learning, coding, investigating bugs | Terminal workflows, team docs, Gradle CI | Terminal workflows, team docs, Maven CI |
| How to stop | IDE Stop button | `Ctrl+C` | `Ctrl+C` |

These methods are **not three different versions of Spring Boot**. They are three ways to launch your application code. Pick the one that matches your project's build tool and current task.

A sensible practice flow when starting out is:

1. Run via **IDE** to understand `main`, logs, and breakpoints.
2. Run via the project's **wrapper** to verify operations work from the terminal on other machines.
3. Try **changing the port** and calling the HTTP endpoint to confirm you are hitting the right process.
4. Build an **executable JAR** and run it with `java -jar` to understand the difference between development mode and running a packaged artifact.

## 8. Common errors and how to resolve them

### 8.1. `java` or `javac` is not recognized

Example on Windows:

```text
'java' is not recognized as an internal or external command
```

Or on Unix:

```text
java: command not found
```

The operating system cannot find Java in `PATH`, or a JDK is not installed. Install a compatible JDK, configure `JAVA_HOME` and `PATH` appropriately, open a new terminal, and re-check `java -version`.

### 8.2. `UnsupportedClassVersionError` or `invalid source release`

This usually indicates a **Java version mismatch** across compiler, bytecode, or running JVM. Check project requirements, `java -version` output, Gradle/Maven toolchain configuration, and the IDE JDK setting. Do not simply change Java in an external terminal and assume the IDE switches automatically.

### 8.3. Wrapper not found or script fails to run

Example error:

```text
./gradlew: No such file or directory
```

Check whether the terminal is in the directory containing `gradlew` and whether the project uses Gradle or Maven. On Windows, invoke the `.bat`/`.cmd` script; on Unix, scripts need appropriate execute permissions. If files inside `wrapper/` are missing, restore the complete wrapper set from the repository.

### 8.4. Failed to download dependencies or Gradle/Maven distribution

On first run, the wrapper may download the build tool; Gradle/Maven then downloads plugins and libraries. If this fails, inspect the exact error regarding network, proxy, certificates, repositories, wrapper URL, dependency versions, or corrupted cache. Do not treat every dependency download failure as a Java source code error.

### 8.5. Port 8080 is already in use

Typical message:

```text
Web server failed to start. Port 8080 was already in use.
```

A likely cause is that you started one instance in the IDE and then tried to start another using the wrapper. Stop the old process using Stop or `Ctrl+C`, or configure `server.port=8081` for the new process.

### 8.6. Startup failure during bean creation

Spring can report `ApplicationContext` or `BeanCreationException` errors if bean configuration, dependency injection, environment variables, or database connections are invalid. Read the **root cause** in the stack trace (`Caused by`), not only the `APPLICATION FAILED TO START` header.

For example, if you added JPA and database dependencies without configuring `spring.datasource.url`, the application may fail to start. That is an application configuration issue, not an IDE, Gradle, or Maven wrapper issue.

### 8.7. Application runs but the endpoint returns 404

Check:

- Is an appropriate web dependency present?
- Does the controller have `@RestController` and the method have `@GetMapping("/hello")`?
- Is the controller in a component-scanned package?
- Are you using the right port, context path, and URL path?
- Are you accidentally running an older JAR instead of your newly edited code?

If running from a JAR, editing source without repackaging will not update the contents of the existing JAR.

## 9. Hands-on exercises

### Exercise 1 — Run the application two ways

Choose a Spring Boot application with a `/hello` endpoint. Run it from the IDE, visit `http://localhost:8080/hello`, and observe the result. Stop the application, run it again using the **matching wrapper** for the project (Gradle or Maven), and visit the same URL.

Note the similarities and differences between launching from the IDE and from the terminal: where logs appear, how to stop it, and how breakpoints work.

### Exercise 2 — Change the port

Set `server.port=8081` in `application.properties`, restart the application, and test both URLs:

```text
http://localhost:8080/hello
http://localhost:8081/hello
```

Explain why only the URL with the configured port connects to that application (assuming no other process is running on the other port).

### Exercise 3 — Use the `dev` profile

Create `src/main/resources/application-dev.properties`:

```properties
server.port=8082
```

Run the application with `SPRING_PROFILES_ACTIVE=dev`. Confirm the endpoint moves to port 8082. Then remove the `dev` profile, restart, and observe the port returning to the default or the value in `application.properties`.

### Exercise 4 — Run the JAR

Package an executable JAR with `bootJar` (Gradle) or `package` with appropriate repackage configuration (Maven). Run it with `java -jar` and call the endpoint. Try editing `/hello`'s return text in source code **without rebuilding the JAR**; explain why the process started from the JAR still serves the old version.

## 10. Connecting knowledge

The `DemoApplication` class with `@SpringBootApplication` and `main()` is the shared starting point. **The IDE** invokes `main()` via a development run configuration; **Gradle wrapper** uses the `bootRun` task; **Maven wrapper** uses the `spring-boot:run` goal. Once Spring Boot actually starts, you confirm it through logs and an HTTP request to your endpoint.

When switching between launch methods, always verify **JDK**, **root directory**, **build tool**, **port**, and **profile**. Mastering these details will help you start up and troubleshoot upcoming Spring Boot lessons on your own.
