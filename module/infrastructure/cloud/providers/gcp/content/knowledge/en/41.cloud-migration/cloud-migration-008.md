# Storage Transfer Service and Object Data Migration

When migrating applications to Google Cloud, a large portion of data may already reside in Amazon S3, Azure Blob Storage, Cloud Storage buckets in another project, or on-premises data center storage. This data is usually stored as **objects**—an object name, payload, and metadata—rather than relational tables with schemas. Moving millions of objects with a custom copy loop is not trivial: you must handle transient failures, API rate limits, authentication, objects changing mid-copy, data transfer costs, and post-migration verification.

**Storage Transfer Service (STS)** is a Google Cloud service that manages data transfers between supported storage systems. You declare the source, sink, object selection filters, overwrite rules, schedule, and permissions. STS plans and executes transfer operations while exposing status, statistics, and error details. STS is optimized for large-scale data movement; for very small tasks, Cloud Storage CLI commands can be simpler.

Within the CLOUD_PROVIDERS_GCP module, STS bridges project organization, IAM, and VPC with Cloud Storage, data protection, automation, and cost tracking. Successful object migration requires designing the target bucket, granting service agent permissions, selecting proper copy policies, and verifying access before switching applications to the new data source.

After this lesson, you will be able to:

- Distinguish Storage Transfer Service from manual copy commands, Storage Transfer Agents, and Transfer Appliance.
- Select supported sources/sinks and know when an agent pool is required.
- Prepare buckets, service agents, IAM, and security constraints before running transfers.
- Create a non-destructive Cloud Storage-to-Cloud Storage job via the Google Cloud CLI.
- Configure overwrite, delete, prefix filters, manifests, schedules, and event-driven transfers.
- Monitor transfer jobs and operations, troubleshoot errors, and verify data integrity.
- Plan initial copy, incremental sync, cutover, and rollback.
- Estimate cost drivers and establish a production migration checklist.

## 1. Choosing the Right Data Migration Tool

Not every object copy requires STS. Before choosing a tool, determine data location, total volume, object count, allowable downtime, and recurring sync needs.

| Tool | Strengths | When to Consider |
|---|---|---|
| `gcloud storage cp` or `gcloud storage rsync` | Easy from a terminal or script; suited for small datasets and one-off tasks | Copying few objects, testing, short operational tasks |
| **Storage Transfer Service** | Manages jobs, operations, schedules, metrics, and retries; optimized for large data | Moving many objects across clouds, cross-project migrations, recurring copies, or monitored runs |
| **Agent-based Storage Transfer** | Runs transfer agents near source/destination; leverages controlled links and bandwidth | On-premises filesystems, HDFS, or S3-compatible storage |
| **Transfer Appliance** | Physical appliance for shipping massive datasets when WAN bandwidth is constrained | Very large data that cannot transfer over the network within the deadline |
| Dedicated DB tools | Understands schemas, transaction logs, replication, or CDC | Migrating relational, transactional, or consistency-sensitive databases |

STS operates on objects and files across supported sources/sinks; it does not automatically migrate database schemas, update application paths, design target IAM, or guarantee transactional consistency across business workflows. For databases, use migration/replication tools suited to that database engine.

Google Cloud describes STS as optimized for transfers larger than roughly 1 TiB. That is a tool-selection guideline, not a mandatory threshold to create a job.

## 2. Which Sources and Sinks Are Supported?

STS supports many data sources, though not every source–destination pair works in both directions.

| Source | Typical Destination | Model | Notes |
|---|---|---|---|
| Cloud Storage | Cloud Storage | Agentless | Supports transfers between buckets in the same or different projects |
| Amazon S3 | Cloud Storage | Agentless | Requires granting STS read access from AWS; check egress charges |
| Azure Blob Storage / ADLS Gen2 | Cloud Storage | Agentless | Requires matching source authentication mechanism |
| HTTP/HTTPS URL list | Cloud Storage | Agentless | Uses a list of public URLs or appropriately signed URLs |
| S3-compatible object storage | Cloud Storage | Agent-based | Requires an agent pool and endpoint to the S3-compatible store |
| On-premises or VM filesystem | Cloud Storage, and select reverse directions | Agent-based | Agents need filesystem read/write permissions and network connectivity |
| HDFS | Cloud Storage | Agent-based | Requires agents and HDFS access configuration |

When your migration scope involves other storage systems or special directions, check the current **Supported sources and sinks** page before designing. In particular, never assume STS supports transferring Amazon S3 to Azure Blob or every source into every sink.

### Agentless Transfer

For transfers between supported cloud object stores, Google manages the data-movement workers. You primarily configure the source/sink, source credentials or permissions, STS service agent permissions on Cloud Storage, and the transfer schedule.

### Agent-Based Transfer

For filesystems, HDFS, or S3-compatible storage, you run transfer agents on machines with connectivity to the source/sink. Agents are grouped into an **agent pool**; STS dispatches work and collects status. Alongside the STS service agent, there is a **transfer agent account** used to authenticate agent processes. These two identities carry distinct IAM responsibilities.

~~~mermaid
flowchart LR
    C[Admin or CI] --> J[Storage Transfer Service job]
    J --> O[Transfer operation]
    O --> A[Google-managed workers]
    A --> S1[Cloud object source]
    A --> D[Cloud Storage destination]
    O --> P[Agent pool - when needed]
    P --> S2[On-prem file system / HDFS / S3-compatible]
    P --> D
~~~

This diagram shows both architectural branches. Any given job uses only the branch matching its source and destination; not every transfer uses an agent pool.

## 3. Distinguishing Transfer Jobs and Transfer Operations

A **transfer job** is the persistent configuration: it stores the source, sink, options, and execution schedule. A **transfer operation** is a single run of that job, with its own start time, status, progress, and counters.

For example, a daily bucket-sync job produces multiple operations over successive days. When inspecting results, distinguish a job remaining `ENABLED` from whether its latest operation succeeded or failed. Jobs can be created with an option not to run immediately; conversely, creating a job via CLI without a schedule or `--do-not-run` can start transferring right away.

| Entity | Role | Example |
|---|---|---|
| Job | Defines what to copy and when to run | `transferJobs/1234567890` |
| Operation | A specific execution instance of a job | `transferOperations/...` |
| Schedule | Run once, daily, or periodically | Nightly during sync phase |
| Event stream | Listens for new/changed object events | Pub/Sub for Cloud Storage, SQS for S3 |
| Agent pool | Cluster of agents running near source/sink | `onprem-transfer-agents` |

STS helps schedule and track data transfers. It does not capture an atomic snapshot across sources undergoing continuous modification. Consistency during cutover must be handled separately.

## 4. Surveying Source Data Before Migrating

A migration can take far longer than expected due to millions of tiny objects even when total bytes are modest. Build an inventory before creating jobs:

- **Size and count:** total bytes, object count, median size, and size distribution.
- **Namespace:** prefixes, object naming patterns, special characters, and name collisions at the destination.
- **Churn:** hourly or daily create/update/delete rates; whether writers remain active.
- **Versioning:** whether the bucket retains multiple generations/versions, and which history must be preserved.
- **Metadata:** content type, cache-control, custom metadata, object ACLs, timestamps, and checksums.
- **Security:** sensitive data, source/target IAM, CMEK, retention policies, object holds, and VPC Service Controls.
- **Cost:** source bandwidth, read/GET request fees, cross-provider egress, and target storage classes.
- **Consumption:** which object names, URLs, bucket names, and access rules applications rely on.

A basic inventory can inspect objects and metadata using the Cloud Storage CLI:

~~~bash
gcloud storage ls --recursive "gs://my-source-bucket/"
gcloud storage objects describe "gs://my-source-bucket/sample/data.csv" \
  --format="json(name,size,crc32c,md5Hash,contentType)"
~~~

These are inspection examples only; in buckets with millions of objects, avoid dumping the entire list to a terminal. Generate manifests, inventory reports, or use organization-approved analytics tooling to aggregate by prefix.

### Defining Transfer Objectives

Before running jobs, agree on:

1. Which objects are included and which are excluded.
2. Which metadata fields must be preserved.
3. Acceptable temporary drift between source and sink.
4. RTO/RPO or cutover window for the application tier.
5. Rules for handling modified, deleted, or colliding objects at the destination.
6. Who authorizes switching application traffic to the destination.
7. How to recover or fail back to the source if verification fails.

Never treat "job succeeded" alone as proof that migration is complete. An operation can succeed while a misconfigured prefix filter leaves business data behind.

## 5. Preparing Projects, Buckets, and IAM Permissions

### Three Permission Scopes to Separate

1. **Project running STS:** users/pipelines creating, running, or monitoring jobs need appropriate STS roles.
2. **Source bucket:** the STS service agent needs permission to list and read objects, and delete permission only if configured to delete source objects.
3. **Destination bucket:** the service agent needs permission to view the bucket, create/read objects, and overwrite/delete if required.

Commonly used roles:

| Role | Principal | Purpose |
|---|---|---|
| `roles/storagetransfer.admin` | Administrators or authorized pipelines | Create, update, delete jobs and manage agent pools |
| `roles/storagetransfer.user` | Job operators | Create, update, and run jobs without deleting jobs |
| `roles/storagetransfer.viewer` | Observers | View jobs and operations |
| `roles/storage.legacyBucketReader` | STS service agent | Read source/sink bucket metadata per integration requirements |
| `roles/storage.objectViewer` | STS service agent on source | Read objects while leaving source intact |
| `roles/storage.objectUser` | STS service agent on sink | Create/read/overwrite and manage objects as required by transfer |
| `roles/storagetransfer.transferAgent` | Transfer agent account, when using agents | Poll work and report status to STS |

Exact permissions depend on transfer type, ACL preservation, source deletion, hierarchical namespace destinations, and organizational policies. For non-destructive GCS-to-GCS transfers, the roles above are a common starting point. Do not grant project-level Storage Admin when bucket-scoped access suffices.

### Storage Transfer Service Service Agent

STS uses a **Google-managed service agent** formatted as:

~~~text
project-PROJECT_NUMBER@storage-transfer-service.iam.gserviceaccount.com
~~~

This identity belongs to the **project managing the transfer job**. It can access source or destination buckets in other projects if granted corresponding permissions on those buckets.

Retrieve the exact service agent email using the Storage Transfer Service API:

~~~bash
export TRANSFER_PROJECT_ID="migration-control-prod"

gcloud services enable storagetransfer.googleapis.com \
  --project="$TRANSFER_PROJECT_ID"

curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://storagetransfer.googleapis.com/v1/googleServiceAccounts/$TRANSFER_PROJECT_ID"
~~~

The response includes an `accountEmail` field. Copy that email into `SERVICE_AGENT_EMAIL` for the IAM commands below. Never guess the service agent email from a project ID; it requires the exact project number.

### Granting Permissions for a GCS-to-GCS Lab

Suppose the buckets reside in two different projects and jobs are managed in `migration-control-prod`. Specify your buckets:

~~~bash
export SOURCE_BUCKET="source-objects-example"
export DEST_BUCKET="destination-objects-example"
export SERVICE_AGENT_EMAIL="project-123456789012@storage-transfer-service.iam.gserviceaccount.com"
~~~

The service agent email above is an example only—replace it with the `accountEmail` returned by the API. Keep source data intact and grant least-privilege permissions for a copy-only transfer:

~~~bash
gcloud storage buckets add-iam-policy-binding "gs://$SOURCE_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.legacyBucketReader"

gcloud storage buckets add-iam-policy-binding "gs://$SOURCE_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.objectViewer"

gcloud storage buckets add-iam-policy-binding "gs://$DEST_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.legacyBucketReader"

gcloud storage buckets add-iam-policy-binding "gs://$DEST_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.objectUser"
~~~

The operator running these commands needs permission to modify bucket IAM policies. If your setup requires deleting source objects or preserving object ACLs, check additional permissions in STS docs. When creating jobs in the Console with sufficient privileges, the Console can offer to grant roles to the service agent automatically; CI/CD typically requires explicit IAM provisioning.

## 6. Hands-On: Transferring Objects Between Two Cloud Storage Buckets

Goal: create a job copying data from the source bucket to the destination bucket **without deleting source objects**, prevent launching an operation until the configuration is reviewed, then run and monitor it.

### Step 1: Prepare the Bucket and Storage Location

Ensure both buckets exist and the destination bucket has the right location, storage class, default encryption, and policies. If creating a new bucket:

~~~bash
gcloud storage buckets create "gs://$DEST_BUCKET" \
  --project="destination-project-prod" \
  --location="asia-southeast1" \
  --uniform-bucket-level-access
~~~

Run creation only if the destination bucket does not already exist. If it exists, inspect its metadata instead of recreating it. Location, retention policies, lifecycle rules, and application read permissions must be designed before copying.

### Step 2: Create the Transfer Job Without Running It Yet

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --description="Initial GCS object migration, non-destructive" \
  --overwrite-when=different \
  --do-not-run
~~~

Meaning of options:

- `gs://$SOURCE_BUCKET` is the source; the destination bucket is the sink.
- `--overwrite-when=different` overwrites destination objects when STS determines they differ from the source per its comparison rules.
- Omitting `--delete-from` ensures the job does not delete objects from either source or sink.
- `--do-not-run` creates the job definition without starting a copy immediately.

The command returns a **job name** formatted as `transferJobs/...`. Save the exact job name from output rather than guessing IDs. Before running, inspect the saved configuration:

~~~bash
gcloud transfer jobs describe "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Verify source/sink, prefixes, delete options, overwrite behavior, and schedule. In production, run a pilot job on a small prefix before expanding to the full bucket.

### Step 3: Trigger a Manual Run

~~~bash
gcloud transfer jobs run "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

For large jobs, this starts an operation asynchronously without necessarily waiting for every object to finish copying. You can pass `--no-async` if you want the CLI to block until completion, keeping CI runtimes and timeouts in mind.

### Step 4: Monitor the Transfer

~~~bash
gcloud transfer jobs monitor "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"

gcloud transfer operations list \
  --job-names="transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Grab an operation name from the list and inspect details:

~~~bash
gcloud transfer operations describe "transferOperations/OPERATION_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Track status, objects/bytes copied, skipped counts, error counts, and completion time. Once the operation finishes, verify data integrity via the steps in Section 11.

### Step 5: Re-Run or Update the Job

An existing job can be re-run to copy new or updated objects. This is useful during migration while the legacy app still writes to the source:

~~~bash
gcloud transfer jobs run "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

If you update source/destination, filters, or overwrite options, review changes before the next run. Never assume every older object gets re-copied; behavior depends on transfer options, metadata, and source/sink state.

## 7. Prefix Filters, Paths, and Manifests

Not every migration requires the entire bucket. You can scope transfers to namespaces like `images/`, `exports/`, or `logs/2026/`.

### Source and Destination Paths

With the `gcloud` CLI, you can specify a prefix as a "folder" in the path:

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET/exports/" \
  "gs://$DEST_BUCKET/archive/" \
  --project="$TRANSFER_PROJECT_ID" \
  --overwrite-when=different \
  --do-not-run
~~~

Trailing `/` slashes matter when specifying folders. Test on sample data to verify how object names concatenate onto the target prefix; Cloud Storage uses flat object namespaces rather than traditional POSIX directories in standard buckets.

### Include/Exclude Prefixes

STS lets you filter objects by prefix or modification time:

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --include-prefixes="exports/,reports/" \
  --exclude-prefixes="exports/tmp/" \
  --do-not-run
~~~

When the source specifies a folder, prefix filters are evaluated relative to that folder. Time filters such as `--include-modified-after-absolute` and `--include-modified-before-absolute` select objects by modification timestamp; check `gcloud transfer jobs create --help` for current flag syntax.

Do not treat prefix filters as IAM access controls. Filters only select objects to transfer; the service agent still requires read permissions on accessed resources per service rules.

### Using a Manifest for Exact Lists

A **manifest** is a CSV file listing exact objects/files to transfer. For object storage, the first column is the object name relative to the source path; a second column can specify a Cloud Storage object generation when an exact version is needed.

Example `objects.csv`:

~~~csv
customers/2026/part-0001.json
customers/2026/part-0002.json
invoices/2025/invoice-042.pdf
~~~

Upload the manifest to a bucket readable by STS, then reference it:

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --manifest-file="gs://migration-manifests/objects.csv" \
  --do-not-run
~~~

Manifests fit well when moving an approved subset of objects, migrating in batches, or specifying exact generations. Do not modify a manifest while an operation is running. Ensure CSV paths, delimiters, and UTF-8 encoding match the documentation for your source type.

### Object Versioning

A standard bucket transfer does not automatically preserve full version history for every object. If non-current generations must move, use a generation-aware manifest workflow and enable object versioning at the destination per GCS-to-GCS docs. Never claim a migration "preserved history" if you only checked live current objects.

## 8. Overwrites, Deletions, and Metadata Preservation

The options below alter data at the destination or source. Confirm them against your inventory and migration goals.

| Option | Meaning | When to Use |
|---|---|---|
| Do not overwrite existing objects | Keeps destination object if name already exists | Testing, one-off imports, avoiding overwriting sink data |
| `--overwrite-when=different` | Overwrites when STS detects sink object differs from source | Incremental sync during migration |
| `--overwrite-when=always` | Always replaces matching object names at sink | When full re-copy is required per approved policy |
| `--delete-from=destination-if-unique` | Deletes sink objects absent from source | Strict mirror sync; only after verification |
| `--delete-from=source-after-transfer` | Deletes source objects after transfer | Ownership transfer; high risk without rollback |
| `--preserve-metadata` | Chooses which metadata fields to keep on copy | When downstream apps rely on content type, ACLs, or metadata |

Do not enable either deletion flag on your first test run. If the destination bucket has a retention policy, legal hold, or versioning, overwrites/deletes may create new versions or be rejected. Certain metadata and ACL permissions cannot be preserved verbatim due to target bucket settings or cross-provider differences.

### ACLs and Uniform Bucket-Level Access

If the destination bucket uses Uniform Bucket-Level Access, access is governed by IAM rather than object ACLs. Applications still relying on per-object ACLs must update their authorization design; STS cannot automatically translate object ACLs into an equivalent IAM model.

### Content Type and Custom Metadata

Metadata such as `contentType`, `cacheControl`, or custom metadata affects how applications consume objects. Specify preservation requirements explicitly and verify them post-copy. Beyond matching byte payloads, a migration can still be broken if a JSON object is served with the wrong content type or altered cache policy.

## 9. Schedules, Incremental Transfers, and Event-Driven Transfers

### One-Time or Scheduled Runs

STS can run once or repeat on a configured schedule. In the Console, users can select one-time, daily, weekly, or custom frequencies. Via the `gcloud` CLI, options include `--schedule-starts`, `--schedule-repeats-every`, and `--schedule-repeats-until`.

For one-time migrations, create the job unscheduled/unrun, inspect it, and run manually. For sources under continuous writes, run recurring operations to shrink unsynchronized deltas ahead of cutover.

### Event-Driven Transfers

Event-driven transfers listen for object creation or modification events instead of repeatedly scanning the entire source:

| Source | Event Source | Destination |
|---|---|---|
| Cloud Storage | Pub/Sub subscription from Cloud Storage notifications | Cloud Storage |
| Amazon S3 | S3 Event Notifications via Amazon SQS | Cloud Storage |
| Azure Blob Storage / ADLS Gen2 | Azure Event Grid via Azure Storage Queues | Cloud Storage |

Event-driven transfers can deliver new objects to the destination in near real time when the source emits events and downstream systems are healthy. **Object deletions are not propagated by this mechanism**: deleting an object at the source does not automatically remove the same-named object at the destination.

Cloud Storage event-driven model example:

~~~mermaid
flowchart LR
    W[App writes object] --> S[Source bucket]
    S --> N[Cloud Storage notification]
    N --> T[Pub/Sub topic]
    T --> Q[Job-dedicated subscription]
    Q --> J[Event-driven STS job]
    J --> D[Destination bucket]
~~~

For event-driven transfers, the service agent needs Pub/Sub Subscriber permission on the target subscription in addition to bucket permissions. Each transfer job uses its own dedicated subscription. You can create the notification and subscription via `gcloud`, then pass `--event-stream-name` when creating the job:

~~~bash
gcloud storage buckets notifications create "gs://$SOURCE_BUCKET" \
  --topic="object-transfer-events"

gcloud pubsub subscriptions create "object-transfer-sub" \
  --topic="object-transfer-events" \
  --ack-deadline=300

gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --event-stream-name="projects/notification-project/subscriptions/object-transfer-sub"
~~~

This illustrates command structure, not complete IAM wiring. Create the topic and subscription in the right project, grant publish permission to the Cloud Storage service agent and subscribe permission to the STS service agent, and tune event stream timing parameters as needed. Never run alongside a bulk migration job without understanding duplicate-transfer rules.

### Choosing Between Scheduled and Event-Driven

- **Scheduled transfer:** fits datasets changing periodically, tolerating hours-to-days latency, or needing full source sweeps.
- **Event-driven:** fits lower-latency sync of new and modified objects; requires operating topics/queues and periodic drift checks.
- **Initial copy + incremental + cutover:** typically the safest pattern when applications keep writing to the source during migration.

## 10. Migrating from Amazon S3, Azure, and On-Premises Sources

### Amazon S3 to Cloud Storage

An agentless transfer from Amazon S3 to Cloud Storage requires:

1. Identifying AWS bucket, region, prefixes, and object classes.
2. Granting read/list permissions on the source via an STS-supported AWS auth method.
3. Granting Cloud Storage write permissions to the STS service agent at the destination.
4. Configuring overwrite, deletion, metadata preservation, and schedule.
5. Piloting a small prefix, monitoring egress/request charges, and then scaling up.

Sources use `s3://bucket/path` and destinations use `gs://bucket/path`. For AWS IAM roles, access keys, or credential files, follow current source-configuration docs. Never place access keys directly in CLI commands, READMEs, or CI logs.

### Azure Blob Storage and ADLS Gen2

STS supports Azure Blob Storage and ADLS Gen2 sources targeting Cloud Storage. Prepare source read permissions and credentials; for event-driven transfers, configure Azure Event Grid and Storage Queues to emit change notifications. Check metadata differences, naming rules, and storage tiers before copying large datasets.

### S3-Compatible Storage

For S3-compatible systems other than Amazon S3, STS uses **agent-based transfer**. Create an agent pool and deploy transfer agents with network routes to the source endpoint. Endpoints, signing regions, network protocols, and authentication methods can be configured in the transfer job.

Provision agents with adequate CPU, RAM, disk, and bandwidth to read from the source; do not treat agents as lightweight control planes. Network throughput between agents and Google Cloud is a primary determinant of transfer speed.

### Filesystems and HDFS

For on-premises filesystems, agents run on hosts able to read source paths, and jobs point to `posix:///absolute/path`. Transferring between two filesystems requires agent pools on both source/sink and an intermediate Cloud Storage bucket per STS docs. These are not agentless cloud-to-cloud object copies; design filesystem permissions and networking carefully.

## 11. Monitoring Operations and Verifying Data

### Monitoring Directly in Storage Transfer Service

Each operation reports object and byte counts copied, skipped, and failed. In the Google Cloud Console, open Storage Transfer Service → Jobs → the job → the specific run to inspect status and error details.

Basic CLI commands:

~~~bash
gcloud transfer jobs describe "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"

gcloud transfer operations list \
  --job-names="transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Distinguish an operation finishing (`DONE`) from error-free success: inspect error counts and final operation status rather than only seeing that the job finished.

### STS Integrity Checking

STS uses source checksums when available alongside metadata and in-transit checksum calculations to detect data corruption. When a source does not supply compatible checksums, STS may rely on size and stream checksums. Certain AWS S3 multipart or AWS KMS-encrypted objects lack an MD5 directly comparable to destination MD5.

This does not mean STS has verified every post-migration business requirement. Google recommends verifying additionally:

- Do the object set and object count match expectations?
- Were the intended versions/generations transferred?
- Do sizes and checksums match where comparable metadata exists?
- Were critical content types, cache policies, and custom metadata preserved?
- Are object names and paths exact for application consumption?

### Spot-Checking on GCS

Pick representative objects—small, large, special-character names, custom metadata, and objects written close to transfer time:

~~~bash
gcloud storage objects describe \
  "gs://$SOURCE_BUCKET/customers/2026/sample.json" \
  --format="json(name,size,crc32c,md5Hash,contentType)"

gcloud storage objects describe \
  "gs://$DEST_BUCKET/customers/2026/sample.json" \
  --format="json(name,size,crc32c,md5Hash,contentType)"
~~~

For large migrations, generate structured inventory reports or run verification tooling to reconcile the entire key set and risk-based checksum samples. GCS CRC32C is broadly available; MD5 is not always present, especially on composite objects. Never compare S3 ETags as if every ETag were a content MD5.

### Cloud Logging, Cloud Monitoring, and Notifications

STS integrates logs and metrics to track progress, bytes transferred, errors, and operation states. Enable Cloud Logging when creating jobs and Pub/Sub notifications for transfer events. For production, build dashboards and alerts for failed operations, permission errors, prolonged stalls, or rising error rates.

Avoid logging signed URLs, access keys, sensitive object paths, or object payloads in application logs. If logs contain sensitive object names, restrict log access and retention.

## 12. Migration Workflow for Changing Data

When writers remain active on the source, the hardest problem is not copying bytes—it is choosing the cutover moment without losing updates.

~~~mermaid
flowchart TD
    A[Inventory and prepare target] --> B[Pilot small prefix]
    B --> C[Initial bulk copy]
    C --> D[Incremental sync or event stream]
    D --> E{Delta within threshold?}
    E -->|Not yet| D
    E -->|Met| F[Freeze/quiesce writes at source]
    F --> G[Final sync and reconciliation]
    G --> H{Verification PASS?}
    H -->|No| I[Fix errors and rerun]
    I --> G
    H -->|Yes| J[Switch app to destination]
    J --> K[Monitor and keep rollback window]
~~~

### Phase 1: Initial Bulk Copy

Run a non-destructive job with appropriate prefixes and overwrite settings. Because source data may change mid-copy, the outcome is only an approximation of the source across different timestamps.

### Phase 2: Incremental Transfer

Re-run scheduled jobs or use event-driven transfer to push new/modified objects to the destination. Monitor expected lag and error counts. If a single object is overwritten frequently, understand version-selection rules before copying.

### Phase 3: Freeze and Final Sync

During the cutover window:

1. Pause writers or switch applications to read-only mode if permitted.
2. Wait for in-flight write requests to complete.
3. Run the final synchronization operation.
4. Reconcile object counts, key sets, checksums, and critical metadata.
5. Verify application access to the target bucket using the real runtime service account.
6. Switch application configuration only once all verification gates pass.

If writes cannot be frozen, you need a CDC/event-stream mechanism and explicit consistency rules. STS does not provide atomic transactions across source and sink.

### Phase 4: Cutover and Rollback

Post-cutover, monitor 403/404 errors, object read latency, and cache/CDN effects. Keep the source intact during the approved rollback window. If failing back, account for new objects written only to the destination to avoid losing updates; rollback is not as simple as flipping the bucket name back.

Apply source deletion policies only after verification finishes, the rollback window expires, and retention policies approve deletion.

## 13. Security, Compliance, and Sensitive Data

### Principle of Least Privilege

- Grant `roles/storagetransfer.user` or a custom role to operators who only run jobs.
- Grant bucket-scoped IAM to the exact STS service agent of the job-managing project.
- Grant delete permissions only when transfers have approved deletion requirements.
- Protect AWS/Azure/agent credentials; prefer short-lived or platform-managed authorization.
- Separate the migration-control project from production projects when aligned with operations.
- Audit who can modify jobs, sources/sinks, schedules, and delete options.

### CMEK and Destination Buckets

The destination bucket can use a customer-managed encryption key (CMEK) if policy requires. Ensure the Cloud Storage service agent or service identity has permission to use the key per the service encryption model and matching key location. Test reading objects post-copy using the application's identity, not just writing them.

### Retention, Holds, and Lifecycle

Object retention, legal holds, and bucket lifecycle rules affect overwrites, deletions, and retention. A transfer job does not automatically copy bucket-level policies. Configure retention/lifecycle on the destination and verify constraints before enabling deletes or overwrites.

### VPC Service Controls and Organization Policies

If buckets sit in separate service perimeters, inspect VPC Service Controls ingress/egress policies to permit transfer traffic. Organization policies such as domain restricted sharing can block cross-project service agent bindings. Investigate policy constraints before over-broadening IAM.

## 14. Performance, Quotas, and Cost

Transfer duration depends on more than total GB. Key factors:

- Object count and size distribution: millions of small objects multiply request volume.
- Source read/list throughput, quotas, and provider throttling.
- Network bandwidth to source, especially for agent-based transfers.
- How the source encrypts, stores checksums, and serves metadata.
- Change-discovery time at source and incremental job frequency.
- Retries, error rates, verification overhead, and metadata volume.

Costs can include STS processing per current pricing, Cloud Storage operations, destination storage, source egress from AWS/Azure/regions, agent VM/network charges, and logging/monitoring. Never estimate solely by byte volume when object counts or API request rates are high.

To forecast:

1. Pick a representative pilot dataset spanning both small and large objects.
2. Measure bytes/s, objects/s, error rates, and API operation counts.
3. Estimate bulk copy duration by byte size and object count, adding buffer.
4. Calculate source read/egress fees and destination storage classes.
5. Schedule transfers to avoid colliding with source production loads and cap network bandwidth if needed.
6. Monitor quotas and scale agent pools for agent-based transfers.

Do not extrapolate the speed of a few small objects as a guaranteed rate for hundreds of TB. For agent-based transfers, benchmark a sizable sample and inspect agent host NIC, CPU, and disk capacity.

## 15. Troubleshooting: From IAM Errors to Missing Data

| Symptom | Common Cause | Investigation and Fix |
|---|---|---|
| Job creation fails with Permission denied | Caller lacks STS role | Check `roles/storagetransfer.user`/`admin` on transfer project |
| Job fails reading source | Service agent lacks bucket metadata/object read | Verify exact service agent email and roles on source bucket |
| Job fails writing destination | Missing object write/read or bucket metadata permission | Grant matching roles on sink bucket; check retention/holds |
| Cross-project transfer blocked | Bucket IAM, org policy, or VPC SC blocks service agent | Check domain restrictions, service perimeters, and IAM inheritance |
| Objects skipped/not copied | Prefix/filter/time window/manifest excludes them | Inspect job spec, exact object names, generations, and filters |
| Job succeeds yet new data is missing | Writers hit source after sync; event stream ignores deletions | Run incremental/final sync and reconcile diffs |
| Objects unexpectedly overwritten | Misapplied `always`/`different` overwrite flags | Review transfer options and destination versioning |
| Cannot delete from source/sink | Missing delete permission or retention/legal hold active | Inspect bucket policies and permissions; do not bypass retention |
| Agent-based transfer is slow | Too few agents, slow source, or congested WAN | Benchmark, add agents reasonably, check CPU/disk/network |
| AWS/Azure read failures | Expired credentials or provider throttling | Check source permissions, token expiration, throttling, egress |
| Metadata/ACLs altered | Different metadata policies or UBLA settings | Inspect preservation flags and target IAM model |
| Checksums incomparable | Source lacks comparable checksum, composite object, multipart ETag | Compare available checksums, sizes, and sample payloads |

When troubleshooting, open **operation error details** first to classify permission, missing-object, quota, transient-network, or input-data issues. If errors affect only a subset of objects, you do not necessarily need a new job—fix the cause and re-run per approved policy.

## 16. Production Migration Checklist

- [ ] Object scope, total bytes, object count, prefixes, and churn profile are locked.
- [ ] Correct source/sink types are selected and transfer agent needs are confirmed.
- [ ] Owners of source, destination, and transfer projects are identified.
- [ ] Destination bucket has approved location, storage class, IAM, encryption, and lifecycle.
- [ ] Exact STS service agent email is retrieved and granted bucket-scoped roles.
- [ ] Secure credentials exist for AWS, Azure, or transfer agents.
- [ ] Prefix filters, manifests, and versioning behavior are reviewed.
- [ ] Overwrite, delete, and metadata preservation rules are approved.
- [ ] Representative pilot succeeded and results were reconciled.
- [ ] Dashboards/alerts monitor operations, bytes, errors, and stalled progress.
- [ ] Egress, API operations, target storage, and agent costs are estimated.
- [ ] Incremental sync or event-driven transfer is designed if source stays writable.
- [ ] Freeze window, final sync, cutover owner, and success criteria are defined.
- [ ] Checksums, key sets, metadata, and application access are verified.
- [ ] Rollback window is active; source is untouched until verification completes.
- [ ] Handover docs cover job names, operations, alerts, and runbooks.

## 17. Applied Exercise

Suppose an enterprise has 12 TB of images and JSON files in a legacy Cloud Storage project. The application adds roughly 50 GB daily. The goal is moving to a new project and a region closer to users without losing images or disrupting service for more than one hour.

Design the steps:

1. Inventory objects by prefix, size, metadata, and write rate.
2. Create the destination bucket with the proper location and policies; confirm IAM conditions.
3. Grant STS service agent permissions on both buckets.
4. Pilot a small prefix with `--do-not-run`, review, and trigger manually.
5. Run non-destructive bulk transfer.
6. Use scheduled incremental jobs or event-driven transfer to shrink the delta.
7. In the cutover window, stop writers, run final sync, reconcile key sets and checksums, and verify the application.
8. Switch bucket configuration in the application, monitor 403/404s and latency, and keep the rollback path open.

Open question: if the source keeps receiving continuous writes and cannot tolerate a one-hour freeze, which mechanism syncs new objects, and how do you handle deleted objects? Hint: event-driven transfers do not automatically propagate delete events; you need a reconciliation workflow and a controlled deletion policy.

## 18. Conclusion

Storage Transfer Service moves object data across supported sources with schedulable, observable, and repeatable jobs. Between Cloud Storage, Amazon S3, Azure, and select cloud sources, the service manages workers automatically; for filesystems, HDFS, and S3-compatible stores, an agent pool is required. Success hinges on service agent IAM design, overwrite/delete settings, metadata handling, and post-copy validation.

In real migrations, follow **inventory → pilot → bulk copy → incremental → final sync → verify → cutover → monitor**. Retain source data until verification is complete and the rollback window closes. STS is the data-movement engine, while business consistency and cutover decisions must still be designed, approved, and tested by the application-owning team.

## References

- [Storage Transfer Service overview](https://docs.cloud.google.com/storage-transfer/docs/overview)
- [Supported sources and sinks](https://docs.cloud.google.com/storage-transfer/docs/sources-and-sinks)
- [Create transfers](https://docs.cloud.google.com/storage-transfer/docs/create-transfers)
- [Transfer between Cloud Storage buckets](https://docs.cloud.google.com/storage-transfer/docs/cloud-storage-to-cloud-storage)
- [Required user permissions](https://docs.cloud.google.com/storage-transfer/docs/iam-user)
- [Configure Cloud Storage source access](https://docs.cloud.google.com/storage-transfer/docs/source-cloud-storage)
- [Configure Cloud Storage destination access](https://docs.cloud.google.com/storage-transfer/docs/sink-cloud-storage)
- [Agent-based project-level permissions](https://docs.cloud.google.com/storage-transfer/docs/iam-agent-based)
- [Manage transfers](https://docs.cloud.google.com/storage-transfer/docs/manage-transfers)
- [Transfer specific files or objects using a manifest](https://docs.cloud.google.com/storage-transfer/docs/manifest)
- [Event-driven transfers](https://docs.cloud.google.com/storage-transfer/docs/event-driven-transfers)
- [Event-driven transfers from Cloud Storage](https://docs.cloud.google.com/storage-transfer/docs/event-driven-google)
- [Data integrity](https://docs.cloud.google.com/storage-transfer/docs/data-integrity)
- [Storage Transfer Service pricing](https://cloud.google.com/storage-transfer/pricing)
