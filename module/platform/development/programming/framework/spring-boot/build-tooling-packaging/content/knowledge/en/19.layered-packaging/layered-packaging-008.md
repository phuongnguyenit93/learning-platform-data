# Identifying Differences Between jarmode tools and layertools Across Spring Boot Versions

## 1. Why Distinguish Versions When Extracting JAR Layers?

A Dockerfile borrowed from a Spring Boot 3.2 project might contain the command:

```bash
java -Djarmode=layertools -jar application.jar extract
```

When upgrading to Spring Boot 3.5 or 4.1, you should not keep that syntax unchanged merely because the executable JAR still has `BOOT-INF/layers.idx`. Spring Boot changed the **built-in JAR mode**, **subcommand names**, **extracted directory layout**, **supporting dependency JAR**, and **build plugin configuration**.

Two names to distinguish:

- **`layertools`**: legacy JAR mode backed by the `spring-boot-jarmode-layertools` artifact; common from when layered JARs arrived in Spring Boot 2.3 through the 3.2 line.
- **`tools`**: newer JAR mode backed by `spring-boot-jarmode-tools`, introduced in Spring Boot **3.3**, supporting **per-layer** extraction as well as an **extracted layout better optimized for running apps/CDS**.

**Practical takeaway:** for Boot **3.3 and later**, prefer `-Djarmode=tools`. To reproduce the old `layertools extract` behavior (four layer directories for Dockerfile COPYs), the new command must include **`extract --layers`**. Do not confuse it with `tools extract` **without `--layers`**, because the default mode produces a different directory structure.

This lesson uses Java 17 and Spring Boot 3.5.16 examples for practice, while clearly showing how to handle Boot 3.2 artifacts and the removal milestone in 4.1. These are **pinned illustrative versions**, not a recommendation to change your project's active release without verifying compatibility.

### Lesson Outcomes

1. Look at a Dockerfile or CI script and identify whether it uses `layertools` or `tools`.
2. Compare Boot **2.3–3.2**, **3.3–4.0**, and **4.1+** on JAR mode name, commands, dependency, and support status.
3. Distinguish `layers.idx`, `classpath.idx`, nested dependencies, and the tool JAR.
4. Run `list`/`list-layers`, `extract`/`extract --layers`, and `help` matching the **artifact version**.
5. Understand the old `includeLayerTools` and new `includeTools` settings in Maven/Gradle, independent of enabling/disabling `layers.idx` generation.
6. Package a Java 17 executable Spring Boot JAR, inspect the archive, extract layers, and run the app from both the original JAR and the extracted structure.
7. Migrate a Dockerfile to the new layout without copying the wrong legacy loader entrypoint.
8. Diagnose errors when the tool JAR is excluded, the layers index is missing, or the archive has a launch script (fully executable JAR).

## 2. Milestones of Changes Across Spring Boot Versions

| Version line | Recommended JAR mode | Basic commands | Tool JAR / configuration |
|---|---|---|---|
| **Boot 2.3 through 3.2.x** | `layertools` | `list`, `extract`, `help` | `spring-boot-jarmode-layertools`, `layers.includeLayerTools` |
| **Boot 3.3.x** | **`tools`**; `layertools` deprecated | `list-layers`, `extract`, `help` | `spring-boot-jarmode-tools`, `includeTools` |
| **Boot 3.4.x – 3.5.x** | **`tools`** | `list-layers`, `extract`, `help` | `includeTools` in Maven/Gradle packaging |
| **Boot 4.0.x** | **`tools`** | `list-layers`, `extract`, `help` | Use new configuration, avoid relying on legacy syntax |
| **Boot 4.1.x and newer** | **`tools`** | `list-layers`, `extract`, `help` | `layertools` **was removed** in 4.1 |

Officially announced historical milestones:

- Spring Boot **2.3** added layered JARs for Docker/OCI images and the `layertools` JAR mode.
- Spring Boot **3.3** introduced `tools` with an extraction mode optimized for **Class Data Sharing (CDS)**, migrated old `layertools` operations to new commands, and deprecated the old interface.
- Spring Boot **4.1** removed the deprecated `layertools`. When a project runs Boot 4.1, `-Djarmode=layertools` **is no longer a supported option** and must be migrated to `tools`.

**Distinguish “deprecated” from “removed”:** 3.3 announced you should stop using the old interface; 4.1 deleted that interface altogether. For 3.3–4.0 artifacts, **do not assume** the packaged JAR carries both tool JARs or that every old command still works. Inspect `BOOT-INF/lib` and test the actual built artifact to know its real capabilities. Using the new syntax is the safest path for long-term Dockerfiles and CI.

### Most Important Command Conversion Matrix

| Purpose | Legacy `layertools` (Boot 3.2) | `tools` (Boot 3.3+) |
|---|---|---|
| Print available operations | `java -Djarmode=layertools -jar app.jar` | `java -Djarmode=tools -jar app.jar` |
| View layers | `java -Djarmode=layertools -jar app.jar list` | `java -Djarmode=tools -jar app.jar list-layers` |
| Extract by layers | `java -Djarmode=layertools -jar app.jar extract` | `java -Djarmode=tools -jar app.jar extract --layers --destination extracted` |
| Help | `java -Djarmode=layertools -jar app.jar help` | `java -Djarmode=tools -jar app.jar help extract` |
| Extract in **new layout** optimized for running | Not an old `layertools extract` feature | `java -Djarmode=tools -jar app.jar extract` |
| Exclude tool JAR from build | `layers.includeLayerTools=false` | `includeTools=false` |

**Do not replace `list` with `list-layers` while still passing `-Djarmode=layertools`, and do not pass `layertools`'s `list` to `tools`.** Commands are parsed by the specific packaged JAR mode implementation, not by the Java launcher itself.

## 3. Three Concepts Often Conflated

### 3.1. BOOT-INF/layers.idx — Image Layer Index

A layered JAR still keeps the standard executable Spring Boot layout:

```text
layer-lab-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/layerlab/LayerLabApplication.class
    ├── lib/
    │   ├── spring-boot-3.5.16.jar
    │   ├── spring-boot-jarmode-tools-3.5.16.jar
    │   └── ... other runtime dependencies
    ├── layers.idx
    └── classpath.idx             (if generated)
```

The diagram above is **illustrative**, not a guarantee that every build contains these exact entries or dependency versions. When `includeTools=false`, the corresponding tool JAR is absent. When layers are disabled, `layers.idx` may be absent.

`BOOT-INF/layers.idx` describes **which files/JARs belong to which Docker/OCI layer** and layer order for caching. Under standard defaults:

| Layer | Typical contents | Rationale |
|---|---|---|
| `dependencies` | Release dependencies without `SNAPSHOT` | Changes infrequently, leverages cache |
| `spring-boot-loader` | Loader classes | Usually changes when upgrading Boot |
| `snapshot-dependencies` | Dependencies with `SNAPSHOT` versions | Likely to change during development |
| `application` | Application classes/resources and local module dependencies | Changes frequently |

Typical layer order:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

**Shortened** example of index contents (not the full verbatim text of a real file):

```yaml
- "dependencies":
  - "BOOT-INF/lib/spring-core-6.x.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
  - "BOOT-INF/lib/example-client-1.0-SNAPSHOT.jar"
- "application":
  - "BOOT-INF/classes/"
```

Each entry corresponds to a path in the archive. JAR names/versions in the example are purely illustrative and must not be used as literal file paths in copy scripts.

**This index can still exist even if you disable bundling the tool JAR.** `includeTools=false` and `layers.enabled=false` are not synonymous: one controls **bundling the extraction tool**, while the other controls **generating layer classification metadata**.

### 3.2. BOOT-INF/classpath.idx — Classpath Order

`BOOT-INF/classpath.idx` lists nested JARs added to the **classpath in order**, serving the Boot Loader when running the executable archive. It does not determine Docker layers and does not share the syntax or purpose of `layers.idx`.

| File | Meaning | Is it the sole requirement to use jarmode? |
|---|---|---|
| `BOOT-INF/layers.idx` | Describes layers for tools to list/extract by layer | Layer metadata is needed for layer operations |
| `BOOT-INF/classpath.idx` | Order of nested JARs on the application classpath | **Not** layer metadata |
| `BOOT-INF/lib/spring-boot-jarmode-*.jar` | Code of the jarmode implementation bundled by Boot | Needs the matching implementation and mode |
| `META-INF/MANIFEST.MF` | Launcher/main bootstrap of the archive | Needs a valid executable archive |

Do not edit `classpath.idx` to try to change Docker layer order, and do not edit `layers.idx` to fix a `NoSuchMethodError` caused by dependency conflicts. The two metadata files solve different problems.

### 3.3. Docker Layers Differ from Classpath and Maven/Gradle Layers

A `Dockerfile` with multiple `COPY` instructions creates multiple image layers. Each `COPY` usually takes content from a directory generated by jarmode, such as `extracted/dependencies/`. The JVM does not read `dependencies` first and load all classes in `application` last; the JVM loads classes on demand via classloaders.

Layering optimizes **cache reuse** when the application changes; it does not guarantee a smaller image or faster runtime execution. Results depend on Docker cache policy, dependency count, artifact size, and how the image is built.

## 4. Where Is JAR Mode Activated?

Java launcher syntax:

```text
java [JVM options] -jar application.jar [arguments for jar mode]
     └─ -Djarmode=tools ─┘            └─ extract --layers ...
```

`-Djarmode=tools` is a **Java system property** and must appear **before `-jar`** so the Java launcher passes it to the JVM. `extract` and `--layers` are arguments to tools mode and appear **after the archive name**.

Correct:

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers
```

Wrong flag placement:

```bash
java -jar target/layer-lab-0.0.1-SNAPSHOT.jar -Djarmode=tools list-layers
```

The erroneous command passes those strings to the **application's `main`** as application arguments and fails to activate JAR mode. It may launch the app normally instead of printing layers.

**JAR mode is not a Maven profile or Spring profile.** Maven's `-Pproduction`, Spring Boot's `--spring.profiles.active=prod`, and `-Djarmode=tools` are three unrelated mechanisms. Tool mode is primarily for **inspecting/extracting the archive**, without executing the app's web/controller/`CommandLineRunner` logic.

A few reminders:

- The Java version must match the bytecode and Spring Boot version of the executable archive.
- `java -Djarmode=tools -jar ...` is a command to **run the packaged archive**, not `mvn spring-boot:run` or `gradle bootRun`.
- If the archive has a shell script prepended at the start of the file as a **fully executable** archive, Spring Boot documentation warns that `tools`/`layertools` does not support that extraction path; build a standard archive if you intend to use `extract`.
- Never assume a plain `jar` or `*-plain.jar` file contains the Loader/`layers.idx`/tool JAR; select the proper `bootJar` or Maven `repackage` output.

## 5. Details of layertools (Boot 2.3–3.2)

### 5.1. Mode Name and Commands

With an executable JAR **built with Spring Boot 3.2.12** containing `spring-boot-jarmode-layertools`:

```bash
# List available operations:
java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar

# List layers:
java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list

# Extract into layer directories in working directory:
java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar extract
```

Supported commands: `list`, `extract`, and `help`. `list-layers` is a **new command in `tools`**, not a standard command in layertools 3.2.

Typical `list` output shows layer names like:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

This is the **default layer list** in the example, without promising every project has the same layers: builds with a custom `layers.xml` can change names and ordering.

### 5.2. Output Paths of layertools extract

Run inside a separate working directory so files do not mix with source/build artifacts:

```bash
mkdir -p legacy-out
cd legacy-out
java -Djarmode=layertools -jar ../target/layer-lab-0.0.1-SNAPSHOT.jar extract
cd ..
```

After extraction succeeds, `legacy-out/` typically contains:

```text
legacy-out/
├── dependencies/
│   └── BOOT-INF/lib/...
├── spring-boot-loader/
│   └── org/springframework/boot/loader/...
├── snapshot-dependencies/
│   └── BOOT-INF/lib/...      (if SNAPSHOT dependencies exist)
└── application/
    ├── BOOT-INF/classes/...
    └── META-INF/MANIFEST.MF
```

This is a **layout suited for a Dockerfile to copy the layer directories sequentially** into the same `WORKDIR`. If a layer has no data, actual output depends on the tool, though layer names should still be checked against the artifact's `layers.idx` rather than guessed from Dockerfile copies.

A sample Spring Boot 3.2 Dockerfile typically launches with:

```dockerfile
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

This is the **Boot Loader 3.2 main class** when contents are unpacked onto the classpath, **not the default optimized launch mechanism of `tools` 3.3+**. When upgrading a Dockerfile, evaluate **both extraction and `ENTRYPOINT`**, not just renaming `layertools` to `tools`.

### 5.3. Disabling Layer Tools in Older Versions

Maven plugin snippet in Boot 3.2:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <includeLayerTools>false</includeLayerTools>
        </layers>
    </configuration>
</plugin>
```

This is a **snippet inserted under `<build><plugins>`**, not a standalone POM. When inclusion is disabled, the archive can **still contain `layers.idx`** if layering is enabled, yet lacks the JAR mode implementation so `java -Djarmode=layertools ...` will not run.

Equivalent Gradle 3.2 Groovy DSL:

```groovy
tasks.named("bootJar") {
    layered {
        includeLayerTools = false
    }
}
```

**Do not** blindly drop 3.3+'s `<includeTools>false</includeTools>` into a 3.2 POM, as that parameter was added in a different version. When inspecting an older project, read the **plugin docs for the 3.2 line itself**.

## 6. Details of tools (Boot 3.3, 3.4, 3.5, 4.0, and 4.1)

### 6.1. Listing Mode and Layers

With Spring Boot **3.5.16**, after packaging the executable JAR:

```bash
# View commands supported by tools:
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar

# View layer names:
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers

# View extract parameter details:
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar help extract
```

Basic `tools` commands: `extract`, `list-layers`, `help`. In a project with custom layer names, `list-layers` output reflects the `layers.idx` of the **inspected artifact**, not necessarily the four default layers.

### 6.2. Two Extraction Modes with Different Layouts

**Option A — default extract, aimed at fast startup/CDS-friendly execution:**

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar extract
```

If the JAR is named `layer-lab-0.0.1-SNAPSHOT.jar` and parameters are unchanged, output typically looks like:

```text
layer-lab-0.0.1-SNAPSHOT/
├── layer-lab-0.0.1-SNAPSHOT.jar
└── lib/
    └── ... dependency JARs
```

The directory is named after the executable JAR minus its extension. The JAR **inside the extracted directory is not the original uber JAR**; it holds application classes/manifest and references extracted libraries in `lib/`. Therefore you can run:

```bash
java -jar layer-lab-0.0.1-SNAPSHOT/layer-lab-0.0.1-SNAPSHOT.jar
```

This is the default `tools extract` layout introduced in Spring Boot 3.3 to reduce nested-JAR overhead and support features like CDS. **Do not confuse this path with `layertools`'s `extracted/application/BOOT-INF/classes`.**

**Option B — extract by layers for Docker COPY/caching:**

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar \
  extract --layers --destination extracted
```

When run from the root directory on Linux/macOS, the tool creates layer directories under `extracted/`:

```text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
```

Each layer contains subdirectories of the matching executable archive contents, which merge when copied sequentially into the runtime directory. **The counterpart to legacy `layertools` is `extract --layers`, not bare `extract`.**

Windows PowerShell can use a **single-line command** to avoid differences in Bash line-continuation syntax:

```powershell
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar extract --layers --destination extracted
```

When the destination already holds content, tools may refuse to write to protect data; check `help extract` for your exact version for flags such as `--force` if needed. To keep exercises reproducible, choose an empty directory or delete **specifically the directory you created** after confirming the path, rather than enabling `--force` carelessly in pipelines.

### 6.3. Why Is tools Not Just a New Name?

When using `tools extract` **without `--layers`**, the application is unpacked into a layout with a thin JAR and `lib/`, runnable via `java -jar extracted-app.jar`; this layout helps with Class Data Sharing and unpacked startup.

When using `tools extract --layers`, you get **one directory per image layer** so a Dockerfile can `COPY` each part separately. That structure targets image caching, not a directly runnable application JAR at the root before copying/merging contents.

| Property | `tools extract` | `tools extract --layers` |
|---|---|---|
| Primary output | A thin application JAR + `lib/` directory | Directories named after layers |
| Purpose | Run exploded jar efficiently, supporting CDS/AOT cache depending on JDK/version | Split into cache-friendly Docker/OCI layers |
| Run command after extract | `java -jar <dir>/<app>.jar` | Must merge layers into the proper runtime location before running |
| Should copy `dependencies`, `application` dirs? | No, layout is not structured that way | Yes, if the artifact uses those layer names |
| Can simply replace `layertools` with `tools` and keep old Dockerfile? | No | Only after updating syntax, paths, `ENTRYPOINT`, and verifying the artifact |

### 6.4. Disabling the Tool JAR in Newer Versions

The Maven plugin **starting in Spring Boot 3.3** places `includeTools` at the **plugin level**, not under `layers`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>false</includeTools>
    </configuration>
</plugin>
```

Gradle Groovy DSL:

```groovy
tasks.named("bootJar") {
    includeTools = false
}
```

If you disable `includeTools`, the app can still run normally via `java -jar`, but `-Djarmode=tools` is no longer available inside the archive. That is a sensible option when images are built by another mechanism and you deliberately want fewer packaged components, **not** a way to disable the Spring Boot Loader.

Conversely, to disable the **layer index file** without assuming anything about the tool JAR:

```xml
<configuration>
    <layers>
        <enabled>false</enabled>
    </layers>
</configuration>
```

For Boot 3.3+, release notes clarify that **disabling layers no longer automatically excludes the tool JAR**; to omit the implementation, use `includeTools=false`. If the tool remains bundled while `layers.idx` is absent, do not expect `list-layers`/`extract --layers` to work normally. Inspect the file and test the exact command against the actual artifact.

### 6.5. Why Does Boot 4.1 Not Use layertools?

Spring Boot 4.1 Release Notes confirm **removal of the deprecated `layertools` mode**. For builds starting with 4.1, layered workflows must move to:

```bash
java -Djarmode=tools -jar my-app.jar list-layers
java -Djarmode=tools -jar my-app.jar extract --layers --destination extracted
```

Do not try to work around this by forcing a 3.2 `spring-boot-jarmode-layertools` dependency into a 4.1 JAR; loader/mode versions are not standalone interchangeable plugins. Upgrade packaging tools and scripts **to match the application's Spring Boot line**.

## 7. Maven + Spring Boot 3.5.16 Example Buildable with Java 17

Let's create **a simple console app**, needing no database or web server, to focus on build tool behavior. The example pins Spring Boot **3.5.16** so contents can be verified directly. You need JDK 17+, a compatible Maven 3.6.3+ or project Maven Wrapper, and repository download access if dependencies are not cached.

### 7.1. Directory Tree

```text
layer-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/layerlab/LayerLabApplication.java
    └── test/java/com/example/layerlab/LayerLabApplicationTests.java
```

If a project has a Maven Wrapper, it also has `mvnw`, `mvnw.cmd`, and `.mvn/wrapper/...`. Never assume a wrapper exists when creating only a POM; you can use an installed Maven and invoke `mvn` instead of `./mvnw`.

### 7.2. Complete pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>layer-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
                <configuration>
                    <!-- Keep tools and layer index for practice. -->
                    <includeTools>true</includeTools>
                    <layers>
                        <enabled>true</enabled>
                    </layers>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Here:

- `spring-boot-starter-parent` manages dependency/plugin versions and common `repackage` configuration.
- `spring-boot-maven-plugin` is declared once in the app so Maven `package` builds an executable JAR.
- `<includeTools>true</includeTools>` sets the policy to **bundle tools**; in Boot 3.5 it defaults to true, yet is written explicitly so learners see the setting.
- `<layers><enabled>true</enabled></layers>` preserves `BOOT-INF/layers.idx` for `list-layers` and `extract --layers`.
- `spring-boot-starter-test` serves tests only and does not enter the JAR as a runtime dependency.

### 7.3. Complete Java Main Class

`src/main/java/com/example/layerlab/LayerLabApplication.java`:

```java
package com.example.layerlab;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayerLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerLabApplication.class, args);
    }

    @Bean
    CommandLineRunner demoRunner() {
        return args -> System.out.println("Layer lab: OK");
    }
}
```

Without `spring-boot-starter-web`, the program opens no HTTP port; after startup, with no remaining non-daemon tasks, it exits. The exact **line printed by `CommandLineRunner`** is:

```text
Layer lab: OK
```

Spring Boot may print its banner and startup logs alongside; do not assert stdout consists of only one line.

### 7.4. Simple Test in Java 17/JUnit Jupiter

`src/test/java/com/example/layerlab/LayerLabApplicationTests.java`:

```java
package com.example.layerlab;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LayerLabApplicationTests {
    @Test
    void javaVersionIsAtLeastSeventeen() {
        assertEquals(true, Runtime.version().feature() >= 17);
    }
}
```

This test only confirms a Java 17+ environment without booting a Spring context. `mvn clean package` runs tests prior to packaging; if Maven's JDK is incompatible, compilation or testing fails. In real projects, test application behavior rather than only checking the JVM version—this lesson uses a lightweight test to focus on packaging.

### 7.5. Building and Running

At the project root containing `pom.xml`:

```bash
# If project already has Maven Wrapper:
./mvnw clean package

# If no Wrapper but Maven is installed:
mvn clean package

# Run Boot 3.5 executable JAR:
java -jar target/layer-lab-0.0.1-SNAPSHOT.jar
```

On Windows PowerShell with a wrapper: `.\mvnw.cmd clean package`. Run **only one build command**; there is no need to run both Maven Wrapper and installed Maven.

### 7.6. Checking the Tools Dependency and layers.idx

```bash
# JDK jar tool: list entries:
jar tf target/layer-lab-0.0.1-SNAPSHOT.jar

# Linux/macOS with grep:
jar tf target/layer-lab-0.0.1-SNAPSHOT.jar |
  grep -E '(BOOT-INF/layers.idx|BOOT-INF/lib/spring-boot-jarmode-tools-)'
```

On Windows PowerShell:

```powershell
jar tf target/layer-lab-0.0.1-SNAPSHOT.jar |
  Select-String 'BOOT-INF/(layers\.idx|lib/spring-boot-jarmode-tools-)'
```

In a properly configured Boot 3.5.16 build, expect:

```text
BOOT-INF/layers.idx
BOOT-INF/lib/spring-boot-jarmode-tools-3.5.16.jar
```

Inspecting the **actual JAR file** matters more than guessing. Having `layers.idx` **does not prove** the tool JAR exists; verify both entries. When the plugin configures `includeTools=false`, missing the tool JAR is expected behavior, not a Maven resolution bug.

### 7.7. Using tools to List and Extract Layers

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers

java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar \
  extract --layers --destination extracted
```

Expected layer names (without custom layer configuration):

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

These are the names/order to recognize, not a promise that output has strictly four lines with no logs or formatting differences. Inspect the real contents of `extracted/`, especially the `application` and `dependencies` layers.

**Special note on argument position:** `--destination extracted` is an argument to `tools extract`; it goes **after `extract`**, not as a Maven option and not as an output setting of `spring-boot-maven-plugin`. Using a destination that collides with existing data may cause the tool to error; pick a clean directory.

### 7.8. Trying Default Extract into Another Layout

In a clean test directory:

```bash
mkdir -p default-extract-demo
cd default-extract-demo
java -Djarmode=tools -jar ../target/layer-lab-0.0.1-SNAPSHOT.jar extract
cd ..
```

The structure normally lands at:

```text
default-extract-demo/
└── layer-lab-0.0.1-SNAPSHOT/
    ├── layer-lab-0.0.1-SNAPSHOT.jar
    └── lib/...
```

Run the application from the thin JAR:

```bash
java -jar default-extract-demo/layer-lab-0.0.1-SNAPSHOT/layer-lab-0.0.1-SNAPSHOT.jar
```

The line printed by `CommandLineRunner` is still `Layer lab: OK`. If you see `dependencies/`, `spring-boot-loader/`, etc. inside `default-extract-demo`, check whether the command actually passed `--layers` or an old directory was not cleaned.

## 8. Inspecting the Archive with Pure Java 17, Without Spring Dependencies

To verify whether a JAR contains the **index** and **tool JAR**, you can use standard Java to scan ZIP entries. Standalone code placed at root as `InspectLayers.java`:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.zip.ZipFile;

public final class InspectLayers {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Usage: java InspectLayers <jar-file>");
            return;
        }

        try (ZipFile file = new ZipFile(Path.of(args[0]).toFile())) {
            boolean hasLayers = file.getEntry("BOOT-INF/layers.idx") != null;
            boolean hasTools = file.stream().anyMatch(entry ->
                    entry.getName().startsWith(
                            "BOOT-INF/lib/spring-boot-jarmode-tools-"));
            boolean hasLayertools = file.stream().anyMatch(entry ->
                    entry.getName().startsWith(
                            "BOOT-INF/lib/spring-boot-jarmode-layertools-"));

            System.out.println("layers.idx: " + hasLayers);
            System.out.println("tools JAR: " + hasTools);
            System.out.println("layertools JAR: " + hasLayertools);
        }
    }
}
```

Compile/run at root with Java 17+:

```bash
javac InspectLayers.java
java InspectLayers target/layer-lab-0.0.1-SNAPSHOT.jar
```

**Exact stdout for the Boot 3.5.16 artifact built from the example POM when both layer index and tools JAR are present:**

```text
layers.idx: true
tools JAR: true
layertools JAR: false
```

This result checks **ZIP entries** by name; it is not a proof of loader runtime compatibility. A custom build could rename or supply tool dependencies differently, in which case the program simply reflects its name-matching rules. Still, it is very useful for detecting **which tool** a JAR was actually packaged with before running `-Djarmode`.

To inspect a Spring Boot 3.2.12 artifact with layertools:

```bash
java InspectLayers path/to/legacy-app.jar
```

In a legacy case with the index file + layertools dependency and no tools dependency, expected output:

```text
layers.idx: true
tools JAR: false
layertools JAR: true
```

Do not assume this result for every 3.2 JAR: the plugin could be configured with `includeLayerTools=false` or layers disabled.

## 9. Legacy Maven Example (3.2.12): What Must Change?

To simulate the older version safely, **create a separate copy of the sample project** and change in the POM:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.12</version>
    <relativePath/>
</parent>
```

In Spring Boot 3.2, **do not keep the `includeTools` parameter from the 3.5 POM**, because that parameter was added in 3.3. Replace `<configuration>` inside the plugin with:

```xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <includeLayerTools>true</includeLayerTools>
    </layers>
</configuration>
```

These are **replacement snippets for the main POM**, not a standalone legacy POM to copy verbatim without `<project>`. The Java 17 classes (`LayerLabApplication.java` and unit test) still work with Boot 3.2.12 when dependency versions are compatible, since the code uses only basic APIs.

Build the copied project:

```bash
mvn clean package

java -Djarmode=layertools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list

mkdir -p legacy-extracted
cd legacy-extracted
java -Djarmode=layertools -jar ../target/layer-lab-0.0.1-SNAPSHOT.jar extract
cd ..
```

If using a Maven Wrapper in the copy, replace `mvn` with `./mvnw`. **Do not** run `java -Djarmode=tools ...` on a Boot 3.2 JAR expecting it to work; that built-in mode had not yet been introduced for that branch.

In real CI, avoid running `mvn clean package` multiple times on the same checkout and comparing tool behavior while forgetting the version changed: **separate the artifacts** with different filenames/paths or use two separate checkouts/build outputs to be certain which version you are testing.

## 10. Gradle: DSL Changes Between Old and New Versions

The essence of JAR mode depends on the **final artifact**, not whether you use Maven or Gradle. However, the DSL controlling the tool JAR changes alongside the plugin version.

### 10.1. Gradle Boot 3.2 Groovy DSL

In `build.gradle` of a project with `org.springframework.boot` + `java`:

```groovy
tasks.named("bootJar") {
    layered {
        enabled = true
        includeLayerTools = false  // Exclude layertools JAR in older versions
    }
}
```

When needing `layertools` for extraction, make sure **not to set `includeLayerTools=false`**. By default when creating a layered archive, the Spring Boot plugin includes the layertools JAR; you may also set it to `true` explicitly if desired.

### 10.2. Gradle Boot 3.5 Groovy DSL

**Complete** build script example to use with the same `LayerLabApplication.java` from section 7:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    includeTools = true
    layered {
        enabled = true
    }
}
```

Minimal `settings.gradle`:

```groovy
rootProject.name = 'layer-lab'
```

With an **existing Gradle Wrapper** and a Gradle version compatible with Spring Boot 3.5:

```bash
./gradlew clean bootJar

jar tf build/libs/layer-lab-0.0.1-SNAPSHOT.jar

java -Djarmode=tools -jar build/libs/layer-lab-0.0.1-SNAPSHOT.jar list-layers

java -Djarmode=tools -jar build/libs/layer-lab-0.0.1-SNAPSHOT.jar \
  extract --layers --destination extracted
```

Windows PowerShell uses `.\gradlew.bat` and writes tools commands on one line. Maven and Gradle share the same layering concepts, yet **never paste POM `<includeTools>` into Groovy**, nor use `tasks.named('bootJar')` in Maven.

### 10.3. Kotlin DSL and Scope of includeTools

If a Gradle project uses `build.gradle.kts`, the corresponding syntax is (configuration snippet, not a standalone file):

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(true)
    layered {
        enabled.set(true)
    }
}
```

A crucial difference is that `includeTools` belongs to the **`BootJar`/`BootWar` task**, not as a nested property under `layered` in 3.3+. For an executable WAR, adjust the `bootWar` task and web application layout paths per the plugin rather than assuming every WAR uses `BOOT-INF/lib` like a JAR.

## 11. Legacy vs. Modern Dockerfiles: Which Command, Which ENTRYPOINT?

### 11.1. Dockerfile for Boot 3.2.x layertools

The example below uses `target/layer-lab-0.0.1-SNAPSHOT.jar` built with **Boot 3.2**. This is a multi-stage Dockerfile using Java 17:

```dockerfile
FROM eclipse-temurin:17-jre AS builder
WORKDIR /builder

COPY target/layer-lab-0.0.1-SNAPSHOT.jar application.jar

RUN mkdir -p extracted
WORKDIR /builder/extracted
RUN java -Djarmode=layertools -jar ../application.jar extract

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

Here `layertools extract` places files into four layer directories. The `COPY` steps sequentially **reassemble the old Boot loader layout**. The entrypoint class `org.springframework.boot.loader.launch.JarLauncher` matches Spring Boot 3.2's loader layout. On older Boot 2.x releases, the launcher class package can differ; verify the manifest/version before copying this snippet.

**Do not take the Dockerfile above to run a 4.1 artifact directly.** 4.1 removed `layertools`; even if extracting via another tool, entrypoint and loader compatibility must be evaluated for the new JAR mode.

### 11.2. Dockerfile for Boot 3.5+ Layered tools

With the **same artifact name** built using Spring Boot **3.5.16**:

```dockerfile
FROM eclipse-temurin:17-jre AS builder
WORKDIR /builder

COPY target/layer-lab-0.0.1-SNAPSHOT.jar application.jar

RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./

# Note: after tools extract --layers and COPY, this is the JAR file
# generated in the new layout; NOT the fat application.jar in the builder.
ENTRYPOINT ["java", "-jar", "application.jar"]
```

The `extract --layers --destination extracted` command and `ENTRYPOINT java -jar application.jar` follow **examples from Spring Boot 3.3+/3.5 docs**. This launch style supports an exploded layout with a thin application JAR and libraries placed in the appropriate directories after copying. Use this Dockerfile with the same artifact name and JRE 17 base for **Boot 3.5**, rather than applying it blindly if a Boot 4.x project requires a different JDK; select a runtime image matching your Boot release.

**Why does ENTRYPOINT differ?** `tools` 3.3+ constructs a layout designed to run via `java -jar` with a manifest classpath pointing to extracted libraries. You should not keep `ENTRYPOINT ["java","org.springframework.boot.loader.launch.JarLauncher"]` as a mandatory recipe once migrated to `tools`.

### 11.3. Why Inspect Layer Order When Copying?

Sequential `COPY` instructions build image layers in order. Release dependencies go first and application goes last so that when only application source changes, Docker can reuse cached library layers.

If the build configures **custom layers**, paths like `extracted/dependencies/` or layer ordering may differ. In that case:

1. Run `list-layers` on the artifact.
2. Extract `layers.idx` or inspect the output directories.
3. Adjust `COPY` instructions for every layer and order.
4. Verify the app starts from the real image with no missing dependencies.
5. Measure image cache hits/size in CI; do not infer performance from layer names.

A Dockerfile should not hardcode a single module version different from what Maven/Gradle builds. Pin the specific artifact path or copy the build output to a consistent name like `application.jar` in the builder.

## 12. Common Errors When Upgrading from layertools to tools

| Symptom | Possible cause | Resolution |
|---|---|---|
| `Unknown jar mode 'layertools'` on Boot 4.1 | Legacy mode was removed | Switch to `-Djarmode=tools` and the new subcommands |
| `Unknown jar mode 'tools'` on Boot 3.2 | Older artifact lacks `tools` mode | Use `layertools` or upgrade Boot/plugin and rebuild |
| `tools list` unrecognized | `tools` uses `list-layers`, not `list` | Update the subcommand |
| `layertools list-layers` fails | Legacy `layertools` uses `list` | Switch back to `list` for legacy artifacts |
| Dockerfile uses `tools extract` yet copies `extracted/dependencies` | Default extract builds a thin JAR + `lib`, not layer directories | Use `extract --layers --destination extracted` |
| `tools extract --layers` cannot find layer index | `BOOT-INF/layers.idx` absent/disabled | Inspect archive and enable `layers.enabled` appropriately |
| JAR has `layers.idx` yet jarmode fails | `includeTools=false` or legacy `includeLayerTools=false` was set | Check nested tool JAR and plugin config, then rebuild |
| Disabled `layers.enabled` yet tools JAR remains in 3.3+ | Layer generation and tool inclusion are decoupled | Set `includeTools=false` if you genuinely want to omit the tool |
| Maven 3.2 says `includeTools` is invalid/ignored | 3.3+ syntax used by mistake | 3.2 uses `layers.includeLayerTools` |
| Gradle says `includeLayerTools` no longer applies | Old DSL used after upgrade | Switch to `includeTools` at the task level |
| Tool cannot process fully executable archive | JAR has a prepended launch script | Disable launch script when needing jarmode extract |
| `java -jar ...` launches app instead of printing layers | `-Djarmode` misplaced (after `-jar app.jar`) | Put `-Djarmode=tools` before `-jar` |
| Build succeeds yet tool mode missing | Plain JAR/mistaken `-plain.jar`, or tool excluded | Inspect the right executable archive and `BOOT-INF/lib` |
| Copied JAR from root yet Dockerfile points to wrong `build/libs`/`target` | Mixed up build tool/output directory | Maven usually uses `target`; Gradle usually uses `build/libs` |
| Docker ENTRYPOINT cannot find `JarLauncher` | Kept legacy entrypoint on the new `tools` layout | Use `java -jar application.jar` per 3.3+ Dockerfiles |
| Local tests pass yet image fails | Missing copied layer or incompatible base JRE/JDK | Compare `list-layers`, check layer dirs, JDK, startup logs |
| Re-running extract refuses to write | Non-empty destination | Use a new directory; safely clear only your own output before re-running |
| Missing `snapshot-dependencies` layer | Project has no SNAPSHOT JARs or empty output | Rely on the real index and directories; do not add dummy files |
| Added more image layers yet image is not faster | Build cache/config issues or dependencies change often | Measure cache reuse, CPU/IO, image size; optimize from data |

### Errors to Distinguish from JAR Mode Issues

- `UnsupportedClassVersionError`: JRE is older than app/Boot bytecode requires; not solved by switching `layertools` ↔ `tools`.
- `ClassNotFoundException`/`NoClassDefFoundError` when running the image: possibly missing a runtime JAR or copying the wrong layer; check classpath/packaging.
- Maven lacking `build-image` goal or Gradle lacking `bootJar` task: build plugin/task setup error, not an archive mode issue.
- Build cache misses: also depend on Dockerfile order, layer contents, base image, and cache policy; `layers.idx` does not automatically speed up Docker images.
- CI uses a stale cached JAR despite POM version bumps: check hashes/timestamps/artifact paths rather than trying random flags.

## 13. Migration Testing Checklist for a Real Project

### 13.1. Pre-Upgrade Inventory

In your active CI/repository, search for:

```text
-Djarmode=layertools
-Djarmode=tools
layertools extract
layertools list
tools extract
tools list-layers
includeLayerTools
includeTools
BOOT-INF/layers.idx
spring-boot-jarmode-layertools
spring-boot-jarmode-tools
```

Do not update only the Dockerfile: CI scripts, shell scripts, Helm/init containers, build automation, and deployment docs may still invoke the old mode. Within your current repository scope, run targeted searches across the codebase; this lesson does not require modifying all external systems immediately.

### 13.2. Verify Version and Actual Artifact

1. Read the **effective POM**/Gradle plugins to verify the Spring Boot plugin version.
2. Confirm the built executable JAR matches that version, avoiding plain JARs.
3. Run `jar tf` to check `BOOT-INF/layers.idx`, the tool JAR, and the launcher.
4. Run `-Djarmode=tools` or `layertools` matching the **version**, not just the filename.
5. Run `list`/`list-layers`; confirm every layer used in the Dockerfile exists.
6. Run `extract` into a clean directory; inspect the real layout before writing `COPY` lines.
7. Verify startup from the extracted layout/Docker image; test basic functionality.
8. For 4.1+, remove all `layertools` invocations from scripts consuming new artifacts.
9. Compare image cache, size, startup, and dependency availability in target CI/runtime.
10. Record which docs/release notes guided the decision to avoid copying snippets across incompatible Boot branches.

### 13.3. How to Prove the Dockerfile Does Not Accidentally Run the App in the Builder

In the builder stage, the goal of JAR mode is **extraction**, not booting the Spring `ApplicationContext`. In our example, the app prints `Layer lab: OK` during normal runs. Meanwhile, the command:

```bash
java -Djarmode=tools -jar target/layer-lab-0.0.1-SNAPSHOT.jar list-layers
```

prints layer info, **does not trigger `CommandLineRunner`**, and does not print `Layer lab: OK` as a Spring startup side effect. If you see app startup logs in the builder, check `-Djarmode` placement, tool inclusion, and the executed command.

### 13.4. Version Governance Policy

- Pin compatible Spring Boot **plugin and runtime dependency** versions; never pull a mismatched tool JAR version manually into an executable archive.
- Maven: if using `spring-boot-starter-parent`, let the parent manage the plugin version; if importing a BOM separately, still configure the Boot plugin/`repackage` on the app.
- Gradle: import the appropriate Spring Boot BOM or dependency-management plugin; apply the Boot plugin only to modules producing executable archives.
- When Spring Boot 3.2 and 3.5 coexist in a monorepo, **Dockerfile/`jarmode` invocations must be tied to each specific artifact**, with no single unbranched command shared across both.
- When upgrading to Boot 4.1, also check **JDK requirements and Spring Framework changes**, beyond renaming the jar mode.

## 14. Quick Summary and Exercises

### Cheat Sheet

| Question | Answer |
|---|---|
| What is `layers.idx`? | Index describing how to split the archive into Docker/OCI layers |
| What is `classpath.idx`? | Index ordering nested JARs on the classpath |
| Which mode does Spring Boot 3.2 need? | `-Djarmode=layertools` |
| Which mode should Spring Boot 3.5 use? | `-Djarmode=tools` |
| Does Spring Boot 4.1 still have `layertools`? | **No**, it was removed |
| What replaces `layertools list`? | `tools list-layers` |
| What replaces `layertools extract` for layer dirs? | `tools extract --layers --destination <dir>` |
| What does `tools extract` without `--layers` create? | Layout with a thin application JAR and a `lib/` folder |
| How to disable tool JAR in Maven 3.2? | `layers.includeLayerTools=false` |
| How to disable tool JAR in Maven 3.3+? | `includeTools=false` |
| Does disabling layer index exclude the tool JAR in 3.3+? | **Not automatically** |
| How should the new Dockerfile start? | For the 3.3+ tools layout built in the example: `java -jar application.jar` |
| Can a fully executable archive with a launch script use tools extract? | Not per Spring Boot docs; build an appropriate standard archive |

### Exercise 1: Classify Three Commands

```bash
java -Djarmode=layertools -jar app.jar list
java -Djarmode=tools -jar app.jar list-layers
java -Djarmode=tools -jar app.jar extract
```

**Answer:** line 1 uses the legacy interface; line 2 lists layers via `tools`; line 3 extracts the new default layout, **not** equivalent to extracting the four legacy layer directories.

### Exercise 2: Check a Dockerfile After Upgrade

An old Dockerfile uses:

```dockerfile
RUN java -Djarmode=layertools -jar application.jar extract
COPY --from=builder /builder/dependencies/ ./
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

To migrate to Boot 3.5/4.1, inspect and fix **all three**:

1. Update the layer extraction command to `java -Djarmode=tools -jar application.jar extract --layers --destination extracted`.
2. Update the `COPY` source to `/builder/extracted/dependencies/` (and the remaining layers), depending on builder `WORKDIR`.
3. Update the entrypoint for the new tools layout to `java -jar application.jar` after merging layers; do not keep the legacy loader main class recipe without verifying the archive.

### Exercise 3: Explain Why a Configuration Change Had No Effect

You set:

```xml
<configuration>
    <layers>
        <enabled>false</enabled>
    </layers>
</configuration>
```

yet still see `spring-boot-jarmode-tools` inside `BOOT-INF/lib` on Spring Boot 3.5. This is **not** Maven ignoring config: starting in 3.3, the flag controlling tool inclusion was separated into `<includeTools>false</includeTools>`. Also verify `layers.idx` is genuinely absent from the archive. If both the index and the tool must be omitted, configure **both** intentionally.

**Final conclusion:** `layertools` is the legacy layer extraction mechanism; `tools` is the modern mechanism (from Spring Boot 3.3 onward) supporting both **per-layer extraction** and **default exploded layout extraction** for efficient app startup. Spring Boot 4.1 marks the point where relying on `layertools` is no longer possible. The safe workflow is **verify version/artifact → inspect tool JAR and `layers.idx` → run matching commands → check layout → verify Docker `COPY` + `ENTRYPOINT` → re-run the artifact/image**.

## Official Documentation for Version-by-Version Comparison

- [Spring Boot 2.3 Release Notes — Building layered jars and layertools](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.3-Release-Notes)
- [Spring Boot 3.2.12 Reference — Container Images / layertools](https://docs.spring.io/spring-boot/docs/3.2.12/reference/html/container-images.html)
- [Spring Boot 3.2.12 Maven Plugin — Packaging / includeLayerTools](https://docs.spring.io/spring-boot/docs/3.2.12/maven-plugin/reference/htmlsingle/)
- [Spring Boot 3.3 Release Notes — tools mode, deprecations, and includeTools](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Spring Boot 3.3 Reference — Efficient Deployments](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.5 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Dockerfiles: tools extract --layers](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 4.1 Release Notes — Removal of layertools mode](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes)
- [Spring Boot 4.1 — Dockerfiles: tools jarmode](https://docs.spring.io/spring-boot/4.1/reference/packaging/container-images/dockerfiles.html)