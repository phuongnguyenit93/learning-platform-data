# Installing the JDK in a CI/CD Pipeline

## Objectives

After this lesson, you will be able to explain why CI needs a JDK; distinguish a JDK from a runtime; choose the right version, vendor, architecture, and package; install or select a JDK on hosted runners, self-hosted runners, and containers; configure `JAVA_HOME` and `PATH`; verify the actual compiler/runtime; use GitHub Actions, GitLab CI, Azure Pipelines, and Jenkins to set up a JDK; manage multiple JDKs using matrices and Java toolchains; cache JDKs/dependencies properly; verify checksums and download sources; and troubleshoot errors when a pipeline cannot find Java or uses the wrong Java version.

## 1. What is a JDK in CI?

CI (Continuous Integration) runs automated builds and checks whenever source code changes or on a schedule. To compile, test, generate Javadoc, and package a Java application, the CI agent needs a **Java Development Kit (JDK)** that matches the project.

A JDK provides development tools, for example:

- **java:** launches Java applications.
- **javac:** compiles `.java` source files into `.class` bytecode.
- **jar:** creates and manipulates Java archives.
- **javadoc:** generates API documentation.
- Diagnostic tools such as `jcmd`, `jstack`, and `jmap`, depending on the package.

A JDK typically also includes the Java runtime needed to run programs. A runtime-only image can run an already-built application but lacks `javac`, so it is unsuitable for jobs that must compile source code.

**Installing the JDK in CI** means making the right Java toolset available in the build environment, and then ensuring that build commands actually use that toolset.

A pipeline can obtain a JDK from:

1. A hosted runner with a pre-installed JDK.
2. A CI action/task that downloads and installs a JDK by version/vendor.
3. A Docker/container image that already contains a JDK.
4. An internal JDK archive extracted on the runner.
5. Centrally managed tool installations on Jenkins or a self-hosted agent.

There is no single approach that fits every CI setup. Choose the approach that matches your runner type, security requirements, network access, and required level of reproducibility.

## 2. Distinguishing JDK, Runtime, and Java Version

### JDK vs. Runtime

| Component | What it contains | When to use |
|---|---|---|
| JDK | Runtime along with compiler and development tools | Compile, test, generate Javadoc, package |
| Runtime image | Components needed to run an application | Run already-built artifacts |
| JRE (traditional term) | Java runtime environment | Common concept in older Java releases; not always distributed as a separate package in modern Java |

If a pipeline runs `javac`, it needs a JDK. A successful `java --version` command does not prove that the compiler is installed. Always check both:

~~~bash
java --version
javac --version
~~~

### JDK Version vs. Application Target

There are three choices to distinguish:

- **Build-running JDK:** the JVM that launches Maven or Gradle.
- **Compiler/toolchain JDK:** the compiler used to compile source code.
- **Java release target:** the bytecode and API version that the artifact is allowed to use.

For example, a project can run Maven on JDK 21, use the JDK 21 compiler, but produce Java 17-compatible bytecode using `--release 17`.

Therefore, `java --version` only tells you the runtime found via `PATH`. It does not necessarily tell you whether the compiler or test task is using the same JDK. Also check `mvn --version`, `./gradlew --version`, and the project's toolchain configuration.

## 3. Choosing a JDK Before Installing

Before configuring the pipeline, determine the following attributes:

| Attribute | Question to answer |
|---|---|
| Feature version | Does the project require Java 17, 21, or 25? |
| Vendor/distribution | Use Temurin, Oracle, Corretto, Zulu, Microsoft Build of OpenJDK, or an organization-approved distribution? |
| Architecture | Is the runner x64, ARM64, or another architecture? |
| Operating system | Linux, Windows, or macOS? |
| Package | Do you need a standard JDK, a JDK with JMODs, or a special package? |
| Patch level | Accept the latest update of a feature release or pin a specific patch? |
| Support policy | Which version is supported by the vendor/organization and still receives security updates? |

### Choosing a Feature Release

Older projects may need JDK 17; newer projects may standardize on JDK 21 or JDK 25. Base your decision on:

- Gradle/Maven and plugin versions.
- Frameworks and dependencies.
- Language features used.
- Production runtime.
- Support and security update policies.

Do not upgrade the JDK just because the runner happens to have the latest version pre-installed. Before upgrading, check whether Gradle/Maven, plugins, test engines, annotation processors, native libraries, and dependencies support it.

### Choosing a Vendor

Many distributions provide OpenJDK builds. They may differ in release schedules, support, packaging, certifications, update policies, and terms of use.

Choose an organization-approved distribution, specify its name explicitly in the CI configuration, and keep it consistent across CI, staging, and production when compatibility requirements demand it.

### Choosing a Version Selector

A configuration like `21` usually means selecting a build from feature release 21 according to the installer's metadata/tool cache. It may receive newer patch updates over time.

If strict reproducibility is required, pin a specific patch/build or pin the container image digest. If the goal is to automatically receive security updates within the same feature release, use a major-version selector and schedule checks on update results.

## 4. CI Agents and JDK Installation Models

### Hosted Runners

A hosted runner is a virtual machine created by the CI provider for a job. Some JDKs may already be pre-installed or present in the tool cache.

Do not assume every hosted image has the same Java versions. The pre-installed list changes by OS image and over time. Use an installation action/task to explicitly request the version and vendor; a verification step helps detect environment changes.

### Self-Hosted Runners

Self-hosted runners are managed by your organization. You can pre-install JDKs on the machine, store multiple versions, or use an installer within the job.

The advantage is control over networking, mirrors, tool versions, and resources. In return, you must manage patches, permissions, disk space, `PATH`, `JAVA_HOME`, and cleaning up old tools.

### Container-Based Runners

The job runs inside a container image. The JDK must be present in the image in which the job executes; a JDK on the host runner does not automatically appear inside the container.

For example, the `eclipse-temurin:21-jdk` image contains JDK 21. If you need Maven, you can use a Maven image paired with a JDK, or install/run Maven Wrapper inside the JDK image.

### Per-Job Installation vs. Baking into an Image

| Approach | Best suited when | Key considerations |
|---|---|---|
| CI action/task | Hosted runners or jobs needing multiple versions | Easy to declare versions; may download the JDK |
| Container image | Jobs using a Docker/Kubernetes executor | Pin tag/digest; update the image periodically |
| Pre-installed JDK | Stable self-hosted runners | Manage tools on each agent |
| Internal archive | Restricted networks or custom distributions | Verify checksum/signature and manage versions |
| OS package manager | Controlled Linux runners | Repositories and package versions must be pinned/controlled |

## 5. JAVA_HOME and PATH

These two variables determine which Java commands many build tools find.

- `JAVA_HOME` should point to the root directory of the JDK.
- `PATH` should include the JDK's `bin` directory.

Linux example:

~~~bash
export JAVA_HOME=/opt/jdk/temurin-21
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
~~~

The path above is an example; replace it with your actual installation directory.

Correct structure:

~~~text
/opt/jdk/temurin-21/
├── bin/
│   ├── java
│   ├── javac
│   └── jar
├── conf/
├── include/
└── lib/
~~~

`JAVA_HOME` must point to `/opt/jdk/temurin-21`, not `/opt/jdk/temurin-21/bin` and not the `java` file itself.

### Windows

PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java --version
javac --version
where.exe java
where.exe javac
~~~

On Windows, use a semicolon to separate `PATH` entries. Linux/macOS use a colon.

### Checking Which Command Is Invoked

Linux/macOS:

~~~bash
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
~~~

Windows:

~~~powershell
where.exe java
where.exe javac
Write-Output $env:JAVA_HOME
~~~

If `java` and `javac` come from two different directories, the pipeline may run with one runtime while compiling with a different JDK. Check `PATH` ordering and invoke `$JAVA_HOME/bin/java` or `$JAVA_HOME/bin/javac` directly when diagnosing.

### Do Environment Variables Persist Across Steps?

An `export` command only affects the current shell process and its child processes. In CI systems with separate steps, do not assume an `export` in one step persists to the next step.

- GitHub Actions: use `GITHUB_ENV` and `GITHUB_PATH` to pass variables/paths to subsequent steps; `setup-java` configures the environment automatically.
- GitLab CI: `before_script` and `script` commands within the same job run in the job environment; separate jobs have their own environments.
- Azure Pipelines: installer tasks set `JAVA_HOME`/`PATH` for subsequent tasks in the job.
- Jenkins Declarative Pipeline: the `tools` block sets up the environment for the corresponding pipeline or stage.

Installing a JDK in one job does not automatically make it available in another job, unless jobs share a persistent environment or an artifact/image/tool cache is explicitly configured.

## 6. Verifying the JDK After Installation

A verification step should run right after the setup step, before invoking Maven or Gradle.

~~~bash
set -eu

if [ -z "$JAVA_HOME" ]; then
  echo "JAVA_HOME is not set" >&2
  exit 1
fi

test -x "$JAVA_HOME/bin/java"
test -x "$JAVA_HOME/bin/javac"

echo "JAVA_HOME=$JAVA_HOME"
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version

command -v java
command -v javac
~~~

These checks confirm:

1. `JAVA_HOME` is set.
2. Both the Java runtime and Java compiler exist in the JDK.
3. Binaries inside `JAVA_HOME` can be executed directly.
4. `PATH` exposes the Java commands for build scripts to use.

Then verify the build tool:

~~~bash
mvn --version
./gradlew --version
~~~

Only run the command corresponding to your project's build tool. Maven and Gradle display the JVM used to launch the build tool itself; toolchain configuration may select a different compiler/test JDK.

## 7. Installing the JDK with GitHub Actions

`actions/setup-java` is the official action for selecting and installing Java for a workflow. It can download the requested distribution, use the tool cache on hosted runners, set up `JAVA_HOME` and `PATH`, and support dependency caching for Maven, Gradle, and sbt.

The following example uses JDK 21 and Maven:

Create `.github/workflows/java-ci.yml`:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 21
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify JDK
        run: |
          echo "JAVA_HOME=$JAVA_HOME"
          java --version
          javac --version

      - name: Build and test
        run: ./mvnw --batch-mode --no-transfer-progress verify
~~~

Explanation:

- `distribution: temurin` selects Eclipse Temurin.
- `java-version: '21'` selects feature release 21.
- `setup-java` sets `JAVA_HOME` and adds `bin` to `PATH` for subsequent steps.
- `cache: maven` caches Maven dependencies and the corresponding wrapper cache.
- `./mvnw` uses the repository's Maven Wrapper to pin the Maven version.
- `verify` runs the lifecycle phases up to `verify`.

If the project uses Gradle, you can change the cache and build command:

~~~yaml
      - name: Set up JDK 21
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Build and test
        run: ./gradlew --no-daemon check
~~~

There is no need to install Maven or Gradle separately if the repository already commits the wrapper and the runner has the tools needed for the wrapper to run.

### Testing Multiple JDKs with a Matrix

If the project supports multiple Java releases, use a matrix to run the same build on each version:

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']

    name: Verify on Java ${{ matrix.java }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - run: java --version
      - run: javac --version
      - run: ./mvnw --batch-mode verify
~~~

Each matrix entry is a job with its own environment. The JDK is installed in that job and does not share `JAVA_HOME` with other jobs.

A matrix is useful when you need to confirm compatibility across multiple JDKs. If a project only supports one version, a multi-version matrix can waste CI time and download dependencies unnecessarily.

### Installing Multiple JDKs in the Same Job

`setup-java` supports multiple versions in the `java-version` input. All JDKs are installed; the last added version becomes the default in `PATH`. Other JDKs can be accessed via version-specific variables such as `JAVA_HOME_17_X64`.

Use this approach when a single job genuinely needs to run multiple compilers/test runtimes. If you only need compatibility testing, a matrix is usually easier to isolate and read.

### Versions and Distributions

`setup-java` v6 supports many distributions and version syntaxes. You can use a major version, a specific patch version, a version range, or the `latest` alias depending on distribution support.

`latest` changes according to release metadata. Use it for jobs that test against the newest GA release; use explicit versions for release builds that require reproducibility.

For self-hosted runners, `setup-java` v6 uses Node 24; the runner needs a compatible version (from v2.327.1 per the action's documentation). Check runner requirements before upgrading the action.

## 8. Installing the JDK with GitLab CI

For GitLab Runners using a Docker or Kubernetes executor, the simplest approach is to choose a job image that already has a JDK. `image` is the container image used to run the job's commands.

Example using the Maven Official Image paired with Eclipse Temurin JDK 21:

~~~yaml
stages:
  - verify

default:
  image: maven:3-eclipse-temurin-21-noble

variables:
  MAVEN_OPTS: "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"

cache:
  key:
    files:
      - pom.xml
  paths:
    - .m2/repository/

verify:
  stage: verify
  script:
    - java --version
    - javac --version
    - mvn --batch-mode --no-transfer-progress verify
~~~

The Maven image includes both Maven and a JDK, so the job does not need to download Maven separately. If you use a JDK-only image, use Maven Wrapper or install the build tool in a project-managed way.

### Choosing the Right Image

- Use a JDK image if the project has a wrapper or build script that already provisions Maven/Gradle.
- Use a Maven image if the job invokes `mvn` directly.
- Use tags that explicitly specify the Maven version, JDK distribution/version, and base OS when control is needed.
- Pin the image digest if you need the exact same immutable image across runs.

The tag `maven:3-eclipse-temurin-21-noble` indicates Maven major 3, Temurin 21, and Ubuntu Noble. Tags can be updated; digests pin more strictly than tags.

### Notes on Executors

`image` applies to container-based executors such as Docker or Kubernetes. With a Shell executor, scripts run directly on the runner machine; specifying a container image in `.gitlab-ci.yml` does not automatically install a JDK on that host.

With a Shell executor, install the JDK on the host runner and configure `JAVA_HOME`/`PATH`, or switch the job to a container-based executor if your CI architecture allows it.

### Caching in GitLab

The example above caches the Maven repository at `.m2/repository`. Dependency caching reduces artifact download time; it is not a way to install the JDK.

If the project uses Gradle, cache the appropriate dependency/wrapper directories and choose an image with a compatible JDK. Do not share stateful caches unsafely across concurrently writing jobs; use cache keys and pull/push policies per pipeline.

## 9. Installing the JDK with Azure Pipelines

Azure Pipelines provides the `JavaToolInstaller@1` task. This task retrieves a JDK from the tool cache, a local directory, or Azure Storage and sets `JAVA_HOME` for subsequent tasks.

Example selecting a JDK already present on a Microsoft-hosted agent:

~~~yaml
trigger:
- main

pool:
  vmImage: ubuntu-latest

steps:
- checkout: self

- task: JavaToolInstaller@1
  displayName: Use JDK 21
  inputs:
    versionSpec: '21'
    jdkArchitectureOption: 'x64'
    jdkSourceOption: 'PreInstalled'

- script: |
    echo "JAVA_HOME=$JAVA_HOME"
    java --version
    javac --version
    ./mvnw --batch-mode verify
  displayName: Verify JDK and build
~~~

`PreInstalled` only works when the hosted agent image actually has the requested version. Check the software list of the image you are using.

### JDK Sources in JavaToolInstaller

| jdkSourceOption | Source | When to use |
|---|---|---|
| PreInstalled | JDK already in the agent tool cache | Hosted images or pre-configured agents |
| LocalDirectory | JDK archive at a local path or source | Self-hosted agents or pre-downloaded packages |
| AzureStorage | Archive in Azure Storage | Organizations storing JDKs internally |

With `LocalDirectory`, provide `jdkFile` pointing to the archive and `jdkDestinationDirectory` for extraction. The archive must contain a valid JDK structure.

With `AzureStorage`, task v1 uses an Azure Resource Manager service connection and Azure RBAC to read the blob. Grant the `Storage Blob Data Contributor` role to the service connection's identity per Azure policy; avoid putting storage keys or long-lived SAS tokens in YAML.

The task sets `JAVA_HOME` and updates `PATH` for subsequent steps. If using a self-hosted agent, verify the agent version and permissions to access the archive/tool cache.

## 10. Installing the JDK with Jenkins

Jenkins manages JDKs as tool installations. Administrators declare JDKs in:

**Manage Jenkins → Tools**

You can choose to:

- Use a JDK pre-installed on the agent and declare the exact JDK home.
- Automatically install a JDK using a configured installer.
- Use an archive from an internal repository via a custom installer.

In a Declarative Pipeline, declare the tool by its registered name:

~~~groovy
pipeline {
    agent any

    tools {
        jdk 'Temurin-21'
    }

    stages {
        stage('Verify JDK') {
            steps {
                sh 'echo "JAVA_HOME=$JAVA_HOME"'
                sh 'java --version'
                sh 'javac --version'
            }
        }

        stage('Build') {
            steps {
                sh './mvnw --batch-mode verify'
            }
        }
    }
}
~~~

`Temurin-21` is the logical name configured by the administrator in Jenkins Tool Configuration. It must match the name referenced in the `Jenkinsfile` exactly.

In a Declarative Pipeline, `tools` sets `JAVA_HOME` and adds the `bin` directory to `PATH` for the corresponding pipeline or stage.

### Scripted Pipeline

In a Scripted Pipeline, the `tool` step returns the JDK home path. You must add it to the environment yourself:

~~~groovy
node {
    def jdkHome = tool name: 'Temurin-21', type: 'jdk'

    withEnv([
        'JAVA_HOME=' + jdkHome,
        'PATH+JDK=' + jdkHome + '/bin'
    ]) {
        sh 'java --version'
        sh 'javac --version'
        sh './mvnw --batch-mode verify'
    }
}
~~~

On Windows agents, use `bat` and `%JAVA_HOME%\bin` according to Windows syntax.

### Multiple Jenkins Agents

A logical JDK may reside at different paths on Linux and Windows agents. Configure Tool Locations per agent so Jenkins knows the right home on each node.

With container agents or ephemeral agents, auto-install may have to re-download the JDK every time a new container is created. If startup time is significant, bake the JDK into a custom agent image and register it as a pre-installed tool.

## 11. Installing the JDK Using a Container Image

Container images are one way to package a CI environment. If the image already includes the JDK, the pipeline does not need to install the JDK in every step.

Example Dockerfile for a build stage:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build

WORKDIR /workspace
COPY . .

RUN java --version
RUN javac --version
RUN ./mvnw --batch-mode verify
~~~

If the JDK image does not include Maven, use Maven Wrapper or choose a Maven image with the appropriate JDK. The build stage uses a JDK; the runtime stage can use a lighter runtime image if it only runs the artifact.

Multi-stage example:

~~~dockerfile
FROM maven:3-eclipse-temurin-21-noble AS build
WORKDIR /workspace
COPY . .
RUN mvn --batch-mode --no-transfer-progress verify package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

The filename `app.jar` is an example; replace it with your project's actual artifact. The build image needs a JDK because it includes the compiler; the runtime image can use a runtime suitable for how the application is packaged.

### Image Pinning and Security Updates

Tags are easy to read, but they can point to a newer image later. If strict reproducibility is needed, pin the digest:

~~~dockerfile
FROM eclipse-temurin:21-jdk@sha256:<verified-image-digest>
~~~

The digest must come from a trusted registry for the exact OS/architecture. Do not copy a digest from another image or another architecture.

Even when pinning digests, you still need a process to update images to receive security fixes. Pinning is meant to control when upgrades happen, not to keep old vulnerable images forever.

## 12. Installing the JDK Manually from an Archive

Manual installation is useful when the runner lacks a suitable action/task, in offline environments or those with access only to an internal artifact repository, when a custom JDK build is needed, when exact package/checksum control is required, or when preparing the JDK before a job runs.

Linux example with a `.tar.gz` archive:

~~~bash
set -eu

if [ -z "$JDK_ARCHIVE_URL" ] || [ -z "$JDK_SHA256" ]; then
  echo "Set trusted JDK_ARCHIVE_URL and JDK_SHA256" >&2
  exit 1
fi

mkdir -p "$RUNNER_TEMP/jdk"
curl --fail --location --silent --show-error \
  "$JDK_ARCHIVE_URL" \
  --output "$RUNNER_TEMP/jdk.tar.gz"

printf '%s  %s\n' "$JDK_SHA256" "$RUNNER_TEMP/jdk.tar.gz" \
  | sha256sum --check --strict

tar -xzf "$RUNNER_TEMP/jdk.tar.gz" \
  --directory "$RUNNER_TEMP/jdk" \
  --strip-components=1

export JAVA_HOME="$RUNNER_TEMP/jdk"
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
~~~

This snippet assumes the archive has a single top-level directory and `bin` resides directly beneath it. Check the vendor's archive layout before using `--strip-components=1`; if the layout differs, adjust the extraction command.

### Verifying Checksums

Do not download a JDK from an untrusted URL. Obtain the SHA-256 checksum or signature from the vendor's official release page/repository, then compare it against the downloaded file.

Eclipse Temurin provides SHA-256 checksum files alongside its archives. The example above accepts the checksum via the `JDK_SHA256` variable; the value must come from trusted metadata for the exact file, version, OS, and architecture.

Checksums help detect files that were altered or corrupted during download. If your organization requires release-source authentication, also verify digital signatures and public keys following the vendor's procedure.

### Using a Linux Package Manager

On Linux runners with appropriate repositories, you can install a JDK package using the OS package manager. Ubuntu example:

~~~bash
sudo apt-get update
sudo apt-get install --yes openjdk-21-jdk

java --version
javac --version
~~~

Packages can vary by Ubuntu version, repository, and architecture. For release builds, control repository/package versions or use an installer/image with explicit versions to avoid unexpected environment changes.

## 13. Build Tool Runtime and Java Toolchains

Installing a JDK in CI answers the question "which Java is on the machine?". Java toolchains answer the question "which JDK should a compile/test task use?".

The two mechanisms are related but distinct.

### Gradle Toolchains

In `build.gradle`:

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

In this example:

- The Java toolchain requires JDK 21 for Java tasks.
- `options.release = 17` restricts the API and output bytecode to Java 17.
- The JDK running the Gradle daemon can differ from the compiler toolchain if the environment has multiple JDKs and Gradle is configured accordingly.

If JDK 21 is already installed via a CI action or container image, Gradle can detect that toolchain. Gradle also supports auto-provisioning toolchains when a suitable toolchain download repository/resolver is configured; do not assume every CI build can auto-download a JDK if a resolver is missing.

### Maven Toolchains

Maven can run on one JDK while requiring compiler/test plugins to use another JDK.

A project can declare the Maven Toolchains Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>21</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

On the machine/agent, `~/.m2/toolchains.xml` maps requirements to JDK homes:

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

The path `/opt/jdk/temurin-21` is an example; replace it with the actual installation directory on the agent. A toolchain only selects an existing JDK; it does not install the JDK onto the machine itself.

Some installers, including `setup-java`, can generate Maven toolchains entries for installed JDKs. If you use this feature, verify that the version/vendor in the entry matches the requirements declared in the POM.

### `--release` Does Not Replace Installing the Right JDK

`--release 17` tells the compiler to produce Java 17-compatible bytecode and APIs. It does not install a JDK 17 compiler, nor does it change the JVM running Maven/Gradle.

If you need to test the application on Java 17, run the test JVM with JDK 17 or toolchain launcher 17. Compiling to Java 17 bytecode on JDK 21 does not replace runtime testing on Java 17.

## 14. Matrix Builds and Compatibility Testing

A matrix allows running the same source code across multiple JDKs. This is a good way to test compatibility and detect behavioral changes between releases early.

Example target matrix:

| Job | JDK | Goal |
|---|---:|---|
| Compatibility minimum | 17 | Confirm the project still supports the baseline |
| Primary build | 21 | Primary build/runtime version |
| Forward compatibility | 25 | Detect issues when upgrading the JDK |

It is not necessary to run the entire integration suite on every version. You can run unit tests on all versions and run the integration/performance suite on the primary version, depending on time and project policy.

If a pipeline needs to compile with JDK 21 but test at runtime on Java 17, you can split jobs:

- The build job installs compiler/toolchain 21.
- The runtime test job installs JDK 17.
- The same artifact is passed between jobs via pipeline artifacts.

Remember that jobs usually run on separate agents/containers. Artifacts passed between jobs are build output files; they do not carry over the JDK installed in the previous job.

## 15. JDK Caching and Dependency Caching

Two types of caches are often confused:

- **JDK cache:** stores the downloaded JDK so subsequent jobs do not have to re-download it.
- **Dependency cache:** stores the Maven repository or Gradle caches to avoid re-downloading libraries.

`setup-java` example:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '21'
    cache: maven
~~~

The action caches Maven dependencies and the wrapper; when dependency caching is enabled, JDK installation caching is also enabled by default unless overridden.

In GitLab, `cache:paths` for `.m2/repository` or Gradle caches is dependency caching. Docker image pulling/caching is a separate mechanism handled by the runner/registry.

### When Should a Cache Key Change?

Dependency cache keys should depend on dependency/wrapper management files such as `pom.xml`, `gradle.lockfile`, `gradle-wrapper.properties`, or the appropriate version catalog.

JDK cache identity should distinguish OS, architecture, vendor/distribution, package type, and version. Do not share a JDK cache across different architectures or vendors.

Caching is only a performance optimization. The pipeline must still build successfully on a cache miss or when the cache is cleared.

## 16. Security and Reproducibility

The JDK is a critical part of the build supply chain. A pipeline can be compromised if it downloads the wrong archive, uses an altered action, or pulls an untrusted container image.

Recommended practices:

1. Choose an organization-trusted distribution and download source.
2. Specify JDK version, vendor, OS, and architecture explicitly.
3. Verify checksums; verify signatures if required by policy.
4. Use official CI actions or actions that have been reviewed.
5. For GitHub Actions, pin actions to a full-length commit SHA per security policy; major tags are readable but can be moved.
6. For containers, pin digests when immutable images are needed.
7. Manage internal JDK archives through a controlled artifact repository or mirror.
8. Do not store private keys, tokens, or credentials in Dockerfiles, command lines, or build logs.
9. Update JDKs periodically to receive security fixes.
10. Restrict pipeline permissions, especially for pull requests from forks.

Do not disable checksum/signature verification just to make a pipeline get past a download error. Identify the root cause, metadata, and keys before changing verification policies.

## 17. Checking the JDK Across Operating Systems

### Linux

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java --version
javac --version
~~~

JDK paths are typically under `/usr/lib/jvm/...` or the CI provider's tool cache directory.

### macOS

~~~bash
/usr/libexec/java_home -V
echo "$JAVA_HOME"
java --version
javac --version
~~~

`/usr/libexec/java_home` can list JDKs recognized by macOS. With CI actions, use the `JAVA_HOME` variable provided by the action instead of guessing the installation path.

### Windows

~~~powershell
Write-Output $env:JAVA_HOME
where.exe java
where.exe javac
java --version
javac --version
~~~

If using a self-hosted Windows runner, check that `PATH` does not prioritize an older Java installation ahead of the newly installed JDK. Avoid modifying the system-wide `PATH` if only job-level configuration is needed.

## 18. Smoke Test Example Confirming the JDK Can Compile and Run

Create `CiJdkCheck.java`:

~~~java
public class CiJdkCheck {
    public static void main(String[] args) {
        if (Runtime.version().feature() < 17) {
            throw new IllegalStateException("Java 17 or newer is required");
        }

        System.out.println("JDK_READY");
    }
}
~~~

Compile with the installed JDK:

~~~bash
javac --release 17 -d out CiJdkCheck.java
~~~

Run:

~~~bash
java -cp out CiJdkCheck
~~~

Exact stdout:

~~~text
JDK_READY
~~~

The program confirms that the compiler can compile source code targeting release 17 and that the current runtime has feature version 17 or newer. `java --version` and `javac --version` should still be recorded in the CI logs so the exact actual versions are known.

If the smoke test passes but the project build fails, the cause may lie in Maven/Gradle, plugins, dependencies, source compatibility, or toolchain configuration.

## 19. Common Errors and Troubleshooting

### `java: command not found`

**Cause:** The JDK is not installed, `PATH` does not include the JDK's `bin` directory, or the step is running in a different container from the one where Java was installed.

**Resolution:** Verify the job image/runner; check `JAVA_HOME`; add `JAVA_HOME/bin` to `PATH`; check that the setup action/task ran before the build step.

### `javac: command not found`

**Cause:** Only a runtime image/JRE is present, the JDK package lacks a compiler, or `PATH` points to another runtime.

**Resolution:** Install a full JDK; check `JAVA_HOME/bin/javac`; choose an image with a JDK suffix instead of JRE; verify `javac --version`.

### `JAVA_HOME is not defined correctly`

**Cause:** The variable points to the `bin` directory, an executable file, or a non-existent directory.

**Resolution:** Set `JAVA_HOME` to the JDK root; confirm `JAVA_HOME/bin/java` and `JAVA_HOME/bin/javac` exist; use OS-appropriate path syntax.

### `java` and `javac` Have Different Versions

**Cause:** `PATH` contains multiple JDKs with the wrong priority order; `JAVA_HOME` and `PATH` do not point to the same installation.

**Resolution:** Print `command -v`/`where.exe`; invoke binaries in `JAVA_HOME/bin` directly; fix `PATH` or toolchain settings; re-run verification before the build.

### Maven Runs with a Different JDK Than the Compiler

**Cause:** Maven's runtime comes from `JAVA_HOME`, while the compiler plugin uses Maven Toolchains or a different compiler executable.

**Resolution:** Check `mvn --version`; inspect `~/.m2/toolchains.xml`; check the Maven Toolchains Plugin and compiler plugin; verify that version/vendor requirements match the toolchain entry.

### Gradle Runs with an Unexpected JDK

**Cause:** `JAVA_HOME`, Gradle daemon JVM criteria, or the project toolchain specify different versions.

**Resolution:** Check `./gradlew --version`; inspect Gradle daemon JVM criteria and Java toolchain settings; stop old daemons after changing the runtime if needed; verify the correct compiler/test launcher is selected.

### CI Installs the JDK Successfully, but Subsequent Steps Do Not See It

**Cause:** Variables exported in one shell step do not persist in a new step; a later job runs on a different agent; a new container does not contain the JDK.

**Resolution:** Use the CI provider's mechanism for passing environment variables; install/set up the JDK in each job; use the same image or managed tool installation; do not rely on the filesystem of a previous job.

### Hosted Runner Has the JDK on a Developer Machine, but CI Does Not

**Cause:** The runner image differs in OS/version, or the list of pre-installed tools has changed.

**Resolution:** Request the version using a setup action/task; print `java --version`; do not rely on the runner's default version.

### Container Has a JDK but Lacks Maven/Gradle

**Cause:** A JDK image only contains Java tools.

**Resolution:** Use Maven/Gradle Wrapper; choose a build image that includes the appropriate Maven/Gradle; or install the build tool at a pinned version.

### Architecture Error or `Exec format error`

**Cause:** Downloaded an ARM64 JDK on an x64 runner, or vice versa.

**Resolution:** Check the architecture of the runner/container; choose the right package; for multi-architecture Docker images, confirm the image manifest supports the target platform.

### TLS/Certificate Error When Downloading the JDK

**Cause:** Proxy, internal CA, certificate inspection, or incorrect truststore.

**Resolution:** Configure the proxy and CA per organizational policy; use an internal mirror; do not disable TLS verification as a default fix.

### JDK Archive Extracts, but Does Not Run

**Cause:** Corrupted archive, wrong checksum, unexpected directory layout, missing execute permissions, or package incompatible with OS/libc.

**Resolution:** Verify the checksum; inspect archive contents; set `JAVA_HOME` correctly; check execute permissions and architecture; use a package matching the runner.

### Pipeline Uses `latest` and Results Change

**Cause:** Aliases or image tags can point to newer releases over time.

**Resolution:** Pin the feature/patch version or image digest per reproducibility requirements; upgrade versions intentionally via pull requests; run a compatibility matrix.

### A Newer JDK Breaks an Older Build

**Cause:** Gradle/Maven wrapper, plugins, annotation processors, or dependencies are not yet compatible with the new JDK.

**Resolution:** Check the build tool/plugin compatibility matrix; separate the build-running JDK from the compiler toolchain when appropriate; upgrade plugins in a controlled manner; keep the verified CI version until migration is complete.

## 20. Standard Process for Adding a JDK to CI

1. Identify the Java release the project needs to support.
2. Choose an approved vendor/distribution and architecture.
3. Determine whether the runner is hosted, self-hosted, or container-based.
4. Choose an action/task, pre-installed tool, or container image.
5. Set the version and configure `JAVA_HOME`/`PATH`.
6. Run `java --version` and `javac --version`.
7. Run `mvn --version` or `./gradlew --version`.
8. Check compiler/test toolchains if the project uses multiple JDKs.
9. Run the build wrapper and test suite.
10. Cache dependencies/JDK after determining appropriate cache keys.
11. Pin actions/images/archives per reproducibility policy.
12. Save version logs in CI artifacts for traceability.

A good CI change should be easy to read: a reviewer looking at the YAML should immediately see the JDK vendor/version, installation source, build command, and verification steps.

## 21. Checklist Before Merging CI Configuration

### JDK Selection

- [ ] Target feature release is identified.
- [ ] Vendor/distribution is explicitly chosen.
- [ ] Correct OS and architecture are selected.
- [ ] Patch update and support policy is defined.
- [ ] Does not rely on an uncontrolled default runner version.

### Installation

- [ ] JDK is installed in the right job/container.
- [ ] Package includes `javac` if compilation is needed.
- [ ] `JAVA_HOME` points to the JDK root.
- [ ] `PATH` prioritizes the right JDK.
- [ ] Environment variables persist across all steps that need them.
- [ ] Checksum/signature is verified when downloading archives.

### Build

- [ ] `java --version` and `javac --version` are recorded in logs.
- [ ] Maven/Gradle runs on the expected JVM.
- [ ] Compile/test toolchains select the right JDK.
- [ ] Java release target is distinguished from the compiler JDK.
- [ ] Wrapper is committed and used.
- [ ] Tests/builds pass on real runners.

### Operations and Security

- [ ] Actions are reviewed and pinned per policy.
- [ ] Container image tags/digests are managed.
- [ ] Caches are not a mandatory dependency for a successful build.
- [ ] JDK security updates have a scheduled review.
- [ ] No secrets are written into YAML/logs/image layers.
- [ ] Self-hosted agents have an update and old-tool cleanup process.

## 22. Official References

- [actions/setup-java — GitHub](https://github.com/actions/setup-java) — installs Java distributions, selects versions, sets `JAVA_HOME`/`PATH`, caches, and supports multiple JDKs.
- [GitHub Actions: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use) — pinning actions by full-length commit SHA and controlling workflow dependencies.
- [GitLab CI/CD YAML syntax](https://docs.gitlab.com/ci/yaml/) — configuring `image`, `cache`, `variables`, and job scripts.
- [Run CI/CD jobs in Docker containers — GitLab](https://docs.gitlab.com/ci/docker/using_docker_images/) — how jobs use Docker images.
- [Eclipse Temurin Official Image](https://hub.docker.com/_/eclipse-temurin) — JDK images and supported architectures.
- [JavaToolInstaller@1 — Microsoft Learn](https://learn.microsoft.com/en-us/azure/devops/pipelines/tasks/reference/java-tool-installer-v1) — selecting JDKs from PreInstalled, LocalDirectory, or Azure Storage and setting `JAVA_HOME`.
- [Managing Tools — Jenkins](https://www.jenkins.io/doc/book/managing/tools/) — configuring pre-installed/auto-install JDKs and tool locations on agents.
- [Jenkins Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/) — Declarative Pipeline `tools` directive.
- [Toolchains for JVM projects — Gradle](https://docs.gradle.org/current/userguide/toolchains.html) — selecting compilers, launchers, and Javadoc tools by JDK version.
- [Guide to Using Toolchains — Maven](https://maven.apache.org/guides/mini/guide-using-toolchains) — selecting a separate JDK for the compiler and toolchain-aware plugins.
- [Archive Installation — Eclipse Adoptium](https://adoptium.net/installation/archives) — installing Temurin archives and verifying SHA-256 checksums.

Installing a JDK in CI is not just about making the `java` command run. The pipeline must select the right distribution/version, provide the compiler when needed, set `JAVA_HOME` and `PATH` consistently, and ensure Maven/Gradle use the right toolchain. Verify versions immediately after the setup step and keep the configuration reproducible so every runner builds the same project according to the chosen Java policy.
