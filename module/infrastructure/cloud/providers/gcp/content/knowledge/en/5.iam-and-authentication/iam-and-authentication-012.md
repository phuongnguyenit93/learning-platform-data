# Controlling and replacing service account keys

In Google Cloud, an application running on Compute Engine, GKE, Cloud Run, or a CI/CD system may need to call Cloud Storage, Pub/Sub, Cloud SQL, or management APIs. The application must prove its **identity**, while IAM decides whether that identity has permission to perform the action. One widely used approach in the past was downloading a **JSON service account key** onto a machine and supplying it to the application. While convenient, this creates a long-lived secret that, if leaked, can be used outside the organization's controlled environment.

This lesson belongs to the **IAM and authentication** chapter of the `CLOUD_PROVIDERS_GCP` module. While learning project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases, learners need to know when a workload must use an identity, how to protect resources, deploy automatically in a safe way, and manage reliability and cost risks. The focus of this lesson is **restricting new key creation, inventorying and handling existing keys, and migrating applications to keyless authentication methods**.

## Learning objectives

After this lesson, you can:

1. Distinguish **service account**, **service account key**, and **access token**; understand why a key does not embed IAM roles.
2. Identify risks when private keys reside in repositories, container images, developer laptops, or CI/CD secrets.
3. Inventory user-managed keys, read their status, and identify workloads depending on each key.
4. Design key replacements using **attached service accounts**, **Application Default Credentials (ADC)**, **Workload Identity Federation (WIF)**, or **service account impersonation**.
5. Understand how Organization Policy restricts creating and uploading new keys.
6. Execute a verified migration plan: configure the new identity, test permissions, switch workloads, disable the old key, monitor, and only then delete it.
7. Handle key exposure incidents without confusing disabling a key with revoking all already-issued tokens.

## 1. How do service accounts, keys, and tokens differ?

A **service account** is an identity for workloads, automation, or applications. It is created inside a Google Cloud project and has an email identifier such as:

~~~text
orders-api@atlas-commerce-dev.iam.gserviceaccount.com
~~~

The email above is only an example. You can grant a service account the roles needed on a project, bucket, topic, or appropriate resource. For instance, an object-reading service can be granted `roles/storage.objectViewer` scoped to the target bucket.

A **service account key** is a cryptographic key pair allowing an application to prove it is authorized to represent the service account. With a **user-managed key**, an authorized admin/application can create or upload a key pair via supported mechanisms; the **private key** portion must be carefully guarded. Google Cloud normally stores only the public key of a user-managed key and cannot let you re-download a previously created private key.

An **access token** is a time-bound credential used in API calls. An app can use a private key to sign proof and request tokens representing the service account, or obtain tokens through mechanisms requiring no private key downloaded to the app.

~~~mermaid
flowchart LR
    A["Service account<br/>Workload identity"] --> B["IAM role/binding<br/>Effective permissions"]
    C["User-managed private key<br/>Long-lived secret"] --> D["Proves authority to act as SA"]
    E["Attached identity / Federation / Impersonation"] --> D
    D --> F["Short-lived access token"]
    F --> G["Google Cloud API call"]
    B --> G
~~~

> **Distinction:** A key does not “carry” IAM roles. If a service account is suddenly granted extra permissions, anyone holding an old private key gains broader access through that identity. Conversely, removing IAM roles reduces the identity's permissions without invalidating the key itself.

### 1.1. Google-managed keys vs. user-managed keys

| Type | Who manages the private key? | What to do |
| --- | --- | --- |
| **Google-managed key** | Google manages internal key lifecycle for compatible auth mechanisms | Applications typically do not need to download, rotate, or store private keys |
| **User-managed key** | Creator/operator is responsible for safeguarding the private key and key lifecycle | Restrict usage; inventory, revoke unneeded access, disable/delete keys |
| **Short-lived credentials via impersonation/WIF/runtime** | Auth infrastructure issues time-bound tokens from a trusted identity | Manage trust, IAM, token lifetimes, and audits instead of long-lived JSON private keys |

Do not confuse **service account keys** with **API keys** (identifiers for certain projects/apps calling APIs), Compute Engine SSH keys, Cloud KMS encryption keys, or user passwords. These credential types serve different purposes and follow different protection models.

## 2. Why are user-managed service account keys a major risk?

A user-managed JSON key typically contains fields such as `client_email`, `private_key_id`, and `private_key`. **No developer password is needed**: anyone who obtains a valid private key and can reach the relevant APIs can authenticate as that service account.

~~~mermaid
flowchart TD
    A["Private key copied"] --> B["Unauthorized party holds secret"]
    B --> C["Generates auth assertion / requests token"]
    C --> D["Calls APIs as service account"]
    D --> E{"Effective IAM permissions?"}
    E -->|Yes| F["Reads/modifies/deletes resources within granted scope"]
    E -->|No| G["API denies per IAM/policies"]
~~~

Typical risks:

- **Credential leaks:** JSON files committed to Git, printed in CI logs, saved on shared drives, sent via email/chat, or baked into Docker images.
- **Long-lived credentials:** keys can continue working after an employee leaves or a pipeline is retired if left unaddressed.
- **Hard attribution:** logs may identify the service account or key footprint, yet not necessarily identify *which human* held and used the private key.
- **Privilege escalation:** anyone able to create keys for a privileged service account can access resources under that identity, even if their direct permissions are narrower.
- **Hard rotation:** a key may be copied across multiple machines/apps without an inventory; rotating it can break unknown running workloads.
- **Malicious auth config risk:** even credential configurations for federation must come from trusted sources; never use config files of unknown origin.

For example, the Commerce team creates a key for `orders-api` to deploy from a laptop. The file `orders-dev-key.json` is accidentally committed to the repository. Even if removed in the next commit, Git history, clones, caches, and backups can still retain the private key. **Deleting the file from the repo is not enough to invalidate the key**; you must remediate the key and assess what permissions may have been abused.

## 3. Principles for choosing authentication mechanisms by environment

Select the identity source based on where the application actually runs, aiming to avoid distributing long-lived private keys.

| Environment | Preferred approach | Deployment notes |
| --- | --- | --- |
| **Cloud Run** | Attach an appropriate **runtime service account** to the service or job | Client libraries use ADC to fetch credentials from the Google Cloud environment |
| **Compute Engine** | Attach a service account to the VM | Requires matching IAM; mind access scopes if restricted scopes are configured |
| **GKE** | **Workload Identity Federation for GKE** | Distinguish Kubernetes ServiceAccount from IAM service account; configure trust/permissions per workload |
| **Developer laptop** | User ADC, or **service account impersonation** when testing with workload permissions | `gcloud auth application-default login`; never copy production keys to laptops |
| **GitHub/GitLab CI/CD, non-GCP Kubernetes, AWS/Azure/on-prem** | **Workload Identity Federation** with an appropriate identity provider | Exchange external platform identity for short-lived credentials per configured trust |
| **Service that must represent another service account** | **Service account impersonation**, IAM Credentials API | Grant impersonation separately, restricting permitted principals |
| **Legacy systems unable to use the options above** | Approved user-managed key exception | Assign owner, store securely, restrict IAM, rotate, and set remediation deadline |

**ADC is a credential lookup mechanism**, not a requirement to have a key file. ADC's typical lookup sequence is: `GOOGLE_APPLICATION_CREDENTIALS` variable, CLI-generated local ADC file in dev environments, then Google Cloud environment credentials (metadata server or matching runtime integration). When client libraries use ADC, source code can remain unchanged even when the credential source changes.

### 3.1. Java example using Cloud Storage without a key

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class ReadMetadata {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ReadMetadata <BUCKET_NAME> <OBJECT_NAME>");
        }

        // Do not specify a JSON private key path.
        // Google Cloud Java client library discovers ADC automatically.
        Storage storage = StorageOptions.getDefaultInstance().getService();
        Blob object = storage.get(BlobId.of(args[0], args[1]));

        if (object == null) {
            System.out.println("Object not found.");
            return;
        }
        System.out.println("Name: " + object.getName());
        System.out.println("Size: " + object.getSize());
    }
}
~~~

The program requires a project-compatible `com.google.cloud:google-cloud-storage` dependency. On Cloud Run, the runtime service account can be granted `roles/storage.objectViewer` on the exact bucket. On a laptop, developers use local ADC or impersonation. If you hit `403 PERMISSION_DENIED`, inspect the actual identity and IAM instead of creating a new private key as a “permission fix”.

## 4. Cloud Run and Compute Engine: using attached service accounts

When an application runs inside a Google Cloud service supporting attached service accounts, let the runtime request credentials from Google Cloud infrastructure. Application libraries invoke ADC and receive time-bound access tokens without distributing JSON files.

~~~mermaid
sequenceDiagram
    participant App as Cloud Run app
    participant ADC as Google Auth Library (ADC)
    participant Meta as Runtime/Metadata Server
    participant API as Cloud Storage API
    App->>ADC: Create client and call API
    ADC->>Meta: Request short-lived credential
    Meta-->>ADC: Access token of runtime identity
    ADC->>API: Request carrying token
    API-->>ADC: Response per IAM/policies
~~~

### 4.1. Choosing a least-privileged service account

For example, `orders-api` only needs to read data from bucket `atlas-orders-dev`. You should:

1. Pick a dedicated service account for the app, e.g., `orders-reader@atlas-commerce-dev.iam.gserviceaccount.com`.
2. Grant needed permissions on the bucket; avoid `roles/editor` or `roles/owner` across the entire project just to read objects.
3. Configure the Cloud Run service to use that identity.
4. Deploy the app using ADC; test live requests.
5. Monitor `401`/`403` errors and relevant Cloud Audit Logs.

On Compute Engine, also inspect VM **access scopes** if configured; sufficient IAM combined with overly narrow scopes can still block API calls. A service account attached to a VM can also be used by multiple processes on that VM depending on internal boundaries; do not treat it as a per-process identity.

### 4.2. Pitfall when migrating away from keys

A workload might still set:

~~~bash
export GOOGLE_APPLICATION_CREDENTIALS="/secrets/orders-service-account-key.json"
~~~

If you attach a service account to Cloud Run or a VM yet **leave that environment variable pointing to the key**, ADC continues preferring the key file. After confirming the attached identity is valid, remove that path and key mount from runtime config so the client library actually uses the new credential source.

Never “test” by printing access tokens or private keys to logs.

## 5. GKE: Workload Identity Federation for GKE

GKE has two service account types that are easily confused:

- **Kubernetes ServiceAccount (KSA)** is a workload identity inside Kubernetes.
- **IAM service account** is an identity resource in Google Cloud.

**Workload Identity Federation for GKE** lets pods call Google Cloud APIs without placing JSON private keys in Kubernetes Secrets. Depending on configuration and target APIs, IAM can grant permissions directly to the Kubernetes workload principal or the workload can impersonate an authorized IAM service account.

~~~mermaid
flowchart LR
    P["Running application Pod"] --> K["Kubernetes ServiceAccount"]
    K --> M["GKE metadata server / Federation"]
    M --> T["Short-lived credential"]
    T --> A["Cloud Storage / Pub/Sub / API"]
    I["IAM bindings by principal"] --> A
~~~

Deployment steps include:

1. Verify GKE mode and Workload Identity Federation are enabled/configured on the cluster and node pools as required.
2. Create a dedicated KSA for the app, avoiding the default identity shared by all pods when different permissions are needed.
3. Set up IAM bindings at the appropriate resource scope for the workload principal or impersonation setup.
4. Run pods using that KSA, removing any prior user-managed key mounts.
5. Test live calls and inspect errors/authentication on the workload.

**Enabling federation does not automatically grant IAM permissions.** Without proper bindings, acquiring a workload identity still results in `403`. Follow guidance matching your cluster's GKE version/mode for enabling and mapping.

## 6. Applications outside Google Cloud: Workload Identity Federation

A CI/CD pipeline on GitHub or GitLab, or a workload running on AWS, Azure, or in a data center, already has **an identity from its current platform**. Rather than generating a Google Cloud JSON key and storing it in CI secrets, you can create a **Workload Identity Pool**, configure an **Identity Provider**, and enforce trust conditions for that external identity source.

A simplified model:

~~~mermaid
sequenceDiagram
    participant CI as CI/CD Pipeline
    participant IdP as External Identity Provider
    participant STS as Google Cloud STS
    participant IAM as IAM / Service Account
    participant API as Google Cloud API
    CI->>IdP: Obtain workload identity token
    IdP-->>CI: Matching OIDC/SAML assertion
    CI->>STS: Exchange token via federation
    STS-->>CI: Short-lived federated token
    CI->>IAM: Use direct permissions or impersonation (if configured)
    IAM-->>CI: Appropriate credential
    CI->>API: Access resources per IAM
~~~

**Two common authorization options:**

- **Direct resource access:** grant IAM roles directly to the federated principal if supported by the target API/resource.
- **Service account impersonation:** grant the federated principal permission to impersonate a service account, then use that service account's IAM permissions to access APIs.

Federation is not automatically safe if trust is configured too broadly. For instance, instead of trusting every pipeline from a CI provider, constrain **repository, branch/environment, issuer, audience, attributes**, and supported restrictions. Accepted external identities must come from a trusted system, not arbitrary forgeable user fields.

A WIF **credential configuration file** can be read by ADC via `GOOGLE_APPLICATION_CREDENTIALS`; it is a configuration telling ADC how to fetch short-lived tokens from an external identity source, distinct from a JSON service account private key. Even so, credential configurations must come from trusted sources because a malicious config can redirect credential retrieval.

### 6.1. When to choose federation?

- The external system already has a supported IdP able to issue OIDC/SAML tokens or another Google Cloud-supported format.
- CI/CD deploys frequently and you want to eliminate long-lived keys.
- Administrators need strict constraints on which workload sources can reach a project.
- The enterprise prioritizes short-lived auth sessions, auditability, and centralized revocation.

You need permissions to create pools/providers, IAM permissions, token exchange settings, and deployment docs for your specific CI provider. Never create a WIF provider with broad trust merely to get a pipeline “working”.

## 7. Developer laptops and service account impersonation

In development environments, users typically establish ADC via:

~~~bash
gcloud auth application-default login
~~~

When testing with a service account's permissions rather than personal permissions, you can use service account impersonation with compatible SDKs:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=orders-reader@atlas-commerce-dev.iam.gserviceaccount.com
~~~

This is an example; the developer account must hold permission to impersonate the service account, typically via `roles/iam.serviceAccountTokenCreator` granted at an appropriate scope. The IAM Credentials API and related conditions must be configured. The target service account **must still hold** permissions on target resources: being able to mint tokens does not grant access to every bucket.

If you only want to run CLI commands as a service account, you can pass impersonation to `gcloud` commands:

~~~bash
gcloud storage ls \
  --impersonate-service-account=orders-reader@atlas-commerce-dev.iam.gserviceaccount.com
~~~

This command does not switch every local application's ADC configuration to impersonation. **CLI credentials and ADC credentials can differ.** Check the file path/environment variables used by your libraries rather than assuming from CLI output.

## 8. Inventorying existing service account keys

Before deleting a key, determine which service account owns it, which project it lives in, whether it is active or disabled, and which workloads may depend on it. Inventorying also helps prioritize service accounts with overly broad roles or aged keys.

### 8.1. Inspecting service accounts and user-managed keys with gcloud

The following commands are **read-only**. Run with an account holding required IAM permissions; replace all example values with real projects/emails.

~~~bash
# Check active CLI account and selected project
gcloud auth list
gcloud config get-value project

# List service accounts in a project
gcloud iam service-accounts list --project=atlas-commerce-dev

# List user-managed keys for a specific service account
gcloud iam service-accounts keys list \
  --iam-account=orders-reader@atlas-commerce-dev.iam.gserviceaccount.com \
  --managed-by=user \
  --project=atlas-commerce-dev
~~~

Output typically includes key IDs and metadata such as creation time, expiration, or disabled status when returned. `--managed-by=user` focuses on **user-managed keys**; default listings may also include Google-managed keys. Never delete Google-managed keys as if they were app-issued private keys.

**Note:** key metadata does not reveal how many places a JSON file has been copied to. You cannot claim a key is unused merely because it does not appear in one repository. Combine owner interviews, pipelines, secret stores, images, host machines, and key-usage telemetry where available.

### 8.2. Building an operational inventory table

| Field | Illustrative sample | Purpose |
| --- | --- | --- |
| Project / service account | `atlas-commerce-dev / orders-reader@...` | Identify identity and scope |
| Key ID | ID from metadata, **not the private key** | Identify the exact key to act on |
| Status | Enabled / Disabled | Know whether the key can authenticate |
| Created / expiration | From actual metadata | Classify aged or soon-to-expire keys |
| Dependent workloads | Legacy batch job, CI pipeline | Avoid breaking systems during migration |
| IAM privilege | Bucket read vs. broader roles | Prioritize high-risk keys |
| Owner / replacement plan | Commerce team / WIF | Who is accountable for migration |
| Target completion date | Per internal schedule | Prevent indefinite key persistence |

Changing IAM and key states is sensitive work. Only authorized personnel should perform it.

## 9. Controlling key creation and upload with Organization Policy

Google Cloud provides **Organization Policy constraints** to curb issuance of long-lived credentials:

- `iam.managed.disableServiceAccountKeyCreation`: managed constraint blocking creation of new user-managed service account keys when enforced.
- `iam.managed.disableServiceAccountKeyUpload`: managed constraint blocking uploading external public keys to service accounts.
- Corresponding legacy constraints: `iam.disableServiceAccountKeyCreation` and `iam.disableServiceAccountKeyUpload`, which may appear in existing configs.

According to Google Cloud documentation, organizations created on or after **May 3, 2024** have the legacy key creation/upload restrictions enabled by default. On older organizations or customized environments, inspect the actual **effective organization policy** rather than assuming all projects are locked identically.

### 9.1. Why block both creation and upload?

Preventing the platform from generating new JSON private keys is insufficient if an authorized user can **generate a key pair externally and upload the public key** so Google accepts the private key they keep. Both constraints close those two paths to creating long-lived credentials.

### 9.2. Policy scope and exceptions

Organization Policies can be configured at the organization, folder, or project level per each constraint's mechanics. Administrators should:

1. Assess current key inventory and workloads needing migration.
2. Enforce policies at the appropriate level to protect future projects.
3. Verify inheritance and active policies on parent/child nodes.
4. If legacy systems cannot migrate immediately, design **narrow, time-bound exceptions with an accountable owner** as supported by the policy mechanism.
5. Periodically audit projects still carrying exceptions.

**Blocking new key creation does not disable existing keys.** Existing keys must be inventoried and remediated through the migration process. Organization Policy also does not replace IAM: rights to administer policies, create keys, or assign roles must be scoped by responsibility.

### 9.3. Never use overly broad roles as shortcuts

`roles/editor` or `roles/owner` can grant many permissions beyond application needs. Separate:

- Workload runtime/operational rights (deploying Cloud Run, running GKE, reading buckets).
- Service account management and IAM granting rights.
- Service account key creation/deletion rights.
- Service account impersonation rights for minting short-lived tokens.

A developer allowed to deploy an application **does not inherently need** permission to create service account private keys. Restricting this permission lowers privilege escalation and secret leak risks.

## 10. Workflow to migrate a workload off a service account key

Suppose a GitHub Actions workflow deploys an app to Cloud Run using a secret holding the JSON key for service account `deploy-bot`. The goal is migrating to WIF and then deleting the old key without disrupting the pipeline.

~~~mermaid
flowchart TD
    A["Inventory key, IAM roles, and usage sites"] --> B["Choose replacement: WIF / attached identity / impersonation"]
    B --> C["Configure trust, IAM, and new credentials"]
    C --> D["Test in a controlled environment"]
    D --> E{"Deploy and least privilege verified?"}
    E -->|No| C
    E -->|Yes| F["Switch workload to new identity"]
    F --> G["Monitor runs and audit logs"]
    G --> H["Disable old key"]
    H --> I{"Any valid workload impacted?"}
    I -->|Yes| J["Controlled restore, fix dependent config"]
    J --> F
    I -->|No| K["Delete old key, update inventory, close change"]
~~~

### Step 1: Identify dependencies and permission scope

- Key ID, service account, project, owner, and deployment locations.
- Permissions the service account genuinely requires; strip overly broad roles before or during migration per plan.
- Every application/pipeline sharing the key; if unknown, investigate before disabling.
- Organization/folder/project policies that could affect WIF or impersonation.
- Test plan, change window, and sign-off owner.

### Step 2: Prepare the replacement mechanism

For GitHub Actions, configure an identity provider with trust locked to the exact repository and workflow/environment; grant impersonation or direct IAM to the authenticated identity. Replace the JSON secret with the supported federated credential step. The deployment identity's permissions must suffice for the exact target service/resources without granting project-wide admin rights.

For Cloud Run, Compute Engine, or GKE, apply the matching native/federated identity mechanism. During cutover, remove `GOOGLE_APPLICATION_CREDENTIALS` if it still points to the old private key file.

### Step 3: Test before cutting off the old key

- Run the pipeline or workload in dev/staging.
- Execute API calls representative of real business operations.
- Verify least privilege, token issuance timing, error codes, and credential refresh.
- Inspect logs and traces/audits without logging tokens or private keys.
- Ensure scheduled jobs, retries, and rollbacks also use the new mechanism.

### Step 4: Disable the old key before deleting it

**Disabling a key** stops it from authenticating to Google APIs. This is a **reversible** step during verification, unlike permanent deletion.

~~~bash
# Run only after workloads have migrated and with authorized permissions.
gcloud iam service-accounts keys disable KEY_ID \
  --iam-account=deploy-bot@atlas-commerce-dev.iam.gserviceaccount.com \
  --project=atlas-commerce-dev
~~~

After disabling, monitor across full operational cycles, especially infrequent scheduled jobs or incident-only workflows. If an unmigrated legitimate dependency surfaces, investigate and remediate before proceeding.

### Step 5: Delete the key once zero dependencies are confirmed

~~~bash
# Deletion is permanent: confirm exact KEY_ID and owner before running.
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=deploy-bot@atlas-commerce-dev.iam.gserviceaccount.com \
  --project=atlas-commerce-dev
~~~

A deleted key **cannot be recovered**. Re-inventory and purge local copies, CI secrets, backup files, or stale configs, keeping in mind deleting copies does not substitute for disabling/deleting the key in Google Cloud.

### Step 6: Complete governance controls

Update documentation and owners, audit IAM, confirm no jobs remain on private keys, enforce key-restriction policies, and monitor auth errors post-cutover. For production workloads, never treat a single successful run as proof all dependencies have migrated.

## 11. When keys cannot be removed immediately: safe exception management

Some legacy systems do not support ADC, WIF, token exchange, or impersonation. Once you verify **no viable keyless option exists**, a user-managed key may be needed temporarily during transition. Treat this as an approved exception.

Minimum checklist:

1. **Clear exception justification:** which system, which environment, why keyless auth cannot work.
2. **Owner and sunset date:** accountable team, review date, target replacement timeline.
3. **Minimal IAM permissions:** restrict resources and actions; never assign broad roles for convenience.
4. **Secure storage:** keep keys out of source code, Git history, build artifacts, and images. Control read access, audit access, and harden storage.
5. **Avoid human distribution:** never send private keys via email/chat or copy manually between laptops.
6. **Tested rotation:** issue replacement key via approved process, roll out to all workloads, test, disable old key, monitor, then delete.
7. **Leak detection:** monitor security findings, audit logs, and key-usage telemetry; maintain an incident response runbook.
8. **Restrictive creation policy:** keep exceptions narrowly scoped; never relax policies org-wide for a single app.

### Why “putting the key in Secret Manager” does not solve the root problem

Secret Manager manages application secrets, yet to read Secret Manager an app **already needs an authentication mechanism**. If the runtime has a valid identity to read Secret Manager, in many cases it can use that very identity directly to call Google Cloud APIs without needing a key at all. Thus, never default to “store service account key in Secret Manager” as a preferred replacement for attached identities or federation.

### Rotation does not equal eliminating risk

Swapping key A for key B while continuing to copy B into repositories or many hosts leaves the risk intact. Rotation only narrows exposure windows; the long-term goal is reducing or eliminating user-managed keys.

## 12. How to respond if a private key is exposed?

Suppose an alert flags the `orders-reader` key inside a public repository. This is a **credential incident**, not a minor config bug.

### 12.1. Immediate actions

1. Identify the exact **key ID**, service account, project, and permission scope. Never paste the private key into ticketing systems or chat.
2. Follow incident response procedures to **disable or delete the exposed key** to halt further use; for confirmed leaks, prioritize shrinking the abuse window over normal migration timelines.
3. Inspect the service account's IAM and all resources it could have reached; trim risky permissions where appropriate.
4. Investigate Cloud Audit Logs, key creation/deletion events, API calls, IAM edits, data access, and anomalous signals within log coverage.
5. Migrate legitimate workloads to keyless identities; if impossible immediately, issue replacement credentials under a tracked incident process and monitor closely.
6. Purge copies from repositories, artifacts, images, and hosts; assess Git history and caches.
7. Document timeline, impact, actions taken, verification, and preventive controls.

**Critical limitation:** Disabling/deleting a key blocks using that key for new authentication, yet **does not immediately revoke short-lived credentials already minted from that key**. When already-issued tokens must be halted, Google Cloud guidance notes considering disabling/deleting the **service account** itself; because that halts all legitimate workloads using the service account, coordinate with owners and assess blast radius.

### 12.2. Wrong assumptions to avoid

| Assumption | Reality to remember |
| --- | --- |
| “I deleted the JSON file from main, so we're safe.” | Copies/private keys may linger in Git history, clones, and artifacts; remediate the key itself. |
| “The creator left the company, so the key lost access.” | An active key still represents the service account until disabled/deleted or SA permissions change. |
| “Disabling a key immediately revokes all access tokens.” | Already-minted short-lived tokens can remain valid until they expire. |
| “Creating a new key fixes 403 errors.” | 403 errors usually stem from IAM/policy/quota; a new key grants no permissions. |
| “Blocking key creation via Org Policy deletes old keys.” | Policies mostly prevent new creation/uploads; existing keys must be handled separately. |
| “Logs show which human used the key.” | Shared private keys make individual attribution difficult. |

## 13. Troubleshooting errors when migrating to keyless auth

| Symptom | Possible cause | What to inspect |
| --- | --- | --- |
| `Could not load the default credentials` | No valid ADC source or env var points to missing path | Check ADC lookup order, WIF config file, runtime identity |
| `401 UNAUTHENTICATED` | Invalid/expired token, missing refresh, or trust mismatch | Check credential type, issuer/audience, clock skew, federation config |
| `403 PERMISSION_DENIED` | Missing IAM or blocked by policy/deny | Check effective principal, roles, resource scope, and policies |
| `iam.serviceAccounts.getAccessToken denied` | Principal lacks impersonation permission or wrong SA | Check IAM binding on service account and IAM Credentials API |
| CI/CD fails to receive federated token | Provider rejects claims or trust is too narrow/wrong | Check issuer, attribute mapping, condition, audience, and CI platform permissions |
| GKE pod gets 403 after removing Kubernetes Secret | KSA/workload principal lacks needed IAM | Check Workload Identity Federation and resource bindings |
| Cloud Run still uses old key | `GOOGLE_APPLICATION_CREDENTIALS` or key mount still present | Remove override once attached identity is ready |
| App breaks after disabling key | Unmigrated dependency still used the key | Follow controlled recovery plan, fix config, re-run |
| System-managed keys show up in list | CLI returns multiple key types | Filter with `--managed-by=user` when inventorying user-managed keys |

Authentication failures often span multiple layers. Effective triage traces **credential source → actual identity → impersonation rights (if any) → target IAM → service and project policies**, rather than generating another key to test.

## 14. End-to-end scenario: replacing keys in an e-commerce platform

Atlas Company operates:

- `orders-api` on Cloud Run, needing to read objects from Cloud Storage.
- `event-worker` on GKE, needing to pull and process Pub/Sub messages.
- A CI/CD pipeline outside Google Cloud, needing to deploy releases.
- A legacy batch job outside Google Cloud, currently supporting only a JSON service account key file.

### 14.1. Proposed design

| Component | Solution | Permissions to review |
| --- | --- | --- |
| `orders-api` / Cloud Run | Attached runtime service account + ADC | Read designated bucket; IAM on Cloud Run runtime |
| `event-worker` / GKE | Workload Identity Federation for GKE | Matching principal/KSA permitted to use Pub/Sub subscription |
| CI/CD Pipeline | WIF with CI platform identity | Trust restricted by repository/workflow; minimal deploy permissions |
| Legacy batch job | Roadmap to WIF or impersonation; controlled key exception meanwhile | Least privilege, key inventory, owner, migration deadline |

### 14.2. Phased rollout plan

**Phase A — Discovery:** List service accounts and user-managed keys, map IAM permissions, locate stored copies, assign owners, and note jobs with infrequent schedules.

**Phase B — Migrate modern workloads:** Attach runtime service account to Cloud Run; enable/configure WIF for GKE; set up trust for CI/CD. Use ADC in client libraries and remove key-pointing env vars.

**Phase C — Verify:** Test in dev/staging, monitoring logs, reliability, token issuance latency, refresh behavior, and least-privilege boundaries.

**Phase D — Retire keys:** Disable old keys once all consumers migrate; monitor across scheduled job cycles; delete keys after confirming zero dependencies.

**Phase E — Prevent recurrence:** Enable constraints blocking key creation/upload at appropriate scopes, add key scanning to repo/CI security checks, and periodically audit remaining exceptions.

### 14.3. Exit criteria

- Modern workloads need no JSON private keys while calling APIs with proper permissions.
- No key files remain in repositories, artifacts, or newly deployed images.
- Replaced user-managed keys are disabled and deleted; inventory is updated.
- Legacy batch job has an owner, risk assessment, exception expiry, and key-removal roadmap.
- Operational records clearly show **who granted permissions, which workload uses them, and how to revoke access**.
- Changes cause no degradation in functionality, reliability, or observability.

## 15. Self-check exercises

**Q1.** Service account `etl-reader` only has permission to read one bucket. If its JSON private key leaks, does whoever gets the key “automatically become Project Owner”?

*Hint:* No. They can authenticate as that service account and exercise its effective IAM permissions, not all permissions. Still, the leak is serious because data within that scope is exposed.

**Q2.** A GitHub Actions pipeline uses a long-lived JSON key to deploy Cloud Run. Which keyless option fits?

*Hint:* Workload Identity Federation with trust restricted to the exact workflow identity, granting direct permissions or impersonating an appropriate service account; use short-lived credentials and verify deployments.

**Q3.** A Cloud Run service already has a new runtime service account attached, yet code still authenticates using the old key. Why?

*Hint:* ADC may still prioritize `GOOGLE_APPLICATION_CREDENTIALS` pointing to the JSON key. Verify and remove that configuration so the app uses the attached identity.

**Q4.** After enabling a policy blocking key creation, can the team conclude all existing keys are disabled?

*Hint:* No. The policy blocks creation/upload operations per configured constraints; existing keys must be inventoried and remediated separately.

**Q5.** Why disable a key and test before deleting it during a planned migration?

*Hint:* Disabling is reversible if an unmigrated dependent job surfaces, whereas deletion is permanent. For an already-leaked key, incident response may prioritize rapid blocking over standard transition timelines.

**Q6.** A GKE pod migrated to Workload Identity Federation yet gets `403` calling Pub/Sub. Should you create a JSON key for the pod?

*Hint:* Check the Kubernetes ServiceAccount, IAM principal, mapping/impersonation, permissions on the subscription, and policies. Federation does not automatically grant IAM roles.

**Q7.** Once an exposed private key is disabled, are short-lived tokens already minted from that key immediately invalidated?

*Hint:* Not necessarily. Assess token lifetimes and incident response needs; disabling the service account itself may be required in severe cases, while factoring in impact on legitimate workloads.

**Q8.** An app team puts a service account key into Secret Manager and lets Cloud Run read the secret. Does that eliminate needing private keys?

*Hint:* Not yet. Cloud Run already needs an identity to read Secret Manager; in many cases it can use that very identity directly to call Google Cloud APIs without relying on a private key at all.

## 16. Key takeaways

- **A service account is an identity; a private key is a secret usable to represent that identity.**
- **Do not store user-managed keys when keyless authentication options exist.**
- **Cloud Run/Compute Engine:** use attached service accounts; **GKE:** use Workload Identity Federation for GKE; **CI/CD outside Google Cloud:** use WIF; **laptops:** use ADC or impersonation.
- **Least-privilege IAM and tight federation trust** matter just as much as removing keys.
- **Organization Policy** restricts key creation/upload yet does not remediate existing keys automatically.
- **Structured migration:** inventory → configure replacement → test → switch workloads → disable → monitor → delete.
- **On exposure:** remediate the key and assess already-issued tokens; removing a file from Git alone does not revoke credentials.
- **Operational monitoring:** verify 401/403 rates, token refreshes, audit logs, and app impact before closing the change.

As you continue into GKE, Cloud Run, VPC, storage, database, CI/CD, and cost sections of the GCP module, ask: **“Which workload is authenticating, via which identity, why does it need that permission, and can it run without holding long-lived private keys?”** That is the foundation for deploying secure services and operating reliably.

## Official reference documentation

- [Best practices for managing service account keys — IAM](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)
- [Best practices for using service accounts securely](https://cloud.google.com/iam/docs/best-practices-service-accounts)
- [Create and delete service account keys](https://cloud.google.com/iam/docs/keys-create-delete)
- [Disable and enable service account keys](https://cloud.google.com/iam/docs/keys-disable-enable)
- [List and get service account keys](https://cloud.google.com/iam/docs/keys-list-get)
- [Service account key rotation](https://cloud.google.com/iam/docs/key-rotation)
- [Restrict service account usage with Organization Policy](https://cloud.google.com/organization-policy/restrict-service-accounts)
- [Service account impersonation](https://cloud.google.com/iam/docs/service-account-impersonation)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
