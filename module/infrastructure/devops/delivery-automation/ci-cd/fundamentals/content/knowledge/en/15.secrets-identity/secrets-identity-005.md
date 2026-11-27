# Introduction to OIDC and Workload Identity Federation

A CI/CD pipeline often needs to access external services to download dependencies, push container images, store artifacts, deploy applications, or read secrets. The legacy approach stores long-lived access keys, passwords, or client secrets in CI configuration and supplies them to jobs at runtime. If a credential leaks in logs, scripts, or runners, unauthorized parties can continue using it until it is revoked or expires.

**OpenID Connect (OIDC)** allows a workload to prove its identity to a target service using a token issued by an identity provider. In CI/CD, the CI system can issue a short-lived OIDC token to a job. The target service validates the token and its claims, then grants temporary access only to trusted repositories, workflows, branches, or environments.

This approach is commonly called **workload identity federation**. The pipeline does not need to keep a shared long-lived credential for the target service. Access is governed by the trust relationship between the issuer, the claims inside the token, and the receiving service's policy.

## 1. What Is OIDC?

OIDC is an identity layer built on top of OAuth 2.0. It standardizes how a token issuer describes an identity and how a recipient verifies that identity. In many CI/CD flows, the issued token is a JSON Web Token (JWT) containing claims about issuer, subject, audience, and expiration.

Common claims:

| Claim | Meaning | Role in Identity Federation |
|---|---|---|
| `iss` | Issuer, the organization or service issuing the token | Identifies the trusted identity source |
| `sub` | Subject, the entity represented by the token | Distinguishes repository, workflow, branch, or environment per issuer rules |
| `aud` | Audience, the intended recipient of the token | Prevents the token from being reused against a different service |
| `exp` | Token expiration timestamp | Limits the usage window |
| `iat` | Token issuance timestamp | Verifies freshness and aids investigation |
| `nbf` | Not-before timestamp | Prevents using the token before it becomes valid |
| `jti` | Token identifier if provided by the issuer | Supports logging and token usage tracking |

Issuers may include additional claims such as repository, organization, branch/ref, commit SHA, workflow, environment, or actor. The target service should rely only on claims that the issuer guarantees and that the receiving platform actually verifies.

### An OIDC Token Is Not an All-Powerful Credential

An OIDC token is proof of identity issued by an issuer. It does not automatically grant permission to read buckets, push images, or deploy to production. The target service must enforce its own trust configuration and authorization policy:

1. The token comes from an accepted issuer.
2. The token is intended for the exact audience.
3. The subject and claims satisfy trust conditions.
4. The token is currently valid and has a valid signature.
5. The verified identity maps to a principal or role.
6. The principal can perform only its granted actions.

Therefore, distinguish **authentication** from **authorization**. OIDC answers who the workload is; the target service's policy decides what the workload is allowed to do.

## 2. Why Should CI/CD Use Workload Identity Federation?

Long-lived credentials create management overhead:

- Secrets must be generated, stored, distributed, and rotated.
- Secrets can be copied across multiple repositories or environments.
- It is hard to pinpoint which exact job used a shared credential.
- Leaked credentials remain usable outside pipeline execution windows.
- A hijacked runner or workflow can expose multiple services at once.

With OIDC federation, a job requests a token when needed, exchanges it for short-lived access, and completes its work. The target service checks identity via claims rather than relying on a static secret string stored in CI.

Key benefits:

| Benefit | Practical Impact |
|---|---|
| No need to store long-lived shared secrets | Reduces the number of stealable credentials |
| Short-lived tokens | Limits the exploitation window if a token leaks |
| Claim-based trust policies | Restricts repository, branch, workflow, or environment |
| Temporary permissions | Issues short-lived roles or credentials per task |
| Traceability | Logs from issuer, STS, and target service identify the workload |
| Environment isolation | Production jobs can have a separate identity from test jobs |

OIDC does not eliminate all secrets. Some services still require dedicated secrets, signing keys, or sensitive configuration data. The goal is to avoid long-lived credentials whenever a service supports workload authentication via federation.

## 3. Components in an OIDC Flow

A typical CI/CD flow includes:

- **Workload:** the job or runner executing the build/deploy.
- **OIDC issuer:** the CI platform issuing tokens and publishing public keys to verify signatures.
- **OIDC token:** the JWT representing the workload in a specific context.
- **Federation endpoint or STS:** the service accepting the token and exchanging it for temporary access.
- **Trust policy:** conditions defining which issuer, audience, subject, and claims are accepted.
- **Target service:** the destination service the job accesses, such as a cloud API, registry, Vault, or Kubernetes API.
- **Role/service account:** the identity mapped after token verification.

General flow:

~~~text
CI job
  |
  | 1. Request OIDC token
  v
OIDC issuer
  |
  | 2. Issue signed JWT
  v
CI job
  |
  | 3. Send token to federation endpoint / STS
  v
Target identity service
  |
  | 4. Verify signature, issuer, audience,
  |    subject, expiration, and trust policy
  v
Role / service account
  |
  | 5. Issue temporary credential or token
  v
Target service
  |
  | 6. Perform action within permission scope
  v
Artifact / cloud resource / deployment target
~~~

Some platforms combine federation and credential issuance into a single API. Others use a separate identity mapping step. Regardless of implementation, the target service must verify the token before granting permissions.

## 4. How Tokens Are Verified

A JWT typically consists of a header, payload, and signature. The payload can be decoded by anyone holding the token, so never treat JWT contents as secret. The signature allows the recipient to verify that the token was issued by the corresponding issuer and has not been tampered with.

Verification typically includes:

1. Reading the issuer from the `iss` claim and matching it against configured issuers.
2. Fetching the matching public key from the issuer's JWKS endpoint or trusted key set.
3. Verifying the signature using an accepted algorithm.
4. Checking that `audience` matches the receiving service.
5. Checking expiration `exp`, not-before `nbf`, and related time conditions.
6. Evaluating `subject` and other claims against the trust policy.
7. Mapping the valid identity to a role, service account, or principal.

Issuers typically publish OIDC discovery metadata and JWKS so recipients can locate endpoints and public keys. Target services must handle key rotation and key caching properly. Never trust a JWT merely because its payload contains a repository name or plausible-looking claims.

### The First Three Fields to Check

**Issuer (`iss`)** answers: which system issued the token? Trust only the explicitly configured issuer—never accept an arbitrary URL supplied by the request.

**Audience (`aud`)** answers: which service was the token issued for? A token intended for AWS STS must not be accepted by another service if that service is not the intended audience.

**Subject (`sub`)** answers: which workload does the token represent? The subject should be narrow enough to distinguish the repository and allowed context, such as a specific branch or environment.

### Token Lifetime and System Clocks

Tokens carry `exp` and may carry `nbf`. CI runners and verification services must keep their clocks reasonably synchronized. Clock skew can cause a token to be rejected even when the workflow just requested it. Do not fix this by disabling expiration checks; fix time synchronization and configure acceptable clock skew within service limits.

Short-lived tokens limit the window of abuse if leaked, but they do not replace protecting runners and logs. An attacker controlling a running job can request new tokens for as long as the job retains permission.

## 5. Binding Identity to Repository, Branch, and Environment

An overly broad trust policy can allow unrelated workflows to assume the same role. For example, checking only the GitHub Actions issuer without restricting the subject can trust every repository or every branch under that issuer, depending on provider configuration.

Select claims aligned with trust boundaries:

| Context | Usable Condition |
|---|---|
| A single repository | Repository owner and repository name |
| A single branch | Repository and specific ref, e.g., `refs/heads/main` |
| A release tag | Repository and allowed tag pattern |
| An environment | Repository and environment name |
| A reusable workflow | Workflow reference or dedicated claim if supported by issuer |
| An organization | Organization claim, combined with repository and ref restrictions |

Restricting only by organization is rarely sufficient when not every repository in the organization should deploy to production. Choose the narrowest condition matching your operations.

### Subject Depends on Issuer Configuration

Subject formats differ across identity providers. In GitHub Actions, the default subject typically contains the repository and ref; if a job references a GitHub Environment, the subject may contain the environment name instead of the ref. GitHub also supports customizing the subject template in certain configurations.

Therefore, inspect actual token claims or issuer documentation before writing trust policies. Never guess a subject from branch or environment names without verifying the exact emitted format.

### Using Protected Environments for Production

A workflow can require a GitHub Environment named `production` before running deployment steps. The environment can enforce reviewers, branch/tag restrictions, and other protection rules. The target service's trust policy can accept only subjects tied to that environment.

When using environments as a boundary, ensure:

- Only allowed branches/tags can reference the environment.
- Reviewers and approval rules are configured on the repository.
- Only jobs requiring production access have permission to request OIDC tokens.
- The production role follows least privilege and is never used by test jobs.

The environment name is part of the subject per issuer rules; by itself, it does not guarantee approvals took place if the environment configuration does not require approvals.

## 6. Example: GitHub Actions Requesting an OIDC Token

GitHub Actions uses the OIDC issuer URL:

~~~text
https://token.actions.githubusercontent.com
~~~

A job needing to request an ID token must be granted `id-token: write`. This permission allows the job to request a token from GitHub; it does not automatically grant access to AWS, Azure, GCP, or other services. Actual permissions depend on the target trust policy and role/service account.

Example workflow allowing deployment jobs to run only from the `main` branch:

~~~yaml
name: Deploy

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
        uses: actions/checkout@v4

      - name: Authenticate to target service
        run: |
          echo "Use the provider-specific OIDC action or SDK here."

      - name: Deploy
        run: ./scripts/deploy.sh
~~~

This is an illustrative workflow skeleton. Replace the authentication step with the official action or SDK of the target provider. In release repositories, pin actions to full commit SHAs per organizational policy, review action permissions, and scope token permissions strictly to the job that needs them.

### Scoping Permissions at the Job Level

Do not grant `id-token: write` to all jobs just because one deploy job needs it. Placing the permission on the deploy job limits scope. Jobs running tests, linting, or pull requests that do not need production access should not have permission to request tokens for that service.

## 7. Example: GitHub Actions Federating with an AWS IAM Role

AWS can trust an OIDC provider and allow workloads to call STS `AssumeRoleWithWebIdentity` to obtain temporary security credentials.

General configuration steps:

1. Create an OIDC identity provider in AWS IAM using the GitHub Actions issuer URL.
2. Configure the allowed audience, typically `sts.amazonaws.com` for AWS STS.
3. Create an IAM role with a trust policy restricting audience and subject.
4. Attach a least-privilege permission policy to the role.
5. In GitHub Actions, request the OIDC token and use the AWS credentials action to assume the role.

Example trust policy restricting repository and the `main` branch:

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
          "token.actions.githubusercontent.com:sub": "repo:acme/payments-api:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Account ID, organization, and repository values are examples. The IAM provider must be created beforehand, and its client ID list must match the audience requested by the workflow. The subject must match the actual token format.

The trust policy determines who can assume the role. The permission policy attached to the role determines what the role can do. Both policies must be reviewed separately. For instance, a deploy role should only update the exact bucket, cluster, or service needed; never attach `AdministratorAccess` just to make a workflow succeed.

A workflow using the AWS credentials action can look like:

~~~yaml
permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/payments-production-deploy
          aws-region: ap-southeast-1

      - name: Verify caller identity
        run: aws sts get-caller-identity

      - name: Deploy
        run: ./scripts/deploy.sh
~~~

This is an illustrative example. In real environments, pin actions by commit SHA, restrict branches/environments, verify the role trust policy, and confirm deploy commands affect only authorized resources. Never store long-lived AWS access keys in repository secrets once OIDC federation meets your requirements.

### When Using GitHub Environments

If a job references the `production` environment, the subject may take the form:

~~~text
repo:acme/payments-api:environment:production
~~~

In that case, the trust policy must match the exact environment-and-repository subject. Because the default subject format may no longer include the branch ref, use environment branch/tag protection rules to constrain deployment sources. Additional claims or custom subject templates can be added if your architecture requires binding multiple attributes.

## 8. Federating with Google Cloud and Azure

Cloud providers use different terminology and configurations, yet the core model remains the same: issuer, audience, subject/attributes, trust mapping, and temporary permissions.

### Google Cloud Workload Identity Federation

Google Cloud Workload Identity Federation allows workloads outside Google Cloud to exchange an OIDC token for an identity mapped in a Workload Identity Pool. The workload can then receive direct IAM permissions or impersonate a service account per IAM policy.

Components to configure:

- Workload Identity Pool.
- OIDC provider pointing to the CI issuer.
- Attribute mapping to map token claims to Google attributes.
- Attribute condition to restrict repository, ref, or workflow.
- IAM binding for the allowed principal or service account.

Conceptual mapping example:

~~~text
google.subject = assertion.sub
attribute.repository = assertion.repository
attribute.ref = assertion.ref
~~~

An attribute condition can require an exact repository and the main branch ref. Exact syntax and claims must match the configured provider. Never use a condition checking only organization if multiple repositories in the organization are not authorized to deploy.

Workflows can call the Google Cloud authentication action with the configured workload identity provider and service account. The `id-token: write` permission is still required so GitHub Actions issues the token. The service account should hold only the minimum roles needed for deployment.

### Microsoft Entra ID and Azure

Azure supports federated identity credentials to link a workload's issuer, subject, and audience to an application or managed identity in Microsoft Entra ID. When the token is valid, the workload can acquire an access token for Azure resources without storing a long-lived client secret.

A federated credential must match:

- The CI system's issuer URL.
- The subject representing repository/ref/environment.
- The configured audience for token exchange, typically `api://AzureADTokenExchange` in GitHub Actions flows.

Workflows can use `azure/login` with client ID, tenant ID, and subscription ID; the action uses OIDC when `id-token` permission is granted. Azure role assignments determine which resources the workload is permitted to manage.

Subject and audience must be verified against the actual federated credential. An application with an overly broad federated credential can let unrelated workflows obtain access tokens.

## 9. Using OIDC with Registries, Vault, and Kubernetes

Cloud providers are not the only systems supporting OIDC. Several other services support workload identity as well:

### Container Registries

Registries may accept tokens from an identity provider or accept temporary credentials via cloud identity. CI uses the federated identity to push images into the exact target repository. Restrict push permissions by project or namespace and allow only trusted release workflows.

### Secret Managers or Vault

Vault can validate JWT/OIDC tokens via its auth method, verify issuer, audience, and bound claims, and map them to a Vault role. The role can restrict repository, branch, or workflow and attach policies granting read access only to required secret paths.

Never grant read access to the entire secret store for every job in a repository. Create separate roles with distinct policies for test, staging, and production.

### Kubernetes

Kubernetes can authenticate service account tokens via OIDC in certain architectures, or use cloud workload identity to map Kubernetes service accounts to IAM principals. For CI deploying into clusters, restrict permissions by namespace and Kubernetes RBAC. Tokens with `cluster-admin` privileges must never be granted to routine build workflows.

## 10. Designing Trust Policies with Least Privilege

A sound trust policy constrains both who is trusted and what actions are allowed. Check the following questions:

1. Is the issuer the exact expected CI platform?
2. Is the audience restricted to the exact receiving service?
3. Does the subject restrict to a specific repository?
4. Are branch, tag, or environment constrained?
5. Are reusable workflows or externally called workflows properly identified?
6. Can tokens be issued to fork pull requests or untrusted code?
7. Does the mapped role/service account follow least privilege?
8. Do temporary credentials have an appropriate lifetime?
9. Do logs capture enough information for traceability without exposing tokens?

### Avoiding Overly Broad Wildcards

A condition like `repo:acme/*` can permit every repository in the organization, depending on how the target service evaluates subjects. If only one repository should deploy, restrict to that exact repository. If only the `main` branch is allowed, add a branch/ref condition or use a protected environment.

Wildcards may be necessary in certain multi-repository models, but they must be intentionally designed, inventoried, and reviewed. Never use wildcards as a shortcut to work around configuration errors.

### Separating Roles by Task and Environment

Roles that should be separated:

| Role | Allowed Source | Permissions |
|---|---|---|
| CI read dependencies | Trusted check workflows | Read dependencies or registries |
| Image publisher | Release workflows on protected branches/tags | Push images to a specific repository |
| Staging deployer | Staging workflows | Deploy to staging |
| Production deployer | Production workflows via approved environments | Deploy to production |
| Release signer | Controlled release workflows | Sign artifacts/provenance within scope |

Separating roles prevents a compromised job from automatically gaining access across all environments.

## 11. Protecting Workflows and Runners

OIDC eliminates long-lived credentials, yet it does not stop a malicious workflow from requesting a token if the job holds that permission. Attackers can modify workflows, inject scripts, swap actions, or exploit runners to abuse trusted identities.

Essential safeguards:

- Grant `id-token: write` only to jobs that genuinely require it.
- Protect branches and workflow files with mandatory reviews.
- Enforce environment protections and reviewers for production.
- Pin third-party actions by full commit SHA and review updates.
- Never run untrusted pull request code in jobs with deploy or production OIDC permissions.
- Avoid using `pull_request_target` to check out and execute fork-controlled code in a high-privilege context.
- Restrict write permissions on `GITHUB_TOKEN` and temporary credentials.
- Use isolated runners for sensitive jobs; avoid sharing self-hosted runners with untrusted workloads.
- Never print JWTs, access tokens, or credential-bearing responses to logs.
- Restrict network egress and host privileges on runners where appropriate.

### Be Careful with Pull Requests from Forks

Pull requests from forks can contain workflow or script changes controlled by external parties. Never grant identities with production permissions to unreviewed code. To validate pull requests, use low-privilege jobs that only build and test in a sandbox; artifact signing and deployment must happen in trusted workflows after changes are accepted.

### Do Not Share Tokens Across Jobs Unnecessarily

OIDC tokens should be requested directly in the job that uses them. Avoid generating a token in one job and passing it through artifacts, outputs, or logs to another job. If another job needs access, give that job its own permissions and trust policy matched to its own identity.

## 12. Lifetime, Scope, and Lifecycle of Temporary Credentials

The OIDC token and the credential exchanged from it may have different lifetimes:

- The OIDC token has an `exp` set by the issuer.
- STS or the cloud provider issues temporary access keys/tokens with their own lifetime.
- The target service may apply additional session policies or session limits.

Do not assume target credentials always expire at the exact same moment as the OIDC token. Check the lifetimes and revocation mechanisms on both sides. Choose durations long enough to finish the task, but no longer than needed.

When workflow compromise is suspected:

1. Disable or narrow the relevant trust relationship.
2. Revoke temporary sessions/credentials if supported by the service.
3. Stop workflows and isolate runners showing signs of compromise.
4. Inspect audit logs across the issuer, STS, and target service.
5. Identify the repository, commit, run ID, and accessed resources.
6. Rotate any other secrets that may have been exposed.
7. Restore a safe trust policy once the root cause is resolved.

Temporary credentials can still be abused while valid. Least privilege, short lifetimes, and audit logs remain critical.

## 13. Troubleshooting OIDC Federation Errors

When token exchange fails, inspect layer by layer instead of immediately loosening the trust policy:

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Unable to obtain token | Job lacks `id-token: write` permission | Check workflow/job permissions and trigger event |
| Issuer mismatch | Wrong issuer URL or provider not registered | Compare `iss` against provider configuration |
| Audience mismatch | Token requested with different `aud` than expected by target service | Check audience in action and trust policy |
| Subject mismatch | Repository, ref, or environment differs from condition | Compare actual `sub` against policy |
| Signature invalid | JWKS/key rotation or token not from trusted issuer | Check discovery/JWKS and token source |
| Token expired/not yet valid | Stale token or clock skew | Request a fresh token and check system time |
| Assume role denied | Trust policy rejects principal or claims | Check provider ARN and trust conditions |
| Access denied after assume | Role authenticated but lacks resource permissions | Check permission policy/RBAC |
| Fails only on environment | Subject changes when job references an environment | Check subject format and protection rules |
| Fails only on pull request | Event or claims differ from branch push | Inspect PR payload and trust boundary |

### Never Solve Errors by Widening Wildcards

If a subject mismatch occurs, first determine which repository, ref, environment, or workflow the token actually represents. Then fix the exact condition. Widening a policy to accept all repositories or all branches may make the pipeline pass, but it introduces over-privileged access.

### Log Enough Without Exposing Tokens

You may log the issuer, audience, non-sensitive subject details, and STS error codes for investigation. Never write full JWTs or access tokens to logs. If you need to inspect claims during debugging, use a test environment, redact sensitive data, and ensure the token is no longer usable.

## 14. Team Rollout Roadmap for OIDC

A controlled rollout approach:

1. **Inventory existing credentials.** Identify repositories, workflows, secrets, and target services using long-lived credentials.
2. **Choose pilot workloads.** Start with a low-risk deploy pipeline or a staging environment.
3. **Register the issuer/provider.** Configure the exact issuer and audience for your CI platform.
4. **Design narrow trust policies.** Constrain repository, branch, workflow, or environment.
5. **Create dedicated roles/service accounts.** Grant least-privilege permissions for the specific task.
6. **Configure jobs to request tokens.** Grant OIDC permission only on jobs that need it and use official actions/SDKs.
7. **Verify identity and permissions.** Run caller-identity checks, test allowed actions, and verify out-of-scope actions are denied.
8. **Enable auditing and alerts.** Monitor token exchanges, role assumptions, and resource access.
9. **Remove legacy long-lived credentials.** Delete them only after the OIDC flow is verified and a rollback plan exists.
10. **Expand by environment.** Create separate identities for staging, production, signing, and other tasks.

Do not migrate every repository at once if trust policies, runners, and approval processes are not yet standardized. Piloting in a small scope helps catch claim mapping and over-permissioning issues before scaling out.

## 15. OIDC Configuration Review Checklist

- [ ] Issuer matches the exact URL of the registered identity provider.
- [ ] Audience is restricted solely to the intended target service.
- [ ] Subject restricts to the exact repository and branch/tag/environment.
- [ ] Claim mappings are verified using real tokens or issuer documentation.
- [ ] Signature, expiration, and key rotation are verified by the target service.
- [ ] Mapped roles/service accounts have only the permissions needed for the task.
- [ ] Temporary credentials have an appropriate lifetime.
- [ ] Only jobs requiring access are granted permission to request tokens.
- [ ] Production workflows enforce branch protection and environment approvals.
- [ ] Untrusted pull requests cannot obtain high-privilege identities.
- [ ] Actions and runners are controlled, and logs contain no tokens.
- [ ] Audit logs suffice to trace issuer, principal, run, and resources.
- [ ] Procedures exist for handling compromised workflows or runners.
- [ ] Old long-lived credentials are removed once federation operates reliably.

OIDC enables CI/CD to prove workload identity per run and receive temporary permissions from target services. When issuer, audience, subject, and trust policies are properly constrained, pipelines can deploy or access resources without storing shared long-lived credentials. Security value comes from the entire chain: protecting workflows and runners, verifying tokens, mapping roles accurately, enforcing least privilege, and logging activity for traceability.
