# From Source Code to Deployable Product: Compiling, Testing, Packaging, and Publishing

A Spring Boot application does not become a deployable product simply because it runs in an IDE. To turn source code into a releasable version, a development team needs a repeatable sequence of steps: **pin versions and dependencies → compile → test → package → verify artifact → publish → deploy**. Each step produces concrete evidence; subsequent steps should only consume results that passed the preceding steps.

This article focuses on the build and release workflow for JVM-based Spring Boot applications. Examples use **Java 17 and Spring Boot 3.3.13** for consistent configuration; for other projects, choose JDK, Spring Boot, and Gradle/Maven versions compatible with that project.

## 1. Understanding Inputs, Stages, and Outputs

| Stage | Purpose | Output / Completion Criteria |
| --- | --- | --- |
| Build preparation | Lock source code, build config, JDK, plugins, and dependency versions | A traceable revision; build tool resolves dependencies |
| Compile | Convert Java code into bytecode; process resources | `.class` files and application resources, with no compiler errors |
| Test / Verify | Run unit tests, integration tests, and configured quality checks | Passing test/check reports; failures halt the pipeline |
| Package | Bundle bytecode, resources, and runtime dependencies in the target format | Executable JAR/WAR or OCI image |
| Artifact verification | Verify the right file, structure, and startup behavior | File exists, starts up, smoke test passes |
| Publish | Push an immutable artifact to controlled storage/distribution | Version + artifact location + checksum/digest |
| Deploy | Select an approved artifact and run it in the target environment | Service starts, health/smoke checks pass |

**Distinction:** *build* creates and verifies an artifact; *publish* distributes the artifact to a repository; *deploy* runs that exact artifact in a target environment. The `mvn deploy` command belongs to the lifecycle for **publishing to a Maven repository**, not deploying the application to a server.

A typical workflow branch:

```text
Git commit + build configuration
        |
        v
Resolve dependencies -> Compile -> Unit tests / Integration tests
        |                                  |
        |                           Fail: stop pipeline
        v                                  |
Package (bootJar / repackage / OCI image) <+
        |
        v
Validate artifact -> Publish immutable version -> Deploy -> Smoke test
```

## 2. Roles of Java, Build Tools, and Spring Boot Plugins

The **JDK** provides `javac` for compiling, `java` for running, and `jar` for inspecting JAR contents. **Gradle/Maven** orchestrates dependencies, tasks/phases, caches, tests, and artifacts. The **Spring Boot plugin** adds Boot-specific running and packaging capabilities: Spring Boot apps typically need a JAR containing runtime libraries and a bootstrap loader so `java -jar` can launch them directly.

With Gradle using the Java plugin and Spring Boot plugin:

- `compileJava` compiles main source code; `processResources` processes `src/main/resources`; `classes` aggregates those outputs.
- `test` runs tests in the default test source set; `check` may include additional static analysis or integration tests attached by the project.
- `bootJar` creates the **executable JAR** in `build/libs/`. `jar` creates a standard JAR; in Spring Boot 3.3 configurations, the standard JAR usually has a `-plain.jar` suffix.
- `assemble` aggregates artifact-producing tasks and is wired by the Spring Boot plugin to `bootJar`; `build` depends on both `assemble` and `check`. Therefore, **`bootJar` alone is not proof that all tests ran**.
- `bootRun` launches the application from the classpath for development; `bootBuildImage` builds an OCI image using Cloud Native Buildpacks when a compatible Docker daemon is available.

With Maven:

- `compile` → `test` → `package` → `verify` → `install` → `deploy` is the standard phase order. Invoking a phase runs all preceding phases in the same lifecycle.
- `spring-boot-maven-plugin` with the `repackage` goal transforms the JAR/WAR created by the `package` phase into an executable archive. When using `spring-boot-starter-parent` and declaring this plugin, the `repackage` execution is preconfigured.
- `mvn clean verify` verifies up through the `verify` phase; integration tests using Maven Failsafe only run if the project **has configured** the corresponding plugin/goals. `mvn install` places the artifact into the local Maven repository; `mvn deploy` pushes it to a configured remote Maven repository.

Do not mix responsibilities between the two tools: pick Gradle **or** Maven as the single source of truth for a build, and use the Wrapper (`gradlew`/`mvnw`) if the project provides one.

## 3. Complete Gradle Example: From Java Source to Executable JAR

Example structure:

```text
demo-build/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/demo/
    │   ├── DemoApplication.java
    │   └── HelloController.java
    └── test/java/dev/example/demo/
        └── HelloControllerTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'demo-build'
```

File `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`org.springframework.boot` registers the `bootJar` task, while `io.spring.dependency-management` imports the Spring Boot BOM so starter dependencies do not need explicit versions. The Java toolchain selects a Java 17 compiler; the build machine still needs a compatible JDK to run Gradle/plugins. `mavenCentral()` is a repository for resolving dependencies, **not a destination that automatically receives published artifacts**.

File `src/main/java/dev/example/demo/DemoApplication.java`:

```java
package dev.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/dev/example/demo/HelloController.java`:

```java
package dev.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from JAR";
    }
}
```

File `src/test/java/dev/example/demo/HelloControllerTest.java`:

```java
package dev.example.demo;

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
    private MockMvc mockMvc;

    @Test
    void helloEndpointReturnsExpectedText() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello from JAR"));
    }
}
```

The test uses the Spring test context and `MockMvc` to invoke the endpoint without opening a real HTTP port. It confirms the controller returns HTTP 200 and the exact body. A real-world application should also include unit tests for pure Java business logic and integration tests for databases, message brokers, or external services; do not rely on a single endpoint test.

**Run from the project directory containing the Gradle Wrapper** (on Windows, replace `./gradlew` with `gradlew.bat`):

```bash
./gradlew clean build
java -jar build/libs/demo-build-1.0.0.jar
```

`clean` deletes previous build outputs; `build` creates the artifact and runs `check`. In another terminal, once the application has started:

```bash
curl -s http://localhost:8080/hello
```

Exact response body:

```text
Hello from JAR
```

If the project does not yet have a Wrapper, generate/verify the Wrapper according to project policy and use it on both developer machines and CI. Do not assume every project already includes `gradlew`.

Useful individual commands:

| Gradle Command | When to Use | What to Keep in Mind |
| --- | --- | --- |
| `./gradlew compileJava` | Only check whether main source code compiles | Does not run tests or create a release artifact |
| `./gradlew test` | Run default tests | Does not mean the app is packaged |
| `./gradlew check` | Run all verification tasks attached to `check` | Scope depends on project configuration |
| `./gradlew bootJar` | Quickly build the executable JAR | Does not guarantee tests ran |
| `./gradlew clean build` | Build and verify via the Gradle lifecycle | Suitable as a basic CI gate |
| `./gradlew bootRun` | Run the app from source/classpath during dev | Does not verify the deliverable JAR |
| `./gradlew tasks --all` | List tasks that actually exist | Useful when a project uses custom plugins |

## 4. Equivalent Maven Example with the Same Java Code

If the project uses Maven, keep the same three Java files above and use the following `pom.xml` **instead of the Gradle configuration**:

```xml
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

    <groupId>dev.example</groupId>
    <artifactId>demo-build</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Run once a compatible Maven installation is available (or replace `mvn` with `./mvnw` if a Wrapper exists):

```bash
mvn clean verify
java -jar target/demo-build-1.0.0.jar
```

Thanks to `spring-boot-starter-parent` and declaring the plugin in the POM, `repackage` is bound to the packaging lifecycle. If you do **not** use this parent, configure the `repackage` execution explicitly; declaring the plugin alone may not make the JAR executable. Running `mvn package spring-boot:repackage` is an explicit option when invoking the goal after creating the original JAR.

**Do not confuse `mvn verify` with actually having integration tests:** verify that the Failsafe plugin and `integration-test`/`verify` goals are wired into the lifecycle before treating integration tests as a release gate. Never assume unconfigured checks ran just from the phase name.

## 5. Verifying the Exact Artifact to Be Released

The primary output of the Gradle example is `build/libs/demo-build-1.0.0.jar`. There may also be `demo-build-1.0.0-plain.jar`; a standard `-plain` JAR lacks the runtime dependencies and Spring Boot bootstrap required for running the app with `java -jar`.

Inspect the structure with the JDK:

```bash
jar tf build/libs/demo-build-1.0.0.jar
```

A Spring Boot 3.x executable JAR typically contains:

- `BOOT-INF/classes/`: application bytecode and resources.
- `BOOT-INF/lib/`: runtime dependency JARs.
- Spring Boot loader and manifest pointing to the application's main class.

A JAR appearing on disk is **not enough** to consider a build ready for release. At minimum, verify: (1) build and test gates passed; (2) right artifact, right version; (3) `java -jar` starts on a compatible JRE/JDK; (4) required endpoints or health checks respond; (5) environment configuration is externalized outside the artifact and contains no committed secrets.

To compare an artifact before and after transferring storage locations, compute SHA-256. On Linux/macOS:

```bash
sha256sum build/libs/demo-build-1.0.0.jar
```

On PowerShell:

```powershell
Get-FileHash build/libs/demo-build-1.0.0.jar -Algorithm SHA256
```

Checksums must match at the destination. Two builds from the same source **do not automatically produce identical checksums** if configuration, dependencies, archive metadata, or the build environment are not pinned; verify reproducibility before claiming reproducible builds.

## 6. Packaging Formats and Deployment Choices

| Artifact | Common Creation Method | Appropriate Usage |
| --- | --- | --- |
| Executable JAR | Gradle `bootJar`; Maven `package` + `repackage` | `java -jar` on a JVM; service packaged with dependencies |
| Plain JAR | Gradle `jar`; standard Maven JAR without repackage | Library consumed by another module, not a self-running bundle |
| Executable WAR | Gradle `bootWar`; Maven WAR + `repackage` | Apps needing WAR format or a compatible servlet container |
| OCI image | Gradle `bootBuildImage`; Maven `spring-boot:build-image` | Registry/container runtime; packages filesystem/runtime for deployment |

**Do not publish an executable Boot JAR as a regular library dependency** if other modules need to import its classes directly: application classes sit in `BOOT-INF/classes`, which differs from a standard Java library JAR layout. If you need a reusable library, extract a library module and publish its plain JAR.

Build an image with Cloud Native Buildpacks when a Docker daemon is ready:

```bash
./gradlew bootBuildImage --imageName=demo-build:1.0.0
docker image inspect demo-build:1.0.0
docker run --rm -p 8080:8080 demo-build:1.0.0
```

`bootBuildImage` builds the image locally; **it does not automatically push the image to a registry**. To release an image, log in to the registry, apply an appropriate tag, push it, and record the **image digest**. Tags can be mutated; a digest identifies the exact bytes of the built image. With containers, still run a smoke test after starting the image.

## 7. Controlled Artifact Publishing

There are three common destinations, each with a distinct meaning:

1. **CI build artifacts / release storage:** store the executable JAR/WAR as a release file alongside version, commit, and SHA-256. CI's `upload-artifact` action only stores build files for retrieval; it does not install or deploy them to a runtime environment.
2. **Maven artifact repository:** `mvn install` saves to local `~/.m2/repository`; `mvn deploy` pushes to a remote repository when the POM defines `distributionManagement` and valid credentials. Gradle needs the `maven-publish` plugin, `publishing.publications`, and `publishing.repositories` before `./gradlew publish` has anything to publish. Do not treat a download dependency repository as a default upload target.
3. **OCI registry:** push the tagged image and verify by digest; deployments should pull the image from the registry rather than rebuilding on the target server.

Example CI workflow that verifies and saves the JAR after passing gates (`.github/workflows/build.yml`), used with the Gradle project in section 3 **that already includes the Gradle Wrapper**:

```yaml
name: Verify and package
on:
  pull_request:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle
      - name: Build and verify
        run: ./gradlew clean build
      - uses: actions/upload-artifact@v4
        with:
          name: executable-jar
          path: build/libs/demo-build-1.0.0.jar
          if-no-files-found: error
```

This workflow fails if `build` fails or the JAR file does not exist. It is **not yet a production release**: publishing to an external registry/repository and deploying should be gated by separate conditions (such as an approved release tag), least-privilege permissions, and artifact traceability. Avoid putting tokens, passwords, or private keys into `build.gradle`, `pom.xml`, source code, or logs; inject credentials from CI's secret manager.

A release should have a **release record** containing: `group/artifact/version` or image name + digest, Git commit, Java/Spring Boot versions, build timestamp, test results, checksum, artifact storage location, and approving person/system. Preserve the exact same artifact from testing through deployment to avoid "each environment building a different binary".

## 8. Designing Quality Gates

- **Before package:** dependencies resolve cleanly, compilation is clean, and unit tests plus configured static checks pass.
- **Before publish:** integration tests are actually configured and run, the executable JAR/OCI image is produced, startup and smoke tests pass, and dependency/security checks meet project policy.
- **Before deploy:** the artifact has an immutable version/digest, the publishing source is verified, environment config/secrets are ready, and a rollback path to the previous version exists.
- **After deploy:** health/readiness checks and core business flows succeed; monitor logs/metrics for regressions.

Never use `-x test` (Gradle), `-DskipTests`, or `-Dmaven.test.skip=true` (Maven) to silently bypass quality gates. If skipping tests is unavoidable for diagnostics, clearly mark the artifact as unapproved for release until verified again.

## 9. Common Errors and How to Fix Them

| Symptom | Common Cause | How to Verify / Fix |
| --- | --- | --- |
| Compile error `invalid source release` or `Unsupported class file major version` | JDK/toolchain differs from requirements; runtime is older than bytecode | Check `java -version`, toolchain, Gradle/Maven, and the Java runtime executing the artifact |
| JAR exists but `java -jar` fails to run | Accidentally running `-plain.jar`, missing Boot loader or main class | Run `bootJar`/`repackage` properly; inspect manifest and filename |
| `bootJar` succeeds but CI still fails tests | `bootJar` does not guarantee running `check` | Use `clean build` or explicitly invoke verification tasks before publishing |
| `mvn package` produces a non-runnable JAR | `repackage` is not bound to the lifecycle | Check starter parent/execution or run `mvn package spring-boot:repackage` |
| `mvn deploy` does not start the app on the server | `deploy` is the Maven artifact publishing phase | Create a separate deployment step targeting the right artifact |
| `./gradlew publish` uploads nothing | Missing/incomplete `maven-publish` and publication/repository configuration | Check publish tasks and publication config for the right artifact type |
| Image build fails unable to connect to Docker | `bootBuildImage` needs a running, accessible Docker daemon | Check Docker context/daemon and network access to pull builders |
| Runtime machine hits config errors unlike build machine | Different ports, env variables, profiles, secrets, JDK/JRE, or network | Test with the same artifact, provide external config, check startup logs and health |
| Builds from "same commit" produce different outputs | Dynamic/SNAPSHOT dependencies, unpinned Wrapper/JDK, timestamps in generated data | Pin versions, use Wrapper and toolchain, control inputs, and compare checksums |

## 10. Practical Checklist

Before saying "ready to release", confirm you can answer yes to each:

- Can it be rebuilt from a single Git commit and versioned build configuration?
- Are JDK, Spring Boot, plugins, and dependencies explicitly pinned?
- Did `clean build`/`clean verify` **actually execute** the checks required by the project?
- Have you identified the exact executable JAR/WAR or image and tested running that exact artifact?
- Is the version attached and the checksum/digest recorded alongside the publication location?
- Can you redeploy or roll back **the exact same artifact** without recompiling?

When all six answers are "yes" backed by evidence, the team has an auditable, repeatable workflow from source code to deployable product.

### Official References

- Spring Boot 3.3 Gradle plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/
- Spring Boot 3.3 Maven plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Gradle build lifecycle (`assemble`, `check`, `build`): https://docs.gradle.org/current/userguide/base_plugin.html
- Gradle Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html