# Confirming Launch Requests and Tracking Completion

In the **Launching** chapter of the **SPRING_CLOUD_TASK** module, a system can initiate a Spring Cloud Task from an admin UI, an API, a scheduler, or a message. Submitting a request is usually fast, whereas the task itself may take several minutes to run. Therefore, you must answer **two distinct questions**:

1. **Has the launch system accepted the request?** (launch acknowledgement).
2. **Has the task actually finished, and did it succeed?** (completion verification).

These are not the same state. An accepted launch command can still fail while downloading the artifact, creating the container, initializing `ApplicationContext`, executing business logic, or writing the final result to `TaskRepository`. Conversely, if the HTTP response is lost after the server accepted the request, the caller might assume a failure and accidentally launch it **twice**.

This lesson uses **Spring Cloud Data Flow (SCDF)** as an example of a task orchestrator, while explaining how the same principles apply to Kubernetes Jobs, schedulers, and `TaskLaunchRequest` over Spring Cloud Stream. The focus is on building a tracking chain from **request** → **execution** → **business outcome** and running retries safely.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `accepted`, `launched`, `running`, `completed`, `failed`, and unknown states.
- Identify the **launch request** ID, `TaskExecution.executionId`, and external IDs (pod/job/runtime) without mixing them up.
- Call the SCDF task-launch API and use the ID/link from the response to query status.
- Design polling with timeouts, backoff, checks on `endTime`, `exitCode`, `exitMessage`, and business success criteria.
- Track failures occurring before `ApplicationContext` finishes initializing, killed processes, and un-updated metadata cases.
- Handle lost launch responses without creating duplicate tasks.
- Coordinate Spring Cloud Task exit codes with `JobExecution` status when the task runs Spring Batch.
- Propose monitoring, alerting, and security practices for scheduled or on-demand applications.

## 2. Three Levels of Confirmation

A request to run an end-of-day report can pass through these stages:

~~~mermaid
flowchart TD
    A["User / scheduler sends request"] --> B{"Did orchestrator accept?"}
    B -->|"No"| X["Rejected / acceptance unknown"]
    B -->|"Yes"| C["ACK + request code / execution id"]
    C --> D["Create process / Kubernetes Job / pod"]
    D --> E["Spring Boot initializes ApplicationContext"]
    E --> F["Spring Cloud Task writes START when possible"]
    F --> G["ApplicationRunner / Spring Batch processes"]
    G --> H["Write outcome and end status when possible"]
    H --> I["Process exits; orchestrator updates status"]
    I --> J{"Business data valid?"}
    J -->|"Yes"| K["Confirm completion"]
    J -->|"No"| L["Failed / needs reconciliation"]
    D -. "May fail" .-> L
    E -. "May fail early" .-> L
    G -. "May fail" .-> L
~~~

You should distinguish **three levels of evidence**:

| Level | Evidence | What It Proves | What It Does **Not** Prove Yet |
| --- | --- | --- | --- |
| **Acceptance** | HTTP 201/202, launcher response, message received | The orchestrator accepted or registered the request per API contract | The app actually ran or data was created |
| **Execution** | Process/pod/Job is running, `TaskExecution` has `startTime` | Execution activity has been observed by one or more systems | The task finished successfully |
| **Completion** | Runtime exited, `TaskExecution.endTime` and `exitCode`, verified output | Evidence exists to classify the outcome | All external side effects are atomic without extra design |

What to avoid is equating **"Launched task"** with **"Task completed successfully"**. An acknowledgement from the launcher is normally only a signal of the initial step, not certification of business results.

## 3. Identifiers to Record from the Start

In a system with multiple attempts, distinguish:

| Identifier | Created By | Purpose | Kept Across Retries? |
| --- | --- | --- | --- |
| `requestId` / `runId` defined by orchestrator | API/scheduler before launch | Identifies **one business request** and correlates logs | **Should stay the same** when retrying the same request |
| `TaskExecution.executionId` | Spring Cloud Task / SCDF via metadata store | Identifies **one physical execution** | Usually **differs** across runs |
| `externalExecutionId` | Deployer/runtime when supported by integration | Links task to a process, pod, or platform deployment | May differ across runs |
| `JobExecutionId` | Spring Batch | Identifies one Batch Job execution | May change across runs/restarts |
| Business key | Business system | Prevents duplicate side effects, e.g., `tenantId+businessDate+version` | **Must be stable** for the same request |

**Example:** a user submits request `REQ-20261124-017` to generate the report for Nov 24. The first launch gets execution ID `101` but ends in failure; the retry gets ID `102`. Both must be linked to the same `requestId` and business key, while the business report should appear only once if created successfully.

Never use `TASK_EXECUTION_ID` to prevent duplicate business writes: it is the technical ID of **an execution**, not of **the requested business work**.

## 4. Example: Issuing a Launch Command with Spring Cloud Data Flow

Spring Cloud Data Flow supports defining task applications and launching them via shell or REST API. This example assumes:

- An SCDF server is running at the illustrative address `http://localhost:9393`.
- A Task definition named `dailySummary` is registered and points to a compatible Spring Cloud Task artifact.
- SCDF has a configured launch platform and a matching metadata data source.
- The calling user/application is authorized to perform launches.

### 4.1. Launching via Data Flow Shell

Example:

~~~text
dataflow:> task launch dailySummary --arguments "--businessDate=2026-11-24"
Launched task 'dailySummary'
~~~

The string `Launched task` means the launch command was accepted/processed by the orchestration tool—**not** that the report was generated. Task names and shell syntax must match your running SCDF version.

Immediately afterward you can monitor:

~~~text
dataflow:> task execution list --name dailySummary
dataflow:> task execution status --id 101
~~~

The value `101` is only an illustrative ID; replace it with the actual execution ID. Output and field sets may vary by SCDF version, Spring Boot version, and platform configuration.

### 4.2. Launching via REST API

SCDF documentation describes the **`POST /tasks/executions/launch`** endpoint for launching tasks. Example with `curl`:

~~~bash
curl -i -X POST "http://localhost:9393/tasks/executions/launch"   --data-urlencode "name=dailySummary"   --data-urlencode "arguments=--businessDate=2026-11-24"
~~~

Illustrative success response, **only showing data shape**:

~~~http
HTTP/1.1 201 Created
Content-Type: application/hal+json
~~~

~~~json
{
  "executionId": 101,
  "schemaTarget": "boot2",
  "_links": {
    "self": {
      "href": "http://localhost:9393/tasks/executions/101?schemaTarget=boot2"
    }
  }
}
~~~

In a real system, `executionId` is newly assigned; `schemaTarget` depends on schema type/version and must not be assumed to always be `boot2`. **Use the returned `_links.self.href` directly for tracking**, rather than manually constructing URLs or schema targets unnecessarily.

**Key takeaway:** HTTP `201 Created` and `executionId` are **a response for creating/registering the execution**. They **do not** promise that the process has finished or that `exitCode=0`.

Some older SCDF versions have a **`POST /tasks/executions`** (legacy) endpoint; SCDF docs distinguish that legacy endpoint from `/tasks/executions/launch` and note limitations of the legacy endpoint with Spring Boot 3 applications. Therefore, never copy an endpoint from an old article without checking it against your running server.

## 5. Tracking Through to Completion

After receiving the launch response, the caller should **save the lookup ID/link** and begin checking status in a separate step. With the SCDF REST API, use the `self` link from the response:

~~~bash
curl -i "http://localhost:9393/tasks/executions/101?schemaTarget=boot2"
~~~

The response typically contains fields similar to:

~~~json
{
  "executionId": 101,
  "taskName": "dailySummary",
  "startTime": "2026-11-24T01:00:00",
  "endTime": "2026-11-24T01:00:08",
  "exitCode": 0,
  "exitMessage": "COMPLETED;rows=1500",
  "errorMessage": null,
  "externalExecutionId": "runtime-generated-id",
  "taskExecutionStatus": "COMPLETE"
}
~~~

This is an **abbreviated, illustrative payload**, not a mandatory verbatim API response. Field types/statuses/names and HAL links vary by version and platform. On early polls, `startTime`, `endTime`, `exitCode`, or status may still be incomplete.

### Criteria for Confirming Completion

Evaluate multiple pieces of evidence together:

1. **Platform status:** pod/process/Job has terminated or is at least no longer running.
2. **Task metadata:** the record has `endTime` and `exitCode` when the repository remains reachable.
3. **Result code:** `exitCode=0` under the app's policy indicates success; non-zero requires investigation, though it does not always mean all business effects rolled back.
4. **Business output:** files, report records, or checksums exist and satisfy required invariants.
5. **Error context:** inspect `errorMessage`, `exitMessage`, and logs to understand the cause.

**`endTime=null` is not enough to conclude "still running"**: the process may have died before updating metadata. Conversely, an application may write final metadata before the OS finishes reclaiming all runtime resources. When data conflicts, transition to reconciliation instead of guessing the outcome.

## 6. Designing Polling Properly

Polling means repeatedly calling a status endpoint at intervals—**not resending the launch command**. Repeatedly calling `POST /launch` can spawn additional executions.

Recommended workflow:

~~~text
POST /launch (exactly once per requestId when acceptance is still unknown)
    -> save executionId and self href
    -> GET self href after a wait interval
    -> if not finished yet: wait with backoff then GET again
    -> if finished: verify exitCode and business outcome
    -> if past deadline or monitoring source fails: UNKNOWN, alert/reconcile
~~~

**Pseudocode** algorithm example—not a concrete Java API:

~~~java
LaunchReceipt receipt = launcher.launchOnce(requestId, arguments);
saveReceipt(requestId, receipt.executionId(), receipt.statusUrl());

long deadline = clock.millis() + timeoutMillis;
long delay = initialDelayMillis;

while (clock.millis() < deadline) {
    TaskState state = monitor.fetch(receipt.statusUrl());

    if (state.hasTerminalPlatformState()) {
        return reconcileTaskAndBusinessResult(requestId, state);
    }

    sleep(delay);
    delay = Math.min(maxDelayMillis, delay * 2);
}

return markNeedsReconciliation(requestId, "TIMEOUT_WAITING_FOR_COMPLETION");
~~~

Interfaces `LaunchReceipt`, `TaskState`, `launcher`, and `monitor` are **design concepts only**, not built-in Spring Cloud Task classes. Your implementation must handle `HTTP 404/429/5xx`, network drops, timeouts, and retries of the GET call.

### Important Polling Principles

- **Enforce a deadline:** a run exceeding its time budget should enter `TIMED_OUT` or `UNKNOWN` in the orchestrator and trigger an alert.
- **Use backoff/jitter:** never poll every few milliseconds, especially with thousands of concurrent tasks.
- **Never repeat POST:** poll with status GETs, and only relaunch after a safe business decision.
- **Do not treat a 404 immediately as "never ran":** it could be a wrong schema target, unsynchronized data source, purged record, or environment mismatch.
- **Preserve the correlation ID:** polling logs and outcomes must link back to the original request.
- **Separate unknown state:** if REST/server/JDBC stops responding, do not jump straight to "FAILED" or "SUCCESS" without sufficient evidence.

## 7. State Model at the Orchestration Layer

An internal API can define its own states to present progress clearly. The names below are **business recommendations**, **not default enums** of Spring Cloud Task or Spring Cloud Data Flow:

| Orchestration State | Meaning | Possible Transitions |
| --- | --- | --- |
| `RECEIVED` | Received and persisted request with `requestId` | `LAUNCHING`, `REJECTED` |
| `LAUNCHING` | Requesting the platform to create a run | `ACCEPTED`, `UNKNOWN`, `REJECTED` |
| `ACCEPTED` | Received launch response/ID per contract | `RUNNING`, `FAILED`, `UNKNOWN` |
| `RUNNING` | Evidence exists that the process is executing | `SUCCEEDED`, `FAILED`, `UNKNOWN` |
| `SUCCEEDED` | Reconciled complete against business criteria | Terminal |
| `FAILED` | Evidence of failure confirmed | Investigate / conditional retry |
| `UNKNOWN` | Insufficient evidence to determine outcome | Reconcile, wait/investigate |
| `REJECTED` | Request not accepted | Fix input/permissions, submit a new request |

Real systems may observe **runs shorter than the polling interval**. A task can finish so quickly that you never observe `RUNNING`; that does not break tracking as long as the final outcome is thoroughly verified.

### Do Not Fabricate "Succeeded" from HTTP 201

If designing your own user-facing API, you can return:

~~~http
HTTP/1.1 202 Accepted
Location: /api/task-requests/REQ-20261124-017
~~~

~~~json
{
  "requestId": "REQ-20261124-017",
  "status": "ACCEPTED",
  "statusUrl": "/api/task-requests/REQ-20261124-017"
}
~~~

This is **a custom API example designed by your team**, **not a default Spring Cloud Task endpoint**. The status endpoint can expose `executionId`, timestamps, business results, and links to logs or SCDF, while avoiding forcing callers to hold the initial HTTP request open until the task finishes.

## 8. Example Spring Cloud Task Application to Verify Outcomes

Suppose `dailySummary` is a Spring Boot + Spring Cloud Task application. A simple runner helps illustrate success and failure cases.

Create `src/main/java/com/example/task/DailySummaryApplication.java`:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DailySummaryApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DailySummaryApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    ApplicationRunner dailySummary() {
        return arguments -> {
            List<String> dates = arguments.getOptionValues("businessDate");

            if (dates == null || dates.size() != 1
                    || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Requires exactly one --businessDate=YYYY-MM-DD");
            }

            LocalDate date = LocalDate.parse(dates.get(0));

            if (arguments.containsOption("failDemo")) {
                throw new IllegalStateException("Simulated business error");
            }

            // In practice: call a service with transactions and idempotency.
            System.out.println("Report completed for " + date);
        };
    }
}
~~~

The project requires `spring-cloud-starter-task`, a Spring Boot starter, and a compatible JDBC driver, with matching Spring Boot parent/BOM and Spring Cloud BOM. Maven dependency snippet example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

To build an executable JAR, the project also needs `spring-boot-maven-plugin` in the `build` section of `pom.xml`. In standard setups, Spring Cloud Task auto-configuration can manage metadata without manually adding `@EnableTask`.

Illustrative `application.yml` configuration:

~~~yaml
spring:
  application:
    name: daily-summary
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  cloud:
    task:
      name: dailySummary
      initialize-enabled: false
~~~

Environment variables must point to a metadata database with a **version-matched pre-created** Spring Cloud Task schema; in SCDF environments, datasource sharing, schema targets, and application properties depend on platform configuration. Never hardcode passwords in committed `application.yml` files or launch parameters. This example is abbreviated and excludes the full POM/migrations.

Running a normal successful execution:

~~~bash
java -jar daily-summary.jar --businessDate=2026-11-24
~~~

Running an intentional failure in a test environment:

~~~bash
java -jar daily-summary.jar --businessDate=2026-11-24 --failDemo
~~~

In both cases, the program **started up**, yet only the first case completed the demo logic. When running via SCDF, **do not assume the launch response confirmed the runner's outcome**; fetch execution status and inspect the repository/logs.

Note: `System.out.println` only marks completion in a demo. For real reports, verify committed/exported output records/files and business correctness.

## 9. Querying TaskRepository After a Run

With a persistent JDBC repository, you can inspect metadata using the default schema:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'dailySummary'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

This SQL query is useful for reconciliation, but it does not replace using **the SCDF API** to query platform-specific details such as `externalExecutionId` or pod status.

Interpretation:

| Observation | Possible Meaning | What to Cross-Check |
| --- | --- | --- |
| `END_TIME IS NULL`, process still running | Task may still be executing | Runtime, deadlines, and logs |
| `END_TIME IS NULL`, process is dead | Completion metadata may not have been written | Pod reason, DB connectivity, business output |
| `EXIT_CODE = 0` and `END_TIME` present | Framework recorded a run completing with success code | Verify business output accuracy and completeness |
| `EXIT_CODE != 0` | Error reported via Task exit code | `ERROR_MESSAGE`, logs, Batch status if used |
| No record | May have failed before context became ready or queried wrong DB/schema | Launcher, container, app logs, datasource/schema target |
| Multiple records with the same `TASK_NAME` | Multiple executions, possibly from retries | Match via requestId/business key and handle duplicates |

If `EXIT_CODE` is `NULL`, never default it to `0`. A record that was initialized but never finished or failed to update may lack final fields.

### Two Moments Where Information Is Easily Lost

Spring Cloud Task records an execution after `ApplicationContext` has bootstrapped far enough. If bootstrapping fails **before `TaskRepository` creates a record**, you may see a platform error with **no `TaskExecution`**. If the JVM is killed after writing business output but before updating the repository, you may see a record missing `END_TIME` even though the work partially or fully completed.

Therefore, the orchestration system should manage launch requests **independently** of the repository, rather than using the Task table as the sole source of truth for all launch **attempts**.

## 10. When Launch Responses Are Lost: Avoiding Duplicate Runs

A commonly mishandled scenario:

1. Client sends `POST /launch`.
2. Server accepts it and may create an execution.
3. Network drops before the client receives the response.
4. Client treats this as a definite failure and resends POST.
5. Two processes may end up launched for one business key.

This is an **uncertain acceptance outcome** problem, similar to losing a response around `COMMIT`. Never assume an HTTP timeout means the server never executed the command.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orchestrator
    participant T as Task runtime
    C->>O: POST launch(requestId=REQ-17)
    O->>T: Initiate run
    O--xC: Response ACK lost
    Note over C,O: Client does not know if launch was accepted
    C->>O: GET status REQ-17 / query by correlation id
    O-->>C: Stored ID and status if present
    Note over C,T: Only retry launch per idempotent policy
~~~

### Deduplication Design at the Orchestration API Layer

If you build an API in front of SCDF, include:

- A client-supplied or stably server-issued `requestId` or `idempotencyKey`.
- A request table with a `UNIQUE(request_id)` constraint.
- Status data `RECEIVED/LAUNCHING/ACCEPTED/...`, validated parameters, and correlation IDs.
- Once SCDF responds, record `executionId`/`self href` onto the request row.
- When the client resends the **same** `requestId`, the API returns the existing status/receipt instead of launching a second time.
- Same `requestId` with different request payload must return a conflict error rather than silently swapping parameters.

**Hard boundary:** if the API system writes `LAUNCHING` to its database, sends the launch command to SCDF, and crashes before saving the execution ID, there is still a window where whether launch happened is uncertain. A unique table only prevents **duplicate requests** in your API; it **does not automatically guarantee exactly-once** across two systems. Reconcile with SCDF/runtime using a correlation ID and make the business logic idempotent as well.

### Prevent More Than Just Duplicate Launches

Even with a single execution, internal retries inside Spring Batch, API calls, or DB operations can create duplicate side effects. Use a **stable business key** such as `tenantId+businessDate+reportVersion` and unique/idempotency constraints where results are persisted.

## 11. Spring Cloud Stream TaskLaunchRequest: ACK Is Not Completion

Spring Cloud Task supports **launching a task from a stream** via a sink processing `TaskLaunchRequest` payloads. Per the API, a `TaskLaunchRequest` describes:

| Property | Meaning |
| --- | --- |
| `uri` | Artifact URI of the task |
| `applicationName` | Name assigned to the task created by the launcher |
| `commandLineArguments` | List of command-line arguments passed to the task |
| `environmentProperties` | Environment variables for the run |
| `deploymentProperties` | Deployment properties understood by the launcher/platform |

Java example creating the request (in a requesting application with compatible dependencies):

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.cloud.task.launcher.TaskLaunchRequest;

TaskLaunchRequest request = new TaskLaunchRequest(
        "maven://com.example:daily-summary-task:jar:1.0.0",
        List.of("--businessDate=2026-11-24"),
        Map.of(),
        Map.of(),
        "dailySummary");
~~~

This snippet illustrates the request structure, **not a complete application that sends messages itself**. In a system using Spring Cloud Stream and a compatible `@EnableTaskLauncher` sink, the request can arrive at the sink to be deployed via `TaskLauncher`. Artifact URIs and deployer choices depend on the environment.

It is crucial to distinguish:

1. **Broker persists / consumer receives message:** the launch request message traversed part of the pipeline.
2. **Task launcher accepts:** the sink may attempt to create the process/deployment.
3. **Task completes:** the separate application finished executing and recorded metadata if available.

ACKing a message on the broker **does not prove the task completed**. If a consumer processes a message more than once, it can trigger duplicate launches unless deduplication is in place. If the sink is killed after launching but before acknowledging the message, the same request may be redelivered.

Do not infer a synchronous reply/acknowledgement mechanism from the `TaskLaunchRequest` class alone; how receipts, correlation, and completion tracking work must be explicitly designed in the messaging architecture.

## 12. Kubernetes Jobs and Schedulers: Platform-Level Checks

When not using SCDF, the same principles apply to Kubernetes Jobs or cron:

| System | Acceptance Evidence | Running Evidence | Completion Evidence |
| --- | --- | --- | --- |
| Kubernetes | API server creates `Job` object | Pod created / `Running` | `Job.status.conditions`, `succeeded/failed`, Pod termination |
| OS Cron / scheduler | Schedule or execution command logged | PID/logs started | Exit code + logs and Task metadata |
| Custom orchestration API | HTTP `202 Accepted` + requestId | Runtime/external ID recorded | Runtime outcome + `TaskExecution` + business data |
| SCDF | Launch response with execution ID/schema target | Runtime status and Task metadata | Final status + exit code + reconciliation |

A created Kubernetes Job object **does not mean the Pod has started**, and a running Pod **does not mean the business outcome succeeded**. Inspect concrete failure reasons such as image pull failures, missing secrets, quotas, scheduling failures, `OOMKilled`, or deadline exceeded.

With Kubernetes, configure `backoffLimit`, `activeDeadlineSeconds`, and `concurrencyPolicy` for CronJobs according to operational goals. Platform-driven retries must align with business idempotency keys; never let the platform repeat a mutating operation without checks.

## 13. Integrating with Spring Batch

When Spring Cloud Task invokes a **Spring Batch Job**:

- `TaskExecution` reflects the **task application** lifecycle.
- `JobExecution` and `StepExecution` reflect the progress/failure of the **Batch Job** and its steps.
- Batch's `JobRepository` supports persisting state and restarting per the job's policy.
- `BatchStatus` and `ExitStatus` do not naturally map one-to-one with the Task exit code or business outcome.

An easily overlooked case is when a Batch Job fails yet the application fails to reflect that in the Task's exit code. Where supported by your Spring Cloud Task version, consider:

~~~yaml
spring:
  cloud:
    task:
      batch:
        fail-on-job-failure: true
~~~

Test with a failing job in staging and verify **Batch FAILED → non-zero Task exit code**, while checking the process status observed by the scheduler. Check the property against your exact Task/Batch versions.

If the Batch job finishes successfully but a post-processing step (file upload, notification) fails, decide whether that should fail **the overall task**. Do not rely solely on Job status to report success when the business requirement includes additional steps.

## 14. Designing User-Facing Result APIs

For an admin UI, a clear pattern is to return **an immediate receipt** and allow status retrieval via a dedicated endpoint:

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Task API
    participant O as SCDF / Scheduler
    participant R as TaskRepository
    U->>A: POST /api/task-requests
    A-->>U: 202 Accepted + requestId + statusUrl
    A->>O: Launch after duplicate check
    O-->>A: executionId / external id if available
    A->>R: Query metadata by executionId
    R-->>A: start/end/exit once recorded
    U->>A: GET statusUrl
    A-->>U: RUNNING / SUCCEEDED / FAILED / UNKNOWN
~~~

The response payload should return **minimal fields**:

~~~json
{
  "requestId": "REQ-20261124-017",
  "taskName": "dailySummary",
  "status": "SUCCEEDED",
  "executionId": 101,
  "startedAt": "2026-11-24T01:00:00Z",
  "finishedAt": "2026-11-24T01:00:08Z",
  "exitCode": 0,
  "result": {
    "reportId": "RPT-20261124-01"
  }
}
~~~

This is **an API schema you design**, not a default SCDF resource. The development team must align on semantics:

- `SUCCEEDED` is returned only once completion criteria are verified.
- `UNKNOWN` represents missing or conflicting evidence, not a generic error.
- `FAILED` should provide an understandable error code without exposing full stack traces or secrets.
- `result` contains only small metadata and links to actual business data; never stuff large reports into an HTTP status response.

The API should enforce authentication/authorization, rate limits on status reads, and retention/cleanup policies. Users should only see execution details within their authorized scope.

## 15. Errors and Diagnostics

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| POST launch returns `201` yet no report appears | Task hasn't run, startup error, runner error, or output not persisted | GET execution, inspect platform logs and business DB |
| POST times out, then two runs appear later | Client retried POST without idempotency/correlation | Check request logs, `executionId`, implement `requestId` + deduplication |
| Execution ID exists but `startTime=null` for a long time | Not deployed/started yet or missing metadata | Platform status, image/artifact, permissions, broker/cluster |
| `endTime=null` yet pod is dead | JVM killed or `TaskRepository` couldn't write completion | Pod termination reason, DB, logs, and output reconciliation |
| `exitCode=0` yet data is wrong | Application swallowed errors or didn't check business invariants | Inspect committed/exported output |
| `exitCode!=0` yet output exists | Output committed before a later step failed | Verify idempotency and decide safe retry |
| API GET returns 404 | Wrong execution ID/schema target, purged, unsynced data, or wrong environment | Use original self link, verify datasource/schema |
| Polling runs forever | Missing deadline or forgot to handle `UNKNOWN` state | Add timeouts, backoff, and alerts |
| Batch status FAILED yet Task SUCCESS | Status-mapping policy misconfigured | `fail-on-job-failure` and test exit code |
| Task invoked multiple times by overlapping cron | No business-key guard or concurrency control | Unique keys, coordination, and skip/retry policies |

### In What Order Should You Investigate?

1. **Launch layer:** `requestId`, HTTP status, `executionId`, self link, orchestrator server logs.
2. **Runtime layer:** whether process/pod was created, image/deployment/quota errors, actual exit code.
3. **TaskRepository layer:** whether `TaskExecution` has a record, timestamps/exit code/exit message.
4. **Business layer:** whether output data is accurate and complete, and whether duplicate side effects occurred.
5. **Batch layer (if any):** `JobExecution`/`StepExecution` and restart state.
6. **Monitoring layer:** events, logs, correlation, alerts, and concluded state.

Never look at just one table or one log line and declare success or failure when data sources disagree.

## 16. Pre-Production Checklist

- [ ] API/scheduler persists `requestId` durably before launching.
- [ ] Launch response and completion status are designed **separately**; never use HTTP 201 as business success.
- [ ] Store `executionId`, `schemaTarget`/self link, and external runtime ID when available.
- [ ] Track via polling with timeout/backoff or appropriate event channels; never poll by resending POST.
- [ ] Define an `UNKNOWN` state and reconciliation workflow for early bootstrap failures, killed JVMs, or lost DB connections.
- [ ] Final outcomes are verified by exit code **and** business invariants.
- [ ] Retries use a stable business key; duplicates are prevented at both orchestration and business-data layers.
- [ ] Tasks run against a persistent JDBC metadata database if cross-run tracking is needed.
- [ ] Separately verify Spring Batch Job/Step statuses and exit-code mapping policies if applicable.
- [ ] Secure APIs, logs, parameters, and response payloads; never expose secrets or stack traces.
- [ ] Test lost launch responses, startup task failures, killed processes, and timeouts in staging.

## 17. Exercises and Self-Check Questions

**Question 1.** SCDF returns HTTP `201 Created` and `executionId=101`. Does this prove the Nov 24 report was successfully generated? Why or why not?

**Question 2.** Why should the `requestId` issued by the API/scheduler remain the same across attempts, while `TASK_EXECUTION_ID` can change?

**Question 3.** If `endTime=null` yet Kubernetes reports the Job failed, which data sources would you check before allowing a re-run?

**Question 4.** How does polling differ from retrying a launch? What bug can happen if a frontend calls POST launch every 5 seconds?

**Question 5.** A client times out right after sending a launch request. Why should it not immediately send a new request without first querying the status of the original request?

**Exercise A — Designing an API contract.** Define `POST /api/task-requests` and `GET /api/task-requests/{requestId}` with `202 Accepted`, orchestration states, and conditions for reporting `SUCCEEDED`. Specify which data comes from SCDF and which comes from the business store.

**Exercise B — Resilient polling.** Describe or implement a worker that polls execution status using the self link from the launch response; bound attempts, timeout, and backoff. Handle `404`, `429`, and `503` without creating extra executions.

**Exercise C — Ambiguous launch.** Simulate the server accepting a launch while the response is lost. Design `requestId`/idempotency, reconciliation, and database constraints to guarantee a business key is not written twice.

**Exercise D — Comparing launch channels.** Compare SCDF REST, Spring Cloud Stream `TaskLaunchRequest`, and Kubernetes Jobs across four dimensions: receipt, execution ID, completion signal, and reliable data source.

**Exercise E — Batch integration.** Have a Batch Job return `FAILED` inside a Spring Cloud Task application. Compare `JobExecution`, `TaskExecution`, process exit code, and the condition for reporting results to users.

## 18. Key Takeaways

- **Confirming launch means request acceptance; confirming completion means proving the task finished and results meet requirements.** Both must be designed independently.
- SCDF can return **`executionId`/`schemaTarget`/self link** on acceptance. Save and use that link for tracking; HTTP `201` does not mean `exitCode=0`.
- `TaskExecution` shows timestamps and outcomes recorded by the framework; **having no record or missing `endTime` does not prove a task never ran**.
- Each retry may generate a new execution ID. **`requestId` and business keys** must stay stable for reconciliation and deduplicating side effects.
- Polling must include **timeouts, backoff, and UNKNOWN handling**; never confuse status GETs with launch POSTs.
- In applications using Spring Batch, inspect `JobExecution`/`StepExecution` and the policy mapping Batch failures to the Task exit code.
- Concluded user-facing status should rely on **runtime + TaskRepository + business outcome**, with independent observability from the scheduler/container.

## References

- [Spring Cloud Task — Features / Lifecycle](https://docs.spring.io/spring-cloud-task/reference/features.html): when `TaskExecution` is created/updated and startup failure limits.
- [Spring Cloud Task — Spring Cloud Stream Integration](https://docs.spring.io/spring-cloud-task/reference/stream.html): `TaskLaunchRequest`, `TaskLauncherSink`, and `@EnableTaskLauncher`.
- [Spring Cloud Task — TaskLaunchRequest API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/TaskLaunchRequest.html): URI, arguments, and deployment/environment properties fields.
- [Spring Cloud Data Flow — Reference Guide, Launching Tasks and Reviewing Task Executions](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/): shell, `/tasks/executions/launch` REST API, execution ID/schema target responses, and execution details.
- [Spring Cloud Data Flow — Task DSL API](https://docs.spring.io/spring-cloud-dataflow/docs/current/api/org/springframework/cloud/dataflow/rest/client/dsl/task/Task.html): asynchronous launching and status tracking.
- [Spring Cloud Data Flow — Task Execution Details](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/#_execution_detail): runtime info, arguments, exit messages, and logs.

Sample APIs must be verified against your actual Spring Cloud Data Flow version, Spring Cloud Task version, deployer platform, and security configuration; in particular, never use a legacy endpoint from one version to infer the REST contract of another.
