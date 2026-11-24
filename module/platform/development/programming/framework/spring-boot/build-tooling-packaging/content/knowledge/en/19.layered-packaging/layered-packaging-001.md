# Purpose of Layered Archives and Relationship with Container Layer Caching

## 1. Practical Problem and Learning Objectives

A Spring Boot executable JAR typically contains both application code and dozens or hundreds of libraries. When you change just one line in a Controller and repackage, **the overall JAR file changes**. If the Dockerfile only has `COPY app.jar app.jar`, that COPY step sees a new file and may create a new **container image layer** containing the entire JAR. This reduces cache reuse and forces the registry to store/transfer a large blob even though the library portion has barely changed.

**Layered archives** address this problem by recording **metadata that groups the contents** of a Spring Boot executable JAR/WAR into parts with different rates of change. Container image build tools can use that information to place stable libraries in earlier image layers and frequently changing application code in a later image layer.

After this lesson, you will be able to:

1. Explain what a Spring Boot layered archive is, how it differs from a standard `BOOT-INF/lib`, and how it differs from Docker/OCI image layers.
2. Describe the role of `BOOT-INF/layers.idx` and the four default layers: `dependencies`, `spring-boot-loader`, `snapshot-dependencies`, and `application`.
3. Understand why **layer order** and **change frequency** determine cache reuse in Docker builds and container registries.
4. Configure or inspect layered `bootJar` (Gradle) and `repackage` (Maven), and use `spring-boot-jarmode-tools` in Spring Boot 3.3 to list/extract layers.
5. Create a runnable Java 17+ Spring Boot example, build an executable JAR, and write a properly layered multi-stage Dockerfile.
6. Verify before and after modifying application code, observe cache hits on `COPY` steps, and distinguish them from the Gradle Build Cache or Maven dependency cache.
7. Understand the limitations of this technique: a layer index does not automatically optimize a Dockerfile that copies the whole JAR; caching does not guarantee artifact security or identical image digests.

**Illustrated versions:** Spring Boot Gradle/Maven Plugin **3.3.5**, Java **17**, compatible Gradle Wrapper/Maven Wrapper, and Docker Engine/BuildKit capable of building Linux images. Spring Boot 3.3 provides the **`-Djarmode=tools`** tool; the old `layertools` command was deprecated starting in Spring Boot 3.3. Do not assume these commands/launchers apply identically to every Boot version. Use the actual version approved by your project.

## 2. Two Different Meanings of the Word “Layer”

Before configuring anything, make sure to clearly distinguish:

| Layer type | Which system does it belong to? | What is it actually? |
| --- | --- | --- |
| **Spring Boot archive layer** | Spring Boot packaging plugin | A **group of files** inside an executable JAR/WAR, described by `layers.idx`; not yet an OCI image layer |
| **Docker/OCI image layer** | Container builder and image registry | A set of filesystem/metadata changes in an image; has its own content digest and can be cached/shared |
| **Gradle Build Cache entry** | Gradle build tool | The output of a task cached by inputs/implementation; not a Docker image layer |
| **Docker build cache** | Docker BuildKit/legacy builder | Reusable output of a Dockerfile step or build graph |
| **Maven/Gradle dependency cache** | Build tool | Local copies of JARs/POMs/metadata downloaded from repositories; does not itself create OCI layers |

You can think of Spring Boot `layers.idx` as a **map guiding** tools on how to separate sets of files inside an executable archive. The Dockerfile or Cloud Native Buildpacks must **actually use that map** to place each group into image layers. If you only generate `layers.idx` without consuming it, container caching gains no meaningful benefit.

### Visualizing the Flow

~~~text
Maven package/repackage OR Gradle bootJar
            |
            v
  Spring Boot executable JAR
  ├── BOOT-INF/classes/...
  ├── BOOT-INF/lib/...
  ├── Spring Boot launcher
  └── BOOT-INF/layers.idx   [grouping metadata]
            |
            v
  java -Djarmode=tools -jar app.jar extract --layers
            |
            v
  extracted/
  ├── dependencies/
  ├── spring-boot-loader/
  ├── snapshot-dependencies/
  └── application/
            |
            v
  Dockerfile: COPY each group in order
            |
            v
  Container image
  ├── base JRE layer(s)
  ├── dependencies layer
  ├── spring-boot-loader layer
  ├── snapshot-dependencies layer
  └── application layer
~~~

This is a conceptual diagram: the actual number of image layers also depends on other Dockerfile steps, metadata, base image, and builder optimizations. The four extracted directories are **Spring Boot groups**, while Docker is what creates the image filesystem layers.

## 3. What Does a Typical Executable JAR Look Like?

A Spring Boot executable JAR has a typical structure:

~~~text
layer-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...    (launcher)
└── BOOT-INF/
    ├── classes/
    │   └── com/example/layers/LayerDemoApplication.class
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-webmvc-*.jar
    │   └── ...                           (runtime libraries)
    ├── classpath.idx                     (may be present)
    └── layers.idx                        (layer metadata)
~~~

**Key points to remember:**

- `BOOT-INF/classes` contains application classes/resources.
- `BOOT-INF/lib` contains packaged dependency JARs (nested JARs).
- The Spring Boot launcher enables the JVM to run `java -jar` with the nested library structure.
- `BOOT-INF/layers.idx` lists the **archive paths assigned to specific named layers** and the preferred order for placing them into a container image.
- `BOOT-INF/classpath.idx`, if present, serves classpath ordering; **it does not have the same function** as `layers.idx`.
- The `layers.idx` file contains only metadata; it **does not physically move** JARs out of `BOOT-INF/lib` or turn one JAR into multiple artifacts at build time.

**A layered JAR is still a valid executable JAR.** With Spring Boot 3.3.5 for example, `java -jar layer-demo-0.0.1-SNAPSHOT.jar` still works as before; the file grouping serves container packaging.

### Example of What layers.idx Looks Like

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/spring-core-6.x.y.jar"
  - "BOOT-INF/lib/spring-boot-3.3.5.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/launch/JarLauncher.class"
- "snapshot-dependencies":
  - "BOOT-INF/lib/my-client-1.0-SNAPSHOT.jar"
- "application":
  - "BOOT-INF/classes/com/example/layers/LayerDemoApplication.class"
~~~

This is an **illustration of syntax and paths**; `6.x.y` and `my-client` are not an actual file list in the sample project. Real JARs contain many more entries, and the `snapshot-dependencies` layer may have no JARs if no snapshots are used. The plugin tool generates `layers.idx` accurately according to the archive contents and active version rules.

## 4. Spring Boot's Four Default Layers

With Spring Boot 3.3, default layering for an executable JAR/WAR typically uses four groups in order:

| Order | Layer | Typical contents | Why placed in this position? |
| --- | --- | --- | --- |
| 1 | `dependencies` | **Non-project dependencies** whose version does not contain `SNAPSHOT` | Usually the most stable across code edits |
| 2 | `spring-boot-loader` | Boot launcher classes under `org/springframework/boot/loader` | Only changes when the Boot loader/plugin changes |
| 3 | `snapshot-dependencies` | External libraries whose version contains `SNAPSHOT` | Likely to change frequently while keeping the same coordinates |
| 4 | `application` | Application classes/resources and local project/module dependencies | Changes the most when developers edit source code |

### 4.1. dependencies

These are external non-snapshot JARs: Spring Framework, Spring Boot starters, logging libraries, and other stable runtime dependencies (depending on the actual graph). If you modify a Controller without changing versions, dependencies usually **remain byte-identical**. Placing them early gives Docker caching the opportunity to reuse the corresponding layers.

**This does not mean these dependencies “never change”**. Upgrading a BOM, changing the Spring Boot version, or updating a driver or transitive dependency will change the JAR files in `dependencies`; cache invalidation in that case is **correct**.

### 4.2. spring-boot-loader

Contains Spring Boot's launcher code, such as `org.springframework.boot.loader.launch.JarLauncher`. The loader is usually stable across business code edits. Separating the loader prevents it from having to be copied again every time a Controller class changes.

**Do not confuse the Boot launcher with Spring MVC or auto-configuration libraries.** Many Spring Boot libraries reside in `BOOT-INF/lib` and belong to `dependencies`, not the `spring-boot-loader` layer.

### 4.3. snapshot-dependencies

Intended for non-project dependencies carrying a `SNAPSHOT` version. This is a common signal for an artifact that may still change before release; therefore, the snapshot layer is placed **after** the stable layers to avoid busting their cache when a SNAPSHOT changes.

A SNAPSHOT from a repository can be republished with **the same version string but different bytes**. Dependency resolution policies, checksum verification, and caching must still ensure the project fetches the right artifact; layered packaging does not make a SNAPSHOT immutable.

### 4.4. application

Includes compiled classes, application resources, and local module/project dependencies that the plugin classifies into the application layer. Editing `GreetingController.java`, adding an endpoint, or changing `application.yml` usually affects this layer. Because it is placed **last**, application changes do not necessarily invalidate the stable image layers copied earlier.

**Note on multi-module builds:** in Gradle, project dependencies are placed in `application` by default; in Maven, modules belonging to the same build/reactor can be treated as local module dependencies. A frequently changing internal library module can cause changes in the application layer; this default is intentional but can be adjusted when genuinely needed.

## 5. Why Does Layer Order Affect Docker Caching?

A standard Dockerfile executes sequentially. The builder reuses the result of an instruction if the instruction and **its relevant inputs** qualify for caching. When one step misses the cache, subsequent dependent steps typically must produce new results, even if there is a step copying rarely changing data.

Suppose two images are built consecutively:

~~~text
Build A:
FROM JRE
COPY dependencies/         -> image layer D1
COPY spring-boot-loader/   -> image layer L1
COPY snapshot-dependencies/-> image layer S1
COPY application/          -> image layer A1

Build B: only change LayerDemoApplication.java
FROM JRE                   -> base layer reused
COPY dependencies/         -> D1 reused
COPY spring-boot-loader/   -> L1 reused
COPY snapshot-dependencies/-> S1 reused
COPY application/          -> new layer A2
~~~

This diagram shows what is **expected when Docker caching works and the inputs to the first three COPY steps do not change**. Actual `CACHED` output depends on the builder, cache storage, and how the pipeline runs. Ordering from least frequently changed to most frequently changed is **not an arbitrary rule**: it protects large/stable layers from unnecessary invalidation when application code changes.

### Comparing Two Dockerfiles

**Approach 1 – Copy the whole JAR:**

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/layer-demo-0.0.1-SNAPSHOT.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

When you change a single byte in the application and rebuild the Boot JAR, **the entire JAR file changes from the perspective of the COPY input**. Docker cannot know to preserve the `BOOT-INF/lib` portion inside the JAR. It will recreate the COPY layer containing the entire JAR (assuming the cache no longer matches).

**Approach 2 – Split by layered archive:** a multi-stage Dockerfile that extracts and copies each group separately will be shown in section 9. With that approach, Docker receives **four independent inputs** to compute caching for each step.

**Core takeaway:** Boot's `layers.idx` **cannot automatically increase Docker cache hits if the Dockerfile still copies the whole JAR in a single step**. The image builder must use `jarmode` or other tooling to extract/create OCI layers according to the metadata.

## 6. Do Not Confuse Build Cache, Image Cache, and Image Registry

| Technology | What is cached | When is it beneficial? | What cannot be concluded |
| --- | --- | --- | --- |
| Gradle Build Cache | Outputs of `compileJava`, `test`, and other cacheable tasks | Repeated tasks with the same inputs | Does not prove Docker reuses layers |
| Maven local repository | Resolved JARs/POMs | Reduces dependency downloads | Does not prove the Spring Boot layered archive is correct |
| Docker/BuildKit cache | Instruction/build graph results, filesystem layers | Faster image rebuilds | Does not prove the code has been tested |
| OCI registry blob deduplication | Layer blobs with matching digests across image versions | Reduces data needing upload/download and storage | Does not necessarily reduce the total deployed size |
| Spring Boot layers.idx | Metadata mapping archive entries → logical layers | Guides splitting of executable JAR/WAR | Is not a cache and is not an image layer |

**Example:** If Gradle reports `:bootJar UP-TO-DATE` while Docker copies the whole `application.jar`, the Dockerfile still has **one single layer for the entire JAR**. Conversely, Gradle might re-execute `bootJar` while Docker still reuses Docker layers if the contents of the corresponding extracted directories are identical.

Layer reuse is also affected by the base image, build arguments, metadata, platform, Dockerfile commands, cache backend, and CI runner. If CI always spins up a fresh builder without loading prior cache, you may not see `CACHED` even when layering is configured properly. Remote cache or registry cache export/import must be set up separately if the environment requires it.

## 7. A Runnable Java 17 Spring Boot Example

Let's create a small Spring Boot Web MVC API. It accepts an HTTP request and returns a fixed string, which is enough to modify one line in the application layer without changing dependencies.

### 7.1. Project Structure

~~~text
layer-demo/
├── settings.gradle
├── build.gradle
├── gradlew, gradlew.bat, gradle/wrapper/
├── Dockerfile                 (layered example in section 9)
├── .dockerignore
└── src/
    ├── main/java/com/example/layers/
    │   ├── LayerDemoApplication.java
    │   └── VersionController.java
    └── test/java/com/example/layers/
        └── VersionControllerTest.java
~~~

The diagram assumes the project already has a **valid Gradle Wrapper**. If a real repository uses Maven, see the POM in section 11 instead of maintaining both Maven and Gradle side-by-side just for an exercise.

### 7.2. settings.gradle File

~~~groovy
rootProject.name = 'layer-demo'
~~~

### 7.3. Complete build.gradle File — Gradle Groovy DSL

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

// Spring Boot 3.3 creates an index for layered archives by default.
// Explicitly declared in the demo to show the exact intent.
tasks.named('bootJar') {
    layered {
        enabled = true
    }
    includeTools = true
}

springBoot {
    mainClass = 'com.example.layers.LayerDemoApplication'
}
~~~

**Explanation:**

1. `java` creates main/test source sets, `compileJava`, and test tasks.
2. `org.springframework.boot` creates the `bootJar` task and integrations for packaging executable JARs.
3. `io.spring.dependency-management` works with the Spring Boot plugin to import the appropriate BOM, so starter dependencies do not need explicit versions.
4. `testImplementation` adds test dependencies only to the test classpath; they do not enter the default runtime image.
5. `layered { enabled = true }` generates `BOOT-INF/layers.idx`. In Spring Boot 3.3, layering **is enabled by default**, but declaring it explicitly is convenient for verification/instruction.
6. `includeTools = true` keeps `spring-boot-jarmode-tools` inside the Boot JAR so `-Djarmode=tools` can be used. If you set `includeTools=false`, you cannot by default run extract commands using tools from that artifact itself.
7. `springBoot.mainClass` ensures the launcher knows the exact application main class.
8. Java toolchain 17 ensures compilation with the proper JDK; the Gradle Wrapper must also be compatible with the chosen Boot plugin.

If the repository centrally manages dependency repositories in `settings.gradle` with `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, remove `repositories { mavenCentral() }` from the project and use the repository configured in settings. This is a dependency governance requirement, not a layered archive setting.

### 7.4. LayerDemoApplication.java File

Path `src/main/java/com/example/layers/LayerDemoApplication.java`:

~~~java
package com.example.layers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LayerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LayerDemoApplication.class, args);
    }
}
~~~

This is a Java class independent of the Controller and compiles when Spring Boot dependencies are on the classpath. It starts a Spring MVC web application with embedded Tomcat; the default port is usually 8080 unless configured otherwise.

### 7.5. VersionController.java File

Path `src/main/java/com/example/layers/VersionController.java`:

~~~java
package com.example.layers;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {
    @GetMapping("/version")
    public String version() {
        return "layer-v1";
    }
}
~~~

This is a complete Java class with `@RestController`, scanned because it resides under `com.example.layers`. Once the application is running successfully, an HTTP GET to `/version` returns the exact body:

~~~text
layer-v1
~~~

### 7.6. VersionControllerTest.java File

Path `src/test/java/com/example/layers/VersionControllerTest.java`:

~~~java
package com.example.layers;

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
    void returnsVersion() throws Exception {
        mvc.perform(get("/version"))
                .andExpect(status().isOk())
                .andExpect(content().string("layer-v1"));
    }
}
~~~

This test can run via Gradle `test { useJUnitPlatform() }` and Spring Boot Starter Test. When changing the Controller response to `layer-v2` in the exercise, **update the test assertion accordingly**, otherwise the build fails at the test step. That is the right behavior for tests: layer optimization must not bypass functional quality gates.

## 8. Building the Layered JAR and Verifying layers.idx

### 8.1. Linux/macOS

From the project root:

~~~bash
./gradlew --version
./gradlew clean test bootJar

jar tf build/libs/layer-demo-0.0.1-SNAPSHOT.jar |
    grep -E 'BOOT-INF/(layers.idx|classes/|lib/)'
~~~

### 8.2. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar

jar tf .\build\libs\layer-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/(layers.idx|classes/|lib/)'
~~~

**Signs to confirm:**

- `BOOT-INF/layers.idx` exists in the Boot executable JAR.
- `BOOT-INF/classes/com/example/layers/LayerDemoApplication.class` and `VersionController.class` exist.
- Runtime JARs exist in `BOOT-INF/lib`, including Spring Framework/Spring Boot/Tomcat resolved by the BOM.
- `spring-boot-jarmode-tools` is present in the archive if `includeTools=true` and the plugin version supports it.
- Run the actual `layer-demo-0.0.1-SNAPSHOT.jar` file, **not `-plain.jar`** if Gradle also generates a plain JAR.

If `jar tf` does not find `BOOT-INF/layers.idx`, check whether the actual task was `bootJar`, whether `layered.enabled=false` was set in another configuration, or whether you are reading a plain or stale archive. **Do not add a handwritten `layers.idx` file** to pretend layering is enabled.

### 8.3. Listing Layers with Spring Boot 3.3 JAR Tools

Linux:

~~~bash
java -Djarmode=tools \
    -jar build/libs/layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

Windows PowerShell, written on one line to avoid shell escaping confusion:

~~~powershell
java -Djarmode=tools -jar .\build\libs\layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

With the default configuration, the listed layer names include:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

**Output order and formatting may depend on version/custom layer definitions**, and a layer can be empty. The command only provides information; **it does not create a Docker/OCI image**.

### 8.4. Extracting into Layer Directories

Linux/macOS:

~~~bash
mkdir -p build/layer-inspection

java -Djarmode=tools \
    -jar build/libs/layer-demo-0.0.1-SNAPSHOT.jar \
    extract --layers --destination build/layer-inspection

find build/layer-inspection -maxdepth 2 -type d
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\build\layer-inspection | Out-Null

java -Djarmode=tools -jar .\build\libs\layer-demo-0.0.1-SNAPSHOT.jar extract --layers --destination .\build\layer-inspection

Get-ChildItem .\build\layer-inspection\
~~~

The expected result is subdirectories corresponding to `dependencies`, `spring-boot-loader`, `snapshot-dependencies`, and `application`. They have a file structure suitable for copying/overlaying in the final image.

**Version note:** Spring Boot 3.3 uses the command `java -Djarmode=tools -jar app.jar extract --layers --destination ...`. Older documentation references `-Djarmode=layertools` and `spring-boot-jarmode-layertools`; that is the legacy mechanism name, **not the preferred choice in Boot 3.3 examples**.

**Limitation:** Spring Boot tools mode does not work with a **fully executable archive that has a prepended launch script**. If a project calls `launchScript()` to build a JAR runnable as a shell script, disable the launch script for artifacts used with jarmode tools, or use another supported packaging flow. This is an important practical boundary when you want both a launcher script style and layer extraction.

## 9. Multi-stage Dockerfile to Leverage the Layers

File `Dockerfile` at the project root:

~~~dockerfile
# Stage 1: extract contents according to Spring Boot layers.idx
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /workspace

COPY build/libs/layer-demo-0.0.1-SNAPSHOT.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

# Stage 2: runtime only needs the JRE and extracted files
FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**This is a complete Dockerfile for the Boot 3.3 example, following the extracted layout produced by Spring Boot 3.3 jarmode tools.** It is used after running Gradle `bootJar`. `-Djarmode=tools` in the build stage runs in tool mode and does not start an HTTP server. The `extract --layers` command creates a Boot-supported layout where the `application` portion contains the layered application JAR usable with the dependencies copied into the working directory; the runtime stage runs `java -jar application.jar`.

Step-by-step explanation:

1. **Extractor stage:** copies the **whole Boot JAR** into a build environment with Java to invoke tools mode. This stage **may need to re-run** when an application class changes; this is an acceptable processing cost.
2. **Runtime stage:** starts from a JRE image. Choose the right Java major version compatible with bytecode and dependencies.
3. **COPY dependencies:** creates a layer containing most release library JARs that rarely change. This is usually the largest layer among app-specific layers.
4. **COPY spring-boot-loader:** copies the launcher, typically stable if the Spring Boot version stays the same.
5. **COPY snapshot-dependencies:** copies snapshot dependencies, which may change more often than release dependencies.
6. **COPY application:** places compiled classes/resources and internal modules at the end, so Controller edits usually affect only this final layer.
7. **ENTRYPOINT:** uses `java -jar application.jar` for the extracted layout produced by Boot 3.3 tools. **Do not blindly change this to `java -jar` on the raw fat JAR in the runtime stage**, because the fat JAR is not copied whole into the final stage in this Dockerfile.
8. **EXPOSE 8080:** declares the expected port; `EXPOSE` itself does not publish the port to the host and does not guarantee the app is running.
9. Do not use wildcard `COPY build/libs/*.jar` in the demo: Gradle may also generate `-plain.jar`, leading to copying multiple files or picking the wrong artifact.

### 9.1. .dockerignore File

You should restrict the Docker build context to avoid accidentally sending caches, credentials, and temporary files. Example:

~~~dockerignore
.git
.gradle
.idea
.vscode
.repro-check
**/*.log
build/**
!build/libs/
!build/libs/layer-demo-0.0.1-SNAPSHOT.jar
~~~

**.dockerignore note:** re-inclusion rules for `build/libs` must be tested with your actual Docker version/build context; Docker supports `!` exceptions, though excluded parent directories can affect traversal. For a small demo, a simpler approach is to **exclude only secret/temporary directories** without excluding `build`, and then verify `build/libs/layer-demo-0.0.1-SNAPSHOT.jar` is present in the Docker context. In production, use a context built specifically from tested artifacts or a Dockerfile-specific ignore policy to avoid pulling in the whole `build` directory unnecessarily.

**Never place secrets** into the build context, `ARG`/`ENV`, or layers by copying credential files. Docker image layers retain history and can be inspected, so “deleting a file in a later layer” does not necessarily remove the secret from an earlier layer blob.

### 9.2. Building and Running the Image

Linux/macOS:

~~~bash
./gradlew clean test bootJar
docker build --progress=plain -t layer-demo:one .
docker run --rm -p 8080:8080 layer-demo:one
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
docker build --progress=plain -t layer-demo:one .
docker run --rm -p 8080:8080 layer-demo:one
~~~

Once the container is ready, in another terminal:

~~~bash
curl -fsS http://localhost:8080/version
~~~

HTTP response body:

~~~text
layer-v1
~~~

If using PowerShell:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/version"
~~~

To run the demo on a different port if host port 8080 is occupied, map host port 8081 to container port 8080: `docker run --rm -p 8081:8080 layer-demo:one` and then call `http://localhost:8081/version`. There is no need to change Spring Boot `server.port` just to resolve a host-port conflict.

## 10. Two-Build Docker Experiment to Observe Caching

Goal: change **only one return string** in the Controller and verify that stable libraries are not treated as changed in their corresponding COPY steps.

### Step A — Baseline

1. Ensure `VersionController.version()` returns `"layer-v1"`; the test expects `layer-v1`.
2. Run Gradle `clean test bootJar`.
3. Run `docker build --progress=plain -t layer-demo:one .`.
4. Save the build log, especially the `COPY --from=extractor ...dependencies` and `application` steps.
5. Run the image and verify `GET /version` returns `layer-v1`.

### Step B — Change Only the Application

In `VersionController.java`, change:

~~~java
return "layer-v1";
~~~

to:

~~~java
return "layer-v2";
~~~

Then update the assertion in `VersionControllerTest.java` from `layer-v1` to `layer-v2`; **do not modify `build.gradle` or dependency versions**.

Run:

~~~bash
./gradlew clean test bootJar
docker build --progress=plain -t layer-demo:two .
~~~

Verify:

~~~bash
docker run --rm -p 8081:8080 layer-demo:two
~~~

Then call `http://localhost:8081/version` (if host port 8081 is free); the response body is:

~~~text
layer-v2
~~~

In an environment with a valid Docker build cache, the **three stable COPY steps** (`dependencies`, `spring-boot-loader`, `snapshot-dependencies`) may show `CACHED` or an equivalent reuse mechanism, while `application` creates a new layer. **Do not claim “100% CACHED” if the logs do not prove it**: the build cache could have been cleared, the builder instance could have changed, or the base image could have received a new digest.

### Step C — Change a Dependency

Add/update a runtime dependency version or upgrade the Spring Boot BOM (on a test branch), rebuild, and observe the logs. This time `dependencies` or `spring-boot-loader` may change; subsequent layers **may also miss the cache** even if the application changed very little. This is a logical consequence of the Docker layer chain.

**Restore** dependencies/Controller/test back to the baseline after the experiment. Do not change a multi-module framework version just to measure caching in a real project without compatibility testing.

### How to Read Docker Logs

Docker BuildKit may print `CACHED` for a reused step. Many steps execute very quickly without printing “CACHED”; read the detailed logs instead of guessing. If `docker build` reports “failed to solve” or cannot find the extractor output directory, verify that `jarmode tools extract` created the right directories and that the Docker COPY source path is valid.

## 11. Maven Also Supports Layered Executable Archives

Because this topic focuses on the Spring Boot layered archive concept, the same model also applies to Maven. When using Spring Boot Starter Parent, the Maven plugin `spring-boot:repackage` typically generates `layers.idx` by default.

### Complete POM for an Equivalent Maven Example

File `pom.xml` for a **separate Maven project**, using the same two Java classes from section 7:

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
    <artifactId>layer-demo</artifactId>
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

**This is a separate POM replacing the Gradle project**; maintaining both build tools in the same application is not recommended. With Spring Boot Parent, the `repackage` goal is already configured; the plugin builds the executable JAR and layers index. The `enabled`/`includeTools` settings in the example only state the intent explicitly, matching Spring Boot 3.3 defaults per that version's documentation.

Run:

~~~bash
./mvnw clean verify
jar tf target/layer-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/layers.idx'
java -Djarmode=tools -jar target/layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

If adapting the Dockerfile in section 9 to Maven, replace:

~~~dockerfile
COPY target/layer-demo-0.0.1-SNAPSHOT.jar application.jar
~~~

for the extractor stage's COPY line. The `extract --layers` part and the `COPY --from=extractor` lines in the final stage keep the same meaning.

**Do not confuse Maven dependency management with Spring Boot plugin management.** If a project only imports the `spring-boot-dependencies` BOM without inheriting Parent, it must declare the appropriate plugin version and `repackage` execution; a BOM alone **does not automatically produce an executable JAR or `layers.idx`**.

## 12. Custom Layers and Layer Order: When Are They Needed?

The default configuration is already suitable for many projects. When an internal module contains mostly rarely changing logic or has frequently changing code generation, you can create a separate layer to optimize caching. However, customizing layering too early easily increases the number of layers and operational complexity.

### 12.1. Gradle DSL Explicitly Defining the Defaults

The following snippet is a **replacement for the `tasks.named('bootJar')` configuration in section 7**, describing Spring Boot 3.3's default rules in Groovy DSL:

~~~groovy
tasks.named('bootJar') {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include "org/springframework/boot/loader/**"
            }
            intoLayer("application")
        }
        dependencies {
            intoLayer("application") {
                includeProjectDependencies()
            }
            intoLayer("snapshot-dependencies") {
                include "*:*:*SNAPSHOT"
            }
            intoLayer("dependencies")
        }
        layerOrder = [
            "dependencies",
            "spring-boot-loader",
            "snapshot-dependencies",
            "application"
        ]
    }
}
~~~

**Explanation:**

- `application { ... }` defines how classes/resources and launcher files go into each layer.
- `dependencies { ... }` classifies nested dependency artifacts.
- `includeProjectDependencies()` puts Gradle `project(':module')` modules into `application`.
- `include "*:*:*SNAPSHOT"` is a `group:artifact:version` pattern for snapshot dependencies.
- `intoLayer("dependencies")` at the end catches the remainder not claimed by earlier layers.
- `layerOrder` is the **layer writing/copying order**; it can differ from the order in which you declare `intoLayer`.
- Matchers are evaluated **top to bottom**; content already claimed by a layer will not be reassigned by a later layer.
- `layerOrder` must cover **every layer name** referenced in `intoLayer`.

**Very important:** `include`/`exclude` inside `layered` **only decide which layer a file belongs to**; they do not exclude a dependency from the executable JAR. To exclude a module from the artifact, modify the dependency graph or `bootJar.classpath` via the appropriate API, then inspect the final executable JAR.

### 12.2. Equivalent Kotlin DSL

In `build.gradle.kts`, the same logic:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }
            intoLayer("application")
        }
        dependencies {
            intoLayer("application") {
                includeProjectDependencies()
            }
            intoLayer("snapshot-dependencies") {
                include("*:*:*SNAPSHOT")
            }
            intoLayer("dependencies")
        }
        layerOrder.set(
            listOf(
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "application"
            )
        )
    }
}
~~~

This is a configuration fragment for a Kotlin Gradle DSL project that already applies the Spring Boot plugin; place `import` at the top of the file. Do not copy this fragment verbatim into a Maven project or a project without a `bootJar` task.

### 12.3. Maven Custom Layers

The Maven plugin also supports a `layers.xml` file to define `application`, `dependencies`, and `layerOrder`. The configuration has its own XML syntax and uses `includeModuleDependencies` instead of Gradle's `includeProjectDependencies`. Do not take the Groovy DSL and guess XML tags from it. Refer to the `Spring Boot Maven Plugin – Layered Jar or War` documentation to configure the exact schema/XSD for your running version.

### 12.4. When Should Customization Be Avoided?

- A project only has a few classes and stable dependencies: defaults are enough.
- CI has no cache across builds: adding extra layers without a cache store may not help much.
- Every layer changes together due to dynamic dependencies/generators: fix the unstable inputs first.
- Container images change their base image every build: Docker invalidates subsequent steps regardless of custom layers.
- The team lacks a smoke test running the **real image**: changing image structure before verifying runtime can introduce unnecessary risk.

## 13. Can Layered Archives Be Applied to WARs?

Yes. Spring Boot supports layered executable WARs with `layers.idx`, but the WAR layout differs from JAR:

~~~text
Spring Boot executable JAR:
  BOOT-INF/classes/
  BOOT-INF/lib/
  BOOT-INF/layers.idx

Spring Boot executable WAR:
  WEB-INF/classes/
  WEB-INF/lib/
  WEB-INF/lib-provided/
  WEB-INF/layers.idx
~~~

In a WAR, `WEB-INF/lib-provided` is typically used for container libraries marked `provided`/`providedRuntime`, supporting executable WARs without conflicts when deployed to an external Servlet container. When building an image from a WAR, follow the **corresponding WAR tools and layout**, rather than applying a JAR Dockerfile to a WAR because artifact structure and launcher behavior differ.

Gradle has the `bootWar` task when the `war` plugin is applied; Maven uses `<packaging>war</packaging>` and `spring-boot:repackage`. Both require checking `WEB-INF/layers.idx` on the actual artifact.

**The core problem remains unchanged:** whether JAR or WAR, layer metadata is only useful if the image builder uses it to separate files into appropriate OCI image layers.

## 14. Practical Benefits and What Must Not Be Overpromised

### 14.1. Common Benefits

- **Faster image builds:** when only application code changes, Docker has the opportunity to reuse dependency and loader layers.
- **Reduced re-uploads/re-pulls:** registries can reuse existing blobs instead of uploading/downloading the entire fat JAR again.
- **Sensible caching across releases:** separates frequently changing parts (application) from stable parts (third-party libraries).
- **Easier inspection of contents:** `layers.idx` and extracted directories help clarify what an artifact contains and how it is partitioned.
- **Buildpack/CI workflow support:** tools that understand layered archives can leverage this information when creating OCI images.
- **Reduced downstream invalidation:** only changes the end of the image build graph when inputs to earlier layers do not change.

### 14.2. What Layering Does Not Automatically Guarantee

- **Does not make the JAR smaller.** Libraries remain inside the executable archive; adding metadata/tools can even slightly increase file size.
- **Does not guarantee faster JVM startup.** Startup speed depends on class loading, JIT, CDS, I/O, AOT, container, and application logic, not just how layers are split.
- **Does not remove CVEs or unnecessary libraries.** To reduce attack surface, evaluate and remove dependencies at the source and scan images/SBOMs.
- **Does not keep the entire image digest identical** when only source changes. Having the image manifest/application layer change is expected.
- **Does not guarantee cache hits if the base image or toolchain changes.** Registry/cache backend, content digests, Dockerfile commands, and build context still govern caching.
- **Does not replace reproducible builds.** Volatile timestamps, generated files, SNAPSHOT artifacts, or dynamic versions can cause dependency/application layers to change even if business code has not changed.
- **Does not replace testing.** A cached layer from a previous run does not prove the new image can start up or serve APIs correctly.

## 15. Cloud Native Buildpacks and build-image

Besides manual Dockerfiles, Spring Boot has tasks/goals to build OCI images via **Cloud Native Buildpacks**, such as `bootBuildImage` in Gradle or `spring-boot:build-image` in Maven. Buildpacks have their own lifecycle/cache and layering rules; with a suitable builder they can take advantage of dependency/application grouping.

**Do not equate these three things by default:**

1. **`bootJar`** creates an executable JAR and `layers.idx`.
2. A **multi-stage Dockerfile** written by you uses `jarmode tools` to COPY each layer.
3. **Cloud Native Buildpacks** builds an image through a builder/lifecycle/cache according to buildpack mechanisms.

Each workflow differs in control over Dockerfile, base image, build/run images, and caching. When using `bootBuildImage`, you do not need to write the Dockerfile from section 9, but you must check the selected builder, cache strategy, network, credentials, image tags, and actual resulting image. Do not claim Buildpacks always use **the exact same four layers** as a manual Dockerfile in every version.

If a project has already standardized on one of the two flows, evaluate that flow first instead of adding a second Dockerfile just to get layering. Two coexisting flows can produce images with different dependencies/versions and make released artifacts harder to trace.

## 16. CI, Docker Cache, and Artifact Governance

### 16.1. Minimal CI Workflow

1. **Pin source commit**: check out the exact commit, do not build from an undetermined working tree.
2. **Pin JDK/Wrapper/BOM**: use Java 17 and Gradle/Maven Wrapper/dependencies per policy.
3. **Run tests**: `./gradlew clean test bootJar` or `./mvnw clean verify`.
4. **Verify archive**: `jar tf` shows `layers.idx`, JAR tools can `list-layers` and extract successfully.
5. **Build OCI image from the exact executable JAR** just tested; do not accidentally copy `-plain.jar`.
6. **Observe cache**: retain Docker build logs and record which `COPY` steps reused cache or missed.
7. **Smoke test the image**: run the container and call `GET /version`.
8. **Scan/SBOM**: check vulnerabilities and licenses per policy; layering does not exempt this step.
9. **Publish by immutable digest**: apply meaningful tags, record the digest, push the image to an authorized registry.
10. **Deploy the exact tested digest**, without rebuilding with dynamic dependencies at the last minute.

### 16.2. Note on Clean CI Runners

On a brand-new runner, the Docker build cache may be empty; two builds on two different runners may **not** reuse cache unless export/import to a registry/remote BuildKit cache or a persistent builder is configured.

For example, BuildKit `buildx` supports cache export/import through a registry, though syntax/usage policy depends on the provider and registry permissions. Do not push cache containing sensitive data in the pipeline just to make `CACHED` appear.

### 16.3. Base Image Is Also an Input

`FROM eclipse-temurin:17-jre` is a **moving tag**; when the tag points to a new image, parent image layers/digests can change, invalidating the cache. For release reproducibility and security, consider pinning the image by a **specific digest** verified by your organization, and maintain a regular process to update the digest for patches.

**Do not keep an outdated base image forever just for cache hits.** OS/JRE patches are more important than avoiding rebuilds; measure cache efficiency after you have an appropriate base image upgrade policy.

## 17. Common Errors and How to Handle Them

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `BOOT-INF/layers.idx` not found | Built with plain `jar`, layering disabled, or stale artifact | Run `bootJar`; check `layered.enabled` and the right file |
| `java -Djarmode=tools` reports no such mode | Older plugin/Boot version, `includeTools=false`, or wrong JAR built | Check Spring Boot 3.3 and `spring-boot-jarmode-tools` in the archive |
| `tools extract` fails on a JAR with launch script | Fully executable archive with prepended shell script | Disable `launchScript()` for artifacts meant to be extracted |
| `layertools` docs differ from `tools` | Boot 2.x/early 3.x docs differ from 3.3 | Use `-Djarmode=tools ... extract --layers` for Boot 3.3 |
| Docker COPY cannot find extracted/dependencies | Extract did not run, wrong stage path, or custom layer names | Inspect builder-stage filesystem and `list-layers` |
| Only one Docker layer seen for the app | Dockerfile copies the whole fat JAR | Use tools extract and separate `COPY --from` instructions |
| `dependencies` layer changes when only Controller changed | Dynamic/SNAPSHOT dependency, generated metadata, or unstable artifact rebuild | Compare extracted dependencies bytes/checksums and dependency graph |
| Docker does not show `CACHED` on rebuild | New builder/cache, `--no-cache`, new base image, changed context/instruction | Inspect `docker build --progress=plain`, cache store, `FROM` digest |
| Final container cannot run `application.jar` | Missing a copied group, wrong entrypoint/extracted layout | Compare Dockerfile against Boot 3.3 docs, run image and check stack trace |
| Port unreachable | Container not started, host port not mapped, app listening on another port | Check logs and `docker run -p HOST:8080` |
| Image hash changes when code changes | `application` layer changing is expected; new manifest/digest | Compare digests of stable layers individually rather than demanding an immutable full image digest |
| Runtime ClassNotFound error | Missing nested JAR during extract/copy or dependency excluded from artifact | Inspect `BOOT-INF/lib`, extracted folders, and dependency graph |
| Wanted to exclude a JAR from image but only configured layer include/exclude | Layer DSL changes grouping, not artifact inclusion | Fix dependency graph/`bootJar` classpath and scan artifact |
| Buildpacks image differs from Dockerfile image | Two builders differ in layering/base image and launch mechanism | Do not compare outputs as the same pipeline; verify each flow separately |
| Docker image size did not decrease | Layering targets byte reuse/transfer, not removing dependencies | Evaluate module dependencies, base image, and startup separately |
| CI tests pass but runtime fails | CI tests use Gradle classpath, real container not run | Add a container smoke test and keep the exact image digest |
| Snapshot dependency causes frequent cache misses | `SNAPSHOT` can change in repository | Use released/locked versions where appropriate and verify provenance |
| Secret leaked in image | Credentials copied into a layer or passed via build args | Use secret mounts/runtime secret managers and audit image history |

### Ordered Troubleshooting Steps

1. Read `./gradlew --version` and the Spring Boot plugin version; confirm the example uses a Boot 3.3 compatible setup.
2. Run `jar tf` and check `BOOT-INF/layers.idx`, `BOOT-INF/lib`, Boot loader, and tools dependency.
3. Run `java -Djarmode=tools -jar ... list-layers` to read the actual layer names.
4. Extract to a new directory and inspect files in each layer and the `application.jar` layout.
5. Check whether the Dockerfile has the right `COPY --from=extractor` lines in order.
6. Run `docker build --progress=plain` and inspect which steps hit or miss cache.
7. If the dependencies layer changed, compare files/checksums in extracted dependencies and the dependency graph; do not infer from filenames alone.
8. Run the container and HTTP smoke test before claiming optimization success.
9. On error, roll back to a tested JAR/image; never skip tests to force container cache hits.

## 18. Evidence-Based Cache Verification Instead of Guessing

**An A/B experiment** should collect at least:

| Observation | Build A (Controller v1) | Build B (Controller v2) | Meaning |
| --- | --- | --- | --- |
| Spring Boot `layers.idx` | Has 4 default layer names | Still has 4 names | Layer metadata is generated |
| `dependencies` content | Baseline hash/list | Unchanged if dependencies stay the same | Stable release library group |
| `spring-boot-loader` content | Baseline hash/list | Unchanged if Boot stays the same | Stable launcher |
| `snapshot-dependencies` | May be empty | Usually unchanged in demo | No new SNAPSHOT |
| `application` content | Contains `layer-v1` | Contains `layer-v2` | Right layer changed |
| Docker build logs | COPY steps create output initially | First three COPYs may be reused; new application | Cache affects image build |
| HTTP smoke test | `layer-v1` | `layer-v2` | Final image runs the right code |

A good measurement compares **OCI layer digests** or Docker builder logs, not just total build duration. First runs involve network/downloads while subsequent runs have warm caches and filesystem buffers, causing times to vary for many reasons.

**Docker cache correctness** differs from performance: a COPY step being cached when inputs are unchanged is valid; when app code changes, the build must produce a **new application layer** or equivalent updated output. Successful optimization means **not recreating stable layers unnecessarily**, while still delivering the right code and dependencies into the image.

## 19. Checklist and Practice Exercise

1. Confirm the project is Spring Boot **3.3.x** with Java 17 and the right Wrapper. If using another Boot version, read the plugin docs for that exact version.
2. Create `LayerDemoApplication`, `VersionController`, and the test as in section 7.
3. Declare `bootJar { layered { enabled = true }; includeTools = true }` when wanting explicit intent; know that 3.3 enables layering by default.
4. Run `clean test bootJar`; verify `BOOT-INF/layers.idx` inside the **actual Boot JAR**.
5. Run `-Djarmode=tools ... list-layers` and then `extract --layers --destination ...`; inspect the directories.
6. Create a multi-stage Dockerfile copying the four groups in default order.
7. Build image `layer-demo:one`, run the container, and verify `GET /version` returns `layer-v1`.
8. Update Controller/test to `layer-v2` without changing dependencies; build image `layer-demo:two` and verify the new response.
9. Inspect Docker build logs and confirm caching has the chance to keep `dependencies`/loader while replacing only application in the final COPY step.
10. Try changing a dependency and note why invalidating earlier cache layers is expected behavior.
11. Compare with a Dockerfile that copies the whole JAR; explain why it cannot see the internal Spring Boot groups.
12. Distinguish Gradle Build Cache, Docker Build Cache, image registry blob reuse, and `layers.idx`.
13. Verify the image against organizational policies: base image digest, runtime user, vulnerability scan, secrets, test report, and image digest.
14. Record artifact source commit, build command, Boot/Gradle/JDK versions, cache screenshots/logs, and smoke test results.
15. Restore the code/tests/dependencies of any real project before finishing.

**You have completed this lesson when:** you can explain why editing just a Controller changes the fat JAR, what `layers.idx` contains, what criteria govern the ordering of the four default layers, **why a Dockerfile must COPY each group separately**, and how to prove Docker reuses the dependencies layer while the new image serves the updated API.

## Official Documentation

- [Spring Boot 3.3 – Gradle Plugin: Packaging Layered Jar or War](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – Maven Plugin: Layered Jar or War](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3 – Dockerfiles with JAR Tools](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/oci-image.html)
- [Spring Boot 3.3 Release Notes – JAR Tools Mode](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Docker Docs – Build Cache Overview](https://docs.docker.com/build/cache/)
- [Docker Docs – Build Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Docker Docs – Optimize Build Cache](https://docs.docker.com/build/cache/optimize/)
- [OCI Image Format Specification](https://github.com/opencontainers/image-spec)
