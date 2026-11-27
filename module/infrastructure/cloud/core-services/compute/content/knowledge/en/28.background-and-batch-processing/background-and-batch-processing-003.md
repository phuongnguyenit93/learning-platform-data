# Job Definitions, Execution Environments, and Task Inputs

In background and batch processing, a **job definition** describes how a piece of work will be run: which program or container image is used, how much CPU and memory are required, what startup command to invoke, which permissions are granted, and how input data is passed. When a data batch needs processing, the system creates a job run from that definition, provides specific inputs, and places the work into a queue or scheduler.

Three components should be distinguished:

- **Job definition:** a versioned description of the run configuration, typically reused across many runs.
- **Execution environment:** the resources and context where the job actually executes, including machine or runtime, container, operating system, networking, identity, storage capacity, and resource limits.
- **Task inputs:** data and parameters specific to a single run, such as the date range to process, object URI, customer ID, partition, or batch identifier.

Clearly separating these three components enables reproducible runs, permission control, worker scaling, and failure investigation. This is an essential capability in cloud compute models, where jobs can run on virtual machines, containers, or managed environments without operators managing servers directly.

## 1. Job definitions and job runs

A job definition is a configuration template describing the work. It typically specifies:

- The image or program package to execute.
- Startup command, entrypoint, and default arguments.
- CPU, memory, GPU, or specialized resources.
- Environment variables, application configuration, and secret references.
- Permissions to access services, storage, queues, and APIs.
- Mounted volumes or temporary storage areas.
- Networking requirements, deployment zones, and placement constraints.
- Default retry policies, timeouts, logging, and output locations.

A **job run** supplies concrete data for a specific processing request. The same job definition can be used for many different batches, each with its own parameters, input objects, and correlation ID.

For example, a `daily-sales-aggregation` definition might always run the revenue aggregation program. The run for 2026-11-21 passes processing date `2026-11-21`, the input manifest URI, and a dedicated output path. The next day, another run can be created from the same definition with the new date and manifest.

~~~mermaid
flowchart TD
    A["Job definition<br/>image, command, resources, permissions"] --> C["Submit job"]
    B["Run inputs<br/>parameters, object URI, batch ID"] --> C
    C --> D["Queue / scheduler"]
    D --> E["Execution environment"]
    E --> F["Task attempt"]
    F --> G["Read input and process"]
    G --> H["Write output / status"]
    H --> I["Job result"]
~~~

A job definition should change only when logic or platform configuration needs updating. Data that varies per run should be passed into the invocation/job submission rather than modifying the definition for every batch.

## 2. Distinguishing jobs, tasks, attempts, and workers

Platforms use different terminology, but the following conceptual model can be used:

| Concept | Meaning | Example |
|---|---|---|
| Job definition | Configuration template for creating work | Image, command, CPU, memory, role, and retry policy |
| Job | A specific processing request submitted to the system | Aggregate revenue for 2026-11-21 |
| Task or task unit | Executable unit of work; sometimes a single container run | Process one partition or one file |
| Attempt | One execution try of a job/task | First try failed due to timeout; second try runs again |
| Worker | Process or resource that claims and executes work | Worker container running on a node |

A job can have just one task, or be divided into many independent tasks. For example, a job processing 1,000 files can create 100 tasks, each processing 10 files. When one task fails, the system can retry only that task rather than rerunning the entire batch, if supported by the architecture and orchestration tool.

Do not assume these names are identical across all providers. In AWS Batch, a job is submitted from a job definition and may run in one or more containers depending on job type. In Kubernetes, a Job manages Pods to complete a finite task; the Pod is the concrete execution unit. In Google Cloud Batch, a job consists of tasks and task groups run on resources provisioned for the job. When reading platform documentation, identify clearly which object is submitted, which object the scheduler creates, and which object is retried.

## 3. Job execution environment

The execution environment is where the program runs after the scheduler accepts the job. It includes both compute infrastructure and the services and configurations enabling the job to operate.

### 3.1. Compute infrastructure

Jobs can run on:

- **Virtual machines or node pools:** the provider or operator provisions machines, OS, and management agents. Machine types can be selected by CPU, RAM, GPU, local SSD, and availability zone.
- **Containers on managed clusters:** jobs run inside containers on nodes managed by an orchestration service. Images package the application and its dependencies.
- **Serverless or fully managed batch environments:** users declare the job and resource requirements; the provider manages provisioning, scheduling, and reclaiming infrastructure within service capabilities.

Virtual machines allow deep control over the OS and base software, but increase patching, maintenance, and capacity management effort. Containers provide consistent application packaging, though you still must understand nodes, images, networking, and resources. Managed batch services reduce server operations; in return, users must adhere to runtime limits, supported regions, instance types, and the service's pricing model.

### 3.2. Runtime and dependencies

The execution environment must clearly specify:

- Operating system and CPU architecture, such as Linux x86-64 or ARM64.
- Runtime such as Java, Python, Node.js, or .NET if the program runs directly on the host.
- Library and dependency versions.
- Locale, timezone, CA certificates, and required system configuration.
- Image digest or artifact version to avoid running unintended code.
- Temporary disk space, working directory, and file descriptor limits if relevant.

Container images should be built once, tested, and released using immutable digests. Using mutable tags like `latest` can cause two runs of the same job definition to execute different image contents if the tag gets updated.

### 3.3. Resources and scalability

The job definition should describe realistic resource needs. For example:

- CPU for decompression, data transformation, and computation.
- Memory for working set size and concurrently processed records.
- GPU for models or accelerated algorithms.
- Ephemeral storage for intermediate files.
- Network bandwidth and connection counts to databases, object storage, or APIs.

If CPU or memory is under-provisioned, the job may run slowly, get throttled, or suffer OOM kills. If requested too high, the scheduler struggles to place tasks on suitable nodes and per-task cost rises. For parallel jobs, total resources are roughly concurrent tasks multiplied by per-task requirements; account for headroom and quota limits.

### 3.4. Networking, identity, and storage

The execution environment must reach the exact services it needs:

- Subnets, routes, DNS, firewalls/security groups, and service endpoints.
- Runtime identity or task role with least-privilege permissions.
- Secrets fetched from a secret manager at runtime.
- Volumes or object storage to read inputs and write outputs.
- Logs and metrics shipped to the monitoring system.

Do not bake access keys, database passwords, or tokens into images. Job permissions should be scoped to resources and actions, such as reading only the input prefix and writing only the output prefix designated for that batch.

## 4. Task inputs

Inputs define the exact work a single run must execute. They can be grouped into categories:

| Input category | Examples | Common passing mechanism |
|---|---|---|
| Business parameters | Start/end dates, tenant ID, report type | CLI arguments, job parameters, or payload |
| Data identifiers | Object URI, bucket/key, database partition, manifest | URI or ID reference; do not pass large files directly in commands |
| Processing configuration | Batch size, output format, dry-run mode | Config file or parameter store |
| Correlation info | Job ID, batch ID, correlation ID | Metadata or environment variables |
| Access secrets | Required credentials or tokens | Secret manager or identity federation |
| Control signals | Partition index, shard count, retry attempt | Task metadata or runtime parameters |

Distinguish between **parameters** and **data**. Parameters are usually small and describe how to process; data can be large and lives in object storage, databases, or streams. Passing an object URI instead of the whole file in the payload reduces message size, avoids API limits, and lets workers fetch data on demand.

An input manifest can list the objects to process:

~~~json
{
  "batchId": "sales-2026-11-21",
  "businessDate": "2026-11-21",
  "inputVersion": "v3",
  "objects": [
    "s3://company-data/sales/date=2026-11-21/part-0001.parquet",
    "s3://company-data/sales/date=2026-11-21/part-0002.parquet"
  ],
  "outputPrefix": "s3://company-results/sales/date=2026-11-21/",
  "schemaVersion": 3
}
~~~

Manifests should include versions, checksums, or source identifiers when reproducibility is required. If input data changes after a job is submitted, the job may produce different results even with identical parameters. Object versions, immutable keys, or checksums can freeze the input set for a run.

## 5. Input validation and verification

A job should not blindly trust data passed by a caller. Before processing, validate:

1. **Schema:** required fields are present, have the right types, and match the expected version.
2. **Value ranges:** valid dates, batch size within bounds, non-negative partition counts.
3. **Ownership:** the caller is authorized to request processing for the specified tenant or customer.
4. **Resources:** file sizes, object counts, and total data volume are within designed limits.
5. **Data source:** objects exist, match expected versions/checksums, and have compatible formats and schemas.
6. **Safety:** filenames and URIs do not allow arbitrary path traversal or out-of-scope resource access.
7. **Consistency:** manifest and batch metadata point to the same data snapshot or version.

For invalid inputs, reject the job early and return a clear error. Do not let workers run for a long time only to discover a missing field or invalid permission. Error logs should include the job ID, field name, or error code, without logging secrets or entire sensitive payloads.

## 6. Example of defining and submitting a job in the batch model

Suppose a data team needs to run a daily revenue aggregation program. Each run processes an input manifest and writes results to a dedicated prefix.

The YAML example below is a **conceptual model** illustrating the fixed definition versus per-run inputs. It is not a direct schema for submitting to a specific provider.

~~~yaml
jobDefinition:
  name: daily-sales-aggregation
  version: "7"
  image: registry.example.com/data/sales-aggregator@sha256:IMAGE_DIGEST
  command:
    - python
    - -m
    - sales_aggregator
  resources:
    cpu: "2"
    memory: "4Gi"
    ephemeralStorage: "10Gi"
  runtime:
    architecture: amd64
    operatingSystem: linux
  identity:
    role: sales-batch-runtime
  environment:
    LOG_LEVEL: INFO
  retry:
    attempts: 3
  timeoutSeconds: 1800

jobRun:
  name: sales-2026-11-21
  parameters:
    businessDate: "2026-11-21"
    inputManifest: "s3://company-data/manifests/sales-2026-11-21.json"
    outputPrefix: "s3://company-results/sales-2026-11-21/"
  metadata:
    batchId: "sales-2026-11-21"
    schemaVersion: "3"
~~~

The job definition holds the image, command, resources, identity, and retry policy. The job run carries the specific business date, manifest, and output prefix. When releasing a new image, the team can create a new definition version; earlier runs remain traceable to older versions.

With AWS Batch, a registered job definition is referenced when submitting a job. Illustrative command:

~~~bash
aws batch submit-job \
  --job-name sales-2026-11-21 \
  --job-queue analytics-queue \
  --job-definition daily-sales-aggregation:7 \
  --parameters businessDate=2026-11-21,inputManifest=s3://company-data/manifests/sales-2026-11-21.json
~~~

The queue name, job definition, and parameters must exist in the target account/region; examples must be adjusted to match real configurations. Container overrides can be declared using the appropriate API/CLI options. Do not pass secrets in command-line parameters because they may appear in logs or command histories.

## 7. Splitting inputs across multiple tasks

When data is large, a job can be split into multiple parallel tasks. Two common approaches:

- **List-based splitting:** each task receives a subset of object or record IDs.
- **Partition-based splitting:** each task receives a partition index or key range to read a slice of data.

For example, with 120 files and 12 desired tasks, each task receives 10 files from the manifest. Ensure groups do not overlap and cover the entire input. If file sizes vary greatly, splitting by file count can cause imbalance; consider splitting by byte size or estimated processing weight.

~~~mermaid
flowchart TD
    A["Input manifest: 120 files"] --> B["Partition planner"]
    B --> C["Task 0: files 1-10"]
    B --> D["Task 1: files 11-20"]
    B --> E["Task 2: files 21-30"]
    B --> F["..."]
    B --> G["Task 11: files 111-120"]
    C --> H["Output partition 0"]
    D --> I["Output partition 1"]
    E --> J["Output partition 2"]
    G --> K["Output partition 11"]
    H --> L["Validate and aggregate"]
    I --> L
    J --> L
    K --> L
~~~

If one task fails, only that partition needs retrying when outputs are written under deterministic keys and operations are idempotent. Each task should record its partition ID, input range, attempt, and output reference for investigation.

Prevent two workers from overwriting the same output uncontrollably. Use output keys containing both batch ID and partition ID, write to temporary paths, and commit a result manifest upon task completion. The final aggregation step reads only partitions confirmed as successful.

## 8. Versioning and reproducibility

A job may need to be rerun weeks later to investigate discrepancies or regenerate reports. To make results reproducible, store enough metadata to know exactly what the run used:

- Job definition name and revision/version.
- Container image digest or artifact checksum.
- Runtime architecture and dependency versions.
- Input parameters and schema version.
- Input manifest, object versions, or checksums.
- Critical business configurations and model/rule versions.
- Runtime identity, queue, region, and associated resource types.
- Job ID, task ID, attempt, start/end timestamps, and outcome.

Do not store secrets directly in job history. Store secret names or version references while enforcing proper access permissions and retention policies. For audited data, keep manifests and metadata immutable or backed by an audit trail.

If a definition changes between two runs, create a new version rather than silently mutating the active configuration. When rerunning an old batch, operators can explicitly choose the old or new version and document the reason.

## 9. Retries, timeouts, and error handling

Batch jobs generally run longer than synchronous requests and can hit infrastructure or data errors. Retry policies should distinguish:

- **Transient errors:** network errors, throttling, temporarily unavailable dependencies. Retry with exponential backoff and jitter.
- **Input errors:** invalid schema, missing files, invalid permissions. Usually require fixing data or configuration before rerunning.
- **Logic errors:** bugs or unhandled business conditions. Log, halt, or route to an investigation queue.
- **Resource errors:** OOM, CPU starvation, out of temp disk space, or timeouts. Adjust resources or split work into smaller pieces.

Timeouts should be based on expected processing times plus reasonable headroom. If a job can run for hours, consider checkpointing to resume from the latest partition or step. Retrying an entire massive job can be expensive and produce duplicate outputs.

Set explicit max attempts, backoff, timeouts, and dead-letter/failure queues. Once retries are exhausted, persist the final status, error code, last attempt, and metadata needed for controlled replay. Never retry input or logic errors indefinitely.

## 10. Securing inputs and execution environments

Jobs frequently process large or internal datasets, so both inputs and runtime environments must be protected:

- Grant least-privilege permissions to the job role; separate input read and output write permissions.
- Use a secret manager or workload identity instead of static keys.
- Encrypt data in transit and at rest per organizational policy.
- Allow network egress only to required services; consider private endpoints.
- Validate object URIs, tenant IDs, and ownership before reading.
- Never place personal data, tokens, or secrets in command lines, tags, or logs.
- Scan images, pin image digests, and update dependencies in a controlled manner.
- Clean up temporary files and intermediate data according to retention policies.
- Limit concurrency and quotas so a job cannot exhaust shared resources.

For multi-tenant data, do not rely on caller-supplied prefixes to enforce authorization. The application must validate the tenant from trusted metadata and enforce permissions at the data access layer.

## 11. Monitoring and verifying a run

A successful submission only means the scheduler accepted the request. It does not guarantee the job ran, read the right inputs, or wrote complete outputs.

A verification procedure should include:

1. **After submission:** record the job ID, definition revision, and submitted parameters; confirm the job entered the right queue.
2. **When scheduled:** verify the execution environment was provisioned, the image pulled cleanly, and the container started.
3. **During execution:** monitor CPU, memory, disk, network, elapsed time, record/file counts, and per-task logs.
4. **Upon completion:** verify exit codes, job status, succeeded/failed task counts, and the output manifest.
5. **Post-completion:** check output counts, checksums, schema, and business rules; reconcile against inputs.
6. **On failure:** retain job ID, attempt, task ID, logs, and input manifest for debugging; replay only according to retry policy.

With AWS Batch, job and queue details can be inspected using:

~~~bash
aws batch describe-jobs --jobs JOB_ID
aws batch describe-job-queues --job-queues analytics-queue
~~~

With Kubernetes Jobs, Job status, Pods, and logs can be inspected using:

~~~bash
kubectl describe job sales-aggregation -n batch
kubectl get pods -n batch -l job-name=sales-aggregation
kubectl logs JOB_POD_NAME -n batch
~~~

These commands identify orchestration and runtime status. You must still inspect output data and business metrics to conclude the batch succeeded.

Useful metrics include queue wait time, scheduling delay, job duration, task success/failure, retry count, CPU/memory utilization, OOMs, disk usage, input/output bytes, records processed, throughput, and cost per batch.

## 12. Job design checklist

- [ ] Job definition has a clear name and version describing the image/artifact, command, and resources.
- [ ] Images are pinned by digest or artifacts have checksums.
- [ ] Execution environment accurately specifies architecture, runtime, dependencies, networking, and storage.
- [ ] CPU, memory, GPU, and ephemeral storage match processing volume.
- [ ] Job role has only required permissions for inputs, outputs, and dependencies.
- [ ] Inputs have clear schemas, versions, validation, and data identifiers.
- [ ] Large files are passed via object URIs/manifests instead of embedded in payloads.
- [ ] Input manifests are immutable or have versions/checksums for run reproducibility.
- [ ] Jobs/tasks have correlation IDs, attempts, and dedicated output locations.
- [ ] Appropriate partitioning, concurrency, and retry strategies are chosen.
- [ ] Timeouts, backoff, dead-letter handling, and checkpoints are defined.
- [ ] Outputs are verified for status, counts, checksums, and business correctness.
- [ ] Logs and metrics are sufficient for tracing without containing secrets or sensitive data.

Job definitions standardize how work runs; execution environments provide the compute capacity and permissions for programs to operate; inputs specify the exact work of each run. When all three parts are versioned, inputs are validated, resources are bounded, and per-attempt metadata is recorded, a batch system can scale in parallel while maintaining reproducibility, security, and cost control.
