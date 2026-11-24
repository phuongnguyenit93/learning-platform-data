# Comparing Buildpacks and Dockerfile by Customizability and Operational Requirements

## 1. Two Ways to Package the Same Java Application

In Spring Boot, you can produce a container image **without writing a Dockerfile** using Cloud Native Buildpacks (CNB), or define the image explicitly with a Dockerfile. Both options produce OCI-compatible images for Docker and Kubernetes, yet differ in **customizability, operating system control, update workflows, maintenance cost, and CI/CD infrastructure**.

**Scenario:** a team running multiple Spring Boot REST services wants to standardize on a packaging approach. Standard services need no special OS libraries, while a few applications require native tools, custom certificates, and specific filesystem layouts. Should the team use CNB for everything, Dockerfiles for everything, or combine both?

This lesson helps you:

1. Understand `buildpack`, `builder image`, `run image`, CNB lifecycle, and Dockerfile stages.
2. Compare the two approaches across **customizability** (Java runtime, OS packages, native libraries, process, entrypoint, filesystem, security) and **operational requirements** (CI, caching, registry, patching, SBOM, rebase, proxy, multi-platform, incident response).
3. Create the **same Spring Boot 4.1.2/Java 17 service**; from it, build one image with Maven `spring-boot:build-image` and another with a multi-stage Dockerfile.
4. Run both images on separate host ports, verify identical HTTP bodies, and accurately compare metadata/entrypoint/layers.
5. Understand how to use `BP_JVM_VERSION` at build time, plus `BPL_*` and `JAVA_TOOL_OPTIONS` at runtime with Paketo.
6. Recognize enterprise risks: custom builders, run-image compatibility, base-image updates, CVEs, ephemeral runner caches, registry credentials, root/non-root, and compliance.
7. Choose technology based on real constraints instead of one-sided claims that “Buildpacks are always better” or “Dockerfiles are more flexible so always better”.

**Context:** *Spring Boot Build Tooling Packaging → Cloud Native Buildpacks*. The sample uses Java 17, Spring Boot Maven Plugin **4.1.2**, Maven, and Docker. Learners need Maven/JDK and permission to use a Docker daemon or an organization-approved build service. Builder/runtime image tags in this document are illustrative; production must manage versions and digests.

## 2. Input Sources and Output Artifacts Diagram

~~~text
                         Java source + pom.xml
                                   |
                           Maven verify/package
                                   |
                        Spring Boot executable JAR
                                   |
             +---------------------+---------------------+
             |                                           |
     Cloud Native Buildpacks                          Dockerfile
             |                                           |
     builder image + buildpacks                 FROM / RUN / COPY / USER
     run image + CNB lifecycle                  multi-stage + BuildKit
             |                                           |
      OCI application image                         OCI application image
             |                                           |
             +---------------------+---------------------+
                                   |
                            Docker / Kubernetes
~~~

**An executable JAR is not a container image.** Maven `package` produces `target/*.jar`, while Spring Boot `build-image` or `docker build` creates an OCI image containing runtime OS, Java, application, and metadata. A successful build also **does not mean the image was pushed** to a registry, signed, or deployed.

### How Does Buildpacks Create an Image?

CNB comprises interconnected components:

| Component | Role |
| --- | --- |
| **Buildpack** | Contains `detect`/`build` logic to recognize the app, install runtime, or contribute launch layers |
| **Builder image** | Build environment containing buildpacks, lifecycle, order, and necessary tools |
| **Run image** | Base runtime layers of the final application image |
| **CNB lifecycle** | Orchestrates detection, analysis, restore, build, export; supplies launcher/rebase mechanisms |
| **CNB launcher** | Starts the process type chosen by buildpacks per image metadata |

Simplified flow:

~~~text
detect -> analyze -> restore -> build -> export
                                   |
                       selected Java buildpacks
                        + JRE/runtime layer
                        + app/dependency layers
                        + launch process metadata
                                   |
                             OCI image
~~~

The builder image **differs** from the run image: the builder holds the build environment; the final image rests on the run image plus launch/app layers. Do not assume every tool inside the builder appears in the final runtime image.

### How Does a Dockerfile Create an Image?

A Dockerfile describes the build through explicit instructions:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/demo.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

With multi-stage builds, one stage uses Maven/JDK to build, and a later stage uses a JRE to run. Dockerfiles control file copying, ownership, OS packages, shell commands, entrypoint, and image configuration. Instructions can be cached by Docker/BuildKit; **using a Dockerfile does not inherently mean slow builds or bloated images**.

## 3. Strengths and Limits in Customizability

### 3.1. Java Version and JVM Vendor

**Buildpacks:** with Paketo Java Buildpack, `BP_JVM_VERSION=17` requests the Java major version. Builders/buildpacks determine which JDK/JRE providers are supported, runtime image layout, and launch hooks. You can switch to a custom builder, alternate JVM buildpack, or compatible run image when changing vendors is needed.

**Dockerfile:** directly choose `FROM eclipse-temurin:17-jre` or another Java base image; you can copy a custom JRE built with `jlink` once tested. Flexibility is high, yet the Dockerfile author owns choosing and maintaining the base.

**Identical Java target bytecode does not guarantee identical JVM runtimes.** Record runtime major, vendor, patch level, architecture, and OS base for a fair comparison.

### 3.2. OS Packages, Native Libraries, and Certificates

**Buildpacks** can support native dependencies, custom CAs, certificates, and tools via buildpacks, extensions, custom builder/run images, or platform bindings. However, if a team needs arbitrary `apt-get install` commands inside an image for a bespoke binary, configuration is usually **more complex than a Dockerfile** without an existing custom CNB platform.

**Dockerfile** can run `RUN apt-get` or `apk` per base distro to install packages. This is easy to inspect in code review, at the cost of managing package sources, versions, CVEs, cleanup, and licenses. **Never bake secrets into image layers via `COPY`/`RUN`.**

### 3.3. Filesystem and Process Startup

- CNB images follow launch contracts/process metadata and filesystem conventions defined by buildpacks. Do not assume `ENTRYPOINT` is `["java","-jar",...]` or that the JAR sits at `/app/app.jar`.
- Dockerfiles can explicitly declare `WORKDIR`, `USER`, `RUN`, `COPY --chown`, `ENTRYPOINT`, and `CMD`. Useful when needing startup scripts, writable directories, timezone data, native binaries, or special process policies.
- Do not replace the CNB launcher with raw `java` without understanding launch hooks; doing so can break buildpack runtime features.
- Avoid shell-form `ENTRYPOINT` that inadvertently leaves a shell holding PID 1 and failing to forward `SIGTERM`. Verify shutdown behavior on both images.

### 3.4. Build Cache and Layers

CNB manages build/launch layers via input tracking, metadata, and the caching lifecycle. Docker/BuildKit manages caching via instruction graphs, image stages, and cache mounts. A Dockerfile can leverage Spring Boot layered JARs to `COPY` into multiple layers; conversely, Buildpacks cannot cache effectively if CI runners discard cache volumes.

**Build speed and image size must be measured**, not inferred from “has a Dockerfile” or “uses Buildpacks”. Rebuilding one Java source class differs greatly from updating base OS packages, changing lockfiles, or swapping the runtime JDK.

### 3.5. Rebasing When the OS Has Vulnerabilities

CNB supports **rebase**: swapping run-image layers of an application image with newer base layers when metadata/stack/platform are **compatible**, without rebuilding application layers. This can be an operational advantage when OS runtime packages receive CVEs.

Yet rebase **does not upgrade Maven dependencies, buildpack-contributed JVM layers, business code, or native libraries inside app layers**; it must not be treated as a substitute for all rebuilds. It requires rebaser tooling, registry access, compatibility, and regression tests. Dockerfiles normally bump the `FROM` digest and rebuild/test; that workflow is straightforward, though potentially slower in certain scenarios.

## 4. Comprehensive Comparison Matrix

| Requirement | Cloud Native Buildpacks | Dockerfile |
| --- | --- | --- |
| Standard Spring Boot service, few exceptions | Minimal per-service config | Needs a Dockerfile or shared template |
| Java runtime | Builder/buildpacks/`BP_JVM_VERSION` | Base image or manually copied JRE |
| Native/OS packages | Custom buildpack/run image/extension | `RUN` install in appropriate stage |
| ENTRYPOINT/launch hooks | Relies on CNB launcher and buildpack metadata | Direct control over `ENTRYPOINT`/`CMD` |
| User and permissions | Depends on builder/run policy; must inspect | Explicit `USER`/`COPY --chown` |
| Cache | CNB layers, `buildCache`/`launchCache` | Dockerfile ordering, BuildKit cache mounts |
| OS security updates | Can rebase when compatible | Update base image and rebuild |
| SBOM | CNB ecosystem includes metadata/SBOM per buildpack | Use Docker/OCI tooling or scanners |
| Source provenance | Builder/buildpack versions and lifecycle | Dockerfile, base digest, and build logs |
| Image size | Depends on run image/JVM/layers | Depends on base/multi-stage/packages |
| CI | Spring Boot `build-image` requires Docker daemon | Docker/BuildKit or build service |
| Proxy/offline | Mirror builder, run image, JRE, buildpack artifacts | Mirror base image, Maven/OS repositories |
| Runtime JVM options | `BPL_*`/`JAVA_TOOL_OPTIONS` per buildpack | Java env options/`ENTRYPOINT` config |
| Multi-platform | Builder/run/buildpacks supporting platform | Buildx/`--platform`, builder/emulation |
| Platform governance | Centrally approved builder/run image helpful | Central Dockerfile templates/base-image policy |
| Exception maintenance cost | May require developing custom buildpacks | Easy to add a few instructions, requires ongoing maintenance |
| Security | Not automatically secure just by using CNB | Not automatically secure just by having a Dockerfile |

**Do not equate** “customizable” with “maintenance-free”: greater flexibility means owning more decisions around runtime OS, package managers, security, and update workflows.

## 5. Spring Boot 4.1.2 Example Used for Both Approaches

We build an HTTP service with easily verifiable output. Use the **exact same source** to compare a Buildpacks image and a Dockerfile image.

### 5.1. Directory Structure

~~~text
catalog-svc/
├── pom.xml
├── Dockerfile
├── .dockerignore
├── src/
│   ├── main/
│   │   ├── java/dev/example/catalog/
│   │   │   ├── CatalogApplication.java
│   │   │   └── CatalogMessage.java
│   │   └── resources/application.properties
│   └── test/
│       └── java/dev/example/catalog/CatalogMessageTest.java
└── target/
~~~

### 5.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>catalog-svc</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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
                        <name>catalog-svc:cnb</name>
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

**Explanation:**

- Starter parent manages dependency versions and the `repackage` goal for the executable JAR; Java target is 17.
- `spring-boot-starter-webmvc` provides dependencies for Spring MVC and the embedded servlet server.
- Image name is `catalog-svc:cnb` so it does not overwrite Dockerfile's `catalog-svc:docker`.
- `BP_JVM_VERSION=17` is a **builder environment** input for the Paketo Java buildpack; it does not change `java.version` in the Maven compiler.
- Builder is not pinned in the demo POM so it uses the default builder selected by Spring Boot 4.1.2. **In real releases, control builder/run image tags and digests**; `latest` is not a reproducibility policy.

### 5.3. `CatalogMessage.java`

File `src/main/java/dev/example/catalog/CatalogMessage.java`:

~~~java
package dev.example.catalog;

public final class CatalogMessage {
    private CatalogMessage() {
    }

    public static String value() {
        return "IMAGE_OK";
    }
}
~~~

### 5.4. `CatalogApplication.java`

File `src/main/java/dev/example/catalog/CatalogApplication.java`:

~~~java
package dev.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @GetMapping("/healthz")
    public String healthz() {
        return CatalogMessage.value();
    }
}
~~~

The demo's `/healthz` endpoint returns a fixed body. **This is not a complete production readiness check**: real applications should check dependency health or use Actuator with appropriate security policies.

### 5.5. `application.properties`

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=catalog-svc
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.banner-mode=off
~~~

Keep port **8080** inside both images. This must match before comparing runtime behavior.

### 5.6. `CatalogMessageTest.java`

File `src/test/java/dev/example/catalog/CatalogMessageTest.java`:

~~~java
package dev.example.catalog;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CatalogMessageTest {
    @Test
    void returnsStableOutput() {
        assertEquals("IMAGE_OK", CatalogMessage.value());
    }
}
~~~

The JUnit test checks logic, **not** whether the image starts properly. We will add HTTP smoke tests after building both images.

## 6. Cloud Native Buildpacks: Building with the Spring Boot Maven Plugin

### 6.1. Prerequisites

For the **`mvn spring-boot:build-image`** command in this lesson:

- Java 17 and compatible Maven or project Wrapper.
- A Docker daemon or Docker API endpoint reachable by the Maven Plugin.
- Proper Docker socket/context permissions, network policy, and image pull permissions.
- Access to builder/run images, registries, and JRE artifacts, or configured mirrors/proxies.
- Sufficient disk/cache volumes and builder memory to execute the CNB lifecycle.
- CI policies permitting temporary containers/volumes and cleanup.

Check:

~~~bash
java -version
mvn -version
docker info
~~~

Having the Docker CLI **does not mean the Docker daemon is working**. If `docker info` fails to connect, fix context/permissions/daemon per system policy rather than opening global Docker socket permissions.

### 6.2. Creating the Buildpacks Image

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp spring-boot:build-image
~~~

The `spring-boot:build-image` goal is appropriate when invoked directly; it can fork the lifecycle to ensure packaging occurs. When binding image creation to a Maven `<execution>` in the lifecycle, Spring Boot provides `build-image-no-fork`; avoid binding `build-image` and triggering unexpected duplicate builds.

Expected image per configuration:

~~~text
catalog-svc:cnb
~~~

**Local image creation differs from registry pushing.** The command above creates an image in the Docker daemon the plugin connects to, unless publish is configured. Do not treat an image tag as proof of an immutable digest in a registry.

### 6.3. Inspecting the Image

~~~bash
docker image inspect catalog-svc:cnb
docker history catalog-svc:cnb
~~~

To view entrypoint/user:

~~~bash
docker image inspect catalog-svc:cnb \
  --format 'USER={{.Config.User}} ENTRYPOINT={{json .Config.Entrypoint}}'
~~~

A CNB image may have the **CNB launcher** as its entrypoint instead of `java -jar /app/app.jar`. That is a valid architectural difference. Inspect process metadata and run the actual app rather than applying Dockerfile entrypoint assumptions to Buildpacks images.

### 6.4. Customizing Builder/Run Image

The Spring Boot Maven Plugin lets you configure builder/run images:

~~~xml
<!-- Fragment inside <configuration> of spring-boot-maven-plugin -->
<image>
    <name>catalog-svc:cnb</name>
    <builder>registry.example.invalid/platform/java-builder:approved</builder>
    <runImage>registry.example.invalid/platform/java-run:approved</runImage>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
    </env>
</image>
~~~

**This is an illustrative fragment only**: names in `example.invalid` are not real registry images; do not copy and run verbatim. Real builder/run images must be mutually compatible with the lifecycle, architecture, stack/run-image requirements, and organizational policy.

Other Maven Plugin options include `imagePlatform`, `pullPolicy`, `createdDate`, `buildpacks`, `buildCache`, `launchCache`, `buildWorkspace`, Docker connection, and publish/registry configuration. Not every builder supports every Paketo variable name, so consult documentation for your exact builder.

**On pinning:** per Spring Boot Maven Plugin 4.1.2 docs, the default builder may reference a `latest` Paketo image and `pullPolicy` defaults to `ALWAYS`. For production releases, manage approved builder/run image digests or versions along with an update schedule. Pinning once does not keep an image safe forever: update and scan for CVEs regularly.

## 7. Multi-Stage Dockerfile: Building the Same Application

### 7.1. Complete `Dockerfile`

~~~dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml ./pom.xml
COPY src ./src
RUN mvn -B -ntp clean verify

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build --chown=10001:10001 \
    /workspace/target/catalog-svc-1.0.0.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Reading each instruction:**

1. `FROM maven:3.9-eclipse-temurin-17 AS build` provides Maven and JDK 17 for compile/test/package, excluded from the final image.
2. `COPY pom.xml` and `COPY src` bring source into the build stage. In multi-module Maven builds, also `COPY` parent POMs/modules and build extensions.
3. `RUN mvn -B -ntp clean verify` runs unit tests and creates the executable JAR. If tests fail, the Docker build fails; never skip tests accidentally.
4. `FROM eclipse-temurin:17-jre` starts the runtime stage needing only a JRE; tags are examples, pin digests in production.
5. `COPY --from=build` extracts only the executable Boot JAR without carrying source code, Maven repo, or compiler into runtime.
6. `USER 10001:10001` avoids running as root. Check where the app needs write access, e.g. `/tmp`, log directories, mounted volumes.
7. `EXPOSE 8080` is metadata only; publish host ports via `docker run -p`.
8. Exec-form `ENTRYPOINT ["java", "-jar", "/app/app.jar"]` delivers signals more directly than a shell-entrypoint parent; the app still needs proper graceful shutdown handling.

This Dockerfile is designed for learning and verification. For production, separate dependency resolution caching, use BuildKit cache mounts, update base images, run security scans, and pin digests per CI policy.

### 7.2. `.dockerignore`

~~~text
.git
.idea
.vscode
target
build
*.log
.DS_Store
~~~

Because the multi-stage Dockerfile **builds the JAR from source itself**, do not exclude `pom.xml` or `src` from the context. `target` should be excluded so stale local artifacts are not copied unintentionally. If using a different Dockerfile that `COPY`s a prebuilt JAR, adjust `.dockerignore` accordingly so the required artifact is not excluded.

### 7.3. Building the Image

~~~bash
docker build -t catalog-svc:docker .
~~~

The image is built in the local Docker daemon. You can verify:

~~~bash
docker image inspect catalog-svc:docker
docker history catalog-svc:docker
~~~

Not every Docker host runs the same BuildKit/Buildx version; multi-stage builds used here are broadly supported, though advanced caching features require a compatible builder.

### 7.4. Customizing OS Packages

A Dockerfile shines when you genuinely need OS packages installed:

~~~dockerfile
# Fragment: insert after runtime FROM, before non-root USER.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
~~~

**This is not required for the example**, as the base image may already include CA certificates. Use the package manager matching the distro; minimal/distroless images may **lack a shell and package manager**, requiring filesystem preparation in an earlier build stage.

Managing package version pins, repositories, and vulnerability updates is the Dockerfile pipeline's responsibility. Buildpacks can also provide custom OS libraries via custom run images/buildpacks/extensions, but that requires capacity to manage the corresponding builder/run image lifecycle.

## 8. Running Side by Side and Verifying the Same API

Run both images on different host ports:

~~~bash
docker run -d --name catalog-cnb \
  -p 18080:8080 catalog-svc:cnb

docker run -d --name catalog-docker \
  -p 18081:8080 catalog-svc:docker
~~~

Once both applications are ready (CI should wait with a bounded readiness loop/timeout):

~~~bash
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18081/healthz
~~~

**Exact HTTP response body of each command:**

~~~text
IMAGE_OK
~~~

This is the **HTTP response body**, not `docker run` stdout. The Buildpacks image has a different launcher/logs from the Dockerfile image while satisfying the exact same functional contract. Do not expect startup logs to match character-for-character.

Inspect further:

~~~bash
docker ps
docker logs catalog-cnb
docker logs catalog-docker
docker image inspect catalog-svc:cnb
docker image inspect catalog-svc:docker
~~~

Clean up the two containers:

~~~bash
docker stop catalog-cnb catalog-docker
docker rm catalog-cnb catalog-docker
~~~

**Do not expect the two images to share the same SHA-256/digest.** Base/run images, JRE providers, labels, entrypoints, timestamps, and filesystem layers differ; identical endpoints demonstrate partial **functional equivalence**, not byte-for-byte identity.

## 9. Build-Time and Runtime Options: `BP_*` vs `BPL_*`

Paketo Java Buildpack provides stage-specific customization mechanisms:

| Variable or Group | Stage | Meaning |
| --- | --- | --- |
| `BP_JVM_VERSION` | Build time | Selects major Java runtime baked into image |
| `BPL_JVM_THREAD_COUNT` | Runtime | Parameter for the buildpack JVM memory calculator |
| `BPL_JVM_HEAD_ROOM` | Runtime | Headroom for buildpack JVM sizing |
| `JAVA_TOOL_OPTIONS` | Java runtime | Adds JVM flags via standard Java/toolchain mechanism |
| `SPRING_PROFILES_ACTIVE` | Spring Boot runtime | Selects application configuration profile |
| `JDK_JAVA_OPTIONS` | Java 17 launcher | Passes Java launcher/VM options, handy in Dockerfile images |
| Other `BP_*` | Build time | Meaningful only if consumed by the active buildpack |
| Other `BPL_*` | Runtime | Meaningful only if supported by runtime helpers/buildpacks |

### Buildpacks Runtime Example

~~~bash
docker run --rm -p 18082:8080 \
  --memory=512m \
  -e BPL_JVM_THREAD_COUNT=100 \
  -e JAVA_TOOL_OPTIONS='-Ddemo.flag=from-cnb' \
  catalog-svc:cnb
~~~

**Do not pass `BP_JVM_VERSION` at runtime expecting to swap the JRE already baked into the image.** It is a Paketo build-time input; runtime JRE version must be chosen at build time and verified via SBOM/runtime diagnostics.

The buildpack JVM memory calculator can use cgroup limits, thread count, class count, headroom, etc. to compute JVM flags; do not assume the heap computed by CNB equals that of a Dockerfile image. `BPL_*` variables are not mandatory across all CNB builders.

### Dockerfile Runtime Example

~~~bash
docker run --rm -p 18083:8080 \
  --memory=512m \
  -e JDK_JAVA_OPTIONS='-Xms64m -Xmx256m -Ddemo.flag=from-docker' \
  catalog-svc:docker
~~~

The Java 17 launcher reads `JDK_JAVA_OPTIONS` without needing Docker shell expansion. `JAVA_OPTS` is **not** a standard environment variable read directly by the Java launcher; it works only if the image runs a script/launcher written to use it.

**Important:** `-Xmx` placed **after `-jar`** in a Docker `CMD` is not a JVM option—it becomes an application argument. When customizing a Dockerfile, put JVM flags before `-jar` or use Java-supported env vars. The CNB launcher follows builder-specific conventions; do not replace it with raw `java -jar` without understanding its launch hooks.

## 10. Image Size, Cache, and Speed: Unbiased Evaluation

### 10.1. Size

Do not claim CNB always produces smaller images than Dockerfiles or vice versa. Size depends on:

- Run image/base OS (distro, glibc, CA/SSL packages).
- JDK vs JRE; Java vendor and runtime modules.
- Library dependencies and packaged files/resources.
- Custom native/OS packages and layer ordering.
- Registry compression, architecture, and image manifest.

Inspect:

~~~bash
docker image ls catalog-svc
docker history --no-trunc catalog-svc:cnb
docker history --no-trunc catalog-svc:docker
~~~

**Do not compare solely by local `SIZE`:** shared layers, compressed registry size, and multi-architecture manifests make measurements differ. Pick metrics aligned with your organization's cost/speed goals: transfer bytes, cold pull time, image footprint, and storage.

### 10.2. Cache

**CNB:** lifecycle/cache restore/export can reuse JRE/app/dependency layers. Spring Boot Maven Plugin provides `buildCache` and `launchCache`; default caches are usually Docker named volumes derived from image name. Ephemeral CI can lose volumes, while changing image names/tags frequently reduces caching efficiency.

**Dockerfile:** BuildKit uses instruction caching. For instance, `COPY src` followed by `RUN mvn ...` invalidates the Maven stage whenever source changes. Use cache mounts for `~/.m2`, remote caches, and separate build artifacts from the runtime stage to optimize. Using a Dockerfile does not mean always re-downloading every dependency.

**Measure across two workloads:** (a) no-change rebuild and (b) single Java class edit. Keep **CI runner resources, network, registry, JDK target, and source identical**; record build durations, cache hits, and digests. Never use cached artifacts to claim you have proven rebuild reproducibility.

### 10.3. Reproducibility

Both a `latest` builder image tag and a Dockerfile `FROM ...:latest` can resolve to different digests days later. When you need to rebuild an exact release:

- Pin source commit and dependency versions/locks.
- Pin/audit Maven plugins, CNB builder/run images, or Docker base image digests.
- Control generated metadata such as `build.time`, archive timestamps, and toolchains.
- Archive SBOM/provenance alongside the image digest.
- Run two independent builds when true reproducibility QA is required.

**A reproducible artifact is not automatically secure:** two byte-identical images can still share the same vulnerability; scanning and patching remain mandatory.

## 11. Security, SBOM, and CVE Patching

### 11.1. Shared Risks

Both approaches face:

1. CVEs in OS packages, JRE, native libraries, and Java dependencies.
2. Mutable image tags changing without pinned digests.
3. Registry credentials/build secrets leaking into layers, build logs, or environment variables.
4. Over-privileged CI runners (e.g. unrestricted Docker socket access).
5. Application processes running as root, lacking network restrictions, or having excessive writable filesystems.
6. Missing provenance, signatures, SBOMs, or license checks.
7. Published images lacking a base-runtime upgrade workflow when CVEs emerge.

**No tool solves all seven risks merely by producing an image.**

### 11.2. Buildpacks Helps Centralize Governance

A platform team can maintain a curated set of approved builder/run images, JVM vendors, and buildpack versions. Standard Spring Boot services are packaged uniformly, reducing copied-and-forgotten Dockerfiles across repositories.

The CNB ecosystem supports buildpack-generated SBOM/BOMs and run-image rebasing when applicable. However, **SBOM completeness depends on the specific builder/buildpacks/tooling**. Before declaring compliance, validate actual artifacts, scanners, and provenance records.

### 11.3. Dockerfile Helps Review Every Instruction

Dockerfiles show `FROM`, `RUN`, `COPY`, `USER`, and entrypoints explicitly; platform teams can enforce policy-as-code/linting. Yet patterns like `RUN curl ... | sh` without checksum pinning or unpinned apt packages make that flexibility harder to govern in the supply chain.

### 11.4. Provenance Suggestion

A release should capture information at this level:

~~~text
source.commit       = <Git SHA>
image.reference     = registry.example.com/team/catalog-svc:1.0.0
image.digest        = sha256:<actual digest after build/push>
java.runtime        = <vendor/version>
os.base.digest      = <run image or base image>
builder.toolchain   = <CNB lifecycle/buildpacks or Docker/BuildKit>
sbom.reference      = <SBOM artifact>
scan.result         = <policy result>
ci.run              = <execution record>
~~~

This is a **field template**, not a SHA or attestation generated in this lesson. Record the **real digest**, never relying solely on a tag as identity. CI run IDs/creation timestamps can live outside the image to avoid embedding volatile metadata into the artifact.

## 12. CI Infrastructure: Docker Daemon, Proxy, Registry, and Cache

### 12.1. With Spring Boot Maven `build-image`

- The plugin communicates with a Docker daemon/API. Having the Docker CLI installed does not guarantee the daemon/socket is usable.
- Builder/run images must be pullable; private registries need proper credentials.
- The builder must reach JRE/buildpack download sources or mirrors. Proxy/CA differences across **host**, **Docker daemon**, and **builder container** can trigger unexpected failures.
- `pullPolicy` per Spring Boot Maven Plugin 4.1.2 docs defaults to `ALWAYS`; watch out when builder tags move to new digests.
- Cache volumes/workspaces can consume substantial disk, especially with many image names.
- `imagePlatform` picks a single builder-supported target platform; it does not automatically produce a multi-arch manifest list.
- Docker host/TLS, registry publish, and build-time env/bindings can be configured in the Maven Plugin, though secrets must never be hardcoded in the POM.

**Distinction:** `spring-boot:build-image` requires a Docker daemon; **Cloud Native Buildpacks in general do not force every developer to run a local daemon**. The CNB lifecycle can run via `pack`, `kpack`, or an organization-managed platform/build service. Infrastructure requirements depend on the integration used.

### 12.2. With Dockerfile/BuildKit

- Requires a Docker/BuildKit builder or appropriate remote builder service.
- Multi-stage Maven builds need Maven repositories/proxies/auth inside the build stage.
- Remote caching and Buildx multi-platform builds are supported when builder, emulation, and base images allow.
- If a Dockerfile `COPY`s a prebuilt JAR, CI must guarantee that JAR came from the exact commit with tests executed; never consume stale artifacts.
- Build secrets should use mechanisms supported by the build service, never copied into the runtime image.
- Rootless/restricted CI may prohibit standard Docker daemons; both approaches need an approved builder solution.

### 12.3. Multi-Platform and Native Dependencies

Java bytecode is portable across amd64/arm64, yet the JRE, OS packages, and JNI/native image dependencies are architecture-specific. CNB requires builder/run images/buildpacks supporting the target platform. Docker Buildx supports multiple platforms where builders, emulation, and base images permit.

**Do not assume a `linux/amd64` image can deploy directly to `linux/arm64`.** For multi-arch deployments, build and publish proper image variants/manifest indexes, then test on the real target architectures.

## 13. Selection Table by Operational Requirement

| Context | Initial Preference | Conditions to Verify |
| --- | --- | --- |
| Many pure-Java REST services, few native deps | Buildpacks | Approved builder/run image, CI, and security policy |
| App needs OS fonts or native imaging libraries | Dockerfile or custom CNB | Package manager, run-image compatibility, CVE policy |
| Want fleet-wide runtime OS updates | Buildpacks favored when rebase fits | Rebase tooling, registry permissions, regression QA |
| Must specify detailed entrypoint/`USER`/filesystem | Dockerfile | Process signals, permissions, container probes |
| Want minimal per-repo boilerplate | Buildpacks | Platform team maintaining builder/builder upgrades |
| Strong existing Dockerfile templates/BuildKit setup | Dockerfile may fit well | Cache, base digest, scanning still standardized |
| Ephemeral CI does not persist Docker volumes | Benchmark required | CNB cache vs BuildKit remote caches |
| Compliance mandates SBOM/attestation | Either can work | Verify tools/metadata with real digests |
| Need both amd64 and arm64 | Either can work | Builder/run platforms or Buildx manifests |
| CI forbids daemon sockets | Depends on build service | Alternative CNB platform or remote BuildKit |
| Need ultra-small image size | Do not guess | Measure with equal Java, OS features, and security requirements |
| Custom OS package needed by only a couple services | Depends on platform maturity | Cost of custom buildpack vs Dockerfile |
| No team maintaining Dockerfiles | Buildpacks usually easier to start | Builder supply chain still needs an owner |
| Platform computes runtime memory automatically | Paketo Buildpacks can help | `BPL_*` knobs, actual cgroup/memory behavior |

**Practical recommendation:** if most workloads are standard Java/Spring Boot services and a platform team maintains a solid CNB builder, pick Buildpacks as the **default path**; allow Dockerfiles as an **exception path** when OS packages, entrypoints, or compliance require them. Both must pass the exact same QA/security gates.

## 14. Non-Functional Operational Testing Beyond HTTP

### 14.1. Identity and Metadata

~~~bash
docker image inspect catalog-svc:cnb \
  --format 'ID={{.Id}} USER={{.Config.User}}'
docker image inspect catalog-svc:docker \
  --format 'ID={{.Id}} USER={{.Config.User}}'
~~~

Inspect architecture, base image labels, user, entrypoint, env, and layers. **Do not force both images to have identical users/entrypoints**; check each against its own policy. The Buildpacks image can use the CNB launcher while the Dockerfile image uses a Java exec `ENTRYPOINT`.

### 14.2. Memory and JVM Runtime

~~~bash
docker run --rm --memory=512m \
  -p 18084:8080 catalog-svc:cnb
~~~

This is a **container memory limit**, not equivalent to JVM `-Xmx512m`. Java also uses native memory, metaspace, thread stacks, direct buffers, and code cache. Measure heap/GC/native memory under representative load instead of trusting startup success alone.

### 14.3. Shutdown

~~~bash
docker run -d --name catalog-stop \
  -p 18085:8080 catalog-svc:docker
docker stop --time 30 catalog-stop
docker logs catalog-stop
docker rm catalog-stop
~~~

Docker sends a stop signal per runtime config and may force-kill after the grace period. Spring Boot supports graceful shutdown, yet you must test with live requests/background jobs rather than assuming `server.shutdown=graceful` guarantees every request completes.

### 14.4. Security Hardening

Verify: non-root execution, read-only root filesystem where appropriate, writable mounts, Linux capabilities, network policies, secret injection, image signing, vulnerability scanning, SBOM, provenance, update SLAs, and rollback. **Never expose the Docker daemon socket or build credentials inside a runtime container.**

## 15. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `spring-boot:build-image` cannot reach Docker | Invalid daemon/socket/context/TLS | `docker info`, plugin Docker connection |
| CNB fails to detect app | Wrong JAR/source format or builder buildpacks | Maven `package`, lifecycle logs, selected builder |
| CNB builder changes across builds | Upstream `latest`/`pullPolicy` pulled new image | Pin approved versions/digests, release policy |
| CNB lacks required native OS library | Run image missing binary/lib | Custom run image/buildpack or Dockerfile |
| `BP_JVM_VERSION` has no effect | Builder lacks Paketo component or wrong input | Check builder/buildpacks, logs, runtime Java |
| Java class version exception | Compiler target and runtime JRE mismatch | Align Java 17 target/run image |
| Docker `COPY` cannot find JAR | Wrong multi-stage path or build produced no JAR | Check `target` in build stage |
| Final Docker image contains full Maven/JDK | Multi-stage not used properly | Separate build and runtime stages |
| Docker build slow on every source edit | Cache invalidated at `COPY src` | Optimize instruction order, Maven/BuildKit cache |
| CNB build slow in CI yet fast locally | Non-persistent cache volumes | Review cache policy/volumes, benchmark |
| CNB image fails when overriding entrypoint | Bypassed CNB launcher/hooks | Keep default process or understand launch metadata |
| `BPL_*` has no effect | Builder does not support that knob | Consult Paketo docs/runtime buildpack |
| App OOMs even with small heap | JVM native memory and container limits | Measure actual heap/native/cgroup usage |
| Docker runtime app ignores `SIGTERM` | Shell-form entrypoint holding PID 1 | Use exec `ENTRYPOINT` and test stop |
| CNB rebase fails | Incompatible run image/metadata/platform | Check rebaser support and stack policy |
| Both images have different digests | Base/JRE/launcher/layer metadata differ | Normal; compare functionality and compliance |
| Dockerfile image scan fails | Base/OS packages or dependencies have CVEs | Update digests/packages, re-scan/re-test |
| CI cannot push to registry | Credentials/namespace/permissions | Verify push step independently |
| Image tag points to wrong build | Mutable tag or pipeline race | Record real digest and deploy by digest |
| App in container does not open port | `server.port` and `docker run -p` mismatch | Check container listen port and port mapping |

**Debugging order:** source and JDK → JAR packaging → CNB builder/buildpacks or Dockerfile stage → OCI metadata → container runtime → registry/provenance. Do not edit Spring business code when the fault lies in the builder/run image.

## 16. Pre-Release Quality Gates

**A. Source/JAR**

- [ ] Git commit identified, Java version and Maven plugins controlled.
- [ ] Spring Boot unit tests discovered and passing.
- [ ] Executable JAR built from the exact source/commit.
- [ ] Dependency versions and SBOM provenance consistent.

**B. Container Image**

- [ ] CNB image uses an approved builder/run image.
- [ ] Dockerfile image uses approved base image digests and proper multi-stage setup.
- [ ] Image architecture, user, entrypoint, env, and layers inspected.
- [ ] Images scanned and compliant with OS/JVM/dependency vulnerability policies.
- [ ] Real image digest recorded upon publish; never rely solely on mutable tags.

**C. Runtime**

- [ ] Both images tested on separate host ports.
- [ ] HTTP `GET /healthz` on both images returns **200 and exact body `IMAGE_OK`**.
- [ ] JVM memory/GC/thread/native memory measured against container cgroup limits.
- [ ] Stop/graceful shutdown and logs verified.
- [ ] Zero secrets or Docker sockets inside runtime images.
- [ ] Non-root, writable directories, and security context meet requirements.

**D. Operations**

- [ ] Clear owner assigned for builder/run images or Dockerfile/base images.
- [ ] Cache strategy fits real runners; not evaluated solely on a laptop.
- [ ] Proxy/CA/registry/credentials tested in CI and production.
- [ ] CVE patching schedule and digest-based rollout/rollback defined.
- [ ] SBOM/provenance/signing policies enforced on both approaches.
- [ ] If using rebase, technical support verified and regression QA run.
- [ ] If multi-arch is required, target architectures and manifest indexes tested.

**An image returning HTTP 200 is not enough to declare it production-ready.** It proves demo functionality; performance, security, patching, and observability still require dedicated verification.

## 17. Scenario Exercises with Answers

**1. A pure-REST Spring Boot service has no special OS dependencies, and the team maintains an approved CNB builder. Which option should be tried first?**

Buildpacks is a sensible starting point due to minimal Dockerfile boilerplate and easy alignment with shared builder/run image policies. Then verify CI cache, Java runtime, SBOM, and security posture.

**2. A service needs OS fonts and a custom-built native binary. Is CNB completely ruled out?**

No; custom buildpacks/run images/extensions can handle it. However, if the platform lacks that capability, a Dockerfile usually provides a more explicit way to install/copy the binary. Weigh long-term ownership costs.

**3. Does `BP_JVM_VERSION=17` change `-Xmx` while the app is running?**

No. With Paketo, that is build-time JVM version selection. Runtime sizing uses `BPL_*` knobs or JVM options per buildpack.

**4. Does `mvn spring-boot:build-image` automatically push the image to a registry?**

Not by default in the sample workflow. Building creates the image via the Docker daemon; publishing is a separate step/configuration, and you should verify the registry digest.

**5. Why do CNB and Dockerfile images have different hashes yet both return `IMAGE_OK`?**

Because base OS, JRE vendor/patch, launcher, labels, file layout, and layers differ. Functional equivalence is different from byte-identical OCI artifacts.

**6. Can CNB rebase update all Java dependencies declared in `pom.xml`?**

No. Rebase swaps compatible run-image layers; it does not alter app artifacts and does not upgrade app dependencies or buildpack-contributed JRE layers.

**7. Can a multi-stage Dockerfile avoid shipping Maven/JDK in the final image?**

Yes. Use a Maven/JDK stage to build the JAR, then copy only the JAR into a JRE runtime stage. This prevents shipping build tools.

**8. CI forbids running a Docker daemon on runners. Is CNB useless?**

No. Spring Boot Maven `build-image` needs a Docker daemon connection; the broader CNB ecosystem has alternative build platforms. Dockerfiles also have remote BuildKit/build services. Pick a solution permitted by your organization.

**9. Is it an error if a Buildpacks image has an `ENTRYPOINT` other than `java -jar`?**

No. The CNB launcher and launch process metadata are part of how Buildpacks work. Test startup/HTTP and inspect metadata per policy.

**10. Why shouldn't you choose solely based on image size?**

Because size depends on JRE, OS libraries, architecture, compression, shared layers, and security features. Measure with an equivalent feature set and other operational metrics.

**11. Does Buildpacks eliminate the need for anyone to maintain CVE patches?**

No. Builder/run images, buildpacks, and dependencies still require owners, upgrade schedules, scanning, and rollback, just like base images/Dockerfile pipelines.

**12. Should an organization combine both approaches?**

Yes. Use Buildpacks as the common path for standard Java services; use Dockerfiles or custom builders for specialized workloads. Both must pass the same quality/security gates.

## 18. Design Decision Checklist

- [ ] Identified custom OS package/native dependency requirements.
- [ ] Identified required control over filesystem/`ENTRYPOINT`/processes.
- [ ] Defined Java runtime vendor/version/patch policy.
- [ ] Checked approved builder/run images or Docker base digests.
- [ ] Distinguished build-time `BP_*` from runtime `BPL_*`.
- [ ] Measured caching on real CI, not guessed.
- [ ] Verified proxy, certificates, and network downloads during builds.
- [ ] Verified registry auth, image publishing, and digests.
- [ ] Accounted for CVE patching, SBOM, and license/provenance scanning costs.
- [ ] Verified non-root/security context and graceful shutdown.
- [ ] Verified resource limits, heap/native memory, and JVM startup.
- [ ] Verified host/OCI architecture compatibility.
- [ ] Defined rollback/rebuild/rebase strategy when base runtime changes.
- [ ] Ran functional smoke tests against real images.
- [ ] Assigned ownership for builder/run images or Dockerfile templates.
- [ ] Avoided mutable `latest` as the sole release identity.
- [ ] Documented concrete rationale for choosing Buildpacks, Dockerfile, or both.

**Conclusion:** **Buildpacks** package Spring Boot by convention and reduce repetitive configuration, which is especially valuable when a platform team maintains shared builder/run images. **Dockerfile** fits when explicit step-by-step control, bespoke OS packages, and custom entrypoints/filesystems are required. Neither wins universally: evaluate against customizability, CI/operational fit, caching, security, upgrades, and empirical results on the same application.

## 19. Official Documentation

1. [Spring Boot Maven Plugin 4.1.2 — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
2. [Spring Boot Gradle Plugin — OCI Image Packaging](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-images.html)
3. [Cloud Native Buildpacks — Documentation](https://buildpacks.io/docs/)
4. [Cloud Native Buildpacks — Platform Specification / Rebase](https://github.com/buildpacks/spec/blob/main/platform.md)
5. [Cloud Native Buildpacks — Lifecycle](https://github.com/buildpacks/lifecycle)
6. [Paketo — Java Buildpack and JVM Configuration](https://paketo.io/docs/buildpacks/language-family-buildpacks/java/)
7. [Docker — Dockerfile Reference](https://docs.docker.com/reference/dockerfile/)
8. [Docker — Build Best Practices](https://docs.docker.com/build/building/best-practices/)
9. [Docker — Multi-platform Builds](https://docs.docker.com/build/building/multi-platform/)
10. [Spring Boot — Dockerfiles for Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
11. [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)
12. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)