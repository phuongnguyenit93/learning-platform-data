# Stabilizing Timestamps in Java Builds

## 1. What is a stable timestamp?

During a build process, timestamps may be written into file metadata inside a JAR/ZIP, the manifest, generated resources, build-info files, or build tool logs. If the timestamp is taken directly from the build machine's clock, two builds of the same source revision can produce different artifacts simply because they were run at different times.

Stabilizing timestamps means setting a deterministic time value for the metadata to be packaged, so that the same source and the same configuration can produce identical artifacts across multiple builds.

Common goals:

- Rebuilt JARs have the same timestamp for every entry.
- Builds on two different machines do not drift in timestamps due to timezone or filesystem mtime.
- The SHA-256 hash of the artifact remains unchanged when only the build time changes.
- Timestamps used in the manifest or generated resources reflect a stable point in time of the source revision.
- CI can independently compare artifacts across runs.

Stable timestamps are one part of reproducible builds. Normalizing time alone is not enough to guarantee that the entire artifact is identical; file order, compiler, dependencies, manifest content, and generated resources must also be stable.

## 2. Distinguishing types of timestamps

Not every timestamp affects the hash of a JAR in the same way.

| Time type | Where stored | Directly affects JAR bytes? |
|---|---|---|
| Source file mtime | Filesystem of `.java` source | Not automatically; the compiler typically does not copy mtime into bytecode. |
| Class file mtime | Filesystem of `.class` | No, unless the build tool includes that mtime in the archive. |
| Archive entry timestamp | ZIP metadata of each file inside the JAR | Yes; it is part of the archive. |
| JAR file mtime | Filesystem of the `.jar` file after creation | Not part of the JAR's byte content, so it does not affect the file's SHA-256. |
| Embedded build timestamp | Manifest, properties, JSON, generated source/resource | Yes; the timestamp is actual content of the artifact. |
| Build log timestamp | Console or log file outside the artifact | No, unless the log is packaged into the artifact. |

`jar --list --verbose` displays the timestamp of each entry inside the archive. This is the timestamp that must be normalized if you want byte-for-byte identical JARs.

Meanwhile, `Get-Item app.jar | Select-Object LastWriteTime` displays the JAR file's timestamp on the filesystem. This value can differ after each build while the hash of the JAR's content remains completely identical.

## 3. How timestamps cause artifacts to change

A JAR is a ZIP-based archive. Each entry has metadata, including its modification time. If two JAR creation runs write the same class file but use different times, the timestamp fields in the ZIP differ and the hash of the entire file also differs.

Example:

~~~text
Build 1:
com/example/Main.class  2026-11-10 20:00:00

Build 2:
com/example/Main.class  2026-11-10 21:00:00
~~~

The contents of `Main.class` may be identical, but the archive metadata differs.

Therefore, simply running `javac` with the same source does not guarantee identical JARs. You must normalize timestamps at the packaging step and check plugins that generate additional metadata.

## 4. SOURCE_DATE_EPOCH

`SOURCE_DATE_EPOCH` is a common environment convention in reproducible builds. Its value is the number of Unix seconds since `1970-01-01T00:00:00Z`.

Example:

~~~bash
SOURCE_DATE_EPOCH=1577836800
~~~

The value above corresponds to:

~~~text
2020-01-01T00:00:00Z
~~~

Use a stable value for the same source revision. A common approach is to take the committer timestamp of the Git commit:

~~~bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct HEAD)"
~~~

On PowerShell:

~~~powershell
$env:SOURCE_DATE_EPOCH = (git log -1 --format=%ct HEAD).Trim()
~~~

`%ct` returns the committer date as Unix seconds. If two builds use the same commit, this value does not depend on the clock of the CI runner machine.

Do not set `SOURCE_DATE_EPOCH` to the current time such as `date +%s` on every build; doing so produces a different timestamp on every run and breaks reproducibility.

If the pipeline does not have Git metadata, you can pass an epoch stored in release metadata or the source archive.

## 5. Setting timestamps when creating a JAR with jar

The JDK provides the `--date` option for the `jar` command:

~~~bash
jar --create --date=2020-01-01T00:00:00Z --file build/app.jar -C build/classes .
~~~

`--date` accepts an ISO-8601 extended offset date-time timestamp. You should specify the timezone explicitly, for example the `Z` suffix for UTC.

You can use a timestamp derived from `SOURCE_DATE_EPOCH`. On PowerShell:

~~~powershell
$timestamp = [DateTimeOffset]::FromUnixTimeSeconds(
    [long]$env:SOURCE_DATE_EPOCH
).UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")

jar --create "--date=$timestamp" --file build/app.jar -C build/classes .
~~~

On a shell with GNU `date`:

~~~bash
timestamp="$(date -u -d "@$SOURCE_DATE_EPOCH" +'%Y-%m-%dT%H:%M:%SZ')"

jar --create "--date=$timestamp" --file build/app.jar -C build/classes .
~~~

`jar` does not automatically read `SOURCE_DATE_EPOCH`. Simply exporting the environment variable and invoking `jar` does not change entry timestamps; you must convert the epoch to an ISO timestamp and pass it via `--date`.

`--date` applies when creating or updating an archive. It normalizes entry times, but does not automatically guarantee that file order, manifest content, or generated resource content are also stable.

## 6. Keeping entry order stable when calling jar

Two JARs with the same entries and the same timestamps can still have different hashes if the order of entries in the archive differs.

When calling `jar` directly, pass files in a deterministic order. Example:

~~~bash
jar --create \
  --date=2020-01-01T00:00:00Z \
  --file=build/app.jar \
  -C build/classes com/example/Greeting.class \
  -C build/classes com/example/Main.class
~~~

For large projects, generate a sorted, stable list of files and pass it via an `@file` argument file. Do not rely on arbitrary directory traversal order from a script or filesystem.

Inspect the archive:

~~~bash
jar --list --verbose --file build/app.jar
~~~

The output shows the timestamps and entry paths in the JAR. If you need to investigate differences, extract both archives and compare the entry list, metadata, and contents of each file.

## 7. Stabilizing timestamps in Maven

Maven uses the `project.build.outputTimestamp` property to pass a stable timestamp to plugins that support reproducible archives.

Set a fixed timestamp in `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2020-01-01T00:00:00Z</project.build.outputTimestamp>
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

`maven-jar-plugin` supports `outputTimestamp` starting from version 3.2.0; by default, this parameter takes its value from `${project.build.outputTimestamp}`.

Build:

~~~bash
mvn -B clean package
~~~

Maven Archiver uses this timestamp for entries packaged in the JAR. When using other plugins such as shade, assembly, or plugins that create additional archives, verify that those plugins support reproducible output and receive the same timestamp.

Do not configure only the JAR plugin and conclude that all artifacts in a multi-module build are reproducible. Each plugin that creates an archive or generated file must be checked individually.

## 8. Passing SOURCE_DATE_EPOCH into Maven

You can take the timestamp from the CI environment instead of hard-coding it in the POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>${env.SOURCE_DATE_EPOCH}</project.build.outputTimestamp>
</properties>
~~~

CI sets the variable before invoking Maven:

~~~bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct HEAD)"
mvn -B clean package
~~~

Maven JAR Plugin accepts `outputTimestamp` values as ISO-8601 strings or integer Unix seconds. Therefore, the epoch value from `SOURCE_DATE_EPOCH` can be passed directly.

You can pass it via the command line:

~~~bash
mvn -B "-Dproject.build.outputTimestamp=$SOURCE_DATE_EPOCH" clean package
~~~

If the environment variable is not set, the property `${env.SOURCE_DATE_EPOCH}` may fail to resolve to a valid timestamp. Ensure CI always provides the variable before the package step or use an intentional default value.

## 9. Stabilizing archive timestamps in Gradle

Gradle provides two properties for archive tasks:

- `preserveFileTimestamps`: whether to preserve the mtime of source files inside the archive.
- `reproducibleFileOrder`: whether to traverse files in a stable order.

Explicit configuration for JAR:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.withType(Jar).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

When `preserveFileTimestamps = false`, Gradle normalizes entry timestamps instead of preserving file modification times from the filesystem. When `reproducibleFileOrder = true`, Gradle traverses files in the archive in a stable order, independent of the order returned by the filesystem.

Starting from Gradle 9.0, these two properties default to `false` and `true` respectively for archive tasks. It is still good practice to declare them explicitly in the build file so the project's intent is easy to review and does not depend on older versions' defaults.

Run:

~~~bash
gradle clean jar
~~~

Inspect:

~~~bash
jar --list --verbose --file build/libs/gradle-1.0.0.jar
~~~

Gradle uses a normalized ZIP-compatible timestamp for entries. This configuration prioritizes byte-for-byte reproducible archives; it does not automatically select the Git commit timestamp.

## 10. Do not embed the current build time in the manifest

Even when archive entries are normalized, JARs can still differ if the manifest contains a dynamic timestamp.

Example unsuitable for reproducible builds:

~~~xml
<manifestEntries>
    <Build-Time>${maven.build.timestamp}</Build-Time>
</manifestEntries>
~~~

`maven.build.timestamp` changes depending on when Maven runs. Because the manifest is inside the JAR, that value changes the artifact's content.

If time metadata is needed, use the same stable timestamp source:

~~~xml
<manifestEntries>
    <Build-Revision-Time>${project.build.outputTimestamp}</Build-Revision-Time>
</manifestEntries>
~~~

Distinguish between ISO-8601 values and epoch seconds. If the manifest requires a human-readable format, convert the epoch to ISO UTC in a deterministic step before placing it in the manifest.

With Gradle, avoid generating manifest entries from `new Date()` or `System.currentTimeMillis()`. If you need to record a revision time, obtain the value from source revision metadata and ensure it does not change across builds of the same revision.

## 11. Generated resources and build-info files

Some plugins generate `build-info.properties`, `git.properties`, version files, or JSON containing the build time. These files are also packaged into the JAR.

Example resource:

~~~properties
build.version=1.0.0
build.time=2026-11-10T21:00:00Z
build.revision=abc123
~~~

If `build.time` is taken from the current clock, two builds of the same commit will generate different resources.

To stabilize:

- Use `SOURCE_DATE_EPOCH` or a pinned commit timestamp.
- Normalize the timezone to UTC.
- Do not record milliseconds/nanoseconds if the timestamp source only has second-level precision.
- Configure the build-info generating plugin to use the same timestamp.
- Inspect the generated file after the build and compare hashes.
- Do not include CI job time or deployment time in build artifacts unless necessary.

Runtime timestamps such as application startup time can still be logged when the application runs. What to avoid is writing build execution time into artifact contents when you want the artifact to be reproducible.

## 12. Timezones and timestamp formats

A point in time should have a consistent representation across all build machines.

Recommended:

~~~text
2020-01-01T00:00:00Z
~~~

`Z` denotes UTC. If another offset is used, specify the offset explicitly:

~~~text
2020-01-01T07:00:00+07:00
~~~

Both representations above refer to the same instant. Do not use date-time strings without a timezone such as `2020-01-01 00:00:00`, because interpretation can depend on the machine's default timezone.

Factors to control:

- Timezone of the JVM and operating system.
- Locale when formatting date-time values.
- Consistent ISO-8601 format.
- Precision of timestamps generated from source metadata.
- How each plugin converts timestamps into ZIP metadata.

`jar --list --verbose` displays times using the formatter of the running environment; when comparing across machines, consider the displayed timezone and the input timestamp value.

## 13. .class timestamps and incremental compilation

`javac` does not embed the current compile time into `.class` bytecode as a separate timestamp field. Given the same source, compiler version, and options, changing only the filesystem mtime of a `.java` file does not necessarily change the class file content.

However, mtime is still used by build tools to decide whether recompilation is needed. Therefore:

- Do not modify source file mtime to force the build system to skip compilation.
- Do not use old class output as proof for a new build.
- When verifying reproducibility, you can clean and rebuild from the same source.
- Compare bytecode by hash after using the same JDK and compiler options.
- Keep the compiler JDK and `--release` consistent.

Example:

~~~bash
javac --release 17 -g -d build/classes src/main/java/com/example/Main.java
~~~

Changing the source mtime can cause the compiler to rerun, but if the source content and compiler inputs are unchanged, the class file can still be identical.

## 14. Inspecting timestamps in a JAR

List entries and timestamps:

~~~bash
jar --list --verbose --file build/app.jar
~~~

To view the manifest:

~~~bash
jar --extract --file build/app.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

On PowerShell:

~~~powershell
jar --extract --file build/app.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
~~~

Check hash:

~~~bash
sha256sum build/app.jar
~~~

On PowerShell:

~~~powershell
Get-FileHash build/app.jar -Algorithm SHA256
~~~

Comparison workflow:

1. Build the artifact the first time.
2. Save the SHA-256.
3. Change the mtime of a source file without changing the source content.
4. Clean and rebuild using the same toolchain/configuration.
5. Compare the SHA-256.
6. If the hashes differ, check entry timestamps, entry order, manifest, generated resources, and the contents of each file.

Identical hashes are strong evidence that two files have the same bytes. Different hashes must be investigated; do not assume timestamps are the only cause.

## 15. Java 17 demo to verify artifacts

Create the file `src/main/java/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Stable timestamp build");
    }
}
~~~

Compile:

~~~bash
javac --release 17 -g -d build/classes src/main/java/com/example/Main.java
~~~

Create the JAR with a fixed timestamp:

~~~bash
jar --create --date=2020-01-01T00:00:00Z --file build/app.jar -C build/classes .
~~~

Run:

~~~bash
java -cp build/app.jar com.example.Main
~~~

Exact stdout:

~~~text
Stable timestamp build
~~~

Create two JARs in two separate runs, keeping class contents unchanged while changing the filesystem mtime of the class file. If both runs use the same `--date`, the same entry list, and the same file order, the hashes of both JARs must be identical.

If `--date` is omitted, entry timestamps may be taken from the input files' mtime and cause the hash to change.

## 16. Maven Lab: building twice with the same SOURCE_DATE_EPOCH

Minimal `pom.xml` example:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>stable-timestamp-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>${env.SOURCE_DATE_EPOCH}</project.build.outputTimestamp>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
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

Run on PowerShell:

~~~powershell
$env:SOURCE_DATE_EPOCH = "1577836800"
mvn -B clean package

Get-FileHash target/stable-timestamp-demo-1.0.0.jar -Algorithm SHA256

# Change the source mtime while keeping the content unchanged.
(Get-Item src/main/java/com/example/Main.java).LastWriteTimeUtc =
    [DateTime]::UtcNow.AddDays(-2)

mvn -B clean package
Get-FileHash target/stable-timestamp-demo-1.0.0.jar -Algorithm SHA256
~~~

The two hashes must be identical if the other plugins and build contents are also reproducible. Check entry timestamps:

~~~bash
jar --list --verbose --file target/stable-timestamp-demo-1.0.0.jar
~~~

In tests with JDK 24.0.2, Maven 3.9.12, and Maven JAR Plugin 3.4.2, `SOURCE_DATE_EPOCH=1577836800` produces entry timestamps corresponding to `2020-01-01T00:00:00Z`. Two `clean package` runs after changing source mtime produce JARs with identical SHA-256 hashes.

## 17. Gradle Lab: normalizing timestamps and entry order

Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.withType(Jar).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Build:

~~~bash
gradle clean jar
~~~

Check hash:

~~~bash
sha256sum build/libs/gradle-1.0.0.jar
~~~

Change the source mtime and rebuild:

~~~bash
gradle clean jar
sha256sum build/libs/gradle-1.0.0.jar
~~~

The two hashes must be identical if the source content and all other inputs remain unchanged.

In tests with Gradle 9.2.1, archive entries are normalized to the ZIP-compatible timestamp `1980-02-01`; two `clean jar` runs after changing source mtime produce JARs with identical SHA-256 hashes. Gradle still prints task execution durations in the console log; those log lines are not included in the JAR.

## 18. Why can hashes still differ even when timestamps are stable?

Timestamps are only one part of metadata. Other causes include:

- Files are added to the archive in a different order.
- The manifest contains `Build-Time`, `Created-By`, or dynamic metadata.
- A plugin generates source/resources containing the current time.
- Different compiler JDK or vendor.
- Dependencies resolve to different versions.
- Resource filtering writes absolute paths or usernames.
- Different newlines, encoding, locale, or timezone.
- An archive plugin does not support reproducible output.
- Build-info content contains changing commit metadata or build numbers.
- Archives have different file permissions or metadata across operating systems.

If the hashes differ, compare the extracted archives or use a tool like `diffoscope` to find the differing entry. Identify the plugin that produced that entry and configure reproducible output for that plugin.

Do not fix timestamps by running `touch` on the final JAR file. That only changes the file's mtime on the filesystem; it does not modify entry timestamps inside the archive and does not make the JAR bytes reproducible.

## 19. Common mistakes when stabilizing timestamps

| Symptom | Cause | Solution |
|---|---|---|
| Two JARs have different hashes despite identical classes | ZIP entry timestamps differ. | Use `jar --date`, Maven `project.build.outputTimestamp`, or Gradle `preserveFileTimestamps=false`. |
| Exported `SOURCE_DATE_EPOCH` but JAR CLI still uses current time | `jar` does not read this variable automatically. | Convert the epoch to ISO UTC and pass `--date`. |
| Maven still produces different JARs | Plugin does not support output timestamps or manifest/resources have dynamic times. | Pin plugins that support reproducible builds and inspect generated files. |
| Gradle JAR changes with file order | Archive task does not have reproducible order enabled. | Set `reproducibleFileOrder=true`. |
| Displayed timestamps are shifted by hours | Input timezone or display timezone differs. | Use UTC `Z` and standardize the timezone when comparing. |
| Timestamp in manifest changes | Using `${maven.build.timestamp}` or `new Date()`. | Use a timestamp from the source revision or omit the time field. |
| Hash differs even though entry times are identical | Content, entry order, permissions, or manifest differ. | Compare each entry and check archive-creating plugins. |
| CI lacks SOURCE_DATE_EPOCH | Pipeline does not pass commit metadata. | Set the variable from the Git commit or pass the epoch from the release process. |
| Local build passes but CI differs | Different JDK/toolchain, plugins, or dependencies. | Pin toolchain, plugin versions, and dependencies. |
| Archive has entries before 1980 | Timestamp is outside the ZIP-compatible range of some archive tasks. | Choose a valid, stable, shared timestamp. |

## 20. Workflow for normalizing timestamps in CI

1. Choose a stable timestamp for the source revision, typically the Git committer timestamp.
2. Export `SOURCE_DATE_EPOCH` as UTC Unix seconds.
3. Identify which archive tools create JAR/ZIP/TAR files in the build.
4. For `jar`, convert the epoch to ISO UTC and pass `--date`.
5. For Maven, configure `project.build.outputTimestamp` and use plugins that support reproducible output.
6. For Gradle, set `preserveFileTimestamps=false` and `reproducibleFileOrder=true`.
7. Remove dynamic build times from manifests and generated resources.
8. Keep compiler, dependencies, locale, encoding, and file order stable.
9. Perform two clean builds from the same source revision.
10. Compare the artifact SHA-256 hashes.
11. If the hashes differ, inspect entry timestamps and compare the contents of each file.
12. Record the hash, toolchain version, and source revision in the build report.

You can check hashes on Linux/macOS with `sha256sum`, or on PowerShell with `Get-FileHash -Algorithm SHA256`. Compare the artifact files themselves; do not use filesystem mtime as sole proof.

## 21. References

- [The jar Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Configuring for Reproducible Builds — Maven](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Gradle AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle Jar Task](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [SOURCE_DATE_EPOCH specification](https://reproducible-builds.org/docs/source-date-epoch/)

Stabilizing timestamps eliminates a common source of differences across Java builds. Use `SOURCE_DATE_EPOCH` as a fixed time source, pass `--date` to `jar`, configure `project.build.outputTimestamp` in Maven, and disable preserving file timestamps in Gradle. Then compare SHA-256 hashes to confirm that the artifacts are truly identical.