# Stable File Order in Java Builds

**Stable file order** ensures that files are discovered, processed, and written into an artifact in a deterministic order across builds. This is part of a **reproducible build**: the same source, dependencies, and build environment must produce the same output, ideally byte-for-byte.

A JAR can contain the exact same classes and resources yet still have a different SHA-256 if the order of ZIP entries, timestamps, or metadata changes. Therefore, keeping file contents identical is not enough. You need to control directory traversal order, path sorting, generated resource order, archive timestamps, manifests, and tool versions.

## 1. Stable File Order and Reproducible Builds

These two concepts are related but not identical:

- **Stable file order:** the same set of files is processed and written into the archive in the same order.
- **Reproducible build:** the same inputs and controlled build environment produce an identical byte-for-byte artifact.

Stable file order solves one source of nondeterminism. Reproducible builds also require controlling timestamps, manifests, compilers, dependencies, generated files, compression, permissions, and other metadata.

For example, two JARs with the same entries:

~~~text
META-INF/MANIFEST.MF
com/acme/Main.class
config/app.properties
images/logo.png
~~~

If the first build writes them in alphabetical order and the second build writes them in filesystem order, the byte sequence of the ZIP archive may differ even though each file's content is identical. Consequently, the checksums of the two JARs will differ.

Stabilizing the order helps build caches work effectively, reduces noisy diffs, enables verifying released binaries from source, and reproduces signing/release workflows. Apache Maven describes a reproducible build as a process that creates a verifiable path from source to binary; output order and timestamps must be controlled. [Apache Maven: Reproducible/Verifiable Builds](https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971)

## 2. Why Can File Order Change?

Do not assume that the filesystem returns files in alphabetical order or in creation order.

APIs and patterns prone to nondeterminism:

~~~java
File[] files = directory.listFiles();
~~~

~~~java
try (var paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
~~~

~~~java
for (String name : hashSet) {
    process(name);
}
~~~

Sources of the problem:

- The filesystem may return directory entries in different orders.
- Windows, Linux, and macOS store and traverse directories differently.
- Creating, deleting, or renaming files in a different order can change traversal order.
- Files.walk() does not guarantee a stable encounter order across filesystems.
- HashMap and HashSet do not define an iteration order in their API contract.
- Multiple parallel tasks can finish in different orders.
- Generated sources or resources may be written in the order of an internal collection.
- Shell glob expansion can be affected by the shell and locale.

Gradle explicitly notes that directory iteration order can vary by OS and filesystem. Apache Maven also lists filesystem-dependent ZIP/JAR entry order as a source of unreproducible builds. [Gradle: Reproducible Archives](https://docs.gradle.org/current/userguide/best_practices_security.html) [Apache Maven: Sources of unreproducible output](https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971)

**Rule:** if input order affects the artifact, define the order explicitly with a comparator before processing.

## 3. Normalizing Paths Before Sorting

A stable order requires a stable path representation.

### Use relative paths

Do not sort by absolute path because the path contains machine-specific information. Instead, use paths relative to the root:

~~~text
src/Main.java
src/resources/config/app.properties
src/resources/images/logo.png
~~~

### Normalize separators

Windows uses backslashes, whereas ZIP/JAR entry paths use forward slashes. When creating archive entries, use:

~~~text
com/acme/Main.class
config/app.properties
images/logo.png
~~~

Use relative paths and normalize separators before sorting.

### Choose a locale-independent comparator

Do not use a Collator based on the default locale if you want the same result across machines with different locales.

In Java, String.compareTo() provides lexicographical order by UTF-16 code units and is locale-independent. This is a clear choice for normalized archive entry names.

If different languages or tools jointly create an archive, define a shared rule for encoding, Unicode normalization, and comparator. You can normalize names to Unicode NFC before sorting, while also detecting and rejecting two paths that become identical after normalization.

### Rules for case and path collisions

Some filesystems are case-sensitive, while others are case-insensitive by default. Names like Config/app.properties and config/app.properties can coexist on one filesystem but collide on another.

If the artifact is distributed cross-platform:

- Choose an explicit case-sensitive or case-insensitive rule.
- Detect duplicate names after applying that rule.
- Do not silently let whichever file is written last determine the content.
- Use an explicit duplicate policy: fail, merge deterministically, or select a declared source.

## 4. Sorting Files with Java 17+

The following example takes a root directory, traverses all regular files, converts paths to relative paths using forward slashes, and sorts them by String natural order.

Create **StableFileOrderDemo.java**:

~~~java
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public final class StableFileOrderDemo {
    private static String archivePath(Path relativePath) {
        return relativePath.toString()
                .replace(File.separatorChar, '/');
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0])
                .toAbsolutePath()
                .normalize();

        List<Path> ordered;

        try (Stream<Path> paths = Files.walk(root)) {
            ordered = paths
                    .filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(path ->
                            archivePath(root.relativize(path))))
                    .toList();
        }

        for (Path file : ordered) {
            System.out.println(
                    archivePath(root.relativize(file)));
        }
    }
}
~~~

Compile:

~~~bash
javac --release 17 StableFileOrderDemo.java
~~~

Run with a directory containing files:

~~~bash
java StableFileOrderDemo classes
~~~

For example, suppose the directory contains zeta.txt, alpha.txt, middle.txt, nested/omega.txt, and nested/beta.txt. Exact stdout:

~~~text
alpha.txt
middle.txt
nested/beta.txt
nested/omega.txt
zeta.txt
~~~

Key points:

1. Files.walk() only collects files; do not assume its traversal order.
2. root.relativize() strips the absolute path.
3. archivePath() normalizes separators.
4. sorted() applies an explicit comparator before processing.
5. Files are processed in the same order when their relative paths are the same.

This example only prints the list for demonstration. In an archiver or build task, use the sorted list itself as the input order.

### Handling symbolic links

Explicitly decide whether to include symbolic links in the archive. Files.walk() does not follow directory symlinks by default, but file-checking APIs may follow file symlinks depending on options. For reproducible and secure artifacts, you can skip or reject symlinks rather than letting the result depend on the target filesystem.

## 5. Entry Order in JAR and ZIP

JAR is based on the ZIP format. An archive contains local file headers, entry data, and a central directory holding entry metadata.

Entry order can affect the entire byte sequence of the archive. Even when file contents are unchanged, the following factors also make JARs differ:

- Entry order.
- Entry timestamps.
- Directory entries.
- Manifest attributes and attribute order.
- Compression method and compressed bytes.
- Extra fields in ZIP.
- Metadata added by the archiver or plugins.

For entries with unique names, changing the order usually does not change the class/resource content read by the application. However, the artifact's checksum and signature can change.

Duplicate entries are a different case: the same name appearing multiple times can cause unpredictable behavior across tools. Fail the build or define an explicit merge rule.

### Inspecting order in a JAR

Use:

~~~bash
jar --list --file app.jar
~~~

This command displays the entry order in the archive. You can use jar --verbose --list --file app.jar to see additional entry details.

Do not just compare a sorted list of names after extraction; inspect the actual entry order inside the archive if the goal is reproducible output.

## 6. Fixing Timestamps When Packaging

Stable order is not enough if each build writes the current timestamp into the ZIP/JAR.

The JDK jar tool provides the --date option to assign a fixed timestamp to entries when creating an archive:

~~~bash
jar --create --file app.jar --date=2024-01-01T00:00:00Z -C classes alpha.txt -C classes middle.txt -C classes nested/beta.txt -C classes nested/omega.txt -C classes zeta.txt
~~~

The file list in the example is passed in sorted order. For large projects, generate a list of relative paths via a script or build task and pass that list to the archiver.

View entry timestamps:

~~~bash
jar --verbose --list --file app.jar
~~~

Notes:

- --date fixes the timestamp of archive entries; it does not by itself solve all sources of nondeterminism.
- Choose a fixed timestamp or a timestamp tied to the source revision, not the current build time.
- ZIP has range and resolution limits for timestamps; stored values may be rounded according to the format.
- Use the same JDK and the same packaging tool version when byte-for-byte reproducibility is required.
- If using a plugin to create JARs, prefer the reproducible archive configuration supported by the plugin.

Oracle describes --date as an option to set the timestamp for entries when creating or updating a JAR. [Oracle JDK 24: jar command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)

## 7. Configuring Maven to Produce Stable JARs

The Maven JAR Plugin has supported reproducible output timestamps since version 3.2.0. The plugin also handles entry ordering to support reproducible JARs. [Maven JAR Plugin: outputTimestamp](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html) [MJAR-263: reproducible entry order and timestamp](https://issues.apache.org/jira/browse/MJAR-263)

In pom.xml, declare a stable timestamp and pin the plugin version:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</build>
~~~

The Maven JAR Plugin reads project.build.outputTimestamp to set the archive timestamp. Plugin versions 3.2.0 and above support this; the example uses 3.4.2.

Build:

~~~bash
mvn clean package
~~~

Inspect:

~~~bash
jar --list --file target/app-1.0.0.jar
~~~

For multi-module projects, manage plugin versions in the parent POM/pluginManagement so all modules use the same configuration.

### Choosing a timestamp from the source revision

A fixed value in the POM is easy to understand for demonstration. In frequently released projects, you can use the source commit timestamp as the output timestamp, as long as the same source revision always receives the same value.

The Maven JAR Plugin accepts timestamps in ISO-8601 format or as an integer representing seconds since the Unix epoch. Do not use maven.build.timestamp based on the current time because each build will produce a different value.

### Maven is not just the JAR Plugin

If the build also produces a source JAR, test JAR, WAR, ZIP, assembly, or shaded JAR, check the corresponding plugins. Reproducible configuration for maven-jar-plugin does not automatically guarantee that all third-party plugins produce stable output.

## 8. Configuring Gradle for Stable Archive Order

Gradle provides two important properties in AbstractArchiveTask:

- reproducibleFileOrder: requests traversing files in a reproducible order.
- preserveFileTimestamps: determines whether to keep the original file timestamps in the archive.

In Gradle 9.0 and later, archive tasks default to reproducibleFileOrder = true and preserveFileTimestamps = false. If your project still supports older Gradle versions, configure them explicitly. [Gradle AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html) [Gradle Best Practices: Reproducible Archives](https://docs.gradle.org/current/userguide/best_practices_security.html)

### Groovy DSL

In build.gradle:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    reproducibleFileOrder = true
    preserveFileTimestamps = false
}
~~~

### Kotlin DSL

In build.gradle.kts:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}
~~~

This configuration applies to archive tasks such as Jar, Zip, War, and Tar.

Build:

~~~bash
./gradlew clean build
~~~

Inspect the JAR:

~~~bash
jar --list --file build/libs/app-1.0.0.jar
~~~

### Handling duplicate entries

If multiple source directories or dependencies contribute the same archive path, you need an explicit duplicate strategy.

You can configure the build to fail on duplicates:

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

For service descriptors that need to be merged, use a deterministic merge step and sort provider names if provider order does not carry priority semantics. If the order is significant at runtime, declare priority explicitly instead of relying on file traversal order.

## 9. Stabilizing Generated Resources and Service Descriptors

File order does not only appear at the packaging step. Many plugins or annotation processors generate resources before the JAR is created.

Common examples:

- META-INF/services.
- Configuration files merged from multiple sources.
- Resource indexes or asset manifests.
- Properties files generated from a Map.
- Lists of migrations or plugins.
- Generated source files.
- Lists of classes or packages discovered by scanning.

### Service provider files

A service descriptor might contain:

~~~text
com.acme.json.JsonFormatter
com.acme.xml.XmlFormatter
com.acme.text.TextFormatter
~~~

If the build collects providers using a HashSet, the order written to the file can vary. If the order does not carry priority semantics, sort provider class names before writing.

If the runtime selects providers in discovery order, do not arbitrarily sort to mask an unclear design. Define the priority order via separate configuration or metadata.

### Merging resources

When multiple modules provide the same resource path:

- Determine which file takes precedence.
- Or merge using a deterministic algorithm.
- Sort source files before merging.
- Normalize line endings and encoding.
- Detect duplicate entries.
- Do not let the completion order of parallel tasks determine the final content.

### Generated code

Annotation processors or code generators may iterate over a Map, Set, or filesystem. Sort inputs and outputs before generating sources. If the output includes timestamps, absolute paths, random identifiers, or build machine names, remove or normalize them.

## 10. Other Sources of Nondeterminism Beyond File Order

Stabilizing archive order is only one part of a reproducible build.

| Source | Example | How to control |
|---|---|---|
| Timestamp | ZIP entry, MANIFEST, pom.properties | Fixed output timestamp |
| File order | Directory traversal | Reproducible archive order |
| Manifest | Built-By, Build-Jdk, attribute order | Normalize manifest and pin toolchain |
| Compiler | Different JDK vendor/version | Pin JDK/toolchain |
| Generated source | HashMap iteration, current time | Sort inputs and remove volatile data |
| Environment | Locale, timezone, user, absolute path | Standardize environment |
| Dependency | Changing version or artifact | Lock/pin dependencies |
| Compression | Deflater or archiver version | Pin build tool and plugins |
| File permissions | Umask or filesystem | Configure permissions explicitly |
| Line endings | CRLF and LF | Enforce encoding/line endings |
| Randomness | UUID or random build ID | Use deterministic seed or remove |
| Native tool | Different compiler/linker version | Pin toolchain and target platform |

Apache Maven lists timestamps, username, manifest order, ZIP/JAR entry order, JDK version, Maven version, and line endings among the sources that can cause artifacts to vary. [Apache Maven: Reproducible/Verifiable Builds](https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971)

### Pinning the JDK and build tools

Even with the same target class file version, different compiler versions can produce different bytecode. Therefore, reproducible builds require pinning the JDK vendor/version and Maven/Gradle/plugin versions.

With Gradle, use a Java toolchain to select the compilation JDK. With Maven, pin the compiler plugin and release. Record the OS/architecture if the build includes native code or a runtime image.

### Do not write the current time into artifacts

Avoid entries such as:

~~~text
Built-At: 2026-11-10T21:00:00
Built-By: developer-name
Machine: workstation-01
~~~

if these values are not necessary artifact metadata. If build provenance is needed, store it in a separate attestation or metadata file with reproducible rules.

## 11. Verifying That Two Builds Are Identical

A simple reproducibility check:

1. Choose a commit or source snapshot.
2. Run a first clean build.
3. Save the artifact and its SHA-256.
4. Run a second clean build with the same configuration.
5. Compare SHA-256 hashes.
6. If the hashes differ, compare archive entry lists and metadata.
7. Use diffoscope or a similar tool to find the differences.

### Maven

~~~bash
mvn clean package
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\app-1.0.0.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum target/app-1.0.0.jar
~~~

Then run clean package again and compare the hashes.

### Gradle

~~~bash
./gradlew clean jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\build\libs\app-1.0.0.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum build/libs/app-1.0.0.jar
~~~

### Comparing entry order

~~~bash
jar --list --file app.jar
~~~

You can save the command output and compare the two lists. If the lists match but the hashes differ, inspect timestamps, manifest, compression, extra fields, and entry contents next.

### When checksums differ

Use diffoscope if available:

~~~bash
diffoscope before.jar after.jar
~~~

Or extract both archives into separate directories and compare:

- Entry names and order.
- Contents of each file.
- Timestamps.
- Manifest.
- pom.properties.
- ZIP extra fields.
- File permissions and metadata.
- Generated files.

Do not conclude reproducibility solely because the application behaves the same at runtime. Running correctly is correctness; byte-for-byte equality is a different requirement.

## 12. Java 17+ Lab: Sorting Files by Relative Path

Create a sample directory:

~~~text
classes/
├── zeta.txt
├── alpha.txt
├── middle.txt
└── nested/
    ├── omega.txt
    └── beta.txt
~~~

Use the StableFileOrderDemo program from section 4 to print the sorted list of files.

Compile:

~~~bash
javac --release 17 StableFileOrderDemo.java
~~~

Run:

~~~bash
java StableFileOrderDemo classes
~~~

Stdout:

~~~text
alpha.txt
middle.txt
nested/beta.txt
nested/omega.txt
zeta.txt
~~~

Try recreating the files in a different order, changing their modified timestamps, and running again. The output remains the same because the order is determined from normalized relative paths.

### Maven Lab: Building Twice

Minimal POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>repro-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

First build:

~~~bash
mvn clean package
~~~

Save the SHA-256, change the creation order of the resource files while keeping their contents identical, then run the second build:

~~~bash
mvn clean package
~~~

Compare the SHA-256 of both JARs. With the same JDK, plugins, and source contents, the outputs should match under proper reproducible configuration.

### Gradle Lab: Building Twice

In build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(AbstractArchiveTask).configureEach {
    reproducibleFileOrder = true
    preserveFileTimestamps = false
}
~~~

First build:

~~~bash
./gradlew clean jar
~~~

Save the SHA-256, change the creation order of the resource files while keeping their contents identical, then run:

~~~bash
./gradlew clean jar
~~~

Compare the hashes. If the artifacts differ, use jar --list and diffoscope to locate the source of variation.

## 13. Verification Results in the Practice Environment

On OpenJDK 24.0.2, Maven 3.9.12, and Gradle 9.2.1, two small sample projects were tested.

- Maven used maven-jar-plugin 3.4.2 and a fixed outputTimestamp. Two builds after reversing the creation order of resource files produced identical SHA-256 hashes.
- Gradle used reproducibleFileOrder = true and preserveFileTimestamps = false. Two builds produced identical SHA-256 hashes.
- jar --list showed the archive entries written into the JAR.
- The Java sorting demo compiled with javac --release 17 and printed relative paths in alphabetical order.
- Both Maven and Gradle JARs ran successfully and printed REPRODUCIBLE.

A specific SHA-256 only has meaning for the exact source, toolchain, and configuration of that run. When practicing, compute the hash of the artifact you built yourself.

## 14. Troubleshooting

### Hash changes while file contents are identical

Check entry order, timestamps, manifest, pom.properties, ZIP extra fields, and compression metadata. Use diffoscope or extract the archives to compare.

### Entry order changes between Windows and Linux

Do not use Files.walk(), listFiles(), or shell glob order as the packaging order. Normalize relative paths and sort with an explicit comparator, or enable the build tool's reproducibleFileOrder option.

### Gradle archives still differ

Check all archive tasks, including custom tasks and third-party plugins. Confirm preserveFileTimestamps=false and reproducibleFileOrder=true. Check generated files and the duplicate strategy.

### Maven JARs still differ

Check that maven-jar-plugin is version 3.2.0 or higher and that project.build.outputTimestamp has a stable value. Check plugins that create source JARs, shaded JARs, manifests, assemblies, or generated metadata.

### Duplicate resource file names

Set an explicit duplicate policy. For safe builds, fail immediately on unexpected duplicates. If merging is required, sort input sources and define the merge order.

### Service providers discovered in a different order

Do not use HashSet or direct directory traversal. Sort the provider list if order does not carry priority semantics. If priority matters, store priority in explicit configuration.

### Local build is stable but CI differs

Compare JDK, Maven/Gradle, plugin versions, locale, timezone, environment variables, OS, architecture, file permissions, and dependency resolution. Pin the toolchain and build dependencies.

### JAR runs but hashes do not match

Two artifacts can be functionally equivalent without being reproducible. Separate correctness checks from byte-for-byte equality checks.

## 15. CI Workflow for Stabilizing File Order

1. Pin JDK vendor/version and Maven/Gradle version.
2. Lock dependency and plugin versions.
3. Normalize relative paths and encoding.
4. Sort discovered files with a fixed comparator.
5. Handle duplicate entries with an explicit policy.
6. Sort generated resources and descriptors if order does not carry priority semantics.
7. Fix archive timestamps.
8. Use Maven/Gradle reproducible archive options.
9. Avoid metadata that depends on username, hostname, current time, or absolute paths.
10. Run clean builds in two independent workspaces.
11. Compare artifact SHA-256 hashes.
12. If hashes differ, inspect the entry list and use diffoscope.
13. Record the build environment, source revision, and checksums.
14. Release the artifact only after both correctness and reproducibility checks pass.

## 16. Checklist for Stabilizing File Order

- Do not rely on the return order of Files.list(), Files.walk(), or File.listFiles().
- Do not rely on HashMap/HashSet iteration order.
- Use relative paths instead of absolute paths.
- Normalize separators to / when creating archive entries.
- Use a locale-independent comparator.
- Define Unicode normalization and case policy if cross-platform builds are needed.
- Detect path collisions after normalization.
- Set an explicit duplicate entry policy.
- Sort generated sources, resources, and service descriptors.
- Fix timestamps in ZIP/JAR.
- Use Maven JAR Plugin 3.2.0 or higher and a stable outputTimestamp.
- For Gradle, enable reproducibleFileOrder and disable preserveFileTimestamps.
- Pin JDK, build tool, plugin, and dependency versions.
- Inspect the manifest and generated metadata.
- Compare SHA-256 after two clean builds.
- Use jar --list to inspect archive entry order.
- Use diffoscope when hashes differ.
- Distinguish correctness from byte-for-byte reproducibility.

## 17. Key Terminology

| Term | Meaning |
|---|---|
| Stable file order | Deterministic file processing order across builds |
| Reproducible build | A build where identical inputs produce a byte-for-byte identical artifact |
| Nondeterminism | Results depending on uncontrolled factors |
| Relative path | A path relative to a root directory |
| Archive entry | A file or directory stored inside a ZIP/JAR |
| Central directory | Entry metadata table in a ZIP archive |
| Timestamp normalization | Setting archive timestamps to a fixed value |
| File traversal | Walking a directory tree to find files |
| Duplicate entry | Multiple sources writing the same archive path |
| Manifest | JAR metadata in META-INF/MANIFEST.MF |
| outputTimestamp | Reproducible timestamp for archives created by Maven JAR Plugin |
| reproducibleFileOrder | Gradle property controlling file order in archives |
| preserveFileTimestamps | Gradle property preserving or stripping original timestamps |
| SOURCE_DATE_EPOCH | Input timestamp convention for reproducible builds |
| SHA-256 | Hash used to compare exact artifact contents |
| diffoscope | Tool for deep diff analysis between two artifacts |

Stabilizing file order starts with normalizing relative paths and sorting explicitly before packaging. Maven and Gradle already provide mechanisms for reproducible archives; configure timestamps, pin toolchains, control generated resources, and verify with SHA-256. Only when both file order and metadata are controlled can the same source produce identical artifacts across multiple builds.

## References

- Apache Maven — Reproducible/Verifiable Builds: https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971
- Apache Maven — Maven JAR Plugin: https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html
- Apache Maven — MJAR-263: https://issues.apache.org/jira/browse/MJAR-263
- Gradle — Best Practices for Security and Reproducible Builds: https://docs.gradle.org/current/userguide/best_practices_security.html
- Gradle — AbstractArchiveTask: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html
- Oracle JDK 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- OpenJDK — Reproducible Builds: https://reproducible-builds.org/
