# Choosing a CI Strategy for a Java Toolchain

Continuous Integration (CI) automatically pulls changes from source control, sets up a controlled build environment, compiles, tests, runs quality checks, and produces artifacts so the team gets early feedback. A CI strategy defines **when it runs, where it runs, which JDK is used, what is checked, how evidence is stored, and who is allowed to release artifacts**.

A good pipeline catches errors early, reproduces results consistently between developers and CI, covers the exact JDKs and OSes the product supports, protects secrets, and produces traceable artifacts. A strategy that is too lightweight will miss compatibility bugs; a strategy that is too broad on every commit will slow down feedback, waste runner capacity, and tempt developers to bypass CI.

This article explains how to choose a platform and design a Java pipeline using Maven or Gradle, from pull request to release. Examples use GitHub Actions and Jenkins; the principles for builds, testing, artifacts, and security also apply to GitLab CI, Azure Pipelines, Buildkite, or other CI systems.

## 1. What Decisions Does a CI Strategy Resolve?

Before writing YAML or a Jenkinsfile, the team needs to agree on:

- **Trigger:** Which commits, pull requests, merge queues, nightly schedules, or release tags run the pipeline?
- **Toolchain:** Which JDK vendor/version runs the build, compiler, tests, and packaging?
- **Runner:** Should it use hosted, self-hosted, container, or dedicated agents?
- **Quality gates:** Which compile, unit test, integration test, static analysis, and security scan checks are mandatory?
- **Matrix:** Which JDKs, OSes, and architectures need to be tested at each stage?
- **Caching:** Which dependencies and build outputs can be safely reused?
- **Artifact:** Which files are retained, signed, published, and promoted?
- **Security:** Which jobs are allowed to read secrets, issue tokens, or deploy?
- **Feedback:** Where and how quickly are failures surfaced?
- **Ownership:** Who maintains workflows, runners, plugins, JDKs, and policies?

CI is part of the Java toolchain. If a project pins a JDK but CI automatically uses a different version, or if the build tool differs between local machines and runners, the toolchain decision is not being fully enforced.

## 2. Gather Requirements Before Choosing a Platform

| Requirement Area | Questions to Answer |
|---|---|
| Repository | Is source hosted on GitHub, GitLab, Bitbucket, or an internal server? |
| Scale | How many repositories, modules, commits, and concurrent builds? |
| Java support | Which Java releases does the product support? |
| Platform | Are Windows, Linux, macOS, x64, ARM64, or native builds required? |
| Network | Which artifact repositories, databases, private networks, or license servers must runners access? |
| Security | Are isolated runners, audit logs, secret managers, signing, or OIDC required? |
| Compliance | How long must build logs, test reports, SBOMs, and provenance be retained? |
| Cost | How are runner, storage, cache, and maintenance costs accounted for? |
| Operations | Who patches runners, upgrades plugins, handles queues, and recovers CI when it fails? |
| Developer experience | Can developers run the exact same commands locally and in CI? |

Record hard constraints before scoring options. If artifacts must be built inside an internal network, hosted runners without access to private repositories may not meet the requirement. If Windows and macOS installers are needed, the pipeline must have runners on those target operating systems.

## 3. Choose the Right CI Model

| Model | Best suited when | Costs/risks to consider |
|---|---|---|
| Managed/hosted runners | You need a fast start, standard builds, and no internal network access | Time/compute limits, queuing, network access, changing OS images |
| Self-hosted runners | You need private networks, specialized hardware, licenses, or special native tools | Team must patch, isolate, monitor, clean up, and secure build machines |
| Hybrid | Standard build/test runs hosted; internal packaging or integration runs self-hosted | Must manage trust boundaries, artifact transfer, and runner permissions |

Hosted runners reduce build machine administration. Check how the provider manages images, OS versions, disk space, CPU/RAM, maximum job duration, and caching. Do not assume labels like ubuntu-latest always point to the same image over time.

Self-hosted runners are appropriate when builds require a private network, specialized hardware, license servers, signing hardware, or data that must not leave a controlled environment. Runners must be isolated:

- Do not run untrusted pull request code on persistent runners that have secrets or internal access.
- Prefer ephemeral runners or a fresh workspace deleted after each job.
- Separate regular build runners from signing/release runners.
- Restrict network egress, filesystem permissions, and service accounts.
- Update the OS, JDK, agent, and plugins on a schedule.
- Do not share a workspace or Maven local repository across concurrent builds without safe isolation.

A hybrid model often makes sense when most work is standard compilation and testing, while a few steps require Windows, macOS, devices, licenses, or a private network. Pass the exact built artifact to the privileged job; do not rebuild from a different source checkout in the release job.

## 4. Choose a Platform Based on Ecosystem and Operational Capability

| Platform | Common Strengths | What to Evaluate |
|---|---|---|
| GitHub Actions | Workflows live in the repository, pull request integration, matrix, and hosted runners | Action management, token permissions, runner cost, and security policies |
| Jenkins | Flexible agents, plugins, private infrastructure, and legacy systems | Controller, plugin, credentials, agent, and pipeline library upgrades |
| GitLab CI | Pipelines tied to repositories, merge requests, runners, and registry | Runner topology, permissions, caching, and ecosystem integration |
| Azure Pipelines | Azure DevOps integration, hosted/self-hosted agents, and environments | Agent pools, service connections, permissions, and template governance |
| Buildkite/other CI | Decouples orchestration from runner infrastructure as needed | Operational overhead, plugins/integrations, and traceability |

Choose a platform already supported by your organization if it meets your requirements. The cost of switching CI typically includes migrating pipelines, secrets, runners, artifact repositories, approvals, auditing, and training. Do not switch platforms just because a YAML example looks shorter.

Evaluate total cost of ownership: compute, storage, network, licenses, maintenance time, developer wait time for builds, and incident response cost.

## 5. Standardize the Java Toolchain Before Designing the Pipeline

CI is only reproducible when the project explicitly declares its toolchain. Distinguish between these versions:

| Component | Role |
|---|---|
| Build JVM | The JVM running Maven or Gradle |
| Compiler toolchain | The JDK providing javac for compile tasks |
| Release target | The API and bytecode compatibility the compiler must target |
| Test runtime | The JDK running unit/integration tests |
| Production runtime | The JDK/runtime supported by the product |
| Packaging JDK | The JDK used for jlink, jpackage, or native packaging |

Pin the Maven/Gradle Wrapper in the repository. Record the JDK vendor and version; for release builds requiring high reproducibility, pin the distribution and image digest or an installer with a verified checksum.

For example, if a project supports Java 17 as its baseline and wants to verify compatibility on JDK 25:

- Compiler release target: 17.
- CI runtime matrix: JDK 17 and JDK 25.
- Build tool: pinned Maven Wrapper or Gradle Wrapper.
- Dependencies and plugins: explicit versions, avoiding dynamic versions in releases.
- Packaging: runs on the OS/architecture the artifact actually supports.

Using a newer JDK to run the build does not automatically raise the release target. Conversely, a release target of 17 does not prove all dependencies can run on Java 17; you must test on the actual runtime.

## 6. Split the Pipeline into Lanes by Speed and Risk

There is no need to run the full test matrix, performance tests, and release scans on every file save. Split work into lanes:

| Lane | Trigger | Contents | Goal |
|---|---|---|---|
| Local feedback | Developer before push | Wrapper, compile, unit tests, formatter | Catch errors quickly on the local machine |
| Pull request | Each PR/commit update | Compile, unit tests, lint, critical tests, dependency policy | Decide whether it is ready to merge |
| Main/integration | Push or merge to main | Full unit/integration, package, smoke test, quality/security gates | Confirm integration status |
| Nightly/scheduled | Scheduled | Broad JDK/OS matrix, compatibility, performance, full scan | Find rare bugs and long-term regressions |
| Release | Tag or release approval | Build artifact, sign, SBOM, provenance, publish, and deploy | Release verified artifacts |

A good PR lane should be fast and reliable. A 5–10 minute target can be useful for some projects, but the realistic threshold must be based on build time and test suite size. Do not drop critical tests just to hit a target duration; move slow tests to the integration/nightly lane and define which results a release must wait for.

## 7. Design Triggers and Branch Policies

Common triggers:

- Pull request: runs required checks before merge.
- Push to main: confirms post-merge status and produces candidate artifacts.
- Merge queue: runs checks on the exact combination of commits to be merged.
- Nightly: runs broad matrices, full integration suites, and periodic scans.
- Tag/release: creates immutable artifacts, signs, and publishes.
- Manual dispatch: re-runs a workflow or profile in a controlled way for investigation.

If using trunk-based development, keep main always buildable and require green CI before merging. Branch protection should require the exact critical status checks; avoid creating too many redundant checks.

Path filters can reduce unrelated builds in a monorepo, but if a required check is skipped due to a filter, branch policy may hang waiting for a check that is never created. Use an always-running aggregate check if the repository requires a fixed status check.

For PR validation, older runs can be canceled when a new commit supersedes them. For deployments or releases that require ordering, queue or limit concurrency to one run at a time; do not cancel an in-progress release just because a new tag arrives.

## 8. Choose a Purposeful Test Matrix

A matrix can include Java version, OS, architecture, database, profile, or build mode. Multiplying every axis causes the job count to explode. For example, 3 JDKs × 3 OSes × 2 architectures × 2 databases produces 36 combinations.

### Minimum Matrix for PRs

- Compile with the standard JDK/toolchain.
- Run unit tests on the Java baseline.
- Run essential integration tests in the default environment.
- Run lint/static checks and dependency policy checks.
- Only add other OSes if code or packaging has relevant differences.

### Broad Matrix for main/nightly

- Lowest supported runtime.
- Latest supported runtime.
- Target OSes/architectures.
- Critical database or service versions.
- Native library and packaging tests on their respective platforms.

### Distinguish Compile Matrix from Runtime Matrix

If a project compiles with JDK 17 targeting release 17, testing the runtime on JDK 17 and 25 checks runtime compatibility. If you want to test a newer compiler, add a separate compile job using JDK 25 with the same release target.

Do not confuse a job running on JDK 25 with the compiler toolchain necessarily using JDK 25 if Gradle/Maven has selected a separate toolchain.

For compatibility matrices, set fail-fast to false if you want to see all failing JDK/OS legs in the same run. Mark jobs as experimental when they are outside the supported baseline. Limit max-parallel to balance queuing, cost, and load on artifact repositories.

## 9. Choose Runners and Build Environments

Runners need the right OS/architecture, JDK distribution/version, Wrapper and shell, native compilers/libraries if JNI or packaging is involved, CA certificates/locale/timezone/fonts if the application needs them, network routes to dependency repositories, and enough disk space for caches/tests/packaging.

For pure Java services, Linux hosted runners are usually sufficient for compiling and testing. If the product ships a Windows installer or macOS package, run jpackage on the target OS runner. Native packages depend on platform SDKs and toolchains; do not assume a Linux job can build proper installers for every OS.

Use container build images when you want to pin the OS/JDK/build utilities. Reference the image digest rather than only a mutable tag. Schedule regular image updates to pick up security patches; pinning a digest does not mean keeping an old image indefinitely.

## 10. Design Stages and Quality Gates

A typical Java pipeline may include:

1. Check out the exact commit.
2. Verify JDK, Wrapper, and build metadata.
3. Resolve dependencies.
4. Compile and check warnings.
5. Unit tests.
6. Static analysis, formatting, and policy checks.
7. Integration/contract tests.
8. Package JAR/WAR or application image.
9. Check dependencies, licenses, vulnerabilities, and secrets.
10. Smoke test the packaged artifact.
11. Generate checksums, SBOM, and provenance.
12. Archive/publish the artifact.
13. Deploy through a protected environment if releasing.

| Gate | When Needed | Pass Condition |
|---|---|---|
| Compile | Every PR | No compile errors |
| Unit tests | Every PR | Required tests pass |
| Formatting/lint | Every PR | Code rules are satisfied |
| Integration tests | Critical PR or main | Dependent services and contracts pass |
| Dependency/SCA scan | PR and release | No findings exceeding policy |
| Secret scan | PR/push | No committed secrets detected |
| License policy | PR/release | Dependencies comply with policy |
| SBOM | Release artifact | Complete inventory and versions |
| Smoke test | Artifact/package | Artifact runs on the target runtime |
| Signature/provenance | Release | Source, digest, and signature are valid |

Define severity levels, exceptions, owners, and remediation deadlines. A scan without a clear policy only generates extra reports without helping decide merge or release readiness.

## 11. Maven and Gradle in CI

### Maven

Use the Maven Wrapper:

~~~bash
./mvnw --batch-mode --no-transfer-progress verify
~~~

Windows:

~~~powershell
.\mvnw.cmd --batch-mode --no-transfer-progress verify
~~~

Pin the Maven distribution in the Wrapper properties. Record the JDK running Maven and, if using Maven Toolchains, record the compiler JDK actually selected by the plugin. For the release target, configure maven.compiler.release and pin a tested compiler plugin version.

In standard CI verification, verify is usually the right stopping point. Only use deploy in a release job that has publish permissions and dedicated protections.

### Gradle

Use the Gradle Wrapper:

~~~bash
./gradlew --no-daemon clean check
~~~

Windows:

~~~powershell
.\gradlew.bat --no-daemon clean check
~~~

check typically includes the verification tasks configured by the project. Do not assume every project has the same task graph; inspect the build logic.

Gradle has two distinct caches:

- Build Cache stores task outputs for reuse when their corresponding inputs have not changed.
- Configuration Cache stores the configuration/task graph result to reduce configuration work on subsequent runs.

They address different parts of the build and can work together. Enable caching after confirming that tasks/plugins are compatible and outputs are properly declared. Caching does not replace testing or artifact verification.

## 12. Caching Without Sacrificing Correctness

Caching reduces download time for dependencies, JDKs, and build outputs. A cache is a performance optimization, not a source of truth for release artifacts.

Maven typically caches the local repository, Wrapper distribution, and configuration files used as cache keys. Keys should change when POMs, Wrapper properties, extensions, or dependency inputs change. Do not share a single Maven local repository across concurrent writes without safe isolation.

Gradle has a dependency cache, Wrapper cache, Build Cache, and Configuration Cache. Each has its own contents and invalidation rules. A Remote Build Cache should have access control and a policy allowing only trusted CI to write to the cache if outputs can affect other builds.

Caching rules:

- Include OS/architecture and Wrapper/build configuration in the key.
- Include lockfiles, version catalogs, or dependency declarations.
- Do not cache secrets, signing keys, credential files, or sensitive workspaces.
- Be cautious with caches populated from untrusted pull requests.
- Use read-only caches for PRs/matrix fan-outs when appropriate.
- Purge caches per policy when poisoning or incompatible data is suspected.

A cache hit does not prove a build is reproducible. Maintain periodic clean builds or release builds that do not rely on untrusted cached outputs.

## 13. Secure Workflows and Runners

CI has access to source code, tokens, artifact repositories, signing credentials, and deployment environments. Workflows are part of the supply chain.

Grant only the permissions a job actually needs. Compile/test jobs usually only need read access to source. Publish jobs are the ones that need write permissions for packages or releases. Do not grant write permissions to the entire workflow just because one release step needs them.

For GitHub Actions, pin actions to a full-length commit SHA or use a workflow dependency lockfile if adopted by your organization. Tags are easier to read but can change over time. Review action source code and update SHAs through controlled pull requests.

Protect secrets:

- Never put secrets in YAML files, source code, command-line logs, or artifacts.
- Do not expose signing/deploy secrets to jobs processing untrusted PR code.
- Scope secrets to specific environments/jobs and limit their lifetime.
- Mask sensitive data, but do not rely on log redaction as the sole control.
- Rotate credentials if exposed in logs or artifacts.
- Keep signing keys separate from regular build runners.

If your cloud provider supports workload identity federation, OIDC can issue short-lived tokens based on workflow identity/claims. Grant id-token: write only to jobs that need to request a token; this permission allows requesting a token and does not itself grant cloud resource access. Cloud IAM must still validate subject, repository, branch, environment, and audience.

Do not run pull requests from forks or untrusted sources on self-hosted runners with internal network access. Use ephemeral runners, segment runner groups, restrict network access, and wipe workspaces after jobs.

## 14. Produce Traceable and Promotable Artifacts

A reliable release pipeline should build an artifact once and promote that exact artifact across environments. Do not rebuild from source for staging and production and assume the outputs are identical.

Store alongside the artifact: commit SHA and repository, build run ID/timestamp/workflow version, JDK vendor/version/build image digest/Wrapper version, dependency/plugin versions, test reports/scan results/SBOM, SHA-256 digest/signature, provenance/attestation if supported, and target OS/architecture/runtime requirements.

Distinguish between build artifacts, container images, installers, and deployed artifacts. Each needs its own digest. Tags like latest or release names are human-readable labels; digests are what uniquely identify the exact contents.

Artifact repositories should have retention, immutability, access control, and cleanup policies. Do not use a runner workspace directory as long-term release storage.

## 15. Separate Build, Verify, Sign, and Deploy

| Job | Input | Required Permissions |
|---|---|---|
| Build | Source and dependencies | Read repository, download dependencies |
| Verify | Built artifact | Read artifact, run tests/scans |
| Sign | Verified artifact | Access signing service/key per policy |
| Publish | Signed artifact and metadata | Write to artifact repository/package registry |
| Deploy | Published digest | Deploy permissions for the target environment |

Separating jobs limits exposure of secrets and write permissions. Downstream jobs must receive the exact artifact from the upstream job and verify its digest; they must not check out a branch again and build a different copy.

Releases and deployments require protected environments, reviewers/approvals, or policies commensurate with the risk level. Never let a pull request trigger a production deployment automatically.

## 16. GitHub Actions Example: Maven, Java 17/25 Matrix

The following example runs verify on pull requests and pushes to main. The project sets compiler release target 17; the matrix runs Maven on JDK 17 and 25 to check compatibility. The Maven Wrapper is committed to the repository.

The pom.xml file needs the corresponding configuration, along with pinning the compiler plugin and build plugins to tested versions:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Workflow .github/workflows/java-ci.yml:

~~~yaml
name: Java CI

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    name: Verify on Java ${{ matrix.java }}
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        java: ['17', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Record toolchain
        run: |
          java --version
          ./mvnw --version

      - name: Verify
        run: ./mvnw --batch-mode --no-transfer-progress verify
~~~

Replace the placeholders in the example with GitHub Actions expressions:

~~~text
${{ github.workflow }} -> github.workflow expression
${{ github.ref }} -> github.ref expression
${{ matrix.java }} -> matrix.java expression
${{ github.event_name == 'pull_request' }} -> github.event_name == 'pull_request' expression
~~~

How to read this configuration:

- pull_request and push to main run the same quality gate.
- permissions grants only contents: read to the verify job.
- concurrency cancels older CI runs on the same ref when a new commit arrives; do not use this setting for releases that must run sequentially.
- fail-fast false ensures results are visible for both JDK legs.
- setup-java installs the JDK, sets JAVA_HOME/PATH, and caches Maven dependencies/Wrapper.
- PRs use a read-only cache so untrusted sources do not write to the cache.
- Maven Wrapper ensures the Maven distribution matches the repository configuration.
- release target 17 preserves the API/bytecode baseline even when the test job runs on JDK 25.

The example uses action tags for readability. For repositories requiring supply-chain hardening, pin each action to a verified full-length commit SHA or use a workflow dependency lockfile per policy. Do not copy an unverified SHA from an example.

This is a PR/main verification workflow. Release jobs should be separate, triggered only on tags/approvals, consume verified artifacts, and be granted the necessary signing/publishing permissions.

## 17. Gradle Variant

For Gradle, use the Wrapper and configure the Java toolchain/release in the build file. Example build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

A basic verify job can run:

~~~yaml
- name: Set up JDK
  uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle

- name: Verify
  run: ./gradlew --no-daemon clean check
~~~

If the Gradle daemon runs on JDK 25 while the JavaCompile toolchain requires 17, the compiler task still needs to select the JDK 17 toolchain. Record both the build JVM and compiler toolchain in the build report. Verify that the Gradle version supports the JVM running Gradle and that plugins are compatible before upgrading the JDK.

When optimizing speed, enable Build Cache or Configuration Cache based on project compatibility. Do not enable flags en masse just because another build uses them; run tests first and verify that tasks/plugins declare inputs and outputs properly.

## 18. Jenkins Pipeline Example for Maven

Jenkins uses a Jenkinsfile to define pipelines as code. Agent labels select nodes with the appropriate JDK and environment. Minimal example:

~~~groovy
pipeline {
    agent {
        label 'linux && jdk17'
    }

    options {
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Toolchain') {
            steps {
                sh 'java --version'
                sh './mvnw --version'
            }
        }

        stage('Verify') {
            steps {
                sh './mvnw --batch-mode --no-transfer-progress verify'
            }
        }
    }

    post {
        always {
            junit testResults: '**/target/surefire-reports/*.xml, **/target/failsafe-reports/*.xml',
                  allowEmptyResults: true

            archiveArtifacts artifacts: '**/target/*.jar',
                             allowEmptyArchive: true,
                             fingerprint: true
        }
    }
}
~~~

Agents must have the appropriate JDK, access to the dependency repository, and sufficient disk space. The Wrapper pins the Maven distribution, but the JDK on the agent still needs to be managed. In Jenkins, credentials should be pulled from the Credentials store and bound only in the stages that need them; never put secrets in the Jenkinsfile.

Plugins such as Pipeline Maven Integration can configure Maven/JDK, settings, and artifact fingerprinting. Plugins should be pinned, updated, and managed as part of the CI toolchain.

## 19. Test Reports, Logs, and Failure Diagnosis

A useful pipeline must show where a failure occurred, not just return a non-zero exit code.

Retain Surefire/Failsafe or Gradle test reports, compiler warnings/errors, static analysis and dependency scan reports, build scan/timing reports if permitted, JDK/Maven/Gradle/OS versions, commit SHA/run ID/artifact digest, and service/test container logs when integration tests fail.

| Failure Category | How to Handle |
|---|---|
| Code/test regression | Fix the code or test; do not retry to mask failures |
| Dependency repository/network | Check status, timeouts, and mirrors; use bounded retries for transient errors |
| Runner infrastructure | Check runner health, disk, memory, and image |
| Flaky test | Reproduce, assign an owner, and fix the root cause; retry only to gather evidence |
| Cache corruption | Try a clean build or bypass cache; investigate keys and trust boundaries |
| Environment mismatch | Compare JDK, locale, timezone, architecture, and environment variables |
| Security policy failure | Remediate the finding or grant a time-bound exception with an owner |

Do not automatically retry every failed test. Retries can make a flaky test look like a pass and erode trust in required checks. If retries are used, preserve the first-attempt result and flag the test as flaky.

## 20. Measuring CI Strategy Effectiveness

| Metric | Meaning |
|---|---|
| Queue time | Time spent waiting for a runner |
| PR feedback time | Time from push until required checks complete |
| Build duration | Duration of each stage/job |
| Success rate | Pass rate of runs per lane |
| Flaky test rate | Rate of unstable tests |
| Cache hit rate | Whether caching is reducing load |
| Failure classification | Code, infra, dependency, or environment failures |
| Artifact reproducibility | Whether the same source/toolchain produces the expected digest |
| Deployment failure rate | Rate of failed deployments after release |
| Change lead time | Time from change to integration/release |

Do not optimize total pipeline duration by cutting critical tests. Break down time by stage: dependency download, configuration, compile, unit, integration, packaging, queue, and artifact upload.

## 21. Special Decisions for Monorepos and Multi-Module Projects

In a monorepo, a change in one module does not always require building every module. You can use a dependency graph or path filters to run only affected parts, but transitive dependencies must be handled accurately.

The strategy should include a root command to run full verification, verifiable rules for determining affected modules, integration jobs for linked modules, cache keys that include Wrapper/build logic/version catalogs, nightly full builds to catch issues missed by path filters, and release jobs that verify the entire dependency graph before publishing.

Do not let path filters turn a change in shared build logic into a PR that runs no checks. Files like parent POMs, settings.gradle, convention plugins, version catalogs, and workflow templates often affect many modules.

## 22. Strategy for jlink, jpackage, and Native Artifacts

If the project builds a custom runtime or installer, CI must verify both the runtime image and the application payload:

- Run jdeps to review module dependencies.
- Use jlink to create the runtime from the pinned JDK/toolchain.
- Run java --list-modules and --validate-modules on the image.
- Run jpackage on the target OS.
- Test the launcher, resources, TLS, locale, native libraries, and service bindings.
- Record digests for the runtime image, application image, and installer.
- Verify signatures/checksums before publishing.

Do not create Windows/macOS installers by simply renaming files from Linux. Use runners matching the target OS and architecture. Separate the native packaging matrix from the PR fast lane if time and cost are high; run fast smoke checks on PRs and the full platform matrix before release.

## 23. Common CI Anti-Patterns

| Anti-pattern | Consequence | How to Improve |
|---|---|---|
| Using the runner's default JDK | Builds change when images update | Install/pin the JDK explicitly |
| Using system Maven/Gradle | Versions differ between local and CI | Use the Wrapper |
| Testing only one JDK despite supporting multiple versions | Misses runtime incompatibilities | Matrix across baseline and supported runtimes |
| Matrixing every combination on every PR | Long queues and wasted compute | Split fast lane and nightly/release matrix |
| Caching without clear keys | Stale/poisoned caches or hard-to-reproduce results | Hash dependency inputs and separate trust boundaries |
| Caching build outputs without declaring task inputs | May reuse wrong outputs | Fix task inputs/outputs and test caching |
| Every job has deploy secrets | Increases blast radius | Separate jobs and grant least privilege |
| Actions/plugins use mutable tags without review | Supply-chain risk | Pin SHAs/lockfiles and audit source |
| Rebuilding in every environment | Artifacts can differ | Build once, promote the same digest |
| Retrying every failed test | Masks flaky tests and regressions | Classify failures, use bounded retries |
| Using persistent self-hosted runners for external PRs | Risk of leaking secrets/workspaces | Use ephemeral runners and trust isolation |
| Release workflows using concurrency cancel | Can cancel an in-progress release | Queue/serialize release jobs |
| Not saving test reports | Hard to investigate after a job finishes | Archive reports/logs with retention |
| Required checks skipped by path filters | Merge queue/branch protection gets stuck or misses gates | Use aggregate checks and controlled filters |

## 24. Step-by-Step CI Strategy Implementation Process

1. Document the Java release baseline, JDK vendor/version, and OS/architecture support.
2. Standardize the Maven/Gradle Wrapper, compiler release, and toolchain.
3. Choose the CI platform based on source control, runners, network, security, and operational capability.
4. Build a small PR lane: checkout, toolchain, compile, unit tests, and lint.
5. Configure required checks and branch protection.
6. Add a main integration lane with integration tests, packaging, and smoke tests.
7. Add a JDK/runtime matrix based on the support policy.
8. Add nightly scans, full platform matrices, and performance tests if valuable.
9. Configure cache keys, cache permissions, and a clean-build schedule.
10. Separate build, sign, publish, and deploy along trust boundaries.
11. Retain test reports, SBOMs, checksums, provenance, and artifact digests.
12. Measure queue time, feedback time, flaky rate, and failure categories.
13. Review workflows/plugins/runners/JDKs periodically and after every policy change.
14. Create runbooks for CI, cache, runner, and release failures.

Start with a simple, reliable pipeline. Add matrices, caching, specialized runners, and release automation when measured requirements justify them.

## 25. CI Strategy Review Checklist

- [ ] CI platform fits the repository and operational capability.
- [ ] Hosted/self-hosted/hybrid runners are chosen based on network, OS, and trust boundaries.
- [ ] JDK vendor/version, build JVM, compiler toolchain, and release target are distinguished.
- [ ] Maven/Gradle Wrapper is committed and pinned.
- [ ] Pull requests run compile, unit tests, and required quality gates.
- [ ] Main/integration runs integration tests and packaging.
- [ ] JDK/OS matrix aligns with the support policy.
- [ ] Matrix avoids redundant combinations and has a clear fail-fast policy.
- [ ] Nightly/release runs necessary broad checks.
- [ ] Cache keys are based on dependency/build inputs and contain no secrets.
- [ ] Caches from untrusted sources are not written to trusted caches.
- [ ] Workflow permissions follow least privilege.
- [ ] Actions/plugins are reviewed and pinned per policy.
- [ ] Secrets are only available in jobs that need them.
- [ ] OIDC/short-lived credentials are used where supported by the platform and allowed by policy.
- [ ] Self-hosted runners are isolated, patched, and cleaned up.
- [ ] Artifacts are built once, checksummed, and promoted by the same digest.
- [ ] Test reports, scan reports, and build metadata are retained.
- [ ] Release jobs have appropriate approvals/environment protection.
- [ ] Metrics, owners, and a review schedule exist for the pipeline.

## 26. Key Takeaways

- A CI strategy defines triggers, toolchains, runners, tests, caching, artifacts, security, and feedback.
- Choose a platform based on repositories, network, compliance, runners, and operational cost.
- Hosted runners reduce administration; self-hosted runners require isolation, patching, and cleanup.
- Use Wrappers and pin JDKs/toolchains to minimize differences between local machines and CI.
- Split PR, main, nightly, and release lanes by speed and risk level.
- Matrices should reflect the support policy; avoid multiplying every axis on every commit.
- Gradle's Build Cache and Configuration Cache solve two different types of work.
- Caching is a performance optimization; clean builds and artifact verification remain essential.
- Grant least privilege, pin actions, and protect secrets.
- Separate build, verify, sign, publish, and deploy along trust boundaries.
- Build once, promote the same artifact digest across environments.
- Retain reports, checksums, SBOMs, provenance, and build metadata.
- Track queue time, feedback time, flaky rate, and failure categories to drive improvements.

## Official References

- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
- [GitHub Actions: Workflow syntax and matrix](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub Actions: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Actions: OpenID Connect](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub Actions: Concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
- [Gradle: Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html)
- [Gradle: Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle: Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Apache Maven: Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Jenkins: Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Jenkins: Pipeline Maven Integration](https://www.jenkins.io/doc/pipeline/steps/pipeline-maven/)
- [Jenkins: Archive Artifacts](https://www.jenkins.io/doc/pipeline/steps/core/)