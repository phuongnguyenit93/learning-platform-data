# Verifying JAR or Image Startup in a Clean Environment

## 1. Goal

A Spring Boot application may run fine via `./gradlew bootRun` on a laptop yet fail when running the packaged JAR or OCI image on a server. Causes usually stem from classpath differences, configs present only on the developer's machine, files outside the JAR, working directory, Java runtime, permissions, network, or container entrypoint.

**Verifying in a clean environment** means running the exact release deliverable in an environment isolated from the developer's workspace/build process, and confirming that the application actually starts, becomes ready to serve requests, returns the right response, and shuts down cleanly.

This lesson distinguishes three levels:

1. **JAR check:** run the executable Boot JAR via `java -jar`, in a temporary directory with a controlled environment. Do not use Gradle/Maven runtime classpaths to mask missing dependencies.
2. **Image check:** run the exact OCI image built, without mounting host sources/build outputs and without passing implicit developer environment variables.
3. **Release candidate check:** confirm the artifact/image digest, Java runtime, health/readiness, logs, and external dependencies required by the target environment.

Hands-on objectives:

- Create a Java 17 Spring Boot application with a smoke test endpoint and Actuator health probes.
- Build an executable JAR with Gradle or Maven.
- Inspect manifest, JAR entries, and checksum before running.
- Run the JAR in a temporary working directory with an environment allowlist, readiness timeout, and cleanup.
- Build an image using Spring Boot Buildpacks or a Dockerfile, and run the image without binding host source/caches.
- Distinguish process started, liveness, readiness, and application-level responses.
- Add CI verification to test the **built artifact** in a clean job/environment.
- Diagnose configuration, port, Java, permission, health check, database, and container startup errors.

**Example versions:** Java 17, Spring Boot 3.3.13. Primary shell commands use Linux/macOS and Docker CLI; Windows PowerShell is covered separately. This is an illustrative milestone, not a claim of the latest release.

## 2. What Does “Clean Environment” Mean?

A test only truly validates an artifact when it does not accidentally rely on things the artifact does not carry.

| Component | Typical Developer Environment | What a Clean Smoke Test Must Specify |
| --- | --- | --- |
| Classpath | Gradle/Maven IDE classpath, compiled classes | Only the executable JAR and packaged runtime dependencies |
| Working directory | Repository root containing config/logs/files | Empty temporary directory, providing only allowed files |
| Environment variables | `JAVA_TOOL_OPTIONS`, `SPRING_*`, proxy, secrets | Environment allowlist; pass only necessary variables |
| Java | JDK/toolchain on laptop | JRE/JDK matching version and vendor policy |
| File system | Source, `build/`, `target/`, local certificates | No host source/cache mounts; explicit read/write permissions |
| Network | DB/Redis/services running locally | Do not assume external services exist; use dedicated test dependencies |
| Container | Docker Compose dev stack | Exact release candidate image, intentional config and mounts |
| Artifact | May run `bootRun` from classes | Run the packaged JAR/image with a known digest |

**Clean does not mean offline or dependency-free.** If production requires PostgreSQL, Redis, or a message broker, a smoke test verifying only the JVM and HTTP server does not prove those integrations work. Add a test environment with ephemeral/managed external services, such as Testcontainers or a test namespace.

A clean environment is also not completely hermetic: the kernel, Docker daemon, CPU architecture, DNS, clock, and network remain inputs. Document significant factors and do not claim absolute reproducibility merely for running in a temporary directory.

## 3. Sample Spring Boot Project

We build an HTTP application with:

- `GET /smoke` returning exact `ok` to confirm requests reach the controller.
- `GET /actuator/health/liveness` to check process liveness and the liveness health indicator.
- `GET /actuator/health/readiness` to check whether the application is ready to accept traffic.
- Graceful shutdown so containers/CI can send SIGTERM and wait for the process to exit.

Structure:

~~~text
smoke-app/
├── settings.gradle                 # choose Groovy DSL
├── build.gradle
│   or settings.gradle.kts          # choose Kotlin DSL
│   or build.gradle.kts
├── pom.xml                         # instead of Gradle if using Maven
└── src/
    ├── main/
    │   ├── java/com/example/smoke/
    │   │   ├── SmokeApplication.java
    │   │   └── SmokeController.java
    │   └── resources/application.properties
    └── test/java/com/example/smoke/
        └── SmokeControllerTest.java
~~~

Do not treat Gradle Groovy, Kotlin DSL, and Maven as three build scripts for the same module simultaneously. Choose the build tool actually used in your repository.

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

The exact HTTP body of this endpoint is `ok` (no JSON wrapper needed). This endpoint is intentionally simple to separate HTTP server startup failures from complex business logic failures.

### 3.3. application.properties

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
~~~

- `server.port` sets the listening port inside the process.
- `server.shutdown=graceful` lets Spring Boot wait for active requests during shutdown per lifecycle.
- `spring.lifecycle.timeout-per-shutdown-phase` caps the wait time per shutdown phase.
- `management.endpoint.health.probes.enabled=true` enables liveness/readiness health groups for local smoke tests.
- Exposes only `health` in the example, without exposing all Actuator endpoints.

With Spring Boot 3.3, when running in Kubernetes, availability probes can be auto-configured by environment; enabling them explicitly here ensures consistent local/container checks. Health endpoints do not automatically verify every business rule or external dependency unless corresponding health indicators exist.

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

The test above checks controller logic, yet **does not start a Spring context or HTTP server**. The JAR/image smoke test later verifies wiring, embedded server, classpath, runtime config, and real endpoints.

## 4. Building the Executable JAR with Gradle

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

`bootJar` builds an executable Spring Boot archive with proper dependencies/loader layout. Set an explicit archive filename so test scripts always pick the right file `build/libs/smoke-app.jar`. Do not pick a random file from a `*.jar` glob because `-plain.jar` may also exist.

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

Kotlin DSL only changes how the build script is written; the Java application source stays unchanged. Use only one DSL per module.

### 4.3. Build and Test

With Gradle Wrapper:

~~~bash
./gradlew --version
./gradlew clean test bootJar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
~~~

File to check:

~~~text
build/libs/smoke-app.jar
~~~

If `bootJar` did not produce the file, inspect task output and build logs before running the smoke script. Do not substitute `bootRun`: `bootRun` runs from Gradle-managed classes/runtime classpath and does not prove the executable JAR was packaged properly.

## 5. Building the Executable JAR with Maven

This is the Maven alternative to Gradle, using the same Java source/resources from section 3.

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

The Spring Boot parent manages dependency/plugin versions and `repackage` execution. `<finalName>smoke-app</finalName>` keeps the artifact name stable at `target/smoke-app.jar`; Maven coordinates remain `smoke-app:1.0.0`.

Build:

~~~bash
./mvnw -B -ntp clean verify
~~~

If there is no Maven Wrapper but Maven is installed per policy:

~~~bash
mvn -B -ntp clean verify
~~~

Artifact:

~~~text
target/smoke-app.jar
~~~

The `verify` goal runs preceding lifecycle phases, including test/package per project config. Make sure Maven `repackage` ran so the JAR contains the Spring Boot loader and dependencies. Do not grab an unrepackaged plain Maven JAR and expect `java -jar` to run it.

## 6. Inspecting the Artifact Before Starting

A smoke test can fail because the wrong file was selected or file transfer corrupted it. Verify the exact artifact first:

### 6.1. Check Size and SHA-256

Linux/macOS:

~~~bash
ls -lh build/libs/smoke-app.jar
sha256sum build/libs/smoke-app.jar
~~~

For Maven, change the path:

~~~bash
ls -lh target/smoke-app.jar
sha256sum target/smoke-app.jar
~~~

Windows PowerShell:

~~~powershell
Get-Item .\build\libs\smoke-app.jar | Select-Object Name, Length
Get-FileHash .\build\libs\smoke-app.jar -Algorithm SHA256
~~~

Store the digest in CI artifact metadata to compare before/after upload/download. A self-computed checksum does not prove publisher authenticity; it detects artifact tampering or corruption when compared against a digest passed over a trusted channel.

### 6.2. Inspect JAR Entries

~~~bash
jar tf build/libs/smoke-app.jar
~~~

An executable Spring Boot JAR typically has:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/smoke/SmokeApplication.class
BOOT-INF/classes/com/example/smoke/SmokeController.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/...
~~~

Loader paths may vary across Spring Boot versions; `BOOT-INF/classes` and `BOOT-INF/lib` entries are key indicators of an executable Boot archive. Do not check only whether the filename ends in `.jar`.

### 6.3. Inspect Manifest

If `unzip` is available:

~~~bash
unzip -p build/libs/smoke-app.jar META-INF/MANIFEST.MF
~~~

An executable JAR's manifest should have `Main-Class` pointing to the Spring Boot launcher and `Start-Class` pointing to the main application class. The launcher name varies with Spring Boot version/packaging mode; read the actual manifest rather than hardcoding one value across all Boot lines.

If `unzip` is absent, use JDK `jar` to extract into a temporary directory and read the manifest. Do not extract untrusted archives into the project root.

### 6.4. Check Java Runtime

~~~bash
java -version
~~~

The sample application is compiled with `--release 17`, and Spring Boot 3.3.13 requires Java 17 or higher. Smoke tests should use the exact JRE/vendor/version accepted by the deployment environment. When running on a newer Java, verify compatibility rather than assuming every patch/vendor behaves identically.

## 7. Running the JAR in a Clean Environment

### 7.1. Why Use `java -jar`?

The command:

~~~bash
java -jar build/libs/smoke-app.jar
~~~

runs the executable archive through Spring Boot's manifest/loader. This is much closer to a production launch than `bootRun` or `spring-boot:run`, which can use source classes and the build tool classpath.

For greater isolation, run from an empty temporary directory, use the absolute path to the JAR, and pass only the required environment.

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
  exec env -i \
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

  if curl --fail --silent --connect-timeout 1 --max-time 2 \
    "$BASE_URL/actuator/health/readiness" >/dev/null; then
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

BODY="$(curl --fail --silent --connect-timeout 1 --max-time 5 "$BASE_URL/smoke")"
if [[ "$BODY" != "ok" ]]; then
  echo "Unexpected /smoke response: $BODY" >&2
  cat "$LOG_FILE" >&2
  exit 1
fi

curl --fail --silent --connect-timeout 1 --max-time 5 \
  "$BASE_URL/actuator/health/liveness" >/dev/null
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

The script creates isolated `HOME`/`TMPDIR` directories, strips most extra environment variables with `env -i`, switches the working directory to the temporary folder, launches the exact JAR, and waits up to 60 seconds for readiness. `exec` replaces the subshell with the Java process so signals/cleanup target the right process. If the app exits early or times out, the script prints logs for diagnosis. The trap stops the process and removes the temporary directory.

**Adjust before using with a real app:** add only the required environment variables/secrets via an allowlist; change the port if occupied; adjust the readiness timeout to match the actual startup budget. Do not pass the developer's entire `env` into the script.

### 7.3. Meaning of the Timeout

The 60 seconds in the example is a smoke test timeout, not a promise that every application must start within 60 seconds. Large applications, JIT warmup, migrations, or dependencies may need a different budget. Base the timeout on SLAs/startup characteristics—long enough for CI stability, short enough to fail fast when the process is broken.

If the process dies before readiness, read startup logs first. If the process stays alive yet readiness never succeeds, check health indicators, config, and external dependencies. Do not raise the timeout indefinitely to mask a readiness failure.

## 8. PowerShell: Checking the JAR on Windows

You can verify the JAR using PowerShell/.NET Process APIs. The snippet below launches Java in a temporary working directory and redirects stdout/stderr to a log file; for real projects, add an environment allowlist per policy.

~~~powershell
$ErrorActionPreference = "Stop"

$jar = (Resolve-Path ".\build\libs\smoke-app.jar").Path
$port = 18080
$baseUrl = "http://127.0.0.1:$port"
$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString("N"))
$logFile = Join-Path $workDir "application.log"
New-Item -ItemType Directory -Path $workDir | Out-Null

$process = $null
$logWriter = $null

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

    $body = (Invoke-WebRequest -Uri "$baseUrl/smoke" -TimeoutSec 5).Content
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
    if ($logWriter) { $logWriter.Dispose() }
    if (Test-Path $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force }
}
~~~

Run:

~~~powershell
.\scripts\smoke-jar.ps1
~~~

Output on pass:

~~~text
JAR_SMOKE_PASS
~~~

The example uses `ProcessStartInfo.ArgumentList` on modern PowerShell/.NET. If a runner uses older Windows PowerShell/.NET lacking this property, construct properly quoted process arguments or switch to PowerShell 7. Never concatenate argument strings from untrusted input.

The script above inherits the parent process environment by default. For stricter isolation, clear unnecessary variables from `psi.Environment` and add an allowlist (e.g., `PATH`, `TEMP`, `JAVA_HOME`, and required app variables); do not mechanically delete mandatory Windows runtime variables.

## 9. Liveness, Readiness, and Startup: Three Different Questions

Spring Boot Actuator provides health groups:

- **Liveness:** is the application process in a state where it can keep running? If liveness fails, the platform may restart the container.
- **Readiness:** is the application ready to accept requests? If readiness fails, the platform should stop routing traffic to that instance.
- **Startup probe:** tells the platform/orchestrator to give the application time to boot; in Kubernetes this is a separate Pod configuration probe, not a mandatory health group for every Spring Boot app.

### 9.1. Why Not Put Every External Dependency into Liveness?

If the database briefly loses connectivity and liveness depends directly on the DB, every app instance can enter a restart loop, making recovery harder. Spring Boot recommends separating application state from external dependency state; readiness is often more appropriate for reflecting whether the app can serve requests.

Default liveness/readiness groups do not automatically check every external service. If business readiness requires a database/broker, intentionally add the indicator to the readiness group and test its behavior. Do not put heavy checks or cross-dependencies into liveness if there is a risk of restart loops.

### 9.2. Endpoints in the Example

With the properties in section 3:

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

Responses may include component details depending on security/configuration. Smoke tests should check HTTP success; do not hardcode JSON formatting/ordering. If a security policy protects the endpoints, tests must use the provisioned internal credentials/route.

### 9.3. Health 200 Does Not Prove Business Logic Works

That is why the script also calls:

~~~bash
curl --fail --silent http://127.0.0.1:18080/smoke
~~~

and checks that the body matches `ok` exactly. In a real app, choose a smoke test endpoint that creates no side effects, requires no personal data, and sufficiently exercises the critical request path. Do not use endpoints that create transactions or delete data in a startup smoke test.

### 9.4. Health Endpoints May Be Protected

If Spring Security is configured, Actuator endpoints may return 401/403 even though the app started cleanly. That can be intentional behavior. Provide test credentials/tokens via a secret manager or expose probe endpoints on a management interface/internal network per policy; never expose health details publicly just for CI convenience.

## 10. Verifying the Image in a Clean Environment

There are two common ways to build an image:

1. Spring Boot Buildpacks: Gradle `bootBuildImage` or Maven `spring-boot:build-image`.
2. Multi-stage Dockerfile: build the JAR in a builder stage, then copy it into a runtime image.

Runtime smoke testing is much the same: run the **built image reference**, without mounting source/build folders or Maven/Gradle caches from the host.

### 10.1. Building the Image with Spring Boot Buildpacks

The Gradle project in section 4 configured:

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

Buildpacks builds the image using builder/run images. A successful build does not confirm endpoints work; you still must run the container.

### 10.2. Multi-Stage Dockerfile (Alternative Option)

If the repository uses a Dockerfile, for example:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

COPY gradlew ./
COPY gradle/ ./gradle/
COPY settings.gradle build.gradle ./
RUN chmod +x gradlew

COPY src/ ./src/
RUN ./gradlew --no-daemon clean test bootJar

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/build/libs/smoke-app.jar /app/smoke-app.jar

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/smoke-app.jar"]
~~~

Build image:

~~~bash
docker build --pull -t local/smoke-app:1.0.0 .
~~~

This Dockerfile uses Gradle Groovy DSL and requires wrapper files/sources to exist in the build context without being excluded by `.dockerignore`. If using Kotlin DSL, substitute the corresponding Gradle files. If the project uses Maven, the builder stage must copy POM/Wrapper and the Maven repackage output from the right path.

This is **one image creation option**; do not add a Dockerfile if your pipeline already uses Buildpacks. In all cases, the smoke test step must run the exact final image.

### 10.3. Check Image Identity

~~~bash
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' local/smoke-app:1.0.0
~~~

Record the image ID, OS, and architecture to know which image is being tested. In CI/releases, prefer the immutable registry digest after pushing. Do not use a mutable tag as the sole proof that smoke testing and deployment ran the same bytes.

## 11. Image Smoke Testing with Docker

### 11.1. Running Manually

~~~bash
docker run --rm -p 18081:8080 local/smoke-app:1.0.0
~~~

Keep the container running in the foreground. Another terminal:

~~~bash
curl --fail --silent http://127.0.0.1:18081/actuator/health/readiness
curl --fail --silent http://127.0.0.1:18081/smoke
~~~

Application endpoint body:

~~~text
ok
~~~

Stop with Ctrl+C. `EXPOSE 8080` in the Dockerfile is only metadata; `-p 18081:8080` maps host port 18081 to container port 8080.

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

  if curl --fail --silent --connect-timeout 1 --max-time 2 \
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

BODY="$(curl --fail --silent --connect-timeout 1 --max-time 5 "$BASE_URL/smoke")"
if [[ "$BODY" != "ok" ]]; then
  echo "Unexpected /smoke response: $BODY" >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi

curl --fail --silent --connect-timeout 1 --max-time 5 \
  "$BASE_URL/actuator/health/liveness" >/dev/null

docker stop --time 20 "$CONTAINER_NAME" >/dev/null
echo "IMAGE_SMOKE_PASS"
~~~

Run:

~~~bash
chmod +x scripts/smoke-image.sh
./scripts/smoke-image.sh
~~~

Final stdout on pass:

~~~text
IMAGE_SMOKE_PASS
~~~

The script does not mount the project, `build/`, `target/`, `.gradle`, `.m2`, or source into the container. It runs the exact image, waits for readiness, checks the application body, and stops the container. The trap cleans up the container on both success and failure.

If the Docker daemon uses a different context, the image is missing locally, or port 18081 is occupied, adjust the environment/test port per CI policy. Do not switch to a different image tag just to make the script pass while forgetting to record the image ID/digest.

### 11.3. Testing Stricter Runtime Environments

For a sample app that does not write to the root filesystem, you can try additional restrictions:

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

This is an **optional hardening test**. Some applications require writable directories, certificates, native temp files, or Linux capabilities; in those cases, design minimal mounts/permissions and test per runtime contract. Do not use these flags without understanding app requirements. If the container fails only under `--read-only`, investigate filesystem writes before concluding the JAR is broken.

### 11.4. Do Not Use `--network none` Blindly

If an app needs no external services, you can verify no outbound network access via appropriate network isolation. However, publishing host ports and `none` networking do not work like bridge networks; connectivity testing must be redesigned. For apps requiring DB/Redis, total network isolation will cause readiness to fail as expected. Use a test network with ephemeral dependencies rather than skipping dependency checks.

## 12. Avoiding Unintended Inheritance of Developer Config

### 12.1. Variables That Can Cause False Passes

Environment variables affecting Spring Boot:

- `SPRING_PROFILES_ACTIVE`: selects profiles and config files.
- `SPRING_DATASOURCE_URL`/username/password: connects to the database.
- `SPRING_CONFIG_LOCATION`/`SPRING_CONFIG_ADDITIONAL_LOCATION`: loads config outside the JAR.
- `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`: injects JVM flags.
- `SERVER_PORT`: overrides the default port.
- `HTTP_PROXY`/`HTTPS_PROXY`: affects networking.
- Secrets/tokens/cloud credentials: allow the app to connect to services absent in a clean image.

If testing on a laptop with a `.env`/IDE run configuration, the app can pass even though the release image lacks required config. The JAR script uses `env -i` to clear most inherited variables, then adds only explicitly declared ones.

### 12.2. Externalized Configuration Is a Contract

If production needs:

~~~text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
~~~

supply valid values from a test secret manager/test database in the smoke/integration environment. Never hardcode credentials into the JAR, Dockerfile, build args, or test scripts. A test without a database only confirms the app can start **without a database**; it cannot validate production configuration with a DB.

### 12.3. Checking Working Directory

Spring Boot can load external configs relative to the current directory. Running from an empty temporary directory therefore catches accidental dependencies on `./application.yml` or `./config/` lying around in the repository root.

If the app intentionally uses an external config mount, test both cases:

1. Without mount: the app fails with a clear message if the config is required.
2. With mount per contract: the app starts and reaches readiness.

Do not copy all local files into the container to fix missing config; specify the exact config file that must be packaged or mounted.

## 13. Testing External Dependencies in a Clean Environment

A service may start its HTTP server yet still not be business-ready because the database/broker is unconnected. Define the startup contract:

| Test Type | External Dependencies | Goal |
| --- | --- | --- |
| Basic JAR smoke | None or mocked | Verify executable, runtime, HTTP wiring |
| Basic image smoke | None or mocked | Verify final image, entrypoint, ports, permissions |
| Integration smoke | Ephemeral DB/Redis/broker | Verify connection/config/schema/auth |
| Deployment smoke | Test/staging services | Verify network, secrets, service discovery, and platform |
| Production readiness | Real dependencies per policy | Verify operations without side effects |

### 13.1. Testcontainers for Databases

If the app requires PostgreSQL, use Testcontainers to spin up an ephemeral DB in integration tests rather than relying on a PostgreSQL installed on a developer's machine. Testcontainers manages the test container lifecycle, port mapping, and connection details; it requires an available Docker daemon.

Example test dependency (versions must be pinned and project-compatible):

~~~groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
~~~

With Maven, add Testcontainers dependencies with `test` scope and manage versions via a BOM/approved versions. Do not leave dependency versions dynamic.

Integration tests should create schemas/test data, verify app queries/transactions, and clean up. A JAR smoke test does not create a database on its own. When running the **final image**, provide a database container via a Docker network/test compose or dedicated integration environment, without mounting local DB state.

### 13.2. Readiness with External Dependencies

If a DB is mandatory to serve requests, you can add a custom health indicator to the readiness group. Consider timeouts, retries, failure behavior, and avoiding heavy queries on every probe. Liveness should reflect the app process, not arbitrarily depend on every external service, to avoid restart storms.

### 13.3. Migrations

If the app runs Flyway/Liquibase migrations on startup, a clean database smoke test should create an empty DB and confirm migrations succeed. If using an existing schema, test the upgrade path separately. Never test migrations against production data via a startup smoke script.

## 14. CI: Build Once, Test the Exact Built Artifact

A good pipeline separates building/testing the artifact from smoke-testing it in a clean environment. The smoke job receives the artifact uploaded by the build job; it **does not recompile** and test a different file.

Gradle GitHub Actions example:

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

The workflow illustrates artifact handoff between two jobs/runners. In production:

- Pin actions by full reviewed commit SHA, not just `@v4` tags.
- Check full JDK version/vendor if policy requires, and record OS/architecture.
- Compute SHA-256 in the build job, pass the checksum with the artifact, and verify it in the smoke job.
- Do not grant signing/publishing secrets to untrusted pull request jobs.
- If using Maven, change the build command to `./mvnw -B -ntp clean verify`, upload `target/smoke-app.jar`, and download to the exact path expected by the smoke script.
- If the workflow runs on a fork PR, restrict tokens/permissions and avoid executing untrusted artifacts with release credentials.

### 14.1. Image CI Smoke Test

When the pipeline builds an image via Buildpacks/Dockerfile, add a job after the image is built:

1. Tag with a reference tied to the commit/build ID.
2. Run `docker image inspect` to record image ID/architecture.
3. Run `scripts/smoke-image.sh` against that exact image reference.
4. If pushing to a registry before smoke testing, resolve the digest and smoke-test that exact digest.
5. Publish/deploy the digest only after smoke and policy gates pass.

For multi-architecture image manifest lists, note which platform the runner pulls. Testing amd64 does not prove the arm64 image runs; run a matrix across each supported architecture or gather platform-specific test evidence.

### 14.2. Artifact Promotion

Build once, promote the same artifact/image digest across dev → staging → production. Do not rebuild per environment if the requirement is to deploy the exact bytes tested. Change configuration/secrets per environment via runtime config, never by rebuilding images to embed credentials.

## 15. Startup, Readiness, and Graceful Shutdown

### 15.1. Process Started Does Not Mean Ready

Stages:

- JVM process created.
- Spring `ApplicationContext` refreshed.
- Embedded web server listening.
- Readiness health group returns UP.
- Business endpoint returns the expected result.
- External dependencies and migrations are ready per contract.

Do not just grep logs for `Started ...` and conclude everything works. Startup logs are a good sign; HTTP readiness/business probes confirm the request-serving path.

### 15.2. Startup Timeout and Retries

Use bounded retries and explicit wait times. On failure:

- Check process exit code and logs.
- Check if the port is occupied.
- Check Java version and classpath.
- Check config profile/env.
- Check external service DNS/port/auth/schema.
- Check container exit state/`OOMKilled`/restart count.

Do not bump timeout from 60 seconds to tens of minutes to hide deadlocks, failing migrations, or dependency outages.

### 15.3. Graceful Shutdown

Spring Boot graceful shutdown lets the web server wait for in-flight requests before exiting. Docker sends SIGTERM on `docker stop`, then SIGKILL after the grace period. `docker stop --time 20` in the example gives the container 20 seconds.

If using a shell-form entrypoint, signals may go to the shell instead of the Java process; Dockerfiles should use exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/smoke-app.jar"]
~~~

The Buildpacks launcher also manages process startup; inspect the actual launch process and shutdown behavior of the image. Do not assume every custom entrypoint forwards signals identically.

## 16. Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `no main manifest attribute` | Plain JAR or missing repackage | Use Gradle `bootJar`/Maven Boot repackage, check manifest |
| `ClassNotFoundException`/`NoClassDefFoundError` | Missing dependency or mispackaged JAR | Inspect `BOOT-INF/lib`, runtime dependency scopes |
| `UnsupportedClassVersionError` | Java runtime older than bytecode | Check `java -version`, `javap -verbose`, toolchain |
| App starts in `bootRun`, JAR fails | Workspace-dependent classpath/config/files | Run the exact executable JAR from a temp directory |
| Port already in use | Host/container port occupied by another process | Change host port, check port mapping |
| Container running, curl fails | App not ready, bound wrong interface/port, or bad mapping | Logs, readiness endpoint, `docker port` |
| Health endpoint 404 | Actuator missing or health probes not enabled/exposed | Dependencies and management properties |
| Health endpoint 401/403 | Security policy protects endpoint | Use internal/test credentials or permitted probe route |
| Readiness 503 while liveness 200 | App process alive, not yet ready | Inspect readiness components/config/dependencies |
| JAR passes, image fails | Runtime image differs in JDK/OS, permissions, entrypoint | Inspect image logs/user/env/architecture |
| Image passes on laptop, fails in CI | Different host ports, Docker daemon, architecture, or env | Record image ID, runner details, run exact digest |
| App needs local file missing from JAR | External file not packaged/mounted | Define config/resource contract and test mount |
| App fails when `HOME` differs | Writes to user home or relies on local cache | Use explicit writable directory/mount |
| Container exit code 137 | May be OOM killed or SIGKILL | Inspect state, memory limits, and logs |
| Container runs as root unintentionally | Base/Dockerfile/user config | Check `docker inspect Config.User` and policy |
| Smoke script hangs | Infinite retry/no process liveness check | Set timeout, check PID/container state |
| Test passes despite broken app logic | Only calling health endpoint | Add assertions on a business smoke endpoint |
| Database readiness fails | DB absent or wrong credentials/schema | Use ephemeral DB and integration tests |
| JAR checksum changes across jobs | Different artifact file or transfer/packaging change | Verify digest, pass the exact built artifact |
| Tested image tag, deployed different digest | Tag overwritten/mutable | Verify/deploy immutable digest |
| PowerShell process does not exit | Child process or event/stream handling | Manage `Process`, timeout, and cleanup properly |
| Leftover temporary files | Trap/`finally` skipped when runner killed | CI cleanup job/workspace isolation, timeouts |

### 16.1. Diagnostic Workflow

1. Identify the exact JAR path/image digest executed.
2. Check checksum/size and JAR manifest.
3. Check Java runtime and OS/architecture.
4. Run manually with `java -jar` or `docker run` and inspect logs.
5. Check process exit, port mapping, and readiness.
6. Check external configs/dependencies.
7. Compare clean environment with developer environment, adding only permitted inputs one by one.
8. Re-run the exact same artifact after fixing, and record digest and test evidence.

Do not modify application code when the real error is testing a plain JAR by mistake, wrong port mapping, or a missing secret in the smoke environment.

## 17. Practice Exercises with Answers

### Exercise 1 — Why Not Use `bootRun`?

The application passes `./gradlew bootRun` yet fails when running `java -jar build/libs/app.jar`. What is the key difference?

**Answer:** `bootRun` uses the Gradle runtime classpath and source/build outputs; `java -jar` uses the exact executable archive and manifest/loader. JAR testing catches packaging, resource, and dependency scope errors.

### Exercise 2 — Process Started, Readiness 503

Liveness returns 200, readiness returns 503. Can you conclude the app crashed?

**Answer:** No. The process may still be alive yet unready to accept traffic, for example waiting on a startup dependency or health indicator. Check readiness components and logs.

### Exercise 3 — Health 200, Business Endpoint Fails

`/actuator/health/readiness` returns 200, `/smoke` returns 500. What must the smoke test conclude?

**Answer:** Fail. Health groups verify status per indicators; the business endpoint test verifies the actual request path.

### Exercise 4 — JAR Runs Only in Project Root

What is a common cause?

**Answer:** The application depends on a relative external config/file path present in the repository. Run from a temp directory and explicitly define whether the config file should be packaged or mounted.

### Exercise 5 — Container Runs on Laptop, Fails in CI

Which factors should be compared?

**Answer:** Image digest/architecture, Docker daemon, host ports, runner permissions, external network/DNS, environment variables, secrets, and memory limits.

### Exercise 6 — Plain JAR

The build directory has `smoke-app-1.0.0.jar` and `smoke-app-1.0.0-plain.jar`. Which file should be smoke-tested?

**Answer:** The executable Boot JAR created by `bootJar`/Maven repackage, usually the file without the `plain` classifier. Configure a fixed output path to avoid picking the wrong file.

### Exercise 7 — No Actuator

If a project does not want to add Actuator, how can it smoke-test?

**Answer:** Use a safe dedicated business endpoint/readiness endpoint. Call only endpoints with no side effects and check status/body. Actuator probes are helpful, not mandatory for every project.

### Exercise 8 — Database Required on Startup

The JAR fails readiness without PostgreSQL. Is this a faulty smoke test?

**Answer:** Depends on the contract. If production requires a DB, the clean environment must provide an ephemeral/test DB and credentials; testing without a DB only checks a DB-less startup mode.

### Exercise 9 — Read-Only Container Fails

The sample app runs in a normal image yet fails with `--read-only`. What to investigate?

**Answer:** Inspect logs and writable paths, temp directories, log files, and uploads/caches. Provision `tmpfs`/volumes for the right paths with minimal permissions, or fix the app so it does not write to the root filesystem unnecessarily.

### Exercise 10 — Build Once, Smoke Elsewhere

A CI job builds the JAR and uploads the artifact; another job rebuilds the JAR and runs the smoke test. Does that meet the goal?

**Answer:** No. The smoke job must download and test **the exact artifact** from the build job, verifying checksum/digest; rebuilding risks testing different bytes.

## 18. Pre-Release Checklist

- [ ] Use Gradle `bootJar` or Maven `repackage` to produce the executable Boot JAR.
- [ ] Select the artifact by fixed path/name; avoid wildcards that could grab a plain JAR.
- [ ] Verify size, SHA-256, manifest, and expected JAR entries.
- [ ] Run `java -jar` in a temporary working directory.
- [ ] Isolate environment variables and pass only required configs/secrets.
- [ ] Use JRE/JDK and OS/architecture matching the deployment environment.
- [ ] Set a readiness timeout, check for early process exit, and capture logs on failure.
- [ ] Check health/readiness/liveness and at least one business smoke endpoint.
- [ ] Run container images without mounting host sources, build outputs, or local caches.
- [ ] Verify image ID/digest and run the exact image intended for deployment.
- [ ] Check ports, entrypoint, user, permissions, tmp directories, and graceful shutdown.
- [ ] If DB/broker is needed, use ephemeral/managed test services and integration checks.
- [ ] CI smoke job receives the exact built artifact, verifies checksum, and does not rebuild.
- [ ] Image smoke job tests the exact digest, not just a mutable tag.
- [ ] Clean up processes/containers/temp files on both pass and fail.
- [ ] Retain auditable logs, build ID, artifact digest, image digest, and test results.
- [ ] Never bake secrets into JAR/image/logs; do not expose Actuator details publicly just for test convenience.

**Conclusion:** `bootRun` or the Maven run goal only shows the app runs in the build environment. Release readiness requires running the **actual executable JAR** via `java -jar` in a clean environment and running the **actual final image** without relying on host workspace/caches. Combine process checks, readiness, business endpoints, external dependency tests, checksums/digests, and cleanup to know accurately whether the deliverable can start and serve requests in its target environment.

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

Timeouts, ports, image tags, and runner labels in the examples are lab values. When adopting into CI/release, pin tool/action versions per policy, choose timeouts based on startup budgets, verify exact image digests, and supply only required external configurations.