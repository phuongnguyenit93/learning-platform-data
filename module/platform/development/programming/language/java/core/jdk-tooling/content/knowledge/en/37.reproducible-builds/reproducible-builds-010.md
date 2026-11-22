# Toolchain Audit for Reproducible Builds

## Objectives

After this lesson, you will be able to explain what a toolchain audit is and how it supports reproducible builds; compile a complete list of inputs for a Java build; inspect the source revision, JDK, compiler, runtime, Gradle/Maven Wrapper, plugins, dependencies, and CI environment; lock dependency versions and verify artifact integrity; normalize timestamps, file order, and archive metadata; compare artifacts between two independent builds; identify root causes when checksums differ; and retain evidence so others can independently verify the results.

## 1. What is a toolchain audit?

A **toolchain audit** is the inventory and verification of the tools, versions, configurations, and environment involved in producing an artifact. For a Java project, the toolchain is not just the JDK. It also includes:

- The build tool and the version used.
- The JDK running the build, the compiler, the test launcher, and the Javadoc tool.
- Wrappers, plugins, build extensions, and build logic.
- Direct dependencies, transitive dependencies, and annotation processors.
- Repositories or mirrors providing the artifacts.
- Operating system, CPU architecture, container image, and environment variables.
- Steps for generating sources/resources, packaging, signing, and publishing artifacts.

An audit answers the question: **What inputs did this build use, are they pinned and verified, and can the exact artifact be reproduced from the same source revision?**

A toolchain audit is part of the reproducible build workflow. It does not make a build reproducible on its own; it helps uncover uncontrolled inputs and provides the data needed to fix them.

## 2. What does a reproducible build mean?

A build is reproducible when the same source code, build instructions, and defined environment can be built independently to produce byte-for-byte identical artifacts.

For example:

- Build A produces `service.jar` with a specific SHA-256 fingerprint.
- Another agent checks out the same commit and runs the build again.
- Build B produces `service.jar` with the same SHA-256.
- When two files are byte-for-byte identical, their checksums match.

If two files are functionally identical but differ in bytes, they are not yet byte-for-byte reproducible. The difference may simply be due to timestamps in the ZIP/JAR, entry ordering, manifest, compiler metadata, or generated files; investigation is still required.

### Distinguishing four concepts

| Concept | Meaning |
|---|---|
| Repeatable build | The build can be re-run in the same environment and produce consistent results |
| Deterministic build | The same set of declared inputs always produces the same output |
| Reproducible build | An independent party can recreate the artifact from the source and build instructions |
| Hermetic build | The build reads only declared inputs; it has no implicit dependencies on the machine, network, or external state |

These concepts are related but not synonymous. A build can be repeatable on a developer's machine while still depending on the home directory, caches, local files, or an undeclared JDK. When moved to another machine, the output may change.

### Why audit?

- Investigate why two CI runners produce different artifacts.
- Verify that a release artifact was actually built from the reviewed commit.
- Detect unintended dependency or plugin changes.
- Distinguish source bugs from differences caused by the build environment.
- Support caching, release approval, rollback, and supply chain auditing.
- Allow others to verify released artifacts.

## 3. Define the audit scope and target artifacts

Before inspecting tools, determine exactly what needs to be audited:

- Which JAR/WAR/EAR or ZIP?
- A single module or the entire multi-module build?
- Production artifacts, test reports, Javadoc, or container images?
- Which build profile, flavor, or feature flags?
- Are there code generation, native compilation, signing, or packaging steps outside Maven/Gradle?

A repository can produce multiple outputs. Comparing only a single JAR does not prove the entire release bundle is reproducible if images, SBOMs, signatures, or other modules still differ.

Record the artifact path and identifiers. For example:

| Field | Sample value |
|---|---|
| Repository | payments-service |
| Commit | 4d91... |
| Module | service-core |
| Build command | ./gradlew clean build |
| Artifact | service-core/build/libs/service-core.jar |
| Java release | 17 |
| Compiler toolchain | JDK 21 |
| Build tool | Gradle Wrapper |
| Comparison | SHA-256 and archive contents |

The values above only illustrate the audit structure. In practice, collect actual data from the repository and CI job.

## 4. Map of Java build inputs

Break the toolchain into layers to avoid only checking `java --version`.

| Layer | Inputs to inspect | Example evidence |
|---|---|---|
| Source | Commit, branch/tag, dirty tree, submodules, generated sources | Git commit, status, submodule SHA |
| Runtime | JDK vendor, feature/patch/build, architecture | java --version, JAVA_HOME |
| Compiler | JDK compiler, release, encoding, annotation processors | javac --version, compiler config |
| Build tool | Gradle/Maven version and Wrapper | Wrapper properties, --version |
| Build logic | Plugins, extensions, init scripts, convention plugins | plugins, pluginManagement, POM |
| Dependency | Direct/transitive versions, lock, checksum | Lockfile, dependency tree |
| Repository | Repository URL, order, mirror, immutable artifact policy | repositories, Maven settings |
| Environment | OS, kernel, libc, architecture, locale, timezone | Runner image, environment manifest |
| Packaging | Archive timestamps, entry order, permissions, manifest | JAR metadata, archive task config |
| Output | Artifact path, size, SHA-256, provenance | Hash file, attestation |

Each input should have a clear status: pinned, verified, recorded, intentionally variable, or unknown. A value that is only logged but not controlled can still change between builds.

## 5. Start from source identity

Two builds cannot be meaningfully compared if the source revision differs or the working tree has uncommitted changes.

Check:

~~~bash
git rev-parse HEAD
git status --short
git diff --stat
git submodule status
git ls-files
~~~

Confirm that:

1. The commit SHA is the same.
2. The working tree has no uncommitted changes.
3. Submodules are checked out at the exact commit.
4. Generated sources are produced from the same inputs/tool versions.
5. LFS files have their actual content downloaded if the repository uses Git LFS.
6. The build does not read undeclared source files outside the repository.

### Dirty tree and untracked files

A local build may pick up uncommitted or untracked files while CI only checks out the commit. Both builds see the same commit SHA, yet the actual inputs differ.

Do not only record `git rev-parse HEAD`. Also save `git status --porcelain` and ensure release builds run from a clean checkout.

### Submodules and Git LFS

Submodules have their own commits. Record the SHA of each submodule, not just the parent commit. With Git LFS, a Git checkout may contain pointer files if objects have not been fetched; check the LFS status before building.

### Generated source

If sources are generated from OpenAPI, Protocol Buffers, ANTLR, schemas, or templates, control:

- Generator version.
- Plugin and runtime versions.
- Input schemas.
- Ordering of input files.
- Locale, timezone, and timestamps used by the generator.
- Whether generated sources are committed or regenerated in CI.

If generated sources are committed yet CI regenerates them, determine which output is actually compiled.

## 6. Audit the JDK and Java compiler

The JDK is one of the most critical inputs because the compiler version can affect bytecode and metadata in the artifact.

Record at a minimum:

- JDK vendor/distribution.
- Feature release.
- Patch/build number.
- Architecture.
- `JAVA_HOME`.
- Java runtime found on `PATH`.
- Compiler selected by the build tool.
- JDK used to run tests and Javadoc.
- Compiler flags such as `--release`, encoding, debug info, and annotation processors.

Inspection commands:

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java --version
javac --version
java -XshowSettings:properties -version
~~~

`java -XshowSettings:properties -version` can display `java.vendor`, `java.version`, `java.home`, `os.arch`, `file.encoding`, and `user.timezone`.

On Windows PowerShell:

~~~powershell
Write-Output $env:JAVA_HOME
where.exe java
where.exe javac
java --version
javac --version
Get-Command java | Format-List Source
Get-Command javac | Format-List Source
~~~

### Distinguish the build JVM from the compiler toolchain

The Gradle daemon may run on one JDK while compile, test, or Javadoc tasks use a different toolchain. Maven can likewise run on one JDK while the Maven Toolchains Plugin selects a different JDK for the compiler plugin.

Therefore, recording only `java --version` is not enough. Also check:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
mvn --version
~~~

Run the commands corresponding to the build tool in use. `javaToolchains` lists the JDKs/JREs detected by Gradle, along with their vendor, architecture, and detection source.

### Pin the toolchain in Gradle

Groovy DSL example:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

This configuration requests JDK 21 from the Adoptium vendor for Java tasks and targets the Java 17 API/bytecode.

`languageVersion` and `vendor` do not necessarily pin the exact patch/build of the JDK. If strict byte-for-byte reproducibility is required, control the specific JDK image/archive and record the package digest or checksum.

### What role does --release play?

`--release 17` instructs the compiler to:

- Use Java 17 language rules.
- Produce Java 17-compatible class files.
- Compile only against APIs provided in Java 17.

It does not select the compiler JDK and does not make two different compiler versions behave as the same compiler. Pin the JDK toolchain and set `--release` separately to control both the compiler and the compatibility target.

### Maven toolchain

The Maven Toolchains Plugin allows a project to request a specific JDK already installed on the agent. The `~/.m2/toolchains.xml` file maps the requirement to a JDK home.

Example toolchain configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdk/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

The path is an example and must match the actual JDK on the agent. Toolchains select an existing JDK; they do not install one. Verify that the version/vendor requested by the POM matches the entry.

### Annotation processors

Annotation processors are code that runs during the compile phase. Lombok, MapStruct, and internal processors can generate source/class outputs.

Audit the processor version, transitive dependencies, and options passed to the processor. If a processor reads the current time, filesystem, environment variables, or file order, it can cause the output to vary.

## 7. Audit Gradle Wrapper and Maven Wrapper

A wrapper fixes the build tool version for developers and CI. A preinstalled build tool on the machine should not determine the execution version.

### Gradle Wrapper

Key files:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Check:

- `distributionUrl` points to the exact Gradle release and uses HTTPS.
- The version is pinned specifically, not pointing to a dynamic URL.
- `distributionSha256Sum` contains the SHA-256 value obtained from the official release source.
- The Wrapper JAR in the repository matches the official checksum or signature.
- Wrapper files are committed to source control.
- Wrapper changes are reviewed as supply chain changes.

`distributionSha256Sum` verifies the downloaded Gradle distribution ZIP file. It does not automatically verify the committed Wrapper JAR. The Wrapper JAR must be verified separately against its official checksum/signature.

You can check the version with:

~~~bash
./gradlew --version
~~~

Do not run the Wrapper of an untrusted repository before inspecting the wrapper JAR, distribution URL, checksum, and build logic. The Wrapper executes before most project-configured safeguards.

### Maven Wrapper

Common files:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar
~~~

Check:

- `distributionUrl` points to a specific Maven release.
- The URL and repository mirror are trusted.
- `distributionSha256Sum` verifies the Maven distribution.
- `wrapperSha256Sum` verifies the Maven Wrapper JAR if the distribution uses that JAR file.
- Wrapper scripts and properties are committed.
- The Wrapper download does not fetch snapshots or mutable artifacts for release builds.

Run:

~~~bash
./mvnw --version
~~~

Maven Wrapper supports internal repository managers. When using a mirror, verify that the mirror returns the exact same artifact content as the verified source.

### Why are Wrapper checksums important?

Pinning the URL only specifies where to download from. The checksum verifies that the received bytes match the expected artifact.

Obtain checksums from the official release page or independent vendor metadata. Do not hash a newly downloaded file and use that same hash as proof of trust; that only proves you can hash a file, not that the file is an official release.

## 8. Audit plugins and build logic

A build plugin is code that executes during the build. It can alter dependencies, generate files, modify manifests, or download auxiliary tools.

### Gradle

Check:

- Plugin versions in the `plugins` block.
- `pluginManagement` in `settings.gradle(.kts)`.
- Buildscript classpath.
- Convention plugins and `buildSrc`.
- Included builds.
- Init scripts in Gradle User Home.
- Repositories used to resolve plugins.
- Plugins that download tools or spawn external processes.

Avoid dynamic plugin versions such as `latest.release`, version ranges, or snapshots in release builds. Pin reviewed versions.

A plugin can have its own dependency graph. Locking project dependencies does not automatically mean all build logic/plugin resolution is locked. Inspect the buildscript classpath and plugin repositories separately.

### Maven

Check:

- Plugin versions in the POM.
- `pluginManagement` in the parent POM.
- Maven core extensions in `.mvn/extensions.xml`.
- Profiles activated by environment.
- `settings.xml` and mirrors.
- Plugin dependencies and build extensions.
- Which plugins run in lifecycle phases that produce artifacts.

Do not rely on Maven's default plugin version selection when the goal is reproducible builds. Pin plugin versions in the parent POM or `pluginManagement` and inspect the effective POM.

### Remote build logic

A script downloaded via an HTTP URL or a build step that downloads an unpinned executable can change without a new source commit.

Record or remove build logic sources outside the repository. For scripts that must be downloaded, pin the version, checksum/signature, and trusted URL. Never run commands that download a script and pipe it directly into a shell in a release pipeline.

## 9. Audit the dependency graph

A dependency coordinate consists of group, artifact, and version. The same version string can still return different bytes if the repository allows overwriting artifacts or uses snapshot/changing modules.

Check:

- Direct dependencies.
- Transitive dependencies.
- Plugin dependencies.
- Annotation processors.
- Test dependencies.
- Build logic dependencies.
- Version catalogs/BOMs.
- Repository order, mirrors, and content filtering.
- Whether artifacts have an immutable release policy.

### Gradle dependency locking

Gradle supports saving resolved dependency versions into a lockfile. For example:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate or update the lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

The default lockfile name is `gradle.lockfile` and should be committed. Each project/subproject can have its own lock state.

Locking fixes the resolved versions, including transitive dependencies. It does not fix the bytes of a changing dependency such as `SNAPSHOT`; the same coordinates can return different content. Do not treat dependency locking as a substitute for artifact checksum verification.

Note: `lockAllConfigurations()` does not automatically lock the buildscript classpath. If you use script plugins/buildscript dependencies, audit and configure locking for that classpath according to project requirements.

### Gradle dependency verification

Dependency verification checks the checksums or signatures of downloaded dependencies/plugins.

Generate metadata from current dependencies:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

To record both checksums and PGP signatures where available:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

The file is created at:

~~~text
gradle/verification-metadata.xml
~~~

Once the metadata exists, Gradle verifies artifacts in subsequent builds. If a checksum does not match or metadata is missing, the build fails.

**Bootstrap requires review:** the metadata generation command fetches artifacts from the current repositories and records their checksums. If a repository is compromised or the wrong dependency was resolved, the newly generated file can inadvertently trust that artifact. Verify the sources and diff the metadata before committing.

Checksums confirm that bytes have not changed relative to trusted values. Signatures help verify that an artifact was signed by a specific key; that key must still be trusted through a review process.

### Maven dependency audit

Maven typically manages versions through dependency declarations, parent POMs, BOMs, and `dependencyManagement`. To audit the resolved graph, run:

~~~bash
mvn dependency:tree -Dverbose
mvn help:effective-pom
~~~

Check:

- Are there any dependency version ranges?
- Are there any `SNAPSHOT` or mutable versions?
- Are parent POMs/BOMs pinned?
- Are transitive dependencies unexpectedly overridden?
- Are plugin versions fixed?
- Does repository ordering change the artifact source?
- Does the internal repository enforce an immutable release policy?

`dependencyManagement` centralizes version management; it does not prove artifact bytes are immutable. With Maven, save the dependency tree/effective POM for the release and enforce a clear version policy. If your organization uses additional locking or verification tooling, audit those files and verification steps as well.

### Avoid dynamic versions in release builds

Examples to avoid in releases:

~~~groovy
dependencies {
    implementation 'org.example:library:1.+'
}
~~~

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>library</artifactId>
    <version>[1.0,2.0)</version>
</dependency>
~~~

A build today and a build next month can resolve different versions even when the source has not changed. Use fixed versions and lock the resolved graph.

## 10. Audit repositories and artifact origin

A fixed dependency version is not enough if a repository allows overwriting the same coordinates.

Audit:

- Repository URLs and protocols.
- Repository priority order.
- Maven mirrors and Gradle repository content filters.
- Whether an internal proxy/cache repository is used.
- Snapshot/release policies.
- Whether artifacts can be redeployed after publishing.
- Whether plugin repositories are separated from library repositories.
- Whether credentials are passed securely and not written to logs.

For release builds, prefer managed repositories with an immutable release artifact policy. If an internal mirror is needed, record the mirror configuration and verify artifact checksums after download.

Do not let dependency resolution depend on public/private repositories added ad hoc on a developer machine or by an init script outside the audit manifest.

## 11. Audit the OS and CI runner environment

The same JDK version can still produce different builds due to the environment.

Record:

| Component | Examples to record |
|---|---|
| OS | Ubuntu, Windows Server, macOS |
| Kernel | Kernel version |
| CPU | x86_64, ARM64 |
| libc | glibc/musl and version if native tools are used |
| Container | Image tag and immutable digest |
| Filesystem | Case sensitivity, file permissions |
| Locale | LANG, LC_ALL |
| Timezone | TZ, process timezone |
| Charset | file.encoding |
| Line ending | LF or CRLF |
| Working directory | Workspace path |
| Environment | Only allowlisted variables that affect the build |

If the build uses GraalVM Native Image, JNI, C/C++ compilers, or native libraries, also audit the compiler/linker, SDK, libc, and native toolchain. The JDK version alone does not sufficiently describe the environment that builds a native binary.

### Locale, timezone, and encoding

Builds can depend on:

- Locale-dependent string sorting.
- Timezone-dependent date parsing/formatting.
- Default JVM charset.
- Line endings of checked-out files.
- Locale-sensitive code generation.

Set locale/timezone/encoding explicitly if the build depends on them. For example:

~~~bash
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
~~~

Verify that the `C.UTF-8` locale exists on the runner. On Windows, use the OS-appropriate locale configuration and check the JVM charset.

Do not dump the entire `env` into the audit artifact. CI environments can contain tokens, passwords, or credentials. Only record an allowlist of non-sensitive variables that affect the build.

## 12. Audit archives and generated metadata

Even when class files are identical, a JAR/ZIP can differ in bytes due to packaging metadata.

Common sources of differences:

- Entry timestamps inside the archive.
- Entry ordering.
- File permissions.
- Manifest containing a build timestamp or hostname.
- Build metadata containing an absolute path or username.
- Generated resources containing timestamps.
- Resource filtering injecting environment variables.
- File ordering dependent on filesystem traversal.
- Line endings or encoding of resources.

### Gradle archive tasks

Since Gradle 9.0, archive tasks such as `Jar`, `Zip`, `War`, and `Ear` produce reproducible archives by default:

- File entries have deterministic ordering.
- Entry timestamps are fixed per archive type.
- Directory/file permissions are normalized.

For older Gradle versions, configure this explicitly:

~~~groovy
tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Do not re-enable preserving timestamps or filesystem iteration order if the goal is reproducible archives. Inspect custom packaging plugins because they may build archives outside the standard tasks.

### Maven output timestamp

Maven recommends using the `project.build.outputTimestamp` property and plugins that support reproducible builds.

Example in POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

The timestamp is a stable value managed in source control. Some projects use the timestamp of the last commit, but you must ensure the method for obtaining it is stable and normalized to UTC.

This property only takes effect for plugins that support reproducible output. Check each plugin that generates JARs, source archives, Javadoc, assemblies, or reports.

### Manifest and build metadata

Check whether `META-INF/MANIFEST.MF` and generated resources contain:

- `Build-Time`.
- `Build-Host`.
- User name.
- Workspace path.
- Current date/time.
- Random identifiers.
- Tool versions or commit metadata.

Some metadata is a product requirement. If it must be kept, choose deterministic values—such as the commit SHA and a normalized timestamp from the source revision—instead of the runner's wall-clock time.

### SOURCE_DATE_EPOCH

`SOURCE_DATE_EPOCH` is a convention used by some build tools/plugins to normalize timestamps. Not every Java compiler, Maven plugin, or Gradle plugin reads this variable automatically.

Only rely on it after confirming that the specific plugin supports it. For Maven, `project.build.outputTimestamp` is the mechanism documented by Maven; for Gradle, use the appropriate archive task properties.

## 13. Audit Gradle build configuration

A Gradle configuration audit should inspect:

~~~text
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
settings.gradle or settings.gradle.kts
build.gradle or build.gradle.kts
gradle.properties
gradle/libs.versions.toml
gradle.lockfile
gradle/verification-metadata.xml
buildSrc/
build-logic/
~~~

### Inspect plugins and version catalogs

- Are plugin versions pinned?
- Does the version catalog contain version ranges or mutable aliases?
- Do convention plugins have undeclared dependencies?
- Do included builds have their own wrapper/build logic?
- Do init scripts in Gradle User Home interfere with repositories or toolchains?

### Inspect task inputs

Custom tasks must declare inputs/outputs properly. If a task reads files outside the project, environment variables, or service responses without declaring them, Gradle may consider the output up-to-date even when the actual inputs have changed.

Do not mistake a build cache hit for proof of reproducibility. A cache returns previously generated output; to audit byte-for-byte reproducibility, an independent build without relying on the output cache is required.

### Useful Gradle audit commands

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew dependencies
./gradlew dependencyInsight --dependency guava --configuration runtimeClasspath
./gradlew tasks --all
~~~

Replace `guava` and the configuration with your actual dependency. Multi-project builds need auditing across each critical module/configuration.

## 14. Audit Maven build configuration

Inspect these files:

~~~text
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar
.mvn/extensions.xml
.mvn/maven.config
pom.xml
parent-pom.xml
settings.xml
toolchains.xml
~~~

Some files live in the home directory or CI secret store rather than the repository. The audit should record which files/configurations were used, without exposing credentials.

### Effective POM

The final POM can inherit from parents, BOMs, and profiles. Reading a child POM alone is therefore not enough.

~~~bash
mvn help:effective-pom
mvn help:active-profiles
mvn dependency:tree -Dverbose
mvn --version
~~~

Save the appropriate output for the audit, filtering out credentials or repository URLs containing login details before uploading.

### Pin plugins

Set plugin versions in the parent POM or `pluginManagement`, especially plugins that produce artifacts:

- Maven Compiler Plugin.
- Maven Resources Plugin.
- Maven JAR/WAR Plugin.
- Maven Surefire/Failsafe.
- Maven Assembly/Shade.
- Source/Javadoc plugins.
- Plugins that generate build info or generated sources.

Each plugin can have different reproducibility behavior. Use `mvn artifact:check-buildplan` to identify plugins that need to be upgraded to versions supporting reproducible builds.

## 15. Standardize dependencies and build logic

A toolchain audit should evaluate both version stability and content integrity.

| Control | What it proves |
|---|---|
| Wrapper version pin | The build uses the exact Gradle/Maven version |
| JDK toolchain pin | Compile/test uses the required JDK |
| Dependency lock | Dependency resolution uses the exact versions |
| Dependency verification | Artifact bytes/signatures match trusted metadata |
| Plugin version pin | Build logic uses reviewed plugin versions |
| Repository policy | Artifacts come from controlled sources |
| Container digest | The runner image has immutable content |
| Artifact checksum | Output bytes can be compared |
| Attestation | There is evidence of the workflow/source that built the artifact |

No single control replaces all the others. For example, a lockfile fixes versions but does not detect a repository returning a modified JAR; a checksum fixes bytes but does not prove that the version is safe.

## 16. Create an audit manifest for a build

An audit manifest is a concise record of the actual inputs. It should be stored alongside CI artifacts or release metadata.

A minimal manifest might look like:

~~~text
source.commit=4d91...
source.dirty=false
source.submodules=recorded
build.tool=Gradle Wrapper
build.version=9.9
build.wrapper.sha256=recorded
jdk.vendor=Eclipse Adoptium
jdk.version=21.0.x
jdk.arch=x86_64
compiler.release=17
os.image=ubuntu-24.04@sha256:...
locale=C.UTF-8
timezone=UTC
dependency.lock=present
dependency.verification=enabled
artifact.path=build/libs/service.jar
artifact.sha256=...
~~~

The values above only illustrate the format. A real manifest must be generated from inspection commands on the runner and must not record credentials.

### Quick inspection commands on Linux

~~~bash
set -e

echo "SOURCE"
git rev-parse HEAD
git status --short
git submodule status || true

echo "SYSTEM"
uname -a
uname -m
printf 'LANG=%s\n' "$LANG"
printf 'LC_ALL=%s\n' "$LC_ALL"
printf 'TZ=%s\n' "$TZ"

echo "JAVA"
echo "JAVA_HOME=$JAVA_HOME"
java --version
javac --version
java -XshowSettings:properties -version 2>&1

echo "BUILD TOOLS"
if [ -x ./gradlew ]; then
  ./gradlew --version
  ./gradlew -q javaToolchains
fi

if [ -x ./mvnw ]; then
  ./mvnw --version
fi
~~~

If locale variables or `JAVA_HOME` are unset, the shell may print empty values. The audit must treat that as data to investigate rather than inferring the expected version.

### Hash the Wrapper and artifacts

Linux:

~~~bash
sha256sum gradle/wrapper/gradle-wrapper.jar
sha256sum .mvn/wrapper/maven-wrapper.jar
sha256sum build/libs/*.jar
~~~

Only run hashes for files that actually exist. For projects that do not use one of the Wrappers or do not produce JARs at that path, omit the corresponding command.

Windows PowerShell:

~~~powershell
Get-FileHash gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256
Get-FileHash .mvn\wrapper\maven-wrapper.jar -Algorithm SHA256
Get-FileHash build\libs\*.jar -Algorithm SHA256
~~~

Local hashes only provide a fingerprint for comparison. To verify the Wrapper or dependencies, compare against checksums/signatures from an independent, trusted release source.

## 17. Perform two independent builds

A basic verification workflow:

1. Select a specific commit and perform a clean checkout.
2. Use the same wrapper, JDK toolchain, plugins, dependency locks, and verification metadata.
3. Standardize the environment, locale, timezone, encoding, and container image.
4. Run a clean build, avoiding reuse of previous build outputs.
5. Save the artifacts and SHA-256 checksums from the first build.
6. Check out the same commit in a different workspace/agent.
7. Repeat the build with the same inputs.
8. Compare checksums and archive contents.
9. If they differ, use diff tools to locate the differing entry or file.
10. Save the manifest and comparison results.

### Gradle build

~~~bash
./gradlew clean build --no-build-cache
sha256sum build/libs/*.jar
~~~

`--no-build-cache` prevents pulling task outputs from the build cache during this test. The dependency cache may still be used; dependency integrity must be controlled separately via locks and verification metadata.

### Maven build

~~~bash
./mvnw --batch-mode clean verify
sha256sum target/*.jar
~~~

For multi-module projects, select the appropriate artifact path for each module. Ensure profiles, Maven settings, toolchains, and repository mirrors are identical.

### Maven artifact compare

Maven provides `maven-artifact-plugin` to compare two builds:

~~~bash
mvn clean install
mvn clean verify artifact:compare
~~~

The second command rebuilds the project and compares the output against the installed reference. Check the report to see which artifacts differ.

Testing on the same machine can catch some issues like timestamps, but it does not prove reproducibility between two independent parties. For stronger verification, rebuild on a different machine/container with a different workspace and user.

### Compare checksums

Linux:

~~~bash
sha256sum build-a/service.jar
sha256sum build-b/service.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash build-a\service.jar -Algorithm SHA256
Get-FileHash build-b\service.jar -Algorithm SHA256
~~~

Matching checksums are evidence that two files are byte-for-byte identical, given the extremely low collision probability of SHA-256. Differing checksums mean investigation is needed; they do not by themselves indicate whether the issue lies in source, compiler, or packaging.

## 18. Investigate when checksums differ

Do not randomly change multiple settings at once. Compare each input layer and locate the first differing file/entry.

### Step 1: compare archive metadata

List contents:

~~~bash
unzip -l build-a/service.jar
unzip -l build-b/service.jar
~~~

Check entry order, timestamps, sizes, and file names. If only ZIP metadata differs, look for the archive-creating plugin or related resource filtering.

### Step 2: compare manifests

~~~bash
unzip -p build-a/service.jar META-INF/MANIFEST.MF
unzip -p build-b/service.jar META-INF/MANIFEST.MF
~~~

Look for build timestamps, build host, JDK version, commit metadata, or fields added by plugins.

### Step 3: compare class files

Extract both archives into separate directories, then compare:

~~~bash
mkdir -p /tmp/build-a /tmp/build-b
unzip -q build-a/service.jar -d /tmp/build-a
unzip -q build-b/service.jar -d /tmp/build-b
diff -ru /tmp/build-a /tmp/build-b
~~~

If class files differ, check the compiler JDK, compiler flags, annotation processors, generated sources, debug metadata, and dependency classpath.

### Step 4: use diffoscope

`diffoscope` can deeply inspect JAR, ZIP, TAR, and many other formats to pinpoint what differs. This tool is useful when checksums differ but a raw binary diff is hard to read.

With Maven, `artifact:buildinfo` can suggest a `diffoscope` command for mismatched artifacts.

### Step 5: check for environment leaks

Look for embedded values from:

- Username and home directory.
- Workspace absolute path.
- Hostname and IP.
- Current time or timezone.
- Locale and charset.
- Environment variables.
- Filesystem iteration order.
- Random numbers or UUIDs.
- Network responses or remote APIs.
- Differently resolved dependencies/plugins.

After finding the source, change only one factor and re-run both builds.

## 19. Common causes of non-reproducible builds

| Symptom | Possible cause | What to check |
|---|---|---|
| JAR hash changes every time | Timestamps in ZIP/JAR | Archive timestamps and `outputTimestamp` |
| Different entry order | Nondeterministic file traversal | Reproducible file order |
| Different class files | Different JDK/compiler or processor | Toolchain, `javac`, compiler flags |
| Different dependency tree | Dynamic versions, snapshots, repositories | Lockfile, effective POM, dependency tree |
| Different manifest | Build time, hostname, git metadata | Packaging plugin and generated metadata |
| Only CI differs from local | Runner image, locale, timezone, path | Audit manifest and container digest |
| Only one module differs | Plugin/module-specific config | Task graph, plugin version, module lock |
| Artifact differs offline/online | Remote metadata or newer dependency | Repository, metadata cache, snapshots |
| Build passes but checksum differs | Nondeterministic output | `diffoscope` and archive entry diff |
| Build passes only with cache | Missing inputs or undeclared task inputs | Task inputs/outputs and clean build |

### Snapshots and changing dependencies

A `SNAPSHOT` or changing module can keep the same version coordinate while changing bytes. Locking versions cannot fix content that changes over time.

Release builds should use immutable release artifacts and appropriate verification metadata.

### Non-reproducible plugins

A plugin may embed timestamps, hostnames, or unstable file ordering. Maven `artifact:check-buildplan` helps detect plugins that need upgrading to support reproducible output.

With Gradle, inspect plugin archive/task behavior and input/output declarations of custom tasks.

### Absolute paths and user home

A plugin may write the workspace path into generated sources, manifests, or build info. Two runners with different workspace paths will produce different outputs.

Standardize the working directory if the plugin supports it; better yet, fix the plugin to only record relative paths or omit paths from the artifact if unnecessary.

## 20. Build cache does not prove reproducibility

A build cache reuses task outputs when inputs are considered identical. It can mask tasks that fail to declare all inputs or outputs generated in a different environment.

During an audit:

- Run a clean build without using the build cache.
- Compare independently generated build outputs.
- Check input/output declarations of custom tasks.
- Do not treat a cache hit as proof that an artifact can be rebuilt independently.
- Do not delete dependency integrity metadata just to get a cache hit.

The dependency cache and build cache are also different. The dependency cache stores downloaded libraries; the build cache stores task outputs. Both need separate policies.

## 21. Provenance, checksums, SBOM, and reproducibility

The following pieces of evidence answer different questions:

| Evidence | Question answered |
|---|---|
| Artifact SHA-256 | Does this file have the exact bytes recorded in the fingerprint? |
| Dependency verification | Do downloaded dependencies/plugins match trusted bytes/keys? |
| SBOM | Which components/dependencies was the artifact built from? |
| Build provenance/attestation | Which repository, commit, workflow, and environment built the artifact? |
| Independent rebuild | Can another party recreate the same artifact from source and build instructions? |

A valid attestation does not by itself prove an artifact is reproducible. It provides evidence of where and how the artifact was built. A checksum does not by itself prove an artifact is safe; it only identifies the file's content.

GitHub Actions can generate artifact attestations to record the workflow, repository, commit SHA, event, and artifact digest. For binaries, a workflow can use `actions/attest` after building the artifact. Permissions and scope depend on repository type and GitHub plan.

## 22. Example Gradle configuration for reproducible builds

An example combining toolchain, release target, dependency locking, and archive behavior:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencyLocking {
    lockAllConfigurations()
}

tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

To complete the setup, you also need to:

1. Pin the Gradle Wrapper version and checksum.
2. Pin plugin versions in build/settings.
3. Generate and commit lockfiles.
4. Generate and review dependency verification metadata.
5. Check the buildscript/plugin classpath as well.
6. Standardize locale/timezone and runner image.
7. Audit custom tasks and generated files.
8. Run an independent rebuild and compare artifacts.

The example only illustrates the core mechanisms. Real projects may also need to configure test launchers, the Javadoc tool, annotation processors, and native toolchains.

## 23. Example Maven configuration for reproducible builds

A POM snippet:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

A real POM needs to pin versions for all plugins participating in the build, not just the compiler plugin. Choose a stable timestamp according to release policy; check whether output-producing plugins support reproducible builds.

Useful audit commands:

~~~bash
./mvnw --version
./mvnw help:effective-pom
./mvnw help:active-profiles
./mvnw dependency:tree -Dverbose
./mvnw artifact:check-buildplan
~~~

After addressing unsupported plugins, try:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

Compare again on another workspace/agent for independent verification.

## 24. Staged toolchain audit workflow

### Stage A — Inventory

1. Identify artifacts and build commands.
2. Record commit, dirty tree, submodules, and generated sources.
3. Record JDK vendor/version/architecture.
4. Record compiler, test, and Javadoc toolchains.
5. Record Gradle/Maven Wrapper versions and checksums.
6. Record plugins, extensions, and build logic.
7. Record dependency graph, repositories, and lock/verification files.
8. Record OS/container image, locale, timezone, and encoding.

### Stage B — Pin and verify

1. Pin the Wrapper version and verify checksums.
2. Pin the appropriate JDK toolchain.
3. Lock resolved dependency versions.
4. Verify dependency checksums/signatures.
5. Pin plugin and build extension versions.
6. Use immutable repository artifacts.
7. Standardize environment and archive metadata.
8. Review custom tasks and generated outputs.

### Stage C — Independent rebuild

1. Create two clean checkouts of the same commit.
2. Use the same container/toolchain or described environment.
3. Run clean builds and avoid reusing the task output cache.
4. Save artifacts, SHA-256 checksums, and manifests.
5. Compare hashes.
6. Open archives and compare entries if hashes differ.
7. Use `diffoscope` to find deep differences.
8. Fix one source of nondeterminism at a time and repeat.

### Stage D — Retain evidence

1. Save the audit manifest.
2. Save the dependency tree/lockfile and verification metadata.
3. Save build logs and tool versions.
4. Save artifact checksums.
5. Save independent rebuild results.
6. Save SBOM/attestations if supported by the pipeline.
7. Link audit results to the commit and release ID.

## 25. Audit report template

| Group | Observed result | Status | Evidence |
|---|---|---|---|
| Source revision | Commit and dirty state | PASS/FAIL | Git SHA/status |
| JDK | Vendor/version/architecture | PASS/FAIL | Runtime/compiler output |
| Toolchain | Compiler/test/Javadoc | PASS/FAIL | Toolchain report |
| Wrapper | Version and checksum | PASS/FAIL | Wrapper properties/hash |
| Plugins | Fixed versions | PASS/FAIL | Effective POM/build files |
| Dependencies | Lock and verification | PASS/FAIL | Lockfile/metadata |
| Repository | Stable artifact source | PASS/FAIL | Repository config |
| Environment | OS/image/locale/timezone | PASS/FAIL | CI manifest |
| Packaging | Timestamp/order/permissions | PASS/FAIL | Archive config |
| Rebuild | Two artifacts with same SHA-256 | PASS/FAIL | Hash comparison |
| Provenance | Commit/workflow/artifact linked | PASS/FAIL | Attestation |

Do not mark PASS just because a configuration file exists. Verify that the actual build used that exact file/configuration.

## 26. Pre-release checklist

### Source and build tool

- [ ] Commit SHA is recorded.
- [ ] Working tree is clean.
- [ ] Submodules/LFS/generated sources are verified.
- [ ] Gradle/Maven Wrapper is used instead of an arbitrary build tool on PATH.
- [ ] Wrapper distribution and Wrapper JAR checksums/signatures are verified.
- [ ] Plugin and build extension versions are pinned.

### Java toolchain

- [ ] JDK vendor, version, patch/build, and architecture are recorded.
- [ ] The JDK running the build is distinguished from compiler/test/Javadoc toolchains.
- [ ] Compiler `--release` is configured properly.
- [ ] Annotation processor versions are pinned.
- [ ] Java toolchains are detected properly on CI.

### Dependencies and repositories

- [ ] No version ranges or dynamic versions outside policy.
- [ ] No `SNAPSHOT`/changing dependencies in release builds.
- [ ] Transitive dependency graph is inspected.
- [ ] Gradle lockfile or Maven dependency management is managed.
- [ ] Dependency checksums/signatures are verified.
- [ ] Repositories/mirrors enforce an immutable policy for release artifacts.

### Environment and output

- [ ] OS, architecture, and container digest are recorded.
- [ ] Locale, timezone, charset, and line endings are controlled.
- [ ] No secrets or machine-specific paths in output.
- [ ] Timestamps and archive entry order are deterministic.
- [ ] Archive/resource-producing plugins support reproducible output.
- [ ] Custom tasks declare complete inputs/outputs.

### Verification and evidence

- [ ] Build is run from a clean checkout.
- [ ] At least two independent builds are performed.
- [ ] Artifact SHA-256 checksums are compared.
- [ ] Archive contents are investigated if hashes differ.
- [ ] Audit manifest is saved.
- [ ] SBOM/provenance is saved if required by the pipeline.
- [ ] Release is only marked reproducible when rebuild evidence exists.

## 27. Common issues and troubleshooting

### Same commit but different artifact hashes

**Cause:** Different JDK, dependencies, plugins, OS, archive timestamps, or generated metadata.

**Fix:** Compare audit manifests first; then inspect archive entries, manifests, class files, and `diffoscope`.

### Same java --version but different bytecode

**Cause:** Different compiler toolchain, different JDK patch/build, different annotation processors, or different compiler flags.

**Fix:** Check `javac --version`, Gradle `javaToolchains`, Maven Toolchains, and compiler configuration. Pin a specific JDK image/package.

### Same dependency version but different JAR bytes

**Cause:** Repository redeployed an artifact at the same coordinates, or a snapshot/changing module changed content.

**Fix:** Check checksums/signatures, repository origin, and immutable release policy; enable dependency verification.

### Gradle lockfile does not prevent dependency changes

**Cause:** Changing dependencies such as `SNAPSHOT` can change bytes even when the version coordinate stays the same.

**Fix:** Use immutable release artifacts; verify checksums/signatures; do not use lockfiles as a substitute for content verification.

### Maven build produces JARs with different timestamps

**Cause:** Packaging plugin does not support reproducible output or `project.build.outputTimestamp` is not applied.

**Fix:** Run `artifact:check-buildplan`; pin/upgrade supporting plugins; use `artifact:compare` and `diffoscope`.

### Gradle JAR has different entry ordering

**Cause:** Older Gradle or custom archive task without reproducible file order enabled.

**Fix:** Enable `reproducibleFileOrder`; inspect custom tasks and packaging plugins. Gradle 9 normalizes standard archive tasks by default.

### Correct Wrapper version but untrusted distribution download

**Cause:** URL is pinned without a checksum, or the checksum was taken from the same untrusted source.

**Fix:** Obtain SHA-256 from an independent release page; verify the distribution and Wrapper JAR separately.

### CI and local differ on line endings

**Cause:** Different Git checkout settings, `.gitattributes`, OS, or resource filtering.

**Fix:** Define line endings in `.gitattributes`; standardize encoding and inspect generated resources.

### Build manifest accidentally contains secrets

**Cause:** Dumping the entire environment or logging settings containing credentials.

**Fix:** Only export an allowlist of non-sensitive environment variables; redact repository URLs containing credentials; inspect artifacts before uploading.

### Two builds on the same machine pass, but another machine fails

**Cause:** The test is only repeatable within the same workspace/user/cache; an environment leak has not been caught yet.

**Fix:** Run on an independent agent/container, different workspace, and different user; check absolute paths, home directory, locale, timezone, and repository mirrors.

### Build cache returns old output and masks nondeterminism

**Cause:** Incomplete task cache inputs or the build did not actually re-execute.

**Fix:** Run a clean build without build cache; check input/output declarations; compare two independent builds.

### Attestation exists but does not prove reproducibility

**Cause:** Attestation records the source and workflow that built the artifact; it does not prove another party can recreate the exact same bytes.

**Fix:** Perform an independent rebuild and compare SHA-256 checksums; keep the attestation as separate provenance evidence.

## 28. Official references

- [Gradle Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — select JDKs for compiler, test launcher, and Javadoc, and distinguish the Gradle daemon JVM from the project toolchain.
- [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) — save resolved dependency versions and verify lock state.
- [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — verify checksums, signatures, and metadata of dependencies/plugins.
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — pin the Gradle version and verify the Wrapper JAR/distribution.
- [Gradle Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html) — distribution checksums and Wrapper verification.
- [Gradle Working with Files](https://docs.gradle.org/9.9.0/userguide/working_with_files.html) — reproducible archives, timestamps, and file ordering.
- [Maven Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — `project.build.outputTimestamp`, plugin support, `artifact:compare`, and `diffoscope`.
- [Maven Wrapper](https://maven.apache.org/tools/wrapper/) — select a Maven distribution and verify `wrapperSha256Sum`/`distributionSha256Sum`.
- [Maven Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains) — select separate JDKs for compilers and plugins.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/specs/man/javac.html) — `--release` and compiler options.
- [GitHub Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations) — record build provenance for binaries and container images.

A toolchain audit is only valuable when it reflects what the build actually used. Record the source, JDK, Wrapper, plugins, dependencies, repositories, and environment; verify any inputs that can be downloaded or modified; normalize outputs; then rebuild independently and compare SHA-256 checksums. When two artifacts differ, use the manifest and archive diff to find the specific cause before declaring the build reproducible.
