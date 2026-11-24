# Permission to Call the Job Launcher

`JobLauncher` is the API used to ask Spring Batch to run a job with a set of `JobParameters`. `JobLauncher` itself does not authenticate the caller and does not decide whether that person has permission to run the job. The application must place access control at the API or service layer before calling the launcher.

This matters because a job can read, modify, or export data with a wider scope than a user's ordinary permissions. A person who is allowed to log in to the application is not implicitly allowed to launch every job, pass every parameter, or operate on the data of every tenant.

## 1. Distinguishing authentication and authorization

There are two separate security decisions:

- **Authentication:** determines who is making the request. For example, a user logged in through a session, an OAuth2 access token, or a service account.
- **Authorization:** decides which actions that identity is allowed to perform on which jobs and data. For example, only a person with the authority `BATCH_JOB_LAUNCH_IMPORT` may run the order import job.

The job-calling flow should look like:

```text
User / scheduler / service
             |
             v
      Authentication
             |
             v
     API or launch service
             |
             v
        Authorization
             |
      +------+-------+
      |              |
   Allowed         Denied
      |              |
      v              v
  JobLauncher    403 / access denied
      |
      v
  JobRepository and JobExecution
```

Spring Batch manages the execution lifecycle, metadata, status, and restart. The policy on who is allowed to request execution is the application's security responsibility.

## 2. JobLauncher does not check permissions itself

The launcher's basic API takes a `Job` together with `JobParameters`:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

This call asks Spring Batch to launch the job. `JobLauncher` does not ask whether the caller has the corresponding role, authority, tenant, or data access rights. If a public controller calls the launcher directly without an access-control layer, any caller who gets past that HTTP layer can request a job run.

`JobRepository` has checks on execution state and identity, such as rejecting a JobInstance that is running or has completed with the same identifying parameters. These checks serve correctness and batch coordination; they are not authorization. A person without permission can still get past the state checks if the application does not block the request beforehand.

Similarly, `JobOperator` provides management operations such as start, restart, stop, and abandon, but those methods also do not replace the application's authorization policy.

## 3. Protecting the call point with Spring Security

In a Spring application, you can use Spring Security to protect the HTTP endpoints and the service that launches jobs. An easy-to-maintain approach is to put the permission rules on a dedicated service, so that every call path from a controller or other component goes through the same policy.

Enable method security:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
}
```

Then require a specific authority on the service:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;
    private final TenantAuthorization tenantAuthorization;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob,
            TenantAuthorization tenantAuthorization) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
        this.tenantAuthorization = tenantAuthorization;
    }

    @PreAuthorize("hasAuthority('BATCH_JOB_LAUNCH_IMPORT')")
    public JobExecution launchImport(
            LocalDate businessDate, String tenantId) throws JobExecutionException {

        Authentication caller = SecurityContextHolder.getContext().getAuthentication();
        tenantAuthorization.assertCanLaunchFor(caller, tenantId);

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("tenantId", tenantId, true)
            .addString("requestedBy", caller.getName(), false)
            .toJobParameters();

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

In this example:

- `@PreAuthorize` requires the caller to have the authority `BATCH_JOB_LAUNCH_IMPORT` before the method is executed.
- `TenantAuthorization` checks whether the caller has permission to run for the requested tenant.
- The job and the parameter set are chosen in the service; the caller cannot arbitrarily specify a different Job bean.
- `requestedBy` stores the requester's identity for audit purposes. This is a non-identifying parameter because the requester does not identify the business unit of work.
- `businessDate` and `tenantId` are identifying parameters in the example because they identify the data set to be processed.

`@EnableMethodSecurity` needs to be enabled for annotations such as `@PreAuthorize` to take effect. The method needs to be called through the Spring proxy; an internal call from one method to another in the same object (self-invocation) can bypass the security interceptor. Therefore, place the control point on a service bean that is called from another bean, or add protection at the calling layer.

An authority is a string agreed upon by the application and the identity provider. You can use a role such as `ROLE_BATCH_OPERATOR`, but for different batch actions, specific authorities usually give more precise authorization.

## 4. Don't expose an endpoint that runs any job arbitrarily

A risky design is to create a generic endpoint that receives a job name and maps parameters from the request and passes them straight to the launcher:

```java
// Don't use a generic endpoint without control like this
@PostMapping("/api/batch/run")
public JobExecution run(
        @RequestParam String jobName,
        @RequestBody Map<String, String> parameters) {
    Job job = jobRegistry.getJob(jobName);
    return jobLauncher.run(job, toJobParameters(parameters));
}
```

A caller can try internal job names, send unexpected parameters, or trigger a processing flow that has higher data access rights than their own. Checking login at the endpoint is still not enough.

You should provide business-oriented endpoints, such as `POST /api/batch/imports`, and let the service choose the specific job. For each job type, clearly define:

- Which authority is allowed to launch it.
- Which parameters are accepted and their data types.
- Which tenants, accounts, business dates, or data scopes the caller is allowed to process.
- Limits on frequency, volume, and the number of concurrent executions.
- What results are returned to the caller and what information is for operations only.

An example controller that receives a request DTO with a fixed structure:

```java
public record ImportRequest(
        @NotNull LocalDate businessDate,
        @NotBlank String tenantId) {
}

@RestController
@RequestMapping("/api/batch/imports")
public class ImportController {

    private final BatchLaunchService launchService;

    @PostMapping
    public ResponseEntity<LaunchResponse> launch(
            @Valid @RequestBody ImportRequest request) throws JobExecutionException {

        JobExecution execution = launchService.launchImport(
            request.businessDate(), request.tenantId());

        return ResponseEntity.accepted().body(
            new LaunchResponse(execution.getId(), execution.getStatus().name()));
    }
}
```

The example illustrates how to separate the request from the service; the `SecurityFilterChain` part still needs to protect the endpoint by an appropriate authority or policy. The service also checks tenant permission itself so another call path cannot accidentally skip the data-scope check.

## 5. Authorizing each action

You should not lump every batch operation into a single `BATCH_ADMIN` permission. A person may be allowed to launch a business job but not to stop or abandon other people's executions.

| Action | Suggested authority | Purpose |
|---|---|---|
| Launch the data import job | `BATCH_JOB_LAUNCH_IMPORT` | Request a run of a specific job type |
| Launch reconciliation | `BATCH_JOB_LAUNCH_RECONCILIATION` | Run a reconciliation job with its own scope |
| View execution status | `BATCH_JOB_READ` | Read the status and the information permitted to be displayed |
| View error details | `BATCH_JOB_READ_DETAILS` | Access stack traces or sensitive operational information |
| Restart an execution | `BATCH_JOB_RESTART` | Request to continue a failed/stopped execution |
| Stop an execution | `BATCH_JOB_STOP` | Request to stop a running execution |
| Abandon an execution | `BATCH_JOB_ABANDON` | Mark an execution as not to be continued, per the operational procedure |
| Administer batch configuration | `BATCH_ADMIN` | Change configuration or administrative policy |

The authorities above are examples defined by the application itself, not a list of permissions that Spring Batch creates. Assign permissions according to actual responsibilities and apply the principle of least privilege: each account has only the permissions needed for its work.

For restart, stop, or abandon operations, you should also check the execution state and the resource scope that the caller manages. For example, the `BATCH_JOB_STOP` permission does not necessarily allow stopping every job in the system.

## 6. Controlling JobParameters and data scope

JobParameters can decide which data the job processes. Therefore, authorization must consider both the launch action and the parameter values.

For example, a user has permission to run the data import job but is only allowed to process tenant `tenant-42`. If the request sends `tenantId=tenant-99`, the service must reject it before calling `JobLauncher`, even though the caller has the authority to launch the job.

Rules to apply:

1. **Allow-list parameters.** Accept only the parameters designed for the job; reject unknown keys or wrong data types.
2. **Validate values.** Check the business date, batch code, file name, time-range limits, and business constraints.
3. **Check permissions per resource.** Compare the tenant, account, region, or business unit in the request against the scope the caller is allowed.
4. **Don't trust authorization data from the request.** If the tenant or user scope can be derived from the token/session, take it from the authenticated identity or cross-check against a server-side authorization service.
5. **Don't put secrets in JobParameters.** Parameters can be stored in metadata and appear in logs or administration tools; do not pass passwords, access tokens, private keys, or credentials.
6. **Choose the identifying flag according to the business.** A parameter that changes the unit of work must take part in identification; audit information such as the requester usually should not create a new JobInstance.

You should not use a `tenantId` parameter declared by the caller as proof that the caller is permitted to access that tenant. A parameter describes the scope of the work; the authorization service is what decides whether the caller has rights to that scope.

## 7. Requester identity and execution identity

A job can be requested by a user but executed on a background thread or by a worker process. You need to distinguish:

- **Requester:** the user or system that requested the launch.
- **Execution identity:** the service account or process that actually runs the job and accesses resources.
- **Business scope:** the tenant, customer, data period, or set of records that the job is permitted to process.

For auditing, you should store the requester, request time, calling source, job name, non-sensitive parameters, execution ID, result, and the reason for launching. You can write to a separate audit table or store an appropriate field in JobParameters/metadata. If you store `requestedBy` in JobParameters, consider that this data is kept in the repository and can be seen by people who have permission to read the metadata.

You should not depend entirely on `SecurityContextHolder` inside a step to determine the requester. With an asynchronous launcher, the step may run on another thread. The Spring Security context is usually tied to a thread; it is not automatically passed to every executor.

If a step truly needs the SecurityContext, configure an explicit context-propagation mechanism, for example `DelegatingSecurityContextTaskExecutor` or an appropriate `TaskDecorator`. It is usually better to explicitly write the requester into the audit metadata before the execution starts, and then let the job use the stored audit data. Do not pass web request objects or access tokens into a background job.

## 8. Jobs called by a scheduler or service account

Not every job is launched by a logged-in user. A scheduler, message consumer, or another orchestration system can call the launch service.

In this case, determine a separate system identity, for example `service:nightly-import`, and grant exactly the authority for that job. The audit needs to distinguish automatic executions from user-created requests.

If the service uses method security, a call from a scheduler may have no authentication in `SecurityContextHolder` and be rejected. This is a behavior to anticipate. Set up a service principal or an internal entry point with a clear policy, instead of removing all security checks just so the scheduler can run.

You should not give the scheduler account administrative rights over all of batch if it only needs to run one job on a schedule. You also need to protect internal endpoints, message channels, or scheduler triggers so outsiders cannot forge automated requests.

## 9. Protecting endpoints and execution information

When a job is launched over HTTP, apply security policies appropriate to the client type:

- For web applications using session/cookies, protect state-changing requests with a CSRF token and appropriate session rules.
- For APIs using OAuth2/JWT, validate the issuer, audience, signature, token expiry, and the mapped authority/scope.
- Use HTTPS to protect tokens and data transmitted over the network.
- Limit the rate and number of launch requests to prevent a caller from creating too many executions or exhausting resources.
- Record audits for rejected requests and accepted requests according to the system's logging policy.
- Do not return stack traces, SQL, connection information, or the entire ExecutionContext to callers who lack permission to read details.

Viewing job status is also a separate permission. Information such as file names, tenants, record counts, exception messages, and business parameters can reveal internal data. Filter the response by authority and resource scope, similar to launch time.

## 10. Permission to call a job and handling duplicate run requests

Authorization answers the question of whether the caller is allowed to request a job run. After the caller is permitted, Spring Batch also applies the rules about JobInstance and execution state.

For example, two requests to run `importOrders` with the same identifying parameters can lead to an instance already-completed or already-running error. This is a JobRepository state control, not a sign that the caller lacks permission.

The API should handle these situations separately:

| Situation | Appropriate response |
|---|---|
| Caller lacks the authority | Deny access, usually HTTP 403 |
| Caller is not authenticated | Require authentication, usually HTTP 401 with an API token |
| Invalid parameters | Return a validation error, usually HTTP 400 |
| JobInstance is running or has completed | Return appropriate conflict/status information, not interpreted as an authorization error |
| Job accepted to run asynchronously | Return the execution code for the caller to monitor, usually HTTP 202 |

You can use a request ID or idempotency key at the API layer to recognize requests resent because of a timeout. You need to design the key and store the request result so that a retry from the client does not unintentionally create a new business job.

## 11. Common authorization mistakes

| Mistake | Risk | Remedy |
|---|---|---|
| Assuming JobLauncher checks roles itself | A logged-in user can run jobs beyond their permissions | Protect the controller/service with Spring Security |
| Checking only the role and not the tenant | A caller can request a job to process another tenant's data | Check permissions per resource and parameter |
| Letting the caller pass an arbitrary job name | Internal or privileged jobs can be triggered | Use business endpoints and a job allow-list |
| Letting the caller pass any JobParameters | The data scope or configuration can be changed unexpectedly | Fixed DTO, allow-list, and validation |
| Using a single admin permission for every operation | Hard to limit the impact of an operator | Separate launch, read, restart, stop, and abandon permissions |
| Relying on the SecurityContext in a worker thread | A background job may not see the caller's identity | Store the requester explicitly or configure context propagation |
| Not auditing the requester | Hard to trace who launched an execution | Store the requester, time, calling source, and execution ID |
| Putting credentials into JobParameters | Secrets can be stored in metadata or logs | Use a secret manager and secure connection configuration |

## 12. Pre-launch verification process

Before calling `JobLauncher`, the launch service should follow this sequence:

1. Verify the caller has been authenticated and recognized by Spring Security.
2. Check that the authority is allowed to launch the right job type.
3. Check permissions on the requested tenant or data scope.
4. Validate and normalize the JobParameters according to the job's contract.
5. Record the audit of the request and the requester's identity.
6. Call `JobLauncher.run(job, parameters)`.
7. Return the execution ID and an appropriate initial status; provide a separately protected status-reading endpoint.

For administrative operations such as restart, stop, and abandon, apply a separate policy based on permissions and the execution state. Do not reuse the launch permission as the default administrative permission.

## Conclusion

`JobLauncher` only provides the mechanism to launch jobs; it does not authenticate or authorize the caller itself. The application needs to protect the call point with Spring Security, limit job types and JobParameters, check permissions on the specific tenant or data, and separate the launch permission from the read, restart, stop, and abandon permissions.

When a job runs asynchronously or is called by a scheduler, store the requester identity and audit explicitly. Combine access control with validation, resource limits, and an idempotency policy so that only valid requests can create an execution.
