# Creating Multiple Artifacts with Classifiers and Avoiding Output Overwrites

A Spring Boot project may need **multiple artifacts from the same codebase**: a plain JAR for other modules to consume, an **executable JAR** for deployment, an API-only JAR for shared contracts, a sources JAR for source lookup, or a WAR for a specialized deployment environment. If you merely rename files manually or let two tasks write to the same path, the build can overwrite outputs, publish the wrong artifact, or cause CI to pick a non-runnable JAR.

The core solution is managing **classifiers**, **archive names**, **output ownership per task/goal**, and **publication coordinates**. This lesson explains this in detail for **Gradle and Maven in Spring Boot**, using a **Java 17** example that generates three distinct files (`plain`, `exec`, `api`), covering artifact publishing, filename collisions, and how to re-verify each JAR's contents.

The illustrative examples use **Spring Boot 3.3.13**, Java 17, and Gradle 8.x or Maven 3.9.x for consistent configuration; this is not a claim about the latest versions. When applying to real systems, prefer actively maintained releases and check documentation for your exact version.

## 1. What are artifacts and classifiers?

An **artifact** is a build output, such as `artifact-demo-1.0.0.jar`, `artifact-demo-1.0.0-exec.jar`, `artifact-demo-1.0.0-api.jar`, or `artifact-demo-1.0.0-sources.jar`. Each artifact has a distinct **content type and purpose**, not merely a different filename.

In the Maven ecosystem, artifact coordinates are typically written as:

```text
groupId : artifactId : version : extension/type : classifier (if any)

com.example : artifact-demo : 1.0.0 : jar : (no classifier)
com.example : artifact-demo : 1.0.0 : jar : exec
com.example : artifact-demo : 1.0.0 : jar : api
com.example : artifact-demo : 1.0.0 : jar : sources
```

A `classifier` is a **secondary identifier** for a variant sharing the same `groupId/artifactId/version` and packaging type. It lets repositories distinguish files at the same version, such as `artifact-demo-1.0.0-exec.jar` vs. `artifact-demo-1.0.0.jar`.

In Gradle, `archiveClassifier` is part of the **default archive filename**. It does not mean the file has been **added to a Maven publication**: producing a JAR on disk and configuring publication are two separate steps.

| Artifact | Typical contents | Primary consumer | Should it be run directly? |
| --- | --- | --- | --- |
| **Plain JAR**, no classifier | Project classes/resources at archive root | Other modules depending on app/library code | Not guaranteed: lacks runtime dependencies/launcher |
| **Executable JAR**, classifier `exec` | Boot loader, `BOOT-INF/classes`, `BOOT-INF/lib` | Deployment, operations, container images | Yes, via `java -jar` when configured properly |
| **API JAR**, classifier `api` | Only a selected subset of classes | Consumers needing a narrow API | Usually no |
| **Sources JAR**, classifier `sources` | Original `.java` sources | IDEs, lookup, and debugging | No |
| **Javadoc JAR**, classifier `javadoc` | HTML documentation from Javadoc | Documentation readers and IDEs | No |

**Note:** a classifier does not magically create different contents. You must still configure the **task or goal to produce the right contents**. Two files with different classifiers that carry the same broken contents are simply two broken artifacts.

## 2. Three types of collisions to distinguish

There are at least three conflict layers:

1. **Filesystem output path collision:** two tasks both write `build/libs/artifact-demo-1.0.0.jar` or two goals emit `target/artifact-demo-1.0.0.jar`. The later task may overwrite the file, Gradle may report overlapping outputs, or builds become non-reproducible.
2. **Publication coordinate collision:** two artifacts are published under the **same group, artifactId, version, extension, and classifier**. A repository cannot store them as distinct variants at the same coordinates; one overwrites the other or publishing fails.
3. **Artifact type confusion:** filenames do not collide, yet a pipeline grabs `-plain.jar` for production, or a library consumer pulls an executable JAR whose classes sit in `BOOT-INF/classes` instead of the classpath root.

`Classifier` helps separate names and coordinates, yet you still must:
- Ensure **every output path has exactly one owner**.
- Ensure **every publication variant has unique coordinates**.
- Select the **right artifact** at deployment and in dependency declarations.
- Inspect **actual contents** instead of guessing from `-exec`/`-api` suffixes.

Diagram:

```text
src/main/java + src/main/resources
                |
           compile/classes
                |
                +----> jar/normal artifact ----> artifact-demo-1.0.0.jar
                |
                +----> bootJar/repackage ------> artifact-demo-1.0.0-exec.jar
                |
                +----> filtered API Jar -------> artifact-demo-1.0.0-api.jar
                |
                +----> sourcesJar -------------> artifact-demo-1.0.0-sources.jar
                       (if enabled)
```

This diagram shows the resulting flow, not a guarantee that every task above is created and executed automatically in every project. Each build tool has its own lifecycle and publication setup.

## 3. How does Gradle prevent `bootJar` and `jar` from overwriting each other?

In Spring Boot Gradle plugin 3.3, when `bootJar` and `jar` are both configured, the **default convention** is typically:
- `bootJar`: empty classifier, output `artifact-demo-1.0.0.jar`.
- `jar`: classifier `plain`, output `artifact-demo-1.0.0-plain.jar`.

Reason: the two tasks **must not produce the same file**. `bootJar` is the executable archive; `jar` is the plain archive. If both defaulted to no classifier with the same base name, version, and directory, outputs would collide.

If you want the **plain JAR to keep the primary coordinates** (no classifier) so other modules can depend on it, and the executable JAR to carry classifier `exec`, update both tasks together:

```groovy
// Place in build.gradle with Java and Spring Boot Gradle plugins applied
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

tasks.named('jar') {
    archiveClassifier = ''
}
```

With `project.name = 'artifact-demo'` and `version = '1.0.0'`, expected outputs are:

```text
build/libs/artifact-demo-1.0.0.jar       # plain, primary
build/libs/artifact-demo-1.0.0-exec.jar  # executable
```

**Do not change only half the configuration and guess.** For instance, setting `jar.archiveClassifier` to empty while leaving `bootJar` empty too risks **two tasks sharing the exact same path**. If a task overrides `archiveFileName` with a custom name, that property can **bypass default classifier-based naming**; verify the final paths of both tasks.

If you do not need a plain JAR, you can avoid running `jar` or disable it deliberately:

```groovy
tasks.named('jar') {
    enabled = false
}
```

However, **do not disable it blindly** in a module that serves as a library dependency, publishes `components.java`, or runs native-image workflows that may rely on `jar`. When producing multiple artifacts, the right approach is usually **keeping both with distinct classifiers**.

## 4. Sample project: one application, one shared API class

We want to produce:
1. A plain JAR containing project classes at the archive root.
2. An executable JAR with the Spring Boot launcher and runtime dependencies.
3. An API-only JAR containing only `Greeting` in package `com.example.artifacts.api`.

Structure:

```text
artifact-demo/
├── settings.gradle / build.gradle       (Gradle option)
├── pom.xml                              (Maven option)
└── src/main/java/com/example/artifacts/
    ├── ArtifactApplication.java
    └── api/
        └── Greeting.java
```

### 4.1. `Greeting.java`

`src/main/java/com/example/artifacts/api/Greeting.java`:

```java
package com.example.artifacts.api;

public final class Greeting {

    private Greeting() {
    }

    public static String message() {
        return "classifier-ok";
    }
}
```

`Greeting` uses only standard Java and has no Spring Boot dependencies. Therefore, placing it in an API-only JAR is a safe example: consumers can call `Greeting.message()` without needing unexported application classes.

### 4.2. `ArtifactApplication.java`

`src/main/java/com/example/artifacts/ArtifactApplication.java`:

```java
package com.example.artifacts;

import com.example.artifacts.api.Greeting;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ArtifactApplication implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication.run(ArtifactApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println("artifact=" + Greeting.message());
    }
}
```

This is valid Java 17. `SpringApplication.run(...)` creates a non-web Spring Boot application when only `spring-boot-starter` is present; `CommandLineRunner` calls `Greeting.message()` and prints one line.

When running the **correct executable JAR**, the line printed by our example code is:

```text
artifact=classifier-ok
```

Spring Boot logs may also appear; do not assume stdout consists solely of that one line. Since the example has no HTTP server or long-running background task, the JVM normally exits after startup runners complete.

**Key point about classifiers:** Java code has no awareness of a JAR's classifier. Classifiers affect only **artifact creation, naming, publishing, and selection**; the exact same class can appear in a plain JAR and an executable JAR under different layouts.

## 5. Gradle Groovy DSL: building `plain`, `exec`, and `api` together

Create `settings.gradle`:

```groovy
rootProject.name = 'artifact-demo'
```

Create complete `build.gradle`:

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
}

// Specify the entry point of the executable archive.
springBoot {
    mainClass = 'com.example.artifacts.ArtifactApplication'
}

// Plain archive is the primary artifact, without classifier.
tasks.named('jar') {
    archiveClassifier = ''
}

// Executable Spring Boot archive carries the "exec" classifier.
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

// Additional artifact: contains only classes in the public API package.
tasks.register('apiJar', Jar) {
    archiveClassifier = 'api'
    from(sourceSets.main.output) {
        include 'com/example/artifacts/api/**'
    }
}

// Ensure assemble also builds the custom API artifact.
tasks.named('assemble') {
    dependsOn tasks.named('apiJar')
}
```

**This is the complete configuration for the sample project**—do not add a second `plugins` block or a second `tasks.register('apiJar')`.

Explanation:
- `tasks.named('jar')` configures the plain archive task from the Java plugin. An empty classifier gives the plain JAR a suffix-free filename.
- `tasks.named('bootJar')` configures the Spring Boot plugin task, setting classifier `exec` and preserving the configured entry point.
- `tasks.register('apiJar', Jar)` creates an independent `Jar` task with classifier `api`. `from(sourceSets.main.output)` pulls compiled classes/resources; `include` keeps only the chosen API package path.
- `assemble.dependsOn(apiJar)` wires the new artifact into `assemble`; do not assume Gradle automatically executes custom `Jar` tasks during `build`.
- All three tasks follow standard project/version/classifier naming into `build/libs` unless overridden elsewhere.

Build:

```bash
./gradlew clean assemble
```

On Windows PowerShell:

```powershell
.\gradlew.bat clean assemble
```

**Expected** outputs:

```text
build/libs/artifact-demo-1.0.0.jar
build/libs/artifact-demo-1.0.0-exec.jar
build/libs/artifact-demo-1.0.0-api.jar
```

**Do not guess filenames when a project customizes `archiveBaseName`, `archiveVersion`, `archiveFileName`, or output directories.** Always verify actual outputs after building.

Run the executable archive:

```bash
java -jar build/libs/artifact-demo-1.0.0-exec.jar
```

Application output line:

```text
artifact=classifier-ok
```

Never run `java -jar build/libs/artifact-demo-1.0.0.jar` expecting Boot JAR behavior: a plain JAR lacks the Boot launcher and nested dependencies by default.

## 6. Inspecting all three Gradle artifacts to prove they differ

List entries:

```bash
jar tf build/libs/artifact-demo-1.0.0.jar
jar tf build/libs/artifact-demo-1.0.0-exec.jar
jar tf build/libs/artifact-demo-1.0.0-api.jar
```

Key entries to look for:

| Artifact | Expected entries |
| --- | --- |
| Plain JAR | `com/example/artifacts/ArtifactApplication.class` and `com/example/artifacts/api/Greeting.class` at archive root |
| Executable JAR | `BOOT-INF/classes/com/example/artifacts/ArtifactApplication.class`, `BOOT-INF/classes/com/example/artifacts/api/Greeting.class`, `BOOT-INF/lib/...`, Boot loader |
| API-only JAR | `com/example/artifacts/api/Greeting.class`; **no** `ArtifactApplication.class`, **no** `BOOT-INF/lib` |

These are the **key expected entries**, not the full `jar tf` listing. Plain and API JARs will also contain `META-INF/MANIFEST.MF` generated by the Java `Jar` task.

Run on Linux/macOS:

```bash
jar tf build/libs/artifact-demo-1.0.0.jar |
    grep '^com/example/artifacts/'
jar tf build/libs/artifact-demo-1.0.0-exec.jar |
    grep '^BOOT-INF/'
jar tf build/libs/artifact-demo-1.0.0-api.jar |
    grep '^com/example/artifacts/api/'
```

If `-exec.jar`'s manifest is read via `unzip -p`, a Spring Boot executable JAR normally shows:
- `Main-Class`: Boot `JarLauncher`, e.g., `org.springframework.boot.loader.launch.JarLauncher` in Spring Boot 3.3.
- `Start-Class`: `com.example.artifacts.ArtifactApplication`.

**Do not confuse the Boot loader's `Main-Class` with the application's main class.** An API-only JAR needs no startup manifest. The `api` classifier does not make consuming modules automatically know which classes are safe to import: actual archive contents and dependency metadata determine usability.

## 7. Gradle Kotlin DSL equivalent

If the project uses `build.gradle.kts`, do not copy Groovy syntax verbatim. Here is the **complete Kotlin DSL file** using the same Java code from section 4:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

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
}

springBoot {
    mainClass.set("com.example.artifacts.ArtifactApplication")
}

tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}

tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("exec")
}

val apiJar by tasks.registering(Jar::class) {
    archiveClassifier.set("api")
    from(sourceSets.main.get().output) {
        include("com/example/artifacts/api/**")
    }
}

tasks.named("assemble") {
    dependsOn(apiJar)
}
```

Use `settings.gradle.kts` with:

```kotlin
rootProject.name = "artifact-demo"
```

Kotlin DSL uses property API `archiveClassifier.set(...)` and typed `tasks.named<BootJar>("bootJar")`. `apiJar` is a `TaskProvider` wired into `assemble` via `dependsOn(apiJar)`.

**Avoid mixing Groovy DSL and Kotlin DSL in the same file.** The resulting file structure and classifier-based trio of outputs match the Gradle Groovy example in section 5.

## 8. Gradle archive naming: when does a classifier stop protecting you?

Gradle normally constructs archive names conceptually as:

```text
[archiveBaseName]-[archiveAppendix]-[archiveVersion]-[archiveClassifier].[archiveExtension]
```

Empty components are omitted according to naming rules. Important properties:

| Property | Role | Common mistake |
| --- | --- | --- |
| `archiveBaseName` | Base artifact name | Two tasks share the same name and forget classifiers |
| `archiveVersion` | Version in filename | One task gets pinned to a stale version |
| `archiveClassifier` | Variant suffix | Both tasks leave it empty or both use `exec` |
| `archiveExtension` | File type, e.g., `jar`, `war` | Extension mismatches contents |
| `archiveFileName` | Overrides the **entire filename** | Two tasks both set `app.jar` despite different classifiers |
| `destinationDirectory` | Output directory | Two tasks write to the exact same full path |

**Dangerous** configuration example—do not use:

```groovy
tasks.named('jar') {
    archiveClassifier = ''
    archiveFileName = 'application.jar'
}
tasks.named('bootJar') {
    archiveClassifier = 'exec'
    archiveFileName = 'application.jar' // STILL resolves to the exact same output path!
}
```

**Why?** `archiveFileName` specifies the entire filename, so `classifier` no longer appends `-exec`. The actual output path is `destinationDirectory + archiveFileName`. If two tasks both target `build/libs/application.jar`, you must change the filename or directory.

Safe example if fixed filenames are required:

```groovy
tasks.named('jar') {
    archiveFileName = 'artifact-demo-plain.jar'
}
tasks.named('bootJar') {
    archiveFileName = 'artifact-demo-exec.jar'
}
```

This is an **alternative output-filename snippet** for a two-task project; when following section 5 without special requirements, **prefer classifiers** over hardcoded names. Hardcoded names must also account for versions and CI environments so a `1.0.1` build does not overwrite `1.0.0` in a shared directory or cache.

**Review rule:** for every archive task, compute or inspect its final `archiveFile`. If two active tasks resolve to the same file path, that is a real hazard regardless of distinct task names, classifiers, or inputs.

## 9. Maven: main artifact vs. attached artifacts

Maven distinguishes the **main artifact** (typically `groupId:artifactId:version:jar` with no classifier) from **supplemental/attached artifacts**. Attached artifacts can be `install`ed into the local repository or `deploy`ed to a remote repository alongside the main artifact when configured properly.

Example for one project:
- `com.example:artifact-demo:1.0.0:jar` → primary JAR (plain).
- `com.example:artifact-demo:1.0.0:jar:exec` → Boot executable JAR.
- `com.example:artifact-demo:1.0.0:jar:api` → API-only JAR.

Note that **merely placing a file named `artifact-demo-1.0.0-api.jar` in `target` is not enough** for it to be published under classifier `api`. A Maven plugin must **attach** the artifact with that classifier. This is the difference between "a file generated during build" and "an addressable artifact consumers can resolve."

### 9.1. What does Spring Boot Maven `repackage` do by default?

With standard Spring Boot starter parent and `spring-boot-maven-plugin` config, `repackage` takes the original JAR produced by `maven-jar-plugin` and **replaces the main artifact with the executable archive**. The pre-repackage JAR may be kept as `*.jar.original`, which must not be mistaken for a **classifier-attached artifact** installed/deployed to repositories.

If you need to **keep the plain JAR as the main artifact** and build an additional Boot JAR, configure classifier `exec` on `repackage`. When no other `exec` artifact exists as input, the plugin repackages the main JAR and attaches the resulting `-exec.jar`.

### 9.2. When an artifact with the same classifier already exists

An important detail of `spring-boot:repackage`: if you configure `<classifier>exec</classifier>` and **an artifact with classifier `exec` already exists in the build**, the plugin can pick **that `exec` artifact as the source to repackage and replace it**, rather than creating an additional Boot JAR from the main JAR.

Therefore:
- Do **not** let `maven-jar-plugin` and `spring-boot-maven-plugin` independently produce two outputs with classifier `exec` unless you intend to repackage that already-built `exec` artifact.
- Use **distinct** classifiers for plain/API and executable artifacts.
- When you truly intend to repackage a pre-built classified artifact, manage **execution ordering within the `package` phase** explicitly and inspect outputs.

In Maven, **`<attach>true</attach>`** (default in the Spring Boot plugin) controls whether the repackaged artifact is included in install/deploy. `attach=false` still creates the local file, yet **does not publish it**; avoid `attach=false` when consumers or deploy pipelines resolve the `exec` classifier from a repository.

## 10. Complete Maven POM: producing plain, executable, and API JARs

Create `pom.xml` at project root, reusing the two Java files from section 4:

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
    <artifactId>artifact-demo</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <executions>
                    <execution>
                        <id>api-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                        <configuration>
                            <classifier>api</classifier>
                            <includes>
                                <include>com/example/artifacts/api/**</include>
                            </includes>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <configuration>
                            <classifier>exec</classifier>
                            <attach>true</attach>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why does this configuration produce three artifacts?**

1. With `<packaging>jar</packaging>`, the Maven lifecycle creates the **unclassified main JAR** from `target/classes`.
2. `maven-jar-plugin` has a **separate execution** `api-jar` in `package`, with classifier `api`, including only classes matching `com/example/artifacts/api/**`. Because its classifier is distinct, it creates an **attached supplemental JAR** instead of replacing the main JAR.
3. `spring-boot-maven-plugin` targets execution ID `repackage` to **customize the execution already provided by the starter parent**, rather than adding a duplicate execution. It takes the main JAR and produces the executable `-exec.jar`; `attach=true` allows installing/deploying it alongside the main artifact.
4. Both plugins use **distinct** task classifiers: `api` does not collide with `exec`. Plugin ordering in the same phase is deliberate so output paths never overlap.

**If the project does not use the Spring Boot starter parent**, you must add versions to Maven plugins and bind the `repackage` goal/phase explicitly rather than relying on inherited executions. Importing only the `spring-boot-dependencies` BOM **does not manage plugin versions or create executions**.

Build:

```bash
./mvnw clean package
```

Expect:

```text
target/artifact-demo-1.0.0.jar
target/artifact-demo-1.0.0-exec.jar
target/artifact-demo-1.0.0-api.jar
```

When a Maven Wrapper is installed, use `./mvnw` on Linux/macOS or `.\mvnw.cmd` on Windows PowerShell. Without a Wrapper, run `mvn` with a compatible Maven/JDK.

### 10.1. Inspecting each Maven file

```bash
jar tf target/artifact-demo-1.0.0.jar
jar tf target/artifact-demo-1.0.0-api.jar
jar tf target/artifact-demo-1.0.0-exec.jar
java -jar target/artifact-demo-1.0.0-exec.jar
```

Line printed by the app:

```text
artifact=classifier-ok
```

Plain/API JARs carry no runtime dependencies, so do not expect them to self-boot like an executable JAR. If `-api.jar` lacks `Greeting.class`, check `<include>com/example/artifacts/api/**</include>` and the Java package/directory path.

### 10.2. Why Maven execution IDs matter

`spring-boot-starter-parent` already configures execution ID `repackage`. When customizing its classifier, reuse that **exact `repackage` ID**. Adding a new execution with a different ID that also runs `repackage` can invoke the goal twice during `package`; that does not give you two valid executable JARs and can cause errors or repackage the wrong artifact.

Similarly, `maven-jar-plugin` already has a default `jar` execution for `jar` packaging. When you want an **extra artifact**, define a new execution with its own classifier; do not accidentally reconfigure the default execution so that the main JAR disappears or changes role.

## 11. Using classifiers when modules depend on one another

In a multi-module repository, two distinct needs often coexist:

- A **consumer** module needs to call this module's API classes as a library.
- A **deployment** pipeline needs to run the full Spring Boot application.

A Spring Boot executable JAR stores application classes in `BOOT-INF/classes`, not at the archive root like a library JAR. Therefore **never use `-exec.jar` as a normal library dependency**. Depend on the plain JAR or appropriate API artifact, and deploy the executable JAR separately.

Maven consumer using the **main plain JAR**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
</dependency>
```

If a consumer needs **only the API JAR**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <classifier>api</classifier>
</dependency>
```

The second snippet only works when the `api` artifact has been properly attached, installed, or deployed. An API-only JAR **does not automatically carry trimmed transitive dependencies** or independent compatibility guarantees like a dedicated library module. If an API class references another class that was filtered out, consumers can still fail at runtime. In serious multi-module systems, extracting a **separate `api` module** manages dependencies and versions far more cleanly than filtering classes out of a JAR manually.

In Gradle, dependency/classifier usage must also align with repository and publication metadata. Never assume merely placing `-api.jar` in `build/libs` makes IDEs and Gradle consumers resolve it automatically.

## 12. Publishing multiple artifacts: how do Maven and Gradle differ?

### 12.1. Maven `install`/`deploy`

With the POM from section 10, run:

```bash
./mvnw clean install
```

When the build succeeds and artifacts are properly attached, the local Maven repository is expected to contain files for that version:

```text
~/.m2/repository/com/example/artifact-demo/1.0.0/
├── artifact-demo-1.0.0.pom
├── artifact-demo-1.0.0.jar
├── artifact-demo-1.0.0-exec.jar
└── artifact-demo-1.0.0-api.jar
```

Additional checksum and metadata files may appear depending on tooling and repository layout. `install` **installs to the local Maven repository**, whereas `deploy` publishes to a remote repository. Remote deployment requires `distributionManagement` and credentials via secure channels. Never publish to a live registry solely to test an exercise.

With the plain JAR as the main artifact, an unclassified `<dependency>` resolves the plain JAR. If you omit the classifier on `repackage`, the executable JAR **replaces the main artifact** and normal consumer dependencies will fail to see classes at the expected classpath layout.

### 12.2. Gradle: build file outputs are not publications

Running `./gradlew assemble` only writes files under `build/libs`. To publish, Gradle requires `maven-publish` (or an equivalent plugin) with publications declaring the desired variants.

**Supplemental snippet for the Groovy `build.gradle` in section 5**, publishing the Java component's plain artifact plus the `exec` and `api` variants:

```groovy
plugins {
    id 'maven-publish'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            artifact(tasks.named('bootJar')) {
                classifier = 'exec'
            }
            artifact(tasks.named('apiJar')) {
                classifier = 'api'
            }
        }
    }
}
```

**How to apply:** in Gradle, `plugins` must be a single block at the top of the file; when merging into section 5's `build.gradle`, **add `id 'maven-publish'` inside the existing `plugins` block**, then append **only the `publishing` block** below. Do not paste a second `plugins` block into the middle of the file.

`from components.java` publishes the primary Java component—normally the plain JAR and its dependency metadata. Both `artifact(tasks.named(...))` lines attach the additional task outputs with distinct classifiers. Never publish the same task/variant twice under colliding classifiers/extensions; if variant metadata or repository policies enforce special rules, verify before adding to CI.

Test against your **local Maven repository** using the publish-to-Maven-local task (the exact task name depends on declared publications):

```bash
./gradlew publishToMavenLocal
```

**Before publishing remotely**, verify output files, Maven coordinates, POM/Gradle module metadata contents, and artifacts in the local repo to avoid pushing non-runnable artifacts or overwriting an existing release. When using Gradle Module Metadata, variants and capabilities are modeled separately; do not treat classifiers as the entirety of Gradle's variant-aware dependency management.

### 12.3. Different filenames do not imply different coordinates

You can set `archiveFileName = 'my-custom-name.jar'` on a Gradle task, yet Maven repositories still key off the publication's **groupId/artifactId/version/classifier/extension**. Conversely, two artifacts with **different local filenames** published under identical coordinates will collide in the registry.

To prevent overwrites, check both:
1. **Filesystem output path**: files written in `build/libs` / `target`.
2. **Published identity**: coordinates and variant metadata in the repository.

## 13. Sources JAR, Javadoc JAR, and other supplemental artifacts

### 13.1. Gradle

The Java plugin supports building source and Javadoc archives via:

```groovy
java {
    withSourcesJar()
    withJavadocJar()
}
```

This is a **snippet added inside the existing `java` block** of `build.gradle`, rather than adding a second `java` block. Gradle normally generates:
- `artifact-demo-1.0.0-sources.jar`: Java source files.
- `artifact-demo-1.0.0-javadoc.jar`: HTML Javadoc documentation.

These are not Boot executable JARs. When `maven-publish` uses `components.java`, source/Javadoc variants are typically added to the publication automatically. Before publishing, inspect the artifact list so you do not manually add duplicate `sources` or `javadoc` artifacts.

### 13.2. Maven

Maven uses `maven-source-plugin` and `maven-javadoc-plugin` to attach source/Javadoc JARs. Example for sources (placed under `<build><plugins>` in `pom.xml`):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

This goal attaches an artifact with classifier `sources`; do not manually copy files to fake `-sources.jar`. If your parent already manages plugin versions, check the effective POM to avoid version conflicts or unintended overrides. Add the Javadoc plugin similarly when publishing API documentation.

**Keep classifiers semantically accurate.** Never use `sources` for an executable JAR or `javadoc` for non-Javadoc contents. IDEs and tooling ecosystems rely on standard classifiers to automatically fetch sources and documentation.

## 14. Do you really need multiple `bootJar`s or multiple entry points?

A project may contain multiple `main` classes, yet **multiple executable artifacts are rarely the cleanest answer**. If two applications have distinct dependencies, resources, and lifecycles, splitting them into **two separate Gradle/Maven application modules** is usually much easier to maintain.

When multiple Boot archives are genuinely required, each task/execution must have:
- An explicit **main class**.
- An appropriate **classpath/dependencies**, without accidentally pulling another variant's runtime classpath.
- A unique **classifier or output file path**.
- Clear **task inputs/outputs and ordering**.
- Dedicated **smoke tests** for every executable artifact.

Never create a plain Gradle `Jar` task, give it classifier `exec2`, and call it an executable JAR; a plain `Jar` task does not embed the Boot loader or nested dependencies like `BootJar`. Likewise, never copy a packaged JAR to another filename and call it a new variant if its contents and behavior are identical.

When you only need different JVM options or runtime profiles, **one executable JAR + runtime arguments/environment variables** (such as `--spring.profiles.active=...`) suffices in most cases, avoiding per-environment JARs. Every extra artifact multiplies testing, publishing, security scanning, and maintenance overhead.

## 15. Common overwrite pitfalls in Maven

| Situation | Risk | How to handle |
| --- | --- | --- |
| `spring-boot:repackage` without classifier | Replaces main JAR with executable JAR; plain remains only locally as `.original` | Set `<classifier>exec</classifier>` when preserving primary plain JAR |
| Two executions emit classifier `api` for same coordinates | Duplicate artifact/publication collision | Assign distinct classifiers or keep one execution owning `api` |
| Maven Jar plugin emits classified `exec` while Boot plugin also sets `exec` | Boot plugin may repackage the **classified `exec` source** | Do only if intentional; verify phase ordering and contents |
| Added a new `repackage` execution ID when using starter parent | Goal may execute twice | Customize the existing `repackage` execution ID |
| Hardcoded `<finalName>application</finalName>` | Different versions/builds overwrite the same local filename | Separate build directories; version artifacts in pipeline storage |
| `<attach>false</attach>` on Boot `exec` | Local file exists yet never enters install/deploy | Use `attach=true` if consumers/deploys fetch it from repo |
| Copied `-api.jar` to `target` via shell | Maven coordinates are not attached | Use plugin execution to attach the classifier properly |
| `repackage` runs before main JAR exists | Missing source JAR or repackaging stale artifact | Bind to `package` phase and verify plugin execution order |
| Aggregate `<packaging>pom</packaging>` module runs `repackage` | No application JAR to package | Enable Boot plugin only on runnable modules |

**Maven distinguishes the main artifact from attached artifacts.** Seeing three files in `target` does not prove all three were installed/deployed cleanly; verify coordinates after `install` or inspect deployment logs.

## 16. Common overwrite pitfalls in Gradle

| Situation | Risk | How to handle |
| --- | --- | --- |
| `jar` and `bootJar` both use empty classifier | Same default path; overlapping task outputs | Set `jar=''` and `bootJar='exec'`, or vice versa |
| Two tasks have different classifiers yet identical `archiveFileName` | Full filename overrides classifier naming | Change filename or directory so final output is unique |
| Same `destinationDirectory` and identical base/version/classifier | Overwrites, broken caching, unreliable task graph | Compute final `archiveFile` per task |
| Custom `apiJar` registered yet never executes | Not wired into `assemble` automatically | `assemble.dependsOn(apiJar)` or invoke the task explicitly |
| `jar.enabled=false` while publishing `components.java` | Consumers lose the plain artifact | Keep plain JAR and distinguish `exec` |
| `archiveFileName='app.jar'` across versions | Different versions collide when collected together | Keep version in target name or isolate per-version folders |
| Publish `bootJar` with same classifier as plain `jar` | Duplicate artifact coordinates in publication | Declare distinct artifact classifiers/variants |
| Manual `from(zipTree(...))` to build a "fat JAR" | Duplicate entries, broken service descriptors, invalid signatures | Prefer `bootJar` for Spring Boot or properly designed shade plugins |
| CI uses `build/libs/*.jar` wildcard | Picks plain/API/sources artifact by mistake | Reference the exact executable JAR path |
| Two Gradle subprojects copy outputs to one release folder with identical names | Files overwrite each other during aggregation | Include module name/version/classifier in path or filename |

If Gradle reports **overlapping outputs** or disables task caching, never use `mustRunAfter` to mask the collision. `mustRunAfter` only orders execution; it **does not separate two colliding output paths**. The safe principle is **each task owns a disjoint set of outputs**.

## 17. Exact artifact verification in CI/CD

### 17.1. Check all three files by exact name

After building the Gradle sample:

```bash
./gradlew clean assemble
test -s build/libs/artifact-demo-1.0.0.jar
test -s build/libs/artifact-demo-1.0.0-exec.jar
test -s build/libs/artifact-demo-1.0.0-api.jar
```

`test -s` is a POSIX shell check ensuring each file exists and is non-empty; in PowerShell use `Test-Path` and `Get-Item`. Paths above assume the sample project name/version; in real builds use the paths reported by your build tool.

### 17.2. Distinguish layouts with `jar tf`

```bash
jar tf build/libs/artifact-demo-1.0.0.jar |
    grep -Fx 'com/example/artifacts/api/Greeting.class'

jar tf build/libs/artifact-demo-1.0.0-api.jar |
    grep -Fx 'com/example/artifacts/api/Greeting.class'

jar tf build/libs/artifact-demo-1.0.0-exec.jar |
    grep -Fx 'BOOT-INF/classes/com/example/artifacts/ArtifactApplication.class'

jar tf build/libs/artifact-demo-1.0.0-exec.jar |
    grep -E '^BOOT-INF/lib/.*[.]jar$'
```

Also verify the **absence** of entries that do not belong in a variant. For example, the API JAR must not contain `com/example/artifacts/ArtifactApplication.class`. File searches do not prove full functional safety; also verify main class, dependencies, and runtime execution.

### 17.3. Smoke test the executable JAR

```bash
java -jar build/libs/artifact-demo-1.0.0-exec.jar
```

Application output line:

```text
artifact=classifier-ok
```

If running the plain or API JAR via `java -jar` fails with a manifest/main/dependency error, that simply confirms **those artifacts are not designed to be executed standalone**, not that project code is broken.

### 17.4. PowerShell check without misleading wildcards

```powershell
$files = @(
    '.\build\libs\artifact-demo-1.0.0.jar',
    '.\build\libs\artifact-demo-1.0.0-exec.jar',
    '.\build\libs\artifact-demo-1.0.0-api.jar'
)

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Missing artifact: $file"
    }
    if ((Get-Item -LiteralPath $file).Length -eq 0) {
        throw "Empty artifact: $file"
    }
}
Write-Output 'Three artifacts found'
```

This snippet checks only filenames, existence, and non-zero size; it **does not** validate contents. Pair it with `jar tf` and running `-exec.jar`. For Maven, replace `build/libs` with `target`. In pipelines, record checksums and bind each deployment stage to the exact artifact rather than taking the first file matching `*.jar`.

## 18. Reproducible builds, caching, and output versioning

Producing three distinct artifacts is not enough if bytes vary unpredictably at the same version or releases are silently overwritten.

- **Version is release identity**, not just a filename. Never rebuild different code and overwrite the same release coordinates in an immutable repository.
- **Classifiers distinguish purpose**, not versions: `exec` and `api` at version `1.0.0` must never ship mismatched source states.
- **Gradle task outputs must not overlap** so up-to-date checks, build cache, and parallel execution remain sound.
- **Maven attached artifacts must carry exact coordinates** and deterministic plugin ordering rather than post-build shell renames.
- **Verify archive reproducibility** when byte-for-byte deterministic builds are required; timestamps, file order, filtering, and build metadata all affect checksums.

To compare local outputs with SHA-256:

```bash
sha256sum build/libs/artifact-demo-1.0.0.jar
sha256sum build/libs/artifact-demo-1.0.0-exec.jar
sha256sum build/libs/artifact-demo-1.0.0-api.jar
```

On PowerShell use `Get-FileHash -Algorithm SHA256`. The three artifacts **should have distinct hashes** because their contents differ; the same artifact across two reproducible builds can match hashes once all inputs/settings are deterministic. Checksums verify bytes, not runtime correctness or trusted provenance.

Never fix overwritten files by adding `clean` to every build: `clean` wipes stale outputs but does not fix **two tasks writing to the same file**. Fix classifier, path, and task ownership first.

## 19. Packaging review checklist when adding a new artifact

When asked to produce an extra `-api.jar`, `-sources.jar`, or another executable, walk through these steps:

1. **Identify consumers:** deployment, dependent modules, IDEs, or distribution packages.
2. **Define required contents:** app classes, runtime dependencies, docs, or an API subset.
3. **Pick the right task/goal:** Gradle `bootJar`/`jar`/custom `Jar`, Maven `spring-boot:repackage`/`maven-jar-plugin`/source plugin.
4. **Pick a unique classifier:** `exec`, `api`, `sources`, etc., matching true semantics.
5. **Compute actual output paths:** base name, version, classifier, extension, directory, and any full filename overrides.
6. **Verify main vs. attached/publication identities:** what is published under which coordinates?
7. **Prevent two producers from owning one path** or publishing identical coordinates.
8. **Wire tasks into the lifecycle deliberately:** `assemble`/`build` in Gradle, `package`/`install` in Maven.
9. **Run a clean build once for verification**, without relying on cached/stale files in output directories.
10. **Inspect each file with `jar tf`**, confirming layout, classes, resources, and dependencies.
11. **Run `java -jar` on executable variants**; add consumer compilation/runtime tests for API JARs if applicable.
12. **Verify local publication before remote**, checking files, coordinates, and metadata.
13. **Update pipeline artifact selection** to use explicit paths instead of ambiguous `*.jar` globs.

### End-of-lesson checklist

- [ ] Plain JAR and Boot executable JAR have **distinct output paths**.
- [ ] Every classifier is chosen intentionally, with no collisions on publication coordinates.
- [ ] Gradle `archiveFileName`/`destinationDirectory` does not defeat classifier uniqueness.
- [ ] Maven `repackage` sets classifier `exec` when **preserving the main JAR** for library consumers.
- [ ] Maven `maven-jar-plugin` uses a dedicated execution and classifier for attached API JARs.
- [ ] No duplicate `repackage` execution was accidentally created when inheriting Spring Boot starter parent.
- [ ] API artifact contains only the intended public API and misses no referenced classes.
- [ ] `sources`/`javadoc` classifiers are used strictly for their standard content types.
- [ ] Build lifecycle actually invokes all tasks/goals producing the expected artifacts.
- [ ] Verified `jar tf`, Boot manifest, `BOOT-INF/lib`, and ran the exact `-exec.jar`.
- [ ] CI/CD selects artifacts by explicit path and tracks versions/checksums.
- [ ] Verified install/deploy/publish identities, not merely file presence in `build/libs`/`target`.

**Remember:** *Classifiers handle naming and variant identity; tasks/goals determine contents; output paths determine on-disk overwrites; publication coordinates determine repository collisions.* With Spring Boot, **keeping the plain JAR as the main artifact and giving the executable JAR classifier `exec`** is practical when one module serves as both library and deployable app. Always verify via **build → list files → `jar tf` → run executable → test resolve/publish**, rather than trusting JAR names alone.

## References

- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Publishing your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html)
- [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven JAR Plugin — Creating an Additional Attached JAR Artifact](https://maven.apache.org/plugins/maven-jar-plugin/examples/attached-jar.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Jar task and archive naming](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)