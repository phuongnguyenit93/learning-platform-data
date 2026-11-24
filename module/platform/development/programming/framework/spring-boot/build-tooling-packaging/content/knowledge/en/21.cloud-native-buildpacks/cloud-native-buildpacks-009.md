# Distinguishing Image Build-Time Environment Variables from Runtime Environment Variables

## Lesson Objectives

**Cloud Native Buildpacks (CNB)** helps package a Spring Boot application into an OCI image without writing a Dockerfile manually. You still need to configure both build and runtime, yet a very common mistake is treating an **environment variable supplied at image build time** as though it will automatically exist in the **running container**.

Consider four distinct examples:

- `BP_JVM_VERSION=17`: Paketo Java Buildpack reads this value **when building the image** to select which Java runtime to include in the image.
- `SPRING_PROFILES_ACTIVE=staging`: Spring Boot reads this at **runtime**, when the application process starts inside a container.
- `BPL_JVM_THREAD_COUNT=100`: Paketo launch components, if present, read this at **runtime** to tune assumptions for the JVM memory calculator; it does not edit Java source.
- `BPE_DEFAULT_APP_LABEL=from-image`: supplied at **build time** so the Paketo Environment Variables buildpack intentionally **embeds a launch default** into the image. This is an explicit exception by design, not behavior shared by every build-time env var.

Because variables all look like `NAME=value`, learners easily confuse `bootBuildImage.environment`, `spring-boot:build-image` `image.env`, and `pack build --env` with `docker run -e`, Docker Compose `environment`, or Kubernetes Pod `env`. They are **not equivalent**.

After this lesson, you will be able to:

1. Distinguish **host/CI job**, **CNB builder**, **OCI image launch environment**, **container runtime**, and **Spring Environment**.
2. Understand variable groups **`BP_*`, `BPL_*`, `BPE_*`**, JVM `JAVA_TOOL_OPTIONS`, and Spring `SPRING_PROFILES_ACTIVE`, `SERVER_PORT`, `APP_LABEL`.
3. Configure build-time env properly in **Gradle `bootBuildImage`**, **Maven `spring-boot:build-image`**, and **`pack build --env`**.
4. Write a Spring Boot Java 17+ application with an HTTP endpoint that safely inspects environment values.
5. Run multiple containers with different runtime configs from **the same image ID/digest** without rebuilding the image.
6. Know when a rebuild is genuinely required (Java version, buildpacks, native compilation, image-embedded defaults) and when only a new Pod/container is needed (profile, DB URL, feature flags).
7. Verify results via build logs, image identity, HTTP responses, and JVM/runtime diagnostics without exposing secrets.
8. Design a CI/CD workflow: **build once, scan/test, then promote the same image digest**, supplying environment-specific configs at deploy time.

**Example context:** Spring Boot **3.3.13**, Java **17**, Gradle **8.x** or compatible Maven, Docker/OCI, and **Paketo Java Buildpack**. The prefixes `BP_`, `BPL_`, and `BPE_` are **Paketo conventions**, not variable names supported by every CNB builder. Examples carry explicit prerequisites: a running Docker daemon, compatible builder, network, and matching plugin versions. Never report output as having been executed if it is only an illustrative prediction.

---

## 1. One Pipeline, Multiple Environment Spaces

### 1.1 Build → Image → Launch Diagram

```text
                Source code, pom.xml/build.gradle
                           |
                        Host / CI
             JAVA_HOME, DOCKER_HOST, CI_*
                           |
                       Maven/Gradle
                     or pack build CLI
                           |
                           v
                Cloud Native Buildpacks
               detect -> build -> export
            BP_JVM_VERSION=17  (BUILD)
                           |
                           v
                      OCI IMAGE
              Java runtime + app classes
           launch process + layers + metadata
           BPE_* can embed launch defaults
                           |
             +-------------+--------------+
             |                            |
             v                            v
     Container staging              Container production
     same image digest              same image digest
     profile=staging                profile=prod
     APP_LABEL=blue                 APP_LABEL=green
     BPL_THREAD_COUNT=50            BPL_THREAD_COUNT=100
             |                            |
             +-------------+--------------+
                           |
                           v
            CNB launcher / runtime components
                           |
                           v
                 Spring Boot process
                        /probe
```

An **image** contains filesystem layers, process types, buildpack-created launch env/config, and runtime libraries. A **container** is a running instance of that image with its own network/mounts/permissions/environment. Launching two containers with different environments **does not mutate the image**.

### 1.2 Four Configuration Zones

| Zone | Who Reads It? | Example Supply Mechanism | Propagates Automatically to Next Zone? |
| --- | --- | --- | --- |
| **Host shell/CI job** | Gradle, Maven, `pack` CLI, Docker client | Bash `export X=...`; PowerShell `$env:X=...`; CI job env | **Does not automatically** pass all vars to builder or runtime |
| **Buildpack environment** | CNB lifecycle and buildpacks | Gradle `bootBuildImage.environment`, Maven `image.env`, `pack build --env` | **Does not automatically** become container runtime env |
| **Image-embedded launch environment** | CNB launcher/profile scripts | Paketo `BPE_DEFAULT_*`/`BPE_APPEND_*`; launch layer env | **Intentionally** applied when the image runs |
| **Container runtime environment** | CNB launch components, JVM, Spring Boot | Docker `-e`, Compose service `environment`, Kubernetes `env` | Applies within **that process/container**, does not alter image |

Whenever you spot a variable in builder logs, ask: was it **passed to the builder**, **turned into an artifact effect**, or **stored as launch env**? Those three possibilities are distinct.

### 1.3 Variables Can Shape Image Bytes Without Being Stored Verbatim

`BP_JVM_VERSION=17` can cause the image to include a Java 17 runtime. When the container runs, Java is still 17 even if you do not see `BP_JVM_VERSION` in `docker image inspect .Config.Env`. The **build effect** was packaged; the **variable itself** does not necessarily live in the launch environment.

Conversely, `BPE_DEFAULT_APP_LABEL=from-image` explicitly asks the buildpack to create a **launch default**; it can continue affecting the container. Meanwhile, `SPRING_PROFILES_ACTIVE=prod` supplied at container startup only changes runtime configuration without recompiling Java classes.

### 1.4 Host Env Is Not Image Env

In Bash:

```bash
export SPRING_PROFILES_ACTIVE=staging
./gradlew bootBuildImage
```

This sets a variable in the **host Gradle process's** environment. Do not conclude that the CNB builder receives that variable, or that the resulting image will run with the `staging` Spring profile. A host variable reaches the builder only if a build mechanism/tool explicitly forwards it, and reaches runtime only if Docker/orchestrator or image launch metadata supplies it.

The same holds for Maven. `-Dspring.profiles.active=staging` for the Maven JVM or a plugin execution is not the same as `SPRING_PROFILES_ACTIVE` for the production application. If the build runs integration tests, a profile might influence the **test JVM**, yet that is still not the production container's launch environment.

## 2. Paketo Build-Time `BP_*` Convention

### 2.1 `BP_JVM_VERSION`

`BP_JVM_VERSION` is supported by Paketo Java buildpacks to select the Java version installed when **building the image**:

```text
BP_JVM_VERSION=17
```

A builder can install a JDK in the build phase and pack an appropriate JRE/runtime into the launch image. Spring Boot Maven/Gradle image plugins usually infer project Java compatibility and instruct the builder, yet setting `BP_JVM_VERSION` lets you override per Paketo's contract.

**Correct usage:**

```bash
pack build example/cnb-env-demo:0.0.1 \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env BP_JVM_VERSION=17
```

This is an example command when the executable JAR has been built by Gradle, the builder contains Paketo Java buildpacks, and the Docker daemon is running. If the builder does not support Java 17 or the tag changed, select a compatible real builder.

**Incorrect usage if trying to upgrade Java after building:**

```bash
docker run --rm \
  -e BP_JVM_VERSION=21 \
  example/cnb-env-demo:0.0.1
```

This only launches a container with an extra **runtime environment variable**; it **does not download, install, or swap the Java runtime** already baked into the OCI layers. To change the Java version in the image, build a new image with the corresponding build-time option, then check bytecode and behavioral compatibility.

### 2.2 Common `BP_*` Variables

| Variable | Paketo Purpose | When Used? |
| --- | --- | --- |
| `BP_JVM_VERSION` | Selects Java version | During image build |
| `BP_JVM_TYPE` | Selects JDK or JRE launch runtime per provider capabilities | During image build |
| `BP_JVM_JLINK_ENABLED` | Requests a `jlink` custom runtime if supported | During image build |
| `BP_NATIVE_IMAGE` | Selects native-image flow if supported by buildpack/builder | During image build |
| `BP_MAVEN_BUILD_ARGUMENTS` | Customizes Paketo Maven buildpack args **when building from source** | Builder receives source, not a prebuilt executable JAR |
| `BP_GRADLE_BUILD_ARGUMENTS` | Customizes Paketo Gradle buildpack args **when building from source** | Builder receives source, not a prebuilt executable JAR |
| `MAVEN_OPTS` | JVM options for the Maven process running inside the builder | Builder building Java source |
| `HTTP_PROXY`/`HTTPS_PROXY` | Network proxy when builder fetches dependencies/runtime | Builder/network; check launch separately |

**Crucial distinction:** Spring Boot plugin's `spring-boot:build-image` and `bootBuildImage` build/pass an **executable archive** to the CNB builder. Paketo Maven/Gradle buildpack build-argument variables generally have no effect in that flow because the builder receives only the JAR/WAR and does not run Maven/Gradle internally. Only when using `pack build --path .` with a **source directory** and a builder supporting Java source buildpacks do `BP_MAVEN_BUILD_ARGUMENTS`/`BP_GRADLE_BUILD_ARGUMENTS` affect the corresponding tooling.

### 2.3 `BP_*` Is Not a Universal CNB Standard

The CNB specification defines the lifecycle/buildpack/launch model, while **buildpack config variable names** are vendor-specific. `BP_JVM_VERSION` is a common Paketo contract; other builders may use different names or ignore it. Do not assume `--env BP_FOO=bar` has any effect unless a buildpack explicitly consumes `BP_FOO`.

Choose a builder matching the application, stack/run-image compatibility, Java requirements, and update policy. Whenever switching builders, review every configuration variable name in use.

## 3. Runtime `BPL_*` Convention

### 3.1 Paketo Memory Calculator

Paketo Java runtime components can read `BPL_*` variables at launch, for example:

- `BPL_JVM_HEAD_ROOM`: adjusts headroom memory reserve.
- `BPL_JVM_THREAD_COUNT`: expected JVM thread count used to estimate stack memory.
- `BPL_JVM_LOADED_CLASS_COUNT`: expected loaded class count.
- `BPL_JVM_CLASS_ADJUSTMENT`: adjusts the class estimate if supported by the component.

Container example:

```bash
docker run --rm -d \
  --name cnb-memory-lab \
  --memory 512m \
  -p 18082:8080 \
  -e BPL_JVM_THREAD_COUNT=100 \
  example/cnb-env-demo:0.0.1
```

If the Paketo launcher includes the Memory Calculator, `BPL_JVM_THREAD_COUNT` is read during **runtime startup** to compute `JAVA_TOOL_OPTIONS` or JVM flags. It does **not** modify Java classes inside the JAR, does not tune Tomcat's thread pool config, and is not a tool to upgrade Java 17 to 21.

Do not cite an exact heap size without measuring; results depend on cgroup memory limits, Metaspace, thread stacks, native buffers, Java version, and memory calculator version. Some runtime options have no effect if the image uses non-Paketo buildpacks or bypasses the launcher.

### 3.2 `JAVA_TOOL_OPTIONS`

`JAVA_TOOL_OPTIONS` is read by the JVM at startup; the Paketo runtime can contribute/append JVM flags through this variable. Example:

```bash
docker run --rm -d \
  --name cnb-timezone-lab \
  -p 18083:8080 \
  -e JAVA_TOOL_OPTIONS="-Duser.timezone=UTC" \
  example/cnb-env-demo:0.0.1
```

In a Paketo image, user-provided flags and buildpack-provided flags can be combined. If the same JVM flag is set by multiple sources, test actual behavior/precedence for your Paketo runtime version and JVM; do not assume `JAVA_TOOL_OPTIONS` in `docker image inspect .Config.Env` reflects every dynamically computed flag.

Never put secrets into JVM system properties, as process diagnostics/logs may display them. Avoid setting `-Xmx` arbitrarily above the container limit while the memory calculator manages JVM sizing.

### 3.3 `BPL_*` Differs from `SPRING_*`

`BPL_JVM_THREAD_COUNT` is an assumption for JVM memory sizing, whereas `SERVER_TOMCAT_THREADS_MAX` maps to Spring property `server.tomcat.threads.max` to control embedded Tomcat in matching Spring Boot versions. Both names contain "thread", yet they belong to **two different subsystems**.

To tune app runtime behavior, consult Spring Boot properties; to tune Paketo launch components, consult Paketo `BPL_*` documentation. Do not invent variable names expecting the framework to recognize them.

## 4. `BPE_*`: Intentionally Embedding Launch Environment at Build Time

### 4.1 Exception by Design

The Paketo **Environment Variables buildpack**, when present in the builder and selected, interprets variables starting with `BPE_*` during the **build stage** to create variables or modification rules for the image's **launch environment**.

| Build-Time Config | Expected Launch Impact |
| --- | --- |
| `BPE_APP_LABEL=from-image` | Sets `APP_LABEL` (per override rules) |
| `BPE_DEFAULT_APP_LABEL=from-image` | Defaults `APP_LABEL` if runtime does not supply it |
| `BPE_OVERRIDE_APP_LABEL=from-image` | Overrides `APP_LABEL` per buildpack rules |
| `BPE_APPEND_JAVA_TOOL_OPTIONS=-Dfoo=bar` | Appends to `JAVA_TOOL_OPTIONS` |
| `BPE_PREPEND_JAVA_TOOL_OPTIONS=-Dfoo=bar` | Prepends to `JAVA_TOOL_OPTIONS` |
| `BPE_DELIM_JAVA_TOOL_OPTIONS= ` | Uses a space as delimiter when appending/prepending |

Variable names on the left are **buildpack inputs**, while those on the right are **launch outputs**. Hence `BPE_*` illustrates the deliberate exception to "build-time env does not persist at runtime"—it persists **only when explicitly configured for embedding**.

### 4.2 Default and Override Example

Assuming the builder includes the Paketo Environment Variables buildpack:

```bash
pack build example/cnb-env-demo:embedded \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env BP_JVM_VERSION=17 \
  --env BPE_DEFAULT_APP_LABEL=from-image
```

With a Spring app reading `app.label`, running **without supplying `APP_LABEL`** can use the default `from-image`. If run with:

```bash
docker run --rm \
  -e APP_LABEL=blue \
  example/cnb-env-demo:embedded
```

then per `BPE_DEFAULT_*` semantics, runtime value `blue` can override the default.

This is a **conditional** example: verify that the real builder contains this buildpack, that it was selected, and inspect actual launch environment via logs/app responses. If the buildpack is absent, `BPE_DEFAULT_APP_LABEL` may simply be ignored.

### 4.3 Embedding a JVM Flag for All Deployments

Per Spring Boot 3.3 Gradle plugin docs, you can configure:

```groovy
tasks.named("bootBuildImage") {
    environment["BP_JVM_VERSION"] = "17"
    environment["BPE_DELIM_JAVA_TOOL_OPTIONS"] = " "
    environment["BPE_APPEND_JAVA_TOOL_OPTIONS"] =
        "-XX:+HeapDumpOnOutOfMemoryError"
}
```

The flag can be applied when launching the image if supported by the Paketo Environment Variables buildpack. This is a **build-stage decision modifying launch**, distinct from `docker run -e JAVA_TOOL_OPTIONS=...` on one specific deployment.

**Never put secrets into `BPE_*`**: embedded launch environments can be viewed through image/layers/metadata or inspection tools, and every deployment of that image inherits them.

### 4.4 When Should You Use `BPE_DEFAULT_*`?

Reasonable for a **non-sensitive default** needing consistency, such as an overridable label. Inappropriate for locking down `SPRING_DATASOURCE_PASSWORD`, tokens, private keys, or staging/prod-specific secrets. When each environment needs distinct config, supply it via Docker/Kubernetes runtime config to keep **the exact same image digest**.

## 5. Spring Boot Runtime: Profile, Port, App Properties

### 5.1 `SPRING_PROFILES_ACTIVE` and Relaxed Binding

Spring Boot maps `SPRING_PROFILES_ACTIVE` to `spring.profiles.active` when the application **starts**.

```bash
docker run --rm -d \
  --name cnb-staging \
  -p 18080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  example/cnb-env-demo:0.0.1
```

If `application-staging.properties` exists, Spring config data can load profile-specific properties by precedence. Naming a profile "staging" does not conjure database credentials automatically: the app still needs real configuration and separate secret sources.

**Changing runtime profiles does not require rebuilding the image** if the artifact already packages the needed resources/code. However, an already-running process does not automatically re-read new env vars when you edit a deployment spec; a new container/Pod or explicit refresh mechanism is required.

### 5.2 `SERVER_PORT` Is Not `docker -p`

Example:

```bash
docker run --rm -d \
  --name cnb-port-demo \
  -e SERVER_PORT=9090 \
  -p 18090:9090 \
  example/cnb-env-demo:0.0.1
```

`SERVER_PORT=9090` tells Spring Boot to listen on port 9090. `-p 18090:9090` publishes host port 18090 to **container** port 9090. Changing only `-p` while the app still listens on 8080 means HTTP traffic sent to container port 9090 will not be handled properly.

Kubernetes `containerPort` is similarly mostly informational port metadata; it does not force Spring to change `server.port`. Configure Spring explicitly if a different port is needed.

### 5.3 App-Specific `APP_LABEL`

In the example, `application.properties` has:

```properties
app.label=from-file
```

When the container has `APP_LABEL=blue` and no higher-precedence property source exists, Spring Boot binds the env var to `app.label` and the app reads `blue`.

Do not assume env vars win in every situation: Spring also checks command-line args, system properties, config imports, `SPRING_APPLICATION_JSON`, and other property sources depending on version/setup. If a CLI argument `--app.label=from-cli` is added by a launcher, it can override the environment variable per Spring's precedence rules.

### 5.4 Misleading Build-Time `SPRING_PROFILES_ACTIVE`

Someone might write:

```groovy
tasks.named('bootBuildImage') {
    environment['SPRING_PROFILES_ACTIVE'] = 'prod'
}
```

expecting the image to launch in `prod`. Yet in the Spring Boot Gradle plugin, `bootBuildImage.environment` goes **to the builder**, and does not automatically become the launch environment. To activate the production profile:

```bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  example/cnb-env-demo:0.0.1
```

If the build stage runs a test JVM or native/AOT compilation, environment variables can affect **those** depending on task/buildpack, which is a separate concern. Never rely on Spring profiles inside the builder to implicitly control deployment environments of an executable-JAR image.

## 6. Spring Boot Java 17+ Verification Project

### 6.1 Structure

```text
cnb-env-demo/
├── pom.xml                       # Choose Maven, or
├── settings.gradle               # choose Gradle
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/cnbenv/
│   │   │   ├── CnbEnvApplication.java
│   │   │   └── ProbeController.java
│   │   └── resources/application.properties
│   └── test/java/com/example/cnbenv/ProbeControllerTests.java
├── mvnw / mvnw.cmd               # Maven Wrapper if present
├── .mvn/wrapper/...
├── gradlew / gradlew.bat         # Gradle Wrapper if present
└── gradle/wrapper/...
```

Use only **one** build system when practicing one branch. Wrappers must be generated by trusted tooling with their supporting files; do not create empty scripts and expect `./gradlew` to work.

### 6.2 Main Class

File `src/main/java/com/example/cnbenv/CnbEnvApplication.java`:

```java
package com.example.cnbenv;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbEnvApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbEnvApplication.class, args);
    }
}
```

This is a valid Java 17+ class **when the project has Spring Boot dependencies**. Do not run bare `javac CnbEnvApplication.java` without Spring classes on the compiler classpath.

### 6.3 Probe Controller That Does Not Leak Secrets

File `src/main/java/com/example/cnbenv/ProbeController.java`:

```java
package com.example.cnbenv;

import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final Environment environment;

    public ProbeController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping(value = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        String label = environment.getProperty("app.label", "unset");
        String profiles = String.join(",", environment.getActiveProfiles());
        return "label=" + label + ";profiles=" + profiles;
    }
}
```

The controller returns **only two non-sensitive illustrative values**, never dumping `System.getenv()` or all properties. Never expose passwords or API tokens in an endpoint.

With runtime `APP_LABEL=blue` and `SPRING_PROFILES_ACTIVE=staging`, the expected response body is:

```text
label=blue;profiles=staging
```

This is the **predicted HTTP response body from the Java method**, not live Docker output. Other Spring config precedence sources can affect the actual value.

### 6.4 `application.properties`

File `src/main/resources/application.properties`:

```properties
spring.application.name=cnb-env-demo
app.label=from-file
management.endpoints.web.exposure.include=health,info
```

At runtime, `APP_LABEL` can override `app.label` via Spring Boot externalized configuration. Actuator `health` is helpful for smoke tests, while `/actuator/env` should not be exposed. In production, tighten exposure and security rather than opening all management endpoints.

### 6.5 Integration Test with a Dedicated Profile

File `src/test/java/com/example/cnbenv/ProbeControllerTests.java`:

```java
package com.example.cnbenv;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "app.label=from-test"
)
@ActiveProfiles("lab")
class ProbeControllerTests {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void readsExpectedEnvironment() {
        String body = rest.getForObject("/probe", String.class);
        assertEquals("label=from-test;profiles=lab", body);
    }
}
```

The test uses a random port, custom property `app.label=from-test`, and `@ActiveProfiles("lab")` to control the test profile. If global Spring test config or extra profiles exist, adjust assertions to match that contract. This test validates the **application inside the build/test JVM**, not whether the **OCI runtime image** receives the right env; running the real container is still required.

## 7. Gradle `bootBuildImage.environment` — Build Time

### 7.1 Complete Groovy DSL

`settings.gradle`:

```groovy
rootProject.name = 'cnb-env-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    imageName = 'example/cnb-env-demo:0.0.1'
    environment['BP_JVM_VERSION'] = '17'
}
```

`bootBuildImage` is created by the Spring Boot Gradle plugin when the Java/War plugin is applied. `environment['BP_JVM_VERSION']` is sent to the **CNB builder**, not the Spring app runtime. `imageName` specifies the OCI image name, not a Spring profile or `app.label`.

Per Spring Boot Gradle docs, the plugin can infer project Java compatibility to ask buildpacks to install the matching Java version. Here `BP_JVM_VERSION=17` is explicit to demonstrate the build mechanism. If using a different builder, verify it supports this variable name.

Run:

```bash
./gradlew clean build
./gradlew bootBuildImage
```

`build` runs Gradle checks/tests per the task graph; `bootBuildImage` creates the OCI image from the archive, **without automatically guaranteeing all tests ran**. Keeping a test gate before image builds is good practice. The Docker daemon must be accessible.

### 7.2 Complete Kotlin DSL

`settings.gradle.kts`:

```kotlin
rootProject.name = "cnb-env-demo"
```

`build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

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
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("example/cnb-env-demo:0.0.1")
    environment.put("BP_JVM_VERSION", "17")
}
```

This is the **equivalent Kotlin DSL**—do not paste Groovy syntax `environment['BP_JVM_VERSION']` into `.gradle.kts`. To change the **runtime profile**, **do not edit this block**: supply `SPRING_PROFILES_ACTIVE` when running/deploying.

### 7.3 Intentionally Adding a `BPE` Default

If the builder has the Paketo Environment Variables buildpack, you can add inside `bootBuildImage`:

```groovy
environment['BPE_DEFAULT_APP_LABEL'] = 'from-image'
```

The expected outcome is an image carrying a launch default for `APP_LABEL`. Omit this in the default example because section 10 demonstrates the **same image** receiving `APP_LABEL` from runtime. Treat this as a separate experiment; using BPE to embed data alters the release candidate image.

## 8. Maven `spring-boot:build-image` — Build Time

### 8.1 Complete POM

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

    <groupId>com.example</groupId>
    <artifactId>cnb-env-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
                        <name>example/cnb-env-demo:0.0.1</name>
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

Inside `<image><env>` is the **builder environment** of the Spring Boot Maven Plugin, not the Spring Boot application runtime environment. It does not imply every container receives `BP_JVM_VERSION` or `SPRING_PROFILES_ACTIVE`.

Run:

```bash
./mvnw clean verify
./mvnw spring-boot:build-image
```

`spring-boot:build-image` ensures the Maven `package` lifecycle runs before building the OCI image. When binding the goal to run inside the `package` lifecycle, use the `build-image-no-fork` variant per Spring Boot docs to avoid unnecessary lifecycle forking.

### 8.2 A Configuration That Looks Right but Misses the Mark

```xml
<image>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
        <SPRING_PROFILES_ACTIVE>prod</SPRING_PROFILES_ACTIVE>
    </env>
</image>
```

`SPRING_PROFILES_ACTIVE` here is **sent to the builder**, and does not guarantee the Spring application launches with `prod`. To set a production profile, pass it at runtime via Docker/Kubernetes. If there is a special reason to bake an image default, Paketo offers `BPE_DEFAULT_SPRING_PROFILES_ACTIVE`, yet that is an intentional artifact choice and generally should not couple a shared image to a single deployment environment.

### 8.3 Docker Daemon and Proxy

Spring Boot Maven `build-image` requires a Docker daemon. Variables like `DOCKER_HOST`/`DOCKER_CONTEXT`/`DOCKER_CONFIG`/TLS configuration establish the Docker engine connection **while building the image**; they are not Spring properties. Passing `HTTP_PROXY`/`HTTPS_PROXY` into the builder can help it download the JRE/runtime dependencies, while the runtime application needing an outbound proxy **requires its own configuration**.

## 9. `pack build --env` — Not `docker run -e`

### 9.1 Building an Image from an Existing Executable JAR

After `./gradlew build` in the example, the executable JAR is typically:

```text
build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar
```

Build the image using Pack CLI:

```bash
pack build example/cnb-env-demo:pack \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env BP_JVM_VERSION=17
```

The `pack build` documentation explicitly states that `--env` and `--env-file` are **build-time environment variables, not automatically present at image runtime**.

If you run:

```bash
pack build example/cnb-env-demo:pack \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env SPRING_PROFILES_ACTIVE=prod
```

do not conclude the image will launch with `prod`. That is builder env. Since the input is an already-built executable JAR, the Spring app does not normally execute inside the builder under that profile as a production server.

### 9.2 The `--env-file` Option

A non-secret build-time file:

```text
BP_JVM_VERSION=17
```

Invoke:

```bash
pack build example/cnb-env-demo:pack \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env-file build-env.txt
```

Do not confuse Pack `--env-file` with Docker `docker run --env-file`. Both tools use similar flag names, yet **different stages and processes receive the variables**.

### 9.3 Building from Source vs Building from Executable JAR

- `pack build --path build/libs/app.jar`: Paketo Java buildpacks process the already compiled/packaged JAR.
- `pack build --path .`: if the builder includes appropriate Maven/Gradle buildpacks, the builder can compile source using build tools inside.
- `bootBuildImage`/`spring-boot:build-image`: the Spring Boot plugin prepares the executable archive and hands it to CNB.

Therefore, variables like `BP_GRADLE_BUILD_ARGUMENTS` or `BP_MAVEN_BUILD_ARGUMENTS` apply when the **builder is running the build tool on source**; they are not a way to alter the host Gradle task graph in `bootBuildImage`.

### 9.4 Passing Host Env into Pack Explicitly

Pack CLI supports `--env VAR=VALUE` or `--env VAR`. In the form without `=VALUE`, the CLI can read from the current host environment per Pack docs. This is an **intentional forwarding action**, not Pack copying the developer machine's entire environment into the image.

## 10. Experiment: One Image, Two Containers, Two Runtime Configs

### 10.1 Identifying the Built Image

After a Gradle or Maven image build:

```bash
docker image inspect example/cnb-env-demo:0.0.1 \
  --format '{{.Id}}'
```

Record the real local image ID. The tag `example/cnb-env-demo:0.0.1` can be reassigned later, so with a registry/CI use the **image manifest digest** to track the immutable artifact across staging and production.

### 10.2 Container A: Staging

```bash
docker run --rm -d \
  --name cnb-env-a \
  -p 18080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  -e APP_LABEL=blue \
  example/cnb-env-demo:0.0.1
```

Wait until the app is ready, then call:

```bash
curl --fail --silent --show-error \
  http://localhost:18080/probe
```

With the sample source and no other overrides, the expected HTTP response body is:

```text
label=blue;profiles=staging
```

This is the predicted response produced by the Java controller, **not output from a live executed Docker run**. If `curl` runs too soon, use a bounded retry/health check and inspect `docker logs cnb-env-a`.

### 10.3 Container B: Production-Like

Without rebuilding, run the exact same image with different variables:

```bash
docker run --rm -d \
  --name cnb-env-b \
  -p 18081:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_LABEL=green \
  example/cnb-env-demo:0.0.1
```

Call:

```bash
curl --fail --silent --show-error \
  http://localhost:18081/probe
```

Expected result:

```text
label=green;profiles=prod
```

Same app code/classes, **different runtime env**. If profile-specific resources exist in the JAR, Spring can read additional config per profile, though the experiment checks only `APP_LABEL` and `SPRING_PROFILES_ACTIVE`.

### 10.4 Proving It Is Truly the Same Image

```bash
docker inspect cnb-env-a --format '{{.Image}}'
docker inspect cnb-env-b --format '{{.Image}}'
docker image inspect example/cnb-env-demo:0.0.1 --format '{{.Id}}'
```

If both `.Image` values match, both containers were created from the **same local image ID**. In a registry, use the digest to guard against tag drift. Changing runtime environment variables never produces a new image ID.

Do not print the full `docker inspect --format '{{json .Config.Env}}'` when real containers hold secrets, as it can leak database passwords/credentials. Use only non-sensitive probes or controlled inspection.

Clean up the lab:

```bash
docker stop cnb-env-a cnb-env-b
```

Because the containers use `--rm`, they are removed on stop. In parallel CI runs, use unique container names/ports to avoid collisions across jobs.

### 10.5 Two Additional Checks

**Check default without `APP_LABEL`:**

```bash
docker run --rm -d \
  --name cnb-env-default \
  -p 18082:8080 \
  example/cnb-env-demo:0.0.1
```

When `APP_LABEL` is omitted, the controller can return `label=from-file;profiles=`, assuming no BPE embedded default and no other env/CLI config.

**Check server port:**

```bash
docker run --rm -d \
  --name cnb-env-9090 \
  -e SERVER_PORT=9090 \
  -p 18090:9090 \
  example/cnb-env-demo:0.0.1
```

Call `http://localhost:18090/probe`, not `18090:8080`. Stop both lab containers after testing.

## 11. Docker Compose and Kubernetes: Runtime Environment

### 11.1 Compose `environment`

Example `compose.yaml`:

```yaml
services:
  app:
    image: example/cnb-env-demo:0.0.1
    ports:
      - "18080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: staging
      APP_LABEL: blue
      BPL_JVM_THREAD_COUNT: "100"
```

`docker compose up` here starts a container from an **existing image**, without triggering a Paketo build because there is no `build:` section. `environment` defines the **service's runtime env**.

If a Compose file has `build.args`, those are **Dockerfile `ARG`s** during a Docker build, not equivalent to `bootBuildImage.environment` or `pack build --env`. Do not conflate Dockerfile builds with the CNB builder lifecycle.

### 11.2 Compose `.env` vs `env_file`

- `.env` in the project or `docker compose --env-file` is normally used for **Compose variable interpolation**.
- Service `environment:` directly defines container runtime env.
- Service `env_file:` loads variables into the service/container environment.
- `docker compose config` prints the resolved model, which can reveal sensitive values; never print full output to public logs.

Example substitution using Compose syntax:

```yaml
services:
  app:
    image: example/cnb-env-demo:0.0.1
    environment:
      SPRING_PROFILES_ACTIVE: ${APP_PROFILE:-staging}
      APP_LABEL: ${APP_LABEL:-blue}
```

In YAML, `${APP_PROFILE:-staging}` is a Compose expression substituting a host variable or the default `staging`. It is **not** Spring Boot property placeholder syntax. Once the service starts the container, Spring sees `SPRING_PROFILES_ACTIVE` already resolved by Compose.

Having a `.env` file **does not mean** every key automatically enters the container unless referenced in the service model or loaded via `env_file`.

### 11.3 Kubernetes `env` and `envFrom`

Container configuration snippet inside a Deployment template:

```yaml
spec:
  template:
    spec:
      containers:
        - name: app
          image: registry.example.com/team/cnb-env-demo:0.0.1
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: APP_LABEL
              value: "green"
            - name: BPL_JVM_THREAD_COUNT
              value: "100"
```

This is an **illustrative snippet**, not a complete Deployment; real manifests require selectors, metadata, resource policies, and an actual image registry. `env` is runtime config supplied to the Pod at container startup. It **does not rebuild the image**. Updating the Pod template in a Deployment usually triggers a Pod rollout so new variables take effect.

### 11.4 Secrets and ConfigMaps

Non-sensitive values like labels can come from a ConfigMap; passwords/API tokens can come from a Kubernetes Secret or external secret manager.

```yaml
env:
  - name: APP_LABEL
    valueFrom:
      configMapKeyRef:
        name: app-settings
        key: label
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
```

A Kubernetes Secret is not inherently unreadable: you must manage RBAC, encryption at rest, audit logs, secret rotation, Pod permissions, and log redaction. Still, runtime secret injection is far safer than baking passwords into `BPE_*`/`build.gradle`/OCI layers.

## 12. Reasoning Mistakes to Avoid

### 12.1 "The variable appears in build logs, so the container has it"

**False.** Build logs only prove the variable affected a builder/tooling phase. Only container environment/launch scripts or app runtime checks prove what exists at runtime.

### 12.2 "Add `-e BP_JVM_VERSION=21` to upgrade the JVM"

**False.** Runtime env never swaps image layers. To change the Java runtime, configure the builder, build a new image, and then verify Java version/bytecode.

### 12.3 "Put `SPRING_PROFILES_ACTIVE=prod` into Gradle image environment"

**Misguided.** `bootBuildImage.environment` is builder env. Use Docker/Compose/Kubernetes runtime env to choose profiles. If an embedded default is truly desired, use BPE when supported by the builder and understand the trade-offs of an image-specific default.

### 12.4 "Pack env-file is the same as Docker env-file"

**False.** `pack build --env-file` supplies build-time environment to the builder; `docker run --env-file` supplies runtime environment to the container. Never reuse one secrets file for both, as that risks leaking sensitive data.

### 12.5 "BPE is the same as BPL"

**False.** `BPE_*` is set **at build time** for the Paketo Environment Variables buildpack to alter the **launch environment**. `BPL_*` is passed **at runtime** for Paketo launch components to read when the container starts.

### 12.6 "All build-time env vanishes completely"

**Inaccurate.** Values can **affect the Java version**, buildpack selection, layers, generated source, SBOM, or launch env if using BPE. The accurate rule is that **the container does not automatically inherit every builder env name/value**.

### 12.7 "Every environment needs its own image build"

Usually **unnecessary** when the application uses externalized runtime config. Build one image, test/promote by digest, and supply distinct runtime env for staging/prod. Only changes to code, Java runtime, native builds, CA packages, or system libraries normally warrant building a new image.

## 13. Build Proxy Differs from Runtime Proxy

When the builder must download dependencies through a proxy, the Spring Boot Gradle plugin can pass:

```groovy
tasks.named('bootBuildImage') {
    environment['HTTP_PROXY'] = 'http://proxy.example.org:3128'
    environment['HTTPS_PROXY'] = 'http://proxy.example.org:3128'
}
```

This is **builder network config**; the address is illustrative. It does not mean the Java app running inside the image automatically uses the same proxy. If runtime needs an HTTPS proxy, configure the launcher/JVM/HTTP client separately, such as via `JAVA_TOOL_OPTIONS` or client-specific settings. Not all Java HTTP clients honor `HTTP_PROXY`.

For authenticated proxies, **never commit username/password inside proxy URLs**. Use approved credential/secret injection mechanisms and protect build logs/caches. If encountering TLS trust errors from a corporate CA, install the trusted certificate properly rather than disabling certificate validation to “get past it”.

## 14. Secrets: Different Stages, Both Must Be Protected

### 14.1 Build Secrets

A token for private Maven/Gradle dependencies may be needed **inside the builder**. Yet `--env MY_TOKEN=...` is not a secure secret mechanism by default: it can surface in command history, logs, caches, or process/config metadata. Use **CNB service bindings**, secret mounts, or official credential mechanisms supported by your builder/platform.

Never embed build tokens into `application.properties`, the JAR, or `BPE_*`. Never publish `--debug` output if it contains internal URLs/tokens.

### 14.2 Runtime Secrets

Database passwords, API keys, and TLS private keys are typically injected **when the container runs** via a secret manager/Kubernetes Secret/mounted file/appropriate runtime injection. Never encode secrets into OCI images, Gradle `image.environment`, Maven POMs, or BPE defaults.

Runtime env is not “100% invisible” either: anyone authorized to inspect Pods/containers or processes can read it; least-privilege access, redaction, and rotation remain essential.

### 14.3 Public Config vs Private Config

Values like `APP_LABEL=blue` and `SPRING_PROFILES_ACTIVE=staging` are normally non-sensitive, whereas `SPRING_DATASOURCE_PASSWORD` or `API_TOKEN` are secrets. In this lab, the controller returns only label/profiles; **do not add an endpoint that dumps all of `System.getenv()`**.

### 14.4 Do Not Leak Data via Runtime Image Debugging

`docker inspect <container>` can display the full `Config.Env`. Avoid printing `docker inspect --format '{{json .Config.Env}}'` to broadly accessible CI logs. When comparing environments, log only **variable names** or redacted values, never raw secrets.

## 15. Runtime Diagnostics and Launcher

### 15.1 Image Metadata Does Not Show All Launch-Time JVM Flags

`docker image inspect` displays image config metadata; however, the Paketo runtime uses launcher/profile scripts and can compute `JAVA_TOOL_OPTIONS` dynamically from cgroup memory limits and `BPL_*`. Thus, not seeing every flag inside `Config.Env` **does not prove** runtime components failed to run.

You can check:

```bash
docker image inspect example/cnb-env-demo:0.0.1 \
  --format '{{.Id}}'

docker image inspect example/cnb-env-demo:0.0.1 \
  --format '{{.Config.Entrypoint}}'

docker inspect cnb-env-a --format '{{.Image}}'
```

If an image uses the CNB launcher, overriding `--entrypoint` directly can **bypass the environment setup** the buildpack relies on. Some Paketo run images have no shell; `docker exec ... sh` is not a reliable check on every image.

### 15.2 Interpreting Build Logs

In Spring Boot `bootBuildImage` or `spring-boot:build-image` build logs, look for:

- Builder image and buildpack IDs and versions.
- Java runtime dependency version chosen by the buildpack.
- Detect/build/export steps and output image name/digest.
- Whether `BP_JVM_VERSION` was honored or ignored by the builder.
- Whether the Paketo Environment Variables buildpack processed `BPE_*`.
- Whether secrets leaked due to overly verbose debug logging.

Do not conclude from **a shell line `export BP_JVM_VERSION=17`** that the builder actually used it; verify plugin forwarding config and logs.

### 15.3 Testing with Pure Java 17 (Without Spring)

An example isolating **runtime environment** from the build system:

```java
public final class EnvProbe {
    public static void main(String[] args) {
        String value = System.getenv().getOrDefault("APP_LABEL", "unset");
        System.out.println("APP_LABEL=" + value);
    }
}
```

Save as `EnvProbe.java`. On JDK 17+ in the same directory:

```bash
javac EnvProbe.java
APP_LABEL=blue java EnvProbe
```

Exact program stdout:

```text
APP_LABEL=blue
```

When the variable is unset (e.g. on systems with `env -u`):

```bash
env -u APP_LABEL java EnvProbe
```

Stdout:

```text
APP_LABEL=unset
```

This program compiles **once** and runs under multiple environments; `javac` does not need to know `APP_LABEL`. It demonstrates Java process environment mechanics without needing Cloud Native Buildpacks.

## 16. Windows PowerShell

PowerShell uses `$env:VAR` to set process variables for the session, not Bash's `VAR=value command`.

```powershell
$env:BP_JVM_VERSION = "17"
$env:APP_LABEL = "blue"
```

These commands still only configure the **host process environment** and do not automatically copy variables into the builder or OCI image. With Gradle, use `environment.put(...)`/`environment['...']` in the proper DSL; with Pack CLI, pass `--env BP_JVM_VERSION=17`.

Single-line PowerShell example (without shell line continuation):

```powershell
pack build example/cnb-env-demo:pack --builder paketobuildpacks/builder-jammy-base --path build\libs\cnb-env-demo-0.0.1-SNAPSHOT.jar --env BP_JVM_VERSION=17
```

Run the container with **runtime** env:

```powershell
docker run --rm -d --name cnb-win -p 18080:8080 -e SPRING_PROFILES_ACTIVE=staging -e APP_LABEL=blue example/cnb-env-demo:pack

(Invoke-WebRequest -Uri "http://localhost:18080/probe").Content

docker stop cnb-win
```

`.Content` per the sample Java code will be `label=blue;profiles=staging` once the server is ready. Windows Docker Desktop must run in Linux containers mode to match Paketo Linux builder/run images; otherwise OS/platform incompatibility errors occur regardless of correct variables.

## 17. Image Identity and CI/CD

### 17.1 A Tag Is Not a Digest

`example/cnb-env-demo:0.0.1` is a **tag that can be reassigned**. With a registry, use an immutable digest (e.g. an image ref with `@sha256:...` provided by the registry) to guarantee staging/prod pull the exact QA-verified bytes rather than relying solely on a tag.

Record essential build inputs: commit hash, build tool, plugin version, builder/run image digests, Paketo buildpacks, Java compatibility, and non-sensitive `BP_*`/`BPE_*` settings. Keep runtime config in deployment specs/secret references rather than baking all of it into artifact metadata.

### 17.2 When Is a New Image Needed?

**Consider rebuilding and re-running QA** when changing:

- Java runtime version `BP_JVM_VERSION`, JVM provider/type, `BP_JVM_JLINK_ENABLED`.
- Builder/buildpacks/run image/OS stack/CA packages.
- Source code, runtime dependency versions, Spring Boot version.
- Native-image build mode or source/AOT compilation.
- `BPE_*` launch defaults baked into the artifact.
- Build processes that genuinely transform resources/classes based on new inputs.

**Usually no rebuild is needed** when changing only:

- `SPRING_PROFILES_ACTIVE` for staging/prod.
- `APP_LABEL` or runtime feature flags.
- Externalized database URL/password.
- `SERVER_PORT`/network routing within app-supported bounds.
- `BPL_JVM_THREAD_COUNT` or runtime `JAVA_TOOL_OPTIONS` tuning.

Even when the image itself stays identical, new runtime configs **must still pass smoke/integration tests** before production rollout.

### 17.3 Controlled Pipeline

1. Check out the exact source/commit using a reviewed Maven/Gradle Wrapper.
2. Run tests and build the executable JAR.
3. Build the OCI image via Paketo with pinned/recorded builder and `BP_*`.
4. Scan image/dependencies, verify runtime Java, and run HTTP smoke tests.
5. Push image and capture the real registry manifest digest.
6. Deploy to staging **by digest**, passing staging env/secret refs when starting Pods/containers.
7. Test staging with authorized data/secrets.
8. Promote the **exact same digest** to production, changing only runtime env/secret refs/resources.
9. Collect logs/metrics and support digest-based rollback.
10. When actual build inputs change, produce a **new release candidate** and repeat gates.

**Never rebuild the image in the production stage** and still claim it was "already tested in staging" if the digest differs. Exceptions require strict reproducible build + attestation pipelines, whereas the simplest and safest pattern is **promoting the same image digest**.

## 18. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `BP_JVM_VERSION` does not change Java during `docker run -e` | It is build-time Paketo config | Rebuild image via plugin/pack, check runtime Java |
| `SPRING_PROFILES_ACTIVE` set in `bootBuildImage.environment` yet app uses default | Builder env does not become launch env | Pass runtime `docker run -e`/Kubernetes `env` |
| Host `export APP_LABEL=blue` ignored by container | Host env does not propagate automatically | Pass runtime env explicitly |
| `pack build --env-file` has profile yet app ignores it | Pack env-file is build-only | Use Docker runtime env-file or Compose |
| `BPE_DEFAULT_APP_LABEL` ignored | Builder lacks Paketo Environment Variables buildpack | Check buildpacks/logs and rebuild properly |
| Runtime fails to override `BPE_*` | May have used `OVERRIDE` instead of `DEFAULT`, or higher-precedence Spring property source | Check BPE action and Spring precedence |
| `BPL_JVM_THREAD_COUNT` does not change HTTP response | Configures JVM memory, not a Spring app property | Inspect JVM launch flags/memory calculator |
| `BPL_*` has no effect | Image lacks Paketo runtime component or launcher was bypassed | Check buildpacks and entrypoint |
| `JAVA_TOOL_OPTIONS` concatenated strangely | BPE append missing delimiter or multiple JVM flag sources | Check `BPE_DELIM_JAVA_TOOL_OPTIONS` and startup flags |
| `SERVER_PORT=9090` yet host curl cannot connect | Wrong Docker port mapping or app not ready | Use `-p HOST:9090` and check logs |
| Java tests pass yet app container fails | Tests ran on build JVM, runtime config differs | Run HTTP smoke test on final image |
| `bootBuildImage` task not found | Boot and Java/War plugins not applied to right module | Check `:module:tasks --all` |
| Maven `build-image` cannot find Docker daemon | Wrong `DOCKER_CONTEXT`/HOST/TLS | Check Docker daemon connection |
| Buildpack ignores `BP_*` | Non-Paketo builder or unsupported variable | Consult builder/buildpack docs |
| Builder proxy works yet runtime HTTPS fails | Runtime proxy/truststore differs | Configure runtime proxy/CA separately |
| Same tag behaves differently after pull | Mutable tag repointed to another digest | Pin/publish by digest, check image identity |
| Changed env yet old Pod keeps old value | Container not restarted/rolled out | Trigger new Pod rollout per deployment model |
| Image contains secrets | Used BPE/ARG/ENV/source to embed credentials | Rotate secrets, fix pipeline, rebuild image |
| `docker inspect` log leaks secrets | Printed full `Config.Env` | Restrict inspection, redact values, enforce RBAC |
| CNB image lacks a shell | Minimal run image | Probe/debug externally rather than forcing `sh` |
| `pack --path .` differs from `bootBuildImage` | One builds from source, the other consumes prebuilt JAR | Compare artifacts, buildpacks, task graph |
| Java runtime older than class-file target | Incompatible build/runtime Java | Align `BP_JVM_VERSION`, compiler target, and tests |
| Changed `-p` yet server still listens on old port | `-p` only maps ports, does not set Spring `server.port` | Set `SERVER_PORT` or fix port mapping |
| App reads file value instead of env | Wrong env var name or higher-precedence source | Check `APP_LABEL` and Spring property sources |
| BPE bakes `prod` profile into every image | Wrong default/override strategy | Remove env-specific BPE, inject runtime config per environment |

### Short Investigation Workflow

1. Determine whether the variable acts at **build**, **launch runtime**, or **image-embedded** time.
2. Check the exact plugin task and image reference/digest.
3. Verify builder/buildpack version and whether the variable is passed via real tool config.
4. Confirm a fresh container was launched with the expected runtime env.
5. Check `/probe`, `/actuator/health`, and startup logs instead of substituting build logs for runtime evidence.
6. For memory flags, inspect JVM/memory calculator; for app properties, inspect Spring.
7. For secrets, avoid logging values and use RBAC/secret managers.
8. If a different Java/runtime library is needed, rebuild the image; if only profile/app label changed, do not rebuild.

## 19. Practice Exercises

### A. Classify Variables

Classify the following into builder-only, runtime launch, embedded launch default, or host/tooling:

```text
BP_JVM_VERSION
BP_JVM_TYPE
BPL_JVM_HEAD_ROOM
BPL_JVM_THREAD_COUNT
BPE_DEFAULT_APP_LABEL
BPE_APPEND_JAVA_TOOL_OPTIONS
SPRING_PROFILES_ACTIVE
SERVER_PORT
APP_LABEL
JAVA_TOOL_OPTIONS
HTTP_PROXY
DOCKER_HOST
```

Explain why `HTTP_PROXY` and `JAVA_TOOL_OPTIONS` can be read by different processes depending on **which stage supplies them**, while `DOCKER_HOST` configures the Docker client/daemon connection.

### B. Gradle Build and Two Containers

1. Set up the project from sections 6–7.
2. Run `./gradlew clean build` and `./gradlew bootBuildImage`.
3. Record local image ID, builder, and Java major.
4. Run container A with `APP_LABEL=blue`, `SPRING_PROFILES_ACTIVE=staging`.
5. Run container B with `APP_LABEL=green`, `SPRING_PROFILES_ACTIVE=prod`.
6. Compare both HTTP responses and both image IDs without rebuilding in between.
7. Conclude that image identity remains unchanged even when runtime config changes.

### C. Maven `build-image`

1. Use the sample POM in section 8 and the same Java code.
2. Run Maven tests, then `spring-boot:build-image`.
3. Inspect `<image><env>` and explain why it **does not automatically establish a runtime profile**.
4. Run with `staging` and `prod` profiles via `docker run -e`.
5. Verify via HTTP responses and image ID.

### D. Pack CLI

1. Build an executable JAR using Gradle/Maven.
2. Run `pack build --path <actual-jar> --env BP_JVM_VERSION=17`.
3. Run the image with `APP_LABEL`/`SPRING_PROFILES_ACTIVE`.
4. On a lab branch, test `pack --env SPRING_PROFILES_ACTIVE=prod` and verify runtime does not inherit it automatically.
5. Distinguish `pack --env-file` from Docker `run --env-file`.

### E. BPE Default

1. Choose a Paketo builder containing the Environment Variables buildpack.
2. Build with `BPE_DEFAULT_APP_LABEL=from-image`.
3. Run without `APP_LABEL`; record the actual label.
4. Re-run with `-e APP_LABEL=blue`; compare results.
5. Explain why a BPE default is an **artifact configuration** and must never hold secrets.

### F. Runtime JVM Tuning

1. Start two containers from the same image with different `BPL_JVM_THREAD_COUNT` values.
2. Keep an explicit memory limit and inspect relevant Paketo/JVM diagnostics.
3. Do not expect `/probe` output to change since the controller does not read that variable.
4. If the memory calculator is absent, state the limitation of the experiment rather than claiming success.

### G. Compose and Kubernetes

1. Write a Compose service `environment` for staging.
2. Explain `.env` vs `env_file`.
3. Write a Kubernetes Pod fragment with `env` and `secretKeyRef` for prod.
4. Describe how to update deployment env and roll out Pods without rebuilding the image.
5. Describe where secrets protection and log redaction are required.

### H. Critique an Incorrect Setup

Someone runs:

```bash
pack build example/cnb-env-demo:wrong \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env SPRING_PROFILES_ACTIVE=prod

docker run --rm example/cnb-env-demo:wrong
```

They claim the image definitely runs `prod`. Point out that `pack --env` targets the builder; for Spring to run `prod`, pass `SPRING_PROFILES_ACTIVE=prod` at launch or use an intentional, supported **BPE launch default**. State which evidence settles the question.

### I. Report Based on Real Results

```text
Module:
Spring Boot plugin version:
Builder image/buildpacks version:
Build command:
Build-time vars (non-sensitive):
Image name + local ID + registry digest:
Container A env (non-sensitive):
Container A HTTP status/body:
Container B env (non-sensitive):
Container B HTTP status/body:
Two containers same image ID?:
BPE default used? Result:
BPL runtime flags used? Evidence:
Secrets injection source (no values):
Conclusion build vs runtime:
```

This is a **report template for recording real results**, not a pre-filled passing report. If Docker/buildpacks are unavailable in the learning environment, explicitly record **smoke test not executed** rather than fabricating HTTP 200 or SHA/digest values.

## 20. Knowledge and Operations Checklist

- [ ] Correctly identify where each variable is supplied: host, CNB builder, image launch, Docker/Kubernetes runtime.
- [ ] `BP_JVM_VERSION` aligns with Java compiler compatibility and is supported by the builder.
- [ ] Gradle `bootBuildImage.environment`/Maven `image.env` contain only intentional builder config.
- [ ] `pack build --env` is understood as build-time, not runtime.
- [ ] `BPL_*` is used only when the image includes the corresponding Paketo launch component.
- [ ] When using `BPE_*`, understand it **embeds/modifies the image's launch env**.
- [ ] No credentials embedded in `BPE_*`, build scripts, image layers, or debug logs.
- [ ] `SPRING_PROFILES_ACTIVE`/`APP_LABEL` are supplied at runtime per environment.
- [ ] `SERVER_PORT` and Docker/Kubernetes port mappings match.
- [ ] Application is tested during build and final image is smoke-tested with real runtime env.
- [ ] Image ID/digest—not solely mutable tags—proves staging/prod share the exact artifact.
- [ ] Runtime secrets are injected via dedicated mechanisms with RBAC/redaction/rotation.
- [ ] Changing build-time config → build new image and re-run QA; changing runtime config → roll out new containers.
- [ ] Never dump the full environment via HTTP/Actuator or CI logs.
- [ ] Actual HTTP responses, logs, and metadata support every “verified” claim.

## 21. Official Documentation

- Spring Boot 3.3.13 Maven Plugin — Packaging OCI Images, `image.env`: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html
- Spring Boot 3.3.13 Gradle Plugin — Packaging OCI Images, `bootBuildImage.environment`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html
- Spring Boot 3.3 — Externalized Configuration, env vars and property source precedence: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Paketo — How To Configure Buildpacks: `BP_*`/`BPL_*`/`BPE_*`: https://paketo.io/docs/howto/configuration/
- Paketo — How to Build Java Apps, Java version and runtime JVM: https://paketo.io/docs/howto/java/
- Paketo — Java Buildpack Reference, memory calculator: https://paketo.io/docs/reference/java-reference/
- Cloud Native Buildpacks — `pack build` CLI, `--env`/`--env-file` build-time: https://buildpacks.io/docs/tools/pack/cli/pack_build/
- Cloud Native Buildpacks — Launch process: https://buildpacks.io/docs/for-buildpack-authors/how-to/write-buildpacks/specify-launch-processes/
- Docker — `docker container run` options: https://docs.docker.com/reference/cli/docker/container/run/
- Docker Compose — Environment precedence: https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/
- Kubernetes — Define Environment Variables: https://kubernetes.io/docs/tasks/inject-data-application/define-environment-variable-container/
- Kubernetes — Secrets: https://kubernetes.io/docs/concepts/configuration/secret/

**Remember:** `BP_*` is Paketo build-time config, `BPL_*` targets runtime launch components, `BPE_*` **embeds launch env from build time**, and Spring properties like `SPRING_PROFILES_ACTIVE`/`SERVER_PORT` belong at runtime when varying by environment. **`pack build --env`, Gradle `bootBuildImage.environment`, and Maven `image.env` are not equivalent to `docker run -e`.** Verify with **one image digest, two containers, two runtime configs, and real HTTP responses**, without rebuilding just to swap a profile or label.