# Data Lake Architecture on S3

Enterprises often store data across many systems: transactional databases, SaaS applications, logs, partner files, IoT systems, and event streams. If each team creates its own copies and separate pipelines, data easily becomes fragmented, access control becomes difficult to manage, and maintenance effort increases. A data lake provides a centralized storage platform to ingest data in multiple formats, retain raw data, and build standardized data layers for analytics.

Amazon S3 is a popular storage foundation for data lakes on AWS thanks to its scalability, high data durability, multiple storage classes, and integration with processing and query services. However, an S3 bucket containing many files does not automatically become a data lake. An architecture that can operate reliably over the long term also requires data partitioning, appropriate file formats, a catalog, data-level access permissions, quality management, lineage, storage lifecycle policies, and clear ingest/transform processes.

In the CLOUD_PROVIDERS_AWS ecosystem, an S3-based data lake connects several service groups: AWS Glue for data integration and processing, AWS Lake Formation for data permission governance, Amazon Athena for querying directly on S3, Amazon Redshift for data warehouse analytics, Amazon EMR for distributed processing, and streaming services for continuous data ingestion. The design needs to balance scalability, security, reliability, performance, and cost.

## 1. Learning Objectives

After this lesson, you can:

- Explain the role of Amazon S3 in a data lake architecture.
- Distinguish between a data lake, a data warehouse, and a data lakehouse.
- Design raw, standardized, and curated data zones.
- Choose appropriate bucket structures, prefixes, partitions, and file formats.
- Describe batch, CDC, and streaming ingestion flows into S3.
- Use AWS Glue Data Catalog to manage metadata and schemas.
- Explain how AWS Lake Formation combines IAM and S3 policies to govern data permissions.
- Choose Athena, Redshift Spectrum, Glue, or EMR for analytics and processing tasks.
- Design encryption, data classification, quality, lineage, lifecycle, and disaster recovery.
- Estimate costs and establish data lake operations processes.

## 2. Data Lakes and the Role of Amazon S3

### 2.1. What Is a Data Lake?

A data lake is a centralized data storage and management architecture capable of ingesting structured, semi-structured, and unstructured data from multiple sources. Raw data is typically retained so that it can be reprocessed when business rules, schemas, or analytical requirements change.

A data lake typically has the following characteristics:

- Stores many types of data such as CSV, JSON, Parquet, Avro, images, videos, logs, and binary data.
- Ingests data from transactional systems, applications, devices, SaaS, and partners.
- Separates raw data from standardized data and analytics-ready data.
- Manages metadata, schemas, access permissions, quality, and data lineage.
- Allows multiple processing or query engines to read the same dataset according to granted permissions.
- Enforces retention, encryption, auditing, and recovery policies.

A data lake is not a dumping ground for arbitrary files without rules. Without owners, a catalog, classification, retention, and access control, a lake easily becomes a data swamp: data exists, but it is hard to find, hard to trust, and hard to use.

### 2.2. Data Lake, Data Warehouse, and Lakehouse

| Architecture | Focus | Common Data | Usage |
|---|---|---|---|
| Data lake | Flexible storage of raw and processed data | Structured, semi-structured, unstructured | Data engineering, exploration, ML, analytics |
| Data warehouse | Modeled data for controlled analytics | Structured, well-defined schema | BI, dashboards, SQL analytics |
| Data lakehouse | Combines open storage on object storage with table management and transactional capabilities | Tabular data, typically using a table format | Analytics, data science, and workloads requiring data updates |

The three models can coexist. An S3 data lake can feed data into Redshift or BI tools; a warehouse can hold data models optimized for queries; a table format such as Apache Iceberg adds metadata and table management mechanisms on S3 to support updates, deletes, schema evolution, and snapshots depending on engine capabilities.

### 2.3. Why Use Amazon S3?

Amazon S3 is well-suited as the data lake storage layer because:

- It scales capacity without requiring you to manage filesystems or storage servers.
- It decouples storage and compute; multiple engines can read the same data without needing an always-on cluster.
- It provides multiple storage classes to optimize for access frequency and retention periods.
- It supports versioning, lifecycle, replication, Object Lock, and data protection mechanisms.
- It integrates with Glue, Lake Formation, Athena, EMR, Redshift, Kinesis/Data Firehose, and many other services.
- It provides strong read-after-write consistency for supported object operations, allowing applications to observe changes immediately after a successful write.

S3 stores objects in buckets, where each object has a key and metadata. S3 is not a POSIX file system; operations like renaming or updating part of a file are typically implemented by creating new objects or copying/deleting. Therefore, a data lake must design file and table formats suited to object storage access patterns.

## 3. Overall Data Lake Architecture on S3

### 3.1. Core Layers

A reference architecture can be divided into the following layers:

1. **Data sources:** transactional databases, applications, files, SaaS, IoT devices, logs, and partner systems.
2. **Ingestion:** batch, change data capture (CDC), event, and streaming ingestion.
3. **Storage zones:** storing raw data, standardized data, and curated data.
4. **Catalog and governance:** managing databases, tables, schemas, owners, classification, and permissions.
5. **Processing:** cleansing, standardizing, joining, aggregating, deduplicating, and checking quality.
6. **Consumption:** SQL querying, BI, data science, ML, and data sharing.
7. **Operations:** orchestration, monitoring, auditing, cost management, retention, and recovery.

~~~mermaid
flowchart TB
    subgraph SRC["Data Sources"]
        A[Applications and databases]
        B[Files and partners]
        C[Streaming and IoT]
        D[SaaS and logs]
    end
    subgraph ING["Ingestion"]
        E[DMS / DataSync / Transfer Family]
        F[Kinesis / Data Firehose]
        G[Glue connectors / API]
    end
    subgraph LAKE["Amazon S3 data lake"]
        H[Raw zone]
        I[Standardized zone]
        J[Curated zone]
    end
    subgraph GOV["Catalog and governance"]
        K[Glue Data Catalog]
        L[Lake Formation]
    end
    subgraph PROC["Processing and consumption"]
        M[Glue ETL / EMR]
        N[Athena]
        O[Redshift Spectrum / Redshift]
        P[BI and ML]
    end
    A --> E
    B --> E
    C --> F
    D --> G
    E --> H
    F --> H
    G --> H
    H --> M
    M --> I
    I --> M
    M --> J
    H --> K
    I --> K
    J --> K
    K --> L
    L --> N
    L --> O
    J --> P
    N --> P
    O --> P
~~~

The diagram illustrates the logical components. A real-world deployment may use multiple accounts, buckets, Regions, and pipelines; not every source has to pass through the same ingestion service.

### 3.2. Organizing Data by Zone

A common organization pattern:

| Zone | Purpose | Recommended Rules |
|---|---|---|
| Raw / landing | Store data received from sources, preserving auditability and reprocessing capability | Restrict modifications, record source metadata and ingest timestamp |
| Standardized / cleansed | Standardize schema, data types, timezone, encoding, and quality | Enforce data contracts, filter out invalid records, and record check results |
| Curated / consumption | Data modeled for analytical consumption | Optimize partitions, file format, table format, and access permissions |
| Sandbox / transient | Experimentation or temporary data | Assign an owner, quota, and short lifecycle |

The names bronze, silver, and gold are also commonly used for raw, standardized, and curated respectively. These are architectural conventions, not mandatory AWS zone names.

The raw zone should keep the original data or a copy close to the source, with timestamp, source system, batch ID, and schema version. If data needs to be fixed, create a new processed version in the next zone rather than silently overwriting the raw data.

The standardized zone is where common technical rules are applied: normalizing encoding, timezone, column names, numeric types, date/time formats, units of measurement, and deduplicating records. The curated zone holds datasets with clear business meaning, such as daily revenue, order status, or user behavior.

### 3.3. Choosing Buckets or Prefixes?

You can use a single bucket for multiple zones with separate prefixes, or separate buckets split by zone, domain, account, or data classification level.

| Option | Advantages | When to Use |
|---|---|---|
| One bucket, multiple prefixes | Fewer resources to manage, easy to start | Small teams with shared security and lifecycle requirements |
| Separate buckets per zone | Clearer policies, lifecycles, logging, and access boundaries | Zones with different permissions or retention requirements |
| Separate buckets per domain/account | Strong separation of owners and blast radius | Organizations with multiple teams, multiple accounts, or sensitive data |

There is no single bucket structure that fits every organization. Choose boundaries based on access permissions, ownership, retention requirements, replication, and operations. Prefixes are not absolute security boundaries; you must use IAM policies, bucket policies, access points, and Lake Formation according to your designed model.

Example object key structure:

~~~text
s3://company-data-lake/
  raw/
    sales/
      source=erp/
        ingest_date=2026-11-20/
          batch_id=001/
  standardized/
    sales/
      orders/
        order_date=2026-11-20/
          region=ap-southeast-1/
  curated/
    commerce/
      daily_revenue/
        business_date=2026-11-20/
~~~

These prefix names are only examples. You must standardize naming conventions, allowed characters, partitioning, date/time formats, and ownership so that individual pipelines do not invent inconsistent structures.

## 4. Ingesting Data into S3

### 4.1. Batch Ingestion

Batch ingestion brings a dataset into the lake on a schedule or in batches. Sources may include CSV/JSON files from partners, database exports, daily logs, or objects from internal systems.

Common options:

- AWS DataSync to transfer files/objects between on-premises storage, NFS/SMB, and S3 in supported scenarios.
- AWS Transfer Family to receive files via supported SFTP, FTPS, or FTP protocols and store them in S3/EFS.
- AWS Glue connectors or jobs to read from databases, SaaS, and compatible data sources.
- Applications writing objects directly to S3 via SDK/API with an IAM role.
- AWS Storage Gateway in appropriate hybrid storage integration scenarios.

For batch workloads, define file arrival conventions, manifests, checksums, encoding, schema versions, completion windows, and missing-file detection. Never treat the mere appearance of a file in S3 as proof that the data was ingested completely.

### 4.2. Change Data Capture from Databases

CDC captures insert, update, and delete changes from a database and delivers them to the data lake or target system. AWS Database Migration Service (AWS DMS) can perform an initial full load combined with ongoing replication/CDC for supported sources and targets.

Typical flow:

1. DMS connects to the source database and reads the initial dataset.
2. The full load is written to S3 as configured.
3. DMS continues reading the source database's transaction log/change stream.
4. Changes are written as files/objects to S3 in batches according to the chosen output structure.
5. A Glue crawler, Glue job, or metadata pipeline updates the catalog and processes the data.

CDC must handle event ordering, primary keys, delete markers, schema changes, and checkpoints. When CDC files are split by time or partition, consumers must apply changes according to the source semantics. Never assume that simply concatenating all files produces the accurate current state.

### 4.3. Streaming Ingestion

For continuous event data, you can use:

- Amazon Kinesis Data Streams to ingest streams and allow multiple consumers to read under a shard/capacity model.
- Amazon Data Firehose to buffer and deliver data to S3 and other supported destinations.
- Amazon MSK or appropriate connectors when the system already uses Apache Kafka.
- AWS IoT Core for ingesting messages from IoT devices.
- Amazon EventBridge for routing events by rules; targets can be processing services or queues before storing in the lake.

Data Firehose can buffer by size or time before writing to S3. Buffers that are too small create many small files; buffers that are too large increase data latency. Choose settings based on freshness requirements and query efficiency.

### 4.4. Event Notifications and Post-Ingest Processing

S3 Event Notifications can send object creation/deletion events to SNS, SQS, or Lambda in supported configurations. Events can trigger downstream pipelines when files arrive, such as verifying manifests, validating schemas, or running Glue jobs.

Design consumers to be idempotent because notifications can be redelivered and event order does not always match application assumptions. When processing a batch consisting of multiple files, a manifest or completion marker is usually more reliable than triggering a pipeline for each individual object without coordination.

### 4.5. Choosing an Ingestion Service

| Need | Typically Suitable Option |
|---|---|
| Transfer files from NAS/on-premises to S3 | DataSync |
| Receive SFTP files from partners | Transfer Family |
| Full load and CDC from databases | AWS DMS |
| Event streams with custom consumers | Kinesis Data Streams |
| Buffer and deliver streams into S3 | Amazon Data Firehose |
| ETL from databases/SaaS/files | AWS Glue |
| Route events between services | EventBridge |
| Write objects from applications | S3 API/SDK with an IAM role |

Multiple options can be combined. For example, DMS writes CDC into the raw zone, Glue standardizes and compacts files, and Athena queries the curated zone.

## 5. File Formats, Compression, and Partitioning

### 5.1. Row-Based and Columnar Formats

CSV and JSON are easy to exchange, read directly, and debug, but are usually not optimal for large analytical queries. Parquet and ORC store data in columnar layout, supporting column pruning, compression, and predicate pushdown, making them well-suited for analytics.

| Format | Characteristics | Use Cases |
|---|---|---|
| CSV | Easy to exchange, simple, schema usually external to the file | Landing, small datasets, partner exchange |
| JSON | Flexible, suited for events and nested data | Raw events, logs, API payloads |
| Avro | Includes schema and supports record-based serialization | Event/data exchange, governed schema evolution |
| Parquet | Columnar, compresses well, widely used in analytics | Standardized and curated datasets |
| ORC | Columnar, optimized for certain engines and workloads | Analytics when well-supported by the engine |

A common strategy is to keep raw JSON/CSV/Avro in the raw zone and convert to Parquet in the standardized/curated zones. Not every source needs immediate conversion; keeping raw data enables reprocessing when transformation logic changes.

### 5.2. Compression

Compression reduces storage size and the volume of data read, at the cost of CPU during compression/decompression. For Parquet, common codecs include Snappy and Zstandard; the choice depends on the engine, speed, compression ratio, and compatibility.

Measure on real data:

- Compressed storage size.
- ETL runtime.
- Bytes scanned and query latency.
- Job CPU utilization.
- Read compatibility across Athena, Glue, EMR, and consumer engines.

### 5.3. Partitioning

Partitioning divides a dataset into logical paths by one or more attributes, commonly date, month, region, or data type. Queries with matching predicates can read only the required partitions, reducing bytes scanned and Athena costs.

Example:

~~~text
curated/orders/
  order_year=2026/
    order_month=11/
      order_day=20/
        region=ap-southeast-1/
          part-00001.parquet
~~~

Partitions should be based on common filter predicates and reasonable cardinality:

- Day or month is usually useful for time-series data.
- Region or business unit can be useful if queries frequently filter by that attribute.
- Avoid partitioning by user ID, request ID, or values with millions of distinct values without a clear reason.
- Too many partitions increase metadata and query planning overhead.
- Overly broad partitions can force queries to scan excessive data.

Not every dataset needs partitioning. Small datasets or datasets queried in full can use a simpler structure.

### 5.4. Small Files Problem

Too many small files increase object counts, metadata overhead, request counts, and query planning time. For example, a streaming pipeline writing tens of thousands of few-KB files per hour can cause Athena/Glue to spend more time listing and opening files than processing data.

Ways to mitigate:

- Increase buffer size/time in Data Firehose if latency allows.
- Use Glue or EMR to compact many small files into larger files.
- Choose a partition granularity suited to the data volume.
- Avoid writing one file per event.
- Monitor object counts and average file sizes.

For analytics on S3, file sizes in the hundreds of MB are often a reasonable starting point, though optimal size depends on the engine, concurrency, schema, and partitioning scheme. Benchmark instead of applying a rigid number to every dataset.

## 6. Catalog and Schema Management

### 6.1. AWS Glue Data Catalog

AWS Glue Data Catalog is a centralized metadata catalog storing information on databases, tables, locations, columns, data types, partitions, and related attributes. Services such as Athena, Glue, and Redshift Spectrum can use the catalog to discover and understand data on S3 through supported integrations.

Data Catalog stores metadata, not the data itself. Deleting table metadata does not necessarily delete objects in S3; conversely, deleting objects does not automatically ensure the catalog is updated accurately.

A catalog database structure can reflect zones or domains:

- raw_sales
- standardized_sales
- curated_commerce
- curated_finance

Database/table names need clear owners and conventions. Avoid letting crawlers create numerous near-duplicate tables caused by inconsistent file paths or schemas.

### 6.2. Glue Crawlers and Schema-on-Read

A Glue crawler can scan S3 or supported sources, infer schemas, and update the Data Catalog. Crawlers are useful when data is new or schemas can be discovered automatically, but automatic inference should not be treated as a data contract.

Risks:

- Data types inferred differently across batches.
- Missing or added columns causing unexpected schema changes.
- Crawlers creating redundant tables or partitions.
- Nested data or inconsistent files producing unusable schemas.

For critical datasets, manage schemas in a controlled way through pipelines or IaC, using crawlers for discovery or partition updates where appropriate. Schema evolution requires compatibility rules and a consumer notification process.

### 6.3. Schema Registry and Event Schemas

For streaming/events, AWS Glue Schema Registry can manage schemas for supported formats and enforce compatibility modes. Producers and consumers can validate schema versions, reducing the risk that a payload change breaks downstream pipelines.

A schema registry does not replace a data catalog for datasets stored on S3. A system can use the registry for event schemas and the Glue Data Catalog for stored data tables.

### 6.4. Partition Metadata

For Hive-style partitions, the Glue Data Catalog can store partition lists. Partition projection in Athena allows Athena to compute partition locations using rules instead of storing metadata for every partition in the catalog, provided the dataset fits the pattern.

Partition projection is useful when partition counts are large and follow a predictable pattern. However, misconfiguring projection can cause Athena to scan nonexistent locations or estimate overly broad ranges. Set ranges, formats, and projection values accurately.

## 7. Data Permission Governance with AWS Lake Formation

### 7.1. Why IAM and Bucket Policies Are Not Enough

IAM and S3 bucket policies control who can call APIs and access S3 resources. In a data lake, however, requirements are often finer-grained: analysts can read a table but must not see PII columns; the finance team can only access finance data; a consumer can only see rows matching a specific tenant.

AWS Lake Formation adds a data lake governance layer, managing permissions on catalog databases/tables, data locations, and row-, column-, or cell-level data filtering according to supported features.

Lake Formation does not eliminate IAM. Users or roles still need IAM permissions to call the required services, while Lake Formation evaluates data permissions under the integrated model. Misconfigured IAM, S3 policies, KMS key policies, or Lake Formation grants can cause access to fail or become broader than intended.

### 7.2. Governance Components

- **Data lake administrator:** manages Lake Formation configuration and high-level administrative permissions.
- **Data location:** S3 locations registered with Lake Formation to manage data access permissions under the supported model.
- **Databases and tables:** metadata in the Glue Data Catalog.
- **LF-tags:** classification labels used to grant permissions by attributes such as domain, classification, or environment.
- **Data permissions:** permissions to read, write, create tables, or manipulate metadata within a granted scope.
- **Resource links and cross-account sharing:** mechanisms to share databases/tables with other accounts via supported workflows.

Separate lake administration permissions from data usage permissions. Do not grant administrator permissions to every analyst just so they can run Athena queries.

### 7.3. Permission Granting Workflow

A basic workflow:

1. Register S3 data locations with Lake Formation if using the location-managed model.
2. Define databases/tables in the Glue Data Catalog.
3. Grant permissions to roles or principals by database/table or LF-tag.
4. Grant the necessary IAM permissions to call Athena/Glue and access required services.
5. Configure KMS permissions if objects are encrypted with SSE-KMS.
6. Test access using the consumer's actual role.
7. Verify both permitted access and access that must be denied.

When Lake Formation manages data permissions, understand hybrid access mode and IAM integration options. Some workloads may continue using IAM/S3 permissions while others use Lake Formation permissions. Do not mix both models without a clear permission matrix and testing.

### 7.4. Row-Level and Column-Level Security

Examples:

- Marketing analytics can read the customers table but cannot view email addresses and phone numbers.
- Regional teams in Singapore can only view rows matching their region.
- Finance can read revenue and cost columns, but cannot access personal identifiers.

Lake Formation data filters can enforce column and row filtering for integrated engines. Verify the specific engine, table type, and feature limitations. If an engine does not enforce filters as required, create reduced views or datasets and control the corresponding S3 locations.

### 7.5. Sharing Data Across AWS Accounts

In multi-account organizations, the data lake may reside in a central account while producers and consumers live in other accounts. Lake Formation supports sharing metadata and data permissions via cross-account mechanisms integrated with AWS RAM.

High-level flow:

1. The lake owner grants database/table permissions to the consumer account or designated principal.
2. The resource share is sent via AWS RAM according to service mechanisms.
3. The consumer accepts or receives the share based on Organizations/RAM configuration.
4. The consumer creates a resource link in their Glue Data Catalog.
5. Roles in the consumer account are granted appropriate permissions and query the data through supported engines.

Sharing metadata does not mean objects are copied to the consumer account. Data can remain in the lake owner's S3 bucket while access is controlled per configuration.

## 8. Processing Data with AWS Glue and Amazon EMR

### 8.1. AWS Glue ETL

AWS Glue provides serverless data integration services, including ETL jobs, crawlers, the Data Catalog, and pipeline management capabilities. Glue jobs can read from S3 or supported sources, transform schemas, cleanse data, join, aggregate, and write results to another zone.

Common tasks:

- Normalize timestamps to UTC.
- Cast data types and standardize column names.
- Clean nulls, invalid values, and encodings.
- Deduplicate records by key and timestamp.
- Mask or tokenize PII per policy.
- Convert JSON/CSV to Parquet.
- Create partitions and compact files.
- Compute aggregated datasets for dashboards.

Glue jobs can use Spark or other supported runtime options. Choose worker type, worker count, job bookmarks, retries, and timeouts based on the workload. Job bookmarks help track processed data for certain sources and configurations, but do not replace checkpoints and idempotency for every pipeline.

### 8.2. AWS Glue Data Quality

Glue Data Quality helps define and run data validation rules. For example:

- The `order_id` column must not be null.
- Total amount must be greater than or equal to 0.
- The `event_time` field must be parseable.
- Invalid `customer_id` rate must stay below a threshold.
- Record counts must not drop abnormally compared to a baseline.

Check results should be stored and linked to the batch/pipeline for traceability. For failed rules, decide upfront whether data will be quarantined, retried, alerted on, or conditionally accepted.

### 8.3. Amazon EMR

Amazon EMR is suited for large-scale distributed processing or workloads requiring frameworks such as Apache Spark, Hadoop, Hive, Trino, and supported components. EMR can run on EC2, EKS, or EMR Serverless depending on the service option chosen.

EMR is useful when:

- Deep runtime/library customization is required.
- Existing Spark/Hadoop workloads are already built.
- Large batch processing or specialized distributed algorithms are needed.
- You want fine-grained control over clusters/capacity and job execution.

EMR can increase costs if clusters remain running while underutilized. Using ephemeral clusters, managed scaling, or appropriate serverless options can reduce idle resources.

### 8.4. Choosing Glue or EMR?

| Criterion | AWS Glue | Amazon EMR |
|---|---|---|
| Model | Serverless data integration service | Big data processing platform with multiple deployment options |
| Infrastructure management | Minimal cluster management | Depends on EMR on EC2, EKS, or Serverless |
| Framework customization | Within runtimes and capabilities supported by Glue | More flexible across supported frameworks and configurations |
| Best suited for | ETL, catalog, crawlers, data quality | Spark/Hadoop/Trino workloads and specialized processing |
| Cost | Based on job resources/DPU and features used | Based on compute, storage, and respective management components |

Neither option is always cheaper. Benchmark with the same data, same SLA, and same output to compare total cost.

## 9. Querying and Consuming Data

### 9.1. Amazon Athena

Athena is a serverless SQL query service that can read data in S3 via the Data Catalog and supported connectors/formats. Users do not need to maintain database clusters for ad hoc queries.

Under pay-per-data-scanned pricing in common workgroups, ways to reduce cost include:

- Convert CSV/JSON to Parquet or ORC.
- Select only needed columns.
- Partition by commonly filtered predicates.
- Use predicates to restrict partitions.
- Avoid `SELECT *` on large datasets.
- Build smaller curated datasets for recurring dashboards.
- Use workgroups to enforce query limits and control output locations.

Athena also offers capacity/reservation options and different billing models depending on the engine/workgroup type. Check current pricing and your organization's actual model.

Example query on partitioned order data:

~~~sql
SELECT
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM curated_commerce.orders
WHERE order_date >= DATE '2026-11-01'
  AND order_date < DATE '2026-12-01'
GROUP BY region
ORDER BY revenue DESC;
~~~

The query assumes the table has `order_date`, `region`, and `total_amount` columns with appropriate data types. Partition pruning effectiveness depends on how partitions are declared and whether predicates match the partition keys.

### 9.2. Amazon Redshift Spectrum

Redshift Spectrum enables Redshift to query external data on S3 through external schemas and catalogs. It is useful when combining warehouse data with lake datasets without loading all data into Redshift.

Spectrum does not make every S3 query automatically as fast as internal tables. Performance depends on file format, partitioning, data scanned, predicates, concurrency, and query design. Frequently queried data or workloads requiring predictable latency may fit better when modeled and loaded into Redshift.

### 9.3. BI and Data Science

Curated data can be consumed by Amazon QuickSight, Redshift, notebooks, SageMaker, and other BI/ML tools based on integrations and access permissions. Publish datasets with owners, business descriptions, freshness, quality metrics, classification, and sample queries.

A good data product should answer:

- What does the data describe?
- What is the source and when was it updated?
- Who owns and supports it?
- What do the columns mean and what are their units?
- Does it contain PII or sensitive data?
- What are the freshness and quality SLAs?
- For what purposes are consumers allowed to use it?

## 10. Table Formats and the Data Lakehouse

### 10.1. Challenges of File-Based Tables

With plain Parquet, each file is an object and table metadata typically lives in the Glue Data Catalog. Appending files is straightforward, but updating/deleting many records, coordinating concurrent writers, schema evolution, and snapshot management require custom ETL logic.

When multiple pipelines write to the same dataset, manual file and metadata management easily leads to duplicates, partial writes, or queries reading inconsistent states.

### 10.2. Apache Iceberg

Apache Iceberg is an open table format for analytic datasets. Iceberg manages table metadata, manifests, and snapshots to support operations such as:

- Atomic commits per the table format mechanism.
- Schema evolution.
- Partition evolution.
- Snapshot isolation and time travel depending on engine support.
- Update/delete/merge depending on engine capabilities.
- Compaction and data file management.

On AWS, Glue Data Catalog can serve as the catalog for Iceberg tables; Athena, EMR, and other engines support Iceberg according to their respective versions and features. Check the compatibility matrix before choosing a specific engine or feature.

### 10.3. When to Use Iceberg?

Iceberg is useful when:

- Datasets require updates or deletes rather than append-only writes.
- Multiple consumers need to read consistent snapshots.
- Controlled schema evolution is required.
- You want to manage partitions without forcing consumers to depend on physical folder layouts.
- Time travel or snapshot rollback is needed per engine capabilities.

For simple append-only datasets, Parquet external tables may suffice with less overhead. Table formats introduce additional metadata and maintenance tasks such as compaction and snapshot expiration; operational processes must be in place.

### 10.4. Managing Maintenance

With Iceberg, monitor:

- Data file count and average file size.
- Manifest growth and metadata files.
- Snapshot retention.
- Orphan files.
- Compaction and rewriting data files.
- Concurrent writers and conflict handling.

Do not arbitrarily delete objects via lifecycle rules if those objects are still referenced by Iceberg metadata. Use maintenance operations appropriate for the engine/table format to avoid corrupting the table.

## 11. Securing the Data Lake

### 11.1. IAM and S3 Security Baseline

Apply baseline controls:

- Enable S3 Block Public Access at both account and bucket levels except for intentionally approved public cases.
- Use bucket policies to restrict principals, VPC endpoints, or enforce TLS conditions where appropriate.
- Enable Object Ownership with bucket owner enforced to simplify object ownership.
- Use temporary IAM roles for workloads and consumers.
- Enable versioning on buckets requiring object recovery.
- Restrict permissions on delete, lifecycle, replication, and bucket policy changes.
- Use S3 Access Points or VPC-restricted access points for complex sharing models when appropriate.

Prefixes do not inherently prevent users from accessing objects. Verify IAM policies, bucket policies, Lake Formation, KMS, and query service permissions.

### 11.2. Encryption

S3 supports server-side encryption such as SSE-S3 and SSE-KMS. For sensitive data or requirements for custom key management, customer managed KMS keys can provide key policy control, auditing, and rotation according to policy.

When using SSE-KMS:

- Principals reading objects need decrypt permissions via IAM and key policies.
- Producers need encrypt or generate data key permissions for write flows.
- Cross-account consumers need properly configured KMS permissions.
- The KMS key must be in the same Region as the bucket and operations.
- Monitor KMS requests and costs when handling high object/request volumes.

Enabling S3 Bucket Keys can reduce KMS request volume in certain SSE-KMS scenarios and lower KMS costs, though you should review conditions and impacts on auditing/permissions.

### 11.3. Sensitive Data Classification and Protection

A data lake may contain PII, financial data, health data, or confidential information. Before ingesting, define:

- Data owner and intended use.
- Classification and retention.
- Whether masking, tokenization, or additional encryption is needed.
- Who can read, write, share, or export the data.
- Whether data is permitted to move across Regions or accounts.
- How deletion or data-restriction requests will be handled.

Amazon Macie can help discover and classify certain sensitive data in S3. It is a supporting tool and does not replace data owners, classification workflows, and access controls.

### 11.4. Networking and Private Access

For workloads accessing S3 from a VPC, an S3 Gateway Endpoint can route traffic to S3 without traversing an Internet Gateway or NAT Gateway. Bucket policies can restrict access via VPC endpoints when the network architecture allows.

For Glue, Athena, and other managed services, verify how each service accesses S3 and which endpoints are required. Never assume all service-to-service traffic passes through endpoints inside your VPC.

### 11.5. Auditing

CloudTrail can log configured management and data API events. S3 data events can generate high log volumes and corresponding costs; select buckets/prefixes or event types to audit based on risk.

Combine CloudTrail, S3 server access logging, or CloudTrail Lake as needed to investigate who accessed or modified data. Protect logs in a separate account/bucket with restricted deletion permissions.

## 12. Quality, Lineage, and Data Contracts

### 12.1. Data Contracts

A data contract is an agreement between producers and consumers regarding schema, semantics, quality, freshness, and changes. A contract should specify:

- Dataset name and owner.
- Schema, data types, units of measurement, and timezone.
- Primary keys or identification rules.
- Rules for nulls, duplicates, and late-arriving data.
- Update frequency and freshness SLA.
- Schema compatibility and versioning.
- Classification, retention, and usage permissions.

When producers change a schema, assess downstream consumers before release. Adding nullable columns is usually more compatible than changing types or removing columns, but always test against actual engines and consumers.

### 12.2. Data Quality

A pipeline should validate:

- Completeness: sufficient records or required fields present.
- Validity: values fall within valid domains.
- Uniqueness: keys are not duplicated per rules.
- Consistency: relationships across columns and datasets do not conflict.
- Timeliness: data arrives within SLA.
- Accuracy: reconciliation against source or control figures.

For example, order counts in the curated zone can be compared against order counts from the transactional system over the same period. If discrepancies exceed thresholds, the pipeline should raise an alert and hold the batch for review.

### 12.3. Lineage and Metadata

Lineage tracks where data came from, which jobs processed it, how it was transformed, and which datasets depend on it. Lineage can be recorded using pipeline metadata, job runs, catalogs, logs, and governance tools used by the organization.

When failures occur, lineage helps determine:

- Which downstream datasets are affected.
- Which batches were produced by which pipeline version.
- Which source file or source table caused the issue.
- Which consumers need to be notified.
- Whether the pipeline can be re-run from the raw zone.

Do not record only the job name. Capture execution ID, input/output locations, schema version, code version, timestamps, quality status, and correlation ID.

## 13. Pipeline Orchestration and Operations

### 13.1. Job Orchestration

A data lake pipeline may include multiple steps:

1. Wait for files or CDC batch completion.
2. Validate manifests and checksums.
3. Update metadata or catalog.
4. Run Glue ETL.
5. Run data quality checks.
6. Write curated datasets.
7. Update partition/table metadata.
8. Publish completion notifications to consumers.

Orchestration can use EventBridge, AWS Step Functions, Glue Workflows, or Amazon Managed Workflows for Apache Airflow (MWAA) depending on complexity and organizational standards.

Step Functions fits workflows with state, retries, and branching. Glue Workflows integrate closely with Glue components. MWAA fits organizations already using Apache Airflow that require complex DAGs. Avoid overly heavy orchestration for simple pipelines with only a few steps.

### 13.2. Idempotency and Retries

Pipelines must be safe to rerun. If a Glue job fails after writing partial output, the next run must not produce duplicate data or leave consumers reading an incomplete state.

Approaches:

- Use batch IDs or execution IDs to identify runs.
- Write outputs to a temporary prefix and publish upon completion.
- Use atomic table commits with an appropriate table format.
- Write a manifest confirming the set of files belonging to a batch.
- Design upserts/deduplication based on keys and event timestamps.
- Limit retries and route failing batches to quarantine.

Retries only help with transient errors. Schema, permission, or invalid data errors must be classified and handled—not retried indefinitely.

### 13.3. Monitoring

Monitor at minimum:

- Ingestion latency and arriving file/record counts.
- Storage size and object count per zone.
- Glue job duration, failures, DPU/worker usage, and retries.
- DMS task latency, CDC backlog, and errors.
- Kinesis shard/stream metrics or Firehose delivery failures.
- Athena bytes scanned, query runtime, and failed queries.
- Data quality pass rates and quarantined batch counts.
- Lake Formation permission failures and permission changes.
- S3 storage classes, lifecycle, replication status, and requests.

Amazon CloudWatch provides metrics, logs, alarms, and dashboards across many services. Use EventBridge to trigger notifications or reactive workflows when jobs fail. Operational reports should surface dataset freshness and quality, not just infrastructure status.

### 13.4. Data Product Owners

Every critical dataset needs an owner responsible for definitions, quality, access permissions, and SLAs. The platform team can operate the infrastructure, but cannot independently verify the business meaning of every column.

The catalog should publish descriptions, owners, domains, classification, freshness, schemas, and usage guidelines. Datasets without an owner or active consumers should be reviewed for archiving or deletion per policy.

## 14. Lifecycle, Durability, and Disaster Recovery

### 14.1. S3 Lifecycle

S3 Lifecycle can transition objects to other storage classes or expire objects based on rules. Build lifecycle rules per zone:

- Raw data may need long retention for auditing and reprocessing.
- Standardized data can be retained according to business cycles and ability to regenerate from raw.
- Curated data generally needs retention aligned with reporting and consumer needs.
- Temporary outputs can have short lifecycles.

If a bucket has versioning enabled, lifecycle rules must address current versions, noncurrent versions, and delete markers. Deleting the current version does not mean older versions are completely removed.

### 14.2. Replication

S3 Replication can copy objects to another bucket in the same Region (SRR) or another Region (CRR) under supported configurations and conditions. Replication helps with DR, data locality, account isolation, or data sharing.

Considerations:

- Versioning enabled on both source and destination.
- IAM roles and bucket policies.
- KMS key policies if using SSE-KMS.
- Replication rules, prefix/tag filters, and delete marker behavior.
- Replication metrics, and Replication Time Control if an SLA is required.
- Storage, request, and data transfer costs.

Replication does not replace backups in all scenarios. If data is overwritten or deleted, replication behavior depends on configuration; combine versioning, Object Lock, or a backup strategy to protect against errors and malicious actions.

### 14.3. Versioning and Object Lock

S3 Versioning retains multiple versions of an object to support recovery from overwrites or deletions. Versioning can increase storage usage because older versions remain stored; apply lifecycle rules for noncurrent versions.

S3 Object Lock provides a WORM model for object versions, with Governance or Compliance modes and retention/legal holds per service terms. Use Object Lock when immutability or evidence retention is required. Test retention and bypass permissions before enabling it on critical data.

### 14.4. Recovery Testing

A data lake DR plan should test:

- Restoring deleted or overwritten objects/versions.
- Reading data from replica buckets or backup Regions.
- Restoring catalog metadata and governance permissions.
- Recreating pipelines and required credentials/roles.
- Querying datasets after recovery.
- Measuring recovery time and data freshness against RPO/RTO.

Successful object replication alone is not enough. If the Glue Data Catalog, Lake Formation permissions, or KMS keys cannot be recovered, consumers may still be unable to access data.

## 15. Data Lake Cost and Optimization

### 15.1. Primary Cost Drivers

| Component | Cost Factors |
|---|---|
| Amazon S3 | GB-month by storage class, requests, retrievals, replication, and data transfer |
| AWS Glue | Job runtime, workers/DPUs, crawlers, Data Catalog, and related features |
| Amazon Athena | Data scanned or chosen capacity model, queries, and related features |
| Amazon EMR | Compute nodes/serverless capacity, storage, cluster, and networking |
| AWS DMS | Replication instances/serverless capacity, storage, and data transfer |
| Kinesis/Data Firehose | Stream capacity, data ingestion/delivery, and destination processing |
| Lake Formation | Integrated governance; underlying services like S3, Glue, and query engines still incur costs |
| CloudWatch | Log ingestion/storage, metrics, alarms, and queries |
| KMS | API requests and keys per the service pricing model |

Data lake costs do not live solely in S3. A cheap bucket combined with pipelines continually reprocessing data, queries scanning entire datasets, and logs retained indefinitely can drive total costs high.

### 15.2. Optimizing S3

- Select storage classes based on access patterns.
- Use lifecycle rules for infrequently accessed or expired data.
- Clean up incomplete multipart uploads.
- Manage noncurrent versions and delete markers.
- Use compression and columnar formats.
- Compact small files.
- Avoid duplicate datasets without owners.
- Monitor via S3 Storage Lens and S3 Inventory.

### 15.3. Optimizing Queries

- Partition by commonly filtered predicates.
- Use Parquet/ORC and select only required columns.
- Use Athena workgroups to cap bytes scanned.
- Build aggregated/curated tables for repeated queries.
- Consider Redshift when stable, repetitive warehouse workloads are needed.
- Monitor query plans, bytes scanned, and concurrency.

### 15.4. Optimizing ETL

- Use incremental processing instead of rereading full datasets.
- Use bookmarks/checkpoints where appropriate.
- Choose worker types and counts based on benchmarks.
- Consolidate small pipelines where overhead can be reduced while preserving operational boundaries.
- Terminate EMR clusters when jobs finish.
- Configure reasonable retries and timeouts.
- Avoid running crawlers repeatedly on unchanged prefixes.

### 15.5. FinOps for Data Lakes

Apply tags or cost allocation metadata for domain, environment, owner, and application. Track costs by:

- Storage zone and bucket.
- Domain or data product.
- Pipeline/job.
- Query workgroup.
- Account and Region.
- Producer/consumer if chargeback/showback mechanisms exist.

Measure unit economics such as cost per TB ingested, per million events, per query, or per served data product. Balance cost against freshness, query latency, retention, and compliance requirements.

## 16. Design Example: E-Commerce Data Lake

### 16.1. Sources and Requirements

An e-commerce platform needs to analyze orders, payments, inventory, user behavior, and application logs. Data comes from:

- Aurora PostgreSQL storing orders and payments.
- Applications emitting behavioral events.
- Shipping partners sending delivery status files.
- S3 storing product images.
- Logging systems generating operational data.

Requirements:

- Retain raw data for reconciliation.
- Update order data in near real time.
- Build daily and regional revenue datasets.
- Restrict access to PII.
- Enable analysts to query using SQL.
- Support recovery and cost control.

### 16.2. Ingestion Design

1. DMS performs full load and CDC from Aurora into the raw zone.
2. Applications send behavioral events to Kinesis Data Streams; Data Firehose buffers and writes to S3 raw.
3. Partners upload files via Transfer Family into a landing prefix.
4. DataSync transfers file data from internal storage when needed.
5. S3 notifications or EventBridge trigger workflows once batches complete.

### 16.3. Standardization and Curation

Glue jobs read raw data:

- Normalize timestamps to UTC and preserve source timezone in metadata when needed.
- Standardize currencies and numeric types.
- Deduplicate events by event ID.
- Mask email/phone in analyst-facing datasets.
- Write Parquet partitioned by date and region.
- Run quality rules on keys, totals, and record counts.

The curated zone contains tables:

- `orders_current`: current order state processed from CDC.
- `payment_transactions`: payment transactions and reconciliation.
- `daily_revenue`: revenue by day, region, and channel.
- `customer_activity`: behavioral events with sensitive identifiers removed or masked.

If CDC upserts and table state updates are needed, the team can evaluate Iceberg tables with supported engines. For append-only datasets, Parquet external tables can be simpler.

### 16.4. Governance and Querying

- Glue Data Catalog stores schemas and partitions.
- Lake Formation grants permissions by domain and LF-tags.
- Analysts query curated tables via Athena workgroups.
- BI teams can use Redshift Spectrum or load frequently queried datasets into Redshift.
- PII is accessible only to approved roles; general analytics use masked versions.

### 16.5. Operations

- CloudWatch monitors DMS CDC latency, Glue jobs, Data Firehose delivery, and Athena queries.
- Step Functions orchestrates ingest, transform, quality checks, and publishing.
- CloudTrail logs selected governance and access activities.
- S3 Lifecycle transitions older raw data to appropriate storage classes per retention policy.
- Versioning/replication and metadata backups are tested periodically.
- Cost Explorer allocates costs by domain and environment.

## 17. Common Pitfalls

| Pitfall | Consequence | Mitigation |
|---|---|---|
| Treating an S3 bucket as a complete data lake | Missing catalog, owners, quality, or governance | Design zones, metadata, and governance processes |
| Writing all data into a single prefix | Difficult permissioning, retention, and querying | Separate zones/domains based on governance needs |
| Using CSV for all analytics | Higher storage and bytes scanned costs | Convert analytical datasets to Parquet/ORC where appropriate |
| Over-partitioning | Too many partitions and metadata overhead | Choose partitions based on query patterns and cardinality |
| Creating millions of small files | Slow queries and high request/metadata overhead | Buffer, compact, and adjust partition counts |
| Uncontrolled crawler schema inference | Schema drift and duplicate tables | Use data contracts and versioned schema management |
| Using IAM alone without data governance | Difficult table/column permission management | Combine with Lake Formation under a clear permission model |
| Consumers reading raw data directly | Definition mismatches, PII exposure, brittle source coupling | Publish curated data products |
| Non-idempotent pipeline retries | Duplicate data or partial outputs | Use batch IDs, manifests, outbox/checkpoints, and controlled publishing |
| Treating replication as a complete backup | Deletions/overwrites can propagate to replicas depending on config | Combine versioning, Object Lock, or backups and test restores |
| Lifecycle deleting Iceberg-referenced files | Table metadata points to missing objects | Use table format maintenance and appropriate retention |
| Monitoring only job status | Datasets may arrive late or fail quality checks | Track freshness, completeness, and quality |

## 18. S3 Data Lake Design Checklist

### Before Implementation

1. Identify domains, data owners, consumers, and use cases.
2. Inventory data sources, volume, formats, velocity, and sensitivity.
3. Define accounts, Regions, buckets, and zones.
4. Choose batch, CDC, or streaming ingestion.
5. Define data contracts, schemas, and partitions.
6. Choose Glue Data Catalog, Lake Formation, and IAM model.
7. Design encryption, networking, auditing, and retention.
8. Estimate S3, ETL, query, streaming, network, and monitoring costs.

### During Implementation

1. Create buckets/prefixes and enable Block Public Access.
2. Configure encryption, bucket policies, roles, and KMS.
3. Set up ingestion and raw landing.
4. Create catalog databases/tables and schema versions.
5. Build Glue/EMR transforms and data quality checks.
6. Grant Lake Formation permissions and verify actual access.
7. Configure Athena workgroups or consumption engines.
8. Set up orchestration, monitoring, and alerts.

### In Operations

1. Monitor freshness, completeness, quality, and lineage.
2. Review access permissions and sensitive data.
3. Compact files and optimize partitions.
4. Verify lifecycle, versioning, and replication.
5. Evaluate query scans, ETL runtimes, and storage growth.
6. Test object, catalog, and pipeline restores.
7. Periodically review owners, consumers, retention, and costs.

## 19. Conclusion

Amazon S3 provides a scalable storage layer for data lakes, but a valuable architecture requires many coordinated components: data zones, ingestion, file formats, partitioning, catalogs, governance, processing, querying, quality, security, and operations. AWS Glue supports cataloging and ETL; Lake Formation governs data permissions; Athena and Redshift Spectrum enable querying; EMR handles distributed processing; and DMS, DataSync, Transfer Family, Kinesis, and Data Firehose bring data into the lake across varied workloads.

A solid design preserves auditable raw data, produces owned standardized and curated datasets, and clearly publishes schemas, quality metrics, and usage permissions. Parquet, partitioning, and compaction keep queries efficient; Lake Formation, IAM, S3 policies, and KMS protect data; and lifecycle policies, versioning, replication, and restore testing support retention and recovery.

A data lake does not end once objects land in a bucket. It is a continuously operated data platform where producers, platform teams, and consumers share responsibility for quality, access control, freshness, and cost. When these responsibilities are designed in from the start, an S3 data lake can safely and reliably serve analytics, data science, and data integration at scale.
