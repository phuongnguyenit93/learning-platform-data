# Choosing Between Running a Whole JAR or Extracting Layers Before Building an Image

## 1. Decision Context and Goal

When deploying a Spring Boot application to Docker/Kubernetes, teams generally choose between two ways to build a container image from a **Spring Boot executable JAR**:

1. **Run the whole JAR (fat/uber JAR)**: copy the single built JAR file into the image and run `java -jar application.jar`.
2. **Extract layers before building the image**: use a **Spring Boot layered archive** and `jarmode=tools` to split dependencies, the loader, and application code; copy each group into separate Docker/OCI image layers, then run the **extracted JAR**.

Both approaches can deploy a Spring Boot application functionally. The first has fewer steps and is easier to investigate; the second increases **opportunities to reuse the Docker build cache and registry layers** when application code changes more often than dependencies. The better choice is not automatically "more layers means faster": you must weigh JAR size, change rate, CI caching, image version volume, operational needs, and tooling constraints.

After this lesson, you will be able to:

- Explain why a whole JAR usually creates **one layer holding the entire application**, whereas extraction creates **multiple image layers grouped by data stability**.
- Distinguish `BOOT-INF/layers.idx`, directories extracted by Spring Boot, and actual **Docker/OCI layers**.
- Write **two complete Dockerfiles** that run **the exact same executable JAR** and select the build mode from the CLI.
- Use Spring Boot **3.3 `-Djarmode=tools`** with `list-layers` and `extract --layers`; understand how it differs from `layertools` in older guides.
- Configure Gradle `bootJar` or Maven `repackage` to produce the right archive; verify the launcher, tools dependency, and input file.
- Conduct an experiment editing a Controller, comparing Docker `CACHED` output and HTTP responses without claiming cache hits before reading logs.
- Recognize constraints around startup, image size, reproducibility, security, non-root users, base images, and CI runners.
- Make an evidence-based decision and verify the actual artifact used.

**Consistent baseline:** Spring Boot **3.3.5**, Java **17**, Spring MVC, compatible Gradle Wrapper or Maven Wrapper, and Docker supporting multi-stage builds. These versions illustrate a consistent API set and **are not a recommendation of the latest release**. Spring Boot 3.3 includes `spring-boot-jarmode-tools`; on Spring Boot 2.x/early 3.x, syntax and layout may differ. Prioritize your project's version-specific documentation.

## 2. First Model: Running the Whole Executable JAR

Spring Boot Gradle `bootJar` or Maven `spring-boot:repackage` produces a JAR runnable via `java -jar`. Its typical structure is:

~~~text
app.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...     (Spring Boot launcher)
└── BOOT-INF/
    ├── classes/                           (application classes/resources)
    │   └── com/example/dockerchoice/...
    ├── lib/                               (runtime dependency JARs)
    │   ├── spring-boot-*.jar
    │   ├── spring-webmvc-*.jar
    │   └── ...
    ├── layers.idx                         (when layering is enabled)
    └── classpath.idx                      (if present)
~~~

At startup, the JVM reads `Main-Class` from the manifest. In a Spring Boot 3.3 executable JAR, `Main-Class` is typically `org.springframework.boot.loader.launch.JarLauncher`, while `Start-Class` points to your application class. The launcher configures the classpath to load nested libraries inside `BOOT-INF/lib`.

A **simple Dockerfile** only needs a base JRE image, one `COPY`, and `ENTRYPOINT`:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

This snippet **only illustrates the principle**; if `app.jar` is not in the build context, `COPY` fails. The hands-on section in Section 7 provides a complete version using `ARG JAR_FILE` to copy directly from Maven/Gradle output.

**Advantages of running the whole JAR:**

- Minimal configuration, easy for newcomers and small projects to understand.
- Needs only the executable JAR, a compatible JRE, and that file in the Docker build context; **no tools extraction needed**.
- Easy to test the exact same artifact locally or in a container via `java -jar app.jar`.
- Independent of `extract --layers` folder structures and custom layer names.
- Fits well when build/push/pull speed is not a bottleneck or the organization already has a simple image-building flow.

**Limitation to measure in practice:** changing one tiny Java class alters the **bytes of the entire `app.jar` file**. If the Dockerfile copies the entire JAR into one image layer, that layer loses cache and must be stored/transferred as a single blob. Docker does not automatically "look inside" `BOOT-INF/lib` to recognize unchanged libraries.

Still, do not conclude every whole-JAR build is slow: Docker still caches the **base image** and steps before `COPY`; if the application JAR is unchanged, `COPY` can be completely reused. Effectiveness also depends on the image registry and CI builder cache.

## 3. Second Model: Extracting a Layered Archive Before Packaging the Image

The Spring Boot plugin can include `BOOT-INF/layers.idx` describing how archive entries map to groups with different change frequencies. Defaults in Spring Boot 3.3 typically include:

| Spring Boot Layer | Contents | Relative Change Frequency |
| --- | --- | --- |
| `dependencies` | External libraries without `SNAPSHOT` in their version, e.g., runtime starters/libraries | Rarely changes when BOM and dependency versions are stable |
| `spring-boot-loader` | Spring Boot launcher classes under `org/springframework/boot/loader` | Rarely changes unless the Boot version changes |
| `snapshot-dependencies` | Snapshot libraries from the dependency graph | Can change often even if the version string stays the same |
| `application` | Application classes/resources and local project/module dependencies | Changes on almost every code edit |

The default order is designed to **place least-frequently changing content first and most-frequently changing content last**.

When running:

~~~bash
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

Spring Boot 3.3 creates an extracted layout, typically with directories:

~~~text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
    └── application.jar                  (thin JAR referencing extracted libraries)
~~~

This is a **simplified diagram**; additional subdirectories can exist deeper inside the groups. `application.jar` inside the `application` folder **is not the original fat JAR**. It is an artifact generated by Spring Boot tools for running the extracted layout, referencing the split libraries in their proper locations.

The container image can use `COPY --from=extractor` instructions to stack the four groups into `WORKDIR /application`:

~~~text
OCI base JRE image
  + dependencies/             (copied first)
  + spring-boot-loader/
  + snapshot-dependencies/
  + application/              (copied last)
  -> java -jar application.jar
~~~

**Key point:** `layers.idx` is **metadata**, not Docker layers. Only when an image build tool extracts and runs separate `COPY` instructions per group do independent Docker/OCI layers have a chance to be reused.

### 3.1. Extracted Folders Differ from the Original Layout

Do not assume `extract --layers` merely unzips `BOOT-INF` as-is and requires you to assemble a manual classpath like:

~~~text
java -cp "BOOT-INF/classes:BOOT-INF/lib/*" ...
~~~

That is not how **Spring Boot 3.3 tools mode** runs by default. Per Boot 3.3 docs, the extracted layout includes `application.jar` and libraries arranged to run via:

~~~bash
java -jar application.jar
~~~

from the extracted directory where the layers are merged. Under Spring Boot 2.x and `layertools`, examples may invoke `JarLauncher` directly; **do not copy old-style entrypoints onto modern tools extraction** without verifying.

### 3.2. Not Every JAR Supports Tools Mode

All of the following must hold:

1. It is a **Spring Boot executable archive**, not a `-plain.jar` or library JAR.
2. Layering is enabled and the archive contains `BOOT-INF/layers.idx`.
3. `spring-boot-jarmode-tools` was actually included by the plugin; `includeTools` was not disabled.
4. The archive **is not a fully executable JAR with a prepended launch script**, because tools mode does not support that format.
5. The Java runtime in the extractor stage is a high enough version to execute the artifact.

If a condition is missing, fix it **in the build tool/source configuration**, rather than manually inserting a hand-written `layers.idx` into the archive after the build.

## 4. Quick Comparison Before Deciding

| Criterion | Whole JAR | Extracted Layers |
| --- | --- | --- |
| Dockerfile | One `COPY` for JAR, fewer steps | Multi-stage extract then multiple `COPY` instructions |
| Readability/Operations | Very simple | Must understand tools mode, extracted layout, and layer names |
| App data in image | Entire JAR in one image layer | Dependencies/loader/application in separate layers |
| When only a Controller changes | Whole-JAR `COPY` usually misses cache | Dependency/loader `COPY` steps can often be reused |
| Registry upload/pull across versions | May re-upload/download large JAR blob | Can share older dependency blobs |
| Cold/empty cache case | Less work during image build | Incurs extraction and multiple `COPY` steps |
| Java entrypoint | `java -jar application.jar` on fat JAR | `java -jar application.jar` on **extractor-generated JAR**, after merging layers |
| Needs `layers.idx`/tools | No | Yes when using `jarmode=tools` |
| Startup benefit | Depends on app and JVM | Extracted layout can reduce nested-JAR overhead and is CDS-friendly; no fixed speedup promised |
| Image size | Depends on base JRE + JAR + other files | Usually does not reduce total dependencies; metadata/layers may add slightly |
| CI/caching | Less sensitive to cache setup | Gains increase when BuildKit cache or registry layer reuse persists |
| Debuggability | Easy to inspect single artifact | Must verify both extraction and runtime layout |
| Use when | POCs, small projects, infrequent releases, simple workflows | Frequent releases, large fat JARs, high registry/pull costs, many apps sharing dependencies |

**Preliminary decision rule:** If you have no measured Docker build or registry/pull bottleneck, running the whole JAR is a sensible starting point. When repeated transfer costs are significant and dependencies are stable, layer extraction is a grounded optimization. Yet both approaches require the exact same testing, image scanning, runtime pinning, and secrets management.

## 5. Creating a Spring Boot Java 17 Project for Both Approaches

We use the exact same source code and Gradle build output, then run **two Dockerfiles** to eliminate application-logic differences.

~~~text
docker-choice-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
├── Dockerfile.jar
├── Dockerfile.layers
├── .dockerignore
└── src/
    ├── main/java/com/example/dockerchoice/
    │   ├── DockerChoiceApplication.java
    │   └── VersionController.java
    └── test/java/com/example/dockerchoice/
        └── VersionControllerTest.java
~~~

**Note:** This assumes the Gradle Wrapper was genuinely created/committed with Gradle tooling; a bare `gradlew` script without `gradle/wrapper` will not run. If the project uses Maven, see Section 12; **there is no need to maintain both Maven and Gradle build files** in a real repository.

### 5.1. `settings.gradle`

~~~groovy
rootProject.name = 'docker-choice-demo'
~~~

### 5.2. `build.gradle` — Complete Groovy DSL

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.dockerchoice.DockerChoiceApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'app.jar'
    layered {
        enabled = true
    }
    includeTools = true
}
~~~

**Why these settings?**

- `spring-boot-starter-web` provides Spring MVC and the Tomcat runtime matching the chosen Spring Boot version.
- `java.toolchain` compiles with Java 17; Docker images also run JRE 17.
- `testImplementation` is used only for testing and does not put JUnit onto the runtime classpath of a normal executable JAR.
- `useJUnitPlatform()` tells Gradle Test to run JUnit Jupiter.
- `bootJar.archiveFileName = 'app.jar'` gives a **stable** output name: `build/libs/app.jar`, preventing the Dockerfile from accidentally picking `-plain.jar` or a SNAPSHOT-versioned name.
- `layered.enabled=true` instructs the plugin to generate `BOOT-INF/layers.idx`; Spring Boot 3.3 enables layering by default, though this lesson declares it explicitly for clarity.
- `includeTools=true` ensures `jarmode=tools` is present; this is also the default in Spring Boot 3.3 when layering is enabled.
- `springBoot.mainClass` fixes the entry point, avoiding ambiguity if more `main` classes are added later.

If a real project already uses `settings.gradle` to manage repositories with `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, omit the project-level `repositories { mavenCentral() }` block and use approved repositories. Do not change repository policies just to build a Docker image.

### 5.3. `DockerChoiceApplication.java`

Path `src/main/java/com/example/dockerchoice/DockerChoiceApplication.java`:

~~~java
package com.example.dockerchoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DockerChoiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(DockerChoiceApplication.class, args);
    }
}
~~~

This class is a valid application main class with Java 17 and Spring Boot Starter Web; it builds and runs via the Wrapper. Do not run it standalone with `javac` without Spring Boot dependencies on the classpath.

### 5.4. `VersionController.java`

Path `src/main/java/com/example/dockerchoice/VersionController.java`:

~~~java
package com.example.dockerchoice;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {
    @GetMapping("/version")
    public String version() {
        return "image-v1";
    }
}
~~~

Once the app starts and an HTTP request to `GET /version` succeeds, the **exact response body** from this code is:

~~~text
image-v1
~~~

Do not assert exact Spring Boot startup log lines, since timestamps, ports, PIDs, and log formatting vary by environment.

### 5.5. `VersionControllerTest.java`

Path `src/test/java/com/example/dockerchoice/VersionControllerTest.java`:

~~~java
package com.example.dockerchoice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(VersionController.class)
class VersionControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void versionReturnsV1() throws Exception {
        mvc.perform(get("/version"))
                .andExpect(status().isOk())
                .andExpect(content().string("image-v1"));
    }
}
~~~

`@WebMvcTest` tests MVC mapping quickly without needing Docker. It **does not prove the container image runs**; you must add a container smoke test. When changing the Controller to `image-v2` in the cache experiment, update the assertion as well so tests do not fail unnecessarily.

## 6. Building the Right Executable JAR Before Writing the Dockerfile

### Linux/macOS

~~~bash
./gradlew --version
./gradlew clean test bootJar
jar tf build/libs/app.jar | grep '^BOOT-INF/'
java -jar build/libs/app.jar
~~~

### Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
jar tf .\build\libs\app.jar | Select-String '^BOOT-INF/'
java -jar .\build\libs\app.jar
~~~

From a second terminal, call:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Expected response body:

~~~text
image-v1
~~~

`bootJar` creates `build/libs/app.jar` per configuration. `jar tf` verifies `BOOT-INF/classes`/`BOOT-INF/lib` and `BOOT-INF/layers.idx`. If the JAR fails to run directly on the host, **do not jump to blaming the Dockerfile**; fix the underlying build/runtime issue first.

After testing with `java -jar`, stop the process before running Docker on host port 8080, otherwise port mapping will conflict.

**Build source first, Docker image second** is the architecture of this lesson. Neither Dockerfile runs Gradle/Maven compilation itself; they only package the tested artifact. That is an advantage for CI: the exact same artifact bytes feed into both Dockerfile strategies.

## 7. Option A — `Dockerfile.jar`: Running the Whole JAR

Create **`Dockerfile.jar`** at the project root:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

ARG JAR_FILE=build/libs/app.jar
COPY $JAR_FILE application.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

**This is a complete Dockerfile for the Gradle-built example.** Explanation:

1. `FROM eclipse-temurin:17-jre`: uses JRE 17 compatible with bytecode/source; the image is an example and should be pinned by digest/organization policy for releases.
2. `WORKDIR /app`: sets the runtime working directory.
3. `ARG JAR_FILE=build/libs/app.jar`: path **relative to the Docker build context** of the built artifact. It is not a path inside the image.
4. `COPY $JAR_FILE application.jar`: copies **the whole executable JAR** into `/app/application.jar`. Do not use `COPY build/libs/*.jar`, which could accidentally pick up `-plain.jar`.
5. `USER 10001:10001`: runs as a numeric non-root user. Since the demo app only reads the JAR and listens on port 8080, root is unnecessary, provided the base image allows reading the file and using an appropriate temp directory.
6. `EXPOSE 8080`: documents the container port; **does not publish the port** to the host.
7. Exec JSON-form `ENTRYPOINT`: Java is the main process with no shell wrapper, enabling cleaner signal handling. Process exit codes are directly observable by Docker/Kubernetes.

**Do not write secrets into the Dockerfile**; database names, passwords, and API tokens are supplied at runtime via environment/secret managers. Do not use `RUN echo "$PASSWORD" > ...` because the data remains in image layers.

### Build Image A

~~~bash
docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar .
docker run --rm -p 8080:8080 docker-choice:jar
~~~

Open another terminal:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Output:

~~~text
image-v1
~~~

The trailing dot in `docker build` means the **build context is the project root**. If the Dockerfile lives elsewhere yet the build context lacks `build/libs/app.jar`, `COPY` will not find the artifact. Do not "fix" this by copying the entire repository and personal files into the image.

### Benefits and Limits of A

**Appropriate** for many simple microservices where image build/pull is fast, dependency JARs are modest, releases are infrequent, or teams prioritize low maintenance burden. This is not a "wrong" solution; it can be the best choice by total cost.

**Limitation** is that Docker does not know the JAR internally splits into `BOOT-INF/lib` and `BOOT-INF/classes`. Editing a Controller changes `app.jar`; `COPY` sees a different input and likely creates a new blob containing all libraries as well. The base JRE image can still be reused.

## 8. Enabling and Verifying the Layered Archive Before Using Dockerfile B

### 8.1. Index File Inside the Boot JAR

Linux/macOS:

~~~bash
jar tf build/libs/app.jar | grep '^BOOT-INF/layers.idx$'
jar tf build/libs/app.jar | grep 'spring-boot-jarmode-tools'
~~~

PowerShell:

~~~powershell
jar tf .\build\libs\app.jar | Select-String '^BOOT-INF/layers.idx$'
jar tf .\build\libs\app.jar | Select-String 'spring-boot-jarmode-tools'
~~~

`BOOT-INF/layers.idx` is the file-group map; `spring-boot-jarmode-tools` provides the tools mode. These two components **serve different roles**. If either is missing, check plugin version, `bootJar` task, `layered.enabled`, `includeTools`, and the actual artifact rather than creating fake directories.

### 8.2. Listing Layers

~~~bash
java -Djarmode=tools -jar build/libs/app.jar list-layers
~~~

In PowerShell:

~~~powershell
java -Djarmode=tools -jar .\build\libs\app.jar list-layers
~~~

With default layering, the names you normally see are:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

If the project uses custom layer DSL/XML, names and order can differ. A layer may contain no JARs, e.g., if no SNAPSHOTs are used. **The layer list is not a list of Docker image layers.**

### 8.3. Extracting and Inspecting Manually

Linux/macOS:

~~~bash
mkdir -p build/inspect-layers
java -Djarmode=tools -jar build/libs/app.jar \
    extract --layers --destination build/inspect-layers
find build/inspect-layers -maxdepth 2 -type d
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\build\inspect-layers | Out-Null
java -Djarmode=tools -jar .\build\libs\app.jar extract --layers --destination .\build\inspect-layers
Get-ChildItem .\build\inspect-layers\
~~~

The extraction command uses **Spring Boot 3.3 `tools` mode**, not the legacy `layertools`. Directories are created per layer. When re-running extraction, use a **fresh/clean destination directory** so leftover files from earlier runs do not mix in.

**Host extraction is not required to use Dockerfile B**; this is just an inspection check. Dockerfile B extracts inside a dedicated builder stage from the **same artifact** copied into the build context.

## 9. Option B — `Dockerfile.layers`: Extracting Layers in a Multi-Stage Build

Create **`Dockerfile.layers`** at the project root:

~~~dockerfile
# Stage 1: copy executable JAR into a Java environment and extract
FROM eclipse-temurin:17-jre AS extractor

WORKDIR /workspace

ARG JAR_FILE=build/libs/app.jar
COPY $JAR_FILE application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

# Stage 2: runtime without carrying the fat JAR from extractor
FROM eclipse-temurin:17-jre

WORKDIR /application

COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/application/application.jar"]
~~~

**This is a complete multi-stage Dockerfile** matching the official Spring Boot 3.3 layout. Breakdown:

1. **Extractor stage** uses a JRE to invoke `-Djarmode=tools`. It does not run an HTTP server and needs no Java source code, Maven, or Gradle in the image.
2. `COPY $JAR_FILE application.jar` copies the built and tested source fat JAR, just like Option A, but only into an **intermediate stage**.
3. `extract --layers --destination extracted` splits the archive into file groups; Spring Boot tools build a runtime layout alongside the extracted application JAR.
4. **Runtime stage** starts a fresh image from the JRE base. It **does not** inherit the extractor stage's filesystem and **does not** copy the source fat JAR.
5. `COPY dependencies` comes first so release libraries that rarely change sit in early image layers.
6. `COPY spring-boot-loader` comes next, isolating the Boot launcher.
7. `COPY snapshot-dependencies` follows because SNAPSHOT libraries fluctuate more than release dependencies.
8. `COPY application` goes last because application classes/resources change most often.
9. `ENTRYPOINT ["java","-jar","/application/application.jar"]` starts the **extracted layout's thin JAR** at runtime, with libraries merged from the four groups.
10. `USER 10001:10001` runs the process without root privileges, just like Option A; directories holding the JAR/libs must be readable by this UID.

**Do not replace ENTRYPOINT with `java -jar /workspace/application.jar`:** the source fat JAR only exists in the **extractor stage** and is never copied to the runtime stage. The runtime `application.jar` is generated by Spring Boot tools from the extracted application layer.

### 9.1. Build Image B

~~~bash
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers .
docker run --rm -p 8080:8080 docker-choice:layers
~~~

Open another terminal:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Result:

~~~text
image-v1
~~~

**You must stop container A or use a different host port** before running B. You can run:

~~~bash
docker run --rm -p 8081:8080 docker-choice:layers
~~~

and then query `http://localhost:8081/version`. The application port inside the container stays 8080; `-p 8081:8080` only changes the host port.

### 9.2. How to Read the Docker Build Cache

BuildKit logs every instruction; steps may print `CACHED` when inputs and the cache store qualify. With B, dependencies/loader often reuse cache when only the Controller changes, though **this is not guaranteed**: if CI uses a fresh builder, clears cache, or the base image changes, the build may execute every step.

Additionally, when the fat JAR changes, `COPY` and `RUN` in the **extractor stage** usually re-run. That **does not negate the benefit** of separate `COPY` instructions in the runtime stage: as long as stable extracted directories keep identical bytes/metadata and the builder detects it, those runtime/registry layers can still be reused.

### 9.3. Benefits and Trade-Offs of B

**Benefits** include finer cache granularity, better reuse of dependency blobs, potential registry bandwidth savings for frequently updated microservices, and an extracted layout friendly to JVM optimizations like CDS under supported conditions.

**Costs** include an extraction stage, a longer Dockerfile, coupling to `jarmode tools` and layer layouts, and extra steps to debug, test, and keep aligned when framework/plugin versions change. Extraction does not guarantee a smaller image; all libraries still reside inside the image for the app to run.

## 10. Docker Cache Rule: `COPY` Order Truly Matters

Docker/BuildKit evaluates an instruction and its inputs when deciding whether to reuse a cached result. Once an instruction misses cache, downstream steps depending on the altered state generally must re-run. Therefore, never place application code ahead of dependencies.

**Correct ordering for B:**

~~~dockerfile
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./
~~~

**Suboptimal ordering for illustration:**

~~~dockerfile
COPY --from=extractor /workspace/extracted/application/ ./
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
~~~

In the second order, **application** comes first. Whenever the application changes, subsequent `COPY` steps can invalidate along the dependency chain even though dependency bytes are unchanged. Do not shuffle layer order arbitrarily just because the command still runs.

### 10.1. Spring Boot Layers and OCI Layers Do Not Match 1:1

The four Spring Boot layers are logical groups. An OCI image can contain multiple base image layers, metadata/history, and layers beyond the four `COPY` commands. Builder optimizations, empty-layer elision, and compression can make the actual layer count differ from the logical group count.

Thus, never verify success merely by saying "`docker history` must have exactly four rows." Instead, inspect the separated Dockerfile `COPY` instructions, cache logs, runtime responses, and, if needed, image layer digests.

### 10.2. Do Not Confuse with the Gradle Build Cache

`./gradlew bootJar FROM-CACHE`, `:compileJava UP-TO-DATE`, and Docker `CACHED` are three separate mechanisms:

- **Gradle UP-TO-DATE:** task outputs in the workspace have not changed.
- **Gradle FROM-CACHE:** task outputs were fetched from the Gradle Build Cache.
- **Docker CACHED:** the Dockerfile instruction result was already in the Docker build cache.
- **OCI registry layer reuse:** the registry/client can skip uploading/pulling a blob that already exists.

A JAR restored from cache by Gradle can still miss Docker `COPY` cache if its contents or metadata differ from what was previously copied. Conversely, Docker can reuse dependency image layers even though `bootJar` just ran fresh. Collect **logs at the right layer** when evaluating optimizations.

## 11. A/B Practice: Edit One Controller to Compare Both Dockerfiles

This experiment is designed so **only application classes change** while the dependency graph stays constant. Cache results must be genuinely observed; do not invent seconds or assume `CACHED` unconditionally.

### 11.1. Baseline v1

1. Keep the Controller returning `"image-v1"` and the test expecting `image-v1`.
2. Run `./gradlew clean test bootJar` or `.\gradlew.bat clean test bootJar`.
3. Build both images:

~~~bash
docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar-v1 .
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers-v1 .
~~~

4. Run each image and call `GET /version`, verifying body `image-v1`.
5. Save Docker build logs, JAR name, base image digest, and cache store details.

If you want to verify caching on a **no-change build**, re-run the exact same `docker build` commands with the same tags/context. Many steps may print `CACHED` in both approaches because no input changed; that does not test source-change optimization.

### 11.2. Edit Code, Keep Dependencies

In `VersionController.java`, replace:

~~~java
return "image-v1";
~~~

with:

~~~java
return "image-v2";
~~~

In `VersionControllerTest.java`, replace the expectation:

~~~java
.andExpect(content().string("image-v1"));
~~~

with:

~~~java
.andExpect(content().string("image-v2"));
~~~

Then:

~~~bash
./gradlew clean test bootJar

docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar-v2 .
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers-v2 .
~~~

Test the new image, picking an unused host port:

~~~bash
docker run --rm -p 8081:8080 docker-choice:layers-v2
~~~

Another terminal:

~~~bash
curl -fsS http://localhost:8081/version
~~~

The response body must be:

~~~text
image-v2
~~~

Test `docker-choice:jar-v2` the same way (stop the prior container or use another host port). **If either image still returns `image-v1`, that is a build/artifact/caching/path bug or a leftover container**, never declare the optimization successful.

### 11.3. Expected Behavior When Caching Actually Works

| Part | Dockerfile.jar | Dockerfile.layers |
| --- | --- | --- |
| JRE base image | Reused if base digest unchanged | Reused if base digest unchanged |
| `COPY` executable JAR | Evaluates new JAR file, usually creates new layer | Extractor `COPY` and `RUN extract` usually re-run |
| Runtime dependencies files | Bundled in whole-JAR layer | Opportunity to reuse `dependencies` layer |
| Spring Boot loader files | Bundled in whole-JAR layer | Opportunity to reuse loader layer |
| Snapshot dependencies | Bundled in whole-JAR layer | Opportunity to reuse if snapshot bytes unchanged |
| Application classes | Changes inside whole JAR | Changes in final `application` layer |
| HTTP response | `image-v2` | `image-v2` |
| Time/pull bytes | Must be measured, not assumed | Can improve over repeated releases |

**Reading Docker build logs:** with BuildKit, reused steps may show `CACHED`. If the builder has no cache or you passed `--no-cache`, you cannot use the absence of `CACHED` to conclude Spring Boot layers are broken. To measure registry layer reuse, compare image layer digests and uploaded/pulled byte counts recorded by the registry/build tool.

### 11.4. Trying Adding a Dependency

When adding or upgrading a runtime library in Gradle/Maven, the `dependencies` group usually changes. `Dockerfile.layers` may miss cache earlier and downstream steps can also be affected. This is **correct invalidation** because the image has a new dependency graph, not an optimization bug.

Restore dependencies, the controller, and tests back to baseline after the experiment if working in a real project.

## 12. Maven Alternative: Still Works with Both Dockerfiles

If your project uses Maven, the Spring Boot Maven Plugin `repackage` supports layered executable JARs equivalent to `bootJar`. Below is a **standalone** POM replacing `build.gradle`, reusing the exact same three Java/test files from Section 5.

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>docker-choice-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

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

**Meaning:** Starter Parent manages plugin/dependency versions and `repackage` config; `<finalName>app</finalName>` makes Maven produce the executable JAR `target/app.jar`. The Maven Boot plugin creates `BOOT-INF/layers.idx` by default with layering enabled; `includeTools` provides Spring Boot 3.3 tools mode. If the project imports only the BOM without inheriting Parent, explicitly configure the plugin version and `repackage` execution.

Build and inspect:

~~~bash
./mvnw --version
./mvnw clean verify
jar tf target/app.jar | grep '^BOOT-INF/layers.idx$'
java -Djarmode=tools -jar target/app.jar list-layers
~~~

In Windows PowerShell, use `.\mvnw.cmd` and `Select-String` accordingly. Java sources stay unchanged because both Maven and Gradle use the `src/main/java`, `src/test/java` layout.

**Build Docker from the Maven artifact:** keep `Dockerfile.jar` and `Dockerfile.layers` unchanged, simply pass the path via `ARG JAR_FILE`:

~~~bash
docker build --progress=plain \
    --build-arg JAR_FILE=target/app.jar \
    -f Dockerfile.jar -t docker-choice:maven-jar .

docker build --progress=plain \
    --build-arg JAR_FILE=target/app.jar \
    -f Dockerfile.layers -t docker-choice:maven-layers .
~~~

Do not set `ARG JAR_FILE` to an arbitrary path outside the Docker build context, because `COPY` cannot read files outside the context. If CI puts the artifact in another folder, choose a valid context and path or copy the verified artifact into a staging context.

**Note:** The whole-JAR Dockerfile **does not require a Maven layer index**. You can pass the same Maven executable JAR containing `layers.idx`, and `Dockerfile.jar` will simply ignore it. That provides an even fairer comparison between the two Dockerfile strategies.

## 13. Kotlin DSL Instead of Groovy DSL

If the project uses `build.gradle.kts`, the equivalent Gradle configuration for `app.jar` is:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

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

tasks.test {
    useJUnitPlatform()
}

springBoot {
    mainClass.set("com.example.dockerchoice.DockerChoiceApplication")
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app.jar")
    layered {
        enabled.set(true)
    }
    includeTools.set(true)
}
~~~

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "docker-choice-demo"
~~~

This is an **alternative** to Groovy DSL; do not include both DSLs simultaneously. Dockerfiles and Java sources remain unchanged. If your project already has custom repository rules or Java plugin settings, merge only the needed configuration rather than overwriting the existing build configuration.

## 14. `.dockerignore` and Artifact Paths: Small Mistakes, Very Common Failures

Because both Dockerfiles copy **a prebuilt artifact**, the Docker build context must contain `build/libs/app.jar` (Gradle) or `target/app.jar` (Maven).

A safe, easy-to-read `.dockerignore` for the example:

~~~dockerignore
.git
.gradle
.idea
.vscode
src
.repro-check
**/*.log
build/classes
build/generated
build/reports
build/test-results
build/tmp
~~~

This file **deliberately does not exclude the whole `build` or `target` directory**, because the Dockerfile needs to read the built JAR. If an organization wants to send only the single JAR as build context, create a **dedicated staging directory** holding the artifact and Dockerfiles and run `docker build` from that directory; adjust `ARG JAR_FILE` and paths accordingly.

**Typical failures:**

- `COPY failed: file not found`: not built yet, path/filename differs, missing from context, or excluded by `.dockerignore`.
- `COPY build/libs/*.jar`: can accidentally match `-plain.jar` or multiple artifacts; avoid wildcards when targeting one JAR.
- Running `docker build` from a subdirectory: the trailing `.` is no longer the project root, so `COPY` looks in the wrong place.
- Changing `archiveFileName` in Gradle or `finalName` in Maven while leaving the old path in the Dockerfile.
- Maven `target/app.jar.original`: not the final executable JAR; do not copy it by mistake.
- Gradle `bootJar` disabled and only `jar` ran: produces a plain JAR missing the Spring Boot launcher/nested libraries.
- A CI command runs `docker build` **before** `gradlew bootJar`: Docker picks up a stale JAR from a previous build.

### Using Docker `ARG` Properly

`ARG JAR_FILE` in both Dockerfiles is only a **build-time path selector**. It does not change the Java main class, Spring runtime profile, or dependencies inside the JAR. Changing `--build-arg JAR_FILE=...` can alter Docker cache behavior because the `COPY` input changes, but it does not compile the Java project for you.

Never place secrets in `ARG` or a hardcoded `ENV` just to pass passwords: they can show up in image history, metadata, or logs. Use a secret manager or a Docker BuildKit secret mount in the build stage if private resource access is truly needed.

## 15. Runtime Image: JRE, Non-Root, and ENTRYPOINT

A good Spring Boot image needs the right **Java runtime**, the right **entrypoint**, proper signal handling, and appropriate file permissions.

### 15.1. Choosing the Java Base Image

- The examples use `eclipse-temurin:17-jre`, matching Java 17 compilation in Spring Boot 3.3.
- Production should pin a **digest** (and platform if needed) per policy so tags do not silently drift, alongside a schedule to update images for security patches.
- Do not blindly pick the smallest JRE: the app may need fonts, locales, TLS certificates, timezone data, or native libraries.
- Do not assume a JRE image has `sh`, `bash`, `curl`, or a package manager; the example Dockerfiles **do not need** those tools at runtime.

### 15.2. Running as a Non-Root User

Both Dockerfiles include:

~~~dockerfile
USER 10001:10001
~~~

This is a non-root numeric UID/GID. For a demo that only reads the JAR and listens on port 8080, it is usually sufficient. If the app must write logs, files, or uploads, provision mounts/paths **with proper write permissions** instead of switching to root as a quick fix. The JVM may need a temp directory like `/tmp`; verify against your chosen base image.

### 15.3. Right ENTRYPOINT for Each Layout

| Artifact/Runtime | Right ENTRYPOINT for Example |
| --- | --- |
| Whole `/app/application.jar` | `["java","-jar","/app/application.jar"]` |
| Extracted layout under `/application` | `["java","-jar","/application/application.jar"]` |
| JAR tools mode in extractor stage | `java -Djarmode=tools -jar application.jar extract --layers --destination extracted` |

Tools mode is a **build-time command**, not a container runtime entrypoint. With the extracted layout, do not forget to copy `dependencies`/loader and then run the fat-JAR entrypoint as if the thin JAR contained all libraries.

### 15.4. Environment Variables and Spring Configuration

Runtime values like `SPRING_PROFILES_ACTIVE`, database URLs, credentials, and tracing configuration should be injected by the deployment environment, not hardcoded in the Dockerfile. `SPRING_PROFILES_ACTIVE=prod` is a **Spring runtime profile**; **it does not alter how the Dockerfile copies the JAR or layer order**.

**`EXPOSE 8080`** merely documents the port, while `docker run -p 8080:8080` publishes the port to the host. In Kubernetes, objects like Service/Ingress manage networking; do not infer from `EXPOSE` that the app is exposed to the internet.

## 16. Practical Impact: Startup, Size, Transfer, and Cache

There are four distinct metrics that should not be collapsed into a vague "more optimized image":

1. **Docker build time:** multi-stage extraction adds overhead, though reusing image layers can make subsequent builds faster. Results depend on the cache backend.
2. **Registry push/pull bytes:** layered copies can reuse dependency blobs when application code changes; a whole JAR may require transferring one large application blob. Registries use content-addressable storage, so inspect actual digests and bytes.
3. **Final image size:** splitting layers **does not delete libraries**; both approaches contain the dependencies and JRE. Never promise a layered image is always smaller. It may shrink or grow slightly depending on compression and layout.
4. **Startup time:** Spring Boot's extracted layout can reduce nested-JAR access overhead and facilitate Class Data Sharing (CDS) in certain workflows, yet it does not guarantee every app starts faster.

### 16.1. Measuring Under Equal Conditions

For a fair comparison:

- Same commit, JDK, Boot, and Gradle versions, and dependency graph.
- Same JRE base image family/digest for both Dockerfiles.
- Same CPU/memory limits when running containers.
- Same warm/cold cache policy; explicitly record whether Docker BuildKit cache reuse occurred.
- Same smoke endpoint, profile, environment, and external data.
- Never compare an image push over network A against an image pull over network B and attribute the difference to layering.
- Measure across multiple runs under equal conditions rather than drawing conclusions from one lucky run.

### 16.2. Do Not Confuse Total Image Size with Bytes Transferred per Release

A layered image may **not be smaller** than a fat-JAR image in total logical size, yet when deploying a new version with unchanged dependency layers, the registry or Kubernetes node may only pull the missing blobs. This is often a more meaningful real-world benefit than "how many MB does `docker image ls` display?"

### 16.3. Do Not Use Cache to Mask Lack of Reproducibility

If `BOOT-INF/lib` contains SNAPSHOT/changing dependencies, or generated resources embed the current timestamp, Docker can miss cache even when business code has not changed. Control dependency versions, resource generation, and Gradle/Maven toolchains to avoid unintended variance.

## 17. CI Pipeline: Build One Artifact, Test, Then Package Two Images

A practical pipeline should split into three stages:

~~~text
SOURCE / COMMIT
      |
      v
Build + unit/integration tests
      |
      v
One executable app.jar (immutable Dockerfile input)
      |
      +---- Dockerfile.jar ----> image A
      |
      +---- Dockerfile.layers -> image B
      |
      v
Smoke test each image
      |
      v
Select approved approach + scan/sign/push/deploy
~~~

**Why does "build one JAR" matter?** If A builds from commit X and B builds from commit Y, any cache/size/startup comparison gets polluted by application differences. Build the artifact once, record its checksum, and feed that exact file into both Dockerfiles. CI might build both only during evaluation; production normally standardizes on **one** workflow.

### 17.1. Core Commands for Linux CI

~~~bash
set -eu

./gradlew --no-daemon clean test bootJar
test -f build/libs/app.jar
jar tf build/libs/app.jar | grep -q '^BOOT-INF/layers.idx$'

docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar-ci .
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers-ci .
~~~

This is a **pipeline snippet**, not a complete workflow YAML. In a shell with `set -o pipefail`, `jar tf | grep -q` can occasionally trigger a broken pipe if the reader exits early; to be strict, write `jar tf ... > jar-entries.txt` and then `grep -q ... jar-entries.txt`.

### 17.2. Smoke Testing Without Hardcoded Sleep

Manual approach:

~~~bash
docker run --rm -p 8080:8080 docker-choice:jar-ci
~~~

Other terminal:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Do the same for `docker-choice:layers-ci` after stopping the first container. In CI automation, run the container detached and **poll the endpoint with a bounded timeout**, saving logs and stopping/removing the container in cleanup even on failure; never run a single fixed `sleep` and assume the server is ready.

### 17.3. Audit Trail

- Commit SHA and dependency/BOM sources.
- JDK, Spring Boot plugin, and Maven/Gradle Wrapper versions.
- SHA-256 of the tested `app.jar`.
- Dockerfile path and `JAR_FILE` build-arg.
- Base image digest, target platform, and builder/cache backend.
- BuildKit logs for `COPY` instructions.
- HTTP smoke results, test reports, image tag/digest, and scan status.
- Deployment reference using an immutable image digest rather than only a mutable tag name.

**Do not merely check `docker build` exit 0** and call the image "verified." The archive may copy syntactically fine while Spring config is broken or listening on a different port, which only shows up when running the container.

## 18. Common Errors and How to Isolate Them

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| Docker `COPY` says source not found | JAR not built, wrong build context, `.dockerignore` excludes JAR | Check `build/libs/app.jar` or `target/app.jar` and the `.` of `docker build` |
| Image A reports `no main manifest attribute` | Copied plain JAR instead of Boot executable JAR | Use Gradle `bootJar`/Maven `repackage`, inspect manifest |
| Image B reports `Unsupported jarmode 'tools'` | Different Spring Boot/plugin version, missing tools JAR, or `includeTools=false` | Check Boot 3.3 tools mode, `BOOT-INF/layers.idx`, and `spring-boot-jarmode-tools` |
| Tools extract fails on fully executable JAR | Archive has prepended launch script | Disable `launchScript()`/fully-executable option for artifacts to extract |
| Image B `COPY --from` says directory missing | Extract lacked `--layers`, wrong path, custom layer names | Run `list-layers`, inspect extractor output and `COPY` paths |
| Image B cannot find `application.jar` at runtime | Missing `application/` copy or wrong layout | Check Spring Boot 3.3 extracted layout and `ENTRYPOINT` |
| Image B hits `ClassNotFoundException` | One of the dependencies/loader groups not copied or overwritten wrongly | Check all four `COPY` steps in order, compare `java -jar` with source fat JAR |
| Running B errors on `JarLauncher` | Used legacy `layertools` entrypoint with new tools extraction | Per Boot 3.3, run extracted `application.jar` with `java -jar` |
| Both Dockerfiles A and B fail HTTP | Likely app/port/profile issue unrelated to layering | Run JAR on host and read container startup logs |
| Both images return stale response | Built/copied old JAR or old container still running | Re-run `clean test bootJar`, check build context and container mappings |
| Cache B misses when Controller changes | Missing cache store, base image changed, non-deterministic metadata | Read BuildKit logs, inspect layer bytes, builder/registry cache |
| `dependencies` layer changes constantly | Dynamic SNAPSHOTs, timestamps in nested JARs, BOM changes | Pin/lock dependencies and audit reproducible outputs |
| `Dockerfile.layers` has many `COPY`s yet size unchanged | Layering reuses blobs rather than deleting libs | Measure push/pull bytes and digests instead of only `docker image ls` |
| Cannot reach HTTP from host | Forgot `-p`, app uses another port, or container not ready | `docker run -p HOST:CONTAINER`, logs, and `curl` |
| Container fails with non-root UID | Lacks read permissions on app/libs or write permissions on tmp/uploads | Check `USER`/file permissions/mounts, grant minimal permissions |
| Fresh CI runner always rebuilds everything | No persisted/remote Docker build cache | Configure cache backend/registry cache per policy; do not promise `CACHED` |
| A and B use different JRE runtimes | Dockerfiles specify different base images | Pin the exact same Java version/base digest for valid comparisons |
| Image B misses dependency after custom layering | Wrong grouping or confusing Boot layering `include/exclude` with artifact filtering | Inspect original archive, index, extracted folders, and runtime |
| Only B fails on deploy while local works | Different platform, env, permissions, or classpath in extracted image | Capture full logs, check image digests, smoke-test in prod-like environment |

### Layer-by-Layer Investigation Workflow

1. **JAR:** does `build/libs/app.jar` exist and run via `java -jar` on Java 17?
2. **Layer metadata:** is `BOOT-INF/layers.idx` present, and does `list-layers` show expected groups?
3. **Tools:** does `-Djarmode=tools ... extract --layers` run and produce the right folders?
4. **Dockerfile:** does build context contain the right JAR? Does `COPY` pick the right file? Does runtime have extracted `application.jar`?
5. **Runtime:** do container logs show `ClassNotFound`/port/config errors? Is the HTTP response correct?
6. **Cache:** does BuildKit have a suitable cache store? Which instructions do logs show as reused vs missed?
7. **Security/compatibility:** are Java, architecture, base image, UID, and secrets correct?
8. **CI:** is the deployed image the exact one smoke-tested, or did the pipeline rebuild a separate copy?

Never edit multiple layers, Java version, dependencies, and the Dockerfile at once before identifying which layer failed.

## 19. Dockerfile Security and Operations: Never Trade Away for Cache

**Common rules for both A and B:**

- **Controlled base images:** use a suitable JRE, scan CVEs, track digests, and update on schedule; do not pin a vulnerable version indefinitely just for cache stability.
- **Run as non-root:** explicit UID, minimal read/write permissions; do not run as root unnecessarily.
- **No credentials in the image:** secrets can linger in image layers/history even if deleted in a later layer. Use runtime secrets or BuildKit secret mounts per policy.
- **Do not copy the whole repository:** limit context using `.dockerignore` or a staging directory; especially avoid `.git`, `.env`, and Maven/Gradle credentials.
- **Do not enable debug or wrong production profiles:** Spring runtime options like `SPRING_PROFILES_ACTIVE` belong to deployment config; do not alter the Java entrypoint.
- **Ensure logs go to stdout/stderr:** Docker/Kubernetes collect console streams; do not write files inside an unmounted image filesystem by default.
- **Check multi-arch:** images for `linux/amd64` vs `linux/arm64` can have different native/JDK dependencies, affecting reproducibility and caching.
- **Use real health/readiness probes:** `EXPOSE` is not a health check; in Kubernetes configure proper probes without publicly exposing all Actuator management endpoints.
- **Run the tested image:** store immutable image digests and avoid rebuilding after tests without provenance.
- **Avoid over-engineering:** if Dockerfile B is overly complex yet performs nearly identically to A, prefer the simpler, well-tested option.

### About Cloud Native Buildpacks

Spring Boot also supports `bootBuildImage` (Gradle) or `spring-boot:build-image` (Maven) to produce images via **Cloud Native Buildpacks** instead of writing manual Dockerfiles. Buildpacks provide their own builder/run images, caching, and layering strategies. That is a **third option** when organizations want standardized image packaging with less Dockerfile maintenance.

Do not expect Buildpacks to produce identical images or layer digests to B; standardize on **one** organization-supported pipeline and measure its actual results. This lesson intentionally compares **two Dockerfile choices** using the same executable JAR.

## 20. Hands-On Lab and Completion Criteria

Perform on a test branch of a Spring Boot project with Docker and Java 17:

1. Create `DockerChoiceApplication`, `VersionController`, and `VersionControllerTest` per Section 5.
2. Choose Gradle Groovy/Kotlin or Maven as shown, and build **one** test-passing executable `app.jar`.
3. Run `java -jar app.jar` locally with a compatible JRE and confirm `GET /version` returns `image-v1`.
4. Create `Dockerfile.jar`, build image A, run the container, and verify response `image-v1`.
5. Verify the Boot archive contains `BOOT-INF/layers.idx` and the tools dependency; run `list-layers`.
6. Test extracting with `extract --layers`; inspect the four groups and extracted `application.jar`.
7. Create `Dockerfile.layers`, build image B, run the container, and verify the response matches image A.
8. Re-run `docker build --progress=plain` without changing source to observe baseline caching behavior.
9. Change the Controller and test to `image-v2`, rebuild the same JAR output path, and build both v2 images.
10. Use logs to compare A's whole-JAR `COPY` against B's four `COPY`s; record which instructions hit or missed cache in your actual environment.
11. Run images A-v2 and B-v2 and verify **both return `image-v2`**.
12. Try upgrading/adding a dependency and note why B's `dependencies` layer must update.
13. Explain how Docker `CACHED`, Gradle `FROM-CACHE`, and registry blob reuse are **separate caches**.
14. Inspect the Java runtime version, non-root permissions, port mapping, secret handling, and artifact/image digests.
15. Write a short conclusion: should your team use A or B given your code change rate, dependency footprint, network/registry/CI cache, and maintenance cost?
16. Revert experimental changes to code/tests/dependencies and do not leave unscanned images for production deployment.

**Pass criteria:** you can accurately explain why **layered archives do not automatically create Docker layers**, run the same Spring Boot JAR via both Dockerfiles, compare caching with evidence, and make a **context-aware decision** instead of blindly extracting every application before building an image.

## Official Reference Documentation

- [Spring Boot 3.3 – Dockerfiles](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3 – Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Efficient Deployments](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/oci-image.html)
- [Docker Docs – Build Cache](https://docs.docker.com/build/cache/)
- [Docker Docs – Optimize Cache Usage](https://docs.docker.com/build/cache/optimize/)
- [Docker Docs – Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker Docs – Dockerfile Reference](https://docs.docker.com/reference/dockerfile/)
- [OCI Image Specification](https://github.com/opencontainers/image-spec)