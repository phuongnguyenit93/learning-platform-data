# Modifying Code or Dependencies to Observe Caching and Spring Boot Image Layers

## 1. Objective and Experiment Rules

This lab uses a small Spring Boot application to observe seven steps: initial build, rebuild with unchanged inputs, editing one Java line, upgrading a dependency version, packaging the JAR into a multi-layer Docker image, observing the BuildKit cache, and comparing with Cloud Native Buildpacks (CNB).

Reference environment: **Java 17, Spring Boot 3.3.13, Maven Wrapper or Gradle Wrapper, Docker BuildKit**. Spring Boot 3.3.13 requires Java 17 or later and supports Maven 3.6.3+ and Gradle 7.5+ on the 7.x/8.x lines. Use the wrapper and toolchain pinned by the project. Commands are hands-on instructions, not pre-run build results.

Change only one factor per run. Keep the commit, JDK, wrapper, build command, Dockerfile, and base image unchanged when comparing. Record the tasks/goals that actually executed, resolved dependency versions, JAR SHA-256, Docker cache lines, image layer diff IDs, and endpoint responses.

## 2. Cache and Artifact Model

§§§text
Java source / pom.xml / build.gradle
                 |
                 v
        Maven / Gradle build
          |              |
          v              v
  Dependency cache   Task / incremental state
          |              |
          +-------+------+
                  |
                  v
        Spring Boot executable JAR
                  |
                  v
       Docker BuildKit / CNB builder
          |              |
          v              v
     Build cache     Image layers
          |              |
          +-------+------+
                  |
                  v
          OCI image + container
                  |
                  v
          Runtime response
§§§

Distinguish three outcomes:

| Observation | Meaning |
| --- | --- |
| **Task/cache hit** | The build tool skips part of the work because inputs/outputs match saved state or cache keys. |
| **Image layer reuse** | The builder reuses a layer because its instruction and relevant inputs did not change. |
| **Artifact/image changed** | JAR bytes or image contents differ from before; this does not by itself prove caching malfunctioned. |

A build can report tasks as UP-TO-DATE while the image still changes due to base image, metadata, or timestamps. Docker can cache a RUN instruction even when a remote package repository has a newer version, because RUN caching does not check external repository state. Record each layer separately.

## 3. Creating the Sample Application

Project structure:

§§§text
cache-lab/
├── pom.xml
├── build.gradle
├── settings.gradle
├── mvnw
├── .mvn/wrapper/
└── src/main/java/com/example/cachelab/
    ├── CacheLabApplication.java
    └── GreetingController.java
§§§

Use either Maven or Gradle for a practice run; there is no need to maintain both build tools in the same pipeline.

### 3.1. Main class

File ¤src/main/java/com/example/cachelab/CacheLabApplication.java:

§§§java
package com.example.cachelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheLabApplication.class, args);
    }
}
§§§

### 3.2. Initial controller

File ¤src/main/java/com/example/cachelab/GreetingController.java:

§§§java
package com.example.cachelab;

import java.util.Map;
import org.apache.commons.lang3.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/greeting")
    public Map<String, String> greeting(
            @RequestParam(defaultValue = "java") String name) {
        return Map.of("message", "Build A: " + StringUtils.capitalize(name));
    }
}
§§§

The controller uses StringUtils.capitalize from Apache Commons Lang so the dependency appears in the runtime archive. The /greeting endpoint returns JSON with a message field.

### 3.3. Maven POM

File ¤pom.xml:

§§§xml
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
    <artifactId>cache-lab</artifactId>
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
        <finalName>cache-lab</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
§§§

finalName pins the executable archive to target/cache-lab.jar. If your project has a custom parent POM or plugin configuration, merge the necessary parts rather than replacing the entire configuration.

### 3.4. Gradle alternative

File ¤build.gradle Groovy DSL:

§§§groovy
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

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.commons:commons-lang3:3.14.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'cache-lab.jar'
}
§§§

File ¤settings.gradle:

§§§groovy
rootProject.name = 'cache-lab'
§§§

Record the output of ¤./gradlew --version before starting; do not upgrade Gradle between measurement runs.

## 4. Baseline: Initial Build and Rebuild

Record source and toolchain:

§§§bash
git rev-parse HEAD
git status --short
java -version
./mvnw -version
# Or:
./gradlew --version
§§§

If the project does not yet have a Git commit, record the source snapshot per team workflow; pushing is not required.

### 4.1. Maven

Initial build:

§§§bash
./mvnw --batch-mode clean package
test -s target/cache-lab.jar
jar tf target/cache-lab.jar
sha256sum target/cache-lab.jar
§§§

In the JAR, look for:

§§§text
BOOT-INF/classes/com/example/cachelab/CacheLabApplication.class
BOOT-INF/classes/com/example/cachelab/GreetingController.class
BOOT-INF/lib/commons-lang3-3.14.0.jar
BOOT-INF/lib/spring-boot-*.jar
§§§

Keep source/POM unchanged and rebuild:

§§§bash
./mvnw --batch-mode package
sha256sum target/cache-lab.jar
§§§

Record the plugins/goals shown in the log, whether the compiler compiled sources or skipped them, whether the JAR was rewritten, and whether the SHA-256 matches the initial build. Maven does not display task outcomes like UP-TO-DATE/FROM-CACHE as Gradle does; compiler/plugins have their own incremental behavior. Do not infer from a fast build that Maven used a Gradle-style task-output cache.

### 4.2. Gradle

Initial build:

§§§bash
./gradlew clean bootJar --info
test -s build/libs/cache-lab.jar
jar tf build/libs/cache-lab.jar
sha256sum build/libs/cache-lab.jar
§§§

Rebuild without clean:

§§§bash
./gradlew bootJar --info
§§§

Read task outcomes:

- UP-TO-DATE: inputs/outputs are unchanged in the workspace.
- FROM-CACHE: output was restored from the local/remote build cache.
- NO-SOURCE: task has no source inputs to process.
- SKIPPED: task was skipped due to conditions/command flags.
- No label: task executed normally.

To observe FROM-CACHE, run twice:

§§§bash
./gradlew clean bootJar --build-cache --info
./gradlew clean bootJar --build-cache --info
§§§

If a cache entry exists and the task is cacheable, some tasks may show FROM-CACHE. If you run bootJar a second time without clean, tasks will typically show UP-TO-DATE instead of FROM-CACHE because outputs still exist in the workspace. Not every task is cacheable.

## 5. Experiment A: Changing Only One Line of Java

Goal: observe how a source change affects compilation/packaging and the image application layer while dependencies remain unchanged.

In GreetingController.java, change:

§§§java
return Map.of("message", "Build A: " + StringUtils.capitalize(name));
§§§

to:

§§§java
return Map.of("message", "Build B: " + StringUtils.capitalize(name));
§§§

Do not edit POM/build.gradle and do not change dependency versions.

Rebuild:

Maven:

§§§bash
./mvnw --batch-mode package
sha256sum target/cache-lab.jar
§§§

Gradle:

§§§bash
./gradlew bootJar --info
sha256sum build/libs/cache-lab.jar
§§§

Observations:

- GreetingController.java changed, so its corresponding class must be recompiled.
- Dependencies did not change, so no new versions need resolution.
- The executable JAR typically has a different SHA-256 because class bytes changed.
- Unaffected classes/dependencies may be retained; exact incremental granularity depends on the compiler/build tool.

Run the new JAR:

§§§bash
java -jar target/cache-lab.jar
§§§

In another terminal:

§§§bash
curl "http://localhost:8080/greeting?name=java"
§§§

Expected response:

§§§json
{"message":"Build B: Java"}
§§§

If you still see Build A, check whether the running process was started from the new JAR. A running Java process does not automatically reload a JAR just because the file on disk was rebuilt. Stop the old process and start a new one.

## 6. Experiment B: Changing Only the Dependency Version

Goal: observe how dependency resolution, the runtime classpath, and the dependencies layer change while Java source stays identical.

### 6.1. Upgrading Commons Lang

In the Maven POM, change:

§§§xml
<version>3.14.0</version>
§§§

to:

§§§xml
<version>3.15.0</version>
§§§

In Gradle, change:

§§§groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
§§§

to:

§§§groovy
implementation 'org.apache.commons:commons-lang3:3.15.0'
§§§

Do not edit GreetingController.java in this experiment.

### 6.2. Verifying the dependency actually resolved

Maven:

§§§bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
./mvnw --batch-mode package
jar tf target/cache-lab.jar | grep commons-lang3
sha256sum target/cache-lab.jar
§§§

Gradle:

§§§bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew bootJar --info
jar tf build/libs/cache-lab.jar | grep commons-lang3
sha256sum build/libs/cache-lab.jar
§§§

The output must confirm that the runtime archive contains commons-lang3-3.15.0.jar. Do not rely only on the value written in POM/build.gradle: dependency management, constraints, resolution rules, or lockfiles can cause the final version to differ from the declaration.

StringUtils.capitalize keeps the same usage. Upgrading the dependency is meant to observe the classpath, archive, and image layers; do not claim the new version changes the response.

### 6.3. Distinguishing dependency cache from task cache

- The Maven local repository or Gradle dependency cache stores downloaded artifacts and resolution metadata.
- Gradle FROM-CACHE refers to task outputs restored from the build cache.
- Docker cache mounts `/root/.m2` or Gradle User Home can retain downloaded dependencies across container builds.
- Image layers hold the libraries packaged into the final product.

A new dependency version may require downloading a new file while still reusing other dependencies already in the local repository. There is no need to delete all of ~/.m2 or ~/.gradle just to test changing one version.

## 7. Experiment C: Observing the Gradle Task Graph and Build Cache

Perform this section only if the project uses Gradle.

View the task graph:

§§§bash
./gradlew bootJar --dry-run
./gradlew tasks --all
./gradlew help --task bootJar
§§§

--dry-run shows scheduled tasks without running actions. Use it to confirm bootJar depends on the required compile/resources tasks.

Run twice consecutively:

§§§bash
./gradlew bootJar --info
./gradlew bootJar --info
§§§

The second run will typically show many UP-TO-DATE tasks if inputs/outputs are unchanged. Edit GreetingController.java and run again; look for compileJava and downstream tasks re-executing.

Compare build cache behavior:

§§§bash
./gradlew clean bootJar --build-cache --info
./gradlew clean bootJar --build-cache --info
./gradlew clean bootJar --no-build-cache --info
§§§

--no-build-cache disables fetching task outputs from the Gradle build cache for that invocation. It does not disable the dependency cache and does not clear Docker caches.

| Observation | Appropriate conclusion |
| --- | --- |
| compileJava UP-TO-DATE when source unchanged | Incremental check saw unchanged inputs/outputs. |
| compileJava executes after editing Java | Source input changed and the task needed to run. |
| Task FROM-CACHE after clean | Output restored from build cache, if the task supports caching. |
| Task SKIPPED | Check onlyIf, enabled, -x, or task conditions. |
| Dependency insight shows new version | Dependency resolution selected the new version. |
| JAR still contains old version | Check module/artifact path, lockfile, and bootJar; do not assume cache is the cause yet. |

Do not use --rerun-tasks as a permanent workaround for tasks missing declared inputs. If a custom task reads a file/property without declaring it as an input, fix the task model so Gradle computes state accurately.

## 8. Experiment D: Observing Docker Layers with a Spring Boot Layered JAR

Spring Boot can split an executable JAR into layers with different frequencies of change. A common default layout includes:

1. dependencies: release dependencies that change infrequently.
2. spring-boot-loader: Spring Boot's loader.
3. snapshot-dependencies: SNAPSHOT dependencies that may change frequently.
4. application: application classes and resources.

Inspect the actual archive's layer index rather than assuming every project has the exact same layout.

### 8.1. Dockerfile using Spring Boot tools jarmode

After building the JAR into target/cache-lab.jar (or build/libs/cache-lab.jar if using Gradle), create Dockerfile:

§§§dockerfile
FROM eclipse-temurin:17-jre AS extract
WORKDIR /layers

COPY target/cache-lab.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extract /layers/extracted/dependencies/ ./
COPY --from=extract /layers/extracted/spring-boot-loader/ ./
COPY --from=extract /layers/extracted/snapshot-dependencies/ ./
COPY --from=extract /layers/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
§§§

If using Gradle, change the source path in the first COPY line to build/libs/cache-lab.jar. The archive must include the layer index and Spring Boot tools jarmode. Do not use tools extraction with a fully executable archive containing an embedded launch script; build an archive suited for container layering.

View layer names:

§§§bash
java -Djarmode=tools -jar target/cache-lab.jar list-layers
§§§

If this command is unavailable in the archive, check the Spring Boot version, plugin packaging, and layer configuration. Do not bypass this error by accidentally copying a plain JAR.

### 8.2. Building the baseline image

§§§bash
docker buildx build --load --progress=plain -t cache-lab:code-a .
docker buildx build --load --progress=plain -t cache-lab:code-a-repeat .
§§§

Record cache lines and executed instructions. A different tag does not necessarily cause a cache miss; Dockerfile caching depends on instructions and inputs, not tag names alone.

### 8.3. Editing only Java code and rebuilding the image

After Experiment A, the JAR now returns Build B. Build:

§§§bash
docker buildx build --load --progress=plain -t cache-lab:code-b .
§§§

Observations:

- COPY JAR into the extract stage receives new input.
- The java -Djarmode=tools ... extract command re-runs because the input JAR changed.
- COPY for the dependencies layer can still be cached if dependency contents did not change.
- COPY spring-boot-loader can be cached if the loader did not change.
- COPY snapshot-dependencies can be cached if no snapshot dependencies changed.
- COPY application must update because application code/resources changed.

This is the expected outcome of a layered JAR when only application code is modified. Builder logs are the definitive evidence; timestamps, metadata, or custom layer configurations can still affect cache keys.

### 8.4. Changing only the dependency version and rebuilding the image

Upgrade the dependency from 3.14.0 to 3.15.0 as in Experiment B, build a new JAR, and run:

§§§bash
docker buildx build --load --progress=plain -t cache-lab:dependency-b .
§§§

Expectation: the extract stage re-runs; the dependencies layer changes; the application layer may be retained if app classes/resources did not change; the loader layer usually stays unchanged if the Spring Boot version did not change; the snapshot-dependencies layer only changes when relevant snapshot dependencies change.

If multiple layers change, inspect layer contents and build metadata before concluding the Docker cache malfunctioned.

### 8.5. Comparing image IDs and filesystem layer digests

§§§bash
docker image inspect --format '{{.Id}}' cache-lab:code-a
docker image inspect --format '{{.Id}}' cache-lab:code-b
docker image inspect --format '{{json .RootFS.Layers}}' cache-lab:code-a
docker image inspect --format '{{json .RootFS.Layers}}' cache-lab:code-b
docker history --no-trunc cache-lab:code-a
docker history --no-trunc cache-lab:code-b
§§§

Distinguish image config ID, RootFS layer diff IDs, and registry manifest digest. These are different digests. docker history shows layer history/metadata and displayed sizes, but does not replace comparing individual filesystem layers. An unpushed local image may not have a RepoDigest yet.

### 8.6. Verifying the image runs the new code

§§§bash
docker run --rm -p 8080:8080 cache-lab:code-b
§§§

In another terminal:

§§§bash
curl "http://localhost:8080/greeting?name=java"
§§§

The expected response is Build B. Older containers still use the image ID bound when the container was created. Recreate the container after confirming the new tag points to the desired image.

## 9. Experiment E: BuildKit Cache Mount for Maven Dependencies

Docker layer cache and dependency cache can work side by side. A BuildKit cache mount preserves Maven data in the builder cache, while mount contents are not baked into image layers.

Multi-stage Dockerfile:

§§§dockerfile
# syntax=docker/dockerfile:1

FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY mvnw pom.xml ./
COPY .mvn ./.mvn
RUN chmod +x mvnw

RUN --mount=type=cache,target=/root/.m2 ./mvnw -B dependency:go-offline

COPY src ./src
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B package -DskipTests

FROM eclipse-temurin:17-jre AS extract
WORKDIR /layers
COPY --from=build /workspace/target/cache-lab.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application
COPY --from=extract /layers/extracted/dependencies/ ./
COPY --from=extract /layers/extracted/spring-boot-loader/ ./
COPY --from=extract /layers/extracted/snapshot-dependencies/ ./
COPY --from=extract /layers/extracted/application/ ./
ENTRYPOINT ["java", "-jar", "application.jar"]
§§§

The example assumes the project includes the Maven Wrapper and .mvn/ directory. CI must run tests before the image build step; -DskipTests here merely shortens the packaging step. If you want tests to run in the build stage, remove that flag and configure the pipeline accordingly.

Create .dockerignore for in-container builds:

§§§text
.git
.idea
.gradle
build/
target/
**/.env
**/.env.*
**/secrets/**
**/*.pem
**/*.key
**/*.p12
**/*.jks
§§§

In this Dockerfile the JAR is built inside the build stage, so excluding target/ from the context makes sense.

### 9.1. Running the build and changing source

§§§bash
docker buildx build --load --progress=plain -t cache-lab:inside-a .
docker buildx build --load --progress=plain -t cache-lab:inside-a-repeat .
§§§

When inputs are unchanged, COPY POM/wrapper and dependency:go-offline can cache hit; the /root/.m2 cache mount retains dependency artifacts; COPY src and package can cache hit if sources have not changed.

Change Build A to Build B and rebuild. COPY src changes, so downstream instructions in the build stage must re-execute; earlier dependency resolution may still cache hit. The /root/.m2 cache mount can still supply already-downloaded dependencies.

### 9.2. Changing the dependency version in the POM

When changing Commons Lang 3.14.0 to 3.15.0, COPY pom.xml changes and invalidates caches for subsequent instructions in the build stage; dependency:go-offline runs again; the /root/.m2 cache mount can still retain older dependencies and fetch only the newly needed version; package runs with the updated dependency graph.

Do not pass passwords/tokens in a build ARG to bust caches. BuildKit does not include secret values in cache checksums; if cache invalidation by non-secret config is needed, use a non-secret version marker and only when the output genuinely depends on that marker.

## 10. Experiment F: Cloud Native Buildpacks (CNB)

The Spring Boot Maven/Gradle plugin can build an image from an executable archive using CNB. Buildpacks uses layers and can restore/reuse caches based on metadata.

Build with the same image name:

§§§bash
./mvnw spring-boot:build-image -Dspring-boot.build-image.imageName=cache-lab:cnb
./mvnw spring-boot:build-image -Dspring-boot.build-image.imageName=cache-lab:cnb
§§§

Look in builder logs for analyze, restore, build, export, and layer reuse messages. Do not assume every buildpack prints the exact same log phrasing; read the messages from the builder/version you are using.

Edit Java source and re-run with the same image name. Track which layers are restored/rebuilt. The application layer typically changes; dependency/JRE layers may be reused if their corresponding metadata/inputs have not changed.

Upgrade the Commons Lang version and rebuild the image with the same target image name. Observe the dependency layer. If you change the tag/image name on every run, the Spring Boot plugin's default cache volume name may change based on the full target image name and reduce reuse.

Compare with a cleaned cache:

§§§bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=cache-lab:cnb \
  -Dspring-boot.build-image.cleanCache=true
§§§

cleanCache requests clearing the buildpack cache for that build. It does not clear the Maven local repository, Gradle dependency cache, Docker BuildKit cache, or runtime caches. Do not wipe all Docker volumes to force a CNB rebuild; manage only cache volumes belonging to the exact project/owner.

Inspect the image:

§§§bash
docker image inspect --format '{{.Id}}' cache-lab:cnb
docker history --no-trunc cache-lab:cnb
§§§

If pack CLI is installed, use pack inspect-image cache-lab:cnb to view CNB metadata/layers. Exact layer structure depends on builder/buildpacks and versions; record builder image and buildpack versions alongside your results.

## 11. Prediction Table and Evidence to Record

| Run | Change | Maven/Gradle | JAR | Docker/CNB image |
| --- | --- | --- | --- | --- |
| 0 | Baseline build | Full build; first Gradle run normally executes tasks. | Save initial SHA-256. | Save image ID and layer diff IDs. |
| 1 | Rebuild with unchanged inputs | Gradle may report UP-TO-DATE; Maven/plugins may skip some work. | Usually identical contents if no dynamic timestamps exist. | Many instructions/layers may cache hit/reuse. |
| 2 | Edit Java source only | Relevant compile task re-runs; dependency resolution keeps versions. | SHA-256 usually changes. | Application layer usually changes; dependency layers may reuse. |
| 3 | Change dependency version only | Resolves new dependency; compile/package use updated classpath. | SHA-256 changes and nested JAR version changes. | Dependency layer changes; application layer may persist if app sources unchanged. |
| 4 | Intentionally invalidated cache | Tasks/commands must re-execute; dependency downloads may still sit in separate cache. | Compare digest with corresponding run. | Many instructions/layers rebuilt; bytes do not necessarily differ. |

Record the commit SHA, Java/wrapper versions, before/after dependency versions, build command, task outcomes or Docker cache lines, JAR filename/size/SHA-256, image tag/config ID/RootFS layer diff IDs, endpoint response, and builder/buildpack versions if using CNB.

Do not mark PASS solely because a command returned exit code 0. Confirm that the artifact, dependencies, and runtime response actually reflect the change.

## 12. Interpreting Common Cases

### Java source changed but JAR did not change

Check the exact source file/module, whether Maven package or Gradle bootJar ran, whether you hashed the right artifact or a plain JAR, whether a file copied from another folder overwrote the output, and whether archive contents reflect the new bytecode.

If Gradle reports UP-TO-DATE despite source changes, check source sets, task inputs, and file paths. If the Docker image is stale despite a fresh JAR, inspect the Docker build context and COPY source path.

### Dependency version changed but JAR still contains the old version

Inspect the dependency graph:

§§§bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
§§§

Check lockfiles, constraints, BOMs, dependencyManagement, and the right module. Rebuild the right Boot archive and check BOOT-INF/lib/. If the new version failed to resolve, inspect repositories/mirrors and download errors; do not delete the whole dependency cache to mask the cause.

### Docker build reports cache hit even though a package repository has a newer version

Docker caching for RUN depends on the instruction and preceding layer, not remote repository state. Pin package versions or intentionally invalidate the needed stage. --pull updates base images; --no-cache forces re-executing Dockerfile instructions for that build. These two options serve different goals.

### Docker application layer changed even when only a dependency changed

Inspect the layer index and extracted contents. Some configurations put generated metadata or dependency metadata into the application layer. Compare directory contents/digests before concluding caching failed. Layer names indicate packaging boundaries, not a guarantee that every project always has identical diff IDs.

### CNB does not reuse cache across two runs

Check whether the target image name changed. The Spring Boot plugin by default names build/launch cache volumes based on the full image name. Use the same image name when testing reuse; record builder/buildpack versions and restore/analyze logs.

### Image tag changed yet container returns old response

A tag is a movable reference; an already-created container keeps the image ID from when it was started. Check:

§§§bash
docker image inspect --format '{{.Id}}' cache-lab:code-b
docker inspect --format '{{.Image}}' <CONTAINER_ID>
§§§

If the IDs differ, recreate the container/service per your deployment workflow. Clearing the build cache is not needed to fix a stale container.

## 13. Common Practice Mistakes and Fixes

| Mistake | Why it happens | Fix |
| --- | --- | --- |
| Changing tag on every run and concluding CNB cache does not work. | Default cache volume may depend on full image name. | Keep target image name stable during the experiment. |
| Running clean before every run and expecting UP-TO-DATE. | clean deletes project outputs. | Run a build without clean to observe incremental state. |
| Confusing Gradle FROM-CACHE with dependency cache. | Both caches store different kinds of data. | Inspect task outcomes and dependencyInsight separately. |
| Expecting Maven to print task outcomes like Gradle. | Maven lifecycle/plugin logs do not use the same task model. | Read phase/goal and compiler/plugin logs. |
| Changing file mtime expecting a Docker COPY cache miss. | Docker does not use mtime alone as a cache checksum. | Modify actual input contents. |
| Expecting RUN apt update to cache miss automatically. | Cache lookup does not inspect remote network state. | Pin inputs and use --no-cache-filter/--no-cache intentionally. |
| Rotating a secret and expecting RUN to cache miss. | Secret values do not enter cache checksums. | Design outputs independent of secrets; use a non-secret version marker if needed. |
| New dependency does not appear in image. | Image build used an old JAR or Dockerfile COPY used the wrong path. | Verify the JAR first, then check the archive path. |
| Every image layer changes after editing one line. | Copying the entire uber JAR into one layer or metadata/layer layout changed. | Use layered JAR and compare extracted directories. |
| Docker build cannot find the JAR. | .dockerignore excluded target/build or wrong path. | Inspect build context and archive path. |
| Tools jarmode fails to run. | Layer index/tools mode not packaged or archive has launch script. | Check Boot plugin packaging and list-layers. |
| Container runs old code. | Container is still using the old image ID. | Recreate container from the new image. |
| CNB image build fails without Docker daemon. | Plugin needs Docker daemon/context connection. | Check Docker context/daemon and permissions. |
| Wiping all caches deletes other projects' data. | Caches are shared across projects/runners. | Clean scoped to specific owner, volume, and lifecycle. |

## 14. Cleaning Up and Restoring After the Experiment

Save the JARs, SHA-256 digests, Docker build logs/layer digests, CNB builder logs/image metadata, before/after dependency trees, and source diff before cleaning up.

| Command | Scope |
| --- | --- |
| ./mvnw clean | Deletes Maven generated outputs in the project per clean configuration. |
| ./gradlew clean | Deletes project build outputs, typically build/. |
| ./gradlew --no-build-cache | Disables fetching task outputs from Gradle build cache for that build. |
| ./gradlew --refresh-dependencies | Refreshes dependency resolution state. |
| docker build --no-cache | Skips Dockerfile layer cache for that build run. |
| docker build --pull | Requests updating base images per pull policy. |
| -Dspring-boot.build-image.cleanCache=true | Instructs Spring Boot Maven plugin to clear CNB cache for that image build. |

Do not run docker system prune -a --volumes, delete all of ~/.m2 or ~/.gradle, or purge shared remote caches just to wrap up the lab. If you need to remove images/containers you created, verify the exact names:

§§§bash
docker image ls cache-lab
docker ps -a --filter ancestor=cache-lab:code-b
§§§

Stop/remove only test containers and lab-created images per machine policy. Do not delete builder/cache volumes currently used by other projects or jobs.

## 15. Extension Exercises

### Comparing uber JAR vs. layered JAR

Create a Dockerfile that copies the entire cache-lab.jar into a single layer. Build a baseline, then edit one Java line. Compare against the Dockerfile using jarmode=tools extract --layers. Analyze layer counts, sizes of changed layers, and cache reuse on each COPY instruction.

Do not claim a layered image is always smaller in total bytes; the primary benefit in this lab is caching/pulling only the changed parts.

### Testing snapshot dependencies and base images

In a separate Maven/Gradle environment, create a SNAPSHOT module or changing dependency to observe differences compared to fixed release dependencies. Record repository update policies and dependency caching. Then build two images using the same JAR but different base image tags/digests; compare the case where the application layer stays unchanged while the image digest changes.

### Checking reproducibility

Build two independent workspaces from the same commit, with the same wrapper/JDK/dependency versions and the same base image digest. Compare JAR SHA-256 digests, then compare layer diff IDs. If the JARs match while the images differ, inspect builder/run images, created dates, architectures, and metadata. If the JARs differ, use diffoscope or extract the archives to locate timestamps, file ordering, and generated metadata.

## 16. Completion Checklist

### Build tool

- [ ] Recorded commit, JDK, and wrapper versions.
- [ ] Built baseline with Maven or Gradle.
- [ ] Rebuilt with unchanged inputs and read logs accurately.
- [ ] Edited one Java line, rebuilt, and verified the new response.
- [ ] Upgraded Commons Lang version, inspected dependency graph and nested JAR.
- [ ] Distinguished Gradle UP-TO-DATE, FROM-CACHE, SKIPPED, NO-SOURCE.
- [ ] Did not confuse Maven compiler/plugin behavior with Gradle task outcomes.

### Docker/CNB

- [ ] Built Docker image from layered Spring Boot JAR.
- [ ] Read cache lines in BuildKit logs.
- [ ] Compared image config ID and RootFS layer diff IDs.
- [ ] Observed an application-only change.
- [ ] Observed a dependency-only change.
- [ ] Verified container runs the new image.
- [ ] Tested CNB with a stable image name and read layer restore/rebuild logs.
- [ ] Distinguished Docker layer cache, BuildKit cache mounts, and CNB build/launch caches.

### Conclusion and evidence

- [ ] Have SHA-256 for each built JAR.
- [ ] Have before/after dependency versions.
- [ ] Have task outcome logs or Docker cache outcomes.
- [ ] Have before/after image IDs/layer digests.
- [ ] Have before/after endpoint responses.
- [ ] Did not delete shared caches or out-of-scope artifacts.
- [ ] Did not claim a layer was reused unless logs/digests prove it.

**Pass criteria:** the learner modifies code and a dependency in two separate runs; proves the JAR/runtime dependency changed; explains Maven or Gradle task/cache behavior; identifies which Docker/CNB layers were cached or rebuilt using logs and image metadata; and verifies the container returns the response from the new image. If a Docker daemon/CNB builder is unavailable, explicitly document the unexecuted parts and do not mark the image-layer experiment complete based solely on building the JAR.

## Official References

- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.3 — Efficient Deployments](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.3 — Dockerfiles and Layered Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3.13 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Docker — Build Cache](https://docs.docker.com/build/cache/)
- [Docker — Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Docker — Cache Optimization](https://docs.docker.com/build/cache/optimize/)
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Build Cache Debugging](https://docs.gradle.org/current/userguide/build_cache_debugging.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)

**Remember:** modifying code mainly affects application inputs/layers; changing dependencies affects dependency resolution, executable archives, and dependency layers; changing the base image affects the image foundation. Keep each experiment limited to one variable, read cache logs, compare SHA-256/layer digests, and verify responses from the new container. Caching is only an optimization; evidence must show that the right output was produced and the right image is running.