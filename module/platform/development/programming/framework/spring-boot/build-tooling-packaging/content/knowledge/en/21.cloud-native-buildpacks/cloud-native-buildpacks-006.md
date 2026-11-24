# Building Images with Gradle `bootBuildImage` in Spring Boot with Cloud Native Buildpacks

## 1. Objectives and Expected Outcomes

`bootBuildImage` is a task of the **Spring Boot Gradle Plugin** that uses **Cloud Native Buildpacks (CNB)** to convert an application's executable JAR/WAR into an **OCI container image**, without writing a Dockerfile manually. The resulting image can be run locally by Docker or pushed to a registry for deployment on Docker, Kubernetes, or any compatible container platform.

After this lesson, you should be able to:

1. Understand **Gradle task → executable archive → CNB builder/buildpacks → OCI image**; distinguish builder image, run image, and output application image.
2. Create a valid Spring Boot Java 17 project, run JUnit tests, and use `./gradlew bootBuildImage` to generate an image.
3. Verify the Docker daemon, image name, tag, layer metadata, and invoke the `/hello` endpoint from the container.
4. Configure `imageName`, `builder`, `runImage`, `BP_JVM_VERSION`, runtime JVM options, and platform selection when needed.
5. Distinguish **local image build** from **registry publish**; manage Docker credentials securely.
6. Understand buildpack caching, image structure, layer reuse effectiveness, and the limitations of changing image tags.
7. Troubleshoot common errors: Docker connection failures, incompatible builder/run images, wrong Java versions, registry authorization, wrong architecture, buildpack detection, or misconfigured native-image setups.

**Version scope of examples:** Spring Boot **3.5.16**, Java **17**, Gradle Wrapper **8.14.3**, and an **accessible Docker Engine**. Default builder names/versions change across Spring Boot releases; when using Boot 4.x or a different Gradle major version, consult documentation for that exact version instead of copying assumptions. Commands are instructions to run in an environment with Java/Docker installed; the lesson does not assume Docker is already running on the reader's machine.

**Keep in mind right away:** `bootBuildImage` is **not** a standalone Gradle Docker task, **does not require** a `Dockerfile`, and **does not automatically push** images to a registry unless publish is enabled.

## 2. How Does Cloud Native Buildpacks Work?

Cloud Native Buildpacks is a set of standards and tools for packaging an application into an image. A **builder image** contains the build environment and one or more **buildpacks**. The buildpacks detect a Java application, prepare the Java runtime, configure application layers, and generate launch metadata.

A typical flow with Spring Boot:

```text
settings.gradle + build.gradle + src/
                 |
                 v
        ./gradlew bootBuildImage
                 |
                 +--> bootJar or bootWar
                 |    creates executable archive
                 |
                 v
      Spring Boot Gradle Plugin
                 |
          communicates with Docker daemon
                 |
                 v
       CNB Builder (default Paketo)
         |        |         |
         v        v         v
       Detect   Build     Export
       app      layers    OCI image
                 |
            Run image / JRE
                 |
                 v
      cnb-demo:0.1.0-SNAPSHOT
                 |
        docker run -p 8080:8080
                 |
                 v
           GET /hello
```

The diagram illustrates roles; the actual CNB lifecycle can include additional analyze, restore, cache handling, and metadata management steps depending on version, and logs do not necessarily follow the drawn order verbatim.

**Four distinct concepts:**

| Component | Role | Is the entire builder put into the runtime image? |
|---|---|---|
| **Gradle `bootBuildImage`** | Orchestrates archive packaging, invokes builder, and creates image | No |
| **Builder image** | Build environment with lifecycle and buildpacks | No, not the runtime base image |
| **Run image** | Runtime OS/libraries base chosen by builder or configured by you | Yes, forms the compatible base for the output launch image |
| **Application image** | Final image with app, Java runtime/layers, and launch metadata | This is the artifact to `docker run`/deploy |

With Spring Boot 3.5, the `bootBuildImage` task is created when the Java or WAR plugin is applied alongside the Spring Boot plugin; the task type is `BootBuildImage`. It takes an executable **JAR or WAR** as input and does **not** ingest raw Java source to replace the Maven/Gradle compiler.

**Default per Spring Boot 3.5 docs:** the chosen builder is `paketobuildpacks/builder-noble-java-tiny:latest`. This is a default **per the documentation line**, not advice to pin `latest` for every production system. The default run image is derived from the builder's metadata. The **tiny** builder and its associated run image have limited system libraries and no shell; applications needing shell scripts or native OS libraries may require choosing a different builder/run image pair.

**CNB security:** images are designed to **build and run with a non-root user** per specification. Do not infer from this that the image has been scanned for vulnerabilities, contains no secrets, or meets all organizational requirements; scanning, SBOM/provenance, and dedicated policies are still required.

## 3. Comparing `bootBuildImage` with Dockerfile, `bootJar`, and `bootRun`

| Tool / task | Input | Output | Needs Docker daemon? | Meaning |
|---|---|---|---|---|
| `./gradlew bootJar` | Java source/resources + dependencies | Executable `.jar` | No | Packages Spring Boot application |
| `./gradlew bootWar` | Source + WAR plugin/dependencies | Executable `.war` | No | Packages WAR |
| `./gradlew bootRun` | Development classpath | Local Java/Spring Boot process | No | Runs app in development, creates no image |
| `./gradlew bootBuildImage` | Executable JAR/WAR and plugin settings | OCI image in Docker daemon | **Yes** per Boot 3.5 task | Buildpack builds image without Dockerfile |
| `docker build -f Dockerfile ...` | Dockerfile + build context | Docker image | Typically Docker builder/daemon | Direct control of every step/layer |
| `docker run image` | Built or pulled image | Container process | Yes | Launches built image |
| `./gradlew bootBuildImage --publishImage` | App + registry/image settings | OCI image and registry upload | Docker daemon + registry access | Publishes via CNB/plugin |

**`bootBuildImage` does not automatically run `test` simply because it builds an image.** Having a task dependency on packaging tasks like `bootJar`/`bootWar` does not imply a dependency on `check`/`test`. When CI requires tests before packaging, invoke `./gradlew clean test bootBuildImage`, `./gradlew check bootBuildImage`, or define explicit pipeline dependencies/gates.

`bootBuildImage` creates an image, which does not mean a container is running. Testing an HTTP endpoint requires `docker run`. Conversely, `bootRun` can run from source without proving an image builds properly.

## 4. Prerequisites Before Running

The machine or runner needs:

- JDK **17** (for example) for Gradle to run/compile per Wrapper/Boot versions; Java toolchain properly configured.
- Valid Gradle Wrapper `gradlew`/`gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, and `gradle-wrapper.properties`. Use a wrapper generated by Spring Initializr/Gradle, not placeholder empty files.
- Docker Engine/Desktop or a compatible daemon exposing a Docker API reachable by the Spring Boot plugin; the **Docker daemon must be running**.
- Permissions to call the daemon and internet/registry access needed to pull builder/run images plus buildpack dependencies on the first build.
- Sufficient disk/RAM for Gradle, the builder container, and cache volumes; runners may need more space than building a JAR alone.
- Builder/run image architecture supporting the target platform: `linux/amd64`, `linux/arm64` depending on actual images/builders.

Check in the terminal:

```bash
java -version
./gradlew --version
docker version
docker info
docker context show
```

On Windows, use `gradlew.bat --version` or PowerShell `.\gradlew.bat --version`. The Docker CLI `docker version` can print both client/server; **having only the Docker CLI is not enough** if the server section fails with "Cannot connect to the Docker daemon".

If using Docker Desktop, verify Docker Desktop is open. In CI, verify socket/engine permissions are properly granted; do not grant broad root/privileged permissions just to solve a connection error when safer infrastructure options exist.

## 5. Complete Spring Boot Java 17 Example

Example project named `cnb-demo`, using Gradle Groovy DSL, Spring Boot Web, and JUnit. We choose a simple HTTP endpoint to verify the image from a real running application.

### 5.1. Directory Structure

```text
cnb-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   └── java/com/example/cnb/
    │       ├── CnbApplication.java
    │       └── HelloController.java
    └── test/
        └── java/com/example/cnb/
            └── HelloControllerTest.java
```

Generate the project using Spring Initializr with Java 17, Gradle Groovy, Spring Web, and Spring Boot Starter Test; then ensure the Gradle build file/versions match the example. If created manually, the wrapper must be generated and committed properly by Gradle.

### 5.2. `settings.gradle`

```groovy
rootProject.name = 'cnb-demo'
```

This name affects the default image name: `docker.io/library/cnb-demo:0.1.0-SNAPSHOT` when `version` is `0.1.0-SNAPSHOT`. In multi-project builds, subproject tasks may derive different names, so set `imageName` explicitly on the application module when releasing.

### 5.3. Runnable `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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

tasks.named('bootBuildImage') {
    imageName = "docker.io/library/cnb-demo:${project.version}"
    environment["BP_JVM_VERSION"] = "17"
}
```

**Configuration explanation:**

1. The `java` plugin provides source sets and Java compile/test tasks.
2. `org.springframework.boot` creates `bootJar`/`bootRun`/`bootBuildImage` per plugin capabilities.
3. `io.spring.dependency-management` lets Spring Boot manage starter versions; this is one approach. If using Gradle native `platform(SpringBootPlugin.BOM_COORDINATES)`, write dependencies accordingly without mixing version-management styles blindly.
4. `group` and `version` describe the project artifact. `imageName` in the example is an independent Docker image name tagged with the project version.
5. `java.toolchain` ensures compiling for Java 17 when a matching toolchain is available. Do not assume toolchains fix everything if the machine/Gradle lacks a suitable runtime.
6. `BP_JVM_VERSION=17` is passed **to the builder** so Paketo Java buildpacks select an appropriate JVM version. With the default builder, the plugin can also infer Java compatibility from the Java plugin; this explicit override makes behavior easy to observe.
7. `tasks.named('test').useJUnitPlatform()` enables JUnit Jupiter. The example has tests, yet the image task **does not automatically guarantee tests ran**; in CI, run `test` beforehand or alongside it.

### 5.4. Java Main File

`src/main/java/com/example/cnb/CnbApplication.java`:

```java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbApplication {
    public static void main(String[] args) {
        SpringApplication.run(CnbApplication.class, args);
    }
}
```

### 5.5. REST Controller

`src/main/java/com/example/cnb/HelloController.java`:

```java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from CNB image";
    }
}
```

If the application runs on the default port 8080 with no custom context path, `GET http://localhost:8080/hello` returns HTTP 200 with response body **`Hello from CNB image`**. This is the HTTP body, not Gradle or Docker stdout.

### 5.6. JUnit Test Verifying the Application Before Packaging

`src/test/java/com/example/cnb/HelloControllerTest.java`:

```java
package com.example.cnb;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsExpectedMessage() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello from CNB image"));
    }
}
```

The test uses `spring-boot-starter-test` and runs inside the Spring test context without needing to start a container. It is **not** a standalone Java Standard Library program compilable with bare `javac` without Spring/JUnit dependencies. Testing the real container is a separate step after building the image.

### 5.7. Gradle Wrapper

File `gradle/wrapper/gradle-wrapper.properties` may contain:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

This is only the key line of the wrapper file, not the full contents. Each project may also include `distributionBase`, `zipStoreBase`, checksum, and other properties. Use an approved, properly generated wrapper and do not modify `gradle-wrapper.jar` arbitrarily.

## 6. Building the Image for the First Time and Testing

### 6.1. Testing Code and Building the Image

From the `cnb-demo` project root:

```bash
# Verify tests without depending on Docker:
./gradlew clean test

# Build a local OCI image using Cloud Native Buildpacks:
./gradlew bootBuildImage
```

Or a single Gradle invocation with the same effect:

```bash
./gradlew clean test bootBuildImage
```

When `bootBuildImage` runs, Gradle packages the application via dependent tasks, talks to the Docker daemon, pulls builder/run images if needed, and has the CNB lifecycle/buildpacks produce the output image. The first run can take a while as many layers/JDK/buildpack dependencies are downloaded. Stdout is not identical across different machines or builder versions.

**What to look for:** the `:bootBuildImage` task succeeds and logs image creation with the configured name; the entire Gradle command ends with `BUILD SUCCESSFUL`. Do not declare a pass just because `bootJar` produced a JAR if the Docker/CNB stage fails.

### 6.2. Verifying the Image Actually Exists

```bash
docker image ls cnb-demo
docker image inspect docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

`docker image ls cnb-demo` filters by local repository name; `docker image inspect` inspects the exact image reference. If the image is missing on the Docker daemon you are querying, check Docker context/host and task logs. The Gradle plugin might have used a **different Docker daemon** from your current CLI due to `DOCKER_HOST`/`DOCKER_CONTEXT`, a remote engine, or CI configuration.

An inspect command with more concise output in a compatible shell:

```bash
docker image inspect \
  --format '{{.Id}} {{.Architecture}} {{.Os}}' \
  docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

The `{{...}}` template syntax is a Go template processed by the Docker CLI, not a Gradle/Groovy string. The result outputs the actual image digest ID, architecture, and OS, with no fixed value to copy ahead of time.

### 6.3. Running the Container

```bash
docker run --rm --name cnb-demo -p 8080:8080 \
    docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

In a second terminal:

```bash
curl -s http://localhost:8080/hello
```

**Expected HTTP response body:**

```text
Hello from CNB image
```

The `\` line continuation applies to Unix/macOS shells; in Windows PowerShell enter commands on a single line or use PowerShell's line continuation syntax. If host port 8080 is occupied by another app, use `-p 8081:8080` and call `http://localhost:8081/hello`; no Java code edits needed.

Stop the container with Ctrl+C in the running terminal or `docker stop cnb-demo` from another terminal. `--rm` makes Docker remove the container upon stopping, **not delete the image**. The Docker image stays around for future runs unless manually deleted or removed by garbage collection policies.

### 6.4. Why Is There No Dockerfile?

The CNB builder/buildpacks determine the Java runtime, launch command, layers, and certain environment variables. Therefore, the minimal repo in section 5 **has no Dockerfile**; `bootBuildImage` builds the image anyway. If you later add a `Dockerfile`, it **is not automatically used by `bootBuildImage`**; you must run `docker build` separately when you want a Dockerfile pipeline.

## 7. Configuring Image Name and Tags

### 7.1. Default Image Name

Per Spring Boot Gradle Plugin 3.5, the default is:

```text
docker.io/library/${project.name}:${project.version}
```

With `rootProject.name='cnb-demo'` and `version='0.1.0-SNAPSHOT'`:

```text
docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

This is a **Docker image reference**, not a Maven GAV. `group='com.example'` does not automatically appear as a registry namespace; if you want to organize an image under `registry.example.com/team/...`, set `imageName` explicitly.

### 7.2. Setting `imageName` in Gradle Groovy

In `build.gradle`:

```groovy
tasks.named('bootBuildImage') {
    imageName = "registry.example.com/team/${project.name}:${project.version}"
}
```

This snippet **replaces** the `imageName` setting of the previous example; avoid declaring multiple overlapping blocks setting the name unless you understand the final configuration order. `registry.example.com` is only an illustrative organizational registry address, not a server readers can push to without permissions.

### 7.3. Overriding Directly on the CLI

```bash
./gradlew bootBuildImage --imageName=example.com/team/cnb-demo:1.0.0
```

The Gradle task builds the image under the specified name for that invocation. Setting a different `imageName` **does not automatically publish**. Run `docker image ls` on the daemon used by the plugin to confirm the result. When using `latest`, a tag can be reassigned to a different artifact; CI should attach a version or Git revision/digest for traceability.

### 7.4. Multiple Tags for One Build

The `BootBuildImage` task supports the `tags` property (**full** image names). Example additional Groovy snippet:

```groovy
tasks.named('bootBuildImage') {
    imageName = "example.com/team/cnb-demo:1.0.0"
    tags = ["example.com/team/cnb-demo:stable"]
}
```

`tags` only affects tagging, not source/JDK selection. Choose immutable tags (`1.0.0` or commit ID) for rollbacks; `stable` is only a convenience label that can point to a different image later. If your setup supplies both `imageName` and `tags` via CLI/Gradle scripts, ensure values follow registry/namespace conventions.

## 8. Builder Image, `runImage`, and Java Version

### 8.1. Paketo Defaults in Spring Boot 3.5

The builder is the CNB component that builds the image; the run image is the foundation for the built application. Do not pick an arbitrary `runImage` just because it includes a shell: **the builder and run image must share a compatible stack**. When switching builders, the plugin reads the run image from builder metadata by default, which is far safer than pairing two unrelated images.

Example explicitly stating the default builder verified in Boot 3.5 docs:

```groovy
tasks.named('bootBuildImage') {
    builder = 'paketobuildpacks/builder-noble-java-tiny:latest'
}
```

Using `latest` in the example follows the plugin's default, **not a guarantee of reproducibility**. In pipelines needing reproducibility/auditability, pin a release tag or registry-supported digest per policy and schedule updates when patches arrive.

**Limitations of "tiny":** the runtime may **lack `/bin/sh`**, package managers, or native OS libraries that application scripts assume exist. If the app needs shell scripts or specific native libraries, choose a **compatible builder/run image pair** with the appropriate system libraries, such as Spring Boot 3.5's documentation suggestion of `paketobuildpacks/ubuntu-noble-run:latest`. Verify this with the exact builder version rather than just changing `runImage` and hoping it works.

### 8.2. Java Toolchain and `BP_JVM_VERSION`

In the `java` block:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

This configures **Gradle compile/test**. When using the default Paketo builder, the Spring Boot Gradle Plugin can also infer Java compatibility from the Java plugin, yet you can specify the JVM requirement explicitly for the CNB builder:

```groovy
tasks.named('bootBuildImage') {
    environment["BP_JVM_VERSION"] = "17"
}
```

`BP_JVM_VERSION` is a **build-time Paketo Java buildpacks** configuration variable, not a Spring Boot property like `server.port`. It determines the JVM placed into the output image by the buildpack. If Java 17 source uses Java 21 APIs or compiler target 21 while runtime 17 is selected, the app can throw `UnsupportedClassVersionError`; align compilation target, test JDK, and runtime JVM.

For most Java server apps, **choose the JVM runtime** instead of native image unless there is an explicit requirement and toolchain/native compatibility have been verified.

### 8.3. Runtime JVM Options

Paketo Java buildpacks configure `JAVA_TOOL_OPTIONS`/launch environment for the container. Do not set `BP_JVM_VERSION` expecting it to change heap limits or GC policy. One way to add a JVM option to the launch environment via buildpack configuration (per Spring Boot docs):

```groovy
tasks.named('bootBuildImage') {
    environment["BPE_DELIM_JAVA_TOOL_OPTIONS"] = " "
    environment["BPE_APPEND_JAVA_TOOL_OPTIONS"] = "-XX:+HeapDumpOnOutOfMemoryError"
}
```

This is an **optional fragment**; it is not needed for `HelloController` to run. `HeapDumpOnOutOfMemoryError` can generate large files: production needs a writable directory, resource limits, retention, and protection for heap dump data. For other runtime settings, consult the Paketo environment variables/JVM memory calculator docs for your buildpack version.

**Do not write secrets into `environment[...]` in committed build scripts.** Build-time properties may be logged or recorded in metadata. Applications should receive database passwords/tokens **when the container runs**, via a secret manager/runtime env, never via tags or public Dockerfile/buildpack settings.

## 9. Complete Gradle Kotlin DSL

If a project uses `settings.gradle.kts` and `build.gradle.kts`, use the corresponding Kotlin syntax. **Choose one DSL** per project—do not keep Groovy `build.gradle` and Kotlin `build.gradle.kts` side by side just to run examples.

`settings.gradle.kts`:

```kotlin
rootProject.name = "cnb-demo"
```

`build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
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

tasks.test {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("docker.io/library/cnb-demo:${project.version}")
    environment.put("BP_JVM_VERSION", "17")
}
```

This is a complete Kotlin DSL build script replacing section 5.3. The Java files from sections 5.4–5.6 still apply unchanged. In Kotlin DSL, the `imageName` property of `BootBuildImage` is a Gradle `Property<String>`, so use `imageName.set(...)`; `environment` is a map-like property, so use `environment.put(...)`.

Execution commands match Groovy:

```bash
./gradlew clean test bootBuildImage
docker run --rm -p 8080:8080 docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

On Windows, invoke `gradlew.bat` per your shell; Docker CLI remains `docker`. Do not copy Groovy snippets like `tasks.named('bootBuildImage')` into a Kotlin file expecting Gradle to translate the syntax.

## 10. Layered JAR, Buildpack Cache, and Build Speed

### 10.1. Role of `layers.idx`

A Spring Boot executable JAR can contain `BOOT-INF/layers.idx`. The default layer structure usually includes:

| Spring Boot layer | Typically contains | Relative change frequency |
|---|---|---|
| `dependencies` | External libraries with stable release versions | Usually low |
| `spring-boot-loader` | Boot Loader classes | Usually on Boot upgrades |
| `snapshot-dependencies` | `SNAPSHOT` dependencies | Depends on development pace |
| `application` | App classes/resources and certain local module dependencies | Usually highest |

The Paketo Spring Boot buildpack understands the layer index and can use it to create appropriate image layers. Thus, when changing only a Java controller, many dependency layers can be reused; you do not need to manually extract the JAR and write four `COPY` instructions as in a manual Dockerfile approach.

**Important:** CNB caching differs from the Gradle build cache. CNB keeps build/launch caches on the Docker daemon/builder side; Gradle keeps compiler/task caches. A buildpack cache hit does not prove `test` ran; testing must still be an explicit pipeline quality gate.

### 10.2. Task-Managed Cache Volumes

Spring Boot 3.5 documentation states that `bootBuildImage` uses **named Docker volumes** for `buildCache`, `launchCache`, and `buildWorkspace` derived from the image name by default. These are not JAR files committed to Git. Because default cache volume names are often **based on the full `imageName`**, changing the tag on every version can produce different cache names, reducing reuse.

To maintain stable caching across versions/tags of the same app, specify explicit volume names (Groovy DSL):

```groovy
tasks.named('bootBuildImage') {
    buildCache {
        volume {
            name = "cache-${rootProject.name}.build"
        }
    }
    launchCache {
        volume {
            name = "cache-${rootProject.name}.launch"
        }
    }
}
```

With `rootProject.name='cnb-demo'`, the two volumes are named `cache-cnb-demo.build` and `cache-cnb-demo.launch`. Choose distinct names by **app, builder stack, and environment** whenever accidental cross-project data sharing must be avoided. Sharing caches unconditionally is not always better: caches must be managed for version/size/permissions and pruned per policy.

Equivalent Kotlin DSL fragment:

```kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    buildCache {
        volume {
            name.set("cache-${rootProject.name}.build")
        }
    }
    launchCache {
        volume {
            name.set("cache-${rootProject.name}.launch")
        }
    }
}
```

### 10.3. When Should Cache Be Cleaned?

The task provides `cleanCache`, defaulting to `false`. When diagnosing stale cache issues, you can temporarily enable it:

```groovy
tasks.named('bootBuildImage') {
    cleanCache = true
}
```

**Use only for a single intentional investigation**, then revert it. Leaving `cleanCache` enabled defeats cache reuse. `./gradlew clean` normally deletes only Gradle `build/` outputs, and is **not** a mechanism to clean Docker buildpack volumes.

Ephemeral CI runners can lose cache volumes between jobs if a new Docker daemon is provisioned each time. To speed up builds across runners, design appropriate cache/persistence rather than assuming a volume on one machine exists on another.

### 10.4. Reproducibility and Image `createdDate`

Spring Boot 3.5 supports the `createdDate` property (defaulting to a fixed epoch timestamp to aid build reproducibility). Setting `createdDate='now'` changes the image metadata timestamp on every build, potentially altering the digest even when code is unchanged. Static resources relying on `last-modified` should also be checked because CNB can normalize file timestamps for layer reproducibility; Spring Boot offers `spring.web.resources.cache.use-last-modified` to adjust how HTTP static resource caching uses that metadata if needed.

**A reproducible image is not the same as supply-chain verified:** you still must pin dependencies/builder/run image properly, inspect SBOMs, scan CVEs, verify image signatures/digests, and maintain independent build provenance.

## 11. Publishing Images to a Registry

### 11.1. Distinguishing Local Build and Publish

`./gradlew bootBuildImage` defaults to **`publish=false`**. The image stays in the local daemon; another CI runner or Kubernetes cluster will not see it automatically unless a registry/transport is configured.

When ready to upload:

```bash
./gradlew bootBuildImage \
  --imageName=registry.example.com/team/cnb-demo:0.1.0 \
  --publishImage
```

`registry.example.com` is an illustrative registry name; replace it with a real registry your organization is authorized to use. If the registry requires authentication, use a Docker credential store/helper or `docker login` against the right registry—**never hardcode passwords in Gradle files or CLI commands**.

Per Spring Boot 3.5, the plugin can read Docker configuration at `$HOME/.docker/config.json` and credential helpers. For private builder/run images, use **`docker.builderRegistry`** credentials; for publishing output, use **`docker.publishRegistry`** if not relying on existing Docker credentials.

**Note:** the target registry is determined from the **host in `imageName`**, not automatically from `docker.publishRegistry.url`. If `imageName` omits a registry host, the image may target Docker Hub by default.

### 11.2. Configuring Publish in Groovy DSL

The following snippet is **for authorized release jobs only**:

```groovy
tasks.named('bootBuildImage') {
    imageName = "registry.example.com/team/cnb-demo:${project.version}"
    publish = true
}
```

When publishing from a developer machine, you can leave `publish=false`/unset and pass `--publishImage` separately to avoid unintended uploads during test builds.

For CI, pass image tags derived from release versions or commit SHAs, and record the output digest after pushing. Avoid publishing a mutable `latest` tag as the **sole signal** identifying a deployed version.

### 11.3. Credentials: Reasonable Usage

If Docker login is configured on the runner via a supported credential helper:

```bash
# Syntax illustration only; command may prompt securely.
docker login registry.example.com

./gradlew bootBuildImage \
    --imageName=registry.example.com/team/cnb-demo:0.1.0 \
    --publishImage
```

In real CI, use a secret store and `--password-stdin` or an appropriate helper; **never pass tokens directly on a command line** that gets logged in workflow output. If the plugin cannot read helper/registry credentials, review `docker.publishRegistry` in the Spring Boot Gradle Plugin docs. Never commit credentials into `build.gradle` or `gradle.properties`.

### 11.4. Verifying Published Results

After pushing, a registry API or `docker pull` on another authorized machine/daemon confirms the image truly exists:

```bash
docker pull registry.example.com/team/cnb-demo:0.1.0
docker image inspect registry.example.com/team/cnb-demo:0.1.0
```

These commands will not work against the illustrative placeholder registry. In production, record the **immutable digest** returned by the registry in the release record rather than relying solely on a tag that can change over time.

## 12. Optimizing Releases in CI/CD

A minimal pipeline should:

1. Check out the exact source revision and pin Java/Gradle Wrapper/Boot plugin versions.
2. Provision Docker Engine or a secured Docker API/socket for the build job.
3. Resolve Gradle dependencies via authorized repositories; do not trust caches as the sole dependency source.
4. Run unit tests/quality gates **before or in the same invocation** as `bootBuildImage`.
5. Build the image with an explicit registry/namespace/tag.
6. Run a container smoke test or integration test against the **exact built image**, checking HTTP endpoints and startup logs.
7. Scan the image and evaluate SBOM/provenance/signatures per policy.
8. Publish the image after quality gates pass; avoid uploading untested images.
9. Save the digest and deploy using that digest or an immutable tag guaranteed by the release process.
10. Never place credentials into image labels, buildpack `environment`, or public logs.

CI example with two distinct stages:

```bash
# Local build and test
./gradlew clean check bootBuildImage \
    --imageName=cnb-demo:ci-candidate

# Smoke test on daemon holding the image, per organization CI workflow
docker run --rm -d --name cnb-candidate -p 18080:8080 cnb-demo:ci-candidate
curl --fail --silent http://localhost:18080/hello
docker stop cnb-candidate

# If all gates and smoke tests succeed, build/publish release image:
./gradlew bootBuildImage \
    --imageName=registry.example.com/team/cnb-demo:0.1.0 \
    --publishImage
```

These commands are an **illustrative CI flow**, not a script guaranteed to work verbatim: `docker run -d` can return before Spring Boot is ready, so real jobs need **readiness polling with timeout and failure cleanup** (or a proper health check). Do not fire an immediate single `curl` and treat a connection error as a buildpack failure. The example also rebuilds at the release step; strict pipelines should control promoting/pushing the **exact smoke-tested image** or compare digests before and after rather than assuming a rebuild produces identical bytes.

If the goal is **only** local testing, neither a registry nor Docker login is needed. If a CI runner has no Docker daemon, `bootBuildImage` in Spring Boot 3.5 will not succeed; provision an authorized builder/runner service instead of falling back to `bootJar` and claiming an image was released.

## 13. Builder, Platform, Proxy, and Advanced Customization

### 13.1. Choosing Image Platform

When building on an ARM64 laptop while deploying to x86_64 or vice versa, consider the architecture of the builder/run image and the Java distribution chosen by the buildpack. The Spring Boot 3.5 task has an `imagePlatform` property accepting `OS[/architecture[/variant]]`, for example:

```groovy
tasks.named('bootBuildImage') {
    imagePlatform = 'linux/amd64'
}
```

**Not every builder supports every architecture.** If a registry only hosts one architecture, this override can cause pull/build failures. The target environment's container runtime must also be compatible; you cannot switch architectures simply by renaming an image tag.

### 13.2. Docker Context and Remote Daemon

The Boot 3.5 task inspects Docker CLI context and several environment variables:

- `DOCKER_CONTEXT`: selected Docker context name, can override `DOCKER_HOST`.
- `DOCKER_HOST`: daemon address such as `unix:///...` or `tcp://...`.
- `DOCKER_CONFIG`: directory holding Docker CLI configuration; can affect context/credentials.
- `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`: TLS settings for remote Docker.

Never hardcode unencrypted `tcp://host:2375` into CI, as the Docker API grants broad control over the host. For remote Docker, use TLS/SSH/secured contexts per policy.

With Docker Desktop, Colima, Podman, or minikube, how the daemon is exposed may vary. Spring Boot documentation gives `docker.host` examples for Podman sockets and Colima; verify runtime version, socket permissions, mount semantics, and Docker API compatibility before treating them as identical to official Docker Engine in every scenario.

### 13.3. Network Proxy

If the builder needs to download a Java runtime or buildpack dependencies through a proxy, the Gradle process having network access is **not enough**: the builder container runs in the Docker daemon's environment and may need `HTTP_PROXY`/`HTTPS_PROXY` in the task `environment`. Illustrative fragment:

```groovy
tasks.named('bootBuildImage') {
    environment["HTTP_PROXY"] = "http://proxy.example.com"
    environment["HTTPS_PROXY"] = "http://proxy.example.com"
}
```

This is an illustrative host; use only if your organization runs a real proxy and handle `NO_PROXY`/certificates per policy. Avoid putting proxy passwords in URLs inside build scripts and logs.

### 13.4. Specifying Specific Buildpacks

Usually you **do not need** to set `buildpacks`: the builder already defines a detection order and suitable buildpacks. If adding a custom buildpack is required, the task allows configuring the list. When `buildpacks` is specified, **only the listed buildpacks will be used**, which can accidentally omit the required Java buildpack.

Conceptual example (use only after confirming the buildpack ID exists in the builder):

```groovy
tasks.named('bootBuildImage') {
    buildpacks = ['urn:cnb:builder:paketo-buildpacks/java']
}
```

Do not use this fragment as a default across every project; IDs, ordering, and buildpack dependencies can vary across builders/versions. If a build fails during detection, restore builder defaults and add customizations one at a time.

## 14. Native Image Is a Separate Path, Not Default Behavior

According to Spring Boot 3.5, when a project applies the **GraalVM Native Build Tools plugin**, the Spring Boot Gradle plugin can configure AOT/native image tasks, and `bootBuildImage` produces a **native image container** instead of a standard JVM image. This path requires GraalVM/native buildpacks and library compatibility, and can consume significantly more build time and resources.

**Do not confuse them:** setting `BP_JVM_VERSION=17` only selects the JVM for a **JVM application image**; it **does not** turn a project into a GraalVM native image. Nor should you apply the native tools plugin just to make a Spring Boot container start faster in every scenario.

If an organization chooses native images, dedicated tests are required for reflection, proxies, serialization, runtime hints, profiles, AOT, binary architecture, and startup/heap behavior; do not copy the entire JVM workflow from this lesson and assume identical native image behavior.

## 15. Inspecting Image Metadata, Logs, and Cache

### 15.1. Checking Container Images After Building

```bash
docker image ls
docker image inspect docker.io/library/cnb-demo:0.1.0-SNAPSHOT
docker history docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

`inspect` reveals properties such as architecture, labels, exposed ports, and configuration of the actual image; **do not rely on a hardcoded label key** without checking the builder/plugin version. `docker history` shows layer history, but is neither a security test report nor a full SBOM. CNB provides metadata/labels for tools to read, though exact fields can differ by builder and lifecycle version.

### 15.2. Debugging Gradle Tasks and the Builder

```bash
# Check whether the task exists and its dependency graph without building an image
./gradlew tasks --all
./gradlew bootBuildImage --dry-run

# Detailed logs if image creation fails
./gradlew bootBuildImage --info --stacktrace
```

`--dry-run` shows which Gradle tasks would be scheduled, **not whether the Docker daemon or CNB builder will build the image successfully**. `--info`/`--stacktrace` can expose paths, registry hostnames, or internal metadata; review before posting publicly.

You can enable `verboseLogging` on the task to inspect additional builder logs when needed, while ensuring verbose logs never expose credentials in public CI artifacts.

### 15.3. Buildpack Cache Hits Differ from Gradle Cache Hits

When source code changes:

- `compileJava`/`bootJar` may re-run because application classes changed.
- Buildpacks can still reuse runtime/dependency layers and cache volumes.
- The new image digest/tag reflects the new application content.
- Do not conclude the cache is broken just because compilation ran; recompiling after source edits is expected.

If the image tag changes on every build, default cache volume names may change too, lowering hit rates. Set stable `buildCache`/`launchCache` names per section 10 when measured to be beneficial. When a base/builder image receives a security update, caches must be invalidated appropriately to pick up the patch.

## 16. Common Errors and Resolutions Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Task 'bootBuildImage' not found` | `org.springframework.boot` and `java`/`war` not applied on the right module, or called on wrong root | Check `plugins`, `./gradlew tasks --all`, target `:app:bootBuildImage` |
| `Cannot connect to Docker daemon` | Docker Engine stopped, wrong socket/permissions/context | `docker version`, `docker info`, Docker context, socket permissions |
| Buildpack pull TLS/proxy error | Docker daemon/builder container cannot reach registry/proxy, untrusted cert | Check Docker proxy/certificates and builder `HTTP_PROXY`/`HTTPS_PROXY` |
| `manifest unknown` pulling builder/run image | Wrong image name/tag or removed upstream | Verify builder/run image for Spring Boot version, pin release |
| `no matching manifest for linux/arm64` | Image does not support selected architecture | Pick builder with matching platform or adjust build/deploy arch intentionally |
| `buildpack detection failed` | Artifact is not a valid executable archive or custom buildpacks omitted Java buildpack | Check `bootJar`/`bootWar`, default builder, restore buildpacks |
| `UnsupportedClassVersionError` when container runs | Java compile target higher than JVM runtime selected by buildpack | Align toolchain, `targetCompatibility`, `BP_JVM_VERSION` |
| `/bin/sh: not found` in container | Tiny run image lacks shell | Do not rely on shell; use builder/run pair with shell if mandatory |
| `docker run image` reports image not found | Build failed, different tag, or different Docker context | Read task `imageName` output, inspect on exact daemon/tag |
| Container runs but `curl /hello` returns 404 | Wrong port/context path or running wrong image version | `docker logs`, `docker inspect`, check controller and routing |
| `docker run -p 8080:8080` reports port in use | Host port already bound by another process | Stop old process or use `-p 8081:8080` |
| `--publishImage` returns `401` or `denied` | Not logged in to right registry or lacks repo push permission | Check Docker credentials/`docker.publishRegistry`, verify namespace |
| Image pushed to Docker Hub by mistake | `imageName` omits registry host | Use fully qualified `registry.example.com/team/app:tag` |
| Too many cache volumes, slow builds | `imageName`/tag changing constantly or fresh daemon per job | Review cache policies, set stable volume names when suitable |
| Different image digest despite unchanged source | Builder/run image `latest` changed, timestamps, JDK/dependencies, or inputs differed | Pin builder/run image, dependency lock, `createdDate`/reproducibility |
| Native image slow or fails | Applied GraalVM native tools/plugin, missing hints/toolchain | Separate native workflow, dedicated profile/compatibility tests |
| Gradle tests green yet container startup fails | Only ran unit tests without smoke testing the real image | Add `docker run` + readiness + API smoke test |
| CI has no Docker daemon | Runner only has CLI or socket blocked | Provide authorized builder/daemon service or revise pipeline architecture |
| Code changed yet old container still returns old response | Container was created before the image tag updated | Stop/recreate container; check new digest |

**Debugging principle:** check **Gradle task failures** first, then Docker daemon/context, next builder/detection/buildpack logs, and finally application startup. Do not blame the Docker engine for every `java.lang.ClassNotFoundException` inside the app if the Boot archive/classpath itself is broken.

## 17. Verification Lab and Checklist

### 17.1. Experiment A — Build Image and Run Application

- Create Java sources and build files from section 5.
- Run `./gradlew clean test bootBuildImage`; confirm all tasks succeed.
- Run `docker image inspect docker.io/library/cnb-demo:0.1.0-SNAPSHOT` to prove the image exists.
- Run the container and call `GET /hello`. Response body is `Hello from CNB image`.

### 17.2. Experiment B — Modify Source

Update `HelloController.hello()` to return `"CNB release two"` and update the expected string in the test accordingly. Re-run `./gradlew test bootBuildImage`. Buildpacks may reuse dependency/Java layers while application content must change. Launch a **new container** from the newly built image and verify the new response.

Do not look solely at `BUILD SUCCESSFUL` to judge caching: an older container with old Java code could still be running. Use the response and image digest/created metadata to verify which version is running.

### 17.3. Experiment C — Intentionally Upgrade Java/Change Builder

Only on an experimental branch: change `BP_JVM_VERSION` to a version supported by the builder and **align toolchain/source compatibility**; observe the Java runtime chosen by the buildpack. If you only lower the runtime below the compiled bytecode level, a compatibility error is expected.

Changing builder tag/digest can also trigger cache invalidation and a different base image. After experimenting, restore project-supported versions/builders and re-run smoke tests.

### 17.4. Experiment D — Safe Publishing

With a real test registry and authorized credentials, set `--imageName=registry...` and `--publishImage`. Pull the image on another machine/daemon, inspect the digest, and run smoke tests. Record the release record. **Never publish an image with only a `latest` tag to a public namespace without authorization.**

### 17.5. Pre-Production CI Checklist

- [ ] Gradle Wrapper, Java 17 toolchain, and Spring Boot plugin version are controlled.
- [ ] `bootBuildImage` exists on the right module and builds cleanly with a running Docker daemon.
- [ ] Project uses a valid executable JAR/WAR; `bootBuildImage` is not confused with `bootRun`.
- [ ] Unit tests/quality gates run before publishing; do not assume `bootBuildImage` runs them.
- [ ] `imageName`, registry host, namespace, and tag reflect the release; digest is tracked for traceability.
- [ ] Builder and run image are compatible, and image architecture matches the target platform.
- [ ] Java compile target and Paketo `BP_JVM_VERSION` are aligned.
- [ ] Tiny run image provides needed system libraries; do not depend on a shell if absent.
- [ ] Buildpack cache volumes are properly managed, without leaving `cleanCache` permanently on.
- [ ] Runtime environment variables/secrets are injected at deploy time, never baked into buildpack images.
- [ ] Docker login/registry credentials never appear in the Git repository or public logs.
- [ ] CI tests the container from the **exact verified image**, using readiness polling/timeouts.
- [ ] Image is scanned and has SBOM/attestation/signature per organizational security policy.
- [ ] Do not treat mutable `latest` tags as sole evidence of the deployed build.
- [ ] Team knows how to read `bootBuildImage --info`, `docker info`, and CNB error logs.
- [ ] Rollout/rollback plan uses image digests or stable release tags.

### Official Documentation

- [Spring Boot 3.5 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html)
- [Spring Boot 3.5 — Container Images with Cloud Native Buildpacks](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/cloud-native-buildpacks.html)
- [Spring Boot 3.5 — Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Cloud Native Buildpacks — Documentation](https://buildpacks.io/docs/)
- [Cloud Native Buildpacks — Specification](https://github.com/buildpacks/spec)
- [Paketo Buildpacks — Java](https://paketo.io/docs/howto/java/)
- [Docker Docs — CLI Reference](https://docs.docker.com/reference/cli/docker/)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)

**Remember:** `./gradlew bootBuildImage` is the direct Spring Boot + Gradle path to create an **OCI image with CNB**, requiring no Dockerfile yet **requiring a Docker daemon** and compatible builder/run images. Inspect the image with `docker image inspect`, run a real container, call the endpoint, manage Java versions/caching, and only use `--publishImage` once you have the right image name, registry credentials, and quality gates.