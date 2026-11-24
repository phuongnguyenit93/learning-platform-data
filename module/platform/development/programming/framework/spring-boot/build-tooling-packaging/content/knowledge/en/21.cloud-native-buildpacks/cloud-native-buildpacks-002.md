# The Roles of Builder, Buildpack, Lifecycle, and Run Image in Cloud Native Buildpacks

## 1. Context: From a Spring Boot JAR to an OCI Image

In Spring Boot, running `mvn spring-boot:build-image` or `./gradlew bootBuildImage` can package an application into an OCI container image **without writing a Dockerfile**. To understand why this mechanism works, how to change the Java runtime, how to troubleshoot build errors, and how to update images safely, you must distinguish four components of **Cloud Native Buildpacks (CNB)**:

1. **Builder**: an OCI image used *at build time* that packages buildpacks, the lifecycle, a build-time base image, and metadata about the run image.
2. **Buildpack**: software that knows how to detect a type of application, supply runtime/dependencies, assemble launch layers, and describe the startup process.
3. **Lifecycle**: the CNB program that orchestrates analyzing, detecting buildpacks, restoring cache, executing builds, and exporting the OCI image.
4. **Run image**: the OCI base image of the *actual running application*; it provides the OS base and system libraries for the final app image.

Other terms must also be understood accurately: a **platform** is the tool orchestrating CNB (for example, the CNB `pack` CLI, or the integration in the Spring Boot Maven/Gradle plugin); the **build image** provides the OS/build environment of the builder; the **app image** is the deployable output; and the **launcher** is the mechanism that starts the app process in the created image.

### 1.1. Data Flow Diagram

```text
   Java 17 Spring Boot project
      |                     |
  Maven package          Gradle bootJar
      |                     |
      +---- executable JAR/WAR -----+
                                   |
                     CNB platform / Spring Boot plugin
                                   |
                                   v
    +-------------------- BUILDER IMAGE ------------------+
    | Build-time base (OS and build tools)                |
    | Buildpacks (Java, runtime, Spring Boot support...)  |
    | CNB lifecycle binaries and detection order          |
    | Metadata: compatible run images/targets             |
    +-------------------------+---------------------------+
                              |
                    lifecycle orchestrates
          ANALYZE → DETECT → RESTORE → BUILD → EXPORT
                              |
                              v
      +--------------- FINAL OCI APP IMAGE ---------------+
      | Run-image base layers: OS/system libraries        |
      | Launch layers: JVM/JRE, app, dependencies         |
      | CNB launch process / image configuration          |
      +-------------------------+-------------------------+
                                |
                      Docker/Kubernetes runtime
                                |
                     Spring Boot controller
```

**Key takeaway to memorize:** the builder is the *image-making environment*; the run image is the *image-running foundation*. The buildpack performs the specialized work; the lifecycle is the orchestrator. In Java buildpacks, the JVM/JRE is usually provided as a **buildpack launch layer**, not necessarily already present in the original run image. Do not equate “run image” with “JDK image”.

### 1.2. Distinguishing Them in a Table

| Object | Nature | Present in runtime app image? | Example work |
|---|---|---|---|
| Builder | OCI image for building | The entire builder is not carried over | Distributes Java buildpacks + lifecycle |
| Buildpack | Detect/build software | Launch layers it creates may be carried over, not the raw build tool | Selects JVM, creates start command |
| Lifecycle | CNB-standard executables | Build-phase binaries are not the app server; launcher may appear | Analyze, detect, restore, build, export |
| Run image | Runtime base OCI image | Base layers **are** in the app image | OS and shared system libraries |
| Build image | Build-time foundation | Not exported to final app image by default | Environment for buildpacks to run |
| Platform | Orchestrator calling lifecycle | Not the runtime application | Maven/Gradle CNB integration, `pack` |
| App image | Final OCI artifact | It itself is the deployable output | `docker run cnb-roles-lab:0.0.1` |

## 2. Builder: The Image Providing the Context to Create an Image

According to the CNB specification, a builder is **an OCI image** containing a build-time base image, a set of buildpacks arranged in detection order, lifecycle binaries, and references to a runtime base image. It is neither a Maven plugin JAR nor the final product to `docker run` as a Spring Boot application.

### 2.1. What Does a Builder Contain?

```text
builder image
├── build-time base filesystem
├── lifecycle executables
├── buildpacks/
│   ├── buildpack A (detect + build)
│   ├── buildpack B (detect + build)
│   └── ...
├── detection order / groups
├── buildpack/lifecycle API metadata
└── run image references / compatibility metadata
```

This is a **conceptual diagram**, not a strict directory tree required for every builder. Runtime image metadata generally does not mean the entire run image sits inside the builder filesystem; the CNB platform still fetches the run image when creating the app image.

With Spring Boot Maven/Gradle Plugin **3.5.16**, the documentation lists the default builder:

```text
paketobuildpacks/builder-noble-java-tiny:latest
```

This is a Paketo builder using Ubuntu Noble and Java buildpacks. The `:latest` suffix **can change content over time**. This lesson may use it to explore features; in important releases, pin the builder by an approved digest/version and record the actual dependency/buildpack versions.

### 2.2. Not Every Buildpack Runs

A builder can contain many buildpacks or **composite buildpacks**. The lifecycle runs **detect** across order groups and selects a set of buildpacks satisfying the application's conditions. Therefore:

- A builder having 20 buildpacks does **not** mean all 20 build every application.
- A builder supporting Java does **not** mean it knows how to handle every custom Java format.
- A Java app may require multiple small buildpacks: supplying the JVM, analyzing the archive, setting CA certificates, and setting the startup command.
- Specifying a custom buildpack via a `buildpacks` override can **replace the default set**, causing detection to miss buildpacks needed for Java.

### 2.3. How to Choose a Builder

Review your project requirements:

- Supports the Java version, framework, and `jar/war` artifact type.
- Supports the target OS/architecture of CI and deployment infrastructure: `linux/amd64`, `linux/arm64`...
- Has a compatible lifecycle and Buildpack/Platform API.
- Has a compatible run image; satisfies system/native library requirements.
- Is approved by the organization, patched for security CVEs, and publishes SBOM/source.
- Can be pulled from the registry in CI without requiring excessive permissions.
- Allows selecting the build-time/runtime options the application genuinely needs.

A **tiny image** can save space but lacks a shell or certain system libraries. If the app depends on shell scripts, fonts, or native libraries, do not assume a tiny builder/run image is sufficient. Check builder documentation and test the real image.

### 2.4. Inspecting a Builder with pack

If `pack` CLI is available:

```bash
pack builder inspect paketobuildpacks/builder-noble-java-tiny:latest
```

Output can list **Buildpacks**, **Detection Order**, **Lifecycle**, **Run Images**, and compatibility metadata. This is the first step to finding the right builder or viewing the run image it references. Do not hardcode individual buildpack/lifecycle versions in test scripts because `:latest` changes.

## 3. Buildpack: The Worker Performing Technical Tasks

A buildpack is the CNB component that turns application input into the parts needed for an OCI image. A typical buildpack has this structure:

```text
buildpack/
├── buildpack.toml
└── bin/
    ├── detect
    └── build
```

`buildpack.toml` contains the ID, name, and version/API metadata. `bin/detect` determines whether it should participate in the build; `bin/build` creates or reuses layers and configures the launch environment and process metadata.

### 3.1. Detect Phase

During detect:

1. The lifecycle retrieves the detection order from the builder.
2. It evaluates buildpack groups in order.
3. Each buildpack can declare **provides/requires** in the build plan.
4. When a compatible group is found, the lifecycle selects those buildpacks to build.
5. If no group matches, the process stops with a detection error.

For example: a Spring Boot JAR packaged by Maven is passed into the Java builder. Paketo Java buildpacks can recognize the archive type, choose the runtime, and configure the appropriate startup mechanism. **Detect does not always compile source**; with `spring-boot:build-image`, Maven already prepared the artifact before CNB runs. If using `pack build --path .` with a source directory, the builder's buildpacks may handle compilation as well.

### 3.2. Build Phase

The selected buildpacks can:

- Download/provide a suitable Java runtime.
- Prepare the start process for a Spring Boot executable archive.
- Analyze dependencies and create launch layers.
- Set build-time/runtime environment variables.
- Produce metadata for cache, SBOM, or launch configuration.
- Reuse layers from cache if buildpack conditions allow.

**Do not confuse a buildpack with a builder image:** `paketo-buildpacks/java` is a buildpack/composite buildpack; `paketobuildpacks/builder-noble-java-tiny:latest` is an OCI builder containing or referencing a suite of buildpacks; the run image is yet another OCI image.

### 3.3. Configuring a Buildpack via Environment

With Paketo Java buildpacks:

```text
BP_JVM_VERSION=17
```

is an example variable selecting the Java version. Spring Boot Maven passes variables in `<image><env>`, while Gradle uses `tasks.named('bootBuildImage') { environment[...] }`.

**Do not confuse** the buildpack's `BP_JVM_VERSION` variable with `JAVA_TOOL_OPTIONS` that the JVM reads at runtime. Some buildpacks support `BPE_*` variables to write changes to the runtime environment; variables only have meaning when supported by the corresponding buildpack.

If `BP_JVM_VERSION` requests a version that the builder/buildpack does not provide, the build phase may fail; do not try to fix it by changing the output image tag.

## 4. Lifecycle: Orchestrating the Five OCI Image Creation Phases

The **CNB lifecycle** is a set of executables with a unified protocol for platforms to invoke buildpacks and export images. It **differs from**:

- Maven lifecycle: `validate → compile → test → package → verify`.
- Gradle task graph: `compileJava`, `bootJar`, `bootBuildImage`.
- Spring application lifecycle: bean creation, ApplicationContext, and request handling.

The five-phase flow described by CNB documentation:

```text
ANALYZE → DETECT → RESTORE → BUILD → EXPORT
```

| Phase | Function | Signals to check on failure |
|---|---|---|
| **Analyze** | Checks metadata/previous app image, image/registry access permissions, run image info | Auth, network, image references, registry/daemon |
| **Detect** | Selects a compatible buildpack group, creates build plan | Builder order, artifact type, buildpack requirements |
| **Restore** | Restores reusable cache/layers/metadata | Cache key, previous image, write permissions, restore logs |
| **Build** | Calls `bin/build` of selected buildpacks, creates launch/build layers | JVM version, JDK download, app archive, buildpack env |
| **Export** | Combines run-image base with launch layers and metadata, exports OCI image | Run image, image layers, registry push, disk/permissions |

Some very old CNB docs describe **analyze/restore** differently: in newer Platform APIs, analyze runs **before detect** to check registry access early; much of cache restoration happens in restore. When debugging, cross-check the actual builder's lifecycle/Platform API rather than assuming all versions behave identically.

### 4.1. Analyze

The analyze phase reads info related to the previous image/run image and helps verify that the platform has permission to read/write the required OCI resources. If no previous build exists, previous metadata may be absent; that is not an error.

If the build stops at `ANALYZING`, check the image name, auth, Docker context, registry, and proxy before editing Java source.

### 4.2. Detect

The detect phase decides **which buildpacks participate**, following the builder's detection order. If `No buildpacks participating` or `failed to detect` appears, check:

- Does the builder contain a Java buildpack?
- Is the input the source/JAR type supported by the builder?
- Did a custom buildpacks list override omit required dependencies?
- Is the target architecture/OS compatible?
- Do the Buildpack/Platform APIs accept the current lifecycle?

### 4.3. Restore

The restore phase finds and restores cached layers for buildpacks when possible. For example, unchanged JVM/dependency layers can be reused. Not every layer is cacheable; nor is a second build guaranteed to be faster if the image name, cache, or builder changed.

### 4.4. Build

The lifecycle runs `bin/build` for the selected buildpacks. In a Java app, buildpacks can supply the runtime and launch layers. The binary named **builder** used for the CNB build phase **is not the builder image**; one is a lifecycle executable, the other is the environment OCI image.

### 4.5. Export

The exporter takes base layers from the **run image**, combines them with **launch layers**, builds image config/labels/process metadata, and exports the image. Output can reside in the local Docker daemon or a registry depending on platform/publish settings. This is the **deployable image**, not an exact copy of the builder image.

### 4.6. Creator, Launcher, Rebaser

- **Creator** can run all five phases in a single invocation when the platform uses that mode (e.g., trusted builder); it is not a sixth phase.
- **CNB launcher** is the component inside the final image that launches the application process. It differs from `org.springframework.boot.loader.launch.JarLauncher` inside an executable Boot JAR.
- **Rebaser** helps update the run image base when a new compatible version is available without rebuilding application layers.
- Image extensions, if used, have their own mechanism; they are not needed for a simple Spring Boot example.

## 5. Run Image: Operating System Foundation for the Application

The **run image** provides the foundation of the final app image: OS runtime, system libraries, and user/base filesystem needed for the application to run. In modern CNB, a builder has metadata referencing compatible run images/targets, and the platform uses the default from there unless overridden by the developer.

Key point: **the run image does not necessarily contain a JVM**. The JVM/JRE may be added by the Paketo Java buildpack as a **launch layer**. Therefore, you cannot check the Java version just by looking at the run image name.

### 5.1. How the Build Image Differs from the Run Image

| Question | Build image | Run image |
|---|---|---|
| Which stage uses it? | CNB build | Application runtime |
| Contains lifecycle/buildpacks in builder? | Builder contains and executes them | Not needed |
| Needs compiler/build dependencies? | Possibly | Not required |
| Is it the OS base of the deployed image? | No | Yes |
| Might it lack a shell? | Depends on build image | Yes, tiny runtimes usually lack a shell |
| Must it match CPU/OS? | Yes | Yes |
| Does changing it affect rebuild/cache? | Yes | Yes; rebase may be considered |

### 5.2. Where Does the Default Run Image Come From?

Spring Boot 3.5 Maven/Gradle Plugin docs state that `runImage` is **not set** by default: the platform uses the run image declared in the **builder metadata**. Thus, a simple configuration only needs to choose the builder:

```text
builder = paketobuildpacks/builder-noble-java-tiny:latest
runImage = (not overridden: use builder metadata)
```

Do not guess an image name from the builder name. Run:

```bash
pack builder inspect paketobuildpacks/builder-noble-java-tiny:latest
```

to read **Run Images** and mirror choices if any. Registry mirrors help fetch the run image closer to the output registry when appropriate; they do not change the nature of the runtime base.

### 5.3. Overriding the Run Image Only When Truly Needed

Spring Boot 3.5 documentation notes that the tiny builder has no shell and limited system libraries. For broader runtime needs, the docs give `paketobuildpacks/ubuntu-noble-run:latest` as an example. Illustrative Maven command:

```bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.runImage=paketobuildpacks/ubuntu-noble-run:latest
```

**Use only when the current builder and new run image are compatible.** Do not pick an arbitrary Alpine or Ubuntu run image; check OS/architecture, libc/system libraries, and target metadata. A different run image may require compatible Java launch layers/native dependencies for the app to work.

### 5.4. Stack and Targets

Older CNB docs used **stack** as a pair of build/run images sharing a **stack ID**. CNB now marks stack as **deprecated** and uses **targets** to describe compatibility, including:

- OS name, e.g., Linux.
- Architecture, e.g., amd64 or arm64.
- OS distribution name, version, and other target details.

Hence, checking the actual metadata of the builder/run image matters more than comparing a stack ID string from legacy documentation.

### 5.5. Tiny Run Images May Lack a Shell

An image still runs Spring Boot normally via the CNB launcher even without `/bin/sh`. Running:

```bash
docker run --rm --entrypoint /bin/sh cnb-roles-lab:0.0.1
```

can fail with a tiny runtime; this is **not a bug in the Java controller or CNB detect**. If the application requires a shell script at startup, change the launch strategy or select a broader run image supported by the builder. Do not rely on `apt-get` inside the final tiny container to fix a build.

## 6. Maven/Gradle/pack Are Integration Platforms, Not Buildpacks

| Build path | Typical CNB input | How to run |
|---|---|---|
| Maven Spring Boot | Executable JAR/WAR produced by Maven/plugin | `mvn spring-boot:build-image` |
| Gradle Spring Boot | `bootJar` or `bootWar` artifact | `./gradlew bootBuildImage` |
| CNB pack CLI | Source directory or app input per config | `pack build ... --builder ...` |

The Maven/Gradle plugin acts as the CNB orchestrator: taking the archive, builder, run image, cache, and env, then invoking the lifecycle/engine. **The Maven plugin is not a Java buildpack.** Conversely, a Java buildpack does not inherently know how Maven `pom.xml` should be configured in a multi-module reactor if the platform only passes it the final archive.

**No Dockerfile is needed** when using the CNB Spring Boot plugin, but a **Docker daemon/API is still required** per the 3.5 plugin documentation; Dockerfile-free differs from Docker-free. `docker info` helps verify the engine/connection when debugging.

## 7. Java 17 + Spring Boot 3.5.16 Example with Maven

The example creates a small web service so the image can be verified via HTTP. Spring Boot **3.5.16** and Java **17** are pinned for the lesson and do not represent “latest” for all projects. Requires JDK 17+, compatible Maven or existing Maven Wrapper, a running Docker Engine/daemon, and enough network/cache to download dependencies, builder, and runtime images.

### 7.1. Directory Tree

```text
cnb-roles-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/cnb/
    │   ├── CnbRolesApplication.java
    │   └── RolesController.java
    └── test/java/com/example/cnb/
        └── RolesControllerTest.java
```

If the project includes the Maven Wrapper, the root also has `mvnw`, `mvnw.cmd`, and `.mvn/wrapper/...`. Simply writing a POM does **not** create the Wrapper automatically; you can use an installed Maven.

### 7.2. Complete pom.xml

```xml
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
    <artifactId>cnb-roles-lab</artifactId>
    <version>0.0.1</version>

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
                        <name>cnb-roles-lab:0.0.1</name>
                        <builder>paketobuildpacks/builder-noble-java-tiny:latest</builder>
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

Meaning:

- The parent manages versions for starters/plugins and configures `repackage` when the app declares the Boot plugin.
- `spring-boot-starter-web` provides the HTTP server and Spring MVC.
- `<builder>` selects the **builder OCI image**.
- `<name>` is the **final app image name**, not the builder.
- `<env><BP_JVM_VERSION>17` passes the Java version to Paketo buildpacks.
- `runImage` is not overridden: uses the run image from builder metadata.
- `buildpacks` is not overridden: preserves the builder's detection order.
- Builder `:latest` changes; pin a digest in production.

### 7.3. Java Main Class

`src/main/java/com/example/cnb/CnbRolesApplication.java`:

```java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbRolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(CnbRolesApplication.class, args);
    }
}
```

### 7.4. HTTP Controller with Deterministic Response

`src/main/java/com/example/cnb/RolesController.java`:

```java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RolesController {
    @GetMapping("/roles")
    public String roles() {
        return "CNB roles: OK\n";
    }
}
```

A GET `/roles` request returns the body `CNB roles: OK` and a newline character. Java code **does not need to import Docker or CNB APIs**: image packaging responsibility belongs to the build tool/buildpacks.

### 7.5. JUnit Jupiter Test

`src/test/java/com/example/cnb/RolesControllerTest.java`:

```java
package com.example.cnb;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RolesControllerTest {
    @Test
    void returnsKnownValue() {
        assertEquals("CNB roles: OK\n", new RolesController().roles());
    }
}
```

The unit test only verifies controller logic, does not open an HTTP port, and does not replace a container smoke test. `spring-boot-starter-test` provides JUnit Jupiter via Spring Boot's dependency management.

### 7.6. Building with Maven and Exporting the Image

From the project root, when the Maven Wrapper is present:

```bash
# Before building:
java -version
docker info

# Run Java tests, package executable JAR:
./mvnw clean package

# Build OCI image using CNB:
./mvnw spring-boot:build-image

# Inspect created image in Docker daemon:
docker image inspect cnb-roles-lab:0.0.1
```

If there is no Maven Wrapper, replace `./mvnw` with `mvn`. On Windows PowerShell, use `.\mvnw.cmd`.

The `spring-boot:build-image` goal **automatically ensures the package lifecycle runs if needed**, so it can be called directly once the plugin is configured. Running `clean package` separately is for demonstration and testing, not a strict requirement every time build-image is called. If you want to bind the goal to `package`, Spring Boot has `build-image-no-fork` for executions, unlike direct CLI usage.

Log phases that may appear:

```text
===> ANALYZING
===> DETECTING
===> RESTORING
===> BUILDING
===> EXPORTING
```

These are **phase names for identification**, not a guarantee of full or character-exact output for every builder version.

### 7.7. Running the Container and Testing HTTP

```bash
docker run --rm -p 8080:8080 cnb-roles-lab:0.0.1
```

From a second terminal once the application is ready:

```bash
curl -fsS http://localhost:8080/roles
```

The **exact** HTTP body produced by the controller:

```text
CNB roles: OK
```

The body has a trailing newline. Spring Boot startup logs/HTTP headers are not listed above. If host port 8080 is already in use, run an **alternative** container with:

```bash
docker run --rm -p 18080:8080 cnb-roles-lab:0.0.1
```

and call `http://localhost:18080/roles`. In `-p 18080:8080`, the first side is the host port and the second is the container port; no need to change `server.port` in the Java app.

### 7.8. Inspecting Who Built the Image and on Which Base

```bash
# User/entrypoint info of final image:
docker image inspect cnb-roles-lab:0.0.1 \
  --format '{{json .Config.User}} {{json .Config.Entrypoint}}'

# View layer history:
docker history cnb-roles-lab:0.0.1

# If CNB pack CLI is available:
pack inspect-image cnb-roles-lab:0.0.1
```

In PowerShell, write the inspect command on one line. In `pack inspect-image`, check **Buildpacks**, **Run Images**, **Processes**, **Rebasable** (if provided), and related metadata. Actual buildpack/run image versions depend on the actual `:latest` builder, so no “guaranteed” output is claimed here.

`docker history` and `docker image inspect` are OCI image reading tools and do **not fully replace** CNB metadata. Do not infer which builder produced an app image from layer names alone; cross-check logs, image labels, and `pack inspect-image`.

## 8. Equivalent Gradle Example

Keep the same Java/JUnit files from section 7; if using Gradle, replace the Maven POM with `settings.gradle` and Groovy DSL `build.gradle`.

`settings.gradle`:

```groovy
rootProject.name = 'cnb-roles-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '0.0.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    imageName = 'cnb-roles-lab:0.0.1'
    builder = 'paketobuildpacks/builder-noble-java-tiny:latest'
    environment['BP_JVM_VERSION'] = '17'
    // Do not set runImage: take default from builder metadata.
}
```

With an **existing Gradle Wrapper**, a Gradle version compatible with Spring Boot 3.5, and an available Docker daemon:

```bash
./gradlew test
./gradlew bootBuildImage
docker image inspect cnb-roles-lab:0.0.1
docker run --rm -p 8080:8080 cnb-roles-lab:0.0.1
```

On Windows, use `.\gradlew.bat` instead of `./gradlew`. `bootBuildImage` uses the appropriate `bootJar`/`bootWar` output, but **does not automatically prove all unit/integration tests ran** if CI only invokes the image build task. Running `test` explicitly is therefore a deliberate QA step.

### 8.1. Overriding runImage in Gradle When Needed

This is a **replacement block for the `bootBuildImage` block above**, to be used only after verifying compatibility:

```groovy
tasks.named('bootBuildImage') {
    imageName = 'cnb-roles-lab:0.0.1'
    builder = 'paketobuildpacks/builder-noble-java-tiny:latest'
    runImage = 'paketobuildpacks/ubuntu-noble-run:latest'
    environment['BP_JVM_VERSION'] = '17'
}
```

If a shell or additional OS libraries are needed, a broader run image can be suitable. However, changing `runImage` alone does not automatically add runtime libraries for every native app system; smoke tests and OS/target checks are still required.

### 8.2. Kotlin DSL

In Gradle `build.gradle.kts`, the task configuration block can be written as:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("cnb-roles-lab:0.0.1")
    builder.set("paketobuildpacks/builder-noble-java-tiny:latest")
    environment.put("BP_JVM_VERSION", "17")
}
```

This is a **Kotlin DSL snippet to insert into an appropriate build script**, not a complete `build.gradle.kts`. Unlike Groovy DSL, Gradle Properties in Kotlin require `.set(...)` and `.put(...)`. Do not mix the two DSLs in the same file.

## 9. `pack` CLI and Selecting Buildpacks Directly

`pack` is the CNB platform CLI. If a developer wants to test a builder independently of the Spring Boot Maven/Gradle integration, a typical command is:

```bash
pack build cnb-roles-source:0.0.1 \
  --builder paketobuildpacks/builder-noble-java-tiny:latest \
  --path .
```

Here `--path .` means the source directory. The result depends on whether the builder has buildpacks that recognize a **source project**; this differs from the Spring Boot plugin providing an **executable JAR** as input. Do not assume `pack` builds identically to the Maven plugin simply from the same source.

Flag concepts:

- `--builder`: selects the OCI builder.
- `--buildpack`: selects specific buildpacks, which can alter the default detection order.
- `--env BP_JVM_VERSION=17`: configures the corresponding buildpack.
- `--run-image` (when supported by the tool/version): selects a run image instead of the default.
- `pack builder inspect`: inspects a builder.
- `pack inspect-image`: inspects CNB metadata of an app image.

**Be careful** when overriding `--buildpack` or `<buildpacks>`: Spring Boot Plugin documentation confirms that if this list is provided, only the specified buildpacks are used, without automatically including every default buildpack in the builder. A list missing the Java runtime or startup support can cause detect/build to fail.

## 10. Cache: Faster Rebuilds, Not the Run Image

The CNB lifecycle can restore cached layers from a previous image/cache when rebuilding. For Java:

- Unchanged JRE and dependencies can be reused.
- Changing application classes usually causes application layers to be rebuilt/re-exported.
- Layer cache hits/misses are determined by the buildpacks themselves and the platform cache configuration.

Logical example:

```text
Run 1: analyze → detect → restore (empty cache)
      → build runtime/app launch layers → export

Run 2: analyze → detect → restore (reuse valid layers)
      → build changed parts → export
```

**There is no guarantee the second build is always faster.** Cache misses occur when changing the builder, Java version, image name, cache volume, CI Docker daemon, or when metadata/layer contents change. Spring Boot Gradle Plugin documentation notes that default cache volume names can depend on the **full output image name**; frequently changing tags impacts reuse.

| Concept | Meaning |
|---|---|
| Build cache | Reuses results/layers to reduce build work |
| Launch layer | Content used when the app runs, such as JRE/app dependencies |
| Run-image layer | OS base layers of the app image |
| Image tag | Mutable reference name pointing to content |
| Image digest | Immutable content-addressable identifier |
| Reproducibility | Same controlled inputs producing equivalent output |

Do not use `:latest`, dynamic dependency versions, and uncontrolled timestamps and then claim byte-for-byte reproducible builds. For release governance, record builder/run image digests, buildpack versions, and the final image digest.

## 11. Rebase: Updating the Runtime Base Without Rebuilding App Layers

**Rebase** allows replacing **run-image base layers** with a new compatible version without re-running all buildpacks or recompiling source, provided image metadata and policy permit it.

```text
Before: App image = run image A + JVM/JAR launch layers
After:  App image = run image B + JVM/JAR launch layers
                    (only if B is compatible and image is rebasable)
```

Rebase is useful when the OS runtime base receives security patches. However:

1. Rebase does **not** change Java source, bytecode, or the Spring Boot version.
2. Rebase does **not automatically change the JVM** if the JVM is a buildpack launch layer sitting on top of the run image.
3. Not every OCI image is `Rebasable`.
4. The new run image must be compatible with the targets, OS/architecture, and native dependencies.
5. Smoke tests, CVE scans, and release/rollback policies are still required after rebase.
6. Do not use rebase in place of a build process when the application or JDK changes.

Check metadata:

```bash
pack inspect-image cnb-roles-lab:0.0.1
```

Look for `Rebasable`, `Run Images`, and related metadata. Do not run `pack rebase` on a production tag without a backup/rollback policy. When needed in a test environment, CNB provides `pack rebase` per official documentation to update the compatible runtime base.

## 12. Security and Operations

### 12.1. Non-Root and File Permissions

Spring Boot documentation on CNB emphasizes that images are built and run under **non-root users** for safety. Consequently:

- The container may not be able to write to the root filesystem or certain directories.
- When output is needed, use a writable volume/path and set proper ownership.
- Do not enable root just to “make it run” when containerizing an application.
- Ensure Kubernetes `securityContext` settings are compatible with the user/process created by the image.

### 12.2. Builders/Buildpacks Execute Code During the Build

Builders and buildpacks are software running in the build environment and can access supplied files/network/bindings/secrets. Therefore:

- Use builder sources approved by the organization.
- Pin digests and verify signatures/provenance as needed.
- Restrict registry credentials, build-time secrets, network access, and writable mounts.
- Review `trustBuilder` in the Spring Boot plugin and only trust builders compliant with policy.
- Avoid putting passwords/tokens in POMs, Gradle build scripts, launch layers, or logs.
- Collect SBOM, image digest, buildpack metadata, and security scans before deploying.

### 12.3. Tiny Runtimes May Lack a Shell and System Libraries

Do not treat `docker exec ... /bin/sh` as a mandatory check for every CNB image. With the Noble Java Tiny builder, lacking a shell can be an **intended characteristic of the image**. If the app runs a startup shell script or invokes a native binary, choose a compatible runtime base with the necessary libraries or change the launch process.

### 12.4. Runtime Configuration Differs from Build-Time Configuration

- `BP_JVM_VERSION`: configures Java runtime selection **during buildpack build**.
- `JAVA_TOOL_OPTIONS`: JVM options when the launch process runs (depending on buildpack integration).
- `SPRING_PROFILES_ACTIVE`, `SERVER_PORT`, and secrets: runtime environment for Spring Boot.
- `BPE_*`: some Paketo buildpacks support baking launch environment changes into the image.

Do not assume every buildpack/vendor understands the same variables. If sensitive data is only needed at runtime, prefer supplying it via Kubernetes Secret/secret manager, **never bake it into OCI layers**.

## 13. Troubleshooting by Phase

| Symptom | Likely Layer | What to Check |
|---|---|---|
| Cannot connect to Docker daemon | Platform/engine | `docker info`, context, socket/TLS |
| Cannot pull builder | Builder/registry | Name, tag/digest, registry auth, proxy |
| `No buildpacks participating` | Detect | Does builder support Java? Is source/JAR artifact valid? |
| `Failed to detect` after specifying custom buildpacks | Buildpack order | Revert to builder defaults or include all required buildpacks |
| JRE 17 not found | Buildpack/runtime provisioning | `BP_JVM_VERSION`, buildpack version, network |
| `UnsupportedClassVersionError` when app runs | Launch JVM lower than bytecode target | Java toolchain and JVM launch layer |
| `ANALYZING` error | Registry/previous-image permissions | Auth, image references, metadata |
| `RESTORING` error | Cache/workspace | Disk, volume, permissions, try intentional clean cache |
| `BUILDING` error downloading artifact | Buildpack/network | Proxy, TLS certificate, outbound allowlist |
| `EXPORTING` error | Run image/registry/disk | Disk quota, pull/run compatibility, push privileges |
| Run image override rejected | Incompatible targets/stack | Builder metadata and run-image architecture |
| App image lacks `/bin/sh` | Tiny run image | Change launch method or compatible run image |
| No `docker image inspect` output | Image not exported to local daemon | Check publish/local engine, image name/tag |
| HTTP `/roles` returns nothing | Runtime/Boot app | `docker logs`, container port mapping, startup errors |
| `docker run` reports port in use | Host port conflict | `-p 18080:8080`, check other services |
| Rebase won't run | Image not rebasable or run image mismatch | `pack inspect-image`, compatibility |
| JRE CVE remains after rebase | JRE is in a launch layer | Upgrade buildpack/JVM and rebuild image |
| Build after code edit still shows old behavior | Wrong artifact/image tag/cache | Check source commit, JAR, image digest |
| Tiny run image missing native lib | OS/runtime compatibility | Choose compatible run image with system libs |
| CI says build succeeded but registry is empty | Publish not enabled or wrong auth | `publish`/`publishImage`, registry URL |
| No Dockerfile | CNB does not need a Dockerfile | Use CNB build-image, not an error |

### 13.1. Reading Logs in Order

1. **Before ANALYZING**: Maven/Gradle compile/test, Docker daemon, builder pull.
2. **ANALYZING**: image/registry access and previous metadata.
3. **DETECTING**: builder buildpacks, group selection, artifact type.
4. **RESTORING**: cache metadata/layers.
5. **BUILDING**: Java runtime download, buildpack logic, image layers.
6. **EXPORTING**: OCI image assembly, run image, disk/registry permissions.
7. **After build, during docker run**: CNB launcher, runtime OS/JVM, Spring Boot application logs.

This is a **heuristic**, not a proof system that an error has only one cause. Read the root error, inspect the image being used, and compare against the actual build configuration.

## 14. Recommended Workflow for CI/CD and Production

1. Verify Java compile, unit/integration tests, and dependency policies.
2. Build executable JAR/WAR from the exact source commit (Maven/Gradle).
3. Choose an approved builder, pin version/digest, and verify Java support.
4. Keep the run image from builder metadata, or override **only** with justification and compatibility tests.
5. Pass build-time environment properly; restrict secrets.
6. Run `spring-boot:build-image` or `bootBuildImage`; observe the five lifecycle phases.
7. Inspect output image: buildpacks, run image, user/entrypoint, architecture, and digest.
8. Run the real image and smoke test HTTP, health, environment, and filesystem permissions.
9. Scan image/SBOM and sign/attest per infrastructure requirements.
10. Push image with explicit tag/digest; deploy exact immutable digest.
11. When the run image gets patches, evaluate rebase if the image is rebasable/compatible; when Java/app changes, rebuild.
12. Archive records of builder/run image refs, buildpacks, lifecycle versions, image digest, test reports, and deployment results.

**Build-image SUCCESS does not prove the image ran successfully or was deployed.** Output must pass smoke tests and operational verification.

## 15. Self-Check Exercises

### Exercise 1: Pick the Right Object

Suppose:

```text
Builder:   paketobuildpacks/builder-noble-java-tiny:latest
Buildpack: Paketo Java
Lifecycle: analyze/detect/restore/build/export
Run image: run image provided by builder metadata
Output:    cnb-roles-lab:0.0.1
```

**Question:** Which image goes to production? **Answer:** the app image `cnb-roles-lab:0.0.1` (preferably by digest); do **not** deploy the builder image. The runtime base OS comes from the run image; launch layers may contain the JVM and app.

### Exercise 2: Correct the Misconception

> “I set `BP_JVM_VERSION=17`, so the run image definitely has JDK 17 installed.”

**False:** this variable instructs the buildpack which Java version to select. The JVM usually resides in a buildpack launch layer; the run image is the OS and system libraries foundation. Verify the JVM in the output via logs and runtime behavior.

### Exercise 3: Distinguish Cache and Rebase

- Cache makes **rebuilding faster** when layers can be reused.
- Rebase **updates the run-image base** without rebuilding app layers when compatible.
- Changing a Java controller requires a **rebuild**.
- Changing the major Java runtime requires a **buildpack/JVM layer rebuild**; rebasing the OS base alone is insufficient.

### Exercise 4: Identify the Failing Phase

- `DETECTING` fails → does the builder have a Java buildpack and is the artifact valid?
- `BUILDING` fails downloading JRE → network/Java version/buildpack.
- `EXPORTING` fails → run image, disk, registry/daemon.
- `docker run` fails due to missing shell → tiny runtime/launch process, not necessarily a Java code error.

## 16. End-of-Lesson Checklist

- [ ] Distinguish between builder image and final app image.
- [ ] Know that a builder contains buildpacks, lifecycle, build base, and run image metadata.
- [ ] Know that a buildpack has `detect` and `build`, and can create Java launch layers.
- [ ] Know the five lifecycle phases `analyze → detect → restore → build → export`.
- [ ] Do not confuse CNB lifecycle with Maven lifecycle or Spring Boot ApplicationContext.
- [ ] Know that the run image is the runtime OS base, not synonymous with a JDK image.
- [ ] Know that the default run image is selected via builder metadata.
- [ ] Know `pack builder inspect` and `pack inspect-image`.
- [ ] Know that Maven `spring-boot:build-image` and Gradle `bootBuildImage` are integrations/platforms, not buildpacks.
- [ ] Know that `BP_JVM_VERSION` differs from JVM runtime options.
- [ ] Do not demand a Dockerfile when using CNB, yet still check the Docker daemon.
- [ ] Check builder/run compatibility, OS/architecture, and native libraries.
- [ ] Understand that tiny images may lack `/bin/sh`.
- [ ] Understand that cache reuse, image digest, reproducibility, and rebase are distinct concepts.
- [ ] Do not assume rebase automatically replaces Java source or the JRE launch layer.
- [ ] Have run Java tests, image build, and HTTP smoke tests on the real image.
- [ ] Have non-root policy, secret handling, builder provenance, and image scanning in place for releases.

**Conclusion:** The CNB **builder** is the image-building environment, the **buildpack** is the component knowing which JVM/app layers to provide, the **lifecycle** is the program orchestrating image creation phases, and the **run image** is the runtime foundation of the deployed OCI image. Identifying these four roles accurately is the prerequisite for configuring Spring Boot build-image, diagnosing errors, controlling cache/rebase, and operating traceable containers.

### Official Documentation

- [Cloud Native Buildpacks — Builder](https://buildpacks.io/docs/for-app-developers/concepts/builder/)
- [Cloud Native Buildpacks — Buildpack](https://buildpacks.io/docs/for-app-developers/concepts/buildpack/)
- [Cloud Native Buildpacks — Lifecycle](https://buildpacks.io/docs/for-platform-operators/concepts/lifecycle/)
- [Cloud Native Buildpacks — Run Image](https://buildpacks.io/docs/for-app-developers/concepts/base-images/run/)
- [Cloud Native Buildpacks — Build Image](https://buildpacks.io/docs/for-app-developers/concepts/base-images/build/)
- [Cloud Native Buildpacks — Rebase](https://buildpacks.io/docs/for-app-developers/concepts/rebase/)
- [Cloud Native Buildpacks — Inspect App Image](https://buildpacks.io/docs/for-app-developers/how-to/build-outputs/inspect-app/)
- [Cloud Native Buildpacks — Targets](https://buildpacks.io/docs/for-buildpack-authors/concepts/targets/)
- [Cloud Native Buildpacks — Builder Config](https://buildpacks.io/docs/reference/config/builder-config/)
- [Spring Boot 3.5 — Maven Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html)
- [Spring Boot 3.5 — Gradle Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html)
- [Paketo Noble Java Tiny Builder](https://github.com/paketo-buildpacks/builder-noble-java-tiny)
