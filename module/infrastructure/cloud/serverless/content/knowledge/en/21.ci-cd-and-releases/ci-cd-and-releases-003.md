# Authenticating Pipelines to Cloud via OIDC Federation

CI/CD pipelines need cloud access to deploy functions, update configurations, publish versions, or modify infrastructure. Traditional approaches typically store access keys, service principal secrets, or service account keys in the CI secret store. These long-lived credentials can leak through logs, compromised workflows, artifacts, or misconfigurations; they also require rotation and revocation.

**OpenID Connect (OIDC) federation** allows a pipeline to prove a job's identity to a cloud identity provider and exchange that token for short-lived credentials. The cloud only grants access when the token is signed by a trusted issuer and claims such as audience, subject, repository, branch, or environment satisfy the trust policy conditions. The pipeline does not need to store long-lived private keys or client secrets to authenticate to the cloud.

In Java serverless, pipelines can use OIDC to deploy ZIP/JARs to AWS Lambda, Azure Functions, or Google Cloud Functions/Run. OIDC only solves workload authentication; IAM/RBAC still determines which functions a pipeline can update, which resources it can create, and what data it can access. A valid token does not mean the pipeline has permission to deploy across the entire account or subscription.

## 1. Problems with Long-Lived Credentials in CI/CD

A pipeline typically runs automatically on shared runners or ephemeral runners created for each job. If long-lived access keys are stored in repository secrets, any workflow capable of reading secrets becomes a path to obtain those credentials.

Common risks:

- Secrets printed to logs due to debug mode or unsafe shell commands.
- Workflows from untrusted pull requests running steps with access to secrets.
- Compromised third-party actions exfiltrating credentials from the environment.
- Credentials copied into files, caches, artifacts, or uncleaned runners.
- Secrets not rotated on time or remaining active after an owner leaves the team.
- A single key shared across multiple repositories making it hard to trace action origins.
- Overly broad key permissions increasing blast radius when compromised.

OIDC changes this model. Instead of the pipeline holding a long-lived secret, the CI provider issues a short-lived identity token for that specific job. The cloud verifies the token and issues temporary credentials mapped to a configured role or identity.

| Long-Lived Credentials | OIDC Federation |
|---|---|
| Secret/key stored in CI | Job requests a token from a trusted issuer |
| May remain valid for months or years | Tokens and exchanged credentials are short-lived |
| Must be rotated and revoked manually | Each job receives a new token; revoked via trust policy or cloud permissions |
| Hard to bind keys to specific branches/jobs | Can bind to repository, branch, workflow, or environment |
| A key can be used outside the pipeline | Token is bound to issuer, audience, subject, and issuance time |

OIDC does not eliminate every secret. Pipelines may still need secrets to access registries, sign artifacts, or call services that do not support federation. The goal is to eliminate long-lived credentials for cloud authentication whenever both the cloud provider and CI provider support OIDC.

## 2. How Does OIDC Federation Work?

OIDC is an identity layer built on top of OAuth 2.0. The CI provider acts as the OpenID Provider (issuer), issuing a JSON Web Token (JWT) describing the job's identity. The cloud provider acts as the relying party, verifying the token and exchanging it for credentials used by cloud APIs.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant J as CI job
    participant I as CI OIDC issuer
    participant C as Cloud STS / identity service
    participant R as Cloud resource API
    J->>I: Request ID token for audience
    I-->>J: JWT with iss, aud, sub, and claims
    J->>C: Send JWT for federation / token exchange
    C->>C: Verify signature, issuer, audience, expiry, and trust conditions
    C-->>J: Short-lived cloud credentials
    J->>R: Call API using temporary credentials
    R->>R: Check IAM / RBAC permissions
    R-->>J: Operation result
~~~

Steps:

1. A job runs in the CI provider with a specific identity, such as repository org/orders-api, branch main, and environment production.
2. The workflow requests an OIDC ID token from the CI provider.
3. The issuer signs the JWT with its private key; the public key is published via a JWKS endpoint.
4. The job sends the token to the cloud's federation service.
5. The cloud verifies the issuer, signature, expiration, audience, and claims required by the trust policy.
6. If conditions are valid, the cloud issues short-lived credentials or allows impersonating a role/service identity.
7. The job uses those credentials to call deployment APIs.
8. The cloud continues checking permission policies/RBAC on each resource.

A JWT is a signed token, not an encrypted token. Anyone holding the token can read payload claims; therefore, never put secrets, passwords, or sensitive data into claims. The token is a bearer credential for its validity period: anyone who obtains it can attempt to use it until it expires or is rejected by policy.

## 3. Important Claims in an OIDC Token

A JWT typically has a header, payload, and signature. The payload holds claims that the cloud uses to decide whether to trust the job.

| Claim | Meaning | Example |
|---|---|---|
| iss | Issuer that issued the token | https://token.actions.githubusercontent.com |
| aud | Audience the token was issued for | sts.amazonaws.com |
| sub | Subject identifying job context | Repository + branch or environment |
| iat | Issued-at timestamp | Unix timestamp |
| nbf | Not-before timestamp | Unix timestamp |
| exp | Expiration timestamp | Unix timestamp |
| jti | Token identifier | JWT identifier |
| repository | Repository running the workflow | org/orders-api |
| repository_id | Immutable repository ID | Numeric ID |
| repository_owner_id | Immutable owner ID | Numeric ID |
| ref | Git ref triggering the workflow | refs/heads/main |
| environment | GitHub Environment attached to the job | production |
| workflow_ref | Workflow path and ref | .github/workflows/deploy.yml@refs/heads/main |
| job_workflow_ref | Reusable workflow used by the job | Repository, file, and ref of the reusable workflow |

Not all CI providers emit the exact same set of claims or the same sub format. Check the issuer's documentation and actual tokens from your pipeline. The cloud can only evaluate claims emitted by the provider and supported for mapping by the cloud provider.

### Issuer and Audience Must Match Exactly

iss identifies who issued the token. The cloud should only trust the exact registered issuer. aud identifies which service the token is intended for. A token issued for AWS STS must not be accepted as a token meant for Azure or Google Cloud.

Audiences typically differ by provider:

| Cloud | Typical Audience with GitHub Actions |
|---|---|
| AWS | sts.amazonaws.com |
| Microsoft Entra / Azure Login | api://AzureADTokenExchange |
| Google Cloud Workload Identity Federation | Workload identity provider audience; actions can auto-configure per provider resource |

Never copy an audience from one cloud example to another. If the audience in the token does not match the federation configuration, the token will be rejected even when the issuer and subject are right.

### Subject Must Be Tightly Constrained

sub is one of the most critical conditions. It can identify the repository, branch, tag, pull request, or environment. Traditional GitHub format examples:

~~~text
repo:ORG/REPO:ref:refs/heads/main
repo:ORG/REPO:environment:production
repo:ORG/REPO:pull_request
~~~

When a job uses a GitHub Environment, sub contains the environment instead of the branch. Therefore, a policy checking environment must be paired with deployment branch rules and required reviewers on the environment itself to restrict which branches are allowed to deploy.

## 4. Major Change: GitHub Immutable Subject Claims from July 2026

Starting **July 15, 2026**, new GitHub repositories default to an immutable subject format that includes owner and repository IDs. Existing repositories keep the prior format unless the organization or repository enables immutable subjects; repositories renamed or transferred after this date also switch to the new format. This feature does not apply to GitHub Enterprise Server.

Examples:

| Type | Subject |
|---|---|
| Legacy format | repo:octo-org/octo-repo:ref:refs/heads/main |
| Immutable format | repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main |
| Legacy environment | repo:octo-org/octo-repo:environment:production |
| Immutable environment | repo:octo-org@123456/octo-repo@456789:environment:production |

This change prevents a deleted or renamed namespace from being re-registered by another owner to produce a subject identical to the old repository. When trust policies rely solely on repository names, namespace reuse can introduce identity confusion risks.

Before configuring federation:

1. Check the actual subject format of the repository.
2. Determine whether the repository has immutable subjects enabled.
3. Retrieve the owner ID and repository ID from GitHub.
4. Update the cloud trust policy to match the new subject.
5. Test the token from a workflow on the right branch/environment.
6. Only after the new policy works should you enable immutable subjects or rename/transfer the repository.

Do not guess sub from the repository name. GitHub provides documentation and an endpoint to inspect claims; trust policies must match the exact actual format. On AWS, you can add repository_id, repository_owner_id, and ref conditions if supported in trust policies. On Google Cloud, map ID claims to attributes and use attribute conditions. On Azure federated credentials, the subject must match the exact value the token currently emits.

Refer to [GitHub OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc) to verify current claim formats.

## 5. How Is an OIDC Token Different from a Cloud Access Token?

A common design mistake is treating a GitHub OIDC ID token as an access token that can call every cloud API directly. In reality, an ID token describes job identity and is used during federation. Cloud STS or an identity service verifies the token and issues platform-specific credentials.

| Token/Credential Type | Role |
|---|---|
| CI OIDC ID token | Proves job identity to the cloud federation endpoint |
| AWS STS credentials | Temporary access key, secret key, and session token to call AWS APIs |
| Azure access token | OAuth token issued by Microsoft Entra for resources/APIs |
| Google federated access token | Short-lived credential issued by STS; can be used to impersonate a service account |
| Long-lived service account key / client secret | Static credential; generally unnecessary when OIDC federation is supported |

Never save OIDC tokens or temporary credentials into artifacts, caches, or logs. Do not pass tokens through outputs between jobs if the target job can request a fresh token under its own identity. Scope token requests strictly to the job that needs to deploy.

## 6. Distinguishing Trust Policies from Permission Policies

OIDC federation involves two independent decisions:

- **Trust / federation policy:** which identity is permitted to exchange a token for credentials or assume a role?
- **Permission policy:** after obtaining credentials, what actions is the identity allowed to perform on cloud resources?

For example, a workflow belonging to repository org/orders-api, branch main, environment production might be allowed to assume an IAM role. Yet that role should only have permissions to update the orders-api function, publish versions, and update required aliases.

Do not grant account-administrator permissions just because a pipeline needs to deploy one function. Separate roles by environment and responsibility:

| Pipeline Identity | Appropriate Permissions |
|---|---|
| Build/test | Needs no cloud deployment role |
| Deploy dev | Update dev functions and resources |
| Deploy staging | Update staging resources, run smoke tests |
| Deploy production | Controlled production release permissions |
| IaC plan | Read/plan permissions needed; no apply permissions if unnecessary |
| IaC apply | Permissions to modify infrastructure per stack and environment |

If the same role is used for dev and production, a compromised dev workflow could have an escalation path to production. Separating accounts, subscriptions, or projects by environment limits the blast radius.

## 7. Designing Secure Pipelines with GitHub Actions

A pipeline should separate build/test from deploy. Build jobs typically do not need cloud access; only deploy jobs receive id-token: write. This reduces the number of steps able to request tokens and limits permissions for code executing within the deployment job.

Example structure:

~~~yaml
name: deploy-serverless

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven
      - run: mvn -B clean verify
      - name: Package function
        run: ./scripts/package-function.sh
      - uses: actions/upload-artifact@v4
        with:
          name: function-package
          path: target/function.zip

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    concurrency:
      group: production-deploy
      cancel-in-progress: false
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: function-package
          path: drop
      # Cloud login and deploy steps go here.
~~~

This is a skeleton; the packaging script must be defined per project. Actions in the example use version tags for readability; in production, pin actions to reviewed full commit SHAs, monitor security updates, and manage workflow dependencies.

id-token: write allows the job to request an OIDC token from GitHub. This permission **does not automatically grant AWS/Azure/GCP access**. The cloud must still verify the token and grant access through trust and permission policies.

If a job uses the production environment, configure the GitHub Environment with:

- Required reviewers or appropriate approvals.
- Deployment branches/tags allowing only protected branches or tags.
- Environment secrets/variables scoped solely to that environment.
- Concurrency rules preventing overlapping deployments if concurrent releases are disallowed.
- Audit logs for approvals and deployments.

Do not grant id-token: write to test jobs or workflows handling untrusted pull requests. Do not use pull_request_target to check out and run code from a fork in a job with cloud permissions. Workflows with deploy permissions must run from protected sources and refs.

## 8. AWS: GitHub Actions OIDC with IAM Roles and STS

AWS IAM supports OIDC identity providers. For GitHub Actions, configure an IAM OIDC provider for issuer https://token.actions.githubusercontent.com, then create an IAM role with a trust policy permitting sts:AssumeRoleWithWebIdentity.

The typical audience is sts.amazonaws.com. The trust policy must restrict sub; AWS requires that subject cannot be empty or wildcard-only. Restrict repository, branch, or environment, and use immutable repository claims when available.

### Trust Policy for a Protected Branch

Example using immutable subject for a newer GitHub repository:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:ORG@OWNER_ID/REPO@REPO_ID:ref:refs/heads/main",
          "token.actions.githubusercontent.com:repository_owner_id": "OWNER_ID",
          "token.actions.githubusercontent.com:repository_id": "REPO_ID",
          "token.actions.githubusercontent.com:ref": "refs/heads/main"
        }
      }
    }
  ]
}
~~~

Replace sample values with the actual account ID, owner ID, repository ID, and subject. For repositories still using the legacy subject format, replace sub with the legacy format. Do not add broad wildcards just to make the policy work easily.

### Trust Policy for a GitHub Environment

If the job uses environment production, the subject will contain the environment:

~~~text
repo:ORG@OWNER_ID/REPO@REPO_ID:environment:production
~~~

In that case, the policy can check sub by environment and also check the ref claim if supported by AWS condition keys:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:ORG@OWNER_ID/REPO@REPO_ID:environment:production",
          "token.actions.githubusercontent.com:repository_id": "REPO_ID",
          "token.actions.githubusercontent.com:repository_owner_id": "OWNER_ID",
          "token.actions.githubusercontent.com:ref": "refs/heads/main"
        }
      }
    }
  ]
}
~~~

When the subject is an environment, you still need to configure deployment branch rules and reviewers on the GitHub Environment. Cloud trust policies and GitHub protection rules complement one another.

### Permission Policy for the Deploy Role

The trust policy only determines who can assume the role. The permission policy limits deployment actions. For example, the role might be granted permission to update code and publish versions for one specific Lambda function; if the pipeline updates aliases, add corresponding alias permissions. If artifacts are uploaded to S3 before deploying, the role needs read access to that exact object/prefix.

Never attach AdministratorAccess to a deployment role. Use specific ARNs and grant only the actions genuinely needed for the workflow.

### GitHub Actions Workflow for AWS

~~~yaml
deploy-aws:
  needs: build
  runs-on: ubuntu-latest
  environment: production
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/download-artifact@v4
      with:
        name: function-package
        path: drop

    - name: Configure AWS credentials with OIDC
      uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: arn:aws:iam::AWS_ACCOUNT_ID:role/orders-function-deploy
        aws-region: ap-southeast-1

    - name: Deploy Lambda package
      run: |
        aws lambda update-function-code \
          --function-name orders-api \
          --zip-file fileb://drop/function.zip
~~~

The AWS credentials action requests a GitHub OIDC token and exchanges it for STS credentials. The example above only illustrates updating code; production may need to wait for the update to complete, publish a version, update an alias, or use CodeDeploy for gradual rollouts. The role should only hold permissions corresponding to those operations.

## 9. Azure: Microsoft Entra Federated Identity Credentials

Azure uses Microsoft Entra to establish a federation link between the CI issuer and an Entra identity. Depending on the integration model, the identity can be an app registration/service principal or a user-assigned managed identity.

A federated identity credential typically consists of three values:

- **Issuer:** https://token.actions.githubusercontent.com
- **Subject:** the exact subject claim of the repository/branch or environment.
- **Audience:** typically api://AzureADTokenExchange on Azure public cloud.

Azure verifies issuer, subject, and audience before issuing an access token. Afterward, Azure RBAC determines whether the identity can deploy a Function App, read storage, or modify resources.

### Creating a Federated Identity Credential

For a job using a GitHub Environment, the subject might be:

~~~text
repo:ORG@OWNER_ID/REPO@REPO_ID:environment:production
~~~

For older repositories not yet using immutable subjects, the subject may still be:

~~~text
repo:ORG/REPO:environment:production
~~~

The subject value must match the exact token emitted by GitHub. If the workflow uses a branch subject instead of an environment, the subject will look like repo:ORG/REPO:ref:refs/heads/main or its immutable equivalent.

Assign Azure RBAC roles at the smallest possible scope, such as the Function App or the resource group containing the app. A deployment identity does not need Owner or Contributor across an entire subscription if it only updates one Function App.

### GitHub Actions Workflow for Azure

~~~yaml
deploy-azure:
  needs: build
  runs-on: ubuntu-latest
  environment: production
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/download-artifact@v4
      with:
        name: function-package
        path: drop

    - name: Azure login with OIDC
      uses: azure/login@v3
      with:
        client-id: ${{ vars.AZURE_CLIENT_ID }}
        tenant-id: ${{ vars.AZURE_TENANT_ID }}
        subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

    - name: Deploy Azure Function
      uses: Azure/functions-action@v1
      with:
        app-name: ${{ vars.AZURE_FUNCTIONAPP_NAME }}
        package: drop/function.zip
~~~

AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, and AZURE_FUNCTIONAPP_NAME are read from GitHub Environment variables; secrets can be used if internal policy requires it. Client ID, tenant ID, and subscription ID are configuration identifiers, not client secrets. OIDC removes the need to store a long-lived client secret for the login step.

If using Azure Government, Azure China, or another sovereign cloud, audience and environment must match the corresponding endpoints; do not blindly use public cloud defaults.

## 10. Google Cloud: Workload Identity Federation

Google Cloud uses Workload Identity Federation (WIF) to trust external identity providers without long-lived service account keys. For GitHub Actions, configuration includes:

1. Workload identity pool.
2. OIDC provider inside the pool with GitHub Actions as issuer.
3. Attribute mapping from GitHub claims to Google attributes.
4. Attribute condition restricting repository/owner/branch/environment.
5. Direct resource access or permission to impersonate a service account.

Google recommends using attribute conditions with multi-tenant issuers like GitHub. Checking only the issuer is insufficient because tokens from many different repositories are issued by the same issuer.

### Creating a Provider and Mapping Claims

Example using immutable claim IDs:

~~~bash
gcloud iam workload-identity-pools providers create-oidc github-actions \
  --location="global" \
  --workload-identity-pool="ci-pool" \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_owner_id == 'OWNER_ID' && assertion.repository_id == 'REPO_ID' && assertion.ref == 'refs/heads/main'"
~~~

Pool name, provider, owner ID, and repository ID are sample values. The attribute condition is a CEL expression. You can add a condition for assertion.environment if the deployment job uses a GitHub Environment; inspect actual token claims before writing conditions.

### Allowing Federated Identities to Impersonate a Service Account

If services or deployment tools require service account impersonation, grant roles/iam.workloadIdentityUser on the service account to the exact repository principal set:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  "orders-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/ci-pool/attribute.repository_id/REPO_ID"
~~~

The service account then receives the required IAM roles on the Function, Cloud Run, or specific resources. If APIs support granting permissions directly to federated principals, you can use direct resource access and skip impersonation. Google recommends direct access when supported by the product; use service account impersonation when APIs or tools have compatibility limitations.

### GitHub Actions Workflow for Google Cloud

~~~yaml
deploy-gcp:
  needs: build
  runs-on: ubuntu-latest
  environment: production
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/download-artifact@v4
      with:
        name: function-package
        path: drop

    - name: Authenticate to Google Cloud
      uses: google-github-actions/auth@v2
      with:
        workload_identity_provider: projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/ci-pool/providers/github-actions
        service_account: orders-deployer@PROJECT_ID.iam.gserviceaccount.com

    - name: Setup gcloud
      uses: google-github-actions/setup-gcloud@v2

    - name: Deploy function
      run: |
        gcloud functions deploy orders-api \
          --gen2 \
          --runtime=java21 \
          --region=asia-southeast1 \
          --source=drop \
          --entry-point=com.example.functions.OrderFunction \
          --trigger-http
~~~

The deploy example assumes the drop artifact directory has the source/deployment structure expected by the Google Functions build system and the Java entry point matches the application. Depending on the pipeline, you can deploy from built source or a pushed image; grant Cloud Build, Artifact Registry, and Function runtime permissions according to the workflow used.

## 11. Comparing Federation Setup Across Clouds

| Concept | AWS | Azure | Google Cloud |
|---|---|---|---|
| Where issuer is registered | IAM OIDC provider | Microsoft Entra federated identity credential | Workload Identity Pool Provider |
| GitHub issuer | https://token.actions.githubusercontent.com | https://token.actions.githubusercontent.com | https://token.actions.githubusercontent.com/ per provider config |
| Sample audience | sts.amazonaws.com | api://AzureADTokenExchange | Provider audience/resource |
| Subject restriction | IAM role trust policy | Federated identity credential | Attribute mapping/condition |
| Credential issuance | AWS STS AssumeRoleWithWebIdentity | Microsoft Entra token exchange | Google STS, optionally impersonating a service account |
| Post-federation permissions | IAM permissions policy | Azure RBAC | IAM allow policy |
| Common GitHub action | configure-aws-credentials | azure/login | google-github-actions/auth |

The same GitHub workflow can request tokens with different audiences for each cloud. Never take a token with an AWS audience and send that same token to Azure or Google. Each login step must request a token with the proper audience and only run when the job has necessary permissions.

## 12. Using OIDC with GitLab CI and Azure DevOps

OIDC is not exclusive to GitHub Actions. Many CI providers issue ID tokens with their own claims:

- GitLab CI uses id_tokens in jobs to request JWTs with a defined audience. The cloud provider verifies issuer https://gitlab.com and claims for project, namespace, branch, or environment.
- Azure DevOps provides workload identity federation in service connections; pipelines obtain tokens from the service connection and use federation to access the cloud.
- Other CI systems may support OIDC or SAML federation, but issuer, audience, and subject formats must come from that provider's documentation.

GitLab CI structure example:

~~~yaml
deploy:
  stage: deploy
  id_tokens:
    CLOUD_OIDC_TOKEN:
      aud: https://example-cloud-token-exchange
  script:
    - ./scripts/federated-login.sh
    - ./scripts/deploy-function.sh
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

aud and how the token is sent in the script must match the cloud provider. Do not assume GitLab claims are identical to GitHub claims. With Azure DevOps, use a service connection configured with workload identity federation rather than creating a client secret in a variable group.

## 13. Protecting Workflows and Deployment Environments

OIDC is only secure when the workflow granted the token is trustworthy. If an attacker can edit a workflow on a trusted branch, they can add a step requesting an OIDC token and exercise valid cloud permissions.

Measures to apply:

- Protect production branches with branch protection and required reviews.
- Use GitHub Environments for production, enabling required reviewers and deployment branch rules.
- Grant id-token: write only to deploy jobs.
- Never grant cloud permissions to pull requests from forks or unreviewed code.
- Avoid pull_request_target if the workflow checks out/runs untrusted code.
- Pin third-party actions to full commit SHAs; review action updates.
- Prefer protected reusable deployment workflows that can be restricted with job_workflow_ref if supported by the provider.
- Separate dev, staging, and production roles.
- Scope permission policies by resource ARN, scope, and action.
- Use concurrency groups to prevent two production releases from running simultaneously.
- Do not let workflows pick roles or subscriptions from arbitrary user inputs.
- Never print tokens, access tokens, or temporary credentials to logs.

If a workflow is triggered by a pull request, the GitHub subject can be pull_request. Never grant this subject production deploy permissions. For production environments, allow only protected branches/tags via GitHub Environment rules and matching trust conditions.

## 14. Protecting Artifacts and Separating Build from Deploy

OIDC proves job identity, not that the artifact has been tested or is safe. A workflow with deploy permissions could still upload a tampered JAR or ZIP to the cloud.

Design the pipeline to:

1. Build and test on a specific commit.
2. Create the artifact once.
3. Compute the checksum and store commit/build metadata.
4. Upload the artifact to a controlled artifact store.
5. Have the deployment job download the exact built artifact.
6. Verify checksum or provenance before deploying.
7. Deploy to the approved environment.
8. Record the release ID, artifact digest, and cloud deployment ID.

Do not rebuild in the production job if you need to guarantee the tested artifact is what gets released. If environment-specific builds are required, establish strict rules separating config from binaries and verifying integrity.

Never place OIDC tokens into artifacts or caches. Credentials should exist only within the deploy job and be cleared from the workspace when the job ends per the action/runtime's mechanism.

## 15. Least-Privilege Permissions for Java Serverless Deployment

A Java pipeline typically needs the following permissions depending on the platform:

| Task | Permissions Potentially Needed |
|---|---|
| Upload artifact | Write to the specific bucket/container or registry |
| Deploy function package | Update code of the specific function |
| Update configuration | Only update settings managed by the pipeline |
| Publish version | Create a new function version |
| Update alias/traffic | Update alias or deployment slot/revision |
| Create infrastructure | IaC permissions scoped to stack/resource group/project |
| Read deploy status | Read deployment/function status |
| Write logs/audit | Only if the pipeline genuinely requires it |

Do not grant a function's runtime permissions to the pipeline if the pipeline only needs to deploy. Conversely, a function's execution role/service identity is not a deployment identity. The two identities have different lifecycles and purposes.

With Terraform or CloudFormation, account for permissions to create, update, and delete resources as well as read state/backends. Separate plan and apply permissions if the process requires approval. An OIDC role for IaC may have broader scope than a role deploying a single function; separate roles and environments accordingly.

## 16. Token Lifetime, Sessions, and Rotation

Both OIDC tokens and cloud credentials expire. Lifetimes depend on the issuer, cloud provider, and role/session configuration. Never assume every provider shares the same TTL.

Principles:

- Request tokens close to the moment deployment is needed.
- Never take a token from an old job and reuse it in a new job.
- If a session expires mid-pipeline, re-authenticate via federation using the action's mechanism.
- Do not save tokens to files longer than necessary.
- Do not print tokens for debugging; JWT payloads are readable and tokens are bearer credentials.
- Revoke trust by disabling the provider, deleting the federated credential, or tightening trust conditions.
- Revoke deployment permissions by modifying IAM/RBAC permission policies.
- If token compromise is suspected, block trust/role first, inspect audit logs, and assess executed actions.

OIDC reduces the burden of rotating long-lived secrets, yet does not eliminate the need to manage trust policies, issuers, audiences, and cloud permissions. When changing repositories, branches, environments, or workflows, review federation conditions.

## 17. Observing and Auditing Federation Activity

You need to know which job received credentials, which role/service identity was used, and which resources were modified.

Monitor:

- GitHub workflow run ID, repository, commit SHA, branch, and environment.
- Assumed cloud identity/role/service account.
- Federation timestamp and session duration.
- Cloud audit logs for deploy, function update, and IAM/RBAC operations.
- Artifact digest and release ID.
- Denied federation attempts due to issuer, audience, or subject mismatches.
- Sensitive operations such as creating roles, editing trust policies, or adding federated credentials.

Do not log raw JWTs. If debugging claims is necessary, decode the payload in a controlled environment and log only needed non-sensitive claims such as iss, aud, sub, ref, repository ID, and expiry. Token signatures must be verified by the cloud; decoding payloads with a local tool does not prove a token is valid.

You can build a correlation ID from the workflow run ID and release ID to connect pipeline logs with cloud audit logs. This helps investigate incidents without storing credentials.

## 18. Troubleshooting OIDC Federation Failures

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Cannot obtain OIDC token from GitHub | Missing id-token: write or job lacks permission | Check permissions at workflow/job level |
| audience mismatch | Action requests an audience different from what provider allows | Compare aud in token with cloud config |
| subject mismatch | Wrong repository, branch, tag, or environment | Inspect actual sub and trust condition |
| Untrusted token issuer | Issuer URL or provider not registered properly | Compare iss and issuer URL |
| New GitHub repo fails to assume role | Subject switched to immutable format | Check owner/repository ID and update trust |
| AWS Not authorized to perform sts:AssumeRoleWithWebIdentity | Wrong trust policy, audience/sub mismatch | Check IAM OIDC provider, role trust policy, and action |
| AWS assume role succeeds but deploy AccessDenied | Permission policy missing action/resource | Check IAM permissions policy and ARN |
| Azure federated credential not found | Issuer, subject, or audience mismatch | Check FIC on the right app/managed identity |
| Azure login succeeds but deploy gets 403 | Insufficient Azure RBAC scope/role | Check role assignment and Function App/resource group scope |
| Google invalid_grant | Wrong provider condition, issuer, or audience | Check pool/provider, attribute mapping, and token claims |
| Google Permission denied on impersonate | Missing Workload Identity User binding | Check principalSet and service account IAM policy |
| Google auth succeeds but deploy fails | Service account lacks deploy rights or API disabled | Check IAM roles, APIs, and target resource |
| Pipeline running from fork has no token | Workflow context lacks permissions | Do not open production permissions; deploy only from protected sources |

Distinguish federation errors from authorization errors. Federation failure means the cloud has not issued credentials yet. Authorization failure means credentials were issued, but lack permission to perform the action. These two failure types must be checked in two different policies.

## 19. Safe OIDC Rollout Process

Do not delete old access keys immediately upon creating an OIDC provider. Transition step by step:

1. Inventory every pipeline using static keys, client secrets, or service account keys.
2. Identify the repository, workflow, branch, environment, and cloud resources each pipeline needs.
3. Create the OIDC provider/federated credential and role with least-privilege permissions.
4. Configure trust conditions for issuer, audience, subject, and immutable claims if supported.
5. Test on dev or staging environments.
6. Inspect cloud audit logs to verify the right principal and role.
7. Switch production pipelines to OIDC after approval.
8. Monitor across several release cycles.
9. Revoke old static credentials and verify no pipelines still depend on them.
10. Periodically review trust policies, action pinning, branch protection, and cloud permissions.

During the transition, avoid leaving both the OIDC role and old keys with broader admin permissions than necessary. Record the owner, purpose, cutover date, and rollback procedure.

## 20. Production Checklist for OIDC Federation

Before enabling a production pipeline, confirm:

1. Is the CI issuer registered accurately in the cloud?
2. Does the token audience match the federation provider?
3. Does the subject restrict to the exact repository and branch or environment?
4. Have you verified whether the actual repository uses legacy or immutable GitHub subject format?
5. If using a GitHub Environment, are deployment branch rules and reviewers enabled?
6. Is id-token: write granted only to deploy jobs?
7. Do pull requests from forks and untrusted workflows lack deploy permissions?
8. Are third-party actions pinned and reviewed?
9. Are trust policies and permission policies separated?
10. Does the role only have permissions on the required function, resource group, project, or stack?
11. Do dev, staging, and production use separate identities?
12. Is the artifact built once, verified by digest, and passed properly to the deploy job?
13. Are tokens/credentials kept out of logs, artifacts, and caches?
14. Do cloud audit logs record the role/service identity and deploy actions?
15. Is there a process to update trust when a repository is renamed, transferred, or switches to immutable subjects?
16. Is there a process to revoke federation and old static credentials?
17. Have you tested audience, subject, permission, and token expiry failures?
18. Is there an owner responsible for periodically reviewing trust policies?

## References

- [GitHub Actions OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub: Immutable subject claims for OIDC tokens](https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/)
- [AWS IAM: Create a role for OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html)
- [AWS IAM: OIDC condition context keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html)
- [Microsoft Learn: Authenticate to Azure from GitHub Actions by OIDC](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect)
- [Google Cloud: Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google Cloud: Best practices for Workload Identity Federation](https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation)

## Conclusion

OIDC federation allows CI/CD pipelines to prove identity to the cloud with short-lived tokens, then receive temporary credentials to deploy Java functions and related infrastructure. This reduces reliance on long-lived access keys, client secrets, and service account keys.

To keep federation secure, restrict issuer, audience, subject, repository, and branch/environment; separate trust policies from permission policies; grant id-token: write only to deployment jobs; protect branches and environments; and grant least-privilege cloud permissions per pipeline. Use IAM roles and STS on AWS, Microsoft Entra federated identity credentials with RBAC on Azure, and Workload Identity Pools/Providers with IAM on Google Cloud. In particular, verify the actual GitHub sub format, including immutable subject claims rolling out from July 2026. When pipelines, artifacts, and cloud permissions are managed together, serverless releases can be automated without storing long-lived credentials in CI.
