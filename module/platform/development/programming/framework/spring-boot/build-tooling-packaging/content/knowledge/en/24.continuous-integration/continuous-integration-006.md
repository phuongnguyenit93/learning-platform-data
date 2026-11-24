# Testing Startup of a JAR or Image in a Clean Environment

## 1. Objective

A Spring Boot application may run fine via `./gradlew bootRun` on a laptop yet fail when starting the packaged JAR or OCI image on a server. Causes typically stem from the classpath, developer-only configuration, files outside the JAR, working directory, Java runtime, permissions, networking, or container entrypoints.

**Testing in a clean environment** means running the exact release deliverable in an environment isolated from the developer's workspace and build process, then verifying that the application actually starts, becomes ready for requests, returns the right responses, and shuts down cleanly.

This lesson distinguishes three levels:

1. **JAR check:** run the executable Boot JAR with `java -jar` inside a temporary directory with a controlled environment. Never use the Gradle/Maven runtime classpath to hide missing dependencies.
2. **Image check:** run the exact built OCI image without mounting host sources/build outputs or leaking implicit variables from a developer machine.
3. **Release candidate check:** verify the artifact/image digest, Java runtime, health/readiness probes, logs, and external dependencies required by the target environment.

Practical objectives:

- Create a Spring Boot Java 17 application with a smoke test endpoint and Actuator health probes.
- Build an executable JAR using Gradle or Maven.
- Inspect the manifest, JAR entries, and checksum before launching.
- Run the JAR in a temporary working directory with an environment allowlist, readiness timeout, and cleanup.
- Build an image using Spring Boot Buildpacks or a Dockerfile, and run it without host source/cache bind mounts.
- Distinguish process started, liveness, readiness, and application-level responses.
- Add a CI check that runs **the built artifact** in a clean job/environment.
- Diagnose configuration, port, Java, permission, health check, database, and container startup failures.

**Example versions:** Java 17, Spring Boot 3.3.13. Primary shell examples use Linux/macOS and Docker CLI; Windows PowerShell equivalents are shown separately. This is an illustrative baseline, not a claim about the latest versions.

## 2. What Does a "Clean Environment" Mean?

A test only validates the artifact if it does not accidentally rely on things the artifact fails to carry with it.

| Component | Typical Developer Environment | Clean Smoke Test Environment Must Specify |
| --- | --- | --- |
| Classpath | Gradle/Maven IDE classpath, compiled classes | Only the executable JAR and packaged runtime dependencies |
| Working directory | Repository root containing configs/logs/files | Empty temporary directory with only explicitly permitted files |
| Environment variables | `JAVA_TOOL_OPTIONS`, `SPRING_*`, proxies, secrets | Environment allowlist; pass only required variables |
| Java | Laptop JDK/toolchain | JRE/JDK matching deployment version and vendor policy |
| File system | Source, `build/`, `target/`, local certificates | No mounted source/caches; explicit read/write permissions |
| Network | DB/Redis/services already running locally | Never assume external services exist; use isolated test dependencies |
| Container | Docker Compose dev stack | Exact release candidate image with intentional config and mounts |
| Artifact | Might run `bootRun` from classes | Runs the packaged JAR/image with a specific digest |

**Clean does not mean offline or dependency-free.** If production requires PostgreSQL, Redis, or a message broker, a smoke test checking only the JVM and HTTP server does not prove those integrations work. Add a test environment with ephemeral or managed external services, such as Testcontainers or a test namespace.

Nor is a clean environment completely hermetic: kernel, Docker daemon, CPU architecture, DNS, clock, and network remain inputs. Record key details and avoid claiming absolute reproducibility just from running inside a temporary directory.

## 3. Sample Spring Boot Project

Let's build an HTTP application exposing:

- `GET /smoke` returning strictly `ok` to verify requests reach the controller.
- `GET /actuator/health/liveness` to check process liveness and the liveness health indicator.
- `GET /actuator/health/readiness` to check whether the application is ready for traffic.
- Graceful shutdown so containers/CI can send `SIGTERM` and wait for the process to exit.

Structure:

~~~text
smoke-app/
├── settings.gradle                 # choose Groovy DSL
├── build.gradle
│   or settings.gradle.kts          # choose Kotlin DSL
│   or build.gradle.kts
├── pom.xml                         # replaces Gradle if using Maven
└── src/
    ├── main/
    │   ├── java/com/example/smoke/
    │   │   ├── SmokeApplication.java
    │   │   └── SmokeController.java
    │   └── resources/application.properties
    └── test/java/com/example/smoke/
        └── SmokeControllerTest.java
~~~

Do not interpret Gradle Groovy, Kotlin DSL, and Maven as three build scripts for the same module. Pick the build tool actually used in your repository.

### 3.1. Main Class

`src/main/java/com/example/smoke/SmokeApplication.java`:

~~~java
package com.example.smoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SmokeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SmokeApplication.class, args);
    }
}
~~~

### 3.2. Controller

`src/main/java/com/example/smoke/SmokeController.java`:

~~~java
package com.example.smoke;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SmokeController {

    @GetMapping("/smoke")
    public String smoke() {
        return "ok";
    }
}
~~~

The exact HTTP response body of this endpoint is `ok` (no JSON wrapper needed). The endpoint is intentionally simple to separate HTTP server startup issues from complex business-logic failures.

### 3.3. application.properties

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
~~~

- `server.port` sets the internal listening port.
- `server.shutdown=graceful` lets Spring Boot wait for in-flight requests during shutdown per its lifecycle.
- `spring.lifecycle.timeout-per-shutdown-phase` bounds the wait time for each shutdown phase.
- `management.endpoint.health.probes.enabled=true` enables liveness/readiness health groups for local smoke tests.
- Only `health` is exposed in this example, avoiding exposing all Actuator endpoints.

In Spring Boot 3.3, availability probes are automatically enabled when running in Kubernetes; enabling them explicitly here ensures consistent local and container testing. Health endpoints do not automatically verify all business behavior or external dependencies unless corresponding health indicators exist.

### 3.4. JUnit Test

`src/test/java/com/example/smoke/SmokeControllerTest.java`:

~~~java
package com.example.smoke;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SmokeControllerTest {

    @Test
    void returnsSmokeResponse() {
        SmokeController controller = new SmokeController();
        assertEquals("ok", controller.smoke());
    }
}
~~~

This test checks controller logic, yet **does not start the Spring context or HTTP server**. Only the JAR/image smoke test in later sections confirms wiring, embedded server, classpath, runtime config, and live endpoints.

## 4. Building an Executable JAR with Gradle

### 4.1. Groovy DSL

`settings.gradle`:

~~~groovy
rootProject.name = 'smoke-app'
~~~

Complete `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'smoke-app.jar'
}

tasks.named('bootBuildImage') {
    imageName = 'local/smoke-app:1.0.0'
}
~~~

`bootJar` produces an executable Spring Boot archive with the proper dependencies and loader layout. Setting an explicit archive filename ensures test scripts always pick `build/libs/smoke-app.jar`. Never pick a file randomly from a `*.jar` glob because `-plain.jar` might also exist.

### 4.2. Kotlin DSL

If the project uses Kotlin DSL, replace the Groovy pair with:

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "smoke-app"
~~~

`build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("smoke-app.jar")
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("local/smoke-app:1.0.0")
}
~~~

Kotlin DSL changes only the build script syntax; the Java application source stays identical. Use only one DSL per module.

### 4.3. Building and Testing

With the Gradle Wrapper:

~~~bash
./gradlew --version
./gradlew clean test bootJar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
~~~

File to verify:

~~~text
build/libs/smoke-app.jar
~~~

If `bootJar` has not generated the file, check task output and build logs before running the smoke script. Never substitute `bootRun`: `bootRun` executes from Gradle-managed classes and runtime classpath, which does not prove the executable JAR was packaged properly.

## 5. Building an Executable JAR with Maven

This is the Maven alternative to Gradle using the same Java source and resources from Section 3.

`pom.xml`:

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
    <artifactId>smoke-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <finalName>smoke-app</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Boot parent manages dependency/plugin versions and `repackage` execution. `<finalName>smoke-app</finalName>` stabilizes the artifact name at `target/smoke-app.jar`; Maven coordinates remain `smoke-app:1.0.0`.

Build:

~~~bash
./mvnw -B -ntp clean verify
~~~

If there is no Maven Wrapper yet a policy-approved Maven is installed:

~~~bash
mvn -B -ntp clean verify
~~~

Artifact:

~~~text
target/smoke-app.jar
~~~

`verify` runs the preceding lifecycle phases, including test and package per project configuration. Ensure Maven `repackage` ran so the JAR includes the Spring Boot loader and dependencies. Never take an un-repackaged plain Maven JAR and expect `java -jar` to run it.

## 6. Inspecting the Artifact Before Starting

A smoke test can fail due to picking the wrong file or a corrupted transfer. Verify the exact artifact first:

### 6.1. Checking Size and SHA-256

Linux/macOS:

~~~bash
ls -lh build/libs/smoke-app.jar
sha256sum build/libs/smoke-app.jar
~~~

Maven adjusts the path:

~~~bash
ls -lh target/smoke-app.jar
sha256sum target/smoke-app.jar
~~~

Windows PowerShell:

~~~powershell
Get-Item .\build\libs\smoke-app.jar | Select-Object Name, Length
Get-FileHash .\build\libs\smoke-app.jar -Algorithm SHA256
~~~

Store the digest in CI artifact metadata to compare before and after upload/download. A self-computed checksum does not prove publisher identity; it detects tampering or corruption when compared against a digest obtained over a trusted channel.

### 6.2. Inspecting JAR Entries

~~~bash
jar tf build/libs/smoke-app.jar
~~~

A typical executable Spring Boot JAR includes:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/smoke/SmokeApplication.class
BOOT-INF/classes/com/example/smoke/SmokeController.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/...
~~~

The loader path can vary across Spring Boot versions; `BOOT-INF/classes` and `BOOT-INF/lib` are key indicators of an executable Boot archive. Do not merely check for a `.jar` extension.

### 6.3. Inspecting the Manifest

If `unzip` is available:

~~~bash
unzip -p build/libs/smoke-app.jar META-INF/MANIFEST.MF
~~~

An executable JAR's manifest typically sets `Main-Class` to the Spring Boot launcher and `Start-Class` to the main application class. Launcher class names vary across Spring Boot versions and packaging modes; read the actual manifest instead of hardcoding one value across all Boot releases.

If `unzip` is unavailable, extract into a temporary directory using the JDK `jar` tool and inspect the manifest. Never extract an untrusted archive into the project root.

### 6.4. Checking the Java Runtime

~~~bash
java -version
~~~

The sample application is compiled with `--release 17`, and Spring Boot 3.3.13 requires Java 17 or newer. Smoke tests should run on the exact JRE/vendor/version approved by the deployment environment. If running on a newer Java release, test compatibility explicitly rather than assuming every patch/vendor behaves identically.

## 7. Running the JAR in a Clean Environment

### 7.1. Why Use java -jar?

The command:

~~~bash
java -jar build/libs/smoke-app.jar
~~~

runs the executable archive through Spring Boot's manifest and loader. This resembles production launches much more closely than `bootRun` or `spring-boot:run`, which can use source classes and build-tool classpaths.

For stronger isolation, launch from an empty temporary directory using an absolute path to the JAR and providing only required environment variables.

### 7.2. Smoke Test Script for Linux/macOS

Create `scripts/smoke-jar.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_JAR="build/libs/smoke-app.jar"
PORT="18080"
BASE_URL="http://127.0.0.1:$PORT"

if [[ ! -f "$APP_JAR" ]]; then
  echo "JAR not found: $APP_JAR" >&2
  exit 1
fi

APP_JAR="$(cd "$(dirname "$APP_JAR")" && pwd)/$(basename "$APP_JAR")"
WORK_DIR="$(mktemp -d)"
mkdir -p "$WORK_DIR/home" "$WORK_DIR/tmp"
LOG_FILE="$WORK_DIR/application.log"
APP_PID=""

cleanup() {
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    kill -TERM "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

(
  cd "$WORK_DIR"
  env -i \
    PATH="$PATH" \
    HOME="$WORK_DIR/home" \
    TMPDIR="$WORK_DIR/tmp" \
    LANG="C.UTF-8" \
    TZ="UTC" \
    java -jar "$APP_JAR" \
      --server.address=127.0.0.1 \
      --server.port="$PORT"
) >"$LOG_FILE" 2>&1 &
APP_PID="$!"

READY=0
ATTEMPT=0
while [[ "$ATTEMPT" -lt 60 ]]; do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "Application exited before readiness." >&2
    cat "$LOG_FILE" >&2
    exit 1
  fi

  if curl --fail --silent "$BASE_URL/actuator/health/readiness" >/dev/null; then
    READY=1
    break
  fi

  ATTEMPT=$((ATTEMPT + 1))
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  echo "Application did not become ready within 60 seconds." >&2
  cat "$LOG_FILE" >&2
  exit 1
fi

BODY="$(curl --fail --silent "$BASE_URL/smoke")"
if [[ "$BODY" != "ok" ]]; then
  echo "Unexpected /smoke response: $BODY" >&2
  cat "$LOG_FILE" >&2
  exit 1
fi

curl --fail --silent "$BASE_URL/actuator/health/liveness" >/dev/null
echo "JAR_SMOKE_PASS"
~~~

Run after building:

~~~bash
chmod +x scripts/smoke-jar.sh
./scripts/smoke-jar.sh
~~~

Stdout when all checks pass:

~~~text
JAR_SMOKE_PASS
~~~

The script creates isolated `HOME`/`TMPDIR` folders, strips most extraneous environment variables via `env -i`, changes working directory to the temp folder, launches the exact JAR, and waits up to 60 seconds for readiness. If the app exits early or times out, it prints the log for diagnostics. The `trap` stops the process and removes the temporary directory.

**Adjust before using with a real app:** supply required environment variables/secrets via an allowlist; change the port if occupied; tune the readiness timeout to match actual startup budgets. Never pass the developer's full `env` into the script.

### 7.3. Meaning of the Timeout

60 seconds in the example is a smoke test timeout, not a promise that every application must start within 60 seconds. Large apps, JIT warmup, migrations, or dependencies may require different budgets. Set timeouts from SLAs and startup characteristics—long enough for CI stability, short enough to fail fast when a process hangs.

If the process exits before readiness, inspect startup logs first. If the process stays alive without reaching readiness, inspect health indicators, configuration, and external dependencies. Never raise timeouts endlessly to mask a readiness failure.

## 8. PowerShell: Testing the JAR on Windows

You can test the JAR using PowerShell/.NET Process APIs. The snippet below launches Java with a temporary working directory and redirects stdout/stderr to a log file; for real projects, add an environment allowlist per policy.

~~~powershell
$ErrorActionPreference = "Stop"

$jar = (Resolve-Path ".\build\libs\smoke-app.jar").Path
$port = 18080
$baseUrl = "http://127.0.0.1:$port"
$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString("N"))
$logFile = Join-Path $workDir "application.log"
New-Item -ItemType Directory -Path $workDir | Out-Null

$process = $null

try {
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = (Get-Command java).Source
    $psi.WorkingDirectory = $workDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.ArgumentList.Add("-jar")
    $psi.ArgumentList.Add($jar)
    $psi.ArgumentList.Add("--server.address=127.0.0.1")
    $psi.ArgumentList.Add("--server.port=$port")

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    $logWriter = [System.IO.StreamWriter]::new($logFile, $false)

    $process.add_OutputDataReceived({
        param($sender, $eventArgs)
        if ($eventArgs.Data) { $logWriter.WriteLine($eventArgs.Data) }
    })
    $process.add_ErrorDataReceived({
        param($sender, $eventArgs)
        if ($eventArgs.Data) { $logWriter.WriteLine($eventArgs.Data) }
    })

    [void]$process.Start()
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($process.HasExited) {
            throw "Application exited before readiness. See $logFile"
        }

        try {
            $response = Invoke-WebRequest -Uri "$baseUrl/actuator/health/readiness" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $ready) {
        throw "Application did not become ready within 60 seconds. See $logFile"
    }

    $body = (Invoke-WebRequest -Uri "$baseUrl/smoke").Content
    if ($body -ne "ok") {
        throw "Unexpected /smoke response: $body"
    }

    Write-Output "JAR_SMOKE_PASS"
}
finally {
    if ($process -and -not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit()
    }
    if ($process) { $process.Dispose() }
    if (Test-Path $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force }
}
~~~

Run:

~~~powershell
.\scripts\smoke-jar.ps1
~~~

Output when passing:

~~~text
JAR_SMOKE_PASS
~~~

The example uses `ProcessStartInfo.ArgumentList` available in modern PowerShell/.NET. If a runner uses older Windows PowerShell/.NET lacking this property, build properly quoted process arguments or switch to PowerShell 7. Never concatenate untrusted input into argument strings.

The script inherits the parent process environment by default. For stricter isolation, clear extraneous variables from `psi.Environment` and populate an allowlist (e.g., `PATH`, `TEMP`, `JAVA_HOME`, and required app variables); do not blindly wipe mandatory Windows runtime variables.

## 9. Liveness, Readiness, and Startup: Three Different Questions

Spring Boot Actuator provides health groups:

- **Liveness:** is the application process still in a state where it can continue running? If liveness fails, the platform may restart the container.
- **Readiness:** is the application ready to receive requests? If readiness fails, the platform should stop routing traffic to that instance.
- **Startup probe:** gives the platform/orchestrator a startup grace window; in Kubernetes this is a Pod-level probe configuration, not a mandatory health group in every Spring Boot app.

### 9.1. Why Not Put Every External Dependency into Liveness?

If a database briefly loses connectivity and liveness directly depends on the DB, every app instance could restart repeatedly, making recovery harder. Spring Boot recommends separating application internal state from external dependency state; readiness is typically a better fit to reflect whether the app can serve requests.

By default, liveness/readiness groups do not automatically check every external service. If business readiness requires a database or broker, explicitly include its indicator in the readiness group and test the behavior. Avoid heavy checks or cross-service dependencies in liveness where restart loops could occur.

### 9.2. Endpoints in the Example

With the properties from Section 3:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

When UP, HTTP status is typically 200 and JSON looks like:

~~~json
{
  "status": "UP"
}
~~~

Responses may include component details depending on security and configuration. Smoke tests should check HTTP success rather than hardcoding JSON formatting or key ordering. If security policy protects endpoints, tests must use granted credentials or internal probe routes.

### 9.3. HTTP 200 Health Does Not Prove Business Logic Works

That is why the script also calls:

~~~bash
curl --fail --silent http://127.0.0.1:18080/smoke
~~~

and compares the exact body to `ok`. In real apps, pick a smoke test endpoint that has no side effects, needs no personal data, and exercises a critical request path. Never invoke endpoints that create transactions or delete data during startup smoke tests.

### 9.4. Health Endpoints May Be Protected

If Spring Security is enabled, Actuator endpoints may return 401/403 even when the app started cleanly. That can be intended behavior. Supply test credentials/tokens via a secret manager or expose probe endpoints on a management interface/internal network per policy; never expose health details publicly just to make CI calls easier.

## 10. Testing an Image in a Clean Environment

There are two common ways to build an image:

1. Spring Boot Buildpacks: Gradle `bootBuildImage` or Maven `spring-boot:build-image`.
2. Multi-stage Dockerfile: build the JAR in a builder stage and copy it into a runtime image.

Runtime smoke testing is nearly identical: run **the built image reference** without mounting host sources, build folders, or Maven/Gradle caches.

### 10.1. Building an Image with Spring Boot Buildpacks

The Gradle project in Section 4 configures:

~~~groovy
tasks.named('bootBuildImage') {
    imageName = 'local/smoke-app:1.0.0'
}
~~~

Build:

~~~bash
./gradlew bootBuildImage
~~~

Maven POM adds image configuration:

~~~xml
<configuration>
    <image>
        <name>local/smoke-app:1.0.0</name>
    </image>
</configuration>
~~~

Then:

~~~bash
mvn spring-boot:build-image
~~~

Buildpacks constructs the image using builder and run images. A successful build alone does not verify endpoints work; you still must run the container.

### 10.2. Multi-Stage Dockerfile (Alternative Option)

If the repository uses a Dockerfile, for example:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

COPY gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle build.gradle ./
RUN chmod +x gradlew

COPY src/ src/
RUN ./gradlew --no-daemon clean test bootJar

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/build/libs/smoke-app.jar /app/smoke-app.jar

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/smoke-app.jar"]
~~~

Build the image:

~~~bash
docker build --pull -t local/smoke-app:1.0.0 .
~~~

This Dockerfile uses Gradle Groovy DSL and requires wrapper files and sources to exist in the build context without being excluded by `.dockerignore`. If using Kotlin DSL, substitute the corresponding Gradle files. If using Maven, the builder stage must copy the POM, Wrapper, and repackaged output from the right path.

This is **an alternative image creation method**; there is no need to add a Dockerfile if the pipeline already uses Buildpacks. Either way, the smoke test step must run the actual final image.

### 10.3. Inspecting Image Identity

~~~bash
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' local/smoke-app:1.0.0
~~~

Record the image ID, OS, and architecture so you know exactly which image was tested. In CI/releases, prefer the immutable registry digest after pushing. Never rely solely on mutable tags as proof that smoke testing and deployment ran identical bytes.

## 11. Image Smoke Testing with Docker

### 11.1. Running Manually

~~~bash
docker run --rm -p 18081:8080 local/smoke-app:1.0.0
~~~

Keep the container running in the foreground. In another terminal:

~~~bash
curl --fail --silent http://127.0.0.1:18081/actuator/health/readiness
curl --fail --silent http://127.0.0.1:18081/smoke
~~~

Application endpoint response body:

~~~text
ok
~~~

Stop with Ctrl+C. `EXPOSE 8080` in a Dockerfile is metadata only; `-p 18081:8080` is what maps host port 18081 to container port 8080.

### 11.2. Automated Image Smoke Script

Create `scripts/smoke-image.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE_REF="local/smoke-app:1.0.0"
CONTAINER_NAME="smoke-app-smoke-$$"
HOST_PORT="18081"
BASE_URL="http://127.0.0.1:$HOST_PORT"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:$HOST_PORT:8080" \
  "$IMAGE_REF"

READY=0
ATTEMPT=0

while [[ "$ATTEMPT" -lt 60 ]]; do
  RUNNING="$(docker inspect --format '{{.State.Running}}' \
    "$CONTAINER_NAME" 2>/dev/null || echo false)"

  if [[ "$RUNNING" != "true" ]]; then
    echo "Container exited before readiness." >&2
    docker logs "$CONTAINER_NAME" >&2 || true
    exit 1
  fi

  if curl --fail --silent \
    "$BASE_URL/actuator/health/readiness" >/dev/null; then
    READY=1
    break
  fi

  ATTEMPT=$((ATTEMPT + 1))
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  echo "Container did not become ready within 60 seconds." >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi

BODY="$(curl --fail --silent "$BASE_URL/smoke")"
if [[ "$BODY" != "ok" ]]; then
  echo "Unexpected /smoke response: $BODY" >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi

curl --fail --silent \
  "$BASE_URL/actuator/health/liveness" >/dev/null

docker stop --time 20 "$CONTAINER_NAME" >/dev/null
echo "IMAGE_SMOKE_PASS"
~~~

Run:

~~~bash
chmod +x scripts/smoke-image.sh
./scripts/smoke-image.sh
~~~

Final stdout when passing:

~~~text
IMAGE_SMOKE_PASS
~~~

The script does not mount the project, `build/`, `target/`, `.gradle`, `.m2`, or source into the container. It runs the exact image, waits for readiness, checks the application body, and stops the container. The `trap` cleans up the container on both success and failure.

If the Docker daemon uses a different context, the image is not available locally, or port 18081 is occupied, adjust the environment or test port per CI policy. Never switch to a different image tag just to make the script pass while forgetting to record the image ID/digest.

### 11.3. Testing a Stricter Runtime Environment

For a sample application that does not write to the root filesystem, you can try additional restrictions:

~~~bash
docker run --detach \
  --name smoke-app-readonly \
  --publish 127.0.0.1:18081:8080 \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  local/smoke-app:1.0.0
~~~

This is an **optional hardening test**. Some applications need writable directories, certificates, native temp files, or Linux capabilities; in those cases, configure minimal mounts/permissions and test against the runtime contract. Do not apply these flags without understanding application requirements. If a container fails only with `--read-only`, investigate filesystem writes before blaming the JAR.

### 11.4. Do Not Use --network none Mechanically

If an app needs no external services, you can test zero outbound access with appropriate network isolation. However, host port publishing and `--network none` do not behave like bridge networking; connectivity tests must be redesigned accordingly. For apps needing DB/Redis, strict network isolation will rightly fail readiness. Use an isolated test network with ephemeral dependencies rather than skipping dependency checks.

## 12. Avoid Inheriting Unintended Developer Config

### 12.1. Variables That Can Cause False Passes

Environment variables affecting Spring Boot:

- `SPRING_PROFILES_ACTIVE`: selects profiles and config files.
- `SPRING_DATASOURCE_URL`/username/password: connects to a database.
- `SPRING_CONFIG_LOCATION`/`SPRING_CONFIG_ADDITIONAL_LOCATION`: loads external configs outside the JAR.
- `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`: injects JVM flags.
- `SERVER_PORT`: overrides default port.
- `HTTP_PROXY`/`HTTPS_PROXY`: affects networking.
- Secrets, tokens, and cloud credentials: let the app connect to services unavailable to a clean image.

If a laptop has a `.env` file or IDE run configuration, the app can pass even when the release image lacks mandatory config. The JAR script uses `env -i` to wipe most inherited variables, then supplies only explicitly declared variables.

### 12.2. Externalized Configuration Is a Contract

If production requires:

~~~text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
~~~

provide corresponding values from a test secret manager or test database in the smoke/integration environment. Never hardcode credentials into the JAR, Dockerfile, build args, or test scripts. A test without a database only confirms the app can start **without a database**; it cannot prove production DB configuration.

### 12.3. Checking Working Directory

Spring Boot can load external configuration from relative/current-directory locations. Running from an empty temporary directory therefore catches accidental reliance on `./application.yml` or `./config/` sitting in the repository root.

If the application intentionally uses an external config mount, test both cases:

1. Without the mount: the application fails with a clear message if the config is mandatory.
2. With a compliant mount: the application starts and reaches readiness.

Never copy every local file into the container to patch over missing configs; identify the exact config files that must be packaged or mounted.

## 13. Testing External Dependencies in a Clean Environment

A service might start its HTTP server yet remain unready for business because a database or broker is unreachable. Define the startup contract:

| Test Type | External Dependencies | Goal |
| --- | --- | --- |
| Basic JAR smoke | None or mocked | Verify executable, runtime, HTTP wiring |
| Basic image smoke | None or mocked | Verify final image, entrypoint, ports, permissions |
| Integration smoke | Ephemeral DB/Redis/broker | Verify connectivity, config, schema, auth |
| Deployment smoke | Test/staging services | Verify networking, secrets, service discovery, and platform |
| Production readiness | Real dependencies per policy | Verify operations without side effects |

### 13.1. Testcontainers for Databases

If the application needs PostgreSQL, use Testcontainers to spin up an ephemeral DB in integration tests instead of relying on a developer's local PostgreSQL install. Testcontainers manages test container lifecycles, port mappings, and connection details; it requires an available Docker daemon.

Example test dependencies (versions must be pinned and compatible with your project):

~~~groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
~~~

With Maven, add Testcontainers dependencies in `test` scope and manage versions via an approved BOM or pinned versions. Avoid dynamic dependency versions.

Integration tests should create schemas/test data, verify app queries/transactions, and clean up. A standalone JAR smoke test does not create databases on its own. When testing **the final image**, supply a database container over a Docker network, test compose stack, or dedicated integration environment without mounting local DB state.

### 13.2. Readiness with External Dependencies

If a DB is mandatory to serve requests, you can add a custom health indicator to the readiness group. Consider timeouts, retries, failure behavior, and avoid heavy queries on every probe. Liveness should reflect the app process itself rather than depending arbitrarily on every external service, avoiding restart storms.

### 13.3. Migrations

If the app runs Flyway or Liquibase migrations on startup, a clean database smoke test should spin up an empty DB and verify migrations succeed. If targeting an existing schema, test the upgrade path separately too. Never test migrations against production data via startup smoke scripts.

## 14. CI: Build Once, Test the Exact Built Artifact

A sound pipeline separates building/testing the artifact from smoke-testing it in a clean environment. The smoke job receives the artifact uploaded by the build job; it **does not recompile** and test a different binary.

GitHub Actions Gradle example:

~~~yaml
name: Spring Boot Artifact Smoke

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Build and unit test
        run: ./gradlew --no-daemon clean test bootJar

      - name: Upload executable JAR
        uses: actions/upload-artifact@v4
        with:
          name: smoke-app-jar
          path: build/libs/smoke-app.jar
          if-no-files-found: error

  smoke-jar:
    needs: build
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: actions/download-artifact@v4
        with:
          name: smoke-app-jar
          path: build/libs

      - name: Run executable JAR smoke test
        run: ./scripts/smoke-jar.sh
~~~

This workflow illustrates artifact handoff between two jobs/runners. In production:

- Pin actions by reviewed full commit SHA rather than just `@v4`.
- Verify full JDK version/vendor if required by policy, and record OS/architecture.
- Compute SHA-256 in the build job, pass the checksum alongside the artifact, and verify it in the smoke job.
- Never grant signing/publishing secrets to untrusted pull-request jobs.
- For Maven, change the build command to `./mvnw -B -ntp clean verify`, upload `target/smoke-app.jar`, and download to the exact path expected by the smoke script.
- When running from fork PRs, restrict tokens/permissions and avoid executing untrusted artifacts with release credentials.

### 14.1. Image CI Smoke Test

When a pipeline builds images via Buildpacks or Dockerfile, add a job after the image is built:

1. Tag it linked to the commit/build ID.
2. Run `docker image inspect` to record image ID and architecture.
3. Run `scripts/smoke-image.sh` against the exact image reference.
4. If pushing to a registry before smoke testing, resolve the digest and smoke-test the exact digest.
5. Only publish/deploy the digest after smoke tests and policy gates pass.

For multi-architecture image manifest lists, verify which platform the runner pulls. An amd64 test does not prove an arm64 image runs; run a matrix across each supported architecture or maintain platform-specific test evidence.

### 14.2. Artifact Promotion

Build once, promote the exact artifact/image digest across dev → staging → production. Never rebuild per environment when the goal is deploying identical tested bytes. Vary configuration and secrets per environment via runtime config, never by rebuilding images to bake in credentials.

## 15. Startup, Readiness, and Graceful Shutdown

### 15.1. Process Started Does Not Mean Ready

Stages:

- JVM process created.
- Spring `ApplicationContext` refreshed.
- Embedded web server listening.
- Readiness health group returning `UP`.
- Business endpoints returning expected responses.
- External dependencies and migrations ready per contract.

Do not just `grep` logs for `Started ...` and assume everything works. Startup logs are helpful signals; HTTP readiness and business probes confirm the actual request path.

### 15.2. Startup Timeouts and Retries

Use bounded retries and explicit wait times. When failures occur:

- Check the process exit code and logs.
- Check for port conflicts.
- Check Java version and classpath.
- Check active config profiles and environment variables.
- Check external service DNS, ports, authentication, and schemas.
- Check container exit state, `OOMKilled`, and restart counts.

Never raise a 60-second timeout to tens of minutes to hide deadlocks, failing migrations, or dependency outages.

### 15.3. Graceful Shutdown

Spring Boot graceful shutdown allows the web server to finish in-flight requests before the process exits. Docker sends `SIGTERM` on `docker stop`, followed by `SIGKILL` after the grace period. `docker stop --time 20` in the example gives the container 20 seconds.

If a Dockerfile uses a shell-form entrypoint, signals may go to the shell instead of the Java process; use exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/smoke-app.jar"]
~~~

The Buildpacks launcher also manages process startup; verify the actual launch process and shutdown behavior of your image. Never assume every custom entrypoint forwards signals identically.

## 16. Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `no main manifest attribute` | Plain JAR or missing repackage | Use Gradle `bootJar`/Maven Boot `repackage`; inspect manifest |
| `ClassNotFoundException`/`NoClassDefFoundError` | Missing dependency or mispackaged JAR | Inspect `BOOT-INF/lib` and runtime dependency scopes |
| `UnsupportedClassVersionError` | Java runtime older than bytecode | Check `java -version`, `javap -verbose`, toolchains |
| App starts in `bootRun` yet JAR fails | Workspace-dependent classpath, config, or file | Run the exact executable JAR from a temp directory |
| Port already in use | Host/container port held by another process | Pick another host port; inspect port mappings |
| Container running yet `curl` fails | App not ready, bound wrong interface/port, or bad mapping | Check logs, readiness endpoint, `docker port` |
| Health endpoint 404 | Missing Actuator or health probes not enabled/exposed | Check dependencies and `management` properties |
| Health endpoint 401/403 | Security policy protects endpoints | Use internal/test credentials or permitted probe routes |
| Readiness 503 while liveness 200 | Process alive yet not ready for traffic | Inspect readiness components, configs, and dependencies |
| JAR passes, image fails | Runtime image differs in JDK/OS, permissions, entrypoint | Inspect image logs, user, env, and architecture |
| Image passes on laptop, fails in CI | Host ports, Docker daemon, architecture, or env differ | Record image ID and runner details; run exact digest |
| App needs local file absent from JAR | External file neither packaged nor mounted | Define config/resource contract and test mount |
| App fails when `HOME` differs | Writes to user home or relies on local cache | Use an explicit writable directory or mount |
| Container exit code 137 | Likely OOM kill or `SIGKILL` | Inspect container state, memory limits, and logs |
| Container unexpectedly runs as root | Base image/Dockerfile/user config | Inspect `docker inspect Config.User` and policy |
| Smoke script hangs | Infinite retry or missing process liveness check | Enforce timeout and check PID/container state |
| Test passes despite broken app logic | Only called health endpoint | Add assertions on a business smoke endpoint |
| Database readiness fails | Missing DB or wrong credentials/schema | Provide ephemeral DB and integration tests |
| JAR checksum changes across jobs | Wrong file or altered transfer/packaging | Verify digests and transfer the exact built artifact |
| Tested image tag yet deployed different digest | Mutable tag overwritten | Verify and deploy by immutable digest |
| PowerShell process fails to stop | Child processes or event/stream handling | Manage `Process`, timeouts, and cleanup properly |
| Temporary files left behind | Trap/finally skipped when runner killed | Use CI cleanup jobs, workspace isolation, and timeouts |

### 16.1. Diagnostic Workflow

1. Identify the exact JAR path or image digest executed.
2. Check checksum, size, and JAR manifest.
3. Check Java runtime, OS, and architecture.
4. Run manually with `java -jar` or `docker run` while watching logs.
5. Check process exit codes, port mappings, and readiness.
6. Check external configurations and dependencies.
7. Compare the clean environment against the developer environment, introducing only explicitly allowed inputs one at a time.
8. Re-run the exact same artifact after fixes; record the digest and test evidence.

Never modify application code when the real fault is testing the wrong plain JAR, misconfigured port mapping, or a missing secret in the smoke environment.

## 17. Practice Exercises with Answers

### Exercise 1 — Why Not Use bootRun?

The application passes `./gradlew bootRun` yet fails when running `java -jar build/libs/app.jar`. What is the key difference?

**Answer:** `bootRun` uses the Gradle runtime classpath and source/build outputs; `java -jar` uses the actual executable archive, manifest, and loader. JAR tests catch packaging, resource, and dependency scope errors.

### Exercise 2 — Process Started, Readiness 503

Liveness returns 200 and readiness returns 503. Can you conclude the app crashed?

**Answer:** No. The process may be alive yet unready for traffic—for example, waiting on a startup dependency or health indicator. Inspect readiness components and logs.

### Exercise 3 — Health 200, Business Endpoint Fails

`/actuator/health/readiness` returns 200 while `/smoke` returns 500. What must the smoke test conclude?

**Answer:** Fail. Health groups reflect configured health indicators; the business endpoint test validates the actual request path.

### Exercise 4 — JAR Runs Only in Project Root

What is the common cause?

**Answer:** The application depends on relative external config files or paths residing in the repository. Run from a temp directory and explicitly define whether config files are packaged or mounted.

### Exercise 5 — Container Runs on Laptop, Fails in CI

Which factors should you compare?

**Answer:** Image digest/architecture, Docker daemon, host ports, runner permissions, external networking/DNS, environment variables, secrets, and memory limits.

### Exercise 6 — Plain JAR

The build directory has `smoke-app-1.0.0.jar` and `smoke-app-1.0.0-plain.jar`. Which file should you smoke-test?

**Answer:** The executable Boot JAR built by `bootJar`/Maven `repackage`, usually the file without the `plain` classifier. Configure a fixed output path to avoid picking the wrong file.

### Exercise 7 — Without Actuator

If a project prefers not to include Actuator, how can it smoke-test?

**Answer:** Use a dedicated, safe business or readiness endpoint. Call only endpoints without side effects and verify both status and body. Actuator probes are helpful, not mandatory for every project.

### Exercise 8 — Database Required at Startup

The JAR fails readiness without PostgreSQL. Is the smoke test wrong?

**Answer:** It depends on the contract. If production requires a DB, the clean environment must supply an ephemeral/test DB and credentials; tests without a DB only verify a DB-less startup mode.

### Exercise 9 — Read-Only Container Fails

The sample app runs in a normal container yet fails with `--read-only`. What do you investigate?

**Answer:** Check logs and writable paths, temp directories, log files, and upload/cache paths. Mount `tmpfs`/volumes at the exact paths with minimal permissions, or fix the app so it stops writing unnecessarily to the root filesystem.

### Exercise 10 — Build Once, Smoke Elsewhere

A CI job builds the JAR and uploads an artifact; another job rebuilds the JAR and smoke-tests it. Does this meet the goal?

**Answer:** No. The smoke job must download and test **the exact artifact** from the build job, verifying its checksum/digest; rebuilding risks testing different bytes.

## 18. Pre-Release Checklist

- [ ] Use Gradle `bootJar` or Maven `repackage` to produce the exact executable Boot JAR.
- [ ] Select artifact files by fixed path/name; never use wildcards that might grab a plain JAR.
- [ ] Verify size, SHA-256, manifest, and expected JAR entries.
- [ ] Run `java -jar` inside a temporary working directory.
- [ ] Isolate environment variables and inject only required configs and secrets.
- [ ] Match JRE/JDK and OS/architecture to the deployment target.
- [ ] Enforce a readiness timeout, monitor process exit, and capture logs on failure.
- [ ] Check health/readiness/liveness and at least one business smoke endpoint.
- [ ] Run container images without mounting host sources, build outputs, or local caches.
- [ ] Verify the image ID/digest and run the exact image intended for deployment.
- [ ] Verify ports, entrypoint, user, permissions, temp directories, and graceful shutdown.
- [ ] If a DB/broker is required, provide ephemeral/managed test services and integration checks.
- [ ] CI smoke jobs receive the exact built artifact, verify its checksum, and never rebuild.
- [ ] Image smoke jobs test the exact digest, not merely a mutable tag.
- [ ] Clean up processes, containers, and temp files after both pass and fail paths.
- [ ] Retain auditable logs, build IDs, artifact digests, image digests, and test outcomes.
- [ ] Keep secrets out of JARs, images, and logs; never expose Actuator details publicly just for testing convenience.

**Conclusion:** `bootRun` or Maven run goals only show an app works inside a build environment. Release readiness requires running **the real executable JAR** via `java -jar` in a clean environment and running **the real final image** without host workspaces or caches. Combine process checks, readiness, business endpoints, external dependency tests, checksum/digest verification, and cleanup to know with certainty whether your deliverable can start and serve requests in its target environment.

## 19. Official Documentation

- Spring Boot 3.3 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Maven Plugin Repackage: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Actuator Liveness and Readiness Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Docker Docs — Run a container: https://docs.docker.com/engine/containers/run/
- Docker Docs — Container lifecycle and logs: https://docs.docker.com/engine/containers/
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Testcontainers for Java — Getting Started: https://java.testcontainers.org/
- GitHub Actions — Store and share data with workflow artifacts: https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts

Timeouts, ports, image tags, and runner labels in the examples are lab values. In production CI/release pipelines, pin tool and action versions per policy, base timeouts on startup budgets, verify exact image digests, and supply only required external configurations.