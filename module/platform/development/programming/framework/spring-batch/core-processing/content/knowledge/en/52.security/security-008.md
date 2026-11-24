# Authorizing Job Launch and Stop in Spring Batch

In a Spring Batch application, **launching a Job** (*launch*) and **requesting to stop a running Job** (*stop*) are operational actions that directly affect data, resources, and business workflow continuity. Someone permitted to view order-processing status is not automatically permitted to rerun a billing Job; someone allowed to launch a reporting Job is not inherently allowed to stop a running financial reconciliation Job.

This lesson belongs to the **Security** group in **Spring Batch Core Processing**, focusing on designing and enforcing authorization for Job control operations: who can **launch**, who can **stop**, on which Job or JobExecution, through which invocation paths, and how to audit and test those decisions.

The core approach is **Spring Security at the application layer combined with business policies**. `JobRepository`, `JobLauncher`, and `JobOperator` manage the Batch lifecycle, **but they are not end-user authorization mechanisms**. The application must wrap them in a protective layer.

## 1. Risks when Batch APIs lack authorization

Suppose an application has these Jobs:

- `dailySettlementJob`: end-of-day payment settlement.
- `importCatalogJob`: product catalog import.
- `customerExportJob`: customer data export.
- `rebuildSearchIndexJob`: search index rebuild.

If there is a generic API:

```http
POST /api/batch/jobs/{jobName}/run
POST /api/batch/executions/{executionId}/stop
```

that any authenticated user can call, an attacker or an over-privileged user could:

1. Launch a Job outside their responsibility, causing duplicate writes or data corruption.
2. Stop a critical Job before it finishes.
3. Supply anomalous JobParameters to read/write the wrong date, tenant, file, or environment.
4. Enumerate `jobExecutionId` values and request stopping another unit's execution.
5. Call repeatedly to spawn many JobInstances, overloading the database, worker pool, or downstream systems.
6. Hinder investigations because there is no trail of who requested the action and why.

Authorization is more than putting `@PreAuthorize` on a controller. You must control **identity**, **action permissions**, **specific resources**, **parameters**, **lifecycle state**, **non-HTTP invocation paths**, and **auditing**.

## 2. Distinguishing Job, JobInstance, JobExecution, and operation permissions

In Spring Batch:

- **`Job`** is the workflow definition, e.g., `dailySettlementJob`.
- **`JobInstance`** is a logical unit of work identified by the Job name plus **identifying JobParameters**.
- **`JobExecution`** is a specific attempt to run a JobInstance.
- **`StepExecution`** is a Step execution belonging to a JobExecution.

```text
Job: dailySettlementJob
│
├── JobInstance #100 (businessDate=2026-11-15)
│   ├── JobExecution #410 -> FAILED
│   └── JobExecution #411 -> COMPLETED (restart)
│
└── JobInstance #101 (businessDate=2026-11-16)
    └── JobExecution #412 -> STARTED
```

The two primary operations inspect different target resources:

| Operation | Resource to check | Policy example |
| --- | --- | --- |
| **Launch** | Job name, task type, parameters, environment, and target data scope | Catalog operators may launch `importCatalogJob`, but not the customer data export Job. |
| **Stop** | **Specific JobExecution**, associated JobInstance, tenant, environment, and current status | Only settlement operators may request stopping execution `#412`. |
| View status | JobExecution and metadata that may contain sensitive details | Viewers see only Jobs belonging to their project/tenant. |
| Restart | Failed/stopped execution, restartability, data rewrite impact | May require a separate `BATCH_RESTART` permission rather than inheriting launch permission by default. |

**Do not use a single blanket boolean `isBatchAdmin` for all actions** when business rules require finer-grained access control. Permissions to **view**, **launch**, **stop**, and **restart** are distinct capabilities.

## 3. Authentication vs. authorization

These two steps serve separate functions:

- **Authentication:** who is the caller? For example, an operations engineer signed in via an Identity Provider, or a scheduler service with a machine identity.
- **Authorization:** is that identity allowed to perform **this action** on **this object** in **this context**?

```text
Client / Scheduler
       |
       v
[Authentication]
  JWT / mTLS / session / workload identity
       |
       v
[Authorization]
  Action = BATCH_LAUNCH or BATCH_STOP
  Resource = jobName / jobExecutionId
  Context = tenant, environment, data scope, approval
       |
       +-- DENY --> HTTP 403 / internal rejection + audit
       |
       v
[Batch control service]
       |
       +-- Launch --> JobLauncher / JobOperator
       |
       +-- Stop ----> JobOperator
       |
       v
[JobRepository / JobExplorer]
```

`JobLauncher` and `JobOperator` **do not authenticate an HTTP caller themselves**. They are invoked by Java code that holds access to those beans/objects. Therefore, enforce policies in an **orchestrating service layer** or a consistent control layer rather than relying on method names like `start` or `stop`.

### Functional permissions and resource permissions

Use two layers:

1. **RBAC / scopes – functional permissions:** does the caller hold `batch.launch`, `batch.stop`, `batch.read`?
2. **ABAC / resource policy – object-level permissions:** which Job, which tenant, which business date, which environment, whose JobExecution, and is approval required?

For instance, a user with scope `batch.stop` still **must not stop every JobExecution in the system** if they only manage tenant `T1`. Functional permission is necessary, not sufficient.

## 4. Designing an authorization matrix before writing code

An illustrative matrix:

| Identity / role | View | Launch catalog | Launch settlement | Stop catalog | Stop settlement |
| --- | --- | --- | --- | --- | --- |
| Support staff | Jobs in assigned tenant | No | No | No | No |
| Catalog operator | Catalog Jobs in scope | Yes | No | Yes | No |
| Settlement operator | Settlement Jobs in scope | No | Yes within approved window | No | Yes per incident procedure |
| Scheduler identity | Assigned scheduled Jobs | Only Jobs configured for scheduler | Only on approved schedule | Not by default | Not by default |
| Batch administrator | Per policy and zone | Conditionally | Conditionally | Conditionally | Conditionally |

This matrix is illustrative only. In a real system, business rules, data sensitivity, and approval gates must be confirmed with workflow owners.

Name permissions by **action** rather than overly broad roles:

```text
batch.read
batch.launch
batch.stop
batch.restart
batch.manage-schedule
batch.manage-authorization
```

Permissions like `batch.launch` can be mapped from Identity Provider claims/scopes to authorities understood by Spring Security. Never trust a client-supplied JSON field like `"role": "admin"` as proof of authorization.

### Default principles

- **Deny by default:** any Job not on the allowlist cannot run through the control API.
- **Least privilege:** each service account gets only required permissions.
- **Separation of duties:** if sensitive Jobs require an approver distinct from the launcher, enforce that rule on the backend.
- **Object-level authorization:** always check permissions on the actual JobExecution, not merely generic `stop` permission.
- **Defense in depth:** enforce checks at the HTTP gateway/filter, method/service, and resource-policy layers.

## 5. Job launch paths that must be protected

A Spring Batch Job can be triggered from multiple places:

```text
REST API ------┐
Admin UI ------┤
@Scheduled ----┤
Message queue -┤----> BatchControlService ----> JobLauncher
CLI ----------─┤
Internal code -┘
```

If you only secure the REST controller, an internal method or another scheduler can still call `JobLauncher` directly. That is not inherently a bug if it is a trusted component, **but it must still have a matching policy and operational identity**.

Restrict access to dangerous APIs through a unified control service layer, for example:

```text
Authenticated HTTP request
        |
        v
  BatchController
        |
        v
  BatchControlService
        |
        v
  BatchAccessPolicy
        |
        +-- requireCanLaunch(actor, job, parameters)
        +-- requireCanStop(actor, storedExecution)
        |
        v
  JobLauncher / JobOperator
        |
        v
  JobRepository
```

This structure lets the same policy be shared when adding an admin UI, worker, or CLI. For internal schedules, use a **restricted scheduler identity** rather than "bypassing all authorization"; pre-approved schedules must be scoped to the exact Job, parameters, and environment.

## 6. Securing REST APIs with Spring Security

The following example uses **Spring Boot 3.x, Spring Security 6.x, and Spring Batch 5.x**. In Spring Batch 6.x, Job/JobExecution types change packages and JobOperator configuration may differ; the endpoint protection principles remain unchanged.

### 6.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Depending on the project, the Spring Boot BOM manages compatible starter versions. The example assumes the API receives a **Bearer JWT** from a trusted Identity Provider; the application must configure the appropriate issuer/JWK and validators.

### 6.2. Illustrative URLs

The API exposes only published Jobs:

```http
POST /api/batch/jobs/dailySettlementJob/executions
Content-Type: application/json
Authorization: Bearer <access-token>

{"businessDate":"2026-11-16"}
```

Stop execution request:

```http
POST /api/batch/executions/412/stop
Authorization: Bearer <access-token>
```

Use `POST` for both state-changing operations; never use `GET` to launch or stop a Job. Endpoints may also require an idempotency key and change reason per business rules.

### 6.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class BatchApiSecurityConfig {

    @Bean
    SecurityFilterChain batchApiFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/api/batch/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/batch/jobs/dailySettlementJob/executions"
                        ).hasAuthority("SCOPE_batch.launch")
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/batch/executions/*/stop"
                        ).hasAuthority("SCOPE_batch.stop")
                        .anyRequest().denyAll()
                )
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }
}
```

Key points:

1. `securityMatcher("/api/batch/**")` scopes this chain to Batch APIs; other app endpoints need their own chain or policy.
2. The launch endpoint requires authority `SCOPE_batch.launch`; stop requires `SCOPE_batch.stop`.
3. With default JWT resource server configuration, Spring Security maps scope values to `SCOPE_`-prefixed authorities. If your Identity Provider uses custom claims, configure a converter grounded in validated claims.
4. `anyRequest().denyAll()` blocks unpublished Batch control routes.
5. `@EnableMethodSecurity` enables `@PreAuthorize` at the service layer.
6. The example **disables CSRF** because the API assumes stateless Bearer token authentication without browser cookies/sessions as credentials. **Do not copy this config into session/cookie-based apps** without re-evaluating CSRF.

In production, validate issuer, signature, expiration, audience, and trust requirements properly. **Clients must never be able to forge valid scope claims** simply by editing a JWT; tokens must be issued and signed by a trusted authority.

### 6.4. Filters check functional permissions, not resource policies

If an account holds `SCOPE_batch.stop`, the URL rule above lets it reach the stop service. You must still verify that the execution ID actually belongs to a Job and tenant that account is authorized to operate.

`jobExecutionId` may be a sequential number; therefore an API relying solely on a coarse scope check is vulnerable to **Insecure Direct Object Reference (IDOR)**: changing `412` to `413` to stop another unit's execution.

## 7. Building a resource-level authorization layer

A policy can be defined as an interface to separate business rules from launch code:

```java
import java.time.LocalDate;

import org.springframework.batch.core.JobExecution;
import org.springframework.security.core.Authentication;

public interface BatchAccessPolicy {

    void requireCanLaunch(
            Authentication actor,
            String jobName,
            LocalDate businessDate);

    void requireCanStop(
            Authentication actor,
            JobExecution execution);
}
```

This interface is **application-defined**, not a built-in Spring Batch API. Implementations must consult trusted authorization data, such as a user–tenant–Job mapping table or an internal policy service.

An illustrative checklist table:

| Check | Launch | Stop |
| --- | --- | --- |
| Authenticated caller | Required | Required |
| Functional permission | `batch.launch` | `batch.stop` |
| Job allowlist | Job approved for launching | Job tied to execution is permitted to stop |
| Tenant/project scope | Scope to be processed | Scope stored on execution and trusted permission mapping |
| Environment | Permitted to launch in this environment | Permitted to stop in this environment |
| Window/reason | May require schedule or approval | May require incident ticket and reason |
| Status | Check data window, duplicates, and restart policy | Must check whether execution is actually running |

**Never authorize stop based solely on a client-supplied `tenantId`.** If a tenant parameter was attached by a trusted backend into JobParameters at launch, it can serve as supporting context; better still is a dedicated execution-authorization table or looking up permissions from an immutable owner/dataset.

Example of an application-managed table:

```sql
CREATE TABLE batch_execution_access (
    job_execution_id BIGINT PRIMARY KEY,
    tenant_id        VARCHAR(64) NOT NULL,
    project_id       VARCHAR(64) NOT NULL,
    submitted_by     VARCHAR(128) NOT NULL,
    classification   VARCHAR(32) NOT NULL,
    created_at       TIMESTAMP NOT NULL
);
```

This table is **application authorization metadata**, not a default Spring Batch table. Design mapping recording/recovery so an execution never loses authorization metadata due to a failure between creating JobExecution and saving the mapping. If creating the mapping and creating JobExecution cannot share one atomic transaction, include reconciliation, fail-closed denial when mapping is absent, and auditing.

### Do not rely on a generic role to unlock every Job

Even administrative permissions may be scoped by environment or data classification. A production operator authorized to manage catalog jobs should not automatically access jobs exporting personally identifiable customer data.

Policies must enforce permissions on the **actual target object**. For stop, load `JobExecution` first, then decide if that execution may be stopped. Never trust only a Job name passed in a client query parameter.

## 8. Job launch service with authorization checks

A clean approach is exposing only a specific operation `launchDailySettlement`, rather than letting clients pass arbitrary `jobName` values and parameter lists.

Spring Batch 5.x example:

```java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class BatchControlService {

    private final JobLauncher jobLauncher;
    private final JobOperator jobOperator;
    private final JobExplorer jobExplorer;
    private final Job settlementJob;
    private final BatchAccessPolicy accessPolicy;

    public BatchControlService(
            JobLauncher jobLauncher,
            JobOperator jobOperator,
            JobExplorer jobExplorer,
            @Qualifier("dailySettlementJob") Job settlementJob,
            BatchAccessPolicy accessPolicy) {

        this.jobLauncher = jobLauncher;
        this.jobOperator = jobOperator;
        this.jobExplorer = jobExplorer;
        this.settlementJob = settlementJob;
        this.accessPolicy = accessPolicy;
    }

    @PreAuthorize("hasAuthority('SCOPE_batch.launch')")
    public LaunchReceipt launchDailySettlement(
            LocalDate businessDate,
            Authentication actor) throws JobExecutionException {

        accessPolicy.requireCanLaunch(
                actor,
                settlementJob.getName(),
                businessDate);

        JobParameters parameters = new JobParametersBuilder()
                .addString(
                        "businessDate",
                        businessDate.toString(),
                        true)
                .addString(
                        "requestId",
                        UUID.randomUUID().toString(),
                        false)
                .toJobParameters();

        JobExecution execution =
                jobLauncher.run(settlementJob, parameters);

        return new LaunchReceipt(
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus().name());
    }

    @PreAuthorize("hasAuthority('SCOPE_batch.stop')")
    public StopReceipt requestStop(
            long executionId,
            Authentication actor) throws Exception {

        JobExecution execution =
                jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            // In a real API, use proper exception mapping
            // to avoid leaking whether another tenant's execution exists.
            throw new IllegalArgumentException(
                    "Execution not found or not accessible");
        }

        accessPolicy.requireCanStop(actor, execution);

        boolean requested = jobOperator.stop(executionId);

        return new StopReceipt(executionId, requested);
    }

    public record LaunchReceipt(
            Long jobInstanceId,
            Long jobExecutionId,
            String observedStatus) {
    }

    public record StopReceipt(
            long jobExecutionId,
            boolean stopRequested) {
    }
}
```

For brevity in the snippet, add the corresponding imports for `JobOperator` and `JobExplorer`:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.explore.JobExplorer;
```

**Conditions for this example:**

- The application context defines a `Job` bean named `dailySettlementJob`, plus `JobLauncher`, `JobOperator`, and `JobExplorer`.
- `BatchAccessPolicy` has an implementation enforcing tenant/Job/processing-date permissions from a trusted source.
- `@EnableMethodSecurity` is enabled, and calls into the service pass through the Spring Security proxy.
- `requestId` is server-generated and marked **non-identifying**. `businessDate` is identifying, so requests for the same date target the same `JobInstance` unless additional identifying parameters are configured.
- If a unit of work per **hourly window** is needed, use `windowStart` as an identifying parameter instead of `businessDate` alone.

Do not generate a random identifying `run.id` on every launch just to avoid duplicate errors when business rules actually permit only one JobInstance per day. Doing so can cause multiple executions to process the same data window twice.

### Why put `@PreAuthorize` on the service?

The controller is one entry point; the service may be invoked from other entry points. Protecting the service centralizes policy enforcement in a reusable boundary.

However, Spring method security uses proxies in many configurations. Calling **`this.launchDailySettlement(...)` from inside the same bean** bypasses the `@PreAuthorize` interceptor. Never create internal paths bypassing authorization. Have components call through a Spring-managed bean or a policy function enforced across every path.

### Launch errors are not always execution failures

`JobLauncher.run(...)` can throw:

- `JobExecutionAlreadyRunningException`: an execution of the same JobInstance is currently running.
- `JobInstanceAlreadyCompleteException`: that instance already completed.
- `JobRestartException`: restart is invalid.
- `JobParametersInvalidException`: parameters were rejected.

These errors typically happen **before a new JobExecution is successfully created**. The API must distinguish them from a Job that launched and ended with `BatchStatus.FAILED`.

## 9. REST controller rejecting arbitrary parameters

The controller accepts only approved business fields. For example, using `LocalDate` lets Spring/Jackson validate date syntax rather than accepting arbitrary file-path strings or query clauses.

```java
import java.time.LocalDate;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/batch")
public class BatchControlController {

    private final BatchControlService service;

    public BatchControlController(BatchControlService service) {
        this.service = service;
    }

    @PostMapping(
            "/jobs/dailySettlementJob/executions"
    )
    public ResponseEntity<BatchControlService.LaunchReceipt> launch(
            @Valid @RequestBody LaunchRequest request,
            Authentication actor) throws Exception {

        var result = service.launchDailySettlement(
                request.businessDate(), actor);

        return ResponseEntity.accepted().body(result);
    }

    @PostMapping("/executions/{executionId}/stop")
    public ResponseEntity<BatchControlService.StopReceipt> stop(
            @PathVariable long executionId,
            Authentication actor) throws Exception {

        var result = service.requestStop(executionId, actor);
        return ResponseEntity.accepted().body(result);
    }

    public record LaunchRequest(
            @NotNull LocalDate businessDate) {
    }
}
```

HTTP `202 Accepted` here indicates the control request was accepted; **it does not imply the Job has completed or stopped**. Depending on your API contract, synchronous runs may return HTTP `200 OK` when reporting immediate completion, while still stating the observed status clearly.

A complete API should also expose a **status read** endpoint protected with `batch.read` scoped per execution, for example:

```http
GET /api/batch/executions/412
```

Clients poll that endpoint or subscribe to secured events/notifications to observe final outcomes. Never use HTTP `202` as proof of business success.

### Never accept these parameters arbitrarily

Avoid APIs letting clients send directly:

```json
{
  "jobName": "anyJobFromContext",
  "parameters": {
    "inputFile": "../../private/export.csv",
    "sql": "DELETE FROM ...",
    "outputBucket": "unapproved-bucket",
    "tenantId": "other-tenant"
  }
}
```

These values illustrate **untrusted inputs**. A safer design defines an explicit contract per Job:

- `businessDate`: standard date, validated against permitted date bounds.
- `tenantId`: derived from the authenticated identity or trusted authorization mapping, never blindly trusting client input.
- `inputDatasetId`: resolved against registered backend datasets/paths.
- `outputLocation`: chosen from approved destinations, never an arbitrary path.
- `runMode`: backend-controlled enum.
- `requestId`: server-generated or validated/idempotent per rules.

**Parameter validation and parameter authorization are distinct.** A syntactically valid `businessDate` can still fall outside the date range an operator is permitted to process.

## 10. Stopping a Job is a cooperative stop request

A common misconception: calling `JobOperator.stop(executionId)` **is not equivalent to killing a thread, killing an OS process, or rolling back already committed data**.

In Spring Batch, stop is designed to signal a running Job to transition toward stopping and terminate cleanly at appropriate execution points.

```text
JobExecution #412
     |
     v
  STARTED
     |
     | operator: stop(412)
     v
  STOPPING
     |
     | Step observes stop signal and exits at an appropriate point
     v
  STOPPED
```

This is the typical flow, not a guarantee that every Job stops immediately. A Step blocked on long I/O, a tasklet not checking the stop signal, or a stalled integration can take considerable time. A Job might also finish before the stop command is processed; terminal statuses can vary depending on races and runtime errors.

### How to return the stop response

`JobOperator.stop(long executionId)` in Spring Batch 5.x returns a boolean indicating whether the stop request was accepted per the API contract; that value **does not prove the Job has reached `STOPPED`**.

A sensible API response:

```json
{
  "jobExecutionId": 412,
  "stopRequested": true
}
```

Clients then inspect actual status via `JobExplorer` or a secured read endpoint, waiting with a timeout for `STOPPED`/terminal status. Never return "Fully stopped" immediately when `stop(...)` returns.

### Do not use stop to hide failures or rewrite history

- Stopping does not delete `JobExecution` or `StepExecution` history.
- Chunks committed before stopping are not automatically rolled back.
- If the Job performed non-transactional side effects, stopping does not undo already-sent emails/APIs/messages.
- Restarting after stop depends on restartability configuration, Step/Job state, and business idempotency.
- If killing an OS process at the infrastructure layer is needed, that is a **different** permission from Job stop and requires its own safety procedure.

Stopping a settlement Job may require an approver or incident ticket because it affects SLAs and processing progress. Policies can mandate a stop reason, restrict stop windows, and require backend confirmation.

## 11. Preventing IDOR when stopping by execution ID

An insecure API:

```java
@PostMapping("/executions/{id}/stop")
public void stop(@PathVariable long id) throws Exception {
    jobOperator.stop(id);
}
```

Even when the endpoint requires login, a caller can change the ID to affect a JobExecution outside their authorized scope.

Correct handling:

1. Authenticate the caller and resolve granted permissions.
2. Load `JobExecution` from `JobExplorer` by ID.
3. Determine JobName, environment, tenant/project, and data classification from a trusted source.
4. Verify the caller holds `batch.stop` **and** permission on that specific execution.
5. Check operational conditions such as status and approval policies.
6. Call `JobOperator.stop(executionId)`; audit both the request and outcome.
7. Observe the subsequent terminal status; do not infer it from the HTTP response.

Two subtle points:

**First, avoid disclosing whether another tenant's execution exists.** Depending on your API contract, return a uniform message like "not found or not accessible" to prevent ID probing. Standardize `403`/`404` usage and avoid leaking information via response timing.

**Second, status can change between check and stop invocation.** The Job may transition from `STARTED` to `COMPLETED`. That is a lifecycle race; the service must handle `JobOperator` results/exceptions and report the observed status rather than assuming every stop succeeds based on a prior snapshot.

## 12. Checking status and stop eligibility

`JobExplorer` provides execution lookup:

```java
JobExecution execution =
        jobExplorer.getJobExecution(executionId);

if (execution == null) {
    // Does not exist in the queried repository.
} else {
    var status = execution.getStatus();
    var name = execution.getJobInstance().getJobName();

    // Use this information to support policy and UI state.
}
```

Common statuses:

| `BatchStatus` | Meaning | Suggested stop handling |
| --- | --- | --- |
| `STARTING` | Job is starting. | Check whether your version/operator accepts stop and whether policy allows it. |
| `STARTED` | Job is running. | Stop may be requested if the actor is authorized. |
| `STOPPING` | Stop is in progress. | Return "stop already requested"; avoid spamming commands. |
| `STOPPED` | Job has stopped. | No need to issue another identical stop command. |
| `COMPLETED` | Job finished. | No longer a running execution to stop. |
| `FAILED` | Job failed. | Do not use stop to alter failure history; inspect restart policy instead. |
| `ABANDONED` | Execution marked unusable for restart per rules. | Not treated as a running execution. |

Policy classification should account for all statuses. Checking only `status == STARTED` may miss transitional states; for API accuracy, follow `JobOperator`'s contract and actual metadata status rather than mutating statuses manually.

In particular, **never run raw SQL to update `BATCH_JOB_EXECUTION.STATUS`** to "stop" a Job. Doing so alters metadata only without notifying workers, causing divergence between actual execution and restartability.

## 13. Launch permissions must bind to JobParameters and business rules

Being allowed to launch `dailySettlementJob` does not mean permission to process **any date, any tenant, or any operational mode**.

Policy example:

```text
Actor: operator-27
Permission: batch.launch
Job allowed: dailySettlementJob
Tenant allowed: tenant-A
Business date allowed: <= current business date
Environment allowed: staging
Approval required in production: yes
```

This policy is illustrative. In code:

- Use an allowlist of published Job names; never expose the entire `ApplicationContext`/`JobRegistry` to public APIs.
- Validate dates/windows are within permitted bounds.
- Bind tenant from the authenticated identity or trusted mapping.
- Allow only approved modes, inputs/outputs, and resources.
- Enforce rate limits, concurrent Job limits, and SLA windows.
- Capture request ID/idempotency keys to distinguish HTTP retries from fresh requests.

### Identifying parameters and duplicate runs

In Spring Batch, **Job name + identifying JobParameters** define a `JobInstance`. If a JobInstance has already completed, attempting to rerun with identical parameters is normally rejected with `JobInstanceAlreadyCompleteException`. If already running, a request for the same instance may be rejected with `JobExecutionAlreadyRunningException`.

However, this **is not an authorization mechanism**. A caller with overly broad launch rights can alter an identifying parameter to spawn a new instance. Launch policies must still restrict which parameter sets are allowed.

When preventing overlap among **different instances** touching the same resource, add coordination/distributed locks or business-level queues. `JobRepository` does not automatically block concurrent executions of the same Job name when identifying parameters differ.

### API idempotency

A client may retry the same HTTP request after a network timeout. If the first attempt already created a JobExecution, the second attempt should not inadvertently create a separate job just because a random `requestId` was treated as identifying.

A solid design persists validated `idempotencyKey` mappings from requests to JobExecutions. Retries with the same key and identical payload return the known result (or in-progress status) without uncontrolled relaunches. If the key matches with a different payload, return a conflict per the API contract.

`JobInstance` identity and HTTP idempotency complement each other; neither replaces protecting business side effects.

## 14. Auditing every launch and stop request

You must be able to answer:

**Who** requested, **when**, **from where**, **on which Job/Execution**, **with which allowed parameters**, **why**, **what the authorization decision was**, and **how the Job ultimately ended**.

An illustrative audit record:

```json
{
  "eventId": "evt-000182",
  "timestamp": "2026-11-16T03:15:00Z",
  "actorId": "operator-27",
  "actorType": "HUMAN",
  "action": "BATCH_STOP",
  "resource": {
    "jobName": "dailySettlementJob",
    "jobExecutionId": 412
  },
  "decision": "ALLOW",
  "requestAccepted": true,
  "reasonCode": "INCIDENT_RESPONSE",
  "incidentTicket": "INC-0123",
  "requestId": "rq-0091"
}
```

This is an **application-defined** audit format, not a built-in Spring Batch schema.

Distinguish events:

- `batch.launch.requested`: launch request reached the system.
- `batch.launch.denied`: caller lacked permission or violated policy.
- `batch.launch.accepted`: Batch created/accepted the JobExecution.
- `batch.launch.rejected`: rejected due to lifecycle state, parameters, or launch failure.
- `batch.stop.requested`: stop request arrived.
- `batch.stop.denied`: invalid stop permission.
- `batch.stop.accepted`: stop request accepted.
- `batch.job.finished`: JobExecution reached terminal outcome and persisted metadata.

**Auditing an accepted stop command is not the same as auditing that the Job stopped successfully.** Final outcomes must be reconciled against `JobRepository`/`JobExplorer` and StepExecutions.

### Auditing denied requests

If `@PreAuthorize` blocks at the Spring Security proxy, the service body never runs. Therefore, **putting audit logging only on the first line of the service will not capture DENY events**.

Add auditing at the authorization boundary, such as `AccessDeniedHandler`, authorization event listeners, request filters, or the policy service. Denial audits log only safe attributes—never raw Bearer tokens, JSON payloads containing secrets, or sensitive exception stack traces.

### Audit durability

If compliance requires persisting every control attempt, INFO logger lines alone may be insufficient. Consider a durable audit table/outbox, retention policies, and access controls. If auditing must be atomic with creating a control command, design transactional boundaries and handle database/audit-sink failures; calling JobLauncher and writing audit in two independent transactions **does not inherently guarantee exactly-once**.

## 15. Schedulers and service accounts

`@Scheduled` has no logged-in HTTP user at callback time. If a scheduler method invokes a `@PreAuthorize`-protected service relying on `SecurityContextHolder`, authentication may be absent. Do not solve this by disabling security or granting admin privileges to every scheduled task.

A clean design:

```text
Trusted Scheduler Identity
  subject = scheduler:settlement
  allowed jobs = [dailySettlementJob]
  allowed action = LAUNCH
  allowed schedule = 02:00 UTC daily
        |
        v
Batch Orchestration
        |
        v
Launch policy (server-side allowlist)
        |
        v
JobLauncher
```

Technical options:

- Use workload identity/short-lived tokens when an external scheduler calls a secured internal API.
- Provision a dedicated service principal for schedules, permitted to launch **only its assigned Jobs**.
- If running schedules in-process, use a dedicated internal entry point with a policy validating schedule definitions and trusted task identities, auditing under the service account.
- Do not grant stop permissions to schedulers unless genuinely required.

With multiple nodes, **authorization does not prevent duplicate scheduled runs**. Add coordination and duplicate-handling rules suited to the Job's semantics.

### Authorizing CLIs and admin tools

CLI tools or Spring Shell can invoke `JobOperator` directly. When CLIs are reserved for sensitive operations, restrict who can run the process/commands, how tokens/identities are issued, environments, and auditing—preventing internal command lines from becoming a bypass around HTTP policies.

## 16. HTTP error handling and safe responses

APIs must align **authentication/authorization** with **Batch state**.

| Scenario | Suggested HTTP status | Meaning |
| --- | --- | --- |
| Missing or invalid token | `401 Unauthorized` | Caller could not be authenticated. |
| Authenticated but missing scope/policy | `403 Forbidden` | Caller lacks permission for the operation. |
| Resource absent or disallowed to disclose | `404 Not Found` or uniform masked response per policy | Prevents enumerating out-of-scope IDs. |
| Invalid body/parameters | `400 Bad Request` | Format or business validation error. |
| JobInstance already completed/running | `409 Conflict` per API contract | Lifecycle conflict or request no longer valid. |
| Launch/stop accepted, final outcome pending | `202 Accepted` | Caller must continue tracking JobExecution. |
| Infrastructure temporarily unable to accept | `503 Service Unavailable` or matching error | Do not pretend the Job was launched. |

These are **contract design suggestions**; Spring Batch does not automatically map exceptions to these HTTP codes. The application needs consistent `@ControllerAdvice` or exception handlers.

Distinguish:

- **403**: actor lacks permission on the action/resource.
- **409**: actor is authorized, but Job state disallows the request.
- **JobExecution FAILED**: Job ran and failed business processing, not an authorization error.

Never include full stack traces, tokens, passwords, datasource configs, or sensitive resource names in client responses.

## 17. Additional defense layers

### 17.1. Rate limits and concurrent Job caps

An actor holding `batch.launch` could still submit thousands of requests. Cap:

- Request rate per actor/tenant.
- Concurrent JobExecutions per Job or environment.
- Queued pending requests.
- Request payload size.
- Permitted execution windows and relaunch rights.

Rate limiting does not replace authorization, yet limits abuse of granted privileges and protects against overload.

### 17.2. Preventing untrusted paths and data injection

If a Job accepts `inputFile`, `outputPath`, or `bucket` via API, checking "non-empty" is not enough. Validate permitted resource scope, path traversal, forbidden absolute paths, symlinks, storage namespaces, and runtime read/write permissions.

For JobParameters used in SQL, always use prepared statements/parameter binding; never concatenate SQL strings. Never let a request `jobName` look up arbitrary beans in the application context to launch them.

### 17.3. Separating API permissions from Job runtime permissions

Users are authorized only to **request execution**; when running, the Job may use dedicated database accounts, object storage credentials, or technical service accounts. Never grant users DB rights or secrets just because they can launch a Job.

Ensure each Job's runtime credentials are least-privilege. For sensitive export Jobs, launch permission must align with **output** access rights; never let a user with launch-only rights receive an export file they are not cleared to view.

### 17.4. Environment and tenant isolation

Staging and production should maintain separate identities, permission scopes, JobRepositories, lock providers, audits, and data. Staging tokens must never be accepted in production unless explicitly permitted by issuer/audience/policy.

In multi-tenant applications, verify tenant ownership against the real object and authorization store—never put `tenantId` in a URL and assume the caller can pick any tenant.

### 17.5. Keeping secrets out of metadata and logs

`JobParameters` and `ExecutionContext` can be persisted into the metadata database. Never put access tokens, passwords, API keys, or raw PII into Job parameters or audit logs. Use references to a secret manager or secured storage keys with separate authorization when needed.

## 18. Testing launch/stop authorization

Security tests must verify both **access denial** and **that the Job itself remained untouched**. Simply asserting HTTP `403` is insufficient if a controller inadvertently launched the Job before a filter returned an error.

### 18.1. Test case matrix

| Test | Condition | Expected outcome |
| --- | --- | --- |
| Unauthenticated launch call | No token | `401`, no JobExecution created. |
| Read permission without launch | Token lacks `batch.launch` | `403`, no launch. |
| Has `batch.launch` but disallowed for this Job | Allowlist policy rejects | `403`, no launch. |
| Valid permission and parameters | Both scope and resource policy allow | JobExecution created/accepted. |
| Out-of-bounds date parameter | Valid scope but violates business policy | `403` or consistent policy error. |
| User with `batch.stop` stops another tenant's execution | Object-level policy rejects | `JobOperator.stop(...)` not called. |
| Authorized stop on running execution | Valid permissions | Stop request accepted; subsequently verify terminal state. |
| Stop already-completed execution | Actor authorized but state disallows | Conflict/appropriate status, not false stop success. |
| Retry identical launch request | Same idempotency key | Does not create extra JobInstance outside contract. |
| Scheduler identity | Authorized only for assigned Job | Launches assigned Job, rejects others. |

### 18.2. MockMvc with mock JWTs

With `spring-security-test`, test filters and controllers. Example:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BatchApiAuthorizationIT {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void noTokenCannotLaunch() throws Exception {
        mockMvc.perform(
                post("/api/batch/jobs/dailySettlementJob/executions")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"businessDate\":\"2026-11-16\"}")
        ).andExpect(status().isUnauthorized());
    }

    @Test
    void readOnlyScopeCannotLaunch() throws Exception {
        mockMvc.perform(
                post("/api/batch/jobs/dailySettlementJob/executions")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority(
                                    "SCOPE_batch.read")))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"businessDate\":\"2026-11-16\"}")
        ).andExpect(status().isForbidden());
    }
}
```

This test covers the **HTTP layer** and does not replace dedicated tests for `BatchAccessPolicy`. Configure a context containing the security chain and required beans. With mocked JWTs, tests do not verify real identity provider signatures/issuers; add separate tests for token validation configuration.

### 18.3. Testing method security

With `@EnableMethodSecurity`, verify that invoking the service via the Spring bean under an under-privileged Authentication is rejected. `@WithMockUser(authorities = "SCOPE_batch.read")` works well in method-security integration tests.

Crucial detail: **do not instantiate the service via `new BatchControlService(...)` and expect `@PreAuthorize` to fire**. Method security relies on Spring proxies. Direct instantiation suits unit-testing internal logic, while authorization tests must invoke the Spring-managed proxy.

### 18.4. Testing object-level authorization

Create two `JobExecution`s belonging to different tenants/scopes in a test repository:

1. Actor A holds `batch.stop` but manages only tenant A.
2. Actor A requests stopping tenant B's execution.
3. Policy must reject.
4. Verify `JobOperator.stop(...)` **was never called** and tenant B's execution metadata remained untouched.
5. Repeat with tenant A's execution in an eligible state, verifying stop is dispatched.

When mocking `JobOperator`, assert zero invocations. When testing with a real Job, use a Tasklet with a latch/timeout to hold the Job running long enough to observe the stop. Avoid fixed `Thread.sleep` calls that make tests flaky.

### 18.5. Testing the stop lifecycle with a real Job

Scenario:

```text
Arrange:
  JobExecution A starts, Step running with checkpoint/stop point
  Actor authorized to stop A

Act:
  POST /api/batch/executions/{A}/stop

Assert:
  API does not claim Job is already STOPPED immediately
  Metadata may transition through STOPPING
  Worker exits cleanly
  JobExecution reaches expected terminal state
  Audit records actor/action/executionId
```

A Tasklet that ignores stop signals may not respond like a chunk-oriented Step; design fixtures to test the exact stop contract of the Step type in use. Enforce test timeouts and clean up workers afterward.

### 18.6. Testing after a Job is restarted

Under the same `JobInstance`, a restart creates a new `JobExecution`. Stop authorization must check the **current execution ID**, not mistakenly use an old `FAILED` or `STOPPED` ID. Do not wipe metadata between failure and restart in tests; repository data is needed for both restart and authorization checks.

## 19. Operational conditions and approvals

High-impact Jobs—such as payouts, ledger closing, data exports, or bulk syncs—may need operational gates beyond scopes and resource permissions:

- Require reason codes on stop, e.g., `INCIDENT_RESPONSE`, `WRONG_INPUT`, `MAINTENANCE`.
- Record incident/change tickets, requester, and approver.
- Restrict launches during closing windows or peak trading hours.
- Enforce two-person approval for sensitive Jobs, separating "request" and "approve" permissions.
- Support a `PENDING_APPROVAL` state on the **control command** before creating any JobExecution; launch only upon approval.
- Notify Job owners when stop is accepted and when the Job actually halts.

Separating **authorized to issue command** from **command executed** is vital for auditing. A completed approval record does not mean the Job ran; a Job is launched only when the backend creates/accepts a JobExecution.

## 20. Common authorization mistakes

### Using only `@PreAuthorize("isAuthenticated()")`

Any signed-in user can launch/stop. Enforce action, resource, and business-scope authorization.

### Using `hasRole("ADMIN")` for every Job

Overly broad and cannot distinguish view, launch, stop, and restart. Use explicit permissions and Job/tenant/environment policies.

### Letting clients pass arbitrary `jobName`

A generic control endpoint could trigger unintended Jobs. Use an allowlist mapping public API names to approved Job beans.

### Securing only the controller

CLIs, schedulers, or internal services may invoke launchers directly. Unify entry points and prevent untrusted code from bypassing the policy layer.

### Checking only the `batch.stop` scope

Failing to verify which tenant/project an execution belongs to creates IDOR vulnerabilities. Always load the execution and enforce object-level permissions.

### Trusting client-sent `tenantId`

Callers can forge tenant IDs. Derive tenant scope from authenticated identity or backend authorization mappings.

### Assuming `stop(id)` returning means the Job finished stopping

Stop is typically a cooperative stop request. Observe terminal status and handle timeouts/races.

### Not checking whether an execution already completed

A stop request may arrive right as the Job finishes; avoid misleading responses. Distinguish "no longer running" from "stop accepted."

### Allowing arbitrary JobParameters changes to rerun

New identifying parameters create a distinct JobInstance and reprocess data. Define work units, idempotency, and parameter permissions clearly.

### Auditing only successful operations

Denied requests also require a trail; if `@PreAuthorize` blocks before entering the service, audit at the authorization/filter boundary.

### Running Jobs under over-privileged runtime accounts

Someone cleared to launch a Job should not gain ability through that Job to read/write every database or export arbitrary data. Scope runtime credentials and destinations tightly.

### Logging tokens or sensitive data

Never persist raw Bearer tokens, passwords, or full secret-bearing JobParameters. Audits should record IDs, actions, decisions, and safely classified parameters.

## 21. Hands-on exercises

Suppose a system has two Jobs:

- `importCatalogJob` imports daily catalog data for one tenant.
- `dailySettlementJob` performs end-of-day financial settlement.

The system has three user groups: viewer, catalog operator, and settlement operator. A scheduler service account is authorized to auto-launch `importCatalogJob` on schedule.

### Part A – Policy design

1. Define `batch.read`, `batch.launch`, `batch.stop`, and `batch.restart` permissions.
2. Build a permission matrix for each group and the scheduler.
3. Specify Job/tenant/environment scopes for each permission.
4. Require a reason or approval before stopping `dailySettlementJob`.
5. Define identifying JobParameters so a single business date cannot accidentally spawn multiple instances.

### Part B – Securing the API

1. Set up a Bearer-token resource server for `/api/batch/**`.
2. Use `SecurityFilterChain` to guard launch/stop endpoints.
3. Use `@EnableMethodSecurity` and `@PreAuthorize` on the service.
4. Use `BatchAccessPolicy` to enforce resource-level permissions.
5. Allow only registered Jobs; never let clients pick arbitrary file paths, tenants, or arbitrary parameters.
6. Return `202` with execution ID/stop request state, plus an authorized status read endpoint.

### Part C – Positive and negative testing

1. No token → `401` and no execution created.
2. Viewer launches Job → `403`.
3. Catalog operator launches `importCatalogJob` in assigned tenant → allowed.
4. Catalog operator launches `dailySettlementJob` → denied.
5. Settlement operator stops another tenant's execution → denied, `JobOperator.stop` not called.
6. Settlement operator stops an assigned tenant's running execution → request accepted.
7. Poll `JobExplorer` to terminal state without confusing `STOPPING` with `STOPPED`.
8. Two launch requests for the same business date → do not create two unwanted units of work.
9. Test CLI/scheduler paths and confirm matching policies apply.
10. Verify audits for `ALLOW`, `DENY`, and post-operation Batch outcomes.

### Part D – Incident scenario

Have `dailySettlementJob` run a Step writing 10,000 records in chunks. After several chunks commit, an authorized actor sends a stop request.

Verify:

- Authorization is checked before calling `JobOperator`.
- The Job stops cleanly, while already committed chunks remain intact.
- Audit clearly records actor, JobExecution ID, timestamp, and stop reason.
- If business rules require a restart, metadata and business data remain eligible to resume without duplicate writes.
- If a second actor concurrently sends a duplicate stop, the system does not return two misleading "stopped" confirmations.

Through this exercise, the key takeaway is that **Job control permissions must bind to actions, real resources, business context, and execution state**, rather than merely whether a user is logged in.

## References

- [Spring Batch Reference – Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): JobLauncher, JobParameters, JobInstance, and JobExecution.
- [Spring Batch Reference – JobOperator](https://docs.spring.io/spring-batch/reference/job/configuring-operator.html): Job operational actions including version-specific stop/restart.
- [Spring Batch Reference – Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): Job/Step states and metadata.
- [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): storage for executions and restart state.
- [Spring Security Reference – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
- [Spring Security Reference – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html): securing requests and resources.
- [Spring Security Reference – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): Bearer JWT validation and authority mapping.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and object-level authorization.

