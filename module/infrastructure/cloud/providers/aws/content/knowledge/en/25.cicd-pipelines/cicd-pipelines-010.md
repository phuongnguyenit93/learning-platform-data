# Cross-Account CI/CD and OIDC Authentication from External Systems

A CI/CD pipeline running outside AWS still needs permissions to call AWS APIs to push artifacts, update infrastructure, deploy containers, or release applications. How permissions are granted directly affects the security posture of the entire release process. Storing long-lived access keys in repository secrets risks exposing credentials via logs, runners, workflows, or backups, and creates credentials that are hard to tie to individual runs.

**OpenID Connect (OIDC) federation** allows a CI/CD platform that has authenticated a workflow to issue a short-lived ID token. AWS Security Token Service (STS) verifies the token and returns temporary credentials for an IAM role if its trust policy accepts the issuer, audience, and subject claims. The pipeline uses those temporary credentials to invoke AWS APIs without storing long-lived AWS access keys.

In multi-account AWS environments, pipelines can either assume a deployment role directly in each account or assume a role in a tooling account and role-chain into workload accounts. Both models require tight trust constraints, least-privilege permissions, auditing, and deployment path controls.

This lesson belongs to the **CI/CD on AWS** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects IAM, STS, AWS Organizations, artifact storage, ECR, CloudFormation, ECS/EKS, and deployment environments to build secure, observable, and controlled pipelines.

> **Principle:** OIDC verifies the workflow's identity; the trust policy decides which workflows may assume the role; the permissions policy decides what the role session may do. These three layers must be designed separately and verified together.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain OIDC federation and distinguish between ID tokens, access tokens, and AWS temporary credentials.
2. Describe the flow where GitHub Actions/GitLab CI obtains a token and calls AWS STS.
3. Distinguish between an IAM OIDC identity provider, a role trust policy, and a role permissions policy.
4. Restrict role assumption by issuer, audience, repository/project, branch, tag, or protected environment.
5. Configure OIDC trust for GitHub Actions and GitLab CI/CD.
6. Explain why long-lived AWS access keys should not be stored in CI secrets.
7. Design cross-account deployments using direct federation or hub-and-spoke role chaining.
8. Configure source and target roles for cross-account `AssumeRole`.
9. Understand the impact of session duration, role chaining, session policies, and SCPs.
10. Design least-privilege permissions for builds, artifact publishing, and deployments.
11. Protect workflows against untrusted pull requests, dependency/action compromise, and token leakage.
12. Use CloudTrail, STS caller identity, and CI logs for auditing and troubleshooting.
13. Establish onboarding, rotation, decommissioning, and incident response processes for OIDC roles.
14. Practice setting up an OIDC deployment role in an AWS sandbox.

## 2. What Is OIDC Federation in CI/CD?

OpenID Connect is an identity layer built on OAuth 2.0. In CI/CD, an identity provider (IdP) issues an **ID token** formatted as a JSON Web Token (JWT) describing the identity and context of the running job/workflow.

An OIDC token typically contains claims:

| Claim | Meaning | Example |
|---|---|---|
| `iss` | Issuer, where the token was issued | `https://token.actions.githubusercontent.com` |
| `aud` | Audience, the target system the token is issued for | `sts.amazonaws.com` |
| `sub` | Subject, the identity of the workflow/project/ref/environment | Repository + branch or GitLab project + ref |
| `iat` | Timestamp when the token was issued | Unix timestamp |
| `exp` | Timestamp when the token expires | Unix timestamp |
| `jti` | Token identifier if issued by the IdP | Unique token ID |

AWS does not trust a token merely because a runner sends it to STS. AWS verifies the signature using public keys from the IdP's JWKS, along with issuer, audience, expiration, and conditions in the IAM role trust policy. If valid, STS returns temporary credentials consisting of an access key ID, secret access key, and session token.

### 2.1. Distinguishing Three Credential Types

| Component | Issued by | Purpose | Is it an AWS credential? |
|---|---|---|---|
| OIDC ID token | GitHub, GitLab, or IdP | Proves identity/claims of the job | No |
| AWS STS temporary credentials | AWS STS | Signs AWS API requests | Yes |
| Long-lived IAM access key | IAM | Long-lived credential for an IAM user | Yes |

The OIDC token is proof of identity. STS credentials are the AWS access granted after the token is verified. Never place OIDC tokens or STS credentials into logs, artifacts, caches, or unnecessary outputs.

### 2.2. Authentication Flow

~~~mermaid
sequenceDiagram
    participant CI as External CI runner
    participant IdP as OIDC provider
    participant STS as AWS STS
    participant IAM as IAM role
    participant AWS as AWS services
    CI->>IdP: Request job ID token
    IdP-->>CI: Signed JWT (iss, aud, sub, exp)
    CI->>STS: AssumeRoleWithWebIdentity
    STS->>STS: Verify signature, issuer, audience, expiry
    STS->>IAM: Evaluate role trust policy
    IAM-->>STS: Allow / Deny
    STS-->>CI: Temporary AWS credentials
    CI->>AWS: Signed API request
    AWS->>IAM: Evaluate role permissions and guardrails
    AWS-->>CI: API response
~~~

Key points to remember:

- The CI runner requests a token from the IdP using the platform's native mechanism.
- Tokens are issued for a specific audience; a token meant for another service should not be usable to assume an AWS role.
- The AWS role trust policy must trust the exact IAM OIDC provider and constrain claims.
- STS credentials expire; runners must finish jobs within the lifetime or refresh safely for long workflows.
- AWS authorization still enforces identity policies, resource policies, permissions boundaries, session policies, SCPs, and other policy controls.

### 2.3. Why OIDC Reduces Credential Risk

- Eliminates storing IAM user access keys in GitHub/GitLab secrets.
- Each job receives temporary credentials bound to a role.
- Trust policies can restrict by repo/project, branch, tag, or environment.
- Access can be revoked by updating trust/permission policies or IdP configuration.
- CloudTrail logs role sessions and STS federation events for investigation.
- Temporary credentials expire naturally, limiting exposure windows if leaked.

OIDC does not automatically make a pipeline secure. If an attacker controls a trusted workflow, runner, or job dependency, they can abuse the token/credentials while the job runs. Source code, workflow files, runners, and dependencies must all be protected.

## 3. Three IAM Components to Configure

### 3.1. IAM OIDC Identity Provider

An IAM OIDC provider defines an issuer accepted by AWS. Configuration includes:

- Exact provider URL/issuer over HTTPS.
- Allowed audiences/client IDs.
- Public discovery document and JWKS endpoints so AWS can verify tokens.
- Certificate chain/endpoint verification per IdP requirements.

GitHub Actions provider example:

| Field | Value |
|---|---|
| Provider type | OpenID Connect |
| Provider URL | `https://token.actions.githubusercontent.com` |
| Audience | `sts.amazonaws.com` |

GitLab.com provider example:

| Field | Value |
|---|---|
| Provider type | OpenID Connect |
| Provider URL | `https://gitlab.com` |
| Audience | `sts.amazonaws.com` (if the job ID token uses this audience) |

For GitLab Self-Managed, the issuer URL must match the instance's exact public URL and the discovery endpoint must be reachable from AWS. OIDC URLs may include a path per OIDC standards; do not strip paths or alter the issuer arbitrarily.

**Important note for cross-account:** The IAM OIDC identity provider referenced in a role trust policy must reside in the **same AWS account** as that role. If pipelines assume roles directly in multiple target accounts, each target account needs its own OIDC provider. In a hub-and-spoke setup, only the tooling account needs the OIDC provider; target accounts trust the tooling account's IAM role using `sts:AssumeRole`.

### 3.2. Role Trust Policy

A trust policy is a resource-based policy attached to an IAM role, defining which principals may assume the role and via which STS action.

For OIDC federation, the action is typically:

~~~text
sts:AssumeRoleWithWebIdentity
~~~

The trust policy must minimally restrict:

- Federated principal matching the exact OIDC provider ARN.
- `aud` matching the audience registered on the IAM provider.
- `sub` matching only authorized repositories/projects and branches/tags/environments.
- Additional stable claims where supported by the IdP and AWS condition keys.

Never use a trust policy with only an issuer and no subject restriction. For GitHub OIDC, AWS requires the `sub` condition not to be null or a bare wildcard. Overly broad wildcards allow out-of-scope workflows to assume the role.

### 3.3. Role Permissions Policy

The permissions policy defines which AWS APIs on which resources the role session can invoke. Examples:

- Build role: write artifacts to a specific prefix.
- Deploy role: update an ECS service or create a CloudFormation stack change.
- Release role: read image metadata, publish releases, and record deployment status.
- Read-only verification role: read CloudWatch/ELB/ECS deployment status.

Do not confuse trust policies with permissions policies:

| Policy | Answers the question | Example |
|---|---|---|
| Trust policy | Who may assume the role? | GitHub repository `my-org/my-service`, branch `main` |
| Permissions policy | What may the role session do? | `s3:PutObject` to the release artifact prefix |

A role can be assumed only if the trust policy allows it. Afterward, AWS evaluates effective permissions of the role session on every service API call.

## 4. Designing Cross-Account CI/CD

An organization may split AWS accounts by environment or function:

| Account | Role |
|---|---|
| Tooling / Shared Services | CI runners, artifact registries, pipeline coordination |
| Development | Workload development |
| Staging | Integration/performance testing |
| Production | Production workloads and critical data |
| Security / Log Archive | Central auditing, CloudTrail, security tooling |

The goal is for pipelines to deploy to the right workload account without holding an organization-wide admin credential.

### 4.1. Model A — Direct OIDC into Each Target Account

~~~mermaid
flowchart TD
    CI["GitHub Actions / GitLab CI"]
    CI -->|"OIDC JWT"| DEV["AWS Dev account<br/>OIDC provider + DevDeployRole"]
    CI -->|"OIDC JWT"| STG["AWS Staging account<br/>OIDC provider + StagingDeployRole"]
    CI -->|"OIDC JWT"| PROD["AWS Production account<br/>OIDC provider + ProdDeployRole"]
    DEV --> DRES["Dev resources"]
    STG --> SRES["Staging resources"]
    PROD --> PRES["Production resources"]
~~~

Per account:

1. Create an IAM OIDC provider for the same IdP.
2. Create a deploy role with a claim-restricted trust policy.
3. Attach an environment-specific permissions policy.
4. Provide the role ARN to the corresponding pipeline.

Advantages:

- No role chaining.
- Trust policies and permission scopes live directly in the target account.
- Clear role separation across Dev/Staging/Production.

Trade-offs:

- Must create and manage an OIDC provider in every account.
- Trust/IdP configurations must stay synchronized if issuer or audience changes.
- Managing many accounts can duplicate similar policies; use IaC modules and AWS Organizations governance.

### 4.2. Model B — Hub-and-Spoke via Tooling Account

~~~mermaid
flowchart TD
    CI["External CI runner"] -->|"OIDC token"| IDP["Tooling account<br/>OIDC provider"]
    IDP --> HUB["CICD-FederationRole"]
    HUB -->|"sts:AssumeRole"| DEV["Dev DeploymentRole"]
    HUB -->|"sts:AssumeRole"| STG["Staging DeploymentRole"]
    HUB -->|"sts:AssumeRole"| PROD["Production DeploymentRole"]
    DEV --> D["Dev resources"]
    STG --> S["Staging resources"]
    PROD --> P["Production resources"]
~~~

This model has two steps:

1. External CI assumes `CICD-FederationRole` in the tooling account via `AssumeRoleWithWebIdentity`.
2. The tooling role calls `AssumeRole` into the deployment role in the target account.

The tooling role needs an identity policy permitting `sts:AssumeRole` to the exact target role ARNs. Each target role needs a trust policy permitting the source tooling role. Target roles carry permissions policies scoped to their workload accounts.

Advantages:

- One centralized OIDC provider in the tooling account.
- Centralizes onboarding and audit entry points.
- Can separate bootstrap, release, and deployment permissions by team.

Trade-offs:

- Adds an extra role assumption hop.
- Both source policy and target trust policy must be managed in sync.
- Role chaining caps sessions at a maximum of one hour; plan deployment durations and credential refreshes accordingly.
- If the tooling role is compromised, its blast radius spans the target roles it is allowed to assume.

### 4.3. Choosing a Model

| Criterion | Direct OIDC per account | Hub-and-spoke |
|---|---|---|
| Number of OIDC providers | One per federated account | One in the tooling account |
| Role assumption hops | One | Two |
| Central governance | IaC/modules synchronized across accounts | Centralized source role |
| Session duration | Per OIDC role max duration | Second hop capped at 1 hour |
| Blast radius | Scoped to each account's role | Scoped to target role ARNs assumable by hub |
| Best fit | Fewer accounts or strict trust isolation | Many accounts wanting centralized CI federation |

No single model fits every organization. Choose based on account count, trust boundaries, deployment duration, team ownership, and IAM policy operational maturity.

## 5. Pre-Configuration Checklist for OIDC

Before creating a provider or role, verify:

1. Whether the external IdP is GitHub.com, GitLab.com, GitLab Self-Managed, or another OIDC provider.
2. Exact issuer URL and discovery endpoint, public and served over HTTPS.
3. The audience the job token will carry; this audience must be in the IAM OIDC provider client ID list.
4. Actual `sub` claim of the workflow/job, including repository/project, branch/tag, or environment.
5. Additional claims supported by AWS IAM as condition keys for that IdP.
6. Target AWS account ID and Region; OIDC providers are account-global IAM resources.
7. Role ARN, maximum session duration, and required AWS actions/resources.
8. Which pipeline events may deploy (push to main, protected tag, manual approval, release environment).
9. Whether runners are ephemeral or persistent, with proper isolation and cleanup.
10. Who owns workflow edits, IAM providers, trust policies, and deployment permission changes.

Do not construct `sub` from memory using repo/branch names and assume tokens will match. Check the IdP docs and actual token claim format for the specific repository/project—paying close attention to GitHub immutable subject claims and GitHub Environments.

## 6. Configuring GitHub Actions OIDC with AWS

GitHub Actions provides a dedicated OIDC token per workflow/job. For a job to request a token, the workflow must grant `id-token: write`. This permission only lets the job request an ID token from GitHub; it **does not grant any AWS access by itself**. AWS still decides via the IAM provider, trust policy, and permissions policy.

### 6.1. Creating the GitHub OIDC Provider in an AWS Account

You can create the provider with AWS CLI:

~~~bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
~~~

This is an IAM change and only needs to run once per account using direct OIDC. If the provider already exists, verify its URL and audiences rather than creating a duplicate.

The provider ARN has the form:

~~~text
arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
~~~

### 6.2. GitHub Subject Claims and Immutable IDs

The subject claim depends on workflow context. For repositories created on or after July 15, 2026, repositories opted into immutable subject claims, or older repositories renamed after that milestone, GitHub can emit subjects containing immutable numeric organization and repository IDs. Example format:

~~~text
repo:my-org@123456/my-service@789012:ref:refs/heads/main
~~~

Older repositories that have not opted in may still use the legacy format:

~~~text
repo:my-org/my-service:ref:refs/heads/main
~~~

If a job uses a GitHub Environment, the subject switches to the environment format, for example:

~~~text
repo:my-org@123456/my-service@789012:environment:production
~~~

Therefore, before writing a trust policy, verify the actual subject format in your repository configuration/claims. Do not copy legacy formats for repositories emitting immutable claims; STS will reject the request if `sub` does not match.

### 6.3. Trust Policy Restricting Repository and Branch

Example role assumable only from the `main` branch of a repository emitting immutable subject claims:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustGitHubMainBranch",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:my-org@123456/my-service@789012:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Replace the account ID, organization ID, repository ID, and names with real environment values. If the repository still uses legacy claims, replace `sub` with the verified exact legacy value.

Avoid `StringLike` with `repo:my-org/*` for production deployments without strong justification; that allows multiple repositories in the organization to assume the role. Exact `StringEquals` on repository/branch or environment is usually safer.

### 6.4. Trust Policy When Using GitHub Environments

If the workflow specifies:

~~~yaml
jobs:
  deploy:
    environment: production
~~~

The subject must match the environment name rather than the branch ref:

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
          "token.actions.githubusercontent.com:sub": "repo:my-org@123456/my-service@789012:environment:production"
        }
      }
    }
  ]
}
~~~

When using an Environment, configure protection rules in GitHub: deployment branches/tags, required reviewers, and needed rules. The trust policy validates the subject; Environment protection controls which workflows may enter the environment.

### 6.5. Least-Privilege Permissions Policy for Artifact Upload

Example role permitted only to write objects into one release artifact prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublishReleaseArtifacts",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::company-release-artifacts/apps/my-service/*"
    }
  ]
}
~~~

This is only a simple object upload example. If the pipeline needs multipart uploads, listing, read-after-upload, or KMS encryption, add the exact required actions/resources per actual API calls. If the bucket uses SSE-KMS, the role also needs matching KMS permissions and the key policy must allow the principal. Never attach `AdministratorAccess` just to make a pipeline work.

### 6.6. GitHub Actions Workflow

Example workflow deploying from the `main` branch using `aws-actions/configure-aws-credentials`:

~~~yaml
name: Deploy to AWS

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
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v6.3.0
        with:
          role-to-assume: arn:aws:iam::123456789012:role/GitHubActionsDeployRole
          aws-region: ap-southeast-1
          role-session-name: gha-${{ github.run_id }}

      - name: Verify AWS identity
        run: aws sts get-caller-identity

      - name: Deploy
        run: |
          echo "Run the approved deployment command here"
~~~

In production, pin third-party actions to reviewed full commit SHAs and update them in a controlled manner. The version shown in the example is illustrative; verify the organization-approved release before use. Never run a deploy role on `pull_request` from forks or unprotected workflows.

### 6.7. GitHub Workflows Using Reusable Workflows

If an organization standardizes deployments with reusable workflows, trust can be further restricted using the `job_workflow_ref` claim where supported by GitHub and AWS IAM. This enforces that deployments pass through a reviewed workflow in a central repository rather than trusting any editable workflow in an application repo. Trust conditions must match actual token claims and should not replace repository/environment subject conditions.

## 7. Configuring GitLab CI/CD OIDC with AWS

GitLab CI/CD can issue ID tokens using the `id_tokens` keyword. Use current ID tokens; the legacy `CI_JOB_JWT_V2` variable was removed in GitLab 17.0.

### 7.1. Creating the IAM OIDC Provider

For GitLab.com, the provider URL is:

~~~text
https://gitlab.com
~~~

The audience must align between the GitLab job ID token and the IAM provider client ID list. Example choosing `sts.amazonaws.com`:

~~~bash
aws iam create-open-id-connect-provider \
  --url https://gitlab.com \
  --client-id-list sts.amazonaws.com
~~~

For GitLab Self-Managed/Dedicated, replace the URL with the instance's exact public issuer URL and verify the discovery/JWKS endpoint. AWS must be able to reach issuer metadata and public keys per OIDC requirements.

### 7.2. Trust Policy Restricting Project and Branch

GitLab.com supports additional stable condition keys `namespace_id` and `project_id`. Example trust policy accepting only project ID `67890` in namespace ID `12345` on branch `main`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustGitLabMainProject",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/gitlab.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "gitlab.com:aud": "sts.amazonaws.com",
          "gitlab.com:sub": "project_path:mygroup/myproject:ref_type:branch:ref:main",
          "gitlab.com:namespace_id": "12345",
          "gitlab.com:project_id": "67890"
        }
      }
    }
  ]
}
~~~

`project_id` remains stable even if a project is renamed or moved across namespaces; `namespace_id` changes if a project is transferred to another namespace. These two conditions are GitLab.com features. For GitLab Self-Managed and GitLab Dedicated, supported AWS condition keys in this guide include only `sub` and `aud`; restrict the subject by project/ref and check documentation for your GitLab version.

### 7.3. GitLab CI Job Obtaining Temporary Credentials

Declare the token with the matching audience:

~~~yaml
deploy:
  image:
    name: amazon/aws-cli:2
    entrypoint: [""]
  id_tokens:
    AWS_ID_TOKEN:
      aud: sts.amazonaws.com
  variables:
    AWS_DEFAULT_REGION: ap-southeast-1
  script:
    - |
      set -eu
      TOKEN_FILE="$CI_PROJECT_DIR/web-identity-token"
      trap 'rm -f "$TOKEN_FILE"' EXIT
      printf '%s' "$AWS_ID_TOKEN" > "$TOKEN_FILE"
      chmod 600 "$TOKEN_FILE"

      export AWS_WEB_IDENTITY_TOKEN_FILE="$TOKEN_FILE"
      export AWS_ROLE_SESSION_NAME="gitlab-$CI_PROJECT_ID-$CI_PIPELINE_ID"

      aws sts get-caller-identity
      echo "Run the approved deployment command here"
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

`AWS_ROLE_ARN` is supplied via a GitLab CI/CD variable scoped by project/group/environment. It is not a secret; the role trust policy enforces authorization. AWS CLI uses the web identity token file and role ARN to call STS via the credential provider chain.

The `trap` deletes the token file when the shell exits normally. With persistent runners, add runner/workspace lifecycle cleanup to handle force-canceled jobs and ensure workspace isolation between jobs. Alternatively, invoke `aws sts assume-role-with-web-identity` directly. Either way, never echo the token, print response credentials to logs, or upload the token file as an artifact.

## 8. Cross-Account Role Assumption

Once the pipeline holds credentials in a tooling account or target account, design deployment permissions across account boundaries. Two conditions must both hold:

1. The source principal has an identity policy allowing `sts:AssumeRole` on the target role.
2. The target role trust policy allows the source principal to assume the role.

A policy on only the source side or only the target side is insufficient for cross-account role assumption.

### 8.1. Target Deployment Role in the Workload Account

Example: target account `222222222222` has role `ProdDeploymentRole`. Trust policy for the hub role from tooling account `111111111111`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustToolingFederationRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/CICD-FederationRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

The source role in the tooling account needs an identity policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeProductionDeploymentRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::222222222222:role/ProdDeploymentRole"
    }
  ]
}
~~~

Do not use `Resource: "*"` when the pipeline only needs to deploy into designated accounts/roles. Separate roles per environment and restrict target ARNs to limit the blast radius.

### 8.2. Target Role Permissions Policy

Example: target role allowed to read artifacts from one prefix and update one ECS service. Actual policies must match the deployment tool's API calls and specific resources:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReleaseArtifact",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::company-release-artifacts/apps/my-service/*"
    },
    {
      "Sid": "UpdateSpecificEcsService",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassOnlyApprovedTaskRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::222222222222:role/MyServiceTaskRole",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ecs-tasks.amazonaws.com"
        }
      }
    }
  ]
}
~~~

Some ECS APIs do not support resource-level permissions and require `Resource: "*"`. For actions that support resource scoping, restrict clusters, services, task definitions, and condition keys per the AWS Service Authorization Reference. `iam:PassRole` should allow passing only specific task/execution roles to the exact AWS service; it is a sensitive permission because it can indirectly grant higher privileges to workloads.

### 8.3. GitHub Actions Assuming a Second Role

In hub-and-spoke, the first step assumes the tooling role via OIDC, and the next step assumes the target deployment role using those credentials:

~~~yaml
- name: Assume tooling federation role
  uses: aws-actions/configure-aws-credentials@v6.3.0
  with:
    role-to-assume: arn:aws:iam::111111111111:role/CICD-FederationRole
    aws-region: ap-southeast-1
    role-session-name: gha-tooling-${{ github.run_id }}

- name: Assume production deployment role
  uses: aws-actions/configure-aws-credentials@v6.3.0
  with:
    role-to-assume: arn:aws:iam::222222222222:role/ProdDeploymentRole
    aws-region: ap-southeast-1
    role-session-name: gha-prod-${{ github.run_id }}
    role-chaining: true

- name: Verify target account
  run: aws sts get-caller-identity
~~~

The second action uses credentials from the first role to call `AssumeRole`. The target role's trust policy must trust the source role; the source role's identity policy must allow assuming the target role. If session tagging is configured, add `sts:TagSession` in matching trust/permissions policies or disable session tagging on the chained step per action options.

### 8.4. Session Duration and Role Chaining

- `AssumeRoleWithWebIdentity` defaults to a 1-hour session; you can request from 900 seconds up to the role's maximum session duration, at most 12 hours.
- Standard `AssumeRole` can also issue sessions up to the role's maximum duration.
- When using **role chaining** (a role session assuming a second role), the second session is capped at **1 hour**, regardless of any higher maximum session duration configured on the target role.
- Choose short durations fitting the build/deploy job; avoid 12-hour sessions just in case a job runs long.
- If a job exceeds the limit, redesign the pipeline into shorter stages with explicit credential refresh/re-assumption.

Never pass STS credentials through job outputs, artifacts, or caches to another pipeline. Each new pipeline/job should obtain a fresh OIDC token and assume a role per its trust policy.

### 8.5. Session Policies, Permissions Boundaries, and SCPs

Effective permissions of a role session can be further constrained by session policies, permissions boundaries, and AWS Organizations SCPs. These guardrails **restrict** permissions; they never grant permissions the role does not have.

- Role permissions policy: baseline permissions of the role.
- Session policy: narrows permissions for a specific session at `AssumeRole` time.
- Permissions boundary: caps maximum permissions an identity policy can grant.
- SCP: caps maximum permissions in member accounts; SCPs grant no permissions.
- Resource policy: controls direct access to a resource where supported by the service.

When a pipeline gets `AccessDenied`, inspect the entire policy evaluation path. Never rush to attach `AdministratorAccess` or remove SCPs to bypass an error.

## 9. OIDC and CI Runner Security

OIDC removes long-lived AWS access keys from CI secrets, yet tokens and runners remain credential boundaries. If an untrusted job can request a token or read temporary credentials, an attacker can abuse the role session to execute permitted actions.

### 9.1. Restrict Where OIDC Tokens Can Be Requested

- Grant `id-token: write` only on jobs that need to deploy, never broadly across all jobs unnecessarily.
- Separate build/test jobs running untrusted code from deploy jobs holding AWS access.
- Never grant deployment roles to workflows processing pull requests from forks.
- Enforce protected branches, protected tags, and required reviewers.
- With GitHub Environments, enable protection rules and restrict deployment branches/tags.
- With GitLab, allow deployments only from protected branches/tags and protected environments.
- Restrict trust policies to exact repositories/projects, branches/tags/environments, and stable IDs where supported by the IdP.
- When using reusable workflows, verify `job_workflow_ref`/claims to trust only reviewed workflows.

### 9.2. Protecting Workflows and Third-Party Actions

- Pin actions to reviewed full commit SHAs; version tags can be moved.
- Review permission changes in workflow YAML, especially `id-token: write`, `contents: write`, `packages: write`, and deployment secrets.
- Use dependency pinning, lockfiles, artifact signing/provenance, and vulnerability scanning.
- Never run untrusted pull request code in the same job that has OIDC permissions.
- Avoid `pull_request_target` workflows running fork code with privileged tokens.
- Minimize secrets and permissions per job; do not give build jobs a deployment role.
- Central reusable workflows should be reviewed, versioned/pinned, and maintained by platform/security teams.

### 9.3. Runner Isolation

Runners can read environment variables and files inside a job. If a persistent runner is shared between untrusted jobs and deploy jobs, tokens/credentials may be accessed improperly.

- Prefer ephemeral runners or runner isolation along trust boundaries.
- Never run untrusted fork PRs and production deploys on the same persistent runner.
- Delete workspaces, token files, AWS credential files, and temporary artifacts after each job.
- Never cache `$HOME/.aws`, web identity token files, or credential files.
- Never mount the Docker socket or broad host filesystems into jobs that do not need them.
- Keep runner images updated and restrict outbound networking as required.
- For self-hosted runners, protect the control plane and restrict who can edit runner labels/configs.

### 9.4. Protecting Tokens and Temporary Credentials

- Never echo OIDC JWTs or AWS credentials to logs.
- Never write credentials into GitHub outputs, GitLab artifacts, caches, or build metadata.
- Never pass tokens via job outputs; each job needing an identity should request its own token.
- Use the shortest STS session duration suitable for the deployment.
- Set `role-session-name` traceable to the workflow run/pipeline ID.
- If tokens/credentials are exposed, revoke session/role access per incident procedure and inspect CloudTrail.
- Never put PII inside OIDC `sub`; subjects can appear in CloudTrail logs.

### 9.5. OIDC Does Not Replace Authorization

A token proves a job belongs to an identity authenticated by the IdP. It does not prove an artifact is safe, code was reviewed, or pipeline logic is benign. Add:

- Branch protection and code owner reviews for workflow files.
- Required deployment approvals for production.
- Policy-as-code checks on IAM/network/storage configurations.
- Artifact signing, provenance verification, and immutable release tags.
- Separation of duties between code mergers and production approvers.
- CloudTrail monitoring for STS assumptions and sensitive AWS API calls.

## 10. Cross-Account Artifact and Resource Access

Cross-account deployment is more than assuming a role. Artifacts, container images, KMS keys, and deployment targets may reside in different accounts; each resource boundary needs proper authorization.

### 10.1. S3 Artifact Bucket in a Central Account

Suppose a deployment role in account `222222222222` needs to read artifacts from bucket `company-release-artifacts` in account `111111111111`.

Both are required:

1. The deployment role's identity policy permits `s3:GetObject` on the object ARN/prefix.
2. The bucket policy in the bucket-owning account permits that exact deployment role principal to read that prefix.

Example bucket policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowProductionDeploymentRead",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::222222222222:role/ProdDeploymentRole"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-release-artifacts/apps/my-service/*"
    }
  ]
}
~~~

Never make a bucket public for CI/CD artifact reads. If objects use SSE-KMS, both the KMS key policy and IAM KMS permissions must allow the target role to decrypt. An S3 bucket policy does not replace a KMS key policy.

### 10.2. ECR Images in Another Account

If images are published in a tooling account and pulled by a workload account:

- The ECR repository policy must permit the target principals/actions needed.
- For ECS, the task execution role needs ECR pull permissions; for EKS, grant permissions to the node role or workload identity per the cluster's image pull mechanism.
- If the pipeline pushes images, the publish role needs ECR upload actions and `ecr:GetAuthorizationToken`.
- Do not grant repository/image delete permissions if the release workflow does not need them.
- Pin images by digest during deployment to avoid tag mutation between build and deploy.

### 10.3. KMS Keys and Secret Access

If a pipeline must read secrets or use KMS keys in another account:

- Source/target role identity policies must allow the required actions.
- KMS key policies or resource policies must allow the cross-account principal.
- Secrets Manager resource policies must restrict role ARNs, secret ARNs, and required conditions.
- Never pass plaintext secrets via workflow outputs or artifacts.
- Grant secret read access only to deploy jobs that truly need it; build/test jobs usually do not need production secrets.

### 10.4. Do Not Confuse ExternalId with OIDC

`sts:ExternalId` is commonly used in cross-account access when a third-party service assumes a role via `sts:AssumeRole`, specifically to mitigate confused-deputy risk. With OIDC web identity, AWS verifies the token's issuer/audience/subject via `AssumeRoleWithWebIdentity`; `ExternalId` does not replace those claim conditions.

If a pipeline performs a second-hop `AssumeRole`, the target role trust policy checks the source IAM role principal and can include conditions suited to the use case. Do not add `ExternalId` out of habit unless your threat model and caller contract require it.

## 11. Auditing, Observability, and Governance

OIDC ties AWS access to a workflow identity. Retain enough information to trace every deployment back to repository/project, commit, actor, and pipeline run.

### 11.1. CloudTrail and STS Events

Monitor STS federation events such as `AssumeRoleWithWebIdentity` and cross-account `AssumeRole`. CloudTrail helps determine:

- Which role was assumed and in which account.
- Timestamp and source context of the request.
- Role session name and assumed role ARN.
- Subsequent AWS API calls executed by the role session.
- Error codes when STS rejects a token or trust evaluation.

Include a run/pipeline ID in `role-session-name` (without secrets or PII) to correlate CI runs with CloudTrail. With GitHub, `github.run_id` is often useful; with GitLab, use project/pipeline IDs.

### 11.2. Checking Caller Identity in the Pipeline

After obtaining credentials, run:

~~~bash
aws sts get-caller-identity
~~~

This returns the account ID, ARN, and user ID of the active principal. In cross-account flows, verify the account ID matches the intended target account before running deployment commands. Fail fast if the account is outside the environment's allowlist.

### 11.3. Metrics and Alerts

| Signal | Objective |
|---|---|
| STS `AssumeRoleWithWebIdentity` success/failure | Detect trust policy/token errors or abuse |
| `AssumeRole` into production outside release windows | Detect abnormal role usage |
| Sensitive API calls outside deployment roles | Detect changes made outside pipelines |
| Sudden spike in `AccessDenied` | Spot permission drift or credential misuse |
| Workflow deploy from non-allowlisted branch/tag | Detect invalid release paths |
| Runner job duration and credential expiration | Detect jobs exceeding session lifetimes |
| OIDC provider/role trust policy changes | Audit changes to federation boundaries |

Build alerts using CloudTrail, EventBridge, CloudWatch alarms, centralized log archives, and security findings. Do not alert solely on STS event counts while ignoring principal, account, repository/project, and environment context.

### 11.4. Onboarding and Decommissioning

Every OIDC deployment role needs owner metadata:

- IdP/provider URL and audience.
- Repository/project IDs and trusted branches/environments.
- AWS account, role ARN, and permissions owner.
- CI workflow/reusable workflow owner.
- Maximum session duration and expected job duration.
- Last-used/CloudTrail review, ticket, and approval.
- Contact/expiry for temporary roles.

When a repository/project is archived, renamed, transferred, or migrated:

1. Confirm the new job and new trust claims.
2. Update the trust policy through change review.
3. Test STS assumption on a sandbox or non-production role.
4. Switch the workflow and verify CloudTrail/caller identity.
5. Remove the old subject/role access once migration completes.
6. Decommission unused providers/roles per dependency inventory.

## 12. Troubleshooting OIDC and Cross-Account Deployments

| Symptom | Possible cause | Where to check |
|---|---|---|
| `InvalidIdentityToken` | Invalid issuer, signature, JWKS, audience, or expired token | Provider URL, discovery document, JWKS, `aud`, clock, and token lifetime |
| `IDPRejectedClaim` | IdP rejected claim or claim failed requirements | Subject/ref/environment, protected branch, GitLab project/namespace IDs |
| `AccessDenied` on `AssumeRoleWithWebIdentity` | Trust policy mismatch, wrong provider ARN, or missing required condition | Federated principal, `aud`, `sub`, provider account, role trust |
| No OpenIDConnect provider found | Provider not created in the role's account or wrong ARN | `list-open-id-connect-providers`, provider ARN, and target account |
| GitHub role assumption fails after repo rename | Subject claim switched to immutable ID format or Environment | Inspect actual `sub`, organization/repository IDs, and environment name |
| GitHub job has no token | Job lacks `id-token: write` or action runs in unsupported context | Workflow/job permissions, trigger, and job context |
| GitLab job cannot get token | Legacy JWT variable used, wrong `id_tokens` audience, or runner config | GitLab version, ID token declaration, `aud`, and issuer |
| Second-hop `AssumeRole` `AccessDenied` | Source role lacks `sts:AssumeRole` or target trust excludes source role | Source identity policy, target trust policy, SCPs/permissions boundaries |
| Deploy role assumed but AWS API denied | Insufficient permissions policy or resource policy | Action, resource ARN, bucket/ECR/KMS policy, `iam:PassRole` |
| Job credentials expire mid-deploy | Short session duration or 1-hour role chaining cap | STS expiration, job duration, role chain, and re-assume design |
| Cross-account S3 `GetObject` denied | Missing identity policy, bucket policy, or KMS key policy | All three policy boundaries and object encryption |
| OIDC provider works in Dev but fails in Prod | Provider exists in only one account, or trust policies differ | Provider in same account as role, IaC drift, and trust conditions |

### 12.1. Inspecting OIDC Providers

~~~bash
aws iam list-open-id-connect-providers

aws iam get-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
~~~

Verify provider URL, client ID list/audiences, and active account. An IAM OIDC provider is an account-level resource; do not assume a provider in the tooling account automatically works in target accounts.

### 12.2. Inspecting Roles and Caller Identity

~~~bash
aws iam get-role \
  --role-name GitHubActionsDeployRole

aws sts get-caller-identity
~~~

Inspect the trust policy and attached permissions policies. When `get-caller-identity` succeeds, verify account ID/ARN before calling deployment APIs.

### 12.3. Inspecting Discovery Documents

An OIDC discovery document lives at `/.well-known/openid-configuration` on the issuer. Examples:

~~~bash
curl -sS https://token.actions.githubusercontent.com/.well-known/openid-configuration
curl -sS https://gitlab.com/.well-known/openid-configuration
~~~

Compare `issuer`, `jwks_uri`, and audience against IdP documentation. AWS needs public endpoint access to verify JWTs; for private/self-managed IdPs, follow the corresponding integration guide instead of exposing endpoints uncontrollably.

### 12.4. Investigating CloudTrail

Search STS federation events in CloudTrail Event history:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --max-results 20

aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --max-results 20
~~~

Inspect error codes, role ARNs, principal/session context, and timestamps. Never print tokens or temporary credentials from CI logs while debugging.

### 12.5. Distinguishing Trust Errors from Permission Errors

- STS role assumption fails: check issuer/provider, audience, subject, trust policy, and source identity.
- STS succeeds but service API fails: check role permissions, session policy, resource policy, permissions boundary, SCP, KMS, and VPC endpoint policy.
- Second-hop `AssumeRole` fails: check source role identity policy and target role trust policy.
- `iam:PassRole` fails: verify role ARN, `iam:PassedToService`, and resource scope.

Never fix a trust error by changing the role's permissions policy. Those two policies govern two separate authorization steps.

## 13. Incident Response When an OIDC Role Is Compromised

If an untrusted workflow or runner is discovered to have assumed a deployment role:

1. Identify the role ARN, AWS account, Region, CloudTrail events, and session timestamps.
2. Disable or narrow the trust policy to stop new tokens from assuming the role; apply deny/permission reductions per incident plan.
3. Pause the pipeline/workflow and isolate the suspected runner.
4. Identify the repository/project, workflow file, branch/tag/environment, actor, and commit involved.
5. Inspect CloudTrail API calls following the STS assume event; identify resources read, modified, or deleted.
6. Revoke active sessions using the appropriate IAM role session revocation mechanism; note that editing a trust policy does not immediately invalidate all already-issued credentials.
7. Rotate/revoke application secrets or downstream credentials if the pipeline could access them.
8. Restore resources, inspect artifacts/images, and publish clean builds if needed.
9. Fix trust policies, permissions, workflows, runner isolation, and dependency pins.
10. Re-enable the pipeline only after testing OIDC and cross-account access in non-production.

Preserve audit evidence per incident retention policy. Never delete CloudTrail logs, runner logs, or related artifacts before investigation concludes.

## 14. Hands-On Labs on AWS Sandbox

### 14.1. Lab A — GitHub Actions Direct OIDC

1. Create a GitHub OIDC provider in an AWS sandbox account.
2. Create a role trusting only one repository and branch with a verified subject claim.
3. Attach a policy permitting artifact writes only to one S3 prefix.
4. Create a GitHub workflow with job-level `id-token: write`.
5. Use `configure-aws-credentials` to assume the role.
6. Run `aws sts get-caller-identity` and verify account/role ARN.
7. Upload a test artifact to the allowed prefix; attempt writing to another prefix to confirm denial.
8. Inspect the CloudTrail event and role session name.

### 14.2. Lab B — GitLab CI OIDC

1. Create a GitLab OIDC provider in an AWS sandbox account.
2. Choose an audience and add it to the IAM provider client ID list.
3. Create a role trust policy restricting project, namespace/project IDs, and branch `main` (if GitLab.com).
4. Create a CI job with `id_tokens` and the matching audience.
5. Configure `AWS_ROLE_ARN` and the web identity token file.
6. Run `aws sts get-caller-identity`.
7. Trigger the pipeline from an untrusted branch and observe STS denial.

### 14.3. Lab C — Hub-and-Spoke Cross-Account

1. Create an OIDC provider and `CICD-FederationRole` in the tooling account.
2. Restrict the trust policy to the repo/project and production branch/environment.
3. Attach a source identity policy allowing assumption of only designated Dev/Staging/Prod role ARNs.
4. Create target roles in Dev/Staging/Prod accounts trusting the source role.
5. Attach different permissions policies for each target environment.
6. Use GitHub Actions to assume the tooling role and then assume the target role.
7. Verify the account ID after each hop.
8. Measure job duration and ensure role chaining stays within one hour.

### 14.4. Lab D — Cross-Account Artifact Bucket

1. Place the S3 artifact bucket in the tooling account.
2. Create a deploy role in the workload account.
3. Grant an identity policy allowing `s3:GetObject` on the required read prefix.
4. Grant a bucket policy allowing that exact role ARN.
5. If using SSE-KMS, add matching KMS key policy/permissions.
6. Test `GetObject` in a deployment job; attempt reading another prefix to confirm denial.

### 14.5. Lab E — Negative Security Tests

Test the following cases in sandbox:

- Change `aud` in the job token.
- Switch branch/ref away from the trusted branch.
- Test from a different repo/project.
- Test with an untrusted GitHub Environment.
- Temporarily remove `id-token: write` from the job.
- Attempt assuming a target role not granted `sts:AssumeRole` on the source role.
- Attempt calling a service action outside the permissions policy.
- Attempt role chaining with a session duration exceeding one hour.

Record the error code and policy condition causing each denial. Negative tests confirm trust policies actually enforce boundaries.

## 15. Review Checklist for OIDC and Cross-Account CI/CD

### Identity Provider and Trust

- [ ] Is the issuer URL exact, HTTPS, with valid discovery/JWKS endpoints?
- [ ] Does the audience match between the CI ID token and IAM provider?
- [ ] Does the OIDC provider reside in the same account as roles directly trusting it?
- [ ] Does the trust policy enforce exact `aud` and `sub` restrictions?
- [ ] Was the GitHub subject claim verified for immutable IDs/Environment format?
- [ ] For GitLab.com, are `project_id`/`namespace_id` pinned when appropriate?
- [ ] Does self-managed GitLab use the exact issuer and AWS-supported claims?
- [ ] Are overly broad wildcards and empty subjects avoided?

### Permissions and Account Boundaries

- [ ] Do role permissions follow least privilege and resource ARNs/prefixes?
- [ ] Does the source role have `sts:AssumeRole` scoped to exact target ARNs?
- [ ] Does the target trust policy trust only the required source role?
- [ ] Is `iam:PassRole` scoped to specific roles and services?
- [ ] Do bucket/ECR/KMS resource policies allow the exact target principal?
- [ ] Are session policies, permissions boundaries, and SCPs accounted for?
- [ ] Do role chaining and session durations fit job execution time?

### CI Workflow and Runners

- [ ] Is `id-token: write` granted only to jobs that need it?
- [ ] Are workflow files protected by branch protection/code review?
- [ ] Does the Production Environment require reviewers/protection rules?
- [ ] Are untrusted fork PRs prevented from running in jobs with AWS roles?
- [ ] Are third-party actions pinned and reviewed?
- [ ] Are runner isolation and ephemeral cleanup adequate?
- [ ] Are tokens/credentials kept out of logs, artifacts, caches, and outputs?

### Auditing and Operations

- [ ] Can `role-session-name` correlate with workflow run/pipeline IDs?
- [ ] Does CloudTrail capture STS events and sensitive API calls?
- [ ] Are alerts configured for abnormal role assumptions and trust policy changes?
- [ ] Do roles/providers have owners, tickets, expirations, and decommission workflows?
- [ ] Do incident runbooks cover handling active role sessions?
- [ ] Do negative tests verify unauthorized branches/repos/audiences are denied?

## 16. Self-Assessment Questions

1. What problem does OIDC federation solve in CI/CD?
2. How does an OIDC ID token differ from AWS STS temporary credentials?
3. What roles do the `iss`, `aud`, and `sub` claims play?
4. What information does AWS use to verify an OIDC token?
5. What does an IAM OIDC provider describe?
6. How does a trust policy differ from a permissions policy?
7. Why must a trust policy restrict `sub`?
8. What does `id-token: write` in GitHub Actions grant, and what does it not grant?
9. Why might a GitHub subject claim contain organization/repository IDs?
10. How does a GitHub Environment change the subject claim?
11. Why are environment protection rules needed alongside an IAM trust policy?
12. Which keyword declares a GitLab ID token?
13. Why should the `CI_JOB_JWT_V2` variable no longer be used?
14. What are `project_id` and `namespace_id` condition keys used for on GitLab.com?
15. Does GitLab Self-Managed share the exact same AWS condition keys as GitLab.com?
16. Why must an IAM OIDC provider reside in the same account as the role trusting it?
17. How does direct per-account OIDC differ from hub-and-spoke?
18. Which policies are needed on source and target for cross-account `AssumeRole`?
19. Why is `sts:AssumeRole` insufficient if the target trust policy does not allow the source role?
20. What is the maximum session duration under role chaining?
21. Does `sts:ExternalId` replace OIDC subject/audience conditions?
22. When is `iam:PassRole` required in an ECS deployment?
23. Why does `iam:PassRole` require strict resource and service conditions?
24. What identity policy and bucket policy are required for cross-account S3 `GetObject`?
25. If an S3 artifact uses SSE-KMS, what else must be checked?
26. Can an SCP grant permissions to a role session?
27. Why should `id-token: write` not be granted to every job?
28. Why is sharing a persistent runner between untrusted PRs and deploy jobs dangerous?
29. How does CloudTrail help correlate OIDC workflows with AWS API calls?
30. When a token is exposed, which layers must be addressed?
31. Why does updating a trust policy not immediately invalidate all active credentials?
32. Which negative tests confirm a trust policy is not overly broad?

### Answer Guidelines

- **Identity:** IdP issues a JWT; AWS STS verifies it and issues temporary credentials.
- **Trust:** Provider defines the issuer; trust policy restricts principals/claims; permissions policy restricts AWS actions/resources.
- **GitHub/GitLab:** Audience must match, and subject must restrict repository/project/ref/environment; verify GitHub immutable subjects and GitLab stable project IDs.
- **Cross-account:** Direct federation creates a provider in each account with a role; hub-and-spoke uses OIDC into a tooling role and `AssumeRole` into target roles.
- **Security:** Least privilege, protected branches/environments, ephemeral runners, action pinning, and no logging of tokens/credentials.
- **Audit:** CloudTrail STS events, role session names, caller identity checks, and negative tests verify access paths.

## 17. Official AWS, GitHub, and GitLab Documentation

1. [AWS IAM: Create an OpenID Connect identity provider](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — Provider URL, discovery document, JWKS, audiences, and IAM provider setup.
2. [AWS IAM: Create a role for OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html) — Trust policy and OIDC role configuration.
3. [AWS IAM: Available keys for AWS OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html) — OIDC claims and condition keys.
4. [AWS STS: AssumeRoleWithWebIdentity API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html) — Web identity token validation and temporary credentials.
5. [AWS STS: AssumeRole API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html) — Cross-account role assumption and role chaining.
6. [AWS IAM: Cross-account resource access](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies-cross-account-resource-access.html) — Source identity policy and target trust policy.
7. [AWS IAM: Role chaining](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html) — Session duration and role chaining constraints.
8. [AWS IAM: Secure-by-default controls for shared OIDC providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc_secure-by-default.html) — Required identity-provider claim controls.
9. [AWS IAM: Create and manage OIDC identity providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — Provider audiences and certificate verification.
10. [AWS CloudTrail user guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — STS and AWS API auditing.
11. [GitHub Docs: Configuring OpenID Connect in AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) — GitHub issuer, audience, claims, and trust policy.
12. [GitHub Docs: OIDC claims and scoping permissions](https://docs.github.com/en/actions/concepts/security/openid-connect) — Workflow identity and token claims.
13. [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) — Current GitHub Action usage, OIDC setup, role chaining, and options.
14. [GitLab Docs: Configure OpenID Connect in AWS](https://docs.gitlab.com/ci/cloud_services/aws/) — GitLab ID tokens, AWS provider, trust policy, and temporary credentials.
15. [GitLab Docs: ID token authentication](https://docs.gitlab.com/ci/secrets/id_token_authentication/) — ID token configuration and audience.
16. [GitLab Docs: Connect to cloud services](https://docs.gitlab.com/ci/cloud_services/) — Cloud federation and claim restrictions.
17. [AWS IAM: IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — Identity, resource, boundary, and organization policy evaluation.
18. [AWS IAM: PassRole](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html) — Securely passing a role to an AWS service.

> **Final takeaway:** OIDC lets external CI obtain temporary AWS credentials without storing long-lived access keys. Trust policies must restrict the exact issuer, audience, and subject; permissions policies must restrict actions and resources. For multiple AWS accounts, choose direct OIDC or hub-and-spoke, verifying source/target trust and session durations. Protect workflows, runners, artifacts, and CloudTrail auditing so every deployment is traceable with a bounded blast radius.
