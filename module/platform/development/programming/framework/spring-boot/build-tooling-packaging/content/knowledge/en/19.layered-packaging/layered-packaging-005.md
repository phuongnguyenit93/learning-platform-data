# Customizing the BootJar Layered DSL in Gradle for Spring Boot

## 1. Problem: One Executable JAR, Multiple Container Cache Layers

`BootJar` is the task created by the **Spring Boot Gradle Plugin** to package an application as an executable JAR. Unlike the Java plugin's plain `jar` task, `bootJar` places application classes/resources in `BOOT-INF/classes`, runtime dependencies in `BOOT-INF/lib`, and adds the Spring Boot launcher.

When building Docker/OCI images, we want to avoid re-uploading or rebuilding all dependency binaries just because one controller changed. Spring Boot supports **layered JARs**: the executable archive preserves the JAR layout runnable via `java -jar`, while adding **`BOOT-INF/layers.idx`**, an index describing which files/paths belong to which logical layer. Image-building tools can read or extract these layers into separate image steps to improve cache reuse.

Example:

```text
Gradle / Spring Boot source
          |
          v
      ./gradlew bootJar
          |
          v
build/libs/layer-demo-0.1.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...    <- spring-boot-loader
├── BOOT-INF/classes/
│   ├── com/example/layer/...              <- application
│   └── static/info.txt                    <- static-assets (custom)
├── BOOT-INF/lib/
│   ├── spring-boot-3.5.0.jar               <- spring-boot-dependencies
│   ├── spring-web-...jar                   <- dependencies
│   └── ...                                 <- dependency groups
└── BOOT-INF/layers.idx                     <- layer group MAP
          |
          v
tools extract --layers
          |
          v
COPY stable layers first -> COPY application last -> OCI image
```

**Key distinction:** layering **does not create a separate JAR for each layer**; it adds metadata inside **a single archive**. Forming image layers happens when building the image with a Dockerfile or equivalent tooling. `bootJar` itself does not publish an OCI image. Spring Boot's `bootBuildImage` uses Cloud Native Buildpacks, which is a separate flow that typically handles layer optimization without writing a custom Dockerfile.

This lesson uses **Spring Boot Gradle Plugin 3.5.0, Java 17, and Gradle Kotlin DSL**, alongside Groovy DSL. Fixed versions keep syntax consistent and do not imply these are the latest releases. Use a Gradle Wrapper version supported by the plugin; some APIs/options differ across Spring Boot 2.x, 3.x, and 4.x.

## 2. Spring Boot's Default Layered JAR

With modern Spring Boot Gradle plugin versions, `bootJar` **enables layering by default**. The `BOOT-INF/layers.idx` index typically has four layers:

| Default layer | Typical contents | Change frequency |
| --- | --- | --- |
| `dependencies` | **Non-project** dependencies whose version does not contain `SNAPSHOT` | Changes less often than application code |
| `spring-boot-loader` | Spring Boot launcher classes under `org/springframework/boot/loader/**` | Usually changes only when upgrading Boot |
| `snapshot-dependencies` | External dependencies whose version contains `SNAPSHOT` | Can change frequently |
| `application` | Application classes/resources and **Gradle project dependencies** | Usually changes the most |

**The default order of layers** is:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Less frequently changing layers are placed **first**, while application classes/resources sit at the end to limit invalidation of subsequent Docker layers when Java source is edited. This is a caching strategy, **not** Java class loading order or Spring bean initialization order.

A layer in `layers.idx` can be represented by paths:

```yaml
- "dependencies":
  - "BOOT-INF/lib/spring-web-6.x.x.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
```

This is a **simplified example** illustrating the format and not the exact content of a real artifact. JAR names/versions, entry counts, and directory grouping in the file are determined by the plugin and dependency graph. Empty layers are possible; do not assume all four layers always contain files. Verify the real file with `unzip -p ... BOOT-INF/layers.idx` after building.

### How Layering Differs from classpath.idx

| File | Purpose | Does it change class loading order? |
| --- | --- | --- |
| `BOOT-INF/layers.idx` | Assigns archive entries to layer groups for image creation/extraction | Not used as a classpath ordering mechanism |
| `BOOT-INF/classpath.idx` | Records dependency JAR order on the classpath when running via Boot launcher | Can affect classpath order in supported modes |
| `META-INF/MANIFEST.MF` | Declares `Main-Class`/`Start-Class` for the JVM to run the archive | Determines launcher/main entry |

Never edit `layers.idx` manually to “override” another dependency class. Dependency version selection belongs to Gradle resolution and classpath configuration; layer metadata only handles archive grouping.

## 3. Overview of BootJar Layered DSL Syntax

In `build.gradle.kts`, once the Spring Boot Gradle plugin is applied:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            // Assign application classes, resources, and Boot Loader classes to layers.
        }
        dependencies {
            // Assign runtime dependency JARs to layers.
        }
        layerOrder.set(listOf(
            "dependencies",
            "spring-boot-loader",
            "snapshot-dependencies",
            "application"
        ))
    }
}
```

**Three mandatory parts to understand when customizing:**
1. `application { ... }` classifies **application and launcher files** using Ant-style path patterns.
2. `dependencies { ... }` classifies **dependency artifacts** using `group:artifact[:version]` patterns or project dependency selectors.
3. `layerOrder` determines **the order layers are placed into the index/image**, from least volatile to most volatile.

For **custom layering**, `layerOrder` must be declared and must contain **every layer name** used by `application`/`dependencies`. Missing names or incompatible leftovers can make Gradle fail during configuration/packaging instead of guessing the order.

### 3.1. `intoLayer` Is a Top-to-Bottom Classifier

Example:

```kotlin
application {
    intoLayer("spring-boot-loader") {
        include("org/springframework/boot/loader/**")
    }
    intoLayer("application")
}
```

The first block **claims** all archive entries matching the Boot Loader pattern; the second block claims all remaining unclaimed contents. Evaluation runs **top-to-bottom**. Placing the `intoLayer("application")` catch-all first leaves later specialized blocks with no files to claim.

The same applies inside `dependencies`:

```kotlin
dependencies {
    intoLayer("snapshot-dependencies") {
        include("*:*:*SNAPSHOT")
    }
    intoLayer("dependencies")
}
```

If the package includes `com.example:billing-client:1.2.0-SNAPSHOT`, the first block claims it; remaining release JARs are claimed by the catch-all block. `*:*:*SNAPSHOT` is a **Gradle module coordinates** matcher, not a `BOOT-INF/lib/...` path.

### 3.2. How `include` and `exclude` Work

An `intoLayer` block may contain:
- `include("pattern")`: claims only entries matching the pattern, if includes are defined;
- `exclude("pattern")`: excludes entries matching the pattern from that layer;
- no `include`: considers **all remaining unclaimed contents**;
- no `exclude`: applies no specific exclusion condition.

**Exclude does not remove a file from the JAR.** A file excluded from the **current layer** can still be claimed by a subsequent layer. Without a final fallback, entries may fail to be assigned properly or packaging may fail; always inspect `layers.idx` and run the application.

Example:

```kotlin
dependencies {
    intoLayer("vendor-libs") {
        include("com.vendor:*:*")
        exclude("com.vendor:experimental-agent:*")
    }
    intoLayer("dependencies")
}
```

`com.vendor` and `experimental-agent` are **illustrative coordinates**, not dependencies declared in the demo project. A dependency excluded from `vendor-libs` can still fall into the `dependencies` catch-all. If the goal is **not packaging** a dependency at all, modify Gradle dependencies/configurations or actual build exclusions, not layer excludes.

## 4. Defining Custom Layers: A Cache-Friendly Design Example

Let's split into six layers:

| Custom layer | Contents | Rationale |
| --- | --- | --- |
| `spring-boot-dependencies` | Module dependencies in group `org.springframework.boot` (excluding snapshots claimed earlier) | Isolates core Boot, changing mainly on framework upgrades |
| `dependencies` | Remaining external release JARs | Cached across business code changes |
| `spring-boot-loader` | Launcher classes | Relatively stable |
| `snapshot-dependencies` | External dependencies with `SNAPSHOT` versions | More volatile group |
| `static-assets` | Contents under `BOOT-INF/classes/static/**` | Separates web assets from Java classes |
| `application` | Remaining application classes/resources, manifest, and Gradle project dependencies | Changes most frequently |

**Choosing order:** stable dependencies first, Java classes/resources later. Placing `static-assets` before `application` helps when only Java source changes; if CSS/JS change more often than Java classes, measure in practice and consider swapping the last two layers. There is no single optimal `layerOrder` for every project.

### 4.1. Complete Kotlin DSL

The following goes inside a `build.gradle.kts` **that already applies the Spring Boot plugin**, not as a standalone file:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }

            intoLayer("static-assets") {
                include("BOOT-INF/classes/static/**")
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

            intoLayer("spring-boot-dependencies") {
                include("org.springframework.boot:*:*")
            }

            intoLayer("dependencies")
        }

        layerOrder.set(
            listOf(
                "spring-boot-dependencies",
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "static-assets",
                "application"
            )
        )
    }
}
```

**Explanation of matcher order:**
- Project dependencies are claimed into `application` first because in a monorepo they normally change alongside app code.
- External SNAPSHOTs are claimed before release dependency groups, preventing an `org.springframework.boot` SNAPSHOT (if present) from accidentally entering a stable group.
- `org.springframework.boot:*:*` is a module coordinate matcher including the version wildcard, not a file path.
- `dependencies` without an include claims all remaining dependency JARs.
- `spring-boot-loader` grabs classes in `org/springframework/boot/loader/**` (not runtime JARs like `org.springframework.boot:spring-boot`).
- `static-assets` grabs static files under `BOOT-INF/classes/static/**`; other classes/manifest/resources fall into `application`.

**Never remove the `intoLayer("application")` or `intoLayer("dependencies")` fallbacks** when adding custom matchers unless you have proved every entry is claimed. Missing a fallback can cause layer configuration errors or an unusable artifact.

### 4.2. Why Can Layer Names Be Customized?

`intoLayer("static-assets")` and `intoLayer("spring-boot-dependencies")` are **logical names chosen by the author**; there is no special Java module with those names. Names appear in `BOOT-INF/layers.idx` and in extracted directories when using jarmode tools. When renaming them, you must update:
- `layerOrder`;
- index verification commands;
- `COPY --from=...` paths in the Dockerfile;
- any image-tool logic that hardcodes the old layer names.

A layer name does not create a new Gradle task, nor does it publish a dependency JAR under a new classifier.

## 5. Complete Runnable Java 17 Spring Boot Application Example

This example suffices to build a single-module Gradle project and test custom layering. `static/info.txt` verifies the custom `static-assets` layer; the Java controller verifies the `application` layer; dependencies from `spring-boot-starter-web` populate the dependency JAR layers.

### 5.1. Project Structure

```text
layer-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/com/example/layer/LayerDemoApplication.java
└── src/main/resources/static/info.txt
```

You need JDK 17+ and a Gradle Wrapper compatible with Spring Boot plugin 3.5.0. In a repository with an existing Wrapper, use `./gradlew`. In a repo without a Wrapper, use a compatible installed Gradle to run `gradle wrapper` or invoke the Gradle CLI directly, then commit the wrapper files to the repository.

### 5.2. `settings.gradle.kts` File

```kotlin
rootProject.name = "layer-demo"
```

### 5.3. Complete `build.gradle.kts` File

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

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
}

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }
            intoLayer("static-assets") {
                include("BOOT-INF/classes/static/**")
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
            intoLayer("spring-boot-dependencies") {
                include("org.springframework.boot:*:*")
            }
            intoLayer("dependencies")
        }

        layerOrder.set(
            listOf(
                "spring-boot-dependencies",
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "static-assets",
                "application"
            )
        )
    }
}
```

**Why is this configuration complete?** The Java plugin provides source sets/tasks; the Spring Boot plugin creates `bootJar`; the dependency-management plugin resolves Spring Boot dependency versions consistently via the BOM; `java.toolchain` uses the proper Java 17 compiler; `layered` configures the layer index when building the executable JAR.

When working in a real project that already has `plugins`, `repositories`, and `dependencies`, **do not paste duplicate `plugins` blocks or duplicate `bootJar` tasks**. Add/merge only the `tasks.named<BootJar>("bootJar")` configuration and follow the repo's plugin version conventions.

### 5.4. Java Main Class

**`src/main/java/com/example/layer/LayerDemoApplication.java`:**

```java
package com.example.layer;

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

    @GetMapping("/layers")
    public String layers() {
        return "layers-ok";
    }
}
```

### 5.5. Static Resource

**`src/main/resources/static/info.txt`:**

```text
STATIC_LAYER_OK
```

Spring Boot MVC serves files in `static` under `/info.txt`. Inside the archive, the file lives at `BOOT-INF/classes/static/info.txt` and the custom matcher assigns it to `static-assets`.

### 5.6. Building and Testing the Application

From the `layer-demo` root:

```bash
./gradlew clean bootJar
java -jar build/libs/layer-demo-0.1.0.jar
```

Once the web server is up on port 8080 (assuming no override and the port is free), call from another terminal:

```bash
curl -fsS http://localhost:8080/layers
curl -fsS http://localhost:8080/info.txt
```

Expected response bodies, respectively:

```text
layers-ok
STATIC_LAYER_OK
```

Two separate `curl` calls may display consecutively without a break because the Java String response does not add a trailing newline; the static file may preserve its trailing newline. Use Ctrl+C to stop the app. If port 8080 is busy, run `java -jar ... --server.port=9090` and update the URLs accordingly.

**A common mistake:** running `./gradlew jar` and inspecting `build/libs/layer-demo-0.1.0-plain.jar` instead of `bootJar`. The Gradle Java plugin's plain JAR is not an executable Spring Boot JAR; it normally lacks nested dependencies and `BOOT-INF/layers.idx`.

## 6. Inspecting layers.idx and Archive Layout

After `./gradlew clean bootJar`:

```bash
jar tf build/libs/layer-demo-0.1.0.jar
```

Entries to look for:

```text
BOOT-INF/layers.idx
BOOT-INF/classes/com/example/layer/LayerDemoApplication.class
BOOT-INF/classes/static/info.txt
BOOT-INF/lib/spring-boot-3.5.0.jar
org/springframework/boot/loader/launch/JarLauncher.class
META-INF/MANIFEST.MF
```

This is a list of **representative entries**, not full output or a guarantee of all dependency versions. `jar tf` only confirms presence; it does not read **layer assignments**.

### 6.1. Reading the Index with unzip

On Linux/macOS or environments with `unzip`:

```bash
unzip -p build/libs/layer-demo-0.1.0.jar BOOT-INF/layers.idx
```

The index must contain **six layer names**, in the exact declared order:

```text
spring-boot-dependencies
dependencies
spring-boot-loader
snapshot-dependencies
static-assets
application
```

The list above is only **the names to recognize**, not the verbatim contents of `layers.idx`. The real file uses YAML-compatible syntax with quoted keys/paths:

```yaml
- "spring-boot-dependencies":
  - "BOOT-INF/lib/spring-boot-3.5.0.jar"
- "dependencies":
  - "BOOT-INF/lib/spring-web-6.x.x.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
- "static-assets":
  - "BOOT-INF/classes/static/"
- "application":
  - "BOOT-INF/classes/com/example/layer/"
  - "META-INF/"
```

This is a **shortened illustration** of the index format; do not copy it into a JAR as an exact file. Additional resource paths, `META-INF`, project JARs, and empty entries may appear. The `spring-web` version in the example is a descriptive placeholder, not a literal filename.

**Expected logic checks:**
- `spring-boot-3.5.0.jar`: belongs to `spring-boot-dependencies` (because of group `org.springframework.boot`).
- `spring-web-...jar`: belongs to `dependencies` (because of group `org.springframework`).
- `static/info.txt`: belongs to `static-assets`.
- `LayerDemoApplication.class`: belongs to `application`.
- Launcher classes: belong to `spring-boot-loader`.

If the static file ends up in `application`, check the `BOOT-INF/classes/static/**` matcher path, whether the file actually lives under `src/main/resources/static`, and whether you are inspecting the right JAR.

### 6.2. Inspecting on Windows PowerShell

The JDK `jar` tool runs on Windows:

```powershell
jar tf build/libs/layer-demo-0.1.0.jar |
    Select-String 'BOOT-INF/layers.idx|BOOT-INF/classes/static/info.txt'
```

To read `layers.idx`, use a ZIP tool that can open entries inside the JAR (PowerShell/.NET ZipArchive, 7-Zip, or an IDE). Do not assume `unzip` is always available on Windows. Never rename a JAR to ZIP and manually edit/re-zip it, as that can corrupt the manifest, ordering, or timestamps.

## 7. Matcher Rules for application and dependencies

### 7.1. application Patterns Are Archive File Paths

`application.intoLayer(...)` uses Ant-style path matching. Examples:

| Pattern | What does it match? | Used for |
| --- | --- | --- |
| `org/springframework/boot/loader/**` | Spring Boot launcher classes | `spring-boot-loader` |
| `BOOT-INF/classes/static/**` | Static web resources | `static-assets` |
| `BOOT-INF/classes/templates/**` | Template files | Separate template layer if needed |
| `BOOT-INF/classes/db/migration/**` | SQL migrations | Migrations layer if caching makes sense |
| `BOOT-INF/classes/com/example/**` | Application bytecode/resource paths | A group of application classes |
| `META-INF/**` | Manifest/metadata | Separate only with a clear reason |

**Do not use `src/main/resources/static/**`** as a matcher in `layered.application`; that is the **pre-packaging** source path, whereas the DSL classifies archive entries by **post-packaging** paths. In an executable Boot JAR, the resource root sits inside `BOOT-INF/classes`.

Matchers select **files inside the archive**; they do not control the `processResources` task. If you want to omit a file from the archive, edit Gradle resource copy/excludes or source sets; `layered.application.intoLayer` only chooses the layer.

### 7.2. dependencies Patterns Are Maven/Gradle Module Coordinates

`dependencies.intoLayer(...)` checks `group:artifact[:version]`, not filenames like `spring-web-...jar`:

```kotlin
dependencies {
    intoLayer("spring-boot-dependencies") {
        include("org.springframework.boot:*:*")
    }
    intoLayer("dependencies")
}
```

Matcher examples:
- `org.springframework.boot:*:*`: all artifacts in the Spring Boot group.
- `com.example:shared-api:*`: a shared API artifact in group `com.example`.
- `*:*:*SNAPSHOT`: module versions whose suffix matches the SNAPSHOT pattern.
- `com.vendor:*:*`: artifacts in group `com.vendor`, if the project uses them.

**Do not write `BOOT-INF/lib/spring-boot-*.jar` in the `dependencies` block** to select a dependency group: that is a file path, not coordinates. Conversely, do not use `org.springframework.boot:*:*` inside the `application` block to select Java classes.

### 7.3. Include/Exclude Order Can Overlap

Suppose an artifact has coordinates `com.vendor:agent:1.0-SNAPSHOT`, matching both:
- `*:*:*SNAPSHOT`;
- `com.vendor:*:*`.

If the snapshot block appears first, the artifact is claimed by `snapshot-dependencies`; the later vendor block will not receive it. If you want “vendor takes priority regardless of SNAPSHOT”, put the vendor layer first. The two choices reflect **different cache policies**; there is no single universal rule.

### 7.4. Project Dependencies Differ from External SNAPSHOTs

A Gradle dependency:

```kotlin
dependencies {
    implementation(project(":shared-lib"))
}
```

is a **project dependency**, unlike:

```kotlin
dependencies {
    implementation("com.example:shared-lib:0.1.0-SNAPSHOT")
}
```

The first line references a sibling project in the same multi-project build and is claimed by `includeProjectDependencies()`; the second is a module dependency with GAV coordinates from a repository, matching `*:*:*SNAPSHOT`. They may share the same `artifactId` yet have different source management and caching behavior.

## 8. Equivalent Gradle Groovy DSL

If the project uses `build.gradle` (Groovy) instead of `build.gradle.kts` (Kotlin), the concepts are identical, though the syntax differs.

**Snippet placed in `build.gradle` with the Spring Boot plugin already applied**:

```groovy
tasks.named('bootJar') {
    layered {
        application {
            intoLayer('spring-boot-loader') {
                include 'org/springframework/boot/loader/**'
            }
            intoLayer('static-assets') {
                include 'BOOT-INF/classes/static/**'
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
            intoLayer('spring-boot-dependencies') {
                include 'org.springframework.boot:*:*'
            }
            intoLayer('dependencies')
        }

        layerOrder = [
            'spring-boot-dependencies',
            'dependencies',
            'spring-boot-loader',
            'snapshot-dependencies',
            'static-assets',
            'application'
        ]
    }
}
```

This is **not a complete `build.gradle` file**: you still need `plugins` (`java` and Spring Boot), repositories/dependencies/toolchain as in the Kotlin example. Do not mix Groovy's `layerOrder = [...]` syntax with Kotlin DSL's `layerOrder.set(listOf(...))` in the same file.

### Kotlin DSL vs. Groovy DSL Comparison

| Task | Kotlin DSL | Groovy DSL |
| --- | --- | --- |
| Reference task | `tasks.named<BootJar>("bootJar")` | `tasks.named('bootJar')` |
| Match files | `include("BOOT-INF/classes/static/**")` | `include 'BOOT-INF/classes/static/**'` |
| Project libs | `includeProjectDependencies()` | `includeProjectDependencies()` |
| Layer order | `layerOrder.set(listOf("a", "b"))` | `layerOrder = ['a', 'b']` |
| Disable index/layering | `layered { enabled.set(false) }` | `layered { enabled = false }` |
| Disable jar tools in Boot 3.5 | `includeTools.set(false)` **on BootJar** | `includeTools = false` **on bootJar** |

When copying snippets from Spring Boot 2.5 or older posts, you may see `includeLayerTools`, `isIncludeLayerTools`, and jar mode `layertools`. In Spring Boot 3.5, **`includeTools`** on `BootJar` and `jarmode=tools` are the current options. Check docs matching your version to avoid “unknown property/method” errors.

## 9. Do Not Customize Layers When Defaults Suffice

For many services, the default `dependencies → spring-boot-loader → snapshot-dependencies → application` is sensible and easy to manage. Customize only when you have **evidence** that a group of dependencies or resources has a distinct change cadence and your Dockerfile/CI actually leverages layer caching.

Valid reasons:
- A group of framework JARs rarely changes and should be cached independently of other third-party libs.
- Multi-project modules change alongside app source and must be separated from external releases.
- Static resources change less often than Java classes, warranting a `static-assets` layer.
- Migrations/schemas change on their own cadence, justifying caching or clear diff inspection.
- Reducing CI registry push/pull time via layers with stable digests.

**Insufficient** reasons:
- Wanting to reduce runtime RAM by adding layers: layer metadata does not partition the heap.
- Wanting to “run dependencies first”: image layers are unrelated to class loading order.
- Wanting to fix version conflicts: use dependency resolution/constraints, not layer matchers.
- Wanting an immediately smaller image: splitting layers **does not reduce total bytes** and may slightly add metadata/overhead.
- Wanting to encrypt secrets: secrets should not be packaged into executable JARs or images; layering is not a security mechanism.

**Success metrics** should be changes in **image layer digests**, build times, registry upload/download bytes, cache hits, alongside startup and correctness—not simply counting layers in `layers.idx`.

## 10. When to Disable Layering or Omit JAR Tools

### 10.1. Disabling Layering

If you do not use image layer extraction/buildpack metadata and do not want `layers.idx` in the artifact:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(false)
    }
}
```

**This is a replacement configuration**, not to be pasted alongside custom `layered { application {...} ... }` from the previous section inside the same `bootJar`. When layering is disabled, do not expect `BOOT-INF/layers.idx`. The JAR still runs via `java -jar`, but it lacks metadata for layer extraction.

Groovy:

```groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
```

### 10.2. Keeping layers.idx While Omitting jarmode Tools from the JAR

In Spring Boot 3.5, `BootJar` supports the **`includeTools`** property. If deployment does not need to invoke jar tools itself, you can omit the tools dependency:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
```

Groovy:

```groovy
tasks.named('bootJar') {
    includeTools = false
}
```

This is an **additional configuration at the `BootJar` level**, not `layered { includeLayerTools... }` from older Boot versions. Setting `includeTools` to false does not disable layering: `BOOT-INF/layers.idx` can still be generated. However, `java -Djarmode=tools -jar app.jar ...` will **not work** if jar mode tools are absent from the archive; an extraction-based Dockerfile would have to use external tooling or re-enable tools. **For the demos in sections 5/12, keep the default `includeTools=true`.**

### 10.3. Fully Executable Archives with Launch Scripts

Some Spring Boot Gradle builds prepend a Unix launch script to the JAR via `launchScript()`. For artifacts needing `java -Djarmode=tools -jar ... extract`, avoid fully executable JARs with a script prefix: some ZIP/JAR tools and jar mode do not handle that format properly. The demo uses a **standard executable JAR** (run via `java -jar`), without a launch script.

## 11. Extracting Layers with Spring Boot Jar Tools

Spring Boot 3.5 supports **`-Djarmode=tools`**, providing commands such as `list-layers`, `extract`, and `help` when tools are included in the archive (default for layered Boot JARs).

For the demo:

```bash
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar list-layers
```

The output lists the indexed layer names. Main contents to verify:

```text
spring-boot-dependencies
dependencies
spring-boot-loader
snapshot-dependencies
static-assets
application
```

These are **the expected layer names**, without promising exact console formatting or guaranteeing every layer contains files.

Extract into directories:

```bash
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar \
  extract --layers --destination build/extracted
```

When operating normally, `build/extracted` contains directories named after the layers (empty layers may not have directories created), holding the corresponding JAR contents. For example:
- `build/extracted/spring-boot-dependencies/BOOT-INF/lib/...`;
- `build/extracted/dependencies/BOOT-INF/lib/...`;
- `build/extracted/static-assets/BOOT-INF/classes/static/info.txt`;
- `build/extracted/application/...`.

Distinguish **extraction paths** from logical layer index contents. `extract --layers` produces the filesystem layout for Dockerfile copies; `java -jar build/libs/layer-demo-0.1.0.jar` still runs the application from the original JAR without needing prior extraction.

### 11.1. If jarmode Tools Fail to Run

Check:
1. Are you using the actual executable Boot JAR from `bootJar`, rather than the plain `jar`?
2. Was `includeTools.set(false)` applied?
3. Is `-Djarmode=tools` placed **before `-jar`**?
4. Are you using Boot 3.5 or following an older `layertools` guide?
5. Is the JAR a fully executable archive with an incompatible launch-script prefix?
6. Does `layers.idx` exist when `--layers` is requested?
7. Are you using a Java 17+ runtime and is the archive uncorrupted?

Correct command:

```bash
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar list-layers
```

Do not use:

```bash
java -jar build/libs/layer-demo-0.1.0.jar --jarmode=tools
```

The second line passes an argument to the **Spring Boot application**, rather than setting a JVM system property to switch the Boot launcher to jar mode. It is not equivalent to the first command.

## 12. Multi-Stage Dockerfile Leveraging Custom Layers

Here is how you see the benefit of the layered DSL: use jar tools to extract the archive into directories named after the custom layers, then copy each group into the runtime image in your chosen order.

**`Dockerfile` matching the Kotlin DSL project in section 5:**

```dockerfile
FROM eclipse-temurin:17-jre AS unpack
WORKDIR /workspace
COPY build/libs/layer-demo-0.1.0.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted \
    && mkdir -p extracted/snapshot-dependencies

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=unpack /workspace/extracted/spring-boot-dependencies/ ./
COPY --from=unpack /workspace/extracted/dependencies/ ./
COPY --from=unpack /workspace/extracted/spring-boot-loader/ ./
COPY --from=unpack /workspace/extracted/snapshot-dependencies/ ./
COPY --from=unpack /workspace/extracted/static-assets/ ./
COPY --from=unpack /workspace/extracted/application/ ./

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
```

**Conditions for the example:**
- `./gradlew clean bootJar` has already produced `build/libs/layer-demo-0.1.0.jar`.
- `docker build` runs at the project root; the Docker build context includes the JAR and no `.dockerignore` excludes it.
- The JAR keeps the default `includeTools=true` so the builder can extract it.
- `static-assets` contains `info.txt` so it has content; `snapshot-dependencies` may be empty, so `mkdir -p` in the builder ensures Docker `COPY` does not fail simply because the directory was not created.
- Both builder and runtime use JRE 17 compatible with the demo's class files.
- Layer names in `COPY` must **match `layerOrder` and the layer index exactly**; renaming a layer in Gradle requires updating the Dockerfile.
- `application.jar` at runtime is the extracted archive for this run mode per the jar-tools layout; **it is not the original fat JAR** initially copied from `build/libs`.

Run:

```bash
./gradlew clean bootJar
docker build -t layer-demo:dev .
docker run --rm -p 127.0.0.1:8080:8080 layer-demo:dev
```

Once the container is running, `curl -fsS http://localhost:8080/layers` should return `layers-ok`; `curl -fsS http://localhost:8080/info.txt` should return `STATIC_LAYER_OK`. If the Dockerfile uses another base image, check the Java runtime and filesystem permissions before deploying.

**Important about caching:** Docker processes `COPY` sequentially. When only the Java controller changes, `application` normally changes while earlier `spring-boot-dependencies`/`dependencies` layers can still be cached. When a dependency version in `dependencies` changes, that layer and subsequent steps may be invalidated. Dockerfile order should align with `layerOrder` and actual change frequency. Cache efficiency also depends on the Docker builder, registry setup, base image, and byte-level reproducibility of each layer.

### 12.1. Why Not Just COPY the Whole JAR?

A minimal Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /application
COPY build/libs/layer-demo-0.1.0.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
```

still **works** and is simple. However, every time the fat JAR changes, that `COPY` command can invalidate an image layer containing the **entire JAR**, including unchanged dependency JARs. Layered extraction splits the contents into multiple `COPY`s so the OCI builder/registry can reuse stable blocks. If the app is small or the pipeline lacks an image cache, the added complexity may not be worthwhile.

### 12.2. Docker Cache Does Not Mean Reproducible JARs

Two Gradle builds can produce different JAR bytes due to timestamps, generated metadata, or input dependencies, even when source is unchanged. When that happens, extracted layer contents/digests may change and cache hit rates suffer.

Recommended practices:
- Deterministic Gradle Wrapper/Java toolchain and dependency versions.
- Archive tasks producing stable file ordering/timestamps (newer Gradle has reproducible defaults; configure explicitly on older versions).
- Avoid embedding build timestamps, absolute paths, or secrets in generated resources.
- Compare layer contents and image layer hashes between two builds of the same commit.
- Do not overuse `--no-cache` when measuring cache effectiveness; test both cold and warm builds.

## 13. Multi-Project Gradle: Which Layer Do Project Dependencies Belong To?

A large repository may look like:

```text
settings.gradle.kts
├── core/
├── service/
└── app/
```

`app` references a sibling project:

```kotlin
dependencies {
    implementation(project(":service"))
}
```

A project JAR such as `:service` may appear inside executable `app` when Gradle resolves `runtimeClasspath`. **By default, Spring Boot classifies project dependencies into the `application` layer** because in a monorepo they tend to change quickly. The custom DSL in section 4 preserves that behavior:

```kotlin
dependencies {
    intoLayer("application") {
        includeProjectDependencies()
    }
    // Remaining dependency groups...
}
```

This block belongs inside `layered { dependencies { ... } }` on the **`app` module's `bootJar` task**, not Gradle's top-level `dependencies`. Both DSL blocks share the name `dependencies`, but their scopes are completely different:

- `dependencies { implementation(project(":service")) }`: declares **runtime/compile dependencies** of the Gradle project.
- `layered { dependencies { intoLayer(...) } }`: **groups already-resolved dependencies** into layer metadata.

### 13.1. When to Split Project Dependencies into a Separate Layer

If app source changes frequently while the `:service` module rarely changes, you can move project dependencies into a `project-dependencies` layer:

```kotlin
tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }
            intoLayer("application")
        }
        dependencies {
            intoLayer("project-dependencies") {
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
                "project-dependencies",
                "application"
            )
        )
    }
}
```

This is a **standalone alternative configuration** compared to the six-layer setup in section 4. Do not paste two `tasks.named<BootJar>` blocks with different layer selections hoping order resolves itself. In a multi-project repo, `bootJar` configuration belongs on the **application project** or a convention plugin intentionally applied to app modules. Library modules like `core`/`service` may only need the `jar` task and should not build executable Boot JARs.

**Trade-off:** separating project dependencies can improve cache reuse when only the app changes; however, if the service module changes alongside the app on most commits, that layer gets invalidated frequently anyway. Base decisions on observed changes, not assumptions.

## 14. Testing the Impact of Individual Changes on Layer Caching

A testing workflow can use three builds:

### 14.1. Build A — Baseline

```bash
./gradlew clean bootJar
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar \
  extract --layers --destination build/extracted-a
```

Record the layer list, file counts, total sizes, and SHA-256 checksums of key files. When running multiple times in the same workspace, avoid running `extract` into an uncleaned directory; tools may refuse to write to a non-empty destination or overwrite according to their own policy.

### 14.2. Build B — Edit Only the Java Controller

Change the `/layers` response from `layers-ok` to another string, **keeping dependency versions and the static resource unchanged**. Rebuild and extract into a new directory. Expectations:
- The `application` layer contains changed class bytecode.
- `static-assets` and dependency layers stay unchanged, provided inputs/generators/archive metadata are controlled.
- Runtime response reflects the new code.

If `spring-boot-dependencies` also changes despite unchanged dependencies, check Gradle dependency resolution, archive reproducibility, timestamps/permissions, or generated files affected by the build.

### 14.3. Build C — Edit Only static info.txt

Keep Java code and dependency versions unchanged, and edit `src/main/resources/static/info.txt`:
- The `static-assets` layer changes.
- `application` bytecode may remain unchanged.
- Response from `/info.txt` changes.
- Because `static-assets` precedes `application` in the Dockerfile, depending on image builder caching, steps after `static-assets` may be invalidated even though application bytecode stayed identical. Layer order should therefore be tuned to actual change frequency.

To measure real impact, build the Docker image twice with BuildKit/cache enabled, and compare output layer digests and registry transfers—not just the checksum of `build/libs/*.jar`. A container image is a different artifact from a JAR; a modified JAR does not mean **every extracted layer** changed.

## 15. Wrong Layer Names and Patterns: How Does Gradle React?

### 15.1. Wrong `layerOrder`

Suppose you have:

```kotlin
intoLayer("static-assets") {
    include("BOOT-INF/classes/static/**")
}
```

yet `layerOrder` omits `static-assets`. This configuration is inconsistent: every layer name referenced by a matcher must appear in the ordered list. The Spring Boot plugin may fail when building layers or packaging. Fix it by updating `layerOrder.set(...)` to list all layers accurately without typos (`static-asset` vs. `static-assets`).

### 15.2. Misplaced Catch-All

**Wrong:**

```kotlin
application {
    intoLayer("application")
    intoLayer("static-assets") {
        include("BOOT-INF/classes/static/**")
    }
}
```

The first `application` block claims all remaining entries, leaving `static-assets` with no files. **Right:** put specialized matchers first and the catch-all last. The same principle applies to `dependencies`.

### 15.3. Pattern from One Section Used in the Wrong Section

`include("org.springframework.boot:*:*")` is coordinates for **dependencies**, not an application file path. `include("BOOT-INF/classes/static/**")` is a path for **application**, not dependency coordinates. A pattern can be syntactically valid yet match nothing, causing unexpected layer assignments.

### 15.4. Exclude Does Not Delete Files from the Executable JAR

`exclude("com.vendor:legacy:*")` inside `intoLayer("vendor")` means **do not place this artifact in the `vendor` layer**. If the `dependencies` catch-all below claims it, the JAR still contains `BOOT-INF/lib/legacy-...jar`. To remove a dependency completely, use Gradle dependency resolution/exclusions in the right place and confirm the app still runs.

### 15.5. SNAPSHOT and Project Dependency Overlap

A project dependency in a multi-project build and an external SNAPSHOT are not the same thing. `includeProjectDependencies()` selects local project outputs, while `include("*:*:*SNAPSHOT")` matches GAV patterns of module dependencies. When a different policy is needed, order matchers by priority and inspect `layers.idx` rather than guessing from version strings or filenames.

## 16. Common Errors and How to Fix Them

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `Unresolved reference: BootJar` in Kotlin DSL | Missing import or plugin not applied | Add `import org.springframework.boot.gradle.tasks.bundling.BootJar` and apply the Spring Boot plugin |
| `Task 'bootJar' not found` | Running in a library project or Java/Spring Boot plugin missing | Configure the app module properly; verify plugins/tasks |
| Missing `BOOT-INF/layers.idx` | Layering disabled or inspecting a plain JAR | Check `bootJar`, `enabled`, and the right `build/libs` file |
| Gradle reports missing layer order | Custom `application`/`dependencies` defined without setting `layerOrder` | Add an ordered list covering every referenced layer |
| Custom layer exists by name yet has no files | Wrong matcher, no matching content, or an earlier catch-all claimed everything | Read `layers.idx`, check archive paths/GAVs, adjust matcher order |
| `spring-boot-loader` is empty | Wrong pattern (confusing groupId with path) | Use `org/springframework/boot/loader/**` in the `application` section |
| `static-assets` is empty | Used `src/main/resources/static/**` instead of archive path | Use `BOOT-INF/classes/static/**` and ensure the file is packaged |
| External SNAPSHOT falls into regular `dependencies` | Wrong snapshot matcher or claimed earlier by another group | Use `*:*:*SNAPSHOT` and verify order |
| Project JAR missing from `application` layer | Missing `includeProjectDependencies()` or custom policy | Specify policy/project selector explicitly; inspect `layers.idx` |
| `-Djarmode=tools` fails to run | `includeTools=false`, using plain JAR, JVM option misplaced | Use the right BootJar, enable tools, place `-D` before `-jar` |
| Docker COPY layer path reports not found | Different layer name, empty layer directory not created, wrong extract path | Sync `layerOrder`/Dockerfile; create empty dirs if needed |
| Container missing classes/resources after extract | Missed copying some layers or omitted extracted app jar | Copy all required layers and run a smoke test |
| Docker cache does not improve | Image copies whole JAR, poor layer order, generated files constantly changing | Use extracted COPYs, measure layer digests and stable outputs |
| `bootBuildImage` ignores custom Dockerfile | Buildpacks do not read your Dockerfile | Distinguish buildpack image workflows from Dockerfile workflows |
| Layer tool CLI from older guides fails | Using old `layertools`/`includeLayerTools` on Boot 3.5 | Use `jarmode=tools` and `includeTools` |
| Layer with Spring Boot libs changes every build | Dynamic version ranges/SNAPSHOTs, unstable metadata | Pin dependencies/versions, check cache and generated files |
| Java service runs raw JAR fine yet image fails | Dockerfile copies in wrong order/location or wrong runtime JRE | Check extracted layout and container logs |
| Gradle `jar` and `bootJar` create two different files | Picked the plain artifact by mistake | Use executable `bootJar` output; inspect manifest/layers |
| `layers.idx` exists yet image has no separate layers | Dockerfile only runs `COPY app.jar`, not a layer-aware build | Extract and COPY layers or use image tooling with support |

### Recommended Debugging Sequence

1. Confirm Spring Boot Gradle Plugin and Gradle Wrapper versions.
2. Run `./gradlew clean bootJar`; make sure the command succeeds.
3. Confirm the output filename/version is right; do not use `-plain.jar`.
4. `jar tf` to check `BOOT-INF/layers.idx`, classes/resources, and dependency JARs.
5. `unzip -p ... BOOT-INF/layers.idx` to inspect names, order, and paths.
6. Verify `application` patterns = archive entry paths, `dependencies` patterns = module coordinates.
7. Verify matcher order: specialized selectors first, catch-alls last.
8. Verify `layerOrder` lists every layer used.
9. Run `java -Djarmode=tools ... list-layers` and `extract --layers` with `includeTools=true`.
10. Inspect filesystem extract output and each `COPY` in the Dockerfile.
11. Run `java -jar`/container smoke tests for `/layers` and `/info.txt`.
12. If caching does not improve, compare layer contents/digests between two builds and inspect dependency resolution, timestamps, and actual changes.

## 17. Differences Between BootJar.layered and Other Gradle Mechanisms

| Mechanism | Scope | Creates an OCI image? |
| --- | --- | --- |
| `tasks.named<BootJar>("bootJar") { layered { ... } }` | Assigns executable JAR entries to the logical layers index | No |
| `bootJar` | Builds executable Boot JAR | No |
| `jar` | Builds plain Java JAR | No |
| `bootRun` | Runs app via a `JavaExec`-like task during development | No |
| `bootBuildImage` | Builds OCI image via Cloud Native Buildpacks | Yes, as configured |
| Dockerfile + jar tools extract | Builds image from extracted layers using Docker/BuildKit | Yes, when running `docker build` |
| Gradle build cache | Caches Gradle task outputs by inputs | Not directly |
| Docker layer cache | Caches container image filesystem layers | Yes |
| Spring Boot `layers.idx` | Maps archive paths to logical layers | Not directly |

**An important misconception:** “Having `layers.idx` means Docker caching works automatically”. Incorrect. If the Dockerfile only has `COPY build/libs/layer-demo.jar app.jar`, the OCI builder does not automatically split each entry in `layers.idx` into filesystem layers. You need jar tools extraction, buildpacks, or other tooling that understands the index.

## 18. Security, Build Quality, and Layering

### 18.1. Layering Does Not Protect Secrets

If `application.properties` contains a password under `src/main/resources`, that file goes into `BOOT-INF/classes` and belongs to a layer. Docker images and JARs can be inspected; **layering does not encrypt or hide contents**. Supply secrets via environment variables/secret managers/mounted files at **runtime**, never baked into source resources or generated metadata.

### 18.2. Reproducibility Affects Caching

For the same dependency layer to yield the same digest across builds:
- Pin versions/plugin repositories and avoid dynamic version ranges.
- Use a consistent Java toolchain/Gradle Wrapper.
- Do not write current timestamps or workspace paths into artifacts.
- Use Gradle archive reproducibility options if needed for a specific version.
- Audit generated code/resource tasks and annotation processors.
- Compare extracted contents rather than only counting layer names.

Creating more layers does not make a non-deterministic build deterministic.

### 18.3. Licenses, SBOM, and Dependency Vulnerabilities

The `spring-boot-dependencies`/`dependencies` layers still contain all resolved runtime libraries. Changing layers does not remove a library with a CVE or alter its license. Use dependency reports, SBOMs, and vulnerability scanning per organizational policy; when a dependency must be removed, fix the actual Gradle configuration.

### 18.4. Runtime Permissions and Filesystem

In a Docker image, you can run as a non-root user and copy files with appropriate read permissions. `USER 10001` in the example Dockerfile assumes extracted files and the app JAR are world-readable; if your build environment uses different permissions, verify with an image smoke test. Layering does not replace `securityContext`, network policies, or secret handling.

## 19. Checklist Before Applying Custom BootJar Layers

- [ ] Confirmed the application module uses `bootJar`, not plain `jar`.
- [ ] Spring Boot/Gradle versions are pinned and compatible with the Java runtime.
- [ ] Have evidence that default layers are insufficient for your caching/change profile.
- [ ] Kotlin DSL uses the `BootJar` import, `tasks.named<BootJar>`, and `layerOrder.set(listOf(...))`.
- [ ] Groovy DSL uses `tasks.named('bootJar')` and `layerOrder = [...]`.
- [ ] `application` matchers use archive paths, e.g., `BOOT-INF/classes/static/**`.
- [ ] `dependencies` matchers use GAV patterns, e.g., `org.springframework.boot:*:*`.
- [ ] `includeProjectDependencies()` is weighed separately against external SNAPSHOTs.
- [ ] Specific `intoLayer` rules precede catch-all fallbacks.
- [ ] `layerOrder` includes all layer names, placing stable layers before frequently changing ones.
- [ ] Inspected actual `BOOT-INF/layers.idx` after `./gradlew bootJar`.
- [ ] Tested `java -Djarmode=tools ... list-layers` and extract if needed.
- [ ] Dockerfile/Buildpacks actually use a layer-aware pipeline.
- [ ] Dockerfile copies match exact layer names/order; empty layers handled.
- [ ] Have an HTTP/runtime smoke test against the image, not just `BUILD SUCCESS`.
- [ ] Measured cache hits, build times, registry push/pull, and image size.
- [ ] No secrets in JAR/layers and layers are not used to “resolve” dependency version conflicts.
- [ ] CI reproducibly pins inputs, JDK, Gradle wrapper, and dependencies.

## 20. Official Documentation

- Spring Boot 3.5 – [Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html): `BootJar`, layered JARs, custom `application`/`dependencies`/`layerOrder`, and `includeTools`.
- Spring Boot 3.5 – [BootJar API](https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootJar.html): task, `layered`, and packaging tools.
- Spring Boot 3.5 – [LayeredSpec API](https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/LayeredSpec.html): layer selectors and ordered configuration.
- Spring Boot 3.5 – [Efficient Container Images](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/efficient-images.html): layer structure and caching strategy.
- Spring Boot 3.5 – [Dockerfiles](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html): jar tools mode, `extract --layers`, and multi-stage Dockerfiles.
- Spring Boot 3.5 – [Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html): executable layout, `classpath.idx`, and `layers.idx`.
- Gradle – [Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): archive tasks, resource processing, and file order.
- Gradle – [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project dependencies and module boundaries.
- Gradle – [Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html): GAV resolution and project dependencies.

**Conclusion:** `BootJar.layered` is a DSL controlling **how executable JAR entries are assigned to logical layers**, not an API for replacing dependencies or a direct image-creation feature. `application { intoLayer(...) }` matches **paths inside the archive**; `dependencies { intoLayer(...) }` matches **dependency coordinates or project dependencies**; `layerOrder` governs layer ordering to support Docker/OCI caching. Write matchers from **specific to fallback**, inspect `BOOT-INF/layers.idx`, use `jarmode=tools` when extraction is needed, keep your Dockerfile synchronized, and measure actual cache hits before declaring optimization a success.