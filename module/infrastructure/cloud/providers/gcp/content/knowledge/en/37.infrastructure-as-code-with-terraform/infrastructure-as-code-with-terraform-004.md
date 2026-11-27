# Terraform State on Cloud Storage and Access Control

Terraform uses **state** to remember the relationship between Infrastructure as Code configurations and real resources on Google Cloud. When multiple engineers or pipelines manage the same infrastructure, state must be stored in a shared location with locking during updates and strictly controlled access. Google Cloud Storage (GCS) provides a remote backend for Terraform: state is stored as objects in a bucket, Terraform supports state locking during write operations, and Cloud Storage provides IAM, encryption, versioning, and audit logs to protect the data.

In the `CLOUD_PROVIDERS_GCP` module, this lesson connects Terraform with organizing projects, IAM, and VPCs, as well as deploying Compute Engine, GKE, Cloud Run, storage, and databases. State is critical governance data for that entire workflow. If state is lost, overwritten, or exposed to unauthorized parties, the team can lose the ability to accurately manage resources or leak sensitive infrastructure details.

## Learning Objectives

After this lesson, learners can:

- Explain the role of Terraform state, remote backends, and state locking.
- Configure the `gcs` backend to store state in Cloud Storage.
- Create a state bucket with Uniform bucket-level access, Public access prevention, and Object Versioning.
- Grant permissions for the Terraform runner using least-privilege IAM and service account impersonation.
- Migrate state from local to GCS, use workspaces, and manage multiple independent states.
- Protect state with encryption, audit logs, and backup/recovery procedures.
- Recognize the risks of sharing `terraform_remote_state`, using workspaces as security boundaries, or storing credentials in backend configuration.

## 1. What Is Terraform State?

### The Role of State

Terraform reads `.tf` configurations, calls the provider to query or modify resources, and saves the known state into the state file. State maps resource addresses in the configuration to the IDs and attributes of real resources. It also stores auxiliary metadata so Terraform can compute changes in the next `plan`.

Example configuration:

```hcl
resource "google_storage_bucket" "app_data" {
  name                        = "example-app-data"
  location                    = "ASIA-SOUTHEAST1"
  uniform_bucket_level_access = true
}
```

In state, Terraform can store the address `google_storage_bucket.app_data`, bucket ID, location, configuration attributes, and metadata returned by the provider. When running `terraform plan`, Terraform compares three sources:

1. **Configuration**: desired state described in Terraform code.
2. **State**: the latest state Terraform recorded and mapped to resources.
3. **Remote infrastructure**: actual resources on Google Cloud queried by the provider.

From these, Terraform determines which resources need to be created, updated, replaced, or destroyed.

### State Is Not a Complete Copy of Infrastructure

State does not replace Cloud Asset Inventory, Cloud Monitoring, or the actual configuration of individual services. It only records resources within the management scope of a configuration and provider. If an engineer creates a VM manually outside Terraform, that resource does not automatically appear in state. To have Terraform manage an existing resource, use `terraform import` or an appropriate `import` block workflow.

State is also not a configuration file to edit directly. Terraform stores state in JSON format, but manually editing JSON can corrupt lineage, serial, or resource mappings. Use `terraform state` commands and supported import/move/remove workflows.

### Why Must State Be Protected?

State and plan files can contain:

- Resource IDs, project names, bucket names, IP addresses, network topology, and workload metadata.
- Values returned by providers, data source results, and configuration attributes.
- Database passwords, tokens, private endpoints, credentials, or secrets if providers store them in state.
- Sensitive variable/output values marked `sensitive` by Terraform.

The `sensitive = true` attribute primarily masks values from certain CLI and UI outputs. Terraform still stores those values in state and plan files if resource attributes require storing them. Therefore, anyone with permission to read state can extract sensitive values stored inside it. State and all copies of state must be treated as confidential data.

Do not commit state, plan files, or backend cache directories to Git. A basic `.gitignore` might include:

```gitignore
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
```

Keep `.terraform.lock.hcl` in Git so the team uses the same pinned provider versions. If generating plan artifacts in CI, store them in an artifact store with appropriate IAM and retention limits; never attach plans to public issues or chats.

## 2. Remote Backends and the GCS Backend

### What Does a Backend Do?

A backend determines where Terraform stores state and the coordination mechanism across runs. The default local backend stores `terraform.tfstate` on the machine running Terraform. When multiple people work on the same system, local state easily becomes out of sync, lost if a machine fails, or overwritten if multiple people operate concurrently.

A remote backend stores state in a shared system. Team members and pipelines can work against the same latest state without emailing files or committing them to Git. Backends that support locking lock the state during write-capable operations, preventing two processes from updating the same state simultaneously.

### The GCS Backend

The Terraform `gcs` backend stores state as objects in an existing Google Cloud Storage bucket. The backend supports state locking and multiple workspaces. The bucket must be created before configuring the backend; you cannot use the very configuration that requires that backend to create the state bucket on the first run.

Example storage layout:

```text
Cloud Storage project: platform-state-prod
└── Bucket: acme-tf-state-prod
    └── Prefix: gcp/network
        ├── default.tfstate
        ├── staging.tfstate
        └── production.tfstate
```

With named workspaces, the GCS backend stores state at object paths of the form `<prefix>/<workspace-name>.tfstate`. State for the `default` workspace also resides under the backend prefix. Use distinct prefixes for each root module or stack to avoid independent configurations writing to the same state.

### Benefits and Limitations

| Capability | Benefit | Operational Consideration |
|---|---|---|
| Storing objects in GCS | Shared, durable storage with IAM integration. | Protect the bucket and state objects as sensitive data. |
| State locking | Prevents concurrent write operations to the same state. | Never disable locking in production; handle stuck locks by procedure. |
| Object Versioning | Retains old versions when a state object is replaced or deleted. | Monitor storage usage and lifecycle of noncurrent versions. |
| IAM | Grants permissions by user, group, or service account. | Bucket-level permissions apply across objects; workspace prefixes do not automatically create IAM boundaries. |
| Cloud KMS CMEK | Allows customer-managed encryption keys for state data. | The GCS service agent needs permission to use the key; never delete a key still needed to decrypt state. |

## 3. Preparing a Cloud Storage Bucket for Terraform State

### Choosing Project and Location

Place the state bucket in a dedicated platform management project, such as `platform-state-prod`, separate from application-hosting projects. This organization allows the platform team to manage bucket lifecycle, IAM, logging, and keys independently of workload development teams.

Choose the location based on data residency requirements, pipeline latency, and operational policy. If state contains sensitive metadata or infrastructure identifiers belonging to a regulated region, the bucket location must comply with that policy. Bucket names are global and may be publicly observable; do not put secrets, customer names, or sensitive data into the bucket name.

### Security Settings to Enable

| Setting | Recommendation | Reason |
|---|---|---|
| Uniform bucket-level access (UBLA) | Enable. | Enforces uniform bucket-level IAM and disables object-level ACLs. |
| Public access prevention (PAP) | Enforced. | Prevents granting public access via `allUsers` or `allAuthenticatedUsers`. |
| Object Versioning | Enable. | Retains previous state versions to support recovery after accidental deletion or overwrite. |
| Encryption at rest | Keep Cloud Storage default encryption or use CMEK if policy requires. | Protects state at rest. |
| Data Access audit logs | Enable according to audit requirements. | Records read/write operations on state objects for investigation. |
| Lifecycle | Configure according to retention and cost policies. | Prevents excessive accumulation of noncurrent object versions. |

UBLA makes IAM the sole access control mechanism for the bucket and objects; individual ACLs are no longer applied. PAP protects the bucket from accidental public access grants. The two mechanisms serve different purposes and should be used together for private state buckets.

### Creating the Bucket with gcloud

The example below creates a state bucket in `asia-southeast1`. Replace `STATE_PROJECT_ID` and `BUCKET_NAME` with actual values. The bucket name must be globally unique.

```bash
gcloud config set project STATE_PROJECT_ID

gcloud services enable storage.googleapis.com

gcloud storage buckets create gs://BUCKET_NAME \
  --project=STATE_PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access \
  --public-access-prevention

# Enable Object Versioning to retain previous state versions.
gcloud storage buckets update gs://BUCKET_NAME --versioning

# Inspect bucket configuration.
gcloud storage buckets describe gs://BUCKET_NAME
```

`asia-southeast1` is only an illustrative location. Do not use this region if your organization's data residency requirements or architecture require a different location.

### Why Is Object Versioning Needed?

Terraform frequently writes new state versions after apply operations. When Object Versioning is enabled, Cloud Storage keeps older generations as noncurrent versions when the current object is replaced or deleted. This enables state recovery in scenarios such as accidental manual operations, automation bugs, or historical investigation.

Object Versioning does not replace state locking. Versioning preserves object history; locking coordinates concurrent Terraform runs. Both address different risks.

Older versions consume storage capacity. Define lifecycle rules to manage noncurrent versions according to policy, but avoid expiring versions too early if the organization needs a recovery or audit window. Combine Object Versioning with soft delete if data protection policies require it and budget permits.

### Avoiding Unsuitable Retention Policies

State buckets need to be continuously updated by Terraform. A retention policy or bucket lock can prevent deleting objects during the retention period, causing state writes or lock cleanup to fail unexpectedly. Only apply time-bound retention policies or lock retention after thoroughly testing GCS backend behavior and establishing a matching state change procedure. Object Versioning is usually a simpler recovery choice for state buckets.

## 4. IAM and Access Control for the State Bucket

### Separating Bucket Administration and Terraform Execution Identities

Separate at least three identity groups:

1. **Bucket administrators**: create buckets, enable versioning, configure UBLA/PAP, IAM, CMEK, and lifecycle. This group holds bucket administrative permissions but does not need to participate in every `terraform apply`.
2. **Terraform runtime identity**: the service account that pipelines or operators impersonate to read, write, and lock state. Grant permissions only on the required state bucket.
3. **State readers / auditors**: individuals who need to inspect state or access history. Read access to state can still expose secrets, so limit the number of grantees.

### Roles for the Terraform Runtime

The HashiCorp GCS backend requires the identity using the backend to have **Storage Object Admin** (`roles/storage.objectAdmin`) on the state bucket. This role allows reading, listing, creating, updating, and deleting objects required for state and locks. If an organization builds a custom role, ensure it includes all object permissions used by the backend and test it on the deployed Terraform version.

Example granting permissions on the exact bucket:

```bash
gcloud storage buckets add-iam-policy-binding gs://BUCKET_NAME \
  --member="serviceAccount:terraform-state-writer@STATE_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

Do not grant `roles/storage.admin` at the project level just so Terraform can read/write state. Storage Admin includes bucket and IAM administrative permissions broader than runtime needs. The bucket administration team can hold broader roles; the service account running Terraform only needs Object Admin on the corresponding state bucket.

IAM changes on a bucket can take a short while to propagate. If the backend returns `403` immediately after granting permissions, verify the exact principal, bucket, and project, and wait for policy propagation before changing other configurations.

### State Read Access Is Sensitive Data Read Access

Anyone with `roles/storage.objectViewer` or equivalent object read permissions can download the state JSON. They can inspect many infrastructure attributes and secret values stored in state by providers. Therefore:

- Do not grant state read permissions to all developers if they only need to view a service's outputs.
- Separate buckets or projects for different security boundaries, especially production and non-production.
- Use administrative groups rather than granting permissions directly to many individual users.
- Review IAM policies periodically and revoke permissions when staff or pipelines are no longer responsible for a stack.
- Enable Data Access audit logs to investigate state read and write activity.

### Workspaces Are Not a Security Boundary

Terraform workspaces create multiple logical states under the same backend. Workspaces are useful for deploying multiple copies of the same configuration, but unsuitable for systems requiring independent credentials and access controls. If a service account has Object Admin on the bucket, it can access objects belonging to other workspaces in that bucket.

For production, staging, and development environments that require different administrators or access permissions, use separate buckets or separate projects with separate IAM. Do not rely on prefixes or workspace names to replace permission isolation.

## 5. Secure Authentication for the GCS Backend

### Application Default Credentials on Developer Machines

When running Terraform from a workstation, you can use Application Default Credentials (ADC):

```bash
gcloud auth application-default login
gcloud config set project STATE_PROJECT_ID
```

The Terraform GCS backend uses ADC if no other credentials are configured. User ADC can expire; when encountering authentication errors, refresh ADC according to your organization's login procedure. Never copy credential files into the repository.

### Service Accounts on Google Cloud

If Terraform runs in a Google Cloud environment, such as a VM or a runner on GKE, prefer attaching an appropriate service account to the workload. Terraform can use that environment's ADC to call Cloud Storage. There is no need to create and store a service account JSON key just for the backend to access the bucket.

### Service Account Impersonation

A common pattern is for engineers or CI runners to authenticate with a short-lived identity and then impersonate a dedicated service account for state. The backend supports `impersonate_service_account`.

Example configuration:

```hcl
terraform {
  backend "gcs" {
    bucket                      = "BUCKET_NAME"
    prefix                      = "gcp/network/prod"
    impersonate_service_account = "terraform-state-writer@STATE_PROJECT_ID.iam.gserviceaccount.com"
  }
}
```

The source identity must have `roles/iam.serviceAccountTokenCreator` on the target service account for impersonation to succeed. The target service account has `roles/storage.objectAdmin` on the state bucket. When using Workload Identity Federation in CI, configure federation so the runner obtains short-lived credentials and can only impersonate the exact required service account.

The backend and provider are two separate authentication configurations. If the backend uses service account impersonation to access state, the Google provider also needs an appropriate identity configured to create or manage resources in the target project. Do not assume the backend identity automatically becomes the provider identity in every configuration.

### Avoiding Credentials in Backend Configuration

Do not hardcode service account JSON keys, access tokens, or sensitive credentials inside `backend "gcs"` or pass them directly via `-backend-config` if those values are secrets. Terraform can write backend configuration into `.terraform` and plan files; credentials placed there may be stored in plaintext.

Prefer ADC, Workload Identity Federation, workload-attached service accounts, or impersonation. If you need to pass separate backend configurations via a file, pass only non-secret values such as bucket, prefix, or service account email, and protect the file according to internal procedures.

## 6. Configuring the Terraform `gcs` Backend

### Minimal Backend Block

Add the following block to the root module:

```hcl
terraform {
  backend "gcs" {
    bucket = "BUCKET_NAME"
    prefix = "gcp/network/prod"
  }
}
```

`bucket` is the previously created bucket name. `prefix` is the logical path inside the bucket to isolate the root module's state. Do not use a leading slash in the prefix, and avoid having multiple independent configurations share the same bucket/prefix/workspace.

The backend block can only be configured with static values. You cannot reference `var.*`, `local.*`, resource outputs, or data sources in a backend block because Terraform must initialize the backend before evaluating the rest of the configuration.

### Backend with CMEK

If the organization requires a Customer-Managed Encryption Key, you can declare `kms_encryption_key` in the GCS backend:

```hcl
terraform {
  backend "gcs" {
    bucket           = "BUCKET_NAME"
    prefix           = "gcp/network/prod"
    kms_encryption_key = "projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/tf-state-ring/cryptoKeys/tf-state-key"
  }
}
```

The Cloud KMS key must be in a location compatible with the bucket per Cloud Storage requirements. The GCS service agent of the project containing the bucket needs `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the CryptoKey. The service agent typically has the format:

```text
service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com
```

This is the Cloud Storage service identity, distinct from the Terraform runtime service account. If using CMEK, ensure the key remains active and is not scheduled for destruction as long as state needs to be read. State encrypted with a deleted key or lost key access may be unrecoverable.

Cloud Storage encrypts data at rest by default and protects API connections with TLS. CMEK adds key control and requires KMS operational management; only enable it when there is an explicit governance or compliance requirement.

### Initializing the Backend

Once the bucket and IAM are ready:

```bash
terraform init
```

Terraform downloads required providers/modules, initializes the backend, and creates the local `.terraform` directory containing backend metadata. If the directory was previously initialized with a local backend and contains state, Terraform may prompt whether to migrate state to GCS.

When intentionally migrating local state to GCS, use:

```bash
terraform init -migrate-state
```

Read the migration prompt carefully, confirm the bucket/prefix, and verify state has been stored remotely. Do not delete the local state or migration backup until you have verified the remote state works and the recovery process is understood.

After initialization, you can verify the active backend from `terraform init` output and inspect state:

```bash
terraform workspace show
terraform state list
terraform plan
```

## 7. State Locking and Concurrent Operations

### How Does Locking Work?

The GCS backend supports state locking. Terraform automatically acquires a lock before operations that can write state, such as `apply`, `import`, or certain state commands. If another process holds the lock, the new process waits or fails according to the configured timeout. This prevents multiple operators from writing state simultaneously and corrupting resource mappings.

You can set a lock wait timeout when running commands:

```bash
terraform apply -lock-timeout=5m
```

Locking is a coordination mechanism between Terraform processes. It does not prevent someone with Storage Object Admin permissions from deleting or modifying objects directly via the Cloud Storage API, and it does not replace IAM.

### Never Disable Locking in Production

Terraform provides a `-lock=false` option for some commands, but bypassing locks when multiple people or pipelines collaborate can cause state overwrites. Never use this option to bypass lock errors in production.

If a lock remains held after a runner terminates abruptly:

1. Identify which pipeline or user created the lock.
2. Check whether the Terraform process is still running or another job is currently applying.
3. Only when certain the lock is stale and no writer is active, consider `terraform force-unlock LOCK_ID`.
4. Use the exact lock ID displayed by Terraform; record the reason and operator.
5. Run `terraform plan` to inspect state and remote infrastructure before further operations.

`force-unlock` is not a general fix for 403 errors, permission errors, or backend errors. Address the root cause first.

### Object Versioning Is Not Locking

| Mechanism | What It Protects Against | What It Does Not Solve |
|---|---|---|
| State locking | Two Terraform processes writing to the same state concurrently. | An IAM-authorized user deleting or overwriting objects directly. |
| Object Versioning | Losing state versions due to object replacement/deletion. | Two processes running plan/apply concurrently and causing logical conflicts. |
| IAM | Unauthorized identities reading/writing state. | Logical mistakes made by an authorized user. |
| CMEK | Protecting encryption keys and object decryption permissions. | Controlling who can read state; an authorized object reader still receives plaintext if permitted to use the key. |

## 8. Workspaces, Prefixes, and Splitting State

### Creating Workspaces

The GCS backend supports Terraform CLI workspaces. For example:

```bash
terraform workspace new staging
terraform workspace new production

terraform workspace list
terraform workspace select staging
terraform workspace show
```

Each workspace has its own state under the same bucket/prefix. Terraform workspaces allow one configuration to create multiple logical instances, but all still share the same backend configuration and typically share one backend identity.

### When Should Workspaces Be Used?

Workspaces are suitable when:

- Environments share the same infrastructure structure and the same deployment permission set.
- Differences are mainly variable values, sizing, or resource names.
- A single operations team is authorized to manage all workspaces in that scope.

Workspaces are unsuitable when production requires different approvers, different credentials, or separate state read permissions from staging. In that case, create separate root modules or stacks, separate buckets/prefixes, and separate service accounts.

### Splitting State by Responsibility

A common layout:

```text
Bucket: acme-tf-state-prod
├── foundation/network/default.tfstate
├── platform/cluster/default.tfstate
├── application/checkout/default.tfstate
└── data/warehouse/default.tfstate

Bucket: acme-tf-state-nonprod
├── foundation/network/default.tfstate
├── platform/cluster/default.tfstate
└── application/checkout/default.tfstate
```

Split state by component lifecycle and ownership. Network foundation, cluster platform, and applications can have different operating teams, release cadences, and permissions. Each root module should have its own state to reduce blast radius when an apply fails.

If sharing one bucket across multiple stacks, prefixes help organize objects, but bucket-level IAM generally applies to the entire bucket. For true permission isolation, use separate buckets or appropriate Managed Folders/IAM mechanisms and thoroughly verify `storage.objects.list` permissions; do not assume IAM conditions on object names restrict all list operations.

## 9. Managing Sensitive Data and Remote State

### `sensitive` Does Not Remove Data from State

Example:

```hcl
variable "database_password" {
  type      = string
  sensitive = true
}

output "database_connection_secret" {
  value     = var.database_password
  sensitive = true
}
```

Terraform masks the value in certain CLI outputs, but still stores the value if the resource/output requires storing it in state. Anyone who can download the state can still read that value. Do not treat `sensitive = true` as encryption or access control.

Newer Terraform versions provide `ephemeral` values and some provider resources support write-only arguments to avoid writing certain values into state/plan. Only use them when your Terraform version and provider support the exact context; consult provider documentation. The best design remains avoiding putting secrets into resource attributes when services support Secret Manager references or short-lived credentials.

### What Are the Risks of `terraform_remote_state`?

The `terraform_remote_state` data source allows one configuration to read outputs from another configuration's state. For example:

```hcl
data "terraform_remote_state" "network" {
  backend = "gcs"
  config = {
    bucket = "acme-tf-state-prod"
    prefix = "foundation/network"
  }
}

output "application_network_id" {
  value = data.terraform_remote_state.network.outputs.network_id
}
```

Even though the configuration only references the `network_id` output, the backend access permission must read the state object. State may contain many other attributes beyond that output, including sensitive data. Therefore, permission to read remote state is access to the entire state snapshot. If you only need to share a few values, consider publishing them through a separately controlled channel such as Secret Manager, service discovery configuration, or a narrowly scoped internal API.

## 10. Backing Up, Recovering, and Migrating State

### Protecting Against Operational Mistakes

Basic safeguards:

- Enable Object Versioning on the state bucket.
- Configure lifecycle rules for noncurrent versions according to retention requirements.
- Restrict IAM for anyone permitted to delete objects or modify policies.
- Enable Data Access audit logs for Cloud Storage if you need to investigate who read/wrote objects.
- Maintain a tested backup and recovery procedure, rather than relying solely on versioning being enabled.
- Avoid running `terraform state push` or editing state JSON directly without a clear recovery plan.

You can use `terraform state pull` to read the current state snapshot, for example when creating a controlled backup:

```bash
terraform state pull > state-backup.json
```

The `state-backup.json` file contains full state data and may include secrets. Store the file in an encrypted location, restrict read permissions, and securely delete it once the backup purpose is complete. Do not let this command write state contents into pipeline logs.

### Recovering State from an Older Object Version

If the current state is accidentally overwritten or deleted:

1. Pause pipelines and instruct operators not to run `plan/apply` on the affected stack.
2. Identify the exact bucket, prefix, workspace, and object path.
3. List object generations/versions and identify the last version before the incident.
4. Create a separate backup of the current state so you can revert if you select the wrong generation.
5. Restore the selected version to the object path used by the backend following Cloud Storage procedures.
6. Verify state lineage, serial, and resource list, and compare against real resources.
7. Run `terraform plan` to assess drift before allowing applies.

Do not hastily restore an older state if a successful apply occurred after that version's timestamp. An older state may omit newly created resources or have a lower serial; applying immediately could cause duplicate creation or resource destruction.

### Migrating Backends

When moving state from local to GCS or from an old bucket to a new bucket:

1. Pause pipelines and users operating on the stack.
2. Back up the current state and verify the backup is readable.
3. Update the backend block to the new bucket/prefix.
4. Run `terraform init -migrate-state` so Terraform transfers the state.
5. Verify the workspace, resource list, and outputs have not changed unexpectedly.
6. Run `terraform plan` and confirm no unexpected mass creation/deletion plan appears.
7. Only after verification, revoke permissions on the old backend or apply archival procedures to the old backend.

If changing or removing a customer-supplied encryption key (CSEK), migration may require manual object rewrite operations because Cloud Storage does not retain the key to decrypt automatically. With CMEK, Cloud Storage retains key metadata and can support backend migration, but keep the old key until the state object has been rewritten with the new key. Never delete a KMS key currently used to encrypt state.

## 11. Auditing and Monitoring the State Bucket

### Cloud Audit Logs

Cloud Storage supports Cloud Audit Logs to record administrative and data access activity. Admin Activity logs help track bucket/IAM changes. Data Access logs can record read, write, or list operations on state objects; enable them per organization/project logging policy and keep log costs in mind.

Events to monitor:

- Changes to the state bucket's IAM policy.
- Changes to UBLA, PAP, versioning, retention, or encryption configuration.
- Creation, reading, writing, and deletion of state objects.
- Unusual access activity from principals outside Terraform pipelines.
- Modification or deletion of the CryptoKey if the bucket uses CMEK.

### Querying Cloud Storage Logs

In Logs Explorer, filter Cloud Storage audit logs by service name:

```text
protoPayload.serviceName="storage.googleapis.com"
```

Then narrow by bucket resource, principal email, or method name to investigate. Method names may vary by JSON API and operation called; inspect `protoPayload.methodName`, `resourceName`, and `authenticationInfo.principalEmail` in actual logs.

### Operational Alerts

Build alerts or SIEM rules for:

- Bucket IAM policy changes outside change windows.
- State bucket deletion or disabling of PAP/UBLA/versioning.
- Unusual deletion of state objects or state reads by an unfamiliar principal.
- Repeated Terraform backend 403, 412, or lock timeout errors.
- KMS key disabled, scheduled for destruction, or losing access permissions.

When enabling Data Access logs, evaluate ingestion volume and log retention. Audit logs aid access investigation but do not replace restricting IAM upfront.

## 12. Sample Deployment Workflow for a Network Stack

Suppose the platform team manages VPCs and subnets with Terraform. State for the network stack is stored in a dedicated bucket `acme-tf-state-prod` in project `platform-state-prod`.

### Step 1: Create the State Bucket

```bash
gcloud config set project platform-state-prod

gcloud storage buckets create gs://acme-tf-state-prod \
  --project=platform-state-prod \
  --location=asia-southeast1 \
  --uniform-bucket-level-access \
  --public-access-prevention

gcloud storage buckets update gs://acme-tf-state-prod --versioning
```

### Step 2: Create the Runtime Service Account and Grant Permissions

```bash
gcloud iam service-accounts create terraform-state-writer \
  --project=platform-state-prod \
  --display-name="Terraform state writer"

gcloud storage buckets add-iam-policy-binding gs://acme-tf-state-prod \
  --member="serviceAccount:terraform-state-writer@platform-state-prod.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

User identities or CI runners need permission to impersonate this service account according to organizational IAM policy. The runtime service account does not need bucket administration permissions or Owner on the project.

### Step 3: Configure the Backend

```hcl
terraform {
  backend "gcs" {
    bucket                      = "acme-tf-state-prod"
    prefix                      = "foundation/network"
    impersonate_service_account = "terraform-state-writer@platform-state-prod.iam.gserviceaccount.com"
  }
}
```

### Step 4: Initialize and Verify

```bash
terraform init
terraform workspace show
terraform plan
```

If the stack previously used local state, add `-migrate-state` to `terraform init` following the migration procedure. Verify the bucket contains the state object after the first write and that unauthorized users cannot read the object.

### Step 5: Run a Controlled Pipeline

The pipeline should authenticate via Workload Identity Federation or an organization-approved short-lived credential mechanism. Before `terraform apply`, the pipeline runs `terraform plan`, stores the plan artifact in a properly protected area, and requires environment-based approval. During apply, Terraform automatically uses state locking. The pipeline must stop if it cannot acquire the lock or if the backend returns an error; never automatically break locks to proceed.

### Step 6: Post-Deployment Security Checks

- Confirm UBLA and PAP remain enabled.
- Confirm Object Versioning is active.
- Check IAM includes only approved admin groups and runtime identities.
- Verify audit logs can query object activity as required.
- Confirm the state prefix is not shared with another stack.
- Test the state recovery procedure in a test environment.

## 13. Common Errors and Troubleshooting

| Symptom | Possible Cause | Troubleshooting Direction |
|---|---|---|
| `terraform init` reports bucket does not exist | Bucket has not been created, wrong project, or wrong bucket name. | Run `gcloud storage buckets describe` and check `bucket` in the backend. |
| HTTP 403 when reading/writing state | Principal lacks object permissions, wrong service account impersonation, or IAM not yet propagated. | Check bucket IAM, actual principal, `roles/storage.objectAdmin`, and token creator. |
| `terraform init` prompts to migrate | Working directory previously used a different backend or local state already exists. | Confirm the right bucket/prefix, then use `-migrate-state` if migrating state. |
| Lock timeout | Another pipeline is running or an old lock was not released. | Check running jobs; only force-unlock when certain the lock is stale. |
| Backend cannot read CMEK object | GCS service agent lacks KMS permissions, key is disabled, or incompatible location. | Check CryptoKey IAM, key status, location, and KMS audit logs. |
| State exposed in plan artifact | Plan file or `.terraform` contains backend config/sensitive values. | Restrict artifact access, do not commit files, rotate exposed credentials, and review logs. |
| Workspace using wrong state | Wrong workspace or prefix across root modules. | Run `terraform workspace show`, check backend block and object path. |
| Apply wants to recreate many resources | Wrong state, wrong workspace, different provider/project, or drifted resources. | Stop apply, check state list, project, lineage, and remote resources before acting. |

When the backend encounters an unrecoverable state write error, Terraform may save the new state locally to prevent data loss. Inspect command output and locate the local state recovery file per Terraform guidance; do not continue applying until remote state is synchronized and verified.

## 14. Checklist for Securing Terraform State on GCS

- [ ] State bucket is created before Terraform initializes the backend.
- [ ] Bucket resides in a platform management project and a location meeting data residency requirements.
- [ ] UBLA is enabled, PAP is enforced, and the bucket has no public principals.
- [ ] Object Versioning is enabled and noncurrent version lifecycle matches policy.
- [ ] No untested retention policy/lock blocks state writes.
- [ ] Terraform runtime uses a dedicated service account with only `roles/storage.objectAdmin` on the required bucket.
- [ ] Users permitted to impersonate the service account are narrowly scoped.
- [ ] CI uses short-lived credentials/WIF; no service account JSON keys are stored in the repository.
- [ ] Backend config contains no secrets or tokens that could be written to `.terraform`/plan files.
- [ ] Backend prefixes isolate root modules and stacks.
- [ ] Production and non-production have separate buckets/projects/IAM where security boundaries are needed.
- [ ] State and plan files are treated as sensitive data; never committed to Git or shared over unprotected channels.
- [ ] If using CMEK, the GCS service agent has Encrypter/Decrypter permissions and the key has a clear lifecycle plan.
- [ ] State locking remains enabled by default; `force-unlock` is reserved only for verified stale locks.
- [ ] Audit logs and alerts for IAM/object changes are configured as required.
- [ ] Recovery from older object versions and backend migration have been rehearsed.

## 15. Conclusion

Terraform state is the core data linking configurations to Google Cloud resources. The GCS backend provides remote storage, supports locking, and integrates IAM, Object Versioning, and Cloud KMS. A secure design starts with a pre-bootstrapped dedicated bucket, UBLA/PAP/versioning enabled, Object Admin granted on that exact bucket for the runtime identity, and short-lived authentication or service account impersonation.

State contains infrastructure information and can contain secrets. Therefore, state read permissions must be controlled like access to sensitive data. Workspaces only separate logical states; buckets, projects, and IAM are the components needed to establish access boundaries. Combining locking, versioning, audit logs, backup/restore procedures, and stack isolation enables teams to deploy Terraform across Compute Engine, GKE, Cloud Run, storage, and databases safely, collaboratively, and recoverably when incidents occur.

## References

- [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Terraform state](https://developer.hashicorp.com/terraform/language/state)
- [Terraform state locking](https://developer.hashicorp.com/terraform/language/state/locking)
- [Terraform remote state](https://developer.hashicorp.com/terraform/language/state/remote)
- [Terraform workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces)
- [Manage sensitive data in Terraform](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
- [Terraform backend configuration](https://developer.hashicorp.com/terraform/language/backend)
- [Cloud Storage uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Use uniform bucket-level access](https://docs.cloud.google.com/storage/docs/using-uniform-bucket-level-access)
- [Cloud Storage public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [Cloud Storage Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage IAM](https://docs.cloud.google.com/storage/docs/access-control/iam)
- [Cloud Storage customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Cloud Storage audit logging](https://docs.cloud.google.com/storage/docs/audit-logging)
- [gcloud storage buckets create](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/create)
- [gcloud storage buckets update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/update)
