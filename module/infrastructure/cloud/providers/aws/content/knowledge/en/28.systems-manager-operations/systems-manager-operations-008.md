# Maintenance Windows and Blast-Radius Controls

> **Chapter:** Systems Manager Operations  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; build skills to select services and design and deploy secure, observable, recoverable, and cost-controlled applications.

An OS patch, agent upgrade, or configuration change may require rebooting servers, draining nodes from a load balancer, or interrupting a service. Running changes during peak hours or simultaneously across the entire fleet can spread operational failures before the team can halt the rollout.

AWS Systems Manager Maintenance Windows lets you define time windows during which maintenance tasks may start, choose exact target resources, order tasks, and set concurrency/error limits. This lesson focuses on designing maintenance windows so changes occur during approved windows with a controlled blast radius.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of Maintenance Windows in AWS operations.
2. Distinguish Maintenance Windows from State Manager and Patch Manager.
3. Design schedules using cron, rate, or at expressions; understand timezone, start/end dates, and schedule offsets.
4. Calculate the cutoff time from duration and cutoff hours.
5. Select targets using instance IDs, tags, or AWS Resource Groups.
6. Choose the appropriate task type among Run Command, Automation, Lambda, and Step Functions.
7. Order tasks using priority and understand which tasks run in parallel.
8. Configure `MaxConcurrency` and `MaxErrors` to limit blast radius.
9. Distinguish `CONTINUE_TASK` from `CANCEL_TASK` when cutoff arrives.
10. Design IAM service roles, task permissions, logging, and monitoring following least privilege.
11. Implement canary testing, ring-based rollouts, and rollbacks on failure.
12. Investigate task executions, target resolution, permission errors, and skipped runs.

## 2. What Problem Does Maintenance Windows Solve?

Maintenance Windows is an AWS Systems Manager capability for scheduling potentially disruptive actions on managed nodes or supported AWS resources. Examples:

- Installing security patches or updating packages.
- Upgrading SSM Agent or host software.
- Rebooting instances during a change window.
- Draining nodes from a load balancer, updating, running health checks, and rejoining nodes.
- Running an Automation runbook to create AMIs or execute resource change sequences.
- Invoking Lambda or Step Functions to orchestrate maintenance workflows.

A Maintenance Window is not a single patch command. It is an orchestration framework comprising a schedule, duration, targets, and registered tasks. Each task has its own configuration for task type, priority, concurrency, error threshold, cutoff behavior, and execution role.

### 2.1. Separating Permitted Launch Time from Actual Task Runtime

A maintenance window defines when Systems Manager is allowed to start task invocations. Once a task starts, it may continue running after the window ends. Therefore:

- `Duration` is the window length, not a hard timeout for every script.
- `Cutoff` is the period before the window ends when Systems Manager stops scheduling new task starts.
- `CutoffBehavior` determines how in-flight invocations are handled when cutoff arrives.
- Timeouts for commands, Automation steps, or workflows must be configured separately.

Do not design schedules assuming every process automatically stops the moment the window closes.

### 2.2. Components of a Maintenance Window

~~~mermaid
flowchart TD
    S["Schedule<br/>cron / rate / at"] --> W["Maintenance Window"]
    D["Duration + Cutoff"] --> W
    W --> T["Registered targets<br/>IDs / tags / Resource Groups"]
    W --> A["Registered tasks"]
    T --> A
    A --> P["Priority order"]
    P --> R["Rate controls<br/>MaxConcurrency / MaxErrors"]
    R --> X["Run Command / Automation / Lambda / Step Functions"]
    X --> M["Logs, status, alarms, EventBridge"]
~~~

| Component | Question to Answer |
| --- | --- |
| Schedule | When does the window activate? |
| Duration | How long is the window open at most? |
| Cutoff | How long before closing should new task scheduling stop? |
| Targets | Which resources may receive tasks? |
| Tasks | Which actions need to run? |
| Priority | Which task must be scheduled first? |
| MaxConcurrency | How many targets are processed simultaneously? |
| MaxErrors | How many errors are allowed before halting further scheduling? |
| CutoffBehavior | How are in-flight task invocations handled at cutoff? |

## 3. When to Use Maintenance Windows?

Systems Manager provides multiple operational tools with distinct purposes. Choosing the right tool avoids misusing maintenance schedules to solve continuous state management problems.

| Tool | Primary Purpose | Example |
| --- | --- | --- |
| Maintenance Windows | Run actions during a defined time window | Weekend production patching |
| State Manager | Maintain desired configuration state | Ensure agents or configs always match required versions/rules |
| Patch Manager | Define patch baselines and coordinate patching | Approve security updates by OS |
| Automation | Run multi-step runbooks on AWS resources | Create AMIs, restart instances, update resources |
| Run Command | Run commands/scripts on managed nodes | Inspect services, install packages, restart processes |

Maintenance Windows is ideal when teams must control *when* changes begin, sequence multiple tasks, and bound how many targets are affected.

### 3.1. Maintenance Windows vs. State Manager

State Manager maintains desired state and can apply associations when new nodes appear or configuration needs enforcement. Maintenance Windows executes actions during a designated time period; it does not automatically keep resources in desired state after a task finishes.

Examples:

- Want every managed node to always keep SSM Agent configured to standard: consider State Manager.
- Want to upgrade SSM Agent at 02:00 Sunday in batches with error limits: consider a Maintenance Window.

State Manager fits compliance/configuration drift; Maintenance Windows fits work with an approved start window.

### 3.2. Maintenance Windows vs. Patch Manager

Patch Manager defines patch baselines, approval rules, and patching operations. Maintenance Windows can serve as the scheduled period hosting patching tasks, such as Run Command or Automation tasks using appropriate documents.

For multi-account/multi-Region patching, AWS recommends considering Patch Policies in Systems Manager Quick Setup. A traditional Maintenance Window for patching operates within a single account and Region; do not assume a single window coordinates an entire organization automatically.

## 4. Scheduling: Cron, Rate, and At

Every Maintenance Window requires a schedule. Systems Manager supports:

- **Cron:** schedule by time of day/week/month.
- **Rate:** repeat on an interval, such as every 7 days.
- **At:** run once at a specific timestamp.

Maintenance Windows supports six-field cron expressions:

~~~text
cron(Minutes Hours Day-of-month Month Day-of-week Year)
~~~

Examples:

| Expression | Meaning |
| --- | --- |
| `cron(0 2 ? * SUN *)` | Weekly on Sunday at 02:00 |
| `cron(30 23 ? * TUE#3 *)` | 23:30 on the third Tuesday of the month |
| `cron(0 1 1 * ? *)` | 01:00 on the first day of every month |
| `rate(7 days)` | Every 7 days |
| `at(2026-12-06T02:00:00)` | Once at the specified timestamp (UTC by default) |

Maintenance Windows cron supports the month field and day-of-week options such as `MON-FRI`, `TUE#3`, and `6L`. Do not specify concrete values in both day-of-month and day-of-week simultaneously; the other field must be `?`.

### 4.1. Specifying Timezone Explicitly

You can specify an IANA timezone using `ScheduleTimezone`, for example:

- `UTC`
- `Asia/Ho_Chi_Minh`
- `Asia/Singapore`
- `America/Los_Angeles`

If maintenance follows the operations team's local time, declare the timezone rather than manually offsetting hours in cron. Timezone and `StartDate`/`EndDate` are independent settings:

- `ScheduleTimezone` sets the timezone used to interpret the schedule.
- `StartDate` and `EndDate` define the active period during which the window may run; timestamps use ISO-8601 and can carry their own offsets.

For multi-Region systems, standardize on a single time convention in the change calendar and state timezones explicitly in operational notices.

### 4.2. StartDate and EndDate

`StartDate` delays when the window becomes active. `EndDate` defines when the window stops running. Neither alters the cron/rate itself; they simply bound the active period during which the schedule is permitted to fire.

Example:

~~~bash
aws ssm create-maintenance-window \
  --name "prod-weekly-patching" \
  --description "Weekly production patching window" \
  --schedule "cron(0 2 ? * SUN *)" \
  --schedule-timezone "Asia/Ho_Chi_Minh" \
  --start-date "2026-12-01T00:00:00+07:00" \
  --end-date "2027-06-30T23:59:00+07:00" \
  --duration 4 \
  --cutoff 1 \
  --region ap-southeast-1
~~~

In this example, the schedule runs at 02:00 Sunday Vietnam time within the specified active period. Verify the actual next run time before enabling, especially when changing timezones or switching between cron and rate.

### 4.3. Schedule Offset

`ScheduleOffset` applies only to cron and takes values from 1 to 6 days. It delays execution by that many days after the cron-specified date/time.

Example:

~~~text
cron(30 23 ? * TUE#3 *)
schedule-offset = 2
~~~

The base schedule is 23:30 on the third Tuesday of the month; an offset of 2 makes the window run at 23:30 two days later. Offsets are useful when waiting on another milestone, such as a couple of days after an update cycle or release date.

If the cron date in the current cycle has already passed while the offset falls in the future, the window may wait until the next cron cycle. Do not compute the first run merely by adding the offset days to the current time.

### 4.4. Cron Frequency Limits

Maintenance Windows does not support cron schedules faster than every 5 minutes. Schedule offsets do not apply to `rate` or `at`. For risky production changes, frequent schedules are no substitute for approvals and blast-radius controls.

## 5. Duration, Cutoff, and Window End Time

When creating a Maintenance Window, two key parameters are:

- `Duration`: maximum hours of the window, from 1 to 24.
- `Cutoff`: hours before the end of duration when Systems Manager stops scheduling new task starts, from 0 to 23.

The cutoff time is calculated as:

\[
\text{Cutoff time} = \text{Window start} + \text{Duration} - \text{Cutoff}
\]

For example, window starts at 22:00, `Duration = 4`, `Cutoff = 1`:

~~~text
22:00            01:00            02:00
|----------------|----------------|
Window starts    Cutoff           Window ends
                 No new tasks
~~~

From 22:00 to 02:00 is the 4-hour duration. From 01:00 onward, Systems Manager stops starting new task invocations. Already-started tasks may continue past 02:00 depending on task type and cutoff behavior.

### 5.1. Cutoff Set to 0

`Cutoff = 0` means no buffer hours are reserved before window close to block scheduling new tasks. Tasks still must begin within the valid window period. If jobs tend to run long, set a large enough cutoff so new tasks do not start right before closing.

### 5.2. Duration Is Not a Hard Completion Deadline

Suppose a patch task starts at 01:30, the window closes at 02:00, yet patching needs 40 more minutes. The task can still run past 02:00 if configured to continue. This means:

- Do not treat duration as a script timeout.
- Configure separate timeouts for Run Command/Automation/workflows. For Run Command, `TimeoutSeconds` on the task invocation is how long to wait for command delivery to SSM Agent; script/command timeout must be configured inside the SSM document or command logic.
- Set cutoff based on the maximum runtime a new task may require.
- Have a plan to monitor tasks still running past the window.
- If the system cannot allow processes past a hard deadline, build controlled termination into the task/runbook itself.

### 5.3. Scheduling Does Not Guarantee Completion Within the Window

A Maintenance Window controls start time and dispatch scheduling. It does not guarantee all targets finish before the end time. Actual runtime also depends on:

- Target count resolved from tags/Resource Groups.
- `MaxConcurrency` and per-target processing time.
- Number of tasks and priorities.
- SSM Agent/managed node connectivity.
- Reboot duration, package downloads, and health checks.
- Wait times in Automation, approvals, or downstream services.

Before production, benchmark runtime on a canary group and estimate total fleet duration.

## 6. Selecting Targets and Controlling Resource Scope

Targets define which resources a task may affect. A valid task with the wrong target can still cause a major outage.

Maintenance Windows supports targets such as:

1. **Instance IDs:** specify exact managed nodes.
2. **Tags:** select nodes by tag key/value.
3. **AWS Resource Groups:** select resources by resource group and supported resource types.

Example tag target:

~~~text
Key=tag:Environment,Values=Production
Key=tag:Role,Values=Web
~~~

When multiple tag conditions are specified, a resource must match all declared conditions in the target group. Use tags with clear operational meaning, such as:

| Tag | Example | Purpose |
| --- | --- | --- |
| `Environment` | `Production` | Separate production from dev/staging |
| `Service` | `order-api` | Target a specific service |
| `MaintenanceRing` | `canary`, `wave-1`, `wave-2` | Partition rollouts into waves |
| `PatchGroup` | `prod-linux` | Associate patch baseline/group |
| `Owner` | `platform-team` | Identify the responsible team |

### 6.1. Selecting Instance IDs

Instance IDs suit a small one-off maintenance run or a specific canary:

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type INSTANCE \
  --targets "Key=InstanceIds,Values=i-0123456789abcdef0" \
  --name "prod-canary-node" \
  --owner-information "platform-team"
~~~

The advantage is an explicit, easy-to-review scope. The drawback is having to update the list as the fleet changes; if instances are replaced by Auto Scaling, old target IDs become stale.

### 6.2. Selecting by Tags

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type INSTANCE \
  --targets "Key=tag:Environment,Values=Production" "Key=tag:MaintenanceRing,Values=canary" \
  --name "prod-canary-ring" \
  --owner-information "platform-team"
~~~

Tag targeting suits dynamic fleets. When the window runs, Systems Manager resolves managed nodes with matching tags. Because target counts can vary, use percentage concurrency when exact fleet size is unknown.

### 6.3. Selecting by Resource Group

A Resource Group can contain multiple supported resource types. When targeting a Resource Group, filter to the exact resource types the task handles. If the group contains unrelated resource types, the task may log errors for unsupported types while still executing on valid ones.

With offline nodes, Resource Groups can still target by resource membership; tasks execute only when nodes can connect and receive commands.

Example registering a Resource Group containing EC2 instances:

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type RESOURCE_GROUP \
  --targets "Key=resource-groups:Name,Values=prod-web-nodes" "Key=resource-groups:ResourceTypeFilters,Values=AWS::EC2::INSTANCE" \
  --name "prod-web-resource-group" \
  --owner-information "platform-team" \
  --region ap-southeast-1
~~~

`RESOURCE_GROUP` is the Maintenance Windows target type; `AWS::EC2::INSTANCE` is the Resource Group's resource type filter. These two values belong to different layers and are not interchangeable.

### 6.4. AllowUnassociatedTargets

When creating a window, `AllowUnassociatedTargets` determines whether a task can target managed nodes not registered as a window target:

- `false`: tasks must use targets registered with the window.
- `true`: tasks can specify managed node IDs directly at task registration even if not in registered targets.

`true` is flexible for one-off tasks on a specific node, but makes central visibility of window targets harder. For standard operational workflows, prefer registering targets upfront to review scope.

### 6.5. Avoiding Overly Broad Tags

Before registering a task, verify:

- Do tags exist on the intended managed nodes?
- Are any non-production or unintended nodes mistakenly tagged `Environment=Production`?
- Are any tag keys missing values or using inconsistent casing?
- Does the Resource Group include unexpected resource types?
- Does the target combine databases, workers, and web nodes in the same batch?
- Are any nodes currently in an active incident or another maintenance run?

Test target resolution by listing matching resources before running destructive tasks. Never treat expected target counts as fixed when targeting by tags.

## 7. Designing Blast Radius Before Registering Tasks

Blast radius is the scope of resources that can be impacted if a task fails or a change introduces a regression. Maintenance Windows offers mechanisms to bound blast radius, but operators must design how to apply them.

### 7.1. Partitioning the Fleet into Rings

A safe rollout typically splits into:

| Ring | Example Scope | Goal |
| --- | --- | --- |
| Canary | 1 instance or 1–2% of fleet | Detect issues early |
| Wave 1 | 5–10% of fleet | Validate behavior on a small group |
| Wave 2 | 25–50% of fleet | Expand once health metrics are stable |
| Final wave | Remaining fleet | Complete after sufficient evidence |

Percentages are examples. For services with few instances or stateful nodes, use small counts and preserve spare capacity.

### 7.2. Preserving Capacity During Maintenance

If a service runs 6 instances behind a load balancer and needs at least 4 healthy instances, do not patch 3 or 4 nodes concurrently. Account for:

- Auto Scaling Group desired/minimum capacity.
- Health check grace period.
- Connection draining duration.
- Session affinity and workload state.
- Recovery headroom if an instance fails to return healthy.
- Remaining capacity if an Availability Zone experiences an outage.

Do not substitute `MaxConcurrency` for capacity planning. Concurrency caps simultaneous tasks; it does not know how many healthy nodes an application needs to meet its SLO.

### 7.3. Separating Tasks by Responsibility

For example, a web fleet patching workflow can separate:

1. Pre-check: confirm nodes are healthy, have enough disk, and have policy-compliant backups/snapshots.
2. Drain: remove nodes from the load balancer or stop sending traffic.
3. Patch: apply updates and reboot if required.
4. Validate: check services, ports, application health, and versions.
5. Rejoin: return nodes to the load balancer.

This sequence can be orchestrated via Automation/Step Functions or prioritized tasks. When splitting into multiple tasks, ensure ordering and health checks are explicitly enforced; priority alone does not implement "run the next step only if the previous step succeeded."

## 8. Supported Task Types

Maintenance Windows supports four task types:

| Task Type | When to Use | Examples |
| --- | --- | --- |
| `RUN_COMMAND` | Run SSM Command documents on managed nodes | Shell/PowerShell scripts, patch commands, service checks |
| `AUTOMATION` | Run multi-step Automation runbooks | Create AMIs, restart instances, drain/update/rejoin |
| `LAMBDA` | Invoke a Lambda function | Precondition checks or change-system integration |
| `STEP_FUNCTIONS` | Start a Step Functions Standard workflow | Orchestrate multi-branch/conditional maintenance workflows |

Maintenance Windows supports only Step Functions **Standard** workflows; Express workflows are not supported.

### 8.1. Run Command

Run Command suits operations inside managed nodes such as Linux shell or Windows PowerShell. Tasks reference an SSM Command document, such as `AWS-RunShellScript` or `AWS-RunPowerShellScript`.

Run Command requires at least one target. If a node is not managed by Systems Manager or cannot reach SSM endpoints/SSM Agent, the command may hit delivery timeout or fail to complete.

Example task registration:

~~~bash
aws ssm register-task-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --name "check-web-service" \
  --task-arn "AWS-RunShellScript" \
  --task-type RUN_COMMAND \
  --targets "Key=WindowTargetIds,Values=11111111-2222-3333-4444-555555555555" \
  --service-role-arn arn:aws:iam::111122223333:role/MaintenanceWindowExecutionRole \
  --priority 10 \
  --max-concurrency "10%" \
  --max-errors "1" \
  --cutoff-behavior CANCEL_TASK \
  --task-invocation-parameters '{"RunCommand":{"Parameters":{"commands":["systemctl is-active nginx"]},"TimeoutSeconds":600,"CloudWatchOutputConfig":{"CloudWatchOutputEnabled":true,"CloudWatchLogGroupName":"/ssm/maintenance"}}}' \
  --region ap-southeast-1
~~~

This example uses a previously registered `WindowTargetId`. In practice, substitute your environment's ID, role, command document, log group, and parameters. Ensure commands are retry-safe and exit non-zero when preconditions fail.

### 8.2. Automation

Automation suits multi-step runbooks that act on AWS resources and support approvals/waits/branching. Examples:

- Create snapshots before updating.
- Verify instance state.
- Execute stop/start/reboot sequences.
- Update configuration and validate outcomes.

When an Automation runbook accepts resources via input parameters, the task may not need a separate target group. For targetless tasks, omit `MaxConcurrency` and `MaxErrors`; Systems Manager may display a placeholder `1` in responses.

### 8.3. Lambda

Lambda tasks fit custom logic or change-management integrations. Payloads can pass maintenance window metadata, service names, or change IDs.

Never embed credentials in payloads. Lambda should obtain permissions via its execution role, validate inputs, and be idempotent to prevent duplicate effects on invocation retries.

### 8.4. Step Functions

Step Functions Standard fits multi-step orchestration workflows, such as:

1. Deregister node from load balancer.
2. Wait for connection draining.
3. Run patch Automation.
4. Wait for node health.
5. Run smoke tests.
6. Re-register node with load balancer.

Workflows should define explicit error branches and timeouts. If patching fails, never automatically return a failed node to traffic simply because the next step was scheduled.

### 8.5. Targetless Tasks

Run Command always requires targets. Automation, Lambda, and Step Functions can be targetless if resources are supplied in task parameters or internal logic.

For instance, an AMI update runbook taking an AMI ID in input parameters needs no target instances. For targetless tasks, omit `--targets`, `--max-concurrency`, and `--max-errors`; rate controls do not apply.

## 9. Priority and Task Execution Order

Each task has a non-negative integer `Priority`. Lower numbers have higher priority. Tasks sharing the same priority are scheduled in parallel; lower-priority tasks are scheduled only after higher-priority tasks reach a final state.

Example:

| Priority | Task | Relationship |
| ---: | --- | --- |
| 0 | Pre-check and backup | Runs first |
| 10 | Drain and patch canary | After priority 0 |
| 20 | Validate canary | After priority 10 |
| 30 | Rollout wave 1 | After priority 20 |
| 40 | Rollout wave 2 | After priority 30 |

### 9.1. Priority Is Not a Success Condition

Once a higher-priority task reaches a final state, lower-priority tasks can still be scheduled even if the prior task ended with `FAILED`. Priority only governs ordering; it does not enforce "run only if the previous task succeeded."

If a subsequent task must run only when health checks pass, implement conditional logic in Automation/Step Functions or a separate approval gate.

### 9.2. Tasks Sharing the Same Priority

Tasks with the same priority can run in parallel. Assign the same priority only when tasks are independent and do not contend for the same resources. If one task drains traffic and another restarts the same node, they need distinct priorities rather than running in parallel.

### 9.3. Multiple Target Groups

AWS explicitly notes that when a maintenance window task is registered with multiple target groups, task invocations across those target groups run sequentially. If you need target groups to run concurrently, register separate tasks per target group with the same priority, and configure concurrency/error thresholds independently per task.

Distinguish registered target groups from resolved managed nodes inside a single target group. Verify actual resolution behavior in a test window before relying on parallelism assumptions.

## 10. MaxConcurrency and MaxErrors

These two rate controls limit rollout speed and error tolerance across targets.

### 10.1. MaxConcurrency

`MaxConcurrency` is the number or percentage of targets allowed to run simultaneously for a task. Examples:

- `1`: process one target at a time.
- `5`: up to five targets concurrently.
- `10%`: up to roughly 10% of resolved targets.
- `100%`: allow all targets in parallel, subject to service quotas/limits.

When targets are tag- or Resource-Group-based and counts fluctuate, percentages scale concurrency proportionally to fleet size. Choose small values for canary and early waves.

### 10.2. MaxErrors

`MaxErrors` is the maximum number or percentage of errors before Systems Manager stops scheduling the task on remaining targets. Examples:

- `0`: zero errors tolerated; once the first error is recorded, stop dispatching to remaining targets.
- `1`: allow one error; when the second error arrives, stop scheduling further targets.
- `5%`: stop scheduling when percentage error threshold is exceeded.

In-flight targets may still fail after the threshold is reached. Thus, the final error count can exceed `MaxErrors`.

### 10.3. Rate Control Example

Suppose 100 instances have a patch task configured with:

~~~text
MaxConcurrency = 10%
MaxErrors      = 2
~~~

The system can dispatch roughly 10 targets concurrently. With `MaxErrors = 2`, once the third error is received, the task stops scheduling remaining targets. Currently running targets can still finish or report errors.

This is a damage-containment control, not a rollback mechanism. When the error threshold trips, the team still must inspect modified nodes and recover if needed.

### 10.4. Choosing Values by Blast Radius

| Phase | Suggested MaxConcurrency | Suggested MaxErrors |
| --- | --- | --- |
| Canary | `1` | `0` or `1` |
| Small wave | `5%` | `1` or `1%` |
| Medium wave | `10–20%` | Per SLO/error budget |
| Stable, low-risk fleet | Increase gradually after validation | Per approved error threshold |

These are starting design values, not universal defaults. Factor in target count, spare capacity, task duration, and acceptable error tolerance before finalizing.

## 11. CutoffBehavior: Handling Running Tasks

`CutoffBehavior` governs what happens when a Maintenance Window reaches cutoff:

| Value | Behavior |
| --- | --- |
| `CONTINUE_TASK` | Default. In-flight task invocations continue; the task may continue launching invocations per current behavior until complete or bounded by window/task behavior. |
| `CANCEL_TASK` | No new invocations start after cutoff; handling of in-flight invocations depends on task type. |

### 11.1. With Automation, Lambda, and Step Functions

With `CANCEL_TASK`, already-running invocations continue; Systems Manager does not launch new invocations after cutoff. Unfinished tasks may enter `TIMED_OUT`.

### 11.2. With Run Command

With `CANCEL_TASK`, Systems Manager issues `CancelCommand` to attempt cancelling commands. AWS does not guarantee underlying commands/processes actually stop. Scripts must handle signals/timeouts themselves and avoid leaving partial mutations in an inconsistent state.

### 11.3. Choosing the Right Behavior

- Choose `CONTINUE_TASK` when tasks must finish safely past cutoff and continuing poses no risk.
- Choose `CANCEL_TASK` when you must stop new invocations and reduce the chance of tasks starting right before the window closes.
- For destructive or multi-step tasks, implement explicit cleanup/rollback logic; never rely on cancel to restore state.

## 12. CloudWatch Alarms as a Guardrail

Maintenance Window tasks can attach a CloudWatch alarm configuration to monitor health signals during execution. Example alarms:

- Application 5xx/error rate.
- p95/p99 latency.
- Load balancer healthy host count.
- CPU, memory, or queue depth.
- Custom metrics tracking patch/agent errors.

Alarm configuration is supported for Run Command and Automation tasks. `AlarmConfiguration` holds one CloudWatch alarm. `IgnorePollAlarmFailure` defaults to `false`; if Systems Manager cannot retrieve the alarm state, execution can stop. If it retrieves `OK` or `INSUFFICIENT_DATA`, execution continues regardless of `IgnorePollAlarmFailure`.

When the alarm triggers (`ALARM` state), the task is stopped. Attaching alarms to Run Command/Automation may require the principal registering the task to hold `iam:CreateServiceLinkedRole` per AWS documentation.

Design alarms before running tasks:

1. Pick metrics that reflect genuine service impact.
2. Set thresholds and evaluation periods sensitive enough while avoiding false positives.
3. Verify alarms are in `OK` state prior to maintenance.
4. Define response steps if an alarm fires or cannot be polled.
5. Monitor alarms alongside task executions and application dashboards.

Alarms are an extra guardrail; they do not replace canaries, rate controls, or in-task health checks.

## 13. IAM Roles and Separation of Duties

Maintenance Windows involves multiple permission layers. Assigning the wrong role or collapsing everything into one broad role can allow a maintenance task to modify resources outside its intended scope.

### 13.1. Task Registrar

The principal creating windows, registering targets, and registering tasks needs the corresponding Systems Manager permissions. When assigning an IAM service role to a task, the principal typically needs `iam:PassRole` for that specific role.

Restrict `iam:PassRole` by role ARN and condition `iam:PassedToService = ssm.amazonaws.com` where appropriate. Never let task creators pass arbitrary IAM roles in the account.

### 13.2. Maintenance Window Service Role

This is the role Systems Manager assumes to execute tasks on the operator's behalf. Basic trust policy:

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

The permission policy depends on task type and runbook. Examples:

- Run Command: permission to send commands to managed nodes and read command status.
- Automation: permission to start/read Automation executions and call AWS APIs required by the runbook.
- Lambda: permission to invoke the specific function ARN.
- Step Functions: permission to start executions of the specific Standard state machine.
- Resource Groups/tag targeting: permission to read required resource group/tag metadata.

AWS recommends a custom service role whose policy contains only permissions needed for the actual tasks. Do not default to a broad service-linked role for all workloads; current AWS documentation recommends creating dedicated roles for Maintenance Windows tasks.

### 13.3. Automation Assume Role

An Automation runbook can accept an `AutomationAssumeRole` parameter. When provided, Automation assumes that role to execute steps inside the runbook. If omitted, the runbook may fall back to the configured Maintenance Window service role.

For example, a runbook creating snapshots needs `ec2:CreateSnapshot`. If the service role lacks that permission and no other Automation Assume Role is supplied, execution fails at the snapshot step.

Separating the orchestration role from the action-execution role scopes permissions per runbook.

### 13.4. Managed Node Instance Profile

For Run Command, managed nodes need SSM Agent and appropriate IAM permissions to communicate with Systems Manager. If output is written from nodes to S3 or CloudWatch Logs, those write permissions belong to the node's instance profile/role, not the IAM user who registered the task.

If the S3 bucket or log group resides in another account, check the destination's resource policy alongside the node role's permissions.

### 13.5. Distinguishing the Four Principals

| Principal | Responsibility |
| --- | --- |
| Operator/automation caller | Creates windows, registers tasks, passes the service role |
| Maintenance Window service role | Assumed by Systems Manager to orchestrate tasks |
| Automation Assume Role | Assumed by the runbook to call AWS APIs inside steps |
| Managed node instance profile | Used by SSM Agent and the node to communicate and write output |

Never assume these roles are identical. Document which ARN is used at each layer in runbooks and change records.

## 14. Logging, Monitoring, and Execution Status

A task ending in `SUCCESS` does not prove the application remains healthy. Combine Systems Manager status with command output, application metrics, and health checks.

### 14.1. Run Command Output

Run Command tasks can send output to:

- Amazon CloudWatch Logs via `CloudWatchOutputConfig`.
- Amazon S3 via `OutputS3BucketName` and `OutputS3KeyPrefix`.
- SNS notifications via `NotificationConfig`.

These output fields live under `TaskInvocationParameters.RunCommand`. AWS has deprecated legacy `LoggingInfo` and `TaskParameters`; use `TaskInvocationParameters` and `Parameters` for new configurations.

Output configuration example:

~~~json
{
  "RunCommand": {
    "Parameters": {
      "commands": [
        "systemctl is-active nginx",
        "df -h"
      ]
    },
    "CloudWatchOutputConfig": {
      "CloudWatchOutputEnabled": true,
      "CloudWatchLogGroupName": "/ssm/maintenance"
    },
    "OutputS3BucketName": "company-ssm-command-output",
    "OutputS3KeyPrefix": "maintenance/prod/"
  }
}
~~~

The node role needs permissions to write to the bucket/log group. Restrict retention and reader access to output because logs may expose hostnames, package versions, paths, or internal configuration.

### 14.2. EventBridge

Maintenance Windows emits operational events usable with Amazon EventBridge. Use EventBridge to:

- Notify when a window execution starts or finishes.
- Create tickets when tasks enter `FAILED`/`TIMED_OUT`.
- Send alerts to SNS/Chatbot or incident workflows.
- Capture owner information and change IDs alongside events.

EventBridge rules should filter by window ID/task status and avoid generating duplicate alerts for every single invocation when one summary alert suffices.

### 14.3. Tracking Execution History

Useful APIs:

- `DescribeMaintenanceWindowExecutions`: lists window executions.
- `DescribeMaintenanceWindowExecutionTasks`: lists tasks within an execution.
- `DescribeMaintenanceWindowExecutionTaskInvocations`: lists per-target invocations.
- `GetMaintenanceWindowExecutionTask`: inspects detailed task execution info.
- `ListCommands`, `ListCommandInvocations`: inspects Run Command results.
- `GetAutomationExecution`: inspects Automation execution details.

Record `WindowExecutionId`, `TaskExecutionId`, `WindowTaskId`, and command/automation execution IDs in change records for auditability.

### 14.4. Statuses to Watch

| Status | Operational Meaning |
| --- | --- |
| `PENDING` | Waiting to be processed |
| `IN_PROGRESS` | Task is running |
| `SUCCESS` | Task completed successfully |
| `FAILED` | Task failed |
| `TIMED_OUT` | Task did not finish within the applicable limit |
| `CANCELLING` / `CANCELLED` | Cancelling or cancelled |
| `SKIPPED_OVERLAPPING` | Run skipped due to overlapping window execution |

When seeing `SKIPPED_OVERLAPPING`, check the schedule, prior run duration, and concurrent window execution limits. Never assume a skipped task means targets were maintained.

## 15. Creating Maintenance Windows and Registering Targets via CLI

This section demonstrates creating a window and registering targets. Use AWS CLI v2 configured for the target account/Region. IDs/ARNs are illustrative; substitute resources from a test environment first.

### 15.1. Create the Window

~~~bash
aws ssm create-maintenance-window \
  --name "prod-weekly-patching" \
  --description "Weekly production patching" \
  --schedule "cron(0 2 ? * SUN *)" \
  --schedule-timezone "Asia/Ho_Chi_Minh" \
  --duration 4 \
  --cutoff 1 \
  --no-allow-unassociated-targets \
  --tags Key=Environment,Value=Production Key=Owner,Value=platform-team \
  --region ap-southeast-1
~~~

The command returns a `WindowId`, formatted as `mw-` followed by 17 hex characters. Save the ID for subsequent steps. `--no-allow-unassociated-targets` requires tasks to use targets registered with the window.

### 15.2. Register the Canary Target

~~~bash
aws ssm register-target-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --resource-type INSTANCE \
  --targets "Key=tag:Environment,Values=Production" "Key=tag:MaintenanceRing,Values=canary" \
  --name "prod-canary-ring" \
  --owner-information "platform-team" \
  --region ap-southeast-1
~~~

The command returns a `WindowTargetId`. Record this ID if tasks register using `Key=WindowTargetIds`.

### 15.3. Inspect the Window and Targets

~~~bash
aws ssm get-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --region ap-southeast-1

aws ssm describe-maintenance-window-targets \
  --window-id mw-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Verify schedule, timezone, duration, cutoff, enabled state, target type, and tag conditions before registering tasks. If needed, inspect current managed nodes/tags via Systems Manager and Resource Groups.

### 15.4. Register a Run Command Task

~~~bash
aws ssm register-task-with-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --name "prod-canary-health-check" \
  --task-arn "AWS-RunShellScript" \
  --task-type RUN_COMMAND \
  --targets "Key=WindowTargetIds,Values=11111111-2222-3333-4444-555555555555" \
  --service-role-arn arn:aws:iam::111122223333:role/MaintenanceWindowExecutionRole \
  --priority 10 \
  --max-concurrency "1" \
  --max-errors "0" \
  --cutoff-behavior CANCEL_TASK \
  --task-invocation-parameters '{"RunCommand":{"Parameters":{"commands":["systemctl is-active nginx","curl -fsS http://localhost/health"]},"CloudWatchOutputConfig":{"CloudWatchOutputEnabled":true,"CloudWatchLogGroupName":"/ssm/maintenance"}}}' \
  --region ap-southeast-1
~~~

This task targets only the registered target and caps concurrency at one target. `MaxErrors=0` stops scheduling further targets immediately on the first error. Before running real health checks, verify the endpoint and command match the application.

## 16. Updating, Disabling, and Deleting a Window

Maintenance Windows can have schedules modified, be enabled/disabled, or have targets/tasks added or removed. Such changes directly affect operational schedules; manage them as reviewed changes.

### 16.1. Temporarily Disabling a Window

~~~bash
aws ssm update-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --no-enabled \
  --region ap-southeast-1
~~~

Disabling a window prevents future scheduled runs. Check for in-flight executions before making changes; do not assume disabling automatically stops already-started task invocations.

### 16.2. Re-enabling a Window

~~~bash
aws ssm update-maintenance-window \
  --window-id mw-0123456789abcdef0 \
  --enabled \
  --region ap-southeast-1
~~~

Before re-enabling, confirm the change window, target tags, task versions, service role, and that the schedule no longer conflicts with another maintenance event.

### 16.3. Updating a Task

`UpdateMaintenanceWindowTask` can update the task ARN, service role, invocation parameters, priority, concurrency, and error threshold. You cannot change the task type of an existing task; if a different task type is needed, register a new task and delete the old one per change plan.

When updating `TaskInvocationParameters`, re-submit every value you want to keep. Omitted fields can be dropped. This is a common mistake that causes CloudWatch/S3 output or notification settings to disappear after an update.

### 16.4. Deleting a Window

Before deleting a window:

1. Verify no executions are currently running.
2. Check whether dashboards/EventBridge rules/runbooks still reference the window ID.
3. Archive necessary execution history.
4. Deregister targets and tasks through proper API workflows if needed.
5. Delete the window only after confirming no dependent consumers remain.

Do not delete a window just to deal with a failed run; normally keep history for investigation and fix the configuration.

## 17. Service Quotas and Operational Limits

Per AWS Systems Manager service quotas, default limits for Maintenance Windows include:

| Resource | Default Quota |
| --- | ---: |
| Maintenance windows per account/Region | 50 |
| Tasks per maintenance window | 20 |
| Targets per maintenance window | 100 |
| Targets per task | 10 |
| Concurrent maintenance window executions | 5 |

Quotas vary by account/Region and increases can be requested via AWS Service Quotas. Before designing multiple parallel windows, check actual quotas rather than relying on documentation defaults.

### 17.1. Other Limits Affecting Rollouts

- Run Command is subject to command delivery, invocation, and managed node throughput quotas.
- Automation has its own concurrency quota; executions exceeding the limit may queue.
- Lambda and Step Functions have separate Regional quotas and availability.
- SSM Agent, instance profiles, and network paths to Systems Manager endpoints determine whether nodes receive tasks.
- Maintenance Windows are normally scoped per account/Region; do not treat one window as an organization-wide schedule.

### 17.2. Feasibility Check Before Creating a Window

For a large fleet, estimate:

1. Resolved target count at runtime.
2. Required task count and target groups.
3. Average and peak duration per invocation.
4. Concurrent invocations allowed under `MaxConcurrency`.
5. Overlapping window executions that may run simultaneously.
6. Automation/Run Command quotas and downstream system capacity.

If total expected runtime exceeds window duration, split the rollout across multiple windows or reduce per-wave scope. Never crank up concurrency solely to force the entire fleet through a short window.

## 18. Common Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| **Window does not run on schedule** | Window disabled, wrong cron/timezone, or outside StartDate/EndDate | Check enabled state, schedule, IANA timezone, start/end, and next execution time |
| **Window runs at wrong local time** | `ScheduleTimezone` unset or timestamp interpreted as UTC | Check IANA timezone and convert timestamps against UTC |
| **Task is not scheduled** | Cutoff reached, higher priority still running, or `MaxErrors` exceeded | Check cutoff time, priorities, and task rate controls |
| **No targets resolved** | Wrong tag key/value/casing, wrong Resource Group, or unmanaged nodes | Check target definitions, tags, resource types, and managed node status |
| **Targets include unexpected nodes** | Shared tags or misapplied tags on resources | Review inventory/tag governance and narrow selectors |
| **Task registration AccessDenied** | Caller lacks SSM permissions or `iam:PassRole` | Check caller identity, policy, and passed role ARN |
| **Task registered successfully but doesn't run** | Invalid `TaskArn`/document, missing targets, or service role cannot be assumed | Check task type, `TaskArn`, target requirements, and trust policy |
| **Run Command delivery timeout** | SSM Agent offline, wrong node role, or no path to SSM endpoints | Check agent, instance profile, DNS, and HTTPS 443 to `ssm`/`ssmmessages`/`ec2messages` |
| **Automation fails at a step** | Service role/Automation Assume Role lacks permission | Inspect Automation execution steps and grant exact API permissions |
| **Lambda/Step Functions task fails to register** | Service unsupported in Region or wrong ARN | Check Regional availability, function/state machine ARN, and task type |
| **Task stops after a few errors** | `MaxErrors` exceeded | Inspect failed targets and count/percentage threshold |
| **Tasks start after cutoff** | `CutoffBehavior` is `CONTINUE_TASK` or invocation already dispatched | Check `CutoffBehavior` and task invocation timestamps |
| **Run Command keeps running after cancel** | `CancelCommand` only requests cancellation; underlying process may ignore it | Build timeouts/cleanup in scripts and inspect processes on nodes |
| **Task marked SKIPPED_OVERLAPPING** | Previous execution overlapped or concurrent window quota hit | Check execution history, duration, schedule, and quotas |
| **Missing command output** | Node role lacks S3/CloudWatch Logs permissions or wrong destination | Check instance profile policy, bucket/log group policy, and output settings |
| **Task stopped by alarm** | CloudWatch alarm entered `ALARM` | Inspect metric, alarm history, application impact, and task execution |
| **Targetless task rejects MaxConcurrency/MaxErrors** | Rate controls passed to a targetless task | Remove both rate control parameters from targetless tasks |
| **Cannot select service role in console** | Role deleted, wrong name/ARN, or missing `iam:ListRoles` | Verify role existence, trust policy, and console permissions |

### 18.1. Checking Managed Nodes

Run Command works only on eligible managed nodes. Check:

- SSM Agent is installed and running.
- Instance profile or hybrid activation role has required Systems Manager permissions.
- Node has outbound HTTPS 443 to Region-appropriate Systems Manager endpoints, including `ssm`, `ssmmessages`, and depending on environment `ec2messages`.
- DNS, routes, proxies, and VPC endpoints do not block traffic.
- Node appears in Systems Manager Fleet Manager/Managed nodes as online.

Offline nodes may still appear in target groups, yet commands cannot be delivered to the agent.

### 18.2. Checking Why No Task Invocations Occurred

1. Confirm the window executed at the expected time.
2. Confirm the task was registered and not deleted.
3. Check target resolution and resource types.
4. Check task priority, cutoff, `MaxErrors`, and prior task status.
5. Confirm the role was assumed and `TaskArn`/document version are valid.
6. Open task execution details and invocation details to read `StatusDetails`.

Do not conclude "nothing changed" just because command output is missing. The task may not have dispatched, or output may be going to a different S3 path/CloudWatch Logs group.

## 19. Case Study: Patching a Web Fleet While Preserving Capacity

### 19.1. Context

A web service runs 60 EC2 instances in one Region across three Availability Zones, 20 instances per AZ. The load balancer must maintain at least 4 healthy targets per AZ to meet capacity SLOs. The platform team needs to install security updates and reboot when needed on Sunday mornings.

### 19.2. Designing Target Rings

Instances are tagged:

~~~text
Environment=Production
Service=web
MaintenanceRing=canary | wave-1 | wave-2
AvailabilityZone=az-a | az-b | az-c
~~~

Rollout split:

| Ring | Scope | Goal |
| --- | --- | --- |
| Canary | 1 instance per AZ (3 instances) | Validate patching, reboots, and health checks |
| Wave 1 | 6 instances per AZ (18 instances) | Confirm impact on a small group |
| Wave 2 | Remaining 13 instances per AZ (39 instances) | Complete fleet after prior stages stabilize |

Do not place all 60 instances into a single unbounded task. Tag rings give the team per-stage target control and prevent updating too many nodes simultaneously in one AZ.

### 19.3. Window Configuration

The window runs at 02:00 Sunday in `Asia/Ho_Chi_Minh`, duration 5 hours, cutoff 1 hour. Thus, no new tasks are scheduled after 06:00; the window closes at 07:00. Already-running tasks can continue past 07:00 depending on cutoff behavior.

### 19.4. Task Ordering

| Priority | Task | Target Ring | Rate Control |
| ---: | --- | --- | --- |
| 0 | Pre-check capacity and policy-compliant backup/snapshot | Canary | `1`, `MaxErrors 0` |
| 10 | Drain, patch, reboot, and validate | Canary | `1`, `MaxErrors 0` |
| 20 | Patch and validate | Wave 1 | `10%`, `MaxErrors 1` |
| 30 | Patch and validate | Wave 2 | `10%`, `MaxErrors 1` |
| 40 | Summarize results and verify fleet health | Targetless if workflow fetches data itself | Per workflow |

The patch runbook should remove nodes from traffic before updating, verify services post-reboot, and rejoin only when health checks pass. If validation fails, keep the node out of traffic, open an incident/ticket, and halt the next wave via workflow/approval logic.

### 19.5. Alarms and Stop Conditions

Attach CloudWatch alarms for:

- Healthy host count per AZ.
- Application 5xx/error rate.
- p95/p99 latency.
- CPU or queue depth if those are primary bottleneck signals.

If an alarm triggers, the task stops. `MaxErrors` also bounds invocation failures. These two guardrails complement each other: alarms observe service-level impact, while `MaxErrors` observes per-target task errors.

### 19.6. Post-Maintenance Verification

- Confirm all 20 healthy instances per AZ, or the count authorized by the change plan.
- Confirm all instances carry the expected patch level/version.
- Confirm SSM Agent remains online.
- Inspect error rates, latency, and traffic distribution.
- Review any `FAILED`/`TIMED_OUT`/`CANCELLED` task invocations.
- Store output, event history, command IDs, and change records.
- Close the change only after the service remains stable across the defined observation period.

### 19.7. Lessons Learned

Maintenance Windows provides scheduling and rate controls. Runbooks provide drain/patch/validate/rejoin logic. CloudWatch alarms provide impact signals. Limiting blast radius requires designing all three together.

## 20. Reinforcement Exercises

### Exercise 1 — Choosing a Tool

An organization wants to guarantee every managed node always uses a standardized agent configuration. Should they prioritize State Manager or Maintenance Windows?

**Hint:** State Manager maintains desired state; Maintenance Windows fits running updates during approved time windows.

### Exercise 2 — Calculating Cutoff

A window starts at 23:00 with duration 4 hours and cutoff 1 hour. What is the latest time a new task may start?

**Hint:** 23:00 + 4 hours - 1 hour = 02:00. The window closes at 03:00.

### Exercise 3 — Selecting a Schedule

A team wants maintenance at 02:00 Sunday Vietnam time. What should be configured so they do not have to convert to UTC manually?

**Hint:** cron `cron(0 2 ? * SUN *)` with timezone `Asia/Ho_Chi_Minh`.

### Exercise 4 — Selecting Targets

A production fleet frequently replaces instances via Auto Scaling. Should you use instance IDs or tag targets?

**Hint:** Tag targets fit better; use `Environment`, `Service`, and `MaintenanceRing` to scope groups.

### Exercise 5 — MaxConcurrency

A task has 80 targets with `MaxConcurrency=10%`. Roughly how many targets can process simultaneously?

**Hint:** roughly 8 targets, depending on service resolution and rounding.

### Exercise 6 — MaxErrors

A task has `MaxErrors=2`. What happens when the third error is received?

**Hint:** Systems Manager stops scheduling the task for remaining targets; in-flight invocations may still return results or errors.

### Exercise 7 — CutoffBehavior

A Run Command task needs to finish cleanup even when cutoff arrives. Does `CANCEL_TASK` guarantee the process stops cleanly?

**Hint:** no. Systems Manager sends `CancelCommand` to attempt cancellation, but does not guarantee the underlying process stops. Scripts must implement their own timeout and cleanup logic.

### Exercise 8 — Priority

Task priority 10 fails. Is task priority 20 automatically skipped?

**Hint:** no. Priority controls execution order; the next task can be scheduled once the prior task reaches a final state. Put success conditions in Automation/Step Functions if subsequent steps must be gated.

### Exercise 9 — Role Permissions

Run Command writes output to S3, yet no file appears. Which role should be checked first?

**Hint:** the managed node's instance profile/role and the S3 bucket policy; output write permissions belong to the node role, not the task registrar.

### Exercise 10 — SKIPPED_OVERLAPPING

A window shows `SKIPPED_OVERLAPPING`. What should you investigate?

**Hint:** whether the previous execution is still running, overly long duration/cutoff, tightly spaced schedule, or reached concurrent window execution quota.

## 21. Pre-Production Checklist

- [ ] Change record includes owner, approver, goal, timing, and rollback plan.
- [ ] Schedule uses valid cron/rate/at and IANA timezone.
- [ ] `StartDate`/`EndDate` do not inadvertently exclude intended runs.
- [ ] Duration is long enough based on measured runtime; cutoff reserves enough time to stop new dispatches.
- [ ] Team understands in-flight tasks may continue past window close.
- [ ] Targets are reviewed; tags/Resource Groups exclude out-of-scope resources.
- [ ] Fleet is segmented into canary and rollout waves.
- [ ] Minimum capacity is preserved per AZ/load balancer/SLO.
- [ ] Runbooks/SSM documents use pinned versions and were tested in non-production.
- [ ] Tasks define timeouts, retry/idempotency, and cleanup/rollback logic.
- [ ] Task priorities express execution order; priority is not confused with a success gate.
- [ ] `MaxConcurrency` does not exceed capacity/downstream system tolerance.
- [ ] `MaxErrors` fits the rollout stage and error budget.
- [ ] `CutoffBehavior` is intentionally selected per task type.
- [ ] CloudWatch alarms monitor critical service impact.
- [ ] IAM service role is a custom least-privilege role.
- [ ] Operators hold `iam:PassRole` only for approved roles.
- [ ] Automation Assume Role and node instance profiles are kept separate.
- [ ] SSM Agent, instance profiles, and network paths to Systems Manager endpoints are verified.
- [ ] Command output has configured storage, retention, and restricted reader access.
- [ ] EventBridge notifications/alarms open tickets or alert the right responders.
- [ ] Service quotas and non-overlapping schedules have been checked.
- [ ] On-call staff monitor canary, wave rollouts, and health metrics.
- [ ] Promotion to the next wave requires passing validation/approval.
- [ ] Plans exist to keep nodes out of traffic if patching/health checks fail.
- [ ] Execution IDs, task IDs, command IDs, and outputs are logged in the change record.
- [ ] Maintenance concludes by confirming service health, patch level, and capacity.

## 22. Key Takeaways

1. Maintenance Windows is a time-based orchestrator for potentially disruptive tasks; it comprises schedule, duration, cutoff, targets, and tasks.
2. Duration (1–24 hours) sets window length; cutoff (0–23 hours) sets when new task scheduling halts.
3. Tasks already running may continue past window close. `CutoffBehavior` and task timeouts determine actual behavior.
4. Use tags/Resource Groups for dynamic fleets; verify target resolution to avoid out-of-scope impact.
5. Run Command, Automation, Lambda, and Step Functions serve different job types; Step Functions must use Standard workflows.
6. Priority controls ordering, not success conditions. Same-priority tasks can run in parallel.
7. `MaxConcurrency` and `MaxErrors` cap dispatch rate and error tolerance; they do not automatically roll back completed changes.
8. IAM service roles, Automation Assume Roles, and node instance profiles are distinct permission layers.
9. CloudWatch alarms, EventBridge, Logs, and execution history help detect impact and investigate outcomes.
10. To limit blast radius, combine canary testing, waves, capacity planning, health checks, and rollback logic.

Maintenance Windows only provides the time window and orchestration framework. Safety depends on selected targets, granted permissions, well-written tasks, bounded concurrency, and how the team responds when health metrics degrade.

### Official AWS Documentation

- [AWS Systems Manager Maintenance Windows](https://docs.aws.amazon.com/systems-manager/latest/userguide/maintenance-windows.html) — concepts, task types, and use cases.
- [CreateMaintenanceWindow API](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_CreateMaintenanceWindow.html) — duration, cutoff, schedule, timezone, and target behavior.
- [Maintenance window scheduling and active period options](https://docs.aws.amazon.com/systems-manager/latest/userguide/maintenance-windows-schedule-options.html) — start/end dates, timezone, and schedule offset.
- [Cron and rate expressions for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/reference-cron-and-rate-expressions.html) — schedule syntax.
- [Choosing between State Manager and Maintenance Windows](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-vs-maintenance-windows.html) — choosing the tool by objective.
- [RegisterTargetWithMaintenanceWindow API](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_RegisterTargetWithMaintenanceWindow.html) — target IDs, tags, and resource groups.
- [RegisterTaskWithMaintenanceWindow API](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_RegisterTaskWithMaintenanceWindow.html) — task type, priority, rate controls, and cutoff behavior.
- [MaintenanceWindowTaskInvocationParameters](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_MaintenanceWindowTaskInvocationParameters.html) — invocation parameters per task type.
- [Assign tasks to a maintenance window](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-maintenance-assign-tasks.html) — task registration, output, and alarms.
- [Assign targets to a maintenance window](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-maintenance-assign-targets.html) — target selection.
- [Setting up Maintenance Windows permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/setting-up-maintenance-windows.html) — IAM service role and operator permissions.
- [Registering maintenance window tasks without targets](https://docs.aws.amazon.com/systems-manager/latest/userguide/maintenance-windows-targetless-tasks.html) — targetless tasks.
- [Troubleshooting Maintenance Windows](https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-maintenance-windows.html) — common errors.
- [Systems Manager endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html) — endpoints and service quotas.
