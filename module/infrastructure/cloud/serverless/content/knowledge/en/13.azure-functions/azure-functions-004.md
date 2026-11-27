# Handling Timer, Storage Queue, and Blob triggers

Azure Functions can run a Java function on a schedule, when a message appears in a queue, or when a blob is created or updated. These three triggers address different kinds of work: Timer for periodic tasks; Storage Queue for asynchronous processing and decoupling producers/consumers; Blob for data processing when files arrive in storage.

Combined, an application can automatically execute scheduled tasks, consume work from queues, and process new files without maintaining an always-running Java process. However, each trigger has distinct semantics for scheduling, retries, ordering, concurrency, and state storage. Proper design must account for a function being invoked repeatedly, running concurrently across multiple instances, or failing after producing a side effect.

In the **CLOUD_SERVERLESS** module, learners build and deploy Java functions triggered by HTTP, messages, or events, while handling state, access permissions, retries, idempotency, scaling, and cost. This lesson focuses on these three Azure Functions triggers and how to operate them in a Java application.

## 1. Overview of the three trigger types

| Trigger | Triggering event | Suitable workloads | Key characteristics |
|---|---|---|---|
| Timer trigger | Scheduled time per NCRONTAB expression | Periodic reports, cleanup, data sync, maintenance tasks | Host coordinates the schedule; requires storage to manage locks and schedule status |
| Storage Queue trigger | Message arrives in Azure Queue Storage | Order processing, sending emails, background jobs, system integration | Consumer receives, processes, then deletes the message; errors can lead to redelivery and poison queues |
| Blob trigger | Blob created or updated in a container | Image resizing, file parsing, data ingestion, thumbnail generation | Detects blob changes via polling or an event-based mechanism depending on configuration |

Distinguish triggers from bindings:

- **Trigger** determines when the function is invoked and supplies trigger data.
- **Input binding** helps the function read data from a service without writing all connection code manually.
- **Output binding** helps the function write data to a destination service.
- **Azure SDK** enables finer control over queries, streaming, transactions, metadata, and retries.

A function has exactly one trigger. A function can have additional input/output bindings or use the SDK directly to interact with multiple services. Triggers do not automatically guarantee exactly-once business execution; consumers still require idempotency and error handling.

## 2. Java programming model and declaring triggers

In Java, functions are typically declared using annotations such as FunctionName, TimerTrigger, QueueTrigger, and BlobTrigger. The Azure Functions host manages the trigger, monitors the event source, and calls the Java method with bound parameters.

A function method typically accepts:

- A trigger parameter containing timer information, queue message, or blob content.
- Additional binding parameters if the function needs extra data.
- ExecutionContext to log messages and retrieve invocation context.

General structure example:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;

public class ExampleFunction {
    @FunctionName("Example")
    public void run(
            final ExecutionContext context) {
        context.getLogger().info("Function invoked");
    }
}
~~~

The function name is the identifier used by the host. Do not treat the Java method name as the trigger name or queue name; these values are declared in annotations and application configuration.

Examples in this lesson use the annotation package from the Azure Functions Java library. Dependencies, the Azure Functions Maven plugin version, Java runtime, and extension bundles must align with the guidelines for the Azure Functions version being deployed.

## 3. Timer trigger: running functions on a schedule

A Timer trigger invokes a function according to an NCRONTAB schedule expression. It suits tasks with deterministic execution times, such as:

- Aggregating metrics hourly.
- Generating start-of-day reports.
- Cleaning up temporary data or expired records.
- Periodically syncing data from external systems.
- Checking a business condition at regular intervals.

Java example running every five minutes:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.TimerTrigger;

public class MaintenanceFunction {
    @FunctionName("MaintenanceTimer")
    public void run(
            @TimerTrigger(
                name = "timerInfo",
                schedule = "0 */5 * * * *"
            ) String timerInfo,
            final ExecutionContext context) {

        context.getLogger().info(
                "Maintenance timer fired. Timer info: " + timerInfo);

        performMaintenance();
    }

    private void performMaintenance() {
        // Call the business service; the operation must be safe to re-run.
    }
}
~~~

The expression above means running at second 0 of every minute divisible by 5. Timer schedules in Azure Functions use a six-field NCRONTAB format in order:

| Field | Typical range | Example |
|---|---|---|
| Seconds | 0–59 | 0 |
| Minutes | 0–59 | */5 |
| Hours | 0–23 | 8 |
| Day | 1–31 | * |
| Month | 1–12 | * |
| Day of week | 0–6 or day names depending on parser | * |

Examples:

| Expression | Meaning |
|---|---|
| 0 */5 * * * * | Every 5 minutes, at second 0 |
| 0 0 * * * * | Every hour, at minute 0 |
| 0 30 8 * * * | Every day at 08:30 |
| 0 0 0 * * 1 | Every Monday at 00:00 |
| 0 0 9 1 * * | First day of every month at 09:00 |

Validate expressions using an NCRONTAB parser or suitable tool before deploying. Azure Functions' six fields differ from standard five-field Linux cron; copying a five-field cron schedule can produce the wrong schedule.

### Putting schedules in application settings

Avoid hardcoding production schedules if schedules may vary across environments. You can reference an application setting using percent signs:

~~~java
@TimerTrigger(
    name = "timerInfo",
    schedule = "%MaintenanceSchedule%"
) String timerInfo
~~~

In local.settings.json for local development:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "MaintenanceSchedule": "0 */5 * * * *"
  }
}
~~~

Local settings are strictly for development and should never have real connection strings or secrets committed to the repository. In Azure, the corresponding configuration lives in Application Settings or the configuration/secret mechanism used by the organization.

### Time zones and execution schedules

Timer schedules are interpreted in UTC by default. This keeps schedules independent of host location, though it may differ from local time when deploying across multiple Regions.

If business logic requires local time, check WEBSITE_TIME_ZONE support for your operating system and hosting plan. Support varies between Windows and Linux, especially on the Consumption plan. For financially critical or SLA-bound schedules, the safest practice is storing and calculating timestamps in UTC, while explicitly handling daylight saving time transitions if the business uses such a timezone.

### Singleton lock and schedule monitoring

Timer triggers use a storage-based locking mechanism to ensure only one instance of the function handles a schedule at a time when an app scales out. Host storage is also used to track schedule status, preventing every instance from independently running the same schedule.

Therefore:

- Host storage configuration must be available and have appropriate access permissions.
- Do not arbitrarily delete or alter internal data used by the host to manage timers.
- When scaling across multiple instances, do not create a separate in-instance timer to replace Timer trigger.
- Observe schedule status and host logs if an execution is delayed or missed.

Timer trigger is not a durable workflow engine. If a task is long-running, multi-step, awaits callbacks, or needs complex retries, have the Timer trigger start a workflow or enqueue work instead of keeping an invocation open too long.

### runOnStartup and useMonitor

TimerTrigger has options like runOnStartup and useMonitor depending on the binding/runtime version. runOnStartup can cause the function to run when the host starts or restarts, outside the regular schedule. In production, avoid enabling this option without a clear reason, as scaling, deployments, or restarts can trigger unexpected extra runs.

useMonitor controls saving/monitoring schedule state. For critical schedules, understand defaults by interval and your specific runtime configuration. Do not disable schedule monitoring merely to reduce storage activity if doing so increases the risk of missed or incorrect runs.

## 4. Storage Queue trigger: asynchronous message processing

Azure Queue Storage is a simple message queue for decoupling producers from consumers. Producers write messages to the queue; the Azure Functions host monitors the queue and invokes the function when messages are ready to process.

Queue triggers fit when:

- An API needs to respond quickly while business work can complete later.
- Many independent tasks need to be distributed across consumers.
- You want to absorb bursts via a backlog rather than pushing all load directly onto a database.
- Messages need to be retried when a dependent service temporarily fails.
- Producer and worker lifecycles should be decoupled.

Java example receiving messages from a queue:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.QueueTrigger;

public class OrderQueueFunction {
    @FunctionName("ProcessOrderMessage")
    public void run(
            @QueueTrigger(
                name = "message",
                queueName = "orders-in",
                connection = "AzureWebJobsStorage"
            ) String message,
            final ExecutionContext context) {

        context.getLogger().info("Received order message");
        processOrderMessage(message);
    }

    private void processOrderMessage(String message) {
        // Parse, validate, call the business service, and commit the result.
    }
}
~~~

The connection attribute references an application connection setting, not a connection string written directly in the annotation. Queue names must follow Azure Queue Storage naming rules, typically lowercase letters, numbers, and hyphens.

### Message lifecycle and acknowledgement

With Azure Queue Storage, the host dequeues a message and the message becomes temporarily invisible to other consumers for the visibility timeout duration. When the function completes successfully, the host deletes the message from the queue. If the function fails or does not complete per host semantics, the message may reappear after the visibility timeout to be redelivered.

Consequently, queue triggers exhibit at-least-once delivery semantics under failure/timeout conditions. A message can be reprocessed if:

- The function committed to the database before the host deleted the message.
- The invocation timed out or the process terminated.
- A network error occurred while the host acknowledged processing.
- Message visibility expired while the previous attempt was still running.

Never assume each message is invoked only once. Design idempotent consumers and persist event/message IDs to detect duplicate processing.

### Dequeue count and poison queues

Each time a message is retrieved for processing, its dequeue count increments. If the function repeatedly fails, the host retries the message according to queue trigger mechanics. After exceeding maxDequeueCount, the message is moved to a poison queue so it stops blocking the main flow.

For a queue named orders-in, the default poison queue is named orders-in-poison. This is where messages that cannot be processed normally are investigated. Never automatically delete poison messages without capturing needed information and identifying the root cause.

Queue behavior can be configured in host.json:

~~~json
{
  "version": "2.0",
  "extensions": {
    "queues": {
      "batchSize": 16,
      "newBatchThreshold": 8,
      "maxDequeueCount": 5,
      "visibilityTimeout": "00:00:30"
    }
  }
}
~~~

Meaning:

- batchSize: number of messages the host fetches in one batch per the queue listener mechanism.
- newBatchThreshold: threshold at which the host fetches the next batch as in-flight message count drops.
- maxDequeueCount: maximum dequeue attempts before a message moves to the poison queue.
- visibilityTimeout: wait duration before a failed message becomes visible again for retry.

These values are illustrative configuration examples, not universal optimal numbers for all workloads. Defaults and limits may depend on the extension version. Verify with the Azure Storage Queues extension you are using.

### Concurrency and backpressure

batchSize and newBatchThreshold affect how many messages are processed concurrently per host instance. During scale-out, total concurrency can grow with the number of instances. Thus, even a small per-instance batch setting can create high application-wide concurrency if the host scales to many instances.

Coordinate:

- Function or hosting plan concurrency limits if available.
- Batch size and maximum instance count.
- Connection pools and database limits.
- Downstream API rate limits.
- Processing duration and visibility timeout.
- Backlog depth, oldest message age, and retry rate.

If the database can only handle 30 concurrent operations, do not allow queue consumers to open hundreds of concurrent invocations. Increasing concurrency only drains a backlog faster if dependencies can sustain that load; otherwise, it drives up timeouts and retries.

## 5. Blob trigger: processing new or updated blobs

Azure Blob Storage stores objects in containers. A Blob trigger invokes a function when a blob matching a path is created or updated. It is a natural fit for file-processing pipelines such as:

- Resizing images or generating thumbnails.
- Scanning uploaded files for viruses.
- Extracting text from PDFs.
- Transforming CSV/JSON into normalized data.
- Generating previews or metadata for videos/documents.
- Ingesting data into databases or data lakes.

Java example receiving binary blob content:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.BindingName;
import com.microsoft.azure.functions.annotation.BlobTrigger;
import com.microsoft.azure.functions.annotation.FunctionName;

public class ImageBlobFunction {
    @FunctionName("ProcessUploadedImage")
    public void run(
            @BlobTrigger(
                name = "content",
                path = "incoming-images/{name}",
                dataType = "binary",
                connection = "AzureWebJobsStorage"
            ) byte[] content,
            @BindingName("name") String blobName,
            final ExecutionContext context) {

        context.getLogger().info("Processing blob: " + blobName);
        processImage(blobName, content);
    }

    private void processImage(String name, byte[] content) {
        // Validate type/size, process, and write the result.
    }
}
~~~

Path incoming-images/{name} monitors blobs in the incoming-images container; the {name} segment binds to the parameter with the matching BindingName. For binary files, byte[] is convenient for small files but loads the entire content into memory. For large files, avoid loading the entire blob into a byte array by default.

### Blob paths and binding data

Paths can specify a container name and a pattern to capture the blob name or part of the path. Examples:

| Path | Meaning |
|---|---|
| incoming/{name} | Every blob in the incoming container |
| incoming/images/{name} | Blobs under the logical images folder of the incoming container |
| incoming/{name}.csv | Blobs ending in .csv per binding-supported patterns |

Blob Storage allows `/` in blob names to simulate directories; these are not physical directories like a filesystem. Check how binding patterns handle nested paths and names with special characters.

### Polling and event-based detection

A Blob trigger can detect changes via scan/polling or via Event Grid depending on configuration, extension, and hosting environment.

- **Polling:** the host checks storage for changes and uses tracking info/receipts to determine which blobs need processing. This approach can have detection latency depending on scanning mechanics and load.
- **Event Grid-based:** Storage emits an event when a blob is created or updated; Event Grid delivers the event to the integration/trigger. This typically lowers detection latency but requires configuring an event subscription, permissions, and an appropriate endpoint.

Do not assume every Blob trigger uses Event Grid by default. Check the extension/runtime documentation and deployed source configuration. If near-real-time response is needed, confirm the event subscription works and test Event Grid retries and delivery.

### Blob receipts and reprocessing

The host uses receipts or tracking metadata to know which blobs have been processed. When a blob is updated, a new version/ETag can cause the trigger to treat it as a change requiring reprocessing. Receipts do not replace business-layer idempotency: a function can still perform a side effect and fail before the host records completion.

If blob processing can be re-triggered, store the ETag, version ID, or a stable operation key alongside business state. Before writing results, check whether that version was already processed.

### Avoid loading entire large files into the heap

The byte[] example above fits small files. For large files, use the Azure Storage SDK to open a stream or download in controlled chunks. This bounds memory usage, processes incrementally, and avoids OutOfMemoryError when multiple blobs process concurrently.

Reference pattern:

~~~java
try (InputStream input = openBlobStream(blobName)) {
    processInChunks(input);
}
~~~

The openBlobStream and processInChunks methods are application abstractions. When using the SDK, clearly define container read permissions, timeouts, retries, stream closure, and how to handle a blob deleted mid-run.

### Poison blobs and recurring errors

Blob triggers can retry when a function fails. With polling-based Blob triggers, the runtime can write failed blob details to a dedicated poison queue after the retry threshold; the common queue name is webjobs-blobtrigger-poison. Exact behavior and configuration depend on trigger source, extension, and runtime version. When using Event Grid, also review Event Grid subscription retries and dead-lettering.

Do not treat a blob appearing in the poison queue as finished processing. Retain the blob path, ETag/version, timestamp, sanitized exception, and function version for investigation. When fixing the file or code and re-running, control which version is replayed and avoid creating duplicate results.

## 6. Comparing Timer, Queue, and Blob triggers

| Criterion | Timer | Storage Queue | Blob |
|---|---|---|---|
| Trigger source | Time schedule | Message in queue | Blob created/updated |
| Load pattern | Schedule-driven | Backlog and message rate driven | Upload/file-change rate driven |
| Input data | Timer information and schedule status | Message body, metadata | Blob content, name, and metadata |
| Retry | Per runtime/function policy; requires explicit design | Redelivered per visibility/dequeue count, poison queue | Per trigger source/runtime; may have poison handling |
| Ordering | By scheduled time, not business event order | Do not assume strict FIFO | No processing order guarantee across multiple blobs |
| Idempotency key | Schedule occurrence/business date | Message ID or event ID | Blob URI + ETag/version |
| State storage | Host storage and business store | Queue and business database | Blob storage, receipts, and business database |
| Typical use cases | Cleanup, reporting, reconciliation | Background tasks and decoupling | File processing and data ingestion |

All three triggers can be combined in a single pipeline:

1. A user uploads a file to the incoming container.
2. A Blob trigger validates metadata and enqueues a work item to a queue.
3. A Queue trigger processes the file, extracts data, and updates the database.
4. A Timer trigger runs periodically to find stuck jobs or reconcile state.
5. When a message cannot be processed, the poison queue retains it for investigation and redrive.

This combination separates file detection, work coordination, and periodic reconciliation into distinct steps. Each function can scale according to its trigger's characteristics.

## 7. Idempotency and business state

All three triggers can cause a task to re-run or overlap. Idempotency means executing the same operation again with the same identifier produces no unintended extra business effects.

### Timer trigger

Use a key representing the business run, such as report-date or schedule-occurrence. Before generating a report, record that key in the database with a unique constraint. If the previous run already completed, a subsequent invocation can skip or update according to policy.

Do not rely solely on current timestamp as the key, because two invocations could run at different seconds for the same reporting period. Normalize the business period, e.g., report date in UTC or business timezone.

### Queue trigger

Messages should contain a messageId/eventId or business operation ID. Store processed status in the database and update status together with side effects in a single transaction where possible. When calling external APIs, pass an idempotency key downstream or use outbox/inbox to prevent duplicate side effects.

### Blob trigger

Use the blob URI together with its ETag or version ID to identify specific content. The same blob name with a different ETag may be new content needing processing. Never use filename alone as an idempotency key if files can be overwritten.

A processed_operations table might store:

| Field | Purpose |
|---|---|
| operation_id | Unique idempotency key |
| source_type | TIMER, QUEUE, or BLOB |
| source_id | Message ID, blob URI/ETag, or schedule occurrence |
| status | STARTED, COMPLETED, FAILED |
| started_at / completed_at | Lifecycle tracking |
| result_reference | Reference to stored output |
| attempt_count | Application-level attempt counter |

Design for the case where a function crashes after committing side effects but before the trigger host acknowledges success. A retry invocation must look up the operation ID and return the prior outcome instead of repeating the side effect.

## 8. Retries, timeouts, and error handling

Not all errors should be retried the same way.

| Error type | Example | Action |
|---|---|---|
| Transient | Database timeout, HTTP 503, temporary network glitch | Retry with limits, backoff, and jitter |
| Permanent data error | Invalid JSON, missing required field, unsupported blob format | Route to poison queue/quarantine or log error for data fix |
| Configuration | Invalid storage credentials, missing permissions, wrong queue name | Alert and fix configuration; avoid infinite retries |
| Business conflict | Order already canceled, disallowed state transition | Apply business rules; do not retry blindly |

For queues, messages are redelivered per visibility timeout when an invocation fails. If processing takes longer than the visibility timeout, the message can reappear while the first attempt is still running. Set an appropriate timeout, shorten processing time, or split work into smaller messages.

For Timer, a failure does not mean the schedule automatically re-runs immediately. Define function/runtime retry policies, alert on failed runs, and establish a backfill or reconciliation process if a scheduled period is missed.

For Blob, check the retry mechanics of the polling trigger or Event Grid. Event Grid can retry delivery per its own policy; configure dead-lettering on the subscription if no events may be lost. The function must also be idempotent since an event can be redelivered.

For long-running tasks, never hold a single invocation indefinitely. Break up the work, enqueue the next step, or use Durable Functions/workflows when durable orchestration is required.

## 9. Storage configuration and security

Timer, Queue, and Blob triggers require access to a storage account. In common configurations, the connection attribute in annotations references an application setting such as AzureWebJobsStorage or a custom setting.

Local development example:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "java"
  }
}
~~~

In Azure, consider managed identity and identity-based connections when supported by the extension/runtime. When doing so, grant the exact data-plane roles to the function:

- Queue triggers need permissions to read messages and delete messages after processing; output queues need permissions to send messages.
- Blob triggers need permissions to read blobs and metadata; functions writing blobs need corresponding write permissions.
- Timer needs storage permissions used by the host to manage locks and schedule monitoring.

Never grant subscription-wide Owner or Contributor just so a function can read a queue. Apply least privilege at the account/container/queue scope and verify the managed identity's permissions in the right subscription and storage account.

A connection string containing an account key is a secret. Never hardcode it in Java source, annotations, logs, or committed config files. Local settings should be protected; production secrets should be managed via Application Settings, Key Vault, or identity-based connections per your chosen architecture.

## 10. Observability and operations

A function can succeed from the runtime's perspective while failing in business logic—for example, a message is deleted while the database write was incorrect. Combine logs, metrics, and business state.

### Timer

Monitor:

- Scheduled time vs. actual execution time.
- Duration, success/failure, and late-run count.
- Schedule status and storage lock errors.
- Which business periods completed and which are missing.

Log the business period and invocation ID for reconciliation. Do not log only "Timer fired"—log the outcome of the scheduled job.

### Queue

Monitor:

- Remaining message count in the queue and oldest message age.
- Dequeue count, poison queue depth, and rate of movement into the poison queue.
- Function execution count, duration, failures, and retries.
- Consumer throughput, batch size, and concurrency.
- Downstream latency, throttling, and connection pool saturation.

If the backlog grows, determine whether consumers are slow, downstreams are bottlenecked, or concurrency is capped. Adding more instances will not solve the problem if the database is already overloaded.

### Blob

Monitor:

- New blob count and latency from upload to invocation.
- Blob trigger failures, retries, and poison records.
- Blob size, read/stream duration, and peak memory.
- Processed versions/ETags and output outcomes.
- Event Grid delivery failures/dead-letters if using an event-based source.

Logs should include a normalized blob URI, ETag/version, and correlation ID. Avoid logging SAS tokens or signed query strings if blob URLs carry credentials.

Application Insights and Azure Monitor can provide distributed tracing, dependency telemetry, and metrics. Propagate correlation IDs across HTTP requests, queue messages, blob processing, and Timer reconciliation steps.

## 11. Local development and testing

Java functions can be tested locally using Azure Functions Core Tools alongside Azurite for emulator-supported Azure Storage services.

Common steps:

1. Install a JDK and Maven matching the target Java runtime.
2. Install Azure Functions Core Tools.
3. Run Azurite to emulate Blob and Queue Storage.
4. Configure local.settings.json with development connection strings.
5. Start the function host locally and send messages/upload blobs/adjust timer schedules to test.
6. Inspect logs, retries, poison queues, and database results.
7. Deploy to an Azure test environment to verify real behavior, as emulators do not fully simulate scaling, identities, Event Grid, or all host behaviors.

Minimum test matrix:

| Trigger | Test case | Expected outcome |
|---|---|---|
| Timer | Valid schedule | Runs on time per configured UTC/timezone |
| Timer | Two host instances active simultaneously | Only one schedule execution per singleton coordination |
| Timer | Function fails mid-run | Logged/alerted; subsequent run creates no duplicate side effects |
| Queue | Valid message | Processed successfully and message deleted |
| Queue | Message repeatedly causes errors | Dequeue count increments and eventually moves to poison queue |
| Queue | Crash after database commit | Message may be redelivered but business effect is not duplicated |
| Queue | Large backlog | Concurrency stays within downstream capacity |
| Blob | New blob uploaded | Function receives exact blob name and content |
| Blob | Blob overwritten | New version/ETag processed according to policy |
| Blob | Large file | Streamed processing or bounded memory usage |
| Blob | Function fails | Retried/dead-lettered per source and runtime configuration |
| All | Storage credentials expired or missing permissions | Error clearly observed and alerted |

## 12. Choosing a trigger by requirement

| Requirement | Suitable trigger | Reason |
|---|---|---|
| Run a report at 02:00 daily | Timer | Recurring schedule is the primary activation condition |
| Send email after an order is created | Storage Queue | Decouples email sending from HTTP request and enables retries |
| Process an image right after upload | Blob | Event is tied to file content |
| Sync data every 15 minutes | Timer | Runs periodically; can enqueue batches |
| Process thousands of independent tasks | Storage Queue | Backlog absorbs bursts and distributes work across workers |
| Parse large CSV files | Blob + Queue | Blob stores the file; Queue coordinates jobs and metadata |
| Reconcile stuck jobs | Timer + database | Finds overdue states and initiates recovery steps |

Do not use a Timer to continuously poll a queue when a Queue trigger handles it directly. Nor should you stuff large files into queue messages; store files in Blob Storage and pass the blob URI, version, and needed metadata through the queue.

## 13. Example architecture combining all three triggers

Suppose an application receives invoices from users:

1. An HTTP API receives metadata and generates an upload reference.
2. The user uploads a PDF file into the incoming container.
3. A Blob trigger validates file type, size, and metadata, then creates a message containing the blob URI, ETag, and invoice ID.
4. A Queue trigger reads the message, streams the file, extracts data, and writes results to the database.
5. If the file is invalid, the consumer logs the error and lets the message move to the poison queue per policy.
6. A Timer trigger runs hourly to find invoices stuck in PROCESSING too long, reconciles against the queue/poison queue, and creates recovery tasks.
7. A dashboard displays pending files, completed files, errors, and processing durations.

Here the Blob trigger detects new data, the Queue trigger executes retryable work, and the Timer trigger handles periodic reconciliation. The database is the canonical source of business state; queues and triggers are the coordination mechanism.

## 14. Common pitfalls

| Pitfall | Consequence | Prevention |
|---|---|---|
| Using five-field cron for Timer trigger | Wrong execution schedule | Use Azure Functions' six-field NCRONTAB |
| Enabling runOnStartup unnecessarily | Extra function runs on host restart/scale | Keep default and enable only when impact is understood |
| Misconfiguring host storage | Timer lock or trigger fails to operate | Verify AzureWebJobsStorage and access permissions |
| Assuming queue delivers only once | Duplicate side effects | Enforce idempotency by message/event ID |
| Setting visibility timeout too short | Message redelivered while first attempt is still running | Configure timeout longer than processing time with safety margin |
| Not monitoring poison queues | Failed messages are forgotten | Alert on poison queue depth and oldest message age |
| Loading large files into byte[] | Heap spikes or OOM | Stream blobs using the SDK |
| Using blob name alone as idempotency key | Fails to distinguish new content on overwrite | Combine URI with ETag/version |
| Assuming Blob trigger always uses Event Grid | Unexpected latency and retry behavior | Verify source and extension configuration |
| Increasing concurrency without checking database | Downstream overload | Bound batch size, concurrency, and connection pools |
| Logging connection strings or SAS URLs | Credential exposure | Redact secrets and query signatures |
| Using triggers as a workflow engine | Hard to manage long steps, callbacks, and compensation | Use Durable Functions/workflows for complex orchestration |

## 15. Pre-production checklist

- **Timer:** schedule uses valid six-field NCRONTAB, timezone is defined, schedule monitoring and host storage are operational.
- **Queue:** queue name and connection are correct; batch size, visibility timeout, maxDequeueCount, and poison queue are intentionally configured.
- **Blob:** container/path are correct; polling or Event Grid chosen appropriately; large files are streamed with a version/ETag strategy.
- **Java runtime:** annotations, binding extensions, and runtime versions are compatible; dependencies are packaged properly.
- **Idempotency:** every schedule occurrence, message, and blob version has a stable operation key.
- **Retry:** transient/permanent/configuration errors are classified; retries are bounded with backoff.
- **Concurrency:** total invocations and batches are bounded to downstream database/API capacity.
- **Security:** managed identity or secrets are configured securely; roles grant only necessary permissions.
- **Observability:** logs, metrics, correlation IDs, and alerts exist for timer failures, queue backlogs, poison queues, and blob failures.
- **Recovery:** runbooks exist for investigating poison messages, redriving, handling failed blobs, and reconciling missed Timer periods.
- **Cost:** invocations, storage transactions, Event Grid, logging, networking, and function execution duration are estimated.

## 16. Conclusion

Timer triggers suit periodic tasks; Storage Queue triggers suit asynchronous work requiring producer/consumer decoupling and retries; Blob triggers suit file-processing pipelines when blobs are created or updated. In Java, triggers are declared via annotations and managed by the Azure Functions host, while business logic should reside in independently testable services.

Design according to the actual semantics of each source: Timer requires schedules and host storage coordination; Queue can redeliver and route to poison messages; Blob requires controlling versions, file sizes, and polling or Event Grid. Combining idempotency, bounded retries, appropriate concurrency, least-privilege access, and telemetry keeps functions reliable through scaling, restarts, and failures.
