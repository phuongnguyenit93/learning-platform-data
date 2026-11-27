# Log Collection, ECS Exec, and Troubleshooting Stopped Tasks

When an application running on **Amazon Elastic Container Service (ECS)** fails to serve requests, the only visible symptom might be "tasks start and vanish," "the service keeps replacing tasks," or "CloudWatch has no logs." To find the root cause, never rush to bump CPU/RAM or widen IAM policies. Separate **application logs**, **ECS lifecycle events**, **interactive diagnostics via ECS Exec**, and **stopped task metadata**.

For example, a Java service on **AWS Fargate** launches a task that stops after 10 seconds. It could be unable to pull the image from Amazon ECR, the execution role might lack secret permissions, networking might block CloudWatch Logs, the Java process might run out of memory, or the app might exit due to a missing environment variable. Each cause leaves traces at a different layer.

This lesson belongs to the **Containers with ECS** chapter of the **CLOUD_PROVIDERS_AWS** module. It ties into the broader AWS ecosystem—Regions/AZs, IAM, VPCs, compute, storage, databases, integration, and serverless—to build skills in secure deployment, effective monitoring, incident recovery, and cost control.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **CloudWatch Logs**, **FireLens**, **ECS service events**, **task state change events**, **CloudTrail**, and **Container Insights**.
2. Configure **`awslogs`** in an ECS task definition, understanding the **task execution role**, log groups, log stream prefixes, and retention.
3. Design structured logging with task ARNs, correlation IDs, and sensitive-data hygiene.
4. Set up and use **ECS Exec** with Session Manager, IAM task roles, network endpoints, and audit controls.
5. Read **`stopCode`**, **`stoppedReason`**, **`containers[].reason`**, **`exitCode`**, and ECS service events to determine why a task stopped.
6. Diagnose common failures: **`CannotPullContainer`**, **`ResourceInitializationError`**, **`EssentialContainerExited`**, OOM, failing health checks, and denied AWS permissions.
7. Build secure runbooks, preserve evidence after tasks disappear, and validate observability prior to production.

## 2. Diagnostic Model: Each Layer Leaves Different Traces

~~~mermaid
flowchart TD
    CLIENT["Client / ALB"] --> SERVICE["ECS Service<br/>Desired count + deployments"]
    SERVICE --> TASK["ECS Task<br/>Task definition revision"]
    TASK --> APP["Application containers"]
    APP --> LOG["stdout/stderr → awslogs<br/>CloudWatch Logs"]
    TASK --> EVENT["STOPPED state change<br/>EventBridge"]
    SERVICE --> EV["Service events<br/>Deployment / placement / health"]
    TASK --> EXEC["ECS Exec + SSM<br/>Task RUNNING"]
    APP --> METRIC["Container Insights<br/>CPU / Memory / network"]
    CONTROL["AWS API / IAM identity"] --> TRAIL["CloudTrail<br/>Who called ECS APIs?"]
~~~

| Information Source | Question It Answers Best | Limitations |
|---|---|---|
| **Application stdout/stderr** | What code error, stack trace, or request failed? | Can be empty if the container never started or logging isn't configured |
| **CloudWatch Logs** | How were container logs collected over time? | Requires log driver, permissions, and network path; omits host logs automatically |
| **ECS task details** | What state is the task in, why did it `STOPPED`, and what was the container exit code? | `STOPPED` tasks remain queryable in ECS for only a short window |
| **ECS service events** | What failed in deployment, health replacement, placement, or scaling? | Does not replace application logs or full task state history |
| **EventBridge task state change** | When did the task enter `RUNNING`/`STOPPED`, and with what event details? | Must be routed/archived explicitly for long-term lookup |
| **ECS Exec** | What files, processes, env vars, or network behavior exist inside a `RUNNING` container? | Cannot attach to `STOPPED` tasks; requires prior opt-in and permissions |
| **CloudTrail** | Which principal called ECS APIs such as `ExecuteCommand` or `UpdateService`? | Does not capture shell commands or stdout unless session logging is enabled |
| **CloudWatch metrics / Container Insights** | How did CPU, memory, task counts, errors, or latency trend? | Metrics alone rarely pinpoint why an app crashed |

A solid investigation combines **multiple evidence sources** on a unified timeline instead of guessing from a single error line.

## 3. Application Logging in ECS: `stdout`/`stderr` Is the Starting Point

### 3.1. Why Write Logs to `stdout`/`stderr`?

Containers can be replaced at any moment due to deployments, crashes, or scale-in. Writing logs only to files inside the container filesystem risks losing them when the task stops. Instead, applications should log to **`stdout`/`stderr`** so ECS's log driver forwards them to centralized storage.

For Java/Spring Boot, configure SLF4J/Logback or equivalent to emit structured logs at **`INFO`/`WARN`/`ERROR`** levels with **`service`, `environment`, `requestId`/`traceId`, and `taskId`** where available. Routine log reading should never require shelling into a container.

**Note:** if a task uses sidecars or secondary processes writing to files, configure matching collection; **`awslogs`** only forwards the output streams of containers configured with that driver. It does not automatically scrape arbitrary files inside containers or ECS agent logs on EC2.

### 3.2. Configuring `awslogs` in the Task Definition

Example ECS Fargate task with container **`orders-api`** and a pre-created log group **`/ecs/orders/prod`**. The JSON below illustrates key fields, not ready-to-run production resources:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::111122223333:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::111122223333:role/ordersTaskRole",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:v12",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/orders/prod",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "orders"
        }
      }
    }
  ]
}
~~~

Image/role/account values are illustrative; registering and running successfully requires a real image, valid roles, subnets/security groups, a service or `RunTask`, and app dependencies.

| Option | Purpose | What to Check |
|---|---|---|
| **`logDriver = awslogs`** | Ships container output to CloudWatch Logs | Driver supported on target compute/agent |
| **`awslogs-group`** | CloudWatch log group name | Group exists in target Region or creation is permitted |
| **`awslogs-region`** | Region storing logs | Can differ from task Region, though design and cost/data rules apply |
| **`awslogs-stream-prefix`** | Prefix for log stream names | **Required on Fargate**; recommended on EC2 |
| **`awslogs-create-group`** | Whether to auto-create missing log group | Defaults to false; requires **`logs:CreateLogGroup`** if true |
| **`awslogs-multiline-pattern` / `awslogs-datetime-format`** | Groups multiline log events by pattern | Adds CPU overhead; use only with stable formats; never set both together |

With prefix **`orders`**, container **`orders-api`**, and fictional task ID **`abcdef1234567890`**, the typical stream name is:

~~~text
orders/orders-api/abcdef1234567890
~~~

Pre-create **log groups** via IaC with retention, KMS encryption if required, access policies, and cost tags. Avoid leaving default infinite retention unless compliance or operations demand it.

### 3.3. Execution Role and Task Role Are Not the Same

This is a frequent IAM mistake:

| Role | Who Uses It? | Example Permissions |
|---|---|---|
| **Task execution role** | ECS/Fargate agent preparing the runtime | Pull ECR images, ship logs via `awslogs`, fetch secrets/env files per task definition |
| **Task role** | Application code inside the container | Read S3, write DynamoDB, call SQS; add **`ssmmessages`** for ECS Exec when needed |
| **EC2 container instance role** | ECS agent on EC2 host in EC2 launch type | Register host with ECS and perform host agent actions |
| **Operator IAM principal** | Engineer/CI calling ECS APIs | `DescribeTasks`, `ExecuteCommand`, `UpdateService` within scope |

For **standard `awslogs` on Fargate**, **`logs:CreateLogStream`** and **`logs:PutLogEvents`** belong on the **execution role**; if auto-creating log groups, also verify **`logs:CreateLogGroup`**. Managed policies such as **`AmazonECSTaskExecutionRolePolicy`** supply baseline permissions where appropriate, though you should inspect exact resource scope.

**Never attach `AdministratorAccess` to the task role to fix log delivery errors.** The real cause is usually missing execution role permissions, a log group in the wrong Region, or missing network connectivity to CloudWatch Logs.

### 3.4. Reading Logs via AWS CLI and CloudWatch Logs Insights

~~~bash
# View recent events; requires appropriate CloudWatch Logs permissions.
aws logs tail /ecs/orders/prod \
  --region ap-southeast-1 \
  --since 30m

# Follow live logs during controlled testing.
aws logs tail /ecs/orders/prod \
  --region ap-southeast-1 \
  --since 5m \
  --follow
~~~

When a log group collects multiple tasks, filter by **log stream** or **task ID** to avoid mixing events. In CloudWatch Logs Insights, try:

~~~text
fields @timestamp, @logStream, @message
| filter @message like /ERROR|Exception|OutOfMemory/
| sort @timestamp desc
| limit 100
~~~

For JSON-formatted logs, query parsed fields such as **`level`**, **`requestId`**, or **`traceId`** where formatting and Logs Insights support it. Narrow the time window around the task stop time to reduce noise and query cost.

## 4. FireLens, Advanced Logging, and Structured Data

**Amazon ECS FireLens** integrates log routing, typically running a **Fluent Bit** sidecar log router to forward logs to multiple destinations via supported output plugins. This fits enterprises centralizing logs into analytics pipelines, Amazon Data Firehose, OpenSearch, or other observability backends.

~~~mermaid
flowchart LR
    APP["Application container<br/>stdout/stderr"] --> FIRE["FireLens log router<br/>Fluent Bit sidecar"]
    FIRE --> CW["CloudWatch Logs"]
    FIRE --> OUT["Other destinations<br/>via output plugin"]
    ECS["ECS task metadata"] -. "Adds metadata when configured" .-> FIRE
~~~

In the task definition, the app container sets **`logDriver = awsfirelens`**, while the log router container sets **`firelensConfiguration`**. Sound setups verify output plugins, credentials, routing, buffer memory, retries, and network paths to destinations.

### 4.1. Choosing `awslogs` vs. FireLens

| Aspect | `awslogs` | FireLens |
|---|---|---|
| Simplicity | Fewer components, simple setup | Adds router container and configuration |
| Destinations | CloudWatch Logs | Multiple destinations via supported plugins |
| Data normalization | App should emit JSON itself | Can parse/transform/filter in the router |
| New failure points | Driver / CloudWatch Logs | Router, plugins, buffers, CPU/memory, and destinations |
| Cost | Log ingestion/storage/queries | Extra router compute resources, traffic, and destination charges |

**Do not turn the log router into an invisible failure point.** Allocate router sidecar CPU/memory, monitor the router, tune buffer/retry settings, and log the router's own output separately. If FireLens breaks, logs can drop silently while the app keeps running—or the whole task can fail depending on `essential`/dependency settings.

### 4.2. Designing Traceable Application Logs

A structured log record might look like:

~~~json
{
  "timestamp": "2026-11-20T03:00:00Z",
  "level": "ERROR",
  "service": "orders-api",
  "environment": "prod",
  "requestId": "req-example-008",
  "traceId": "trace-example-456",
  "message": "Database connection timeout",
  "errorType": "DB_TIMEOUT"
}
~~~

Include **UTC timestamps**, service/version, correlation IDs, task/container metadata, and actionable messages. Avoid logging **passwords, access keys, session cookies, bearer tokens, or unnecessary PII**. For multiline Java stack traces, prefer single-line JSON or consistent multiline settings for clean querying.

### 4.3. CloudTrail and Metrics Are Not Application Logs

- **CloudTrail** identifies who modified a service/task definition or invoked ECS Exec. It does not replace container business logs.
- **CloudWatch Container Insights** measures CPU/memory/network/task counts per observability settings. Metric spikes are symptoms, not root-cause diagnoses.
- **ECS task/service state change events** reconstruct timelines of deployments, health transitions, and task terminations.

## 5. ECS Exec: Diagnostic Access to a Running Container

**ECS Exec** uses **AWS Systems Manager Session Manager** to interact with containers inside a **`RUNNING`** ECS task—without opening inbound SSH ports or managing EC2 host SSH keys. It runs interactive shells or commands within supported container types and environment constraints.

ECS Exec works well for checking DNS, non-sensitive config files, processes, scrubbed env vars, listening ports, or network reachability from a live task. **Never use ECS Exec as a routine deployment method**: manual edits inside a container produce non-reproducible state that vanishes when the task is replaced.

### 5.1. ECS Exec Architecture

~~~mermaid
sequenceDiagram
    participant OP as Operator + AWS CLI
    participant ECS as Amazon ECS API
    participant SSM as SSM Session Manager
    participant TASK as Container in ECS task
    OP->>ECS: ExecuteCommand (IAM check)
    ECS-->>OP: Session setup details
    OP->>SSM: Connect via Session Manager plugin
    TASK->>SSM: SSM core agent uses task role
    SSM-->>OP: Encrypted interactive channel
    OP->>TASK: Permitted diagnostic command
    TASK-->>OP: Output
~~~

The ECS/Fargate agent manages **`ExecuteCommandAgent`** inside the container to establish sessions. You can check agent state under **`DescribeTasks` → `containers[].managedAgents`**.

### 5.2. Prerequisites Before Using ECS Exec

| Prerequisite | Meaning |
|---|---|
| **Task is `RUNNING`** | Cannot Exec into `STOPPED` or unstarted tasks |
| **`enableExecuteCommand = true`** | Must be enabled when the task is created; enabling on a service does not retrofit existing tasks |
| **AWS CLI + Session Manager plugin** | Interactive CLI requires the plugin and compatible versions |
| **Compatible agent/platform** | ECS agent/platform version/OS must support ECS Exec |
| **Task IAM role** | Needs four **`ssmmessages`** actions to open data/control channels |
| **Operator IAM permission** | User needs **`ecs:ExecuteCommand`** on target resources |
| **Networking** | Task reaches **`ssmmessages`** via NAT/Internet or a VPC interface endpoint |
| **Filesystem and resources** | ECS Exec writes temporary state to the filesystem and adds CPU/memory overhead |
| **Auditing** | CloudTrail and CloudWatch/S3 session logging configured appropriately |

Important limitations in AWS documentation:

- ECS Exec **is not supported on tasks with a fully read-only root filesystem** via **`readonlyRootFilesystem`**.
- Commands in ECS Exec run as **`root`** inside the container, even if the application runs as a non-root user. This makes permissions highly sensitive.
- ECS Exec does not support **`IPv6-only`** task configurations per current documented limits.
- Shared PID namespaces may limit concurrent exec sessions; multi-container tasks may require specifying the target container explicitly.
- You cannot enable ECS Exec on an **already-running older task**; new tasks must be launched with it enabled.

On EC2 launch type, AWS specifies minimum ECS agent versions; on Fargate Linux, documentation specifies **platform version 1.4.0 or later** (Windows has its own thresholds). Verify documentation for your Region and environment when deploying.

### 5.3. IAM for the Task Role

Example policy on the **task role** allowing the SSM core agent to create and open communication channels:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowECSExecChannels",
      "Effect": "Allow",
      "Action": [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    }
  ]
}
~~~

This policy serves the **in-container agent channel** and should be attached only to task roles that genuinely require ECS Exec. **Do not confuse it with the operator's `ecs:ExecuteCommand` permission.** If configuring a KMS customer managed key for session encryption or storing session logs in S3/CloudWatch Logs, additional KMS/log/S3 permissions are required; inspect KMS key policies and resource accounts.

Operator permissions should be scoped by **cluster, task, container, tags, and conditions** supported by ECS, enabled only when needed. Direct Session Manager access outside ECS Exec can be restricted per AWS guidance to prevent un-audited bypasses.

### 5.4. Enabling ECS Exec on a Service

Example updating an ECS service so **new tasks** launch with ECS Exec enabled:

~~~bash
aws ecs update-service \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --service orders-api \
  --enable-execute-command \
  --force-new-deployment
~~~

**Warning:** this mutates the service, and **`--force-new-deployment`** replaces live serving tasks. Run only in authorized environments with deployment/rollback plans and testing. Toggling the flag without replacing tasks leaves existing tasks at **`enableExecuteCommand = false`**.

With **`RunTask`** for standalone tasks, pass **`--enable-execute-command`** at launch time if you expect to use ECS Exec later.

### 5.5. Verifying the Agent and Starting a Session

~~~bash
# Inspect details of the RUNNING task.
aws ecs describe-tasks \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/training-cluster/TASK_ID \
  --query 'tasks[].{Task:taskArn,Status:lastStatus,Exec:enableExecuteCommand,Containers:containers[].{Name:name,Agents:managedAgents}}'

# Run Exec only after Exec=true and the agent shows lastStatus=RUNNING.
aws ecs execute-command \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --task arn:aws:ecs:ap-southeast-1:111122223333:task/training-cluster/TASK_ID \
  --container orders-api \
  --interactive \
  --command "/bin/sh"
~~~

**`TASK_ID`**, cluster, and container names are placeholders; the container image must actually contain **`/bin/sh`** or another valid shell. ECS Exec supports only **interactive sessions** via this CLI mechanism, so **`--interactive`** is required. Never assume distroless images include a shell. To diagnose minimal images, rely on logs, metrics, or build-time diagnostic tooling.

Safe diagnostic commands inside a container include **`pwd`**, **`ps`**, checking allowed config filenames, DNS lookups if tools exist, or testing connectivity to a lab endpoint. Avoid commands that mutate data, kill processes, dump all env vars, or read secrets unnecessarily.

### 5.6. If ECS Exec Fails to Connect

Checklist order:

1. **Task `lastStatus = RUNNING`**, **`enableExecuteCommand = true`**.
2. **`ExecuteCommandAgent` `lastStatus = RUNNING`** inside the target container.
3. Operator has **`ecs:ExecuteCommand`**, not blocked by SCPs/boundaries/explicit denies.
4. Task role has the **`ssmmessages`** actions, not just the execution role.
5. Task can reach the **`ssmmessages` endpoint**; in private subnets without NAT, check interface VPC endpoints, DNS, and HTTPS security groups.
6. If encrypting sessions with a customer managed KMS key, verify KMS permissions and network reachability to KMS.
7. Image/container allows ECS Exec writes and has spare CPU/RAM; **`readonlyRootFilesystem`** is incompatible.
8. AWS CLI and **Session Manager plugin** versions are compatible, and the shell binary exists.

When tasks use an HTTP proxy, verify **`NO_PROXY`** excludes metadata/task role endpoints (e.g., **`169.254.169.254`** and **`169.254.170.2`** where used), or credential retrieval can fail.

**Note:** ECS Exec cannot "rescue" a `STOPPED` task; for stopped tasks, rely on logs, stop reasons, exit codes, and stored events.

## 6. Logging and Auditing ECS Exec Sessions

Application container logging and **ECS Exec session logging** are **two separate mechanisms**. Application logs are controlled by the log driver; ECS Exec logging is controlled by **`executeCommandConfiguration`** at the ECS cluster level.

| ECS Exec Logging Mode | Behavior |
|---|---|
| **`NONE`** | Does not ship exec session transcripts via this mechanism |
| **`DEFAULT`** | Ships session logs to CloudWatch Logs per task definition **`awslogs`**; if no suitable `awslogs` exists, no session logs land there |
| **`OVERRIDE`** | Targets a specified CloudWatch log group or S3 bucket (or both) per cluster execute-command configuration |

AWS uses **CloudTrail** to record **`ExecuteCommand`** API events showing which principal started a session; auditing **full shell input/output** requires explicit session logging. To upload exec transcripts to S3/CloudWatch Logs as supported, the container image needs **`script`** and **`cat`** binaries; ultra-minimal images may fail to upload transcripts even while interactive sessions work.

**Production controls:** limit who may run ECS Exec, require approvals, enforce log retention and KMS encryption if mandated, restrict log read access, and never type secrets into commands. Because Exec runs as root, tight IAM/cluster/container scoping is critical.

## 7. Stopped Tasks: Understanding Status, `stopCode`, and `exitCode`

An ECS task transitions through **`PROVISIONING`**, **`PENDING`**, **`ACTIVATING`**, **`RUNNING`**, **`DEACTIVATING`**, **`STOPPING`**, **`DEPROVISIONING`**, and **`STOPPED`** depending on stage and launch type. **`STOPPED` is not always an error:**

- A standalone batch task finishing normally enters `STOPPED` with exit code **`0`**.
- An ECS service intentionally stops tasks during rollouts or scale-in.
- An essential container crashes, forcing the task to `STOPPED`.
- Task launch fails due to image, network, IAM, or resource constraints.

### 7.1. Key Fields to Inspect

| Field in `DescribeTasks` | How to Read It | Do Not Confuse With |
|---|---|---|
| **`lastStatus` / `desiredStatus`** | Current and target task states | `STOPPED` alone does not prove a failure |
| **`stopCode`** | API-level stop reason category | Detailed error strings like `ResourceInitializationError` |
| **`stoppedReason`** | Human-readable stop message | Unsuitable for rigid exact-string automation matching |
| **`stoppingAt` / `stoppedAt`** | Timestamps of termination | Does not replace application logs |
| **`containers[].name`** | Which container in the task | Tasks can hold multiple essential and nonessential containers |
| **`containers[].exitCode`** | Process exit code of the container, when present | Not the ECS `stopCode` |
| **`containers[].reason`** | Per-container error details, if recorded by ECS | Can be empty even when the process failed |
| **`containers[].lastStatus`** | Container-level status | Task-level state differs from container-level state |
| **`taskDefinitionArn`** | Revision that launched this task | Not automatically the latest registered revision |

**`stopCode` values** in the ECS Task API include **`TaskFailedToStart`**, **`EssentialContainerExited`**, **`UserInitiated`**, **`ServiceSchedulerInitiated`**, **`SpotInterruption`**, **`TerminationNotice`**, and **`InfrastructureHealth`** per AWS-supported enums. Meanwhile, strings like **`CannotPullContainerError`**, **`ResourceInitializationError`**, and **`OutOfMemoryError`** typically appear as **diagnostic message prefixes/reasons**, not necessarily as values of **`stopCode`**.

### 7.2. What Do Container Exit Codes Tell You?

| Observed `exitCode` | Common Interpretation | Additional Checks |
|---|---|---|
| **`0`** | Process exited cleanly | Intended batch/one-shot completion, or web server exiting prematurely? |
| **`1`** or other app code | Application returned an error code | Stack traces, config, dependencies, startup logic |
| **`137`** | Process received **`SIGKILL`**; sometimes from OOM | Task/container memory, OOM diagnostics, host/container events; never conclude from 137 alone |
| **`143`** | Process received **`SIGTERM`**, e.g., scale-in/deploy/controlled stop | ECS service events, deployments, timestamps, termination flow |
| **No `exitCode`** | Container never progressed far enough to exit | `stoppedReason`, image pulls, secrets, networking, initialization |

**Important:** **`143` is not automatically a bug**, **`137` is not always OOM**, and **`exitCode` `0` does not guarantee business success**. Correlate exit codes with `stopCode`, `stoppedReason`, timestamps, and logs before concluding.

## 8. Workflow for Investigating `STOPPED` Tasks

~~~mermaid
flowchart TD
    A["Detect STOPPED task / service capacity shortfall"] --> B["Record task ARN, cluster, Region,<br/>timestamp, task definition revision"]
    B --> C["DescribeTasks:<br/>stopCode, stoppedReason,<br/>containers[].exitCode/reason"]
    C --> D{"Did the container start?"}
    D -->|"No"| E["Image pull / secrets / logging<br/>IAM execution role / network / storage"]
    D -->|"Yes"| F["Application logs<br/>OOM / exit / health / signals"]
    E --> G["Service events + CloudTrail + metrics"]
    F --> G
    G --> H["Identify root cause<br/>and apply minimal fix"]
    H --> I["Test deploy and verify<br/>RUNNING, healthy, logs, SLO"]
~~~

### Step 1 — Capture Evidence Before It Disappears

Record **cluster, service, task ARN, task definition revision, Region, task stop time**, and all stop reasons. Per AWS docs, `STOPPED` tasks remain visible in the ECS Console for only about **one hour**; API retention is also limited. For long-term history, capture **ECS Task State Change events** with EventBridge alongside centralized logs and metrics.

### Step 2 — List and Describe Tasks

~~~bash
# List STOPPED tasks still returned by ECS.
aws ecs list-tasks \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --desired-status STOPPED

# Inspect stop reason and exit codes for a specific task.
aws ecs describe-tasks \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/training-cluster/TASK_ID \
  --query 'tasks[].{Task:taskArn,Definition:taskDefinitionArn,Status:lastStatus,StopCode:stopCode,StoppedReason:stoppedReason,StoppedAt:stoppedAt,Containers:containers[].{Name:name,Exit:exitCode,Reason:reason,Status:lastStatus}}' \
  --output json
~~~

If **`list-tasks`** no longer shows the task, check centralized logs, archived EventBridge events, or other telemetry; never assume the task never ran.

### Step 3 — Cross-Check Service Events

If the task belongs to an ECS service:

~~~bash
aws ecs describe-services \
  --region ap-southeast-1 \
  --cluster training-cluster \
  --services orders-api \
  --query 'services[].{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Deployments:deployments[].{Status:status,Desired:desiredCount,Running:runningCount},Events:events[0:10]}' \
  --output json
~~~

Events about **task placement**, **target group health**, **deployment failures**, **capacity**, or **resource constraints** separate app crashes from scheduler/infrastructure issues. For ALB-backed services, inspect target group health reasons and app logs—a scheduler can terminate a healthy-looking process simply because ALB health checks failed.

### Step 4 — Inspect Logs and Metrics

Locate the CloudWatch log stream by **task ID** and **container name**, filtering the minutes right before `STOPPED`. If logs are missing, check whether the container created the stream, whether the execution role has log permissions, whether the log group exists, and whether networking reaches CloudWatch Logs.

Correlate **CPU/memory**, OOM messages, DB connection errors, healthy target counts, and networking. For EC2 launch types, you may also inspect **ECS agent/container runtime logs on the EC2 host**; Fargate does not expose host logs directly.

### Step 5 — Form a Hypothesis and Test Under Control

Change **only one root cause** supported by evidence: fix the image tag, add exact execution role permissions, add a VPC endpoint, increase memory based on benchmarks, fix the ALB health path, or fix app config. Redeploy in a test environment and confirm tasks stay **`RUNNING`/healthy**, logs flow, APIs work, and crash loops stop.

## 9. Common Stopped Task Failure Categories

| Indicator | Common Causes | Primary Evidence | Resolution |
|---|---|---|---|
| **`CannotPullContainerError`** | Missing image tag/digest, lacking ECR permissions, registry unreachable | `stoppedReason`, ECR image, execution role, VPC endpoints | Verify image URI, pull permissions, routes, DNS, and ECR |
| **`ResourceInitializationError`** | Cannot fetch secrets, ECR auth, S3 env files, or CloudWatch Logs | Message in `stoppedReason`; execution role/networking | Check endpoints, SGs, NAT, IAM, and backing resources |
| **`ResourceNotFoundException`** | Missing secret/key/resource or wrong Region/ARN | `stoppedReason` and ARN | Fix name/ARN/Region and matching access permissions |
| **`EssentialContainerExited`** | Essential container process exited | `exitCode`, application logs | Fix app bug, startup command, config, or dependencies |
| **`OutOfMemoryError` / OOM** | Insufficient container/task memory or memory leak | ECS reason, `exitCode`, memory metrics, Java heap | Profile memory, tune JVM limits, increase memory, fix leaks |
| **`CannotStartContainerError`** | Bad entrypoint, file permissions, binary/architecture mismatch, mount error | `containers[].reason`, image metadata, app bootstrap | Fix image, command, CPU platform, or volume mounts |
| **Health check failures** | Wrong ALB/ECS health path/port, slow app startup | ECS service events, target group health | Fix `/ready`, SGs/ports, `startPeriod`/grace period |
| **`SpotInterruption` / termination** | Spot capacity reclaimed, abnormal host/capacity event | `stopCode`/events and infrastructure logs | Add retries, checkpoints, and reserve capacity |
| **Task placement failures** | Insufficient CPU/RAM, subnet IPs, quotas, AZ capacity, or constraints | Service events, placement/capacity errors | Add capacity or relax constraints/fix networking |
| **`ServiceSchedulerInitiated`** | Deployment, scale-in, or service health replacement | `stopCode`, service events, deployment timeline | Verify planned operation before treating as an incident |

**Never write automation matching exact `stoppedReason` prose** as a strict API contract; AWS may reword messages. Rely on structured **`stopCode`**, `exitCode`, and verifiable fields in events/logs, combining multiple signals where needed.

## 10. Scenario A: Task Fails to Pull Image in a Private Subnet

**Context:** An ECS Fargate service runs tasks in private subnets. After a release, tasks move **`PENDING` → `STOPPED`** with **`CannotPullContainerError`** or an ECR initialization failure.

Checks to run:

1. Does the **image URI and tag/digest** actually exist in ECR in the target Region and account?
2. Does the **task execution role** have required ECR permissions (such as **`ecr:GetAuthorizationToken`**, **`ecr:BatchGetImage`**, **`ecr:GetDownloadUrlForLayer`**)?
3. Do tasks have an HTTPS network path to ECR APIs/registry?
4. In private subnets without NAT, do **VPC interface endpoints `ecr.api`, `ecr.dkr`** and an **S3 gateway endpoint** exist for image layers in supported setups?
5. Do security groups, endpoint SGs, DNS, route tables, NACLs, and image/cache policies align?

**Resolution:** fix the exact missing image, permission, or network leg. Never grant full ECR admin to the application task role; image pulls run under the **execution role**, and verify endpoints for your Fargate platform/Region.

## 11. Scenario B: Logs Never Appear in CloudWatch

**Context:** ECS tasks stop right after launch, and CloudWatch log group **`/ecs/orders/prod`** has zero streams.

**Do not jump to "Java code isn't logging."** The container may have failed to launch or the `awslogs` driver failed to initialize. Check in order:

1. Does the active task definition revision define **`logConfiguration`** for the failing container?
2. Does **`awslogs-region`** match the log group you're viewing? Is **`awslogs-stream-prefix`** set for Fargate?
3. Does the log group already exist? If using **`awslogs-create-group`**, does the execution role have **`logs:CreateLogGroup`**?
4. Does the execution role have **`logs:CreateLogStream`** and **`logs:PutLogEvents`** on the matching resource?
5. Can tasks reach CloudWatch Logs via NAT or a **`logs`** VPC endpoint if required?
6. Does `stoppedReason` show **`ResourceInitializationError`** mentioning logger initialization?
7. If using FireLens, did the log router container crash or fail to connect to its destination?

Once log streams appear, record the mapping **`task ID → stream name`**. Set **retention** and log access controls to avoid storing sensitive data or uncapped log bills.

## 12. Scenario C: Java Service Stops Due to Memory

**Context:** A Fargate ECS task is allocated **512 MiB**, and the Java app loads large objects into memory. Tasks stop under traffic spikes with truncated logs or no final stack trace.

**Diagnostic steps:**

1. Inspect **`containers[].exitCode`**, `stoppedReason`, and any **`OutOfMemoryError`** messages.
2. Check CloudWatch/Container Insights memory metrics, spike timing, and recent releases.
3. Account separately for **Java heap**, **off-heap/native memory**, thread stacks, metaspace, and JVM/container overhead.
4. Compare JVM flags and heap limits against the **task/container memory limit**; never set `Xmx` to 100% of container memory ignoring native overhead.
5. Reproduce in staging with representative datasets/traffic to separate memory leaks from under-sizing.

**Why isn't `exitCode` `137` conclusive?** It indicates `SIGKILL`, which can come from other sources too. Confirm OOM using memory metrics, stop reasons/logs, or runtime diagnostics.

### Java Logging Practice

A Java application should log errors with **`requestId`**, error type, and actionable context:

~~~java
try {
    processOrder(orderId);
} catch (Exception ex) {
    log.error("Order processing failed: orderId={}", orderId, ex);
    throw ex;
}
~~~

Illustrative code only; **`orderId`** must contain no sensitive data. When logging exceptions, guard against stack traces or messages leaking tokens, request bodies, or PII. Standardize logging libraries and structured fields across services.

## 13. Scenario D: Task Is `RUNNING` Yet Replaced Continuously by ALB

**Context:** The Java process runs, yet ECS service events show targets turning unhealthy, causing the service to stop tasks and launch replacements.

**Likely causes:**

- ALB health check hits **`/health`** while the app exposes **`/actuator/health/readiness`**.
- Container listens on **`8080`** while target group/SG uses another port.
- App boots slowly and isn't ready when probed; **`healthCheckGracePeriodSeconds`** or `startPeriod` is too short.
- Health endpoint returns 500 because an optional dependency failed, causing unnecessary task churn.
- Routes, security groups, or NACLs between ALB subnets and task ENIs block probes.

**Resolution:** compare ECS service events, ALB target group health reasons, and app access logs. Fix the health endpoint/protocol/port or grace period. Never bump `desiredCount` just to mask continuous task churn.

**Liveness vs. readiness:** liveness tells whether the process needs restarting; readiness tells whether it can serve traffic. Design health endpoints around true serving readiness without tying them to non-essential services.

## 14. Scenario E: ECS Exec Reports `TargetNotConnectedException`

**Context:** A service is `RUNNING`, yet **`aws ecs execute-command`** fails with **`TargetNotConnectedException`** or times out.

Verification checklist:

| Check | Expected State |
|---|---|
| Task launched with ECS Exec | **`enableExecuteCommand = true`** |
| SSM agent | **`containers[].managedAgents`** shows `ExecuteCommandAgent` **`RUNNING`** |
| IAM task role | **`ssmmessages`** actions allowed |
| IAM operator | **`ecs:ExecuteCommand`** allowed for cluster/task/container |
| Network path | Task reaches **`ssmmessages`** endpoint over HTTPS |
| VPC endpoints | SGs/DNS/routing for `ssmmessages` and KMS if using customer managed key |
| Container image | Valid shell installed, writable filesystem, spare CPU/memory |
| Client | Compatible AWS CLI and Session Manager plugin |

**Never open SSH ports or change the task role to `AdministratorAccess` as a trial-and-error fix.** If using `readonlyRootFilesystem`, design alternative diagnostics or an approved image/config change for that workload.

## 15. Retaining Task Events for Investigation After One Hour

Because `STOPPED` tasks vanish quickly from the ECS Console, production systems should capture **ECS Task State Change events** via **Amazon EventBridge** and forward them to durable storage/pipelines: CloudWatch Logs, SQS, Lambda, EventBridge archives, or your observability store.

Events carry fields such as **`source = aws.ecs`**, **`detail-type = ECS Task State Change`**, **`detail.lastStatus`**, **`detail.stopCode`**, **`detail.stoppedReason`**, and **`detail.containers[].exitCode`**.

Example EventBridge rule pattern to capture `STOPPED` tasks:

~~~json
{
  "source": ["aws.ecs"],
  "detail-type": ["ECS Task State Change"],
  "detail": {
    "lastStatus": ["STOPPED"]
  }
}
~~~

The pattern only matches events—it does not create a destination. Configure an **EventBridge target**, IAM role/resource policy, retention, sensitive-data filtering, and alert routing. Planned stops during service rollouts also emit `STOPPED` events, so alerts must distinguish **planned stops** from **abnormal task failures**.

### 15.1. Tiering Alerts by Severity

Suggested tiers:

| Severity | Example | Action |
|---|---|---|
| **P1** | Service loses all healthy targets; `desired > running` persists | Page on-call; evaluate rollback/recovery |
| **P2** | Elevated `STOPPED` task rate after deployment | Inspect `stopCode`, service events, logs |
| **P3** | Single standalone batch task failed with retries/DLQ active | Log, retry per design, alert if threshold breached |
| **Info** | Planned `STOPPED` task from service scheduler rollout | Record event; suppress paging if service stays healthy |

Tune thresholds to SLOs, prod/staging tiers, workload groups, and alert fatigue. Never page P1 on every single `STOPPED` event.

## 16. Security, Permissions, and Boundaries During Diagnostics

### 16.1. Least Privilege Across Every Access Path

| Role | Typical Permissions | Avoid |
|---|---|---|
| **Developer reading logs** | `logs:DescribeLogStreams`, `logs:FilterLogEvents`, or scoped query rights | Unneeded permissions to edit/delete log groups |
| **ECS operator** | `ecs:DescribeTasks`, `ecs:ListTasks`, `ecs:DescribeServices` scoped by cluster/service | Mutating rights across all ECS clusters unnecessarily |
| **ECS Exec operator** | `ecs:ExecuteCommand` scoped to cluster/task/container plus required KMS/session rights | Enabling ECS Exec everywhere or bypassing audit logs |
| **Task execution role** | ECR pull, `awslogs`, task-definition secret injection | Account-wide S3/DynamoDB rights for the app |
| **Task role** | App APIs + `ssmmessages` only when ECS Exec is enabled | `AdministratorAccess`, dumping all secrets in logs/debug |

ECS Exec runs as **root inside the container**: allow it only on approved tasks, with audit logging and timeouts. Never run diagnostic commands that alter production data without formal change control.

### 16.2. Keep Sensitive Data Out of Logs

Configure filters/redaction for:

- AWS access keys, session tokens, API tokens, passwords, and connection strings.
- `Authorization`/`Cookie` headers and unnecessary personal identifiers.
- Full request/response bodies or stack traces carrying personal payloads.
- Command/terminal output when ECS Exec session auditing is active.

Verify **log Region**, KMS encryption, retention, and read access. Comprehensive logging retained indefinitely or exposed broadly creates both security exposure and high bills.

### 16.3. Why Can't You Rely on ECS Exec Every Time?

You cannot Exec into `STOPPED` tasks, tasks launched without the flag, shell-less images, or `readonlyRootFilesystem` setups. Moreover, operators should not depend on interactive shells to verify SLOs. **Logs, metrics, state events, health checks, and tracing** must be built ahead of incidents.

## 17. Standard Workflow for Deployment and Incident Handling

### Before Deployment

1. Configure task definitions with **`awslogs`** or FireLens, pre-creating log groups and retention.
2. Separate **task execution role** and **task role**; verify ECR/image, secrets, KMS, and VPC connectivity.
3. Enable **CloudWatch metrics/Container Insights**, ECS service event monitoring, EventBridge state capture, and SLOs.
4. Where ECS Exec is needed in specific environments, opt in tightly with `ssmmessages`, operator IAM, session logging, and dry runs.
5. Add meaningful health checks, graceful shutdown, and memory/CPU headroom for the app plus sidecars/SSM agent.

### When Tasks Stop Abnormally

1. **Do not immediately alter permissions or capacity.** Record timestamps, deployment version, task ARN, and cluster/Region.
2. Inspect **`stopCode` + `stoppedReason` + `containers[].exitCode/reason`**.
3. Inspect **service events** for deployments, scale-in, or health replacements.
4. Check **CloudWatch Logs** by task ID; if empty, check logger config, execution role, and networking.
5. Check **metrics** to verify memory, CPU, and health; check archived events if the task aged out of ECS APIs.
6. Reproduce in staging/lab; for live `RUNNING` tasks, use approved ECS Exec if needed.
7. Fix the root cause, deploy with rollback protection, and verify stable tasks, healthy targets, complete logs, and passing SLOs.

### After the Incident

Document **root cause, evidence, changes applied, post-fix verification, residual risk, and preventive actions**. If investigation was slowed by missing logs or expired task history, prioritize adding observability immediately.

## 18. Practice Exercises

### Exercise A — Setting Up Logging for a Java API

A Fargate Java service has container **`billing-api`**. Goal: store `stdout`/`stderr` in CloudWatch Logs, trace each task by ID, and enforce organizational retention.

**Task:** propose the log group, stream prefix, execution role permissions, and a **`logConfiguration`** snippet. Describe how to verify post-deploy using **`aws logs tail`** and **`ecs describe-tasks`**.

**Hint:** log group **`/ecs/billing/prod`**, prefix **`billing`**; use **`awslogs`**, pre-create the log group, grant **`logs:CreateLogStream`/`PutLogEvents`** on the execution role, then inspect streams named **`billing/billing-api/TASK_ID`**.

### Exercise B — CloudWatch Has No Logs

A task `STOPPED` before printing "Application started"; `stoppedReason` mentions **`ResourceInitializationError`** and CloudWatch logging.

**Task:** list at least four hypotheses to check before blaming Java application bugs.

**Hint:** missing log group, wrong Region, missing execution role permissions, no network path to **`logs`** endpoint, bad `awslogs` config, or container never started.

### Exercise C — ECS Exec Has No `RUNNING` Agent

A task is `RUNNING` with **`enableExecuteCommand = false`**. An engineer with `ecs:ExecuteCommand` still fails to open a session.

**Task:** explain why IAM Allow is insufficient and propose the fix.

**Hint:** the running task was not created with ECS Exec enabled. Enable it on the service/launch **new tasks**, plan the deployment, and verify `managedAgent`, task role `ssmmessages`, networking, and plugin. You cannot flip the flag on an existing task.

### Exercise D — Container Exit Code 137

A Java worker stops with **`exitCode` `137`** and the service replaces it. Memory utilization spiked at the time of failure.

**Task:** list evidence confirming OOM, how to distinguish OOM from other `SIGKILL` causes, and long-term fixes.

**Hint:** correlate reason/CloudWatch metrics/runtime logs, JVM heap/off-heap/threads, memory limits, and load tests. Fix memory leaks, switch to streaming/chunking, or right-size memory—never blindly raise RAM without finding why it grew.

### Exercise E — EventBridge Alerts Too Noisy

The system pages P1 on every **`ECS Task State Change` → `STOPPED`** event, including normal rolling updates.

**Task:** design cleaner filtering and alerting.

**Hint:** inspect `stopCode` alongside service deployments/desired/healthy targets, alert on abnormal `STOPPED` rates, exclude clean batch exits (`0`), archive all events for history, and anchor paging on metrics/SLOs.

## 19. Production Checklist

- [ ] Task definition sets an appropriate log driver for every container needing observability.
- [ ] Log group, Region, stream prefix, retention, and encryption are configured.
- [ ] **Execution role** holds image pull, logging, and secret injection permissions per task definition.
- [ ] **Task role** holds only app API permissions; `ssmmessages` added only when ECS Exec is approved.
- [ ] Logs include timestamp, severity, service, version, and request/trace ID without exposing secrets.
- [ ] FireLens router/sidecar (if used) has dedicated resources, retries, logs, and monitoring.
- [ ] CloudWatch metrics, Container Insights, or equivalent telemetry is active.
- [ ] Pipeline captures **ECS task `STOPPED` events** via EventBridge for long-term investigation.
- [ ] Runbooks exist for reading `stopCode`, `stoppedReason`, container `exitCode`, and service events.
- [ ] ECS Exec is enabled only for new tasks via approved processes, with scoped operator IAM and Session Manager plugin.
- [ ] Exec-enabled tasks have **`ExecuteCommandAgent` `RUNNING`**, reachability to `ssmmessages`, and writable root filesystem.
- [ ] Exec sessions have audit logging; since ECS Exec runs as root, access is tightly restricted.
- [ ] Tested image pulls, secrets, CloudWatch Logs, DNS/VPC endpoints, and ALB health checks.
- [ ] Tested graceful shutdown, OOM/crash behavior, deployment replacement, and batch retries.
- [ ] Log ingestion/storage/query costs, FireLens overhead, CloudWatch, and networking are budgeted.

## 20. Takeaways

When an ECS task stops, **collect evidence first**: container logs if present, **`stopCode`**, **`stoppedReason`**, **`exitCode`**, service events, and metrics around that timestamp. **`awslogs`** captures container `stdout`/`stderr`, while **FireLens** handles advanced log routing; these permissions typically involve the **task execution role** and networking. **ECS Exec** enables interactive inspection of an opted-in **`RUNNING`** task using **SSM Session Manager**, **task role `ssmmessages`**, operator permissions, and proper auditing—it cannot inspect a task after it becomes `STOPPED`. A well-run architecture puts **logging, metrics, task state events, least-privilege IAM, network endpoints, and tested runbooks** in place before incidents happen.

### Official AWS Documentation for Deployment Reference

- [Amazon ECS task logging with awslogs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html) — container log collection.
- [LogConfiguration API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_LogConfiguration.html) — log drivers and parameters.
- [Using FireLens to route container logs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_firelens.html) — sidecar and routing.
- [Monitor Amazon ECS containers with ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) — prerequisites, permissions, limits, session logging.
- [Running commands using ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec-run.html) — AWS CLI commands and Session Manager plugin.
- [Amazon ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) — application permissions.
- [Amazon ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) — ECR/log/secrets permissions.
- [Viewing Amazon ECS stopped task errors](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stopped-task-errors.html) — CLI and ECS Console.
- [Amazon ECS stopped task error categories](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stopped-task-error-codes.html) — stop error categories.
- [Resolve Amazon ECS stopped task errors](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/resolve-stopped-errors.html) — remediation approaches.
- [ECS task API stopCode and stoppedReason](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Task.html) — status field definitions.
- [ECS task lifecycle events and EventBridge](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-lifecycle-events.html) — lifecycle event capture.
- [Troubleshooting ECS OutOfMemoryError](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/out-of-memory.html) — memory failures.
- [CloudWatch Logs Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html) — querying logs.
- [Amazon ECS pricing](https://aws.amazon.com/ecs/pricing/) and [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) — operational cost.
