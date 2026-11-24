# Customizing Build Properties and Managing Build Time in Spring Boot

## 1. Objectives

A Spring Boot release should answer at least three questions: **which version is this**, **which source was it built from**, and **what does the recorded timestamp mean**. Spring Boot supports standard metadata in `META-INF/build-info.properties`. The Gradle Spring Boot Plugin provides the `bootBuildInfo` task; the Maven Spring Boot Plugin provides the `build-info` goal. When this file is on the classpath, the application can read it through `BuildProperties`, and Spring Boot Actuator can expose it at `/actuator/info` if configured and exposed appropriately.

However, `build.time` is normally generated from **when the build executes**. Keeping a constantly changing value can cause the same source revision to produce artifacts with different contents and force Gradle to re-run unnecessary tasks. Therefore, it is important to distinguish **version-identifying metadata** from **operations/deployment timestamps**, and choose a clear timestamp policy.

After this lesson, you will:

1. Understand the standard keys `build.group`, `build.artifact`, `build.name`, `build.version`, `build.time`, and additional keys.
2. Configure Groovy DSL/Kotlin DSL to generate metadata, override properties, and **exclude `build.time`** when optimizing reproducibility.
3. Configure `spring-boot:build-info` in Maven, add properties, and control the timestamp with `<time>off</time>` or an ISO-8601 value.
4. Build a Java 17/Spring Boot program that reads real `BuildProperties` and prints deterministic output.
5. Inspect the `bootBuildInfo` task, `META-INF/build-info.properties`, the Boot executable JAR, and the differences between build time, JVM start time, Git commit time, release time, and deployment time.
6. Understand the relationship between variable timestamps, Gradle `UP-TO-DATE`, build cache, reproducible archives, and CI/CD.
7. Avoid writing secrets, host paths, access tokens, or non-public metadata into an artifact resource.

**Scope:** examples use Spring Boot 3.3.13, Java 17, and the corresponding Gradle Spring Boot Plugin or Spring Boot Maven Plugin. This version baseline keeps the examples consistent and does not imply the latest release. Use the wrapper/versions accepted by your real project.

## 2. What is build metadata?

Build metadata describes the **produced artifact** rather than the application's live runtime configuration. It is typically generated at build time and stored inside the artifact for post-release lookup.

Example file at classpath `META-INF/build-info.properties`:

~~~properties
build.artifact=metadata-demo
build.group=com.example
build.name=metadata-demo
build.version=1.0.0
build.channel=training
build.revision=manual-local
~~~

This is an **example with build time excluded**, so `build.time` is absent. The line order written by the plugin may vary; a Java Properties file does not require the order shown above.

| Key in file | Meaning | Common default source |
| --- | --- | --- |
| `build.artifact` | Identifying artifact name | Gradle: archive base name of `bootJar`/`bootWar`; Maven: artifactId |
| `build.group` | Owning group/coordinate | Gradle `project.group`; Maven `groupId` |
| `build.name` | Display name | Gradle project name; Maven `name` or derived value |
| `build.version` | Artifact version | Gradle `project.version`; Maven `version` |
| `build.time` | Instant recorded in metadata at build time | Plugin-defined timestamp, can be excluded or fixed |
| `build.channel`, `build.revision` | Extended properties | Declared by the build team |

Extended properties receive the **`build.` prefix** when the plugin generates the file. For example, writing key `channel` in Gradle `additional` produces `build.channel` in the file, while `BuildProperties.get("channel")` reads the value by its logical name `channel`.

**Metadata is not an audit database:** if you need verifiable proof of approvers, provenance, artifact signatures, or SBOMs, use your release/CI system and proper signing/attestation mechanisms rather than simply adding self-declared strings to build-info.

## 3. Distinguishing four commonly confused layers of "properties"

The phrase "build properties" can refer to completely different things.

| Concept | Where configured/read | Effect |
| --- | --- | --- |
| Gradle project properties | `gradle.properties`, `-P...`, Providers API | Inputs to build scripts/tasks |
| Spring Boot build-info properties | `META-INF/build-info.properties`, `BuildProperties` | Metadata packaged into classpath/artifact |
| Spring runtime configuration | `application.properties`, environment, system properties, Config Server | Application behavior at startup/runtime |
| CI/release metadata | Git revision, CI run ID, signed provenance, deployment records | Identifies source/approvals/deployments |

Example:

~~~properties
# gradle.properties
org.gradle.caching=true
~~~

`org.gradle.caching` controls Gradle's build cache; it **does not become** `build.org.gradle.caching` inside the Boot JAR. Conversely:

~~~properties
# src/main/resources/application.properties
app.feature.enabled=true
~~~

is application configuration; it **does not automatically create** `BuildProperties`. To obtain Boot build metadata, you need `springBoot { buildInfo(...) }` or the corresponding Maven goal.

Likewise, do not treat `-Pversion=...`, `-Dspring.profiles.active=...`, and `build.version` as the same mechanism. Project build version must be defined in an authoritative configuration source, which metadata then reflects or overrides by design.

## 4. How the Spring Boot Gradle Plugin generates metadata

When applying the Spring Boot Gradle Plugin with the Java plugin, you can enable:

~~~groovy
springBoot {
    buildInfo()
}
~~~

This registers the `bootBuildInfo` task. In Spring Boot 3.3, the task is wired into the `classes` lifecycle when the Java plugin is present; the default output is `META-INF/build-info.properties` in the main source set's resources output, typically:

~~~text
build/resources/main/META-INF/build-info.properties
~~~

After `bootJar`, the file typically lives inside the executable archive under:

~~~text
BOOT-INF/classes/META-INF/build-info.properties
~~~

**Key points to remember:**

- Applying the Spring Boot plugin alone does not automatically generate `build-info.properties`: you must **enable `buildInfo`**.
- This file belongs to the main runtime classpath, unlike `src/test/resources`.
- Gradle `bootJar` packages main classes/resources; metadata is bundled with the application without manual shell copying.
- `bootBuildInfo` is not `bootJar`; the former generates the metadata file, while the latter builds the executable archive.
- Do not edit the generated file in `build/resources/main` by hand: `clean` or a subsequent build will overwrite it from the DSL.

### 4.1. Which properties can be customized?

The Spring Boot Gradle plugin lets you customize standard keys `artifact`, `group`, `name`, `version`, along with `additional`. **Groovy fragment** example:

~~~groovy
springBoot {
    buildInfo {
        properties {
            artifact = 'public-service'
            group = 'com.example.services'
            name = 'Public Service'
            version = '2.3.4'
            additional = [
                'channel': 'release',
                'schema': 'v1'
            ]
        }
    }
}
~~~

This is a **build-info metadata fragment**. It alters the values written into the file and read by Spring Boot; it **does not automatically change** `project.group`, `project.version`, the `bootJar` output filename, or publishing coordinates. If metadata version is `2.3.4` while Gradle project version remains `1.0.0`, the release pipeline may publish conflicting information.

Therefore, in most projects, **keep default group/artifact/version derived from the project**; only override them when there is an explicit contract. Extended properties are better suited for supplemental details like revision, release channel, and schema version.

## 5. Gradle Groovy DSL — complete project, metadata without build.time

We will build a Java 17 console application named `metadata-demo`. The primary version excludes `build.time` for more stable build output; afterwards we will test re-enabling time to observe the trade-off.

Structure:

~~~text
metadata-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/com/example/metadata/MetadataApplication.java
│   └── test/java/com/example/metadata/MetadataApplicationTest.java
└── build/                            # Created by Gradle during build
~~~

If using Groovy DSL, `settings.gradle`:

~~~groovy
rootProject.name = 'metadata-demo'
~~~

Complete `build.gradle`:

~~~groovy
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            additional = [
                'channel': 'training',
                'revision': 'manual-local'
            ]
        }
    }
}
~~~

**Key detail:** `excludes = ['time']` is the official Spring Boot 3.3 DSL to **omit `build.time`**. It is not a command to delete a property from an existing file; the plugin generates a fresh file from the configuration. `additional` adds two stable values; they become `build.channel` and `build.revision`.

Because we do not manually hardcode `artifact`/`group`/`version` here, metadata defaults from `rootProject.name`, `group`, and `version`. If you change `rootProject.name` or `version`, expected output and archive name change accordingly.

**Environment requirements:** a Gradle wrapper or compatible Gradle CLI and a JDK 17 toolchain available or provisioned properly. `settings.gradle` and `build.gradle` do not create `gradlew` by themselves. When generating via Spring Initializr, the wrapper is typically included; on Windows use `.\gradlew.bat`.

## 6. Gradle Kotlin DSL — equivalent configuration

If your repository uses Kotlin DSL, **choose this pair of files instead of the Groovy pair**; do not leave both `build.gradle` and `build.gradle.kts` as if they were two sequential scripts.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "metadata-demo"
~~~

Complete `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
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
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

springBoot {
    buildInfo {
        excludes.set(setOf("time"))
        properties {
            additional.set(
                mapOf(
                    "channel" to "training",
                    "revision" to "manual-local"
                )
            )
        }
    }
}
~~~

Key differences from Groovy:

- `excludes` is a Gradle `SetProperty`, so Kotlin uses `excludes.set(setOf("time"))`.
- `additional` is a `MapProperty`, so Kotlin uses `additional.set(mapOf(...))`.
- You do not manually register a task named `bootBuildInfo`; the `springBoot.buildInfo` DSL does it.

**Verification point:** both DSL versions generate the same logical keys in `build-info.properties`, with `build.time` absent. Do not compare bytes between two different Gradle/JDK environments and conclude the DSL behaves differently; keep toolchains/dependencies aligned for a fair comparison.

## 7. Java 17: reading real metadata with BuildProperties

Create `src/main/java/com/example/metadata/MetadataApplication.java`:

~~~java
package com.example.metadata;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MetadataApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    CommandLineRunner reportMetadata(BuildProperties build) {
        return args -> {
            System.out.println("ARTIFACT=" + build.getArtifact());
            System.out.println("GROUP=" + build.getGroup());
            System.out.println("VERSION=" + build.getVersion());
            System.out.println("CHANNEL=" + build.get("channel"));
            System.out.println("REVISION=" + build.get("revision"));

            if (build.getTime() == null) {
                System.out.println("TIME=<absent>");
            } else {
                System.out.println("TIME=" + build.getTime());
            }
        };
    }
}
~~~

`BuildProperties` belongs to `org.springframework.boot.info.BuildProperties`. Spring Boot creates the bean from `META-INF/build-info.properties` when the file exists on the classpath. The class exposes `getArtifact()`, `getGroup()`, `getName()`, `getVersion()`, and `getTime()`; custom keys are read via `get("channel")`/`get("revision")`, **without the `build.` prefix**.

`getTime()` returns `java.time.Instant`, or `null` if no valid time property is present. Never call `build.getTime().toString()` unconditionally when metadata excludes time.

In this lesson, `spring-boot-starter` is enough—neither Actuator nor the Web starter is required just to inject `BuildProperties` from Spring Boot auto-configuration. If a project omits the `buildInfo` task yet injects the bean without a fallback, the application context may fail to start due to a missing `BuildProperties` bean; this signals that the build metadata resource was not generated or packaged.

### 7.1. JUnit test to enforce the metadata contract

Create `src/test/java/com/example/metadata/MetadataApplicationTest.java`:

~~~java
package com.example.metadata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringBootTest
class MetadataApplicationTest {

    @Autowired
    private BuildProperties build;

    @Test
    void buildMetadataHasExpectedValues() {
        assertEquals("metadata-demo", build.getArtifact());
        assertEquals("com.example", build.getGroup());
        assertEquals("1.0.0", build.getVersion());
        assertEquals("training", build.get("channel"));
        assertEquals("manual-local", build.get("revision"));
        assertNull(build.getTime());
    }
}
~~~

This test verifies that the file was generated and the bean holds the right values for the **exclude-time configuration**. If you later intentionally change version/channel or keep `build.time`, update the assertions accordingly; avoid hardcoding a static version in real release tests and forgetting to update it when bumping versions.

## 8. Running and verifying from task to executable JAR

Inside `metadata-demo` with a valid Gradle wrapper:

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew clean bootBuildInfo
./gradlew clean build
java -jar build/libs/metadata-demo-1.0.0.jar
~~~

`./gradlew clean bootBuildInfo` demonstrates the task directly; `./gradlew clean build` rebuilds completely and runs tests per the Java lifecycle. When a build only applies the Gradle Java plugin with no Java sources declared, tasks may report `NO-SOURCE`; however, this project has Java main/test sources so compiler and test tasks perform real work.

On Windows PowerShell, use `.\gradlew.bat` instead of `./gradlew`. When no wrapper is present, use a compatible installed Gradle or generate a wrapper per repository policy.

**The exact lines printed by the program** when running the executable JAR with the Section 5/6 config:

~~~text
ARTIFACT=metadata-demo
GROUP=com.example
VERSION=1.0.0
CHANNEL=training
REVISION=manual-local
TIME=<absent>
~~~

Spring Boot may print additional startup logs; the lines above are stdout from `CommandLineRunner`, not the entire terminal output. If you use a different main class, change group/version, or declare different metadata, the output changes according to your real config.

### 8.1. Locating the metadata file

In Gradle, inspect:

~~~text
build/resources/main/META-INF/build-info.properties
~~~

This is the usual task output in Spring Boot 3.3. If the task destination directory was customized, the path may differ. After `bootJar`:

~~~bash
jar tf build/libs/metadata-demo-1.0.0.jar
~~~

Look for entry:

~~~text
BOOT-INF/classes/META-INF/build-info.properties
~~~

Having the file in the JAR proves it was packaged; **it is not enough** to prove every value is accurate. To inspect its contents, use a ZIP tool such as `unzip` on Linux/macOS if available:

~~~bash
unzip -p build/libs/metadata-demo-1.0.0.jar \
  BOOT-INF/classes/META-INF/build-info.properties
~~~

If `unzip` is unavailable, extract the archive into a separate inspection directory using JDK `jar` and read the entry. Do not run `jar -xf` carelessly in the project root as it may create or overwrite files.

### 8.2. When verifying a fresh build

Do not just see that the file exists and assume it came from the current build run. To avoid mistaking a stale artifact:

- Run `clean` when you genuinely want to regenerate local outputs.
- Inspect the logs for `bootBuildInfo`, `processResources`, and `bootJar`.
- Verify the path matches the current module/version/classifier.
- Inspect property contents, not only the filename.
- Run the exact JAR you intend to publish using `java -jar`.
- If CI uses multiple modules, invoke the exact task path, e.g. `:api-service:bootJar` if an `api-service` module exists.

## 9. Problems with the default build.time

### 9.1. A changing instant alters output

With the simple configuration:

~~~groovy
springBoot {
    buildInfo()
}
~~~

the task generates default metadata including `build.time` set to the instant of the build. The file may contain a line like:

~~~properties
build.time=2026-11-09T02:00:00Z
~~~

**This is only an illustrative timestamp string**, not the expected time on a learner's machine. On another build, the instant changes even when Java sources, dependency versions, and group/version remain identical.

Consequences:

1. `build-info.properties` changes bytes.
2. Downstream tasks depending on resource outputs may have to re-run.
3. The final JAR archive may change checksums solely due to the timestamp.
4. Build caching and Gradle up-to-date checks lose effectiveness for related tasks.
5. Two people building the same commit can get different binaries with zero business logic changes.

Spring Boot 3.3 documentation notes that with the default time, `bootBuildInfo` is **not up-to-date** and its output changes constantly. Therefore, removing `time` directly improves build performance and repeatability, rather than merely changing how the info endpoint renders.

### 9.2. Policies to choose explicitly

| Policy | Build metadata | Pros | Trade-off |
| --- | --- | --- | --- |
| Record actual build time | Dynamic `build.time` present | Shows exact instant plugin ran | Changing outputs, cache/stability loss; same source can yield different bytes |
| Exclude build time | No `build.time` | More stable, helps repeatability | Cannot query `BuildProperties.getTime()` for build time |
| Record a meaningful fixed instant | Fixed `build.time` | Stable time metadata present | Must manage timestamp source and document what event it represents |

**No single choice fits every system.** For services requiring reproducible builds/supply-chain verification, omitting arbitrary timestamps usually makes sense. For pipelines that must audit **when a job actually ran**, store timestamps in CI deployment records, build run metadata, or signed provenance instead of mutating the binary every second.

### 9.3. Gradle 3.3 recommendation: `excludes` instead of legacy `time = null`

Per Spring Boot 3.3 DSL:

**Groovy fragment:**

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
springBoot {
    buildInfo {
        excludes.set(setOf("time"))
    }
}
~~~

This is the documented approach for the 3.3 line. Some older Spring Boot 2.x articles used `properties.time = null` to omit time; **do not copy legacy syntax** into a 3.3 project when the `excludes` API is available. Do not put conflicting fragments together in the same module.

### 9.4. "Omitting time" does not guarantee full binary reproducibility

Even once `build.time` disappears, the binary JAR can still change if:

- Source inputs or dependencies change.
- The Java compiler/toolchain or annotation processors produce non-deterministic output.
- Archive entries contain unstable timestamps, filesystem ordering, or absolute paths.
- Manifest, Git metadata, or custom resource processing writes varying timestamps.
- Code generators use `new Date()`, `Instant.now()`, random UUIDs, or network data without pinning inputs.
- Packaging/plugin/JVM/OS differences alter output.

**Reproducibility is a property of the entire build**, not a single property. Omitting `build.time` is an important step, but you must also check deterministic inputs, archive file ordering/timestamps, dependency locks, and toolchains if bit-for-bit identical output is needed.

## 10. Optional: testing incremental build effectiveness

To observe the effect of build time:

**Case A — leaving default time enabled:**

~~~groovy
springBoot {
    buildInfo()
}
~~~

Run twice without modifying source code:

~~~bash
./gradlew build --info
./gradlew build --info
~~~

Per official docs, `bootBuildInfo` is typically not `UP-TO-DATE` when dynamic time is generated; downstream tasks like `classes`, certain tests, or packaging may be affected. **Do not claim every task always re-runs**, as Gradle versions, task graphs, and cache policies vary.

**Case B — excluding time:**

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Run the same pair of commands:

~~~bash
./gradlew build --info
./gradlew build --info
~~~

If inputs are unchanged, `bootBuildInfo` has the opportunity to become `UP-TO-DATE` and downstream outputs stay more stable. This demonstrates the exact reason the feature exists.

### 10.1. Do not confuse UP-TO-DATE with FROM-CACHE

- `UP-TO-DATE`: outputs in the current workspace still match inputs and local execution history.
- `FROM-CACHE`: task output was restored from the Gradle build cache when the task is cacheable and a valid entry exists.
- `EXECUTED`: task actions ran during this invocation.
- `NO-SOURCE` or `SKIPPED`: the task had no inputs or was skipped conditionally.

Omitting `build.time` reduces volatile inputs/outputs; it **does not guarantee** `bootBuildInfo` or `bootJar` will always report `FROM-CACHE`. To see which tasks are cacheable, check the task implementation/plugin version and actual logs.

### 10.2. Configuration cache is not build-info time

`--configuration-cache` caches the configuration/task graph result; `bootBuildInfo` creates the metadata file during execution/build. Using configuration cache does not replace managing `build.time`. Both can be enabled together, provided plugins and custom tasks comply with configuration-cache requirements.

If Gradle reports a problem around `bootBuildInfo`/serialization, inspect the report and plugin version; do not "fix" it by deleting metadata or blindly disabling all caches.

## 11. Maven: generating build-info and customizing time

The Maven Spring Boot Plugin provides the `spring-boot:build-info` goal. Unlike Gradle, Maven uses XML configuration and lifecycle executions. Below is an **alternative Maven project replacing Gradle** for the same Java source in Section 7.

Complete `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>metadata-demo</artifactId>
    <name>metadata-demo</name>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                        <configuration>
                            <time>off</time>
                            <additionalProperties>
                                <channel>training</channel>
                                <revision>manual-local</revision>
                            </additionalProperties>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This is a complete Maven POM for the example. It uses the Spring Boot starter parent to manage dependency/plugin defaults and the `repackage` execution when the plugin is declared. The additional `build-info` execution is defined in `build/plugins`; there is no Gradle `bootBuildInfo` task in a POM.

**Detail on `<time>off</time>`:** this is the documented Spring Boot Maven Plugin way to **omit `build.time`** from the file. The extended keys in `<additionalProperties>` become `build.channel` and `build.revision`.

**Detail on `project.build.outputTimestamp`:** the fixed ISO-8601 value in the example sets a timestamp policy for archives/plugins supporting reproducible outputs. It is **not the actual machine clock at run time**. In this POM, `<time>off</time>` still keeps `build.time` absent even though `project.build.outputTimestamp` is declared. Never treat an arbitrary fixed timestamp as production audit data.

### 11.1. Maven commands and output files

~~~bash
mvn -version
mvn clean test
mvn package
java -jar target/metadata-demo-1.0.0.jar
~~~

If the repository has a Maven wrapper, use `./mvnw` on Unix or `.\mvnw.cmd` on Windows. During `mvn package`, Maven creates `target/classes/META-INF/build-info.properties` via the `build-info` goal. Spring Boot `repackage` packages the metadata file into the executable archive, typically under `BOOT-INF/classes/META-INF/build-info.properties`.

In this Maven example, the Java code in Section 7 and test in Section 7.1 yield the same results as the Gradle version: artifact/group/version/channel/revision and `TIME=<absent>`. If the Maven goal did not run, the app may lack the `BuildProperties` bean. In that case inspect `mvn help:effective-pom` and goal logs rather than writing `build-info` manually.

### 11.2. When not inheriting spring-boot-starter-parent

A POM using a different parent or only importing the Boot BOM may **not** inherit the same plugin management/executions as the Spring Boot parent. In that case, configure plugin versions and the `build-info` and `repackage` executions appropriately. Do not copy a fragment containing the `repackage` goal if another parent already defines it, as that can cause duplicate executions.

Verify:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn spring-boot:help -Ddetail=true -Dgoal=build-info
~~~

`spring-boot:help` requires valid plugin prefix/resolution. Inspect the effective version/goal/config; do not assume every Spring Boot Maven project generates `build-info` automatically.

## 12. Managing build time in Maven: three options

### 12.1. Keeping the default dynamic time

If you omit `<time>off</time>` and do not set `project.build.outputTimestamp`, the `build-info` goal typically uses the Maven session start time as `build.time` (per Spring Boot Maven Plugin 3.3). This value varies per run; two artifacts from the same source can differ.

This is suitable when you intentionally want to record when the build session ran, though it must not be mistaken for Git commit time or deployment time.

### 12.2. Omitting time to prioritize stability

In the `build-info` goal configuration:

~~~xml
<configuration>
    <time>off</time>
</configuration>
~~~

This is a **replacement fragment** for the longer configuration block in Section 11's POM, not a second execution. When metadata is generated, the file omits `build.time` and `BuildProperties.getTime()` returns `null`. Any controller or test reading time must handle `null`.

The Spring Boot Maven Plugin also supports `excludeInfoProperties`; however, `<time>off</time>` is the direct, readable, documented approach when you only want to omit time.

### 12.3. Recording a meaningful fixed instant

If a project needs a timestamp representing a controlled **release event**, you can supply an ISO-8601 value parseable by `Instant.parse`:

~~~xml
<configuration>
    <time>2025-01-01T00:00:00Z</time>
</configuration>
~~~

This example timestamp **only illustrates syntax**, not a real release time. In a production pipeline, source the timestamp from a defined authority (such as a release manifest or commit/release epoch per policy) and pass it via a CI/POM property.

To use a Maven property value, the goal configuration can reference:

~~~xml
<configuration>
    <time>${project.build.outputTimestamp}</time>
</configuration>
~~~

Here `project.build.outputTimestamp` must be defined or resolved by the build system to a valid timestamp. If undeclared, Spring Boot Maven Plugin's default behavior may fall back to session start time; for truly reproducible builds, do not rely on an undefined value.

**Note:** the timestamp inside `build.time` and the timestamps of ZIP archive entries are **two distinct concepts**. Setting `project.build.outputTimestamp` governs reproducible archive timestamps across supporting Maven plugins; `build-info` `time` governs the content of the metadata file. For bit-for-bit identical binaries, both—and all other inputs—must be controlled.

## 13. "Build time" can mean many things

| Milestone | Event | Software/mechanism typically recording it |
| --- | --- | --- |
| Git commit time | Commit created/recorded in VCS | Git metadata |
| CI job start time | Runner begins the job | CI server |
| Build-info time | Timestamp written into `build.time` by plugin | Spring Boot Gradle/Maven Plugin |
| Artifact publication time | Artifact uploaded to repository | Artifact repository |
| Release approved time | Release signed off | Release management |
| Deployment time | Release rolled out to environment | CD system/platform |
| Application startup time | JVM/Spring context starts | Runtime metrics/logging |

Do not lump all of these under one label like "build date." For instance, an artifact may be built at 10 AM, published at noon, and deployed the next evening. `BuildProperties.getTime()` **does not return deployment time**. Restarting a container **does not update** the packaged build-info time.

To answer "how long has the app been running?", use runtime uptime/startup telemetry, not build metadata. To answer "which release is running in staging?", use version/revision alongside deployment records.

### 13.1. Local time and UTC

`build.time` should use a parseable **`Instant`**, for example:

~~~text
2025-01-01T00:00:00Z
~~~

`Z` denotes UTC. Whether the build machine is set to `Asia/Ho_Chi_Minh`, UTC, or another timezone, an `Instant` represents a global point in time. Formatting for a viewer's timezone belongs in the UI or logging/reporting layer.

Java 17 converting an `Instant` to local datetime when needed:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class TimeExample {

    public static void main(String[] args) {
        Instant buildTime = Instant.parse("2025-01-01T00:00:00Z");
        ZonedDateTime local =
                buildTime.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println(buildTime);
        System.out.println(local);
    }
}
~~~

Save as standalone `TimeExample.java`, compile and run with JDK 17:

~~~bash
javac TimeExample.java
java TimeExample
~~~

Exact stdout:

~~~text
2025-01-01T00:00:00Z
2025-01-01T07:00+07:00[Asia/Ho_Chi_Minh]
~~~

This is a **standalone Java SE example** for learning time representation, requiring no Spring Boot. The example value is a fixed point in time and does not read the system clock, so its output is identical across runs.

### 13.2. Do not use formatted local time as canonical data

Strings like `09/11/2026 09:00` lack timezone/offset information and can be interpreted differently between build/CI machines and operations machines. Use ISO-8601 with `Z` or a valid offset for machine-readable metadata. If keeping `build.time`, do not write arbitrary strings like `Mon Nov 9` and assume `BuildProperties.getTime()` will parse them.

## 14. Build metadata and Actuator /actuator/info

### 14.1. BuildProperties does not require an HTTP endpoint

The `BuildProperties` bean is consumed directly by the application from the build-info resource. That is why the console example in Section 7 only needed `spring-boot-starter`, with no HTTP endpoint. Exposing build info over HTTP requires **Actuator and a web application**, plus an exposure policy.

With Gradle Groovy, dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Kotlin equivalent:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

With Maven, add the two corresponding `<dependency>` entries inside `<dependencies>`. This is an **optional extension**, unnecessary if you only read `BuildProperties` in Java code.

In `src/main/resources/application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info
management.info.build.enabled=true
~~~

In Spring Boot 3.3, only the `health` endpoint is typically exposed over HTTP by default; therefore `info` must be explicitly included. `BuildInfoContributor` is automatically available when the build-info resource exists and the feature is enabled. `management.info.build.enabled=true` makes the intent explicit, though system policies may change defaults.

Start the web application after adding the starters:

~~~bash
./gradlew bootRun --args='--server.port=18080'
~~~

In another terminal:

~~~bash
curl -fsS http://localhost:18080/actuator/info
~~~

The JSON may contain a `build` object with keys `artifact`, `group`, `name`, `version`, `channel`, and `revision`; additional fields depend on contributors and runtime configuration. When `time` is excluded, do not expect a `time` field to always appear. Do not hardcode the entire JSON byte-for-byte since serialization/ordering and contributors may vary.

### 14.2. Security: metadata can also be sensitive

Do not put into `build-info.properties`:

- Access tokens, repository passwords, signing keys, or secret API keys.
- Internal filesystem paths, full CI environment dumps, host usernames, or sensitive IPs.
- Production environment details unnecessary inside the artifact.
- Full Git remote URLs containing credentials.

Even when `/actuator/info` is not exposed, anyone holding the executable JAR can extract `META-INF/build-info.properties`. **Do not treat disabling the HTTP endpoint as protection for secrets inside the artifact**.

If you want to expose a revision, use a publicly permitted identifier (such as a short commit hash) per policy. Do not automatically add full branch names or private ticket IDs when the endpoint may be public.

## 15. Customizing other properties: group, name, artifact, version, and additional

### 15.1. Setting standard properties via DSL

**Gradle Groovy fragment:**

~~~groovy
springBoot {
    buildInfo {
        properties {
            artifact = 'course-service'
            group = 'com.example.training'
            name = 'Course Service'
            version = '2.1.0'
        }
    }
}
~~~

**Gradle Kotlin fragment:**

~~~kotlin
springBoot {
    buildInfo {
        properties {
            artifact.set("course-service")
            group.set("com.example.training")
            name.set("Course Service")
            version.set("2.1.0")
        }
    }
}
~~~

**These snippets are only examples of overriding metadata**. If applied to the lesson's `metadata-demo` project, the Java output in Section 8 will no longer match the previous artifact/group/version; update assertions/tests to match the new contract. Do not combine two `buildInfo` blocks declaring conflicting values.

In Maven, group/artifact/version/name default from the POM. To change the "release identifier," normally update **`groupId`, `artifactId`, `version`, and `name` in the POM** from a single source of truth rather than setting metadata completely different from the published coordinates. The Maven `build-info` goal also offers `excludeInfoProperties`, `outputFile`, and `additionalProperties`; check the effective POM and plugin version when customizing deeply.

### 15.2. What additional properties are useful?

Helpful supplemental metadata:

| Logical key | Example | Notes |
| --- | --- | --- |
| `channel` | `training`, `snapshot`, `release` | Use labels strictly per organizational policy |
| `revision` | Approved short Git SHA | Must be an actual revision, not a placeholder in releases |
| `schema` | `v1` | Version of the metadata contract, not the app version |
| `builder` | `ci` | Avoid recording sensitive machine usernames/hostnames |
| `toolchain` | `java-17` | Describes compiler target; not necessarily runtime JVM |
| `pipeline` | Publicly safe ID | May point to CI run records; consider exposure |

When setting `additional`, the plugin prepends `build.`. Do not write key `build.channel` in the map if you want `build.channel`, as that creates a redundant `build.build.channel` key. Key names should be simple, stable, and hold normalized values.

### 15.3. CI-sourced properties: avoid calling system APIs at configuration time without reason

An anti-pattern is:

~~~groovy
springBoot {
    buildInfo {
        properties {
            additional = [
                'revision': System.getenv('GIT_COMMIT'),
                'hostname': java.net.InetAddress.localHost.hostName
            ]
        }
    }
}
~~~

This snippet is **not recommended**: it reads the environment during Gradle configuration, records a potentially sensitive hostname, and introduces a dependency on machine state. It can break configuration caching and build reproducibility.

**Better strategy:** provide a controlled CI variable, use Gradle Providers API/lazy values for task inputs, pick an explicit development fallback, and avoid recording unnecessary data. Spring Boot Gradle docs confirm additional properties can be computed lazily via `Provider`. Example Kotlin fragment illustrating when a real project sets `CI_COMMIT_SHA`:

~~~kotlin
springBoot {
    buildInfo {
        properties {
            additional.put(
                "revision",
                providers.environmentVariable("CI_COMMIT_SHA").orElse("local")
            )
        }
    }
}
~~~

This is an **additive fragment**, replacing `additional.set(mapOf(...))` in the full example if you want another revision source. In production, policy must require the real variable rather than silently publishing `local` as release metadata. Do not keep both a static `revision` and a dynamic `revision` without clarifying which takes effect.

Note: if you intentionally embed a Git SHA in the file, the output **will differ when the source revision differs**, which is a valid change in build inputs. Reproducibility means the same source and **defined** environment produce the same output; it does not mean forcing distinct revisions to share an identical metadata file.

## 16. Correlation with Git metadata

Spring Boot also supports `git.properties` (via an appropriate plugin) so Actuator can display Git branch and commit ID/time. It is **not** the same file as `build-info.properties`:

~~~text
classpath:/META-INF/build-info.properties  → BuildProperties
classpath:/git.properties                  → GitProperties
~~~

The information differs:

- `build.version`: version supplied by the build tool/POM.
- `build.revision`: custom property if the team deliberately writes it; should match the CI source.
- `git.commit.id`: value from Git metadata.
- `git.commit.time`: commit timestamp, not build timestamp.
- `build.time`: instant determined by the build-info plugin.

If a team uses a Git plugin to create `git.properties` while also recording `build.revision`, add a test/assertion verifying they come from the same source. Never alter Git commit time to "tidy up" `build.time`. For a release artifact, commit ID is usually a more reliable traceability key than a standalone build timestamp.

## 17. Build metadata and ZIP timestamps: two independent layers

### 17.1. Metadata file

When `build-info.properties` contains:

~~~properties
build.time=2025-01-01T00:00:00Z
~~~

this is **text content** inside a resource. Keeping it fixed or omitting it stabilizes that file.

### 17.2. Archive entry timestamps

A JAR is a ZIP archive; each entry within it carries metadata such as a timestamp. A plugin/archiver can record per-entry file modification times, producing different JAR bytes even when `build-info.properties` is identical. Therefore, configure reproducible archives at the Gradle/Maven layer if policy demands byte-for-byte equivalence.

With Gradle's `AbstractArchiveTask`, helpful settings (optional fragment) are:

**Groovy:**

~~~groovy
tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Kotlin:**

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

This is part of a reproducible-archives policy, **not a replacement** for `buildInfo.excludes`. Newer Gradle versions have their own defaults; read your exact wrapper version's docs rather than assuming a default.

In Maven, compatible archivers/plugins can use:

~~~xml
<properties>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

A stable value can normalize archive entry timestamps; the example uses ISO-8601. If CI wants release time as separate metadata, define a consistent source and do not randomly vary `project.build.outputTimestamp` across job retries when pursuing reproducibility.

### 17.3. Why checking JAR checksums can serve as an extra check

If two builds from identical commit/dependencies/toolchain/policy yield `metadata-demo-1.0.0.jar` with different checksums, check:

1. Does `build-info.properties` contain a dynamic timestamp?
2. Does generated Git metadata include a system-clock timestamp?
3. Are ZIP entry timestamps/ordering stable?
4. Do the Java compiler, annotation processors, or codegen emit non-deterministic data?
5. Are the build tools and environments truly identical?
6. Does any build step add a signature, launch script, or unstable CI data?

Use checksums as a diagnostic signal; **do not conclude two differing JARs were tampered with** before ruling out legitimate sources of variation.

## 18. Testing and CI/CD for a build metadata policy

A pipeline can follow this checklist:

1. **Lock inputs:** Gradle wrapper/Maven version, Spring Boot plugin, Java toolchain, dependency versions.
2. **Define the contract:** which metadata is mandatory and which is allowed to be public?
3. **Choose a time policy:** keep time, exclude time, or fix an instant from a controlled release source.
4. **Bind the revision reliably:** require CI jobs to supply the Git commit SHA, disallowing fake fallbacks in releases.
5. **Generate metadata:** Gradle `bootBuildInfo` or Maven `build-info`.
6. **Run tests:** verify `BuildProperties` against expected version/group/channel/revision.
7. **Package:** `bootJar` or Maven `package` + `repackage`.
8. **Inspect the actual file:** read `META-INF/build-info.properties` inside the published archive.
9. **Smoke test:** run `java -jar` and verify output/endpoints where applicable.
10. **Cross-reference records:** commit SHA, CI run, artifact checksum, release/deployment records; never treat `build.time` as the sole source of truth.
11. **Protect secrets:** ensure properties do not expose tokens/private data via the artifact or Actuator.
12. **Rebuild test:** if reproducibility is required, rebuild with equivalent inputs, compare hashes, and resolve discrepancies.

### 18.1. Metadata accuracy before performance

If a system truly requires knowing the **exact instant of the real build**, do not just exclude time and replace it with a meaningless dummy value. Design out-of-band provenance or a valid time metadata field from a verifiable source. Conversely, do not leave dynamic time in the file just because it is the default when the system primarily needs identical rebuilds from the same source.

A practical split is:

- The artifact holds stable values such as version/revision/channel.
- CI records job start/end timestamps.
- The artifact repository records publish timestamp/checksum.
- The deployment platform records deploy time/environment.
- Monitoring records application startup time.

This layering gives full traceability without turning every rebuild of the same commit into a different binary just because the clock ticked.

## 19. Common errors and fixes

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Spring lacks `BuildProperties` bean | build-info not enabled or file not on classpath | Check `bootBuildInfo`/Maven goal, file, and archive |
| `build-info.properties` does not appear | Task/goal did not run, wrong module configuration | `./gradlew tasks --all`, `mvn help:effective-pom`, and outputs |
| `build.time` still present despite thinking it was excluded | Config placed in wrong scope, different Gradle DSL version, stale artifact | Check exact `buildInfo.excludes`, run `clean`, check new file |
| `BuildProperties.getTime()` returns null | Time was excluded or value is unparseable | Check the file; handle null, check `get("time")` if diagnosing |
| `build.version` differs from archive filename | Metadata was overridden without changing project version | Check Gradle `version`/POM `version`, `bootJar` output, and metadata |
| `build.artifact` differs from Maven artifactId | `<artifactId>` and `name`/customizations differ | Check POM, `build-info` goal, and output file |
| `bootBuildInfo` never UP-TO-DATE | Dynamic default `build.time` | Exclude time if reproducibility is prioritized |
| Build keeps re-running tests without Java edits | Metadata resource changes due to build time | Compare task graph/`--info` and inspect `bootBuildInfo` output |
| `/actuator/info` returns 404 | Missing Actuator/web starter or endpoint not exposed | Check dependencies and `management.endpoints.web.exposure.include` |
| `/actuator/info` lacks `build` | Missing build-info resource or `BuildInfoContributor` disabled | Check `management.info.build.enabled`, file, and logs |
| CI leaks Git branch/secret | Additional properties pulled env vars indiscriminately | Audit metadata, remove sensitive keys, check endpoint exposure |
| `java -jar` shows old version | Running wrong JAR, stale build file, or copied wrong classifier | Identify `bootJar`/`repackage` output, check manifest/contents |
| Maven `<time>off</time>` yet JAR checksums still differ | ZIP timestamps, codegen, Git metadata, or tools/env still vary | Check `project.build.outputTimestamp` and non-deterministic sources |
| Gradle `FROM-CACHE` never appears | Task not cacheable/cache miss or only `UP-TO-DATE` | Check `--info`, task inputs, and build cache settings |
| Gradle configuration cache errors around build-info | Plugin/task compatibility for that version | Check configuration cache report, upgrade plugin, or temporarily disable it |
| Runtime instant and build instant differ | Two distinct events | Use logs/metrics for startup and CI records for build |
| Timezone causes confusion | Timestamp string lacks offset or uses wrong format | Use `Instant`/ISO-8601 UTC and format at presentation layer |

**Troubleshooting order:** verify build plugin/task → inspect generated metadata file → verify entry in archive → verify values via `BuildProperties` → then investigate Actuator/CI runtime. Do not modify the controller when `build-info.properties` was never created.

## 20. Practice exercises with answers

### Exercise 1 — Change channel

**Task:** change the `channel` property in the Gradle example from `training` to `release`, rebuild, and print metadata.

**Result:** the file has `build.channel=release` and `BuildProperties.get("channel")` returns `release`. Any JUnit assertion still hardcoding `training` must be updated. `project.version` does not change automatically just because `channel` changed.

### Exercise 2 — What happens to time?

**Question:** the Groovy version has `excludes = ['time']`; code calls `build.getTime()`. What is the value?

**Answer:** `null`. There is no `build.time` in the generated resource. Therefore null-handling or a display fallback policy is needed.

### Exercise 3 — Build re-runs without source changes

**Scenario:** `bootBuildInfo` runs on every invocation even though Java sources are unchanged. The build uses `springBoot { buildInfo() }` without excluding time.

**Answer:** the default `build.time` is a changing instant; it causes output to vary and keeps the task from being up-to-date per documentation. If the team prioritizes repeatability/performance, add `excludes` for `time` and re-measure.

### Exercise 4 — Group and artifact

**Question:** why can `build.artifact` differ from `build.name`? Must they always match?

**Answer:** `artifact` is typically the technical name/base name of the archive, while `name` is a display name. They can differ intentionally. What matters is that they match the artifact/release contract, not that they are identical.

### Exercise 5 — Maven time off

**Task:** configure the Maven goal to omit `build.time`.

**Answer:**

~~~xml
<configuration>
    <time>off</time>
</configuration>
~~~

This fragment belongs in the `spring-boot:build-info` execution, not a `maven-jar-plugin` property. After `mvn package`, check `target/classes/META-INF/build-info.properties`.

### Exercise 6 — Two meanings of outputTimestamp

**Question:** the POM sets `project.build.outputTimestamp=2025-01-01T00:00:00Z` and the `build-info` goal sets `<time>off</time>`. Does the metadata file contain `time`?

**Answer:** no. `<time>off</time>` omits `build.time`. `project.build.outputTimestamp` can still be used by archive plugins to normalize ZIP/JAR entry timestamps. The two configuration layers are independent.

### Exercise 7 — Actuator info 404

**Scenario:** `BuildProperties` works inside the app, yet HTTP `/actuator/info` returns 404.

**Answer:** having the metadata bean does not mean the HTTP endpoint is installed/exposed. Check the Actuator dependency, web server, endpoint exposure, and security. Do not manually copy metadata into a custom REST controller as a workaround.

### Exercise 8 — Deployment time

**Question:** after restarting a JAR released yesterday, does `build.time` change to the restart time?

**Answer:** no. That metadata was written at build time and packaged into the archive. Restart time must be read from runtime/monitoring/operations records.

### Exercise 9 — Same code, different SHA-256

**Scenario:** `build.time` was excluded, yet two JARs from the same commit still have different checksums.

**Answer:** check ZIP timestamps/ordering, generated sources/resources, toolchains, dependency graph, Git properties, and CI environment. Excluding time removes only one source of non-determinism.

### Exercise 10 — Data leak

**Scenario:** someone put an access token into `additional` and merely disabled `/actuator/info`.

**Answer:** still unsafe. The token remains inside the JAR and can be extracted from `META-INF/build-info.properties`. Remove the token from metadata, revoke/rotate it if already published, and fix CI policy.

## 21. Pre-release checklist

- [ ] A `bootBuildInfo` task or Maven `build-info` execution actually runs on the right application module.
- [ ] The file is generated at `META-INF/build-info.properties` and present in the final artifact.
- [ ] Metadata group/artifact/name/version match published coordinates and filenames.
- [ ] Additional keys are stable and meaningful, with no secrets or sensitive data.
- [ ] Clear policy exists for `build.time`: dynamic, omitted, or fixed provenance timestamp.
- [ ] If prioritizing reproducibility, time is excluded in Gradle and `time=off`/fixed is set in Maven.
- [ ] Checked archive timestamps/ordering and other non-determinism sources when comparing checksums.
- [ ] `BuildProperties.getTime()` is handled as nullable.
- [ ] Tests/smoke tests verify the real metadata and JAR.
- [ ] Actuator `info` (if present) is exposed only per policy without leaking unnecessary details.
- [ ] Git revision, CI run ID, release time, and deployment time are not confused with build instant.
- [ ] Gradle wrapper/Maven/Spring Boot plugin versions are explicit and DSL snippets match those versions.
- [ ] CI publishes the right JAR/Build Info rather than grabbing a stale artifact or plain JAR.

**Conclusion:** effective metadata management is more than adding a timestamp. First keep group/artifact/version accurate for traceability, add controlled extended properties, and then decide explicitly whether build time belongs in the **binary** or in **CI/release records**. In Spring Boot 3.3, Gradle `buildInfo.excludes = ['time']` and Maven `<time>off</time>` are the standard ways to omit dynamic time for more stable outputs; full reproducibility must still be verified on actual artifacts.

## 22. Official documentation

- Spring Boot 3.3 — Gradle Plugin, *Integrating with Actuator / Generating Build Information*: https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html
- Spring Boot 3.3 — Maven Plugin, *Integrating with Actuator / build-info*: https://docs.spring.io/spring-boot/docs/3.3.13/maven-plugin/reference/htmlsingle/
- Spring Boot 3.3.13 API — `BuildProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/BuildProperties.html
- Spring Boot 3.3 — Actuator *Endpoints / Application Information*: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Gradle — Incremental Build & Task Outcomes: https://docs.gradle.org/current/userguide/incremental_build.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Apache Maven — Reproducible Builds Guide: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Java SE 17 — `Instant` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html

When changing build tools/plugins or upgrading Java/Spring Boot, re-check the corresponding configuration APIs: this lesson aims to establish a **stable, testable, traceable metadata contract**, not to force every project to drop timestamps in every situation.
