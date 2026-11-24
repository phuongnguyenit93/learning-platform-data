# Ordering COPY by Layer to Maximize Cache Reuse in a Spring Boot Dockerfile

## 1. Goal: Edit Source Without Redoing Everything

When packaging a Spring Boot application into a container image, a common optimization mistake is **copying the entire source tree into the image too early**:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -ntp package
```

Whenever `src/main/java` or any file pulled in by `COPY . .` changes, that `COPY` instruction can no longer reuse the cache. Every subsequent step, including `RUN mvn package`, must be re-evaluated in a fresh filesystem state. As a result, editing one line of Java can trigger a lot of unnecessary dependency work, especially when network library downloads are slow.

**Core strategy:**

> Place **the least-frequently changing, most expensive files and operations** at the top of the Dockerfile; put **frequently changing files** like `src/` and application resources into the last `COPY` instructions.

Example optimized pattern in the **build stage**:

```dockerfile
COPY pom.xml ./
RUN mvn -B -ntp dependency:go-offline
COPY src/ ./src/
RUN mvn -B -ntp package
```

And in the **runtime image**, Spring Boot supports splitting the executable JAR into **application layers** and executing `COPY` in order:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Most fixed-version dependencies change far less often than application classes. Consequently, many code edits can reuse the dependency image layers, reducing the amount of data rebuilt and pushed/pulled from the registry.

This lesson clearly separates **two distinct places where cache can be reused**:

1. **Docker build-time cache from source:** avoids resolving/downloading dependencies unnecessarily when only Java code changes.
2. **Final runtime image cache:** avoids recreating/pushing unchanged dependency JAR layers even when the overall executable JAR file changes.

The two approaches complement each other but **are not the same mechanism**. Examples use Docker BuildKit, Java 17, and Spring Boot 3.5.x; adjust filenames and versions for other projects.

## 2. How Does Docker Cache Work with `COPY`?

### 2.1. A Dockerfile Is a Chain of Dependent Steps

Simplified for learners:

```text
FROM base-image
    |
    v
COPY stable-build-files
    |
    v
RUN dependency-resolution
    |
    v
COPY application-source
    |
    v
RUN compile-and-package
    |
    v
COPY artifact into runtime-image
```

Docker/BuildKit computes cache keys from each step's instruction and inputs. For `COPY`/`ADD`, the builder hashes file contents and relevant metadata (such as mode/permissions). Changing only the **file modification timestamp `mtime`** is normally not enough to invalidate cache. For a regular `RUN`, BuildKit does not inspect downloaded packages inside the container to check if an upstream repository released updates; caching depends on the instruction/state and modeled inputs.

Once a step misses cache, dependent **downstream** steps must be recomputed/rechecked. Modern BuildKit can optimize independent stages, yet the safe mental model is: **a change in an early layer usually creates more work downstream**.

### 2.2. Two Dockerfiles That Both Run, Yet Behave Differently Under Cache

**Unoptimized:**

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -ntp dependency:go-offline
RUN mvn -B -ntp package
```

Because `COPY . .` copies both source code and POM before dependency resolution, every Java source edit invalidates the layer beneath `dependency:go-offline`.

**Ordered by change frequency:**

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml ./
RUN mvn -B -ntp dependency:go-offline
COPY src/ ./src/
RUN mvn -B -ntp package
```

When only `src/...` changes:

- `COPY pom.xml` typically still hits cache.
- `RUN dependency:go-offline` can reuse the prior cached result.
- `COPY src` and `RUN package` run to reflect the new source.

When `pom.xml` changes, the dependency-declaration layer and downstream steps must be recomputed. **That is correct** because the dependency graph or build plugins may have changed.

Putting expensive commands first **does not mean trying to hide new dependencies from the build**: the dependency manifest remains an input to resolution, so editing the POM should invalidate cache.

### 2.3. Distinguish Cached Layers from Package Manager Caches

The two examples above lack a BuildKit cache mount. If `RUN dependency:go-offline` misses cache, Maven may need to download artifacts again. BuildKit `--mount=type=cache` can retain the Maven repository folder across executions:

```dockerfile
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp dependency:go-offline
```

- **Layer cache** **skips the entire command** when instruction and inputs match.
- **Cache mount** **saves network downloads** when the command must re-run by reusing data in the cache directory.
- Cache mounts **do not enter the final image** and must not be treated as immutable inputs published alongside the artifact.
- Cache mounts can be pruned, absent on fresh CI runners, or differ in state; the build must still succeed when the cache is empty.

That is why you should combine both **COPY ordering** and **cache mounts** instead of picking only one.

## 3. Preparing a Runnable Spring Boot Java 17 Project

Create a project named `cache-copy-demo` using Spring Boot 3.5.x, Java 17, Maven, Spring Web, and Spring Boot Starter Test. Layout:

```text
cache-copy-demo/
├── pom.xml
├── src/
│   ├── main/java/com/example/cache/
│   │   ├── CacheCopyApplication.java
│   │   └── GreetingController.java
│   └── test/java/com/example/cache/
│       └── GreetingControllerTest.java
├── Dockerfile.multi
├── Dockerfile.multi.dockerignore
├── Dockerfile.layers
└── Dockerfile.layers.dockerignore
```

Each Dockerfile has an **independent role**. `Dockerfile.multi` runs Maven inside the container. `Dockerfile.layers` requires an executable JAR already built on the host/CI, then splits it into image layers. Do not attempt to run both in a single command.

### 3.1. Complete Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cache-copy-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

`spring-boot-starter-parent` manages dependency/plugin versions; `spring-boot-maven-plugin` creates the executable archive during Maven packaging per parent conventions. There is no need to edit the main class manifest manually.

### 3.2. Spring Boot main class

File `src/main/java/com/example/cache/CacheCopyApplication.java`:

```java
package com.example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheCopyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheCopyApplication.class, args);
    }
}
```

### 3.3. REST controller

File `src/main/java/com/example/cache/GreetingController.java`:

```java
package com.example.cache;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public String hello() {
        return "cache-copy-ok";
    }
}
```

HTTP GET `/hello` returns the exact response body:

```text
cache-copy-ok
```

The response body **is not the full stdout** of Java/Spring Boot. Server logs still vary by version and environment.

### 3.4. JUnit test

File `src/test/java/com/example/cache/GreetingControllerTest.java`:

```java
package com.example.cache;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsGreeting() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("cache-copy-ok"));
    }
}
```

This example builds and tests through Maven because it needs Spring Boot and JUnit dependencies. It is not a program you can compile across the whole project using bare JDK `javac`. To test only the Java environment, `java -version` or a plain Java Standard Library program is a separate check and does not replace Spring Boot tests.

## 4. `Dockerfile.multi`: COPY Manifest First, Source Second

### 4.1. Complete Multi-Stage Maven Dockerfile

File `Dockerfile.multi`:

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: compile and package. Do not carry Maven/JDK build tools into runtime.
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

# Stable step: POM changes less often than source.
COPY pom.xml ./

# Pre-fetch dependencies and build plugins; cache mount retains Maven repo.
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp dependency:go-offline

# Frequently changing step:
COPY src/ ./src/

# Maven package still runs unit tests by default.
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp package

# Stage 2: image with only Java runtime and executable archive.
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/target/cache-copy-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Why is this order good?**

1. `FROM`/`WORKDIR` near the top are normally stable; if you update the base image digest or JDK tag, dependent layers rebuild — which is right since the runtime/build environment changed.
2. `COPY pom.xml ./` puts only the **dependency manifest** into the build stage. Maven dependency resolution does not need to inspect `src/` to figure out dependencies.
3. `RUN --mount=type=cache,... dependency:go-offline` uses a cache mount for Maven artifacts. When source changes while the POM stays identical, this step can hit **`CACHED`** and skip re-running.
4. `COPY src/ ./src/` brings application source in **after** the expensive, stable step.
5. `RUN mvn package` re-compiles, tests, and packages when source changes, as intended; do not skip tests to fake faster builds.
6. `COPY --from=build ...app.jar` brings only the built artifact into the **runtime stage**. The Maven executable and `/root/.m2` stay out of the final image.

**Limitation of `dependency:go-offline`:** this goal attempts to resolve plugins and dependencies for offline execution, yet does not guarantee 100% of dynamic artifacts needed by later goals are pre-fetched. A cache mount cuts down downloads if extra dependencies surface during `package`; the build still needs access to a trusted repository if anything is missing.

**Do not equate `CACHED` with "code unchecked."** When fresh source enters `COPY src`, Maven `package` runs on the new inputs, including unit tests in this example. Running `mvn package -DskipTests` for speed is changing your testing policy, **not** a benefit of `COPY` ordering.

### 4.2. Dockerfile-Specific Ignore File for the Maven Build

File `Dockerfile.multi.dockerignore` in **the same directory as `Dockerfile.multi`**:

```dockerignore
.git
.idea
.vscode
.gradle
build
target
*.log
.env
.env.*
```

Docker supports ignore files named after the Dockerfile: `Dockerfile.multi.dockerignore` applies when building with `-f Dockerfile.multi`, and takes precedence over root `.dockerignore` if both exist.

**Why exclude `target` from the build context?** The Maven stage in Section 4 compiles and creates a fresh JAR itself. An old `target/` folder on a developer machine need not be sent to the builder. If someone accidentally uses `COPY . .` and `target` is not ignored, outputs from an earlier run can trigger cache misses unrelated to source code.

Do not exclude `pom.xml` or `src/`: the Dockerfile needs both. In real Maven projects with `.mvn/` (extensions, `maven.config`), internal settings files, or multi-module layouts, include all files Maven needs before dependency resolution; **never drop a config that truly affects the build just to chase cache hits**.

### 4.3. Build and Run

From the project root:

```bash
docker build --progress=plain \
    -f Dockerfile.multi \
    -t cache-copy-demo:multi \
    .

docker run --rm -p 8080:8080 cache-copy-demo:multi
```

In another terminal:

```bash
curl -s http://localhost:8080/hello
```

Response body: `cache-copy-ok`. Backslash `\` line continuation is for Unix/macOS. On Windows PowerShell, enter `docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .` on one line, then invoke `docker run` and `curl.exe` appropriately.

**The trailing dot in `docker build ... .` is the build context**; `COPY pom.xml` looks in the context root, not in a directory set by `WORKDIR`. A running Docker Engine/BuildKit and network access for initial base image and Maven dependency downloads are required.

## 5. Measuring Cache Behavior of `Dockerfile.multi`

Follow in order rather than guessing from wall-clock time:

### 5.1. First Run: Populating Cache

```bash
docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .
```

Early uncached layers download dependencies and compile/test. BuildKit logs show `COPY pom.xml`, `RUN ...dependency:go-offline`, `COPY src`, and `RUN ...package`.

### 5.2. Second Run: No Source Changes

Re-run the exact same build command:

```bash
docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .
```

When cache is present and inputs are unchanged, multiple steps display **`CACHED`**. An abbreviated sample log (not fixed stdout):

```text
#7 [build 3/5] COPY pom.xml ./
#7 CACHED
#8 [build 4/5] RUN --mount=type=cache,... dependency:go-offline
#8 CACHED
#9 [build 5/5] COPY src/ ./src/
#9 CACHED
```

Do not expect exact step numbers to match the example: Docker/BuildKit assigns step numbers, log ordering, and platform details dynamically.

### 5.3. Third Run: Edit Only the Controller

In `GreetingController.java`, change the response body to a different string, and update the expected string in `GreetingControllerTest.java` so tests verify the new behavior. Rebuild:

```bash
docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .
```

Expected: **`COPY pom.xml` and `dependency:go-offline` can still hit `CACHED`**; `COPY src` and `RUN package` process the new code. After running the new image, the endpoint returns the new string. A build succeeding while the app returns the old string is **a bug to investigate**: an old container is still running, the image tag was not updated, or you are hitting the wrong port.

### 5.4. Fourth Run: Edit `pom.xml`

Intentionally add a needed dependency or change a version in the POM, then build. When `COPY pom.xml` sees updated content, the dependency prefetch layer must recompute for the new input, affecting downstream layers too. The Maven cache mount can still reduce downloads because most prior JARs stay in `/root/.m2/repository`.

**After the experiment, restore source and POM to their tested state.** Do not commit dummy dependencies just to see a cache miss. A good Dockerfile is not one that is "always `CACHED`," but one that invalidates **accurately when relevant inputs change**.

## 6. Image from a Prebuilt Executable JAR: The Simplest Approach

If CI already ran Maven/Gradle and produced an executable JAR **before** invoking Docker, you do not need to compile again inside the container. Minimal Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/cache-copy-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This is valid and suits small services; it uses a single layer holding the **entire** executable JAR. However, whenever source edits change the JAR, the whole `app.jar` blob changes and its layer may need to be rebuilt and pushed — even though `BOOT-INF/lib` inside barely changed.

**This is exactly why Spring Boot offers layered executable JARs.** We want stable dependencies in separate Docker layers so that when application classes change, dependency image layers can be reused.

**Not every** Spring Boot project has to use a layered image: if the JAR is small and CI/CD does not need pull/push optimization, the extraction and multi-stage Dockerfile maintenance cost may outweigh the benefit. Measure your actual workload.

## 7. Layered Executable JAR: Stable Dependency Layers First, Application Last

The Spring Boot Maven/Gradle Plugin provides a **layered JAR** mechanism. An executable JAR still holds:

```text
BOOT-INF/classes/
BOOT-INF/lib/
BOOT-INF/layers.idx
META-INF/MANIFEST.MF
```

`BOOT-INF/layers.idx` maps which contents belong to which layer. By default, layers are ordered as:

| Spring Boot Layer | Typical Contents | Change Frequency |
|---|---|---|
| `dependencies` | Non-SNAPSHOT third-party libraries | Usually low when locks/versions are managed well |
| `spring-boot-loader` | Boot Loader classes | Usually changes only when upgrading Spring Boot/packager |
| `snapshot-dependencies` | Dependencies with SNAPSHOT versions | Can change more often than stable deps |
| `application` | Application classes/resources and local module dependencies | Changes frequently on code edits |

The default order follows expected change frequency. It **does not guarantee** every SNAPSHOT dependency changes constantly or that the application layer is always small, yet it is a good convention to start with.

Key points:

1. `layers.idx` is **archive metadata**; copying a whole JAR into an image does not automatically create four Docker layers.
2. To take advantage of the four layers, the Dockerfile must **extract the layered JAR** and perform separate `COPY --from` instructions.
3. Spring Boot 3.5 uses `spring-boot-jarmode-tools` and `-Djarmode=tools` to list/extract; **do not** use `jarmode=layertools` from older Boot documentation.
4. The plugin generates a layered archive by default during packaging per Spring Boot 3.5 docs, unless you disable layering or exclude the tools dependency.
5. A JAR using `jarmode=tools` must not be a **fully executable archive with a prepended launch script**; if using the Spring Boot launch script, disable that setting for the extraction pipeline.

Inspect the JAR with the JDK:

```bash
jar tf target/cache-copy-demo-0.1.0-SNAPSHOT.jar
java -Djarmode=tools -jar target/cache-copy-demo-0.1.0-SNAPSHOT.jar list-layers
```

When tools mode and the index are present, `list-layers` outputs the layers understood by the tool. If you get `Unknown mode` or a missing command, check the Spring Boot version, artifact file, and whether tools/layers were excluded.

## 8. `Dockerfile.layers`: Copying Four Runtime Image Layers from Stable → Changing

### 8.1. Complete Dockerfile from a Prebuilt Maven JAR

Place `Dockerfile.layers` at the project root:

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: used solely to unpack the layered executable JAR.
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /workspace
COPY target/cache-copy-demo-0.1.0-SNAPSHOT.jar application.jar
RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

# Stage 2: runtime image with four separate COPY instructions.
FROM eclipse-temurin:17-jre
WORKDIR /application

# Least-frequently changing first:
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./

# More-frequently changing last:
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
```

**Why is the entrypoint `application.jar` rather than `org.springframework.boot.loader.launch.JarLauncher`?** In Spring Boot 3.5, `jarmode=tools extract --layers` produces a runtime structure with a **small `application.jar` as the entry point** and classes/JARs arranged in layer folders. That is the layout used in Spring Boot 3.5 Dockerfile documentation; do not graft `java -cp ... JarLauncher` from older Boot tutorials onto this example.

**Do not misunderstand the cache effect:** when code changes, **the original executable JAR file changes**, so `COPY ...application.jar` in the **extractor stage** and `RUN extract` usually re-run. Yet in the **final runtime stage**, the `dependencies`/`spring-boot-loader` layers can still contain identical bytes and be reused by BuildKit while `application` updates. Extraction-stage caching and runtime-layer data caching are two separate concerns.

### 8.2. Dedicated Ignore File for `Dockerfile.layers`

File `Dockerfile.layers.dockerignore`:

```dockerignore
.git
.idea
.vscode
.gradle
.mvn
src
build
*.log
.env
.env.*
target/*
!target/cache-copy-demo-0.1.0-SNAPSHOT.jar
```

`COPY target/cache-copy-demo-0.1.0-SNAPSHOT.jar` requires that JAR in the build context. **Do not keep the full `target` ignore rule** from `Dockerfile.multi` here. Dockerfile-specific ignore files let each build mode maintain the right context:

- `Dockerfile.multi.dockerignore`: excludes `target`, **keeps `pom.xml` and `src`**.
- `Dockerfile.layers.dockerignore`: **keeps only the exact built executable JAR** in `target`, excluding unneeded files.

A Dockerfile-specific ignore file **takes precedence** over root `.dockerignore` when named correctly in the same folder as the Dockerfile. If an older Docker version or build frontend does not support this mechanism properly, check the context and apply an appropriate ignore strategy before building.

### 8.3. Build and Run

First build the JAR on the host/CI with the Maven Wrapper:

```bash
./mvnw clean package
```

Then:

```bash
docker build --progress=plain \
    -f Dockerfile.layers \
    -t cache-copy-demo:layers \
    .

docker run --rm -p 8080:8080 cache-copy-demo:layers
```

In another terminal:

```bash
curl -s http://localhost:8080/hello
```

Expected response body is `cache-copy-ok`. Do not run `:multi` and `:layers` containers simultaneously bound to host port 8080; stop the old instance first or change the port mapping.

### 8.4. Why Can Layers Be Reused?

A Docker image is a stack of layers, so separating these steps yields:

```text
FROM JRE
  + dependencies/             [stable]
  + spring-boot-loader/       [stable]
  + snapshot-dependencies/    [may change]
  + application/              [changes frequently]
```

If you edit `GreetingController` while keeping the dependency set fixed, files in `dependencies` and `spring-boot-loader` stay unchanged, giving early Docker `COPY` steps a chance to show **`CACHED`**. Only the final `application` part updates, reducing layer push/pull bandwidth during deployment.

This **does not mean** the final image stays "unchanged" when the application changes: the new content digest/image ID still changes; you must publish and deploy the new image to run the new code.

## 9. When to Build Inside the Container vs Copy a JAR from CI?

| Choice | Pros | Trade-offs |
|---|---|---|
| `Dockerfile.multi`: Maven build inside Docker | Build JDK/Maven encapsulated in builder image; source-only context | Builder may fetch dependencies; compile/test inside Docker; whole JAR is one runtime layer |
| `Dockerfile.layers`: copy prebuilt JAR | CI cleanly separates compile/test from packaging; runtime layers reuse well | Must build JAR first; JAR changes re-trigger extractor stage |
| Combined Maven builder + `jarmode` extractor + layered runtime | Gets both build dependency cache and runtime layer reuse | Longer Dockerfile; must verify two cache tiers and artifact flow |
| Copy whole JAR from CI into one runtime image | Simplest, fewest moving parts | When JAR changes, whole-JAR layer changes; registry does not split dependencies |
| Cloud Native Buildpacks (`bootBuildImage`/`spring-boot:build-image`) | Buildpacks manage layering and image conventions automatically | Not a custom Dockerfile; requires understanding buildpack cache/builder stacks |

Decision prompts:

- Want to **build completely inside Docker from source**? Start with `Dockerfile.multi`.
- CI already builds, tests, and publishes a clear JAR? `Dockerfile.layers` is convenient and easy to trace back to the artifact.
- Large images due to stable dependencies while code changes continuously? Layered JARs are usually worth trying.
- CI prefers standardized buildpacks? Look at `bootBuildImage`/`spring-boot:build-image`, without assuming it uses your Dockerfile `COPY` layout.

## 10. Gradle: Equivalent `COPY` Strategy

If the project uses Gradle instead of Maven, the idea is identical:

```text
settings.gradle, build.gradle, gradle.properties, Gradle Wrapper
          -> resolve Gradle dependencies
src/
          -> test + bootJar
          -> final runtime image
```

### 10.1. Complete Groovy DSL Build Files

`settings.gradle`:

```groovy
rootProject.name = 'cache-copy-demo'
```

Example `gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx1g
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the **same three Java files** from Section 3 while choosing Gradle as the build tool. `gradlew`, `gradlew.bat`, and `gradle/wrapper/gradle-wrapper.{jar,properties}` must be valid files generated by Gradle/Initializr; creating empty placeholder files is not enough.

### 10.2. Multi-Stage `Dockerfile.gradle`

`Dockerfile.gradle` (builds from source, paired with a matching Dockerfile-specific ignore file):

```dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

# Build descriptors + Wrapper before source.
COPY gradlew settings.gradle build.gradle gradle.properties ./
COPY gradle/wrapper/ ./gradle/wrapper/
RUN chmod +x gradlew

# Download dependencies via Wrapper, keeping Gradle cache across builds.
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon dependencies --configuration runtimeClasspath

# Source changes often so copy after dependency step.
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon test bootJar

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/cache-copy-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

You need `Dockerfile.gradle.dockerignore` excluding at least `.git`, `build`, `.gradle`, `target`, editor files, logs, and secrets — while **not** excluding Gradle Wrapper, `settings.gradle`, `build.gradle`, `gradle.properties`, or `src`.

**Note:** `./gradlew dependencies --configuration runtimeClasspath` only resolves dependencies for **that configuration**; it does not guarantee all plugin artifacts or test dependencies are downloaded. Using a **cache mount** lets `test bootJar` keep reusing the Gradle user home cache. Do not run `RUN ./gradlew --offline` inside the builder when artifacts are incomplete; it will fail on a fresh builder.

If the build relies on `buildSrc`, a `gradle/libs.versions.toml` version catalog, multi-module `include`s, or convention plugins, include **all relevant configuration files** in early `COPY` steps. The minimal Dockerfile above is tailored to a single-module project matching this `build.gradle`.

### 10.3. Build and Runtime

```bash
docker build --progress=plain -f Dockerfile.gradle \
    -t cache-copy-demo:gradle .
docker run --rm -p 8080:8080 cache-copy-demo:gradle
```

In PowerShell or CMD, enter commands on a single line. If Gradle outputs a differently named JAR due to custom `archiveFileName`, classifier, or `version`, update `COPY --from` to match the actual output. **Do not** accidentally grab `-plain.jar`; you need the executable JAR produced by `bootJar`.

Layered runtime with Gradle still uses `-Djarmode=tools` after `bootJar` creates the file. For a Gradle project built outside Docker, replace `target/...` in `Dockerfile.layers` with `build/libs/cache-copy-demo-0.1.0-SNAPSHOT.jar` and update the ignore file to permit that exact JAR in the context.

## 11. Using Multi-Project Gradle or Maven Reactor Builds

In multi-module repositories, copying only the root `pom.xml` before resolving dependencies may **not be enough**: the Maven reactor usually needs child module POMs during dependency resolution. Similarly, Gradle has `settings.gradle`, version catalogs, root, and subproject build scripts.

### 11.1. Maven Multi-Module: Copy Each Module POM Before Source

Example structure:

```text
platform/
├── pom.xml
├── shared-core/pom.xml
├── api-app/pom.xml
├── shared-core/src/
└── api-app/src/
```

Builder Dockerfile fragment:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

# Less-frequently changing config files first.
COPY pom.xml ./
COPY shared-core/pom.xml shared-core/pom.xml
COPY api-app/pom.xml api-app/pom.xml

# Test this goal against your project's reactor and plugins.
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp dependency:go-offline

# Copy sources afterward.
COPY shared-core/src/ shared-core/src/
COPY api-app/src/ api-app/src/
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp -pl :api-app -am package
```

This is a **model fragment**: running it requires a real parent POM declaring `<modules>`, child POMs, dependencies, and sources. Maven `dependency:go-offline` in a reactor with many plugins may need unbuilt internal artifacts; verify the command rather than assuming every multi-module repo supports offline resolution in a single goal.

### 11.2. Gradle Multi-Project: Do Not Omit Configuration Inputs

In Gradle, files affecting the dependency graph include:

- `settings.gradle` or `settings.gradle.kts`.
- Root and subproject `build.gradle` or `build.gradle.kts`.
- `gradle.properties`.
- `gradle/libs.versions.toml` (version catalog).
- `buildSrc`/`build-logic` convention plugins and needed metadata.
- `gradle/wrapper` and wrapper scripts, when building with the wrapper.
- Dependency lockfiles or verification metadata.

These must be placed into `COPY` steps before dependency resolution if goals/tasks read them. Copy required configuration **explicitly** so source edits do not invalidate dependency resolution, without dropping config files that genuinely affect the build.

When multiple modules are packaged together, Spring Boot's `application` image layer can include local module dependencies. If a local library changes, the `application` layer can change even while the external `dependencies` layer stays cached. That is expected behavior.

## 12. `.dockerignore`: Shrinking Context and Avoiding Unwanted Cache Misses

The Docker build context is the set of files the client sends to the builder from the path at the end of `docker build ... .`. By default, it can include `.git/`, `target/`, `build/`, IDE settings, test reports, logs, local secrets, and backup files. Any change in those files can cause invalidation if the Dockerfile runs `COPY . .`, and swells context size.

**Example root `.dockerignore` when building Maven from source:**

```dockerignore
.git
.idea
.vscode
target
build
.gradle
*.log
.env
.env.*
.DS_Store
```

**Do not drop genuinely needed inputs.** If a Dockerfile executes `COPY target/app.jar`, a `target` rule makes Docker fail to find the JAR. Hence Dockerfile-specific ignore files are useful when maintaining both `Dockerfile.multi` and `Dockerfile.layers`.

**Negation rule note:** Docker `.dockerignore` supports `!pattern` to re-include a file after a broad exclusion, and **the last matching rule** wins. For example:

```dockerignore
target/*
!target/cache-copy-demo-0.1.0-SNAPSHOT.jar
```

This retains **only the exact artifact** to copy, omitting `target/classes`, test reports, and old JARs. Before applying to a real pipeline, inspect the build context with `docker build --progress=plain` or test `COPY` on the exact file to catch bad patterns.

**Security:** `.dockerignore` is a safeguard against accidentally adding secrets to the context, **not a replacement** for a secret manager. Never commit `.env` files with credentials, and never design a Dockerfile that copies private keys into the image and "deletes them in a later `RUN`" — earlier layers can still retain sensitive bytes in build cache and history.

## 13. BuildKit Cache Mounts: Keeping Dependency Downloads Efficient

### 13.1. Maven Local Repository

```dockerfile
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp package
```

`/root/.m2/repository` fits the Maven image running as `root` in our example. If your builder runs as a non-root user, uses a different `MAVEN_CONFIG`, or sets `-Dmaven.repo.local`, **adjust `target`** to match the Maven repository path used by the process; do not hardcode the root path out of habit when the tool reads elsewhere.

Docker BuildKit cache mounts are stored locally according to builder/GC policy; they do not place package-manager artifacts into the runtime image. When a command re-runs because source changed, Maven can reuse dependencies already cached in the mount.

### 13.2. Gradle User Home

```dockerfile
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon test bootJar
```

Mounting `/root/.gradle` can preserve the Gradle distribution, downloaded modules, plugin JARs, and metadata caches. When a project uses user `gradle` or a custom `GRADLE_USER_HOME`, adjust the target and ownership; do not hit `permission denied` and blame dependency resolution.

**Correctness principle:** both Maven and Gradle builds must still succeed when the cache mount is empty, provided repositories are reachable. Never rely on a cache mount holding undeclared local files as the sole source of truth.

### 13.3. Cache Mounts Do Not Replace `COPY` Ordering

If you put `COPY . .` ahead of dependency resolution, a cache mount may cut down network downloads, yet the Maven/Gradle goal still gets re-triggered repeatedly. Splitting `COPY pom.xml` before `COPY src` lets Docker **skip the resolution step entirely** when only source changes; cache mounts act as a second line of defense when the task must re-run.

## 14. Caching on Fresh CI Runners: Registry Cache and Safety

On a laptop, BuildKit keeps a local build cache; on ephemeral CI runners, each job can start with an empty cache. To reuse cache across runners, use Buildx cache exporters/importers.

**Illustrative syntax for an organization registry** (replace namespace and registry with an account holding real permissions):

```bash
docker buildx build --push \
  -f Dockerfile.multi \
  -t registry.example.com/team/cache-copy-demo:latest \
  --cache-from type=registry,ref=registry.example.com/team/cache-copy-demo:buildcache \
  --cache-to type=registry,ref=registry.example.com/team/cache-copy-demo:buildcache,mode=max \
  .
```

`registry.example.com` is a documentation placeholder domain, **not a pushable registry without configuration**. Besides credentials, ensure your builder driver/cache backend supports the `registry` exporter. With the default Docker driver, some registry backends require the containerd image store enabled; a Buildx driver is another option.

- `mode=max` exports cache even for intermediate stages, which helps Maven builders.
- Cache entries can overwrite one another if multiple branches push to one `buildcache` tag; define a cache scoping policy.
- Cache does not guarantee the newest image, nor does it replace base image vulnerability scanning or dependency verification.
- Exported cache can hold data from build steps; **never pass secrets into `ARG`, `COPY`, or `RUN` commands** that could end up pushed to a public cache registry.
- Use `RUN --mount=type=secret` and proper credential handling when tokens are needed; secret mounts do not enter the final image by default.
- Maven/Gradle **cache mounts** and **exported layer caches** are two different things. Do not assume data inside `--mount=type=cache` gets exported to the registry via `--cache-to`.

If CI only needs fast builds on a single runner, first fix `COPY` ordering and add builder cache mounts; do not stand up remote-cache infrastructure without evidence that build cost justifies it.

## 15. How to Read Logs to Evaluate a `COPY` Improvement

Example BuildKit statuses:

| Log Line | Meaning | How to Interpret |
|---|---|---|
| `CACHED` on `COPY pom.xml` | Manifest/context input matches cache | This step was reused |
| `CACHED` on `RUN dependency:go-offline` | Builder skipped re-running resolution | Build-stage cache goal achieved on this run |
| `DONE 9.2s` on `RUN mvn package` | `package` command executed | Expected when Java source just changed |
| `CACHED` on `COPY --from=extractor .../dependencies` | Runtime dependency layer reused | Good when code changed while dependency bytes stayed identical |
| `DONE ...` on `COPY .../application` | Application layer changed/rebuilt | Normal when source or resources changed |
| `FROM-CACHE` in Gradle logs | **Gradle Build Cache**, not a Docker image layer | Do not confuse with BuildKit `CACHED` |
| `UP-TO-DATE` from Gradle | Gradle task output still current | Does not confirm Docker layer cache |
| Maven log `Downloading from ...` | Maven had to fetch artifact | Likely empty cache mount or updated manifest |
| `COPY failed: file not found` | File absent from context or ignored | Check context, filename, `.dockerignore`, and build outputs |

An optimization pays off when **routine source edits** neither trigger expensive dependency steps nor force Docker to re-upload all runtime dependencies. Total build time, however, still depends on compiler/tests, base image pulls, CPU, network, registry, and cache eviction.

Never benchmark from the single build right after editing the Dockerfile: **changing the Dockerfile itself invalidates cache**. Warm the cache for the new Dockerfile first, then compare equivalent source-change scenarios.

## 16. Using `COPY --link`: Advanced Option, Not Mandatory

Docker BuildKit provides `COPY --link`, allowing copied layers to stay more independent of earlier layers in certain cases. In a layered runtime image, when base layers update, this can help reuse/rebase copied layers whose contents did not change.

Advanced snippet example:

```dockerfile
# syntax=docker/dockerfile:1
COPY --link --from=extractor /workspace/extracted/dependencies/ ./
```

**Condition:** `COPY --link` cannot rely on reading contents or symlinks from prior destination layers the way standard `COPY` does. If destination paths involve symlinks or special merge semantics, test carefully. The syntax requires Dockerfile frontend/BuildKit support.

**Do not apply it mechanically** in place of the fundamentals: ordering `COPY` by change frequency, keeping the context small, and splitting Spring Boot layers deliver the primary gains. `--link` is a secondary optimization once build infrastructure supports it and measurements justify it.

## 17. Common Failures and Remedies

| Problem | Common Cause | Remedy |
|---|---|---|
| Editing one Java file makes Maven re-download everything | `COPY . .` before dependency resolution, missing cache mount | `COPY pom.xml` first, `COPY src` after; add BuildKit cache mount |
| Docker build always misses on `COPY . .` | `.git`, logs, `target`, editor files, or outputs changed | Use `.dockerignore` matched to the build context |
| `Dockerfile.multi` cannot find `pom.xml` | Building from wrong directory or `.` is not project root | Run from root, verify `docker build ... .` |
| `Dockerfile.layers` cannot find JAR | Haven't run Maven package, different filename, or ignored by `target` rule | Build JAR first; allow the exact file in Dockerfile-specific ignore |
| `layers.idx` exists yet image has one `app.jar` layer | Copied whole executable JAR without extracting | Run `jarmode=tools extract --layers` and four `COPY --from`s |
| `Unsupported jarmode` | Archive lacks tools JAR, legacy mode name, or wrong JAR type | Check Boot version, tools setting, manifest, and layers |
| Tools extraction fails | Fully executable archive with prepended launch script | Disable launch script for artifacts using `jarmode` tools |
| `application.jar not found` at runtime | Forgot `application` layer or wrong destination | Match extraction stage paths to Spring Boot 3.5 Dockerfiles docs |
| Runtime reports missing dependencies | Omitted `dependencies` or `snapshot-dependencies` layer; missing build artifacts | Copy all four layers, inspect original JAR |
| `jar tf` shows plain JAR | Picked `jar`/`plain.jar` instead of `bootJar`/repackage | Select real executable archive, check `BOOT-INF/layers.idx` |
| Edited Maven POM yet dependency step stays `CACHED` | Dockerfile didn't copy edited file or built another context | Check actual `COPY`, cache logs, and source paths |
| Image keeps running old version after builds | Docker copied stale artifact, old tag/container still running | Remove old container, rebuild JAR/image from exact artifact |
| Maven `go-offline` still accesses network in `package` | Some plugin artifacts resolve at goal execution time | Expect that behavior, use cache mount and proper plugin repos |
| Gradle wrapper fails to run | Missing wrapper JAR/scripts or `chmod`, Java/Gradle mismatch | Commit valid wrapper, match JDK/Wrapper versions |
| Cache mount permission denied | Target points to wrong user home or insufficient owner permissions | Match `MAVEN_CONFIG`/`GRADLE_USER_HOME` and UID/GID |
| Low CI build cache hit rate | Ephemeral runner drops cache, mutable base/tag, dynamic plugin versions | Use external cache appropriately, pin dependencies and base images |
| Docker cache hides security updates | Base image tag not refreshed, package manager `RUN` cached | Schedule `--pull`/rebuilds and image scans; don't force cache hits forever |
| Secrets appear in image layer | `COPY` or `ARG` passed credential, followed by `RUN rm` | Never copy secrets; use BuildKit secret mounts, rotate leaked credentials |

**When troubleshooting, inspect actual inputs before reaching for `docker build --no-cache`.** `--no-cache` bypasses the layer cache and helps diagnose issues, yet it **is not** an optimization fix; running it routinely defeats the value of a well-ordered Dockerfile.

## 18. Performance, Security, and Reproducibility

### 18.1. Balancing Cache Reuse and Patches

Keeping dependency and base layers long-term lowers rebuild/push times, yet you **must never** keep reusing a vulnerable base image forever. When JDK/OS patches arrive, CI should pull updated base images per policy, rebuild, run tests, and scan. Pinning image digests helps reproducibility alongside a scheduled digest-update workflow.

Docker `RUN apt-get update` can stay cached even after upstream package repositories change, because the builder does not inspect every remote URL when evaluating layer caches. Never abuse cache to skip OS package patching.

### 18.2. Keep Secrets Out of Images and Caches

- Store repository credentials in CI secret storage and pass via BuildKit `--secret`; never commit `settings.xml`/`gradle.properties` containing tokens into source.
- Never `COPY` `.env` or private SSH keys into a stage and delete them with `RUN rm`; bytes can still survive in layers/cache.
- Never write credentials into `ARG`/`ENV` that end up in image metadata/history.
- Restrict access to remote cache registries and avoid exporting cache from trusted builds into untrusted namespaces.
- Build caching is a performance optimization, **not a supply-chain verification mechanism**. Verify provenance, SBOMs, image scans, and artifact digests separately.

### 18.3. Run with Least Privilege

The illustrative Dockerfiles focus on caching. For production, create/select a non-root user, set `USER` properly, configure permissions, writable temp directories, health checks, and resource limits. Do not merely append `USER 10001` at the end of an arbitrary Dockerfile without verifying read permissions on the JAR/runtime dirs and write permissions for logs/tmp.

### 18.4. Mind the Layer Count

Each `COPY` adds a metadata/content layer, yet more layers are not automatically better. **The four Spring Boot layers make sense** because they group dependencies and classes by change frequency; creating thousands of `COPY` steps for individual `.class` files has no real benefit. Aim for **reusable, maintainable layers**, not maximizing instruction count.

## 19. Acceptance Checklist: Is `COPY` Ordered Correctly?

- [ ] Dockerfile uses a base image/JDK compatible with Spring Boot and patched for security.
- [ ] Stable files governing dependency/plugin versions are copied **before** `src`.
- [ ] Dependency-resolution commands depend only on the build descriptors actually needed.
- [ ] `COPY src` comes **after** expensive dependency resolution.
- [ ] BuildKit cache mounts for Maven/Gradle are not mistaken for Docker image layers.
- [ ] Build still succeeds with an empty cache mount when repositories are reachable.
- [ ] `.dockerignore` excludes unneeded Git metadata, stale outputs, logs, and local secrets.
- [ ] If building from a prebuilt JAR: the JAR to `COPY` is not ignored.
- [ ] If using a layered JAR: artifact has `BOOT-INF/layers.idx` and supports `-Djarmode=tools`.
- [ ] Four `COPY --from` instructions in the runtime image progress from `dependencies` to `application`.
- [ ] `ENTRYPOINT` launches the right extracted `application.jar` for Spring Boot 3.5.
- [ ] Running twice with no source changes shows `CACHED` steps when builder cache is warm.
- [ ] Editing Java source rebuilds the app layer while reusing dependency layers when inputs match.
- [ ] Editing the dependency manifest invalidates the relevant steps properly.
- [ ] JUnit tests still run; endpoints in the new image return new code rather than hitting a stale container.
- [ ] Ephemeral CI has a cache-persistence strategy if real build times warrant it.
- [ ] `--no-cache` is not used as a default, and security patching is not sacrificed for cache hits.
- [ ] Secrets are supplied safely without being baked into layers or exported build caches.

### Official Documentation Sources

- [Docker — Optimize Cache Usage in Builds](https://docs.docker.com/build/cache/optimize/)
- [Docker — Build Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Docker — Build Context and Dockerfile-specific Ignore Files](https://docs.docker.com/build/concepts/context/)
- [Docker — Dockerfile Reference: COPY, --link, cache mounts](https://docs.docker.com/reference/dockerfile)
- [Docker — Cache Storage Backends for BuildKit/Buildx](https://docs.docker.com/build/cache/backends/)
- [Spring Boot 3.5 — Dockerfiles and jarmode=tools](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.5 — Maven Packaging Layered JARs](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Apache Maven — dependency:go-offline goal](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html)
- [Docker Official Maven Image](https://hub.docker.com/_/maven)
- [Docker Official Eclipse Temurin Image](https://hub.docker.com/_/eclipse-temurin)

**Key takeaway:** Docker layer caching shines when you put **least-changing inputs first and most-frequently changing inputs last**. For Spring Boot, in the **builder stage**, copy Maven/Gradle descriptors before `src`; in the **runtime stage**, order Spring Boot extracted layers as `dependencies → spring-boot-loader → snapshot-dependencies → application`. Combine `.dockerignore`, cache mounts, and code/POM change experiments to prove cache reuse **in the right places**, rather than just seeing `CACHED` in build output.