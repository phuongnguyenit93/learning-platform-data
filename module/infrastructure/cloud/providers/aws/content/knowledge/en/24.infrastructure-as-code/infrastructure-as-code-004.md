# Change Sets, Stack Updates, and Rollbacks

A CloudFormation change might merely adjust the number of EC2 instances, or it might replace a database, delete a security group, or recreate a load balancer. Once a stack serves production, updating a template is no longer a simple file edit: it is a **deployment that modifies running infrastructure**.

A CloudFormation **change set** lets you preview the changes an update intends to perform. Operators can inspect the list of resources to be added, modified, deleted, or replaced, review property-level differences, and then decide whether to execute. If an update fails, CloudFormation can roll back to the previous configuration; when rollback itself fails, the stack transitions to a state requiring intervention such as UPDATE_ROLLBACK_FAILED.

This lesson belongs to the **Infrastructure as Code** chapter of the **CLOUD_PROVIDERS_AWS** module. It frames change sets, stack updates, and rollbacks within a safe AWS operational workflow with monitoring, recovery, and cost control. Examples use AWS CloudFormation and the AWS CLI; stack names, accounts, Regions, and resources are illustrative.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the roles of a CloudFormation stack, template, parameters, resources, outputs, and change set.
2. Create a change set for an existing stack and review it before executing.
3. Interpret Add, Modify, Remove, Import, and Replacement actions to evaluate blast radius.
4. Distinguish updates with no interruption, updates with some interruption, and replacements.
5. Update a stack via console or AWS CLI using an auditable workflow.
6. Monitor stack status, events, and resource status reasons, and handle update failures.
7. Configure rollback triggers using CloudWatch alarms and a monitoring period.
8. Distinguish UPDATE_ROLLBACK_COMPLETE from UPDATE_ROLLBACK_FAILED and know how to recover.
9. Use stack policies, termination protection, DeletionPolicy, and UpdateReplacePolicy appropriately.
10. Detect drift, manage nested stacks, and configure CloudFormation service roles and least privilege.
11. Plan testing, cutover, rollback, and post-deployment verification.

## 2. Foundational Concepts

| Concept | Meaning | Example |
|---|---|---|
| **Template** | YAML/JSON specification of desired infrastructure | VPC, subnet, EC2, RDS, S3 |
| **Stack** | A deployed instance of a template with parameters/tags/role | orders-prod-network |
| **Resource logical ID** | Resource name in the template used by CloudFormation for tracking | AppDatabase |
| **Physical ID** | Actual AWS resource ID | DB instance identifier, bucket name |
| **Parameter** | Input passed when creating/updating a stack | InstanceType, Environment |
| **Output** | Value published by a stack for users or other stacks | VPC ID, endpoint |
| **Change set** | Preview of proposed changes for a stack operation | Replace database, add subnet |
| **Stack event** | Event describing resource/stack progress | UPDATE_IN_PROGRESS, UPDATE_FAILED |
| **Drift** | Actual configuration differs from template and parameter values | SG rule modified outside CloudFormation |

CloudFormation stores the mapping between logical IDs in the template and physical resources. When the template changes, CloudFormation compares the new configuration with the currently deployed stack configuration to determine which resources to create, modify, retain, replace, or delete.

### 2.1. Updating a Stack vs. Editing a Template

Editing a YAML file in Git only changes the **desired state in the repository**. AWS resources only change when a stack operation is executed. A change set previews the difference between the new desired state and the current stack.

~~~mermaid
flowchart TD
    GIT["New template in Git"] --> INPUT["Parameters / capabilities / role"]
    INPUT --> CS["Create change set"]
    CS --> REVIEW["Review resource actions<br/>Replacement / property diff"]
    REVIEW --> DECISION{"Accept changes?"}
    DECISION -->|"No"| DELETE["Delete change set"]
    DECISION -->|"Yes"| EXEC["Execute change set"]
    EXEC --> EVENTS["Monitor stack events"]
    EVENTS --> RESULT{"Result"}
    RESULT -->|"UPDATE_COMPLETE"| VERIFY["Smoke test and verification"]
    RESULT -->|"Rollback completed"| INVESTIGATE["Investigate root cause"]
    RESULT -->|"UPDATE_ROLLBACK_FAILED"| RECOVER["Recover rollback"]
~~~

## 3. What Is a Change Set and What Are Its Limits?

A change set describes the changes CloudFormation **intends** to perform when a stack operation runs. When you create a change set, CloudFormation analyzes template/parameter changes and returns a list of resource actions. Creating a change set does not apply changes to the stack.

A change set helps:

- Identify which resources will be **Add, Modify, Remove, Import**.
- See whether a resource will undergo **Replacement**.
- View property-level changes and before/after values where supported.
- Compare alternative change plans using multiple change sets.
- Catch certain validation errors, naming conflicts, quotas, and configuration issues before execution.
- Create via Console, AWS CLI, or CloudFormation API.

**A change set does not guarantee the update will succeed.** Some errors only surface when CloudFormation calls service APIs or waits for a resource to stabilize, such as custom resource logic, runtime service quotas, missing resource policy permissions, network conditions, or unready dependent resources.

### 3.1. Change Set Lifecycle

| Status | Meaning |
|---|---|
| CREATE_PENDING / CREATE_IN_PROGRESS | CloudFormation is creating the change set |
| CREATE_COMPLETE | Change set has been created and can be reviewed |
| FAILED / CREATE_FAILED | Failed to create change set; inspect StatusReason |
| AVAILABLE | Execution status indicating the change set can be executed |
| EXECUTE_IN_PROGRESS | Change set is currently executing |
| EXECUTE_COMPLETE | Execution completed |
| OBSOLETE | Change set is no longer applicable to the current stack |

Exact status names depend on the `ChangeSetStatus` and `ExecutionStatus` fields. A change set with `ChangeSetStatus` `CREATE_COMPLETE` is not necessarily executable unless `ExecutionStatus` is `AVAILABLE`.

### 3.2. A Change Set Is Not a Backup

A change set does not copy database data, create AMIs, snapshot EBS volumes, or guarantee data recovery after a resource is replaced or deleted. For stateful resources, you must design independent **backups, snapshots, replication, and restore tests**.

## 4. Reading Change Types Before Execution

A change set typically displays the action and replacement level. Reviewers must understand both fields; a `Modify` can lead to replacement.

| Action | Meaning | Questions during review |
|---|---|---|
| **Add** | Create a new resource | Are quotas, subnets, policies, naming, and costs accounted for? |
| **Modify** | Update an existing resource | Do the properties cause interruption or replacement? |
| **Remove** | Delete a resource from the stack | Will data be lost? Is there a retain policy? |
| **Import** | Bring an existing resource under stack management | Do resource properties match the template and import requirements? |

Replacement can be represented as:

- **True:** CloudFormation will replace the physical resource.
- **False:** no physical resource replacement is needed.
- **Conditional:** replacement may occur depending on property values or runtime conditions.

Note: **Conditional is not a Resource Action**. It is a value that can appear in the `Replacement` field. The action remains `Add`, `Modify`, `Remove`, or `Import`; whether replacement occurs is described separately.

### 4.1. Replacement Needs the Most Careful Review

For example, changing a DB instance identifier or an immutable property can cause CloudFormation to create a new database and delete the old one according to resource update semantics. This can cause:

- Downtime or endpoint changes.
- Regeneration of the physical ID.
- Increased cost while both resources coexist during cutover.
- Data loss if the old resource is deleted without an appropriate snapshot/retain policy.
- Impact on stacks/apps referencing the old endpoint.

Do not treat replacement as a minor diff line. For databases, volumes, buckets, keys, or critical network resources, prepare a migration/cutover plan and data recovery strategy.

### 4.2. Property-Level Changes

When property-level change details are available, review:

1. Which properties are modified, added, or removed?
2. Do current and proposed values match the target environment?
3. Does the resource type documentation specify `Update requires`: no interruption, some interruption, or replacement?
4. Are security exposure, encryption, retention, deletion behavior, or public access changing?
5. Will dependent resources be updated in a cascade?

Not every resource/property provides complete property-level diffs. Cross-check the CloudFormation resource reference and service documentation when the change set omits details.

## 5. Standard Pre-Update Workflow

Before creating a change set, know what state the stack is currently in, which account/Region manages it, and whether the current template has drifted.

### 5.1. Preflight Checklist

- Verify the AWS account, Region, and caller identity.
- Verify the stack name/stack ID, stack status, and CloudFormation service role.
- Verify the template/version/commit being deployed.
- Check parameters, dynamic references, mappings, conditions, and capabilities.
- Inspect recent stack events and resource status reasons.
- Check drift on critical resources.
- Verify backups/snapshots and RPO/RTO if stateful resources are involved.
- Verify IAM permissions, service quotas, VPC/network dependencies, and maintenance window.
- Define rollback triggers/CloudWatch alarms and the monitoring period.
- Prepare smoke tests, dashboards, on-call owner, and rollback decision criteria.

### 5.2. Only Update Stacks in an Appropriate State

Normally, a stack should be in a stable state such as `CREATE_COMPLETE` or `UPDATE_COMPLETE` before a regular update. If the stack is in `UPDATE_IN_PROGRESS`, `DELETE_IN_PROGRESS`, or `UPDATE_ROLLBACK_FAILED`, do not start a new update. Inspect its state and resolve the current operation first.

### 5.3. Confirm the Exact Stack

Stack names can be identical across Regions or accounts. Use the **stack ID/ARN** in production automation whenever possible; verify the account, Region, environment tags, and service role before creating a change set.

~~~bash
aws sts get-caller-identity

aws cloudformation describe-stacks \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --query 'Stacks[0].{StackId:StackId,Status:StackStatus,Reason:StackStatusReason,RoleARN:RoleARN,Drift:DriftInformation.StackDriftStatus}' \
  --output json
~~~

This is a metadata read command. If the stack has no drift information or has never run drift detection, the drift field may not reflect current state; proactively run drift detection when needed.

## 6. Creating a Change Set with the AWS CLI

The example below creates a change set for an existing stack. The new template resides in a local file and parameters are passed explicitly.

### 6.1. Illustrative Template

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Orders API compute settings

Parameters:
  Environment:
    Type: String
    AllowedValues:
      - dev
      - staging
      - prod
  InstanceType:
    Type: String
    Default: t3.small

Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTPS from approved ingress
      VpcId: vpc-0123456789abcdef0
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 10.20.0.0/16

  AppLaunchTemplate:
    Type: AWS::EC2::LaunchTemplate
    Properties:
      LaunchTemplateData:
        InstanceType: !Ref InstanceType
        SecurityGroupIds:
          - !Ref AppSecurityGroup

Outputs:
  LaunchTemplateId:
    Value: !Ref AppLaunchTemplate
~~~

This template illustrates structure and should only be used in a lab after replacing the VPC ID with an appropriate VPC. For production, VPC, subnet, AMI, IAM instance profile, ingress source, and launch template version must be intentionally managed. Do not use overly broad CIDRs or hardcoded resource IDs from the wrong account/Region.

### 6.2. Creating the Change Set

Example using parameter overrides:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=prod \
    ParameterKey=InstanceType,ParameterValue=t3.medium \
  --description "Increase app instance size after capacity review" \
  --region ap-southeast-1
~~~

Key points to note:

- Use `UPDATE` for an existing stack. Creating a change set for a new stack is the `CREATE` flow and has different stack states.
- When not passing a new parameter, confirm whether the current value or default will be used; avoid accidentally resetting critical parameters.
- For templates containing IAM resources, pass the appropriate capability such as `CAPABILITY_IAM` or `CAPABILITY_NAMED_IAM`.
- For macros/transforms that expand templates, `CAPABILITY_AUTO_EXPAND` may be required depending on the template type and workflow.
- For nested stacks, decide whether to create change sets for nested stacks; review both root and child stacks.
- A CloudFormation service role can be specified via `--role-arn` when needed; this role is associated with the stack for future operations.

### 6.3. Waiting for Change Set Creation

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1 \
  --output json
~~~

Check:

- `Status` and `StatusReason`.
- Whether `ExecutionStatus` is `AVAILABLE`.
- `Changes`: `LogicalResourceId`, `ResourceType`, `Action`, `Replacement`.
- `Details`: `Target.Attribute`, `Target.Name`, `Evaluation`, and `ChangeSource` if provided.
- Parameters, capabilities, role ARN, rollback configuration, and nested change sets.

If the change set is `FAILED`, read `StatusReason`, fix the cause, and create a **new change set**. Never execute a failed change set or assume a change set created from an old template still applies after the stack has changed.

### 6.4. Viewing a Compact List of Changes

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1 \
  --query 'Changes[].ResourceChange.{LogicalId:LogicalResourceId,Type:ResourceType,Action:Action,Replacement:Replacement,Scope:Scope}' \
  --output table
~~~

This output helps with quick review, but before production you must inspect full details/property changes, the template, parameter values, and the resource reference. A summary table cannot replace architectural review.

## 7. Change Set Review Checklist

Review the change set layer by layer:

### 7.1. Resource Actions

- [ ] No unexpected `Remove` resources.
- [ ] Every `Add` has an owner, quota, dependencies, naming, and cost estimate.
- [ ] Every `Modify` is classified by interruption/replacement.
- [ ] Every `Replacement` has a plan for data, endpoints, DNS, cutover, and cleanup.
- [ ] `Import` is used only for existing resources meeting import requirements.
- [ ] No changes outside the scope of the ticket/commit.

### 7.2. Security Changes

- [ ] IAM policies do not expand permissions beyond requirements.
- [ ] Security group ingress/egress does not open overly broad CIDRs or ports.
- [ ] S3 bucket public access, encryption, versioning, and lifecycle remain accurate.
- [ ] KMS keys, key policies, aliases, and grants are reviewed.
- [ ] Secrets Manager/SSM dynamic references point to the right secret/path.
- [ ] VPC endpoint policies, route tables, and network ACLs do not expose services.
- [ ] Logging/audit/CloudTrail settings remain enabled as required.

### 7.3. Availability, Data, and Cost

- [ ] Stateful resources (RDS/Aurora/EBS/ElastiCache) have appropriate backups/snapshots.
- [ ] Multi-AZ/replicas/autoscaling settings are not accidentally reduced.
- [ ] Replacements do not cause downtime exceeding SLOs.
- [ ] Capacity/quotas/limits are sufficient for new resources.
- [ ] Temporary double cost while old and new resources coexist is accounted for.
- [ ] CloudWatch alarms and rollback monitoring periods are meaningful.
- [ ] Rollback can restore configuration, while data needing separate restore has a plan.

### 7.4. Which Change Sets Must Be Rejected?

Do not execute when:

- A database or storage resource undergoes an unplanned replacement.
- A `Remove` resource lacks an owner or a backup/retain decision.
- An IAM policy unexpectedly widens to wildcards or broad resources.
- The stack/Region/account is wrong.
- The change set was created from a different commit/template/parameter set than the release under review.
- The change set is obsolete or `ExecutionStatus` is not `AVAILABLE`.
- Nested stack changes have not been reviewed.
- Unexplained drift exists, risking overwriting out-of-template changes.

## 8. Executing a Change Set and Monitoring Stack Updates

Execute only after review and approval per the deployment workflow:

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1
~~~

After execution:

- The stack transitions to `UPDATE_IN_PROGRESS`.
- CloudFormation applies resource operations according to the dependency graph.
- Events appear for each resource and the stack.
- If successful, the stack reaches `UPDATE_COMPLETE`.
- If the update fails and rollback succeeds, the stack typically reaches `UPDATE_ROLLBACK_COMPLETE`.
- If rollback cannot complete, the stack reaches `UPDATE_ROLLBACK_FAILED`.

After executing a change set, other change sets attached to the stack are deleted/invalidated because the stack state has changed. If the update fails and you want to retry, create a new change set from the current state.

### 8.1. Monitoring Stack Events

~~~bash
aws cloudformation describe-stack-events \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --max-items 50 \
  --output table
~~~

Stack events are typically returned in reverse chronological order, with the newest event first. Focus on:

- `Timestamp`.
- `LogicalResourceId` and `PhysicalResourceId`.
- `ResourceType`.
- `ResourceStatus`.
- `ResourceStatusReason`.
- `ClientRequestToken` to correlate operations if present.

When seeing a resource `UPDATE_FAILED`, read the specific reason. The stack-level event may only say the operation failed; the resource event typically shows causes such as quotas, invalid parameters, dependency violations, insufficient permissions, or service stabilization timeouts.

### 8.2. Monitoring Stack Status

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --query 'Stacks[0].{Status:StackStatus,Reason:StackStatusReason,Updated:LastUpdatedTime}' \
  --output json
~~~

Do not rely solely on the CLI exit code of `execute-change-set` to conclude a deployment succeeded. The command can return as soon as CloudFormation starts the operation; monitor until a terminal status and run application smoke tests.

### 8.3. Monitoring Specific Resources

~~~bash
aws cloudformation describe-stack-resources \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --output table
~~~

Use the resource list to cross-check logical ID, physical ID, and resource status. For replacements, verify old/new physical IDs and consumers referencing endpoints or ARNs.

### 8.4. Do Not Edit Resources Outside CloudFormation Mid-Update

While a stack is updating or rolling back, avoid manually modifying resources managed by CloudFormation unless a runbook calls for specific remediation. Out-of-band edits can cause CloudFormation to lose expected state, causing rollback or subsequent updates to fail.

## 9. Automatic Rollback When Stack Updates Fail

In a normal update, if CloudFormation cannot complete a resource operation, the stack can automatically roll back applied changes to the pre-operation state. The final status is typically **UPDATE_ROLLBACK_COMPLETE** when rollback succeeds.

Rollback can:

- Restore resource properties to previous values.
- Delete newly created resources from the operation if policies/operation settings permit.
- Restore modified resources according to the resource type's update behavior.
- Keep the old resource if replacement created a new resource and rollback reverts to the previous physical resource.

**Rollback is not a distributed data transaction.** It does not reverse side effects performed by applications/custom resources, does not automatically restore data written/deleted inside databases, and does not undo changes made outside CloudFormation.

### 9.1. Update and Rollback Statuses

| Stack status | Meaning | Action |
|---|---|---|
| UPDATE_IN_PROGRESS | Applying changes | Monitor events/alarms; do not run another update |
| UPDATE_COMPLETE | Update succeeded | Run smoke tests and post-deployment verification |
| UPDATE_FAILED | Update failed; depends on failure behavior/configuration | Read events and determine which operation the stack can continue with |
| UPDATE_ROLLBACK_IN_PROGRESS | Reverting the update | Monitor resource rollback events |
| UPDATE_ROLLBACK_COMPLETE | Rollback completed; stack can accept future updates | Investigate root cause, create a new change set after fixing |
| UPDATE_ROLLBACK_FAILED | Rollback did not complete | Resolve the blocker, then continue update rollback |

A stack in `UPDATE_ROLLBACK_COMPLETE` does not mean the new deployment succeeded; it means the stack returned to its state before the failed update. The application may still suffer from pre-existing issues or data may have been affected by side effects.

### 9.2. Canceling an Update

CloudFormation supports canceling certain stack updates while in `UPDATE_IN_PROGRESS`. This asks CloudFormation to stop the update and roll back according to operation semantics; it is not an instant undo button. Some resource operations cannot stop immediately, and CloudFormation still needs time to stabilize/roll back.

Do not cancel merely because no events appear for a few seconds. Check the resource operation, service events, and timeout before deciding.

## 10. Rollback Triggers with CloudWatch Alarms

You can instruct CloudFormation to monitor one or more **CloudWatch alarms** during creation/update and during a monitoring period after resources are deployed. If an alarm enters the `ALARM` state, CloudFormation rolls back the entire stack operation.

### 10.1. Choosing Meaningful Alarms

Examples:

- Application 5xx error rate exceeds threshold.
- ALB target response time/p99 exceeds SLO.
- ECS service fails to maintain desired healthy tasks.
- CPU/memory utilization exceeds thresholds impacting availability.
- Custom business metric shows a sharp spike in checkout failures.

Alarms must measure the exact application/stack being updated. An alarm stuck in `INSUFFICIENT_DATA` or lacking datapoints can prevent rollback signals from reflecting real health; a non-existent alarm ARN can cause the stack operation to fail.

### 10.2. Monitoring Period

The rollback configuration includes **MonitoringTimeInMinutes**, ranging from 0 to 180 minutes, defaulting to 0. When set, CloudFormation continues monitoring triggers after resource provisioning completes. This window can also keep old resources around during manual validation before cleanup, depending on operation semantics.

Choose a period long enough for the application to start up, warm up, receive sample traffic, and surface errors. Too short a period can miss delayed failures; too long a period extends deployment duration and retention of old resources, affecting cost.

### 10.3. Rollback Configuration Example

Rollback configuration can be passed when creating a change set:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name release-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --rollback-configuration '{
    "RollbackTriggers": [
      {
        "Arn": "arn:aws:cloudwatch:ap-southeast-1:444455556666:alarm:orders-api-5xx-high",
        "Type": "AWS::CloudWatch::Alarm"
      }
    ],
    "MonitoringTimeInMinutes": 15
  }' \
  --region ap-southeast-1
~~~

The alarm ARN and account are examples. CloudFormation needs credentials/permissions to monitor the alarm and related resources. When updating rollback triggers on a stack, a new list may **replace** the stored trigger list; to keep old triggers, resubmit the full desired list. If no rollback triggers are passed, CloudFormation preserves existing configuration per API behavior.

### 10.4. Triggers Do Not Replace Post-Deployment Tests

CloudWatch alarms only check configured metrics/conditions. You still need:

- Smoke tests for critical APIs.
- Verification of database migrations/schema compatibility.
- Checks on queue consumers and event processing.
- Checks on IAM authorization and network paths.
- Business correctness checks using test transactions.

If an alarm fires, CloudFormation rolls back infrastructure; application data or external side effects require a separate runbook.

## 11. When Rollback Fails: UPDATE_ROLLBACK_FAILED

A stack enters **UPDATE_ROLLBACK_FAILED** when CloudFormation cannot restore one or more resources to their pre-update state. In this state, the stack cannot accept normal updates. You must recover the rollback to **UPDATE_ROLLBACK_COMPLETE** first before creating a new change set.

Example causes:

- An old resource was deleted outside CloudFormation and cannot be restored.
- Quotas are insufficient to restore the resource.
- A dependent resource fails to reach a stable state.
- Security/network/permission changes prevent CloudFormation from operating on the resource.
- A custom resource rollback handler errors or is non-idempotent.
- A nested stack rollback failed.
- Resource replacement/physical IDs were manually interfered with during the operation.

### 11.1. Investigation Workflow

1. Run `describe-stacks` to retrieve `StackStatusReason`.
2. Run `describe-stack-events` to find resources in `UPDATE_FAILED` during the `UpdateRollback` phase.
3. Run `describe-stack-resources` to identify logical IDs and physical IDs.
4. Inspect the actual resource in its corresponding service: does it still exist, has it drifted, what are its dependencies/quotas/permissions?
5. Fix external blockers per runbook, such as restoring a deleted resource or fixing quotas/network/policies.
6. Only once the cause is resolved, continue the rollback.

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --query 'Stacks[0].{Status:StackStatus,Reason:StackStatusReason}' \
  --output json

aws cloudformation describe-stack-events \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --max-items 100 \
  --output table
~~~

### 11.2. Continue Update Rollback

Once the cause is resolved, continue the rollback:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name orders-prod \
  --region ap-southeast-1
~~~

CloudFormation resumes recovering the stack from `UPDATE_ROLLBACK_FAILED`. Monitor events until the stack reaches `UPDATE_ROLLBACK_COMPLETE`. If the operation still fails, read the new reason and continue resolving the specific cause.

### 11.3. Skip Resources Only When Truly Necessary

If the blocker cannot be fixed, the API supports **ResourcesToSkip** to skip certain resources preventing rollback completion:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name orders-prod \
  --resources-to-skip AppDatabase \
  --region ap-southeast-1
~~~

Logical ID `AppDatabase` is just an example. Only specify resources that entered **UPDATE_FAILED during the UpdateRollback phase**, not resources that failed during the forward update. For nested stacks, use the format `NestedStackLogicalName.ResourceLogicalID`.

When a resource is skipped, CloudFormation marks it `UPDATE_COMPLETE` to continue the rollback. **The resource's actual state may no longer match the template/stack metadata.** Before the next update, you must reconcile the resource and template with a clear plan; otherwise, subsequent operations may fail or leave the stack hard to recover.

### 11.4. Force Rollback

The CLI supports force rollback so CloudFormation skips resources that failed rollback:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name orders-prod \
  --force-rollback \
  --region ap-southeast-1
~~~

Do not pass `--force-rollback` and `--resources-to-skip` together in the same request. Force rollback may skip more resources than the minimal set needed, including nested resources. Use it only after assessing consequences and establishing a reconciliation plan.

### 11.5. Reconciling After Skipping Resources

After the stack returns to `UPDATE_ROLLBACK_COMPLETE`:

1. Run drift detection on the stack and the skipped resources.
2. Compare actual physical resource properties against the template.
3. Decide whether to keep the actual resource, modify the resource to match the template, or update the template to reflect the desired state.
4. Back up data before any destructive changes.
5. Create a new change set, carefully review replacements/deletions, and reconcile step by step.
6. Close the incident only after stack state, template, and application behavior are consistent.

## 12. Stack Policy: Protecting Critical Resources from Unintended Updates

A **stack policy** is a JSON document defining which update actions CloudFormation is allowed to perform on stack resources. Its goal is to protect high-risk resources such as databases or storage volumes from unintended updates/replacements.

A stack policy:

- Is an additional protective layer during stack updates.
- Applies to users performing stack updates without distinguishing users via separate policy logic.
- Does not replace IAM policies and does not grant permissions to service APIs.
- Does not prevent users with direct permissions from modifying resources outside CloudFormation.
- Does not automatically protect data from all delete operations outside stack updates.

### 12.1. Example Protecting a Database

~~~json
{
  "Statement": [
    {
      "Effect": "Deny",
      "Action": "Update:*",
      "Principal": "*",
      "Resource": "LogicalResourceId/ProductionDatabase"
    },
    {
      "Effect": "Allow",
      "Action": "Update:*",
      "Principal": "*",
      "Resource": "*"
    }
  ]
}
~~~

Logical ID `ProductionDatabase` is an example. This policy denies updates to the database and allows updates to remaining resources. Review evaluation order and resource matching per stack policy documentation; never copy a sample policy into production without verifying actual logical IDs.

### 12.2. Temporarily Allowing an Update

If a change set needs to update a protected resource, the existing stack policy still applies when executing the change set. **You cannot pass a temporary stack policy override with `ExecuteChangeSet`.** You must update the stack policy beforehand or use a direct update workflow that supports a temporary policy override via the API.

After the update, restore the stack policy to continue protecting the resource. Relaxing the policy requires separate approval and auditing.

### 12.3. Stack Policies Do Not Replace IAM Least Privilege

IAM controls who can call CloudFormation APIs and service APIs; stack policies control resource update actions during a stack update. A principal with permission to delete a database directly via the RDS API will not be blocked by a stack policy. Use IAM/SCPs/resource policies to enforce real access control.

## 13. Termination Protection, DeletionPolicy, and UpdateReplacePolicy

These three mechanisms address different scenarios and do not substitute for each other.

| Mechanism | What does it protect? | When does it apply? |
|---|---|---|
| **Termination protection** | Prevents deleting the entire stack | When someone calls DeleteStack |
| **DeletionPolicy** | Specifies how a resource is handled when removed from the stack or the stack is deleted | Resource removal/stack deletion |
| **UpdateReplacePolicy** | Specifies how the old physical resource is handled after CloudFormation replaces a resource on update | Resource replacement |

### 13.1. Termination Protection

New stacks have termination protection disabled by default. When enabled, direct `DeleteStack` calls are rejected and the stack remains unchanged. For nested stacks, termination protection is controlled from the root stack.

~~~bash
aws cloudformation update-termination-protection \
  --stack-name orders-prod \
  --enable-termination-protection \
  --region ap-southeast-1
~~~

Termination protection **does not prevent a stack update from deleting or replacing resources** if a template update requires it. It only protects against stack deletion; it is not a blanket safeguard against all resource deletions.

### 13.2. DeletionPolicy

Example retaining a database when a stack is deleted:

~~~yaml
Resources:
  ProductionDatabase:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Retain
    Properties:
      DBInstanceClass: db.t3.medium
      Engine: postgres
      AllocatedStorage: 100
~~~

`DeletionPolicy` typically offers options such as `Delete`, `Retain`, and `Snapshot` for supported resource types. For RDS, `Snapshot` can preserve a snapshot before resource deletion; behavior and support depend on resource type. **Retain** keeps the physical resource, though CloudFormation no longer manages it as a resource inside the stack after removal.

### 13.3. UpdateReplacePolicy

When an update forces replacement, `UpdateReplacePolicy` decides how to handle the old physical resource after the new resource is created:

~~~yaml
Resources:
  ProductionDatabase:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Snapshot
    UpdateReplacePolicy: Snapshot
    Properties:
      DBInstanceClass: db.t3.medium
      Engine: postgres
      AllocatedStorage: 100
~~~

The example sets `Snapshot` for an RDS resource; verify resource type support and snapshot constraints. `UpdateReplacePolicy` differs from `DeletionPolicy`: one applies when a resource is removed/stack is deleted, while the other applies when an update replaces a physical resource.

### 13.4. Do Not Confuse Retain with Backup

Retain preserves the resource, but does not prove data can be restored, does not create new backups, and does not verify RPO/RTO. Snapshots also require checking status, encryption keys, retention, cross-account/Region copies, and restore tests.

## 14. Drift Detection Before and After Updates

**Drift** occurs when actual resource configuration differs from the template/parameter values managed by CloudFormation. For example, an engineer adds an ingress rule directly in the EC2 Security Group console without editing the template.

Drift can cause:

- Change sets not to reflect the full differences operators expect.
- Subsequent updates to overwrite out-of-template changes.
- Rollbacks to fail to restore out-of-band configurations.
- Stack deletions/updates to hit dependency or state mismatches.

### 14.1. Detecting Drift

~~~bash
aws cloudformation detect-stack-drift \
  --stack-name orders-prod \
  --region ap-southeast-1
~~~

The command returns a `StackDriftDetectionId`. Monitor progress:

~~~bash
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id DETECTION_ID \
  --region ap-southeast-1
~~~

Once detection finishes, inspect drifted resources:

~~~bash
aws cloudformation describe-stack-resource-drifts \
  --stack-name orders-prod \
  --stack-resource-drift-status-filters MODIFIED DELETED \
  --region ap-southeast-1 \
  --output table
~~~

### 14.2. Limitations of Drift Detection

CloudFormation only compares supported resource properties and values explicitly set in the template/parameters. Implicit defaults not explicitly declared may not be drift-checked. Drift detection on a root stack does not automatically detect drift in nested stacks; run it separately on child stacks.

An `IN_SYNC` status means supported and checked properties match the expected configuration; it does not prove all runtime behavior or application data is correct.

### 14.3. How to Handle Drift

1. Identify who changed it, when, and why.
2. Evaluate whether the out-of-band change needs to be kept.
3. If valid, update the template/parameters so desired state reflects the new configuration.
4. If invalid, use controlled CloudFormation updates or service APIs to return the resource to the desired state.
5. Re-run drift detection and review the change set before the next update.

Do not automatically "fix all drift" without understanding its operational purpose. A manual change might be an active mitigation protecting production; understand it before reverting.

## 15. Nested Stacks and Change Sets

Nested stacks let you split large templates into child templates with distinct responsibilities, such as networking, database, compute, and monitoring. The root stack references child templates via the `AWS::CloudFormation::Stack` resource type.

### 15.1. Change Sets for Nested Stacks

When creating a change set, CloudFormation can generate change sets for nested stacks. Nested change sets are often enabled by default; you can choose `Disabled` if you only want a change set for the current stack. When reviewing production, inspect both root and child change sets because a small parent change can cascade to many child resources.

### 15.2. Executing a Root Change Set

For nested stack changes, execute the root change set. CloudFormation executes the associated nested change sets if nested change sets were enabled during creation. Monitor events in both root and child stacks.

### 15.3. Rolling Back Nested Stacks

When rolling back a parent stack, CloudFormation also attempts to roll back child stacks. If rollback fails on a nested resource, identify the child stack name and logical ID. When skipping nested resources, the format is:

~~~text
NestedStackName.ResourceLogicalID
~~~

Example:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name WebInfra \
  --resources-to-skip WebInfra-Storage.Database \
  --region ap-southeast-1
~~~

The child stack name is an example; retrieve the exact nested stack physical name and logical ID from stack resources/events. Do not guess the child stack name from its logical ID.

## 16. CloudFormation Service Role and Deployment Identity

CloudFormation can assume a **service role** to call AWS service APIs on behalf of the person running a stack operation. This role is distinct from the IAM identity of the developer/CI invoking the CloudFormation API.

| Identity | Role |
|---|---|
| Developer/CI deploy role | Creates change sets, reviews/executes per granted permissions |
| CloudFormation service role | Assumed by CloudFormation to create/modify/delete EC2, RDS, IAM, S3, etc. |
| Application runtime role | Used by code in ECS/EKS/Lambda/EC2 during business execution |

### 16.1. Why Is the Service Role Important?

When a service role is attached to a stack, CloudFormation uses that role for subsequent operations. Someone with permission to operate on the stack can indirectly cause CloudFormation to use the attached role, even if that principal lacks permission to pass that role on every operation. Thus, the service role can become an **indirect privilege** for anyone allowed to update the stack.

### 16.2. Least Privilege for the CloudFormation Service Role

- Grant only the actions needed to manage the resource types in the stack.
- Scope resource ARNs and conditions where supported by services.
- Restrict `iam:PassRole` to specific runtime roles.
- Do not use `AdministratorAccess` as the default service role.
- Review the trust policy for `cloudformation.amazonaws.com`.
- Audit the role ARN on the stack and changes to permissions.
- Separate service roles for stacks/apps with differing permission scopes where appropriate.

### 16.3. Attaching a Role When Creating a Change Set

Example:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name release-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --role-arn arn:aws:iam::444455556666:role/orders-cloudformation-service-role \
  --region ap-southeast-1
~~~

The specified role ARN must align with the trust policy and permissions. If a stack already has an attached service role, operations may continue using the existing role when no new role is specified. Changing the service role requires review because it affects all future stack operations.

## 17. Parameters, Capabilities, and Dynamic References

A change set is only meaningful when its inputs match the intended release. A correct template with the wrong parameter can update the wrong account/resource, change an instance class unexpectedly, or point an application to the wrong endpoint.

### 17.1. Keeping Current Parameters When Appropriate

When updating a stack, you can retain previous parameter values with `UsePreviousValue`:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name update-app-capacity \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=InstanceType,ParameterValue=t3.medium \
  --region ap-southeast-1
~~~

Do not assume every parameter should stay unchanged. Review parameters with new defaults, `AllowedValues`, `NoEcho`, dynamic references, and conditions. Record approved parameter values in the deployment record.

### 17.2. Capabilities for IAM Resources and Macros

If the template creates/updates IAM resources:

- **CAPABILITY_IAM:** acknowledges the template contains IAM resources that do not use custom names in a way requiring another capability.
- **CAPABILITY_NAMED_IAM:** acknowledges the template contains IAM resources with custom names.
- **CAPABILITY_AUTO_EXPAND:** applies to macros/transforms when the workflow requires acknowledging auto expansion.

Example:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name update-iam-role \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-southeast-1
~~~

Capabilities are only an acknowledgment for CloudFormation to proceed; they **do not replace reviewing IAM policies**. Review trust policies, actions, resources, conditions, permission boundaries, and `iam:PassRole`.

### 17.3. Do Not Pass Plaintext Secrets via Parameters

Never pass database passwords/API tokens directly on the command line or in parameter overrides; they can appear in shell history, CI logs, or deployment records. Use dynamic references to Secrets Manager/SSM SecureString when supported by the resource property, or let the application fetch secrets at runtime using an IAM role.

Example dynamic reference:

~~~yaml
Resources:
  AppDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      MasterUsername: orders_admin
      MasterUserPassword: '{{resolve:secretsmanager:orders/prod/database:SecretString:password}}'
      Engine: postgres
      DBInstanceClass: db.t3.medium
      AllocatedStorage: 100
~~~

A dynamic reference may hide the secret value in the change set; that does not mean the secret value has been validated. Verify the secret exists, version/rotation behavior, KMS permissions, and resource property constraints.

### 17.4. Handling No-Op Change Sets

If the new template and parameters produce no resource changes, CloudFormation may return a `FAILED` change set with a reason indicating there are no updates. This is typically a no-op, not an infrastructure failure needing rollback. Verify:

- Is it the right stack/Region/account?
- Is the template artifact from the intended new commit?
- Were parameters preserved or overridden unintentionally?
- Did conditions/mappings prevent the change from applying?
- Does the resource already have the desired value?

Do not try to execute a no-op change set. If the intended change does not appear, fix the template/inputs and create a new change set.

## 18. Managing Obsolete Change Sets

A stack can have multiple change sets to compare options. Once you decide not to deploy an option, delete the change set so another operator cannot execute it by mistake.

~~~bash
aws cloudformation list-change-sets \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --output table

aws cloudformation delete-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1
~~~

After executing one change set, other change sets on the stack no longer match the new stack state and are deleted/marked obsolete by CloudFormation. If an update fails, create a new change set once the stack returns to an updatable state.

## 19. Update Failure Behavior and Partially Created Resources

In some workflows, CloudFormation lets you choose behavior when provisioning fails, including rolling back or preserving successfully provisioned resources for investigation. This option affects resource states and cleanup in subsequent operations.

### 19.1. Rollback on Update Failure

This is the common choice for production: failed resources are returned to the last known stable state if rollback succeeds. Monitor events to see which resources updated, which rolled back, and which errored.

### 19.2. Preserve Successfully Provisioned Resources

Preserving successfully provisioned resources can help when:

- Deploying a new stack or an independent group of resources.
- Inspecting resources created before the operation failed.
- Following a clear runbook to continue or clean up the remainder.

However, preserved resources may not be managed in the final state the team expects, can incur charges, and must be reconciled before the next operation. Do not choose preserve mode merely to avoid rollback in production.

### 19.3. Resources Without a Last Known Stable State

A newly created resource whose operation never reached a stable state may be deleted in the next stack operation. Read the status reason and CloudFormation failure options for your version; do not assume a resource visible in the console will survive the next operation.

## 20. Tiered Rollback and Recovery Procedures

Rollbacks should be classified before running commands:

| Level | Situation | Action |
|---|---|---|
| **A — Update failed, auto-rollback completed** | UPDATE_ROLLBACK_COMPLETE | Keep stack, investigate root cause, create new change set after fixing |
| **B — Rollback in progress** | UPDATE_ROLLBACK_IN_PROGRESS | Monitor events, wait for resource operations to finish |
| **C — Rollback failed** | UPDATE_ROLLBACK_FAILED | Resolve blocker, then ContinueUpdateRollback |
| **D — Resource cannot roll back** | A few resources failed rollback | Consider minimal ResourcesToSkip or approved force rollback |
| **E — Data/application side effects** | Stack rolled back, yet data or external systems changed | Execute separate application/data recovery runbook |

### 20.1. Do Not Delete the Stack to Cure UPDATE_ROLLBACK_FAILED

Deleting the stack can destroy remaining resources and data while failing to solve why rollback failed. First understand which resource errored, data retention policies, and physical IDs. Use `ContinueUpdateRollback` to return the stack to an operable state whenever possible.

### 20.2. Application Rollback vs. Infrastructure Rollback

CloudFormation template/resource rollback does not automatically roll back:

- Database schema migrations run by the application.
- Messages already sent to SQS/SNS/EventBridge.
- Data writes already committed to RDS/DynamoDB.
- External API side effects.
- DNS caches/client connection state.

Design backward-compatible deployments: expand/contract DB migrations, versioned event schemas, idempotency, and feature flags. When infrastructure reverts to the old version, the application/data layer must still operate safely.

### 20.3. Rollback Does Not Delete Retained Resources

`DeletionPolicy`/`UpdateReplacePolicy` and operation settings affect whether old/new resources remain after rollback. Check physical resources, snapshots, and costs after rollback; do not infer solely from stack status.

## 21. Cost and Operational Impact During Updates

A change set itself deploys no resources, yet execution can create new resources before deleting old ones. During replacement or blue/green cutover, costs may temporarily increase.

| Impact | Example | How to control |
|---|---|---|
| **Temporary double capacity** | RDS replacement or ASG rolling update | Estimate cost of two coexisting resources |
| **Snapshots/backups** | Snapshot before deleting RDS/EBS | Set retention, encryption, and cleanup owner |
| **Data transfer** | Replicate/copy data cross-AZ/Region | Account for transfer fees and sync duration |
| **Long monitoring window** | Rollback trigger monitoring keeping old resources | Pick an appropriate period, monitor cleanup |
| **Failed resources** | Preserved successful resources or incomplete rollback | Have a cleanup plan and owner |
| **Retries/operations** | Repeated change set/update attempts | Reduce deploy churn, fix root causes |

Do not choose replacement merely because the template diff looks neat. Weigh downtime, cost, data safety, and reversibility.

## 22. Runbook for Deploying a Stack Update

Sample runbook for a production update:

### Phase A — Preparation

1. Confirm the release commit, template artifact, and checksum/version.
2. Verify account, Region, stack ID, stack status, and CloudFormation service role.
3. Check stack drift and critical resources.
4. Confirm backups/snapshots, maintenance window, quotas, and dependencies.
5. Verify CloudWatch alarms, rollback triggers, and dashboards.
6. Run unit/template validation and pre-deployment policy checks.

### Phase B — Create and Review Change Set

1. Create a change set from versioned template/parameters.
2. Wait for `CREATE_COMPLETE` and `ExecutionStatus` `AVAILABLE`.
3. Inspect all resource actions, replacement flags, and property-level diffs.
4. Review IAM/security/network/database changes.
5. Review nested stack changes and rollback configuration.
6. Save the change set ARN/ID, commit, redacted parameters, and approval record.
7. If rejected, delete the change set.

### Phase C — Execute and Monitor

1. Execute the exact reviewed change set ID.
2. Monitor stack status and stack events.
3. If `UPDATE_FAILED`, read the resource reason and let rollback finish per policy.
4. If rollback triggers enter `ALARM`, verify application metrics and rollback events.
5. Do not start a new operation while the stack is updating/rolling back.

### Phase D — Verify or Recover

1. Upon `UPDATE_COMPLETE`, run smoke tests and verify application health.
2. Check physical IDs, outputs, DNS/endpoints, IAM permissions, and CloudWatch alarms.
3. Detect drift if needed; check resource replacements/retained resources.
4. If `UPDATE_ROLLBACK_COMPLETE`, keep the stack and create a new change set after fixing the root cause.
5. If `UPDATE_ROLLBACK_FAILED`, run the rollback recovery runbook; skip resources only with a reconciliation plan.
6. Record outcomes, incurred costs, action items, and release status.

~~~mermaid
flowchart TD
    PRE["Preflight: account, Region, stack, drift, backups"] --> CREATE["Create change set"]
    CREATE --> REVIEW["Review actions, replacements,<br/>security, nested stacks"]
    REVIEW --> APPROVE{"Approval"}
    APPROVE -->|"Reject"| DISCARD["Delete change set"]
    APPROVE -->|"Approve"| EXEC["Execute change set"]
    EXEC --> MON["Monitor stack events + alarms"]
    MON --> STATUS{"Terminal stack status"}
    STATUS -->|"UPDATE_COMPLETE"| TEST["Smoke tests / outputs / drift"]
    STATUS -->|"UPDATE_ROLLBACK_COMPLETE"| RCA["Root cause + new change set"]
    STATUS -->|"UPDATE_ROLLBACK_FAILED"| REC["Fix blocker + continue rollback"]
    REC --> STATUS
~~~

## 23. Scenario Exercises

### Scenario A — Changing DB Instance Class Reports Replacement

The team wants to scale up the DB instance class. The change set shows `AppDatabase` `Modify` with `Replacement: True`.

**Question:** Should we execute immediately since it is only a compute configuration change?

**Hint:** No. Check resource property update behavior and engine/instance compatibility. If replacement is truly required, prepare snapshot/restore, replication/cutover, endpoint migration, downtime window, backups, and a cost plan. Consider modifying in-place if supported by the resource type.

### Scenario B — Change Set Includes an Unrequested Resource Remove

A template update adds an SQS queue, yet the change set also shows `Remove` for an old IAM role the team did not mention.

**Question:** What should be done before executing?

**Hint:** Identify resource owner/dependencies, inspect conditions/logical IDs/template diff, and check whether other workloads assume the IAM role. Reject the change set until the removal is explained and separately approved.

### Scenario C — Change Set Creation Fails

`CREATE_FAILED` with a `StatusReason` indicating the template contains IAM resources without capability acknowledgment.

**Question:** Add `CAPABILITY_NAMED_IAM` and execute right away?

**Hint:** A capability only acknowledges that CloudFormation is permitted to process IAM resources. Review trust/permissions policies and resource scope first, then create a new change set with the right capability; do not treat capability as security approval.

### Scenario D — Update Fails and Rollback Succeeds

A security group update causes service health checks to fail. CloudFormation returns the stack to `UPDATE_ROLLBACK_COMPLETE`.

**Question:** Can the stack accept a new update immediately?

**Hint:** Usually the stack is back in an operable state, but you must read events, verify actual resource configuration, find the health check root cause, and create a new change set. Do not re-execute the old change set.

### Scenario E — UPDATE_ROLLBACK_FAILED Because Old Database Was Manually Deleted

A template update replaces an RDS database. The forward update fails; rollback tries to revert to the old physical database, but that DB was deleted outside CloudFormation.

**Question:** Why did rollback not complete?

**Hint:** CloudFormation cannot restore a physical resource that was deleted. Check snapshots/restore paths and resource dependencies; restore the blocker if possible, then run `ContinueUpdateRollback`. Skip the database only after understanding consequences and preparing a reconciliation plan.

### Scenario F — Skipping a Resource to Make the Stack Operable Again

The team uses `ResourcesToSkip` to bring the stack to `UPDATE_ROLLBACK_COMPLETE`, yet the template still describes database properties different from the actual DB.

**Question:** What is the next step?

**Hint:** Do not keep deploying. Detect drift on the database, compare physical state with the template, verify backup/data integrity, and reconcile. CloudFormation may mark the skipped resource `UPDATE_COMPLETE`, yet that does not prove the resource matches the template.

### Scenario G — Rollback Trigger Enters ALARM After Deployment

The stack update finishes resource provisioning, yet the 5xx alarm switches to `ALARM` during the 15-minute monitoring period.

**Question:** What does CloudFormation do and what must the team do?

**Hint:** The rollback trigger can cause CloudFormation to roll back the entire stack operation. Monitor events and alarms, check deployment/application logs, data side effects, and external systems. After rollback, verify app behavior and create a new change set after fixing.

### Scenario H — Clean Change Set Preview Fails at Runtime

The change set has no replacements, yet during execution a new resource hits a service quota exceeded error.

**Question:** Was the change set broken?

**Hint:** A change set only previews and pre-validates some failure causes; it does not guarantee resource operations will succeed. Check quotas, request an increase if needed, let state roll back, and retry with a new change set.

### Scenario I — Drift from an Emergency Manual Change

During an incident, an engineer adds an ingress rule directly on a security group. The next day CloudFormation updates the template and the rule is removed.

**Question:** What is the proper operational practice?

**Hint:** After an emergency change, record it and update template/parameter desired state or revert the manual change in a controlled way. Detect drift before updates so old templates do not accidentally overwrite active mitigations.

### Scenario J — Stack Policy Blocks Database Update

The change set is valid, yet execution fails because a stack policy denies `Update:*` for `ProductionDatabase`.

**Question:** Will adding IAM `AdministratorAccess` solve it?

**Hint:** No. A stack policy is a CloudFormation update guardrail, separate from IAM. Review the change, update the stack policy via an approved process or use a direct update workflow with a temporary policy override if appropriate; then restore the protective policy.

### Scenario K — Stack Has Termination Protection Yet Update Still Deletes a Resource

The team believes enabling termination protection prevents all resource deletions. A change set still proposes `Remove` for an S3 bucket from the stack.

**Question:** Why?

**Hint:** Termination protection prevents `DeleteStack`, not updates that delete or replace resources. You need `DeletionPolicy`, stack policies, IAM/resource policies, and change set review.

### Scenario L — Parent Stack Updates Yet Nested Child Stack Fails

A root stack change set updates network and database child stacks. The child database stack fails rollback.

**Question:** How do you specify a nested resource to skip?

**Hint:** Inspect root/child stack events and stack resource physical IDs. For `ResourcesToSkip`, use the nested stack physical name plus the logical resource ID; parent rollback orchestrates child stacks. Reconcile the entire hierarchy before the next update.

### Scenario M — Overly Broad CloudFormation Service Role

The CI deploy role only has `ExecuteChangeSet`, yet the stack has an attached service role with `AdministratorAccess`. A pipeline change set could create a new IAM policy.

**Question:** Why is this still a risk?

**Hint:** CloudFormation uses the attached service role for operations; permission to operate on the stack can indirectly leverage that role. Scope down the service role, review `iam:PassRole`, stack resource policies, and pipeline approvals.

### Scenario N — Non-Existent Alarm

A change set declares a rollback trigger ARN, yet the alarm was deleted or resides in a different Region.

**Question:** How might the operation behave?

**Hint:** If the trigger does not exist or is inaccessible, the stack operation can fail and roll back. Verify alarm ARNs, Region, account, permissions, and alarm state before deployment.

### Scenario O — Stack Rollback Succeeds Yet Orders Were Sent Twice

A custom resource or application hook sends an event to SQS before another resource fails. CloudFormation rolls back the stack, yet the message was already processed by a consumer.

**Question:** Does rollback retract the message?

**Hint:** No. Side effects outside CloudFormation require idempotency, deduplication, outbox/workflow compensation, and application recovery. Design custom resources with idempotent create/update/delete handlers.

## 24. Production Checklist

- [ ] Verified exact account, Region, stack ID, status, and CloudFormation service role.
- [ ] Template/parameters are versioned/committed and reviewed.
- [ ] Stack is not in an active operation or `UPDATE_ROLLBACK_FAILED`.
- [ ] Drift has been checked on critical resources.
- [ ] Backup/snapshot/restore plans exist for stateful resources.
- [ ] Change set created and reaches `CREATE_COMPLETE`/`AVAILABLE`.
- [ ] All `Add`/`Modify`/`Remove`/`Import` actions reviewed.
- [ ] `True`/`Conditional` replacements evaluated for downtime, data migration, endpoint cutover, and cost.
- [ ] IAM capabilities and IAM policy changes reviewed.
- [ ] Security groups, KMS, bucket policies, endpoint policies, and encryption reviewed.
- [ ] Nested stack change sets inspected.
- [ ] Parameters, dynamic references, capabilities, and role ARN match the release.
- [ ] Rollback triggers point to existing alarms in the right account/Region with active metrics.
- [ ] Monitoring period is sufficient for app warm-up and smoke tests.
- [ ] Stack policy protects critical resources and has an override procedure.
- [ ] Termination protection is enabled on stacks needing protection from `DeleteStack`.
- [ ] `DeletionPolicy`/`UpdateReplacePolicy` match data retention requirements.
- [ ] CloudFormation service role is least privilege; `iam:PassRole` is restricted.
- [ ] CI deploy identity is separated from the CloudFormation service role and application runtime role.
- [ ] Executed the exact approved change set; obsolete change sets cleaned up.
- [ ] Stack events and resource status reasons monitored until terminal status.
- [ ] `UPDATE_COMPLETE` verified via smoke tests and application metrics.
- [ ] `UPDATE_ROLLBACK_COMPLETE` investigated before attempting the next update.
- [ ] `UPDATE_ROLLBACK_FAILED` recovered per runbook; skipping resources is a last resort.
- [ ] After skipping resources, drift detected and template/physical state reconciled before the next update.
- [ ] Side effects of application/data migrations have compensation/idempotency plans.
- [ ] Retained/replaced resources and snapshots have owners/cleanup plans.
- [ ] Deployment results, stack events, change set ARN, approvals, and rollback decisions archived for audit.

## 25. Key Takeaways

**A change set is the review step before updating a CloudFormation stack.** Creating a change set does not modify resources; executing it starts the update. Read `Add`/`Modify`/`Remove`/`Import` actions, replacement flags, property-level differences, IAM/security changes, parameters, and nested stack changes. Change sets preview impact but do not guarantee the update will succeed.

When an update fails, CloudFormation normally rolls back automatically. **UPDATE_ROLLBACK_COMPLETE** indicates rollback finished and the stack can proceed after investigation. **UPDATE_ROLLBACK_FAILED** means rollback did not finish; fix the blocker and run `ContinueUpdateRollback`. `ResourcesToSkip`/force rollback should only be used when truly necessary, because skipped resources may not match the template and must be reconciled before the next update.

To reduce risk, use rollback triggers/CloudWatch alarms, stack policies, termination protection, `DeletionPolicy`/`UpdateReplacePolicy`, least-privilege CloudFormation service roles, and drift detection. Finally, remember that CloudFormation rollbacks do not undo database writes, messages, or external side effects; separate backups/restores, idempotency, smoke tests, and application runbooks are required.

### Official AWS Documentation for Reference

- [Update CloudFormation stacks using change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html) — creating, viewing, and executing change sets.
- [Create a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-create.html) — parameters, capabilities, and nested stacks.
- [Execute a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-execute.html) — execution behavior and stack policies.
- [Update stacks directly](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-direct.html) — update flow and rollback.
- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html) — change sets, drift, and rollback triggers.
- [Continue rolling back an update](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-continueupdaterollback.html) — UPDATE_ROLLBACK_FAILED, ResourcesToSkip, and force rollback.
- [Troubleshooting CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/troubleshooting.html) — causes of rollback failures.
- [Rollback triggers](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-rollback-triggers.html) — CloudWatch alarms and monitoring period.
- [RollbackConfiguration API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_RollbackConfiguration.html) — triggers and MonitoringTimeInMinutes.
- [Stack policies](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html) — protecting resources from unintended updates.
- [Termination protection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html) — preventing stack deletion.
- [Drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — detecting out-of-template changes.
- [Detect drift on a stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-stack.html) — drift detection operations.
- [CloudFormation UpdateStack API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html) — RoleARN, rollback configuration, and stack policy.
