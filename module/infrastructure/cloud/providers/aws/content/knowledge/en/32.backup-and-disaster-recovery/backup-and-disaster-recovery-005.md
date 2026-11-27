# Restore Testing and Data Integrity Verification

## Learning Objectives

A backup is only valuable when an organization can restore data at the right point in time, with the right scope, and within an acceptable duration. A successful backup job status indicates the service created a recovery point per its workflow; a completed restore job status indicates the resource was recreated. Neither signal proves the application can serve users or that restored data satisfies business rules.

This lesson places recovery testing into the operational AWS context: selecting recovery points, provisioning resources in a safe environment, measuring RTO/RPO, verifying data across multiple layers, testing the application, and retaining evidence. It applies to workloads using EC2, EBS, RDS, Aurora, DynamoDB, S3, EFS, FSx, Redshift, and other AWS Backup-integrated services.

After this lesson, you will be able to:

- Distinguish between backup success, restore success, data integrity, and application recovery.
- Build a testing strategy driven by RTO, RPO, criticality, and data type.
- Create an AWS Backup restore testing plan and selection, choosing either the latest or a random recovery point within an appropriate window.
- Prepare an isolated account, VPC, IAM, KMS, and dependencies for safe testing.
- Verify data via checksums, manifests, structural checks, queries, and business rules.
- Automate validation using EventBridge, Lambda, and the AWS Backup API.
- Measure recovery durations, investigate failures, and produce repeatable audit evidence.

## 1. Why Test Restores?

Backup is the process of creating and storing recovery points. Restore is the process of using a recovery point to recreate data or resources. Restore testing validates the ability to execute that second process under controlled conditions.

A backup job can succeed while recovery still fails because:

- The recovery point does not reside in a vault or account accessible to the recovery team.
- The KMS key was disabled, deleted, had its policy altered, or does not allow the restore role to decrypt.
- Restore metadata no longer matches current subnets, security groups, engine versions, instance classes, or configuration.
- The IAM role lacks permissions to create resources, attach volumes, write logs, or read secrets.
- Quotas, IP addresses, capacity, subnets, or concurrency limits are insufficient.
- Data restores cleanly, yet the database fails to start, the application cannot connect, or external dependencies are unavailable.
- Data is missing, on the wrong version, inconsistent across tables, or violates business rules.

Periodic testing exposes these issues before a real incident strikes. It also clarifies who executes the restore, which permissions are needed, how long it takes, what must be checked, and what evidence proves the system recovered.

## 2. Distinguishing Statuses and Concepts

| Concept | Meaning | What Cannot Yet Be Concluded |
|---|---|---|
| Backup job COMPLETED | Service completed the job creating a recovery point | Does not prove data is restorable |
| Recovery point available | A recovery point exists in the vault or source service | Does not prove access permissions and metadata remain valid |
| Restore job COMPLETED | Service finished creating restored resources or data | Does not prove logical data correctness or application functionality |
| Integrity validation successful | Defined integrity checks all passed | Does not prove every business edge case is valid |
| Application validation successful | Tested dependencies and application flows function | Does not replace load testing or comprehensive security testing |
| DR exercise passed | Recovery scenario met agreed criteria | Valid only within the tested scope, point in time, and assumptions |

A **recovery point** is a data point usable for recovery. For snapshots, it represents data state at snapshot time. For continuous backup or point-in-time recovery (PITR), you can choose a timestamp within the window supported by the service.

A **restore test** typically provisions temporary restored resources for verification. A **disaster recovery exercise** has a broader scope: it can span a standby account or Region, DNS, networking, IAM, secrets, startup ordering, traffic cutover, incident communications, and failback decisions.

## 3. RTO, RPO, and How to Measure Results

RTO (Recovery Time Objective) is the maximum outage duration an organization aims to tolerate. RPO (Recovery Point Objective) is the maximum acceptable data loss, typically expressed as time from incident occurrence to the recoverable data point.

For example, a service sets a 60-minute RTO and a 15-minute RPO:

- If an outage begins at 10:00, the service must be operational again before 11:00.
- The latest restored data must be no older than 09:45 per workload criteria.

These are design targets, not timing guarantees from AWS Backup. AWS provides no SLA for restore duration; actual times vary with system load, data volume, resource type, and service conditions.

### 3.1. Measuring the Right Timestamps

Do not measure only from clicking Restore until job completion. For a real service, record:

1. **T0 – Incident declared:** agreed starting timestamp for recovery timing.
2. **T1 – Restore initiated:** timestamp when the restore job is requested.
3. **T2 – Resource available:** newly created resource is up and reachable.
4. **T3 – Data validated:** structural and data checks pass.
5. **T4 – Application ready:** application and essential dependencies operate.
6. **T5 – Service accepted:** owner confirms readiness to cut over traffic or complete the drill.

AWS Backup restore duration generally reflects only the restore job duration. End-to-end RTO must account for all other required steps per organizational definition. Recording only T1 to T2 cannot substitute for RTO from T0 to T5.

### 3.2. Measuring RPO with Data, Not Just Backup Schedules

A 15-minute backup schedule alone does not prove a 15-minute RPO. A job may run late or fail; a recovery point might not yet be copied to a standby vault or Region. Record the actual data timestamp inside the recovery point and compare it against the simulated incident time.

For databases, use transaction markers or an audit table recording timestamps and sequence numbers. For files/objects, use manifests with creation timestamps and versions. For event systems, record event offsets or sequences. Inspecting how far restored data reaches reveals actual data loss.

## 4. Building a Testing Strategy

Not every workload needs a full restore every day. Testing frequency and depth should reflect criticality, data churn rate, compliance mandates, and cost.

| Testing Category | Scope | Suggested Design Frequency |
|---|---|---|
| Recovery point checks | Jobs, vaults, recovery point age, encryption, copies | Daily or matching backup schedule |
| Technical restore | Representative resource, verify restore job | Weekly or monthly |
| Data integrity checks | Checksums, record counts, constraints, manifests | On every restore test |
| Application testing | Health checks, DB connectivity, synthetic read/write flows | Monthly or after major changes |
| Region/account DR | Rebuild part or all of the system in standby environment | Based on criticality and compliance |
| Failover/failback drills | Traffic cutover, DNS, dependencies, and human procedures | Per approved DR plan |

These frequencies are illustrative. Choose schedules fitting retention, RTO/RPO, and environment capacity. A test restoring a single EC2 instance does not prove an entire multi-tier system can recover.

### 4.1. Tiering by Criticality

- **Tier 0 – Critical:** transactions, payments, identity, or internal control planes. Requires frequent testing of recovery points, restores, data, and applications; may require cross-account/Region drills.
- **Tier 1 – Important:** high-impact services with temporary manual/fallback options. Periodic restore tests and dependency checks.
- **Tier 2 – Standard:** tolerates longer recovery. Sample representative resources and test on a less frequent cadence.
- **Tier 3 – Archive:** primarily requires retrieval of archived records. Periodically verify accessibility, decryption, readability, and content integrity.

Do not apply a single schedule to all resources. Prioritize systems with tight RTO/RPO, rapid data churn, many dependencies, or complex recovery steps.

## 5. Multi-Layer Testing Model

A trustworthy test passes through multiple layers. Each layer answers a different question.

~~~mermaid
flowchart TD
    A[Selected recovery point] --> B[Restore job completed]
    B --> C[Resource and storage accessible]
    C --> D[Integrity: checksum / structure / data]
    D --> E[Application: dependencies / health / synthetic transactions]
    E --> F[Compare against RTO / RPO and criteria]
    F --> G[Evidence, conclusion, and action items]
~~~

1. **Availability:** the recovery point exists and the restore role can access it.
2. **Resource integrity:** the resource launches with required attributes; volumes or file systems mount cleanly.
3. **Storage integrity:** file or object contents are readable and checksums match.
4. **Logical integrity:** the database opens, indexes/constraints are valid, and critical data is present.
5. **Application integrity:** the application connects to the right dependencies, handles representative requests, and never writes mistakenly to production.
6. **Operational readiness:** monitoring, logging, secrets, IAM, DNS, runbooks, and owners are ready.

If a layer does not apply to a specific resource, explicitly document why rather than silently skipping it.

## 6. How AWS Backup Restore Testing Works

AWS Backup provides Restore testing to periodically evaluate recoverability and track restore job completion times. A restore testing plan consists of two parts:

- **Plan:** name, schedule, start time, start window, and recovery point selection rules.
- **Selection:** resource type, protected resource scope, IAM role, restore parameters, and how long temporary resources are kept for validation.

On schedule, AWS Backup selects matching resources and recovery points, then runs restore jobs following the same mechanics as on-demand restores. Results appear in the AWS Backup console and can be queried via API/CLI. Restore testing can integrate with AWS Backup Audit Manager to evaluate whether restore durations meet configured targets.

Restore testing is not an automated application logic test. To verify data and health checks, build a custom validation workflow or run separate verification steps.

### 6.1. Supported Resource Types

Per AWS Backup Restore testing documentation, supported resource types include:

- Amazon Aurora and Amazon RDS.
- Amazon DocumentDB and Amazon Neptune.
- Amazon DynamoDB.
- Amazon EBS and Amazon EC2.
- Amazon EFS.
- Amazon FSx for Lustre, ONTAP, OpenZFS, and Windows File Server.
- Amazon Redshift.
- Amazon S3.

Support scope can vary by Region, recovery point type, engine, and restore options. Check the AWS Backup feature availability matrix for each resource before finalizing schedules.

### 6.2. Restore Testing vs. On-Demand Restore

| Attribute | Restore Testing | On-Demand Restore |
|---|---|---|
| Execution | Scheduled by plan | Triggered by operator or automation |
| Recovery point | Chosen per plan rules | Selected by user |
| Results | Records validation status and test duration | Restored resources are generally retained |
| Cleanup | AWS Backup begins deleting test resources after the validation window | User manages resource lifecycle |
| Purpose | Periodic verification and audit evidence | Incident recovery or ad-hoc restoration |

Restore testing uses the same recovery point types and restore operations as on-demand restores. A thorough test should still mirror parameters and dependencies close to real recovery scenarios.

## 7. Designing Restore Testing Plans and Recovery Point Selection

When creating a plan, choose a schedule and start window fitting the restore scale. AWS Backup may randomize restore job start times within the start window to spread load. Start window is configured in hours; the current range is 1 to 168 hours.

Recovery point selection specifies:

- **IncludeVaults:** backup vaults eligible for recovery point selection; specific vaults or wildcards per API.
- **ExcludeVaults:** vaults to exclude if any.
- **Algorithm:** select the latest recovery point within the window or a random recovery point within the window.
- **RecoveryPointTypes:** snapshot, continuous/PITR, or both.
- **SelectionWindowDays:** maximum lookback window to search for recovery points, from 1 to 365 days.

Choose LATEST_WITHIN_WINDOW when testing the most recent recovery point. Choose RANDOM_WITHIN_WINDOW to sample older recovery points and uncover retention-related issues or long-term drift. Both modes answer different questions; create separate plans if you need both perspectives.

### 7.1. Calculating the Selection Window

The selection window is measured from when the restore job actually executes, not the scheduled start time. Because jobs can start anywhere within the start window, make the selection window wide enough that valid recovery points are not excluded by delayed execution.

Example:

- Backups run daily.
- The restore testing plan has a 6-hour start window.
- SelectionWindowDays is set to 1 day.

If the job actually begins after the latest recovery point has just aged past the 1-day window, the resource may have no eligible recovery points. Choose a selection window larger than the backup interval plus the start window buffer, and check retention so overly old points are not picked unintentionally.

### 7.2. Choosing PITR vs. Snapshot

Snapshots suit testing restores from scheduled backup points. Continuous backup/PITR suits restoring to a specific timestamp within the service-supported window.

PITR does not automatically guarantee every transaction up to the desired instant was persisted. For databases, verify transaction markers or timestamps after restoring. Check PITR feature availability and retention per resource type.

### 7.3. Protected Resource Selection vs. Recovery Point Selection

Resource selection identifies which protected resources belong to the plan. Recovery point selection determines which recovery points of those resources qualify for restoration.

Tag conditions on protected resources are evaluated against tags on the latest recovery point in the vault holding the resource. Tag conditions do not filter older recovery points individually. Therefore, do not assume an older restored recovery point necessarily carries the exact same tags as the latest recovery point.

On each plan run, AWS Backup restores at most one recovery point per selected protected resource. If you need to test multiple timestamps for the same resource, schedule multiple runs or run a separate on-demand scenario.

### 7.4. Quotas and Concurrency

Common restore testing plan quotas include 100 plans per account/Region, 30 selections per plan, up to 30 ARNs or conditions per selection, and a maximum selection window of 365 days. Concurrent restore job limits also vary by resource type. If concurrency quotas are saturated, jobs may fail to launch within the start window and be marked FAILED.

Review current quotas before scaling up plans. Stagger schedules, widen start windows reasonably, or request quota increases where supported. Avoid piling every large database, volume, and bucket onto the exact same timestamp if it strains account limits or dependencies.

## 8. Safe Recovery Environment

Best practice is designating a dedicated account for restore tests. The test environment must be isolated enough that restored resources cannot impact production.

### 8.1. Account and Network

- Use a dedicated account or OU for recovery exercises if governance allows.
- Provision VPCs, subnets, and security groups with restricted connectivity.
- Block routes to the production data plane unless the test requires access.
- Use separate DNS zones or test hostnames.
- Avoid overlapping resource names, endpoints, and IP addresses with production.
- Do not open broad inbound rules merely to make health checks convenient.

While some restore metadata is inferred from the recovery point, the target environment may still require specific subnets, security groups, or overrides. Review restore parameters before executing.

### 8.2. IAM Least Privilege

Restore testing uses the IAM role specified in the selection. When creating a plan, AWS Backup creates a service-linked role for the feature. The restore role requires permissions from AWSBackupServiceRolePolicyForRestores or appropriately scoped custom equivalents.

Beyond AWS Backup permissions, verify permissions to create target resources, attach volumes, apply tags, access KMS keys, write logs, and read secrets. With custom roles, missing a secondary permission like tagging resources can break restores or cleanup.

Never attach AdministratorAccess just to bypass restore errors. Use CloudTrail and job error messages to identify denied APIs and grant only the minimum required permissions.

### 8.3. KMS and Encryption

Restoring may require decrypting a recovery point and re-encrypting the target resource with a different KMS key. Check:

- The key is active and resides in the right Region.
- The key policy allows the restore principal or service to perform required actions.
- IAM policies and grants provide sufficient key access.
- Cross-account keys are shared following proper procedures.
- Permissions exist to create grants or use keys as required by the resource type.

Never assume permission to read a backup vault implies permission to decrypt data. When using customer managed keys, include KMS policies and key accessibility in periodic tests.

### 8.4. Secrets and Dependencies

An application might restore its database yet fail to boot due to missing secrets, certificates, parameters, or endpoints. Use dedicated test secrets and prevent connections to live production payment gateways, email providers, or webhooks.

Create stubs or sandboxes for external dependencies. When verifying connectivity to AWS services, use endpoints and roles inside the test account. Document any mocked dependencies so reports do not overstate recovery readiness.

## 9. Metadata and Differences During Restore

AWS Backup can infer part of the required metadata from the recovery point. For specific resource types, operators can override fields such as subnet, security group, instance class, database name, availability zone, or encryption key.

The GetRecoveryPointRestoreMetadata API retrieves metadata saved alongside a recovery point. When automating restores, avoid hard-coding every value from the legacy environment. Distinguish:

- **Metadata to preserve:** engine, data settings, or attributes needed to faithfully recreate the workload.
- **Metadata to override:** subnets, security groups, KMS keys, or resource names suited to the test account.
- **Sensitive metadata:** secrets, passwords, or identifiers pulled from a secrets manager.

Most AWS Backup restores create a new resource to avoid disturbing existing resources. However, destructive restore exceptions exist: Amazon Redshift Serverless namespace restores overwrite data in the target namespace; SAP HANA on EC2 restores overwrite the database at the specified target location. Check resource-specific documentation and target only isolated test resources for these cases.

### 9.1. Tags and Cleanup

For resource types supporting tag-on-restore, AWS Backup attaches the tag awsbackup-restore-test to track test resources and manage cleanup. If anyone deletes this tag before cleanup runs, AWS Backup may fail to delete the resource, requiring manual intervention.

Some resources such as DynamoDB and S3 do not support tag-on-restore in restore testing; cleanup relies on resource names. Deleting an S3 bucket may take several days as lifecycle rules remove objects asynchronously. Do not assume every resource disappears the instant validation ends.

Establish checks for orphaned test resources, monitor deletion statuses, and alert when cleanup fails. Include temporary storage, snapshots, and running compute in your restore testing budget.

## 10. Automating Validation with EventBridge and Lambda

AWS Backup emits Restore Job State Change events to EventBridge. When a restore testing job transitions to COMPLETED, a rule can invoke Lambda or another target to run data and application validation.

Sample flow:

~~~mermaid
flowchart TD
    A[AWS Backup restore test] --> B[Restore Job State Change]
    B --> C{status = COMPLETED?}
    C -->|No| D[Log state and handle job failure]
    C -->|Yes| E[EventBridge rule]
    E --> F[Lambda validation workflow]
    F --> G[Verify resource, data, application]
    G --> H[PutRestoreValidationResult]
    H --> I[AWS Backup console / API / audit evidence]
~~~

An event pattern can filter by resource type and restore testing plan ARN:

~~~json
{
  "source": ["aws.backup"],
  "detail-type": ["Restore Job State Change"],
  "detail": {
    "resourceType": ["RDS"],
    "restoreTestingPlanArn": ["arn:aws:backup:ap-southeast-1:111122223333:restore-testing-plan:weekly_critical"],
    "status": ["COMPLETED"]
  }
}
~~~

Never trigger validation before the job completes. If the restore job FAILED, log the restore failure separately; never report validation as successful just because Lambda executed.

### 10.1. Event Fields to Use

The restore job event can provide restoreJobId, resourceType, createdResourceArn, recovery point details, and restore testing plan ARN. Use the newly created resource ARN to locate the exact resource spun up by this test run. Do not guess resource names from the source resource if AWS Backup generated new names.

The validation workflow should:

1. Validate that the event originates from AWS Backup and an authorized plan.
2. Parse the created resource ARN and restore job ID.
3. Poll with bounded retries until the resource is ready.
4. Execute checks defined for that resource type.
5. Persist detailed results to logs or an evidence store.
6. Call PutRestoreValidationResult with status and message.

### 10.2. Recording Results

PutRestoreValidationResult submits an independent validation outcome. Valid statuses are SUCCESSFUL, FAILED, TIMED_OUT, and VALIDATING. The API requires RestoreJobId and ValidationStatus; ValidationStatusMessage is optional.

Illustrative AWS CLI example:

~~~bash
aws backup put-restore-validation-result --restore-job-id 12345678-1234-1234-1234-123456789012 --validation-status SUCCESSFUL --validation-status-message "RDS connectivity, schema and critical data checks passed"
~~~

Once a validation status is set, it cannot be changed. Treat the API call as a one-shot action and submit results only after the workflow reaches a final conclusion. Although the API lists VALIDATING as a valid value, do not use it as a transient state if the workflow still needs to post a final verdict later; track intermediate workflow state externally until completion.

According to AWS documentation, PutRestoreValidationResult is not included in the built-in AWS SDK for JavaScript inside Lambda runtimes; official examples recommend packaging a Lambda layer with the latest SDK. For other runtimes, verify SDK versions and API availability before deployment.

### 10.3. Idempotency and Retries

EventBridge and Lambda may deliver duplicate events. Validation must be idempotent:

- Use restoreJobId as the unique key for the test run.
- Avoid real business side effects during verification steps.
- Record individual check states to prevent uncontrolled re-execution.
- Retry transient failures with exponential backoff and hard timeouts.
- Never submit multiple final results for the same restore job.

If a workflow times out or cannot verify, submit TIMED_OUT or FAILED per policy. An unknown outcome must never be reported as successful.

## 11. Verifying Data Integrity

Integrity spans multiple layers. Matching checksums prove the compared bytes did not change under that algorithm; they do not prove records carry valid semantics, transactions committed cleanly, or business rules hold.

| Verification Layer | Examples | What It Proves |
|---|---|---|
| Byte-level | SHA-256 of files or objects | Byte contents match the manifest |
| Object-level | Object count, keys, versions, metadata | Expected objects and attributes exist |
| File-system | Mounts, permissions, owners, file counts, filesystem checks | File system is accessible with intact structure |
| Database structural | Engine startup, schemas, indexes, constraints | Database structure is readable |
| Database logical | Row counts, aggregates, foreign keys, transaction markers | Logical data satisfies defined invariants |
| Application | API health, login, synthetic read/write, business workflows | Application works against restored data |

### 11.1. Manifests and Checksums

Before backing up or when producing authoritative data, generate a manifest containing:

- File path or object key.
- Byte size.
- Checksum and algorithm.
- Version or timestamp.
- Data classification label and owner.

After restoring, recompute checksums on restored contents and compare against the manifest tied to that recovery point. Store manifests independently with versioning and restricted write access; if a manifest sits alongside corrupted or tampered data, it ceases to serve as independent proof.

SHA-256 suits detecting unintended byte changes. If your threat model includes attackers able to modify both data and manifests, sign manifests or store reference hashes in a separately hardened system.

### 11.2. Notes on Amazon S3 ETag

Never assume ETag is the object's MD5. With multipart uploads, encryption, or certain copy flows, ETag may not represent the MD5 checksum of the entire object. Use S3-supported checksums such as SHA-256 or CRC where supported by upload/download operations, and recompute checksums over actual downloaded contents when independent proof is required.

Example downloading a test object and computing SHA-256:

~~~bash
aws s3api get-object --bucket recovery-test-data --key manifests/orders-2026-11.csv restored-orders.csv
sha256sum restored-orders.csv
~~~

Compare results against an independently stored manifest. For large or multipart objects, verify checksum type and how S3 aggregates composite checksums so you compare matching data scopes.

### 11.3. Selecting Representative Test Data

Scanning petabytes of data on every test is unnecessary. Combine approaches:

- Validate full metadata and resource counts.
- Verify checksums for high-value datasets.
- Sample hierarchically by partition, date, tenant, or file type.
- Check newest, oldest, and boundary records.
- Verify transaction markers, financial totals, order counts, and relational integrity.

Document the sampling rate, selection method, timestamp, and limitations. If only 1% is sampled, never report the result as full-dataset verification.

## 12. Verifying EC2 and EBS

EC2/EBS restores require checking block devices, file systems, OS health, and applications:

1. Instance or volume launches in the intended subnet and AZ.
2. Instance reaches running state and passes system status checks.
3. Volume attaches to the proper device and shows available/in-use status.
4. File system mounts cleanly with proper permissions.
5. Critical files exist with expected sizes and checksums.
6. Services start, read configuration, and reach dependencies.
7. Application health checks return expected responses.

### 12.1. OS-Level Checks

On Linux, use lsblk, findmnt, df, and journalctl to verify volumes, mount points, and boot logs. Never run fsck on a file system mounted read-write. For offline checks, detach the volume and follow procedures suited to that file system type.

Example checking mount states:

~~~bash
lsblk -f
findmnt
df -h
systemctl --failed
~~~

On Windows, verify disks are online, drive letters, NTFS/ReFS health, and Windows Event Logs. Avoid altering disk signatures or drive mappings during read-only inspection.

Volumes created from EBS snapshots may need to initialize blocks from the snapshot before reaching full performance. During initialization, first reads of unloaded blocks can incur higher latency. If RTO requires serving production-level throughput, factor in initialization time or evaluate Fast Snapshot Restore or Provisioned Rate for Volume Initialization when appropriate.

### 12.2. File and Application Checks

Maintain a manifest of checksums for critical files such as versioned config files, artifacts, or exported transaction files. Post-restore, recompute checksums and verify owner/group permissions. A file with a valid checksum but wrong permissions can still break application startup.

For databases running on EC2, do more than check running processes. Run read queries, inspect schemas, and verify transaction markers following database engine procedures.

## 13. Verifying RDS, Aurora, and Relational Databases

For databases, restore job completion is just step one. Verify:

- Engine and version match application compatibility.
- Instance/cluster reaches available status.
- Endpoints and security groups permit test client connections.
- Required databases, schemas, tables, indexes, and constraints exist.
- Key record counts or aggregates align with baselines.
- Transaction markers reflect the target RPO.
- Critical business queries return accurate results.

### 13.1. Schema and Data Checks

PostgreSQL example:

~~~sql
SELECT current_database(), current_timestamp;
SELECT COUNT(*) FROM orders;
SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status;
SELECT MAX(updated_at) FROM orders;
~~~

MySQL example:

~~~sql
SELECT DATABASE(), NOW();
SELECT COUNT(*) FROM orders;
SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status;
SELECT MAX(updated_at) FROM orders;
~~~

These queries are illustrative. Choose actual tables and columns per your application's data contract. On large tables, COUNT(*) can be expensive; use snapshot baselines, partition aggregates, or optimized queries.

### 13.2. Constraint and Relationship Checks

For relational databases, verify primary keys, foreign keys, unique constraints, and not-null rules. Check for orphaned records using anti-joins or equivalent queries. Inspect critical indexes and query plans if performance is part of recovery acceptance criteria.

A database can start even when data is missing or tables are out of sync. Choose representative invariants—such as order counts by status, daily transaction totals, or order-item-customer referential consistency.

### 13.3. Consistency and Transactions

Storage-level snapshots may be crash-consistent or application-consistent depending on service, engine, and backup method. For databases, prefer engine-integrated backup mechanisms and verify committed transactions.

When data spans multiple databases or resources, restoring individual resources independently can produce an inconsistent state. Test using coordinated recovery point sets or procedures that re-establish cross-component consistency.

## 14. Verifying DynamoDB and Amazon S3

### 14.1. DynamoDB

For DynamoDB, verify:

- Table is created and in ACTIVE state.
- Partition keys, sort keys, indexes, and stream settings match design.
- TTL, encryption, point-in-time recovery, and autoscaling match expectations.
- Item counts or aggregates across key partitions.
- A representative sample of items has expected keys and attributes.
- Application can read key items using the test IAM role.

Never use a single Scan with Limit to infer total table item count. Scan paginates and only returns items from the current page. For full counts, handle pagination completely or rely on manifests/metrics captured for testing.

### 14.2. Amazon S3

For S3, verify:

- Target bucket is created in the right Region with proper encryption settings.
- Critical prefixes or object keys exist.
- Versioning and object metadata satisfy requirements.
- Objects are readable by the intended role.
- Checksums or manifests match baselines.
- Lifecycle rules, storage classes, retention, and access policies do not inadvertently purge or block recovered data.

If backups span multiple versions, inspect the exact version and timestamp required. Counting objects with ListObjectsV2 requires handling continuation tokens; the first page does not represent the entire bucket.

For very large buckets, build prefix-partitioned manifests and verify controlled samples. Document which objects were checked, which were skipped, and why.

## 15. Verifying EFS, FSx, and Redshift

### 15.1. EFS

After restoring EFS:

- Mount the file system from an EC2 instance or client inside an authorized subnet.
- Check mount targets, security groups, and DNS resolution.
- Verify directories, file counts, POSIX permissions, owner/group, and checksums.
- Test reading/writing a probe file inside a dedicated test directory.
- Confirm the application can access its expected paths.

If using access points, verify root directories and POSIX identities. Never let a test inadvertently write into a production file system.

### 15.2. FSx

For FSx for Windows, verify file system status, DNS, domain join, SMB shares, ACLs, and test user access. For FSx for ONTAP, OpenZFS, or Lustre, verify volumes, exports/shares, mounts, snapshots, and file metadata per protocol.

Do not stop at checking file system availability. A share can exist while users or service accounts lack read permissions.

### 15.3. Redshift

For Redshift, verify cluster or namespace availability, database connectivity, schema and table existence, and accuracy of key aggregate queries. For Redshift Serverless, note specifically that namespace restores can overwrite data in the target namespace. Use a dedicated test namespace and double-check the target before starting.

## 16. Application-Layer and Business-Workflow Verification

An application is considered recovered only when essential functions operate against restored data. Define a repeatable set of representative transactions that produce no live side effects.

Example for an e-commerce system:

1. Health endpoint returns ready.
2. Service reads test configuration and test secrets.
3. Checkout locates known catalog products.
4. Historical orders can be queried.
5. Order totals match baseline figures.
6. Inventory reads stock levels at a known point in time.
7. A synthetic transaction runs in a sandbox and is rolled back or purged.

For event-driven systems, verify event sources, queues, offsets, DLQs, and idempotent processing. Never replay live messages to production consumers during a restore test.

### 16.1. Health Checks Are Not Enough

An HTTP 200 on a health endpoint proves only part of readiness. Readiness checks should verify critical dependencies—databases, caches, object stores, and message brokers—without overloading them. Add representative business queries to validate underlying data.

### 16.2. Post-Restore Security and Access Checks

Restoring data with broader permissions than production is also a failure. Audit IAM roles, security groups, bucket policies, KMS keys, database grants, secret rotation, and logs. Ensure sensitive data is accessible only to the authorized test team.

## 17. End-to-End Test Scenario

A test scenario should clearly state its goal, scope, prerequisites, baseline data, execution steps, pass/fail criteria, and owner.

~~~text
Scenario: Restore orders and verify checkout
Scope: RDS/Aurora + EC2/ECS application
Recovery point: Selected snapshot or PITR within a 24-hour window
RTO target: 60 minutes from restore start to application-ready
RPO target: No transaction marker loss beyond 15 minutes

1. Create markers and record baseline before backup.
2. Select recovery point and start restore test.
3. Restore database into test subnet using test KMS key and test security group.
4. Wait for database available; record timestamp.
5. Verify schema, counts, aggregates, foreign keys, and markers.
6. Launch application in test environment.
7. Run health checks and read-only business queries.
8. Execute a sandbox transaction if approved.
9. Record timings, checksums, query results, and logs.
10. Submit validation result and verify cleanup.

Pass: all invariants pass, application is ready, and RTO/RPO meet targets.
Fail: any invariant fails, dependencies are unavailable, or timing exceeds thresholds.
~~~

The scenario must specify whether RTO starts at restore job launch or at incident declaration. Without consistent start markers, results across test runs cannot be compared.

## 18. Hands-On: Creating a Restore Testing Plan with the AWS CLI

The following example creates a weekly plan that randomly selects a snapshot or continuous recovery point from the past 14 days. This is an illustrative configuration; adjust vaults, resource types, roles, schedules, and windows for your environment.

Create restore-testing-plan.json:

~~~json
{
  "RestoreTestingPlan": {
    "RestoreTestingPlanName": "weekly_critical_restore",
    "ScheduleExpression": "cron(0 2 ? * SUN *)",
    "ScheduleExpressionTimezone": "Asia/Ho_Chi_Minh",
    "StartWindowHours": 6,
    "RecoveryPointSelection": {
      "Algorithm": "RANDOM_WITHIN_WINDOW",
      "RecoveryPointTypes": ["SNAPSHOT", "CONTINUOUS"],
      "IncludeVaults": ["*"],
      "SelectionWindowDays": 14
    }
  }
}
~~~

Create the plan:

~~~bash
aws backup create-restore-testing-plan --cli-input-json file://restore-testing-plan.json
~~~

Once the plan is created, create a separate selection for each resource type. Example selection using wildcard ARN combined with tag conditions to target production RDS resources:

~~~json
{
  "RestoreTestingPlanName": "weekly_critical_restore",
  "RestoreTestingSelection": {
    "RestoreTestingSelectionName": "rds_critical",
    "IamRoleArn": "arn:aws:iam::111122223333:role/AWSBackupRestoreTestingRole",
    "ProtectedResourceType": "RDS",
    "ProtectedResourceArns": ["*"],
    "ProtectedResourceConditions": {
      "StringEquals": [
        {
          "Key": "Environment",
          "Value": "production"
        }
      ]
    },
    "ValidationWindowHours": 12
  }
}
~~~

Create the selection:

~~~bash
aws backup create-restore-testing-selection --cli-input-json file://restore-testing-selection.json
~~~

In the API, a selection can use an explicit ARN list or a wildcard with conditions. Do not mix explicit ARNs with conditions in unsupported combinations. Verify the current schema before putting JSON into pipelines.

View plans and selections:

~~~bash
aws backup list-restore-testing-plans
aws backup list-restore-testing-selections --restore-testing-plan-name weekly_critical_restore
aws backup get-restore-testing-plan --restore-testing-plan-name weekly_critical_restore
~~~

View restore jobs:

~~~bash
aws backup list-restore-jobs --by-restore-testing-plan-arn arn:aws:backup:ap-southeast-1:111122223333:restore-testing-plan:weekly_critical_restore
aws backup describe-restore-job --restore-job-id 12345678-1234-1234-1234-123456789012
~~~

These commands illustrate syntax and workflow only. Verify options against your installed AWS CLI version and IAM permissions before running. Replace illustrative ARNs and account IDs with your test environment values.

## 19. Evidence and Auditing

A restore test outcome must be traceable and repeatable. Store evidence independently of test resources:

- Restore testing plan ARN, selection name, and execution timestamp.
- Recovery point ARN/ID, vault, recovery point type, and data timestamp.
- Restore job ID, status, resource type, and created resource ARN.
- Start/end timestamps for each stage.
- Checksum, query, file count, health check, and business invariant results.
- Version of validation scripts, container images, or Lambda functions executed.
- Approver, operator, conclusion, and follow-up action items.
- Cleanup status and any remaining resources post-test.

CloudTrail records API calls like StartRestoreJob when appropriate account logging is enabled. The AWS Backup console and API display restore jobs, statuses, and validation statuses. AWS Backup Audit Manager offers the Restore time for resources meet target control to evaluate whether restore jobs finish within configured target times.

This control evaluates resource restore duration using metrics reported by AWS Backup; it does not replace your organization's checksum or application validation. Compliance reports should clearly distinguish timing verification from data integrity verification.

### 19.1. Storing Tamper-Resistant Evidence

If evidence is required for audits or investigations, store outputs in a dedicated bucket with versioning and an appropriate retention policy. Consider S3 Object Lock when immutable archival is required. Restrict principals allowed to write, delete, or alter retention. Save checksums of reports and manifests, and consider signing results using an organization-approved mechanism.

Never record secrets, private keys, passwords, or raw personal data inside reports. Use ARNs, serial numbers, hashes, and the minimal metadata needed for traceability.

## 20. Common Failure Analysis

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| No eligible recovery points | Selection window too short, vault excluded, insufficient retention | Inspect IncludeVaults, ExcludeVaults, RecoveryPointTypes, and actual job start time |
| Restore job FAILED due to permissions | Role lacks resource or KMS permissions | Read status message, CloudTrail AccessDenied events, and key policies |
| Job fails to start within start window | Concurrent restore job quota or capacity constraint | Widen start window reasonably, reduce concurrency, or request quota increase |
| EC2 restored but SSH fails | Subnet, route, security group, key pair, or OS networking | Inspect instance status, ENIs, routes, and console/system logs |
| Volume attaches but fails to mount | Device mapping, filesystem error, or duplicate UUID | Check lsblk, dmesg, mount options, and filesystem state |
| RDS available but app cannot connect | Security group, subnet group, DNS, secret, or DB grants | Check endpoint, port, TLS, credentials, and database user grants |
| Database opens but data is missing | Stale recovery point, wrong PITR timestamp, or uncommitted transactions | Compare transaction markers, timestamps, and aggregates |
| Checksum mismatch | Stale manifest, wrong object version, or corrupted data | Verify recovery point, version ID, algorithm, and hash scope |
| Validation Lambda does not run | Wrong event pattern, missing target permission, or retries/DLQ | Inspect EventBridge metrics, rule matches, Lambda permissions, and DLQ |
| Validation reports SUCCESSFUL too early | Result sent before all checks finish | Use a state machine and submit final result only at the very end |
| Cleanup fails | Test tag deleted, name-based cleanup resource, or deletion still in progress | Check deletion status, tags, resource name, and job messages |
| Unexpected test cost spike | Large resources, long retention, slow S3 cleanup, or excessive frequency | Review usage, restore durations, retention, and test cadence |

### 20.1. Categorizing Failures

Classify failures into one of these categories:

- **Backup/recovery point:** no eligible point or point inaccessible.
- **Restore execution:** permissions, quotas, metadata, or target service caused job failure.
- **Integrity:** checksum, structural, or logical data checks failed.
- **Application:** dependencies, configuration, secrets, or health checks failed.
- **Security:** post-restore access permissions are improper.
- **Cleanup:** test resources were not deleted as planned.
- **Evidence:** missing logs, timestamps, or outputs to reach a conclusion.

Categorization routes action items to the right owners and avoids marking an entire test as a vague generic failure.

## 21. Optimizing Cost and Coverage

Restore tests incur direct costs, and restored resources incur compute, storage, I/O, network, snapshot, database, or supporting service charges. Keeping resources alive longer for validation also adds cost.

Cost controls:

1. Start with a small number of resources and resource types to measure actual spend.
2. Select recovery points based on risk; avoid testing every resource on every run.
3. Stagger schedules to avoid peak capacity bottlenecks and concurrent restore quotas.
4. Keep validation windows just long enough to complete checks.
5. Limit test data sizes where representative datasets can be isolated.
6. Monitor deletion statuses and clean up orphaned resources.
7. Use tags or naming conventions to distinguish test resources.
8. Track costs by plan, resource type, and account.

Never shrink the validation window so much that workflows cannot finish checking. The goal is solid evidence at controlled cost.

## 22. Self-Check Exercises

### Question 1

A backup job shows COMPLETED. Can you conclude the data recovers successfully?

**Answer:** No. COMPLETED only confirms the backup job finished. You need restore testing to verify the recovery point is usable and restored data/applications meet criteria.

### Question 2

A restore job COMPLETED, yet the API returns errors when querying the database. Did the test pass?

**Answer:** Not yet. The restore job only confirms the restore operation completed. Check networking, credentials, database schema, grants, and application queries.

### Question 3

RTO is 60 minutes. The restore job took 20 minutes and application validation took another 25 minutes. Can you report a 20-minute RTO?

**Answer:** No, if RTO is defined up to service-ready. Measure from the agreed start marker through completed validation/application readiness; this example has not even included earlier steps and already totals at least 45 minutes from restore initiation.

### Question 4

Is SelectionWindowDays measured from the scheduled cron time or from when the job actually runs?

**Answer:** From when the job actually runs. Account for StartWindowHours when choosing the selection window so recovery points are not excluded.

### Question 5

A DynamoDB Scan with Limit 100 returns 100 items. Can you conclude the table has only 100 items?

**Answer:** No. Scan paginates; handle LastEvaluatedKey or use an appropriate baseline/aggregate.

### Question 6

Is an S3 object's ETag always the MD5 of the entire object?

**Answer:** No. Multipart uploads and certain encryption/copy modes prevent ETag from representing the full-object MD5. Use supported checksums or hash downloaded contents.

### Question 7

Why is an independent checksum manifest needed?

**Answer:** If a manifest is corrupted or altered alongside the data, internal comparisons cannot be trusted. Store manifests where permissions and lifecycles are independent, optionally signed or immutable.

### Question 8

Does AWS Backup restore testing automatically verify application business logic?

**Answer:** No. You need a separate workflow such as EventBridge and Lambda to run health checks, queries, and business invariants and post validation results.

### Question 9

What happens if the awsbackup-restore-test tag is deleted before cleanup?

**Answer:** For resource types relying on tag-on-restore, AWS Backup may fail to identify the resource for automatic deletion, requiring investigation and manual cleanup. Certain resource types use name-based cleanup instead.

### Question 10

Does the AWS Backup Audit Manager control "Restore time for resources meet target" prove restored data checksums are valid?

**Answer:** No. That control evaluates restore duration against a target; checksums and logical data require separate validation.

## 23. Pre-Signoff Checklist for a Successful Restore Test

- [ ] RTO, RPO, and start/end timing markers are defined.
- [ ] Recovery point, vault, Region, and timestamp are recorded.
- [ ] Restore role holds least-privilege permissions and accesses KMS cleanly.
- [ ] Resources are restored into an isolated environment.
- [ ] Networking, subnets, security groups, and DNS test properly.
- [ ] Restored resources reach ready state and are accessible.
- [ ] File/object checksums or manifests match within defined scope.
- [ ] Database schemas, constraints, aggregates, and transaction markers pass.
- [ ] Application passes readiness and representative business flows.
- [ ] Post-restore IAM, KMS, secrets, and policies are verified.
- [ ] Validation status is submitted only after all checks conclude.
- [ ] Evidence captures restore job ID, recovery point, timestamps, script version, and results.
- [ ] Cleanup status is tracked and any remaining resources have an owner.
- [ ] Gaps in RTO/RPO, integrity, or application readiness have action items and deadlines.
- [ ] Scenarios are updated when architectures or dependencies change.

## 24. Official References

- [AWS Backup: Restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
- [AWS Backup: Restore testing validation](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing-validation.html)
- [AWS Backup: Restore a backup by resource type](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-a-backup.html)
- [AWS Backup API: CreateRestoreTestingPlan](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_CreateRestoreTestingPlan.html)
- [AWS Backup API: RestoreTestingRecoveryPointSelection](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_RestoreTestingRecoveryPointSelection.html)
- [AWS Backup API: PutRestoreValidationResult](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_PutRestoreValidationResult.html)
- [AWS Backup: Quotas](https://docs.aws.amazon.com/aws-backup/latest/devguide/aws-backup-limits.html)
- [AWS Backup Audit Manager: Controls and remediation](https://docs.aws.amazon.com/aws-backup/latest/devguide/controls-and-remediation.html)
- [AWS Backup: Feature availability by resource](https://docs.aws.amazon.com/aws-backup/latest/devguide/backup-feature-availability.html)
- [Amazon S3: Checking object integrity](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html)
- [AWS Backup: Restore an Amazon EBS volume](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-ebs.html)
- [Amazon RDS: Restoring a DB instance](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_RestoreFromSnapshot.html)

API names, quotas, and feature availability may change by service and Region. Before deploying, check current documentation for your exact resource type, Region, and AWS CLI/SDK versions.
