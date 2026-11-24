# Separating dependencies, spring-boot-loader, snapshot-dependencies, and application

A **Spring Boot executable JAR** typically contains dozens of runtime libraries, application classes, resources, and Spring Boot startup classes. If the whole JAR file is placed into a Docker image with a single `COPY` instruction, **even a tiny change in application code** can cause the JAR copy step and corresponding image layers to lose reuse benefits. **Layered JARs** solve this problem by describing which parts belong to rarely changing groups (release dependencies, Boot loader) and which parts change frequently (SNAPSHOTs, application code).

In Spring Boot 3.3, the four default layers are **`dependencies`, `spring-boot-loader`, `snapshot-dependencies`, and `application`**, in that order. This lesson explains the **actual classification rules**, how to read `BOOT-INF/layers.idx`, using `jarmode=tools` to list and extract layers, packaging from Maven/Gradle, designing a Dockerfile with separate `COPY` instructions, and customizing rules when a project has multiple modules or internal libraries.

Examples use **Spring Boot 3.3.13, Java 17, Maven 3.9.x, or Gradle 8.x** for consistent syntax. These are illustrative versions, not a claim that they are the latest releases. Jar tool modes change across generations: **Spring Boot 3.3 uses `-Djarmode=tools`**; do not mechanically copy `-Djarmode=layertools` commands from older tutorials.

## 1. What Is a Layered JAR, and How Does It Differ from a Docker Image Layer?

There are two related concepts that are not the same thing:

1. **A layer in a Spring Boot executable archive** is a **logical grouping of JAR entries**, described in an index file. The JAR still contains `BOOT-INF/classes`, `BOOT-INF/lib`, the Boot loader, and the manifest like any standard executable archive.
2. **A layer in a Docker/OCI image** is a storage unit created by each operation in a Dockerfile/build system that can be **reused across image builds** when the corresponding step has not changed.

`BOOT-INF/layers.idx` **does not automatically turn one JAR into four OCI layers** simply by running `docker build` on any Dockerfile. To take advantage of the grouping, the image build tool must **read the index, extract/assemble accordingly, and create the right image layers**. For instance, a Dockerfile with four separate `COPY` commands for the four extracted directories is a clear way to do this.

```text
Spring Boot build output
        |
        v
executable app.jar
  |-- BOOT-INF/classes/        (app code + resources)
  |-- BOOT-INF/lib/            (nested runtime JARs)
  |-- org/springframework/boot/loader/
  |-- BOOT-INF/layers.idx      (logical layer map)
        |
        | java -Djarmode=tools ... extract --layers
        v
extracted/
  |-- dependencies/
  |-- spring-boot-loader/
  |-- snapshot-dependencies/
  |-- application/
        |
        | Dockerfile COPY each directory in order
        v
OCI image layers reusable when corresponding inputs do not change
```

**Remember:** `layers.idx` is **archive metadata**, while `COPY` / the image builder is what constructs **actual OCI layers**. The primary benefit of layering is reducing the bytes that must be rebuilt/uploaded/downloaded when only frequently changing parts change; it does not inherently make the JVM run faster or make dependencies immutable.

## 2. The Four Default Layers and Their Exact Meanings

| Default layer | Main contents | Expected change frequency | Related location in Boot JAR |
| --- | --- | --- | --- |
| **`dependencies`** | External dependencies whose version **does not contain `SNAPSHOT`** | Rarely changes during daily application code edits | Nested JARs under `BOOT-INF/lib` |
| **`spring-boot-loader`** | Boot launcher/loader classes of the executable archive | Usually only changes when changing Boot loader version/config | `org/springframework/boot/loader/**` |
| **`snapshot-dependencies`** | Dependencies **not from a module in the same build** whose version contains `SNAPSHOT` | Can change frequently in dev/integration | Nested JARs under `BOOT-INF/lib` |
| **`application`** | Main app classes and resources **and project/local module dependencies** | Usually changes the most | `BOOT-INF/classes/**` and certain nested module JARs in `BOOT-INF/lib` |

**Default order**:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Spring Boot places groups expected to **change rarely first, and those that change easily last** so OCI image build steps can leverage caching of the base layers. Both the names and order above are Boot 3.3 defaults; if a project has custom layer configuration, trust the **actually packaged index**, rather than predicting from this table.

### 2.1. `dependencies` Does Not Mean Every File in `BOOT-INF/lib`

`BOOT-INF/lib` can contain release libraries, SNAPSHOT libraries, module JARs from the same reactor/project, and jarmode tools. Thus, **just residing in `BOOT-INF/lib` does not place a file in `dependencies`**.

A directly declared dependency `org.apache.commons:commons-lang3:3.14.0` normally goes into `dependencies` if it is an external release dependency. A dependency `com.example:shared:1.0.0-SNAPSHOT` **in the same multi-module build** can go into `application` because project/module matching rules run first. Conversely, an external SNAPSHOT pulled from a repository normally goes into `snapshot-dependencies`.

### 2.2. `spring-boot-loader` Differs from `spring-boot-*.jar` Libraries

Spring Boot launcher classes are stored as `org/springframework/boot/loader/**` entries in the outer executable JAR. That is the `spring-boot-loader` portion. However, `BOOT-INF/lib/spring-boot-3.3.13.jar` is a **Spring Boot runtime library** packaged as a nested JAR, normally belonging to **`dependencies`**.

Seeing both in `jar tf` and assuming both belong in the loader layer is a mistake:
- `org/springframework/boot/loader/launch/JarLauncher.class` → **`spring-boot-loader`**.
- `BOOT-INF/lib/spring-boot-3.3.13.jar` → **`dependencies`** when it is an external release dependency.

Classification is based on **role and rules**, not merely whether the filename contains `spring-boot`.

## 3. Why Is `snapshot-dependencies` Separated?

A release dependency like `com.acme:payment-api:2.3.1` typically never changes content after publication if the repository enforces immutability. By contrast, `com.acme:payment-api:2.4.0-SNAPSHOT` can be published multiple times under the same base version during integration. Mixing both into `dependencies` would allow a single changing SNAPSHOT to invalidate **the layer containing all release libraries**.

Separating SNAPSHOTs into `snapshot-dependencies` helps:
- Keep the `dependencies` layer stable when only a snapshot library updates.
- Provide a layer that can be replaced independently when a snapshot JAR changes.
- Make artifact review clearer: frequently changing components are isolated visibly.

However, this is **not a dependency locking system**:
- A SNAPSHOT can have **the same version string with changed bytes**.
- Docker caching can speed up image builds, **not guarantee today's/tomorrow's build fetches the same snapshot**.
- For reproducible production releases, pin immutable release artifacts and manage the dependency graph and checksums/provenance per policy.

In a project with no external SNAPSHOTs, the `snapshot-dependencies` layer **may be empty or contain no library files**. That is not an error.

## 4. How Are Project Dependencies and Maven Reactor Modules Handled?

This is an important distinction from relying solely on version suffixes.

### Gradle

Gradle multi-project example:

```groovy
dependencies {
    implementation project(':shared')
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

- `project(':shared')` is a **project dependency**, so under default layering it belongs to **`application`**, even if the `:shared` project currently has version `1.0.0-SNAPSHOT`.
- `commons-lang3:3.14.0` is a **non-project released dependency**, so it goes into `dependencies`.
- An external `com.acme:lib:1.0.0-SNAPSHOT` downloaded from a repository will likely go into `snapshot-dependencies`.

### Maven

If `shared` and `boot-app` appear together in the **currently building Maven reactor**, the dependency `com.example:shared:1.0.0-SNAPSHOT` is recognized as a **local module dependency** and defaults to **`application`**.

If `shared` only exists as a JAR in `~/.m2/repository` from an earlier install and is **not part of the current reactor**, the Spring Boot Maven plugin may treat it as a **regular dependency**. When its version contains `SNAPSHOT`, it can end up in **`snapshot-dependencies`**.

| Scenario | Default recognition | Typical layer |
| --- | --- | --- |
| Gradle `implementation project(':shared')` | Project dependency | `application` |
| Maven `shared` as a module in the same reactor | Local module dependency | `application` |
| Maven dependency fetched from local cache outside the reactor | Regular dependency | `dependencies` or `snapshot-dependencies` by version |
| External released JAR | Non-project release | `dependencies` |
| External SNAPSHOT JAR | Non-project SNAPSHOT | `snapshot-dependencies` |

**Conclusion:** “My company's module” does not automatically equal “application layer”. The tool needs to know the dependency is a **module of the current build**, not merely that it has an internal groupId. When suspecting a misclassified layer, check the project dependency/reactor graph before tweaking layer names.

## 5. What Classification Does `BOOT-INF/layers.idx` Record?

A layered executable JAR contains a **layer index** at `BOOT-INF/layers.idx`. This is structured text showing layer names and the entries/paths belonging to each layer.

**Shortened example illustrating shape only** (actual content varies by resolved JARs and plugin-generated order):

```yaml
- "dependencies":
  - "BOOT-INF/lib/spring-boot-3.3.13.jar"
  - "BOOT-INF/lib/commons-lang3-3.14.0.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/launch/JarLauncher.class"
- "snapshot-dependencies":
  - "BOOT-INF/lib/remote-client-1.2.0-SNAPSHOT.jar"
- "application":
  - "META-INF/MANIFEST.MF"
  - "BOOT-INF/classes/"
  - "BOOT-INF/lib/shared-1.0.0-SNAPSHOT.jar"
```

The names `remote-client` and `shared` are hypothetical examples from a multi-module/external SNAPSHOT scenario; the runnable project later in this lesson **does not declare** those libraries. The actual index may record broader directory paths instead of individual files or include additional index/metadata entries. **Do not use this illustration to compare line-by-line against a real archive**.

You can list the JAR and locate the index:

```bash
jar tf target/layer-demo-1.0.0.jar | grep '^BOOT-INF/layers.idx$'
```

With Gradle, use the path `build/libs/layer-demo-1.0.0.jar` instead of `target/...`. On Windows PowerShell:

```powershell
jar tf .\target\layer-demo-1.0.0.jar | Select-String '^BOOT-INF/layers.idx$'
```

**`jar tf` only lists entry names.** To read the contents of `layers.idx` without unpacking, when `unzip` is available:

```bash
unzip -p target/layer-demo-1.0.0.jar BOOT-INF/layers.idx
```

If `unzip` is not installed, create a temporary directory, run `jar xf ../target/layer-demo-1.0.0.jar BOOT-INF/layers.idx`, and read the text file. Do not extract the whole JAR into a directory containing important data.

## 6. How Does Layering Optimize Docker/OCI Caching?

Dockerfile without layers:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/layer-demo-1.0.0.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
```

The `COPY` command places the **entire JAR** into one image layer. Changing a class in `BOOT-INF/classes` generally changes the JAR's bytes, causing the layer containing the JAR to change as well, even though most dependencies stayed the same.

Layered Dockerfile:
- Copy `dependencies` first.
- Copy `spring-boot-loader` next.
- Copy `snapshot-dependencies` next.
- Copy `application` last.

When only app code changes, the rarely changing layers **have the opportunity to reuse cache/image blobs**. When the Boot plugin version changes, the loader layer and possibly runtime dependencies change; when a SNAPSHOT library changes, the snapshot layer changes. This is an **expected benefit depending on content/hashes and how Docker/BuildKit/buildpacks build images**, not a promise that every build changes only one layer or achieves a specific speed.

**Layer order is cache priority order, not the order in which Spring Boot loads beans or classes.** Classpath order is a separate matter, potentially influenced by `BOOT-INF/classpath.idx`. Do not use `layerOrder` to resolve runtime bean/resource conflicts.

## 7. Sample Java 17 Spring Boot Project for Building a Layered JAR

Common structure for Maven or Gradle:

```text
layer-demo/
├── pom.xml                   (if choosing Maven)
├── settings.gradle           (if choosing Gradle)
├── build.gradle              (if choosing Gradle)
└── src/
    └── main/
        ├── java/com/example/layers/
        │   └── LayerDemoApplication.java
        └── resources/demo/
            └── build-marker.txt
```

The example uses no database, broker, HTTP server, or external SNAPSHOT. This lets you observe the **default layers** and verify that resources remain readable after packaging without needing a private repository to practice.

### 7.1. Application Source Code

Create `src/main/java/com/example/layers/LayerDemoApplication.java`:

```java
package com.example.layers;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class LayerDemoApplication {

    public static void main(String[] args) throws IOException {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(LayerDemoApplication.class, args)) {
            try (InputStream in = LayerDemoApplication.class
                    .getClassLoader()
                    .getResourceAsStream("demo/build-marker.txt")) {
                if (in == null) {
                    throw new IOException("Missing resource demo/build-marker.txt");
                }
                String marker = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("layer-demo=" + marker.strip());
            }
        }
    }
}
```

Create `src/main/resources/demo/build-marker.txt` containing **one line**:

```text
layered-jar-ok
```

When running the proper executable JAR, the program prints:

```text
layer-demo=layered-jar-ok
```

Spring Boot may print additional startup logs; the line above is **stdout from application code**, not the entire output. `spring-boot-starter` does not include a web server in this application, and `ConfigurableApplicationContext` is closed after reading the resource so the Java process exits.

If the resource does not make it into the archive, the program throws an `IOException` with a clear message. This helps test that **layer extraction and runtime classpath preserve contents accurately**.

## 8. Complete Maven POM: Default Layering

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>layer-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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

Maven's Spring Boot parent manages the plugin version and `repackage` execution, so `mvn package` converts the JAR into a **Spring Boot executable JAR**. In Spring Boot 3.3, layered archives and `layers.idx` **are enabled by default**; there is no need to add an external plugin to attach the four layer names.

From the project root:

```bash
./mvnw clean package
jar tf target/layer-demo-1.0.0.jar
java -jar target/layer-demo-1.0.0.jar
```

If you do not have a Maven Wrapper, use a compatible `mvn`; on Windows PowerShell, use `.\mvnw.cmd`. The expected program output line is `layer-demo=layered-jar-ok`. Inside `target`, any `*.jar.original` file is the plain JAR before `repackage`; **do not use it as the target for inspecting the layered executable archive**.

**If importing only the Spring Boot BOM without inheriting the starter parent:** a BOM managing dependency versions **does not automatically configure the `repackage` plugin execution**. You must declare the plugin version and execution separately. When `BOOT-INF/layers.idx` is missing, first check whether the artifact was actually repackaged.

## 9. Complete Gradle Groovy DSL: Default Layering

Create `settings.gradle`:

```groovy
rootProject.name = 'layer-demo'
```

Create `build.gradle`:

```groovy
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
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}

springBoot {
    mainClass = 'com.example.layers.LayerDemoApplication'
}
```

The Spring Boot Gradle plugin applies conventions so the `bootJar` task builds a layered executable JAR when combined with the Java plugin. You do not need to declare `layered { enabled = true }` to receive the four default layers unless the project has overridden this rule.

Run:

```bash
./gradlew clean bootJar
jar tf build/libs/layer-demo-1.0.0.jar
java -jar build/libs/layer-demo-1.0.0.jar
```

If you do not have a Gradle Wrapper, use a compatible `gradle`; PowerShell uses `.\gradlew.bat`. When Gradle also produces `layer-demo-1.0.0-plain.jar`, inspect **`layer-demo-1.0.0.jar` from `bootJar`**, not `-plain.jar` from `jar`. A plain JAR lacks the Boot loader and nested dependency layout and is insufficient for testing the four layers.

### 9.1. Equivalent Kotlin DSL (If Using `build.gradle.kts`)

A project can replace the Groovy file with Kotlin DSL. Corresponding configuration:

```kotlin
plugins {
    java
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
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

springBoot {
    mainClass.set("com.example.layers.LayerDemoApplication")
}
```

This is an **alternative `build.gradle.kts`**, not a snippet to mix into a Groovy `build.gradle`. Keep a matching `settings.gradle.kts` with `rootProject.name = "layer-demo"`. All default layering behavior remains the same.

## 10. Inspecting `layers.idx` and the Exact Four Layer Names

After running either build command, store the artifact path in a shell variable for easier inspection.

**Linux/macOS with Maven artifact:**

```bash
JAR=target/layer-demo-1.0.0.jar
jar tf "$JAR" | grep -E '^(BOOT-INF/layers[.]idx|BOOT-INF/classes/|BOOT-INF/lib/|org/springframework/boot/loader/)'
unzip -p "$JAR" BOOT-INF/layers.idx
```

**Linux/macOS with Gradle artifact:**

```bash
JAR=build/libs/layer-demo-1.0.0.jar
jar tf "$JAR" | grep 'BOOT-INF/layers.idx'
unzip -p "$JAR" BOOT-INF/layers.idx
```

**Windows PowerShell:**

```powershell
$jar = '.\build\libs\layer-demo-1.0.0.jar'
jar tf $jar | Select-String '^BOOT-INF/layers.idx$'
```

PowerShell does not necessarily have `unzip`. When you need to read the index, create an empty temporary directory, enter it, run `jar xf ..\build\libs\layer-demo-1.0.0.jar BOOT-INF/layers.idx`, and then `Get-Content .\BOOT-INF\layers.idx`. If using Maven, replace `build\libs` with `target`.

For the sample project:
- `dependencies` is expected to contain Spring Boot/Commons Lang release JARs.
- `spring-boot-loader` is expected to contain loader classes.
- `application` is expected to contain `LayerDemoApplication.class`, the `demo/build-marker.txt` resource, and app-related manifest/metadata.
- `snapshot-dependencies` does not need to contain any JARs because the sample project **declares no external SNAPSHOTs**.

**Do not match index contents against fixed dependency names from another machine**; transitive libraries can differ if you change the BOM/plugin. Verify **logic**, layer names, the right app classes/resources, and the actual packaged libs.

## 11. `jarmode=tools`: Listing and Extracting Properly for Spring Boot 3.3

Spring Boot 3.3 includes `spring-boot-jarmode-tools` inside layered archives (by plugin default). It enables running the JAR in tool mode **without starting the Spring application**.

View the command list:

```bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar
```

Important Boot 3.3 commands are:
- `list-layers`: lists extractable layer names.
- `extract`: extracts the archive into files/directories; with `--layers`, separates them by layer.
- `help`: help information.

List layers:

```bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar list-layers
```

Names expected under the default configuration:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

These are **the logical names to verify**; do not claim the tool always prints strictly four lines with no other output.

Extract with a specified destination directory:

```bash
java -Djarmode=tools -jar target/layer-demo-1.0.0.jar extract --layers --destination extracted
```

The tool creates a directory structure suitable for building layered container images. Depending on the tool mode/extraction layout, there may also be an `application.jar` file used to run after combining the directories; the official Boot 3.3 Dockerfile uses this file. Use `list-layers`/`help` and inspect the generated directory instead of guessing all filenames.

**If not using Maven**, replace `target/layer-demo-1.0.0.jar` with `build/libs/layer-demo-1.0.0.jar`. **Do not use**:
- `-Djarmode=layertools` (common in Spring Boot 2.x/3.2) for this Boot 3.3 example.
- `java -jar app.jar extract` without `-Djarmode=tools`; in that case the JVM may start the app and pass `extract` as an application argument.
- `extract --layers` syntax on a JAR lacking the proper tool or having a launch script that interferes with tool mode.

## 12. Why Does the Dockerfile `COPY` the Four Layers in Order?

After extracting with `tools`, an ideal Dockerfile splits each group into its own `COPY` command:

```dockerfile
# Dockerfile for the Spring Boot 3.3.13 Maven demo project
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /workspace

COPY target/layer-demo-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
```

This is a **complete multi-stage Dockerfile** illustrating Boot 3.3 and Java 17. It assumes `target/layer-demo-1.0.0.jar` was built **before** invoking Docker. With Gradle, change the `COPY target/...` line to `COPY build/libs/layer-demo-1.0.0.jar application.jar`. Do not use the `*.jar` glob when the same directory also holds `*-plain.jar` or artifacts with other classifiers.

Try it:

```bash
./mvnw clean package
docker build -t layer-demo:1.0.0 .
docker run --rm layer-demo:1.0.0
```

Line printed by the Java application:

```text
layer-demo=layered-jar-ok
```

The Dockerfile builds an OCI image using four `COPY`s matching the default order. When only an app class/resource changes without changing release libraries:
- `dependencies` has the opportunity to be reused.
- `spring-boot-loader` has the opportunity to be reused.
- `snapshot-dependencies` has the opportunity to be reused if unchanged.
- `application` reflects the new change.

You cannot guarantee **exactly how much build time decreases**: it depends on available Docker/BuildKit cache, CI environment, actual bytes, artifact metadata, and network. Even though the extractor stage may have to rerun because the outer JAR changed, the copy layers in the runtime stage can still be reused based on content.

### 12.1. `application.jar` in the Image Is Not the Intact Outer Uber JAR

After `extract --layers` in `tools` mode, Spring Boot provides a layout suitable for running the app from the copied layers. The `application.jar` file in the final image **does not need to be the outer JAR containing all nested libraries like the build stage input**. It can be a launcher JAR referencing the extracted files. **Do not change ENTRYPOINT to `java -jar target/layer-demo-1.0.0.jar`** in the extracted image unless you copied that file into the right place.

Use the exact Boot 3.3 Dockerfile with `ENTRYPOINT ["java", "-jar", "application.jar"]`, and smoke-test the real image. Do not manually copy only `BOOT-INF/classes` and omit the loader/manifest/classpath structure.

## 13. Maven `repackage`: Enabling/Disabling Layers and Tools Option

The Spring Boot 3.3 Maven plugin has `<layers>` to control the layer index. The default configuration enables it; to **disable** it when there is a reason:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>false</enabled>
        </layers>
    </configuration>
</plugin>
```

This is a **replacement plugin snippet** inside `<build><plugins>` of the POM, not a complete POM. Once `layers.idx` is disabled, do not use a Dockerfile expecting `extract --layers` to produce all four groups.

If you want to keep `layers.idx` while **excluding jarmode tools** to reduce auxiliary code in the archive, Spring Boot 3.3 supports `includeTools`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>false</includeTools>
    </configuration>
</plugin>
```

**Consequence:** the `java -Djarmode=tools -jar ...` command cannot rely on a tool that was excluded. Only use `includeTools=false` when your image builder has another extraction method or compatible buildpacks/tooling. Do not disable tools and then use the Dockerfile from section 12.

`spring-boot-maven-plugin` must actually run the `repackage` goal. If the project does not inherit from starter parent, declare the plugin version and execution explicitly. A main JAR is typically created by `maven-jar-plugin` prior to `repackage`.

## 14. Gradle `bootJar`: Enabling/Disabling Layers and Extract Tools

With Gradle Groovy DSL, disable the layer index:

```groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
```

This is an **additional or replacement configuration for the `bootJar` task** inside an existing `build.gradle`. Disable tools while keeping the layer index:

```groovy
tasks.named('bootJar') {
    includeTools = false
}
```

With Gradle Kotlin DSL:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
```

In Spring Boot 3.3, `includeTools` is a property on the `bootJar` task; do not copy `layered { includeLayerTools = false }` from older Spring Boot versions expecting the syntax to stay the same. **All snippets in this section are configuration choices**; you should not both disable tools and run an extraction Dockerfile that depends on tools.

If the project uses `bootWar`, the layering principle is similar, though the archive layout is `WEB-INF/classes` and `WEB-INF/lib`/`WEB-INF/lib-provided`, rather than `BOOT-INF/classes`/`BOOT-INF/lib` like JAR. Apply the Dockerfile/JAR commands in these examples only when the artifact is a Boot JAR.

## 15. Gradle Customizing the Four-Layer Rules in Claim Order

If you want to understand how Spring Boot decides each layer's contents, you can **redeclare the default rules**. The following Groovy DSL snippet goes in a `build.gradle` with the Spring Boot plugin:

```groovy
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
            intoLayer('dependencies')
        }
        layerOrder = [
            'dependencies',
            'spring-boot-loader',
            'snapshot-dependencies',
            'application'
        ]
    }
}
```

**Two different orders:**

1. **`intoLayer` order (claim):** when the plugin inspects an archive part, an **earlier** rule gets the first chance to claim it. `includeProjectDependencies()` must precede the SNAPSHOT matcher so local project dependencies stay in `application`. Then `*:*:*SNAPSHOT` claims external snapshots, and finally the fallback claims remaining external releases.
2. **`layerOrder` order (output):** determines the order in which layers are written into the index/used when building images to optimize caching. It is `dependencies → spring-boot-loader → snapshot-dependencies → application`.

**Do not take the `intoLayer` order and copy it straight into `layerOrder`.** Doing so risks accidentally putting `application` in an early layer and ruining cache efficiency, or letting a broad rule at the top “swallow” every dependency before the snapshot matcher is checked.

Matchers in `application` use Ant-style paths like `org/springframework/boot/loader/**`. Matchers in `dependencies` use coordinate-style patterns `group:artifact[:version]`; `*:*:*SNAPSHOT` matches versions containing `SNAPSHOT`. `includeProjectDependencies()` is a rule for **project dependencies**, not a string match on a library name.

## 16. Gradle Kotlin DSL: Equivalent Four-Layer Rules

If the project uses `build.gradle.kts`, the equivalent Kotlin DSL snippet (placed below the `plugins` block of the existing file):

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }
            intoLayer("application")
        }
        dependencies {
            intoLayer("application") {
                includeProjectDependencies()
            }
            intoLayer("snapshot-dependencies") {
                include("*:*:*SNAPSHOT")
            }
            intoLayer("dependencies")
        }
        layerOrder.set(
            listOf(
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "application"
            )
        )
    }
}
```

This is an **additional configuration snippet for Gradle Kotlin DSL**, not a complete `build.gradle.kts` file; apply the `java` and `org.springframework.boot` plugins in the `plugins` block as in section 9. Import `BootJar` properly; in some Gradle scripts and IDE environments, `tasks.named<BootJar>` works once the plugin is applied.

If no layer adjustments are needed, **keeping Spring Boot's defaults** is less error-prone. Do not copy custom rules just to show you are “optimizing”; this lesson uses them to explain how groups are classified.

## 17. Maven Customizing Layering with `layers.xml`

With Maven, complex layer configuration lives in a **standalone XML file**, such as `src/layers.xml`, read by the Spring Boot Maven plugin during `repackage`.

Add the configuration inside the `spring-boot-maven-plugin` declaration in the sample POM (do not declare the plugin twice):

```xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <configuration>${project.basedir}/src/layers.xml</configuration>
    </layers>
</configuration>
```

File `src/layers.xml` describing **the four default layers explicitly**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
        <into layer="dependencies"/>
    </dependencies>

    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-boot-loader</layer>
        <layer>snapshot-dependencies</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
```

Points to note:
- This XML file **is not `pom.xml`**; it has a `<layers>` root and the schema matching Spring Boot 3.3.
- `<application>` classifies Boot loader classes and app classes/resources.
- `<dependencies>` classifies local reactor modules, external SNAPSHOTs, and external released dependencies.
- `<includeModuleDependencies/>` is the Maven mechanism corresponding to the idea of `includeProjectDependencies()` in Gradle.
- `<layerOrder>` must list **every layer** used by `<into>`.
- The order of `<into>` elements affects **first-claim rules**, while `layerOrder` affects **layer order in the index/image**.

When editing the custom file, run `./mvnw clean package` and re-read `BOOT-INF/layers.idx`. If the XML has a schema error, layer name typo, or omitted entry, **do not assume the archive is still valid**; inspect the build error and actual index.

## 18. When Should Internal Libraries Be Split into a Separate Layer?

In large projects, there may be a set of company-published libraries released more frequently than Spring Boot dependencies but changing less often than each service's code. In that case, a `company-dependencies` layer can be helpful.

**Note:** this is an **additional customization**, no longer strictly the four default layers that B209 wants you to understand. Consider it only after accurately verifying the four original layers and measuring caching behavior.

### Gradle Example

Groovy snippet replacing the `dependencies` and `layerOrder` parts inside the `layered` configuration from section 15:

```groovy
dependencies {
    intoLayer('application') {
        includeProjectDependencies()
    }
    intoLayer('snapshot-dependencies') {
        include '*:*:*SNAPSHOT'
    }
    intoLayer('company-dependencies') {
        include 'com.acme:*'
    }
    intoLayer('dependencies')
}

layerOrder = [
    'dependencies',
    'spring-boot-loader',
    'company-dependencies',
    'snapshot-dependencies',
    'application'
]
```

This is an **additional configuration snippet inside `layered { ... }`**, not project-level Gradle `dependencies { implementation ... }`. Keep the `application { ... }` section from section 15. The `com.acme:*` matcher is an example for a hypothetical company group, not an existing default external repository.

### Maven Example

In `src/layers.xml`, replace `<dependencies>` and `<layerOrder>` from section 17 with:

```xml
<dependencies>
    <into layer="application">
        <includeModuleDependencies/>
    </into>
    <into layer="snapshot-dependencies">
        <include>*:*:*SNAPSHOT</include>
    </into>
    <into layer="company-dependencies">
        <include>com.acme:*</include>
    </into>
    <into layer="dependencies"/>
</dependencies>

<layerOrder>
    <layer>dependencies</layer>
    <layer>spring-boot-loader</layer>
    <layer>company-dependencies</layer>
    <layer>snapshot-dependencies</layer>
    <layer>application</layer>
</layerOrder>
```

The snippet above consists of **two XML sections to replace inside `<layers>`**, not a standalone `layers.xml` file. When adding a new layer to the index, **the Dockerfile must also add a corresponding `COPY`** in the same order, otherwise libraries will be missing or run with the wrong classpath.

**Important priority rule:** if you want internal SNAPSHOTs to go into `snapshot-dependencies` instead of `company-dependencies`, place the SNAPSHOT matcher **before** the company matcher. If you want internal modules in the same reactor to go into `application`, place `includeModuleDependencies` **before** the other matchers.

## 19. When Does `layers.idx` Exist Yet Caching Still Fails to Help?

Common causes:

1. The Dockerfile still uses a single `COPY app.jar` instead of extracting and running `COPY` per layer.
2. Using `COPY . .` too early, causing source changes to affect all subsequent steps or accidentally copying stale `target`/`build`.
3. The JAR contains generated resources with a per-build timestamp, making `application` always change (which may be acceptable if only the application layer changes).
4. Dynamic/changing/SNAPSHOT dependencies are updated unexpectedly; `snapshot-dependencies` or even `dependencies` changes.
5. Gradle/Maven/BOM locks are unstable, leading to different dependency versions across CI runners.
6. Docker build cache on CI is wiped, a different builder is used, or the base image is updated, so expected cache is missing.
7. Placing constantly changing internal modules in the `dependencies` layer, forcing the “rarely changing” library group to rebuild.
8. Customizing `layerOrder` to put `application` first, causing subsequent layers to be invalidated along the cache chain.
9. Changing the Spring Boot plugin/runtime JDK, altering multiple layers simultaneously.
10. Building images through a tool with its own cache/layer mechanism while measuring against expectations of a custom Dockerfile.

**`layers.idx` is a classification tool, not a version-locking tool or a universal build accelerator.** When benchmarking, compare two builds with **the same environment and controlled cache state**, inspect `docker history`/logs and changed blob sizes, and do not claim cache hits merely because you see four layer names.

## 20. Comparing Application, Dependency, and Boot Version Changes

| Action | Layer likely to change | Layers with a chance to keep cache |
| --- | --- | --- |
| Edit `LayerDemoApplication.java` | `application` | `dependencies`, `spring-boot-loader`, `snapshot-dependencies` |
| Edit `demo/build-marker.txt` | `application` | Remaining three layers if inputs do not change |
| Upgrade `commons-lang3` release from `3.14.0` to another version | `dependencies` | Loader may remain unchanged; later layers depend on cache chain |
| External SNAPSHOT JAR republished | `snapshot-dependencies` | `dependencies` and loader if unchanged |
| Edit a Gradle project dependency in the same build | `application` | `dependencies` and loader if unchanged |
| Change Spring Boot plugin/loader version | `spring-boot-loader`, often also `dependencies` | No guarantee of preserving cache on other layers |
| Add a new external release library | `dependencies` | Loader preserved only if implementation stays unchanged |
| Change custom layer rules/index | Can affect **many layers and how the image is assembled** | Must re-evaluate because the mapping changed |
| Change only Docker base image | Base layers change; subsequent steps may rebuild | Do not assume cache remains intact |

The table is an **expected analysis**, not a live simulation run. When an earlier layer in the Dockerfile changes, subsequent steps can lose effective caching even if their own source directories did not change. The remedy is to measure in practice and prioritize placing stable parts earlier.

## 21. Are `bootBuildImage`, Buildpacks, and Custom Dockerfiles the Same?

Spring Boot Maven/Gradle provide OCI image-building goals/tasks such as `spring-boot:build-image` and `bootBuildImage` using **Cloud Native Buildpacks**. They can optimize classpaths and image layers in their own way, not necessarily executing the **exact four `COPY` instructions** of the Dockerfile in section 12.

The differences:
- **`bootJar`/`repackage`**: creates the executable JAR and `layers.idx`.
- **`jarmode=tools`**: lists/extracts the archive by layers.
- **Custom Dockerfile**: you control `COPY`, base image, ENTRYPOINT, users, and cache strategy.
- **Buildpacks**: builder/lifecycle/cache/OCI layers are managed by the buildpack; check buildpack docs and outputs for the actual layout.

Do not compare an image from buildpacks with a custom Dockerfile and conclude one side “lost the `spring-boot-loader` layer” just because `docker history` looks different. The benefit is **isolating inputs that change at different cadences**, not creating strictly four layers at all costs.

If the target is an application running directly via `java -jar` on a VM/bare metal, layered metadata may not bring clear container caching benefits; you can still keep defaults since it does not affect normal startup behavior.

## 22. How to Verify Correct Layer Names, Order, and Contents in CI

A minimal CI verification step after packaging:

1. Identify the **exact executable JAR file**, not `-plain.jar`.
2. Verify `jar tf` includes `BOOT-INF/layers.idx` and the Boot loader.
3. Use `jarmode=tools list-layers`; confirm the four default layer names appear in expected order.
4. Use `extract --layers --destination ...` to inspect the directories.
5. Verify application classes/resources are present after extraction.
6. Verify release dependencies reside in the stable group; SNAPSHOTs, if any, go into the appropriate group.
7. Build the Docker image and run an application smoke test.
8. Save build logs, container image digest, and check SBOM/versions if policy requires.

**Bash (Maven demo; requires JDK 17, `grep`, and `jar`):**

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR=target/layer-demo-1.0.0.jar

test -s "$JAR"
jar tf "$JAR" > jar-entries.txt

grep -Fx 'BOOT-INF/layers.idx' jar-entries.txt
grep -Fx 'BOOT-INF/classes/com/example/layers/LayerDemoApplication.class' jar-entries.txt
grep -Fx 'BOOT-INF/classes/demo/build-marker.txt' jar-entries.txt
grep -E '^BOOT-INF/lib/.*[.]jar$' jar-entries.txt

java -Djarmode=tools -jar "$JAR" list-layers > layers-list.txt
grep -Fx 'dependencies' layers-list.txt
grep -Fx 'spring-boot-loader' layers-list.txt
grep -Fx 'snapshot-dependencies' layers-list.txt
grep -Fx 'application' layers-list.txt

java -Djarmode=tools -jar "$JAR" extract --layers --destination extracted

test -f extracted/application/BOOT-INF/classes/com/example/layers/LayerDemoApplication.class
test -f extracted/application/BOOT-INF/classes/demo/build-marker.txt
test -d extracted/dependencies
test -d extracted/spring-boot-loader

java -jar "$JAR" > app-smoke.log
grep -Fx 'layer-demo=layered-jar-ok' app-smoke.log
```

This script uses the **exact sample project** and `list-layers` outputs each layer name on its own line in Boot 3.3. When customizing layers, update assertions/paths accordingly. Do not run the script from another directory if the artifact path does not match. On Windows, use PowerShell and `jar tf` / `Select-String`, or run checks in Linux CI.

**Do not use `grep` on directory names as a substitute for verifying contents**: `layers.idx` can declare a group while a library still fails to enter the archive due to wrong dependency scope/configuration. For high confidence, verify specific external JARs and project JARs against the graph. For Boot 3.3 extraction output, verify the actual class/resource paths under `extracted/application/BOOT-INF/classes`.

## 23. Common Errors When Creating and Using the Four Layers

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| JAR lacks `BOOT-INF/layers.idx` | Build produced plain JAR, plugin did not repackage, or layering disabled | Check Maven `repackage` / Gradle `bootJar`, `<layers><enabled>`, or `layered.enabled` |
| `java -Djarmode=tools` does not recognize command | Tools excluded, wrong Boot version, or JAR has embedded launch script | Check `includeTools`, Boot version, do not use fully executable launch script |
| Script using `-Djarmode=layertools` fails | Confused with older Boot syntax | For Boot 3.3 use `-Djarmode=tools` and `list-layers`/`extract --layers` |
| `snapshot-dependencies` is empty | No external SNAPSHOTs | This can be valid; do not add a fake SNAPSHOT just to “fill all layers” |
| Internal SNAPSHOT JAR lands in `application` | It is a Gradle project dependency or Maven reactor local module | This is usually the correct default classification |
| Internal dependency via Maven local cache lands in snapshot layer | Not part of the currently building reactor | Check reactor modules; use multi-module build if local module recognition is desired |
| `spring-boot-3.3.13.jar` is in dependencies rather than loader | It is a runtime lib, not Boot loader classes | Distinguish `BOOT-INF/lib` from `org/springframework/boot/loader/**` |
| Layer index has four names but Docker image has one app copy layer | Dockerfile `COPY outer.jar` in one step | Use tools extract and separate `COPY` for directories |
| Docker build cache still misses | Base image/dependency/plugin changed, CI cache lost, volatile file metadata | Compare contents, lock dependencies, inspect Docker/BuildKit logs |
| Container image throws `ClassNotFoundException` | Missing an extracted directory group or custom layer not `COPY`ed | Compare `layers.idx` against every `COPY` in the Dockerfile |
| App resource missing after extract | Copied wrong path, custom rule did not claim resource | Check `BOOT-INF/classes/demo/build-marker.txt` in index/extraction |
| Maven custom `layers.xml` does not load | Wrong XML path/schema, misplaced plugin config | Check `layers.configuration` and `repackage` plugin logs |
| Gradle custom layers misordered | Confused `intoLayer` order with `layerOrder` | Claim rules run first, output order is separate and must include all layers |
| JAR runs `java -jar` fine but cache is poor | Runtime works, but extraction/COPY/cache not optimized | Evaluate Dockerfile and layer reuse; do not treat runnable as sufficient |
| Plain JAR cannot read Boot layer tools | Not a Spring Boot executable JAR | Run the proper `bootJar` or `repackage` artifact |
| Custom `company-dependencies` missing in final image | Dockerfile still copies only the four default layers | Add corresponding directory/`COPY` and smoke-test |
| Changed SNAPSHOT version yet release layer hash changed | Graph/transitive dependencies may also have changed | Inspect resolved graph, BOM, repository, and archive metadata |
| Build differs between IDE and Docker | Different toolchain, dependency resolution, packaging/runtime | Pin Java 17, plugin versions, and use the right packaged artifact |

## 24. Checklist for Understanding and Applying the Four Layers

- [ ] Distinguished **Spring Boot archive layers** from **Docker/OCI image layers**.
- [ ] Mastered the **default order**: `dependencies → spring-boot-loader → snapshot-dependencies → application`.
- [ ] Know `dependencies` holds external non-SNAPSHOT release dependencies, **not** all of `BOOT-INF/lib`.
- [ ] Know `spring-boot-loader` holds launcher/loader classes in the outer archive, **distinct from** nested `spring-boot-*.jar`.
- [ ] Know `snapshot-dependencies` holds external SNAPSHOTs and can be empty when there are none.
- [ ] Know `application` holds app classes/resources and local Gradle project/Maven reactor module dependencies.
- [ ] Do not confuse “internal group” with “module inside the current reactor/project”.
- [ ] `jar tf` shows `BOOT-INF/layers.idx`, and the index reflects accurate names/order/contents.
- [ ] Use **Spring Boot 3.3's `-Djarmode=tools`**, not mixing commands from older versions.
- [ ] Know `list-layers` and `extract --layers --destination`, along with layer paths after extraction.
- [ ] Maven `spring-boot-maven-plugin` executed `repackage`, Gradle used `bootJar`; do not pick plain JARs.
- [ ] If customizing Gradle, `intoLayer` governs **claim order** and `layerOrder` governs **output order**.
- [ ] If customizing Maven, `layers.xml` has complete `application`, `dependencies`, and `layerOrder` matching the schema.
- [ ] Every custom layer appearing in the index is handled/copied completely by the image builder.
- [ ] The Dockerfile genuinely layers via `COPY` operations rather than copying the whole outer JAR.
- [ ] Do not treat the SNAPSHOT layer as a version/byte-locking mechanism; releases still need an immutable artifact policy.
- [ ] Tested `java -jar` on the packaged archive **and** smoke-tested the OCI image after extraction.
- [ ] CI validates layers using real files, dependency graphs, and image provenance, rather than guessing from filenames.

**Remember:** `dependencies` holds external release libraries, `spring-boot-loader` holds loader classes, `snapshot-dependencies` holds external SNAPSHOT libraries, and `application` holds application code/resources plus local project/module dependencies. **Claim rules** decide which layer an entry belongs to, **layer order** decides the placement order for cache optimization, and **Dockerfile/buildpacks** turn those groups into real OCI layers. Verify via **`layers.idx → jarmode tools → extracted directories → image COPY → smoke test`**.

## Official References (Specific to Spring Boot 3.3 Branch)

- [Spring Boot 3.3 — Gradle Plugin: Packaging Layered Jar or War](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 — Maven Plugin: Layered Jar or War / Custom Layers](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3 — Dockerfiles and jarmode tools](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Gradle — Dependencies and Project Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html)
- [Docker — Optimizing Builds with Cache](https://docs.docker.com/build/cache/optimize/)