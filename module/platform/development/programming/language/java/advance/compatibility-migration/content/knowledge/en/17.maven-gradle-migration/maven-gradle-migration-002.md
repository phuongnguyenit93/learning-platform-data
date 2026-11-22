# Maven Wrapper, Gradle Wrapper, and Project-Pinned Versions

When upgrading a Java project to a new JDK, running `mvn clean verify` or `gradle build` does not necessarily produce the same result on two machines. One developer may have Maven 3.x installed from years ago; another machine may have a newer Maven version; CI may use the default Gradle version in the build image. Build scripts, plugins, compilers, and the way dependencies are resolved can change depending on the tool version.

**Maven Wrapper** and **Gradle Wrapper** bring build tool version selection directly into the repository. Developers and pipelines run the script bundled with the project, while the Wrapper configuration specifies which Maven/Gradle version will be downloaded or used. This is the foundation of reproducible builds during Java Advance Compatibility Migration, yet it is not sufficient: a Wrapper does not by itself lock the JDK, Java source/bytecode target, plugins, dependencies, or production runtime.

This lesson presents how to use both Wrappers, where versions are pinned, the difference between the tool and the JDK, controlled upgrade workflows, CI integration, supply chain security, and common failure scenarios.

## 1. What problem does a Wrapper solve?

A Java repository can be built using a tool pre-installed on the machine:

~~~bash
mvn clean verify
gradle clean build
~~~

This approach relies on the `PATH` variable, operating system setup, and the runner's environment. If Maven/Gradle versions are inconsistent, results can differ.

With a Wrapper, the repository provides a launcher:

~~~bash
# Linux / macOS:
./mvnw clean verify
./gradlew clean build

# Check the selected version:
./mvnw --version
./gradlew --version
~~~

On Windows:

~~~powershell
.\mvnw.cmd clean verify
.\gradlew.bat clean build

.\mvnw.cmd --version
.\gradlew.bat --version
~~~

A Wrapper is not a second Maven or Gradle. It is a mechanism to bootstrap and launch the **Maven/Gradle distribution chosen by the project**. A Maven repository typically uses `mvnw`; a Gradle repository uses `gradlew`.

Three main benefits:

1. **Consistency:** the same commit usually leads to the same build tool version.
2. **Onboarding:** new developers do not have to guess which Maven/Gradle version to install.
3. **Change governance:** upgrading the build tool is recorded as a reviewable and rollback-capable change in Git.

Three important limitations:

1. A Wrapper does not automatically select the right JDK to run the build if the environment/toolchain has not been configured.
2. A Wrapper does not lock all transitive dependencies or build plugins.
3. A Wrapper does not guarantee reproducible builds across all OSes, CPUs, locales, timezones, or network environments.

## 2. Distinguishing four different versions

During Java migration, do not lump everything into a single `javaVersion` field.

| Component | Example | Role |
|---|---|---|
| Maven/Gradle version | Maven 3.9.x / Gradle 8.x | Build tool and build DSL/runtime |
| JDK running the build | JDK 21 | JVM running Maven/Gradle, plugins, or build logic |
| JDK toolchain | JDK 21 | JDK executing the Java compiler or related Java tasks |
| Java release target | `--release 17` | Syntax, Java SE APIs, and bytecode target of the application |

For example: Gradle runs on JDK 21, the JavaCompile task also uses JDK 21, yet `options.release = 17` instructs the application to use the Java 17 source/API/bytecode baseline. The Wrapper only determines the **Gradle version**.

Another scenario: the Gradle daemon runs on JDK 17 while the compilation toolchain can choose JDK 21 if supported by the Gradle version and configuration. In that case, you must check the test runtime separately to know whether the artifact actually runs on the lowest Java version that must be supported.

Do not conclude that an application is Java 17 compatible simply because `./gradlew --version` shows Gradle supports Java 17.

## 3. Maven Wrapper: structure and configuration

A Maven project may contain:

~~~text
maven-project/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── .mvn/
    ├── maven.config
    ├── jvm.config
    └── wrapper/
        ├── maven-wrapper.properties
        └── maven-wrapper.jar    # Optional, depending on Wrapper mode
~~~

Role of each component:

- `mvnw` and `mvnw.cmd`: launchers for Unix shells and Windows.
- `.mvn/wrapper/maven-wrapper.properties`: metadata specifying the Maven distribution, download source, and corresponding Wrapper settings.
- `maven-wrapper.jar`: bootstrap JAR in some modes; there are wrapper configurations that use scripts without needing to commit this JAR.
- `.mvn/maven.config`: default arguments for Maven commands if used by the project.
- `.mvn/jvm.config`: JVM arguments used by Maven; does not install a JDK by itself.

Do not assume every Maven Wrapper has the exact same file layout. The Maven Wrapper plugin has different distribution and bootstrap modes depending on its version.

### 3.1. Distribution URL pinning the Maven version

Example `.mvn/wrapper/maven-wrapper.properties`:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

This is an example using Maven 3.9.9 to illustrate where the version is pinned, **not a claim of the latest or mandatory version**. In a real project, choose the Maven version based on the compatibility matrix with the JDK and plugins.

Some wrapper configurations support checksums, a wrapper download URL, or other options. Property names and behavior must be checked against the **specific Maven Wrapper version** rather than copied unconditionally from a template.

### 3.2. Generating the Maven Wrapper

If the environment already has Maven and an appropriate Maven Wrapper plugin:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

This command creates or updates the Wrapper files according to the resolved plugin version. Parameters and how the plugin version is chosen may change, so projects should check the official guide for the wrapper plugin in use.

Then run:

~~~bash
./mvnw --version
./mvnw -B clean verify
~~~

`-B` enables batch mode suited for CI. Once the wrapper has been committed, normal builds should invoke `./mvnw` rather than arbitrarily using global Maven.

## 4. Gradle Wrapper: structure and configuration

A Gradle project usually has:

~~~text
gradle-project/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/
    ├── libs.versions.toml
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Groovy DSL `settings.gradle` / `build.gradle` can be used instead of Kotlin DSL `.kts`.

- `gradlew` and `gradlew.bat`: launchers.
- `gradle-wrapper.jar`: bootstrap code that reads configuration and runs Gradle.
- `gradle-wrapper.properties`: distribution URL and download options.
- `libs.versions.toml`: version catalog, if used by the project; it manages plugin/dependency declarations and **does not choose the Gradle distribution version**.
- `build.gradle`: configures plugins, source sets, tasks, and dependencies.

### 4.1. Example gradle-wrapper.properties

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

`8.10.2` is an example version number. The project needs to pick a Gradle version that supports the target JDK, plugins, and intended toolchains.

`distributionUrl` specifies the distribution. The `-bin.zip` suffix is the standard binary distribution for running builds; `-all.zip` adds documentation/sources for cases that need them. Options such as `networkTimeout` and `validateDistributionUrl` are supported depending on the Wrapper version; do not assume very old scripts read every newer property.

When supported by the wrapper, you can declare a checksum:

~~~properties
distributionSha256Sum=<VERIFIED_SHA256_OF_DISTRIBUTION>
~~~

This is a placeholder and cannot be used directly. You must fill in the exact checksum obtained from a trusted source. The checksum helps detect unexpected changes to the distribution.

### 4.2. Creating or upgrading the Gradle Wrapper

If Gradle is already installed on the machine:

~~~bash
gradle wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

When the repository already has a Wrapper:

~~~bash
./gradlew wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

After upgrading, inspect **the scripts, the wrapper JAR, and the properties**. In the proper Gradle workflow, running the wrapper task a second time after the new distribution has been activated may be needed to fully update all bootstrap files.

Manually editing only `distributionUrl` can change the distribution version while leaving old launcher/JAR files behind; that misses functional and security updates in the wrapper bootstrap.

## 5. Which Wrapper files should be committed

The Wrapper should be part of the repository so developers and CI use the same commit, not just a single machine's setup.

For Maven:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar   # only if the wrapper mode includes this file
~~~

For Gradle:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Do not commit the downloaded Maven/Gradle distribution or a developer's entire cache. On Unix, scripts need the executable bit:

~~~bash
chmod +x mvnw
chmod +x gradlew

git add mvnw gradlew
~~~

The same repository is not required to have both `mvnw` and `gradlew`; the snippet illustrates how to mark whichever script files are present.

### 5.1. Do not overlook the binary wrapper JAR

The Gradle Wrapper JAR is executable code supplied by the repository. A change to `gradle-wrapper.jar` in a pull request can execute before the build tool starts. Verify the origin of the wrapper JAR and review binary/script changes according to security procedures.

The Maven Wrapper also has bootstrap files that need similar inspection if used by the project.

## 6. How the Wrapper downloads and caches distributions

In principle:

~~~text
./mvnw or ./gradlew
          |
          v
Read wrapper.properties
          |
          v
Is the right distribution version already cached?
          |
     +----+----+
     |         |
    Yes        No
     |         |
     |         v
     |     Download distribution
     |         |
     |         v
     |     Checksum/validation (if supported by configuration)
     |         |
     |         v
     |       Cache
     +----+----+
          |
          v
Launch Maven/Gradle
~~~

A developer machine that has built before can use the cached distribution. A fresh CI runner may have to download it again. Therefore, a green build on a machine using a cache does not guarantee a build on a clean machine will succeed if proxies, TLS truststores, or mirrors are missing.

Distinguish between:

- **Wrapper distribution cache:** stores downloaded Maven/Gradle.
- **Dependency cache:** stores libraries/plugins resolved by Maven/Gradle.
- **Compiler/JDK toolchain cache:** may store JDKs provisioned under the appropriate configuration.
- **Build cache:** stores task outputs to speed up builds.

Deleting one type of cache does not clear the others. Do not clear all caches as a default "fix" without knowing the cause.

## 7. A Wrapper does not automatically lock dependencies or plugins

The same Maven version can still resolve different dependencies if the POM uses SNAPSHOTs, version ranges, or changing repository metadata. Similarly, Gradle using dynamic versions can pull new artifacts:

~~~groovy
dependencies {
    implementation 'com.example:client:2.+'
}
~~~

`2.+` is not a version pin. Build timing and caches can affect the resolved version.

Separate these layers:

| Version group | Maven | Gradle |
|---|---|---|
| Build tool | Wrapper properties | Wrapper properties |
| Build plugins | `pluginManagement` and plugin `<version>` | `plugins`, `pluginManagement`, version catalog |
| Direct dependencies | POM properties, dependencyManagement, BOM | Dependency declarations, platforms/catalog |
| Transitive dependencies | Mediation, BOM, effective POM | Constraints, conflict resolution, locking |
| Build JDK | JVM running Maven | JVM running the Gradle daemon |
| Compiler | Compiler plugin, toolchain | Java toolchain, JavaCompile |
| Java target | `maven.compiler.release` | `options.release` |

### 7.1. Maven dependencyManagement

In Maven, a BOM can govern a group of versions:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>example-bom</artifactId>
      <version>1.2.3</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

This is a structural example, not a real dependency to use. Inspect resolved dependencies with:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Specific plugin versions may need to be resolved. Results must be tied to the exact POM, Maven version, and repository state.

### 7.2. A Gradle version catalog differs from a lockfile

An example `gradle/libs.versions.toml`:

~~~toml
[versions]
logging = "2.0.1"

[libraries]
logging-api = { module = "org.example:logging-api", version.ref = "logging" }
~~~

A version catalog centralizes declarations. By default, it does not lock all transitive versions. If the project requires dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

After configuring and resolving the appropriate configurations, Gradle's `--write-locks` mechanism can be used according to the documentation for that exact version. Lockfiles should be reviewed and committed.

Gradle dependency verification can add hash/signature metadata for dependencies. This is a different layer from the checksum of the **Gradle distribution** in the Wrapper.

## 8. Maven Wrapper does not automatically choose the JDK

`./mvnw` launches the Maven distribution, yet the JVM executing Maven usually comes from `JAVA_HOME` and the launcher environment. Check with:

~~~bash
./mvnw --version
java -version
echo "$JAVA_HOME"
~~~

The output of `./mvnw --version` shows the Maven version and the Java runtime/home used by Maven. This matters more than guessing from `java -version` in a differently configured terminal.

### 8.1. Compiler release

Example `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

With a supporting Maven Compiler Plugin, this property sets the Java release target for compilation. It does **not** mean the Maven JVM is JDK 17.

Plugin example:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

The plugin version is illustrative only, not a requirement to use this exact version. Pick the actual version from the Maven/JDK matrix.

### 8.2. Maven Toolchains

Maven Toolchains allow certain plugins/tasks to choose a different JDK from the JVM running Maven, if the plugin supports toolchains.

~~~text
Maven Wrapper version
        |
        v
JDK running Maven
        |
        v
Maven Compiler Plugin
        |
        v
Compilation toolchain JDK
        |
        v
--release 17
~~~

Some plugins may not use toolchains and continue running inside Maven's JVM. Therefore, verify which JDK the compiler and specific tasks actually choose, rather than looking solely at the toolchain XML.

## 9. Gradle Wrapper differs from the Gradle JVM and Java toolchain

In Gradle, three things must be distinguished:

- **Gradle distribution version:** from the Wrapper.
- **Gradle JVM/daemon:** the JDK running build logic and plugins.
- **Java toolchains:** the specific JDK used to compile, test, or run supported tasks.

Check with:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

`javaToolchains` is available with an appropriate Gradle/Java plugin environment and helps inspect detected JDK installations.

Groovy DSL example:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

The project chooses JDK 21 for compilation while constraining Java source/API/bytecode to Java 17. That alone does not guarantee every third-party dependency runs on Java 17: inspect dependency bytecode and APIs alongside runtime tests.

A Gradle version may support **using JDK N as a toolchain** before or after it supports **running the Gradle daemon on JDK N**. Always verify the two capabilities separately.

### 9.1. Daemon after switching JDKs

If you switch JDKs and an old daemon remains running, you can stop the daemon as needed during investigation:

~~~bash
./gradlew --stop
./gradlew --version
~~~

This is only a daemon-management step. It will not fix broken plugins, an overly old wrapper, or a misconfigured toolchain.

## 10. Why can upgrading a Wrapper break the build?

### Maven

After upgrading the Maven distribution:

- An overly old compiler plugin may not understand the new release target.
- Surefire/Failsafe or test providers may not support the new JDK.
- Packaging, code generation, bytecode manipulation, or shading plugins may rely on old APIs.
- Dependency resolution/settings.xml/mirror policies may expose differences.
- Custom Maven extensions or build agents may be incompatible.

### Gradle

After upgrading Gradle:

- Custom Gradle plugins may use removed APIs.
- Groovy/Kotlin DSL or `buildSrc` logic may need updates.
- Spring/Android/Kotlin or instrumentation plugins have their own support matrices.
- Compilers/annotation processors may not understand the new classfile target.
- Defaults, caching, and dependency resolution may change between Gradle versions.

Therefore, **upgrading the Wrapper successfully does not equal a successful build**. You must test plugins and tasks with the intended JDK version.

## 11. Controlled Maven Wrapper upgrade workflow

### Step 1: Capture the baseline

~~~bash
./mvnw --version
./mvnw -B clean verify
~~~

Record the Maven version, Java version/home, compiler target, plugin versions, dependency graph, and artifact output. If the build already fails at baseline, record the exact error before making changes.

### Step 2: Choose the Maven version

Cross-check against the target JDK, critical plugins, and support policy. Do not assume the latest release always fits every legacy project.

### Step 3: Update the Wrapper

Example:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

When using another version/plugin, follow the corresponding Maven Wrapper documentation. Review scripts, properties, and bootstrap files.

### Step 4: Run the build with the new Wrapper

~~~bash
./mvnw --version
./mvnw -B clean verify
~~~

If a plugin fails, identify the plugin and upgrade it in a separate change when possible.

### Step 5: Integrate into CI

CI must call `./mvnw`. Check mirrors, checksums/provenance, JDK setup, and a clean runner. Commit the full set of Wrapper changes after review.

### Step 6: Prepare rollback

Rollback usually requires reverting both the wrapper files and matching plugin/JDK configuration. Do not simply edit the version number in the distribution URL and assume everything matches the prior state.

## 12. Controlled Gradle Wrapper upgrade workflow

### Step 1: Capture the baseline

~~~bash
./gradlew --version
./gradlew clean build
~~~

Record the Gradle JVM, toolchains, plugins, warnings, test results, and artifacts.

### Step 2: Verify the compatibility matrix

Check whether the target Gradle version runs on the JDK used by the daemon, supports the required JDK toolchains, and whether plugins support the new Gradle version.

### Step 3: Upgrade the Wrapper

~~~bash
./gradlew wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

The version is illustrative. Follow the procedure for the corresponding Gradle version, re-running the wrapper task when needed to update the wrapper JAR and launcher scripts completely, not just properties.

### Step 4: Verify

~~~bash
./gradlew --version
./gradlew --warning-mode all build
~~~

The `--warning-mode all` flag (on supporting Gradle versions) surfaces deprecated API warnings; it does not replace tests.

### Step 5: Review and commit

Review:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Verify provenance, diffs, checksums, and plugin changes. On rollback, restore the full set of files compatible with the previous distribution version.

## 13. CI must specify the Wrapper and JDK explicitly

A good pipeline specifies the JDK explicitly, then uses the repository's Wrapper.

GitHub Actions example for Maven (illustrative only; action versions must follow organizational policy):

~~~yaml
name: Maven CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Show versions
        run: |
          java -version
          ./mvnw --version
      - name: Verify
        run: ./mvnw -B clean verify
~~~

Gradle example:

~~~yaml
name: Gradle CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle
      - name: Show versions
        run: |
          java -version
          ./gradlew --version
      - name: Build
        run: ./gradlew clean build
~~~

This is an example structure; organizations may require pinning actions by commit SHA, restricting token permissions, or using internal runners.

### 13.1. Commands that easily cause drift

~~~text
Developer: ./gradlew build  -> Gradle distribution in the repository
CI:        gradle build     -> Globally installed Gradle on the runner

Developer: ./mvnw verify   -> Maven distribution in the repository
CI:        mvn verify      -> Globally installed Maven on the runner
~~~

If CI uses a global tool, the Wrapper no longer guarantees the team shares a version. Check IDEs, Dockerfiles, release scripts, scheduled jobs, and dependency-update bots, not just the main YAML workflow.

## 14. Wrapper security and distribution download sources

The Wrapper is part of the software supply chain because its launcher/downloader/bootstrap executes code before the build runs.

### 14.1. Distribution URL

Inspect the chosen URL:

- Official source or an approved internal artifact mirror.
- HTTPS and proper TLS trust configuration.
- Immutable artifacts/versions or protective retention policies.
- Redirects/proxies do not lead to unexpected domains.
- Source, checksums, and releases are auditable.

Do not switch to an untrusted source just to bypass a network failure.

### 14.2. Checksum

The Gradle Wrapper supports `distributionSha256Sum` in appropriate versions. The Maven Wrapper also has validation capabilities depending on version/configuration. Obtain the expected checksum from a trusted source **independent of the downloaded file**.

Merely hashing a file downloaded from an untrusted source and storing that hash does not prove the file came from a valid origin.

### 14.3. Wrapper scripts and JAR

Wrapper scripts/JARs can execute with developer or CI privileges. You should:

- Review script changes.
- Verify the wrapper JAR from the chosen release.
- Avoid running untrusted PRs with production secrets.
- Apply least-privilege permissions to CI tokens.
- Consider wrapper validation and dependency verification according to policy.
- Never place credentials in `distributionUrl`, source control, or logs.

### 14.4. Proxies, internal networks, and offline builds

Clean CI runners may fail to download distributions if they depend on proxies/certificates configured on developer machines. Projects should define:

- Approved artifact mirrors.
- Procedures for supplying CA certificates/proxies/credentials.
- Checksum and caching policies.
- Offline build capability if operationally required.
- How to distinguish a Wrapper distribution download failure from a Maven/Gradle dependency download failure.

## 15. Multi-module projects and monorepos

### Maven reactor

~~~text
repo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
├── api/pom.xml
├── service/pom.xml
└── integration-tests/pom.xml
~~~

Use the Wrapper at the root:

~~~bash
./mvnw verify
./mvnw -pl service -am test
~~~

`-pl` selects a project and `-am` includes dependent projects in the reactor required by the command. Modules can use different Java targets per policy; a shared Wrapper does not automatically unify every compiler configuration.

### Gradle multi-project

~~~text
repo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/build.gradle.kts
└── core/build.gradle.kts
~~~

Run tasks per project:

~~~bash
./gradlew :app:build
./gradlew :core:test
~~~

### Multi-build-root monorepo

A monorepo may contain independent Maven and Gradle applications, each subdirectory having its own Wrapper. CI must run with the right working directory and launcher rather than picking a Wrapper from a different build root.

If an organization aims to standardize Maven/Gradle versions, coordinate version upgrades via PRs and test matrices rather than removing individual Wrappers to rely on global tools.

## 16. Build reproducibility requires more than a Wrapper

A build can use the exact same Maven/Gradle version and still produce different output due to:

- Different JDK vendors, updates, or compiler flags.
- Changing plugin versions or transitive dependencies.
- SNAPSHOTs, version ranges, or dynamic versions.
- Locale, timezone, charset, and line endings.
- Timestamps embedded into JARs/manifests or generated code.
- OS/architecture/native libraries.
- Build environment variables or external services.
- File ordering inside archives.
- Test concurrency and environmental data.

Record in build metadata:

~~~text
buildTool=Maven/Gradle
buildToolVersion=...
wrapperDistributionUrl=...
jdkVendor=...
jdkVersion=...
compilerToolchain=...
javaReleaseTarget=...
pluginAndDependencyVersions=...
gitCommit=...
artifactSha256=...
~~~

Depending on the system, metadata may live in CI logs, provenance attestations, or SBOMs. Never put credentials or secrets in metadata.

## 17. Common failures

| Symptom | Cause to investigate | Evidence |
|---|---|---|
| `./gradlew: Permission denied` | Launcher is missing the executable bit | Git file mode and OS |
| `Could not determine Java version` | Old Gradle does not recognize the new JDK version | Gradle Wrapper and JDK matrix |
| `UnsupportedClassVersionError` | Build/plugin JVM is too old to read the classfile | JVM and bytecode version |
| `source option 5 is no longer supported` | Default compiler target is too old | Compiler plugin, `--release` |
| `NoClassDefFoundError` in a plugin | Plugin is incompatible or missing a dependency | Stack trace and plugin graph |
| Distribution download error | URL, proxy, TLS, checksum, or network | Wrapper properties and download logs |
| Wrapper cannot find bootstrap class | Missing or corrupted JAR/script file | Committed Wrapper files |
| Maven builds, yet tests do not run | Surefire/JUnit provider, plugin, or JDK runtime | Test plugin version and logs |
| Gradle daemon error | Incompatible Gradle JVM or plugin | `./gradlew --version`, daemon logs |
| Passes locally, fails in CI | CI uses a different tool/JDK | CI commands, `--version` output |
| Builds differ despite same wrapper | Dynamic deps, snapshots, environment | Lockfiles, effective POM, dependency graph |

When troubleshooting errors, distinguish between the **bootstrap**, **build tool runtime**, **plugin/build logic**, **compiler/toolchain**, **dependency resolution**, and **test/deployment runtime** layers. An exception does not necessarily come from a source code change.

## 18. Diagnostic workflow when upgrading the JDK

1. **Does the Wrapper run?** Check `./mvnw --version` or `./gradlew --version`. If it fails, inspect scripts, JAR, URL, network, and file permissions.
2. **Which JDK does the build tool use?** Read the version output, Java home, CI setup, and IDE configuration.
3. **Does the tool version support that JDK?** Check the Maven/Gradle compatibility matrix against the target JDK.
4. **Are plugins compatible?** Identify the failing plugin's stack trace, version, and APIs used.
5. **What is the compiler target?** Check toolchains, `--release`, source/APIs, and classfile versions.
6. **Are dependencies locked?** Compare resolved versions, plugin graphs, and lockfiles.
7. **Which JDK are tests running on?** The test JVM may differ from the compiler JDK or production runtime.
8. **Which runtime does the deployed artifact use?** Docker images, installers, or runtime images may differ from CI.
9. **Is it reproducible from a clean checkout?** Run with organizational standard tools and network settings.
10. **Can it be rolled back?** Restore the Wrapper and accompanying JDK/plugin config, and test the baseline artifact.

Do not change the JDK, Gradle/Maven, frameworks, and dependencies all at once if the changes can be separated. Each change group can be tested and rolled back independently to isolate root causes easily.

## 19. Java upgrade roadmap with a Wrapper

A practical progression:

### Phase A — Standardize the current build

- Commit the Wrapper into Git if not present yet.
- Update README/CI to use the Wrapper.
- Pin critical plugins and versions.
- Record baseline Maven/Gradle/JDK and test results.

### Phase B — Controlled build tool upgrade

- Choose a Maven/Gradle release supporting both the current JDK and target JDK.
- Update the Wrapper files completely.
- Upgrade required plugins to keep the build green on the old JDK when feasible.
- Verify CI and clean source checkout.

### Phase C — Upgrade JDK/toolchain

- Choose the new JDK with explicit vendor/version.
- Keep the old `--release` when runtime compatibility must be preserved.
- Inspect annotation processors, bytecode tools, and plugins.
- Run tests on both the target JDK and minimum runtime.

### Phase D — Upgrade Java source/API target when needed

- Change `--release` in a separate commit.
- Update sources/dependencies to use new JDK APIs.
- Run integration tests and committed compatibility tests.

### Phase E — Release and maintenance

- Record artifact hashes and Wrapper/JDK versions in release metadata.
- Verify packaging and production launchers.
- Prepare rollback to a known-good commit.
- Schedule Wrapper/plugin upgrades according to security patches and vendor support.

## 20. Checklist for Wrappers in Java migration

- [ ] Identified the exact Maven/Gradle build root of the project.
- [ ] Put the corresponding Wrapper scripts and bootstrap files in place.
- [ ] Committed the Wrapper to Git with appropriate executable bits.
- [ ] Verified the distribution URL and build tool version.
- [ ] Checked checksums/provenance when supported by the wrapper version.
- [ ] Used the Wrapper instead of global Maven/Gradle binaries in README and CI.
- [ ] Recorded the JVM actually running Maven/Gradle.
- [ ] Distinguished the build JVM from the Java toolchain JDK.
- [ ] Pinned the source/API/bytecode target according to requirements.
- [ ] Cross-checked the Maven/Gradle version against the JDK matrix.
- [ ] Verified plugin/build logic compatibility.
- [ ] Controlled direct and transitive dependency versions.
- [ ] Checked SNAPSHOT/dynamic versions, BOMs, or lockfiles.
- [ ] Ran builds/tests on the exact target JDK and OS.
- [ ] Verified distribution downloads in clean CI, proxies, and mirrors.
- [ ] Reviewed wrapper JAR/script changes as executable code changes.
- [ ] Saved build metadata, artifact hashes, and test results.
- [ ] Prepared a rollback plan covering the Wrapper/JDK/plugins and artifacts.

## 21. Conclusion

Maven Wrapper and Gradle Wrapper help a repository pin the **build tool version**, reducing reliance on global tools on developer machines or runners. Maven typically declares the distribution in `.mvn/wrapper/maven-wrapper.properties`; Gradle uses `gradle/wrapper/gradle-wrapper.properties` alongside the corresponding wrapper scripts and JAR.

In Java Advance Compatibility Migration, you must distinguish the **Wrapper distribution version**, **JDK running Maven/Gradle**, **compiler toolchain**, **Java release target**, and **plugin/dependency versions**. Upgrading one layer does not automatically upgrade the others. Consistency requires CI configuration, provenance/checksums, dependency management, and testing on the intended runtime.

A sustainable workflow uses the Wrapper across all environments, selects a build tool release supporting the target JDK, updates the complete set of wrapper files, conducts security reviews, upgrades plugins based on evidence, and records metadata for each release. That turns the Wrapper into part of a reproducible and maintainable Java application contract rather than just a convenient launch script.
