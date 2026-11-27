# State Manager and Maintaining Desired Configuration

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of AWS Systems Manager State Manager in configuration management and reducing configuration drift.
- Describe an association and the relationship among SSM documents, targets, parameters, schedules, and IAM roles.
- Choose a Command, Policy, or Automation document for each scenario.
- Register EC2 instances and hybrid servers as managed nodes so State Manager can orchestrate them.
- Select targets by tags, Resource Groups, node IDs, or all managed nodes in an account and Region.
- Design execution schedules, schedule offsets, concurrency, and error thresholds aligned with fleet size.
- Use Systems Manager Compliance, execution history, and Amazon S3 output to track results.
- Separate permissions among SSM Agent, the association dispatch role, and the Automation assume role.
- Combine State Manager with Quick Setup, AWS Organizations, CloudWatch, CloudTrail, and other operational services.

## 1. The Problem: Keeping Systems in a Defined State

An operations team may launch hundreds of EC2 instances for multiple applications. Every machine needs the CloudWatch Agent installed, certain OS services enabled, standardized security settings applied, and SSM Agent kept up to date. If staff must log into each machine to verify configuration, configurations will gradually diverge across servers. A manual change may be forgotten, a new machine may miss a package, or a critical service may stop.

That is configuration drift: the actual state of resources deviates from the state the organization intends.

AWS Systems Manager State Manager automatically applies defined configurations to managed nodes and certain AWS resources through associations. An association binds an SSM document to targets, parameters, and a schedule. When the association runs, State Manager executes the document on the targets or invokes Systems Manager Automation to modify AWS resources.

For example, an association can ensure every Linux server tagged **Environment=Production** has CloudWatch Agent installed and its service running. If the package is missing, the document installs it. If the service has stopped, the document can restart it. Subsequent runs continue verifying and returning machines to the defined state.

In the AWS ecosystem, State Manager integrates with:

- **SSM Agent** to receive and execute commands on EC2 instances and hybrid servers.
- **IAM** to scope permissions for node management, association dispatch, and Automation execution.
- **Amazon EC2, VPC, and VPC endpoints** to connect nodes with Systems Manager.
- **AWS Resource Groups and tags** to select the right resource groups.
- **Systems Manager Automation** to modify AWS resources via APIs.
- **Amazon S3 and CloudWatch** to store output and observe activity.
- **AWS Organizations and Quick Setup** to deploy consistent baselines across multiple accounts and Regions.

State Manager is well suited for periodic configuration enforcement and drift remediation. For maintenance tasks requiring an execution window with duration, cutoff, and an explicit maintenance schedule, consider Maintenance Windows.

## 2. Desired State and the Convergence Loop

Desired state is the end state a system must achieve. For example:

- CloudWatch Agent must be installed on the server.
- The **amazon-cloudwatch-agent** service must be enabled and running.
- SSM Agent must be updated on a schedule.
- A configuration file must have the specified content and permissions.
- A security group must have the approved set of ingress/egress rules.
- A group of EC2 instances must be stopped outside business hours.

State Manager does not need to watch every change in real time to accomplish this. An association applies the document upon creation, on a schedule, and on certain events such as when the association is updated, the document is updated, an operator requests a manual run, or a node comes back online after missing a scheduled run.

As a result, an association typically forms a convergence loop:

1. Inspect current state.
2. Compare against desired conditions.
3. Apply missing changes.
4. Verify state after changes.
5. Return success or failure.
6. Repeat on the next run.

~~~mermaid
flowchart TD
    A["Desired configuration"] --> B["State Manager association"]
    B --> C["Select targets and schedule"]
    C --> D["Run SSM document"]
    D --> E["Inspect current state"]
    E --> F{"Matches desired state?"}
    F -->|Yes| G["Report success / compliant"]
    F -->|No| H["Apply configuration"]
    H --> I["Verify result"]
    I --> J{"Verification passed?"}
    J -->|Yes| G
    J -->|No| K["Report failure and retain details"]
    G --> L["Wait for next run or trigger"]
    K --> L
    L --> B
~~~

To make this loop safe, documents should be idempotent: running repeatedly with the same inputs converges resources to the same state without introducing unnecessary extra changes. For example, `systemctl enable --now` enables and starts a service if needed. A script that appends a configuration line to a file on every run creates duplicate entries and is not idempotent.

Association success must also be meaningful. If a script merely finishes without verifying the final state, Systems Manager may report `Success` even though the configuration goal was not achieved. Make the document return an error code when the desired state cannot be verified.

## 3. State Manager and Associations

State Manager is a capability of AWS Systems Manager. Its central construct is the **association**.

An association is a configuration linking:

| Component | Role |
|---|---|
| SSM document | Defines the steps to perform |
| Targets | Selects managed nodes or AWS resources to apply to |
| Parameters | Passes input values to the document |
| Schedule | Determines when the association runs |
| Document version | Selects which version of the document content executes |
| Association dispatch role | Allows State Manager to send commands or start Automation |
| `AutomationAssumeRole` | Grants a runbook permission to call required AWS APIs |
| Compliance severity | Assigns a severity level to compliance results |
| Rate controls | Limits concurrent targets and allowed error thresholds |

When an association is created, State Manager assigns an Association ID. Associations can be created via the Systems Manager console, AWS CLI, AWS Tools for PowerShell, or APIs.

By default, an association runs immediately upon creation and then continues on the chosen schedule. If you do not want it to run immediately, you can configure it to apply only at the next cron interval in supported scenarios.

A single managed node can belong to multiple associations, but keep the count and scope manageable to avoid overlapping configurations.

## 4. Choosing the Right SSM Document

An SSM document describes the work Systems Manager performs. AWS provides many built-in documents; organizations can also author custom documents.

Common document types used with State Manager:

| Document type | Purpose | Examples |
|---|---|---|
| Command | Run commands or scripts on managed nodes | **AWS-RunShellScript**, **AWS-RunPowerShellScript** |
| Policy | Apply policies or baselines on managed nodes | Documents used for policy-based configuration |
| Automation | Execute multi-step workflows calling AWS APIs or manipulating resources | **AWS-RestartEC2Instance**, custom runbooks |

### 4.1 Command Documents

Command documents fit configuration inside the operating system:

- Installing or updating packages.
- Enabling and starting services.
- Creating directories or configuration files.
- Updating file contents.
- Checking processes and network ports.
- Running periodic configuration verification scripts.

Command documents are sent to managed nodes and executed by SSM Agent. Therefore, the node must be managed by Systems Manager and able to communicate with the service.

### 4.2 Policy Documents

Policy documents are used when applying policies on managed nodes. When selecting a document, check its document type and behavior in AWS documentation. Not every SSM document is suitable for an association.

### 4.3 Automation Runbooks

Automation runbooks are appropriate when the desired state involves AWS APIs or resources rather than an OS-internal process.

Examples:

- Ensuring an EC2 instance has the desired IAM configuration or state.
- Standardizing security group ingress/egress rules.
- Creating or deleting EBS snapshots.
- Creating or deleting DynamoDB backups.
- Updating S3 bucket configuration.
- Starting, stopping, or restarting EC2 and other AWS resources.

For associations running Automation, configure **AutomationAssumeRole** in the runbook parameters. State Manager uses this role to call the AWS services required by the runbook. Configuring rate controls helps roll out Automation across a fleet.

### 4.4 Choosing a Document by Where the Configuration Lives

| Question | Appropriate Choice |
|---|---|
| Need to install packages or edit files inside Linux/Windows? | Command document |
| Need to apply a built-in policy to managed nodes? | Policy document |
| Need to call EC2, S3, EBS, DynamoDB, or AWS services via APIs? | Automation runbook |
| Need to check state periodically and auto-remediate drift? | Association with an idempotent document |
| Need to run a one-time task on a maintenance schedule with a cutoff? | Consider Automation or Maintenance Windows depending on requirements |

## 5. Prerequisites for a Node to Become a Managed Node

State Manager can apply associations only to nodes already managed by Systems Manager.

For an EC2 instance, the basic prerequisites include:

1. SSM Agent is installed and running on a supported operating system.
2. The instance has an IAM instance profile or is managed via Default Host Management Configuration.
3. The role grants the permissions SSM Agent needs to register and communicate with Systems Manager.
4. The instance can reach Systems Manager endpoints over the Internet/NAT or appropriate VPC interface endpoints.
5. The node appears in the target AWS account and Region.

A commonly used policy for the instance profile is **AmazonSSMManagedInstanceCore** or an equivalent policy per current AWS guidance. Do not attach broad administrative privileges to an instance just to make it appear in Systems Manager.

### 5.1 EC2 Instances

Connection flow:

1. The EC2 instance starts SSM Agent.
2. The agent retrieves credentials from the instance profile or configured host management mechanism.
3. The agent connects to Systems Manager endpoints.
4. Systems Manager registers the node and reports its managed node status.
5. State Manager can target the node by ID or tags.

If the instance lacks outbound Internet access, you can create VPC interface endpoints for the required Systems Manager services. Depending on the Region and setup, check the **ssm**, **ssmmessages**, and **ec2messages** endpoints along with DNS, security groups, and routes.

### 5.2 Hybrid and Multicloud Servers

State Manager can also manage servers outside AWS, such as on-premises servers or VMs in other cloud providers.

General workflow:

1. Create a hybrid activation in Systems Manager.
2. Specify the node limit and activation expiration.
3. Use the activation code and activation ID to register the server.
4. Install and start SSM Agent.
5. The agent receives credentials issued during registration.
6. Confirm the node appears as a managed node.
7. Assign tags for grouping and create associations.

For non-EC2 servers, you need an appropriate IAM service role for hybrid environments and must protect credentials on the OS. Do not reuse activation credentials carelessly across arbitrary hosts or store them in readable scripts.

### 5.3 Verifying Managed Nodes

List nodes with the CLI:

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1
~~~

Inspect a specific node by filtering `InstanceInformationList` by `InstanceId`. If a node does not appear, check SSM Agent, IAM permissions, endpoint connectivity, OS support, and Region. Status `Online` indicates the agent is communicating with Systems Manager; `Offline` must be investigated before creating associations.

## 6. Selecting Targets for an Association

Targets define which resources receive the configuration. State Manager supports common selection methods:

| Target | When to Use |
|---|---|
| Instance ID / managed node ID | Testing or managing a specific set of nodes |
| Tags | Grouping nodes by environment, role, or application |
| AWS Resource Groups | Selecting resources by query or CloudFormation stack |
| All managed nodes | Applying a baseline across every node in the current account and Region |

Tag examples:

- **Environment=Production**
- **OperatingSystem=Linux**
- **Application=Checkout**
- **PatchGroup=ProdLinux**

An association installing CloudWatch Agent can target **Environment=Production** and **OperatingSystem=Linux**. Using tags lets newly launched resources join the management group automatically once tagged accordingly.

### 6.1 Targeting by Tags

When an association uses a Command or Policy document, newly created nodes bearing matching tags can automatically receive the association, run initially, and then continue on schedule. When the tag is removed, the node leaves the target set.

This is the recommended approach for fleet-wide associations managing nodes.

There are tag key limits: the console supports at most one tag key for an Automation association and five tag keys for a Command association; the AWS CLI supports up to five tag keys. Declared tag keys must exist on the node. If more complex conditions are needed, use AWS Resource Groups.

### 6.2 Targeting by Resource Groups

A Resource Group can collect resources based on tags or a CloudFormation stack. An association can target the nodes returned by the group's query.

Limits to keep in mind:

- One association can target at most one Resource Group.
- Nested groups or multiple groups in a single association are not supported.
- For tag-based groups, tag keys and values are subject to limits per AWS documentation.
- When a Resource Group is deleted, nodes in the group no longer receive that association; delete the association targeting that group per procedure.

Permission to create an association targeting a Resource Group can be equivalent to root-level control over the EC2 instances in that group because documents can execute OS commands. Grant this permission only to trusted administrators.

### 6.3 Targeting All Managed Nodes

Targeting **InstanceIds=\*** applies the association to all managed nodes in the current account and Region. Newly registered nodes can have the association applied upon registration.

This is a broad scope. Before using it, verify the document, permissions, concurrency, and OS compatibility across the entire fleet.

### 6.4 Automation Runbook Targets

Automation associations have their own targeting mechanism. You can target by tags, Resource Groups, or parameter values. With parameter values, Systems Manager launches a child automation for each value; up to 50 parameter values can be targeted.

When you want an Automation association to automatically update as new nodes arrive, AWS-supported prerequisites must be met. Currently, automatic target node updates for Automation runbooks are supported in certain Quick Setup associations and when the runbook declares appropriate resource types such as **AWS::EC2::Instance** or **AWS::SSM::ManagedInstance**. Do not assume every CLI-created Automation association automatically picks up new nodes the same way Command/Policy associations do.

## 7. Schedules: Cron, Rate, and Offset

An association can run immediately upon creation, on a schedule, or manually on demand. Schedules are specified using cron or rate expressions.

| Schedule Type | Example | Meaning |
|---|---|---|
| Rate | **rate(30 minutes)** | Runs every 30 minutes |
| Rate | **rate(1 day)** | Runs every day |
| Cron | **cron(0 2 ? \* SUN \*)** | Sundays at 02:00 UTC |
| Cron | **cron(30 23 ? \* TUE#3 \*)** | Third Tuesday of the month at 23:30 UTC |

### 7.1 Schedule Constraints

For State Manager associations:

- The minimum interval is 30 minutes.
- Rate expressions must be 30 minutes or more and less than 31 days.
- Cron expressions do not support specifying months as Maintenance Windows do.
- Cron schedules use UTC.
- Expressions must conform to the format supported by Systems Manager.

For example, **rate(15 minutes)** is invalid for a State Manager association. If faster execution is needed, choose another suitable mechanism rather than trying to push association schedules below the limit.

### 7.2 Schedule Offset

Schedule offset lets you delay an association by a number of days after a scheduled cron date. For example, an association can run three days after the second Thursday of the month.

Offset accepts values from 1 to 6 days. To use offset, select **Apply association only at the next specified Cron interval** in the console or set **ApplyOnlyAtCronInterval=true** via the API/CLI. When enabled, the association does not run immediately upon creation and waits until the next cron interval. Offset does not apply to rate expressions.

### 7.3 Choosing Rate vs. Cron

Use rate when configuration should be applied at steady intervals, such as checking a service daily or updating SSM Agent weekly. Use cron when execution must align to a specific wall-clock time, such as before business hours or on a particular day of the week.

For Automation associations, AWS recommends rate expressions in many cases because Systems Manager can retry Automations after throttling caused by hitting concurrent automation limits.

## 8. When Does an Association Run?

By default, State Manager runs an association immediately upon creation and then continues on schedule. Aside from the periodic schedule, an association can also run when:

- A user edits and saves the association.
- The referenced document version is updated.
- An operator chooses Apply association now or calls the corresponding API.
- A managed node appears for the first time, returns after missing a schedule, or comes back after an extended offline period.
- Targets change and meet association update conditions.

When an association is concurrency-limited and a node misses the current interval, State Manager can retry in the next interval. Skipped intervals can be viewed in Execution History.

If an association is created for a new resource and you do not want immediate execution on target changes, use **Apply association only at the next specified Cron interval** where supported. This helps avoid running a costly Automation every time the fleet scales out.

## 9. Creating an Association with the AWS CLI

The following example creates an association to install CloudWatch Agent on Linux production nodes. The illustrative account and Region are **ap-southeast-1**.

~~~bash
aws ssm create-association \
  --association-name install-cloudwatch-agent-production \
  --name AWS-ConfigureAWSPackage \
  --document-version '$DEFAULT' \
  --targets Key=tag:Environment,Values=Production \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"]}' \
  --schedule-expression 'rate(1 day)' \
  --compliance-severity HIGH \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --max-concurrency '10%' \
  --max-errors '1' \
  --region ap-southeast-1
~~~

Replace the account ID and role ARN with actual values. The association dispatch role must trust Systems Manager and have appropriate command-sending permissions. EC2 instances must also have permissions for SSM Agent and package downloads.

Key parameters:

- **--name:** SSM document to use.
- **--document-version:** document version; **$DEFAULT** selects the default version.
- **--targets:** group of managed nodes receiving the association.
- **--parameters:** input parameters passed to the document.
- **--schedule-expression:** execution schedule.
- **--compliance-severity:** severity level reported for compliance.
- **--association-dispatch-assume-role:** role State Manager assumes when dispatching.
- **--max-concurrency:** maximum concurrent nodes.
- **--max-errors:** maximum errors before halting dispatch to remaining targets.

Creating an association triggers an initial run by default. Test on a small group before expanding.

## 10. Creating a Custom Command Document to Keep a Service Running

AWS managed documents cover many common tasks. When custom logic is needed, you can author a custom Command document.

The following example is strictly for Linux systems using systemd. The document checks whether the CloudWatch Agent service exists, enables it, and starts it. If the service is not installed, the document exits with an error so the association reports failure instead of false success.

~~~yaml
schemaVersion: '2.2'
description: Ensure Amazon CloudWatch Agent service is enabled and running
mainSteps:
  - action: aws:runShellScript
    name: ensureCloudWatchAgent
    inputs:
      runCommand:
        - |
          set -eu
          if ! systemctl list-unit-files --type=service | grep -q '^amazon-cloudwatch-agent.service'; then
            echo "CloudWatch Agent service is not installed" >&2
            exit 1
          fi
          systemctl enable --now amazon-cloudwatch-agent
          systemctl is-active --quiet amazon-cloudwatch-agent
~~~

Create the document:

~~~bash
aws ssm create-document \
  --name EnsureCloudWatchAgentRunning \
  --document-type Command \
  --document-format YAML \
  --content file://ensure-cloudwatch-agent-running.yaml \
  --region ap-southeast-1
~~~

Create the association for the Linux production group:

~~~bash
aws ssm create-association \
  --association-name ensure-cloudwatch-agent-running \
  --name EnsureCloudWatchAgentRunning \
  --targets Key=tag:Environment,Values=Production \
  --schedule-expression 'rate(30 minutes)' \
  --compliance-severity HIGH \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --max-concurrency '10%' \
  --max-errors '1' \
  --region ap-southeast-1
~~~

This document only checks and maintains service state. Package installation is handled separately using `AWS-ConfigureAWSPackage` or an image/bootstrap workflow. Separating installation from service enforcement makes package errors easier to investigate.

To target Windows, create a separate document using **aws:runPowerShellScript** and check the corresponding Windows Service. Never run systemd commands on Windows nodes.

## 11. Using an Automation Association to Manage AWS Resources

State Manager can also run Automation runbooks on a schedule to maintain AWS resource states.

Example: a development team wants to stop EC2 instances tagged **Environment=Development** on Sunday evenings to reduce runtime. They can use a reviewed internal runbook such as **Company-StopTaggedDevelopmentInstances**.

Illustrative CLI example:

~~~bash
aws ssm create-association \
  --association-name stop-development-instances \
  --name Company-StopTaggedDevelopmentInstances \
  --targets Key=tag:Environment,Values=Development \
  --parameters AutomationAssumeRole=arn:aws:iam::123456789012:role/StateManagerAutomationExecutionRole \
  --automation-target-parameter-name InstanceId \
  --schedule-expression 'cron(0 20 ? * SUN *)' \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --region ap-southeast-1
~~~

Here there are two distinct roles:

- **StateManagerAssociationDispatchRole** allows State Manager to dispatch the association and start Automation.
- **StateManagerAutomationExecutionRole** is the role the runbook assumes to call EC2 APIs.

Before using, verify the document defines the **InstanceId** and **AutomationAssumeRole** parameters and implements appropriate stop behavior. Because this example targets by tag, ensure the tag cannot accidentally match production servers.

Some runbooks can make broad changes such as modifying security groups or deleting snapshots. Read every step and IAM permission before deploying, and start with a manual test or small target group.

## 12. Rate Controls: Limiting Concurrency and Error Thresholds

When an association applies to many nodes, avoid running across the entire fleet simultaneously if the document consumes CPU, network, or restarts services.

State Manager provides two rate controls:

| Property | Meaning |
|---|---|
| Max concurrency | Number or percentage of targets allowed to run concurrently |
| Max errors | Number or percentage of errors allowed before stopping dispatch to remaining targets |

Concurrency can be expressed as an absolute number or a percentage of the target set. For example, **10** means at most 10 nodes; **10%** means at most 10% of the target set.

If an association uses targets without declaring concurrency, State Manager defaults to a maximum of 50 concurrent nodes. If error threshold is omitted, the default is 100% errors.

### 12.1 How Error Threshold Works

If max errors is set to **3**, State Manager stops sending the association to subsequent targets once the fourth error occurs. Targets already running are allowed to finish and may also fail.

If max errors is set to **10%** on 50 targets, dispatch stops after the sixth error occurs. To reduce the chance of exceeding the threshold due to many parallel targets, set concurrency to 1 during the initial rollout phase.

### 12.2 Safe Rollout Example

Suppose you have 500 production nodes and want to install an agent:

- Pilot phase: 5 targets, concurrency 1, max errors 1.
- Canary phase: 5% of fleet, concurrency 5%, max errors 1.
- Expansion phase: 10% or 20% of fleet depending on timing and impact.
- Steady state: choose concurrency based on system capacity and operational windows.

If an association is updated while nodes are running, already-started executions are allowed to finish; unstarted executions may be cancelled. After updating, the association can run again across all targets with the new concurrency.

Rate controls limit blast radius, but do not replace rollback. For risky changes, prepare recovery procedures and monitor during rollout.

## 13. IAM and Separation of Duties

State Manager involves multiple IAM layers. Merging everything into one broad administrative role makes it hard to control who can send commands, who can modify nodes, and which APIs runbooks may invoke.

### 13.1 Instance Profile or Hybrid Service Role

SSM Agent needs credentials to talk to Systems Manager. For EC2, credentials typically come from an instance profile or Default Host Management Configuration. For hybrid servers, credentials come from the IAM service role configured during activation.

This role requires node management permissions such as **AmazonSSMManagedInstanceCore** or equivalent permissions for the actual setup.

### 13.2 Association Dispatch Assume Role

State Manager assumes this role to dispatch configurations to managed nodes or invoke Automation. Its trust policy allows **ssm.amazonaws.com** to assume the role.

Sample trust policy:

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

Permissions must match the association type:

- Command/Policy associations need `ssm:SendCommand` and related permissions.
- Automation associations need `ssm:StartAutomationExecution` and related dispatch permissions.

AWS is moving away from relying on the default service-linked role for State Manager associations. Configure a custom association dispatch role to maintain explicit permission control. You can use the **ssm:AssociationDispatchAssumeRole** condition key in IAM policies to require principals to specify this role when creating/updating associations.

### 13.3 AutomationAssumeRole

`AutomationAssumeRole` is the role an Automation runbook assumes to call AWS APIs during its steps. It needs a trust relationship for Systems Manager Automation and permissions tailored to the runbook's actions.

For example, a runbook that stops EC2 instances needs `ec2:StopInstances` on the appropriate instances. A runbook modifying security groups needs permissions to read and update the relevant ingress/egress rules. Avoid `AdministratorAccess`.

### 13.4 Principal Creating the Association

The user or pipeline creating an association needs permission to create, update, view, and delete associations within its allowed scope. It also needs `iam:PassRole` to pass the association dispatch role and Automation role where applicable.

Scope the principal's permissions by:

- Allowed SSM documents.
- Allowed target tags or Resource Groups.
- Allowed association dispatch role to pass.
- Allowed Automation runbooks to run.
- AWS resources that the Automation execution role can modify.

### 13.5 Protecting Node Control Permissions

Someone allowed to create an association targeting a Resource Group of EC2 instances can run high-privilege commands across the nodes in that group. This represents fleet-wide OS control.

Do not grant `ssm:CreateAssociation` or `ssm:UpdateAssociation` broadly to developers if they are not permitted to execute commands across all targets. Separate permissions for authoring documents, approving documents, creating associations, and operating associations.

## 14. Compliance and Severity

Systems Manager Compliance aggregates status from State Manager associations and Patch Manager. For an association, compliance status can be:

- **Compliant:** the association achieved a successful state based on reported results.
- **Non-compliant:** the association failed or configuration status did not meet requirements.

When creating an association, you can assign a severity:

| Severity | Suggested Use |
|---|---|
| CRITICAL | Security or availability configurations with severe impact |
| HIGH | Critical production baselines |
| MEDIUM | Operational configurations requiring tracking |
| LOW | Low-risk maintenance tasks |
| UNSPECIFIED | Severity not yet classified |

Severity helps operations teams prioritize findings. It does not change document behavior and does not remediate resources on its own.

A common point of confusion: the **ExecutionTime** field in State Manager compliance reports represents when Systems Manager recorded/aggregated compliance, not necessarily when the association actually ran on the node. To find actual execution times and which targets ran, use association execution history and execution target details.

View compliance summaries via CLI:

~~~bash
aws ssm list-compliance-summaries \
  --region ap-southeast-1
~~~

View per-resource summaries:

~~~bash
aws ssm list-resource-compliance-summaries \
  --region ap-southeast-1
~~~

If a document merely runs commands without verifying desired state, compliance may misrepresent business requirements. Design documents to fail when conditions are not met.

## 15. Tracking Execution History and Output

Aggregate association status is insufficient for diagnosing failures. When an association fails, inspect execution history and target-level details.

Common commands:

~~~bash
aws ssm describe-association \
  --association-id 11111111-2222-3333-4444-555555555555 \
  --region ap-southeast-1
~~~

View executions:

~~~bash
aws ssm describe-association-executions \
  --association-id 11111111-2222-3333-4444-555555555555 \
  --region ap-southeast-1
~~~

View target details for an execution:

~~~bash
aws ssm describe-association-execution-targets \
  --association-id 11111111-2222-3333-4444-555555555555 \
  --execution-id 99999999-8888-7777-6666-555555555555 \
  --region ap-southeast-1
~~~

Replace illustrative IDs with the actual Association ID and Execution ID.

### 15.1 On-Node Output and Amazon S3

For Command associations, you can configure output to be saved to Amazon S3. S3 write permissions come from the EC2 instance profile or hybrid node IAM service role, not from the principal that created the association.

If the bucket is in another account, configure the bucket policy and cross-account permissions accordingly. Scope bucket prefixes by application, environment, and association ID.

### 15.2 CloudWatch and CloudTrail

CloudWatch can monitor logs of applications or agents managed by an association. If a document writes logs to files, configure CloudWatch Agent or an equivalent log-collection mechanism.

Note: API operations launched by an SSM document during an association run are not logged as CloudTrail API events as described by AWS. Retain association execution history, SSM Automation execution details, S3 output, and application logs for complete operational evidence.

## 16. Updating Associations and Managing Versions

An association can be updated when changes are needed to:

- Document version.
- Document parameters.
- Target nodes.
- Schedule expression.
- Compliance severity.
- Output location.
- Concurrency and error thresholds.
- Association dispatch role.

When an association is edited and saved, State Manager may run it again immediately. Therefore, updating a document or parameter in production should be treated as an impactful change.

### 16.1 Choosing a Document Version

There are three common ways to reference a version:

- **$DEFAULT:** uses the version currently marked as default.
- **$LATEST:** uses the newest version.
- Explicit version number: pins the association to a tested version.

Pinning versions keeps deployments predictable and prevents unexpected changes when a document is updated. To roll out a new version, test first and explicitly update the association.

If an association references **$DEFAULT** and the default version changes, or references **$LATEST** and the document is updated, State Manager may re-execute the association.

There is a limitation for cross-account shared documents: State Manager always runs the default version of a shared document, even if the console indicates a newer version was processed. When using a cross-account shared document, set its version to **default** and manage versions in the owning account.

### 16.2 Updating a Document

A document change can be applied to hundreds of nodes when the association re-runs. Safe workflow:

1. Create a new version of the document.
2. Test on a lab node.
3. Create a test association targeting a canary group.
4. Inspect output and compliance.
5. Expand targets or update the production association.
6. Monitor error thresholds and execution history.
7. Keep the previous version for rollback if needed.

### 16.3 Deleting an Association

Deleting an association stops it from running on targets. Deleting an association does not automatically uninstall packages, stop services, or revert previously applied changes.

If you need to return nodes to a prior state, create a rollback document or separate uninstall/reconfiguration procedure. Record the association ID and document version before deleting.

## 17. State Manager, Maintenance Windows, Patch Manager, and Automation

Capabilities in Systems Manager address related problems with distinct goals.

| Capability | Primary Goal | Example |
|---|---|---|
| State Manager | Maintain desired configuration by schedule and targets | Ensure an agent is installed and a service stays running |
| Maintenance Windows | Organize maintenance tasks inside a window with duration/cutoff | Restart servers during a maintenance window |
| Patch Manager | Manage scanning, installation, and compliance of patches | Install security updates per patch baseline |
| Automation | Orchestrate multi-step AWS API calls and resource actions | Snapshots, restarts, security group updates |
| Run Command | Send one-off commands to managed nodes | Run diagnostic or immediate remediation scripts |

State Manager can run Patch Manager or Automation via associations, but does not replace those specialized capabilities. Choose the tool that matches the goal and job lifecycle.

## 18. Quick Setup and Multi-Account Management

Quick Setup simplifies deploying common Systems Manager operational configurations. It can create the State Manager associations, IAM roles, and supporting resources needed.

Quick Setup can apply to a single account or multiple accounts/Regions via AWS Organizations. Its dashboard displays deployment status and association status.

For example, Quick Setup configurations can:

- Configure host management for EC2.
- Enable inventory collection.
- Set up periodic patch scans.
- Update SSM Agent on a schedule.
- Configure fleet best practices.

Quick Setup also checks periodically for configuration drift on the options it manages and attempts remediation. When a configuration is created via Quick Setup, inspect the associations and roles it deployed before creating duplicate associations.

When deploying across multiple accounts:

1. Choose the management account or delegated administrator per your governance model.
2. Identify target OUs/accounts and Regions.
3. Verify AWS Organizations integration permissions.
4. Deploy the Quick Setup configuration.
5. Monitor stack/deployment status and association status.
6. Investigate accounts without managed nodes or unmet prerequisites.
7. Check service quotas and Regional availability.

Quick Setup configuration types can vary by Region. Check current Regional support before designing an organization-wide rollout.

## 19. Hybrid and Multicloud Operations

State Manager helps operations teams apply the same baseline to EC2 instances and hybrid servers registered with Systems Manager.

For example, an enterprise may have:

- EC2 Linux in AWS.
- EC2 Windows in AWS.
- Physical servers in an on-premises datacenter.
- Virtual machines in another cloud provider.

You can apply consistent tags such as **Environment**, **OperatingSystem**, and **Application** to create corresponding associations.

Targets must be separated by operating system. A document using systemd only suits Linux with systemd. A document using PowerShell only suits Windows Server. Never attach a single document to all managed nodes if it is incompatible with some operating systems.

For hybrid servers, monitor activation expiration, the IAM service role, SSM Agent version, network connectivity, and node re-registration. If a node is offline, an association cannot complete on that node until the agent reconnects.

## 20. Cost and Operational Limits

When designing State Manager at scale, monitor:

- Number of associations per managed node.
- Number of targets per association.
- Schedule frequency and document execution duration.
- Number of concurrent Automation executions.
- Automation, S3 output, CloudWatch Logs, and downstream service costs.
- Node offline duration and missed executions.
- Document updates that trigger association re-runs.

Key limits per current AWS documentation:

| Item | Limit or Behavior |
|---|---|
| Associations per managed node | Maximum 20 |
| State Manager schedule interval | Minimum 30 minutes |
| Automation associations | Count toward the account's concurrent Automation limit |
| Concurrent Automation executions | Account quota is typically 100; verify actual Service Quotas |
| Parameter values when targeting Automation | Maximum 50 values |
| Target sets larger than 1,000 nodes | Status aggregation may be throttled hourly |
| Resource Groups in one association | Maximum one group |

When managing more than 1,000 nodes, aggregated status metrics may update under hourly throttling, so dashboards may not immediately reflect every target change. Use execution history and target-level details when precise investigation is needed.

Do not configure overly frequent State Manager schedules if the document is expensive or alters system state. An association can also re-run due to document updates or association updates, so account for unscheduled runs as well.

## 21. Architecture Example: Production Fleet Baseline

Suppose an organization runs 300 EC2 Linux instances and 50 Windows instances. Goals:

- Every node is managed by Systems Manager.
- CloudWatch Agent is installed.
- The agent service is running.
- SSM Agent is updated periodically.
- Association failures are reported by severity.
- Configuration changes roll out in small batches.

Design:

1. EC2 instances use an instance profile or Default Host Management Configuration.
2. SSM Agent registers nodes and connects to Systems Manager endpoints.
3. Tags group nodes by **Environment**, **OperatingSystem**, and **Application**.
4. Linux and Windows associations use separate documents.
5. Rate controls limit concurrency to prevent fleet-wide impact.
6. Compliance severity is assigned by baseline importance.
7. Output and execution history are retained per operational policy.
8. Quick Setup can deploy foundational configurations at the organization level.

~~~mermaid
flowchart TD
    A["AWS Organizations / Accounts"] --> B["Quick Setup and IAM roles"]
    B --> C["EC2 and hybrid managed nodes"]
    C --> D["SSM Agent connectivity"]
    D --> E["State Manager associations"]
    E --> F["Linux document"]
    E --> G["Windows document"]
    E --> H["Automation runbooks"]
    F --> I["Desired OS configuration"]
    G --> I
    H --> J["AWS resource configuration"]
    I --> K["Compliance and execution history"]
    J --> K
    K --> L["S3 output / CloudWatch / Operations"]
~~~

Do not share a single association across Linux and Windows if execution steps differ. Separating associations helps control scope, document versions, schedules, and platform-specific errors.

## 22. Lab: Installing and Maintaining CloudWatch Agent with State Manager

This lab uses a group of test EC2 Linux instances in the **ap-southeast-1** Region. Do not use a production fleet.

### Step 1: Prepare Managed Nodes

- Launch test EC2 Linux instances.
- Install SSM Agent and confirm the agent is running.
- Attach an instance profile with the required Systems Manager permissions.
- Ensure instances can reach Systems Manager endpoints.
- Confirm nodes appear in Fleet Manager or Managed nodes.

### Step 2: Apply Tags

Apply tags:

~~~text
Environment=StateManagerLab
OperatingSystem=Linux
Application=Observability
~~~

Tags ensure the association targets only the test group.

### Step 3: Verify the Package Document

Verify that **AWS-ConfigureAWSPackage** is available in the Region along with its required parameters. This document installs Distributor-supported packages.

### Step 4: Create the Association

Run the CLI:

~~~bash
aws ssm create-association \
  --association-name install-cloudwatch-agent-lab \
  --name AWS-ConfigureAWSPackage \
  --document-version '$DEFAULT' \
  --targets Key=tag:Environment,Values=StateManagerLab \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"]}' \
  --schedule-expression 'rate(1 day)' \
  --compliance-severity MEDIUM \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --max-concurrency '1' \
  --max-errors '1' \
  --region ap-southeast-1
~~~

Replace the account ID and role ARN with your lab values. If the dispatch role has not been created yet, create the Systems Manager trust policy and appropriate permissions first.

### Step 5: Inspect the Association

List associations:

~~~bash
aws ssm list-associations \
  --association-filter-list key=AssociationName,value=install-cloudwatch-agent-lab \
  --region ap-southeast-1
~~~

Save the returned Association ID. Use **describe-association** and **describe-association-executions** to check status and history.

### Step 6: Verify on the Node

Connect to the test EC2 instance and check the package and service:

~~~bash
sudo systemctl is-enabled amazon-cloudwatch-agent
sudo systemctl is-active amazon-cloudwatch-agent
~~~

If the package is installed but the service is not configured, create a separate association with a custom document to enforce service state. Do not treat package presence as proof that the agent is sending telemetry.

### Step 7: Check Compliance

Open Systems Manager Compliance and locate the new association. Inspect status and severity. If the association failed, open execution history, select the target, and read the detailed output.

### Step 8: Test Configuration Drift

Stop CloudWatch Agent on the test machine:

~~~bash
sudo systemctl stop amazon-cloudwatch-agent
~~~

Run the association manually or wait for the schedule if you created the service-maintenance document. Confirm the service returns to the `active` state. With an association that only installs the package, stopping the service does not necessarily cause the association to fail; a service-checking document is required if the desired state includes running status.

### Step 9: Cleanup

- Delete the lab association.
- If no longer needed, uninstall the package or keep it per test requirements.
- Clean up lab tags and EC2 instances when done.
- Delete lab IAM roles if no remaining associations use them.

Deleting an association does not automatically uninstall packages already installed on nodes.

## 23. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Node missing from Systems Manager | SSM Agent not installed/running or unsupported OS | Check agent and operating system |
| Node Offline | Wrong instance profile, service role, or endpoint connectivity | Check IAM, DNS, routes, and VPC endpoints |
| Association finds no targets | Wrong tag key/value or target in wrong Region/account | Check tags and scope |
| Association stuck Pending | Node offline or agent not receiving commands | Check managed node status and SSM Agent logs |
| Association Failed | Document returned an error code or lacked permissions | Inspect execution history and output |
| Package fails to install | Wrong package name/version or Distributor access | Check document parameters and package |
| Linux service not running | Missing package or wrong service name | Check unit file and OS logs |
| Association runs unexpectedly often | Association/document updates or target changes triggered runs | Check update history and schedule |
| New node does not get Automation association | Automation target-update conditions unmet | Check Quick Setup, resource type, parameters, and targets |
| Association runs wrong version | Document version points to `$DEFAULT`, `$LATEST`, or shared doc | Check document version and owning account |
| S3 output missing | Instance profile/hybrid role lacks S3 permissions | Check node role and bucket policy |
| Compliance timestamp mismatches execution | Timestamp is when compliance was captured | Use association execution history |
| Automation throttled | Exceeded concurrent Automation limit | Use rate schedule, reduce concurrency, and check quotas |
| Many fleet nodes failing | Max concurrency/error threshold too high or incompatible doc | Roll out via canary, lower concurrency, separate OSes |
| Resource Group target returns InvalidTarget | Group exceeds tag limits or invalid query | Check Resource Group configuration |

### Failure Investigation Workflow

1. Identify the Association ID and target node/resource.
2. Check association status and the latest execution.
3. Check document name, version, and parameters.
4. Confirm the node is Online in the right Region.
5. Check the association dispatch role and `AutomationAssumeRole` if using a runbook.
6. Open execution target details to pinpoint the failing step.
7. Read SSM Agent logs or SSM Automation step output.
8. Verify target tags and document compatibility with the OS.
9. Re-test on a single test node after fixing.
10. Expand rollout only after the association succeeds consistently.

## 24. Design Mistakes to Avoid

- **Non-idempotent documents:** each re-run creates duplicate configuration or breaks existing state.
- **Overly broad targets:** a new association may execute across the entire production fleet.
- **Lack of standardized tags:** node groups become hard to manage consistently at scale.
- **Unpinned document versions:** document edits can unexpectedly re-trigger associations.
- **Using AdministratorAccess:** expands blast radius if a document has bugs or is modified.
- **Merging dispatch role and Automation role:** obscures separation between command dispatch and AWS resource modification.
- **Omitting rate controls:** many nodes restart or mutate simultaneously.
- **Skipping final state verification:** an association reports `Success` even when desired state is unmet.
- **Confusing compliance timestamp with execution time:** leads to wrong conclusions during investigations.
- **Assuming Automation associations auto-target new nodes:** AWS-supported target update criteria must be met.
- **Not saving output:** makes it hard to identify which nodes failed and at which step.
- **No rollback plan:** the association keeps re-applying faulty configuration across cycles.
- **Using associations for every task:** maintenance tasks with duration and cutoffs belong in Maintenance Windows.
- **Ignoring schedule limits:** associations cannot run faster than every 30 minutes and cron has specific constraints.

## 25. Best Practices

### Desired State

- Express desired state with verifiable conditions.
- Write idempotent documents that include a verification step.
- Separate package installation from service enforcement when appropriate.
- Use separate documents per operating system or compatibility group.
- Store custom documents in version control and review changes.

### Targets and Rollout

- Use consistent tags to group by environment and application.
- Start with a lab node, then canary.
- Limit concurrency and error thresholds.
- Verify target expansion before creating associations.
- Restrict permission to create associations targeting Resource Groups to fleet administrators.

### IAM and Security

- Use instance profiles or Default Host Management Configuration with minimal permissions.
- Use a custom association dispatch role.
- Use a separate `AutomationAssumeRole` for runbooks.
- Scope `iam:PassRole` to specific roles and trusted services.
- Restrict who can create, edit, or delete associations.
- Never place secrets directly in document parameters or command output.
- Protect S3 output buckets with encryption, bucket policies, and lifecycle rules.

### Operations

- Assign compliance severity based on impact.
- Monitor association execution history and target details.
- Centralize logs and retain required output.
- Monitor offline nodes and failed associations.
- Manage document versions and rollout schedules.
- Use Quick Setup when deploying baselines across multiple accounts/Regions.
- Verify quotas and costs before scaling the fleet.

## 26. Practice Exercises

1. What components make up a State Manager association?
2. Why should documents be idempotent when maintaining desired state?
3. When should you use a Command document vs. an Automation runbook?
4. An EC2 instance does not appear in Managed nodes. Which conditions do you check?
5. When should you target by tags instead of listing instance IDs?
6. If an association targets `Environment=Production`, can a new node with that tag receive the association?
7. Why do Automation associations have specific rules for automatically updating target nodes?
8. Is `rate(15 minutes)` valid for State Manager? Why or why not?
9. In what scenario is schedule offset used?
10. When does an association run immediately outside its schedule?
11. What does max concurrency `10%` mean for 200 targets?
12. If max errors is `2`, when does State Manager stop dispatching to subsequent targets?
13. Why separate the association dispatch role from `AutomationAssumeRole`?
14. Who provides S3 output write permission for an association: the creator principal or the node's instance profile?
15. Is Compliance `ExecutionTime` always the actual time the association executed?
16. How do you find which node failed in an association execution?
17. When should you use Maintenance Windows instead of State Manager?
18. Why can document version `$LATEST` cause unscheduled runs?
19. An association installed a package successfully, but the service is stopped. What condition should be added?
20. Does deleting an association automatically uninstall packages or revert configurations?

### Answer Hints

1. Document, targets, parameters, schedule, document version, IAM roles, compliance severity, and rate controls.
2. So repeated runs do not create duplicate changes and always converge to the same state.
3. Command for inside-OS actions; Automation for AWS APIs and resource-level workflows.
4. SSM Agent, agent status, IAM instance profile or host management, endpoint connectivity, OS support, and Region.
5. When managing dynamic fleets by tags so new nodes join automatically.
6. Yes for Command/Policy associations via target updates; Automation has specific support requirements.
7. The Automation runbook must declare target parameters/resource types and the association must meet AWS-supported conditions.
8. No. State Manager associations require a minimum 30-minute interval.
9. When you want to run a few days after a cron date, such as after Patch Tuesday.
10. Upon association creation, association/document updates, manual starts, or when a target node returns in supported cases.
11. Up to roughly 20 targets running concurrently.
12. When the third error occurs.
13. The dispatch role lets State Manager send commands/launch Automation; `AutomationAssumeRole` grants permissions for APIs inside the runbook.
14. The EC2 instance profile or hybrid node IAM service role.
15. No. That is when compliance was captured; check execution history for actual run time.
16. Use `DescribeAssociationExecutionTargets` with the Association ID and Execution ID.
17. When you need a maintenance schedule with duration, cutoff, and task orchestration within a maintenance window.
18. Document updates can trigger the association to re-run.
19. Add a step to verify and maintain the service running, not just install the package.
20. No. The association stops running, but previously applied changes persist until a rollback/uninstall workflow runs.

## 27. Interview Questions

### What problem does State Manager solve?

State Manager automatically applies desired configuration to managed nodes or AWS resources via associations. It reduces configuration drift and standardizes fleet operations.

### What is an association?

An association links an SSM document, targets, parameters, and a schedule. It defines what configuration to apply and how State Manager distributes it.

### Is State Manager a real-time configuration monitoring tool?

No. State Manager applies configurations when an association runs: immediately upon creation by default, on schedule, and during certain update/target events. The interval between runs creates a drift detection lag.

### Why should documents be idempotent?

Because associations run repeatedly. An idempotent document guarantees a stable final state and avoids making redundant changes.

### What is the difference between a Command association and an Automation association?

A Command association runs commands on managed nodes via SSM Agent. An Automation association invokes a runbook to execute workflows on AWS resources or other orchestration steps.

### What is the benefit of targeting by tag in State Manager?

Tags let you apply an association to nodes sharing a role or environment. When a new node carries matching tags, a Command/Policy association can apply automatically to that node.

### When should Resource Groups be used?

When targets must come from a query or CloudFormation stack and aggregate many nodes by governance criteria. Check Resource Group limits and protect association creation permissions.

### Why are rate controls needed?

To avoid executing simultaneously across too many nodes, reduce workload impact, and halt rollout when failure rates exceed a threshold.

### Does association compliance replace execution history?

No. Compliance shows aggregate status and severity. Execution history shows run times, targets, and error details.

### How does Quick Setup relate to State Manager?

Quick Setup can create State Manager associations and supporting resources to deploy operational configurations across one or more accounts/Regions.

### Why are two roles needed when an Automation association runs?

The association dispatch role allows State Manager to dispatch or start Automation. `AutomationAssumeRole` grants the runbook permissions to call AWS APIs in each step.

### Does State Manager replace Maintenance Windows?

No. State Manager enforces configurations by schedule and target. Maintenance Windows coordinate maintenance tasks inside a window with duration and cutoff.

## 28. Pre-Production Checklist

### Managed nodes

- [ ] SSM Agent is installed and running on a supported OS.
- [ ] EC2 has an instance profile or Default Host Management Configuration.
- [ ] Hybrid nodes have valid activations and service roles.
- [ ] Nodes can reach Systems Manager endpoints.
- [ ] Nodes appear Online in the correct account and Region.
- [ ] Tags are standardized by environment and application.

### Associations and documents

- [ ] Desired state has verifiable conditions.
- [ ] Documents are reviewed and tested.
- [ ] Documents are idempotent and fail when verification fails.
- [ ] Documents are compatible with OS and target resource types.
- [ ] Document versions are pinned or have a controlled update workflow.
- [ ] Target scope is verified before rollout.
- [ ] Schedules comply with minimum intervals and UTC.
- [ ] Option to skip immediate execution on creation is configured if needed.

### IAM and rollout

- [ ] Association dispatch role has the right trust relationship.
- [ ] `AutomationAssumeRole` has only required permissions.
- [ ] Association-creating principal has scoped permissions and `PassRole`.
- [ ] Concurrency and error thresholds are configured.
- [ ] Canary succeeded before wide rollout.
- [ ] Change Calendar or CloudWatch alarms are used where appropriate.

### Monitoring and recovery

- [ ] Compliance severity is assigned.
- [ ] Association history and target details are accessible.
- [ ] S3 output has an appropriate bucket policy and encryption.
- [ ] OS logs or CloudWatch Agent logs are available when needed.
- [ ] Rollback/uninstall procedures exist.
- [ ] Alerts exist for failed associations and offline nodes.
- [ ] Processes exist for handling drift and exceptions.

## 29. Official Reference Documentation

- [AWS Systems Manager State Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-state.html)
- [Understanding how State Manager works](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-about.html)
- [Creating associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations-creating.html)
- [Understanding targets and rate controls in State Manager associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-state-manager-targets-and-rate-controls.html)
- [Cron and rate expressions for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/reference-cron-and-rate-expressions.html)
- [Scheduling automations with State Manager associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/scheduling-automations-state-manager-associations.html)
- [About State Manager association compliance](https://docs.aws.amazon.com/systems-manager/latest/userguide/compliance-about.html)
- [Viewing association histories](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations-history.html)
- [Editing and creating a new version of an association](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations-edit.html)
- [Setting up managed nodes for AWS Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-setting-up-nodes.html)
- [Troubleshooting managed node availability](https://docs.aws.amazon.com/systems-manager/latest/userguide/fleet-manager-troubleshooting-managed-nodes.html)
- [SSM Agent technical details](https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent-technical-details.html)
- [AWS Systems Manager Quick Setup](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-quick-setup.html)
- [Supported Quick Setup configuration types](https://docs.aws.amazon.com/systems-manager/latest/userguide/quick-setup-config-types.html)
- [AWS Systems Manager service quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html)

