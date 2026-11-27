# Drift Detection, Resource Import, and Managing Out-of-Band Changes

Infrastructure as Code (IaC) describes desired infrastructure in files that can be reviewed, version-controlled, and deployed repeatably. Yet AWS infrastructure can still be modified outside the IaC workflow: an engineer edits a Security Group in the Console to resolve an incident, an automation script updates a configuration, a service alters a managed property on its own, or a team creates a new resource directly via the CLI. When actual configuration no longer matches code, the system exhibits **configuration drift**.

Drift detection identifies discrepancies between IaC-managed configuration and actual state. Resource import brings existing resources under IaC management. Out-of-band change management establishes a process to record, evaluate, approve, revert, or codify intentional changes back into the source of truth.

This lesson belongs to the **Infrastructure as Code** chapter, **CLOUD_PROVIDERS_AWS** module. It connects Regions/AZs, IAM, VPC, compute, storage, databases, messaging, and serverless toward building infrastructure that is secure, observable, recoverable, and cost-controlled. Examples use AWS CloudFormation and Terraform to illustrate general concepts; import/drift limitations depend on resource type, provider version, and tooling.

> **Operational principle:** Before fixing drift, identify the resource owner, source of truth, impact, and reason for the change. Only one IaC system should own a resource's lifecycle at any given time. An apply command can modify or delete live running resources; always read the plan/change set before executing.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain configuration drift and distinguish drift from unmanaged resources.
2. Distinguish desired configuration, actual configuration, IaC state, and resource ownership.
3. Describe how CloudFormation drift detection compares a template with an AWS resource.
4. Understand `IN_SYNC`, `DRIFTED`, `NOT_CHECKED` statuses and detection operation states.
5. Recognize coverage limits: resource types, properties, default values, nested stacks, and attachment relationships.
6. Detect drift in Terraform using `plan`, `plan -refresh-only`, and HCP Terraform health assessments.
7. Distinguish refreshing state from modifying live infrastructure.
8. Import existing resources into a CloudFormation stack or Terraform state/configuration.
9. Build an inventory and identify resource identifiers, dependencies, and ownership before importing.
10. Avoid managing the same resource with multiple stacks/workspaces.
11. Choose remediation: codify changes, revert to desired state, import, or separate ownership.
12. Manage emergency changes via break-glass, audit trails, approvals, and reconciliation.
13. Protect Terraform state, state locking, backups, and CloudFormation change sets.
14. Build CI/CD drift checks, AWS Config/CloudTrail signals, and operational alerts.
15. Practice detecting, importing, and resolving drift in a safe sandbox.

## 2. What Is Configuration Drift?

**Configuration drift** occurs when a resource's actual properties differ from the configuration desired or recorded by IaC. Examples:

- A template defines a Security Group opening only TCP 443, yet an engineer adds a TCP 22 rule from the Internet.
- Terraform declares an RDS instance with deletion protection, yet the Console disables that setting.
- A CloudFormation template defines an S3 bucket with versioning enabled, yet the actual configuration is changed.
- Automation alters the desired capacity of an Auto Scaling Group outside the IaC workflow.
- A resource was created via the Console and is not yet in any state/template: this is an **unmanaged resource**, not necessarily drift of a specific stack/workspace.

### 2.1. Three States to Distinguish

| Concept | Meaning | Example |
|---|---|---|
| Desired configuration | Configuration requested by IaC code | `min_size = 2` |
| Recorded state | Information IaC stores about managed resources | Terraform state records instance ID and most recently refreshed attributes |
| Actual configuration | Configuration currently existing in AWS | ASG currently has `min_size = 4` |

Drift can exist between desired and actual, or between recorded state and actual. Tools detect this differently: CloudFormation compares actual against managed properties in the template; Terraform refreshes provider state and compares it against configuration to build a plan.

### 2.2. Security Group Drift Example

~~~mermaid
flowchart LR
    CODE["IaC desired state<br/>TCP 443 from approved CIDR"] --> EXPECTED["Expected configuration"]
    CONSOLE["Console / CLI / automation<br/>adds TCP 22 from 0.0.0.0/0"] --> ACTUAL["Actual Security Group"]
    EXPECTED --> COMPARE["Drift detection / plan"]
    ACTUAL --> COMPARE
    COMPARE --> RESULT["Drift found"]
    RESULT --> DECIDE{"Review intent and impact"}
    DECIDE -->|"Approved change"| UPDATE["Update IaC code"]
    DECIDE -->|"Unauthorized / temporary"| REVERT["Restore approved configuration"]
~~~

### 2.3. Why Is Drift Dangerous?

- **Security:** widened rules, disabled encryption, enabled public access, or relaxed IAM permissions.
- **Availability:** modified subnet routes, load balancer listeners, scaling, or database parameters.
- **Data protection:** altered retention, backups, deletion protection, versioning, or KMS key policies.
- **Cost:** unexpected increases in instance sizes, NAT Gateways, logging, storage classes, or provisioned capacity.
- **Deployment failure:** the next apply may overwrite operational changes, modify resources, or trigger replacement.
- **Audit/compliance:** code in Git no longer reflects the live running configuration.

Drift detection does not fix resources on its own. It provides evidence so operators can decide on remediation.

## 3. How Drift, Import, and Unmanaged Resources Differ

| Scenario | Resource in IaC state/stack? | Actual differs from desired? | Primary action |
|---|---:|---:|---|
| Drifted managed resource | Yes | Yes | Detect, review, and reconcile |
| In-sync managed resource | Yes | No (within tool's check scope) | Continue normal management |
| Unmanaged resource | No | No corresponding desired state | Inventory, import, or assign another owner |
| Orphan resource | No valid owner left | Unknown | Trace owner, dependencies, retention before handling |
| Intentional out-of-band change | Possibly | Possibly | Approve, codify, or roll back |
| Unsupported property/resource | Yes | Inconclusive | Add other checks; do not treat `NOT_CHECKED` as in-sync |

**Import is not a universal remediation for all drift.** Import is used when a resource already exists but is not yet managed by a stack/state. If the resource is already inside a CloudFormation stack or Terraform state, you typically update either the template/configuration or the actual resource so both converge.

### 3.1. A Resource Should Have Only One IaC Owner

An EC2 instance or Security Group should not have its lifecycle managed simultaneously by:

- CloudFormation stack A,
- Terraform workspace B,
- a CDK stack,
- and a pipeline script calling AWS APIs directly.

Multiple tools may read or reference the same resource, yet only one owner should be responsible for create/update/delete. If two systems manage it concurrently, one pipeline can undo the other's changes or delete a resource the other still assumes exists.

### 3.2. Distinguishing Shared Dependencies from Shared Ownership

A network stack can own VPCs/subnets while an application stack references subnet IDs via exports/outputs/data sources. The application stack using a VPC does not mean it owns the VPC's lifecycle. Designing clear ownership boundaries upfront reduces drift and prevents overlapping imports.

## 4. General Drift Management Workflow

~~~mermaid
flowchart TD
    A["Schedule / alert / incident"] --> B["Discover affected resource"]
    B --> C["Identify IaC owner and last change"]
    C --> D["Detect and collect expected vs actual"]
    D --> E{"Resource supported and result reliable?"}
    E -->|"No"| F["Use AWS Config / API / audit checks"]
    E -->|"Yes"| G["Assess security, availability, data and cost impact"]
    F --> G
    G --> H{"Why did it change?"}
    H -->|"Approved permanent change"| I["Update IaC code"]
    H -->|"Emergency / temporary"| J["Record exception and expiry"]
    H -->|"Unauthorized / accidental"| K["Restore desired state"]
    H -->|"Unmanaged resource"| L["Inventory and import decision"]
    I --> M["Plan / change set review"]
    J --> M
    K --> M
    L --> M
    M --> N["Apply through approved workflow"]
    N --> O["Re-detect / verify / close audit"]
~~~

Required steps:

1. **Discover:** find the resource, account, Region, stack/workspace, and business owner.
2. **Identify source of truth:** confirm the repository, module, state backend, and resource address/logical ID.
3. **Detect:** run drift detection or a refresh-only plan and record the timestamp.
4. **Investigate:** cross-check CloudTrail, AWS Config, incident tickets, change requests, and the actor.
5. **Classify:** intentional change, emergency, accidental, service-managed, or unmanaged resource.
6. **Choose remediation:** codify, revert, import, separate ownership, or create a time-bound exception.
7. **Review:** inspect the plan/change set and replacement/deletion impact.
8. **Apply:** execute through a workflow with approval, state locking, and audit.
9. **Verify:** re-run detection, check health/metrics, and close the incident/change record.


## 5. AWS CloudFormation Drift Detection

CloudFormation can detect drift across an entire stack or per individual resource. The tool compares **actual property values** with expected values in the template and stack parameters. If a resource has a differing property, it is marked `MODIFIED`; if the resource was deleted outside CloudFormation, its status can be `DELETED`.

### 5.1. Drift Statuses

| Scope | Status | Meaning |
|---|---|---|
| Stack | `IN_SYNC` | Supported and checked resources match expected properties |
| Stack | `DRIFTED` | At least one resource has drifted |
| Stack | `NOT_CHECKED` | No drift check result yet |
| Resource | `IN_SYNC` | Supported and checked properties match expected values |
| Resource | `MODIFIED` | One or more resource properties differ from expected |
| Resource | `DELETED` | Resource was deleted outside the stack |
| Resource | `NOT_CHECKED` | Resource has not been checked or lacks appropriate coverage |
| Detection operation | `DETECTION_IN_PROGRESS` | Detection operation is running |
| Detection operation | `DETECTION_COMPLETE` | Detection finished for supported resources |
| Detection operation | `DETECTION_FAILED` | Detection failed for at least one resource |

`IN_SYNC` only means properties supported and checked by CloudFormation match. It **does not prove every property of every resource in the stack matches**; a stack containing no drift-supported resources can also carry this status.

### 5.2. What CloudFormation Can and Cannot Detect

CloudFormation drift detection has important limitations:

- Only checks resource types that support drift detection.
- Only checks resource properties explicitly declared in the template or passed via stack parameters. Default values omitted from the template are not tracked.
- Some properties cannot be compared accurately because service APIs do not return corresponding values, such as certain code contents or indirectly represented settings.
- Certain attachment relationships between resource types can make results hard to interpret, especially when the attachment resides in another stack.
- Drift detection on a parent stack does not automatically run on nested stacks; it must be run directly on nested stacks.
- In some cases, services return default values or normalize properties, requiring human review of results.

Before relying on detection as a mandatory control, check AWS's resource type/property support list for your Region and resources. When results show `NOT_CHECKED`, supplement with AWS Config rules, service API checks, or policy-as-code.

### 5.3. Running Drift Detection via AWS CLI

~~~bash
# Start drift detection for the entire stack.
aws cloudformation detect-stack-drift \
  --stack-name production-network

# The command above returns a StackDriftDetectionId.
# Use that ID to monitor the operation.
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id d1b2c3d4-0000-1111-2222-example

# List drift details for resources in the stack.
aws cloudformation describe-stack-resource-drifts \
  --stack-name production-network
~~~

This is a configuration-read/detection operation and does not modify resources. Running detection can take several minutes depending on resource count. Do not launch overlapping operations on the same stack; check the `Last drift check` timestamp to avoid relying on stale results.

### 5.4. Detecting a Specific Resource

~~~bash
aws cloudformation detect-stack-resource-drift \
  --stack-name production-network \
  --logical-resource-id PublicWebSecurityGroup
~~~

Useful right after resolving an incident or verifying a resource post-remediation. The output includes expected/current property values and difference types when supported by the service/resource.

### 5.5. Required IAM Permissions

The principal running drift detection needs appropriate CloudFormation permissions such as `cloudformation:DetectStackDrift`, `cloudformation:DetectStackResourceDrift`, plus read/describe permissions for the resource types being checked (e.g., EC2 Describe APIs). Some resource types also require CloudFormation registry/type configuration read permissions. Missing permissions can cause detection to fail or skip resources.

### 5.6. Example Interpreting Results

Suppose a template declares:

~~~yaml
Resources:
  WebSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: HTTPS ingress only
      VpcId: vpc-0123456789abcdef0
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 203.0.113.0/24
~~~

If the Console adds an SSH TCP 22 rule from `0.0.0.0/0`, drift details will show differing property list entries. Before reverting, check incident/change records: an engineer may have added the rule for incident mitigation and forgotten to roll it back. If the rule is unapproved, update the template/stack to the approved secure configuration and verify the actual rule disappears after the update.

## 6. Importing Existing Resources into CloudFormation

Resource import is used when an AWS resource already exists but is not yet managed by the target CloudFormation stack. Import lets the stack adopt ownership of the resource without deleting and recreating it. Not all resource types support import; check the resource identifier and support matrix before creating a change set.

### 6.1. Preparation Before Import

1. Inventory the resource: account, Region, ARN/physical ID, tags, dependencies, and business owner.
2. Confirm the resource does not belong to another CloudFormation stack in the same Region.
3. Verify the resource type supports import and identify the identifier property.
4. Gather the actual configuration from AWS API/Console/Config.
5. Write a template with a new resource logical ID or the exact target logical ID; properties must reflect actual configuration.
6. Set `DeletionPolicy` on the imported resource. `Retain` is usually the prudent choice when adopting resources with data; the final policy choice must fit the lifecycle.
7. Create an `IMPORT` change set, review carefully, and then execute.
8. After import succeeds, run drift detection and adjust the template to match actual state.

**An import operation is not a normal stack update.** Within the same import operation, CloudFormation does not allow creating new resources, deleting other resources, or modifying resource configuration properties. Import first; then create a separate update change set for desired changes.

### 6.2. Example Importing an S3 Bucket

Suppose the `audit-storage` stack already exists, while bucket `company-audit-logs-prod` was created manually, currently holds data, and belongs to no stack. A minimal template must declare the resource and an appropriate policy:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Adopt an existing audit bucket into CloudFormation

Resources:
  AuditLogsBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    Properties:
      BucketName: company-audit-logs-prod
      VersioningConfiguration:
        Status: Enabled
~~~

The example above only illustrates structure. Before importing, the template must match the actual properties CloudFormation will manage; do not assume versioning is enabled on the bucket without verifying.

Create `resources-to-import.json`:

~~~json
[
  {
    "ResourceType": "AWS::S3::Bucket",
    "LogicalResourceId": "AuditLogsBucket",
    "ResourceIdentifier": {
      "BucketName": "company-audit-logs-prod"
    }
  }
]
~~~

Create the import change set:

~~~bash
aws cloudformation create-change-set \
  --stack-name audit-storage \
  --change-set-name adopt-audit-bucket \
  --change-set-type IMPORT \
  --template-body file://template.yaml \
  --resources-to-import file://resources-to-import.json
~~~

Review the change set before executing:

~~~bash
aws cloudformation describe-change-set \
  --stack-name audit-storage \
  --change-set-name adopt-audit-bucket

aws cloudformation execute-change-set \
  --stack-name audit-storage \
  --change-set-name adopt-audit-bucket
~~~

If the template includes IAM resources requiring a capability, pass the corresponding capability after reviewing IAM creation/update permissions. Monitor stack events until the import operation completes (`IMPORT_COMPLETE`) or rolls back/fails.

### 6.3. Post-Import Verification

~~~bash
aws cloudformation detect-stack-drift \
  --stack-name audit-storage

aws cloudformation describe-stack-resource-drifts \
  --stack-name audit-storage
~~~

If the newly imported resource shows `MODIFIED`, the template does not accurately describe the actual configuration for the checked properties. Fix the template to reflect actual state first, or plan a post-import resource update. Never run a blind update that could cause data loss or alter security posture.

### 6.4. Importing Multiple Resources and Auto-Import

CloudFormation can import multiple resources in a single operation if all resource types/identifiers meet requirements. Certain named resources also support auto-import during stack creation or updates. Auto-import does not eliminate review: verify identifier uniqueness, templates, stack ownership, and post-import drift.

### 6.5. Limitations to Remember

- The resource type must support import in the current Region.
- Every imported resource requires a `DeletionPolicy`.
- Do not import the same resource into multiple stacks in the same Region.
- Import does not automatically discover and write a complete template for every attribute; an IaC generator can be used as a starting point if the resource type is supported, but it must be reviewed.
- Stack quotas and resource identifier formats still apply.
- Import does not automatically transfer ownership of related resources; dependencies/attachments must be evaluated separately.


## 7. Terraform Drift Detection and Refresh-Only Mode

Terraform uses a different mechanism from CloudFormation. During a normal `terraform plan`, Terraform refreshes managed resources by calling the provider to read actual state, updates state **in memory**, and compares it against configuration to produce an execution plan. If resources were modified outside Terraform, the plan may display a notice such as `Objects have changed outside of Terraform` and propose actions needed to bring actual infrastructure back to configuration.

### 7.1. Normal Plan Detects Drift

~~~bash
terraform init
terraform plan
~~~

Example: Terraform state previously recorded a Security Group with TCP 443 ingress. An engineer adds TCP 22 ingress via the Console. A normal plan refreshes current state and compares against HCL; if HCL still allows only 443, the plan may propose deleting the TCP 22 rule.

A plan only presents proposed changes; **`terraform plan` does not execute changes on AWS**. Never skip the `Plan:` summary or resource actions during review.

### 7.2. Refresh-Only Plan

~~~bash
terraform plan -refresh-only
~~~

Refresh-only mode creates a plan aimed at updating Terraform state and root module outputs to match real changes outside Terraform. It lets you review state changes before writing them.

If you decide to accept the current actual configuration into state:

~~~bash
terraform apply -refresh-only
~~~

That command updates state/outputs; it **does not modify resources in AWS**. However, HCL still holds the old desired configuration. Therefore, the next normal plan may propose altering actual infrastructure to match HCL. If the out-of-band change is permanent and approved, update HCL before/after refreshing through the review workflow so the source of truth reflects the decision.

### 7.3. Do Not Confuse Refresh-Only with Remediation

| Command/Mode | State | Actual infrastructure | Purpose |
|---|---|---|---|
| `terraform plan` | Refreshed in memory | Unchanged | Detect drift and preview reconciliation |
| `terraform plan -refresh-only` | Computes state updates, not saved | Unchanged | Review state changes |
| `terraform apply -refresh-only` | Writes state to match actual | Unchanged | Accept actual state into state file |
| `terraform apply` normal mode | Writes state after apply | May change | Bring resources to match HCL |
| `terraform plan -refresh=false` | Skips refresh | Unchanged | Special mode; may miss drift |

Do not use `-refresh=false` as a way to "get a clean plan." It can cause Terraform to ignore out-of-band changes and generate an incomplete execution plan. `terraform refresh` is a legacy deprecated command; prefer refresh-only mode to review before writing state.

### 7.4. Reading Drift in a Plan

Suppose a plan snippet looks like:

~~~text
Note: Objects have changed outside of Terraform

  # aws_security_group.web has changed
  ~ resource "aws_security_group" "web" {
        id = "sg-0123456789abcdef0"
      ~ ingress = [
          + {
              from_port   = 22
              to_port     = 22
              protocol    = "tcp"
              cidr_blocks = ["0.0.0.0/0"]
            },
        ]
    }

Plan: 0 to add, 1 to change, 0 to destroy.
~~~

The `+` sign in the drift section illustrates a property present on the actual resource. Inspect the entire plan: if Terraform proposes deleting the rule, confirm that is the intended action and will not break incident mitigation or service dependencies.

### 7.5. Drift in HCP Terraform

HCP Terraform provides health assessments for workspaces (depending on edition/features). Drift detection can run non-destructive refresh-only plans to compare actual resources with state. Assessments report drift; they do not automatically update state or infrastructure. Scheduled assessments, workspace notifications, and policy checks can integrate drift into operational workflows.

## 8. Importing Existing Resources into Terraform

Terraform import brings a remote object into Terraform state at a resource address. To manage its lifecycle going forward, a matching resource configuration is required. Import does not automatically convert all actual settings into complete HCL; after importing, review `terraform plan` to confirm no unintended changes exist.

### 8.1. Preparation

1. Identify the provider/account/Region and resource identifier per provider documentation.
2. Check whether the resource supports import; not all resource types are importable.
3. Confirm the object is not already managed in another state or another Terraform address.
4. Write a resource block describing the resource and dependencies.
5. Prepare the remote backend/state lock; back up state according to security procedures.
6. Import into a single address.
7. Run `terraform state show` and `terraform plan`.
8. Adjust HCL to match actual state, or review the plan to actively reconcile actual toward desired.

### 8.2. Declarative Import Block (Terraform 1.5+)

Example for an existing S3 bucket:

~~~hcl
import {
  to = aws_s3_bucket.audit_logs
  id = "company-audit-logs-prod"
}

resource "aws_s3_bucket" "audit_logs" {
  bucket = "company-audit-logs-prod"
}
~~~

Run:

~~~bash
terraform init
terraform plan
terraform apply
terraform state show aws_s3_bucket.audit_logs
terraform plan
~~~

The import block declares the target resource address and object ID. `terraform plan` displays the import action for review; `terraform apply` executes the import into state. After importing, either keep the import block as declarative adoption history or remove it per repository convention once the import is verified and state is safely saved.

### 8.3. CLI Import of a Resource

The traditional command can also be used:

~~~hcl
resource "aws_s3_bucket" "audit_logs" {
  bucket = "company-audit-logs-prod"
}
~~~

~~~bash
terraform import \
  aws_s3_bucket.audit_logs \
  company-audit-logs-prod
~~~

CLI import writes the binding into state for the resource address. It **does not automatically write the resource block**; HCL must be prepared beforehand. With CLI import, the command invokes the provider and updates state directly, so verify workspace/backend/Region before running.

### 8.4. Post-Import: State Show and Plan

~~~bash
terraform state show aws_s3_bucket.audit_logs
terraform plan
~~~

If the plan proposes modifying versioning, encryption, policy, lifecycle, or bucket settings, stop and review. You can:

- Update HCL to reflect the approved actual configuration.
- Keep HCL as desired state and apply controlled changes to reconcile the resource.
- Split settings into separate resource blocks per the AWS provider schema (e.g., bucket versioning, encryption, ownership controls), importing each remote object/address if the provider model requires it.

A provider resource abstraction may manage a subset of attributes or a distinct remote object; read the docs for your exact provider version to prevent two resource blocks from managing the same attribute.

### 8.5. Importing Multiple Resources

Import blocks support `for_each` to declare batch imports when you have a map/set of identifiers. For large inventories, Terraform query/bulk import features can be used if supported by the provider and workflow. Never import hundreds of resources before testing one representative resource and verifying provider IDs, generated configuration, dependencies, and plan behavior.

### 8.6. One-to-One Mapping and Common Errors

Terraform expects one remote object to bind to **a single resource address** in state. Importing the same object into two addresses or two workspaces creates an ownership conflict; one pipeline may alter or destroy a resource the other workspace still manages.

Common errors:

- Wrong ID format; each provider resource has its own import ID.
- Resource block missing required arguments.
- Wrong provider alias/account/Region.
- Resource already in state or managed by another workspace.
- Different provider version changing schemas/attributes.
- Plan after import proposes replacement because an immutable argument mismatches.
- Importing a parent resource while omitting dependencies or attachment resources.

## 9. Protecting State and Ownership During Import/Reconcile

Terraform state maps resource addresses to remote object identities. It also contains attributes and provider metadata; some state values can contain secrets. State is sensitive operational data, not a cache file that can be deleted or edited freely.

### 9.1. Remote State, Locking, and Backups

- Use a remote backend or HCP Terraform so the team shares a consistent state.
- Choose a backend supporting state locking; Terraform automatically locks state-writing operations when supported by the backend.
- Do not pass `-lock=false` in team workflows merely to bypass lock contention.
- Back up state before migrations/imports/state surgery; store backups with encryption and access control.
- Never commit `terraform.tfstate`, state backups, or plan files that may contain sensitive values to Git.
- Never edit JSON state directly. Use supported `terraform state` commands.
- Use `terraform force-unlock` only after verifying the lock belongs to your own failed operation and the lock ID matches; force-unlocking while someone else is applying can corrupt state.

### 9.2. Reading and Saving State Safely

~~~bash
# List resources in state.
terraform state list

# Read attributes of a resource.
terraform state show aws_s3_bucket.audit_logs

# Pull state to stdout for backup in a secured workflow.
terraform state pull
~~~

`state pull` can print sensitive data. If saving to a file, use a directory with restricted permissions, encryption, and retention policies; never send the file over chat or commit it to a repository.

### 9.3. Distinguishing state rm, state mv, and import

| Command | Effect on state | Direct effect on AWS |
|---|---|---|
| `terraform state rm ADDRESS` | Removes resource binding from state | Does not delete remote object |
| `terraform state mv SOURCE DEST` | Moves binding to a new address | Does not create/delete remote object |
| `terraform import ADDRESS ID` | Creates binding for an existing object | Does not create a new resource |
| `terraform apply` normal | Updates state per apply | May create/update/delete resources |

`terraform state rm` is not a resource deletion command; after removing the binding, the resource becomes unmanaged for that workspace. If management is still needed later, import it into the right target address or restore the binding. Use `state mv` when refactoring/renaming addresses within the same state so Terraform does not treat the old resource as destroyed and a new resource as needing creation.

### 9.4. Never Let Two Workspaces Own the Same Resource

Before transferring ownership between workspaces:

1. Freeze apply pipelines on both workspaces.
2. Back up both states and verify resource addresses/physical IDs.
3. Confirm the target workspace already has matching HCL/providers/dependencies.
4. Execute state move/import per a reviewed migration procedure.
5. Check `terraform plan` in both workspaces; the source workspace must not propose destroying the handed-over resource.
6. Record the new owner and unfreeze pipelines.

Never run import before confirming the old binding has been handled. Importing the same remote object into two states does not create coordination between them.

## 10. Managing Out-of-Band Changes in Production

Not every out-of-band change is wrong. During a production incident, an engineer may need to quickly modify a Security Group, scale capacity, or adjust a route to restore service. Risk arises when changes go unrecorded, have no expiration, and are never brought back to the IaC source of truth.

### 10.1. Classifying Changes

| Change type | Example | Action |
|---|---|---|
| Emergency break-glass | Temporarily open rule to restore connectivity | Record incident, actor, scope, and expiry; review post-incident |
| Approved permanent change | Increase DB storage due to growth | Update IaC via PR and deploy with review |
| Accidental change | Disable encryption or delete route by mistake | Restore desired state, assess impact |
| Service-managed change | ECS tasks/ASG instances scaled by controller | Evaluate proper abstraction; avoid pinning ephemeral state |
| Unmanaged creation | Create S3 bucket/queue via Console | Identify owner; import or move to data/reference model |
| Third-party automation | Security tool attaches policy/tags | Clarify field ownership and integration contract |

### 10.2. Break-Glass Workflow

An emergency workflow should include:

1. A dedicated break-glass role with MFA/short-lived session and incident-scoped permissions.
2. Ticket/incident ID, actor, resource ARN, Region/account, and justification.
3. Capture of before/after configuration or CloudTrail events.
4. Defined expiration (TTL) for the temporary change and an owner responsible for rollback.
5. Notification to the IaC owner so no concurrent pipeline apply runs.
6. Once stable, decide whether to revert or codify the approved change.
7. Run drift detection/plan and close the incident once actual state, code, and state converge.

Do not treat "incident mitigated" as the end of change management. If a temporary change cannot be rolled back immediately, create an exception with an expiry, compensating control, and clear owner.

### 10.3. Single Standard Deployment Path

Production changes should flow through the IaC pipeline with PRs, code review, policy checks, plans/change sets, and approvals. Console/CLI access may still be needed for read-only troubleshooting and break-glass; direct write permissions should be restricted, monitored, and audited based on risk.

## 11. AWS Config and CloudTrail Complement Drift Detection

CloudFormation/Terraform drift detection focuses on resources managed by a stack/state. It is not an account-wide inventory and does not detect every manually created resource. Two AWS services expand visibility:

### 11.1. AWS Config

AWS Config records resource configuration history and can evaluate resources against AWS Config Rules/conformance packs.

Use AWS Config to:

- Discover resources in an account/Region, including unmanaged resources.
- View configuration timelines/changes and compare configuration items.
- Evaluate compliance such as S3 public access, encrypted volumes, restricted SSH, or required tags.
- Aggregate compliance/configuration across multiple accounts using an aggregator.
- Detect new resources or configurations violating policy.

AWS Config rules evaluate **compliance against a rule**; they do not necessarily know what HCL/CloudFormation templates desire. Therefore Config complements IaC drift detection rather than replacing IaC plan/diff.

### 11.2. AWS CloudTrail

CloudTrail records API activity to help answer:

- Who called the API?
- At what time?
- Which API action/resource was modified?
- From which role/session, source IP, or user agent?
- Was it tied to an incident, deployment, or automation?

Management events record control-plane operations. If you need to audit object-level S3 access or other data-plane operations, configure appropriate data events; do not assume all data events are logged by default. Event history, trails, and CloudTrail Lake have different scopes, retention, and costs.

### 11.3. Combining Signals

~~~mermaid
flowchart TD
    CFN["CloudFormation drift detection"] --> CORRELATE["Correlate by ARN / account / Region / time"]
    TF["Terraform plan -refresh-only"] --> CORRELATE
    CONFIG["AWS Config history / rules"] --> CORRELATE
    TRAIL["CloudTrail API events"] --> CORRELATE
    CORRELATE --> CASE["Incident / change record"]
    CASE --> OWNER["IaC owner investigates"]
    OWNER --> FIX["Codify / revert / import / exception"]
    FIX --> VERIFY["Re-run drift and compliance checks"]
~~~

Example: AWS Config reports a Security Group is non-compliant with a restricted SSH rule; CloudTrail shows an assumed role called `AuthorizeSecurityGroupIngress`; a Terraform refresh-only plan displays the new rule. Together, the three signals identify the resource, timestamp, and owner for proper remediation.

## 12. Choosing the Right Remediation

Once drift is confirmed, there is no single "fix drift" command for every situation. The decision depends on intent, security impact, owner, resource lifecycle, and desired state.

### 12.1. Revert Actual to IaC Desired State

Use when the out-of-band change is unapproved or an expired workaround.

- Confirm the current rule/property is no longer needed for an incident or service.
- Review the Terraform plan or CloudFormation change set.
- Check whether the resource will undergo replacement, interruption, deletion, or data loss.
- Apply through an approved pipeline.
- Re-run drift detection and verify service health.

Example: Terraform HCL still allows only HTTPS. After confirming the SSH rule is no longer needed, a normal plan proposes removing the out-of-band rule. Review the plan and apply within the change window.

### 12.2. Codify Actual as Desired State

Use when the out-of-band change was intentional, approved, and permanent.

1. Collect the actual configuration and justification for the change.
2. Update the template/HCL to describe the approved state.
3. Open a PR with a risk assessment and rollback plan.
4. Run plan/change set to ensure no unintended changes appear.
5. Merge/deploy via pipeline.
6. Re-run drift checks to confirm the source of truth matches.

If actual state was edited in the Console before updating code, the next pipeline run should not unexpectedly roll back that change. Update code and review the plan before applying.

### 12.3. Import Unmanaged Resource

Use when a resource already exists, has a clear owner, and the decision is to bring it under the IaC lifecycle. Before importing, verify resource type support, identifier, dependencies, current state/stack, and one-to-one ownership. If the resource only needs to be referenced, use a data source/CloudFormation parameter or output rather than importing ownership.

### 12.4. Transfer Ownership or Split Resources

If a resource currently lives in the wrong stack/workspace, plan a handover. Pause concurrent applies, back up state, remove bindings/ownership cleanly, and import into the target owner. Ensure the previous owner no longer proposes destroying the resource.

### 12.5. Time-Bound Temporary Exception

Sometimes a change cannot be codified or reverted immediately. In that case, the exception must specify:

- Resource ARN, account/Region, and differing properties.
- Business/incident justification and risk acceptance.
- Compensating controls (e.g., restricted source CIDR, additional monitoring).
- Owner and approver.
- Expiry/rollback date.
- Drift check cadence and how to close the exception.

Do not use Terraform `lifecycle.ignore_changes` or omit properties from a template merely to hide drift. Only use ignore/ownership delegation when another controller is explicitly designated to manage that field; document the field, owner, reason, and tests to avoid masking security changes.

### 12.6. When a Resource Was Deleted Out-of-Band

If CloudFormation reports `DELETED` or Terraform refresh shows the object is gone:

- Check CloudTrail, AWS Config history, and the dependency graph to determine who deleted it and when.
- Verify whether the resource was intentionally decommissioned or deleted by mistake.
- If restoration is required, review the plan/change set recreating the resource; some replacements generate new physical IDs and require updating references/data restores.
- If the resource was retired, update IaC and downstream references per the change request; do not keep a resource block merely to make detection "green."
- Never recreate a database/storage resource without confirming backup, retention, and data recovery requirements.

## 13. Preventing Drift in CI/CD and Operations

Effective drift control combines preventive controls and detective controls.

### 13.1. Preventive Controls

- Use dedicated pipeline roles for IaC deployments; restrict direct production write access via Console/CLI.
- Use separate break-glass roles with MFA, short sessions, alerts, and post-incident reviews.
- Require PR reviews, plan/change set artifacts, and approvals before production applies.
- Use policy-as-code to block public storage, unrestricted SSH/RDP, unencrypted resources, or missing tags.
- Apply appropriate AWS Organizations SCPs/permission boundaries; avoid overly broad denies that block IaC service roles or incident response.
- Enforce owner, environment, cost-center, repository/workspace, and support contact tags per policy.
- Separate shared network/security/platform ownership from application stacks.
- Do not let operational scripts alter IaC-managed properties without a clear contract/field ownership.

### 13.2. Detective Controls

- Schedule CloudFormation drift detection for critical stacks.
- Schedule Terraform refresh-only plans/health assessments for critical workspaces.
- Use AWS Config rules/conformance packs to evaluate compliance account-wide.
- Use CloudTrail/EventBridge to alert on API write calls outside deployment roles.
- Track unmanaged resources, orphan resources, and tag/owner coverage.
- Route findings to dashboards/tickets containing account, Region, resource ARN, owner, and timestamp.
- Set remediation SLAs by severity: critical security drift requires faster response than tag/cost metadata drift.

### 13.3. Terraform Plan in Pipelines

A check step can run:

~~~bash
terraform init -input=false
terraform validate
terraform plan -input=false -detailed-exitcode
~~~

`-detailed-exitcode` typically returns:

| Exit code | Meaning |
|---:|---|
| 0 | Plan has no changes |
| 1 | Error |
| 2 | Plan has changes |

Exit code 2 alone does not prove drift: changes may come from an HCL PR. Pipelines must distinguish source changes from scheduled drift assessments; use refresh-only plans or HCP Terraform health assessments for drift-focused checks.

If saving plan files for review/apply, protect the file because it can contain sensitive values and resource details. Do not publish raw plans/state as public artifacts.

### 13.4. CloudFormation Drift Schedule

EventBridge Scheduler or a periodic pipeline can call `detect-stack-drift`, poll the detection ID, and retrieve resource drift details. Alert when a stack is `DRIFTED` or detection fails. Set concurrency/rate limits, handle nested stacks separately, and run only on CloudFormation-supported stack statuses.

### 13.5. Tiered Drift Policy

| Tier | Examples | Suggested checks |
|---|---|---|
| Critical | IAM, KMS, public access, network perimeter, production data | Frequent detection + Config/CloudTrail alerts |
| High | RDS, EKS, load balancers, production compute | Scheduled plan/drift assessment and PR approval |
| Standard | Non-production application resources | Scheduled assessment per release/cadence |
| Low | Disposable sandbox resources | Cleanup/TTL and periodic inventory |

Cadence should reflect blast radius, compliance, and API call costs. Drift detection does not replace real-time monitoring or security incident detection.

## 14. Comparing CloudFormation and Terraform

Both tools share the goal of managing desired state, yet they store ownership and detect drift differently.

| Aspect | AWS CloudFormation | Terraform |
|---|---|---|
| Desired configuration | Stack template + parameters | HCL configuration |
| Recorded ownership | Stack resources/logical IDs | Resource addresses in state |
| Drift detection | Detect stack/resource drift | Refresh provider state then create plan |
| Highlighting drift | Drift status + expected/current properties | Plan output/refresh-only plan |
| Accepting actual into recorded state | Import/adopt resource or update stack/template per workflow | `apply -refresh-only` updates state |
| Importing unmanaged resource | Import change set, resource identifier, `DeletionPolicy` | Import block or CLI `terraform import` |
| Previewing changes before execution | Change set | Execution plan |
| Ownership uniqueness | A resource cannot be imported into multiple stacks in the same Region | A remote object should bind to one resource address |
| Coverage | Only drift-supported resources/properties | Depends on provider read/schema and resource implementation |
| State security | AWS manages stack metadata | Team/backend must protect Terraform state |

### 14.1. Choosing Tools by Workflow

- Use CloudFormation drift detection when a resource already resides in a CloudFormation stack and you need to compare the template with actual properties.
- Use Terraform plan/refresh-only when a resource is managed by Terraform state.
- Use AWS Config when you need inventory/compliance across many resources, including those outside IaC.
- Use CloudTrail when investigating which actor/role called an API that modified a resource.
- Use import when a resource has no IaC owner and the organization decides to adopt ownership.

Never run Terraform import on a resource belonging to a CloudFormation stack merely to "pull it into Terraform." First establish an ownership handover plan between both systems, including state/stack removal and rollback.

## 15. Runbook for Handling a Drift Incident

Example: a production Security Group unexpectedly has SSH ingress open from the Internet.

### 15.1. Contain and Gather Evidence

1. Identify the account, Region, Security Group ID, VPC, and affected workloads.
2. Assess exposure, source CIDR, port, timestamp, and traffic.
3. Gather CloudTrail events, AWS Config timeline, and incident context.
4. Identify the IaC owner (CloudFormation stack or Terraform workspace) and running pipeline status.
5. If risk is high, follow incident procedures to limit exposure; record before/after states and notify the IaC owner.

### 15.2. Review Drift

If CloudFormation owns the resource:

~~~bash
aws cloudformation detect-stack-resource-drift \
  --stack-name production-network \
  --logical-resource-id WebSecurityGroup

aws cloudformation describe-stack-resource-drifts \
  --stack-name production-network
~~~

If Terraform owns the resource:

~~~bash
terraform plan -refresh-only
terraform plan
~~~

Store drift results/plans in a controlled location tagged with the incident ID. Never share plans/states containing secrets on public channels.

### 15.3. Decide Remediation

- If the SSH rule is unapproved: restore the approved configuration after confirming recovery is unaffected.
- If the rule is a necessary workaround: create an exception with TTL/compensating controls, then codify or roll back during a change window.
- If the resource has no owner: inventory, identify dependencies, and import once approved.
- If the rule is managed by security automation: clarify field ownership and prevent two controllers from fighting over the same property.

### 15.4. Verify and Close Incident

- Verify the live Security Group no longer has unintended rules.
- Re-run drift detection/plan after remediation.
- Confirm service health, application connectivity, and security controls.
- Ensure no pending pipeline apply or automation will reintroduce the old rule.
- Document root cause, actor, timeline, corrective action, owner, and prevention tasks.
- Close the exception/ticket once IaC, state, and actual state have converged.

## 16. Sandbox Practice Labs

### 16.1. Lab A — CloudFormation Drift Detection

1. Create a sandbox stack with a Security Group opening only HTTPS from a test CIDR.
2. Use the Console/CLI to add a temporary ingress rule outside the stack.
3. Run `detect-stack-drift` and retrieve resource drift details.
4. Record expected/current property values and statuses.
5. Remove the out-of-band rule or update the template based on your decision.
6. Run detection again and confirm the expected status.

Never perform experiments on production Security Groups or resources serving live traffic.

### 16.2. Lab B — Importing an S3 Bucket into CloudFormation

1. Create a sandbox bucket using the AWS CLI/Console and verify its configuration.
2. Create a target CloudFormation stack that already exists.
3. Write a template describing the bucket with `DeletionPolicy: Retain`.
4. Create a resources-to-import file with the right `ResourceType`, `LogicalResourceId`, and `ResourceIdentifier`.
5. Create an import change set, review it, and execute.
6. Run drift detection; adjust the template if the resource is `MODIFIED`.
7. Verify the stack manages the bucket without creating a new bucket or losing objects.

### 16.3. Lab C — Terraform Refresh-Only

1. Use Terraform to create a sandbox Security Group.
2. Modify a property via the AWS Console.
3. Run `terraform plan` and inspect the drift output.
4. Run `terraform plan -refresh-only` and review state changes.
5. Try `terraform apply -refresh-only` in the sandbox to see state update while the AWS resource remains unchanged.
6. Run a normal plan; explain why Terraform may propose reverting actual configuration back to HCL.
7. Reconcile according to an intentional decision.

### 16.4. Lab D — Terraform Import

1. Create a sandbox S3 bucket outside Terraform.
2. Write an HCL resource block and an import block pointing to the bucket name.
3. Run `terraform plan`, review the import action, and then run `terraform apply`.
4. Run `terraform state show` and `terraform plan`.
5. Adjust HCL to match actual state or review changes to actively reconcile.
6. Verify the bucket is managed by only one workspace.

### 16.5. Lab E — Investigating an Out-of-Band Change

Simulate an API write call on a sandbox resource. Use CloudTrail to identify the principal/action/time, AWS Config to inspect the configuration timeline, and then correlate the drift result with the IaC owner. Write a change record specifying revert vs. codify, owner, expiry, and verification method.

## 17. Review Checklist Before Merging or Closing a Drift Ticket

### Ownership and Inventory

- [ ] Identified account, Region, resource ARN/physical ID?
- [ ] Identified owning CloudFormation stack or Terraform workspace?
- [ ] Is the resource managed by another IaC system?
- [ ] Verified resource type/property supports drift/import?
- [ ] Identified dependencies and blast radius?

### Detection and Investigation

- [ ] Does the drift result/plan have a recent timestamp?
- [ ] Distinguished `NOT_CHECKED` from `IN_SYNC`?
- [ ] Inspected expected/current property values?
- [ ] Checked AWS Config/CloudTrail and incident/change records?
- [ ] Identified actor, intent, and business owner?

### Remediation/Import

- [ ] Is the decision to revert, codify, import, hand over, or grant an exception justified?
- [ ] Does Terraform import have a resource block, exact ID, and one-to-one binding?
- [ ] Does CloudFormation import have `DeletionPolicy`, exact identifier, and an import change set?
- [ ] Is the import operation free of simultaneous creates/deletes/property updates?
- [ ] Is the plan/change set free of unintended replacements/deletions?
- [ ] Do temporary exceptions have an owner, expiry, and compensating controls?
- [ ] Are state backups/locking/access controls in place?

### Verification and Governance

- [ ] Were changes deployed through an approved workflow?
- [ ] Was drift detection/plan re-run after remediation?
- [ ] Have actual resource, IaC code, and state/stack converged within checked scope?
- [ ] Are service health and security posture verified?
- [ ] Are CI/CD, AWS Config, CloudTrail alerts, and ownership tags aligned?
- [ ] Does the ticket/incident contain root cause, evidence, owner, and prevention actions?

## 18. Self-Assessment Questions

1. What is configuration drift?
2. How do desired configuration, recorded state, and actual configuration differ?
3. Is an unmanaged resource always drift?
4. Why should a resource have only one IaC owner?
5. Which values does CloudFormation drift detection compare?
6. Does `IN_SYNC` prove every property was checked?
7. Does `NOT_CHECKED` mean a resource has not drifted?
8. Why does CloudFormation only detect explicitly declared properties?
9. Does drift detection on a parent stack automatically include nested stacks?
10. Which permissions are needed to run CloudFormation drift detection?
11. Does importing a resource into CloudFormation require `DeletionPolicy`?
12. Can an import change set simultaneously create new resources or change properties?
13. Why must you run drift detection after a CloudFormation import?
14. How does a normal Terraform plan refresh state?
15. How does `terraform plan -refresh-only` differ from a normal plan?
16. Does `terraform apply -refresh-only` modify resources on AWS?
17. Why might a normal plan after refresh-only propose reverting actual configuration?
18. Does Terraform CLI import automatically generate an HCL resource block?
19. From which version is the Terraform import block supported?
20. Why should one remote object bind to only one Terraform resource address?
21. Does `terraform state rm` delete the remote resource?
22. In what scenario is `terraform state mv` useful?
23. Why are remote state and locking needed in a team?
24. How does AWS Config differ from IaC drift detection?
25. How does CloudTrail help investigate out-of-band changes?
26. When should actual configuration be codified?
27. When should actual configuration be reverted to desired state?
28. When should a resource be imported instead of using a data source?
29. Why should `lifecycle.ignore_changes` not be used to hide drift?
30. What information must a break-glass change record?
31. Why can `-refresh=false` produce an incomplete plan?
32. Which guardrails help reduce out-of-band changes?
33. Why must plan files and Terraform state be protected?
34. Does drift detection replace real-time security monitoring?

### Answer Key Guidance

- **Drift:** Discrepancy between desired/recorded state and actual state; unmanaged resources have no IaC owner yet.
- **CloudFormation:** Compares actual state against explicitly declared supported properties; import via IMPORT change set, requires `DeletionPolicy`, then re-detect.
- **Terraform:** Normal plan refreshes in memory; refresh-only apply updates state to actual without editing AWS; import requires a resource block and one-to-one binding.
- **Ownership:** One remote object has one IaC owner; use data sources/references when not taking lifecycle ownership.
- **Governance:** CloudTrail investigates actor/API, AWS Config provides inventory/history/compliance; break-glass requires a ticket, expiry, owner, and reconciliation.
- **Remediation:** Revert, codify, import, hand over, or grant an exception depending on intent and impact; review plans/change sets before applying.

## 19. Official AWS and HashiCorp Documentation

1. [CloudFormation drift detection overview](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — Drift concepts, status codes, limitations and permissions.
2. [Detect drift on an entire CloudFormation stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-stack.html) — Start and inspect stack drift operations.
3. [Detect drift on individual stack resources](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-resource.html) — Resource-level detection.
4. [CloudFormation resource type support](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-supported-resources.html) — Import, drift detection and IaC generator support matrix.
5. [Import AWS resources into an existing CloudFormation stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/import-resources-manually.html) — Import requirements, DeletionPolicy and operation constraints.
6. [Import existing resources into a stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-existing-stack.html) — Import workflow and CLI.
7. [Automatically import named resources](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/import-resources-automatically.html) — Auto-import support and requirements.
8. [AWS Config developer guide](https://docs.aws.amazon.com/config/latest/developerguide/WhatIsConfig.html) — Resource inventory, configuration history and rules.
9. [AWS CloudTrail user guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — API activity and audit trails.
10. [Terraform plan command](https://developer.hashicorp.com/terraform/cli/commands/plan) — Normal and refresh-only planning modes.
11. [Manage resource drift in Terraform](https://developer.hashicorp.com/terraform/tutorials/state/resource-drift) — Detect drift and inspect refresh-only plans.
12. [Terraform import overview](https://developer.hashicorp.com/terraform/language/import) — Import workflows and resource ownership.
13. [Terraform import block reference](https://developer.hashicorp.com/terraform/language/block/import) — Declarative import syntax and arguments.
14. [Import existing resources with Terraform CLI](https://developer.hashicorp.com/terraform/cli/import/usage) — CLI import workflow and one-to-one mapping.
15. [Terraform state](https://developer.hashicorp.com/terraform/language/state) — State purpose, security and object bindings.
16. [Terraform state locking](https://developer.hashicorp.com/terraform/language/state/locking) — Lock behavior and force-unlock cautions.
17. [Terraform state backends](https://developer.hashicorp.com/terraform/language/state/backends) — Remote state storage and locking.
18. [HCP Terraform drift and policy tutorial](https://docs.hashicorp.com/terraform/tutorials/cloud/drift-and-policy) — Health assessments and drift checks.

> **Final takeaway:** Drift detection reveals where actual resources diverge from IaC configuration within the tool's inspection scope. Import brings unmanaged resources under a single IaC owner. Terraform refresh-only updates state, whereas normal apply can modify AWS; CloudFormation import requires an import change set and `DeletionPolicy`. Every out-of-band change needs an owner, justification, audit evidence, an expiry if temporary, and a reconciliation step so code, state, and infrastructure stay consistent.
