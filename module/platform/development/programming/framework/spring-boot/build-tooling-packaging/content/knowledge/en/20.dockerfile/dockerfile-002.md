# Distinguishing a JDK Build Image from a JRE Runtime Image

## Learning Objectives

When containerizing a Spring Boot application with Docker, a critical choice is **which image compiles the application** and **which image actually goes into production**. Many beginners put Maven, Gradle, the JDK, source code, and the executable JAR into a single image and then run `java -jar`. That can work, but it usually ships unnecessary components in the release image.

Docker **multi-stage builds** solve this by separating the phases:

- **Build stage:** uses an image containing a **JDK** and build tools/Wrapper to compile Java, run tests, resolve dependencies, and produce the Spring Boot executable JAR/WAR.
- **Runtime stage:** uses an image containing a **JRE** (or an appropriately constructed Java runtime) to **run the built artifact**, without carrying `javac`, Maven, Gradle, source code, or test suites.
- **Handoff:** `COPY --from=build` takes the exact executable JAR from the build stage into the runtime stage; only files explicitly copied or installed in the runtime stage appear in the final filesystem.

After this lesson, you will be able to:

1. Explain the differences between **JVM, JRE, and JDK**; understand why Java runtimes after Java 9 do not necessarily have a nested `jre/` directory like older JDKs.
2. Read Docker tags like `eclipse-temurin:17-jdk-jammy` and `eclipse-temurin:17-jre-jammy` accurately; choose compatible **Java major versions** and operating systems/architectures.
3. Write a **multi-stage Dockerfile** to build Spring Boot with Maven Wrapper or Gradle Wrapper on a JDK, then run the executable JAR on a JRE.
4. Avoid accidentally copying `-plain.jar`, `.jar.original`, source code, `.m2`, `.gradle`, or secrets into the production image.
5. Use `docker build`, `docker run`, `docker image inspect`, `java -version`, `javac -version`, and an HTTP smoke test to prove the two stages play different roles.
6. Optimize build context/cache, run as a non-root user, check base image digests, CVEs, CA certificates, filesystem permissions, and resource limits.
7. Identify **edge cases** where a minimal JRE is not enough: applications using the Java compiler API, `jlink`/`jdeps`, stripped Java modules, or diagnostic tools found only in a JDK.
8. Distinguish building **inside Docker** from **building in CI followed by a runtime-only Dockerfile**, and understand alternatives like buildpacks or custom `jlink` runtimes.

**Example context:** Spring Boot **3.3.13**, Java **17**, an **Eclipse Temurin JDK 17** image for building, and **Eclipse Temurin JRE 17** for runtime. Both tags `17-jdk-jammy` and `17-jre-jammy` exist in the Eclipse Temurin Docker Official Image at the time of reference. They are **mutable** tags that can be updated; to lock base image bytes in a release pipeline, use digests according to your organization's policy. Examples use shell/Linux Docker; Windows PowerShell variants appear later.

---

## 1. From Java Source to a Running Spring Boot Process

First, look at the flow **without Docker**:

```text
src/main/java/*.java
       |
       v
  javac / JavaCompiler                <-- tool in the JDK
       |
       v
    *.class
       |
       v
 Maven/Gradle + Spring Boot plugin   <-- packages executable JAR
       |
       v
  container-demo-0.0.1-SNAPSHOT.jar
       |
       v
 java -jar file.jar                   <-- needs Java runtime + app dependencies
       |
       v
 Spring Boot ApplicationContext
       |
       v
 HTTP GET /hello
```

When producing `.class` files, a Java compiler must be provided. At the `java -jar` step, most standard Spring Boot applications **do not need to continue compiling source code**.

### 1.1 JVM, JRE, and JDK: Different Responsibilities

| Component | Primary Role | Needed at Which Step? |
| --- | --- | --- |
| **JVM** | Executes Java bytecode, classloading, garbage collection, JIT, thread handling. | Runtime; also used when running Java tools. |
| **JRE** | JVM + Java standard libraries/modules + components supporting Java application execution. | Running `java -jar`. |
| **JDK** | Java runtime **plus development tools**, such as `javac`, `jar`, `jlink`, `jdeps`, and other utilities depending on the distribution. | Compile/test/package/build image; can **also** run the application. |
| **Maven/Gradle** | Build orchestration: dependency resolution, compilation, testing, packaging. | Typically used in the build stage, **not required** at runtime. |
| **Spring Boot executable JAR** | App classes/resources + Boot launcher + runtime dependency JARs packaged by the plugin. | The file executed by the runtime JRE. |

**A JDK is not something that "only compiles and cannot run."** A JDK includes a runtime and is completely capable of running `java -jar`. Choosing a JRE for the final image is a **decision to remove unneeded components**, not a mandatory Java requirement.

**A JRE is not just a bare JVM.** The JVM needs Java platform classes/modules and native libraries to run a program. An overly stripped runtime missing required modules can fail even if the `java` binary is present.

### 1.2 Java 9+ and the "JRE" Naming

In Java 8, many developers grew accustomed to distinguishing `JDK/bin` and `JDK/jre/bin`. Since Java 9 and the Java Platform Module System, you should not assume a modern JDK still contains a nested `jre/` directory. A modern JRE image may hold the Java runtime at `/opt/java/openjdk` with standard modules, yet **lack the full set of development tools**.

Therefore, verify with **actual commands** instead of inferring from folder names:

```bash
# Build image
docker run --rm --entrypoint java eclipse-temurin:17-jdk-jammy -version
docker run --rm --entrypoint javac eclipse-temurin:17-jdk-jammy -version

# Runtime image
docker run --rm --entrypoint java eclipse-temurin:17-jre-jammy -version
```

The expected result is that both have `java` and the JDK has `javac`. **There is no need to try running `javac` in the JRE to check**, because a missing executable errors immediately at runtime; Section 11 provides a safer shell command to check its absence.

### 1.3 A Spring Boot Executable JAR Is Not a Compiler

In Spring Boot 3.3, an executable JAR typically contains:

```text
container-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/com/example/container/ContainerApplication.class
├── BOOT-INF/lib/spring-boot-...jar
├── BOOT-INF/lib/spring-webmvc-...jar
├── BOOT-INF/lib/tomcat-embed-...jar
└── org/springframework/boot/loader/...
```

This is an **illustrative layout**; dependency names and versions are chosen by the build tool. When `java -jar` is called, the Boot launcher starts the application and loads nested JARs. The JRE **does not need to unpack and recompile** all `BOOT-INF/classes` to run.

The JVM's JIT compiler optimizes machine code **while the program is running**. That is a runtime mechanism **different from `javac`** and does not invalidate the rule that "the JRE is for runtime."

## 2. Why Separate the Build Image from the Runtime Image?

### 2.1 Consequences of a Single JDK Image for All Phases

A simple but unoptimized example:

```dockerfile
FROM eclipse-temurin:17-jdk-jammy

WORKDIR /workspace
COPY . .
RUN ./mvnw clean package
ENTRYPOINT ["java", "-jar", "/workspace/target/container-demo-0.0.1-SNAPSHOT.jar"]
```

This is a **counter-example**, not a recommended production Dockerfile. It also assumes `mvnw` already has the executable bit set and `.mvn` is copied properly. Such an image can contain:

- The JDK with the compiler and development tools unneeded at runtime.
- Project source code, test fixtures, build scripts, and arbitrary files in the build context.
- Maven/Gradle caches and dependency metadata accumulated across layers.
- Tooling or sensitive files accidentally swept in by `COPY . .`.
- A larger filesystem and broader vulnerability scan scope, depending on the actual OS layers and packages.

**Do not automatically conclude that a JDK image contains security vulnerabilities** or that a JRE is always safer. Both JDK and JRE images can have CVEs; OS packages, base image age, app dependencies, and patch policies decide. Multi-stage builds simply **reduce unnecessary components** in the runtime image and can improve risk management.

### 2.2 Multi-stage: Keep the Build Process, Omit Build Tools from Final

```text
                 Dockerfile
                     |
        +------------+------------------+
        |                               |
        v                               v
Stage "build"                     Stage "runtime"
JDK 17                             JRE 17
Maven/Gradle Wrapper               No Wrapper needed
src/ and test/                     No source needed
dependency cache                   No build cache needed
javac, tests, packaging            Only Java launcher + app.jar
        |                               ^
        v                               |
  /out/app.jar -------- COPY --from=build
                                        |
                                        v
                                Production container
                                java -jar /app/app.jar
```

A Dockerfile can contain multiple `FROM` instructions. Each `FROM` starts **a stage** with its own base filesystem. In a standard Docker build, the **final stage** becomes the tagged image; earlier layers may be kept by BuildKit in the **build cache**, but they do not become filesystem layers of the final image unless you explicitly copy from or reference them.

**Remember:** secrets can still leak into build logs, caches, or remote build infrastructure if mishandled, even if they do not appear in the final image. Multi-stage builds **do not replace** secret management.

### 2.3 Practical Comparison Table

| Question | Build Stage Using JDK | Runtime Stage Using JRE |
| --- | --- | --- |
| Has `java`? | Yes | Yes |
| Has `javac`? | Yes | Usually no |
| Has Maven/Gradle? | Provided by you via Wrapper or base image | Usually not needed |
| Has source/tests? | Yes, for building and testing | Should not be copied |
| Has `jar`/`jlink`/`jdeps`? | Usually present in JDK | Should not be assumed present |
| Can run Spring Boot app? | Yes | Yes, if Java/runtime is compatible |
| Can compile Java source? | Yes | Not the standard goal |
| Can run JUnit/Gradle tests? | Yes, if configured properly | Not needed in production |
| Optimization goal | Fast, correct builds with diagnostic tools | Minimal components and privileges, easy updates |
| Guarantees absolute security? | No | No |

## 3. Compatibility Requirement: Choosing the Right Java Major Version

Java bytecode has a **class file version**. An application built for Java 17 uses class file **major 61**; an older Java runtime may throw `UnsupportedClassVersionError`. Conversely, a newer JRE generally runs older bytecode within Java/platform compatibility boundaries, though API, module, library, or runtime behavior changes can still occur.

Same-version line example:

```dockerfile
# Compiler/toolchain for a Java 17 application
FROM eclipse-temurin:17-jdk-jammy AS build

# Java 17 runtime from the same distribution family
FROM eclipse-temurin:17-jre-jammy AS runtime
```

This is a simple, low-surprise choice for a Spring Boot 3.3.13 project with a Java 17 toolchain.

**Do not arbitrarily pair** `21-jdk` with `17-jre` and assume it is safe. JDK 21 can be configured with `--release 17` or a Gradle Java 17 toolchain to emit compatible bytecode, but if code uses Java 21 APIs or the compiler target is wrong, JRE 17 will still fail. Explicitly declare the Java compiler target/`maven.compiler.release`/`java.toolchain` and test against the actual runtime.

### 3.1 Checking the Version Inside the Image

```bash
docker run --rm --entrypoint java \
  eclipse-temurin:17-jdk-jammy -version

docker run --rm --entrypoint java \
  eclipse-temurin:17-jre-jammy -version
```

The output **must not be asserted verbatim**: Temurin minor/security patches and build numbers can change as tags update. What to compare is **major Java version 17** and an approved version/build.

### 3.2 Linux Distribution Differences and Native Dependencies

The `-jammy` suffix indicates Ubuntu 22.04 "Jammy" as the base OS, not part of the Java version. Two images with the same Java 17 based on Ubuntu, Alpine/musl, or a distroless base can differ in:

- libc: **glibc** vs **musl**.
- CA certificate store and how trust certificates are updated.
- Timezone/locale/font packages.
- Native libraries, JNI, `java.library.path`.
- Presence or absence of shell/debug tools.
- User/group setup, filesystem, and paths.

For libraries using JNI/native code such as certain drivers, OCR, graphics, or Netty native transport, do not assume "same Java major means guaranteed to run." Test the actual runtime image on the target CPU architecture/OS.

### 3.3 CPU Architecture

Docker Official Images may support multiple architectures such as `linux/amd64` and `linux/arm64`, but **not every tag** supports every platform. Inspect before building multi-arch or running on ARM:

```bash
docker buildx imagetools inspect eclipse-temurin:17-jdk-jammy
docker buildx imagetools inspect eclipse-temurin:17-jre-jammy
```

This uses the Buildx plugin. Platform availability can change by tag/registry; do not assume an ARM host will run an x86_64 native layer or that an app with native dependencies is automatically compatible.

## 4. Spring Boot Java 17+ Project for Practice

To give this lesson clear verification criteria, we use a small web app returning a fixed string, with the same project buildable via **Maven or Gradle**. When practicing, pick **one build system**; do not mix both Dockerfiles on one project tree and guess the output.

### 4.1 Structure

```text
container-demo/
├── src/
│   ├── main/java/com/example/container/ContainerApplication.java
│   └── test/java/com/example/container/ContainerApplicationTests.java
├── pom.xml                        (if using Maven)
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...               (if using Maven Wrapper)
├── settings.gradle                (if using Gradle)
├── build.gradle                   (if using Gradle)
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...             (if using Gradle Wrapper)
├── Dockerfile.maven               (Maven option)
├── Dockerfile.gradle              (Gradle option)
└── .dockerignore
```

The `mvnw`/`gradlew` files and Wrapper directories must be generated from trusted tools/sources. **Do not create a Wrapper using only a hand-written shell script** while omitting the Maven/Gradle distribution checksum and required wrapper JAR.

### 4.2 Java Code That Actually Compiles in a Spring Boot Project

`src/main/java/com/example/container/ContainerApplication.java`:

```java
package com.example.container;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ContainerApplication {

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "Hello from Spring Boot";
    }

    public static void main(String[] args) {
        SpringApplication.run(ContainerApplication.class, args);
    }
}
```

This class acts as both main configuration and registers the REST endpoint `GET /hello`. It is valid Java 17+ **inside a project with `spring-boot-starter-web`**. Do not invoke `javac ContainerApplication.java` standalone without configuring the Spring Boot classpath.

### 4.3 HTTP Integration Test

`src/test/java/com/example/container/ContainerApplicationTests.java`:

```java
package com.example.container;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ContainerApplicationTests {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void helloEndpointReturnsText() {
        String body = rest.getForObject("/hello", String.class);
        assertEquals("Hello from Spring Boot", body);
    }
}
```

The test starts embedded Tomcat on a random port in the build/test environment. It helps ensure the app works at a basic level **before creating the runtime image**. **Testing on the build-stage JVM differs from the final runtime image**; an HTTP smoke test after `docker run` is still required.

### 4.4 Complete Maven POM

File `pom.xml`:

```xml
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
    <artifactId>container-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Because it uses `spring-boot-starter-parent`, the Spring Boot Maven Plugin's `repackage` goal is wired into the lifecycle when declared. After `./mvnw clean package`, the sample app has its **main executable JAR** at `target/container-demo-0.0.1-SNAPSHOT.jar`; Maven may keep the pre-repackage archive as `.jar.original`.

### 4.5 Complete Gradle Groovy DSL

`settings.gradle`:

```groovy
rootProject.name = 'container-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

After `./gradlew clean build`, the executable Spring Boot JAR is typically at `build/libs/container-demo-0.0.1-SNAPSHOT.jar`. If the `jar` task also runs, `container-demo-0.0.1-SNAPSHOT-plain.jar` may exist alongside it. **A plain JAR cannot replace the Boot JAR in `java -jar`** when it lacks the Boot launcher and nested runtime dependencies.

## 5. Multi-Stage Maven Dockerfile: JDK Builds, JRE Runs

Create `Dockerfile.maven` (Linux containers):

```dockerfile
# syntax=docker/dockerfile:1

# ----- STAGE 1: Build application using a JDK -----
FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /workspace

# Copy Maven Wrapper and POM first for dependency-layer caching.
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

RUN chmod +x mvnw && ./mvnw -B -ntp dependency:go-offline

# App source changes more often than POM/dependencies.
COPY src/ src/

# Compile, execute tests, and create the executable Spring Boot JAR.
RUN ./mvnw -B -ntp clean package \
    && test -f target/container-demo-0.0.1-SNAPSHOT.jar \
    && cp target/container-demo-0.0.1-SNAPSHOT.jar /tmp/app.jar

# ----- STAGE 2: Run application using a JRE -----
FROM eclipse-temurin:17-jre-jammy AS runtime
WORKDIR /app

# This example uses Ubuntu-based Temurin images with useradd/groupadd.
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --from=build --chown=10001:10001 /tmp/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

### 5.1 Reading the Maven Dockerfile Part by Part

- `FROM eclipse-temurin:17-jdk-jammy AS build`: creates a stage named `build` using JDK 17 to run the Maven Wrapper, Java compiler, and tests.
- `WORKDIR /workspace`: sets a fixed working directory; subsequent relative `COPY`/`RUN` instructions use it.
- `COPY .mvn/ .mvn/` and `COPY mvnw pom.xml ./`: brings the Maven Wrapper files and POM into the build stage. They are **not** copied to the runtime stage.
- `RUN chmod +x mvnw`: ensures the script is executable in the Linux image. If `mvnw` has wrong CRLF line endings, fix the line endings in the repository; do not treat `chmod` as a newline fix.
- `dependency:go-offline`: attempts to pre-download common plugins/dependencies to benefit from layer caching when source changes. It does not guarantee all plugins/test providers in every project are preloaded; `package` may still need network access or missing artifacts.
- `COPY src/ src/`: copies main and test source into the build stage; changing Java code invalidates later steps while usually keeping the earlier dependency layer.
- `./mvnw ... clean package`: builds and **runs tests per the default lifecycle**. The example **does not** add `-DskipTests`.
- `test -f ...jar`: fails fast if the filename differs from expectations or `repackage` did not create the main archive.
- `cp ... /tmp/app.jar`: normalizes the handoff path so the final stage does not depend on a dynamic versioned filename.
- `FROM eclipse-temurin:17-jre-jammy AS runtime`: starts a **fresh** filesystem containing only the base JRE and what is declared afterward.
- `groupadd/useradd`: creates UID 10001 so the Java process does not run as root.
- `COPY --from=build --chown=10001:10001`: copies **only the path-verified executable JAR** to runtime.
- `USER 10001:10001`: subsequent instructions/runtime execute with this privilege unless overridden.
- `EXPOSE 8080`: documents the port the app is expected to listen on; **does not publish the port to the host**.
- `ENTRYPOINT ["java","-jar",...]`: uses exec form to launch the Java process, aiding cleaner signal handling without an unnecessary wrapper shell.

This is a **complete Dockerfile** for the sample Maven project with an existing Wrapper, files at the expected paths, a Docker daemon/BuildKit, and network access to download dependencies. Docker **cannot** be assumed able to build if a private Maven repository requires unprovided credentials.

### 5.2 Building the Maven Image

From the Maven project root:

```bash
docker build -f Dockerfile.maven -t container-demo:maven .
```

The trailing `.` is the **build context**. Docker only copies files in the context allowed by `.dockerignore`. If the Dockerfile is placed outside the root or the build context lacks `pom.xml`/`src/`/`mvnw`, `COPY` will fail; fix the path or context properly rather than arbitrarily copying the entire disk.

### 5.3 Running a Smoke Test on the JRE Image

```bash
docker run --rm -d \
  --name container-demo-maven-test \
  -p 18080:8080 \
  container-demo:maven

# Once the application has started:
curl --fail --silent --show-error http://localhost:18080/hello

# View logs if the application does not respond:
docker logs container-demo-maven-test

# Stop the test container:
docker stop container-demo-maven-test
```

When the server is ready, the expected HTTP response body is:

```text
Hello from Spring Boot
```

This is **the output returned by the Java method per the sample code**, not a log from a live run. Because the container is created with `--rm`, Docker automatically deletes it after `docker stop`. If you change the name, port, or container ID, adjust the commands accordingly.

If host port 18080 is already in use, change the **left side** of `-p 18080:8080`, e.g., `18081:8080`; the right side must match the port Spring Boot actually listens on inside the container.

### 5.4 Why Does the Final Image Have No Maven Cache or Source?

`COPY --from=build /tmp/app.jar /app/app.jar` copies **a single file**. It does not automatically copy `/workspace/src`, `/workspace/.mvn`, `/root/.m2`, or `/tmp` from the build stage. Those files may remain in Docker's build cache on the builder/CI machine, but they are **not part of the final stage's filesystem**.

However, if you accidentally write `COPY --from=build /workspace /app`, source code and build scripts enter the final image. Multi-stage builds do not automatically protect against an overly broad `COPY`; reviewing paths is mandatory.

## 6. Multi-Stage Gradle Dockerfile: The Equivalent Approach

Create `Dockerfile.gradle` for the **sample Gradle project**:

```dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /workspace

# Include the wrapper distribution definition and build scripts.
COPY gradle/ gradle/
COPY gradlew settings.gradle build.gradle ./
RUN chmod +x gradlew

# Resolve dependencies before copying frequently changing app sources.
RUN ./gradlew --no-daemon dependencies --configuration runtimeClasspath

COPY src/ src/

# build runs checks/tests and creates executable Boot JAR.
RUN ./gradlew --no-daemon clean build \
    && test -f build/libs/container-demo-0.0.1-SNAPSHOT.jar \
    && cp build/libs/container-demo-0.0.1-SNAPSHOT.jar /tmp/app.jar

FROM eclipse-temurin:17-jre-jammy AS runtime
WORKDIR /app

RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --from=build --chown=10001:10001 /tmp/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

### 6.1 Differences from the Maven Stage

- `gradle/` contains the Gradle Wrapper JAR and `gradle-wrapper.properties`; `gradlew` is the wrapper script. **Do not exclude `gradle/` via `.dockerignore`**, or the Wrapper will fail to start.
- `RUN ./gradlew --no-daemon dependencies --configuration runtimeClasspath` is a preload/graph-read step that can aid layer caching; it **does not guarantee** all test/plugin dependencies are downloaded. The `build` run may still require network access.
- `./gradlew --no-daemon clean build` runs compile, test, and assemble; the Spring Boot Gradle plugin wires `bootJar` into the build lifecycle properly. Running only `bootJar` **does not** run all tests by default; therefore the example uses `build`.
- Gradle may produce both `container-demo-...jar` and `container-demo-...-plain.jar`. `test -f` + `cp` picks the **exact non-classifier name** of the sample Boot JAR; do not use `COPY .../*.jar` when multiple files exist.
- `--no-daemon` requests not keeping a long-lived Gradle daemon in the build container; Gradle may still fork a single-use daemon under certain toolchain/JVM args, which is cleaned up after the command.
- The runtime stage matches Maven's: **JRE 17, `app.jar`, and user 10001**, with no Gradle in the final image.

Build and run:

```bash
docker build -f Dockerfile.gradle -t container-demo:gradle .

docker run --rm -d \
  --name container-demo-gradle-test \
  -p 18081:8080 \
  container-demo:gradle

curl --fail --silent --show-error http://localhost:18081/hello

docker stop container-demo-gradle-test
```

**`curl` may fail if run too early.** Wait for the app to be ready using time-bounded polling/health checks and inspect `docker logs` on error; do not use a fixed `sleep 2` as proof of startup success.

### 6.2 If the Project Uses Gradle Kotlin DSL

The Dockerfile above copies `settings.gradle`/`build.gradle`; for Kotlin DSL, adjust:

```dockerfile
COPY gradlew settings.gradle.kts build.gradle.kts ./
```

and the build scripts must be the corresponding `.kts` files. If the project has `gradle.properties`, a `gradle/libs.versions.toml` version catalog, `buildSrc`, included builds, or source generation scripts, copy those inputs into the build stage at the right paths before running tasks. Do not use a minimal Dockerfile to assume a complex monorepo needs only `src` and one build file.

### 6.3 If the Project Has Multiple Gradle Modules

Suppose the application lives in `:app`. The task and artifact path might be:

```bash
./gradlew :app:build
```

```text
app/build/libs/app-0.0.1-SNAPSHOT.jar
```

Names are illustrative, not fixed paths for every project. The Dockerfile must:

1. Copy `settings.gradle` and the subprojects/build scripts used.
2. Run `:app:build` or the appropriate task graph.
3. Identify the **app module's** Boot executable JAR, not mistaking `:core`'s plain/library JAR.
4. Copy the exact output to `/tmp/app.jar` before the runtime stage.

Do not use `find . -name '*.jar' | head -1` to select a release artifact.

## 7. `.dockerignore` and Build Context: Speed Up, Avoid Unwanted Data

A `.dockerignore` suitable for the sample project:

```dockerignore
.git/
.gitignore
.idea/
.vscode/
*.iml

target/
build/
.gradle/
out/
logs/
*.log

.env
.env.*
*.pem
*.key
**/secrets/
**/credentials/

node_modules/
.DS_Store
Thumbs.db
```

Depending on your project, add rules for other sensitive files or generated folders. **Do not** ignore `gradle/` (Gradle Wrapper), `.mvn/`, `pom.xml`, `build.gradle`, `settings.gradle`, or `src/` if the Dockerfile needs to copy them.

### 7.1 Do Not Confuse `.gradle/` with `gradle/`

- `.gradle/`: usually holds local project caches and execution history; no need to copy from the host.
- `gradle/`: usually holds the Wrapper JAR/properties and possibly the version catalog, **required** to run the Gradle Wrapper in Docker when the project uses that layout.

Similarly:

- `.mvn/` holds Maven Wrapper configuration (and possibly extensions/config), needed when using `mvnw`.
- `~/.m2/repository` is the build machine's dependency cache; normally you should not copy all of it from the host into a Docker image.

### 7.2 Keep Secrets Out of the Build Context

`.dockerignore` reduces risk, but it is **not a secret manager**:

- Do not commit secrets in source code.
- Do not pass production credentials via Dockerfile `ARG`/`ENV` and treat them as invisible.
- For private Maven repositories or dependency proxies needing tokens, use **BuildKit secret mounts** per policy rather than passing passwords on the Docker build command line or in layers.
- Do not print tokens in logs.
- Protect builder/CI caches, especially if using a remote cache.
- Do not copy `~/.ssh` or your home directory into the build context.

If source contains secrets, merely excluding them from the final JRE stage is not enough to prevent them from appearing in build caches or logs.

### 7.3 Runtime-Only Dockerfiles Have Different Context Needs than Multi-Stage

If you **build the JAR on the host/CI first**, the Dockerfile only copies the produced artifact. In that case, `.dockerignore` **must not exclude the artifact path** the Dockerfile needs. For example, a Dockerfile copying `release/app.jar` needs the `release/` directory in the context; do not ignore it or copying from the host will fail.

In the multi-stage Dockerfiles in Sections 5–6, `target/` and `build/` on the host can be ignored because the artifact is **created inside the build stage**.

## 8. Another Option: CI Builds the JAR, Then a Runtime-Only Dockerfile

Docker does not always have to compile Java. A pipeline can:

1. Use a runner with a JDK + Maven/Gradle to compile and test.
2. Publish a **verified executable Spring Boot JAR**.
3. Run a Docker image stage that copies only this artifact into a JRE image.

Example `Dockerfile.runtime`:

```dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --chown=10001:10001 release/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This is a **runtime-only** Dockerfile with no JDK stage. Before `docker build`, the pipeline must place the **exact built/tested JAR** at `release/app.jar` in the build context. If the file is missing, `docker build` fails at `COPY` — a useful check, not an error to work around by copying an arbitrary JAR.

Build:

```bash
# After CI has built, verified, and staged release/app.jar:
docker build -f Dockerfile.runtime -t container-demo:runtime-only .
```

Comparison:

| Approach | Where Java Build Happens | Final Image Has JDK? | Pros | Things to Manage |
| --- | --- | --- | --- | --- |
| Docker multi-stage | JDK stage inside Docker build | No, JRE only if configured right | Centralized packaging workflow, easy to reproduce on a Docker host | Cache/build secrets, Docker context, build time |
| CI build first + runtime-only | Runner/agent with JDK | No | Clear separation of testing and image packaging, reuses verified artifact | Must prove the staged file is the QA-passed artifact |
| Single-stage JDK | Inside final image | Yes | Simple for labs/dev or runtimes requiring a JDK | Image includes compiler/caches/source if broadly copied |
| Buildpacks | Buildpack lifecycle/builder | Launch image typically runtime-only | Plugin can create optimized layered images | Must understand buildpack builder/run image, toolchain, and configuration |

**Choose based on goals:** multi-stage is a solid default for many Dockerfiles, while runtime-only makes sense when CI already has controlled build/test steps and tracks artifact identity/checksums.

## 9. Verifying in Practice: What Do the JDK and JRE Images Contain?

### 9.1 Comparing `java` and `javac` Across Base Images

```bash
# Both images have the Java runtime.
docker run --rm --entrypoint java eclipse-temurin:17-jdk-jammy -version
docker run --rm --entrypoint java eclipse-temurin:17-jre-jammy -version

# The JDK image has the Java compiler.
docker run --rm --entrypoint javac eclipse-temurin:17-jdk-jammy -version
```

On the illustrative Ubuntu/Jammy images that include a shell, you can check for the compiler in the JRE using:

```bash
docker run --rm --entrypoint sh eclipse-temurin:17-jre-jammy \
  -c 'if command -v javac >/dev/null 2>&1; then echo "javac found"; else echo "javac absent"; fi'
```

For a properly scoped JRE tag, the **expected** stdout of this check script is:

```text
javac absent
```

This is a **conditional expected result**, not live output from a currently running container. Other runtimes might include a compiler or lack a shell, in which case the inspection method must change.

### 9.2 Inspecting the Final Image Built from the Dockerfile

```bash
docker image inspect container-demo:maven --format '{{.Config.User}}'
docker image inspect container-demo:maven --format '{{.Config.Entrypoint}}'
docker image inspect container-demo:maven --format '{{.Architecture}}'
docker image history container-demo:maven
```

Following the lesson's Maven Dockerfile, `Config.User` is expected to be `10001:10001` and `Entrypoint` is expected to be `[java -jar /app/app.jar]` in Docker template representation. Formatting syntax and output display may vary by CLI version.

**`docker image history` describes only layers of the tagged final image**; it does not automatically list the entire filesystem of intermediate build stages. For deep auditing, use an organization-approved image inspection/SBOM/security scanner.

### 9.3 Verifying the Final Stage Lacks `javac`, Maven, or Gradle

```bash
docker run --rm --entrypoint sh container-demo:maven \
  -c 'command -v java; command -v javac || true; command -v mvn || true; command -v gradle || true'
```

With an Ubuntu JRE runtime image, `java` should be found; `javac`/`mvn`/`gradle` are normally absent. This command **only checks `PATH`**; it does not prove the entire filesystem is completely free of related files. To check thoroughly, inspect image packages/SBOM instead of extrapolating from `command -v`.

Do not use similar `sh` commands against a shell-less distroless image; use a debug image/sidecar or external inspection tools.

### 9.4 Comparing Image Sizes Without Inventing Numbers

```bash
docker image ls eclipse-temurin
docker image ls container-demo
docker image inspect eclipse-temurin:17-jdk-jammy --format '{{.Size}}'
docker image inspect eclipse-temurin:17-jre-jammy --format '{{.Size}}'
```

**Do not assert fixed MB counts**: base images, OS flavors, architectures, and patch dates change sizes. Usually a JRE image of the same family/flavor is smaller than the JDK, though this is not a law across all images/vendors.

Image size alone cannot determine **startup performance, memory footprint, or security**. JRE and JDK images using the same JVM line can consume similar CPU/heap for an app; performance claims require measuring actual processes under valid comparison conditions.

## 10. Why Doesn't `EXPOSE 8080` Make HTTP Accessible Yet?

In a Dockerfile, `EXPOSE` declares a port the application intends to use. It is metadata/documentation; **it does not open a host port**.

Run the app:

```bash
docker run --rm -d \
  --name container-demo-port-test \
  -p 18080:8080 \
  container-demo:maven
```

- `18080` is the **host port**.
- `8080` is the **container port**, where Spring Boot's embedded Tomcat listens by default.
- `curl http://localhost:18080/hello` from the host routes through the port mapping.
- If Spring Boot is configured with `server.port=9090`, change the container side of `-p` to `9090`.
- If the app binds `server.address=127.0.0.1` **inside the container**, traffic from Docker port publishing may not reach it. Typically the server needs to bind on an appropriate interface (`0.0.0.0`) to accept connections from outside the container.

Run in another terminal:

```bash
curl --fail --silent --show-error http://localhost:18080/hello
docker logs container-demo-port-test
docker stop container-demo-port-test
```

**There is no HTTP endpoint difference caused by JDK vs JRE**, provided the runtime has the required Java modules, native libs, and identical app configuration. The difference is **which tools exist inside the image**, not whether `@GetMapping` controller logic works.

## 11. Runtime Security: Non-Root, Base Images, Secrets, and Write Permissions

### 11.1 Running Java as a Non-Root User

The example Dockerfile sets:

```dockerfile
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --from=build --chown=10001:10001 /tmp/app.jar /app/app.jar
USER 10001:10001
```

The goal is to restrict the Java process's privileges. By default, a Docker container **is not an absolute security sandbox**; non-root reduces risk if the app is exploited or has a filesystem-write bug.

Key points to understand:

- UID/GID inside the image can interact with permissions on host-mounted volumes.
- The `/app` directory is typically created by root; in the example, the JAR belongs to UID 10001 and is readable, yet the app cannot write arbitrarily into `/app`.
- If the app writes uploads/logs/cache into `/app`, create a writable directory and assign deliberate permissions or mount a volume per policy.
- If using a privileged port below 1024, a non-root process may require special capabilities/permissions; using 8080 keeps things simpler.
- Never remove `USER` and switch runtime to root just to fix a filesystem error; fix permissions on the exact path that needs writes.

### 11.2 Secrets Must Not Enter Image Build Arguments

Do not write:

```dockerfile
# Unsafe example, DO NOT use:
ARG DB_PASSWORD
ENV DB_PASSWORD=hardcoded-password
```

Secrets can surface in build metadata, layers, logs, image inspection, or container environments if mismanaged. Instead use your deployment environment's secret manager; when credentials are needed in the **build stage** to download private Maven dependencies, use a BuildKit secret mount or an approved mechanism.

Spring Boot reads environment variables/runtime configuration via externalized configuration. Still, **passing a password via `docker run -e ...` is not by itself a secure secret manager**: on a host or CI runner where users can inspect processes/containers, the value can be exposed. For production, use dedicated secret injection per organizational standards.

### 11.3 Updating the Base Image

Tags like `17-jre-jammy` can be updated by the publisher when patches arrive. Therefore:

- Pin a **digest** when strict reproducibility/auditing is required.
- Update the digest periodically through a review and testing process rather than keeping patched CVEs indefinitely.
- Scan the base image, application dependencies, and final image.
- Do not assume a "smaller" image means "zero CVEs."
- Look beyond the Java version; OS libraries also have CVEs.
- Ensure registry provenance and multi-architecture manifests comply with policy.

Digest pinning syntax example (fill in a **real** digest verified by registry/CI):

```dockerfile
# Illustrative syntax: do not use placeholder text as a real digest.
FROM eclipse-temurin:17-jre-jammy@sha256:<verified-image-digest>
```

This is a **syntax template**, not a verbatim buildable Dockerfile. Use the provided tag to run the examples; production can substitute a verified digest.

### 11.4 Read-Only Filesystem

A runtime container can run with a read-only root filesystem if the application and libraries only write to permitted mounts. Lab **example** to try:

```bash
docker run --rm -d \
  --name container-demo-readonly \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 18082:8080 \
  container-demo:maven
```

Some Spring Boot embedded servers, logging libraries, TLS, or app components may need to write temporary files; `--tmpfs /tmp` provides temporary scratch space. However, other requirements might conflict with `noexec` or the 64 MiB limit. **Do not treat this snippet as a universal mandate**; test your real app and adjust mounts/capabilities/temp directories as needed.

### 11.5 The Runtime Image Must Have Required CA/Locale/Timezone Data

JRE images vary in:

- CA truststore and handling of custom corporate CAs.
- TLS providers/cipher suites.
- Locale, timezone data, and font rendering.
- Native libraries, JNI, and file permissions.
- DNS resolver/runtime network stack.

If the app makes outbound HTTPS calls and hits `SSLHandshakeException` because an internal CA is untrusted, never fix it by disabling certificate validation. Import the CA certificate into the **truststore/runtime image following the vendor's method**, or mount/configure a valid truststore.

A minimal JRE image may omit `sh` and `curl`; healthchecks should use **tools present in the runtime** or external orchestrator probes. Do not add full build tools back into the image just to run a `curl` healthcheck if a lighter/safer method exists.

## 12. Does Replacing JDK with JRE Make the App Slower?

Performance cannot be inferred solely from the labels JDK vs JRE.

- The same Temurin Java 17 family shares a very similar JVM. JIT, GC, and bytecode execution remain present.
- JRE images typically omit tools, so **download size and image footprint** can decrease.
- **Heap/RSS/CPU** depend on the application, JVM flags, container limits, GC, thread count, workload, and native libs, not just the tag name.
- Startup time is also affected by class loading, Spring bean count, disk/network, image layer cache, and warm-up; benchmark realistically.
- A JRE does not inherently make an app "less secure" or "completely secure"; patch management matters.

### 12.1 Tuning Memory to Container Limits

Java 17 includes container awareness suited to cgroups in supported environments. You can adjust the heap percentage via JVM flags if needed:

```bash
docker run --rm -d \
  --name container-demo-memory \
  --memory 512m \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65.0" \
  -p 18083:8080 \
  container-demo:maven
```

`JAVA_TOOL_OPTIONS` is read by the Java launcher and may be printed by the JVM to logs. Not every application should use 65%: native memory, Metaspace, thread stacks, direct buffers, and GC overhead all need room. If a container is `OOMKilled`, inspect cgroup memory, JVM native memory, and application behavior before raising heap blindly.

Also distinguish **Docker image size** from **container memory usage**: removing JDK tools from the filesystem does not directly reduce the heap used by Spring.

## 13. Controlling Artifacts: Avoiding Plain JARs or WARs by Mistake

### 13.1 Maven `.jar.original`

With default Spring Boot Maven `repackage`:

```text
target/container-demo-0.0.1-SNAPSHOT.jar
target/container-demo-0.0.1-SNAPSHOT.jar.original
```

The `.jar` file is the executable Boot JAR if `repackage` ran; `.jar.original` is the backed-up original archive. Placing `.jar.original` in the JRE runtime causes `java -jar` to fail without the launcher/runtime classpath.

If the POM sets a custom classifier such as `exec`, the executable file may be `...-exec.jar`, while the unclassified `.jar` is plain. The Dockerfile must update `cp` to the **exact right name** and verify the manifest/layout.

### 13.2 Gradle `-plain.jar`

With the Spring Boot Gradle plugin:

```text
build/libs/container-demo-0.0.1-SNAPSHOT.jar
build/libs/container-demo-0.0.1-SNAPSHOT-plain.jar
```

The `bootJar` task produces the executable Spring Boot JAR; the `jar` task produces a standard JAR using the `plain` naming convention. Therefore:

```dockerfile
# ERROR-PRONE when multiple artifacts exist:
COPY build/libs/*.jar /app/app.jar
```

is an example **not to use**. If the wildcard matches more than one JAR, `COPY` to a file destination can fail or behave unexpectedly; some pipelines also "pick the first file" and accidentally ship the plain JAR.

Explicitly pick the `bootJar` output, or configure a task to copy to `release/app.jar` after inspecting the ZIP:

```bash
jar tf build/libs/container-demo-0.0.1-SNAPSHOT.jar
```

Markers of an executable Boot JAR are `BOOT-INF/classes`, `BOOT-INF/lib`, and the Boot launcher; the JRE can run it only when the artifact has the proper entrypoint, dependencies, and runtime compatibility.

### 13.3 JAR vs WAR

If a project builds an **executable WAR** with `bootWar`, `java -jar app.war` can also run on a JRE when the WAR embeds the servlet runtime in `WEB-INF/lib-provided` and the Boot `WarLauncher`. However, a plain WAR deployed into external Tomcat is a different model; running it on a JRE image with `java -jar` is not the default.

This lesson **uses an executable JAR**; do not copy a `.war` and assume it shares the exact same Spring Boot loader/layout. If external Tomcat is required, a common architecture is **Tomcat runtime image + WAR deploy**; that is not "plain JRE with `java -jar`" unless intentionally using an executable WAR.

### 13.4 Artifact QA Flow

```text
JDK builder:
  source + Wrapper -> test -> bootJar/repackage
                         |
                         v
                  verify JAR path
                         |
                         v
                    /tmp/app.jar
                         |
                   COPY --from=build
                         |
                         v
JRE runtime:
                  /app/app.jar
                         |
                    java -jar
                         |
                  HTTP smoke test
```

All it takes is **one explicit artifact-identification step** to avoid file selection mistakes; you do not need to stuff the entire source repository into the final image just to debug which JAR was picked.

## 14. Docker Cache and Build Time

### 14.1 `COPY` Ordering Helps Reuse Dependency Layers

In the Maven Dockerfile:

```dockerfile
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -B -ntp dependency:go-offline

COPY src/ src/
RUN ./mvnw -B -ntp clean package
```

When only Java source is edited, steps before `COPY src` have a chance to reuse cache. Using `COPY . .` right at the start means a tiny source change can needlessly invalidate the dependency resolution layer.

In Gradle it is similar: copy Wrapper/build scripts before source, preload the graph, then copy source. Still, remember: Gradle/Maven plugins and dependencies may still need downloads during compile/test; `go-offline` or `dependencies` is not an absolute offline guarantee.

### 14.2 BuildKit Cache Mounts (Optional)

In a builder stage using BuildKit Dockerfile syntax, you can mount a Maven or Gradle cache to avoid re-downloading dependencies on builds where the instruction layer misses cache:

```dockerfile
# syntax=docker/dockerfile:1

# Snippet replacing RUN in the Maven builder:
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp clean package
```

Gradle:

```dockerfile
# syntax=docker/dockerfile:1

# Snippet replacing RUN in the Gradle builder:
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon clean build
```

These snippets **are not standalone Dockerfiles**; place them in the builder stage after proper `COPY` and `chmod`. `--mount=type=cache` works when Docker BuildKit supports it, and `target` must point to the exact cache directory of the build user.

Cache mounts **do not become filesystem layers of the final image**. However, the cache stays on the builder/CI machine, may contain artifact/repository metadata, and needs permission, retention, and trust controls. Do not store secrets in the cache as plaintext files and assume multi-stage builds make it safe.

### 14.3 Why `RUN clean` Does Not Mean "No Cache"

`./mvnw clean package` or `./gradlew clean build` deletes project workspace outputs inside the build stage and rebuilds them. Docker layer cache can still reuse the instruction if inputs have not changed, and BuildKit cache mounts still keep downloaded dependencies if configured.

**There are two distinct caches:**

- **Docker layer cache** at the Dockerfile instruction level.
- **Build tool caches** (Gradle dependency cache, task build cache, or Maven artifact repository) inside the builder/cache mount.

Do not confuse Gradle's `bootJar UP-TO-DATE` with a Docker layer cache hit; they are two separate caching systems. When measuring performance, record build mode, `--no-cache`, BuildKit cache mounts, and dependency fetches before comparing seconds.

### 14.4 Prioritize Correctness; Do Not Skip Tests for Speed

Some internet examples use:

```bash
./mvnw package -DskipTests
./gradlew bootJar
```

These two commands **are not equivalent** to running the test suite before release. Maven `-DskipTests` skips test execution; `bootJar` does not force `test` into the task graph. If a CI pipeline already has a separate trusted test step, build/package stages can be separated per policy; otherwise, run `mvn package` or `gradlew build` as shown in the lesson.

Do not compare "Docker JRE build is faster because we skipped tests" and credit the JRE: swapping JRE for JDK affects only the **runtime stage**, not compiler/test execution speed.

## 15. Cases Where a JRE Is Not Enough

Using a JRE for runtime is sensible for many standard Spring Boot apps, but not every Java application can run on a stripped runtime.

### 15.1 Applications Compiling Code at Runtime

Some systems dynamically generate/compile Java source, build DSLs via the Java compiler API, call `ToolProvider.getSystemJavaCompiler()`, or invoke `javac` at runtime. A JRE lacking `jdk.compiler` or `javac` will fail.

Do not "add `javac` by copying a single binary" because the compiler also needs other modules and libraries. The solutions are:

1. Verify whether runtime code compilation is truly necessary or can move to the build stage.
2. If needed, use a JDK runtime image or a verified custom runtime containing the compiler/modules.
3. Test that feature inside the **final image**, not only on a developer machine.

**Exception:** a library with its own compiler such as Janino can compile certain Java expressions without `javac`; therefore do not assume all "dynamic code" strictly requires a JDK — check the actual implementation.

### 15.2 `jar`, `jlink`, `jdeps`, and Debugging Tools

Commands like `jlink` to create custom runtimes, `jdeps` to analyze module dependencies, and `javac` to compile are normally only in the **JDK**.

- **Creating a custom JRE with `jlink`:** perform this in the **JDK builder** and copy the resulting runtime into a suitable final image; do not expect `jlink` inside a JRE.
- **Bytecode/JAR analysis:** run in CI or the build stage, not in production.
- **Investigating with debuggers/profilers:** JDK tools like `jcmd`, `jstack`, and `jmap` may be absent from a JRE runtime; use a diagnostic image/sidecar or dedicated debug image per procedure.
- **Troubleshooting:** is not a default reason to ship the entire toolchain inside every production container.

### 15.3 Over-Stripped Custom Runtimes Missing Java Modules

If you use `jlink` to trim Java modules, an app may lack `java.naming`, `java.sql`, `java.management`, `java.xml`, `jdk.crypto.ec`, or other modules depending on dependencies. Spring Boot and reflection/proxy/SSL/JDBC libraries can require modules not obvious from static analysis.

A custom JRE must be **tested with the real app**, not merely `java -version`. If startup or a runtime feature misses a module, the issue may be the custom runtime rather than the Spring Boot build plugin.

### 15.4 Native Images Are Not JRE Images

Spring Boot can be compiled into a **native executable** via GraalVM/Native Build Tools. In that case, the runtime image may **not need a JVM/JRE at all** if the native executable and native libraries are properly prepared. That is a **different pipeline** from an executable Boot JAR run with `java -jar`.

Do not copy this lesson's JRE Dockerfile to run a native binary and claim a JRE is required. Equally, do not use a GraalVM builder/JDK image to run a native app in production when the optimized architecture allows a different runtime.

## 16. Comparison with Cloud Native Buildpacks and Layered JARs

### 16.1 Buildpacks

Spring Boot supports building OCI container images via Maven/Gradle build plugins paired with **Cloud Native Buildpacks**:

```bash
# Maven project with suitable plugin/configuration
./mvnw spring-boot:build-image

# Gradle project with Spring Boot plugin
./gradlew bootBuildImage
```

Image names, Docker daemon setup, and actual builder/run images depend on configuration. Buildpacks organize build/launch phases using builder components, without requiring you to write a JDK/JRE Dockerfile identical to our examples.

Relevance to this lesson: whether using a manual Dockerfile or buildpacks, the goal remains **putting only necessary runtime components** into the app-running image. Do not infer that Buildpacks put a JDK into the runtime image just because the builder uses build tools.

### 16.2 Spring Boot Layered Executable JAR

Spring Boot 3.3 supports `BOOT-INF/layers.idx` and extracting contents into layers such as:

```text
dependencies/
spring-boot-loader/
snapshot-dependencies/
application/
```

Layers separate slowly changing dependencies from frequently changing application classes, aiding Docker layer caching when building images. **Layered JARs are a different optimization from JDK vs JRE**:

- JDK vs JRE governs **Java runtime/tooling** across stages.
- Spring Boot layers govern **how application contents are split** inside the runtime image.
- Both can be combined: a JDK builder creates the Boot JAR; a JRE/Java runtime stage extracts or receives the extracted layers.
- For Boot 3.3.13, the Dockerfiles documentation uses **`java -Djarmode=tools -jar app.jar extract`**; older Boot versions used the mode name `layertools` — do not mix commands across versions.

This is an advanced topic; **the two-stage Maven/Gradle Dockerfiles above are completely valid without extraction**. Only implement layer extraction once you have verified your Spring Boot plugin/loader produces a compatible archive.

### 16.3 Launch Script Caveat

Some Spring Boot executable archives can be configured with an embedded **fully executable launch script** to run like a Unix service. Spring Boot documentation warns that `tools` layer extraction mode is incompatible with a fully executable archive prepended with a launch script. If using a layered Dockerfile, disable the launch script or choose another approach.

There is no reason to enable a launch script just to run `java -jar` in this lesson's Dockerfile: `ENTRYPOINT ["java","-jar",...]` invokes the Java runtime directly.

## 17. CI/CD: Verifying the Final Image, Not Just the Builder

A pipeline should enforce these gates:

| Gate | What Is Checked? | Why Is It Needed? |
| --- | --- | --- |
| Java build/test | `mvn package`/`gradlew build` succeeds | App classes and tests are verified. |
| Executable artifact | Right Boot JAR, not `plain`/`original` | Runtime JRE can execute `java -jar`. |
| Image build | Docker multi-stage build succeeds | Artifact copied from builder to JRE stage. |
| Java runtime | `java -version` in final image, right major/platform | Prevents `UnsupportedClassVersionError`. |
| Tooling absence | No `javac`/Maven/Gradle unless required | Verifies minimal runtime stage. |
| Non-root | Expected `Config.User` and container process UID | Reduces default privileges. |
| Smoke test | HTTP `GET /hello` returns 200 and exact body | Proves app boots in the **final JRE image**. |
| Image scan | CVEs, dependencies/SBOM, base image policy | Smaller JRE does not mean vulnerability-free. |
| Provenance | Image digest, artifact hash, CI build metadata | Deploys the exact tested artifact. |
| Runtime permissions | File/config/temp dirs writable/readable as designed | Non-root does not crash app on writes. |

### 17.1 Example Bash Smoke Test Checking the HTTP Body

Assume `container-demo:maven` is already built. The following script is for a **lab environment** with Docker, curl, and port 18084 free; add CI cleanup policies if multiple jobs run concurrently:

```bash
#!/usr/bin/env bash
set -euo pipefail

image="container-demo:maven"
name="container-demo-ci-test"
url="http://localhost:18084/hello"

docker run --rm -d \
    --name "$name" \
    -p 18084:8080 \
    "$image" >/dev/null

cleanup() {
    docker stop "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

response=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    response="$(curl --fail --silent --show-error \
        --connect-timeout 2 --max-time 3 "$url" 2>/dev/null || true)"
    if [[ "$response" == "Hello from Spring Boot" ]]; then
        echo "PASS: JRE runtime image serves /hello"
        exit 0
    fi
    sleep 2
done

docker logs "$name" || true
echo "FAIL: HTTP smoke test did not become ready" >&2
exit 1
```

When the container is ready and the endpoint returns the exact body, the **expected line printed by the script** is:

```text
PASS: JRE runtime image serves /hello
```

This is **conditional stdout**, not a log captured from the learner's environment. On startup/port/container image failure, the script fails; inspect `docker logs`. In parallel CI, allocate unique container names and host ports per job to avoid collisions.

### 17.2 Verifying Artifact and Image Identity

You can retrieve the image ID/digest via the Docker CLI:

```bash
docker image inspect container-demo:maven --format '{{.Id}}'
docker image inspect container-demo:maven --format '{{.Config.User}}'
docker image inspect container-demo:maven --format '{{.Architecture}}'
```

If pushing the image to a registry, the manifest digest **after push** is the registry reference production should pull per policy. Do not rely solely on `:latest`/`:maven` tags as unique identifiers; tags can be reassigned.

In a multi-stage Dockerfile, build-stage artifacts are not published independently. Export only the final image after gates pass and store necessary build/test logs. If a deploy stage **rebuilds** from source and reuses the same tag, it may not be the scanned/tested image; promote by the same digest.

### 17.3 Security Means More Than Scanning the Final Base

Evaluate:

- Final image OS packages/JRE runtime.
- Application `BOOT-INF/lib` dependency JARs and their CVEs.
- Supply chain of Maven/Gradle plugins, wrapper distributions, and download sources.
- Builder stage and pipeline credentials, since it has access to source and secrets.
- Image signing/provenance and patch update workflows.

Multi-stage builds separate the build toolchain from the final runtime, but they do not make the builder pipeline immune to supply-chain attacks.

## 18. Windows PowerShell and Windows Learners

Docker Desktop can run **Linux containers** on Windows; the `eclipse-temurin:17-...-jammy` Dockerfiles use Linux images. **Do not** mix with Windows container runtimes if the Docker daemon is in Windows containers mode or the OS/arch is unsupported.

Build the Maven image:

```powershell
docker build -f Dockerfile.maven -t container-demo:maven .
```

Build the Gradle image (on the corresponding Gradle project):

```powershell
docker build -f Dockerfile.gradle -t container-demo:gradle .
```

Run:

```powershell
docker run --rm -d --name container-demo-win-test -p 18080:8080 container-demo:maven
(Invoke-WebRequest -Uri "http://localhost:18080/hello").Content
docker logs container-demo-win-test
docker stop container-demo-win-test
```

The expected `.Content` result is the string `Hello from Spring Boot` if the app is running. Do not put PowerShell commands `.\mvnw.cmd` or `.\gradlew.bat` **inside a Linux Dockerfile**: a Linux build stage needs `./mvnw` and `./gradlew`. Outside Docker, Windows developers can use the `.cmd`/`.bat` wrappers for local compilation/testing.

Check Java version:

```powershell
docker run --rm --entrypoint java eclipse-temurin:17-jre-jammy -version
docker image inspect container-demo:maven
```

If `COPY mvnw` into a Linux image reports `/bin/sh^M: bad interpreter`, check Git line endings and convert `mvnw`/`gradlew` to LF. Do not work around this by running Windows batch scripts inside a Linux container.

## 19. Common Errors and Troubleshooting Methods

| Symptom | Likely Cause to Check | Evidence and Fix |
| --- | --- | --- |
| Docker `COPY mvnw`/`COPY gradlew` reports file not found | Wrong build context or `.dockerignore` excludes Wrapper | Run `docker build` from proper root, check context and filenames |
| `./mvnw: Permission denied` | Script not executable in Linux image | `RUN chmod +x mvnw`, fix Git file mode if needed |
| `/bin/sh^M: bad interpreter` | Wrapper has CRLF in Linux image | Convert EOL to LF on `mvnw`/`gradlew` |
| Maven/Gradle downloads dependencies slowly on every build | Cache layer invalidated, slow repo, missing BuildKit cache | Copy build scripts before source, check cache mounts and network |
| Maven `dependency:go-offline` still needs network in `package` | Goal does not preload all plugins/artifacts or dependency changed | Read exact missing artifact error, do not assume strict offline |
| Gradle `dependencies` insufficient for offline build | Different test/plugin/annotationProcessor configuration | Prewarm relevant configuration or allow controlled network build |
| JDK builder reports `Unsupported class file major version` | Gradle/Maven/plugin/compiler running wrong Java version | Check builder `java -version`, Wrapper/plugin compatibility |
| JRE runtime reports `UnsupportedClassVersionError` | Bytecode compiled for newer Java than runtime | Align toolchain/release and JRE major, rebuild |
| `no main manifest attribute` or missing Boot loader | Copied plain JAR by mistake or Maven did not repackage | Check `jar tf`/manifest of source artifact |
| Gradle wildcard `COPY` puts multiple JARs into target path | Both `-plain.jar` and Boot JAR exist | Explicitly select `bootJar` output |
| Maven copies `.jar.original` | That is the pre-repackage archive | Select executable JAR matching plugin config |
| Builder has `javac` while runtime does not | **Intended design** of JDK→JRE multi-stage | Only a bug if the app truly needs runtime compilation |
| Runtime reports missing `mvn`/`gradle` | Build tools were not copied to final image | Expected when production only runs `java -jar` |
| `java -jar` throws `NoClassDefFoundError` | Artifact lacks runtime dependencies or custom Java modules missing | Check `BOOT-INF/lib`, dependency graph, JRE modules |
| App needs `ToolProvider.getSystemJavaCompiler` and fails | JRE lacks compiler module/tool | Needs JDK/custom runtime or move compilation to builder |
| `exec /app/start.sh: not found` in minimal JRE image | Missing shell/script or CRLF, wrong shebang | Use exec-form `ENTRYPOINT ["java",...]` or a shell-equipped base |
| Container starts then immediately exits | Spring startup failure, port conflict, missing env/secret | `docker logs`, exit code, health/HTTP probe |
| HTTP 404 at `localhost:18080/hello` | Wrong port mapping, Spring context path, or controller mapping | Check `-p`, `server.servlet.context-path`, route, and logs |
| HTTP connection refused | Server not ready, wrong bind address/port, or container exited | `docker ps`/`docker logs` and polling with timeout |
| Image runs as root despite Dockerfile `USER` | User set in another stage or overridden at runtime | `docker image inspect Config.User`/runtime UID |
| `Permission denied` writing `/app` | Non-root lacks volume/dir permissions | Grant specific permissions, mount writable dir, do not blindly run as root |
| TLS `PKIX path building failed` | Missing CA or different truststore across images | Install CA properly, do not disable TLS verification |
| App fails on JNI/native library | Base OS libc/architecture or native package incompatible | Check platform, OS flavor, required `.so`/JNI |
| Small image yet many CVEs | Unpatched OS package/JRE or vulnerable dependency in JAR | Scan and update digest/tag, review app dependencies |
| Docker build `exec format error` on ARM/x86 | Image or native binary architecture mismatch | Check `--platform` and manifest list, use compatible image |
| Final image still contains build artifacts | `COPY --from=build /workspace ...` too broad | Copy only the exact executable JAR/required runtime files |
| Source edited yet image runs old code | Docker cache, stage copying old artifact, or wrong tag deployed | Verify SHA/image ID, build logs, and actual artifact |
| Web tests pass during build but JRE runtime fails | Tests ran only on JDK builder | Must smoke-test the **final JRE image** |
| Slow image startup | Warm-up/JIT, I/O, dependencies, CPU/memory limits | Measure real runtime; do not automatically blame JRE |
| Docker daemon cannot build Jammy image on Windows | Daemon is in Windows containers mode | Switch to Linux containers or use OS-compatible base |
| Custom `jlink` runtime fails with missing module | Missing Java modules | Check `jdeps`, test real features, add required modules |
| Docker `HEALTHCHECK curl` fails | Runtime image lacks curl/shell | Use external HTTP probe or intentionally install tool |
| Image tag changes silently | Mutable tag updated by publisher | Pin digest, manage update cadence/signed provenance |
| Tests skipped in Docker builder | Used Maven `-DskipTests` or only `gradlew bootJar` | Run CI tests separately or `mvn package`/`gradlew build` with tests |

### Evidence-Based Diagnostic Process

1. **Build stage:** right JDK image, valid Wrapper, Java/toolchain version? Did the error happen before or after `COPY src`?
2. **Artifact:** does the executable JAR exist? Does it have Boot loader, `BOOT-INF/classes`, and `BOOT-INF/lib`? Exact filename?
3. **COPY boundary:** does the final image have `/app/app.jar`, byte-identical to the builder's file? Any extra source/cache copied?
4. **Runtime:** is `java -version` in the JRE image the right major and platform? Are required modules, CAs, and native libs present?
5. **Process:** are user ID, entrypoint, filesystem permissions, environment, and memory limits right?
6. **Network:** are Spring Boot's listening port, port mapping, and HTTP endpoint right? Is the app ready?
7. **Supply chain:** have image digest, vulnerability scan, and dependency/JAR provenance passed gates?

**Do not simultaneously change the Dockerfile, Java version, POM, and image tag before identifying which layer failed.** Change one variable in a lab environment to isolate, then promote the verified fix to the pipeline.

## 20. Exercises from Basic to Advanced

### A. Identify JDK/JRE Components

1. Pull/run `eclipse-temurin:17-jdk-jammy` and `17-jre-jammy`.
2. Run `java -version` on both, and `javac -version` on the JDK.
3. Check whether the JRE has `javac` on `PATH` using a conditional shell command.
4. Record the OS/architecture of the images and explain what `17`, `jdk`, `jre`, and `jammy` mean.
5. Answer: why can the JDK still run apps while the JRE is not used to compile standard source?

### B. Maven Multi-Stage

1. Create project `container-demo` using the POM/Java/test from Section 4.
2. Use a proper Maven Wrapper and `Dockerfile.maven` from Section 5.
3. Build image `container-demo:maven`.
4. Inspect the build log and confirm Maven tests ran (without `-DskipTests`).
5. Run the container on host port 18080, GET `/hello`, verify body `Hello from Spring Boot`.
6. Enter the final image with the example's `--entrypoint sh` command and verify `mvn`/`javac` are absent.
7. Explain why Maven dependency caches in the builder do not need to be copied to the runtime image.

### C. Gradle Multi-Stage

1. Create an equivalent Gradle project with `settings.gradle`/`build.gradle` and Wrapper.
2. Build with `Dockerfile.gradle`, verifying the executable Boot JAR is not `-plain.jar`.
3. Run the container and test `GET /hello`.
4. Add a harmless Java method, rebuild the image to observe which Docker layers are reused.
5. Answer: how does `./gradlew bootJar` differ from `./gradlew build` regarding tests?
6. Try changing `build.gradle` or a dependency version on a lab branch and note why the dependency cache layer invalidates.

### D. Prebuilt JAR and Runtime-Only

1. On CI/local JDK, build and test the project first.
2. Copy the verified executable artifact to `release/app.jar` in the build context.
3. Use `Dockerfile.runtime` and make sure `.dockerignore` does not exclude `release/app.jar`.
4. Build the runtime-only image, call `GET /hello`, and compare output with multi-stage.
5. Answer: which approach makes it easier to guarantee the **exact same artifact** from the test stage is deployed when the pipeline tracks digests?

### E. Security and Permissions

1. Inspect `Config.User` of the final image: you should see the UID/GID from the Dockerfile.
2. In a lab, try `--read-only --tmpfs /tmp`; verify the app works or inspect error logs.
3. Explain why secrets must not go into Dockerfile `ARG`/`ENV`.
4. Review base image digest, CVE scan, and update schedule.
5. Distinguish reducing package count from guaranteeing zero vulnerabilities.

### F. Changing Java/Runtime and Catching Errors Early

1. Record the Java major version of the compiler and runtime base image.
2. On a lab branch, change the compiler target to a newer Java than the runtime (do not deploy to production), and observe the `UnsupportedClassVersionError` that can occur.
3. Revert both JDK and JRE to Java 17.
4. Explain why a Java 17 runtime cannot run target-21 bytecode and why changing only the Docker tag does not fix the compiler target.
5. If using JNI/TLS, list additional factors beyond Java major version to verify.

### G. Inspecting a Real Image

Create a structured report:

```text
Project name:
Build system: Maven / Gradle
Build image ref:
Runtime image ref:
Java major/toolchain target:
OS distribution/architecture:
Dockerfile path:
Build command:
Did tests run? Evidence:
Executable JAR path before copy:
Source task: bootJar / spring-boot:repackage
Final /app/app.jar exists:
Final user UID/GID:
java -version in final:
javac present in final?:
mvn/gradle present in final?:
Host port mapping:
HTTP /hello status:
HTTP /hello body:
Image digest after push:
Findings and next action:
```

**This is a template for recording measured values**, not a pre-filled PASS report. If no Docker daemon is available, you can complete the Dockerfile and dependency graph analysis, but you must explicitly note that **image execution and HTTP smoke testing were not performed**.

### H. Analyzing an Unoptimized Dockerfile

Given the following Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jdk-jammy
WORKDIR /code
COPY . .
RUN ./gradlew bootJar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/code/build/libs/container-demo-0.0.1-SNAPSHOT-plain.jar"]
```

Tasks:

1. Point out the issues with **single-stage JDK**, `COPY . .`, and no `.dockerignore`.
2. Distinguish `bootJar` from `build`/`test`.
3. Explain why `-plain.jar` can cause `java -jar` to fail.
4. Rewrite it using **JDK builder + JRE runtime**, copying only the Boot executable artifact.
5. Add a non-root user and verify port mapping.
6. Provide at least two pieces of evidence: the compiler is in the builder and unneeded at runtime, and the JRE image's HTTP endpoint works.

**Pass criteria:** do not just memorize the names `jdk`/`jre`; you must explain why **the compiler belongs to build** and **the Java runtime belongs to final**, recognize **the limits of multi-stage builds**, select the right Spring Boot executable artifact, and run a real smoke test on the final JRE image.

## 21. Official Documentation

- Docker Docs — Multi-stage builds, `FROM ... AS` and `COPY --from`: https://docs.docker.com/build/building/multi-stage/
- Docker Docs — Dockerfile reference, `FROM`/`COPY`/`USER`/`EXPOSE`/`ENTRYPOINT`: https://docs.docker.com/reference/dockerfile/
- Docker Docs — Build best practices, layer caching and pinning image digests: https://docs.docker.com/build/building/best-practices/
- Docker Docs — BuildKit cache mounts: https://docs.docker.com/build/cache/optimize/
- Docker Docs — `.dockerignore` and build context: https://docs.docker.com/build/building/context/#dockerignore-files
- Docker Official Image — Eclipse Temurin, JDK/JRE tags and custom Java runtime notes: https://hub.docker.com/_/eclipse-temurin
- Eclipse Adoptium — Temurin containers: https://adoptium.net/installation/containers/
- Spring Boot 3.3.13 — Dockerfiles and layered JAR (`jarmode=tools`): https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3 — Gradle Plugin Packaging Executable Archives (`bootJar`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Maven Plugin Packaging Executable Archives (`repackage`): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Cloud Native Buildpacks: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/cloud-native-buildpacks.html
- Oracle/OpenJDK — Java Platform Module System and `jlink`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html

**Conclusion:** A **JDK** image is an environment with the Java compiler and development tools for **building, testing, and packaging**; a **JRE** image provides the Java runtime needed to **run** an executable Spring Boot JAR. Docker multi-stage builds use `FROM ... AS build` and `COPY --from=build` to separate these two responsibilities. Using a JRE final image avoids shipping toolchains, source code, and caches to production, yet **does not replace checks for Java/native module compatibility, security, access permissions, artifact identity, and HTTP smoke testing**. Success is only proven when **the exact executable JAR** is built with a JDK and **actually boots and serves requests on the final JRE image**.