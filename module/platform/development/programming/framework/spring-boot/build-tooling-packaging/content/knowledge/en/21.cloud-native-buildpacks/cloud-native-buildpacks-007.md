# Configuring Image Name, Tag, Builder, Run Image, and Pull Policy with Cloud Native Buildpacks

Spring Boot supports packaging applications into an **OCI container image** via Maven `spring-boot:build-image` or Gradle `bootBuildImage` using **Cloud Native Buildpacks (CNB)** without writing a Dockerfile. Still, the same project can produce an image under the wrong name, attach untraceable tags, pick up stale builder/run images from cache, pull images unintentionally, or fail to push due to confusing the Docker daemon with a registry.

This lesson focuses on **five core concepts**: **image name**, **tag**, **builder**, **run image**, and **pull policy**; explaining defaults, Maven/Gradle configuration, differences between build and publish, verifying real Docker images, along with security and reproducibility risks. Examples choose **Spring Boot 3.3.13, Java 17** for consistent syntax. This is an illustrative version, not a claim about the latest or still-supported release; in real projects, consult documentation for your exact project version.

## 1. Three Image Types in a Single CNB Build

| Image | Role | When Used? |
| --- | --- | --- |
| **Builder image** | Contains CNB buildpacks, lifecycle, and metadata to build the app | Build time |
| **Run image** | Provides launch/base operating-system layers for the built app | Runtime base |
| **Application image** | Final OCI artifact, with name/tag/digest to run or release | Output and deploy |

Flow:

```text
Java source + Maven/Gradle
           |
           v
   executable JAR/WAR
           |
           v
 builder image + buildpacks ---------+
           |                        |
           v                        v
      CNB lifecycle             run image
           |                        |
           +-------------+----------+
                         |
                         v
           application image :1.0.0
                         |
                   +-----+------+
                   |            |
                docker run    registry push
```

**The builder is not the output image.** Changing the image name does not change the builder. **The run image is not the `docker run` command**; it is the base image of the result. A build using a run image incompatible with the builder can fail even if Java code runs in an IDE.

## 2. Image Name, Tag, and Digest

An OCI reference typically has the form:

```text
[registry-host[:port]/][namespace/]repository[:tag][@digest]
```

Examples:

```text
image-config-demo:1.0.0
docker.io/library/image-config-demo:1.0.0
docker.io/acme/image-config-demo:dev
registry.example.invalid/team/image-config-demo:1.0.0
registry.example.invalid/team/image-config-demo:git-a1b2c3d
registry.example.invalid/team/image-config-demo@sha256:<real-digest>
```

`registry.example.invalid` and `acme` are examples, not real registries/accounts. `<real-digest>` is a placeholder representing the actual digest retrieved from the registry after publishing.

- **Registry hostname** determines the remote server storing the image.
- **Repository** determines the namespace and image name.
- **Tag** such as `dev`, `1.0.0`, `latest` is a label that can be moved to a new image if the registry allows overwrites.
- **Digest** references the OCI manifest by content, suitable for deploying the exact tested artifact.

If no tag is specified, Docker image references normally default to `latest`. **A tag is not a checksum and does not guarantee immutability.** `docker tag` creates an additional local reference to the same image; it neither rebuilds nor pushes the image.

## 3. Defaults in Spring Boot 3.3.13

Per Spring Boot 3.3 branch plugin documentation:

| Item | Maven Plugin | Gradle Plugin |
| --- | --- | --- |
| Output image name | `docker.io/library/${project.artifactId}:${project.version}` | `docker.io/library/${project.name}:${project.version}` |
| Builder (standard JVM) | `paketobuildpacks/builder-jammy-base:latest` | `paketobuildpacks/builder-jammy-base:latest` |
| Run image | Taken from builder metadata if not overridden | Taken from builder metadata if not overridden |
| Pull policy | `ALWAYS` | `ALWAYS` |
| Publish | `false` | `false` |

Spring Boot Gradle has an exception when the GraalVM Native Image plugin is applied; this example does **not** use native image. Defaults can change across versions, so do not use docs from newer Boot branches to infer Boot 3.3 defaults.

Notably, `:latest` on the **builder** is a tag on the builder repository, unrelated to `:latest` on the **application**. Two builds using a `:latest` builder at different times may receive different contents.

## 4. Maven ↔ Gradle Configuration Mapping Table

| Intent | Maven `spring-boot:build-image` | Gradle `bootBuildImage` |
| --- | --- | --- |
| Primary name/tag | `<image><name>...` | `imageName` |
| CNB builder | `<image><builder>...` | `builder` |
| Launch/run image | `<image><runImage>...` | `runImage` |
| When to pull builder/run | `<image><pullPolicy>...` | `pullPolicy` |
| Buildpack variables | `<image><env>...` | `environment` |
| Publish output | `<image><publish>...` | `publish` |
| Additional tags | Can be added via Docker `tag` or configured per specific plugin API | `tags` list |

`pullPolicy` accepts only three enum values in Spring Boot 3.3: **`ALWAYS`, `IF_NOT_PRESENT`, and `NEVER`**.

**Watch out:** the Maven XML field is `<name>`, whereas the Maven CLI property is called `spring-boot.build-image.imageName`. The Gradle task uses `imageName` in both the build script and the `--imageName` command-line option.

## 5. Java 17 Project to Test the Image

Choose Maven or Gradle, sharing the same three files:

```text
image-config-demo/
├── pom.xml                          # Maven
├── settings.gradle                  # Gradle (replaces Maven)
├── build.gradle                     # Gradle (replaces Maven)
└── src/
    ├── main/java/com/example/image/
    │   ├── ImageConfigApplication.java
    │   └── StatusController.java
    └── test/java/com/example/image/
        └── StatusControllerTest.java
```

`src/main/java/com/example/image/ImageConfigApplication.java`:

```java
package com.example.image;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImageConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImageConfigApplication.class, args);
    }
}
```

`src/main/java/com/example/image/StatusController.java`:

```java
package com.example.image;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/status")
    public String status() {
        return "image-config-ok";
    }
}
```

`src/test/java/com/example/image/StatusControllerTest.java`:

```java
package com.example.image;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class StatusControllerTest {
    @Test
    void returnsExpectedText() {
        assertEquals("image-config-ok", new StatusController().status());
    }
}
```

The files have matching packages/paths and are valid for Java 17. The unit test checks the endpoint logic **without needing a Spring context**. When running the application image with embedded server on port 8080, HTTP `GET /status` returns the exact body:

```text
image-config-ok
```

That is the HTTP body, not all console logs. A real smoke test on the container verifies packaging and launch.

## 6. Complete Maven POM: Image Name, Builder, Run Image, Pull Policy

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>image-config-demo</artifactId>
    <version>1.0.0</version>
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
                    <image>
                        <name>docker.io/library/image-config-demo:${project.version}</name>
                        <builder>paketobuildpacks/builder-jammy-base:latest</builder>
                        <runImage>paketobuildpacks/run-jammy-base:latest</runImage>
                        <pullPolicy>IF_NOT_PRESENT</pullPolicy>
                        <publish>false</publish>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

This is a complete POM; no extra files are needed. Key elements:
- `<name>...:${project.version}</name>` produces primary output image `docker.io/library/image-config-demo:1.0.0`.
- `builder` selects the Paketo Jammy Base CNB builder.
- `runImage` illustrates overriding to the Paketo Jammy Base run image matching the stack family; in real projects, inspect run images listed in builder metadata.
- `pullPolicy=IF_NOT_PRESENT` uses local builder/run images if already present in the Docker daemon.
- `publish=false` **builds locally only**, without pushing.
- `BP_JVM_VERSION=17` tells the Paketo Java buildpack to select runtime major 17 when available.

**You can omit `<runImage>` completely** to let the builder pick the run image declared in metadata — a less error-prone approach when no custom override is needed. `latest` on builder/run image is mutable; this lesson uses it for practice, not as a recommendation for unpinned production releases.

## 7. Maven: Building the Image and Running a Smoke Test

Prerequisites:
- JDK 17 and Maven Wrapper or compatible Maven.
- Working Docker daemon where `docker info` succeeds.
- Network/registry auth sufficient to pull builder, run image, and buildpack artifacts on the first run.
- Permissions to use the Docker socket/daemon and sufficient disk space.

Commands from the project root:

```bash
java -version
docker version
docker info
./mvnw clean verify
./mvnw spring-boot:build-image
```

In PowerShell use `.\mvnw.cmd`; if no Maven Wrapper is present, use `mvn`. The `spring-boot:build-image` goal ensures the required `package` phase runs before generating the OCI image.

Verify:

```bash
docker image ls image-config-demo
docker image inspect docker.io/library/image-config-demo:1.0.0
docker image inspect docker.io/library/image-config-demo:1.0.0 \
    --format '{{.Id}}'
```

Run the container:

```bash
docker run --rm -p 8080:8080 \
    docker.io/library/image-config-demo:1.0.0
```

Open a second terminal:

```bash
curl -fsS http://localhost:8080/status
```

Expected:

```text
image-config-ok
```

Stop the container with Ctrl+C. If host port 8080 is busy, run `-p 8091:8080` and call `localhost:8091/status`. `docker image inspect` proves the image exists on the current Docker daemon, **not** that it was pushed to a registry.

## 8. Overriding Properties via Maven CLI

Spring Boot Maven Plugin 3.3 supports user properties:

```bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=image-config-demo:trial \
  -Dspring-boot.build-image.builder=paketobuildpacks/builder-jammy-base:latest \
  -Dspring-boot.build-image.runImage=paketobuildpacks/run-jammy-base:latest \
  -Dspring-boot.build-image.pullPolicy=ALWAYS
```

Bash uses `\` for line continuation; PowerShell should use one line or PowerShell backticks. Exact options are:
- `spring-boot.build-image.imageName`: output name/tag.
- `spring-boot.build-image.builder`: CNB builder.
- `spring-boot.build-image.runImage`: run image.
- `spring-boot.build-image.pullPolicy`: `ALWAYS` / `IF_NOT_PRESENT` / `NEVER`.
- `spring-boot.build-image.publish`: enables/disables push (do not enable for local practice).

**Distinction:** XML uses `<image><name>`, whereas CLI uses `imageName`. If a project does not inherit from `spring-boot-starter-parent`, merely importing the BOM is insufficient to configure goals/executions and plugin versions; configure the Maven plugin explicitly.

## 9. Maven `build-image` vs `build-image-no-fork`

In Spring Boot 3.3:
- `spring-boot:build-image` is suited for **direct command-line invocation**; it ensures the `package` lifecycle has run.
- `spring-boot:build-image-no-fork` is suited for **binding into the Maven lifecycle**, avoiding forking `package` a second time.

Example **snippet added inside the existing Spring Boot Maven plugin declaration** if you also want `package` to create an image:

```xml
<executions>
    <execution>
        <id>package-image</id>
        <goals>
            <goal>build-image-no-fork</goal>
        </goals>
    </execution>
</executions>
```

Do not copy this snippet as a standalone POM and do not add a duplicate plugin declaration. Binding image creation to every `mvn package` causes jobs meant only for unit tests to depend on a Docker daemon/registry, so release pipelines typically run image builds as a separate step.

## 10. Complete Gradle Groovy DSL with `bootBuildImage`

`settings.gradle`:

```groovy
rootProject.name = 'image-config-demo'
```

`build.gradle`:

```groovy
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.image.ImageConfigApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    imageName = "docker.io/library/${project.name}:${project.version}"
    builder = 'paketobuildpacks/builder-jammy-base:latest'
    runImage = 'paketobuildpacks/run-jammy-base:latest'
    pullPolicy = 'IF_NOT_PRESENT'
    environment['BP_JVM_VERSION'] = '17'
    tags.set(['docker.io/library/image-config-demo:dev'])
    publish = false
}
```

`bootBuildImage` is created by the Spring Boot plugin when the Java or War plugin is applied, using `bootJar`/`bootWar` as input. This task belongs on the application module; in a multi-module project, target the exact project path and do not run image builds for a library lacking a main class.

`imageName` sets primary tag `1.0.0`. `tags.set(...)` adds a full reference `:dev` pointing to the **same image content**, without triggering a second build. `environment` passes build-time variables to the builder, while `publish=false` prevents pushing.

Run:

```bash
./gradlew clean test bootBuildImage
docker image inspect docker.io/library/image-config-demo:1.0.0
docker image inspect docker.io/library/image-config-demo:dev
```

PowerShell uses `.\gradlew.bat`. If both tags return the same image ID, they are two references to the same local image.

## 11. Equivalent Gradle Kotlin DSL

If using `build.gradle.kts`, example **standalone file replacing Groovy `build.gradle`**:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

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
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

springBoot {
    mainClass.set("com.example.image.ImageConfigApplication")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("docker.io/library/${project.name}:${project.version}")
    builder.set("paketobuildpacks/builder-jammy-base:latest")
    runImage.set("paketobuildpacks/run-jammy-base:latest")
    setPullPolicy("IF_NOT_PRESENT")
    environment.put("BP_JVM_VERSION", "17")
    tags.set(listOf("docker.io/library/image-config-demo:dev"))
    publish.set(false)
}
```

`settings.gradle.kts`:

```kotlin
rootProject.name = "image-config-demo"
```

`setPullPolicy("IF_NOT_PRESENT")` is the string-accepting method provided by `BootBuildImage` in Spring Boot 3.3; the other fields are Gradle Property APIs such as `imageName.set`, `builder.set`, and `tags.set`. Do not mix Groovy and Kotlin syntax in the same file.

## 12. Gradle Task Options

You can test changing image/builder names without editing the build script:

```bash
./gradlew bootBuildImage \
  --imageName=image-config-demo:trial \
  --builder=paketobuildpacks/builder-jammy-base:latest \
  --runImage=paketobuildpacks/run-jammy-base:latest \
  --pullPolicy=ALWAYS
```

The `--...` flags are Gradle **task options**, distinct from Maven `-Dspring-boot.build-image...`. Check available options for your version:

```bash
./gradlew help --task bootBuildImage
```

Do not assume a `--tags` CLI flag exists just because `tags` is a task property. To add tags, configure `tags.set(...)` in the script, pass a validated Gradle project property, or run `docker tag` after building. `--publishImage` enables publish; do not use it in local demos.

## 13. Builder Image: Selecting by Stack and Buildpacks

Spring Boot 3.3 docs use `paketobuildpacks/builder-jammy-base:latest` for typical JVM builds. When choosing another builder, check:
- Whether Java buildpacks support JDK 17 and Spring Boot executable archives.
- Whether the builder OS/stack is compatible with the intended run image.
- Whether it supports the CPU architecture of the build daemon and target platform.
- Whether required system libraries for app native dependencies are present.
- Whether buildpack/lifecycle versions comply with security and support policies.
- Whether the source registry is trusted and builder tags/digests cannot be tampered with.
- Whether CI has permission to pull builder/run images and resources to run the builder container.

If the **Pack CLI** is installed, inspect builder metadata:

```bash
pack builder inspect paketobuildpacks/builder-jammy-base:latest
```

Pack CLI is not required to run `bootBuildImage`. If the image exists on the Docker daemon, `docker image inspect` provides local metadata:

```bash
docker image inspect paketobuildpacks/builder-jammy-base:latest
```

Names like `base` or `tiny` do not guarantee suitability for every app. A small builder whose run image lacks fonts, CA certificates, or system libraries can cause runtime errors.

## 14. Run Image: Defaulting to Builder Metadata Is Safe

When `runImage` is unset, Spring Boot 3.3 Maven/Gradle **uses the run image designated by builder metadata**. This reduces the risk of pairing an incompatible base image.

Example pair in the Paketo Jammy Base family:
- Builder `paketobuildpacks/builder-jammy-base:latest`.
- Run image `paketobuildpacks/run-jammy-base:latest`.

Without an override requirement:
- **Maven:** omit the `<runImage>` element from `<image>`.
- **Gradle:** omit the `runImage` assignment.

Overriding the run image is typically only needed for private registry mirrors, OS security update policies, digest pinning, or custom compatible bases. Before overriding, inspect the stack ID and run images in the chosen builder's metadata. **Do not pair a Jammy builder with an Alpine/musl run image or different stack just because both support Java 17.**

The run image is the runtime foundation and **does not need** Maven, Gradle, a JDK compiler, or buildpacks inside it. If the app needs native libs, verify them in the actual run image, not just in the builder.

## 15. Three Pull Policies and Their Real Meaning

`pullPolicy` of `build-image` governs **builder/run images at build time**, not the application image at deploy time.

| Value | Policy | When to Use | Risk |
| --- | --- | --- | --- |
| **`ALWAYS`** | Checks/pulls builder and run image from registry on every build | CI frequently updating base images | Mutable `latest` tag may change, requires network |
| **`IF_NOT_PRESENT`** | Uses local image if present, only pulls if missing | Developers with cache or CI with preloaded base images | Two daemons using the same tag may hold different content |
| **`NEVER`** | Does not pull builder/run images from registry | Environments where images are pre-seeded | Fails build if local image missing; other dependency sources may still require network |

**`ALWAYS` does not guarantee reproducibility**, and `IF_NOT_PRESENT` does not guarantee security updates. `NEVER` does not make the entire build offline: Maven/Gradle dependency downloads and artifacts fetched by buildpacks may still need internet/mirror access.

Do not confuse with Kubernetes `imagePullPolicy`:
- Spring Boot: `IF_NOT_PRESENT` in Maven/Gradle build.
- Kubernetes: `IfNotPresent` in Pod spec, deciding whether to pull the **application image at node runtime**.

## 16. `docker run` and Kubernetes Are Different Stages

```text
Spring Boot build-image:
pullPolicy = IF_NOT_PRESENT
    -> governs pulling builder/run images at build time.

docker run image-config-demo:1.0.0
    -> Docker daemon runs the ready application image,
       potentially pulling from registry per Docker behavior.

Kubernetes:
spec.containers[].imagePullPolicy = IfNotPresent
    -> kubelet decides whether to pull application image when creating Pod.
```

A Kubernetes YAML fragment, **not a complete manifest**:

```yaml
containers:
  - name: image-config-demo
    image: registry.example.invalid/team/image-config-demo:1.0.0
    imagePullPolicy: IfNotPresent
```

The registry name is fictional. Kubernetes values are `Always`, `IfNotPresent`, `Never`. Their casing differs from `ALWAYS`, `IF_NOT_PRESENT`, `NEVER` in the Spring Boot build plugin.

## 17. One Image Can Carry Multiple Tags

In Gradle 3.3, `bootBuildImage.tags` is a list of **additional full image references**:

```groovy
tasks.named('bootBuildImage') {
    imageName = "docker.io/library/image-config-demo:${project.version}"
    tags.set([
        'docker.io/library/image-config-demo:dev',
        'docker.io/library/image-config-demo:git-a1b2c3d'
    ])
}
```

Merge this into the existing task; in real files, manage `imageName` and `tags` consistently in one place.

With Maven, a simple way to add local tags after building the primary image is `docker tag`:

```bash
docker tag docker.io/library/image-config-demo:1.0.0 \
    docker.io/library/image-config-demo:dev

docker tag docker.io/library/image-config-demo:1.0.0 \
    docker.io/library/image-config-demo:git-a1b2c3d
```

Do not guess a Maven `<tags>` syntax based on the Gradle property without verifying the actual plugin API/version. `docker tag` does not push automatically. Verify both tags point to the same image ID:

```bash
docker image inspect docker.io/library/image-config-demo:dev \
    --format '{{.Id}}'
```

**Multiple tags do not create two executable JARs or two separate OCI builds.** They are merely references to the existing image, as long as you are tagging the same image ID.

## 18. Local Image vs Pushing to a Registry

By default, Spring Boot Maven/Gradle image builds use `publish=false`. The image is stored in the Docker daemon connected to the build tool; **it is not yet on the registry**.

To publish when approved:
- Maven `<image><publish>true</publish>` or CLI `-Dspring-boot.build-image.publish=true`.
- Gradle `publish.set(true)` or task CLI `--publishImage`.
- Docker CLI `docker push registry/path/image:tag` after building/tagging with proper permissions.

Illustrative Maven snippet, **do not push to a fake registry**:

```xml
<image>
    <name>registry.example.invalid/team/image-config-demo:${project.version}</name>
    <publish>true</publish>
</image>
```

**Merge** this into the existing `<image>` block rather than creating two `<image>` blocks. The registry configured **in the image name** determines the push destination; `docker.publishRegistry.url` does not change the hostname of the image name.

### 18.1. Two Types of Registry Credentials

Spring Boot plugins distinguish:
- `docker.builderRegistry`: permissions to **pull private builder and run images**.
- `docker.publishRegistry`: permissions to **push the application image** to the target registry.

Never hardcode real passwords/tokens into the POM, `build.gradle`, or command-line logs. Inject them via a CI secret manager and scope permissions per repository. Local builds do not need publish credentials unless builder/run images reside in a private registry.

## 19. Docker Daemon and Docker Context

Before debugging `builder` or `pullPolicy`, check:

```bash
docker context show
docker version
docker info
```

`build-image` requires a Docker daemon. Environments can differ in sockets/permissions/contexts:
- `DOCKER_CONFIG` points to the Docker CLI configuration directory.
- `DOCKER_CONTEXT` selects the Docker context.
- `DOCKER_HOST` selects the daemon host/socket.
- `DOCKER_TLS_VERIFY` and `DOCKER_CERT_PATH` configure TLS connections when needed.

**The Docker daemon is not the registry.** An image listed by `docker image ls` on a remote Docker daemon may not appear in local Docker Desktop; an unpushed local image will not appear in a Kubernetes cluster. Do not change `pullPolicy` to fix `Cannot connect to Docker daemon`; fix the daemon/context/permissions instead.

## 20. Tag Mutability, Cache, and Reproducibility

A build with fixed source code can still yield different outputs because:
1. Builder `:latest` digest changed.
2. Run image `:latest` digest changed.
3. Downloaded buildpack/JDK artifacts have new versions.
4. Maven/Gradle dependencies or plugin versions changed.
5. Docker daemon image caches differ across CI runners.
6. Metadata or build timestamps changed.
7. The registry repointed a mutable release tag.

For traceable releases:
- Pin source commit, JDK, Maven/Gradle Wrapper, and Spring Boot plugin.
- Record builder/run image IDs/digests and verify stack/runtime compatibility.
- Use immutable release tags or deploy by manifest digest.
- Archive SBOMs/test reports and appropriate checksums/provenance.
- Manage pull policy by environment goal, avoiding `NEVER` forever just to bypass security patches.
- Update base images under testing rather than accidentally reusing an outdated local cached builder.

The Gradle plugin also manages `buildCache`, `launchCache`, and `buildWorkspace`, usually via Docker named volumes; cache names can derive from the output image name. When the primary `imageName` tag changes continually, cache reuse can drop. `cleanCache` clears CNB build caches, unlike `pullPolicy`, which only controls pulling builder/run images.

**Do not treat `docker image inspect --format '{{.Id}}'` as the registry digest.** Local image ID differs from the manifest digest returned after publishing; to deploy the exact approved content, capture and verify the digest published by the registry.

## 21. Choosing the Java Runtime in the Paketo Builder

Paketo Java buildpacks detect the Java target version and accept the variable:

```text
BP_JVM_VERSION=17
```

Maven places it in `<image><env>`:

```xml
<env>
    <BP_JVM_VERSION>17</BP_JVM_VERSION>
</env>
```

Gradle Groovy:

```groovy
tasks.named('bootBuildImage') {
    environment['BP_JVM_VERSION'] = '17'
}
```

Gradle Kotlin:

```kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    environment.put("BP_JVM_VERSION", "17")
}
```

These are **snippets to merge into existing configurations**, not standalone files. `BP_JVM_VERSION` is buildpack-specific and not guaranteed to be understood by non-Paketo builders. Do not confuse it with `JAVA_TOOL_OPTIONS` or `BPE_APPEND_JAVA_TOOL_OPTIONS` used for JVM runtime flags.

## 22. Troubleshooting Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Image does not have expected name/tag | Maven/Gradle project version or `imageName` override differs | Check logs and `docker image inspect` |
| Maven XML `<imageName>` has no effect | Correct POM field is `<name>` | Fix `<image><name>...` |
| Tag defaults to `latest` | Omitted `:tag` | Specify explicit version/commit tag |
| `invalid reference format` | Uppercase repo name or invalid reference syntax | Fix lowercase/path/tag |
| `docker run` cannot find image | Image sits on a different Docker daemon | Check `docker context show` and image list |
| `pullPolicy=NEVER` reports missing image | Builder/run image not present locally | Pre-pull per policy or change policy |
| `IF_NOT_PRESENT` gives different results across machines | Mutable builder tags and differing caches | Pin builder/run digests |
| `pull access denied` during build | Private registry lacks authorization | `docker.builderRegistry` or daemon auth |
| `unauthorized` on push | Missing publish rights or wrong namespace | `docker.publishRegistry` and correct image name |
| Stack mismatch | Run image belongs to different builder family/stack | Use builder metadata default or compatible run image |
| Image fails on native libraries at runtime | Run image missing OS dependencies | Check run image, architecture, libc/certs |
| Build reports no Docker daemon | Docker Engine stopped or wrong context/socket | Fix Docker before changing builder |
| `BP_JVM_VERSION` not applied | Builder does not use Paketo Java buildpack | Read logs and builder docs |
| Gradle library lacks `bootBuildImage` task | Appropriate plugin not applied or wrong module | Run on application module |
| Pull policy `ALWAYS` still yields different bytes | Builder `latest` was updated | Use immutable identifiers |
| `NEVER` still requires internet | Maven/Gradle or buildpacks fetch dependencies | Mirror/cache all inputs if offline is needed |
| `dev` tag created locally yet missing from registry | `docker tag` does not push | Push/publish when approved |
| Docker/Kubernetes pull behavior differs from build | Confusing Spring's `pullPolicy` with `imagePullPolicy` | Configure each layer properly |
| Build very slow despite cached base | CNB `buildCache`/Maven downloads differ from pull policy | Read build logs, analyze cache layers |
| Container runs yet `/status` returns 404 | Wrong class/controller or wrong image picked | Compare source, JAR, and image ID |

## 23. Controlled CI/CD Workflow

Suggested sequence:
1. Build Java 17 and run unit/integration tests.
2. Verify dependency graph and plugin/builder/run-image references.
3. Build local image with `publish=false`.
4. Inspect image ID, tag, runtime metadata, and archive build logs.
5. Start container, wait for readiness, and assert `GET /status` returns `image-config-ok`.
6. Scan image/SBOM and validate security policies.
7. Apply version/commit tags and confirm identical image ID.
8. Push using secret-based registry credentials, capturing the real manifest digest.
9. Deploy using immutable tag/digest, verify health, and maintain a rollback reference.

Example Bash smoke test after Maven build:

```bash
#!/usr/bin/env bash
set -euo pipefail

./mvnw -B clean verify
./mvnw -B spring-boot:build-image

IMAGE=docker.io/library/image-config-demo:1.0.0
docker image inspect "$IMAGE" >/dev/null

cid=$(docker run -d -p 18080:8080 "$IMAGE")
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT

for i in $(seq 1 30); do
    if curl -fsS http://localhost:18080/status > response.txt; then
        break
    fi
    sleep 1
done
test "$(cat response.txt)" = "image-config-ok"
```

This script requires Bash, curl, Docker, Maven Wrapper, and free port 18080. If the app does not become ready, the test fails. Production CI must handle timeouts/readiness and remote Docker daemon networking rather than assuming `localhost` is always the same host.

With Gradle, replace the two Maven lines with `./gradlew clean test bootBuildImage` and keep the inspect/run steps the same. The lab **does not automatically push images** because there is no real registry or learner credentials.

## 24. Practice Exercises

**A. Change `imageName`:** use Maven CLI `-Dspring-boot.build-image.imageName=image-config-demo:trial` or Gradle `--imageName=image-config-demo:trial`. After building, inspect the new reference and explain why the builder/run image remained unchanged.

**B. Add a tag:** use Gradle `tags.set(...)` or `docker tag` after a Maven build; verify both tags point to the same image ID. Explain why adding a tag does not push automatically.

**C. Compare pull policies:** in a test environment with cached images, switch `ALWAYS` to `IF_NOT_PRESENT`; inspect logs and IDs. Then explain why `NEVER` can fail when a base image is missing.

**D. Run image:** remove the `runImage` override and let builder metadata decide. Compare with the illustrative Jammy Base pair and verify stack compatibility; do not switch to a base image from a different stack.

**E. Release trace:** record the image version/commit tag and post-publish digest, explaining why deployments should not rely solely on `latest`.

## 25. Checklist

- [ ] Understand builder, run image, application image, and each one's responsibility.
- [ ] Image name has valid registry/repository/tag; avoid implicit `latest` for releases.
- [ ] Do not confuse image tags with immutable digests.
- [ ] Maven POM uses `<image><name>`; Gradle task uses `imageName`.
- [ ] Maven CLI uses `-Dspring-boot.build-image.imageName`; Gradle CLI uses `--imageName`.
- [ ] Builder contains Java buildpacks matching JDK/architecture.
- [ ] Run image is compatible with builder; know how to let metadata choose it.
- [ ] Clearly understand `ALWAYS`, `IF_NOT_PRESENT`, `NEVER` and their base-image build scope.
- [ ] Do not confuse `pullPolicy` with Kubernetes `imagePullPolicy`.
- [ ] Do not treat `NEVER` as a guarantee of a completely offline build.
- [ ] Gradle additional tags use full references; `docker tag` does not push.
- [ ] `publish=false` for local testing; publish only with a real registry and authorization.
- [ ] Docker daemon/context is correct and the image is inspected via Docker.
- [ ] Java 17 and `BP_JVM_VERSION` match the Paketo buildpack.
- [ ] Built image runs and `GET /status` returns `image-config-ok`.
- [ ] CI archives source commit, dependency graph, builder/run digests, output image digest, and test results.
- [ ] Policy covers base image updates, security testing, and rollback.

**Conclusion:** `name`/`imageName` determines the output name; `tags` adds references; `builder` performs the build; `runImage` provides the runtime base; `pullPolicy` controls pulling **builder/run images only at build time**. A tag is not a digest, a local build is not a publish, and CNB pull policy is not Kubernetes pull policy. Verify along the chain **build → inspect → smoke test → publish → verify digest**.

## References

- [Spring Boot 3.3 — Maven Plugin Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Spring Boot 3.3 — Maven Image API](https://docs.spring.io/spring-boot/3.3/maven-plugin/api/java/org/springframework/boot/maven/Image.html)
- [Spring Boot 3.3 — Gradle BootBuildImage API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootBuildImage.html)
- [Paketo Buildpacks — Builders Reference](https://paketo.io/docs/reference/builders-reference/)
- [Cloud Native Buildpacks](https://buildpacks.io/docs/)
- [Docker — Image Tag](https://docs.docker.com/reference/cli/docker/image/tag/)
- [Docker — Image Inspect](https://docs.docker.com/reference/cli/docker/image/inspect/)
- [Kubernetes — Container Images](https://kubernetes.io/docs/concepts/containers/images/)