# CloudFormation StackSets for Multiple Accounts and Regions

> **Chapter:** Infrastructure as Code  
> **Module:** `CLOUD_PROVIDERS_AWS` — exploring the AWS ecosystem across Regions/AZs, IAM, VPC, compute services, storage, databases, integration, and serverless. Learners build the ability to choose services and design and deploy applications that are secure, observable, recoverable, and cost-controlled.

## Learning Objectives

AWS CloudFormation StackSets extend the Infrastructure as Code (IaC) model from a single stack in one account/Region to coordinated deployments across multiple AWS accounts and Regions. A StackSet holds the template and deployment configuration; each target account/Region receives a corresponding **stack instance**.

This lesson builds a baseline for an AWS Organization, deploys across multiple Organizational Units (OUs) and Regions, and then monitors operations, detects drift, and handles errors in a controlled manner. The content focuses on two permission models: service-managed and self-managed.

After this lesson, you will be able to:

1. Distinguish Stack, StackSet, stack instance, and StackSet operation.
2. Choose service-managed or self-managed permissions based on the governance model.
3. Explain AWS Organizations trusted access and delegated administrator.
4. Select account/OU targets, account filters, and Regions.
5. Design templates with parameters, pseudo parameters, and region-specific values.
6. Create StackSets and stack instances using the AWS CLI.
7. Configure Region concurrency, failure tolerance, and concurrency modes.
8. Design auto-deployment when accounts join or leave an OU.
9. Detect drift and understand the limitations of drift detection.
10. Execute wave rollouts, handle partial failures, and control rollbacks.
11. Protect administrative permissions, execution roles, SCPs, KMS, and auditing.
12. Operate StackSets with metrics, operation history, and runbooks.

## 1. What Problem Do StackSets Solve?

### 1.1. From One Stack to Multiple Accounts and Regions

A CloudFormation stack deploys resources in one specific account and Region. If an organization has dozens of accounts, each running across multiple Regions, copying templates and deploying manually causes configuration drift, lacks auditability, and creates high operational overhead.

StackSets allow managing a template from one central place and creating/updating/deleting stacks across many accounts/Regions in a single operation.

~~~mermaid
flowchart TD
    ADMIN[CloudFormation StackSet]
    ADMIN --> A1[Account A]
    ADMIN --> A2[Account B]
    ADMIN --> A3[Account C]
    A1 --> R11[ap-southeast-1 stack]
    A1 --> R12[ap-southeast-2 stack]
    A2 --> R21[ap-southeast-1 stack]
    A2 --> R22[ap-southeast-2 stack]
    A3 --> R31[ap-southeast-1 stack]
    A3 --> R32[ap-southeast-2 stack]
~~~

For example, a security baseline needs to create the same CloudWatch log group, AWS Config rule, or IAM role in every workload account. StackSets let you define the template once and deploy it by OU and Region.

### 1.2. Four Concepts to Distinguish

| Concept | Meaning |
|---|---|
| Stack | A collection of resources managed by CloudFormation in one account/Region |
| StackSet | Central definition containing the template, parameters, permissions, and deployment configuration |
| Stack instance | A stack managed by a StackSet in a specific account/Region |
| StackSet operation | A create/update/delete/drift detection/import execution across a set of stack instances |

A StackSet can manage many stack instances. A stack instance is identified by account and Region; the same account can have one instance in Singapore and another in Sydney.

### 1.3. Deployment Matrix

Suppose an organization has 3 accounts and 2 Regions:

| Account | ap-southeast-1 | ap-southeast-2 |
|---|---|---|
| Shared Services | Stack instance | Stack instance |
| Development | Stack instance | Stack instance |
| Production | Stack instance | Stack instance |

An operation can deploy to the entire matrix or a subset. Clearly define the target set to avoid accidentally applying changes to production.

### 1.4. When to Use StackSets?

StackSets fit foundational configurations requiring uniformity:

- Shared IAM roles/policies;
- AWS Config rules and conformance baselines;
- CloudWatch log groups, alarms, or account-level settings;
- GuardDuty/Security Hub/CloudTrail configuration;
- Per-account VPC endpoints or network baselines;
- SSM parameters, deployment agents, and tagging baselines.

StackSets do not replace every deployment pipeline. Applications with independent release cadences, complex dependencies, or per-workload approval requirements may fit dedicated pipelines better, while StackSets manage account baselines.

## 2. StackSet Permissions: Service-Managed and Self-Managed

### 2.1. Two Permission Models

| Criterion | Service-managed | Self-managed |
|---|---|---|
| Target scope | Accounts in AWS Organizations; can target organization/OU | Specified Account IDs |
| Role provisioning | CloudFormation/Organizations manages service-linked roles | Organization creates and manages IAM roles itself |
| Organizations | Required for this model | Not required |
| Account onboarding | Can automatically deploy to new accounts in target OUs | Must update targets/deployments manually |
| Delegated administrator | Supported | Does not use Organizations delegated admin under this model |
| Role control | Managed via service-linked roles and Organizations | Trust/policy roles managed by the organization |
| Best suited for | Enterprise multi-account governance | Cross-account deployments with custom role setups or without Organizations |

Neither model is always better. If the organization already manages accounts via AWS Organizations, service-managed usually reduces creating and maintaining execution roles. Self-managed works well when targeting specific accounts outside the same Organization or wanting direct control over role provisioning.

### 2.2. Service-Managed Permissions

Service-managed StackSets integrate with AWS Organizations. Once trusted access is enabled, CloudFormation can create and use the required service-linked roles in the management account and member accounts.

You do not need to manually create administrator/execution roles in each target account. CloudFormation orchestrates role provisioning according to Organizations and the permission model.

Important conditions and limitations:

- Target accounts must belong to an AWS Organization;
- A StackSet can target the entire organization or specific OUs;
- Cannot target accounts outside the Organization;
- Service-managed StackSets **do not deploy to the management account**;
- Service-managed StackSets do not support nested stacks or templates containing macros/transforms;
- Deployment actions are initiated from the management account or a registered delegated administrator.

If you need to deploy to the management account, evaluate self-managed permissions and a separate governance process for that account.

### 2.3. Self-Managed Permissions

With self-managed StackSets, the organization must prepare IAM roles:

1. **Administration role** in the account controlling the StackSet;
2. **Execution role** in each target account;
3. Trust policy allowing the administration role to assume the execution role;
4. Permission policy on the execution role to create/update resources required by the template.

Model:

~~~mermaid
flowchart LR
    OP[Operator / CI role]
    OP --> ADMIN[Administration role]
    ADMIN -->|AssumeRole| E1[Execution role - Account A]
    ADMIN -->|AssumeRole| E2[Execution role - Account B]
    E1 --> CFN1[CloudFormation resources]
    E2 --> CFN2[CloudFormation resources]
~~~

Role names can be customized but must match the StackSet configuration. The organization is responsible for creating, securing, rotating/updating policies, and managing trust relationships. Do not copy an `AdministratorAccess` execution role into every account.

### 2.4. Choosing a Model by Scenario

- All workload accounts belong to one Organization and require OU-based auto-deployment: evaluate service-managed first.
- Target accounts sit outside an Organization or have custom cross-account role requirements: evaluate self-managed.
- Need to deploy into the management account: plan separately; service-managed does not target the management account.
- Want a delegated platform team to operate: service-managed delegated admin may fit, but evaluate the broad scope of delegated administrator permissions.

## 3. AWS Organizations Trusted Access and Delegated Administrator

### 3.1. Trusted Access

Trusted access allows CloudFormation StackSets to integrate with AWS Organizations to deploy across accounts/OUs. It is the foundation of the service-managed permission model.

Before creating a service-managed StackSet:

- The Organization must be configured in AWS Organizations;
- Trusted access for CloudFormation StackSets must be enabled;
- The operator needs permissions to manage StackSets and target scope;
- Target accounts must be in a valid state to receive deployments;
- Required Regions must be enabled in target accounts.

Disabling trusted access disrupts service-managed StackSet operations. Do not alter trusted access during an active rollout without assessing impact.

### 3.2. Management Account and Delegated Administrator

The management account owns service-managed StackSets. A member account can be registered as a **delegated administrator** to operate StackSets without running every daily operation directly from the management account.

When a delegated administrator creates a StackSet, the StackSet is still created in the management account context. CLI commands run from a delegated admin must specify `--call-as DELEGATED_ADMIN`.

AWS allows up to **5 delegated administrator accounts** registered for StackSets in an Organization. A delegated administrator has broad permissions: it can deploy to any account in the Organization; the management account cannot restrict a delegated admin to only certain OUs or StackSet operation types through this delegated admin mechanism alone.

Therefore:

- Only register delegated admin on a protected platform account;
- Use appropriate IAM policies/SCPs and change approval workflows;
- Monitor CloudTrail for StackSet operations;
- Do not grant delegated admin rights to workload teams if they do not need Organization-wide deployment access.

### 3.3. Deployment Targets in Organizations

Service-managed StackSets can target:

- The entire Organization;
- One or more OUs;
- Specific accounts;
- Account sets selected using account filters combined with OU/account targets.

When targeting a parent OU, child OUs and accounts underneath are included as well. Understand the OU hierarchy before selecting a parent OU, as a broad target may include more workloads than expected.

### 3.4. Account Filters

When combining OU IDs and account IDs, `AccountFilterType` filters the account set:

| Filter type | Meaning |
|---|---|
| `NONE` | No account filtering applied |
| `INTERSECTION` | Select only accounts that both belong to target OUs and appear in the accounts list |
| `DIFFERENCE` | Select accounts in target OUs excluding those in the accounts list |
| `UNION` | Select accounts belonging to target OUs or appearing in the accounts list |

Example: target OU `ou-prod` while excluding an account undergoing migration using `DIFFERENCE`. Before deploying, verify the actual account set via Organizations and StackSet target configuration; do not infer targets solely from OU names.

**Note on auto-deployment:** StackSets do not apply account-level targeting filters to accounts added later. If auto-deployment is enabled, the StackSet may deploy to a new account in the Organization/OU even if the initial configuration had an account filter list. If this is undesirable, disable auto-deployment or align StackSets/OUs with the intended lifecycle.

### 3.5. Account Onboarding and Offboarding

With auto-deployment enabled, a new account joining a target OU automatically receives stack instances. When an account leaves a target OU, the StackSet either deletes or keeps the stack instances depending on `RetainStacksOnAccountRemoval`.

Auto-deployment is also triggered when an account moves between OUs. For instance, an account leaving the Development OU to enter the Production OU can have its Development-targeted StackSet instance deleted and a Production-targeted StackSet instance created.

The retain decision must follow ownership:

- Baselines owned by a central platform may need deletion when an account leaves scope;
- Resources holding data/workload ownership may need retaining and handover;
- Deleting a stack can delete resources if template/resource policies allow it.

Do not pick retain or delete merely for operational convenience; align with resource lifecycle and data retention.

## 4. Designing Shared Templates Across Accounts/Regions

### 4.1. The Template Is the Source of Truth

A StackSet uses a CloudFormation template. The template should:

- Declare resources clearly;
- Use Parameters for per-environment differences;
- Use pseudo parameters such as `AWS::AccountId`, `AWS::Region`, `AWS::Partition`;
- Avoid hardcoding account IDs and Regions in resource names/policies;
- Include required tags, outputs, and metadata;
- Use resource names that do not collide across accounts/Regions;
- Produce the same desired state when deployed repeatedly.

### 4.2. Regional Baseline Template Example

The following template creates an SSM Parameter in each targeted account/Region:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Regional baseline marker deployed by CloudFormation StackSets

Parameters:
  EnvironmentType:
    Type: String
    AllowedValues:
      - development
      - staging
      - production

Resources:
  RegionalEnvironmentParameter:
    Type: AWS::SSM::Parameter
    Properties:
      Name: !Sub /organization/${EnvironmentType}/deployment-context
      Type: String
      Value: !Sub 'account=${AWS::AccountId};region=${AWS::Region};partition=${AWS::Partition}'
      Description: Regional deployment context managed by StackSets
      Tags:
        ManagedBy: CloudFormationStackSets
        Environment: !Ref EnvironmentType

Outputs:
  ParameterName:
    Value: !Ref RegionalEnvironmentParameter
~~~

`AWS::AccountId` and `AWS::Region` resolve independently in each stack instance. Because SSM Parameter is a regional resource, each account/Region gets its own parameter. This is a training example; production requires appropriate namespaces, encryption, and ownership.

### 4.3. Shared Parameters and Parameter Overrides

A StackSet can accept shared parameters for instances. For specific stack instances, parameter overrides can customize per account/Region.

Examples:

- `EnvironmentType=production` for the production OU;
- Different `LogRetentionDays` based on compliance;
- Account-specific `VpcCidr`;
- Region-specific `KmsKeyArn`.

Do not embed secrets directly into templates or parameter values that could be exposed via CloudFormation APIs/events. Use dynamic references to Secrets Manager/SSM SecureString when appropriate and grant read permissions to the execution context.

Parameter overrides enable per-target customization but increase complexity; manage them via source control/manifests rather than unaudited manual edits.

With auto-deployment, parameter overrides apply only to accounts currently in target OUs and child OUs. Accounts added later use the StackSet's default values; do not rely on existing overrides to configure newly onboarded accounts.

### 4.4. Region and Partition Pseudo Parameters

Templates can use:

- `AWS::Region`: Region of the stack instance;
- `AWS::AccountId`: target deployment account;
- `AWS::Partition`: partition such as `aws`, `aws-cn`, `aws-us-gov`.

Do not assume every service/resource type exists in every Region or partition. Commercial, China, and GovCloud have separate endpoints, account boundaries, and service availability. StackSets are not a mechanism for deploying across arbitrary partitions.

### 4.5. IAM Capabilities

If a template creates IAM resources, `create-stack-set` may require `CAPABILITY_IAM` or `CAPABILITY_NAMED_IAM` depending on resource naming. Acknowledge capabilities only after reviewing the IAM permissions the template will create.

StackSets replicate permissions across many accounts. An overly broad policy in a template can widen the blast radius across the entire Organization; review IAM resources like production code.

## 5. Creating a StackSet with Service-Managed Permissions

### 5.1. General Workflow

1. Prepare the AWS Organization, OUs, and trusted access;
2. Select the management account or delegated administrator;
3. Review the template, parameters, IAM capabilities, and target scope;
4. Create the StackSet with `SERVICE_MANAGED`;
5. Create stack instances for OUs/accounts and Regions;
6. Monitor the operation until a terminal status;
7. Verify stack instances and resources in target accounts.

Creating a StackSet only creates the management definition; to deploy into selected OUs/Regions, you must create stack instances or enable auto-deployment for eligible accounts.

### 5.2. Creating the StackSet

AWS CLI example from the management account:

~~~bash
aws cloudformation create-stack-set \
  --stack-set-name organization-regional-baseline \
  --template-body file://regional-baseline.yaml \
  --permission-model SERVICE_MANAGED \
  --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false \
  --parameters ParameterKey=EnvironmentType,ParameterValue=production \
  --region ap-southeast-1
~~~

If invoking from a delegated administrator, add `--call-as DELEGATED_ADMIN`. If invoking from the management account, use the default `SELF`.

`--region ap-southeast-1` in this command specifies the Region where the StackSet API/definition is managed; it does not mean stack instances are deployed only in Singapore. Target Regions are specified when creating/updating stack instances.

`RetainStacksOnAccountRemoval=false` is an illustrative choice. Evaluate resource deletion behavior before using it in production.

### 5.3. Creating Stack Instances by OU and Regions

Create `operation-preferences.json`:

~~~json
{
  "RegionConcurrencyType": "SEQUENTIAL",
  "RegionOrder": [
    "ap-southeast-1",
    "ap-southeast-2"
  ],
  "FailureTolerancePercentage": 5,
  "MaxConcurrentPercentage": 10,
  "ConcurrencyMode": "STRICT_FAILURE_TOLERANCE"
}
~~~

Then create instances:

~~~bash
aws cloudformation create-stack-instances \
  --stack-set-name organization-regional-baseline \
  --deployment-targets OrganizationalUnitIds=ou-abcd-12345678 \
  --regions ap-southeast-1 ap-southeast-2 \
  --operation-preferences file://operation-preferences.json \
  --region ap-southeast-1
~~~

`ou-abcd-12345678` is a placeholder. Verify OU IDs and account membership before running. With a delegated administrator, add `--call-as DELEGATED_ADMIN`.

### 5.4. Deploying to Selected Accounts in an OU

To select only specific accounts within an OU, use account filters. Conceptual example:

~~~bash
aws cloudformation create-stack-instances \
  --stack-set-name organization-regional-baseline \
  --deployment-targets OrganizationalUnitIds=ou-abcd-12345678,Accounts=111122223333,444455556666,AccountFilterType=INTERSECTION \
  --regions ap-southeast-1 \
  --region ap-southeast-1
~~~

The example uses `INTERSECTION`: only accounts that are both in the OU and in the account list receive deployments. Check your AWS CLI version and corresponding shorthand/JSON syntax; for complex configurations, use a JSON file to avoid parsing errors.

## 6. Creating a StackSet with Self-Managed Permissions

### 6.1. Preparing Roles

Before calling CloudFormation:

- Administration role exists in the controlling account;
- Execution role exists in each target account;
- Administration role is allowed to assume the execution role;
- Execution role trust policy allows the exact administration role;
- Execution role has only the permissions required for resources in the template;
- Role names align with the StackSet configuration.

Use current AWS-provided setup templates/guides to establish trust relationships; do not guess principal ARNs or bypass external governance controls.

### 6.2. Creating a Self-Managed StackSet

Example:

~~~bash
aws cloudformation create-stack-set \
  --stack-set-name selected-account-baseline \
  --template-body file://regional-baseline.yaml \
  --permission-model SELF_MANAGED \
  --administration-role-arn arn:aws:iam::111122223333:role/StackSetAdministrationRole \
  --execution-role-name StackSetExecutionRole \
  --parameters ParameterKey=EnvironmentType,ParameterValue=staging \
  --region ap-southeast-1
~~~

Then deploy to account IDs:

~~~bash
aws cloudformation create-stack-instances \
  --stack-set-name selected-account-baseline \
  --accounts 444455556666 777788889999 \
  --regions ap-southeast-1 ap-southeast-2 \
  --region ap-southeast-1
~~~

In the self-managed model, StackSets do not automatically discover accounts via OUs. Target account lists and role provisioning are the organization's responsibility.

### 6.3. Checking Trust and Execution Permissions

AssumeRole errors are commonly caused by:

- Execution role missing in the target account;
- Trust policy not permitting the administration role to assume it;
- Administration role lacking `sts:AssumeRole`;
- Execution role missing CloudFormation resource permissions;
- SCP/permission boundary blocking the action;
- Role name in the StackSet mismatching.

Do not fix this by attaching `AdministratorAccess` to every execution role. Craft policies matching the resource types/actions the template actually needs.

## 7. Operation Preferences: Concurrency and Failure Tolerance

### 7.1. Region Concurrency

A StackSet can execute in two ways:

- `SEQUENTIAL`: completes one Region before moving to the next Region;
- `PARALLEL`: deploys across multiple Regions simultaneously.

Sequential fits controlled rollouts, such as deploying Singapore first, verifying, and then moving to Sydney. Parallel shortens execution time but increases concurrent blast radius.

With `SEQUENTIAL`, you can specify `RegionOrder` to control sequencing. Pick a first Region with an appropriate blast radius and strong observability; for per-account canaries, target a small separate account/OU first.

### 7.2. Failure Tolerance

Failure tolerance specifies the number or percentage of accounts per Region allowed to fail before CloudFormation stops deployment in that Region and halts progression to subsequent Regions.

You can choose:

- `FailureToleranceCount`;
- `FailureTolerancePercentage`.

Use only one of the two in a given configuration. When using a percentage, CloudFormation rounds down to the nearest integer. With a very small target set, 5% may round down to 0 accounts allowed to fail.

### 7.3. Maximum Concurrent Accounts

`MaxConcurrentCount` or `MaxConcurrentPercentage` sets the maximum account concurrency for the operation. Use only one of the two.

Actual concurrency may be lower due to throttling/service limits. Under `STRICT_FAILURE_TOLERANCE`, initial concurrency is capped at failure tolerance + 1 and decreases as failures occur to stay within failure tolerance. Under `SOFT_FAILURE_TOLERANCE`, concurrency is decoupled from failure tolerance and continues at the configured maximum despite failures.

### 7.4. Choosing ConcurrencyMode

| Mode | Behavior | When to consider |
|---|---|---|
| `STRICT_FAILURE_TOLERANCE` | Reduces concurrency when failures occur to respect failure tolerance | Cautious rollouts, critical baselines |
| `SOFT_FAILURE_TOLERANCE` | Keeps concurrency at the configured maximum despite failures | Rollouts needing throughput with separate controls |

The default is `STRICT_FAILURE_TOLERANCE`. Do not choose soft mode merely for speed without capacity, alarms, and operation-stopping procedures.

In soft mode, once failures exceed failure tolerance, the operation stops after deployments already in the concurrency queue complete. Consequently, the final count of failed instances can exceed the configured failure tolerance; account for this when sizing blast radius.

### 7.5. Operation Preferences Are Not Auto-Deployment Preferences

`StackSetOperationPreferences` apply to user-initiated operations such as create/update stack instances. These preferences **do not apply to AutoDeployment**. Auto-deployment settings are configured separately at the StackSet level.

If you need wave rollouts with canaries, do not rely on auto-deployment to replace an approval-gated pipeline. Target OUs in waves or control account onboarding via separate Organizations workflows.

### 7.6. Managed Execution

A StackSet can enable `ManagedExecution` to let non-conflicting operations run concurrently while queuing conflicting operations. When a StackSet has running or queued operations, new operations may be queued according to managed execution behavior.

Enable managed execution only when you understand operation ordering and conflict semantics. It does not mean two updates to the same stack instance run in parallel.

AWS recommends considering managed execution when using auto-deployment; this mechanism lets auto-deployment operations across multiple target accounts run concurrently within a StackSet, accelerating onboarding in large Organizations.

If a StackSet already has running or queued operations, CloudFormation queues new operations even if they do not conflict. You cannot change execution configuration while the StackSet still has running/queued operations.

## 8. Auto-Deployment with AWS Organizations

### 8.1. New Accounts Entering an OU

When auto-deployment is enabled on a service-managed StackSet, new accounts joining the target Organization/OU automatically receive stack instances. This is how baselines are applied during account onboarding.

Example:

- A new account is created in the `Workloads-Production` OU;
- A StackSet targets that OU with auto-deployment enabled;
- CloudFormation creates stack instances in the Regions configured for the StackSet;
- The baseline appears without an operator manually adding the account.

### 8.2. Accounts Leaving an OU

When an account leaves a target OU, the StackSet handles stack instances according to `RetainStacksOnAccountRemoval`:

- `false`: stack instances are deleted per auto-deployment behavior;
- `true`: stacks are retained in the account after it leaves the target scope.

Retaining stacks can leave resources no longer managed the same way by the central StackSet. Establish clear ownership handoff, tagging, and cleanup workflows.

When retain is chosen, stacks and resources remain in the target account, yet the stack is disassociated from the StackSet; afterward, the central StackSet no longer manages them as its stack instances.

### 8.3. Auto-Deployment Settings Are StackSet-Level

Auto-deployment settings apply at the StackSet level and cannot be configured per individual OU/account/Region within the same StackSet. If OUs have different lifecycles, split StackSets by policy/ownership.

### 8.4. Dependencies Between StackSets in Auto-Deployment

For service-managed StackSets, you can declare a list of StackSet ARNs that the current StackSet depends on in the `AutoDeployment.DependsOn` property. When auto-deployment triggers, CloudFormation orders execution so all dependencies succeed before starting the dependent StackSet's operation.

Current limits:

- Maximum 10 dependencies per StackSet;
- Maximum 100 dependencies per account;
- Dependencies are removed when a StackSet is deleted or Organizations is deactivated.

Example CLI configuration when updating auto-deployment:

~~~bash
aws cloudformation update-stack-set \
  --stack-set-name workload-baseline \
  --use-previous-template \
  --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false,DependsOn=NETWORK_BASELINE_STACKSET_ARN,SECURITY_BASELINE_STACKSET_ARN \
  --region ap-southeast-1
~~~

`NETWORK_BASELINE_STACKSET_ARN` and `SECURITY_BASELINE_STACKSET_ARN` are placeholders; replace them with actual StackSet ARNs in the same Organization/matching permission model.

This dependency mechanism is for **auto-deployment operations**. It does not replace pipelines/waves for manual updates or releases requiring separate approvals. For canary rollouts with health checks between stages, continue orchestrating via pipelines/workflows.

## 9. Region Strategy and Account Readiness

### 9.1. Selecting Regions Before Deploying

Each stack instance deploys resources in one account/Region. Before choosing Regions, determine:

- Where workloads need to run;
- Data residency/compliance requirements;
- Whether services/resource types are supported;
- Whether the Region is enabled in target accounts;
- Quotas and resource naming;
- Network/DNS/KMS dependencies;
- Deployment and operational costs.

A Region may be disabled by default in an account. Enable the Region for target accounts per AWS procedures before StackSets deploy there.

### 9.2. Uneven Region Availability

A template valid in Singapore can fail in Sydney if resource types, features, or quotas differ. Some services are global/account-level while others are regional. Do not assume every resource created once automatically appears globally.

Use conditions/parameters where genuine differences exist, while avoiding overcomplicating a single template for every partition and service combination.

### 9.3. RegionOrder and Rollout Waves

Example rollout:

~~~text
Wave 0: sandbox account, ap-southeast-1
Wave 1: development OU, ap-southeast-1
Wave 2: development OU, ap-southeast-2
Wave 3: staging OU, both Regions
Wave 4: production OU, ap-southeast-1
Wave 5: production OU, ap-southeast-2
~~~

Use target OUs/account filters to form waves; set sequential Region concurrency when you need to observe one Region at a time. Define clear success criteria before advancing to the next wave.

### 9.4. Cross-Account Resource References

ARNs, KMS keys, VPC IDs, and resource names can vary by account/Region. Use parameters, SSM parameters, or outputs/exports according to the architecture. Do not assume CloudFormation export/import automatically works across accounts/Regions as within a single stack.

When a template needs a resource from another account, explicitly define the sharing mechanism such as RAM, resource policies, role assumption, or deployment dependencies.

## 10. Monitoring StackSet Operations

### 10.1. Operations Are Asynchronous

Create/update/delete stack instance commands return an operation ID. Operations can take time because CloudFormation executes stack operations across multiple accounts/Regions.

Do not treat the CLI returning an operation ID as deployment success. Monitor until a terminal status and inspect individual stack instances.

### 10.2. Inspection Commands

~~~bash
aws cloudformation describe-stack-set \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1

aws cloudformation list-stack-instances \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1

aws cloudformation list-stack-set-operations \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1
~~~

To inspect a specific operation:

~~~bash
aws cloudformation describe-stack-set-operation \
  --stack-set-name organization-regional-baseline \
  --operation-id OPERATION_ID \
  --region ap-southeast-1
~~~

Replace `OPERATION_ID` with the ID returned by create/update commands. When using a delegated administrator, add `--call-as DELEGATED_ADMIN` to commands requiring call-as context.

### 10.3. Operation and Stack Instance Statuses

Track statuses such as `RUNNING`, `SUCCEEDED`, `FAILED`, `STOPPING`, `STOPPED`, `QUEUED` at the operation level and stack instance statuses such as `CURRENT`, `OUTDATED`, `INOPERABLE`, or corresponding failure states.

Do not read only the overall StackSet status. An operation can achieve partial success: many instances succeed while a few accounts/Regions fail. Inspect the status reason and stack events inside the failing account/Region.

### 10.4. Retrying Operations After Fixing Errors

When an operation fails:

1. Identify the failing account/Region/stack instance;
2. Open stack events and read the Status reason;
3. Classify whether it is a template error, IAM deny, quota, Region availability, or resource conflict;
4. Fix the template/role/target prerequisites;
5. Verify previously succeeded instances still match desired state;
6. Start a new operation with appropriate targets/concurrency;
7. Verify the entire target set.

Do not blindly run repeated batch retries without knowing the cause. Doing so increases throttling and obscures event history.

## 11. Drift Detection and Configuration Compliance

### 11.1. What Is Drift?

Drift occurs when actual resource configuration differs from the desired configuration in the CloudFormation template and parameters—for example, an operator edits a Security Group rule directly in the console.

StackSet drift detection runs drift detection across the stacks backing stack instances and aggregates statuses. It helps surface configurations modified outside IaC.

### 11.2. Running Drift Detection

Example:

~~~bash
aws cloudformation detect-stack-set-drift \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1
~~~

The command returns an operation ID; monitor it via `describe-stack-set-operation`. Drift detection can take time depending on the number of instances/resources, and only one drift detection operation can run on a StackSet at a time.

### 11.3. Limitations of Drift Detection

Drift detection:

- Only evaluates resource types/properties supported by CloudFormation drift detection;
- Requires permissions to read resource state;
- Does not replace AWS Config, Security Hub, or continuous compliance monitoring;
- Does not detect every change across every service;
- Only compares properties explicitly declared via templates/parameters; undeclared default properties may not be tracked;
- Modifying a stack instance directly via a CloudFormation stack operation, rather than through the StackSet, is not considered drift in StackSet drift detection;
- May have edge cases with relationships/attachments across resources or stacks.

Therefore, `IN_SYNC` is not absolute proof that every configuration in an account is compliant. Combine drift detection with AWS Config rules, CloudTrail, security monitoring, and policy-as-code.

### 11.4. Handling DRIFTED

When an instance has drifted:

1. Inspect resource drift details and expected/current property values;
2. Determine whether the change was intentional or out-of-process;
3. If the change is valid, update the template so desired state reflects the new decision;
4. If the change is unauthorized, review impact and restore the resource to template state;
5. Re-run update/drift detection;
6. Record audit details and update processes to prevent recurrence.

Do not update a StackSet blindly before understanding resource drift; CloudFormation could overwrite manual mitigations and cause disruption.

## 12. Updates, Rollbacks, and Change Management

### 12.1. Updating Templates and Instances

When the template changes:

- Review the diff and resource replacement risks;
- Verify parameter changes;
- Identify target accounts/Regions;
- Choose operation preferences;
- Deploy via canaries/waves;
- Monitor each stack instance;
- Verify resource state and application health.

A StackSet update can impact hundreds of stacks. Never use a production-wide update as the first test.

### 12.2. A StackSet Operation Is Not an Organization-Wide Transaction

An operation may succeed in some accounts/Regions and fail in others. CloudFormation does not guarantee an atomic rollback of the entire matrix to its prior state.

An individual stack instance may roll back resources within that stack per CloudFormation semantics, while instances that already succeeded in other accounts may remain on the new version. You must manage partial rollouts and decide whether to continue, fix and retry, or deploy a reviewed reverse update.

### 12.3. Rollback Strategy

Before a rollout, prepare:

- Previous template version;
- Parameter values/overrides;
- Target account/Region list;
- Operation ID and status snapshot;
- Template-level change set/diff review if your workflow includes it;
- Rollback/forward-fix criteria;
- Owner and maintenance window.

A rollback may mean updating the StackSet back to the old template version, yet resource updates do not always reverse data or external side effects. Database migrations, data deletions, and IAM trust changes require separate plans.

### 12.4. RetainStacksOnAccountRemoval Is Not Deletion Protection

`RetainStacksOnAccountRemoval` governs auto-deployment when an account leaves target scope. It does not replace CloudFormation stack termination protection or resource-specific deletion policies.

Use `DeletionPolicy: Retain` on resources needing data preserved when stacks are deleted, and review resource lifecycles. Clearly distinguish retaining a stack instance from retaining a resource during stack deletion.

### 12.5. Import and Migration

If accounts already have manually created resources or resources from standalone stacks, do not assume a StackSet will automatically adopt them. Evaluate CloudFormation resource import, StackSet import capabilities, and resource type support.

Before importing, reconcile logical IDs, physical IDs, template ownership, stack status, and drift. Do not create a duplicate resource with the same name merely because the StackSet does not yet manage the old resource.

## 13. Security Guardrails and Governance

### 13.1. Least Privilege for Operators

Operator/CI roles need appropriate CloudFormation StackSets permissions for actions such as create/update/delete/list/describe/detect drift, plus Organizations or role assumption permissions required by the permission model.

Restrict by:

- StackSet names/ARNs and allowed Regions;
- Allowed resource types in templates;
- Target OUs/accounts;
- IAM capabilities;
- Role ARN and execution role name;
- Change approval for production OUs.

### 13.2. Execution Permissions

With self-managed permissions, the execution role can create any resources allowed by its policy. With service-managed permissions, service-linked roles and permissions are managed through Organizations integration, yet operator permissions still govern who can initiate deployments.

Do not confuse permission to invoke CloudFormation with the permissions CloudFormation needs to create resources. Check operator policies, execution/service-linked roles, resource policies, and SCPs.

### 13.3. SCPs and Permission Boundaries

An SCP can block a resource action even when the StackSet template and execution role allow it. For example, an SCP blocks creating public S3 buckets or disabling CloudTrail. Before a rollout, check the guardrails on the target OU.

Do not disable an SCP merely to make a deployment succeed. Fix the template or policy according to approved security architecture.

### 13.4. Secrets and Encryption

- Never hardcode secret values in templates;
- Use Secrets Manager/SSM SecureString dynamic references when appropriate;
- Control KMS key policies per account/Region;
- Never log sensitive parameter values;
- Encrypt artifacts/templates in S3 if they contain sensitive data;
- Restrict read access to template artifacts and operation logs.

### 13.5. Audit

CloudTrail records API calls related to CloudFormation/Organizations. Record:

- Who initiated the operation;
- StackSet name and operation ID;
- Template version/hash;
- Target OUs/accounts and Regions;
- Parameter overrides;
- Operation preferences;
- Results, failed instances, and remediation.

Include change ticket/release IDs in tags, descriptions, or deployment metadata for change traceability.

## 14. Troubleshooting

### 14.1. Trusted Access or Organizations Errors

Verify whether trusted access is enabled, whether the operator is using the management account or delegated admin, whether `--call-as` is right, and whether target accounts belong to the Organization.

If the delegated admin is unregistered or the wrong call-as context is passed, the API will reject the call. Do not pass `SELF` from a delegated account for a service-managed operation when the API requires `DELEGATED_ADMIN`.

### 14.2. Incorrect Account/OU Targets

Verify OU IDs, parent/child hierarchy, account membership, and `AccountFilterType`. With account filters, verify the resulting intersection/difference/union set before deploying.

Be especially careful when targeting a parent OU: child OUs can be included.

### 14.3. Disabled Region or Unsupported Resource

If a Region is disabled by default in a target account, enable the Region first. Check resource type/service availability, quotas, KMS keys, and dependencies in that Region.

Listing a Region in `--regions` does not guarantee every resource in the template is supported there.

### 14.4. AssumeRole / AccessDenied

For self-managed:

- Is the administration role ARN correct?
- Does the execution role exist in every target account?
- Does the trust policy specify the right principal?
- Is `sts:AssumeRole` allowed?
- Does the execution role have resource permissions?

For service-managed, check trusted access/service-linked roles and operator permissions. Both models can be blocked by SCPs/permission boundaries/resource policies.

### 14.5. Resource Creation Failed

Open stack events in the failing account/Region to find the resource logical ID and Status reason. Check duplicate names, quotas, dependencies, immutable property replacements, IAM capabilities, and Region-specific limitations.

The StackSet operation status usually only shows the high-level summary; stack events reveal the detailed cause of the resource failure.

### 14.6. Operation Running Long or Queued

Inspect operation history, number of target instances, Region concurrency, max concurrent accounts, and service throttling. Managed execution may queue conflicting operations. Do not submit additional concurrent updates expecting them to run faster.

### 14.7. Stack Instance OUTDATED or INOPERABLE

`OUTDATED` typically indicates the stack instance does not match the current template/version or a previous operation did not finish. `INOPERABLE` can indicate the instance is in a state where normal operations cannot proceed.

Inspect stack events, status reasons, and stack status. Fix the root cause and run the appropriate update/retry; if a stack requires manual repair, document the change and run drift detection afterward.

## 15. Case Study: Deploying a Regional Baseline for an Organization

### 15.1. Context

An organization has:

- Management account;
- Platform delegated administrator account;
- OUs `Sandbox`, `Development`, `Production`;
- Workload accounts in Singapore and Sydney;
- Baseline requiring one SSM Parameter per account/Region for applications to read deployment context.

Requirements:

1. New accounts entering an OU receive the baseline automatically;
2. Development rolls out before Production;
3. Singapore deploys before Sydney;
4. Do not deploy to the management account;
5. Support retaining stacks when an account leaves an OU per policy;
6. Monitor operations and drift.

### 15.2. Design

- Use service-managed permissions;
- Enable trusted access for CloudFormation StackSets;
- Register the platform account as delegated administrator;
- Create the StackSet in the management account context via the delegated admin;
- Target individual OUs across rollout waves;
- Choose `SEQUENTIAL` Region concurrency;
- Start with `STRICT_FAILURE_TOLERANCE`;
- Enable auto-deployment for OUs with automatic onboarding;
- Set `RetainStacksOnAccountRemoval` per ownership policy;
- Use CloudWatch/CloudTrail and runbooks for monitoring.

### 15.3. Rollout Plan

~~~text
Preflight:
  - Validate template
  - Confirm trusted access and delegated admin
  - Confirm target OU/account membership
  - Enable required Regions
  - Confirm service quotas and IAM/SCP

Wave 1:
  - Sandbox OU
  - ap-southeast-1
  - Validate SSM parameter and stack events

Wave 2:
  - Development OU
  - ap-southeast-1, then ap-southeast-2
  - Verify drift and application consumption

Wave 3:
  - Production OU
  - Canary accounts first
  - Review operation status and health signals

Steady state:
  - Auto-deploy new accounts
  - Periodic drift detection
  - Review operation history and failed instances
~~~

### 15.4. Success Criteria

- All target accounts/Regions have stack instances in `CURRENT`;
- Stack operations complete with `SUCCEEDED`;
- SSM parameter values reflect accurate account/Region values;
- No unexpected resource replacements;
- Drift detection reports no unhandled drift;
- CloudTrail captures actor/operation ID for auditing;
- Onboarding accounts receive the baseline per auto-deployment policy;
- Offboarding accounts retain/delete stacks per recorded decision.

## 16. Self-Check Questions

1. How do Stack, StackSet, and stack instance differ?
2. How many account/Region combinations can a StackSet deploy to by design?
3. Which AWS service do service-managed permissions rely on?
4. Which roles do self-managed permissions require?
5. Why do service-managed StackSets not target the management account?
6. Where is a delegated administrator registered and what is its permission scope?
7. When is `--call-as DELEGATED_ADMIN` used?
8. Does targeting a parent OU include child OUs?
9. How do `INTERSECTION`, `DIFFERENCE`, and `UNION` differ?
10. How does auto-deployment handle new accounts entering an OU?
11. What does `RetainStacksOnAccountRemoval` control?
12. Why does `OperationPreferences` not control auto-deployment?
13. How do `SEQUENTIAL` and `PARALLEL` Region concurrency differ?
14. How does `STRICT_FAILURE_TOLERANCE` reduce concurrency?
15. Why can a failure tolerance percentage round down to zero?
16. Does creating a StackSet automatically deploy stack instances?
17. Why can an operation achieve partial success?
18. Does drift detection catch every change outside CloudFormation?
19. Why are `AWS::Region` and `AWS::AccountId` useful in StackSet templates?
20. Why should you not hardcode a KMS key ARN or account ID in a shared template?
21. How does a disabled-by-default Region affect deployment?
22. Do StackSets guarantee atomic Organization-wide rollback?
23. Why does the service-managed model not support nested stacks/macros/transforms?
24. When are self-managed permissions needed?
25. What data must be recorded in a deployment audit?

## 17. Suggested Answers

1. A Stack is a set of resources; a StackSet is the definition managing multiple stacks; a stack instance is a stack in a single account/Region.
2. Depends on target account count, Regions, service quotas, and design; check current quotas.
3. AWS Organizations trusted access.
4. Administration role and execution roles in target accounts.
5. It is a limitation of the service-managed permission model; use self-managed if deploying to the management account.
6. Registered in AWS Organizations; delegated admin has broad deployment permissions across accounts in the Organization.
7. When invoking service-managed StackSets from a delegated administrator account.
8. Yes; targeting a parent OU includes child OUs/accounts.
9. Intersection is the overlap; Difference excludes accounts in the list; Union is the combined set.
10. Auto-deployment creates stack instances when an account enters the target scope.
11. Whether to retain or delete stack instances when an account leaves the target OU/scope.
12. Auto-deployment has its own settings; StackSetOperationPreferences do not apply to auto-deployment.
13. Sequential processes one Region at a time; Parallel runs multiple Regions concurrently.
14. Decreases actual concurrency when failures occur to stay within failure tolerance.
15. CloudFormation rounds down to an integer number of accounts.
16. No; you need `create-stack-instances` or auto-deployment.
17. Some instances can succeed while certain accounts/Regions fail.
18. No; only resource types/properties supported by drift detection.
19. They resolve individually per stack instance.
20. Each account/Region has distinct resources/ARNs; use pseudo parameters and parameters.
21. Stack instance deployment fails until the Region is enabled.
22. No; operations can have partial success and require remediation/forward-fix.
23. It is a limitation of service-managed StackSets.
24. When target accounts are outside an Organization or custom role deployment management is needed.
25. Actor, StackSet, template version/hash, targets, Regions, parameters, operation ID, preferences, and results.

## 18. Production Deployment Checklist

### Governance and Permissions

- [ ] Chose service-managed or self-managed based on account governance.
- [ ] Trusted access enabled and verified when using service-managed.
- [ ] Delegated administrator registered on the right account and secured.
- [ ] Understood that service-managed StackSets do not deploy to the management account.
- [ ] Self-managed administration/execution roles have least-privilege trust and permissions.
- [ ] Operator roles, SCPs, and permission boundaries reviewed.
- [ ] Target OU/account IDs verified.

### Template and Deployment

- [ ] Template validated, diff reviewed, and stored in version control.
- [ ] Parameters/overrides have manifests and audits.
- [ ] Pseudo parameters used for account/Region/partition.
- [ ] Resource types supported across all target Regions.
- [ ] Required Regions enabled in target accounts.
- [ ] `RegionOrder`, concurrency, and failure tolerance match rollout risk.
- [ ] Auto-deployment/retain behavior decided.
- [ ] Dependencies between StackSets coordinated via waves/pipelines.
- [ ] IAM capabilities and resource replacement risks reviewed.

### Operations and Security

- [ ] Operation IDs monitored to terminal status.
- [ ] Stack instances and stack events checked, not just StackSet summaries.
- [ ] Procedures exist for handling partial success/`OUTDATED`/`INOPERABLE`.
- [ ] Drift detection combined with AWS Config/CloudTrail and compliance monitoring.
- [ ] Secrets absent from plaintext templates/parameters/logs.
- [ ] KMS/resource policies checked per account/Region.
- [ ] CloudTrail audit logs actor, target, template version, and operation ID.
- [ ] Rollback/forward-fix, canary, runbooks, and owners in place.
- [ ] Procedures exist to redrive/retry operations after fixing root causes.
- [ ] No assumption that a StackSet operation is an atomic Organization-wide transaction.

**Expected outcome:** you can design and operate CloudFormation StackSets across multiple accounts and Regions, choose the right permission model, target the right OUs, coordinate safe rollouts, monitor partial failures, and detect drift in a centralized IaC model.

## Official AWS Documentation

- [CloudFormation StackSets concepts](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-concepts.html)
- [Prerequisites for using CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs.html)
- [Create StackSets with service-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-associate-stackset-with-org.html)
- [Activate trusted access for StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html)
- [Register a delegated administrator](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-delegated-admin.html)
- [Create StackSets with self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-getting-started-create-self-managed.html)
- [Add stacks to StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stackinstances-create.html)
- [Enable or disable automatic deployments](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-manage-auto-deployment.html)
- [StackSet AutoDeployment properties and dependencies](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-cloudformation-stackset-autodeployment.html)
- [StackSet operation options](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-operate.html)
- [Choose the concurrency mode](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/concurrency-mode.html)
- [StackSetOperationPreferences API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_StackSetOperationPreferences.html)
- [Managed execution for StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-concepts.html)
- [Performing drift detection on StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-drift.html)
- [Troubleshooting StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-troubleshooting.html)
- [AWS::CloudFormation::StackSet resource reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudformation-stackset.html)
- [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html)
- [AWS Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_introduction.html)

> **Application note:** OU IDs, account IDs, role ARNs, Regions, resource names, and parameters in this lesson are training examples. Before deploying, verify target membership, trusted access, permissions, Region availability, quotas, and resource replacement behavior. StackSets can modify resources in bulk across many accounts; test in a sandbox, use canaries/waves, and keep complete audit records.
