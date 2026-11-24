# How Does Cloud Native Buildpacks Create an Image from a Spring Boot Application?

**Cloud Native Buildpacks (CNB)** is a set of specifications and tools that transforms source code or application artifacts into an **OCI container image** without requiring developers to maintain a Dockerfile manually. With Spring Boot, the Gradle `bootBuildImage` task or the Maven `spring-boot:build-image` goal takes the built executable JAR/WAR, passes it to a **builder** containing buildpacks and the lifecycle, and then produces an image with a Java runtime, application layers, launch configuration, and metadata.

Three points to remember:

1. **Not needing a Dockerfile does not mean not needing a container engine.** In Spring Boot 3.3, the integrated CNB tasks/goals need to communicate with a **Docker daemon** to run the builder and export the image.
2. **Compile/package and containerize are two different jobs.** Gradle/Maven prepares the JAR or WAR; CNB buildpacks detect the artifact, provide the JRE, layers, and launch process for the container.
3. **An image is not a renamed JAR.** It consists of OCI config, runtime base layers, a Java runtime, application layers, and process information. The image can be stored locally or pushed to a registry according to configuration.

This lesson dives deep into the builder/buildpack/lifecycle components, the five processing phases, how Spring Boot Gradle/Maven invokes CNB, a hands-on Java 17 example, cache/layer optimization, differences from Dockerfile, build and runtime environments, SBOM/security, troubleshooting, and CI/CD considerations.

The example pins **Spring Boot 3.3.5**, **Gradle 8.7**, **Java 17**, and compatible Paketo Java buildpacks for illustration, **without claiming these are the latest versions**. Image/builder `latest` tags can change over time; pin versions or digests in a strict release process.

## 1. Why Cloud Native Buildpacks?

A common way to containerize a Spring Boot app is to write a Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is only a **minimal Dockerfile for comparison**, not a file in the CNB example. With this approach, you must manually choose the base image, JRE, user, how to copy/partition content layers, entrypoint, how to apply OS security patches, and the build pipeline.

With Spring Boot and CNB, creating an image can start with:

~~~bash
./gradlew bootBuildImage
~~~

or:

~~~bash
mvn spring-boot:build-image
~~~

The builder and buildpacks encapsulate the logic to detect a Java application, add the runtime, declare how to run it, use cache, and create OCI layers. The operational mindset shifts from **writing custom Dockerfile workflows for each app** to **centrally managing builders/buildpacks/run images and artifact policies**.

**Do not assume CNB is automatically best on every criterion.** For native libraries, very specific packages, extremely small image requirements, or unusual build pipelines, a Dockerfile or custom builder may be more suitable. Evaluate security, compatibility, performance, and maintainability.

## 2. Main Components

| Component | Role | Example |
| --- | --- | --- |
| Application input | Source or artifact to package | Executable Spring Boot JAR |
| Platform | Connects the application with lifecycle, builder, cache, and output | Spring Boot plugin, `pack` CLI |
| Builder image | Build environment containing buildpacks, lifecycle, and build-time base | Paketo builder |
| Buildpack | Detects application capabilities and contributes runtime/layers | Paketo Java buildpacks |
| Lifecycle | Orchestrates build phases according to the CNB specification | Analyzer, detector, restorer, builder, exporter |
| Build image | OS/tools needed during the build process | Build-time base of the builder |
| Run image | OS/base layers of the image at runtime | Run image referenced by the builder |
| Cache | Stores reusable layers | Docker named volumes or platform-supported mechanisms |
| Result image | OCI-compliant container image | `cnb-hello:1.0.0` |
| Launcher/process | How the app runs inside the image | CNB launcher and process type |

### How Builder Differs from Buildpack and Run Image

A **buildpack** is logic that knows how to detect/provide a capability: Java runtime, executable-JAR handling, process metadata, etc. A **builder** is an image configured with a buildpack order, lifecycle, build-time base, and a reference to a run image. The **run image** provides the base layers used in the final container.

~~~text
Spring Boot JAR/WAR
       |
       v
+-----------------------------------+
| CNB builder image                 |
| - ordered buildpacks              |
| - lifecycle                       |
| - build-time environment          |
| - reference to run image          |
+-----------------------------------+
       |
       v
 Analyze -> Detect -> Restore -> Build -> Export
       |
       v
+-----------------------------------+
| OCI application image             |
| - compatible run image layers     |
| - Java runtime layers             |
| - application layers              |
| - launch process and metadata     |
+-----------------------------------+
       |
       v
 Docker / Kubernetes / container runtime
~~~

The diagram does not guarantee the same number or position of layers for every builder. A composite buildpack can invoke child buildpacks; not every buildpack corresponds to exactly one OCI layer.

### A Build Image Is Not a Run Image

The build-time environment may need compilers/tools to run buildpacks. The runtime environment usually only needs runtime libraries/JRE and the app. If you select a custom run image that is incompatible with the OS/architecture or the builder target, the build may fail or the image may run incorrectly. Therefore, without a clear reason, **use the run image selected by the builder**.

## 3. What Does the Spring Boot Plugin Pass to CNB?

Gradle:

~~~text
src/main/java + src/main/resources
             |
     compileJava/processResources
             |
           bootJar
             |
    executable Spring Boot JAR
             |
        bootBuildImage
             |
      CNB builder/lifecycle
             |
        OCI image
~~~

`bootBuildImage` is a task provided by the Spring Boot Gradle plugin when the appropriate Java or War plugin is applied. The task takes the built executable archive (`bootJar` or `bootWar`) as input. Gradle task dependencies ensure the required producer tasks run beforehand.

Maven:

~~~text
Source -> Maven package/repackage -> executable JAR/WAR
                                             |
                                             v
                                  spring-boot:build-image
                                             |
                                             v
                                          OCI image
~~~

The `spring-boot:build-image` goal run from the command line ensures the appropriate package lifecycle has run. If you want to bind it to the `package` phase, the Spring Boot documentation recommends the `build-image-no-fork` goal to avoid launching a duplicate lifecycle loop.

**Key takeaway:** CNB in general can build from source; however, the Spring Boot Gradle/Maven plugin integration in this lesson **passes a packaged application archive**. By default, the buildpack does not re-execute `gradle build` or `mvn package` from source inside the builder.

### Distinguishing Tasks

- `bootJar`: creates an executable JAR; no container image yet.
- `bootWar`: creates an executable WAR; no container image yet.
- `bootBuildImage`: creates an OCI image from the executable archive.
- `java -jar`: runs the artifact using the current JVM.
- `docker build`: builds an image from a Dockerfile/build context, which is a different workflow.
- `docker run`: runs a container from an existing image.

If `bootJar` succeeds but `bootBuildImage` fails because of the Docker daemon, that is **not necessarily a Java compilation error**.

## 4. The Five Phases of the Cloud Native Buildpacks Lifecycle

According to CNB documentation, the five main phases are **Analyze → Detect → Restore → Build → Export**. The platform may run them through a combined process such as `creator`, so logs will not always display five separate processes.

~~~text
                  Application artifact
                          |
                          v
                    [Analyze]
              Previous image metadata
                          |
                          v
                     [Detect]
             Choose applicable buildpacks
                          |
                          v
                    [Restore]
                   Reuse layers
                          |
                          v
                     [Build]
       Runtime + application + launch metadata
                          |
                          v
                     [Export]
              OCI image + cache update
~~~

### 4.1. Analyze

The analyzer inspects metadata from the previous image and registry/cache access conditions according to the platform. The goal is to understand the state of the previous build so layers can be reused. On the first run without a previous image, a build can still succeed; having no cache is not automatically an error.

### 4.2. Detect

The detector walks the buildpack order configuration, asks buildpacks whether they recognize the input, and selects a matching group; from there it creates a **build plan**. For an executable Spring Boot JAR, Java/executable-archive buildpacks can be selected; unrelated buildpacks can be skipped.

If the builder lacks a buildpack that supports Java or the input file is not a valid archive format, an error may appear during the Detect phase. Changing `spring.application.name` will not resolve a missing buildpack error.

### 4.3. Restore

The restorer restores metadata and reusable layers from the previous image/cache. The Java runtime layer, infrequently changing libraries, or launch layers can be reused when inputs/metadata match. Do not assume every code edit changes only one layer: partitioning and cache invalidation depend on the buildpack/lifecycle/artifact.

### 4.4. Build

The selected buildpacks execute their logic to contribute:

- A Java/JRE runtime suitable for the application's bytecode.
- Application files from the executable JAR/WAR.
- Runtime library layers and metadata on how to launch.
- Build-time configuration and component/SBOM information if supported by the buildpacks.
- Process, environment, and filesystem layer information for the exporter to use.

With Paketo Java buildpacks, the `BP_JVM_VERSION=17` variable requests the Java major version inside the image. Gradle's Java toolchain remains a separate setting: Gradle uses it to compile, while the buildpack uses that variable to prepare the runtime. The two versions must be compatible.

### 4.5. Export

The exporter combines **run image base layers** with launch layers/metadata to create the OCI image, writes it to the target output, and updates the cache. Depending on platform/plugin config, the image can be loaded into the local Docker daemon or pushed to a registry.

**The final image is not the builder image.** The builder is the build environment; the app runtime image is newly created from the run image and appropriate layers.

### Launch and Rebase Are Different Operations

When the container runs, the **CNB launcher** executes the process declared by the buildpacks, which is not necessarily the exact `java -jar app.jar` string a developer used from a terminal.

**Rebase** is an operation that swaps the base/run-image layers of a built image when compatible, avoiding re-running all buildpacks. Rebase does not compile Java sources, does not upgrade Spring dependency versions in the JAR, and does not fix every CVE. It produces a new image/digest, requiring testing and release provenance recording.

## 5. Gradle Hands-On: Spring Boot REST Application → Image

This example can be run with JDK 17, Gradle Wrapper 8.7, Spring Boot 3.3.5, a running Docker daemon, and network access to builder/dependency repositories. We will create an HTTP endpoint returning `HELLO_FROM_CNB` and package it **without a Dockerfile**.

### 5.1. Structure

~~~text
cnb-hello/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/cnb/
    ├── CnbHelloApplication.java
    └── HelloController.java
~~~

If using Gradle Wrapper, the root also contains `gradlew`, `gradlew.bat`, and `gradle/wrapper/`. The example assumes a compatible Wrapper is already present.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'cnb-hello'
~~~

### 5.3. `build.gradle` (Groovy DSL, complete)

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}

springBoot {
    mainClass = 'com.example.cnb.CnbHelloApplication'
}

tasks.named('bootBuildImage', BootBuildImage) {
    imageName = 'cnb-hello:1.0.0'
    environment['BP_JVM_VERSION'] = '17'
}
~~~

Explanation:

1. The Java plugin and Spring Boot plugin create the tasks needed to compile, package, and build the image.
2. `spring-boot-starter-web` provides Spring MVC and the embedded Tomcat runtime.
3. `java.toolchain` requests Java 17 when compiling; `BP_JVM_VERSION` controls the version requirement for the Paketo Java buildpack.
4. `imageName` sets an explicit local tag, avoiding inferring it from `project.name` and `project.version`.
5. `builder` is not set, so the Spring Boot plugin uses the default builder for the plugin version in use; this default **can change across plugin versions**.
6. `publish` is not enabled: the image is built into the Docker daemon the plugin connects to, and is not automatically pushed to a registry.
7. There is no `Dockerfile` and `docker build` is not called.

### 5.4. `CnbHelloApplication.java`

Path `src/main/java/com/example/cnb/CnbHelloApplication.java`:

~~~java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbHelloApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbHelloApplication.class, args);
    }
}
~~~

### 5.5. `HelloController.java`

Path `src/main/java/com/example/cnb/HelloController.java`:

~~~java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public String hello() {
        return "HELLO_FROM_CNB";
    }
}
~~~

The controller is in the same package as the main class so it is found by Spring Boot component scan. No DB, message broker, or cloud secrets are needed. Spring MVC defaults to port 8080 if `server.port` is not changed.

### 5.6. Check the Environment

~~~bash
java -version
./gradlew --version
docker version
docker info
~~~

`docker version` and `docker info` must be able to connect to the daemon. **Having only the Docker CLI executable is not enough.** Docker Desktop must be running or the Docker Engine/remote daemon must have appropriate access permissions. If the Docker context/`DOCKER_HOST` points to a different daemon, the image may appear in a different image store than where you are checking.

### 5.7. Build the Image

~~~bash
./gradlew clean bootBuildImage
~~~

Gradle runs the dependent tasks needed to produce the executable archive, and then the `bootBuildImage` task starts the CNB lifecycle. The first run may need to download Maven dependencies, builder/run images, and the JRE runtime, making it slower than cached builds.

Actual logs may show messages similar to:

~~~text
> Task :compileJava
> Task :bootJar
> Task :bootBuildImage
... buildpack/lifecycle logs ...
... image created ...
~~~

This is a **log outline**, not guaranteed stdout. The task list/order/phase text and digest vary by plugin, cache, and Docker. Do not infer an image digest before the image itself has been created.

### 5.8. Verify the Image

~~~bash
docker image ls cnb-hello
docker image inspect cnb-hello:1.0.0
~~~

Once the image is loaded into the Docker daemon, the inspect command returns image ID/config/layers info. If it is not found, check `imageName` in the build output, the Docker context/daemon Gradle used, and whether the build actually completed.

### 5.9. Run the Container

~~~bash
docker run --rm -p 8080:8080 cnb-hello:1.0.0
~~~

In another terminal:

~~~bash
curl -fsS http://localhost:8080/api/hello
~~~

Expected response body:

~~~text
HELLO_FROM_CNB
~~~

If host port 8080 is already in use:

~~~bash
docker run --rm -p 18080:8080 cnb-hello:1.0.0
~~~

and test:

~~~bash
curl -fsS http://localhost:18080/api/hello
~~~

In the `-p HOST:CONTAINER` option, the right-hand port must be the port the app actually listens on inside the container. Running in the foreground keeps the terminal open; stop with Ctrl+C. The HTTP response body does not automatically include a newline; tests should compare exact content.

**Important:** `curl` may run too early before the app finishes starting up. In CI, use retry/timeout or a health check instead of assuming a single request right after `docker run -d` always succeeds.

## 6. How Does Maven Create a Similar OCI Image?

With Maven, create the same two Java files, but use `pom.xml` instead of Gradle scripts. Complete POM example for Spring Boot 3.3.5:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cnb-hello</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>com.example.cnb.CnbHelloApplication</mainClass>
                    <image>
                        <name>cnb-hello:1.0.0</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run from the Maven project root:

~~~bash
mvn spring-boot:build-image
docker image inspect cnb-hello:1.0.0
docker run --rm -p 8080:8080 cnb-hello:1.0.0
~~~

The Maven goal `spring-boot:build-image` on the CLI ensures the package lifecycle has run. There is no need to call `mvn package` manually beforehand when using the goal as documented.

### `build-image` vs `build-image-no-fork`

- **`build-image`:** suitable for calling directly from the terminal; forks the lifecycle to ensure packaging.
- **`build-image-no-fork`:** suitable for binding a goal execution to the `package` lifecycle to avoid forking the package phase a second time.

Example snippet in `spring-boot-maven-plugin`, use only when **you want to automatically build an image on every package**:

~~~xml
<executions>
    <execution>
        <goals>
            <goal>build-image-no-fork</goal>
        </goals>
    </execution>
</executions>
~~~

Do not add this snippet to the exercise POM if you want image building to be an intentional operation. If bound to `package`, CI running `mvn package` might require a Docker daemon and network even when only intending to compile/test the artifact.

## 7. `bootBuildImage` vs `pack build` vs Dockerfile

| Approach | Input | Who decides runtime image/layers? | Needs Dockerfile? |
| --- | --- | --- | --- |
| Gradle `bootBuildImage` | Boot executable archive | CNB builder/buildpacks | No |
| Maven `spring-boot:build-image` | Boot executable archive | CNB builder/buildpacks | No |
| CNB `pack build` | Source directory or artifact | Selected builder/buildpacks | No |
| `docker build` | Dockerfile and build context | Dockerfile/base images | Yes |

`pack` is the standalone CNB CLI. If you already have a Spring Boot JAR:

~~~bash
./gradlew bootJar
pack build cnb-hello:1.0.0 --path build/libs/cnb-hello-1.0.0.jar --builder paketobuildpacks/builder-jammy-base:latest
~~~

This is an **illustrative command** requiring the `pack` CLI to be installed and the Java builder to exist/be compatible; it is not mandatory for using the Spring Boot plugin. With the Spring Boot Gradle configuration as in the example, the executable JAR is typically placed at `build/libs/cnb-hello-1.0.0.jar`. If `archiveFileName` has been customized, use the actual path.

**You do not need to install the pack CLI for `bootBuildImage`.** The Spring Boot plugin acts as the CNB platform/orchestrator itself. A Dockerfile may be appropriate when an organization needs OS packages/native customizations beyond the capabilities of available builders. However, there is no universal answer that one approach is always safer or smaller than the other without measuring and scanning.

## 8. Choosing Java Version, Builder, and Run Image

### Java Version in Three Places

- **`java.toolchain=17`:** the Java version used for compilation when Gradle uses toolchains.
- **`BP_JVM_VERSION=17`:** tells the Paketo Java buildpack to select a Java 17 runtime during image build.
- **`java -version` on host:** the JVM invoked by the current shell, not necessarily matching the runtime JVM packaged in the image.

With Paketo, major version 17 may resolve to a current Java 17 patch provided by the builder/buildpack. **Do not infer the exact patch version solely from `BP_JVM_VERSION=17`.** Use SBOM/build output and image metadata to verify the JRE.

### Custom Builder

Gradle snippet used only when a suitable builder is available:

~~~groovy
tasks.named('bootBuildImage') {
    builder = 'paketobuildpacks/builder-jammy-base:latest'
}
~~~

The Paketo builder here is a documented choice for the Spring Boot 3.3 family; the mutable `latest` tag should not be the sole pin in strict release CI. Builder versions can change buildpack behavior, cache compatibility, Java runtime, and security settings.

### Custom Run Image

The builder specifies a compatible run image by default. You can override `runImage` with an image **verified to be compatible**, but do not put a regular Dockerfile JRE base image into this setting just because its name contains `java`.

**Difference:** the builder image contains the CNB lifecycle/buildpacks; the run image provides the OS base for the final image. If a custom run image differs in stack/target architecture/libc, the build may fail or the image may run incorrectly. Without a special policy, prefer the run image selected by the builder.

### Build-Time and Runtime Variables

| Category | Example | Timing |
| --- | --- | --- |
| Buildpack Java option | `BP_JVM_VERSION=17` | Image build |
| Paketo launch/runtime variable | Certain `BPL_*` options | Container startup |
| Spring application variable | `SPRING_PROFILES_ACTIVE`, `SERVER_PORT` | When Spring Boot runs |
| Gradle compiler config | Java toolchain | Before image build |

Example of passing a Spring profile at runtime:

~~~bash
docker run --rm -p 18080:8080 -e SPRING_PROFILES_ACTIVE=dev cnb-hello:1.0.0
~~~

This profile is not required for the example's endpoint to work. In real applications, do not hardcode credentials or environment-specific secrets into the image or build script.

## 9. How Do Layering and Caching Affect Speed?

A Spring Boot executable JAR can contain:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
org/springframework/boot/loader/
BOOT-INF/layers.idx       (when a layered archive is created)
~~~

Depending on version/build configuration, Spring Boot can categorize contents into dependencies, snapshot dependencies, loader, and application. Java buildpacks can leverage a layered archive or perform their own analysis to create appropriate OCI layers. **Do not equate the number of OCI layers with the number of entry groups in the JAR.**

Suppose there are two builds:

~~~text
A: same Spring libraries + Java application code A
B: same Spring libraries + Java application code B
~~~

If only application code changes, some dependency/runtime layers can be reused; if the JRE, builder, or dependency graph changes, the cache may be invalidated.

### Build Cache and Launch Cache

Spring Boot Gradle/Maven CNB integration configures a **build cache** and **launch cache**, typically using Docker named volumes for local builds. According to Spring Boot 3.3 documentation, default cache names can be derived from the **full output image name**. Therefore:

~~~text
cnb-hello:1.0.0
cnb-hello:1.0.1
~~~

can have different cache names, preventing layers from being reused as expected even when very little code changed. This is why CI needs to manage cache naming and cache lifecycles.

**Optional** example, not needed for the first project:

~~~groovy
tasks.named('bootBuildImage') {
    buildCache {
        volume {
            name = 'cnb-hello.build-cache'
        }
    }
    launchCache {
        volume {
            name = 'cnb-hello.launch-cache'
        }
    }
}
~~~

When using a shared CI Docker daemon, set distinct cache names per application/build to avoid collisions between jobs. Do not share caches across unrelated applications without control.

### Caches Are Not All the Same

- **Gradle build cache/up-to-date:** reuses task outputs/compile results when inputs match.
- **CNB cache:** reuses build/launch layers stored by CNB buildpacks.
- **Docker local image/layer store:** manages image blobs of the Docker daemon.
- **Registry cache/previous image:** depends on platform and remote build configuration.

Running `./gradlew bootBuildImage` can skip compilation if Gradle sees unchanged sources, but the image build/lifecycle still has its own work. Do not treat `UP-TO-DATE` on a Gradle task as proof that all CNB layers were reused.

### Measure Instead of Guessing

To benchmark, compare builds with the same builder/run images, code/dependencies, cache state, network, and machine. Separate cold-cache runs from warm-cache runs. Record compile time, CNB lifecycle time, number of restored/rebuilt layers, and peak memory. A Dockerfile build is not necessarily slower than CNB; Docker layer ordering and build context also have a large impact.

## 10. Runtime Process, Non-Root, SBOM, and Image Identity

### Launch Process

The CNB launcher selects the process contributed by the buildpacks. The OCI Entrypoint/Cmd configuration is not necessarily equivalent to the literal string `java -jar app.jar`. Use:

~~~bash
docker image inspect cnb-hello:1.0.0
~~~

to inspect the actual metadata. Docker port publishing via `-p` only maps host ↔ container ports; it does not force Spring Boot to change `server.port`.

### Non-Root

Spring Boot 3.3 documentation states that CNB images are built and run with non-root users in supported workflows. Still, check the actual image `User`/security context if using a custom builder, container runtime overrides, or special policies. **Non-root is a layer of protection, not a replacement for image scanning and filesystem permission management.**

### SBOM

Buildpacks can generate a **Software Bill of Materials (SBOM)** describing the JRE, application dependencies, or other components depending on the buildpack. It supports inventory/license/CVE scanning and provenance tracking. An SBOM **does not by itself prove an image is free of vulnerabilities**: you need a scanner, vulnerability data, buildpack/base updates, and security policies.

The CNB CLI `pack` provides commands to view/download SBOMs in supported versions, such as `pack sbom download`. Format/path details can vary by CNB API and buildpack version; inspect actual output rather than fabricating a report.

### Release Provenance

A useful record:

~~~text
Git commit:           <actual-commit-from-CI>
Spring Boot version:  <actual-version>
Builder digest:       <verified-builder-digest>
Run image digest:     <verified-run-image-digest>
Output image tag:     <registry/repository:tag>
Output image digest:  <actual-sha256-digest>
SBOM reference:       <actual-reference-if-generated>
~~~

This is a **template to fill in**, not data generated in this lesson. Tags can be mutated if the registry allows it; image digests identify content better during production investigations.

### Do Not Embed Secrets

Do not write passwords/tokens or private registry keys into Gradle `environment`, packaged Spring `application.properties`, Docker layers, or OCI labels. Registry/build authentication should come from appropriate CI secrets/config mechanisms; runtime credentials from orchestrator secret management. Build logs and SBOMs may be retained or shared, so review information policies.

## 11. How Rebase Differs from Rebuild and Dependency Upgrades

CNB supports the concept of **rebase**: replacing base/run image layers with a new compatible run image without re-running all buildpacks.

- **Rebase:** replaces runtime base layers; can apply some OS security fixes when compatible.
- **Rebuild:** re-executes buildpacks, potentially selecting different runtime/app dependencies based on inputs.
- **Application dependency upgrade:** updates Gradle/Maven dependencies, compiles/tests, and produces a new binary.

Rebase does not upgrade Spring libraries inside the JAR. Nor does it always replace the JRE if the Java runtime was contributed by buildpacks in a layer separate from the run image base. Rebase produces a new image/digest and requires tests/scans and a release record.

Mutable builder tags can change buildpack versions, Java patch selection, SBOM, and behavior even when source code is unchanged. For supply-chain reproducibility, manage builder/run image digests, buildpack versions, dependency locking, and artifact provenance.

## 12. Publishing Images to a Registry and CI/CD Deployment

In the Gradle example, `imageName='cnb-hello:1.0.0'` only creates a local image in the Docker daemon. **It does not automatically push the image.**

Once you have registry permissions and have logged in using a secure mechanism:

~~~bash
docker tag cnb-hello:1.0.0 registry.example.test/team/cnb-hello:1.0.0
docker push registry.example.test/team/cnb-hello:1.0.0
~~~

`registry.example.test` is only an example and must be replaced with a real registry; there is no real endpoint to push to here. Spring Boot `bootBuildImage` also has a `publish` property and registry authentication configuration, but only enable it when you intend to publish the image:

~~~groovy
tasks.named('bootBuildImage') {
    publish = true
}
~~~

This is an **optional snippet**, not part of the hands-on project that has no registry yet. Image name, authentication, and push permissions must be properly supplied by CI. Pushing an image is a release action, so it needs quality gates/release approvals per organization policy.

### CI Smoke Test

A pipeline might run:

~~~bash
./gradlew clean test bootBuildImage
docker image inspect cnb-hello:1.0.0
docker run --rm -d --name cnb-smoke -p 18080:8080 cnb-hello:1.0.0
curl -fsS http://localhost:18080/api/hello
docker stop cnb-smoke
~~~

This is an **illustrative command flow**, not a production-ready CI test: `curl` might arrive before the server is ready. Real CI needs readiness retries, timeouts, cleanup on failure, container logs, and assertions on HTTP body/status. Also ensure the Docker daemon seen by the CI test is the one where the image was built.

### Architecture and Platform Compatibility

An image built on amd64 does not automatically become an ARM64 image; target architecture depends on the builder/run image/platform. To run across multiple architectures, you need an appropriate build workflow and multi-arch manifest. Do not just change a tag and expect native libraries and OS layers to work cross-platform.

## 13. Common Errors Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Task 'bootBuildImage' not found` | Project has not applied Spring Boot and appropriate Java/War plugins | Check `plugins`, `tasks --all`, and target module |
| Maven goal not found | Spring Boot Maven plugin/POM setup is unsuitable | Check `pom.xml`, plugin resolution |
| `Cannot connect to Docker daemon` | Engine not running, wrong context/socket/permissions | `docker info`, `DOCKER_HOST`/Docker context/TLS |
| Unable to pull builder image | Network, DNS, proxy, registry auth/rate limit | Check builder URL and network |
| Detect phase failed | Builder lacks Java buildpacks or archive is invalid | Check `bootJar` and builder metadata |
| Build phase missing JRE | `BP_JVM_VERSION` not supported by builder/buildpacks | Choose a compatible JDK version |
| `UnsupportedClassVersionError` | Container Java is lower than bytecode | Compare Gradle toolchain and Paketo JVM |
| Image not listed in `docker image ls` | Wrong image tag or output is on another daemon | Check `imageName` in logs and Docker context |
| HTTP 404 | Wrong route or component scan | Check `/api/hello`, package, and logs |
| Container starts then exits | App exception, no long-lived process, or missing config | `docker logs`, startup exception |
| Port unreachable | Wrong `-p`, app not ready, or port conflict | Check listen port and port mapping |
| Build re-downloads JRE every time | Cache lost, image name/tag changes, builder updated | Check CNB caches and image naming |
| Image too large | Heavy JRE/base/dependency layers | Compare builder/run image, SBOM, and dependencies |
| CI hits OOM | Concurrent builds, image build cache/daemon/JVM out of RAM | Check cgroup limits and memory allocations |
| Push denied | Missing registry credentials or repository permissions | Check CI identity and registry policy |
| CVEs still present | App libs/JRE/run image not updated | Scan SBOM, patch dependency/runtime/base |
| ARM cluster won't run amd64 image | Architecture mismatch | Build for the right platform/multi-arch strategy |

**Read the failing phase accurately:** a buildpack detection failure occurs differently from a Docker daemon access error or an HTTP error in a running container. Do not change `spring.application.name` or Java packages just because an image cannot be pulled from a registry.

## 14. Standard Diagnostic Workflow

1. **Confirm JAR/WAR runs:** `./gradlew bootJar` and `java -jar` before investigating CNB.
2. **Confirm Docker daemon:** `docker info` succeeds under the exact user/context of the build plugin.
3. **Identify builder/run image:** logs show which image tags/digests are used; check OS/architecture/JVM compatibility.
4. **Check failing phase:** Analyze, Detect, Restore, Build, or Export.
5. **Check Java:** compile/toolchain JDK, `BP_JVM_VERSION`, and actual JRE in the image/SBOM.
6. **Inspect output image:** `docker image inspect` with the exact imageName/tag/daemon.
7. **Run the container:** ports, environment, startup logs, and process exit code.
8. **Test real HTTP endpoint:** with retries/health readiness, verify status/body.
9. **Check cache:** image name, volumes, builder versions, CI runner lifetime.
10. **Check policy:** SBOM, CVE scanner, non-root runtime, image signing, and secrets.
11. **Record output digest/provenance:** ensure a traceable release record.
12. **Do not mix build and runtime errors:** image created does not mean business functionality works.

### Quick Diagnostic Commands

~~~bash
./gradlew tasks --all
./gradlew clean bootJar
./gradlew bootBuildImage --info
docker info
docker image ls
docker image inspect cnb-hello:1.0.0
docker run --rm -p 18080:8080 cnb-hello:1.0.0
curl -fsS http://localhost:18080/api/hello
~~~

`--info` displays additional Gradle logs, while detailed buildpack output varies by platform/builder versions. With a cold cache, the first run may download many images/runtime layers.

## 15. Self-Check Questions

**Q1.** Does `bootBuildImage` require a Dockerfile?

**Answer:** No. It uses a CNB builder/lifecycle to build an OCI image from the executable archive. With Spring Boot 3.3 integration, a Docker daemon is still required.

**Q2.** How do a builder image and a run image differ?

**Answer:** The builder contains buildpacks/lifecycle and the build environment; the run image provides the runtime base layers for the final image.

**Q3.** What are the five main phases of the lifecycle?

**Answer:** Analyze → Detect → Restore → Build → Export, which respectively inspect previous metadata, select buildpacks, reuse cache, contribute layers, and produce the output image/cache.

**Q4.** If `bootJar` succeeds, does that guarantee `docker image inspect` will find a new image?

**Answer:** No. `bootJar` only creates the JAR; `bootBuildImage` creates the image.

**Q5.** Does `BP_JVM_VERSION=17` change the Gradle compiler to Java 17?

**Answer:** No. That is a Paketo Java buildpack build-time setting; Gradle's Java toolchain is separate and must be compatible.

**Q6.** Why can changing an image tag invalidate the cache?

**Answer:** The Spring Boot plugin's default CNB cache volumes can depend on the full image name; changing the tag affects the cache name/lifecycle.

**Q7.** Does a locally built image automatically appear in the registry?

**Answer:** No. You must enable publish with appropriate authentication or run a separate push.

**Q8.** Does an SBOM guarantee there are no CVEs left?

**Answer:** No. An SBOM describes components and supports scanning/auditing; vulnerability data and remediation are still required.

**Q9.** Does rebase fix Spring dependency versions inside the JAR?

**Answer:** No. Rebase swaps compatible run-image base layers; it does not recompile source or update Java dependencies.

**Q10.** When the container does not return `HELLO_FROM_CNB`, what should you check?

**Answer:** Whether the image was built properly, whether the container is still running, startup/logs, port mapping, HTTP route, readiness, and app runtime config.

## 16. Official Documentation

- Spring Boot 3.3 — [Packaging OCI Images with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html): `bootBuildImage`, Docker, builder, run image, env, caches.
- Spring Boot 3.3 — [Maven Build Image](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html): `build-image`, `build-image-no-fork`, Docker, and publish.
- Spring Boot 3.3 — [Container Images: Cloud Native Buildpacks](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/cloud-native-buildpacks.html): Spring Boot CNB overview.
- CNB — [How Buildpacks Work](https://buildpacks.io/how-it-works/): builder, buildpacks, and image flow.
- CNB — [Lifecycle Phases](https://buildpacks.io/docs/for-buildpack-authors/concepts/lifecycle-phases/): Analyze, Detect, Restore, Build, Export.
- CNB — [What Is a Builder?](https://buildpacks.io/docs/for-app-developers/concepts/builder/): builder components.
- Paketo — [Building Java Applications](https://paketo.io/docs/howto/java/): Java buildpacks and `BP_JVM_VERSION`.
- Spring Boot — [BootBuildImage Task API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootBuildImage.html): imageName, builder, runImage, publish, caches.

**Conclusion:** The Spring Boot plugin produces an **executable archive**; the CNB **builder** selects buildpacks and runs **Analyze → Detect → Restore → Build → Export**; the **run image** provides the runtime base; and finally you receive an **OCI image** with the appropriate Java runtime and launch process. To confirm success, inspect the **output image**, run a **real container**, and test the application rather than stopping at JAR creation.
