# Handling Duplicate Resources and Archive Inclusion Rules

When Maven or Gradle builds a Spring Boot application, files from `src/main/resources` are placed on the **application classpath** and can then be packaged inside the executable JAR/WAR. If multiple sources produce the same destination path — for instance, two files both become `config/messages.properties` — the outcome can be a **failed build, one file silently skipped, an overwrite, or an archive containing duplicate entries**. You must identify which stage causes the collision before choosing how to resolve it.

This lesson focuses on **rules for including resources in archives**, handling **duplicate names/paths**, configuring **include/exclude**, differences between **Gradle and Maven**, distinguishing **duplicate entries in a single archive from same-named resources across different dependency JARs**, and verifying the actual packaged files. Examples use Java 17, Gradle 8.x, and Maven 3.x; when the Spring Boot plugin appears, examples illustrate the 3.3.x line. Build-tool syntax must always be placed in the project's matching DSL or POM.

## 1. What Is a Resource, and How Are "Duplicates" Determined?

In Java, a **resource** is runtime data such as YAML, properties, JSON, templates, HTML, CSS, images, sample files, and metadata. Build tools do not compile these files into `.class` files like Java sources; normally they are **copied or processed** into output directories.

Typical structure:

```text
resource-demo/
├── build.gradle or pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   └── ResourceDemoApplication.java
    │   └── resources/
    │       ├── application.yml
    │       ├── demo/message.txt
    │       ├── static/logo.svg
    │       └── templates/page.html
    └── test/
        ├── java/com/example/demo/
        │   └── ResourceDemoApplicationTest.java
        └── resources/
            └── demo/message.txt
```

The **relative path on the classpath** is the primary criterion for detecting collisions, not the bare filename alone. Two files `images/header.svg` and `icons/header.svg` share a basename yet **do not** collide on the classpath. Conversely, files in two different roots sharing the path `demo/message.txt` will collide **if copied into the same output root**.

Example:

```text
src/main/resources/demo/message.txt       -> demo/message.txt
src/shared/resources/demo/message.txt     -> demo/message.txt  (DUPLICATE target path)

src/main/resources/icons/header.svg       -> icons/header.svg
src/shared/resources/images/header.svg    -> images/header.svg (NO collision)
```

These paths are normalized to archive layout using `/` separators. Do not rely on case differences across operating systems: `Logo.svg` and `logo.svg` can behave differently on case-insensitive filesystems or when extracted on another OS. Use consistent naming that avoids post-normalization collisions.

Collision categories:

| Situation | Example | Stage to inspect |
| --- | --- | --- |
| Two source resource roots produce the same path | `main/resources/demo/x.txt` and `shared/resources/demo/x.txt` | Gradle `processResources` / Maven `process-resources` |
| An archive copy rule adds a file matching an existing entry | `bootJar.from(...)` recreates `BOOT-INF/classes/demo/x.txt` | Archive packaging task |
| Two dependency JARs both contain `META-INF/services/...` | `library-a.jar` and `library-b.jar` | Classpath/runtime or *shaded* JAR step, if any |
| Main resource and test resource share a path | `src/main/resources/demo/x.txt` and `src/test/resources/demo/x.txt` | Test classpath; not necessarily a production archive collision |
| A config file inside the JAR and one outside the app | Internal `application.yml` and external config folder | Spring Boot config precedence, not an archive duplicate entry |

**Key point:** having the "same name" across two **different** dependency JARs does not automatically create a duplicate entry in the outer JAR when using Spring Boot nested JARs. Nor does it mean those files are automatically merged.

## 2. Which Steps Do Resources Pass Through Before Entering a JAR/WAR?

Overview of a Java/Spring Boot project:

```text
src/main/java  ------ compileJava / compile -------> .class
                                                    \
src/main/resources -- processResources -------------> main output
                                                      \
                                                       +--> jar/bootJar/bootWar
                                                      /     \
runtime dependencies --------------------------------+       +--> deployable artifact

src/test/java + src/test/resources
            ---- compileTest / processTestResources --> test output
                                                         |
                                                         +--> test (not packaged into prod JAR by default)
```

| Artifact component | Common Gradle | Common Maven | Inside Spring Boot executable JAR |
| --- | --- | --- | --- |
| Application classes | `build/classes/java/main` | `target/classes` | `BOOT-INF/classes/.../*.class` |
| Main resources | `build/resources/main` | `target/classes` | `BOOT-INF/classes/...` |
| Runtime dependencies | `runtimeClasspath` configuration | Compile/runtime dependencies | `BOOT-INF/lib/*.jar` |
| Test classes/resources | `build/classes/java/test` and `build/resources/test` | `target/test-classes` | **Not** packaged by default |

In an executable WAR, application classes usually reside in `WEB-INF/classes` and dependencies in `WEB-INF/lib` / `WEB-INF/lib-provided` depending on deployment setup. By contrast, a plain JAR built by `jar` or `maven-jar-plugin` places classes and resources at the **JAR root**, not under `BOOT-INF/classes`.

**Inclusion rules apply in layers:**

1. The build tool determines **source roots** (which roots are main vs. test resources).
2. `include`/`exclude` and copy/filter steps decide which resources reach the output.
3. **Destination path**, renaming, and duplicate-strategy rules decide how identical paths are handled.
4. The archive task gathers class/resource outputs and runtime dependencies for packaging.
5. The Spring Boot launcher resolves resources from the **runtime classpath**; libraries in nested JARs keep their own internal paths.

Because multiple layers exist, identify where a file actually lives: **source**, **processed resources/classes**, **main archive**, **dependency JAR**, or **external config**.

## 3. Gradle: Managing Resources in `processResources`

The Gradle Java plugin creates the `main` source set with `src/main/resources` by convention. The `processResources` task (of type `ProcessResources`) uses `CopySpec` rules to copy and optionally transform resources into `build/resources/main`.

### 3.1. Adding a Resource Root Intentionally

Example `build.gradle` (Groovy DSL):

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

sourceSets {
    main {
        resources {
            srcDir 'src/shared/resources'
        }
    }
}

tasks.named('processResources') {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    exclude '**/*.bak', 'draft/**'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **complete build-file configuration**, paired with the Java main class created in section 6. `srcDir` appends `src/shared/resources` to the main source set while `src/main/resources` remains the default root. `exclude` in `processResources` drops backup files and the `draft` directory **during resource processing**. Two files from different roots producing the **same destination path** will be caught because `duplicatesStrategy = DuplicatesStrategy.FAIL` is set.

**Do not accidentally overwrite `sourceSets.main.resources.srcDirs`** when you only want to add a directory. `srcDir` appends a source; reassigning the entire list drops `src/main/resources` unless you list it explicitly.

### 3.2. `DuplicatesStrategy` Values

Gradle supports these strategies for copy and archive operations:

| Value | On duplicate destination path | When to use |
| --- | --- | --- |
| `FAIL` | Throws `DuplicateFileCopyingException`, failing the task | When duplicates indicate a data/build bug (fail fast) |
| `EXCLUDE` | Keeps the first copied file and ignores subsequent ones | When source order is strictly controlled and "first wins" is intentional |
| `INCLUDE` | Allows duplicates; ZIP/JAR may hold multiple entries with the same path | Only when format and consumers handle duplicate entries reliably |
| `WARN` | Same as `INCLUDE` while logging warnings | Useful for observation, not a long-term production fix |
| `INHERIT` | Inherits from parent copy spec | Default on many specs/tasks, not a semantic resolution policy |

Configuration example:

```groovy
tasks.named('processResources') {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
```

Or selecting `EXCLUDE`:

```groovy
tasks.named('processResources') {
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
}
```

Understand clearly: **`EXCLUDE` does not "merge two files into one"**. It discards later files and keeps whichever was processed first; order can shift when source or copy-spec definitions change. Avoid using `EXCLUDE` to mask critical collisions like two differing `application.yml` files. `FAIL` helps you fix the root cause at the source roots. With `INCLUDE`/`WARN`, a ZIP archive can contain multiple entries with identical names and readers may pick arbitrarily; runtime correctness **is not guaranteed**.

### 3.3. Fixing Collisions at the Source

Suppose:

```text
src/main/resources/demo/message.txt       contains: from-main
src/shared/resources/demo/message.txt     contains: from-shared
```

After adding both roots with `FAIL`, `./gradlew processResources` will catch the duplicate `demo/message.txt` path (provided both files are actually task inputs). Valid fixes include:

- Pick **one authoritative source file** and remove the other from the source set.
- Rename the shared path to `demo/shared-message.txt` so both serve distinct purposes.
- Only when precedence is an explicit requirement, define explicit copy/rename/filter path rules and test the result.

Never "fix" a collision by running builds repeatedly to see which file happens to win. Differences in source ordering or OS filesystems can hide the problem.

### 3.4. `include` and `exclude` Rules

Example keeping only resources from the `reports` folder:

```groovy
tasks.named('processResources') {
    include 'reports/**'
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
```

**Caution:** using `include` can drop files outside `reports/**` (including `application.yml`, templates, and static assets). It acts as a **broad allowlist**, unsuitable when the app needs other resources.

A safer pattern keeps defaults and **excludes specific unwanted paths**:

```groovy
tasks.named('processResources') {
    exclude 'draft/**', '**/*.bak', '**/*.tmp'
}
```

CopySpec patterns match paths **relative to the resource root**; do not write `src/main/resources/draft/**` when trying to exclude `draft/**`. Verify against actual outputs because an overly broad pattern can strip runtime assets.

**Do not confuse `.gitignore` with build rules.** `.gitignore` tells Git which files not to track; it does not prevent packaging. A file sitting inside a resource root can still be copied and packaged even if listed in `.gitignore`.

## 4. Gradle: Distinguishing `processResources` from `bootJar`

When combining Gradle's Java and Spring Boot plugins:
- `processResources` produces the **resource output of the `main` source set**.
- `bootJar` assembles main classes/resources and runtime libraries into an executable Spring Boot JAR.
- `jar` creates a **plain JAR** with its own rules and artifact.
- `bootWar` does the equivalent for WARs when the `war` plugin is applied.

Example configuring the **archive task** to exclude backup files from the executable JAR:

```groovy
tasks.named('bootJar') {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    exclude '**/*.bak'
}
```

`duplicatesStrategy` here governs **duplicate paths added while `bootJar` writes entries**; it **cannot undo** duplicates already dropped or overwritten during `processResources`. Conversely, if a file was excluded during `processResources`, `bootJar` will not normally receive it from main resource output.

**Prefer filtering at source/`processResources`** for application resources: that keeps `bootRun` (which reads output directories) consistent with `bootJar`. Reserve archive-level exclusions for genuinely packaging-specific needs, and verify the resulting archive. Putting rules only on `tasks.named('jar')` does not apply them to `bootJar`; they are separate tasks.

If you add files directly via `from(...)` inside `bootJar`, those resources **bypass `processResources`**. Check the target archive path and duplicate strategy on the archive task itself. Avoid feeding the same file through both paths (main resources and `bootJar.from`), as that invites duplicates.

## 5. Maven: Controlling Resources Before Building the JAR

Maven copies main resources into `target/classes` via the Maven Resources Plugin, normally during the `process-resources` phase. Test files pass through `process-test-resources` into `target/test-classes`. Resource directories are configured in `<build><resources>`, with path filtering via `<includes>` and `<excludes>`.

### 5.1. Example Excluding Specific Files in Maven

Place the following **inside `<project>` in `pom.xml`**:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>draft/**</exclude>
                <exclude>**/*.bak</exclude>
                <exclude>**/*.tmp</exclude>
            </excludes>
        </resource>
    </resources>
</build>
```

When defining `<resources>` explicitly, retain `src/main/resources` if the project needs the default root. If a second resource root exists, add another `<resource>` block for it.

Example using `include` intentionally:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <includes>
            <include>config/*.yml</include>
            <include>reports/**</include>
        </includes>
        <excludes>
            <exclude>reports/internal/**</exclude>
        </excludes>
    </resource>
</resources>
```

This snippet **replaces the `<resources>` section**, rather than sitting beside a duplicate resource block unless needed. Only paths matched by `include` and not rejected by `exclude` are copied by this resource entry. Files like `static/index.html` will be omitted unless matched; audit all runtime assets before using an allowlist.

### 5.2. When Two Resource Roots Target the Same Destination

Example of a **collision-prone configuration**:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
    </resource>
    <resource>
        <directory>src/shared/resources</directory>
    </resource>
</resources>
```

If both roots contain `demo/message.txt`, both write to `target/classes/demo/message.txt`. Maven Resources Plugin has an `overwrite` parameter controlling overwriting existing output files, yet **`overwrite=true/false` is not equivalent to Gradle's `DuplicatesStrategy.FAIL/EXCLUDE/INCLUDE`**. Which copy survives can depend on plugin version, processing order, timestamps, and existing target files; do not rely on implicit overwrite side effects.

More reliable solutions:
1. Maintain **one authoritative source** per classpath path.
2. Adjust source paths or use `<targetPath>` deliberately to give each resource group its own prefix.
3. If data must be merged, run a **deterministic resource-generation step** before `process-resources` and verify its output.

Example keeping both `demo/message.txt` files by placing shared resources under a `shared` prefix:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
    </resource>
    <resource>
        <directory>src/shared/resources</directory>
        <targetPath>shared</targetPath>
    </resource>
</resources>
```

Expected output layout:

```text
target/classes/demo/message.txt
target/classes/shared/demo/message.txt
```

`targetPath` changes **the resource's classpath and archive path**, so application code must look up the new path (`shared/demo/message.txt`). In multi-module setups, make sure a `targetPath` does not accidentally collide with an existing folder in main resources.

### 5.3. Maven Archive-Level Include/Exclude

Maven normally builds the plain JAR using `maven-jar-plugin` from `target/classes`. You can exclude files **at the JAR packaging step only** via this plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <configuration>
                <excludes>
                    <exclude>demo/local-only.txt</exclude>
                </excludes>
            </configuration>
        </plugin>
    </plugins>
</build>
```

This is a **plugin configuration snippet** to merge into your existing `<build><plugins>`; do not create a second `<build>` element. `maven-jar-plugin` evaluates paths **relative to `target/classes`**, not `src/main/resources/demo/local-only.txt`. When `spring-boot-maven-plugin` subsequently runs `repackage` on that JAR, the excluded file is absent from the input JAR and therefore also omitted from `BOOT-INF/classes` in the executable JAR.

Note that `spring-boot-maven-plugin`'s `<excludes>` filters **dependency artifacts** (by group/artifact), not arbitrary resource paths. To drop individual resources, configure `<resources>` or the archive plugin appropriately.

## 6. Runnable Java 17 Example: Verifying the Resource Actually Read by the App

The Gradle `build.gradle` in section 3.1 includes `spring-boot-starter`. Create two Java files in package `com.example.demo`.

**File `src/main/java/com/example/demo/ResourceDemoApplication.java`:**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDemoApplication.class, args);
    }
}
```

**File `src/main/java/com/example/demo/ResourceProbe.java`:**

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceProbe {

    private ResourceProbe() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream in = ResourceProbe.class
                .getClassLoader()
                .getResourceAsStream("demo/message.txt")) {
            if (in == null) {
                throw new IOException("Missing demo/message.txt");
            }
            String value = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println("resource=" + value.strip());
        }
    }
}
```

`src/main/resources/demo/message.txt` contains **exactly one line**:

```text
from-main
```

When `src/shared/resources/demo/message.txt` also contains **one line `from-shared`**, running:

```bash
./gradlew clean processResources
```

detects the duplicate because `duplicatesStrategy = DuplicatesStrategy.FAIL` was set in section 3.1. You can **move/rename the shared file to** `src/shared/resources/demo/shared-message.txt` so the two files have distinct paths.

After resolving the collision, run:

```bash
./gradlew clean classes
java -cp "build/classes/java/main:build/resources/main" com.example.demo.ResourceProbe
```

The stdout **printed by `ResourceProbe`** (excluding Gradle/JVM output) is:

```text
resource=from-main
```

On Windows PowerShell, run:

```powershell
.\gradlew.bat clean classes
java -cp "build/classes/java/main;build/resources/main" com.example.demo.ResourceProbe
```

The classpath separator is `:` on Linux/macOS and `;` on Windows. `java -cp` uses the project's compiled classes and resource outputs directly without needing to build the Boot JAR first. `ResourceProbe` is plain Java using the classpath API. It uses `getResourceAsStream` instead of `new File("src/main/resources/demo/message.txt")` because packaged resources live inside the JAR.

Because the project now contains two `main` classes, specify the entry point for the Boot archive in `build.gradle`:

```groovy
springBoot {
    mainClass = 'com.example.demo.ResourceDemoApplication'
}
```

Then run:

```bash
./gradlew clean bootJar
```

With consistent `group`/`version` and root project name (e.g., `rootProject.name = 'resource-demo'`), the typical artifact is `build/libs/resource-demo-1.0.0.jar`. Exact paths can vary with archive settings; check `build/libs`.

**Why run `clean` in this exercise?** To prevent stale outputs from masking results after renaming or deleting source resources. Routine builds do not need `clean` every time; in duplicate-testing exercises, it guarantees reproducible results.

## 7. Rules for Inspecting Files Inside a Spring Boot Archive

### 7.1. Common Archive Layout

For a Spring Boot executable JAR:

```text
resource-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/demo/ResourceDemoApplication.class
│   │   ├── demo/message.txt
│   │   ├── application.yml
│   │   ├── static/
│   │   └── templates/
│   └── lib/
│       ├── spring-boot-*.jar
│       └── ...
└── org/springframework/boot/loader/...
```

This is an **illustrative diagram**, not a strict list required in every project. Spring Boot 3.x executable JARs place application classes/resources under `BOOT-INF/classes` and dependency JARs under `BOOT-INF/lib`. Plain JARs have a different layout; executable WARs typically use `WEB-INF/classes` and `WEB-INF/lib`.

Use the JDK to list entries:

```bash
jar tf build/libs/resource-demo-1.0.0.jar
```

Look for paths:

```text
BOOT-INF/classes/demo/message.txt
BOOT-INF/classes/demo/shared-message.txt
BOOT-INF/classes/com/example/demo/ResourceDemoApplication.class
```

`jar tf` **lists only entry names**, not file contents. If `unzip` is available, print contents directly:

```bash
unzip -p build/libs/resource-demo-1.0.0.jar BOOT-INF/classes/demo/message.txt
```

Expected contents:

```text
from-main
```

On Windows, use 7-Zip/a ZIP viewer or extract with `jar xf` into a **separate temporary directory** and inspect `BOOT-INF/classes/demo/message.txt`. Never edit files inside a built archive manually; fix the source and rebuild.

### 7.2. Checking for Duplicate Entries Within the Same JAR

`jar tf` can print the same path multiple times if the archive contains duplicate ZIP entries. You can detect this by listing entries and counting occurrences of each path (some ZIP tools have options to highlight duplicates). Having no duplicates in the **outer JAR** listing **does not** rule out identical resource paths across multiple **nested** dependency JARs.

Example:

```text
BOOT-INF/lib/library-a.jar -> META-INF/services/com.example.Plugin
BOOT-INF/lib/library-b.jar -> META-INF/services/com.example.Plugin
```

These two files share a path **inside two separate nested JARs**, so they do not create duplicate `BOOT-INF/classes/META-INF/services/...` entries in the outer JAR. Both can be loaded together by `ServiceLoader` when supported by the classpath/runtime classloader. Do not strip one blindly just because the paths look "duplicate".

### 7.3. Why Not Resolve Every Collision with `EXCLUDE`?

An exclusion rule in `processResources` or an archive task can:
- accidentally strip `application.yml`, `META-INF/spring/...AutoConfiguration.imports`, or vital metadata;
- drop templates, CSS, or images needed at runtime;
- mask changes coming from an upgraded dependency;
- make `bootRun` (reading resource outputs) diverge from `java -jar` (reading the packaged artifact);
- leave behind the wrong version of a resource if copy order shifts.

In particular, `META-INF/services/*` metadata is **intentionally present across multiple dependency JARs**. Merging service descriptors only arises when **flattening/shading** JARs into a single archive, which requires a dedicated merge strategy and testing. A standard Spring Boot nested executable JAR **is not a shaded JAR**.

## 8. Test Resources Colliding with Main Resources

Example:

```text
src/main/resources/demo/message.txt  -> "from-main"
src/test/resources/demo/message.txt  -> "from-test"
```

This can be **intentional**: tests want to load a fixture instead of the default resource. Maven and Gradle compile **main outputs** and **test outputs** to separate directories, so sharing a classpath-relative path between main and test does not cause `bootJar` to fail with a duplicate error.

However, when the test runtime classpath contains both test and main outputs, which copy `getResourceAsStream("demo/message.txt")` returns can depend on classpath ordering. Do not assume "test always wins" across every build tool, IDE, or custom setup.

When deterministic test loading matters:
- Use an explicit fixture path like `fixtures/message-test.txt` instead of shadowing a main path.
- Or pass the explicit path in test code/configuration and assert on the loaded value.
- For Spring Boot profiles, use `application-test.yml` and activate the `test` profile explicitly; **profile selection** is different from **classpath resource order**.

`src/test/resources` does not enter the executable production JAR **by default**, unless custom copy/archive rules or misconfigured source sets pull test outputs into main.

## 9. Distinguishing Resource Collisions from Spring Boot Config Precedence

An easily misunderstood case:

```text
BOOT-INF/classes/application.yml        (packaged config)
./config/application.yml                 (external config outside JAR)
```

These **are not duplicate entries inside the archive**. Spring Boot has its own **property source and config data precedence rules**, covering profiles, external config locations, environment variables, system properties, and command-line arguments. An external value can override a packaged value per Spring Boot rules, completely unrelated to Gradle's `DuplicatesStrategy`.

By contrast, if two main resource roots both produce **`application.yml`** and the copy step resolves it ambiguously, that is a **build-time path duplicate**. Fix it in source/build configuration before debating runtime property precedence.

A clean strategy:
- Keep **default, secret-free configuration** in `src/main/resources/application.yml`.
- Supply secrets and environment-specific settings via secret managers, environment variables, or external config outside the artifact.
- Never maintain multiple `application.yml` files across different resource roots relying on copy order to pick a "winner".
- Test effective runtime values in the target environment, since build-time filtering and runtime resolution are separate stages.

## 10. Filtering and Generated Resources: Avoiding Unclear Collisions

### 10.1. Gradle `expand` While Keeping Unfiltered Files Intact

Gradle can substitute placeholders in text resources during `processResources`:

```groovy
tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(buildVersion: project.version)
    }
}
```

File `src/main/resources/build-info.properties`:

```properties
build.version=${buildVersion}
```

After processing with `project.version = '1.0.0'`, expected output:

```properties
build.version=1.0.0
```

This is **file-content transformation**, not a duplicate-path handler. If another task also generates `build-info.properties` into the same output root, establish a single authoritative owner. Never apply `expand` to binary files, as PNG/PDF/JAR files can be corrupted or misparsed.

### 10.2. Maven Filtering

Maven Resources Plugin supports `<filtering>true</filtering>` with variables from the POM, properties, and filter files. Apply it only to **text files needing interpolation**, avoiding images and binaries.

Example splitting two groups under `<build><resources>`:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <excludes>
            <exclude>build-info.properties</exclude>
        </excludes>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
        <includes>
            <include>build-info.properties</include>
        </includes>
    </resource>
</resources>
```

The same source directory appears **twice** with **disjoint** patterns so `build-info.properties` is copied only by the filtered group. This cleanly isolates a single filtered text file. If both entries matched `build-info.properties`, you would target the same output path twice and depend on overwrite behavior.

Maven also provides `<nonFilteredFileExtensions>` to protect binary extensions; accidentally filtering images, PDFs, or JARs corrupts them. Inspect the output after `process-resources` to verify values were substituted cleanly.

### 10.3. Generated Resources Need Clear Ownership and Task Ordering

When a plugin/task generates `META-INF/build-info.properties` while a static source file sits at that same path, you have the same collision as two overlapping roots. Decide **who owns the final file** rather than committing a source file and overwriting it during builds.

In Gradle, when a task generates resources consumed by `processResources`, connect the tasks via a provider/task dependency pointing to a dedicated output directory; never write generated files directly into `src/main/resources` during a build. In Maven, bind generation plugins to a phase before `process-resources` or register their output root properly, checking plugin execution order. Do not rely on manually deleting outputs between builds.

Conceptual safe workflow:

```text
generateMetadata -> generated/resources/META-INF/build-info.properties
                                     |
                                     v
                      processResources (single authoritative source)
                                     |
                                     v
                         build/resources/main
                                     |
                                     v
                               bootJar/bootWar
```

Generated resources and human-maintained files need **clear paths and ownership** so builds stay reproducible.

## 11. Archive Inclusion Rules: What Belongs and What Does Not

A deployable application artifact typically needs:

| File / data type | Include in artifact? | Reason |
| --- | --- | --- |
| `.class` from `src/main/java` | Yes | Executable program code |
| Default `application.yml` | Yes, if needed and free of secrets | Baseline configuration |
| `static/**`, `templates/**` | Yes, when used by the app | Web assets and templates |
| Valid `META-INF/**` | Yes, when needed by features/libraries | Metadata, SPI, auto-configuration |
| Runtime dependencies | Yes, per Spring Boot layout | Libraries needed to run |
| `src/test/java`, `src/test/resources` | No, by default | Testing only |
| `*.bak` backups, drafts, unused internal docs | Usually no | Artifact bloat and unnecessary exposure |
| Real passwords, private keys, tokens in resources | No | Never embed secrets in archives |
| Runtime-scoped drivers | Yes, when required | Missing them causes `ClassNotFoundException` |
| Environment-specific deployment configs | Usually managed externally | Switch values without rebuilding |

Do not exclude `META-INF/**` wholesale thinking it is "extra metadata". Files there are critical for Java `ServiceLoader`, logging, Spring Boot auto-configuration, and runtime tooling. Likewise, do not strip `BOOT-INF/lib` to shrink an executable JAR expecting `java -jar` to download dependencies automatically.

**The classpath of a Boot executable JAR is not just `BOOT-INF/classes`**; nested dependencies in `BOOT-INF/lib/*.jar` are loaded by the Boot launcher as well. Inspect resources in both **application outputs** and **dependency libraries** when diagnosing unexpected runtime behavior.

## 12. Workflow for Diagnosing Duplicate or Missing Resources

A diagnostic workflow for both Gradle and Maven:

1. **Identify the classpath path the code requests**, e.g., `demo/message.txt` (not the source filesystem path).
2. **List all main/test/generated source roots** wired to the task and see how many files map to that path.
3. **Check `include`/`exclude`/rename/`targetPath`/filtering/`duplicatesStrategy` rules** on the exact task or resource entry.
4. **Run one clean build to diagnose**, avoiding confusion from stale outputs.
5. **Inspect pre-packaging outputs**: `build/resources/main` or `target/classes`.
6. **Inspect the actual deployed artifact**: `jar tf`, files inside `BOOT-INF/classes` or `WEB-INF/classes`; distinguish plain JARs from Boot JARs.
7. **If the resource comes from a dependency**, inspect the dependency tree and the nested JAR contents; do not look only inside `BOOT-INF/classes`.
8. **Run the real artifact** in a representative environment and check the loaded resource or feature behavior.
9. **Add a regression test** for critical paths/values so future build changes cannot reintroduce collisions.

Reference Gradle commands:

```bash
./gradlew clean processResources
./gradlew bootJar
./gradlew dependencies --configuration runtimeClasspath
jar tf build/libs/resource-demo-1.0.0.jar
```

Equivalent Maven commands:

```bash
./mvnw clean process-resources
./mvnw package
./mvnw dependency:tree
jar tf target/resource-demo-1.0.0.jar
```

If no wrapper exists, run `gradle` or `mvn` with a compatible installation. In Gradle, the output JAR name depends on `project.name`, `version`, and archive settings; in Maven, on `artifactId`, `version`, and packaging. **Do not copy example filenames verbatim if your project uses different coordinates.**

Common error categories:

| Error or symptom | Common cause | Where to fix |
| --- | --- | --- |
| Gradle fails with `Entry ... is a duplicate` | Two sources/copy specs share a path without a permissive strategy | Check `processResources` or `bootJar`; keep `FAIL` and fix the sources |
| `getResourceAsStream` returns `null` | File excluded, wrong classpath path, or never copied | Check main/test outputs and the archive |
| Tests read a different file than production | Main/test share a resource path with different classpath ordering | Give fixtures distinct paths and verify the classloader |
| Deleted source file still appears in the JAR | Stale build output or custom copy/generator task recreates it | Run `clean` to check; locate the real task/source |
| Application resource gets "overwritten" | Two Maven resource roots share the same target path | Use one source or a distinct `targetPath` |
| JAR contains two entries with the exact same name | CopySpec/`INCLUDE` or archive injection duplicated a path | Remove or rename one path, set `FAIL`, and recheck |
| Resource not found in `BOOT-INF/classes` | Resource lives in a dependency JAR rather than the app | Inspect `BOOT-INF/lib` and the classpath |
| `application.yml` holds unexpected values | Runtime property precedence or build-time filtering | Separate Spring config precedence from copy-stage changes |
| Static assets return 404 after build | `include` is too narrow or `exclude` is too broad | Inspect archive entries and fix resource patterns |
| Image/PDF corrupted after packaging | Text filter applied to binary files | Split filtering and disable filtering for binaries |
| Spring Boot loses auto-configuration or SPI | Excluded `META-INF/**` accidentally | Restore metadata and verify library entries |
| Deployed JAR differs from the JAR just inspected | Plain JAR vs. executable JAR or different classifier | Verify the exact artifact path used in CI/CD |

## 13. Checklist Before Finalizing Resource/Packaging Configuration

- [ ] Every **critical** resource has a **unique classpath path** and a single clear owner.
- [ ] Main, test, and generated resources are separated so test fixtures never enter production archives.
- [ ] In Gradle, you know which **task** `duplicatesStrategy` applies to; prefer `FAIL` to catch collisions, using `EXCLUDE` only for intentional first-wins setups.
- [ ] In Maven, `<resources>` and `include/exclude` patterns are complete, without relying on `overwrite` as a duplicate-handling strategy.
- [ ] Rules on `processResources` and `bootJar` do not conflict; required runtime files exist in the archive.
- [ ] `META-INF/services/**` is not blindly collapsed and `META-INF/**` is not stripped; shaded JARs use explicit merge transformers.
- [ ] Filtering applies only to intended text files, never corrupts binaries, and never writes two files to the same output path.
- [ ] Verified both **pre-archive resource outputs** and the **packaged archive**; aware that `jar tf` lists names only.
- [ ] The running artifact loads resources via **classpath** paths without depending on `src/main/resources` still existing on disk.
- [ ] No secrets, drafts, backups, or test data enter the production JAR; build outputs remain reproducible.

**Core principle:** determine **target paths** first and resolve duplicates **as early in the pipeline as possible**. `include/exclude` decides **which files travel**; Gradle's `duplicatesStrategy` decides **how collisions react**; Maven requires explicit sources and target mappings; the archive task decides **JAR/WAR structure**; and the runtime classpath decides **which resource is loaded**. Inspecting actual outputs and running the real artifact is the final verification.

## Technical References

- [Gradle ProcessResources task](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html)
- [Gradle DuplicatesStrategy API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/DuplicatesStrategy.html)
- [Apache Maven Resources Plugin — Including and Excluding](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html)
- [Apache Maven Resources Plugin — Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Spring Boot — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
