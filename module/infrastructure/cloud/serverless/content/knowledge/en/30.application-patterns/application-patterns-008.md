# Triggering AI Inference via API and Orchestrating Background Tasks

A serverless Java application can expose an API to receive AI inference requests, invoke a model provider, and return results to the caller. For short tasks, a function can call the model synchronously and return the response immediately. For long-running tasks such as document analysis, multi-image processing, report generation, batch embeddings, or multi-step pipelines, holding an HTTP request open throughout execution increases timeouts, ties up concurrency slots, and makes recovery difficult if the network drops.

A common pattern is **an API that accepts a job, persists durable state, enqueues the job, and delegates execution to background workers**. The caller receives a job ID and a status URL; the worker invokes the model, stores the result, and updates job state. A workflow engine can orchestrate long-running steps, retries, branches, and callbacks. This pattern decouples acceptance time from completion time while enabling control over concurrency, quotas, costs, and recovery.

This lesson covers designing synchronous and asynchronous AI inference APIs, using queues or workflows to orchestrate background tasks, persisting job state, implementing Java functions, securing data, and managing retries, idempotency, observability, and cost.

## 1. The Big Picture

An AI inference request typically follows these steps:

1. The caller submits input along with optional parameters such as model, task type, or output format.
2. The API authenticates the caller, checks permissions, enforces size limits, and validates input.
3. The system decides whether to run synchronously or create a background job.
4. The worker calls the model provider or inference endpoint.
5. Results are validated, normalized, and persisted.
6. The caller receives the result directly or polls job status.
7. Logs, metrics, and traces correlate the entire journey.

~~~mermaid
flowchart TD
    Client[Client / application]
    Gateway[API Gateway]
    Handler[Java serverless API]
    Auth[Identity and validation]
    DB[(Job database)]
    Outbox[(Transactional outbox)]
    Queue[Queue / event bus]
    Worker[Java inference worker]
    Model[AI model API]
    Storage[(Object storage)]
    Status[Job status API]

    Client --> Gateway --> Handler --> Auth
    Auth -->|Short task| Model
    Model --> Handler
    Handler -->|Immediate result| Client
    Auth -->|Long task| DB
    DB --> Outbox --> Queue --> Worker
    Worker --> Model
    Worker --> Storage
    Worker --> DB
    Client --> Status
    Status --> DB
    Status --> Client
~~~

The job-intake API and the worker can be separate independent functions, allowing distinct timeout, memory, concurrency, IAM, and scaling configurations per workload type.

## 2. Choosing Synchronous Inference or Asynchronous Jobs

Not every model invocation needs a queue. Choose the execution model based on processing duration, caller experience, and recoverability.

| Criterion | Synchronous Inference | Asynchronous Job |
|---|---|---|
| Processing time | Short and tightly bounded | Long, variable, or multi-step |
| HTTP response | Returns result immediately | Returns `202 Accepted` and a job ID |
| Caller must wait | Yes | No |
| Timeout | Must fit within HTTP and function budgets | Each step has its own timeout; job has a deadline |
| Retries | Caller/client and function must coordinate | Queue/workflow manages durable retries |
| Scaling | By request concurrency | By queue backlog and worker capacity |
| Suitable for | Short classification, small prompts, fast Q&A | Document processing, batch embeddings, report generation, multi-step agent workflows |

As a rule of thumb, run synchronously only when both normal and tail latencies reliably fit within the API latency budget. Do not choose synchronous execution merely because the model responds quickly during small-scale testing.

### Synchronous Flow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java API function
    participant M as Model API

    C->>A: POST /v1/inference
    A->>A: Authenticate + validate
    A->>M: Inference request
    M-->>A: Model response
    A-->>C: 200 result
~~~

### Asynchronous Flow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java API function
    participant D as Job database
    participant Q as Queue
    participant W as Worker function
    participant M as Model API

    C->>A: POST /v1/inference-jobs
    A->>D: Insert job + outbox
    D-->>A: Commit
    A-->>C: 202 + jobId + status URL
    D->>Q: Publish job event
    Q->>W: Deliver job
    W->>M: Inference
    M-->>W: Result
    W->>D: Save result + SUCCEEDED
    C->>A: GET /v1/inference-jobs/{id}
    A->>D: Read status
    D-->>A: SUCCEEDED + result reference
    A-->>C: 200 status/result
~~~

## 3. Designing the API Contract

The API must clearly indicate whether the caller is requesting an immediate result or creating a job that completes later.

A synchronous contract:

~~~http
POST /v1/inference
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "task": "classify-document",
  "model": "approved-model-alias",
  "input": {
    "text": "Content to classify"
  }
}
~~~

Response upon completion:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "requestId": "req-72c1",
  "modelVersion": "model-release-12",
  "output": {
    "label": "invoice",
    "confidence": 0.97
  }
}
~~~

An asynchronous contract:

~~~http
POST /v1/inference-jobs
Authorization: Bearer <access-token>
Idempotency-Key: 3b7a8d1e-...
Content-Type: application/json

{
  "task": "summarize-document",
  "model": "approved-model-alias",
  "input": {
    "objectRef": "uploads/doc-918"
  },
  "callback": null
}
~~~

Acceptance response:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/inference-jobs/job-918
Retry-After: 3
Content-Type: application/json

{
  "jobId": "job-918",
  "status": "QUEUED",
  "statusUrl": "/v1/inference-jobs/job-918"
}
~~~

Return `202` only after both the job and the dispatch intent are durably persisted. If you only store state in memory before returning `202`, a function restart can lose the job.

### Status Endpoint

~~~http
GET /v1/inference-jobs/job-918
Authorization: Bearer <access-token>
~~~

While the job is running:

~~~json
{
  "jobId": "job-918",
  "status": "RUNNING",
  "createdAt": "2026-11-17T09:00:00Z",
  "updatedAt": "2026-11-17T09:00:12Z",
  "progress": {
    "stage": "MODEL_INFERENCE",
    "completedUnits": 1,
    "totalUnits": 3
  }
}
~~~

Upon completion:

~~~json
{
  "jobId": "job-918",
  "status": "SUCCEEDED",
  "result": {
    "url": "/v1/inference-jobs/job-918/result",
    "expiresAt": "2026-11-18T09:00:00Z"
  }
}
~~~

On failure, return a stable error code and a safe message to the caller. Never expose raw stack traces, provider secrets, or internal prompts.

## 4. Job Identification and Idempotency Keys

A `jobId` identifies a persisted execution record in the system. An idempotency key identifies the caller's intent to submit a job. These two concepts must not be conflated.

If a caller retries the same request after a timeout:

- Same idempotency key and same request payload: return the already-created job.
- Same key with a different payload: return `409 Conflict` per contract.
- New key: create a new job.

Persist the request hash to detect misuse of keys across differing payloads. The unique constraint must include tenant or caller scope so two customers never accidentally share an idempotency namespace.

~~~sql
CREATE TABLE inference_jobs (
    job_id            VARCHAR(128) PRIMARY KEY,
    tenant_id         VARCHAR(128) NOT NULL,
    idempotency_key   VARCHAR(128) NOT NULL,
    request_hash      VARCHAR(128) NOT NULL,
    task_type         VARCHAR(64) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    model_alias       VARCHAR(128) NOT NULL,
    model_version     VARCHAR(128) NULL,
    input_ref         TEXT NULL,
    result_ref        TEXT NULL,
    error_code        VARCHAR(64) NULL,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    completed_at      TIMESTAMP NULL,
    UNIQUE (tenant_id, idempotency_key)
);
~~~

Never generate a fresh random job ID for every retry of the same HTTP submission. Otherwise, a caller timing out and retrying can spawn two jobs and incur double inference charges.

## 5. Persisting Jobs and Dispatching Events with a Transactional Outbox

Saving a job in the database and publishing a queue message separately introduces a dual-write problem:

- Database commit succeeds, queue publish fails: the job stays stuck in `QUEUED` with no worker picking it up.
- Queue publish succeeds, database rolls back: a worker receives an event pointing to a nonexistent job.

Use a transactional outbox to persist the job and the event to dispatch in the same transaction.

~~~sql
CREATE TABLE inference_outbox (
    outbox_id       VARCHAR(128) PRIMARY KEY,
    aggregate_id    VARCHAR(128) NOT NULL,
    event_type      VARCHAR(128) NOT NULL,
    payload         TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL
);
~~~

Within a single transaction:

1. Insert into `inference_jobs`.
2. Insert into `inference_outbox` with event `inference.job.requested`.
3. Commit.

A dispatcher reads unpublished outbox rows, sends messages, and marks them published. Because the dispatcher can redeliver if it crashes after publishing but before updating `published_at`, workers still require idempotency.

Never hold a database transaction open while calling a queue or model provider. The outbox decouples data commits from network calls.

## 6. Job State Machine

Background jobs need explicit states so the API, workers, support tools, and schedulers agree on where a job stands.

A reference state machine:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> QUEUED
    RUNNING --> FAILED
    QUEUED --> CANCELLED
    RETRY_WAIT --> CANCELLED
    RUNNING --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> CANCELLED
    CANCEL_REQUESTED --> SUCCEEDED
~~~

States:

| State | Meaning |
|---|---|
| `QUEUED` | Job is persisted and awaiting a worker |
| `RUNNING` | A worker holds a lease and is processing |
| `RETRY_WAIT` | Transient error occurred; awaiting the next attempt |
| `SUCCEEDED` | Results are durably persisted |
| `FAILED` | Terminal error or retry budget exhausted |
| `CANCEL_REQUESTED` | Caller requested cancellation; worker must stop safely |
| `CANCELLED` | System confirmed job cancellation |

Define valid state transitions and enforce them via conditional updates/versioning. Never allow an old worker to mark a job `SUCCEEDED` if the job was already cancelled or claimed by another worker under a newer lease.

### Leases and Worker Recovery

A worker can be terminated mid-inference while waiting on a model. Use a lease containing owner, expiration, and generation/fencing token to prevent two workers from writing competing results. If a lease expires, a scheduler or another worker can reclaim the job. Any stale worker must validate its fencing token before persisting final results.

Never leave jobs in `RUNNING` indefinitely. A periodic sweeper should detect expired leases or past-deadline jobs and transition them to retry, `FAILED`, or reconciliation according to policy.

## 7. Java API: Accepting Jobs

A Spring Boot example showing how the API persists the job and outbox in the same transaction. Both repositories are assumed to share the same transaction manager and database.

~~~java
public record InferenceJobRequest(
        String task,
        String model,
        String objectRef) {}

public record AcceptedJob(
        String jobId,
        String status,
        String statusUrl) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/v1/inference-jobs")
public class InferenceJobController {

    private final InferenceJobService service;

    public InferenceJobController(InferenceJobService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<AcceptedJob> submit(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody InferenceJobRequest request,
            Authentication authentication) {

        String tenantId = tenantFromTrustedAuthentication(authentication);
        AcceptedJob accepted = service.submit(tenantId, key, request);

        URI statusUri = URI.create(accepted.statusUrl());
        return ResponseEntity.accepted()
                .location(statusUri)
                .body(accepted);
    }

    private String tenantFromTrustedAuthentication(
            Authentication authentication) {
        // Resolve tenant from verified identity/membership context.
        throw new UnsupportedOperationException("Application-specific");
    }
}
~~~

Service:

~~~java
@Service
public class InferenceJobService {

    private final InferenceJobRepository jobs;
    private final OutboxRepository outbox;
    private final RequestHasher hasher;
    private final JobIdGenerator ids;

    public InferenceJobService(
            InferenceJobRepository jobs,
            OutboxRepository outbox,
            RequestHasher hasher,
            JobIdGenerator ids) {
        this.jobs = jobs;
        this.outbox = outbox;
        this.hasher = hasher;
        this.ids = ids;
    }

    @Transactional
    public AcceptedJob submit(
            String tenantId,
            String idempotencyKey,
            InferenceJobRequest request) {

        validate(request);
        String requestHash = hasher.hashCanonical(request);

        var existing = jobs.findByTenantAndKey(
                tenantId, idempotencyKey);

        if (existing.isPresent()) {
            var job = existing.get();
            if (!job.requestHash().equals(requestHash)) {
                throw new IdempotencyConflictException();
            }
            return accepted(job.jobId(), job.status());
        }

        String jobId = ids.newId();
        jobs.insertQueued(
                jobId, tenantId, idempotencyKey,
                requestHash, request.task(), request.model(),
                request.objectRef());

        outbox.insertJobRequested(jobId, tenantId);

        return accepted(jobId, "QUEUED");
    }

    private void validate(InferenceJobRequest request) {
        if (request == null || request.task() == null
                || request.model() == null) {
            throw new IllegalArgumentException("Invalid request");
        }
    }

    private AcceptedJob accepted(String jobId, String status) {
        return new AcceptedJob(
                jobId,
                status,
                "/v1/inference-jobs/" + jobId);
    }
}
~~~

In production, also handle races when two submissions with the same idempotency key arrive concurrently: the unique constraint is the final arbiter. On an insert conflict, re-read the committed row, compare request hashes, and return either the existing job or `409`. Never rely solely on a `SELECT` before `INSERT`.

Tenant IDs must come from verified identity and membership checks—never trust a `tenantId` supplied by the caller in JSON.

## 8. Java Worker Calling the Model Provider

The worker receives a job ID, claims the job via a lease, reads authorized inputs, and calls the model provider. The HTTP client must enforce explicit timeouts and retry only transient errors per policy.

Example using the JDK `HttpClient`:

~~~java
public final class ModelApiClient {

    private final HttpClient client;
    private final URI endpoint;
    private final Duration requestTimeout;

    public ModelApiClient(
            URI endpoint,
            Duration connectTimeout,
            Duration requestTimeout) {
        this.endpoint = endpoint;
        this.requestTimeout = requestTimeout;
        this.client = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();
    }

    public HttpResponse<String> infer(
            String bearerToken,
            String jsonBody) throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(requestTimeout)
                .header("Authorization", "Bearer " + bearerToken)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Tokens should be retrieved from a secrets manager or workload identity credential flow. Never hardcode tokens in source code, container images, or environment files. Production code must parse responses, verify HTTP status codes, validate output schemas, and classify provider errors.

### Classifying Model API Errors

| Scenario | Recommended Action |
|---|---|
| `400` / invalid input | `FAILED`, do not retry the same payload |
| `401` / `403` | Halt and alert on credentials/IAM |
| `429` / rate limit | Backoff, jitter, and honor `Retry-After` |
| Transient `5xx` | Bounded retries |
| Connect/read timeout | Outcome may be unknown; check idempotency/provider request ID |
| Output fails schema validation | Validation failure, or bounded retry if the contract permits |
| Content/policy refusal | Record outcome per contract; do not retry blindly |

Model APIs may bill you even if the client times out or the worker terminates after the provider started processing. If the provider supports request idempotency keys or operation status lookups, use them. Otherwise, store the provider request ID and attempt state to reconcile before re-sending a request that could incur a second charge.

## 9. Orchestrating Multi-Step Tasks

An AI job may consist of multiple stages:

1. Fetch the document from object storage.
2. Validate file type and scan for malware.
3. Extract text / run OCR.
4. Chunk text and generate embeddings.
5. Call a model to summarize or classify.
6. Validate outputs against schemas and business rules.
7. Persist results and notify the caller.

Three common orchestration approaches:

### Queue and Worker

Fits when each message represents an independent unit of work processed competitively by workers without complex state machines. Queues handle buffering, delivery, and retries; the database holds business state.

### Workflow Orchestration

Fits when there are multiple sequential steps, branches, waits, callbacks, per-step retries, timeouts, and compensations. A workflow engine maintains orchestration state and invokes functions or services step by step.

### Event Choreography

Each service emits an event upon completion and downstream services react. Fits when steps are loosely coupled and eventual consistency is acceptable. Requires correlation IDs, explicit event contracts, and end-to-end observability.

| Requirement | Suitable Pattern |
|---|---|
| Single independent background job | Queue + worker |
| Multi-step sequence with branching | Workflow / state machine |
| Multiple services reacting to domain events | Event choreography |
| Fan-out across many independent documents | Queue / parallel map with concurrency caps |
| Waiting for human approval | Workflow with human task / callback |

Do not build a makeshift workflow engine by having functions call each other over HTTP when the platform provides a suitable durable orchestrator.

## 10. Fan-Out, Batching, and Concurrency Limits

For multi-document jobs, the API can create a parent job and fan out into child tasks, each processing one document or small batch.

Define:

- Maximum child jobs per parent job.
- Batch sizes and payload limits.
- Per-tenant and global concurrency caps.
- Model provider quotas by requests/tokens.
- Database write capacity.
- Ordering rules if child outputs depend on one another.
- Aggregation rules for parent job status and outputs.

Never allow one large request to spawn tens of thousands of unbounded invocations. Use admission control, queues, and quotas to protect providers and databases.

A parent job reaches `SUCCEEDED` only when all mandatory child tasks complete per policy. If some children fail, the state may be `PARTIALLY_SUCCEEDED` or `FAILED` depending on the contract; never silently ignore failed child tasks.

## 11. Streaming Responses for Inference

Chat experiences often stream tokens so users see content appear progressively. You can use Server-Sent Events (SSE), WebSockets, or streaming HTTP responses when supported by the API gateway, runtime, and model provider.

Streaming is suitable when:

- The caller keeps a connection open.
- The model emits output incrementally.
- Total duration remains within gateway and runtime limits.
- Clients implement clear disconnect and resume semantics.

Streaming is not equivalent to a durable background job. If the client disconnects, the function may be cancelled or continue running depending on the platform. Decide explicitly whether inference continues, whether outputs are saved, and whether callers can query results afterward.

For long tasks, you can combine both: the API creates a job, the client subscribes to an event stream for progress updates, and the database remains the authoritative source of state. If the stream drops, the caller reconnects and reads status/results from the API.

## 12. Callbacks and Webhooks on Job Completion

Instead of polling continuously, callers can register a callback URL. When the job finishes, the system sends a webhook notification.

Webhooks must implement:

- Cryptographic signatures or strong authentication.
- Timestamps and replay protection.
- Stable event IDs.
- Retry policies and timeouts.
- Receiver-side idempotency.
- Domain allowlists or SSRF controls when accepting callback URLs.
- Secret rotation and endpoint verification procedures.

Never call arbitrary caller-supplied callback URLs without SSRF protections. Allow HTTPS only, block private/link-local/metadata IPs per policy, inspect DNS resolution and redirects, or require pre-registered endpoints.

Webhook deliveries can repeat. Receivers must deduplicate event IDs and return `2xx` only after durably persisting the event. Avoid sending sensitive payloads directly when you can send an event reference and require the caller to fetch details via an authorized API.

## 13. Retries, DLQs, and Failed Job Handling

Workers can fail due to provider rate limits, timeouts, network errors, quotas, or output validation failures. Classify errors:

- **Retryable:** throttling, transient `5xx`, network interruptions.
- **Permanent:** invalid inputs, disallowed models, authorization failures.
- **Ambiguous:** the provider may have processed the request, but the response was lost.
- **Business/policy outcomes:** model refusals or outputs failing business constraints.

Use capped exponential backoff with jitter. Enforce maximum attempts, maximum elapsed time, and job deadlines. For longer retry delays, transition to `RETRY_WAIT` and schedule the next attempt rather than keeping a function alive and sleeping.

DLQs hold job events that exhausted retry budgets for investigation. Redrives must preserve the original job ID and idempotency identity. If the provider completed the request before the worker crashed, reconcile state first to avoid calling and paying for the model twice.

## 14. Job Cancellation and Deadlines

Callers may cancel a job when results are no longer needed. The API can expose:

~~~http
POST /v1/inference-jobs/job-918/cancel
Authorization: Bearer <access-token>
~~~

Cancellation is best-effort. If a worker is mid-request with a provider, aborting depends on HTTP client and provider cancellation support. An inference already started may be unstoppable and still incur charges.

Design:

- Transition state to `CANCEL_REQUESTED` via conditional update.
- Have workers check cancellation flags before starting the next step and before persisting results.
- If the provider supports an async cancel endpoint, invoke it.
- Record clear outcomes when the provider cannot cancel an in-flight call.
- Never mark `CANCELLED` while side effects or inference may still be running unconfirmed.
- Move expired-deadline jobs to terminal states or reconciliation.

Every job should have an absolute deadline. Workers must not start a new step if remaining time is insufficient for expected timeouts and cleanup.

## 15. Securing Inputs, Prompts, and Model Outputs

Model inputs may contain personal data, internal documents, source code, or malicious content. Model outputs are also untrusted data until validated.

Principles:

- Authenticate callers and authorize access per tenant, job, and object.
- Derive tenant context strictly from trusted identity claims.
- Verify read permissions on `objectRef` before workers download files.
- Never let callers specify arbitrary models; enforce model alias allowlists and policies.
- Cap input sizes, file types, token budgets, and output sizes.
- Redact sensitive data before sending to external providers if required.
- Never log secrets or internal system prompts.
- Treat prompt injection inside documents as untrusted input.
- Never blindly execute model-generated code, SQL, URLs, or tool calls.
- Validate outputs against strict schemas and business rules.
- Require human approval for high-impact actions.

Prompt instructions are not a security boundary. Authorization for tool invocations, database access, or sending emails must be enforced in code/service layers independently of model output.

## 16. Model Management, Prompts, and Reproducibility

AI outputs vary across model versions, prompt templates, decoding parameters, and provider updates. To investigate or reproduce results, persist metadata:

- Model alias and resolved model version/provider revision if available.
- Prompt template ID and version.
- Input schema version.
- Temperature, top-p, max tokens, and related parameters.
- Provider request ID.
- Token usage and latency.
- Safety/policy outcomes.
- Application code release ID.
- Execution timestamp.

You do not always need to retain full prompts and responses if sensitivity or retention policies prohibit it. Store hashes, redacted metadata, and access-controlled object references instead.

If a model alias automatically resolves to newer versions, record the exact resolved model on the job record. For queued jobs, decide whether to pin the version at submission time or resolve at execution time; never let behavior shift implicitly without an explicit contract.

## 17. Quotas, Rate Limits, and Admission Control

AI providers enforce quotas by requests/second, tokens/second, model, project, or account. Rapid function scale-out can breach provider quotas even before internal APIs hit max concurrency.

Control load across multiple layers:

- Per-user and per-tenant request rates.
- Global request rates per provider and model.
- Token budgets per tenant or task type.
- Maximum queued jobs and queue age limits.
- Maximum worker concurrency.
- Per-model concurrency caps.
- Maximum input and output tokens.
- Daily/monthly spend limits or budget alerts.

Use token buckets or distributed rate limiters. When a provider returns `429`, workers back off while queues hold pending jobs. Prevent fleets of workers from retrying simultaneously.

Return `429` when a caller exceeds their quota; return `503` or an explicit queued status when the system temporarily sheds load per contract. Never accept unbounded work that pushes queue backlogs past retention or budgets.

## 18. Multi-Tenant Isolation

Every job must belong to a tenant/caller scope. When reading status or results, the API must authorize access to that specific job; knowing a `jobId` never implies permission to read it.

Controls:

- Tenant-scoped unique idempotency keys.
- `tenant_id` columns and supporting indexes on job rows.
- All status and result queries filtered by tenant.
- Tenant-scoped object storage paths or metadata.
- Workers restricted to reading inputs and secrets belonging to authorized workloads.
- Callback endpoints bound to specific tenants and owners.
- Per-tenant quota and cost attribution.
- Logs and traces isolated so payloads never leak across tenants.

Never trust `tenantId` inside an event payload if the event could originate from an untrusted source. Producers or gateways must sign/authenticate context; workers verify source identity and object permissions before processing.

## 19. End-to-End Observability

A single job can cross the API, outbox dispatcher, queue, worker, model provider, and callbacks. Use distinct identifiers for distinct purposes:

- `requestId`: a single HTTP request.
- `jobId`: a business job.
- `eventId`: a single message/event.
- `traceId`: a distributed trace.
- `providerRequestId`: a request sent to the model provider.

Propagate trace context across message attributes when supported by the broker. Attach `jobId` and release/model version to structured logs and traces. Never use high-cardinality IDs as metric labels.

Key metrics:

- Jobs accepted, queued, running, succeeded, failed, and cancelled.
- Queue age and wait time before worker pickup.
- End-to-end completion latency.
- Model API latency, `429`s, `5xx`s, and timeouts.
- Retry counts and DLQ depth.
- Input/output token counts and estimated cost.
- Per-tenant quota rejections.
- Expired job leases and stuck `RUNNING` jobs.
- Callback delivery successes and failures.
- Cost per successful job.

Dashboards should break down queue wait time, preprocessing, model inference, post-processing, and callback delivery. Measuring total duration alone hides whether bottlenecks sit in the queue or at the provider.

## 20. Cost and Unit Economics

Inference costs extend well beyond Java function compute. Total cost can include:

~~~text
Total job cost =
  API/function compute
  + queue/event operations
  + model input/output tokens or provider compute
  + storage and data transfer
  + logs, metrics and traces
  + retry and duplicate attempts
  + workflow/orchestration charges
~~~

Model providers may bill per input token, output token, image/audio unit, model compute time, or provisioned throughput. Worker retries after timeouts can incur model charges even when the job never recorded a result.

Track:

- Cost per submitted job.
- Cost per successful job.
- Input/output tokens per task type.
- Retry waste and duplicate inference costs.
- Storage bytes and retention costs.
- Costs segmented by model, tenant, and business unit.
- Percentage of jobs failing after already consuming tokens.

Use smaller, faster models for simple tasks, cap `max_output_tokens`, trim unnecessary context, cache results where semantics permit, and batch embeddings if supported by the provider. Never share caches across tenants for sensitive outputs or when prompts/contexts alter results.

## 21. Testing APIs and Workflows

Test both API contracts and background task failure windows.

| Scenario | Expected Outcome |
|---|---|
| Valid synchronous request | Returns result within latency contract |
| Long-running request | Returns `202` after job and outbox commit |
| Same idempotency key, same payload | Returns the same `jobId` |
| Same key, different payload | `409 Conflict` |
| DB commit succeeds, queue publish fails | Outbox dispatcher publishes on retry |
| Queue delivers duplicate message | Worker produces no duplicate side effects |
| Worker crashes after provider response | Reconciliation/idempotency resolves unknown outcome |
| Provider `429` | Backs off and respects quotas |
| Provider `5xx` | Bounded retries |
| Provider `401`/`403` | Stops retrying and alerts on configuration |
| Job exceeds deadline | Transitions to terminal state or reconciliation |
| Caller reads another tenant's job | `403` or `404` per security contract |
| Webhook callback delivered twice | Receiver deduplicates event ID |
| Cancellation during `RUNNING` | Best-effort cancel and valid state transition |
| Model output fails schema check | Never saved as a successful result |
| Growing queue backlog | Admission and concurrency controls protect the provider |

Use a fake model provider for unit and integration tests to control latency, HTTP statuses, and outputs. Run bounded contract tests against real providers without sensitive data and under strict budget caps.

## 22. Common Design Pitfalls

- **Holding HTTP requests open for long tasks:** causes timeouts and wastes concurrency; move to background jobs.
- **Returning `202` before durable job persistence:** restarts can lose work; commit job and outbox first.
- **Publishing to queues and writing to the DB separately:** causes dual-write inconsistencies; use a transactional outbox.
- **Skipping idempotency:** caller retries spawn duplicate jobs; enforce keys and request hashes.
- **Treating `jobId` as authorization:** leaks results across tenants; check permissions on every read.
- **Workers without leases:** multiple workers process the same job; use conditional claims and fencing.
- **Retrying every model API error:** wastes tokens and amplifies load; classify errors carefully.
- **Ignoring timeout unknown outcomes:** the provider may have processed the call; persist provider request IDs and reconcile.
- **Unbounded tokens and concurrency:** bills spike and quotas break; enforce admission control.
- **Using model aliases without logging resolved versions:** hinders debugging output changes; record model metadata.
- **Treating prompts as security boundaries:** models are vulnerable to prompt injection; enforce permissions in code.
- **Logging full prompts and responses:** risks data leaks; redact and enforce retention.
- **Aggressive polling:** inflates API and database costs; use `Retry-After`, backoff, or callbacks.
- **Marking jobs `CANCELLED` immediately:** workers or providers may still be running; use `CANCEL_REQUESTED` and confirm.
- **Ignoring queue age:** jobs stall even while worker invocations look healthy; measure end-to-end latency.

## 23. Step-by-Step Build Process for Serverless Java AI Inference

1. Define task types, latency budgets, and input/output contracts.
2. Choose synchronous vs. asynchronous execution based on runtime and caller UX.
3. Design APIs, authentication, tenant authorization, and idempotency.
4. For async flows, persist jobs and outbox records in the same transaction before returning `202`.
5. Design the state machine, leases, deadlines, retries, and cancellation.
6. Route job events to a queue or workflow engine.
7. Bound worker concurrency to provider quotas and downstream capacity.
8. Call models using an HTTP client with timeouts, managed credentials, and error classification.
9. Validate outputs, store results securely, and record model/prompt versions.
10. Use callbacks or status polling to deliver results to callers.
11. Protect data, prompts, tool access, and object references per tenant.
12. Instrument traces, queue age, token usage, retries, DLQs, and cost per successful job.
13. Test duplicates, timeouts, provider `429`/`5xx`, crashes, and DLQ redrives.
14. Canary deploy, monitor latency and cost, and tune quotas.
15. Periodically review model versions, retention, spend limits, and policies.

## 24. Key Takeaways

Synchronous AI inference fits short requests with tight latency budgets. Long-running or multi-step tasks should be accepted as durable jobs returning `202` with a `jobId`, then executed via queues or workflows. A job database holds authoritative state, while a transactional outbox guarantees dispatch intents are never lost between the database and the broker.

Workers require leases, idempotency, timeouts, bounded retries, and handling for unknown provider outcomes. Status and result APIs must enforce tenant authorization. Both prompts and model outputs are untrusted data; tool permissions and data access must be enforced in application code.

Monitor queue wait times, inference latency, token usage, retries, DLQs, and cost per successful job. A solid architecture keeps APIs responsive, scales workers with demand, recovers cleanly from failures, and keeps AI spend predictable as job volume grows.
