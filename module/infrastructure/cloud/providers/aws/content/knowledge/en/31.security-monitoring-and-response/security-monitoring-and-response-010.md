# Automating Response with EventBridge and Systems Manager

When an incident occurs, operations teams must recognize the signal, identify affected resources, select an appropriate action, and record the outcome. If every step waits for an on-call engineer to open the console, locate the right resource, and run manual commands, response time lengthens and execution easily becomes inconsistent.

Amazon EventBridge receives events from AWS services, applications, and partners, filters them using rules, and routes them to processing targets. AWS Systems Manager provides Automation runbooks to orchestrate multi-step workflows, Run Command to execute commands on managed nodes, and OpsCenter to record, triage, and track operational work. Combining both services builds repeatable, permission-controlled, and auditable response workflows.

This lesson belongs to the **Security Monitoring and Response** chapter of the CLOUD_PROVIDERS_AWS module. The module helps learners select and operate AWS services securely, with observability, resilience, and cost control.

## Learning Objectives

After this lesson, you will be able to:

- Describe the flow from source events through EventBridge to actions in Systems Manager.
- Write event patterns that trigger only when events satisfy handling conditions.
- Choose among Automation, Run Command, and OpsCenter based on response complexity.
- Pass event data into runbook parameters using Input Transformer.
- Distinguish the IAM role EventBridge uses to invoke targets from the IAM role Automation uses to modify resources.
- Design responses with blast-radius controls, idempotency against duplicate execution, and failure-handling paths.
- Monitor status, troubleshoot errors, and test workflows before enabling production automation.

## 1. Event-Driven Response Architecture

A baseline workflow has four parts:

1. **Detection source:** GuardDuty, Security Hub CSPM, AWS Config, CloudWatch Alarms, EC2, other AWS services, or internal applications.
2. **Routing:** EventBridge receives events on an event bus, matches rule event patterns, and selects targets.
3. **Execution:** Systems Manager Automation runs a multi-step runbook, Run Command runs a command document on managed nodes, or OpsCenter creates an OpsItem for investigation.
4. **Monitoring:** EventBridge receives status events from Systems Manager; CloudWatch metrics, CloudTrail, SNS, and OpsCenter support monitoring, alerting, and auditing.

~~~mermaid
flowchart TD
    A["GuardDuty / Security Hub / CloudWatch / AWS service"] --> B["EventBridge event bus"]
    B --> C{"Event pattern matches?"}
    C -->|No| D["Do not invoke target"]
    C -->|Yes| E["EventBridge rule"]
    E --> F["Systems Manager Automation"]
    E --> G["Systems Manager Run Command"]
    E --> H["Systems Manager OpsCenter"]
    F --> I["Runbook: inspect, approve, remediate"]
    G --> J["Command document on managed nodes"]
    H --> K["OpsItem: investigate and assign"]
    I --> L["Execution status"]
    J --> L
    L --> M["EventBridge / CloudWatch / CloudTrail / notifications"]
~~~

EventBridge handles receiving, filtering, and routing events. It does not decide on its own whether a remediation action is safe. Inspection logic, approval gates, action permissions, and recovery steps must be designed into runbooks or operational workflows.

A successful EventBridge delivery does not mean the runbook finished. Successful target invocation only indicates the target call was accepted; the outcome of each Automation step must be tracked separately.

## 2. Role of EventBridge in the Workflow

### 2.1. Event Bus, Events, and Rules

An event bus receives events. Events emitted by AWS services in an account go to the account and Region's **default event bus**. You can create custom event buses to ingest application events or isolate processing streams. EventBridge also supports events from SaaS partners.

A typical event contains these fields:

| Field | Meaning |
|---|---|
| `version` | Event structure version |
| `id` | Event identifier |
| `source` | Service or application emitting the event, e.g., `aws.guardduty` |
| `detail-type` | Event type, e.g., `GuardDuty Finding` |
| `account` | AWS account emitting the event |
| `region` | Associated Region |
| `time` | Event emission timestamp |
| `resources` | Associated resource ARNs |
| `detail` | Event-specific payload |

A rule uses an event pattern to specify which events to forward. Patterns mirror event structure and can filter on `source`, `detail-type`, account, Region, or fields inside `detail`.

For example, a rule may handle only high-severity findings involving EC2 instances inside a specific production account. The more specific the rule, the lower the risk of invoking the wrong runbook.

### 2.2. AWS Service Events and CloudTrail

Some services emit service events directly to EventBridge. GuardDuty emits `GuardDuty Finding` events; Systems Manager emits Automation and Run Command status events; EC2 emits instance state-change events.

Some API operations lack dedicated service events. In those cases, build rules against API events recorded via CloudTrail, typically with `detail-type` set to `AWS API Call via CloudTrail`. This requires CloudTrail to record the relevant event types and the event pattern to match the exact CloudTrail event structure.

Do not assume every service carries identical event delivery guarantees. AWS publishes delivery semantics per service event type—some are best-effort and some are durable. Verify the delivery guarantee of critical sources before treating EventBridge as the sole trigger for a response workflow.

For GuardDuty, new findings with unique IDs are sent in near real-time. Subsequent occurrences of the same finding are aggregated into update events; by default GuardDuty batches updates over six hours, and administrator accounts can choose 15-minute, one-hour, or six-hour intervals. Consequently, a single finding can emit multiple events over time while keeping the same finding ID. Idempotency design should key off the finding ID alongside the action and current resource state.

Findings automatically archived by a GuardDuty suppression rule are not sent to EventBridge. If a response workflow must receive those findings, review suppression rules and excluded event scopes.

### 2.3. Event-Based Rules vs. Schedules

Event-pattern rules suit immediate responses when changes or new findings occur. EventBridge rules also support `rate` and `cron` schedules; for new schedules, consider EventBridge Scheduler when one-time schedules, time zones, or independent schedule management are needed.

Do not use periodic schedules in place of event-driven responses when the goal is reacting promptly to a specific incident.

## 3. Choosing the Right Systems Manager Target

EventBridge can invoke many target types. With Systems Manager, the three common choices are Automation, Run Command, and OpsCenter.

| Target | When to Use | Expected Output |
|---|---|---|
| **Automation** | Multi-step workflows, branching, state checks, approvals, AWS API calls, or orchestrating multiple runbooks | An Automation execution with step-by-step status and history |
| **Run Command** | Running a command document across one or more EC2/hybrid managed nodes | One or more command invocations on managed nodes |
| **OpsCenter** | Creating operational work items to investigate, prioritize, assign, and link runbooks | An OpsItem with status, linked resources, and handling history |

### 3.1. Systems Manager Automation

Automation executes an Automation document, commonly called a *runbook*. A runbook can:

- Invoke AWS APIs via `aws:executeAwsApi`.
- Run Python or PowerShell scripts via `aws:executeScript`.
- Run commands on managed nodes via `aws:runCommand`.
- Branch conditionally via `aws:branch`.
- Wait for resource states via `aws:waitForAwsResourceProperty`.
- Pause for human approval via `aws:approve`.
- Invoke nested runbooks via `aws:executeAutomation`.

Automation fits conditional workflows, such as inspecting a finding, verifying the resource, preserving evidence, awaiting approval, and then isolating the resource.

AWS provides built-in runbooks such as `AWS-CreateImage`, `AWS-StopEC2Instance`, and `AWS-QuarantineEC2Instance`. Read a runbook's content and permission list before using it, as short names do not convey full impact.

### 3.2. Systems Manager Run Command

Run Command dispatches a command document to managed nodes. EventBridge calls `SendCommand` on your behalf. Targets must specify resources by instance ID or tag; EventBridge's Run Command configuration supports one to five target groups.

Run Command suits straightforward tasks such as checking service status, inspecting disk space, or running standardized scripts. If branching, approvals, multi-step API calls, or structured error handling are needed, encapsulate the logic inside an Automation runbook.

Managed nodes must be registered with Systems Manager, run an active SSM Agent, hold a valid IAM instance profile or authentication mechanism, and reach Systems Manager endpoints. Creating an EventBridge rule does not install agents or register hosts automatically.

### 3.3. Systems Manager OpsCenter

OpsCenter creates an OpsItem for operations teams to investigate and resolve. An OpsItem tracks fields such as title, priority, description, source, related resources, and status.

Use EventBridge to create an OpsItem when:

- GuardDuty or Security Hub emits findings needing human analysis.
- An Automation execution fails.
- A service experiences throttling or a resource enters an abnormal state.
- An event must be tracked as an accountable work item.

OpsCenter can associate runbooks with an OpsItem so on-call engineers can open the item, inspect related data, and launch Automation. OpsCenter also supports duplicate OpsItem detection; configure a deduplication string on the rule when one incident may emit multiple events. OpsItems incur charges per Systems Manager pricing, so tight event patterns and deduplication also help control OpsItem volume.

## 4. Designing an Automation Runbook

Automation runbooks are authored in YAML or JSON. Documents declare parameters, an execution role, and a list of `mainSteps`.

A runbook typically includes:

- `schemaVersion`: Automation document schema version, commonly `'0.3'`.
- `assumeRole`: IAM role Automation assumes to call AWS services.
- `parameters`: inputs and value constraints.
- `mainSteps`: sequential or branching execution steps.

Example runbook skeleton:

~~~yaml
---
description: "Framework for inspecting a resource before remediation"
schemaVersion: '0.3'
assumeRole: '{{ AutomationAssumeRole }}'
parameters:
  AutomationAssumeRole:
    type: String
    description: "ARN of the role used by Automation"
  InstanceId:
    type: String
    description: "EC2 instance to inspect"
    allowedPattern: '^i-[0-9a-f]+$'
mainSteps:
  - name: inspectInstance
    action: aws:executeAwsApi
    onFailure: Abort
    inputs:
      Service: ec2
      Api: DescribeInstances
      InstanceIds:
        - '{{ InstanceId }}'
    outputs:
      - Name: InstanceState
        Selector: '$.Reservations[0].Instances[0].State.Name'
        Type: String
  - name: checkInstanceState
    action: aws:assertAwsResourceProperty
    onFailure: Abort
    inputs:
      Service: ec2
      Api: DescribeInstances
      InstanceIds:
        - '{{ InstanceId }}'
      PropertySelector: '$.Reservations[0].Instances[0].State.Name'
      DesiredValues:
        - running
~~~

This skeleton illustrates declaring parameters, calling an API, and asserting state. When building real runbooks, cross-check API names, request/response structures, and selectors against the action's documentation; valid YAML can still fail if API inputs or JSONPath selectors are wrong.

### 4.1. Designing Safe Parameters

Parameters should accurately describe required inputs and constrain accepted values:

- Use `allowedValues` for fixed choice lists.
- Use `allowedPattern` to validate ID or name formats.
- Use `StringList` when a list of values is needed.
- Set safe defaults if the runbook may be launched manually.
- Never pass passwords, tokens, or sensitive data in event payloads unnecessarily.
- Never accept an arbitrary ARN from an event and use it directly as the target of a privileged action.

Events can carry service-supplied or user-supplied data. Validate parameters and verify the target resource before using those values to modify infrastructure.

### 4.2. Controlling Step Failures

Attributes such as `onFailure`, `onCancel`, `maxAttempts`, `timeoutSeconds`, and `nextStep` define how Automation reacts when a step fails or times out.

For example:

- Use `Abort` when a critical verification step fails; do not proceed to resource-modifying steps.
- Use `maxAttempts` for operations prone to transient errors that are safe to retry.
- Use `aws:waitForAwsResourceProperty` to wait for state transitions rather than assuming an API return implies completion.
- Record helpful outputs so on-call engineers see which steps ran and which resources changed.

Never infinitely retry steps whose side effects are unsafe to repeat, such as creating multiple snapshots or issuing repeated configuration changes.

## 5. Connecting EventBridge to Automation

When creating an EventBridge rule, choose the event bus, event pattern, and target **Systems Manager Automation** with the desired runbook. For runbooks with required parameters, supply all values; if parameters are missing, the rule may still save yet fail to invoke the target when events arrive.

Two methods exist for passing data:

- **Constant input:** passes static values into runbook parameters. Suits targets operating on a fixed resource or configuration.
- **Input Transformer:** extracts fields from events via JSONPath and constructs JSON input matching runbook parameters. Suits events varying per resource.

For instance, EC2 events contain `detail.instance-id`. Input Transformer can extract the instance ID and pass it as `InstanceId` to the runbook. Do not confuse Input Transformer with `Input` on a Run Command target: Run Command uses `RunCommandParameters` to specify target nodes and `Input` to pass document name and parameters.

## 6. Example: Responding to a GuardDuty Finding on EC2

Suppose GuardDuty detects suspicious behavior involving an EC2 instance. The workflow must:

1. Accept only findings meeting a chosen severity threshold.
2. Handle only findings whose resource is an EC2 instance.
3. Extract the instance ID from the event.
4. Run a runbook to inspect and isolate the instance.
5. Record status and notify the security team.

GuardDuty emits events with `source` set to `aws.guardduty` and `detail-type` set to `GuardDuty Finding`. The `detail` object holds a finding, including severity, ID, finding type, and resource details.

### 6.1. Event Pattern for Filtering Findings

The example below selects findings with severity 7 or higher whose resource is an EC2 instance. GuardDuty severity ranges from 1.0 to 10.0; pick thresholds aligned with your organization's triage policy.

~~~json
{
  "source": [
    "aws.guardduty"
  ],
  "detail-type": [
    "GuardDuty Finding"
  ],
  "account": [
    "123456789012"
  ],
  "region": [
    "ap-southeast-1"
  ],
  "detail": {
    "severity": [
      {
        "numeric": [
          ">=",
          7
        ]
      }
    ],
    "resource": {
      "resourceType": [
        "Instance"
      ],
      "instanceDetails": {
        "instanceId": [
          {
            "exists": true
          }
        ]
      }
    }
  }
}
~~~

Replace account and Region with your actual scope. This pattern only illustrates filtering by severity and resource type; production rules may add filters on finding type, accounts, governance tags, or resource groups approved for automated handling.

Use EventBridge Sandbox to test patterns against sample GuardDuty events before creating rules. Verify both events that should match and events that should be excluded.

### 6.2. Mapping Event Data

GuardDuty places the instance ID at `detail.resource.instanceDetails.instanceId`. For a runbook accepting `InstanceId`, Input Transformer can extract this field. Example:

**Input paths**

~~~json
{
  "instanceId": "$.detail.resource.instanceDetails.instanceId",
  "findingId": "$.detail.id",
  "findingType": "$.detail.type"
}
~~~

**Input template**

~~~json
{
  "InstanceId": [
    <instanceId>
  ],
  "FindingId": [
    <findingId>
  ],
  "FindingType": [
    <findingType>
  ],
  "AutomationAssumeRole": [
    "arn:aws:iam::123456789012:role/AutomationQuarantineRole"
  ],
  "IsolationSecurityGroup": [
    "Quarantine-EC2"
  ]
}
~~~

`FindingId`, `FindingType`, `AutomationAssumeRole`, and `IsolationSecurityGroup` are parameters of the custom runbook in this example. If targeting an AWS-managed runbook, pass only the parameters actually declared by that document. Input Transformer substitutes placeholders with JSONPath values; never add fields outside the runbook schema.

### 6.3. Selecting an Isolation Runbook

AWS provides the `AWS-QuarantineEC2Instance` runbook. This runbook:

- Collects instance details.
- Checks whether the instance belongs to an Auto Scaling group.
- Creates a snapshot of the root volume and waits for snapshot completion.
- Attaches the specified isolation security group to the instance.

The isolation security group blocks inbound and outbound traffic. The runbook verifies the instance does not belong to an Auto Scaling group. If the instance is managed by Auto Scaling, the runbook's precondition fails; design a dedicated approved workflow for Auto Scaling lifecycle handling rather than assuming the runbook will detach the instance or adjust desired capacity.

The runbook outputs the root volume snapshot ID and the ID/name of revoked security groups. Save these outputs in the OpsItem or incident record so responders have reference data when restoring networking. If the instance has additional EBS volumes requiring forensic preservation, add separate snapshot steps for them.

Therefore, treat automated isolation as a high-impact action. For critical environments, route findings to OpsCenter first, require approval, or allow automated isolation only for instances tagged or grouped as approved. Verify permissions, RDP/SSH settings, and recovery paths before enabling.

### 6.4. Adding an Approval Step

If an on-call engineer must approve before isolation, create a wrapper runbook containing an `aws:approve` step, then invoke `AWS-QuarantineEC2Instance` via `aws:executeAutomation`.

~~~yaml
---
description: "Approve before isolating an EC2 instance with a GuardDuty finding"
schemaVersion: '0.3'
assumeRole: '{{ AutomationAssumeRole }}'
parameters:
  AutomationAssumeRole:
    type: String
    description: "Role used by Automation"
  InstanceId:
    type: String
    allowedPattern: '^i-[0-9a-f]+$'
  FindingId:
    type: String
  FindingType:
    type: String
  IsolationSecurityGroup:
    type: String
  ApprovalTopicArn:
    type: String
mainSteps:
  - name: approveContainment
    action: aws:approve
    timeoutSeconds: 3600
    onFailure: Abort
    inputs:
      NotificationArn: '{{ ApprovalTopicArn }}'
      Message: 'GuardDuty finding {{ FindingId }} ({{ FindingType }}) requires review to isolate EC2 {{ InstanceId }}.'
      MinRequiredApprovals: 1
      Approvers:
        - arn:aws:iam::123456789012:role/SecurityIncidentApprover
  - name: quarantineInstance
    action: aws:executeAutomation
    timeoutSeconds: 7200
    onFailure: Abort
    inputs:
      DocumentName: AWS-QuarantineEC2Instance
      RuntimeParameters:
        InstanceId:
          - '{{ InstanceId }}'
        IsolationSecurityGroup:
          - '{{ IsolationSecurityGroup }}'
        AutomationAssumeRole:
          - '{{ AutomationAssumeRole }}'
~~~

This is an illustrative template; substitute ARNs, parameters, and permissions for your account. The SNS topic used for approvals must meet Automation requirements; approval topic names use the prefix `Automation`. Approvers must hold `ssm:SendAutomationSignal` on the execution and permissions needed to view Automation. The `aws:approve` action does not support multi-account and multi-Region Automation executions.

Child runbooks run in the context of the principal that initiated the parent Automation execution. If the child runbook declares `AutomationAssumeRole`, the initiating principal must hold `iam:PassRole` for that role; it also needs `ssm:StartAutomationExecution` on the child document. Thus, when EventBridge is the initiator, the invocation role must hold permissions to start both the wrapper and child runbooks. The child runbook's `AutomationAssumeRole` parameter must be passed explicitly in `RuntimeParameters`.

## 7. Separating IAM Roles

An auditable design typically separates two roles:

1. **EventBridge invocation role:** EventBridge assumes this role to invoke the target, such as starting an Automation execution. For Systems Manager Automation targets, the trust policy permits `events.amazonaws.com` and `ssm.amazonaws.com`.
2. **Automation assume role:** Systems Manager assumes this role to operate on EC2, EBS, Auto Scaling, or related services. The trust policy permits `ssm.amazonaws.com`.

Do not grant EC2 modification permissions to the EventBridge invocation role if it only needs to start a runbook. Resource-modifying permissions belong on the Automation role and should be scoped to the exact runbook.

For Systems Manager Automation targets, AWS guidance requires the EventBridge invocation role's trust policy to allow both `events.amazonaws.com` and `ssm.amazonaws.com`. That role still only needs permissions to start Automation and pass the Automation role. The Automation assume role is a separate role assumed by Systems Manager to modify resources, trusting `ssm.amazonaws.com`.

### 7.1. EventBridge Role Trust Policy

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "events.amazonaws.com",
          "ssm.amazonaws.com"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This role's permissions policy should allow `ssm:StartAutomationExecution` on the specified runbooks and `iam:PassRole` for the Automation role. Restrict resources to specific document and role ARNs.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StartApprovedRunbook",
      "Effect": "Allow",
      "Action": "ssm:StartAutomationExecution",
      "Resource": [
        "arn:aws:ssm:ap-southeast-1:123456789012:document/GuardDutyQuarantineWithApproval",
        "arn:aws:ssm:ap-southeast-1::document/AWS-QuarantineEC2Instance",
        "arn:aws:ssm:ap-southeast-1:123456789012:automation-execution/*"
      ]
    },
    {
      "Sid": "PassOnlyAutomationRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::123456789012:role/AutomationQuarantineRole",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ssm.amazonaws.com"
        }
      }
    }
  ]
}
~~~

In IAM policies, official Systems Manager examples grant `ssm:StartAutomationExecution` on `document` and `automation-execution` resource types. EventBridge's target `Arn` field uses the `automation-definition` ARN format; these are two distinct ARN contexts, so align IAM policies with Systems Manager examples and target configurations with EventBridge documentation.

### 7.2. Automation Role Trust Policy

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

For `AWS-QuarantineEC2Instance`, the runbook documentation lists required permissions including:

- `autoscaling:DescribeAutoScalingInstances`
- `autoscaling:DetachInstances`
- `ec2:CreateSecurityGroup`
- `ec2:CreateSnapshot`
- `ec2:DescribeInstances`
- `ec2:DescribeSecurityGroups`
- `ec2:DescribeSnapshots`
- `ec2:ModifyInstanceAttribute`
- `ec2:RevokeSecurityGroupEgress`
- `ec2:RevokeSecurityGroupIngress`

This is a reference list for that specific runbook, not a boilerplate policy to attach verbatim to every Automation. For wrapper runbooks with approvals, the Automation role needs `sns:Publish` on the approval SNS topic. Permissions for `ssm:StartAutomationExecution` on child documents and `iam:PassRole` to pass `AutomationAssumeRole` belong to the principal starting the parent Automation; in this example, that is the EventBridge invocation role. Read the exact runbook version in use and verify resource-level permissions, IAM conditions, SNS approval permissions, and child runbook permissions. Avoid attaching `AdministratorAccess` merely to make Automation work.

## 8. Configuring EventBridge Rules with AWS CLI

The following examples use two JSON files prepared by the implementer:

- `guardduty-ec2-high-pattern.json`: event pattern from section 6.1.
- `guardduty-automation-target.json`: target and Input Transformer.

Example target file:

~~~json
[
  {
    "Id": "guardduty-quarantine",
    "Arn": "arn:aws:ssm:ap-southeast-1:123456789012:automation-definition/GuardDutyQuarantineWithApproval",
    "RoleArn": "arn:aws:iam::123456789012:role/EventBridgeInvokeAutomationRole",
    "InputTransformer": {
      "InputPathsMap": {
        "instanceId": "$.detail.resource.instanceDetails.instanceId",
        "findingId": "$.detail.id",
        "findingType": "$.detail.type"
      },
      "InputTemplate": "{\"InstanceId\":[<instanceId>],\"FindingId\":[<findingId>],\"FindingType\":[<findingType>],\"IsolationSecurityGroup\":[\"Quarantine-EC2\"],\"ApprovalTopicArn\":[\"arn:aws:sns:ap-southeast-1:123456789012:Automation-IR-Approval\"],\"AutomationAssumeRole\":[\"arn:aws:iam::123456789012:role/AutomationQuarantineRole\"]}"
    }
  }
]
~~~

Create the rule and attach the target:

~~~bash
aws events put-rule \
  --name GuardDutyHighEC2Finding \
  --event-pattern file://guardduty-ec2-high-pattern.json \
  --state ENABLED \
  --description "Route high-severity EC2 GuardDuty findings to Systems Manager Automation"

aws events put-targets \
  --rule GuardDutyHighEC2Finding \
  --targets file://guardduty-automation-target.json
~~~

The `put-targets` response should report `FailedEntryCount` as 0. If errors occur, inspect `FailedEntries` to see which target failed to attach. Recheck the rule, role ARN, document ARN, Input Transformer, and required parameters.

If invoking a built-in runbook directly, AWS-owned document ARNs typically use `*` as the account component, e.g., `arn:aws:ssm:ap-southeast-1:*:automation-definition/AWS-QuarantineEC2Instance`. Verify the exact ARN and parameter schema in the runbook documentation for your target Region.

## 9. EventBridge Invoking Run Command

For simple tasks, EventBridge can invoke Run Command directly. The target requires:

- Command document ARN.
- IAM role allowing `ssm:SendCommand` on the document and permitted instances.
- `RunCommandParameters` specifying instance IDs or tags.
- `Input` containing document name, version if needed, and `Parameters` map.

Abbreviated target structure example:

~~~json
{
  "Id": "check-web-service",
  "Arn": "arn:aws:ssm:ap-southeast-1:123456789012:document/AWS-RunShellScript",
  "RoleArn": "arn:aws:iam::123456789012:role/EventBridgeRunCommandRole",
  "Input": "{\"DocumentName\":\"AWS-RunShellScript\",\"Parameters\":{\"commands\":[\"systemctl is-active nginx\"]}}",
  "RunCommandParameters": {
    "RunCommandTargets": [
      {
        "Key": "tag:Environment",
        "Values": [
          "development"
        ]
      }
    ]
  }
}
~~~

This example checks service status on Linux managed nodes tagged `Environment=development`. Before running, ensure target tags are strictly governed and cannot be accidentally applied to production hosts.

The EventBridge role for Run Command requires `ssm:SendCommand` on the command document and target instances/managed instances. When targeting by tag, use IAM resource-tag conditions to narrow the machine set. For command documents capable of modifying systems, review scripts and parameter constraints just as you would review a software change.

The trust policy of the Run Command target role must allow `events.amazonaws.com` to assume it. When targeting by tag, the policy must restrict permissions on both the command document and the allowed set of tagged managed nodes; never grant `ssm:SendCommand` across all instances when the workflow serves only a specific group.

## 10. Creating an OpsItem Instead of Immediate Auto-Remediation

Not every finding can be safely resolved by an automated action. When root cause is unclear, the resource may serve critical systems, or an action risks data loss, create an OpsItem for on-call investigation.

A typical workflow:

1. EventBridge filters findings by severity and resource type.
2. The rule routes events to OpsCenter to create an OpsItem.
3. The OpsItem records the resource, finding, description, and priority.
4. On-call staff inspect CloudTrail, CloudWatch, GuardDuty, and resource details.
5. Responders select an appropriate runbook and execute it after verification.
6. After remediation, update the OpsItem status to Resolved and record root cause details.

OpsCenter integrates with EventBridge to create OpsItems automatically. Use a deduplication string when multiple events may represent the same incident—for example, the same resource and finding type within a timeframe.

## 11. Reliability: Retries, DLQs, and Duplicate Events

### 11.1. Retrying Failed Target Invocations

EventBridge rule targets have a retry policy. For classic rule targets, by default EventBridge retries delivery for up to 24 hours and up to 185 attempts with exponential backoff and jitter; whichever limit is reached first ends retries. Event retention age and maximum retry attempts can be configured as needed.

Without a dead-letter queue (DLQ), events failing after retries exhaust may be dropped. Configure an SQS DLQ for critical targets and monitor messages sent to the DLQ.

Do not confuse classic rule target retries with retry policies of newer EventBridge subscriber types on custom event buses; each model has distinct defaults. Always check the event bus type and target mechanism in use.

### 11.2. Designing Idempotency

An event may be redelivered, or a rule may fire multiple times for the same finding. Response actions must therefore be safe when repeated.

Common approaches:

- Combine `event.id` or GuardDuty `findingId` with resource ID and action to build a processing key.
- Record processed state using DynamoDB conditional writes or an equivalent locking mechanism.
- Before modifying a resource, read its current state and act only if preconditions still hold.
- Attach tags/metadata with the incident ID to aid correlation.
- Use standardized naming for resources, snapshots, and tickets to detect already-created outputs.

Never assume a finding emits only one event or that a target runs strictly once.

### 11.3. Preventing Infinite Loops

A rule can re-trigger itself if a remediation action generates an event matching the rule's own pattern. For example, a rule watching security group changes that runs a runbook modifying security groups may keep catching events generated by the runbook itself.

To prevent loops:

- Filter precisely on `source`, `detail-type`, and specific state fields.
- Match only transitions from healthy/acceptable states into states requiring attention.
- Exclude automation-driven changes or tag changes to identify originators.
- Avoid overly broad rules matching every event from a service when only one event type is needed.
- Monitor invocation counts and costs after enabling rules.

### 11.4. Handling DLQs and Replays

DLQs retain records of undelivered events for investigation. Before redriving or replaying, verify current resource state and incident status; replaying an old event can re-execute an action that has already been resolved.

If an SQS DLQ is encrypted with a customer-managed KMS key, the key policy must allow EventBridge to use the key per AWS service guidance. The queue policy must also permit the specific EventBridge rule to send messages.

## 12. Monitoring Automation Outcomes

EventBridge emits metrics for target delivery, while Systems Manager records Automation execution progress. These two signal groups answer different questions:

- **EventBridge:** Did the event match the rule and reach the target?
- **Systems Manager:** Did the runbook start and complete its remediation steps?

EventBridge metrics to monitor:

| Metric | Meaning |
|---|---|
| `InvocationAttempts` | Total times EventBridge attempted to invoke targets, including retries |
| `SuccessfulInvocationAttempts` | Number of successful target invocations |
| `RetryInvocationAttempts` | Number of retries during target delivery |
| `FailedInvocations` | Permanently failed invocations; excludes in-progress retries, retry successes, or counts already captured in `DeadLetterInvocations` |
| `DeadLetterInvocations` | Times a rule failed to invoke a target for an event; may include EventBridge blocking infinite loops |
| `InvocationsSentToDlq` | Events successfully forwarded to a DLQ |
| `InvocationsFailedToBeSentToDlq` | Times EventBridge failed to send an invocation to the DLQ, typically due to permissions, queue issues, or size limits |
| `IngestionToInvocationSuccessLatency` | Latency from event ingestion to successful target invocation |

Create CloudWatch Alarms when `FailedInvocations` rises, DLQ messages appear, or target delivery latency breaches thresholds. Combine `SuccessfulInvocationAttempts` and `InvocationAttempts` to measure delivery success rate.

EventBridge metrics are emitted to CloudWatch on a best-effort basis; they are useful for tracking trends and spotting anomalies, not as an exhaustive per-event audit ledger.

Systems Manager emits events when an Automation execution or step changes state. Create dedicated rules matching:

- `source`: `aws.ssm`
- `detail-type`: `EC2 Automation Execution Status-change Notification` or `EC2 Automation Step Status-change Notification`
- `detail.Status`: `Failed`, `Success`, `TimedOut`, `Canceled`, or other tracked statuses.

When Automation fails, notify SNS, create an OpsItem, or trigger a fallback workflow. Scope patterns to specific statuses and runbooks so notification rules do not react to every Automation in the account.

Systems Manager status events are emitted best-effort. Use Automation execution history and CloudTrail as authoritative investigative sources rather than relying solely on status events to confirm outcomes.

### 12.1. Preserving Audit Trails

Use multiple log sources according to their strengths:

- **Systems Manager Automation execution history:** per-execution status, steps, inputs, outputs, and errors.
- **CloudWatch Logs:** outputs of `aws:executeScript` steps when logging is configured.
- **CloudTrail:** records APIs such as `StartAutomationExecution`, `SendCommand`, and resource modifications.
- **EventBridge metrics and configured logs:** track matches, invocations, retries, latency, and target errors.
- **OpsCenter:** tracks investigation status, assignees, resources, and linked runbooks.

Never print secrets, tokens, or personal data in runbook outputs. Apply retention and read permissions appropriate for incident sensitivity.

## 13. Controlling Blast Radius and Execution Velocity

Automation can turn a small configuration mistake into widespread resource changes. Before enabling, bound scope:

- Permit targets only in designated accounts, Regions, and tags.
- Use an allowlist of approved finding types rather than auto-handling every finding.
- Require approvals for actions that can halt services or sever management access.
- Test in development/staging first.
- Roll out in small batches, measure outcomes, then expand.
- For Automation targeting multiple resources via `StartAutomationExecution` or `aws:executeAutomation`, use `MaxConcurrency` and `MaxErrors` to cap parallelism and error thresholds. Simple EventBridge targets do not enforce these limits via Input Transformer alone.
- Prepare rollback runbooks or access recovery procedures.
- Monitor quotas and Automation execution throughput during large finding spikes.

`MaxErrors` is the threshold that stops dispatching Automation to new targets after a set number of errors; in-flight executions may still succeed or fail. For example, setting `MaxErrors=3` stops dispatching to new targets upon the fourth error. If strict error limits are required, lower `MaxConcurrency` to 1 for sequential execution.

Never automatically stop, terminate, or isolate an entire fleet based on an unverified event. Combine findings, resource roles, tags, Auto Scaling relationships, and workload criticality.

## 14. Running Multi-Account and Multi-Region Automation

In large organizations, events can originate across many accounts and Regions. EventBridge event bus policies can forward events from member accounts to a centralized bus; rules in the central account then triage and invoke appropriate targets.

Systems Manager Automation supports multi-account and multi-Region execution scenarios via target locations, shared runbooks, and IAM roles in target accounts. When designing, specify:

- Which account detects, which orchestrates, and which owns the resource.
- Event bus policies permitting the right source accounts/events.
- Runbook sharing scope and versions.
- Target-account roles granting only necessary actions.
- Aggregation and reconciliation of child automation results in the orchestrating account.

With a GuardDuty delegated administrator, `detail.accountId` identifies the member account where the finding originated. The top-level `account` field indicates the account that emitted the event; select the exact field when filtering for a specific member account in a centralized setup.

The `aws:approve` step does not support multi-account and multi-Region Automation. If centralized approval is needed for multi-account workflows, implement the approval step in an appropriate orchestration layer rather than assuming `aws:approve` works across every topology.

## 15. Testing Before Enabling Automated Response

Layered testing uncovers flaws without creating real incidents.

1. **Test event schema:** obtain sample service events and confirm required fields exist.
2. **Test event pattern:** use EventBridge Sandbox or `test-event-pattern` to confirm intended events match and out-of-scope events do not.
3. **Test Input Transformer:** test against sample events and confirm output JSON has valid types, parameter names, and required values.
4. **Test runbook standalone:** run the runbook manually against a test resource with controlled parameters.
5. **Test IAM:** verify EventBridge can assume the invocation role, invoke the target, and pass the Automation role.
6. **Test approval:** verify the SNS topic receives notifications and authorized principals can approve/reject.
7. **Test DLQ:** use a controlled permission-denied test target to verify failures route to the DLQ after retries.
8. **Test duplicates:** resend identical test data and confirm the runbook causes no duplicate side effects.
9. **Test rollback:** execute recovery procedures in a test environment.
10. **Roll out in cohorts:** monitor metrics, execution history, and OpsItems before expanding.

You can use the AWS CLI to test an event pattern:

~~~bash
aws events test-event-pattern \
  --event-pattern file://guardduty-ec2-high-pattern.json \
  --event file://sample-guardduty-finding.json
~~~

The command returns `Result: true` if the event matches the pattern. This command tests only the filter; it does not run Automation or verify target IAM permissions.

Check rule and target status:

~~~bash
aws events describe-rule \
  --name GuardDutyHighEC2Finding

aws events list-targets-by-rule \
  --rule GuardDutyHighEC2Finding
~~~

Check Automation results once an execution ID is available:

~~~bash
aws ssm get-automation-execution \
  --automation-execution-id <AUTOMATION_EXECUTION_ID>
~~~

Never use production findings or user-facing instances to test isolation actions. Use recoverable test resources.

## 16. Common Troubleshooting

| Symptom | Possible Cause | Inspection Direction |
|---|---|---|
| Rule does not match events | Wrong `source`, `detail-type`, field name, numeric type, or Region | Inspect raw event; use EventBridge Sandbox/test-event-pattern |
| Rule matches but target does not run | Target not attached, missing required parameters, or wrong target ARN | `list-targets-by-rule`, inspect `FailedEntries` and target ARN |
| EventBridge reports AccessDenied | Invocation role lacks permissions or trust policy excludes `events.amazonaws.com` | Check trust relationship, `ssm:StartAutomationExecution`, and `iam:PassRole` |
| Automation reports missing permissions | Automation role lacks API permissions or hits an explicit Deny | Inspect failed step, CloudTrail, and assume role IAM policies |
| Automation cannot assume role | Wrong ARN or trust policy excludes `ssm.amazonaws.com` | Verify role exists, trust relationship, and `AutomationAssumeRole` parameter |
| Run Command produces no results | Instance not a managed node, agent offline, or missing permissions | Check Managed nodes, SSM Agent, instance profile, and endpoint connectivity |
| Input Transformer fails | JSONPath missing or template renders invalid JSON | Check sample event, input paths, and template in Sandbox |
| Events land in DLQ | Target throttling, missing role permissions, missing resource, or retries exhausted | Read DLQ error code/message, retry metrics, and target logs |
| Single event spawns multiple executions | Redelivered event, finding updates, or duplicate rules | Correlate event ID/finding ID; add idempotency guard |
| Automation succeeds yet resource unchanged | Runbook checks state and exits, wrong target, or state-changing step skipped | Inspect step executions, outputs, and resource ID |
| Instance loses management access after quarantine | Isolation security group blocks SSM/SSH/RDP paths | Use break-glass procedures and approved recovery runbooks |
| Rule triggers itself continuously | Remediation emits events matching the same rule | Narrow event pattern, exclude automation changes, and check invocation counts |

When diagnosing, pinpoint which stage failed: event did not reach bus, pattern did not match, target was not invoked, Automation failed to start, or a runbook step failed. Each stage has distinct logs and permissions.

## 17. Practical Scenario

An AWS account runs an internal application on EC2. GuardDuty emits a high-severity finding for the instance. The security team wants to preserve evidence, notify on-call staff, and isolate the host once confirmed.

Design a workflow meeting these requirements:

- Accept only EC2 findings at or above the security team's severity threshold.
- Extract the exact instance ID and finding ID from the event.
- Create an OpsItem so the security team can track investigation.
- Wait for approval before running the isolation runbook.
- Send a result notification after Automation finishes.
- Avoid repeating isolation actions if the same finding is redelivered.

One possible design:

1. An EventBridge rule filters GuardDuty findings by `source`, `detail-type`, `severity`, `resourceType`, and account/Region.
2. The rule routes events to OpsCenter to create an OpsItem and to the Automation wrapper runbook.
3. Input Transformer maps instance ID, finding ID, and finding type into parameters.
4. The runbook inspects the resource, governance tags, and current state.
5. The runbook uses `aws:approve` to wait for on-call approval.
6. Upon approval, the runbook calls `AWS-QuarantineEC2Instance`.
7. Automation execution status events trigger a rule notifying success or failure.
8. The runbook or orchestration layer records the finding ID and processing state in an idempotency store so duplicate events do not repeat mutations.
9. On-call responders update the OpsItem, record justification, and oversee recovery.

When reviewing this design, explain why OpsCenter remains necessary alongside Automation, which role is allowed to launch runbooks, which role is allowed to modify EC2, and how access is restored after containment.

## 18. Design Pitfalls to Avoid

**Matching every event from a service.** This can trigger runbooks excessively and create unexpected costs. Filter by specific event types and meaningful attributes.

**Using a single admin IAM role for every target.** If that role is compromised or a rule misconfigured, the blast radius is massive. Separate roles and scope permissions by document, resource, and action.

**Letting events directly dictate which resources change.** Events may omit fields or carry unexpected values. Verify resource ID, account, Region, tags, and state before acting.

**Treating target invocation success as remediation success.** EventBridge accepting a request and Automation finishing are two separate states. Monitor both.

**Ignoring duplicate events.** Repeated events can create duplicate snapshots, OpsItems, or repeated resource edits. Build idempotency from the start.

**Auto-isolating every EC2 instance with a finding.** An instance may serve critical systems, belong to an Auto Scaling group, or hold data needing preservation. Classify resources and gate high-blast-radius actions with approvals.

**Lacking a DLQ or target-failure alerting.** Events dropped after retries exhaust can leave operations unaware an incident was missed.

**Skipping recovery preparation.** Isolating, stopping, or altering configurations can sever access. Prepare recovery runbooks and controlled break-glass permissions.

## 19. Self-Check Questions

1. What part of the response workflow does EventBridge handle?
2. How do `source` and `detail-type` differ?
3. Why should event patterns filter by account and Region?
4. When should you choose Automation over Run Command?
5. What problem does OpsCenter solve that Automation execution history does not fully cover?
6. How does Input Transformer help when events carry varying instance IDs?
7. Why must event-derived parameters be validated before use in a runbook?
8. How do the EventBridge invocation role and Automation assume role differ in responsibility?
9. Which risk does `aws:approve` help control?
10. Why doesn't a successful EventBridge target invocation prove remediation completed?
11. What scenarios does a DLQ help handle?
12. How do you prevent a runbook from emitting events that re-trigger the same rule in a loop?
13. Why is idempotency required when the same finding can arrive multiple times?
14. When should you create an OpsItem instead of automatically isolating a resource?
15. What must be verified before applying a quarantine runbook to production EC2 instances?

## 20. Pre-Production Checklist

- [ ] Event source, event type, account, and Region are defined.
- [ ] Event patterns have been tested against matching and non-matching sample events.
- [ ] Input Transformer maps all required parameters with accurate data types.
- [ ] Runbook content, version, actions, and outputs have been reviewed.
- [ ] EventBridge role can only invoke the intended targets and pass the right Automation role.
- [ ] Automation role holds only permissions required by the runbook.
- [ ] Managed nodes are ready if the workflow uses Run Command.
- [ ] High-impact actions have approval gates or explicit scope constraints.
- [ ] Idempotency guards and loop-prevention controls are implemented.
- [ ] Retry policies and SQS DLQs are configured.
- [ ] CloudWatch alarms monitor target failures, retries, and DLQs.
- [ ] A rule monitors Automation execution status.
- [ ] CloudTrail, Automation history, and required logs are retained.
- [ ] Rollback procedures, break-glass paths, and owners are defined.
- [ ] Tested in development/staging prior to production enablement.

## Conclusion

EventBridge and Systems Manager form an event-driven response platform: EventBridge ingests and filters signals, while Systems Manager executes defined runbooks or creates OpsItems for operator triage. System reliability depends on accurate event patterns, runbooks that validate inputs, least-privilege IAM roles, approval gates for risky actions, duplicate-event handling, and end-to-end observability from event arrival through verified remediation.

## AWS Reference Documentation

- [Run automations based on EventBridge events](https://docs.aws.amazon.com/systems-manager/latest/userguide/running-automations-event-bridge.html)
- [Sample scenarios: Systems Manager targets in EventBridge rules](https://docs.aws.amazon.com/systems-manager/latest/userguide/monitoring-systems-manager-targets.html)
- [Event bus targets in Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-targets.html)
- [Processing GuardDuty findings with Amazon EventBridge](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings_eventbridge.html)
- [AWS-QuarantineEC2Instance runbook](https://docs.aws.amazon.com/systems-manager-automation-runbooks/latest/userguide/aws-quarantineec2instance.html)
- [Systems Manager Automation actions reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-actions.html)
- [aws:executeAutomation action](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-executeAutomation.html)
- [aws:approve action](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-approve.html)
- [Setting up Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup.html)
- [Systems Manager Automation identity-based policy examples](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup-identity-based-policies.html)
- [Systems Manager IAM actions, resources, and condition keys](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awssystemsmanager.html)
- [IAM roles for EventBridge targets](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-events-iam-roles.html)
- [Amazon EventBridge input transformation](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-transform-target-input.html)
- [Passing data to Automation using input transformers](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-tutorial-eventbridge-input-transformers.html)
- [EventBridge retry policies and dead-letter queues](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html)
- [Monitoring Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-monitoring.html)
- [Systems Manager event examples for EventBridge](https://docs.aws.amazon.com/systems-manager/latest/userguide/monitoring-systems-manager-event-examples.html)
- [Systems Manager OpsCenter](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter.html)
- [Configure EventBridge rules to create OpsItems](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-automatically-create-OpsItems-2.html)
- [Monitoring Systems Manager events with EventBridge](https://docs.aws.amazon.com/systems-manager/latest/userguide/monitoring-eventbridge-events.html)
- [Amazon EventBridge event patterns and types for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/reference-eventbridge-events.html)
- [Testing event patterns with EventBridge Sandbox](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-pattern-sandbox.html)
