# Verifying Which Layers Are Affected by Application Code or Dependency Changes

## 1. Problem Statement and What Must Be Proved

Spring Boot supports **layered executable JARs**: alongside application code and runtime libraries, the archive includes an index specifying which groups of files belong to which layer. When a container image is built by **extracting and copying each layer separately**, the Docker/OCI builder has the opportunity to reuse rarely changing layers instead of re-transferring the entire application every time a Java method is edited.

The central question of this lesson is not “did `jar` build successfully?” but rather:

- If **only an application Java class or resource changes**, does the `application` layer change while external libraries remain unchanged?
- If **an external release dependency is upgraded**, does `dependencies` change? Which other metadata files might change alongside it?
- When modifying a **local module dependency** or external `SNAPSHOT`, how are contents layered?
- Do differences in **logical Spring Boot layers** actually correspond to Docker image cache hits?
- How do you use **two controlled builds**, `layers.idx`, extraction, and **per-file SHA-256** to answer with evidence instead of guesswork?

This article uses **Spring Boot 3.3.13 and Java 17**, with Maven or Gradle. These are illustrative versions, not a claim of being the latest releases. The “expected” outcomes are things learners must run themselves to verify; we do not claim to have executed builds, Docker, or Java code on the learner's machine.

## 2. Three Levels of “Layer” That Must Not Be Conflated

### 2.1. Structure Inside an Executable JAR

A Spring Boot executable JAR typically contains:

~~~text
layer-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/launch/JarLauncher.class
├── org/springframework/boot/loader/... (other loader classes)
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/layer/LayerDemoApplication.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-<version>.jar
    │   ├── commons-lang3-<version>.jar
    │   └── ... (runtime libraries)
    └── layers.idx
~~~

`BOOT-INF/classes` holds the application's primary code/resources, `BOOT-INF/lib` holds nested dependency JARs, and the Spring Boot Loader at root helps the JVM load the right runtime classpath when running `java -jar`. `layers.idx` is **layering metadata**, not executable Java code.

### 2.2. Four Default Logical Layers in Spring Boot 3.3.13

| Layer | Typical contents | When can it change? |
| --- | --- | --- |
| `dependencies` | External release dependencies whose version does not contain `SNAPSHOT`. | Upgrading/adding/removing Spring Framework, Jackson, Commons Lang, release drivers, etc. |
| `spring-boot-loader` | Spring Boot Loader classes for starting the archive. | Changing Spring Boot loader/plugin version or related layout. |
| `snapshot-dependencies` | External non-project SNAPSHOT dependencies. | Adding/removing/upgrading/updating snapshot artifacts. |
| `application` | App classes/resources, metadata, and local project/module dependencies by default. | Editing app code, resources, build metadata, or internal modules. |

**Default order:** `dependencies` → `spring-boot-loader` → `snapshot-dependencies` → `application`. The idea is placing rarely changing contents earlier to increase cache reuse. A layer may be **empty**, especially `snapshot-dependencies` when no external SNAPSHOTs exist.

Subtle detail: a **local module JAR** can still sit at `BOOT-INF/lib/core.jar` while being assigned to the logical `application` layer, **not** `dependencies`. File location inside the ZIP and layer membership are two separate concepts.

### 2.3. Docker/OCI Image Layers

`BOOT-INF/layers.idx` **does not automatically create** OCI layers. If a Dockerfile only does:

~~~dockerfile
FROM eclipse-temurin:17-jre
COPY target/layer-demo-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

then the Dockerfile has **a single step copying the whole outer JAR**. When a class changes, the outer JAR differs too; Docker does not automatically inspect `layers.idx` to split libraries sitting inside the ZIP.

To leverage logical layers, use an extraction tool (such as Spring Boot jarmode tools) or layering-aware buildpacks, then observe the cache of the **actual image builder**.

**Do not conclude** that “logical dependencies layer unchanged” equals “Docker definitely hits cache on every remaining image layer”: cache keys also depend on **parent layers**, Dockerfile instructions, build context, base image, build args, and builder implementation.

## 3. What Information Does `BOOT-INF/layers.idx` Contain?

`layers.idx` is a list of layers and the paths assigned to each layer, ordered for use when building images. **Illustrative** example, not a capture of a real built JAR:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/commons-lang3-3.14.0.jar"
  - "BOOT-INF/lib/spring-webmvc-6.x.y.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/launch/JarLauncher.class"
- "snapshot-dependencies":
  - "BOOT-INF/lib/some-lib-1.0-SNAPSHOT.jar"
- "application":
  - "META-INF/MANIFEST.MF"
  - "BOOT-INF/classes/"
~~~

The actual index may use directory prefixes or list detailed entries per plugin behavior. Library sets and selected versions vary by project. Do not copy placeholder examples like `6.x.y` or `1.0-SNAPSHOT` as real filenames.

Meanings to distinguish:

- `layers.idx`: which file **is assigned to which logical layer**.
- `classpath.idx` (if present): **classpath order** metadata for the launcher under applicable conditions.
- `MANIFEST.MF`: `Main-Class` (usually `JarLauncher`) and `Start-Class` (the Java application main class).
- `jar tf`: lists entries in the outer JAR, **without descending into nested JARs**.
- `Dockerfile COPY`: only with proper extraction/copying does grouping turn into useful container layer steps.

### 3.1. One Important Default Difference Between Maven and Gradle

**Maven Plugin:** classifies **module dependencies belonging to the current reactor/build** into `application`. A module resolved solely from the Maven local repository—even with identical GAV coordinates—that does **not** participate in the current build may be treated as a regular dependency.

**Gradle Plugin:** project dependencies (`implementation project(':core')`) go into `application`; release **non-project dependencies** go into `dependencies`, and non-project SNAPSHOTs go into `snapshot-dependencies`.

Therefore, do not decide a layer solely by seeing `SNAPSHOT` in a JAR's name. Read the index from the **exact artifact and exact build mode**.

## 4. Designing a Controlled-Variable Experiment

To establish causation, we need three builds:

| Build | Java source | Commons Lang dependency | Purpose |
| --- | --- | --- | --- |
| **A – baseline** | Endpoint returns `v1:Layered boot`. | `3.14.0`. | Reference baseline. |
| **B – code-only** | Change only `v1:` to `v2:`. | Keep `3.14.0`. | Isolate impact of application code changes. |
| **C – dependency-only** | **Revert to v1 code like A**. | Upgrade from `3.14.0` to `3.15.0` (if repository/policy permits). | Isolate impact of changing an external release dependency. |

Valid comparisons are **A→B** and **A→C**. Comparing B→C mixes two changes (code reverted and dependency upgraded), failing to isolate a single cause.

### 4.1. Initial Hypothesis Matrix

| Experiment | `dependencies` | `spring-boot-loader` | `snapshot-dependencies` | `application` |
| --- | --- | --- | --- | --- |
| A→B, only app Java changed | Expected unchanged. | Expected unchanged. | Expected unchanged/empty. | **Expected changed.** |
| A→C, upgrade external release dependency | **Expected changed.** | Usually unchanged when plugin version stays constant. | Usually unchanged. | **May** change due to archive metadata/layer index. |
| Edit only `src/main/resources` | Usually unchanged. | Usually unchanged. | Usually unchanged. | Expected changed. |
| Edit only test source | Usually unchanged. | Usually unchanged. | Usually unchanged. | Usually unchanged if test output does not enter artifact. |
| Change local module `core` | May remain unchanged. | May remain unchanged. | May remain unchanged. | May change since module JAR sits in `application`. |
| Upgrade Boot plugin/BOM | May change. | May change. | May change. | May change. |

**Important note:** do not write a rigid assertion that “upgrading a dependency may only change the dependencies layer”; `layers.idx`, the manifest, generated build-info, or classpath-related metadata can also change another layer. A file-level diff is the real evidence.

### 4.2. Fair Comparison Conditions

Keep constant across builds A/B/C:

1. JDK vendor/version and Maven/Gradle Wrapper.
2. Spring Boot plugin version, compiler flags, resource filtering, and packaging config (except the intentionally changed dependency).
3. Repository selection, OS/architecture, and environment variables affecting builds.
4. No external SNAPSHOT republishes or silently shifting dynamic versions.
5. No automatic injection of build timestamps/random UUIDs into resources/manifest.
6. Tests actually run, and packaging actually produces the executable JAR.
7. Never use the same extraction directory for two builds.
8. Never use wildcards that accidentally match `*-plain.jar` or `*.jar.original`.
9. Save A/B/C binaries to separate files **before the next build overwrites the output**.
10. Capture the resolved dependency tree to explain any unexpected differences.

## 5. Illustrative Java 17 Application, Shared Source for Maven/Gradle

Common file tree:

~~~text
layer-demo/
  pom.xml                  # Choose Maven
  # or settings.gradle and build.gradle if choosing Gradle
  src/main/java/com/example/layer/LayerDemoApplication.java
  src/main/resources/application.properties
  src/test/java/com/example/layer/LayerDemoApplicationTest.java
  captures/                # captures A/B/C, not part of release source
  LayerDelta.java          # standalone layer comparison program, in section 11
~~~

### 5.1. Complete Main Application

`src/main/java/com/example/layer/LayerDemoApplication.java`:

~~~java
package com.example.layer;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LayerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerDemoApplication.class, args);
    }

    @GetMapping("/layer")
    public String layer() {
        return "v1:" + StringUtils.capitalize("layered boot");
    }
}
~~~

`StringUtils.capitalize("layered boot")` returns `Layered boot`, so build A's expected HTTP body is `v1:Layered boot`. The endpoint **actually invokes external Commons Lang**; this catches missing runtime dependency JARs rather than merely checking startup.

Build B changes only the **method body**:

~~~java
return "v2:" + StringUtils.capitalize("layered boot");
~~~

This is an edit snippet, not a standalone Java file. When using B, also update the test assertion from `v1:Layered boot` to `v2:Layered boot`.

### 5.2. Primary Resource

`src/main/resources/application.properties`:

~~~properties
spring.application.name=layer-demo
server.port=8080
~~~

This file normally lands at `BOOT-INF/classes/application.properties` and belongs to the `application` layer. To try a **resource-only** change, edit it **after** finishing the code-only/dependency-only experiments.

### 5.3. Complete JUnit 5 + MockMvc Test

`src/test/java/com/example/layer/LayerDemoApplicationTest.java`:

~~~java
package com.example.layer;

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
class LayerDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void layerEndpointReflectsCurrentCode() throws Exception {
        mvc.perform(get("/layer"))
           .andExpect(status().isOk())
           .andExpect(content().string("v1:Layered boot"));
    }
}
~~~

This test uses the **Spring test context/MockMvc** without opening a real HTTP port. It requires `spring-boot-starter-test`. The `java -jar` smoke test in a later step verifies the runtime of the packaged artifact.

## 6. Complete Maven POM and Default Layered Archive

`pom.xml`:

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
    <artifactId>layer-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
~~~

**Why does this file build a layered JAR?**

- `spring-boot-starter-parent` manages compatible dependency/plugin defaults and the `repackage` execution when the Boot Maven Plugin is declared.
- `spring-boot-maven-plugin` 3.3.13 supports layers by default and writes `BOOT-INF/layers.idx` when building the executable JAR.
- External release `commons-lang3` normally lands in `dependencies`; check the **selected version** in `dependency:tree` and the actual index.
- `project.build.outputTimestamp` stabilizes ZIP entry timestamps across plugins supporting reproducible builds, though it does not replace controlling generated inputs.
- `spring-boot-starter-test` has scope `test` and does not enter the default executable runtime JAR.
- If a corporate parent only imports the BOM, you must declare the Boot plugin version/binding yourself; a BOM does not automatically run `repackage`.

Maven commands (when the project has a Maven Wrapper):

~~~bash
./mvnw -version
./mvnw clean verify
./mvnw dependency:tree
jar tf target/layer-demo-0.0.1-SNAPSHOT.jar
~~~

Do not pick `*.jar.original` retained by `repackage`; that may be a plain JAR. Verify test reports in `target/surefire-reports` rather than only reading `BUILD SUCCESS`.

## 7. Complete Gradle Groovy DSL and `bootJar`

Use the **same Java files** while choosing Gradle instead of Maven.

`settings.gradle`:

~~~groovy
rootProject.name = 'layer-demo'
~~~

`build.gradle`:

~~~groovy
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
    implementation 'org.apache.commons:commons-lang3:3.14.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Explanation:**

- The Java plugin creates source sets/tests; the Boot plugin creates executable `bootJar` and enables layered archives by default.
- `io.spring.dependency-management` supports Spring Boot dependency management.
- `AbstractArchiveTask` reduces ZIP metadata noise (timestamps/ordering) for cleaner comparisons. This is Groovy DSL, not Kotlin DSL.
- Test libraries live in the test configuration and are not packaged into the regular executable runtime JAR.
- If `*-plain.jar` is also produced by Gradle `jar`, choose the **exact `bootJar` output** for verification.
- The Java 17 toolchain works only when the environment supplies a compatible JDK or appropriate provisioning; the Gradle Wrapper must also be compatible.

Commands:

~~~bash
./gradlew --version
./gradlew clean build
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
jar tf build/libs/layer-demo-0.0.1-SNAPSHOT.jar
~~~

`dependencyInsight` output matters: if graph/version constraints keep the old version pinned, editing a version declaration may not actually alter the dependency layer.

## 8. Baseline A: Inspecting the Index and Creating an Isolated Snapshot

### 8.1. Checking `BOOT-INF/layers.idx`

With Maven:

~~~bash
jar tf target/layer-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/layers.idx$'
unzip -p target/layer-demo-0.0.1-SNAPSHOT.jar BOOT-INF/layers.idx
~~~

With Gradle:

~~~bash
jar tf build/libs/layer-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/layers.idx$'
unzip -p build/libs/layer-demo-0.0.1-SNAPSHOT.jar BOOT-INF/layers.idx
~~~

`grep`/`unzip` must be available in Bash/macOS/Linux. Windows PowerShell can use `jar tf ... | Select-String 'layers.idx'`; if `unzip` is absent, run JDK `jar xf` inside a **dedicated inspection directory**.

If `BOOT-INF/layers.idx` is missing, confirm you are inspecting the Boot executable JAR and did not accidentally set `<layers><enabled>false</enabled></layers>` (Maven) or `layered { enabled = false }` (Gradle). **Do not insert fake metadata into the archive**.

### 8.2. Spring Boot 3.3 `jarmode=tools`

In a standard layered archive, Spring Boot 3.3.13 includes `spring-boot-jarmode-tools` and supports:

~~~bash
java -Djarmode=tools -jar target/layer-demo-0.0.1-SNAPSHOT.jar help
java -Djarmode=tools -jar target/layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

Gradle uses the corresponding `build/libs/...jar` path. This is **`tools` mode**; do not copy `-Djarmode=layertools` from older Spring Boot tutorials without checking versions.

**Exception:** `jarmode=tools` cannot be used with a **fully executable archive that has a prepended launch script**. If a project enables Gradle `launchScript()` or Maven `executable`, build a standard executable archive without the script to use tools mode. If the project disables `includeTools`/jarmode tools, use another inspection tool per that version's docs.

### 8.3. Capturing A and Extracting to an Isolated Directory

Maven:

~~~bash
mkdir -p captures
./mvnw clean verify
cp target/layer-demo-0.0.1-SNAPSHOT.jar captures/A.jar

java -Djarmode=tools -jar captures/A.jar list-layers
java -Djarmode=tools -jar captures/A.jar \
  extract --layers --destination captures/A-layers
~~~

Gradle replaces the build/copy part with:

~~~bash
mkdir -p captures
./gradlew clean build
cp build/libs/layer-demo-0.0.1-SNAPSHOT.jar captures/A.jar

java -Djarmode=tools -jar captures/A.jar list-layers
java -Djarmode=tools -jar captures/A.jar \
  extract --layers --destination captures/A-layers
~~~

**Expectation:** `captures/A-layers` holds contents for `dependencies`, `spring-boot-loader`, `snapshot-dependencies` (possibly empty), and `application`. Never reuse the same destination when extracting B/C. `java -Djarmode=tools -jar ... extract --layers --destination ...` is the supported Boot 3.3 extraction command.

## 9. Build B: Change **Only Application Code**

Keep POM/Gradle build scripts and dependency versions identical to A. Edit the Java method:

~~~java
// Build B, replace only the return body in layer()
return "v2:" + StringUtils.capitalize("layered boot");
~~~

Update the test expectation to `v2:Layered boot`, since `src/test` is not packaged in the default runtime archive. Do not alter `application.properties`, plugin versions, resource generation, or other dependencies.

Maven:

~~~bash
./mvnw clean verify
cp target/layer-demo-0.0.1-SNAPSHOT.jar captures/B.jar
java -Djarmode=tools -jar captures/B.jar \
  extract --layers --destination captures/B-layers
~~~

Or Gradle:

~~~bash
./gradlew clean build
cp build/libs/layer-demo-0.0.1-SNAPSHOT.jar captures/B.jar
java -Djarmode=tools -jar captures/B.jar \
  extract --layers --destination captures/B-layers
~~~

**Prediction:** `BOOT-INF/classes/com/example/layer/LayerDemoApplication.class` changes, so `application` changes. The remaining three layers are **expected** to stay unchanged if all other inputs stay constant. Do not treat this as an observed fact until running the file-level comparison in section 11.

### 9.1. Runtime Smoke Test for B

~~~bash
java -jar captures/B.jar --server.port=18085
~~~

Once the server is ready, in a second terminal:

~~~bash
curl -i http://localhost:18085/layer
~~~

**Expected:** HTTP 200 and body `v2:Layered boot`. Stop the app with Ctrl+C before running A/C on the same port. Testing via `java -jar` matters because building/testing alone does not prove the packaged executable artifact works.

## 10. Build C: Upgrade **Only an External Release Dependency**

Before upgrading the dependency, **restore production source/tests back to A**: `"v1:"` and expected `v1:Layered boot`. Never compare B→C to infer dependency-only impact, since both code and dependency version differ.

In the Maven POM, update one declaration to:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.15.0</version>
</dependency>
~~~

In Gradle Groovy DSL, update to:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.15.0'
~~~

These are **replacement snippets** for the declaration in sections 6/7, not standalone POM/Groovy files. If this version is not approved in your repository, pick an actual resolvable release version, note that version clearly, and apply the same principle.

Maven:

~~~bash
./mvnw clean verify
./mvnw dependency:tree
cp target/layer-demo-0.0.1-SNAPSHOT.jar captures/C.jar
java -Djarmode=tools -jar captures/C.jar \
  extract --layers --destination captures/C-layers
~~~

Or Gradle:

~~~bash
./gradlew clean build
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
cp build/libs/layer-demo-0.0.1-SNAPSHOT.jar captures/C.jar
java -Djarmode=tools -jar captures/C.jar \
  extract --layers --destination captures/C-layers
~~~

**Prediction:** if the selected version actually changes from 3.14.0 to 3.15.0, the `BOOT-INF/lib/commons-lang3-...jar` entries in `dependencies` change. `spring-boot-loader` usually remains stable since the Boot plugin version stayed the same. `application` **may** change due to regenerated `layers.idx`/manifest/build metadata, even though Java production classes did not change.

**Prerequisite check:** verify the selected version via `dependency:tree` (Maven) or `dependencyInsight` (Gradle) and list `BOOT-INF/lib` of file C. A requested version in the build script **does not prove** the archive used that version if BOMs/constraints/conflicts override it.

## 11. Java 17 Tool: Comparing Per-File SHA-256 Across Each Layer

Comparing the hash of the **outer JAR** only tells you “the archive changed”. We need to know **which file, in which layer**, so we extract A/B/C and run a standalone Java program.

`LayerDelta.java`, **compiles with Java 17 without Spring on the classpath**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public final class LayerDelta {
    private static final List<String> LAYERS = List.of(
            "dependencies", "spring-boot-loader",
            "snapshot-dependencies", "application"
    );

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java LayerDelta <before-dir> <after-dir>");
            System.exit(2);
        }

        Path before = Path.of(args[0]).toAbsolutePath().normalize();
        Path after = Path.of(args[1]).toAbsolutePath().normalize();
        if (!Files.isDirectory(before) || !Files.isDirectory(after)) {
            throw new IllegalArgumentException(
                    "Both paths must be extracted layer directories");
        }

        for (String layer : LAYERS) {
            SortedMap<String, String> oldFiles = files(before.resolve(layer));
            SortedMap<String, String> newFiles = files(after.resolve(layer));
            SortedSet<String> all = new TreeSet<>(oldFiles.keySet());
            all.addAll(newFiles.keySet());

            List<String> changed = new ArrayList<>();
            for (String name : all) {
                if (!oldFiles.containsKey(name)) {
                    changed.add("+ " + name);
                } else if (!newFiles.containsKey(name)) {
                    changed.add("- " + name);
                } else if (!Objects.equals(oldFiles.get(name), newFiles.get(name))) {
                    changed.add("~ " + name);
                }
            }

            System.out.printf("%s: %s (old=%d, new=%d, changed=%d)%n",
                    layer,
                    changed.isEmpty() ? "UNCHANGED" : "CHANGED",
                    oldFiles.size(), newFiles.size(), changed.size());
            changed.stream().limit(12)
                    .forEach(s -> System.out.println("  " + s));
            if (changed.size() > 12) {
                System.out.println("  ... more changes omitted");
            }
        }
    }

    private static SortedMap<String, String> files(Path root)
            throws Exception {
        SortedMap<String, String> result = new TreeMap<>();
        if (!Files.isDirectory(root)) {
            return result;
        }

        try (Stream<Path> stream = Files.walk(root)) {
            for (Path file : stream.filter(Files::isRegularFile).toList()) {
                String relative = root.relativize(file)
                        .toString().replace('\\', '/');
                MessageDigest sha = MessageDigest.getInstance("SHA-256");

                try (InputStream input = Files.newInputStream(file)) {
                    byte[] buffer = new byte[8192];
                    int n;
                    while ((n = input.read(buffer)) != -1) {
                        if (n > 0) {
                            sha.update(buffer, 0, n);
                        }
                    }
                }

                result.put(relative, HexFormat.of().formatHex(sha.digest()));
            }
        }
        return result;
    }
}
~~~

**Mechanism:** the program walks **relative paths inside each layer**, computes SHA-256 over file bytes, and classifies: `+` is a new file; `-` is a removed file; `~` is the same path with changed contents. It ignores file timestamps after extraction, reducing noise between directories A/B/C.

Because `Path.of`, `Stream.toList`, and `HexFormat` all exist in Java 17, this source runs independently of the Maven/Gradle project. Execute it in a trusted local directory and only extract archives from verified sources.

Compile the audit tool and run:

~~~bash
javac LayerDelta.java

# Change only application code:
java LayerDelta captures/A-layers captures/B-layers

# Upgrade only dependency:
java LayerDelta captures/A-layers captures/C-layers
~~~

Expected pattern for **A→B** (actual counts and paths must come from your live run):

~~~text
dependencies: UNCHANGED (old=..., new=..., changed=0)
spring-boot-loader: UNCHANGED (old=..., new=..., changed=0)
snapshot-dependencies: UNCHANGED (old=0, new=0, changed=0)
application: CHANGED (old=..., new=..., changed=...)
  ~ BOOT-INF/classes/com/example/layer/LayerDemoApplication.class
~~~

Expected pattern for **A→C**: `dependencies: CHANGED`, with the old Commons Lang release path removed and the new JAR added. **Do not force `application` to be UNCHANGED**; if metadata files changed too, report those exact changed files accurately.

### 11.1. Tool Limitations

- Handles only **the four default layers**. If custom layers create `company-dependencies`, add the layer name and inspect the real `layers.idx` before running.
- Does not measure Docker image digests/cache hits; identical extracted file contents do not mean the image builder definitely cached the step.
- Does not verify cryptographic signatures or CVEs; SHA-256 here compares A vs. B, not against a publisher trust baseline.
- Does not test runtime/business correctness; run `java -jar` or a separate smoke job.
- If an extraction directory contains leftover files from overwriting, diffs will be wrong; always use **new, independent** paths.
- Does not follow symbolic links or treat special files as regular files; use trusted archives and isolated environments when needed.
- If bytecode changes solely due to a different JDK/compiler, the tool **accurately reports a change**, though the cause may not be business logic.

## 12. How to Interpret Results from A→B and A→C

### 12.1. A→B: `application` Is the Expected Impact

A method-body edit in `LayerDemoApplication` alters the class file, so the `application` layer normally reports `CHANGED`. External release dependencies and the Boot Loader stay unchanged when other build inputs are held constant.

If `dependencies` also changed:

1. Check `dependency:tree` or `dependencyInsight` to see whether selected versions differed.
2. Read `BOOT-INF/layers.idx` to see if files still share the same layer ownership.
3. Compare nested JAR hashes/paths via `LayerDelta`: added, removed, or same name with different bytes?
4. Check for external SNAPSHOT/changing dependencies or repository mirror rewrites.
5. Compare plugin/BOM/JDK/build profiles/resource generation between A and B.
6. Verify the exact captures: did you mix up a freshly rebuilt file or pass the wrong path?

### 12.2. A→C: External Dependency Changes Do Not Mean Every Class Changed

Switching Commons Lang from one release version to another normally causes `dependencies` to change. `LayerDelta` may print:

~~~text
dependencies: CHANGED (...)
  - BOOT-INF/lib/commons-lang3-3.14.0.jar
  + BOOT-INF/lib/commons-lang3-3.15.0.jar
~~~

That is an explanatory sample, not guaranteed stdout if selected versions differ. A metadata/index file can cause `application` to change **even when `LayerDemoApplication.class` is byte-for-byte identical**. Keep two questions distinct: “did business classes change?” and “did logical application layer contents change?”.

### 12.3. Test-Only and Resource-Only Changes

- **Editing test source/test resources:** not included in the Boot executable archive under standard configuration. If the JAR/layers change, investigate custom plugin tasks, generated metadata, or uncontrolled inputs.
- **Editing `src/main/resources`:** copied into `BOOT-INF/classes`; normally causes `application` to change. Check resource filtering/`processResources` before concluding files were packaged properly.
- **Activating a different profile at runtime:** does not by itself alter JAR/layer contents. However, if a build script actively filters profile-specific resources into the archive, that is a build content change and must be documented separately.

## 13. Multi-Module and SNAPSHOTs: Two Cases to Remember

### 13.1. Gradle Project Dependency

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

The Gradle Boot Plugin normally places **project dependencies** into `application`. The `core-...jar` file still sits as a nested file inside `BOOT-INF/lib`, yet its logical owner is `application`. Thus **editing `core` source** can cause `application` to change even when `app` classes stay untouched.

### 13.2. Maven Local Module Dependency

The Maven Boot Plugin treats local modules participating in the **current reactor build** as candidates for the `application` layer. If `app` resolves `core` solely from the local Maven repository without building `core` as part of the current build, the plugin may classify `core` as a regular dependency. Use your actual CI reactor workflow to predict layer membership.

### 13.3. External SNAPSHOTs

An external JAR `some-lib-1.0-SNAPSHOT.jar` normally goes into `snapshot-dependencies` by default. However, a **Gradle project dependency** carrying a `SNAPSHOT` version still belongs to `application` because of the project relationship. Likewise, an internal Maven module inside the reactor can land in `application`.

Lockfiles pin version coordinates, not guarantees that bytes of a mutable SNAPSHOT have not changed. For release reproducibility, use immutable artifacts, approved repositories, and appropriate verification/provenance policies.

### 13.4. Upgrading the Spring Boot Version Is a **Multi-Variable** Experiment

Upgrading the Boot plugin/BOM can simultaneously change `spring-boot-loader`, Spring/embedded server libraries in `dependencies`, jarmode tools, manifest/index files, and possibly application output. Never assume “upgrading Spring Boot only changes the loader”. Read the real diff and release notes.

## 14. Dockerfile Using Spring Boot jarmode Tools

Spring Boot 3.3 includes `spring-boot-jarmode-tools`. A multi-stage Dockerfile can extract and copy each layer to build the image:

~~~dockerfile
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /builder

ARG JAR_FILE=target/layer-demo-0.0.1-SNAPSHOT.jar
COPY ${JAR_FILE} application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /builder/extracted/dependencies/ ./
COPY --from=extractor /builder/extracted/spring-boot-loader/ ./
COPY --from=extractor /builder/extracted/snapshot-dependencies/ ./
COPY --from=extractor /builder/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**Things to understand:**

- The extractor stage invokes `jarmode=tools` from the built **executable JAR** itself. If a project disables jarmode tools or enables a fully executable launch script, this pattern may not apply.
- The final stage **does not copy the entire outer executable JAR**; it uses the extracted layout prepared by tools, where `application.jar` and related paths are structured for startup. This pattern is documented in Spring Boot 3.3.
- Each `COPY --from=extractor` is a separate Dockerfile step. Copy `dependencies` first and `application` last to improve cacheability.
- Base image `eclipse-temurin:17-jre` is only an example; production builds must use organizationally approved base images/tags/digests.
- If custom layers introduce new layers, add matching `COPY` steps and verify paths/`ENTRYPOINT`. Never omit files just because a new layer is missing from the Dockerfile.
- Never put secrets into Dockerfiles, build args, or application resources to “optimize caching”.
- Never claim cache hits solely from the layer index. Docker caching also depends on build context, parent layers, Dockerfile structure, BuildKit settings, and registries.

Docker build example for a Maven artifact:

~~~bash
docker build --progress=plain -t layer-demo:a .
~~~

For a Gradle artifact:

~~~bash
docker build --progress=plain \
  --build-arg JAR_FILE=build/libs/layer-demo-0.0.1-SNAPSHOT.jar \
  -t layer-demo:a .
~~~

These commands are for an authorized Docker environment. To compare A/B, ensure each build context supplies the exact A or B artifact at the declared path while holding the base image, Dockerfile, and builder settings constant. Capture logs of **every `COPY` step** rather than guessing cache efficiency from timestamps.

### 14.1. Logical Layers and OCI Layers Can Differ Even with Identical Content

A Docker `COPY` step can miss the cache because a parent layer changed, even though the bytes it copies are identical; another builder might deduplicate content-addressed blobs. Check `docker build --progress=plain` and actual image manifests/digests to evaluate.

If a Dockerfile only runs `COPY app.jar`, a minor app edit alters that step's input. In that situation, Spring Boot `layers.idx` **is not used to split Dockerfile steps**, so you cannot assume cache optimization just because the JAR has an index.

## 15. When Should Layers Be Customized?

Default layering is usually sensible. Customize only when a dependency group has a distinct update frequency, measurable caching behavior, or a release policy requiring additional layers.

### 15.1. Maven Custom `layers.xml`

The Spring Boot Maven Plugin can reference a separate file inside plugin `<configuration>`:

~~~xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <configuration>src/layers/layers.xml</configuration>
    </layers>
</configuration>
~~~

Example `src/layers/layers.xml` (for Maven 3.3):

~~~xml
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.springframework.org/schema/boot/layers
          https://www.springframework.org/schema/boot/layers/layers-3.3.xsd">
    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application"/>
    </application>
    <dependencies>
        <into layer="application">
            <includeModuleDependencies/>
        </into>
        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>
        <into layer="company-dependencies">
            <include>com.example:*</include>
        </into>
        <into layer="dependencies"/>
    </dependencies>
    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-boot-loader</layer>
        <layer>snapshot-dependencies</layer>
        <layer>company-dependencies</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
~~~

`<into>` rules are evaluated in **order of appearance**. Local module dependencies already claimed by `includeModuleDependencies` will not shift into `company-dependencies`. `layerOrder` must list all used names, though the order for **evaluating include rules** differs from the order for **writing layers**.

### 15.2. Gradle Custom Layer DSL

Groovy snippet for `build.gradle`:

~~~groovy
tasks.named('bootJar') {
    layered {
        application {
            intoLayer('spring-boot-loader') {
                include 'org/springframework/boot/loader/**'
            }
            intoLayer('application')
        }
        dependencies {
            intoLayer('application') {
                includeProjectDependencies()
            }
            intoLayer('snapshot-dependencies') {
                include '*:*:*SNAPSHOT'
            }
            intoLayer('company-dependencies') {
                include 'com.example:*'
            }
            intoLayer('dependencies')
        }
        layerOrder = [
            'dependencies',
            'spring-boot-loader',
            'snapshot-dependencies',
            'company-dependencies',
            'application'
        ]
    }
}
~~~

When `company-dependencies` exists, **update `LayerDelta.java`** to audit that layer as well and update the Dockerfile to `COPY` the new layer. Otherwise, the report could overlook files even while the build/JAR works.

Do not modify `layers.xml`/Gradle DSL **in the same pass** as verifying code-only or dependency-only changes, as that introduces another variable: files can move between layers even with unchanged bytes.

## 16. Common Discrepancies and How to Diagnose Them

| Symptom | Possible cause | Proper verification step |
| --- | --- | --- |
| `BOOT-INF/layers.idx` missing. | Plain JAR, layers disabled, wrong plugin/config. | Check `jar tf`, `repackage`/`bootJar`, and actual output file. |
| `java -Djarmode=tools` fails to run. | Missing tools dependency, launch script, wrong Boot version. | Check `help`, manifest, executable/`includeTools` settings. |
| Edited Java app yet `dependencies` CHANGED. | Dynamic/SNAPSHOT dependency, repository rewrite, changed graph, or wrong capture. | Diff resolved graph, nested JAR path/hash, and artifact source. |
| Upgraded Commons Lang yet `dependencies` unchanged. | Selected version stayed identical due to constraints/lockfile, or stale package. | `dependencyInsight`/`dependency:tree`, `BOOT-INF/lib`, `layers.idx`. |
| App code unchanged yet `application` CHANGED. | Build-info timestamp, manifest, layer index, generated resource. | Check `~`/`+`/`-` filenames from `LayerDelta` and compare inputs. |
| Core project JAR changed yet `dependencies` unchanged. | Local project/module assigned to `application`. | Read layer index and build relationships. |
| SNAPSHOT changed yet `snapshot-dependencies` not affected. | It is a local project/module or custom layers apply. | Check graph and index. |
| Changed only unit test yet packaged JAR changed. | Test output copied into main, generated metadata, or non-reproducible build. | Compare `BOOT-INF/classes`, resource processing, archive timestamps. |
| Docker gets no cache hits when app changes. | Copying whole JAR, different parent layer, changed context/base/builder. | Inspect Dockerfile, `--progress=plain` logs, and image digests. |
| Java audit does not report custom layer. | `LAYERS` list only contains the four defaults. | Check `list-layers`, add custom layer names. |
| A/B extraction shows strange results. | Reused same destination or extracted over stale files. | Create fresh dirs, confirm A/B artifacts, re-run with isolated inputs. |
| Image fails to run even though whole JAR works. | Missed `COPY`ing a layer, wrong path/launcher/JDK. | Inspect extracted tree, Dockerfile, and runtime container logs. |
| Outer JAR hash changes even when logical content barely differs. | ZIP timestamps/order, metadata, or generated resources. | Compare per-file digests from extracted layers instead of only the JAR hash. |
| `application.properties` embeds secret in image. | Layering does not strip secrets; it only groups files. | Never commit secrets; scan/rotate per policy. |
| Build picks `*-plain.jar`. | Gradle generates multiple artifacts/classifiers. | Select `bootJar` output and verify Boot Loader/`layers.idx`. |

### 16.1. Recommended Investigation Order

1. **Is this the right executable JAR?** Confirm via manifest and `BOOT-INF`.
2. **Is the index really present?** Read `BOOT-INF/layers.idx`.
3. **Did the selected dependency version change?** Maven tree/Gradle insight.
4. **Did tools mode extract the exact artifact into a clean directory?**
5. **Which layer and file changed according to per-file SHA-256?**
6. **Are generated metadata/timestamps introducing noise?**
7. **Do runtime `java -jar` and HTTP/job smoke tests still pass?**
8. **Does the OCI image actually use extraction and caching?** Collect real logs.
9. Do dependency/resource changes introduce any **vulnerability/license/secrets** risks?

Never delete files inside the ZIP, disable tests, or alter layer order just to produce a “clean” `CHANGED`/`UNCHANGED` report.

## 17. Final Lab Exercise and Completion Criteria

### Task A — Baseline A

1. Create the Java 17 Spring Boot project from section 5 and Maven/Gradle build from section 6/7.
2. Run real tests and verify test reports include `layerEndpointReflectsCurrentCode`.
3. Build the executable JAR; inspect `BOOT-INF/classes`, `BOOT-INF/lib`, and `BOOT-INF/layers.idx`.
4. Run jarmode tools `list-layers` and extract A into `captures/A-layers`.
5. Save `A.jar` and the selected dependency graph.
6. Run `java -jar captures/A.jar --server.port=18085`, call `/layer`; expect HTTP 200/`v1:Layered boot`.

### Task B — Code-Only B

1. Change only the Java return prefix from `v1` to `v2` and update the test assertion to match.
2. Build with the same toolchain/config, keeping dependency versions unchanged.
3. Capture `B.jar` and extract into `captures/B-layers`.
4. Run `java LayerDelta captures/A-layers captures/B-layers`.
5. Submit the list of changed/unchanged layers and file-level evidence.
6. HTTP smoke test for B must return `v2:Layered boot`.

### Task C — Dependency-Only C

1. Revert Java source/tests back to A.
2. Upgrade only Commons Lang from `3.14.0` to `3.15.0` or another approved release.
3. Inspect the resolved graph, run tests, capture `C.jar`, and extract separately.
4. Run `java LayerDelta captures/A-layers captures/C-layers`.
5. Inspect the nested Commons Lang JAR and actual `layers.idx`.
6. Report all metadata/`application` layer changes if present, without hiding them to match predictions.

### Task D — Resource-Only, Project Module, and Docker

1. Edit only `application.properties` and inspect the impact on `application`.
2. If using a multi-project build, try editing `core`; observe which layer the local dependency belongs to.
3. If using an external SNAPSHOT, explain why changing a SNAPSHOT can affect `snapshot-dependencies`, while avoiding uncontrolled mutable artifacts in releases.
4. If Docker is available, build images A/B with the same Dockerfile & base image, saving `--progress=plain` logs and cache evidence.
5. Compare logical file-level differences with OCI cache results, noting conditions that cause cache misses.

### Evaluation Checklist

- [ ] Can explain how `BOOT-INF/layers.idx` differs from `BOOT-INF/lib` and Docker image layers.
- [ ] Can name the four default layers and their order.
- [ ] Understand that local Maven modules/Gradle project dependencies normally reside in `application`.
- [ ] Distinguish external releases from external SNAPSHOTs.
- [ ] Configured Maven `repackage` or Gradle `bootJar` with controlled JDK/Wrapper.
- [ ] Know how to read the index via `unzip -p` or `jar xf`.
- [ ] Use `java -Djarmode=tools -jar ... list-layers/extract` properly for Boot 3.3.
- [ ] Captured A/B/C and extracted into three separate dirs without overwriting.
- [ ] Compare files using relative paths + SHA-256 rather than only hashing the whole JAR.
- [ ] Know code-only changes are expected to affect `application` and dependency-only changes usually affect `dependencies`, though metadata can affect other layers.
- [ ] Know test-only changes do not normally enter the runtime archive.
- [ ] Ran `java -jar` and HTTP smoke tests to verify the artifact still works.
- [ ] Do not equate “has `layers.idx`” with “Docker cached four layers”.
- [ ] Understand multi-stage Dockerfile layer COPYs and reading cache logs.
- [ ] Understand how JDK, plugins, timestamps, and generated inputs introduce noise.
- [ ] When using custom layers, update the auditor/Dockerfile/QA to match the real index.
- [ ] Do not embed credentials in JAR/image and know layering does not protect secrets.

**Completion criteria:** learners submit the three artifacts A/B/C, three extracted directories, `layers.idx`, `LayerDelta` outputs for A→B and A→C, dependency reports, JUnit test results, and `java -jar` HTTP smoke output. The summary states **which layers and files actually changed and why**, distinguishing that from real Docker caching. If Docker is unavailable, state clearly “OCI cache not verified” rather than claiming cache hits.

## Official References

- [Spring Boot 3.3.13 — Maven Plugin: Layered Jar or War](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3.13 — Gradle Plugin: Packaging Layered Jar or War](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3.13 — Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3.13 — Dockerfiles and Jarmode Tools](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Gradle — Building Java/JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Docker — Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker — Build Cache](https://docs.docker.com/build/cache/)

**Remember:** **inspect the layer index → create controlled A/B/C builds → extract → compare per-file SHA-256 → verify packaged runtime → measure Docker caching when needed**. Never infer the impact of a code or dependency change solely from the hash of the entire JAR or a `BUILD SUCCESS` line.