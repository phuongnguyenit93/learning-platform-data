# Inspecting Image Size, Layer Contents, and Startup Readiness

## 1. Why Docker Image Verification Does Not Stop at `docker build`

In a Spring Boot application, a Dockerfile can build successfully yet still produce an image that is bloated, missing the JAR, containing unwanted data, or unable to serve HTTP requests. A thorough QA workflow must therefore answer three distinct questions:

1. **Image size:** what is the total byte size of the image; how much is the Java runtime versus the application and libraries?
2. **Layer contents:** does the Docker image contain the expected filesystem layers and runtime files; are dependency layers reused from cache when only application code changes?
3. **Startup readiness:** does the container launch the right Java runtime, initialize the Spring context, open its port, and return HTTP health/endpoint responses within a deadline?

Running **`docker build`** only proves an image could be constructed. Running **`docker run -d`** returns a container ID even if Java crashes a second later. Running **`docker image ls`** prints a SIZE without proving a servlet ever served a request. All three verification groups must be performed independently.

This lesson belongs to the **Dockerfile** topic under Spring Boot Build Tooling Packaging, illustrated with Java 17 and Spring Boot 3.5, featuring Maven/Gradle examples, two Dockerfiles, and QA commands for Linux or Windows.

## 2. Image, Container, and Layer Concepts

An **image** is an immutable artifact combining configuration (`ENTRYPOINT`, `USER`, `WORKDIR`, `EXPOSE`...) with read-only filesystem layers. A **container** is a live instance with a process, network, runtime state, logs, and a writable filesystem layer. One image can spawn many containers.

~~~text
Source + Maven/Gradle
         |
         v
Spring Boot executable JAR
         |
         v
Dockerfile + docker build
         |
         v
Image filesystem layers + config
         |
         v
docker run -> Container -> Java process -> Spring Boot
         |
         v
HTTP request + health/readiness
~~~

**Spring Boot layers** and **Docker image layers** are not the same thing. The Spring Boot Maven/Gradle plugin can generate **`BOOT-INF/layers.idx`** with four groups:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Spring Boot 3.5 uses **`spring-boot-jarmode-tools`**, which can be invoked via:

~~~bash
java -Djarmode=tools -jar app.jar list-layers
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

The extract command creates folders matching the **Spring Boot** groups, yet **does not create image layers**. Only when a Dockerfile executes separate **`COPY --from=extractor`** instructions does Docker produce the corresponding filesystem layers.

Never treat **`RootFS.Layers`** in `docker inspect` as a list of **`BOOT-INF/layers.idx`** names. One represents the image's filesystem layers, while the other is file-grouping metadata inside the Java archive.

## 3. Sizes That Are Easily Confused

| Value | Command | What It Reflects |
| --- | --- | --- |
| **Image SIZE** | `docker image ls` | Total uncompressed size of filesystem layers for the local image/platform |
| **Image `.Size`** | `docker image inspect` | Image bytes if provided by the engine/image store |
| **Shared / Unique** | `docker system df -v` | Storage shared across images vs unique to each image on the host |
| **BuildKit cache** | `docker buildx du` | Build cache records stored by the builder |
| **Registry compressed blobs** | Registry manifest/OCI tooling | Compressed bytes to upload/download on a cache miss |
| **Container writable layer** | `docker inspect --size` | Data written by a container, not the image size |

Never report **`docker image ls SIZE` as the network download size**. Docker registries store compressed blobs, clients may already cache base layers locally, and multi-platform tags can point to different platform variants.

Never sum every row of **`docker image ls`** to estimate unique disk usage: two images sharing a base JRE share its layers. Use **`docker system df -v`** to inspect shared vs unique storage.

Similarly, **`docker buildx du`** does not measure runtime image size; it measures the builder's cache records. A 4 GB cache report does not mean your shipped Docker image is 4 GB.

## 4. Preconditions for a Valid Comparison

When comparing two Dockerfiles, hold these constant:
- Same Git commit and exact same executable Boot JAR.
- Same Java target and Spring Boot/plugin versions.
- Same JRE base image or pinned digest.
- Same OS/CPU architecture, e.g., `linux/amd64`.
- Same Docker Engine/BuildKit builder and cache policy.
- Same CPU/memory limits when measuring startup time.
- Same health endpoint and test suite.

Check the environment:

~~~bash
java -version
docker version
docker info
docker buildx version
~~~

If the Docker CLI cannot connect to the daemon, resolve permissions/services per host policy. Never wipe Docker caches or images belonging to other projects just to capture a cold measurement.

In production, pin the digest of an approved base image and track security patches. This lesson uses **`eclipse-temurin:17-jre`** for readability, without claiming it is always the smallest or safest image.

## 5. Java 17/Spring Boot Project for Testing Real Images

We build a simple HTTP endpoint with Actuator readiness and a JUnit test. The example uses **Spring Boot 3.5.16** with Java 17. For new projects, use a branch and patch release supported by your organization; the version here is a technical illustration.

### 5.1. File layout

~~~text
image-check/
├── pom.xml                       (Maven)
│   or
├── build.gradle                  (Gradle)
├── settings.gradle               (Gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/...
├── gradlew / gradlew.bat / gradle/wrapper/...
├── Dockerfile.flat
├── Dockerfile.layered
└── src/
    ├── main/
    │   ├── java/com/example/imagecheck/
    │   │   ├── ImageCheckApplication.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/java/com/example/imagecheck/
        └── ProbeControllerTest.java
~~~

Choose **either Maven or Gradle** in a real project. Wrapper scripts must be generated by Spring Initializr or the corresponding Wrapper tooling; adding a POM or `build.gradle` does not automatically generate **`mvnw`** or **`gradlew`**.

### 5.2. Main class

File **`src/main/java/com/example/imagecheck/ImageCheckApplication.java`**:

~~~java
package com.example.imagecheck;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImageCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImageCheckApplication.class, args);
    }
}
~~~

### 5.3. Controller

File **`src/main/java/com/example/imagecheck/ProbeController.java`**:

~~~java
package com.example.imagecheck;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    @GetMapping("/probe")
    public String probe() {
        return "image-check-ok";
    }
}
~~~

When the app is actually serving HTTP, the response body of **`GET /probe`** is exactly:

~~~text
image-check-ok
~~~

### 5.4. `application.properties`

File **`src/main/resources/application.properties`**:

~~~properties
spring.application.name=image-check
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
~~~

**`spring-boot-starter-actuator`** exposes health endpoints. **`management.endpoint.health.probes.enabled=true`** enables the liveness/readiness groups when testing outside Kubernetes. Once the app is ready with no failing indicators, **`/actuator/health/readiness`** typically returns:

~~~json
{"status":"UP"}
~~~

Spring Boot readiness does not automatically check every external system; if you need to check an external dependency, configure an appropriate health group and evaluate the operational risk.

### 5.5. JUnit/MockMvc test

File **`src/test/java/com/example/imagecheck/ProbeControllerTest.java`**:

~~~java
package com.example.imagecheck;

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
class ProbeControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void probeReturnsExpectedBody() throws Exception {
        mvc.perform(get("/probe"))
                .andExpect(status().isOk())
                .andExpect(content().string("image-check-ok"));
    }
}
~~~

**Note:** this test runs on Maven/Gradle's classpath; it **does not prove the Docker image has all runtime libraries**. You must run the actual image and send HTTP requests in later steps.

## 6. Maven Configuration to Build an Executable Layered JAR

File **`pom.xml`**:

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
    <artifactId>image-check</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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
                <configuration>
                    <layers>
                        <enabled>true</enabled>
                    </layers>
                    <includeTools>true</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Boot starter parent supplies managed versions and **`repackage`** execution when the plugin is declared. **`layers.enabled`** creates layer metadata; **`includeTools`** keeps **`spring-boot-jarmode-tools`** inside the executable JAR. In Spring Boot 3.5, both are enabled by default in standard setups, yet written explicitly here for clarity.

**Do not enable `<executable>true</executable>`** in Maven for an archive needing `jarmode` tools: a fully executable JAR prepended with a Unix launch script is incompatible with tools mode.

Build:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

When tests pass, the Boot JAR is typically at:

~~~text
target/image-check-1.0.0.jar
~~~

Use **`mvnw.cmd`** on Windows. If you customize `finalName` or `classifier`, adjust the `COPY` paths below to match the actual artifact.

## 7. Equivalent Gradle Configuration

If using Gradle, **you do not need `pom.xml`** above. File **`settings.gradle`**:

~~~groovy
rootProject.name = 'image-check'
~~~

File **`build.gradle`** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    layered {
        enabled = true
    }
    includeTools = true
}
~~~

Build with a compatible Gradle Wrapper (e.g., Gradle 8.14 in the Spring Boot 3.5 range):

~~~bash
./gradlew --version
./gradlew clean test bootJar
~~~

Default output:

~~~text
build/libs/image-check-1.0.0.jar
~~~

**`bootJar`** differs from the plain **`jar`** task. When using Gradle, replace every **`COPY target/image-check-1.0.0.jar`** in the Dockerfiles with **`COPY build/libs/image-check-1.0.0.jar`**. Never run both Maven and Gradle and mix artifacts from two projects.

## 8. `Dockerfile.flat`: Copying the Whole Boot JAR

Create **`Dockerfile.flat`**:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /application

COPY target/image-check-1.0.0.jar application.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

- The base JRE suffices to run Java without carrying Maven, Gradle, or `javac`.
- **`COPY`** puts the Spring Boot executable JAR into runtime.
- **`USER 10001:10001`** uses a numeric non-root account; verify files and working directory are readable by that user.
- **`EXPOSE 8080`** only documents metadata; it does not publish a host port.
- **`ENTRYPOINT`** uses exec form so Java receives signals more directly than with an arbitrary shell wrapper.

Build after Maven `clean verify` succeeds:

~~~bash
docker build -f Dockerfile.flat -t image-check:flat .
~~~

This approach is straightforward. However, editing a single controller changes the bytes of the original uber JAR completely; the Docker layer holding `application.jar` must be rebuilt even though third-party dependencies did not change.

## 9. `Dockerfile.layered`: Copying Spring Boot Layers

Create **`Dockerfile.layered`**:

~~~dockerfile
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /builder

COPY target/image-check-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /builder/extracted/dependencies/ ./
COPY --from=extractor /builder/extracted/spring-boot-loader/ ./
COPY --from=extractor /builder/extracted/snapshot-dependencies/ ./
COPY --from=extractor /builder/extracted/application/ ./

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

In the extractor stage, **`jarmode` tools** split the Boot executable archive into folders. The runtime stage copies only the extracted files; the original full uber JAR does not need to exist in the final image.

Four default directories:
- **`dependencies`**: stable third-party dependencies.
- **`spring-boot-loader`**: Spring Boot Loader classes.
- **`snapshot-dependencies`**: SNAPSHOT dependencies, if any.
- **`application`**: compiled application classes/resources and local project components.

In this efficient runtime layout, Spring Boot tools generate a thin **`application.jar`** and JAR files under **`lib/`**. The four `COPY`s merge contents into **`/application`**; copying only **`extracted/application/`** alone is not enough to run.

Build:

~~~bash
docker build -f Dockerfile.layered -t image-check:layered .
~~~

If custom layer names are defined, update the `COPY` lines to match **`list-layers`** output rather than assuming four fixed layers. Putting stable content first and frequently changing content last creates caching opportunities; **it does not guarantee a smaller image `SIZE`**.

### 9.1. Inspecting Spring Boot Layers Before the Docker Build

~~~bash
java -Djarmode=tools -jar target/image-check-1.0.0.jar list-layers
java -Djarmode=tools -jar target/image-check-1.0.0.jar extract --layers --destination extracted
~~~

Expected default `list-layers` output:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

These commands **do not execute `Application.main()`** and do not run JUnit; they operate solely on the built archive. **`-Djarmode=tools`** must precede **`-jar`**, otherwise the JVM will not pick up the `JarMode` system property in time.

## 10. Inspecting Image Size with `docker image ls`

Once both tags are built:

~~~bash
docker image ls image-check
~~~

The table below is **illustrative only**, not actual live output:

~~~text
REPOSITORY    TAG       IMAGE ID        SIZE
image-check   flat      <image-id-1>     238MB
image-check   layered   <image-id-2>     239MB
~~~

Both images can have nearly identical total size because they hold the same JRE and dependencies, differing only in layout. Do not conclude from the sample table that layered is worse: the primary goal may be cutting bytes re-pushed/pulled when source code updates.

Use formatted output for logging:

~~~bash
docker image ls image-check --format 'table {{.Repository}}:{{.Tag}}	{{.ID}}	{{.Size}}'
~~~

To read exact byte counts:

~~~bash
docker image inspect image-check:flat --format '{{.Size}}'
docker image inspect image-check:layered --format '{{.Size}}'
~~~

**`.Size`** is present on many Docker engines/image stores, yet may not behave identically in every mode; if the field is absent, rely on **`docker image ls`** and engine-compatible inspection instead of filling in zero.

**Units:** 1 MiB = 1,048,576 bytes; 1 MB = 1,000,000 bytes. Always convert to the same unit when comparing.

### 10.1. Recording Exact Platform and Image Identity

~~~bash
docker image inspect image-check:layered --format '{{.Id}}'
docker image inspect image-check:layered --format '{{.Os}}/{{.Architecture}}'
docker image inspect image-check:layered --format '{{json .Config.Entrypoint}}'
docker image inspect image-check:layered --format '{{.Config.User}}'
~~~

If image A was built for `linux/amd64` and B for `linux/arm64`, they can include differently sized JREs. Never attribute that difference to Dockerfile optimization. Image tags can be overwritten on rebuilds; record image IDs/digests so you do not compare the wrong version.

## 11. Inspecting Docker Filesystem Layers with `history`

~~~bash
docker image history image-check:flat
docker image history image-check:layered
docker image history --no-trunc image-check:layered
~~~

To focus on instructions and layer sizes:

~~~bash
docker image history --format 'table {{.CreatedBy}}	{{.Size}}' image-check:layered
~~~

In the layered image, look for the **`COPY --from=extractor`** lines for dependencies, loader, snapshot dependencies, and application, alongside the base image entries. Docker history lists entries **newest first**.

Metadata instructions like **`USER`**, **`WORKDIR`**, **`EXPOSE`**, and **`ENTRYPOINT`** modify image config without necessarily adding filesystem bytes, so they often show **`0B`**.

### 11.1. `RootFS.Layers` Are Not Spring Boot Layer Names

~~~bash
docker image inspect image-check:layered --format '{{json .RootFS.Layers}}'
~~~

**`RootFS.Layers`** is typically a list of uncompressed filesystem **diff IDs**. They are neither registry compressed blob digests, nor layer names from `layers.idx`, nor in a 1:1 relationship with every `0B` history entry.

Therefore, seeing 14 rows in `history` while `RootFS.Layers` has 8 elements is not an error. Metadata-only instructions do not create filesystem layers.

### 11.2. When Does a Layered Dockerfile Actually Pay Off?

If a developer edits only **`ProbeController.java`**:
- Flat image: the original JAR changes, so the JAR's `COPY` layer invalidates.
- Layered image: the `dependencies`/`loader` folders keep identical contents and can hit cache; only the `application` layer changes.
- If the Spring Boot or dependency version changes, the affected library layers change too.

Therefore compare **rebuild time, cache hits, and uploaded/pulled bytes**, not just image `SIZE`. On a completely fresh CI runner with no cache, extraction adds overhead without caching gains.

## 12. Shared Storage and Cache Disk Usage

~~~bash
docker system df
docker system df -v
docker buildx du
~~~

**`docker system df -v`** shows `SHARED SIZE` and `UNIQUE SIZE` across local images. When flat and layered images share the same base JRE, they share those base layers.

**`docker buildx du`** reports BuildKit builder cache. This number can be far larger than image `SIZE` because it holds snapshots, build contexts, and intermediate build records. Never treat it as runtime image size.

**Never run `docker system prune -a` or `docker builder prune` on shared machines.** Those commands can wipe other projects' images and caches, slowing down subsequent builds and skewing benchmarks. Use isolated runners/builders or clean only the resources created by your job per policy.

## 13. Inspecting Actual Files Inside the Runtime Image

Image history does not list every file. When the base image has a shell, override `ENTRYPOINT` to inspect the filesystem:

~~~bash
docker run --rm --entrypoint sh image-check:layered   -c 'ls -la /application; ls /application/lib | head -n 20'
~~~

Flat image:

~~~bash
docker run --rm --entrypoint sh image-check:flat   -c 'ls -lh /application/application.jar'
~~~

The layered image must contain **`/application/application.jar`**, the **`lib/`** directory, and supporting files of the extracted layout. The flat image needs only the original Boot JAR and Java runtime. Do not delete `lib/` to shrink the image, or the runtime will lose required classes.

This is only **filesystem inspection**, not a Java startup check. Distroless images usually lack **`sh`**; use a suitable builder/debug stage rather than adding a shell to production just for inspection.

### 13.1. Inspecting Image Configuration

~~~bash
docker image inspect image-check:layered --format '{{json .Config.Entrypoint}}'
docker image inspect image-check:layered --format '{{.Config.WorkingDir}}'
docker image inspect image-check:layered --format '{{.Config.User}}'
docker image inspect image-check:layered --format '{{json .Config.ExposedPorts}}'
~~~

With the sample Dockerfile:
- Entrypoint runs **`java -jar application.jar`**.
- WorkingDir is **`/application`**.
- User is **`10001:10001`**.
- ExposedPorts contains **`8080/tcp`** metadata.

**`EXPOSE` does not publish host ports.** To access the service from the host, use **`-p`** or appropriate container network/orchestrator config.

### 13.2. Checking for Files That Should Not Be Present

A typical runtime image should not contain:
- Git repositories, Java source/test outputs, Maven/Gradle caches;
- private keys, access tokens, or `.env` files holding secrets;
- compiler toolchains or package manager caches unused at runtime;
- stale logs or temporary build files.

During inspection, never dump raw environment variables or credential contents into public logs. Note that image history can retain data from earlier layers even if deleted in the final filesystem. If a secret leaks, rotate/revoke it and rebuild cleanly.

## 14. Startup: A Container ID Does Not Mean Spring Boot Is Ready

Run the layered image on localhost:

~~~bash
docker run -d --name image-check-smoke   -p 127.0.0.1:18080:8080   image-check:layered
~~~

Explanation:
- **`-d`** runs detached.
- **`--name`** makes inspection/logs easy.
- **`-p 127.0.0.1:18080:8080`** publishes host loopback port 18080 to container port 8080, limiting exposure during testing.
- The Java process starts via `ENTRYPOINT`.

After Docker returns a container ID, **you must still check process state**:

~~~bash
docker ps --filter "name=image-check-smoke"
docker ps -a --filter "name=image-check-smoke"
docker inspect --type container image-check-smoke --format '{{.State.Status}}'
~~~

When a container has exited or is restarting:

~~~bash
docker inspect --type container image-check-smoke   --format 'exit={{.State.ExitCode}} oom={{.State.OOMKilled}}'
docker logs --tail 80 image-check-smoke
~~~

**`OOMKilled=true`** signals memory exhaustion; check container limits, heap, and native memory. **`ExitCode=0`** may be fine for a batch job, yet for a long-running HTTP service, exiting fails the goal of serving requests.

### 14.1. Reading Logs by Layer

| Symptom | Layer to Check |
| --- | --- |
| `Unable to access jarfile application.jar` | `COPY`/`WORKDIR`/`ENTRYPOINT` |
| `UnsupportedClassVersionError` | JRE runtime and Java target |
| `NoClassDefFoundError` / `ClassNotFoundException` | `lib/` or missing `COPY` layer |
| `BeanCreationException` | Spring DI/config |
| Port bind error | `server.port` or networking |
| `OOMKilled` | Memory limit and JVM memory |
| Connection refused | Server not ready yet, crashed process, or port mapping |
| 404 from actuator readiness | Actuator dependency, probe settings, base path |

Do not tweak `build.gradle`/`pom.xml` blindly when the real issue is a wrong host port or missing runtime secret; equally, do not tweak Spring properties when the image is missing `application.jar`.

## 15. HTTP Smoke Test + Spring Boot Actuator

From the host terminal:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/probe
~~~

Exact body on success for this example:

~~~text
image-check-ok
~~~

Check Actuator:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health/liveness
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health/readiness
~~~

When ready, readiness normally returns:

~~~json
{"status":"UP"}
~~~

**Liveness** reflects whether the process can keep running; avoid tying it directly to external DB errors so a DB outage does not restart every pod. **Readiness** reflects readiness to receive traffic based on Spring `ApplicationAvailability` and configured health indicators; it does not check every external dependency by default.

If Spring Security blocks health endpoints, configure HTTP authentication and exposure policies properly — **do not expose all Actuator endpoints publicly** just for test convenience.

### 15.1. Retrying with a Deadline Instead of Fixed Sleep

Java and Spring Boot take time to initialize the `ApplicationContext`. `docker run -d` can return many seconds before readiness. A CI script must:
1. Poll the endpoint repeatedly within a bounded deadline.
2. Pass only when both HTTP status and response match.
3. On timeout, print `docker logs`/`State.ExitCode` and fail.
4. Clean up the test container afterward.

Never rely solely on **`sleep 2`** and assume any app taking longer than 2 seconds is undeployable.

## 16. Bash Smoke Script with Cleanup

For a dedicated CI Linux test runner, create **`smoke.sh`**:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

name="image-check-ci-smoke"
base="http://127.0.0.1:18080"

docker run -d --name "$name"   -p 127.0.0.1:18080:8080 image-check:layered >/dev/null

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ready=0
for attempt in $(seq 1 30); do
  if curl --fail --silent "$base/actuator/health/readiness" |
     grep -q '"status":"UP"'; then
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "FAIL: readiness not UP"
  docker ps -a --filter "name=$name"
  docker logs --tail 100 "$name"
  exit 1
fi

body="$(curl --fail --silent --show-error "$base/probe")"
if [ "$body" != "image-check-ok" ]; then
  echo "FAIL: unexpected response"
  exit 1
fi

echo "PASS: container ready and HTTP probe correct"
~~~

Run:

~~~bash
chmod +x smoke.sh
./smoke.sh
~~~

When everything passes, the script prints:

~~~text
PASS: container ready and HTTP probe correct
~~~

This is **expected example stdout**, not output observed on the current machine. The script requires Bash, Docker, `curl`, `grep`, and `seq`. It uses a fixed container name and port, suitable only for an isolated runner with no concurrent jobs. In parallel CI, derive container names and ports per job ID so you never remove someone else's container.

The script removes only the container it created; it never prunes all images/caches. If a deadline longer than 30 × 1 second is needed, tune it to match your organization's startup SLO and resource limits.

## 17. Stopping Containers, Checking CPU/RAM, and `HEALTHCHECK`

For a manually started container:

~~~bash
docker stop --time 15 image-check-smoke
docker ps -a --filter "name=image-check-smoke"
docker rm image-check-smoke
~~~

Use **`docker stop`** to give the app a chance at graceful shutdown rather than always using `kill -9`. While the container runs, check runtime resource usage:

~~~bash
docker stats --no-stream image-check-smoke
docker inspect --size --type container image-check-smoke
~~~

**`docker stats`** measures CPU/memory/network; **`docker inspect --size`** adds `SizeRw`/`SizeRootFs` for the container filesystem. They are **not image `SIZE`** and not compressed download sizes.

### 17.1. Missing `HEALTHCHECK` Does Not Mean Unhealthy

The two Dockerfiles above do not declare `HEALTHCHECK`, so Docker does not transition containers into a **`healthy`** state. **`.State.Health`** may be absent or `null`.

To use Docker `HEALTHCHECK`, a check tool must exist inside the runtime image. This snippet **works only if the actual runtime includes `curl`**:

~~~dockerfile
HEALTHCHECK --interval=30s --timeout=3s   --start-period=40s --retries=3   CMD curl --fail --silent http://127.0.0.1:8080/actuator/health/readiness || exit 1
~~~

Never assume `eclipse-temurin` or distroless includes `curl`. When the helper is absent, the healthcheck fails even if the web server works fine. Use Kubernetes HTTP probes or a deliberately packaged health checker instead.

For images with `HEALTHCHECK`:

~~~bash
docker inspect --type container image-check-smoke   --format '{{json .State.Health}}'
~~~

Kubernetes liveness/readiness probes and Docker healthchecks use different orchestration mechanisms. For slow-starting apps, Kubernetes **`startupProbe`** prevents premature restarts before the app is ready.

## 18. Flat vs Layered Comparison with Illustrative Numbers

| Metric | Flat | Layered | Notes |
| --- | ---: | ---: | --- |
| Image uncompressed `SIZE` | 238 MiB | 239 MiB | Layering does not shrink size automatically |
| `COPY` runtime content | One uber JAR | Four layer groups | Different cache boundaries |
| First image build | 24 s | 29 s | Layered adds extraction step |
| Rebuild after editing controller | 12 s | 6 s | Stable dependencies can hit cache |
| Readiness time | 4.2 s | 4.0 s | Requires repeated samples to confirm |
| `/probe` | PASS | PASS | Identical functionality |

**All numbers are hypothetical for illustration.** Comparisons are meaningful only with the same source, JRE, platform, test conditions, and Docker cache policy.

Example size increase:

~~~text
Delta SIZE = 239 - 238 = +1 MiB
Delta% = 1 / 238 * 100% = +0.42%
~~~

Do not call that a "size reduction" simply because a layered Dockerfile was used. In the hypothetical table, rebuild time dropping from 12 to 6 seconds is a **50%** drop, yet you must measure repeatedly in real CI before drawing conclusions.

To measure from a registry, compressed blobs and layers already cached on the client determine actual bytes pulled. A multi-arch tag can point to multiple manifests; **`docker image ls`** on a `linux/amd64` host does not represent pull bytes on a `linux/arm64` host.

## 19. PowerShell / Windows Docker Desktop

Docker Desktop provides the Docker CLI from PowerShell:

~~~powershell
docker image ls image-check
docker image history image-check:layered
docker image inspect image-check:layered --format '{{.Os}}/{{.Architecture}}'
docker system df -v
~~~

Test the container:

~~~powershell
docker run -d --name image-check-ps -p 127.0.0.1:18080:8080 image-check:layered
docker ps -a --filter "name=image-check-ps"
docker logs --tail 60 image-check-ps
~~~

Call HTTP:

~~~powershell
(Invoke-WebRequest 'http://127.0.0.1:18080/probe').Content
(Invoke-WebRequest 'http://127.0.0.1:18080/actuator/health/readiness').Content
~~~

Then clean up:

~~~powershell
docker stop image-check-ps
docker rm image-check-ps
~~~

**`Invoke-WebRequest`** returns a response object; read **`.Content`** for the body. When Docker Desktop runs Linux containers, the Java 17 base image is still a Linux JRE; do not mistake it for a native Windows executable. With Gradle, adjust `COPY` source paths in the Dockerfile using forward slashes rather than putting PowerShell backslashes into a Linux image.

## 20. Quick Diagnostic Table

| Failure | Where to Investigate |
| --- | --- |
| Docker `COPY` cannot find JAR | Maven/Gradle output path, `.dockerignore`, build context |
| Image too large | JDK base instead of JRE, stray files, layer history |
| Layered not smaller than flat | Normal when holding the same runtime files |
| `buildx du` is huge | BuildKit cache, not runtime image size |
| `history` shows many `0B` entries | Metadata instructions; not every line adds filesystem bytes |
| `Unable to access jarfile` | Wrong `WORKDIR`/`ENTRYPOINT`/`COPY` |
| `ClassNotFoundException` | Missing `lib/` or custom layer |
| `UnsupportedClassVersionError` | Java runtime too old |
| `docker run -d` exits immediately | Check logs, `State.ExitCode`, `OOMKilled` |
| Port 18080 busy | Pick another host port and update `curl` URL |
| Container running yet `curl` fails | Startup still in progress, port mapping, bind address, app exception |
| Actuator 404/401 | Missing `starter-actuator`, probe settings, or security rules |
| Health unhealthy | Check if healthcheck command has `curl` and right port |
| Image works on one machine, fails on another | Architecture/platform, JRE/OS differences |
| Dependency layer misses cache | Build inputs, ordering, new base digest, builder cache policy |
| Docker disk full while image `SIZE` looks small | Volumes, stopped containers, builder cache, `docker system df` |

Read logs layer by layer: image build → filesystem layout → Java runtime/classpath → Spring context → networking → readiness → business behavior.

## 21. Pre-Release QA Checklist

- [ ] Java build/tests pass; artifact is the right-version Boot executable JAR.
- [ ] Dockerfile copies the exact file, not excluded by `.dockerignore`.
- [ ] Same base JRE/platform used when comparing flat vs layered.
- [ ] Spring Boot layered mode includes tools JAR and all layer folders are copied.
- [ ] Read `docker image ls`, `image inspect`, recording units and image ID.
- [ ] Read `docker image history` and `RootFS.Layers`, distinguishing `0B` metadata entries.
- [ ] Do not confuse Image `SIZE` with shared/unique disk, builder cache, or compressed registry bytes.
- [ ] Runtime filesystem has `application.jar` and `lib/` when using the layered layout.
- [ ] No source/test outputs, build caches, or secrets/credentials present.
- [ ] `WORKDIR`, `USER`, `ENTRYPOINT`, and `EXPOSE` configured properly.
- [ ] Container is running with no fatal startup errors in logs.
- [ ] `GET /probe` returns exact body **`image-check-ok`**.
- [ ] `/actuator/health/readiness` reports `UP` within the deadline.
- [ ] Checked graceful stop, `OOMKilled`, and CPU/RAM usage if needed.
- [ ] When `HEALTHCHECK` is declared, helper binary genuinely exists and targets the right endpoint.
- [ ] Recorded cache state, startup timings, and actual image sizes when comparing optimizations.
- [ ] Recorded source commit, JDK, image digest, platform, and security scan evidence.
- [ ] Cleaned up only test containers created by the job, without pruning other projects' resources.

## 22. Conclusion

A Dockerfile QA workflow should follow:

~~~text
Build Spring Boot JAR + tests
              |
              v
docker build flat/layered
              |
              v
docker image ls / inspect -> size + platform
              |
              v
docker history + RootFS.Layers -> layers
              |
              v
Inspect runtime application.jar + lib
              |
              v
docker run + ps/inspect/logs
              |
              v
curl /probe + Actuator readiness
              |
              v
stop container + archive release evidence
~~~

**A small image is not enough; well-structured layers are not enough either.** An artifact is trustworthy only when runtime files are right, it runs on the target platform, and it passes smoke tests. Spring Boot layer extraction primarily enables dependency cache reuse — it does not make required dependencies disappear.

## 23. Official Reference Documentation

- Docker — Image list and SIZE: https://docs.docker.com/reference/cli/docker/image/ls/
- Docker — Image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Docker — Image history: https://docs.docker.com/reference/cli/docker/image/history/
- Docker — Docker system df: https://docs.docker.com/reference/cli/docker/system/df/
- Docker — Buildx du: https://docs.docker.com/reference/cli/docker/buildx/du/
- Docker — Docker inspect: https://docs.docker.com/reference/cli/docker/inspect/
- Docker — Dockerfile reference: https://docs.docker.com/reference/dockerfile/
- Docker — Build cache optimization: https://docs.docker.com/build/cache/optimize/
- Docker — Multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Spring Boot 3.5 — Dockerfiles with jarmode tools: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.5 — Maven packaging: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle packaging: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Actuator health and probes: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html