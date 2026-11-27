# Object versioning and recovering overwritten data

In the **Object Storage and Archive Storage** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson focuses on an operational question: when an application overwrites an object with bad data, how do you restore the valid content while preserving an incident trail?

The scenario is an application on OCI Compute, running inside a VCN, reading configuration files or Oracle Database export data from a private bucket. The operations team coordinates tenancy, compartment, IAM, and Object Storage to recover data, audit actions, and control costs. Versioning is one layer of protection in that architecture; application availability also depends on error detection time and the ability to switch to recovered data.

## Learning objectives

After this lesson, you will be able to:

- Explain object name, version ID, latest version, and delete marker.
- Distinguish the three bucket versioning states and recognize when data is no longer protected.
- Recover overwritten content by reading a specific version and creating a new latest version.
- Distinguish overwrite recovery, recovering a deleted object, and restoring from Archive Storage.
- Design action permissions, history retention windows, and verification evidence for a recovery workflow.

## Data model: one object name, multiple versions

Suppose an application always reads the object `config/payment.json`. This name is a stable lookup key; subsequent updates can carry different content.

When versioning is enabled on a bucket, a new write makes the newly written version the **latest version**; prior content can remain as a **previous version**. A **Version ID** identifies a specific version. Normal access by object name retrieves the latest content; reading history requires specifying a version. See [Oracle Object Storage versioning concepts](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

The example below uses labels V1, V2, V3 for illustration, not actual version IDs:

| Timestamp | Action on the same object name | Current content | Historical content |
| --- | --- | --- | --- |
| 09:00 | Upload valid configuration | V1 | None yet |
| 09:10 | Pipeline uploads faulty configuration | V2 | V1 |
| 09:20 | Read V1 and re-upload | V3, with content matching V1 | V1 and V2 |

V3 receives a new identifier. Recovering by re-uploading neither rewinds time nor deletes V2. This preserves the faulty copy for investigation and clearly represents the corrective action.

~~~mermaid
sequenceDiagram
    participant P as Pipeline
    participant B as Versioned Bucket
    participant O as Operator
    P->>B: Write valid configuration
    Note over B: V1 current
    P->>B: Overwrite with faulty configuration
    Note over B: V2 current, V1 remains in history
    O->>B: Read exact version ID of V1
    B-->>O: V1 content
    O->>O: Verify checksum and business content
    O->>B: Upload verified content
    Note over B: V3 current, keeping V1 and V2
~~~

Do not use version IDs as sequence numbers to infer chronological order. In operational procedures, cross-check timestamps, content, update sources, and identifiers recorded in deployment logs. An older copy is not automatically the right copy.

## Bucket versioning states

Versioning is configured at the bucket level. States to distinguish:

| State | Operational meaning |
| --- | --- |
| `Disabled` | Bucket has never had versioning enabled; overwrites retain no history recoverable via this feature |
| `Enabled` | Creates and retains versions upon updates; existing versions can still be read |
| `Suspended` | Stops creating new history for subsequent overwrites or deletes; previously retained versions remain unless deleted |

Once enabled, a bucket cannot return to `Disabled`; it can transition to `Suspended` and then back to `Enabled`. The bucket update CLI accepts `Enabled` and `Suspended`. See [UpdateBucket versioning parameter](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/update.html).

Enabling versioning after an incident cannot recreate content lost beforehand. Similarly, seeing a bucket as Enabled today does not prove it protected an overwrite that occurred yesterday. During an investigation, verify the state at the time of change and confirm that the version needed for recovery actually still exists.

In infrastructure automation, explicitly declare the desired versioning state, detect drift toward Suspended, and restrict who can modify buckets. Enabling versioning in the Console only to have an infrastructure deployment later flip it to Suspended breaks the intended protection window.

## Three easily confused actions during deletion and recovery

### Deleting an object by name

In an Enabled bucket, deleting an object without specifying a version ID creates a **delete marker**. The marker flags the deleted state; prior version data can still remain. Normal access by name will not return old data merely because it exists in history.

If you remove the marker hiding a valid data version, the underlying version can become current again. In the Console, toggle showing deleted objects and inspect the version list. See [recovering a deleted object](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning_topic-To_recover_a_deleted_object.htm).

### Deleting a specific version

Deleting with a version ID permanently deletes the selected version, even if it is currently the latest version. Versioning does not automatically create an extra copy to rescue a permanently deleted version. See [deleting Object Storage versions](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning_topic-To_delete_an_object.htm).

Therefore, when V2 is faulty and V1 is still good, prefer reading V1 and writing it back as a new version. Deleting V2 to expose the underlying copy destroys part of the evidence and ties recovery to an irreversible delete permission.

### Restoring data in Archive Storage

Restoring from Archive makes a cold-stored object readable for a recovery window. It solves cold-data accessibility, not selecting the right business version after an overwrite. Wait for the restore process to finish before downloading data. See [restoring objects from Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects_topic-To_restore_objects_from_Archive_Storage.htm).

If the good version has already transitioned to Archive, the workflow adds a step to restore **that exact version**, then download, verify, and promote the content as the current version. The restore CLI accepts a version ID parameter; do not omit the identifier when needing a specific historical version. See [OCI CLI object restore](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/restore.html).

## IAM permissions and recovery scope

A bucket resides in a compartment, yet recovery permission does not arise merely from knowing the bucket name. Permission design should separate duties:

| Role | Need | Recommended boundary |
| --- | --- | --- |
| Data-writing application | Create or overwrite objects per business logic | Only required bucket or prefix; do not grant history deletion by default |
| Incident investigator | List and read versions | Read data only, do not modify bucket configuration |
| Recovery operator | Read good copy and write replacement | Assigned bucket scope, with audited actions |
| History cleaner | Delete versions per policy | Separated from normal application accounts |
| Bucket administrator | Configure versioning and lifecycle | Control changes to data-protection settings |

In OCI permissions, modifying buckets involves `BUCKET_UPDATE`; deleting objects and deleting versions are separate permissions: `OBJECT_DELETE` and `OBJECT_VERSION_DELETE`. `manage objects` includes deleting versions, so granting it broadly to applications can weaken history protection. See [IAM reference for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

When writing real policies, administrators must verify the APIs called, compartment scope, and bucket/object conditions. Never assume a list of roles in a design document replaces deployed policies. The lab below assumes the account already has permission to read the namespace, read/update the bucket, list/read, and create/overwrite objects in the lab bucket.

If the application runs in a private VCN subnet, also confirm the network path to the Object Storage endpoint fits the architecture, such as routing via a Service Gateway. Access errors caused by networking, wrong region, or missing permissions are not proof that a version was lost.

## Operational workflow for handling overwrites

A recovery workflow can follow six steps:

1. **Isolate the change.** Pause the faulty pipeline or write stream; record the region, namespace, bucket, object name, and detection time.
2. **Capture initial state.** Record the current version ID and ETag, list of related versions, timestamps, and change source. If data classification permits, preserve the faulty copy in a controlled investigation location.
3. **Select a candidate.** Read the expected good version by version ID. Cross-check release IDs, known checksums, or business checks.
4. **Recover safely.** Create a new latest version from the verified content. Use an ETag condition or a write-freeze window to avoid overwriting another change.
5. **Read back as the application does.** Download the object without specifying a version ID, verify content, and run relevant application checks.
6. **Resume writes and monitor.** Confirm the application loaded the new copy, update the incident record, and address the root cause.

Version ID and ETag serve two different purposes. Version ID selects specific source data; ETag is used in conditions to detect whether the resource changed since it was inspected. Do not treat ETag as a business checksum or assume it is the MD5 of the content.

If the ETag condition no longer matches, stop and evaluate what just changed. Fetching the new ETag and blindly retrying the write can overwrite someone else's valid fix.

## Hands-on lab: recover an overwritten configuration file

The following commands are for **Bash**, such as OCI Cloud Shell. This is a lab on a pre-created private lab bucket, initially empty and without concurrent writers. Do not use a real data bucket.

Prepare an authenticated OCI CLI and a Standard bucket named `versioning-lab` in your region. The bucket must have no active retention rules or other settings preventing versioning from being enabled. Replace region and bucket below to match your environment. Object names and sample contents contain no secrets.

### Prepare and enable versioning

~~~bash
set -euo pipefail

REGION="ap-singapore-1"
BUCKET="versioning-lab"
KEY="lab/config.json"
LAB_DIR="$(mktemp -d)"

NS="$(oci os ns get --region "$REGION" --query data --raw-output)"
test -n "$NS"

oci os bucket get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET"

oci os bucket update \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --versioning Enabled

oci os bucket get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" \
  --query 'data.versioning' --raw-output
~~~

The final output must be `Enabled`. If enabling fails, resolve the cause before uploading data that needs protection. Do not continue simply because the update command was issued.

### Create a good version and record its identifier

~~~bash
printf '%s\n' '{"release":1,"paymentEnabled":true}' > "$LAB_DIR/good.json"
printf '%s\n' '{"release":2,"paymentEnabled":false}' > "$LAB_DIR/bad.json"

oci os object put \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/good.json" \
  --content-type application/json --no-multipart

oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all

V1="$(oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all \
  --query 'data.items[0]."version-id"' --raw-output)"

test -n "$V1"
test "$V1" != "null"
printf 'Recorded version: %s\n' "$V1"
~~~

At this point the lab bucket contains only one object and one version, so picking the first item suffices for the example. In a real bucket, `--prefix` is a prefix filter and may return multiple object names; match the exact object name, exclude delete markers, and select the version based on evidence rather than copying positional indexing.

The list command returns entries under `data.items`, including name, version ID, and delete-marker indicator. Refer to [listing object versions in OCI](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning_topic-To_list_object_versions.htm). `--all` retrieves all result pages; omitting pagination can lead you to wrongly conclude the version does not exist. See [OCI CLI list-object-versions](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/list-object-versions.html).

### Simulate a faulty overwrite

~~~bash
oci os object put \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/bad.json" \
  --content-type application/json --no-multipart --force

oci os object get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/current-bad.json"

cat "$LAB_DIR/current-bad.json"

oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all
~~~

Reading without a version ID should show release 2 with `paymentEnabled:false`. The version list should still contain the first version. This is the expected result for the learner to verify, not output from a pre-executed run.

### Read the exact historical version and verify

~~~bash
oci os object get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --version-id "$V1" \
  --file "$LAB_DIR/recovered.json"

cmp "$LAB_DIR/good.json" "$LAB_DIR/recovered.json"
cat "$LAB_DIR/recovered.json"
~~~

`cmp` must exit with success and print no differences. In the lab, the good source file serves as the reference baseline. In a real incident, use a checksum from a trusted release artifact or appropriate business validation; downloading without error alone does not prove the data is right.

The `--version-id` flag in [OCI CLI object get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/get.html) lets you read the exact version even when the object name currently points to different content.

### Write back the good content with an ETag condition

After verifying the good copy, fetch the ETag of the current object:

~~~bash
CURRENT_ETAG="$(oci os object head \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --query etag --raw-output)"

test -n "$CURRENT_ETAG"
test "$CURRENT_ETAG" != "null"

oci os object put \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/recovered.json" \
  --content-type application/json \
  --if-match "$CURRENT_ETAG" --no-multipart --force
~~~

`head` fetches metadata and ETag without downloading the entire content. See [OCI CLI object head](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/head.html). The `--if-match` condition allows the write only if the ETag still matches; `--force` skips the CLI overwrite prompt and does not replace concurrency protection. This example uses a small object and single-part upload. See [OCI CLI object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

In real systems, capture the ETag during the same step that inspects current state and enforce it when writing. The lab has no other writers; in production with multiple writers, prefer pausing or coordinating them during the recovery window.

Re-uploading from a local file does not automatically carry over all metadata from the source version. The lab explicitly sets Content-Type; real data may also require preserving business metadata, Content-Encoding, or Cache-Control. Record and re-apply required attributes instead of verifying payload bytes alone.

### Read back the current copy and confirm history

~~~bash
oci os object get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/current-restored.json"

cmp "$LAB_DIR/good.json" "$LAB_DIR/current-restored.json"

oci os object head \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY"

oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all
~~~

The lab meets its goal when a normal read returns release 1 content, a new latest version exists, and previous versions remain preserved. With exactly three successful uploads, no retries creating extra writes, and no other operations, three data versions are expected.

Applications may keep configuration in memory or cache it in another layer. After Object Storage is right, verify the application has reloaded the data; checking the Console alone is not enough to conclude the payment flow has recovered.

Local files reside in the temporary directory printed by `printf '%s\n' "$LAB_DIR"`. After the lab, clean up according to environment policy. Deleting an object by name in an Enabled bucket does not mean all versions were deleted and all storage space was freed.

## Service-side copy option

For large objects, you can choose CopyObject instead of downloading to a workstation and re-uploading. Specify `--source-version-id` explicitly to avoid accidentally copying the faulty current version. You can copy to a staging key or existing recovery bucket before replacing the key used by the application.

The following example is an alternative after `V1` exists in the lab; it creates a new key for verification:

~~~bash
RECOVERY_KEY="recovery/config-v1.json"

oci os object copy \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" \
  --source-object-name "$KEY" --source-version-id "$V1" \
  --destination-namespace "$NS" \
  --destination-region "$REGION" \
  --destination-bucket "$BUCKET" \
  --destination-object-name "$RECOVERY_KEY" \
  --destination-object-if-none-match-e-tag '*' \
  --wait-for-state COMPLETED
~~~

The copy command is asynchronous; monitor the work request to completion and read back the result. If the test key already exists, the condition in the example prevents overwriting. When replacing an existing object, you can use a destination ETag condition. These parameters are documented in [OCI CLI object copy](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/copy.html).

Copy requires both caller permissions and permissions for the Object Storage service to act on the user's behalf. Grant service permissions scoped to the required region and buckets; never fix copy errors by granting tenancy-wide permissions by default. Copying from Archive also requires restoring first. See [CopyObject prerequisites and permissions](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/copyingobjects.htm).

This copies one selected version, not the entire version history to the destination. If the goal is an independent recovery replica, explicitly design which versions are copied and how they are verified.

## If an object was deleted: handling delete markers

This situation differs from the faulty overwrite in the main lab. First, list versions of the exact object name, locate the entry with `is-delete-marker: true`, and confirm it is the marker to remove. With a latest delete marker and a good data version directly underneath, removing the marker can make the data reappear.

The example below illustrates syntax only; replace the ID after verification and never pass the ID of a data version:

~~~bash
DELETE_MARKER_ID="REPLACE_WITH_CONFIRMED_DELETE_MARKER_ID"

oci os object delete \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --object-name "$KEY" \
  --version-id "$DELETE_MARKER_ID"
~~~

The CLI prompts for confirmation. Confirm only after verifying the exact object name and marker. Running this same command with the ID of a data version permanently deletes that version. See [OCI CLI object delete syntax](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/delete.html).

If there are multiple markers or interleaved writes, do not bulk-delete markers with a context-free filter. Selecting a good data version and creating a new latest version usually gives clearer control over the outcome. After any recovery method, still read back by normal object name to verify what the application will see.

## Recovery windows, lifecycle, and cost

Versioning retains multiple data copies, so billable capacity can far exceed the size of the current version. Initial engineering estimates must sum the size of all retained versions rather than counting only object names. This is a capacity-estimation model, not an OCI price quote.

Hypothetical example: a 100 MiB object has its full content replaced 12 times per day. Keeping old versions for 30 days can accumulate roughly 360 previous versions, or around 35.2 GiB, plus the current version. That figure only illustrates a constant-size object with no lifecycle rules and no other writes; actual costs also depend on tier, retention duration, requests, retrieval, and data transfer.

Operational policies can be tailored per data group:

| Data group | Question to answer before setting lifecycle rules |
| --- | --- |
| Deployment configuration | How long does operations typically take to detect a faulty config? |
| Report exports | Do multiple periods need comparison and re-verification of published outputs? |
| Temporary data | Does history genuinely need to outlive the job lifecycle? |
| Database recovery data | Which files must belong together in one consistent recovery set? |

Lifecycle supports managing previous versions. The age of a previous version may be measured from when it transitioned from latest to previous; read the rule criteria carefully. Deleting a previous version is permanent, so the retention window must cover both error-detection time and remediation time. Lifecycle runs as a background process and should not be treated as deletion at an exact second. See [Object Lifecycle Management](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm).

If transitioning older versions to Archive to reduce hot-tier capacity, weigh that against retrieval time and cost. A configuration needing recovery within minutes should not depend solely on a good version sitting in a tier that requires waiting for a restore.

## Limits to account for in design

Versioning lets you roll back the content of individual objects whose history was retained. It does not validate data correctness and does not provide multi-object recovery transactions.

For example, an Oracle data export set comprises `manifest.json`, `customers.csv`, and `orders.csv`. Rolling back `orders.csv` alone while the other two belong to another export run can leave the dataset inconsistent. A recommended design generates an export batch ID, writes a manifest listing each file's name and version ID or checksum, and validates the entire set before consumption.

Do not rely on versioning as the sole defense against a compromised admin account. Anyone with permission to delete versions or configure broad lifecycle rules can still destroy history. Combine separation of duties, encryption key management where applicable, and recovery copies per system requirements.

If using retention rules or replication, check compatibility before combining them: OCI enforces constraints between active retention rules and versioning; replication does not copy all previous versions and destination buckets have specific restrictions. See [interactions between versioning and Object Storage features](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

## Tracking and completion evidence

Deployment logs and incident records should link an object to the source of change. A minimal recovery record can include:

~~~text
Incident: INC-EXAMPLE-017
Region / namespace / bucket: confirmed values
Object name: config/payment.json
Detection timestamp: include timezone
Version before recovery: identifier of the faulty version
Source version: identifier of the verified version
Pre-operation ETag: value used as condition
Version after recovery: new identifier
Verification: checksum or content check + application check
Operator / automation source: traceability identifier
~~~

This is a suggested record template, not real incident data. When reviewing Audit or related logs, correlate timestamps, caller identity, and request IDs of evidenced operations; never infer full object contents from API names in logs alone.

Periodically monitor versioning status on critical buckets, version count growth, historical storage usage, access errors, and recovery drill outcomes. For workloads on Compute, close an incident only when both Object Storage reads and application behavior are confirmed.

## Handling common scenarios

| Symptom | What to check | Action |
| --- | --- | --- |
| Good version not found | Exact region, namespace, bucket, name, pagination; bucket state at write time | List all versions and check deployment evidence |
| Reading by name reports not found | Whether a current delete marker exists | Read specific data version or handle confirmed marker |
| Reading a specific version is denied | IAM, network path, encryption keys if any | Fix permissions or access conditions within assigned scope |
| Recovery write fails ETag condition | Whether another writer modified the object mid-process | Stop, inspect the new change, and coordinate |
| Cannot download older version yet | Whether that version is in Archive or restoring | Restore that exact version, wait for completion, then read |
| Copy yields no result yet | Work request and Object Storage service permissions | Check status, errors, and read back destination object |
| Current copy is right yet app still fails | Cache, loaded config, related files | Inspect actual read path and full dataset consistency |
| Storage size does not drop after delete | Retained previous versions and markers | Inspect version history and version-cleanup policies |

If a version was permanently deleted or content was overwritten while unprotected, do not promise recovery via versioning. In that case, locate an independent copy or regenerate the data from a trusted source.

A solid workflow combines three pieces of evidence: the right source version was selected, the new current version was read back accurately, and the application operates properly with the recovered data.