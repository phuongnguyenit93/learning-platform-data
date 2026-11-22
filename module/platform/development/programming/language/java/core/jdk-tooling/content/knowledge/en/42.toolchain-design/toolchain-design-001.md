# Defining Build Goals for a Java Project

## 1. What is a Build Goal?

A build goal describes the outcome a project needs to produce from its source code and defined inputs. It answers the following questions:

- What deliverable needs to be produced: a library JAR, executable JAR, WAR, application distribution, or container image?
- Which Java version, operating system, and architecture must the artifact run on?
- Which steps must complete before the build is considered successful?
- What quality characteristics need to be proven: compilation, tests, static analysis, dependency checks, packaging, or signatures?
- Where is the artifact stored, how is it named, and who will consume it?
- How can other developers or CI reproduce the build and verify the result?

A good build goal describes a verifiable outcome. “Build the Java application” is vague. A more concrete goal is: “Produce the executable JAR orders-cli-1.0.0.jar, compiled against the Java 17 API, runnable on Java 17 or newer, containing a Main-Class, passing unit tests, and having a SHA-256 checksum in CI.”

The build goal guides the configuration of the toolchain, build tool, tasks, dependencies, testing, and artifacts. Choosing Maven or Gradle before understanding the required output often leads to redundant or missing configuration.

## 2. Distinguishing Build Goal, Build Task, and Release Goal

| Concept | Question | Example |
|---|---|---|
| Build goal | What outcome needs to be achieved? | Produce a Java 17-compatible library JAR and run tests. |
| Build task/phase | What work must the tool perform? | compileJava, test, jar, Maven package. |
| Release goal | How should the artifact be prepared for distribution? | Sign the JAR, generate checksums and SBOM, and publish to a repository. |

A single goal may require multiple tasks. The goal of producing an executable JAR requires compiling classes, processing resources, creating a manifest, packaging, and verifying the run command.

Building is also different from deploying an application. The Maven `deploy` phase typically uploads artifacts to a remote repository; it does not mean deploying a service to production. Application deployment is a separate operational activity that may use a container platform, application server, or release system.

## 3. Starting from Consumers and Required Deliverables

Identify who will consume the build output:

| Consumer | Typical Artifact Needed | Key Criteria |
|---|---|---|
| Developers using it in another project | Library JAR, POM/module metadata | API, dependency metadata, version. |
| Users running from the command line | Executable JAR or application distribution | Entry point, runtime dependencies, arguments. |
| Users installing a desktop app | Installer or OS-specific package | Native launcher, runtime, icon, permissions. |
| CI/CD pipeline | JAR, ZIP, image, reports | Deterministic output, tests, checksums, provenance. |
| Release repository | Versioned artifacts | Coordinates, signature, SBOM, immutable version. |

Not every JAR needs a `Main-Class`. Library JARs are typically loaded by another application. Conversely, an executable JAR with a `Main-Class` may still fail to run if runtime dependencies are missing.

Defining the deliverable upfront helps decide whether you need a manifest, fat JAR, application distribution, module path, or installer.

## 4. Writing a Build Contract Before Configuring

A build contract is a concise description of the build's inputs, outputs, and acceptance criteria. It can be documented as a table in the project README:

| Component | Question to Answer | Example |
|---|---|---|
| Source | Which source revision is being built? | Currently checked-out Git commit. |
| Build JDK | Which JDK runs the build tool/compiler? | Temurin JDK 21. |
| Runtime baseline | What minimum Java version does the app require? | Java 17+. |
| Platform | Which OS/CPU architectures are supported? | Windows/Linux/macOS, x64. |
| Dependency | How are dependencies managed? | Versions pinned, no snapshots in releases. |
| Output | Which artifact must be produced? | orders-cli-1.0.0.jar. |
| Quality gates | Which conditions must pass? | Compile, unit tests, integration tests. |
| Reproducibility | Does the build need to be byte-for-byte reproducible? | Yes for release JARs. |
| Security | Which checks are mandatory? | Dependency scan, license policy, signing. |
| Delivery | Where is the artifact stored? | CI artifact or Maven repository. |

The build contract must be specific enough that someone else can run the exact command and verify the exact result.

## 5. Common Categories of Build Goals

A project may select one or more categories:

1. **Compile goal:** verify that source code compiles with the target JDK and API.
2. **Test goal:** run the required unit, integration, or contract tests.
3. **Package goal:** produce a JAR, WAR, ZIP, or distribution.
4. **Verification goal:** verify archive structure, manifest, metadata, static analysis, and quality rules.
5. **Compatibility goal:** confirm bytecode/API and runtime compatibility with supported Java versions.
6. **Reproducibility goal:** produce reproducible artifacts from the same source and pinned inputs.
7. **Security goal:** check dependencies, vulnerabilities, licenses, secrets, and signatures per policy.
8. **Performance goal:** bound build duration and CI resource usage.
9. **Publication goal:** publish artifacts with appropriate versions, checksums, SBOM, and metadata.
10. **Developer feedback goal:** keep the local compile/test loop fast and easy to diagnose.

It is not necessary to enable every gate on every run. For example, dependency vulnerability scans can run on pull requests and nightly builds; release signing only runs in the release pipeline.

## 6. Setting Measurable Acceptance Criteria

A goal is only useful when it can clearly answer whether the build succeeded or not. Avoid descriptions like “fast build”, “runs stably”, or “good compatibility” without measurable criteria.

Examples of acceptance criteria:

- `javac --release 17` compiles successfully.
- All mandatory unit tests pass; no tests are skipped outside the approved list.
- `mvn clean verify` or `gradle clean build` exits with code 0.
- The JAR has the correct name and version.
- The executable JAR has the correct `Main-Class` in its manifest.
- The JAR runs on JDK 17 and JDK 21 if both runtimes are within the supported scope.
- The dependency scan has no vulnerabilities exceeding the policy threshold.
- The release artifact has a valid SHA-256 checksum and signature if required by the process.
- Release builds use pinned dependency and tool versions.
- Build time stays within the agreed budget, e.g., under 5 minutes for pull requests on a standard runner.

Criteria must fit the deliverable. A library JAR does not need a `java -jar` run criterion; a GUI application may need an installation and launch smoke test.

## 7. Choosing the Build JDK and Target Java Version

Distinguish between:

- **Build JDK:** the JDK running Maven/Gradle and the compiler.
- **Target release:** the Java API and class file version that the source code is compiled against.
- **Runtime JDK:** the JDK used by end users or the deployment environment to run the artifact.

For example, a project can run Gradle on JDK 21 while producing Java 17 bytecode:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`toolchain` selects the JDK used for compile tasks. `options.release` restricts the target Java API and class file version. Setting only `source`/`target` without `release` can allow code to call APIs newer than the target runtime.

With Maven, declare:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

And pin the Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
~~~

If you need a compiler JDK different from the JVM running Maven, configure Maven Toolchains accordingly. Do not rely solely on `JAVA_HOME`; verify the actual JDK used by the build tool and compiler.

## 8. Defining Platform Scope

The build goal should explicitly state the supported platforms:

- Is it pure portable Java bytecode, or does it include JNI/JNA/native libraries?
- Are Windows, Linux, and macOS supported?
- Is x64, ARM64, or both supported?
- Does it depend on file permissions, symbolic links, shells, or OS services?
- Are OS-specific installers required?

If the application only uses standard Java APIs, a single JAR can run across multiple compatible OSes. If it includes native libraries, artifacts or distributions may need to be built separately per OS/architecture.

Do not label a build “cross-platform” if it is only compiled on a single runner. For products committed to multi-platform support, include the key OSes in the CI matrix and test on actual runtimes.

## 9. Selecting Build Steps Based on Goals

A typical Java pipeline includes:

~~~text
Source + configuration
        |
        v
Validate inputs and toolchain
        |
        v
Compile source
        |
        v
Process resources
        |
        v
Run unit tests
        |
        v
Package artifact
        |
        v
Verify artifact and quality gates
        |
        v
Publish or archive output
~~~

Not every project needs every step on every build. However, you must define which steps are mandatory before marking a build as successful.

For example:

- Compile-only checks can be used for fast feedback loops.
- `test` runs unit tests.
- `package` creates the artifact.
- `verify` runs the verification goals configured in the lifecycle.
- `publish` pushes the artifact to a repository or registry if configured appropriately.

A build that only compiles successfully does not prove that tests pass, that the JAR is runnable, or that runtime dependencies are complete.

## 10. Choosing Maven or Gradle Based on Needs

Maven fits well when a project needs clear conventions, a standard lifecycle, and familiar XML configuration. Gradle fits well when you need a flexible task graph, custom build logic, or Kotlin/Groovy DSL configuration.

| Need | Maven | Gradle |
|---|---|---|
| Standard Java compile/package | Compiler/JAR plugins and lifecycle | Java Plugin tasks |
| Running unit tests | Surefire/Failsafe | Test task and JUnit Platform |
| Selecting compiler JDK | Maven Toolchains/Compiler Plugin | Java Toolchains |
| Creating executable JAR | Maven JAR Plugin manifest | JAR task manifest |
| Customizing task graph | Plugin/phase configuration | Task graph and plugins |
| Dependency management | POM coordinates/scopes | Configurations/dependencies |
| Wrapper | Maven Wrapper | Gradle Wrapper |

The build goal dictates the required configuration. Do not add plugins or tasks just because another project uses them. Every component should serve a specific output or quality gate.

## 11. Example Build Contract for a CLI Application

Suppose you need to build a command-line tool:

| Requirement | Criterion |
|---|---|
| Deliverable | Executable JAR |
| Minimum Java | Java 17 |
| Build JDK | JDK 21 |
| Entry point | com.example.BuildGoalDemo |
| Input | Command-line arguments |
| Output | build-goal-demo-1.0.0.jar |
| Test | Unit tests for business logic |
| Runtime dependencies | Declared and fully distributed |
| Verification | JAR can be listed and run with java -jar |
| Release | Fixed version, checksum, and metadata |

An acceptance test can run:

~~~bash
java -jar build-goal-demo-1.0.0.jar ci
~~~

And check stdout:

~~~text
Build goal: package a Java 17 application
Target: ci
~~~

This is an observable criterion. If the command exits with code 0 and produces the expected output, the smoke test confirms the entry point works in that test environment.

## 12. Standalone Runnable Java 17 Example

Create `src/main/java/com/example/BuildGoalDemo.java`:

~~~java
package com.example;

public final class BuildGoalDemo {
    private BuildGoalDemo() {
    }

    public static void main(String[] args) {
        String target = args.length == 0 ? "local" : args[0];
        System.out.println("Build goal: package a Java 17 application");
        System.out.println("Target: " + target);
    }
}
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/example/BuildGoalDemo.java
~~~

Create the executable JAR:

~~~bash
jar --create \
  --file build-goal-demo.jar \
  --main-class com.example.BuildGoalDemo \
  -C build/classes .
~~~

Run:

~~~bash
java -jar build-goal-demo.jar ci
~~~

Exact stdout:

~~~text
Build goal: package a Java 17 application
Target: ci
~~~

This example runs standalone without external libraries. It demonstrates the compile + package + executable entry point goal. It does not replace unit tests, dependency scans, or integration tests for a real-world application.

## 13. Configuring Maven According to the Build Goal

Example `pom.xml` for a Java 17 CLI:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>build-goal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.BuildGoalDemo</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Build the artifact:

~~~bash
mvn -B clean package
~~~

Run:

~~~bash
java -jar target/build-goal-demo-1.0.0.jar ci
~~~

If the goal requires tests, add JUnit Jupiter and the Maven Surefire Plugin. If the goal requires static analysis, dependency checks, or signing, configure the corresponding plugins and clearly define pass/fail thresholds.

`package` creates the artifact. `verify` runs additional verification goals configured in the lifecycle; if the project has not configured quality plugins, do not assume `verify` automatically runs every kind of scan.

## 14. Configuring Gradle According to the Build Goal

Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.named('jar', Jar).configure {
    manifest {
        attributes 'Main-Class': 'com.example.BuildGoalDemo'
    }
}
~~~

Build:

~~~bash
./gradlew clean jar
~~~

On Windows:

~~~powershell
.\gradlew.bat clean jar
~~~

Run:

~~~bash
java -jar build/libs/build-goal-demo-1.0.0.jar ci
~~~

If the goal requires tests, configure JUnit and `useJUnitPlatform()`. The Gradle `check` task can aggregate verification tasks, while `build` typically depends on `check` and `assemble`.

Do not confuse `assemble` with `check`: one task produces artifacts, while the other checks quality according to configured tasks.

## 15. Defining Test Goals

Choose test types based on the risks that need to be verified:

| Test Type | Objective | Example |
|---|---|---|
| Unit test | Class/method logic | Input validation, calculations, mapping. |
| Integration test | Component integration | JDBC, filesystem, HTTP client. |
| Contract test | Interface/protocol compliance | JSON schema, API contract. |
| Smoke test | Artifact starts up | java -jar app.jar --help. |
| End-to-end test | Complete user flow | Calling CLI or REST workflow from start to finish. |

Not every test needs to run on every build. A common configuration:

- Pull request: compile, unit tests, static checks.
- Main branch: unit + integration tests, package, and smoke tests.
- Nightly: broad OS/JDK matrix, end-to-end, performance tests.
- Release: full verification, dependency/security scan, signing, and checksums.

Clearly specify which tests are mandatory. Skipped tests must have a reason, avoiding a gradual increase in skipped tests without anyone noticing.

## 16. Defining Dependencies and Build Inputs

A build can only be reproducible if its inputs are controlled.

Identify direct and transitive dependencies, plugin versions, JDK vendor/version, toolchains, build properties, environment variables, generated resources, repository dependencies, and native binaries if any.

Avoid uncontrolled dependency version changes, unstable snapshots in releases, and downloading tools from unverified URLs.

For releases, pin plugin and dependency versions, use dependency locking where appropriate, and record the source revision along with the toolchain version.

Do not package secrets or credentials into the JAR. Secrets should be provided at runtime or via the deployment environment's secret manager.

## 17. Defining Artifact Goals and Naming

An artifact needs a clear identity:

- `groupId`: organization group or namespace.
- `artifactId`: module name.
- `version`: product version.
- `classifier`: variant, if any.
- `packaging`: JAR, WAR, or other artifact type.

Example Maven coordinates:

~~~text
com.example:orders-cli:1.4.0
~~~

Typical filename:

~~~text
orders-cli-1.4.0.jar
~~~

Do not use generic names like `final.jar` for release artifacts. Names and versions help CI, users, and repositories distinguish between builds.

If producing multiple variants, clearly document the classifier or distribution convention, such as `linux-x64`, `windows-x64`, or `sources`. Only create variants when the deliverable genuinely needs to differ.

## 18. Quality Gates and Security Goals

A successful build does not mean the artifact is secure or ready for release. Choose gates based on risk level and organizational policy.

Examples:

- Compiler warnings or lint rules.
- Unit/integration tests.
- Static analysis and code coverage thresholds.
- Dependency vulnerability scan.
- License policy.
- Secret scanning.
- SBOM generation.
- Artifact signing and checksums.
- Container image scan if building containers.

Define clear thresholds, such as zero unaccepted critical vulnerabilities or coverage not falling below the project-agreed level. Do not pick an arbitrary threshold and treat it as a universal standard for every project.

Scans may require network access or external services. Record the scan database version and execution timestamp so results are explainable. Do not include API tokens or signing keys in source code or build logs.

## 19. Reproducibility and Traceability

Two builds from the same source can produce different artifacts if dependencies, timestamps, file order, or generated metadata change.

If the goal requires reproducible builds:

- Pin the JDK, build tool, plugins, and dependencies.
- Normalize archive timestamps and file order.
- Remove dynamic build times from manifests and resources.
- Control locale, timezone, and encoding.
- Avoid embedding absolute paths or usernames in the artifact.
- Rebuild from the same source revision and compare SHA-256 checksums.

Traceability adds information to answer where an artifact came from: Git commit/source revision, build JDK, build tool version, dependency lock, build run ID, checksums, and signatures if applicable.

Reproducibility answers “can the exact same artifact be recreated?”. Traceability answers “which source and process did this artifact come from?”. The two goals complement each other but are not the same.

## 20. Balancing Build Speed and Reliability

Fast builds give developers early feedback; release builds require more thorough checks.

| Run Level | Contents | Timing |
|---|---|---|
| Fast feedback | Compile and critical unit tests | While developers are working. |
| Pull request | Clean build, unit tests, static checks | Before merge. |
| Main branch | Integration tests, package, smoke tests | After merge. |
| Nightly | OS/JDK matrix, E2E, performance, dependency scan | Scheduled. |
| Release | Full verification, signing, SBOM, checksums | Before release. |

Use incremental builds to speed up the local loop. Use clean builds in CI/release to verify the artifact does not depend on stale outputs.

Do not compromise mandatory quality gates just to save a few seconds. If a build is slow, measure which tasks consume time and optimize caching, parallelism, or test selection while preserving quality goals.

## 21. CI: Turning Build Goals into a Pipeline

CI must enforce the same contract documented in the project. A basic workflow:

~~~yaml
name: Java build

on:
  pull_request:
  push:
    branches: [main]

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

      - name: Verify
        run: ./mvnw -B clean verify

      - name: Upload JAR
        uses: actions/upload-artifact@v4
        with:
          name: build-output
          path: target/*.jar
~~~

This workflow assumes the repository has the Maven Wrapper, the project builds on Ubuntu, and Maven `verify` is configured with the desired gates.

If supporting multiple OSes/JDKs, use a matrix. If the goal only requires a Java 17 runtime, include a job that actually runs on JDK 17; compiling with release 17 on JDK 21 does not replace runtime testing on Java 17.

Do not publish release artifacts from every pull request. Separate build verification and release publication using appropriate branches/tags, permissions, and approval policies.

## 22. Inspecting the Artifact After Building

After building, inspect the actual output rather than relying solely on the `BUILD SUCCESSFUL` message.

List JAR contents:

~~~bash
jar --list --file target/build-goal-demo-1.0.0.jar
~~~

Inspect the manifest:

~~~bash
jar --extract --file target/build-goal-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Run the executable JAR:

~~~bash
java -jar target/build-goal-demo-1.0.0.jar ci
~~~

Compute checksum in PowerShell:

~~~powershell
Get-FileHash .\target\build-goal-demo-1.0.0.jar -Algorithm SHA256
~~~

Linux:

~~~bash
sha256sum target/build-goal-demo-1.0.0.jar
~~~

If the goal is a library, verify coordinates, POM/module metadata, and that the artifact resolves in a consumer project. If the goal is an application distribution, inspect launcher scripts, the dependency directory, configuration, and permissions.

## 23. Lab: Verifying the Same Build Goal with javac, Maven, and Gradle

The `BuildGoalDemo.java` example in section 12 is used as the shared source. The lab goal is to build a Java 17 executable JAR, run it with the argument `ci`, and verify stdout.

**Method 1 — Direct JDK**

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/BuildGoalDemo.java
jar --create --file build-goal-demo.jar --main-class com.example.BuildGoalDemo -C build/classes .
java -jar build-goal-demo.jar ci
~~~

**Method 2 — Maven**

Use the POM in section 13:

~~~bash
mvn -B clean package
java -jar target/build-goal-demo-1.0.0.jar ci
~~~

**Method 3 — Gradle**

Use the build file in section 14:

~~~bash
./gradlew clean jar
java -jar build/libs/build-goal-demo-1.0.0.jar ci
~~~

All three methods must satisfy the same contract: compile targeting Java 17, JAR has the main class, and the program prints the exact two lines of output. Output folder structure and metadata may differ depending on the build tool.

## 24. Verified Lab Results

The Java 17 fixture was run on Windows with JDK 24.0.2, Maven 3.9.12, and Gradle 9.2.1.

| Build Method | Result | Verification |
|---|---|---|
| javac + jar | PASS | JAR runs with java -jar. |
| Maven Compiler 3.13.0 + JAR Plugin 3.4.2 | BUILD SUCCESS | Executable JAR runs. |
| Gradle 9.2.1 Java Plugin | BUILD SUCCESSFUL | Executable JAR runs. |

Stdout of all three artifacts when passing the `ci` argument:

~~~text
Build goal: package a Java 17 application
Target: ci
~~~

The builds use the same source, `--release 17`, and manifest main class. JAR hashes across the three builds are not expected to match because Maven and Gradle may add different metadata. The lab verifies identical runtime behavior and output contract, without claiming byte-for-byte reproducibility.

## 25. Common Mistakes When Defining Build Goals

| Mistake | Consequence | Fix |
|---|---|---|
| Only writing “build project” | Unclear artifact and pass criteria. | Describe deliverable, outputs, and acceptance criteria. |
| Confusing Build JDK with target Java | Artifact may require a newer runtime than intended. | Configure toolchain and --release separately. |
| Assuming every JAR is executable | Library JAR is mistakenly treated as broken. | Distinguish between application JARs and library JARs. |
| Only checking compilation | Test/dependency/manifest errors slip through. | Add tests, packaging, and smoke verification. |
| Treating package as release | Artifact lacks checksums, signatures, or metadata. | Define a separate release goal. |
| Not pinning plugins/dependencies | Builds can change over time. | Pin versions and manage dependencies. |
| Only running on developer machines | Environment issues surface late in CI. | Run CI on supported environments. |
| Running clean on every small change | Slow local feedback loop. | Incremental locally, clean in CI/release. |
| Using build exit code as the sole criterion | Artifact may miss entry point or dependencies. | Inspect the artifact and run smoke tests. |
| Not defining who receives the artifact | Output does not fit usage needs. | Start from the consumer and distribution method. |

## 26. Reusable Build Contract Template for Projects

You can use the following template in project documentation or pull requests:

~~~text
Build purpose:
Primary consumer:
Artifact type:
Artifact name and version:
Build JDK and vendor:
Minimum runtime Java:
Target release:
Supported OS/architecture:
Dependency and plugin policy:
Required compile/test/verification tasks:
Runtime dependency strategy:
Reproducibility requirement:
Security and signing requirements:
Output location:
CI command:
Acceptance criteria:
Release/publish destination:
~~~

Fill in each item with concrete values. If an item does not apply, explicitly state “not applicable” and why rather than leaving implementers to guess.

Example acceptance criteria for an executable CLI:

1. Maven `clean verify` exits with code 0.
2. Artifact is named `orders-cli-1.0.0.jar`.
3. Manifest has the correct `Main-Class`.
4. `java -jar orders-cli-1.0.0.jar --help` prints usage and exits with code 0.
5. Mandatory unit/integration tests pass.
6. Runtime dependencies are packaged or fully distributed.
7. Release artifact has checksums and signatures per policy.

## 27. References

- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [The jar Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [GitHub Actions Matrix Builds](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)

Define build goals by starting from the deliverable and its consumers, then writing a build contract covering JDK, runtime baseline, artifacts, quality gates, and acceptance criteria. Once the required outcome is clear, Maven or Gradle can then be configured to execute and prove those requirements.
