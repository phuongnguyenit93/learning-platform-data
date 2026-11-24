# Observing the Impact When the Boot Plugin Combines with java-library, application, and maven-publish

## 1. Goal: Understanding What Changes in Gradle When Plugins Are Combined

In a Spring Boot Gradle build, each plugin has a distinct role:

- `org.springframework.boot` adds capabilities to **run and package a Spring Boot application**, and integrates with several other plugins.
- `java-library` models a **Java module consumed as a library**: exposes an API to other modules, separates `api`/`implementation` dependencies, and publishes variants for consumers.
- `application` models a **JVM program with a `main` entry point**: provides a run command and a distribution with start scripts.
- `maven-publish` controls **what is published to a Maven repository**: creates `MavenPublication`s, POMs, and publishing tasks.

This lesson focuses on **the effects when plugins appear together**: which tasks are created, which artifacts are packaged, which artifacts are published, and whether other modules can consume it as a library JAR.

Foundational point: the Spring Boot Gradle Plugin **reacts when it detects other plugins applied**. Applying `org.springframework.boot` alone without an appropriate Java/Groovy/Kotlin plugin does not set up the full application build pipeline. Both `java-library` and `application` apply the Java plugin in Gradle, so they can trigger the `bootJar` path even without explicitly declaring `id 'java'`.

### Artifact Overview

```text
                       Gradle project
                            |
            +---------------+----------------+
            |               |                |
       java-library     application      maven-publish
            |               |                |
      Java variants    mainClass/run      publications
      apiElements      startScripts        repositories
      runtimeElements  distZip/distTar     publish tasks
            |               |
            +------- Java plugin -----------+
                            |
                     Spring Boot reacts
                      /            \
                    bootJar       bootRun
                executable JAR   run from classes
                    |
           +--------+--------+
           |                 |
     boot distribution   explicit bootJar artifact
     (with application)  (with maven-publish)
```

Quick reference table (with Spring Boot Gradle Plugin **3.5.x**, Gradle 8.x):

| Plugin combination | Primary impact | Artifacts/outputs to inspect |
|---|---|---|
| `java-library` | Inherits Java plugin; adds `api` and consumable variants | Regular `jar`, `apiElements`/`runtimeElements` |
| `org.springframework.boot` + `java-library` | Because Java plugin is present, Boot also creates `bootJar`/`bootRun`; `assemble` depends on `bootJar` | `*-plain.jar` and executable JAR; may fail if library module lacks `main` |
| `application` | Inherits Java; adds `run`, `startScripts`, and `main` distribution | Standard JVM distribution with JAR/libraries and start scripts |
| `org.springframework.boot` + `application` | Adds `bootStartScripts` and `boot` distribution; honors `application.mainClass` | `bootDistZip`/`bootDistTar` containing executable JAR and `java -jar` scripts |
| `maven-publish` | Adds `publications` and publish tasks | Publishes only configured artifacts/components; does not automatically infer publishing `bootJar` |
| `java-library` + `maven-publish` | `from components.java` publishes Java component and dependency metadata | Library JAR alongside POM/Gradle Module Metadata |
| `org.springframework.boot` + `maven-publish` | Can publish executable JAR when declaring `artifact(tasks.named('bootJar'))` | `bootJar` artifact; metadata depends on publication configuration |

**Do not equate "the build produces a JAR" with "the publication uploads that JAR to a repository".** `build/libs`, `components.java` variants, and `publishing` configuration are three separate concepts.

## 2. When Boot Meets java-library

### 2.1. java-library Is Not Simply Another Name for Boot

The `java-library` plugin extends the Java plugin, providing:

- `compileJava`, `test`, `jar`, and standard Java tasks.
- `api`: dependencies whose types appear in the library's public API signatures; consumers need them at compile time.
- `implementation`: dependencies that are internal implementation details; consumers normally do not see them on their **compile classpath**, though they still need them at runtime.
- `apiElements` and `runtimeElements`: **consumable variants** used when other modules depend on this module, attaching the proper artifact and dependency metadata.

Example in `build.gradle` of an actual **library** module:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.slf4j:slf4j-api:2.0.17'
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

This is an **illustrative declaration snippet**; `repositories { mavenCentral() }` and a complete build are needed to resolve dependencies. Use `api` when types from a dependency appear in public signatures; libraries used only inside method bodies belong in `implementation`. `implementation` does not mean "absent from the consumer's runtime".

### 2.2. What Happens If Spring Boot Is Also Applied?

```groovy
plugins {
    id 'java-library'
    id 'org.springframework.boot' version '3.5.16'
}
```

Because `java-library` pulls in the Java plugin, Spring Boot creates `bootJar`, `bootRun`, `bootBuildImage`, configures `bootArchives`, updates `assemble` to build the executable archive, and applies the `plain` classifier convention to `jar`. Consequently Gradle can produce:

- `build/libs/<module>-<version>.jar`: **executable Boot JAR**, with app classes under `BOOT-INF/classes` and runtime libraries under `BOOT-INF/lib`.
- `build/libs/<module>-<version>-plain.jar`: **regular Java JAR** produced by `jar`, usable as a standard library/classpath dependency.

Filenames follow default conventions unless `archiveBaseName`, `archiveVersion`, or `archiveClassifier` are changed. Do not assume the two files are interchangeable merely because both end in `.jar`.

**Pitfall:** a library module may have no `main` method. When `assemble` triggers `bootJar`, the task can fail because no main class is found or configured. Moreover, an executable Boot JAR **is not** a regular Java library for a compile classpath: classes sit inside `BOOT-INF/classes`, not at the root of the JAR like a library JAR.

Recommendation for multi-module projects: **apply the Spring Boot plugin only to application modules that have an entry point**. Modules like `core`, `domain`, and `shared-lib` only need `java-library` (and `maven-publish` if published); this avoids generating pointless executable JARs and preserves standard library consumption.

If a single module intentionally serves as both an application and a published API, you must explicitly manage **two distinct artifact needs** rather than arbitrarily renaming `bootJar` to `jar`.

## 3. When Boot Meets application

Gradle's `application` plugin applies the Java plugin and Distribution plugin, creating:

- `run`: runs the application's main class with the main source set's runtime classpath.
- `startScripts`: generates scripts for Windows and Unix.
- `distZip`/`distTar`: packages a standard Java distribution.
- `installDist`: installs the distribution into the build directory for testing.
- The `application` extension for declaring `mainClass` and, optionally, `applicationDefaultJvmArgs`.

When the **Spring Boot Gradle Plugin** is also present, Gradle additionally gains:

1. `bootRun`: runs the Spring Boot application from built classes/resources and the runtime classpath without packaging a JAR first.
2. `bootStartScripts`: generates scripts that launch the executable JAR in `bootArchives` via `java -jar`.
3. The `boot` distribution, typically packaged by `bootDistZip`/`bootDistTar`; contains the executable JAR in `lib` and launch scripts in `bin`.
4. `application.mainClass` serves as the convention for `bootRun`'s main class and the `Start-Class` entry in `bootJar`'s manifest.
5. `applicationDefaultJvmArgs` can be applied to run tasks and Boot distribution scripts.

Example configuration:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'application'
}

application {
    mainClass = 'com.example.app.DemoApplication'
    applicationDefaultJvmArgs = ['-Dfile.encoding=UTF-8']
}
```

This is a snippet for an application containing `com.example.app.DemoApplication`, not a complete build. The main class can be inferred by Spring Boot when unambiguous, yet **explicit declaration** helps when multiple entry points exist or for stable distributions.

| Task | How it executes | Best suited for |
|---|---|---|
| `run` | Application plugin runs main class on runtime classpath | Running a Java program with Application plugin mechanics |
| `bootRun` | `BootRun` (based on `JavaExec`) runs Spring Boot from main source set | Developing/running the app without building `bootJar` first |
| `jar` | Builds a regular Java JAR | Libraries or inputs to a standard Java distribution |
| `bootJar` | Packages app and runtime dependencies into an executable JAR | `java -jar` or Boot distributions |
| `distZip` | Packages the default Java distribution (`main`) | Scripts + JAR/libraries from the Application plugin |
| `bootDistZip` | Packages the Boot distribution | Scripts invoking the executable JAR |
| `bootBuildImage` | Builds an OCI image via buildpacks if environment supports it | Runtime container image; **not** a Maven publishing mechanism |

The file layouts inside `distZip` and `bootDistZip` organize runtime execution differently. Do not treat the two ZIPs as duplicates or expect both to run the same way. Image-building tasks also depend on a container engine/daemon or buildpacks environment, so seeing `bootBuildImage` in `tasks` does not mean an image has been built.

## 4. When Boot Meets maven-publish: Picking the Right Artifact

`maven-publish` provides `publishing { publications { ... } repositories { ... } }` and tasks such as:

- `generatePomFileFor<Publication>Publication` (POM metadata).
- `publish<Publication>PublicationTo<Repository>Repository` (uploads publication to a repository).
- `publish<Publication>PublicationToMavenLocal` and `publishToMavenLocal` (local Maven repository).
- `publish` (aggregates publishing all publications to declared repositories).

**Do not assume** applying `maven-publish` automatically publishes `bootJar`. You must create a `MavenPublication` and specify the component or artifact explicitly.

### 4.1. Publishing a Regular Library

In a module with `java-library`:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
}
```

`from components.java` pulls in the **Java component**: the regular JAR, API/runtime variants, and configured dependency metadata. This is the standard approach when consumers will place the artifact on their classpath to compile or run.

### 4.2. Publishing a Spring Boot Executable JAR Application

In an application module:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'java'
    id 'maven-publish'
}

publishing {
    publications {
        bootJava(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
```

This is the pattern recommended by Spring Boot documentation: `artifact tasks.named('bootJar')` selects the executable archive. Use this block only after configuring the main class and dependencies for a real application.

**Metadata implication:** a publication using only `artifact tasks.named('bootJar')` does not carry full dependency/variant metadata from `components.java`. This is usually fine when releasing a **self-contained executable application**, since the Boot JAR already embeds its runtime libraries. However, if consumers need API/libraries resolved transitively, publish the Java component of a **library module** rather than expecting a fat JAR to carry a library-style POM.

### 4.3. What Happens with `from components.java` on a Boot Module?

The Boot plugin sets the `plain` classifier on `jar` by convention. Because `components.java` normally references the **regular** JAR, a `from components.java` publication may publish the `-plain.jar` artifact instead of the executable JAR. When publishing to a Maven repository, if the library JAR gets a `plain` classifier while you expected a **primary JAR with no classifier**, consumers resolving normal coordinates may fail to fetch the right artifact. Do not assume `from components.java` swaps in `bootJar`.

If you genuinely need to publish **both JARs in the same publication**, assign explicit classifiers. Example **alternative snippet** for an application project with `java`, `org.springframework.boot`, and `maven-publish`:

```groovy
tasks.named('jar') {
    archiveClassifier = ''
}
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java      // Regular Java JAR: primary artifact
            artifact tasks.named('bootJar') // Executable JAR: "boot" classifier
        }
    }
}
```

This configuration lets default consumers fetch the **plain JAR**; the `boot`-classified artifact serves callers explicitly requesting the executable archive. This is an **alternative** to the `bootJava` publication in section 4.2—do not put two conflicting configurations into the same build without designing release coordinates. If you want the executable JAR as the primary artifact, prefer publishing only `bootJar` or a separate publication with a different `artifactId`; inspect the artifacts and POM after publishing.

**Never publish a Spring Boot fat JAR as a Java library merely because "the file is also a JAR".** Classes under `BOOT-INF/classes` and nested dependencies are not unpacked/loaded by a standard Java classpath the way Java libraries are designed.

## 5. Hands-On Observation Lab: A Two-Module Gradle Project

We will build a project with one Java library and one Boot application consuming that library. Splitting modules shows clearly **which plugin applies where**, while demonstrating `java-library`, `application`, and `maven-publish`.

**Requirements:** JDK 17+, Gradle 8.14.3 (or a Gradle 8.x compatible with Spring Boot 3.5), and network or cached dependencies/plugins. The example pins Spring Boot **3.5.16** for illustration; do not assume it is always the latest release. The examples below use **Groovy DSL** (`.gradle`); do not mix Kotlin DSL `.gradle.kts` syntax.

### 5.1. Directory Tree

```text
boot-plugin-lab/
├── settings.gradle
├── build.gradle
├── gradlew                  # if the project has generated the Gradle Wrapper
├── gradlew.bat              # on Windows
├── gradle/wrapper/...       # if the Gradle Wrapper has been generated
├── shared-lib/
│   ├── build.gradle
│   └── src/main/java/com/example/domain/Greeter.java
└── service-app/
    ├── build.gradle
    └── src/main/java/com/example/app/DemoApplication.java
```

The Wrapper files in the tree **exist after you generate the Gradle Wrapper**; they do not appear merely from writing `settings.gradle`. If there is no wrapper yet, you need Gradle installed to run `gradle wrapper --gradle-version 8.14.3`. Once generated, commit `gradlew`, `gradlew.bat`, and `gradle/wrapper` so others can reproduce the build.

### 5.2. Root `settings.gradle`

```groovy
rootProject.name = 'boot-plugin-lab'
include 'shared-lib', 'service-app'
```

### 5.3. Root `build.gradle`

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
}

allprojects {
    group = 'com.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
```

`apply false` brings the plugin version into root build resolution without **applying the Boot plugin to root**. Any child module needing Spring Boot applies `id 'org.springframework.boot'` itself. This avoids creating Boot tasks on library modules.

### 5.4. `shared-lib/build.gradle`

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            name = 'lab'
            url = uri(rootProject.layout.buildDirectory.dir('maven-repo').get().asFile)
        }
    }
}
```

Here `from components.java` publishes a regular library. The `lab` repository points to **root's `build/maven-repo`** for safe local observation during this lab without pushing to any external server. In real systems, use an internal Maven repository and credentials per policy.

Create `shared-lib/src/main/java/com/example/domain/Greeter.java`:

```java
package com.example.domain;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

This is a pure Java 17 library with no Spring Boot main class and no Spring Boot plugin required. `Greeter.greet("Gradle")` returns `Hello, Gradle!`.

### 5.5. `service-app/build.gradle`

```groovy
plugins {
    id 'org.springframework.boot'
    id 'application'
    id 'maven-publish'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.example.app.DemoApplication'
}

dependencies {
    implementation project(':shared-lib')

    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

publishing {
    publications {
        bootJava(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
    repositories {
        maven {
            name = 'lab'
            url = uri(rootProject.layout.buildDirectory.dir('maven-repo').get().asFile)
        }
    }
}
```

Explanation of choices:

1. `application` **already applies the Java plugin**, so `org.springframework.boot` creates `bootJar`, `bootRun`, and related tasks; you do not need to write `id 'java'` separately.
2. `application.mainClass` supplies the entry point for `run`, `bootRun`, `bootJar`, and start scripts.
3. `implementation project(':shared-lib')` declares a dependency from the app onto the library in the same build. `shared-lib` compiles before the app needs its classes.
4. `platform('org.springframework.boot:spring-boot-dependencies:3.5.16')` imports BOM version constraints via **Gradle native platform support**; `implementation 'org.springframework.boot:spring-boot-starter'` actually adds the starter. Applying the Spring Boot plugin alone **does not add** starter dependencies.
5. `bootJava` selects `bootJar` as the published artifact, whereas the library selects `components.java`.
6. You can use `io.spring.dependency-management` instead of native BOM, in which case Spring Boot imports the matching BOM automatically; avoid mixing multiple version management mechanisms without understanding application order.

### 5.6. `service-app/src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.domain.Greeter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner greetingRunner() {
        return args -> System.out.println(Greeter.greet("Gradle"));
    }
}
```

The app uses `spring-boot-starter` rather than the web starter, so it does not start an HTTP server. When it runs successfully, stdout **contains the line**:

```text
Hello, Gradle!
```

Spring Boot/Gradle may also print startup info and other logs depending on environment; do not assume stdout consists solely of one line.

## 6. Observing Each Module's Tasks and Artifacts

From the project root with Gradle Wrapper, run on Linux/macOS:

```bash
./gradlew :shared-lib:tasks --all
./gradlew :service-app:tasks --all

./gradlew :shared-lib:jar
./gradlew :service-app:jar :service-app:bootJar

./gradlew :service-app:run
./gradlew :service-app:bootRun
```

Windows PowerShell/cmd uses `gradlew.bat` instead of `./gradlew`. `run` and `bootRun` are **two independent runs** for comparison, not both needed in every build. Here both run `DemoApplication` and print the greeting; `bootRun` uses Spring Boot integration and adds conventions suited for development.

To avoid long `tasks --all` output, inspect individual tasks directly:

```bash
./gradlew :shared-lib:help --task jar
./gradlew :service-app:help --task bootJar
./gradlew :service-app:help --task bootDistZip
./gradlew :service-app:help --task publishBootJavaPublicationToLabRepository
```

**Expected observations** with the example's default names/versions:

| Location | File/task | Meaning |
|---|---|---|
| `shared-lib/build/libs/` | `shared-lib-1.0.0.jar` | Standard Java JAR, usable as a library |
| `service-app/build/libs/` | `service-app-1.0.0-plain.jar` | Regular JAR created by the `jar` task |
| `service-app/build/libs/` | `service-app-1.0.0.jar` | Executable Boot JAR created by `bootJar` |
| `:shared-lib:jar` | Java library task | Builds a library JAR even with no main class |
| `:service-app:bootJar` | Boot task | Packages app classes + runtime dependencies |
| `:service-app:run` | Application task | Runs directly from classpath |
| `:service-app:bootRun` | Spring Boot task | Runs the app from main source set |
| `:service-app:bootDistZip` | Boot distribution task | ZIP containing executable JAR and launch scripts |

Do not rely solely on the expected table if you changed `version`, `archiveClassifier`, or module names: **actual task outputs** are the source of truth.

Inspect archives with the JDK's `jar` tool:

```bash
./gradlew :service-app:bootJar :service-app:jar

# List entries of the Boot executable archive
jar tf service-app/build/libs/service-app-1.0.0.jar

# Run the executable archive
java -jar service-app/build/libs/service-app-1.0.0.jar
```

The Boot archive listing typically includes `BOOT-INF/classes/com/example/app/DemoApplication.class` and `BOOT-INF/lib/` containing runtime dependency JARs (including the `shared-lib` artifact). `-plain.jar` places classes at standard package paths like `com/example/app/DemoApplication.class` without bundling runtime dependencies. Do not expect `java -jar ...-plain.jar` to work like a Boot JAR.

To inspect how Gradle selects dependencies and variants:

```bash
./gradlew :shared-lib:outgoingVariants
./gradlew :service-app:dependencies --configuration runtimeClasspath
./gradlew :service-app:dependencyInsight --configuration runtimeClasspath --dependency shared-lib
```

`outgoingVariants` shows the Java library's variants such as `apiElements` and `runtimeElements`. For a **project dependency**, `dependencyInsight` displays relationships and variant selection reasons depending on Gradle version/config; do not read labels as promises about fat JAR layout. Also check `:shared-lib:dependencies` to compare library API and implementation dependencies.

## 7. Observing Distributions Created by application and Boot

In `service-app`, run:

```bash
./gradlew :service-app:distZip :service-app:bootDistZip
```

ZIP files are created under `service-app/build/distributions/`; exact names may include distribution name, project name, and version. Open both ZIPs to compare:

- **`main` distribution** from the Application plugin: standard scripts launching the main class with a classpath containing the JAR and dependencies in the distribution directory.
- **`boot` distribution** from Spring Boot integration: scripts generated by `bootStartScripts` launching the executable JAR via `java -jar`, with the JAR typically inside the distribution's `lib` folder.

To run scripts from a distribution, unpack the corresponding ZIP and run the script under `bin` matching the actual distribution name. On Unix, scripts require executable permissions; on Windows, use the provided `.bat` script. `bootDistZip` does not upload artifacts to a Maven repository: it packages a distribution for end users running the app.

If `bootDistZip` does not exist, check whether `application` is applied in the **app module**. If `bootJar` does not exist, check whether the Java/Application plugin is actually applied. If `bootJar` cannot find the main class, check `application.mainClass` and confirm classes compiled.

## 8. Observing maven-publish Without Pushing to an External Server

The example configures a file-based repository in root `build/maven-repo`. You can publish both publications with:

```bash
./gradlew :shared-lib:publishLibraryPublicationToLabRepository
./gradlew :service-app:publishBootJavaPublicationToLabRepository
```

Gradle creates directories matching Maven coordinates, such as:

```text
build/maven-repo/
└── com/
    └── example/
        ├── shared-lib/
        │   └── 1.0.0/
        │       ├── shared-lib-1.0.0.jar
        │       └── shared-lib-1.0.0.pom
        └── service-app/
            └── 1.0.0/
                ├── service-app-1.0.0.jar
                └── service-app-1.0.0.pom
```

Additional checksum or metadata files may also be generated depending on Gradle/repository settings; the diagram shows only the primary artifacts for recognition.

**Things to verify yourself:**

1. `shared-lib-1.0.0.jar` in the repository is a library JAR with classes at root package paths, published from `components.java`.
2. `service-app-1.0.0.jar` is a Boot executable JAR published via `artifact tasks.named('bootJar')`; it runs via `java -jar` when prerequisites are met.
3. Open both `.pom` files to inspect metadata. The library publication attached to the Java component expresses API/runtime dependencies; the Boot application publication attached only as an artifact does not necessarily list all internal dependencies.
4. Do not conclude from `publish...` succeeding that the app JAR is valid: test running the published artifact and verify `BOOT-INF/`.
5. If you change classifiers or publication names, re-check paths and coordinates; do not assume the filenames above remain unchanged.

To inspect a publication's POM before publishing, run:

```bash
./gradlew :shared-lib:generatePomFileForLibraryPublication
./gradlew :service-app:generatePomFileForBootJavaPublication
```

POM files normally appear at `<module>/build/publications/<publication>/pom-default.xml`. Do not treat Gradle Module Metadata (`.module`) and Maven POM (`.pom`) as the same format or assume they represent dependency variants identically.

### When Publishing Multiple Publications

Do not publish both a classifierless Boot app publication and a classifierless Java component publication **at the same GAV** without checking for colliding paths and artifacts. If you need both a library and an executable app, prefer **two modules or two `artifactId`s**. Within one module, you can use distinct classifiers as shown in section 4.3, provided library consumers know which one to pull. Keep intent distinct:

- **Reusable library**: `from components.java`, focused on API/runtime metadata and plain JAR.
- **Deployable/runnable app**: `artifact tasks.named('bootJar')`, focused on executable archive and release workflow.

## 9. A Small Experiment: Accidentally Applying Boot to a Library

Suppose you temporarily edit `shared-lib/build.gradle` to add the Boot plugin **as an experiment**, not a recommended setup:

```groovy
plugins {
    id 'java-library'
    id 'org.springframework.boot'
    id 'maven-publish'
}
```

With root defining the Boot version via `apply false`, this causes `shared-lib` to gain the `bootJar` task. Observe with:

```bash
./gradlew :shared-lib:tasks --all
./gradlew :shared-lib:help --task bootJar
./gradlew :shared-lib:assemble
```

`shared-lib` in this example **has no main class**. Because `assemble` depends on `bootJar`, the build fails at determining the main class for the executable JAR. That is **proof of the Boot plugin's reactive nature**, not proof that `java-library` is syntactically incompatible.

To return to a clean design, restore the original `shared-lib` config **without the Boot plugin**. Avoid faking `springBoot.mainClass` or forcing `bootJar` on a library just to make the task pass. If you genuinely must apply the Boot plugin to a non-standard module, inspect and explicitly configure the affected tasks rather than applying it blindly to every subproject.

## 10. Common Errors and Verification Directions

| Symptom | Common source | How to check/fix |
|---|---|---|
| `bootJar` does not exist | Appropriate Java/Groovy/Kotlin plugin not applied to module | Check `plugins` and `tasks --all` on the **exact module** |
| `bootJar` cannot find main class | Module is a library with no entry point or ambiguous `mainClass` | Apply Boot only to apps, or configure `application.mainClass` accurately |
| `jar` creates a `-plain.jar` file | Boot applies `plain` classifier convention to avoid clashing with Boot JAR | Expected behavior; select the artifact matching your purpose |
| Boot JAR used as dependency fails compile with missing classes | App classes live under `BOOT-INF/classes` | Publish/consume the plain JAR of a Java library |
| `application` has `run` yet lacks `bootDistZip` | Boot plugin not applied or checking wrong module | Check plugins and tasks on the app module |
| Boot ZIP name differs from expected | Distribution name/version/classifier may differ | List `build/distributions` after running the task |
| `publish` does not upload Boot JAR | Publication does not attach `bootJar` | Use `artifact tasks.named('bootJar')` |
| Publication unexpectedly uploads `-plain.jar` | `from components.java` selects the Java component | Select the Boot artifact explicitly, or use clear classifiers |
| Published app POM has very few dependencies | Publication only attached the `bootJar` artifact | Expected for an executable app; libraries use `components.java` |
| `api` is not recognized | Module uses only `java`/`application`, not `java-library` | Apply `java-library` when designing a library with an API |
| Spring Boot starter fails resolution due to missing version | Missing version management via BOM/Gradle platform | Use `platform('org.springframework.boot:spring-boot-dependencies:...')` or dependency-management plugin |
| `bootBuildImage` fails connecting to build environment | Missing compatible container engine/buildpacks | Check image build prerequisites; not a Maven publishing error |
| Other module resolves dependency yet misses classes at runtime | Wrong runtime variant/implementation or published wrong JAR | Inspect `outgoingVariants`, `runtimeClasspath`, POM, and archive |
| `publishToMavenLocal` does not put files in `lab` repo | Two different destinations | Run `publish...ToLabRepository` when targeting root `build/maven-repo` |

## 11. Observation and Architectural Decision Checklist

- [ ] Know which modules are **libraries** (reusable APIs) and which are **applications** (have `main`).
- [ ] Apply `org.springframework.boot` only to modules that run/package a Spring Boot app.
- [ ] Use `java-library` when separating API/implementation dependencies and exposing Java components to consumers.
- [ ] When applying `application`, declare `mainClass` so `run`/`bootRun`/distributions identify the entry point cleanly.
- [ ] Use `tasks --all` or `help --task ...` to see real tasks; never guess solely from plugin names.
- [ ] Distinguish `jar` (plain) and `bootJar` (executable), inspecting archives with `jar tf`.
- [ ] Distinguish `distZip` (Java distribution) and `bootDistZip` (Boot distribution).
- [ ] Publish libraries via `from components.java`, and Boot apps via `artifact tasks.named('bootJar')` when appropriate.
- [ ] Inspect classifiers, group/artifact/version, and generated `.pom` files after publishing.
- [ ] Test running the **exact published executable archive**, not just checking that the publish task succeeded.
- [ ] Verify Gradle wrapper/JDK and dependency management before blaming plugins.

**Remember:** `java-library` governs how a module is **consumed as a library**; `application` governs how a program is **run and distributed**; the Spring Boot plugin adds **executable JARs, `BootRun`, and Boot distributions** when it detects Java/Application plugins; `maven-publish` governs **which artifacts are uploaded to a repository**. Inspecting the task graph, variants, archives, and publications together is the only way to be sure a plugin combination achieves your intent.

### Official Documentation

- [Spring Boot 3.5 — Reacting to Other Plugins](https://docs.spring.io/spring-boot/3.5/gradle-plugin/reacting.html)
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Publishing Your Application](https://docs.spring.io/spring-boot/3.5/gradle-plugin/publishing.html)
- [Spring Boot 3.5 — Running Your Application](https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)