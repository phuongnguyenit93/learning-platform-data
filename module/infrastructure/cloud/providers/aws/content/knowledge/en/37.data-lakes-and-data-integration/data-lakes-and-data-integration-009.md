# Amazon EMR on EC2, EKS, and Serverless

Amazon EMR is AWS's platform for running distributed data processing frameworks such as Apache Spark, Apache Hadoop, Hive, Trino, and other engines supported per deployment model. EMR powers large-scale data lake processing, ETL, batch analytics, interactive querying, and certain streaming workloads. When designing a system, data teams have three primary deployment options: **EMR on EC2**, **EMR on EKS**, and **EMR Serverless**.

All three options share Amazon EMR's optimized runtimes, yet differ in compute management, workload isolation, and cost models. EMR on EC2 gives full control over clusters and hardware; EMR on EKS runs jobs inside Kubernetes namespaces to share infrastructure with containerized workloads; and EMR Serverless automatically provisions workers on demand for Spark/Hive applications. Choosing the right model requires evaluating job frequency, runtime duration, customization needs, operational skills, security requirements, compute sharing, and total cost.

This lesson covers the architecture of each model, storage and compute selection, IAM/networking, autoscaling, operations, reliability, and cost. The comparison also highlights key service boundaries: EMR Serverless does not provide HDFS; Spark Structured Streaming on EMR Serverless runs in a dedicated mode; and EMR on EKS can run Spark and Flink depending on the supported release/submission model.

## 1. Learning Objectives

After this lesson, you can:

- Explain Amazon EMR's role in data lakes and the AWS ecosystem.
- Distinguish EMR on EC2, EMR on EKS, and EMR Serverless across compute, control plane, storage, scaling, and billing.
- Design an EMR on EC2 cluster with primary, core, and task nodes, using instance groups or instance fleets.
- Select HDFS, S3A, EBS, and local storage based on data lifecycle.
- Create a virtual cluster on EKS and understand namespaces, job runs, execution roles, and pod scheduling.
- Distinguish Spark Operator, Flink Kubernetes Operator, and the `StartJobRun` model.
- Configure EMR Serverless applications, worker sizes, maximum capacity, pre-initialized capacity, and auto-stop.
- Select deployment models for batch, interactive, streaming, long-running, and multi-tenant workloads.
- Integrate S3, Glue Data Catalog, Lake Formation, IAM, KMS, and VPC.
- Monitor jobs, troubleshoot failures, optimize compute, and estimate costs.
- Establish safe deployment, upgrade, rollback, and resource cleanup workflows.

## 2. Amazon EMR in a Data Lake Architecture

Amazon EMR provides AWS-optimized runtimes for open-source frameworks. The service typically sits at the compute/processing layer in a data lake architecture:

    Data producers
      |  application events / database exports / files
      v
    Amazon S3 data lake
      |
      +---- AWS Glue Data Catalog
      |
      +---- AWS Lake Formation permissions
      |
      v
    Amazon EMR
      |  Spark / Hive / Trino / Hadoop / Flink
      |
      +---- Transform / join / aggregate / validate
      |
      +---- S3 curated zone / Apache Iceberg / Hudi / Delta
      |
      +---- Data warehouse / search / serving systems
      |
      v
    Athena / Redshift / SageMaker / BI / applications

EMR is not required to store all data long term. In a decoupled storage-and-compute architecture, raw, standardized, and curated data usually reside in S3; EMR provisions compute to read, process, and write outputs. This design lets multiple clusters and jobs share datasets and allows stopping compute without deleting the data lake.

### 2.1 Related Components

| Component | Role in Architecture |
|---|---|
| Amazon S3 | Stores raw, staging, curated, checkpoints, logs, and artifacts |
| AWS Glue Data Catalog | Database/table/schema metadata for Spark, Hive, Athena, and integrated engines |
| AWS Lake Formation | Manages fine-grained data access permissions on catalog/table/column/row/cell via supported integrations |
| Amazon EMR | Distributed processing runtime |
| Amazon EKS | Kubernetes control plane and compute orchestration for EMR on EKS |
| Amazon EC2 | Compute nodes for EMR on EC2 or EKS worker nodes |
| Amazon EBS | Block storage attached to EC2 nodes, used for scratch or HDFS per configuration |
| Amazon CloudWatch | Metrics, logs, dashboards, and alarms |
| AWS IAM | Service roles, runtime/job roles, and operator permissions |
| AWS KMS | Encryption keys for data, volumes, buckets, and secrets |
| AWS Step Functions / MWAA | Pipeline orchestration and inter-job dependencies |

### 2.2 Frameworks vs. Deployment Models

A framework is the engine or library executing computations; the deployment model decides where and how infrastructure is provisioned:

- Apache Spark: batch, SQL, ML, and Structured Streaming.
- Apache Hive: SQL/data warehouse workloads per supported version.
- Trino: interactive distributed querying when supported by the release/deployment model.
- Hadoop/MapReduce: batch processing and Hadoop ecosystem workloads.
- Apache Flink: stream processing; can run on EMR on EC2 and EMR on EKS per compatible releases.

Not every framework is available across all three models. EMR Serverless application types currently focus on Spark and Hive. EMR on EKS supports Spark jobs and the Flink operator in documented releases. Verify release labels, Regions, connectors, and submission models before choosing an engine.

## 3. Comparing the Three Deployment Models

| Criterion | EMR on EC2 | EMR on EKS | EMR Serverless |
|---|---|---|---|
| Compute | EC2 instances inside an EMR cluster | Pods on EKS worker capacity | Workers provisioned by the service per job/application |
| Management unit | Cluster | EKS cluster, namespace, EMR virtual cluster, job run | Application and job run |
| Infrastructure | User selects instances, storage, network, and lifecycle | User manages EKS cluster/node capacity; EMR manages runtime/job integration | No EC2/Kubernetes cluster management for jobs |
| Frameworks | Many Hadoop ecosystem applications per release | Spark and Flink per supported release/submission model; verify other capabilities | Spark and Hive; Spark Structured Streaming has a dedicated mode |
| Long-running services | Fits persistent clusters and interactive workloads | Fits jobs or services running on EKS per supported framework | Fits Spark batch and streaming jobs; applications manage workers |
| Infrastructure customization | High: instance types, AMIs, bootstrap actions, EBS, daemons | High via EKS/node/pod templates; runtime follows EMR release | Lower; configure workers, custom images, and application settings |
| Scaling | Managed scaling, instance groups/fleets, Auto Scaling | Kubernetes scheduler, node autoscaling, and EMR job controls | Automatic worker provisioning, maximum capacity, dynamic allocation |
| Isolation | Cluster/role/security group | Namespace, pod, IAM job execution role | Application and job runtime role |
| Operations | Manage cluster lifecycle, patches/releases, capacity | Requires Kubernetes/EKS skills, quotas, node pools, and networking | Minimal compute management; still manage apps, roles, data, and jobs |
| Storage | HDFS, S3A, EBS, local disk | Primarily S3/object storage and pod ephemeral storage; persistent volumes per EKS design | No HDFS support; uses S3/data services and temporary local worker disk |
| Cost | EMR charge + EC2/EBS/network/related services | EMR uplift per vCPU/memory + EKS + EC2/Fargate/storage/network | Worker vCPU, memory, and storage by usage duration; plus pre-initialized idle capacity if enabled |
| When appropriate | Stable workloads, deep customization, HDFS, or diverse frameworks | Organizations already running EKS wanting shared compute/observability/guardrails | Intermittent jobs, spiky traffic, minimal cluster management |

### 3.1 Quick Selection Rules

- Choose **EMR on EC2** when you need control over instances/AMIs/bootstraps, long-lived clusters, diverse frameworks, HDFS, or cluster-level Spot/managed scaling optimization.
- Choose **EMR on EKS** when your organization already operates Kubernetes, needs multi-tenant namespaces, shares compute with container apps, and wants Kubernetes tooling for Spark/Flink.
- Choose **EMR Serverless** when workloads are mostly scheduled or event-driven Spark/Hive jobs with fluctuating load and you want to avoid maintaining clusters.

Never choose solely based on clichés like "serverless is always cheaper" or "Kubernetes always has higher utilization." Total cost depends on utilization, wait times, worker sizing, cluster idle time, EKS overhead, Spot usage, pre-initialized capacity, and operational overhead.

## 4. EMR on EC2: Cluster Architecture

EMR on EC2 provisions a cluster of EC2 instances. EMR installs frameworks and management components on the nodes, then schedules jobs via YARN or the corresponding runtime.

### 4.1 Three Node Types

| Node Type | Responsibility | HDFS Storage | Typical Role |
|---|---|---|---|
| Primary | Manages cluster, YARN ResourceManager, HDFS NameNode, and job tracking | Metadata/control role | Coordination and management |
| Core | Runs tasks/executors and HDFS DataNode | Yes | Compute + intermediate data storage |
| Task | Runs additional tasks/executors | No HDFS storage | Elastic compute scaling |

Small clusters may have a single primary node. Critical production clusters can use three primary nodes for high availability of supported coordination components. Core nodes contribute both compute and HDFS storage, so shrinking core nodes can affect both compute and storage capacity. Task nodes provide compute only, making them ideal for elastic capacity, especially with Spot.

### 4.2 Instance Groups and Instance Fleets

EMR offers two ways to organize EC2 node groups:

**Instance groups**

- Each group uses a single instance type.
- Instances can be added/removed in core/task groups.
- Simple and predictable configuration.
- Suitable when workloads have relatively uniform hardware profiles.

**Instance fleets**

- Each fleet can include multiple instance types.
- Specify On-Demand and Spot target capacities.
- EMR selects an instance mix to meet target capacity.
- Supports allocation strategies for On-Demand and Spot.
- Improves capacity acquisition when one instance pool lacks supply or Spot experiences interruptions.

Instance groups and instance fleets are chosen at cluster creation; you cannot convert between them after the cluster is created. Decide based on instance type flexibility, capacity resilience, and Spot management requirements.

### 4.3 Selecting Instance Types

Select instances based on workload characteristics:

| Workload | Resources to Prioritize |
|---|---|
| Large Spark SQL/joins | Memory, CPU, network, and shuffle I/O |
| ML preprocessing | CPU, memory, local disk, and network |
| Shuffle-intensive | Network bandwidth and EBS/local I/O |
| HDFS-heavy | Core node storage capacity and throughput |
| Interactive Trino | Stable CPU, memory, and network |
| Compression/encryption | CPU and appropriate vector instructions |

Do not choose instances solely by vCPU count. Measure executor memory, GC, spill, shuffle read/write, network, EBS throughput, and skew. For memory-heavy workloads, instances with larger RAM can lower total cost by reducing executor counts or disk spill.

### 4.4 On-Demand and Spot

On-Demand fits primary/core capacity requiring stability and workloads that cannot tolerate interruptions. Spot fits task capacity or jobs equipped with checkpoints/retries and safe rerun capabilities.

Best practices:

- Keep primary nodes and essential core capacity on On-Demand when stability is required.
- Use Spot for task nodes or replaceable compute capacity.
- Diversify across multiple instance types/pools to reduce dependence on a single pool.
- Pick capacity-prioritized allocation strategies when workloads are interruption-sensitive.
- Design Spark jobs with retries/checkpoints and idempotent outputs.
- Never store the sole copy of critical data on local disk or HDFS if the cluster can terminate.

Instance fleets support allocation strategies such as `price-capacity-optimized`, `capacity-optimized`, `capacity-optimized-prioritized`, `diversified`, and `lowest-price` depending on configuration/release. From EMR release 6.10.0 onward, `price-capacity-optimized` is the default for Spot fleets per current documentation. `lowest-price` can increase interruptions by picking the cheapest pool without considering capacity depth.

### 4.5 Managed Scaling

EMR managed scaling automatically adjusts EC2 instance or unit counts based on workload metrics to balance cost and speed. Operators configure minimum/maximum capacity, On-Demand/Spot caps, and scaling bounds.

Managed scaling can scale down capacity when workloads finish, yet it does not replace sound job design. If one executor holds resources due to skew or a job fails to release containers, the cluster may remain scaled up. Inspect YARN pending containers, Spark executor states, and utilization before raising max capacity.

### 4.6 Auto Scaling and Custom Scaling

EMR also supports automatic scaling driven by CloudWatch metrics and user-defined scaling policies. Use this when behavior must be more tailored than managed scaling or when custom metrics better reflect workload demand. Avoid configuring conflicting scaling policies targeting the same instance group.

## 5. Storage on EMR EC2

### 5.1 HDFS

HDFS is a distributed file system hosted across core nodes. It helps for intermediate data, caching, and workloads repeatedly reading the same dataset. HDFS offers compute locality, yet its lifecycle is tied to the cluster. Once the cluster terminates, HDFS data and local disks are gone.

Never use HDFS as the sole persistent store for raw/curated data that must survive across clusters. Write durable outputs to S3 or another persistent store.

### 5.2 Amazon S3 and S3A

S3 provides durable object storage decoupled from compute. EMR reads and writes S3 via a filesystem connector. Starting with EMR release 7.10.0, S3A replaced EMRFS as the default S3 connector. Older releases differ in behavior and settings; verify schemes, connectors, and compatibility before upgrading.

S3 suits raw/landing zones, curated data, Iceberg/Hudi/Delta table data, checkpoints, event logs, artifacts, and job outputs. It enables sharing datasets across multiple clusters/jobs and preserves data after compute stops.

### 5.3 Local Disk and EBS

Local instance store fits scratch, cache, and temporary shuffle storage. Data on instance store is lost when instances terminate. EBS provides attached block storage with a lifecycle distinct from instance store; however, cluster-attached EBS volumes incur charges and must follow cleanup lifecycles.

Do not confuse HDFS/local disk with S3. If a job fails after cluster termination, intermediate data on local storage may be lost. Store recoverable data in S3 or durable storage.

### 5.4 Choosing Storage by Pattern

| Pattern | Recommended Option |
|---|---|
| Read once, process, and write results | S3A |
| Iterative algorithms reading the same data repeatedly | Cache/HDFS or appropriate local storage |
| Heavy Spark shuffles | Local disk/EBS scratch based on benchmarks |
| Data shared across multiple clusters | S3 |
| Transactional data lake tables | S3 + Iceberg/Hudi/Delta per engine support |
| Temporary staging | Local/EBS if loss on cluster termination is acceptable |

### 5.5 S3 Layout, Partitioning, and File Sizing

Organize S3 prefixes by domain, zone, table, and partition keys. Avoid overly granular partitions or excessive small files that inflate metadata overhead, listing latency, and query planning time. Use compaction to merge small files; choose partitions based on query patterns rather than partitioning by every column.

In Spark, too many output tasks can generate thousands of small files. Tune shuffle partitions, `coalesce`/`repartition`, file rolling, and table format settings. For Iceberg/Hudi/Delta, run their respective compaction/maintenance operations.

## 6. EMR on EKS: Architecture and Concepts

EMR on EKS runs EMR runtimes inside pods on an Amazon EKS cluster. Organizations can share EKS compute between data workloads and containerized applications while using namespaces and IAM execution roles for tenant isolation.

### 6.1 EKS Cluster, Namespace, and Virtual Cluster

| Concept | Meaning |
|---|---|
| EKS cluster | Kubernetes control plane and worker capacity |
| Kubernetes namespace | Logical boundary for workloads, service accounts, quotas, and resources |
| EMR virtual cluster | A namespace registered with EMR for job submissions |
| Job run | A single execution of a Spark/Flink application per submission model |
| Job execution role | IAM role assumed by jobs/pods to access AWS resources |

A virtual cluster is simply a namespace registration with EMR; the virtual cluster itself creates no continuously running compute resources and carries no separate charge. EKS cluster, worker node, storage, networking, and EMR runtime charges still apply per consumed resources.

A single EKS cluster can host multiple namespaces/virtual clusters, with each virtual cluster mapping to one namespace. Namespace separation alone does not guarantee complete isolation; pair it with Kubernetes RBAC, IAM, network policies, resource quotas, pod security, and job execution roles.

### 6.2 Spark Job Execution Flow

    Data engineer / Scheduler
              |
       StartJobRun API
              |
       EMR virtual cluster
              |
       Kubernetes namespace
              |
       Kubernetes scheduler
              |
       Driver pod + Executor pods
              |
       EMR runtime container image
              |
       S3 / Glue / Lake Formation / sinks

When a job is submitted, EMR on EKS requests pods from the Kubernetes scheduler. Container images package the base OS, Spark, and EMR release dependencies. If the image is cached on nodes, subsequent runs avoid re-pulling it. Once the job finishes, pods terminate; logs and event logs can be stored in S3/CloudWatch for post-mortem debugging.

### 6.3 Submission Models

Common ways to submit jobs:

- `StartJobRun` API/CLI: submits a job run to a virtual cluster, specifying execution role, release label, job driver, and configuration overrides.
- Spark Operator: declares Spark applications as Kubernetes custom resources; the operator manages Spark application lifecycles.
- `spark-submit` or Livy per supported submission models and releases.
- For Flink: Flink Kubernetes Operator or Flink Native Kubernetes per supported releases.

Pick one submission model and standardize logging, retries, tagging, ownership, and deployment. Never allow multiple controllers to manage the same application simultaneously.

### 6.4 EMR on EKS Support for Spark and Flink

EMR on EKS supports Spark job runs. For Flink, EMR releases 6.13.0+ support the Flink Kubernetes Operator per current guidance; Flink session mode is supported starting in release 6.15.0. The Flink Operator manages application lifecycles; HA requires properly configured metadata storage, checkpoints, and job manager behavior.

The release label determines runtime and framework versions. Never assume every EMR release ships identical Spark/Flink versions or features. Check the release compatibility matrix and supported releases for your submission model before deploying.

### 6.5 Job Execution Roles

A job execution role is the IAM role assumed by Spark/Flink pods to read/write data. This role is separate from the caller's permissions to invoke `StartJobRun` and permissions to administer the EKS cluster.

The role typically needs permissions to read scripts/JARs and data from S3, write outputs/logs/event logs, access Glue Data Catalog, read/write Kinesis/MSK/DynamoDB/databases as required, and use KMS keys if data is encrypted with customer managed keys.

With IRSA, a trust policy binds the IAM role to a Kubernetes service account via an OIDC provider. EMR on EKS also supports EKS Pod Identity in documented releases/submission models, starting with EMR 7.3.0 for `StartJobRun`. Check compatibility and configure role associations before selecting.

### 6.6 Job Concurrency Controls

Starting August 28, 2026, EMR on EKS provides job run admission controls for virtual clusters:

- `maxConcurrentJobRuns`: maximum job runs executing simultaneously.
- `maxInQueueJobRuns`: maximum job runs accepted into the pending queue.

When the queue is full, `StartJobRun` can return `ValidationException` so callers can apply backpressure or route to another cluster. Both limits are optional; by default, no limits are enforced. This feature helps multi-tenant shared EKS clusters prevent one workload from exhausting capacity.

### 6.7 Kubernetes Compute Capacity

EMR on EKS runs on EKS worker capacity. An EKS cluster can use EC2 node groups/managed node groups, Karpenter, or Fargate in supported workloads/configurations. With EC2, node and EBS costs accrue even when part of node capacity sits unused. With Fargate, billing is based on pod vCPU/memory duration and Fargate minimum rules.

Do not assume Fargate as the default for every EMR job. Check features, networking, storage, pod constraints, startup latency, and pricing for your specific submission model.

## 7. EMR Serverless: Applications and Workers

EMR Serverless lets you create framework-specific applications and submit jobs without provisioning or managing EC2/EKS clusters for job compute. The service provisions workers automatically, scales to demand, and releases workers once jobs finish.

### 7.1 Applications and Job Runs

| Component | Role |
|---|---|
| Application | Defines framework type, EMR release, architecture, capacity limits, networking, and runtime config |
| Job run | A single execution of a Spark/Hive or supported streaming workload |
| Driver | Coordinates the Spark job |
| Executor/worker | Executes distributed tasks |
| Runtime role | IAM role used by the job to read/write data |
| Maximum capacity | Upper bound on CPU, memory, and disk for the application |
| Pre-initialized capacity | Warm workers kept ready to reduce startup latency |

EMR Serverless application types currently support Spark or Hive. Spark jobs can run Java/Scala JARs or PySpark scripts. For streaming, EMR Serverless supports Spark Structured Streaming in a dedicated mode—not the Apache Flink runtime.

### 7.2 Worker Sizing

Workers offer vCPU, memory, and ephemeral disk configurations depending on the release. Current documentation lists workers from 1, 2, 4, 8, 16, up to 32 vCPUs with per-size memory ranges. Drivers and executors can use different sizes.

Size workers based on driver memory/cores, executor cores/memory, Spark memory overhead, shuffle/spill disk, concurrent executor counts, and data volume/parallelism. Too little worker memory leads to OOMs or heavy disk spill; overly large workers reduce fine-grained scaling and waste resources on small jobs.

### 7.3 Maximum Capacity

Maximum capacity caps total CPU, memory, and disk for an application. It serves as a guardrail against runaway jobs or burst submissions consuming excessive capacity. Size maximum capacity as expected worker count multiplied by worker specs, plus appropriate headroom.

For example, to cap at 40 workers with 2 vCPU, 16 GB memory, and 40 GB disk each:

    Maximum CPU    = 40 × 2  = 80 vCPU
    Maximum memory = 40 × 16 = 640 GB
    Maximum disk   = 40 × 40 = 1,600 GB

This is a sizing example. Account for drivers, executors, concurrency, and account quotas; jobs can fail if the application or account hits maximum capacity.

### 7.4 Auto-Start and Auto-Stop

By default, EMR Serverless can auto-start when a job is submitted and auto-stop after 15 minutes of idle time. When an application transitions to `STOPPED`, pre-initialized capacity is released. These behaviors can be customized or disabled.

Auto-stop cuts charges for idle pre-initialized capacity, though the next job incurs cold-start initialization time. For infrequent scheduled workloads, auto-stop usually makes sense; for interactive workloads requiring fast responses, consider keeping warm capacity.

### 7.5 Pre-Initialized Capacity

Pre-initialized capacity keeps drivers/workers warm so jobs start quickly. It acts as an application warm pool. Even when idle, pre-initialized capacity can incur charges while the application remains in the `STARTED` state.

Use pre-initialized capacity when jobs are submitted frequently, startup latency is a product requirement, interactive sessions need fast turnaround, or steady background load keeps workers utilized. Never leave large warm capacity running overnight if jobs only run for a few minutes a day. Set idle timeouts/auto-stop and size warm pools based on utilization.

### 7.6 Job Concurrency and Queueing

EMR Serverless supports configuring `maxConcurrentRuns` and `queueTimeoutMinutes` on applications in eligible releases. When the concurrency limit is reached, new jobs queue instead of immediately provisioning workers. Queueing smooths burst submissions and avoids breaching application capacity.

Per current documentation, job concurrency/queueing was introduced in EMR 7.0.0 and enabled by default from 7.3.0 onward per service behavior. Verify your release and configuration before relying on this behavior.

### 7.7 Flex Execution

Flex execution allows Spark batch jobs to use spare capacity at different pricing than Standard, at the cost of potentially waiting longer for executors. Flex is unsuitable for jobs needing fast startup, streaming jobs, or interactive sessions. If a Flex job fails, do not assume the service automatically falls back to Standard; orchestration must handle resubmission.

### 7.8 Streaming Jobs on EMR Serverless

EMR Serverless supports Spark Structured Streaming jobs starting with EMR release 7.1.0. Jobs run in `STREAMING` mode, typically stay running continuously, and use checkpoints to recover progress. Supported connectors include Kinesis Data Streams and Kafka/MSK per connector guidance.

Key characteristics:

- Uses the Spark engine with Structured Streaming only.
- Long-running execution; do not apply typical batch execution timeouts.
- Includes service-managed auto-retry and AZ resiliency mechanisms.
- Provides log rotation and log compaction for long-running jobs.
- Uses checkpoints to recover state and progress.
- Flex execution is not supported for streaming jobs.

If Apache Flink stateful streaming is required, evaluate EMR on EC2, EMR on EKS with Flink, or Managed Service for Apache Flink. Never choose EMR Serverless Spark Streaming expecting Flink semantics.

## 8. Choosing a Deployment Model by Workload

### 8.1 Daily Batch ETL

A nightly job reading 5 TB from S3, joining, and writing Parquet/Iceberg:

- EMR Serverless fits when load fluctuates, runtimes are moderate, and minimal cluster management is preferred.
- EMR on EC2 fits when jobs are large and steady, needing Spot/instance fleets or HDFS/local caching.
- EMR on EKS fits when the organization already has an EKS platform and wants standardized namespaces, scheduling, and IAM.

### 8.2 Interactive SQL/Analytics

For continuous interactive queries, startup latency and warm capacity matter:

- EMR on EC2 can maintain long-running clusters with Trino/Hive/Spark per configuration.
- EMR on EKS can run interactive endpoints sharing EKS capacity where supported.
- EMR Serverless can use pre-initialized capacity and interactive sessions via supported features.

### 8.3 Multi-Tenant Platforms

When multiple teams submit jobs:

- EMR on EKS provides namespaces, execution roles, Kubernetes quotas, and scheduler policies.
- EMR Serverless isolates applications, runtime roles, and maximum capacities.
- EMR on EC2 can isolate clusters/roles/security configurations per tenant, usually with higher operational overhead.

Never treat namespaces as the sole security boundary. Combine IAM, networking, secrets, S3 prefix/bucket policies, and catalog permissions.

### 8.4 Streaming

| Requirement | Model to Consider |
|---|---|
| Spark Structured Streaming with auto-provisioned workers | EMR Serverless (release 7.1.0+) |
| Apache Flink on Kubernetes | EMR on EKS with Flink Operator/compatible release |
| Apache Flink on EMR clusters | EMR on EC2 |
| Spark/Flink needing deep node/daemon control | EMR on EC2 or EKS depending on framework |

### 8.5 Custom AMIs, Bootstraps, and Native Dependencies

When installing custom drivers, native libraries, daemons, kernel tweaks, or custom OS packages, EMR on EC2 generally provides the highest control via custom AMIs and bootstrap actions. EMR on EKS supports custom container images/pod templates per runtime. EMR Serverless supports custom images within feature/runtime boundaries and compatibility rules.

### 8.6 Decision Matrix

| Question | If Answer Is "Yes" | Preferred Direction |
|---|---|---|
| Need deep control over instances/AMIs/bootstraps? | Yes | EMR on EC2 |
| Already running shared EKS with strong Kubernetes expertise? | Yes | EMR on EKS |
| Short, spiky jobs with zero desire to manage clusters? | Yes | EMR Serverless |
| Need HDFS or local cluster storage? | Yes | EMR on EC2 |
| Need Spark or Flink on Kubernetes? | Yes | EMR on EKS |
| Need serverless Spark Structured Streaming? | Yes | EMR Serverless |
| Need multiple frameworks on the same cluster? | Yes | EMR on EC2 |
| Want queue/capacity limits across many jobs? | Yes | EMR on EKS or Serverless depending on platform |

## 9. Data Lake Integration: S3, Glue, Lake Formation, and Table Formats

### 9.1 S3 Layout

A common layout:

    s3://company-lake/
      raw/
        source=orders/ingest_date=2026-11-20/
      staging/
        job=orders-normalize/run_id=...
      curated/
        domain=commerce/table=orders/
      analytics/
        product=finance/table=monthly_revenue/
      logs/
      checkpoints/
      artifacts/

The raw zone preserves source data in near-original form. Staging holds intermediate job/run outputs. Curated holds standardized schemas with validated quality. Analytics serves specific data products or consumers.

Separate buckets/prefixes by environment, owner, and data classification. Never let production jobs overwrite raw inputs; use run IDs, partitions, and atomic commit patterns suited to your table format.

### 9.2 AWS Glue Data Catalog

Glue Data Catalog stores databases, tables, schemas, partitions, and metadata for the data lake. Spark/Hive/Trino/Athena integrate with the catalog per engine/release support. Use the catalog so multiple compute engines agree on schemas and locations.

When a job writes a table:

1. Identify database/table and schema.
2. Select a format such as Parquet, Iceberg, Hudi, or Delta per engine support.
3. Write data files to S3.
4. Update metadata/catalog via the mechanism supported by the table format.
5. Verify snapshots/manifests/partitions and concurrent writer behavior.

### 9.3 Lake Formation

Lake Formation governs fine-grained permissions across database/table/column/row/cell levels in Glue Data Catalog via supported integrations. With EMR on EC2, runtime roles and credential vending ensure jobs read only authorized data. Integration requires matching runtime releases, Glue Catalog, and Lake Formation configuration.

Do not confuse IAM bucket permissions with Lake Formation permissions. A role holding `s3:GetObject` is not automatically authorized to read a Lake Formation-governed table; conversely, a catalog grant does not automatically supply all required KMS or network permissions.

### 9.4 Table Formats

| Format | Characteristics | Notes |
|---|---|---|
| Parquet | Columnar file format, strong compression, column pruning | Does not manage transactions or table metadata itself |
| Apache Iceberg | Snapshots, schema evolution, partition evolution, time travel | Verify catalog and engine compatibility |
| Apache Hudi | Upserts/incremental processing and table services | Requires compaction/clustering management |
| Delta Lake | Transaction log and ACID semantics | Verify Delta runtime/integration support |

Table formats affect write semantics, compaction, concurrent writers, and cross-engine queryability. Do not choose based solely on a single query benchmark; evaluate ingestion, updates, deletes, time travel, schema evolution, and maintenance.

### 9.5 Small Files and Compaction

Jobs with too many small tasks produce tiny output files, inflating metadata and query overhead. Solutions:

- Tune partition counts and shuffle partitions.
- Use `coalesce`/`repartition` carefully.
- Set target file sizes.
- Run compaction or rewrite data files.
- Avoid partitioning by very high-cardinality columns.
- Monitor file counts and average object sizes.

## 10. IAM and Security

### 10.1 EMR on EC2 Roles

EMR on EC2 uses multiple role layers:

- Service role: allows the EMR service to manage AWS resources.
- EC2 instance profile: permissions for software running on EC2 nodes.
- Runtime role: job/user-scoped data access permissions when runtime role authorization is enabled.
- Job submitter: permissions to create clusters, submit steps, view logs, and terminate per policy.

Separate infrastructure management permissions from data read permissions. If every job shares an overly broad instance profile, any job or user could access data beyond its business scope.

### 10.2 EMR on EKS Roles

Separate:

- Submitter/administrator IAM roles.
- Job execution role for driver/executor pods.
- EKS cluster/node roles.
- Kubernetes service accounts and RBAC.
- IRSA or EKS Pod Identity associations.

Job execution roles should grant access only to required S3 prefixes, Glue databases/tables, KMS keys, and log destinations. Submitters should hold `iam:PassRole` restricted to authorized roles so they cannot escalate privileges.

### 10.3 EMR Serverless Runtime Role

EMR Serverless uses an execution/runtime role per job. The role needs permissions to read inputs, write outputs, fetch scripts/JARs, access Glue/KMS, and emit logs as configured. Job permissions can be scoped further via execution IAM policies where supported by the submission API.

Never store long-lived access keys inside scripts, Spark configs, or environment variables. Use IAM roles and Secrets Manager.

### 10.4 Encryption

Encrypt:

- S3 objects with SSE-S3 or SSE-KMS per policy.
- EBS volumes and local data per EMR/EC2 configuration.
- Data in transit with TLS.
- Logs, checkpoints, snapshots, and artifacts.
- KMS key policies for EMR service roles, runtime roles, and data consumers.

With EMR on EC2, security configurations can enforce encryption at rest for EMRFS/S3 and local disks, plus encryption in transit. HDFS transparent encryption has separate settings. Verify engine, release, and connector behavior.

### 10.5 Networking

EMR on EC2 requires subnets, security groups, routes, NAT/VPC endpoints, and connectivity to S3, Glue, KMS, CloudWatch, and sources/sinks. For private clusters, prefer VPC endpoints for AWS services where appropriate.

EMR on EKS requires EKS cluster networking, pod IP capacity, security groups for pods if used, CNI, DNS, node placement, private endpoints, and egress rules. Namespaces do not isolate networks by themselves.

EMR Serverless can reach certain same-Region AWS service endpoints by default without VPC configuration; to reach private resources or external services, configure VPC/subnets/security groups per guidance. VPC mode can incur NAT, endpoint, and data transfer costs.

### 10.6 Data Access Governance

- Use bucket policies and prefix-level access controls.
- Use Lake Formation when fine-grained catalog/table access is needed.
- Use Apache Ranger on EMR when supported by the architecture/release and a Hadoop-ecosystem policy framework is needed.
- Protect logs and Spark UIs, as they can reveal queries, paths, or sensitive values.
- Separate dev/test/prod and accounts by data classification.
- Audit with CloudTrail and pipeline logs.

## 11. Deployment and Version Management

### 11.1 Choosing an EMR Release

The EMR release label dictates framework, library, Java, Python, and runtime optimization versions. Choose releases based on:

- Required Spark/Hadoop/Hive/Trino/Flink versions.
- Connector compatibility with sources and sinks.
- Java/Python dependencies.
- Security patches and support lifecycle.
- Needed features such as Lake Formation, EKS submission models, or Graviton.

Never track `latest` blindly in production. Pin release labels and test thoroughly before upgrading. When tracking recent security updates is required, use `latest` under policy with controlled change windows and regression tests.

### 11.2 EMR on EC2 Cluster Lifecycle

    Create cluster
        |
    Provision EC2 instances
        |
    Bootstrap actions
        |
    Install EMR applications
        |
    RUNNING
        |
    Submit steps / interactive work
        |
    WAITING or TERMINATING
        |
    TERMINATED

Clusters can run transiently—auto-terminating after the last step—or long-running. Long-running clusters continue accruing charges until terminated. Enable auto-termination policies for idle clusters and termination protection for critical clusters to prevent accidental shutdowns.

### 11.3 Bootstrap Actions and Custom AMIs

Bootstrap actions run on nodes during cluster provisioning to install packages, configure daemons, or prepare environments. Custom AMIs offer deeper control over OS and packages. Keep scripts idempotent, versioned, logged, and checking exit codes. Never pull unverified dependencies from the public Internet in production.

### 11.4 EMR on EKS Job Deployment

1. Create or select an EKS cluster and node capacity.
2. Create a Kubernetes namespace for the workload.
3. Register the namespace as an EMR virtual cluster.
4. Create the job execution role and IRSA/Pod Identity association.
5. Configure S3 log destinations, Glue/KMS access, and networking.
6. Choose an EMR release label.
7. Submit jobs via `StartJobRun`, Spark Operator, or Flink Operator.
8. Monitor job status, pods, Spark UI, and logs.
9. Clean up unused virtual clusters/namespaces per lifecycle policy.

### 11.5 EMR Serverless Application Deployment

1. Select application type (`Spark` or `Hive`).
2. Choose EMR release and architecture (`x86_64` or `arm64` if supported).
3. Configure maximum capacity.
4. Configure pre-initialized capacity if startup latency matters.
5. Configure auto-start/auto-stop and job concurrency.
6. Configure VPC connectivity if accessing private data.
7. Create the runtime role.
8. Submit jobs with S3 scripts/JARs, parameters, and monitoring settings.
9. Monitor job run states and `billedResourceUtilization`.
10. Delete unused applications and verify related logs/data resources.

## 12. Orchestration and Pipeline Design

EMR is typically one stage in a broader pipeline:

    Event / Schedule
          |
    Step Functions / MWAA
          |
    Validate input
          |
    Submit EMR job
          |
    Wait / poll job status
          |
    Validate output and quality
          |
    Update catalog / publish event
          |
    Notify downstream

### 12.1 Idempotency

Jobs may retry after errors or orchestrator timeouts. Design idempotent outputs:

- Assign each run a `run_id`.
- Write to a staging prefix before publishing.
- Validate record counts/schemas prior to committing.
- With Iceberg/Hudi/Delta, leverage the table format's transaction/commit semantics.
- Avoid overwriting partitions actively read by consumers without an atomic publish strategy.

### 12.2 Retries and Timeouts

Never retry configuration or permission errors indefinitely. Classify failures:

- Transient: capacity shortages, network glitches, throttling, temporary service issues.
- Data: corrupt records, schema mismatches, missing partitions.
- Code: bugs, OOMs, invalid SQL.
- Security: `AccessDenied`, KMS denials, missing Lake Formation grants.

Retry only recoverable errors. Use exponential backoff and cap attempts; route data errors to quarantine/DLQ or remediation.

### 12.3 Dependencies and Concurrency

If Job A writes a partition that Job B reads, orchestration must wait until commit and validation finish. For concurrent jobs, enforce concurrency controls across applications/virtual clusters, account quotas, Glue catalog mutations, and sink capacity.

## 13. Monitoring and Troubleshooting

### 13.1 EMR on EC2

Monitor:

- Cluster state and step states.
- YARN pending containers and allocated memory/vCores.
- Lost Spark executors, task retries, and shuffle spill.
- HDFS capacity, disk utilization, and DataNode health.
- EC2 CPU/network/EBS metrics.
- Spot interruptions and instance replacements.
- CloudWatch logs and application logs on S3.

### 13.2 EMR on EKS

Monitor:

- Job run states: `SUBMITTED`, `PENDING`, `RUNNING`, `FAILED`, `CANCELLED`.
- Pod states, pending reasons, `OOMKilled` events, and restart counts.
- Node CPU/memory/disk pressure.
- Kubernetes events, scheduler placement, and quotas.
- Driver/executor logs, Spark UI, and Flink dashboard.
- Job queue/concurrency limits and `StartJobRun` errors.

If pods stay `Pending`, check node capacity, taints/tolerations, affinity, resource requests, subnet IPs, and quotas. If pods are `OOMKilled`, inspect container memory requests/limits and Spark executor/driver overhead.

### 13.3 EMR Serverless

Monitor:

- Application states: `CREATING`, `CREATED`, `STARTING`, `STARTED`, `STOPPING`, `STOPPED`.
- Job states: `SUBMITTED`, `QUEUED`, `PENDING`, `SCHEDULED`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLING`, `CANCELLED`.
- Worker allocation, `billedResourceUtilization`, and application maximum capacity.
- Driver/executor logs, event logs, and Spark UI.
- Queue timeouts, concurrent runs, and account service quotas.
- Auto-start/auto-stop behavior and pre-initialized capacity utilization.

If jobs fail due to `maximumCapacity`, raise capacity carefully or reduce concurrency/worker size. If workers are not allocated, check account vCPU quotas, application caps, and worker configurations.

### 13.4 Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Cluster fails to launch | EC2 capacity, subnet IPs, service role, or quotas | Check events, instance fleets, and IAM |
| Job waiting on YARN | Insufficient vCores/memory or held containers | Inspect YARN UI, scale, or adjust requests |
| Spark OOM | Low executor/driver memory, skew, large `collect` | Mitigate skew, increase memory appropriately, avoid `collect` |
| HDFS full | Core nodes out of disk or uncleaned intermediate data | Add storage/scale core nodes, clean scratch properly |
| S3 `AccessDenied` | IAM/KMS/bucket policy/Lake Formation | Verify runtime role and key policies |
| EMR on EKS pod `Pending` | Node capacity, quotas, taints, subnet IPs | Check Kubernetes events and node groups |
| EKS job `AccessDenied` | Wrong job execution role or trust policy | Check IRSA/Pod Identity and `iam:PassRole` |
| Serverless job does not start | Application not `STARTED`, max capacity/quotas | Check state, queue, and account quotas |
| Serverless worker OOM | Insufficient worker memory/overhead | Adjust driver/executor sizes |
| Job creates many small files | Poor partition/shuffle settings | Apply `coalesce`/`repartition` and compaction |
| Job runs longer than expected | Data skew, shuffles, spill, growing input | Analyze Spark UI and stage metrics |
| High cost despite finished jobs | Idle clusters, warm capacity, or retained storage | Enable auto-terminate/auto-stop and audit resources |

## 14. Reliability, Availability, and Disaster Recovery

### 14.1 Decouple Storage and Compute

Persist durable data in S3, catalogs, and appropriate checkpoint locations. Clusters or pods can be replaced without losing raw/curated data. HDFS/local disks should hold only regenerable intermediate data.

### 14.2 Multi-AZ

EMR on EC2 clusters run within a single Availability Zone by cluster placement; to improve resilience, design job orchestration and durable storage so clusters can be recreated in another AZ. EMR on EKS runs on multi-AZ EKS clusters; configure pod placement and node groups with topology spread. EMR Serverless provides AZ resiliency for streaming jobs per service documentation; still design downstream durability and retries.

### 14.3 Checkpoints and Retries

Spark Structured Streaming uses checkpoint locations to store progress and state. Flink uses checkpoints/savepoints. Batch jobs need output commit and idempotency mechanisms. Never place checkpoints on local disk or HDFS if recovery across cluster replacements is required.

### 14.4 Recovery Objectives

Define:

- RPO: maximum acceptable data/progress loss or reprocessing window.
- RTO: maximum acceptable time to recover the pipeline.
- Replay window: source retention long enough to rerun.
- Recovery capacity: compute provisionable in another Region/AZ.
- Data consistency: whether downstream consumers tolerate duplicates/replays.

### 14.5 Cross-Region

For cross-Region DR:

- Replicate S3 data and required metadata/catalogs.
- Maintain artifacts, configs, secrets, and KMS keys in the target Region.
- Verify Glue Catalog/Lake Formation permissions.
- Confirm EMR release and EC2/EKS capacity availability.
- Account for replication, inter-Region transfer, and storage costs.
- Test recovery runbooks rather than relying solely on documentation.

## 15. Cost and Optimization

### 15.1 EMR on EC2

Total cost typically includes:

    EMR EC2 total
      = EMR service charge
      + EC2 On-Demand / Spot
      + EBS / instance storage
      + S3 / Glue / KMS / CloudWatch
      + NAT / VPC endpoints / data transfer

EC2 clusters continue accruing charges while `WAITING` until terminated. Use transient clusters, step-completion termination, or auto-termination policies to eliminate idle costs. Spot and managed scaling cut compute spend but require resilience.

### 15.2 EMR on EKS

Costs include:

- EMR uplift per vCPU-hour and GB-memory-hour requested by EMR pods, billed from EMR application image download start until pod termination, rounded per second.
- EKS cluster control plane charge.
- EC2 worker nodes or Fargate.
- EBS, networking, NAT, data transfer, and logging.
- S3/Glue/KMS and downstream services.

Virtual clusters carry no separate compute charge. Sharing an EKS cluster reduces cluster overhead, though idle node capacity still incurs cost. Allocate node costs by namespace/resource usage to avoid underestimating workload costs.

AWS announced a 30% reduction in EMR charges on EKS effective October 23, 2026 for both vCPU and memory uplifts; underlying EKS charges remain unchanged. Verify the current pricing page per Region as prices may vary.

### 15.3 EMR Serverless

EMR Serverless bills by aggregate vCPU, memory, and storage consumed by workers from ready-to-run until stopped, rounded per second with a one-minute minimum per worker. Billing details may include additional storage beyond 20 GB per worker; check worker configurations and regional pricing. Unused pre-initialized workers do not appear in a job's `billedResourceUtilization`, yet warm capacity can still incur charges while the application is `STARTED`.

Costs depend on worker vCPU/memory sizes and duration, driver/executor counts, ephemeral storage and shuffles, Standard vs. Flex execution, pre-initialized capacity and idle timeout, application/job concurrency, sources/sinks, S3, CloudWatch, VPC, and networking.

### 15.4 Cost Comparison by Utilization

| Scenario | Potentially Suitable Model |
|---|---|
| 24/7 cluster with high utilization | EMR EC2 or shared EKS capacity |
| Infrequent, short batch jobs | EMR Serverless |
| Large, steady batch jobs able to use Spot | EMR EC2 or EMR on EKS |
| Multiple teams already on EKS with well-shared compute pools | EMR on EKS |
| Continuous small jobs needing warm startup | Serverless with pre-initialized capacity, after factoring idle cost |
| Need HDFS/local caching and custom AMIs | EMR EC2 |

### 15.5 Practical Optimizations

- Benchmark instance families, Graviton, and worker sizes.
- Tune Spark executor cores/memory and dynamic allocation.
- Reduce shuffles, skew, and unnecessary repartitions.
- Use Parquet/columnar formats and appropriate partitioning.
- Compact small files.
- Use Spot for interruption-tolerant capacity.
- Enable managed scaling or auto-stop/auto-termination.
- Cap maximum capacity and concurrency.
- Trim pre-initialized capacity when utilization is low.
- Stop idle clusters/applications.
- Optimize log retention and metric cardinality.
- Track cost per TB processed or cost per successful job.

## 16. Design Example: Orders Data Pipeline

### 16.1 Requirements

A retail company receives order data from multiple systems. Each day brings 2 TB of raw data requiring schema standardization, invalid record filtering, joins with product and customer dimensions, and writing curated tables for BI and machine learning.

### 16.2 Data Flow

    Source systems
        |
    S3 raw zone
        |
    Glue Catalog / Lake Formation
        |
    EMR job (Spark)
        |
    Validate + normalize + join
        |
    S3 curated (Iceberg/Parquet)
        |
    Athena / Redshift / SageMaker / BI

### 16.3 Selecting the Model

Assuming the workload runs once daily, needs no HDFS, needs no interactive cluster, and has variable load:

- EMR Serverless is a suitable starting point to minimize cluster management.
- Configure maximum capacity to cap cost.
- Use Spark dynamic allocation and benchmarked worker sizing.
- Integrate S3/Glue Catalog and a runtime role.
- If jobs grow to multiple hours daily or utilization stabilizes, re-benchmark EMR on EC2/EMR on EKS.

If the organization already operates an EKS data platform wanting standardized scheduling/namespaces, the same job can run on EMR on EKS. If the job needs HDFS caching or custom AMIs, EMR on EC2 may fit better.

### 16.4 Quality Control and Commits

Jobs write to a staging prefix keyed by `run_id`. After validating schema, row counts, null ratios, and duplicate keys, the job commits to curated tables. If a job fails, retain staging per retention for debugging; never publish incomplete outputs.

### 16.5 Unit Economics

    Cost per TB processed = monthly EMR + related cost / TB input processed
    Cost per successful run = allocated pipeline cost / successful runs

Evaluate cost alongside duration, throughput, output quality, and freshness. A faster job generating many small files or requiring heavy compaction can raise overall TCO.

## 17. Lab A: Creating an EMR Cluster on EC2

### Goal

Create an EMR cluster running Spark, read data from S3, write output, and auto-terminate upon completion.

### Prerequisites

- Lab AWS account and Region.
- S3 bucket for input, output, and logs.
- Appropriate IAM service role and EC2 instance profile.
- VPC/subnet with routing to S3.
- AWS CLI v2 or EMR console.

### Step 1: Prepare Data

1. Create prefix `raw/orders/`.
2. Upload small CSV/JSON files.
3. Define schema and expected output.
4. Create prefix `curated/orders/`.

### Step 2: Create the Cluster

1. Open the Amazon EMR console.
2. Choose EMR on EC2.
3. Pick a release label containing Spark.
4. Select primary/core nodes and small lab-appropriate instance types.
5. Select subnet, security groups, and IAM roles.
6. Configure the S3 log URI.
7. Enable auto-termination or terminate after last step.
8. Create the cluster.

### Step 3: Submit a Spark Step

Use the SparkPi sample or a PySpark script that reads S3, transforms, and writes Parquet. Observe step state and YARN/Spark UI.

### Step 4: Verify Output

1. Inspect the S3 curated prefix.
2. Check schema and row counts.
3. Compare against input.
4. Confirm the cluster terminated.
5. Confirm logs remain in S3.

### Step 5: Clean Up Lab

Delete unnecessary S3 input/output/log objects, terminate the cluster if still active, and check for leftover EBS volumes, security groups, or created resources.

## 18. Lab B: Running a Spark Job on EMR on EKS

### Goal

Register a Kubernetes namespace as a virtual cluster, submit a Spark job, and inspect job pods/logs.

### Prerequisites

- EKS cluster with suitable node capacity.
- Dedicated lab namespace.
- IAM role for job execution.
- IRSA or EKS Pod Identity per supported release.
- S3 buckets/prefixes for input, output, and logs.
- Supported EMR release label.

### Step 1: Create a Virtual Cluster

1. Create a namespace, e.g., `emr-lab`.
2. Register the namespace with EMR using `create-virtual-cluster`.
3. Save the virtual cluster ID.
4. Verify the namespace mapping.

### Step 2: Configure Roles

1. Create the job execution role.
2. Grant required S3/Glue/KMS/CloudWatch permissions.
3. Configure trust policy for IRSA or Pod Identity.
4. Grant submitters permission to call `StartJobRun` and `iam:PassRole` on that specific role.

### Step 3: Submit the Job

Example command skeleton:

    aws emr-containers start-job-run \
      --virtual-cluster-id <VIRTUAL_CLUSTER_ID> \
      --name orders-etl-lab \
      --execution-role-arn <JOB_EXECUTION_ROLE_ARN> \
      --release-label <SUPPORTED_EMR_RELEASE> \
      --job-driver '<JOB_DRIVER_JSON>' \
      --region <AWS_REGION>

Replace placeholders with actual IDs/ARNs and a Spark job driver payload. Never embed credentials in commands or scripts.

### Step 4: Observe

1. Check job run status.
2. Use `kubectl` to inspect driver/executor pods.
3. Inspect Kubernetes events if pods stay `Pending`.
4. Open Spark UI/logs.
5. Verify S3 output.

### Step 5: Clean Up Lab

Cancel running jobs, delete unused virtual clusters, remove the namespace per process, revoke role associations, and clean up logs/data per retention.

## 19. Lab C: Running a Spark Job on EMR Serverless

### Goal

Create a Spark application, configure maximum capacity, submit a PySpark job, and inspect billed resource utilization.

### Step 1: Create the Application

1. Select type `SPARK`.
2. Select an appropriate EMR release.
3. Select `x86_64` or `arm64` if dependencies support it.
4. Configure maximum capacity.
5. Configure auto-start/auto-stop.
6. Enable pre-initialized capacity only if fast startup is needed.

### Step 2: Create the Runtime Role

The role needs permissions to read scripts/inputs, write outputs, access Glue/KMS, and write logs. Restrict S3 prefixes for the lab.

### Step 3: Submit the Job

    aws emr-serverless start-job-run \
      --application-id <APPLICATION_ID> \
      --execution-role-arn <JOB_RUNTIME_ROLE_ARN> \
      --job-driver '{
        "sparkSubmit": {
          "entryPoint": "s3://<BUCKET>/scripts/orders_etl.py",
          "entryPointArguments": [
            "s3://<BUCKET>/raw/orders/",
            "s3://<BUCKET>/curated/orders/"
          ],
          "sparkSubmitParameters": "--conf spark.executor.cores=2 --conf spark.executor.memory=4g --conf spark.driver.cores=1 --conf spark.driver.memory=2g"
        }
      }' \
      --region <AWS_REGION>

### Step 4: Inspect the Job

1. Track job state from `SUBMITTED` to `SUCCESS`/`FAILED`.
2. Open driver/executor logs.
3. Verify S3 output.
4. Call `GetJobRun` to inspect `billedResourceUtilization`.
5. Compare duration and worker sizing.

### Step 5: Clean Up Application

Wait for jobs to complete, delete unused applications, verify pre-initialized capacity is released, and delete logs/artifacts per policy.

## 20. Self-Check Questions

**Question 1.** What problem does Amazon EMR solve?

**Answer:** Provides managed runtimes and integrated infrastructure to run distributed data processing frameworks such as Spark, Hadoop, Hive, Trino, and other supported engines.

**Question 2.** What are the three main deployment models?

**Answer:** EMR on EC2, EMR on EKS, and EMR Serverless.

**Question 3.** What is the primary node's responsibility?

**Answer:** Cluster management and coordinating components such as YARN ResourceManager and HDFS NameNode per configuration.

**Question 4.** How do core nodes differ from task nodes?

**Answer:** Core nodes both run tasks and store HDFS data; task nodes provide compute only and do not store HDFS data.

**Question 5.** When should you use instance fleets?

**Answer:** When combining multiple EC2 instance types with flexible On-Demand/Spot targets to improve capacity fulfillment.

**Question 6.** Why are task nodes strong Spot candidates?

**Answer:** Task nodes hold no persistent HDFS data, so reclamation causes lower impact when jobs use retries and spare capacity.

**Question 7.** Is HDFS durable storage?

**Answer:** No. HDFS on EMR EC2 is bound to the cluster lifecycle and disappears upon termination; persistent data belongs in S3.

**Question 8.** Starting in which EMR release did S3A replace EMRFS as the default S3 connector?

**Answer:** EMR 7.10.0.

**Question 9.** What is an EMR on EKS virtual cluster?

**Answer:** A Kubernetes namespace registered with EMR; it does not provision separate compute resources on its own.

**Question 10.** What is the job execution role in EMR on EKS used for?

**Answer:** Grants AWS permissions to driver/executor pods when reading/writing data and calling AWS services.

**Question 11.** From which releases does EMR on EKS support Flink?

**Answer:** EMR 6.13.0+ supports the Flink Operator per documentation; session mode is supported from 6.15.0.

**Question 12.** What do job concurrency controls on EMR on EKS accomplish?

**Answer:** Cap simultaneous running jobs and queued jobs in a virtual cluster to protect shared EKS capacity.

**Question 13.** Which application types are commonly selected in EMR Serverless?

**Answer:** Spark or Hive.

**Question 14.** Does EMR Serverless support HDFS?

**Answer:** No. Worker disks provide temporary storage for shuffle/processing; durable data uses S3 or appropriate storage services.

**Question 15.** Can pre-initialized capacity incur costs when idle?

**Answer:** Yes. Warm workers still accrue charges while the application is `STARTED` even without active jobs.

**Question 16.** Which engine powers EMR Serverless streaming jobs?

**Answer:** Spark Structured Streaming starting from EMR release 7.1.0; not Flink.

**Question 17.** Which jobs fit Flex execution?

**Answer:** Spark batch jobs tolerant of startup delays that can run on spare capacity; not suited for streaming or interactive jobs.

**Question 18.** What makes up EMR on EKS costs?

**Answer:** EMR vCPU/memory uplift, EKS cluster charges, EC2/Fargate workers, EBS, networking, logs, and data services.

**Question 19.** Why configure maximum capacity on EMR Serverless?

**Answer:** Caps total CPU/memory/disk to control costs and prevent one application from exhausting account capacity.

**Question 20.** Why is idempotent output required in orchestration?

**Answer:** Jobs can retry or rerun; idempotent outputs prevent duplicates, bad overwrites, or publishing incomplete data.

## 21. Production Readiness Checklist

- [ ] Deployment model fits the workload and operational skills.
- [ ] EMR release/framework/connector compatibility verified.
- [ ] EC2 node types, instance groups/fleets, and Spot policies designed if using EC2.
- [ ] HDFS holds only regenerable intermediate data.
- [ ] S3 layout, lifecycle, partitioning, and file sizing standardized.
- [ ] EKS namespaces/virtual clusters, node capacity, and quotas defined if using EKS.
- [ ] Job execution roles follow least privilege with accurate trust policies.
- [ ] IRSA/Pod Identity verified for the release/submission model.
- [ ] EMR Serverless maximum capacity, worker sizing, and concurrency configured.
- [ ] Pre-initialized capacity enabled only when justified by latency and utilization.
- [ ] Streaming mode clearly distinguished between Spark Structured Streaming and Flink.
- [ ] Glue Catalog/Lake Formation permissions tested.
- [ ] S3/KMS/network encryption configured.
- [ ] Logs, metrics, Spark UI, and alerts assigned owners.
- [ ] Retries, timeouts, idempotency, and output commits designed.
- [ ] Checkpoints/replays/source retention satisfy RPO/RTO.
- [ ] Auto-termination/auto-stop and cleanup policies enabled appropriately.
- [ ] EMR, EC2/EKS, EBS, storage, network, and log costs estimated.
- [ ] Load tests, failure tests, and rollback plans in place.
- [ ] Savings/unit costs measured from post-deployment actual usage.

## 22. Official References

1. [Amazon EMR – Getting started](https://aws.amazon.com/emr/getting-started/) — overview of the three deployment models.
2. [Understanding EMR clusters and nodes](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-overview.html) — cluster lifecycle and node types.
3. [Primary, core, and task nodes](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-master-core-task-nodes.html) — role of each node type.
4. [Configure EMR cluster hardware and networking](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-plan-instances.html) — EC2 instances and networking.
5. [Instance fleets](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-instance-fleet.html) — target capacity and allocation strategies.
6. [Managed scaling](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-managed-scaling.html) — automatic cluster capacity scaling.
7. [Working with storage and file systems](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-plan-file-systems.html) — HDFS, S3A, and local storage.
8. [EMRFS](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-fs.html) — default S3 connector change in EMR 7.10.0.
9. [Auto-termination policy](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-auto-termination-policy.html) — cleaning up idle clusters.
10. [EMR on EKS concepts](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/emr-eks-concepts.html) — namespaces, virtual clusters, and job runs.
11. [Running Spark jobs on EMR on EKS](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/job-runs-main.html) — job submission and Spark Operator.
12. [Running Flink jobs on EMR on EKS](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/run-flink-jobs.html) — Flink Operator and native Kubernetes.
13. [Job execution roles on EMR on EKS](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/iam-execution-role.html) — IAM execution roles.
14. [EMR on EKS security best practices](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/security-best-practices.html) — least privilege and tenant isolation.
15. [EMR Serverless application behavior](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/app-behavior.html) — worker sizing, maximum capacity, and lifecycle.
16. [Pre-initialized capacity](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/pre-init-capacity.html) — warm workers and idle cost.
17. [EMR Serverless job concurrency and queuing](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/applications-concurrency-queuing.html) — throttling job submissions.
18. [EMR Serverless streaming jobs](https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/jobs-streaming.html) — Spark Structured Streaming and resiliency.
19. [EMR Serverless pricing](https://aws.amazon.com/emr/pricing/) — vCPU, memory, storage, and execution modes.
20. [EMR on EKS job concurrency controls – August 28, 2026](https://aws.amazon.com/about-aws/whats-new/2026/08/amazon-emr-eks/) — job run and queue limits.
21. [EMR on EKS 30% pricing reduction – October 23, 2026](https://aws.amazon.com/about-aws/whats-new/2026/10/emr-eks-reduces-emr-charge-30-percent/) — EMR uplift update.
22. [Integrate EMR with Lake Formation](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-lake-formation.html) — fine-grained data access.
23. [EMR security and encryption](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-security.html) — shared responsibility, IAM, and data protection.

---

**Conclusion:** EMR on EC2, EKS, and Serverless all support big data processing while optimizing for different operational models. EC2 provides cluster and storage control; EKS brings Spark/Flink onto shared Kubernetes platforms; Serverless removes cluster management for Spark/Hive and Spark Structured Streaming. Select based on workload, release compatibility, storage semantics, isolation, startup latency, utilization, and total cost, then validate with benchmarks and failure tests prior to production.
