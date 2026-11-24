# Linking Artifacts to Commits, Branches, and CI Run IDs

When a Spring Boot service fails in production, asking "which version is the app running?" is rarely enough. Two JARs can both have Maven version `1.0.0` yet be built from two different commits; two workflow runs on the same commit can use different dependencies or toolchains; a CI rerun can produce a new artifact even when `run_id` stays unchanged. Therefore, you need to link the **actual deployed artifact** to the **source revision**, **triggering ref/branch**, and **CI run ID and attempt**, while keeping a strong identifier to verify the exact released bytes.

This lesson focuses on **build metadata** in Spring Boot, Maven/Gradle, and CI/CD:

- Embed source and CI identifiers into the executable JAR via `META-INF/build-info.properties` using Spring Boot build plugins.
- Distinguish `commit SHA`, `branch/ref`, `run ID`, `run attempt`, `version`, and `artifact SHA-256`.
- Verify that metadata is generated **during the build**, **packaged inside the JAR**, read by Spring Boot at runtime, and aligned with CI logs.
- Choose consciously between **embedded metadata inside the artifact** and **digest-keyed sidecar provenance**, so you do not inadvertently break build reproducibility.
- Handle Git detached HEAD, pull request merge commits, tags, reruns, monorepos, and cross-environment promotion strategies properly.

The examples use **Java 17, Spring Boot 3.3.13**, Maven 3.9.x or a Boot 3.3-compatible Gradle; GitHub Actions serves as an illustrative provider. Versions are pinned so learners can reproduce the mechanics, not as a claim that these are the latest releases.

## 1. Six distinct types of identity

Suppose CI produces a file `lineage-demo-1.0.0.jar`. Hypothetical metadata for that build might look like:

```text
application.version = 1.0.0
source.repository    = example-org/lineage-demo
source.commit        = 4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
source.ref           = refs/heads/main
ci.provider          = github-actions
ci.run.id            = 8123456789
ci.run.attempt       = 2
artifact.sha256      = <64 hexadecimal characters computed AFTER packaging>
```

The `<64 hexadecimal characters ...>` line is a **structural placeholder**, not a usable digest; the digest must be computed from the real JAR's bytes. All other values are illustrative too and do not represent a real commit or workflow.

| Property | Question it answers | Immutable? | What is it used for? |
| --- | --- | --- | --- |
| **Artifact version** | What logical release version is it? | Insufficient to distinguish every binary | Release notes, dependency coordinates, semantic versioning |
| **Full commit SHA** | Which Git object was the working tree/checkout based on? | Stable object identifier within the repository | Tracing back to source at build time; comparing commits |
| **Branch/tag/ref** | Under which ref name was the build triggered? | **No**: branches can move | Knowing PR/main/release context; deployment policies |
| **CI run ID** | Which workflow/pipeline invocation produced the artifact? | Stable per provider/repository; not necessarily globally unique | Locating logs, test reports, artifacts, approvals |
| **Run attempt** | Which retry/attempt of that same run? | Tied to each retry/rerun | Distinguishing two executions of the same run |
| **Artifact digest** | Which exact bytes are being referenced? | Strong per file; any byte change alters the digest | Verifying integrity, matching deployments and provenance |

**Never use a branch name as an immutable source identifier.** `main` can point to a new commit after every merge. **Never rely on Maven version as the sole proof of an artifact**: the same version can be rebuilt. **Never record run ID without attempt** when the provider keeps the same run ID across reruns.

In GitHub Actions, `GITHUB_RUN_ID` does not change when a workflow run is re-run, whereas `GITHUB_RUN_ATTEMPT` increments. `GITHUB_RUN_NUMBER` is a workflow counter and does not replace `GITHUB_RUN_ID`; combining repository + workflow identity + run ID + attempt (+ job/matrix if needed) traces back to the exact invocation.

## 2. Provenance architecture: source → build → artifact → deployment

```text
Git repository
   commit: immutable full SHA
   ref: branch/tag/PR ref at trigger time
         |
         v
CI event + checkout
   repository ID + workflow
   run ID + attempt + job ID
   working tree revision (HEAD)
         |
         v
Maven/Gradle build
   Java/Boot/plugin/dependency versions
   verification tests + packaging
         |
         +--> Embedded metadata:
         |    META-INF/build-info.properties
         |    [optional git.properties]
         |
         v
Executable Spring Boot JAR
   BOOT-INF/classes
   BOOT-INF/lib
         |
         +--> Compute SHA-256 AFTER packaging
         |
         +--> External provenance/attestation:
         |    artifact digest -> source revision + CI invocation
         |
         v
Artifact registry / OCI image
   name + version + digest
         |
         v
Deployment record
   environment + timestamp + deployed digest
         |
         v
Incident lookup: digest -> CI run -> commit/source
```

This chain has **two independent links**:

1. **Build link:** commit/ref/run information is collected by CI and recorded alongside the output.
2. **Release link:** the published/deployed artifact has the exact same **digest** as the verified file.

With only the first link, a pipeline could accidentally deploy a different JAR sharing the same name/version. With only the digest and no build record, you know the exact bytes but struggle to trace back to the commit, test logs, and approver. True traceability requires **both**.

### Build metadata does not prove authenticity by itself

Anyone with permission to build or edit the JAR can write a fake `build.ci.commit=...` line. Hence, embedded metadata is **self-asserted data inside the artifact**, useful for diagnostics yet **not a cryptographic signature**. For supply-chain assurance, add checksums, signed provenance/attestations, CI identity, and trusted-source verification policies.

## 3. Where does Spring Boot provide metadata?

Spring Boot 3.3 includes standard mechanisms:

- **`META-INF/build-info.properties`:** Maven goal `spring-boot:build-info` or Gradle task `bootBuildInfo` generates this file. Spring Boot auto-configures `BuildProperties` when it is on the classpath. `BuildInfoContributor` can surface build data at Actuator `/actuator/info`.
- **`git.properties`:** typically generated by a Git metadata plugin or dedicated build task, placed **at the classpath root**. Spring Boot auto-configures `GitProperties` when present; `GitInfoContributor` can expose commit/ref on the info endpoint.
- **Manifest `META-INF/MANIFEST.MF`:** for an executable Boot JAR, `Main-Class` points to `JarLauncher` and `Start-Class` points to the app's main class. Some attributes hold version/build metadata, though it is **not** the only or mandatory place to attach CI run identity.
- **CI artifact store/sidecar:** holds test results, SHA-256, provenance, SBOMs, signed attestations, etc., linked to the same artifact digest.

A typical `build-info.properties` file may contain:

```properties
build.artifact=lineage-demo
build.group=dev.example
build.name=lineage-demo
build.version=1.0.0
build.ci.commit=4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
build.ci.ref=refs/heads/main
build.ci.run.id=8123456789
build.ci.run.attempt=2
```

The Spring Boot Maven Plugin **prepends `build.`** to custom properties declared under `<additionalProperties>`. Thus configuring `ci.commit` writes `build.ci.commit` in the file. Through `BuildProperties`, you read it with `build.get("ci.commit")`, without assuming `git.properties` and build-info come from the same source.

**Note:** `spring-boot:build-info` and `bootBuildInfo` **do not automatically fetch the full Git SHA or CI run ID** unless you configure them. Those values must be supplied by CI, a Git metadata plugin, or the build script.

## 4. Complete Maven example: embedding commit, ref, and run identity

This example creates a Spring Boot web application exposing `GET /lineage` to return metadata embedded in the JAR. In local builds, explicit fallback values keep the app runnable. In CI, values are passed via Maven system/user properties.

Structure:

```text
lineage-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/lineage/
    │   │   ├── LineageApplication.java
    │   │   └── LineageController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/dev/example/lineage/
            └── LineageControllerTest.java
```

### 4.1. Complete `pom.xml`

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
    <artifactId>lineage-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <ci.commit>local</ci.commit>
        <ci.ref>local</ci.ref>
        <ci.run.id>local</ci.run.id>
        <ci.run.attempt>0</ci.run.attempt>
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
                <executions>
                    <execution>
                        <id>generate-build-lineage</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                        <configuration>
                            <time>off</time>
                            <additionalProperties>
                                <ci.commit>${ci.commit}</ci.commit>
                                <ci.ref>${ci.ref}</ci.ref>
                                <ci.run.id>${ci.run.id}</ci.run.id>
                                <ci.run.attempt>${ci.run.attempt}</ci.run.attempt>
                            </additionalProperties>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Key points:

1. `spring-boot-starter-parent` manages dependency versions and supplies Spring Boot Maven Plugin defaults; the plugin in `build/plugins` runs `repackage` via the starter parent alongside the declared `build-info` execution. **Importing the BOM alone** does not automatically run both goals.
2. `<ci.commit>local</ci.commit>`, `<ci.ref>local</ci.ref>`, `<ci.run.id>local</ci.run.id>`, and `<ci.run.attempt>0</ci.run.attempt>` are **dev fallback values** and must not be accepted as real release provenance.
3. `<additionalProperties>` writes those Maven properties as `build.ci.*` inside generated `META-INF/build-info.properties`.
4. `<time>off</time>` intentionally omits `build.time` so a changing timestamp does not mutate the metadata file on every run. **It is not enough to guarantee a reproducible artifact** if CI run ID/attempt vary every run: those fields still change JAR bytes.
5. `spring-boot-starter-actuator` enables `BuildInfoContributor` on `/actuator/info` when exposed; the `/lineage` controller in the example serves the lab. Do not expose both endpoints publicly in production by default.
6. The source code does not use `GitProperties`, so **no Git plugin is needed** in this minimal example; CI passes the Git commit directly into build-info.

### 4.2. Application main class

`src/main/java/dev/example/lineage/LineageApplication.java`:

```java
package dev.example.lineage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LineageApplication {

    public static void main(String[] args) {
        SpringApplication.run(LineageApplication.class, args);
    }
}
```

### 4.3. HTTP controller reading metadata packaged in the JAR

`src/main/java/dev/example/lineage/LineageController.java`:

```java
package dev.example.lineage;

import org.springframework.boot.info.BuildProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LineageController {

    private final BuildProperties build;

    public LineageController(BuildProperties build) {
        this.build = build;
    }

    @GetMapping("/lineage")
    public LineageResponse lineage() {
        return new LineageResponse(
                build.getVersion(),
                build.get("ci.commit"),
                build.get("ci.ref"),
                build.get("ci.run.id"),
                build.get("ci.run.attempt")
        );
    }

    public record LineageResponse(
            String version,
            String commit,
            String ref,
            String runId,
            String attempt
    ) {
    }
}
```

**Explanation:** `BuildProperties` is the bean Spring Boot creates when it finds `META-INF/build-info.properties`. `build.getVersion()` returns the Maven/Gradle version, while `build.get("ci.commit")` reads the additional property **after Spring Boot strips the `build.` prefix**. If the metadata file is absent or the `build-info` goal never ran, the app lacks a `BuildProperties` bean to inject, catching the error immediately at startup.

The demo endpoint exposes no secrets, tokens, workspace paths, or runner names. In production, **do not automatically make detailed build metadata public**; depending on repository/ref sensitivity and security policy, restrict the endpoint to internal monitoring or enforce authentication/authorization.

### 4.4. Minimal HTTP configuration

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: lineage-demo
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
```

With Spring Boot Actuator 3.3, HTTP `info` is **not exposed by default**; the configuration above exposes only `health` and `info`. It does not add authentication for `/lineage` — hence **this config is intended for hands-on practice in a trusted environment**. Production projects must apply Spring Security, reverse proxy restrictions, or a separate management port per enterprise rules.

### 4.5. Test verifying the bean and metadata exist

`src/test/java/dev/example/lineage/LineageControllerTest.java`:

```java
package dev.example.lineage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LineageControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void exposesBuildMetadataGeneratedDuringBuild() throws Exception {
        mvc.perform(get("/lineage"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("1.0.0"))
                .andExpect(jsonPath("$.commit").isNotEmpty())
                .andExpect(jsonPath("$.ref").isNotEmpty())
                .andExpect(jsonPath("$.runId").isNotEmpty())
                .andExpect(jsonPath("$.attempt").isNotEmpty());
    }
}
```

This test verifies that the Spring context sees `BuildProperties` and exposes those fields. It **does not prove the final artifact is the exact file CI uploaded/deployed**; that requires checking digests and packages as shown below.

### 4.6. Running locally with fallback values

In the directory containing `pom.xml`:

```bash
mvn -version
mvn clean verify
java -jar target/lineage-demo-1.0.0.jar
```

Second terminal:

```bash
curl -s http://localhost:8080/lineage
```

JSON body under the default local configuration:

```json
{
  "version": "1.0.0",
  "commit": "local",
  "ref": "local",
  "runId": "local",
  "attempt": "0"
}
```

JSON property serialization order does not have to match the example order; values and field names are what matter.

Spring Boot Actuator `/actuator/info` can also render the `build` group. JSON nesting and contributor mode depend on Boot configuration; do not use `/actuator/info` JSON as a standalone substitute for the metadata file and CI build records.

## 5. Maven: building with explicit commit/ref/run from CI

Git stores commit objects, while CI provides workflow context. On a Linux/macOS terminal with Git and a JDK, you can test manually:

```bash
COMMIT="$(git rev-parse --verify HEAD)"
REF="$(git symbolic-ref --quiet HEAD || printf 'detached-HEAD')"

mvn -B -ntp clean verify \
  "-Dci.commit=$COMMIT" \
  "-Dci.ref=$REF" \
  "-Dci.run.id=local-check-001" \
  "-Dci.run.attempt=1"
```

**Distinction:** `git rev-parse --verify HEAD` returns the **actual checked-out commit**. `git symbolic-ref --quiet HEAD` only returns a symbolic ref when `HEAD` is attached to a local branch; on detached HEAD (common when CI checks out a commit directly) it outputs nothing and exits non-zero, so the example labels it `detached-HEAD`. The ref supplied by the CI event may describe the **trigger context** more accurately, and is **not necessarily a branch name**.

Note that `$(...)` is shell command substitution; the example above targets Bash. In PowerShell, retrieve the SHA with `git rev-parse HEAD` and pass quoted Maven arguments using PowerShell syntax instead of copying Linux shell syntax verbatim without Bash.

When CI supplies metadata:

```bash
mvn -B -ntp clean verify \
  "-Dci.commit=$CI_COMMIT" \
  "-Dci.ref=$CI_REF" \
  "-Dci.run.id=$CI_RUN_ID" \
  "-Dci.run.attempt=$CI_RUN_ATTEMPT"
```

Every variable must be **validated as non-empty before the build**. Never let a release job silently fall back to `local`, as the released artifact would record ambiguous provenance even though the build succeeded.

### Which data is the source of truth?

- `CI_COMMIT`: ideally the commit SHA **of the checkout actually being built** (verified via `git rev-parse HEAD`). In GitHub PR workflows, the default checkout may be a **temporary merge commit** under `refs/pull/N/merge`; that differs from the PR's head commit. If you also want to record the PR head SHA, store it in a separate field (e.g. `source.pr.head.sha`) rather than **silently overwriting the actual built commit**.
- `CI_REF`: the full event ref such as `refs/heads/main`, `refs/tags/v1.0.0`, or `refs/pull/123/merge`. Do not assume every ref is a branch; tag-triggered workflows also have refs.
- `CI_RUN_ID`: the CI invocation identifier within the provider/repository scope.
- `CI_RUN_ATTEMPT`: distinguishes reruns when the provider supports attempts.
- `CI_JOB_ID`/matrix: if multiple jobs/Java versions/architectures in the same run produce different files, store the job/variant in external provenance; one run ID cannot uniquely identify every output in a matrix.

## 6. Inspecting metadata **after** Maven packaging

After building, the example's Spring Boot executable JAR contains:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/lineage/LineageApplication.class
BOOT-INF/classes/dev/example/lineage/LineageController.class
BOOT-INF/classes/META-INF/build-info.properties
BOOT-INF/lib/...
```

`build-info.properties` sits in `target/classes/META-INF` before repackage and moves to `BOOT-INF/classes/META-INF` inside the executable JAR. **Do not mistakenly look for `META-INF/build-info.properties` at the root of the outer executable JAR**; the Boot JAR path normally sits under `BOOT-INF/classes`.

Inspect directly:

```bash
jar tf target/lineage-demo-1.0.0.jar
unzip -p target/lineage-demo-1.0.0.jar \
  BOOT-INF/classes/META-INF/build-info.properties
```

Look for the corresponding lines:

```properties
build.ci.commit=4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
build.ci.ref=refs/heads/main
build.ci.run.id=8123456789
build.ci.run.attempt=2
```

These illustrate values injected by CI; in practice, verify the exact SHA/ref/run of that build. Because of `<time>off</time>` in the POM, do not expect `build.time` in the file.

### Automated gate to reject fake fallbacks

Bash example, run **after building in CI**:

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/lineage-demo-1.0.0.jar"
COMMIT="$(git rev-parse --verify HEAD)"

test -f "$JAR"
test -n "$COMMIT"
test -n "$CI_REF"
test -n "$CI_RUN_ID"
test -n "$CI_RUN_ATTEMPT"

unzip -p "$JAR" BOOT-INF/classes/META-INF/build-info.properties > build-info-check.properties

grep -Fqx "build.ci.commit=$COMMIT" build-info-check.properties
grep -Fqx "build.ci.ref=$CI_REF" build-info-check.properties
grep -Fqx "build.ci.run.id=$CI_RUN_ID" build-info-check.properties
grep -Fqx "build.ci.run.attempt=$CI_RUN_ATTEMPT" build-info-check.properties

echo "PASS: embedded build metadata matches CI and working commit"
```

When these checks pass, the script's stdout is:

```text
PASS: embedded build metadata matches CI and working commit
```

Under `set -euo pipefail`, undefined CI variables fail clearly. If a value was not passed to Maven and the plugin wrote the `local` fallback, `grep -Fqx` fails. This is **evidence checking metadata inside the artifact's bytes**, not a cryptographic signature guaranteeing builder trust.

**To avoid temp files in the workspace**, you can pipe `unzip -p ... | grep ...`, though the sample script saves contents once to inspect multiple fields. In CI with parallel jobs sharing a workspace, isolate temp filenames per job.

## 7. Gradle: generating the same metadata with `bootBuildInfo`

Spring Boot Gradle Plugin 3.3 offers the `springBoot { buildInfo { ... } }` DSL and `bootBuildInfo` task. The resulting metadata file has the same format understood by Spring Boot Actuator/`BuildProperties`. Below is a **POM-alternative** setup for the exact same Java sources and test from Section 4.

`settings.gradle`:

```groovy
rootProject.name = 'lineage-demo'
```

`build.gradle` (Groovy DSL):

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

def ciCommit = providers.environmentVariable('CI_COMMIT').orElse('local')
def ciRef = providers.environmentVariable('CI_REF').orElse('local')
def ciRunId = providers.environmentVariable('CI_RUN_ID').orElse('local')
def ciAttempt = providers.environmentVariable('CI_RUN_ATTEMPT').orElse('0')

springBoot {
    mainClass = 'dev.example.lineage.LineageApplication'
    buildInfo {
        excludes = ['time']
        properties {
            additional = [
                'ci.commit'     : ciCommit.get(),
                'ci.ref'        : ciRef.get(),
                'ci.run.id'     : ciRunId.get(),
                'ci.run.attempt': ciAttempt.get()
            ]
        }
    }
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Meaning:

- `bootBuildInfo` creates `META-INF/build-info.properties` as a task output wired into the application's resources/classpath when using the Java plugin; `bootJar` packages it into the executable archive.
- `properties.additional` stores `ci.commit`/`ci.ref`/`ci.run.id`/`ci.run.attempt`, written as `build.ci.*`. Gradle does not define a built-in `CI_COMMIT` key for Spring Boot; `providers.environmentVariable(...)` reads from the **build invocation's** environment.
- `excludes = ['time']` avoids writing a changing `build.time` on every build. Per Spring Boot Gradle Plugin docs, the default build time prevents the task from staying up-to-date and alters outputs. Omitting time improves stability; however, embedding run ID/attempt still makes artifacts from different runs differ byte-for-byte.
- `test` uses JUnit Platform to run `LineageControllerTest` via Spring Boot starter test.
- Calling `.get()` in the configuration above evaluates env vars eagerly during build script evaluation. For large projects optimizing configuration cache or lazy providers, pass `Provider` values directly where supported and verify plugin/version compatibility; never write scripts that accidentally leak secrets into outputs.

### Building Gradle with local metadata

If the repository has a compatible Gradle Wrapper:

```bash
./gradlew clean build
java -jar build/libs/lineage-demo-1.0.0.jar
```

In another terminal:

```bash
curl -s http://localhost:8080/lineage
```

The response will return `version=1.0.0` and `local`/`0` values just like Maven.

On Linux/macOS with explicit CI variables, you can run:

```bash
CI_COMMIT="$(git rev-parse --verify HEAD)" \
CI_REF="refs/heads/main" \
CI_RUN_ID="local-check-001" \
CI_RUN_ATTEMPT="1" \
./gradlew clean build
```

In this example `refs/heads/main` is a **manually supplied** value for learning and does not prove that ref is actually checked out. In real CI, take the ref from the provider and verify the checkout event.

### Gradle output path

Inspect:

```bash
jar tf build/libs/lineage-demo-1.0.0.jar
unzip -p build/libs/lineage-demo-1.0.0.jar \
  BOOT-INF/classes/META-INF/build-info.properties
```

Do not assume the generated file always lives at `build/resources/main/META-INF` across all versions/configurations. What must be confirmed is that **the resource exists inside the Boot executable JAR** and matches the CI data used.

## 8. Sample CI: GitHub Actions collecting and embedding commit/ref/run/attempt

The workflow below targets the **Maven** repository from Section 4, using a GitHub-hosted Ubuntu runner and illustrative action versions. For a Gradle app, replace the Maven build step with Gradle Wrapper and pass the same `CI_*` variables. In a real project this workflow goes in `.github/workflows/lineage.yml`; here it is **instructional material** and makes no changes to any repository.

```yaml
name: Build artifact with source lineage

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  jar:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build and verify with immutable source identity
        shell: bash
        env:
          CI_REF: ${{ github.ref }}
          CI_RUN_ID: ${{ github.run_id }}
          CI_RUN_ATTEMPT: ${{ github.run_attempt }}
        run: |
          set -euo pipefail
          CI_COMMIT="$(git rev-parse --verify HEAD)"
          test -n "$CI_COMMIT"
          test -n "$CI_REF"
          test -n "$CI_RUN_ID"
          test -n "$CI_RUN_ATTEMPT"

          mvn -B -ntp clean verify \
            "-Dci.commit=$CI_COMMIT" \
            "-Dci.ref=$CI_REF" \
            "-Dci.run.id=$CI_RUN_ID" \
            "-Dci.run.attempt=$CI_RUN_ATTEMPT"

          unzip -p target/lineage-demo-1.0.0.jar \
            BOOT-INF/classes/META-INF/build-info.properties \
            > target/embedded-lineage.properties

          grep -Fqx "build.ci.commit=$CI_COMMIT" \
            target/embedded-lineage.properties
          grep -Fqx "build.ci.ref=$CI_REF" \
            target/embedded-lineage.properties
          grep -Fqx "build.ci.run.id=$CI_RUN_ID" \
            target/embedded-lineage.properties
          grep -Fqx "build.ci.run.attempt=$CI_RUN_ATTEMPT" \
            target/embedded-lineage.properties

          sha256sum target/lineage-demo-1.0.0.jar \
            > target/lineage-demo-1.0.0.jar.sha256

      - name: Upload exact verified JAR and digest
        uses: actions/upload-artifact@v4
        with:
          name: lineage-demo-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            target/lineage-demo-1.0.0.jar
            target/lineage-demo-1.0.0.jar.sha256
          if-no-files-found: error
```

**Reading the workflow properly:**

- `actions/checkout` produces the checkout the build actually uses. `git rev-parse --verify HEAD` measures the commit in **that working tree**, instead of guessing from a branch name.
- `github.ref` is the **full triggering ref**; on a Pull Request event it can be `refs/pull/N/merge`. In PR workflows, the checked-out `HEAD` is often a temporary merge commit. If you need to save the PR head commit or base commit, put them in **separate fields** rather than conflating them with the compiled commit.
- `github.run_id` is the run identity within the repository; `github.run_attempt` is the retry count. The workflow's artifact name includes both so attempts are never confused.
- `mvn clean verify` runs tests/build per the POM; release policy may add integration/static/security gates.
- `grep -Fqx` verifies that the **embedded build-info content** matches the event and checkout. Any fallback metadata or mismatched CI env fails the job.
- `sha256sum` computes the digest **after packaging**, on the exact JAR file about to be uploaded. The digest is stored alongside the file rather than inserted back into the JAR, which would cause a self-referential loop.
- `upload-artifact` uploads that run's exact JAR/digest. It does not sign provenance on its own; if build-origin guarantees are needed, add attestation/signing per policy.

**Important workflow security note:** the example restricts `permissions: contents: read` and avoids secrets. In production, pin actions by an approved commit SHA and protect branches/tags/build environments; tags like `@v4` illustrate major API versions and do **not** offer the same supply-chain guarantee as pinning immutable action commits.

### Should `GITHUB_SHA` also be recorded?

`GITHUB_SHA` is the commit associated with the GitHub event, but its exact meaning depends on event type. On certain pull request workflows it is the PR's **merge commit**, while `github.event.pull_request.head.sha` is the PR's head commit. Both are useful and are not necessarily identical.

**Rule:** `source.commit` metadata describes the **commit actually built** (`git rev-parse HEAD`), while the CI record can additionally store **trigger SHA**, **PR head SHA**, and **base SHA** to explain why the build reflects that source. Never label a merge checkout's SHA as the "head commit."

## 9. How to trace back from a run ID to logs

In GitHub Actions, log URLs follow the form:

```text
https://github.com/<owner>/<repo>/actions/runs/<run_id>
```

This is a **URL pattern**—substitute real owner/repo/run_id; private repositories require appropriate permissions. When a run is re-run, use `attempt` to pinpoint the exact logs and artifacts. Workflow name, job, and matrix variant also distinguish cases where one run produces multiple binaries.

Suggested tracking record schema in an artifact repository or deployment database:

| Field | Example | Explanation |
| --- | --- | --- |
| `repository` | `example-org/lineage-demo` | Include host/namespace when multiple sources exist |
| `artifact_coordinate` | `dev.example:lineage-demo:1.0.0` | Maven coordinate; may not be byte-unique |
| `commit_sha` | Full SHA from checkout | Actual revision built |
| `source_ref` | `refs/heads/main` | Event context; not immutable |
| `ci_provider` | `github-actions` | Namespace of the run |
| `ci_run_id` | `8123456789` | Which workflow run |
| `ci_attempt` | `2` | Which rerun |
| `ci_job` | `jar` | Job/variant that produced the output |
| `sha256` | SHA-256 of actual JAR | Byte-level identifier |
| `build_status` | `passed` | Quality gates satisfied |
| `published_uri` | Maven/registry URL | Where the artifact is stored |
| `deployed_environment` | `staging` or `production` | Where it was deployed after build |

Never write credentials, access tokens, private keys, or full environment variable dumps into this record. If Git branches or repository names contain sensitive information, keep them in an internal metadata store and restrict runtime endpoints.

## 10. Embedded metadata vs. external provenance: two options with trade-offs

### 10.1. Option A — Embed commit + branch/ref + run ID into the JAR

The sample POM and Gradle build above use Option A. Pros:

- With only the JAR in hand, you can inspect revision/ref/run ID even when CI is offline.
- `/lineage` or Actuator `/info` aids debugging and operations support.
- Artifact inspection in CI proves metadata came from the build rather than a runtime env var.

Cons:

- **Rebuilding the same commit in a new run produces a different `build.ci.run.id`**, resulting in different bytes and SHA-256.
- When a CI run is re-run with a new attempt, the artifact changes even though source is identical.
- Git branch/ref is event-scoped and mutable; rebuilding the same commit from another branch/tag alters metadata.
- Operational details or ref names may leak at endpoints if HTTP exposure is uncontrolled.

If your organization prioritizes **direct in-binary traceability** and accepts run-specific JARs, this design is reasonable. Just do not claim "byte-for-byte reproducible" when run-dependent fields vary.

### 10.2. Option B — Embed only stable source identity; store run details externally

An alternative strategy is:

1. Embed only **version + immutable Git commit SHA** and static/controlled metadata inside the JAR.
2. Omit run ID/attempt, branch name, wall-clock build time, or volatile environment data.
3. After packaging, compute the JAR's SHA-256.
4. Record **CI run ID + attempt + branch/ref + build environment** in a sidecar/provenance record **keyed by the digest**.
5. Publish the JAR and attestation together; deploy strictly by approved digest.

```text
Executable JAR
  build.version=1.0.0
  build.ci.commit=<full stable revision>
        |
        v
sha256(JAR bytes) = D
        |
        +--> provenance record:
             subject.digest.sha256 = D
             source.revision       = commit SHA
             invocationId          = CI run + attempt
             source.ref            = branch/tag/PR
             builder identity      = trusted CI
             test results          = passed
```

Option B allows builds with identical inputs **to potentially** produce identical bytes, though that also depends on plugins, archive timestamps, dependency locks, toolchains, locale, input ordering, and reproducible-build settings. **You cannot claim reproducibility merely by dropping run ID**; rebuild in an independent environment and compare digests.

### 10.3. Why not embed the final SHA-256 inside build-info inside the JAR?

If you:

1. Build JAR A.
2. Compute SHA-256(A) = D.
3. Edit `build-info.properties` **inside A** to insert D.

then the modified JAR is **A'**, and `SHA-256(A')` **differs from** D. Storing an artifact's digest inside the very bytes hashed to produce that digest creates a **self-referential loop**. The solution is storing the digest **externally** in a sidecar/registry/attestation—or hashing a clearly defined subset without calling it the SHA-256 of the entire final JAR.

## 11. `git.properties` is another option, not Maven build-info

In Spring Boot 3.3, if the classpath root contains `git.properties` with keys `git.branch`, `git.commit.id`, `git.commit.time`, etc., `GitProperties` and `GitInfoContributor` can read and expose them.

Example resource:

```properties
git.branch=main
git.commit.id=4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
git.commit.time=2026-11-09T00:00:00Z
```

This is only a **format illustration**, not real output. Never write an arbitrary timestamp and present it as the commit timestamp. Git metadata plugins (e.g. popular plugins for Maven/Gradle) typically read `.git`, generate `git.properties`, and allow field selection.

**Pros and cons:**

- Convenient for `GitProperties.getCommitId()` and Actuator's git contributor.
- CI checkouts may run in **detached HEAD**; `git.branch` may be absent or not reflect the expected trigger event. You may still want to record `CI_REF` separately.
- Some CI systems perform shallow clones; plugins relying on Git history/tags may lack data. Full commit SHA of `HEAD` is still available once checked out; fetching full history is unnecessary solely for the SHA.
- Do not run a Git plugin against a working tree modified after CI captured metadata; verify working tree and source revision consistency.

**Do not confuse the two resources:**

| Resource | Generated by | Contents |
| --- | --- | --- |
| `META-INF/build-info.properties` | Spring Boot Maven/Gradle plugin | Maven/Gradle coordinates, version, time (if configured), custom CI fields |
| `git.properties` | Git metadata plugin/build task | Git commit, branch, commit time, and Git fields |
| `META-INF/MANIFEST.MF` | JAR/Boot packaging plugin | Entry point, `Start-Class`, archive/implementation metadata |
| Sidecar provenance | CI/attestation builder | Subject digest, revision, CI invocation, builder, test/publish evidence |

In the complete Maven/Gradle examples in this lesson, we use **build-info** as the single path to avoid inconsistency between two Git metadata sources. In real systems, if both are enabled, add a CI check verifying `build.ci.commit` matches `git.commit.id`.

## 12. Actuator `/actuator/info` and data exposure risks

Spring Boot Actuator provides the `info` endpoint to expose build and Git metadata. In Boot 3.3:

- `BuildInfoContributor` is enabled when `META-INF/build-info.properties` is present.
- `GitInfoContributor` is enabled when `git.properties` is present.
- By default, HTTP Actuator usually **exposes only `health`**, so you must explicitly include `info` to access it over HTTP.
- `management.info.git.mode=full` can expose many additional Git fields. Do not enable full mode merely for debugging convenience without reviewing actual contents.
- All endpoints exposing build identity and source paths must be secured per policy, especially when private repo names, branch names, or CI URLs are involved.

Minimal configuration **for development environments**:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    git:
      mode: simple
```

If you only want specific safe fields, create an internal endpoint returning just version/full commit/run ID with separate access control. **Adding the `spring-boot-starter-actuator` dependency does not automatically make `info` public.**

### Should every client see the full commit?

It depends on policy and threat model. A full commit SHA is usually not a cryptographic secret, yet it can disclose repository history/branch context or aid deployment fingerprinting. In public-facing setups, prefer `version` or a less sensitive deployment ID, keeping full CI traces in internal telemetry/registries. Never put access tokens/passwords, sensitive runner hostnames, or secret strings into build-info.

## 13. GitHub Actions: identifying the right commit across event types

**Important observation:** `git rev-parse HEAD` and `GITHUB_SHA` do not always represent what users casually call "the feature branch commit."

| Event | Typical ref | SHA to record |
| --- | --- | --- |
| Push to main | `refs/heads/main` | Checked-out working commit, usually the pushed commit |
| Push release tag | `refs/tags/v1.0.0` | Commit checked out for the tag/event; ref is a tag, not a branch |
| Pull request (workflow default checkout) | `refs/pull/123/merge` | May be a synthetic test merge commit created by GitHub, differing from PR head |
| Pull request target | Base branch context ref | Explicitly record event checkout and trust boundary; do not assume it is PR head |
| Workflow dispatch | Ref selected at trigger | Use checkout `HEAD` and full ref; store actor/event if policy requires |
| Rerun attempt | Ref/SHA usually tied to same run | Run ID may stay identical while attempt increments; distinguish new artifacts |

On a PR, when testing the PR code **merged into base**, building the synthetic merge commit makes sense. When proving code matches the exact PR head, have the workflow check out the head SHA explicitly per policy. **Never automatically check out and run code from untrusted forks in an environment holding production secrets.**

### Do not capture branch name via `git branch --show-current` in CI and treat it as immutable

Many CI systems run in detached HEAD, so `git branch --show-current` can return an empty string. Separate them:

- **Built commit:** `git rev-parse HEAD`.
- **Trigger ref:** CI event variable such as `GITHUB_REF`.
- **Human-friendly name:** `GITHUB_REF_NAME` for display; be aware of ref type and formats like `123/merge` on PRs.
- **Source repository identity:** `GITHUB_REPOSITORY` or canonical repo URI.
- **Optional PR head SHA:** from the event payload when genuinely needed.

## 14. Other CI providers: normalized names do not mean identical semantics

An application may be built by GitHub Actions, GitLab CI, Jenkins, or another provider. The goal is normalizing into internal fields `ci.commit`, `ci.ref`, `ci.run.id`, and `ci.run.attempt` after verifying what each variable means.

| Provider | Common commit source | Ref/branch | Run/build identifier |
| --- | --- | --- | --- |
| GitHub Actions | `GITHUB_SHA` and `git rev-parse HEAD` | `GITHUB_REF`/`GITHUB_REF_NAME` | `GITHUB_RUN_ID` + `GITHUB_RUN_ATTEMPT` |
| GitLab CI | `CI_COMMIT_SHA` | `CI_COMMIT_REF_NAME` or `CI_COMMIT_REF_SLUG` | `CI_PIPELINE_ID`; `CI_JOB_ID` distinguishes jobs |
| Jenkins | `GIT_COMMIT` from SCM plugin or `git rev-parse HEAD` | `GIT_BRANCH` if supplied by plugin/SCM | `BUILD_NUMBER` must be namespaced by `JOB_NAME`/server |

GitLab/Jenkins variable names and semantics depend on CI configuration, pipeline type, and plugins. For example, Jenkins `BUILD_NUMBER=42` is only unique **within a job**, not globally; also record the Jenkins controller/job identity. Never treat a bare number like "42" as meaningful without a namespace.

For monorepos/matrices, add `module`, `artifact name`, `Java version`, `OS/architecture`, and `job identifier` to tell apart multiple outputs from the same pipeline.

## 15. Preserving artifact identity across publish and deploy

After build/QA, manage **artifact identity** as an immutable object:

### 15.1. Computing the digest

Linux/macOS:

```bash
sha256sum target/lineage-demo-1.0.0.jar
```

To save a sidecar file:

```bash
sha256sum target/lineage-demo-1.0.0.jar > target/lineage-demo-1.0.0.jar.sha256
```

Output format looks like:

```text
<sha256-hex>  target/lineage-demo-1.0.0.jar
```

`<sha256-hex>` is an explanatory placeholder, not a real checksum. If the file is moved to another directory, the path inside the sidecar may no longer match; verify directly by recomputing the hash and comparing the 64-character hex value, or update the sidecar **through a controlled process** without modifying the JAR.

PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 target/lineage-demo-1.0.0.jar
```

### 15.2. After publishing: verify the digest

CI/CD should:

1. Upload the JAR along with the checksum computed from the tested file.
2. In the registry or staging, fetch back that exact coordinate/digest.
3. Compute SHA-256 of the downloaded file and compare it against the value stored in the build record.
4. Promote/deploy **only the exact same bytes**, never re-running Maven/Gradle in the deploy stage to build a new file under the same version name.
5. Write a deployment record: environment, cluster, time, deployed digest, CI run/attempt, commit.
6. During incidents/rollbacks, look up the exact digest and provenance, not merely "latest version."

**Maven `SNAPSHOT`, mutable Docker tags (`latest`), and reused artifact versions** are common sources of confusion. If a registry allows overwriting files at the same path/tag, enforce immutability or pin digests in deployment configs.

### 15.3. OCI container images also have their own digest

If a Spring Boot JAR is packaged into a container image, there are **two objects**:

- **JAR SHA-256:** hash of the exact JAR bytes.
- **OCI image digest:** hash of the image manifest/content-addressed data in the registry.

They are **not the same value**. A container adds base images, filesystem layers, image config, and metadata. Keep a record mapping `image digest → JAR digest → Git commit → CI run`.

You can attach OCI annotations/labels such as:

```text
org.opencontainers.image.source   = https://github.com/example-org/lineage-demo
org.opencontainers.image.revision = 4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
org.opencontainers.image.version  = 1.0.0
```

These lines represent the **metadata concept**; exact label attachment depends on Dockerfile, Buildpacks, or registry tooling. The `revision` label is also self-asserted; proving origin requires trusted provenance/signatures and subject digest verification.

## 16. Provenance and SBOM: what can they prove?

A **Software Bill of Materials (SBOM)** lists an artifact's components/dependencies, useful for vulnerability and license tracking. **Provenance/attestation** describes the subject artifact, builder, invocation, and build source. The two **complement** each other and are not the same.

A provenance record in the spirit of **SLSA provenance v1.x** might describe:

```json
{
  "subject": [
    {
      "name": "lineage-demo-1.0.0.jar",
      "digest": {
        "sha256": "HEX_DIGEST_COMPUTED_FROM_THE_REAL_JAR"
      }
    }
  ],
  "buildDefinition": {
    "buildType": "example-ci-build",
    "externalParameters": {
      "sourceRef": "refs/heads/main"
    },
    "resolvedDependencies": [
      {
        "uri": "git+https://github.com/example-org/lineage-demo",
        "digest": {
          "gitCommit": "4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b"
        }
      }
    ]
  },
  "runDetails": {
    "builder": {
      "id": "example-trusted-builder"
    },
    "metadata": {
      "invocationId": "github-actions/run/8123456789/attempt/2"
    }
  }
}
```

**This is an illustrative JSON diagram explaining field groups, not a complete attestation or valid signed payload satisfying all SLSA schemas/requirements.** Values like `HEX_DIGEST_COMPUTED_FROM_THE_REAL_JAR` must be replaced with real hashes, and `buildType`/`builder.id` must use operator-defined identifiers. Never treat this snippet as a verified certificate.

In a secure workflow:

- A trusted CI builder generates an attestation whose **subject digest matches the final artifact**.
- The attestation is signed using an enterprise-approved mechanism such as Sigstore/certificate-based signing.
- Deployment gates verify the signature, builder identity, source revision, and policy rather than **merely parsing self-declared JSON**.
- An SBOM can be linked to the same artifact digest to inspect actual included dependencies.

Run ID/attempt are fields for finding logs; they cannot substitute for **builder identity, signature, and subject digest**.

## 17. Reproducibility: timestamps and run IDs can break byte-for-byte equality

A "reproducible build" artifact means identical **effective inputs and toolchain** produce identical output bytes through a deterministic process. This matters for supply-chain verification. **Unstable values** commonly alter binaries:

- Wall-clock build timestamps in `build.time` or ZIP entry metadata.
- `ci.run.id` or `ci.run.attempt` embedded into `build-info.properties`.
- Branch/ref names when the same commit is built from multiple refs.
- Non-deterministic ordering of generated resources.
- `SNAPSHOT`/dynamic dependencies or registries allowing mutable overwrites.
- Differing plugins/toolchains/environments; embedded locales/timezones/absolute paths.
- Dirty source trees: generated files or uncommitted files entering the build.

**With Maven** in this example, `<time>off</time>` removes the `build.time` property, though that alone does not make all ZIP/JAR files reproducible. You may also need a fixed `project.build.outputTimestamp`, plugin versions supporting reproducible archives, dependency locks, and empirical verification.

**With Gradle**, `excludes = ['time']` is appropriate when prioritizing up-to-date checks and repeatability; Boot Gradle Plugin docs explain that the default current-instant build time keeps `bootBuildInfo` from being up-to-date and alters outputs.

### How to run a proper experiment

1. Pick one Git commit and freeze toolchains/dependencies.
2. Build in two clean workspaces, ensuring **all embedded values match**.
3. Compute and compare the SHA-256 of each artifact.
4. If they differ, inspect `build-info.properties`, archive entry timestamps, file ordering, generated metadata, and toolchains.
5. If you must track run identity while keeping identical binaries, move run ID/attempt to **sidecar provenance** (Option B in Section 10).

Whenever different run IDs are embedded, the two builds **do not share the same effective inputs**; differing hashes do not by themselves prove a compiler is non-deterministic.

## 18. Multi-module: which module holds metadata and which artifact is deployed?

In Maven/Gradle multi-module builds, do not put metadata only on the root aggregator assuming every module JAR automatically receives the right file:

```text
multi-module/
├── pom.xml                    (aggregator)
├── common/                    (plain library JAR)
└── api-service/               (Spring Boot executable JAR)
```

If `api-service` is the releasable module:

- Bind `build-info`/**`bootBuildInfo` on the app module itself** (or inherit properly, avoiding missing/wrong metadata in children).
- Pass the same full commit SHA/ref/run context from CI across modules in a build, while adding module/artifact coordinates to the external record.
- Inspect `api-service/target/api-service-...jar` or `api-service/build/libs/api-service-...jar`, not an artifact at the root.
- If a single CI run builds multiple modules, the `run ID` is **shared**, so `module` and `artifact SHA-256` are needed to identify each output.
- When building only one module via `mvn -pl :api-service -am` or `./gradlew :api-service:build`, the build tool still builds upstream libraries; the app's build metadata must represent **the revision of the compiled source** and the packaged artifact.
- If a library module is published separately for consumers, use a plain JAR with POM/Gradle module metadata; do not apply Boot repackage to every module just to embed build-info.

Example Maven module selector from root:

```bash
mvn -B -ntp -pl :api-service -am clean verify \
  "-Dci.commit=$CI_COMMIT" \
  "-Dci.ref=$CI_REF" \
  "-Dci.run.id=$CI_RUN_ID" \
  "-Dci.run.attempt=$CI_RUN_ATTEMPT"
```

This is a **fragment for a repository that actually has `api-service`**; do not run it verbatim in the single-module `lineage-demo` example. Before publishing, gates must inspect the right app module output and compute its own digest.

## 19. Tracing deployment failures backward

A realistic scenario: `/lineage` in staging returns:

```json
{
  "version": "1.0.0",
  "commit": "4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b",
  "ref": "refs/heads/main",
  "runId": "8123456789",
  "attempt": "2"
}
```

Investigation workflow:

1. Retrieve the **digest of the currently deployed artifact** from deployment/registry/infrastructure records (JAR checksum or OCI image digest).
2. Match that digest against the artifact CI published from `runId=8123456789` and `attempt=2`.
3. Identify the repository/workflow/job that produced the artifact. If a matrix exists, locate the exact variant/OS/JDK.
4. Verify the full SHA inside embedded metadata matches the checkout SHA in CI logs/provenance.
5. Review test reports, dependency scans/SBOMs, build logs, and approvals for that exact build run.
6. Inspect the Git diff between that commit and the previous running build; **the branch may have moved forward**, so never use the branch's latest HEAD to guess what is deployed.
7. If rolling back, select a **QA-verified artifact digest** instead of rebuilding an old tag by version name and guessing it matches.
8. After rollback, confirm runtime deployment records/endpoints/digests reflect the chosen artifact.

**If the metadata endpoint and registry digest mismatch:** treat this as a release-process anomaly requiring investigation (wrong artifact deployed, registry overwrite, stale CI output, container carrying a different JAR, or tampered metadata). Never patch the endpoint to hide the discrepancy.

## 20. Common pitfalls and fixes

| Symptom | Possible cause | Correct action |
| --- | --- | --- |
| `/actuator/info` returns empty despite Actuator | build-info/`git.properties` not generated or contributor/config disabled | Enable `build-info`/`bootBuildInfo`; inspect resource and HTTP exposure |
| `GET /actuator/info` returns 404 | HTTP info endpoint not exposed | `management.endpoints.web.exposure.include=health,info`; secure access |
| Spring fails to create `BuildProperties` bean | `META-INF/build-info.properties` absent on classpath or goal/task did not run | Check Maven execution/Gradle `bootBuildInfo` and JAR entries |
| File only has `build.version`, missing commit/run | CI parameters not passed or `additionalProperties` missing | Configure fields and verify metadata after packaging |
| Release artifact records `ci.commit=local` | Missing CI properties; dev fallback leaked into release | Fail pipeline on fallback metadata; cross-check SHA with `git rev-parse HEAD` |
| Commit in JAR differs from PR head commit | PR built synthetic merge commit | Record built SHA and PR head SHA separately; never conflate them |
| `git.branch=HEAD` or empty | CI checked out detached HEAD | Record trigger ref from CI event; keep SHA from checked-out commit |
| Same run ID produced two different JARs | Workflow rerun with another attempt or matrix jobs | Record attempt, job/matrix, and **artifact digest** |
| Identical filename/version yet different SHA-256 | Rebuilt artifact or differing timestamp/run ID metadata | Compare bytes, build inputs, and provenance; do not treat version as identity |
| SHA-256 stored inside JAR mismatches final file | Self-reference from embedding digest inside the artifact | Compute hash **after** packaging and store externally |
| Maven imports BOM yet generates no build-info | BOM only manages dependency versions | Bind `spring-boot:build-info` and `repackage` in Boot Maven Plugin |
| Gradle `bootBuildInfo` always re-runs | Default `build.time` changes | Consider `excludes = ['time']`; inspect all dynamic fields |
| CI builds another repo yet logs same SHA | Missing repository namespace | Store repository URI/ID alongside full SHA; never rely on bare SHA alone |
| Public endpoint leaks branch name/private repo | Info or custom lineage endpoint overly exposed | Restrict HTTP exposure, use Spring Security, or keep metadata internal |
| Artifact uploaded properly yet deploy rebuilds | Deploy stage runs Maven/Gradle again | Promote **exact tested file/digest**; never rebuild at deploy |
| OCI tag `latest` points to another version | Mutable image tag | Pin image digest and store JAR digest → image digest mapping |
| `git.properties` and build-info have differing SHAs | Plugins read different checkouts/refs/times | Inspect pipeline, pick one authoritative built SHA, add consistency gate |
| CI output has hash yet does not prove trusted builder | Checksum alone lacks signed provenance | Use attestation/signature/identity checks per supply-chain policy |

### Quick debugging procedure

1. **Identify the actual JAR file** built and slated for release.
2. Use `jar tf` to find `BOOT-INF/classes/META-INF/build-info.properties`.
3. Use `unzip -p` to read commit/ref/run/attempt directly from the binary.
4. Check `git rev-parse HEAD` of the CI checkout and the full triggering ref.
5. Check CI run ID, attempt, job/matrix, test logs, and validation status.
6. Recompute the file's SHA-256 and compare against the artifact store/deployment record.
7. When trusted provenance is required, verify signature/attestation subject digest and builder identity.
8. On mismatch, fail the gate and fix build/deploy scripts; **never edit a JAR after hashing/signing**.

## 21. Reinforcement exercises

**Scenario A.** An artifact has version `1.0.0` and ref `main`. Is that enough to identify the built commit?

*Answer:* No. Branches are movable pointers and versions can be reused. You need the full commit SHA alongside the repository identity.

**Scenario B.** GitHub Actions reruns workflow `run_id=8123456789`. Why record the attempt?

*Answer:* `run_id` stays unchanged across GitHub Actions reruns, while `run_attempt` increments. Two runs may execute in different environments or yield different artifacts; attempt and digest distinguish them.

**Scenario C.** The same commit is built twice, embedding two different run IDs into `build-info.properties`. Will the JAR SHA-256 hashes match?

*Answer:* Typically **no**, because a metadata file inside the archive changed. To achieve byte-for-byte equality across invocations, move run ID/attempt to external provenance and control all other non-deterministic inputs.

**Scenario D.** CI computed digest D of the JAR, then injected D into the manifest and uploaded it. Can D verify the uploaded file?

*Answer:* No, because editing the manifest changed the JAR's bytes. Always compute the hash **after all artifact modifications** and store the hash externally.

**Scenario E.** A GitHub Pull Request has a PR head SHA different from `git rev-parse HEAD` inside the job. What should metadata record?

*Answer:* Store the built commit SHA from checkout (which may be a synthetic merge commit), plus the optional PR head SHA in a separate field. Never call the PR head SHA the actual built source if the build ran on the merge commit.

**Scenario F.** `spring-boot-starter-actuator` is included, yet `/actuator/info` does not display commit and run ID. Is adding `management.endpoints.web.exposure.include=health,info` sufficient?

*Answer:* Not yet. You must also generate a valid `META-INF/build-info.properties` or `git.properties`, enable the contributor, place the file on the classpath, and secure the endpoint per policy.

**Scenario G.** Maven `pom.xml` declares custom build-info fields, yet CI forgot to pass `-Dci.commit`. Build and tests still pass. Should it be published?

*Answer:* No. The sample uses a `local` fallback for developers; release gates must fail when commit/run identity does not match the checkout and CI event.

**Scenario H.** One run produces three distinct module JARs. Can the same run ID uniquely represent all three files?

*Answer:* Run ID only ties them to the same workflow; each artifact must have its own module/coordinate and **distinct digest**, optionally alongside job/matrix variant.

**Scenario I.** A Docker image label `org.opencontainers.image.revision` points to SHA X, while the deployment registry lists a digest matching a JAR from SHA Y. Which should you trust?

*Answer:* Trust neither as absolute proof yet. Cross-check signed provenance/subject digests, build logs, JAR bytes inside the image, and deployment records; labels are self-declared data.

**Scenario J.** A team wants to roll back by running "rebuild tag v1.0.0 and deploy." Does that guarantee the exact binary that passed QA earlier?

*Answer:* No. Tag/version is only one input; outputs can diverge due to dependencies, toolchains, timestamps, or run metadata. Roll back using the **QA-verified artifact digest**.

## 22. Acceptance checklist for artifact → CI → source traceability

**Source and build:**

- Record repository identity, **full SHA of the actual built checkout**, trigger ref, and event type.
- Namespace CI run ID by provider/repository; record attempt and job/variant where applicable.
- Local fallback allowed for dev, **rejected** by release gates.
- Source tree and dependency/toolchain inputs identified; build executes required tests/checks.

**Embedded metadata:**

- Maven `build-info` or Gradle `bootBuildInfo` actually runs.
- `META-INF/build-info.properties` exists in compiled classes and `BOOT-INF/classes/META-INF` inside the executable JAR.
- Custom fields `ci.commit`, `ci.ref`, `ci.run.id`, `ci.run.attempt` match CI context.
- If `git.properties` is present, it does not contradict the recorded full SHA.
- Actuator/custom lineage endpoints leak no secrets and are not publicly exposed against policy.

**Artifact and release:**

- Compute SHA-256 **after** packaging finishes; never modify the JAR after hashing/signing.
- CI artifact store, registry, container image, and deployment all reference the **exact verified digest**.
- Different reruns/matrices/modules are distinguished by attempt/job/artifact identity.
- Tests, archive inspection, smoke tests, and policy approvals pass before production.
- Where trusted provenance is required, CI signs an attestation with subject digest and builder/source identity, and deploy gates verify it.
- Where reproducibility is required, omit run-specific metadata from the JAR and compare independent builds empirically.

**Conclusion:** **Commit SHA identifies code revision, ref identifies context, run ID + attempt identify the CI invocation, and artifact digest identifies the exact released bytes.** Spring Boot `build-info`/`bootBuildInfo` and `BuildProperties` provide the standard mechanism to embed metadata in an executable JAR; Git plugins/`git.properties` are a complementary source. The traceability chain is only complete when **metadata inside the JAR matches the CI checkout, the file digest is verified, and deployment uses the exact QA-approved artifact**.

### Official documentation

- Spring Boot 3.3.13 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot — Maven build-info goal: https://docs.spring.io/spring-boot/3.4/maven-plugin/build-info.html
- Spring Boot 3.3 — Gradle Plugin: Generating Build Information: https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html
- Spring Boot 3.3.13 — Actuator info: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3.13 — BuildProperties API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/BuildProperties.html
- GitHub Actions — Contexts Reference: https://docs.github.com/en/actions/reference/workflows-and-actions/contexts
- GitHub Actions — Default Variables: https://docs.github.com/en/actions/reference/workflows-and-actions/variables
- Git — `rev-parse`: https://git-scm.com/docs/git-rev-parse
- SLSA — Provenance v1.1: https://slsa.dev/spec/v1.1/provenance
- OCI Image Specification — Annotations: https://github.com/opencontainers/image-spec/blob/main/annotations.md