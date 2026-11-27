# Standard, Infrequent Access, and Archive tiers

## Lesson objectives

In OCI Object Storage, choosing a storage tier means choosing how objects are stored and retrieved to match the data lifecycle. A tier with lower storage cost does not necessarily have a lower total cost, and data that remains intact is not necessarily ready for immediate download when an application needs it.

This lesson belongs to the **Object Storage and Archive Storage** chapter of the **CLOUD_PROVIDERS_ORACLE** module. It connects object storage with IAM, applications, backups, lifecycle automation, and cost control on OCI.

After this lesson, you will be able to:

- Distinguish Standard, Infrequent Access, and Archive by access pattern and intended use.
- Select a tier based on access requirements, recovery time, and retention duration.
- Identify storage, retrieval, operation, minimum retention, and data transfer costs.
- Explain why Archive restore is an asynchronous workflow with a wait time and an access window.
- Distinguish tier transitions, lifecycle policies, Auto-Tiering, retention, and versioning.
- Design applications and test plans so data requiring immediate access is not placed into a flow that must wait for a restore.

This lesson does not treat a fixed price schedule, minimum duration, or restore time as a service guarantee. During implementation, verify the exact values, limits, and tier-transition capabilities supported by OCI for your specific bucket, object, and region.

## 1. An object is still an object, but how it is accessed changes

An object is identified within a namespace and bucket by its object name, along with a version when distinguishing versions. The storage tier is an attribute governing how the data is stored and served, not an access permission or a filename extension.

For example:

```text
Bucket: company-documents
Object name: reports/2026/11/summary.pdf
```

The `/` characters in the object name organize objects by prefix; they do not create a POSIX filesystem with mount operations and directory permissions like File Storage. Moving data to another tier also does not automatically change IAM permissions or make a bucket public.

You must distinguish a bucket's storage tier configuration from an object's tier and the transitions supported by the service. Do not assume you can change the bucket type or transition every object in every direction with the same operation. Before automating, confirm the bucket type, default configuration, and corresponding tier-change or copy flow.

## 2. Comparing the three tiers

| Criterion | Standard | Infrequent Access | Archive |
| --- | --- | --- | --- |
| Intended use | Frequently accessed data or data needing direct retrieval | Infrequently accessed data that still needs direct retrieval on demand | Rarely accessed, long-lived data where waiting before reading is acceptable |
| Requires an Archive restore workflow before reading? | No | No | Yes |
| Notable cost drivers | Stored capacity, operations, and related charges | Stored capacity, retrieval, and minimum retention conditions | Stored capacity, restore/retrieval, and minimum retention conditions |
| Application serving path | Can sit in a direct object-download flow | Can sit in a direct object-download flow | Needs a request-to-prepare flow and status polling |
| Suitable examples | Active content, current processing datasets | Older reports occasionally downloaded immediately | Long-term archives, rarely requested records where a wait time is acceptable |

**Infrequent Access does not mean waiting for a restore like Archive.** Its key difference is its cost model and infrequent-access purpose, not turning every download into an offline recovery job.

**Archive is not a cheaper-storage version of Standard where every behavior stays the same.** Applications must handle the restore step and the time window during which the object is made available for retrieval.

## 3. When to choose Standard?

Standard is suitable when data is in active use or when access cannot depend on an Archive preparation step.

Examples:

- Documents that users frequently view or download.
- Input datasets for an active pipeline.
- Newly generated processing results that multiple components will consume.
- A subset of backup data that must remain ready for fast recovery options.

Access frequency is not the only criterion. An object that is very rarely read yet must be immediately available during an incident is still unsuitable for Archive if restore wait time exceeds requirements.

Standard is also a candidate starting point for observation when you lack sufficient data on access behavior. Once you have evidence, you can evaluate other tiers through supported mechanisms. Do not change tiers solely because an object is old without knowing which business workflows still rely on it.

## 4. When to choose Infrequent Access?

### 4.1. Infrequent access, yet direct retrieval is still required

Infrequent Access, abbreviated IA, fits data read less often that must still be retrieved directly on demand rather than waiting for an Archive restore.

Examples:

- Last month's reports occasionally downloaded for reconciliation.
- Closed project documents that may still require immediate retrieval.
- Fallback data with low read rates needed by a workflow that cannot wait for Archive preparation.

Do not interpret IA as "a little slower" and assume a specific latency figure. Verify service characteristics and measure your application flow; the distinguishing design criterion is direct retrieval paired with a cost structure suited to infrequent reads.

### 4.2. Retrieval charges can offset storage savings

An object opened rarely, yet read in full at large size each time, can still generate significant retrieval volume. Conversely, many small partial reads produce a different cost profile.

Observe:

- Total read volume over time.
- Number of read operations and how the application splits requests.
- Whether background scans, periodic checks, or analytics jobs exist.
- Whether caching reduces actual reads against Object Storage.
- Bulk reload bursts when applications restart or lose cache.

Do not count only users clicking a download button. Internal jobs are also a source of retrieval traffic.

### 4.3. Minimum retention is a billing condition, not automatically a delete lock

IA has a minimum storage duration condition per service terms. Deleting or transitioning data early can incur corresponding charges under the applicable policy.

This differs from a retention rule used to restrict modifying or deleting data. An object may be permitted to be deleted from an authorization standpoint while still incurring a charge because the minimum duration was not met.

Before applying lifecycle rules, confirm when the minimum duration clock starts and how tier transitions, overwrites, or deletions interact with your active configuration. Do not assume every timer starts from the original object creation time.

## 5. When to choose Archive?

### 5.1. Long-term data where waiting is acceptable

Archive fits when read demand is low, retention duration is long enough, and the business accepts a preparation phase before retrieving content.

Examples:

- Historical records requested only during planned audits.
- Older backups outside the daily fast-recovery set.
- Raw data kept long-term to allow reprocessing in rare situations.

Not every dataset named "backup" or "audit" belongs in Archive. If investigations require downloading data within minutes or recovery objectives do not allow wait time, design a more readily accessible data layer or choose another tier.

### 5.2. Archive restore is not restoring a deleted version

In this context, restore means requesting that an object stored in Archive be made retrievable for a period of time according to service mechanics. It does not mean rolling back to a previous version, repairing corrupted data, or recovering a deleted object that has no remaining recovery source.

Versioning, backups, and retention solve different problems. A system needs both a way to keep the right data copies and a way to retrieve data from the tier where it resides.

### 5.3. Archive retrieval workflow

A conceptual flow:

```text
Identify the exact bucket, object, and version needed
  -> check tier and archival state
  -> submit a restore request with a supported retrieval window
  -> track the job/state using an appropriate mechanism
  -> once the object is ready, download within the allowed window
  -> verify content and store the result where needed
```

Exact state names, API fields, and durations must follow the corresponding OCI interface. The flow above describes behavior, not a request schema you can send directly.

An accepted restore request does not mean the object is already ready to download. Applications need to distinguish at least three situations: preparation not requested, preparation in progress, and ready to read.

### 5.4. Limited access window

Once restore completes, the data is made available for an access window according to the request and service limits. The processing workflow must have enough time to download, verify, and finish its work before that window expires.

Restoring does not permanently convert an Archive object to Standard. Once the window expires, reading it again may require a new restore request.

If restored data will continue to be used frequently, evaluate a workflow to copy or write it as an object in an appropriate tier using supported capabilities. Do not rely on continuously extending or repeating restores as a default substitute for changing the storage model.

Do not delete the source copy just because a copy operation has started. Verify the destination copy, content, permissions, and retention requirements before deciding the lifecycle of the old copy.

## 6. Choosing tiers by end-to-end system recovery time

### 6.1. Account for the whole process, not a single operation

For Archive data:

```text
Time to usable data
  = time to discover/identify the data
  + restore wait time
  + download time
  + verification time
  + time to import/recover into the application, if any
```

This is a planning model. Steps may overlap partially depending on the solution, but they must not be omitted when evaluating recovery time.

For example, an intact database backup in Archive still cannot serve queries immediately after the object is restored. You may still need to download multiple parts, prepare the database environment, apply logs, and verify consistency.

### 6.2. RPO differs from RTO

- **RPO** reflects the acceptable amount of data loss measured in time.
- **RTO** reflects the service recovery time target that must be met.

Tier selection alone does not guarantee either objective. RPO also depends on backup/replication frequency and data that was successfully written. RTO also depends on restore, network, Compute, software, and operational procedures.

For Oracle Database, inspect the entire recovery chain: base backups, incrementals, logs, and required metadata for the tooling in use. Do not place a mandatory link in the chain into Archive and then calculate recovery time using only the portion left in Standard.

### 6.3. Multi-tier data model

An illustrative layout:

| Data group | Requirement | Candidate tier |
| --- | --- | --- |
| Active data | Frequent, direct access | Standard |
| Older data that may be requested immediately | Rarely read, no wait for restore | Infrequent Access if total cost fits |
| Long-term historical data | Rarely read, wait workflow acceptable | Archive |

This is a grouping approach for evaluation, not an age-based rule to apply blindly to every system. Determine transition timing from access evidence and retention obligations.

## 7. Evaluating total cost

### 7.1. Components to include

A conceptual model:

```text
Total cost
  = storage by capacity and duration
  + retrieval/restore by tier and actual activity
  + API operations
  + data transfer along the applicable path
  + minimum storage duration adjustments, if any
  + resources for processing and related copies
```

Not every line item occurs equally across all tiers or access paths. Use the actual pricing schedule to determine what applies and avoid double-counting charges already included.

Also account for versions, copies, and recovery staging data. Downloading or copying data elsewhere can generate separate storage or Compute costs not captured in the source tier's price sheet.

### 7.2. Break-even example with hypothetical numbers

Suppose a mathematical model calculated:

- Moving a dataset to an infrequent-access tier reduces storage cost by 100 cost units per month.
- Incremental retrieval cost is 0.02 units per GiB read.
- Other items are assumed constant purely for illustration.

Then:

```text
Break-even read volume
  = 100 / 0.02
  = 5,000 GiB per month
```

If additional reads exceed that level, storage savings no longer offset retrieval in the hypothetical model. This is not an OCI price list and must not be used for real budgeting; it illustrates how to question real cost data.

If minimum retention, API, network, or restore charges apply, include them in the model before drawing conclusions.

### 7.3. Higher-than-forecast reads are a real risk

Situations that alter retrieval costs:

- Full dataset scans for analytics or audits.
- Migrating an application to a new environment and repopulating caches.
- An incident causing multiple instances to reload the same dataset simultaneously.
- The organization receiving bulk reconciliation requests.
- Repeated Archive restores because the access window was too short.

Budgets should cover both normal months and recovery or read-spike scenarios, not just a quiet month.

## 8. Lifecycle policies and Auto-Tiering

### 8.1. Lifecycle policies automate by rule

Lifecycle policies can automate service-supported actions such as tier transitions or object lifecycle handling. Before applying them, confirm filters, age calculation, and which objects the rule affects.

Questions to answer:

- Which bucket, prefix, and versions does the rule apply to?
- Which timestamp is used to evaluate the condition?
- Is there any data requiring immediate direct access inside the same scope?
- Does the tier transition align with minimum storage duration rules?
- Do retention rules or data-holding policies restrict the action?
- Does another rule produce effects that conflict with the current goal?

Lifecycle actions run as background service processes; do not treat a lifecycle threshold as a guarantee of transition down to a specific second.

### 8.2. Prefix is a technical scope, not automatically an accurate business classification

For example:

```text
active-documents/...
closed-projects/...
long-term-records/...
```

Readable prefixes help design rules, yet a file written by mistake under `long-term-records/` will still be processed by the rule there. Control how applications construct object names and how requirements evolve over time.

Do not share the same prefix between content users must download immediately and archival records where waiting is acceptable without a clear distinguishing mechanism.

### 8.3. Auto-Tiering does not replace the decision to move data to Archive

OCI Auto-Tiering automatically optimizes between Standard and Infrequent Access through supported mechanisms. Do not treat it as a mechanism that automatically moves data into Archive and designs an Archive restore flow for your application.

Before enabling it, confirm eligibility conditions, access-tracking behavior, and compatibility with existing lifecycle rules. Avoid two mechanisms or rules expressing conflicting intentions without understanding precedence.

Auto-Tiering also does not replace measuring application targets, checking costs, or understanding organizational retention requirements.

### 8.4. Last-Modified is not last read

When an object was modified and when its content was downloaded are two different concepts. An object unchanged for months may still be downloaded every day.

Do not use `Last-Modified` as proof that data is no longer accessed. Use appropriate observation sources such as application metrics, activity reports, or service-supported tracking mechanisms, with their scope and limitations clearly understood.

## 9. Designing applications for Archive data

### 9.1. Separate the preparation request from content download

For a Java application serving historical documents, an Archive download flow should not hold a synchronous HTTP request open waiting for the entire preparation process.

An architecture to evaluate:

1. The user requests access to a document.
2. The backend authenticates the user and checks authorization for the document.
3. The backend checks the tier/state of the exact object or version.
4. If a restore is needed, it creates or reuses an existing preparation task.
5. It returns an in-progress status along with a task identifier.
6. A worker polls progress with backoff, retry limits, and timeouts.
7. When ready, it provides a controlled download stream within the access window.
8. It tracks failures, expiration, and whether to re-request or move to another tier.

This is an illustrative architecture, not a mandate to implement an API with a fixed schema.

### 9.2. Prevent duplicate restores from concurrent requests

If multiple users request the same object concurrently, the application should coordinate by bucket/object/version identity and task state. Do not fire unlimited new restore requests every time a user clicks download.

Handle cases where a worker restarts, a request times out after the task was already accepted, or the access window expires. Retries must inspect the current state rather than assuming nothing happened previously.

### 9.3. Permissions and data protection still apply

The data-preparation service needs appropriate permissions to inspect metadata, request restores, and retrieve content per its assigned role. Do not grant tenancy-wide administrator privileges by default.

Time-limited URLs or sharing mechanisms, if used, do not replace the restore step and do not allow bypassing business-level user authorization checks. Do not make a bucket public just to simplify downloading a restored document.

If customer-managed encryption keys are used, maintain key usability and associated permissions throughout the data retention period. Keeping an object long-term while losing decryption capability fails recovery objectives.

## 10. Testing and tier-transition plan

### 10.1. Use a representative dataset

Select test objects matching real data in size, access patterns, and protection requirements. Keep a manifest containing identifiers, version where applicable, size, and content verification values using an appropriate mechanism.

Do not assume ETag is always the same checksum type across all upload methods and configurations. Use a supported verification mechanism and understand what the compared values represent.

### 10.2. Scenarios to test

| Scenario | What to observe | Purpose |
| --- | --- | --- |
| Reading Standard | Latency, errors, data transfer volume | Establish a baseline for direct-access flows |
| Reading Infrequent Access | Download capability and generated retrieval volume | Verify access requirements and cost model |
| Reading Archive before restore | Status/error returned by the service | Ensure the application accurately detects preparation needs |
| Restore then download | Time to ready, access window, and download speed | Assess whether RTO is met |
| Access window expiration | Download behavior and how to re-request | Avoid treating restore as a permanent tier change |
| Concurrent requests | Number of jobs/requests and shared state | Control duplicate restores and user experience |
| Missing permissions or unusable key | Clear errors, alerts, and handling capability | Distinguish authorization/key errors from tier issues or data loss |
| Lifecycle on test set | Exact scope and actual action taken | Prevent mis-transitioning data needing direct access |
| Full application recovery | Download, verification, import, and startup time | Do not measure only the object restore step |

Record actual measurements alongside test conditions. One successful restore proves the workflow works in that scenario; it does not guarantee every object size or every download wave will take the same time.

### 10.3. Expand scope after obtaining evidence

Before migrating large datasets, confirm that applications and operators know which tiers require waiting, where rules apply, and how to retrieve data.

Monitor metrics after transition: capacity per tier, read volume, restore jobs, recovery times, and actual spend. Compare against forecasts to adjust classification rather than assuming "moved to a cheaper tier" means the job is done.

Do not delete sources still needed for rollback, retention, or recovery chains simply because a test batch downloaded a few objects.

## 11. Selection worksheet and self-check

Complete the following worksheet for each dataset:

| Item | Details to record |
| --- | --- |
| Scope | Relevant namespace, bucket, prefix, object/version |
| Data role | Primary data, copy, cache, backup, or compliance archive |
| Access pattern | Read volume, frequency, object size, batch jobs, and burst reads |
| Time targets | Whether direct reads are needed, end-to-end recovery time |
| Retention duration | Business requirements, retention rules, and minimum storage conditions |
| Recommended tier | Standard, IA, or Archive with rationale |
| Transition mechanism | Supported operation, lifecycle policy, or Auto-Tiering as appropriate |
| Permissions and keys | Reader/restorer identities, sharing rules, and decryption capability |
| Total cost | Storage, retrieval/restore, API, network, copies, and minimum adjustments |
| Evidence | Results from read, restore, window expiration, and app recovery tests |
| Owner | Person managing rules, monitoring spend, and handling retrieval requests |

Self-check:

1. Why does Infrequent Access not mean restoring before every read?
2. Is a rarely used object that must be immediately available suitable for Archive? What else do you need to know?
3. Does Archive restore permanently change an object to Standard?
4. How does retrieving a backup from Archive differ from restoring a database?
5. How do minimum storage duration conditions differ from retention rules?
6. Why does total data volume read matter more than simply counting how many times users open a document?
7. Does Auto-Tiering replace deciding on and designing an Archive workflow?
8. Why can't Last-Modified be used as proof of last access time?
9. If the access window expires before download completes, which states must the application detect and handle?
10. Before migrating a large dataset, what evidence is needed regarding permissions, content, recovery time, and cost?

The output of this exercise is a well-grounded tier selection for each dataset, paired with a data retrieval workflow that meets business timing requirements and a verified cost model.
