# Distinguishing Recreating the Build Environment from Producing Byte-for-Byte Identical Artifacts

## 1. Two Closely Related Goals That Are Not the Same

In a Java/Spring Boot project, the statement **“this build is reproducible”** can mean different things. Person A wants a colleague to install the right Java, Maven, and dependencies so `mvn clean package` succeeds. Person B wants to take the same source code, rebuild it on an independent machine, and obtain a `.jar` file with **every single byte identical** to the release artifact. These are **two different levels of evidence**.

**Recreating the build environment** means identifying and accurately reconstructing the inputs, tools, and execution conditions: source revision, JDK, Maven/Gradle, plugin versions, dependency graph, repositories, environment variables, and build steps. It enables others to run **the same process**, yet the resulting bytes can still differ.

**Producing a byte-for-byte identical artifact** (*bit-for-bit/byte-for-byte identical artifact*) means two builds produce the specified files with **the exact same byte sequence**—that is, the same size, contents, and SHA-256 (provided you are comparing the right files). Checking via full byte comparison is direct proof; SHA-256 is a very strong practical fingerprint. To achieve this level, in addition to recreating inputs, you must eliminate **sources of nondeterminism** inside the build: timestamps, ZIP entry ordering, embedded paths/users/hostnames, random data, time-dependent generators, differing dependency binaries, and more.

This lesson belongs to the **Reproducible Builds** section of **Spring Boot Build Tooling Packaging**. You will learn how to:

1. Distinguish an “identical” build environment from byte-identical outputs.
2. Identify the parts that create differences even when source, JDK, and Maven versions match.
3. Configure Maven and the Spring Boot Maven Plugin to reduce nondeterminism in executable JARs.
4. Use Java 17 and two independent checkouts to verify raw artifact bytes instead of relying on the feeling that a build “succeeded.”
5. Understand Gradle reproducible archives, toolchains, dependency locking, and the scope of guarantees.
6. Diagnose mismatches in `META-INF/MANIFEST.MF`, `BOOT-INF`, timestamps, dependencies, class files, and metadata.
7. Design CI to **build → compare → publish the exact verified artifact**, rather than inadvertently verifying one file and releasing another.

**Scope:** The focus is reproducibility of **Spring Boot JARs/WARs and build processes**. OCI images, SBOMs, digital signatures, and provenance are mentioned where they affect conclusions, without conflating them with JAR checksums.

## 2. A Useful Scale of Assurance Levels

| Level | What you can claim | Example evidence | What cannot be concluded yet |
| --- | --- | --- | --- |
| 1. Build runs | Source builds successfully on one machine | `mvn clean package` returns exit code 0 | Another build produces similar results |
| 2. Environment is recreatable | Source, tools, dependencies, and commands are locked and recorded | Git commit, Maven Wrapper/JDK, plugin versions, repository policy | The JAR files are byte-identical |
| 3. Product behavior is equivalent | Both artifacts run and smoke tests pass | `java -jar`, HTTP/CLI contract | Both ZIP/JAR files match byte-for-byte |
| 4. Two artifacts are byte-identical | Comparing raw files shows equality | `cmp`, `Files.mismatch`, identical SHA-256 | Other OSes, JDKs, or third parties can reproduce it |
| 5. Independently verified reproducible build | Another party rebuilds from stated source, instructions, and environment and matches artifacts | Two genuinely independent environments, same checksum/artifact set | That it is an absolute proof for all future builds |

According to the Apache Maven documentation, a *reproducible build* is a process that allows recreating bit-for-bit identical copies of an artifact from **the same source, build environment, and instructions**. In practice, a two-run test on the **same machine/same cache** is useful for catching timestamp issues, but it **does not prove** that an independent environment can reproduce the output. Therefore, always record the **verified scope**.

These three statements are not equivalent:

- “Both machines have Java 17 and Maven 3.9” → only partially matches the environment.
- “Both machines ran the same commit and both builds are green” → only proves both builds succeeded.
- “Both executable JAR files built by two machines have the same SHA-256” → provides strong evidence that **those specific files** are byte-identical.

A byte-identical artifact does not mean the code inside is secure or functionally correct. A software bug can be reproduced identically in both builds. Reproducibility supports auditing and supply-chain verification; it **does not replace** testing, security reviews, or trustworthy artifact signing/publishing.

## 3. Input and Output Model of a Build

Think of a build as a transformation:

~~~text
SOURCE
  + TOOLCHAIN (JDK, Maven/Gradle, plugins)
  + DEPENDENCIES (binary bytes, repositories)
  + CONFIGURATION (profiles, properties, resource filters)
  + ENVIRONMENT (OS, locale, timezone, path, filesystem)
  + NONDETERMINISTIC INPUTS (clock, random, network)
               |
               v
       build steps / packaging
               |
               v
      class files + resources
               |
               v
     plain JAR / executable JAR / WAR
~~~

The output **depends on every input that is read**, not just `src/main/java`. A generator might call `Instant.now()`; a plugin might capture the username or checkout path; a build script might embed Git dirty-state or a runtime-specific hostname into `build-info.properties`; a ZIP writer might traverse the filesystem in a different order.

Picture the same commit built twice:

~~~text
Build A: same pom.xml, same JDK17, same Maven, same runtime libs
         archive entry timestamp = 2026-11-09 09:00
Build B: same pom.xml, same JDK17, same Maven, same runtime libs
         archive entry timestamp = 2026-11-09 09:05
~~~

If ZIP file entries store different timestamps, the **raw archive bytes differ** even if the actual Java classes are completely identical. This is a direct counterexample to the inference “same environment ⇒ same checksum.”

Conversely, if building deterministically in two different environments produces byte-identical output, you have **stronger empirical evidence** that environmental differences are controlled or do not affect the artifact.

## 4. Common Sources of Nondeterminism in Java/Spring Boot

| Source of difference | Manifestation in artifact | Mitigation |
| --- | --- | --- |
| ZIP/JAR entry timestamps | Same entries, but different archive SHA-256 | Set a reproducible output timestamp or disable preserving source timestamps |
| ZIP entry ordering | Entry list or positions change | Use plugins/tasks with deterministic file ordering |
| Build date in generated files | `build.time`, manifest, Git properties differ | Use a fixed revision-based timestamp or omit build-time fields |
| UUID/random numbers | Resource names or metadata differ on each run | Supply a fixed seed when justified; avoid randomness in artifacts |
| Absolute build paths | Generated sources/metadata embed `/home/a/...` vs `C:\work\...` | Use relative paths; control generator/debug metadata |
| Username/hostname | Metadata contains builder user or machine name | Do not embed, or embed only stable source-derived data |
| Locale/timezone/encoding | Properties, resource filtering, or formatting differs | Explicit charset, normalization, do not rely arbitrarily on default locale |
| Different JDK/compiler | Different bytecode, debug info, ordering, or jar tooling | Documented toolchain; test on the exact JDK/version/vendor when needed |
| Snapshot/range/dynamic deps | Dependency binaries differ even when POM/source is unchanged | Pin versions, eliminate ranges/SNAPSHOTs for releases; control repositories |
| Changing plugin/task versions | JAR layout, manifest, or compression behavior differs | Manage plugin versions and use a build tool Wrapper |
| ZIP compression/extra fields | Same entry contents, but different raw ZIP | Pin archiver/library/plugin; understand byte-level packaging |
| File permissions/line endings | Resource contents vary by OS checkout | `.gitattributes`, normalization, fixed modes where appropriate |
| Parallel task ordering | Generated lists/services files differ in order | Sort explicitly; do not rely on HashMap/filesystem traversal |
| Mutable external services | Downloads newer code/data or files from network endpoints | Turn external inputs into versioned, verified dependencies |

Two artifacts can contain the **same meaningful classes/resources** yet have different raw ZIP bytes due to entry metadata or compression. You must distinguish **semantic equivalence** from **byte identity**. If the requirement is supply-chain reproducibility, never “ignore a few timestamp bytes” and report byte-identical.

## 5. Locking Down the Build Environment: Necessary Condition, Not the Result

### 5.1. Minimum Inputs to Record

A build record might include:

~~~text
Git revision         : commit SHA of the built source
Working tree         : clean / uncommitted changes?
JDK                  : vendor, feature, patch, architecture
Maven/Gradle         : Wrapper distribution + checksum
Build plugins        : versions; effective POM or Gradle scripts
Dependencies         : resolved coordinates and actual artifact hashes
Repositories         : trusted source, mirrors, immutable policy
Build command        : clean package / bootJar, profiles, skip flags
Environment          : OS/arch, locale, timezone, file encoding
Output artifact      : path, filename, SHA-256
Build time source    : fixed timestamp or SOURCE_DATE_EPOCH policy
~~~

This information helps **recreate the environment and trace root causes**. However, having a complete record file does not by itself make plugins or generated code deterministic.

### 5.2. Maven Wrapper and JDK

A Maven Wrapper such as `./mvnw`/`mvnw.cmd` ensures the project uses the declared Maven distribution version. However, it **does not lock the JDK by itself**; Maven usually runs using the machine's Java unless configured via toolchains or a managed container image.

Check:

~~~bash
./mvnw -version
java -version
git rev-parse HEAD
git status --short
~~~

In Windows PowerShell, use `.\mvnw.cmd -version` if the repo has a Wrapper. If the project does not have a Maven Wrapper, use `mvn -version` and record the Maven version. Do not try running `./mvnw` in a project without that script.

The major JDK version alone is also insufficient for every byte-identity requirement: compiler patches/vendors and platform-dependent tools/generators can affect output. For sensitive releases, pin the toolchain/environment specifically enough and compare checksums across the target environments.

### 5.3. Dependencies and Repositories

In Maven, managing `<dependencyManagement>`/BOM helps lock versions; you still need to avoid version ranges, `-SNAPSHOT` artifacts whose contents can change, and uncontrolled plugin resolution. A Maven coordinate **does not prove by itself** that binary bytes are immutable if the repository allows overwrites. For strong reproducibility, verify both the integrity of resolved artifacts and the repository policy.

In Gradle, you can use version catalogs, dependency locking, and dependency verification. They solve **different tasks**: catalogs manage declared versions, locking preserves resolved versions, and verification checks declared checksums/signatures. Do not claim “we have `gradle.lockfile`, so every downloaded JAR is guaranteed byte-identical” without checking binary integrity and the network environment.

## 6. Maven: Configuring Reproducible Archive Timestamps

### 6.1. project.build.outputTimestamp

Apache Maven recommends setting the `project.build.outputTimestamp` property so compatible Maven plugins use a **deterministic timestamp** instead of the current time when creating archive entries:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

The value above is an ISO 8601 **fixed example value**, not a recommendation that every release forever carry a 2024 timestamp. For a release pipeline, pick a stable value derived from the source/release commit and keep it identical across all rebuilds of the **same revision**.

The Spring Boot Maven Plugin `repackage` goal has an `outputTimestamp` parameter defaulting to the `project.build.outputTimestamp` property. The Maven JAR Plugin and other compatible packaging plugins have a similar mechanism. That helps eliminate differences caused by **archive entry** timestamps.

**What you must not infer:** merely adding a property guarantees identical SHA-256 hashes. If a task writes `build-number=Instant.now()` into a resource, the archive writer property **will not fix the resource contents**. If runtime JAR dependencies differ in bytes, the executable Boot JAR will still differ.

According to current Maven documentation, Maven 3.10+/4.0-beta introduced default reproducible mode behavior. Do not rely on that default across older Maven versions; the clearest approach in a learning example is to **declare the timestamp explicitly** and verify in practice.

### 6.2. SOURCE_DATE_EPOCH and Source Time

`SOURCE_DATE_EPOCH` is a standard environment variable carrying a **Unix timestamp (seconds since 1970-01-01 UTC)** stably derived from source or the release process; supporting tools can use it instead of the wall-clock.

POSIX shell example, when building from a pinned Git commit:

~~~bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
printf 'SOURCE_DATE_EPOCH=%s\n' "$SOURCE_DATE_EPOCH"
~~~

This is an option when the project/toolchain **actually supports reading that variable**. Do not treat `SOURCE_DATE_EPOCH` as a magic switch controlling every Maven/Gradle plugin; verify parameters, versions, and outputs. You can pass it into the POM via an explicitly resolved property if your release policy requires it.

**Avoid:** `<project.build.outputTimestamp>now</project.build.outputTimestamp>`, timestamps that change per build, or values from a CI system that are unstable across two rebuilds. Even synchronized VM/container clocks are not enough; builds of different durations can produce different timestamps if code queries the clock at multiple stages.

### 6.3. Spring Boot build-info Metadata

The Spring Boot Maven Plugin has a `build-info` goal that generates `META-INF/build-info.properties`; the `build.time` field is also **content inside the artifact**. In supporting plugin versions, the `time` parameter defaults to `project.build.outputTimestamp`, or session start time when unset. If you configure the `build-info` goal or add custom generated metadata, inspect the **actual output file** and the current plugin version behavior.

On the other hand, do not strip build metadata solely because hashes differ without understanding how that data is used for audits/rollbacks. You can replace wall-clock time with the source commit timestamp, or place release execution info into a provenance system **outside** the artifact if the deployment contract allows it.

## 7. Complete Hands-On Example: Spring Boot Executable JAR with a Fixed Timestamp

The Java 17+ example below creates a small CLI Spring Boot application. There is no web server or database so external factors do not skew the comparison.

### 7.1. Directory Structure

~~~text
repro-demo/
  pom.xml
  CompareArtifacts.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`CompareArtifacts.java` is a **standalone QA tool at the root**, not inside `src/main/java`. Maven only compiles the application in the standard source directory.

### 7.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
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
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Explanation of each decision:**

- Boot parent `3.3.5` manages dependency/plugin configuration, so the example uses an intentional version set.
- `java.version=17` sets the Java compile target via the Spring Boot parent.
- `project.build.sourceEncoding=UTF-8` controls encoding for supporting plugins/source processing.
- `project.build.outputTimestamp` fixes entry timestamps for the Maven JAR Plugin and Boot repackage when the plugin supports that parameter.
- Maven JAR Plugin `3.4.2` is declared explicitly so timestamp handling does not depend on changing Maven global defaults.
- `spring-boot-maven-plugin` has its version managed by the parent; declaring the plugin binds the `repackage` goal to the package lifecycle via the parent.
- We **did not** add the `build-info` goal or generated files with random timestamps; this example isolates archive byte behavior.

For projects not using the Boot parent, you must bind `repackage` and manage versions independently; never assume any POM containing a Boot dependency automatically builds an executable JAR.

### 7.3. Complete Application.java

Create `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println("repro-demo:ok");
    }
}
~~~

Build from the root:

~~~bash
mvn clean package
java -jar target/repro-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

If the project has a Maven Wrapper, you can replace `mvn` with `./mvnw` (Linux/macOS) or `.\mvnw.cmd` (PowerShell). **The application itself** prints:

~~~text
repro-demo:ok
~~~

The Maven command has its own logs; running Java above does not verify the archive checksum. It only proves **the artifact is runnable**. The next question in this lesson is: can the same commit reproduce **those exact bytes**?

## 8. Measuring Byte Identity with Java 17, Not Just File Size

Create a standalone file `CompareArtifacts.java` at the project root:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareArtifacts {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java CompareArtifacts.java <artifact-a> <artifact-b>");
        }

        Path left = Path.of(args[0]);
        Path right = Path.of(args[1]);

        if (!Files.isRegularFile(left) || !Files.isRegularFile(right)) {
            throw new IllegalArgumentException(
                    "Both artifact paths must be regular files");
        }

        long mismatch = Files.mismatch(left, right);

        if (mismatch == -1L) {
            System.out.println("artifact.byte_identical=true");
        } else {
            System.out.println("artifact.byte_identical=false");
            System.out.println("first.mismatch.offset=" + mismatch);
            System.exit(1);
        }
    }
}
~~~

`Files.mismatch` (available since Java 12, so it runs on Java 17) compares the **bytes** of two files and returns `-1` when identical, or the offset of the first differing byte. The program exits with a non-zero status code when they differ, making it suitable as a CI gate.

Assuming you have built two artifacts per Section 9, run:

~~~bash
java CompareArtifacts.java path/to/build-a.jar path/to/build-b.jar
~~~

**When the two files are byte-identical, the exact stdout** is:

~~~text
artifact.byte_identical=true
~~~

When they differ, the program prints `artifact.byte_identical=false` and `first.mismatch.offset=<actual offset>`, then exits with code `1`. The first mismatch offset depends on the two real files, so **do not** fabricate a fake offset as if a build were run.

If you need a fingerprint to store in a report, POSIX shells can use:

~~~bash
sha256sum path/to/build-a.jar path/to/build-b.jar
~~~

In Windows PowerShell:

~~~powershell
Get-FileHash .\path\to\build-a.jar -Algorithm SHA256
Get-FileHash .\path\to\build-b.jar -Algorithm SHA256
~~~

Compare the digests, **not** the path text. If two files are byte-identical, their SHA-256 digests will be equal. If their SHA-256 digests are equal, in practice this is extremely strong verification evidence; meanwhile `Files.mismatch` directly inspects every byte of the two existing files.

**Distinguish** comparing two executable JARs from comparing source classes. During Boot repackage, a ZIP/JAR file may contain identical class files while differing in timestamps, nested library archives, manifest/ZIP extra fields, or compression, causing the raw artifacts not to match.

## 9. Two Clean Builds from Two Independent Checkouts

### 9.1. Why Not Build Twice in the Same Target?

If you run `mvn package` twice without `clean`, plugins may reuse old outputs or skip tasks; matching checksums in that case **do not show that a fresh build is deterministic**. Even `mvn clean package` twice in the same directory shares the same user home, cache, path, JDK, and OS.

A better first check is to build **the same Git commit in two different checkouts**, running `clean` first in each checkout, and comparing files **by exact name**. This helps catch differences caused by embedded absolute checkout paths, file order, and generated metadata.

### 9.2. POSIX Shell Example with a Fully Committed Git Repo

Assuming the project is at the root of a Git repository, `pom.xml` and sources are committed, and the machine has `git`, `mktemp`, `mvn`, JDK 17, and downloadable dependencies:

~~~bash
set -eu

commit=$(git rev-parse HEAD)
work=$(mktemp -d)

git clone --quiet . "$work/build-a"
git clone --quiet . "$work/build-b"

(
  cd "$work/build-a"
  git checkout --quiet "$commit"
  mvn -B -ntp clean package
)
(
  cd "$work/build-b"
  git checkout --quiet "$commit"
  mvn -B -ntp clean package
)

a="$work/build-a/target/repro-demo-1.0.0.jar"
b="$work/build-b/target/repro-demo-1.0.0.jar"

cmp "$a" "$b"
sha256sum "$a" "$b"
~~~

This is a **complete example script for a committed repo**, not a claim that the code has already been executed in the learner's environment. If `git clone .` is unavailable due to repo policies, you can create two checkouts using an equivalent mechanism, provided they have the **same revision, same inputs, and no stale artifacts**.

Meaning of each step:

- `git rev-parse HEAD` pins the revision, avoiding accidentally building two different commits.
- `mktemp -d` creates an isolated working directory for the test.
- Two `git clone` calls create separate working trees, exposing any embedded absolute paths.
- `mvn -B -ntp clean package` produces the archive from a clean build without relying on old directory outputs.
- `cmp` returns exit code `0` if the raw files match. If `cmp` fails, `set -e` stops the script before the final SHA-256 command; when diagnosing failures, hash both files separately.
- `sha256sum` produces the fingerprint (if execution reaches that line).

**Limitation of this test:** two checkouts on the same machine can still share **the same JDK, Maven installation, home repository/cache, and OS**. If it PASSes, you have a **same-host independent-checkout check**, not cross-machine independent reproducibility proof.

If the project is a multi-module Maven build, the artifact path lives in the corresponding module (e.g., `service/target/...jar`), not necessarily at the root. In a release pipeline, you must verify the entire published **artifact set**, not just pick one file that happened to match.

### 9.3. Two Truly Independent Environments

The advanced step is running two builds on **two clean workers/containers or two machines**, from the same commit and given complete build instructions. Record:

- Git commit, patch/working-tree state.
- JDK vendor/feature/patch, Maven/Gradle distribution/version, and plugins.
- Dependency artifact digests or verified repository snapshot.
- Build command, profiles, OS/arch, locale/timezone, environment variables.
- Path of each artifact and SHA-256.
- Differences between the two environments that could affect output.

Freezing the environment with a container image **pinned by digest** helps recreate tooling, whereas a tag like `maven:latest` can point to new bytes next time. An image digest does not automatically make codegen, network, and timestamps deterministic; it remains **one input control**.

A PASS across two independent setups is stronger than a rebuild on the same machine, yet the scope of proof remains **the specific artifacts and specific conditions tested**.

## 10. Inspecting the Artifact When Checksums Differ

When `Files.mismatch` or `cmp` FAILs, **do not** immediately delete metadata or tweak timestamps at random. Classify the difference:

1. **Do class/resource contents themselves differ?** Compare entries inside the archive; decompile/debug when needed.
2. **Are entry names the same, but ordering differs?** Check ZIP entry creation and plugin versions.
3. **Are entry bytes identical, but timestamps/extra fields differ?** You need normalized archive timestamps and deterministic ZIP tooling.
4. **Does `META-INF/MANIFEST.MF` differ?** Inspect Build-Jdk, Build-By, implementation metadata, or generated attributes.
5. **Do `META-INF/build-info.properties`/`git.properties` differ?** Check build time, source revision, dirty flag, and env-derived values.
6. **Does `BOOT-INF/lib` differ?** Inspect the dependency graph and nested JAR hashes, snapshots/ranges/versions.
7. **Does the binary ZIP still differ even with identical uncompressed entries/metadata?** It may be compression level/implementation, ZIP extra attributes, comments, signatures, or local/central directory order; use appropriate inspection tools.

### 10.1. Inspecting Manifest and Entries

From the JDK:

~~~bash
jar tf target/repro-demo-1.0.0.jar
~~~

If `unzip` is available on Linux/macOS:

~~~bash
unzip -p target/repro-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

A Spring Boot 3.3 JAR normally contains `BOOT-INF/classes`, `BOOT-INF/lib`, and the Boot loader, though you need not hardcode every entry name/order across versions.

Observing archive metadata also matters: `jar tf` only lists entry names; it **does not** prove timestamps or compressed ZIP bytes match. You can use `unzip -v`/`zipinfo` if installed in your environment, or a Java ZIP-inspection program when cross-platform verification is needed.

### 10.2. Identical Entry Contents Are Not Enough for Raw Byte Identity

For example, both archives contain:

~~~text
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/spring-core-x.y.z.jar
META-INF/MANIFEST.MF
~~~

and the bytes **after decompressing each entry** are identical. Even so, the ZIP central directory, timestamps, ordering, and compression metadata can differ → different raw JAR SHA-256. If the goal is a “byte-for-byte reproducible JAR,” never relax the criterion to “entry contents equal” and report PASS.

However, entry-level comparison is very useful for locating the fault: if a class differs, check the compiler/generator; if only ZIP metadata differs, focus on the archiver/plugin. **Never normalize an artifact after release and compare hashes of the normalized copy**, because you are no longer checking the exact bytes users download.

### 10.3. Spring Boot Nested Dependencies

The Spring Boot Maven Plugin `repackage` packages dependencies into `BOOT-INF/lib`. If a runtime dependency has the same Maven coordinates but its bytes were modified by the repository, the executable JAR cannot be byte-identical either.

To inspect:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

A project depends on transitive libraries and other Maven plugins; you must verify resolved versions **and actual binary contents**, not just inspect `pom.xml`. Do not blindly delete the local Maven cache to “fix” a checksum without confirming the repository is a trusted source, as doing so can make the environment less controlled.

## 11. Gradle: Deterministic Archives Are Different from Locking the Toolchain

Gradle provides properties on `AbstractArchiveTask`:

- `preserveFileTimestamps`: when `false`, archive tasks do not preserve differing original timestamps of files.
- `reproducibleFileOrder`: when `true`, file traversal order is made deterministic.

**Starting in Gradle 9.0**, archive tasks such as `Jar`, `Zip`, `War`, `Ear`, and `Tar` are reproducible by default: timestamps are fixed and file ordering is deterministic. With Gradle 8.x or projects that must remain compatible with older versions, configure them explicitly in `build.gradle` (Groovy DSL):

~~~groovy
tasks.withType(
        org.gradle.api.tasks.bundling.AbstractArchiveTask
).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

This snippet is a **fragment placed inside a Gradle project that already has plugins/tasks**, not a complete `build.gradle`. With the Spring Boot Gradle plugin, check the output **of `bootJar`** (and `bootWar` if using WAR) rather than checking only the plain `jar`.

A project should use the Gradle Wrapper for a reproducible tool version:

~~~bash
./gradlew --version
./gradlew clean bootJar
~~~

If a project lacks a Wrapper, record the actual Gradle version used and generate a Wrapper through an authorized process. **The Gradle Wrapper does not automatically guarantee the JVM used by the build process and toolchain**.

Gradle Java Toolchains help select the language and compiler:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

This fragment must go into a project with the Java plugin applied. Toolchains reduce ad-hoc builds using `JAVA_HOME`, though strict byte identity still requires checking JDK vendor/patch and non-JVM tools.

### 11.1. Dependency Locking and Verification

A Gradle project can configure:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

And intentionally create/update the lock state with the project-appropriate command:

~~~bash
./gradlew dependencies --write-locks
~~~

Locking fixes recorded **resolved versions**; dependency verification manages the integrity/trust of downloaded artifacts. Both complement each other. Do not conclude that merely adding `lockAllConfigurations()` without committing lockfiles is enough to reproduce dependencies.

### 11.2. Spring Boot Gradle Plugin Is Not the Maven Plugin

Maven uses `project.build.outputTimestamp` in coordination with plugins. Gradle uses its own task properties; do not copy an XML `<properties>` block from Maven to Gradle and expect `bootJar` to honor it. What you must compare is the **actual output `build/libs/*.jar`**, with exact Gradle/Spring Boot Plugin versions and generated resources.

## 12. Do Not Confuse JAR Reproducibility with Container-Image Reproducibility

A Docker/OCI image contains much more than the JAR:

~~~text
OCI image
  - base OS/runtime image layers
  - JRE/JDK files
  - application JAR or exploded layers
  - filesystem metadata, permissions, timestamps
  - image config, environment, entrypoint, labels
  - image manifest/layer-compression metadata
~~~

Therefore:

- **Identical JAR SHA-256** does not automatically make OCI image digests identical.
- Two different image digests do not prove the JAR inside differs.
- Pinning `FROM ...@sha256:...` controls the base image input; you must still manage timestamps, builders/plugins, buildpacks, metadata, and image compression.
- `spring-boot:build-image` and Spring Boot layered JARs solve a related problem that is **distinct** from Maven `jar/repackage` raw checksums.
- `build-info`, SBOMs, attestations, and signatures typically record provenance/release metadata; if metadata changes or signatures include timestamps/randomness, define **which artifact set must be byte-identical** and which metadata should be generated/trusted separately.

A practical strategy: verify the **executable JAR** SHA-256 first, then verify the **runtime image and image digest** according to pipeline criteria, without collapsing both into an unexplained boolean.

## 13. CI: Separating Build Repeatability, Byte Identity, and Release Verification

A clear pipeline can separate three goals:

~~~text
A. Recreate inputs
   - checkout the exact revision
   - set toolchain/Wrapper/repositories/profiles
   - pin dependency versions, validate integrity
                |
                v
B. Verify deterministic artifact
   - clean build A
   - appropriately independent clean build B
   - SHA-256 / Files.mismatch on the exact JAR/WAR
   - inspect/diff if FAIL
                |
                v
C. Publish exactly verified bytes
   - archive artifact A + checksum
   - do not rebuild and silently upload artifact B
   - promote the same artifact to repository/image/deploy
                |
                v
D. Runtime smoke tests & security controls
~~~

If the goal is solely improving developer onboarding reliability, step A may suffice so others can run the build; if the goal is **independent reproducibility verification** for releases/supply chain, you must complete B with independent environments, identical sources/inputs, and output comparison.

**Never label a build “reproducible” simply because of a Maven cache hit or Gradle `UP-TO-DATE` task.** Cache reuse may return identical bytes without proving the generator will recreate them identically. Testing should include at least one *real clean rebuild*, and for deep verification, separate caches/workspaces/systems appropriately.

### 13.1. Clear Status Reporting in the Pipeline

| Outcome | Correct interpretation |
| --- | --- |
| Builds A and B succeed, hashes differ | Environment runs; byte reproducibility **FAILs** for the tested scope |
| Builds A and B have equal hashes on the same machine | Byte identity **PASSes in a same-host test**; cross-host not yet proven |
| Independent builds have equal hashes, right artifact set | Strong evidence for a reproducible build within the stated scope |
| Same JAR hash, different image digest | Investigate image layers/config/builder; do not conclude JAR is faulty |
| Raw JAR hashes differ, smoke tests all PASS | Functional smoke **PASSes**, byte identity **FAILs** |
| Maven Wrapper and JDK pinned, artifacts not yet compared | Environment preparation **PASSes**, artifact reproducibility **UNKNOWN** |

### 13.2. Outputs Worth Retaining

In a release record, it is useful to store:

- Git commit and clean working-tree status.
- Effective tool versions, build profile, and reproducibility timestamp policy.
- Actual artifact paths, SHA-256 digests, sizes, and classifiers.
- Byte comparison result of the two builds (PASS/FAIL) and comparison environments.
- Logs/ZIP diff report on FAIL.
- The **verified release artifact**, provenance/signature, and deployment method.

Do not dump passwords, tokens, or every environment variable into public logs just to “replay the build.” Reproducibility does not require exposing secrets; builds should isolate secrets and consume dependencies via controlled mechanisms.

## 14. Frequently Asked Questions and Common Missteps

| Situation | Wrong inference | Correct handling |
| --- | --- | --- |
| Two developers both have Maven 3.9/JDK17 | “The JAR SHA-256 is definitely identical” | Check actual versions/dependencies, timestamps, and compare JAR bytes |
| `mvn clean package` is green on both machines | “Reproducible build is proven” | Compare artifact bytes; record the tested environment scope |
| Hashes differ only in some ZIP metadata | “It's just timestamps, so count as PASS” | For byte identity requirements, it is still **FAIL**; fix the archive writer |
| Hashes match after two non-clean `mvn package` runs | “The compiler ran identically again” | Clean builds, independent checkouts, check cache/up-to-date |
| `project.build.outputTimestamp` is set | “Every plugin uses that timestamp” | Check plugin support, generated files, and actual output |
| Dependencies share name and version | “Binaries are definitely identical” | Verify repository immutability/checksums |
| Diff is only in `META-INF/build-info.properties` | “Delete all build metadata” | Identify varying fields, pin time/commit or separate provenance intentionally |
| JAR hash matches, Docker image differs | “JAR is not reproducible” | Compare raw JAR separately; inspect OCI layers/config |
| Same-host comparison PASSes | “Third parties can reproduce from release source” | Rebuild independently using the documented environment/inputs |
| Compiling Java17 with two JDK vendors | “Bytecode is definitely identical” | Test in practice; pin JDK/tools specifically when needed |
| Gradle dependency lock is present | “All dependency artifacts are safe and immutable” | Add integrity verification and repository policy |
| `java -jar` runs fine | “The build is bit-for-bit reproducible” | Run smoke tests for behavior and byte comparisons for reproducibility **separately** |

## 15. Practical Checklist

1. **Define the comparison target**: executable JAR, WAR, sources JAR, docs JAR, or OCI image? Record the artifact set clearly.
2. **Pin the source revision** and eliminate unintended working-tree changes.
3. **Lock the toolchain**: Maven/Gradle Wrapper, appropriate JDK version/vendor, plugin versions, and build commands.
4. **Control dependencies**: versions, snapshots/ranges, repository immutability, and binary integrity.
5. **Set a time policy**: Maven `project.build.outputTimestamp` or `SOURCE_DATE_EPOCH` where tools support it; Gradle archive timestamps/ordering.
6. **Eliminate nondeterministic generated data**: current time, random IDs, absolute paths, locale-dependent output, unordered collections.
7. **Clean-build twice** from the same source in two independent checkouts; for high assurance, use two separate workers/environments.
8. **Compare raw files**: `Files.mismatch`/`cmp` and SHA-256; do not confuse JAR contents with raw ZIP bytes.
9. **If mismatched**, locate differing entries/metadata, check manifest/build-info, file ordering, embedded dependencies, compression, and generators.
10. **Do not weaken the PASS condition** by normalizing artifacts only after release without inspecting raw bytes.
11. **Record the conclusion scope**: same-machine, same-container, cross-host, cross-OS, or independent rebuild.
12. **Publish the exact verified artifact**, do not rebuild before deployment without re-verifying.
13. **Continue runtime/security tests**: byte identity does not replace behavioral quality or security.

### Self-Check

**A.** Both machines run Java17, Maven 3.9, the same Git commit, and have green builds. Does that prove the JARs are byte-identical?

**Answer:** No. Timestamps, plugins, resolved binaries, generated metadata, OS/locale, or ordering can still differ. You must compare the artifacts themselves.

**B.** Two executable JARs have the same list of classes and resources, but different ZIP entry timestamps. Are they byte-identical?

**Answer:** No. The raw archive contains metadata, so SHA-256 can differ even if extracted entry contents match.

**C.** What does configuring `project.build.outputTimestamp` solve, and what does it not solve?

**Answer:** It tells supporting Maven plugins to use a deterministic timestamp for output archives. It does **not** automatically lock the JDK, dependency binaries, random generators, or every self-generated metadata file.

**D.** Two builds on the same checkout both return cache hits and matching hashes. Has independent reproducibility been verified?

**Answer:** No. You need real clean/rebuilds, separate workspaces, and ideally verification from an independent environment.

**E.** An application produces identical JAR SHA-256 hashes, yet `java -jar` fails in production. What is the conclusion?

**Answer:** Byte identity may PASS, while runtime compatibility, profiles, JDK, permissions, network, or external dependencies still need verification. Reproducibility does not equal runtime correctness.

**F.** Gradle 9 has default archive reproducibility. Are all Spring Boot outputs guaranteed byte-identical?

**Answer:** No. Archive task defaults only control certain archive properties; custom generators, dependencies, JDK, and Spring Boot tasks still need verification against real outputs.

## 16. Official Documentation

- Maven — Configuring for Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Spring Boot Maven Plugin — Packaging Executable Archives, outputTimestamp: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot Maven Plugin — build-info time: https://docs.spring.io/spring-boot/maven-plugin/build-info.html
- Gradle — Working with Files, Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html#sec:reproducible_archives
- Gradle — AbstractArchiveTask DSL: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html
- Gradle — Best Practices for Security / Reproducible Artifacts: https://docs.gradle.org/current/userguide/best_practices_security.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Reproducible Builds — SOURCE_DATE_EPOCH specification: https://reproducible-builds.org/specs/source-date-epoch/
- Reproducible Builds — Timestamps: https://reproducible-builds.org/docs/timestamps/
- Java 17 — Files.mismatch: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html

**Remember:** **Recreating the build environment** is controlling conditions and inputs so others can repeat the process. **Producing a byte-for-byte identical artifact** is a measurable outcome on the release file itself and requires eliminating nondeterminism in every build/packaging step. A sound workflow needs **both**, states the verified scope clearly, and publishes **the exact bytes that were compared**.