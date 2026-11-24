# Building Images with Dockerfile and Buildpacks from the Same Spring Boot Application

## 1. Goal: One Application, Two Ways to Build an OCI Image

A Spring Boot application can be packaged into a container image in at least two common ways:

- **Dockerfile:** the development team explicitly describes the base image, install/copy instructions, user, port, and entrypoint. Docker BuildKit executes those instructions to produce an image.
- **Cloud Native Buildpacks (CNB):** the development team passes source code or an executable archive to a builder. Buildpacks automatically detect the application type, select matching buildpacks, prepare the runtime, and create an OCI image through a lifecycle.

Both approaches can produce an OCI image running the same application. The differences lie in level of control, how layers are created, how the JRE is chosen, base image update workflows, customizability, and the amount of configuration the development team must maintain.

This article belongs to **Integrated Practice** under **Spring Boot Build Tooling Packaging**. After this lesson, you will be able to:

1. Explain Dockerfile, multi-stage builds, Buildpack, builder, build image, run image, and the CNB lifecycle.
2. Create a Java 17 Spring Boot application with a health check endpoint.
3. Build the executable JAR once, record its SHA-256, and use that exact archive as input for both approaches.
4. Write a Dockerfile running the JAR on JRE 17 as a non-root user.
5. Use the Paketo Buildpacks CLI `pack` to build an image from the already-built executable JAR.
6. Use the Spring Boot Maven Plugin `spring-boot:build-image` to build an image directly from the Maven project.
7. Run both images on different ports and verify the same HTTP response.
8. Inspect image metadata, Java runtime, user, layers, image size, and registry digest.
9. Compare caching, customizability, security, reproducibility, debugging, and maintenance.
10. Choose the right packaging approach and integrate both methods into a controlled CI/CD pipeline.

**Practice stack:** Java `17`, Spring Boot `3.5.16`, Maven, Docker Engine/BuildKit, Cloud Native Buildpacks, Paketo builder, and Pack CLI. The two sample images use these tags:

~~~text
local/image-build-comparison:dockerfile
local/image-build-comparison:buildpacks
~~~

These are local tags for the lab, not registry names for release. Build commands in this article require a running Docker daemon with permission to pull builder/base images.

## 2. Two Approaches Solving the Same Problem

### 2.1. Dockerfile

A Dockerfile is a specification of steps for Docker to execute. For example, a Java image might declare:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY application.jar /app/application.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

The development team decides directly:

- Base image and JRE version.
- Which files enter the image.
- User/group and filesystem permissions.
- Environment variables, port metadata, healthchecks, and entrypoint.
- Required operating system packages.
- Layer splitting and how build steps are cached.

Dockerfile gives direct control. In return, the development team is responsible for updating base images, keeping the runtime secure, managing file permissions, configuring the JVM, and maintaining build instructions.

### 2.2. Cloud Native Buildpacks

Buildpacks automate transforming source code or an application archive into an OCI image. A **builder** is an image containing:

- Ordered buildpacks.
- Lifecycle binaries orchestrating the build.
- A build image serving as the build execution environment.
- Metadata referencing the run image used as the runtime base.

Buildpacks inspect the application, generate a build plan, and contribute the required layers. For Java applications, Paketo can detect Maven/Gradle, executable JARs, or WARs and select the appropriate buildpacks.

The development team can focus on source code, Maven/Gradle metadata, and settings such as `BP_JVM_VERSION`. The builder determines many runtime/layer details according to its buildpack versions and configuration.

### 2.3. There is no single "identical" image produced by both methods

Providing the same input JAR does not give both images the same digest. The two approaches may use:

- Different base OS and JRE patch versions.
- Different image configs, users, entrypoints, and labels.
- Different layer boundaries and compression.
- Different buildpack metadata, SBOMs, and process types.
- Different creation timestamps, architectures, and manifests.

The goal of comparison is to confirm **the same application, the same input JAR, the same runtime contract, and the same smoke test result**. Do not treat two different digests as proof that one image is wrong.

## 3. Understanding the Buildpacks Lifecycle

Cloud Native Buildpacks is not simply a command that auto-generates a Dockerfile. A builder runs a lifecycle to detect, build, and export an image.

Overview flow:

~~~text
Executable JAR / source
          |
          v
      ANALYZE
  reads previous image metadata
          |
          v
       DETECT
  selects matching buildpacks
          |
          v
      RESTORE
  restores cached layers
          |
          v
       BUILD
  executes buildpacks
          |
          v
       EXPORT
  creates OCI image + cache
          |
          v
      RUN IMAGE
  launcher runs process
~~~

| Phase | Role |
| --- | --- |
| Analyze | Reads previous image metadata to determine which layers can be reused |
| Detect | Runs buildpack detection and selects a build plan |
| Restore | Restores previously cached layers |
| Build | Executes selected buildpacks to create/contribute layers |
| Export | Assembles the image and saves metadata/cache |

When running the application, the CNB launcher invokes a process type contributed by a buildpack. For Java executable JARs, Paketo typically provides process types such as `web`, `task`, and `executable-jar`.

A builder may contain many buildpacks; not every buildpack in the builder necessarily contributes a layer to every application. Detection determines which buildpacks fit the project.

## 4. Practice Project Structure

Create the project:

~~~text
image-build-comparison/
  pom.xml
  Dockerfile
  .dockerignore
  src/
    main/
      java/
        demo/
          ImageBuildComparisonApplication.java
  target/
    image-build-comparison-1.0.0.jar
  dist/
    application.jar
~~~

`target/` is the Maven output. `dist/application.jar` is the copy used as the **shared input** for both image creation methods.

This lab builds the JAR once, then:

1. The Dockerfile copies `dist/application.jar` into the runtime image.
2. Pack CLI uses the exact same `dist/application.jar` as the application path so Buildpacks detects the executable JAR.

Thus both methods receive the exact same bytes of the executable archive. The Dockerfile keeps the JAR file in the image filesystem; the Java Buildpack processes the archive into application contents/layers inside the image.

## 5. pom.xml: Spring Boot Java 17

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example.container</groupId>
    <artifactId>image-build-comparison</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Image Build Comparison</name>
    <description>One Spring Boot app packaged by Dockerfile and Buildpacks</description>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                    <image>
                        <name>local/image-build-comparison:buildpacks-maven</name>
                        <builder>paketobuildpacks/builder-noble-java-tiny:latest</builder>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                            <BP_JVM_TYPE>JRE</BP_JVM_TYPE>
                        </env>
                        <publish>false</publish>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation:

- `spring-boot-starter-parent` manages plugin/dependency versions compatible with Spring Boot 3.5.16.
- `java.version` and `maven.compiler.release` set the Java 17 compilation baseline.
- `maven.compiler.target` is also explicitly declared so Buildpacks tooling detects the target Java version through compiler configuration/target metadata.
- `spring-boot-starter-web` provides Spring MVC and an embedded servlet container.
- `image.name` sets the tag for the Spring Boot Maven Plugin build route.
- `builder` selects a specific Paketo builder. The `latest` tag is convenient for labs, though it can change over time.
- `BP_JVM_VERSION=17` tells the Paketo Java Buildpack to install JVM major version 17.
- `BP_JVM_TYPE=JRE` chooses JRE for the runtime image; the buildpack may still use a JDK at build time.
- `publish=false` keeps the image in the local Docker daemon rather than pushing to a registry.

In production, replace mutable builder tags with vetted image digests, pin plugin/buildpack versions, and control JVM patches/providers according to update policy. `BP_JVM_VERSION=17` locks the major release; it does not automatically pin every patch version of the JRE.

## 6. Application.java: A Shared Endpoint for Comparison

Create `src/main/java/demo/ImageBuildComparisonApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ImageBuildComparisonApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ImageBuildComparisonApplication.class, args);
    }

    @GetMapping(value = "/health", produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "image-build-comparison:ok";
    }
}
~~~

The application exposes HTTP endpoint `GET /health` on default port `8080`. Both images must return the exact same response body.

This is a standalone Spring Boot example requiring no database, message broker, or external service. That keeps the focus on image packaging and removes variables from supporting systems.

## 7. Building the JAR Exactly Once

From the project root, run:

~~~bash
mvn -B -ntp clean verify
~~~

Inspect the executable JAR:

~~~bash
test -f target/image-build-comparison-1.0.0.jar
jar tf target/image-build-comparison-1.0.0.jar
~~~

A standard Spring Boot executable JAR contains these entries:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/ImageBuildComparisonApplication.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Check the main class and dependencies:

~~~bash
unzip -l target/image-build-comparison-1.0.0.jar
~~~

If the machine does not have `unzip`, use the JDK's `jar tf`.

Copy the archive to the handoff directory:

Linux/macOS/Git Bash:

~~~bash
mkdir -p dist
cp target/image-build-comparison-1.0.0.jar dist/application.jar
sha256sum dist/application.jar
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force dist
Copy-Item target/image-build-comparison-1.0.0.jar dist/application.jar
Get-FileHash dist/application.jar -Algorithm SHA256
~~~

Save the printed SHA-256 to the build record. Do not fill in an illustrative hash; every build producing real bytes must be measured.

You can run the JAR directly on Java 17 before building images:

~~~bash
java -jar dist/application.jar
~~~

Then call:

~~~bash
curl -fsS http://localhost:8080/health
~~~

Exact response body:

~~~text
image-build-comparison:ok
~~~

The application keeps running to serve requests; press Ctrl+C when you want to stop it.

## 8. Dockerfile: Packaging the JAR into JRE 17

Create `Dockerfile` at the project root:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

COPY --chown=10001:10001 dist/application.jar /app/application.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Explanation of each instruction:

- `FROM` selects the JRE 17 image as the runtime base.
- `WORKDIR` sets the working directory.
- `COPY --chown` copies the built JAR and assigns ownership to UID/GID 10001.
- `USER` runs the process with a numeric non-root identity.
- `EXPOSE` documents the port the application expects to listen on; this instruction does not publish the port on the host.
- `ENTRYPOINT` uses exec form so the JVM becomes the main process and receives signals from the container runtime.

Using numeric UID/GID avoids having to create a named user inside the lab image. The sample application does not need write access to `/app`. If a real application needs to write files, identify the volume/path and grant minimal permissions to that specific directory.

### 8.1. .dockerignore

Create `.dockerignore`:

~~~text
.git
.idea
.vscode
target/
build/
**/*.log
.env
.env.*
~~~

The Dockerfile only needs `dist/application.jar` and the Dockerfile itself. Exclude source build outputs, IDE files, Git history, logs, and environment files from the Docker context.

Do not add `dist/` to the ignore list because that directory holds the archive copied by the Dockerfile. Also never put credentials or `.env` into the image build context.

### 8.2. Building the Dockerfile image

~~~bash
docker build --pull \
  --file Dockerfile \
  --tag local/image-build-comparison:dockerfile \
  .
~~~

Docker Engine executes the Dockerfile instructions and creates the local image. `--pull` requests checking/pulling the base image by tag; with mutable tags, results can change between builds.

In production, pin the base image using an approved digest while maintaining a digest update schedule to receive security fixes. Do not treat a tag like `latest` as proof of an immutable runtime image.

### 8.3. Inspecting the Dockerfile image

~~~bash
docker image inspect local/image-build-comparison:dockerfile
docker history --no-trunc local/image-build-comparison:dockerfile
docker image ls local/image-build-comparison
~~~

Inspect the configured user:

~~~bash
docker image inspect --format '{{.Config.User}}' local/image-build-comparison:dockerfile
~~~

Expected output:

~~~text
10001:10001
~~~

Check the Java runtime:

~~~bash
docker run --rm --entrypoint java local/image-build-comparison:dockerfile -version
~~~

The runtime should report Java 17. The exact patch version and vendor depend on the base image tag/digest pulled at build time.

## 9. Buildpacks: Building an Image from the Exact Same Input JAR

Install Pack CLI and Docker Engine following the official Cloud Native Buildpacks instructions. Verify:

~~~bash
pack version
docker version
docker info
~~~

The Docker daemon must be running and able to pull builder images. For this build route, we supply `dist/application.jar` as the application path.

Run:

~~~bash
pack build local/image-build-comparison:buildpacks \
  --path dist/application.jar \
  --builder paketobuildpacks/builder-noble-java-tiny:latest \
  --env BP_JVM_VERSION=17 \
  --env BP_JVM_TYPE=JRE
~~~

Meaning:

- `pack build` instructs the CNB lifecycle to build an image.
- `--path dist/application.jar` uses the executable JAR built by Maven in section 7.
- `--builder` specifies the builder containing lifecycle/buildpacks and run image metadata.
- `BP_JVM_VERSION=17` requests the Java Buildpack to provide Java 17.
- `BP_JVM_TYPE=JRE` selects JRE for runtime.

The buildpack detects the executable JAR, prepares application contents, contributes JVM/runtime layers, and creates the image. You do not write an `ENTRYPOINT` Dockerfile for this route; the executable JAR buildpack contributes the process type so the launcher starts the application.

### 9.1. Inspecting the Buildpacks image

~~~bash
docker image inspect local/image-build-comparison:buildpacks
docker image ls local/image-build-comparison
~~~

Inspect the configured user:

~~~bash
docker image inspect --format '{{.Config.User}}' local/image-build-comparison:buildpacks
~~~

CNB images are described in Spring Boot Build Image documentation as building/running with non-root users for security reasons. The exact UID/GID depends on the builder/run image; do not assume it is always 10001 like the sample Dockerfile.

Check Java:

~~~bash
docker run --rm --entrypoint java local/image-build-comparison:buildpacks -version
~~~

Java major must be 17 per `BP_JVM_VERSION`. The exact patch version/provider depends on the buildpack release and dependency metadata.

### 9.2. Buildpacks caching

A CNB builder maintains a build cache and launch cache for layers created by buildpacks. The lifecycle can restore layers from a previous image/cache and only rebuild what changed.

Do not clear the cache after every build if the goal is measuring incremental performance. Conversely, when troubleshooting cache issues, you can rebuild with a clean cache using the corresponding option in the builder/Pack or plugin, noting clearly that it is a clean-cache run.

Caching is a build optimization mechanism. It does not replace image tags/digests, registry retention, or prove that an image has undergone security review.

## 10. Direct Buildpacks Integration via Spring Boot Maven Plugin

In addition to Pack CLI, the Spring Boot Maven Plugin provides the `spring-boot:build-image` goal. This goal creates an OCI image using Cloud Native Buildpacks and automatically runs the package lifecycle to ensure the executable archive has been built.

With the POM in section 5, run:

~~~bash
mvn -B -ntp spring-boot:build-image
~~~

The plugin uses the configured image name:

~~~text
local/image-build-comparison:buildpacks-maven
~~~

This integration route is convenient when Maven is the primary build orchestrator and you want to create an image immediately after packaging. The plugin can repackage the application automatically if needed; it is not mandatory to run `repackage` separately before `build-image`.

### 10.1. Differences between the Maven plugin route and Pack route

| Invocation | Application input | Orchestrator |
| --- | --- | --- |
| `mvn spring-boot:build-image` | Maven project and executable archive built in lifecycle | Spring Boot Maven Plugin |
| `pack build --path dist/application.jar` | Pre-built JAR | Pack CLI and CNB lifecycle |
| `docker build -f Dockerfile` | Files COPY'd in Docker context | Dockerfile instructions and BuildKit |

The Maven plugin route is convenient and understands Spring Boot packaging. The Pack route is suitable when you want explicit control over the input archive file or when integrating Buildpacks into a pipeline that does not invoke a Spring Boot Maven goal.

In the main comparison, the Pack route uses the exact `dist/application.jar` file copied by the Dockerfile. The Maven plugin route is an additional integration option; it runs the Maven package lifecycle and produces an archive from the same source project, so you should not assume the JAR bytes from two separate builds are identical.

### 10.2. Docker daemon and registry credentials

Spring Boot `build-image` needs a connection to the Docker daemon. The plugin reads Docker CLI configuration/context or uses configured Docker connection parameters.

If only creating a local image, `publish=false` suffices. When publishing to a registry, configure credentials through a Docker credential helper/secret store or plugin-supported registry configuration fields. Never write usernames/passwords/tokens into a committed POM.

If the builder or run image is in a private registry, provide pull permissions for the builder. Pull permissions for the builder/run image are separate from push permissions for the application image; grant the right permissions for each registry.

### 10.3. build-image-no-fork

If you want to bind image creation into the package lifecycle in the POM, use the `build-image-no-fork` goal:

~~~xml
<execution>
    <id>build-container-image</id>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

`build-image-no-fork` does not fork the lifecycle to automatically ensure package has run. It fits binding into the lifecycle; when invoking directly on the command line, use `spring-boot:build-image`.

Do not bind `build-image` to package in a way that triggers repeated lifecycle forks. Check plugin documentation and execution ordering before automating.

## 11. Running Both Images and Verifying the Same HTTP Contract

Run the Dockerfile image:

~~~bash
docker run --detach \
  --name image-dockerfile \
  --publish 18080:8080 \
  local/image-build-comparison:dockerfile
~~~

Run the Buildpacks image:

~~~bash
docker run --detach \
  --name image-buildpacks \
  --publish 18081:8080 \
  local/image-build-comparison:buildpacks
~~~

Both containers run the same application, but use two different host ports.

Test the endpoints:

~~~bash
curl --fail --silent --show-error --retry 30 \
  --retry-connrefused --retry-delay 1 --retry-max-time 35 \
  http://127.0.0.1:18080/health
~~~

~~~bash
curl --fail --silent --show-error --retry 30 \
  --retry-connrefused --retry-delay 1 --retry-max-time 35 \
  http://127.0.0.1:18081/health
~~~

Both response bodies must be exactly:

~~~text
image-build-comparison:ok
~~~

This is evidence that both images boot the application and serve the same endpoint. It does not prove the images share identical layer contents, digests, JRE patches, or security posture.

### 11.1. Cleaning up containers after the lab

~~~bash
docker rm --force image-dockerfile image-buildpacks
~~~

If container names were already used by an earlier run, verify the exact containers before deleting them. Do not delete unrelated containers in the developer environment.

## 12. Comparing the Two Images Systematically

| Criterion | Dockerfile | Buildpacks |
| --- | --- | --- |
| Configuration style | Explicit via instructions | Builder/buildpacks detect and configure |
| Base OS/runtime | Chosen directly by development team | Determined by builder metadata and run image |
| Java runtime | Selected from base image | Selected via buildpack/provider, e.g., `BP_JVM_VERSION` |
| User | Declared via `USER` | CNB images run non-root by default |
| Entrypoint | Declared via `ENTRYPOINT`/`CMD` | Buildpack contributes process type/launcher |
| Layering | Dockerfile instructions and BuildKit | Component-based buildpack layers |
| Caching | Docker/BuildKit layer cache | CNB build/launch layer caches |
| OS package customization | Very direct in Dockerfile | Usually requires custom builder/run image or buildpack |
| JVM memory/runtime config | Environment/command flags managed by team | Buildpack-provided runtime components and variables available |
| Debugging | Easy to inspect per instruction/layer | Requires understanding builder, lifecycle, buildpack logs/processes |
| Maintenance | Team manages Dockerfile/base image | Team manages builder/buildpack versions and policies |
| Reproducibility | Pin base image digest, tools, and build inputs | Pin builder/run image digest, buildpack/JVM inputs |
| Portability | Docker-compatible tools | CNB-compatible platform/Pack and builder |

Do not conclude that Buildpacks always creates smaller or faster images than Dockerfile. Results depend on the builder, run image, layer strategy, app dependencies, cache state, compression, and platform.

## 13. When to Choose Dockerfile?

Dockerfile is suitable when:

- The application needs specific operating system packages, certificates, or native libraries.
- The team needs fine-grained control over each filesystem layer and entrypoint.
- The runtime has custom hardening rules, UID/GIDs, or specialized filesystem layouts.
- Custom tooling/sidecar assets or specialized startup scripts must be integrated.
- Operations already has standardized Dockerfile templates, policies, and scanner gates.

For example, adding a custom CA certificate or native package into the runtime image: a Dockerfile can specify the exact package and file path. However, you must control the package source, version, checksum, and update cadence.

A Dockerfile does not guarantee image security on its own. A Dockerfile running as root, using an outdated base image, copying secrets, or installing unpinned packages still produces a risky image.

## 14. When to Choose Buildpacks?

Buildpacks is suitable when:

- Applications follow standard Maven/Gradle layouts and common runtimes.
- You want to reduce the number of custom Dockerfiles to maintain.
- You want the builder to auto-detect app types and choose buildpacks.
- You want built-in layer caching, JVM provisioning, and process types.
- Multiple services share a common builder policy and runtime baseline.
- The organization wants to standardize builder/run images and buildpack versions.

Buildpacks is especially helpful when application teams focus on source/POMs while a platform team manages builders and runtime stacks.

If deep customization of OS packages, certificates, or filesystem layouts is needed, you can build custom builder/run images or custom buildpacks. That increases responsibility for maintaining builders and lifecycle compatibility.

## 15. Multi-Stage Dockerfile: Building Source Inside Docker

Section 8 used a pre-built JAR to compare identical input bytes. Another common Dockerfile pattern is building source inside Docker using a **multi-stage build**.

Alternative Dockerfile example:

~~~dockerfile
FROM maven:3.9.11-eclipse-temurin-17 AS build

WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

RUN chmod +x mvnw \
    && ./mvnw -B -ntp dependency:go-offline

COPY src/ src/

RUN ./mvnw -B -ntp clean verify

FROM eclipse-temurin:17-jre-jammy AS runtime

WORKDIR /app

COPY --from=build --chown=10001:10001 \
    /workspace/target/image-build-comparison-1.0.0.jar \
    /app/application.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

In the build stage:

- Maven/JDK and dependencies exist only in the build stage.
- Copy `pom.xml` and the Wrapper first to take advantage of dependency layer caching.
- Copy `src/` after the dependency layer has been created.
- Run `clean verify` to build and test.

In the runtime stage:

- Copy only the executable JAR.
- Use JRE 17.
- Run as a non-root user.
- Exclude Maven, source tree, and compiler from the final image.

Multi-stage builds ensure the final image only receives files copied via COPY from earlier stages. It removes build tools from the runtime image and separates build and runtime environments.

**Note on comparison:** the multi-stage Dockerfile above rebuilds the JAR inside Docker. If Buildpacks also builds from source, the two paths can produce archives with different bytes due to timestamps, toolchains, environments, or build metadata. To compare the exact same binary strictly, use the build-JAR-once approach in section 7 and feed it to the runtime-only Dockerfile and Pack CLI as in sections 8–9.

## 16. Layer Caching and Optimizing Build Time

### 16.1. Dockerfile cache

Docker/BuildKit caches each instruction based on the instruction and relevant inputs. The structure:

~~~dockerfile
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN ./mvnw dependency:go-offline
COPY src/ src/
RUN ./mvnw -B -ntp clean verify
~~~

prevents source code changes from invalidating the dependency-download layer cache if the POM/Wrapper have not changed.

Caching does not replace a dependency repository. When a dependency version changes, the layer must be rebuilt and Maven resolves dependencies according to the POM/settings.

### 16.2. Buildpacks cache

The CNB lifecycle uses analyze/restore to reuse layers from previous images/caches. Buildpacks split JVM, application, and other components into layers based on metadata and buildpack behavior.

An initial build may need to pull the builder, run image, and download the JRE. Subsequent runs can be faster thanks to caching. To benchmark fairly:

1. Run one cold build for both approaches.
2. Run one warm build for both approaches.
3. Use the same host, Docker daemon, architecture, and network.
4. Record whether the cache was kept or cleared.
5. Never compare a cold Docker build against a warm Buildpacks build.

### 16.3. Build cache vs. release artifact

Docker BuildKit cache and CNB layer cache exist to speed up builds. The image tag/digest is the output to deliver and release.

Do not treat a cached layer as the product's identity. Images must be tagged, scanned, have their registry digest recorded, and be linked to a source revision/build record.

## 17. Java Runtime, Port, and Environment Configuration

### 17.1. Pinning the Java major version

Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
~~~

Buildpacks:

~~~text
BP_JVM_VERSION=17
BP_JVM_TYPE=JRE
~~~

Both configurations request Java 17. However, they may use different vendors and patch versions. Check `java -version` inside each image if runtime patch/provider is part of policy.

### 17.2. Runtime environment variables

Spring Boot applications accept configuration via environment variables. For example, changing the port:

~~~bash
docker run --rm \
  --publish 18082:18082 \
  --env SERVER_PORT=18082 \
  local/image-build-comparison:dockerfile
~~~

Spring Boot relaxed binding maps `SERVER_PORT` to `server.port`. For the Buildpacks image, pass the environment variable similarly:

~~~bash
docker run --rm \
  --publish 18083:18083 \
  --env SERVER_PORT=18083 \
  local/image-build-comparison:buildpacks
~~~

`EXPOSE 8080` in the Dockerfile is metadata only. If you change the server port, update host/container port mappings accordingly. Buildpacks does not automatically make a Spring Boot app listen on a different port unless application configuration changes.

### 17.3. JVM flags

The Dockerfile image can receive:

~~~bash
docker run --rm \
  --env JAVA_TOOL_OPTIONS="-XX:+ExitOnOutOfMemoryError" \
  local/image-build-comparison:dockerfile
~~~

Paketo also supports `JAVA_TOOL_OPTIONS` and specialized runtime variables such as `BPL_JVM_HEAD_ROOM` or `BPL_JVM_THREAD_COUNT` for their corresponding runtime components. Check the exact Java Buildpack version and avoid copying `BPL_` variables not supported by the current buildpack.

Do not put secrets into Dockerfile `ENV` instructions or build arguments that might be stored in image history/metadata. Supply secrets through a runtime secret store or orchestrator.

## 18. Security and Supply Chain

### 18.1. Non-root user

The sample Dockerfile uses:

~~~dockerfile
USER 10001:10001
~~~

Buildpacks images produced by the Spring Boot plugin are designed to build/run non-root. Even so, inspect the actual image and test the application in a production-like environment.

Do not grant root just to work around a permission error. Identify the exact file/path requiring write access, then grant minimal permissions or mount a writable volume.

### 18.2. Base image and builder image

Dockerfile requires controlling:

- Base image vendor/tag/digest.
- JRE patch/security updates.
- OS package inventory.
- CA certificates and native libraries.
- User, filesystem permissions, and exposed ports.

Buildpacks requires controlling:

- Builder image and digest.
- Buildpack IDs/versions.
- Build image and run image metadata.
- JVM provider/version and runtime components.
- Registry source, trust, and update cadence.

Buildpacks reduces Dockerfile authoring, but does not eliminate the responsibility of managing builder/run images.

### 18.3. SBOM and vulnerability scanning

Both images must be checked for:

- Application dependencies.
- JRE and OS packages.
- Buildpack/runtime components.
- Native libraries and CA packages.
- License/notice obligations.
- Vulnerability findings and remediation policies.

Buildpacks can emit SBOM metadata for components managed by buildpacks. Dockerfile images can be scanned using the organization's SBOM/image scanning tools. Do not assume a Maven dependency tree describes every package in an OCI image.

Use organization-approved scanners, store results by image digest, and evaluate findings against policy. A passing scan applies only to the exact image digest scanned.

### 18.4. Registry digest and provenance

These identifiers have different meanings:

~~~text
Git commit SHA  : source revision
JAR SHA-256     : executable archive bytes
Image tag       : mutable reference name that can be updated
Image digest    : content identifier of OCI manifest/index
~~~

After pushing to a registry, record the actual digest returned by the registry. `docker image inspect .Id` on a local image is typically the image config ID and should not be confused with the manifest/index digest used for multi-platform deployments.

Link the image digest to the source commit, JAR SHA-256, builder/base image digests, CI run ID, and SBOM. Even if a tag moves, the digest remains the identifier of the published content.

## 19. Reproducibility and Multi-Platform

### 19.1. Why can two builds produce different digests?

Even when source code does not change, the image digest can vary due to:

- Base image/builder tag pointing to a new digest.
- Updated JRE patch version or OS packages.
- Buildpack/plugin version changes.
- Different archive timestamps or image creation dates.
- Different architectures.
- Different layer ordering/compression/image config.
- Different environment variables or build arguments.

To improve reproducibility, pin versions/digests, control build inputs, control network dependencies, and save SBOM/provenance.

### 19.2. Multi-platform images

An image can support `linux/amd64` and `linux/arm64`. Docker Buildx can build/publish multiple platforms; Buildpacks requires builder/run images that support the chosen platform.

The Spring Boot Maven Plugin provides the `imagePlatform` option in supported versions, while Pack/buildpack platform support depends on the builder and CLI. Do not assume a builder supports every architecture.

For multi-platform releases, save the manifest-list/index digest and verify that platform-specific images were created. Run smoke tests on each target architecture; do not test only the amd64 image and assume arm64 behaves identically.

## 20. CI Pipeline for Both Packaging Methods

An overview pipeline:

~~~text
Checkout exact commit
        |
        v
Set up JDK 17 + Maven Wrapper
        |
        v
mvn clean verify
        |
        v
Build executable JAR once
        |
        v
Copy to dist/application.jar
        |
        v
Calculate JAR SHA-256
        |
        +----------------------------+
        |                            |
        v                            v
Dockerfile build                 Pack build
        |                            |
        v                            v
Docker image A                   CNB image B
        |                            |
        +-------------+--------------+
                      |
                      v
          Smoke-test same HTTP endpoint
                      |
                      v
            Scan both image digests
                      |
                      v
             Store SBOM + provenance
                      |
                      v
          Approve and publish exact images
~~~

### 20.1. Sample GitHub Actions job

The workflow snippet below illustrates building and creating both images on a Linux runner equipped with a Docker daemon and Pack CLI:

~~~yaml
name: Compare Dockerfile and Buildpacks

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  image-build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build and verify the application
        run: ./mvnw -B -ntp clean verify

      - name: Prepare the common executable JAR
        shell: bash
        run: |
          set -eu
          mkdir -p dist
          cp target/image-build-comparison-1.0.0.jar dist/application.jar
          sha256sum dist/application.jar > dist/application.jar.sha256

      - name: Build Dockerfile image
        run: |
          docker build --file Dockerfile \
            --tag local/image-build-comparison:dockerfile .

      - name: Build Buildpacks image
        run: |
          pack build local/image-build-comparison:buildpacks \
            --path dist/application.jar \
            --builder paketobuildpacks/builder-noble-java-tiny:latest \
            --env BP_JVM_VERSION=17 \
            --env BP_JVM_TYPE=JRE

      - name: Verify image metadata
        run: |
          docker image inspect local/image-build-comparison:dockerfile
          docker image inspect local/image-build-comparison:buildpacks
~~~

The runner must have Pack CLI installed and access to a Docker daemon before the `pack build` step. In production, pin action versions by commit SHA per policy, pin builder/base image digests, scan images, and run smoke tests on both tags.

### 20.2. Release gate

Publish only when:

- The JAR passed Maven verify and smoke tests.
- Both images were built from the same JAR SHA-256 per the lab design.
- Both containers return the same response from `GET /health`.
- Java major/runtime, user, and exposed ports comply with policy.
- Image scans and SBOMs are archived by digest.
- Builder/base image digests and source commit are recorded.
- An authorized approver has signed off on the exact image digests.

Never rebuild an image after scanning/approval and reuse old scan results for a new digest.

## 21. Common Errors and Troubleshooting

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `docker build` reports `dist/application.jar` not found | JAR not copied to dist or .dockerignore excluded it | Check file before build and ignore rules |
| `pack build` does not detect Java app | Wrong app path, file is not an executable JAR, or manifest missing | Inspect JAR with `jar tf` and check manifest |
| Buildpacks cannot find Docker daemon | Docker Engine not running or wrong context/permissions | Check `docker info`, Docker context, and daemon permissions |
| Builder image pull fails | Registry/network/credentials or wrong tag | Check builder reference, registry auth, and network |
| Spring Boot Maven `build-image` runs package but produces no image | Docker daemon or builder phase failed | Read lifecycle logs and check Docker daemon connection |
| Image builds successfully but container exits immediately | Entrypoint/process type or app startup failure | Check `docker logs` and inspect command/user |
| Dockerfile image runs but Buildpacks image fails | Different JRE/runtime config/process type | Check buildpack logs, `BP_JVM_VERSION`, image user, and process |
| Buildpacks image runs but Dockerfile image gets permission denied | File ownership or unsuitable user | Check `COPY --chown`, writable paths, and UID/GID |
| Endpoint does not respond | Wrong port mapping or app binds to another port | Check `SERVER_PORT`, `EXPOSE`, and `docker port` |
| Docker image has wrong Java major version | Base image tag/runtime differs from expectation | Run `java -version` in image and pin digest |
| Buildpacks image uses unexpected JRE patch | Buildpack/provider pulled a newer patch | Inspect SBOM/JVM metadata and pin builder/runtime inputs |
| Dockerfile image larger than expected | Base image/build tools or extra files copied | Use multi-stage build, .dockerignore, and runtime base |
| Second Buildpacks build is not faster | Cache not retained or image/cache identity changed | Check CNB cache volumes, builder, and image tag |
| Two image digests differ | Layer/config/base image/created metadata differ | Normal; compare shared input JAR and runtime contract |
| Local Docker build works but CI fails | Runner lacks Docker daemon/Pack or permissions | Provision runner and daemon access |
| Image works locally but fails in production | Different environment, architecture, registry digest, or secrets | Compare image digest, platform, runtime env, and logs |
| Maven plugin build-image picks wrong archive | Multi-module or multiple JARs in target | Select exact module/classifier/source archive |
| Multi-arch pull gets different image than local | Platform manifest selects image by architecture | Check manifest/index and platform-specific tests |

### 21.1. Quick investigation commands

~~~bash
docker version
docker info
pack version
docker image ls local/image-build-comparison
docker image inspect local/image-build-comparison:dockerfile
docker image inspect local/image-build-comparison:buildpacks
docker logs image-dockerfile
docker logs image-buildpacks
docker port image-dockerfile
docker port image-buildpacks
~~~

Inspect input file:

~~~bash
sha256sum dist/application.jar
jar tf dist/application.jar
~~~

If an error occurs in only one approach, preserve builder logs/Docker build logs from that exact build and compare runtime configuration before changing source code.

## 22. Pre-Selection and Image Release Checklist

### Application artifact

- [ ] Same source commit and Maven coordinates.
- [ ] JDK/compiler release pinned to runtime baseline.
- [ ] `mvn clean verify` succeeds.
- [ ] Executable JAR has valid manifest/Boot loader/dependencies.
- [ ] JAR SHA-256 saved in build record.
- [ ] Both methods receive the exact same input archive in the comparison.

### Dockerfile

- [ ] Base image/JRE version controlled.
- [ ] Final stage contains only required runtime files.
- [ ] User is non-root.
- [ ] `COPY` does not copy secrets or leftover build files into the image.
- [ ] Entrypoint uses exec form.
- [ ] Port mapping and runtime environment verified.

### Buildpacks

- [ ] Builder image/digest vetted.
- [ ] Buildpacks and JVM provider/version appropriate.
- [ ] `BP_JVM_VERSION` set to the right major version.
- [ ] Docker daemon and registry access operational.
- [ ] Run image aligns with builder metadata.
- [ ] Image runs as a non-root user.
- [ ] Cache and SBOM managed according to policy.

### Release

- [ ] Both images pass the same HTTP smoke tests.
- [ ] Image scan and SBOM linked to digest.
- [ ] Source commit, JAR SHA-256, and builder/base image digests archived.
- [ ] Release tag and registry digest recorded.
- [ ] Do not use mutable cache tags as deployment identity.
- [ ] Deployment uses approved digest.

## 23. Self-Check Questions

**A. Do both Dockerfile and Buildpacks produce OCI images?**

Yes. Dockerfile uses Docker build instructions; Buildpacks uses a builder/lifecycle to build images. Both can produce OCI-compliant images.

**B. Why does this lab build the JAR once before building the two images?**

So both approaches receive the exact same bytes of the executable JAR. If each approach builds source independently, archives may differ due to toolchains, timestamps, or environments.

**C. Does Buildpacks require a Docker daemon?**

In this lab using Pack CLI and the Spring Boot Maven Plugin, a Docker-compatible daemon is needed to build images. Some other CNB-implementing platforms have their own daemon/registry integrations.

**D. Does `BP_JVM_VERSION=17` pin the exact JRE patch?**

No. It selects Java major 17. The specific JRE patch/provider depends on buildpack versions and dependency metadata; inspect SBOM/runtime and pin builder inputs according to policy.

**E. Does Buildpacks run as root at runtime?**

CNB images built by Spring Boot build-image are designed to run non-root. You should still inspect the image and verify the actual user.

**F. Do both images have the same digest when using the same JAR?**

No. Base image, JRE, layer boundaries, image config, metadata, and compression may differ. Compare the input JAR hash and behavior instead of expecting identical digests.

**G. When should `build-image-no-fork` be used?**

When binding the image build goal to a Maven lifecycle phase. When invoking directly from the command line, use `spring-boot:build-image`.

**H. Is a multi-stage Dockerfile still useful if using Buildpacks?**

Yes, if a project needs explicit control over build/runtime stages, OS packages, or custom runtimes. Buildpacks and Dockerfile are two packaging options selectable based on operational requirements.

**I. Does `EXPOSE 8080` make the container automatically publish the port?**

No. It is image metadata. You must map the port with `docker run -p hostPort:containerPort` or configure it appropriately in the orchestrator.

**J. If scanning an image tag passes, can that tag be deployed forever?**

No. A tag can later point to a new digest. Record and deploy the scanned/approved digest, and re-scan whenever the image changes.

## 24. Official References

- Spring Boot 3.5.16 — Packaging OCI Images / Maven `build-image`: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Spring Boot 3.5 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Docker — Multi-stage builds: https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/
- Docker — Build best practices: https://docs.docker.com/build/building/best-practices/
- Cloud Native Buildpacks — What is a builder?: https://buildpacks.io/docs/for-app-developers/concepts/builder/
- Cloud Native Buildpacks — Lifecycle: https://buildpacks.io/docs/for-platform-operators/concepts/lifecycle/
- Paketo — Build Java applications with Paketo Buildpacks: https://paketo.io/docs/howto/java/
- Paketo — Java Buildpack reference: https://paketo.io/docs/reference/java-reference/
- Paketo — Configure Buildpacks: https://paketo.io/docs/howto/configuration/
- Paketo — Executable JAR Buildpack: https://github.com/paketo-buildpacks/executable-jar
- Pack CLI — Install and usage: https://buildpacks.io/docs/tools/pack/

**Remember:** Dockerfile lets the development team directly specify the runtime image; Buildpacks uses a builder and lifecycle to detect the application, prepare the runtime, and build layers. Both can package the same Spring Boot application. Build a verified JAR once, pass the exact same bytes as input, run the same smoke tests, and store each image's digest/SBOM/provenance separately. Choose the method based on the runtime control, customizability, and operational capability your product requires.