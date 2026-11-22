# Sample Project Structure and Reproducible Run Commands

When practicing CRaC (Coordinated Restore at Checkpoint), the result depends on both the application source code and the runtime environment. A project may build successfully on a regular JDK but fail to create a checkpoint if the JDK does not support CRaC or the Linux host lacks the prerequisites for CRIU. Similarly, a checkpoint created on one machine is not guaranteed to restore on another machine with a different architecture, kernel, or JDK build.

This lesson builds a small Java project to observe the full lifecycle: building the application, running the server, preparing resources before checkpoint, creating a checkpoint, restoring, and verifying that the server works again. The example uses Maven, Java 21, and the built-in HTTP server in the JDK to focus on the CRaC API without depending on a web framework.

## 1. Objectives and Practice Conditions

The sample project needs to demonstrate four things:

1. The same source code produces an artifact that can be rebuilt using locked tool versions.
2. The application registers resources with CRaC via `org.crac.Resource`.
3. The `beforeCheckpoint` callback releases resources that must be closed; the `afterRestore` callback recreates resources that must operate after restore.
4. After restore, the HTTP endpoint responds normally without having to re-run the entire application startup process.

### 1.1. Environment

| Component | Requirement |
|---|---|
| Operating system | Linux with CRIU checkpoint/restore support |
| JDK | A JDK distribution with CRaC integrated; this example uses Java 21 |
| Maven | Maven Wrapper with the version locked in the project |
| CRIU | Installed and passing the check on the actual runtime environment |
| OS permissions | Sufficient capabilities/permissions required by CRIU and the kernel |
| Architecture | Clearly record the CPU architecture and use it consistently for checkpoint/restore |

A regular JDK 21 is not synonymous with a CRaC-enabled JDK 21. Check the specific distribution and build before running. At startup, if the JVM reports that it does not recognize the `-XX:CRaCCheckpointTo` option, it is very likely using a JDK without CRaC.

CRaC checkpoint/restore relies on Linux and CRIU mechanisms. On Windows or macOS machines, use a Linux host or a VM/container with the required kernel and permissions. With WSL2 or Docker Desktop, only proceed when CRIU actually passes the check in that environment; installing CRIU into the filesystem does not prove full kernel support.

Checks before building:

```bash
java -version
javac -version
./mvnw -version
criu --version
criu check
uname -a
uname -m
```

The `criu` and `uname` commands run in the Linux environment that will be used for checkpointing. If `criu check` fails, resolve permissions, capabilities, kernel, or container configuration before investigating the Java code.

## 2. Project Structure

The example project is named `crac-demo`. Directory structure:

```text
crac-demo/
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── mvnw
├── mvnw.cmd
├── pom.xml
├── .gitignore
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── crac/
│                       ├── Application.java
│                       └── HttpServerResource.java
└── target/                         # generated during build; do not commit
    ├── crac-demo-1.0.0.jar
    └── crac-checkpoint/            # generated during checkpoint; do not commit
```

Role of each component:

- `pom.xml`: locks the Java version, CRaC API, and Maven plugins.
- `.mvn/wrapper/`, `mvnw`, `mvnw.cmd`: ensures every machine uses the same Maven version.
- `Application.java`: the application entry point, creates the resource and keeps the process running.
- `HttpServerResource.java`: owns the HTTP server and registers callbacks with CRaC.
- `target/`: contains local build and checkpoint artifacts. This is environment-generated data and is not committed to Git.

### 2.1. Maven Wrapper

Commit the Maven Wrapper files to the repository so others do not have to choose a Maven version themselves. The `.mvn/wrapper/maven-wrapper.properties` file should point to a fixed Maven release, for example:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

The `mvnw`, `mvnw.cmd`, and wrapper JAR/properties files must be generated using Maven Wrapper and committed with the project. Do not replace the URL with `LATEST`, a dynamic version, or a snapshot. If the organization requires verifying the Maven distribution checksum, add `distributionSha256Sum` taken from the official checksum of the exact Maven version chosen.

## 3. Build Configuration and CRaC API Declaration

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>crac-demo</artifactId>
    <version>1.0.0</version>
    <name>CRaC Demo</name>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <crac.version>1.4.0</crac.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>${crac.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.crac.Application</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The `org.crac:crac` dependency provides the API for source code to reference `Core`, `Context`, and `Resource`. The version in the example is declared explicitly so that builds do not automatically change with new versions on the Maven repository. The runtime performing the checkpoint must still be a CRaC-enabled JDK compatible with the API the application is compiled against.

You can skip the Maven Wrapper if only doing a quick test with an installed Maven, but the result then depends on the Maven version on that machine. For a shareable lab exercise, use `./mvnw` on Linux or `mvnw.cmd` on Windows for the standard build step.

## 4. Writing the Sample Application

### 4.1. Application Entry Point

Create the file `src/main/java/com/example/crac/Application.java`:

```java
package com.example.crac;

import java.util.concurrent.CountDownLatch;

public final class Application {

    private Application() {
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.getInteger("server.port", 8080);

        new HttpServerResource(port);

        System.out.println("READY: HTTP server listening on port " + port);

        // Keep the process alive so the JDK.checkpoint command can be sent.
        new CountDownLatch(1).await();
    }
}
```

The application creates an `HttpServerResource`, then waits indefinitely to keep the process running. This is a way to keep the example compact; in real applications, request-serving threads and other runtime components usually already keep the process alive.

### 4.2. Resource Managing the HTTP Server

Create the file `src/main/java/com/example/crac/HttpServerResource.java`:

```java
package com.example.crac;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class HttpServerResource implements Resource {

    private final int port;

    private HttpServer server;
    private ExecutorService executor;

    public HttpServerResource(int port) throws IOException {
        this.port = port;

        // Register the resource so the JVM invokes the two CRaC callbacks.
        Core.getGlobalContext().register(this);

        startServer();
    }

    private synchronized void startServer() throws IOException {
        if (server != null) {
            return;
        }

        HttpServer newServer =
                HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        ExecutorService newExecutor =
                Executors.newVirtualThreadPerTaskExecutor();

        newServer.setExecutor(newExecutor);
        newServer.createContext("/health", this::handleHealth);
        newServer.createContext("/", this::handleHome);
        newServer.start();

        executor = newExecutor;
        server = newServer;

        System.out.println("HTTP server started on port " + port);
    }

    private void handleHealth(HttpExchange exchange) throws IOException {
        reply(exchange, "OK\n");
    }

    private void handleHome(HttpExchange exchange) throws IOException {
        reply(exchange, "Hello from the CRaC demo\n");
    }

    private static void reply(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        System.out.println("beforeCheckpoint: stopping HTTP server");

        if (server != null) {
            // Stop accepting new connections and give the current exchange time to finish.
            server.stop(1);
            server = null;
        }

        if (executor != null) {
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }

            executor = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        System.out.println("afterRestore: starting HTTP server");
        startServer();
    }
}
```

The key point of the example lies in the resource lifecycle:

- The constructor registers the object with `Core.getGlobalContext().register(this)`, then starts the HTTP server.
- `beforeCheckpoint` stops the server and executor before the JVM creates the checkpoint. This avoids saving an open listener socket into the state to be restored.
- `afterRestore` creates a new server and executor so the process can accept requests again.
- Both callbacks are synchronized to avoid concurrent start/stop operations on the same resource.

This is an example for a small HTTP server. Real-world applications must also handle in-flight requests, connection pools, database connections, message consumers, schedulers, custom threads, file handles, and time-dependent resources. Do not copy these callbacks verbatim for every library; use the corresponding library's lifecycle API and ensure resources are closed/opened in the proper order.

## 5. Configuration Files and Building the Artifact

Create `.gitignore`:

```gitignore
/target/
/checkpoint/
*.hprof
hs_err_pid*
```

A checkpoint typically contains the application's memory state at the moment of capture. It can be large, environment-dependent, and contain runtime data. Keep the checkpoint in local practice storage; do not commit it to Git as a portable artifact.

Build from the project root directory:

```bash
./mvnw -B -ntp clean verify
```

The expected output is:

```text
target/crac-demo-1.0.0.jar
```

Inspect the manifest and dependency tree when you need to confirm the main class and API version:

```bash
unzip -p target/crac-demo-1.0.0.jar META-INF/MANIFEST.MF
./mvnw -B -ntp dependency:tree
```

The `clean` command deletes the old `target` directory before building, helping avoid mixing up artifacts or checkpoints from a previous run. Do not switch the JDK between the build step and the run step without actively checking bytecode, API, and CRaC runtime compatibility.

## 6. Running the Application Normally Before Checkpoint

First, you can run the application without requesting a checkpoint to test the endpoints:

```bash
java -jar target/crac-demo-1.0.0.jar
```

Open another terminal:

```bash
curl --fail --show-error http://127.0.0.1:8080/health
curl --fail --show-error http://127.0.0.1:8080/
```

Expected output:

```text
OK
Hello from the CRaC demo
```

Stop this test process before running the checkpoint exercise. If the old process continues holding port 8080, the next run may encounter an `Address already in use` error.

Having the endpoint work on a regular JDK only verifies the application and HTTP handlers. It does not prove that the environment can checkpoint/restore. The next step must use the proper CRaC-enabled JDK.

## 7. Creating a Checkpoint

### 7.1. Starting with a CRaC-Enabled JDK

From the project directory, choose a new checkpoint path for this run:

```bash
java -XX:CRaCCheckpointTo="$PWD/target/crac-checkpoint" \
     -jar target/crac-demo-1.0.0.jar
```

Keep this terminal open. The application must print the message that the server is ready. Using another terminal, with the same user and the same JDK, find the PID:

```bash
jcmd -l
```

Select the PID of `com.example.crac.Application` or the corresponding JAR process. Send the checkpoint command:

```bash
jcmd <PID> JDK.checkpoint
```

Replace `<PID>` with the actual PID number. The JVM invokes the registered resource callbacks; in this example, the `beforeCheckpoint` log appears and the HTTP server is stopped before the checkpoint completes.

Do not invoke `criu dump` directly as a replacement for this command. The CRaC-enabled JDK coordinates the checkpoint with the JVM, including callbacks and necessary runtime handling.

### 7.2. Verifying the Checkpoint Result

After the command completes, verify that the `target/crac-checkpoint` directory contains checkpoint data. The exact file layout depends on the JDK/CRIU and should not be assumed to be a single file.

A new run should use a new checkpoint directory. Do not mix files from multiple checkpoints into the same directory. If you need to start over from scratch, build with `clean` to remove the old `target` and then create a new checkpoint.

## 8. Restoring the Process

Restore using the exact same CRaC-enabled JDK that created the checkpoint:

```bash
java -XX:CRaCRestoreFrom="$PWD/target/crac-checkpoint"
```

The restore command initializes the JVM from the checkpoint state. When the resource callbacks are invoked, `afterRestore` creates a new HTTP server on port 8080.

Test the endpoints from another terminal:

```bash
curl --fail --show-error http://127.0.0.1:8080/health
curl --fail --show-error http://127.0.0.1:8080/
```

If it returns `OK` and `Hello from the CRaC demo`, the server is accepting requests after restore. You can send multiple consecutive requests to confirm the listener remains active:

```bash
for i in 1 2 3 4 5; do
    curl --fail --silent http://127.0.0.1:8080/health
done
```

Do not start a new instance of the application on the same port while restoring. When restore fails, read the JVM and CRIU logs to determine how far the checkpoint was read, which callbacks ran, and which resource could not be restored.

## 9. Organizing Commands for Reproducible Subsequent Runs

Do not rely on memory for commands typed in the terminal. Save the practice commands in the repository's README or scripts so others can follow the exact same sequence.

A standard procedure can be documented as steps:

```text
1. Verify Linux, kernel, CRIU, and checkpoint permissions.
2. Select the right CRaC-enabled JDK.
3. Record tool versions and Git commit.
4. ./mvnw clean verify
5. Run the JAR with -XX:CRaCCheckpointTo=<checkpoint-dir>.
6. Find the PID using jcmd -l.
7. Send jcmd <PID> JDK.checkpoint.
8. Restore with -XX:CRaCRestoreFrom=<checkpoint-dir>.
9. Call /health and check the afterRestore log.
```

To save environment evidence before checkpointing, you can create a `target/environment.txt` file:

```bash
{
    date -u
    git rev-parse HEAD
    uname -a
    uname -m
    java -version 2>&1
    ./mvnw -version
    criu --version
    sha256sum target/crac-demo-1.0.0.jar
} > target/environment.txt
```

If the build is not inside a Git repository, omit the `git rev-parse HEAD` line or replace it with the source version identifier the team is using. Save the build log, checkpoint log, and restore log as well when comparing multiple experimental runs.

## 10. Locking Factors That Affect Reproducibility

The same command does not guarantee the same checkpoint. Record and control the following factors:

| Factor | How to Record or Lock |
|---|---|
| Source code | Specific Git commit or tag |
| Java | Vendor, version, build number, and architecture |
| Maven | Maven Wrapper version and wrapper distribution URL |
| Dependencies | Explicit dependency/plugin versions; save dependency tree |
| CRIU | Version and `criu check` output |
| Linux | Distribution, kernel version, architecture, and capabilities |
| App configuration | Port, environment variables, JVM options, and config files |
| Artifact | SHA-256 of the JAR after build |
| Checkpoint path | Absolute path and filesystem used |

### 10.1. Same JDK Build

Use the same JDK vendor, version, and build for both checkpoint and restore. Merely recording “Java 21” is not enough because distributions may differ in patch level, CRaC integration, or native configuration. The `java -version` output should be saved verbatim.

### 10.2. Same Linux Environment

A checkpoint can depend on the kernel, CPU architecture, CRIU, filesystem, network namespace, and capabilities granted to the process. Therefore, do not treat a checkpoint as a JAR file that can be carried to any machine to run. Create and restore it in a defined compatible environment.

If running in a container, record the image digest instead of only a mutable tag. Ensure the checkpoint directory resides on a permitted filesystem and has the same path during restore. Mounts, ports, network namespaces, and access permissions must match the state at the time the checkpoint was created.

### 10.3. Same Artifact and Configuration

Build from the chosen source commit, record the JAR checksum, and keep the JVM options identical. Changing environment variables, system properties, native libraries, or config files can cause post-restore behavior to differ from previous runs.

Do not use `LATEST`, version ranges, or snapshot dependency versions for a reproducible lab exercise. Lock Maven plugins and direct dependencies; when deeper control is needed, save the dependency tree and checksums of resolved artifacts.

### 10.4. A Checkpoint Is the Output of a Runtime State

Even with identical code and tools, data residing in the heap can differ due to workload, request order, warm-up timing, or caches. Therefore, fix the warm-up workload, endpoint call sequence, wait times, and request-stopping conditions before checkpointing.

If the goal is to compare restore times, run the same warm-up scenario and the same number of requests. Record clearly how long after startup the checkpoint was created and what types of requests the application processed.

## 11. Common Errors

| Symptom | Cause to Check | Resolution |
|---|---|---|
| `Unrecognized VM option 'CRaCCheckpointTo'` | Using a JDK without CRaC support or wrong build | Verify `JAVA_HOME`, `java -version`, and `jcmd` path |
| `criu check` fails | Kernel, permissions, capabilities, or container configuration unsuitable | Check on the target Linux host/container; fix OS prerequisites first |
| `Operation not permitted` | Process lacks required checkpoint permissions/capabilities | Check user, container runtime, and granted capabilities |
| `Address already in use` after restore or at start | Old process or another listener is holding the port | Identify PID and listener status before re-running |
| No `afterRestore` log visible | Restore did not reach callback, resource not registered, or restore failed earlier | Read JVM/CRIU logs and verify resource registration |
| Endpoint unresponsive after restore | Callback did not reopen server, wrong port, or network namespace | Check `afterRestore` log, port binding, and network namespace |
| Build cannot find `org.crac` | Missing dependency or Maven cannot resolve repository | Check dependency in POM and dependency tree |
| Restore fails when changing machines | Different JDK, kernel, architecture, filesystem, or native environment | Return to a compatible environment where the checkpoint was created |

When investigating, separate errors into three layers: artifact build, JVM/CRIU checkpoint, and post-restore resource initialization. A successfully built JAR does not prove checkpointing will succeed; a created checkpoint also does not prove the application is ready to serve requests after restore.

## 12. Extending the Project for Real-World Applications

After the HTTP server example works, you can add each type of resource into the same project structure:

- **Database pool**: close the pool before checkpoint; create a new pool and validate connections after restore.
- **HTTP client**: handle connection pools and open sockets according to the client's lifecycle.
- **Message consumer**: stop receiving messages, finish or roll back in-flight messages, then re-subscribe.
- **Scheduler**: pause jobs, avoiding duplicate runs or missed schedules upon restore.
- **Cache**: determine which caches can be retained and which need refreshing due to time-sensitive data.
- **Credentials/tokens**: check expiration and refresh if tokens are no longer valid after the checkpoint duration.

Each resource should have a clear owner, a way to close before checkpoint, and a way to recover after restore. Callbacks should be idempotent where appropriate: being invoked again in a retry scenario must not create multiple duplicate pools, listeners, or schedulers.

When integrating into Spring Boot, resources can be registered via lifecycle-managed beans or a dedicated initialization component. Do not rely solely on the fact that the Spring context still exists in the heap to conclude that all connections, sockets, and threads managed by beans remain valid after restore.

## 13. Criteria for Verifying a Practice Run

A run can be considered reproducible when someone else can check out the exact source commit, use the exact recorded JDK/Maven/CRIU and Linux environment, and re-execute all commands without modifying source code or guessing configurations.

The minimum evidence that should be saved:

- Source Git commit and JAR checksum.
- Full JDK, Maven Wrapper, and CRIU versions.
- Linux kernel info, architecture, and `criu check` output.
- Startup command with `CRaCCheckpointTo` and the `JDK.checkpoint` command.
- `beforeCheckpoint` and `afterRestore` callback logs.
- Endpoint call results before checkpoint and after restore.
- Checkpoint path and required configuration to restore in the same environment.

Once this evidence is in place, you can change one factor at a time — such as the JDK build, warm-up configuration, or resource type — to evaluate its impact. Keeping the remaining factors constant makes comparisons meaningful and helps isolate whether an issue belongs to source code, JVM, CRIU, or the deployment environment.
