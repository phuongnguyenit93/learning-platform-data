# Workload Identity Federation for systems outside GCP

## Learning objectives

After this lesson, learners can:

1. Explain why **Workload Identity Federation (WIF)** lets workloads outside Google Cloud call Google Cloud APIs without storing long-lived service account keys.
2. Distinguish **Identity Provider (IdP)**, **Workload Identity Pool**, **Provider**, **Security Token Service (STS)**, **federated principal**, **service account impersonation**, and IAM permissions on resources.
3. Design trust boundaries using issuer, audience, attribute mapping, attribute conditions, and least-privilege access policies.
4. Implement a sample authentication flow from **GitHub Actions** to Google Cloud, and understand how to apply similar patterns for AWS, Azure, GitLab, and Kubernetes/on-premises systems.
5. Diagnose authentication or authorization errors, build testing workflows, and operate WIF safely for Compute Engine, Cloud Run, GKE, Cloud Storage, and CI/CD.

## 1. The problem: applications outside Google Cloud need access to GCP resources

In the **CLOUD_PROVIDERS_GCP** module, learners explore how to manage projects, IAM, and VPCs; deploy Compute Engine, GKE, and Cloud Run; select storage and database services; automate releases, protect resources, monitor reliability, and control costs. Not every component in a multi-environment architecture runs inside Google Cloud.

Common scenarios:

- A **GitHub Actions** pipeline builds a Java application and deploys a revision to **Cloud Run**.
- A **GitLab CI** runner outside GCP reads artifacts from **Cloud Storage** or pushes images to **Artifact Registry**.
- An application running on **AWS EC2** or an **Azure VM** queries **BigQuery** or other Google Cloud APIs.
- Containers in **Kubernetes outside GKE** need to fetch data from a bucket or publish events to Pub/Sub.
- A system running in an **enterprise data center** needs to access Google Cloud using identities issued by an internal IdP.

An older approach was creating an **IAM service account**, downloading a **JSON private key**, and storing that key in CI secrets or on external servers. Such keys can be long-lived, easily copied, and require separate issuance, rotation, inventory, and revocation workflows.

**Workload Identity Federation** solves this by establishing a trust relationship between Google Cloud and external identities. The workload uses short-lived identity proof issued by its runtime environment; Google Cloud verifies that proof and issues a short-lived token carrying the corresponding IAM scope. This reduces the need to distribute **long-lived service account keys**.

> WIF does not mean an external service is trusted automatically. Administrators must properly configure **issuer**, **target audience**, **identity attributes**, **allow conditions**, and **resource permissions**.

## 2. Components of Workload Identity Federation

| Component | Role | Example |
|---|---|---|
| **External workload** | Program or pipeline that needs to call Google Cloud APIs | GitHub Actions job deploying a Java API |
| **External Identity Provider (IdP)** | System issuing authentication proof verifiable by Google Cloud | GitHub OIDC, Microsoft Entra ID, AWS, internal OIDC/SAML IdP |
| **Subject token / assertion** | External identity proof, usually short-lived | OIDC JWT containing issuer, subject, audience, expiry, claims |
| **Workload Identity Pool** | Namespace managing federated identities; container for providers | github-prod |
| **Workload Identity Pool Provider** | Defines trust source, token type, issuer, audience, and claim mapping | github-main using GitHub OIDC |
| **Attribute mapping** | Translates IdP claims into attributes Google Cloud understands | google.subject, attribute.repository_id |
| **Attribute condition** | Filters which identities are allowed through the provider | Only a specific repository ID on branch main |
| **Google Cloud STS** | Verifies external proof and exchanges it for a federated access token | Security Token Service API |
| **IAM principal / principalSet** | Represents a federated identity or group of identities in IAM policy | External account identified by subject or attribute |
| **IAM service account (optional)** | Google Cloud identity the workload may be permitted to impersonate | cloud-deployer@shop-prod-001.iam.gserviceaccount.com |

### Distinguishing project, pool, and provider

The **project holding the pool** is often a dedicated identity-management project; the **project holding the resources** can be another project. Never assume the target API's project ID is identical to the WIF pool's project ID.

One pool can contain multiple providers, yet identities in the same pool share one identity namespace. When using multiple IdP sources or environments with different risk profiles, consider **separating pools** so mapped attributes from different sources cannot accidentally match the same privileged group.

Example structure:

~~~text
Project identity-hub-001
└── Workload Identity Pool: github-prod
    └── OIDC Provider: github-main
        └── GitHub Actions from an allowed repository/branch

Project shop-prod-001
├── Cloud Run application
├── Artifact Registry repository
└── IAM service account: cloud-deployer
    └── May be impersonated by the federated GitHub identity per IAM
~~~

In the IAM identifier for a federated identity, you must use the **project number** of the project holding the pool—such as **123456789012**—not the project name **identity-hub-001**.

## 3. Authentication mechanics: from external token to Google Cloud permissions

~~~mermaid
sequenceDiagram
    participant W as External workload
    participant I as External IdP
    participant S as Google Cloud STS
    participant A as IAM Credentials API
    participant R as Google Cloud API
    W->>I: Request identity proof
    I-->>W: Short-lived token/assertion
    W->>S: Exchange token via pool/provider
    Note over S: Validate issuer, audience,<br/>signature, expiry, mapping, condition
    S-->>W: Federated access token
    alt Direct access
        W->>R: Call API with federated token
        Note over R: Check IAM of federated principal
        R-->>W: Result or denial
    else Via service account
        W->>A: Request service account impersonation
        Note over A: Check roles/iam.workloadIdentityUser
        A-->>W: Short-lived service account access token
        W->>R: Call API with service account token
        Note over R: Check IAM of service account
        R-->>W: Result or denial
    end
~~~

### Step 1: workload obtains an identity from its runtime environment

For example, GitHub Actions issues an OIDC token to a job granted **id-token: write**. The token typically contains:

- **iss (issuer)**: address of the issuing authority; for GitHub Actions this is **https://token.actions.githubusercontent.com**.
- **sub (subject)**: identity tied to the workflow, repository, branch, or environment per IdP rules.
- **aud (audience)**: intended recipient of the token, preventing token replay elsewhere.
- **exp/iat**: expiration and issued-at timestamps.
- **Additional claims**: repository ID, repository owner ID, ref, workflow, and contextual claims supplied by the IdP.

A token from GitHub is **not automatically a Google Cloud token**. It must be accepted on the Google Cloud side according to provider configuration.

### Step 2: STS verifies and exchanges the token

The workload sends the subject token to **Security Token Service**. The provider validates issuer, signature, audience, expiry, attribute mapping, and attribute condition. If verification succeeds, STS returns a short-lived **federated access token**. If validation fails, the flow stops here before service permissions are even evaluated.

### Step 3: IAM decides resource access

**Successful authentication does not mean authorization is granted.** After STS, an IAM policy must grant the right permissions, such as reading objects in a bucket or viewing Cloud Run services. The two authorization approaches are analyzed next.

## 4. Two authorization models: direct access and service account impersonation

### 4.1. Direct resource access

When an API or resource supports **federated principals** in IAM, administrators can bind roles directly to external identities.

For example, an app outside GCP only needs to read objects from one specific bucket. An IAM binding on the **bucket** can grant **roles/storage.objectViewer** to a federated identity mapped from a repository or subject.

Two common IAM member formats:

~~~text
# Single mapped subject:
principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-prod/subject/SUBJECT

# Set of identities sharing a repository_id attribute:
principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-prod/attribute.repository_id/987654321
~~~

**Advantages:** no intermediate service account to create and manage; IAM roles are assigned directly on resources to the federated entity. **Limitations:** some APIs or operations do not yet support federated principals directly, requiring service compatibility verification.

### 4.2. Service account impersonation

If a service account is needed as the acting identity:

1. Create or select an **IAM service account** per purpose and environment.
2. Grant **roles/iam.workloadIdentityUser** on **that exact service account** to the matching federated principal/principalSet.
3. Grant minimal resource access to the **service account**, such as Cloud Run read access or permissions on a specific Artifact Registry repository.
4. The workload uses the federated token to call the **IAM Credentials API**, obtaining a short-lived token for the service account, and then invokes the target service.

**No service account key needs to be created** in this path. Impersonation permissions and resource access permissions are two separate layers.

| Criterion | Direct resource access | Service account impersonation |
|---|---|---|
| Identity seen by target API | Federated principal | IAM service account |
| IAM role on resource | Granted directly to principal/principalSet | Granted to service account |
| Requires roles/iam.workloadIdentityUser | No | Yes, on the service account |
| Intermediate service account | No | Yes |
| Suitable when | Service supports federated principals directly | Tools/APIs require a service account or architecture already uses service accounts |
| Trade-off | Must verify per-API support and policy placement | Adds impersonation permissions and SA operations; multiple sources can share one identity if configured broadly |

**Selection principle:** prefer direct resource access when the service supports it and policy placement fits requirements; use impersonation when compatibility or existing permission workflows call for it. Never grant both paths more broadly than needed.

### 4.3. How WIF differs from similarly named authentication mechanisms

- **Workload Identity Federation (this lesson)**: connects workloads **outside Google Cloud** to Google Cloud IAM.
- **Workload Identity Federation for GKE**: a separate mechanism enabling pods on **GKE** to use workload identities; related concepts, but configured differently from GitHub or AWS providers.
- **Workforce Identity Federation**: federates **human user** identities for workforce interactive access; distinct from machine/program workloads.
- **Service account key**: downloaded long-lived private key; not WIF token exchange.
- **User `gcloud auth login`**: interactive login, not the standard authentication model for external CI jobs.

## 5. Designing trust boundaries before creating a pool

### 5.1. Why trusting the issuer alone is not enough

GitHub Actions OIDC shares a **common issuer** across many organizations and repositories. If a provider accepts every token from GitHub's issuer, workflows outside your organization could attempt token exchange. To enforce strict boundaries, use **attribute conditions** and IAM policies.

For GitHub, Google Cloud docs recommend using stable numeric IDs like **repository_id** and **repository_owner_id**. Repository and owner names can be reused or reclaimed after deletion/renaming; numeric IDs reduce identity confusion risk.

Example CEL condition:

~~~text
assertion.repository_owner_id == '24681012'
  && assertion.repository_id == '987654321'
  && assertion.ref == 'refs/heads/main'
~~~

This condition accepts only tokens matching the expected owner, repository, and ref. If production deploys only from a **GitHub Environment** protected by approvals, you can add conditions on the corresponding claim after inspecting real token contents.

**Provider conditions** restrict which identities can exchange tokens; **IAM bindings** decide what they are allowed to do. Both must follow least privilege.

### 5.2. Core control layers

| Layer | Question to answer | Example action |
|---|---|---|
| **Issuer** | Who actually issued the token? | Accept only the verified OIDC issuer |
| **Audience** | Was the token minted specifically for this WIF provider? | Prefer default audience matching the provider URL/identifier |
| **Subject** | How is a single external entity identified? | Map google.subject from an appropriate claim |
| **Mapped attributes** | Which attributes are used in policies? | repository_id, repository_owner_id, ref |
| **Attribute condition** | Which identities may participate in federation? | Specific repo ID and main branch only |
| **IAM permission** | Which resources can that identity act on? | Read Cloud Run in a project or read a single bucket |
| **Pipeline protection** | Who can edit workflows, triggers, and deployment code? | Protected branches, reviews, protected environments, restricted token rights |
| **Lifecycle/review** | When repos change, environments split, or access is revoked, who updates it? | Inventory, owners, audit logs, periodic reviews |

### 5.3. Environment separation

A simple architecture:

~~~text
GitHub repository A, branch develop
  → WIF provider for dev
  → principalSet dev
  → service account deploy-dev
  → shop-dev-001

GitHub repository A, branch main and protected environment
  → WIF provider for prod
  → principalSet prod
  → service account deploy-prod
  → shop-prod-001
~~~

Never grant production deployment permissions to every job that can read the repository. When designing pool/provider structure, draw boundaries by **trust source, environment, and sensitivity**. Granting a wildcard principalSet across an entire pool can empower more identities than intended.

## 6. Walkthrough: GitHub Actions accessing Google Cloud

Scenario: a development team wants to use a workflow in an approved repository to check the status of a **Cloud Run** service in production before later adding a release step. The first goal is proving **OIDC → STS → service account → Google Cloud API** works.

The names and IDs below are **fictitious** and must be replaced with real values:

| Sample variable | Fictitious value | Meaning |
|---|---|---|
| Project holding pool | identity-hub-001 | Manages federation boundary |
| Pool project number | 123456789012 | Required in resource names and principalSet |
| Pool ID | github-prod | Pool for production workflows |
| Provider ID | github-main | OIDC provider trusting GitHub Actions |
| GitHub repository owner ID | 24681012 | Numeric ID of the permitted organization |
| GitHub repository ID | 987654321 | Numeric ID of the permitted repo |
| Resource project | shop-prod-001 | Hosts the Cloud Run service |
| Service account | cloud-deployer@shop-prod-001.iam.gserviceaccount.com | Identity used by the workflow |

### Step 0 — Prepare permissions and APIs

Administrators need sufficient permissions to manage Workload Identity Pools/Providers, IAM service accounts, and IAM policies on target resources. You can separate IdP admin, IAM admin, and workload owner roles.

Required APIs for this scenario include **IAM API**, **Security Token Service API**, **Service Account Credentials API**, and target resource APIs such as Cloud Run. Check API status before running. The sample commands below are administrative actions to run only in an authorized project:

~~~bash
gcloud services enable \
  iam.googleapis.com \
  sts.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=identity-hub-001

# Confirm actual PROJECT NUMBER; never guess from project ID
gcloud projects describe identity-hub-001 \
  --format="value(projectNumber)"
~~~

Subsequent commands use **123456789012** as an example project number read from that output. You cannot substitute the project ID string.

### Step 1 — Create the Workload Identity Pool

~~~bash
gcloud iam workload-identity-pools create github-prod \
  --project=identity-hub-001 \
  --location=global \
  --display-name="GitHub production" \
  --description="OIDC federation for production workflows"

gcloud iam workload-identity-pools describe github-prod \
  --project=identity-hub-001 \
  --location=global
~~~

For typical GitHub WIF setups, the pool **location** is **global**. The pool name is a resource inside the identity management project, not a service account name.

### Step 2 — Create the GitHub OIDC provider with strict conditions

~~~bash
gcloud iam workload-identity-pools providers create-oidc github-main \
  --project=identity-hub-001 \
  --location=global \
  --workload-identity-pool=github-prod \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_owner_id=='24681012' && assertion.repository_id=='987654321' && assertion.ref=='refs/heads/main'"

gcloud iam workload-identity-pools providers describe github-main \
  --project=identity-hub-001 \
  --location=global \
  --workload-identity-pool=github-prod
~~~

**Configuration meaning:**

- **issuer-uri** identifies GitHub's OIDC source.
- **google.subject** is a required mapping to identify the subject (claim length limits and stability should be verified).
- **attribute.repository_id** and **attribute.repository_owner_id** allow IAM and conditions to rely on numeric IDs.
- **attribute.ref** distinguishes branches; only `main` is accepted in this example.
- **Omitting `allowed-audiences`** makes the provider use Google Cloud's default audience rules. Tokens must be requested specifically for the matching provider; never widen audiences casually just to let an unintended token pass validation.

**Note:** GitHub conditions only succeed if actual claims and values match the workflow, repository, organization, and event. When changing branches, GitHub Environments, or triggers, inspect real claims and update policies through review.

### Step 3 — Grant impersonation permission to the federated principal

Assume the service account already exists in **shop-prod-001** and its owner approved allowing GitHub Actions to impersonate it. On **the service account itself**:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  cloud-deployer@shop-prod-001.iam.gserviceaccount.com \
  --project=shop-prod-001 \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-prod/attribute.repository_id/987654321"
~~~

This binding lets identities mapped with **repository_id=987654321** impersonate the service account, **provided** the token passes through a valid provider and satisfies its attribute condition. In a pool with multiple providers, check whether attributes from another provider could also match the same principalSet. Using separate pools for sensitive trust boundaries lowers this risk.

### Step 4 — Grant minimal Google Cloud permissions to the service account

To test only **listing Cloud Run services**, you can grant an appropriate read-only role on the target project or resource:

~~~bash
# Example granting Cloud Run viewer on the target project
gcloud projects add-iam-policy-binding shop-prod-001 \
  --member="serviceAccount:cloud-deployer@shop-prod-001.iam.gserviceaccount.com" \
  --role="roles/run.viewer"
~~~

When moving from verification to **deployment**, design additional permissions for the exact operations: such as Cloud Run deployment rights, Artifact Registry image read rights, and **iam.serviceAccounts.actAs** on the runtime service account when required. Grant only at the resource and environment scope genuinely needed. **roles/iam.workloadIdentityUser** does not by itself grant application deployment permissions.

### Step 5 — Configure the GitHub Actions workflow

Create the workflow in the repository owned by your organization and allowed for federation. The sample below runs only **read-only status commands**, without deploying or modifying resources:

~~~yaml
name: Verify Google Cloud WIF

on:
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  verify-identity:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        id: auth
        uses: google-github-actions/auth@v3
        with:
          workload_identity_provider: projects/123456789012/locations/global/workloadIdentityPools/github-prod/providers/github-main
          service_account: cloud-deployer@shop-prod-001.iam.gserviceaccount.com
          project_id: shop-prod-001

      - name: Set up gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Verify target
        run: |
          gcloud projects describe shop-prod-001 --format="value(projectId)"
          gcloud run services list --project=shop-prod-001 --region=asia-southeast1
~~~

Explanation:

1. **id-token: write** permits the job to request an OIDC token from GitHub; the word **write** here does not imply write access on Google Cloud. Google Cloud permissions are governed by IAM.
2. **google-github-actions/auth** acquires the token and configures federation through the provider. When **service_account** is specified, the action follows the authorized impersonation path.
3. **setup-gcloud** prepares the CLI for subsequent steps.
4. The project and Cloud Run read commands verify context. This exercise does not yet perform a live deployment.

The **auth@v3** version in the example reflects the major action version published in the repository docs at the time of writing; for production, confirm compatibility with your runner/Node version and **pin actions to audited commit SHAs** per software supply-chain security policy.

**Check right after creation:** actions, pools/providers, and IAM can take time to propagate. Never loosen IAM permissions or remove attribute conditions merely because an initial run hits a transient failure.

### Step 6 — Verify identity and access permissions

What to observe in the job:

- Auth step completes: GitHub issued a token with valid **aud/iss/claims** and STS exchange succeeded.
- Cloud Run read command runs against **shop-prod-001**, not the project hosting the pool.
- If IAM permissions are insufficient, **PERMISSION_DENIED** appears at the target API even though authentication succeeded.
- Test running on a branch other than **main** in a test setup: the attribute condition is expected to reject it.
- Test from a repository outside the allow condition: the token must be rejected.
- Inspect relevant audit logs in Google Cloud and GitHub job history, without printing raw tokens to logs.

After verifying, the team can add a deployment step with dedicated permissions and approvals. Avoid treating success on a read-only command as proof that a workflow has complete, safe production deployment permissions.

## 7. Using WIF with AWS, Azure, GitLab, and self-managed systems

WIF is not limited to GitHub Actions. The core pattern remains **IdP → short-lived proof → STS → IAM permissions**; differences lie mainly in proof type, where tokens are obtained, and how attributes are validated.

| Workload source | Source identity | Implementation pattern |
|---|---|---|
| **AWS EC2 / AWS workloads** | AWS identity or AWS-issued OIDC token via supported mechanism | AWS or OIDC provider, constraining AWS account/role and Google Cloud permissions |
| **Azure VM / Microsoft Entra ID systems** | Azure managed identity or Entra application token | Azure/OIDC provider, restricting tenant, application, or object ID |
| **GitLab CI/CD** | GitLab OIDC ID token containing project ID, namespace ID, ref/environment | OIDC provider; restrict namespace/project/ref |
| **Azure DevOps** | Service connection OIDC token | OIDC provider; constrain exact service connection/application |
| **Kubernetes outside GKE** | ServiceAccount token via cluster OIDC issuer | OIDC provider; authorize by cluster, namespace, and ServiceAccount |
| **On-premises IdP** | OIDC token, SAML assertion, or supported mechanism | Verify issuer, public keys/certificates, subject, audience, and trust scope |

### 7.1. AWS and Azure

For AWS or Azure, admins create a pool/provider per provider instructions, then generate an **external account credentials** config file for the workload. This file tells libraries/CLI **how to fetch source platform credentials** and perform token exchange; it is **not a Google Cloud JSON private key**.

Example config file generated for an **AWS EC2** workload using IMDSv2 (paths, pool, account, and service account are examples):

~~~bash
gcloud iam workload-identity-pools create-cred-config \
  projects/123456789012/locations/global/workloadIdentityPools/aws-prod/providers/aws-ec2 \
  --service-account=reader@shop-prod-001.iam.gserviceaccount.com \
  --aws \
  --enable-imdsv2 \
  --output-file=/opt/app/google-wif.json
~~~

This command **only generates a config file** after pool/provider and IAM are already set up. It does not create IAM roles, grant Google Cloud permissions, or issue a Google service account key. When running on real AWS workloads, the library needs access to valid AWS identity metadata to execute the exchange.

For Azure, the CLI supports **--azure** and the corresponding **--app-id-uri** parameter for the configured app. Verify managed identity, audience, and tenant rather than mechanically copying AWS flags.

### 7.2. OIDC tokens from a file or self-managed endpoint

For an IdP capable of issuing short-lived OIDC JWTs to workloads, you can generate a credential configuration pointing to a controlled **token file** or internal **endpoint**:

~~~bash
# Example: system outside GCP already rotates OIDC tokens at this path
gcloud iam workload-identity-pools create-cred-config \
  projects/123456789012/locations/global/workloadIdentityPools/onprem-prod/providers/onprem-oidc \
  --service-account=reader@shop-prod-001.iam.gserviceaccount.com \
  --credential-source-file=/var/run/workload/tokens/oidc.jwt \
  --output-file=/opt/app/google-wif.json
~~~

**Prerequisites:** the file must contain a valid subject token refreshed before expiration and readable only by appropriate processes; the token must carry issuer/audience/claims matching the provider. A stale file containing an expired JWT will cause token exchange to fail.

When a Java app uses supported Google Cloud libraries, you can configure:

~~~bash
# Linux/macOS
export GOOGLE_APPLICATION_CREDENTIALS=/opt/app/google-wif.json
~~~

~~~powershell
# Windows PowerShell, when using a config file suited to the environment
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\app\google-wif.json"
~~~

An **external account credentials** file contains no Google Cloud private key and is generally not a secret in the sense of a service account key. Still, **the token source, config file, and any executable paths or URLs it references must remain trusted**. Never use configs from untrusted sources, never allow another workload to alter the credential source location, and never print raw tokens to logs.

### 7.3. Kubernetes outside GKE

In Kubernetes outside GKE, a **Kubernetes ServiceAccount** can receive a projected token with an audience targeted at a trusted provider. Google Cloud must verify the cluster's OIDC issuer/JWKS, map stable subjects, and restrict by namespace/ServiceAccount.

Do not confuse:

- **Kubernetes ServiceAccount (KSA)**: workload identity inside the cluster.
- **Google Cloud IAM service account**: Google Cloud IAM identity, used when choosing impersonation.
- **Workload Identity Federation for GKE**: dedicated mechanism for workloads inside GKE; this section applies to clusters **outside** GKE.

If a cluster is compromised or tokens are issued too broadly, WIF cannot replace Kubernetes defenses such as RBAC, pod security, secret management, network policies, and issuer protection.

## 8. Java/Spring apps and Google Cloud Client Libraries

A Java application running on AWS or on-premises normally does not need to craft raw HTTP calls to STS. The **Google Auth Library** and **Google Cloud Client Libraries** supporting external account credentials handle reading the credential source, exchanging tokens, and refreshing them.

Example initializing a Cloud Storage client using **Application Default Credentials (ADC)**:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class StorageClientFactory {
    private StorageClientFactory() {}

    public static Storage create() {
        // ADC reads GOOGLE_APPLICATION_CREDENTIALS in the runtime environment.
        // Outside GCP, this file can be an external-account configuration for WIF.
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Deployment requirements:

1. Use a Java library version supporting external account credentials compatible with your token source.
2. Point **GOOGLE_APPLICATION_CREDENTIALS** to a valid WIF config file; the app needs read permissions on that file and the token source.
3. Ensure the IdP issues tokens with the exact audience/issuer and refreshes them before expiration.
4. Grant IAM permissions on the **specific bucket or resource** to the federated principal or impersonated service account.
5. Specify target project, bucket, dataset, or API in application config; credentials **do not replace resource configuration**.
6. Log errors and latency sufficiently for diagnostics without logging access tokens, JWTs, or sensitive data.

Good tests cover both **positive cases** (right identity reads allowed resources) and **negative cases** (wrong subject, wrong environment, or out-of-scope resource access must be denied).

## 9. Safe operations: security, reliability, and cost

### 9.1. Common risks

| Risk | Impact | Recommended control |
|---|---|---|
| Provider accepts all tokens from a shared issuer | Other jobs/orgs may be accepted if IAM is too wide | Attribute condition matching org/repository/workload IDs |
| Permitting arbitrary audiences | Tokens issued for other purposes could be replayed | Use an audience dedicated to the WIF provider |
| Overly broad PrincipalSet | More workloads gain access than needed | Bind by exact subject/attribute; split pools when necessary |
| Service account holds broad Owner/Editor roles | High blast radius if pipeline is compromised | Least privilege, appropriate roles/resources |
| Sharing one service account across dev and prod | Dev can impact prod | Separate identities, providers, and IAM policies |
| Token source readable by multiple processes | Tokens could be reused before expiry | File/endpoint permissions, short token lifetimes, monitoring |
| Dependency on IdP availability | Workloads fail to obtain fresh tokens | Monitor STS errors, token refresh, and incident runbooks |
| Renaming repository without updating policy | Broken or mismatched trust scope | Prefer stable numeric IDs; review mappings and conditions |
| Overly broad workflow edit rights | Attackers can run jobs using trusted identities | Protected branches, reviews, protected environments, action controls |

### 9.2. Reliability of token acquisition

WIF replaces static keys with a dynamic dependency chain. During peak load, if the IdP, STS, or IAM Credentials API fails to issue fresh tokens, programs can fail API calls even while the target service itself is healthy.

Your design needs:

- Auth libraries with proper token caching/refresh logic.
- Accurate system clocks; expired or not-yet-valid tokens can be rejected.
- Controlled retry/backoff on transient errors, without infinite loops or printing tokens for debugging.
- Alerts on auth errors, 401/403 rates, auth latency, and impact on business SLOs.
- Procedures for when a provider/issuer rotates JWKS, tenant, audience, branch, or claims.

### 9.3. IAM and traceability

Ensure teams can correlate **job/repository/source principal** metadata with accessed resources. Monitor **Cloud Audit Logs** for relevant services per active log settings and policies; with impersonation, check service account details and delegation trails where logged. Default logging varies by activity type, so verify log enablement and retention meet investigation needs.

### 9.4. Cost control

WIF manages identities; it **does not set budgets or quotas** on resources. An authorized deployment workflow can still drive up costs on Compute Engine, Cloud Run, GKE, Cloud Storage, or data services. Pair least-privilege IAM with pipeline testing, budget alerts, quotas, and usage tracking. Never equate “secure sign-in” with “approved change” or “controlled spending”.

## 10. Diagnosing common errors

WIF errors typically occur at **three distinct layers**: obtaining the external token, exchanging the token via STS, or IAM authorization at the target resource. Identify the failing layer before altering configuration.

| Symptom | Causes to check | Resolution |
|---|---|---|
| Job fails to get GitHub OIDC token | Missing **id-token: write**, unsupported runner/action, workflow restrictions | Inspect workflow permissions and action logs |
| **invalid_grant**, issuer or signature error | Token not issued by configured IdP, expired, wrong JWKS/issuer | Verify issuer, exp/iat, JWKS, and token source |
| **Audience mismatch** | Token targets a different audience than provider expects | Configure the exact audience; do not disable checks as a workaround |
| **Attribute condition rejected** | Owner ID, repo ID, ref, namespace, or other claim mismatch | Safely inspect actual claims; update mapping/condition via review |
| **Cannot find pool/provider** | Wrong project number, location, pool/provider ID, or not yet propagated | Re-check resource name and describe pool/provider |
| Impersonation returns **PERMISSION_DENIED** | Missing **roles/iam.workloadIdentityUser** or wrong principalSet | Review IAM policy on the service account; avoid broad project grants |
| Token obtained yet Cloud Run/Storage returns **403** | Target identity lacks role on resource or another policy blocks it | Check target API, IAM roles, project, and IAM conditions |
| Java fails to load credentials | Wrong **GOOGLE_APPLICATION_CREDENTIALS**, old library, unreadable token source | Verify file path, library version, and runtime environment |
| Fails after running for several minutes | Subject token not refreshed, clock skew, job outlives token lifetime | Auto-refresh source token, check clocks and retries |
| One environment has more access than intended | Dev/prod share an account or principalSet is too broad | Separate providers, service accounts, and resource policies; audit IAM |
| GitHub auth succeeds yet deploy fails | Read rights differ from deploy rights; missing **actAs** on runtime SA or Artifact Registry access | Assign exact roles per step and resource |

### Suggested investigation workflow

1. **Check the source:** where is the workload running, which IdP issued the token, and what are audience/issuer/subject?
2. **Check WIF config:** project number, pool, provider, mapping, condition, token type, and lifetime.
3. **Check authorization branch:** direct principal or impersonation? Which resource or service account holds the IAM binding?
4. **Check target API:** resource, project, region, IAM roles, conditional policies, and API enablement.
5. **Verify negative cases:** unauthorized jobs/repositories must receive errors; do not test only the happy path.
6. **Check configuration propagation:** newly created IAM grants and providers sometimes need time to take effect.

Never fix errors by adding **Owner/Editor** roles or deleting all attribute conditions just to “make it run”. Such changes can establish an unintended wide trust relationship.

## 11. End-to-end scenario: Cloud Run deployment pipeline from GitHub

**An Binh** Enterprise operates three projects:

- **shop-dev-001**: development team's rapid testing.
- **shop-stg-001**: Cloud Run and Cloud SQL integration testing.
- **shop-prod-001**: live e-commerce service and production data.

Code lives in GitHub; build runners sit outside Google Cloud. Previously, the team shared one service account key holding deployment rights across both staging and production.

### 11.1. Target design

| Component | Dev / staging | Production |
|---|---|---|
| Trust source | Specific Repo ID, dev branch or suitable test workflow | Specific Repo ID, main branch and protected environment |
| Pool/provider | Split by risk boundary or separate provider with conditions | Strictly constrained production provider |
| Google Cloud identity | Least-privileged deploy-stg service account | Least-privileged deploy-prod service account |
| Resource permissions | Deploy to shop-stg-001 | Only authorized resources in shop-prod-001 |
| Pipeline protection | Code review and automated tests | Environment approvals, protected branch, change reviews |
| Verification | Build/test, test valid access and out-of-scope denials | Verify release artifacts, canary/rollback, audit logs |

**Impact:** an incident in a staging job is much harder to pivot into production because identities, conditions, and IAM are isolated. Eliminating stored JSON private keys lowers long-lived secret exposure; however, source code, workflows, and workflow-edit permissions must still be protected.

### 11.2. Mandatory test cases

| Test | Expectation |
|---|---|
| Valid workflow on main in registered repo | Token exchange succeeds; operates only within granted IAM scope |
| Fork or different repository attempts to use prod provider | Rejected at attribute condition or lacks IAM permissions |
| Workflow from unapproved branch | Rejected by ref condition |
| Expired source token | STS rejects; system must refresh token |
| Service account lacks resource role | Auth may succeed, yet API call returns 403 |
| Service account with staging rights tries accessing prod | Denied |
| User alters provider/role bypassing process | Caught by admin access controls and change audit trail |

### 11.3. Production readiness criteria

Deploy only with evidence that trust configuration is accurate, IAM is minimal, disallowed cases are genuinely denied, workflows are protected, and monitoring/recovery meet service requirements. Post-launch, periodically prune unused repositories, pools, providers, and service accounts to shrink the attack surface.

## 12. Practice exercise

**Scenario:** a team runs a Java system on AWS EC2 while also using GitHub Actions to build and deploy to Cloud Run. Java only needs to read a product-images bucket; the pipeline needs to read Cloud Run status and deploy new revisions after approval.

1. Diagram two separate authentication flows for **Java on AWS** and **GitHub Actions**, naming IdP, pool/provider, and IAM principal.
2. For Java reading Cloud Storage, analyze whether to grant **direct resource access** or use service account impersonation. Justify using API support and audit requirements.
3. Propose a GitHub mapping/condition constraining **repo ID**, **owner ID**, and **branch main**. Explain why checking GitHub's issuer alone is insufficient.
4. Separate pipeline service account permissions from Java application permissions. Which permission set needs only object reads, and which can deploy?
5. Describe negative tests: unauthorized repository, expired token, wrong audience, and service account missing IAM role.
6. When the pipeline reports **403** after a successful auth step, identify which layer to inspect before changing configuration.
7. List evidence regarding logging, workflow protection, token handling, and accountable owners needed before production.

### Result evaluation hints

- Answers identify **two distinct layers**: IdP/provider decides who can federate; IAM on resources or service accounts decides what they can do.
- No JSON private keys used for workflows when WIF satisfies the need.
- No broad roles granted to everyone in a pool or an entire repository when only one workflow needs access.
- Clearly distinguish **project number** in principal URIs from **project ID** of target resources; never conflate the two.
- Explain failures along **token source → STS → impersonation/IAM → resource API**, and include negative test cases.

## 13. Key takeaways and official references

**Five core points:**

1. **WIF** lets workloads outside Google Cloud exchange runtime identities for short-lived Google Cloud tokens, reducing the need to hold service account keys.
2. **Pools and providers** define trust sources; **issuer, audience, claims, mapping, and conditions** decide which tokens are accepted.
3. **Direct resource access** and **service account impersonation** are two valid authorization paths; choose based on API support and governance needs.
4. **Least-privilege IAM** is always mandatory: successful token exchange does not by itself authorize deploying or reading data.
5. WIF security spans **IdP, pipeline, policies, token refresh, logging, and operations**; negative testing matters just as much as positive testing.

**Official reference sources:**

1. [Workload Identity Federation — Google Cloud IAM](https://docs.cloud.google.com/iam/docs/workload-identity-federation) — overview, use cases, direct access, and impersonation.
2. [Configure Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) — GitHub Actions, GitLab, Azure DevOps, and HCP Terraform.
3. [Best practices for using Workload Identity Federation](https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation) — issuer, audience, attribute conditions, and trust boundaries.
4. [Configure Workload Identity Federation with AWS or Azure VMs](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-clouds) — AWS/Azure identities and credential configuration.
5. [Configure Workload Identity Federation with other identity providers](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers) — OIDC/SAML, file and endpoint token sources.
6. [Configure Workload Identity Federation with Kubernetes](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-kubernetes) — workloads on Kubernetes clusters outside GKE.
7. [gcloud iam workload-identity-pools create-cred-config](https://docs.cloud.google.com/sdk/gcloud/reference/iam/workload-identity-pools/create-cred-config) — syntax for generating external account credential files.
8. [google-github-actions/auth — GitHub](https://github.com/google-github-actions/auth) — GitHub authentication action and workflow examples.
