# Building Images with Maven spring-boot:build-image

## 1. Creating an OCI Image Without Writing a Dockerfile

When a Spring Boot project needs to run in a container, the familiar approach is to write a Dockerfile, choose a Java base image, copy the JAR into the image, and declare an ENTRYPOINT. That approach remains valid when a team needs direct control over individual OS installation commands, directories, file permissions, or runtime packages.

Another option is **Cloud Native Buildpacks (CNB)**. The Spring Boot Maven Plugin integrates CNB through the goal:

~~~bash
./mvnw spring-boot:build-image
~~~

This goal analyzes the application, selects suitable buildpacks, builds a runtime image, and exports an **OCI container image** to the Docker daemon. With the default builder documented in Spring Boot 3.5.16, the process uses the Paketo ecosystem. You can build and run an image without writing a Dockerfile for typical Java applications.

The key point is that **spring-boot:build-image does not simply rename a JAR into an image**. It orchestrates a process involving a builder, buildpacks, a build-time base image, a run image, a lifecycle, dependency layers, and caches. Those components determine which JDK/JRE is installed, how the application is packaged, which process will run, and which filesystem layers the final image contains.

This lesson belongs to the parent topic **Cloud Native Buildpacks**. We will clarify CNB, builder, and buildpack; configure the Maven goal; create a buildable Java 17 application; run the image; configure Java/buildpacks; understand Docker daemon, cache, and registry; and finally cover common troubleshooting and a CI checklist.

## 2. What Are Cloud Native Buildpacks?

**Cloud Native Buildpacks** is a standard and tool ecosystem for turning source code or an application artifact into an OCI image following reusable rules. Instead of authoring Dockerfile steps for every language, the platform invokes specialized **buildpacks** to detect the application and contribute required components.

A buildpack can:
- Detect the application type or input conditions it supports.
- Supply the required JDK/JRE, runtime, server, or libraries.
- Prepare the artifact and launch environment.
- Create cacheable and reusable dependency layers.
- Record metadata, process types, and a Software Bill of Materials (SBOM) depending on the buildpack's capabilities.

For Java, buildpacks can recognize executable JARs, Maven/Gradle projects, or other Java applications, and select an appropriate packaging strategy. The Spring Boot Maven Plugin translates Maven project settings to the CNB platform without needing to invoke the `pack` command separately for common cases.

### 2.1. Comparing Dockerfile and Buildpacks

| Criterion | Dockerfile | Cloud Native Buildpacks |
| --- | --- | --- |
| Input | Dockerfile + build context | Source or application artifact + builder/buildpacks |
| How build steps are decided | Author specifies instructions | Buildpacks detect and execute build steps |
| Base image | `FROM` chosen by author | Builder provides build image; builder metadata specifies run image |
| Java runtime | Author installs/copies JRE or JDK | Java buildpack contributes suitable JDK/JRE |
| Customization | Very direct via Dockerfile | Via builder, buildpacks, environment, bindings, project config |
| Image layers | Per Dockerfile instructions | Per dependency/application layers exported by buildpacks |
| Best suited for | Needing control over OS packages and bespoke flows | Wanting a standardized process with automatic app and runtime detection |

Both approaches produce OCI images and can be deployed via Docker, Kubernetes, or compatible container platforms. Buildpacks do not eliminate the need to understand images, registries, networking, and runtime behavior; they automate many image-preparation steps.

### 2.2. When Should You Use `spring-boot:build-image`?

Usually suitable when:
- The application is a Spring Boot executable JAR/WAR following a plugin-supported layout.
- You want a Java runtime and non-root user configured by buildpacks.
- You want dependency caching and OCI layers without writing a Dockerfile.
- The team wants to standardize image builds across multiple Java services.
- Approved builders/buildpacks can be controlled and updated according to policy.

A Dockerfile or custom builder may fit better when the application requires specific OS packages, custom init/system tools, running multiple processes outside the buildpack model, or explicit declaration of every image instruction. Some requirements can still be met using a custom buildpack or builder extension.

## 3. Distinguishing Buildpack, Builder Image, Build Image, and Run Image

These four concepts are often loosely lumped together as “buildpack image”, yet they serve distinct roles.

### 3.1. Buildpack

A **buildpack** is a component performing a specific job. For instance, a Java buildpack can detect a Java application, supply a JDK/JRE, configure the classpath or launch process, and prepare runtime layers.

A builder can contain multiple buildpacks in order. Each buildpack is asked whether it supports the application during the detect phase. Selected buildpacks run during the build phase.

### 3.2. Builder Image

A **builder** is an OCI image used to execute the build process. Per CNB, a builder contains:
- An ordered list of buildpacks and groups.
- **Build-time base image**: the environment where the lifecycle/buildpacks run, which may include build tools.
- CNB **lifecycle binaries** that orchestrate the phases.
- Metadata referencing the **run image** used as the foundation for the final image.

The builder is the build environment, not by default the final image running the application. JDK, compilers, and tooling may exist in the build-time image, while the runtime image is chosen separately.

### 3.3. Run Image

The **run image** is the base image for the application at runtime. It supplies the operating system and underlying runtime components. Builder metadata designates a compatible run image; the Spring Boot Plugin uses that image by default unless overridden.

Do not choose an arbitrary run image just because it includes Java. The run image must be compatible with the builder/stack used by the buildpacks. When changing either the builder or run image, verify compatibility and update policies for the pair.

### 3.4. Final Image

After buildpacks contribute the application, JRE, and required layers, the lifecycle exports an **OCI image**. That image is the output you run with Docker or push to a registry.

~~~text
Maven project
     |
     v
spring-boot:build-image
     |
     v
CNB platform + Builder
     |
     +--> Build-time base image
     +--> Lifecycle
     +--> Ordered buildpacks
     +--> Run image reference
                |
                v
        Analyze / Detect / Restore
                |
                v
               Build
                |
                v
              Export
                |
                v
          OCI application image
~~~

The **builder image** creates the image. The **run image** serves as the base of the final image. The **application image** is what the container runs.

## 4. How Does the CNB Lifecycle Proceed?

The Spring Boot Maven Plugin orchestrates the CNB lifecycle through the Docker daemon. Conceptually, the main phases are:

| Phase | Action Performed | Result |
| --- | --- | --- |
| **Analyze** | Reads previous image metadata and cache info | Identifies existing layers eligible for reuse |
| **Detect** | Asks buildpacks whether they recognize the app and picks a matching group | Build plan |
| **Restore** | Restores dependency/application layers from previous cache | Cached layers ready |
| **Build** | Runs the selected buildpacks | Dependencies, app output, metadata, and layers |
| **Export** | Assembles layers and metadata to produce the image | OCI image and updated cache |

The CNB lifecycle includes additional components/details depending on Platform API and lifecycle version. The table above outlines the flow of a typical build.

### 4.1. Analyze and Cache

When a previous image exists, the lifecycle reads metadata and checks layers to determine what has not changed. The Spring Boot Plugin stores cache in Docker named volumes by default; caching reduces the work of rebuilding reusable dependencies or content.

### 4.2. Detect

Buildpacks inspect the application. With a Spring Boot Maven project, the Java buildpack can recognize the project structure and executable archive. If no buildpack detects the application, detection fails and no valid image is exported.

A detect error can indicate:
- Wrong builder selected.
- Builder lacks a suitable buildpack.
- Application artifact was not created or is not in the source directory used by the plugin.
- Project has a layout/packaging unsupported by the current buildpacks.

### 4.3. Build and Export

Buildpacks supply runtime components, process the application artifact, and generate layers. Export builds the image on top of the run image, writes metadata/process definitions, and updates cache. Build output can contain multiple filesystem layers rather than a single layer holding the entire application.

**Buildpacks do not automatically guarantee the smallest image or fastest startup for every application.** Results depend on the builder, buildpack versions, JRE provider, dependencies, application layout, and runtime configuration.

## 5. What Does `spring-boot:build-image` Do?

The **spring-boot:build-image** goal of the Spring Boot Maven Plugin 3.5.16:
- Forks the Maven lifecycle to ensure the **package** phase has run.
- Creates the required executable archive if not yet present.
- Passes the application to the CNB builder.
- Runs buildpacks to generate an OCI image.
- Creates the image locally in the Docker daemon by default.
- Can publish the image to a registry when the publish option is enabled.

**It is not mandatory to run `spring-boot:repackage` separately beforehand** for `build-image` to have an executable archive; the goal can produce the required archive and apply the corresponding packaging settings.

### 5.1. Simplest Command

At the root directory of a project with Maven Wrapper:

~~~bash
./mvnw spring-boot:build-image
~~~

If using a locally installed Maven:

~~~bash
mvn spring-boot:build-image
~~~

On Windows:

~~~powershell
.\mvnw.cmd spring-boot:build-image
~~~

The goal runs the package lifecycle and then builds the image. If the build succeeds, the image typically receives a default name derived from the Maven project's **artifactId** and **version**:

~~~text
docker.io/library/<artifactId>:<version>
~~~

For example, a project with artifactId **cnb-demo** and version **1.0.0** gets the default name:

~~~text
docker.io/library/cnb-demo:1.0.0
~~~

You can inspect the image with:

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0
~~~

The image is created in the Docker daemon the plugin connects to; it is not pushed to a registry by default.

### 5.2. Difference Between `build-image` and `build-image-no-fork`

Both goals share a similar purpose, but participate in the Maven lifecycle differently:

| Goal | How Invoked | Meaning |
| --- | --- | --- |
| **build-image** | Called directly from the command line | Forks the lifecycle to ensure `package` has run |
| **build-image-no-fork** | Used in a plugin execution bound to a lifecycle phase | Does not fork the lifecycle again |

Use **build-image** for direct CLI commands:

~~~bash
./mvnw spring-boot:build-image
~~~

If you want the image to build automatically during `mvn package`, bind **build-image-no-fork**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>build-image-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Do not bind **build-image** directly into the `package` phase where it forks repeatedly. The **build-image-no-fork** goal is designed for lifecycle execution; for direct command-line invocation, use **build-image**.

## 6. Prerequisite: Docker Daemon

The goal needs access to a Docker daemon to:
- Pull builder and run images.
- Create the builder container and volumes.
- Access cache.
- Export the image to the image store or publish to a registry.

Before building, check:

~~~bash
docker version
docker info
docker context ls
docker context show
~~~

If the Docker CLI itself cannot connect to the daemon, fix the Docker Engine/Desktop/Podman context first. If the Docker CLI works but the Maven plugin cannot connect, check the context and environment variables received by the Maven process.

### 6.1. Docker Context and Environment Variables

The Spring Boot Plugin reads Docker CLI configuration to determine the current context. Common variables:

| Variable | Effect |
| --- | --- |
| **DOCKER_CONFIG** | Docker CLI config directory; defaults usually to `.docker` in home |
| **DOCKER_CONTEXT** | Name of Docker context to use; takes precedence over `DOCKER_HOST` |
| **DOCKER_HOST** | Docker daemon URL, e.g. `tcp://host:2376` |
| **DOCKER_TLS_VERIFY** | Enables TLS verification when set to `1` |
| **DOCKER_CERT_PATH** | Path to certificates when using TLS |

Example when selecting an existing Docker context:

~~~bash
docker context use desktop-linux
./mvnw spring-boot:build-image
~~~

Context names depend on the machine; check with **`docker context ls`**, and do not assume every machine has `desktop-linux`.

If using a remote daemon over TLS, configure the host and certificates properly per policy. Do not expose an unauthenticated Docker TCP socket to a public network; control over a Docker daemon generally equates to high host privileges.

### 6.2. Configuring Docker Host in the POM

The plugin also supports Docker parameters:

~~~xml
<docker>
    <host>tcp://docker-builder.internal:2376</host>
    <tlsVerify>true</tlsVerify>
    <certPath>/secure/docker-certs</certPath>
</docker>
~~~

This is an **illustrative configuration snippet**, not a live host or pre-existing certificate. The cert directory must exist on the machine running Maven and be protected per policy. If Docker context is already configured properly, you do not need to redeclare `host` in the POM.

### 6.3. Docker Desktop, Podman, Colima

Spring Boot 3.5.16 provides guidance on connecting to environments such as Docker Engine, minikube, Podman, and Colima. For these environments, the key is ensuring the plugin receives the right daemon endpoint/socket.

For example, on Linux/macOS with a Colima Docker context, you can retrieve the endpoint per Colima CLI docs and assign it to `DOCKER_HOST`. The exact socket path depends on the user and machine setup; do not hardcode a socket path from another machine.

With Podman, the plugin can be configured via the host socket and `bindHostToBuilder`. Confirm that the daemon socket is enabled and the builder container can reach necessary network services.

## 7. Hands-On Example: Spring Boot Java 17

We will create a small web application to build an image and test it after running. The example uses **Java 17** and **Spring Boot 3.5.16**; this is an illustrative combination, not an immutable recommendation for every new project.

### 7.1. Project Structure

~~~text
cnb-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/cnb/
    │   │   ├── CnbDemoApplication.java
    │   │   └── HelloController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/cnb/
            └── HelloControllerTest.java
~~~

The Maven Wrapper must be generated via Spring Initializr or the Maven Wrapper plugin. The files **mvnw**, **mvnw.cmd**, and **.mvn/wrapper** should be committed with the project so machines use the same Maven distribution.

### 7.2. Main Class

File **src/main/java/com/example/cnb/CnbDemoApplication.java**:

~~~java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbDemoApplication.class, args);
    }
}
~~~

### 7.3. Controller

File **src/main/java/com/example/cnb/HelloController.java**:

~~~java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello-from-buildpacks";
    }
}
~~~

Once the application starts and a `GET /hello` request succeeds, the exact response body is:

~~~text
hello-from-buildpacks
~~~

### 7.4. application.properties

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=cnb-demo
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
~~~

This configuration sets the HTTP port to 8080 and enables Spring Boot health probe groups. The application can be checked via **/actuator/health/readiness** once the Actuator dependency is added.

### 7.5. Controller Test

File **src/test/java/com/example/cnb/HelloControllerTest.java**:

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
class HelloControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void helloReturnsExpectedText() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("hello-from-buildpacks"));
    }
}
~~~

The test verifies the Spring context and controller in the Maven test environment. You still need to run the real image afterward to check the runtime JRE, process, port, and container networking.

## 8. Complete POM to Build an Image with Buildpacks

File **pom.xml**:

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
    <artifactId>cnb-demo</artifactId>
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
                    <image>
                        <name>docker.io/library/cnb-demo:${project.version}</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                    <createdDate>2026-01-01T00:00:00Z</createdDate>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation:
- **spring-boot-starter-parent** manages dependency/plugin versions and integrates appropriate executions.
- **java.version=17** sets Java compatibility for compilation.
- **spring-boot-starter-web** supplies Spring MVC and the embedded server.
- **spring-boot-starter-actuator** supplies health endpoints.
- **spring-boot-starter-test** is used only for tests.
- **spring-boot-maven-plugin** provides the `build-image` goal.
- **image.name** sets an explicit image reference matching the artifact version.
- **BP_JVM_VERSION=17** asks the Paketo Java buildpack to use Java major version 17.
- **createdDate** is a fixed metadata timestamp for the reproducible build example; choose a value matching your actual release policy.

In this POM, no Dockerfile is needed. The default builder for Spring Boot 3.5.16 is **paketobuildpacks/builder-noble-java-tiny:latest**; builder metadata supplies a compatible run image. For release environments, choose an approved builder tag/digest and manage updates rather than relying indefinitely on the mutable `latest` tag.

**Note on `createdDate`:** a fixed value makes image metadata more reproducible, but is not sufficient to guarantee the entire image is byte-for-byte identical. You must also control builder/buildpack versions, run image, dependencies, platform, and all other sources of build metadata.

## 9. Building and Running the Image for the First Time

From the project root directory:

~~~bash
./mvnw -B -ntp clean verify
./mvnw spring-boot:build-image
~~~

The second command runs the package lifecycle via goal semantics. You can invoke just a single command directly:

~~~bash
./mvnw spring-boot:build-image
~~~

When the build completes, inspect the local image:

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0
~~~

Run the container:

~~~bash
docker run --rm --name cnb-demo   -p 127.0.0.1:18080:8080   cnb-demo:1.0.0
~~~

From another terminal:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/hello
~~~

Expected body:

~~~text
hello-from-buildpacks
~~~

Check readiness:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health/readiness
~~~

Once the application is ready and no health indicator fails, the response is typically:

~~~json
{"status":"UP"}
~~~

**`docker run`** and HTTP responses are two distinct steps. If the container does not start or the endpoint fails to respond, check logs, port mapping, and runtime configuration before concluding that buildpacks built a bad image.

### 9.1. Running the Container Detached to Inspect Logs

~~~bash
docker run -d --name cnb-demo-test   -p 127.0.0.1:18080:8080   cnb-demo:1.0.0

docker ps -a --filter "name=cnb-demo-test"
docker logs --tail 80 cnb-demo-test
~~~

After testing:

~~~bash
docker stop --time 15 cnb-demo-test
docker rm cnb-demo-test
~~~

Only remove the test container you created. Never run bulk commands to delete all containers/images/caches on a shared Docker daemon.

## 10. Customizing Builder and Run Image

Spring Boot 3.5.16 uses the default builder:

~~~text
paketobuildpacks/builder-noble-java-tiny:latest
~~~

You can select a different builder via the POM:

~~~xml
<image>
    <builder>paketobuildpacks/builder-noble-java-tiny:latest</builder>
</image>
~~~

Or via the command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.builder=paketobuildpacks/builder-noble-java-tiny:latest
~~~

The **latest** tag can change across publishes. In CI/releases, pin a specific version tag or approved digest, while controlling the corresponding run image.

### 10.1. Run Image

Builder metadata specifies the default run image. If you need to replace the run image, configure:

~~~xml
<image>
    <builder>registry.example.com/platform/java-builder:1.2.0</builder>
    <runImage>registry.example.com/platform/java-run:1.2.0</runImage>
</image>
~~~

The registry name and versions here are examples. The run image must be compatible with the builder stack/API and the components created by buildpacks. Do not swap in an arbitrary base image and expect application layers to still run.

You can override via the command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.builder=registry.example.com/platform/java-builder:1.2.0   -Dspring-boot.build-image.runImage=registry.example.com/platform/java-run:1.2.0
~~~

### 10.2. Is the Builder a Runtime Image?

No. The builder image contains the environment to run buildpacks and the lifecycle. The run image is the base for the application at runtime. The final image is exported from the run image plus the layers contributed by buildpacks.

If the builder is too old, buildpacks may not understand current source/artifacts. If the run image is incompatible, the image may build yet fail at runtime due to missing OS libraries or ABI mismatches. Update builder/run images as a pair and run smoke tests after changes.

## 11. Selecting Platform and Pull Policy

### 11.1. `imagePlatform`

Since Spring Boot 3.4, the Spring Boot Maven Plugin supports configuring the platform for builder, run, and buildpack images:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imagePlatform=linux/amd64
~~~

Some example values:

~~~text
linux/amd64
linux/arm64
linux/arm/v7
~~~

The platform must be supported by the builder. Choose the platform matching where the image will run. If building on an ARM laptop while production is AMD64, configure the platform explicitly to avoid producing an image for the wrong architecture.

### 11.2. `pullPolicy`

The Spring Boot Plugin supports three choices:

| Value | Behavior |
| --- | --- |
| **ALWAYS** | Always check/pull builder and run images from the registry |
| **IF_NOT_PRESENT** | Only pull when the image is not present locally |
| **NEVER** | Do not pull; requires all needed images to be present locally |

The default documented in Spring Boot 3.5.16 is **ALWAYS**. This fetches the newest image for a tag, but can slow down builds or reduce reproducibility if the tag is mutable.

Example using local cache when builder/run images are pre-staged:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.pullPolicy=IF_NOT_PRESENT
~~~

**NEVER** should only be used when you are certain all required builder/run/buildpack images already exist in the daemon and need no pulling. If an image is missing, the build will fail.

## 12. Setting Image Name and Tags

The default image name is derived from Maven **artifactId** and **version**, for example:

~~~text
docker.io/library/cnb-demo:1.0.0
~~~

You can set the name in the POM:

~~~xml
<image>
    <name>registry.example.com/team/cnb-demo:${project.version}</name>
</image>
~~~

Or via the command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-demo:1.0.0
~~~

Image references have the form:

~~~text
[registry-host[:port]/][namespace/]image-name[:tag]
~~~

If no registry is specified, Docker Hub is normally assumed as the default registry. If no path is specified, the default namespace is usually `library`; if no tag is specified, the default tag is `latest`.

### 12.1. Additional Tags

The plugin supports adding one or more full image references as tags. When configuring multiple tags, provide full registry/path/name/tag values in the documented format. Avoid using the `latest` tag as the sole identifier for a release; maintain clear version/commit tags for traceability.

A tag is only a reference name. The same image can carry multiple tags; changing tags does not alter the image bytes.

### 12.2. Confirming the Local Image

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0 --format '{{.Id}}'
docker image inspect cnb-demo:1.0.0 --format '{{.Os}}/{{.Architecture}}'
docker image inspect cnb-demo:1.0.0 --format '{{.Config.User}}'
docker image history cnb-demo:1.0.0
~~~

Spring Boot documentation states that images are built and run using a **non-root user** for security reasons. Inspect the actual image configuration to verify the user and process; do not assume every custom builder preserves this policy.

## 13. Publishing Images to a Registry

By default:

~~~text
publish = false
~~~

The goal creates a local image without automatically pushing it. To publish, you can use the command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-demo:1.0.0   -Dspring-boot.build-image.publish=true
~~~

When publish is enabled, the target registry is determined by the registry portion of the image name. Verify the tag/repository carefully before enabling publish in a pipeline.

### 13.1. Logging In to a Registry

If the registry uses a Docker CLI credential helper or credential store, the plugin can read the existing Docker configuration (typically in `.docker`). For example:

~~~bash
docker login registry.example.com
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-demo:1.0.0   -Dspring-boot.build-image.publish=true
~~~

Do not place real passwords into shell history or committed POMs. In CI, use a credential store/secret injection according to the runner's policy.

### 13.2. Two Types of Registry Credentials

Distinguish between:
- **builderRegistry**: authenticates when pulling the builder image or run image from a private registry.
- **publishRegistry**: authenticates when pushing the application image created by buildpacks.

They serve two separate flows. If the builder/run image resides in a private registry, configure `builderRegistry`; if the application image publishes to a private registry, configure `publishRegistry`. An appropriate `docker login` can also supply credentials via Docker config.

Example configuration structure, using CI environment variables instead of real credentials:

~~~xml
<docker>
    <builderRegistry>
        <username>${env.BUILDER_REGISTRY_USER}</username>
        <password>${env.BUILDER_REGISTRY_PASSWORD}</password>
        <url>https://registry.example.com</url>
    </builderRegistry>
    <publishRegistry>
        <username>${env.APP_REGISTRY_USER}</username>
        <password>${env.APP_REGISTRY_PASSWORD}</password>
        <url>https://registry.example.com</url>
    </publishRegistry>
</docker>
~~~

This is an illustrative configuration. Verify the exact property/environment variable names and authentication scheme of your organization's registry. Do not print credentials in Maven logs; restrict token scopes by repository and expiration.

### 13.3. Verifying After Publish

After a successful push, use registry tooling or `docker pull` on an authorized machine/runner:

~~~bash
docker pull registry.example.com/team/cnb-demo:1.0.0
docker image inspect registry.example.com/team/cnb-demo:1.0.0
~~~

Build success and push success are two separate outcomes. In release evidence, record the image digest, source commit, builder/buildpack versions, and registry reference. Tags can be overwritten; a digest is a more suitable content identifier for finalized deployments.

## 14. Configuring the Java Buildpack

With the Paketo Java buildpack, an important build-time variable is:

~~~text
BP_JVM_VERSION
~~~

Example in the POM:

~~~xml
<image>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
    </env>
</image>
~~~

Or via the command line when environment variables are configured via POM/properties appropriately. When the Spring Boot Plugin uses the default Paketo builder, the plugin can read the Maven compiler's Java compatibility and instruct the buildpack to install the matching Java version. Setting `BP_JVM_VERSION` explicitly makes intent clear and avoids relying on ambiguous compiler configuration.

### 14.1. JDK and JRE

By default, the Paketo Java buildpack typically uses a JDK at build time and a JRE at runtime when compatible dependencies are available. The variable:

~~~text
BP_JVM_TYPE
~~~

can control the type of JVM the buildpack installs. Think carefully before requesting a JDK in the runtime image: a JDK is larger and contains more tools than the application needs.

Some buildpacks/providers support creating a minimal JRE via JLink. The variable:

~~~text
BP_JVM_JLINK_ENABLED=true
~~~

can enable that mechanism when supported by the provider/version. Do not enable it just to shrink size without verifying which Java modules the application or libraries require.

### 14.2. Runtime JVM Options

At runtime, the Paketo Java buildpack provides configuration variables such as:
- **BPL_JVM_HEAD_ROOM**
- **BPL_JVM_LOADED_CLASS_COUNT**
- **BPL_JVM_THREAD_COUNT**
- **BPL_JVM_CLASS_ADJUSTMENT**
- **JAVA_TOOL_OPTIONS**

The `BPL` variables tune runtime components supplied by the buildpack, such as the JVM memory calculator. `JAVA_TOOL_OPTIONS` is the standard Java mechanism for passing JVM flags.

Example running the container:

~~~bash
docker run --rm   -e JAVA_TOOL_OPTIONS="-Dserver.port=8081"   -p 8081:8081   cnb-demo:1.0.0
~~~

This example changes the server port via a system property. If the application has another `server.port` setting or security requirements, re-verify the endpoint and port mapping.

### 14.3. Build-Time and Runtime Environments Are Not the Same

| Group | Prefix/Variable | When Applied |
| --- | --- | --- |
| Buildpack configuration | **BP_** | During image creation |
| Buildpack runtime component | **BPL_** | When container starts |
| Java standard options | **JAVA_TOOL_OPTIONS** | JVM runtime |
| Embedded environment modifications | **BPE_** | Built into image if Environment Variables buildpack is present |

**Do not confuse `BP_JVM_VERSION` with a container runtime environment variable.** Changing `BP_JVM_VERSION` requires rebuilding the image. Changing `JAVA_TOOL_OPTIONS` during `docker run` can alter JVM behavior without rebuilding the image.

### 14.4. Do Not Embed Secrets in the Image

The Paketo Environment Variables buildpack can embed default variables into the image via `BPE_*`. Those values become metadata/content viewable by anyone with read access to the image.

**Do not embed passwords, API tokens, private keys, or database credentials into the image.** Use a secret manager, orchestrator secrets, or buildpack bindings for credentials needed at build/runtime. Non-sensitive configuration values such as a default JVM flag may be appropriate for the embedded environment when policy permits.

## 15. Proxy and Network in Buildpacks

During the build, the builder container and buildpacks may need to download the JDK, dependencies, or metadata from registries/remote sources. The host machine having internet access does not guarantee the builder container has the same network/proxy setup.

With Paketo, proxy environment variables can be passed via image configuration:

~~~xml
<image>
    <env>
        <HTTP_PROXY>http://proxy.example.com:8080</HTTP_PROXY>
        <HTTPS_PROXY>http://proxy.example.com:8080</HTTPS_PROXY>
    </env>
</image>
~~~

This is an illustrative proxy; use an endpoint approved by your organization. Avoid writing proxy credentials into the POM or Maven logs.

The plugin also has a **network** parameter to configure the Docker network driver of the builder container. The value is passed to Docker; ensure the network exists and the builder container has access to the required services.

If the build fails while downloading the JDK or dependencies, check:
1. Can the Docker daemon pull builder/run images?
2. Does the builder container have DNS and network connectivity?
3. Are proxy variables being passed properly into the builder?
4. Does the registry/artifact mirror require credentials?
5. Are the CA certificates of the proxy/private registry trusted?

## 16. Builder Cache and Workspace

The Spring Boot Plugin uses cache volumes to store layers created during build/launch. By default, cache volumes derive their names from the **full image name**.

This has a practical consequence: if the image name contains a constantly changing version, for example:

~~~text
cnb-demo:1.0.0
cnb-demo:1.0.1
cnb-demo:1.0.2
~~~

then the default cache volumes will differ across image names, reducing cache reuse across releases.

### 16.1. `cleanCache`

The **cleanCache** parameter defaults to `false`. When set to `true`, the plugin clears the cache before building:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.cleanCache=true
~~~

Use this when investigating cache corruption or verifying a cold build. Do not enable it on every routine CI build if you want cache benefits; doing so can slow builds and increase network load.

### 16.2. Customizing Cache Volumes

You can specify explicit cache volume names in the POM:

~~~xml
<image>
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
</image>
~~~

The build cache and launch cache serve different layers. Pick stable names per project/branch policy; avoid letting unrelated projects share a volume without controlled design. If multiple CI jobs run concurrently, review how the builder and Docker daemon manage cache volumes to avoid contention.

### 16.3. Workspace

**buildWorkspace** is the temporary area where the builder/buildpacks process files during the build. By default, the plugin uses a named volume on the Docker daemon. You can switch to a bind mount if the environment requires managing specific paths or storage.

Do not manually delete named volumes currently in use by another build. When cleaning cache, identify the exact volume created by the project and follow runner policies.

## 17. Reproducible Images and `createdDate`

The Spring Boot Maven Plugin provides the **createdDate** parameter for the `Created` field in image metadata. Values can be:
- An ISO 8601 instant, e.g. `2026-01-01T00:00:00Z`.
- **now**, meaning the current timestamp.

A fixed timestamp makes image metadata more reproducible:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.createdDate=2026-01-01T00:00:00Z
~~~

In the POM, you can configure:

~~~xml
<createdDate>2026-01-01T00:00:00Z</createdDate>
~~~

If **now** is used, the same source built at different times will produce different `Created` metadata. For releases requiring reproducibility, take the timestamp from finalized release/commit metadata and use it consistently.

**`createdDate` alone is not enough to guarantee byte-for-byte identical images.** You must also control:
- Builder/run image versions and digests.
- Buildpack versions.
- JDK/JRE provider and patch versions.
- Dependencies, repositories, and artifact inputs.
- Platform/architecture.
- Generated metadata, timestamps, and build environment.
- Cache and lifecycle configuration.

A reproducible image also requires verification by rebuilding and comparing digests/artifacts in a controlled environment. Do not infer reproducibility from a single `createdDate` line alone.

## 18. How Do Buildpacks Produce the OCI Image Output?

CNB export creates an image comprising the required filesystem layers and metadata. The image typically includes:
- Runtime base from the run image.
- Dependency/runtime layers contributed by buildpacks.
- Application layer.
- Metadata describing processes, buildpacks, stack/run image, and build info.
- SBOM or BOM metadata depending on buildpack/platform and version.

Do not assume a fixed number of layers for every application. A Java buildpack may contribute JRE, classpath, application, and other runtime components; each buildpack version or configuration can change the layer count.

### 18.1. Inspecting Image History

~~~bash
docker image history cnb-demo:1.0.0
docker image inspect cnb-demo:1.0.0
~~~

CNB images do not necessarily look like manual Dockerfiles in `history`. Layers created by the lifecycle/buildpacks carry metadata differing from images built by a sequence of Dockerfile instructions.

If the CNB `pack` CLI is installed, you can use its inspect/report commands to view buildpack/process metadata and the image's SBOM. Specific tooling depends on `pack` version and builder API.

### 18.2. Checking the Non-Root User

The Spring Boot Plugin notes that images are built and run with a non-root user for security. Check the configuration:

~~~bash
docker image inspect cnb-demo:1.0.0 --format '{{.Config.User}}'
~~~

The result may be a non-zero UID depending on the builder. Do not hardcode a fixed UID in the application unless necessary; check file permissions and runtime paths whenever the app needs to write data.

### 18.3. Checking Image Size

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0 --format '{{.Size}}'
docker system df -v
~~~

Distinguish between:
- Local image `SIZE`, which is typically the uncompressed size.
- Registry transfers, which send compressed blobs.
- Shared/unique sizes depending on other images present on the daemon.
- Buildpack cache volumes consuming disk separately from the runtime image.

Do not assume an image is smaller just because a builder has `tiny` in its name. Compare the same application, same platform, and same JRE/dependency policy; a tiny builder might lack a component the app needs or require a different buildpack.

## 19. Automatically Building Images in the Maven Lifecycle

If an organization wants **`mvn package`** to create the image automatically, bind **build-image-no-fork** to the `package` phase:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>build-image-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Then:

~~~bash
./mvnw package
~~~

will run `package` and the image build goal as part of the execution. This is convenient for CI, but also means every local `package` run may require a Docker daemon, pulling the builder, and running buildpacks. If a developer does not have Docker, the `package` phase can fail.

You can use a separate Maven profile for container builds:

~~~xml
<profiles>
    <profile>
        <id>container-image</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <phase>package</phase>
                            <goals>
                                <goal>build-image-no-fork</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Then invoke:

~~~bash
./mvnw -Pcontainer-image package
~~~

This is a build-organization choice; not every project needs a profile. Ensure duplicate plugin executions are not declared across parents/profiles, which could accidentally trigger multiple image builds.

## 20. Excluding/Including Dependencies

When building an image, the Spring Boot Plugin packages the application following repackage rules. Certain dependencies such as **spring-boot-devtools** and **spring-boot-docker-compose** are excluded by default; this can be adjusted via plugin configuration if the project truly needs them.

Since Spring Boot 3.5.7, the **includeOptional** parameter is supported and defaults to `true` in the `build-image` goal. If the application has optional dependencies that must be included in the image, check the effective POM and plugin version behavior. Do not arbitrarily exclude a dependency just because it enlarges the image; the application may rely on it in a rare endpoint or feature.

Other parameters include **excludes**, **excludeGroupIds**, **includeSystemScope**, **classifier**, and **sourceDirectory**. Only adjust them once you understand the Maven dependency graph and the artifact `build-image` reads.

## 21. Common Errors When Running `spring-boot:build-image`

| Error or Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Cannot connect to Docker daemon | Docker daemon/context not running or Maven uses a different context | `docker info`, `docker context show`, `DOCKER_HOST`/`DOCKER_CONTEXT` |
| Error response from daemon | Docker Engine/permissions/network | Docker logs, daemon status, user permissions |
| Pull access denied for builder | Private builder image or wrong name/tag | builder reference, `builderRegistry`, Docker login |
| Run image pull fails | Private run image credentials or network | Builder metadata, registry credentials, `pullPolicy` |
| No buildpack groups passed detection | Builder lacks suitable buildpack or app layout is wrong | Builder contents, buildpack order, artifact path |
| Buildpack detect failed | Could not recognize source/artifact | Maven package, main class, `sourceDirectory` |
| Build phase failed | JDK download, dependency resolution, proxy, or buildpack error | Verbose logs, `BP_` variables, network/proxy |
| Export phase failed | Registry/daemon/storage/cache issue | Docker daemon, disk, registry, lifecycle logs |
| Wrong Java version | Compiler config and `BP_JVM_VERSION` differ | POM properties, buildpack environment, SBOM |
| Image built successfully but container exits | Runtime config, port, Spring bean, or missing dependency | `docker run`, logs, inspect state |
| Container runs but endpoint fails | Port mapping, security, app bind, or not ready | `docker ps`, logs, `curl`, Actuator readiness |
| Image size too large | Unsuitable builder/run image or heavy dependency layers | `docker image inspect`/history, SBOM, builder |
| Slow build every time | `pullPolicy` `ALWAYS`, renamed cache, or `cleanCache` enabled | pull policy, cache volumes, image name |
| CI cannot reuse cache | Ephemeral Docker daemon/runner or cache volume not persisted | Runner lifecycle, cache storage policy |
| Publish denied | `publishRegistry` unauthenticated or wrong image path | image name, Docker credential helper, registry ACL |
| TLS handshake failed | CA/certificate or proxy TLS | Docker cert path, trusted CA, proxy config |
| Platform mismatch | Builder/run image does not support target architecture | `imagePlatform` and builder metadata |
| Permission denied at runtime | Non-root user lacks write permission to path | Container user, volume/file permissions |
| Maven package builds image twice | `build-image` and `build-image-no-fork` double-bound | Effective POM and plugin executions |

### 21.1. Diagnosing in Order

1. Run **`docker info`** to confirm the daemon.
2. Confirm Maven build/package and input artifact.
3. Confirm the builder image can be pulled and matches the architecture.
4. Check buildpack detection.
5. Read buildpack logs for dependency/JDK/proxy issues.
6. Check export/cache/registry.
7. If image creation finished, inspect Docker metadata and runtime logs.
8. Call HTTP readiness/endpoints after container startup.

Do not edit the POM or switch builders before identifying whether the error lies in the daemon, detection, build, export, or runtime.

## 22. Building in CI/CD

A basic pipeline:

~~~text
Checkout source commit
        |
        v
Maven clean verify
        |
        v
spring-boot:build-image
        |
        v
Inspect image name/platform/digest
        |
        v
Run container smoke test
        |
        v
Security scan + SBOM + policy gates
        |
        v
Publish to registry
        |
        v
Deploy immutable image digest
~~~

Separate **local image build** and **publish** into intentional steps. Only enable publish after the image has passed tests/scans and the target registry/tag has been verified.

### 22.1. Using Version and Commit Tags

An image can have a version tag:

~~~text
registry.example.com/team/cnb-demo:1.0.0
~~~

and a commit tag:

~~~text
registry.example.com/team/cnb-demo:git-<short-commit>
~~~

This is an example naming policy, not real tags. Avoid relying solely on `latest` as a deployment reference. Record the digest returned by the registry and use that digest in deployment manifests when exact image content guarantees are needed.

### 22.2. Builder Versions in Pipelines

Pin builder/run image versions or digests in pipelines so builds stay controlled. When upgrading a builder:
- Read release notes of the builder and buildpacks.
- Verify OS distribution/base image changes.
- Check JDK/JRE provider/patch.
- Rebuild and compare size/startup/health.
- Run security scans/SBOM checks.
- Roll out through staging before changing production.

The `latest` tag fetches newer builders automatically, but also means the same commit can yield a different image across builds. This is a freshness-versus-reproducibility trade-off; release policy should state it explicitly.

### 22.3. Build Cache on Ephemeral Runners

If CI creates a fresh Docker daemon per job, default named cache volumes may be lost after the job finishes. In that situation, buildpacks must re-download/restore many dependencies, increasing build duration. Options include:
- Using a persistent builder/daemon with appropriate isolation policies.
- Managing build/launch cache volumes per project.
- Using a registry/cache mechanism supported by the platform.
- Monitoring cache hits/misses and avoiding unconditional cache deletion.

Do not share caches across untrusted projects without evaluating isolation and lifecycle.

## 23. Buildpacks, SBOM, and Security

Buildpacks produce images with metadata about buildpacks/dependencies; depending on the builder/platform, they can supply SBOM and BOM layers. This serves as useful input for:
- Dependency inventory.
- Vulnerability scanning.
- Verifying JDK/JRE versions.
- Tracing builder/buildpack versions.
- Auditing image provenance.

However, **having an SBOM does not mean an image is secure**. You must scan for CVEs, check base image patch status, verify buildpack sources, and review dependency licenses per policy.

### 23.1. Non-Root Runtime

The Spring Boot Plugin notes that images are built/run under a non-root user per the CNB security model. This reduces application privileges compared to root, yet you still need to:
- Configure volumes with proper owner/permissions.
- Avoid writing to non-writable filesystem paths.
- Avoid exposing actuator details/secrets.
- Restrict Linux capabilities and network permissions per environment.
- Supply secrets from an orchestrator/secret manager.

### 23.2. A Builder Is Trusted Software

The builder contains the lifecycle and buildpacks—code that executes during the build. Therefore:
- Use builders from approved sources.
- Pin versions/digests.
- Inspect buildpack IDs/versions.
- Manage registry access permissions.
- Do not let untrusted pull request builds access publish credentials.
- Separate build-time credentials from runtime secrets.

A custom builder may require explicit trust configuration; do not assume a new builder is trustworthy merely because it produces an image.

## 24. Comparing Buildpacks and Dockerfile in Real Projects

| Question | CNB with `build-image` | Dockerfile |
| --- | --- | --- |
| Need to write JAR copy instructions? | No, in standard cases | Yes |
| Need to select a JRE manually? | Buildpack/provider handles per config | Dockerfile/base image chosen by team |
| Can OS packages be customized? | Via buildpack/builder/extension | Directly via Dockerfile |
| Build layers/caching supported? | Yes, via lifecycle/buildpack layers | Yes, per instructions and build cache |
| Can entrypoint be controlled? | Via process type/buildpack config | Via `ENTRYPOINT`/`CMD` |
| Transparency of OS steps | Via builder/buildpack metadata/logs | Directly in the Dockerfile |
| Fit for typical Java applications | Very well suited | Well suited |
| Deep OS environment customization | Requires custom builder/buildpack | Usually more direct |

No single option fits every team. CNB suits standardized applications wanting less boilerplate; Dockerfile suits cases needing fine-grained control over the image environment. Both still require tests, image scans, SBOMs, health checks, and deployment policies.

## 25. Practice Exercises with Answers

**Q1.** Does the `spring-boot:build-image` goal need to run `docker build` with a Dockerfile?

**Answer:** No. The goal uses Cloud Native Buildpacks to create an OCI image. A Docker daemon is still required in the default Spring Boot 3.5 workflow.

**Q2.** Do the builder and run image share the same role?

**Answer:** No. The builder supplies buildpacks, lifecycle, and the build-time environment; the run image acts as the base for the application image at runtime.

**Q3.** Why can a builder contain a JDK/tooling while the runtime image only has a JRE?

**Answer:** The build-time base and runtime base are two distinct environments. The builder needs tools to build; the run image only needs what is required to run the application.

**Q4.** Why do direct commands use `build-image` while lifecycle bindings use `build-image-no-fork`?

**Answer:** `build-image` forks the Maven lifecycle to ensure `package` has run. `build-image-no-fork` avoids forking again when the goal is bound to a lifecycle phase.

**Q5.** After `build-image`, is the image automatically pushed to a registry?

**Answer:** No. `publish` defaults to `false`. You must enable `publish` and provide the appropriate image name/registry credentials.

**Q6.** How do `BP_JVM_VERSION` and `JAVA_TOOL_OPTIONS` differ?

**Answer:** `BP_JVM_VERSION` configures which Java version is installed while building the image. `JAVA_TOOL_OPTIONS` passes flags to the JVM when the container runs.

**Q7.** Why can changing an image tag cause cache misses?

**Answer:** Default cache volumes are named based on the full image name. When the name/tag changes continuously, the plugin may use a different cache volume.

**Q8.** Should `cleanCache=true` be enabled on every CI build?

**Answer:** No. It clears the cache before building and can slow down builds. Enable it only when you need to clean or investigate the cache.

**Q9.** Does a fixed `createdDate` guarantee a reproducible image?

**Answer:** No. You must also pin builder/run images, buildpacks, dependencies, platform, and other inputs.

**Q10.** The image builds successfully, yet the container returns no HTTP response. What should you do?

**Answer:** Check `docker ps`, inspect `State`, logs, port mapping, Spring configuration, and readiness. Build success does not prove runtime success.

## 26. Pre-Release Image Checklist

- [ ] Maven build/tests PASS on the locked source commit.
- [ ] Spring Boot Maven Plugin version matches the project.
- [ ] The Docker daemon/context used by Maven has been verified.
- [ ] Builder and run image come from approved sources with a version/digest policy.
- [ ] Java compatibility and `BP_JVM_VERSION` are consistent.
- [ ] Image name, version tag, and target registry are accurate.
- [ ] Buildpack detect/build/export succeeded.
- [ ] Build cache policy fits the CI runner.
- [ ] Image is built locally before publishing; publish is enabled only when approved.
- [ ] Builder registry credentials and publish credentials are separated.
- [ ] No hardcoded secrets or embedded credentials in the image.
- [ ] Image runs non-root with appropriate file permissions.
- [ ] `docker inspect` confirms platform, image ID/digest, and runtime config.
- [ ] Container smoke test PASSES, HTTP endpoints and readiness PASS.
- [ ] SBOM/security scan/license checks per policy have PASSED.
- [ ] `createdDate`/builder/buildpack/dependency inputs are controlled if reproducibility is required.
- [ ] Registry digest is saved in the release record and used for deployments requiring immutable identity.
- [ ] Cache volumes and workspace are managed; caches of other projects are not deleted.

## 27. Conclusion

The Maven goal **spring-boot:build-image** uses **Cloud Native Buildpacks** to turn a Spring Boot JAR/WAR into an OCI image. The plugin orchestrates the builder and buildpacks, creates runtime layers, exports the image to the Docker daemon, and can publish to a registry when enabled.

Process to remember:

~~~text
Maven project + spring-boot:build-image
                   |
                   v
             Docker daemon
                   |
                   v
          CNB builder + lifecycle
                   |
                   v
           Detect buildpacks
                   |
                   v
          Restore / Build layers
                   |
                   v
             Export OCI image
                   |
                   v
          docker image inspect
                   |
                   v
             docker run
                   |
                   v
        HTTP health + smoke tests
                   |
                   v
             Publish / Deploy
~~~

Properly understanding **builder**, **run image**, **buildpacks**, **cache**, and **registry publishing** lets you stay in control of your images rather than treating `build-image` as an opaque magic command. For releases, pin critical inputs, verify non-root runtime, smoke test the real image, and deploy using the verified digest.

## 28. Official References

- Spring Boot 3.5.16 Maven Plugin — Packaging OCI Images, build-image goal, Docker daemon, builder/run image, publish, and cache: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Cloud Native Buildpacks — What is a builder?: https://buildpacks.io/docs/for-app-developers/concepts/builder/
- Cloud Native Buildpacks — What happens during build?: https://buildpacks.io/docs/for-app-developers/concepts/build/
- Cloud Native Buildpacks — Lifecycle Create (analyze/detect/restore/build/export): https://buildpacks.io/docs/for-platform-operators/concepts/lifecycle/create/
- Cloud Native Buildpacks — Build reproducibility: https://buildpacks.io/docs/for-app-developers/concepts/reproducibility/
- Paketo — Configure Paketo Buildpacks, build-time/runtime environment and bindings: https://paketo.io/docs/howto/configuration/
- Paketo — Java Buildpack, JVM version/type and runtime options: https://paketo.io/docs/buildpacks/language-family-buildpacks/java/
- Docker — Docker CLI configuration and contexts: https://docs.docker.com/engine/manage-resources/contexts/
- Docker — Image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Docker — Image history: https://docs.docker.com/reference/cli/docker/image/history/
- Docker — Container run: https://docs.docker.com/reference/cli/docker/container/run/