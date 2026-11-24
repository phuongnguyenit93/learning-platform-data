# Inspecting Metadata in Archives and Its Relationship with Spring Boot Actuator info

## 1. Why inspect metadata in both the packaged file and the running application?

When releasing a Spring Boot application, development teams typically want to answer four questions:

1. **Which artifact is running?** For example `com.example:metadata-demo:0.1.0-SNAPSHOT`.
2. **Which Git commit was the artifact built from?** To link the running process back to source code, releases, and pipelines.
3. **Was metadata actually written into the executable JAR/WAR?** A successful build plugin configuration does not guarantee every metadata file ended up inside the artifact used by the server.
4. **Does Spring Boot Actuator publish that exact information at `/actuator/info`?** The endpoint must be enabled, exposed over HTTP, and backed by the appropriate `InfoContributor` beans.

In Spring Boot, related yet **non-identical** data layers include:

- `META-INF/MANIFEST.MF`: standard JAR/WAR archive metadata; Spring Boot executable archives use fields such as `Main-Class` and `Start-Class`.
- `META-INF/build-info.properties`: **build-time** info such as group, artifact, name, version, and build timestamp; Spring Boot auto-configures `BuildProperties` when found on the classpath.
- `git.properties`: **Git source revision** info such as commit ID, branch, and commit time; Spring Boot auto-configures `GitProperties` when found at the classpath root.
- **Actuator `info`**: endpoint aggregating data from `InfoContributor` beans; by default `build` and `git` contributors are enabled when metadata exists, while **exposing the endpoint over HTTP** must be evaluated separately.

This lab uses **Spring Boot 3.5.x, Java 17**, with Maven or Gradle. Plugins and layouts are chosen to fit the examples; projects on Spring Boot 4.x or older versions should consult documentation for their exact version.

**Inspection principle:** inspect the **actual deployed artifact**, not only the POM/build script or an endpoint served by an IDE process. A JAR built yesterday can still hold an old commit/version even if today's source and `pom.xml` changed.

## 2. Data flow diagram: build-time → archive → runtime → HTTP

```text
Git repository                       Maven / Gradle project
- HEAD commit                       - group / artifact / version
- branch                             - build time
        |                                      |
        v                                      v
Git metadata generator                Spring Boot build-info task/goal
        |                                      |
        v                                      v
git.properties                       META-INF/build-info.properties
        |                                      |
        +----------------+---------------------+
                         |
                         v
              processResources/classes
                         |
                         v
         Spring Boot executable JAR / WAR
         - BOOT-INF/classes/... (JAR)
         - WEB-INF/classes/...  (WAR)
                         |
             java -jar / deploy
                         |
                         v
            Spring application context
              |                   |
              v                   v
          GitProperties       BuildProperties
              |                   |
              v                   v
          GitInfoContributor  BuildInfoContributor
              +--------+----------+
                       |
                       v
                Actuator InfoEndpoint
                       |
             [HTTP exposure + security]
                       |
                       v
                  GET /actuator/info
```

Separate **three conditions**:

**Condition A — generate metadata:** Gradle/Maven must execute the task or goal that creates metadata files. Applying the Spring Boot plugin alone does not necessarily trigger `build-info` unless declared.

**Condition B — file present on the runtime classpath:** the file must be copied to class outputs and packaged into the real runnable JAR/WAR. Running a `plain.jar` or a file from another module by mistake means the runtime will not see the expected metadata.

**Condition C — information published:** the `spring-boot-starter-actuator` dependency is present, contributors are not disabled, the `info` endpoint is permitted, and it is exposed on the channel being queried. A valid file in the JAR can still result in HTTP 404 or `{}` if runtime conditions are unmet.

## 3. Comparing metadata types and storage locations

| Source | File/entry | Created by | How does Spring Boot read it? | Commonly used for |
|---|---|---|---|---|
| Standard manifest | `META-INF/MANIFEST.MF` | Maven JAR/WAR, Gradle archive + Boot repackager | `java -jar` uses `Main-Class`; Boot Loader uses `Start-Class` | Checking launcher, main class, build-dependent manifest version |
| Build info | `META-INF/build-info.properties` at **classpath root** | Spring Boot Maven `build-info` goal or Gradle `bootBuildInfo` task | `BuildProperties` bean → `BuildInfoContributor` | Release/group/version/build timestamp |
| Git info | `git.properties` at **classpath root** | Git Commit ID Maven plugin / Gradle Git Properties plugin | `GitProperties` bean → `GitInfoContributor` | Source revision traceability |
| `info.*` Spring properties | `application.properties` or external config | Developer/CI/runtime config | `EnvironmentInfoContributor`, **disabled by default in Boot 3.5** | Custom operational info |
| Custom InfoContributor | Spring bean class | Developer | Bean implementing `InfoContributor` | Custom-filtered or computed metadata |
| Build version from archive filename | `build/libs/app-0.1.0.jar` | Maven/Gradle naming | **Not** a default source for `BuildProperties` | Quick visual filename check; insufficient as runtime proof |

In particular, **Maven POM version does not appear at `/actuator/info` automatically** merely because `pom.xml` exists. Spring Boot requires `META-INF/build-info.properties` or another `InfoContributor` supplying that information. Manifest and build-info are also **not guaranteed to stay in sync** if a pipeline modifies the manifest, reuses an old archive, or generates metadata in another module.

## 4. Locations inside executable JARs and WARs

### 4.1. Executable JAR

A Spring Boot executable JAR uses Boot Loader, application classes, and nested dependencies in the familiar layout:

```text
metadata-demo-0.1.0-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/metadata/MetadataApplication.class
    │   ├── META-INF/build-info.properties
    │   ├── git.properties                 [if generated]
    │   └── application.properties
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-boot-actuator-*.jar
        └── ... dependencies
```

This tree is illustrative; sub-JAR names, index files, and dependency counts vary by build. On the **classpath**, `META-INF/build-info.properties` sits at the root under `META-INF`; as a **ZIP entry** in a Spring Boot executable JAR, it typically resides at:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

Similarly, `git.properties` at the classpath root is packaged as:

```text
BOOT-INF/classes/git.properties
```

**Do not confuse** `META-INF/MANIFEST.MF` at the archive root with `BOOT-INF/classes/META-INF/build-info.properties` inside application classes. The two files have different purposes and paths.

### 4.2. Executable WAR

When a project is a Spring Boot executable WAR, class output uses `WEB-INF/classes`:

```text
metadata-demo-0.1.0-SNAPSHOT.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/launch/WarLauncher.class
└── WEB-INF/
    ├── classes/
    │   ├── com/example/metadata/MetadataApplication.class
    │   ├── META-INF/build-info.properties
    │   └── git.properties                 [if generated]
    ├── lib/
    └── lib-provided/
```

Archive metadata is still resolved on the **application classpath**: `WEB-INF/classes/META-INF/build-info.properties` and `WEB-INF/classes/git.properties` under the WAR layout. `WEB-INF/lib-provided` holds provided dependencies when running a Boot WAR via `java -jar`; it is not where build-info normally lives.

When deploying a WAR to an external servlet container, startup and context paths differ from an executable WAR; however, if metadata files are on the web application's classpath and Actuator is configured properly, `BuildProperties`/`GitProperties` can still be created. Test the actual deployment path separately.

### 4.3. What information is in the manifest?

A Boot 3.5 executable JAR manifest typically contains:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.metadata.MetadataApplication
Spring-Boot-Version: 3.5.16
```

`Main-Class` is the launcher invoked by `java -jar`; `Start-Class` is your application's Java main class. `Spring-Boot-Version` is the framework/packaging plugin version, **not necessarily equal to the application artifact version**. The manifest may also carry `Implementation-Version` if configured by the build, though **Actuator build info does not automatically read arbitrary manifest attributes as `build.*` sources**.

In Boot 3.2+, the launcher package is `org.springframework.boot.loader.launch`. If comparing against Boot 2.x documentation showing the older launcher package, treat **your current artifact's manifest** as evidence rather than applying old class names to a new build.

## 5. Runnable example: Spring Boot Java 17 with /actuator/info

Create a project named `metadata-demo` from Spring Initializr with **Java 17**, Spring Boot 3.5.x, and dependencies **Spring Web**, **Spring Boot Actuator**, and **Spring Boot Starter Test**. Pick **Maven or Gradle**; do not mix both build tools in the same module just to run the lesson.

Shared source layout:

```text
metadata-demo/
├── pom.xml                   [if using Maven]
│   or
├── settings.gradle           [if using Gradle Groovy]
├── build.gradle
├── src/main/java/com/example/metadata/
│   ├── MetadataApplication.java
│   └── VersionController.java
├── src/main/resources/application.properties
└── src/test/java/com/example/metadata/
    └── BuildMetadataTest.java
```

### 5.1. Spring Boot main class

`src/main/java/com/example/metadata/MetadataApplication.java`:

```java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetadataApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }
}
```

### 5.2. Controller reading BuildProperties

`src/main/java/com/example/metadata/VersionController.java`:

```java
package com.example.metadata;

import java.util.Map;
import org.springframework.boot.info.BuildProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {
    private final BuildProperties build;

    public VersionController(BuildProperties build) {
        this.build = build;
    }

    @GetMapping("/version")
    public Map<String, String> version() {
        return Map.of(
                "artifact", build.getArtifact(),
                "version", build.getVersion());
    }
}
```

Key point: `BuildProperties` is only available when Spring Boot finds a valid `META-INF/build-info.properties` on the runtime classpath. This controller **intentionally requires the bean**, so a build missing metadata fails loudly at startup instead of silently returning a guessed version.

For projects that must boot even without build-info (e.g., running a Java file standalone before building), inject `ObjectProvider<BuildProperties>` or design an explicit fallback. **Never** add a fake fallback like `0.0.0` and present it as the accurately packaged version.

### 5.3. HTTP exposure configuration

`src/main/resources/application.properties`:

```properties
spring.application.name=metadata-demo
server.port=8080

# Expose only health and info in this hands-on lab.
management.endpoints.web.exposure.include=health,info
```

In Spring Boot 3.5, **only `health` is exposed over HTTP by default**, so setting `management.endpoints.web.exposure.include=health,info` is required to test `GET /actuator/info`. You do not need `management.info.build.enabled=true` here because the `build` contributor is enabled by default when metadata exists. `management.info.git.enabled` is also enabled by default where applicable.

In production, enforce an endpoint protection policy; this lab neither opens all endpoints with `*` nor puts secrets into info.

### 5.4. Testing BuildProperties

`src/test/java/com/example/metadata/BuildMetadataTest.java`:

```java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BuildMetadataTest {
    @Autowired
    private BuildProperties buildProperties;

    @Test
    void buildMetadataWasGenerated() {
        assertNotNull(buildProperties);
        assertEquals("metadata-demo", buildProperties.getArtifact());
        assertEquals("0.1.0-SNAPSHOT", buildProperties.getVersion());
    }
}
```

This test **does not check** Git info and needs no HTTP port to run. It verifies that the build placed the metadata file on the test runtime classpath and Spring instantiated `BuildProperties`. If the project changes `group`, `artifactId`, or `version`, update expected values or design assertions per release requirements; do not commit tests with hardcoded versions when pipelines continuously override versions.

JUnit Jupiter tests run when `spring-boot-starter-test` is on the test classpath, the build-info goal/task is wired properly, and Maven/Gradle test resource processing has executed.

## 6. Maven: generating build-info.properties and the executable JAR

### 6.1. Complete POM for the example

`pom.xml` (inheriting Spring Boot starter parent):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>metadata-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <name>Metadata Demo</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                        <id>generate-build-info</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

In a project inheriting `spring-boot-starter-parent`, the Spring Boot Maven Plugin's version and `repackage` goal are managed by the parent. The `build-info` execution above is the **part you add** to generate metadata. This goal normally binds to `generate-resources`; the default output is:

```text
target/classes/META-INF/build-info.properties
```

**You do not need to create `src/main/resources/META-INF/build-info.properties` manually** when the plugin generates it. To have pipelines control build version, alter `<version>` or build properties via standard Maven mechanisms rather than manually editing generated files in `target/classes` after packaging.

### 6.2. Build, inspect the file, and run

With a valid Maven Wrapper from Spring Initializr:

```bash
./mvnw clean verify
java -jar target/metadata-demo-0.1.0-SNAPSHOT.jar
```

On Windows: `mvnw.cmd clean verify` and `java -jar target/metadata-demo-0.1.0-SNAPSHOT.jar`. `verify` runs the lifecycle through verification and builds the JAR at `package`; `build-info` already ran before compile/test via its execution.

In a second terminal:

```bash
curl -s http://localhost:8080/version
curl -s http://localhost:8080/actuator/info
```

With the example POM/source, `/version` returns a JSON object containing:

```json
{
  "artifact": "metadata-demo",
  "version": "0.1.0-SNAPSHOT"
}
```

JSON key ordering is **not guaranteed**. `/actuator/info` includes a `build` section; it may also include `time` depending on plugin/config, while `git` only appears when Git metadata exists. Never hardcode a timestamp from another build into expected output.

### 6.3. Maven goals do not auto-run just because the plugin is declared

Distinguish:

- `spring-boot:repackage`: builds the executable archive.
- `spring-boot:build-info`: creates `META-INF/build-info.properties`.
- `spring-boot:run`: runs the application from classes/development classpath.
- `mvn package`/`verify`: executes goals **bound** to the lifecycle.

If you only declare Spring Boot Maven Plugin **without adding the `build-info` execution**, do not assume build-info output will exist. If a plugin goal is run manually and repackaged by a separate pipeline step, verify the generated file actually enters the final JAR.

### 6.4. Adding optional build details

Inside the `<execution>` of `spring-boot-maven-plugin`, add `<configuration>` when needed:

```xml
<configuration>
    <additionalProperties>
        <release.channel>training</release.channel>
        <java.version>${java.version}</java.version>
    </additionalProperties>
</configuration>
```

This is a **fragment**, not a complete plugin or POM. Additional properties receive the `build.` prefix when written to `build-info.properties`, e.g. `build.release.channel=training`. Never put passwords, tokens, or sensitive internal URLs into `additionalProperties`, as the file can be packaged into the artifact and exposed via info.

**Note on nested configuration:** if the `build-info` goal sits inside an execution and you want configuration scoped specifically to it, place `<configuration>` inside that exact execution; avoid creating two executions writing to the same path uncontrollably.

## 7. Gradle: generating metadata with bootBuildInfo

### 7.1. Groovy DSL — complete project

`settings.gradle`:

```groovy
rootProject.name = 'metadata-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'
description = 'Metadata Demo'

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

springBoot {
    buildInfo()
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`springBoot { buildInfo() }` configures the **`bootBuildInfo`** task. Per Spring Boot 3.5 documentation, the task creates `META-INF/build-info.properties` for the **main source set** and wires it so the resource is present on the classpath. Default fields include `build.artifact`, `build.group`, `build.name`, `build.version`, and `build.time`.

Commands:

```bash
./gradlew clean test bootJar
java -jar build/libs/metadata-demo-0.1.0-SNAPSHOT.jar
```

With `bootJar`, the executable archive output lives in `build/libs` (unless `archiveFileName` is changed). The generated file can be viewed under the output of `bootBuildInfo`/main resources, though you **must inspect the actual archive** since plugin task output paths can change across versions.

**Do not manually guess and add `processResources.dependsOn bootBuildInfo`** when `springBoot.buildInfo()` already wires it cleanly. Redundant dependencies may not fail immediately, yet they obscure the build script and easily cause task cycles as configurations evolve.

### 7.2. Equivalent Kotlin DSL

`settings.gradle.kts`:

```kotlin
rootProject.name = "metadata-demo"
```

`build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"
description = "Metadata Demo"

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
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

springBoot {
    buildInfo()
}

tasks.test {
    useJUnitPlatform()
}
```

Java/test files are identical to Section 5; do not paste Groovy syntax like `implementation '...'` into `build.gradle.kts`. In a multi-module project, only application modules needing metadata require `bootBuildInfo`; do not assume every library module needs `/actuator/info`.

### 7.3. Customizing or excluding build.time to support repeatable builds

**Issue:** Per Spring Boot 3.5 Gradle plugin docs, the default `build.time` is the build instant, causing task output to change on every run and preventing `bootBuildInfo` from being **up-to-date**. That increases downstream work and reduces artifact reproducibility.

If a team prioritizes repeatability and speed over having a task-generated runtime timestamp in every artifact, you can **exclude the `time` field**:

```groovy
// Replacement for springBoot { buildInfo() } in build.gradle.
springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            additional = [
                'release.channel': 'training'
            ]
        }
    }
}
```

Kotlin DSL:

```kotlin
// Replacement for springBoot { buildInfo() } in build.gradle.kts.
springBoot {
    buildInfo {
        excludes.set(setOf("time"))
        properties {
            additional.set(mapOf("release.channel" to "training"))
        }
    }
}
```

These are **mutually exclusive alternatives**; do not place multiple conflicting `springBoot.buildInfo` blocks in a real project. When `time` is omitted, `/actuator/info` no longer displays `build.time`; CI can still record release timestamps in a separate deployment/release system.

In Maven, the `build-info` goal offers `time` and `excludeInfoProperties`. Per Boot 3.5 docs, setting `<time>off</time>` in the goal's configuration or excluding the `time` field is the deliberate way to omit `build.time`. Never use a fabricated fake timestamp that misleads traceability.

## 8. Git revision: generating git.properties separately from build-info

### 8.1. Git metadata answers a different question

`build-info.properties` describes the **project artifact**: group, artifact, name, version, and time. `git.properties` describes the **Git state at build time**: commit, branch, commit time, and optionally additional fields provided by the plugin.

Example `git.properties` at the classpath root:

```properties
git.branch=main
git.commit.id=0123456789abcdef0123456789abcdef01234567
git.commit.time=2026-10-01T07:30:00+0000
```

Values in this example are **illustrative data**, not an actual project commit. Many plugins also record abbreviated commit IDs, tags, build user, build host, or remote URL; control which fields enter the artifact.

Spring Boot 3.5 auto-configures `GitProperties` if `git.properties` is on the classpath. `GitInfoContributor` exposes only a small subset—such as branch, commit ID, and commit time—by default (when present).

### 8.2. Maven Git Commit ID plugin

If a project inherits `spring-boot-starter-parent`, Spring Boot 3.5 docs state that the parent already manages the Git Commit ID Maven Plugin configuration. To enable Git metadata generation, **add the plugin inside `<build><plugins>` in the example POM**:

```xml
<plugin>
    <groupId>io.github.git-commit-id</groupId>
    <artifactId>git-commit-id-maven-plugin</artifactId>
</plugin>
```

This is an **additional plugin**, not a `<dependencies>` entry and not a complete POM. The Boot parent supplies the default version/config; if using another corporate parent, declare the version and execution generating `git.properties` per plugin docs. The output typically lands at:

```text
target/classes/git.properties
```

**No `.git` directory or missing commit info?** Many CI setups check out from source archives, shallow clones/detached HEAD, or snapshots lacking full Git metadata; configure the plugin accordingly or pass revision info from CI rather than guessing a commit. After adding the plugin, run a **fresh build** and inspect the generated file instead of merely checking workspace Git history.

### 8.3. Gradle Git Properties plugin

In the `plugins { ... }` block of Section 7's `build.gradle`, add:

```groovy
id 'com.gorylenko.gradle-git-properties' version '2.4.1'
```

If using Kotlin DSL:

```kotlin
id("com.gorylenko.gradle-git-properties") version "2.4.1"
```

This version is **used as an example in Spring Boot 3.5 documentation**, not a claim of the latest version at all times. The plugin provides a task generating `git.properties` during builds, typically `generateGitProperties`; check `./gradlew tasks --all` and task logs for your version. Spring Boot will read the file once its output is wired properly onto the runtime classpath.

In multi-module repositories, only modules with the required plugin/config generate the file. If root and submodules point to different Git directories or build from source archives, inspect plugin configuration rather than assuming `git.properties` appears in every module.

## 9. Actuator /info: contributor, endpoint, and exposure are three separate decisions

### 9.1. Built-in contributors in Spring Boot 3.5

| Contributor | Creation condition | Default in 3.5 |
|---|---|---|
| `BuildInfoContributor` | `META-INF/build-info.properties` → `BuildProperties` | **Enabled** when metadata exists |
| `GitInfoContributor` | `git.properties` → `GitProperties` | **Enabled** when metadata exists |
| `EnvironmentInfoContributor` | Spring `info.*` properties | **Disabled** by default |
| `JavaInfoContributor` | Running JVM | **Disabled** by default |
| `OsInfoContributor` | Operating system | **Disabled** by default |
| `ProcessInfoContributor` | Process runtime | **Disabled** by default |

Example when wanting only build and Git metadata:

```properties
management.endpoints.web.exposure.include=health,info

# Optional, since both contributors are enabled by default:
management.info.build.enabled=true
management.info.git.enabled=true
```

This **illustrates the mechanism**. Section 5's source already includes the exposure line; you do not need both `true` lines just to force file generation, because contributors **never generate metadata files**.

To add manual information via Spring Environment:

```properties
management.info.env.enabled=true
info.app.owner=training
info.app.runtime=java17
```

When the `env` contributor is enabled, `info.*` properties are published at the endpoint; **never place secrets** under `info.*`. If you only add `info.app.owner` without enabling `management.info.env.enabled=true`, by Boot 3.5 defaults, the response will **not** include that section.

### 9.2. Valid example JSON

After a clean Maven/Gradle build and launching the executable JAR:

```bash
curl -s http://localhost:8080/actuator/info
```

An **illustrative response when only build-info exists and `git.properties` is absent**:

```json
{
  "build": {
    "artifact": "metadata-demo",
    "name": "Metadata Demo",
    "group": "com.example",
    "version": "0.1.0-SNAPSHOT",
    "time": "2026-10-01T07:30:00Z"
  }
}
```

The timestamp is illustrative only; it will differ or be absent if `time=off`/`excludes=['time']` is configured. JSON field order is also not guaranteed. Gradle's `name` field may default from the project name instead of `description`; do not force Maven and Gradle outputs to have identical `build.name` unless configured identically.

If you add a Git plugin and valid file, the response can additionally include:

```json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": "0123456",
      "time": "2026-10-01T07:30:00Z"
    }
  }
}
```

This is an **illustrative `git` section**, not a mandatory second JSON response. `git.commit.id` may be abbreviated in default mode; the branch may vary by CI environment. Check `git rev-parse HEAD` in the build workspace and compare against the file in the JAR; do not jump to wrong conclusions just because the endpoint displays a short ID.

### 9.3. Why can GET /actuator/info return 404 by default?

In Spring Boot 3.5, **only `health` is exposed over HTTP by default**. Even when both `BuildProperties` and `BuildInfoContributor` exist, unless `info` is added to `management.endpoints.web.exposure.include`, the endpoint is not exposed over HTTP.

With Spring Security (if added to the project), you may get `401 Unauthorized` or `403 Forbidden` depending on authentication/authorization. These statuses are completely distinct from `404` caused by non-exposure or a disabled endpoint. If your team exposes `info` for internal systems, configure dedicated security (e.g., an appropriate role), firewall, or API gateway, and keep sensitive details out of the response.

**Do not set `management.endpoints.web.exposure.include=*` in production just to resolve a 404**; expose only required endpoints and enforce access control.

## 10. Inspecting metadata directly in archives using JDK and ZIP tools

### 10.1. Listing archive entries

Maven:

```bash
./mvnw clean package
jar tf target/metadata-demo-0.1.0-SNAPSHOT.jar
```

Gradle:

```bash
./gradlew clean bootJar
jar tf build/libs/metadata-demo-0.1.0-SNAPSHOT.jar
```

Look for these paths:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/META-INF/build-info.properties
BOOT-INF/classes/git.properties                    (if Git plugin is present)
BOOT-INF/classes/com/example/metadata/MetadataApplication.class
```

**Do not confuse a plain JAR with `bootJar`**. Some Gradle builds produce both `metadata-demo-...-plain.jar` and an executable JAR; only the executable JAR has the `BOOT-INF` layout above. In Maven, `repackage` replaces the main artifact while keeping the original file with a different suffix depending on plugin config. Always pick the exact artifact CI publishes/deploys.

### 10.2. Reading contents with unzip

On Linux/macOS or environments with `unzip`:

```bash
# Use the exact file generated by Maven.
unzip -p target/metadata-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
unzip -p target/metadata-demo-0.1.0-SNAPSHOT.jar \
    BOOT-INF/classes/META-INF/build-info.properties

# If git.properties exists:
unzip -p target/metadata-demo-0.1.0-SNAPSHOT.jar \
    BOOT-INF/classes/git.properties
```

For Gradle, change the file path to `build/libs/metadata-demo-0.1.0-SNAPSHOT.jar`. `unzip -p` reads an entry's **contents** without extracting the whole archive. On Windows, use a ZIP tool or the Java `JarFile` program in Section 11 to avoid depending on `unzip`.

Example build-info (sample file contents):

```properties
build.artifact=metadata-demo
build.group=com.example
build.name=Metadata Demo
build.version=0.1.0-SNAPSHOT
build.time=2026-10-01T07:30:00Z
```

Do not expect Maven and Gradle to emit identical key ordering or timestamps. If a Maven/Gradle build excludes `build.time`, that field's absence is **intentional**, not an error.

### 10.3. Inspecting before starting the application

You can verify metadata **without launching** Spring Boot via `jar tf`/`unzip -p`. This is especially useful in CI to validate artifacts prior to publishing. Still, checking file presence does not prove `/actuator/info` is exposed or properly secured; runtime requires a separate smoke test.

## 11. Standalone Java 17 tool to inspect JAR/WAR manifests and metadata

If `unzip` is unavailable, use the Java Standard Library and JDK 17. Create **`InspectBootArchive.java`** in a standalone directory outside the app source:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Properties;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class InspectBootArchive {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java InspectBootArchive <archive.jar-or-war>");
            System.exit(2);
        }

        try (JarFile archive = new JarFile(args[0])) {
            Manifest manifest = archive.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Missing manifest");
            }

            System.out.println("Main-Class="
                    + manifest.getMainAttributes().getValue("Main-Class"));
            System.out.println("Start-Class="
                    + manifest.getMainAttributes().getValue("Start-Class"));

            // Check both executable JAR and executable WAR layouts.
            show(archive, "BOOT-INF/classes/META-INF/build-info.properties");
            show(archive, "BOOT-INF/classes/git.properties");
            show(archive, "WEB-INF/classes/META-INF/build-info.properties");
            show(archive, "WEB-INF/classes/git.properties");
        }
    }

    private static void show(JarFile archive, String name)
            throws IOException {
        JarEntry entry = archive.getJarEntry(name);
        if (entry == null) {
            System.out.println(name + " -> absent");
            return;
        }

        System.out.println(name + " -> present");
        Properties properties = new Properties();
        try (InputStream stream = archive.getInputStream(entry)) {
            properties.load(stream);
        }
        List<String> keys = new ArrayList<>(properties.stringPropertyNames());
        Collections.sort(keys);
        for (String key : keys) {
            System.out.println("  " + key + "=" + properties.getProperty(key));
        }
    }
}
```

Compile and run (example with the Maven artifact):

```bash
javac --release 17 -encoding UTF-8 InspectBootArchive.java
java InspectBootArchive target/metadata-demo-0.1.0-SNAPSHOT.jar
```

This program **needs no Spring dependencies**, using only `java.util.jar` and `java.util.Properties`. If Section 6's Maven artifact has build-info and **no Git plugin yet**, the key expected status lines are:

```text
Main-Class=org.springframework.boot.loader.launch.JarLauncher
Start-Class=com.example.metadata.MetadataApplication
BOOT-INF/classes/META-INF/build-info.properties -> present
BOOT-INF/classes/git.properties -> absent
WEB-INF/classes/META-INF/build-info.properties -> absent
WEB-INF/classes/git.properties -> absent
```

**Note:** between those status lines, the program also prints `build.artifact=...`, `build.group=...`, and other properties right after `present`; the snippet above shows **selected lines** highlighting locations rather than verbatim consecutive stdout. With an executable WAR, `WEB-INF/classes` switches to `present` and `BOOT-INF/classes` becomes `absent`.

`Properties.load(InputStream)` uses ISO-8859-1 and Unicode escapes per Java properties conventions; if metadata contains Unicode written under another convention, read Java properties using the matching encoding. For the ASCII keys/values in this example, the program prints accurate output.

## 12. Runtime testing: cross-checking the artifact against /actuator/info

### 12.1. Layer-by-layer verification workflow

**Layer 1 — build output**: confirm the task/goal ran and the file appears under the application module's classes/resources output.

**Layer 2 — executable artifact**: inspect `BOOT-INF/classes/META-INF/build-info.properties` and `git.properties` (if any) in the JAR; for WAR, inspect `WEB-INF/classes`.

**Layer 3 — startup**: run `java -jar` on the **exact inspected file**; avoid letting an IDE or `bootRun` launch separate classes. If `VersionController` injects `BuildProperties` successfully and returns artifact/version, the bean is present.

**Layer 4 — Actuator endpoint**: send `GET /actuator/info` to the right port/management base path with valid credentials; compare `build.artifact` and `build.version` against the packaged file.

**Layer 5 — provenance**: if Git metadata exists, compare the commit ID against the CI build revision/source tag. When CI uses detached HEAD, the branch name may differ from the merged source branch, making commit ID the stronger provenance signal.

**Never** run `git rev-parse HEAD` on your laptop today to verify a JAR built yesterday on a different CI runner; compare against the revision CI checked out **at artifact build time**.

### 12.2. HTTP statuses and responses to distinguish

| Result when calling /actuator/info | Possible explanation | Next check |
|---|---|---|
| `200`, JSON has `build` | Endpoint exposed; build contributor has metadata | Match fields against the right version's JAR |
| `200`, JSON has `build` but no `git` | Missing `git.properties`, Git contributor disabled, or invalid metadata | Inspect `git.properties`, Git plugin, and `management.info.git.enabled` |
| `200`, JSON `{}` | Endpoint active, yet no contributor supplied info | Inspect classpath metadata, `management.info.*.enabled`, and Spring context |
| `404` | Endpoint not exposed/enabled or wrong URL/path/port | Check `management.endpoints.web.exposure.include` and endpoint enablement |
| `401`/`403` | Spring Security or gateway blocking access | Supply valid authentication/authorization; do not expose all of actuator |
| Connection refused | Process not running, wrong port/container routing | Check app logs, `server.port`, `management.server.port` |
| `200` yet stale version | Running old artifact, old container image, CI skipped rebuild, or wrong deploy | Compare manifest/JAR checksum, image digest, and internal build-info |
| Unexpected `build.time` | Plugin used build instant or `outputTimestamp`; or time was excluded | Inspect task/goal config; do not confuse with deploy time |

### 12.3. Build metadata is not runtime metadata

- `build.version`: version at **build time**; does not change while the JVM runs.
- `build.time`: build timestamp/plugin value, **not** deployment time or JVM startup time.
- `git.commit.time`: commit timestamp per Git metadata, **not** the running image/container timestamp.
- `java.version` or `os.name` from **runtime contributors**: details of the JVM/OS the app is **currently running on**, if those contributors are enabled.

When investigating incidents, record **application version, Git commit, artifact checksum/image digest, deployment ID, and runtime environment** together. A `build.version` alone can collide when multiple different `SNAPSHOT` builds share the same name.

## 13. Build reproducibility: build.time, Git, and artifact checksums

### 13.1. Timestamps can make builds diverge

If `build.time` is freshly generated each run, two builds from identical sources/dependencies can yield different bytes. For Gradle, Spring Boot 3.5 docs note that `bootBuildInfo` uses the current build time by default, keeping the task from being up-to-date and reducing artifact reproducibility. If your organization prioritizes reproducible builds, consider excluding `time` or supplying a stable timestamp from the build system.

For Maven, the `build-info` goal has a `time` parameter tied to `project.build.outputTimestamp`; you can set `<time>off</time>` to omit the time field. If other plugins also emit timestamps, archive entry times, generated files, or unstable resource filtering, omitting `build.time` alone is **not enough** to guarantee byte-for-byte reproducibility.

### 13.2. Git properties and reproducibility

If a Git plugin emits varying build user, host, branch, or build time, metadata can differ even for the same commit. Consider restricting output to **commit ID and commit time**/only truly needed fields. CI shallow clones may not retrieve tags or full branch info.

Keeping the Git commit ID in metadata aids traceability, though it is **not cryptographic signing proof**. For strong provenance, combine artifact checksums, SBOMs, signatures, and pipeline attestations—mechanisms separate from Actuator info.

### 13.3. Do not confuse source hash with artifact hash

`git.commit.id` is the hash of Git commit/tree metadata, not the SHA-256 of the executable JAR. One commit can yield multiple distinct artifacts if dependencies, plugins, JDKs, or environment inputs change. When an organization must verify "the exact approved file," the pipeline should record the artifact's checksum or image digest after the build.

Never compute a JAR's checksum and write it back into **that same JAR** without a deterministic scheme: modifying the file alters its checksum, creating a loop. Store artifact digests in an artifact repository or external release metadata.

## 14. Security: /actuator/info must not become a system-disclosure leak

Even when `/actuator/info` holds only a few fields, it still lets readers determine product version, commit, branch, and release timestamp. In production, decide **who is allowed access** per organizational policy.

- Expose only needed endpoints: `management.endpoints.web.exposure.include=health,info`, or `health` alone if `info` is unused.
- With Spring Security, protect `info` with proper authentication/authorization; when defining a custom `SecurityFilterChain`, re-evaluate all actuator rules since default auto-configuration may back off.
- Place Actuator behind network policies, firewalls, service meshes, or internal gateways where appropriate; never treat URL obscurity as security.
- Never configure `management.info.git.mode=full` in public environments if Git metadata contains remote URLs, build users, or internal branch names.
- Never place tokens, secrets, internal endpoint URLs, credentials, or customer data into `build-info.properties`, `git.properties`, `info.*`, or custom `InfoContributor` beans.
- Use field allowlists to control exposed data. Do not rely solely on Actuator sanitization applied to **other endpoints** like `env`/`configprops`.

**Distinction:** a field suppressed in `GitInfoContributor` may still **remain intact inside `git.properties` in the JAR** if the plugin generated it. Archive read access and HTTP endpoint access are two separate exposure surfaces. Minimizing generated data at build time protects both.

## 15. Multi-module setups: metadata belongs on the application module

Consider a Maven reactor or Gradle multi-project build:

```text
platform/
├── shared-domain/          (library JAR)
├── orders-api/             (Spring Boot executable JAR)
└── reporting-worker/       (Spring Boot executable JAR)
```

Each module can have its own coordinates/version and role. If a root aggregator configures a `build-info` plugin execution inherited by **every module**, shared libraries also emit `META-INF/build-info.properties` and get bundled into the app. That places **multiple `build-info.properties` files at the same path** on the classpath, potentially causing Spring to pick a file that is not the executable app's metadata.

Principles:

1. Generate build-info **in the module producing the executable artifact**, typically `orders-api`/`reporting-worker`.
2. In Maven parents, manage plugin versions in `pluginManagement` if needed while binding the goal only in app modules; check `inherited` on executions.
3. In Gradle, apply `springBoot { buildInfo() }` in app modules rather than turning it on across libraries unnecessarily.
4. Check that dependency JARs bundled into `BOOT-INF/lib` do not carry colliding metadata resources causing ambiguity.
5. Have CI build target modules and inspect the **exact archive**; e.g. Maven `-pl :orders-api -am package`, or Gradle `:orders-api:bootJar`.
6. When multiple apps share a parent and version, do not equate the root's `build.name` with the app's `build.artifact`; inspect fields in each archive.

**Caveat:** this is a classpath design risk rather than a claim that two metadata resources always break every project. Still, production traceability metadata must be **unambiguous**, so avoid duplicate `build-info` resources between applications and libraries.

## 16. Controlled experiments: missing, valid, and disabled metadata

Use the Section 5 project with **one build tool**.

### Run A — With build-info, no Git plugin

1. Keep the Maven `build-info` goal or Gradle `springBoot.buildInfo()`.
2. Build a fresh `package`/`bootJar` and check `META-INF/build-info.properties` inside the archive.
3. Run the executable JAR and call `/actuator/info`.
4. Expect `build.artifact` and `build.version`; `git` is absent because `git.properties` was not generated.
5. The `/version` controller also returns artifact/version from `BuildProperties`.

### Run B — Add a Git plugin

1. Add the Git Commit ID Maven Plugin or Gradle Git Properties Plugin as in Section 8.
2. Rebuild inside a checkout with a valid `.git`.
3. Verify `git.properties` sits at the classpath root of the executable archive.
4. Restart the **new JAR** and call `/actuator/info`. Expect a `git` section if the plugin generated data and the Git contributor is enabled.
5. Compare the commit ID against the revision CI checked out.

### Run C — Metadata present, info not exposed

1. Keep metadata files intact.
2. Remove `info` from `management.endpoints.web.exposure.include`, or set `management.endpoints.web.exposure.include=health`.
3. Restart the app and call `/actuator/info`; per default config, the endpoint is not exposed over HTTP.
4. Restore `health,info` after the experiment. Conclusion: the file and contributor are not enough if HTTP exposure is disabled.

### Run D — Disable build contributor while keeping the file

In `application.properties`, add:

```properties
management.info.build.enabled=false
```

Restart the app. `BuildProperties` still exists because the build-info file is valid; however, `BuildInfoContributor` is disabled, so `/actuator/info` omits the `build` section contributed by it. `/version` can still return the version from `BuildProperties`. **Conclusion:** the metadata bean and HTTP info presentation are two distinct layers.

After testing, remove `management.info.build.enabled=false` if you want build info published. Do not leave experimental toggles in production accidentally.

### Run E — Omit build-info generation

On a **copy or test branch**, remove the Maven `build-info` execution or `springBoot { buildInfo() }`, run `clean`, and rebuild. `build-info.properties` will not be generated by those tasks. Because `VersionController` uses required `BuildProperties` injection, the app may **fail to start**, or `BuildMetadataTest` fails due to a missing bean. This intentional failure illustrates the app's dependency on build metadata.

Restore the build-info configuration and rebuild. Do not blame the plugin if an old file lingered in class outputs because `clean` was skipped; that is why this experiment uses a clean build.

## 17. Quick troubleshooting table

| Symptom | Common cause | Resolution |
|---|---|---|
| `jar tf` lacks `BOOT-INF/classes/META-INF/build-info.properties` | Generating goal/task did not run, or wrong JAR packaged | Check Maven `build-info` execution / Gradle `bootBuildInfo` and exact artifact |
| `build-info` in `target/classes` yet missing from JAR | Wrong repackage/resource layout, stale archive, or file excluded | Clean build, inspect `BOOT-INF/classes`, check packaging |
| `/actuator/info` returns 404 | `info` not exposed over HTTP or wrong base path/port | Set `management.endpoints.web.exposure.include=health,info` and verify management port/path |
| `/actuator/info` returns 401/403 | Spring Security/gateway restriction | Provide proper credentials/roles; do not disable security |
| HTTP 200 yet `{}` | No active contributors or contributors disabled | Check classpath files and `management.info.*.enabled` |
| `build` present yet `git` missing | `git.properties` not generated or Git contributor disabled | Enable Git plugin, verify file and `management.info.git.enabled` |
| `build.version` shows parent/library version | Metadata from wrong module or running wrong artifact | Configure generation on app module and inspect the right artifact |
| `build.time` changes on every build | Plugin uses build timestamp | Consider omitting `time` if repeatability is needed |
| `build.time` absent | Configured Maven `time=off` or Gradle `excludes=['time']` | Confirm policy; do not assume every absence is a bug |
| `git.branch` is `HEAD` or empty | CI detached HEAD/shallow checkout | Rely on commit ID and CI revision info |
| Endpoint Git commit differs from local `HEAD` | Built from another commit or stale artifact | Compare against build pipeline's source revision rather than local workspace blindly |
| Cannot inject `BuildProperties` | `build-info` file missing on classpath or auto-config altered | Check JAR entry, task execution, and test runtime classpath |
| `info.app.*` not displayed | `EnvironmentInfoContributor` disabled by default | Set `management.info.env.enabled=true` if data is safe |
| Artifact Git metadata contains secrets | Git plugin exported too many fields | Restrict with an allowlist, rebuild, and rotate leaked credentials |
| `jar tf` inspected plain JAR instead of `bootJar` | Multiple output files or classifiers | Pick the right executable archive in `build/libs` or `target` |
| Gradle re-processes resources on every test run | Changing `build.time` keeps `bootBuildInfo` out-of-date | Consider excluding `time` per plugin docs |
| Deployed container runs old version despite fresh CI build | Wrong image digest/tag/rollout | Check registry digest, deployment revision, and archive metadata |

Helper commands (use only the tools belonging to your actual project):

```bash
# Maven
./mvnw help:effective-pom
./mvnw clean verify

# Gradle
./gradlew tasks --all
./gradlew clean bootJar --info

# Inspect artifact manifest and classpath entries
jar tf target/metadata-demo-0.1.0-SNAPSHOT.jar

# While the app is running
curl -i http://localhost:8080/actuator/info
```

The `jar tf` command above targets the Maven artifact; for Gradle builds, use `build/libs/...jar`. Never run against a nonexistent file path and conclude metadata is missing.

## 18. CI/CD pipeline for pre-release metadata verification

A pipeline can establish a **quality gate** for metadata just like tests and coverage:

1. **Check out an explicit source revision** using pinned JDK + Maven/Gradle Wrapper.
2. **Build the artifact from source**: Maven `clean verify` or Gradle `clean test bootJar`/`build` as appropriate.
3. **Inspect the archive** with `jar tf`/`JarFile`: confirm `META-INF/MANIFEST.MF`, build-info in place, and Git info if required.
4. **Cross-check build coordinates** against the artifact repository/release metadata; do not merely check file existence.
5. **Compare the archive's Git commit** against the revision CI checked out if the Git plugin is enabled. Watch for abbreviated SHAs vs. full SHAs.
6. **Launch the exact artifact** in a test environment, call `/actuator/info` through an authorized path, and verify the response.
7. **Store checksum/image digest** with the release record; do not confuse Git commit ID with artifact digest.
8. **Publish/deploy the exact verified file**, avoiding rebuilds that introduce new timestamps/dependencies without retesting.
9. **Enforce security policy**: expose only approved fields and never leak credentials.
10. **Post-deploy verification**: runtime endpoints and artifact bytes on the target environment must match the release record.

Example of two sequential steps (Maven):

```bash
./mvnw -B clean verify
java InspectBootArchive target/metadata-demo-0.1.0-SNAPSHOT.jar
```

The second step assumes the `InspectBootArchive.java` helper from Section 11 is compiled, and requires **checking the output** rather than ignoring stdout. In real CI, turn this step into a script asserting keys and values with a non-zero exit code if required metadata is missing. Across different shells/PowerShell, adapt parsing accordingly and **never print secrets to public logs**.

**Important:** `/actuator/info` is not self-sufficient proof of supply-chain security. It is a convenient operational diagnostics source; artifact checksums/signing, SBOMs, and attestations must be managed separately if required by your organization.

## 19. Summary: avoiding three common misconceptions

**Misconception 1: "Having the version in the JAR filename means Actuator knows it."** False. The archive name is just a filename. Spring Boot's build contributor reads `META-INF/build-info.properties` or a custom contributor; it does not parse versions from filename suffixes.

**Misconception 2: "Just adding Actuator makes the Git commit appear."** False. Actuator needs `git.properties` on the classpath, produced by a Git plugin or build step. Without that file, `GitProperties`/`GitInfoContributor` have nothing to expose.

**Misconception 3: "Since metadata is in the archive, `/actuator/info` is definitely reachable."** False. You need the Actuator dependency, enabled endpoint/contributors, HTTP exposure, and security rules. A `BuildProperties` bean can exist even when `/actuator/info` returns 404 or the `build` contributor is disabled.

### Acceptance checklist

- [ ] Correct Maven/Gradle project and Java/Spring Boot versions.
- [ ] Maven `build-info` goal or Gradle `bootBuildInfo` task actually executes.
- [ ] `META-INF/build-info.properties` is on the application module's runtime classpath.
- [ ] `BOOT-INF/classes/META-INF/build-info.properties` or `WEB-INF/classes/META-INF/build-info.properties` is inside the deployed artifact.
- [ ] Manifest `Main-Class`/`Start-Class` match executable layout.
- [ ] `build.artifact`, `build.group`, and `build.version` reflect the application module, not a parent or library.
- [ ] `git.properties` is required only when Git provenance is needed; if required, it holds the right revision.
- [ ] `BuildProperties`/`GitProperties` are auto-configured by Spring without unintended overrides.
- [ ] Actuator `info` is intentionally exposed over HTTP with security-appropriate response statuses.
- [ ] `build`/`git` contributors are enabled when needed, and `env` only when data is controlled.
- [ ] `build.time` is kept or excluded per reproducibility policy.
- [ ] No secrets or private URLs exist inside archive metadata or info JSON.
- [ ] CI matches archive contents, Git source revision, and release records before deployment.
- [ ] Smoke tests run against the **exact built/published artifact file**.

### Official documentation

- [Spring Boot 3.5 — Actuator Endpoints and Application Information](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — How-to Build: Generate Build and Git Information](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Spring Boot 3.5 — Maven Plugin: Integrating with Actuator / build-info](https://docs.spring.io/spring-boot/3.5/maven-plugin/build-info.html)
- [Spring Boot 3.5 — Gradle Plugin: Integrating with Actuator / bootBuildInfo](https://docs.spring.io/spring-boot/3.5/gradle-plugin/integrating-with-actuator.html)
- [Spring Boot 3.5 — Executable Jar Structure](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot — Actuator info REST API](https://docs.spring.io/spring-boot/api/rest/actuator/info.html)
- [Git Commit Id Maven Plugin — Repository/Documentation](https://github.com/git-commit-id/git-commit-id-maven-plugin)

**Remember:** verify along the chain **build-info/git-info generated → file present in executable archive → Spring creates BuildProperties/GitProperties → Actuator contributor publishes → endpoint exposed and authorized**. If any link in the chain breaks, `/actuator/info` may fail to reflect the build you think is running.