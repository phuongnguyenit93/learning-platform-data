# Comparing SHA-256 Hashes of Two Builds from the Same Source in Clean Environments

## 1. Goal: Proving the Packaged File Is Reproducible

A Spring Boot project can **build successfully many times** while producing JAR files with **different byte contents** even without modifying source code. For instance, a ZIP/JAR file might contain differing timestamps, entry order, `Build-Time` values, Git metadata, build host paths, or annotation processor outputs. These small details do not necessarily break the application at runtime, yet they change the SHA-256 hash.

A **reproducible build** in the strong sense means: given an explicitly defined set of inputs (source code, dependencies, build scripts, toolchain, and build conditions), the resulting artifact has the exact same byte sequence. Merely behaving identically at runtime **is not enough**; you must verify **byte-for-byte** equality of the output file.

This lesson sets up a practical verification test:

1. Pick **a fixed Git commit**.
2. Create **two clean, independent checkouts**, carrying over no stale build files.
3. Hold Maven/Gradle, JDK, plugin, dependency versions, and configurations constant.
4. Build the exact same type of **Spring Boot executable JAR** twice.
5. Compute the **SHA-256** of both files.
6. Compare both digests and compare the two files byte-for-byte.
7. On mismatch, inspect ZIP contents, manifest, timestamps, and environment-derived data to locate the cause.
8. Integrate the check into CI to catch reproducibility regressions.

**Examples use Java 17, Spring Boot 3.3.5, Maven 3.9.x, or Gradle 8.5**, producing an artifact named **repro-demo-1.0.0.jar**. This is a fixed version set for practice, not the latest available versions.

### Expected Outcome

When two builds actually share identical bytes, an illustrative output looks like:

~~~text
BUILD_A_SHA256=<64 hexadecimal characters>
BUILD_B_SHA256=<same 64 hexadecimal characters>
REPRODUCIBLE=PASS
~~~

Angle brackets in the diagram above merely explain format; they are **not a real measured SHA-256**. You cannot know a valid digest before actually building the artifact. In the runnable scripts below, real checksums are computed and printed from the JAR files rather than hard-coded.

**Note on “clean environment”:** Two clean checkouts on the same host are a very useful controlled experiment, yet **they do not prove reproducibility across all operating systems/JDKs**. For stronger verification, run in two independent containers/runners with pinned image digests, JDKs, and toolchains recorded.

## 2. What Does SHA-256 Confirm?

**SHA-256** is a cryptographic hash function mapping any byte sequence to a **256-bit** digest, typically rendered as **64 hexadecimal characters**. Conceptually:

~~~text
SHA256(bytes of artifact-a.jar) = H1
SHA256(bytes of artifact-b.jar) = H2

H1 == H2  → strong practical proof both files share identical bytes
H1 != H2  → guarantees the two files differ in bytes
~~~

SHA-256 ignores filenames, whether the app runs, or whether source “looks identical.” Changing even a single bit in the JAR completely changes the SHA-256.

**Do not conflate concepts:**

| Check | Meaning | What has NOT been proven |
| --- | --- | --- |
| Two test runs both PASS | Logic satisfies existing tests | That the JARs have identical bytes |
| Two JARs have identical size | File lengths match | Byte contents match |
| Two JARs have the same class list | Entry names correspond | Identical contents/ZIP metadata/timestamps |
| Two JARs share the same SHA-256 | Very strong evidence of identical bytes | That build source/trust chain is safe |
| `cmp` confirms two files are identical | Direct byte-by-byte verification | That artifact came from trusted source or was signed |
| Digest is signed with attestation | Adds provenance evidence when properly verified | Does not replace content, dependency, and build checks |

In theory hash collisions could exist for different inputs, yet for practical reproducible build verification, **matching SHA-256 digests are very strong evidence**. We also pair them with **cmp** for direct file comparison when running on the same host/runner.

**SHA-256 is a consistency check, not a supply-chain security certification.** If both builds download a tampered dependency under the same coordinate, both JARs can still share the same hash. Verifying origin requires dependency verification, signatures, SBOMs/provenance, and proper publishing policies.

## 3. Precisely Defining “Same Source” and “Clean Environment”

### 3.1. Same Source Means Same Git Commit, Not Just Same Branch

Never treat “both are on branch main” as sufficient proof. A branch can advance between two checkouts. Pin the commit:

~~~bash
git rev-parse HEAD
~~~

The output is a repository-specific Git object ID, such as a hex string; **there is no universal fixed stdout across all projects**. In automated scripts, capture the commit ID in a variable and check out **that exact ID** twice.

If the project uses Git submodules, Git LFS, or generated code fetched from another repository, pin and fetch those inputs by their respective versions/commits too. Pinning only the root commit is insufficient if the build pulls mutable data elsewhere.

### 3.2. A Clean Checkout Differs from Simply Running clean

Running **mvn clean** or **gradle clean** typically deletes configured build directories like `target/` or `build/`. It **does not guarantee** deleting non-standard script outputs, local `.env` files, generated sources outside the build directory, resources placed in `src/`, or leftover workspace state.

Therefore:

- **Two fresh checkouts from the same commit** avoid leftover outputs from prior runs.
- **clean package / clean bootJar** clears standard outputs before each build.
- **Separate dependency/cache directories** per run provide a stronger test, preventing two runs from sharing hidden local cache state.
- **Never copy artifacts from run A into checkout B** before building B.
- **Never mix test reports or artifacts from both runs** in the same output path when hashing.

Note: Gradle/Maven caches do not inherently make builds non-reproducible. Correct caches reuse outputs keyed by inputs. Still, when testing independence, separating caches verifies results do not depend on hidden local state.

### 3.3. Same Tool Versions and Environment

Record at minimum:

~~~text
Git commit ID
OS and CPU architecture
Java vendor + exact Java version
Maven/Gradle version
Spring Boot plugin version
Dependency graph and resolved versions
Locale, timezone, file encoding where influential
Environment variables read by build scripts
Build commands and flags
Artifact path and SHA-256
~~~

**java -version**, **./mvnw -version**, or **./gradlew --version** inspects the toolchain. Recording only “Java 17” is often insufficient across environments, because differing patch releases and vendors can change compiler/tool output.

Pin the Gradle Wrapper/Maven Wrapper in the Git commit. When using containers, pin the **image digest** for stronger testing; tags can be overwritten. In the immediate example below, both builds run on the **same OS/JDK** to avoid confusing environmental drift with build contents.

## 4. Sources of Variability Inside a Spring Boot Executable JAR

### 4.1. ZIP Entry Timestamps

A JAR is a ZIP archive. Entries carry metadata like filename, compressed bytes, CRC, timestamp, and extra attributes. If the packaging task preserves differing **file modification times**:

~~~text
Run A: BOOT-INF/classes/... 2026-11-09 09:00:00
Run B: BOOT-INF/classes/... 2026-11-09 09:02:00
~~~

...then ZIP/JAR bytes can differ even with identical class contents.

**How to reduce differences:**

- **Maven:** use **project.build.outputTimestamp** and ensure both JAR packaging and Spring Boot **repackage** receive a stable timestamp.
- **Gradle:** on **AbstractArchiveTask**, set **preserveFileTimestamps = false** and **reproducibleFileOrder = true** for target archive tasks; Gradle 9+ provides better defaults, yet this lesson pins Gradle 8.5 so set them explicitly.
- **Never** patch ZIP timestamps manually post-build as your primary solution; configure it at the archive-creation task.

### 4.2. File Order Inside the Archive

Two ZIPs containing identical files, added in a different order:

~~~text
JAR A: A.class, B.class, application.properties
JAR B: application.properties, B.class, A.class
~~~

...will produce different SHA-256 digests. Filesystems, traversal order, or unstable custom copy tasks are frequent culprits.

In Gradle, **reproducibleFileOrder=true** instructs the archive task to traverse files in a stable order. In Maven, use plugin versions supporting reproducible archives and audit any plugins/custom executions generating files in nondeterministic order.

### 4.3. Manifest and Build Metadata

The manifest **META-INF/MANIFEST.MF** or **META-INF/build-info.properties** might embed:

~~~text
Build-Time: <execution timestamp>
Build-Host: <build machine hostname>
Build-User: <user account running the build>
Build-Revision: <Git revision>
~~~

These are examples of fields that can introduce variation. **Spring Boot does not add all four of these fields automatically by default.** They appear when configured by the project or plugins. If any field reads **new Date()**, **Instant.now()**, CI execution time, hostname, or workspace path, the two builds will differ.

Remediation:

- If **revision** is needed, derive it from the **same pinned Git commit**.
- If **build time** is needed, use a reproducible value from release metadata/source commit time, or omit time from the artifact and store it in CI provenance.
- For Spring Boot build-info, check **build.time** when the `build-info` task/goal is enabled; never assume dynamic timestamps are disabled across all configurations.
- Never write usernames, absolute machine paths, or environment secrets into the JAR.
- Intentional changes to input metadata **must change the checksum**; that is not a bug.

### 4.4. Annotation Processors and Generated Code

Lombok, MapStruct, OpenAPI generators, protobuf compilers, and custom codegen can emit files using unstable ordering or timestamps. A processor writing the current time into generated sources/classes changes output even when app logic is untouched.

Check:

- Plugin and processor versions are pinned.
- Generated sources live in a clean output directory.
- Outputs do not depend on unstable file traversal order.
- No absolute source paths or hostnames embedded.
- When using incremental compilation tasks, compare against a **clean** build so stale outputs do not affect run A or B.

### 4.5. Dependencies and Plugins

A dependency at **1.0-SNAPSHOT**, **1.+**, or a Maven version range can resolve to different bytes at two points in time. Maven/Gradle plugins are also build inputs.

**Pinning versions** is the first step; stricter requirements also store and verify dependency artifact checksums. Gradle dependency locking/verification, Maven dependency version policies, and immutable repositories limit mutable inputs.

Never assume “same Git commit guarantees same dependencies” if builds use dynamic selectors, snapshot metadata, or mutable remote plugin resolution.

### 4.6. Build Scripts, OS, and ZIP Tooling

Scripts invoking OS tools to build archives may encounter differing compression library versions, newline conventions, file permissions/symlinks, or traversal orders. Such differences do not show up when comparing Java source files.

For cross-platform checks, pin image/tool versions, check `.gitattributes` and line endings, file permissions, locale/timezone, and native tools. **Passing on one machine** is only the first step before claiming cross-platform reproducibility.

## 5. Minimal Java 17 Spring Boot Application for Verification

Create a project named **repro-demo**. It needs only one main class with fixed output, no dynamic build time, and no database/web server.

### 5.1. Directory Structure

~~~text
repro-demo/
├── pom.xml                    # Maven option
├── settings.gradle            # Gradle option
├── build.gradle               # Gradle option
├── mvnw / mvnw.cmd            # Maven wrapper if using Maven
├── .mvn/wrapper/...           # corresponding Maven wrapper
├── gradlew / gradlew.bat      # Gradle wrapper if using Gradle
├── gradle/wrapper/...         # corresponding Gradle wrapper
└── src/main/java/com/example/repro/ReproApplication.java
~~~

**Maven and Gradle are two alternative build setups.** A real exercise repository only needs the files for your chosen tool. Wrappers must be generated/scaffolded and committed to Git; merely listing wrapper names in a diagram does not create them.

### 5.2. Java Application

File **src/main/java/com/example/repro/ReproApplication.java**:

~~~java
package com.example.repro;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReproApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReproApplication.class, args);
    }

    @Bean
    CommandLineRunner result() {
        return args -> System.out.println("REPRO_BUILD_OK");
    }
}
~~~

This is a complete Java 17 class. It avoids **Instant.now()**, random UUIDs, or hostnames in packaged data. It also starts no HTTP server since it uses the core Spring Boot starter rather than starter-web.

After building the executable JAR and running:

~~~bash
java -jar target/repro-demo-1.0.0.jar
~~~

or the corresponding Gradle path, the app prints the **stdout line from code**:

~~~text
REPRO_BUILD_OK
~~~

Spring Boot may emit additional logs and banners depending on configuration; **REPRO_BUILD_OK** is the fixed marker for this exercise. **Never substitute `java -jar` output for SHA-256**: two JARs with different bytes can both print `REPRO_BUILD_OK`.

## 6. Maven: Configuring outputTimestamp for JAR and Spring Boot Repackage

### 6.1. Complete pom.xml

Use the following **pom.xml** for the Maven option:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <version>3.4.2</version>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**This is a complete POM** for the Spring Boot 3.3.5 demo. Key points:

1. **project.build.outputTimestamp** is a stable input for ZIP entry timestamps, not live build time. The sample **2024-01-01T00:00:00Z** was chosen for easy verification, not as a real release date.
2. **maven-jar-plugin** creates the standard JAR in the package lifecycle and honors `outputTimestamp` as configured.
3. **spring-boot-maven-plugin** repackages into the executable JAR and also takes `outputTimestamp`. Boot plugin's default references **project.build.outputTimestamp**, yet we declare it explicitly here so readers see both stages.
4. **spring-boot-starter-parent** supplies dependency management and the standard repackage execution. Do not declare duplicate repackage executions.
5. **project.build.sourceEncoding=UTF-8** fixes source/resource encoding when supporting plugins need it.
6. **spring-boot-starter** omits a version because the Spring Boot parent manages it. Parent/plugin versions are pinned at **3.3.5**.
7. **Do not enable spring-boot:build-info with dynamic build.time** or live custom manifest attributes, avoiding nondeterministic inputs.

**`outputTimestamp` is not a magic guarantee.** If generated code contains timestamps, dependencies shift, custom packagers run, or compression ordering varies, the two JARs will still differ. It solves **one critical cause**, not every check.

### 6.2. Building and Locating the Artifact

In a Maven project with Wrapper:

~~~bash
./mvnw -B -ntp clean package
~~~

Or using a compatible installed Maven:

~~~bash
mvn -B -ntp clean package
~~~

On Windows use **mvnw.cmd**. Depending on your Maven setup, **-ntp** (no transfer progress) keeps logs cleaner without affecting JAR contents.

Final artifact to check:

~~~text
target/repro-demo-1.0.0.jar
~~~

With the Spring Boot parent and repackage goal, this is the executable Boot JAR. Do not compare **.jar.original** when your target is the deployable artifact.

### 6.3. When to Use the Git Commit Timestamp Instead of a Constant?

This lesson uses a fixed timestamp for simplicity. In release pipelines, use a **timestamp taken from a pinned commit** (e.g., from `git log`) or an approved release epoch instead of hard-coding a 2024 date.

**Key condition:** two builds from the same commit must receive the **exact same value**. Never run `date +%s` on every build to set `outputTimestamp`, as that brings back dynamic timestamps.

If CI passes the value via a Maven property, record it in build provenance. Other plugins and build steps producing archives must adhere to the same timestamp policy.

## 7. Gradle: Reproducible Archive Tasks, bootJar, and Source Set

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'repro-demo'
~~~

### 7.2. Complete build.gradle (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

This is a **complete `build.gradle`** when paired with the Java class in Section 5. Purpose of each section:

- **java + java.toolchain** configures the project to use Java 17 via a managed compiler/toolchain.
- **Spring Boot Gradle Plugin 3.3.5** provides **bootJar** (with the Java plugin) to package the executable Boot archive.
- **io.spring.dependency-management 1.1.6** imports the Spring Boot BOM so starters need no explicit versions.
- **tasks.withType(AbstractArchiveTask).configureEach** applies policy to all applicable archive tasks, covering both **jar** and **bootJar** since `bootJar` is an archive task. Do not configure **jar** alone and overlook **bootJar**.
- **preserveFileTimestamps = false** prevents varying source modification timestamps from entering ZIP entries.
- **reproducibleFileOrder = true** ensures deterministic archive file traversal independent of filesystem order.
- With **Gradle 8.5**, set both properties explicitly. With Gradle 9+, reproducible archive defaults are improved, though auditing plugins and custom tasks remains necessary.

**Never write `Build-Time = new Date()`** into `bootJar`'s manifest. Any file/field containing live build-time data will break SHA-256 even when archive tasks are properly configured.

### 7.3. Building and Identifying the Right JAR

~~~bash
./gradlew --no-daemon clean bootJar
~~~

Or to include standard verification tasks:

~~~bash
./gradlew --no-daemon clean build
~~~

In a Spring Boot Gradle project, the expected executable archive is:

~~~text
build/libs/repro-demo-1.0.0.jar
~~~

Gradle may also produce a plain JAR when running **build**:

~~~text
build/libs/repro-demo-1.0.0-plain.jar
~~~

**Always compare the right artifact type.** Never compare **-plain.jar** from run A against **bootJar** from run B, nor compare a pipeline-modified copy against the original JAR and mistake it for non-reproducibility.

### 7.4. Checking Which Tasks Produce Archives

~~~bash
./gradlew tasks --all
./gradlew help --task bootJar
~~~

If a project defines custom `Zip`/`War`/`Jar` tasks, each archive may need matching timestamp/order policies. **Never assume the entire build is reproducible just because `bootJar` is configured properly.** Generated resources, compiled classes, and nested dependency JARs are all inputs.

## 8. A/B Experiment: Two Clean Checkouts from the Same Git Commit

This is the core test. We create **two fresh Git worktrees** from one commit, build independently, and compare SHA-256 digests. Worktrees reference the original repository's `.git` while isolating working files in two distinct directories. This avoids carrying over untracked outputs from your active working tree. Tools, dependencies, and non-Git inputs still need pinning.

### 8.1. Prerequisites

- Machine with **Git**, **JDK 17**, compatible Maven/Gradle, and Bash.
- Project source **committed in Git**, including POM or Gradle files, Java sources, and Wrapper scripts.
- From repository root, **git rev-parse --show-toplevel** points to the project being built. If the project lives in a monorepo subfolder, adjust execution paths to that subfolder.
- Project has a valid wrapper **mvnw** or **gradlew** (and committed wrapper config files). Without a wrapper, substitute an installed Maven/Gradle of the exact version.
- Maven/Gradle can fetch dependencies from reachable repositories or valid offline/cache policies.
- Output path matches Section 6 (Maven) or Section 7 (Gradle), without custom classifiers/filenames.

### 8.2. Complete Bash Script: scripts/check-repro.sh

Create **scripts/check-repro.sh** at root and commit it if you plan to reuse it. It accepts **maven** or **gradle** to choose the build tool. The script below uses the same Git commit and two **separate dependency cache/user home directories**.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: bash scripts/check-repro.sh maven|gradle" >&2
  exit 2
fi

MODE="$1"
if [ "$MODE" != "maven" ] && [ "$MODE" != "gradle" ]; then
  echo "Choose maven or gradle" >&2
  exit 2
fi

REPO="$(git rev-parse --show-toplevel)"
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
TMP="$(mktemp -d)"

A="$TMP/source-a"
B="$TMP/source-b"

cleanup() {
  git -C "$REPO" worktree remove --force "$A" >/dev/null 2>&1 || true
  git -C "$REPO" worktree remove --force "$B" >/dev/null 2>&1 || true
  rm -rf -- "$TMP"
}
trap cleanup EXIT

git -C "$REPO" worktree add --detach "$A" "$COMMIT"
git -C "$REPO" worktree add --detach "$B" "$COMMIT"

if [ "$MODE" = "maven" ]; then
  (
    cd "$A"
    ./mvnw -B -ntp -Dmaven.repo.local="$TMP/maven-a" clean package
  )
  (
    cd "$B"
    ./mvnw -B -ntp -Dmaven.repo.local="$TMP/maven-b" clean package
  )
  ARTIFACT="target/repro-demo-1.0.0.jar"
else
  (
    cd "$A"
    GRADLE_USER_HOME="$TMP/gradle-a" ./gradlew --no-daemon clean bootJar
  )
  (
    cd "$B"
    GRADLE_USER_HOME="$TMP/gradle-b" ./gradlew --no-daemon clean bootJar
  )
  ARTIFACT="build/libs/repro-demo-1.0.0.jar"
fi

FILE_A="$A/$ARTIFACT"
FILE_B="$B/$ARTIFACT"

test -f "$FILE_A"
test -f "$FILE_B"

HASH_A="$(sha256sum "$FILE_A" | awk '{print $1}')"
HASH_B="$(sha256sum "$FILE_B" | awk '{print $1}')"

printf 'COMMIT=%s\n' "$COMMIT"
printf 'BUILD_A_SHA256=%s\n' "$HASH_A"
printf 'BUILD_B_SHA256=%s\n' "$HASH_B"

if [ "$HASH_A" = "$HASH_B" ] && cmp -s "$FILE_A" "$FILE_B"; then
  echo "REPRODUCIBLE=PASS"
else
  echo "REPRODUCIBLE=FAIL" >&2
  exit 1
fi
~~~

This is a **complete Bash script** for Linux and Unix environments with `sha256sum`. It uses **two worktrees at the same COMMIT**, with **two separate Maven local repositories or Gradle user homes**.

Key points:

1. **MODE** picks Maven or Gradle; the script **never cross-compares both tools**.
2. **COMMIT** is resolved once, guaranteeing both checkouts share the exact source revision.
3. **mktemp -d** creates an isolated temporary workspace avoiding outputs from the working project.
4. **git worktree add --detach** creates two clean checkouts from one commit, preserving Git metadata so plugins needing revision details see the exact same commit.
5. **clean package / clean bootJar** executes inside each worktree with isolated `target`/`build` directories.
6. **-Dmaven.repo.local** and **GRADLE_USER_HOME** isolate caches; wrapper distributions/dependencies may download twice. Both still hit external repositories, so remote inputs are not guaranteed immutable if repositories serve mutable versions.
7. **sha256sum** computes real digests. **awk** extracts the digest without filepaths; comparing raw `sha256sum` lines with differing A/B paths would cause string comparison to fail despite matching checksums.
8. **cmp -s** verifies files byte-by-byte when digests match.
9. **exit 1** on mismatch lets CI fail the gate.
10. **trap cleanup** removes both Git worktrees and the temp directory on exit. To investigate on FAIL, temporarily modify the script to **retain the workspaces** instead of cleaning immediately; remember to clean up after analysis.

**Cleanup warning:** the script only deletes the **TMP directory created by mktemp** and the two registered worktrees. Never run the script after replacing `mktemp`/`TMP` with an arbitrary unverified path, because `cleanup` will delete that path. Review carefully before copying into CI.

### 8.3. Invoking and Stdout

For a Maven project:

~~~bash
bash scripts/check-repro.sh maven
~~~

For a Gradle project:

~~~bash
bash scripts/check-repro.sh gradle
~~~

If **both JARs are byte-identical**, the end of output includes:

~~~text
COMMIT=<measured Git commit ID>
BUILD_A_SHA256=<SHA-256 of JAR A>
BUILD_B_SHA256=<same SHA-256>
REPRODUCIBLE=PASS
~~~

The script also prints Git/Maven/Gradle logs, so **output is not limited to those four lines**. Both hashes are live measured outputs, with no precomputed digest fixed in documentation. On FAIL, the script prints **REPRODUCIBLE=FAIL** and exits non-zero.

**Boundary of evidence:** this command proves reproducibility across two clean working trees on the same host with the external inputs resolved during the run. It does not by itself prove cross-platform reproducibility or stability months later.

### 8.4. Manual Alternative Without Using the Script

Before automating in CI, learners can test manually:

~~~bash
./mvnw -B -ntp clean package
sha256sum target/repro-demo-1.0.0.jar
~~~

Then check out the same commit in **another clean directory**, run the exact same command, record the hash, and compare. For Gradle, use **./gradlew --no-daemon clean bootJar** and path **build/libs/repro-demo-1.0.0.jar**.

**It is insufficient** to run **mvn package** twice in the same directory without `clean`, or compare the SHA of a stale JAR left in the output folder. Manual tests must ensure outputs are cleared and sources remain untouched.

## 9. Windows PowerShell: Checking SHA-256 Without sha256sum

Windows includes the **Get-FileHash** cmdlet. Once two builds exist at paths A and B, run in PowerShell:

~~~powershell
$a = Get-FileHash -Algorithm SHA256 -LiteralPath "C:\build-a\target\repro-demo-1.0.0.jar"
$b = Get-FileHash -Algorithm SHA256 -LiteralPath "C:\build-b\target\repro-demo-1.0.0.jar"

Write-Output ("BUILD_A_SHA256=" + $a.Hash)
Write-Output ("BUILD_B_SHA256=" + $b.Hash)

if ($a.Hash -eq $b.Hash) {
    Write-Output "REPRODUCIBLE=PASS"
} else {
    Write-Output "REPRODUCIBLE=FAIL"
    exit 1
}
~~~

This is an **illustrative PowerShell comparison script**: `C:\build-a` and `C:\build-b` are paths where you must actually create two source checkouts and build them, **not pre-existing directories**. For Gradle, update `target/...` to **build\libs\repro-demo-1.0.0.jar**.

**Note:** PowerShell compares hex strings cleanly rather than running a byte-by-byte `cmp` directly. If you need independent binary comparison, use an environment binary compare tool or read both streams; matching SHA-256 already provides strong practical evidence.

On Windows, Maven builds use **mvnw.cmd** and Gradle builds use **gradlew.bat**. Never paste Bash/`mktemp`/`sha256sum` syntax into PowerShell 5.1 expecting all commands to work verbatim.

## 10. Verifying Exactly Which Artifact Is Being Hashed

In a Spring Boot Gradle project, a **build** command can produce:

~~~text
build/libs/repro-demo-1.0.0.jar        # executable bootJar
build/libs/repro-demo-1.0.0-plain.jar  # plain jar
~~~

With Maven Spring Boot parent, after repackaging without a classifier, there are typically:

~~~text
target/repro-demo-1.0.0.jar           # executable Boot JAR
target/repro-demo-1.0.0.jar.original  # pre-repackage JAR, when present
~~~

**Never compare plain against executable**, and never grab the first match of **build/libs/*.jar** because globbing can pick the wrong file. Stick to the exact archive type and path produced by the same task.

Use the JDK to inspect entries:

~~~bash
jar tf target/repro-demo-1.0.0.jar
~~~

or:

~~~bash
jar tf build/libs/repro-demo-1.0.0.jar
~~~

A standard Boot executable JAR contains entries under:

~~~text
BOOT-INF/classes/com/example/repro/ReproApplication.class
BOOT-INF/lib/...
META-INF/MANIFEST.MF
~~~

**When both JARs share the same SHA-256**, run one or both with **java -jar** to verify the artifact still boots properly. **Reproducible does not mean correct**: you can reproduce a broken build.

## 11. If SHA-256 Hashes Differ: Systematic Root-Cause Analysis Without Guessing

### Step 1: Confirm Inputs Truly Match

Verify both checkouts share the exact Git commit, Gradle/Maven Wrapper, JDK vendor/patch version, and build commands/flags. If one run passed **-DskipTests** or **-PprofileA**, the project can produce a different artifact—that is differing input, not a reproducibility bug.

Check whether the build used dynamic/snapshot dependencies, unpinned plugin versions, or network-fetched resources during build time.

### Step 2: Confirm Exact Artifact and Size

Compare filenames and sizes with **ls -l** on Linux/macOS or **Get-Item** in PowerShell. Matching sizes can still differ in bytes; differing sizes guarantee differing bytes. Never treat matching sizes as PASS.

### Step 3: Compare ZIP Entry Lists

Run:

~~~bash
jar tf /path/to/build-a/repro-demo-1.0.0.jar
jar tf /path/to/build-b/repro-demo-1.0.0.jar
~~~

Listings can reveal:

- Build A contains an extra **META-INF/build-info.properties** or generated file.
- Build B added/swapped a dependency JAR in **BOOT-INF/lib**.
- Entry ordering differs.
- Certain resource/class files differ.

If entry names differ, inspect source/resource copy tasks, dependencies, and code generation.

### Step 4: Compare ZIP Metadata and Timestamps

If `unzip`/`zipinfo` is installed:

~~~bash
unzip -lv /path/to/build-a/repro-demo-1.0.0.jar
unzip -lv /path/to/build-b/repro-demo-1.0.0.jar
~~~

**unzip -lv** shows compression methods, sizes, and entry timestamps (exact output depends on version). If file contents appear identical while timestamps/order differ, inspect **outputTimestamp** in Maven or **preserveFileTimestamps/reproducibleFileOrder** in Gradle.

### Step 5: Extract Both JARs to Diff Each Entry

Create two separate temp directories, unpack each JAR into its own folder, and diff contents. Example on Unix:

~~~bash
mkdir -p /tmp/jar-a-inspect /tmp/jar-b-inspect
cd /tmp/jar-a-inspect
jar xf /path/to/build-a/repro-demo-1.0.0.jar
cd /tmp/jar-b-inspect
jar xf /path/to/build-b/repro-demo-1.0.0.jar
diff -qr /tmp/jar-a-inspect /tmp/jar-b-inspect
~~~

**This is an inspection example**: replace **/path/to/...** with real paths, and ensure inspect directories are empty before extracting so old files do not contaminate results. **jar xf** extracts into the current working directory; do not run it in the project root unless you want `BOOT-INF` and `META-INF` created there.

**Note:** if extracted files match while JAR hashes differ, the cause is **ZIP metadata, compression, entry ordering, or permissions/timestamps**, not entry logic contents.

### Step 6: Use diffoscope If Available

**diffoscope** is a dedicated artifact diffing tool that displays ZIP metadata, Java class details, and internal file diffs. It is an **optional tool**, not installed by default with JDK/Maven/Gradle. When available:

~~~bash
diffoscope /path/to/build-a/repro-demo-1.0.0.jar /path/to/build-b/repro-demo-1.0.0.jar
~~~

Interpret its output carefully: differing timestamps, differing generated files, differing manifests, or differing dependency JARs. Never change everything at once and lose track of the root cause.

### Step 7: Fix the Root Cause, Rerun A/B

Examples:
- Differing archive timestamps → configure timestamp normalization.
- Differing entry order → configure reproducible file order/custom tasks.
- Differing Build-Info time → omit dynamic values or pin to the same input.
- Differing Manifest Build-Revision → read revision from the same commit.
- Differing H2/Guava/starter/dependency ZIPs → pin versions, enforce immutable repositories/checksums.
- Differing bytecode → pin JDK compiler vendor/patch, processors, compiler options.
- Resource embeds absolute path → strip host paths from artifacts or normalize inputs.

After each fix, rerun **two clean builds** and re-compare SHA-256; never claim FIXED just because a warning vanished.

## 12. Reproducible Builds Are Not Build Caches or Incremental Builds

| Concept | Purpose | Verification check |
| --- | --- | --- |
| **Incremental compilation** | Recompiles only changed parts | Gradle/Maven runs faster when inputs are unchanged |
| **Up-to-date checks** | Skips tasks when outputs remain valid | Gradle task reports `UP-TO-DATE` |
| **Build cache** | Reuses outputs keyed by input fingerprints | Task reports `FROM-CACHE` on cached output |
| **Dependency cache** | Avoids re-downloading cached libraries | Artifacts loaded from local cache |
| **Reproducible artifact** | Identical inputs yield **identical bytes** | Two clean builds, matching SHA-256 and/or `cmp` |
| **Supply-chain verification** | Confirms origin/integrity of inputs/outputs | Signatures, provenance, checksums, SBOM, policies |

A **FROM-CACHE** outcome does not prove build B from source regenerates the exact same artifact if executed fresh; it may merely restore A's cached output. Stronger tests use **isolated caches** or disable the build cache during verification.

In Section 8's script, **GRADLE_USER_HOME** and **maven.repo.local** are isolated between A and B. To ensure no organization-configured external build cache interferes, verify active remote caches, settings, and environment variables. With Gradle, pass **--no-build-cache** when CI requires uncached task verification; Maven may likewise use extensions that require explicit control.

## 13. Testing Inside Two Clean Containers/Runners

### 13.1. Levels of Evidence

Evidence falls into tiers:

1. **Two clean runs in the same directory**: catches timestamps, yet shares hidden workspace state.
2. **Two separate Git checkouts/worktrees on the same host**: removes most stale outputs and tests differing source paths intentionally.
3. **Two independent runners/containers using the same image digest**: isolates environments better and pins OS/JDK/tools.
4. **Two different OSes or architectures**: validates cross-platform reproducibility, harder due to native tools/file metadata.
5. **Independent source rebuild by a third party**: advances verifiable/reproducible supply chains and provenance.

This exercise achieves level 2; CI setups can advance to level 3.

### 13.2. What Should Be Pinned in Containers?

- **Container image by immutable digest**, not `latest` or mutable tags.
- **JDK vendor + exact update version**, not merely Java major 17.
- **Maven/Gradle Wrapper**, plugin versions, and repositories.
- **Dependencies/lockfiles/verification metadata** when used by the project.
- **Locale/TZ/encoding** if codegen or plugins read the environment.
- **Source commit**, submodules, LFS objects, and build scripts.
- **Never share a mounted output directory** between the two jobs.
- **Never let resource-generation steps depend on live time** or unpinned mutable services.

**Matching results across two containers from the same image** still cannot unconditionally guarantee future builds if dependencies are mutable or scripts hit the internet dynamically.

## 14. Integrating SHA-256 Comparison into CI/CD

### 14.1. Per-Project Gate

On a Linux CI runner with Git/JDK/Gradle/Maven provisioned per policy, run:

~~~bash
bash scripts/check-repro.sh maven
~~~

or:

~~~bash
bash scripts/check-repro.sh gradle
~~~

CI treats exit code **0** as A/B PASS, exit code **1** as differing artifacts, and exit code **2** as invalid script usage. The script can also fail due to missing dependencies, wrappers, network, or permissions; **do not misinterpret those failures as a SHA mismatch** if comparison never ran.

Store **commit ID, build image digest, toolchain versions, A/B SHA-256 hashes, and logs** in the build report. You need not retain both artifacts on every pull request if storage costs are high, yet on FAIL retain both JARs as CI artifacts for `diffoscope` inspection.

### 14.2. At Release Time

Best practice:

1. Build and run tests on the pinned source commit.
2. Produce artifacts with pinned toolchains/dependency versions.
3. Rebuild in an independent environment per policy and compute A/B SHA-256.
4. If they match, publish **the hash alongside the release artifact** and provenance.
5. Sign the artifact/checksum and push to an immutable registry/repository per organizational workflow.
6. When consumers download the artifact, verify checksums and signatures where present.

**Note:** matching A/B SHA-256 digests only demonstrates **reproducibility under tested conditions**. It does not replace unit/integration tests, static analysis, vulnerability scanning, license checks, or security reviews.

### 14.3. When Releasing a Docker Image

There are two distinct digests:

- **Spring Boot JAR SHA-256**: exact hash of the JAR file's bytes.
- **Container image digest**: hash of manifest/layers/config per OCI/image format, also depending on Dockerfile, base image, layer timestamps, and build tooling.

Identical JARs do not guarantee **identical Docker image digests** if image creation embeds varying timestamps/metadata. If the lesson target is the JAR, **hash the JAR before placing it in the image**. When pursuing reproducible container images, design separate tests for full OCI images and layers.

## 15. Inspecting Differences with Java 17 (Independent of OS SHA Tools)

To avoid depending on `sha256sum` across operating systems, use **MessageDigest** in Java 17 to compute SHA-256.

Create **Sha256Compare.java** at the project root (alongside `pom.xml` or `build.gradle`), **outside** `src/main/java` because it is a build verification utility, not part of the application.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class Sha256Compare {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java Sha256Compare.java <artifact-a> <artifact-b>");
        }

        String a = sha256(Path.of(args[0]));
        String b = sha256(Path.of(args[1]));

        System.out.println("BUILD_A_SHA256=" + a);
        System.out.println("BUILD_B_SHA256=" + b);

        if (a.equals(b)) {
            System.out.println("REPRODUCIBLE=PASS");
        } else {
            System.out.println("REPRODUCIBLE=FAIL");
            System.exit(1);
        }
    }

    private static String sha256(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream stream = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

This is a **complete Java 17 single-file source launcher program**, using **MessageDigest**, **Files**, and **HexFormat** from the JDK. It streams files rather than loading large JARs entirely into RAM.

Once both JARs exist, pass the real paths:

~~~bash
java Sha256Compare.java /path/to/build-a/repro-demo-1.0.0.jar /path/to/build-b/repro-demo-1.0.0.jar
~~~

**/path/to/... are illustrative paths to replace with real files.** For Gradle, use the corresponding `build/libs` paths.

If both files match, the program prints:

~~~text
BUILD_A_SHA256=<measured digest>
BUILD_B_SHA256=<same measured digest>
REPRODUCIBLE=PASS
~~~

For differing files, the final line is **REPRODUCIBLE=FAIL** and exit code is 1. **No SHA-256 is predetermined before building**. Unlike the Bash script in Section 8, this Java verifier compares hashes only without invoking `cmp`; add direct byte comparison when needed.

## 16. Scenarios to Interpret Accurately

### 16.1. Two JARs from the Same Source Differ Only in Timestamps: Should You Care?

If sources, class bytecode, and dependencies are unchanged while ZIP entry timestamps differ, the application may behave identically. Nevertheless, the **reproducible build goal failed** under byte-for-byte standards. Where environments rely on artifact signing, caching, provenance, or release verification, this discrepancy still warrants fixing.

### 16.2. Two JARs Share the Same SHA-256 Despite Source Changes?

Matching SHAs mean identical artifact bytes, not necessarily identical Git commits. Source changes may have touched only comments or test code excluded from the packaged artifact. Always **record the commit ID** and toolchain rather than inferring source equality backwards from a hash.

### 16.3. Test Code Changed, Yet Boot JAR Stayed Identical?

Since test classes/resources are not packaged into the main Boot JAR, test edits need not alter the JAR. That can be completely normal; still, test changes affect release qualification even when the artifact is byte-identical.

### 16.4. Should Maven and Gradle Building the Same App Produce the Same SHA?

**No.** The two tools differ in archive packagers, compiler/bytecode settings, manifest metadata, and ZIP entry/compression/ordering behavior. Compare **Maven A vs. Maven B**, or **Gradle A vs. Gradle B** first. Cross-tool byte identity is a separate goal requiring dedicated configuration and testing.

### 16.5. Dependency Version Pinned, Yet Overwritten Under the Same Coordinate

A repository allowing overwrites under the same GAV can serve Maven/Gradle different bytes a few hours later. Enforce immutable release repositories and dependency checksum verification. **Version pinning does not replace checksum pinning** when artifact sources are untrusted or mutable.

### 16.6. Does Using a “Fake” Fixed Timestamp Lose Build Information?

A reproducible ZIP anchor must not be confused with actual build execution time. Real release timestamps belong in **CI provenance, release manifests, or build logs**. The key is **separating content-defining metadata** from **per-run operational metadata**.

### 16.7. Comparing Plain JAR, Sources JAR, WAR, and Containers Too

Always compare each type against its exact counterpart: `bootJar` A vs `bootJar` B, `plainJar` A vs `plainJar` B, `sourcesJar` A vs `sourcesJar` B, `bootWar` A vs `bootWar` B. Each artifact uses its own task/format and may require separate reproducibility settings. Never extrapolate from Boot JAR PASS that all other artifacts PASS.

## 17. Common Pitfalls and Fixes

**Pitfall 1 — Comparing only `java -jar` stdout.** Both printing `REPRO_BUILD_OK` does not prove byte-identical JARs. **Fix:** hash the two final artifacts themselves.

**Pitfall 2 — Hashing the source ZIP instead of the executable JAR.** The goal is the built artifact; source ZIPs can match even when build outputs diverge. **Fix:** hash `target/repro-demo-1.0.0.jar` or `build/libs/repro-demo-1.0.0.jar`.

**Pitfall 3 — Comparing Maven Boot JAR against Gradle Boot JAR.** Differing tooling and ZIP packaging choices constitute different inputs. **Fix:** compare two runs of the same tool and configuration first.

**Pitfall 4 — Running twice in the same directory without cleaning.** Old outputs can be reused; the test does not verify clean builds. **Fix:** two clean checkouts and clean builds.

**Pitfall 5 — Sharing an artifact output directory between A and B.** One build can overwrite or pick up the wrong file. **Fix:** separate worktrees and output directories.

**Pitfall 6 — Comparing raw `sha256sum` lines including filepaths.** Matching hashes with different paths cause string comparisons to fail. **Fix:** compare only the 64-character digest (`awk` field 1).

**Pitfall 7 — Checking only JAR file size.** Equal sizes do not imply equal bytes. **Fix:** SHA-256 and `cmp`.

**Pitfall 8 — Differing ZIP entry timestamps.** Source files copied with differing modified times. **Fix:** Maven `outputTimestamp`; Gradle `preserveFileTimestamps=false`.

**Pitfall 9 — Unstable ZIP entry ordering.** Filesystem traversal or custom tasks vary ordering. **Fix:** Gradle `reproducibleFileOrder=true` and audit other packagers.

**Pitfall 10 — Using Spring Boot `build-info` with live time.** `META-INF/build-info.properties` gets differing `build.time`. **Fix:** use a deterministic timestamp or omit `build.time` when unneeded.

**Pitfall 11 — Manifest embeds username/hostname or absolute paths.** Two runners emit different metadata. **Fix:** avoid embedding unneeded host values; store them in CI provenance.

**Pitfall 12 — Gradle configures `jar` task, skips `bootJar`.** Plain JAR may reproduce while executable JAR differs. **Fix:** configure `AbstractArchiveTask`/`bootJar` properly and compare the Boot JAR.

**Pitfall 13 — Maven configures `maven-jar-plugin`, ignores Boot repackage.** Boot plugin rewrites the final archive, potentially reintroducing differences. **Fix:** ensure `outputTimestamp` applies to both stages.

**Pitfall 14 — Dynamic versions or non-immutable SNAPSHOTs.** Dependencies shift between A and B. **Fix:** pin versions and verify checksums.

**Pitfall 15 — Differing JDK vendors/patches.** Compiler outputs or tool defaults can vary. **Fix:** pin JDK vendor + exact version via Gradle toolchain/Maven compiler.

**Pitfall 16 — Scripts using dates/UUIDs in resource generation.** Build inputs change every run. **Fix:** eliminate randomness or derive from fixed source data.

**Pitfall 17 — Generated code depends on Map or filesystem order.** Emitted classes/sources shift. **Fix:** sort input keys/files deterministically in the generator.

**Pitfall 18 — Picking Gradle `-plain.jar` or Maven `.jar.original` by mistake.** Hashes reflect the wrong artifact type. **Fix:** select the Boot executable JAR emitted by the target task/goal.

**Pitfall 19 — Remote build cache enabled, assuming matching hashes prove deterministic compilation.** Run B may just restore A's cache entry. **Fix:** isolate caches or pass `--no-build-cache` in independent checks.

**Pitfall 20 — Hashes differ yet script exits 0.** CI misses regressions. **Fix:** compare digests/`cmp` and exit non-zero on mismatch.

**Pitfall 21 — Unpacking both JARs into the same directory.** Files overwrite one another, invalidating diffs. **Fix:** separate inspection directories and clean beforehand.

**Pitfall 22 — Discarding both artifacts on CI FAIL.** Insufficient evidence to find root cause. **Fix:** upload both JARs, versions, and logs for `diffoscope` analysis.

**Pitfall 23 — Claiming cross-platform reproducibility after two builds on one host.** Claim exceeds tested scope. **Fix:** state exact evidence tier and test across distinct runners/OSes when required.

**Pitfall 24 — Treating matching hashes as absolute security proof.** Both builds could still include a malicious dependency. **Fix:** separate reproducibility from supply-chain verification, SBOMs, signatures, and security checks.

## 18. Checklist Before Finalizing SHA-256 Results

- [ ] Record the **Git commit ID** and external non-Git dependencies.
- [ ] Explicitly select **Maven Boot JAR** or **Gradle bootJar**, never plain JAR by mistake.
- [ ] Pin Maven/Gradle Wrapper, JDK 17 vendor/patch, Spring Boot plugin, and dependencies.
- [ ] Disable/omit unneeded live build-time data in generated resources/manifests/build-info.
- [ ] Maven configures **project.build.outputTimestamp** for archive creation and repackage.
- [ ] Gradle sets **preserveFileTimestamps=false** and **reproducibleFileOrder=true** on relevant archive tasks.
- [ ] Create **two clean checkouts/worktrees of the same commit**.
- [ ] Use separate output directories and, where possible, separate dependency caches.
- [ ] Run **clean package** or **clean bootJar** in each checkout.
- [ ] Verify both files actually exist and are the same artifact type.
- [ ] Compute **SHA-256 per file**, comparing hash values rather than full filepath lines.
- [ ] Run **cmp** for byte-by-byte verification when tooling supports it.
- [ ] On FAIL, compare entries, timestamps, manifest, generated code, and dependency graph.
- [ ] On PASS, proceed with **java -jar** smoke tests and remaining quality gates.
- [ ] Report **COMMIT, toolchain, hashes, PASS/FAIL outcome**, and tested environment scope.
- [ ] When release security requires it, add signatures, provenance, and dependency checks.

## 19. Official Reference Documentation

- Gradle — Reproducible Archives / Working with Files: https://docs.gradle.org/8.5/userguide/working_with_files.html
- Gradle — AbstractArchiveTask API, preserveFileTimestamps and reproducibleFileOrder: https://docs.gradle.org/8.5/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Maven — Guide to Configuring Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Maven JAR Plugin — outputTimestamp: https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html
- Spring Boot 3.3 Maven Plugin — Repackage / outputTimestamp: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 Gradle Plugin — Executable Archive Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Oracle Java 17 — MessageDigest API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Oracle Java 17 — HexFormat API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- Reproducible Builds — Definitions and background: https://reproducible-builds.org/docs/definition/

**Remember:** to conclude two builds from the same source are reproducible, build **the exact same executable Spring Boot JAR** from **two clean checkouts of the same Git commit**, using **pinned toolchains/dependencies**, normalized **ZIP timestamps and file ordering**, then **compare SHA-256** (and verify bytes directly when possible). **Matching hashes** are strong evidence of byte identity under tested conditions; **differing hashes** are a signal to locate the exact varying input/packaging metadata rather than skipping the check.