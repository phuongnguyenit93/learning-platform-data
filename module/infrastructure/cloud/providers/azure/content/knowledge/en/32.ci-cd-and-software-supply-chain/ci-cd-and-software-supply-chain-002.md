# Azure Pipelines for Java Application Build Workflows

A Spring Boot service running on Azure App Service is typically packaged from Java source code using Maven or Gradle. If each developer builds locally and sends JARs over chat or uploads them to a server, it becomes very hard to answer: **Which commit produced this JAR? Which JDK version was used? Did the tests run? Were dependencies downloaded from trusted sources? Who approved the code before the build? Can the same artifact be reproduced and errors traced?**

**Azure Pipelines** is the CI/CD service in Azure DevOps that lets you define workflows in YAML and execute them on agents. For Java, a solid pipeline does more than run **mvn package** or **gradle build**: it standardizes the JDK/toolchain, verifies source code, runs tests and quality gates, publishes reports, produces an **immutable build artifact**, and preserves evidence for subsequent deployment and auditing.

This lesson belongs to the **CI/CD and Software Supply Chain** chapter of the **CLOUD_PROVIDERS_AZURE** module. In the path of learning Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to networking, compute, storage, and data, Azure Pipelines is the link that automates **building, verifying, preparing for deployment, monitoring, and controlling risks/costs** of Java applications on Azure.

> **Scope:** Focuses on **Java build workflows using Azure Pipelines**: source → checkout → JDK → Maven/Gradle → test/quality → JAR → publish artifact. Pushing images to Azure Container Registry or deploying to App Service/AKS are downstream CI/CD steps, but **build must not be conflated with deploy**, and no real Azure resources need to be provisioned to practice this lesson.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain Azure DevOps organization/project, repository, pipeline, run, agent, pool, job, step, task, stage, and artifact.
2. Distinguish **CI build** from **CD release/deployment** and why build artifacts should be produced once and reused.
3. Create an **azure-pipelines.yml** file for Maven Java 17/21 on a Microsoft-hosted Ubuntu agent.
4. Use **JavaToolInstaller@0**, Maven Wrapper, and **Maven@4** appropriately.
5. Run **mvn verify** to test and package, publish JUnit XML, and publish artifacts.
6. Write an equivalent pipeline for **Gradle Wrapper** and understand the requirements of **Gradle@3/@4**.
7. Distinguish post-push pipeline **triggers** from **PR build validation** on Azure Repos versus GitHub.
8. Configure **dependency caching** with `Cache@2` and know when not to cache.
9. Manage environment variables, secret variables, variable groups, Azure Key Vault, service connections, and pipeline token permissions.
10. Design unit tests, integration tests, code coverage, and quality gates while avoiding masking test failures.
11. Secure the software supply chain: dependency sources, wrappers, lockfiles, SBOM, provenance, scans, and least privilege.
12. Separate temporary job workspace outputs from **Pipeline Artifacts**; retrieve artifacts by commit/build ID.
13. Troubleshoot JDK/Maven/Gradle errors, failed tests, 401/403 private feed errors, cache issues, disk quotas, and agent outages.
14. Set build-time SLOs and analyze agent duration/cost, retention, and optimization strategies.
15. Execute a full build cycle and evaluate a checklist before enforcing mandatory CI on the main branch.

## 2. Running scenario: Orders API with Spring Boot

A team develops the **orders-api** service using Java 21, Spring Boot, and Maven. The application will run on Azure App Service or in a container at a later stage.

Team requirements:

- Every push to **main** or **develop** must be built with the designated JDK.
- Every PR to **main** must pass build validation and unit tests.
- Unit tests must not be skipped just to build the JAR faster.
- The pipeline produces a clearly named/versioned JAR from the exact verified source commit.
- Test and coverage reports are available for reviewers and SREs to inspect.
- Dependency caching reduces build times without breaking reproducibility.
- PR pipelines must not read production credentials or perform deployments.
- The release team can retrieve the artifact from an approved run; no ad-hoc rebuilding on target servers.
- Logs must not contain passwords, PATs, access tokens, or secrets.

Basic CI diagram:

~~~mermaid
flowchart LR
    DEV["Developer commit / PR"] --> GIT["Azure Repos / GitHub"]
    GIT --> TRIGGER["Azure Pipelines<br/>CI / PR validation"]
    TRIGGER --> AGENT["Build agent<br/>JDK + Maven/Gradle"]
    AGENT --> TEST["Compile + unit/integration tests"]
    TEST --> QA["Coverage, dependencies,<br/>quality/security checks"]
    QA --> PKG["Package JAR / WAR"]
    PKG --> ART["Publish Pipeline Artifact<br/>run + commit provenance"]
    ART -. "later approved CD" .-> DEPLOY["App Service / AKS / VM"]
~~~

**CI output:** a run with status, logs, JUnit/test reports, and an artifact. **CD output:** deploying the verified artifact to an environment, typically with separate approvals and credentials.

## 3. Azure Pipelines in the Azure DevOps ecosystem

| Concept | Function | Example |
|---|---|---|
| **Organization** | Azure DevOps governance boundary | Company organization |
| **Project** | Group of repos, boards, pipelines, permissions | Commerce Platform |
| **Repository** | Stores source code and pipeline YAML | orders-api |
| **Pipeline** | Automation definition for build/release | orders-api-ci |
| **Run** | A single pipeline execution on a commit/context | Build #1428 |
| **Agent** | Machine/process executing work | Microsoft-hosted Ubuntu |
| **Agent pool** | Source of agents selectable by jobs | Azure Pipelines pool / custom pool |
| **Job** | Group of steps on an agent or server context | BuildAndTest |
| **Step** | Script/task/checkout inside a job | Maven@4 |
| **Task** | Pre-packaged Azure Pipelines action | Cache@2 |
| **Stage** | Group of jobs with conditions/dependencies | Build, Scan, Package |
| **Variable** | Pipeline configuration value | JDK_VERSION, MAVEN_CACHE |
| **Service connection** | Identity/authorization for calling external resources | Azure Resource Manager connection |
| **Pipeline Artifact** | Output stored/distributed from a run | orders-api JAR |
| **Environment** | Deployment target supporting checks/approvals | staging/prod |

### 3.1. YAML pipelines vs. classic pipelines

With YAML, configuration **lives in the repository**, is reviewed via Pull Requests, and shares change history with source code. Classic UI still exists in some projects; YAML makes it easier to standardize templates, test changes, and adopt GitOps practices.

### 3.2. Agents and agent pools

**Microsoft-hosted agents** are provisioned by Azure DevOps per job; images like **ubuntu-latest** come with many preinstalled tools, though versions can change as images update. New jobs should not depend on state left over from previous jobs.

**Self-hosted agents** are operated by the organization and fit scenarios needing internal network access, specialized tools, heavy builds, or hardware control. In return, you must update the OS/JDK/tools, secure tokens/working directories, manage quotas, and prevent malicious execution from untrusted PRs.

Never use a self-hosted agent carrying privileged production credentials to automatically execute code from arbitrary fork PRs.

### 3.3. Microsoft-hosted images are not immutable environments

The label **ubuntu-latest** can point to a newer OS/toolset image over time. For strong reproducibility:

- Choose a specific **vmImage** where appropriate and supported.
- Specify the **JDK version** explicitly.
- Use a pinned Maven/Gradle Wrapper and verify its checksum.
- Pin dependencies/plugins and inspect the resolved dependency tree.
- Record provenance of the agent image/toolchain.
- Optionally use a digest-pinned container job image, provided image/run capabilities match.

## 4. CI vs. CD and "build once, deploy many"

### 4.1. Continuous Integration

CI validates code on every push/PR per policy:

~~~text
Checkout source
→ Configure JDK
→ Resolve dependencies
→ Compile
→ Unit tests
→ Integration tests (if applicable)
→ Static checks + coverage
→ Package
→ Publish artifact
~~~

If required quality gates fail, **do not publish the artifact as a valid release candidate**.

### 4.2. Continuous Delivery/Deployment

CD can perform:

~~~text
Download approved artifact
→ Verify checksum/signature and metadata
→ Apply environment-specific non-secret config
→ Deploy to staging
→ Smoke test
→ Approval / checks
→ Deploy to production
→ Monitor / rollback
~~~

CD may use Azure Resource Manager service connections, managed identities/federated credentials, Azure App Service deploy, AKS manifests, or ACR. **Those permissions are unnecessary for a job that simply builds Java from public dependencies**.

### 4.3. Why not rebuild in production?

If each environment runs Maven independently, dependency repositories or plugin versions can shift between builds, making the artifact running in production **different** from what was tested in staging. An artifact built and verified once carries a **run ID, source commit, checksum, SBOM, and provenance**, aiding investigation and rollback.

A good artifact carries sufficient evidence yet **contains no secrets** or credentials from the build environment.

## 5. Maven and Gradle: Java build lifecycle

### 5.1. Maven

Maven uses **pom.xml** and a lifecycle; common phases include:

| Phase | Role | Runs tests? |
|---|---|---|
| validate | Validates project/POM | Depends on plugins |
| compile | Compiles main sources | Does not run tests automatically |
| test | Runs unit tests with Surefire by default when configured | Yes |
| package | Packages jar/war | Runs preceding phases |
| verify | Runs post-package checks, potentially integration-test/Failsafe/JaCoCo checks | Depends on POM |
| install | Installs artifact into local Maven repository | Unnecessary for single-module CI |
| deploy | Publishes to remote Maven repository (distinct from app deploy) | Side effects on artifact feed |

**Baseline recommendation:** use **mvn -B -ntp clean verify**, not merely **package -DskipTests**. **verify** only runs quality gates **configured in the POM**; it does not automatically generate integration tests, coverage, or security scans if the POM lacks those plugins.

### 5.2. Maven Wrapper

Projects should commit **mvnw**, **mvnw.cmd**, **.mvn/wrapper/maven-wrapper.properties**, and related files to install a pinned Maven version. The wrapper still downloads the Maven distribution if uncached on the agent; verify **distributionUrl/checksum/provenance** per policy.

~~~bash
# Local baseline before moving into Azure Pipelines:
java -version
./mvnw -B -ntp clean verify
~~~

On Windows, use **mvnw.cmd** or an appropriate shell environment. On Linux, **mvnw** needs executable permission, or you can invoke **bash ./mvnw** when the script is compatible.

### 5.3. Gradle

Gradle uses **settings.gradle(.kts)**, **build.gradle(.kts)**, and the Wrapper:

~~~bash
./gradlew --no-daemon clean check
./gradlew --no-daemon bootJar
~~~

- **test** runs unit tests.
- **check** typically depends on test and verification tasks.
- **build** typically runs assemble + check.
- **bootJar** builds an executable Spring Boot JAR when the Spring Boot plugin is configured.
- **integrationTest** is not a default task in every Gradle project; suites must be declared explicitly.
- **Gradle Wrapper** uses a pinned distribution/version.
- Do not run system **gradle** from the agent when you want the wrapper-controlled version.

### 5.4. JDK version

The JDK used for compilation must match **pom.xml maven-compiler-plugin release** or **Gradle Java toolchain**. Never assume JDK 21 runs Java 8 bytecode with identical semantics or library compatibility without testing. Distinguish:

- **Build JDK:** the agent JDK running Maven/Gradle.
- **Target bytecode release:** class file version and usable APIs.
- **Runtime JRE/JDK:** environment running the application after deployment.
- **Multi-module toolchains:** modules may target different versions.

A Spring Boot 3.x project typically requires Java 17 or higher; always check the version matrix for your actual framework and plugins.

## 6. Suggested repository structure

~~~text
orders-api/
├── azure-pipelines.yml
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── src/
│   ├── main/
│   │   ├── java/com/example/orders/
│   │   └── resources/application.yml
│   └── test/
│       └── java/com/example/orders/
├── docs/
│   └── build-and-release.md
└── .gitignore
~~~

Do not commit **target/**, **build/**, **.gradle/**, **.m2/**, or credentials. Generated files such as SBOMs or test reports can be published from the pipeline rather than committed to Git.

### 6.1. Minimal POM considerations

A Spring Boot Maven project needs plugins and dependencies to produce an executable JAR and run tests. Java version, Spring Boot plugin, Surefire/Failsafe, JaCoCo, and checks must be defined per framework/BOM. The pipeline **does not replace** the POM.

### 6.2. Maven Wrapper is executable code

Before allowing a pipeline to run **./mvnw** on an external PR, inspect the wrapper scripts, JAR, and distribution URL. A PR can modify pipeline YAML, the wrapper, or the POM to execute arbitrary code inside the job. Therefore, never attach high-privilege secrets to PR jobs.

## 7. Creating a pipeline in Azure DevOps

Typical UI workflow:

1. Sign in to the Azure DevOps organization with appropriate permissions.
2. Open **Project → Pipelines → New pipeline**.
3. Select the source repository (**Azure Repos Git**, GitHub, or supported provider).
4. Authorize repository access as needed; do not grant broader permissions than required.
5. Choose **Existing Azure Pipelines YAML file** if **azure-pipelines.yml** is already committed, or create a new one per policy.
6. Review the YAML file in a PR/working branch.
7. Select the agent pool and check hosted parallelism entitlements/quotas.
8. Trigger the first run on a trusted commit and inspect all steps.
9. Once verified, enable branch policies / PR validation for `main`.
10. Document ownership, notifications, and artifact retention policies.

**No real pipeline or Azure resource was created while authoring this lesson.** These steps serve as a guide for approved lab or project environments.

## 8. Maven YAML pipeline: build, test, and publish JAR

The example below targets a Java 21 repository using **Maven Wrapper**. Requirements: a **pom.xml**, a Linux-compatible **mvnw** script, and a POM configured to build a JAR. The artifact name is **orders-api-java**.

~~~yaml
# azure-pipelines.yml
trigger:
  branches:
    include:
      - main
      - develop

# pr: is used by Azure Pipelines for GitHub/Bitbucket Cloud.
# For Azure Repos Git, PR validation is configured via Branch Policies.
pr:
  branches:
    include:
      - main

pool:
  vmImage: 'ubuntu-latest'

variables:
  MAVEN_CACHE_FOLDER: '$(Pipeline.Workspace)/.m2/repository'

steps:
  - checkout: self
    clean: true
    fetchDepth: 1
    persistCredentials: false

  - task: JavaToolInstaller@0
    displayName: 'Select JDK 21'
    inputs:
      versionSpec: '21'
      jdkArchitectureOption: 'x64'
      jdkSourceOption: 'PreInstalled'

  - task: Cache@2
    displayName: 'Cache Maven dependencies'
    inputs:
      key: 'maven | "$(Agent.OS)" | **/pom.xml'
      restoreKeys: |
        maven | "$(Agent.OS)"
      path: '$(MAVEN_CACHE_FOLDER)'

  - bash: |
      set -euo pipefail
      java -version
      bash ./mvnw --version
      bash ./mvnw -B -ntp \
        -Dmaven.repo.local="$(MAVEN_CACHE_FOLDER)" \
        clean verify
    displayName: 'Maven compile, test and verify'

  - task: PublishTestResults@2
    displayName: 'Publish JUnit XML results'
    condition: succeededOrFailed()
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '**/surefire-reports/TEST-*.xml'
      searchFolder: '$(System.DefaultWorkingDirectory)'
      failTaskOnFailedTests: true
      failTaskOnMissingResultsFile: true

  - task: CopyFiles@2
    displayName: 'Stage JAR artifact'
    condition: succeeded()
    inputs:
      SourceFolder: '$(Build.SourcesDirectory)/target'
      Contents: '*.jar'
      TargetFolder: '$(Build.ArtifactStagingDirectory)/app'
      flattenFolders: true

  - task: PublishPipelineArtifact@1
    displayName: 'Publish immutable build output'
    condition: succeeded()
    inputs:
      targetPath: '$(Build.ArtifactStagingDirectory)/app'
      artifact: 'orders-api-java'
      publishLocation: 'pipeline'
~~~

### 8.1. Conditions for this example to work

- The repo is a **Maven project with a wrapper**; wrapper scripts must be checked out and the distribution reachable under network policy.
- **JavaToolInstaller@0** in **PreInstalled** mode requires the agent image to include a supported JDK 21. If the image changes or a self-hosted agent lacks it, use another reliable JDK installation method and pin the version.
- The POM includes unit tests and Maven Surefire outputs XML reports.
- **CopyFiles@2** picks up the JAR directly from **target/** of a **single-module project**. For multi-module builds, adjust the paths/selector.
- **PublishPipelineArtifact@1** applies to Azure DevOps Services; some Azure DevOps Server environments or other pipeline types may require a compatible artifact task.
- Setting **failTaskOnMissingResultsFile** prevents silent passes when tests are expected; verify exact semantics for your agent/task version.
- If a build produces no JAR, add an explicit file-existence check before Publish; do not assume CopyFiles fails by default when no artifact is found.

### 8.2. Why `verify` instead of `package`?

**clean verify** runs compile, test, and package; if the POM configures JaCoCo, Failsafe, or SBOM goals, they execute in lifecycle order. It does **not** automatically provide dependency scanning or coverage if the POM lacks those plugins.

### 8.3. Why does PublishTestResults run even when the build fails?

**condition: succeededOrFailed()** publishes XML reports even when Maven tests fail, allowing reviewers to see which tests broke. It does **not** turn a red pipeline green; the task preserves failure status and artifacts only publish when gates succeed.

### 8.4. JAR verification step

CopyFiles alone is not a strong enough quality gate if files are missing. In real Java projects, add a step after Maven verify and before CopyFiles:

~~~yaml
  - bash: |
      set -euo pipefail
      test "$(find target -maxdepth 1 -type f -name '*.jar' | wc -l)" -eq 1
      test -s "$(find target -maxdepth 1 -type f -name '*.jar' | head -n 1)"
      sha256sum target/*.jar
    displayName: 'Validate artifact count and checksum'
    condition: succeeded()
~~~

**Note:** If using multiple modules or producing **sources.jar / javadoc.jar**, refine the selector to pick only the deployable JAR. Logging the checksum provides build evidence, though it must not be confused with a digital signature.

## 9. Maven@4: built-in task or Maven Wrapper?

Azure Pipelines provides the **Maven@4** task to invoke Maven, integrate JDK selection, and publish JUnit test results. It is useful when an organization standardizes builds on task versions; Maven Wrapper is useful when a project locks the Maven distribution version inside the repository.

### 9.1. Basic Maven@4 task

With Maven preinstalled on the agent and **pom.xml** at the repository root:

~~~yaml
steps:
  - task: Maven@4
    displayName: 'Maven clean verify'
    inputs:
      mavenPOMFile: 'pom.xml'
      goals: 'clean verify'
      options: '-B -ntp'
      publishJUnitResults: true
      testResultsFiles: '**/surefire-reports/TEST-*.xml'
      javaHomeOption: 'JDKVersion'
      jdkVersionOption: '1.21'
      jdkArchitectureOption: 'x64'
      mavenVersionOption: 'Default'
~~~

This is an **alternative** to the Bash Maven Wrapper and PublishTestResults steps in Section 8, not an addition to run Maven twice. Verify task schema and agent Java versions on your Azure DevOps instance.

### 9.2. Comparison

| Criterion | Bash + Maven Wrapper | Maven@4 task |
|---|---|---|
| Maven version | Pinned in wrapper properties | Agent preinstalled or custom configured |
| Execution command | Full command line visible | Configured via task inputs |
| Publish test XML | Separate PublishTestResults@2 | Built-in support |
| Portability | Identical locally/CI with trusted wrapper | Tied to Azure Pipelines |
| Toolchain control | JDK task + wrapper | JDK/Maven task inputs |
| Maven updates | PR updating wrapper version/checksum | Agent/task update or custom install |
| Security | Wrapper/scripts are executable code to review | Task and agent versions also require review |

Do not pick `Maven@4` assuming "no POM review is needed." Both approaches execute code from build plugins and dependencies; source trust boundaries and credential isolation remain essential.

### 9.3. Avoid accidentally running tests twice

If you run `Maven@4` with **goals=clean verify** and also run **./mvnw verify**, tests execute twice, artifacts may be overwritten, and logs become confusing. Establish one clear **build authority** per job. If splitting stages for integration tests or security scans, define workload boundaries and artifact access explicitly.

## 10. Gradle YAML pipeline: Gradle Wrapper + Java 21

For a repository containing **gradlew**, **gradle/wrapper/**, **build.gradle(.kts)**, and the Spring Boot plugin, a Gradle Wrapper pipeline looks like:

~~~yaml
# azure-pipelines-gradle.yml
trigger:
  branches:
    include:
      - main
      - develop

pool:
  vmImage: 'ubuntu-latest'

variables:
  GRADLE_USER_HOME: '$(Pipeline.Workspace)/.gradle'

steps:
  - checkout: self
    clean: true
    persistCredentials: false

  - task: JavaToolInstaller@0
    displayName: 'Select Java 21'
    inputs:
      versionSpec: '21'
      jdkArchitectureOption: 'x64'
      jdkSourceOption: 'PreInstalled'

  - task: Cache@2
    displayName: 'Cache Gradle files'
    inputs:
      key: 'gradle | "$(Agent.OS)" | **/gradle-wrapper.properties'
      restoreKeys: |
        gradle | "$(Agent.OS)"
      path: '$(GRADLE_USER_HOME)'

  - bash: |
      set -euo pipefail
      java -version
      bash ./gradlew --version
      bash ./gradlew --no-daemon clean build
    displayName: 'Compile, test, package with Gradle'

  - task: PublishTestResults@2
    displayName: 'Publish Gradle JUnit reports'
    condition: succeededOrFailed()
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '**/build/test-results/test/TEST-*.xml'
      searchFolder: '$(System.DefaultWorkingDirectory)'
      failTaskOnFailedTests: true
      failTaskOnMissingResultsFile: true

  - bash: |
      set -euo pipefail
      mkdir -p "$(Build.ArtifactStagingDirectory)/app"
      find build/libs -maxdepth 1 -type f \
        -name '*.jar' ! -name '*-plain.jar' \
        ! -name '*-sources.jar' ! -name '*-javadoc.jar' \
        -exec cp {} "$(Build.ArtifactStagingDirectory)/app/" \;
      test "$(find "$(Build.ArtifactStagingDirectory)/app" \
        -type f -name '*.jar' | wc -l)" -eq 1
      sha256sum "$(Build.ArtifactStagingDirectory)"/app/*.jar
    displayName: 'Stage a single deployable JAR'
    condition: succeeded()

  - task: PublishPipelineArtifact@1
    displayName: 'Publish Gradle JAR'
    condition: succeeded()
    inputs:
      targetPath: '$(Build.ArtifactStagingDirectory)/app'
      artifact: 'orders-api-gradle'
      publishLocation: 'pipeline'
~~~

### 10.1. Requirements and adjustments

- Gradle Wrapper has valid scripts and distribution version, and **bash ./gradlew** runs on Ubuntu.
- The **java** and **Spring Boot** plugins are declared in `build.gradle(.kts)` according to app type.
- The project's **build** task runs tests and packages the JAR. For Spring Boot, verify that **bootJar** is in the task graph and generates the deployable JAR.
- The Java plugin typically writes JUnit XML under **build/test-results/test/**; custom test tasks use different paths.
- Filtering out **-plain.jar** follows Spring Boot convention and may need adjustment once the exact artifact name is known.
- In multi-module projects, artifacts may live under **services/orders-api/build/libs/** instead of root `build/libs`.
- Gradle user-home cache does not replace Gradle's build cache or configuration cache; apply separate versioning and permission policies.

### 10.2. Why use the Wrapper?

The wrapper eliminates Gradle version mismatches between developers and agents. However, **gradle-wrapper.jar**, **distributionUrl**, and checksums must still be verified because wrapper code or distribution URLs can be altered by malicious PRs. Version pinning does not replace dependency integrity.

### 10.3. Gradle@3/@4 tasks

Azure Pipelines also offers **Gradle task** versions supporting the Gradle wrapper, JDK, and test reporting. Use only task versions supported by your organization and check the exact inputs for that version rather than assuming every version shares the same **gradleWrapperFile, tasks, publishJUnitResults, testResultsFiles** inputs. Invoking **Gradle Wrapper via Bash** keeps commands explicit in the example above, though it does not make them inherently safer.

## 11. Triggers: push CI, Pull Requests, and branch policies

### 11.1. CI trigger

A YAML trigger:

~~~yaml
trigger:
  branches:
    include:
      - main
      - develop
  paths:
    exclude:
      - docs/**
~~~

The pipeline runs on matching pushes per provider and pipeline settings. Excluding `docs/**` saves build minutes, but carries risk if docs contain API specs, generated code, or build instructions affecting artifacts. Choose path filters according to your threat model.

### 11.2. PR triggers differ by source provider

**Important:** YAML **pr:** triggers generally apply to GitHub and Bitbucket Cloud. For **Azure Repos Git**, configure **Branch Policies → Build Validation** on the target branch to validate PRs; do not treat YAML `pr:` as a substitute for branch policies.

| Repo | Where is PR build validation typically configured? |
|---|---|
| **Azure Repos Git** | Branch Policies → Build Validation |
| **GitHub** | Azure Pipelines YAML `pr` trigger and GitHub branch protection/checks per integration |
| **Bitbucket Cloud** | YAML `pr` trigger and provider permissions/checks as supported |

A successful pipeline run on a feature branch does not guarantee PR merges to `main` are blocked on failure. Configure required build validation/status checks according to your repo provider.

### 11.3. Build validation branch policy for Azure Repos

Typical setup:

1. Open **Repos → Branches**.
2. On **main**, select **Branch policies**.
3. Add **Build validation** and select the exact pipeline.
4. Set the policy to **Required** if required by workflow.
5. Configure appropriate expiration/revalidation policies to avoid merging on stale builds.
6. Test a PR with a failing test and verify merging is blocked.
7. Modify build YAML in a PR and verify required validation still applies.
8. Do not grant bypass permissions lightly; audit anyone with bypass rights.

**Branch protection + code review + build validation** reinforce each other; no single check replaces the others.

### 11.4. PRs from forks are untrusted sources

When a pipeline runs code from a fork PR, YAML, shell scripts, Maven plugins, Gradle tasks, and test code may all be modified by an untrusted actor. Never grant production service connections, secret variables, strong PATs, or privileged self-hosted agent network access to these runs.

Never assume a job is "safe" just because it is named **UnitTest**: build steps can still execute arbitrary shell commands or binaries committed in the PR.

### 11.5. Manual, scheduled, and path triggers

You can organize:

- **CI push** for `main`/`develop`.
- **PR validation** for required branches.
- **Scheduled dependency scan** to detect new CVEs even when code has not changed.
- **Manual approved build** to produce release candidates.
- **Tag-based release** under governance.

Avoid overlapping rules that trigger 3 redundant pipelines for the same commit; measure throughput/cost and tune accordingly.

## 12. Variables, parameters, and secrets

### 12.1. Variable categories

| Type | Example | Safe to commit? |
|---|---|---|
| Regular YAML variable | `JDK_VERSION=21`, `MAVEN_CACHE_FOLDER` | Yes, if non-sensitive |
| Predefined variable | `Build.SourceVersion`, `Build.BuildId`, `Agent.OS` | Provided by Azure Pipelines |
| Runtime variable | `Build.SourceBranch` | Use per docs; do not trust as deploy approval |
| Template parameter | Choose JDK/goals at YAML compile time | Input requires review |
| Secret pipeline variable | Required access token / credential | Never commit value |
| Variable group | Scoped config/secrets with separate permissions | Protect permissions/approvals |
| Key Vault-linked variable group | Secrets fetched from Key Vault via integration | Requires Azure connection/Key Vault permissions |
| Service connection | Authorization to access Azure/feeds/external services | Do not leak secret into scripts |

### 12.2. Macro syntax and runtime

~~~yaml
variables:
  JAVA_TARGET: '21'

steps:
  - bash: |
      echo "Build ID: $(Build.BuildId)"
      echo "Commit SHA: $(Build.SourceVersion)"
      echo "Java target: $(JAVA_TARGET)"
    displayName: 'Non-secret build metadata'
~~~

Here, **$(...)** is Azure Pipelines variable expansion. Inside Bash, if a macro is undefined, an unexpanded **$(unknown)** becomes unintended Bash command substitution. Avoid building shell commands from untrusted user input; pass validated values via **env:** and quote properly.

### 12.3. Secret variables via `env`

Example **only when a job truly needs a token**:

~~~yaml
steps:
  - bash: |
      set -euo pipefail
      test -n "$PRIVATE_FEED_TOKEN"
      echo "Token available; value not displayed"
    env:
      PRIVATE_FEED_TOKEN: $(PRIVATE_FEED_TOKEN)
~~~

**PRIVATE_FEED_TOKEN** is stored as a secret variable in the Azure DevOps Library or a secure source; YAML holds only the **name**, not the value. For private Maven feeds, **MavenAuthenticate@0** and job identity are usually preferable to manually passing a PAT. Secret masking cannot guarantee hiding every transformed/substring variant of a secret, so **never print/echo tokens** or pass them in command-line arguments when safer options exist.

### 12.4. Do not use variables to enforce authorization

**Build.SourceBranch** can limit steps, but a string condition does not replace **branch policies, approvals, environment checks, resource authorization, or service-connection permissions**. Scope credentials at the resource level and ensure untrusted PRs cannot reference them.

## 13. Dependency caching and reproducibility

### 13.1. What does `Cache@2` actually cache?

`Cache@2` restores and saves a directory across runs keyed by a **cache key**. It can reduce the time Maven/Gradle spends downloading artifacts and metadata. However, it **does not replace a remote artifact repository**, does not guarantee dependency integrity, and does not turn a pipeline into a reproducible build.

~~~mermaid
flowchart LR
    START["New agent"] --> KEY["Evaluate cache key"]
    KEY --> CACHE{"Cache hit?"}
    CACHE -->|Yes| RESTORE["Restore Maven/Gradle dir"]
    CACHE -->|No| FETCH["Download verified dependencies"]
    RESTORE --> BUILD["Build + tests"]
    FETCH --> BUILD
    BUILD --> SAVE["Cache post-job save policy"]
~~~

### 13.2. Key strategy

Sample cache key:

~~~yaml
- task: Cache@2
  inputs:
    key: 'maven | "$(Agent.OS)" | **/pom.xml'
    restoreKeys: |
      maven | "$(Agent.OS)"
    path: '$(Pipeline.Workspace)/.m2/repository'
~~~

**Cache keys** can reference files or globs; when a POM changes, the cache key rotates. If using different Maven toolchains or Java versions, consider adding version or wrapper metadata to the key. For Gradle, include at least **gradle-wrapper.properties**, lockfiles, and OS.

### 13.3. Caches are immutable per key

Azure Pipelines caches are immutable for a given key; once saved, subsequent runs with the same key do not overwrite that cache entry. **restoreKeys** can fall back to a broader prefix, though new dependencies must still be downloaded from the repository. Use versioned key strategies and never cache build outputs assuming new source was compiled.

### 13.4. Poisoning and secret risks

- Never cache **Maven settings.xml** if it contains credentials.
- Never cache token files, `.npmrc`/`gradle.properties` with passwords, or Azure CLI caches.
- Never share a cache trust boundary between untrusted PRs and privileged release jobs if policy forbids it.
- Dependency caches may retain files downloaded from a compromised mirror; verify checksums/signatures whenever possible.
- Never cache **target/** or **build/libs/** and publish artifacts without rebuilding and testing from source.
- Rotate keys / clear caches if supply-chain compromise is suspected.

### 13.5. A warm cache is not a security guarantee

A cache hit speeds up builds, but if a repository artifact was tampered with, a compromised dependency was cached earlier, or a plugin contains malicious code, caching confers zero trust. **Reproducible builds** require pinning versions, verifying sources, running tests/checks, and recording provenance.

## 14. Build artifacts, naming, and traceability

### 14.1. Three things often confused

- **Workspace files:** JARs in **target/** or **build/libs/** on the agent.
- **Pipeline Artifact:** files uploaded/stored per pipeline run for retrieval in later stages.
- **Container image:** an image with layers/digest in a registry; not created automatically by publishing a JAR.

Do not assume a file placed in **$(Build.ArtifactStagingDirectory)** is a durable artifact until the Publish task runs.

### 14.2. Artifact metadata to record

| Metadata | Reason |
|---|---|
| Repo/project/pipeline ID | Origin |
| **Build.SourceVersion** | Exact Git commit |
| **Build.BuildId** | Run ID |
| Branch/PR/merge commit | Validation context |
| JDK/Maven/Gradle versions | Toolchain provenance |
| Dependency lock/SBOM | Software composition |
| Test/coverage results | Quality evidence |
| SHA-256 digest | Artifact content integrity check |
| Agent image/runtime | Reproducibility context |
| Timestamp UTC | Investigation/audit |
| Later approval/environment | CD traceability |

### 14.3. Publish and download

Publish from the build run:

~~~yaml
- task: PublishPipelineArtifact@1
  inputs:
    targetPath: '$(Build.ArtifactStagingDirectory)/app'
    artifact: 'orders-api-java'
~~~

A downstream job/stage in the **same pipeline** can use:

~~~yaml
- task: DownloadPipelineArtifact@2
  inputs:
    artifactName: 'orders-api-java'
    targetPath: '$(Pipeline.Workspace)/downloaded'
~~~

To download artifacts from **a different run** or pipeline, configure source/run identifiers per task documentation. Do not assume `DownloadPipelineArtifact` from the current run fetches an unpublished artifact. **CD must select an approved run** rather than pulling an arbitrary "latest" artifact from any branch.

### 14.4. Artifact retention

Artifacts can be purged under retention policies, storage quotas, or project settings. "Build once, deploy many" does not mean artifacts live forever. For approved release candidates, configure appropriate retention, preservation, or registry policies and verify recovery procedures if an artifact expires.

### 14.5. Checksums differ from signatures

**SHA-256** detects whether a binary was altered relative to a stored digest. However, if an attacker can replace **both the artifact and the checksum**, a hash alone does not authenticate the publisher. For higher supply-chain assurance, use **cryptographic signing/attestation** and protected provenance verified by policy at deploy time.

## 15. Testing: unit, integration, and reporting

### 15.1. Java test pyramid

~~~mermaid
flowchart TB
    FAST["Many fast unit tests<br/>JUnit 5 / Mockito"]
    INTEG["Fewer integration tests<br/>Testcontainers / emulator"]
    E2E["Few end-to-end<br/>staging smoke tests"]
    FAST --> INTEG --> E2E
~~~

**Unit tests:** logic without real Azure dependencies. **Integration tests:** DB/testcontainers, HTTP contracts, or an Azure lab resource with a clear lifecycle. **E2E tests:** staging services or approved environments. Never use production database credentials in PRs.

### 15.2. Surefire and Failsafe

Maven conventions:

- **maven-surefire-plugin** runs unit tests in the `test` phase, typically writing **target/surefire-reports/TEST-*.xml**.
- **maven-failsafe-plugin** can run integration tests in `integration-test`/`verify`, typically writing **target/failsafe-reports/TEST-*.xml** when configured.
- Class naming conventions such as **\*Test** and **\*IT** depend on plugin configuration.
- **mvn verify** will not run integration tests if the POM has not bound Failsafe goals.
- If using Testcontainers, the agent needs a compatible container runtime and permissions; Microsoft-hosted Linux images typically support Docker, though networking and quotas of your environment must be verified.

### 15.3. Publish both unit and integration reports

When both Surefire and Failsafe are present:

~~~yaml
- task: PublishTestResults@2
  condition: succeededOrFailed()
  inputs:
    testResultsFormat: 'JUnit'
    testResultsFiles: |
      **/surefire-reports/TEST-*.xml
      **/failsafe-reports/TEST-*.xml
    searchFolder: '$(System.DefaultWorkingDirectory)'
    failTaskOnFailedTests: true
    failTaskOnMissingResultsFile: true
~~~

Remember that publishing test reports **does not replace failing the build/test** when tests break. Never set **continueOnError: true** on the build task or **-Dmaven.test.skip=true** and treat a green pipeline as passing quality.

### 15.4. Flaky tests

Tests that pass or fail intermittently erode trust in PR validation:

- Eliminate uncontrolled timing and randomness.
- Use fake clocks, deterministic IDs, and isolated test data.
- Minimize external network dependencies in unit tests.
- When Azure lab integration is required, use dedicated environments and stable fixtures.
- Apply conditional retries/triage sparingly, **never masking real failures**.
- Quarantine flaky tests with an owner and timebound fix rather than disabling them indefinitely.

### 15.5. Test data must contain no secrets

Never print JWTs, API keys, customer PII, or database passwords into test logs, HTML reports, screenshots, or artifacts. Use synthetic fixtures or minimally scoped integration environment credentials.

## 16. Code coverage, quality gates, and static analysis

### 16.1. Coverage is not an absolute quality guarantee

**Line/branch coverage** measures which code lines or branches were executed during tests; it does not prove assertions are meaningful, integrations work, code is secure, or race conditions are absent. Still, coverage trends alert teams when testing is neglected.

| Gate | Common Java tools | Outcomes to inspect |
|---|---|---|
| Unit/integration tests | JUnit 5, Maven Surefire/Failsafe, Gradle Test | Pass/fail, JUnit XML |
| Coverage | JaCoCo | Line/branch coverage and thresholds |
| Lint/static | Checkstyle, PMD, SpotBugs, Error Prone | Violations by severity |
| Code quality | SonarQube/SonarCloud if adopted by org | Quality gate and findings |
| Dependency vulnerabilities | Approved SCA scanner | CVE/severity/remediation evidence |
| Secret scanning | Repo scanner and pipeline controls | Accidentally committed tokens/passwords |
| Licensing | SBOM/SCA/license policy | Policy-noncompliant libraries |

You do not have to enable every tool on day one; select gates based on risk, false-positive rate, ownership, and latency budget.

### 16.2. JaCoCo plugin in Maven

Sample **POM fragment**—pin an approved plugin version before building:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.jacoco</groupId>
      <artifactId>jacoco-maven-plugin</artifactId>
      <version>REPLACE_WITH_APPROVED_VERSION</version>
      <executions>
        <execution>
          <goals><goal>prepare-agent</goal></goals>
        </execution>
        <execution>
          <id>generate-report</id>
          <phase>verify</phase>
          <goals><goal>report</goal></goals>
        </execution>
        <execution>
          <id>quality-check</id>
          <phase>verify</phase>
          <goals><goal>check</goal></goals>
        </execution>
      </executions>
      <!-- Declare specific rules/limits if you want to fail below a threshold. -->
    </plugin>
  </plugins>
</build>
~~~

**REPLACE_WITH_APPROVED_VERSION** is a placeholder and will not run as-is. The `check` goal will not fail at an 80% threshold by default unless rules are declared in the POM. Maven **verify** only executes plugins and goals configured by the project.

### 16.3. Publishing coverage reports in Azure Pipelines

Once JaCoCo generates XML, you can add:

~~~yaml
- task: PublishCodeCoverageResults@2
  displayName: 'Publish JaCoCo coverage'
  condition: succeededOrFailed()
  inputs:
    summaryFileLocation: '$(System.DefaultWorkingDirectory)/target/site/jacoco/jacoco.xml'
    failIfCoverageEmpty: true
~~~

**Publishing** is not a **quality gate** on its own; use **JaCoCo check**, a Sonar quality gate, or another threshold-enforcing policy. Multi-module reports use different paths and may need aggregation. Verify syntax against your task/agent version.

### 16.4. When to fail the build?

Illustrative policy:

- Compile/test failure → **CI fail**.
- Missing required test reports → **CI fail**; never treat "0 tests" as a pass.
- Verified critical dependency vulnerability → **fail release** and triage.
- Secret scan detects real credential → **fail** and trigger incident response.
- Coverage drops below approved threshold → fail or require a timebound waiver.
- New minor lint warnings → optionally warn first, then promote to fail per plan.

Never use **continueOnError: true** to make a mandatory check look successful. Exceptions require an owner, expiration, and risk sign-off.

## 17. Private Maven feeds and Azure Artifacts

A Java project may consume internal libraries from an **Azure Artifacts Maven feed**:

~~~xml
<dependency>
  <groupId>com.company.shared</groupId>
  <artifactId>common-auth</artifactId>
  <version>2.1.0</version>
</dependency>
~~~

**401/403** errors during dependency resolution typically relate to feed authentication/permissions, **not** Key Vault or missing Azure Contributor roles.

### 17.1. MavenAuthenticate@0

When the pipeline identity has access to an existing Azure Artifacts feed:

~~~yaml
steps:
  - task: MavenAuthenticate@0
    displayName: 'Authenticate Maven feed'
    inputs:
      artifactsFeeds: 'team-maven-feed'

  - bash: |
      set -euo pipefail
      bash ./mvnw -B -ntp clean verify
    displayName: 'Build from approved feeds'
~~~

The task handles feed authentication as configured; **pom.xml or settings.xml** must still define the exact repository URL and server ID. Do not assume the task automatically creates dependency declarations. Never cache a settings file containing credentials into a shared Maven cache.

### 17.2. Job identity and feed permissions

The feed may require granting the Reader role to the **Project Build Service** or **Project Collection Build Service** identity depending on project/collection authorization scope. If the build fails:

1. Confirm the artifact `groupId`/`artifactId`/`version` exists.
2. Verify feed name, repository URL, and server ID.
3. Verify `MavenAuthenticate` runs before Maven.
4. Check that the pipeline identity has feed read permission.
5. Check cross-project feed authorization if applicable.
6. Check network egress to the feed.
7. Never put a long-lived PAT into the POM or logs as a "quick fix."

### 17.3. Release dependencies vs. SNAPSHOT

**SNAPSHOT** dependencies can change bytes even under the same version string. For release artifacts, prefer immutable versions, approved BOMs, and repository controls. If a build uses snapshots, you cannot claim reproducibility from the application commit alone.

### 17.4. Gradle private repositories

Gradle can also consume Maven repositories using credentials supplied via **environment variables** or credential providers. Never commit passwords into **build.gradle**, **gradle.properties**, Dockerfiles, or CI logs. Check plugin repositories, artifact repository URLs, and dependency verification.

## 18. Azure credentials, service connections, and secrets

### 18.1. Pure Java builds need no subscription credentials

A job compiling, testing, and packaging from public dependencies **needs no** Azure Resource Manager service connection. Fewer credentials in CI shrink the blast radius of a malicious PR.

### 18.2. Grant permissions only when actions require them

| Activity | Permissions typically needed |
|---|---|
| Build public Maven/Gradle project | Repo checkout and agent; no Azure subscription |
| Read private Maven feed | Azure Artifacts feed reader per project/identity |
| Push Docker image to ACR | Scoped registry push permission/connection |
| Deploy App Service or AKS | Azure service connection/identity and environment approvals |
| Fetch secret for approved integration test | Scoped Key Vault get permission in lab |
| Sign artifact | Signer identity/key permission per signing architecture |

**Never** allow PR validation to access a production service connection simply because another stage in the pipeline deploys.

### 18.3. Workload identity federation

Azure Resource Manager service connections can use **workload identity federation** instead of long-lived client secrets where supported. You must:

- Restrict resource/subscription scope.
- Restrict which pipelines can use the service connection.
- Enable approvals/checks or resource authorization as needed.
- Never enable "Grant access permission to all pipelines" indiscriminately.
- Prevent YAML from an untrusted PR from triggering a privileged publish job.
- Monitor changes to service connections and federated identity credentials.

### 18.4. Secret variables and variable groups

Use pipeline secret variables, Key Vault-linked variable groups, or secure files **only when the task genuinely requires them**. When passing a secret into a Bash task:

~~~yaml
steps:
  - bash: |
      set -euo pipefail
      test -n "$LAB_TOKEN"
      echo "Lab token is present (value omitted)"
    env:
      LAB_TOKEN: $(LAB_TOKEN)
~~~

**LAB_TOKEN** is a secret variable from a secure source, not a hardcoded literal. **Never echo values, log Authorization headers, or write them into artifacts**. Log masking has limits with substrings or transformations of a secret; a malicious build script can still exfiltrate any secret injected into the job.

### 18.5. PR code is untrusted code

A PR can modify **pom.xml**, Gradle scripts, wrappers, pipeline YAML, or test code to run arbitrary commands on the agent. A job named "UnitTests" is not inherently safe. Separate:

1. **Untrusted PR verification**: no production secrets or service connections.
2. **Trusted post-merge build**: protected by branch policies, tests, and limited publish permissions.
3. **Approved CD**: dedicated service connections, approvals, and deployment environments.

Never share a self-hosted agent holding long-lived credentials between untrusted and privileged runs.

## 19. Attack surfaces in the software supply chain

~~~mermaid
flowchart TD
    SRC["Repo + PR + pipeline YAML"] --> AGENT["Agent OS/JDK + build wrapper"]
    AGENT --> DEPS["Maven/Gradle plugins + dependencies"]
    DEPS --> TEST["Compile/test/quality gates"]
    TEST --> ART["JAR artifact + SBOM + provenance"]
    ART --> CD["Trusted release/deployment"]
    REPO["Private/public repositories"] --> DEPS
    AUTH["Scoped job token/credentials"] -. "only approved jobs" .-> DEPS
~~~

### 19.1. Execution sources that must be controlled

- Maven/Gradle wrapper scripts and distribution URLs.
- POM plugins, `build.gradle` tasks, and test setup code.
- Maven repositories, plugin repositories, and public mirrors.
- JDK/tool installers and agent image updates.
- Third-party Azure Pipelines extensions/tasks.
- Dockerfiles/base images if containerization follows later.
- Build scripts downloading binaries/installers from the network.
- Secret variables and service connections.
- Artifact publishing and storage paths.

### 19.2. Dependency pinning

Maven:

- Use fixed versions/BOMs and pin Maven plugins.
- Inspect **mvn dependency:tree** and the effective POM.
- Minimize SNAPSHOTs and version ranges on release paths.
- Verify the Maven Wrapper distribution checksum when available.
- Restrict downloads from unapproved repositories.

Gradle:

- Use **Gradle Wrapper** with pinned version/checksum.
- Consider dependency locking and dependency verification.
- Audit plugin repositories; do not assume version catalogs lock transitive versions unless configured.
- Run tests and SCA on the resolved dependency graph.

### 19.3. Avoid `curl | bash`

Anti-pattern:

~~~bash
# DO NOT run this example:
curl -fsSL https://unknown.example.invalid/install.sh | bash
~~~

Replace with an approved binary/installer using version pinning and checksum/signature verification, or a maintained Azure task. Never disable TLS validation to download dependencies.

### 19.4. Self-hosted agent isolation

- Prefer ephemeral workers for untrusted source code.
- Never mount production secrets, the host Docker socket, or shared home directories casually.
- Separate agent pools and networks between PR jobs and release jobs.
- Patch the OS/JDK/agent and restrict outbound networking.
- Clean workspaces, credential caches, and artifacts after privileged runs.
- Monitor abnormal process or network activity where feasible.
- Keep incident investigation logs free of secrets.

Microsoft-hosted agents reduce host maintenance overhead, but they do not replace repo permissions or secret isolation.

## 20. SBOM, provenance, checksums, and signing

### 20.1. SBOM

A **Software Bill of Materials (SBOM)** lists package and dependency versions, helping identify affected libraries when CVEs emerge. Common formats: **CycloneDX** and **SPDX**. A Java Maven project can use a pinned/approved **CycloneDX Maven Plugin** to generate an SBOM:

~~~bash
# Requires the plugin to be pinned and configured in pom.xml.
bash ./mvnw -B -ntp cyclonedx:makeAggregateBom
~~~

Output paths and goal names vary by plugin version and multi-module layout. Publish the SBOM alongside the JAR per artifact policy. An SBOM **does not prove dependencies are free of malware**.

### 20.2. Illustrative provenance metadata

~~~json
{
  "repository": "orders-api",
  "commit": "example-git-sha",
  "runId": "1428",
  "jdk": "21",
  "buildTool": "Maven Wrapper",
  "artifact": "orders-api.jar",
  "sha256": "example-checksum",
  "tests": "passed",
  "timeUtc": "2026-11-20T09:00:00Z"
}
~~~

This is illustrative metadata only, **not a cryptographically signed attestation**. Never call a self-generated JSON file trusted provenance if an attacker could alter both the metadata and the binary.

### 20.3. Hashes, signatures, and attestations

| Mechanism | Value | Limitation |
|---|---|---|
| SHA-256 | Checks whether binary changed relative to digest | Does not verify who built it |
| SBOM | Inventories components and dependencies | Does not prove security by itself |
| Digital signature | Verifies signer and bytes under a valid trust chain | Does not prove code is bug-free |
| Build provenance | Source, toolchain, builder, and run metadata | Requires a trusted builder/attestation |
| SLSA-style controls | Reduces source/build tampering risk | Does not replace runtime security |

To practice "build once, deploy many," downstream CD should download the **approved artifact from a specific run** and verify digests/signatures per policy, rather than rebuilding from a new branch HEAD or pulling an uncontrolled "latest."

### 20.4. A typical supply-chain attack

An attacker edits the POM to add a plugin running in the `validate` phase that reads CI secret variables and exfiltrates them. Unit tests may still pass. Controls:

1. Keep secrets out of PR jobs.
2. Review POM/wrapper/pipeline YAML as **executable code**.
3. Protect service connections and variable groups.
4. Restrict egress and agent privileges.
5. Grant least-privilege feed/artifact publish permissions.
6. Use scanners, trusted repositories, and provenance.
7. Require code owners and PR validation before trusted releases.
8. Maintain an incident response plan when build logs or credentials are exposed.

## 21. Multi-stage pipelines and job boundaries

A complex pipeline may split into **Build → VerifyArtifact → Release**. Example using two stages—build and artifact inspection—without deploying:

~~~yaml
trigger:
  branches:
    include:
      - main

pool:
  vmImage: 'ubuntu-latest'

stages:
  - stage: Build
    jobs:
      - job: BuildJava
        steps:
          - checkout: self
          - task: JavaToolInstaller@0
            inputs:
              versionSpec: '21'
              jdkArchitectureOption: 'x64'
              jdkSourceOption: 'PreInstalled'
          - bash: |
              set -euo pipefail
              bash ./mvnw -B -ntp clean verify
            displayName: 'Build and test'
          - task: PublishTestResults@2
            condition: succeededOrFailed()
            inputs:
              testResultsFormat: 'JUnit'
              testResultsFiles: '**/surefire-reports/TEST-*.xml'
              failTaskOnFailedTests: true
          - task: CopyFiles@2
            inputs:
              SourceFolder: '$(Build.SourcesDirectory)/target'
              Contents: '*.jar'
              TargetFolder: '$(Build.ArtifactStagingDirectory)/app'
          - task: PublishPipelineArtifact@1
            inputs:
              targetPath: '$(Build.ArtifactStagingDirectory)/app'
              artifact: 'orders-api-java'

  - stage: VerifyArtifact
    dependsOn: Build
    condition: succeeded()
    jobs:
      - job: Inspect
        steps:
          - checkout: none
          - task: DownloadPipelineArtifact@2
            inputs:
              artifactName: 'orders-api-java'
              targetPath: '$(Pipeline.Workspace)/app'
          - bash: |
              set -euo pipefail
              test "$(find "$(Pipeline.Workspace)/app" \
                -type f -name '*.jar' | wc -l)" -eq 1
              sha256sum "$(Pipeline.Workspace)"/app/*.jar
            displayName: 'Verify downloaded JAR'
~~~

### 21.1. Key takeaways

- **Jobs may run on different agents**, without access to the prior job's `target` directory.
- Use **PublishPipelineArtifact/DownloadPipelineArtifact** to exchange outputs across stages.
- **dependsOn + condition: succeeded()** blocks downstream stages when builds fail.
- **Stages do not protect credentials on their own**: resource authorization, branch policies, and approvals are required.
- Production Copy/Publish steps should use explicit conditions/validation so empty artifacts are never published.
- Each stage/job adds overhead and can increase agent minutes.
- A build run on a feature branch can still produce an artifact, yet **is not automatically an approved release**.

### 21.2. Job dependencies do not replace release policy

If a manual build runs on an untrusted branch, downstream deploy must verify source run, branch, commit, approvals, tests, and provenance. Never use an unvetted "latest artifact" as a release source.

## 22. Multi-module Java and monorepos

### 22.1. Maven reactor

Project layout:

~~~text
commerce/
├── pom.xml
├── common-model/
│   └── pom.xml
├── common-security/
│   └── pom.xml
├── orders-api/
│   ├── pom.xml
│   └── target/orders-api-1.0.jar
└── azure-pipelines.yml
~~~

Running **mvn clean verify** at the root builds reactor modules per POM. The deployable JAR sits in **orders-api/target**, not necessarily in root **target/**.

~~~yaml
- task: CopyFiles@2
  inputs:
    SourceFolder: '$(Build.SourcesDirectory)/orders-api/target'
    Contents: 'orders-api-*.jar'
    TargetFolder: '$(Build.ArtifactStagingDirectory)/app'
    flattenFolders: true
~~~

Refine the selector so **sources.jar**, **javadoc.jar**, or library modules are not copied by mistake. You can build a specific module and its reactor dependencies:

~~~bash
bash ./mvnw -B -ntp -pl orders-api -am clean verify
~~~

**-pl** selects the module and **-am** builds upstream reactor dependencies. However, changes to **common-security** require thorough testing; running only unit tests in `orders-api` may miss shared-module checks.

### 22.2. Gradle multi-project

Layout:

~~~text
settings.gradle.kts
build.gradle.kts
common-model/build.gradle.kts
orders-api/build.gradle.kts
~~~

Task path in a Gradle multi-project build:

~~~bash
bash ./gradlew --no-daemon :orders-api:build
~~~

The JAR may reside under **orders-api/build/libs/**. Ensure Gradle projects, plugins, and tasks are explicitly declared; Gradle does not automatically know which module is the deployable app.

### 22.3. Path filters in a monorepo

~~~yaml
trigger:
  branches:
    include:
      - main
  paths:
    include:
      - services/orders-api/**
      - libraries/common/**
      - build-tools/**
      - azure-pipelines.yml
~~~

These paths are examples. If **pom.xml, settings.gradle.kts, version catalogs, wrappers, or shared security code** fall outside the filter, changes may fail to trigger necessary builds. For Azure Repos PRs, configure matching **Build Validation branch policy path filters**.

### 22.4. Matrix builds

A Java library may need verification on both JDK 17 and JDK 21:

~~~yaml
# Fragment inside a job; do not place strategy under steps.
strategy:
  matrix:
    JDK17:
      JAVA_VERSION: '17'
    JDK21:
      JAVA_VERSION: '21'

steps:
  - task: JavaToolInstaller@0
    inputs:
      versionSpec: '$(JAVA_VERSION)'
      jdkArchitectureOption: 'x64'
      jdkSourceOption: 'PreInstalled'
  - bash: bash ./mvnw -B -ntp clean verify
~~~

A matrix increases confidence across runtimes, but also increases **parallel jobs, cache diversity, and build minutes**. For a single-runtime Java 21 app, avoid wide matrices without a compatibility requirement.

## 23. JAR versioning and release candidates

### 23.1. Layered artifact identity

~~~text
Maven coordinates:
  groupId    com.example.orders
  artifactId orders-api
  version    1.8.0

Azure Pipelines:
  Build.BuildId        = 1428
  Build.SourceVersion  = abcdef123...
  Branch               = refs/heads/main

Artifact:
  orders-api-1.8.0.jar
  SHA256 <digest>
~~~

The JAR's **semantic version** differs from **Build.BuildId** and the Git commit hash. During PR validation, **Build.SourceVersion** may represent a merge commit rather than the branch HEAD directly; record the exact value reported by the run.

### 23.2. Do not mutate POM versions uncontrollably

If the pipeline alters the version before building, that mutation is a build input and must be recorded in provenance and the release manifest. Prefer committed versions or reviewed release workflows rather than auto-committing version bumps to `main` from a PR job.

### 23.3. Distinguishing outputs

| Output | Used for | Verification needed |
|---|---|---|
| Executable JAR | Spring Boot application | Main class, Java runtime, checksum |
| WAR | Java web/servlet runtime | Servlet container compatibility |
| Library JAR | Azure Artifacts Maven feed | Coordinates/immutable version |
| Container image | AKS/Container Apps | Base image, SBOM, scan, digest |
| Native binary | GraalVM-native project | Toolchain, architecture, tests |

This lesson focuses on building JARs. Docker builds and ACR pushes are extension steps and do not happen automatically when publishing a JAR.

### 23.4. Illustrative release manifest

~~~json
{
  "service": "orders-api",
  "artifact": "orders-api-1.8.0.jar",
  "sourceCommit": "abcdef123",
  "runId": "1428",
  "artifactSha256": "example-hash",
  "jdkVersion": "21",
  "tests": "PASSED",
  "qualityGate": "PASSED"
}
~~~

This is simulated metadata. An unsigned, unattested JSON file does not constitute trusted provenance.

## 24. Conditions, branch checks, and deployment permissions

### 24.1. Branch-scoped condition

~~~yaml
- bash: |
    echo "Trusted main post-build metadata task"
  condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
~~~

This condition prevents unnecessary steps on feature branches, but **is not a sufficient access-control boundary** if a PR can modify YAML and access privileged service connections.

### 24.2. Defense layers

- **Condition:** YAML logic within a job/step.
- **Branch policy:** requires reviews and build validation before merging.
- **Repository permissions:** controls who can edit YAML, code, tags, and `main`.
- **Service connection authorization:** controls which pipelines can use a credential.
- **Environment approvals/checks:** pre-deployment gates.
- **Azure RBAC:** controls what an identity can do on Azure resources.
- **Feed permissions:** controls which packages the build identity can read or write.

A green pipeline does not bypass CD approval layers. Never allow code from an untrusted PR to invoke production service connections.

### 24.3. Separation of duties

Developers open PRs, reviewers/owners approve, CI jobs build and test with least privilege, release operators approve, and deployment jobs run with staging/prod-scoped identities. Audit any branch policy bypasses or service connection grants to new pipelines.

### 24.4. When building a container after the JAR

Extended workflow:

~~~text
Compile/test Java
→ Package immutable JAR
→ Scan dependencies/SBOM
→ Docker build using pinned trusted base image
→ Scan/sign image
→ Push ACR with scoped identity
→ CD deploy approved digest
~~~

Never collapse all steps into a single `docker push` while skipping tests; likewise, ACR is not required to complete this Java CI lesson.

## 25. Troubleshooting Azure Pipelines for Java

| Symptom | Common cause | Where to check |
|---|---|---|
| Azure Repos PR does not trigger | Only YAML `pr:` configured, missing Build Validation | Branch Policies on `main` |
| Push does not run CI | Branch/path filter or pipeline disabled | YAML trigger, pipeline settings |
| Job stays queued | Insufficient hosted parallelism/agent capacity | Agent pools and queue |
| Agent lacks JDK 21 | Image updated or self-hosted missing JDK | JavaToolInstaller/agent capabilities |
| Maven "release version not supported" | Build JDK older than compiler release | `java -version` and Maven runtime |
| Maven Wrapper fails to run | Script/file permissions/distribution download | `mvnw`, wrapper properties |
| Gradle Wrapper permission denied | `gradlew` not executable | Git executable bit or bash wrapper |
| Maven dependency 401 | Wrong feed auth/server ID | `MavenAuthenticate`/feed ACL |
| Maven dependency 403 | Insufficient feed permission/scope | Project/Collection Build Service identity |
| Dependency checksum mismatch | Corrupt cache/mirror or tampering | Repository integrity, cache policy |
| Tests do not run | Wrong Surefire/Failsafe/Gradle task config | Test discovery, skip flags |
| Tests fail | Bug, flaky test, or environment issue | JUnit XML, failure logs |
| JUnit reports missing | Wrong paths or tests did not run | `target/surefire-reports`, `build/test-results` |
| JaCoCo XML missing | Plugin/report goal did not run | POM/Gradle configuration |
| JAR staging empty | Wrong directory/module/packaging | `target`, `build/libs`, and CopyFiles |
| Artifact is plain JAR instead of boot JAR | Wrong copy glob | Boot plugin output/convention |
| PublishPipelineArtifact unsupported | Server/task compatibility | Azure DevOps Services vs. Server |
| Disk full | Testcontainers, cache, Docker layers | Agent disk space |
| Maven/Gradle OOM | JVM heap/agent RAM | `MAVEN_OPTS`/Gradle JVM config |
| Slow build | Cache miss, tests, network, queue | Timeline, cache logs |
| Testcontainers fail | Docker runtime/socket/privileges | Agent capabilities |
| TLS/proxy errors | Networking or trust roots | Egress/proxy/CA configuration |
| Pipeline green despite test failure | `continueOnError` or skip flags | Task conditions/POM |
| Secret exposed in logs | Script echo/wire logging | Incident triage + rotation |
| CD picks wrong JAR | Wrong artifact/run selection | Run ID/source SHA/approval |

### 25.1. JDK errors

~~~text
Fatal error compiling: error: release version 21 not supported
~~~

Investigate:

1. `java -version` in the same job.
2. `bash ./mvnw --version` to see the JVM Maven actually uses.
3. Maven compiler `release`/`source`/`target` and plugin config.
4. `JavaToolInstaller@0` inputs and agent image support.
5. Toolchains file if the project uses multiple JDKs.
6. Runtime compatibility after deployment.

Do not downgrade the compiler release just to pass the build if the source code relies on Java 21 APIs.

### 25.2. Missing JUnit XML

- Build failed before the `test` phase, so no report exists.
- Tests were disabled with **-DskipTests** or build config.
- Surefire missed test classes due to naming conventions.
- Failsafe did not bind `integration-test`/`verify` goals.
- Gradle test task was skipped by condition or cache.
- Multi-module reports live in module subdirectories.
- `PublishTestResults` searched the wrong root path.

**A pipeline with zero tests** is unlikely to satisfy quality gates. Production services need explicit checks rather than passing silently on empty reports.

### 25.3. Publish artifact has no JAR

If a Maven project is a **parent with packaging=pom**, there is no root `target` JAR. If Spring Boot produces a **plain.jar** alongside **bootJar**, an overly broad glob may copy both. Check artifact count, path, and checksum before Publish. Never mask CopyFiles failures with `condition: always()`.

### 25.4. Failures after a hosted image upgrade

**ubuntu-latest** can be updated by Microsoft. Log JDK/Maven/Gradle versions and agent image metadata inside jobs. On regression:

- Reproduce on both old and new images among supported versions.
- Pin toolchains with wrappers and explicit JDK versions.
- Check TLS/CAs, Docker/Testcontainers, and distro packages.
- Use a controlled container job image when necessary.
- Do not stay pinned to an end-of-life/unpatched image indefinitely just to keep CI green.

### 25.5. Private feed errors are unrelated to Azure subscription RBAC

**App Service Contributor** or **Key Vault Secrets User** does not grant Azure Artifacts feed read access. For dependency 401/403 errors, verify feed URL, server ID, job identity, permissions, and `MavenAuthenticate` rather than elevating Azure subscription roles.

### 25.6. Security scan errors

SCA/security scanners may fail due to external service timeouts or missing tokens rather than actual vulnerabilities. Distinguish:

- **Scan complete, critical finding** → fail gate per policy.
- **Scanner unavailable** → fail closed or require an approved waiver; never auto-pass.
- **False positive** → triage with evidence, owner, and expiration.
- **Dependency inaccessible** → inspect repo/feed network; do not switch to an untrusted mirror.

## 26. Observability and run health

### 26.1. Useful metrics

| Metric | Question to answer |
|---|---|
| Pipeline success rate | Are `main`/PR runs stable? |
| Build queue time | Are delays caused by insufficient agent capacity? |
| Checkout time | Is repo/LFS network a bottleneck? |
| Cache hit ratio | Is caching reducing dependency downloads? |
| Maven/Gradle build duration | Which compiler/plugins are slow? |
| Unit/integration test duration | Which suite drives feedback latency? |
| Flaky test rate | Is validation trustworthy? |
| Coverage/quality-gate trends | Are changes eroding verification? |
| Artifact size/digest | Any packaging anomalies? |
| Time to first PR feedback | How long do developers wait? |
| Time to approved build artifact | How long is the release cycle? |
| Agent minutes/parallel jobs | What is compute/cost utilization? |
| Role/connection policy changes | Any signs of privilege creep? |

The Azure DevOps UI surfaces logs, timelines, test results, and run details. Some aggregate metrics must be collected via APIs, dashboards, or external telemetry.

### 26.2. Example build timeline

~~~text
09:00 Commit pushed
09:01 Run queued
09:03 Agent allocated
09:04 Checkout finished
09:05 JDK 21 configured
09:06 Dependency cache restored
09:12 Maven verify completed
09:13 JUnit/coverage published
09:14 JAR checksum and artifact publish finished

Queue time: 2 min
Execution time: 11 min
End-to-end feedback: 14 min
~~~

**Numbers are hypothetical**, not an Azure Pipelines SLA. The key is separating queue wait from compile/test/scan duration so you optimize the actual bottleneck.

### 26.3. Safe metadata logging

~~~json
{
  "event": "JAVA_CI_BUILD",
  "service": "orders-api",
  "runId": "1428",
  "sourceCommit": "abcdef123",
  "jdk": "21",
  "buildTool": "Maven Wrapper",
  "tests": "PASSED",
  "artifact": "orders-api-java",
  "durationSeconds": 640
}
~~~

Never log PATs, secret variables, private feed tokens, access tokens, connection strings, sensitive customer fixtures, or raw Authorization headers. Even non-secret source metadata may be subject to data classification.

### 26.4. When to alert?

- Consecutive red `main` CI runs or required PR validation failing to trigger.
- Agent queue time exceeds feedback SLO.
- Missing test reports while the pipeline still reports green.
- Missing artifacts or checksum mismatches.
- Critical dependency CVE or secret scan alerts.
- Unauthorized expansion of service connection or variable group permissions.
- Build artifacts purged by retention before CD consumes them.
- Hosted image or toolchain updates causing widespread regressions.

Alerts need an owner/on-call rotation and a runbook; avoid sending the same alert from 5 systems and causing alert fatigue.

## 27. Build performance and cost

### 27.1. Cost drivers

| Component | Factors |
|---|---|
| Microsoft-hosted agents | Parallel jobs, job minutes, and plan/entitlements |
| Self-hosted agents | VM/OS/disk/network, operations, updates, security |
| Artifact storage/retention | JAR size, reports, pipeline artifacts, and policy |
| Azure Artifacts | Feed/storage limits, retention, and usage |
| Security scanners | Tool licenses, external services, compute/time |
| Testcontainers | Docker resources and test duration |
| Private network | Egress/proxy/networking for self-hosted agents |
| Container image builds | Build compute, registry/storage/push operations |
| Logs/monitoring | Retention and export per plan |
| Reviewer/developer wait time | Feedback latency, reruns, flaky tests |

No fixed unit prices are cited because Azure DevOps plans, hosted parallelism, and billing terms vary; consult your organization's active licensing/cost policy.

### 27.2. Build minutes calculation

Assumptions:

~~~text
30 PRs/day
2 validation runs/PR (8 minutes each)
4 main branch builds/day (12 minutes each)

PR agent minutes = 30 × 2 × 8 = 480
Main agent minutes = 4 × 12 = 48
Total = 528 agent minutes/day
~~~

If each PR automatically runs a **JDK 17 + 21 matrix** across two agents, total minutes nearly double before accounting for queue or cache variations. **Parallel jobs** reduce wall-clock feedback time but consume multiple agent slots concurrently.

### 27.3. Optimizing bottlenecks one by one

- Increase **cache hit rates** without caching secrets or build outputs.
- Use Maven/Gradle Wrapper to minimize drift.
- Add matrix builds only when compatibility requires them.
- Keep unit tests fast on PRs; run integration/nightly suites under a risk-based policy.
- Fix flaky tests instead of retrying endlessly.
- Optimize test fixtures, DB startup, and Testcontainers.
- Split jobs only when it meaningfully shortens the critical path and agent capacity permits.
- Use path filters carefully; never exclude shared build or security files.
- Prune unneeded artifacts via retention while preserving approved release artifacts.
- Pin toolchains proactively instead of being surprised by hosted image shifts.

### 27.4. Caching can slow builds down

If a Maven repository is small while the cached archive is huge, restore/save time can exceed direct downloads. Measure **Cache@2 hit/miss/download/save duration** alongside dependency resolution time. Never assume caching always improves speed.

### 27.5. Cost spikes from pipeline failures

A malicious PR can spawn infinite scripts or download massive data without timeouts, egress limits, and permission controls. Enforce:

- Job timeouts and cancellation policies.
- Parallelism and budget caps.
- Resource quotas.
- Repo permissions and branch policies.
- Network and credential scoping.
- Build artifact size and retention limits.

## 28. Runbook for a failed Java build

Workflow for SREs/developers:

1. Identify **pipeline ID, run ID, source commit, branch, and PR**.
2. Open the first failing job/stage; distinguish infrastructure failures from code failures.
3. Identify the agent image, JDK, and Maven/Gradle versions.
4. Read the specific error rather than just the final "Job failed" line.
5. For dependency errors, check repository, feed, auth, and network.
6. For compile failures, check JDK, target release, sources, and annotation processors.
7. For test failures, inspect JUnit XML and related logs.
8. For scan failures, distinguish real findings from scanner unavailability.
9. For packaging failures, inspect POM/Gradle plugins and output paths.
10. For Publish failures, check staging paths, permissions, and task support.
11. Preserve logs/metadata for investigation; never paste credentials into tickets.
12. Reproduce locally with the matching wrapper and JDK if possible.
13. Open a fix PR and pass required validation; do not bypass branch policy.
14. Once green, inspect the artifact/run SHA and run a postmortem if multiple services were impacted.
15. If compromise is suspected, contain credentials/agents and preserve evidence before retrying.

### 28.1. Do not just click Retry

Retries can help with transient outages (feed 503 or agent blip), but if code fails to compile or a vulnerability gate fails, retrying fixes nothing. When failures stem from a malicious PR, rerunning on a privileged agent increases exposure.

### 28.2. Regression from Maven Wrapper

If a PR modifies the wrapper distribution URL, treat it as changing an executable supply-chain input. Never allow the pipeline to fetch Maven from an unknown domain just to pass the build; inspect source, checksums, and commit history.

### 28.3. Recovery when an artifact has expired

If an approved release artifact was purged, do not arbitrarily deploy a similarly named JAR from another run. Check retention/registry, provenance, signatures, and policy; if rebuilding is required, run a **new fully validated build** and clearly record that it is a new artifact—never claim it is byte-identical without verification.

## 29. End-to-end lab: building CI for Orders API

These instructions are for an **approved Azure DevOps lab project/repository**, not actions executed while writing this lesson.

### 29.1. Preparation

- Have an Azure DevOps organization/project with permission to create pipelines and read repos.
- Have a Java 21 Maven Spring Boot project with **pom.xml**, **mvnw**, **mvnw.cmd**, and tests.
- Use sample data only; include no production secrets.
- Be able to run Maven Wrapper locally.
- Have Microsoft-hosted agent entitlement/parallel jobs or a lab self-hosted agent.
- Identify the source provider: Azure Repos Git or GitHub.
- Have permission to configure branch policies if enforcing mandatory PR validation.
- If using a private feed, ensure an operator has granted read access to the pipeline identity.
- Do not create production service connections for this lab.

### 29.2. Standardize the project locally

In the lab repo checkout:

~~~bash
java -version
bash ./mvnw --version
bash ./mvnw -B -ntp clean verify
~~~

Verify:

1. JDK target matches the POM.
2. Maven Wrapper distribution is valid.
3. At least one unit test with assertions exists.
4. **target/surefire-reports/TEST-*.xml** is generated.
5. A deployable **target/*.jar** exists for a single-module project.
6. No credentials exist in source, POM, or test fixtures.
7. The build does not depend on settings specific to one developer's laptop.

### 29.3. Add `azure-pipelines.yml`

Copy and adapt the example from Section 8:

- Adjust the JDK version for the project.
- Keep **checkout self** and versioned source.
- Use either Maven Wrapper or `Maven@4` per policy—never both unnecessarily.
- Configure cache with the exact path and key.
- Run **clean verify**.
- Publish test results even if tests fail.
- Verify the JAR exists and avoid confusing sources/plain JARs.
- Publish the Pipeline Artifact named **orders-api-java**.

### 29.4. Run the first build

1. Commit YAML to a lab branch.
2. Open **Pipelines → New pipeline** and select the repo/YAML.
3. Review the pipeline YAML from a trusted source.
4. Trigger a run within lab scope.
5. Inspect logs for `JavaToolInstaller`, `Cache`, `Maven`, `JUnit`, and Artifact Publish.
6. Verify the run ID and source commit.
7. Download the artifact, compute SHA-256, and compare against the digest in the logs.
8. Inspect the Tests tab and test outcomes.
9. If tests fail, confirm the pipeline fails and the artifact is not published as an approved release.

### 29.5. Test PR validation

If using **Azure Repos Git**:

1. Open **Repos → Branches → main → Branch policies**.
2. Add **Build validation** for the pipeline.
3. Set it to Required per lab policy.
4. Open a PR with an intentionally failing test in the authorized test environment.
5. Observe red build validation and verify merging is blocked.
6. Fix the test in the PR, rerun validation, and confirm green.
7. Never bypass policies just to test "whether merge works" on a shared repository.

For GitHub, verify the YAML **pr** trigger and required GitHub checks/branch protection per integration. Do not apply Azure Repos branch policy UI concepts to GitHub as if they share one UI.

### 29.6. Test caching

1. Run the pipeline the first time and record dependency download / cache miss duration.
2. Rerun with the same source/toolchain and observe cache hit/restore.
3. Measure total `Maven verify` duration.
4. Modify the POM in a lab PR and observe the cache key change.
5. Confirm full tests still run despite a cache hit.
6. Verify the cache contains no `settings.xml` or tokens.

### 29.7. Test JDK mismatch

In a lab branch, change the JDK selector to a version incompatible with the POM and observe compiler errors. Restore the proper JDK afterward; do not downgrade the Java target if the project genuinely uses newer APIs. This negative test teaches toolchain debugging.

### 29.8. Test artifact traceability

Sample lab report:

| Item | Illustrative value |
|---|---|
| Repo | orders-api |
| Pipeline | orders-api-ci |
| Run ID | 1428 |
| Commit SHA | abcdef123 |
| JDK | 21 |
| Maven | Wrapper pinned |
| Compile | PASS |
| Unit tests | 42 passed |
| Coverage | JaCoCo report when configured |
| Artifact | orders-api-java |
| Checksum | recorded SHA-256 |
| Secret exposure | none observed |
| PR validation | Required on main |
| Deploy production | Not attempted |

**All numbers and IDs are examples**. In a real lab, record values from actual runs—never copy this table as real test evidence.

### 29.9. Completion criteria

The lab passes when:

- YAML is reviewed and executed cleanly from the repo.
- Builds use an explicit JDK/toolchain.
- Maven/Gradle compiles, runs unit tests, and executes POM/Gradle quality gates.
- Failing tests fail the build and produce JUnit reports.
- Artifacts carry checksums, run IDs, and commit provenance.
- Required PR build validation works with the actual provider.
- No PATs, secrets, or production service connections exist in PR jobs.
- No artifact is published as an approved release when tests fail.
- Logs/metadata suffice for debugging and estimating agent minutes.

## 30. Anti-patterns to avoid

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Build JAR on laptop and send manually | Unknown commit/toolchain/tests | Reproducible Azure Pipeline CI |
| Rely on default `ubuntu-latest` JDK unchecked | Image updates break compilation | Explicit JDK + wrapper |
| Build with `-DskipTests` | Buggy PRs turn green | `clean verify`, required tests |
| Run `package` assuming integration tests ran | Missing quality gates | Configure Surefire/Failsafe properly |
| Publish JAR from root `target` in multi-module | Empty/wrong module artifact | Select exact module path |
| Publish every JAR in the repo | Copies library/sources/test jars | Validate artifact count/type |
| Cache `target` or `build/libs` | Stale artifacts | Cache only controlled dependencies |
| Cache credential files | Secret leakage | Separate credentials from cache |
| Use uncontrolled SNAPSHOTs in releases | Non-reproducible builds | Immutable versions |
| Give PR jobs production secrets | PR script exfiltration | Separate untrusted/privileged jobs |
| Use long-lived PATs for private feeds | Hard rotation / large blast radius | Feed identity + `MavenAuthenticate` |
| Allow all pipelines to use service connections | Privilege abuse | Resource authorization |
| Have `pr:` YAML without Azure Repos Build Validation | PRs are not blocked from merging | Required branch policy |
| Path filters omit shared build files | Security checks skipped | Include all build-affecting paths |
| Click Retry 10 times for flaky tests | Masks test instability | Fix root cause, deterministic fixtures |
| `continueOnError` on dependency scan | Releases ship critical CVEs | Enforce security gate |
| Print tokens in logs to debug 401 | Credentials exposed | Sanitized auth diagnostics |
| Run `curl \| bash` from unknown sources | Supply-chain RCE | Pin + verify trusted installers |
| Trust artifacts solely via SHA-256 | Attacker swaps both hash and binary | Signing/provenance |
| Download "latest artifact" at deploy time | Wrong branch/run | Approved run and digest |
| Rebuild in production | Deployed artifact differs from tested one | Build once, deploy many |
| Grant Owner to build job just to compile Java | Excessive privilege | No Azure subscription rights for pure builds |
| Run fork PRs on self-hosted release agents | Agent/secret compromise | Isolated agents |
| Retain all artifacts forever without policy | Cost/storage/compliance issues | Retention + approved release preservation |
| Run builds with no one watching failures | `main` stays broken | Required checks + alerts |

## 31. Production checklist for Java CI

### 31.1. Repository and triggers

- [ ] Pipeline YAML lives in the repository and code owners review changes.
- [ ] Repo/build wrappers/POM/Gradle scripts are treated as executable inputs.
- [ ] CI triggers cover the right branches and path filters do not omit shared build files.
- [ ] Azure Repos `main` has **Required Build Validation branch policy** when using Azure Repos.
- [ ] GitHub required checks are configured when sourcing from GitHub.
- [ ] Fork PR jobs have no production credentials or privileged network access.
- [ ] Repo settings prohibit arbitrary bypasses or audit any bypasses.
- [ ] Build cancellation, timeout, and retry policies are defined.

### 31.2. JDK and build tooling

- [ ] JDK version is explicit and matches project target/runtime.
- [ ] Maven/Gradle Wrapper version and checksum are verified.
- [ ] Agent image and tool versions are recorded in metadata.
- [ ] Builds run **clean verify** or **clean build/check** with tests.
- [ ] POM/Gradle plugins are pinned; dependencies use approved BOMs/lockfiles.
- [ ] Builds do not depend on tools manually installed on developer laptops.
- [ ] Multi-module paths are verified accurately.
- [ ] A runbook exists for hosted agent image updates.
- [ ] Self-hosted agents are patched and isolated if used.

### 31.3. Tests and quality gates

- [ ] Real unit tests exist and output JUnit XML.
- [ ] Missing test reports do not silently pass required suites.
- [ ] Integration tests are configured separately with clear ownership.
- [ ] Testcontainers/lab credentials never touch production.
- [ ] Coverage reports are published when JaCoCo is configured.
- [ ] Coverage thresholds act as real gates, not just reports.
- [ ] Static, security, dependency, and license scans run per policy.
- [ ] Critical findings are never hidden behind `continueOnError`.
- [ ] Flaky tests have quarantine owners and timebound fixes.
- [ ] CI is green only when all required gates pass.

### 31.4. Artifacts and supply chain

- [ ] Artifact count, name, binary type, and size are validated.
- [ ] Pipeline Artifacts are published only after build/test success.
- [ ] Run ID, commit, toolchain, and SHA-256 are recorded.
- [ ] SBOM/provenance/signatures are generated when release policy requires them.
- [ ] No secrets are committed or published into artifacts or logs.
- [ ] Downstream CD selects artifacts from **approved runs**, never an arbitrary `latest`.
- [ ] Release artifact retention supports rollback requirements.
- [ ] SCA verifies dependencies and approved plugin repositories.
- [ ] Untrusted install scripts are prohibited.
- [ ] A response process exists for compromised build credentials or artifacts.

### 31.5. IAM, secrets, network, and FinOps

- [ ] Pure Java builds hold no unnecessary Azure subscription privileges.
- [ ] Feed read permissions are scoped accurately.
- [ ] Build identity is separated from release/deployment identity.
- [ ] Service connections and variable groups enforce resource authorization and checks.
- [ ] OIDC federation is preferred over long-lived secrets where supported.
- [ ] Tokens, PATs, and Authorization headers are never printed.
- [ ] Caches never contain credentials.
- [ ] Agents enforce outbound network and permission boundaries by trust level.
- [ ] CI queue, build, and test durations have dashboards and owners.
- [ ] Alerts exist for failing `main`, blocked security gates, and missing artifacts.
- [ ] Agent minutes/parallelism, cache efficiency, and artifact retention are measured.
- [ ] Required tests and security gates are never disabled purely to save cost.
- [ ] Pipeline secrets and access logs have an incident response plan.

## 32. Practice exercises

### Exercise 1: Trace the artifact path

Diagram the flow from commit to JAR, labeling **agent, JDK, Maven, JUnit, JaCoCo, artifact store, and source SHA** at each step. Explain the role of CI versus CD.

### Exercise 2: Maven YAML

Based on the example in Section 8:

1. Select JDK 17 instead of 21 for a Java 17 project.
2. Add Maven Wrapper.
3. Enable `Cache@2`.
4. Run `clean verify`.
5. Publish JUnit reports.
6. Fail if no JAR or required tests are missing.
7. Publish an unambiguously named artifact.

### Exercise 3: Gradle YAML

Write an equivalent pipeline for Gradle Wrapper including `clean build`, JUnit XML, and selecting only the proper boot JAR. Explain what happens when a project produces both `plain.jar` and `bootJar`.

### Exercise 4: Azure Repos PR validation

A repo has `pr` YAML yet PRs into `main` do not trigger builds. Diagnose the root cause, configure **Required Branch Policy Build Validation**, test a failing test, and verify merging is blocked.

### Exercise 5: Private Maven feed 401

A pipeline cannot resolve **com.company.shared:common-auth**. Build a runbook checking repository URL, POM server ID, `MavenAuthenticate` task, build identity/feed ACLs, and egress—without committing a PAT.

### Exercise 6: Cache poisoning

Suppose a broad cache key lets an untrusted PR run store a tampered dependency. Propose how to isolate trust boundaries, version cache keys, verify dependency integrity, and protect release builds.

### Exercise 7: JaCoCo quality gate

Configure JaCoCo `report` and `check` for Maven, introduce a failing test or drop coverage, and confirm **CI turns red**. Explain why running `PublishCodeCoverageResults` alone does not block merges.

### Exercise 8: Multi-module Maven

A project contains `common-model`, `common-security`, and `orders-api`. Update the pipeline to build the reactor, test shared modules, and publish only the **orders-api executable JAR**. Write explicit artifact count validation.

### Exercise 9: Malicious PR in POM

A PR adds a Maven plugin that reads environment variables. Identify the controls preventing this job from obtaining production secrets even if a reviewer misses it.

### Exercise 10: JDK matrix

A library must support JDK 17 and 21. Design matrix jobs, compare agent minutes against a single-JDK pipeline, and evaluate whether the quality/cost trade-off is justified.

### Exercise 11: Artifact provenance

From run ID, commit SHA, Maven/JDK versions, test status, and JAR checksum, construct a release manifest. Explain why a hash does not replace a digital signature.

### Exercise 12: Flaky integration tests

A Testcontainers test fails intermittently due to race conditions or networking. Design test isolation, fixtures, timeouts, logging, and a flaky-test policy without infinite retries.

### Exercise 13: Source trust and service connections

Design the separation between PR builds, trusted post-merge publishing, and approved Azure deployments. Specify identity permissions, which jobs receive secrets, and what prevents PRs from using production credentials.

### Exercise 14: Agent capacity and FinOps

Given 30 PRs/day, two runs/PR at 8 minutes each, and 4 `main` builds/day at 12 minutes each, verify the **528 agent minutes/day** calculation and analyze the impact of adding a JDK matrix or parallel tests.

### Exercise 15: Troubleshooting missing artifacts

Maven `verify` passes, yet `PublishPipelineArtifact` finds no JAR. Check project packaging, multi-module paths, Spring Boot repackaging, `CopyFiles` patterns, and fail-if-empty validation.

### Exercise 16: Build compromise tabletop

SOC detects the Maven Wrapper distribution URL was changed to an unfamiliar domain in a pipeline carrying secret variables. Create a response plan: cancel runs, revoke credentials, quarantine agents, preserve logs, audit artifact provenance, rotate keys, and add regression controls.

## 33. Self-check questions

1. Which Azure DevOps product does Azure Pipelines belong to?
2. How does an organization differ from a project and a pipeline?
3. What are an agent and an agent pool?
4. How does a job differ from steps/tasks and stages?
5. How does CI scope differ from CD scope?
6. Why should you build once and deploy many times?
7. How does Maven **verify** differ from **package** and **deploy**?
8. What problem does Maven Wrapper solve?
9. How does Gradle Wrapper differ from system-installed Gradle on an agent?
10. How do build JDK, runtime JDK, and compiler target release differ?
11. Is **ubuntu-latest** an immutable image?
12. What does `JavaToolInstaller@0` do?
13. How does the `Maven@4` task differ from Bash + Maven Wrapper?
14. What does **Cache@2** typically store?
15. Does a cache hit guarantee dependencies are safe?
16. Why should you never cache Maven `settings.xml` containing credentials?
17. Why should you never cache **target/** and publish the JAR from it?
18. Which test types do Maven Surefire and Failsafe normally run?
19. Where are JUnit XML files usually located in Maven and Gradle?
20. Why does `PublishTestResults` run with `succeededOrFailed`?
21. Why should missing required test reports fail the pipeline?
22. Does `PublishCodeCoverageResults` enforce thresholds by itself?
23. What is required for JaCoCo `check` to fail on a threshold?
24. What does `PublishPipelineArtifact` do that `CopyFiles` does not?
25. In a two-stage pipeline, why must downstream jobs download the artifact?
26. How does an artifact checksum differ from a digital signature?
27. What do **Build.SourceVersion** and **Build.BuildId** represent?
28. Can an artifact be produced by an unapproved PR run?
29. Why should you not fetch the "latest artifact" to deploy automatically to production?
30. How do YAML **pr** triggers behave with Azure Repos Git?
31. Where is required Azure Repos build validation configured?
32. Why can path filters in a monorepo introduce gaps?
33. How must artifact paths be adjusted in multi-module Maven builds?
34. What do Maven **-pl** and **-am** flags solve?
35. How does Gradle **bootJar** differ from a library JAR?
36. Why are pipeline YAML, POMs, and wrappers all executable code?
37. Should an untrusted PR job read production secrets?
38. How does a job access token differ from an Azure Resource Manager service connection?
39. Can an Azure Artifacts feed 401/403 error be fixed by granting Azure Contributor?
40. What does `MavenAuthenticate@0` do?
41. Can secrets in a variable group protect against a malicious build script?
42. Which credential type does workload identity federation eliminate?
43. What is an SBOM? Does it guarantee the absence of malware?
44. What does provenance/attestation need in order to be trustworthy?
45. Which threats do SLSA-style controls target?
46. When should you use a self-hosted agent?
47. What risks arise from running fork PRs on a self-hosted release agent?
48. Why should a flaky test not be permanently ignored?
49. How should build success rate and queue time be measured differently?
50. How can you reduce agent minutes without removing required quality gates?

## 34. References

- [Azure Pipelines documentation — Microsoft Learn](https://learn.microsoft.com/azure/devops/pipelines/)
- [Build Java apps with Azure Pipelines](https://learn.microsoft.com/azure/devops/pipelines/ecosystems/java)
- [Build and deploy with Maven](https://learn.microsoft.com/azure/devops/pipelines/ecosystems/maven)
- [Build Java apps with Gradle](https://learn.microsoft.com/azure/devops/pipelines/ecosystems/gradle)
- [Azure Pipelines YAML schema](https://learn.microsoft.com/azure/devops/pipelines/yaml-schema/)
- [YAML pipeline triggers](https://learn.microsoft.com/azure/devops/pipelines/build/triggers)
- [Configure CI triggers](https://learn.microsoft.com/azure/devops/pipelines/repos/azure-repos-git)
- [Azure Repos branch policies](https://learn.microsoft.com/azure/devops/repos/git/branch-policies)
- [Microsoft-hosted agents](https://learn.microsoft.com/azure/devops/pipelines/agents/hosted)
- [Self-hosted agents](https://learn.microsoft.com/azure/devops/pipelines/agents/agents)
- [Azure Pipelines tasks reference](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/)
- [Maven@4 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/maven-v4)
- [JavaToolInstaller@0 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/java-tool-installer-v0)
- [Gradle task reference](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/gradle-v3)
- [Cache@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/cache-v2)
- [Pipeline caching](https://learn.microsoft.com/azure/devops/pipelines/release/caching)
- [PublishTestResults@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-test-results-v2)
- [PublishCodeCoverageResults@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-code-coverage-results-v2)
- [PublishPipelineArtifact@1 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-pipeline-artifact-v1)
- [DownloadPipelineArtifact@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/download-pipeline-artifact-v2)
- [Pipeline Artifacts](https://learn.microsoft.com/azure/devops/pipelines/artifacts/pipeline-artifacts)
- [Azure Pipelines expressions and conditions](https://learn.microsoft.com/azure/devops/pipelines/process/conditions)
- [Azure Pipelines variables](https://learn.microsoft.com/azure/devops/pipelines/process/variables)
- [Azure Pipelines templates](https://learn.microsoft.com/azure/devops/pipelines/process/templates)
- [Azure Pipelines security](https://learn.microsoft.com/azure/devops/pipelines/security/overview)
- [Secure access to repositories](https://learn.microsoft.com/azure/devops/pipelines/security/secure-access-to-repos)
- [Azure service connections](https://learn.microsoft.com/azure/devops/pipelines/library/service-endpoints)
- [MavenAuthenticate@0 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/maven-authenticate-v0)
- [Azure Artifacts Maven packages](https://learn.microsoft.com/azure/devops/artifacts/maven/)
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/)
- [Gradle Java plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Maven build lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [JaCoCo Maven Plugin](https://www.jacoco.org/jacoco/trunk/doc/maven.html)
- [CycloneDX documentation](https://cyclonedx.org/docs/)
- [SLSA supply chain security framework](https://slsa.dev/)
- [Azure DevOps pricing](https://azure.microsoft.com/pricing/details/devops/azure-devops-services/)
