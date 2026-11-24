# Configuring Remote Debugging for a Spring Boot Application Process

## 1. What Is Remote Debugging and Which JVM Is Being Debugged?

**Remote debugging** means connecting a debugger (IntelliJ IDEA, VS Code, Eclipse, or any JDWP-compatible tool) to a **Java process that was started with the debug agent**. The debugger can set breakpoints, inspect call stacks and variables, step through code, and trace execution flow. "Remote" simply means the debugger and the application JVM are two separate processes communicating over a protocol; they can reside on the **same machine**, inside a **Docker container**, on another **VM**, or inside a **Kubernetes pod**.

The standard mechanism on Java 17+ is the **Java Debug Wire Protocol (JDWP)**. The application JVM loads the debug agent via `-agentlib:jdwp=...`. The IDE connects to the agent's port. Spring Boot does not need a separate "network debug mode" to support JDWP; this is a built-in JVM feature.

```text
Developer machine / IDE                           Spring Boot application JVM
+--------------------------------+              +-------------------------------+
| IntelliJ / VS Code             |  JDWP TCP    | Java 17+ + JDWP agent        |
| - Matching-version source      |------------->| - port 5005                 |
| - Breakpoints                  |              | - classes + dependencies    |
| - Attach: localhost:5005       |              | - HTTP server: port 8080    |
+--------------------------------+              +-------------------------------+
                                      ^                       ^
                                      |                       |
                                Debug port               HTTP API port
                                (e.g., 5005)             (e.g., 8080)
```

**Two independent ports:** Spring Boot's `server.port=8080` serves HTTP; `address=127.0.0.1:5005` in JDWP serves the debugger. Changing `server.port` does not change the JDWP port. Conversely, opening port 5005 does not mean the HTTP endpoint is up yet, especially when `suspend=y` is enabled.

### When Remote Debugging Is Useful

- Running the application via `java -jar`, Gradle `bootRun`, or Maven `spring-boot:run`, then attaching an IDE to investigate bugs that only appear at runtime.
- Running a service inside Docker or a separate development environment while setting breakpoints in a local IDE.
- Diagnosing issues during startup: use `suspend=y` to attach **before** `main` or the Spring context initializes.
- Diagnosing issues on a specific request: use `suspend=n` so the app starts normally, then attach before sending the request.
- Comparing runtime configuration, execution flow across controllers/services, exception stacks, and bean state.

**Do not confuse with** Spring Boot's `--debug`: that flag enables additional diagnostic/condition evaluation logging and **does not open a JDWP port**. Meanwhile, `-Dorg.gradle.debug=true` debugs the **Gradle daemon/build logic**, not the Spring Boot application JVM. Be sure to target the right process.

## 2. Java 17+ JDWP Syntax

Standard command to run a built JAR in a development environment:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

Here `app.jar` stands for the executable JAR filename; the runnable example in Section 4 uses a concrete filename. On Java 17+, use `address=127.0.0.1:5005` so the agent **listens only on loopback**. An equivalent localhost shorthand on modern JDKs is typically `address=5005`, though specifying the host explicitly is easier to verify.

| Component | Meaning and Behavior |
| --- | --- |
| `-agentlib:jdwp` | Loads the debug agent into the **application JVM**. This is a JVM option and must precede `-jar` or the main class name. |
| `transport=dt_socket` | Connects the debugger over a TCP socket. |
| `server=y` | The application JVM **listens**, and the IDE actively **attaches** to the JVM. |
| `server=n` | The JVM initiates a connection out to a listening debugger (reverse attach; use only when intentionally designed). |
| `suspend=n` | The JVM starts running immediately; the debugger can attach after startup. |
| `suspend=y` | The JVM waits for the debugger to attach and resume before executing application code; useful for catching startup issues. |
| `address=127.0.0.1:5005` | Binds JDWP to port 5005 on loopback, suitable for local dev and SSH tunnels. |
| `address=*:5005` | Listens on **all interfaces**; may be needed inside containers, but dangerous if the port is publicly reachable. |
| `address=5005` | On Java 9+ usually loopback-only; behavior on older JDKs differs. |

**Security rule:** JDWP provides no authentication or encryption layer like standard HTTPS services. Anyone who can reach the debugger can inspect and deeply manipulate the process. Enable it only in development environments or authorized investigation sessions; prefer **loopback + SSH tunnel / `kubectl port-forward`** and restrict network access. Never expose `*:5005` directly to the Internet, and never enable the debug agent by default on production pods.

### Choosing `suspend=y` vs. `suspend=n`

**`suspend=y`:** The JVM usually prints a message like `Listening for transport dt_socket at address: 5005` and **does not run `SpringApplication`** until the IDE attaches and resumes execution. Thus `curl localhost:8080` will fail until resumed. Use this to hit breakpoints in `main`, bean initialization, or code running immediately at startup.

**`suspend=n`:** The application starts normally. Set breakpoints in handlers/controllers, attach the IDE, and then send the request. If a request arrives **before** attaching or setting the breakpoint, the debugger cannot rewind time to pause an already-handled request.

**Note:** When a breakpoint pauses all threads or a request-handling thread, the client may time out. That is the intended effect of the debugger, not necessarily an application deadlock.

## 3. Preparing the Environment and a Runnable Java 17 Application

This section uses **Spring Boot 3.5.0 and Java 17+** for consistent commands and configuration. This is a fixed example version, **not an implication of the latest Spring Boot release**. You need JDK 17 or higher, a Maven or Gradle version compatible with the plugin, and repository access to download dependencies. The Java code is identical for Maven and Gradle; pick just one build tool during practice.

Structure:

```text
jdwp-demo/
├── pom.xml                        # use if Maven is chosen
├── settings.gradle.kts             # use if Gradle is chosen
├── build.gradle.kts                # use if Gradle is chosen
└── src/main/java/com/example/debug/JdwpDemoApplication.java
```

**`src/main/java/com/example/debug/JdwpDemoApplication.java`:**

```java
package com.example.debug;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class JdwpDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdwpDemoApplication.class, args);
    }

    @GetMapping("/calc")
    public String calculate(
            @RequestParam("a") int a,
            @RequestParam("b") int b) {
        int result = a + b; // Set a breakpoint on this line.
        return "sum=" + result;
    }
}
```

The example exposes an HTTP endpoint `GET /calc?a=2&b=3`. When running normally, the response body is **`sum=5`** (without necessarily ending in a newline). The breakpoint goes on `int result = a + b;`; the IDE will pause there when a request is handled.

### 3.1. Complete Maven POM

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jdwp-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Running `mvn clean package` produces the executable archive `target/jdwp-demo-0.0.1-SNAPSHOT.jar` via the Spring Boot Maven plugin. If the repository includes a Maven Wrapper, replace `mvn` with `./mvnw` (Windows: `mvnw.cmd`). The sample POM and Java code above are sufficient to start the HTTP endpoint.

### 3.2. Complete Gradle Kotlin DSL (Alternative to Maven)

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "jdwp-demo"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

With a Gradle Wrapper compatible with Spring Boot 3.5:

```bash
./gradlew clean bootJar
```

The executable JAR is typically `build/libs/jdwp-demo-0.0.1-SNAPSHOT.jar`. If there is no Wrapper yet, use a compatible installed Gradle to run `gradle wrapper` and then use the wrapper, or replace `./gradlew` with `gradle`. On Windows use `gradlew.bat`. Do not copy `pom.xml` into an active Gradle project assuming both build tools automatically share configuration: each tool has its own plugin/task model.

## 4. Simplest Approach: Debugging a JAR with `java -jar`

This is the most direct way to test JDWP without relying on a Maven/Gradle runtime once the archive is built.

With the Maven project from Section 3:

```bash
mvn clean package
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar target/jdwp-demo-0.0.1-SNAPSHOT.jar
```

With the Gradle project, run `./gradlew bootJar` and adjust the JAR path:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar build/libs/jdwp-demo-0.0.1-SNAPSHOT.jar
```

**Sequence when `suspend=y`:**

1. The terminal starts the JVM and JDWP agent, waiting for a debugger to connect to `127.0.0.1:5005`.
2. Open the IDE and create an **Attach / Remote JVM Debug** configuration with host `localhost` and port `5005`.
3. Attach; if the IDE prompts to resume or pauses at startup, continue execution.
4. Spring Boot starts the web server (port `8080` by default unless overridden).
5. Set a breakpoint in `calculate` and send an HTTP request from another terminal.

```bash
curl -fsS 'http://localhost:8080/calc?a=2&b=3'
```

When the breakpoint pauses on `int result = a + b;`, the input variables are `a=2` and `b=3`; after stepping past the addition, `result=5`. Resume execution so the HTTP client receives **`sum=5`**. With `suspend=n`, steps 2–4 can be reversed, though you must still attach before the request whose breakpoint you want to catch.

**Watch JVM option order:** the valid form is `java -agentlib:jdwp=... -jar app.jar`. Placing `-agentlib:jdwp` after `-jar app.jar` turns it into an application argument instead of enabling JDWP. Likewise, `--debug` after the JAR name is a Spring Boot argument, not a JVM debug-agent option.

### Changing the Port and Bind Address

When port 5005 is already occupied by another process, switch to `5006`:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5006 -jar target/jdwp-demo-0.0.1-SNAPSHOT.jar
```

The IDE must attach to port **5006**, while the HTTP API remains on **8080**. The JDWP port does not need to match the HTTP port, and neither should conflict with other processes.

## 5. Gradle: Debugging `bootRun` Properly

The Spring Boot Gradle plugin creates the `bootRun` task, which is a `JavaExec` task. It starts the **Spring Boot application in a child JVM**, so you can use the task's `--debug-jvm` option or configure `debugOptions`.

### 5.1. Instant Debugging with `--debug-jvm`

With the Gradle Kotlin DSL from Section 3:

```bash
./gradlew bootRun --debug-jvm
```

Gradle starts the application process with the debug agent on default **port 5005**, **suspended waiting for a debugger**. Attach the IDE to `localhost:5005`; the app then continues starting, and you can call `/calc` as in Section 4.

Here `--debug-jvm` targets the **JVM running the `bootRun` task**, not the Gradle daemon. To skip waiting at startup, see `debugOptions` below. By contrast, `./gradlew test --debug-jvm` enables debugging for the **forked test JVM**, not the Spring Boot application; choose the task matching your goal.

**Avoid confusion:**

```bash
./gradlew help -Dorg.gradle.debug=true
```

This command debugs the **Gradle build process** (such as build scripts or plugins), usually waiting for a debugger on port 5005; it is not equivalent to `bootRun --debug-jvm`. Do not enable both modes simultaneously on port 5005 without explicitly configuring separate ports.

### 5.2. Configuring `debugOptions` with Kotlin DSL

If you want a custom port and want the app to start immediately without waiting for the IDE, **add** this snippet to `build.gradle.kts` from Section 3:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    debugOptions {
        enabled.set(true)
        host.set("127.0.0.1")
        port.set(5006)
        server.set(true)
        suspend.set(false)
    }
}
```

Then:

```bash
./gradlew bootRun
```

The application runs with JDWP on `127.0.0.1:5006` without waiting for a debugger (`suspend=false`). Configure the IDE to attach to `localhost:5006`. Properties `enabled`, `host`, `port`, `server`, and `suspend` belong to Gradle's `JavaDebugOptions`; they configure the **agent inside the application JVM**.

**Caution:** if left enabled directly in the build script, this configures debugging for every `bootRun` execution. In shared projects, gate it behind a Gradle project property or keep it only in local/development configuration so a debug agent is not opened unintentionally in CI.

Example enabling it only when `-PlocalDebug` is passed:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

val localDebug = providers.gradleProperty("localDebug")

tasks.named<BootRun>("bootRun") {
    debugOptions {
        enabled.set(localDebug.isPresent)
        host.set("127.0.0.1")
        port.set(5006)
        server.set(true)
        suspend.set(false)
    }
}
```

This is an **alternative replacement** for the `tasks.named<BootRun>` block above; do not paste both and overwrite the same options. Running `./gradlew bootRun -PlocalDebug` enables the agent. Running `./gradlew bootRun` without the property keeps it disabled. In larger environments, using explicit providers helps keep configuration cache tracking clean.

### 5.3. Equivalent Groovy DSL

If the project uses `build.gradle` instead of Kotlin DSL, declare:

```groovy
tasks.named('bootRun') {
    debugOptions {
        enabled = true
        host = '127.0.0.1'
        port = 5006
        server = true
        suspend = false
    }
}
```

This Groovy snippet assumes the Spring Boot plugin has registered the `bootRun` task. The settings match the Kotlin DSL: port 5006, immediate startup, loopback-only. Use only **one** DSL style per project.

### 5.4. Differences Among `-Dorg.gradle.debug`, `-P`, `--debug`, and `--debug-jvm`

| Command/Option | Target |
| --- | --- |
| `./gradlew bootRun --debug-jvm` | Enables JDWP for the **application JVM** launched by `bootRun`. |
| `./gradlew help -Dorg.gradle.debug=true` | Enables JDWP for the **Gradle daemon/build logic**. |
| `./gradlew bootRun --debug` | Enables DEBUG logging for the **Gradle CLI**; does not open JDWP for the app. |
| `./gradlew bootRun --args='--debug'` | Passes `--debug` to the **Spring Boot application**; this configures Boot's log/condition output, not JDWP. |
| `./gradlew bootRun -Pfoo=bar` | Sets a Gradle project property; does not automatically configure JDWP or Spring runtime properties. |

When the IDE appears "connected" yet breakpoints in a Java controller never hit, first verify the IDE attached to the **right application JVM**, not the Gradle daemon.

## 6. Maven: Passing JDWP to the `spring-boot:run` JVM

The Maven Spring Boot plugin runs `spring-boot:run` in a **forked application process**. Therefore, `-D...` flags do not automatically forward every system property from the Maven JVM to the application. The plugin provides the `spring-boot.run.jvmArguments` parameter specifically to pass **JVM options** to the Spring Boot process.

Using the POM from Section 3, run:

```bash
mvn spring-boot:run "-Dspring-boot.run.jvmArguments=-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
```

Maven starts the application JVM with JDWP on port 5005 waiting for the debugger; the IDE attaches and the app starts. This is a flag **for the Spring Boot Maven plugin** passed via a Maven property, distinct from Gradle's `-Dorg.gradle.debug=true`.

To avoid waiting for the debugger at startup, change `suspend=n`:

```bash
mvn spring-boot:run "-Dspring-boot.run.jvmArguments=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005"
```

Quoting wraps the entire `-Dspring-boot.run.jvmArguments=...` in double quotes so the shell preserves the argument intact. If the project includes a Maven Wrapper, use `./mvnw` or `mvnw.cmd` accordingly.

### Configuring the Maven Plugin in the POM

When you genuinely need a development profile with dedicated debug settings, you can add the following **inside** the `spring-boot-maven-plugin` `<plugin>` block:

```xml
<configuration>
    <jvmArguments>
        -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005
    </jvmArguments>
</configuration>
```

This is a **plugin configuration snippet**, not a standalone `pom.xml` file. It enables debugging for every `spring-boot:run` invocation using that configuration, so restrict it to a development Maven profile if sharing the project. Port and suspend settings can still be adjusted via CLI as above.

**Do not confuse:** `mvn -X` increases **Maven build** debug logging without enabling JDWP. `-Dspring-boot.run.arguments=--debug` sends Spring Boot's log flag to the app, which also does not enable JDWP. If both the POM `jvmArguments` and the CLI specify values, check the output/logs to verify what the plugin actually passes and avoid duplicate debug agent declarations.

## 7. IDE: Attaching to the Right Source Code, Host, and Port

### 7.1. IntelliJ IDEA

1. Open the exact project containing `JdwpDemoApplication.java`, ensuring the source matches the bytecode running in the JVM.
2. Set a breakpoint on `int result = a + b;`.
3. Open **Run → Edit Configurations → Add New → Remote JVM Debug** (menu names may vary by IDE version).
4. Choose debugger mode **Attach to remote JVM**, set **Host = localhost**, **Port = 5005** (or `5006` if changed).
5. Start the application JVM with JDWP, then launch the remote debug configuration to attach.
6. If `suspend=y`, resume execution so the app starts; send `curl /calc` and watch the breakpoint hit.

The IDE needs matching sources and classpath. If multiple modules or classes share a name, select the right module or configure source lookup. A breakpoint that appears **gray, unverified, or never pauses** usually means the class is not loaded yet, sources mismatch the running version, execution never took that branch, or you attached to the wrong process.

Remote JDWP attach for Java usually does not require extra Spring Boot debugger plugin features. Certain deeper Spring runtime inspections may depend on the IDE edition/version, but basic JDWP attach steps remain identical.

### 7.2. Visual Studio Code

Requires **Debugger for Java** (included in Extension Pack for Java). In the project, create **`.vscode/launch.json`**:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "java",
      "name": "Attach Spring Boot JVM (5005)",
      "request": "attach",
      "hostName": "localhost",
      "port": 5005
    }
  ]
}
```

Open Run and Debug, choose `Attach Spring Boot JVM (5005)`, and start debugging. This file only configures the debugger on the developer machine and **does not start the application JVM**. The application must already be started with JDWP on the matching port. Change `port` to `5006` if your build/run uses `5006`. Ensure the Java project is imported with matching sources.

When debugging over VPN, SSH, or a `kubectl` tunnel, attach to `localhost:<local-port>` after establishing the tunnel rather than exposing JDWP on a public IP address.

### 7.3. Common Operations

- **Breakpoint:** pauses on a line when a thread reaches it; set before sending the request.
- **Step Over:** executes the current line and pauses at the next line.
- **Step Into:** enters the called method if matching bytecode/source is available.
- **Evaluate Expression:** evaluates an expression in the current stack frame; avoid calling functions with side effects on sensitive data.
- **Exception Breakpoint:** pauses when an exception is thrown or uncaught, helping identify the root cause before it becomes HTTP 500.
- **Resume:** continues execution until the next breakpoint; the HTTP client receives the response only after the handling thread is resumed.

When inspecting sensitive values in the debugger, respect data access permissions and policies of the environment being debugged; a debugger can read secrets and payloads residing in process memory.

## 8. Docker: Debugging Inside a Container and Attaching from the Host

When the JVM runs inside Docker, `127.0.0.1` **inside the container** is not the host machine's loopback interface. For standard port publishing to work, the JVM must listen on an interface Docker routes to, such as `address=*:5005` **inside the container**. Then publish the debugger port **only to the host's loopback**.

Example using the Maven JAR from Section 3. **`Dockerfile`:**

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/jdwp-demo-0.0.1-SNAPSHOT.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Run from the directory containing the POM, sources, and Dockerfile:

```bash
mvn clean package
docker build -t jdwp-demo:dev .
docker run --rm \
  -e 'JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005' \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:5005:5005 \
  jdwp-demo:dev
```

The lines above use `\` for Bash line continuation; in PowerShell, write `docker run` on a single line or use PowerShell's own continuation syntax. You can run it on one line:

```bash
docker run --rm -e 'JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005' -p 127.0.0.1:8080:8080 -p 127.0.0.1:5005:5005 jdwp-demo:dev
```

**How it works:**

- `JAVA_TOOL_OPTIONS` is supplied **exclusively to the app container**, so `java -jar` picks up the JDWP agent without hardcoding debug mode in the Dockerfile.
- `address=*:5005` tells the agent to listen on **container** interfaces; this is commonly required so Docker can forward host traffic into the container.
- `-p 127.0.0.1:5005:5005` restricts the **host-published address** to loopback. This differs from `-p 5005:5005`, which may publish across all host interfaces depending on Docker settings.
- `-p 127.0.0.1:8080:8080` publishes the HTTP API separately on loopback.
- The IDE on the host attaches to `localhost:5005`; then call `http://localhost:8080/calc?a=2&b=3`.

**Two address layers:** `address=*:5005` is only the socket address **inside the container**, not an endorsement to expose this port publicly. Check network/host binding policies, Docker version, and environment (Docker Desktop, bridge network, remote Docker host). Never create a public ingress or service for 5005.

**Caution with `JAVA_TOOL_OPTIONS`:** if set globally on a machine running Maven or Gradle, it can accidentally enable JDWP on **multiple JVMs** (build tool, daemon, workers, application), causing port 5005 collisions. The example above scopes it strictly to the target container runtime. Launchers may log `Picked up JAVA_TOOL_OPTIONS`; that is a normal JVM notice, not a build error.

### Equivalent Docker Compose for Dev Environment

```yaml
services:
  app:
    image: jdwp-demo:dev
    environment:
      JAVA_TOOL_OPTIONS: >-
        -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
    ports:
      - "127.0.0.1:8080:8080"
      - "127.0.0.1:5005:5005"
```

This file assumes `jdwp-demo:dev` has been built as above. This is a **dev-only** configuration and should not be merged into production compose defaults. Once debugging finishes, remove the agent configuration and port 5005 mapping.

## 9. VMs, SSH Tunnels, and Kubernetes: Controlled Connectivity

### 9.1. VM/Remote Host: Using SSH Local Forwarding

When an application runs on a development VM accessible via SSH, a safer pattern is:

1. The JVM on the VM listens for JDWP on **`127.0.0.1:5005`**, never publicly exposed.
2. The developer workstation opens a secure **SSH local port forward** from `localhost:5005` to `127.0.0.1:5005` on the VM.
3. The IDE attaches to `localhost:5005` through the tunnel; port 5005 does not need to be opened on any public firewall.

Example SSH command:

```bash
ssh -N -L 5005:127.0.0.1:5005 devuser@devhost.example
```

`devhost.example` is an **illustrative** hostname to replace with an authorized development VM; `devuser` is an authorized SSH account. `-N` instructs SSH to forward ports without starting a remote shell. On the IDE machine, `localhost:5005` must be free. If using another local port such as `15005`, attach the IDE to `localhost:15005` while the remote JVM still listens on `5005`.

The tunnel is encrypted by SSH, yet **JDWP still has no per-user authentication of its own**. Grant SSH access only to authorized personnel and disable the debug agent when the session ends.

### 9.2. Kubernetes Development Namespace

In Kubernetes, debug only when approved in a development namespace and with pod access permissions. Assuming the application was started with the debug agent listening on `*:5005` **inside the pod** (for instance via temporary env on a dev deployment), run on the developer's machine:

```bash
kubectl port-forward --address 127.0.0.1 deployment/jdwp-demo 5005:5005
```

If the namespace is not the current context's default, add `-n <namespace>` with the exact dev namespace. `kubectl port-forward` selects one pod from the deployment; if the pod restarts or the connection drops, re-establish the port-forward. `--address 127.0.0.1` keeps the **local port** bound only to loopback. Attach the IDE to `localhost:5005`.

**Prerequisites:** a JVM must be listening on 5005 inside the pod, and Kubernetes RBAC/network policies must permit port-forwarding. Running `kubectl port-forward` alone does not automatically enable JDWP on the application; enabling the agent typically requires **restarting the JVM process** with the appropriate JVM option. Avoid enabling JDWP on production deployments or exposing it via a public `Service`/`Ingress`. When debugging multiple replicas, target the specific pod handling your request; port-forwarding to a deployment may pick a different pod than the one receiving traffic.

### 9.3. Can You Attach to a Running JVM Without Enabling the Agent at Startup?

In standard Spring Boot workflows, the most reliable and reproducible approach is **starting the JVM with `-agentlib:jdwp`**. Certain JDKs/tools support dynamic agent attachment, but that requires matching OS/JDK permissions and cannot be assumed available inside containers or production environments. This guide uses the JDWP agent configured at startup to avoid the misconception that an IDE can attach to any arbitrary JVM.

## 10. Handling Breakpoints When Spring Boot Uses Multiple Classloaders

Spring Boot DevTools (if used by the project) may set up a separate **restart classloader** for application classes to speed up code reload detection. Consequences when debugging:

- Breakpoints may change state when classes reload or the app restarts; verify the IDE stays attached to the **right JVM** with matching source mappings.
- If new code is compiled while an older JVM is still running, the debugger may display updated source lines while in-memory classes still hold old bytecode. Rebuild/restart, or use HotSwap within your tooling's limits.
- **Hot Code Replace / HotSwap** generally supports editing method bodies, whereas structural class changes (adding fields/methods, changing hierarchy) usually require a JVM restart. Exact behavior depends on JDK, IDE, and runtime mode.
- Spring Boot DevTools **remote update/restart** is separate from JDWP and introduces distinct security risks; you do not need remote DevTools to attach a JDWP debugger.
- With Spring proxies (AOP, transactions, security), calls may route through proxies/interceptors; place breakpoints along the real controller/service path, and consider exception breakpoints to catch failures before handlers translate them.

**Breakpoints in constructors or bean startup:** use `suspend=y`. With `suspend=n`, Spring may already finish creating beans before the IDE attaches, causing startup breakpoints to be missed.

## 11. How Does a Debug Session End?

- **Disconnecting in the IDE** only detaches the debugger; the application usually keeps running unless killed by the IDE or launcher.
- **Stopping/Terminating the application** from the terminal, IDE, or container runtime is what actually ends the Java process.
- If the app is paused at a breakpoint and the debugger disconnects, whether threads resume or recover depends on the IDE and thread state; do not treat disconnect as a guaranteed resume mechanism.
- If the debug agent was enabled via Docker, CI, or deployment configuration, **remove that configuration source** so the next restart does not reopen the JDWP port.
- With `suspend=y` and no debugger attached, startup hangs indefinitely waiting; never accidentally ship this setting into production health-checked startups.

A helpful debug session records the **startup command**, JVM version, JDWP host/port, source revision, reproduction steps, and observed findings. Never store internal debug ports, passwords, or secrets in public documentation.

## 12. Common Errors and How to Fix Them

| Symptom | Possible Cause | Check and Fix |
| --- | --- | --- |
| IDE reports `Connection refused` | JVM lacks JDWP, wrong port, startup failed, agent listening on another address | Check JVM command, `Listening for transport dt_socket` log, host/port |
| IDE reports `Connection timed out` | Firewall, routing, Docker publish, Kubernetes port-forward, or SSH tunnel broken | Verify connectivity path to target JVM/port and network policy |
| `ERROR: transport error 202: bind failed` | JDWP port already used by another process, or invalid bind address | Change port, stop old JVM, verify bind IP |
| `JDWP Transport dt_socket failed to initialize` | Malformed option syntax, port unavailable, agent loaded twice | Ensure `-agentlib` appears once and precedes `-jar` |
| App does not open HTTP port 8080 | `suspend=y` awaiting attach/resume, or app startup failed | Attach debugger first; distinguish JDWP wait from Spring Boot logs |
| `bootRun --debug-jvm` runs, breakpoint never hits | IDE attached to Gradle daemon/other VM, or mismatched class | Check PID, source, JDWP port, and exact `bootRun` task |
| `-Dorg.gradle.debug=true` causes build to hang | Debugging the Gradle daemon, not the application | Use `bootRun --debug-jvm` for Spring Boot |
| Maven `spring-boot:run` ignores `-agentlib` | Wrong `-D` property name, missing `spring-boot.run.jvmArguments`, bad quoting | Use the exact Maven plugin parameter from Section 6 |
| Java reports `Unrecognized option: -agentlib...` | JVM option placed after `-jar` or invalid JDK/runtime | Move option before `-jar`, check `java -version` |
| Docker host sees 5005, attach fails | JDWP in container bound to `127.0.0.1` instead of container interface | Use `address=*:5005` inside container + loopback host publish |
| Container debug port publicly exposed | Used `-p 5005:5005` or public Service/Ingress | Publish `127.0.0.1:5005:5005`, use port-forward/tunnel, disable afterward |
| Source breakpoint stays gray or skipped | Source/bytecode mismatch, class unloaded, branch not reached | Rebuild, select right module, hit matching endpoint |
| Breakpoints stop working after DevTools restart | Classloader recreated, IDE/source mappings shifted | Check reload, reset breakpoint, disable DevTools restart temporarily to isolate |
| HTTP client times out while debugging | Request thread suspended at breakpoint | Resume thread, increase dev client timeout if needed |
| HotSwap fails after editing code | JVM/IDE does not support structural class changes | Restart app with updated artifact |
| `curl` to `/calc` returns 404 | Wrong endpoint, context path, HTTP port, or wrong build running | Use exact `/calc?a=2&b=3` and inspect Spring logs |
| IDE attaches, but hits wrong Kubernetes instance | Port-forward selected a different pod than the one serving traffic | Port-forward the target pod and route requests to that instance |

### Verification Commands on Windows and Linux/macOS

**On Windows PowerShell:**

```powershell
Get-NetTCPConnection -LocalPort 5005 -State Listen
```

**On Linux:**

```bash
ss -lntp | grep 5005
```

These two commands only check whether the **machine running the command** has a `LISTEN` socket. If the JVM runs inside Docker or a pod, inspect the proper network namespace as well as host binding/tunnels. Seeing no listener on 5005 on the host does not prove JDWP is off inside a container whose port has not been published.

Check the active JVM in your terminal:

```bash
java -version
```

When suspecting source/runtime mismatch, verify the built artifact version, actual started PID, and terminal/container logs. Never attach blindly to an existing port 5005 without confirming it belongs to the intended service.

## 13. Common Design Mistakes When Setting Up Remote Debugging

### Confusing JVM Debugging with Debug Logging

Spring Boot's `--debug` only increases Spring Boot diagnostic output; Gradle's `--debug` increases Gradle verbosity; JDWP requires the debug agent inside the application JVM. Similar flag names do not mean identical behavior.

### Enabling JDWP by Default Across All Environments

Putting `JAVA_TOOL_OPTIONS` in a shared base image, production Helm chart, or shell profile can open a debug port on every JVM at startup—including batch jobs, Gradle daemons, and replicas. Apply debug options only on **targeted development launches**, and disable them immediately once done. Note that deployments can share the same image while runtime environment controls whether the agent is enabled.

### Binding the Debug Port to All Interfaces Without Network Protection

`address=*:5005` may be needed inside a container, but if Docker publishes it across the host or a Kubernetes `Service` exposes it publicly, anyone able to reach JDWP gains deep process control. Protect it with loopback binding, SSH tunnels, internal Kubernetes `port-forward`, firewalls/RBAC, and least-privilege access. **JDWP must never be treated as an application API with built-in authentication**.

### Leaving `suspend=y` Enabled in CI or Production

Without a debugger attaching, the application waits forever, health checks fail, and restart loops ensue. Enable `suspend` only when catching startup code; never leave it in standard configuration.

### Source and Bytecode Mismatch

When remote debugging Docker or a VM, the IDE may display your current checkout while the JVM runs an artifact from an earlier commit. Breakpoints fail to hit or stop on misaligned lines. Rebuild the image from the exact source revision, verify artifact names/timestamps, and compile with debug symbols (Java compilers generate sufficient info by default; check custom compiler/minification settings if altered).

### Expecting the Debugger to Fix Runtime Configuration

Attaching JDWP **does not fix** Spring properties, environment variables, bean wiring, or network routing. The debugger helps observe the bug; changing application configuration typically requires a restart or explicit reload mechanism. Do not use Evaluate Expression to mutate real data outside authorized debug sessions.

## 14. End-to-End Operational Checklist

1. **Identify the right JVM:** will the app run via `java -jar`, Gradle `bootRun`, Maven `spring-boot:run`, Docker, or Kubernetes?
2. **Verify JVM/JDK:** Java 17+, matching source revision and running artifact; confirm the IDE holds matching sources.
3. **Choose suspend mode:** `y` to catch startup; `n` to debug requests once the app is ready.
4. **Choose bind/port:** local VM `127.0.0.1:5005`; containers may use `*:5005` internally while publishing only to loopback/tunnel.
5. **Start with the JDWP agent:** via `-agentlib:jdwp`, `bootRun --debug-jvm`, Gradle `debugOptions`, or Maven `spring-boot.run.jvmArguments`.
6. **Attach the IDE:** Remote JVM Debug (IntelliJ) or `request: attach` (VS Code) with the exact host and port.
7. **Set breakpoint and reproduce:** call `curl 'http://localhost:8080/calc?a=2&b=3'`, inspect `a=2`, `b=3`, `result=5`.
8. **Analyze:** inspect call stacks, threads, exceptions, and expressions; distinguish client timeouts caused while suspended.
9. **Clean up:** resume or stop the JVM, close port-forwards, clear debug variables, and confirm subsequent deployments do not open JDWP.

## 15. Official Documentation

- Oracle Java 17 – [JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html): `-agentlib:jdwp`, transport, `server`, `suspend`, and `address`.
- Gradle – [JavaExec API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html): `--debug-jvm` and `debugOptions`.
- Gradle – [JavaDebugOptions API](https://docs.gradle.org/current/javadoc/org/gradle/process/JavaDebugOptions.html): `enabled`, `host`, `port`, `server`, and `suspend`.
- Gradle – [Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): distinguishing Gradle daemon debugging.
- Spring Boot – [Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun` task based on `JavaExec`.
- Spring Boot – [Running Your Application with Maven](https://docs.spring.io/spring-boot/maven-plugin/run.html): `spring-boot.run.jvmArguments` for the forked JVM.
- IntelliJ IDEA – [Attach to Process / Remote JVM Debug](https://www.jetbrains.com/help/idea/attach-to-process.html): steps to configure debugger attachment.
- VS Code – [Java Debugging](https://code.visualstudio.com/docs/java/java-debugging): `launch.json` and `request: attach`.
- Kubernetes – [kubectl port-forward](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/): forwarding a port to a pod over Kubernetes.
- Docker – [Publishing and Exposing Ports](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/): meaning of host bindings when publishing a debug port.

**Key takeaway:** remote debugging is configured on the **JVM actually running the application**. `bootRun --debug-jvm` and Maven `spring-boot.run.jvmArguments` target the Spring Boot JVM, whereas `-Dorg.gradle.debug=true` targets the Gradle daemon. Bind JDWP to loopback whenever possible, use controlled tunnels remotely, verify matching source/bytecode, and disable the agent after debugging.