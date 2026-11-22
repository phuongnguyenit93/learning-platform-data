# Toolchain Checklist for Java Projects

## 1. Purpose and Scope

A Java toolchain is the set of tools and configurations that turns source code into artifacts that can be tested, executed, and distributed. A toolchain typically includes:

- JDK and Java runtime.
- Compiler, archive, documentation, and diagnostic tools.
- Build tools such as Maven or Gradle.
- Dependency repositories and version policy.
- IDE/editor and project configuration.
- Test framework and quality checks.
- CI runner, cache, and artifact storage.
- Runtime/container/installer when the project needs to distribute an application.

This checklist is used when setting up a new developer machine, auditing a machine that already has Java installed, standardizing a project, or reviewing before a release. Each item should have a status and verification evidence. Mark an item complete only when there is an actual verified result, not merely because a tool has been installed.

## 2. Define Requirements Before Installation

Before choosing a JDK or build tool, clearly document:

- The minimum Java version the application must support.
- The JDK used to run the compiler and build tool.
- Supported operating systems and CPU architectures.
- Maven or Gradle; which version is pinned by the project.
- Artifacts to be produced: library JAR, executable JAR, WAR, ZIP, container image, or installer.
- The IDE/editor and test framework used by the team.
- Dependency repositories, proxies, and internal certificates, if any.
- Mandatory quality gates: compile, unit tests, integration tests, static analysis, vulnerability scan, license, signing.
- How artifacts and build reports are stored.

Distinguish between the three Java versions:

| Component | Meaning | Example |
|---|---|---|
| Build JDK | JDK that runs Maven/Gradle and the compiler | JDK 21 |
| Target release | Java API and bytecode targeted by the source code | Java 17 |
| Runtime JDK | Java that actually runs the application | Java 17 or newer |

A machine can run Gradle with JDK 21, compile source code against the Java 17 API, and run the artifact on Java 17. These three values must be controlled separately.

## 3. Choose an Appropriate JDK Distribution

The JDK includes the Java runtime and development tools such as `javac`, `jar`, `javadoc`, `jshell`, and `jdeps`. Install the full JDK on developer machines and build runners.

Common distributions include Eclipse Temurin, Amazon Corretto, Azul Zulu, Oracle JDK, and Microsoft OpenJDK. When choosing, check:

- Vendor and official download source.
- Java version and security update schedule.
- Operating system, architecture, and package type.
- Your organization's licensing and support policies.
- Availability of updates throughout the product lifecycle.
- Internal rules regarding vendor consistency, if any.

Not every project needs to use the same vendor, but a single project should clearly define the vendor/version for CI builds so results are reproducible. If the production runtime uses a different vendor from the build JDK, include that runtime in compatibility testing.

**Checklist**

- [ ] Java baseline and supported runtimes are defined.
- [ ] JDK distribution is selected from an official source.
- [ ] Correct OS and architecture are selected, e.g., Windows x64 or Linux ARM64.
- [ ] Vendor license and update policy are confirmed.
- [ ] Vendor, version, and installation source are documented.
- [ ] Development JDK is distinguished from the minimum runtime required to run the product.

## 4. Install the JDK and Verify the Directory

After installation, locate the JDK root directory. This directory usually contains subdirectories such as `bin`, `conf`, `include`, `jmods`, and `lib`. Do not point `JAVA_HOME` directly to the `bin` directory.

Example:

~~~text
C:\Program Files\Java\jdk-21\
├── bin\
├── conf\
├── include\
├── jmods\
└── lib\
~~~

On Linux/macOS, the JDK is typically located in a directory managed by the package manager or vendor installer. Do not move the JDK directory after configuring `JAVA_HOME` without updating the related paths.

**Checklist**

- [ ] JDK is installed in a stable path with read and execute permissions.
- [ ] The `bin` directory contains `java` and `javac`.
- [ ] Multiple JDKs are not extracted into the same directory.
- [ ] Files from two vendors/versions are not mixed in a single JDK directory.
- [ ] The JDK path is recorded for IDE and build tool configuration.

## 5. Configure JAVA_HOME and PATH

`JAVA_HOME` should point to the JDK root directory. `PATH` must include the `bin` directory so the shell can find the executables.

Windows PowerShell, for the current terminal only:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
~~~

Linux/macOS:

~~~bash
export JAVA_HOME=/opt/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
~~~

The commands above only modify the environment of the current terminal and its child processes. For persistent configuration, use Windows Environment Variables or the appropriate shell profile such as `~/.bashrc` or `~/.zshrc`. On macOS, you can use `/usr/libexec/java_home` to select an installed JDK.

Do not set `JAVA_HOME` to a path ending with `/bin`. Do not add multiple JDK directories to `PATH` without a clear priority order. Do not set a global `CLASSPATH` to resolve per-project dependencies.

**Checklist**

- [ ] `JAVA_HOME` points to the correct JDK root.
- [ ] `PATH` contains `JAVA_HOME/bin`.
- [ ] The desired JDK appears before older Java installations in `PATH`.
- [ ] A new terminal was opened after making persistent environment changes.
- [ ] Global `CLASSPATH` is not used to manage project dependencies.

## 6. Verify the Active Java Executables

Run:

~~~bash
java --version
javac --version
jar --version
~~~

Windows PowerShell:

~~~powershell
Get-Command java, javac, jar -All | Select-Object Name, Source
$env:JAVA_HOME
~~~

Windows Command Prompt:

~~~cmd
where.exe java
where.exe javac
~~~

Linux/macOS:

~~~bash
command -v java
command -v javac
type -a java
echo "$JAVA_HOME"
~~~

Ensure `java` and `javac` come from the expected JDK. If `java` returns JDK 21 while `javac` comes from JDK 17, `PATH` may contain multiple JDKs in an unintended order.

You can view detailed runtime information:

~~~bash
java -XshowSettings:properties -version
~~~

Check `java.home`, `java.version`, `java.vendor`, `os.name`, `os.arch`, `file.encoding`, and `user.dir`. Do not include the full output in logs if the environment contains internal paths or unnecessary information.

**Checklist**

- [ ] `java --version` matches the expected version.
- [ ] `javac --version` matches the expected compiler.
- [ ] `java` and `javac` belong to the same JDK unless intentionally using a different toolchain.
- [ ] `java.home` and `java.vendor` match the environment.
- [ ] No older Java executable is shadowing the desired JDK.

## 7. Verify Bundled JDK Tools

In addition to `java` and `javac`, check the tools required for the project:

| Tool | Purpose | When Needed |
|---|---|---|
| jar | Create and read JARs | Package/inspect JAR |
| javadoc | Generate API documentation | Library or project requiring docs |
| jshell | REPL for testing Java expressions | Learning, exploring APIs |
| jdeps | Analyze dependencies and modules | Dependency inspection, preparing for `jlink` |
| jlink | Create custom runtime images | Distributing a minimal runtime |
| jpackage | Create application packages/installers | Distributing desktop/native packages |
| keytool | Manage keystores and certificates | TLS, signing, truststore |
| jarsigner | Sign and verify JARs | Releases requiring signatures |

Check versions:

~~~bash
jar --version
javadoc --version
jshell --version
jdeps --version
jlink --version
jpackage --version
keytool -help
jarsigner -help
~~~

Not every project needs `jlink` or `jpackage`. If a tool is out of scope, mark it as not applicable rather than treating its absence as a JDK failure.

**Checklist**

- [ ] `jar` works.
- [ ] `javadoc` works if API docs need to be published.
- [ ] `jshell` works if the team uses the REPL.
- [ ] `jdeps` works if dependency analysis is needed.
- [ ] `jlink`/`jpackage`/`keytool`/`jarsigner` are available when required by project goals.

## 8. Choose Java Release and Compiler Settings

Explicitly set the Java release so the build does not accidentally use APIs newer than the minimum runtime.

`javac` command:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/App.java
~~~

Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

If the project uses preview features, configure compile and runtime consistently with the exact JDK release; preview bytecode is not a way to produce artifacts compatible with arbitrary runtimes.

Do not set only `sourceCompatibility`/`targetCompatibility` or `source`/`target` if the goal is to also restrict the Java API. Use `--release` when appropriate and test on the minimum supported runtime.

**Checklist**

- [ ] Java release is agreed upon in the project.
- [ ] Compiler uses `--release` or equivalent configuration.
- [ ] Source encoding is explicitly set to `UTF-8` if that is the project standard.
- [ ] Preview features are only enabled when explicitly required.
- [ ] Runtime is tested on the lowest supported Java version.

## 9. Install and Pin Maven or Gradle

Choose one primary build tool per project. Do not require developers to install an exact global version if the project provides a wrapper.

Maven Wrapper:

~~~bash
./mvnw --version
~~~

Windows:

~~~powershell
.\mvnw.cmd --version
~~~

Gradle Wrapper:

~~~bash
./gradlew --version
~~~

Windows:

~~~powershell
.\gradlew.bat --version
~~~

Commit wrapper files to the repository. Pin the distribution version in the wrapper properties and verify the distribution checksum if required by policy. The wrapper ensures every developer and CI runner uses the same build tool version.

Release builds should not depend on whatever Maven/Gradle version happens to be on `PATH`.

**Checklist**

- [ ] Project has chosen Maven or Gradle.
- [ ] Wrapper files are committed.
- [ ] Build tool distribution version is pinned.
- [ ] Wrapper checksum is configured/verified when appropriate.
- [ ] Both CI and local runs invoke the wrapper instead of a global command.
- [ ] No build script requires an undocumented tool version.

## 10. Configure JDK Toolchains in Maven and Gradle

The build JVM and compiler JDK can be different. The build tool can run on JDK 21 while the compiler uses JDK 17 via a toolchain.

Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

A Gradle toolchain selects the JDK for tasks that require Java tools. The Gradle daemon still runs on its own JVM; inspect the `gradle --version` output to see the Launcher JVM and Daemon JVM.

Maven can use Maven Toolchains. A `toolchains.xml` file declares installed JDKs, and then the Maven Compiler Plugin or toolchain-aware plugins select the right JDK. Example configuration in `pom.xml`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

JDK paths in `toolchains.xml` are machine/runner-specific configuration; do not commit personal paths into `pom.xml`. CI must install or provision the appropriate JDK and verify that the toolchain resolves.

**Checklist**

- [ ] Build JVM version is defined.
- [ ] Compiler JDK/toolchain version is defined.
- [ ] Target release aligns with runtime requirements.
- [ ] Gradle daemon JVM and compiler toolchain are checked separately.
- [ ] Maven `toolchains.xml` is configured in each required environment.
- [ ] CI has the right JDK toolchain and does not rely on an arbitrary JDK on the runner.

## 11. Configure IDE and Editor

The IDE may use a different JDK from the terminal. Check these individual settings:

- Project SDK/JDK.
- Language level or Java compiler compliance.
- Bytecode target/release.
- Maven importer/runner JDK.
- Gradle JVM and Gradle toolchain.
- JRE/JDK in Run Configurations.
- Test runner and working directory.
- Annotation processors and generated sources if needed by the project.

For IntelliJ IDEA, check Project Structure, Maven/Gradle settings, and Run Configurations. For Eclipse, check Installed JREs, Java Compiler compliance, and Build Path. For VS Code, check the Java runtime selected by the extension and Maven/Gradle project import.

Run the same command from both the terminal and the IDE to spot differences if the build only fails in one environment.

**Checklist**

- [ ] IDE recognizes the correct JDK.
- [ ] Project language level matches target release.
- [ ] Maven/Gradle runner uses the right JVM.
- [ ] Run Configuration uses the right classpath/module path.
- [ ] Working directory and environment variables are explicitly set.
- [ ] No stale class outputs from another JDK or build configuration are used.

## 12. Standardize Encoding, Locale, and Line Endings

Set encoding explicitly in the build to avoid depending on the developer's machine.

Maven:

~~~xml
<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
~~~

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

You can use `.gitattributes`:

~~~gitattributes
* text=auto
*.java text eol=lf
*.gradle text eol=lf
*.xml text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
~~~

If the application formats dates/numbers or parses machine-readable data, specify `Locale` and timezone instead of relying on machine defaults. Test fixtures containing Vietnamese text, Unicode, and LF/CRLF line endings if the application processes files.

**Checklist**

- [ ] Source encoding is explicitly set.
- [ ] Line ending policy is stored in the repository.
- [ ] Tests include Unicode data when supported by the application.
- [ ] Locale/timezone are specified for data requiring a stable format.
- [ ] No configuration file works only because of a single machine's default encoding.

## 13. Manage Dependencies and Repositories

Dependencies are part of the toolchain because the build must resolve the exact versions of libraries and plugins.

- Declare direct dependencies in the Maven POM or Gradle build file.
- Pin plugin and dependency versions; use a BOM or version catalog where appropriate.
- Avoid dynamic versions and unstable snapshots in releases.
- Use dependency locking when transitive version control is needed.
- Define which repositories are allowed.
- Check proxies, TLS certificates, and authentication per policy.
- Do not put tokens/passwords in source code or build files.
- Do not download JARs from unknown sources.
- Save dependency reports when investigation is needed.

Maven and Gradle can use local caches. Caches speed up builds, but do not replace checking repositories and dependency versions. When diagnosing resolution errors, try building with the appropriate refresh/dependency insight flags and record the actual repository/error.

**Checklist**

- [ ] Direct dependencies and plugins have explicit versions.
- [ ] Repository policy is defined.
- [ ] Proxy/TLS/authentication work if required.
- [ ] No secrets appear in POM, `build.gradle`, or logs.
- [ ] Dependency locking/BOM/version catalog is used as needed.
- [ ] No snapshots or dynamic versions in releases if prohibited by policy.

## 14. Verify Compile, Test, and Package

A toolchain is only considered ready when it can complete the project's full build lifecycle.

Common Maven command:

~~~bash
./mvnw -B clean verify
~~~

Windows:

~~~powershell
.\mvnw.cmd -B clean verify
~~~

Common Gradle command:

~~~bash
./gradlew --no-daemon clean build
~~~

Windows:

~~~powershell
.\gradlew.bat --no-daemon clean build
~~~

Distinguish between the goals:

- Compile: main source and test source compile cleanly.
- Test: unit tests and configured test tasks run.
- Package/assemble: produces artifacts.
- Verify/check: runs declared quality gates.
- Install: installs artifacts into the local Maven repository or equivalent.
- Deploy/publish: pushes artifacts to a remote repository per configuration.

Maven `verify` does not automatically run every kind of static/security scan unless the project has configured the corresponding plugins. Gradle `check` likewise only runs verification tasks wired into the task graph.

**Checklist**

- [ ] Clean build succeeds.
- [ ] Mandatory unit tests pass.
- [ ] Integration tests run in a prepared environment.
- [ ] Skipped tests have documented reasons.
- [ ] Package/assemble produces the right artifact.
- [ ] Required verification tasks are configured and actually execute.
- [ ] Build returns exit code 0 and test reports are accessible.

## 15. Verify Output Artifacts

After building, inspect the artifact instead of just looking at the `BUILD SUCCESSFUL` line.

List JAR contents:

~~~bash
jar --list --file target/app.jar
~~~

Inspect the manifest:

~~~bash
jar --extract --file target/app.jar META-INF/MANIFEST.MF
~~~

Run the executable JAR if that is the target:

~~~bash
java -jar target/app.jar
~~~

Analyze dependencies/modules:

~~~bash
jdeps --multi-release 17 --print-module-deps target/app.jar
~~~

Compute checksum on Windows PowerShell:

~~~powershell
Get-FileHash .\target\app.jar -Algorithm SHA256
~~~

Linux:

~~~bash
sha256sum target/app.jar
~~~

For a library JAR, verify coordinates, POM/module metadata, and that consumer projects can resolve the dependency. For an executable JAR, verify `Main-Class` and runtime dependencies. For an application distribution, verify launcher scripts, config, permissions, and directory structure.

**Checklist**

- [ ] Artifact is generated in the expected directory.
- [ ] Name/version/coordinates are correct.
- [ ] Manifest or module metadata matches the artifact type.
- [ ] JAR can be listed and read.
- [ ] Smoke test runs on the minimum runtime.
- [ ] Required dependencies are fully distributed.
- [ ] Checksums are generated if required by the process.

## 16. Align CI Toolchain with Local

CI must use the wrapper and JDK specified in the build contract. Example GitHub Actions workflow for Maven:

~~~yaml
name: Java toolchain

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Show toolchain
        run: |
          java --version
          javac --version
          ./mvnw --version

      - name: Verify
        run: ./mvnw -B clean verify
~~~

This example runs on JDK 21. If multiple JDKs or OSes need testing, use a matrix and ensure the `setup-java` step actually consumes the matrix values. Do not declare a matrix and then accidentally hardcode a single version in the setup step.

For Gradle, use `cache: gradle` and run `./gradlew --no-daemon clean build`. In high-security environments, pin GitHub Actions to audited commit SHAs rather than relying solely on mutable version tags.

**Checklist**

- [ ] CI checks out the right source revision.
- [ ] CI installs the right JDK vendor/version.
- [ ] CI invokes the Maven/Gradle Wrapper.
- [ ] CI prints the versions of the runtime, compiler, and build tool.
- [ ] CI runs the same defined quality gates.
- [ ] Test reports and artifacts are uploaded when needed.
- [ ] Matrix actually uses the declared OS/JDK values.
- [ ] Release publication is separated from pull request verification.

## 17. Container and Runtime Distribution

If building or running the application in a container, clarify whether the image contains a JDK or only a runtime. Multi-stage builds typically use a JDK in the build stage and a smaller runtime image in the execution stage.

Items to check:

- Base image comes from a trusted registry.
- Tag or digest is pinned per policy.
- Image OS/architecture matches the artifact.
- Java runtime in the image matches the baseline.
- Container memory limit is accounted for when sizing the heap.
- Container user does not run as root unless necessary.
- Certificates/TLS and timezone data are present when required by the application.
- Native libraries match the ABI and architecture.

`jlink` can create a custom runtime image from the module closure. Only use it once dependencies/modules have been analyzed and tested on the final image. Do not assume a minimal runtime image includes all providers or native components.

**Checklist**

- [ ] Base image and Java runtime version are pinned.
- [ ] Build stage and runtime stage have clear roles.
- [ ] Runtime image passes smoke tests.
- [ ] Heap is appropriate for the memory limit.
- [ ] User, permissions, certificates, and native libraries are verified.
- [ ] Image scan is performed per security policy.

## 18. Security and Supply-Chain Checks

The toolchain is part of the software supply chain. Check the following:

- Install JDK and build tools from official sources or approved internal mirrors.
- Verify distribution checksums/signatures when published by the vendor.
- Pin dependency, plugin, and wrapper versions.
- Scan dependency vulnerabilities and licenses per policy.
- Scan for secrets in the repository and artifacts.
- Do not print credentials, tokens, or private keys in build logs.
- Generate an SBOM if required by the release process.
- Sign artifacts and verify signatures if required by the product.
- Update JDK/build plugins according to security advisories.
- Restrict permissions of CI tokens and signing credentials.

Do not bypass TLS certificate validation to work around download errors. If using a proxy or internal certificate, configure the truststore properly according to your organization's administration guidelines.

**Checklist**

- [ ] JDK/build tool sources are approved.
- [ ] Distribution checksums/signatures are verified when available.
- [ ] Dependency vulnerability and license scans have run.
- [ ] Secrets do not appear in source, artifacts, or logs.
- [ ] SBOM/signing are performed if required by release policy.
- [ ] CI credentials have minimum necessary permissions.

## 19. Reproducibility and Traceability

Reproducible builds aim to produce the exact same artifact from the same source and defined inputs. Traceability helps identify which source revision and process produced an artifact.

To improve reproducibility:

- Pin JDK, Maven/Gradle, plugins, and dependencies.
- Use wrappers and dependency locking where appropriate.
- Standardize encoding, locale, and timezone.
- Avoid unnecessary timestamps, absolute paths, and usernames in artifacts.
- Control generated sources/resources.
- Record source commit, build run ID, and toolchain versions.
- Compare checksums when checking byte-for-byte reproducibility.

Two builds can run identical logic yet produce JARs with different hashes due to timestamps or metadata. If byte-for-byte reproducibility is a goal, configure archive timestamps and dynamic metadata sources, then build twice from the same source in clean environments to verify.

**Checklist**

- [ ] Source commit is recorded.
- [ ] JDK/build tool/plugin/dependency versions are pinned.
- [ ] Build inputs and generated files are controlled.
- [ ] Locale/timezone/encoding are stable.
- [ ] Checksums are stored alongside artifacts.
- [ ] Reproducibility is tested if required for release.

## 20. Performance, Caching, and Developer Experience

A good toolchain provides fast feedback while preserving quality gates.

- Use incremental builds for local loops.
- Use clean builds in CI/release to avoid relying on stale outputs.
- Use Maven/Gradle caches safely.
- Run tests in parallel when tests are independent and thread-safe.
- Separate fast unit tests from heavy integration/E2E tests.
- Measure task/build phases before optimizing.
- Avoid caching secrets or untrusted artifacts across jobs.
- Record build duration and cache hit rates when needed.

Do not disable mandatory tests just to make builds faster. Optimize caching, test selection, or the task graph after gathering metrics.

**Checklist**

- [ ] Local and CI build times are tracked.
- [ ] Caching does not compromise correctness.
- [ ] Parallel tests do not share mutable state.
- [ ] Unit/integration/E2E tests have appropriate execution schedules.
- [ ] Clean build still succeeds.

## 21. Check Network Environment and Certificates

Build tools often need to download dependencies, plugins, or JDK distributions. When encountering resolution errors:

- Check DNS, proxy, and connectivity to the repository.
- Confirm repository URL and credentials.
- Check certificate expiration and truststore.
- Distinguish between authentication, authorization, timeout, and missing artifact errors.
- Inspect Maven/Gradle logs at an appropriate verbosity level.
- Do not disable TLS verification or use insecure HTTP to bypass errors.

Maven can use `settings.xml` to configure mirrors, proxies, and server credentials. Gradle can pull repository credentials from environment/secret stores. Do not commit personal `settings.xml` files or tokens to the repository.

**Checklist**

- [ ] Repositories are accessed over HTTPS or approved internal mirrors.
- [ ] Proxy/DNS work.
- [ ] TLS trust chain is valid.
- [ ] Credentials are provided outside source code.
- [ ] Download errors are classified by their actual root cause.

## 22. Minimal Smoke Test for JDK and Runtime

You can verify compiling, packaging, and running Java 17 with a small program.

File `ToolchainProbe.java`:

~~~java
package com.example;

/**
 * Minimal program used to verify the local Java toolchain.
 */
public final class ToolchainProbe {
    private ToolchainProbe() {
    }

    /**
     * Prints the runtime version and the requested verification target.
     *
     * @param args optional target label
     */
    public static void main(String[] args) {
        String runtime = System.getProperty("java.version");
        String target = args.length == 0 ? "local" : args[0];
        System.out.println("Toolchain probe passed");
        System.out.println("runtime=" + runtime);
        System.out.println("target=" + target);
    }
}
~~~

From the directory containing the source, compile:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/ToolchainProbe.java
~~~

Create an executable JAR:

~~~bash
jar --create --file build/toolchain-probe.jar --main-class com.example.ToolchainProbe -C build/classes .
~~~

Run:

~~~bash
java -jar build/toolchain-probe.jar ci
~~~

Output on Java 17.0.15 runtime:

~~~text
Toolchain probe passed
runtime=17.0.15
target=ci
~~~

If built with a newer JDK, the `runtime` line reflects the JDK running it. Run the same JAR on a Java 17 runtime to verify target compatibility.

You can generate Javadoc and analyze module dependencies:

~~~bash
javadoc -Xdoclint:all -d build/docs src/com/example/ToolchainProbe.java
jdeps --multi-release 17 --print-module-deps build/toolchain-probe.jar
~~~

For this program, `jdeps` identifies the module dependency as `java.base`. This is a smoke test for JDK tools; it does not replace the build and test suite of an actual project.

## 23. Phase-Based Checklists

### When setting up a developer machine

- [ ] Install JDK with the right vendor/version and architecture.
- [ ] Configure `JAVA_HOME` and `PATH`.
- [ ] Check `java`, `javac`, `jar`, and required tools.
- [ ] Install IDE/editor and select the right project SDK.
- [ ] Check Maven/Gradle Wrapper.
- [ ] Resolve dependencies from approved repositories.
- [ ] Run clean build and unit tests.
- [ ] Run the application or artifact smoke test.
- [ ] Record toolchain versions in team documentation.

### When creating or modifying a project

- [ ] Document Java baseline and target release.
- [ ] Pin build tool via wrapper.
- [ ] Configure compiler/toolchain.
- [ ] Configure encoding and line endings.
- [ ] Declare dependency/plugin versions.
- [ ] Configure unit/integration tests.
- [ ] Define artifact and naming.
- [ ] Configure CI to use the same build contract.
- [ ] Verify README has accurate build/run commands.

### Before release

- [ ] Clean build from a specific source revision.
- [ ] Use approved JDK/build tool versions.
- [ ] All mandatory tests and quality gates pass.
- [ ] Test on the minimum runtime and supported OSes.
- [ ] Artifact has the correct name/version/manifest/module metadata.
- [ ] Dependency and license scans meet policy.
- [ ] SBOM, checksum, and signature are generated if required.
- [ ] Artifact is stored at the designated release location.
- [ ] Save build logs, test reports, and provenance.
- [ ] Verify the released artifact can be downloaded and run.

## 24. Troubleshooting Common Toolchain Issues

| Symptom | Common Cause | Resolution |
|---|---|---|
| `java` not recognized | JDK not installed or wrong `PATH` | Check `JAVA_HOME`, `PATH`, and open a new terminal. |
| `java` and `javac` have different versions | Multiple JDKs in `PATH` | Check `Get-Command`/`where.exe` or `command -v`. |
| Maven/Gradle uses a different JDK | Build JVM/daemon differs from terminal | Check `mvn --version`, `gradle --version`, and toolchain configuration. |
| IDE compiles differently from terminal | Wrong Project SDK or runner JDK | Sync SDK, language level, and runner. |
| `UnsupportedClassVersionError` | Runtime is older than bytecode | Use a newer runtime or compile with the appropriate `--release`. |
| Dependency fails to resolve | Wrong repository, proxy, TLS, or version | Check URL, credentials, truststore, and dependency metadata. |
| Tests pass locally but fail in CI | Different environment, timezone, path, or services | Compare JDK/OS/env and run matrix. |
| JAR does not run after packaging | Missing `Main-Class` or runtime dependencies | Check manifest, classpath, and smoke test. |
| Build produces different hash | Timestamps or dynamic metadata | Control archive metadata if reproducibility is needed. |
| `OutOfMemoryError` in CI | Heap/container limits or parallel tests | Measure memory, tune heap and concurrency. |
| Javadoc fails | Missing comments, doclint, or source issues | Check specific warnings/errors and fix API docs. |
| TLS handshake fails | Certificate/proxy/truststore | Configure a valid trust chain; do not disable verification. |

When troubleshooting, collect at a minimum `java --version`, `javac --version`, `JAVA_HOME`, executable paths, Maven/Gradle versions, OS/architecture, and the build command executed. Do not include secrets in attached logs.

## 25. Project Toolchain Report Template

Verification results can be stored in the README, wiki, or build report:

~~~text
Project:
Source revision:
OS and architecture:
JDK distribution:
JDK vendor/version:
JAVA_HOME:
java executable:
javac version:
Target Java release:
Runtime versions tested:
Maven/Gradle wrapper version:
IDE and project SDK:
Dependency repository:
Build command:
Test command:
Artifact path and version:
Smoke test result:
Security/quality gate result:
CI run:
Known limitations:
Last verified:
~~~

This template helps distinguish a machine that merely has Java installed from a verified toolchain. A list of versions without build/test evidence is not enough to confirm a project is ready.

## 26. Sample Environment Verification Results

The smoke test checklist was run on Windows 11 x64 with:

| Component | Version / Result |
|---|---|
| Current JDK | Azul Zulu 24.0.2 |
| Compatibility runtime | Amazon Corretto 17.0.15 |
| Maven | 3.9.12 |
| Gradle | 9.2.1 |
| `javac --release 17` | PASS |
| `javadoc -Xdoclint:all` | PASS |
| `jar` create and list | PASS |
| `jdeps --multi-release 17` | PASS |
| JAR on Java 24 | PASS |
| JAR on Java 17 | PASS |

The JAR was compiled with JDK 24 using `--release 17` and ran successfully on both the Java 24.0.2 runtime and Corretto 17.0.15. `jdeps` reported the `java.base` module dependency. Javadoc was generated with full doclint and zero warnings after the source included comments for the class and `main` method.

These results confirm the smoke test suite on the stated Windows environment. Each project still needs to run its own tests on the OSes, JDK vendors, and runtimes in its own support matrix.

## 27. References

- [Java Platform, Standard Edition Documentation](https://docs.oracle.com/en/java/javase/25/)
- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Maven Wrapper](https://maven.apache.org/wrapper/)
- [Maven Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [GitHub Actions: Building and Testing Java](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-java-with-maven)

A toolchain is ready when developers and CI use the right JDK/build tools, compile against the right Java baseline, resolve dependencies reliably, run tests, and produce verifiable artifacts. Keep this checklist in the repository, update it when upgrading the JDK or build tool, and save build/test evidence for every toolchain change.