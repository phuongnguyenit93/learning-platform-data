# Authorizing CI/CD via Identity Federation Instead of Long-Lived Keys

CI/CD pipelines need to authenticate with the cloud to provision infrastructure, push container images, update applications, or publish artifacts. Traditional setups often store access keys, client secrets, or service account keys in CI variables and pass those credentials to every job. Long-lived credentials can outlive the pipeline lifecycle, leak into logs or artifacts, get reused outside the runner, or remain active after the person who created the job leaves the team.

OpenID Connect (OIDC) workload identity federation lets a pipeline prove its identity using a short-lived token issued by the CI platform. The cloud provider verifies the token's issuer, audience, and subject/claims, then issues temporary credentials or an access token for a configured principal. The pipeline does not store any long-lived cloud keys. Deployment permissions are still enforced by IAM/RBAC on specific resources and by trust conditions restricting which repository, branch, environment, or service connection may request a token.

This lesson belongs to the **Application Deployment** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module provides hands-on practice integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on authorizing CI/CD runners via OIDC federation, replacing long-lived keys, scoping trust policies, and separating pipeline permissions from the application's runtime identity.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the risks of access keys, client secrets, and service account keys stored in CI/CD.
- Describe the OIDC token exchange flow from GitHub Actions, GitLab CI, or Azure DevOps to a cloud provider.
- Distinguish between issuer, subject, audience, claim, federated credential, and cloud principal.
- Set up an AWS IAM OIDC provider and role trust policy for GitHub Actions.
- Use Microsoft Entra federated identity credentials for GitHub Actions or Azure DevOps service connections.
- Create a Google Cloud Workload Identity Pool/Provider and grant permissions via service account impersonation or direct resource access.
- Restrict trust by repository ID, owner ID, project ID, branch, environment, and workflow.
- Design least-privilege deployer permissions by account, subscription, project, and resource.
- Separate the CI/CD identity from the workload identity used by Spring Boot at runtime.
- Handle tokens, credential files, logs, and artifacts securely.
- Test both permitted and denied scenarios, and diagnose federation errors.

## 2. Why Not Store Long-Lived Cloud Keys in Pipelines?

A long-lived key can typically be reused until explicitly revoked or expired. If a key is stored in a CI variable, anyone with permission to edit the pipeline or job can attempt to read, exfiltrate, or reuse that key beyond its intended purpose.

Common risks include:

- Secrets printed to logs when shell tracing is enabled or debug commands dump the entire environment.
- Credentials copied into artifacts, caches, Docker build arguments, or image layers.
- A job triggered from an untrusted pull request attempting to read environment variables with production permissions.
- A compromised self-hosted runner persisting credentials for later reuse.
- A key shared across multiple repositories making it hard to trace which job used it.
- Keys left unrevoked when team members, repositories, or pipelines change.
- Key permissions being far broader than required to deploy a single service.

OIDC federation changes how pipelines prove identity: a job receives a short-lived JWT from the CI platform; the cloud verifies the token against configured trust; and then it issues temporary credentials. Trust policies and IAM roles still exist, but there is no need to store long-lived private keys or access keys in CI.

### 2.1. Comparing the Two Authentication Approaches

| Criterion | Long-lived keys | OIDC workload identity federation |
|---|---|---|
| Credentials stored in CI | Access key, client secret, or JSON key | No cloud keys stored |
| Lifetime | Can persist until rotated/revoked | Exchanged tokens and credentials are short-lived |
| Repository/job binding | Usually relies on where secrets are stored and CI permissions | Can bind issuer, subject, audience, and claims |
| Rotation | Must create, distribute, and revoke keys | CI platform issues a fresh token per job |
| Auditability | Hard to distinguish users/jobs when sharing a key | Traceable by subject, role session, and workflow |
| Remaining risks | Secret leaks and reuse | Overly broad trust policy, compromised runner/job, excessive IAM permissions |

OIDC does not automatically make a pipeline secure. If a trust policy allows any repository under a public issuer, or a production workflow executes arbitrary code from pull requests, attackers can still obtain valid tokens. You must restrict trust and control what code executes inside the job.

## 3. OIDC Flow from CI Runner to Cloud

~~~mermaid
sequenceDiagram
    participant CI as CI platform
    participant Job as CI runner/job
    participant Cloud as Cloud identity provider
    participant IAM as IAM / RBAC
    participant API as Deployment API

    CI->>Job: Issue OIDC ID token to job
    Job->>Cloud: Send JWT (issuer, audience, subject, claims)
    Cloud->>Cloud: Verify signature, issuer, expiry, audience
    Cloud->>Cloud: Match subject and trust conditions
    Cloud->>Job: Issue short-lived credential or federated token
    Job->>IAM: Call API as authenticated principal
    IAM->>IAM: Check role, action, and resource scope
    IAM->>API: Allow or deny operation
~~~

Steps to distinguish:

1. **CI identity token:** the CI platform issues a JWT representing the job/workflow/service connection.
2. **Federation trust:** the cloud verifies that the token has a trusted issuer, the right audience, and matching subject/claims.
3. **Cloud credential:** AWS issues temporary credentials via STS; Microsoft Entra issues an access token; Google Cloud STS issues a federated token, optionally impersonating a service account.
4. **Authorization:** IAM/RBAC checks what the principal is permitted to do on which resources.

The CI OIDC token is not an access token for every cloud service directly. It is proof presented to the cloud to obtain credentials under the configured trust.

## 4. Four OIDC Fields to Understand

| Field | Meaning | Example |
|---|---|---|
| Issuer (`iss`) | Platform issuing the token | `https://token.actions.githubusercontent.com` |
| Audience (`aud`) | Intended recipient service the token is issued for | `sts.amazonaws.com`, `api://AzureADTokenExchange` |
| Subject (`sub`) | Workflow/repository/branch/environment/service connection requesting access | `repo:org/repo:ref:refs/heads/main` |
| Claims | Additional metadata used to constrain trust | `repository_id`, `repository_owner_id`, `ref`, `environment`, `project_id` |

The cloud provider verifies the signature using the issuer's public keys and checks the configured fields. Never decode a JWT manually and trust its claim values without verifying signature, issuer, audience, and expiration.

### 4.1. Audience Must Match Exactly

Audience prevents a token issued for one service from being replayed against another service. For example:

- GitHub Actions with the official AWS credentials action typically uses `sts.amazonaws.com`.
- GitHub Actions with Microsoft Entra login typically uses `api://AzureADTokenExchange`.
- GitHub Actions with Google Cloud Workload Identity Federation uses the Workload Identity Provider audience per action configuration.
- GitLab ID tokens for Google Cloud often set audience to the GitLab instance URL; the Google STS exchange request uses the provider's resource name as audience.

Do not copy an audience value from a different provider's example. Compare the exact value emitted by the CI job with the audience registered on the cloud.

### 4.2. Subject Must Restrict the Exact Source

The subject typically varies by trigger:

- Branch push: repository and branch.
- Tag: repository and tag.
- Pull request: repository and `pull_request` event.
- Job using a GitHub Environment: repository and environment.
- Azure DevOps: specific service connection.
- GitLab: project, ref type, ref, and environment depending on the token.

Never use broad wildcards like `repo:org/*` or conditions checking only the issuer if a job only needs to deploy one production repository. Use specific subject/claims and widen only when there is a clear operational reason.

## 5. Designing the Trust Boundary Before Creating Federation

Before creating an OIDC provider or federated credential, determine:

- Which repository owns the source code.
- Which branches or tags are permitted to deploy.
- Which approvals/protection rules protect the production environment.
- Which workflows are allowed to use deployment reusable workflows.
- Whether runners are hosted or self-hosted, and who can modify runners.
- Which jobs have permission to read artifacts or secrets.
- The target cloud account/subscription/project.
- The resources and actions required for build, image push, provisioning, and deployment.
- Who is allowed to create/modify OIDC providers, trust policies, and role assignments.

A strong trust boundary constrains at least: organization/owner, repository ID, branch or environment, audience, and approved workflows. On GitHub, prefer immutable IDs when the provider supports those claims. On GitLab, use group/project IDs rather than relying solely on mutable project names.

### 5.1. Subject by Branch or Environment?

| Binding Method | When Suitable | Notes |
|---|---|---|
| Branch `main` | Only the main branch may deploy | Branch protection must block direct pushes and require reviews |
| Release tag | Only published tags may deploy | Protect tag creation permissions and control who can edit tags |
| GitHub Environment | Approvals, reviewers, and protection rules needed for production | Subject uses environment name instead of branch |
| Reusable workflow | Standardize deployment logic in a shared workflow | Can check `job_workflow_ref` when supported by the cloud |
| GitLab environment | Separate deployment permissions per environment | Check `environment` and `ref_path` in the token |

A workflow may target a `production` environment, yet that environment must enforce deployment branch/tag restrictions and reviewers. Simply putting the name `production` in the subject does not create approvals on its own.

## 6. Important Note: GitHub Immutable Subject Claims Starting 2026-07-15

GitHub changed the default format of the OIDC `sub` claim for repositories newly created after July 15, 2026; repositories renamed or transferred after that date also switch to the immutable format. Existing repositories retain the name-based format until opted in. The new format includes both the owner ID and repository ID, preventing scenarios where a deleted repository/organization name is re-registered by someone else.

Example legacy name-based subject:

~~~text
repo:octo-org/octo-repo:ref:refs/heads/main
~~~

Example immutable subject:

~~~text
repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main
~~~

For jobs using a GitHub Environment, the trailing segment of the subject is `environment:production`; the immutable subject looks like:

~~~text
repo:octo-org@123456/octo-repo@456789:environment:production
~~~

Before writing a trust policy, inspect the actual token claims emitted by your repository/workflow. Do not guess the subject from a branch name or copy an old policy. GitHub Enterprise Server does not support this immutable subject format per current documentation.

This change directly affects AWS IAM trust conditions, Microsoft Entra federated credentials, and Google Cloud attribute conditions. When a repository transitions subject formats, update trust policies in a controlled manner and verify the pipeline before removing the legacy configuration.

## 7. Separating Build, Deploy, and Application Runtime Identities

A pipeline performs multiple tasks, but should never use a single unconstrained principal for everything:

| Identity | Task | Example Permissions |
|---|---|---|
| Build identity | Download dependencies, build JAR, test | Read artifact caches/private packages if needed |
| Registry identity | Push image | ECR push, ACR push, Artifact Registry writer |
| Provisioner identity | Create/update infrastructure | IaC permissions within dedicated scope |
| Deployer identity | Deploy revision or update service | Deployment permissions on compute target |
| Runtime identity | Running application accessing storage/messaging/databases | S3 read, Blob data contributor, Pub/Sub publisher |

A CI/CD deployer does not need permission to read all production data just because it deploys the application. Conversely, the Spring Boot runtime does not need permission to edit IAM roles or create storage accounts.

You can share one CI identity per service/environment if permissions are very narrow; production and non-production must still use separate identities to limit blast radius. For larger systems, build/publish/provision/deploy can use separate roles and the pipeline assumes only the right role in each stage.

## 8. AWS: Creating an OIDC Provider and IAM Role for GitHub Actions

AWS Security Token Service (STS) supports `AssumeRoleWithWebIdentity`. GitHub Actions issues an ID token; the IAM OIDC provider represents the issuer; the IAM role trust policy constrains subject/audience; the role permissions policy defines permitted actions.

### 8.1. Creating the IAM OIDC Provider

For GitHub Actions:

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience/client ID list: `sts.amazonaws.com`

Create the provider once per AWS account, or check whether it already exists before creating it. Do not recreate the provider for each pipeline if the issuer is the same.

### 8.2. Trust Policy Restricting Repository and Branch

The example below applies to a repository using the legacy subject format. Only workflows from the `main` branch of the specified repository can assume the role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:octo-org/octo-repo:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

For repositories using the immutable subject format, replace `sub` with the actual value, for example:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Do not keep both legacy and immutable subjects in the same trust policy unless actively supporting a transition window. A broad legacy subject can preserve subject-recycling risks even after the repository switches to immutable format.

If the job uses the `production` GitHub Environment, the subject must match the environment:

~~~json
{
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
    "token.actions.githubusercontent.com:sub": "repo:octo-org@123456/octo-repo@456789:environment:production"
  }
}
~~~

In that case, protect the GitHub Environment with required reviewers and deployment branch/tag rules.

### 8.3. Separating Permission Policy from Trust Policy

The trust policy answers only "who may assume this role?". The permission policy answers "what may this role do?". For example, a deployer that only pushes images to an ECR repository may need ECR push actions on that repository; a role updating an ECS service needs the corresponding deployment permissions.

Never grant `AdministratorAccess` to a role merely to make a pipeline pass. Start from actual API calls, assign specific actions/resources, and expand only with verified evidence. Certain ECR actions like fetching authorization tokens operate at `*` scope, while layer upload/put image permissions can be scoped by repository ARN; review service-specific policies.

### 8.4. GitHub Actions Workflow for AWS

Example workflow using the configured role. Replace placeholder action refs with full commit SHAs verified and pinned by your organization; never rely solely on mutable tags for supply-chain security.

~~~yaml
name: deploy-aws

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Checkout
        uses: actions/checkout@VERIFIED_FULL_COMMIT_SHA

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@VERIFIED_FULL_COMMIT_SHA
        with:
          role-to-assume: arn:aws:iam::123456789012:role/orders-ci-deployer
          aws-region: ap-southeast-1
          role-session-name: orders-ci

      - name: Verify caller identity
        run: aws sts get-caller-identity

      - name: Deploy
        run: ./scripts/deploy-aws.sh
~~~

`id-token: write` only allows the job to request an OIDC token from GitHub; it does not grant write access to the source repository. The AWS role determines cloud permissions. Keep permissions scoped to the deploy job; never grant `id-token: write` to every job in a workflow unless necessary.

`aws sts get-caller-identity` confirms the active principal/session. Never print tokens, secrets, or the full credential environment.

## 9. AWS with GitLab CI/CD

GitLab CI/CD supports `id_tokens` so each job requests a JWT with a specific audience. For AWS, create an IAM OIDC provider for the GitLab instance issuer and a trust policy constraining subject, audience, or appropriate claims.

Example job requesting only the token:

~~~yaml
deploy_aws:
  stage: deploy
  id_tokens:
    AWS_OIDC_TOKEN:
      aud: sts.amazonaws.com
  script:
    - ./scripts/exchange-gitlab-oidc-with-aws.sh
    - ./scripts/deploy-aws.sh
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

The exchange script must call STS `AssumeRoleWithWebIdentity` with the token in `AWS_OIDC_TOKEN`, the role ARN, and a session name, then export temporary credentials for subsequent commands. Use a reviewed library/CLI or script, and never echo the token to stdout.

On GitLab.com, the issuer is typically `https://gitlab.com`; GitLab Self-Managed uses the instance's issuer URL. Trust policies must match the actual claims emitted by your GitLab version and the audience declared in `id_tokens`. Use project/group IDs when supported by the provider to avoid relying only on mutable group/project names.

GitLab removed `CI_JOB_JWT` and `CI_JOB_JWT_V2` starting in GitLab 17.0; use ID tokens. Do not build new pipelines on those removed JWT variables.

## 10. Azure: Federated Identity Credentials in Microsoft Entra

Microsoft Entra Workload Identity Federation allows an app registration or user-assigned Managed Identity to trust tokens from GitHub Actions, GitLab, or Azure DevOps. When a GitHub job needs to deploy Azure resources, Entra validates the token's issuer, subject, and audience, then issues an access token for the service principal/Managed Identity.

Typical values for GitHub Actions:

- Issuer: `https://token.actions.githubusercontent.com`
- Audience: `api://AzureADTokenExchange`
- Subject: the actual subject claim of the repository/workflow.

### 10.1. Creating a Federated Credential for GitHub Actions

Example JSON using the repository's immutable subject and the `main` branch:

~~~json
{
  "name": "orders-github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main",
  "audiences": [
    "api://AzureADTokenExchange"
  ]
}
~~~

Create the credential on a user-assigned Managed Identity:

~~~bash
az identity federated-credential create \
  --name orders-github-main \
  --identity-name orders-ci-deployer \
  --resource-group rg-identity-prod \
  --issuer https://token.actions.githubusercontent.com \
  --subject 'repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main' \
  --audiences api://AzureADTokenExchange
~~~

The JSON above describes the same set of `issuer`, `subject`, and `audiences` values. For an app registration, create the federated credential on the application object via Microsoft Graph or admin tooling supporting that object. Ensure the object ID passed to commands/APIs is the application object ID; the app/client ID is a different identifier.

For repositories still using the legacy subject, the subject may be `repo:octo-org/octo-repo:ref:refs/heads/main`. For jobs using a GitHub Environment, the subject ends with `environment:production`. Always inspect the actual token claims before creating the credential.

### 10.2. Flexible Federated Identity Credentials

Microsoft Entra provides Flexible Federated Identity Credentials (currently documented as Preview), allowing match expressions and additional immutable claims. For GitHub, conditions must match `sub` and `repository_id` or `repository_owner_id`; you can also add `job_workflow_ref` to constrain reusable workflows.

Illustrative expression example:

~~~text
claims['sub'] matches 'repo:octo-org@123456/octo-repo@456789:ref:refs/heads/*'
and claims['repository_id'] eq '456789'
and claims['repository_owner_id'] eq '123456'
~~~

This expression targets repositories emitting immutable subjects. Legacy repositories that have not opted in use name-based subjects; adjust the `sub` match to the actual token. This feature is in Preview and management support varies by identity type, API, and tool version. Before adopting it, consult current documentation for the exact target (app registration vs. user-assigned Managed Identity) and verify create/read/update operations are supported. Do not assume every Azure CLI, PowerShell, or Terraform provider version understands `claimsMatchingExpression`. For baseline setups, exact-match federated credentials on `issuer`, `subject`, and `audiences` are easier to audit and control.

### 10.3. Assigning Azure RBAC to the Deployer

Once federation works, assign roles to the Managed Identity or service principal at the deployment scope. For example, if a pipeline only pushes container images to Azure Container Registry, grant `AcrPush` on that exact registry; if deploying App Service, grant the appropriate deployment role scoped to the app/resource group.

Subscription-level `Contributor` is usually too broad for a single application's pipeline. Separate:
- Permissions to manage resource groups and IaC.
- Permissions to push images to a registry.
- Permissions to deploy application revisions.
- Permissions to create role assignments, which are sensitive and should belong to a dedicated pipeline/platform identity.

A federated credential only authenticates the pipeline; it does not automatically grant Azure RBAC permissions.

### 10.4. GitHub Actions Workflow for Azure

Example using the Azure Login action. Pin actions by verified full commit SHA:

~~~yaml
name: deploy-azure

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Checkout
        uses: actions/checkout@VERIFIED_FULL_COMMIT_SHA

      - name: Azure login with OIDC
        uses: azure/login@VERIFIED_FULL_COMMIT_SHA
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Verify identity
        run: az account show

      - name: Deploy
        run: ./scripts/deploy-azure.sh
~~~

Client ID, tenant ID, and subscription ID are configuration identifiers, not secrets. Credentials are issued after the OIDC exchange. Never create an `AZURE_CLIENT_SECRET` just for Azure Login when federation is already configured.

If using a user-assigned Managed Identity, the client ID must belong to the identity holding the federated credential. Assign RBAC roles to that identity at the required resource scopes.

## 11. Azure DevOps: Workload Identity Federation Service Connections

Azure DevOps uses service connections so pipelines can obtain tokens and authenticate with Microsoft Entra. When creating an Azure Resource Manager service connection, choose the **Workload identity federation** credential type instead of a secret or certificate.

Issuer and subject depend on the service connection type and when it was created. Current Azure DevOps documentation distinguishes:

| Service Connection Type | Issuer | Subject |
|---|---|---|
| Legacy type | `https://vstoken.dev.azure.com/<organization-id>` | `sc://<organization>/<project>/<service-connection>` |
| Newer service connection | `https://login.microsoftonline.com/<tenant-id>/v2.0` | `<prefix>/sc/<organization-id>/<service-connection-id>` |

Do not construct these fields manually from organization names. Copy the issuer and subject identifier directly from the service connection's **Workload Identity federation details** page and use that exact pair in the federated credential.

Operational notes:

- Create a separate service connection per application and environment.
- Scope the service connection to the exact subscription/resource group required.
- Enable approvals/checks on the service connection itself if required by organizational policy.
- Verify that the pipeline tasks/extensions in use support workload identity federation.
- If token exchange reports that no matching federated identity was found, verify exact issuer and subject match.
- Reduce default subscription permissions that the setup wizard may grant; assign narrower roles after creation.

## 12. Google Cloud: Workload Identity Federation for CI/CD

Google Cloud Workload Identity Federation (WIF) establishes trust with external OIDC providers. A Workload Pool contains providers; a provider verifies issuers and claims; attribute mappings transform claims into Google principals/attributes; attribute conditions restrict token sources.

Permissions can be granted in two ways:

- **Direct resource access:** grant IAM roles directly to the federated principal/`principalSet` on resources.
- **Service account impersonation:** grant `roles/iam.workloadIdentityUser` to the federated principal on a service account; the service account holds roles on target resources.

Google recommends direct resource access when supported by the API. Service account impersonation is useful when tools, actions, or APIs require a service account identity.

### 12.1. Creating a Workload Identity Pool

Example creating a pool for GitHub Actions:

~~~bash
gcloud iam workload-identity-pools create github-ci \
  --location=global \
  --display-name="GitHub Actions CI" \
  --description="Federated identities for approved deployment workflows"
~~~

The pool ID is a stable identifier appearing in principal URIs. Manage pools/providers in a platform project or dedicated identity project rather than scattering providers arbitrarily across many projects.

### 12.2. Creating an OIDC Provider with Attribute Mapping and Conditions

Example mapping GitHub claims:

~~~bash
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global \
  --workload-identity-pool=github-ci \
  --display-name="GitHub Actions" \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_owner_id=='123456' && assertion.repository_id=='456789' && assertion.ref=='refs/heads/main'"
~~~

Replace IDs with the actual values from your tokens. The attribute condition restricts access to the specified repository, owner, and branch. GitHub, GitLab SaaS, and HCP Terraform share multi-tenant issuers; checking only the issuer is insufficient. Google recommends attribute conditions to restrict trusted organizations, groups, or workspaces.

Do not rely on `repository` or `repository_owner` names when immutable `repository_id` and `repository_owner_id` are available. Every attribute referenced in a condition must have a corresponding mapping. `google.subject` must uniquely identify a workload.

### 12.3. Allowing a Federated Principal to Impersonate a Service Account

Example granting `Workload Identity User` for a specific repository ID:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-ci-deployer@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-ci/attribute.repository_id/456789"
~~~

`PROJECT_NUMBER` is the project number containing the Workload Identity Pool, not the project ID. `roles/iam.workloadIdentityUser` allows the federated principal to impersonate the service account; it does not grant resource deployment permissions. Grant deployment roles separately to the service account on Artifact Registry, Cloud Run, GKE, or target resources.

If using direct resource access, skip impersonation and grant roles directly to the `principalSet` on resources supporting IAM allow policies. Do not configure both models unless there is a clear reason.

### 12.4. GitHub Actions Workflow for Google Cloud

Example using service account impersonation:

~~~yaml
name: deploy-gcp

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Checkout
        uses: actions/checkout@VERIFIED_FULL_COMMIT_SHA

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@VERIFIED_FULL_COMMIT_SHA
        with:
          workload_identity_provider: projects/123456789/locations/global/workloadIdentityPools/github-ci/providers/github
          service_account: orders-ci-deployer@PROJECT_ID.iam.gserviceaccount.com

      - name: Set up gcloud
        uses: google-github-actions/setup-gcloud@VERIFIED_FULL_COMMIT_SHA

      - name: Verify identity
        run: gcloud auth list

      - name: Deploy
        run: ./scripts/deploy-gcp.sh
~~~

`workload_identity_provider` uses the project number and provider ID. The action requires `id-token: write` on the job; the service account needs a `roles/iam.workloadIdentityUser` policy binding for the federated principal. If using direct resource access, configure the auth action per direct federation instructions and grant IAM roles directly to the principal.

## 13. GitLab CI/CD with Google Cloud WIF

GitLab ID tokens let each job declare an audience. For GitLab.com, the issuer is `https://gitlab.com`; for self-managed instances, use the GitLab instance URL. Google Cloud needs provider mappings and conditions restricting group/project.

Example mapping for GitLab:

~~~text
google.subject=assertion.sub
attribute.namespace_id=assertion.namespace_id
attribute.project_id=assertion.project_id
attribute.ref_path=assertion.ref_path
attribute.environment=assertion.environment
~~~

Conditions can restrict project and branch:

~~~text
assertion.namespace_id=='123456'
&& assertion.project_id=='987654'
&& assertion.ref_path=='refs/heads/main'
~~~

Example GitLab job declaring an ID token:

~~~yaml
deploy_gcp:
  stage: deploy
  id_tokens:
    GCP_OIDC_TOKEN:
      aud: https://gitlab.com
  script:
    - ./scripts/deploy-gcp-with-wif.sh
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

Tokens are issued per job; the script exchanges the token via Google STS and optionally impersonates a service account. Never use `CI_JOB_JWT_V2`; GitLab removed that variable in 17.0. Use `id_tokens` with an audience matching the provider configuration.

### 13.1. Why Use Group/Project IDs?

GitLab SaaS shares a common issuer across many groups. If you only verify `iss=https://gitlab.com` and a name-based project subject, another project could produce claims with the same name structure if a namespace is reused. Using `namespace_id` and `project_id` binds identity to more stable identifiers.

## 14. Azure DevOps Using Google Cloud WIF

Azure DevOps can issue ID tokens from an Azure Resource Manager workload identity service connection. When configuring the Google provider:

- Retrieve the issuer and subject identifier from the service connection.
- For Azure DevOps service connections, Google docs recommend mapping `google.subject` from the segment after `/sc/` if the full subject exceeds the 127-character limit.
- Map `oid` or a claim identifying the service connection/application to construct an attribute condition.
- Grant permissions to the exact principal/subject, not the entire pool.

Example mapping per Google Cloud guidance:

~~~text
google.subject=assertion.sub.split('/sc/')[1]
~~~

The condition should check the object ID of the Azure DevOps application/service principal using the appropriate claim:

~~~text
assertion.oid=='APPLICATION_OBJECT_ID'
~~~

For Azure DevOps providers, Google documentation specifies the fixed application ID of the Azure Token Exchange Endpoint as the audience for newer connections. Do not use GitHub or GitLab audiences for this service connection.

Azure DevOps may automatically grant a role on an Azure subscription when creating a service connection. If the target is Google Cloud, remove or minimize the default Azure role assignment after confirming the service connection does not need Azure resource access.

## 15. CI/CD Permissions by Cloud

| Provider | Identity Federation | Post-Exchange Credential | Deployment Permissions |
|---|---|---|---|
| AWS | IAM OIDC provider + role trust policy | STS temporary access key/session token | IAM permission policy on AWS resources |
| Azure | Microsoft Entra federated identity credential | Entra access token | Azure RBAC role on subscription/resource group/resource |
| Google Cloud | Workload Identity Pool + OIDC provider | Federated token or impersonated service account credentials | IAM role on resource or service account |

Do not confuse:
- AWS role trust policy vs. AWS permission policy.
- Entra federated credential vs. Azure RBAC role assignment.
- Google WIF provider condition vs. IAM role binding.
- `roles/iam.workloadIdentityUser` vs. actual deployment permissions.

Each provider separates authentication and authorization in its own way; the pipeline must complete both.

## 16. Scoping Pipeline Permissions by Stage

A pipeline can separate roles by stage:

| Stage | Required Permissions | Not Needed |
|---|---|---|
| Test | Read dependencies, run unit/integration tests | Production cloud permissions |
| Build image | Read source and dependencies, build container | IAM modification permissions |
| Push image | Push to a specific registry/repository | Delete subscription/project permissions |
| IaC plan | Read state and preview changes | Runtime permissions to read production data |
| IaC apply | Create/update resources within assigned scope | Account-wide Owner/Administrator |
| Deploy | Update service/revision | Read access to all secrets |
| Smoke test | Call endpoints/health checks, minimal test operations | Resource administration permissions |

If IaC must create role assignments, separate that stage from application deployment or require approved permission elevation. Permissions such as `iam:PassRole`, `Microsoft.Authorization/roleAssignments/write`, `resourcemanager.projects.setIamPolicy`, and equivalent IAM permissions allow pipelines to escalate privileges significantly; grant them only when truly required.

### 16.1. Separating Production and Non-Production

Create separate trust policies/roles for:
- Dev/test.
- Staging.
- Production.

Production roles must trust only protected branches, tags, or environments. Never allow pull requests from forks to use production roles. Never allow jobs capable of editing arbitrary workflow definitions to obtain production tokens.

## 17. Managing Tokens, Credentials, and Temporary Files on Runners

OIDC tokens and exchanged credentials remain sensitive data despite their short lifetimes.

- Never echo JWTs, access tokens, temporary secret keys, or credential files.
- Never enable shell tracing around token handling steps.
- Never upload token/credential files to artifacts or caches.
- Delete temporary credential files after the job if actions/tools do not clean them up automatically.
- Never pass tokens via job outputs when downstream jobs can request their own tokens.
- Restrict `GITHUB_TOKEN` permissions; grant `id-token: write` only to jobs that need it.
- On self-hosted runners, clean workspaces and credential caches between jobs.
- Never run untrusted jobs on runners with access to production metadata or internal networks.
- Set role session durations matching deployment duration; never maximize session duration just to avoid refreshes.

Short-lived credentials reduce the exposure window after a leak, but do not eliminate risk while the job is running. A compromised runner can abuse an active token before it expires.

## 18. Protecting Workflows from Malicious Pull Requests and Dependencies

Attackers can tamper with workflows, build scripts, or dependencies to hijack pipeline cloud access. Control both code sources and OIDC permissions.

- Never grant production OIDC access to `pull_request` events from forks.
- Separate pull-request validation workflows from deployment workflows.
- Enforce protected branches and required reviews.
- Use GitHub Environments with required reviewers and branch restrictions.
- Pin third-party actions to verified full commit SHAs.
- Audit whether each action genuinely requires `id-token: write`.
- For reusable workflows, constrain `job_workflow_ref` when supported by the cloud provider.
- Restrict `workflow_dispatch` and `workflow_call` from untrusted sources.
- Review deployment scripts and dependency lockfiles before granting production permissions.
- On GitLab, enforce protected branches/environments and limit who can trigger protected jobs.
- On Azure DevOps, guard service connections with approvals/checks and governed pipeline templates.

Never grant OIDC permissions at the top workflow level when only a single deploy job needs them. Build and test jobs should not be able to obtain production cloud tokens.

## 19. GitHub Actions Environments and Reusable Workflows

If a trust policy uses an environment subject, the workflow must declare the exact environment name:

~~~yaml
jobs:
  deploy:
    environment: production
    permissions:
      contents: read
      id-token: write
~~~

GitHub Environments can require reviewers, restrict branches/tags, and protect secrets. The subject includes the environment name; the trust policy must match the exact name, including case sensitivity.

For reusable workflows, the `job_workflow_ref` claim identifies the shared workflow executing. This helps organizations centralize deployment logic in a governed repository. However, reusable workflows must be pinned by version/commit and cloud trust must match the exact claim emitted by GitHub.

Do not assume calling a reusable workflow creates a security boundary on its own. The calling repository must still be trusted and OIDC permissions granted only to the right job.

## 20. Azure DevOps Service Connection Approvals and Governed Pipelines

An Azure DevOps service connection is its own trust boundary. If a user can modify pipeline YAML and use a production service connection unchecked, OIDC only removes long-lived secrets without blocking unauthorized deployments.

You should:
- Create separate service connections per application and environment.
- Enable approvals/checks on production service connections.
- Restrict service connections to only the required pipelines.
- Apply branch policies and required reviewers to pipeline templates.
- Use governed pipeline templates to prevent jobs from injecting arbitrary administrative steps.
- Never allow a production service connection to be used by all projects.
- Verify that tasks/extensions support workload identity federation.

Older Azure DevOps task versions may lack WIF support. If token acquisition fails, check task compatibility and Azure CLI versions before modifying federated credentials.

## 21. GitLab Protected Environments and Token Audiences

GitLab jobs can issue ID tokens restricted to a specific audience. Set `aud` to match your cloud provider and use protected branches/environments for deployment jobs.

Example pipeline rules:

~~~yaml
deploy_production:
  stage: deploy
  environment:
    name: production
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
      when: manual
    - when: never
  id_tokens:
    CLOUD_OIDC_TOKEN:
      aud: https://gitlab.com
  script:
    - ./scripts/deploy-production.sh
~~~

Cross-check actual token claims against trust conditions. GitLab `sub` may include project path, ref type, and ref; use project ID/namespace ID when supported by the provider. Never trust all tokens from the same GitLab issuer.

## 22. Testing OIDC Federation Before Production

Testing must prove both that authorized workloads receive the identity and out-of-scope workloads are denied.

| Scenario | How to Test | Expected Result |
|---|---|---|
| Right repository, branch | Run workflow from permitted branch | Token exchange succeeds |
| Wrong repository | Run from another repository in same org | Trust condition rejects |
| Wrong owner/group | Run from another organization/group | Provider condition rejects |
| Wrong branch | Run from a feature branch | Cannot assume production role |
| Wrong environment | Use a different environment name | Subject does not match |
| Wrong audience | Request token with a different audience | Cloud rejects exchange |
| Legacy/immutable subject | Inspect token after opting into immutable subject | Trust policy matches new format |
| Pull request from fork | Run test workflow without deploy privileges | Cannot obtain cloud role |
| Missing IAM permission | Trust succeeds, but role lacks action | Cloud API returns AccessDenied/403 |
| Expired token | Submit an expired token in test | Exchange fails |
| Credential refresh | Run job longer than credential lifetime | Tool/SDK obtains fresh credentials or fails cleanly |
| Reused runner | Run subsequent job on self-hosted runner | No leftover credentials/files from prior job |
| Wrong Azure DevOps issuer | Test legacy vs. newer service connection metadata | Federation finds no matching credential |
| Wrong Google WIF claim mapping | Remove mapping or condition attribute | STS rejects token |
| Missing GCP service account binding | Federation succeeds, but missing `workloadIdentityUser` | Cannot impersonate service account |

Use test accounts/subscriptions/projects and resources without production data. Never perform negative tests by revoking roles from live production workloads.

### 22.1. Verifying the Active Principal

- AWS: `aws sts get-caller-identity` shows the active ARN/session.
- Azure: `az account show` verifies tenant/subscription context; inspect the signed-in service principal/Managed Identity.
- Google Cloud: `gcloud auth list` and `gcloud config list` verify account/project context; audit logs record which principal called APIs.

Never print raw JWTs or access tokens to verify identity. Checking the principal and audit logs suffices for most situations.

## 23. Troubleshooting Common Errors

| Symptom | Possible Cause | Remediation |
|---|---|---|
| GitHub job gets no ID token | Missing `id-token: write` on the job | Grant permission on the exact job |
| AWS `Not authorized to perform sts:AssumeRoleWithWebIdentity` | Wrong issuer/audience/subject or missing trust condition | Match OIDC provider ARN, `aud`, and `sub` |
| AWS `AccessDenied` after assuming role | Permission policy lacks action/resource | Check role policy and resource policy |
| AWS trust policy breaks suddenly after rename | GitHub subject switched to immutable format | Update `sub` to match new token |
| Azure finds no matching federated identity | Issuer, subject, or audience mismatch | Inspect actual metadata/token claims and compare field by field |
| Azure login succeeds but deploy returns 403 | Service principal/Managed Identity lacks Azure RBAC | Assign role at the proper scope |
| Azure DevOps task lacks WIF support | Outdated task/extension version | Upgrade task or use a supported task |
| Google STS `invalid_target`/audience error | Provider audience mismatch | Check ID token audience and provider config |
| Google `invalid_grant` | Wrong issuer, signature, subject, or attribute condition | Check issuer URL, clock, claims, and CEL condition |
| Google impersonation denied | Missing `roles/iam.workloadIdentityUser` on service account | Grant role to exact `principalSet`/subject |
| Google deploy returns 403 | Service account/federated principal lacks resource role | Grant IAM deployment role on resource |
| GitLab job has no token | Missing `id_tokens` or wrong audience | Add token declaration and right `aud` |
| Credential file remains on self-hosted runner | Incomplete cleanup or shared workspace | Wipe workspace/cache and isolate runners |
| Pipeline holds unusually broad permissions | Role assigned at overly broad account/project/subscription scope | Narrow scope and separate identities by stage |

Never fix trust errors by replacing `sub` with a wildcard for all repositories. Inspect the actual claims and fix only the minimal condition required.

## 24. Migrating from Static Credentials to OIDC

You can migrate service by service and environment by environment:

1. Inventory all long-lived credentials currently in CI variables, variable groups, secret stores, runners, and deployment scripts.
2. Identify which pipelines genuinely need cloud access and the exact operations each performs.
3. Create OIDC providers/federated credentials in the cloud.
4. Create dedicated deployer roles/service principals/service accounts per application and environment.
5. Grant least-privilege IAM/RBAC permissions.
6. Add OIDC permissions and login steps to a staging pipeline.
7. Verify the active principal and run deployment/smoke tests.
8. Cut over production through an approved environment/service connection.
9. Confirm no remaining steps read static credentials in workflows.
10. Revoke old keys and delete unused CI variables and secret mounts; rotate immediately if prior exposure is suspected.
11. Monitor logs/audits after cutover to catch any lingering use of old principals or keys.

Never delete old credentials before verifying the new pipeline works reliably. Yet set a firm cutover deadline to avoid maintaining two authentication paths indefinitely.

## 25. Recommended Multi-Cloud Release Model for Spring Boot

A release pipeline can be structured as follows:

~~~mermaid
flowchart TD
    SRC["Protected source branch / release tag"] --> TEST["Build and test"]
    TEST --> IMAGE["Build OCI image"]
    IMAGE --> SCAN["Scan and publish image"]
    SCAN --> OIDC["Request CI OIDC token"]
    OIDC --> FED["Exchange token with AWS / Entra / Google STS"]
    FED --> DEPLOYER["Obtain short-lived deployer credential"]
    DEPLOYER --> INFRA["Provision or update infrastructure"]
    INFRA --> DEPLOY["Deploy Spring Boot revision"]
    DEPLOY --> SMOKE["Smoke test and verify principal"]
    SMOKE --> APPROVE["Production environment approval"]
    APPROVE --> TRAFFIC["Promote / enable traffic"]
~~~

Control points:

- Build the artifact once and promote the same image digest across environments.
- Request OIDC tokens only in deployment jobs.
- Deployer identities hold permissions only for assigned resources/services.
- Spring Boot's workload identity is configured independently on the compute platform.
- Runtime secrets are read from a secret manager via workload identity, never passed through CI jobs.
- IaC provisioners have a separate identity if creating resources or role assignments.
- Production deployments require appropriate approvals/protections.

## 26. Pre-Production Checklist

- **Issuer:** Correct CI platform issuer URL is registered.
- **Audience:** Matches the exact audience emitted by jobs.
- **Subject:** Constrained to the exact repository, branch, environment, or service connection.
- **Immutable claims:** Current GitHub subject format is verified; repository/owner IDs are used where supported.
- **Attribute conditions:** Google/GitLab/Azure providers constrain tenant, group, project, and branch.
- **Trust policy:** No broad wildcards or issuer-only checks.
- **Role permissions:** Only required actions on specific resources/scopes are granted.
- **Identity separation:** Build, provisioner, deployer, and runtime identities are separated.
- **GitHub:** `id-token: write` only on required jobs; actions pinned to full commit SHAs; environments enforce protection rules.
- **GitLab:** Uses `id_tokens`, not deprecated/removed JWT variables; protected branches/environments configured.
- **Azure DevOps:** Service connections use workload identity federation; issuer/subject copied from actual metadata; approvals/checks enabled.
- **AWS:** OIDC provider, `aud`, `sub`, trust policy, and permission policy are tested.
- **Azure:** Federated credentials and Azure RBAC are verified separately.
- **Google Cloud:** Workload Identity Pool/Provider mappings, attribute conditions, and service account bindings are tested.
- **Token handling:** No logging of JWTs, access tokens, or credential files; cleanup is in place.
- **Runners:** Self-hosted runners are isolated and cleaned between jobs.
- **Pull requests:** Workflows from forks/untrusted branches never receive production tokens.
- **Audit:** Role sessions/principals and deployment runs are traceable.
- **Migration:** Plan exists to revoke and remove legacy static keys from CI.
- **Recovery:** Federated credentials/role associations can be revoked if a pipeline or repository is compromised.

## 27. Summary

OIDC workload identity federation lets CI/CD pipelines authenticate to the cloud using short-lived tokens issued by GitHub Actions, GitLab, or Azure DevOps. AWS validates tokens via an IAM OIDC provider and issues STS temporary credentials; Microsoft Entra uses federated identity credentials to issue access tokens; Google Cloud uses Workload Identity Pools/Providers and STS to issue federated credentials or impersonate service accounts.

Replacing long-lived keys is only part of pipeline security. Trust policies must constrain issuer, audience, repository, owner, branch, environment, or service connection; IAM/RBAC must grant only the right deployment permissions; workflows and runners must be protected against untrusted code. Separating the deployer identity from the workload identity ensures Spring Boot runs with least-privilege data access while pipelines only hold permission to release new versions. With negative testing, audit logs, and a retirement plan for old credentials, multi-cloud application deployments become far easier to govern and audit.

## References

- [GitHub Actions OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [Configuring OpenID Connect in Amazon Web Services](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [AWS IAM OIDC provider and role trust policy for GitHub Actions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
- [AWS STS AssumeRoleWithWebIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html)
- [Microsoft Entra federated identity credentials](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation)
- [Azure CLI: az identity federated-credential](https://learn.microsoft.com/en-us/cli/azure/identity/federated-credential)
- [Flexible federated identity credentials](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-flexible-federated-identity-credentials)
- [Migrate GitHub Actions federated credentials to immutable subjects](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-github-immutable-subjects)
- [Azure DevOps workload identity federation troubleshooting](https://learn.microsoft.com/en-us/azure/devops/pipelines/release/troubleshoot-workload-identity)
- [Google Cloud Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google Cloud Workload Identity Federation best practices](https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation)
- [GitLab CI/CD: Connect to cloud services](https://docs.gitlab.com/ci/cloud_services/)
- [GitLab CI/CD: Configure OpenID Connect with Google Cloud](https://docs.gitlab.com/ci/cloud_services/google_cloud/)
