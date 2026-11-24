# Stabilizing Timestamps with Maven's project.build.outputTimestamp

## 1. Why Do Two Functionally Identical JARs Have Different SHA-256 Hashes?

You check out the exact same commit of a Spring Boot project, run Maven **clean verify** twice, and both return **BUILD SUCCESS**. Source code, tests, and Java behavior did not change, yet the SHA-256 hash of **target/app.jar** differs. One cause is that **entry timestamp metadata inside the JAR/ZIP** changed during packaging.

A JAR contains not only Java bytecode, but many entries such as:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/repro/ReproApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/spring-boot-....jar
BOOT-INF/lib/...
~~~

ZIP entries carry timestamps. If an archive is created with timestamps taken from build time, a JAR built today can differ from one built tomorrow by a few bytes even when source is unchanged. When releasing artifacts, this complicates verifying “was this binary produced from the published source and tools?”.

Apache Maven supports **Reproducible Builds**. Part of that support is the Maven property:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

Maven plugins supporting reproducible archives use this value as a stable timestamp for **archive entries**. Specifically:
- **maven-jar-plugin:jar** supports the **outputTimestamp** parameter since version **3.2.0**.
- **spring-boot-maven-plugin:repackage** supports the **outputTimestamp** parameter since version **2.3.0**, defaulting to the Maven property above.
- Plugins producing source JARs, WARs, assemblies, Javadoc, and other artifacts may need separate inspection.

**Fixing timestamps is not a sufficient condition for all bytes to match**. It addresses only one class of nondeterminism. Dependencies, JDK, Maven plugins, generated sources, resources, manifests, or environment can still cause differences.

This lesson focuses on **Maven's project.build.outputTimestamp** in a Spring Boot context, showing how to set an intentional timestamp, build and compare two JARs by SHA-256, diagnose remaining differences, and integrate the setup into release/CI.

## 2. Understanding Reproducible Builds Properly

**Reproducible build** means that given the same source code, build environment, and published build instructions, target artifacts can be recreated **byte-for-byte identically**. This definition is stronger than “runs properly,” yet does not imply the software is secure or bug-free.

| Concept | What does it verify? | What does it NOT prove? |
| --- | --- | --- |
| **Functional equivalence** | Two JARs behave identically in tests | Does not prove two JARs share identical bytes |
| **Local bit-for-bit reproducibility** | Two clean builds in the same environment produce JARs with identical SHA-256 | Does not prove a third machine reproduces identical bytes |
| **Independent reproducibility** | Another party using published source/toolchain reproduces the exact release artifact bytes | Does not replace audits or security checks |
| **Supply-chain provenance** | Origin, builder, workflow, and inputs are recorded | Does not automatically make vulnerable code safe |

The target artifact set must be stated explicitly: **main Boot JAR**, plain JAR, WAR, sources JAR, javadoc JAR, published POM, buildinfo, SBOM, or image. Matching main JARs do not automatically guarantee the **entire release package** is reproducible.

### 2.1. Filesystem Timestamps Are Not ZIP Entry Timestamps

When Maven produces **target/repro-demo-1.0.0.jar**, the operating system assigns an **mtime** to the JAR file itself at the current time. On a second build, the file's mtime will differ from the first.

However, **project.build.outputTimestamp** targets metadata **inside the archive** written by supporting plugins. It **does not promise** to freeze the outer JAR file's filesystem mtime. Therefore:
- Never use **ls -l** to judge reproducibility.
- Never use upload timestamps in an artifact repository.
- Use **sha256sum / Get-FileHash / cmp** to compare full binary contents.

### 2.2. Timestamps Written Inside File Contents Are a Different Problem

Suppose a plugin/resource generator writes this value into **application.properties**:

~~~properties
app.build.at=2026-11-09T10:37:42+07:00
~~~

If the next build writes a fresh timestamp, the resource contents differ, changing the JAR hash even when all ZIP entry timestamps are fixed. Likewise, **META-INF/build-info.properties**, generated Java sources, manifests, or JSON generated using the current clock can destabilize output.

Hence you must distinguish:

| Time type | Where does it live? | Handled directly by project.build.outputTimestamp? |
| --- | --- | --- |
| ZIP/JAR entry metadata | Archive entries created by supporting plugins | **Yes** |
| Filesystem mtime | target/*.jar on disk | **Not guaranteed** |
| Values inside files | Properties, manifest, Java sources, resources | **Depends on whether the plugin/generator uses a stable value** |
| CI job log timestamps | Runner logs and monitoring | **No** |
| Runtime startup/deploy timestamps | Running process | **No** |

There is no need to strip timestamps from runtime logs; they aid debugging and do not normally live inside release artifacts.

## 3. How Does project.build.outputTimestamp Work?

### 3.1. Configuring the Property in the POM

Place it under **properties**:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Maven plugins whose **outputTimestamp** parameter defaults to this property use a stable anchor when writing archive entries. If a project has a parent POM, the property can be inherited or overridden by a child, profile, or user property.

**This is a Maven property, not a Spring runtime property.** Do not put it in **application.properties** expecting the Maven JAR Plugin to read it.

### 3.2. Valid Formats

Two common forms:

- **ISO 8601 extended offset date-time**, preferably using UTC marker **Z** for consistency.
- **Integer seconds since the Unix epoch**, matching the **SOURCE_DATE_EPOCH** convention.

Equivalent examples:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

and:

~~~xml
<project.build.outputTimestamp>1782864000</project.build.outputTimestamp>
~~~

**1782864000** is the number of **seconds** since the Unix epoch for the UTC instant above. Do not pass epoch milliseconds (e.g., **1782864000000**), as plugins expect seconds and may error or misinterpret it.

An ISO 8601 string like **2026-07-01T07:00:00+07:00** represents the same instant, yet when multiple people edit POMs, standardizing on UTC `Z` avoids offset confusion.

### 3.3. Where Should the Value Come From?

Every build of the **same source release** must receive the **same output timestamp**. Three strategies exist:

1. **A static timestamp committed in the POM** alongside the release version. Easy to learn and audit.
2. **Timestamp of a pinned Git commit/tag**, derived deterministically from Git history and passed via the release pipeline.
3. **Release metadata stored by CI**, reused identically by every rebuilder replicating the release artifact.

Avoid using the **actual wall-clock time of each Maven invocation**. Two builds of the same source at 09:00 and 10:00 would get different timestamps, defeating reproducibility.

### 3.4. Do Not Confuse the Maven Property with SOURCE_DATE_EPOCH

**SOURCE_DATE_EPOCH** is a widespread environment variable convention in reproducible builds carrying seconds since the epoch. Whether Maven or a given plugin **reads this variable automatically** depends on the plugin version and implementation.

For consistent behavior across versions, **configure project.build.outputTimestamp explicitly** or pass the epoch from CI as a Maven user property, then verify the **effective property**.

Syntax for passing an epoch from a Unix environment once the variable is controlled:

~~~bash
./mvnw -B -ntp   "-Dproject.build.outputTimestamp=$SOURCE_DATE_EPOCH"   clean verify
~~~

This assumes **SOURCE_DATE_EPOCH** is properly set in seconds, non-empty, and stable for the same source. Never assume the CI environment variable always exists.

### 3.5. What Do Maven Core and Maven Plugins Support?

Current Maven documentation notes that **Maven 3.10.0** and **4.0.0-beta-5** enable reproducible builds mode by default in supported cases. However:
- Not every project runs those Maven versions.
- Older or third-party plugins may ignore outputTimestamp.
- Generated resources may record current time themselves.
- Dependencies/repositories/JDKs can still differ.

Therefore **setting the property explicitly** and **comparing real artifacts** remains sound practice. Never assume a newer Maven version automatically makes every custom plugin deterministic.

Documentation: https://maven.apache.org/guides/mini/guide-reproducible-builds.html

## 4. Why Does Spring Boot Repackage Need the Same Timestamp?

The Spring Boot Maven workflow typically follows these stages:

~~~text
src/main/java + src/main/resources
             |
             v
compile + process-resources
             |
             v
maven-jar-plugin:jar -> ordinary JAR
             |
             v
spring-boot-maven-plugin:repackage
             |
             v
Executable Spring Boot JAR
  BOOT-INF/classes
  BOOT-INF/lib/*.jar
  Spring Boot Loader + manifest
~~~

The **repackage** step creates the Boot layout, embeds dependencies under **BOOT-INF/lib**, and rewrites the archive. If only the JAR Plugin has stable timestamps while the Boot Plugin writes unstable metadata, the **final executable JAR** will still produce different hashes.

Spring Boot Maven Plugin **repackage** defines the parameter:

~~~text
outputTimestamp: String
default = project.build.outputTimestamp
~~~

With supporting plugins and the property set, you need not repeat `outputTimestamp` everywhere just to share the value. Still, if the POM customizes plugin configs, parents/profiles, archive layouts, or classifiers, verify the effective POM and real artifacts.

**Nested JARs remain an input source.** If a SNAPSHOT dependency is republished under the same coordinate with different bytes, the final Boot JAR cannot match merely because **outer archive entry** timestamps are stable.

### 4.1. When Should You Configure outputTimestamp on the Plugin Directly?

For illustration inside **build/plugins**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
    </configuration>
</plugin>
~~~

This is an **auxiliary configuration snippet** illustrating the plugin parameter, not a complete POM. With current Spring Boot Maven Plugin defaults, this extra line on the plugin is **usually unnecessary**; the project property alone suffices. If the release also builds WAR/source/assembly JARs, verify **every** archive-producing plugin rather than adjusting Boot repackage alone.

Documentation: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html

## 5. A Java 17 Example You Can Build and Run with Spring Boot

Use a project without a database or HTTP server to avoid external sources of variation. This technical example uses Java **17** and Spring Boot **3.5.16**; these are concrete illustrative versions, not a default recommendation for every new project at any point in time.

### 5.1. Project Structure

~~~text
repro-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/repro/
    │   │   ├── ReproApplication.java
    │   │   └── StableMessage.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/repro/
            └── StableMessageTest.java
~~~

The Maven Wrapper must be generated via Spring Initializr or the Maven Wrapper plugin; merely creating `pom.xml` will not generate **mvnw** files. If no Wrapper exists yet, use a compatible local Maven and substitute **mvn** for **./mvnw**; to verify reproducibility, still pin the Maven version.

### 5.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Explanation of key sections:**
- **spring-boot-starter-parent** manages versions of Spring Boot dependencies and several Maven plugins.
- **java.version=17** sets the Java compilation level per parent convention.
- **project.build.outputTimestamp** sets a stable archive entry timestamp.
- **spring-boot-starter** brings in Spring Boot core without creating a web endpoint or opening port 8080.
- **spring-boot-starter-test** provides JUnit and test utilities.
- **spring-boot-maven-plugin** builds the executable archive via **repackage** using the execution configured by the parent.

You do not need to declare a Maven Jar Plugin version in a starter-parent example when the parent already provides a compatible version. With a corporate parent POM, verify dependency/plugin management and actual executions in the effective POM.

### 5.3. Java Helper Returning Stable Data

File **src/main/java/com/example/repro/StableMessage.java**:

~~~java
package com.example.repro;

public final class StableMessage {
    private StableMessage() {
    }

    public static String text() {
        return "repro-build-ok";
    }
}
~~~

### 5.4. Main Application Class

File **src/main/java/com/example/repro/ReproApplication.java**:

~~~java
package com.example.repro;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReproApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReproApplication.class, args);
        System.out.println(StableMessage.text());
    }
}
~~~

Spring Boot emits startup logs that vary by run time, yet after context initialization, the program prints a dedicated line with **exact stdout**:

~~~text
repro-build-ok
~~~

Do not try to freeze runtime log timestamps with **outputTimestamp**; those reflect live execution time, not archive metadata.

### 5.5. application.properties

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=repro-demo
~~~

This is a static resource that does not generate a build timestamp. If you use Maven Resources Plugin filtering to substitute time tokens, inspect the copied contents in **target/classes** and decide whether that value can be reproduced.

### 5.6. JUnit Test

File **src/test/java/com/example/repro/StableMessageTest.java**:

~~~java
package com.example.repro;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StableMessageTest {
    @Test
    void textIsStable() {
        assertEquals("repro-build-ok", StableMessage.text());
    }
}
~~~

Tests run when Maven Surefire is configured via the parent and starter-test. **Never pass -DskipTests** in one build and compare against another build with tests when evaluating two release builds: the verification scope has changed.

### 5.7. Building and Running the Artifact

On Linux/macOS:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
java -jar target/repro-demo-1.0.0.jar
~~~

On Windows use **mvnw.cmd** or **.\mvnw.cmd** depending on your shell. **clean verify** runs compile/test/package phases and the project's repackage goal. The artifact path **target/repro-demo-1.0.0.jar** matches the POM's group/artifact/version; custom classifiers or output names change the actual path.

Individual runs differ in execution timing and logs, while JAR bytes remain stable when all inputs and plugin outputs are deterministic.

## 6. Verifying Maven Actually Reads the Timestamp

### 6.1. Reading the Property with Maven Help Plugin

~~~bash
./mvnw -q help:evaluate -Dexpression=project.build.outputTimestamp -DforceStdout
~~~

For the sample project, the expected value is:

~~~text
2026-07-01T00:00:00Z
~~~

Maven Help Plugin may need to download on first run; if warnings or other logs appear, locate the property value rather than assuming the entire console consists of a single line.

If the value differs from expectations, inspect the effective POM:

~~~bash
./mvnw help:effective-pom
~~~

Check the property, active profiles, and plugin versions. **effective-pom** shows the merged configuration from parents/profiles, yet you must still inspect real artifacts to confirm behavior.

### 6.2. Inspecting outputTimestamp on Plugins

~~~bash
./mvnw help:describe -Dplugin=org.apache.maven.plugins:maven-jar-plugin -Dgoal=jar -Ddetail=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Maven Jar Plugin from **3.2.0** and Spring Boot repackage from **2.3.0** provide the **outputTimestamp** parameter for reproducible archive entries.

If the project uses **maven-war-plugin**, **maven-source-plugin**, **maven-assembly-plugin**, **maven-shade-plugin**, custom packaging, or signing plugins, inspect each plugin individually. Never treat seeing the property in the POM as proof every output of every plugin will be deterministic.

## 7. Essential Workflow: Build Twice, Compare Exact Hashes

### 7.1. Why Copy the JAR Outside target?

Maven's **clean** goal deletes **target/**. If you build once and immediately run `clean` a second time without copying the reference file, the first artifact is gone and you have no two real binaries to compare.

Verification flow:

~~~text
Pin source commit + Maven/JDK + dependency versions
                           |
                           v
                    clean verify #1
                           |
                           v
              Copy first JAR outside target
                           |
                           v
                    clean verify #2
                           |
                           v
              Copy second JAR outside target
                           |
                           v
                 SHA-256 + byte compare
                     |           |
                   PASS         FAIL
                     |           |
           Independent check  Inspect contents/ZIP metadata
~~~

When comparing, do not add or remove test flags between runs, edit the POM, or change dependency sources. **Both the first and second builds must succeed** before evaluating the comparison.

### 7.2. Bash Script for Linux

Create **compare-repro.sh** at the project root:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

artifact="target/repro-demo-1.0.0.jar"
result_dir="$(mktemp -d)"
echo "Comparison outputs are in $result_dir"

echo "First clean build"
./mvnw -B -ntp clean verify
cp "$artifact" "$result_dir/first.jar"

echo "Second clean build"
./mvnw -B -ntp clean verify
cp "$artifact" "$result_dir/second.jar"

echo "SHA-256 of both artifacts:"
sha256sum "$result_dir/first.jar" "$result_dir/second.jar"

if cmp -s "$result_dir/first.jar" "$result_dir/second.jar"; then
    echo "PASS: artifacts are byte-for-byte identical"
else
    echo "FAIL: artifacts differ; inspect both copies"
    exit 1
fi
~~~

Run in a workspace authorized for building/cleaning:

~~~bash
chmod +x compare-repro.sh
./compare-repro.sh
~~~

On the success branch, the script prints the exact conclusion line:

~~~text
PASS: artifacts are byte-for-byte identical
~~~

Actual SHA-256 values **are not hardcoded in this lesson** because they depend on exact versions, toolchains, and artifact bytes. The script leaves **result_dir** intact so you retain both references on FAIL; when cleaning up, delete only the verified temporary directory.

**Script prerequisites:**
- Bash, Maven Wrapper, Java, and build execution permissions.
- **sha256sum** and **cmp** (standard on Linux).
- On macOS, replace **sha256sum** with **shasum -a 256**.
- Both clean builds run the **exact same command**, source, and project dependencies.
- If Maven or tests fail, **set -e** halts the script so a failed build is never counted as valid.

### 7.3. PowerShell on Windows

For Windows PowerShell:

~~~powershell
$artifact = ".\target\repro-demo-1.0.0.jar"
$dir = Join-Path $env:TEMP ("maven-repro-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $dir | Out-Null

& .\mvnw.cmd -B -ntp clean verify
if ($LASTEXITCODE -ne 0) {
    throw "First Maven build failed"
}
Copy-Item -LiteralPath $artifact -Destination (Join-Path $dir "first.jar")

& .\mvnw.cmd -B -ntp clean verify
if ($LASTEXITCODE -ne 0) {
    throw "Second Maven build failed"
}
Copy-Item -LiteralPath $artifact -Destination (Join-Path $dir "second.jar")

$first = (Get-FileHash (Join-Path $dir "first.jar") -Algorithm SHA256).Hash
$second = (Get-FileHash (Join-Path $dir "second.jar") -Algorithm SHA256).Hash

Write-Host "First SHA-256: $first"
Write-Host "Second SHA-256: $second"

if ($first -eq $second) {
    Write-Host "PASS: SHA-256 hashes match"
} else {
    throw "FAIL: two Maven outputs have different hashes"
}
~~~

Both JARs are preserved outside **target/** in a temporary directory. Hash collisions between differing contents are practically negligible, making this a sound byte-identity check. Still, matching hashes **do not prove** independent build verification or vulnerability freedom.

### 7.4. What Counts as PASS?

| Result | Conclusion |
| --- | --- |
| Two clean builds succeed, identical SHA-256, identical scope | PASS local verification for that artifact |
| Two builds PASS, yet SHA-256 differs | FAIL local reproducibility; investigate |
| One build/test FAILs | No valid pair of successful builds to compare |
| SHA-256 matches, yet built once and copied twice | **Not** a reproducibility test |
| Both main JARs match, yet sources JAR differs | **Not** reproducible for the **full release** if sources JAR is in scope |
| Two builds on machine A match | Independent rebuild still needed before claiming independently reproducible |

**Important:** the filesystem timestamps of **first.jar** and **second.jar** can still differ while their SHA-256 digests match. Do not treat that as FAIL.

## 8. Maven Artifact Plugin: Checking with the Official Tool

Maven provides **maven-artifact-plugin** to assist Reproducible Builds verification.

### 8.1. Identifying Nondeterministic Plugins

~~~bash
./mvnw artifact:check-buildplan
~~~

The **artifact:check-buildplan** goal inspects the build plan to flag plugins/goals with known reproducibility issues or needed upgrades. It **cannot certify** that all custom plugins, code generators, or runtime environments are deterministic.

### 8.2. Comparing Against a Reference Artifact in the Local Repository

Per Maven guidance, you can run:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

The first command installs built artifacts into the local repository; the second performs a clean build and runs **artifact:compare** against the installed reference. This helps validate release artifacts via plugin tooling, especially with multiple outputs or attached artifacts.

**Do not confuse local install with an artifact published to Maven Central or a production repository.** A passing local comparison does not prove a third machine can rebuild the published release file. For independent verification, use the published artifact as the reference and rebuild from documented source and toolchain.

### 8.3. If compare FAILs

Diagnostic steps:
1. Preserve both output files and plugin logs.
2. Identify which artifact diverged: main JAR, sources, Javadoc, WAR, POM, or metadata.
3. Run **diffoscope** or a ZIP-aware diff tool to locate differing entry metadata or contents.
4. Trace which goal/plugin produced the diverging file.
5. Upgrade to a reproducibility-supporting plugin version or fix the nondeterministic codegen/input.
6. Rebuild and re-compare all artifacts.

Never patch ZIP bytes post-build to “make hashes match” while leaving the underlying generator bug intact.

Documentation: https://maven.apache.org/guides/mini/guide-reproducible-builds.html

## 9. When a Fixed Timestamp Is Still Not Enough

### 9.1. Outdated Plugins or Misconfiguration

If **maven-jar-plugin** or **spring-boot-maven-plugin** is too old to support `outputTimestamp` or is not invoked, the POM property will not stabilize the final JAR. Additionally, parents/profiles can override configuration.

Use **help:effective-pom**, **help:describe**, and Maven build logs to confirm actual **versions and execution goals**.

### 9.2. Dynamic Dependencies or SNAPSHOTs

If a build relies on an updated SNAPSHOT or a version range resolving differently, the final JAR can embed a **dependency with different bytes** despite matching coordinates.

In a Spring Boot executable archive, dependencies live under **BOOT-INF/lib**. Changing bytes in a nested JAR inevitably changes the outer Boot JAR hash. Maven `outputTimestamp` **does not lock dependencies** and cannot make differing third-party JARs identical.

### 9.3. JDK, Compiler, and Generated Sources

**javac** across different JDK major versions can emit different class files from identical Java source. Annotation processors, code generators, or source-generating plugins may embed:
- generation timestamps;
- absolute workspace paths;
- machine/user names;
- random UUIDs;
- non-deterministically ordered field lists;
- compiler/build tool versions.

Pin JDK/toolchain and plugin versions, and inspect generated sources and class bytecode. Do not tweak `outputTimestamp` to another number when the real issue lives in generated code.

### 9.4. Line Endings, Encoding, Locale, and OS

A text resource on Windows may use **CRLF**, while Unix uses **LF**. Resource filtering, generated code, default encodings, and differing locales can alter bytes. Standardize:
- **UTF-8** for sources/resources where applicable;
- line-ending policy;
- timezone/locale used by generators;
- matching Java major version and plugin versions;
- consistent profiles/CI options across systems.

Maven documentation emphasizes that independent rebuilds across Windows and Unix may require handling newline/OS differences.

### 9.5. File Ordering and Non-Timestamp ZIP Metadata

One plugin might add entries to a JAR in unstable filesystem traversal order; another might write different attributes/permissions or extra ZIP fields. **Identical timestamps** do not make those other fields match.

Use binary/ZIP-aware diffs to classify:
- only entry timestamps differ;
- entry ordering differs;
- manifest differs;
- compiled `.class` files differ;
- resource contents differ;
- nested libs differ;
- signatures/signing metadata differ.

Fix the root cause evidenced by the diff rather than tweaking timestamps to mask differences.

## 10. Spring Boot build-info.properties Embeds Time Inside Contents

Spring Boot Maven Plugin supports the **build-info** goal generating:

~~~text
META-INF/build-info.properties
~~~

When enabled, this file can contain **build.group, build.artifact, build.name, build.version, build.time**. This is resource content, not a ZIP entry timestamp.

Per Spring Boot **3.5.16** documentation, the **time** parameter of **spring-boot:build-info** uses **project.build.outputTimestamp** if present; otherwise the plugin may use the Maven session start time. Thus a fixed property stabilizes not only `repackage` but also **build.time** when `build-info` is used.

### 10.1. Enabling build-info When Required

In the sample POM, **replace** the existing Spring Boot Maven Plugin block with:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>build-info</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

This XML is only a **plugin block** inside **build/plugins**, not a standalone POM. With the Spring Boot starter parent, **repackage** remains active via the parent, while **build-info** is added by this execution.

After building, inspect **target/classes/META-INF/build-info.properties** (once generated by the goal), and compare that entry inside the final Boot JAR if needed. Never assume **build-info.properties** is generated automatically just because a project uses the Spring Boot Plugin.

### 10.2. Separating “Pinned Build Date” from “Job Execution Date”

**build.time** derived from the project property stays constant when reproducing the same release even if a CI job reruns a week later. If dashboards need the latest deploy/start time, pull it from deployment metadata or runtime monitoring—**do not edit outputTimestamp on every job run**.

If you want to omit **build.time** from the resource, Spring Boot Plugin supports **excludeInfoProperties** or setting `time` to **off**; choose based on product requirements and still inspect the remaining fields in the file.

## 11. Choosing an Appropriate Timestamp for Release Pipelines

### 11.1. Fixed Value in the POM

A release can set:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

Same release source, same timestamp value. When preparing a new release, the pipeline/release manager updates the anchor per policy and commits it alongside version/metadata. This is straightforward to audit, though it requires discipline not to forget updating it.

### 11.2. Using the Git Commit Timestamp

Git can supply the HEAD commit timestamp in seconds:

~~~bash
git log -1 --format=%ct
~~~

Once a release pipeline fixes HEAD as the released commit, pass that value into Maven:

~~~bash
stamp="$(git log -1 --format=%ct)"
./mvnw -B -ntp "-Dproject.build.outputTimestamp=$stamp" clean verify
~~~

**%ct** returns epoch **seconds**, constant for the same commit. If the workspace is dirty, commit time does not fully represent the source; ensure a controlled clean checkout before releasing.

This is an **alternative to a static POM timestamp**—do not edit the POM property to one value while overriding it with a different value on every CLI call. When overriding via CLI properties, verify **help:evaluate** and plugin behavior on your actual Maven version.

### 11.3. Note on the Maven Release Plugin

Maven documentation notes that Maven Release Plugin versions starting at **3.0.0-M1** support updating `outputTimestamp` automatically during release workflows. Custom release pipelines or `versions-maven-plugin` behave differently by version. Enable automation only after testing on a staging branch/release, rather than assuming every plugin synchronizes timestamps automatically.

### 11.4. Never Use the CI Job's Current Clock Time

If the same commit is rebuilt on another day, using current time as the property yields a different timestamp. That writes a timestamp into the archive, yet **it is unstable**, defeating the reproducible build goal. Timestamps embedded in artifacts must be **deterministic release metadata**, never the live clock.

## 12. Multi-Module Maven and Parent Inheritance

In a multi-module project:

~~~text
platform-parent/
├── pom.xml
├── api/pom.xml
├── library/pom.xml
└── boot-app/pom.xml
~~~

You can define in the **parent POM**:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Child modules that **actually declare the appropriate parent** inherit the value unless overridden. **Merely listing a module in an aggregator POM does not mean every module inherits properties**. Inspect each module's effective POM if proof is needed.

In multi-module builds:
- Each JAR/WAR/source archive must be built by plugins with matching versions and policies.
- If a single module generates a resource with a dynamic timestamp, that module alone can break release-wide reproducibility.
- Ensure identical reactor selection and build flags across compared runs.
- Never compare a full-repo build against a single-module build and claim identical workloads.

Example when module **boot-app** exists:

~~~bash
./mvnw -pl boot-app -am -B -ntp clean verify
~~~

**-pl** selects the module and **-am** adds reactor dependencies. This command is not equivalent to building the entire repo if unrelated modules are skipped.

## 13. Diagnosing Results When Hashes Still Differ

| Symptom | Question to ask | How to inspect |
| --- | --- | --- |
| Property exists, yet JAR hash changes | Which plugin creates/rewrites the archive? | Effective POM, plugin goal logs |
| Maven Jar Plugin produces stable output, Boot JAR differs | Does `repackage` use `outputTimestamp`? Do nested libs differ? | Spring Boot Plugin version, diff Boot JAR |
| ZIP entries have different timestamps | Older plugin or another archive step reset metadata? | Plugin `outputTimestamp`, ZIP diff |
| `.class` file bytes differ | Different JDK/compiler/codegen? | Compare `.class`, `javap`, toolchain |
| Resource file differs | Uses current time, env variable, or filtering? | `target/classes`, generated files |
| Nested JAR differs | Snapshot/version range or repository changed? | `dependency:tree`, dependency hashes |
| Manifest differs | Embedding build time/host/JDK info? | Compare `META-INF/MANIFEST.MF` |
| `build-info` has dynamic `build.time` | Did `build-info` goal fall back to session time? | Property and `build-info` time config |
| SHA matches on Linux, fails on Windows | Newlines/encoding/OS assumptions? | Normalize JDK and resource bytes |
| Filesystem mtime differs, yet SHA matches | Only outer file metadata changed | Content reproducibility PASSed |
| Sources JAR differs while Boot JAR matches | Different plugin handles source archive | Inspect source plugin and file entries |
| Dynamic dependencies keep coordinates, change bytes | Same SNAPSHOT republished? | Repository metadata, dependency hashes |
| Plugin embeds machine path | Absolute source path in generated output? | Diffoscope and source generator config |
| JAR has stable timestamps, signing output differs | Signatures/certificates include their own time metadata | Control signing process per release policy |
| `artifact:check-buildplan` PASSes, yet binaries differ | Tool only knows certain plugin issues | Compare real hashes and diffoscope |
| Hashes match, yet built once and copied twice | Flawed experiment | Two independent clean builds |

**Work from broad to narrow:**
1. Confirm source commit, Maven/JDK, dependencies, and active profiles match.
2. Verify **project.build.outputTimestamp** and plugin versions.
3. Preserve both the reference and new binaries.
4. Use **diffoscope** or a ZIP-aware diff tool to locate differing entries.
5. Identify which goal/plugin generated the differing file.
6. Fix the actual root cause, rebuild, and re-compare hashes.

Never run **touch** to alter file mtime and claim ZIP metadata is fixed. Never unpack a JAR and hand-edit contents to force matching binaries: fix the **artifact creation process**.

## 14. Differences from Gradle

This lesson targets **Maven's project.build.outputTimestamp**, not the Gradle build cache or Spring runtime properties. Gradle's Java plugin provides its own mechanisms for reproducible archive tasks, such as configuring **preserveFileTimestamps** and **reproducibleFileOrder** on applicable archive tasks. Never copy Maven XML into **build.gradle**; if using Gradle, consult Gradle task settings and Spring Boot Gradle packaging documentation.

Enabling Maven `outputTimestamp` **does not speed up compilation**, make the JVM run faster, or replace a dependency cache. Reproducibility solves **byte consistency**, whereas performance is measured in time and resource consumption.

## 15. Practice Exercises with Solutions

### Exercise 1: Distinguishing Filesystem vs. Archive Timestamps

You build twice; the **mtime of target/repro-demo-1.0.0.jar differs**, yet **SHA-256 matches**. Is the build reproducible?

**Answer:** For the main JAR bytes tested, the result **PASSes local verification**. Filesystem mtime is not ZIP entry bytes. You still need to verify other in-scope release artifacts and run independent checks for stronger claims.

### Exercise 2: Why Isn't a Static Timestamp Enough?

The POM sets:

~~~xml
<project.build.outputTimestamp>2026-07-01T00:00:00Z</project.build.outputTimestamp>
~~~

Yet a custom Maven plugin writes **build.startTime** using the system clock into packaged JSON. Could hashes differ?

**Answer:** Yes. Data **inside the JSON file** changed. Replace it with a stable release timestamp, or store runtime/CI timestamps outside the artifact.

### Exercise 3: Seconds or Milliseconds?

Two values:

~~~text
1782864000
1782864000000
~~~

Which value is valid as an epoch integer for Maven `outputTimestamp`?

**Answer:** **1782864000** is in seconds. The longer number is milliseconds, which does not match what the plugin expects.

### Exercise 4: Maven Jar Plugin Is Stable, Boot Repackage Is Old

The project's plain JAR produces matching hashes, yet the final Spring Boot JAR differs. What should you do?

**Answer:** Check Spring Boot Maven Plugin version, **repackage outputTimestamp**, and nested dependencies; diff the diverging files before changing configuration. Do not stop at the plain JAR result.

### Exercise 5: Main JAR Is Stable, Sources JAR Differs

Can you declare the entire release reproducible?

**Answer:** If the release includes the sources JAR, **no**. Inspect the plugin creating the sources archive and source metadata; reproducibility criteria must apply to all target artifacts.

### Exercise 6: Same Git Commit, CI Runs in Different Time Zones

Two builds derive the timestamp with **git log -1 --format=%ct** using identical JDK/inputs. Will differing time zones change epoch seconds?

**Answer:** **%ct** outputs the commit's Unix epoch seconds, so it does not change merely because machines sit in different time zones. Still, other plugins/resources may depend on machine time zones and must be checked separately.

### Exercise 7: build-info.properties Has Varying build.time

If the Spring Boot `build-info` goal uses session time because the Maven project property was unset, what should you do?

**Answer:** Set a stable **project.build.outputTimestamp** or configure **build-info time** per release policy. Compare `build-info` contents rather than checking only ZIP entry timestamps.

### Exercise 8: Compared Twice on the Same Machine—Can Outsiders Rebuild It?

**Answer:** Not yet proven. You need an independent rebuild in another controlled environment, compared against the **published artifact**, with recorded toolchain/dependency/provenance.

## 16. Pre-Release Checklist

- [ ] Clearly defined which artifacts must be reproducible: main Boot JAR, WAR, sources, javadoc, etc.
- [ ] Source commit/tag is pinned with no untracked dirty changes.
- [ ] Maven version/Wrapper, JDK/compiler, and plugin versions are pinned.
- [ ] Dependencies are stable, avoiding uncontrolled snapshots/version ranges.
- [ ] **project.build.outputTimestamp** has a stable ISO 8601 UTC or Unix epoch **seconds** value.
- [ ] The property resolves properly in the effective POM without unintended profile/CLI overrides.
- [ ] Maven Jar Plugin and Spring Boot Maven Plugin support `outputTimestamp`; other archive plugins verified individually.
- [ ] Resource filtering, generated sources, manifest, and build-info do not embed dynamic timestamps, hostnames, or random IDs.
- [ ] Newlines/encoding/locale/OS/JDK are controlled per release process.
- [ ] Ran **two clean builds**, copying the first JAR outside `target` before the second build.
- [ ] Compared full bytes using **SHA-256** or **cmp**, not just file mtime.
- [ ] On hash mismatch, used **artifact:check-buildplan**, **artifact:compare**, diffoscope, and plugin inspection.
- [ ] In multi-module builds, verified matching module scope, parent inheritance, and source versions.
- [ ] When claiming independent reproducibility, rebuilt in a separate environment and compared against the published artifact.
- [ ] Still ran unit/integration tests, scanning, and release checks; reproducibility does not replace them.
- [ ] Recorded build provenance: source ref, toolchain versions, timestamp policy, dependency sources, and release checksums.

## 17. Summary

**project.build.outputTimestamp** is a Maven property supplying a **stable timestamp for archive entries** in supporting plugins, notably **maven-jar-plugin** and **spring-boot-maven-plugin:repackage**. It eliminates binary variations caused purely by building on different days.

Workflow to remember:

~~~text
Pin source + Maven/JDK/dependencies
                  |
                  v
Select release/commit timestamp
                  |
                  v
Set project.build.outputTimestamp
                  |
                  v
Clean build #1, save artifact outside target
                  |
                  v
Clean build #2, save artifact outside target
                  |
                  v
Compare SHA-256 and check artifact scope
                  |
             +----+----+
             |         |
            PASS      FAIL
             |         |
  Independent check  Inspect binary/ZIP/codegen,
                     locate plugin, fix root cause
~~~

**The takeaway cannot be reduced to “add one property line and you're done.”** A truly reproducible build requires byte-identical artifacts, controlled source/toolchain/dependencies, and comparison evidence from the actual release workflow.

## 18. Official References

- Apache Maven — Configuring for Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Apache Maven JAR Plugin — jar:jar, outputTimestamp: https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html
- Apache Maven Artifact Plugin — artifact:check-buildplan: https://maven.apache.org/plugins/maven-artifact-plugin/check-buildplan-mojo.html
- Apache Maven Artifact Plugin — artifact:compare: https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Spring Boot 3.5.16 Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5.16 Maven Plugin — Build Info: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-info.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Reproducible Builds — SOURCE_DATE_EPOCH: https://reproducible-builds.org/docs/source-date-epoch/
- Reproducible Builds — Timestamps: https://reproducible-builds.org/docs/timestamps/