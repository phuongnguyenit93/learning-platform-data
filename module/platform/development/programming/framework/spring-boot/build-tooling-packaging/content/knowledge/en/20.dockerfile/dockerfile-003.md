# Organizing Multi-Stage Builds and Optimizing Build Context with .dockerignore

## 1. Lesson Goals

When packaging a Spring Boot application into a Docker image, two distinct concerns are easily confused:

1. **Multi-stage builds** determine **which tools and files appear in each image-building stage**, specifically keeping the JDK, Maven/Gradle caches, source code, and compiler tools out of the runtime image.
2. **`.dockerignore`** determines **which files from the build machine enter the Docker build context**, reducing the data processed/transferred to the builder, keeping unnecessary files out, and lowering the risk of cache invalidation from unrelated changes.

These two techniques complement each other but **do not replace each other**. A Dockerfile that already has two `FROM` statements can still accidentally send gigabytes of data into the build context if ignore rules are poorly configured. Conversely, `.dockerignore` can be very strict while the runtime image still bloats if the entire JDK, source code, and build tools are placed into the final stage.

After this lesson, you will be able to:

- Explain and control the build context via the final argument to `docker build`, without confusing it with `WORKDIR`.
- Write a sensible `.dockerignore` for Spring Boot Gradle/Maven without accidentally excluding the wrapper, POM, build scripts, or `src`.
- Organize a Dockerfile into `build`, `extract` (when needed), and `runtime` stages, using `COPY --from` only to transfer the needed artifact into the final image.
- Create a runnable Spring Boot Java 17 application, build an executable `bootJar` or Maven `repackage` inside a container, and run the final image.
- Leverage Docker layer caching, BuildKit cache mounts for Gradle/Maven, and, when appropriate, Spring Boot layered JARs.
- Distinguish optimizing **build context**, **build time**, **final image size**, **image layers**, **runtime security**, and **reproducibility**.
- Troubleshoot common issues: `COPY failed`, missing Gradle wrapper, wrong runtime JAR `-plain.jar`, build cache misses, Dockerfile-specific ignore precedence, secret leaks, and multi-module paths.

**Example baseline:** Java 17 and Spring Boot 3.3.13 for consistent syntax. This is an illustrative version, not a claim of being the latest release. Current Docker documentation may evolve; your project's actual Docker Engine/BuildKit, Gradle wrapper, and plugins are the source of truth when deploying.

## 2. Visualizing the Flow from Host to Container

~~~text
Project directory on host
    |
    | docker build -t boot-web:gradle .
    |                            ^
    |                      build context = .
    |
    +-- .dockerignore filters files entering context
    |
    v
Docker / BuildKit builder
    |
    +-- FROM JDK image AS build
    |     | COPY build scripts / wrapper / src
    |     | RUN gradle or maven test + package
    |     v
    |   app.jar in build stage filesystem
    |
    +-- FROM JRE image AS runtime
          | COPY --from=build .../app.jar /app/app.jar
          | non-root USER
          | ENTRYPOINT java -jar ...
          v
      Final image serving the application
~~~

Key points:

- `COPY gradlew` or `COPY src` reads from the **build context**, with `.dockerignore` already applied.
- `COPY --from=build /workspace/build/libs/app.jar ...` reads from the **build stage's filesystem**, **not** from the host build context.
- There is no need to send the developer machine's `build/` directory into the context when the builder stage itself creates a fresh Boot JAR.
- Only what the final stage inherits from its base image and the instructions inside the final stage becomes the runtime image's filesystem. The JDK, Gradle cache, and `src` in the build stage do not automatically enter the final image.

This is why multi-stage builds fit Java/Spring Boot applications so well: you need a **JDK + build tool** to compile, yet typically only a **compatible JRE + executable artifact** to run.

## 3. What Is the "Build Context" Really?

When you type:

~~~bash
docker build -t boot-web:gradle .
~~~

the trailing `.` selects the **current directory as the filesystem build context**. Given a Dockerfile:

~~~dockerfile
WORKDIR /workspace
COPY src/ src/
~~~

Docker reads `src/` **relative to the build context**, then copies it to `/workspace/src` inside the current stage. `WORKDIR` does not decide which host directory is sent to Docker.

These two commands can use **two different contexts**:

~~~bash
docker build -f Dockerfile .
docker build -f docker/Dockerfile .
~~~

Both use `.` as the context; only the Dockerfile path differs. By contrast:

~~~bash
docker build -f docker/Dockerfile docker/
~~~

uses `docker/` as the context. If `src/` and `build.gradle` live at the project root outside `docker/`, `COPY src/ src/` will fail to find the source. You cannot use `COPY ../src` to escape the context as a workaround; Docker restricts source paths to the selected context.

### 3.1. Why Does a Large Context Hurt?

A Java repository may contain:

~~~text
.git/                       Git history can be huge
.gradle/                    project Gradle metadata/cache
build/                      compiled classes, reports, old JARs
target/                     Maven outputs
.idea/, .vscode/            IDE data
node_modules/               frontend dependencies
logs/, reports/, tmp/       files unneeded for the build
.env, *.pem                 sensitive config/keys
src/                        application source code
gradle/wrapper/             Gradle wrapper needed for container build
build.gradle(.kts), pom.xml required build configuration
~~~

If the context includes everything, the builder may have to process and transfer large amounts of data, especially when building remotely. In a Dockerfile using `COPY . .`, changing an unrelated file (logs, `.git`, build artifacts) can also **invalidate the cache** of `COPY` and all subsequent steps.

Modern BuildKit can skip transferring files unused by instructions or transfer them on demand; however, you should still **narrow the context with `.dockerignore`** to reduce accidental copy risks and sources of variability. Do not infer context size solely from total project disk size; check the `transferring context` output during builds.

## 4. What Does `.dockerignore` Filter and When?

Docker looks for `.dockerignore` at the **root of the build context**. Files/paths matching the ignore rules are excluded from the context before the builder uses them as sources for `COPY`/`ADD`.

Example at the project root:

~~~text
boot-web/
├── .dockerignore
├── Dockerfile
├── settings.gradle
├── build.gradle
├── gradlew
├── gradle/wrapper/
├── src/
├── build/
└── .git/
~~~

Recommended `.dockerignore` contents for a **Spring Boot project whose builder stage compiles from source**:

~~~dockerignore
# Version control and IDE configuration
.git
.gitignore
.idea
.vscode
*.iml

# Gradle/Maven outputs & local state
.gradle
**/.gradle
build
**/build
target
**/target

# Local cache and frontend dependencies if unused in the image
node_modules
**/node_modules
logs
**/logs
tmp
**/tmp
*.log
*.tmp
.DS_Store

# Secrets and developer-machine data: do not send to context
.env
.env.*
**/*.pem
**/*.key
**/*.p12
**/*.jks
~~~

**Important:** this ignore file **does not exclude** `gradlew`, `gradle/wrapper/`, `settings.gradle`, `build.gradle`, or `src`. If the Dockerfile requires the wrapper, make sure `gradle/wrapper/gradle-wrapper.jar` and `gradle-wrapper.properties` actually exist in the context.

In a project using a Maven builder image with Maven preinstalled, the required files typically include only `pom.xml`, `src`, and other POMs/configs in the repository. If building via Maven wrapper `./mvnw`, keep `mvnw` and `.mvn/wrapper/`; do not add `.mvn` to the ignore file when the Dockerfile needs it.

**This is an example for the sample repository, not an ignore list to apply blindly to every app.** If a project runs frontend/build scripts inside `node_modules`, adjust your dependency strategy; if a public SSL cert or test fixture is legitimately read during compile/test, do not exclude it unconditionally. Secrets must be supplied via a secret manager/build secret mechanism when needed, never relying solely on an ignore file.

### 4.1. `.dockerignore` Is Not `.gitignore`

`.gitignore` controls Git tracking, whereas `.dockerignore` controls Docker's build context. Docker does not automatically inherit Git ignore rules when using a local filesystem context. A file ignored by Git can still be sent into the Docker context if `.dockerignore` does not exclude it and the builder accesses it.

For example, `build/` may be in `.gitignore`, yet if a Dockerfile runs `COPY . .` with no `.dockerignore`, Docker can still send and copy build artifacts.

### 4.2. Important Pattern Syntax

Docker's `.dockerignore` has its own matching rules based on filepath matching:

- Each line is a pattern; a line starting with `#` in column 1 is a comment.
- Leading/trailing `/` slashes in paths are typically normalized during matching.
- `*` matches filename/path segments per matcher rules; `?` matches a single character.
- `**` is Docker's extended wildcard, matching **0 or more directory levels**.
- The `!` prefix creates an exception to re-include an ignored file/path.
- **The last matching rule** can decide whether a file is included or excluded; order matters.
- The `.` pattern is a special case ignored by Docker for historical reasons.

Example:

~~~dockerignore
*.md
!README.md
README-secret.md
~~~

Intent: exclude root Markdown files except `README.md`, then explicitly exclude `README-secret.md` even if matched by another include condition. Do not assume this syntax is 100% identical to `.gitignore`: Docker has its own matcher and rule precedence.

An example of **exception ordering**:

~~~dockerignore
*.md
!README*.md
README-internal.md
~~~

With this ordering, `README-internal.md` is excluded because the last line matches. Moving `!README*.md` to the bottom can include it again. In deeply nested repositories, test rules against the real directory tree instead of guessing from shell globs.

### 4.3. Do Not Exclude a Parent Directory and Expect Child Files to Return

If you write:

~~~dockerignore
gradle
!gradle/wrapper/gradle-wrapper.jar
~~~

and the Dockerfile runs `COPY gradle/wrapper/ ...`, the result may not work as intended because the parent directory was excluded. For the Gradle wrapper, the simplest approach is **not ignoring `gradle/`**; only exclude local state `.gradle/` (with the leading dot), leaving `gradle/wrapper/` intact.

If your organization uses a `**` exclude-all allowlist and re-includes individual files, you must include both **directory ancestors** and required paths, and test on the real tree. Dropping build inputs just to "shrink the context" will either fail the Docker build or, worse, succeed while missing a needed resource.

### 4.4. Dockerfile-Specific Ignore Files When Multiple Dockerfiles Exist

Docker supports dedicated ignore files placed in **the same directory as the Dockerfile**, named like:

~~~text
docker/
├── build.Dockerfile
├── build.Dockerfile.dockerignore
├── test.Dockerfile
└── test.Dockerfile.dockerignore
~~~

When running:

~~~bash
docker build -f docker/build.Dockerfile .
docker build -f docker/test.Dockerfile .
~~~

the Dockerfile-named ignore files take precedence over `.dockerignore` at the context root. **File-specific ignore files have precedence**; do not assume they automatically merge rules with root `.dockerignore`. Always read the active ignore file for each command.

Practical scenario: a runtime Dockerfile only needs the built JAR, while a test Dockerfile needs sources, test fixtures, and the wrapper. The two builds have different input requirements and can use two different ignore sets. Still, always determine the context root from the final argument to `docker build`, not from the Dockerfile's location.

### 4.5. You Can Exclude Dockerfile and .dockerignore from COPY, Yet Docker Still Reads Them

Docker docs allow listing `Dockerfile` and `.dockerignore` in ignore rules. Those files are still sent as needed for the builder to execute the build, **but they cannot be used as sources in `COPY`/`ADD` or context bind mounts** in the usual way once ignored.

Thus there is no need to copy the Dockerfile into the final image. If a pipeline truly needs the Dockerfile as an audit artifact, handle it outside the Docker runtime layer or design an appropriate ignore/context setup.

## 5. Hands-On Spring Boot Java 17 Project

We create a small REST API listening on container port 8080 and returning the body:

~~~text
hello-from-container
~~~

The exact same Java source is used for **both Gradle and Maven**; only the build scripts and Dockerfile change.

Gradle project structure:

~~~text
boot-web/
├── .dockerignore
├── Dockerfile
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   └── java/com/example/docker/
    │       ├── DockerDemoApplication.java
    │       └── HelloController.java
    └── test/
        └── java/com/example/docker/
            └── HelloControllerTest.java
~~~

The project can be generated via Spring Initializr or by initializing the wrapper with Gradle. **Having only `build.gradle` does not generate `gradlew`**; if the wrapper is missing, generate it using a compatible installed Gradle or copy from an approved repository template.

### 5.1. Application main class

File `src/main/java/com/example/docker/DockerDemoApplication.java`:

~~~java
package com.example.docker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DockerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DockerDemoApplication.class, args);
    }
}
~~~

### 5.2. Controller

File `src/main/java/com/example/docker/HelloController.java`:

~~~java
package com.example.docker;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello-from-container";
    }
}
~~~

### 5.3. JUnit test for the builder stage to verify

File `src/test/java/com/example/docker/HelloControllerTest.java`:

~~~java
package com.example.docker;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HelloControllerTest {

    @Test
    void returnsExpectedResponse() {
        HelloController controller = new HelloController();
        assertEquals("hello-from-container", controller.hello());
    }
}
~~~

This test invokes the Java controller directly without starting an HTTP server; the goal is a simple, **runnable** JUnit test independent of network or test databases. Once the image runs, add an HTTP smoke test to prove the server actually serves requests.

## 6. Gradle Groovy DSL Configuration Used in the Dockerfile

File `settings.gradle`:

~~~groovy
rootProject.name = 'boot-web'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

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

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'app.jar'
}
~~~

Why set `archiveFileName = 'app.jar'`? So the Dockerfile copies **one deterministic output path**:

~~~text
/workspace/build/libs/app.jar
~~~

Do not use `COPY --from=build /workspace/build/libs/*.jar /app/app.jar` when the directory can contain `-plain.jar` or multiple classifiers/versions. A fixed output name ensures the image grabs the exact executable Boot archive.

**Warning:** `bootJar` and `jar` are different. `bootJar` packages runtime dependencies in the Spring Boot executable layout. `jar` usually builds a plain JAR; `java -jar` on a plain JAR fails due to missing loader/dependencies. The Dockerfile must use the `bootJar` artifact.

### 6.1. Kotlin DSL if the project uses `.gradle.kts`

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "boot-web"
~~~

Equivalent `build.gradle.kts`:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app.jar")
}
~~~

If using Kotlin DSL, the Dockerfile needs `COPY settings.gradle.kts build.gradle.kts ./` instead of the Groovy files. **Do not keep two `build.gradle` files of different DSLs and expect both to apply sequentially.**

Do not treat the Java 17 toolchain config as proof that the runtime image has Java: the **builder stage** has JDK 17 to compile, while the **final stage** needs its own suitable JRE/JDK to run the artifact.

## 7. Multi-Stage Dockerfile with Gradle — Runnable Version

At the `boot-web` root, use the following `Dockerfile` together with the Groovy DSL from Section 6, `.dockerignore` from Section 4, and Java sources from Section 5:

~~~dockerfile
# syntax=docker/dockerfile:1

# Stage 1: JDK + Gradle wrapper + source => executable Boot JAR
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

# Copy only files needed for Gradle to recognize the project and download wrapper/plugins
COPY gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle build.gradle ./
RUN chmod +x gradlew

# Warm configuration/plugin resolution; may not download all runtime JARs yet
RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon help

# Source changes more often than build scripts
COPY src/ src/

# Build inside container. BuildKit cache mount does not enter final image.
RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon test bootJar

# Stage 2: JRE + runtime artifact only
FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=build /workspace/build/libs/app.jar /app/app.jar

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is a **complete Dockerfile** for the Groovy Gradle project defined above. It relies on Docker BuildKit for `RUN --mount=type=cache`. On modern Docker, BuildKit is typically the default builder; if an older environment does not support cache mounts, enable BuildKit or omit `--mount` and use a regular `RUN`, without inventing non-existent flags.

### 7.1. Reading the Dockerfile Stage by Stage

**`FROM eclipse-temurin:17-jdk AS build`:** creates a builder stage with JDK 17, needed for Gradle and `javac`. This base image has a larger size and more tools than a JRE; because it is an intermediate stage, it does not become the final runtime image when we only copy the JAR.

**`WORKDIR /workspace`:** sets the working directory inside the stage without changing the host build context.

**`COPY gradlew` and `COPY gradle/wrapper/`:** brings the Gradle wrapper shell script and wrapper JAR/properties into the builder. The Dockerfile does not need `gradlew.bat` to run on the Linux stage.

**`COPY settings.gradle build.gradle ./`:** informs Gradle of the project name, plugin versions, repositories, and dependencies. Because this runs before `COPY src`, when only Java code changes Docker can reuse the wrapper/configuration layer instead of redoing setup from scratch.

**`RUN chmod +x gradlew`:** ensures the wrapper has execute permission in the Linux builder; this permission does not carry over to the runtime JAR.

**`RUN --mount=type=cache,target=/root/.gradle,sharing=locked ... help`:** initializes/configures the Gradle wrapper and plugins; the cache mount persists Gradle User Home data across builds on the same builder. Running `help` **does not guarantee resolving and downloading all application runtime artifacts**. When `test bootJar` runs afterward, Gradle downloads whatever is still missing.

**`COPY src/ src/`:** copies only Java sources/resources/tests. For projects with code generation, included builds, Gradle version catalogs, custom init scripts, or Java resources outside `src`, add those build inputs in appropriate `COPY` instructions; do not assume every project only needs two folders.

**`RUN ... test bootJar`:** JUnit tests from Section 5 are run by `test`, then `bootJar` creates the executable `app.jar`. If tests fail, the image build fails; do not add `-x test` in a production workflow without another policy. If the build needs integration tests or Docker-in-Docker, design a separate test stage and CI setup rather than treating this unit test as the entire test suite.

**`FROM eclipse-temurin:17-jre AS runtime`:** creates the runtime stage from a JRE, with no Gradle, Maven, `javac`, or source code by default. This key difference keeps the final image leaner and reduces attack surface compared to using the JDK builder at runtime.

**`COPY --from=build ... app.jar`:** copies one exact artifact across stages. The `build` ignore rule on the host **does not affect** files newly created inside the build stage's filesystem.

**`EXPOSE 8080`:** records metadata about the port the app usually listens on; **does not publish the port** to the host. `docker run -p 18080:8080` performs the port mapping.

**`USER 10001:10001`:** launches the process with a non-root UID/GID. The JAR copied by `COPY` normally has appropriate read permissions; if the app needs to write to the filesystem (logs/uploads/temp), prepare writable mounts/directories/permissions upfront rather than switching unconditionally to root.

**Exec-form `ENTRYPOINT`:** runs Java directly without default shell wrapping. This gives cleaner signal/exit-status propagation for container orchestration.

### 7.2. If Using Kotlin DSL

Change the exact line:

~~~dockerfile
COPY settings.gradle.kts build.gradle.kts ./
~~~

in the Dockerfile above, keeping `COPY gradlew`, `gradle/wrapper`, and `COPY src` as before. Do not include both Groovy and Kotlin lines if only one pair exists; Docker will fail with `not found` for the missing source files.

### 7.3. Build and Smoke-Test Commands

From the `boot-web` root, with Docker Engine/BuildKit and network access to base images and Gradle/Maven repositories:

~~~bash
docker build --progress=plain -t boot-web:gradle .
docker run --rm -p 18080:8080 boot-web:gradle
~~~

`docker run` in the foreground keeps the web app running. In **another terminal**:

~~~bash
curl -fsS http://localhost:18080/hello
~~~

Expected HTTP body:

~~~text
hello-from-container
~~~

Spring Boot also prints startup logs; the controller returns the string body with no extra newline. Stop the foreground container with Ctrl+C.

If port 18080 is already taken on your machine, choose another host port in `-p` and the matching URL. If the app uses a custom `server.port`, change the container port in the mapping to match; `EXPOSE 8080` **does not change** Spring configuration.

### 7.4. Distinguishing Build-Stage vs Runtime-Stage Failures

- `COPY ... not found`: source missing from context or ignored; not a Java controller error.
- `gradlew: not found` / permission denied: missing wrapper, script, or execute bit in the build stage.
- `Could not resolve ...`: dependency repository, network, proxy, or credentials issue in the builder.
- `compileJava FAILED`: Java source, toolchain, or classpath error.
- `test FAILED`: JUnit assertion or test environment failure.
- `COPY --from=build ... app.jar not found`: `bootJar` output name differs or the build task did not run.
- Image builds successfully yet container exits: inspect logs/runtime args rather than blaming the build context.
- `curl` timeout: server not ready yet, wrong port mapping, or the app bound only to internal loopback instead of an appropriate interface.

## 8. Why Does `.dockerignore` Help Multi-Stage Builds Even When `COPY` Is Selective?

A reasonable question: the Dockerfile in Section 7 only runs `COPY gradlew`, `COPY gradle/wrapper`, `COPY settings.gradle build.gradle`, and `COPY src`; why is `.dockerignore` still needed?

**Three reasons:**

1. **Reduces context data:** especially with remote builders or Docker/BuildKit versions/configurations that transfer extra files; excluding `.git`, caches, and outputs prevents unnecessary context transfer.
2. **Safety net as build scripts evolve:** a future developer may add `COPY . .` or use another Dockerfile with a broad `COPY`. Ignore rules prevent extra files from being sent and causing invalidation.
3. **Lowers risk of leaking sensitive files into builds:** `.env`, private keys, and logs are excluded from the context. This is defense-in-depth, **not absolute security**; source repos, remote build contexts, build args, secrets management, and base images still require separate controls.

BuildKit can optimize context transfer and skip unused files; do not claim every ignored byte translates 1:1 to saved network bytes across all versions. Measure using `transferring context` logs or build diagnostics on your actual builder.

### 8.1. Do Not Exclude Files Currently Being Copied

Example of a broken `.dockerignore` for the Gradle Dockerfile:

~~~dockerignore
gradle
gradlew
src
~~~

Consequence:

~~~text
COPY gradlew ...       -> source excluded
COPY gradle/wrapper ...-> source excluded
COPY src ...           -> source excluded
~~~

Depending on BuildKit, the error may look like `failed to calculate checksum ... not found` or `COPY failed`. The fix is not removing `COPY`, but keeping the required builder inputs and ignoring only unneeded caches/outputs.

### 8.2. `.dockerignore` Does Not Replace Stage Boundaries

If you have:

~~~dockerfile
FROM eclipse-temurin:17-jdk
COPY . .
RUN ./gradlew bootJar
ENTRYPOINT ["java", "-jar", "build/libs/app.jar"]
~~~

even with a great `.dockerignore`, **the final image still uses the JDK stage**, and sources/wrapper/Gradle artifacts have been copied into the image layers. That is a single-stage image and is usually unsuitable for production.

You must add a `FROM ... AS runtime` to create a new stage, then copy only the output via `COPY --from`; an ignore file cannot remove JDK/base layers already present in the final stage.

## 9. Docker Cache Differs from Gradle Cache

Three related caches exist, and they are not synonymous:

| Mechanism | Stored Data | Example |
| --- | --- | --- |
| Docker/BuildKit layer cache | Instruction/layer results when inputs are unchanged | Reusing `COPY build scripts` and `RUN gradlew help` |
| BuildKit cache mount | A persistent directory for package managers/compilers | `/root/.gradle`, `/root/.m2/repository` |
| Gradle dependency/build cache | Gradle modules, metadata, and task outputs per Gradle settings | `~/.gradle/caches/modules-2`, task build cache entries |

If `COPY src` changes, Docker may have to re-run `RUN gradlew test bootJar`. Yet the **cache mount** can still hold downloaded dependencies so Gradle does not re-download everything. If Gradle's build cache is enabled and a task is cacheable, task outputs can be reused based on Gradle inputs; that is an optimization **inside the build stage**, not a substitute for Docker layer caching.

### 9.1. Why Copy Build Scripts Before Source?

Docker layer caching evaluates the instruction and its input files. If a Dockerfile does:

~~~dockerfile
COPY . .
RUN ./gradlew test bootJar
~~~

changing a README, logs, or a single Java source file invalidates the broad `COPY`, and the subsequent `RUN` executes again. With the sequence:

~~~dockerfile
COPY settings.gradle build.gradle ./
RUN ./gradlew help
COPY src/ src/
RUN ./gradlew test bootJar
~~~

steps before `COPY src` can be reused when only source code changes. Be clear, however, that `gradlew help` only warms the wrapper, plugins, and configuration; it **does not guarantee downloading the full runtime dependency graph**. To cache dependencies across `RUN` executions, use BuildKit cache mounts as in Section 7's Dockerfile.

### 9.2. Cache Mounts: Useful, With Caveats

Fragment:

~~~dockerfile
RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon test bootJar
~~~

Meaning:

- `type=cache` lets the cache directory persist in the builder across build invocations, subject to cache GC.
- `target=/root/.gradle` fits when the builder stage runs Gradle as the sample image's default `root` user.
- `sharing=locked` makes concurrent tasks using the same cache wait for one another, which can be safer under concurrent writers at the cost of parallel build throughput.
- A cache mount **does not carry the Gradle User Home into the final image**.
- Caches can be pruned; the build **must still succeed** when the cache is empty. Never rely on the cache as the sole source of truth.

If you switch the builder user to `gradle` or `app`, `GRADLE_USER_HOME` may also change. Mount the directory belonging to that user and set UID/GID on the cache mount if needed; do not hardcode `/root/.gradle` for a non-root stage.

### 9.3. Do Not Use Docker `--no-cache` to Clear the Gradle Dependency Cache

~~~bash
docker build --no-cache --progress=plain -t boot-web:gradle .
~~~

`--no-cache` forces Docker not to use instruction layer cache for that build, yet **it does not necessarily clear BuildKit cache mounts** or external repository/download caches. Nor does it alter Gradle dependency resolution TTLs.

Conversely, `./gradlew clean` cleans workspace outputs without deleting BuildKit layers or the Gradle dependency cache. Do not treat commands at different layers as a single generic "clear cache" switch.

### 9.4. Trading Correctness for Speed Is Wrong

Steps like:

~~~dockerfile
RUN ./gradlew bootJar -x test
~~~

can finish faster while **skipping testing**. Only omit tests if the pipeline has a separate job running the full required test suite per policy and a release gate enforces the result. Never drop dependency verification, security checks, or compiler warnings merely to speed up a Docker build.

## 10. Multi-Stage Maven Build — The Equivalent Option

If the repository uses Maven, no Gradle wrapper is needed. Create a separate `boot-web` project with the same Java sources and the `pom.xml` below; use a dedicated Dockerfile to avoid mixing build tools.

### 10.1. Complete Maven POM

File `pom.xml`:

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
    <artifactId>boot-web</artifactId>
    <version>0.1.0</version>

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
        <finalName>app</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Boot parent manages dependency/plugin versions and `repackage` execution when the plugin is declared. `<finalName>app</finalName>` gives the output executable artifact a stable name `target/app.jar`. Do not confuse `<finalName>` with changing Maven's `artifactId`/`version`: artifact coordinates remain defined by the POM.

### 10.2. Complete `Dockerfile.maven`

At the Maven project root, create `Dockerfile.maven`:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY pom.xml ./

# Warm dependencies/plugins; some plugins still download more in later phases
RUN --mount=type=cache,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp dependency:go-offline

COPY src/ src/

RUN --mount=type=cache,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp verify

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=build /workspace/target/app.jar /app/app.jar

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is the Maven equivalent of Gradle:

- The build stage includes Maven + JDK 17.
- `pom.xml` is copied before `src` so dependency resolution can cache cleanly.
- `dependency:go-offline` downloads many dependencies/plugins needed for offline builds, yet **does not guarantee every dynamic plugin/test/task artifact is downloaded**; the main `verify` goal may still need network access.
- `mvn verify` runs Maven's test/package/verify lifecycle per project config; the Spring Boot plugin's `repackage` produces the executable archive.
- The final stage receives only `target/app.jar` and the JRE, with no Maven local repo, POM, or sources.

Hands-on commands:

~~~bash
docker build --progress=plain -f Dockerfile.maven -t boot-web:maven .
docker run --rm -p 18081:8080 boot-web:maven
~~~

In another terminal:

~~~bash
curl -fsS http://localhost:18081/hello
~~~

Expected body:

~~~text
hello-from-container
~~~

Note that the shared `.dockerignore` also suits this Maven builder: it does not exclude `pom.xml` or `src`. If the Maven project uses a multi-module parent POM, local dependencies, or `.mvn/extensions.xml`, add those build inputs to the context and `COPY` them in the proper structure.

### 10.3. Using the Maven Wrapper Instead of an Image with Maven Preinstalled

You can use a JDK image, copy `mvnw` + `.mvn/wrapper`, and run `./mvnw` instead of relying on Maven preinstalled in the builder. When doing so:

- Keep `mvnw`, `.mvn/wrapper/maven-wrapper.properties`, and needed wrapper files in the context.
- Do not blanket-ignore the `.mvn` directory.
- The builder must be able to download the Maven distribution or have an appropriate offline cache/provisioning.
- A Maven wrapper version pinned in the repository provides better build tool consistency.

Do not mix the two approaches and omit source files: if the Dockerfile calls `./mvnw` without copying `mvnw`/`.mvn`, the build fails before compilation even starts.

## 11. Adding an Extract Stage to Leverage Spring Boot Layered JARs

Multi-stage builds can optimize further than copying a single uber JAR. Spring Boot 3.3 features **layered executable JARs** with `BOOT-INF/layers.idx` and `spring-boot-jarmode-tools` (when enabled). JAR tools support:

~~~bash
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

This command creates layer groups such as:

~~~text
dependencies/
spring-boot-loader/
snapshot-dependencies/
application/
~~~

Using separate Docker `COPY` instructions per group can improve image caching: stable libraries sit in earlier layers while frequently changing application code sits in the last layer. This is the **Spring Boot artifact layers** mechanism, distinct from having multiple stages in a Dockerfile.

### 11.1. Three-Stage Dockerfile: Gradle Build → Extract → Runtime

This is a **complete variant replacing Section 7's Dockerfile**, using the same Groovy Gradle project `boot-web` with `bootJar.archiveFileName='app.jar'`:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

COPY gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle build.gradle ./
RUN chmod +x gradlew

RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon help

COPY src/ src/

RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon test bootJar

FROM eclipse-temurin:17-jre AS extract
WORKDIR /extract
COPY --from=build /workspace/build/libs/app.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=extract /extract/extracted/dependencies/ ./
COPY --from=extract /extract/extracted/spring-boot-loader/ ./
COPY --from=extract /extract/extracted/snapshot-dependencies/ ./
COPY --from=extract /extract/extracted/application/ ./

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Per Spring Boot 3.3, the `extract` output puts an application JAR and a manifest referencing the extracted libraries into the `application` layer; after copying each layer into the same `WORKDIR`, `java -jar application.jar` launches from that layout.

This **is not** running the old uber JAR with `java -jar app.jar` in the final stage: the final image receives only the files extracted from the layers, with no need to retain the full uber JAR.

### 11.2. Key Requirements for Extraction to Work

- The executable JAR must support `-Djarmode=tools` and include `spring-boot-jarmode-tools`; if a team disables `includeTools`, the mode will not exist.
- The JAR must be built **without a launch script**. Spring Boot 3.3 docs state that `tools` mode **cannot be used** on a fully executable archive prepended with a shell script.
- Verify the JAR has layer metadata per plugin configuration. If a team defines custom layers, the default names/folders may not apply.
- Use a compatible Java runtime in the extract stage.
- If `extract` fails, read the actual logs before editing the `Dockerfile` or disabling tests.
- On older Spring Boot versions, mode/arguments may differ (`layertools` in older lines). Do not copy this syntax blindly across all versions.

### 11.3. Multi-Stage and Layered Copies Optimize Different Things

| Optimization | Primary Impact |
| --- | --- |
| Separate build stage and JRE final stage | Keeps JDK/Maven/Gradle/source out of the final image |
| `.dockerignore` | Excludes unneeded host files from the build context |
| Proper `COPY` ordering | Prevents invalidating early Docker layers when source changes |
| BuildKit cache mount | Reuses downloaded dependencies and partial caches across build invocations |
| Spring Boot layers + separate `COPY` | Splits runtime libraries/loader/app classes for Docker image layer caching |
| Smaller/pinned base image | Reduces footprint and risk depending on image; requires compatibility testing |
| Gradle/Maven reproducible build policy | Reduces unnecessary differences in artifact bytes |

Do not lump all these techniques together as "multi-stage builds" or "Docker cache." They act at different layers of the system.

## 12. Organizing Context for Gradle Multi-Project and Maven Multi-Module Builds

Real projects are rarely as small as a single demo:

~~~text
workspace/
├── settings.gradle
├── build.gradle
├── gradle/
│   ├── wrapper/
│   └── libs.versions.toml
├── gradlew
├── common-lib/
│   ├── build.gradle
│   └── src/
├── api-service/
│   ├── build.gradle
│   └── src/
└── docker/
    └── api.Dockerfile
~~~

If the Dockerfile sits at `docker/api.Dockerfile`, the right command to use the root build context is typically:

~~~bash
docker build -f docker/api.Dockerfile -t api-service:local .
~~~

The trailing `.` remains the context root. The Dockerfile must copy the files required by the Gradle root, subprojects, version catalogs, and shared build logic. Reference fragment:

~~~dockerfile
WORKDIR /workspace
COPY gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle build.gradle ./
COPY gradle/libs.versions.toml gradle/libs.versions.toml
COPY common-lib/build.gradle common-lib/build.gradle
COPY api-service/build.gradle api-service/build.gradle
COPY common-lib/src/ common-lib/src/
COPY api-service/src/ api-service/src/
RUN ./gradlew --no-daemon :api-service:test :api-service:bootJar
~~~

This is an **illustrative fragment**, not a complete Dockerfile: it assumes the project root actually contains all those paths. If using Kotlin DSL, substitute `.gradle.kts` filenames. If you have `buildSrc`, an included build `build-logic`, `gradle.properties`, generated sources, schema files, or codegen inputs, copy those additional paths too.

Principles:

1. **Include only the modules needed to build the application**, without dropping project dependencies the application requires.
2. Keep root settings and version catalogs if Gradle needs them to resolve the full dependency graph.
3. Target the task path `:api-service:bootJar` instead of root `bootJar` when the root project is not a Spring Boot application.
4. Configure an explicit output filename on the module actually producing the artifact.
5. Use `COPY --from=build /workspace/api-service/build/libs/app.jar ...` in the runtime stage, rather than assuming `workspace/build/libs`.
6. Do not set the context to `api-service/` when `settings` references `common-lib/` outside that directory.

### 12.1. Maven Multi-Module

A Maven reactor has a parent POM and module POMs. A `Dockerfile.maven` might need:

~~~dockerfile
COPY pom.xml ./
COPY common-lib/pom.xml common-lib/pom.xml
COPY api-service/pom.xml api-service/pom.xml
COPY common-lib/src/ common-lib/src/
COPY api-service/src/ api-service/src/
RUN mvn -B -ntp -pl api-service -am verify
~~~

This is a **fragment**: the root POM must declare the corresponding modules, and all plugins/parent dependencies must resolve. `-pl api-service -am` selects the module plus its required reactor dependencies, without producing an artifact in the root `target`.

The runtime stage must copy the exact module output, e.g., `/workspace/api-service/target/app.jar` if that Maven module sets `finalName=app`. Do not run `COPY target/*.jar` on the root when the root uses `pom` packaging.

### 12.2. Do Not Blanket-Ignore `**/build` and Then Expect to Copy a Local JAR

There are two distinct models:

**A. Docker builds from source:** the builder stage runs Gradle/Maven and needs `src`/build scripts; you should ignore local `build/`/`target/` to avoid sending stale outputs.

**B. Docker image from a CI-prebuilt JAR:** the Dockerfile only needs the executable JAR; the context must contain the **deterministically staged/published JAR**, e.g., `dist/app.jar`. In this case, do not add an ignore rule that removes the exact source JAR needed by `COPY dist/app.jar`.

No single `.dockerignore` is optimal for both scenarios when input requirements differ. Use separate names like `Dockerfile.source`/`Dockerfile.artifact` and Dockerfile-specific ignore rules when necessary.

## 13. Packaging an Image Only from a Host-Built JAR

This **is not a multi-stage build from source**, yet it is very useful when CI has already run `./gradlew test bootJar` and only needs container packaging. Separating artifact compilation from Docker packaging can make provenance and CI orchestration clearer.

Example layout:

~~~text
publish-image/
├── Dockerfile
├── .dockerignore
└── dist/
    └── app.jar
~~~

Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY dist/app.jar /app/app.jar
EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

A `.dockerignore` for this scenario can use a controlled allowlist:

~~~dockerignore
**
!dist/
!dist/app.jar
!Dockerfile
!.dockerignore
~~~

With allowlists/negation, test thoroughly because matcher and parent-directory rules apply. This example intentionally preserves `dist/app.jar`. With `dist` at the context root, run the Docker build from `publish-image/`:

~~~bash
docker build -t boot-web:artifact .
~~~

Do not pick the JAR via a `build/libs/*.jar` glob when both `-plain.jar` and the Boot JAR exist. The CI staging step should copy **the exact task output** to `dist/app.jar`, and that file must pass QA first.

**Distinction:** excluding `build/` in `.dockerignore` shrinks a source-build context, whereas for an image-from-artifact build you must *include* the path holding the staged artifact. Focus on **each Dockerfile's input contract**, not a rigid universal ignore rule.

## 14. Verifying Build Context and Cache Effectiveness Properly

### 14.1. Enabling Verbose Build Output

~~~bash
docker build --progress=plain -t boot-web:gradle .
docker build --progress=plain -t boot-web:gradle .
~~~

Watch for lines resembling:

~~~text
[internal] load .dockerignore
[internal] load build context
transferring context: ...
CACHED ...
RUN ... test bootJar
~~~

These are **message categories**, not fixed stdout. Exact context byte counts, duration, and cache hits depend on Docker/BuildKit version, builder backend, source tree, and current state.

The first build may download the base image, Gradle distribution, and plugins/dependencies. The second build can be faster due to Docker layers, BuildKit cache mounts, Gradle downloaded dependencies, and filesystem caching. **Do not claim a specific savings figure** without controlled measurements.

### 14.2. Edit One File to Observe Invalidation

After the first build, modify a string in `HelloController.java` and rebuild:

~~~bash
docker build --progress=plain -t boot-web:gradle .
~~~

Expected behavior:

- Layers copying the wrapper and build scripts can show `CACHED` when those inputs are unchanged.
- The `COPY src` layer changes.
- `test bootJar` re-runs, or Gradle reuses valid task outputs from the cache mount if configured.
- The runtime stage receives only the new Boot JAR; source code is not carried into the final image.

If you edit `build.gradle` instead of source, setup/configuration steps invalidate earlier; this is right because plugins, versions, or the dependency graph may have changed.

### 14.3. Confirming the Final Image Contains No Build Tooling

The following inspection commands are for verification, not an absolute security guarantee:

~~~bash
docker image ls boot-web
docker image inspect boot-web:gradle
docker history --no-trunc boot-web:gradle
~~~

`docker history` inspects the final image and reflects base/history/runtime instructions. It does not prove every file's presence or absence; for stronger verification, run a shell inspection when the runtime image includes a shell:

~~~bash
docker run --rm --entrypoint sh boot-web:gradle -c 'ls -la /app'
~~~

Expected in the example: `/app/app.jar` exists. There is no `gradlew` or source code under `/app`. Still, `eclipse-temurin:17-jre` contains OS/JRE components; multi-stage builds do not produce a literal "single-file image."

If using a shell-less distroless image, `--entrypoint sh` will not work; inspect with other tooling or a suitable debug stage rather than concluding the image is broken.

### 14.4. Comparing Image Size and Build Time

For meaningful measurements:

- Use the exact same source revision, base images, builder, network, and cache state.
- Record sizes via `docker image inspect`/`docker image ls`, and durations from build logs.
- Compare a single-stage Dockerfile (for experimentation only) against the multi-stage/JRE runtime.
- Do not compare compressed registry transfer size against uncompressed local image size as if they share a unit.
- Record cold vs warm Docker layer cache and Gradle/Maven dependency cache states.
- Verify endpoints/behavior; a smaller image missing runtime libraries or permissions is not a successful optimization.

## 15. Security: Multi-Stage and .dockerignore Are Only Protective Layers

### 15.1. Do Not Put Secrets in Dockerfiles or Build Args

Avoid:

~~~dockerfile
ARG REPO_PASSWORD=hardcoded-secret
ENV REPO_PASSWORD=hardcoded-secret
COPY .env /app/.env
~~~

These are **anti-patterns**. Build args, environment variables, layers, and history can leak sensitive values if misused. `.dockerignore` lowers the chance of sending local sensitive files, yet it **does not** protect secrets hardcoded in a Dockerfile/build script or fetched unchecked over the network.

With BuildKit, use `--secret` and `RUN --mount=type=secret` per Docker documentation when the builder needs private repository credentials. Never print secrets to logs or copy them into final artifacts/layers. Coordinate with your CI secret manager and credential rotation policy.

### 15.2. Use a Non-Root Runtime

In the final stage:

~~~dockerfile
USER 10001:10001
~~~

This prevents the Spring Boot process from running as root by default. You must still verify:

- The JAR file is readable by this UID/GID.
- Log storage and temp directories are writable if the app needs them.
- The listening port does not require root privileges (8080 is unprivileged).
- The runtime filesystem works read-only or has necessary mounts.
- Container orchestration may override UID/GID; do not assume every environment preserves it unchanged.

Do not fix permission errors by switching unconditionally to `USER root`. Grant permissions only to the specific directories that need writes.

### 15.3. Pin Base Images and Verify the Supply Chain

`eclipse-temurin:17-jdk`/`:17-jre` and `maven:3.9-eclipse-temurin-17` are illustrative image tags. Tags can update for security patches; in production enforce policies for approved registries, image digest pinning or update cadences, vulnerability scanning, SBOMs, and provenance.

Do not paste a fake `sha256:...` into a Dockerfile; retrieve the real digest from an organization-approved registry and verify compatibility. Multi-stage builds leave fewer tools in the runtime image, yet **do not by themselves prove** zero CVEs or a trustworthy base image.

### 15.4. Do Not Trust Arbitrary Context Sources

Docker supports local and remote Git/tar contexts. When `docker build` receives a remote URL, files are fetched from that source; ignore handling and builder permissions can differ from a local checkout. Never build from an untrusted Git URL using secrets or a privileged builder. Verify context sources, commits/revisions, and checksums in your CI pipeline.

## 16. Common Errors and Fixes

| Symptom | Common Cause | Check and Proper Fix |
| --- | --- | --- |
| `COPY gradlew: not found` | Wrapper missing from context or ignored | Verify `gradlew` exists, context root, and `.dockerignore` |
| `COPY gradle/wrapper: not found` | Wrong name/path or `gradle` excluded | Keep `gradle/wrapper`, avoid confusing with `.gradle` |
| `gradlew: Permission denied` | Wrapper not executable in Linux | `RUN chmod +x gradlew` before `RUN` |
| `gradlew` fails downloading Gradle distribution | Network/TLS/URL/wrapper permission issue | Check `gradle-wrapper.properties`, proxy, approved mirror |
| `settings.gradle`/`build.gradle` not found | Using Kotlin DSL while Dockerfile copies Groovy names | Switch to `.gradle.kts` and preserve proper context |
| `COPY src` not found | Chose `docker/` context by mistake or ignored source | Use repository root context and fix ignore rules |
| Gradle `bootJar` task not found | Plugin not applied on the right module | Check `plugins` and Gradle project path |
| `COPY --from=build ... app.jar` missing | Different output filename, task didn't run, different module path | Fix `archiveFileName`/`finalName`, select exact path |
| `java -jar` lacks `Main-Class` or runtime libs | Plain JAR copied by mistake | Check `bootJar`/Maven repackage, manifest, and `BOOT-INF` |
| Container starts yet URL unreachable | Wrong `-p` or app not bound to right port | Inspect logs, port mapping, and `server.port` |
| Docker build very slow after editing README | `COPY . .` and context missing ignore rules | Split `COPY` by stability, exclude unneeded docs/logs/cache |
| Docker build re-downloads Gradle/Maven deps | Missing cache mount or fresh builder/GC prune | Use BuildKit cache mounts, pin wrapper and repositories |
| `.dockerignore` not taking effect as expected | File at wrong root or Dockerfile-specific ignore takes precedence | Identify exact context, Dockerfile path, and active ignore file |
| `!` rule fails to re-include file | Rule ordering or parent directory excluded | Check last-match rule; test on actual directory tree |
| Builder compiles fine, runtime hits `ClassNotFound` | Wrong JAR copied or wrong dependency scope | Inspect `BOOT-INF/lib`, production `runtimeClasspath` |
| `USER 10001` cannot write logs | Missing runtime writable directory/permissions | Provision proper mounts and permissions; do not blindly enable root |
| `jarmode=tools` reports unsupported | JAR has launch script or missing tools/wrong version | Use Boot JAR without script, include tools, match Boot version |
| Layered Dockerfile `COPY extracted/...` fails | Extract did not produce expected folders or custom layers used | Inspect extract command/output in the stage |
| Image unexpectedly large | Copied full source/JDK to runtime, oversized base | Check final stage and `COPY --from`, pick a suitable JRE |
| Build context contains secrets | Missing ignore rules or broad `COPY` | Exclude files from context, use secret mounts, audit sources |
| Multi-module build fails | Missing project dependencies/version catalogs/`buildSrc` | Copy all required inputs or use proper root context |

### 16.1. Safe Diagnostic Process

1. **Inspect the command** `docker build -f ... CONTEXT`, identifying the actual context root.
2. **Check the active `.dockerignore`** and Dockerfile-specific ignore file if present.
3. **Identify the failing stage**: build, extract, or runtime. Do not edit the controller when `COPY` fails before compilation.
4. **Check build tool outputs**: Gradle `bootJar`/Maven `repackage` and the actual file path.
5. **Inspect the artifact**: manifest and `BOOT-INF/classes`/`BOOT-INF/lib` when using an executable Boot JAR.
6. **Inspect the final image**: JRE runtime, JAR path, non-root permissions, `ENTRYPOINT`.
7. **Run the smoke test** with proper port mapping; read logs.
8. **Only then optimize cache** once a non-cached build already succeeds and passes tests.

## 17. Practice Exercises with Answers

### Exercise 1 — Understanding the Context Root

The Dockerfile is at `docker/Dockerfile`, while `src`/`build.gradle` are at the root. You run:

~~~bash
docker build -f docker/Dockerfile docker/
~~~

`COPY src/ src/` fails. Why?

**Answer:** the context is `docker/`, not the root directory containing `src`. Run `docker build -f docker/Dockerfile .` from the project root or intentionally restructure the context.

### Exercise 2 — Keep Wrapper, Exclude Cache

Consider two directories:

~~~text
.gradle/
gradle/wrapper/
~~~

**Question:** which directory should be ignored when the Dockerfile runs `./gradlew`?

**Answer:** typically ignore `.gradle/` (local state), and **keep** `gradle/wrapper/` and `gradlew`. The wrapper is needed inside the Linux builder.

### Exercise 3 — Why `.dockerignore` Does Not Shrink a Single-Stage Runtime

**Question:** a Dockerfile uses `FROM eclipse-temurin:17-jdk`, `COPY src`, and `RUN ./gradlew bootJar`, then runs that same image. Why is the image still huge despite a tiny context?

**Answer:** the final image is still based on the JDK stage, and sources/build tooling remain in its filesystem/layers. You must add a new JRE final stage and `COPY --from` only the JAR.

### Exercise 4 — Picking the Right JAR

A Gradle task produces both:

~~~text
build/libs/boot-web-0.1.0-plain.jar
build/libs/boot-web-0.1.0.jar
~~~

**Question:** which file should the Dockerfile copy to the `java -jar` runtime?

**Answer:** the output of `bootJar`, usually the unclassified file by default; better yet, set `archiveFileName='app.jar'` to copy an exact path. Never pick via a blind glob.

### Exercise 5 — BuildKit Cache Mount

**Question:** a Dockerfile uses `RUN --mount=type=cache,target=/root/.gradle ...`, and editing a Java source file makes `RUN` execute again. Must all dependencies be re-downloaded from scratch?

**Answer:** not necessarily. A Docker instruction cache miss occurs, yet the Gradle dependency cache inside the mount remains if retained by the builder. If the cache mount was GC'd/cleared or dependencies changed, downloading updates is normal.

### Exercise 6 — Maven vs Gradle

**Question:** a Maven Dockerfile uses `FROM maven:3.9-eclipse-temurin-17` and copies the POM and `src`; is `gradlew` needed?

**Answer:** no. That is a Maven builder where `mvn` is already in the image. If you want to use the Maven wrapper, change the design and copy `mvnw`/`.mvn` completely.

### Exercise 7 — Layered Image

**Question:** why use 4 `COPY --from=extract` instructions for `dependencies`, `spring-boot-loader`, `snapshot-dependencies`, and `application` instead of copying a single uber JAR?

**Answer:** Docker can cache and pull layers independently; when app classes change while dependencies stay unchanged, stable layers change less often. Precondition: the Spring Boot JAR supports extraction and the output layout matches.

### Exercise 8 — Launch Script

**Scenario:** a project enables `launchScript()` to run `./app.jar` directly on Unix; a new Dockerfile invokes `-Djarmode=tools ... extract --layers`.

**Answer:** in Spring Boot 3.3, `tools` mode does not support fully executable archives with a launch script. Build a Boot JAR **without a script** for Docker layer extraction; if direct Unix execution is needed, publish a separate variant.

### Exercise 9 — Include Exceptions

`.dockerignore` contains:

~~~dockerignore
*.md
!README*.md
README-private.md
~~~

**Question:** is `README-private.md` in the context?

**Answer:** it is excluded due to the last matching rule. Moving the exception last can change the outcome; order is part of ignore-file semantics.

### Exercise 10 — Secrets

**Question:** having ignored `.env`, is it safe to put `ARG DB_PASSWORD=...` in the Dockerfile?

**Answer:** no. `.dockerignore` filters the host context; it does not hide hardcoded values, build args, layers, or logs. Use BuildKit secrets or CI/runtime secrets per policy.

## 18. Pre-Merge Dockerfile Checklist

- [ ] Identified the **exact build context** and root `.dockerignore` for every `docker build` command.
- [ ] Necessary build inputs (source, wrapper, POM, settings, version catalog, generated inputs) are not ignored.
- [ ] `.git`, `.gradle`, `build/`, `target/`, logs, local credentials, and unneeded files are excluded from the context.
- [ ] Build stage uses a JDK/build tool; runtime stage uses only a JRE and necessary artifacts.
- [ ] Dockerfile uses `COPY --from` with explicit stage and artifact path; never mistakes a plain JAR.
- [ ] Gradle `bootJar` or Maven `repackage` actually runs, with test gates enforced per policy.
- [ ] BuildKit cache mounts (if used) do not make builds depend on unverified cached data.
- [ ] Source-only edits do not needlessly invalidate unrelated early Dockerfile steps.
- [ ] When using layered JARs, `jarmode=tools` matches the Spring Boot version, tools are included, and launch scripts are disabled.
- [ ] Final image runs as a non-root user with proper port mapping and filesystem permissions.
- [ ] No build secrets, certs, or tokens exist in the context, image history, runtime JAR, or Docker logs.
- [ ] Base images come from approved registries with version/digest policies, scanning, and update cadences.
- [ ] Executed `docker build --progress=plain` and smoke-tested the endpoint with `docker run -p`/`curl`.
- [ ] Measured context/cache/image size under explicit conditions; no unmeasured optimization percentages claimed.
- [ ] CI picks the right Dockerfile/context and artifact variant when the repo spans Gradle/Maven/multi-project setups.

**Conclusion:** multi-stage builds govern **the boundary between the build environment and the runtime image**; `.dockerignore` governs **the boundary between the host filesystem and data entering the build context**. Combining both with proper `COPY` ordering and BuildKit cache mounts reduces build time, avoids copying unneeded artifacts/caches/secrets, and keeps the runtime image lean. Yet true completion remains **a reproducible build, controlled tests, and a final image that runs the application correctly in the target environment**.

## 19. Official Sources

- Docker Docs — Build Context and `.dockerignore` patterns, negation, Dockerfile-specific precedence: https://docs.docker.com/build/concepts/context/
- Docker Docs — Multi-stage Builds: https://docs.docker.com/build/building/multi-stage/
- Docker Docs — Optimize Cache Usage in Builds: https://docs.docker.com/build/cache/optimize/
- Docker Docs — Dockerfile Reference, `RUN --mount=type=cache`: https://docs.docker.com/reference/dockerfile/
- Docker Docs — BuildKit: https://docs.docker.com/build/buildkit/
- Spring Boot 3.3.13 — Dockerfiles and `jarmode=tools extract --layers`: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3.13 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Running Gradle Builds with Docker: https://docs.gradle.org/current/userguide/docker.html
- Apache Maven — Build and Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html

Whenever changing the Gradle wrapper, Maven plugin, Spring Boot version, or Dockerfile frontend, consult the version-matched documentation and verify the build/image in a real environment. The goal is a **lean, accurate context, a well-equipped builder, a compact and secure final image, and a verified artifact**, not merely two `FROM` lines or a long `.dockerignore`.