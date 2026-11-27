# Designing Event-Driven File Processing Pipelines with Blob Events

In an Azure business system, files are often uploaded continuously: PDF invoices, product images, CSV reports, accounting records, or backups. If an application has to periodically scan entire directories for new files, processing lags, wastes redundant listing calls, and scales poorly during upload spikes. An **event-driven architecture** kicks off processing pipelines whenever Azure Blob Storage emits events for data objects.

For instance, when a user uploads an invoice to the **incoming** container, Azure Event Grid can receive the **Microsoft.Storage.BlobCreated** event and forward metadata to Azure Functions or a queue. A worker inspects the file, extracts data, saves results to **processed**, and updates job status. The uploading app does not have to block waiting for the entire pipeline to finish.

This lesson belongs to the **Object Storage with Blob Storage** chapter in the Microsoft Azure learning path: organizing resources with subscriptions/resource groups, designing virtual networks and Microsoft Entra ID, and deploying compute, storage, data, monitoring, security, and cost controls for application architectures.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Blob Storage**, **Blob events**, **Event Grid**, **Azure Functions**, and **queues** within a pipeline.
2. Design the end-to-end flow from file upload to processing, output storage, and completion notification.
3. Choose between direct Event Grid triggers and an Event Grid → Queue → Worker architecture.
4. Understand that events can duplicate, arrive out of order, retry, or arrive after the blob has changed.
5. Design **idempotency**, retries, dead-lettering, backpressure, and reliable job state tracking.
6. Configure event filters, permissions, private networking, monitoring, and acceptance criteria.
7. Read a Python Azure Functions example and verify the live flow in Azure Portal/Azure CLI.

## 1. Why Use Events Instead of Periodic Polling?

Suppose an application receives 20,000 images per day. Periodic polling has to list massive numbers of blobs, compare timestamps, and guess which files remain unprocessed. Another process scanning the same container adds load and risks duplicate processing.

With an event-driven model:

1. Client uploads a blob to Azure Storage.
2. Storage emits an object activity event per supported capabilities.
3. Event Grid filters and routes the event to a configured destination.
4. The consumer starts or enqueues the work item.
5. A worker reads the blob, runs security checks, processes it, and writes outputs/status.

| Criterion | Periodic polling | Event-driven triggering |
|---|---|---|
| Detecting new files | Depends on scan interval and comparison logic | Driven by event notifications as operations occur |
| Scan overhead | Repeatedly lists large numbers of objects | Processes only events matching filters |
| Latency | Bounded by schedule interval | Typically lowers detection latency, though not hard real-time |
| Loss/duplicate tolerance | Requires custom state tracking and reconciliation | Still requires retries, idempotency, and reconciliation |
| Operations | Must manage scan checkpoints | Must monitor delivery, queues, consumers, and processing errors |

**Event-driven does not mean "each blob is always processed exactly once."** Events can be redelivered; correctness must be enforced at the application layer.

## 2. Pipeline Components

### Azure Blob Storage

Blob Storage stores file payloads in a **Storage Account**, organized by **containers** and blob names. In our example, the team uses:

- **incoming**: newly uploaded files from users; treated as untrusted data.
- **processed**: output files or successfully processed results.
- **quarantine**: risky files or payloads failing security validation.
- **failed**: recorded error artifacts for investigation, if copies or failure reports are kept.

Separating containers makes permissions, lifecycle policies, and event filters clean. Separating containers **does not automatically isolate permissions** if applications still use an overly broad account key.

### Azure Event Grid

**Azure Event Grid** is an event routing service. An **Event Grid system topic** represents the Azure service event source, such as a Storage Account; an **event subscription** defines event types, filters, and the destination endpoint.

Destinations can include Azure Functions, webhooks, queues, or compatible processing services depending on endpoint type and supported features. Event Grid carries **operation metadata**, not the entire file payload inside the event.

### Azure Functions

**Azure Functions** executes code on triggers such as an Event Grid trigger or a queue trigger. One function can stay minimal: validating the event and enqueueing work metadata. Another worker function handles heavier file processing with independent retries and scaling.

### Queues and Processing Services

**Azure Storage Queues** or **Azure Service Bus Queues** decouple upload rates from processing rates. Queues buffer pending work, support competing workers, and smooth traffic spikes. Service Bus offers advanced features like built-in dead-letter queues and message handling suited to complex workflows. Storage Queues are simpler and include poison-message handling paired with Azure Functions queue triggers.

A pipeline can either route Event Grid **directly to a queue** when endpoint type/auth satisfies requirements, or have a Function receive Event Grid events and enqueue work items.

### State Store

A durable **job ledger**, such as Azure Table Storage, Cosmos DB, or an existing database, tracks:

~~~text
jobKey | blobName | blobETag | state | attempts | startedAt | completedAt | result
~~~

States may include **RECEIVED**, **PROCESSING**, **SUCCEEDED**, **FAILED**, and **QUARANTINED**. This is application-designed state, **not** a built-in status property of a BlobCreated event.

## 3. Choosing an Architecture by Complexity

### Option A: Direct Processing via Event Grid Trigger

~~~text
Upload blob to incoming
           |
           v
      BlobCreated
           |
           v
       Event Grid
           |
           v
 Azure Function (Event Grid trigger)
           |
           v
 Read blob, validate, process
           |
           v
     Write outputs
~~~

Suitable when processing is brief, traffic is steady, and work fits safely within Function execution and retry bounds. Its weakness is that slow consumers, persistent errors, or upload bursts make backpressure and recovery harder. In particular, never force Event Grid to wait on multi-minute processing when work can be offloaded to a queue.

### Option B: Event Grid → Queue → Worker

~~~text
Client upload
     |
     v
Blob Storage / incoming
     |
     v
Event Grid: BlobCreated
  | filter container + event type
  v
Ingest Function or supported queue destination
     |
     v
Storage Queue / Service Bus Queue
     |
     +--------> Worker #1
     +--------> Worker #2
     +--------> Worker #N
                    |
                    v
          Validate & process file
                    |
                    v
       processed / quarantine / failed
                    |
                    v
       Job ledger + metrics + notifications
~~~

**This is the reference architecture for this lesson** because it cleanly separates concerns:

- Event Grid detects and distributes event metadata.
- The ingest layer receives, runs minimal validation, and enqueues work.
- The queue buffers bursts, drives retries, and decouples worker scaling.
- Workers process contents, determine outcomes, and update the ledger.
- Operations monitor backlog, failures, output quality, and costs.

### When Are Durable Functions or Workflows Needed?

If a file must pass through multi-step dependencies such as malware scan → OCR → manual review → database save → notification, evaluate **Durable Functions**, Logic Apps, or Service Bus workflows. They provide state orchestration across steps, though they do not eliminate idempotency or external error-handling requirements.

## 4. Understanding Azure Blob Storage Events

Two common event types:

| Event type | Meaning | Usage |
|---|---|---|
| **Microsoft.Storage.BlobCreated** | Blob created or written/committed by an event-emitting operation | Trigger file ingestion pipelines |
| **Microsoft.Storage.BlobDeleted** | Blob deleted via a supported operation | Sync indexes, mark deleted records, or clean up related resources |

Not every metadata edit, tag update, or backend operation emits a BlobCreated event. If you require other event types, check official event documentation for your specific storage account kind.

### Illustrative Event Grid Schema Record

~~~json
{
  "id": "example-event-123",
  "eventType": "Microsoft.Storage.BlobCreated",
  "subject": "/blobServices/default/containers/incoming/blobs/invoice-001.pdf",
  "eventTime": "2026-11-20T03:00:00Z",
  "topic": "/subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.Storage/storageAccounts/stfilesdemo",
  "data": {
    "api": "PutBlob",
    "url": "https://stfilesdemo.blob.core.windows.net/incoming/invoice-001.pdf",
    "eTag": "0x8EXAMPLE0001",
    "contentLength": 32768,
    "contentType": "application/pdf",
    "sequencer": "00000000000000000001"
  },
  "dataVersion": "",
  "metadataVersion": "1"
}
~~~

This is a **condensed illustrative sample**, not output from a live Storage Account. Key fields:

- **id**: event record identifier; useful for tracing and detecting duplicate deliveries.
- **eventType**: activity type that generated the event.
- **subject**: typically includes container and blob path, useful for filtering.
- **eventTime**: timestamp when the event was recorded; not an ordering guarantee.
- **data.url**: source blob URL; workers must still validate host/path and permissions.
- **data.eTag**: version marker for blob content/state at event time; helps prevent processing stale overwrites.
- **data.contentLength / contentType**: useful metadata for quick checks, yet **must never be blindly trusted** over real content inspection.
- **data.sequencer**: assists relative ordering of mutations on **the exact same blob**; not a global ordering across all blobs.

Event Grid also supports the **CloudEvents schema**, using different field names like **type**, **source**, **subject**, and **data**. Pick one schema, inspect actual payloads at the destination, and write the matching parser; never assume every handler receives JSON matching this example.

### When Is a Blob Upload Finished?

In standard Blob Storage, BlobCreated events typically correspond to blob creation/commit operations like **Put Blob** or **Put Block List**. However, uploads via **Data Lake Storage Gen2 (hierarchical namespace)**, **SFTP**, or other sync tools can have distinct upload stages and event behavior.

For example, an ADLS Gen2 workflow may need to process only events where **data.api = FlushWithClose**; SFTP flows likewise distinguish file creation from commit/close so workers do not read incomplete files. Exact conditions depend on upload protocol and Storage event documentation.

**Design rule:** explicitly define "file ready for processing" for your upload protocol; never assume every BlobCreated means the same upload-completion point across all protocols.

## 5. Designing Event Subscription Filters

To process only files uploaded to the **incoming** container, filter as early as possible:

1. Select only **Microsoft.Storage.BlobCreated**.
2. Use a subject prefix filter such as:

~~~text
/blobServices/default/containers/incoming/blobs/
~~~

3. Optionally filter extensions like **.pdf**, **.csv**, or **.jpg** via subject suffix and/or advanced filters on supported properties.
4. For ADLS Gen2 or SFTP uploads, consider filtering **data.api** to accept only finalized write operations.
5. Write outputs to a **processed** container or a separate Storage Account so newly written outputs never re-trigger the pipeline.

Filters are **noise-reduction tools**, not content validation layers. A client can name a file **invoice.pdf** while uploading non-PDF bytes. Workers must inspect actual content.

### Example: Preventing Infinite Loops

If an Event Grid subscription lacks a subject filter and a worker writes new files to **processed** in the same Storage Account, the output blob emits another BlobCreated event. The consumer handles that event and writes another output, creating an **infinite event and cost loop**.

Correct design: subscribe only to **incoming**, restrict output writes to **processed**, and verify the container name inside event-handling code. You can also add status metadata or separate Storage Accounts as needed, without relying solely on metadata tags to prevent loops.

## 6. Delivery Semantics: At-Least-Once and Unordered Delivery

This is the most critical part of event-driven pipelines.

### Event Grid Can Redeliver Events

An event subscription retries failed deliveries according to its configured retry policy. An event can arrive **more than once**, even if the blob did not change. Retry window/count limits depend on policy; once exhausted, Event Grid drops the event or sends it to a **dead-letter destination** if configured and eligible.

### No Ordering Guarantee

If **orders.csv** is written as version A and then version B seconds apart, handlers may process event B before event A. Worse, when a worker handles event A, the blob at that path already holds data B.

Never rely on event arrival time or queue order to assume current blob content matches the original event. Define an explicit **processing contract**.

### Choosing a File Processing Contract

| Contract | Implementation | Fits when |
|---|---|---|
| **Process latest only** | When the worker runs, read current blob properties and skip if ETag no longer matches | Files update frequently and intermediate versions do not matter |
| **Process every version** | Enable blob versioning where supported, store versionId, and read that exact version | Auditing or processing every write is mandatory |
| **Immutable blob names** | Each upload uses a unique name; never overwrite paths in **incoming** | Job/batch uploads, greatly simplifying processing |

When operational incidents must never miss files, add a **reconciliation** step: periodically compare blobs in **incoming** against the ledger and re-enqueue missing jobs. Event-driven systems can still benefit from an infrequent reconciliation sweep, unlike polling everything every cycle.

## 7. Idempotency: Avoiding Duplicate Outputs

**Idempotent processing** ensures that even if the same work item executes multiple times, the business outcome matches a single successful execution.

Relying solely on **event.id** is not always enough: the same blob can emit multiple distinct valid events. A practical **job key** is:

~~~text
jobKey = hash(storageAccount + container + blobName + eTag)
~~~

Or include **versionId** when versioning is enabled and every version must be processed. Hash URLs only after normalizing names and stripping any SAS tokens or secrets.

### The Job Ledger Must Support Conditional Updates

A sound algorithm:

~~~text
receive event/queue message
    |
    v
validate account/container/blob and jobKey
    |
    v
try INSERT jobKey with state=PROCESSING (unique key)
    |
    +-- already SUCCEEDED --> ACK duplicate, no new output
    |
    +-- active PROCESSING --> defer/retry according to lease policy
    |
    v
read correct blob version or compare current ETag
    |
    v
validate content + scan according to security policy
    |
    v
write output with deterministic name / conditional create
    |
    v
update ledger to SUCCEEDED with result reference
    |
    v
ACK queue message
~~~

**"Check if exists, then insert" is not atomic.** Two workers can both see no record simultaneously. Use **insert-only/unique keys**, ETag conditional writes, transactions, or database leases. If a worker crashes while PROCESSING, records need a **lease timeout** or reclaim rule to prevent permanent stalls.

For output blobs, derive deterministic names from the job key and upload with **no-overwrite** or conditional creation. If the output already exists, the worker must verify it is a valid output for that job before marking completion.

### Principle: "Ack Only After Durable Persistence"

When Event Grid invokes an HTTP Function to enqueue work, the Function must return success only after **durably writing the message to the queue**. If enqueueing fails, let delivery retry per subscription rules; never return 2xx and drop the event.

Similarly, workers should complete/delete a queue message only after outputs and ledger updates have been persisted. Exact ack mechanics differ across Storage Queue triggers, Service Bus triggers, and custom endpoints, yet **never acknowledging prematurely** remains universal.

## 8. Retries, Poison Messages, and Dead-Lettering

Errors fall into two categories:

- **Transient:** network blips, Storage throttling, OCR service temporarily unavailable, brief worker resource exhaustion. Retry with backoff.
- **Permanent or data errors:** malformed file, oversized payload, malicious content, policy-denied permissions. Infinite retries will never fix these.

### Two Error Layers Must Be Monitored Separately

| Layer | Example failure | Recovery path |
|---|---|---|
| **Event Grid delivery** | Unable to deliver to Function/queue endpoint | Event subscription retries, dead-letter destination if configured |
| **Queue → Worker** | Worker crashes or file processing fails | Queue redelivery, max delivery count, poison queue/DLQ, and replay workflow |

**Event Grid dead-lettering is not Service Bus DLQ.** They cover separate stages. With Azure Storage Queues, Azure Functions queue triggers move messages to a **-poison** queue after exceeding host-configured retry thresholds; Service Bus provides a dedicated **dead-letter subqueue**.

During replay, preserve the job key, inspect current ledger state, and separate fixed transient failures from still-invalid data. Never automatically replay all poison messages indefinitely.

### Backpressure Protection

Suppose 50,000 images arrive in 10 minutes while the image-processing service only handles 500 images/minute. Invoking processing synchronously per event can overwhelm active functions and downstream dependencies.

With queues, let the backlog buffer smoothly while scaling workers under policy:

- Monitor queue depth and **age of the oldest message**.
- Cap concurrent workers and blob read streams to match CPU, RAM, and bandwidth.
- Rate-limit calls to OCR, databases, or external APIs.
- Apply exponential backoff and distinguish 429/5xx responses from data errors.
- Enforce file size caps, timeouts, and guards against oversized files.
- Alert when backlog or message age breaches business SLAs.

Queues smooth load spikes; **they do not create infinite processing capacity**. Account storage capacity, throughput limits, queue message size caps, and service quotas still require capacity planning.

## 9. Security Design for File Pipelines

Uploads are an entry point for **untrusted data**. Files may carry malware, personal data, dangerous CSV formulas, or spoofed extensions.

### Least Privilege with Microsoft Entra ID

Separate application identities:

| Component | Expected permissions | Scope |
|---|---|---|
| Uploader | Create/write only in `incoming` per scenario | Minimum needed for upload |
| Ingest Function | Send messages to queue | Queue sender role on target queue |
| Worker | Read `incoming`, write `processed`/`quarantine` | Separate data-plane roles on matching containers |
| Result consumer | Read-only on `processed` | Read role at minimum required scope |
| Operations team | View metrics/logs, authorized replay | RBAC on relevant resources |

Prefer **managed identities** and Microsoft Entra ID SDKs for Functions. For Blobs, use roles like **Storage Blob Data Reader** and **Storage Blob Data Contributor**; for Storage Queues, use matching queue data sender/processor roles. For Service Bus, grant queue-scoped send/receive roles and check Event Grid destination identity support.

Never hardcode account keys or long-lived SAS tokens in source code. If issuing SAS for direct client uploads, restrict permissions, container/blob scope, short lifetime, and HTTPS, with a clear revocation plan.

### Network Security

Storage Accounts can use **private endpoints** and disable public network access for the data plane once legitimate clients have private connectivity. Workers reading via a Blob private endpoint need DNS resolving Storage hostnames to private IPs and valid routing.

**Blob access over a private endpoint is separate from Event Grid delivering events to a Function/queue.** Never assume disabling public network access on Storage makes every Event Grid destination automatically work over private networks. Verify private networking support, public endpoints, firewall exceptions, managed identities, and delivery models for **each destination** before locking down networking.

### Content Validation

Workers should:

- Verify real file types via **magic bytes/decoders**, not just filename extensions or client-declared `contentType`.
- Enforce file size limits, page/image count caps, and decompression-bomb protections.
- Run malware scanning per organizational policy; evaluate managed Storage security services where appropriate.
- Process files in a least-privilege sandbox without executing embedded macros or code.
- Never log sensitive payloads, file contents, or tokens.
- Promote files to downloadable zones only after passing security and policy checks.

A BlobCreated event **is not proof a file is safe**. Strict workloads should advance state explicitly through RECEIVED → SCANNED → PROCESSED → PUBLISHED and withhold public/consumer access until checks complete.

## 10. Python Azure Functions Example: Receiving Events and Queueing Work

The example below uses the Azure Functions **Python programming model v2**: an Event Grid trigger receives BlobCreated and sends a compact message to an **Azure Storage Queue**. This is strictly the **ingest** step, avoiding reading whole blobs inside the Event Grid trigger.

### Prerequisites

- A source Storage Account and **incoming** container.
- An Event Grid subscription routing BlobCreated to a supported **Azure Function** endpoint.
- An Azure Storage Queue named **blob-work**.
- Function **managed identity** granted data-plane permission to send messages to the queue.
- App settings containing **EXPECTED_BLOB_HOST**, **QUEUE_ACCOUNT_URL**, and **QUEUE_NAME** (no keys).
- Python packages: **azure-functions**, **azure-identity**, and **azure-storage-queue**.
- Functions runtime/hosting and networking configured so the function can reach the queue.

When deployed on Azure, **DefaultAzureCredential** can use the managed identity. Locally, it may pick developer credentials, so verify subscription/tenant and data permissions before testing.

### Example function_app.py

~~~python
import json
import logging
import os
from urllib.parse import unquote, urlsplit

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.queue import QueueClient

app = func.FunctionApp()


@app.event_grid_trigger(arg_name="event")
def receive_blob_created(event: func.EventGridEvent):
    # Ignore events other than BlobCreated.
    if event.event_type != "Microsoft.Storage.BlobCreated":
        return

    data = event.get_json()
    blob_url = data.get("url", "")
    parsed = urlsplit(blob_url)

    # Never blindly trust the URL from the event payload.
    expected_host = os.environ["EXPECTED_BLOB_HOST"].lower()
    if parsed.scheme != "https" or parsed.hostname != expected_host:
        logging.warning("Ignored event: unexpected blob endpoint")
        return

    path = unquote(parsed.path.lstrip("/"))
    container, separator, blob_name = path.partition("/")

    # Process only the incoming container to prevent event loops.
    if not separator or container != "incoming" or not blob_name:
        return

    allowed_suffixes = (".pdf", ".png", ".jpg", ".csv")
    if not blob_name.lower().endswith(allowed_suffixes):
        return

    job = {
        "eventId": event.id,
        "accountHost": expected_host,
        "container": container,
        "blobName": blob_name,
        "eTag": data.get("eTag"),
        "eventType": event.event_type,
    }

    queue = QueueClient(
        account_url=os.environ["QUEUE_ACCOUNT_URL"],
        queue_name=os.environ.get("QUEUE_NAME", "blob-work"),
        credential=DefaultAzureCredential(),
    )

    # Do not swallow send errors: let the trigger retry.
    queue.send_message(json.dumps(job, ensure_ascii=False))
    logging.info("Enqueued blob work: eventId=%s", event.id)
~~~

**Limitations of this sample:** this is an illustrative ingest skeleton, not a complete production solution. Extension checks only provide quick filtering; workers must still validate real file contents. Add structured telemetry, full source/topic/subject validation per event contract, permission audits, and Event Grid delivery monitoring.

For ADLS Gen2/SFTP accounts, add **data.api** or appropriate upload-completion checks before enqueueing. This example assumes uploaders emit BlobCreated only once content is committed.

### Idempotent Queue Worker

Workers can use an Azure Functions **Queue trigger** and read blobs via the Azure Blob SDK with managed identity. The pseudocode below separates orchestration/idempotency from content processing:

~~~text
function processMessage(job):
    validate job fields and expected account/container
    jobKey = stableHash(accountHost, container, blobName, eTag)

    if ledger[jobKey] is SUCCEEDED:
        return success  # duplicate delivery

    atomically reserve jobKey or recover expired lease
    blob = open source blob via managed identity

    if processing_latest_only and blob.currentETag != job.eTag:
        mark job SKIPPED_STALE
        return success

    if processing_each_version:
        open exact blob version from validated versionId

    enforce size / file type / security policy
    if malware_or_rejected:
        record QUARANTINED without exposing file
        return success

    result = transform_or_extract(blob)
    write result with deterministic output name and conditional create
    atomically/fail-safely record SUCCEEDED and result reference
    return success
~~~

Real orchestration must handle **a worker writing the output successfully and crashing before updating the ledger**: on retry, the worker must detect the existing output and finalize the ledger without producing duplicates. Consistency across queues, output blobs, and databases has no automatic distributed transaction; design for **at-least-once + idempotent side effects**.

### Configuration Items to Verify

| Component | What to confirm |
|---|---|
| Event Grid trigger | Subscription targets the exact Function; endpoint validation/auth handled per config |
| Queue sender | Managed identity holds queue send permissions |
| Queue trigger | Function host holds queue access and connection settings matching auth mode |
| Blob reader | Managed identity holds container read permissions and valid DNS/routing |
| Job ledger | Unique keys/conditional writes, lease timeouts, recovery states |
| Blob output | Write mode prevents unintended overwrites; deterministic output names |
| Monitoring | Correlation across eventId, queue message ID, jobKey, and blob ETag |

## 11. Setting Up the Pipeline in Azure Portal

Because creating Event Grid subscriptions, queues, and Functions can incur charges, run labs only in an authorized subscription/resource group. Never experiment on production Storage holding customer data.

### Step 1: create Storage and containers

Prepare a Storage Account with **incoming**, **processed**, and **quarantine** containers. Configure redundancy, encryption, public network access, private endpoints, and RBAC as needed. Confirm uploaders hold only minimum required permissions.

### Step 2: pick the processing topology

For this lesson's example, create **Storage Queue blob-work** and a Function App with an Event Grid trigger. Add a worker Function consuming the queue and writing results to **processed**. Function resources may need runtime hosting/storage dependencies depending on plan.

To route Event Grid directly to a Service Bus queue, verify delivery/managed identity support, RBAC, and network restrictions beforehand. Do not mix up Storage Queue and Service Bus settings.

### Step 3: create the event subscription

From the source Storage Account, open **Events** and create an Event Grid event subscription. Depending on the Portal UI, the system topic may be created/managed in the same step.

Illustrative settings:

~~~text
Name: evt-incoming-created
Event types: Blob Created
Subject begins with:
  /blobServices/default/containers/incoming/blobs/
Endpoint type: Azure Function
Endpoint: receive_blob_created
Event delivery schema: Event Grid schema (matching the sample code)
~~~

Check the exact container/path prefix and avoid matching broader scopes than needed. For ADLS Gen2, add appropriate upload-completion conditions. Configure retry/dead-letter policies per operational needs and permissions on the dead-letter destination.

### Step 4: configure permissions and app settings

Grant the Function's managed identity permission to **send messages** to the queue. Grant workers permission to **read incoming** and **write processed/quarantine**, avoiding a shared account key across all components. Set `EXPECTED_BLOB_HOST` and `QUEUE_ACCOUNT_URL` to real endpoints.

Lock down public network access only after verifying routing/DNS to Blobs and queues. Verify Event Grid delivery paths to Functions separately according to network features and hosting plan.

### Step 5: upload a test file

Upload a test file to **incoming**, such as **invoice-001.pdf**. Observe:

1. The blob exists with expected byte size.
2. Event Grid records successful delivery to the Function.
3. The ingest Function enqueued a message into **blob-work**.
4. The worker consumed the message, updated the job ledger, and wrote output.
5. Output lands in **processed** without triggering a new loop.
6. Telemetry captures eventId/jobKey to trace the full journey.

### Step 6: test failures and retries

In a test environment, simulate controlled failures such as malformed files or unavailable downstream services. Confirm messages retry within policy bounds and land in poison/DLQ/quarantine as expected.

After fixing the issue, run a controlled replay and confirm **no duplicate outputs are created**. Never intentionally disrupt production resources to test retries.

### Step 7: clean up and monitor costs

Remove unused event subscriptions, Functions/queues, and lab resources after confirming owner and scope. **Delete the entire resource group only once certain it contains nothing worth keeping.** Review Azure Cost Management and retention on logs, dead-letter blobs, and test outputs.

## 12. Read-Only Inspection with Azure CLI

The commands below are for inspection and do not create or delete resources. Resource group/account/container names are illustrative:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az storage account show \
  --resource-group "rg-file-pipeline" \
  --name "stfilesdemo" \
  --query "{name:name,location:location,kind:kind,publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

List event subscriptions by Storage Account resource ID:

~~~bash
az eventgrid event-subscription list \
  --source-resource-id "<STORAGE_ACCOUNT_RESOURCE_ID>" \
  --output table
~~~

With **Microsoft Entra ID** and appropriate Blob data-plane roles, inspect container contents:

~~~bash
az storage blob list \
  --account-name "stfilesdemo" \
  --container-name "incoming" \
  --auth-mode login \
  --output table
~~~

When Storage restricts access to private endpoints, the CLI host must also have DNS/routing to the private endpoint; Entra ID permissions cannot replace network connectivity.

To inspect queue settings or consumer status, use the corresponding Azure Portal blades or Azure tools per granted permissions. Do not delete messages, trigger replays, or edit event subscriptions merely to inspect state.

## 13. Monitoring and Operations

A pipeline that works on its first test run is not yet production-safe. Monitor end to end.

### Key Metrics

| Metric | Meaning |
|---|---|
| Event Grid publish/delivery failures | Detects events failing to reach destinations |
| Queue length / oldest message age | Measures backlog and lag during upload spikes |
| Worker success/failure/retry counts | Tracks processing stability |
| Processing latency | Elapsed time from upload to usable output |
| Blob bytes processed | Tracks volume and processing cost |
| DLQ/poison message count | Flags unhandled failures |
| Duplicate/stale event count | Evaluates idempotency and overwritten files |
| Quarantined/rejected files | Tracks data quality and security issues |
| Storage 403/429/5xx | Separates permission errors, throttling, and service faults |

### Correlation IDs

Every log record should carry safe tracing fields:

~~~json
{
  "eventId": "example-event-123",
  "jobKey": "hash-of-account-container-name-etag",
  "sourceContainer": "incoming",
  "blobName": "invoice-001.pdf",
  "state": "SUCCEEDED",
  "durationMs": 820,
  "resultBlob": "processed/invoice-001.json"
}
~~~

Never log SAS tokens, account keys, file contents, personal data, or full URLs containing secret query strings.

### Alerting Targets

- Rising Event Grid delivery failures or dead-lettered events.
- Queue backlog or oldest message age breaching SLAs.
- Workers continuously failing/retrying with zero completions.
- Abnormal spikes in quarantined files.
- Rapid cost increases across Functions, queues, storage, and logs.
- Private DNS/network changes blocking workers from reading blobs.

Use **Azure Monitor**, **Application Insights**, diagnostic settings, and dashboards to correlate logs and metrics. Exact metric names and granularity depend on service, plan, and collection setup.

## 14. Troubleshooting Common Issues

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Upload succeeds but no job runs | Event subscription wrong resource/event type/filter; delivery failure | Inspect Events blade, subject filter, endpoint, and delivery metrics |
| Events arrive but queue stays empty | Ingest Function failing or lacking queue send permissions | Check Function logs, managed identity, and Queue Data roles |
| Queue grows continuously | Worker stopped, low concurrency, or downstream throttling | Inspect Function host, scaling, queue age, CPU/memory, and external APIs |
| One file processed twice | Retry or duplicate delivery; missing idempotency | Compare eventId, blob ETag, jobKey, and unique-key ledger |
| Processed old event but read new content | Blob overwritten before worker read it | Compare ETag; enable versioning if old versions must be read |
| BlobCreated arrives before file is ready | Multi-step upload, ADLS Gen2/SFTP commit differs from expectations | Check `data.api` and upload completion protocol |
| Worker gets 403 reading Blob | Missing RBAC role, token issue, or blocked by Storage firewall | Check managed identity, data-plane roles, network rules, and DNS |
| Worker times out reaching Blob | Misconfigured Private DNS, routing, NSG, or Private Endpoint | Resolve hostname from worker, test TCP/443, and check endpoint state |
| Job stuck in PROCESSING | Worker crashed, ledger lacks lease timeout | Check TTL/leases, retries, and reclaim logic |
| Output event triggers new job | Overly broad event filter or output written to `incoming` | Check subject prefix and container validation logic |
| Growing DLQ/poison queue | Unresolved data errors or misconfiguration | Classify transient vs. permanent, fix root cause, and replay cleanly |
| Processing succeeds but output missing | Written to wrong account/container or permission/ledger bug | Check output key, request ID, roles, and state transactions |

### A Scenario to Reason Through

A user uploads **report.csv** and then uploads a new file with the exact same name seconds later. Event A carries ETag A; event B carries ETag B. The worker handles event B first and writes output for B. Next, event A arrives. If the worker simply reads the current blob by path, event A may reprocess **content B** and emit duplicate output.

Prevent this by checking ETag before reading, enforcing unique immutable names per upload, or enabling versioning and reading the exact version. Pair this with a job-key ledger to block duplicate processing and write deterministic outputs.

## 15. Performance and Cost Optimization

Pipeline costs extend beyond Blob Storage capacity alone. Estimate:

- **Blob Storage**: capacity, transactions, storage tiers, lifecycle/retention, versions/soft delete if enabled.
- **Event Grid**: event operations/deliveries and retries per current pricing.
- **Queue/Service Bus**: message counts, operations, retention, premium tiers if used.
- **Azure Functions**: hosting plan, execution duration, memory/compute, execution count, and companion services.
- **AI/OCR/transforms**: per-document/page/transaction fees if integrated.
- **Networking**: private endpoints, NAT, bandwidth/data transfer, or companion network services.
- **Observability**: logs/metrics ingestion, storage, queries, and retention periods.

An efficient design uses **compact queue messages carrying metadata and blob references**, rather than stuffing full file bytes into queues. Queues must never replace Blob Storage for holding large files; every queue service enforces strict message size limits.

Tune batch size and concurrency so workers stay within resource limits and avoid throttling Storage or downstream systems. Use lifecycle rules to purge temporary files or tier older data once retention requirements are met. Apply owner tags and budgets per resource group/subscription, and track current pricing rather than hardcoding static rates in architectural docs.

## 16. Case Study Exercise: PDF Invoice Processing

An e-commerce company needs to process roughly 10,000 PDF invoices per day. Users upload to Blob Storage. The system must scan files, extract invoice numbers and totals, store JSON results, and notify accounting. Duplicate uploads with identical names can occur; some files are large; the OCR service occasionally returns transient errors.

Design:

1. **incoming**, **processed**, and **quarantine** containers, plus permissions for uploaders and workers.
2. An Event Grid subscription accepting only BlobCreated from **incoming**.
3. Which queue to buffer load, justifying Storage Queue vs. Service Bus.
4. How to confirm a PDF upload is complete for the active upload protocol.
5. Job keys and ledger preventing duplicate processing of the same version.
6. How to distinguish OCR timeouts from corrupted/malicious files.
7. Retry, poison/DLQ, replay, and reconciliation strategies.
8. Steps to verify DNS, private endpoints, and data-plane permissions.
9. How to stop newly created JSON outputs from re-triggering the pipeline.
10. Metrics, alerts, SLAs, and cost items to report.

**Guided solution hints:** use Event Grid → Function enqueue → Queue → Worker; key jobs by **account/container/blob/ETag**; write deterministic JSON outputs; validate real file contents and malware scan status; apply bounded retries for transient OCR errors; route permanent failures to quarantine/DLQ; and alert on **oldest message age**. If business rules require processing every single overwrite, enable versioning, capture `versionId`, and read that exact version.

## 17. Pre-Production Checklist

| Area | What to verify |
|---|---|
| Source | Correct Storage Account, containers, subresource, and upload completion definition |
| Events | Correct event type/schema/filters; no event loops |
| Delivery | Correct endpoint, authentication/authorization, and retry/dead-letter policies |
| Queue | Message size limits respected, retry/poison queues, and backlog safeguards |
| Correctness | Idempotency keys, unique-key ledger, ETag/version checks, conditional outputs |
| Security | Managed identity/RBAC, zero hardcoded secrets, untrusted-file validation |
| Networking | DNS, routing, private endpoints, and event delivery paths verified |
| Application | Transient vs. permanent errors classified; sensible timeouts and concurrency |
| Operations | Correlation IDs, metrics, alerts, replay runbooks, and reconciliation jobs |
| Cost | Modeled Event Grid, queues, compute, storage, networking, and logging |
| Acceptance | Tested uploads, duplicates, overwrites, malformed files, retries, recovery, and scale |

## 18. Self-Check Questions

1. When should you use BlobCreated events instead of scanning an entire container on a schedule?
2. Does an Event Grid event contain the raw bytes of the PDF file? Where does the worker fetch the file content from?
3. Why filter subjects to **incoming** and keep outputs out of the uncontrolled input stream?
4. What is the difference between a direct Event Grid trigger and Event Grid → Queue → Worker?
5. How does "at-least-once delivery" affect output file naming and job state design?
6. Why isn't a single `eventId` always sufficient to uniquely identify a Blob data version?
7. How do ETags and Blob versioning help handle file overwrites?
8. What is the difference between an Event Grid delivery failure and a queue message processing failure?
9. Why validate actual PDF file contents even when the filename ends in **.pdf**?
10. What role does managed identity play when workers read Blobs and send messages to queues?
11. Why doesn't a Private Endpoint on Storage automatically guarantee Event Grid can deliver events?
12. Which metrics help detect workers falling behind during an upload surge?
13. If an output blob was written but the worker crashed before updating the ledger, what should the retry run do?
14. Why might an event-driven system still need a periodic reconciliation job?

## References

- Microsoft Learn — *Azure Blob Storage events with Azure Event Grid*: https://learn.microsoft.com/azure/storage/blobs/storage-blob-event-overview
- Microsoft Learn — *Event schemas for Blob Storage events*: https://learn.microsoft.com/azure/event-grid/event-schema-blob-storage
- Microsoft Learn — *Azure Event Grid overview*: https://learn.microsoft.com/azure/event-grid/overview
- Microsoft Learn — *Azure Event Grid delivery and retry*: https://learn.microsoft.com/azure/event-grid/delivery-and-retry
- Microsoft Learn — *Event Grid trigger for Azure Functions*: https://learn.microsoft.com/azure/azure-functions/functions-bindings-event-grid-trigger
- Microsoft Learn — *Azure Functions Blob storage bindings*: https://learn.microsoft.com/azure/azure-functions/functions-bindings-storage-blob
- Microsoft Learn — *Azure Functions Queue storage trigger*: https://learn.microsoft.com/azure/azure-functions/functions-bindings-storage-queue-trigger
- Microsoft Learn — *Azure Blob Storage versioning*: https://learn.microsoft.com/azure/storage/blobs/versioning-overview
- Microsoft Learn — *Authorize Blob data with Microsoft Entra ID*: https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory
