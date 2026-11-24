# Distinguishing build-image from build-image-no-fork When Binding to the Maven Lifecycle

## 1. Goal and Real-World Scenario

The Spring Boot Maven Plugin provides two similarly named goals:

- `spring-boot:build-image`.
- `spring-boot:build-image-no-fork`.

Both use **Cloud Native Buildpacks (CNB)** to build an **OCI container image** from a Spring Boot application without writing a Dockerfile. The core difference is not in the image format or Java version, but in **how Maven executes the build lifecycle before creating the image**:

- **`build-image` forks the Maven lifecycle up to `package`** to prepare the artifact. This is the goal Spring Boot recommends when **invoking directly via a CLI command**.
- **`build-image-no-fork` does not fork the lifecycle**. This is the goal Spring Boot recommends **inside a plugin execution** already bound by Maven to a phase such as `package`, avoiding a second `package` invocation.

Choosing the wrong goal when binding in a POM can cause Maven to re-run compile/test/package and plugin executions unnecessarily. Calling no-fork directly from unbuilt source can also result in missing or stale artifacts.

After this lesson, you can:

1. Explain Maven phases, plugin goals, executions, and lifecycle forking.
2. Create an OCI image via CLI `./mvnw spring-boot:build-image` without calling `package` manually beforehand.
3. Bind `build-image-no-fork` to `package` inside a Maven `container` profile to build images intentionally.
4. Write a Java 17/Spring MVC application, complete POM, and runnable test.
5. Distinguish `repackage`, JAR/WAR, CNB builder, Docker daemon, local image, and registry publication.
6. Inspect the exact image with `docker image inspect` and container smoke tests.
7. Understand why an image bound to `package` can be built **before integration tests in `verify`** and choose appropriate release gates.
8. Troubleshoot duplicate build-image runs, Docker daemon issues, Maven multi-module setups, profiles, image tags, and Java runtime mismatches.

**Sample versions: Spring Boot 3.3.5**, Java 17, Spring Boot Starter Parent, and a properly configured Maven Wrapper. These versions illustrate specific APIs/configs and are not necessarily the latest required for every project. Consult the Spring Boot Maven Plugin documentation matching your actual project version.

## 2. How Does Cloud Native Buildpacks Create an Image?

Cloud Native Buildpacks consists of a **builder image**, a set of buildpacks, and a lifecycle performing detect/build/export. The builder reads the application archive, selects a runtime (such as Java), creates layers and a launch process, and generates an OCI image based on an appropriate run image.

~~~text
Java source + pom.xml
        |
        v
Maven compile / test / package
        |
        v
Application JAR or WAR
        |
        v
Spring Boot Maven Plugin image goal
        |
        v
CNB builder + buildpacks + lifecycle
        |
        v
OCI image (filesystem layers + launch metadata)
        |
        v
Docker daemon or container registry
        |
        v
Container running the application
~~~

**No Dockerfile used:** neither goal of the Spring Boot plugin in this lesson executes `docker build .`. An existing Dockerfile in the repository is not automatically read or executed by the CNB plugin. If you need exact control over `RUN`/`COPY` instructions or Dockerfile-style base image selection, use a separate Dockerfile workflow.

**Docker daemon still required:** Spring Boot Maven Plugin 3.3 connects to a Docker daemon to create images. Maven compile/test can succeed even when Docker Desktop/Engine is stopped, but the `build-image` goal will fail. Builder/run images and dependencies may also require network access, registry credentials, or internal mirrors.

| Component | Primary Role |
| --- | --- |
| Maven lifecycle | Compiles, runs tests, packages the application |
| `spring-boot:repackage` | Creates a Spring Boot executable JAR/WAR with loader and nested dependencies |
| `spring-boot:build-image` | Forks the `package` lifecycle, then passes the app to CNB image build |
| `spring-boot:build-image-no-fork` | Passes the app to CNB image build without forking the lifecycle |
| CNB builder image | Image build environment, detects Java and runs buildpacks |
| CNB run image | Base layer component of the container image at runtime |
| Docker daemon | Target the plugin communicates with to build/store the image |
| OCI registry | Where the image is published when configured, distinct from local Docker daemon |

## 3. Maven Lifecycle: Phase and Goal Are Two Different Concepts

Major phases of the Maven default lifecycle:

~~~text
validate
    |
    v
compile
    |
    v
test
    |
    v
package
    |
    v
verify
    |
    v
install
    |
    v
deploy
~~~

Maven also includes intermediate phases such as `process-resources`, `test-compile`, `prepare-package`, and `integration-test`. When running:

~~~bash
./mvnw clean package
~~~

Maven cleans build outputs and runs default lifecycle phases **up to `package`**. That typically covers compilation, Surefire unit tests, and archive creation per packaging/plugin configuration.

When running:

~~~bash
./mvnw clean verify
~~~

Maven also executes phases after `package` up to `verify`. Integration tests using Maven Failsafe can run in `integration-test` and be verified in `verify`.

**Differences to remember:**

- `package`: name of a **phase** in the lifecycle, not a Spring Boot goal.
- `spring-boot:build-image`: name of a **goal** invokable from the CLI.
- `<execution>`: binds one or more plugin goals to a phase.
- **Forked lifecycle**: a goal asks Maven to run additional phases to prepare data; unrelated to a Git fork or Docker process fork.

Thus, `./mvnw package` is not equivalent to `./mvnw spring-boot:build-image`.

## 4. `build-image`: Forks `package`, Suited for CLI Invocation

Per Spring Boot Maven Plugin 3.3, the `build-image` goal **forks the Maven `package` lifecycle** to ensure the artifact is packaged before buildpacks create the OCI image.

~~~bash
./mvnw spring-boot:build-image
~~~

Diagram:

~~~text
CLI: mvnw spring-boot:build-image
                |
                v
Maven executes goal build-image
                |
                v
FORK package lifecycle
(compile -> test -> package and bound executions)
                |
                v
JAR/WAR ready
                |
                v
CNB detect / build / export image
~~~

**Advantage:** developers do not need to remember to run `./mvnw package` separately beforehand. A single CLI command prepares the archive and creates the image.

If you want to build from a clean workspace:

~~~bash
./mvnw clean spring-boot:build-image
~~~

In PowerShell:

~~~powershell
.\mvnw.cmd clean spring-boot:build-image
~~~

**Avoid the following combination without a specific reason:**

~~~bash
./mvnw package spring-boot:build-image
~~~

`package` is explicitly invoked and the `build-image` goal may **fork `package` again**, causing compile/tests/plugin executions to run twice. That does not necessarily mean Maven always errors or loops infinitely, but it creates redundant work and makes CI harder to predict.

**Appropriate scenarios:** an intentional build-image command on a developer's machine, or a dedicated CI job creating the image after the system decides to enter the image packaging stage.

## 5. `build-image-no-fork`: Does Not Fork `package`, Designed for Executions

The `build-image-no-fork` goal builds an OCI image via the same CNB mechanism, **without running the `package` lifecycle beforehand**. It is designed to operate when an **ongoing lifecycle** has already brought Maven to an appropriate phase, such as `package`.

~~~xml
<execution>
    <id>make-image-on-package</id>
    <phase>package</phase>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

In Spring Boot 3.3, this goal has a default phase of `package`; specifying `<phase>package</phase>` explicitly spares readers from having to memorize the default.

~~~text
CLI: mvnw -Pcontainer clean package
                |
                v
Maven runs lifecycle up to package
                |
                v
Compiler -> tests -> JAR/WAR
                |
                v
Execution: build-image-no-fork
                |
                v
CNB creates OCI image
(does not re-invoke package lifecycle)
~~~

**Do not interpret no-fork as skipping compilation/testing.** Phases prior to `package` still execute normally due to the outer Maven lifecycle. No-fork merely avoids spawning a secondary `package` lifecycle from the image goal itself.

### Key Comparison Table

| Question | `build-image` | `build-image-no-fork` |
| --- | --- | --- |
| Builds OCI image using buildpacks? | Yes | Yes |
| Forks `package` lifecycle before goal? | **Yes** | **No** |
| Where is it used? | Standalone CLI | Maven `<executions>` bound to a phase |
| Sample command | `./mvnw spring-boot:build-image` | `./mvnw -Pcontainer package` with POM binding |
| What if `package` hasn't run? | Automatically triggers `package` lifecycle | Does not guarantee `package` has run |
| Requires Docker daemon? | Yes | Yes |
| Requires Dockerfile? | No | No |
| Pushes to registry by default? | No | No |
| Guarantees integration tests in `verify` passed? | No; forks only to `package` | No if execution is bound to `package` |
| Can repackage executable archive if needed? | Yes | Yes |
| Suitable to bind to `package`? | **Not recommended** | **Intended use case** |

**Rule of thumb:** **CLI invocation → `build-image`. Lifecycle binding → `build-image-no-fork`.**

## 6. Distinguishing `repackage` from Image Creation

The Spring Boot Maven Plugin goal `repackage` turns a Maven archive into a Spring Boot **executable JAR/WAR**. The JAR typically contains:

~~~text
target/cnb-maven-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/...
    └── lib/...
~~~

Meanwhile, `build-image`/`build-image-no-fork` use buildpacks to create an **OCI image** with a Java runtime, layers, and launch configuration.

Per Spring Boot 3.3 docs, **it is not strictly necessary to call `spring-boot:repackage` separately before the image goal**: if the required executable archive has not been created yet, the image goal can repackage automatically according to plugin configuration. Repackage dependency exclusion options also apply when the image goal builds/repackages the application.

However:

- `build-image-no-fork` **does not run the Maven compiler/`package` itself** if invoked standalone without an existing artifact.
- With `spring-boot-starter-parent`, the standard `repackage` execution is usually already managed and activated when the plugin is declared.
- With a corporate parent that only imports the Spring Boot BOM, configure the plugin version and executions properly; importing the BOM does not automatically create all plugin bindings.
- Do not declare two duplicate `repackage` executions when the parent already provides an appropriate one.
- If a module is a Java library with no main class, do not assume it can produce a runnable container image like a Spring Boot application.

## 7. Complete Spring Boot Java 17 Example

Example project `cnb-maven-demo`:

~~~text
cnb-maven-demo/
├── pom.xml
├── mvnw, mvnw.cmd, .mvn/wrapper/...
└── src/
    ├── main/java/com/example/cnb/
    │   ├── CnbMavenDemoApplication.java
    │   └── PingController.java
    └── test/java/com/example/cnb/
        └── PingControllerTest.java
~~~

The project assumes the Maven Wrapper is genuinely generated and committed. You cannot simply create an empty file named `mvnw` without the wrapper implementation and expect it to run.

### 7.1. File `CnbMavenDemoApplication.java`

Path `src/main/java/com/example/cnb/CnbMavenDemoApplication.java`:

~~~java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbMavenDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CnbMavenDemoApplication.class, args);
    }
}
~~~

This is a valid public main class. Using `spring-boot-starter-web`, Spring MVC and embedded Tomcat are configured; do not compile/run the source with standalone `javac` without Spring Boot dependencies on the classpath.

### 7.2. File `PingController.java`

Path `src/main/java/com/example/cnb/PingController.java`:

~~~java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`PingController` resides in a package scanned by `@SpringBootApplication` component scan. Once Spring Boot starts, `GET /ping` returns response body:

~~~text
pong
~~~

Startup log lines contain changing timestamps and PID/ports; do not treat the entire startup stdout as a fixed string.

### 7.3. File `PingControllerTest.java`

Path `src/test/java/com/example/cnb/PingControllerTest.java`:

~~~java
package com.example.cnb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PingController.class)
class PingControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

This test verifies the Spring MVC mapping via `@WebMvcTest`; it **does not run Docker**, does not test buildpacks, and does not guarantee the real image starts. Proving the image is runnable requires an additional smoke test.

## 8. Complete POM for Direct `build-image` Invocation

File `pom.xml`:

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
    <artifactId>cnb-maven-demo</artifactId>
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
                    <image>
                        <name>docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT</name>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**This is the complete POM for the sample project.**

- Spring Boot Starter Parent manages dependency/plugin versions and appropriate build config.
- `<packaging>jar</packaging>` and Spring Boot Maven Plugin serve the executable JAR.
- `java.version=17` aligns Java source/target for the example.
- `spring-boot-starter-web` provides Spring MVC/runtime; `spring-boot-starter-test` is for tests only.
- `<image><name>...` specifies the image tag explicitly, avoiding reliance on implicit names in `docker run` commands.
- No `build-image-no-fork` execution yet: `./mvnw package` **does not automatically create an OCI image** just because the Spring Boot Maven Plugin is declared.

Do not overwrite a real system's POM that uses a corporate parent; port the relevant pieces into the appropriate plugin/profile following existing version and naming conventions.

## 9. Testing the CLI `build-image` Command

### 9.1. Check the Environment

Linux/macOS:

~~~bash
java -version
./mvnw --version
docker version
docker info
~~~

Windows PowerShell:

~~~powershell
java -version
.\mvnw.cmd --version
docker version
docker info
~~~

The Maven Wrapper must use an appropriate JDK. The Docker CLI may exist while the daemon is unreachable; in that case compile/test can still pass while the `build-image` goal fails.

### 9.2. Create the Image via Standalone Goal

Linux/macOS:

~~~bash
./mvnw spring-boot:build-image
~~~

PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:build-image
~~~

The goal ensures `package` runs via lifecycle forking. When a clean build is needed:

~~~bash
./mvnw clean spring-boot:build-image
~~~

Logs may contain Maven compiler/Surefire/JAR/repackage output along with CNB detect/build/export steps. Do not assume exact stdout or timing, as cache, builder, and network vary.

### 9.3. Inspect the JAR and OCI Image

Linux/macOS:

~~~bash
jar tf target/cnb-maven-demo-0.0.1-SNAPSHOT.jar |
    grep '^BOOT-INF/'
docker image inspect docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

Windows PowerShell:

~~~powershell
jar tf .\target\cnb-maven-demo-0.0.1-SNAPSHOT.jar |
    Select-String '^BOOT-INF/'
docker image inspect docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

If `docker image inspect` returns metadata, the image exists in the connected Docker daemon/context; that **does not prove** the image was published to a registry. Do not guess the image digest from the tag name.

### 9.4. Run a Smoke Test on the Container

First terminal:

~~~bash
docker run --rm -p 8080:8080 docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

Second terminal:

~~~bash
curl -fsS http://localhost:8080/ping
~~~

Expected HTTP response body:

~~~text
pong
~~~

On PowerShell:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/ping"
~~~

If host port 8080 is occupied, run `docker run --rm -p 8081:8080 ...` and call `http://localhost:8081/ping`. Do not map two containers to the same host port simultaneously.

## 10. Binding `build-image-no-fork` to the Maven Lifecycle via a Profile

So that developers/CI only build an OCI image on demand, add a `container` Maven profile. **Insert the following fragment before the closing `</project>` tag** in the POM from section 8, without creating a second project root:

~~~xml
<profiles>
    <profile>
        <id>container</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>create-image-at-package</id>
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

Meaning:

1. `<id>container</id>` is the Maven profile ID, active only when `-Pcontainer` or another explicit activation condition is used.
2. The plugin with the same coordinates is merged by Maven with the `image.name` configuration already in `<build>`.
3. `<phase>package</phase>` specifies when Maven runs the execution.
4. `<goal>build-image-no-fork</goal>` builds the OCI image **within the running lifecycle**, without forking a secondary `package` lifecycle.
5. `<id>create-image-at-package</id>` helps trace the execution in Maven logs.
6. Because `activeByDefault` is not set, a normal `mvn package` does not trigger `build-image`.

### 10.1. Normal Build Without Requiring Docker

~~~bash
./mvnw clean package
~~~

Builds/tests/packages the application using normal lifecycle and plugin defaults; the image goal inside the profile is not activated.

### 10.2. Building the Image with the Profile Active

Linux/macOS:

~~~bash
./mvnw -Pcontainer clean package
~~~

PowerShell:

~~~powershell
.\mvnw.cmd -Pcontainer clean package
~~~

The no-fork execution runs at `package`. Verify:

~~~bash
docker image inspect docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

**Do not append `spring-boot:build-image` after `-Pcontainer package`**. The profile already binds the image goal; appending another goal can trigger a duplicate image build.

### 10.3. Example of Incorrect Configuration

Do not use:

~~~xml
<execution>
    <id>wrong-goal-on-package</id>
    <phase>package</phase>
    <goals>
        <goal>build-image</goal>
    </goals>
</execution>
~~~

Because `build-image` forks `package` itself, placing it in a `package` execution causes nested lifecycles or extra unnecessary goal runs. Do not conclude every Maven version enters an infinite loop; what is certain is that **this is not the pattern recommended by the Spring Boot plugin**.

Replace it with:

~~~xml
<execution>
    <id>create-image-at-package</id>
    <phase>package</phase>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

## 11. Common Command Combinations

| Command | What happens per the example model |
| --- | --- |
| `./mvnw clean package` | Packages JAR, does not build OCI image if profile is inactive |
| `./mvnw spring-boot:build-image` | Standalone goal forks `package`, creates OCI image |
| `./mvnw clean spring-boot:build-image` | Cleans then forks `package`, creates image |
| `./mvnw -Pcontainer clean package` | Maven `package`, no-fork execution creates image |
| `./mvnw -Pcontainer clean test` | Stops before `package`, image execution does not run |
| `./mvnw -Pcontainer clean verify` | Passes `package` so image is created **before `verify` finishes** |
| `./mvnw package spring-boot:build-image` | May run `package` twice, not recommended by default |
| `./mvnw -Pcontainer spring-boot:build-image` | May build image twice because the goal forks `package` which has the no-fork execution in the profile |
| `./mvnw spring-boot:build-image-no-fork` | Not recommended standalone without `package`, risks stale/missing artifact |
| `./mvnw -Pcontainer -Dspring-boot.build-image.skip=true clean package` | Still packages application but skips image goal |

**Do not confuse a Maven profile with a Spring runtime profile.** `-Pcontainer` controls whether the Maven plugin execution runs. `spring.profiles.active=prod` controls Spring application beans/config at runtime; it does not alter `package` forking behavior.

## 12. Repackage, Effective POM, and Ordering

When a project inherits from Spring Boot Starter Parent, the `repackage` execution may already be configured by the parent into the packaging lifecycle. If you also bind a no-fork execution to `package`, the Spring Boot plugin is designed to handle this; the image goal can even repackage if needed.

To view merged executions from parent, profile, and module:

~~~bash
./mvnw -Pcontainer help:active-profiles
./mvnw -Pcontainer help:effective-pom -Doutput=effective-pom.xml
~~~

`effective-pom.xml` is output for **inspection**, not a file to edit. Modify the source `pom.xml` to make changes.

Expected diagram:

~~~text
Maven lifecycle up to package
          |
          +-- Maven JAR/WAR packaging
          |
          +-- Spring Boot repackage (if bound)
          |
          +-- build-image-no-fork (container profile)
          |
          v
        OCI image
~~~

**Do not infer exact execution ordering from the diagram alone** in projects with a corporate parent/multiple plugins. Maven has specific plugin/goal ordering rules; inspect the effective POM and real Maven logs. Also avoid declaring duplicate `repackage` goals or conflicting classifiers thinking the image goal requires it.

### Multi-Module Maven Reactor

Example:

~~~text
company-parent/
├── pom.xml                   (packaging=pom)
├── common-library/pom.xml    (packaging=jar, no Spring main)
└── web-app/pom.xml           (packaging=jar, Spring Boot app)
~~~

Only application modules like `web-app` should build images. An execution placed in the parent `<build><plugins>` can propagate to child modules or attempt to build an image for a library lacking a main class.

Recommendation: manage shared versions in `<pluginManagement>`, while placing image executions in the exact application module or a controlled profile. With multiple applications, give each a distinct image name. Inspect Maven reactor logs before rolling out across an entire monorepo.

## 13. CI and Important Notes Regarding `verify`

An image goal bound to `package` can run **before integration tests/quality gates in `verify` complete**.

~~~text
compile -> test -> package -> integration-test -> verify
                     |
                     +-- build-image-no-fork
                         when execution is at package
~~~

Example:

~~~bash
./mvnw -Pcontainer clean verify
~~~

Maven passes through `package` and creates the image, then proceeds to `integration-test`/`verify`. If an integration test fails, the image may already exist locally, but **must not be published/deployed as a QA-approved release**.

### Strategy A: Package Image, Gate Publish

1. Run `./mvnw -Pcontainer clean verify`.
2. The image is built at `package`, yet CI only advances to subsequent steps if `verify` passes.
3. Run container HTTP smoke tests, scan CVEs/SBOM, and verify provenance.
4. Publish/deploy image by digest **only after all gates**.
5. If `verify` fails, do not push and do not deploy.

Advantage: easy integration with Maven lifecycle; drawback: still incurs image-build cost even when post-package tests fail.

### Strategy B: Verify First, Build Image Later

1. Run `./mvnw clean verify` **without activating the image profile**.
2. If it passes, run `./mvnw spring-boot:build-image` in a separate CI stage.
3. Keep in mind `build-image` forks `package`, so it may repeat compilation/tests/packaging that already ran.
4. Control inputs and archive checksums if policy requires the image to be built from the **exact bytes of the verified artifact**.
5. Smoke test, scan, and publish using the immutable image digest.

When you need to avoid re-running `package` as well, you can design a **no-fork execution at a later phase** in a pipeline with verified ordering, or a workflow consuming a saved artifact. Still, do not assume the same source commit suffices for byte-for-byte identity if builds contain timestamps/dynamic dependencies.

### Moving the No-Fork Execution to `verify`?

You can configure:

~~~xml
<execution>
    <id>create-image-on-verify</id>
    <phase>verify</phase>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

This is an **alternative to the `package` execution**; do not keep both active at once. If Failsafe `verify` and the image goal share the `verify` phase, confirm the actual plugin execution order. When ordering is unclear, use separate CI stages to guarantee the image is built only after quality gates.

## 14. Configuring CNB Image, Builder, and Run Image

Both goals share similar CNB parameters. Example **plugin configuration fragment** (do not add a second plugin with duplicate coordinates):

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <name>docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT</name>
            <builder>paketobuildpacks/builder-jammy-base:latest</builder>
        </image>
    </configuration>
</plugin>
~~~

Spring Boot 3.3 docs describe Paketo builders like `paketobuildpacks/builder-jammy-base:latest`; **the `latest` tag is not an immutable digest**. Production should manage builder/run image versions and security update policies. Do not pin a vulnerable image indefinitely just to preserve cache.

| Setting | Role |
| --- | --- |
| `image.name` | Name/tag of output OCI image |
| `image.builder` | Builder image for CNB lifecycle |
| `image.runImage` | Run image if explicit control is needed |
| `image.env` | Environment values for buildpacks (e.g., Java runtime policy) |
| `image.pullPolicy` | When to pull builder/run image |
| `image.cleanCache` | Intentionally clears cache for investigation |
| `image.publish` | Only publishes image to registry when enabled |
| `image.verboseLogging` | Adds more buildpack activity details |

**Default `publish=false`:** a local image may run fine without ever having been pushed to a registry. Do not hardcode registry credentials in the POM.

### Overriding Image Tag via CLI

Linux/bash:

~~~bash
./mvnw -Dspring-boot.build-image.imageName=demo-local:0.0.1 \
    spring-boot:build-image
~~~

PowerShell:

~~~powershell
.\mvnw.cmd "-Dspring-boot.build-image.imageName=demo-local:0.0.1" spring-boot:build-image
~~~

When overriding, pass `demo-local:0.0.1` to `docker image inspect` rather than looking for the old tag in the POM.

### CNB Cache Is Not Maven Cache

Buildpacks cache layers/runtime components completely separately from the Maven local dependency repository `~/.m2/repository`. A fresh CI runner, updated builder, or cleared cache volume can make image builds slower even when source is unchanged. Read actual logs instead of blaming `build-image` vs `no-fork` for every slowdown.

## 15. Skipping Image, Skipping Tests, and Publish Permissions

If the image profile is active yet you want to build the JAR without running Docker:

~~~bash
./mvnw -Pcontainer -Dspring-boot.build-image.skip=true clean package
~~~

The property `spring-boot.build-image.skip` controls the **image goal** and does not skip compile/test/package. Nor does it delete a Docker image created by a previous build.

Contrast with:

~~~bash
./mvnw -Pcontainer -DskipTests clean package
~~~

`-DskipTests` normally skips running unit tests, **not** the CNB image goal. Avoid building/publishing untested production images just to shorten build times.

**Registry publishing** is a separate decision: `docker image inspect` succeeding only confirms the image exists in the current Docker daemon. Publishing requires an image registry, credentials, access permissions, and a controlled push step or `image.publish=true`. If the plugin and Docker CLI use different Docker contexts, you may be looking at the wrong daemon; check `docker context ls` and Docker API settings.

## 16. Verification Commands for CI

An **illustrative** Linux/bash scenario when you intentionally build the image at `package` yet gate before publishing:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Image created at package; verify continues running subsequent tests/gates.
./mvnw -B -ntp -Pcontainer clean verify

# Script proceeds only if Maven verify succeeds.
IMAGE='docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT'
docker image inspect "$IMAGE" > /dev/null

echo "VERIFY_AND_IMAGE_PRESENT"
~~~

If `verify` passes and the image is present in the current daemon, stdout from the final statement prints:

~~~text
VERIFY_AND_IMAGE_PRESENT
~~~

**Limitation:** the script verifies Maven `verify` and image presence, but **does not yet run HTTP smoke tests, SBOM/CVE scans, signatures, or publish gates**. Those must be added in a real release pipeline. If `verify` fails, an image might have been built earlier during the `package` phase, yet the script will not print PASS.

To test the container over HTTP, run the image with `docker run` and call `/ping` once the server is ready. In CI automation, start detached, poll the endpoint with a bounded timeout, capture logs, and clean up the container even when tests fail. Do not use a single `sleep 1` and assume the app has started.

**Do not assume a successful image build means all runtime integrations work.** JUnit `@WebMvcTest` and container smoke tests validate two different layers.

## 17. Troubleshooting: Where Do Mistakes Usually Happen?

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| CLI `build-image` runs compile/test/package | That is **lifecycle forking by design** | Not a bug; use the right goal for CLI |
| `package` appears twice in Maven log | Bound `build-image` to `package` by mistake or ran `package + build-image` | Switch to `build-image-no-fork` in execution |
| `-Pcontainer package` does not create OCI image | Profile inactive, invalid XML, or execution skipped | Check `active-profiles`, effective POM, logs |
| Regular `mvn package` suddenly requires Docker | Image execution was bound to the default build | Move to an opt-in `container` profile |
| CLI no-fork after `clean` reports missing archive | No-fork does not fork lifecycle to prepare `package` | Use `build-image` directly |
| Image exists yet `verify` tests fail | Image goal at `package`, tests in a later phase | Do not publish; fix CI gating |
| Docker daemon connection failed | Docker Engine/Desktop stopped or wrong socket/context | `docker info`, `docker context ls`, permissions |
| Builder/run image fails to download | Registry auth, proxy, DNS, network, or pull policy | Check mirror and access permissions |
| Incompatible runtime Java version | Maven compiler target and builder Java differ | Align Java 17 and CNB runtime config |
| Main class not found | Library module without main or multiple main classes | Target right app module, specify `mainClass` |
| JAR has no main manifest attribute | Picked plain JAR not Boot repackaged | Check Maven artifact and Spring Boot Maven Plugin |
| Inspect cannot find image at expected name | `image.name`/CLI override or different daemon | Read image name in logs and check context |
| Dockerfile exists yet edits don't affect CNB image | CNB goal does not execute Dockerfile | Use Dockerfile pipeline if needed |
| Every child module builds an image | Parent plugin execution inherited | Bind only in the app module |
| Builder repeatedly downloads dependencies despite unchanged source | Cold cache, builder image changed, dynamic dependencies | Check cache store, versions, and logs |
| `spring-boot.build-image.skip=true` yet image still in daemon | Skip does not delete old images | Compare logs from current run |
| Docker publish returns 401/403 | Missing registry credentials/permissions | Use CI secret store and valid namespace |
| Image runs yet `GET /ping` fails | Controller/config/port/runtime incorrect | Check container logs and real endpoint |

### Investigation Order

1. Read the **command line**: is it invoking a lifecycle phase or a plugin goal directly?
2. Inspect effective POM/profiles: is `build-image` or `build-image-no-fork` bound to any phase?
3. Check the JAR in `target` and Java main class/Boot manifest.
4. Check Docker daemon, CNB builder, run image, network, and auth.
5. Read detect/build/export logs, not only the final error line.
6. Verify exact image tag, `docker image inspect`, and `docker run`.
7. Call HTTP `/ping` and verify response `pong`.
8. Confirm integration tests in `verify` pass before publishing.
9. Fix the exact failing layer rather than changing Java version, Maven phase, Docker daemon, and builder all at once.

## 18. Practice Lab and Completion Criteria

Work on a test branch of a Spring Boot Maven project:

1. Create `CnbMavenDemoApplication`, `PingController`, `PingControllerTest`, and `pom.xml` from sections 7–8.
2. Use `java -version`, `mvnw --version`, `docker info` to verify JDK/Maven/Docker.
3. Run `./mvnw clean package`; verify the executable JAR in `target` without creating an image.
4. Run `./mvnw spring-boot:build-image`; read logs to point out the `package` lifecycle fork and CNB build.
5. Run `docker image inspect` and `docker run`; verify `GET /ping` returns `pong`.
6. Add the `container` Maven profile with a `build-image-no-fork` execution bound to `package`.
7. Run `./mvnw -Pcontainer clean package`; verify the image goal runs inside the `package` lifecycle **without forking `package` again**.
8. Run `./mvnw clean package` without activating the profile and explain why no image is created.
9. Test `-Dspring-boot.build-image.skip=true`, confirming Maven still packages while the image goal is skipped.
10. Read `help:effective-pom` to inspect executions merged from parent/profile.
11. Run `./mvnw -Pcontainer clean verify`, confirming an image can be built before `verify` completes.
12. In a multi-module project, verify only the web application has the image execution.
13. Record image tag/digest, Docker context, builder/run image, Maven/Boot/Java versions, test reports, and HTTP smoke results.
14. Explain the impact of mistakenly binding `build-image` to `package`.
15. Conclude whether the organization should adopt the CLI goal, an opt-in lifecycle profile, or separate CI stages.
16. Restore experimental configuration before finishing and never publish unscanned/unapproved images.

**Passing criteria:** you understand Maven lifecycle forking, can build OCI images with both **CLI `build-image`** and **lifecycle-bound `build-image-no-fork`**, avoid redundant image goal runs, and only publish/deploy after quality gates.

## Official References

- [Spring Boot 3.3 – Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 – Maven Plugin: Goals](https://docs.spring.io/spring-boot/3.3/maven-plugin/goals.html)
- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven – Introduction to Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven – Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Cloud Native Buildpacks – Concepts](https://buildpacks.io/docs/for-app-developers/concepts/)
- [Cloud Native Buildpacks – Specification](https://github.com/buildpacks/spec)
- [Paketo Buildpacks – Documentation](https://paketo.io/docs/)
- [Docker Docs – Docker Engine](https://docs.docker.com/engine/)