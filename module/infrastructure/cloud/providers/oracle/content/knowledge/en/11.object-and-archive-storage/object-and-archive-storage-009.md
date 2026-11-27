# Object replication and cross-region data copying

In the **Object Storage and Archive Storage** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson covers maintaining object data across multiple OCI regions. It connects tenancy, compartment, and IAM concepts with Object Storage, monitoring, automation, cost, and strategies for maintaining operations when the primary region experiences an outage.

A bucket storing invoices in region A may serve normal traffic well, yet applications in region B still need to know which data has arrived, whether it is readable yet, and when writes are permitted. Therefore, cross-region deployments require both data-transfer mechanisms and operational procedures.

## 1. Objectives and scope

After this lesson, you will be able to:

- Choose between continuous replication and on-demand CopyObject.
- Prepare the source bucket, destination bucket, and two layers of IAM permissions.
- Create a replication policy and verify data in the standby region.
- Plan initial loading of pre-existing data, handle concurrent updates, and manage per-object errors.
- Design lag monitoring, failover, failback, and cost control.

The main examples use **two regions within the same tenancy**. Replicating across two tenancies requires separate cross-tenancy IAM design; do not apply the policies in this lesson verbatim for that case. Commands below are hands-on guidance; replace sample variables before running on OCI.

## 2. Three needs to distinguish

### Continuous replication

Object Storage replication establishes a relationship from a source bucket to a destination bucket. Data transfers asynchronously, meaning a successful write at the source does not prove the object is already available at the destination. You can use buckets in the same region or different regions within the tenancy; this lesson uses a different region for disaster recovery. [Source: Oracle Object Storage FAQ](https://www.oracle.com/cloud/storage/object-storage/faq/).

### On-demand copying with CopyObject

CopyObject performs a single copy of a specified object. Operators decide the destination name, region, timing, and how existing destination objects are handled. This fits exporting a finalized dataset or planned data migration. A single copy does not establish a continuous synchronization relationship.

Example: moving finalized monthly reports from an operations bucket to an analytics bucket. Today's job must have an explicit object list; reports arriving tomorrow require another request.

### Independent historical recovery copies

Suppose an application overwrites an invoice with bad content. A replica in another region can also receive that bad content. The system still needs history retention or immutable finalized copies to recover from business-logic errors.

| Need | Option to evaluate | Evidence to collect |
| --- | --- | --- |
| Continue serving when primary region is unreachable | Replication and region-switch runbook | Objects present and readable in standby region |
| Transfer a defined list of objects | Manifest-driven CopyObject | Outcome of each work request and content comparison |
| Recover data from before a business-logic error | Version history or appropriate independent copy | Recovery point, read permissions, and recovery test |
| Reduce read latency for users in another region | Evaluate read replicas closer to users | Measured app latency and endpoint selection policy |

The table above gives design suggestions. Every option must be validated against your application's write patterns and recovery requirements.

## 3. Data lifecycle when replication is enabled

In the example, the source bucket is **oci-objects-primary-lab** in **us-ashburn-1**; the destination is **oci-objects-dr-lab** in **us-phoenix-1**.

~~~mermaid
flowchart LR
    App["App in primary region"] -->|"Write object"| Source["Source bucket: read and write"]
    Source -->|"Asynchronous replication"| Target["Destination bucket: read-only to apps"]
    Target -->|"Read replicated data"| DR["Standby app"]
    Operator["Operator"] -->|"IAM and replication policy"| Source
~~~

Key replication semantics:

- Only objects uploaded **after the policy is created** enter the automatic replication stream; pre-existing objects are not automatically copied to the destination.
- Deleting an object at the source can delete the corresponding object at the destination.
- The destination bucket becomes read-only for normal writes; replication updates data there.
- Each source has at most one policy and one destination; each destination has one source. A destination cannot simultaneously act as a source for chained replication.
- Replication of objects encrypted directly with customer-provided keys under SSE-C is not supported. [Source: Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm).

Do not interpret a successful write at the source as an atomic transaction completed across both regions. For example, if an application updates a database to reference a newly written object, the standby region may see the database record before the object becomes readable. Establish conventions for objects that have not arrived yet, such as deferring the request, bounded retries, or returning a processing status.

### Timeline boundary example

| Example timestamp | Action | What to verify |
| --- | --- | --- |
| 09:00 | Upload old-report.csv before policy creation | Pre-existing data needs a separate backfill plan |
| 09:10 | Create source-to-destination policy | Exact buckets and exact regions |
| 09:12 | Upload new-report.csv | Timestamp when object appears at destination |
| 09:15 | Overwrite new-report.csv | Which content the standby app actually reads |
| 09:20 | Delete test object at source | Behavior at destination once processed |

Timestamps only illustrate ordering, not an OCI processing SLA.

## 4. Preparing buckets, compartments, and IAM

### Prerequisites before creating a policy

Prepare two buckets in the right regions, confirm the tenancy is subscribed to the destination region, and ensure the configurator has access on both sides. Creating a replication policy does not replace bucket preparation. In the Console, the policy is created on the source bucket with destination region and destination bucket details. [Source: Creating an Object Storage Replication Policy](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_create_a_replication_policy.htm).

For the hands-on lab:

- Use two dedicated compartments: **StoragePrimaryLab** and **StorageDRLab**.
- Choose Standard so read checks do not depend on Archive restore times.
- Keep buckets private and use sample data only.
- Destination must not have versioning enabled or retention rules; those conditions can cause policy creation to fail. [Source: Troubleshooting Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Troubleshooting/usingreplication_topic-Troubleshooting_Replication.htm).

Never use a destination bucket already containing unrelated critical data. Clear bucket names and purposes help prevent mistakes during drills or cleanup.

### Operator permissions and service permissions

Two identities must be granted permissions:

1. The user or operations group creating buckets, configuring policies, and checking objects.
2. The Object Storage service in the source region transferring data on the user's behalf.

The CLI caller's permissions do not automatically transfer to the service. Also never work around a service-permission error by making a bucket public.

Example policy for a group in the default identity domain in a lab environment:

~~~text
Allow group Default/StorageReplicationOperators to manage buckets in compartment StoragePrimaryLab
Allow group Default/StorageReplicationOperators to manage objects in compartment StoragePrimaryLab
Allow group Default/StorageReplicationOperators to manage buckets in compartment StorageDRLab
Allow group Default/StorageReplicationOperators to manage objects in compartment StorageDRLab

Allow service objectstorage-us-ashburn-1 to manage object-family in compartment StoragePrimaryLab
Allow service objectstorage-us-ashburn-1 to manage object-family in compartment StorageDRLab
~~~

Replace **Default**, group name, and compartment names with actual values. Place the policy at a scope covering both compartments, such as a policy at the root tenancy targeting both child compartments.

This is a broad lab-compartment permission example, not a least-privilege production policy. Narrow it with specific permissions and bucket/region conditions following OCI's IAM model. If the source is in another region, substitute the matching service principal; when reversing direction, evaluate service permissions for the new source region. [Source: IAM for replication](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm), [bucket and region limits](https://www.oracle.com/cloud/storage/object-storage/faq/).

For environments using Vault or custom encryption mechanisms, include keys, key usage permissions, and key reachability in the DR test plan. Never treat an object appearing at the destination as proof that the standby app has full permission to read it.

## 5. Hands-on: setting up cross-region replication

Snippets use **PowerShell and the OCI CLI** with authentication configured. You can inspect local syntax using **--help**. This lesson does not require creating Compute instances or VCNs just to practice object transfers.

### Declare parameters

~~~powershell
$SourceRegion = 'us-ashburn-1'
$DestinationRegion = 'us-phoenix-1'
$Namespace = 'REPLACE_WITH_TENANCY_NAMESPACE'
$SourceCompartmentId = 'REPLACE_WITH_SOURCE_COMPARTMENT_OCID'
$DestinationCompartmentId = 'REPLACE_WITH_DESTINATION_COMPARTMENT_OCID'
$SourceBucket = 'oci-objects-primary-lab'
$DestinationBucket = 'oci-objects-dr-lab'
$PolicyName = 'primary-to-dr-lab'
~~~

Namespace is the Object Storage namespace, not the tenancy display name. Choose available bucket names in their respective regions.

### Create both buckets

~~~powershell
$SourceBucketArgs = @(
    'os', 'bucket', 'create',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--compartment-id', $SourceCompartmentId,
    '--name', $SourceBucket,
    '--storage-tier', 'Standard',
    '--public-access-type', 'NoPublicAccess',
    '--versioning', 'Disabled'
)
oci @SourceBucketArgs
if ($LASTEXITCODE -ne 0) { throw 'Failed to create source bucket' }

$DestinationBucketArgs = @(
    'os', 'bucket', 'create',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--compartment-id', $DestinationCompartmentId,
    '--name', $DestinationBucket,
    '--storage-tier', 'Standard',
    '--public-access-type', 'NoPublicAccess',
    '--versioning', 'Disabled'
)
oci @DestinationBucketArgs
if ($LASTEXITCODE -ne 0) { throw 'Failed to create destination bucket' }
~~~

If reusing existing lab buckets, check their configuration and skip creation rather than running it blindly. Access type, storage tier, and versioning flags are documented in [OCI CLI: bucket create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/create.html).

Before the next step, you can upload a sample file **before-policy.txt** to the source via the Console to observe how pre-existing data behaves.

### Create the policy on the source

~~~powershell
$ReplicationArgs = @(
    'os', 'replication', 'create-replication-policy',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $SourceBucket,
    '--destination-region', $DestinationRegion,
    '--destination-bucket', $DestinationBucket,
    '--name', $PolicyName
)
$PolicyJson = oci @ReplicationArgs
if ($LASTEXITCODE -ne 0) { throw 'Failed to create replication policy' }

$Policy = ($PolicyJson -join [Environment]::NewLine) | ConvertFrom-Json
$ReplicationId = $Policy.data.id
if ([string]::IsNullOrWhiteSpace($ReplicationId)) {
    throw 'Did not receive replication ID'
}
$Policy.data
~~~

Save the replication ID in your operations log to inspect the right policy later. **--region** specifies the source side receiving the command; **--destination-region** specifies where data is replicated. Do not swap these two parameters. [Reference: creating a policy](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_create_a_replication_policy.htm).

### Read back the replication relationship

~~~powershell
$GetPolicyArgs = @(
    'os', 'replication', 'get-replication-policy',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $SourceBucket,
    '--replication-id', $ReplicationId
)
oci @GetPolicyArgs

$ListSourcesArgs = @(
    'os', 'replication', 'list-replication-sources',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $DestinationBucket
)
oci @ListSourcesArgs
~~~

Verify source name, destination name, regions, and policy status. Use **get-replication-policy** to inspect status, messages, and returned sync timestamp fields; use **list-replication-sources** in the destination region to confirm the receiving side. [Reference: get policy](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/replication/get-replication-policy.html), [reference: listing sources](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_list_replication_policies.htm).

A policy showing ACTIVE only confirms configuration is active at the policy level. Verify actual data before concluding the application can serve from the destination.

### Verify with a test object

After creating the policy, use the Console to upload **after-policy.txt** with known content into the source bucket. Then check the destination:

~~~powershell
$HeadArgs = @(
    'os', 'object', 'head',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $DestinationBucket,
    '--name', 'after-policy.txt'
)
oci @HeadArgs
~~~

HeadObject returns fields such as ETag and metadata without downloading the entire content. [Reference: OCI CLI: object head](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/head.html).

Poll with a bounded timeout; record when the source upload succeeded and when the destination became readable. If the object does not appear yet, check policy status and permissions before assuming data loss. For small test files, download the destination copy via the Console and open its content for extra confirmation.

You can test overwrites and deletes using a dedicated lab object. Never use production files to rehearse delete operations.

## 6. Copying a single object on demand

Use a separate destination bucket **oci-objects-copy-lab**, pre-created in the destination region, to avoid conflicting with the bucket acting as a replication destination.

### Submit a CopyObject request

~~~powershell
$CopyBucket = 'oci-objects-copy-lab'
$CopyArgs = @(
    'os', 'object', 'copy',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $SourceBucket,
    '--source-object-name', 'before-policy.txt',
    '--destination-region', $DestinationRegion,
    '--destination-namespace', $Namespace,
    '--destination-bucket', $CopyBucket,
    '--destination-object-name', 'initial-load/before-policy.txt',
    '--destination-object-if-none-match-e-tag', '*'
)
$CopyJson = oci @CopyArgs
if ($LASTEXITCODE -ne 0) { throw 'Failed to submit copy request' }

$CopyResponse = ($CopyJson -join [Environment]::NewLine) | ConvertFrom-Json
$WorkRequestId = $CopyResponse.'opc-work-request-id'
$CopyResponse
~~~

The **--destination-object-if-none-match-e-tag '*'** condition instructs the operation to fail if the destination name already exists. You can add **--source-object-if-match-e-tag** with the ETag read from the source to ensure the object did not change since planning. [Source: OCI CLI CopyObject](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/copy.html).

Include a batch ID in destination names when you want to keep transfer runs independent. If business rules allow overwrites, specify clearly which objects may be replaced and under what condition; avoid unconditional overwrites as a default error-handling shortcut.

### Track the CopyObject work request

~~~powershell
if ([string]::IsNullOrWhiteSpace($WorkRequestId)) {
    throw 'Need opc-work-request-id from copy response'
}

$WorkRequestArgs = @(
    'os', 'work-request', 'get',
    '--region', $SourceRegion,
    '--work-request-id', $WorkRequestId
)
oci @WorkRequestArgs
~~~

Query in the region where the copy request was submitted. Save the work request ID alongside source object, destination name, and submission timestamp for troubleshooting. The query API returns the processing status of the asynchronous request. [Source: OCI CLI work-request get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/work-request/get.html).

You can pass **--wait-for-state COMPLETED --wait-for-state FAILED** directly to the copy command to wait for one of the terminal states, then inspect the returned status. A client-side CLI timeout does not prove the server-side operation failed; query the work request again before submitting another request. [Reference: CopyObject wait options](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/copy.html).

### Data differences and Archive considerations

A successful copy creates a destination object with a new ETag, so do not require matching ETags on both sides to conclude content matches. An object in Archive must be restored before being used as a copy source. Copying into an Archive bucket stores the destination object in Archive; this affects readiness time when reads are needed. Each copy request specifies one object. [Source: Copying an Object](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/copyingobjects.htm).

For critical datasets, standardize an application-level checksum and store it in the manifest. Comparing contents or checksums of stable data detects wrong objects, wrong names, and wrong dataset selection; seeing the same object count alone does not prove the data is right.

## 7. Backfilling pre-existing data and controlling concurrent updates

A system running for months usually holds data created before replication was enabled. Treat initial data loading as a separate job with explicit inputs and verification results.

### Simple approach: when a write pause is possible

Suggested workflow for small systems:

1. Stop write and delete jobs that could alter the dataset being backfilled.
2. Build a manifest listing name, size, ETag, and application checksum if available.
3. While the destination bucket is still writable, copy each pre-existing object to it.
4. Wait for all work requests to complete and reconcile against the manifest.
5. Create the replication policy between the two buckets.
6. Verify the policy, then reopen the source write stream.
7. Test a new object to confirm subsequent writes flow properly.

The pause window must cover locking the manifest, backfilling, and creating the policy. Reopening writes mid-way without tracking changes can introduce data gaps.

### When writes cannot be paused for long

Design a migration workflow with cutoffs and delta capture, such as:

- Use immutable object names tied to business IDs or version IDs.
- Record ongoing operations in a separate replayable log.
- Backfill baseline data to a staging destination, then reconcile deltas.
- Schedule a brief cutover window to drain remaining changes and verify the dataset.

These architectural approaches require dedicated implementation and testing. Never assume listing objects while an application keeps writing produces an application-consistent snapshot.

If the policy is already active and you discover missing older data, do not arbitrarily write into a read-only destination. Prepare a fresh destination and repeat the process, or use a separate ingestion store with a controlled cutover plan.

### Designing a multi-object copy job

Running CopyObject per object requires an orchestrator for large datasets. A manifest can include:

| Field | Purpose |
| --- | --- |
| batch_id | Distinguish backfill batches |
| source_region, source_bucket, object_name | Identify source |
| source_etag or source_version_id | Pin the source state to read |
| destination_region, destination_bucket, destination_name | Identify destination |
| work_request_id, status, attempts | Track execution |
| expected_size, application_checksum | Verify outcome |

The job should bound concurrency, handle pagination when listing objects, retry transient failures with backoff, and persist per-item progress. Separate source-changed errors from network errors: the former requires re-evaluating which data to copy rather than blindly retrying the same request.

If an earlier run created the destination object and a retry hits an "already exists" condition, reconcile against the manifest and content before marking complete. A name collision alone does not prove the earlier copy succeeded cleanly.

## 8. Monitoring and evaluating RPO and RTO

**RPO** represents acceptable data loss measured in time during recovery. **RTO** represents the time required to restore service to the target operational level. These are system and operational objectives that must be measured through drills.

An empirical measurement can use:

~~~text
observed_replication_delay
  = time object becomes readable at destination
  - time source write completed

observed_recovery_time
  = time business verification at destination succeeds
  - time simulated incident began
~~~

Write a canary object with a unique name and UTC timestamp, check it at the destination, and record lag across varying load levels. Set alert thresholds according to business requirements. One canary arriving quickly does not prove all objects have arrived, especially across differing object sizes and write streams.

Combine three layers of checks:

| Layer | Signal | Decision supported |
| --- | --- | --- |
| Configuration | Policy status and error messages | Detect broken replication relationships |
| Data | Canary, manifest, reconciled latest business objects | Assess data recoverability |
| Application | Test login, document reads, and sample transactions in DR | Assess actual serving readiness |

Per the referenced Oracle documentation, the Console does not provide dedicated replication metrics. Therefore, do not build your entire alerting strategy assuming a built-in replication lag chart exists. [Source: Scope and Constraints](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm).

If the application uses Oracle Database or another database to store metadata, verify consistency between metadata and objects. Having Object Storage data ready does not replace recovery plans for databases, Compute, networking, keys, and application configuration.

## 9. Controlled failover and failback

### Failing over to the standby region

Suggested runbook:

1. Record the incident, the failover decision-maker, and the verified data cutoff.
2. Stop old writers from writing when possible so both sides do not accept concurrent updates.
3. Verify critical objects and application dependencies in the standby region.
4. If only reading replicated data is needed, evaluate serving reads directly from the destination.
5. If writes are required, explicitly terminate the replication destination role first.
6. Switch application configuration to the standby endpoint/bucket.
7. Run business validation checks and record any missing data or catch-up actions needed.

When writes in DR have been approved, illustrative command:

~~~powershell
$PromoteArgs = @(
    'os', 'replication', 'make-bucket-writable',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $DestinationBucket
)
oci @PromoteArgs
~~~

**MakeBucketWritable** stops receiving replication and makes the destination bucket writable. This is a data-role transition, not a read-only check. [Source: OCI CLI make-bucket-writable](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/replication/make-bucket-writable.html).

After stopping replication on the destination, the source policy can transition into an error state. Re-establishing the old relationship requires handling the source policy and recreating it per Oracle's procedure. Never expect to enable writes in DR and automatically resume bidirectional synchronization. [Source: Troubleshooting Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Troubleshooting/usingreplication_topic-Troubleshooting_Replication.htm).

### Returning to the original region

After DR has accepted writes for a period, the latest data may live in DR. A failback plan should:

- Identify the authoritative source for each data category.
- Reconcile changes made during the outage and resolve conflicts.
- Prepare the receiving bucket and permissions for the new replication direction.
- Backfill data created before creating the new policy.
- Switch applications within an agreed window, then run business verification.

Never just point endpoints back to the old region. Ignoring changes made in DR can cause applications to serve stale data or overwrite newer writes.

## 10. Versioning, retention, and cost

Replication does not carry full previous-version history to the destination; the destination cannot have versioning enabled. Therefore, if you must roll back an invoice modified by mistake, define clearly where history is retained and who can restore it. [Source: Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

When business rules require immutable storage, evaluate an independent archive/retention bucket with appropriate permissions and retention rules. Never plan around adding a retention rule to an active replication destination, since destination restrictions must be checked upfront.

Build budgets across these categories using your tenancy's actual unit prices and terms at deployment time:

- Source, destination, staging, and historical storage capacity.
- Volume of changed data, including repeated overwrites of the same object name.
- Read/write requests, copy operations, and cross-region data transfer.
- Reads, restores, and billing rules for each storage tier.
- Job execution, logs, monitoring, and drill costs.

You can roughly estimate data transfer volume:

~~~text
period transfer volume
  ≈ initial data loaded during the period
  + total volume of new writes and overwrites requiring transfer
~~~

Hypothetical example: 300 GB of initial data plus 20 GB of changed content per day over 30 days generates roughly 900 GB of transfer input before accounting for retries and operational specifics. This is a volume estimate for capacity planning, not an OCI billing formula.

If RTO requires immediate reads, test realistically before choosing Archive for the standby copy. Low storage unit prices alone do not determine total recovery cost or business response time.

## 11. Troubleshooting by symptom

| Symptom | Where to check |
| --- | --- |
| Cannot create policy | Regions, destination bucket, versioning, retention, and both IAM layers |
| Policy enters error state | Whether destination still accepts replication or was made writable; active permissions; capacity limits |
| Test does not see older objects | Compare upload timestamp against policy creation timestamp and backfill manifest |
| Copy accepted yet data not present | Work request status in the submitting region |
| Copy fails ETag condition | Compare source version and destination object state |
| Object exists yet app fails to read | DR app identity, endpoint config, read permissions, and keys |
| Referenced data missing | Compare metadata recovery point against object data point |
| DR has newer data not yet on old source | Perform reconciliation and failback; do not switch endpoints prematurely |

Causes of policy creation and replication errors are documented by Oracle in [Troubleshooting Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Troubleshooting/usingreplication_topic-Troubleshooting_Replication.htm). Rows about applications and workflows are investigation starting points to validate against your real architecture.

When reporting errors, save the request ID or work request ID, region, bucket name, object name, and UTC timestamp. Never put keys, tokens, or sensitive content into diagnostic logs.

## 12. Reinforcement exercise

Use sample data in the lab buckets to complete:

1. Upload one object before creating the policy and one after; record the difference at the destination.
2. Verify reading the post-policy object's content in the standby region.
3. Overwrite and delete a test object, observing the outcome and timing.
4. Copy the pre-policy object to the separate copy bucket, save the work request, and verify content.
5. Re-run the copy request with the anti-overwrite condition; explain how to handle it safely.
6. Write an application DR cutover runbook, including enabling writes and stopping old writers.
7. Evaluate cost impact if overwrite frequency increases sharply while end-of-period capacity stays nearly flat.

Required deliverables: source-destination diagram, IAM scope, a small manifest, destination read evidence, observed lag, and cutover steps. Never use a single ACTIVE status as your sole completion criterion.

After the lab, identify which data must be kept, stop the replication relationship as planned, and clean up test resources after verifying exact scope. Never clean up buckets actively used by applications.

## 13. Design takeaways

Start from data and recovery requirements: which data must exist in another region, whether losing the latest updates is acceptable, whether history is needed, and how applications choose where to read and write.

A sound deployment must prove three things: the replication relationship is configured correctly, destination data meets required recovery points, and the standby application can perform business operations. Replication, CopyObject, manifests, and runbooks work together to produce that evidence.