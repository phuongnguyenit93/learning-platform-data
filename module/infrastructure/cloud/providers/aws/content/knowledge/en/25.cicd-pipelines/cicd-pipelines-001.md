# Designing Build, Test, Release, and Rollback Pipelines

A development team can finish a feature in a few hours, but getting that change to production requires many steps: fetching source code, building the artifact, running tests, scanning for vulnerabilities, packaging the container, deploying to a test environment, waiting for approval, and releasing in a controlled manner. If each release has to be done manually, the process is prone to skipping steps, hard to repeat, and makes it difficult to know exactly which version is running.

**CI/CD (Continuous Integration / Continuous Delivery or Deployment)** automates the path from source code to the runtime environment. On AWS, a pipeline typically combines **AWS CodePipeline** to orchestrate stages/actions, **AWS CodeBuild** to build/test, **Amazon ECR** to store container images, **Amazon S3** as the artifact store, and **AWS CodeDeploy/CloudFormation/ECS/Lambda/EKS** to deploy. The pipeline also needs IAM roles, KMS encryption, approvals, monitoring, and rollback.

This lesson belongs to the **CI/CD on AWS** chapter of the **CLOUD_PROVIDERS_AWS** module. The content connects the release process with Region/AZ, IAM, VPC, compute, storage, database, integration, and serverless; the goal is to build pipelines that are secure, observable, recoverable, and cost-controlled.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish between Continuous Integration, Continuous Delivery, and Continuous Deployment.
2. Design a pipeline across stages from source, build, test, security scan, artifact, deploy, to verify.
3. Choose AWS CodePipeline, CodeBuild, CodeDeploy, ECR, S3, CodeArtifact, and CloudFormation according to the task.
4. Design immutable artifacts, versioning, image digests, and promotion across environments.
5. Configure buildspec, test reports, caching, and the build environment.
6. Use IAM roles, AWS CodeConnections, OIDC federation, and cross-account roles instead of long-lived access keys.
7. Deploy applications to ECS, EKS, Lambda, and infrastructure with CloudFormation/CDK/SAM.
8. Choose rolling, blue/green, canary, or linear deployment according to availability requirements.
9. Set up manual approvals, automated gates, CloudWatch alarms, and rollback.
10. Monitor pipeline executions, logs, deployment events, audit trails, and costs.
11. Troubleshoot build failures, test failures, deployment failures, rollback failures, and artifact mismatches.

## 2. CI, Continuous Delivery, and Continuous Deployment

These three related concepts differ as follows:

| Concept | Meaning | Decision point |
|---|---|---|
| **Continuous Integration (CI)** | Every change is integrated frequently, built, and tested automatically | Automatically verifies source quality |
| **Continuous Delivery** | Artifacts are always in a releasable state after checks; production release may require approval | Humans/processes decide when to release to production |
| **Continuous Deployment** | Changes that pass all gates are automatically deployed into production | No manual approval required for each release |

Continuous Deployment does not mean deploying any commit immediately. It is only appropriate when tests, security gates, rollout controls, monitoring, and rollback are sufficiently reliable. For financial systems or workloads with mandatory change management, Continuous Delivery with approval can still be the appropriate choice.

### 2.1. A Pipeline Is a Directed Graph of Conditional Steps

A pipeline can run sequentially or in parallel. For example, unit tests, dependency scans, and IaC scans can run in parallel after source checkout; deployment only starts when all required gates pass.

~~~mermaid
flowchart TD
    SRC["Git commit / Pull request"] --> SOURCE["Source stage"]
    SOURCE --> BUILD["Build & package"]
    BUILD --> PARALLEL{"Quality gates"}
    PARALLEL --> UNIT["Unit / integration tests"]
    PARALLEL --> SAST["SAST / dependency scan"]
    PARALLEL --> IAC["IaC / container scan"]
    UNIT --> GATE["All required checks pass"]
    SAST --> GATE
    IAC --> GATE
    GATE --> ART["Publish immutable artifact"]
    ART --> TEST["Deploy test / staging"]
    TEST --> VERIFY["Smoke / contract / acceptance tests"]
    VERIFY --> APPROVE{"Production approval"}
    APPROVE -->|"Approved"| PROD["Production deployment"]
    APPROVE -->|"Rejected"| STOP["Stop / discard release"]
    PROD --> OBS["Observe health & metrics"]
    OBS --> RESULT{"Healthy?"}
    RESULT -->|"Yes"| DONE["Release complete"]
    RESULT -->|"No"| ROLLBACK["Rollback / traffic shift back"]
~~~

### 2.2. A Pipeline Must Have Clear Inputs and Outputs

| Input | Processing | Output |
|---|---|---|
| Git commit/tag | Checkout source, validate branch/tag | Immutable source revision |
| Maven/Gradle project | Compile, unit test, package | JAR/WAR |
| Dockerfile | Build image, scan, tag | Container image digest |
| CloudFormation/CDK/SAM template | Validate, lint, policy scan, change set | IaC artifact/change set |
| Release metadata | Attach version, commit SHA, build ID | Deployment manifest/SBOM |

A release must be traceable: **source commit → build execution → test reports → artifact digest → deployment execution → runtime version**.

## 3. Common CI/CD Architecture on AWS

An AWS-native pipeline typically uses:

| Service | Primary role |
|---|---|
| **AWS CodePipeline** | Orchestrates stages, actions, artifacts, approvals, and triggers |
| **AWS CodeBuild** | Builds, runs unit/integration tests, packages, lints, and scans |
| **AWS CodeConnections** | Connects source providers such as GitHub/GitLab/Bitbucket as supported |
| **Amazon S3** | Artifact store for CodePipeline and build outputs |
| **AWS KMS** | Encrypts the artifact store and resources supporting encryption |
| **Amazon ECR** | Stores container images, handles image scanning and lifecycle |
| **AWS CodeDeploy** | Deployment orchestration for EC2/on-premises, ECS blue/green, and Lambda |
| **AWS CloudFormation** | Provisions/updates infrastructure and change sets |
| **AWS CodeArtifact** | Stores internal package dependencies such as Maven/npm/PyPI |
| **Amazon CloudWatch** | Logs, metrics, alarms, and deployment health signals |
| **AWS CloudTrail** | Audits API calls/control-plane events according to configuration |

~~~mermaid
flowchart LR
    GIT["Git provider"] --> CP["CodePipeline"]
    CP --> CB["CodeBuild<br/>Build / Test / Scan"]
    CB --> ART["S3 artifact store"]
    CB --> ECR["Amazon ECR<br/>Image digest"]
    ART --> TEST["Test / Staging deploy"]
    ECR --> TEST
    TEST --> GATE["Approval / quality gate"]
    GATE --> PROD["Production deploy"]
    PROD --> CD["CodeDeploy / ECS / Lambda / EKS"]
    PROD --> CFN["CloudFormation / CDK"]
    CD --> CW["CloudWatch alarms"]
    CFN --> CW
    CP --> CT["CloudTrail audit"]
~~~

Not every project has to use all services. For example, a Java application running on ECS can use CodePipeline + CodeBuild + ECR + ECS deploy action; a Lambda application can use CodeBuild + SAM/CloudFormation + Lambda deployment preferences/CodeDeploy; an EKS GitOps team can use a pipeline to update manifests/Helm charts in a deployment Git repository.

## 4. Choosing a Pipeline Model and Tooling

### 4.1. CodePipeline or GitHub Actions?

CodePipeline fits when an organization wants AWS-native deployment orchestration, integration with IAM/CloudFormation/ECS/CodeDeploy, and artifact management inside AWS. GitHub Actions fits when source, pull requests, and workflow engineering are centered on GitHub; it can assume an AWS role via OIDC to deploy.

| Criterion | AWS CodePipeline | GitHub Actions |
|---|---|---|
| Orchestration | Stages/actions, execution modes, approvals | Workflows/jobs/steps |
| Source integration | CodeConnections, S3, CodeCommit as currently supported | GitHub native |
| AWS identity | Pipeline/service/action roles | OIDC assume role or credentials provider |
| Artifact storage | S3 artifact store | Workflow artifacts, ECR/S3, or package registries |
| AWS deployment | Native actions and integrations | AWS CLI/CDK/SAM/SDK and actions |
| Approval | Manual approval action | Environment protection rules/reviewers |
| Best fit | AWS-centric release orchestration | GitHub-centric CI/CD and multi-cloud |

Both options can be combined, but avoid creating two pipelines that deploy the same stack or update the same service without clear locking/ownership.

### 4.2. CodePipeline V1 and V2

CodePipeline has pipeline types with different capabilities and pricing. V2 adds support for triggers/filters and execution modes such as queued, superseded, or parallel as configured; V1 has different feature limitations. Choose the pipeline type based on concurrency, triggers, and current pricing requirements. Do not assume changing the type is just a metadata update with no behavioral impact.

### 4.3. One Large Pipeline or Many Small Pipelines?

Split pipelines when:

- Services have separate owners, release cadences, or rollback boundaries.
- Artifact/deployment targets differ.
- IAM permissions need to be scoped per service.
- One long pipeline causes queueing or a large blast radius.

Keep one pipeline when components must be released together and have a clear dependency/version contract. With a monorepo, path filters can be used to build/deploy only affected services, but shared libraries and the dependency graph must be controlled.

## 5. Source Stage and Version Management

The source stage determines which code enters the pipeline. Triggers can be commits, tags, pull requests, or schedules; validation workflows must be separated from production release workflows.

### 5.1. Branch and Tag Strategy

A simple model:

| Event | Pipeline behavior |
|---|---|
| Pull request | Build, unit tests, static analysis, IaC validation; do not deploy to production |
| Merge into main | Build artifact and deploy to integration/staging |
| Release tag vX.Y.Z | Create release candidate/production pipeline |
| Hotfix branch/tag | Controlled pipeline with separate approval and audit |

Branch protection requires reviews, status checks, and signed commits/tags if required by organizational policy. Do not allow a production pipeline to run automatically from arbitrary branches.

### 5.2. CodeConnections for GitHub

CodePipeline can connect to repositories via **AWS CodeConnections** (formerly named CodeStar Connections in older documentation/console). The connection must be created/authorized with the source provider; the pipeline role needs permission to use the connection ARN. Do not embed a Git personal access token in the buildspec or source repository.

### 5.3. Commit SHA and Source Revision

Each build should record:

- Repository and commit SHA.
- Branch/tag and pull request ID if applicable.
- Pipeline execution ID and CodeBuild build ID.
- Build timestamp and toolchain versions.
- Release version and artifact digest.

The `latest` tag is not sufficient to prove which artifact is running. Use immutable commit SHA/version tags and image digests.

### 5.4. Source Archive and Reproducibility

Builds should run on a specific source snapshot. Do not clone a mutable branch a second time between stages and accidentally build newer code than the initial source artifact. If the build depends on submodules, Git LFS, or generated files, pin versions explicitly and ensure they are checked out reproducibly.

## 6. Build Stage with AWS CodeBuild

CodeBuild runs build commands in a managed environment or a custom container image. A build project defines the source, environment image, compute, service role, environment variables, cache, artifacts, and logs.

### 6.1. Buildspec

A buildspec is a YAML file describing phases such as install, pre_build, build, post_build, artifacts, reports, and cache. You can place `buildspec.yml` at the root or specify another path in the project.

Java Maven example:

~~~yaml
version: 0.2

env:
  variables:
    MAVEN_OPTS: "-Dmaven.repo.local=.m2/repository"

phases:
  install:
    runtime-versions:
      java: corretto21
    commands:
      - java -version
      - mvn -version
  pre_build:
    commands:
      - echo "Validating source revision"
      - test -f pom.xml
  build:
    commands:
      - mvn -B clean verify
  post_build:
    commands:
      - echo "Build completed"

reports:
  junit-reports:
    files:
      - "**/surefire-reports/TEST-*.xml"
      - "**/failsafe-reports/TEST-*.xml"
    base-directory: target
    file-format: JUNITXML

artifacts:
  files:
    - target/*.jar
  discard-paths: yes

cache:
  paths:
    - ".m2/repository/**/*"
~~~

This is an example buildspec for Maven; verify supported runtime images and versions in CodeBuild before selecting `corretto21`. If the project uses Gradle, replace the commands and cache paths according to the Gradle wrapper/cache. Do not use `clean verify` if the project's build lifecycle has unintended side effects.

### 6.2. The Phases

| Phase | Work | Example |
|---|---|---|
| install | Install toolchain/runtime | JDK, Maven, Docker CLI |
| pre_build | Verify environment, log into registry, prepare config | ECR login, version metadata |
| build | Compile, test, package, container build | mvn verify, docker build |
| post_build | Publish, generate metadata, report status | Push image, write manifest |

### 6.3. Exit Codes Must Reflect True Results

If a test or scan fails, the build command must return a non-zero exit code so CodeBuild/CodePipeline marks the action as failed. Avoid writing shell scripts that always exit 0 or using `|| true` for mandatory security/test commands.

### 6.4. Test Reports

CodeBuild can collect test reports to display results and store reports. You should distinguish:

- Fast unit tests without real AWS dependencies.
- Integration tests using LocalStack or dedicated test accounts/resources.
- Contract tests verifying compatibility between services.
- End-to-end tests verifying critical business flows.
- Performance/load tests run in a controlled manner, not on every commit if cost is high.

## 7. Quality Gates and Security Checks

A pipeline is only valuable when gates reflect real risk. Do not lump everything into a single build command without saving results or knowing where failures occurred.

### 7.1. Recommended Check Suite

| Gate | Example tools/checks | Pass condition |
|---|---|---|
| Compile | Maven/Gradle | No compile errors |
| Unit test | JUnit, Mockito | All critical tests pass |
| Static analysis | SonarQube, Checkstyle, SpotBugs | Within quality threshold |
| Dependency scan | OWASP Dependency-Check, SCA service | No unresolved critical/high findings per policy |
| Secret scan | Git/provider scanning, gitleaks | No valid secrets detected |
| IaC scan | cfn-lint, cfn-guard, policy scanners | Valid template and policy compliant |
| Container scan | ECR image scanning or approved scanner | Vulnerability policy passes |
| SBOM | Syft/CycloneDX/Maven plugin | SBOM generated and attached to artifact |
| License check | Dependency/license policy | Dependency licenses approved |
| Integration tests | Test environment | Contract/API checks pass |

### 7.2. Scan Findings Need an Exception Process

A CVE might not be exploitable in the application or may not yet have a patch. Do not disable the entire scan when one finding causes a failure. Create an exception with an owner, rationale, expiry date, compensating controls, and remediation ticket; the pipeline should bypass only the approved finding per policy.

### 7.3. IaC Validation

Before deploying CloudFormation/CDK/SAM:

- Parse/validate the template.
- Lint resource properties and intrinsic functions.
- Check IAM wildcards, public exposure, and encryption requirements.
- Create a change set and review replacements/removals.
- Run CloudFormation Guard/policy-as-code checks if used by the organization.

A syntactically valid template does not guarantee a secure architecture. Change set review and policy checks complement each other.

### 7.4. Keep Secrets Out of Build Logs

Secrets should be retrieved from Secrets Manager/Parameter Store or CodeBuild secret-type environment variables with least privilege. Do not echo environment variables, enable shell tracing for commands containing secrets, or pass secrets via command-line arguments that are easily logged. Log masking is not an absolute guarantee; prevent secrets from appearing in the first place.

## 8. Building and Pushing Container Images to Amazon ECR

For a Spring Boot application running on ECS/EKS, the pipeline typically builds a JAR, creates a container image, scans the image, and pushes it to Amazon ECR.

### 8.1. Minimal Dockerfile

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/orders-api.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is an illustrative example. Production images should pin the base image by digest, run as non-root, copy only runtime artifacts, apply multi-stage builds when needed, and update the base image according to security policy. Do not put AWS credentials or application secrets into image layers.

### 8.2. Buildspec Pushing Image by Commit SHA

Example for a Linux CodeBuild project with privileged mode enabled if using the Docker daemon, and the ECR repository URI configured in the project:

~~~yaml
version: 0.2

env:
  variables:
    ECR_REPOSITORY_URI: "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api"

phases:
  pre_build:
    commands:
      - ECR_REGISTRY="$(echo "$ECR_REPOSITORY_URI" | cut -d/ -f1)"
      - aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
      - COMMIT_SHA="$(echo "$CODEBUILD_RESOLVED_SOURCE_VERSION" | cut -c 1-12)"
      - IMAGE_TAG="$COMMIT_SHA"
  build:
    commands:
      - mvn -B clean verify
      - docker build -t "$ECR_REPOSITORY_URI:$IMAGE_TAG" .
  post_build:
    commands:
      - docker push "$ECR_REPOSITORY_URI:$IMAGE_TAG"
      - printf '{"imageUri":"%s","imageTag":"%s","commit":"%s"}\n' "$ECR_REPOSITORY_URI" "$IMAGE_TAG" "$CODEBUILD_RESOLVED_SOURCE_VERSION" > image-detail.json

artifacts:
  files:
    - image-detail.json
~~~

This is an example to explain the flow; `ECR_REPOSITORY_URI` and `AWS_DEFAULT_REGION` must be set properly in the project/environment, ensuring the source has a Dockerfile and JAR at the right paths. For non-Git-commit source triggers, `CODEBUILD_RESOLVED_SOURCE_VERSION` may have different semantics; validate the value before using it as a tag.

### 8.3. IAM Permissions for CodeBuild

The CodeBuild service role typically needs permissions for:

- ECR authorization token at the scope required by AWS.
- ECR upload layer/image actions on the specific repository.
- Writing build logs to CloudWatch Logs.
- Reading package dependencies from CodeArtifact if used.
- Reading parameters/secrets needed for the build, only when truly required.
- Writing artifacts to the S3 artifact store according to the pipeline configuration.

Do not grant ECR full access or `AdministratorAccess` just to push images. Separate build/push permissions from production deploy permissions whenever the pipeline architecture allows.

### 8.4. Image Tags and Digests

Commit SHA tags help trace back to source; an **image digest** is the immutable content identifier of an image manifest. When deploying to production, prefer an image URI with a digest, for example:

~~~text
444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:...
~~~

Tags can be overwritten if the ECR repository does not enable tag immutability. Enable immutable tags for release repositories and store the digest in the release manifest. Do not use `latest` to identify releases.

### 8.5. Image Scanning and Promotion

ECR image scanning can detect vulnerabilities based on the enabled scan mode/configuration. The pipeline should wait for scan results and apply a threshold policy before deploying. For promotion across accounts/Regions, you can use ECR replication or controlled image copying; after copying, verify the digest and provenance in the destination repository.

## 9. Artifact Store, CodeArtifact, and Immutability

CodePipeline stores intermediate artifacts in an S3 artifact bucket. The artifact store must be designed as a production component:

- Enable encryption using SSE-KMS per policy.
- Block public access, with a bucket policy restricting access to pipeline roles.
- Configure versioning/lifecycle aligned with retention and audit requirements.
- Do not share an uncontrolled bucket across multiple organizations/applications.
- Define cross-Region artifact stores when the pipeline has actions in other Regions.
- Configure KMS key policies for the pipeline role, action roles, and target accounts.

### 9.1. Pipeline Artifacts vs. Application Artifacts

Pipeline artifacts are files exchanged between actions/stages, such as source archives, test reports, templates, or deployment manifests. Application artifacts are the released JAR/WAR/container image. Do not treat an intermediate ZIP file in S3 as the sole source of truth for identifying the runtime image if the actual deployment uses an ECR digest.

### 9.2. Release Manifest

A manifest can record:

~~~json
{
  "service": "orders-api",
  "version": "1.8.0",
  "sourceCommit": "0123456789abcdef",
  "buildId": "orders-build:1042",
  "imageUri": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:REPLACE_WITH_DIGEST",
  "sbom": "artifacts/orders-api-1.8.0.cdx.json",
  "createdAt": "2026-11-20T04:00:00Z"
}
~~~

The manifest above is an example; replace the digest with the actual value from the image push. Do not store secrets, environment-specific credentials, or secret values in the manifest. You can add signatures, provenance attestations, and deployment config versions.

### 9.3. CodeArtifact for Internal Dependencies

AWS CodeArtifact can store Maven, npm, Python, and supported package formats. Use an internal repository to:

- Cache/proxy dependencies from public repositories.
- Distribute shared libraries and internal SDKs.
- Control package versions, upstream sources, and access policies.
- Reduce dependency confusion risk via namespace/source policies.

The build role needs permission to authenticate/read package repositories; the publish role needs permission to write/publish. Do not allow every build job to overwrite released package versions.

### 9.4. Reproducible Builds and Dependency Pinning

- Use the Maven Wrapper/Gradle Wrapper and pin plugin versions.
- Pin container base images by digest.
- Do not use dynamic dependency versions like `LATEST` or `SNAPSHOT` for production releases without controls.
- Store SBOMs, build metadata, and checksums.
- Caching is only an optimization; a cache miss must not change the build output.
- Separate build-time credentials from runtime credentials.

## 10. CodePipeline Structure and Action Artifacts

A CodePipeline typically consists of stages, where each stage has one or more actions. Actions can consume artifacts from a preceding action and produce output artifacts for the next stage.

### 10.1. Sample Pipeline Stages

| Stage | Action provider | Input | Output / gate |
|---|---|---|---|
| Source | CodeConnections | Git commit | SourceArtifact |
| Build | CodeBuild | SourceArtifact | AppArtifact, test reports |
| Security | CodeBuild/approved scanner | AppArtifact | Scan reports, pass/fail |
| Image | CodeBuild | AppArtifact | ECR image digest + manifest |
| Deploy test | ECS/CloudFormation/CodeDeploy | Manifest/template | Test environment |
| Verify | CodeBuild | Test endpoint/config | Smoke test result |
| Approval | Manual approval | Release summary | Approved/rejected |
| Deploy prod | ECS/CodeDeploy/CloudFormation | Same digest/template | Production deployment |
| Observe | CloudWatch/CodeBuild | Runtime metrics | Release accepted/rollback |

### 10.2. Artifact Names and Namespaces

Use meaningful artifact names, such as `SourceArtifact`, `BuildArtifact`, `ImageManifest`, `IaCTemplate`. Do not overwrite artifacts across parallel executions using a shared custom S3 key; use execution-specific paths and keep links to the execution ID.

### 10.3. Manual Approval Action

Manual approval is useful before production or high-risk changes. Approval notifications can be sent to an SNS topic; the approver should review the release summary, change set, test results, artifact digest, risk/rollback plan, and target environment. Approval does not replace automated checks; it is an audited decision gate.

### 10.4. Execution Modes and Concurrent Releases

CodePipeline V2 supports execution modes such as `SUPERSEDED`, `QUEUED`, and `PARALLEL`. Choose the mode based on how releases should be processed:

- **SUPERSEDED:** a new execution can replace an older waiting/running execution under supported conditions.
- **QUEUED:** executions are processed in a queue to prevent concurrent runs against the same target.
- **PARALLEL:** multiple executions can run in parallel; use only when deployments do not contend for the same target/state.

If multiple releases update the same ECS service, CloudFormation stack, or database schema, parallel deployments can cause race conditions. Use `QUEUED`/`SUPERSEDED` appropriately or system-level deployment locking/serialization.

## 11. IAM Roles and Pipeline Security

A pipeline involves multiple principals. Do not use a single overly permissive role for every stage.

~~~mermaid
flowchart TD
    DEV["Developer / Git provider"] --> CONN["CodeConnections"]
    CONN --> CP["CodePipeline service role"]
    CP --> CB["CodeBuild service role"]
    CP --> DEPLOY["Deployment action role"]
    DEPLOY --> CFN["CloudFormation service role"]
    CFN --> RES["AWS resources"]
    CB --> ECR["ECR repository"]
    CB --> S3["Artifact bucket"]
    CP --> KMS["KMS key"]
    DEPLOY --> TARGET["Cross-account target role"]
~~~

### 11.1. Role Separation

| Role | Typical permissions |
|---|---|
| CodePipeline service role | Read source connection, invoke action providers, read/write artifacts, use KMS |
| CodeBuild service role | Logs, artifact access, dependency read, ECR push, and required test resources |
| CloudFormation service role | Create/update resources defined in the template |
| CodeDeploy service role | Orchestrate deployments to compute targets |
| Cross-account deploy role | Receive deployments from the pipeline account, operate in the target account |
| Application runtime role | Business permissions when the application runs |

### 11.2. Least Privilege and iam:PassRole

CodePipeline/CodeBuild/CloudFormation may require `iam:PassRole` to attach a role to a resource or service. Scope it to specific role ARNs and service conditions where supported. Do not grant `iam:PassRole` on a wildcard if the pipeline only deploys a single workload.

### 11.3. Cross-Account Deployment

A multi-account model typically has a dedicated pipeline account and target accounts for dev/staging/prod:

1. The pipeline role in the source account has permission to assume the target deployment role.
2. The target role trust policy allows only the specific source role.
3. The target role has permissions to deploy the stack/service in the target account.
4. The CloudFormation service role in the target account creates resources following least privilege.
5. The artifact bucket/KMS key policy allows the required cross-account actions.

Do not share access keys across accounts. Use STS `AssumeRole` temporary credentials and audit assumed-role sessions.

### 11.4. Cross-Account Artifact Encryption

For cross-account CodePipeline, the target account needs to read artifacts and decrypt with the appropriate KMS key. Verify both:

- S3 bucket policy for the target principal/account.
- KMS key policy/grants for encrypt/decrypt/generate data key.
- Pipeline role and target action role permissions.
- The artifact store in the Region where the action runs.

An S3 object encrypted with SSE-KMS without KMS key policy permissions for the target account to decrypt will cause the action to fail even if the bucket policy allows it.

### 11.5. Source Connections and GitHub OIDC

CodeConnections and GitHub Actions OIDC are two different connection/authorization mechanisms. With GitHub Actions, the AWS role trust policy can restrict the repository, branch, or environment via token claims. Do not allow every repository in an organization to assume a production role.

### 11.6. Secrets in CodeBuild

CodeBuild supports retrieving environment variables from Parameter Store or Secrets Manager per project/buildspec configuration. The service role should only have permission to read specific secrets. Do not print secrets, store them in artifacts, bake them into Docker build layers, or reuse the build role as the runtime role.

## 12. Deploying Infrastructure with CloudFormation, CDK, and SAM

Pipelines often need to deploy both application and infrastructure. Infrastructure deployment should be separated from application rollout when they have different lifecycles/risks, while still being managed with shared release metadata.

### 12.1. CloudFormation Template Validation

An IaC stage can:

1. Check YAML/JSON syntax.
2. Run `cfn-lint` or an equivalent validator.
3. Run policy checks such as CloudFormation Guard.
4. Package artifacts if the template references local assets.
5. Create a CloudFormation change set.
6. Review resource actions/replacements and wait for approval.
7. Execute the change set.
8. Wait for the stack terminal status and verify outputs.

Do not deploy directly to a production template if policy requires change set review. A change set preview does not guarantee resource operations will succeed; the pipeline must still monitor events and handle rollback.

### 12.2. CloudFormation Deploy Action

CodePipeline has CloudFormation action providers supporting operations such as create/update stack and create/execute change set depending on action configuration. When using change sets:

- One action creates the change set.
- A manual approval/review stage can be inserted.
- The next action executes the created change set.
- Roles, capabilities, parameters, and artifact paths must match the template.

Verify the exact action provider/version/configuration being used; avoid assuming all CloudFormation action types automatically wait for manual approval or automatically roll back application data.

### 12.3. AWS CDK

AWS CDK lets you define infrastructure in a programming language. A pipeline can run:

~~~bash
npm ci
npm test
npx cdk synth
npx cdk diff
npx cdk deploy OrdersProductionStack --require-approval broadening
~~~

This is a CLI example; a CDK app can use TypeScript, Python, Java, C#, or Go as supported. For production, separate synth/diff from deploy, store synthesized templates as artifacts, and review IAM/security changes. CDK bootstrap resources and deployment roles must be pre-configured for the account/Region.

### 12.4. AWS SAM for Serverless

SAM build creates deployment artifacts; package/deploy uses CloudFormation to manage resources:

~~~bash
sam validate --lint
sam build
sam package --s3-bucket orders-sam-artifacts-prod --output-template-file packaged.yaml
aws cloudformation create-change-set \
  --stack-name orders-api-prod \
  --change-set-name release-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://packaged.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-southeast-1
~~~

Capabilities depend on the template; do not blindly add `CAPABILITY_NAMED_IAM` or `CAPABILITY_AUTO_EXPAND`. A SAM template can create Lambda functions, API Gateways, queues, policies, and event source mappings; review all expanded CloudFormation changes.

### 12.5. IaC State and Drift

CloudFormation is the source of desired state for the stack. Do not let a pipeline and engineers modify the same resource through two unsynchronized mechanisms. If an emergency manual change is made, record it and reconcile the template/drift before the next release.

## 13. Deploying Applications to Amazon ECS

An ECS deployment requires updating the task definition revision and the ECS service. The pipeline typically:

1. Builds the JAR/container image.
2. Pushes the image to ECR and retrieves the image digest.
3. Renders a new task definition with the image URI/digest.
4. Deploys the task definition revision to the ECS service.
5. Waits for the service to stabilize and health checks to pass.
6. Runs smoke tests and monitors metrics.

### 13.1. Rolling Deployment

ECS rolling updates replace tasks according to the deployment configuration, such as minimum healthy percent and maximum percent. This is a simple option suitable for stateless and backward-compatible services. Configure health checks, grace periods, capacity, and the deployment circuit breaker.

The ECS deployment circuit breaker can detect when a deployment fails to reach a steady state; when rollback is enabled, ECS can revert to the previous deployment. This is an ECS service deployment mechanism, distinct from CloudFormation stack rollback.

### 13.2. Blue/Green Deployment with CodeDeploy

ECS blue/green uses two target groups and listener routing through a load balancer:

- Blue is the current task set.
- Green is the new task set.
- CodeDeploy creates the green task set, waits for tests/traffic shifting, and shifts listener traffic according to the deployment configuration.
- If an alarm fires or validation fails, CodeDeploy can roll traffic back to blue per configuration.

Example ECS AppSpec (fragment):

~~~yaml
version: 0.0
Resources:
  - TargetService:
      Type: AWS::ECS::Service
      Properties:
        TaskDefinition: <TASK_DEFINITION>
        LoadBalancerInfo:
          ContainerName: orders-api
          ContainerPort: 8080
~~~

This AppSpec is only a fragment; an actual deployment requires a task definition artifact, AppSpec artifact, ECS cluster/service, target groups, listener, CodeDeploy application/deployment group, and service role. Configure a test listener and lifecycle hooks when needed.

### 13.3. Database Migrations Must Be Backward-Compatible

During blue/green or rolling deployments, old and new versions can run concurrently. Schema migrations should follow the expand/contract pattern:

1. Add the new schema so the old version can still run.
2. Deploy the application supporting both old and new schemas.
3. Migrate/backfill data and verify.
4. Shift traffic completely to the new version.
5. Remove the old schema only in a subsequent release after no old consumers remain.

Rolling back an application does not automatically roll back a destructive database migration. Use versioned migration scripts, backups, and a compensation plan.

## 14. Deploying to AWS Lambda

Lambda deployments need to manage the code package/image, function configuration, versions, and aliases. Do not update a production alias with an uncontrolled command if traffic shifting/rollback is needed.

### 14.1. Versions and Aliases

A Lambda version is an immutable snapshot of published function code/configuration. An alias is a pointer to a version and can configure weighted routing between two versions. Production integrations should invoke the alias instead of invoking **$LATEST** directly.

### 14.2. CodeDeploy Traffic Shifting

Lambda can use CodeDeploy to shift traffic from the old version to the new version using:

- **Canary:** shifts a small percentage of traffic first, waits for a period, then shifts the remainder.
- **Linear:** shifts traffic in equal percentage increments.
- **All-at-once:** shifts all traffic immediately.

Choose the deployment configuration based on latency, cold starts, blast radius, and observability. Attach CloudWatch alarms and pre/post-traffic hooks to validate health.

### 14.3. SAM Deployment Preferences

Example:

~~~yaml
Resources:
  OrdersFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: com.example.orders.Handler::handleRequest
      Runtime: java21
      CodeUri: target/orders-function.jar
      AutoPublishAlias: live
      DeploymentPreference:
        Type: Canary10Percent10Minutes
        Alarms:
          - !Ref OrdersApiErrorsAlarm
        Hooks:
          PreTraffic: !Ref PreTrafficValidation
          PostTraffic: !Ref PostTrafficValidation
~~~

This is a SAM fragment; the function, alarm, and hook resources must be fully defined. Deployment preferences support CodeDeploy traffic shifting; choose a runtime/version supported by Lambda and verify the Java packaging model.

### 14.4. Lambda Rollback

If an alarm enters `ALARM` or a hook fails, CodeDeploy can stop the deployment and shift alias traffic back to the previous version per deployment configuration. Verify function code, environment variables, IAM roles, event source mappings, reserved concurrency, and API integrations. Alias rollback does not restore data or side effects that occurred during the canary window.

## 15. Deploying to Amazon EKS

EKS deployments can use CodePipeline/CodeBuild to build images, push to ECR, and update Kubernetes manifests/Helm charts. A common approach is **GitOps**: the pipeline updates the image digest in a GitOps repository, and Argo CD/Flux reconciles the desired state into the cluster.

### 15.1. Direct Deploy vs. GitOps

| Approach | Flow | Best fit when |
|---|---|---|
| Direct deploy | CodeBuild assumes a deploy role and runs Helm/kubectl | Teams have simple pipelines with controlled deploy permissions |
| GitOps | Pipeline commits manifest/chart; controller pulls and reconciles | Desired-state audit in Git and continuous reconciliation are needed |

GitOps does not eliminate CI. CI still builds/tests/scans the artifact; the CD controller deploys the approved desired state.

### 15.2. Image Digest and Rollout

Production manifests should pin the image digest, not just a mutable tag:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:REPLACE_WITH_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
~~~

The digest is a placeholder; the pipeline must replace it with the built/scanned digest. Readiness/liveness probes must match the application's actual endpoints and security configuration.

### 15.3. Rollout Status and Rollback

Common commands:

~~~bash
kubectl rollout status deployment/orders-api -n production --timeout=5m
kubectl rollout history deployment/orders-api -n production
kubectl rollout undo deployment/orders-api -n production
~~~

Deployment rollback returns Kubernetes to the previous revision in rollout history if that revision still exists. It does not roll back CloudFormation resources, database schemas, or external messages. With GitOps, revert the desired state in Git rather than patching the cluster manually; the controller may overwrite out-of-band changes.

### 15.4. Progressive Delivery on EKS

`RollingUpdate` is the default for Kubernetes Deployments. Canary/blue-green can be implemented via a service mesh, ingress controller, or progressive delivery controllers such as Argo Rollouts/Flagger depending on architecture. Clear metrics analysis, automated promotion/abort, and traffic routing are required; simply increasing replicas does not create a canary.

## 16. Release Strategies and Traffic Shifting

No single deployment strategy fits every application. Choose a strategy based on availability, latency, state compatibility, capacity, cost, and rollback time.

| Strategy | How it works | Pros | Risks/conditions |
|---|---|---|---|
| **In-place** | Updates instances/tasks/functions directly | Simple, minimal temporary resources | Downtime/interruption may occur |
| **Rolling** | Replaces groups of instances/tasks incrementally | No full duplicate environment needed | Old/new versions run concurrently |
| **Blue/green** | Provisions new environment, shifts traffic | Fast cutover/rollback via traffic routing | Requires double capacity and data compatibility controls |
| **Canary** | Shifts a small share of traffic, observes, then increases | Limits blast radius | Requires metrics and sufficient sample traffic |
| **Linear** | Shifts traffic in incremental steps | Observe progression step by step | Longer release duration |
| **All-at-once** | Shifts all traffic immediately | Fast, minimal concurrent run time | Large blast radius on failure |

### 16.1. Blue/Green Does Not Automatically Solve Database Compatibility

Two application versions may connect to the same database simultaneously. The schema must be backward-compatible, and migrations must not drop columns/indexes still used by the old version. If a migration is not backward-compatible, a traffic rollback may restore the old application while the database remains changed, breaking the app.

### 16.2. Canary Requires Sufficient Traffic and Time

If only 10 requests arrive during the canary window, a 0% error rate does not prove the release is safe. Choose a sample size/time window appropriate to traffic, latency SLOs, and error budgets. Also monitor business metrics such as order completion, payment failures, queue age, and consumer lag.

### 16.3. Feature Flags Complement Deployment Strategies

Deploying code and enabling a feature are two decisions that can be separated. Feature flags let you release code with a new feature turned off, enable it for internal users/percentage cohorts, and expand once metrics stabilize. Flags need an owner, expiry, and cleanup plan; long-lived flags can create many code branches that are hard to test.

## 17. Automated Rollback and Deployment Health

Rollback must be designed before a release, not improvised during an incident.

### 17.1. Rollback Signals

| Signal | Example threshold | Configurable action |
|---|---|---|
| Application errors | 5xx rises above baseline/SLO | Abort canary, CodeDeploy rollback |
| Latency | p95/p99 breaches SLO continuously | Stop traffic shift |
| ECS health | Desired tasks fail to reach healthy | ECS circuit breaker rollback |
| Lambda errors/throttles | Error/throttle rate rises after alias shift | CodeDeploy alias rollback |
| EKS rollout | Readiness probes fail, unavailable replicas | Pause/undo rollout or Git revert |
| Business KPI | Payment/order completion drops | Stop release, disable feature flag, compensate |
| IaC stack | CloudFormation resource update failed | CloudFormation rollback per operation |

Thresholds must be based on baselines and traffic; do not copy a single generic number across every service. Overly sensitive alarms cause false rollbacks; overly slow alarms increase blast radius.

### 17.2. CloudWatch Alarms and CodeDeploy

A CodeDeploy deployment group can associate CloudWatch alarms. When an alarm enters `ALARM` during a deployment, CodeDeploy can stop/roll back the deployment depending on configuration. Ensure:

- Alarms have metrics and dimensions matching the exact service/version/target group.
- Alarms are deployed before or in dependency order with the deployment group.
- The role and service integration have permission to monitor alarms.
- Alarm state/`INSUFFICIENT_DATA` behavior is well understood.
- The deployment group is configured for auto rollback on deployment failure/alarm when needed.

### 17.3. ECS Deployment Circuit Breaker

For ECS rolling deployments, configure the deployment circuit breaker and rollback. ECS evaluates whether a deployment reaches steady state based on task launch/health progression. It does not replace application-level smoke tests or business metrics; a deployment can reach healthy tasks while request logic is still broken.

### 17.4. CloudFormation Rollback

CloudFormation rollback protects the stack update, not the entire release. If a pipeline deploys the app image and CloudFormation infrastructure separately:

- A stack update rollback may not roll back an image/service deployment executed in another action.
- A CodeDeploy rollback may shift traffic back to the previous app version but does not restore DB data.
- Pipeline orchestration is needed to halt subsequent stages, record status, and trigger the appropriate recovery action.

### 17.5. Rollback vs. Roll-Forward

Rollback fits when the previous version remains compatible with data/schema/configuration. A roll-forward hotfix fits when rollback is unsafe or a data migration is already irreversible. The decision must follow the incident runbook, not simply whichever action is easier to run.

## 18. Multi-Environment and Cross-Account Releases

Pipelines typically promote the same artifact through dev → test → staging → production. **Build once, promote many times** ensures the tested binary/image is the exact binary/image deployed to production.

### 18.1. Separating Configuration from Artifacts

Artifacts must not contain:

- Production database passwords.
- AWS access keys/session tokens.
- Environment-specific secret values.
- Hard-coded account IDs, endpoints, or bucket names if they must vary per environment.

Runtime configuration is supplied via environment variables, Parameter Store, Secrets Manager, task/pod/Lambda configuration, and IAM roles.

### 18.2. Cross-Account Deployment Model

~~~mermaid
flowchart TD
    SRC["Source repository"] --> PIPE["Pipeline account"]
    PIPE --> BUILD["Build once"]
    BUILD --> ART["Encrypted artifact / ECR image"]
    ART --> DEV["Dev account role"]
    DEV --> TEST["Integration tests"]
    TEST --> STAGE["Staging account role"]
    STAGE --> APPROVE["Approval"]
    APPROVE --> PROD["Production account role"]
    PROD --> VERIFY["Health / smoke / alarms"]
~~~

### 18.3. Cross-Account Roles

Each target account has a dedicated deploy role. Its trust policy restricts access to the source pipeline role; its permissions policy only allows updating approved stacks/services. The pipeline account needs permission to assume the role and access artifacts; the target role needs permission to read artifacts/decrypt the KMS key if the action runs in the target account.

Do not allow a production deploy role to modify arbitrary IAM trust policies or assume roles in unrelated accounts.

### 18.4. Cross-Region Deployment

CodePipeline supports per-Region artifact stores when pipeline actions run across multiple Regions. You must specify an artifact store and corresponding KMS key for each Region. Cross-Region actions can incur data transfer and encryption permissions requirements; verify the pipeline service role is allowed to use keys across Regions.

Do not just change a Region parameter and assume resources are replicated. For ECR, S3, KMS, databases, and secrets, replication/backup/copy must be configured and destination resources verified.

### 18.5. Approval and Separation of Duties

Production approval should be performed by a person/team responsible for releases, distinct from the author of the change when policy requires. The approval summary should display:

- Source commit, release version, and artifact digest.
- Test/security scan results.
- IaC change set and replacement/deletion risks.
- Target account/Region/environment.
- Rollout strategy, alarm links, and rollback plan.
- Ticket/change request and approver identity.

Approval must not rely on a generic message like "green build." Approvers need enough information to properly evaluate the release.

## 19. Pipeline Example: Designing CodePipeline for ECS

Logical pipeline example for a Spring Boot service:

~~~text
Source:
  Provider: CodeConnections
  Repository: orders-api
  Trigger: merge to main

Build:
  Provider: CodeBuild
  Commands: mvn clean verify
  Output: application JAR + test reports

Security:
  Provider: CodeBuild
  Checks: SCA + secret scan + IaC scan
  Gate: all required findings pass

Container:
  Provider: CodeBuild
  Commands: docker build + ECR push
  Output: image digest manifest

Deploy-Test:
  Provider: ECS deploy action
  Input: task definition + image digest

Verify-Test:
  Provider: CodeBuild
  Checks: smoke + API contract tests

Approval:
  Provider: Manual approval
  Evidence: reports + release manifest + rollback plan

Deploy-Prod:
  Provider: ECS rolling or CodeDeploy blue/green
  Input: same image digest used in test

Observe:
  Provider: CloudWatch alarms + smoke checks
  Result: accept release or rollback
~~~

This is a blueprint, not a deployable pipeline definition file as-is. Action provider names, artifact names, IAM role ARNs, task definition files, and CodePipeline V1/V2 configuration must be declared per project.

### 19.1. Task Definition Template

A task definition template can keep a placeholder for the image:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::444455556666:role/orders-api-execution-role",
  "taskRoleArn": "arn:aws:iam::444455556666:role/orders-api-task-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "REPLACE_WITH_ECR_IMAGE_DIGEST",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ]
    }
  ]
}
~~~

The pipeline renders the image URI with the built digest, saves the task definition artifact, and deploys it. Do not write runtime secrets into the task definition artifact; use Secrets Manager references or application runtime secret retrieval.

### 19.2. CodeBuild Deploy Verification

After deploying to test, a CodeBuild action can run smoke tests:

~~~bash
set -euo pipefail

for attempt in $(seq 1 30); do
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' "$APP_BASE_URL/actuator/health/readiness" || true)"
  if [ "$status" = "200" ]; then
    echo "Readiness check passed"
    exit 0
  fi
  sleep 10
done

echo "Application did not become ready"
exit 1
~~~

This is a shell example; `APP_BASE_URL` must come from controlled environment configuration. In a production pipeline, bound retries/timeouts and do not use a readiness endpoint as the sole business verification.

## 20. Pipeline Observability and Auditing

A green pipeline is not enough to prove a healthy release. Monitor **pipeline execution**, **deployment**, **application runtime**, and **business outcomes**.

### 20.1. Pipeline Metrics

| Metric | Question |
|---|---|
| Pipeline success/failure rate | Do releases fail frequently? |
| Stage/action duration | Which stage creates a bottleneck? |
| Build queue time | Is CodeBuild capacity/concurrency sufficient? |
| Test failure rate | Which regressions appear most often? |
| Deployment duration | How long does a release take to serve traffic? |
| Rollback frequency | Are quality gates missing defects? |
| Lead time / deployment frequency | How is delivery speed changing? |
| Change failure rate / MTTR | How often do releases cause incidents and how long does recovery take? |

### 20.2. CloudWatch Logs

CodeBuild build logs can be sent to CloudWatch Logs or S3 per configuration. Set appropriate retention, control read access, and redact sensitive output. Do not log all environment variables or build commands containing secrets.

### 20.3. CloudTrail

CloudTrail helps audit API actions such as creating pipelines, updating projects, assuming roles, updating stacks/services, and modifying IAM. Enable a trail/organization trail as required; data events and retention can impact cost.

### 20.4. Deployment Dashboard

A release dashboard can display:

- Pipeline execution ID and commit SHA.
- Build ID, test reports, and scan findings.
- Artifact version/image digest.
- Target account/Region/cluster/service/stack.
- Deployment strategy and current traffic percentage.
- Alarm state, error rate, latency, and healthy targets.
- Rollback action and final stack/service state.

### 20.5. Notifications

Notifications can be sent via SNS, EventBridge rules, Chatbot/Chat integrations, or incident management systems. Notifications should include links to executions/logs, release ID, failed action, error summary, and owner; do not include credentials, secret values, or customer payloads.

## 21. GitHub Actions OIDC and Pipeline Identity

When using GitHub Actions for CI/CD, there is no need to store long-lived AWS access keys in GitHub secrets. GitHub can issue an OIDC token allowing a workflow to assume an IAM role whose trust policy restricts repository/ref/environment.

### 21.1. Trust Policy Restricting Repository and Branch

Example trust policy for the `orders-api` repository workflow, allowing only the `main` branch:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubActionsMainOnly",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::444455556666:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:example-org/orders-api:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Replace the account ID, organization, and repository with real values. If using a GitHub Environment, the subject claim has a different format; the trust policy must match the exact token claims issued by the workflow. Do not use overly broad wildcards across all branches/repositories.

### 21.2. Workflow Role Assumption

Example workflow:

~~~yaml
name: Build and deploy

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::444455556666:role/orders-api-ci-role
          aws-region: ap-southeast-1
      - name: Verify identity
        run: aws sts get-caller-identity
      - name: Build
        run: mvn -B clean verify
~~~

This is a workflow fragment. In production, pin third-party actions to full commit SHAs or follow your organization's supply-chain policy, scope permissions, separate deploy jobs/environments, and prevent untrusted pull request code from running in jobs with production access.

### 21.3. Pull Requests from Forks

Do not grant a production OIDC role to workflows running code from forks/untrusted pull requests. Pull request jobs should only run tests/static analysis with minimal permissions; deployment credentials should only be granted after merge or protected environment approval.

### 21.4. GitHub OIDC and CodeConnections Are Different

CodeConnections grants CodePipeline access to a source provider to fetch source revisions. GitHub OIDC allows a GitHub Actions workflow to assume an AWS role. They do not replace each other and have distinct trust boundaries.

## 22. Supply Chain Security and Release Provenance

A secure pipeline must prove that an artifact came from reviewed source, a trusted build environment, and controlled dependencies.

### 22.1. SBOM and Provenance

An SBOM lists components/dependencies in an artifact. Provenance records the source revision, builder, build steps, and artifact digest. Store them with release metadata and link them to the deployment.

### 22.2. Artifact Signing

Container images or packages can be signed with appropriate tools such as Notation/Cosign and integrated with AWS Signer depending on the use case. A runtime/deployment admission policy can require a signature from a trusted identity before allowing an image to run. Signing is only effective when verification policy is enforced at the deployment boundary.

### 22.3. Pin Actions, Dependencies, and Build Images

- Pin GitHub Actions by commit SHA when using GitHub workflows.
- Use a specific CodeBuild managed image version or a controlled custom image.
- Pin Maven/Gradle plugins and dependency versions.
- Pin Docker base images by digest.
- Manage package sources/allowlists in CodeArtifact.
- Scan artifacts and generate SBOMs before release.

### 22.4. Build Isolation

Untrusted pull request builds should not run in an environment with permissions to publish production images or assume production roles. Separate projects/roles or build phases; restrict privileged Docker mode and network egress when not needed.

### 22.5. Artifact Promotion

Do not rebuild in each environment. Promote the same artifact digest across dev/staging/prod; change only deployment configuration, secret references, and runtime roles. If an image must be copied across accounts/Regions, verify the digest and signature after copying.

## 23. Cost and Operational Efficiency

CI/CD reduces manual effort and release errors, but pipeline executions, build minutes, artifact storage, image scanning, logs, and temporary deployment capacity all incur costs.

| Component | Cost drivers | Control measures |
|---|---|---|
| CodePipeline | Pipeline type, active pipeline/execution pricing per current model | Choose V1/V2 based on required triggers/concurrency |
| CodeBuild | Compute type, build duration, concurrency, reserved capacity | Cache dependencies, right-size compute, parallelize sensibly |
| S3 artifact store | Storage, requests, replication, data transfer | Lifecycle policies, retention, and artifact cleanup |
| KMS | Key usage/API requests per current pricing | Use an appropriate key strategy, avoid unnecessary keys |
| ECR | Image storage, scan features, data transfer | Lifecycle rules, remove untagged/obsolete images carefully |
| CodeArtifact | Package storage/requests/data transfer | Retention/cleanup and dependency caching |
| CloudWatch | Log ingestion/storage/metrics/alarms | Retention, log levels, metric cardinality |
| Cross-Region/account | Artifact copy, replication, KMS operations | Choose appropriate Regions and promotion model |
| Blue/green | Two environments running temporarily in parallel | Estimate capacity and monitoring window |
| Test environments | ECS/EKS/RDS resources for testing | Ephemeral environments, scheduled shutdown, and cleanup |

### 23.1. Optimizing CodeBuild

- Cache Maven/Gradle dependencies while still pinning versions.
- Choose compute sizes suited to compile/test workloads.
- Run independent tests in parallel when there is no resource contention.
- Avoid rebuilding the same image in multiple stages.
- Use test selection/path filters in monorepos with a clear dependency graph.
- Clean up ephemeral resources after integration tests.

### 23.2. Optimizing Artifact and Image Retention

Keep release artifacts per retention policy for rollback/audit. Delete untagged images and build intermediates via lifecycle rules, but do not delete digests currently referenced by ECS/EKS/Lambda releases or rollback plans. Retain enough image versions for the rollback window and compliance.

### 23.3. Measuring DORA-Style Delivery Metrics

Track deployment frequency, lead time for changes, change failure rate, and time to restore service. Use metrics to improve bottlenecks, not to pressure teams into increasing release counts by cutting tests or skipping necessary approvals.

## 24. Pipeline and Deployment Troubleshooting

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Source action cannot fetch code | Connection unauthorized, role missing UseConnection, wrong webhook/trigger | Connection status, pipeline role, source revision |
| CodeBuild cannot checkout source | Incorrect source artifact/input mapping, missing artifact bucket permissions | Action configuration, S3/KMS, build logs |
| Maven/Gradle build fails | JDK/toolchain mismatch, dependency repository error, test failure | Build image/runtime, wrapper version, logs/reports |
| CodeBuild cannot push to ECR | Role missing ECR upload actions, wrong Region/repository URI | Caller identity, repository policy, ECR auth |
| Docker build fails | Missing privileged mode, daemon unavailable, wrong build context | Project environment, Dockerfile, build logs |
| Image scan fails | Vulnerability threshold or scan not yet complete | ECR scan status, finding severity, exception policy |
| Pipeline artifact decrypt denied | S3 bucket/KMS key policy missing cross-account permissions | Artifact store, KMS key policy/grants |
| CloudFormation action fails | Capabilities, template, service role, change set, or quota | Stack events, change set status reason |
| ECS deployment does not stabilize | Task crash, image pull, health check, capacity, or networking | ECS service events, stopped task reason, target health |
| ECS blue/green fails | Wrong target group/listener/AppSpec/task definition | CodeDeploy deployment events, ALB target health |
| Lambda deployment fails | Alias/version, hook, permission, or alarm | CodeDeploy deployment, Lambda logs, alias routing |
| EKS rollout stuck | Image pull, readiness probe, insufficient capacity, RBAC | kubectl describe/events/logs, rollout status |
| OIDC AssumeRole denied | Trust policy sub/aud mismatch, missing workflow permissions | Token claims, role trust policy, id-token permission |
| Secret exposed in logs | Echoing env, shell tracing, build command | Stop job, rotate secret, handle incident and audit logs |
| Rollback does not restore app | Non-reversible database migration/side effect | App/data recovery plan, forward fix, compensation |
| Pipeline artifact mismatch | Overwritten tag, artifact key collision, parallel executions | Release manifest, digest, action input/output mapping |

### 24.1. Source/Connection Failure

Check connection state, repository authorization, branch filters, trigger configuration, IAM permissions on the connection ARN, and event delivery. If the pipeline does not trigger, run a manual execution to distinguish source trigger issues from action configuration issues.

### 24.2. Build Failure

Read the CodeBuild phase status and the first meaningful error line in the logs. Verify the runtime image, JDK/Maven/Gradle versions, dependency repositories, network egress, environment variables, and cache. Reproduce the build on the same commit in an equivalent environment before changing the production buildspec.

### 24.3. Deployment Failure

Do not look only at the red CodePipeline stage. Open the specific provider:

- CloudFormation: stack events and resource status reasons.
- ECS: service events, stopped task reasons, target group health.
- CodeDeploy: deployment lifecycle events and hook logs.
- Lambda: function logs, version/alias configuration, concurrency.
- EKS: Pod events, image pull status, readiness/liveness probes, and rollout history.

### 24.4. Rollback Failure

Rollbacks can fail due to database migrations, deleted resources, service quotas, permissions, or custom hooks. Stop new executions, identify the deployment system owning the rollback (ECS, CodeDeploy, CloudFormation, Kubernetes), and follow the proper recovery runbook. Do not invoke multiple rollback mechanisms simultaneously against the same target.

### 24.5. Pipeline Artifact Mismatch

If staging runs image digest A while production runs digest B:

1. Compare the release manifest and ECR digest.
2. Check artifact input/output mappings between actions.
3. Check whether a tag was overwritten.
4. Check for parallel pipeline executions and artifact key collisions.
5. Promote only the tested digest; do not rebuild in the production stage.

## 25. Production Release Runbook

### Phase A — Pre-Release

1. Confirm source commit/tag and code review.
2. Confirm the pipeline is running on the right branch/tag and target account/Region.
3. Pass build, unit tests, integration tests, security scans, and IaC checks.
4. Generate JAR/image, SBOM, provenance, and release manifest.
5. Record the image digest; do not rely on the `latest` tag.
6. Verify artifact encryption, IAM roles, and deployment permissions.
7. Confirm backup/data migration/rollback plan.
8. Confirm CloudWatch alarms, dashboard, and on-call owner.

### Phase B — Test/Staging

1. Deploy the exact same artifact digest to test/staging.
2. Run smoke, contract, acceptance, and security checks.
3. Verify caller identity/runtime role and environment-specific secrets/config.
4. Run migration/compatibility checks.
5. Measure latency/error/business metrics and verify autoscaling.
6. Save test evidence and release notes.

### Phase C — Approval and Production

1. Review release summary, artifact digest, change set, scan reports, and risk.
2. Approver confirms target environment, deployment strategy, and rollback plan.
3. Execute production deployment with a dedicated role.
4. Monitor traffic shift, healthy targets, alarms, and business KPIs.
5. Run post-deployment smoke tests.
6. If health checks pass during the monitoring window, mark the release complete.

### Phase D — Rollback or Close

1. If a gate fails, stop promotion and trigger the corresponding rollback mechanism.
2. Verify application traffic has returned to the stable version.
3. Inspect database/data side effects and run compensation/forward fixes if needed.
4. Verify final ECS/CodeDeploy/Lambda/EKS/CloudFormation state.
5. Save pipeline execution, deployment IDs, logs, alarms, and decision records.
6. Create incident/postmortem and remediation tasks.

~~~mermaid
flowchart TD
    A["Source revision approved"] --> B["Build once + test + scan"]
    B --> C["Publish immutable artifact + SBOM"]
    C --> D["Deploy test / staging"]
    D --> E["Smoke / contract / acceptance"]
    E --> F{"Approval & gates pass?"}
    F -->|"No"| STOP["Stop release / fix"]
    F -->|"Yes"| G["Production rollout"]
    G --> H["Observe alarms, SLO and business KPIs"]
    H --> I{"Healthy during window?"}
    I -->|"Yes"| J["Release complete + audit"]
    I -->|"No"| K["Rollback / traffic shift / recovery"]
    K --> L["Verify service and data state"]
~~~

## 26. Scenario Exercises

### Scenario A — Green Build but Production Fails

The pipeline compiles and unit tests pass, yet production returns 500 after deployment. Integration tests were not run, and production configuration differs from staging.

**Question:** Which gates are missing?

**Hint:** Add integration/contract tests, post-deploy smoke tests, config validation, and canary/alarms. Compare runtime roles, secrets, endpoints, and database schemas between staging/prod; do not treat passing unit tests as proof of a production-safe release.

### Scenario B — Latest Image Tag Overwritten

Two pipeline executions run in parallel and both push the `latest` tag. Staging tests the image from build A, while production deploys the image from build B.

**Question:** How do you ensure the right artifact is promoted?

**Hint:** Tag by commit/build ID, enable ECR tag immutability, store the image digest in the manifest, and deploy by digest. Serialize deployments if two executions update the same target.

### Scenario C — CodeBuild Cannot Push to ECR

Build tests pass, but `docker push` returns `AccessDeniedException`. The team grants `AdministratorAccess` to the CodeBuild role to unblock it.

**Question:** What least-privilege permissions should be checked?

**Hint:** Check the ECR authorization token and layer/image upload actions on the repository, Region, and repository policy. Grant only the exact permissions needed to the CodeBuild role; do not grant production deployment permissions if the build only needs to push images.

### Scenario D — Docker Build Fails in CodeBuild

The buildspec calls `docker build`, but fails with an error connecting to the Docker daemon.

**Question:** Which configuration needs verification?

**Hint:** Check whether the project environment has Docker capability/privileged mode enabled for daemon-based container builds, compute image/architecture, and build context. Consider an alternative builder if privileged mode is undesirable.

### Scenario E — GitHub Workflow Assume Production Role Denied

The workflow runs on branch `release/1.2`, but the trust policy only allows `refs/heads/main`.

**Question:** Should the `sub` condition be changed to a wildcard for all branches?

**Hint:** No. Intentionally update the trust policy for protected release branches or a GitHub Environment claim, restrict repository/ref, and keep the approval gate. Verify `aud`/`sub` token claims.

### Scenario F — Cross-Account Artifact Decrypt Denied

The pipeline account writes artifacts to S3 with SSE-KMS. The target account assumes the deployment role, but the action cannot decrypt the artifact.

**Question:** Which two layers must be checked?

**Hint:** Both the S3 bucket policy and KMS key policy/grants, along with pipeline/action role permissions. The target role must be allowed to read the object and decrypt with the right key; the artifact store/Region must match the action.

### Scenario G — ECS Deployment Rolls Back Despite Healthy Tasks

New tasks are healthy, yet API error rates increase because the application queries an incompatible new schema.

**Question:** Which health checks were missing?

**Hint:** Smoke/contract tests and business metrics, not just container health. Apply expand/contract migrations, canary traffic, and CloudWatch alarms to catch business errors before full rollout.

### Scenario H — Lambda Canary Fails After Database Changes

CodeDeploy shifts 10% of traffic to the new version; a migration makes an incompatible schema change, an alarm fires, and the alias shifts back to the old version.

**Question:** Why can rollback still leave the old app broken?

**Hint:** Alias rollback does not reverse DB migrations. Use backward-compatible migrations, backups, and compensation; decouple schema changes from traffic switches.

### Scenario I — EKS GitOps Keeps Reverting a Manual Hotfix

An engineer patches the image tag directly with `kubectl`, but Argo CD resets the manifest back to the version in Git.

**Question:** How should the hotfix be released?

**Hint:** Update the desired state in the GitOps repository, review/merge the hotfix commit, and let the controller reconcile. Record emergency manual changes and synchronize Git to avoid drift.

### Scenario J — CodePipeline Runs Two Deployments Concurrently

Two consecutive commits trigger parallel executions that update the same CloudFormation stack and ECS service simultaneously.

**Question:** Which execution mode should be chosen?

**Hint:** `QUEUED` if sequential processing is required; `SUPERSEDED` if only the latest release matters and action semantics allow; `PARALLEL` only when targets are independent. Use a deployment lock for shared databases/schemas.

### Scenario K — Security Scan Fails on a CVE with an Approved Exception

The pipeline blocks a release because the dependency scan detects a CVE temporarily accepted by the security team.

**Question:** Should the dependency scan be disabled?

**Hint:** No. Use an exception record with an owner, rationale, expiry, compensating controls, and a remediation ticket. The gate should bypass only the approved finding/version.

### Scenario L — CodeDeploy Rollback Succeeds but Pipeline Remains Green

The CodeDeploy deployment rolls back to the previous version, yet the pipeline action does not check the final status and subsequent stages still run.

**Question:** How should orchestration be improved?

**Hint:** Treat a rollback as a deployment failure, inspect the final deployment status, halt promotion stages, and send an incident notification. The pipeline must verify runtime state after rollback.

### Scenario M — Pull Request Build Job Can Read Production Secrets

An untrusted fork pull request runs a CodeBuild project using a service role with `GetSecretValue` on a production secret.

**Question:** How do you limit the blast radius?

**Hint:** Separate the PR build role/project with no production permissions, separate the deploy job behind merge/protected approval, and restrict network egress. Never run untrusted code in a build environment with secret access.

### Scenario N — ECR Lifecycle Deletes an Image Needed for Rollback

A repository lifecycle policy deletes older images after a few days. An incident requires rolling back to the previous release digest, but the image has been deleted.

**Question:** How should retention be changed?

**Hint:** Retain enough release images for the rollback/compliance window, protect tags/digests currently deployed, and test restore/copy. Lifecycle policies must account for tag patterns and untagged image behavior.

### Scenario O — Pipeline Updates CloudFormation Successfully but App Is Not Ready

The CloudFormation stack reaches `UPDATE_COMPLETE`, yet ECS tasks are unhealthy due to container startup failures.

**Question:** Why is stack status not sufficient?

**Hint:** IaC success only proves resource operations completed. A deployment stage, ECS service stabilization, target health, smoke tests, and application metrics are required; the pipeline must not mark a release complete while runtime is unhealthy.

## 27. Production Checklist

- [ ] Pipeline has a clear source trigger/branch/tag strategy and separate pull request validation.
- [ ] Every release is traceable to source commit, build ID, test reports, and deployment ID.
- [ ] Build environment, JDK/toolchain, dependencies, and base images are pinned.
- [ ] Unit, integration, contract, and smoke tests match risk levels.
- [ ] Security gates include SAST/SCA/secret/IaC/container scans per policy.
- [ ] Finding exceptions have an owner, rationale, expiry, and remediation plan.
- [ ] Buildspec returns accurate exit codes and emits test reports.
- [ ] Docker builds enable privileged mode only when required and have proper isolation.
- [ ] ECR tag immutability is enabled for release repositories; production deploys use image digests.
- [ ] SBOM/provenance/release manifests are generated and stored with artifacts.
- [ ] CodePipeline artifact store has S3/KMS encryption, bucket policies, retention, and cross-Region stores.
- [ ] CodeArtifact repositories and package permissions are controlled.
- [ ] CodePipeline, CodeBuild, CloudFormation, CodeDeploy, and runtime roles are separated.
- [ ] OIDC/CodeConnections trust is restricted to specific repositories, branches, environments, and connection ARNs.
- [ ] No long-lived access keys are used in pipelines, Docker images, or source code.
- [ ] Cross-account deploy roles, artifact bucket policies, and KMS key policies are verified.
- [ ] Production approvals display digest, test results, change set, target account/Region, and rollback plan.
- [ ] ECS deployments have appropriate health checks/circuit breakers or CodeDeploy blue/green.
- [ ] Production Lambda uses published versions/aliases and traffic shifting when needed.
- [ ] EKS rollouts have readiness/liveness probes, resource capacity, and GitOps desired state if applicable.
- [ ] Database migrations are backward-compatible; rollback does not rely on destructive reverse migrations.
- [ ] CloudWatch alarms, deployment hooks, smoke tests, and business KPIs are configured.
- [ ] Pipeline execution mode avoids concurrent updates to the same target/state.
- [ ] Rollback mechanisms are tested for the specific deployment provider.
- [ ] Application/data side effects have idempotency/compensation plans.
- [ ] Logs/notifications do not contain credentials, tokens, secret values, or customer payloads.
- [ ] CloudTrail, CloudWatch dashboards, retention, and incident notifications have owners.
- [ ] ECR/S3/CodeArtifact/logs/test environments have lifecycle/retention policies.
- [ ] Rollback images/artifacts are retained long enough and remain accessible.
- [ ] Pipeline failures, deployment failures, alarm rollbacks, cross-account access, and recovery have been rehearsed.

## 28. Takeaways

**CI/CD is a traceable process from source commit to runtime release.** CodePipeline orchestrates stages/actions; CodeBuild builds and tests; S3 stores pipeline artifacts; ECR stores container images; CodeDeploy/ECS/Lambda/EKS deploy workloads; CloudFormation/CDK/SAM manage infrastructure; CloudWatch and CloudTrail provide signals and auditing.

**Build once and promote the same immutable artifact** across dev/staging/prod. Use commit SHAs and image digests instead of the `latest` tag; store SBOMs/provenance; separate pipeline, build, deployment, CloudFormation, and runtime roles; use CodeConnections or OIDC with scoped trust policies; encrypt artifacts with KMS; and keep secrets out of source code, build logs, and images.

Choose rolling, blue/green, canary, or linear based on availability and data compatibility. Rollback requires metrics, alarms, health checks, and dedicated runbooks for ECS, CodeDeploy, Lambda, EKS, and CloudFormation. Remember that traffic/code rollback does not automatically restore database data or external side effects. Finally, control execution concurrency, artifact retention, logs, build minutes, and temporary capacity so the pipeline is both reliable and cost-effective.

### Official AWS Documentation for Reference

- [AWS CodePipeline User Guide](https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome.html) — stages, actions, artifacts, and execution.
- [CodePipeline pipeline types](https://docs.aws.amazon.com/codepipeline/latest/userguide/pipeline-types.html) — V1/V2 capabilities.
- [CodePipeline cross-Region actions](https://docs.aws.amazon.com/codepipeline/latest/userguide/actions-create-cross-region.html) — artifact stores and cross-Region actions.
- [AWS CodeBuild User Guide](https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html) — build projects, environments, and reports.
- [Buildspec reference](https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html) — phases, artifacts, reports, and cache.
- [CodeBuild environment variables](https://docs.aws.amazon.com/codebuild/latest/userguide/build-env-ref-env-vars.html) — source/build metadata.
- [Amazon ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html) — scan configuration and findings.
- [Amazon ECR image tag mutability](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-tag-mutability.html) — immutable tags.
- [AWS CodeDeploy User Guide](https://docs.aws.amazon.com/codedeploy/latest/userguide/welcome.html) — deployment groups, hooks, and rollback.
- [ECS blue/green deployments with CodeDeploy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html) — target groups and traffic shifting.
- [ECS deployment circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html) — detect failure and rollback.
- [Lambda traffic shifting with CodeDeploy](https://docs.aws.amazon.com/lambda/latest/dg/deploying-lambda.html) — canary/linear deployments.
- [AWS SAM gradual deployments](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/automating-updates-to-serverless-apps.html) — deployment preferences and alarms.
- [Amazon EKS application deployments](https://docs.aws.amazon.com/eks/latest/userguide/deploying.html) — Kubernetes deployment practices.
- [AWS IAM OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — web identity trust.
- [GitHub Actions OIDC in AWS](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — trust policy and role assumption.
- [AWS CodeConnections User Guide](https://docs.aws.amazon.com/dtconsole/latest/userguide/welcome-connections.html) — source provider connections.
- [AWS CodeArtifact User Guide](https://docs.aws.amazon.com/codeartifact/latest/ug/welcome.html) — package repositories.
- [CloudFormation change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html) — preview and execute infrastructure changes.
- [AWS Well-Architected DevOps guidance](https://docs.aws.amazon.com/wellarchitected/latest/devops-guidance/welcome.html) — release engineering, deployment safety, and operations.
