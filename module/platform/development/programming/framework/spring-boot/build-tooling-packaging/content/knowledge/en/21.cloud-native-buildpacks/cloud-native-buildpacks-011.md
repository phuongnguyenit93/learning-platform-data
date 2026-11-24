# Private Registry Authentication and Image Publishing Configuration

Spring Boot can produce an **OCI container image with Cloud Native Buildpacks (CNB)** via Maven `spring-boot:build-image` or Gradle `bootBuildImage` without writing a Dockerfile. Building successfully on a local machine does not mean the image has been pushed to a **private registry**. When an organization uses private registries, you must distinguish precisely between **pulling the builder/run image**, **pushing the application**, **each identity's permissions**, **target image name**, **when publish runs**, and **proof of publication**.

**Remember:** In Spring Boot 3.3, `docker.builderRegistry` handles authentication when fetching private builder/run images; `docker.publishRegistry` handles authentication when publishing the generated application image. The target push registry is chosen from the **host in the image name** (`registry.example.com/team/cnb-registry-demo:1.0.0`), not merely from `publishRegistry.url`. Only enabling `publish` in Maven or `--publishImage` in Gradle instructs the plugin to push. An image sitting in the Docker daemon without being pushed is not yet a published artifact.

This lesson pins examples to **Java 17, Spring Boot 3.3.13, Maven 3.9.x or compatible Gradle**. The hostnames `registry.example.com`, `mirror.corp.example`, and package `dev.example` are illustrative values, **not** live repositories. Only execute push operations when authorized, with a real registry and secret store. Versions are pinned for consistent explanation, not claimed as the latest releases.

## 1. Architecture of CNB Images and Authentication Points

The Spring Boot plugin connects to a Docker-compatible daemon, creates a build container from the CNB builder, and uses buildpacks and lifecycle to produce an application image. The builder image holds buildpacks/lifecycle; the run image provides the runtime base; the application image is the deployable artifact.

```text
                         Java source / Maven / Gradle
                                     |
                                     v
                            Spring Boot plugin
                                     |
                                     v
                              Docker daemon
                                     |
             +-----------------------+-------------------+
             |                                           |
             v                                           v
  Private builder registry                      Private run registry
  pull builder image                            pull run image
  docker.builderRegistry                        docker.builderRegistry
             |                                           |
             +-----------------------+-------------------+
                                     |
                                     v
                          CNB builder/lifecycle
                                     |
                                     v
                             Application image
                 registry.example.com/team/cnb-registry-demo:1.0.0
                                     |
                           publish=true / --publishImage
                                     |
                                     v
                           Private application registry
                           docker.publishRegistry
                                     |
                                     v
                           Remote manifest digest
                                     |
                          pull identity of runtime
                                     |
                                     v
                             Kubernetes / Docker
```

| Operation | Permission Needed | Credential Domain | Result to Verify |
| --- | --- | --- | --- |
| Pull builder image | `read/pull` | Registry hosting builder | Builder image has expected tag/digest |
| Pull run image | `read/pull` | Registry hosting run image | Run image matches builder stack |
| Push application | `write/push` | Registry where app image is published | Manifest/layers accepted |
| Pull at deploy time | `read/pull` | Identity of deploying Pod/host | Deployment actually pulls image |
| Verify image | `read/inspect` | Registry after publish | Image digest matches release record |

**Never use a single writer token for everything.** The CI account only needs pull on builder/run and push on the specific application repository; the runtime cluster only needs pull on the final artifact. Writer permissions should be scoped narrowly to a namespace/repository, never an admin role.

### 1.1. Three Image Types Can Use Different Registries

```text
mirror.corp.example/buildpacks/java-builder:approved
mirror.corp.example/buildpacks/java-run:approved
registry.example.com/team/cnb-registry-demo:1.0.0
```

The first two references serve the CNB lifecycle, while the last is the application image. If builder/run live on one private host and the app on another, the app publish token does **not** automatically pull the builder. Conversely, a builder pull token should normally **not** have push access to the application repository.

If the builder image points to its default run image in metadata, `runImage` can be left at the default. Override it only when the enterprise intentionally mirrors the run image **and** ensures stack/run-image compatibility. Depending on registry and plugin mechanisms, if builder/run reside on different registries, multiple auth identities or daemon credential helpers may be needed; do not assume one `builderRegistry` credential pair works across every host.

### 1.2. Docker Daemon vs Docker Registry

| Component | Responsibility | Typical Error |
| --- | --- | --- |
| Docker daemon | Runs builder container, manages local images, provides Docker API | `Cannot connect to the Docker daemon` |
| Docker registry | Accepts pushes/pulls and stores OCI manifests/layers | `unauthorized`, `denied`, `manifest unknown` |
| Maven/Gradle plugin | Calls CNB/Docker API, sets image name, supplies registry credentials | Wrong name, missing publish flag |
| CI runner | Provides JDK, checks out source, injects secrets, Docker socket, network | Missing token or publish permission |
| Kubernetes runtime | Pulls published image, starts Pod | `ErrImagePull`, `ImagePullBackOff` |

`docker info` succeeding proves a daemon is reachable, **not that you have permission to publish**. `docker login` succeeding only confirms a registry login mechanism, **not that a missing daemon issue is fixed**.

## 2. Image Name Determines the Target Registry

A typical reference:

```text
registry.example.com:5000/team/cnb-registry-demo:1.0.0
|------ host:port -----|------ repository ------|tag|
```

A full reference contains registry host, namespace/repository, and tag. To publish to a private registry, specify **all three**; do not let the plugin default to `docker.io/library/...` while only adding credentials for an internal registry.

**Common mistake:** configuring `docker.publishRegistry.url=registry.example.com` while leaving the image name as `docker.io/library/cnb-registry-demo:1.0.0`. Official Spring Boot 3.3 documentation clarifies: the `url` field is passed to registry-auth logic, **not used to determine the publish destination**. The destination always comes from the registry part of the image name.

| Field | Example | Meaning |
| --- | --- | --- |
| Host | `registry.example.com` | Push destination |
| Namespace | `team` | ACL/ownership area |
| Repository | `cnb-registry-demo` | Product |
| Tag | `1.0.0` or full commit SHA | Potentially mutable label |
| Digest | `@sha256:...` | Actual manifest/index identifier |

`@sha256:...` above is only a **format template**, not a usable hash. Registries generally let tags be repointed to a new manifest unless immutability is enabled. For exact rollbacks, record the **verified registry digest**, not just a `latest` tag.

### 2.1. Common Tagging Patterns

- `1.0.0`: fits semantic releases; requires preventing overwrites or storing the digest.
- `git-<short-sha>`: concise to read; carries long-term collision risk, so provenance should still keep the full SHA.
- `git-<full-sha>`: clear revision; yet two builds of the same commit are not guaranteed to be byte-identical.
- `run-<run-id>-<attempt>`: distinguishes CI reruns; also include repo/workflow/job namespace if producing multiple images.
- `latest`: handy for local testing, unsuitable for pinning exact production artifacts.

Never put tokens/passwords into image tags, OCI labels, or repository paths; those values can show up in registry logs and UIs.

## 3. Two Publishing Approaches: Direct Plugin vs Docker Push

### Approach A — Spring Boot Plugin Build and Push

Maven:

```bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-registry-demo:1.0.0 \
  -Dspring-boot.build-image.publish=true
```

Gradle:

```bash
./gradlew bootBuildImage \
  --imageName=registry.example.com/team/cnb-registry-demo:1.0.0 \
  --publishImage
```

These illustrate **how to enable publish**, and only succeed when daemon/registry/auth are configured. For private registries, configuring `publishRegistry` may be required; do not expect the plugin to rely automatically on Docker CLI logins across every version/runner.

### Approach B — Build Local Image First, Then Push via Docker CLI

```bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-registry-demo:1.0.0

docker image inspect registry.example.com/team/cnb-registry-demo:1.0.0
docker push registry.example.com/team/cnb-registry-demo:1.0.0
```

Approach B uses **Docker CLI credentials**, such as `docker login --password-stdin`. Useful when policy requires scanning/local smoke testing/approval **before** pushing. If you already chose direct plugin publishing, calling `docker push` afterward is usually redundant.

**Plugin default is `publish=false`.** A finished image build visible in `docker images` does not mean the remote registry has it. Verify after pushing via remote pull/manifest digest.

## 4. Hands-On Spring Boot Java 17 Example

We build a small REST app `cnb-registry-demo`. The `GET /status` endpoint returns `cnb-ready`; we use it as a smoke test after pushing and pulling the image back.

### 4.1. Project Structure

```text
cnb-registry-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/cnb/
    │   ├── CnbRegistryApplication.java
    │   └── StatusController.java
    └── test/java/dev/example/cnb/
        └── StatusControllerTest.java
```

You can use the Maven POM in section 5 **or** the Gradle `settings.gradle`/`build.gradle` in section 7 with the **same Java sources**. There is no need to maintain both build definitions in one project unless specifically required.

### 4.2. Main Application

`src/main/java/dev/example/cnb/CnbRegistryApplication.java`:

```java
package dev.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbRegistryApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbRegistryApplication.class, args);
    }
}
```

### 4.3. Controller

`src/main/java/dev/example/cnb/StatusController.java`:

```java
package dev.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/status")
    public String status() {
        return "cnb-ready";
    }
}
```

### 4.4. Testing with MockMvc

`src/test/java/dev/example/cnb/StatusControllerTest.java`:

```java
package dev.example.cnb;

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
class StatusControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void statusReturnsExpectedBody() throws Exception {
        mvc.perform(get("/status"))
                .andExpect(status().isOk())
                .andExpect(content().string("cnb-ready"));
    }
}
```

This tests the Spring context on the test classpath and does **not** prove the OCI image built/pushed or that the runtime image starts. Image and remote pull verification in later sections are mandatory additional steps.

## 5. Maven Spring Boot 3.3: Complete POM for `publishRegistry`

`pom.xml`:

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
    <artifactId>cnb-registry-demo</artifactId>
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
                        <name>${env.IMAGE_NAME}</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                    <docker>
                        <publishRegistry>
                            <username>${env.REGISTRY_USER}</username>
                            <password>${env.REGISTRY_TOKEN}</password>
                        </publishRegistry>
                    </docker>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**How to read this accurately:**

1. `IMAGE_NAME` must be a **full target reference** such as `registry.example.com/team/cnb-registry-demo:1.0.0`. Do not let a release run with an empty name; CI must validate variables before `build-image`.
2. `REGISTRY_USER`/`REGISTRY_TOKEN` come from the environment when Maven runs. These are **app push** credentials, not builder credentials.
3. `BP_JVM_VERSION=17` is a Paketo Java buildpack config variable, **not a channel for secrets**. Never put tokens inside `image.env`; buildpacks may log or record certain environment variables.
4. The POM intentionally **omits** `<publish>true</publish>` as a default. Only authorized release jobs turn on `-Dspring-boot.build-image.publish=true`.
5. `spring-boot-starter-parent` manages versions and the `repackage` goal. `spring-boot:build-image` invokes CNB to create the image; `build-image-no-fork` is used when the archive already exists from the same lifecycle invocation.
6. `${env...}` in the POM is Maven syntax for reading environment variables. **This example POM needs those variables to run `build-image`**; if image name/credentials are unset, run only tests/packaging without publishing. In enterprise projects, split local/release Maven profiles to avoid requiring publish credentials unnecessarily.

**Security:** env injection does not guarantee secrecy in every situation. Never print `env`, `help:effective-pom` (especially with resolved secrets), `mvn -X`, or process environments on shared runners. Never commit credentials or pass tokens on the CLI via `-Dpassword=...` on uncontrolled jobs.

### 5.1. Local Maven Check and Un-published Image Build

Once the Docker daemon is accessible, in Bash:

```bash
export IMAGE_NAME="registry.example.com/team/cnb-registry-demo:local"
mvn -B -ntp clean verify
mvn -B -ntp spring-boot:build-image
docker image inspect "$IMAGE_NAME"
```

`spring-boot:build-image` suits direct CLI invocation because it forks the lifecycle to `package`, ensuring the JAR input exists. Even if `mvn verify` ran beforehand, this goal may repeat some `package` steps; in CI you can use the no-fork goal after `verify`.

With `publish=false`, the plugin does not push to the target private registry. However, if your POM/provider resolves and checks `publishRegistry` values even when not publishing, supply harmless placeholder values or use a separate local Maven profile. Never supply real secrets just to run unit tests that do not log in.

### 5.2. Maven Publish After Quality Gates

With `IMAGE_NAME`, `REGISTRY_USER`, and `REGISTRY_TOKEN` provided by the CI secret store:

```bash
test -n "${IMAGE_NAME:-}"
test -n "${REGISTRY_USER:-}"
test -n "${REGISTRY_TOKEN:-}"

mvn -B -ntp verify spring-boot:build-image-no-fork \
  -Dspring-boot.build-image.publish=true
```

**Why use `build-image-no-fork` here?** Maven runs the `verify` lifecycle first—completing `package` and bound goals—and then invokes the CNB goal **without re-forking the lifecycle**. This fits release policies wanting to avoid repeating `package` unintentionally. For standalone CLI invocations on a workspace without a built JAR, use `spring-boot:build-image` (forking) instead of `build-image-no-fork`.

**Do not assume Maven `verify` automatically runs every static/security/integration check**: those plugins/jobs must be configured and marked required per policy. If an external vulnerability scan is mandatory, the publish job must wait for it to pass.

### 5.3. Common CLI Properties

| Maven Option | Meaning |
| --- | --- |
| `-Dspring-boot.build-image.imageName=...` | Sets image name from CLI via plugin property |
| `-Dspring-boot.build-image.publish=true` | Enables publishing |
| `-Dspring-boot.build-image.builder=...` | Overrides builder image |
| `-Dspring-boot.build-image.runImage=...` | Overrides run image |
| `-Dspring-boot.build-image.pullPolicy=ALWAYS` | Pull rule for builder/run |
| `-B -ntp` | Maven batch mode and reduced download progress output |

When the POM already defines `<name>${env.IMAGE_NAME}</name>`, prefer **one single configuration source** via `IMAGE_NAME` to avoid ambiguity between environment and CLI overrides. Verify the actual name in logs without exposing secrets.

## 6. Maven Using Private Builder/Run Images

If builder and run images are mirrored internally, use this fragment to **replace** the `<image>` and `<docker>` sections inside the Spring Boot Maven Plugin configuration:

```xml
<image>
    <name>${env.IMAGE_NAME}</name>
    <builder>${env.CNB_BUILDER_IMAGE}</builder>
    <runImage>${env.CNB_RUN_IMAGE}</runImage>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
    </env>
</image>
<docker>
    <builderRegistry>
        <username>${env.BUILDER_REGISTRY_USER}</username>
        <password>${env.BUILDER_REGISTRY_TOKEN}</password>
    </builderRegistry>
    <publishRegistry>
        <username>${env.REGISTRY_USER}</username>
        <password>${env.REGISTRY_TOKEN}</password>
    </publishRegistry>
</docker>
```

Expected environment variables (names descriptive only, containing no real secrets):

```text
CNB_BUILDER_IMAGE = mirror.corp.example/buildpacks/java-builder:approved
CNB_RUN_IMAGE     = mirror.corp.example/buildpacks/java-run:approved
IMAGE_NAME        = registry.example.com/team/cnb-registry-demo:1.0.0
BUILDER_REGISTRY_USER  = injected-from-ci-secret-store
BUILDER_REGISTRY_TOKEN = injected-from-ci-secret-store
REGISTRY_USER          = injected-from-ci-secret-store
REGISTRY_TOKEN         = injected-from-ci-secret-store
```

**This is not a complete POM and `injected-from-ci-secret-store` strings are not valid tokens.** You need real authorized credentials and real, compatible builder/run images.

**Important limitations:**

- `builderRegistry` controls access to private builder/run images; `publishRegistry` controls application pushes.
- If the two private images reside in **two separate registries** requiring two distinct identities, verify plugin/daemon/credential helper support for each host. Do not assume one `builderRegistry` credential pair works across every host.
- Docker registry credentials do not authenticate private Maven repositories, buildpack dependency mirrors, or HTTP proxies. Those need separate configurations/bindings and trust setup.
- The run image must be compatible with the builder's stack/lifecycle. Switching run images to be “smaller” without checking compatibility can break launch.
- Builder/run images should be chosen via approved tags/digests with scan/signing policies, never picking random images merely because registry login succeeded.

## 7. Gradle 3.3: `bootBuildImage` with `publishRegistry`

Gradle uses the `bootBuildImage` task of the Spring Boot Gradle Plugin. This is an **alternative build** for the exact same Java sources in section 4; no POM is needed when using Gradle.

`settings.gradle`:

```groovy
rootProject.name = 'cnb-registry-demo'
```

Complete `build.gradle` (Groovy DSL):

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

tasks.named('test') {
    useJUnitPlatform()
}

def imageInput = providers.environmentVariable('IMAGE_NAME')
        .orElse('registry.example.com/team/cnb-registry-demo:local')
def userInput = providers.environmentVariable('REGISTRY_USER')
def tokenInput = providers.environmentVariable('REGISTRY_TOKEN')

tasks.named('bootBuildImage') {
    imageName = imageInput.get()

    docker {
        publishRegistry {
            if (userInput.present && tokenInput.present) {
                username = userInput.get()
                password = tokenInput.get()
            }
        }
    }
}
```

**Meaning:**

- `bootBuildImage` builds an OCI image from the executable Boot app with CNB; the image name is explicit with a local default.
- `publishRegistry` reads credentials from the environment only when both variables exist. **Release jobs must fail fast** if variables are missing; do not rely on local credential fallbacks when publishing.
- `publish=true` is not enabled by default in the build script. CI enables `--publishImage` intentionally.
- Tests use JUnit Platform. Running `bootBuildImage` alone does not run all verification tasks; required CI must run `build` plus any policy-mandated checks.
- `providers.environmentVariable` reads the Gradle process's environment, never baking secrets into the image. Still, calling `.get()` during task configuration can affect configuration cache/caching depending on Gradle/plugin version; never log resolved tokens.

### 7.1. Gradle Local and CI

If the repository includes a Gradle Wrapper compatible with Spring Boot 3.3:

```bash
./gradlew clean build
./gradlew bootBuildImage
docker image inspect registry.example.com/team/cnb-registry-demo:local
```

On Windows use `gradlew.bat`. Do not assume every repo includes a wrapper; if missing, generate or install a compatible Gradle version.

CI after injecting secrets and image name:

```bash
test -n "${IMAGE_NAME:-}"
test -n "${REGISTRY_USER:-}"
test -n "${REGISTRY_TOKEN:-}"

./gradlew clean build bootBuildImage --publishImage
```

`./gradlew build` (Java lifecycle) and `bootBuildImage` are two distinct steps; `bootBuildImage` does not prove unit/integration/security gates passed. CLI `--publishImage` is a **task option of `bootBuildImage`**, not a Docker daemon setting.

### 7.2. Gradle Private Builder Registry

Replace/extend the matching task block when CI has both builder/run and publish credentials:

```groovy
tasks.named('bootBuildImage') {
    imageName = providers.environmentVariable('IMAGE_NAME').get()
    builder = providers.environmentVariable('CNB_BUILDER_IMAGE').get()
    runImage = providers.environmentVariable('CNB_RUN_IMAGE').get()

    docker {
        builderRegistry {
            username = providers.environmentVariable('BUILDER_REGISTRY_USER').get()
            password = providers.environmentVariable('BUILDER_REGISTRY_TOKEN').get()
        }
        publishRegistry {
            username = providers.environmentVariable('REGISTRY_USER').get()
            password = providers.environmentVariable('REGISTRY_TOKEN').get()
        }
    }
}
```

This is a **replacement fragment for the `tasks.named('bootBuildImage')` block**, not a second competing `publishRegistry` block. `Provider.get()` fails if required CI variables are unset, which is appropriate for **mandatory release configuration**. When builder/run images are public, omit `builderRegistry` and do not require builder secrets.

## 8. Docker Login and Credential Helpers

The Docker CLI uses its own credential store. Logging in without exposing password/token on the command line looks like:

```bash
test -n "${REGISTRY_USER:-}"
test -n "${REGISTRY_TOKEN:-}"

printf '%s' "$REGISTRY_TOKEN" |
  docker login registry.example.com \
    --username "$REGISTRY_USER" --password-stdin
```

Here the token is injected into the environment by a **secret manager**; the example uses no real value. `docker login` takes a **registry host** (optionally with port), not a repository path like `registry.example.com/team`.

### 8.1. What Is a Credential Store?

Docker can use:

- OS keychain/credential manager from Docker Desktop.
- Per-registry `credHelpers` or global `credsStore`.
- Docker config file (`$HOME/.docker/config.json` or `DOCKER_CONFIG` directory).

Without a helper/store, Docker may store **base64-encoded** auth in `config.json`. Base64 is **not secure encryption**; never commit config files, never print config to logs, and never share them across unrelated CI jobs.

**The Spring Boot plugin is not the Docker CLI.** `docker login` succeeding on a developer laptop does not guarantee the Maven/Gradle plugin in CI sees the same credential helper and config. Spring Boot 3.3 supports explicit `docker.publishRegistry`/`docker.builderRegistry` config; this lesson uses them for the plugin. If a plugin/version supports reading Docker config, verify that behavior on your real CI runner before removing explicit credentials.

### 8.2. Token, Password, and Identity Token

Spring Boot 3.3 supports username/password or `token` depending on the registry's accepted auth method. Some providers issue a **short-lived registry access token** used as the password where Docker Registry protocol expects username/password; others accept an identity token directly. **Do not mix the two arbitrarily.** Read your registry's documentation and grant properly scoped permissions.

### 8.3. Separating Pull and Push

- Writer token: granted only to trusted publish jobs, scoped to write to a single app repository.
- Builder pull token: read-only access to builder/run images.
- Deployment pull token: read-only access to the app image in production/staging, without builder access.
- If CI supports OIDC federation for short-lived cloud registry tokens, prefer that over static long-lived secrets.
- Never embed credentials into JARs, OCI image labels, image names, buildpack env `BP_*`, Dockerfile `ENV`, or output logs.

## 9. Sample GitHub Actions CI to Publish to GHCR

GitHub Container Registry uses `ghcr.io`. GitHub Actions can use `GITHUB_TOKEN` with job permission `packages: write` to publish to an appropriately linked package. This depends on package-level permissions, org policies, and repository association; `packages: write` does not grant push access to arbitrary repositories.

Example workflow for the **Maven project in section 5**, triggered only on pushes to `main`:

`.github/workflows/publish-image.yml`:

```yaml
name: Verify and publish CNB image

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  image:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Define image target from commit
        shell: bash
        run: |
          set -euo pipefail
          image="ghcr.io/${GITHUB_REPOSITORY,,}:${GITHUB_SHA}"
          echo "IMAGE_NAME=$image" >> "$GITHUB_ENV"

      - name: Verify and publish with buildpacks
        shell: bash
        env:
          REGISTRY_USER: ${{ github.actor }}
          REGISTRY_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          test -n "${IMAGE_NAME:-}"
          test -n "${REGISTRY_USER:-}"
          test -n "${REGISTRY_TOKEN:-}"
          mvn -B -ntp verify spring-boot:build-image-no-fork \
            -Dspring-boot.build-image.publish=true

      - name: Verify private image is pullable
        shell: bash
        env:
          REGISTRY_USER: ${{ github.actor }}
          REGISTRY_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          printf '%s' "$REGISTRY_TOKEN" |
            docker login ghcr.io \
              --username "$REGISTRY_USER" --password-stdin
          docker pull "$IMAGE_NAME"
          docker image inspect --format '{{json .RepoDigests}}' "$IMAGE_NAME"
          docker logout ghcr.io
```

**Technical details to note:**

1. `GITHUB_REPOSITORY` has the form `owner/repo`; Bash `${GITHUB_REPOSITORY,,}` lowercases it to satisfy OCI repository naming rules. `GITHUB_SHA` is the push event revision; if adapting for PRs, separate PR head vs merge SHA checkout carefully.
2. `GITHUB_ENV` sets env vars for **subsequent steps**, not immediately in the same script. The build step after it receives `IMAGE_NAME`.
3. `GITHUB_TOKEN` is issued by Actions and exposed only in trusted steps; never save it to source/POM.
4. The Maven plugin uses `${env.REGISTRY_USER}`/`${env.REGISTRY_TOKEN}` from the POM without needing a prior Docker CLI login to publish. The final step runs a **separate Docker CLI login** to pull the image and inspect its remote digest.
5. `mvn verify spring-boot:build-image-no-fork` runs `verify`/bound `package` phases first before building/publishing; if static/SBOM/security checks live in other CI jobs, require them via status/job dependencies prior to publish.
6. `packages: write` must also be accepted by org/repository/package settings. If GHCR returns `denied`, check package access and repo linkage before requesting broader permissions.
7. `docker pull` after publish proves the remote registry holds the image and the account can read it; `RepoDigests` should be stored with the exact reference/digest in the release record. The abbreviated workflow only **prints the digest for observation**; real release pipelines must extract, validate, and archive the digest structurally.
8. Major action tags like `@v4` are illustrative; production CI should pin reviewed **immutable action commit SHAs** with supply-chain hardening.

### 9.1. Why Not Publish from Untrusted Pull Requests?

A PR from a fork can modify Maven/Gradle build scripts. If a job runs that code with a write token, the PR author could exfiltrate credentials or push a malicious image. Test PRs in jobs without publish secrets; publish only after merging to protected branches/tags with required checks passing. Never use `pull_request_target` to check out untrusted PR code with secrets without strict isolation/review.

## 10. Verifying the Published Image and Retrieving the Manifest Digest

**Do not rely solely on “BUILD SUCCESS” logs or `docker images`.** Both may only indicate a local build succeeded. After publishing, use a separate read identity to query the **remote registry**.

Linux/macOS Bash:

```bash
IMAGE_NAME="registry.example.com/team/cnb-registry-demo:1.0.0"

docker pull "$IMAGE_NAME"
docker image inspect --format '{{json .RepoDigests}}' "$IMAGE_NAME"
```

After pulling, `RepoDigests` may contain:

```text
["registry.example.com/team/cnb-registry-demo@sha256:..."]
```

The `...` is **illustrative**, containing no real digest. Select the matching repository entry and record the full digest. A local image can carry multiple `RepoDigests` if pulled/tagged across multiple repositories.

| Identifier | What It Represents | Suitable to Pin Deployment? |
| --- | --- | --- |
| Image tag | Human-readable pointer, can be overwritten | Insufficient without immutability |
| Local image ID | Digest of image config inside the Docker daemon | Not guaranteed equal to manifest digest |
| OCI registry manifest digest | Manifest or multi-platform index stored by registry | Yes, paired with full repository reference |
| Layer digest | A single layer | Does not identify the whole image |
| Git commit SHA | Source revision | Not equivalent to image digest |

Do not confuse `docker image inspect ... Id` with `RepoDigests`. **Image ID and registry manifest digest do not always refer to the same object**, because image config, manifest, and index are distinct artifacts.

### 10.1. Pinning an Image by Digest

Format:

```text
registry.example.com/team/cnb-registry-demo@sha256:<FULL_MANIFEST_DIGEST>
```

This is a sample syntax only. CI must obtain `FULL_MANIFEST_DIGEST` from the registry. Deployments then use the exact reference to avoid tag drift. For multi-platform images, distinguish between the **OCI index** digest and individual platform manifest digests; choose according to release/cluster policy.

### 10.2. Remote Pull Differs from Push Permissions

CI may push with a writer token while a Kubernetes Pod hits `ImagePullBackOff` due to missing pull identity, expired token, wrong namespace, TLS/CA issues, or platform mismatch. Spring Boot `publishRegistry` **does not** travel with the image into production. The cluster needs its own Kubernetes `imagePullSecrets`/workload identity with read access.

## 11. Smoke Testing the Pulled Image

Once you have a real `IMAGE_NAME` and `docker pull` succeeds:

```bash
docker image inspect --format '{{.Config.User}}' "$IMAGE_NAME"
docker image inspect --format '{{.Config.Entrypoint}}' "$IMAGE_NAME"

docker run --rm --name cnb-registry-demo-test \
  -p 127.0.0.1:18080:8080 \
  "$IMAGE_NAME"
```

Wait for Spring Boot startup logs; open a **second terminal**:

```bash
curl -fsS http://127.0.0.1:18080/status
```

Expected body:

```text
cnb-ready
```

The example uses loopback port mapping instead of exposing to the entire LAN. CNB builder/runtime stacks provide their own launcher and runtime user; **never assume the entrypoint is always `java -jar` or UID is `10001`** as in a manual Dockerfile.

In CI, use process management, timeouts, log capture, and cleanup so tests cannot hang forever. Passing a smoke test proves the image serves HTTP in the test environment, **not that production databases or networks are ready**.

## 12. Registries and Access Patterns by Provider

| Registry | Typical Image Name | Common Auth Strategy | What to Check |
| --- | --- | --- | --- |
| Docker Hub | `docker.io/org/app:1.0` | Username + access token | Org/repository ACL, rate limits |
| GitHub Container Registry | `ghcr.io/org/app:sha` | `GITHUB_TOKEN` or scoped PAT | `packages:write`, package/repo association |
| GitLab Registry | `registry.gitlab.com/group/project/app:sha` | Job/deploy token or user/token | Project and token scopes |
| Amazon ECR | `account.dkr.ecr.region.amazonaws.com/app:sha` | IAM exchanging short-lived Docker login password | Account/region/repository IAM |
| Google Artifact Registry | `region-docker.pkg.dev/project/repository/app:sha` | Workload identity/service account | Project/location/IAM |
| Azure Container Registry | `myregistry.azurecr.io/app:sha` | Managed identity, service principal/token | `AcrPush`/`AcrPull` |
| Harbor/self-hosted | `harbor.example.com/team/app:sha` | Robot account/token | Project RBAC, CA, tag immutability |

These are **illustrative structures**. Registry credentials are consumed by the Spring Boot plugin as Docker Registry auth accepted by that provider; for example, a raw AWS access key is **not** a valid ECR password directly. Cloud IAM must first issue/exchange a valid registry token, which is then passed to the plugin/CLI.

### 12.1. Never Use Over-Privileged Tokens Across All Steps

CI publishers should push only to the **target repository**, without permissions over every org package. Builder mirrors need only pull. Kubernetes needs only pull. Where policy supports OIDC/short-lived tokens, prefer them over long-lived PATs. Never commit tokens into POMs, `build.gradle`, Dockerfiles, or `.github/workflows`.

## 13. TLS, CA, and Network: Completely Distinct from Auth Errors

Problems often misdiagnosed as “wrong password”:

| Error | Layer | How to Investigate |
| --- | --- | --- |
| `Cannot connect to Docker daemon` | Daemon/socket | `docker info`, Docker context, `DOCKER_HOST` |
| `401 Unauthorized` | Registry authentication | Username/token/expiry/method |
| `403 Forbidden` or `denied: requested access to resource is denied` | Registry authorization | Write scope, namespace, package permissions |
| `x509: certificate signed by unknown authority` | TLS/CA trust | Install valid CA, verify hostname, certificate chain |
| `dial tcp ... timeout` | DNS/firewall/proxy | Network path from runner/daemon/builder |
| `manifest unknown` | Reference | Correct host/repo/tag/digest, did push finish? |
| `ImagePullBackOff` | Deployment runtime | `imagePullSecret`, ServiceAccount, CA, platform |
| `no basic auth credentials` | Auth lookup | Plugin credentials, Docker config/`DOCKER_CONFIG` |

Check the daemon:

```bash
docker version
docker info
docker context ls
```

If the Docker host uses TLS/remote daemon, configure client certificate/`docker.host`/`tlsVerify`/`certPath` properly per Spring Boot plugin documentation. **`docker.host` is the Docker daemon endpoint, not `publishRegistry.url`**. Never expose an unauthenticated/unencrypted Docker TCP API or run privileged containers merely to bypass permission errors.

### 13.1. Builder Containers Have Their Own Network Path

The CNB builder may need to download JDK/buildpack dependencies, Maven dependencies, or SBOM metadata from external hosts. Credentials for an OCI registry **do not automatically** unlock a private Maven repository or HTTP proxy. When timeouts occur, identify the **failing hostname** before rotating push tokens without knowing which layer failed.

### 13.2. Private CA

If a self-hosted registry uses an internal CA, the Docker daemon/runtime and builder components must trust the appropriate CA. Never enable `insecure-registries` or disable TLS in production as a knee-jerk reaction. If a private network/firewall blocks traffic, adjust network policies rather than disabling verification.

## 14. Secret Safety in Build and Publish Workflows

### 14.1. Patterns to Avoid

```bash
# Bad: password can appear in command line/shell history
docker login registry.example.com -u real-user -p plain-text-password

# Bad: secret can leak via process list or CI logs
mvn spring-boot:build-image -Ddocker.publishRegistry.password=plain-text-password
```

Never hardcode `password = "plain-text-password"` in Gradle scripts; never put PATs into `BP_*` env; never put auth data in image labels/tags; never commit `~/.docker/config.json`.

### 14.2. Recommended Practices

1. Use a CI secret manager or cloud workload identity.
2. Inject secrets only into trusted release jobs after required checks.
3. Scope tokens strictly to read/pull builder and write/push the specific app repo; never grant admin by default.
4. Prefer short-lived tokens with rotation, revocation, and audit logs.
5. Use `docker login --password-stdin` if pushing via Docker CLI.
6. With the plugin, configure `publishRegistry`/`builderRegistry`, avoiding CLI `-D...password` flags that leak easily.
7. Never print environment variables or resolved build configs containing secrets.
8. Never run untrusted PR/fork code with publisher tokens.
9. Never share Docker credential stores across multiple CI tenants.
10. Archive builder/run image digests, source commit, and registry manifest digest for provenance and incident response.

**Important:** environment secrets can still leak through process dumps, CI debug logging, or malicious build scripts. True security depends on runner trust boundaries, permissions, masking, and token lifecycles.

## 15. Multi-Module CI and Selecting the Right Image to Release

With a Maven monorepo:

```text
platform-parent/             root POM
├── common-library/          plain JAR
└── api-service/             Boot executable app + CNB image
```

Only the app needs the Spring Boot image plugin/publish config. In a reactor, you can test selected upstream modules:

```bash
mvn -B -ntp -pl :api-service -am verify
```

Then build the image for the app from available artifacts, depending on reactor/dependency resolution and exact Maven lifecycle. **Do not assume** `mvn -pl :api-service spring-boot:build-image` always picks up un-installed/unpublished source changes from a sibling library; ensure dependencies resolve the right versions.

Gradle multi-project:

```bash
./gradlew :api-service:build :api-service:bootBuildImage --publishImage
```

This is a **fragment for a repository containing an `api-service` module** with the plugin applied there. Gradle runs upstream module task dependencies when needed, yet does not automatically test unrelated sibling/downstream modules unless targeted. Release policies must specify required tests for the scope of changes.

When publishing multiple images in one CI run, record **separate digests** for each module/application. A Run ID does not replace artifact identity, and two jobs should never overwrite a shared mutable tag without coordination.

## 16. Traceability Chain from Commit to Image Digest

A useful release record includes:

```text
source.repository = org/service-repository
source.commit     = full Git SHA from checked-out HEAD
ci.run.id         = provider run identifier
ci.run.attempt    = retry/attempt number
module            = api-service
image.reference   = registry.example.com/team/api-service:version-or-sha
image.digest      = sha256 value read from registry manifest
builder.digest    = approved CNB builder digest
run.image.digest  = approved run image digest
validation        = required tests, scan and smoke-test result
```

This is a **data schema**, not live CI results. **Accuracy must rest on real evidence**:

1. Git checkout has the full commit SHA.
2. Required Maven/Gradle tests and static/security checks passed.
3. CNB build used controlled builder/run images.
4. Publish actually sent the application image to the intended repository name.
5. Image was pulled back from the registry and its verified manifest digest recorded.
6. Container smoke test ran against the remote image/digest.
7. Deployment pulls **the exact QA-verified digest**, without rebuilding at deploy time.
8. Optionally archive OCI SBOM and signed provenance/attestation bound to the subject digest if required by policy.

An image tag or label containing a Git SHA is self-asserted data, not a cryptographic supply-chain proof. For true authenticity, CI builders sign attestations and deployments verify builder identity + subject digest.

### 16.1. Image ID Is Not the Manifest Digest

Docker's local image `Id` usually corresponds to the image config digest. A registry reference using `@sha256:...` requires the manifest/index digest returned by the registry. Never substitute a local image ID in Kubernetes deployment manifests.

### 16.2. Why Can the Same Commit Yield Different Digests?

Builder/run images may change via mutable tags, buildpack dependencies may update, build environments may differ, timestamps/build metadata may vary, or CI run-specific values may be embedded. For reproducible builds, pin inputs and builder/run digests, control timestamps, and test repeatability empirically. A single commit SHA alone does not guarantee byte-identical images.

## 17. Troubleshooting Common Errors

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Local build succeeds, image missing from registry | `publish` is `false` | Enable `-Dspring-boot.build-image.publish=true` or `--publishImage` in trusted job |
| Image went to Docker Hub instead of private registry | Image name omits private host | Set full image name `registry.example.com/team/app:tag` |
| Push `401 Unauthorized` | Wrong/expired credentials | Verify username/token type/expiry; do not log token |
| Push `403 Forbidden` | Missing write scope | Check repo/namespace/package ACL; avoid granting broad permissions |
| Private builder pull fails | Missing `builderRegistry` for that host | Separate builder/run pull auth from app push auth |
| Builder pull works, publish fails | Builder token is read-only | Provision separate write token for publishing |
| GHCR denied despite `packages: write` | Package access/association misconfigured | Check org/package/repo policy |
| Docker CLI push fails while Maven plugin publish works | Docker CLI credentials differ from plugin | Run `docker login --password-stdin`/credential helper for CLI |
| CI passes on laptop yet fails on clean runner | Local Docker config/cache helped developer | Configure auth explicitly in CI |
| `x509 unknown authority` | Private CA | Fix trust store/CA/TLS; do not disable TLS |
| Docker daemon unavailable | Socket/context/TLS | `docker info`, Docker context, socket permissions |
| Registry `manifest unknown` on pull | Wrong repo/tag, pushed to different host, or incomplete | Compare image name and target registry |
| Kubernetes `ImagePullBackOff` | Missing deployment read identity | `ImagePullSecret`/ServiceAccount, node CA, reference |
| Image pushes fine yet container fails to start | Run image/JDK/launcher/app config | Docker logs, stack/run compatibility, smoke test |
| ECR token expired | Short-lived cloud registry credential | Generate token close to push time |
| Immutable tag push rejected | Tag already exists | Generate a new tag per policy; do not disable immutability |
| Multi-platform images from separate jobs overwrite same tag | Tag race | Tag per job/platform or assemble OCI index cleanly |
| Docker registry push token appeared in logs | Verbose build/CLI command contained secret | Revoke and rotate token; scrub logs per security policy |

### Quick Investigation Checklist

1. Does the image name contain the **correct registry host + repo + tag**?
2. Is plugin `publish` enabled? Is the Docker daemon running?
3. Did the error occur at **builder pull**, **run image pull**, **app push**, or **runtime pull**?
4. Are credentials present in the trusted job with the right **scope** (check presence only, never print values)?
5. Is the registry returning `401`, `403`, a TLS error, or a network error?
6. Are builder/run image versions and stack compatibility valid?
7. Does the image have a remote manifest digest? Can it be pulled back?
8. Did smoke tests run against the published image and was the digest saved in the release record?

## 18. Self-Check Exercises

**Exercise A.** A POM sets `docker.publishRegistry.url=registry.example.com` while `image.name=docker.io/library/app:1.0`. Where will the image publish?

*Answer:* Destination comes from the image name. Fix the name to `registry.example.com/team/app:1.0`; credential `url` does not reroute the host.

**Exercise B.** A CNB builder image in a private registry returns `401`, while the app writer token is valid. Which config should you check?

*Answer:* `docker.builderRegistry` credentials and the builder/run image host, not just `publishRegistry`.

**Exercise C.** Gradle `bootBuildImage` finishes and `docker images` shows the artifact. Can production deploy from the private registry yet?

*Answer:* Not proven. Enable publish, verify the push, pull the image from the registry, and capture its digest.

**Exercise D.** CI copies its push token into a Kubernetes `imagePullSecret`. Does that follow least privilege?

*Answer:* No. Pods only need read/pull scope; push tokens should never exist at runtime.

**Exercise E.** A GHCR job has `packages: write` yet gets `denied`. Is the Spring Boot plugin definitely broken?

*Answer:* No. Check GitHub package access, repository linkage, org settings, and the token's actual permissions.

**Exercise F.** Docker `Image ID` differs from `RepoDigests`. Which value should deployments pin?

*Answer:* Use the registry repository reference with the verified **manifest/index digest**, never substituting a local config image ID.

**Exercise G.** A developer ran `docker login`, yet the CI Maven plugin lacks tokens. Is that contradictory?

*Answer:* No. CI environment differs from a developer machine; the plugin needs auth settings/credential helpers on the actual runner. Docs provide explicit `publishRegistry` configuration.

**Exercise H.** CI publishes cleanly yet Kubernetes shows `ImagePullBackOff`. Is Maven `publishRegistry` at fault?

*Answer:* Not necessarily. Runtime pull is a separate step; inspect Pod identity/`imagePullSecret`, network/TLS, image ref, and platform.

**Exercise I.** Is using `BP_JVM_VERSION` to store an access token for a private Maven repo or OCI registry valid?

*Answer:* No. That is a buildpack setting selecting the Java version; secrets must go through proper auth/bindings, never general builder environment variables.

**Exercise J.** Does tagging with a Git SHA guarantee rolling back to the exact same image bytes?

*Answer:* Not if the tag is mutable. Save the QA-verified digest and deploy/rollback by digest.

## 19. Private Image Publishing Checklist

**Preparation:**

- Spring Boot app has a main class, Java 17 toolchain, and required tests.
- Docker-compatible daemon is running and CNB builder/run stack is suitable.
- Full image name contains registry host, repository namespace, and tag per conventions.
- Builder/run private registry credentials are read-only; `publishRegistry` is a narrow writer.
- Short-lived tokens are injected by a secret manager, absent from source/POM literals/build logs.
- Runner has working network/DNS/TLS/CA access to builder/run/app registries.

**Build and Publish:**

- Maven `build-image` or Gradle `bootBuildImage` runs on the right app module.
- Required unit/IT/static/security checks actually pass before publishing per policy.
- Publish option is enabled **intentionally in trusted jobs**, never on untrusted PRs.
- Target registry derives from the image name, not confused with `publishRegistry.url`.
- Plugin uses valid auth scheme/token, builder image, and run image.
- Build/push errors fail CI—never mask with `|| true` or `ignoreFailures`.

**Verification and Deployment:**

- Remote image can be pulled using a read identity separate from the push token.
- Registry manifest digest is recorded alongside Git SHA, CI run/attempt, and module.
- Smoke test runs against the pulled image, not merely the local JAR.
- Deployment uses the verified digest with dedicated pull identity/`imagePullSecrets`.
- SBOM/vulnerability scans, signing/attestations, and immutable tags follow policy.
- Never rebuild the image in the deploy stage while keeping the old artifact's tag/version.

**Conclusion:** With CNB, **registry auth and image publication are two responsibilities that must be configured per data direction**: read builder/run images via `builderRegistry`, write the application image via `publishRegistry`. The **full image name** selects the push target; the **publish option** authorizes sending the image; **CI secrets/permissions** determine access; and **remote digest + smoke tests** confirm the artifact genuinely exists and works. “Local image build succeeded” is only the first step, never proof of safe publication.

### Official Documentation

- Spring Boot 3.3 — Maven Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html
- Spring Boot 3.3 — Gradle Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html
- Spring Boot 3.3 — Maven build-image-no-fork: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image-no-fork.html
- Spring Boot 3.3 — Maven Plugin Goals: https://docs.spring.io/spring-boot/3.3/maven-plugin/goals.html
- Docker CLI — docker login: https://docs.docker.com/reference/cli/docker/login/
- Docker CLI — docker image push: https://docs.docker.com/reference/cli/docker/image/push/
- Docker CLI — docker image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Cloud Native Buildpacks Documentation: https://buildpacks.io/docs/
- GitHub Docs — Package publishing via Actions: https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions
- GitHub Docs — Container Registry: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- Kubernetes — Pull an Image from a Private Registry: https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/