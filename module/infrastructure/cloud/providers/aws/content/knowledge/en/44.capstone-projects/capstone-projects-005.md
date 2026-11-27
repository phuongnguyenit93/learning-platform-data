# Setting Up a Cross-Account CI/CD Pipeline with Automatic Rollback

## Project Objectives

A development team needs to deliver an application to AWS across dev, staging, and production environments. Each environment resides in a separate AWS account to isolate blast radius, access permissions, and data. The team wants every merge to the main branch to run automated tests, build a single immutable artifact, and promote sequentially across accounts. If a release fails or a health metric breaches thresholds, the system must automatically roll back to the most recent stable version.

This capstone builds the pipeline using AWS CodePipeline, AWS CodeBuild, AWS CodeDeploy, Amazon S3, AWS KMS, IAM, and Amazon CloudWatch. The tooling account hosts the pipeline and artifacts. Environment accounts host the application, Auto Scaling groups, CodeDeploy deployment groups, and alarms. CodePipeline assumes cross-account IAM roles to invoke deployment actions in each target account.

This lesson belongs to the **AWS Capstone Projects** chapter of the CLOUD_PROVIDERS_AWS module. Learners will design and implement an auditable release path with production approval and two rollback layers at the deployment and pipeline levels.

After this project, learners will be able to:

- Design separate AWS accounts for tooling, dev, staging, and production.
- Create a GitHub source pipeline using AWS CodeConnections.
- Use CodeBuild to test, build, and package immutable artifacts.
- Configure an S3 artifact bucket and customer-managed KMS key for cross-account access.
- Configure trust policies and IAM permissions for CodePipeline to assume roles in target accounts.
- Deploy applications onto EC2 with CodeDeploy.
- Configure CloudWatch alarms and automatic rollback for CodeDeploy.
- Configure CodePipeline V2 stage rollback on stage failure.
- Add smoke tests, manual approval, and promotion gates.
- Test rollbacks, troubleshoot cross-account failures, and manage artifact retention.
- Design backward-compatible database migrations so application rollbacks remain safe.

## 1. Problem Statement and Acceptance Criteria

Suppose the team operates an order-management REST API service. The application is packaged as a JAR file, runs on Linux EC2 instances inside an Auto Scaling group, and receives traffic via an Application Load Balancer. Each environment has its own endpoints and data.

The pipeline must satisfy these criteria:

| Criterion | Expected Outcome |
|---|---|
| Source control | Merging into `main` triggers the pipeline |
| Quality gate | Unit tests, relevant integration tests, and package checks must pass |
| Artifact | Produces a single artifact with version, commit SHA, and checksum |
| Promotion | The exact same artifact promotes through dev, staging, and production |
| Account isolation | Pipeline uses no static credentials or Administrator permissions in target accounts |
| Approval | Production requires approval from an authorized reviewer |
| Deployment health | CloudWatch alarms monitor errors and application health during deployment |
| Automatic rollback | CodeDeploy redeploys the last known good revision on deployment failure or alarm trigger |
| Pipeline rollback | CodePipeline can roll back a stage to its latest successful execution when the stage fails |
| Auditability | Commit, build ID, artifact digest, deployment ID, and CloudTrail events provide full traceability |

A green pipeline status alone is not enough for acceptance. You must prove the expected version was deployed, health checks passed, the exact same artifact ran across accounts, and rollback genuinely restores the application.

## 2. Multi-Account Architecture

Use one account for tooling and three accounts for environments:

| Account | Responsibility | Core Resources |
|---|---|---|
| Tooling | Orchestrate CI/CD and store artifacts | CodePipeline, CodeBuild, CodeConnections, S3 artifact bucket, KMS key |
| Development | First target for testing new versions | VPC, ALB, EC2 Auto Scaling group, CodeDeploy, CloudWatch |
| Staging | Production-like testing and release verification | VPC, ALB, EC2 Auto Scaling group, CodeDeploy, CloudWatch |
| Production | Serve live users | VPC, ALB, EC2 Auto Scaling group, CodeDeploy, CloudWatch |

Example account IDs used in this lesson:

- Tooling: `111122223333`
- Development: `444455556666`
- Staging: `777788889999`
- Production: `000011112222`

These are illustrative IDs for ARNs and policies. Replace them with real account IDs during implementation.

Each environment maintains its own IAM roles, security boundaries, secrets, networking, and data. Production never shares a database or secrets with staging. Use AWS Organizations and Service Control Policies to enforce account-level guardrails if your organization uses Organizations.

~~~mermaid
flowchart TB
    subgraph TOOL["Tooling account"]
      GH[GitHub repository]
      CON[CodeConnections]
      CP[CodePipeline V2]
      CB[CodeBuild]
      S3[S3 artifact bucket]
      KMS[KMS customer-managed key]
      GH --> CON --> CP
      CP --> CB
      CB --> S3
      S3 --- KMS
    end
    subgraph DEV["Development account"]
      DR[Cross-account deploy role]
      DC[CodeDeploy]
      DA[EC2 Auto Scaling group]
      DM[CloudWatch alarms]
      DR --> DC --> DA
      DC --> DM
    end
    subgraph STAGE["Staging account"]
      SR[Cross-account deploy role]
      SC[CodeDeploy]
      SA[EC2 Auto Scaling group]
      SM[CloudWatch alarms]
      SR --> SC --> SA
      SC --> SM
    end
    subgraph PROD["Production account"]
      PR[Cross-account deploy role]
      PC[CodeDeploy]
      PA[EC2 Auto Scaling group]
      PM[CloudWatch alarms]
      PR --> PC --> PA
      PC --> PM
    end
    CP -->|AssumeRole + artifact| DR
    CP -->|AssumeRole + artifact| SR
    CP -->|AssumeRole + artifact| PR
~~~

The pipeline and artifacts reside in the tooling account. Target accounts grant only the permissions required by the pipeline role and CodeDeploy agent. This layout minimizes where release permissions live and separates build permissions from production deployment permissions.

## 3. End-to-End CI/CD Flow

The pipeline executes these steps in sequence:

1. A developer opens a pull request and completes code review.
2. Merging to `main` triggers the source action via CodeConnections.
3. CodeBuild runs tests, performs quality checks, and packages the artifact.
4. CodePipeline deploys the artifact into the development account.
5. Smoke tests verify endpoints, health checks, and core business flows.
6. The pipeline deploys the same artifact into the staging account.
7. Staging runs integration tests, acceptance tests, and appropriate performance checks.
8. Manual approval requires the release owner to review the commit, test reports, artifact digest, and staging results.
9. CodePipeline assumes the role in the production account and invokes CodeDeploy.
10. CodeDeploy rolls out per the deployment configuration, monitors CloudWatch alarms, and automatically rolls back if triggered.
11. Production smoke tests verify the release. If the stage fails, CodePipeline V2 can roll back the stage to its prior successful execution.
12. The pipeline records the deployment ID, artifact digest, and final result.

~~~mermaid
flowchart TD
    A[Merge to main] --> B[CodeConnections source]
    B --> C[CodeBuild: test, scan, package]
    C --> D[Immutable BuildArtifact]
    D --> E[Deploy dev account]
    E --> F[Dev smoke tests]
    F --> G[Deploy staging account]
    G --> H[Integration and acceptance tests]
    H --> I{Manual approval}
    I -->|Rejected| X[Stop release]
    I -->|Approved| J[Deploy production account]
    J --> K[CodeDeploy + CloudWatch alarms]
    K --> L[Production smoke tests]
    L --> M[Record release evidence]
    K -->|Deployment failure or alarm| R[CodeDeploy automatic rollback]
    L -->|Stage failure| S[CodePipeline stage rollback]
~~~

The pipeline builds the artifact only once. Never rebuild source code separately for staging or production, because doing so can produce a binary different from the one already tested.

## 4. Separation of Responsibilities Across Services

| Service | Role in Project |
|---|---|
| AWS CodeConnections | Connect the GitHub repository to CodePipeline via GitHub App |
| AWS CodePipeline | Orchestrate source, build, approval, deploy, and stage rollback |
| AWS CodeBuild | Run tests, build package, generate checksums, and output artifact |
| Amazon S3 | Store pipeline-generated artifacts |
| AWS KMS | Encrypt artifacts using a customer-managed key |
| AWS IAM / STS | Grant permissions and assume cross-account roles |
| AWS CodeDeploy | Deploy revisions to EC2 and perform automatic rollback |
| Amazon CloudWatch | Collect metrics, evaluate alarms, and support deployment verification |
| Amazon SNS | Send approval or deployment notifications if configured |
| AWS CloudTrail | Log API calls and permission/configuration changes |

CodePipeline orchestrates actions. CodeDeploy manages revision swaps on compute targets. CloudWatch provides health signals. IAM/STS governs identities and cross-account access.

## 5. Preparing the Repository and Artifact Structure

Example repository layout:

~~~text
orders-api/
├── pom.xml
├── src/
│   ├── main/
│   └── test/
├── appspec.yml
├── buildspec.yml
└── scripts/
    ├── prepare.sh
    ├── configure.sh
    ├── start.sh
    └── validate.sh
~~~

The build output is packaged as:

~~~text
BuildArtifact.zip
├── appspec.yml
├── SHA256SUMS
├── app/
│   └── orders-api.jar
└── scripts/
    ├── prepare.sh
    ├── configure.sh
    ├── start.sh
    └── validate.sh
~~~

The artifact must include everything CodeDeploy needs. Never place AWS access keys, passwords, database credentials, or production configuration into the ZIP. At runtime, the application fetches environment-specific configuration from Systems Manager Parameter Store or Secrets Manager using its IAM role.

Version artifacts by commit SHA or build ID. Record SHA-256 checksums so you can verify identical artifacts across promoted accounts.

## 6. Connecting GitHub with CodeConnections

In the tooling account:

1. Open Developer Tools / Connections in the AWS Console.
2. Create a connection to GitHub using the GitHub App.
3. Grant access only to the required organization and repository.
4. Complete authorization and wait for the connection status to become `AVAILABLE`.
5. Save the connection ARN.
6. Create the source action in CodePipeline specifying repository, branch, and connection ARN.

CodePipeline uses the `CodeStarSourceConnection` action provider for GitHub App connections. The provider name in the pipeline structure remains `CodeStarSourceConnection`, even though the service console now uses the name CodeConnections.

Never store personal access tokens in `buildspec.yml` or the repository. If connections are unavailable in a chosen Region, check current regional availability and pick a supported Region before designing the pipeline.

## 7. Artifact Store and Encryption Design

CodePipeline uses an S3 bucket as its artifact store. For cross-account actions, create a customer-managed KMS key in the same Region as the pipeline and artifact bucket.

Example:

- Bucket: `codepipeline-ap-southeast-1-111122223333`
- Key ARN: `arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555`

Bucket configuration:

- Block Public Access enabled.
- Bucket versioning enabled.
- Default encryption using the customer-managed KMS key.
- Bucket policy allowing access only to identified principals.
- Require TLS for all requests.
- Lifecycle policy retaining artifacts long enough for rollbacks and audits.
- Never delete artifacts belonging to executions still within the rollback window.

The KMS key policy must allow the pipeline service role and cross-account roles that read artifacts. Each target role's IAM identity policy must also permit using the key. With cross-account KMS, adding an identity policy without updating the key policy is insufficient.

KMS keys are regional resources. If a pipeline executes cross-Region actions, each action Region needs its own artifact bucket and key; CodePipeline manages artifact replication across Regions. This project uses a single Region to reduce complexity.

## 8. Artifact Constraints in Cross-Account Pipelines

CodePipeline enforces an important rule: an action in another account can consume an artifact created in the pipeline account. An artifact can also be reused by actions within the same account where it was produced. You cannot pass an artifact directly from one target account to another target account when both differ from the pipeline account.

Therefore, this architecture keeps the original artifact in the tooling account and lets actions in dev, staging, and production read that same artifact. Do not deploy to dev and then pull the artifact from the dev account for staging.

When a cross-account action needs an artifact:

1. CodePipeline assumes the role in the target account.
2. The target role is permitted to read objects in the artifact bucket.
3. The target role is permitted to decrypt objects with the KMS key.
4. CodeDeploy receives the revision and deploys to targets in the target account.
5. The CodeDeploy agent on EC2 also needs permission to read the artifact and decrypt with the key when downloading the revision.

Verify both the action role and the EC2 instance profile. Granting permissions only to the action role can let the pipeline create the deployment while the agent on EC2 fails to download the revision.

## 9. Designing Cross-Account IAM Roles

There are at least four distinct role types:

| Role | Account | Trust Principal | Responsibility |
|---|---|---|---|
| `CodePipelineServiceRole` | Tooling | `codepipeline.amazonaws.com` | Orchestrate the pipeline and assume target roles |
| `CodePipelineDeployRole` | Dev/Staging/Prod | `CodePipelineServiceRole` in tooling | Allow pipeline actions to deploy into target accounts |
| `CodeDeployServiceRole` | Dev/Staging/Prod | `codedeploy.amazonaws.com` | Manage deployment targets and lifecycle |
| `CodeDeployInstanceRole` | Dev/Staging/Prod | `ec2.amazonaws.com` | Allow the EC2 agent to download artifacts and emit logs |

Never reuse one role for every responsibility. The pipeline role needs no permission to log into EC2; the instance profile needs no permission to edit the pipeline; the CodeDeploy service role needs no access to the source repository.

## 10. Trust Policy for the Cross-Account Deploy Role

Example trust policy in the production account trusting only the tooling account's pipeline service role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustCentralCodePipeline",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/CodePipelineServiceRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Do not set the principal to the entire account root when only one pipeline service role should deploy. The trust policy defines who can assume the role; the role's permission policy defines what actions it can take once assumed.

`CodePipelineServiceRole` in the tooling account needs an identity policy allowing `sts:AssumeRole` on the exact three deploy roles:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeEnvironmentDeployRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
        "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
        "arn:aws:iam::000011112222:role/CodePipelineDeployRole"
      ]
    }
  ]
}
~~~

Each target account can use the same role name, but its ARN and policies must bind to that account's resources. In production, grant only the actions required for the specific CodeDeploy application and deployment group.

## 11. Permissions for the Cross-Account Deploy Role

The role in each target account needs permissions to:

- Create deployments and check deployment status.
- Read application revisions and deployment configurations.
- Register revisions when required by the action provider.
- Read artifact objects in the tooling account's S3 bucket.
- Call `kms:Decrypt` and `kms:DescribeKey` on the artifact key.
- Access required CodeDeploy resources by ARN.

AWS CodePipeline publishes sample policies for cross-account CodeDeploy actions. Some CodeDeploy APIs require broader resource scoping than others. Consult the Service Authorization Reference and scope resources to the application and deployment group wherever supported.

The CodeDeploy service role is a separate role. It is assumed by the CodeDeploy service and holds permissions to manage lifecycle operations across EC2, Auto Scaling, and load balancers for the deployment group.

## 12. S3 Bucket Policy for Artifact Access

The tooling account's bucket policy must allow designated roles to read artifacts. Abbreviated example:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowTargetRolesReadArtifacts",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
          "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodeDeployInstanceRole"
        ]
      },
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::codepipeline-ap-southeast-1-111122223333/*"
    },
    {
      "Sid": "AllowTargetRolesListBucket",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
          "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodeDeployInstanceRole"
        ]
      },
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::codepipeline-ap-southeast-1-111122223333"
    }
  ]
}
~~~

This is an illustrative policy for roles reading artifacts. Add or adjust principals per account and actual action type (including dev and staging instance roles if applicable). The pipeline service role still needs permission to write pipeline artifacts. Never open the bucket to anonymous users or entire external accounts.

If the bucket uses `Bucket owner enforced` Object Ownership, object ACLs are unnecessary. Verify compatibility with action providers and existing bucket policies before altering current bucket settings.

## 13. KMS Key Policy for Cross-Account Decryption

In the tooling account, the KMS key policy must grant decryption access to target-account roles. Example statement granting artifact decryption:

~~~json
{
  "Sid": "AllowEnvironmentRolesToDecryptPipelineArtifacts",
  "Effect": "Allow",
  "Principal": {
    "AWS": [
      "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
      "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
      "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
      "arn:aws:iam::000011112222:role/CodeDeployInstanceRole"
    ]
  },
  "Action": [
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*"
}
~~~

In the full policy, preserve key administration statements and key usage permissions for `CodePipelineServiceRole`. Target roles also require an IAM identity policy permitting `kms:Decrypt` on the exact key ARN. Never grant key administration permissions to deployment roles.

If a CodePipeline action outputs an artifact from a target account, add the required encrypt/write permissions. Since this CodeDeploy action produces no output artifact, read and decrypt permissions are the focus.

## 14. Preparing EC2 and CodeDeploy in Each Account

Each environment requires:

1. An appropriate VPC and subnets.
2. An Application Load Balancer and target group if the app receives traffic via ALB.
3. An EC2 Auto Scaling group hosting application instances.
4. The CodeDeploy agent installed and running on EC2.
5. An EC2 instance profile permitted to read artifacts from S3 and decrypt using the KMS key.
6. A CodeDeploy application and deployment group.
7. A CodeDeploy service role permitted to manage targets.
8. CloudWatch log groups, metrics, and alarms.
9. Security groups permitting only required traffic.
10. Parameter Store/Secrets Manager entries for environment-specific configuration and secrets.

The CodeDeploy agent needs connectivity to service endpoints and the artifact store. Verify routes, DNS, NAT Gateways, or VPC endpoints as appropriate. If EC2 instances live in private subnets, confirm paths to S3 and required endpoints.

Never embed credentials in user data or AMIs. The EC2 instance profile supplies temporary credentials via the metadata service.

## 15. Creating CodeDeploy Applications and Deployment Groups

Create a CodeDeploy application for the `orders-api` service in each account. Select the `EC2/On-Premises` compute platform for the deployment group and associate it with the corresponding Auto Scaling group or tag group.

For this capstone, start with in-place deployments using `OneAtATime` to limit concurrent instance updates. When further downtime reduction is required, evaluate blue/green deployments with load balancer traffic shifting.

Deployment group components:

- `ApplicationName`: CodeDeploy application name.
- `DeploymentGroupName`: environment-specific group name.
- `ServiceRoleArn`: CodeDeploy service role in the target account.
- `DeploymentConfigName`: e.g., `CodeDeployDefault.OneAtATime`.
- `Ec2TagFilters` or `AutoScalingGroups`: identify target instances.
- `AlarmConfiguration`: CloudWatch alarms monitored during deployment.
- `AutoRollbackConfiguration`: events that trigger rollback.
- `DeploymentStyle`: in-place or blue/green depending on the design.

Application names can match across accounts, while resource ARNs remain distinct. Pipeline actions use `roleArn` in the target account to invoke the corresponding application and deployment group.

## 16. AppSpec and Lifecycle Hooks

CodeDeploy uses `appspec.yml` to determine which files to copy and which scripts to run at each lifecycle event.

Example `appspec.yml` for Linux:

~~~yaml
version: 0.0
os: linux
files:
  - source: app/orders-api.jar
    destination: /opt/orders-api/

hooks:
  BeforeInstall:
    - location: scripts/prepare.sh
      timeout: 120
      runas: root

  AfterInstall:
    - location: scripts/configure.sh
      timeout: 120
      runas: root

  ApplicationStart:
    - location: scripts/start.sh
      timeout: 120
      runas: root

  ValidateService:
    - location: scripts/validate.sh
      timeout: 60
      runas: root
~~~

Hook responsibilities:

- `BeforeInstall` prepares directories and file permissions.
- `AfterInstall` updates symlinks or runtime configuration.
- `ApplicationStart` starts the service.
- `ValidateService` calls the health endpoint and exits non-zero if the service is unhealthy.

Scripts must be idempotent, have timeouts, log clearly, and never delete application data. Never print secrets to stdout because CodeDeploy deployment logs may be readable by multiple operations team members.

## 17. Configuring CloudWatch Alarms for Deployments

Alarms should reflect customer impact or target health. Examples:

| Alarm | Signal | Action |
|---|---|---|
| `orders-prod-5xx` | HTTP 5xx spike on ALB or application metric | Stop deployment and roll back |
| `orders-prod-latency` | p95 response time breaches SLO | Stop rollout |
| `orders-prod-healthy-hosts` | `HealthyHostCount` drops below safe floor | Stop deployment |
| `orders-prod-process-errors` | Application error metric rises | Stop deployment |

Use metrics with appropriate baselines and evaluation periods. Overly sensitive alarms may trigger false rollbacks on brief spikes; overly loose alarms let errors affect users for too long.

CodeDeploy deployment groups attach CloudWatch alarms. For EC2 deployments, monitor instance or Auto Scaling group metrics; depending on architecture, add ALB/application metrics to observe request health.

Before deploying, alarms must exist and be in an evaluable state. Where strict safety is required, configure deployments not to proceed if CodeDeploy cannot read alarm states.

## 18. CodeDeploy Automatic Rollback

CodeDeploy can roll back automatically when:

- A deployment fails.
- One or more CloudWatch alarms attached to the deployment group enter `ALARM` state.

CodeDeploy performs rollback by redeploying the previously succeeded revision. This creates a new deployment with a new deployment ID, rather than rewinding the failed deployment ID.

Example deployment group configuration snippet:

~~~yaml
AlarmConfiguration:
  Enabled: true
  IgnorePollAlarmFailure: false
  Alarms:
    - Name: orders-prod-5xx
    - Name: orders-prod-latency

AutoRollbackConfiguration:
  Enabled: true
  Events:
    - DEPLOYMENT_FAILURE
    - DEPLOYMENT_STOP_ON_ALARM
~~~

This is an illustrative snippet; place it inside an `AWS::CodeDeploy::DeploymentGroup` resource or equivalent deployment group configuration. Create the alarms before associating them with the group.

If the very first deployment fails with no prior successful revision, CodeDeploy has no last-known-good revision to redeploy. Bootstrap an initial stable release before relying on automatic rollback.

## 19. CodePipeline V2 Automatic Stage Rollback

CodePipeline V2 supports automatic stage rollback when a stage fails. When the failure condition triggers, the stage rolls back to the most recent successful execution of that stage.

Example stage configuration:

~~~json
{
  "name": "DeployProduction",
  "actions": [
    {
      "name": "DeployOrdersApi",
      "actionTypeId": {
        "category": "Deploy",
        "owner": "AWS",
        "provider": "CodeDeploy",
        "version": "1"
      },
      "configuration": {
        "ApplicationName": "orders-api",
        "DeploymentGroupName": "orders-prod"
      },
      "inputArtifacts": [
        {
          "name": "BuildArtifact"
        }
      ],
      "outputArtifacts": [],
      "roleArn": "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
      "runOrder": 1
    }
  ],
  "onFailure": {
    "result": "ROLLBACK"
  }
}
~~~

This is a stage fragment, not a complete pipeline definition. Rollback configuration belongs to the V2 pipeline structure.

Key conditions to remember:

- Stage rollback works only when a prior successful execution exists under the same pipeline structure version.
- After adding or modifying pipeline structure, run at least one successful execution before relying on automatic stage rollback for the new structure.
- `PARALLEL` execution mode does not support stage rollback. Use `SUPERSEDED` or `QUEUED` if rollback is required.
- Stage rollback starts a new execution using the target execution's revisions/artifacts.
- Stage rollback does not undo arbitrary external side effects outside the pipeline.

In this capstone, use `QUEUED` `executionMode` so releases run sequentially without multiple executions contending over production deployment.

## 20. Two Rollback Layers Handle Different Scenarios

| Mechanism | Trigger | Scope | Result |
|---|---|---|---|
| CodeDeploy automatic rollback | Deployment failure or CloudWatch alarm | Application revision inside a deployment group | Redeploys the last known good revision |
| CodePipeline stage rollback | Stage failure | Pipeline stage | Reruns the stage using the prior successful execution |
| Manual rollback | Operator decision | Selected deployment or stage | Restores the chosen revision |
| Infrastructure rollback | CloudFormation resource update failure | CloudFormation-managed stack/resources | CloudFormation rolls back stack updates per stack behavior |

CodeDeploy rollback should act as the primary safeguard for deployment health. CodePipeline stage rollback adds stage-level recovery if a deploy action or an in-stage smoke test fails.

Place the deploy action and smoke-test action in the same stage if a smoke-test failure should fail that stage and trigger stage rollback. If smoke tests live in a separate stage, rolling back that test stage does not automatically revert the earlier deployment stage.

## 21. Rollback Limitations and Database Migrations

Rolling back the application does not roll back data.

For example, a release adds a database column or alters a message format. If the older application cannot read the new schema, CodeDeploy may restore the old binary while the service continues failing.

Use the expand/contract strategy:

1. **Expand:** add new columns/tables/indexes in a way compatible with the old application.
2. Deploy new code capable of reading both old and new schemas.
3. Gradually shift reads/writes to the new structure.
4. Monitor and verify data integrity.
5. **Contract:** remove old fields or schemas only after the previous version no longer needs rollback support.

Never automatically roll back destructive database migrations. Every data-impacting migration requires backups, compatibility review, and its own recovery plan.

CodeDeploy also does not undo side effects created by lifecycle scripts. Files created outside CodeDeploy's managed file list or database mutations are not reverted merely because a deployment rolls back.

## 22. Building and Testing with CodeBuild

The CodeBuild action receives `SourceArtifact`, executes `buildspec.yml` inside a build container, and outputs `BuildArtifact` for downstream actions.

Sample `buildspec.yml` for a Java Maven application:

~~~yaml
version: 0.2

phases:
  install:
    runtime-versions:
      java: corretto21

  pre_build:
    commands:
      - mvn -B -ntp clean verify

  build:
    commands:
      - mkdir -p deploy/app deploy/scripts
      - cp target/orders-api.jar deploy/app/orders-api.jar
      - cp appspec.yml deploy/appspec.yml
      - cp scripts/prepare.sh deploy/scripts/prepare.sh
      - cp scripts/configure.sh deploy/scripts/configure.sh
      - cp scripts/start.sh deploy/scripts/start.sh
      - cp scripts/validate.sh deploy/scripts/validate.sh
      - sha256sum deploy/app/orders-api.jar > deploy/SHA256SUMS

reports:
  unit-tests:
    files:
      - target/surefire-reports/TEST-*.xml
    file-format: JUNITXML

artifacts:
  base-directory: deploy
  files:
    - "**/*"
  discard-paths: no
~~~

This example assumes Maven builds `target/orders-api.jar`. Adjust paths to match your actual build output.

The CodeBuild service role needs permissions to read input artifacts, write output artifacts, write CloudWatch Logs, and reach dependency repositories. Never grant production deploy permissions to the CodeBuild role when CodePipeline action roles handle deployment.

## 23. Creating CodePipeline V2

The pipeline requires these primary stages:

- `Source`: `CodeStarSourceConnection`.
- `Build`: `CodeBuild`.
- `DeployDev`: CodeDeploy action using the dev cross-account role.
- `DeployStaging`: CodeDeploy action using the staging cross-account role.
- `ApproveProduction`: Manual approval.
- `DeployProduction`: CodeDeploy action using the production cross-account role with stage rollback.

Pipeline properties to use:

~~~json
{
  "pipelineType": "V2",
  "executionMode": "QUEUED"
}
~~~

This is a snippet of pipeline properties, not the full pipeline JSON. When provisioning via CloudFormation or CLI, combine these properties with `roleArn`, `artifactStore`, and stage definitions.

Example source action:

~~~json
{
  "name": "GitHubSource",
  "actionTypeId": {
    "category": "Source",
    "owner": "AWS",
    "provider": "CodeStarSourceConnection",
    "version": "1"
  },
  "configuration": {
    "ConnectionArn": "arn:aws:codestar-connections:ap-southeast-1:111122223333:connection/11111111-2222-3333-4444-555555555555",
    "FullRepositoryId": "example-org/orders-api",
    "BranchName": "main",
    "OutputArtifactFormat": "CODE_ZIP"
  },
  "outputArtifacts": [
    {
      "name": "SourceArtifact"
    }
  ],
  "inputArtifacts": [],
  "runOrder": 1
}
~~~

Example Build action:

~~~json
{
  "name": "BuildAndTest",
  "actionTypeId": {
    "category": "Build",
    "owner": "AWS",
    "provider": "CodeBuild",
    "version": "1"
  },
  "configuration": {
    "ProjectName": "orders-api-build"
  },
  "inputArtifacts": [
    {
      "name": "SourceArtifact"
    }
  ],
  "outputArtifacts": [
    {
      "name": "BuildArtifact"
    }
  ],
  "runOrder": 1
}
~~~

These JSON blocks are action fragments. When assembling the full pipeline, keep artifact names consistent between `outputArtifacts` and `inputArtifacts`.

## 24. Cross-Account CodeDeploy Action

In each deploy stage, the action specifies the target account's application/deployment group and the `roleArn` of the cross-account deploy role.

Example:

~~~json
{
  "name": "DeployStaging",
  "actions": [
    {
      "name": "DeployOrdersApi",
      "actionTypeId": {
        "category": "Deploy",
        "owner": "AWS",
        "provider": "CodeDeploy",
        "version": "1"
      },
      "configuration": {
        "ApplicationName": "orders-api",
        "DeploymentGroupName": "orders-staging"
      },
      "inputArtifacts": [
        {
          "name": "BuildArtifact"
        }
      ],
      "outputArtifacts": [],
      "roleArn": "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
      "runOrder": 1
    }
  ],
  "onFailure": {
    "result": "ROLLBACK"
  }
}
~~~

The `roleArn` must belong to the account that owns the CodeDeploy application and deployment group. `CodePipelineServiceRole` in the tooling account must be permitted to assume that role, and the target role's trust policy must trust that exact service role.

Never reuse a staging action role to deploy into production. Each account has its own role and resource scope.

## 25. Manual Approval Before Production

A manual approval action creates a gate before the production stage. Approvers should inspect:

- Commit SHA and merged pull request.
- Build ID and artifact checksum.
- Unit and integration test reports.
- Dev and staging deployment results.
- CloudWatch alarm states and smoke tests.
- Release notes and database changes.
- Rollback revision and on-call owner.

Example action:

~~~json
{
  "name": "ApproveProduction",
  "actions": [
    {
      "name": "ReleaseApproval",
      "actionTypeId": {
        "category": "Approval",
        "owner": "AWS",
        "provider": "Manual",
        "version": "1"
      },
      "configuration": {
        "CustomData": "Review staging results, artifact digest, migration plan and rollback readiness.",
        "ExternalEntityLink": "https://example.invalid/release-review"
      },
      "inputArtifacts": [],
      "outputArtifacts": [],
      "runOrder": 1
    }
  ]
}
~~~

Replace the placeholder link with your internal release review portal. You can configure an SNS topic to notify approvers. Manual approval does not replace code review or security gates.

## 26. Promoting the Same Artifact Across Accounts

The artifact is created once in the Build stage and reused across every environment.

Example release metadata:

~~~json
{
  "service": "orders-api",
  "version": "1.8.4",
  "commit": "a1b2c3d4e5f6",
  "buildId": "orders-api:1042",
  "artifactSha256": "replace-with-real-sha256",
  "createdAt": "2026-11-20T08:30:00Z"
}
~~~

The pipeline can store this metadata alongside the artifact or attach it to a release record. In each account, verify the JAR's checksum matches the built artifact.

Never rebuild source code in the production stage. If staging passes but production compiles a separate binary, staging test results no longer validate the binary running in production.

## 27. Managing Environment Configuration and Secrets

Separate the application artifact from environment configuration.

| Data | Appropriate Store |
|---|---|
| Database endpoint | Parameter Store or configuration service |
| Database password | Secrets Manager |
| API token | Secrets Manager |
| Feature flag | AppConfig or appropriate configuration store |
| Public runtime setting | Parameter Store |
| Deployment metadata | Pipeline artifact or release record |

The application on EC2 uses its instance profile to read parameters and secrets from its environment's account and Region. Never copy production secrets into dev or staging.

When secrets rotate, verify the application refreshes credentials and connection pools cleanly. Secret rotation is a change in itself requiring monitoring and a rollback plan.

## 28. Observing the Pipeline and Deployments

Monitor both the pipeline and the application:

| Layer | Metrics / Events | Purpose |
|---|---|---|
| CodePipeline | `PipelineExecution`, stage/action status | Know where a release paused or failed |
| CodeBuild | Build duration, failed builds, report summary | Detect test/build failures |
| CodeDeploy | Deployment status, lifecycle events, rollback events | Track deployment progress |
| EC2 / Auto Scaling | Healthy instances, CPU, memory, status checks | Assess compute health |
| ALB | Target 5xx, target response time, `HealthyHostCount` | Measure request health |
| Application | Error rate, p95/p99 latency, business success rate | Verify customer impact |
| IAM / Audit | CloudTrail `AssumeRole`, CodeDeploy API calls | Trace principals and actions |

Include release ID, commit SHA, and deployment ID in application logs and metrics whenever possible. When an alarm fires, the on-call engineer can correlate metrics directly to the running version.

CloudTrail records API calls such as `AssumeRole`, `CreateDeployment`, and deployment group updates. CloudWatch Logs retains application logs and lifecycle script output per retention policy.

## 29. Testing Cross-Account Permissions

Before running the full pipeline, verify each permission:

1. `CodePipelineServiceRole` has `sts:AssumeRole` on target deploy roles.
2. Each deploy role's trust policy trusts only `CodePipelineServiceRole`.
3. The deploy role can read artifact objects in S3.
4. The deploy role can decrypt artifacts using the KMS key.
5. The CodeDeploy action can invoke the target application and deployment group.
6. The EC2 instance profile can read artifacts and decrypt with the KMS key.
7. The CodeDeploy service role can manage deployment targets.
8. EC2 instances can reach CodeDeploy endpoints and health dependencies.

Use STS to confirm identity after assuming a role. If `AssumeRole` succeeds but deployment fails, inspect the target role's permission policy and resource policies. If CodeDeploy creates a deployment but instances fail to download the revision, inspect the instance profile, S3 bucket policy, KMS key policy, network routes, and agent logs.

## 30. Testing Automatic Rollback in Development or Staging

Never test rollback by intentionally breaking production.

Test scenario:

1. Deploy a known-good version to development.
2. Verify the health endpoint and record the deployment ID.
3. Build a test revision whose `ValidateService` hook intentionally fails.
4. Run the pipeline into development.
5. Verify CodeDeploy marks the deployment as failed.
6. Verify automatic rollback triggers a new deployment using the prior successful revision.
7. Check ALB target health, application version, and request success.
8. Repeat using a CloudWatch alarm trigger in staging.
9. Verify pipeline stage statuses and rollback history.

Use a dedicated test alarm with an easily triggered threshold in staging. Never alter production alarms just to run a rollback drill.

## 31. Testing CodePipeline Stage Rollback

Stage rollback requires a prior successful execution under the same pipeline structure version.

Procedure:

1. Create a V2 pipeline and configure `onFailure.result` to `ROLLBACK` on the stage.
2. Run the pipeline to completion at least once so the stage has a known-good execution.
3. Produce a test build/revision that causes the smoke-test action inside the deploy stage to fail.
4. Run the pipeline.
5. Verify the stage fails and triggers rollback.
6. Confirm the stage reverts to the artifact/revision from the most recent successful execution.
7. Inspect execution history for the new rollback execution.
8. Verify the application remains on the stable version.

If the pipeline structure was recently modified, older executions may not qualify as rollback targets. Complete one successful execution on the current structure before testing rollback.

## 32. Testing Manual Approval and Promotion Gates

Create a test release and verify:

- The pipeline pauses at the Approval stage.
- Users without approval permissions cannot approve.
- Authorized approvers can inspect the commit, test results, and artifact digest.
- Rejecting stops the pipeline before production.
- Approving allows the production stage to start.
- The production action assumes the right cross-account role.
- The production artifact digest matches staging.

Never place approval credentials or tokenized external links inside `CustomData`. Approval messages should contain only metadata and links to an access-controlled release review system.

## 33. Failure Scenarios and Remediation

| Symptom | Common Cause | Where to Check |
|---|---|---|
| Source action does not run | Connection not `AVAILABLE` or missing repo access | Check connection status, repository access, and branch |
| CodeBuild fails to read source | Pipeline/CodeBuild role lacks artifact permissions | Check CodeBuild service role and input artifact |
| `AssumeRole` `AccessDenied` | Wrong principal in trust policy or missing `sts:AssumeRole` | Verify pipeline service role ARN and policies |
| S3 `AccessDenied` | Bucket policy or role policy denies access | Check object ARN, bucket ARN, and principal |
| KMS `AccessDenied` | Key policy or identity policy missing decrypt permission | Check key ARN, Region, and role |
| CodeDeploy action cannot find group | Wrong application/group name or account/Region | Verify resources inside the target account |
| EC2 fails to download revision | Instance profile lacks S3/KMS access or network path | Check agent logs, instance profile, S3/KMS endpoints |
| Deployment fails in hook | Script error, missing dependency, or OS permission | Check lifecycle event logs |
| Alarm not evaluated | Wrong alarm name/Region or CodeDeploy role lacks permissions | Check `AlarmConfiguration` and service role |
| Rollback does not trigger | Rollback events not enabled or no known-good revision | Check `AutoRollbackConfiguration` and deployment history |
| Pipeline stage does not roll back | Pipeline not V2 or in `PARALLEL` mode | Check `pipelineType` and `executionMode` |
| Stage rollback has no target | No successful execution under current structure version | Run one successful execution on the current pipeline structure |
| Old app still fails after rollback | Incompatible database/schema or side effects | Check migrations and backward compatibility |
| Staging passes but production fails | Differences in config, quotas, networking, or dependencies | Compare environment configs, IAM, and networking |

## 34. Ordered Troubleshooting Workflow

When a cross-account deployment fails, investigate in order:

1. **Pipeline execution:** identify the failing stage/action, execution ID, and error code.
2. **Account/Region:** verify the action runs in the intended account and Region.
3. **AssumeRole:** check the actual principal and trust relationship.
4. **Artifact:** verify S3 bucket, object key, version, and artifact checksum.
5. **KMS:** inspect key ARN, key policy, identity policy, and Region.
6. **CodeDeploy:** check application, deployment group, deployment ID, and lifecycle events.
7. **EC2 agent:** inspect agent status, instance profile, networking, and deployment logs.
8. **Application:** check systemd, health endpoints, ALB target health, and dependencies.
9. **Rollback:** verify CodeDeploy or CodePipeline rollback events and restored revision.

Never fix policy errors by granting `AdministratorAccess` to every role. Add only the specific APIs, resource ARNs, and principals needed. Record policy changes and re-run negative tests to confirm permissions were not over-broadened.

## 35. Security and Change Control

Security principles:

- The production account accepts deployments only from the approved pipeline role.
- Target trust policies trust only the specific `CodePipelineServiceRole`.
- Pipeline action roles hold permissions only on the required CodeDeploy application and deployment group.
- EC2 instance profiles read only required artifacts, logs, and secrets.
- The S3 artifact bucket is private and enforces TLS.
- KMS keys are administered separately; deployment roles hold no key admin permissions.
- The GitHub repository enforces branch protection and code reviews.
- `buildspec.yml` lives in the reviewed repository; disallow arbitrary action-level overrides.
- Secrets use Secrets Manager/Parameter Store, never plaintext environment variables.
- CloudTrail and CodeDeploy events are retained for auditing.
- Production deployments require approval and release windows when mandated by the workload.

Because the pipeline can deploy to production, permissions to modify the pipeline or alter `buildspec.yml` effectively grant production impact. Protect pipeline definitions with reviews, IaC, and restricted update permissions.

## 36. Cost Management and Artifact Retention

Project costs stem from CodeBuild build minutes, CodePipeline actions, S3 artifact storage, KMS requests, EC2/ALB capacity, CloudWatch logs/alarms, and CodeDeploy target infrastructure.

Controls:

- Use build caching for dependencies to shorten build times.
- Size CodeBuild compute appropriately for the workload.
- Configure EC2 Auto Scaling group minimum capacity appropriately per environment.
- Stop or scale down dev/staging outside working hours if architecture allows.
- Configure retention on CloudWatch Logs.
- Apply S3 lifecycle policies to older artifacts while keeping enough history for rollbacks and audits.
- Monitor build durations and failed builds to avoid repeated retry costs.
- Apply cost allocation tags for project, environment, and owner.

Never delete the artifact corresponding to the current last-known-good revision. Retention must outlast the rollback window and satisfy organizational audit requirements.

## 37. Capstone Implementation Lab

Perform this lab inside approved AWS test accounts. Start with tooling and development; add the production account only after cross-account permissions and rollbacks are proven.

### Step 1: Prepare Accounts

- Identify tooling, dev, staging, and prod account IDs.
- Choose a shared Region.
- Provision VPC, ALB, and EC2 Auto Scaling group in each environment account.
- Install the CodeDeploy agent on EC2.
- Create the CodeDeploy service role and instance profile.
- Record all role ARNs.

### Step 2: Provision Artifact Infrastructure in Tooling

- Create the S3 artifact bucket.
- Enable Block Public Access and versioning.
- Create the customer-managed KMS key.
- Configure `CodePipelineServiceRole`.
- Grant S3/KMS access to the pipeline service role.
- Prepare bucket and key policies for target roles.

### Step 3: Set Up Cross-Account Roles

In each environment account:

- Create `CodePipelineDeployRole`.
- Trust only `CodePipelineServiceRole` in tooling.
- Grant least-privilege CodeDeploy permissions.
- Grant `s3:GetObject` and `kms:Decrypt` for artifacts.
- Grant S3/KMS read permissions to `CodeDeployInstanceRole`.
- Verify `AssumeRole` and artifact access.

### Step 4: Create CodeDeploy Resources

- Create CodeDeploy application `orders-api`.
- Create environment-specific deployment groups.
- Attach the Auto Scaling group.
- Choose the deployment configuration.
- Create CloudWatch alarms.
- Enable automatic rollback on deployment failure and alarms.

### Step 5: Set Up Source and Build

- Create the CodeConnections GitHub connection.
- Create the CodeBuild project and service role.
- Commit `buildspec.yml`, `appspec.yml`, and lifecycle scripts to the repository.
- Run build and tests directly before wiring up the pipeline.
- Verify `BuildArtifact` contains expected files and checksums.

### Step 6: Create CodePipeline V2

- Add the Source action.
- Add the CodeBuild action.
- Add `DeployDev` using the dev role ARN.
- Add smoke tests in the deploy stage.
- Add `DeployStaging` using the staging role ARN.
- Add integration tests and acceptance gates.
- Add Manual approval.
- Add `DeployProduction` using the production role ARN.
- Set `onFailure.result` to `ROLLBACK` on deploy stages requiring stage rollback.

### Step 7: Test a Successful Release

- Merge a small commit to `main`.
- Monitor source, build, dev deployment, and staging deployment.
- Approve production.
- Verify the application reports the expected version.
- Compare the JAR's SHA-256 checksum across environments.
- Record the execution ID and deployment ID.

### Step 8: Test Rollbacks

- In dev, deploy a revision with a failing health check.
- Verify CodeDeploy automatic rollback.
- In staging, trigger a post-deploy smoke test failure.
- Verify CodePipeline stage rollback.
- Record rollback duration and application health.
- Restore test alarms and a stable revision.

### Step 9: Clean Up

- Delete the pipeline and build project when the lab is no longer needed.
- Delete CodeDeploy deployment groups and applications in dependency order.
- Delete test EC2/ALB/Auto Scaling groups and VPCs if no longer needed.
- Retain reports and logs per chosen retention rules.
- Never delete KMS keys or artifacts required for auditing before confirming retention policies.

## 38. Release and Rollback Operations Runbook

### Pre-Release

1. Confirm `main` is reviewed and merged.
2. Check test reports and security scans.
3. Record the artifact digest and commit SHA.
4. Confirm CloudWatch alarms are in `OK` state.
5. Confirm a last-known-good revision exists.
6. Confirm database migrations are backward compatible.
7. Confirm on-call engineer and release approver availability.

### During Deployment

1. Watch CodePipeline stage and action progress.
2. Watch CodeDeploy lifecycle events.
3. Monitor CloudWatch alarms and target health.
4. Do not modify the deployment group mid-release unless planned.
5. If an alarm fires, allow CodeDeploy to execute automatic rollback and verify the outcome.
6. If smoke tests fail, verify CodePipeline stage rollback.
7. If rollback fails, halt promotion and escalate to the incident owner.

### Post-Release

1. Verify application version, deployment ID, and artifact digest.
2. Monitor 5xx errors, latency, healthy hosts, and business KPIs.
3. Check queues, backlogs, or async jobs if applicable.
4. Update the release record.
5. Close the change after the observation window completes.

## 39. Production Acceptance Checklist

### Pipeline

- [ ] Source connection uses GitHub App/CodeConnections.
- [ ] Branch protection and code reviews are enforced.
- [ ] Pipeline uses CodePipeline V2.
- [ ] Execution mode is not `PARALLEL` if stage rollback is required.
- [ ] Build/test gates run before deployment.
- [ ] Artifact is built once and promoted across accounts.
- [ ] Production has manual approval.

### Cross-Account Security

- [ ] Tooling service role assumes only the designated deploy roles.
- [ ] Target trust policies trust only the pipeline service role.
- [ ] Deploy roles hold least-privilege CodeDeploy and artifact permissions.
- [ ] Artifact bucket policy allows only required principals.
- [ ] KMS key policy and IAM policies permit the right roles.
- [ ] EC2 instance profiles can read artifacts and decrypt with the key.
- [ ] CodeDeploy service role is separated from action roles.
- [ ] No static AWS credentials are used.

### Deployment and Rollback

- [ ] CodeDeploy agent is running on EC2.
- [ ] `appspec.yml` and lifecycle scripts are tested.
- [ ] Deployment group attaches to the correct Auto Scaling group.
- [ ] CloudWatch alarms have baselines and thresholds.
- [ ] CodeDeploy auto rollback is enabled for failures and alarms.
- [ ] CodePipeline stage rollback is configured.
- [ ] A prior successful execution exists as a rollback target.
- [ ] Rollback tests have been executed in dev/staging.
- [ ] Database migrations are backward compatible with the prior version.
- [ ] Artifact retention exceeds the rollback window.

### Operations

- [ ] Dashboards and alerts cover pipeline, deployment, and application health.
- [ ] Owners and runbooks exist for release failures.
- [ ] Release records capture commit, artifact digest, and deployment ID.
- [ ] Log retention and audit trails are configured.
- [ ] Budget alerts and non-production cleanup are configured.

## 40. Self-Check Exercises

### Question 1

Why should CodePipeline reside in the tooling account?

**Answer:** To centralize release orchestration, artifact management, and auditing while target environment accounts grant only the specific permissions needed to deploy.

### Question 2

What mechanism does a cross-account deploy action use to access the target account?

**Answer:** CodePipeline assumes an IAM role in the target account via STS; the action specifies that role's ARN.

### Question 3

How do a trust policy and a permission policy differ?

**Answer:** The trust policy specifies which principals may assume the role; the permission policy specifies what actions the role may perform once assumed.

### Question 4

Why does cross-account CodePipeline require a customer-managed KMS key?

**Answer:** So roles in other accounts can decrypt artifacts via the key policy and IAM policies; default AWS managed keys do not support this cross-account sharing pattern.

### Question 5

Why does the EC2 instance profile also need S3/KMS access?

**Answer:** The CodeDeploy agent running on EC2 must download artifacts from S3 and decrypt them if encrypted with KMS.

### Question 6

Where should cross-account artifacts be stored?

**Answer:** In the pipeline account's artifact store; actions in target accounts read artifacts from there.

### Question 7

Can an artifact be passed directly from the dev account to the staging account in the same pipeline?

**Answer:** No, due to CodePipeline cross-account artifact rules; artifacts must originate in the pipeline account or from an earlier action within the consuming action's own account.

### Question 8

What responsibilities does CodeBuild perform in this capstone?

**Answer:** Runs tests, builds the package, generates the deployment bundle and checksum, and outputs the artifact for deploy stages.

### Question 9

Why should you not rebuild the application separately for production?

**Answer:** A production rebuild could produce a binary different from what passed staging tests; promoting the same artifact preserves consistency.

### Question 10

What conditions trigger CodeDeploy automatic rollback?

**Answer:** A deployment failure or a CloudWatch alarm configured on the deployment group entering `ALARM` state.

### Question 11

How does CodeDeploy rollback work?

**Answer:** It creates a new deployment to redeploy the most recent successful revision, generating a new deployment ID.

### Question 12

How does CodePipeline V2 stage rollback differ from CodeDeploy rollback?

**Answer:** CodeDeploy rollback restores the application revision inside a deployment group; CodePipeline rollback restores the stage to its most recent successful execution.

### Question 13

Why does stage rollback require a prior successful execution?

**Answer:** Because the pipeline needs a successful execution under the same pipeline structure version to act as the rollback target.

### Question 14

Does pipeline `PARALLEL` mode support stage rollback?

**Answer:** No. Use `SUPERSEDED` or `QUEUED` if stage rollback is required.

### Question 15

Why should deploy and smoke tests run inside the same stage?

**Answer:** So a smoke-test failure fails the deploy stage itself and triggers stage rollback on that deployment stage.

### Question 16

Which signals should CloudWatch alarms monitor?

**Answer:** Application 5xx/error rates, latency, healthy host/instance counts, and SLO-relevant business metrics.

### Question 17

If the very first deployment fails, does CodeDeploy have an older revision to roll back to?

**Answer:** No, unless a prior deployment succeeded; bootstrap a known-good revision first.

### Question 18

Does CodeDeploy rollback automatically revert database migrations?

**Answer:** No. Database migrations require backward compatibility, backups, and a dedicated recovery plan.

### Question 19

Why should `AdministratorAccess` never be granted to a cross-account deploy role?

**Answer:** Because the pipeline only needs a specific set of APIs and resources; overly broad permissions expand blast radius if the pipeline or source repository is compromised.

### Question 20

What evidence should be archived after every release?

**Answer:** Commit SHA, build ID, artifact checksum, pipeline execution ID, deployment ID, approver identity, alarm states, and test reports.

## 41. Official References

- [Create a pipeline in CodePipeline that uses resources from another AWS account](https://docs.aws.amazon.com/codepipeline/latest/userguide/pipelines-create-cross-account.html)
- [Configure a stage for automatic rollback](https://docs.aws.amazon.com/codepipeline/latest/userguide/stage-rollback-auto.html)
- [Configure conditions for a stage](https://docs.aws.amazon.com/codepipeline/latest/userguide/stage-conditions.html)
- [Set or change the pipeline execution mode](https://docs.aws.amazon.com/codepipeline/latest/userguide/execution-modes.html)
- [How pipeline executions work](https://docs.aws.amazon.com/codepipeline/latest/userguide/concepts-how-it-works.html)
- [GitHub connections for CodePipeline](https://docs.aws.amazon.com/codepipeline/latest/userguide/connections-github.html)
- [CodeBuild build and test action reference](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-CodeBuild.html)
- [CodeDeploy deployment groups and advanced options](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-groups-configure-advanced-options.html)
- [Monitoring deployments with CloudWatch alarms in CodeDeploy](https://docs.aws.amazon.com/codedeploy/latest/userguide/monitoring-create-alarms.html)
- [Redeploy and roll back a deployment with CodeDeploy](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployments-rollback-and-redeploy.html)
- [Deployments on an EC2/On-Premises compute platform](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-steps.html)
- [Application Specification files for CodeDeploy](https://docs.aws.amazon.com/codedeploy/latest/userguide/application-specification-files.html)
- [AWS Prescriptive Guidance: CI/CD best practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-cicd-litmus/cicd-best-practices.html)
- [AWS CodePipeline security](https://docs.aws.amazon.com/codepipeline/latest/userguide/security.html)
- [AWS KMS key policies](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [Using IAM roles to delegate permissions across AWS accounts](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_cross-account-with-roles.html)

Action names, quotas, Regional availability, and behaviors can change across AWS services. Before deploying, verify current documentation, the Service Authorization Reference, and quotas in each account. Test deployment failures, alarm rollbacks, and stage rollbacks in test accounts before enabling automation in production.
