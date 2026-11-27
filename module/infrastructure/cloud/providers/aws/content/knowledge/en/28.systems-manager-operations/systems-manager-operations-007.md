# Automation Runbooks and Recurring Incident Remediation

## Lesson Objectives

Within the **CLOUD_PROVIDERS_AWS** ecosystem, AWS Systems Manager provides operational tools for managing resources and managed nodes at scale. Automation turns an operational procedure into a repeatable runbook with clear inputs, execution permissions, conditions, approval steps, outputs, and execution history. When combined with Amazon EventBridge, Amazon CloudWatch, and OpsCenter, runbooks become part of the incident intake and remediation workflow.

After this lesson, learners will be able to:

- Distinguish Automation runbooks from Command documents, Run Command, State Manager, and Maintenance Windows.
- Read the structure of an Automation document and choose appropriate actions.
- Design runbooks with parameters, input validation, branching, post-checks, and error handling.
- Configure IAM assume roles following least privilege and understand caller permissions.
- Connect runbooks to EventBridge, operational schedules, CloudWatch alarms, and OpsItem workflows.
- Control multi-resource execution using concurrency, error thresholds, and approvals.
- Monitor executions, investigate failures, and improve runbooks for safe recurring incident handling.

## 1. What Operational Problem Does Automation Solve?

In systems operations, many incidents share the same remediation pattern: identify affected resources, collect state, check preconditions, execute remediation, confirm service recovery, and record the outcome. If performed manually every time, results vary across engineers, response times stretch, and it becomes hard to prove who did what.

AWS Systems Manager Automation standardizes that workflow into an executable, auditable sequence of steps. Runbooks can act on AWS resources such as EC2, EBS, RDS, S3, CloudFormation, and on managed nodes via Run Command. A runbook can call AWS APIs, execute Python or PowerShell scripts, invoke other runbooks, wait for resource states, request approvals, or run commands on servers.

For example, when a web service on EC2 repeatedly stops, the operations team can build this workflow:

1. Identify the affected instance and service.
2. Check whether the instance is running and still connected to Systems Manager.
3. Gather service status and required logs.
4. Require authorization approval if the action may cause disruption.
5. Restart the service.
6. Verify the service is active and the application endpoint returns expected responses.
7. Record the execution ID, outcome, timestamps, and root cause.

Runbooks let the team follow the exact same process every time an incident occurs. However, automation should only perform actions that are well understood and guarded by safety checks. An insufficiently specific alert should never automatically trigger an action capable of causing data loss or broad impact.

## 2. Distinguishing Automation from Other Systems Manager Features

Systems Manager includes several document types and operational mechanisms. Choosing the right one keeps runbooks maintainable and avoids confusion about how they execute.

| Component | Purpose | Example |
|---|---|---|
| Automation runbook | Orchestrate multi-step workflows across AWS resources or managed nodes | Inspect EC2, request approval, restart service, verify |
| Command document | Define commands that run on managed nodes via SSM Agent | `AWS-RunShellScript`, `AWS-RunPowerShellScript` |
| Run Command | Dispatch a Command document to one or more managed nodes | Run a disk-space check command on EC2 |
| State Manager | Maintain desired configuration state via associations and schedules | Ensure agents or configurations remain installed periodically |
| Maintenance Windows | Schedule maintenance windows for operational tasks | Run updates or automations during maintenance hours |

An Automation runbook is an `Automation` document type using schema version `0.3`. Command documents use different schema versions, typically `1.2`, `2.0`, or `2.2`. An Automation runbook can invoke a Command document using the `aws:runCommand` action; the two documents serve different layers of the workflow.

Use Automation when you need multi-step orchestration, conditionals, execution permissions, approvals, or actions across multiple AWS services. If you only need to run a set of commands on a group of servers, Run Command may suffice. If you need continuous enforcement of a desired configuration, State Manager fits better. If a task must run inside a scheduled maintenance window, Maintenance Windows can invoke Automation or Run Command as a task.

## 3. Components of an Automation Runbook

Runbooks are stored as Systems Manager documents. Content can be authored in YAML or JSON. A runbook typically contains:

- `description`: describes the purpose.
- `schemaVersion`: document schema version; Automation uses `0.3`.
- `assumeRole`: the IAM role Automation assumes to execute steps.
- `parameters`: caller-supplied inputs, optionally with types, defaults, and constraints.
- `mainSteps`: sequential execution steps.
- `outputs`: result values exposed from steps that produce compatible outputs.

Each item in `mainSteps` has a unique `name` and an `action`. The action determines the step's inputs, behavior, and outputs. A step can reference a previous step's output using `{{ stepName.outputName }}`. This lets a runbook fetch a resource ID from one API call and pass it to the next step.

Minimal structure example:

~~~yaml
description: Check the status of an EC2 instance
schemaVersion: '0.3'
parameters:
  InstanceId:
    type: String
    description: ID of the EC2 instance to check
mainSteps:
  - name: describeInstance
    action: aws:executeAwsApi
    inputs:
      Service: ec2
      Api: DescribeInstances
      InstanceIds:
        - '{{ InstanceId }}'
    outputs:
      - Name: InstanceState
        Selector: '$.Reservations[0].Instances[0].State.Name'
        Type: String
~~~

This example illustrates the structure. In production implementations, add input constraints, IAM permissions, handling for cases where the API returns no instance, and result verification steps. With `aws:executeAwsApi`, `Selector` uses JSONPath to extract data from the API response. With wait or assertion actions, `PropertySelector` specifies the property to compare.

## 4. Common Automation Actions

Automation includes many purpose-built actions. You do not need to write scripts for every operation; prefer built-in actions because they clearly express intent and outputs.

| Action | Function | Suitable Scenario |
|---|---|---|
| `aws:executeAwsApi` | Call an AWS service API | Read EC2 status, create snapshots, update tags |
| `aws:executeScript` | Run Python or PowerShell in the runbook | Transform data, compute values, or handle custom logic without a dedicated action |
| `aws:runCommand` | Run a Command document on managed nodes | Check services, disk space, or run remediation commands |
| `aws:branch` | Jump to another step conditionally | Branch between Linux/Windows or remediate only when conditions match |
| `aws:approve` | Pause awaiting principal approval or denial | Restart critical services, modify production config |
| `aws:waitForAwsResourceProperty` | Wait until a resource property reaches a desired value | Wait for an instance, volume, or image state transition |
| `aws:assertAwsResourceProperty` | Assert a property has an expected value | Halt workflow if preconditions fail before making changes |
| `aws:executeAutomation` | Invoke another Automation runbook | Modularize large workflows into reusable runbooks |
| `aws:invokeLambdaFunction` | Invoke a Lambda function | Integrate custom logic already packaged in Lambda |
| `aws:loop` | Iterate over steps | Process a list of items in a workflow |
| `aws:sleep` | Pause for a specified duration | Wait before a follow-up check |

Common step attributes also include:

- `maxAttempts`: retry count when a step fails; defaults to one attempt.
- `timeoutSeconds`: execution time limit for the step.
- `onFailure`: `Abort`, `Continue`, or jump to another step.
- `onCancel`: specifies a step to handle cancellation, subject to supported limits and action types.

Do not set high retry counts blindly for every error. IAM permission errors, invalid parameters, or missing resources rarely resolve on retry. Retries are most effective for transient failures, throttling, or resources transitioning states. For actions with side effects, ensure retries do not duplicate resources or repeat unintended mutations.

## 5. Designing Parameters and Input Validation

Parameters make a single runbook reusable across many resources. Rather than writing separate documents for each EC2 instance, operators supply `InstanceId`, service name, environment, or remediation level at runtime.

Common data types include `String`, `StringList`, `Boolean`, `Integer`, `MapList`, and others per the Systems Manager schema. You can define `default`, `allowedValues`, `allowedPattern`, `minItems`, `maxItems`, and descriptions to constrain inputs.

Example:

~~~yaml
parameters:
  InstanceId:
    type: String
    description: EC2 instance ID
    allowedPattern: '^i-[0-9a-f]{8,17}$'
  ServiceName:
    type: String
    description: Linux systemd service name
    allowedPattern: '^[A-Za-z0-9_.@-]{1,64}$'
  Environment:
    type: String
    allowedValues:
      - development
      - staging
      - production
~~~

Parameter constraints catch errors early and reduce the chance of operators targeting the wrong resource. When parameters are substituted into shell commands or scripts, restrict valid characters, validate values in an initial step, and avoid raw string concatenation into commands. Never pass passwords, access keys, tokens, or secrets in plain text parameters; use dedicated secrets management and separate access controls.

A production runbook should require enough context to accurately identify the target and change scope. For example, instead of accepting only an `InstanceId`, the workflow can verify `Environment`, `Application`, and `Owner` tags before permitting remediation.

## 6. IAM Assume Roles and Execution Permissions

Distinguish two permission layers:

1. **Caller (user or system) permissions:** govern whether the principal can call `ssm:StartAutomationExecution` on the document, pass an assume role, and view, stop, or signal executions.
2. **Automation assume role permissions:** govern which AWS APIs and managed node actions the workflow can perform.

When a runbook specifies `assumeRole`, Systems Manager uses that IAM role to execute steps. The role's trust policy must allow the Systems Manager service to assume it. Policies attached to the role must enforce least privilege for the specific actions and resources. For example, a runbook calling EC2 APIs needs corresponding EC2 permissions; a runbook calling `aws:runCommand` needs permission to dispatch the Command document to the managed nodes and reference the document.

The caller needs `iam:PassRole` for the Automation role passed when required by the operation. Never grant `iam:PassRole` on all roles in the account. Scope the allowed role ARN and restrict which documents the principal may execute.

If no assume role is specified, Automation runs under the caller's permissions. That can work for short, simple tasks, but fails to separate operator privileges from execution privileges when the runbook needs elevated permissions. For production workflows, use a dedicated Automation service role with a strict trust policy, least-privilege permissions, logging, and periodic reviews.

Certain cases require specifying a service role—such as State Manager associations running runbooks, executions expected to last longer than 12 hours, or non-AWS-owned runbooks using `aws:executeScript` to call AWS APIs or manipulate resources. Whenever `aws:executeScript` calls AWS APIs, an Automation assume role is mandatory, and that role must have permissions for the invoked service.

For managed nodes, ensure SSM Agent is running, the instance profile or credential mechanism has Systems Manager permissions, and the node can reach required endpoints. Automation role permissions do not replace managed node connectivity and registration prerequisites.

## 7. Connecting Runbooks to Schedules and Events

Runbooks can be launched manually from the Systems Manager console or AWS CLI. For recurring work, use schedules or events to avoid relying on manual intervention.

### 7.1. Amazon EventBridge

EventBridge can target a runbook from a rule. Rules can trigger on a schedule or when an AWS event matches an event pattern. Examples:

- EC2 enters `running` and needs bootstrap steps.
- A resource state-change event triggers an inspection workflow.
- A periodic schedule audits resources, performs cleanup, or verifies state.
- A service event triggers diagnostics or remediation.

EventBridge needs a role allowing it to invoke Systems Manager Automation and pass required runbook parameters. When parameters come from the event payload, use an input transformer to map event fields into the expected input structure. If a rule omits a required parameter, the target invocation can fail.

Events may be redelivered when targets fail. Therefore, runbooks should be idempotent and inspect current state before mutating anything. Never assume each event is processed strictly once.

### 7.2. Maintenance Windows

For tasks bound to fixed windows, Maintenance Windows can schedule Automation tasks. For example, the platform team runs post-patch verification on weekends or executes periodic maintenance off-peak.

Use EventBridge schedules for simple periodic runbooks. Use Maintenance Windows when you need maintenance window governance, task ordering, target registration, and cutoff limits aligned with operational processes.

### 7.3. CloudWatch Alarms and OpsCenter

You can attach a CloudWatch alarm to an Automation execution to monitor system health while the workflow runs. If the alarm enters `ALARM`, the execution can be cancelled and run its defined `onCancel` step. This acts as a safety circuit breaker if the system degrades during remediation.

OpsCenter lets you associate OpsItems with Automation runbooks for remediation. Operators can inspect related CloudWatch metrics, alarms, CloudTrail logs, and AWS Config data, then run an appropriate runbook. Clearly define which runbooks may run automatically and which require human confirmation.

## 8. Approvals and Change Control

Not all remediation should be fully automated. Actions can be grouped by risk tier:

| Risk Level | Example | Control Mechanism |
|---|---|---|
| Read-only diagnostics | Collect instance status, logs, or configuration | Can be automated with scoped read permissions |
| Low-risk, reversible change | Add standard tags, restart a stopped agent | Verify preconditions, scope targets, and log |
| Potentially disruptive | Restart service, detach volume, change network config | Require approval or a change window |
| Potential data loss or wide blast radius | Delete resources, modify databases, fleet-wide actions | Multi-level approval, backups, canary, rollback, scope verification |

The `aws:approve` action pauses Automation until designated principals approve or deny. Notifications can be sent via SNS; SNS topic names used for approvals must start with `Automation`. One or multiple approvals can be required. By default, an approval step waits up to 7 days and can be configured up to 30 days. If the timeout expires without sufficient approvals, the workflow does not proceed as if approved.

Key limitations to note: `aws:approve` does not support multi-account and multi-Region automations. For workflows needing approvals across accounts or Regions, design approval at the orchestration layer or split workflows by supported scope.

For significant changes, record the rationale, ticket, approvers, timestamps, target resources, and executed document version. Approvals must precede steps with side effects; never place an approval after the mutation has occurred.

## 9. Multi-Resource Execution with Rate Controls

Automation supports mapping targets by ID or criteria such as tags. When running across a fleet, control how many resources process concurrently and how many errors are tolerated before stopping further dispatches.

- **MaxConcurrency:** number or percentage of targets processed simultaneously. For example, `1` runs sequentially; `10%` allows up to 10% of targets at once.
- **MaxErrors:** number or percentage of errors allowed before stopping Automation dispatch to new targets. If set to `0`, dispatch halts after the first error.

Executions already in flight when the error threshold is reached are allowed to finish and may also fail. To minimize errors exceeding the threshold, set concurrency to `1` for sequential execution. For high-impact changes, start with a small canary, validate outcomes, and then raise the rate.

Example rollout strategy for 100 EC2 instances:

| Phase | Targets | Concurrency | Error Threshold | Goal |
|---|---:|---:|---:|---|
| Canary | 1 instance | 1 | 0 | Verify execution and post-checks |
| Small expansion | 10 instances | 1 or 10% | 1 | Catch issues while blast radius is small |
| Full expansion | Remaining instances | Proven rate | Per operational SLO | Complete while metrics remain healthy |

Numbers in the table are design examples, not AWS defaults. Tune them to recovery capability, application load, maintenance window duration, and service limits. If a runbook contains multiple disruptive steps, consider both execution-level rate controls and per-step halt conditions.

## 10. Example: Linux Service Restart Runbook with Approval

Suppose an application on EC2 frequently experiences web process crashes. The team wants to standardize restarting the service, while requiring human approval in production before any change occurs.

Sample workflow:

~~~mermaid
flowchart TD
    A[CloudWatch alarm or OpsItem] --> B[Receive InstanceId and ServiceName]
    B --> C[Validate parameters and scope]
    C --> D{Prerequisites met?}
    D -- No --> E[Stop and log reason]
    D -- Yes --> F[Wait for approval]
    F --> G{Approved?}
    G -- No or timeout --> H[Abort and record decision]
    G -- Yes --> I[SSM Run Command: restart service]
    I --> J[Check systemctl is-active]
    J --> K{Service active?}
    K -- Yes --> L[Record success]
    K -- No --> M[Flag for investigation]
~~~

The Automation document below illustrates the key components. Replace the role ARN, SNS topic, and approvers with resources from your account. This runbook applies only to Linux instances with a running SSM Agent and systemd-managed services.

~~~yaml
description: Restart a Linux service after approval
schemaVersion: '0.3'
assumeRole: '{{ AutomationAssumeRole }}'

parameters:
  AutomationAssumeRole:
    type: String
    description: IAM role for Systems Manager Automation
  InstanceId:
    type: String
    description: EC2 instance to remediate
    allowedPattern: '^i-[0-9a-f]{8,17}$'
  ServiceName:
    type: String
    description: systemd service name
    allowedPattern: '^[A-Za-z0-9_.@-]{1,64}$'
  ApprovalTopicArn:
    type: String
    description: SNS topic whose name starts with Automation
  ApproverArns:
    type: StringList
    description: IAM users or roles allowed to approve

mainSteps:
  - name: approveRestart
    action: aws:approve
    timeoutSeconds: 3600
    onFailure: Abort
    inputs:
      NotificationArn: '{{ ApprovalTopicArn }}'
      Message: 'Approve restart of {{ ServiceName }} on {{ InstanceId }}.'
      MinRequiredApprovals: 1
      Approvers: '{{ ApproverArns }}'

  - name: restartService
    action: aws:runCommand
    timeoutSeconds: 600
    onFailure: Abort
    inputs:
      DocumentName: AWS-RunShellScript
      InstanceIds:
        - '{{ InstanceId }}'
      Parameters:
        commands:
          - 'set -e'
          - 'systemctl restart {{ ServiceName }}'
          - 'systemctl is-active --quiet {{ ServiceName }}'
          - 'systemctl --no-pager status {{ ServiceName }}'
~~~

Key design details:

- `schemaVersion: '0.3'` identifies this as an Automation document.
- `assumeRole` specifies the role used to execute the steps.
- `allowedPattern` restricts the instance ID and allowed characters in the service name, reducing command-injection risk when parameter values are substituted into shell commands.
- `aws:approve` pauses the workflow and notifies the SNS topic. If denied or timed out, the restart step does not run.
- `aws:runCommand` invokes `AWS-RunShellScript` on the specified instance.
- `systemctl is-active --quiet` serves as a post-check. If the service is inactive, the command exits non-zero and Automation marks the step failed.

This example intentionally uses a single `aws:runCommand` action. Automation supports multiple Run Command actions in a runbook, but output from only one Run Command action is supported at a time. If you need pre-restart diagnostics and post-checks across multiple Run Command calls, design explicit output storage and retrieval—such as CloudWatch Logs or S3—rather than assuming every action exposes inline output in the same execution.

Before production use, add checks for environment tags, EC2 state, managed node permissions, change windows, logging, and rollback. Never trigger restarts across every instance at once solely because an alarm fired.

## 11. Launching and Tracking Executions with the AWS CLI

You can create Automation documents using the console, Document Builder, or AWS CLI. Given the prepared YAML file, example creation command:

~~~bash
aws ssm create-document \
  --name "RestartLinuxServiceWithApproval" \
  --document-type "Automation" \
  --document-format "YAML" \
  --content file://restart-linux-service.yml \
  --region ap-southeast-1
~~~

When running, pass parameters matching the document types. Example `parameters.json`:

~~~json
{
  "AutomationAssumeRole": [
    "arn:aws:iam::123456789012:role/SSMAutomationRole"
  ],
  "InstanceId": [
    "i-0123456789abcdef0"
  ],
  "ServiceName": [
    "nginx"
  ],
  "ApprovalTopicArn": [
    "arn:aws:sns:ap-southeast-1:123456789012:Automation-ApprovalRequest"
  ],
  "ApproverArns": [
    "arn:aws:iam::123456789012:role/OperationsApprover"
  ]
}
~~~

Start the execution and save the returned `AutomationExecutionId`:

~~~bash
aws ssm start-automation-execution \
  --document-name "RestartLinuxServiceWithApproval" \
  --parameters file://parameters.json \
  --region ap-southeast-1
~~~

Monitor status and per-step details:

~~~bash
aws ssm get-automation-execution \
  --automation-execution-id "EXECUTION_ID" \
  --region ap-southeast-1
~~~

If the execution is awaiting approval, an authorized principal can send an approve or deny signal:

~~~bash
aws ssm send-automation-signal \
  --automation-execution-id "EXECUTION_ID" \
  --signal-type "Approve" \
  --payload "Comment=Approved after checking the maintenance ticket." \
  --region ap-southeast-1
~~~

Replace `Approve` with `Deny` to reject. Operators can also stop an execution using `stop-automation-execution`. Record the execution ID in the ticket or OpsItem to link actions to the root incident.

Documents are versioned. Every content update creates a new version, and one version can be set as default. In production, test new versions, review diffs, and update the default version only after validation. For workflows requiring reproducibility, specify an explicit document version at launch instead of relying on `latest`, which can change over time.

## 12. Logging, Monitoring, and Traceability

An incident-remediation runbook must leave sufficient evidence for both the active responder and post-incident reviewers. Track:

- `AutomationExecutionId`, document name, and version.
- Start time, end time, and initiating user or service.
- Parameters used, target resources, and AWS account/Region.
- Step names, actions, statuses, durations, and error messages.
- Approval decisions, approvers, comments, and timestamps.
- Post-check results, rollbacks, and final incident state.

The Systems Manager console and `GetAutomationExecution` API expose overall status and `StepExecutions`. For a failed step, inspect the step's outputs and `FailureMessage` to identify which API or action failed.

You can send output from `aws:executeScript` actions to CloudWatch Logs for debugging. This logging configuration applies at the account level; Systems Manager does not automatically create log groups or log streams for documents that do not use `aws:executeScript`. If the log group is encrypted with KMS, streamed output is encrypted accordingly. For Run Command outputs, configure CloudWatch Output or S3 output separately as needed.

Do not log secrets, tokens, passwords, personal data, or sensitive content in messages, script outputs, or logs unless strictly required. Restrict read access to logs and execution history by role. Set retention policies on CloudWatch Logs and S3 to balance audit requirements, troubleshooting needs, and storage costs.

## 13. Common Error Handling

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Cannot start execution | Missing `ssm:StartAutomationExecution` or document access | Check principal's IAM policy and document ARN |
| `iam:PassRole` error | Caller not permitted to pass the Automation role | Grant scoped `iam:PassRole` for the exact role ARN |
| Cannot assume role | Role missing, wrong trust policy, or invalid ARN | Check `ssm.amazonaws.com` trust principal, ARN, and policy |
| `AccessDenied` inside a step | Automation role lacks target service API permissions | Compare actions in the runbook against the IAM policy |
| `aws:runCommand` does not reach instance | Not a managed node, SSM Agent error, or missing endpoint access | Check Fleet Manager, SSM Agent, instance profile, and network |
| Step times out | `timeoutSeconds` too short or downstream service slow | Check step output, actual duration, and resource state |
| API returns no resource | Wrong ID, wrong Region, or resource deleted | Check account, Region, parameters, and read permissions |
| Runbook fails after retries | Input or permission error that retries cannot fix | Classify error before raising `maxAttempts` |
| Approval stuck in Waiting | Missing required approvals or notifications undelivered | Check SNS topic, approver ARNs, timeout, and execution ID |
| Some targets fail in fleet run | Tag mismatch, inconsistent permissions, or rate controls halted dispatch | Check per-target results, target mapping, and error threshold |

Investigation should start at the first failing step rather than only looking at the aggregate status. Identify which API the action called, actual inputs, which role executed it, the exact error returned, and whether the resource was in the expected state. After fixing the root cause, re-run with validated parameters and a verified document version.

When using a runbook as incident remediation, record why automation could not resolve the issue and escalate to the on-call engineer. Never automatically loop a state-mutating action when the root cause is unknown.

## 14. Designing Resilient and Safe Runbooks

A good runbook does more than finish with `Success`. It enforces input validation, actions, postconditions, and failure handling.

**Idempotency:** re-running the same runbook should not create duplicate resources or cause unnecessary state changes. For example, before creating a new snapshot, check whether a suitable snapshot already exists. Before restarting a service, check service status and prerequisites.

**Preconditions and postconditions:** verify the target resource is in scope before modifying it; after the action, verify actual state. An API returning success does not prove the application has recovered.

**Timeouts and retries:** set timeouts tailored to each API or script. Use bounded retries with appropriate backoff, and apply retries only to potentially transient errors.

**Rollback or recovery path:** for disruptive changes, prepare a way back to the previous state, such as restoring configuration or using a tested AMI/snapshot. Never assume rollback is automatically safe; it also needs preconditions and approvals.

**Canary and blast radius:** test on one non-critical resource, then a small group, before expanding. Use meaningful tags and re-verify targets before acting.

**Document versions and changes:** manage runbooks like source code. Review changes, version releases, test in staging, assign owners, and govern default version promotion.

**Human handoff:** when encountering anomalous data, missing inputs, or breached thresholds, halt remediation and escalate the incident to an authorized responder.

## 15. Cost and Operational Limits

Automation has quotas on concurrent executions. Current AWS documentation lists a default quota of 100 concurrent Automations per account; you can opt into adaptive concurrency to dynamically scale the quota up to 500 concurrent executions per AWS's documented mechanism. Parent executions, child executions, and rate-controlled executions all count toward concurrency. For large fleets, check current account and Region quotas rather than looking only at instance counts.

AWS also updated the Systems Manager Automation free tier: new customers starting August 14, 2025 no longer receive the Automation free tier; the free tier for existing customers ended December 31, 2025. Therefore, as of the writing of this lesson, estimate Automation costs using current pricing. Downstream services invoked by runbooks—such as EC2, Lambda, CloudWatch Logs, SNS, S3, or KMS—may also incur separate charges.

Cost-control measures:

- Avoid running automations too frequently when events can be batched or deduplicated.
- Scope targets and concurrency to operational goals.
- Use timeouts and exit conditions to prevent runaway executions.
- Log only what is necessary and set appropriate retention.
- Track execution counts, failures, and costs by account, Region, document, and resource group.

## 16. Deployment Lifecycle from Testing to Production

Roll out runbooks in structured stages:

1. **Describe the incident:** document symptoms, blast radius, common root causes, and current manual procedure.
2. **Standardize operations:** separate diagnostics, decisions, mutations, post-checks, and rollback.
3. **Select actions:** prefer built-in API actions; use scripts only when custom logic is necessary.
4. **Design parameters and IAM:** constrain resources, validate inputs, and separate caller permissions from execution permissions.
5. **Author the runbook:** define clear step names, timeouts, retries, `onFailure`, approvals, and outputs.
6. **Test in staging:** test success paths, bad parameters, missing permissions, timeouts, unavailable targets, and denied approvals.
7. **Run canary:** restrict to one or a few resources, verify post-checks and actual impact.
8. **Integrate:** wire into EventBridge, CloudWatch alarms, Maintenance Windows, or OpsCenter once manual runs are stable.
9. **Release:** review, create a new document version, and promote the default version under change management.
10. **Operate:** monitor executions, failures, recovery time, and remediation success rates; update the runbook as applications or architectures evolve.

Useful metrics include time from alert to execution start, time to service recovery, runbook success rate, escalation-to-human rate, rollback rate, and repeat remediation counts. These metrics verify whether automation actually reduces MTTR and human error.

## 17. Hands-On Exercise

An internal application runs on EC2 with an `nginx` service. Over the past month, the service stopped multiple times, forcing operations staff to log into individual servers to restart it. Design a reusable runbook meeting these requirements:

- Accept `InstanceId` and `ServiceName` as parameters.
- Allow only valid characters in the service name.
- Use an Automation assume role with least privilege.
- Send an approval request to the on-call responder before restarting in production.
- Invoke `AWS-RunShellScript` to restart the service.
- Check `systemctl is-active` after restarting.
- Record the execution ID in the ticket and configure appropriate logging.
- Test on a staging instance before expanding.

Then analyze these scenarios:

1. The instance does not appear in Fleet Manager.
2. The caller has `ssm:StartAutomationExecution` but lacks `iam:PassRole`.
3. Approval is denied.
4. The service restart succeeds, yet the application health check still fails.
5. The runbook runs on 20 instances and the first two fail.
6. EventBridge delivers the same event twice.
7. A new document version has a bug and you must revert to the previous version.

The expected deliverable is a runbook where every design choice is justified, blast radius is bounded, and unsafe conditions escalate cleanly to a human responder.

## Conclusion

AWS Systems Manager Automation turns operational procedures into repeatable, controlled, and auditable runbooks. Runbooks combine parameters, actions, outputs, conditions, IAM assume roles, and approvals to operate on AWS resources or managed nodes. EventBridge, maintenance schedules, CloudWatch alarms, and OpsCenter bring runbooks into day-to-day operations.

When automating incident remediation, verify scope before mutating state, enforce least-privilege permissions and concurrency limits, require approval for disruptive actions, validate post-action outcomes, and retain execution history. Runbooks should only auto-remediate well-defined conditions; anomalous cases must halt safely and escalate to accountable engineers.

## References

- [AWS Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-automation.html)
- [Creating your own runbooks](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-documents.html)
- [Authoring Automation runbooks](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-authoring-runbooks.html)
- [Systems Manager Automation actions reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-actions.html)
- [Setting up Automation and configuring service roles](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup.html)
- [aws:approve – Pause an automation for manual approval](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-approve.html)
- [aws:runCommand – Run a command on a managed instance](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-runcommand.html)
- [Run automations based on EventBridge events](https://docs.aws.amazon.com/systems-manager/latest/userguide/running-automations-event-bridge.html)
- [Control automations at scale](https://docs.aws.amazon.com/systems-manager/latest/userguide/running-automations-scale-controls.html)
- [Logging Automation action output with CloudWatch Logs](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-logging.html)
- [Troubleshooting Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-troubleshooting.html)
- [Remediate OpsItem issues](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-remediating.html)
- [AWS Systems Manager pricing](https://aws.amazon.com/systems-manager/pricing/)
