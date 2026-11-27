# Designing IAM policies for buckets and objects

In Oracle Cloud Infrastructure (OCI), an application may need to download invoices from Object Storage without being allowed to delete data, modify bucket configuration, or issue sharing links. An Oracle Database backup process needs to push data into a bucket, while an operations team only needs to inspect configuration and monitor errors. Granting the same administrative privileges to all of these principals erases responsibility boundaries.

This lesson belongs to the **Object Storage and Archive Storage** chapter within the **CLOUD_PROVIDERS_ORACLE** module. It connects tenancy, compartment, and IAM knowledge to Compute, storage, and backup scenarios: designing least privilege, using identities for automation, observing access, and restricting operations that can cause data loss or unexpected costs.

After this lesson, you will be able to:

- Translate business requirements into concrete principals, resource scopes, and permissions.
- Separate bucket management permissions from object read, create, overwrite, and delete permissions.
- Write policies scoped to a bucket or prefix, while understanding the limits of listing permissions.
- Build a permission test matrix for users and workloads before putting policies into production.

## The authorization model to master

An access requirement needs to answer four questions:

| Question | Design component |
| --- | --- |
| Who performs the action? | Users via groups; workloads via dynamic groups or corresponding principal mechanisms |
| What action is performed? | API operations and the permissions those operations require |
| On which data? | Compartment containing the bucket, bucket name, object name or pattern |
| Under what constraints? | IAM conditions and related protection mechanisms |

Do not equate **authentication** with **authorization**. An API key or instance principal lets OCI identify the caller. Policies decide what that identity is allowed to do.

You must also separate the **network path** from **data permissions**. For example, a design where Compute in a private subnet reaches Object Storage via a Service Gateway still requires an appropriate IAM policy. Having a network route to the service does not grant permission to download objects.

### Buckets and objects are two scopes of responsibility

A bucket is where storage attributes and data protection settings are configured. An object is the content stored inside a bucket. In permission design, separate two groups of tasks:

- **Bucket management:** viewing or modifying configuration, managing sharing and protection mechanisms.
- **Object access:** listing names, reading content, creating new objects, overwriting, deleting, or restoring from Archive.

An account allowed to download objects does not necessarily need permission to alter bucket configuration. Conversely, someone auditing bucket configuration may not need to read invoice contents.

OCI provides the resource types `buckets`, `objects`, `objectstorage-namespaces`, and the aggregate family `object-family`. Choosing specific resource types expresses responsibilities more clearly than granting broad permissions across the entire family. See [Policy Reference for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

## Start from requirements, not from policy syntax

Suppose the system has a compartment `DataProd` with two private buckets:

- `billing-documents-prod`: stores invoices and ingested data.
- `db-backups-prod`: stores database backups.

Initial role design:

| Illustrative role | Valid requirement | Actions that must be blocked |
| --- | --- | --- |
| `BillingReaders` | List and download data in the billing bucket | Upload, overwrite, delete, change bucket config |
| `InvoicePrefixReaders` | Download known object names under `invoices/` | List entire bucket, read outside prefix |
| `BillingUploaders` | Create new object names under `incoming/` | Read, overwrite existing names, delete |
| `StorageMetadataAuditors` | View billing bucket configuration | Download invoice contents, modify config |
| `AuditUploadAgents` | Compute automatically uploads small payloads to `incoming/` | Use personal keys, modify or delete uploaded data |
| `ArchiveRecoveryOperators` | Request restores and read backups | Delete backups, modify bucket |

These are choices for the learning scenario, not built-in OCI roles. Before writing real policies, specify:

1. Which compartment the bucket resides in.
2. Whether the caller is a user or a workload.
3. Which APIs the client calls, including implicit API calls.
4. Whether listing, multipart, overwrite, PAR, or restore is needed.
5. Whether broader policies, inherited permissions, or other protection mechanisms also apply.

A requirement to "allow uploads" is not specific enough. Uploading a small object under a new name and uploading a large backup via multipart can require different permission sets.

## Policy syntax and scope

An allow statement has the form:

```text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
```

Example:

```text
Allow group BillingReaders to read objects in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

Components of the example:

| Component | Meaning |
| --- | --- |
| `group BillingReaders` | Grants permissions to members of the group |
| `read objects` | Selects the verb and resource type |
| `in compartment DataProd` | Scopes the resource location |
| `target.bucket.name` | Further restricts which bucket can be accessed |

Groups and dynamic groups in these examples are assumed to belong to the default identity domain. If using another domain, qualify the subject with the domain, such as `group FinanceDomain/BillingReaders`. OCIDs can be used when exact identification is needed; never leave placeholders in deployed policies. See [IAM Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm) and [identifying subjects in policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm).

### Distinguish where a policy is stored from resource scope

A policy is a resource managed at the tenancy or compartment level. The `in compartment ...` clause in a statement specifies the scope of resources being granted access; storing a policy at the root does not mean the policy grants access across the entire tenancy.

In this example, IAM administrators can manage the policy at the root compartment while the statement still applies only to `DataProd`. For nested compartments, use the appropriate compartment path or the `in compartment id <compartment_ocid>` syntax.

Child compartments inherit permissions from parent compartments. Placing a bucket in its own compartment only isolates permissions when ancestor policies are also appropriately scoped. See [Managing Compartments and inherited permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm).

### A narrow allow statement does not revoke a broad allow statement

Suppose the same user belongs to two groups:

```text
Allow group BillingReaders to read objects in compartment DataProd
where target.bucket.name = 'billing-documents-prod'

Allow group LegacyStorageAdmins to manage object-family in tenancy
```

If the user still belongs to `LegacyStorageAdmins`, the first statement does not turn them into a read-only user. When evaluating permissions, you must account for all effective permission grants.

OCI introduced **deny policies** as a tenancy-level opt-in feature. This lesson builds allow policies and does not assume the tenancy has enabled deny policies. If your environment uses deny policies, evaluate those constraints too; never infer effective access from a single allow statement alone. See [IAM deny policies release notes](https://docs.oracle.com/en-us/iaas/releasenotes/identity/deny-policies.htm).

## Understand verbs before choosing permissions

The verbs `inspect`, `read`, `use`, and `manage` represent increasing levels of access. However, their exact meaning depends on the resource type. For `objects`, a common pitfall is that `use` grants overwrite permission but does not automatically grant permission to create a new object. Verb names are no substitute for reading the service's permission table.

To design least privilege, map the APIs for the operations actually needed:

| Operation | Primary permission to check |
| --- | --- |
| List buckets | `BUCKET_INSPECT` |
| View bucket configuration | `BUCKET_READ` |
| List objects | `OBJECT_INSPECT` |
| Download object content | `OBJECT_READ` |
| Put object with a non-existent name | `OBJECT_CREATE` |
| Put object with an existing name | `OBJECT_OVERWRITE` |
| Delete object | `OBJECT_DELETE` |
| Delete a version | `OBJECT_VERSION_DELETE` |
| Request Archive object restore | `OBJECT_RESTORE` |
| Manage pre-authenticated requests | `PAR_MANAGE` |

This table is for design reference and does not represent every service API. Workflows such as multipart, lifecycle, copy, and replication may require multiple permissions or permissions for a service principal. Consult [permissions by API operation](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm) when choosing your client and workflow.

Two practical consequences follow:

- `read buckets` does not express permission to download object contents; that requires permissions on `objects`.
- `manage objects` without permission conditions is far broader than "create new objects only".

## Bucket-scoped read policy pattern

The `BillingReaders` group needs to list and download all objects in the billing bucket:

```text
Allow group BillingReaders to read objects in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

This policy fits when an application needs to browse the object list before downloading. It also allows seeing object names in the bucket, so assess whether object names contain sensitive data.

If the group genuinely needs to view bucket configuration, add a separate statement:

```text
Allow group BillingReaders to read buckets in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

Do not add the second statement just to make an authorization error disappear. For APIs/CLIs that already know the namespace, bucket, and object name, the design may not need the Console's resource discovery flow.

A configuration-auditor group uses a separate role:

```text
Allow group StorageMetadataAuditors to read buckets in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

If the Console needs to list buckets, consider discovery permission separately:

```text
Allow group StorageMetadataAuditors to inspect buckets in compartment DataProd
```

This discovery statement scopes to **all bucket names in the compartment**. It must not be treated as permission to see only one bucket. If exposing bucket names is inappropriate, choose a direct-access workflow or redesign compartment boundaries.

## Prefix-scoped object read pattern

Suppose an application already knows the exact object to download and may only read names starting with `invoices/`:

```text
Allow group InvoicePrefixReaders to manage objects in compartment DataProd
where all {
  target.bucket.name = 'billing-documents-prod',
  target.object.name = 'invoices/*',
  request.permission = 'OBJECT_READ'
}
```

Here, `manage` sets the base verb scope, while `request.permission` narrows the statement down to read permission. Every condition inside `all` must be satisfied simultaneously.

Design examples:

| Requested object | Expected result for this role |
| --- | --- |
| `invoices/2026/november-001.pdf` | Allowed to read |
| `invoices/archive/2025-001.pdf` | Allowed to read |
| `payroll/2026/november.csv` | Denied |
| `invoices-old/november-001.pdf` | Denied |

A prefix is part of the object name, not a directory with its own ACL. OCI supports `target.object.name` and patterns for object-level authorization; this example uses `/` to form a clear name boundary. See [IAM at the object level and object naming](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm).

### Listing is a separate decision

The pattern above does not grant `OBJECT_INSPECT`, so it cannot be used to list objects. It serves direct downloads of known object names.

If you add a statement granting `OBJECT_INSPECT` across the whole bucket, you also open discovery of all object names in that bucket. The `--prefix` parameter in a CLI command is a client-supplied filter; never treat a client filter argument as proof of an authorization boundary.

When an application needs both discovery and data restriction:

- Clarify whether seeing object names outside the prefix is acceptable.
- Test listing and direct access outside the prefix separately.
- If isolating both names and contents is complex, consider splitting buckets by dataset.

Bucket names are case-sensitive in the service, yet the IAM reference notes that bucket name conditions are matched case-insensitively. Avoid designing isolation boundaries using bucket names that differ only in letter case. See [Object Storage condition variables](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

## Create-new-objects-only pattern

For ingested data, the requirement may be "upload once, do not read back, and do not modify previously uploaded data":

```text
Allow group BillingUploaders to manage objects in compartment DataProd
where all {
  target.bucket.name = 'billing-documents-prod',
  target.object.name = 'incoming/*',
  request.permission = 'OBJECT_CREATE'
}
```

This permission set is designed for single-part PutObject flows using new names:

- Uploading a new name under `incoming/`: allowed.
- Re-uploading the exact same existing name: denied for lack of overwrite permission.
- Reading or deleting objects: denied for lack of corresponding permissions.
- Uploading outside `incoming/`: fails the object name condition.

Applications should generate unique names, such as `incoming/<request-id>.json`, and log the request ID for retry handling. When a connection drops after upload, the client may not know whether the request completed. Do not handle every retry by granting overwrite permission; instead define how to reconcile outcomes and prevent duplicate submissions.

Create-only permission does not make data immutable against every principal. An administrator or another workload with delete/overwrite permissions can still act per its permissions. For data needing long-term protection, design retention rules, versioning, and appropriate separation of duties.

### Multipart changes permission requirements

Clients can automatically switch large files to multipart upload. Per the OCI reference, multipart steps require overwrite permission as well; the commit step can also require bucket and object read permissions. Thus, a policy with only `OBJECT_CREATE` is not a universal upload pattern for all file sizes. See [multipart permission requirements](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

For a large backup workload where the business accepts read and overwrite permissions, you can design a separate role in a dedicated bucket:

```text
Allow group BulkBackupUploaders to read buckets in compartment DataProd
where target.bucket.name = 'db-backups-prod'

Allow group BulkBackupUploaders to manage objects in compartment DataProd
where all {
  target.bucket.name = 'db-backups-prod',
  any {
    request.permission = 'OBJECT_CREATE',
    request.permission = 'OBJECT_OVERWRITE',
    request.permission = 'OBJECT_READ',
    request.permission = 'OBJECT_INSPECT'
  }
}
```

This role **has read and overwrite permissions**, so it must not be described as "write-new-only". Not granting delete also means multipart abort flows require separate review: the abort operation requires delete permission per OCI's API permission table.

The practical decision rests on three factors: data size, SDK/CLI behavior, and backup protection requirements. Choose them together.

## Using dynamic groups for workloads on Compute

A process running on Compute should have its own workload identity rather than using an operator's personal API key.

Example dynamic group `AuditUploadAgents` matching a single instance:

```text
instance.id = '<INSTANCE_OCID>'
```

The matching rule defines membership; it does not grant data permissions yet. Next, create the policy:

```text
Allow dynamic-group AuditUploadAgents to manage objects in compartment DataProd
where all {
  target.bucket.name = 'billing-documents-prod',
  target.object.name = 'incoming/*',
  request.permission = 'OBJECT_CREATE'
}
```

Replace placeholders with actual OCIDs before use. If you broaden the matching rule to all instances in a compartment, also review who has permission to create or modify eligible instances. See [Writing Matching Rules to Define Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/Writing_Matching_Rules_to_Define_Dynamic_Groups.htm).

To test from that exact instance with the OCI CLI, use the corresponding authentication method:

```powershell
oci os object put --auth instance_principal --region ap-singapore-1 --namespace-name <NAMESPACE> --bucket-name billing-documents-prod --name incoming/<UNIQUE_NAME>.txt --file <SMALL_LOCAL_FILE> --no-multipart --force
```

Replace all values in `<...>` before running. This pattern targets a small file and create-only permission. `--force` controls CLI prompt behavior; it does not bypass IAM or grant `OBJECT_OVERWRITE`. Refer to [CLI authentication methods](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/oci.html) and [object put command](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

Do not run `instance_principal` from your laptop and conclude from the error that the policy is wrong. Test from an environment that actually holds the instance identity included in the dynamic group.

## Separate sharing permissions from upload permissions

A pre-authenticated request (PAR) creates a URL allowing anyone holding that URL to access resources per the granted scope and access type. Sharing that URL becomes part of data access control.

If a task only uploads invoices, there is no default reason to grant `PAR_MANAGE`. Permission to create a PAR must also be accompanied by data permissions matching the shared access type. See [PAR permissions and limits](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests.htm).

A more controllable design:

1. The upload workload has only the data permissions it needs.
2. A separate sharing role creates PARs upon approved business requests.
3. Sharing requests specify the object/prefix, recipient, access type, and expiration.
4. URLs are handled as secrets with a revocation plan.

Do not change a bucket to public to work around an application IAM error. Changing public access is a completely different decision from granting permissions to an authenticated principal. Oracle recommends restricting which groups hold `BUCKET_UPDATE`, since it can affect public access configuration. See [Securing Object Storage](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm).

## Permissions for Archive recovery

Reading objects and requesting Archive object restores are two distinct needs that should be separated. For a recovery role on the backup bucket:

```text
Allow group ArchiveRecoveryOperators to manage objects in compartment DataProd
where all {
  target.bucket.name = 'db-backups-prod',
  any {
    request.permission = 'OBJECT_RESTORE',
    request.permission = 'OBJECT_READ',
    request.permission = 'OBJECT_INSPECT'
  }
}
```

This role is designed to locate objects, request restores, and read data once the object is ready. It does not grant delete or overwrite permissions.

In operational workflows, separate "restore request accepted" from "data is ready to download". Operators performing recovery should also record the target object and purpose to avoid unnecessary restores. Not granting restore permission to every regular reader account gives tighter control over Archive retrieval operations.

## Policy test matrix

Do not test with an Administrators account to conclude a narrow role is correct. Use the actual identity of each role and ensure it does not simultaneously belong to a broad admin group.

Prepare sample data in a learning environment with known objects:

- `invoices/demo.txt`
- `payroll/demo.txt`
- A new name to be generated under `incoming/`

Expected test matrix for the policies in this lesson:

| Test case | BillingReaders | InvoicePrefixReaders | BillingUploaders |
| --- | --- | --- | --- |
| List objects in billing bucket | Succeeded | Blocked | Blocked |
| Read `invoices/demo.txt` | Succeeded | Succeeded | Blocked |
| Read `payroll/demo.txt` | Succeeded | Blocked | Blocked |
| Create new name under `incoming/` | Blocked | Blocked | Succeeded |
| Overwrite newly created name | Blocked | Blocked | Blocked |
| Delete created object | Blocked | Blocked | Blocked |
| Access unassigned bucket | Blocked | Blocked | Blocked |
| Modify bucket configuration | Blocked | Blocked | Blocked |
| Create PAR | Blocked | Blocked | Blocked |

"Blocked" must be verified against a valid existing target resource. Requests to a non-existent object name do not prove that the policy blocked access to real objects.

### Verification example with PowerShell and OCI CLI

The commands below are a hands-on test; they do not create groups or policies themselves. They assume the CLI is installed, profiles are configured for **separate identities**, the namespace is known, and the sample file exists.

```powershell
$Namespace = 'REPLACE_WITH_NAMESPACE'
$Bucket = 'billing-documents-prod'
$Region = 'ap-singapore-1'
$PayloadPath = './sample-invoice.txt'
$ObjectName = 'incoming/' + [guid]::NewGuid().ToString('N') + '.txt'

# Profile BILLING_READER: expected to list objects.
oci os object list --profile BILLING_READER --region $Region --namespace-name $Namespace --bucket-name $Bucket --limit 10

# Profile INVOICE_PREFIX_READER: expected to download known object.
oci os object get --profile INVOICE_PREFIX_READER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name invoices/demo.txt --file ./invoice-demo.download.txt

# Same profile, outside prefix: expected to be blocked.
oci os object get --profile INVOICE_PREFIX_READER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name payroll/demo.txt --file ./payroll-denied.download.txt

# Profile BILLING_UPLOADER: first upload with new name should succeed.
oci os object put --profile BILLING_UPLOADER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name $ObjectName --file $PayloadPath --no-multipart --force

# Re-run immediately with same ObjectName: expected to block overwrite.
oci os object put --profile BILLING_UPLOADER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name $ObjectName --file $PayloadPath --no-multipart --force

# Test only on the newly created sample object: expected to block delete.
oci os object delete --profile BILLING_UPLOADER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name $ObjectName --force
```

Use a small file to test the single-part PutObject flow independently. Afterward, test with the actual file sizes and SDK used by your production application. The [CLI object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html) documentation explains automatic multipart selection and the `--no-multipart` option.

A profile name only selects an authentication configuration; it is not an IAM role. Two profiles pointing to the same user with admin privileges cannot verify the boundary between reader and uploader.

Record timestamp, principal, operation, resource, outcome, and request ID when testing. For tests that fail as expected, still verify the cause was not a wrong region, wrong namespace, or missing resource. Policy changes may take time to propagate before test results stabilize; see [notes on Object Storage policy propagation](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm).

## Diagnosing unexpected results

| Symptom | Where to check |
| --- | --- |
| Can read object but Console cannot open listing | Separate direct-access permissions from Console discovery permissions |
| Small file upload works but large file fails | Check whether client switches to multipart and calls additional APIs |
| Uploader can modify existing objects | Check `OBJECT_OVERWRITE`, `use` verb, and other groups/policies |
| Prefix reader sees object names outside scope | Check for statements granting `OBJECT_INSPECT` at bucket level |
| Same command works on laptop, blocked on Compute | Check principal, matching rule, and `--auth` method |
| Changing to another bucket still succeeds | Look for broader statements, inherited permissions, or admin groups |
| IAM looks right but customer-managed-key bucket fails | Check Object Storage service permissions on the Vault key |
| Delete permission looks sufficient yet delete is denied | Check retention rules and other data-protection constraints |

Buckets using customer-managed keys introduce an authorization relationship with Vault. Do not grant `manage keys` to an application just to fix an object error: identify the exact service principal and key permissions needed for that workflow. Additional requirements are listed per API in the [Object Storage permission reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

For observability, distinguish administrative changes from object data access; select Audit, Object Storage service logs, and appropriate logging configurations. Collect data useful for troubleshooting without writing API keys or PAR URLs into error reports. See [Object Storage security and logging guide](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm).

## Putting the design into production

Before applying policies to real applications, document each policy along with its rationale and role owner. Every statement should answer: "if this permission is removed, which business operation breaks?"

A deployment change should include:

- List of affected principals and buckets.
- Expected API flow, including multipart or restore if applicable.
- Test results for both allowed operations and operations that must be blocked.
- How to roll back to the previous policy if the application fails.
- Owner responsible for reviewing permissions when workloads or data change.

When automating deployments, use an identity and permissions scoped to that deployment job; do not leave tenancy administrator privileges in pipelines by default. For critical backups or invoices, separating data operators, policy administrators, and key administrators reduces the chance of a single account impacting the entire protection chain.

The core of IAM design for Object Storage is stating precisely **who can do what on which data**, and then verifying it with the right identity and the right API flow. A concise policy is only valuable when its scope matches business requirements and is not undermined by broader permissions elsewhere.