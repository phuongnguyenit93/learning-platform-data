# Smoke Testing Startup from the Packaged JAR Instead of Running Only from Source

## 1. Why Must You Verify the Exact Artifact to Be Released?

In a Spring Boot application, `mvn spring-boot:run` or `./gradlew bootRun` may start cleanly, and unit tests plus `@SpringBootTest` may all pass, yet `java -jar app.jar` on the deployment host still fails. The reason: running from an IDE or build classpath **is not identical** to launching the packaged executable JAR.

Several failures appear only in the packaged artifact:

- `spring-boot:repackage` or `bootJar` did not run, so the selected file is a **plain JAR** lacking the Spring Boot launcher.
- The manifest lacks `Main-Class`, has a wrong `Start-Class`, or the main class is absent from the archive.
- A dependency exists only on the compile/test classpath or was excluded from the runtime package, causing `ClassNotFoundException` or `NoClassDefFoundError`.
- A resource in `src/main/resources` is missing from `BOOT-INF/classes`, mis-filtered, or resolved differently at runtime than from source paths.
- The build used a newer JDK than the deployment JRE, causing `UnsupportedClassVersionError`.
- The upload pipeline or Dockerfile picked the wrong file from another module or a stale artifact left over from an earlier build.

That is why this lesson—part of **Build Verification** under **Spring Boot Build Tooling Packaging**—requires a test that **actually starts and calls the packaged JAR**. This is commonly called a **packaged-artifact smoke test** or **JAR startup smoke test**.

### Lesson Objectives

1. Distinguish testing against source/test classpaths from testing the **actual executable JAR**.
2. Understand how Maven `repackage`, Gradle `bootJar`, manifests, and the `BOOT-INF` layout affect startup.
3. Write a Java 17+ Spring Boot application with a verification HTTP endpoint.
4. Build a Java 17 runner using `ProcessBuilder` to launch `java -jar`, poll HTTP with a timeout, detect early process exit, capture logs, and clean up the process when finished.
5. Apply the same workflow to Maven and Gradle, then integrate it into CI prior to upload/publish.
6. Distinguish "the server opened a port" from "the application is ready," without over-interpreting an HTTP 200.

**Example versions:** Spring Boot `3.3.5`, Java `17`, and compatible Maven/Gradle. These versions are fixed to present concrete syntax and do not imply the latest release. In real projects, use the Java, build plugin, and Spring Boot versions required by your project's compatibility matrix.

## 2. Comparing Four Ways to Run Spring Boot

| Run / test mode | Classpath / entry point source | Evidence obtained | What is **not** verified |
| --- | --- | --- | --- |
| `@SpringBootTest` | Test classpath, Spring test context | Beans/configuration initialize in the test context | Whether the release JAR has valid manifest, launcher, and runtime dependencies |
| `mvn spring-boot:run` | Classes/dependencies from Maven project | Can launch from the Maven development classpath | Whether the `package/repackage` artifact runs with `java -jar` |
| `./gradlew bootRun` | Gradle `JavaExec` with build classpath | Can launch from the Gradle project | Whether `bootJar` output runs |
| `java -jar path/to/app.jar` | **The built JAR itself** and its embedded boot launcher | Launches via the exact path used in deployment | Does not automatically prove all business logic and external dependencies work |

Even `@SpringBootTest(webEnvironment = RANDOM_PORT)` normally uses the build tool's test runtime classpath; it can launch a real web server during tests, yet **it does not execute the packaged executable JAR**.

**Scenario example:** `Application.java` code is valid, and both `mvn spring-boot:run` and the IDE work. However, the POM lacks the Spring Boot Maven Plugin, so `mvn package` builds only a plain JAR. Once deployed to a server, `java -jar` fails with `no main manifest attribute`. A packaged-JAR smoke test catches this before publish.

These four layers **complement each other**: unit tests are fast, Spring context tests verify wiring, integration tests verify system interactions, and packaged smoke tests focus on **the executability of the release artifact**.

## 3. What Makes a JAR Startup Smoke Test Reliable?

A minimal flow should look like:

~~~text
Clean workspace
      |
      v
Compile + unit tests
      |
      v
Maven package/repackage or Gradle bootJar
      |
      v
Select the EXACT executable JAR file
      |
      v
Inspect manifest/layout if needed
      |
      v
Launch JAR in a separate Java process
      |
      v
Poll endpoint with bounded timeout
      |
      +---- process exited early? ---> FAIL + read log
      +---- timeout expired? --------> FAIL + read log
      +---- wrong HTTP/status/body? -> FAIL
      |
      v
HTTP 200 + body matches contract
      |
      v
Clean up process in finally
      |
      v
Smoke runner exits 0 -> PASS
~~~

For a typical **web service**, the server does not exit on its own after serving a request; the runner must **actively stop** it once readiness is confirmed. Writing a test that merely waits for the child process to exit `0` can hang the build indefinitely. Conversely, for a **CLI/batch app** designed to terminate, the expected exit code and stdout/stderr form the main contract.

A solid smoke test should:

- Verify **the artifact file exists** before starting.
- Invoke `java -jar` with a deterministic runtime without importing app classes into the test runner.
- Catch **early child process exit** and retain logs for diagnosis.
- Poll the endpoint instead of sleeping for a fixed duration.
- Enforce both an overall deadline and per-HTTP-request timeouts.
- Assert **both status code and response body** or an explicit health criterion.
- Guarantee the child process is stopped even if the test throws an exception.
- Return a **non-zero exit code** on failure so CI blocks publishing.

## 4. Maven Practice: Creating an Executable JAR with an HTTP Probe

The minimal Spring Boot example below exposes `GET /probe` returning `packaged-ok`. We will package it as a JAR, then launch and call the endpoint from another Java program.

### 4.1. Project Structure

~~~text
packaged-startup-demo/
  pom.xml
  PackagedJarSmokeTest.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`PackagedJarSmokeTest.java` is a standalone file at the **project root**, outside `src/main/java`. Maven will not bundle that test harness into the application. This keeps **shipped code** distinct from **verification harness code**.

### 4.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>packaged-startup-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

**Explanation:**

- `spring-boot-starter-parent` provides Maven defaults compatible with Spring Boot, including a pre-defined `repackage` execution; declaring `spring-boot-maven-plugin` in `plugins` enables `mvn package` to build an executable JAR.
- `spring-boot-starter-web` pulls in Spring MVC and the embedded server.
- `java.version=17` sets the example's compatibility baseline; the actual JDK used to compile/build must match.
- `artifactId=packaged-startup-demo` and `version=1.0.0` produce the default local file `target/packaged-startup-demo-1.0.0.jar` with JAR packaging when `finalName` and classifier are unchanged.
- If a project **does not use Boot parent**, bind `spring-boot:repackage` explicitly to the lifecycle; declaring Boot dependencies alone does not make the JAR executable.

### 4.3. Complete Java 17 `Application.java`

Create `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @GetMapping(value = "/probe", produces = "text/plain")
    public String probe() {
        return "packaged-ok";
    }
}
~~~

`Application` serves both as the `main` entry point and as a `@RestController` exposing `/probe`. On a successful request:

~~~text
GET /probe
HTTP 200
Body: packaged-ok
~~~

This block **describes three request/response facts**, not verbatim console stdout. The actual body is the string `packaged-ok` with no extra newline added by application code. Never treat Spring Boot console startup logs as a substitute for an HTTP assertion.

### 4.4. Building the JAR

From the project root:

~~~bash
mvn clean package
~~~

Maven runs the lifecycle through `package`, builds the archive, and Spring Boot `repackage` replaces the main JAR with an executable archive. The file will be:

~~~text
target/packaged-startup-demo-1.0.0.jar
~~~

If using a Maven Wrapper, the command is `./mvnw clean package` (Linux/macOS) or `.\mvnw.cmd clean package` (Windows PowerShell). The example does not auto-generate a Wrapper; use a compatible Maven installation when no Wrapper is present.

Use the JDK's `jar` tool to inspect the archive:

~~~bash
jar tf target/packaged-startup-demo-1.0.0.jar
~~~

In a typical Spring Boot 3.3 executable JAR layout, entries look like:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

This is an **abbreviated listing**, not the full stdout of `jar tf`. `BOOT-INF/classes` holds application classes and resources; `BOOT-INF/lib` holds runtime JARs; `org/springframework/boot/loader` classes bootstrap the archive.

If `unzip` is available, inspect the manifest:

~~~bash
unzip -p target/packaged-startup-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

With Boot 3.3 and default layout, the manifest typically includes:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

`Main-Class` is the launcher the JVM invokes on `java -jar`; `Start-Class` is the application class the launcher invokes. Launcher class names can change across Boot versions or WAR/ZIP layouts, so never hardcode them as immutable constants.

## 5. Writing a Self-Contained Java 17 JAR Smoke Test

Running the JAR manually and curling it from a second terminal is fine during ad-hoc experiments, but automation requires controlling the child process, port, and timeouts. Below is a program **using only the standard JDK**.

Design:

1. Accept the artifact path **as an argument**, never guessing with globs.
2. Use the runner's own `java.home` to launch the child JVM, avoiding accidental selection of a different JDK on `PATH`.
3. Request an available loopback port temporarily, then let Spring Boot bind that port.
4. Redirect Spring Boot stdout/stderr to a temporary log file to prevent pipe buffer stalls.
5. Poll `GET /probe` for up to 45 seconds with a 2-second timeout per request.
6. Fail if the child exits early, times out, or returns HTTP 200 with an unexpected body.
7. Clean up the child process in `finally` and return an accurate exit status to CI.

**Note:** picking a port via a socket and releasing it leaves a small window where another process could claim the port (*TOCTOU race*). The lesson uses this approach for simplicity on Java 17 and typical learning machines. For heavily loaded CI or high reliability, consider `server.port=0` paired with passing back the actual bound port, or bounded port-selection retries.

### 5.1. Complete `PackagedJarSmokeTest.java`

Place at the project root alongside `pom.xml`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class PackagedJarSmokeTest {

    private static String javaExecutable() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        String file = os.startsWith("windows")
                ? "java.exe" : "java";
        return Path.of(System.getProperty("java.home"),
                "bin", file).toString();
    }

    private static int choosePort() throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (ServerSocket socket =
                new ServerSocket(0, 50, loopback)) {
            return socket.getLocalPort();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java PackagedJarSmokeTest.java <jar-path>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException(
                    "JAR not found: " + jar);
        }

        int port = choosePort();
        Path log = Files.createTempFile("jar-smoke-", ".log");

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable(),
                "-jar",
                jar.toString(),
                "--server.address=127.0.0.1",
                "--server.port=" + port,
                "--spring.main.banner-mode=off");
        builder.redirectErrorStream(true);
        builder.redirectOutput(log.toFile());

        Process child = builder.start();
        boolean passed = false;

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();
            URI uri = URI.create(
                    "http://127.0.0.1:" + port + "/probe");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(45);
            int lastHttpStatus = -1;

            while (System.nanoTime() < deadline) {
                if (!child.isAlive()) {
                    throw new IllegalStateException(
                            "JAR exited early; exit="
                                    + child.exitValue()
                                    + "; log=" + log);
                }

                try {
                    HttpResponse<String> response = client.send(
                            request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
                    lastHttpStatus = response.statusCode();

                    if (lastHttpStatus == 200) {
                        if (!"packaged-ok".equals(response.body())) {
                            throw new AssertionError(
                                    "Unexpected /probe body: "
                                            + response.body());
                        }
                        passed = true;
                        System.out.println("smoke.status=PASS");
                        System.out.println("smoke.http=200");
                        System.out.println("smoke.body=packaged-ok");
                        return;
                    }
                } catch (IOException connectionNotReady) {
                    // Server may not yet be ready to accept requests.
                }

                Thread.sleep(250);
            }

            throw new IllegalStateException(
                    "Timeout waiting for /probe; last HTTP="
                            + lastHttpStatus + "; log=" + log);
        } finally {
            if (child.isAlive()) {
                child.destroy();
                if (!child.waitFor(5, TimeUnit.SECONDS)) {
                    child.destroyForcibly();
                    child.waitFor(5, TimeUnit.SECONDS);
                }
            }

            if (passed) {
                try {
                    Files.deleteIfExists(log);
                } catch (IOException ignored) {
                    // Log cleanup does not affect a passed probe.
                }
            } else {
                System.err.println("smoke.log=" + log);
            }
        }
    }
}
~~~

**Key details to understand:**

- `System.getProperty("java.home")` retrieves the JDK/JRE **running the runner**; `javaExecutable()` uses that exact binary path, avoiding `PATH` mismatches across multiple JDKs. Checking `os.startsWith("windows")` prevents mistaking macOS (`Darwin`) for Windows.
- `ServerSocket(0)` lets the OS pick an ephemeral port on `127.0.0.1`. After closing the socket, Spring Boot can bind that port. A small race window remains, so inspect startup logs on failure.
- `ProcessBuilder` launches **an independent process** with `-jar`; the runner **never** imports `demo.Application`, preventing it from accidentally running off the source classpath.
- `redirectErrorStream(true)` and `redirectOutput(log.toFile())` capture startup logs to a file. When the child fails, the error points to the log path so you can read the stack trace.
- `HttpClient` sends a real `GET` to the server. Never treat an open port or a "Started" log line as sole proof of passing.
- `child.isAlive()` catches early crashes before the route comes up. `IOException` while the server is still binding is retried; assertion errors are not swallowed.
- `deadline` and `HttpRequest.timeout` prevent infinite hangs; `Thread.sleep(250)` throttles polling without assuming startup completes in 250 ms.
- `finally` cleans up the child on PASS, wrong HTTP body, timeout, or exception. A normal web server **does not exit with code 0** after a request, so the runner stops it actively instead of waiting for exit.
- On PASS, the temp log is deleted if possible. On FAIL, the log is preserved for diagnostics. In production systems, apply log-handling safeguards since startup logs can contain sensitive details.

### 5.2. Running on Linux/macOS and Windows

After `mvn clean package`, run from the project root:

~~~bash
java PackagedJarSmokeTest.java target/packaged-startup-demo-1.0.0.jar
~~~

On Windows PowerShell, use a Windows path:

~~~powershell
java PackagedJarSmokeTest.java .\target\packaged-startup-demo-1.0.0.jar
~~~

Java 17 supports **source-file mode**, so the runner does not require separate `javac` and `java -cp` steps. Both commands launch a second JVM using `java -jar` on the packaged archive.

On success, **the test runner's stdout** is exactly:

~~~text
smoke.status=PASS
smoke.http=200
smoke.body=packaged-ok
~~~

These three lines are printed by `PackagedJarSmokeTest` itself. The child process's Spring Boot logs go to the temp log file rather than mixing into this output. An HTTP body like `packaged-ok` will differ in a real application; if you change the endpoint, update the assertion to match the **defined contract** rather than deleting the assertion just to pass.

On failure, the Java launcher exits non-zero and prints a stack trace; the runner retains the log file to inspect Spring Boot errors. Never treat file existence or HTTP 200 from **another process** as proof of passing.

### 5.3. Four Illustrative FAIL Cases

**Error 1 — wrong path**

~~~text
JAR not found: ...
~~~

Fix the path, verify the module, `finalName`, and classifier. If packaging has not run yet, run the packaging task first. Never create a dummy file or substitute `spring-boot:run` to "pass" the check.

**Error 2 — early child exit**

~~~text
JAR exited early; exit=1; log=...
~~~

The JVM exited before the endpoint became ready. Open the log: it could be a main class/Java version mismatch, missing dependency, runtime config error, or port-bind failure. Never guess the cause solely from exit code `1`.

**Error 3 — timeout**

~~~text
Timeout waiting for /probe; last HTTP=-1; log=...
~~~

`last HTTP=-1` means the runner **received no HTTP response at all**, not necessarily that packets were dropped. If `404`, `401`, or `503` was received, `last HTTP` preserves that status so you can investigate routes, security, or readiness.

**Error 4 — wrong body**

~~~text
Unexpected /probe body: ...
~~~

If HTTP 200 is returned with a body other than `packaged-ok`, the test **FAILS immediately**. This can indicate a changed route, wrong artifact, or another service listening on that port. An assertion checking only 200 is insufficient when you need to confirm the exact target application answered.

## 6. Ensuring the Test Runs the Exact JAR Just Built

### 6.1. Choosing the Right File Among Multiple Artifacts

A project may contain:

~~~text
target/
  packaged-startup-demo-1.0.0.jar
  packaged-startup-demo-1.0.0.jar.original
  packaged-startup-demo-1.0.0-exec.jar
~~~

These are **examples of filenames that appear under different configurations**, not a claim that every build creates all three. Maven Spring Boot `repackage` by default replaces the main artifact and saves the plain JAR with `.original`. When using an `exec` classifier, the executable archive is attached separately as `-exec.jar`.

Never blindly pick `target/*.jar` because wildcards can match multiple files. Pick **the exact archive to be deployed**, inspect its manifest if uncertain, and pass the explicit path to the runner.

With Gradle, the `jar` task may produce a plain JAR while `bootJar` produces the executable archive. Check `archiveFileName` or the output path reported by the build tool instead of assuming every file under `build/libs` is runnable.

### 6.2. Do Not Test Stale JARs Left in `target`

When CI skips `clean`, a stale `target/app-old.jar` from an earlier build may linger. A smoke test pointing to a stale file can PASS even when the latest commit produces a broken artifact. Build in a clean workspace, verify timestamps/artifact paths, and pass only the artifact produced by the current build.

A valid sequence:

~~~bash
mvn clean package
java PackagedJarSmokeTest.java target/packaged-startup-demo-1.0.0.jar
~~~

A sequence that **does not** verify the packaged JAR:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

The second command runs the project via the development plugin rather than launching the archive with `java -jar`. Likewise, Gradle `bootRun` is no substitute for `bootJar` smoke testing.

### 6.3. Verifying Artifact Bytes Between Test and Publish

An artifact can be altered after the smoke test (for instance, if the pipeline rebuilds or copies a different file). To guarantee you publish **the exact artifact tested**, compare SHA-256 digests or artifact identifiers across pipeline stages.

Linux/macOS:

~~~bash
sha256sum target/packaged-startup-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\packaged-startup-demo-1.0.0.jar -Algorithm SHA256
~~~

The digest changes whenever file contents change. Never hardcode a fake checksum in documentation; record the real checksum and verify it against the artifact at upload/deploy time. For Docker images, also test the **final image itself**, since the Dockerfile, base JRE, file permissions, and entrypoint may differ from the host runtime.

## 7. Equivalent Workflow with Gradle `bootJar`

Use the following `build.gradle` (Groovy DSL), keeping `src/main/java/demo/Application.java` and the root runner unchanged:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.learning'
version = '1.0.0'

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
}

tasks.named('bootJar') {
    archiveFileName = 'packaged-startup-demo.jar'
}
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'packaged-startup-demo'
~~~

Build and smoke-test from the project root containing the Gradle Wrapper:

~~~bash
./gradlew clean bootJar
java PackagedJarSmokeTest.java build/libs/packaged-startup-demo.jar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
java PackagedJarSmokeTest.java .\build\libs\packaged-startup-demo.jar
~~~

`bootJar` is the task that builds the executable Spring Boot JAR; `bootRun` launches the app from the project classpath. Gradle `assemble` or `build` may depend on `bootJar` in standard Spring Boot/Java setups, yet `build` itself **does not run a packaged black-box smoke test** unless you wire a custom task.

**Java Toolchains note:** Gradle toolchains can select a compilation JDK independent of the JVM running Gradle. The runner uses the JDK executing the runner to launch the child JVM, so CI must select the **exact target Java runtime** to test deployment compatibility. Running a Java 17 artifact on JDK 21 does not prove it works on production Java 17.

## 8. Distinguishing Startup, Liveness, Readiness, and Business Health

The `/probe` endpoint in the example proves the Spring Boot HTTP server can return a specific response. That check is very valuable, yet it does not mean the whole system is ready for every workload.

| Verification level | Example evidence | Do not conclude |
| --- | --- | --- |
| Process liveness | `child.isAlive()` is `true` | HTTP server bound or ready to serve requests |
| TCP listen | Port connection succeeds | Routes and HTTP status are correct |
| HTTP smoke | `GET /probe` returns 200 + expected body | DB, broker, and SSO are all healthy |
| Application readiness | Readiness health group reports ready for traffic | Every business transaction works |
| Integration/contract | Exercises real database/API/messaging | All E2E flows were tested |
| End-to-end | Multiple tiers participate in a real user flow | Zero long-running or environment risks remain |

### 8.1. Using Spring Boot Actuator When Appropriate

If a project includes `spring-boot-starter-actuator`, `/actuator/health` is the familiar health endpoint. Spring Boot offers application availability with liveness/readiness indicators and health groups such as `/actuator/health/liveness` and `/actuator/health/readiness` when probes are enabled and configured.

Never assume those endpoints are always public or always return `200`: `Spring Security`, actuator exposure, management port, context path, and health status all affect responses. For production-like checks, probe the actual readiness endpoint configured for deployment with proper access controls; if `401`/`403` is returned, review security policy before concluding the app failed to start.

**Liveness** indicates whether a process needs restarting; **readiness** indicates whether it should receive traffic. Avoid placing every external dependency into liveness to prevent cascading restarts during external outages. Layer packaged smoke tests separately from readiness and dependency tests rather than mixing them indiscriminately.

### 8.2. Services with a Context Path or Security

If a real service sets `server.servlet.context-path=/api`, `/probe` moves to `/api/probe`. The example runner uses a fixed path to teach the mechanism; in real projects, parameterize the URL or read test config to match the route. Similarly, if security requires authentication, test an allowed endpoint in the test environment rather than disabling all security just to get HTTP 200.

## 9. Wiring the Check into CI Without Distorting Its Meaning

A pipeline should follow this sequence:

~~~text
Checkout code
    -> verify toolchain/JDK
    -> compile + unit tests
    -> build executable JAR
    -> packaged JAR smoke test
    -> archive / publish the EXACT tested JAR
    -> deploy
    -> health/readiness smoke in target environment
~~~

Ensure a failure in any stage **blocks the publish stage**. Never run smoke tests with `mvn spring-boot:run` or `bootRun` and label the artifact "packaged JAR verified."

### 9.1. Maven in POSIX Shell

~~~bash
set -e
mvn clean package
java PackagedJarSmokeTest.java target/packaged-startup-demo-1.0.0.jar
~~~

`set -e` is a simple POSIX shell pattern with context-dependent caveats. In CI providers, rely on the runner's native fail-on-nonzero step behavior so publishing never proceeds after a failed smoke runner.

### 9.2. Gradle in POSIX Shell

~~~bash
set -e
./gradlew clean bootJar
java PackagedJarSmokeTest.java build/libs/packaged-startup-demo.jar
~~~

On Windows PowerShell, scripts chaining multiple native commands must inspect `LASTEXITCODE` or set appropriate error handling; do not always assume a non-zero Java exit code automatically aborts the script.

### 9.3. Maven Failsafe Differs from Testing the Executable JAR

`maven-surefire-plugin` normally runs unit tests, while `maven-failsafe-plugin` runs integration tests via `integration-test` and `verify`. However, **simply adding Failsafe or running `mvn verify` does not automatically test the packaged JAR**. You must either write an integration test that explicitly invokes `java -jar` on the packaged file or run the smoke runner step in CI after packaging.

If integrating the packaged smoke test into JUnit/Failsafe or Gradle verification tasks, verify:
- The phase/task executes **after** `package/repackage` or `bootJar`.
- The artifact path passed is the current build's output.
- The test does not fall back to the test classpath instead of the archive.
- The child process is cleaned up even on assertion exceptions.
- Test outcomes propagate via exit codes/reports to block publishing.

A standalone runner was chosen in this lesson to make the boundary between **building** and **running the artifact** crystal clear; in real projects, you may integrate it via tasks/plugins per team conventions.

## 10. Isolating Processes, Ports, and Environments

### 10.1. Avoid Uncontrolled Fixed Ports

If you hardcode `8080` while an old service is running, the test can receive HTTP 200 from **a service other than the new JAR**. The runner requests a random loopback port, checks that the child stays alive, and asserts the body. This reduces risk, though a small race window remains between picking the port and Spring Boot binding it.

For tests requiring absolute instance identity, pass a unique nonce to the app and return it in the endpoint response, or read the bound port communicated directly by the new process—never rely solely on "HTTP 200 from localhost" as proof of identity.

### 10.2. Bounded Logs and Timeouts

An unreliable manual approach:

~~~bash
java -jar app.jar &
sleep 3
curl http://localhost:8080/health
~~~

Without tracking the PID and a trap/cleanup, the process can outlive the job. Nor does `sleep 3` guarantee readiness: CI may be slower, or the app may crash early.

The runner in this lesson uses:
- 45-second overall deadline, 2-second HTTP request timeout.
- `isAlive` check before every request.
- Bounded retries while connections are not yet accepted.
- Immediate failure on HTTP 200 with wrong body.
- `ProcessBuilder` log redirection to a file so output streams never deadlock.
- `finally` stopping the child process, even on FAIL.

These are **illustrative settings**, not universal SLAs for every service. Real projects should tune budgets to startup profiles and CI resources.

### 10.3. Working Directory and Runtime Environment

`java -jar` may be launched from a working directory different from your IDE. If code calls `Files.readString(Path.of("config/service.yml"))`, it looks for a **file relative to the working directory**, not a resource inside the JAR. For packaged resources, normally load from the classpath via `ClassLoader.getResourceAsStream` or equivalent APIs.

Smoke tests should run under deployment-like settings: target Java runtime version, appropriate profile, required environment variables, and an intentional working directory. If local machines have secret files or configs missing in CI, surface that hidden dependency early. Never copy real secrets into repositories or smoke-test logs.

### 10.4. When the Final Deliverable Is an OCI Image or WAR

Packaged-JAR smoke testing verifies the executable JAR on the host, yet does not prove a Docker image works, since containers differ in base JRE, permissions, filesystem, entrypoint, user, and networking. For Docker/OCI, follow the host JAR smoke test by running the **final image** and probing its endpoint inside the container.

For executable WARs or WARs deployed to an external servlet container, layout and launch mechanics differ. Always test **the exact artifact and launch mode** used in production; never blindly apply JAR commands to every WAR.

## 11. Non-HTTP Servers: CLI and Batch Applications

Not every Spring Boot application opens a web port. A CLI app may run a `CommandLineRunner`, print output, and exit. In that case, an artifact startup test should:

1. Launch `java -jar path/to/cli.jar` with appropriate arguments.
2. Wait for the process to terminate within a bounded timeout.
3. Verify exit code `0` (when success is the contract) along with expected stdout/stderr or output files.
4. Destroy the process in `finally` on timeout.
5. Isolate test input data, working directory, and environment.

Do not reuse the HTTP runner in section 5 for CLI apps, because it treats early process exit as an error and polls a nonexistent HTTP endpoint. Conversely, never use "process exited 0" as the criterion for a long-running web server. This lesson uses an HTTP server to practice startup and serving readiness.

## 12. Real-JAR Failure Diagnosis Table

| Symptom | Possible cause | Check first |
| --- | --- | --- |
| `JAR not found` | Wrong path, module, `finalName`, classifier, or packaging didn't run | Inspect task outputs; select the exact file from the current build |
| `no main manifest attribute` | Plain JAR, `repackage`/`bootJar` didn't run, or wrong artifact picked | Inspect manifest, `BOOT-INF`, and plugin executions |
| `ClassNotFoundException` for launcher | Missing Spring Boot loader or altered archive | `jar tf`, `Main-Class`, artifact checksum |
| `ClassNotFoundException` for app main | Wrong `Start-Class`, or class missing from `BOOT-INF/classes` | Compare FQCN, compiled classes, and manifest |
| `NoClassDefFoundError` | Missing runtime dependency or classpath mismatch | Inspect `BOOT-INF/lib` and Maven/Gradle resolved graphs |
| `NoSuchMethodError` | Binary incompatibility across runtime versions | Inspect selected versions and bundled libs in the JAR |
| `UnsupportedClassVersionError` | Runtime Java older than compiled bytecode | Check `java -version` on target host and compiler/toolchain config |
| Web server fails to bind port | Port already in use, wrong interface, or permissions | Child log, port flags, and running processes |
| Timeout with HTTP `-1` | No response received, slow/crashing startup, or unbound endpoint | Child log, process status, networking |
| HTTP `401`/`403` | Endpoint protected by security | Spring Security/Actuator config and access rules |
| HTTP `404` | Wrong route, context path, or artifact | Request URL, route mappings, startup logs |
| HTTP `503` | Health/readiness unfulfilled or app reports unavailable | Health details and required dependencies |
| HTTP `200` with unexpected body | Route changed, another app answered, or wrong artifact | Assertion, instance identity, port, and build path |
| `spring-boot:run` works, yet JAR fails | Classpath differences or broken packaging config | Manifest, `BOOT-INF/lib`, resources, and plugin logs |
| Host JAR PASSES, yet image FAILS | Different JRE, env, file permissions, or entrypoint | Run and probe the final OCI image itself |
| Green smoke test, yet old version deployed | Checksum mismatch or CI picked a different file | Compare SHA-256 and paths across pipeline stages |

These are **initial hypotheses**, not the sole possible cause for a given exception. Prioritize reading the child log and inspecting the actual JAR file executed.

## 13. Pre-Publish Checklist

1. Select the JDK/runtime supported by the real deployment environment; verify Maven/Gradle/Boot compatibility.
2. Run compile, unit tests, and packaging from a clean workspace.
3. With Maven: ensure `spring-boot:repackage` takes effect; with Gradle: use `bootJar`.
4. Identify the exact **artifact file to be released**; never use wildcards across multiple JARs.
5. When in doubt, inspect the manifest, `Start-Class`, `BOOT-INF/classes`, and `BOOT-INF/lib`.
6. Launch the **exact archive** with `java -jar`; never substitute `spring-boot:run`/`bootRun`.
7. Choose a verification endpoint matching your goal; assert both HTTP status and body/health contract.
8. Enforce timeouts, early-exit detection, logging, and cleanup across all branches.
9. Ensure smoke test failure blocks publish/deploy; never swallow exit codes.
10. Verify via checksum or artifact identity that the deployed file is the exact file tested.
11. Add image/production-readiness smoke checks if the final deliverable is a container or separate runtime.
12. Maintain separate unit/integration/e2e tests; smoke tests do not replace those testing layers.

### Self-Check Questions

**Question 1:** Why isn't a green `@SpringBootTest` enough to prove `java -jar` works?

**Answer:** Spring tests normally run on the test classpath and do not verify the manifest, Boot launcher, nested dependencies, or final packaged artifact.

**Question 2:** If a JAR packages successfully yet the runner reports `no main manifest attribute`, what should you check?

**Answer:** Verify you selected the executable archive; check `repackage`/`bootJar` and `META-INF/MANIFEST.MF`.

**Question 3:** A web server runs steadily and does not exit by itself. After the endpoint PASSES, what should the runner do?

**Answer:** Actively stop the child process during cleanup; never wait for the server to exit `0` on its own.

**Question 4:** Is HTTP 200 on port 8080 enough to prove the new JAR is running?

**Answer:** No. An older server could return 200. Use an isolated port, verify the new process and response contract; add instance identity when needed.

**Question 5:** Why still test the Docker image even after host `java -jar` PASSES?

**Answer:** Base JRE, user permissions, environment, entrypoint, and filesystem can differ, causing failures that appear only inside the final image.

## 14. Official Reference Documentation

- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot 3.3 — First Application and Maven package: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot Gradle Plugin — Packaging: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot Actuator — Endpoints, Liveness and Readiness: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Apache Maven Failsafe Plugin — Integration Test Lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/index.html
- Gradle — Testing Java Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Java 17 API — ProcessBuilder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Java 17 API — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html

**Remember:** A green build does not prove the **released archive** can run. Build the executable JAR, select the exact file, launch it via `java -jar` in a separate process, wait with a bounded HTTP probe with cleanup, and publish **only the exact verified artifact**.
