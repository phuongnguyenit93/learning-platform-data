# Distinguishing Speedup Caches from Deliverable Artifacts in CI

## 1. Problem: Both Are Stored Files, But Not for the Same Purpose

A Java/Spring Boot pipeline typically needs to retain two categories of data:

- **Cache** stores reproducible data so subsequent builds do not have to download dependencies or recompute task outputs from scratch.
- **Artifact** stores a specific output produced during a single build run so another job, another workflow, or an operator receives that exact file.

For example: Maven downloads dependency JARs into `~/.m2/repository`. That is cache data to speed up builds. After building, the project produces `target/ci-artifact-demo-1.0.0.jar`. That is the deliverable to test, hand off to a Docker image build job, or upload to a Maven repository.

Treating a cache like an artifact can cause a deployment job to pick up a stale file matching a cache key, a file not produced by the just-completed build, or a file no longer matching the tested commit. Treating an artifact like a cache risks losing a releasable file when a cache expires, gets evicted, or misses.

This lesson belongs to **CI Automation** under **Spring Boot Build Tooling Packaging**. After this lesson, you will be able to:

1. Distinguish dependency caches, build caches, workspace outputs, CI workflow artifacts, and release repositories.
2. Understand the roles of `~/.m2/repository`, `~/.gradle/caches`, `target/`, and `build/`.
3. Choose cache keys tailored to OS, architecture, JDK, Maven/Gradle Wrapper, and dependency files.
4. Know when to use the Maven local repository cache, Gradle dependency cache, and Gradle task-output build cache.
5. Transfer an executable JAR between GitHub Actions jobs using `upload-artifact`/`download-artifact`.
6. Verify checksums after downloading an artifact to ensure the handed-off file was not unintentionally altered.
7. Prevent cache poisoning, storing secrets in caches, and using caches as release sources.
8. Design a pipeline following **build → test → upload artifact → download → verify → deploy/publish exact bytes**.
9. Distinguish retention-bounded workflow artifacts from Maven repositories/OCI registries used for long-term product distribution.

**Hands-on example:** Java `17`, Spring Boot `3.5.16`, Maven Wrapper, GitHub Actions, `actions/setup-java@v6`, `actions/upload-artifact@v7`, and `actions/download-artifact@v8`. The illustrative workflow targets GitHub.com hosted runners; GitHub Enterprise Server users must verify compatible action versions for their server.

## 2. High-Level Model: Caches and Artifacts Answer Different Questions

| Question | Appropriate Mechanism | Example |
| --- | --- | --- |
| How do we avoid re-downloading dependencies? | Dependency cache | `~/.m2/repository`, `~/.gradle/caches/modules-2` |
| How do we avoid re-running an expensive task? | Build/task-output cache | Gradle build cache |
| How does the test job receive the exact JAR just built? | CI workflow artifact | Upload/download `application.jar` |
| How do we store releases for consumers to resolve by version? | Artifact repository | Maven repository, package registry |
| How do we deploy the exact container image verified by QA? | OCI registry + digest | Image digest in registry |
| How do we inspect a job's failure after the job ends? | CI artifact/log retention | Test report, coverage, build log |

A single pipeline can use both caches and artifacts:

~~~text
Source code + pom.xml + Maven Wrapper
                 |
                 v
       RESTORE DEPENDENCY CACHE
       ~/.m2/repository
                 |
                 v
           mvn clean verify
                 |
                 v
       target/application.jar
                 |
             TEST PASS
                 |
                 v
       CREATE CHECKSUM (SHA-256)
                 |
                 v
         UPLOAD CI ARTIFACT
          application.jar
             SHA256SUMS
                 |
          job A completes
                 |
                 v
        DOWNLOAD IN JOB B
                 |
                 v
       VERIFY CHECKSUM + RUN
                 |
                 v
       DEPLOY/PUBLISH EXACT FILE
~~~

**A cache miss should only make a build slower.** If wiping all caches prevents a build from running, the pipeline is treating cache state as a mandatory data source. A sound pipeline can re-download dependencies or regenerate task outputs when the cache is empty.

**Artifact handoff must have explicit identity.** The receiving job must know which workflow run/build produced the artifact, which filename it expects, what checksum it should match, and which tests it passed.

## 3. Five Data Categories to Distinguish

### 3.1. Dependency Cache

Stores downloaded dependencies/plugins or metadata supporting dependency resolution. Its goal is reducing network traffic and wait time.

- Maven: typically `~/.m2/repository`.
- Gradle: typically `~/.gradle/caches`, containing module artifacts and resolution metadata.
- Maven/Gradle Wrapper: maintains a separate distribution cache to avoid re-downloading the build tool.

The dependency cache is not a directory of accepted deliverables. Its contents can be deleted and re-fetched from repositories according to coordinates, metadata, and integrity policies.

### 3.2. Build Cache / Task-Output Cache

Stores outputs of executed tasks so another build can reuse them if corresponding inputs remain unchanged.

For example, Gradle can cache outputs of compilation, resource processing, or artifact transforms. The build cache relies on input/output declarations and task cacheability; custom tasks must declare inputs and outputs accurately for safe reuse.

A task with undeclared inputs can return stale outputs even when underlying data changed. Therefore, a task-output cache must be verified as a build optimization, never treated as a release repository.

### 3.3. Workspace Output

Files generated inside a job's workspace:

- Maven: `target/classes`, `target/test-classes`, `target/*.jar`, `target/surefire-reports`.
- Gradle: `build/classes`, `build/resources`, `build/libs`, `build/reports`.

A CI job's workspace is typically destroyed when the job finishes. Another job has its own runner and workspace; it cannot implicitly read `target/application.jar` from a prior job. To pass files across jobs, use workflow artifacts or an intentional storage mechanism.

### 3.4. CI Workflow Artifact

A file or set of files produced by a workflow and uploaded to:

- Transfer build outputs between jobs.
- Preserve binaries, test reports, or logs for inspection after the job finishes.
- Supply files to testing, image packaging, or deployment steps.
- Retain evidence of a CI run according to a retention policy.

An artifact is bound to a workflow run and its name/ID. It is an **output handoff mechanism**, not a drop-in replacement for a Maven repository or long-term product registry.

### 3.5. Release Artifact in a Repository

A deliverable published with a stable identity and governed by organizational policy:

- Maven: GAV + extension + classifier in a Maven repository.
- OCI: image manifest/index digest in a container registry.
- Generic binary: artifact repository or release storage.

Release artifacts require versioning, checksums, publish permissions, retention, immutability, and promotion/rollback workflows. A workflow artifact can be an intermediate step before release, yet uploading it does not automatically make it a Maven release.

## 4. Maven: The Local Repository Is Both a Cache and a Local Install Store

The default Maven local repository typically lives at:

~~~text
Linux/macOS: ~/.m2/repository
Windows:     %USERPROFILE%\.m2\repository
~~~

It serves two roles:

1. Stores dependency and plugin artifacts downloaded from remote repositories.
2. Stores project artifacts installed locally via `mvn install`.

Thus `~/.m2/repository` is a **mixed area**, not solely a download cache. Maven can reuse JARs/POMs already present there instead of fetching from remote repositories. The local repository path can be changed in `settings.xml` via `<localRepository>`.

### 4.1. Maven Commands Do Not Share the Same Goal

| Command | Effect | Is It Artifact Handoff Between CI Jobs? |
| --- | --- | --- |
| `mvn dependency:go-offline` | Pre-downloads many required dependencies and plugins | No |
| `mvn -o verify` | Runs offline using only data already in the local repo | No |
| `mvn clean verify` | Performs a clean build and runs lifecycle through `verify` | Not yet; outputs stay in the current job's workspace |
| `mvn install` | Installs main/attached artifacts into the local Maven repository | No; affects only that environment's local repository |
| `mvn deploy` | Publishes project artifacts to a configured remote repository | This is publishing, not CI caching |

Running `mvn install` in job A does not make the JAR available to job B if job B runs on a different runner without a shared local repository. The proper way to transfer built products is uploading the JAR as a CI artifact or publishing it to a shared repository.

### 4.2. Caching Maven in GitHub Actions

`actions/setup-java` supports Maven caching:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
~~~

With this configuration, the action manages the Maven dependency cache, typically `~/.m2/repository`. Depending on action configuration, it can also cache the Maven Wrapper distribution and the JDK when dependency caching is enabled.

In multi-module projects, you can specify the files used to compute the cache key:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
    cache-dependency-path: |
      **/pom.xml
      .mvn/wrapper/maven-wrapper.properties
      .mvn/extensions.xml
~~~

`setup-java` constructs the cache key from OS, architecture, package manager, and hashes of the dependency/build input files per the action's logic. When a POM, Maven Wrapper properties, or extension file changes, the key changes and a fresh cache can be created.

**Do not add `target/` to the dependency cache path.** JAR files in `target/` are build outputs of the run; they must be verified and transferred via workflow artifacts.

### 4.3. Maven Cache Does Not Replace the Source Repository

The Maven local repository is not an authoritative release store:

- Caches can be deleted or expire.
- Remote `SNAPSHOT`s can be updated and metadata can change.
- Repository origins, mirrors, checksum policies, and dependency coordinates still affect resolution.
- An artifact installed locally via `mvn install` might not exist in any remote repository.
- Under identical coordinates, a repository could return different bytes if it permits republishing.

Do not use caches to replace Maven Central or an internal repository manager, and never manually copy files out of the local repository as a publishing workflow. Use Maven repository APIs/goals and managed remote repositories.

### 4.4. Be Careful with settings.xml and Credentials

Maven `settings.xml` often holds server credentials, proxy credentials, mirror settings, or a local repository path. The user settings file lives outside the project at `~/.m2/settings.xml` by default.

Cache only the dependency repository directory itself; **never cache or upload the entire user home directory**. Never place a `settings.xml` containing passwords or tokens into cache paths, CI artifacts, or build logs. Supply credentials via a secret store and generate settings securely for the job.

## 5. Gradle: Dependency Cache vs. Build Cache

Gradle has multiple caches; avoid calling all of them "the Gradle cache" and assuming they serve the same purpose.

### 5.1. Dependency Cache

Gradle stores module artifacts, POM/Ivy metadata, and dependency resolution results in Gradle User Home, usually under:

~~~text
~/.gradle/caches
~/.gradle/wrapper
~~~

The dependency cache avoids re-downloading dependencies and metadata. Gradle tracks repository origins and stores artifacts by checksum; metadata caches also record which repository supplied a module. This keeps the resolver from blindly treating identically named coordinates across different repositories as the same source.

Useful commands:

~~~bash
./gradlew dependencies
./gradlew --offline build
./gradlew --refresh-dependencies build
~~~

- `dependencies` prints the dependency graph for the relevant configurations.
- `--offline` instructs Gradle to rely solely on cached data; missing required artifacts fail the build.
- `--refresh-dependencies` asks Gradle to re-validate dependency resolution against repositories; it does not blindly re-download every file.

Caching does not make dynamic versions or changing/`SNAPSHOT` dependencies immutable. When a dependency is marked changing, Gradle applies separate refresh and cache TTL rules. Releases should pin versions and govern dependency verification and locking by policy.

### 5.2. Gradle Build Cache

The Gradle build cache stores **task outputs** and artifact-transform outputs for reuse when corresponding inputs match. It differs from the dependency cache:

| Cache | Data | Examples |
| --- | --- | --- |
| Dependency cache | Libraries/plugins downloaded from repositories and resolution metadata | `spring-core.jar`, plugin modules |
| Build cache | Outputs produced by tasks | Compiled classes, processed resources, task outputs |
| Wrapper cache | Downloaded Gradle distribution | Gradle version declared in the Wrapper |

You can enable the build cache for a single run:

~~~bash
./gradlew clean build --build-cache
~~~

Or enable it in `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

Gradle has a local build cache and supports configuring a remote build cache. When using a remote cache, enforce read/write access controls; never allow untrusted workflows to push outputs into a cache trusted by release builds.

**The build cache is not a release JAR store.** After Gradle creates `build/libs/app.jar`, upload that exact file as a CI artifact or publish it to a Maven/OCI repository. A task-output cache hit only indicates Gradle could reuse a task result under a cache key; it does not prove an artifact was durably stored or approved for release.

### 5.3. Gradle Tasks Must Declare Inputs and Outputs Accurately

Cacheable tasks must declare every input and output that affects their results. If a task reads environment files, environment variables, tool versions, or external files without declaring them as inputs, Gradle can reuse an outdated output.

When writing custom tasks:

- Declare source files, configurations, and tool versions as appropriate inputs.
- Declare output files/directories accurately.
- Avoid implicit dependencies on current time, random values, hostnames, or undeclared external files.
- Avoid writing multiple unmanaged outputs into a single cacheable directory.
- Enable caching only for tasks with deterministic behavior that is safe to reuse.

Caching is an optimization that demands correctness; it cannot repair a task with a broken input/output contract.

### 5.4. Caching Gradle in GitHub Actions

Using `setup-java`:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle
    cache-dependency-path: |
      **/*.gradle*
      **/gradle.properties
      **/gradle-wrapper.properties
      gradle/libs.versions.toml
~~~

Or use `gradle/actions/setup-gradle` when more advanced Gradle cache management is needed. Consult the documentation for your action and Gradle versions; never cache all of `build/` as though it were a dependency repository.

## 6. Cache Keys: Which Inputs Yield the Right Cache?

A cache key is a label used to look up a cache entry. An overly broad key can restore incompatible data; an overly narrow key triggers excessive misses and wastes storage.

A dependency cache key typically accounts for:

- Runner operating system.
- CPU architecture.
- Package manager and version/Wrapper.
- JDK/toolchain when cached data depends on the toolchain.
- POMs or Gradle build files.
- Lockfiles, version catalogs, and dependency declarations.
- Maven/Gradle extensions or properties affecting resolution.
- Profiles and modules actually built.

Conceptual examples:

~~~text
maven-Linux-X64-JDK17-wrapperHash-pomHash
gradle-Linux-X64-JDK17-wrapperHash-lockfileHash
~~~

You do not necessarily write keys manually when `setup-java` manages them; this model explains what triggers cache rotation.

### 6.1. Exact Keys and restore-keys

GitHub Actions caching can:

1. Search for an exact key match.
2. Search for prefix/partial matches.
3. Try `restore-keys` in order.
4. On no match, treat it as a cache miss; the job runs and may save a new cache upon successful completion.

Example using `actions/cache`:

~~~yaml
- uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: maven-${{ runner.os }}-${{ hashFiles('**/pom.xml') }}
    restore-keys: |
      maven-${{ runner.os }}-
~~~

This is a manual example illustrating key matching; when `setup-java` already uses `cache: maven`, you usually do not add a second cache action for the same directory. Avoid two actions managing one path, as they can conflict or save unexpected contents.

`restore-keys` can fetch the newest close match. For a dependency cache, Maven/Gradle still performs resolution against current coordinates, metadata, and repository policies. Never use a broad restore prefix to restore `target/`/`build/` and treat those outputs as the current build.

### 6.2. Cache Misses Are Normal

Caches can miss when:

- POMs or lockfiles change.
- JDK, OS, or architecture changes.
- A cache is evicted or expires past retention.
- A branch does not yet have its own cache.
- The key or cache version differs.
- The runner operates in a different cache scope.

On a miss, the pipeline should download dependencies and run the build normally. Never make a cache hit a prerequisite for deployment. Never skip tests because "we used the cache from the previous build."

## 7. GitHub Actions Cache Security and Cache Poisoning

Caches are not trusted stores by default. GitHub documentation warns that cache contents are not signed or verified; workflows that can read a cache can extract its contents, and restored cache files can influence executed build code.

### 7.1. Never Store Secrets

Never cache:

- `settings.xml` containing Maven credentials.
- Access tokens, passwords, private keys, or signing keys.
- `.env` files containing secrets.
- Credential files or private repository configurations.
- Workspaces containing sensitive files readable by other workflows.

Cache paths should include only the necessary dependency/build caches. Supply secrets through the CI secret store and inject them only into jobs that require them.

### 7.2. Restricting Who Can Write Caches

Cache poisoning occurs when an untrusted workflow writes cache contents that a higher-privilege workflow later restores and uses. For example, a PR workflow writes a cache containing a trojanized executable; a trusted release workflow restores that cache and runs it.

Countermeasures:

- Allow only trusted branches/triggers to write caches consumed by releases.
- Give PR/fork workflows read-only cache access where possible.
- Never put secrets in a cache even if the cache key looks hard to guess.
- Never execute binaries fetched from a cache without controlling their source and integrity.
- Keep cache keys isolated by OS, architecture, toolchain, and dependency inputs.
- On a cache miss, re-run resolution/builds rather than grabbing unverified output files.
- For critical builds, verify dependency integrity via checksums/signatures and use trusted repositories.

`actions/setup-java` supports `cache-read-only`; for example, allowing only `main` to write caches:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
    cache-read-only: ${{ github.ref != 'refs/heads/main' }}
~~~

This expression makes all refs other than `main` read-only for the cache; adjust it to match your organization's branch policy. GitHub enforces branch/trigger cache access boundaries, yet custom policies and workflow triggers still require review.

## 8. CI Workflow Artifacts: Transferring the Exact File Between Jobs

Each GitHub Actions job typically runs on its own runner and workspace. If the `build` job produces:

~~~text
target/ci-artifact-demo-1.0.0.jar
~~~

the `package` job does not automatically have that file. The handoff flow is:

1. Build and test the JAR in job A.
2. Generate a checksum for that exact JAR.
3. Upload the JAR and checksum as a workflow artifact.
4. Job B downloads the artifact by its exact name/ID.
5. Verify the checksum.
6. Use the exact downloaded file for smoke testing, image building, or deployment.

### 8.1. upload-artifact and download-artifact

GitHub provides:

- `actions/upload-artifact`: uploads files or directories produced in a workflow.
- `actions/download-artifact`: downloads workflow artifacts within the same workflow run, or from another run/repository given an authorized token.

Artifacts store build binaries, test results, logs, and coverage, and share outputs across jobs. Since v4, workflow artifacts are immutable once created; each upload should use a unique name. Do not design multiple jobs to mutate one artifact name like a shared folder.

The example below uses current major versions per documentation: upload `@v7` and download `@v8`. Before adopting them, check compatibility with GitHub Enterprise Server and your runners; the download action documentation notes v4+ support limitations on GHES. For high-security pipelines, pin actions by reviewed full commit SHA rather than major tags alone.

### 8.2. Artifact Retention

GitHub workflow artifacts follow a retention policy:

- A common default is `90 days`, depending on repository/organization settings.
- A shorter `retention-days` can be set for handoff or diagnostic files.
- Expired artifacts can no longer be downloaded.
- Workflow artifacts suit handoffs and investigation within the retention window; long-term releases need a repository or registry with dedicated retention policies.

For example, set `retention-days: 14` for intermediate files. Never use workflow artifacts as an indefinite release archive.

### 8.3. Artifact Names Must Identify the Exact Run

Artifact names should include details distinguishing runs and matrix jobs, such as:

~~~text
executable-jar-<git-sha>-<run-id>-<run-attempt>
test-report-linux-jdk17
test-report-windows-jdk17
~~~

When a matrix runs multiple OS/JDK combinations, do not have all jobs upload to the same name expecting them to auto-merge. Assign distinct names or use an intentional artifact merge step. Workflow reruns should also produce distinct artifact identities to avoid colliding with existing artifacts.

## 9. Complete Example: Maven Build Cache + Transferring an Executable JAR Between Two Jobs

Let's create a simple Spring Boot CLI application. The build job uses the Maven cache to reduce dependency downloads; once the JAR passes the build and smoke test, it is uploaded as a workflow artifact. A second job downloads and executes **the exact received file** without rebuilding from source.

### 9.1. Project Structure

~~~text
ci-artifact-demo/
  pom.xml
  .mvn/
    wrapper/
      maven-wrapper.properties
  mvnw
  src/
    main/
      java/
        demo/
          CiArtifactDemoApplication.java
~~~

The example assumes Maven Wrapper has been generated and committed with the project. If the repository lacks a Wrapper, add one via the Maven Wrapper setup or use a CI-managed Maven version.

### 9.2. Complete pom.xml

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.ci</groupId>
    <artifactId>ci-artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

With the Spring Boot parent, the plugin version is managed and the `repackage` goal is bound to the `package` lifecycle. Expected executable JAR:

~~~text
target/ci-artifact-demo-1.0.0.jar
~~~

If the project does not use the Boot parent, configure the plugin version and execution explicitly; never assume an arbitrary Maven POM produces an executable Spring Boot JAR.

### 9.3. CiArtifactDemoApplication.java

Create `src/main/java/demo/CiArtifactDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CiArtifactDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CiArtifactDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args ->
                System.out.println("ci-artifact-demo:ok");
    }
}
~~~

The application has no web server; once the Spring context initializes and `CommandLineRunner` finishes, the process exits when `main` returns. This lets the workflow verify the executable JAR without keeping a background HTTP server alive.

Local build:

~~~bash
./mvnw -B -ntp clean verify
~~~

Run the JAR:

~~~bash
java -jar target/ci-artifact-demo-1.0.0.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Exact line printed by application code:

~~~text
ci-artifact-demo:ok
~~~

In the workflow, we compare stdout against this exact string to validate the packaged archive.

## 10. Generating SHA-256 Before Upload

After `mvnw clean verify` and the packaged JAR smoke test pass, create a `handoff` directory:

~~~bash
set -eu

mkdir -p handoff
cp target/ci-artifact-demo-1.0.0.jar handoff/application.jar

(
  cd handoff
  sha256sum application.jar > SHA256SUMS
)
~~~

Inside `handoff/`:

~~~text
application.jar
SHA256SUMS
~~~

`SHA256SUMS` has the format:

~~~text
<sha256-hex>  application.jar
~~~

`<sha256-hex>` is an illustrative placeholder; the real digest is computed by `sha256sum` from the file's bytes. Never record fabricated digests in release records.

In the receiving job, run:

~~~bash
cd handoff
sha256sum --check SHA256SUMS
~~~

If the file matches, stdout shows:

~~~text
application.jar: OK
~~~

If bytes changed or the file is missing, the command exits non-zero. The job must halt before using the file.

**What does a checksum sidecar protect against?** It detects transfer corruption, file substitution, or picking the wrong file when the checksum is preserved independently and compared properly. If an attacker can replace both the JAR and `SHA256SUMS`, the sidecar alone does not prove build authenticity; protect workflows, artifact permissions, and provenance/attestation/signatures according to the required assurance level.

## 11. Complete Two-Job GitHub Actions Workflow

Create `.github/workflows/build-transfer.yml`:

~~~yaml
name: Build and transfer executable JAR

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v7

      - name: Set up Java and restore Maven dependency cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml
          cache-read-only: ${{ github.ref != 'refs/heads/main' }}

      - name: Build project and run Maven verification
        run: ./mvnw -B -ntp clean verify

      - name: Smoke-test the packaged JAR and prepare handoff
        shell: bash
        run: |
          set -eu

          jar=target/ci-artifact-demo-1.0.0.jar
          test -f "$jar"

          output="$(java -jar "$jar" \
            --spring.main.banner-mode=off \
            --logging.level.root=OFF)"

          test "$output" = "ci-artifact-demo:ok"

          mkdir -p handoff
          cp "$jar" handoff/application.jar
          (
            cd handoff
            sha256sum application.jar > SHA256SUMS
          )

      - name: Upload the verified executable JAR
        uses: actions/upload-artifact@v7
        with:
          name: executable-jar-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: handoff/
          if-no-files-found: error
          retention-days: 14

  consume:
    needs: build
    runs-on: ubuntu-latest

    steps:
      - name: Set up Java runtime for the downloaded JAR
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Download the artifact from the build job
        uses: actions/download-artifact@v8
        with:
          name: executable-jar-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: handoff
          digest-mismatch: error

      - name: Verify checksum and execute the transferred JAR
        shell: bash
        run: |
          set -eu
          cd handoff

          sha256sum --check SHA256SUMS

          output="$(java -jar application.jar \
            --spring.main.banner-mode=off \
            --logging.level.root=OFF)"

          test "$output" = "ci-artifact-demo:ok"

          printf '%s\n' 'artifact.transfer=PASS'
          printf '%s\n' 'artifact.run=PASS'
~~~

### 11.1. What Happens in the build Job?

- `actions/setup-java@v6` installs Java 17 and restores the Maven dependency cache.
- `cache: maven` speeds up dependency downloads; the cache never contains `handoff/application.jar`.
- `./mvnw clean verify` builds the source and produces the executable JAR.
- The workflow runs **the packaged JAR itself** and checks stdout.
- `sha256sum` writes the checksum of the smoke-tested file.
- `upload-artifact@v7` uploads the JAR and sidecar as an artifact named with commit, run, and attempt.

### 11.2. What Happens in the consume Job?

- `needs: build` ensures the job runs only after `build` succeeds.
- The second runner installs JRE/JDK 17 to execute the downloaded file.
- `download-artifact@v8` downloads the artifact by its exact generated name.
- `digest-mismatch: error` instructs the action to fail if the downloaded artifact digest mismatches the server-provided value.
- `sha256sum --check` verifies the JAR bytes after extracting the artifact.
- `java -jar` executes **the downloaded file** without rebuilding from source.
- The final two lines print only if both checksum verification and the runtime smoke test pass.

With the example workflow, the final output printed by the verify step is:

~~~text
application.jar: OK
artifact.transfer=PASS
artifact.run=PASS
~~~

Maven build and upload steps produce their own logs. If either the checksum or application output mismatches, `set -eu`/`test` fails the step and the workflow cannot mark the `consume` job successful.

### 11.3. Why Does the Artifact Name Include Run ID and Run Attempt?

A commit may be re-run multiple times. Using only the commit in the name could collide with an artifact already created in the same workflow run. Appending `github.run_id` and `github.run_attempt` separates runs and prevents multiple jobs from accidentally uploading the same artifact name.

For matrix builds, also include `matrix.os`, `matrix.java`, or a classifier in the name to distinguish outputs by platform/JDK. Never merge identically named files from multiple jobs without defining explicit selection/merge rules.

## 12. Workflow Artifacts Are Not a Maven Release Repository

Workflow artifacts are suited for preserving and transferring files within a workflow run. However, an application or library that consumers resolve by Maven coordinates must be published to a Maven repository.

| Criterion | GitHub Workflow Artifact | Maven Repository |
| --- | --- | --- |
| Identifier | Workflow run + artifact name/ID | GAV + extension + classifier |
| Purpose | Job handoff, test outputs, build outputs, logs | Dependency resolution and Maven artifact distribution |
| Retention | Governed by GitHub Actions retention policy | Governed by repository manager retention/immutability policy |
| Consumer | Workflows/jobs or users with repo permissions | Maven/Gradle consumers and repository-aware tools |
| SNAPSHOT/release metadata | Not Maven metadata | Maintains repository metadata and snapshot/release policies |
| Publish command | `upload-artifact` | `mvn deploy` or equivalent publisher |
| Checksum | Artifact digest and/or sidecar | Repository checksums/signatures per policy |

`mvn install` only puts the artifact into the local Maven repository; `mvn deploy` publishes the artifact to a configured remote repository. Never upload the entire `~/.m2/repository` as a workflow artifact and treat it as a public Maven repository.

For Maven deliverables, remote repositories require release immutability, authentication, access control, snapshot policies, and retention. Workflow artifacts eventually expire, so do not use them for long-term release storage unless your organization operates a dedicated archival policy meeting all requirements.

## 13. OCI Images Also Need Distinct Artifact Identity

If a downstream job uses the JAR to build a Docker image, transfer the exact JAR via workflow artifact and then:

1. Download the JAR and `SHA256SUMS`.
2. Run `sha256sum --check`.
3. Build the Docker image using a Dockerfile that only `COPY`s the verified JAR.
4. Extract the JAR from the image and compare its checksum against the downloaded file.
5. Smoke-test the container.
6. Push the image and record the registry digest.

Do not confuse these three identifiers:

~~~text
Git commit SHA     = source revision
JAR SHA-256       = executable JAR bytes
OCI image digest  = image manifest/index
~~~

Identical Git commits do not guarantee identical JAR bytes; identical JAR bytes do not guarantee identical OCI image digests because base images, OS layers, image config, compression, and platforms can differ.

Never cache a Docker release image and treat a cached tag as the deployment artifact. Build layer caches can accelerate Docker builds, yet published images must be identified by tag/digest and pass all image gates.

## 14. Caching Build Outputs vs. Caching Dependencies: When to Use Which?

### 14.1. Maven

Good candidates to cache:

- `~/.m2/repository` for dependencies and plugins.
- Maven Wrapper distribution if the workflow would otherwise re-download it every run.
- CI-action-supported caches keyed cleanly on POM, Wrapper, OS, and architecture.

Do not cache by default:

- `target/` containing stale compile/package outputs.
- QA-verified JAR files lacking artifact identity.
- `~/.m2/settings.xml` or the entire user home.
- Logs or reports that could contain secrets.

If a project uses the Maven build-cache extension or plugin output caching, read its documentation and validate cache correctness independently; that is not default local-repository behavior.

### 14.2. Gradle

Keep separated:

- Dependency cache: downloaded module artifacts and metadata.
- Wrapper cache: Gradle distribution.
- Build cache: task outputs with accurate input/output declarations.
- Workflow artifact: verified `build/libs/*.jar` handed off between jobs.

You can enable the Gradle build cache while still uploading the executable JAR separately. Never treat a cache hit as evidence that the JAR was released or transferred to another job.

### 14.3. Incremental Workspace Outputs

Some reused CI runners retain stale workspace files. `mvn clean` or `./gradlew clean` clears stale outputs before building. However, `clean` does not replace artifact transfer, and restoring caches into `target/`/`build/` can introduce stale outputs if plugins or tasks mishandle incremental state.

To pass built deliverables, use an explicit artifact file. To speed up tasks, use build-tool-supported caching mechanisms. Both patterns can coexist as long as their boundaries stay distinct.

## 15. GitHub Actions Caches and Artifacts: Practical Limits

### 15.1. Caches Are Not Modified in Place Under an Existing Key

GitHub Actions caches store entries by key. Once an exact key exists, its entry is not modified like a shared directory; a new key is required to create a new entry. When a job uses `restore-keys`, it may receive the closest partial match.

Therefore, never use a fixed cache key like `production-latest` to overwrite a release JAR repeatedly. That is a misuse of caching.

### 15.2. Workflow Artifacts Are Immutable

Starting with `upload-artifact@v4`, created artifacts are immutable. Subsequent uploads cannot arbitrarily append to the same artifact as older versions allowed. When a new artifact is needed, create a new artifact with a distinct name/ID; overwriting (if enabled) generates a new ID and replaces the prior artifact rather than mutating bytes in place.

In the example workflow, a single build job uploads a single artifact, and the consume job only downloads it. That is the simplest way to prevent collisions.

### 15.3. File Permissions in Artifact Archives

ZIP-based artifact uploads may not preserve all original POSIX permissions; files are typically restored with the action's default permissions. For JARs, this is harmless because the file is invoked via `java -jar` and needs no executable bit. If transferring shell scripts or binaries that need execute permissions, pack them into a `tar` before uploading and unpack after downloading, or choose an upload strategy matching your action version.

### 15.4. Retention and Quotas

Artifacts expire and storage is subject to quotas. Short retention fits handoff and diagnostic files; release binaries belong in long-term managed repositories or registries. Never design production rollbacks around a workflow artifact that could expire past its retention window.

## 16. Choosing a Strategy by Scenario

| Scenario | Recommended Mechanism | Reason |
| --- | --- | --- |
| Multiple builds share Maven dependencies | Cache `~/.m2/repository` | Avoids repeatedly downloading dependencies/plugins |
| Gradle build has expensive compile/resource tasks | Dependency cache + Gradle build cache | Reuses downloads and task outputs via two distinct mechanisms |
| Integration test job needs JAR from build job | Workflow artifact | Transfers the exact output file across isolated runners |
| Docker job needs smoke-tested JAR | Workflow artifact + SHA-256 | Guarantees Docker build receives the exact verified bytes |
| Multiple developers consume an internal library | Maven remote repository | Resolves by GAV/version/classifier |
| Production requires an immutable container image | OCI registry digest | Deploys the exact published manifest/index |
| Debugging failed tests after runner exits | Workflow artifact logs/reports | Retains evidence per retention policy |
| Release requires rollback months later | Release repository/registry with retention | Short-lived workflow artifacts are insufficient |
| Running offline builds on a fresh machine | Seeded, verified dependency cache/repository | Missing cached dependencies will fail offline builds |
| Untrusted PR needs `main`'s cache | Restore-only / read-only cache | Reduces cache poisoning risk |

## 17. Common Errors and How to Handle Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Job B reports `target/app.jar` not found | Each job has an isolated workspace | Upload artifact in job A and download in job B |
| Ran `mvn install`, yet another runner lacks the artifact | `install` writes only to runner A's local repository | Use workflow artifacts or a remote Maven repository |
| Cache miss breaks the build | Pipeline treats cache as a mandatory source | Allow downloading/rebuilding from remote repositories |
| Build picks up stale JAR from cache | Cache output path/key too broad or wrong restore fallback | Never cache release JARs; upload artifacts tied to run identity |
| POM changed yet cache stays stale | Cache key does not hash all dependency inputs | Add POM, lockfile, Wrapper, and extension paths |
| Gradle dependency cache hits, yet tasks still run | Dependency cache is not the task-output build cache | Configure build cache if tasks are cacheable |
| Gradle build cache returns wrong outputs | Task omits input/output declarations or is non-deterministic | Fix task contract and verify cacheability |
| `--offline` Maven/Gradle fails | Cache lacks dependencies, plugins, or metadata | Drop offline mode or seed the cache/repository completely |
| Workflow artifact download not found | Artifact/run name mismatch, upload failed, or expired retention | Check upload summary, exact name/ID, and run |
| Duplicate artifact upload name | Multiple jobs/matrix entries/reruns use the same name | Add run ID, attempt, OS, and JDK to the name |
| SHA-256 mismatch after download | File altered, wrong file, or wrong manifest | Halt deploy; inspect source and checksum |
| JAR checksum passes, yet app fails at runtime | Checksum checks bytes, not runtime correctness | Run packaged-JAR and container smoke tests |
| Cache contains credentials | Cache path too broad or caches user home | Delete exposed cache, rotate credentials, narrow path |
| PR writes cache trusted by release build | Cache poisoning or overly broad write permissions | Read-only cache for untrusted workflows; trusted cache writers |
| Workflow artifact expired | Retention too short for release/rollback | Publish to long-term Maven repository or OCI registry |
| CI build passes, yet release artifact differs | Publish job rebuilt instead of reusing tested artifact | Download exact artifact, verify checksum, never rebuild |
| Uploaded shell script loses executable bit | ZIP artifacts do not preserve POSIX permissions | Tar file before upload or `chmod` after download |
| Multi-module uses incomplete cache key | Hashed only root POM, omitting child module inputs | Use `cache-dependency-path` covering all modules |
| SNAPSHOT dependency changed, yet old cache persists | Snapshot update policy and metadata caching | Use release versions for releases; refresh intentionally |

## 18. Pipeline Design Checklist

### Cache

- [ ] Caches contain only reproducible dependency/tool/build cache data.
- [ ] Keys include OS/architecture and appropriate dependency/build inputs.
- [ ] Maven/Gradle Wrapper and toolchains are managed.
- [ ] `target/`/`build/` are not cached as deliverable products without a proper task-cache strategy.
- [ ] `settings.xml`, secrets, tokens, and private keys are never cached.
- [ ] A cache miss still allows builds to download dependencies and run completely.
- [ ] PRs/forks have read-only cache access when workflows are untrusted.
- [ ] Caches are treated strictly as optimizations; tests are never skipped on a cache hit.

### Artifact Transfer

- [ ] The job produces artifacts after build and tests succeed.
- [ ] The exact JAR/WAR/image or test report to transfer is explicitly selected.
- [ ] Artifact names include commit/run/attempt/matrix details to prevent collisions.
- [ ] Upload action fails if no files exist.
- [ ] Uploads include appropriate checksums/provenance.
- [ ] Receiving jobs download the exact artifact ID/name.
- [ ] Checksums are verified after downloading.
- [ ] Downloaded files are smoke-tested rather than rebuilt from source.
- [ ] Retention covers debugging and handoff needs.

### Release

- [ ] Release JARs/WARs are published to a Maven repository with clear policies.
- [ ] OCI images are published to a registry and digests are recorded.
- [ ] Workflow caches are never used as a release source.
- [ ] Short-lived workflow artifacts are never used as long-term release storage.
- [ ] The exact bytes that passed all gates are published.
- [ ] Git commit, artifact checksum, repository coordinates/image digest, and CI run ID are recorded.

## 19. Self-Check Questions

**A. Does a Maven cache hit prove the current job built the exact JAR needed for release?**

No. A cache hit only shows the cache key matched and cached dependencies were restored. The JAR must still be built/verified in the job and uploaded as a separate artifact.

**B. Why shouldn't you cache `target/ci-artifact-demo-1.0.0.jar` and have a deploy job read it back?**

Caches have key-matching/restore policies and separate lifecycles; they are not a handoff protocol guaranteeing a job receives the exact output of the current run. Use workflow artifacts, artifact IDs, and checksums.

**C. Does `mvn install` transfer a JAR between two GitHub-hosted runners?**

No. It installs into the current runner's local Maven repository. A job on another runner needs artifact upload/download or a remote repository.

**D. Are the Gradle dependency cache and Gradle build cache the same thing?**

No. The dependency cache holds downloaded modules and metadata; the build cache holds reusable task outputs. Both differ from workflow artifacts used to pass deliverable files between jobs.

**E. If the cache is deleted, should the pipeline fail?**

No. The build should be able to re-download dependencies and regenerate outputs. A cache miss should only slow down the pipeline, unless the system intentionally runs offline with a fully seeded store.

**F. Does a successful artifact upload prove the application works properly?**

No. Uploading only proves the file was stored as a workflow artifact. You still need to run the packaged JAR, verify checksums, run integration/smoke tests, and check runtime behavior before publishing or deploying.

**G. Is `SHA256SUMS` uploaded alongside the JAR enough to stop an attacker who replaces both files?**

No. A sidecar detects transfer errors or wrong file selection when the checksum is independently trusted. For provenance, you need signatures/attestations, protected workflows, least privilege, and trusted artifact storage.

**H. Can GitHub workflow artifacts be used to retain releases for 2 years?**

Do not rely on default/bounded workflow artifact retention for long-term rollbacks. Publish releases to a Maven repository, generic artifact repository, or OCI registry with appropriate retention and immutability policies.

## 20. Official Documentation

- GitHub Actions — Dependency caching concepts: https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching
- GitHub Actions — Dependency caching reference, key matching and security: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- GitHub Actions — Workflow artifacts: https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts
- GitHub Actions — Store and share workflow artifacts: https://docs.github.com/en/actions/tutorials/store-and-share-data
- actions/setup-java — Maven/Gradle dependency, Wrapper and JDK caching: https://github.com/actions/setup-java
- actions/upload-artifact — Artifact upload, immutability and retention: https://github.com/actions/upload-artifact
- actions/download-artifact — Download and digest verification: https://github.com/actions/download-artifact
- Apache Maven — Introduction to repositories: https://maven.apache.org/guides/introduction/introduction-to-repositories
- Apache Maven — Local repositories: https://maven.apache.org/repositories/local.html
- Apache Maven — Settings reference and localRepository: https://maven.apache.org/settings.html
- Gradle — Dependency caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Build cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Build cache use cases: https://docs.gradle.org/current/userguide/build_cache_use_cases.html
- Spring Boot 3.5 — Packaging executable archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Maven Wrapper — Usage and configuration: https://maven.apache.org/wrapper/

**Key takeaway:** Caches answer **"what data can be reused to build faster?"**. Artifacts answer **"which exact file was produced in this run, how was it verified, and where must it be delivered?"**. Caches can miss or be deleted without breaking builds; artifacts must have clear identity, checksums, and upload/download flows. When releasing, ship **the exact verified bytes**, then store them long-term in a Maven repository or OCI registry per product policy.