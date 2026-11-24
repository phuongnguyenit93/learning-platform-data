# Managing Build Cache, Launch Cache, and Cache Cleaning in Cloud Native Buildpacks

## 1. Problem and Objectives

When using **Cloud Native Buildpacks (CNB)** to build an OCI image for Spring Boot, a build may need to download a Java runtime, analyze an executable JAR, prepare buildpack layers, and export the image. **Caching** helps subsequent builds reuse previously generated content, reducing downloads and repeated work, yet it can also complicate debugging if a developer believes fresh data was used while the system actually reused an older layer.

There are three key concepts in Spring Boot `spring-boot:build-image`/`bootBuildImage`:

- **`buildCache`**: stores **buildpack-contributed cached layers** to speed up subsequent image builds; typically holds data needed during build or download steps.
- **`launchCache`**: supports reusing **launch-related layers** during image creation; relates to layers placed into the image to run the application, not business-level caching at HTTP request time.
- **`buildWorkspace`**: the temporary workspace used by the builder/buildpacks during a build. It is **not** an alias for build cache or launch cache and has its own lifecycle.

Spring Boot 3.3 Maven/Gradle plugins create these areas by default as **Docker named volumes**, with names derived from the **output image name**. When the image name/tag changes frequently, default volume names change with it, preventing cache reuse across builds as expected. The plugins let you assign stable cache volume names. <https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html> and <https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html> document the relevant options.

**This assignment targets four practical skills:**

1. Explain build cache, launch cache, and build workspace accurately in the CNB lifecycle.
2. Configure caching explicitly in the Spring Boot Maven Plugin or Gradle `bootBuildImage`.
3. Distinguish a **warm build**, a **cold-ish build with `cleanCache`**, and **controlled manual volume removal**.
4. Design an experiment measuring cache hits/misses and diagnosing cache misses without accidentally deleting someone else's data.

The lesson uses **Spring Boot 3.3.13, Java 17**, a compatible Docker daemon, and Maven/Gradle Wrapper. This is an illustrative version set, not a claim of being the latest release. Buildpacks/builder images can evolve over time; use organization-approved builders and consult documentation matching your exact plugin/runtime versions. **No command in the examples is claimed to have already been executed on the learner's machine.**

## 2. Cloud Native Buildpacks Model: From Application to Image

CNB builds application container images using a **builder image**, **buildpacks**, a **lifecycle**, and a **run image**:

~~~text
Spring Boot project
   |
   | Maven package + spring-boot:build-image
   | or Gradle bootJar + bootBuildImage
   v
Executable JAR/WAR or build input provided by plugin
   |
   v
CNB Builder Image
   +-- buildpack group/order: detect
   +-- lifecycle phases: analyze, detect, restore, build, export
   +-- workspace: temporary files during build
   +-- cache: content to reuse
   |
   +--> buildCache  (buildpack layers restorable for future builds)
   +--> launchCache (launch-related layers eligible for reuse)
   |
   v
OCI application image
   +-- run image/base layers
   +-- buildpack-contributed launch layers
   +-- application layer(s)
   +-- CNB metadata, process/launch configuration
~~~

**Distinguishing builder and run image:**

- The **builder image** contains the environment and buildpacks needed for the **image creation process**, and is usually larger than the run image.
- The **run image** contains the minimal base needed for the application to run. Production containers run on the run image and launch layers; they do not carry the full builder environment.
- The **application image** is the output; it does not “run out of the cache volume” after release. Cache volumes accelerate **subsequent builds**, rather than storing runtime business state of a running container.

**Brief lifecycle overview:**

1. **Analyze** checks previous image/layer info to decide what can be reused.
2. **Detect** identifies buildpacks matching the application according to builder order.
3. **Restore** restores matching cached layers.
4. **Build** executes buildpacks, reusing layers or downloading/compiling anew.
5. **Export** combines launch layers, app contents, and the run image to produce the OCI image, while updating cache/metadata per platform rules.

Exact ordering/components across lifecycle implementations and Platform APIs can evolve; this is an explanatory model, not a requirement to run each phase executable manually when using the Spring Boot plugin.

### 2.1. Where Are “Cache” and “Layer” Defined?

A CNB buildpack can create a layer and mark its attributes per the spec:

~~~toml
[types]
build = true
launch = true
cache = true

[metadata]
example_version = "1.0"
~~~

This is an **illustrative TOML snippet showing how buildpack authors flag a layer**, not a configuration file to paste into a Spring Boot app. Meaning of the flags:

- `build = true`: the layer can be made available to subsequent buildpacks during the build phase.
- `launch = true`: the layer is contributed to the application image for runtime.
- `cache = true`: the layer is permitted in the build cache so it can be restored in later builds.
- `metadata`: data the buildpack can use to compare versions and check whether cached state is still valid.

These three booleans are **not a single combined flag**. For example, `cache=true, build=true, launch=false` can describe a build-time-only toolchain; `launch=true, cache=false` can still be reused from a previously exported image if the platform/buildpack permits. Thus **clearing the build cache does not guarantee every launch layer is rebuilt from scratch**: the previous image/layers and metadata also play a role. See the official CNB caching strategies docs at the end of the lesson.

### 2.2. Other Caches That Must Be Separated

| Component | Purpose | Does Boot `build-image` `cleanCache` clear it? |
| --- | --- | --- |
| CNB `buildCache` | Restores cached layers while building the image. | Affects the platform/plugin-managed cache for that build. |
| CNB `launchCache` | Helps reuse launch layers across exports/previous images. | Check logs for exact cleaning behavior of that build; do not assume all daemon images/volumes are deleted. |
| CNB `buildWorkspace` | Temporary files used during the build. | Not identical to a cache volume; can exist separately. |
| Maven `~/.m2/repository` | Caches Maven artifacts prior to creating the executable JAR. | **Not** deleted by CNB `cleanCache`. |
| Gradle `~/.gradle/caches` | Caches Gradle dependency resolution/tasks before CNB task. | **Not** deleted by CNB `cleanCache`. |
| Docker image layers and image store | Stores pulled/created image/base layers. | Does not disappear completely just from cleaning CNB cache. |
| Docker BuildKit build cache | Cache used when running `docker build`/Dockerfiles. | **Separate** from CNB plugin cache. |
| Redis, HTTP cache, database, local app temp files | Serves **application runtime**. | **Unrelated** to CNB build cache/launch cache. |

**Rule:** when a build is slow, first ask “is it slow in Maven/Gradle dependency resolution, CNB buildpacks, Docker pull, or image push?” before picking which cache to investigate.

## 3. How Do Build Cache and Launch Cache Differ?

### 3.1. Build Cache

**Build cache** retains contents a buildpack wants available again during a future build. Depending on the buildpack, this could be a download cache, build-time tooling, or a runtime artifact marked `cache=true`. A layer is reused only when metadata/input policies deem it valid.

A typical log reading pattern:

~~~text
===> RESTORING
... Restoring data for buildpack layers ...
===> BUILDING
... Reusing cached dependency ...
~~~

This is an **illustrative pattern**, not guaranteed stdout for a specific Paketo/Boot version. A build can still succeed even when restore finds no cached data: the buildpack simply recreates/re-downloads the layer. Caching optimizes performance; it is **not the source of truth for artifact versions**.

**What you cannot infer:** a cache volume existing does not prove a buildpack used it; the cache might hold an older version or the buildpack might choose to invalidate it.

### 3.2. Launch Cache

**Launch cache** pertains to layers used for **image launching** and their reuse during subsequent builds/exports. Some launch layers can be reused from a **previous application image or remote registry** without re-downloading everything to the host, depending on platform and buildpack metadata.

In the Spring Boot plugin, `launchCache` is configured separately from `buildCache`. **Never call it “the cache of the app while the container runs”**:

- It does not store HTTP sessions, query results, Redis values, or database records.
- Clearing `launchCache` does not “reset state” of a running service.
- A built image is an independent artifact; deleting cache does not delete the image.
- Understanding launch layer reuse requires inspecting the **analyze/export phases**, previous image, and registry/local image availability, not just volume size.

### 3.3. Build Workspace

`buildWorkspace` is the area where the builder/buildpacks manipulate files during the build. The Spring Boot plugin typically creates it as a separate Docker named volume (derived from the image name if unconfigured). **A workspace existing does not prove a cache hit**, and deleting it is not equivalent to “cleaning the build cache”.

Avoid mounting sensitive organizational data into the workspace; builders/buildpacks write and temporarily hold content there. If configuring a bind mount, understand permissions and paths on the Docker daemon host, especially when the daemon runs on a different machine from Maven/Gradle.

### 3.4. Four Questions to Choose the Right Action

| Symptom | Question to Ask | First Action |
| --- | --- | --- |
| Second build still downloads the Java runtime. | Do cache volumes share the same name and did the buildpack mark the layer reusable? | Compare image names, volume names, builder/buildpack versions, and logs. |
| Image does not reflect new Java code. | Does the input executable JAR already contain the new bytecode? | Check Maven/Gradle packaging, run the JAR standalone; do not delete volumes first. |
| Upgraded a dependency yet logs still report reusing some layers. | Which layers changed, and which are legitimately allowed to be reused? | Check resolved dependency graph, SBOM, image labels/layers; reuse is not necessarily wrong. |
| Want to measure a cold build without old CNB cached layers. | Can you clean only the cache for a specific image/build? | Use `cleanCache` or `pack --clear-cache` intentionally; capture logs. |

## 4. Where Is Cache Stored? Image Name Drives Cache Identity

Per Spring Boot 3.3 docs, `buildCache`, `launchCache`, and `buildWorkspace` are created by default in the **Docker daemon** as named volumes whose names derive from the **full target image name**.

For example, if a project builds by default:

~~~text
docker.io/library/cnb-cache-demo:0.0.1-SNAPSHOT
~~~

and CI changes the tag per commit:

~~~text
docker.io/library/cnb-cache-demo:commit-a1b2
docker.io/library/cnb-cache-demo:commit-c3d4
~~~

then the default cache identity can change across builds. Consequence: logs fail to find expected cached layers, build times grow, and extra volumes accumulate on the daemon even though app/dependencies barely changed.

**Two ways to keep cache identity stable:**

1. **Use a fixed image name/tag for local builds** (e.g. `cnb-cache-demo:local`), then apply other immutable digest/version tags if needed — taking care not to overwrite production tags.
2. **Configure explicit `buildCache` and `launchCache` names**, independent of the target image tag, so builds of the same project reuse the intended cache.

Only share caches across genuinely compatible builds: same trusted builder/buildpack stack, architecture/platform, and policy. **Do not share a cache volume across unrelated projects or untrusted tenants** just to save disk space.

### 4.1. Do Not Guess Default Docker Volume Names

Default names are an **implementation detail that can vary by plugin/version/image name**. Do not construct a string guessed from the image name and pass it to `docker volume rm`. For accurate lifecycle management, **set explicit volume names in config** and verify them with `docker volume inspect`.

## 5. Runnable Java 17 Spring Boot Example

The exact same Java code works with **Maven or Gradle**; pick one build tool.

Basic structure:

~~~text
cnb-cache-demo/
├── pom.xml                               # if choosing Maven
├── settings.gradle                       # if choosing Gradle
├── build.gradle                          # if choosing Gradle
├── src/main/java/com/example/cnb/CacheDemoApplication.java
├── src/test/java/com/example/cnb/CacheDemoApplicationTest.java
└── (Maven Wrapper or Gradle Wrapper provided by repository)
~~~

### 5.1. Main Application

`src/main/java/com/example/cnb/CacheDemoApplication.java`:

~~~java
package com.example.cnb;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @GetMapping("/cache")
    public String cache() {
        return "cache-" + StringUtils.capitalize("warm");
    }
}
~~~

**Expected:** `GET /cache` returns exact body `cache-Warm`. Java 17 supports all Java syntax here. `StringUtils.capitalize` comes from `commons-lang3`, creating a real code path using an external runtime dependency. This is an **illustrative endpoint**, not a CNB cache management feature; do not confuse the `/cache` URL with a cache-clearing command.

### 5.2. JUnit + MockMvc Test

`src/test/java/com/example/cnb/CacheDemoApplicationTest.java`:

~~~java
package com.example.cnb;

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
class CacheDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void cacheEndpointReturnsExpectedText() throws Exception {
        mvc.perform(get("/cache"))
           .andExpect(status().isOk())
           .andExpect(content().string("cache-Warm"));
    }
}
~~~

The test verifies Java/Spring context/Commons Lang on the **test classpath**, but does not test CNB image caching or the Docker runtime. You must still verify the built image. When modifying code in exercises A/B/C, update assertions accordingly.

## 6. Approach 1: Maven `spring-boot:build-image` and Cache Volumes

### 6.1. Runnable `pom.xml`

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
    <artifactId>cnb-cache-demo</artifactId>
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
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
                    <image>
                        <!-- Stable tag for local experiments -->
                        <name>cnb-cache-demo:local</name>
                        <!-- Dedicated build and launch cache names, easy to manage -->
                        <buildCache>
                            <volume>
                                <name>cnb-demo-build-cache</name>
                            </volume>
                        </buildCache>
                        <launchCache>
                            <volume>
                                <name>cnb-demo-launch-cache</name>
                            </volume>
                        </launchCache>
                        <verboseLogging>true</verboseLogging>
                        <cleanCache>false</cleanCache>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Configuration belongs in **Spring Boot Maven Plugin**, not `maven-jar-plugin` or `maven-dependency-plugin`:

- `image.name` sets a stable image name for local experiments.
- `buildCache.volume.name` specifies the CNB build cache named volume.
- `launchCache.volume.name` specifies the CNB launch cache named volume.
- `verboseLogging` enables detailed logs for QA.
- `cleanCache=false` attempts warm caching by default. When measuring a clean run, use a **command-line override** instead of permanently modifying the POM.
- `buildWorkspace` is left unconfigured in the demo so the plugin chooses one automatically; it is **not manually deleted** in the exercises targeting the two specific caches.

Maven `spring-boot:build-image` **forks the lifecycle to ensure `package` ran**; if binding the goal to the Maven lifecycle, use `build-image-no-fork` per documentation to avoid unintentional duplicate forks. This lesson invokes the CLI goal directly.

### 6.2. Normal Build and Clean-Cache Commands

From root with Maven Wrapper, running Docker daemon, and permission to pull builder/run images:

~~~bash
# Check toolchain, tests, and artifact first
./mvnw -version
docker version
./mvnw clean verify

# Normal CNB build: do not intentionally clear cache
./mvnw spring-boot:build-image

# Same code/image/config, run once more to observe warm cache
./mvnw spring-boot:build-image

# Only when intentionally testing a cache-clean run:
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.cleanCache=true
~~~

`-Dspring-boot.build-image.cleanCache=true` is a documented property in Spring Boot Maven Plugin 3.3. Do not pass this flag on **every** CI command if you want cache benefits.

**Do not confuse `./mvnw clean` with CNB cache cleaning**: Maven `clean` only clears build outputs like `target/`, and does not delete Docker named volumes managed by CNB. Likewise, plugin cache is not the local Maven repository.

### 6.3. Why Not Hardcode Host Docker Volume Paths?

Docker volumes belong to the **Docker daemon**; with Docker Desktop or a remote daemon, the physical path is not necessarily a directory under the user's shell. Use Docker CLI inspect rather than trying to enter `/var/lib/docker/volumes` or running `rm -rf` on the host.

## 7. Approach 2: Gradle `bootBuildImage` and Cache Volumes

If using Gradle, keep the same source/tests and replace the POM with these two files.

`settings.gradle`:

~~~groovy
rootProject.name = 'cnb-cache-demo'
~~~

`build.gradle`:

~~~groovy
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
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    // Keep image name stable to compare builds.
    imageName.set('cnb-cache-demo:local')

    // Cache volumes managed by CNB/Docker daemon.
    buildCache {
        volume {
            name = 'cnb-demo-build-cache'
        }
    }
    launchCache {
        volume {
            name = 'cnb-demo-launch-cache'
        }
    }

    cleanCache.set(false)
    verboseLogging.set(true)
}
~~~

Explanation:

- The Spring Boot Gradle Plugin creates the `bootBuildImage` task when the Java/War plugin is applied and uses Cloud Native Buildpacks.
- `imageName` is the output image name. Real projects may assign version/commit tags while keeping cache volume names stable.
- `buildCache` and `launchCache` are **two separate `CacheSpec` blocks**; `volume.name` is the Docker volume name used to store/pass the respective cache.
- `cleanCache` is a `Property<Boolean>` on the task, so `set(false)` works in Groovy DSL. Do not copy this DSL verbatim into a Maven POM or Kotlin DSL.
- `verboseLogging` aids CNB lifecycle/log analysis and does not change product correctness.

### 7.1. Gradle Commands

~~~bash
./gradlew --version
docker version

# Java compile/test/JAR
./gradlew clean build

# CNB image build, preserving cache
./gradlew bootBuildImage

# Re-run with identical code and config, compare logs
./gradlew bootBuildImage

# Only when wanting to clean cache before a single build:
./gradlew bootBuildImage --cleanCache
~~~

`--cleanCache` is a task option listed in Spring Boot Gradle Plugin 3.3 docs. You can also temporarily set `cleanCache.set(true)` in the build script, yet remember to **restore `false`** after testing so warm caching is not unintentionally disabled.

**`./gradlew clean` does not remove Docker named volumes.** It cleans Gradle project outputs such as `build/`, unlike CNB image build's `cleanCache`. The Gradle build cache (`~/.gradle/caches` or a remote Gradle build cache) is also distinct from the CNB build cache.

### 7.2. Is It Safe for Maven and Gradle to Share Volume Names?

In this **lesson**, the Maven and Gradle configs share the same volume names for easy comparison, yet only **one tool** should run at a time. In an organization, incompatible pipelines must not accidentally share identically named caches. To run Maven and Gradle or two architectures side by side, prefix by tool/project/platform, such as `cnb-maven-demo-build` and `cnb-gradle-demo-build`.

**Rule:** cache identity must be stable enough for reuse yet isolated enough not to mix incompatible buildpacks/tenants/toolchains.

## 8. Inspection Steps Before Cleaning

### 8.1. Checking the Docker Daemon

~~~bash
docker version
docker info
~~~

If the client cannot reach the server, the Spring Boot image build fails before or while creating the builder container. Do not mistake a **daemon unavailable** error for a cache bug. When the Docker context points to a remote daemon, all named volumes live **on that daemon**, not necessarily on the machine running Maven/Gradle.

### 8.2. Checking Named Cache Volumes

The following commands **only read metadata**:

~~~bash
docker volume ls
docker volume inspect cnb-demo-build-cache
docker volume inspect cnb-demo-launch-cache
~~~

If a volume does not yet exist before the first build, `inspect` may return non-zero; that is not automatically an error. After an image build, whether volumes appear depends on platform/version/config and how far the build progressed. Inspect `docker volume ls` and logs to verify.

**Do not assume anything containing `cache` belongs to you:** a Docker daemon can host volumes from many projects. Delete a volume only after verifying its **exact name**, purpose, owner, and impact.

### 8.3. Observing the Built Image

~~~bash
docker image ls
docker image inspect cnb-cache-demo:local
~~~

`docker image inspect` reveals the image ID, labels, digest metadata, and platform; it **does not** prove which cache volumes hit during the lifecycle. Reading **analyze/restore/build/export logs** is required to see which layers were reused or rebuilt by buildpacks.

### 8.4. Verifying Container Behavior

Once the image builds successfully, run:

~~~bash
docker run --rm -p 18085:8080 cnb-cache-demo:local
~~~

In another terminal:

~~~bash
curl -i http://localhost:18085/cache
~~~

**Expected:** HTTP 200, body `cache-Warm`. This is an **image** smoke test, not a cache hit test. If the image runs properly yet the second build did not reuse cache, the issue is **performance/caching**, not necessarily a broken app.

Stop the server via Ctrl+C in the container terminal. In CI, manage background containers by ID, timeout, and cleanup; avoid leaving a foreground server running indefinitely expecting the pipeline to finish on its own.

## 9. A/B/C Experiment: Comparing Warm Cache, Code Changes, and Dependency Changes

To verify cache behavior, change **one variable at a time** and record logs along with timings. Four baseline runs are suggested:

| Run | Input Change | Clean Cache? | Question |
| --- | --- | --- | --- |
| A1 | Baseline source/dependency, fixed image and volume names. | May start with intentional clean. | Which layers take time to build/download? |
| A2 | No code/dependency/builder changes. | No. | Do buildpacks reuse cache or image layers? |
| B | Change only one literal in Java code and test assertion. | No. | Are still-valid buildpack layers reused? |
| C | Revert to code A, change only approved Commons Lang release version. | No. | Which dependency layers are replaced/invalidated, and is runtime still right? |

### 9.1. Run A1: Cache-Clean Baseline

Maven:

~~~bash
./mvnw clean verify
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.cleanCache=true
~~~

Or Gradle:

~~~bash
./gradlew clean build
./gradlew bootBuildImage --cleanCache
~~~

**Do not claim a “100% cold build” from `cleanCache` alone:** the daemon may still retain builder/run images; Maven/Gradle caches remain warm; previous image/registry layers may exist; and buildpacks may apply other reuse mechanisms. Call this a **clean-CNB-cache baseline** and document the environment.

Archive evidence per policy: command, image name, volume names, builder/run image references and digests, JDK, plugin version, selected dependency versions, container logs, and CI timings. If log files are needed, redirect stdout/stderr via your shell; never attach logs from a different build as evidence.

### 9.2. Run A2: Warm Build

Repeat the exact same command **without the clean flag**:

~~~bash
# Maven or Gradle, choose one:
./mvnw spring-boot:build-image
# ./gradlew bootBuildImage
~~~

In the logs, observe:
- Are there **RESTORING** / **Reusing** / **Cached** phases/messages?
- Which buildpacks reuse cached layers and which still re-run?
- Does it pull builder/run images from the registry due to the default pull policy?
- Are the same cache volume names, daemon/context, and image ref used?
- Does runtime still return HTTP 200/`cache-Warm`?

**Do not infer a cache hit purely from faster wall-clock time**: network conditions, Docker image store, Maven local repo, Gradle build cache, and host load also affect duration. Pair timing measurements with log/layer metadata.

### 9.3. Run B: Code-Only Change

In `CacheDemoApplication.java`, change:

~~~java
return "cache-" + StringUtils.capitalize("warm");
~~~

to:

~~~java
return "code2-" + StringUtils.capitalize("warm");
~~~

Update the expected test string to `code2-Warm` so tests stay valid. Do not modify POM/Gradle dependencies, cache names, builder/run image, or Docker context. Build and run the image normally:

~~~bash
# Maven:
./mvnw clean verify
./mvnw spring-boot:build-image

# Or Gradle:
# ./gradlew clean build
# ./gradlew bootBuildImage
~~~

Run a container from the new image; expect body `code2-Warm`. Logs may show many dependency/buildpack layers being reused even though the application layer changed. **Do not demand identical log phrasing across every buildpack version**; compare actual data.

### 9.4. Run C: Dependency-Only Change

**Restore code and tests to A** (`cache-Warm`) first. Upgrade **only** the Commons Lang version from `3.14.0` to `3.15.0` or an organization-approved, resolvable release version:

Maven POM fragment:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.15.0</version>
</dependency>
~~~

Gradle fragment:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.15.0'
~~~

Verify the **selected version**, not merely the declaration:

~~~bash
# Maven
./mvnw dependency:tree

# Gradle (choose if using Gradle)
./gradlew dependencyInsight --configuration runtimeClasspath \
  --dependency commons-lang3
~~~

Build the image normally, compare logs with A2, run the image, and verify `cache-Warm`. Some buildpack layers may invalidate while others reuse; do not expect an identical pattern across all builders. Inspect runtime archive contents / SBOM and image metadata when needed to explain changes.

### 9.5. Sample Results Table (Fill with Real Measurements)

| Run | Input commit/dependency | Clean cache | Volume names | Layers reused/rebuilt (log excerpt) | Actual duration | HTTP smoke |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Baseline | Yes | Named build/launch | Record evidence | Record measurement | 200 / `cache-Warm` |
| A2 | Same as A1 | No | Same as A1 | Record evidence | Record measurement | 200 / `cache-Warm` |
| B | Code-only | No | Same as A1 | Record evidence | Record measurement | 200 / `code2-Warm` |
| C | Dependency-only | No | Same as A1 | Record evidence | Record measurement | 200 / `cache-Warm` |

Do not fill in “estimated” seconds or cache hit ratios without actually running them. Before comparing durations, make sure toolchain, daemon, network, and source inputs match.

## 10. Cleaning Cache Within the Right Scope: Four Ways

### 10.1. Preferred Way for Spring Boot Maven

Use **intentionally for a single run only**:

~~~bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.cleanCache=true
~~~

The plugin requests clearing caches **associated with the current image build** before constructing the image. This is **not** a command to wipe all Docker volumes/Gradle caches/Maven repositories on the machine. Afterward, return to the normal command so warm caching can resume.

### 10.2. Preferred Way for Spring Boot Gradle

~~~bash
./gradlew bootBuildImage --cleanCache
~~~

Similarly, this is a **`BootBuildImage` task option**, not `./gradlew clean` and not `docker system prune`. Check logs to confirm cache handling succeeded and the resulting image runs properly.

### 10.3. With `pack` CLI — `--clear-cache`

If invoking **`pack` CLI directly**, this is a separate workflow from the Spring Boot Maven/Gradle Plugin. Check the installed version:

~~~bash
pack version
pack build --help
pack builder suggest
~~~

Example using a builder supported by the corresponding version's docs (replace builder when policy requires):

~~~bash
# From project root (with Docker daemon and compatible builder)
pack build cnb-cache-demo:pack \
  --path . \
  --builder paketobuildpacks/builder-jammy-base:latest

# Intentionally clear cache tied to this image before this pack build:
pack build cnb-cache-demo:pack \
  --path . \
  --builder paketobuildpacks/builder-jammy-base:latest \
  --clear-cache
~~~

`--clear-cache` is an official `pack build` option clearing the **cache tied to that image/build** before building. Do **not** assume `pack build` is completely identical to `spring-boot:build-image`: inputs, detection, buildpacks, cache naming, and build flags can differ. Do not compare wall-clock time directly between `pack` and the Boot plugin and blame the difference solely on cache.

The builder in the example is an illustrative reference with a `latest` tag; for reproducibility in real projects, pin an approved builder version/digest. If that builder image is no longer present in the repository, switch to a compatible organization-approved builder; never disable verification/TLS to pull at any cost.

### 10.4. Manual Volume Removal — Only After Verifying Ownership

**Use only when cleaning a local test daemon after verifying the exact two Docker volumes managed by this demo.** Never run this automatically on a shared Docker host or multi-team CI daemon.

Step 1 — read metadata:

~~~bash
docker volume ls
docker volume inspect cnb-demo-build-cache
docker volume inspect cnb-demo-launch-cache
~~~

Step 2 — confirm:

- Both names **match exactly** the POM/Gradle configuration of the **right project**.
- No other job/build/container is currently using them.
- They hold no non-reproducible data; CI/ops approved deletion if on a shared environment.
- `buildWorkspace` is not confused with a cache volume.
- You are connected to the **exact Docker context/daemon** where the project built.

Step 3 — destructive cache removal action (only after confirmation):

~~~bash
docker volume rm cnb-demo-build-cache cnb-demo-launch-cache
~~~

This is a **destructive command** on the two named Docker volumes. If a volume is attached to a container, Docker may refuse. **Do not add `-f` or kill containers indiscriminately to force deletion**, especially on a shared daemon.

Step 4 — intentional verification:

~~~bash
docker volume ls
./mvnw spring-boot:build-image
# Or if using Gradle: ./gradlew bootBuildImage
~~~

After building, volumes may be recreated; that is normal. Do not claim “volumes will never reappear” while the platform still caches for future builds.

### 10.5. Strictly Distinguish from Broader Commands

| Command/Action | Impact | Should it be used just to clean this lesson's CNB cache? |
| --- | --- | --- |
| Maven `clean` | Deletes Maven build outputs like `target`. | Does not replace CNB cache cleaning. |
| Gradle `clean` | Deletes build outputs like `build`. | Does not replace CNB cache cleaning. |
| `docker image rm <image>` | Deletes local image tag/image when unused. | Does not guarantee deleting cache volumes. |
| `docker builder prune` | Clears **Docker BuildKit build cache**, not these exact two CNB named volumes. | **No**, unless specifically handling BuildKit. |
| `docker volume prune` | May delete **many unreferenced volumes** belonging to other projects. | **No** on shared hosts. |
| `docker system prune --volumes` | Broadly impacts unused objects/caches/volumes. | **No** for a single cache test. |
| `rm -rf ~/.m2`/`~/.gradle/caches` | Deletes dependency/build-tool caches, not CNB cache. | No; high blast radius and forces heavy re-downloads. |

**Safety principle:** prefer `cleanCache`/`--clear-cache` scoped to **one image build**, or remove **the exact owned named volumes** when truly needed. Never run global prune commands as a “quick fix” for a single cache miss symptom.

## 11. Configuring Stable Caches When CI Image Tags Change

A pipeline often produces images tagged per commit:

~~~text
cnb-cache-demo:abc123
cnb-cache-demo:def456
cnb-cache-demo:ghi789
~~~

If the plugin uses default volume names **derived from the full image name**, every tag can spawn separate volumes, reducing cache reuse across commits. The fix is to **tie cache volume names to the project/toolchain**, not to fluctuating tags.

### 11.1. Maven

Snippet inside `spring-boot-maven-plugin`:

~~~xml
<image>
    <!-- Image name/tag can vary per pipeline -->
    <name>registry.example.invalid/team/cnb-cache-demo:commit-id</name>
    <!-- Keep cache volumes stable per project -->
    <buildCache>
        <volume><name>team-cnb-demo-build</name></volume>
    </buildCache>
    <launchCache>
        <volume><name>team-cnb-demo-launch</name></volume>
    </launchCache>
</image>
~~~

This is a **configuration fragment**, not a real registry URL and not a standalone POM. `registry.example.invalid` is an illustrative marker, do not push. In real CI, assign the image name from your release/versioning system using an approved registry and appropriate credentials/permissions. If multiple CI runners use separate daemons, **using the same volume name does not magically share cache across machines**.

### 11.2. Gradle

Groovy DSL fragment:

~~~groovy
tasks.named('bootBuildImage') {
    // Replace imageName with real CI version/commit.
    imageName.set('cnb-cache-demo:ci-demo')

    buildCache {
        volume { name = 'team-cnb-demo-build' }
    }
    launchCache {
        volume { name = 'team-cnb-demo-launch' }
    }
}
~~~

Likewise, volume names stay stable as image tags vary. Avoid **race conditions** when two jobs run concurrently on the same daemon sharing a cache: namespace caches by pipeline/platform or synchronize per policy. Cache is not guaranteed to be safe mutable shared state for arbitrary numbers of concurrent runners.

### 11.3. When CI Uses Ephemeral Runners

If each build spawns a fresh Docker daemon/VM and volumes do not survive across jobs, **local named-volume cache will not persist** even with identical names. Options:

- Use persistent runners/daemons if policy permits.
- Consider remote image/cache strategies of the CNB platform, such as `pack --cache-image` or registry-based caching per CLI support and publish rights.
- Check **registry reachability/authentication** and cache tenancy/security.
- Do not claim that merely adding `buildCache.volume.name` suffices for completely stateless CI runners.

`pack` also supports cache volume/bind/registry image options depending on version and flags; check `pack build --help` for your binary. Remote caching requires authentication, registry policies, and publish permissions; it is not an automatic feature enabled by the Maven/Gradle snippets in this lesson.

## 12. Why Does Cache Still Miss Even When Volumes Exist?

### 12.1. Buildpacks Decide Validity Using Metadata

An old cache entry is not guaranteed to be reused forever. A buildpack may compare Java version, buildpack version, dependency checksums, build input metadata, stack/run image compatibility, or custom criteria. If metadata mismatches, it rebuilds the layer. That is **correct cache invalidation**, not a bug to force around.

### 12.2. Common Causes

| Symptom | Likely Cause | Check / Resolution |
| --- | --- | --- |
| Second build re-downloads many dependencies. | Image/cache volume name changed, different daemon, cache cleaned, or builder version changed. | Print image name and exact volume names, Docker context, restore/build logs. |
| Docker volume exists yet no `Reusing` log appears. | Buildpack invalidated cache, layer not marked cacheable, or new metadata. | Check builder/buildpack versions, runtime deps, buildpack logs. |
| Changing tag per commit makes builds run like cold. | Default cache name derives from tagged image name. | Set stable `buildCache`/`launchCache` names if builds are compatible. |
| Build stays fast even after cleaning cache. | Maven/Gradle caches, Docker builder/run images, and previous image layers remain. | Separate cache sources; do not conclude `cleanCache` is broken. |
| `java -jar`/Docker app still returns old code output. | Package input not rebuilt, old image tag, old container, or different resource/config. | Check executable JAR, image ID, container ID, and code path; do not delete volumes first. |
| Upgraded Commons Lang yet buildpack reuses JRE layer. | JRE layer does not directly depend on Commons Lang. | Likely valid cache reuse; inspect updated app/dependency layers. |
| `docker volume inspect` reports not found. | Not yet created, wrong name, wrong daemon context, or build failed early. | Check config, Docker context/logs; do not guess from image name. |
| `bootBuildImage` task missing. | Missing Java/War plugin or Spring Boot plugin. | Check `plugins` and `./gradlew tasks --all`. |
| Maven `build-image` cannot find Docker daemon. | Docker stopped, missing permissions, or context/TLS config wrong. | `docker version`/`docker context ls`; inspect plugin Docker connection. |
| Build fails downloading builder/run image. | Network/registry/TLS/auth/pull policy issue. | Fix access to right source; do not wipe cache or disable TLS. |
| Cache too large, disk full. | Many image tags spawning volumes, stale caches, builder images, and image store. | Bounded inventory, delete owned volumes only, enforce retention. |
| Parallel CI jobs writing same volume. | Cache namespace collision across jobs, compatibility unguaranteed. | Separate namespaces by tool/platform/runner or synchronize. |
| Changing Java version invalidates cache. | JDK/runtime compatibility/metadata changed. | Likely expected; confirm builder/buildpack pins and Java toolchain. |
| `cleanCache=true` left permanently on so every run is cold-ish. | Setting stayed committed in POM/Gradle. | Enable only for a single clean test run, then revert to `false`. |
| Ran `docker builder prune` yet CNB still reuses layers. | BuildKit cache differs from CNB volumes/previous image layers. | Do not use BuildKit prune to manage CNB volumes. |
| `launchCache` mistaken for application Redis cache. | Confusing build-time container artifact cache with runtime business state. | Review lifecycle/docs; inspect image instead of Redis endpoints. |
| New image fails at runtime despite build reusing cache. | New app/dependency/config incompatible; cache is not a correctness test. | Smoke test image, check SBOM, dependency graph, and logs. |

### 12.3. Layered Diagnostic Framework

1. **Build tool:** did Maven/Gradle compile/test/package the right code?
2. **Inputs:** are source hash, dependency versions, application archive, and selected builder image right?
3. **Docker:** which daemon/context is in use; are network/registry healthy?
4. **Cache configuration:** do build/launch cache and workspace names match config?
5. **CNB lifecycle logs:** which layers did analyze/restore/build/export reuse or invalidate?
6. **Image result:** were image tag, ID, labels, runtime stack, and process created properly?
7. **Runtime:** does the container run the new code and return the expected HTTP response?
8. **Security:** are provenance, SBOM/CVEs/registry policies satisfied with zero secrets in layers/cache?

Only after pinpointing **which layer failed** should you decide to use `cleanCache`, change configuration, or fix code/dependencies.

## 13. Distinguishing CNB Cache from Spring Boot Layered JARs

A Spring Boot JAR may include `BOOT-INF/layers.idx`, typically grouped into:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

This is **how files are grouped inside the executable archive**, not the Docker cache volumes named `buildCache` and `launchCache` themselves.

- `BOOT-INF/layers.idx` tells which Java classes/dependency JARs belong to each logical archive layer.
- CNB buildpacks/lifecycle decide how to build/reuse **OCI image** layers based on application content and buildpack metadata.
- `buildCache`/`launchCache` are cache storage resources supplied to the image build lifecycle.
- Docker BuildKit cache is a separate mechanism used with `docker build`/Dockerfiles.

Thus, editing `BOOT-INF/classes` may change the application layer while the buildpack's Java runtime/JRE layer is still reused. Changing a dependency can affect another OCI layer depending on the buildpack strategy. **Do not force a 1:1 mapping between names in `layers.idx` and Docker volume contents.**

If you genuinely need to know how effective caching is, **measure build logs and image layers** from the exact builder with identical inputs, rather than just grepping `layers.idx`.

## 14. “Clean Cache” Behavior Does Not Equal Reproducible Builds

A fresh cache run can produce the same image if inputs are controlled; conversely, a warm cache run still builds a new image when source/dependencies change. Reproducibility requires:

- Pinning Java toolchain, Gradle/Maven Wrapper, plugins, and builder/run image versions/digests per policy.
- Locking dependency versions, avoiding dynamic/changing dependencies in release builds.
- Managing dependency verification/provenance, trusted registry mirrors, and buildpack selection.
- Keeping generated metadata free of unnecessary timestamps/random IDs; pay attention to image `createdDate`.
- Never relying on `latest` image tags for bit-for-bit reproducibility without knowing actual digests.
- Verifying binary behavior and image content/SBOM; fast builds do not equal correct builds.
- Using clean cache **only when diagnosing**, never making it a default CI step that wastes network and storage.

Spring Boot 3.3 provides `createdDate` with a fixed default to aid reproducibility; setting `now` changes image metadata on every build, which can change the digest even when application code stays the same. That is an **image metadata** difference, not proof of broken caching.

### 14.1. Which Cache Configuration Should Production Use?

**Local dev:** volumes with stable project/toolchain names, relaxed retention, occasional intentional clean when debugging.

**CI persistent runner:** isolate caches by project/platform and permissions, clear retention, monitor disk usage, prevent concurrent jobs from sharing incompatible caches.

**CI ephemeral runner:** local Docker volumes do not survive; evaluate registry-backed caching or persistent cache services supported by platform/tooling, verifying auth, latency, and trust.

**Release:** never skip tests, artifact integrity/SBOM, signature/CVE scans, or runtime smoke tests because of cache. Caching is a **performance optimization** and must never alter product acceptance rules.

## 15. Final Practice Lab and Verification Criteria

### Exercise A — First Image Build and Clarifying the Three Storage Areas

1. Set up the Java 17 project per section 5 and POM or Gradle file per section 6/7.
2. Run the test suite and inspect the report; verify `cacheEndpointReturnsExpectedText` actually ran/passed.
3. Run the first image build with your chosen plugin to create `cnb-cache-demo:local`.
4. Read lifecycle logs, especially `RESTORING`/`BUILDING`/`EXPORTING`, noting which layers were created.
5. `docker volume inspect` the two configured cache volume names.
6. Explain how `buildWorkspace` differs from build/launch caches.
7. Run the container; `GET /cache` returns HTTP 200/`cache-Warm`.

### Exercise B — Warm Build and Comparison

1. Make zero changes to source/dependencies/builder/image name/cache volume names.
2. Rebuild **without `cleanCache`**.
3. Record logs showing which layers were reused and which were rebuilt.
4. Compare real measured durations (same daemon/network if possible).
5. Explain other speedup sources such as the Maven repository, Gradle cache, and Docker image store.
6. Never claim “saved X%” without measuring.

### Exercise C — Intentional Cache Clean

1. Use Maven `-Dspring-boot.build-image.cleanCache=true` or Gradle `--cleanCache` for exactly one build.
2. Read lifecycle logs and compare with the warm build.
3. Verify the image still runs and responds accurately.
4. Return to the normal command and show warm caching can be reused afterward.
5. Explain why `mvn clean`/`gradlew clean` does not affect those same caches.

### Exercise D — Code and Dependency Changes

1. Edit only the method body to return `code2-Warm`, update the test, and build without cleaning cache.
2. Record which layers were reused/invalidated and run HTTP smoke check after building.
3. Revert code to baseline, upgrade Commons Lang to an approved release version.
4. Compare resolved versions, build logs, image behavior, and SBOM if available.
5. Explain why a dependency update does not force every buildpack/JRE layer to rebuild.

### Exercise E — Responsible Cache Volume Management

1. Identify the Docker daemon/context and verify ownership of the two explicit volume names.
2. Run `docker volume inspect` to verify before considering removal.
3. On a **dedicated local test daemon**, with permission and no active job using them, run `docker volume rm` on only those two names.
4. Rebuild and confirm the volumes/layers can be recreated cleanly.
5. Explain why `docker volume prune` or `docker system prune --volumes` must not be used on a shared host.

### Completion Checklist

- [ ] Know that build cache restores buildpack cached layers, and launch cache supports reusing launch-related layers.
- [ ] Distinguish CNB caches from `buildWorkspace`, Maven/Gradle caches, Docker BuildKit, and Redis/runtime caches.
- [ ] Explain lifecycle `analyze`/`detect`/`restore`/`build`/`export` well enough to read logs.
- [ ] Understand buildpack layer flags `build`, `launch`, `cache`, and metadata reuse.
- [ ] Know that default image name/tag drives default Docker cache volume names.
- [ ] Know how to configure `buildCache.volume.name`/`launchCache.volume.name` in Spring Boot Maven Plugin.
- [ ] Know how to configure `buildCache { volume {...} }`/`launchCache {...}` in Gradle `bootBuildImage`.
- [ ] Know `spring-boot.build-image.cleanCache` and Gradle task option `--cleanCache`.
- [ ] Know that `pack build --clear-cache` is a separate CLI workflow and differs from Docker prune.
- [ ] Know to run `docker volume ls/inspect` before any cleanup operation.
- [ ] Never delete Docker volumes belonging to other jobs/teams or run global prune for a single app's cache issue.
- [ ] Know that local Docker volumes do not automatically share across CI runners/daemons.
- [ ] Have JUnit/MockMvc test reports and Docker image HTTP smoke tests verifying the binary.
- [ ] Have logs/layer evidence comparing cold-ish, warm, code-only, and dependency-only runs.
- [ ] Never use warm/cold build durations as the sole proof of a cache hit.
- [ ] Understand why custom builders/plugins/toolchains and previous images can cause cache invalidation.
- [ ] Know that caching does not prove vulnerabilities were patched or that builds are bit-for-bit reproducible.

**Passing criteria:** submit Maven or Gradle config using two explicit named cache volumes; logs for at least one cached image build, one clean-cache run, and one warm build; confirmation of volume names via Docker; explanation of one code-change and one dependency-change run; and verification that the container runtime `/cache` returns the expected response. If no Docker daemon is available, explicitly mark Docker/CNB steps as **not executed** rather than guessing cache hits/passes.

## Official References

- [Spring Boot 3.3.13 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3.13 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Spring Boot 3.3.13 — BootBuildImage API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootBuildImage.html)
- [CNB — Caching Strategies](https://buildpacks.io/docs/for-buildpack-authors/concepts/caching-strategies/)
- [CNB — Create Dependency Layers](https://buildpacks.io/docs/for-buildpack-authors/how-to/write-buildpacks/create-layer/)
- [CNB — Lifecycle Tutorial](https://buildpacks.io/docs/for-platform-operators/tutorials/lifecycle/)
- [CNB — pack build CLI](https://buildpacks.io/docs/tools/pack/cli/pack_build/)
- [Docker — Volumes](https://docs.docker.com/engine/storage/volumes/)
- [Docker — Docker Build Cache](https://docs.docker.com/build/cache/)

**Remember:** `buildCache` and `launchCache` serve the **OCI image creation process**, not the application's business data cache. To optimize, configure properly scoped stable cache names and read CNB lifecycle logs. To clean, use **Spring Boot `cleanCache` / pack `--clear-cache`** or remove **only the verified Docker volumes**—never use system-wide prune commands to troubleshoot a single project.