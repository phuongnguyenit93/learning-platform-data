# Checking Permissions in Background Jobs with Explicit Execution Identities

## 1. Problem Statement and Goals

In a Spring Security application, an HTTP request usually has a clear identity: who authenticated, which authorities they hold, and which records they may act upon. When work moves to `@Async`, a thread pool, `@Scheduled`, a queue, a batch processor, or a worker in another process, those assumptions break down. A task can still execute **after the HTTP request ends, on another thread or machine, under a service account**, or after the requester has lost permissions.

This lesson centers on one principle: **every background task must have a defined and verified execution identity while retaining the initiator's identity to evaluate data permissions.** Never equate "the service is allowed to run a worker" with "any user may ask the worker to act on any data."

Running example: Alice belongs to tenant A and may export reports for tenant A; Bob belongs to tenant B. Alice submits an export request for document A-101, and the API creates job `J-100`. The worker uses service identity `report-worker` to read data and generate the file. If the worker relies only on broad service rights without checking the requester, Alice could send `documentId=B-202` or alter the tenant in the payload to extract B's data. If Alice's permission is revoked between job creation and execution, running with "stale permissions" can also violate policy.

**Goals after this lesson:**

- Identify **initiator/requester**, **execution principal**, **data subject/tenant**, and job action; enforce appropriate checks at job creation, job execution, and result retrieval.
- Understand when `SecurityContext` is lost across thread boundaries; use the right Spring Security tools to propagate context for short tasks, and know the limits of that mechanism.
- Design queues/batches/schedulers with explicit service identities, "on behalf of" audit trails, current-permission rechecks, data scoping, membership changes, retries, and cancellation.
- Test allow/deny, side effects, audits, and worker data isolation under concurrency.

## 2. Four Distinct Entities in a Job

| Component | Question to Answer | Example | Security Purpose |
| --- | --- | --- | --- |
| **Requester/initiator** | Who requested the work? | `user:alice` | Proves authority to submit and access data; supports auditing |
| **Execution principal** | Under which identity does the worker run? | `service:report-worker` | Proves authority to call required services/infra; never grants access to all tenants |
| **Resource/data scope** | Which records, tenant, columns, and export belong to the scope? | `tenant:A`, `document:A-101` | Enforces object-level authorization and prevents cross-tenant access |
| **Job identity** | Which job, which state, and who may view/download results? | `job:J-100`, owner Alice | Constrains read/cancel/retry/download and traces a single execution |

Key distinctions:

- **Authentication**: verifies the user token at the API or the service credential at the worker.
- **Functional authorization**: e.g., the user holds `SCOPE_report.export` to create jobs; the service holds `report-job:execute` to run that job type.
- **Object/data authorization**: is the actor allowed to read those specific documents/columns/tenants being exported?
- **Delegation/on-behalf-of**: the service performs work for Alice on data Alice is authorized for, under an explicit contract for scope and lifetime. A service token does not automatically turn into a user token.
- **Audit identity**: log `requestedBy`, `executedBy`, `jobId`, `tenantId`, `action`, `decision`, and `policyVersion` for investigation; never log raw access tokens or credentials.

A job can have **two simultaneous conditions**: "a valid worker is allowed to handle this job type" **AND** "the requester is currently allowed to perform the operation on the exact data." If either condition fails, the job must stop safely. There can also be "system-initiated" jobs with no human requester; those must declare an explicit job type and service identity with dedicated scope rather than spoofing an arbitrary user.

## 3. Thread Boundaries: `SecurityContextHolder` Does Not Follow Work Automatically

In standard Servlet configurations, `SecurityContextHolder` stores context per **current thread**, defaulting to a `ThreadLocal`-based strategy. Thus the HTTP request's `Authentication` is not automatically present on a worker thread. An `@Async` or `CompletableFuture.supplyAsync` call can observe an empty context unless context is explicitly propagated.

Possible states:

1. **No context propagation:** `SecurityContextHolder.getContext().getAuthentication()` in the worker thread is usually `null`. A method with `@PreAuthorize` requiring authentication will deny; custom code that "skips checks if null" creates a vulnerability.
2. **Proper propagation for short tasks:** Spring Security provides `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextAsyncTaskExecutor`, and variants; they bind context during delegate execution and clean up/restore via the wrapper, preventing one task's identity from leaking to the next.
3. **Wrong propagation or holding context too long:** binding a fixed admin `SecurityContext` to **every task**, or storing a user's context for hours and restoring it later, can cause over-privileged execution, stale permissions, and cross-request data leaks.
4. **`@Scheduled`/message workers:** typically have no active user HTTP request. Never assume an HTTP request principal will be present; design explicit execution identities and policies.

> `SecurityContext` is the security context for a single execution. It is **not** a durable authorization record for queued jobs, not permanent proof of permission, and not a place to store full business state.

### When Is Propagating `SecurityContext` Appropriate?

Very short `@Async` tasks running in the same process that need method security under the current identity can use the wrapper—provided the caller is truly authorized to submit, execution lifetime is bounded, and the worker still checks object permissions. If a job must survive restarts, message brokers, long retries, or run on another machine, **propagating the `SecurityContext` object is inappropriate**; queues should carry minimal identity/security metadata and rehydrate policy from trusted server sources at execution time.

## 4. Short `@Async` Example: Right Propagation, Not the Whole Policy

The following configuration is a **Java/Spring fragment for Servlet Spring Security 6.x/7.x**, requiring spring-context/spring-task and spring-security dependencies. It is not a standalone plain-Java program. The wrapper captures the context of the **task-submitting thread** when enqueueing onto the executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
class AsyncSecurityConfiguration {
    @Bean("contextAwareExecutor")
    AsyncTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor delegate = new ThreadPoolTaskExecutor();
        delegate.setCorePoolSize(4);
        delegate.setMaxPoolSize(8);
        delegate.setQueueCapacity(64);
        delegate.setThreadNamePrefix("report-short-");
        delegate.initialize();

        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
~~~

Another method, invoked through a Spring-managed bean:

~~~java
@Service
class QuickPreviewService {
    private final DocumentPolicy policy;
    private final ReportRenderer renderer;

    QuickPreviewService(DocumentPolicy policy, ReportRenderer renderer) {
        this.policy = policy;
        this.renderer = renderer;
    }

    @Async("contextAwareExecutor")
    @PreAuthorize("hasAuthority('SCOPE_report.preview')")
    public CompletableFuture<ReportPreview> preview(long documentId) {
        Authentication actor =
            SecurityContextHolder.getContext().getAuthentication();

        policy.requireCanPreview(actor, documentId);
        return CompletableFuture.completedFuture(renderer.preview(documentId));
    }
}
~~~

Add `@Service`, `@Async`, `@PreAuthorize`, `CompletableFuture`, `Authentication`, `SecurityContextHolder`, and project collaborators as needed. **This is only an integration illustration**, and `@PreAuthorize` can apply at a different interceptor boundary when combined with async; test with a real Spring context to verify exactly when the policy executes. Enforce checks at the **submit endpoint** for immediate rejection, and **recheck** when the task starts if policy requires; do not rely solely on annotation ordering.

What must be verified:

- When Alice submits a task, the task observes Alice—not a principal from another request by Bob on the same pool.
- When the task finishes or throws an exception, no context lingers on the reused thread for the next task.
- `@Async` only takes effect through a Spring proxy; `this.preview(...)`/self-invocation may neither run async nor hit interceptors.
- If a task was submitted before permission revocation, the propagated context can still hold **stale** authorities; the wrapper does not revalidate revocations.
- Never use `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` as a default solution for thread pools: long-lived reused threads can retain unexpected contexts.
- Never put secret authentication material or a full serialized `SecurityContext` into queues, databases, Kafka messages, or logs.

`DelegatingSecurityContextExecutor` also has a constructor taking a **fixed** `SecurityContext`. That mode has specific uses for controlled system tasks, yet must never be put on a shared pool that accidentally runs all "on behalf of Alice" tasks under a privileged account.

## 5. Durable Job Queues: Separated Identity Model

For asynchronous report exports, the safe pattern is persisting job metadata **server-side** right after validating the request. A suggested schema:

~~~json
{
  "jobId": "J-100",
  "jobType": "REPORT_EXPORT",
  "requestedBy": "user:alice",
  "requestedTenant": "tenant:A",
  "resourceIds": ["A-101"],
  "requestedAction": "report.export",
  "createdAt": "2026-11-06T07:00:00Z",
  "expiresAt": "2026-11-06T08:00:00Z",
  "authorizationMode": "RECHECK_AT_EXECUTION",
  "status": "PENDING"
}
~~~

This is an example business schema, **not a self-authenticating token or credential**. `jobId`, `requestedBy`, `requestedTenant`, `jobType`, and resource selection must come from a protected job store; every permission-affecting field in the public payload must be validated before saving. Queue messages can carry just `jobId` and version so the worker reloads the trusted record. Across trust boundaries, verify message origin, integrity, tenant routing, and tampering/replay protection.

Never store `Authentication`, JWT access tokens, refresh tokens, passwords, or permission "snapshots" inside a job and blindly trust them at execution time. A permission snapshot may only be used if the business contract **explicitly** allows it with concrete time bounds, audits, and scope limits. For data exports and high-impact operations, practical policy usually requires **rechecking at execution time** and before delivering outputs.

### Flow from HTTP to Output

~~~mermaid
flowchart TD
    A[HTTP: Alice requests export] --> B[Validate token and check submit permission]
    B --> C{Is Alice allowed to export document A-101?}
    C -->|No| X[Deny, do not create job]
    C -->|Yes| D[Save job with requester, tenant, action, scope]
    D --> E[Queue carries ID/version only, worker verifies source]
    E --> F[Authenticated service identity: report-worker]
    F --> G{Is service allowed to execute job type?}
    G -->|No| Y[Fail closed, audit]
    G -->|Yes| H[Reload requester and current policy]
    H --> I{Does requester still have permission on data?}
    I -->|No| Z[DENIED/CANCELLED, do not export file]
    I -->|Yes| J[Query data with scope constraints]
    J --> K[Verify file content, store result safely]
    K --> L[Download: check requester/current permissions]
~~~

**Key point:** job creation permission, job execution permission, and output download permission are **three distinct checks** with different purposes. Never treat an API returning `202 Accepted` as proof that the final export is authorized. `202` only means the request was accepted for asynchronous processing, not guaranteed to succeed.

## 6. Permission Policies at Each Lifecycle Point

### 6.1. Before Writing the Job (Submit)

- Authenticate the requester and verify the right `issuer`/`audience` for the API. Check functional authority (`SCOPE_report.export`) and resource read/export policies by tenant, organization, owner, and ACL.
- Normalize/pin the approved `resourceIds` or filter; never trust tenant/owner from an `X-Tenant` header or JSON body. For dynamic filters like "export entire tenant," record the allowed filter and server-verified tenant explicitly.
- Enforce quotas/size limits and rate limits before enqueueing so legitimate users cannot enqueue millions of jobs and starve workers; quotas do not replace authorization.
- Never allow callers to choose `runAs=admin`, `executorRole=superuser`, or a service identity in the payload.
- Audit `requestedBy`, timestamp, requested scope, decision, policy source/version, and correlation ID; avoid storing PII/confidential files in message logs.

### 6.2. When the Worker Picks Up Work (Execute)

- The worker authenticates its **execution principal** via an appropriate internal mechanism: service account, workload identity/mTLS, or machine-to-machine token with an explicit audience. If the infrastructure lacks a framework principal, at minimum the job handler must have a trusted configured service identity with constrained execution rights.
- Check that the service is authorized for the `jobType` being run; a reporting worker must not be able to run user-admin operations.
- Load the job from the protected store and verify `PENDING/RETRY` status, message signature/source, deadline, tenant, and version/idempotency token. Never treat the message queue as the source of authority.
- Reload the requester by `requestedBy`; verify account is active, membership is valid, resource/scope still belongs to that user, policy version, and other bounds. If no longer authorized, deny/mark denied; never "fall back" to the service's own permissions.
- Read/write data via scope-predicated queries inside appropriate transactions; for large exports, enforce scope per batch/cursor and avoid scanning full tables then filtering after sensitive data leaves the DB.
- If execution runs very long, define checkpoint/reauthorization intervals per policy; a check at second zero may not suffice for a multi-hour job.

### 6.3. When Delivering Results (Download, Retry, Cancel)

- The job creator is not always the only person allowed to download; define explicit policies for authorized admins, shared groups, owner assistants, etc. Never infer permission from knowing `jobId` or the URL.
- The download endpoint must enforce `view/download` permissions on **job + file + underlying data**, even when the file was generated before permission revocation. For signed URLs, bound lifetimes/audiences and define invalidation procedures per sensitivity.
- Retries must not escalate privileges: re-run only verified metadata, recheck the requester, and never let retry payloads switch tenants. Cancel/restore/purge must also check actor and job scope.
- Delete temporary files when a job is denied/failed; ensure previously created files cannot be downloaded via old URLs if policy requires revocation.

### 6.4. System-Initiated Jobs

A `@Scheduled` midnight invoice aggregation job may have **no user requester**. Explicitly set `origin=SYSTEM_SCHEDULE` and `executedBy=service:billing-scheduler` with a dedicated whitelist of job types/tenants/data policies. Run under an authenticated, authorized service principal—never attach a manual "admin" account just to bypass method security. The system may hold cross-tenant batch rights, yet those must be explicitly granted and audited; tenant routing must never come from untrusted parameters.

## 7. Spring Service Pattern: Splitting Submit and Execute Permissions

The following snippets are **Spring Boot/Spring Security skeletons requiring real repositories, policies, and job stores** to illustrate control placement; they are not standalone code.

Submit from a request with a valid principal:

~~~java
@Service
class ExportJobSubmission {
    private final ExportPolicy exportPolicy;
    private final ExportJobRepository jobs;

    ExportJobSubmission(ExportPolicy exportPolicy, ExportJobRepository jobs) {
        this.exportPolicy = exportPolicy;
        this.jobs = jobs;
    }

    @PreAuthorize("hasAuthority('SCOPE_report.export')")
    @Transactional
    public String submit(Authentication actor, String documentId) {
        // Returns server-verified tenant; NEVER use client-supplied tenant.
        String tenant = exportPolicy.requireCanExport(actor, documentId);

        ExportJob job = ExportJob.pending(
            actor.getName(), tenant, documentId, "REPORT_EXPORT");
        jobs.save(job);
        return job.getId();
    }
}
~~~

In the controller, pass the `Authentication` obtained from Spring Security after authentication. Here `@PreAuthorize` checks functional authority; `requireCanExport` checks resource/tenant. Besides the job row, you need an outbox/transactional messaging setup to avoid committing the DB while failing to enqueue, or vice versa. Never store submit-time `actor.getAuthorities()` as immutable permissions for the worker later.

Worker with service identity:

~~~java
@Service
class ExportJobRunner {
    private final ExportJobRepository jobs;
    private final ExportPolicy policy;
    private final DocumentRepository documents;
    private final ExportStorage storage;

    ExportJobRunner(ExportJobRepository jobs, ExportPolicy policy,
                    DocumentRepository documents, ExportStorage storage) {
        this.jobs = jobs;
        this.policy = policy;
        this.documents = documents;
        this.storage = storage;
    }

    // Called through a service adapter with verified workload identity,
    // or by an internal scheduler granted a configured service identity.
    public void execute(String jobId, ExecutionIdentity executor) {
        policy.requireCanExecute(executor, "REPORT_EXPORT");

        ExportJob job = jobs.lockPending(jobId);
        if (!"REPORT_EXPORT".equals(job.getType())) {
            throw new AccessDeniedException("Wrong job type");
        }

        // Recheck policy loads current membership/roles of requester.
        policy.requireCanStillExport(job.getRequestedBy(),
                                     job.getTenantId(),
                                     job.getDocumentId());

        // Query enforces verified scope constraints.
        var doc = documents.findByIdAndTenantId(
            job.getDocumentId(), job.getTenantId()
        ).orElseThrow(() -> new AccessDeniedException("Out of scope"));

        storage.writeAuthorized(job.getId(), doc);
        jobs.markCompleted(job.getId());
    }
}
~~~

In a real system, handle transactions/outboxes, lease locking, idempotency, and file/DB errors. `ExecutionIdentity` must be constructed by a trusted service-authentication component, never from an `executor` field in the queue body. `lockPending` and `markCompleted` need owner/state/version constraints so two workers cannot export the same job concurrently. Avoid holding one long DB transaction across an entire file upload if that holds locks too long; use a lease + state machine with staging outputs and proper commit/cleanup.

If placing `@PreAuthorize` on the worker, the method must be called **through a Spring proxy** with a corresponding `Authentication` present. In durable queues, a policy accepting an explicit `ExecutionIdentity` is often clearer than fabricating a user `Authentication` inside `SecurityContextHolder`. You can combine method security for the service identity with business policies for `requestedBy`, provided you specify which enforces what.

### Do Not Reuse Contexts Manually on Thread Pools

Anti-pattern that easily leaks identities:

~~~java
// Dangerous if context is not restored/cleared and permissions revalidated.
SecurityContextHolder.getContext().setAuthentication(userAuthentication);
workerPool.execute(() -> writeDataWithoutObjectCheck(job));
~~~

Calling `setAuthentication(...)` on the **request thread** does not ensure tasks running on worker threads receive that context; and if code sets context inside a worker without a `finally` restore/clear, a pooled thread can "leak" that identity to the next task. Use executor wrappers for short tasks, or explicit job execution identities and policies for durable jobs.

If a temporary context is truly needed in an internal adapter, the core pattern is:

~~~java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContext next = SecurityContextHolder.createEmptyContext();
    next.setAuthentication(verifiedServiceAuthentication);
    SecurityContextHolder.setContext(next);
    invokeSecuredService();
} finally {
    SecurityContextHolder.setContext(previous);
}
~~~

This is an **illustrative code fragment**, not a guide to forging a fake service authentication. `verifiedServiceAuthentication` must originate from the worker's trusted authentication path. Prefer official wrapper mechanisms where suitable because hand-rolled context management is error-prone under concurrency. In particular, never share or mutate the same `SecurityContext` instance across threads.

## 8. Standalone Java 17: Jobs Do Not Inherit Permissions from Executors

The program below simulates an enqueue API, job store, service identity, and worker that rechecks the requester. It **does not use Spring Security**, isolating permission invariants in Java 17+ before Spring integration. Save as `BackgroundAuthorizationDemo.java`; run `javac BackgroundAuthorizationDemo.java` then `java BackgroundAuthorizationDemo`.

~~~java
import java.util.*;

public class BackgroundAuthorizationDemo {
    record Actor(String id, String tenant, boolean active,
                 Set<String> permissions) {}
    record Document(String id, String tenant) {}
    record Job(long id, String requestedBy, String tenant,
               String documentId) {}

    static final class Denied extends RuntimeException {}

    static final class Platform {
        final Map<String, Actor> users = new HashMap<>();
        final Map<String, Document> documents = new HashMap<>();
        final Map<Long, Job> jobs = new LinkedHashMap<>();
        long nextId = 1;

        private boolean canExport(Actor actor, Document doc) {
            return actor != null
                && actor.active()
                && actor.permissions().contains("report.export")
                && doc != null
                && actor.tenant().equals(doc.tenant());
        }

        Job enqueue(String requesterId, String documentId) {
            Actor actor = users.get(requesterId);
            Document doc = documents.get(documentId);
            if (!canExport(actor, doc)) throw new Denied();

            Job job = new Job(nextId++, actor.id(),
                              actor.tenant(), documentId);
            jobs.put(job.id(), job);
            return job;
        }

        void run(long jobId, String serviceIdentity) {
            // Execution identity must be verified by the worker adapter.
            if (!"service:report-worker".equals(serviceIdentity)) {
                throw new Denied();
            }

            Job job = jobs.get(jobId);
            if (job == null) throw new Denied();
            Actor current = users.get(job.requestedBy());
            Document doc = documents.get(job.documentId());

            // Do not grant data access from broad service permissions.
            if (!canExport(current, doc)
                    || !current.tenant().equals(job.tenant())) {
                throw new Denied();
            }

            System.out.println("executed job=" + job.id()
                + " by=" + serviceIdentity
                + " for=" + job.requestedBy());
        }
    }

    static void expectDenied(Runnable action) {
        try {
            action.run();
        } catch (Denied expected) {
            return;
        }
        throw new AssertionError("Expected access denial");
    }

    public static void main(String[] args) {
        Platform p = new Platform();
        p.users.put("alice", new Actor(
            "alice", "A", true, Set.of("report.export")));
        p.documents.put("A-101", new Document("A-101", "A"));
        p.documents.put("B-202", new Document("B-202", "B"));

        Job job = p.enqueue("alice", "A-101");
        System.out.println("queued job=" + job.id());

        expectDenied(() -> p.enqueue("alice", "B-202"));
        System.out.println("denied cross-tenant submit");

        // Simulate permission revocation after the job was already saved.
        p.users.put("alice", new Actor(
            "alice", "A", true, Set.of()));
        expectDenied(() -> p.run(job.id(), "service:report-worker"));
        System.out.println("denied revoked permission");

        // Worker rejects a self-chosen execution identity.
        expectDenied(() -> p.run(job.id(), "service:untrusted"));
        System.out.println("denied wrong executor");

        p.users.put("alice", new Actor(
            "alice", "A", true, Set.of("report.export")));
        p.run(job.id(), "service:report-worker");
    }
}
~~~

Expected output:

~~~text
queued job=1
denied cross-tenant submit
denied revoked permission
denied wrong executor
executed job=1 by=service:report-worker for=alice
~~~

Takeaways from the example: an accepted enqueue **does not guarantee** the worker can execute; revocation must affect execution when the policy rechecks. `service:report-worker` only proves a valid worker in the demo, not a replacement for the user. In production, a service name string is insufficient for authentication: use mTLS/workload identity/credentials verified by the adapter; jobs need idempotency, state transitions, and download permission checks.

## 9. SQL Patterns for Scoping Data and Job State

Never query records solely by `documentId` and rely on the worker being a trusted service to skip scoping. For example:

~~~sql
SELECT d.id, d.tenant_id, d.content
FROM documents AS d
WHERE d.id = :documentId
  AND d.tenant_id = :authorizedTenant;
~~~

`:authorizedTenant` must be the tenant verified for the requester **at the moment policy is evaluated**. If the application uses row-level security, ACLs, or shared workspaces, predicates must express the full policy rather than assuming tenant equality suffices. For large exports, apply the same predicates to `COUNT`, pagination/cursors, joins, file streaming, and child jobs.

To prevent two workers from claiming the same job simultaneously, use conditional state transitions, illustrated conceptually in SQL:

~~~sql
UPDATE export_jobs
SET status = 'RUNNING',
    claimed_by = :verifiedServiceId,
    lease_until = :leaseDeadline
WHERE id = :jobId
  AND status IN ('PENDING', 'RETRY')
  AND tenant_id = :verifiedJobTenant;
~~~

Check that **updated row count** equals 1 before proceeding; if 0, the job was not claimed. You also need lease expiration, attempt counts, isolation, and guards preventing two workers from reclaiming an expired lease while one worker is still running. `claimed_by` is for service traceability and does not prove requester data access; requester authorization remains separate. A `RUNNING` job state must not act as a license to export data if permissions were just revoked.

## 10. Performance, Operational Resilience, and Least Privilege

Protecting background jobs does not mean calling a remote authorization API per data row in an N+1 loop. Pick the right **unit of verification**:

- **Before enqueue:** check job creation rights, quotas, and filters once.
- **Before each run/retry:** verify service identity, job integrity, requester, membership, current policy, and resource scope.
- **At query/batch time:** push server-side predicates into the DB/search engine, using optimized ACL joins, RLS, or policy queries rather than filtering records after fetching. For millions of rows, check permissions per batch/checkpoint and abort when revoked per contract.
- **Policy caching:** if caching decisions like "Alice has access to tenant A," key by actor, tenant, action, resource/policy versions, and valid lifetime. On revocation, match invalidation/TTL to sensitivity; a cache hit alone does not prove permissions remain valid.
- **Retry/backoff:** authorization errors should move jobs to `DENIED`/`CANCELLED` rather than retrying indefinitely. Transient infra errors need backoff, max attempts, and waiting states, **never** falling back to service-admin to force completion.
- **Concurrency/isolation:** queue partitions, thread pools, transactions, and job locks must never mix tenant A/B contexts; verify caches, temp files, report paths, and output metadata.
- **Backpressure:** per-actor/tenant quotas, max concurrent jobs, memory/file size caps, and queue depth limits prevent one actor from exhausting worker capacity. Rate limiting is resource control, not a replacement for authorization.

### Audit and Observability

Each enqueue/run/download should log structured fields: `eventType`, `jobId`, `requestedBy`, `executedBy`, `tenantId`, `scope/action`, `decision`, `reasonCode`, `timestamp`, `correlationId`, and policy version where relevant. For system schedulers, `requestedBy` should be `SYSTEM` or an explicit null with reason, **never** forged as a fake user's username.

Useful metrics: counts of `DENIED_AT_SUBMIT`, `DENIED_AT_EXECUTION`, `REVOKED_DURING_RUN`, `FAILED_AUTH_SERVICE`, queue wait time, retry rate, stale jobs, and quota throttling. Alert on unusual spikes in denied jobs or cross-tenant access attempts. Never put tokens/refresh tokens/PII into metric labels or logs to prevent leakage via observability tools.

## 11. Boundary-Accurate Security Testing

### Minimum Test Matrix

| Scenario | What Must Be Proven |
| --- | --- |
| Alice allowed to export A, valid worker | Enqueues cleanly; runs strictly on tenant A, outputs matching records |
| Alice submits document B's ID | Rejected at submit; no job created/enqueued |
| Alice submits A's ID but alters tenant in message | Worker reads tenant from protected job store; never exports B |
| Alice loses `report.export` after enqueue | Worker rechecks and denies; no file exported |
| Alice locked/loses membership while job pending | Worker denies even though job was initially accepted |
| Service lacks job-type permission or invalid credential | Worker denies before querying DB; never borrows user rights |
| Another user guesses `jobId` or download URL | Cannot view, cancel, retry, or download unauthorized files |
| Contexts A and B share a thread pool | Task B never sees principal A; cleanup works after exceptions |
| Retry after crash, duplicate queue delivery | Idempotent state transition; never double-runs or escalates |
| Policy/auth server temporarily fails | Fail closed or defer with controlled retry; never dumps entire DB |
| Large export containing A/B data | All pages/chunks/rows/counts include only authorized data |
| System scheduler | Explicit service identity, whitelisted job types/scope; no fake requester |

### Three Complementary Testing Levels

**1. Policy unit tests:** pass `requestedBy`, `executorIdentity`, `action`, `documentId`, `tenantId`, `membership`, and `jobStatus` into the policy function. Assert both allow and deny, especially "valid executor yet requester lost rights," "valid requester yet invalid executor," and "both have functional rights yet document is out of tenant." Mock source data when testing policy logic itself; never mock the decision under test.

**2. Spring Security / thread-pool integration tests:** use `@SpringBootTest` with a real executor, submit two tasks under two distinct identities, verify each reads the right authentication, and verify cleanup even when a task throws. Use `CountDownLatch`/`Future` with timeouts instead of `Thread.sleep(...)` to avoid flakiness. Verify `@Async` runs through the proxy and method security triggers. To test runtime JWT validation, test the decoder/issuer/audience too; `jwt()` in MockMvc constructs authentication while skipping real token verification.

**3. E2E with broker/storage:** send a real job creation request, let the worker pick up the message, mutate membership before execution, and assert state transitions and untouched DB/files on denial. Test job replay, duplicates, unauthorized download/cancel, multi-page batch exports, and crash retries. Use clear actor A/B fixtures and distinct data IDs; every negative test must have a positive control so a system that denies everything does not falsely pass.

### Illustrative Spring Test Skeleton

~~~java
@SpringBootTest
class ExportWorkerAuthorizationTest {
    @Autowired ExportJobSubmission submission;
    @Autowired ExportJobRunner runner;
    @Autowired TestFixtures fixtures;

    @Test
    void revocationBetweenSubmitAndExecutionMustDeny() {
        Authentication alice = fixtures.authenticatedAliceWithExport();
        String jobId = submission.submit(alice, "A-101");

        fixtures.revokeExportPermission("alice");

        assertThatThrownBy(() -> runner.execute(
                jobId, fixtures.verifiedReportWorker()))
            .isInstanceOf(AccessDeniedException.class);

        assertThat(fixtures.exportFileExists(jobId)).isFalse();
        assertThat(fixtures.jobStatus(jobId)).isEqualTo("DENIED");
    }
}
~~~

This is a **skeleton** requiring real repositories, policies, fixtures, and exception handling. It cannot be claimed to compile standalone. In a real application, a submit method with `@PreAuthorize` requires Alice's real `SecurityContext` when invoked through the Spring proxy; passing an `Authentication` parameter alone does not automatically expose that principal to method security. Establish authentication via Spring Security's test mechanisms (e.g., `@WithMockUser` or properly populated `SecurityContextHolder`) and ensure tests verify authority checks at submit time too. Persisting job status `DENIED` happens when catching the error in the real workflow; the illustrative runner above may throw before persisting that status. Tests must reflect the real state machine.

## 12. Common Bugs and Anti-Patterns

| Bug | Why It Is Dangerous | How to Avoid |
| --- | --- | --- |
| "Async has no auth so drop `@PreAuthorize`" | Background jobs run broader than user rights | Define execution identities and explicit policy checks |
| Copying user `SecurityContext` into queue | Stale tokens/rights, credential exposure, unsafe serialization | Store minimal identity/job metadata; revalidate at execution |
| Every task uses a fixed admin `SecurityContext` | Any user leverages service power out of scope | Give service narrow capabilities plus requester/object policy |
| `MODE_INHERITABLETHREADLOCAL` on pools | Reused threads mix principals | Use standard wrappers or explicit job identity; test cleanup |
| Worker trusts `tenantId`/`requestedBy` from client message | Requester spoofing and cross-tenant access | Read from server-side job store, verify message origin |
| Checking only at enqueue | Membership/scope can be revoked later | Recheck before running/retrying and at checkpoints if needed |
| Worker queries `findAll()` then filters in Java | Unauthorized data loaded, leaks in logs/cache/files | Enforce scope predicates in DB and export streams |
| Download checks only knowledge of `jobId` | IDOR, leaks files even when job ran right | Check explicit permissions on job/file at download |
| Retry falls back to service-admin or skips policy | Privilege escalation after infra failures | Always route retries through policy, bound attempts |
| Using `@Async` + `@PreAuthorize` without testing interceptors | Thread boundaries alter context/check timing | Run integration tests and separate submit/run policies |
| Asserting only HTTP 202 | Worker may run with wrong rights asynchronously | Assert DB/files, job state, and actor/executor audit |
| Logging access tokens with jobs | Credential leakage via log systems | Log canonical identities and correlation IDs |

## 13. Design and Acceptance Checklist

- [ ] Every job records `requestedBy` (or defined `SYSTEM`), `executedBy`, `jobType`, resource/tenant scope, state, and audit trail.
- [ ] Requester is authenticated and authorized to submit for both the action **and** exact resources; clients cannot pick service identities or spoof requesters.
- [ ] Worker authenticates its service identity, holds permission for the job type, and never runs on trust of requester-supplied tokens/roles.
- [ ] Policies define checks at submit, execute, retry, and download; revocation/expiry handling is intentional.
- [ ] Job store and message integrity are protected; workers never trust unverified payloads.
- [ ] Data is queried with exact tenant/ACL constraints, never using broad service rights as a shortcut.
- [ ] Short pooled tasks use proper context propagation and cleanup; durable jobs use identity metadata + recheck.
- [ ] Schedulers have dedicated system permissions, action/tenant whitelists, and never impersonate users to pass security.
- [ ] State transitions/idempotency/leases exist, retries are bounded, and cancellation applies when permissions are revoked.
- [ ] Private outputs/files enforce authorization, denied temp files are cleaned up, and logs contain no credentials.
- [ ] Unit/integration/E2E tests cover happy path, cross-tenant, revocation, pool reuse, broker duplicates, and unauthorized downloads.
- [ ] Permission decisions log requester and executor separately—traceable without leaking sensitive details.

**Passing criterion:** a job running under a valid service identity performs **only** authorized actions on data the requester (or system policy) is allowed to access per the defined evaluation time/delegation mode. No background execution path ever becomes an automatic Spring Security bypass, even when the initial request authenticated cleanly.

### References

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and `ThreadLocal` wrappers.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContextHolder`, `SecurityContext`, and `Authentication`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, bean proxies, and method-level checks.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request entrypoint permissions.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `@Scheduled`, and task executors.
