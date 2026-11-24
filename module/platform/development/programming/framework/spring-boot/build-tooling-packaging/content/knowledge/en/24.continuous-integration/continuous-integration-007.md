# Gating Publishing on Successful Required Checks

A Spring Boot build may compile cleanly and produce a JAR or container image, yet still not be eligible for release. An artifact must only be published once all **required quality gates** have executed and returned a successful result: unit tests, integration tests, code quality checks, dependency/security scans, package verification, and the release rules agreed upon by the team.

This lesson focuses on three principles:

1. **Every gate has a clear contract:** define which command runs, which reports are produced, pass/fail criteria, and how to handle test or scanner infrastructure errors.
2. **Publishing depends on every gate:** if any gate fails, is canceled, is unexpectedly skipped, or lacks evidence, the publish job must not run.
3. **The exact verified artifact is released:** when splitting build and publish across multiple jobs, transfer the exact QA-verified JAR/image, verify its checksum/digest, and never silently build another binary in the publish job.

The examples use **Java 17, Spring Boot 3.3.13, Maven 3.9.x, Gradle 8.x**, and GitHub Actions. This is a fixed illustrative version set; real projects must choose a compatible toolchain approved by their organization.

## 1. Gate Model from Source to Release

A Spring Boot release pipeline can be structured as follows:

```text
Pull request / protected release tag
                 |
                 v
        Checkout source + toolchain
                 |
                 v
       Compile + unit tests (UT)
                 |
                 v
       Integration tests (IT)
                 |
                 v
       Static / code quality checks
                 |
                 v
       Dependency / security / license checks
                 |
                 v
       Package executable JAR / OCI image
                 |
                 v
       Artifact smoke test + checksum
                 |
                 v
        All required gates SUCCESS
                 |
                 v
         Publish exact artifact
                 |
                 v
       Registry / artifact repository
                 |
                 v
        Verify remote artifact identity
                 |
                 v
        Protected deployment approval
```

Not every project needs a separate job per gate. Several steps can run within the same Maven/Gradle invocation or concurrently in CI. What matters is that **every gate's output lies on the dependency path before publishing**.

| Gate | Evidence | Passing Condition |
| --- | --- | --- |
| Compile | Compiler exit code, compiled classes | Zero compilation errors |
| Unit test | Surefire/Gradle test reports | Tests discovered and all pass |
| Integration test | Failsafe/Gradle IT reports | ITs run and results verified |
| Code quality | Lint, formatting, static analysis | All mandatory rules pass |
| Security | CVE, secret, malware, license scans | No findings blocking release per policy |
| Package | JAR layout, manifest, startup/smoke test | Valid executable artifact that starts cleanly |
| Integrity | Git commit, tool versions, SHA-256/digest | Artifact bound to exact source and build |
| Release policy | Version, tag, approval, branch rules | Valid source and release conditions |

Distinguish **required** from **advisory** checks. Warning-level coverage reports or scanner findings may be informational only. Required gates must have explicit pass/fail criteria. Never label a job as required if the pipeline still publishes when that job fails or is skipped.

## 2. Which Statuses Permit Publishing?

In CI, a gate can end in several states:

- **Success:** completed and met all criteria.
- **Failure:** check detected an error or command exited non-zero.
- **Cancelled:** canceled due to timeout, user action, or workflow cancellation.
- **Skipped:** did not run due to conditions, dependencies, or configuration.
- **No result:** job was never created, runner crashed, or status was never reported.

For a release gate, only an **explicit Success** qualifies. A skipped job is not evidence that a check passed.

| Unit Tests | Security Scan | Integration Tests | Publish |
| --- | --- | --- | --- |
| Success | Success | Success | Eligible for downstream release checks |
| Failure | Success | Success | Does not run |
| Success | Failure | Success | Does not run |
| Success | Success | Skipped | Does not run if IT is required |
| Success | Success | Cancelled | Does not run |
| Success | Success | Success | Still requires valid tag/version, approval, and artifact validation |

### 2.1. Fail-Closed Principle

A release pipeline should **deny publishing by default whenever evidence is missing**:

- If the test command did not run or discovered zero tests against policy, the gate must fail.
- If a scanner cannot reach its database or required service, the gate must fail or enter an approved exception process; never treat scanner errors as passing.
- If the artifact is missing, its checksum mismatches, or download fails, publishing halts.
- If a required job is skipped, canceled, or fails, publishing halts.
- Never use `continue-on-error: true`, `|| true`, `-x test`, `-DskipTests`, or similar settings to downgrade a required gate into advisory.
- Never put `always()` on a publish job to "publish even when an earlier job failed." `always()` suits report collection and cleanup, not bypassing quality gates.

A green dashboard means nothing unless the pipeline actually executed the required gates. Verify test counts, scanner scope, and the list of jobs `publish` depends on.

## 3. Define Release Policy Before Writing the Workflow

Example policy for a Spring Boot service:

| Category | Release Condition |
| --- | --- |
| Source | Commit from a protected branch or protected release tag |
| Java/toolchain | Properly configured Java 17, pinned Maven/Gradle Wrapper |
| Unit tests | All required tests pass; tests discovered |
| Integration tests | ITs run against production-like config and pass |
| Quality | Checkstyle/SpotBugs/JaCoCo or equivalent rules pass |
| Security | Dependency/image scans have no blocking findings per approved thresholds |
| Dependencies | No SNAPSHOT or dynamic versions if prohibited by release policy |
| Packaging | Valid Boot executable JAR or OCI image |
| Integrity | Checksum/digest computed and recorded |
| Publish | Runs only after all required gates succeed |
| Approval | Protected release environment approved when required |

Avoid vague conditions like "green CI" or "fully tested." Every condition must specify **which job/task enforces it**, **where the evidence lives**, and **which statuses are accepted**.

### 3.1. Distinguishing Build, Publish, and Deploy

- **Build/package:** produces the JAR or container image.
- **Publish:** pushes the artifact to a Maven repository, package registry, or OCI registry.
- **Deploy:** rolls out the published artifact to staging or production.

These three actions can have distinct gates and permissions. A publisher only needs artifact write access; a deployer needs environment rollout permissions. Never grant production deployment secrets to a job that only runs tests.

## 4. Maven Lifecycle: Using verify to Gate Unit and Integration Tests

Maven uses a standard lifecycle. For JAR projects, relevant phases typically are:

```text
validate
   |
compile
   |
test-compile
   |
test                 Surefire: unit tests
   |
package              executable JAR
   |
pre-integration-test setup environment
   |
integration-test     Failsafe: integration tests
   |
post-integration-test teardown environment
   |
verify               Failsafe verifies IT results
   |
install
   |
deploy
```

### 4.1. Surefire and Failsafe Serve Distinct Roles

- **Maven Surefire Plugin** runs unit tests in the `test` phase.
- **Maven Failsafe Plugin** runs integration tests in `integration-test` and checks results in `verify`.
- Failsafe intentionally avoids failing the build immediately in `integration-test` so `post-integration-test` can tear down test environments.
- Therefore, for integration tests, invoke **`mvn verify`**, not `integration-test` directly. Stopping at `integration-test` can skip teardown and verification steps.

`verify` runs all preceding phases, including compile, unit tests, packaging, and configured integration-test lifecycle goals. Running only `mvn package` does not guarantee Failsafe executed.

### 4.2. Spring Boot POM for Unit and Integration Tests

Example using Java 17, Spring Boot 3.3.13, and JUnit 5. `*Test.java` targets Surefire; `*IT.java` targets Failsafe.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>release-gate-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <includes>
                        <include>**/*IT.java</include>
                    </includes>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

`failIfNoTests` prevents this example from silently passing if expected test classes are not discovered. In multi-module builds where some modules lack ITs, configure this per module or profile instead of forcing it globally.

### 4.3. Spring Boot Application

`src/main/java/dev/example/releasegate/ReleaseGateApplication.java`:

```java
package dev.example.releasegate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReleaseGateApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseGateApplication.class, args);
    }
}
```

`src/main/java/dev/example/releasegate/StatusController.java`:

```java
package dev.example.releasegate;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/status")
    public String status() {
        return "ready";
    }
}
```

### 4.4. Unit Test Run by Surefire

`src/test/java/dev/example/releasegate/StatusControllerTest.java`:

```java
package dev.example.releasegate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StatusController.class)
class StatusControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void returnsReady() throws Exception {
        mvc.perform(get("/status"))
                .andExpect(status().isOk())
                .andExpect(content().string("ready"));
    }
}
```

This is an MVC slice test: Spring initializes the required web layer and `MockMvc` invokes the controller without opening a real TCP server.

### 4.5. Integration Test Run by Failsafe

`src/test/java/dev/example/releasegate/StatusControllerIT.java`:

```java
package dev.example.releasegate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StatusControllerIT {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate http;

    @Test
    void applicationServesHttpRequest() {
        String body = http.getForObject(
                "http://localhost:" + port + "/status",
                String.class
        );

        assertThat(body).isEqualTo("ready");
    }
}
```

The IT starts an embedded server on a random port and sends a real HTTP request over loopback. It verifies the application context, web server, and routing; it does not yet replace test databases, brokers, or external services if the application depends on them.

### 4.6. Running and Reading Results

From the project root:

```bash
./mvnw -B -ntp clean verify
```

Reports typically live in:

- `target/surefire-reports/` for unit tests.
- `target/failsafe-reports/` for integration tests.

On success, Maven finishes with:

```text
BUILD SUCCESS
```

This is a general completion line; exact test counts and logs vary by project. Do not rely solely on sample output with hardcoded test counts; verify the exit code and actual reports.

### 4.7. Flags That Bypass Gates

Never pass these flags in a release job when tests are required:

| Flag/Configuration | Effect |
| --- | --- |
| `-DskipTests` | Skips running tests depending on Surefire/Failsafe config |
| `-Dmaven.test.skip=true` | Skips both compiling and running tests |
| `-DskipITs` | Skips Failsafe integration tests/verification |
| `-Dmaven.test.failure.ignore=true` | Ignores test failures |
| `testFailureIgnore=true` | Prevents test failures from failing the build |

If developers need a fast build profile, keep that profile separate from the release pipeline and never let the publish job use it.

## 5. Gradle: Wiring Integration Tests into the check Lifecycle

With the Gradle Java Plugin:

- `test` runs unit tests.
- `check` is the lifecycle task aggregating verification tasks; by default it depends on `test`.
- `build` depends on `check` and `assemble`.

If a project defines a custom `integrationTest` task yet **fails to attach it to `check`**, `./gradlew build` can finish without running ITs. Always wire custom test suites into the verification lifecycle or invoke them explicitly in CI.

### 5.1. Gradle Groovy DSL for Spring Boot

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

sourceSets {
    integrationTest {
        java.srcDir file('src/integrationTest/java')
        resources.srcDir file('src/integrationTest/resources')
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests against the Spring Boot application.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    include '**/*IT.class'
    shouldRunAfter tasks.named('test')
    useJUnitPlatform()
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

`integrationTestImplementation` extends `testImplementation`; `integrationTestRuntimeOnly` extends `testRuntimeOnly`. Separating source sets keeps integration tests distinct from unit tests.

### 5.2. Placing the Integration Test in the Right Directory

Use the same test content from the Maven section, placed at:

`src/integrationTest/java/dev/example/releasegate/StatusControllerIT.java`

The class name ends in `IT`, matching the custom task's `**/*IT.class` include pattern.

### 5.3. Running and Inspecting the Task Graph

```bash
./gradlew clean check
./gradlew clean build
./gradlew check --dry-run
```

- `check` must run both `test` and `integrationTest`.
- `build` runs `check` and then `assemble`, thereby including attached verification tasks.
- `--dry-run` prints the planned task graph, useful for confirming ITs are included.

If CI only runs `./gradlew bootJar`, `check` does not necessarily run. `bootJar` is a packaging task; it does not prove all quality gates passed.

### 5.4. Gradle Skip and Ignore Settings

Never bypass required tasks during releases:

- `-x test` skips unit tests.
- `-x integrationTest` skips the custom integration task.
- `-x check` skips the aggregate verification task.
- `ignoreFailures = true` prevents test failures from failing the build.
- `onlyIf { false }` prevents tasks from executing.

If a task is unexpectedly skipped, the release pipeline must detect it and fail. Inspect the task graph, reports, and test counts.

## 6. Wiring Quality Gates into the Dependency Graph

Two common structures exist.

### 6.1. Single Job, Single Build Sequence

Maven example:

```bash
set -euo pipefail
./mvnw -B -ntp clean verify
./ci/run-required-quality-checks.sh
./ci/validate-release-artifact.sh target/release-gate-demo-1.0.0.jar
./ci/publish-release-artifact.sh target/release-gate-demo-1.0.0.jar
```

The shell halts if any required command returns a non-zero exit code. Each project script in this example must execute its corresponding gate and exit non-zero if criteria fail.

Maven has a `deploy` lifecycle phase after `verify`. When plugins are properly bound, `mvn deploy` runs preceding phases prior to deploying. However, external scans, security checks, and approvals still must be wired into the publish condition.

### 6.2. Multiple Jobs Connected via needs

Modern CI often splits jobs to run in parallel:

```text
       +--------- verify ---------+
       |                          |
       |                          v
       |                    upload artifact
       |
       +--------- security -------+
                    |
                    v
             all required jobs
                    |
                    v
                  publish
                    |
                    v
                  deploy
```

In GitHub Actions, `jobs.<job_id>.needs` declares jobs that must succeed before the current job runs. If any dependency fails or is skipped, downstream jobs are skipped by default unless the downstream condition overrides it.

Example:

```yaml
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - run: ./mvnw -B -ntp clean verify

  security:
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/run-security-gate.sh

  publish:
    needs: [verify, security]
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/publish-release-artifact.sh
```

`publish` runs only after both `verify` and `security` succeed. `needs` must list **every required gate**; any job omitted from `needs` will not block publishing.

### 6.3. Be Careful with if, success, and always

Release condition pattern:

```yaml
publish:
  needs: [verify, security]
  if: ${{ success() && github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') }}
```

This condition requires all dependencies to succeed and the workflow to be triggered by a `v...` release tag.

Never write:

```yaml
publish:
  needs: [verify, security]
  if: ${{ always() }}
```

`always()` allows the job to be scheduled even when dependencies failed or were skipped. It fits report collection and cleanup, not safe publish gating.

If a gate is optional under policy, explicitly define which events/branches are exempt in an auditable manner. Never make required gates optional via overly broad expressions.

## 7. GitHub Actions: verify → security → publish Workflow

Example for the Maven project in Section 4. The workflow runs checks on Pull Requests to `main` and when pushing `v*` release tags. Publishing runs only on tags after both `verify` and `security` succeed.

File `.github/workflows/release-gates.yml`:

```yaml
name: Spring Boot release gates

on:
  pull_request:
    branches: [main]
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  verify:
    name: Required build and tests
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run unit and integration tests
        run: ./mvnw -B -ntp clean verify

      - name: Prepare exact verified artifact
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p dist
          cp target/release-gate-demo-1.0.0.jar dist/
          sha256sum dist/release-gate-demo-1.0.0.jar \
            > dist/release-gate-demo-1.0.0.jar.sha256

      - name: Upload verified artifact
        uses: actions/upload-artifact@v4
        with:
          name: spring-boot-jar-${{ github.sha }}
          path: dist/
          if-no-files-found: error
          retention-days: 7

  security:
    name: Required security scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Scan source and dependency manifests
        run: |
          trivy fs \
            --scanners vuln,misconfig,secret \
            --severity HIGH,CRITICAL \
            --exit-code 1 \
            .

  publish:
    name: Publish verified release
    needs: [verify, security]
    if: ${{ success() && github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') }}
    runs-on: ubuntu-latest
    environment: release
    permissions:
      contents: read

    steps:
      - name: Checkout release metadata
        uses: actions/checkout@v4

      - name: Download artifact from verify job
        uses: actions/download-artifact@v4
        with:
          name: spring-boot-jar-${{ github.sha }}
          path: dist/

      - name: Verify artifact checksum
        run: |
          sha256sum --check dist/release-gate-demo-1.0.0.jar.sha256

      - name: Publish the verified JAR
        env:
          RELEASE_REPOSITORY_URL: ${{ vars.RELEASE_REPOSITORY_URL }}
          MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
          MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
        run: |
          set -euo pipefail
          test -n "${RELEASE_REPOSITORY_URL:-}"
          test -n "${MAVEN_USERNAME:-}"
          test -n "${MAVEN_PASSWORD:-}"

          ./mvnw -B -ntp -s .ci/settings-release.xml \
            org.apache.maven.plugins:maven-deploy-plugin:3.1.3:deploy-file \
            -Dfile=dist/release-gate-demo-1.0.0.jar \
            -DpomFile=pom.xml \
            -DrepositoryId=release-repo \
            -Durl="$RELEASE_REPOSITORY_URL"
```

### 7.1. Prerequisites for Running the Workflow

- The repository contains Maven Wrapper, POM, Java source/tests from Section 4, and `.ci/settings-release.xml`.
- The `security` job runner has a pinned/managed Trivy version and can reach the vulnerability database. If the scanner is absent or broken, the job must fail.
- `MAVEN_USERNAME`, `MAVEN_PASSWORD`, and `RELEASE_REPOSITORY_URL` are configured in the GitHub Environment/Variables/Secrets named `release`.
- The Maven server ID in the settings file is `release-repo`, matching `-DrepositoryId=release-repo`.
- Version `1.0.0` in the POM must match the release tag. Real projects need a tag/version consistency check and protection against re-publishing immutable release coordinates.
- The JAR path must match actual output. In multi-module builds it might be `api-service/target/...jar`.
- `@v4` actions are illustrative version tags. Production pipelines should pin actions to reviewed full commit SHAs or workflow dependency locks per policy.

### 7.2. Maven Settings for the Release Repository

`.ci/settings-release.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>release-repo</id>
            <username>${env.MAVEN_USERNAME}</username>
            <password>${env.MAVEN_PASSWORD}</password>
        </server>
    </servers>
</settings>
```

This file stores only variable names, no secrets. Maven `deploy-file` picks credentials matching the server ID. Never print resolved settings or enable Maven `-X` in public logs.

### 7.3. Why Does the Publish Job Download the Artifact from Verify?

The `verify` job builds the JAR, computes SHA-256, and uploads the artifact. The `publish` job downloads that exact artifact from the same workflow run, checks the checksum, and publishes that exact file via `deploy-file`.

This guarantees:

- The publish job never recompiles/repackages a different JAR with a different toolchain or cache.
- The checksum proves the downloaded file matches the uploaded file.
- The POM and settings come from the exact same commit/tag.
- If the artifact is missing or its checksum fails, publishing halts before contacting the repository.

In strict release pipelines, re-download the artifact from the remote repository using a read identity after publishing and compare checksums/digests. An "upload success" log alone does not prove remote bytes match the verified file.

### 7.4. Security Scanning Is a Real Gate

`trivy fs` illustrates scanning source/dependency manifests, misconfigurations, and secrets. `--exit-code 1` fails the command whenever findings match the chosen severities. The runner must have the right Trivy version and an updated database.

`HIGH,CRITICAL` is only an example threshold. Organizations must define policies per application type and environment alongside an exception process. When using another scanner, keep the same contract: **a scan that did not run or hit an infrastructure error must never pass**.

## 8. Branch Protection and Release Environments Are Separate Layers

Workflow `needs` controls job dependencies within **a single workflow run**. It does not by itself ensure every pull request passed those checks before merging.

Configure repository protections:

1. **Branch protection/rulesets:** require status checks `Required build and tests` and `Required security scan` to succeed before merging into `main`.
2. **Release tag policy:** restrict who can create/push `v*` tags and protect already released tags.
3. **Environment protection:** the `publish` job references the `release` environment, which can require reviewers, branch/tag rules, or wait approvals.
4. **Secret scoping:** only the release job holds publisher credentials; test jobs need no write tokens.
5. **Action policy:** pin actions, minimize `GITHUB_TOKEN` permissions, and review workflow edits.

`needs` prevents publishing inside a workflow run when dependencies fail; branch protection prevents merging code lacking required status checks; environment protection prevents privileged publish jobs from running prior to approval/policy compliance. These controls complement one another.

### 8.1. Required Status Checks Must Have Stable Names

Give jobs clear, unique names across workflows. When enabling branch protection, select the exact check contexts emitted by live workflows. If workflows skip via path filters or conditions, ensure required checks do not go missing or stay pending indefinitely; configure triggers so required jobs run on relevant changes.

### 8.2. Never Grant Publish Secrets to Pull Requests from Forks

PRs from forks may include build scripts modified by external contributors. Jobs executing that code must never hold publish rights or access release secrets. Run tests/scans read-only; grant write credentials only to protected release jobs after source is reviewed/merged and passes gates.

## 9. Gradle: Wiring check and publish Tasks to Required Gates

With Gradle, `./gradlew clean build` only runs verification tasks actually attached to `check`. Once `integrationTest` is configured as in Section 5 and wired into `check`, `build` runs unit tests, integration tests, and assembly.

With the Gradle Maven Publish Plugin, `publish` tasks do not automatically depend on `check` by default. You can wire publish tasks to `check`:

```groovy
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn tasks.named('check')
}
```

This snippet applies to projects with `maven-publish` applied and Maven publications/repositories declared. `check` must encompass all required verification tasks. In multi-job CI, still put `needs: [verify, security]` on the publish job so gates outside Gradle also block publishing.

### 9.1. Gradle CI Command

```bash
./gradlew --no-daemon clean build
```

If the pipeline runs static analysis, dependency verification, SBOM generation, or image scans, they must either be tasks in `check` or separate CI jobs that `publish` depends on. Never judge by `BUILD SUCCESSFUL` alone if the task graph omits policy-required gates.

### 9.2. Publishing the Exact Artifact Across Jobs

In a multi-job workflow:

1. `verify` runs `./gradlew clean build`, saving the exact JAR/Boot JAR and SHA-256.
2. `security` scans source, dependency graphs, or images per policy.
3. `publish` declares `needs: [verify, security]` and downloads the JAR/checksum from `verify`.
4. Verify the checksum before publishing.
5. Use a publisher configured to consume **the downloaded file**; never re-invoke a build task that generates a new artifact replacing the verified file.

If Gradle's `publish` task rebuilds components from source, inspect the task graph and outputs. For releases requiring exact artifact promotion, publish the exact verified file or keep build and publish inside one task graph with explicit dependencies.

## 10. Single Job or Multiple Jobs?

| Criterion | Single Job / Single Invocation | Multiple Jobs with needs |
| --- | --- | --- |
| Setup | Simple, minimal artifact transfer config | Requires artifact handoff and checksums |
| Parallelism | Limited | Tests, scans, and policy checks can run in parallel |
| Permissions | Single job may hold broad credentials | Easier to separate read/test from write/publish |
| Debugging | Single continuous log | Dedicated report per gate |
| Exact artifact | Shared workspace makes keeping file easy | Requires upload/download and checksum verification |
| Approval | Can place environment on final job | Easy to isolate protected publish/deploy jobs |
| Best fit | Small projects with clear lifecycles | Monorepos, multiple scanners/policies, enterprise releases |

A single Maven invocation `mvn clean deploy` walks phases preceding `deploy`, including `verify`, when plugins are bound properly. Still, scanners and approvals outside Maven must be wired into the publish gate.

## 11. Other Gates to Consider for Spring Boot

### 11.1. Code Quality and Coverage

- Checkstyle, SpotBugs, PMD, or equivalents.
- JaCoCo coverage thresholds if the team defines a baseline.
- Formatting and lint checks.
- API compatibility or architecture tests.
- Never substitute raw coverage percentages for test quality; tests without meaningful assertions still raise coverage.

If a coverage gate is required, the command must fail when below threshold. Report-only checks that never block builds are advisory only.

### 11.2. Dependency and Supply-Chain Checks

- CVE checks across direct and transitive dependencies.
- License policy checks.
- Checksum, signature, and dependency verification checks.
- SBOMs for JARs and container images.
- Pinning build plugins, Wrappers, and CI actions.
- Secret scanning in source and config.
- Builder and base image checks when building OCI images.

Never publish when a scanner fails to fetch its vulnerability database or verification metadata mismatches, unless governed by a formally approved, auditable exception.

### 11.3. Package and Image Validation

- Does the JAR have the expected Spring Boot executable layout (`BOOT-INF/classes`, `BOOT-INF/lib`)?
- Does `java -jar` start cleanly?
- Do health/readiness endpoints return expected responses?
- Does the OCI image have the expected repository, tag, platform, user, port, and configuration?
- Was the checksum/digest computed from the actual post-package artifact?
- Did the smoke test run the exact image/JAR selected for publishing?

### 11.4. Release Policy

- Version is not a `SNAPSHOT` for releases.
- Release tag matches the version in POM/Gradle.
- Commit/tag originates from a protected source.
- Immutable release versions are never reused.
- Changelog/release notes and approvals are complete.
- Artifacts are signed/attested if required by policy.

## 12. Avoiding Accidental Bypass Paths

| Configuration / Command | Risk | Remediation |
| --- | --- | --- |
| `-DskipTests` | Unit tests skipped | Ban in release workflows |
| `-Dmaven.test.skip=true` | Skips compiling and running tests | Ban in release workflows |
| `-DskipITs` | Integration tests skipped | Gate ITs explicitly or ban flag |
| `-Dmaven.test.failure.ignore=true` | Build continues despite test failures | Disable in releases |
| `-x test` / `-x check` | Gradle skips verification tasks | Never use in releases |
| `ignoreFailures = true` | Test failures do not fail task | Enforce fail-on-error |
| `continue-on-error: true` | Job stays green despite step failure | Use only on advisory steps |
| `if: always()` on publish | Runs even if dependencies fail/skip | Use `needs` + `success()` |
| Missing required job in `needs` | Publish fails to wait for that gate | List all required dependencies |
| Security job runs only on PR while tag publish lacks scan | Release lacks scan coverage | Run gate on tags or verify same commit |
| Publish job rebuilds package | Published artifact differs from tested one | Transfer artifact and verify checksum |
| Mutable `latest` tag | Rollback cannot pinpoint exact bytes | Store digest, use immutable references |
| Artifact upload ignores missing files | Publish lacks valid input | Use `if-no-files-found: error` and checksum verification |
| Scanner infrastructure error treated as pass | Missing scan evidence | Fail closed or use approved time-bound exception |

### 12.1. Use always to Collect Reports, Never to Publish

You can apply `if: always()` to steps uploading logs or test reports so reviewers can inspect results even when tests fail. That is a reporting step. The publish job itself must require success from every required job.

### 12.2. Gates Skipped by Path Filters

If a workflow skips running on certain file changes, required status checks may be missing or remain pending depending on settings. Skip builds only under reviewed path-based policies after confirming those paths cannot impact the deliverable. For release tags, ensure gates execute on the exact commit being released.

## 13. Multi-Module and Matrix Builds

### 13.1. Maven/Gradle Multi-Module

Suppose a monorepo layout:

```text
platform/
├── pom.xml
├── common-library/
│   └── pom.xml
├── api-service/
│   └── pom.xml
└── admin-service/
    └── pom.xml
```

When releasing `api-service`, ensure upstream modules it depends on are compiled and tested per policy. Do not assume `mvn -pl :api-service` automatically checks all required modules; `-am` builds upstream reactor projects, though test policies still need verification. In Gradle, `:api-service:build`'s task graph executes required dependencies without necessarily checking unrelated sibling modules.

### 13.2. Java/OS Matrices

If a product supports multiple Java versions or OS/architectures, publishing must wait for **every required matrix leg** to succeed. Never set `continue-on-error` on required matrix legs. If one matrix entry is advisory, separate it cleanly from release acceptance criteria.

When multiple legs upload artifacts, name each distinctly by Java/OS to prevent overwrites. Select the exact releasable artifact according to your matrix and release policy.

## 14. Evidence and Artifact Integrity

When splitting verify and publish:

1. Verify job creates the artifact.
2. Compute SHA-256 after packaging finishes.
3. Upload file and checksum as a pair.
4. Publish job downloads the exact artifact from the same workflow run.
5. Run `sha256sum --check`.
6. Publish the exact verified file.
7. Re-read the artifact from the repository/registry if possible and compare digests.
8. Write a release record: Git SHA, tag, CI run ID, artifact coordinates, SHA-256/OCI digest, test/security outcomes, and approvals.

Bash example:

```bash
sha256sum target/release-gate-demo-1.0.0.jar \
  > target/release-gate-demo-1.0.0.jar.sha256

sha256sum --check target/release-gate-demo-1.0.0.jar.sha256
```

Output when matching:

```text
target/release-gate-demo-1.0.0.jar: OK
```

A checksum verifies that the received file matches the stored digest; it does not prove builder identity or publisher authenticity by itself. Where strong provenance is required, sign artifacts/attestations and verify signatures, builder identity, and subject digests at the deploy gate.

## 15. Distinguishing Publishing from Production Deployment

Even after publishing an artifact, production deployment may enforce separate gates:

```text
Required CI checks
       |
       v
Publish immutable artifact
       |
       v
Verify registry digest
       |
       v
Staging deployment
       |
       v
Smoke / health / integration checks
       |
       v
Production approval
       |
       v
Deploy same digest to production
```

The production environment can require reviewer approvals, wait timers, branch/tag constraints, or custom policy checks. Those rules apply to jobs referencing the environment; they do not replace pre-publish tests and scans.

**Never rebuild when promoting staging to production.** Promote the exact verified artifact digest so staging and production never run different binaries under the same tag or version.

## 16. Diagnosing Release Gate Failures

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Publish runs despite unit test failure | `needs` omits test job or `if` overrides dependency status | List gate in `needs` and use `success()` |
| Publish skipped despite green tests | Another dependency skipped/canceled or wrong branch/tag rule | Inspect all `needs` jobs and `github.ref` |
| Maven `verify` passes with no IT report | Failsafe unbound or test names mismatch | Check plugin executions, `*IT.java`, and report directory |
| Maven stops before IT cleanup | Invoked `integration-test` directly or runner killed | Invoke `verify`; inspect teardown and reports |
| Gradle `build` passes without running ITs | Custom task not attached to `check` | Add `dependsOn` and inspect task graph |
| CI passes with 0 tests | Wrong discovery pattern or `failIfNoTests` disabled | Inspect reports/counts and enable fail-if-none |
| Security job green despite scanner not running | `continue-on-error`, `|| true`, or log-only step | Capture scanner exit code; fail on scanner errors |
| Publish cannot find artifact | Upload omitted file or artifact name/path mismatch | Use `if-no-files-found: error`; match names/paths |
| Checksum fails during publish | File modified, wrong download, or mismatched sidecar | Halt publish and investigate; never recompute to pass |
| Release tag differs from POM version | Tag/version consistency unchecked | Add a version consistency gate |
| PR checks pass yet tag lacks scan | Security workflow triggers only on PR | Run gate on tags or verify same commit |
| GitHub environment awaiting approval | Required reviewer or branch rules active | Review environment protection settings |
| Local build passes yet CI fails | Toolchain, env, cache, secret, or service mismatch | Use Wrapper, pin JDK, reproduce on runner |
| Matrix publishes despite one platform failing | Matrix leg had `continue-on-error` or missing dependency | Include every required leg in a required job |
| Release job rebuilds different artifact | Publish job re-runs package/build | Transfer verified artifact and compare digests |
| Publish succeeds yet remote pull fails | Registry path, ACL, token, or replication issue | Verify remote repository using a read identity |

### Investigation Steps When Publishing Is Blocked

1. Check each required job's status: success, failure, cancelled, or skipped.
2. Verify `publish`'s `needs` includes every required gate.
3. Read exit codes and Surefire/Failsafe or Gradle test reports.
4. Confirm scanners actually executed with proper thresholds.
5. Inspect branch/tag conditions, environment protections, and approvals.
6. Verify artifact upload/download names and paths match.
7. Compare checksums before publishing; on mismatch, preserve evidence and halt.
8. Rerun only after understanding root cause; never drop gates or tweak conditions to force a green release.

## 17. Self-Check Exercises

**Scenario A.** Maven unit tests pass, yet Failsafe ITs fail. Should we publish because `package` succeeded?

*Answer:* No. Failsafe `verify` checks IT results; `mvn verify` fails if integration tests do not pass.

**Scenario B.** `mvn integration-test` runs ITs, yet the test environment is not cleaned up. Why?

*Answer:* Stopping at `integration-test` never reaches `post-integration-test` or `verify`. Invoke `mvn verify`.

**Scenario C.** Gradle `build` is green, yet no `integrationTest` report exists. Likely cause?

*Answer:* The custom task was not attached to the `check` lifecycle; `build` only depends on `check` and `assemble`.

**Scenario D.** GitHub Actions `publish` has `needs: [verify]`, yet the security scan failed. Why did it still publish?

*Answer:* The security job was missing from `needs`. Add every required job to the dependency list.

**Scenario E.** The publish job uses `if: always()`. Tests fail yet the artifact still pushes. How do you fix it?

*Answer:* Remove `always()` from `publish`, populate `needs` completely, and use `success()` combined with branch/tag policy.

**Scenario F.** The security scan times out, yet `continue-on-error: true` leaves the job green. Has the gate passed?

*Answer:* No. There is no proof the scan finished. Remove `continue-on-error` on required scans or follow an approved, time-bounded, auditable exception.

**Scenario G.** `verify` uploads the JAR and checksum; `publish` rebuilds the JAR and pushes it. Are you sure the tested artifact was published?

*Answer:* No. `publish` must download the exact verified file, verify its checksum, and publish that file.

**Scenario H.** All jobs pass, yet the tag is `v1.0.0` while the POM version is `1.0.1`. Can it release?

*Answer:* Not if policy requires tag and version alignment. Add a version consistency gate.

**Scenario I.** PR checks passed, yet the tag workflow skips security scanning. Can you reuse the PR result to publish?

*Answer:* Only if policy verifies the exact same commit SHA, identical artifact/inputs, and still-valid scan results. It is safer to execute gates on the exact release tag/commit.

**Scenario J.** The publish job awaits reviewer approval and has not been approved yet. Is the job considered passing?

*Answer:* No. Environment protection prevents the job from running; approval is an independent release condition.

## 18. Release Gate Acceptance Checklist

**Tests and build:**

- Maven releases run `clean verify` or an equivalent lifecycle.
- Surefire runs unit tests; Failsafe runs ITs and verifies reports.
- Never call `integration-test` alone and treat the gate as complete.
- Custom Gradle `integrationTest` tasks are attached to `check`.
- Test discovery is verified; builds do not pass unintentionally with 0 tests.
- Skip flags and failure-ignoring options are banned in release jobs.

**CI dependency graph:**

- Every required gate maps to an explicit job/task with clear pass/fail outcomes.
- `publish` lists all required jobs in `needs`.
- Publish conditions enforce `success()` and valid branch/tag/release policies.
- `always()` and `continue-on-error` are never used to bypass publish gates.
- All required matrix jobs must pass.
- Branch protection/rulesets enforce the right required status checks.

**Artifact integrity:**

- JAR/image comes from the exact commit/tag.
- The verify job preserves the artifact and SHA-256/digest after packaging.
- The publish job downloads the exact artifact from the same run and verifies its checksum.
- Binaries are never rebuilt at publish/deploy stages when promoting exact artifacts.
- Remote repositories/registries are re-checked after upload.
- Release records capture commit, CI run, artifact coordinates, and digest.

**Security and approval:**

- Security, dependency, and license scans genuinely run and fail on blocking findings.
- Scanner outages never convert into passing results.
- Publisher credentials reside solely in protected release jobs.
- Untrusted PRs never access write secrets.
- Production environments enforce reviewer/branch/tag rules when required by policy.
- Production deployments use the exact published and approved digest.

**Conclusion:** Publishing conditions must be modeled as a **dependency graph with fail-closed semantics**. Maven uses `verify` to finish the Surefire/Failsafe lifecycle; Gradle attaches every verification task to `check`; CI uses `needs`/`success()` so publishing runs strictly after required gates; branch protection and environment approvals govern merges and releases; and checksums/digests ensure the exact verified artifact is shipped. Whenever any gate fails, is skipped, is canceled, or lacks evidence, the release must halt until the root cause is resolved.

### Official Documentation

- Maven Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven Surefire Plugin: https://maven.apache.org/surefire/maven-surefire-plugin/
- Maven Failsafe Plugin — Integration Test Lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/
- Gradle Java Plugin — test, check, build: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle Task Basics and Dependencies: https://docs.gradle.org/current/userguide/task_basics.html
- GitHub Actions Workflow Syntax — needs, if, environment: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Actions Deployments and Environments: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments
- GitHub Actions Secure Use: https://docs.github.com/en/actions/reference/security/secure-use
- Spring Boot 3.3 Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot 3.3 Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/