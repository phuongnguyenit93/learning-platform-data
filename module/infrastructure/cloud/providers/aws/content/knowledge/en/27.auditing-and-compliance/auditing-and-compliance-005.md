# Config rules, conformance packs, and automated remediation

## Learning objectives

After this lesson, you can explain how AWS Config records and evaluates resource configurations; distinguish between managed/custom rules and detective/proactive evaluation; design conformance packs for an account, Region, or AWS Organization; configure Systems Manager Automation to remediate NON_COMPLIANT resources; and operate remediation with least-privilege IAM, retries, concurrency limits, and monitoring mechanisms.

## 1. The problem and the role of each component

An organization may require S3 buckets to block public access, EBS volumes to be encrypted, security groups not to open SSH to the entire Internet, and IAM password policies to meet a minimum length. If checked only manually once a quarter, misconfigurations can persist for weeks before being discovered.

AWS Config records the configuration state of AWS resources and evaluates that state against rules. When a rule detects a violation, operations teams can investigate, open a ticket, remediate manually, or invoke an automated workflow using Systems Manager Automation.

In the AWS ecosystem, Config works with IAM to restrict permissions, S3 to store history, Lambda for custom evaluation, Systems Manager for remediation, and Organizations to apply multi-account baselines. CloudTrail adds API audit trails, while CloudWatch supports observing workflows. These components help platform teams deploy safety controls, track state, and reduce remediation time.

| Component | Role |
|---|---|
| AWS Config rule | Describes the condition for a resource to be considered compliant |
| Conformance pack | Packages multiple rules and remediations into a single deployment unit |
| Remediation action | Executes configuration fix steps for non-compliant resources |
| Systems Manager Automation | Runs a runbook to perform the remediation action |

For example, the rule **s3-bucket-public-read-prohibited** detects buckets allowing public read. A conformance pack can combine this rule with rules for encryption, versioning, and logging. A remediation action can invoke an SSM Automation runbook to enable S3 Block Public Access once the organization confirms the action is appropriate for those buckets.

AWS Config is the state evaluation layer. Systems Manager Automation is the change execution layer. Separating these two responsibilities allows the organization to alter how issues are handled while keeping the detection logic unchanged.

## 2. Overall workflow

1. The configuration recorder records configurations of selected resource types in a Region.
2. AWS Config creates a configuration item when a resource is created, modified, or deleted.
3. The AWS Config rule is triggered per its configured trigger and evaluates the configuration item.
4. The rule returns COMPLIANT, NON_COMPLIANT, ERROR, or NOT_APPLICABLE.
5. If remediation is configured, AWS Config passes parameters to Systems Manager Automation.
6. Automation assumes the specified IAM role and runs the steps in the SSM document.
7. AWS Config records the new configuration and re-evaluates the resource.
8. Operations teams monitor history, errors, exceptions, and compliance trends.

~~~mermaid
flowchart TD
    A["AWS resources"] --> B["AWS Config recorder"]
    B --> C["Configuration items"]
    C --> D["AWS Config rules"]
    D --> E{"Evaluation result"}
    E -->|COMPLIANT| F["Keep monitoring"]
    E -->|NON_COMPLIANT| G["Compliance finding"]
    G --> H{"Remediation mode"}
    H -->|Manual| I["Operator starts runbook"]
    H -->|Automatic| J["AWS Config starts Automation"]
    I --> K["SSM Automation document"]
    J --> K
    K --> L["Automation assume role"]
    L --> M["Change AWS resource"]
    M --> N["New configuration item"]
    N --> D
~~~

A rule only detects and reports status. Remediation is the part that actually performs changes. A NON_COMPLIANT result does not mean the resource has been fixed.

## 3. Configuration recorder and recording scope

AWS Config can only evaluate configurations that the service can observe and record. The configuration recorder defines which resource types are recorded in an account and Region. A configuration item stores the configuration state of a resource at a point in time, including attributes, metadata, and related relationships.

If the recorder does not record the **AWS::EC2::Volume** resource type, an EBS encryption rule lacks the data needed to evaluate volumes in that Region. Successfully creating a rule does not prove the recorder is configured properly.

Before deploying rules or packs, verify:

- AWS Config is enabled in each Region requiring governance.
- The recorder is running and includes the resource types the rules need to inspect.
- The AWS Config IAM role has permissions to read the required configurations.
- The delivery channel and S3 bucket storing history/snapshots are configured.
- The organization understands the cost of recording and evaluating resources.

You can record all supported resource types or only a subset of resource types. Recording all reduces the risk of missing a rule's target, though it can increase cost. Selective recording helps control cost, though it requires managing a matrix between rules and resource types.

To report compliance status accurately, record the **AWS::Config::ResourceCompliance** resource type. To store conformance pack compliance state change history on the timeline, you can also record **AWS::Config::ConformancePackCompliance**; AWS Config provides recording of this resource type at no additional charge.

AWS Config operates per Region. A recorder in **ap-southeast-1** does not automatically record resources in **ap-southeast-2**. In multi-Region environments, enable the recorder and deploy rules or packs in every Region requiring control.

## 4. AWS Config rules

A rule typically consists of source, scope, trigger, input parameters, and evaluation mode. Some rules are also linked to a remediation action.

| Component | Meaning | Design question |
|---|---|---|
| Source | Managed rule or custom logic | Use a built-in rule or define your own? |
| Scope | Resource types, IDs, or tags evaluated | Which resources are in scope? |
| Trigger | Event that causes the rule to run | Run on change or periodically? |
| Input parameters | Thresholds or expected values | Which values represent the organization's standard? |
| Evaluation mode | Detective or proactive | Evaluate existing resources or planned configurations? |
| Remediation | Linked SSM Automation document | Is there a manual or automatic fix action? |

For example, an EBS encryption rule can apply to all recorded EBS volumes in a Region. A tagging rule can restrict scope to resources with the tag **Environment=Production**. Limiting scope reduces unnecessary evaluations and avoids applying policies out of bounds.

### 4.1 Managed rules

Managed rules are predefined rules provided by AWS. You select a rule and configure appropriate parameters and scope.

| Rule | Purpose |
|---|---|
| **s3-bucket-public-read-prohibited** | Detects S3 buckets allowing public read |
| **s3-bucket-public-write-prohibited** | Detects S3 buckets allowing public write |
| **s3-bucket-server-side-encryption-enabled** | Checks S3 bucket default encryption |
| **encrypted-volumes** | Checks whether EBS volumes are encrypted |
| **restricted-ssh** | Detects security groups allowing SSH from undesired scopes |
| **iam-password-policy** | Checks IAM password policy attributes |
| **access-keys-rotated** | Checks IAM access key age against a threshold |

Managed rules fit when check conditions closely match organizational requirements. For example, **access-keys-rotated** accepts a maximum age parameter. If the organization requires access keys to be no older than 60 days, you set that parameter instead of rewriting evaluation logic.

Read the rule's documentation before deploying: resource types, required parameters, triggers, Region availability, and limitations.

### 4.2 Custom rules

When managed rules do not fully express a policy, custom rules can be created in two ways:

- **Custom Policy rules with CloudFormation Guard:** express conditions as policy-as-code, suited for structural checks of configuration attributes.
- **Custom Lambda rules:** use Lambda for complex processing logic or integrating external data. Lambda returns evaluation results to AWS Config via the corresponding API.

Example Guard rule checking Point-in-Time Recovery for a DynamoDB table:

~~~guard
let status = ['ACTIVE']

rule table_is_active when
    resourceType == "AWS::DynamoDB::Table" {
    configuration.tableStatus == %status
}

rule check_pitr when
    resourceType == "AWS::DynamoDB::Table"
    table_is_active {
    let pitr = supplementaryConfiguration.ContinuousBackupsDescription.pointInTimeRecoveryDescription.pointInTimeRecoveryStatus
    %pitr == "ENABLED" <<DynamoDB tables must have Point-in-Time Recovery enabled>>
}
~~~

Guard rules must use the exact configuration and supplementaryConfiguration structures provided by AWS Config for the resource type. Inspect the schema and examples for that resource type before deploying a policy.

For custom Lambda rules, Lambda must process the evaluation event, determine the resources to check, return valid evaluation results, and use the result token provided by AWS Config. The Lambda execution role needs least-privilege permissions. If the rule calls other services, account for timeouts, retries, concurrency, and dependency failures.

Prefer managed rules when the condition is built-in and configurable via parameters. Choose Guard when policies are straightforward and need source-code review. Choose Lambda when custom logic or external data integration is needed. Custom rules increase maintenance responsibility for code, runtime, IAM, logging, and testing.

## 5. Triggers and evaluation modes

### Trigger

AWS Config supports the main trigger types:

| Trigger | How it works | When to use |
|---|---|---|
| Configuration changes | Evaluates when a resource matching scope changes | Detect misconfigurations after creation or update |
| Periodic | Evaluates on a configured interval | Re-check conditions on a schedule |
| Hybrid | Combines configuration changes and periodic | Need fast response plus periodic re-checks |

Configuration change triggers can be scoped by resource type, resource ID, tag key/value, or all recorded resources. Periodic triggers are useful when logic must re-run even without a new configuration item. Shorter intervals can produce more evaluations; balance detection latency against cost.

Do not assume every rule needs to be periodic. A rule checking bucket configuration can run on configuration changes. Use periodic only when that trigger is supported and scheduled re-evaluation is required.

### Detective evaluation

Detective evaluation checks resources that have already been deployed. AWS Config reads recorded configuration items and compares them against the rule.

For example: an existing security group opens TCP/22 to **0.0.0.0/0**; AWS Config records the change; the **restricted-ssh** rule evaluates the security group and returns NON_COMPLIANT if the configuration violates the rule.

This is the primary mode for monitoring existing configurations in an account.

### Proactive evaluation

Proactive evaluation checks planned properties before a resource is deployed. An application or pipeline submits the planned configuration so AWS Config can evaluate whether it satisfies proactive rules enabled in the account and Region.

Proactive evaluation fits Infrastructure as Code. For example, a pipeline checks a subnet configuration before deployment to see whether it would be evaluated as NON_COMPLIANT.

There are two limits to remember:

1. Only rules and resource types supporting proactive evaluation can participate.
2. Proactive evaluation does not automatically block deployments and does not automatically remediate resources marked NON_COMPLIANT.

To use proactive evaluation as a deployment gate, the pipeline must read the result and actively halt the deployment step when the result fails requirements. Do not assume enabling proactive evaluation will automatically block CloudFormation or Terraform.

## 6. Interpreting evaluation results

An AWS Config rule can return the following statuses:

| Status | Meaning | Next action |
|---|---|---|
| COMPLIANT | Resource meets the rule condition | Continue monitoring |
| NON_COMPLIANT | Resource does not meet the rule condition | Investigate and remediate |
| ERROR | Invalid parameter, wrong type, or wrong format | Fix rule configuration or logic |
| NOT_APPLICABLE | Rule logic does not apply to that resource | Check scope and resource type |

ERROR usually indicates the rule could not evaluate properly due to parameters or configuration; it should not be treated as a security violation. NOT_APPLICABLE also does not mean the resource passed the check, but rather that the rule logic does not apply to that resource.

Inspect per-resource results and evaluation details, not just aggregate compliant/noncompliant counts. If the resource type is not recorded by the recorder, the rule lacks the required data.

## 7. Conformance packs

A conformance pack is a collection of AWS Config rules and remediation actions described in a YAML template. A pack can be deployed as a single unit in an account and Region, or deployed as a custom/organization conformance pack across multiple accounts in AWS Organizations.

A pack can contain managed rules, custom policy rules, custom Lambda rules, Systems Manager Automation-based remediation actions, and input parameters to standardize values per environment.

For example, **baseline-security** can include rules for public S3, encryption, SSH, CloudTrail, and IAM. Another pack can focus on logging, backup, and tagging. Separating packs by objective clarifies ownership, deployment, and exception management.

For AWS Config templates, the main supported resource types are:

- **AWS::Config::ConfigRule**
- **AWS::Config::RemediationConfiguration**

### 7.1 Managed conformance packs

Managed conformance packs are defined and maintained by AWS. You choose a pack from the catalog, configure supported parameters, and deploy.

- Rule contents are maintained by AWS.
- Supported parameters can be modified.
- You cannot manually add or remove rules inside a managed pack.
- Deployed rules may differ between Regions due to differing rule support.
- AWS may add, update, or remove rules as requirements, services, or best practices evolve.
- Managed conformance packs are deployed per account and Region; they are not deployed via Organization Conformance Packs.

When AWS updates a managed pack, parameters you customized are preserved. Uncustomized parameters use current defaults. New rules may be introduced into existing deployments with default values. Monitor pack content updates and assess impact.

### 7.2 Custom conformance packs

Custom conformance packs are authored by the organization. You control rules, parameters, names, remediation, and update cadence.

Custom packs fit when an organization has its own baseline, needs to combine rules across services, add Guard/Lambda rules, bundle remediation, or deploy the same control set across multiple accounts via organization conformance packs.

You can start from an AWS sample template and tailor it to your resources, Regions, and internal processes. Sample templates are only starting points; AWS explicitly notes that templates do not guarantee compliance with any specific law or standard.

| Criterion | Managed pack | Custom pack |
|---|---|---|
| Content owner | AWS | Organization |
| Add/remove rules | No | Yes |
| Parameter configuration | Per supported parameters | Per template |
| Customize remediation | Per pack design | Designed by organization |
| Content updates | AWS may update | Published by organization |
| Organization deployment | Not supported via Organization Conformance Pack | Yes |
| Best suited for | Quick start with best practices | Custom baselines and centralized governance |

## 8. Building a custom conformance pack template

A template can have Parameters and Resources sections. Parameters declare values used to configure rules. Resources declare the rules and remediations.

The example below bundles two managed rules into a pack:

~~~yaml
Parameters:
  IamPasswordPolicyMinimumLength:
    Default: '14'
    Type: String
  AccessKeysMaximumAge:
    Default: '90'
    Type: String

Resources:
  IamPasswordPolicy:
    Type: AWS::Config::ConfigRule
    Properties:
      ConfigRuleName: iam-password-policy
      InputParameters:
        MinimumPasswordLength: !Ref IamPasswordPolicyMinimumLength
      Source:
        Owner: AWS
        SourceIdentifier: IAM_PASSWORD_POLICY

  AccessKeysRotated:
    Type: AWS::Config::ConfigRule
    Properties:
      ConfigRuleName: access-keys-rotated
      InputParameters:
        maxAccessKeyAge: !Ref AccessKeysMaximumAge
      Source:
        Owner: AWS
        SourceIdentifier: ACCESS_KEYS_ROTATED
~~~

Items to verify:

- **Owner: AWS** is used for managed rules.
- **Owner: CUSTOM_POLICY** is used for custom policy rules.
- **Owner: CUSTOM_LAMBDA** is used for custom Lambda rules.
- The managed rule's SourceIdentifier must match the identifier in AWS documentation.
- Parameter names in InputParameters must match the rule's parameters.
- Parameter types must match the rule's definition.
- The resource type evaluated by the rule must be recorded by the recorder.
- Rule names must remain stable because remediations reference them.

Do not copy compliance templates from the Internet and deploy them immediately. Check whether the rules are available in the Region, whether parameters fit, and which resources will be evaluated.

## 9. Attaching remediation to a conformance pack

A custom conformance pack can contain both Config rules and RemediationConfiguration. The following example uses the rule checking S3 bucket public read and the SSM Automation runbook **AWS-DisableS3BucketPublicReadWrite**.

The template sets manual mode first so operations teams can observe findings and check impact. After testing and approval, `Automatic` can be changed to `true` to enable auto-remediation.

~~~yaml
Resources:
  S3BucketPublicReadProhibited:
    Type: AWS::Config::ConfigRule
    Properties:
      ConfigRuleName: s3-bucket-public-read-prohibited
      Source:
        Owner: AWS
        SourceIdentifier: S3_BUCKET_PUBLIC_READ_PROHIBITED

  S3BucketPublicReadProhibitedRemediation:
    Type: AWS::Config::RemediationConfiguration
    DependsOn: S3BucketPublicReadProhibited
    Properties:
      ConfigRuleName: s3-bucket-public-read-prohibited
      ResourceType: AWS::S3::Bucket
      TargetType: SSM_DOCUMENT
      TargetId: AWS-DisableS3BucketPublicReadWrite
      TargetVersion: "1"
      Automatic: false
      MaximumAutomaticAttempts: 5
      RetryAttemptSeconds: 300
      ExecutionControls:
        SsmControls:
          ConcurrentExecutionRatePercentage: 10
          ErrorPercentage: 50
      Parameters:
        AutomationAssumeRole:
          StaticValue:
            Values:
              - arn:aws:iam::111122223333:role/ConfigRemediationAutomationRole
        S3BucketName:
          ResourceValue:
            Value: RESOURCE_ID
~~~

Replace **111122223333** with the appropriate AWS account ID and create the role with the matching name before deploying. The rule name in RemediationConfiguration must match the rule's ConfigRuleName exactly.

### Static and dynamic parameters

RemediationConfiguration can pass two types of values:

- **StaticValue:** fixed values, such as the ARN of the Automation assume role.
- **ResourceValue:** values substituted by AWS Config when running remediation.

In the example, **AutomationAssumeRole** is a static ARN of the role Automation will assume. **S3BucketName** receives **RESOURCE_ID**. For S3 buckets, the resource ID is the bucket name.

Dynamic parameters let a single remediation configuration handle multiple resources. Do not hard-code a fixed resource ID if the runbook needs to handle each violating bucket.

### DependsOn and intrinsic functions

RemediationConfiguration references the Config rule. `DependsOn` instructs CloudFormation to create the rule before creating the remediation.

For conformance pack remediation, AWS Config requires the Automation execution role ARN and ConfigRuleName to be declared with literal full values. Do not use CloudFormation intrinsic functions for these two values in the remediation configuration section. Replace the sample ARN with a real ARN before deploying.

## 10. Deploying a conformance pack

Before deploying:

1. Enable AWS Config recording in the Region.
2. Verify the recorder includes the resource types the pack needs to evaluate.
3. Confirm the rules are available in the Region.
4. Create the Automation assume role if the pack includes remediation.
5. Create the Lambda function and execution role if the pack includes custom Lambda rules.
6. Configure the S3 delivery bucket and bucket policy when storing templates/artifacts.
7. Verify permissions of the principal deploying the pack.

### Deploying from the console

In the AWS Config console, open Conformance packs, choose Deploy conformance pack, select a managed or custom pack, configure parameters/template, review, and deploy. For templates larger than 50 KB, upload the template to S3 and select the S3 URI. After deploying, monitor deployment status.

The conformance pack name must be unique within the account and Region, up to 256 alphanumeric characters, may include hyphens, and cannot contain spaces.

### Deploying a custom pack with the AWS CLI

Example deploying a template from a local file to the Singapore Region:

~~~bash
aws configservice put-conformance-pack \
  --conformance-pack-name s3-public-access-baseline \
  --template-body file://s3-public-access-baseline.yaml \
  --delivery-s3-bucket config-artifacts-111122223333 \
  --region ap-southeast-1
~~~

If the template is stored in S3, use **--template-s3-uri** instead of **--template-body**.

Monitor deployment status:

~~~bash
aws configservice describe-conformance-pack-status \
  --conformance-pack-name s3-public-access-baseline \
  --region ap-southeast-1
~~~

View compliance status:

~~~bash
aws configservice describe-conformance-pack-compliance \
  --conformance-pack-name s3-public-access-baseline \
  --region ap-southeast-1
~~~

Successful deployment does not mean all rules have finished evaluating. Wait for rules to complete evaluation and inspect details for each rule/resource.

### Updating and deleting packs

When updating a custom pack, republish the updated template. Carefully review adding/removing rules, changing parameters, or changing remediation because these changes can generate many findings or alter live resources.

When deleting a pack, the rules and remediations belonging to the pack are also deleted. Check dashboards, downstream workflows, and evidence retention requirements before deleting. Deleting a remediation action does not delete the Config rule; the two operations have separate lifecycles.

## 11. Deploying at AWS Organizations scale

Organization conformance packs enable centralized governance from the organization management account or an eligible delegated administrator. Organizations can deploy, update, and delete packs across member accounts while optionally excluding specific accounts from deployment.

General flow:

1. Enable AWS Config recording in target accounts and Regions.
2. Set up AWS Organizations and service integration permissions.
3. Create or verify the required service-linked role.
4. Prepare the template and an S3 delivery bucket with an appropriate bucket policy.
5. If remediation is included, create the Automation execution role with the same name in every target account.
6. Call `PutOrganizationConformancePack` in each Region requiring governance.
7. Monitor deployment status and detailed status per member account.
8. Handle new accounts, accounts without a recorder, and permission errors.

Key points to remember:

- The organization pack deployment API is Region-scoped. To deploy to another Region, call the API in that Region.
- When a new account joins the Organization, the organization pack is deployed to that account.
- When an account leaves the Organization, the corresponding organization pack is removed from that account.
- AWS Config only retries deployment for a new account for 7 hours after the account joins the Organization if no recorder exists yet; create the recorder within this window.
- If using a delegated administrator, pay attention to the service-linked role in the management account.
- The role used to run remediation must exist in all relevant accounts before calling `PutOrganizationConformancePack`.

Managed conformance packs do not support deployment via Organization Conformance Packs. If centralized deployment through Organizations is needed, use a custom conformance pack.

Commonly used APIs:

- **PutOrganizationConformancePack:** create or update an organization pack.
- **DescribeOrganizationConformancePacks:** list organization packs.
- **DescribeOrganizationConformancePackStatuses:** view deployment status.
- **GetOrganizationConformancePackDetailedStatus:** view status per member account.
- **DeleteOrganizationConformancePack:** delete the pack across member accounts.

An organization-level deployment request can succeed in some accounts while failing in others. Include account ID, Region, status, and error message in operational reports.

## 12. Process checks

Not every compliance requirement can be inferred from AWS configuration. Some controls require attestation from humans or systems outside AWS.

Process checks allow including those tasks in a conformance pack. Examples:

- Confirm offline backups are stored in an independent location.
- Confirm access approval workflows were followed.
- Confirm recovery test reports were reviewed.
- Confirm personnel completed periodic security training.

Process checks help combine configuration control results and process controls in the same pack. Status must be updated according to organizational evidence and procedures. This is not an automated resource configuration discovery mechanism.

## 13. Remediation with Systems Manager Automation

AWS Config performs remediation using AWS Systems Manager Automation documents. An Automation document, commonly called a runbook, describes the steps to run and input parameters. AWS provides managed Automation documents and allows creating custom documents.

| Runbook | Purpose |
|---|---|
| **AWS-DisableS3BucketPublicReadWrite** | Uses S3 Block Public Access to disable public read/write |
| **AWS-EnableS3BucketEncryption** | Configures default encryption for an S3 bucket |
| **AWS-ConfigureS3BucketVersioning** | Configures S3 bucket versioning |
| **AWSConfigRemediation-ConfigureS3BucketPublicAccessBlock** | Configures S3 Block Public Access per remediation workflow |

The runbook name alone is not proof that the action is suitable. Read its description, parameters, steps, IAM permissions, and impact on resources before attaching it to a rule.

### Manual remediation

Manual remediation associates a runbook with a rule but requires an operator to initiate it explicitly. This fits when the action may be disruptive, requires approval, needs exception verification, or the operations team wants to test one resource at a time.

The `StartRemediationExecution` API starts remediation for selected resource keys based on the existing configuration. Operators must inspect execution results and re-evaluate the resource.

### Automatic remediation

Automatic remediation lets AWS Config automatically start Automation when it detects a resource is NON_COMPLIANT for the configured rule.

1. The rule evaluates the resource and returns NON_COMPLIANT.
2. AWS Config looks up the matching remediation configuration.
3. AWS Config passes static/dynamic parameters to the SSM document.
4. Systems Manager starts the Automation.
5. Automation assumes the role and executes the steps.
6. AWS Config records and evaluates the post-change configuration.

Automatic remediation fits well-scoped actions that can be safely repeated and are unlikely to break workloads. Do not enable auto on every rule just because a runbook exists.

| Criterion | Manual | Automatic |
|---|---|---|
| Initiator | Operator or approved workflow | AWS Config |
| Execution timing | After review | After the rule detects a violation |
| Processing speed | Depends on operator | Can be fast and consistent |
| Impact control | Easy to inspect per resource | Requires concurrency and scope limits |
| Best suited for | Risky actions or those needing approval | Repeatable, controllable actions |

A practical design usually starts with manual remediation, measures success rate and impact, and then transitions to automatic for validated resource groups.

## 14. IAM for remediation

Remediation has multiple permission layers. Do not use a single `AdministratorAccess` role for the entire workflow.

### AWS Config service-linked role

When deploying a conformance pack, AWS Config uses its corresponding service-linked role, typically named **AWSServiceRoleForConfigConforms**, to create Config rules and remediation configurations in the account.

### Automation assume role

SSM Automation can run in the context of the caller or an IAM service role. AWS recommends using a service role/assume role to control the permissions a runbook is allowed to execute.

Minimal illustrative trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ssm.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

The role needs the permissions required by each step of the runbook. For example, a runbook fixing S3 buckets may need permission to read Block Public Access status and update that configuration. Read the steps in the runbook to determine exact permissions, restrict resource ARNs, and avoid wildcard permissions whenever possible.

### Deploying principal and iam:PassRole

The principal deploying a pack needs permissions to create/update conformance packs, read templates from S3 or SSM documents, and allow AWS Config to create the service-linked role when needed. API documentation notes common errors such as missing IAM `GetRole`, `CreateServiceLinkedRole`, S3 read permissions, or `ssm:GetDocument`.

When a principal invokes Automation with a service role, check `iam:PassRole` permission for the passed role. Scope `PassRole` to the exact role and trusted service.

A typical design separates three groups:

- **Config deployment role:** deploys rules, packs, and updates configurations.
- **Automation execution role:** assumed by SSM to remediate resources.
- **Operator role:** views compliance, investigates findings, runs manual remediation, and handles exceptions.

Separating roles helps audits identify who changed the baseline, which service executed the action, and which operator approved manual steps.

## 15. Retries, concurrency, and errors

Remediation can fail due to missing permissions, changed resources, invalid runbook parameters, target service throttling, or the resource state no longer matching evaluation time.

| Property | Meaning |
|---|---|
| MaximumAutomaticAttempts | Maximum failed attempts before creating a remediation exception |
| RetryAttemptSeconds | Time window used to count retry attempts |
| ConcurrentExecutionRatePercentage | Percentage of remediations allowed to run concurrently for the rule |
| ErrorPercentage | Allowed error percentage before Systems Manager stops running automations for the rule |

According to the API reference, if unspecified, `MaximumAutomaticAttempts` defaults to 5 and `RetryAttemptSeconds` defaults to 60 seconds. `MaximumAutomaticAttempts` has a maximum limit of 25. `RetryAttemptSeconds` and concurrency/error values have limits per the API schema; check the API reference when configuring.

In the template example, **ConcurrentExecutionRatePercentage: 10** keeps parallel execution rate low to start. **ErrorPercentage: 50** allows a certain error threshold before SSM halts execution. Choose values based on resource count, risk level, and workload resilience.

When repeated auto-remediations fail within the retry window, AWS Config can create a remediation exception for the resource. Exceptions prevent infinite loops of a failing action. Operations teams need to review exceptions, address root causes, and manage lifecycles per procedure.

Retries do not replace fixing root causes. Increasing retries while a role lacks permissions or parameters are wrong only increases failures and Automation costs.

## 16. Auto-remediation risks and limiting blast radius

Automatically modifying configurations can impact running applications. For example, a bucket might intentionally be public to serve a static website. Enabling Block Public Access immediately could take the website offline.

Another technical risk is that AWS Config uses periodic compliance data snapshots to initiate auto-remediation. If a resource was already fixed after the snapshot but the snapshot has not yet updated, remediation may still start based on the stale NON_COMPLIANT state. Consequently, an action can occasionally launch against a resource that is already compliant.

Controls to apply:

1. Start with manual remediation for high-impact actions.
2. Restrict scope by resource type, tag, or account.
3. Manage valid exceptions with a time-bound process and owner.
4. Use runbooks that can be safely repeated (idempotent) where possible.
5. Check current state immediately before making changes.
6. Limit concurrency and error thresholds.
7. Test in development, then staging, before production.
8. Log inputs, target resources, step outcomes, and errors.
9. Have a rollback or configuration recovery path if an action affects workloads.
10. Monitor remediation exceptions and do not leave exceptions active indefinitely.

For changes that could cause data loss, delete resources, lock out access, or disrupt production, require a separate approval step rather than enabling auto-remediation immediately.

## 17. API limits and deployment models

Not every rule can attach remediation in the same way.

- The AWS Config console only allows managing remediation directly for non-service-linked rules.
- The `PutRemediationConfigurations` API does not support adding remediation configurations to service-linked rules such as organization Config rules, rules deployed by conformance packs, or rules deployed by AWS Security Hub.
- If you need to bundle rules and remediation in a custom conformance pack, declare both `AWS::Config::ConfigRule` and `AWS::Config::RemediationConfiguration` in the same template.
- If an SSM document changes in a backward-incompatible way, update the remediation configuration so AWS Config uses the compatible target configuration.
- Some rules are only available in certain Regions. Check Region availability before deploying a pack.
- Resources must be recorded by the recorder for rules to have evaluation data.

Distinguish between a remediation configuration attached directly to a standalone rule and remediation defined inside a custom conformance pack.

## 18. Monitoring compliance and remediation

Monitor three layers:

### Rule compliance

Inspect which rules are COMPLIANT/NON_COMPLIANT/ERROR/NOT_APPLICABLE, which resources are flagged, rule parameters/scope, and evaluation timestamps.

You can request rule re-evaluation via CLI:

~~~bash
aws configservice start-config-rules-evaluation \
  --config-rule-names s3-bucket-public-read-prohibited \
  --region ap-southeast-1
~~~

### Conformance pack status

The conformance pack dashboard displays deployment status, compliance score, and the rules in the pack. The compliance score is the ratio of compliant rule-resource pairs over total possible pairs. While a pack is deploying, the score may be incomplete.

Pack aggregate status follows specific rules: a pack is NON_COMPLIANT if any rule is NON_COMPLIANT; a pack is INSUFFICIENT_DATA only when all rules lack evaluation data. If some rules are COMPLIANT and the remaining rules are INSUFFICIENT_DATA, the pack still displays COMPLIANT. Compliance is evaluated per rule group, not necessarily with all rules completing simultaneously. Therefore, open individual rules and resources to inspect detailed results.

To report compliance accurately, the recorder must record **AWS::Config::ResourceCompliance**. To view pack compliance history changes on the timeline, you can record **AWS::Config::ConformancePackCompliance**.

### Remediation execution

For failed remediations, use `DescribeRemediationExecutionStatus` to inspect status, step timestamps, and error messages. Then check SSM Automation execution history to locate the failing step.

Example starting manual remediation for a test S3 bucket:

~~~bash
aws configservice start-remediation-execution \
  --config-rule-name s3-bucket-public-read-prohibited \
  --resource-keys resourceType=AWS::S3::Bucket,resourceId=my-test-bucket \
  --region ap-southeast-1
~~~

Replace the resource ID with a verified appropriate bucket and test before executing.

## 19. Architecture example: multi-account security baseline

Suppose a company has three account groups: Shared services containing CI/CD, logging, and networking tools; Development for dev environments; and Production running live applications.

The cloud platform team maintains a custom conformance pack **company-security-baseline** covering S3 public access, S3 default encryption, EBS volume encryption, security group SSH exposure, CloudTrail enabled, and IAM password policy.

Operational workflow:

1. The platform team updates the template in a repository.
2. Pull requests are reviewed by security and cloud operations.
3. The pipeline validates YAML, rule names, resource types, and Region availability.
4. The pipeline deploys the pack to a test account.
5. Operations reviews findings and verifies false positives.
6. Remediation is run manually for resources needing fixes.
7. Once runbooks are proven, selected rules can transition to automatic.
8. The pack is deployed via Organizations to appropriate accounts/OUs.
9. A dashboard aggregates status, remediation failures, and exceptions.
10. Every baseline change is stored in version control with approval history.

~~~mermaid
flowchart TD
    A["Security baseline repository"] --> B["Review and CI validation"]
    B --> C["Test account and Region"]
    C --> D["AWS Config conformance pack"]
    D --> E["Organization deployment"]
    E --> F["Development accounts"]
    E --> G["Production accounts"]
    F --> H["Compliance findings"]
    G --> H
    H --> I["Manual or automatic SSM remediation"]
    I --> J["Re-evaluation and audit evidence"]
    J --> K["Central operations dashboard"]
~~~

Do not deploy a baseline with the same level of automation across all accounts. Development may allow broader automatic remediation. Production may require approval for changes with potential service impact.

## 20. Lab: creating rules, conformance packs, and testing remediation

The lab uses a test bucket and the **ap-southeast-1** Region. Do not use production buckets or buckets serving live websites.

### Step 1: prepare AWS Config

- Open AWS Config in the test Region.
- Enable the configuration recorder.
- Ensure the recorder records S3 buckets.
- Confirm the delivery channel and IAM role are working.

### Step 2: prepare the Automation role

- Create an IAM role for Systems Manager Automation.
- Trust policy allows **ssm.amazonaws.com** to assume the role.
- Attach least-privilege permissions per the steps of runbook **AWS-DisableS3BucketPublicReadWrite**.
- Record the role ARN.
- Confirm the deploying principal has the required permission to pass the role to Automation.

### Step 3: create a test bucket

Create a bucket solely for lab use. If you need to generate a NON_COMPLIANT state, configure public read on the test bucket in a manner permitted by AWS in the lab account. Do not apply this step to real data.

### Step 4: create the conformance pack

- Save the template from section 9 as **s3-public-access-baseline.yaml**.
- Replace the account ID in the Automation role ARN.
- Ensure the rule name in remediation matches the rule's ConfigRuleName.
- Keep **Automatic: false** for the initial run.
- Deploy the pack using the AWS CLI or console.

### Step 5: inspect rule results

Wait for AWS Config to evaluate the bucket. Open Conformance packs, select the pack, and view the rule and NON_COMPLIANT resource. Verify the test bucket and confirm the reason for the violation.

### Step 6: run manual remediation

Run `StartRemediationExecution` for the test bucket or launch remediation from the console. Monitor the Automation execution in Systems Manager. Inspect each step, inputs, and outputs.

### Step 7: re-verify

- Check the bucket's S3 Block Public Access settings.
- Trigger AWS Config rule re-evaluation.
- Confirm status transitions to COMPLIANT.
- Record detection time, remediation time, and outcome.

### Step 8: test automatic remediation

After manual remediation succeeds, update the template to set **Automatic: true**, deploy the pack update to the lab environment, and test on another test bucket. Observe retries, concurrency, errors, and compliance status.

## 21. Common troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Rule has no results | Resource type not recorded by recorder | Check recorder and Region |
| Rule stays INSUFFICIENT_DATA | No matching resources or no data yet | Check resource type, scope, and initial recording |
| Rule returns ERROR | Input parameter wrong type or format | Cross-check parameter with rule documentation |
| Rule evaluates wrong resources | Incorrect scope or tag filter | Check scope and actual tags |
| Custom Lambda rule does not run | Wrong Lambda ARN, permission, or execution role | Check invoke permissions, CloudWatch Logs, and timeout |
| Guard rule gives unexpected results | Wrong configuration path or schema | Check payload and Guard policy |
| Pack deployment fails | Missing permissions, S3 bucket policy, or recorder off | Check prerequisites, IAM, and S3 access |
| Pack only deploys partially | Some accounts lack recorder or role | View detailed status per account |
| SSM Automation fails to start | Missing `StartAutomationExecution`, `PassRole`, or trust relationship | Check IAM caller and Automation role |
| Runbook cannot find resource | Wrong dynamic parameter or resource type | Check `RESOURCE_ID` and document parameters |
| Runbook runs but fails to fix | Role lacks permissions on resource | Read step error and add least-privilege permissions |
| Remediation fails repeatedly | Wrong parameters, service error, or changed state | Stop retries, investigate root cause, check exceptions |
| Compliant resource still remediated | Compliance snapshot not yet updated | Check current state and execution history |
| Pack compliance score is low | Many resources/rules non-compliant | Inspect rule-resource details and prioritize by risk |
| Rule has no remediation option | Rule is service-linked or deployment method unsupported | Include remediation in a custom conformance pack template if appropriate |

### Troubleshooting workflow for remediation failures

1. Identify the account, Region, Config rule, and resource ID.
2. Check the compliance result and evaluation timestamp.
3. Check the remediation configuration: TargetId, TargetVersion, Automatic, and Parameters.
4. Open the SSM Automation execution to find the failing step.
5. Check the IAM role trust relationship and permissions for each API call.
6. Check whether the resource still exists and still needs remediation.
7. Verify the runbook receives the right dynamic resource ID.
8. Fix the configuration and re-run manually on a single resource.
9. Only re-enable auto-remediation once results are stable.
10. Monitor remediation exceptions to ensure errors are not silently masked.

## 22. Cost and quotas

Costs to consider include AWS Config recording and evaluations, number of recorded resource types/resources, periodic evaluation frequency, Systems Manager Automation executions, Amazon S3 storage for templates/history/snapshots, plus Lambda and CloudWatch Logs if custom rules use Lambda.

A periodic rule running frequently across a wide scope can generate many evaluations. Failed remediations with many retries can create extra Automation executions. To optimize cost:

- Record only resource types with clear control needs, or use all supported resource types when coverage benefits outweigh cost.
- Avoid overly frequent periodic triggers if configuration change triggers meet requirements.
- Scope by resource type/tag when a policy does not apply to all resources.
- Remove duplicate or unused rules.
- Monitor evaluation counts and remediation execution counts.
- Design runbooks to exit early when a resource is already in the desired state.

AWS Config quotas may change over time. At the time of writing, AWS documentation lists these main limits:

| Item | Default quota |
|---|---:|
| AWS Config rules per account, per Region | 1,000 |
| Conformance packs per account | 50 |
| Config rules in a conformance pack | 130 |
| Organization conformance packs per Organization | 50 |
| Config rules in an organization conformance pack | 130 |
| Configuration aggregators | 50 |
| Accounts in an aggregator | 10,000 |

Rules inside a conformance pack still count toward the account/Region AWS Config rules quota. Organization-level packs also count toward child accounts' quotas. Templates passed inline in API calls have size limits; larger templates must be stored in S3. Check service quotas and API references before large rollouts.

## 23. Best practices

### Rule design

- Write rule descriptions in business terms.
- Scope intentionally to avoid evaluating out-of-scope resources.
- Choose triggers matching desired detection latency.
- Verify the resource type is recorded by the recorder.
- Use managed rules if built-in logic already exists.
- Keep custom Guard/Lambda rules in version control and review them like source code.

### Conformance pack design

- Split packs by security, operations, or cost governance objectives.
- Use parameters to standardize thresholds per environment.
- Check rule availability in each Region.
- Version-control templates with a review workflow.
- Use custom packs when deploying via AWS Organizations.
- Track content updates in AWS-maintained managed packs.
- Do not treat sample packs as compliance certifications.

### Remediation design

- Start with manual remediation for high-impact actions.
- Read the entire runbook before attaching it to a rule.
- Use a dedicated Automation assume role with least privilege.
- Pass dynamic resource IDs rather than hard-coding resource IDs.
- Prefer idempotent actions.
- Limit concurrency and error percentage.
- Set reasonable retries; do not use retries to mask configuration errors.
- Monitor stale compliance snapshots and remediation exceptions.
- Have rollback or recovery procedures for risky changes.

### Multi-account operations

- Enable recorders before deploying organization packs.
- Deploy by Region and by OU/account scope.
- Create the Automation role in every account requiring remediation.
- Use a delegated administrator when the operating model calls for it.
- Monitor detailed deployment status per account.
- Assign owners and expiration dates to all exceptions.
- Maintain template change and approval history.

## 24. Self-practice exercises

1. A rule checking EBS encryption returns no results for newly created volumes. Which component do you check first?
2. When should you use a configuration change trigger instead of a periodic trigger?
3. State the difference between detective and proactive evaluation.
4. Does proactive evaluation automatically block CloudFormation from deploying a NON_COMPLIANT resource? Explain.
5. A managed rule has a `maxAccessKeyAge` parameter. The organization requires a maximum of 60 days. Where do you configure it?
6. When should you choose a custom Guard rule instead of a custom Lambda rule?
7. A conformance pack has 12 rules. What is the benefit of deploying them via a single YAML template?
8. Can you manually add rules to a managed conformance pack?
9. Why might a managed conformance pack contain different numbers of rules between two Regions?
10. An organization wants to deploy a baseline via AWS Organizations. Should they use a managed or custom conformance pack?
11. Why does the Automation assume role need narrower permissions than AdministratorAccess?
12. In RemediationConfiguration, how does `RESOURCE_ID` help?
13. Why should you start with manual remediation for enabling Block Public Access on production buckets?
14. What can happen when AWS Config uses a stale compliance snapshot to trigger auto-remediation?
15. When do repeated retries increase cost without solving the problem?
16. An organization conformance pack failed to deploy in two accounts. Which data do you inspect?
17. Why does a template with remediation require the Automation role to exist in target accounts?
18. An SSM document changes in a backward-incompatible way. Which component needs to be updated?
19. Why should you not rely solely on a pack's aggregate compliance score?
20. Which type of compliance requirements do process checks fit?

### Answer hints

1. Check whether the recorder records **AWS::EC2::Volume** in the right Region.
2. Use configuration change when evaluation is needed after each change; periodic when scheduled re-checks are needed even without configuration changes.
3. Detective evaluates deployed resources; proactive evaluates planned properties before deployment.
4. No. The pipeline or deployment system must read the result and decide to stop.
5. In the rule's input parameter or the corresponding parameter in the conformance pack template.
6. When the policy can be clearly expressed in Guard without complex logic/integrations.
7. Easy to version, review, deploy repeatably, and track the baseline as a unit.
8. No. Managed pack rule contents are managed by AWS.
9. Rule availability can vary by Region.
10. Custom conformance pack, because managed packs do not support Organization Conformance Packs.
11. To limit blast radius if the runbook errors or is invoked unexpectedly.
12. AWS Config replaces `RESOURCE_ID` with the ID of the violating resource at runtime.
13. Because a bucket may serve a website or application requiring public access; the action could cause downtime.
14. Remediation may still start based on the old NON_COMPLIANT state even though the resource was already fixed.
15. When the cause is missing permissions, wrong parameters, or logic bugs; retries just repeat the error.
16. Account ID, Region, deployment status, detailed status, recorder, and IAM role.
17. SSM Automation must assume the role to execute APIs modifying resources.
18. Update the remediation configuration/pack to use a compatible document version and parameters.
19. Because an aggregate score can hide rules/resources missing data or specific violations.
20. Requirements needing verification by humans or systems outside AWS, such as document checks, approvals, or recovery drills.

## 25. Interview questions

### How does an AWS Config rule differ from a CloudTrail event?

CloudTrail records API activity and who performed an action. AWS Config records resource configuration state over time and evaluates that state against rules. CloudTrail helps investigate who made a change; Config helps determine whether the post-change configuration is compliant.

### When do you choose a managed rule?

When AWS already provides appropriate logic and the requirement can be expressed via input parameters. Managed rules reduce the amount of custom code to maintain.

### How does a custom Guard rule differ from a custom Lambda rule?

Guard expresses policy-as-code to check configuration attributes. Lambda fits more complex logic requiring custom processing or calling external systems. Lambda increases responsibility for managing runtime, IAM, logging, and retries.

### Why is proactive evaluation not a deployment gate?

AWS Config returns an evaluation result, but does not block deployments itself. Pipelines must invoke the evaluation API, read the result, and enforce stop/allow policies.

### Why can managed conformance packs not be deployed via Organization Conformance Packs?

This is a documented limitation of managed packs by AWS. When organization-wide deployment is needed, use custom conformance packs and manage your organization's templates.

### Does a conformance pack guarantee ISO 27001 or PCI DSS certification?

No. A pack is an AWS configuration checking framework and can assist in gathering evidence. Achieving certification also depends on processes, people, scope, evidence, and assessment by the organization/independent auditors.

### Why might remediation run on an already compliant resource?

AWS Config uses periodic compliance data snapshots to initiate some auto-remediations. The snapshot may be older than the current state. Therefore, check state inside the runbook and manage scope carefully, especially when enabling auto on existing resources.

### When should automatic remediation be enabled?

When the action has been tested, can run safely and repeatedly, permissions are scoped, concurrency/error limits are set, and workload impact has been assessed. High-risk actions should require approval.

### How do you limit impact when remediation runs across many resources?

Restrict scope, use manual mode initially, set concurrency/error thresholds, roll out in small batches, use idempotent runbooks, and track outcomes per resource.

## 26. Pre-production checklist

### AWS Config

- [ ] Recorder enabled in each Region requiring governance.
- [ ] Recorder includes resource types needing evaluation.
- [ ] Delivery channel and history storage configured.
- [ ] Config IAM role has least-privilege permissions.
- [ ] Rule scope and triggers reviewed.
- [ ] Managed/custom rules verified against documentation and Region availability.
- [ ] Proactive evaluation integrated into pipelines if a deployment gate is needed.

### Conformance pack

- [ ] Template stored in version control.
- [ ] Rule names and parameters consistent.
- [ ] Template does not exceed size limits when passed inline.
- [ ] Rules are available in the target Region.
- [ ] S3 bucket policy for delivery artifacts verified.
- [ ] Pack tested in a test account.
- [ ] Organization pack has detailed status per account.
- [ ] Rule/pack quotas checked before rollout.

### Remediation

- [ ] Runbook read and tested.
- [ ] Automation assume role has appropriate trust relationship.
- [ ] IAM permissions scoped by action and resource.
- [ ] Dynamic parameters map to the right resource ID.
- [ ] ConfigRuleName and Automation role ARN are literal full values as required by templates.
- [ ] Manual remediation succeeded before enabling auto for risky actions.
- [ ] Retries, concurrency, and error percentage configured appropriately.
- [ ] Exception handling and rollback procedures in place.
- [ ] Monitoring configured for SSM Automation executions and errors.

### Governance

- [ ] Owners assigned for each pack and each exception.
- [ ] Approval process exists for baseline changes.
- [ ] Expiration dates set for exceptions.
- [ ] Compliance reports available by account/Region.
- [ ] Audit evidence retained per policy.
- [ ] Operations team understands packs do not replace legal/regulatory compliance assessments.

## 27. Official documentation

- [AWS Config terminology and concepts](https://docs.aws.amazon.com/config/latest/developerguide/config-concepts.html)
- [Components of an AWS Config Rule](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_components.html)
- [AWS Config Managed Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_use-managed-rules.html)
- [Creating AWS Config Custom Policy Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_develop-rules_cfn-guard.html)
- [Evaluating resources with AWS Config Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluating-your-resources.html)
- [Conformance Packs for AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/conformance-packs.html)
- [Creating templates for Custom Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/custom-conformance-pack.html)
- [Prerequisites for Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/cpack-prerequisites.html)
- [Deploying Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-pack-deploy.html)
- [Managing Organization Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-pack-organization-apis.html)
- [Remediating Noncompliant Resources with AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/remediation.html)
- [Setting Up Auto Remediation](https://docs.aws.amazon.com/config/latest/developerguide/setup-autoremediation.html)
- [PutRemediationConfigurations API](https://docs.aws.amazon.com/config/latest/APIReference/API_PutRemediationConfigurations.html)
- [AWS-DisableS3BucketPublicReadWrite runbook](https://docs.aws.amazon.com/systems-manager-automation-runbooks/latest/userguide/automation-aws-disables3bucketpublicreadwrite.html)
- [Systems Manager Automation IAM roles](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup-iam.html)
- [AWS Config service limits](https://docs.aws.amazon.com/config/latest/developerguide/configlimits.html)
- [Viewing Compliance Data in the Conformance Packs Dashboard](https://docs.aws.amazon.com/config/latest/developerguide/conformance-pack-dashboard.html)
- [Compliance History Timeline for Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/compliance-history-conformance-pack.html)

