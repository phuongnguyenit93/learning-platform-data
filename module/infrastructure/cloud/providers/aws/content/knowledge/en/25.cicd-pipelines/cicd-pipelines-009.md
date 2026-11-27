# Deploying IaC Through Pipelines and Reviewing Change Sets

## Learning Objectives

After this lesson, learners can:

- Explain why infrastructure must be managed as code and deployed through a controlled CI/CD process.
- Design an IaC pipeline covering source, validate/lint, security checks, packaging, preview, approval, execution, and post-deployment verification.
- Distinguish between CloudFormation templates, stacks, change sets, stack policies, drift detection, and rollback.
- Create CloudFormation change sets to preview resource additions, modifications, removals, and replacements before mutating an environment.
- Inspect change sets at the resource/property level, assess data risks, and determine when to reject or request changes.
- Configure CodePipeline CloudFormation actions using both `CHANGE_SET_REPLACE` and `CHANGE_SET_EXECUTE` modes, placing manual approval between the two steps.
- Distinguish between the pipeline service role, deployment/action role, and CloudFormation execution role; apply least privilege and `iam:PassRole`.
- Validate templates with `cfn-lint`, CloudFormation Validate, CloudFormation Guard, and other policy/security checks.
- Preserve reviewed artifacts unchanged from build to deploy, tying approvals to the exact commit and change set.
- Deploy across multiple environments/accounts/Regions using cross-account roles, StackSets, or AWS CDK Pipelines.
- Compare CloudFormation change sets with `cdk diff` and Terraform saved plans.
- Protect stateful resources, handle rollback, drift, secrets, IAM changes, nested stacks, and deployment failures.

**Module context:** This lesson belongs to the **CI/CD on AWS** chapter in CLOUD_PROVIDERS_AWS. The module helps learners select services and design AWS systems that are secure, observable, recoverable, and cost-controlled. An IaC pipeline bridges changes in Git with actual infrastructure in an AWS account/Region.

> **Scope:** Primary examples use AWS CloudFormation and AWS CodePipeline/CodeBuild. CDK and Terraform are covered for comparison. Stack names, role names, buckets, accounts, Regions, and commits in examples are illustrative; pin tool versions and consult reference docs for the versions you use.

## 1. The Problem: One Template Change Can Alter All of Production

A team wants to change a service's instance type, add a subnet, or update an S3 bucket policy. A developer edits the template, and the pipeline deploys straight to production. If a property change causes CloudFormation to replace an existing resource with a new one, the system may suffer an outage or data loss.

With IaC, a Git commit is a proposed change to infrastructure state. Before applying it, the team needs to know:

- Which resources will be created, updated, deleted, or replaced?
- Which properties change, and does replacement affect data?
- Does it add IAM permissions, public access, or network exposure?
- Are parameters, secrets, quotas, dependencies, and stack policies aligned?
- Who reviewed it, and who is authorized to approve production changes?
- Does the pipeline deploy the exact artifact that was reviewed?

~~~mermaid
flowchart LR
    Dev[Developer / Pull request] --> Git[Source repository]
    Git --> CI[Validate / Lint / Security]
    CI --> Package[Immutable IaC artifact]
    Package --> Plan[Create change set]
    Plan --> Review[Review resource diff]
    Review --> Gate[Approval]
    Gate --> Deploy[Execute change set]
    Deploy --> Verify[Verify / Monitor / Drift]
~~~

A well-designed pipeline produces clear evidence: which commit built which artifact, what changes that artifact proposes, who approved it, which change set executed, and what the outcome was.

## 2. How Does IaC Deployment Differ from Application Deployment?

Application deployment typically swaps a binary/container image and adjusts traffic. IaC deployment modifies foundational resources: VPCs, subnets, routes, security groups, IAM roles, S3 buckets, databases, queues, load balancers, or service configurations.

| Aspect | Application delivery | IaC delivery |
| --- | --- | --- |
| Artifact | JAR, container image, static bundle | Template, synthesized template, module/configuration, variables |
| Preview | Tests, packaging, deployment plan | CloudFormation change set, CDK diff, Terraform plan |
| Risk | Runtime errors, regressions, downtime | Resource replacement/deletion, data loss, privilege/network changes |
| Rollback | Redeploy previous version or shift traffic | Stack rollback/redeploy old config; may not restore lost data |
| Approval | Release/quality gate | Infrastructure, security, data owner, and change-management review |
| Audit | Build/release history | Commit, artifact digest, change set, CloudTrail, stack events |

A syntactically valid template is not guaranteed to deploy successfully. A successfully created change set also does not guarantee every resource operation will succeed at execution time. Therefore, the pipeline needs multiple layers of verification.

## 3. Reference IaC Pipeline Architecture

With CloudFormation, a common pipeline uses CodePipeline for orchestration and CodeBuild to run validation/packaging scripts.

~~~mermaid
flowchart TD
    Source[Git source / PR merge] --> Validate[Template validation]
    Validate --> Policy[Policy as code / Security scan]
    Policy --> Test[Unit / Integration / Contract tests]
    Test --> Package[Package templates and assets]
    Package --> Dev[Deploy dev change set]
    Dev --> Smoke[Smoke tests / drift check]
    Smoke --> Stage[Stage change set]
    Stage --> Review[Change set review]
    Review --> Approve[Manual approval]
    Approve --> Prod[Execute production change set]
    Prod --> Verify[Stack events / alarms / outputs]
    Verify --> Audit[Record evidence / notify]
~~~

Stages should have distinct responsibilities:

1. **Source:** fetch the exact revision from the repository.
2. **Validate:** parse, lint, and verify CloudFormation resource schemas.
3. **Policy/Security:** evaluate encryption, public exposure, IAM privileges, tags, and organizational policies.
4. **Test:** test modules, nested templates, helper scripts, and integration behavior.
5. **Package:** upload templates/assets and generate a manifest with commit SHA and checksum.
6. **Deploy non-production:** create a change set, review/deploy per policy, and run smoke tests.
7. **Production preview:** create a change set in the target account/Region.
8. **Approval:** authorized reviewers inspect the diff and risks.
9. **Execute:** execute the exact approved change set.
10. **Verify/Audit:** monitor stack events, alarms, outputs, CloudTrail, and drift.

Not every change needs the same approval path. A tag update may use a lighter gate; changes to IAM, network perimeter, KMS, databases, or production data require dedicated reviewers.

## 4. CloudFormation Templates, Stacks, and Change Sets

A **Template** is a declarative description of desired resources and configuration. A **Stack** is a managed instance created by CloudFormation from a template and parameters. A **Change set** is a preview of the changes CloudFormation intends to make when updating or creating a stack.

~~~mermaid
flowchart TD
    Template[CloudFormation template] --> Stack[Stack: orders-prod]
    Parameters[Parameters / mappings] --> Stack
    Current[Current stack state] --> Diff[CloudFormation comparison]
    NewTemplate[Proposed template + parameters] --> Diff
    Diff --> CS[Change set]
    CS -->|Review only| Reviewer[Reviewer]
    Reviewer -->|Approve| Execute[Execute change set]
    Execute --> Updated[Updated stack]
~~~

When creating a change set, CloudFormation compares the new template/parameters against the stack and describes the resource changes. Infrastructure is not modified merely by creating a change set. Changes begin only when the change set is executed.

For a new stack, a change set can place the stack in `REVIEW_IN_PROGRESS`; resources are created only after execution.

Documentation: [Update CloudFormation stacks using change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html).

## 5. Structuring IaC in a Repository

A repository may contain multiple stacks and modules. Clarify ownership and deployment boundaries so a pipeline does not accidentally modify out-of-scope environments.

Example:

~~~text
infrastructure/
  network/
    template.yaml
    parameters/
      dev.json
      prod.json
  application/
    template.yaml
    nested/
      database.yaml
      service.yaml
  security/
    iam-roles.yaml
  policies/
    guard/
      s3-encryption.guard
      iam-boundary.guard
  tests/
    fixtures/
  scripts/
    validate.ps1
    package.sh
  pipeline/
    buildspec.yml
~~~

Helpful organization rules:

- Every stack has a clear owner, purpose, environment, and deployment account.
- Separate shared foundations (network/security/logging) from application stacks when lifecycles differ.
- Use versioned nested stacks or modules when reuse is genuinely needed.
- Avoid copy-pasting the same resource definitions across accounts when parameterization or StackSets can be used.
- Templates, policy rules, parameters, and scripts must be under version control.
- Never place secret values, state files, or credentials in the repository.
- Use stable, traceable stack names without sensitive data.

## 6. Defining a Deployment Contract Before Building the Pipeline

Each stack should have a deployment contract—the set of inputs and constraints the pipeline must enforce.

| Component | Example |
| --- | --- |
| Stack name | `orders-network-prod` |
| Target account | Designated production AWS account |
| Region | `ap-southeast-1` |
| Template artifact | `network/packaged.yaml` |
| Parameter set | `parameters/prod.json` |
| CloudFormation execution role | `CfnOrdersDeployRole` |
| Capabilities | `CAPABILITY_NAMED_IAM` if the template creates named IAM resources |
| Change set name | `orders-prod-a1b2c3d` |
| Approval group | Platform + Security + Service owner |
| Verification | Stack status, outputs, alarms, smoke tests |

The pipeline should fail fast if account ID, Region, stack name, template digest, or environment mapping violates the deployment contract.

Use `AWS::AccountId`, `AWS::Region`, `AWS::Partition`, and constrained parameters to keep templates portable. Do not hardcode account/Region in ARNs when they can be constructed via pseudo parameters and `Fn::Sub`.

## 7. Validating Templates Before Touching AWS

Validation should run on pull requests and run again in the pipeline before packaging/deploying.

| Layer | Tool/check | Detects |
| --- | --- | --- |
| YAML/JSON parse | YAML/JSON parser | Syntax errors |
| CloudFormation schema | `cfn-lint`, `cfn-validate` | Invalid properties, missing required fields, type mismatches |
| Template checks | CloudFormation Validate | Intrinsic references, resource schemas, and tool best-practice findings |
| Policy as code | CloudFormation Guard | Organizational policy violations |
| Security scan | IAM Access Analyzer, appropriate scanners | Overly broad permissions, secret/public exposure |
| AWS pre-deployment validation | Change set creation validation | Errors depending on account/Region/quotas/resource state |

Example running validation in CodeBuild:

~~~bash
set -euo pipefail

cfn-lint infrastructure/**/*.yaml
cfn-validate infrastructure/ --strict

cfn-guard validate \
  --rules infrastructure/policies/guard/ \
  --data infrastructure/network/template.yaml
~~~

Pin versions of `cfn-lint`, `cfn-validate`, and Guard in the build image or tool installer. With multiple templates, run validation across all templates, including nested templates and templates synthesized from CDK/SAM.

Note: `cfn-guard` evaluates policies against YAML/JSON data; it does not replace template syntax/schema validation. `cfn-validate` checks templates locally, yet does not prove deployment will succeed in the target account/Region.

Documentation: [CloudFormation Validate](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html), [CloudFormation Guard](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-guard.html).

## 8. Policy as Code: Putting Guardrails in the Pipeline

Policy as code turns security rules into automated checks. Examples:

- S3 buckets must enable encryption and block public access.
- EBS/RDS storage must be encrypted.
- Security groups must not open SSH/RDP to the entire Internet without an approved exception.
- IAM policies must not use wildcard actions/resources outside an allowlist.
- Resources must carry `Environment`, `Owner`, and `CostCenter` tags.
- Production databases must enable appropriate backups/retention.
- CloudTrail/logging/network controls must not be disabled in foundational stacks.

Illustrative Guard rule:

~~~guard
let s3_buckets = Resources.*[ Type == "AWS::S3::Bucket" ]

rule s3_buckets_require_encryption when %s3_buckets !empty {
    %s3_buckets.Properties.BucketEncryption exists
}

rule s3_buckets_block_public_access when %s3_buckets !empty {
    %s3_buckets.Properties.PublicAccessBlockConfiguration exists
}
~~~

This is a simplified sample policy; production rules must account for inherited settings, exceptions, nested templates, and related resource types.

**Guard CLI is a pipeline check.** If enforcement is required on the CloudFormation side during stack operations, consider CloudFormation Hooks/Guard Hooks. Do not assume a CI scan alone stops out-of-band changes made outside the pipeline.

## 9. Packaging Templates and Keeping Artifacts Immutable

A pipeline must deploy the exact template that was validated and reviewed. If a template is repackaged after approval, its contents may differ from what the reviewer inspected.

Workflow:

1. Check out a specific commit.
2. Validate and test templates.
3. Upload nested templates, Lambda code, or assets to the artifact bucket.
4. Generate the packaged template and manifest.
5. Compute checksums/digests.
6. Attach commit SHA, build ID, target environment, and tool versions to metadata.
7. Pass that exact same artifact across stages.

Example manifest:

~~~json
{
  "repository": "platform-infrastructure",
  "commit": "a1b2c3d4e5f6",
  "buildId": "build-2026-11-20-001",
  "template": "network/packaged.yaml",
  "sha256": "REPLACE_WITH_REAL_SHA256",
  "target": {
    "environment": "prod",
    "region": "ap-southeast-1"
  }
}
~~~

Never put a dummy checksum like the example above into a real manifest; the pipeline must compute the checksum from the artifact bytes. Enable encryption and versioning on the artifact bucket, restrict read/write permissions, and apply appropriate KMS key policies. Never allow any stage to arbitrarily overwrite an already-reviewed artifact.

## 10. Parameters, Secrets, and Environment Configuration

Parameters should be separated from templates when they vary by environment, while still remaining controlled.

- Use version-controlled parameter files for non-secret settings.
- Use CloudFormation AWS-specific parameter types when appropriate.
- Use dynamic references to Secrets Manager/Parameter Store instead of embedding secrets.
- Use `NoEcho` to limit displaying sensitive parameters, without treating `NoEcho` as secret storage.
- Never write secret values into build logs, CodePipeline action configurations, or artifacts.
- Never place secrets in change set descriptions or approval comments.
- Check `UsePreviousValue` and parameter overrides to avoid inadvertently retaining stale values.

Example non-secret parameter file:

~~~json
[
  {
    "ParameterKey": "Environment",
    "ParameterValue": "prod"
  },
  {
    "ParameterKey": "InstanceType",
    "ParameterValue": "t3.small"
  }
]
~~~

If a database password is needed, use a Secrets Manager dynamic reference or an appropriate secret lifecycle; the CloudFormation/resource runtime IAM role must have permissions at the point of resolution.

## 11. Pipeline IAM Identities and the Least Privilege Principle

Pipelines typically require multiple permission scopes. Never combine everything into one role with `AdministratorAccess`.

| Identity | Role |
| --- | --- |
| CodePipeline service role | Allows CodePipeline to invoke source/build/deploy/approval actions and read/write artifacts |
| CodeBuild service role | Runs builds/tests, reads source/artifacts, and writes reports |
| Cross-account deployment role | Lets the pipeline in the tooling account assume deploy permissions in the target account |
| CloudFormation execution/service role | Assumed by CloudFormation to create/update resources |
| Runtime role | Used by the deployed workload to access AWS services |

Scope permissions by stack/resource boundary, required actions, and target account. Separate change set creation permissions from approval permissions where separation of duties is required.

Never let CodeBuild run scripts from untrusted pull requests using a production role. For PRs from forks or contributors without deploy privileges, grant validation-only permissions with no AWS write access.

## 12. Distinguishing CodePipeline Role, Cross-Account Action Role, and CloudFormation Execution Role

This is an easy area to mix up when configuring CodePipeline CloudFormation actions.

The **CodePipeline service role** lets the pipeline orchestrate stages/actions and transfer artifacts. When an action runs in another account, **ActionDeclaration.RoleArn** can specify the cross-account action role CodePipeline assumes to run the action in the target account. Inside the CloudFormation action configuration, **Configuration.RoleArn** is the CloudFormation service role that CloudFormation assumes to perform resource operations. These are two `RoleArn` fields at two different configuration layers. The deployed runtime workload has its own separate role.

~~~mermaid
flowchart TD
    Pipeline[CodePipeline service role] --> Action[CloudFormation deploy action]
    Action -->|Create change set / pass role| CFN[CloudFormation]
    CFN -->|Assume service role| Exec[CloudFormation execution role]
    Exec --> Resources[AWS resources]
    Reviewer[Approval identity] --> Gate[Manual approval]
    Gate --> Execute[Execute approved change set]
~~~

When not using a cross-account action role, the CodePipeline service role needs permission to call CloudFormation actions directly. When using `ActionDeclaration.RoleArn`, the pipeline service role needs permission to assume that action role; the action role needs the required CloudFormation permissions and `iam:PassRole` for the CloudFormation service role. The CloudFormation execution role holds the permissions to create/update resources.

Scope `iam:PassRole` to specific role ARNs and condition `iam:PassedToService` when appropriate. The execution role's trust policy must allow `cloudformation.amazonaws.com` to assume it. Cross-account setups additionally require trust relationships and role assumption in the target account.

With a cross-account CloudFormation action, `ActionDeclaration.RoleArn` is the role CodePipeline assumes to run the action in the target account. `Configuration.RoleArn` is the CloudFormation service role and must reside in the same account as the action role. The action role needs read access to the artifact bucket to generate an S3 signed URL for the template; the CloudFormation service role does not need artifact bucket read permissions because CloudFormation receives the signed URL.

Per the CloudFormation action reference, `Configuration.RoleArn` specifies the service role CloudFormation uses when manipulating resources. This field is required in `CHANGE_SET_REPLACE`; it is not re-applied in `CHANGE_SET_EXECUTE`. The change set/stack retains the service role attached when creating the change set. `ActionDeclaration.RoleArn`, if used, is the role CodePipeline assumes to execute the action and has distinct semantics. Review the action mode and account/role context of your pipeline carefully.

## 13. How Change Sets Work

Basic workflow:

1. The pipeline supplies the new template, parameters, and stack options.
2. CloudFormation compares the proposal against the current stack.
3. CloudFormation creates a change set.
4. Reviewers inspect resource changes and property-level details.
5. If needed, the team creates another change set or deletes the current one.
6. After approval, the pipeline executes the change set.
7. CloudFormation updates the stack and emits stack events.

A change set does not modify resources upon creation. Multiple change sets can be created to compare alternatives. Executing one change set invalidates and deletes other change sets on that stack.

**Important limitation:** a change set does not guarantee execution will succeed. Runtime conditions, service quotas, custom resources, permissions, dependency timing, or service-specific constraints can still cause deployment failures.

## 14. Change Set Types and Statuses to Understand

| Case | `ChangeSetType` | Meaning |
| --- | --- | --- |
| Create new stack | `CREATE` | Preview resources to be created |
| Update existing stack | `UPDATE` | Preview changes against the stack |
| Import resources into stack | `IMPORT` | Preview resource import operation |

CloudFormation returns two separate status fields:

| Field | Value | Meaning |
| --- | --- | --- |
| `ChangeSetStatus` | `CREATE_PENDING` | Change set creation queued |
| `ChangeSetStatus` | `CREATE_IN_PROGRESS` | CloudFormation is generating the change set |
| `ChangeSetStatus` | `CREATE_COMPLETE` | Change set ready for review |
| `ChangeSetStatus` | `FAILED` | Creation failed or no changes apply |
| `ExecutionStatus` | `AVAILABLE` | Change set can be executed |
| `ExecutionStatus` | `EXECUTE_IN_PROGRESS` | Currently executing |
| `ExecutionStatus` | `EXECUTE_COMPLETE` | Change set execution completed |
| `ExecutionStatus` | `OBSOLETE` | Change set no longer applies to the current stack |
| `ExecutionStatus` | `UNAVAILABLE` | Change set cannot be executed |

A change set can enter `FAILED` with reason "The submitted information didn't contain changes" when the template/parameters produce no diff. Pipelines should classify no-op results as no-deploy-needed only after verifying `StatusReason`; never treat every `FAILED` change set as a no-op.

## 15. Reading Resource Changes: Add, Modify, Remove, and Replacement

Change sets list the resources that will change:

| Action | Meaning | Review question |
| --- | --- | --- |
| `Add` | Create a new resource | Any public exposure, quota, cost, or IAM impact? |
| `Modify` | Update an existing resource | Which properties change? Any downtime or service disruption? |
| `Remove` | Delete resource from stack | Does the resource hold data or serve active workloads? |
| `Import` | Import an existing resource | Are resource identity and drift verified? |
| `Replacement` | Replace existing resource with a new one | Will the old resource be deleted? Are data migration/backups ready? |

Replacement is usually shown via `Replacement` with values `True`, `False`, or `Conditional`.

- `True`: CloudFormation expects to replace the resource.
- `False`: the resource updates in place or does not require replacement.
- `Conditional`: replacement depends on actual property values/runtime behavior.

Do not count only the number of `Add`/`Modify`/`Remove` entries. A `Modify` on an IAM policy or security group can be riskier than adding many new resources. Replacing an RDS instance, EFS filesystem, KMS key, or S3 bucket requires assessing data retention and migration.

## 16. A Change Set Is Not a Downtime or Data Migration Plan

A CloudFormation change set previews resource-level changes; it does not simulate all application-layer impacts.

Examples:
- Changing a DB instance identifier may create a new database and delete the old one depending on update behavior.
- Changing subnets/routes/security groups may sever active connections.
- Changing a KMS key may prevent workloads from decrypting older ciphertext if key lifecycles are mishandled.
- Changing an S3 bucket name is generally not an in-place update.
- Changing an IAM policy can cause `AccessDenied` during deployment or runtime.
- Custom resources may execute code with side effects not fully captured in the change set.

For stateful resources, reviews must combine the change set, CloudFormation resource update behavior docs, backup/restore plans, data migrations, and rollback runbooks.

Use `DeletionPolicy` and `UpdateReplacePolicy` appropriately to protect data-bearing resources. These policies do not replace backup/restore testing and do not guarantee zero downtime.

## 17. Creating Change Sets via AWS CLI

Example updating stack `orders-network-prod`. The pipeline has packaged the template and prepared a parameter file:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d \
  --change-set-type UPDATE \
  --template-body file://packaged.yaml \
  --parameters file://parameters-prod.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --role-arn arn:aws:iam::111122223333:role/CfnOrdersDeployRole \
  --description "commit=a1b2c3d environment=prod"
~~~

A change set name must be unique within the stack, start with a letter, and use only alphanumeric characters and hyphens; include a short commit SHA or pipeline execution ID so parallel runs do not collide. Maximum length is 128 characters.

In the CloudFormation API, `TemplateBody` has a 51,200-byte limit; for larger templates, upload to S3 and use `TemplateURL` / `--template-url`. CloudFormation `TemplateURL` supports templates up to 1 MB. With nested templates or assets, the package step should upload files to the artifact bucket and generate stable reference URLs.

Wait for the change set and read metadata:

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d
~~~

Inspect resource change details:

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d \
  --query "Changes[].ResourceChange"
~~~

Execute only after reviewer approval:

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d

aws cloudformation wait stack-update-complete \
  --stack-name orders-network-prod
~~~

In automation, handle `CREATE` vs. `UPDATE`, nonexistent stacks, no-op change sets, and failure reasons explicitly. Waiting for a change set does not replace inspecting `StatusReason` when `create-change-set` fails. Never auto-execute simply because `describe-change-set` returned output.

## 18. Change Set Review Checklist

Reviewers should read the change set alongside the template/commit/manifest, not just glance at a "deployment ready" notice.

| Review category | Questions |
| --- | --- |
| Identity/scope | Are account, Region, stack, environment, and owner correct? |
| Artifact | Does the template digest match the artifact built by the pipeline? |
| Resource actions | Are `Add`/`Modify`/`Remove`/`Import` actions justified? |
| Replacement | Which resources show `Replacement` as `True` or `Conditional`? |
| Data | Are RDS/S3/EFS/KMS/data-bearing resources affected? Where are backup/restore tests? |
| IAM | Are new actions/resources, trust principals, or permissions boundary changes added? |
| Network | Does it open new public ingress, routes, endpoints, or egress? |
| Encryption | Do KMS keys or bucket/database encryption settings change? |
| Availability | Are there replacement, restart, rolling update, quota, or downtime risks? |
| Cost | Do instance sizes, throughput, storage, or retention increase? |
| Nested stacks | Are nested stack change sets enabled and reviewed? |
| Drift | Does the current stack have unreconciled drift? |
| Rollback | Are stack policies, deletion policies, rollback alarms, and recovery plans suitable? |
| Evidence | Are approval comments, ticket/change IDs, and approver identities recorded? |

### Example Risk Classification

| Change | Default risk | Review action |
| --- | --- | --- |
| Add `CostCenter` tag | Low | Verify tag policy |
| Increase ECS desired count | Medium | Check capacity/cost/alarms |
| Open ingress `0.0.0.0/0` | High | Security review, justification, and expiration |
| Change IAM trust policy | High | Verify principals and assume paths |
| Replace RDS instance | Very high | Backups, migration, maintenance window, owner approval |
| Delete KMS key/resource | Very high | Check dependencies, retention, and recoverability |

No generic risk score replaces reviewing by resource type and business context.

## 19. CodePipeline: Creating a Change Set Before Approval

The CloudFormation deploy action can create or replace a change set using action mode `CHANGE_SET_REPLACE`. The pipeline pauses at a manual approval so reviewers can inspect the change set. Once approved, the next action uses `CHANGE_SET_EXECUTE`.

~~~mermaid
flowchart TD
    Build[Build artifact] --> Create[CloudFormation CHANGE_SET_REPLACE]
    Create --> Review[Reviewer opens change set]
    Review --> Decision{Approve?}
    Decision -->|Reject / timeout| Stop[Pipeline fails / stop]
    Decision -->|Approve| Execute[CloudFormation CHANGE_SET_EXECUTE]
    Execute --> Verify[Verify stack]
~~~

An AWS CodePipeline manual approval action pauses the pipeline until an identity authorized to approve/reject responds. If rejected or left unanswered for seven days, the action fails and the pipeline stops.

Documentation: [CodePipeline CloudFormation action](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-CloudFormation.html), [Manual approval actions](https://docs.aws.amazon.com/codepipeline/latest/userguide/approvals.html).

## 20. Example CloudFormation Action Configuration in CodePipeline

The snippet below illustrates configuring actions inside a stage. `BuildArtifact` contains the packaged template and parameter/config artifact:

~~~yaml
- Name: CreateChangeSet
  ActionTypeId:
    Category: Deploy
    Owner: AWS
    Provider: CloudFormation
    Version: "1"
  RunOrder: 1
  InputArtifacts:
    - Name: BuildArtifact
  Configuration:
    ActionMode: CHANGE_SET_REPLACE
    StackName: orders-network-prod
    ChangeSetName: orders-prod-a1b2c3d
    TemplatePath: BuildArtifact::packaged.yaml
    TemplateConfiguration: BuildArtifact::prod-config.json
    Capabilities: CAPABILITY_NAMED_IAM
    RoleArn: arn:aws:iam::111122223333:role/CfnOrdersDeployRole

- Name: ApproveInfrastructureChange
  ActionTypeId:
    Category: Approval
    Owner: AWS
    Provider: Manual
    Version: "1"
  RunOrder: 2
  Configuration:
    CustomData: "Review the exact CloudFormation change set for orders-network-prod."
    ExternalEntityLink: "https://console.aws.amazon.com/cloudformation/home"

- Name: ExecuteChangeSet
  ActionTypeId:
    Category: Deploy
    Owner: AWS
    Provider: CloudFormation
    Version: "1"
  RunOrder: 3
  InputArtifacts:
    - Name: BuildArtifact
  Configuration:
    ActionMode: CHANGE_SET_EXECUTE
    StackName: orders-network-prod
    ChangeSetName: orders-prod-a1b2c3d
    Capabilities: CAPABILITY_NAMED_IAM
~~~

This is an illustrative fragment, not a complete CodePipeline definition. A pipeline needs source/build stages, an artifact store, a service role, target account/Region configuration, and notification/approval permissions. `TemplatePath` must point to the exact file in the artifact; `TemplateConfiguration` is optional.

When using nested stacks, configure change set creation to include nested stack changes when reviewing the full hierarchy is needed. For templates with IAM resources, supply the right capability and review new IAM permissions before executing.

### Capabilities to Distinguish

- `CAPABILITY_IAM`: acknowledges templates containing IAM resources without custom names.
- `CAPABILITY_NAMED_IAM`: acknowledges templates containing IAM resources with custom names; also required whenever IAM resources use custom names.
- `CAPABILITY_AUTO_EXPAND`: acknowledges macro transforms when creating/updating a stack directly without reviewing a change set. When using a change set to review the macro-expanded result, this capability is not needed during change set creation; review the transformed resources.

## 21. Manual Approval Must Approve the Exact Revision and Change Set

A basic approval action can pause a pipeline, yet review quality depends on the information presented to the reviewer.

Approval context should include:

- Repository and commit SHA;
- Build ID and artifact checksum;
- Stack name, account ID, and Region;
- Change set name/ARN and creation time;
- Summary of resource actions and replacements;
- Link to the CloudFormation change set;
- Link to the pull request, ticket, and test results;
- Reviewer group and approval deadline;
- Risk summary and rollback plan.

**Never rebuild or generate a new change set after approval and then execute the new artifact.** If templates, parameters, or stack state change, generate a new change set and require re-review. Approval binds to the exact proposed change, not merely the pipeline name.

Separation of duties may require that the person proposing a change cannot approve it for production. Grant `codepipeline:PutApprovalResult` only to authorized approver groups.

## 22. Execute, Monitor, and Verify Post-Deploy

After approval, the pipeline executes the exact change set. CloudFormation starts the stack operation and emits stack events.

Verify:

1. The `CHANGE_SET_EXECUTE` action succeeds;
2. Stack status reaches `UPDATE_COMPLETE` or the matching success state;
3. No resources remain in `UPDATE_FAILED`, `DELETE_FAILED`, or rollback;
4. Outputs match expected values;
5. Application smoke tests pass;
6. CloudWatch alarms do not enter `ALARM`;
7. Health checks, connectivity, IAM access, and service metrics are normal;
8. CloudTrail/CodePipeline history preserves complete evidence.

CLI example:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-network-prod \
  --query "Stacks[0].[StackStatus,Outputs]"

aws cloudformation describe-stack-events \
  --stack-name orders-network-prod \
  --max-items 30
~~~

Do not treat an action status of started as deployment success. Track through to the terminal stack status and verify workload behavior.

## 23. Rollback and Protecting Critical Resources

CloudFormation can roll back a stack operation when a resource update fails, yet rollback is not backup/restore. Side effects outside CloudFormation or deleted data may not be recovered.

| Mechanism | Purpose |
| --- | --- |
| `DeletionPolicy` | Defines behavior when a resource is removed from a stack or the stack is deleted |
| `UpdateReplacePolicy` | Defines handling of the old physical resource during replacement |
| Stack policy | Prevents updates to protected resources |
| Termination protection | Blocks accidental stack deletion |
| Rollback triggers | Monitors CloudWatch alarms during stack operations and rolls back when triggered |
| Backup/restore | Restores data per RPO/RTO |
| Change approval | Blocks risky changes prior to execution |

Example protecting a database:

~~~yaml
Resources:
  OrdersDatabase:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Snapshot
    UpdateReplacePolicy: Snapshot
    Properties:
      DBInstanceClass: db.t4g.small
      Engine: postgres
      AllocatedStorage: 50
      StorageEncrypted: true
~~~

This example is a fragment; production templates must declare appropriate engine/version/credentials/network/backup options. A snapshot policy does not replace backup retention, restore drills, or a database migration strategy.

## 24. Stack Policies and Termination Protection

A stack policy is a JSON document specifying which resources CloudFormation is allowed to update inside a stack. Updates to RDS, KMS keys, or critical resources can be denied unless an approved break-glass procedure is followed.

Termination protection prevents deleting the stack; it does not block all resource updates. A stack policy is not an IAM policy: IAM controls who can invoke CloudFormation APIs, whereas a stack policy controls which resource updates CloudFormation itself may perform.

When a change set executes, CloudFormation enforces the active stack policy. If a change set must update a protected resource, adjust the stack policy via a controlled procedure before executing. Never disable policies simply to turn a pipeline green.

## 25. Drift Detection: Detecting Changes Outside the IaC Pipeline

**Drift** occurs when actual resource configuration diverges from the configuration managed by CloudFormation. For example, someone edits a security group rule directly in the console without updating the template.

CloudFormation drift detection compares actual resource properties against expected properties from the template/parameters for resource types supporting drift detection.

~~~mermaid
flowchart LR
    Template[Template state] --> Expected[Expected properties]
    Console[Manual console change] --> Actual[Actual resource state]
    Expected --> Compare[Drift detection]
    Actual --> Compare
    Compare --> Result{Drift?}
    Result -->|No| Clean[IN_SYNC]
    Result -->|Yes| Drift[MODIFIED / DELETED]
    Drift --> Reconcile[Reconcile template or resource]
~~~

Handling workflow:

1. Detect drift periodically and before major changes;
2. Identify who/what made the change using CloudTrail;
3. Evaluate whether the change is valid;
4. If valid, update the template/parameters so IaC reflects desired state;
5. If invalid, create a change set returning the resource to desired state;
6. Re-run drift detection and record the result.

Not every resource property is supported by drift detection; results must also be interpreted within resource provider limitations. Drift-aware change sets can help inspect/reconcile certain drifted resources, though careful review is still required.

Documentation: [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html).

## 26. Cross-Account and Multi-Region Deployments

A common model places repositories/artifacts/pipelines in a tooling account while dev/stage/prod run in separate workload accounts.

~~~mermaid
flowchart TD
    Tooling[Tooling account: CodePipeline] --> DevRole[Assume DevDeploymentRole]
    Tooling --> StageRole[Assume StageDeploymentRole]
    Tooling --> ProdRole[Assume ProdDeploymentRole]
    DevRole --> Dev[Dev account / Region]
    StageRole --> Stage[Stage account / Region]
    ProdRole --> Prod[Prod account / Region]
~~~

Principles:

- The pipeline identity may assume only allowlisted target roles.
- Target role trust policies trust only the exact tooling account/role with required conditions.
- Target roles can deploy only stacks/resources within their scope.
- CloudFormation execution roles are separated with scoped permissions.
- Artifact bucket/KMS key policies permit target actions to read required artifacts.
- Production approval sits before the execute action.
- Each environment has distinct parameters, stack names, and Region settings.
- Use STS short-lived credentials; never store long-lived access keys.

Cross-account deployments in CodePipeline require matching artifact store encryption/key policies and action roles. Do not simply add `RoleArn` and assume trust, `iam:PassRole`, artifact access, and KMS access work automatically.

## 27. StackSets for Shared Infrastructure Across Accounts

CloudFormation StackSets allow deploying one template to multiple AWS accounts and Regions in a single operation.

Well-suited for baseline IAM roles, CloudTrail/Config/security controls, VPC endpoints/shared networking, logging/monitoring agents, and organization-wide guardrails.

StackSets support self-managed permissions and service-managed permissions through AWS Organizations. The service-managed model can target the organization or OUs; a delegated administrator can manage StackSets when trusted access is enabled.

Set concurrency and failure tolerance carefully. For foundational infrastructure, deploy sequentially or to canary accounts first before expanding. Avoid high concurrency when a change could impact many workload accounts.

Documentation: [CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/what-is-cfnstacksets.html).

## 28. AWS CDK: Synth and Diff Before Deploy

AWS CDK lets you define infrastructure in a programming language. Pipelines run `cdk synth` to emit CloudFormation templates; `cdk diff` compares the proposed template with the deployed stack; final deployment still uses CloudFormation.

~~~bash
npm ci
npm test
npx cdk synth --all
npx cdk diff OrdersNetworkProd
~~~

Key considerations:

- Review synthesized templates, not only TypeScript/Python code.
- Check asset manifests, Docker/Lambda assets, and bootstrap bucket references.
- `cdk diff` reports changes, yet does not replace CloudFormation change sets in every workflow.
- CDK Pipelines can automate synth/deploy stages and support manual approval steps.
- CDK bootstrap roles/buckets require proper trust policies and permissions, especially cross-account.
- Pin CDK CLI/library versions for stable synthesis output.

For production, you can combine `cdk synth` → artifact → CloudFormation change set → approval → execute depending on pipeline design.

## 29. Terraform: Plan/Apply Is the Corresponding Preview

When IaC uses Terraform, the workflow is similar, except the preview artifact is a saved plan rather than a CloudFormation change set.

~~~bash
terraform init -input=false
terraform fmt -check -recursive
terraform validate

terraform plan \
  -input=false \
  -out=tfplan

terraform show -no-color tfplan
~~~

After approval, apply the exact saved plan:

~~~bash
terraform apply -input=false tfplan
~~~

Key points:

- `terraform plan` does not modify infrastructure.
- `terraform plan -out=tfplan` saves a specific execution plan for automation to apply after review.
- `terraform apply tfplan` executes the saved plan without prompting for new approval.
- Plan files can contain sensitive values in cleartext even if terminal output masks them; protect them as secret artifacts.
- Plans can become stale if state or remote infrastructure changes; generate and review a new plan whenever state shifts.
- Remote backends, state locking, workspace/environment mappings, and provider/module versions must be controlled.

Never reuse an old approval to apply a new plan. Review the plan artifact, commit SHA, state context, and target workspace/account/Region together.

Documentation: [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan), [Terraform apply](https://developer.hashicorp.com/terraform/cli/commands/apply).

## 30. Security Controls for IaC Pipelines

An IaC pipeline has permissions to create IAM, network, and data resources, so source, build, artifacts, and deployment identities all need controls.

| Control | Practice |
| --- | --- |
| Source protection | Branch protection, signed commits/tags where appropriate, CODEOWNERS |
| Pull request | Required reviews, status checks, no direct production pushes |
| Build isolation | Ephemeral workers, restricted networking, pinned toolchains |
| Dependencies | Pin modules/providers/actions/images; scan supply chain |
| Secrets | Secrets Manager/SSM, OIDC federation, never log credentials |
| Artifacts | Encryption, versioning, checksums, restricted access |
| IAM | Least privilege, short-lived credentials, `iam:PassRole` allowlists |
| Approval | Separation of duties, reviewer groups, immutable change references |
| Policy | Guard/CloudFormation Hooks, security scanning, organizational controls |
| Audit | CloudTrail, CodePipeline history, stack events, approval comments |

Be especially careful with untrusted pull requests: never run untrusted build scripts with a production role or allow scripts to assume deploy roles.

## 31. Testing IaC: Unit, Integration, and Deployment Verification

A pipeline that merely runs lint and deploys is insufficient. Test in layers:

- **Unit tests:** verify constructs/functions emit expected resource properties.
- **Template tests:** schemas, references, policy rules, naming, tags, encryption.
- **Diff review:** resource actions and replacements.
- **Integration tests:** deploy into ephemeral/test accounts or sandbox stacks.
- **Smoke tests:** verify endpoints, connectivity, permissions, alarms, and outputs.
- **Drift checks:** compare actual state against templates after deploy or on a schedule.
- **Recovery tests:** test rollbacks, snapshot restores, and resource recreation in non-production.

With CDK, use assertions/template tests to verify synthesized CloudFormation. With Terraform, use module tests/plan assertions and sandbox testing. With CloudFormation, use `cfn-lint`, `cfn-validate`, Guard, and test stacks.

Never treat local template validation as a substitute for AWS integration testing. Some errors surface only when CloudFormation invokes service providers in a real account/Region.

## 32. Observability and Auditing for Deployments

Every deployment should preserve enough evidence to answer: who deployed, what was deployed, where, from which revision, who approved it, and what the result was.

Collect:

- CodePipeline execution IDs and stage/action results;
- CodeBuild build IDs, logs, and reports;
- Git commit SHA, PR link, and artifact digest;
- CloudFormation stack ID, change set ARN/name, and status reason;
- CloudFormation stack events;
- CloudTrail events for API calls and role assumptions;
- Approval identity/comment/timestamp;
- CloudWatch alarms and post-deploy smoke test results.

Send SNS/EventBridge notifications when pipelines fail, stacks roll back, or drift is detected. Never include template secrets or sensitive parameter values in notification payloads.

## 33. Common Incident-Causing Anti-Patterns

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Deploying directly from a mutable branch | Unclear which code/template was actually deployed | Pin commit SHA and immutable artifacts |
| Skipping change sets | Resource replacement/deletion unseen before deploy | Create change sets and review |
| Rebuilding artifact after approval | Executed contents differ from reviewed contents | Promote the exact same artifact/digest |
| Single admin role for pipeline | Large blast radius, hard to audit | Separate pipeline/execution/target roles |
| Storing secrets in parameters/artifacts | Secrets exposed via logs/artifacts | Dynamic references/secret stores |
| Treating a change set as a guarantee of success | Runtime updates can still fail | Tests, alarms, monitoring, rollback plans |
| Ignoring `Replacement` | Risk replacing databases or stateful resources | Review property-level changes and update behavior |
| Ignoring drift | Change sets rely on wrong assumptions about current state | Detect/reconcile drift |
| Using `CAPABILITY_NAMED_IAM` without IAM review | Unexpected permissions may be granted | Review policy/trust changes |
| Running PR scripts with prod credentials | Supply-chain/privilege escalation | Isolate untrusted PR builds |
| Applying a Terraform plan different from the approved one | Unreviewed changes applied | Apply exact saved plan artifact |
| Scaling concurrency too quickly | Outages spread across many accounts/Regions | Canary, failure tolerance, and staged rollouts |

## 34. Troubleshooting: Pipeline or CloudFormation Deployment Failures

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Template validation failed | Invalid YAML/schema/property | Run `cfn-lint`, `cfn-validate`, check line/column |
| Guard rule failed | Template violates security/compliance policy | Fix template or grant exception with owner/expiry |
| `InsufficientCapabilitiesException` | Missing IAM capability acknowledgment | Review IAM resources and declare matching capability |
| `AccessDenied` creating change set | Pipeline role lacks CloudFormation permissions | Check service role and action permissions |
| `iam:PassRole` denied | Pipeline cannot pass CloudFormation execution role | Scope `PassRole` to the exact role and service |
| Change set `FAILED` | Invalid template, role/quota/resource issue, or no changes | Read `StatusReason`, distinguish no-op from real error |
| Change set created but execute fails | Runtime condition, custom resource, permission, or quota | Inspect stack events and CloudTrail; create new change set after fixing |
| Artifact/template not found | Wrong artifact name/path or S3 access | Check `TemplatePath`, artifact store, and KMS |
| Nested stack update fails | Child template/role/parameter mismatch | Inspect nested stack events and change sets |
| Unexpected replacement | Property update forces replacement | Check resource update behavior, backups, and migrations |
| Stack rollback | Resource operation or alarm failed | Inspect first failure in stack events and rollback triggers |
| Stack policy blocks update | Resource is protected | Follow controlled policy change procedure |
| Drift detected | Out-of-band change outside CloudFormation | Identify actor and reconcile template |
| Manual approval timeout | No approver responded within 7 days | Check notifications/permissions and start new run after review |
| Cross-account `AccessDenied` | Wrong trust policy, target role, KMS/artifact policy | Check STS assume, `PassRole`, and resource policies |
| Pipeline runs in wrong Region/account | Wrong environment mapping/variables | Assert caller identity, account ID, and Region before deploy |

### Ordered Investigation Workflow

~~~text
1. Confirm source commit, artifact digest, account, Region, and stack name.
2. Inspect failing CodePipeline action and CodeBuild logs.
3. Check template validation, policy reports, and package paths.
4. If change set fails, read DescribeChangeSet.StatusReason.
5. If execute fails, locate the first stack event with status *_FAILED.
6. Check CloudTrail to identify denied principals/APIs.
7. Verify CloudFormation execution role, trust policy, and iam:PassRole.
8. Check resource quotas, service-specific constraints, and dependencies.
9. Check stack policies, deletion/update replacement policies, and rollback alarms.
10. Fix source, create a new artifact/change set, and re-review before executing.
~~~

Never edit resources directly in the console to make a pipeline pass without recording the change in IaC; if an emergency change is necessary, reconcile drift after the incident.

## 35. Lab: Building a CloudFormation Pipeline with an Approval Gate

### Scenario

You have a template creating an S3 bucket for an application. The pipeline deploys to dev automatically; production must create a change set, pause for review, and then execute.

### Step 1 — Create the Template

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Orders artifact bucket

Parameters:
  Environment:
    Type: String
    AllowedValues:
      - dev
      - prod

Resources:
  OrdersArtifactBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      VersioningConfiguration:
        Status: Enabled
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Application
          Value: orders

Outputs:
  BucketName:
    Value: !Ref OrdersArtifactBucket
~~~

Actual bucket names must be globally unique; you can add an account/Region suffix via appropriate parameters. `DeletionPolicy: Retain` preserves the bucket if the resource is deleted from the stack, yet does not protect objects from lifecycle rules or user deletion.

### Step 2 — Validate and Package

~~~bash
cfn-lint template.yaml
cfn-validate template.yaml --strict

aws cloudformation package \
  --template-file template.yaml \
  --s3-bucket platform-cfn-artifacts \
  --output-template-file packaged.yaml
~~~

If the template has no local assets, the package step may not upload extra files, yet the pipeline should still keep the packaged template as the verified artifact.

### Step 3 — Create the Production Change Set

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-artifacts-prod \
  --change-set-name orders-artifacts-prod-a1b2c3d \
  --change-set-type CREATE \
  --template-body file://packaged.yaml \
  --parameters ParameterKey=Environment,ParameterValue=prod \
  --description "commit=a1b2c3d environment=prod"
~~~

If the stack already exists, use `UPDATE`. The pipeline must check stack existence or handle `CREATE`/`UPDATE` explicitly.

### Step 4 — Review

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-artifacts-prod \
  --change-set-name orders-artifacts-prod-a1b2c3d
~~~

Verify the exact account/Region/stack, bucket encryption, public access block, versioning, retention, tags, and IAM capabilities if present. The reviewer records the verified commit/change set.

### Step 5 — Execute After Approval

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-artifacts-prod \
  --change-set-name orders-artifacts-prod-a1b2c3d

aws cloudformation wait stack-create-complete \
  --stack-name orders-artifacts-prod
~~~

### Step 6 — Verify

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-artifacts-prod

aws cloudformation detect-stack-drift \
  --stack-name orders-artifacts-prod
~~~

Check stack status, output bucket name, encryption/versioning/public access block, and drift status. Practice making a manual change in the console in sandbox and running drift detection to observe the discrepancy.

## 36. Exercises and Self-Check Questions

### Exercise 1 — Database Replacement

A change set shows `Modify` on an RDS resource with `Replacement: True`.

**Task:** Explain what this means, identify data-loss/downtime risks, backup/restore plans, maintenance windows, and approval owners.

### Exercise 2 — CodePipeline Actions

A pipeline has a CloudFormation `CHANGE_SET_REPLACE` action, manual approval, and `CHANGE_SET_EXECUTE`.

**Task:** Describe action ordering, permissions needed by the pipeline role, CloudFormation execution role, and reviewer; explain why artifacts must not be rebuilt after approval.

### Exercise 3 — IAM Capabilities

A template adds an IAM role and policy. Change set creation fails due to missing capabilities.

**Task:** Distinguish `CAPABILITY_IAM`, `CAPABILITY_NAMED_IAM`, and `CAPABILITY_AUTO_EXPAND`; review trust policies and permission policies before acknowledging.

### Exercise 4 — Cross-Account Deployment

A tooling account deploys a network stack into a production account but receives `iam:PassRole` `AccessDenied`.

**Task:** Draw the trust chain, distinguish the CodePipeline role, target deployment role, and CloudFormation execution role; scope `iam:PassRole` and trust conditions.

### Exercise 5 — Drift

An engineer edits a security group rule directly in the console. The next change set does not reflect what they expected.

**Task:** Run drift detection, identify actual vs. expected state, locate the CloudTrail actor, and reconcile the template before deploying.

### Exercise 6 — Terraform Pipeline

A team uses Terraform and wants an approval gate equivalent to a CloudFormation change set.

**Task:** Generate a saved plan with `terraform plan -out=tfplan`, review `terraform show`, store the plan as a sensitive artifact, and apply the exact approved file.

### Exercise 7 — Policy as Code

Security requires every S3 bucket to enable encryption, block public access, and carry an `Environment` tag.

**Task:** Write Guard rules, run them in CodeBuild, and explain the difference between Guard CLI and Guard Hooks.

### Exercise 8 — Multi-Account Baseline

An organization has 30 AWS accounts and needs to deploy a CloudTrail/Config baseline.

**Task:** Compare a pipeline assuming a role per account against CloudFormation StackSets with service-managed permissions; choose rollout concurrency/failure tolerance and a delegated administrator model.

### Short Questions

1. **What is a Template?** A declarative description of desired resources and configuration.
2. **What is a Stack?** A CloudFormation-managed instance created from a template and parameters.
3. **Does a change set modify resources immediately on creation?** No; executing it starts the stack update/create.
4. **Does a change set guarantee deployment success?** No; runtime/service-specific failures can still happen.
5. **What does `CHANGE_SET_REPLACE` do?** Creates or replaces a change set.
6. **What does `CHANGE_SET_EXECUTE` do?** Executes an already-created change set.
7. **What does `Replacement: True` mean?** The resource is expected to be replaced with a new resource.
8. **Is "no changes" always a deployment failure?** No; it can be a no-op that the pipeline should classify cleanly.
9. **When does a CodePipeline manual approval time out?** After seven days.
10. **When is `CAPABILITY_NAMED_IAM` used?** When the template creates IAM resources with custom names.
11. **What does `iam:PassRole` permit?** Allows passing an IAM role to a designated service; must be tightly scoped.
12. **What does the CloudFormation execution role do?** Supplies permissions for CloudFormation to create/update resources.
13. **Is a stack policy an IAM policy?** No; it protects resource updates within a stack.
14. **What does termination protection prevent?** Prevents deleting the stack.
15. **Does `DeletionPolicy` replace backups?** No.
16. **What is drift?** Actual resource properties diverging from expected template state.
17. **Does Guard CLI replace syntax validation?** No; use `cfn-lint`/`cfn-validate` alongside Guard.
18. **Can a Terraform saved plan contain secrets?** Yes; it must be protected as a sensitive artifact.
19. **Should artifacts be rebuilt after approval?** No; execute the exact reviewed artifact/change set.
20. **What are StackSets used for?** Deploying and managing stacks across multiple accounts/Regions.

## 37. Pre-Production Checklist

- [ ] Source revision/commit SHA is pinned and has pull request review.
- [ ] Templates, nested templates, scripts, and policy rules are under version control.
- [ ] `cfn-lint`/`cfn-validate` and Guard/security checks pass.
- [ ] Tool versions, providers/modules, and build images are pinned.
- [ ] Artifacts are packaged, checksummed, and immutable across stages.
- [ ] Parameters/environment mappings match the right account, Region, and stack.
- [ ] Secrets do not appear in source code, logs, parameter files, or artifacts.
- [ ] Pipeline role, target role, and CloudFormation execution role are separated with least privilege.
- [ ] `iam:PassRole` is scoped to the exact CloudFormation service role.
- [ ] Cross-account trust, artifact bucket, and KMS key policies are verified.
- [ ] Change set is created against the exact target stack/account/Region.
- [ ] Resource actions and property-level changes have been reviewed.
- [ ] `Replacement: True`/`Conditional`, deletions, and IAM/network/KMS changes have owner approval.
- [ ] Stateful resources have backup/restore and migration plans.
- [ ] Nested stack changes are included and reviewed when required.
- [ ] Stack policies, termination protection, `DeletionPolicy`, and `UpdateReplacePolicy` are appropriate.
- [ ] Approvals are bound to a specific commit, artifact digest, and change set.
- [ ] Approvers hold separate authority; separation of duties meets policy.
- [ ] Execute action runs the exact approved change set.
- [ ] Stack events, CloudTrail, alarms, outputs, and smoke tests are verified.
- [ ] Drift detection runs on a schedule and after emergency changes.
- [ ] Rollback, break-glass, and incident runbooks are ready.
- [ ] Multi-account/Region rollouts use canary, concurrency, and failure tolerance settings.
- [ ] Terraform plan/CDK synth artifacts are handled according to each tool's semantics.

## 38. Summary

Deploying IaC via pipelines turns infrastructure changes into a repeatable, reviewable, and auditable process. A pipeline must validate templates, run policy/security checks, package immutable artifacts, generate a preview, obtain approval, execute, and verify the stack post-deploy.

With CloudFormation, **change sets are the critical control point before mutating production**. Reviewers must understand resource actions, property-level changes, replacement behavior, IAM/network impacts, data retention, and rollback. A change set is only a preview; deployments can still fail due to runtime conditions, permissions, quotas, or custom resources.

CodePipeline can create change sets with `CHANGE_SET_REPLACE`, pause at manual approval, and execute them with `CHANGE_SET_EXECUTE`. Separate the CodePipeline service role, cross-account deployment role, and CloudFormation execution role; scope `iam:PassRole`; and preserve approved artifacts unchanged. For multiple accounts/Regions, evaluate cross-account roles or StackSets. For CDK/Terraform, review synthesized templates/diffs or saved plans and deploy the exact approved artifacts.

Key points to remember:

1. IaC modifies real resources; reviews must focus on replacement, deletion, data, and permissions.
2. Change sets do not alter stacks until executed and do not guarantee runtime deployment success.
3. `CHANGE_SET_REPLACE` generates the preview; approval gates it; `CHANGE_SET_EXECUTE` executes that exact preview.
4. Pipeline roles and CloudFormation execution roles have distinct responsibilities; `iam:PassRole` must be tightly scoped.
5. Artifacts/plans must remain immutable, and approvals must bind to the exact commit/digest/change set.
6. Policy as code, drift detection, stack policies, backups, and rollback alarms provide complementary guardrails.
7. Terraform saved plans and CDK synth/diff have distinct semantics; do not treat them as the same artifact type as CloudFormation change sets.

### Official Documentation

- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)
- [Update CloudFormation stacks using change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- [Create a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-create.html)
- [Execute a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-execute.html)
- [CloudFormation change set resource reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudformation-changeset.html)
- [CodePipeline CloudFormation action reference](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-CloudFormation.html)
- [CodePipeline manual approvals](https://docs.aws.amazon.com/codepipeline/latest/userguide/approvals.html)
- [CodePipeline CloudFormation pipeline walkthrough](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/continuous-delivery-codepipeline-basic-walkthrough.html)
- [CloudFormation Validate](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html)
- [CloudFormation Guard](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-guard.html)
- [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html)
- [CloudFormation rollback triggers](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-rollback-triggers.html)
- [CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/what-is-cfnstacksets.html)
- [AWS CDK Pipelines](https://docs.aws.amazon.com/cdk/v2/guide/cdk-pipeline.html)
- [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan)
- [Terraform apply](https://developer.hashicorp.com/terraform/cli/commands/apply)

**Operational note:** Change set formats, validation tools, CodePipeline action properties, and resource update behaviors may evolve. Before production, verify documentation for the exact service/resource types in use, test in a sandbox account, and preserve change set/approval/stack event evidence in deployment records.
