# Controlling JDK, encoding, annotation processors, and dependencies for reproducible Java builds

> **Context:** Java Advance – compilation → Build integration. The goal is to ensure that the same commit, same configuration, and same set of inputs produce verifiable build artifacts, while making it possible to explain any discrepancy when switching developer machines or running CI.

## 1. What does a “reproducible build” actually mean?

A build is **reproducible** when independent parties can rebuild the **exact same bytes** of an artifact (e.g., `.jar`), from the same source code, build instructions, and specified input environment. A **repeatable** build can run successfully multiple times yet may not produce a file with the same SHA-256. A **hermetic** build attempts to isolate the allowed inputs; this is a useful means to get closer to reproducibility, without automatically guaranteeing the result.

Mental model:

```text
Artifact = f(
  source + resources,
  JDK/javac + build tool/plugins,
  dependency graph + annotation processors,
  compiler flags + charset + environment,
  generated files + archive metadata
)
```

If one argument of `f` changes silently, different SHA-256 hashes are likely to occur. For example: using Java 17 instead of Java 21; pulling dependency version `1.+`; saving source in Windows-1258 yet compiling in UTF-8; an annotation processor injecting the current time; or a JAR containing timestamps in ZIP entries.

Three quality levels should be distinguished:

1. **Successful build:** code compiles and tests can run.
2. **Functionally consistent build:** the program behaves identically, yet JARs can still differ byte-for-byte.
3. **Bit-for-bit reproducible build:** the same pinned set of inputs yields identical artifact contents and metadata, verifiable by hash.

Do not claim “completely reproducible” merely because two consecutive builds on one machine yield the same hash: paths, locale, OS, or caches may still be hidden input sources.

## 2. Standardizing the JDK: controlling compiler and target API

### 2.1. Four parameters to distinguish

| Parameter | What does it determine? | Risk if not locked |
| --- | --- | --- |
| **JDK running the build tool** | JVM running Maven/Gradle and plugins | Plugins or build logic execute differently |
| **JDK providing `javac`** | Compiler generating bytecode | Different minor/patch/vendor versions may change output |
| **Target language/API** | Java features and Java APIs allowed | Build passes yet fails to run on the target runtime |
| **JDK running tests/app** | Post-compilation verification environment | Tests pass only on the developer's machine |

`-source` restricts syntax and `-target` restricts class-file version, yet this pair alone does **not** prevent a program from referencing Java APIs newer than the target version. Use `--release 17` when needing to run on Java 17. `--release` simultaneously controls the language level, bytecode level, and set of Java platform APIs allowed during compilation. However, `--release 17` **does not pin the patch/vendor version of `javac`**; JDK 17.0.x and JDK 21 compiling with `--release 17` do not necessarily emit identical bytes.

Build-tool-independent example, using JDK 17+:

**`src/Hello.java`**

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Tiếng Việt: cà phê");
    }
}
```

Run inside the directory containing `src`:

```bash
javac -version
javac -encoding UTF-8 --release 17 -proc:none -d out src/Hello.java
java -cp out Hello
```

Stdout of the `java` command (when source is saved as UTF-8 and the console displays Unicode):

```text
Tiếng Việt: cà phê
```

`javac` usually prints nothing on success; the line printed by `javac -version` depends on the actual JDK version. `-proc:none` is appropriate for programs **not requiring annotation processors**. If a program needs to generate sources, processors must be enabled and explicitly declared as in section 4.

### 2.2. How to pin the environment in practice

- Commit **Maven Wrapper** (`mvnw`, `.mvn/wrapper/*`) or **Gradle Wrapper** (`gradlew`, `gradle/wrapper/*`), specifying the exact Maven/Gradle version. With Gradle, check `distributionSha256Sum` in `gradle-wrapper.properties`; the wrapper manages the build tool version and **does not automatically pin the JDK**.
- Pin the JDK by **major + vendor + patch** in CI images or hash-verified toolchain distributions. A toolchain saying only “Java 17” can still match multiple 17.0.x builds; depending on bit-identical requirements, standardize a specific release.
- In Maven, **Toolchains Plugin** can select a JDK for supporting plugins, separate from the JDK running Maven. In Gradle, declare a **Java toolchain**. Toolchains avoid relying on per-machine `JAVA_HOME`, yet JDK provenance/patch version still must be managed.
- Record and verify `java -version`, `javac -version`, `./mvnw -version`, or `./gradlew --version`, along with OS and architecture on CI. Store this information in build provenance/logs, **without necessarily embedding machine paths or execution timestamps into the JAR**.
- Ensure IDEs use the same compiler, annotation processing, and target release as the CLI; trust only CI builds via wrapper, not whether the IDE shows green.

A common mistake is installing JDK 21 to run Maven, configuring `<maven.compiler.release>17</maven.compiler.release>`, and thinking javac 17 is being used. This configuration only enforces **API/bytecode target 17**; selecting the right compiler requires a toolchain and locked environment.

## 3. Encoding: pinning how sources and resources are interpreted

**UTF-8** should be the convention across all `.java`, `.properties`, templates, JSON, YAML, and text resources. A file containing “cà phê” can cause compilation errors, corrupted characters in strings, or differing artifact contents if the compiler/resource-filtering reads using a different default charset.

- Save files physically as UTF-8; configure editors and `.editorconfig`. Avoid silent charset changes when running on Windows/Linux.
- For plain `javac`, use `-encoding UTF-8`. In Maven, use `project.build.sourceEncoding` and configure explicitly when specific plugins do not inherit the value. In Gradle, set `JavaCompile.options.encoding = "UTF-8"`.
- Java files and resources **follow different processing paths**. Configuring only compiler encoding does **not** guarantee resources with filtering are read/written in the right charset; check Maven Resources Plugin configuration, Gradle filtering mechanisms, and generator-specific encodings.
- When Java runs, use overloads taking `StandardCharsets.UTF_8` for custom I/O rather than relying on the system default charset. Modern JDK default charsets are typically UTF-8 (JEP 400 since Java 18), yet legacy build parts, third-party tools, or custom configs can still diverge.
- Normalize newlines (`LF` if the repo uses it), file ordering, and resource generation when tools depend on CRLF/paths; `.gitattributes` can manage line endings. Do not arbitrarily “rewrite the entire repo” just to fix one build.

**Example `.editorconfig`:**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
```

`.editorconfig` affects how editors save files; it **does not replace** encoding flags in the compiler or resource plugin.

## 4. Annotation processors: treating them as build tools needing control

Annotation processors run during compilation and can generate `.java` files, metadata, or resources. Lombok, MapStruct, AutoValue, and many other libraries use this mechanism. They directly affect output and have permission to execute code during the build.

### 4.1. Principles

1. **Declare processors separately**, rather than letting the runtime classpath accidentally decide which processors run. In Maven 3 + Compiler Plugin 3.x, use `annotationProcessorPaths` and, when needed, the `annotationProcessors` list; in Gradle use the `annotationProcessor` configuration.
2. **Pin processor versions and transitive dependencies** like other build dependencies. Ensure processors are compatible with the chosen JDK/`javac`.
3. If **no processor exists**, specify `-proc:none`. If processors exist, list allowed processors and control their options; do not enable whole-classpath scanning merely for convenience.
4. Many generators can emit banners containing timestamps, absolute paths, unstable file traversal orders, usernames, or environment data. Configure options to suppress unstable values when the library provides them; inspect `generated-sources` output.
5. Distinguish **generated sources** as reproducible compilation outputs from **committed sources**: do not mix files generated by two generator versions into the same directory without cleaning.

**Important change:** starting in **JDK 23**, `javac` by default **no longer automatically runs processors merely because they are found on the classpath**. Configure processors explicitly so builds do not “lose” generated code when upgrading the JDK. `-proc:full` allows annotation processing followed by compilation, yet automatically enabling every processor found on the classpath can introduce security/reproducibility risks; prefer intentional processor declarations. `-proc:only` performs annotation processing only, without continuing compilation.

### 4.2. Maven: separating the processor path

The following snippet is for a project **already using MapStruct**; this is a **compiler plugin configuration fragment**, not a standalone POM:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.14.1</version>
  <configuration>
    <release>17</release>
    <annotationProcessorPaths>
      <path>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct-processor</artifactId>
        <version>1.6.3</version>
      </path>
    </annotationProcessorPaths>
    <annotationProcessors>
      <annotationProcessor>org.mapstruct.ap.MappingProcessor</annotationProcessor>
    </annotationProcessors>
    <compilerArgs>
      <arg>-Amapstruct.suppressGeneratorTimestamp=true</arg>
      <arg>-Amapstruct.suppressGeneratorVersionInfoComment=true</arg>
    </compilerArgs>
  </configuration>
</plugin>
```

The API library `org.mapstruct:mapstruct:1.6.3` must be declared separately in `<dependencies>` if code uses MapStruct annotations. The two `-A...` options prevent the generator from inserting metadata likely to make output vary across builds. In this example the processor is a **compile-time tool**, not a runtime dependency.

### 4.3. Gradle: separating compile and processor dependencies

```kotlin
dependencies {
    implementation("org.mapstruct:mapstruct:1.6.3")
    annotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")
}

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(
        listOf(
            "-processor", "org.mapstruct.ap.MappingProcessor",
            "-Amapstruct.suppressGeneratorTimestamp=true",
            "-Amapstruct.suppressGeneratorVersionInfoComment=true"
        )
    )
}
```

This is an **addition** to a `build.gradle.kts` that already has the Java plugin and appropriate repositories. When enabling processors, do **not** keep the `-proc:none` setting from the processor-free example in section 6. In a multi-module project, each module must manage its own processor path.

## 5. Dependency graph: both direct and transitive versions are inputs

A dependency is identified not only by `group:artifact:version` but also by classifier, packaging, variant, repository, metadata attributes, transitives, and actual file checksums.

### 5.1. What needs pinning

- Avoid `SNAPSHOT`, `latest.release`, `+`, open version ranges, or dependencies pulled from moving Git branches in release builds. Today and next week may resolve to different bytes even when the POM/Gradle script has not changed.
- Pin versions of **direct and transitive dependencies**, build plugins, and processors. **Maven BOM/dependencyManagement** helps align versions, yet putting a BOM alone does not freeze all artifacts/plugins or guarantee repositories do not change.
- **Gradle dependency locking** records resolved versions for each configuration; commit `gradle.lockfile` (and any other lockfiles). **Dependency verification** adds checksums/signatures to detect byte changes in artifacts; version locking and checksum verification are **two distinct concerns**.
- With Maven, pin plugin versions and dependency rules in POM/parent/BOM, avoiding SNAPSHOT; inspect `./mvnw dependency:tree` and `./mvnw help:effective-pom`. Internal repository managers, “no redeploy release” policies, and checksums help block artifact tampering on the same GAV; Maven does not have an equivalent built-in Gradle-style dependency lock.
- Lock down repository order and sources. Avoid `mavenLocal()` or `~/.m2/repository` containing locally installed artifacts differing from remote in release CI. Do not disable checksum verification when checksums fail; investigate the root cause.
- Separate dependencies for compile, runtime, test, and processors. Changing processor transitives can also change generated sources even when `implementation` is unchanged.

**Gradle Kotlin DSL, locking illustration:**

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

After configuring dependencies, run via the project wrapper:

```bash
./gradlew build --write-locks
./gradlew --write-verification-metadata sha256 help
```

Inspect the diff, then commit the lockfile and `gradle/verification-metadata.xml`. The command generating checksum verification metadata may download/resolve artifacts related to the invoked task; metadata must cover **every configuration** used in CI and must be reviewed before committing. Do not pass lock-writing flags in routine CI builds: CI must **consume committed locks** and fail if anything diverges.

### 5.2. Build tools and plugins are also dependencies

Factors such as Maven Compiler/Resources/JAR Plugin, Gradle Java plugin, shading plugins, Kotlin/Groovy compilers, codegen, native libraries, or Docker base images all affect output. Lock versions of **wrapper + plugins + toolchains + external binaries** alongside the dependency graph. Pinning with a moving tag like `latest` still exposes volatile inputs.

## 6. Maven configuration example for a Java 17 project without processors

This is a **minimal complete POM** for plain Java; assumes `src/main/java/demo/Hello.java` below. Use the committed Maven Wrapper and a standardized JDK in CI.

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>reproducible-java</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
          <proc>none</proc>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-resources-plugin</artifactId>
        <version>3.3.1</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
      </plugin>
    </plugins>
  </build>
</project>
```

**`src/main/java/demo/Hello.java`**

```java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Build Java ổn định");
    }
}
```

Command (Unix/macOS uses `./mvnw`; Windows uses `mvnw.cmd`):

```bash
./mvnw -B clean package
java -cp target/classes demo.Hello
```

Exact stdout from the `java` command:

```text
Build Java ổn định
```

`project.build.outputTimestamp` fixes packaging timestamps for Maven plugins supporting reproducible archives, without fixing other plugins embedding timestamps, paths, or random data. The POM above is an **intentional example for Java code requiring no annotation processors**; when using MapStruct/Lombok you must remove `<proc>none</proc>` and declare processors explicitly as in section 4. If the build uses resource filtering, inspect charsets/line endings and values interpolated into resources.

**Selecting a JDK with Maven Toolchains Plugin** (the snippet below is added into `<build><plugins>` when wanting to select an installed JDK 17):

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.3.0</version>
  <executions>
    <execution>
      <goals>
        <goal>select-jdk-toolchain</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <version>[17,18)</version>
  </configuration>
</plugin>
```

`[17,18)` requests a JDK in the 17 line; to standardize **patch/vendor as well**, pin distributions and checksums in CI or constrain toolchains more tightly and verify the actual compiler. Plugins/compilers must support toolchains; the Maven runtime is still determined by the environment launching Maven.

## 7. Gradle Kotlin DSL example for a Java 17 project without processors

**`build.gradle.kts`** (plain Java project example; Gradle can run on a JDK compatible with the chosen Gradle version):

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.add("-proc:none")
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

dependencyLocking {
    lockAllConfigurations()
}
```

- Gradle toolchain selects a Java 17 compiler for Java tasks, `options.release.set(17)` confirms target API/bytecode; still pin patch/vendor in CI environments if bit-identical artifacts are needed.
- The two archive properties remove unstable timestamps and filesystem-dependent entry order. Gradle **9.0+** enables reproducible archives by default for standard archive tasks; explicit declarations remain useful if older Gradle versions must be supported.
- `options.compilerArgs.add("-proc:none")` is only for **processor-free** setups. If processors exist, drop this flag and declare `annotationProcessor` as in section 4.
- `lockAllConfigurations()` is a configuration step: `--write-locks` must be run when changing dependencies, lockfiles committed, and resolution verified by CI.

Source layout, outputs, and basic commands:

```text
src/main/java/demo/Hello.java
build.gradle.kts
settings.gradle.kts
gradlew
gradle/wrapper/gradle-wrapper.properties
```

```bash
./gradlew clean build
java -cp build/classes/java/main demo.Hello
```

Using the same `demo.Hello` class from the Maven section will print `Build Java ổn định`. In a project with new dependencies, a `build.gradle.kts` with `mavenCentral()` repo does not automatically lock contents: locking/verification must be added, and repositories managed from `settings.gradle.kts` if required by the organization.

## 8. JARs and the packaging step: bytes prone to variation

A `.jar` is a ZIP archive. Even when `.class` files match, JAR SHA-256 hashes can still differ due to entry timestamps, entry ordering, file permissions, manifest ordering, auto-generated files, paths, signatures, or plugin-written metadata.

Check each item in turn:

- **ZIP entries:** fixed timestamps; deterministic packaging order; stable file permissions/line endings.
- **Manifest and metadata:** must not contain build time, hostname, username, absolute working directory, random build id, or changing branch names.
- **Generated resources:** sorted deterministically before serializing JSON/YAML/service descriptors; do not rely on hash collection iteration order or filesystem order.
- **Locale/time zone:** do not format dates/numbers using default locale; set deterministic timezone/locale for generators if applicable.
- **External tools:** Protobuf/OpenAPI/ANTLR codegen, native compilers, container assemblers… require pinned versions/configs.
- **Build cache:** caches speed up builds yet can hide undeclared inputs; test cold builds and compare across independent environments. Do not treat “clearing the cache makes the bug go away” as a substitute solution.

Faulty example:

```java
// Snippet illustrating a non-reproducible source; do not embed this value into artifacts:
String generatedAt = java.time.Instant.now().toString();
```

If a generator puts `generatedAt` into a Java/resource file, two builds one second apart can yield different JARs. The fix is removing unnecessary data or taking a **fixed, controlled, traceable** value such as an agreed release timestamp.

## 9. Procedure for verifying reproducibility via CI

**Step 1 – Identify inputs.** Verify a clean working tree, commit ID, wrapper version, JDK distribution/version/hash, dependency locks/checksums, processor versions, required env, and build command.

**Step 2 – Run two clean builds.** Execute in **two independent directories/machines or containers**, carrying over no `target`/`build`/outputs from prior runs. Whenever possible, use a clean environment and controlled toolchains/repository mirrors.

**Step 3 – Compare artifacts byte-by-byte.** Example on Linux/macOS:

```bash
sha256sum build-a/target/reproducible-java-1.0.0.jar
sha256sum build-b/target/reproducible-java-1.0.0.jar
cmp build-a/target/reproducible-java-1.0.0.jar build-b/target/reproducible-java-1.0.0.jar
```

Paths `build-a` and `build-b` represent two independent workspaces after copying artifacts to a comparison location. `cmp` returns exit code **0** if bytes are identical, non-zero if they differ. SHA-256 hashes must match to meet bit-for-bit criteria; **do not fabricate a preset hash value** because hashes depend on all real inputs. On Windows PowerShell, use `Get-FileHash -Algorithm SHA256 <path>` for each artifact.

**Step 4 – Investigate diffs if hashes differ.** Compare ZIP entry contents, timestamps, manifests, bytecode (`javap -v`), generated sources, dependency trees, and build logs. `diffoscope` is very useful for seeing deep differences inside archives. With Maven, `maven-artifact-plugin` provides the `artifact:compare` goal to compare a second build against the installed one, yet testing on **another environment** remains necessary to uncover environment leaks.

**Step 5 – Retain evidence.** CI should retain logs of JDK/build tool versions, dependency locks/checksums, commands, source revision, and final hashes. Published artifacts should include provenance/SBOM and supply-chain verification workflows when needed; these documents can vary per release, so store them **separately** if the goal is a byte-identical JAR.

### Common failure matrix

| Symptom | Common cause | How to check and fix |
| --- | --- | --- |
| Build passes in IDE, fails in CI | Different `JAVA_HOME`/compiler, flags, or processors | Print JDK version, use wrapper/toolchain and CLI build |
| `invalid target release` | Compiler too old for target release | Choose a sufficiently new JDK `javac`, keep appropriate `--release` |
| `cannot find symbol` for generated class | Processor did not run, especially JDK 23+ | Explicitly declare processor path/class, inspect generated sources |
| Corrupted Vietnamese text in classes/resources | Source or filtering read with wrong charset | Check file bytes, `-encoding`, and UTF-8 resource encoding |
| Same commit yet different dependencies | Dynamic versions/SNAPSHOT, different repos, or altered artifacts | Dependency tree, locks, checksum verification, and repository policy |
| Identical `.class` yet different JAR hash | ZIP timestamp/order, manifest, or metadata | Compare ZIP entries and reproducible archive settings |
| Differs only between two OSes | Line endings, paths, file permissions, locale | Normalize inputs and generators; verify across two environments |
| Re-running build makes error disappear | Stale outputs/caches from prior build or race condition | Clean isolated build, clean generated outputs properly, and audit task inputs |

## 10. Checklist for a repository

- [ ] Sources/resources use UTF-8, line endings follow convention; compiler and resource filtering configure charset explicitly.
- [ ] Wrapper is committed, Maven/Gradle and plugin versions are pinned; CI uses the wrapper.
- [ ] Compiler JDK, target API `--release`, vendor/patch, and test runtime are specified per requirements.
- [ ] Annotation processors run intentionally, versions/paths/options are pinned; disabled explicitly if no processors are used.
- [ ] Direct/transitive dependency graph, repositories, and artifact checksums are controlled; no dynamic versions in releases.
- [ ] Generators do not inject clock, random values, hostname, user, or absolute paths into release artifacts.
- [ ] JAR/archive has fixed entry timestamps and deterministic ordering; built from a clean workspace.
- [ ] CI builds independently, compares hashes, stores provenance, and has a workflow to investigate diffs.

**Important limitation:** the configuration set illustrated above is a foundation, not a “reproducibility certificate”. Bit-level reproducibility must be **verified on actual artifacts**, across all code generators, plugins, dependencies, resources, and project-specific environments.

## Authoritative references

- Apache Maven – Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Apache Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Apache Maven Toolchains Plugin: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Gradle – Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle – Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle – Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle – Working With Files/Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Oracle `javac` specification: https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- JDK 23 annotation-processing behavior: https://inside.java/2024/06/18/quality-heads-up/
- Reproducible Builds – JVM: https://reproducible-builds.org/docs/jvm/