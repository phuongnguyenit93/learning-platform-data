# Authenticating Terraform with Short-Lived Identities

> **Chapter:** Infrastructure as Code with Terraform · **Scope:** Google Cloud (GCP)

## 1. Why Does Terraform Need Short-Lived Identities?

Terraform reads infrastructure state, compares it with configuration, and calls Google Cloud APIs to create, modify, or delete resources. If a pipeline keeps a service account JSON key file for months, anyone who obtains the key can use that identity until the key is revoked. Keys can also easily leak into Git history, CI logs, artifacts, or developer machines.

**Short-lived identities** mean Terraform obtains temporary credentials from a trusted source identity, typically via **service account impersonation** or **Workload Identity Federation (WIF)**. Service account access tokens normally have a default maximum lifetime of **1 hour**; when expired, the tool uses a valid authentication chain to request a new token rather than carrying the service account's private key. A short token lifetime does **not** by itself replace least-privilege permissions, restricting identity sources, and controlling where state is stored.

Across the journey of deploying Google Cloud infrastructure—from IAM/VPC to Compute Engine, GKE, Cloud Run, and data services—the same principle applies so Terraform has just enough permissions in each environment and every action remains traceable.

### After This Lesson, You Can

- Explain the differences between **Application Default Credentials (ADC)**, **service account impersonation**, **WIF**, and long-lived JSON keys.
- Use a developer account to request short-lived tokens for a service account that Terraform uses locally.
- Set up a **GitHub Actions OIDC → Google Cloud WIF → service account** flow without creating service account keys.
- Configure the **Google provider** and **GCS backend**, recognizing the two places that require separate access permissions.
- Diagnose 401/403 errors and inspect permission boundaries without printing access tokens to logs.

## 2. Identity Flow: Who Proves Identity, Who Gets Permissions?

```text
Developer machine                    GitHub Actions / CI                 Runner on GCP
User account                         Job OIDC token                      Service account attached to runtime
         |                                   |                                  |
         | ADC + impersonation               | WIF: STS + IAM Credentials API  | Metadata server
         v                                   v                                  v
                 ADC source or short-lived credentials
                                      |
                             Terraform CLI
                         /                        \
                  GCS backend                Google provider
                read/write/lock state       manage GCP resources
```

Three concepts should not be conflated:

| Component | Responsibility | Key Point |
| --- | --- | --- |
| **Source identity** | Proves who the person/job/runtime is, such as a Google user or GitHub OIDC. | Only an authorized source identity can request impersonation. |
| **Target service account** | The identity Terraform uses to call APIs; assigned IAM roles on resources to manage. | The service account's permissions determine the allowed scope of changes. |
| **Access token** | Temporary OAuth credential when calling APIs. | Tokens expire; never place them in HCL code, logs, or state files. |

**ADC** is the mechanism Google libraries use to locate an authentication source; ADC is not synonymous with a specific token type. Typical search order: (1) the path in `GOOGLE_APPLICATION_CREDENTIALS`; (2) the local ADC file at the standard location; (3) the identity attached to the Google Cloud environment via the metadata server. Therefore, a leftover environment variable pointing to a JSON key can cause Terraform to use the wrong identity even if you just logged in with `gcloud`.

**Impersonation** uses an already-authenticated identity to call the IAM Service Account Credentials API to request an access token for a service account. A user account typically needs `roles/iam.serviceAccountTokenCreator` **on the target service account**, rather than granting this role across the entire project.

**WIF** accepts an OIDC token from an external identity provider, validates the issuer, audience, and attributes, and exchanges it via the Security Token Service (STS). WIF can be granted permissions directly on resources; for Terraform, the example below chooses **WIF via a service account** to reuse existing IAM roles and improve service compatibility. The external principal needs `roles/iam.workloadIdentityUser` on the service account to use. The two roles `workloadIdentityUser` and `serviceAccountTokenCreator` serve two different forms of delegation; do not grant both by default.

| Execution Environment | Recommended Approach | Service Account JSON Key? |
| --- | --- | --- |
| Developer machine | Local ADC combined with impersonation | No |
| GitHub Actions, GitLab, or CI outside GCP | WIF accepting the job's OIDC; optionally impersonate a service account | No |
| Compute Engine/runner on Google Cloud | Attach a user-managed service account to the runtime and use ADC | No |
| Downloaded JSON key | Only consider when the above options are impossible, and strictly control key lifecycle | Yes, higher risk |

> **Note:** User ADC on a developer machine may still store login credentials/refresh tokens locally. "No service account key" does not mean "the machine has zero long-lived credentials." Protecting the machine, account, and ADC file remains critical.

## 3. Local Hands-On: ADC with Service Account Impersonation

Suppose the team has a demonstration project `my-project`, a pre-created state bucket `my-terraform-state`, and a service account `tf-deploy@my-project.iam.gserviceaccount.com`. **All IDs, emails, buckets, and project numbers in this lesson are examples and must be replaced with real values.**

Prerequisites before starting:

1. Terraform and Google Cloud CLI are installed; the practitioner is logged in with a personal or corporate identity.
2. An administrator has enabled the **IAM Service Account Credentials API** when using impersonation and granted `roles/iam.serviceAccountTokenCreator` to the practitioner on the `tf-deploy` service account.
3. The `tf-deploy` service account has permissions to **read/write objects in the state bucket** and the permissions required for the Google Cloud resources Terraform manages. For example, the state bucket commonly uses `roles/storage.objectAdmin` at the **bucket** scope, while the project only grants roles matching the resource types rather than granting `Owner`/`Editor` out of habit.
4. The GCS backend bucket exists before running `terraform init`. Enable **Object Versioning** to have a recovery path for state in case of accidental deletion or overwrite.

### Step 1: Create ADC with Impersonation Enabled

```bash
gcloud auth login
gcloud auth application-default login --impersonate-service-account=tf-deploy@my-project.iam.gserviceaccount.com
```

The first command authenticates the user for the **gcloud CLI**; the second creates the **ADC file** used by libraries/Terraform to automatically request an access token for the target service account. Running `gcloud auth login` alone does not mean ADC is configured for Terraform.

Do not put `--impersonate-service-account` alongside a private key into the repository. If `GOOGLE_APPLICATION_CREDENTIALS` currently points to another file, inspect and remove the conflicting configuration before using local ADC.

### Step 2: Declare the Provider and Backend

Minimal `main.tf` example for a lesson managing a test VPC:

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }

  backend "gcs" {
    bucket = "my-terraform-state"
    prefix = "dev/network"
  }
}

provider "google" {
  project = "my-project"
  region  = "asia-southeast1"
}

resource "google_compute_network" "lab" {
  name                    = "tf-short-lived-lab"
  auto_create_subnetworks = false
}
```

In this example, **both the backend and the provider obtain credentials via ADC**. When ADC is already configured to impersonate `tf-deploy`, there is no need to add `impersonate_service_account` to both blocks. The project must have the Compute Engine API enabled, and the service account must have permission to create VPCs, such as an appropriate network management role within the approved scope.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
```

Run `terraform apply` **only when** you have a test environment, permission to modify resources, and have carefully reviewed the plan; it may incur costs or alter infrastructure. After practicing, destroy the test resources according to your team's procedure.

### Alternative Approach: Impersonation Directly in Terraform Configuration

If ADC is currently a **source identity** (for example, `gcloud auth application-default login` with a user account without impersonation), you can select a dedicated service account per environment using the parameter in **both places**:

```hcl
terraform {
  backend "gcs" {
    bucket                      = "my-terraform-state"
    prefix                      = "dev/network"
    impersonate_service_account = "tf-deploy@my-project.iam.gserviceaccount.com"
  }
}

provider "google" {
  project                     = "my-project"
  region                      = "asia-southeast1"
  impersonate_service_account = "tf-deploy@my-project.iam.gserviceaccount.com"
}
```

This is an **alternative** to the pre-impersonated ADC approach above, not an addition to insert into the `main.tf` template as a second configuration. The source identity needs `roles/iam.serviceAccountTokenCreator` on the target service account. You can choose **two** different service accounts if you want to separate state operation permissions from infrastructure creation permissions.

**Why must it be specified in two places?** Terraform initializes the **GCS backend during `terraform init`**, before the Google provider configuration is used to manage resources. Setting impersonation on the provider does not automatically propagate to the backend. If the backend only has state read permissions while the provider has full permissions to create a VPC, `init` can still fail with 403; conversely, `init` succeeds but `plan`/`apply` is denied when calling service APIs.

## 4. CI/CD: GitHub Actions Using Workload Identity Federation

A job running in GitHub has an OIDC token proving its organization, repository, branch, and execution context. Instead of storing a JSON key in GitHub Secrets, we configure Google Cloud to **trust the exact claims** of that job. The `google-github-actions/auth` action generates a temporary credentials configuration file and exports `GOOGLE_APPLICATION_CREDENTIALS` for Terraform to use.

### Step 1: Set Up WIF Before Running the Pipeline

The following bootstrap operations are performed by an **administrator** with permissions to create pools/providers, update IAM, and manage service accounts. Use `my-project` as the project hosting the pool, **project number** `123456789012`, GitHub **owner ID** `111111`, and **repository ID** `222222`. Replace these with real organization/repository IDs; numeric IDs are more stable than names that can be renamed or reused.

Create a dedicated service account for CI if one does not already exist:

```bash
gcloud iam service-accounts create tf-deploy --project=my-project --display-name="Terraform deployment"
```

Create the WIF pool and OIDC provider. Flags are kept on a single line for easy copying and clear visibility of the trust condition; do not run with placeholder IDs:

```bash
gcloud iam workload-identity-pools create github-ci --project=my-project --location=global --display-name="GitHub Terraform"

gcloud iam workload-identity-pools providers create-oidc github --project=my-project --location=global --workload-identity-pool=github-ci --issuer-uri="https://token.actions.githubusercontent.com/" --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id" --attribute-condition="assertion.repository_owner_id=='111111' && assertion.repository_id=='222222' && assertion.ref=='refs/heads/main'"
```

The provider condition restricts access to **the exact organization, exact repository, and `main` branch**. The `attribute.repository_id` attribute used for granting access must be mapped first. If you later run from tags, environments, or other branches, redesign the condition **intentionally**; avoid opening the entire GitHub issuer because it is shared across many organizations.

Allow **only the selected repository** to impersonate the service account using the appropriate WIF role:

```bash
gcloud iam service-accounts add-iam-policy-binding tf-deploy@my-project.iam.gserviceaccount.com --project=my-project --role=roles/iam.workloadIdentityUser --member="principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-ci/attribute.repository_id/222222"
```

Next, grant `tf-deploy` the required permissions on the state bucket and the actual resources declared in Terraform. For instance, object permissions on the **state bucket** are a separate permission grant; VPC management permissions in the **target project** are another permission grant. Setting up trust, roles, and the bucket usually belongs to administrator-controlled IAM bootstrap; do not expect the pipeline's own Terraform to grant its own initial permissions.

Ensure the required Security Token Service API and IAM Service Account Credentials API are enabled according to the WIF/impersonation setup documentation. IAM/WIF updates sometimes take a few minutes to propagate.

### Step 2: Plan-Only Workflow

Place the GitHub Actions workflow under `.github/workflows/terraform-plan.yml`. This example intentionally runs only on `workflow_dispatch`, with minimal GitHub permissions for obtaining an OIDC token; Terraform resource definitions live in the repository root.

```yaml
name: Terraform plan with short-lived identity

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  terraform-plan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v3
        with:
          project_id: my-project
          workload_identity_provider: projects/123456789012/locations/global/workloadIdentityPools/github-ci/providers/github
          service_account: tf-deploy@my-project.iam.gserviceaccount.com
          create_credentials_file: true
          export_environment_variables: true

      - name: Install Terraform
        uses: hashicorp/setup-terraform@v4

      - name: Initialize backend
        run: terraform init -input=false

      - name: Check HCL
        run: terraform fmt -check

      - name: Validate configuration
        run: terraform validate

      - name: Show plan
        run: terraform plan -input=false -lock-timeout=5m
```

In this workflow:

1. `id-token: write` allows the job to obtain an OIDC token from GitHub; `contents: read` is for checkout. These are **GitHub-side** permissions, not Google Cloud IAM permissions.
2. `auth@v3` exchanges identity through the WIF provider and impersonates the service account. The action creates a temporary credentials configuration for ADC; no `credentials_json` is needed, and no JSON key is stored in Secrets.
3. `setup-terraform@v4` provides the Terraform CLI. `terraform init` uses the exported credentials for the **GCS backend**; `plan` uses the same ADC for the **Google provider** in the section 3 example.
4. The WIF condition requires the `main` branch: run the workflow from that branch. This job **does not invoke `terraform apply`**; real deployments require a separate approval workflow and environment controls.

The action creates a temporary `gha-creds-*.json` file in the workspace and cleans it up in a post-action step. Add the following patterns to ignore rules to avoid accidentally including credentials configurations in commits or artifacts:

```gitignore
gha-creds-*.json
.terraform/
*.tfstate
*.tfstate.backup
```

**Do not** ignore `.terraform.lock.hcl`: the provider version lock file should generally be committed so runs remain reproducible. If using self-hosted runners, ensure the workspace is properly cleaned after each job.

### Is a Service Account Always Needed in WIF?

Not always. Google Cloud allows granting IAM roles **directly** to WIF principals when supported by the service; this skips the impersonation step and can reduce the number of identities to manage. However, some APIs do not yet support all federated principal types. This example chooses service account impersonation so Terraform works reliably across many resource types; the final decision depends on the APIs and permission boundaries of your environment.

## 5. Permission Assignment and Protecting State

| Permission Point | Granted To | Purpose | Common Mistake |
| --- | --- | --- | --- |
| Service account `tf-deploy` | Developer: `roles/iam.serviceAccountTokenCreator` **on the SA** | Request an impersonation access token locally | Granting Token Creator too broadly at the project level. |
| Service account `tf-deploy` | WIF `principalSet`: `roles/iam.workloadIdentityUser` **on the SA** | Allow GitHub job to impersonate the SA | Allowing any repo or the entire pool to use the SA. |
| Bucket `my-terraform-state` | SA `tf-deploy`: object read/write/delete permissions needed for state/locking, e.g., `roles/storage.objectAdmin` on the bucket | `terraform init`, reading/writing state, and state locking | Forgetting backend permissions or granting Storage Admin project-wide. |
| GCP resources | SA `tf-deploy`: exact role for the service/resource, e.g., VPC management permissions in this lesson | `plan`/`apply` on resources | Granting `roles/owner` or `roles/editor` to "fix" 403 errors. |

The GCS backend supports **state locking**; state is sensitive data because it can contain secret resource attributes even when outputs are marked `sensitive`. Restrict bucket IAM, enable versioning, use appropriate encryption mechanisms, and protect version history. **Never** embed access tokens, JSON private keys, or credential contents in `.tf`, `.tfvars`, `-backend-config`, build logs, or artifacts. If the backend configuration changes, intentionally re-run `terraform init -reconfigure` and check the impact on existing state.

To improve auditability, provision service accounts per **environment** (dev/staging/prod) and separate runners/permissions accordingly; monitor **Cloud Audit Logs** for resource operations and IAM Credentials API usage when impersonation is applied. A single service account should not be able to manage every project simply because it is used for Terraform.

## 6. Diagnosing Common Authentication Errors

| Symptom | Possible Cause | Check and Resolution |
| --- | --- | --- |
| `terraform init` returns `403` with GCS | Backend identity lacks object permissions, wrong bucket, or IAM not yet propagated | Verify bucket exists, the SA/ADC used by the backend, and IAM **on the bucket**; wait for propagation if policy was just changed. |
| `init` succeeds but `plan` returns `403` | Google provider uses a different identity or SA lacks service API permissions | Check project/provider, roles on resources, and enabled APIs; do not assume init PASS means provider PASS. |
| `iam.serviceAccounts.getAccessToken denied` | Source identity is not permitted to impersonate the service account | For user ADC, check `roles/iam.serviceAccountTokenCreator`; for WIF, check `roles/iam.workloadIdentityUser` and the principal set. |
| `invalid_grant` or expired token | Local login session revoked/expired, OIDC source no longer valid, or clock skew | Re-authenticate ADC or start a new CI job; avoid reusing manually copied tokens. |
| GitHub reports unable to get OIDC token | Missing `id-token: write`, wrong auth step order, or job lacks OIDC permission | Check `permissions` and step order `checkout → auth → terraform`. |
| WIF returns issuer/audience/attribute condition error | Wrong project **number**, pool/provider name, repository/owner ID claim, branch, or audience | Compare the full provider name and OIDC claims against the mapping/condition; do not relax conditions just to make the job pass. |
| Terraform still uses an old key | `GOOGLE_APPLICATION_CREDENTIALS` points to the wrong file | Check the environment variable path and ADC precedence; remove the old configuration. |

When troubleshooting, use commands **that do not print tokens** such as `gcloud auth list`, `gcloud config list account`, `terraform version`, and inspect IAM/bucket policies. `gcloud auth list` only reflects the **gcloud CLI** account and does not prove Terraform is using the same ADC. Avoid running `gcloud auth application-default print-access-token` into CI logs: that token can be abused if exposed.

## 7. Applied Scenario: Separating Dev and Production

A team deploys a dev VPC and then expands Terraform to GKE and Cloud Run in production. A sound design is:

- Developers only impersonate `tf-dev` to read/propose changes in dev.
- The production pipeline obtains an OIDC token from a protected workflow, WIF restricts the exact repository, branch, and context, and then impersonates `tf-prod` with appropriate roles.
- Dev and production state backends use separate buckets or prefixes with matching IAM permissions; someone with dev access cannot automatically read/write production state.
- `plan` and `apply` steps are controlled by an approval workflow; no single static JSON key is shared across environments.
- IAM logs and Cloud Audit Logs allow investigating both the user/job that initiated the command and the service account that executed the API calls.

**Completion criteria for practice:** You can explain which identity mints the token, which IAM role allows impersonation, which IAM role allows modifying resources, which credentials the backend is using, and why CI runners do not need downloaded service account keys.

## Official Documentation and References

1. Google Cloud — [Authentication for Terraform](https://docs.cloud.google.com/docs/terraform/authentication).
2. Google Cloud — [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials).
3. Google Cloud — [Use service account impersonation](https://docs.cloud.google.com/docs/authentication/use-service-account-impersonation) and [Service account credentials](https://docs.cloud.google.com/iam/docs/service-account-creds).
4. Google Cloud — [Configure Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).
5. HashiCorp — [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs).
6. GitHub Actions — [google-github-actions/auth](https://github.com/google-github-actions/auth) and [hashicorp/setup-terraform](https://github.com/hashicorp/setup-terraform).

*Examples reflect publicly documented syntax at the time of writing. Before production deployment, verify action/CLI versions, IAM policies, and active service features.*
