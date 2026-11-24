# Configuring Reproducible File Order and Timestamps for Gradle Archives

## 1. Goal and Motivation

When a team builds the same Spring Boot commit on a laptop and in CI, the ideal outcome is **the exact same artifact with identical bytes and identical SHA-256**. In practice, two JAR or WAR files sometimes behave identically yet produce different hashes because archive entries appear in a different order, individual entry timestamps change, file permissions come from the host filesystem, or a task embeds time-dependent metadata.

**Reproducible archives** are a vital pillar of a *reproducible build*: if inputs, toolchains, and influential environment factors are held steady, the resulting ZIP/JAR/WAR/TAR artifacts must also remain byte-for-byte stable. This supports provenance verification, release artifact validation, catching unintended changes, reducing downstream task cache misses, and supply-chain security.

After this lesson, you will be able to:

1. Understand why **file order (entry order)** and **entry timestamps** alter archive bytes even when source contents stay unchanged.
2. Use `reproducibleFileOrder = true` and `preserveFileTimestamps = false` on Gradle `AbstractArchiveTask` tasks.
3. Distinguish **Gradle 9.0+ defaults** from explicit configuration needed while still supporting Gradle 8.x or older.
4. Apply these settings to `Jar`, `Zip`, `Tar`, `War`, and Spring Boot `bootJar`/`bootWar`; know which items require separate checks per plugin version.
5. Build a runnable Java 17 + Spring Boot project, package a ZIP and Boot JAR, and use **two clean builds bypassing the build cache** to compare SHA-256 digests.
6. Diagnose hash mismatches caused by manifests, generated resources, compiler/toolchain differences, dependency versions, file permissions, nested JARs, or other metadata.
7. Design a CI build-reproducibility verification step and understand the limits of “matching hashes” as evidence.

**Practice assumptions:** Java 17, Spring Boot Gradle Plugin 3.3.5, and a compatible **Gradle Wrapper 8.x** for examples. These versions illustrate configuration, not the latest recommended releases. Gradle 9.0+ and 9.7+ are discussed separately because defaults/APIs changed; use newer APIs only when your project's Spring Boot/plugins and Gradle are genuinely compatible.

## 2. Understanding Archive Structure: Bytes Matter More Than Filenames

JAR and WAR files are ZIP formats with content conventions; each ZIP entry carries a **name, data, compression details, and metadata**, including a timestamp. TAR also stores per-member metadata. Consequently, archives can differ at the byte level even when unpacking yields files with identical contents.

Consider two ZIPs both containing two files:

~~~text
Archive A
  alpha.txt  timestamp: build run A
  beta.txt   timestamp: build run A

Archive B
  beta.txt   timestamp: build run B
  alpha.txt  timestamp: build run B
~~~

Even when `alpha.txt` and `beta.txt` have identical contents, differing **entry order and timestamp metadata** change the ZIP's SHA-256. Never rely on “we unzipped and diffed the folders with no diffs” to conclude two archives are byte-for-byte identical.

### Two Distinct Timestamp Layers

| Time | Where does it live? | Controlled by `preserveFileTimestamps`? |
| --- | --- | --- |
| **Archive entry timestamp** | Per-file metadata inside ZIP/JAR/WAR/TAR | Yes: set `false` so Gradle uses a fixed archive-type timestamp |
| **Filesystem mtime of the .jar/.zip file itself** | Outer archive file metadata on disk after build/copy | Not directly: writing a file updates the *outer file's* mtime even when inner bytes match |
| **Time inside generated files/manifests** | Text contents like `Built-At: 2026-...` or `build.time=...` | No: you must fix the generator itself or stop embedding volatile data |
| **Time from application/runtime logs** | Logs emitted when running the app | Unrelated to archive SHA-256 unless logs are written into the archive |

**When verifying reproducibility, compare the SHA-256 of the archive files**. Never treat timestamps displayed in File Explorer, Finder, or `ls -l` on the outer archive as failure evidence.

### File Order and Path Order

`reproducibleFileOrder` ensures Gradle traverses files inside **input directories** in a reproducible order rather than relying on filesystem/OS directory iteration order. It **is not a magic switch that sorts every entry regardless of sources, CopySpecs, dependency ordering, or nested archives**.

For an archive to truly stabilize, every `from(...)` input, manifest property, dependency JAR, and upstream task output must also behave deterministically. If a script builds text by iterating a `HashMap` and writes that order to a resource, flipping two archive flags **cannot fix that text content**.

## 3. Two Core Gradle Properties

Most archive tasks extend `org.gradle.api.tasks.bundling.AbstractArchiveTask`. They expose two Boolean properties:

| Property | Recommended value | Effect |
| --- | --- | --- |
| `reproducibleFileOrder` | `true` | Traverses files from directory inputs in a consistent order across filesystems/OSes |
| `preserveFileTimestamps` | `false` | Drops original source file timestamps in archive entries; uses a fixed value defined by Gradle |
| `reproducibleFileTimestamp` | Optional in Gradle 9.7+ | Supplies a **deterministic timestamp** (epoch milliseconds) for all entries instead of the default fixed value; requires `preserveFileTimestamps=false` |

### Distinguishing Gradle 8.x and 9.x

- **Gradle before 9.0:** archive tasks support both Boolean properties, yet **do not enable full reproducible defaults like Gradle 9**. To guarantee results, configure `false/true` explicitly in the build.
- **Gradle 9.0 and later:** per Gradle documentation, `AbstractArchiveTask` defaults to `preserveFileTimestamps=false` and `reproducibleFileOrder=true`, and file/dir entries use stable default permissions (`0644` for files, `0755` for directories).
- **Gradle 9.7 and later:** the incubating `reproducibleFileTimestamp` API lets you pick a custom fixed timestamp. **Do not call this property in projects running Gradle 8.x**, as the API does not exist there.

Therefore **never blindly apply “defaults are always false/true” across all versions**. Check `./gradlew --version` or `.\gradlew.bat --version` before deciding whether explicit configuration is needed.

### When Should You Not Preserve Timestamps?

When the goal is a byte-for-byte reproducible artifact, you generally **must not** preserve filesystem timestamps. Even from the same commit checkout, files on machine A and machine B can have different mtimes; `preserveFileTimestamps=true` carries that variation into the archive.

### What If File Permissions Matter?

Gradle 9+ normalizes permissions via defaults as well. On older Gradle releases, builds on Unix machines with differing `umask` and executable bits can alter archives. APIs like `filePermissions` and `dirPermissions` allow explicit configuration **when supported by your Gradle version**; do not blindly force `0644` onto shell scripts that must remain executable. Set permissions intentionally and verify script executability after extraction.

## 4. Groovy DSL Configuration for All Archive Tasks

In `build.gradle`, once the project has plugins applied, add:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**This is an excerpt**, not a full project file. If the file already has `import` and `plugins` blocks, place the import at the top and `tasks.withType...` in a valid build script position; avoid conflicting blocks configuring the same flags.

Explanation:

1. `tasks.withType(AbstractArchiveTask)` targets tasks whose type subclasses `AbstractArchiveTask` in the **current project**, including `Jar`, `Zip`, `Tar`, `War`, and plugin-registered archive tasks.
2. `configureEach` uses lazy configuration, covering tasks registered later by plugins without eagerly realizing every task.
3. `preserveFileTimestamps=false` and `reproducibleFileOrder=true` govern archive entry metadata and input file traversal order.
4. This block **adds no new tasks** and **selects no dependency versions**; it only configures archive tasks registered in the project.
5. In multi-project builds, a root-level block does not automatically apply to **subprojects**. Place it in a shared convention plugin or configure per module according to your build architecture.

### Applying to a Single Task Only

If a team wants to adjust only one specific archive rather than all archives:

~~~groovy
tasks.named('jar', Jar) {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Or for the Spring Boot task:

~~~groovy
tasks.named('bootJar') {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Spring Boot Gradle Plugin's `bootJar` subclasses `Jar` via `BootJar`, inheriting archive properties. For an application module releasing only `bootJar`, a narrower scope may be easier to review than configuring every task.

**Do not configure `jar` and assume `bootJar` was configured too.** They are **two separate tasks**, even though they draw from similar files. If CI publishes the Boot executable JAR, inspect the configuration of `bootJar` itself.

## 5. Kotlin DSL Equivalent

In `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Note the property naming difference in Kotlin DSL:

- Groovy: `preserveFileTimestamps`, `reproducibleFileOrder`.
- Kotlin: `isPreserveFileTimestamps`, `isReproducibleFileOrder`.

These are Boolean properties on tasks, **not Gradle project properties**. Writing `org.gradle.reproducibleFileOrder=true` in `gradle.properties` is not an official way to enable these properties across archive tasks.

For a specific task, Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Place `import` statements at the top of the build script. Pick Groovy **or** Kotlin per project; never mix both syntaxes in one file.

## 6. Sample Project: Spring Boot Executable JAR and Document ZIP

We will build a Gradle Groovy DSL project producing two artifacts to compare:

- `build/distributions/source-data.zip` created from text files, directly demonstrating file order and entry timestamps.
- `build/libs/archive-demo-0.0.1-SNAPSHOT.jar` as the Spring Boot executable JAR, verifying the settings also apply to `BootJar` without breaking `java -jar`.

### 6.1. Directory Structure

~~~text
archive-demo/
├── settings.gradle
├── build.gradle
├── gradlew, gradlew.bat, gradle/wrapper/
└── src/
    └── main/
        ├── archive-data/
        │   ├── alpha.txt
        │   └── beta.txt
        └── java/com/example/archive/
            └── ArchiveDemoApplication.java
~~~

This example assumes you have created a Gradle project with a valid Wrapper; **never type out `gradlew` manually while skipping the wrapper JAR**. When integrating into an existing Spring Boot project, adopt only the archive configuration rather than overwriting the existing build file.

### 6.2. The settings.gradle File

~~~groovy
rootProject.name = 'archive-demo'
~~~

### 6.3. First Data File: src/main/archive-data/alpha.txt

~~~text
alpha
~~~

### 6.4. Second Data File: src/main/archive-data/beta.txt

~~~text
beta
~~~

These files are inputs to `packageDocuments`, **kept outside `src/main/resources`** to avoid unexpectedly affecting the Boot JAR. Filesystem file order may vary across machines, yet the archive task traverses directory inputs in a reproducible order.

### 6.5. Complete build.gradle File

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.bundling.Zip

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.archive.ArchiveDemoApplication'
}

// Compatible with Gradle 8.x versions still supported by projects.
// Gradle 9.0+ enables both settings by default.
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}

tasks.register('packageDocuments', Zip) {
    from('src/main/archive-data')
    archiveFileName = 'source-data.zip'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

**This is the complete build script for the Groovy DSL example.**

- `java.toolchain` selects Java 17 for Java tasks, keeping compilation consistent between local/CI when a matching JDK exists.
- `spring-boot-starter` provides a minimal Boot app without a web server to run JAR checks.
- `springBoot.mainClass` specifies the application entry point, avoiding detection discrepancies if more main classes are added later.
- `tasks.withType(AbstractArchiveTask).configureEach` applies to both `packageDocuments` and the `bootJar` task registered by the Spring Boot plugin.
- `packageDocuments` is a `Zip` task taking two text files from a fixed directory and writing `source-data.zip`.
- `destinationDirectory` places the ZIP under `build/distributions`; `clean` deletes these outputs **without deleting source data**.
- `BOOT-INF/lib` inside the Boot JAR is packaged by the Spring Boot plugin, not drawn from `src/main/archive-data`.

**Build tool note:** the Spring Boot plugin version in the example is illustrative. If an existing project uses another Spring Boot plugin version, do not downgrade or upgrade it just to set two archive properties. Do not alter dependency management, repositories, or the Gradle Wrapper in a PR intended solely to enable archive reproducibility.

### 6.6. The src/main/java/com/example/archive/ArchiveDemoApplication.java File

~~~java
package com.example.archive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ArchiveDemoApplication {

    public static void main(String[] args) {
        System.out.println("ARCHIVE_DEMO_OK");
        SpringApplication.run(ArchiveDemoApplication.class, args);
    }
}
~~~

This Java 17+ source suffices to build a Spring Boot executable JAR with the declared Starter dependency. Without a web starter, the program normally starts and exits after creating the `ApplicationContext`; no database connection or HTTP port is needed.

The line printed by program code is:

~~~text
ARCHIVE_DEMO_OK
~~~

Afterward, the Spring Boot banner/logs with timestamps and PID may appear. **Timestamps in runtime logs do not alter the JAR**, because logs are not stored inside the archive. Do not confuse the two kinds of timestamps.

## 7. Initial Execution and Archive Inspection

### Linux/macOS

~~~bash
./gradlew --version
./gradlew --no-build-cache clean packageDocuments bootJar
ls -lh build/distributions/source-data.zip
ls -lh build/libs/archive-demo-0.0.1-SNAPSHOT.jar
jar tf build/distributions/source-data.zip
jar tf build/libs/archive-demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/archive-demo-0.0.1-SNAPSHOT.jar
~~~

### Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --no-build-cache clean packageDocuments bootJar
Get-Item .\build\distributions\source-data.zip
Get-Item .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar
jar tf .\build\distributions\source-data.zip
jar tf .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar
java -jar .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar
~~~

`jar tf` is the JDK tool for listing ZIP/JAR entries; to verify reproducibility, you must still **compare hashes across two separate builds**, not just inspect the file listing once.

### Expected Observations

- `source-data.zip` contains two entries `alpha.txt` and `beta.txt`, with no unexpected OS files or directories.
- The Boot JAR contains entries such as `BOOT-INF/classes/com/example/archive/ArchiveDemoApplication.class`, nested dependencies, and the launcher matching the Spring Boot plugin version.
- `java -jar` prints `ARCHIVE_DEMO_OK` without throwing `ClassNotFoundException` from launcher/nested libraries.
- No `build.timestamp`, `Built-At`, or clock data added by you in generated resources/manifest.

**Never treat filename, file size, or `BUILD SUCCESSFUL` as bit-for-bit proof**. Two JARs with identical names and sizes can still have different SHA-256 hashes.

## 8. Running Two Clean Builds and Comparing SHA-256 — Linux/macOS

Run on the exact same source checkout and Wrapper/JDK, without editing any source files. Save artifact copies **outside the `build` directory** because `clean` deletes previous outputs.

### Step 1: First Build and Save Artifacts

~~~bash
./gradlew --no-build-cache clean packageDocuments bootJar

mkdir -p .repro-check
cp build/distributions/source-data.zip .repro-check/source-data-1.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/application-1.jar

sha256sum .repro-check/source-data-1.zip
sha256sum .repro-check/application-1.jar
~~~

### Step 2: Rebuild from Clean Output

~~~bash
./gradlew --no-build-cache clean packageDocuments bootJar

cp build/distributions/source-data.zip .repro-check/source-data-2.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/application-2.jar

sha256sum .repro-check/source-data-2.zip
sha256sum .repro-check/application-2.jar
~~~

### Step 3: Compare Bytes

~~~bash
cmp -s .repro-check/source-data-1.zip .repro-check/source-data-2.zip \
  && echo "ZIP_IDENTICAL"

cmp -s .repro-check/application-1.jar .repro-check/application-2.jar \
  && echo "JAR_IDENTICAL"
~~~

If both ZIP files match completely, this line appears:

~~~text
ZIP_IDENTICAL
~~~

If both Boot JAR files match completely, this line appears:

~~~text
JAR_IDENTICAL
~~~

**These two lines are conditional outcomes**, not a promise they always print in every project. If `cmp` detects differences, the corresponding marker is omitted; use `sha256sum` and the troubleshooting section to investigate. In CI scripts that must fail loudly when bytes differ, run `cmp` directly with its exit code or `set -e` rather than letting `&&` skip silently while the job passes.

**Why `--no-build-cache`?** To test that tasks **actually regenerate identical bytes**, rather than restoring the same cached archive from a prior run. `clean` wipes outputs; the build cache can otherwise restore tasks unless disabled. If custom plugins write outputs outside `build`, control or clean those outputs during the test too.

## 9. Windows PowerShell Equivalent

On Windows, with `gradlew.bat` and JDK available, use `Get-FileHash` (no `sha256sum` installation needed).

### Step 1: Run Build and Save Both Archives

~~~powershell
.\gradlew.bat --no-build-cache clean packageDocuments bootJar

New-Item -ItemType Directory -Force .\.repro-check | Out-Null
Copy-Item .\build\distributions\source-data.zip .\.repro-check\source-data-1.zip
Copy-Item .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar .\.repro-check\application-1.jar

Get-FileHash .\.repro-check\source-data-1.zip -Algorithm SHA256
Get-FileHash .\.repro-check\application-1.jar -Algorithm SHA256
~~~

### Step 2: Second Clean Build

~~~powershell
.\gradlew.bat --no-build-cache clean packageDocuments bootJar

Copy-Item .\build\distributions\source-data.zip .\.repro-check\source-data-2.zip
Copy-Item .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar .\.repro-check\application-2.jar

Get-FileHash .\.repro-check\source-data-2.zip -Algorithm SHA256
Get-FileHash .\.repro-check\application-2.jar -Algorithm SHA256
~~~

### Step 3: Assert Matching Hashes and Fail on Mismatch

~~~powershell
$zip1 = (Get-FileHash .\.repro-check\source-data-1.zip -Algorithm SHA256).Hash
$zip2 = (Get-FileHash .\.repro-check\source-data-2.zip -Algorithm SHA256).Hash
$jar1 = (Get-FileHash .\.repro-check\application-1.jar -Algorithm SHA256).Hash
$jar2 = (Get-FileHash .\.repro-check\application-2.jar -Algorithm SHA256).Hash

if ($zip1 -ne $zip2) { throw "ZIP hash mismatch" }
if ($jar1 -ne $jar2) { throw "JAR hash mismatch" }

Write-Output "ZIP_IDENTICAL"
Write-Output "JAR_IDENTICAL"
~~~

When both comparisons pass, exact output from the last two statements is:

~~~text
ZIP_IDENTICAL
JAR_IDENTICAL
~~~

PowerShell prints hex hashes in uppercase; comparing two strings both produced by `Get-FileHash` avoids case-sensitivity mismatches on SHA-256 strings.

### About the .repro-check Directory

`.repro-check` sits **outside `build`** so Gradle `clean` does not erase it. Never commit this test directory to Git or accidentally include it via an archive's `from('.')`. If a project copy task pulls the whole repo as input, exclude `.repro-check` or place comparison artifacts in an external temp directory outside the project.

## 10. Inspecting Entry Order and Timestamps Inside the Archive

### 10.1. Listing ZIP/JAR Entry Order

On Linux:

~~~bash
jar tf .repro-check/source-data-1.zip
jar tf .repro-check/source-data-2.zip
~~~

In PowerShell:

~~~powershell
jar tf .\.repro-check\source-data-1.zip
jar tf .\.repro-check\source-data-2.zip
~~~

Compare the **entire line order**. For the sample ZIP, `alpha.txt` and `beta.txt` normally appear in a consistent order. If an archive includes directory entries, `jar tf` prints directory paths too; that is not necessarily an error.

### 10.2. Viewing Entry Timestamps with JDK

Use `jar tvf` instead of `jar tf`:

~~~bash
jar tvf .repro-check/source-data-1.zip
jar tvf .repro-check/source-data-2.zip
~~~

`jar tvf` displays size, formatted timestamp, and entry name. **Displayed date/time can depend on the tool's timezone/locale**, so avoid relying solely on human-readable strings across machines in different time zones. For exact ZIP metadata inspection, use a dedicated ZIP inspector; in CI, prefer **byte-for-byte SHA-256**.

### 10.3. Using Python (If Available) to Inspect ZIP Entry Metadata

This is an **optional** check requiring Python 3, outside Gradle core. Linux/bash:

~~~bash
python3 - <<'PY'
from zipfile import ZipFile
path = ".repro-check/source-data-1.zip"
with ZipFile(path) as archive:
    for entry in archive.infolist():
        print(entry.filename, entry.date_time)
PY
~~~

It reveals entry order and the date-time tuple stored in the ZIP for each entry. **Do not expect the timestamp to match the build run date/time** when `preserveFileTimestamps=false`; Gradle writes a fixed metadata value matching the archive format and Gradle version.

### 10.4. Avoid Confusing Outer mtime with Inner Timestamps

`stat`/`Get-Item` may show a different modification time on `application-1.jar` vs. `application-2.jar` because the two copies happened at different moments. **If SHA-256 hashes match**, the archive bytes are still identical. That is a completely valid reproducible state.

## 11. Applying to Spring Boot bootJar and bootWar

### 11.1. bootJar Is a Subtype of Jar

In Spring Boot Gradle Plugin 3.3, `org.springframework.boot.gradle.tasks.bundling.BootJar` extends `Jar`, so it inherits `AbstractArchiveTask` properties. The broad configuration:

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

applies to `bootJar` within the **configured project**. To restrict strictly to the executable JAR:

~~~groovy
tasks.named('bootJar') {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Do not treat `jar` and `bootJar` as the same task**. The Java plugin's `jar` normally builds a plain JAR, while the Spring Boot plugin builds the Boot executable JAR with loader and dependencies in `BOOT-INF/lib`. A project may produce both archives; when comparing release artifact hashes, pick **the exact published `bootJar` file**, not `-plain.jar`.

### 11.2. bootWar Is a Subtype of War

In projects using both Gradle's `war` plugin and the Spring Boot plugin, `bootWar` also inherits archive mechanics. Groovy DSL example:

~~~groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
}

tasks.named('bootWar') {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**This is a fragment**, not a standalone WAR project: a deployable WAR needs Servlet application code, dependencies, and proper `providedRuntime` configuration. The point here is solely that both archive properties apply to `bootWar`. When inspecting a WAR, examine `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` rather than assuming `BOOT-INF` from executable JARs.

### 11.3. Embedded/Nested Dependencies and Layers

A Spring Boot executable JAR contains nested dependency JARs and may include `BOOT-INF/layers.idx` or metadata supporting container image layering. Gradle's two flags control **outer archive entries** and Gradle packaging, yet cannot fix bytes **inside an already-published dependency JAR**.

If a SNAPSHOT/changing dependency is rebuilt with different bytes under the same version, the outer Boot JAR rightly changes its SHA-256. Lock/pin versions and verify dependency provenance instead of trying to tweak file ordering to mask differences.

Dependency entry ordering, layer index metadata, and Java build tools can also vary across Spring Boot plugin versions. Therefore artifact comparisons must hold **plugin versions and dependency graphs constant**. `reproducibleFileOrder=true` is an important condition, not a guarantee that all plugins/generators are deterministic.

## 12. Kotlin DSL Equivalent of the Sample Project

If a repository uses Kotlin DSL instead of Groovy, substitute the following files.

**settings.gradle.kts:**

~~~kotlin
rootProject.name = "archive-demo"
~~~

**build.gradle.kts:**

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
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
    implementation("org.springframework.boot:spring-boot-starter")
}

springBoot {
    mainClass.set("com.example.archive.ArchiveDemoApplication")
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

tasks.register<Zip>("packageDocuments") {
    from("src/main/archive-data")
    archiveFileName.set("source-data.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
}
~~~

**Kotlin DSL compilation note:** `Zip` is a Gradle task class included in standard Gradle Kotlin DSL default imports. If your build script or Gradle version does not resolve it automatically, add `import org.gradle.api.tasks.bundling.Zip` at the top of the file; sample projects may import it explicitly for clarity.

With the same `ArchiveDemoApplication.java` and two text files, run:

~~~bash
./gradlew --no-build-cache clean packageDocuments bootJar
~~~

Expected output matches the Groovy version: one document ZIP and one Spring Boot executable JAR. **Never keep both `settings.gradle`/`settings.gradle.kts` or `build.gradle`/`build.gradle.kts` in the same role within one project**; pick one DSL to prevent overlapping configuration.

## 13. Setting Meaningful Reproducible Timestamps: Gradle 9.7+ (Advanced)

By default `preserveFileTimestamps=false` suffices to strip filesystem timestamps. When an organization wants archive entries to carry a **meaningful deterministic timestamp**, such as the source commit timestamp, Gradle **9.7+** offers the incubating `reproducibleFileTimestamp` API.

### 13.1. Obtaining SOURCE_DATE_EPOCH from a Trusted Source

`SOURCE_DATE_EPOCH` is an environment variable widely used in reproducible build workflows representing **seconds since the Unix epoch**. It can come from a pinned commit timestamp, e.g., via Git:

~~~bash
git log -1 --format=%ct
~~~

This yields a **commit-dependent** value stable across builds of the same commit; it does not always represent a business timestamp. In production CI, its origin must be validated and applied consistently.

### 13.2. Groovy DSL (Gradle 9.7+)

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
    reproducibleFileTimestamp = providers.environmentVariable('SOURCE_DATE_EPOCH')
        .map { seconds ->
            java.time.Instant.ofEpochSecond(seconds.toLong()).toEpochMilli()
        }
}
~~~

### 13.3. Kotlin DSL (Gradle 9.7+)

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import java.time.Instant

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    reproducibleFileTimestamp = providers.environmentVariable("SOURCE_DATE_EPOCH")
        .map { Instant.ofEpochSecond(it.toLong()).toEpochMilli() }
}
~~~

**This is an advanced 9.7+ API example; do not use it in the Gradle 8.x project in Section 6.** If your Spring Boot plugin is incompatible with Gradle 9.7, **do not upgrade Gradle solely to use this property**; the two standard flags already handle archive timestamp stabilization.

Notes:

- `reproducibleFileTimestamp` expects **milliseconds**, while `SOURCE_DATE_EPOCH` uses **seconds**. Thus you must convert with `Instant.ofEpochSecond(...).toEpochMilli()`.
- `preserveFileTimestamps` must be `false`; setting `true` alongside a custom reproducible timestamp causes Gradle to error.
- ZIP date/time has its own resolution and valid range; Gradle may clamp values below the minimum and reject timestamps exceeding format limits.
- The `reproducibleFileTimestamp` API is **incubating**; check documentation for your exact Gradle version before adopting it in long-term build policy.
- Never compute `SOURCE_DATE_EPOCH` from `date +%s` on every build if cross-run reproducibility is the goal: that merely replaces one volatile timestamp with **another volatile timestamp**.

## 14. File Permissions and Other Metadata

Beyond entry timestamps and file ordering, permission bits can vary across OSes, umasks, and CI agents. In Gradle 9.0+, `AbstractArchiveTask` standardizes default permissions for file and directory entries to support reproducibility.

If a project needs intentional fixed permissions, compatible Gradle versions support:

~~~groovy
tasks.named('jar', Jar) {
    preserveFileTimestamps = false
    reproducibleFileOrder = true

    filePermissions {
        unix('644')
    }
    dirPermissions {
        unix('755')
    }
}
~~~

**This excerpt applies only to `jar`**, and does not automatically configure `bootJar`. In archives containing shell scripts or native executables, `644` removes execute permissions, so apply separate rules for executable entries.

**Never alter file permissions solely to make hashes match** if doing so breaks artifact semantics. Rather than forcing arbitrary modes, maintain an explicit policy for regular files, directories, and executables, and verify on the target environment.

Other metadata that can cause archives to differ even when both flags are set:

- JAR/WAR manifests containing `Implementation-Version`, `Build-Time`, or clock-generated attributes.
- Spring Boot `build-info.properties` generated by `bootBuildInfo`: `build.time` can vary depending on config/plugin; check when enabled.
- Java/Kotlin code compiled by different compiler versions producing different bytes.
- Resource filtering injecting hostnames, workspace paths, CI job numbers, or varying commit metadata.
- ZIP entry permissions/owner/group, file encodings/line endings, and compression settings changing across build tools/OSes.
- `SNAPSHOT`/changing dependencies or repositories returning different bytes under the same coordinate.
- Code generator tasks relying on `HashMap` iteration order, random seeds, locale/timezone, or network calls.

**Proper handling:** prove which component differs first rather than disabling hash checks or copying an old archive to “achieve PASS.”

## 15. Troubleshooting: Hashes Differ After Two Clean Builds

| Symptom | Cause to investigate | Remediation |
| --- | --- | --- |
| `source-data.zip` hash differs though alpha/beta are unchanged | Archive flags missed the task or input file metadata differs | Check `packageDocuments`, entry order/timestamps, Gradle Wrapper |
| `jar tf` lists identical files, yet SHA-256 differs | Entry timestamps, permissions, compression, manifest/metadata, or nested JAR bytes | Inspect `jar tvf`, manifest, entries, and binary diff |
| `bootJar` hash differs while data ZIP matches | Generated resources, nested dependencies, loader/plugin version, manifest, or class files | Compare `BOOT-INF/classes`, `BOOT-INF/lib`, Boot plugin/dependency graph |
| `reproducibleFileOrder=true` is set, yet hash still differs | Flag only normalizes partial source ordering; contents/metadata remain volatile | Audit `preserveFileTimestamps`, permissions, generators |
| `preserveFileTimestamps=false` is set, yet `build.time` changes | Timestamp lives **inside the contents** of generated resources/manifest | Fix generator, use fixed timestamp, or omit build time |
| Linux CI hash differs from Windows laptop | Line endings, JDK/compiler, file permissions, Gradle/plugin version, normalized inputs | Pin Wrapper/toolchain, compare sources and generated outputs |
| `--build-cache` gives matching hashes, disabling cache differs | Restoring the same cached artifact instead of generating deterministic output | Test with `--no-build-cache clean` to verify true regeneration |
| Changing `SOURCE_DATE_EPOCH` alters the hash | Custom timestamp is an influential input | Keep timestamp constant for the same source/commit |
| Gradle reports unknown property `reproducibleFileTimestamp` | Wrapper too old (< Gradle 9.7) | Drop the new API; use the two long-supported Boolean properties |
| Gradle errors on custom timestamp | `preserveFileTimestamps=true` set or timestamp out of format range | Set `false`, check timestamp units and range |
| SHA-256 matches, yet `ls -l` shows different modified dates | Outer archive file's filesystem mtime differs | Not a reproducibility failure; bytes are identical |
| `Jar` matches, yet `bootWar` differs | Only `jar` task configured, not `bootWar` | Use `AbstractArchiveTask` or configure the actual deployed task |
| Artifact disappears after `clean` | First comparison copy was stored inside `build` | Save first artifact in `.repro-check` or external temp dir |
| Archive contains unexpected entries | CopySpec `from('.')`, temp files, backups, untracked content | Specify explicit input directories; never package the entire repo |
| CI tests pass, yet artifact hashes differ | Tests verify behavior, not bytes | Add two-clean-build hash comparison and investigate diffs |
| Disabling `preserveFileTimestamps` breaks a legacy tool | Downstream tool relies on archived file mtimes | Re-evaluate requirement; build a separate artifact or record explicit business timestamps |

### Steps to Analyze a Detected Mismatch

1. Record SHA-256 of both archives and `./gradlew --version`.
2. Run `jar tf` to diff entry lists and **entry order**, and `jar tvf` to inspect timestamps.
3. If entry lists match, unpack each archive into separate directories and diff **file contents**; if contents match, focus on metadata/compression.
4. Inspect `META-INF/MANIFEST.MF` and generated resources like `build-info.properties`.
5. For Boot JARs, compare `BOOT-INF/lib` listings and nested JAR SHA-256 hashes if needed; do not assume all dependencies are locked just because filenames match.
6. Compare toolchains, Gradle Wrapper, compiler flags, locale, encoding, input line endings, and permissions.
7. Once the source of divergence is found, fix it **at the source of truth** (build script, generator, dependency management, CI environment)—never hand-edit the JAR after building.
8. Rerun **two clean builds without cache** and re-compare hashes.

## 16. Reproducibility, Build Cache, and Supply Chain: Related, Not Identical

| Mechanism | Purpose | Why is it related? |
| --- | --- | --- |
| Reproducible archives | Same inputs → same bytes in ZIP/JAR/WAR | Enables artifact hash comparisons |
| Gradle Build Cache | Reuses cacheable task outputs by inputs/cache key | Deterministic outputs make cache entries reliable and cut invalidation |
| Up-to-date checks | Skips tasks when workspace inputs/outputs remain valid | Does not prove another machine reproduces identical bytes |
| Dependency verification/locking | Verifies/stabilizes resolved modules and versions | Reduces risk of same source pulling different dependencies |
| SBOM/provenance/attestations | Records artifact origin and composition | Reproducible hashes are strong evidence, yet do not prove code safety |
| CI artifact retention | Preserves built artifacts to deploy exactly what was tested | Avoids rebuilding with uncontrolled inputs or environments |

**Never treat a build cache hit as reproducibility proof**: when a task loads from cache, you may simply be comparing the same byte stream produced by an earlier run. Testing with `--no-build-cache clean` or in an independent environment is stronger verification.

**Matching SHA-256 hashes do not prove an artifact has no vulnerabilities**: they prove two files share identical bytes with negligible collision probability in practice. You still need dependency scanning, tests, signing, permissions, and appropriate provenance.

### Why Does This Help Container Images?

A Spring Boot JAR can enter a container image as a single file or split into layers. If every build emits a JAR with a different hash due to harmless metadata, Docker/OCI image layers and build caches are invalidated even though functional source did not change. Byte-stable archives make caching and artifact auditing more predictable.

**Never infer container image digests will match merely because JAR hashes match**: Dockerfiles, base image digests, layer metadata, timestamps, build arguments, and image tooling can also vary.

## 17. A CI Reproducibility Check — Safe Bash Script

If your organization requires verifying that two builds of the same commit produce identical SHA-256 hashes, the following script illustrates a **same-CI-worker comparison**. Use a pinned container/JDK/Gradle Wrapper and keep functional testing separate from the reproducibility check.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

./gradlew --no-build-cache clean packageDocuments bootJar

mkdir -p .repro-check
cp build/distributions/source-data.zip .repro-check/source-1.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/app-1.jar

./gradlew --no-build-cache clean packageDocuments bootJar

cp build/distributions/source-data.zip .repro-check/source-2.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/app-2.jar

sha256sum .repro-check/source-1.zip .repro-check/source-2.zip
sha256sum .repro-check/app-1.jar .repro-check/app-2.jar

cmp .repro-check/source-1.zip .repro-check/source-2.zip
cmp .repro-check/app-1.jar .repro-check/app-2.jar

echo "REPRODUCIBLE_ARCHIVES_PASS"
~~~

When all `cmp` checks confirm matching bytes, the **final output printed by the script** is:

~~~text
REPRODUCIBLE_ARCHIVES_PASS
~~~

If either the ZIP or JAR differs, `cmp` returns a non-zero exit code and `set -e` stops the script before printing PASS. Avoid `cmp || true` or swallowing exit codes; CI should fail clearly.

**This is only a same-worker check**. Stronger verification runs across **two independent workspaces or two machines** from the same commit with controlled tools, exchanging hashes/artifacts for comparison. For cross-OS checks, address compiler/encoding/path normalization as well, not just archive flags.

Avoid blindly running two heavy builds back-to-back on every PR if cost is prohibitive; run it as a periodic job, release gate, or check per organization policy. Even so, for release artifacts requiring strong provenance, gather real comparison evidence rather than merely trusting flags.

## 18. Common Misconceptions

| Claim | Reality |
| --- | --- |
| “Gradle always requires configuring `preserveFileTimestamps=false`.” | Starting in **Gradle 9.0**, this property defaults to `false` on `AbstractArchiveTask`; older Gradle needs checking/configuring. |
| “Setting `reproducibleFileOrder=true` alone is enough.” | Timestamps, permissions, generator outputs, and dependencies can still vary. |
| “Disabling `preserveFileTimestamps` erases Git history.” | It affects only **entry timestamps inside the archive**, not commit history or source file mtimes. |
| “Differing `.jar` filesystem mtimes mean it's not reproducible.” | Outer mtimes can differ while **archive bytes and SHA-256 match**. |
| “Matching hashes with `--build-cache` prove deterministic rebuilds.” | You may just be restoring cached outputs; verify with `--no-build-cache clean`. |
| “Matching `jar tf` filenames mean SHA-256 will match.” | Entry order, timestamps, permissions, compression, or nested JAR contents can still differ. |
| “Configuring `jar` automatically configures `bootJar`.” | They are distinct tasks, even though `bootJar` subclasses `Jar`. |
| “Archive settings fix timestamps inside `build-info.properties`.” | No; that is **file content**, requiring fixes in the generator/source config. |
| “`reproducibleFileTimestamp` works in every Gradle version.” | It was introduced in **Gradle 9.7**; 8.x projects must not use it. |
| “Matching hashes prove the image/SBOM is secure.” | You still need dependency/provenance/vulnerability checks and verification of other layers. |

## 19. Checklist and Hands-On Exercise

Perform this in an experimental branch of a Java 17+ Spring Boot Gradle project:

1. Check `./gradlew --version`, Java toolchain, and Spring Boot plugin version. Determine whether Gradle is before or at/after **9.0**.
2. On Gradle 8.x, or when wanting explicit policy visibility, add both flags on `AbstractArchiveTask`: `preserveFileTimestamps=false`, `reproducibleFileOrder=true`.
3. Create the `alpha.txt`/`beta.txt` source ZIP and the `ArchiveDemoApplication` Spring Boot project as shown.
4. Run `--no-build-cache clean packageDocuments bootJar`, inspect archives with `jar tf`, and locate the Boot executable JAR.
5. Save the first artifacts in `.repro-check` outside `build`.
6. Rebuild with the exact same command without touching sources/Gradle config/dependencies, and save the second artifacts.
7. Use `sha256sum` or `Get-FileHash` and `cmp`/PowerShell assertions to verify **both pairs of archives are byte-identical**.
8. If mismatched, check in order: entry order, timestamps, manifest, permissions, generated files, bytecode, nested dependencies, and toolchain.
9. Run `java -jar` to verify the Boot executable JAR still executes after normalizing metadata.
10. Test a **real change** (such as changing `alpha.txt` contents), rebuild, and verify the ZIP hash changes—this is expected, not a reproducibility failure.
11. Restore the original contents and verify the baseline hash reproduces.
12. Record results in PR/CI: Gradle/JDK/Boot versions, commands, run 1/2 SHA-256 digests, artifact files, and root causes if different.
13. If using remote build cache or configuration cache, treat them as **separate optimizations**; never rely on cache state as sole proof.
14. On Gradle 9.7+ with specific policies, evaluate whether `SOURCE_DATE_EPOCH` is truly required and held steady across builds.

**Success criteria:** you can explain why ZIP/JAR hashes change even with identical logical contents; configure `AbstractArchiveTask` in Groovy or Kotlin DSL; demonstrate two clean builds of identical source yielding **matching SHA-256 hashes**; and articulate the limits of these two archive flags.

## Official Documentation and Further Reading

- [Gradle – Working with Files: Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle – AbstractArchiveTask DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle – Upgrade to Gradle 9.0: Reproducible Archives Defaults](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html)
- [Gradle – Solving Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html)
- [Gradle – Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html)
- [Gradle – Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Gradle – Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – BootJar API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootJar.html)
- [Reproducible Builds – JVM](https://reproducible-builds.org/docs/jvm/)