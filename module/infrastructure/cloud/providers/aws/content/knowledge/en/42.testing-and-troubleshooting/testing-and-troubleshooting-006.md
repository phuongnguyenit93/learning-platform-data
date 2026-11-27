# Diagnosing IAM, STS, and Expired Credential Errors

An application calling AWS APIs must identify **which principal is sending the request**, prove the request is signed with valid credentials, and have sufficient permissions to execute the action on the target resource. Authentication errors typically involve access keys, secret keys, session tokens, credential expiration, or SigV4 signatures. Authorization errors occur when AWS identifies the principal yet policies do not permit the action.

AWS Identity and Access Management (IAM) manages identities and permissions. AWS Security Token Service (AWS STS) issues temporary security credentials so applications, federated users, or workloads can access AWS for a limited duration. Once credentials expire, requests signed with the old credentials are no longer valid. When credentials are valid yet lack permissions, issuing fresh credentials will not resolve an `AccessDenied` error.

This lesson explains how to distinguish between these two error classes, determine the active credential provider, inspect IAM policies and role trusts, handle expired STS sessions, configure automatic credential refreshing in the AWS CLI and AWS SDK for Java 2.x, and build an investigation workflow applicable across EC2, ECS, EKS, Lambda, and CI/CD environments.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish authentication, authorization, IAM principals, and STS sessions.
- Recognize the structure of temporary security credentials and the `Expiration` field.
- Explain how AWS evaluates identity policies, resource policies, trust policies, permissions boundaries, session policies, SCPs, RCPs, and VPC endpoint policies.
- Determine the exact principal used by the AWS CLI or an application.
- Diagnose `ExpiredToken`, `InvalidClientTokenId`, `AccessDenied`, `SignatureDoesNotMatch`, and credential provider chain errors.
- Configure IAM Identity Center, AssumeRole, web identity, instance profiles, and container credentials.
- Use caching and refreshable credential providers in AWS SDK for Java 2.x.
- Investigate failed requests using CloudTrail, IAM Policy Simulator, and authorization details where supported.
- Design secure, self-healing, and auditable credential workflows.

## 1. Authentication and Authorization in an AWS Request

An AWS request typically passes through two logical stages:

1. **Authentication:** AWS verifies which credentials signed the request, whether they are valid, whether the session token is complete, whether the signature matches, and whether the signing timestamp falls within the accepted window.
2. **Authorization:** after identifying the principal, AWS evaluates applicable policies for the action, resource, and request context. Without an allow—or if an explicit deny applies—the request is rejected.

```mermaid
flowchart TD
    A[Application / AWS CLI sends request] --> B[Credential provider fetches credentials]
    B --> C[Sign request with SigV4]
    C --> D{Valid authentication?}
    D -->|No| E[Invalid token / ExpiredToken / Signature error]
    D -->|Yes| F[Identify IAM principal]
    F --> G[Evaluate policies and request context]
    G --> H{Authorization allowed?}
    H -->|No| I[AccessDenied / UnauthorizedOperation]
    H -->|Yes| J[Execute API]
```

For example, if AWS returns `ExpiredToken`, the request failed authentication using temporary credentials. If it returns `AccessDenied` stating `not authorized to perform: s3:GetObject`, the credentials may be completely valid yet the principal lacks read permissions on the object or is blocked by another policy.

Both errors can occur sequentially. An application might first use expired credentials; after successfully refreshing, the next request hits `AccessDenied` because the new role lacks permissions on the bucket. Inspect each layer rather than treating every access error as the same root cause.

## 2. IAM Principals and Temporary Security Credentials

### 2.1 Who Is the Principal?

A principal is the identity making the request. In AWS, a principal is typically:

- An IAM user or IAM role.
- An assumed-role session created via AWS STS.
- A federated user or web identity session.
- An AWS service principal when one service calls another.
- The root principal of an AWS account.

In modern architectures, workloads should use IAM roles and temporary credentials instead of long-term IAM user access keys. For example, EC2 uses instance profiles, ECS uses task roles, EKS uses EKS Pod Identity or IAM Roles for Service Accounts (IRSA), Lambda uses execution roles, and CI/CD pipelines can use OIDC federation.

### 2.2 Credential Structure

A set of temporary security credentials issued by STS has four primary fields:

| Field | Meaning |
|---|---|
| `AccessKeyId` | Access key identifier for the session |
| `SecretAccessKey` | Secret used to compute request signatures |
| `SessionToken` | Additional token proving the credentials belong to a temporary session |
| `Expiration` | Timestamp when credentials expire, typically expressed in UTC |

Example response structure with sensitive values redacted:

```json
{
  "Credentials": {
    "AccessKeyId": "ASIAEXAMPLEACCESSKEY",
    "SecretAccessKey": "REDACTED_SECRET_VALUE",
    "SessionToken": "REDACTED_SESSION_TOKEN",
    "Expiration": "2026-11-20T10:00:00Z"
  }
}
```

The access key ID, secret key, and session token must be used together as a unit. When using temporary credentials, omitting `SessionToken` or mixing a session token from one session with the access key/secret key of another can cause AWS to return `InvalidClientTokenId` or a similar authentication error.

Never write these values to logs, tickets, source control, chat, or screenshots. When sharing investigation logs, keep only the principal ARN, expiration timestamp, profile name, and masked credential portions.

### 2.3 Temporary Credentials vs. Long-Term Access Keys

Long-term IAM user access keys do not have an STS-issued `Expiration` field. Access keys have an Active/Inactive status and can be rotated or deleted. Temporary credentials are dynamically issued, time-limited, and cannot be reused once expired.

Therefore, when encountering expiration errors:

- If the application uses STS/roles/SSO/web identity, refresh the session or restore the credential source.
- If the application uses long-term IAM user access keys, check whether the key is inactive, deleted, rotated, or misconfigured; do not treat it as an STS session.
- Never create new IAM user access keys merely to bypass refreshing temporary credentials.

## 3. AWS STS and Session Duration

AWS STS provides APIs to generate temporary credentials for various scenarios.

| STS API | Use Case |
|---|---|
| `AssumeRole` | Authenticated users or workloads assume an IAM role's permissions, commonly for cross-account access or privilege separation |
| `AssumeRoleWithWebIdentity` | Obtain permissions from an OIDC token, e.g., EKS workloads or CI/CD federation |
| `AssumeRoleWithSAML` | Federate identity via a SAML 2.0 identity provider |
| `GetSessionToken` | Create a temporary session for an IAM user, often used when MFA is required |
| `GetFederationToken` | Create a federated user session via a custom identity broker |

### 3.1 AssumeRole Duration

For `AssumeRole`, `DurationSeconds` can range from 900 seconds (15 minutes) up to the Maximum session duration configured on the role. A role can be configured for up to 12 hours. The default role limit is typically one hour unless changed by an administrator.

**Role chaining** means using temporary credentials from one role session to assume another role. When chaining, the new session is capped at a maximum of one hour, even if the target role allows a longer maximum session duration. Requesting 12 hours in a role chain will be rejected by STS.

For example: a user signs into IAM Identity Center, assumes role `Developer`, and from that session assumes role `ProductionReadOnly`. The second session is role chaining and cannot exceed one hour. Keep role chains short and clear, and let providers refresh automatically while source permissions remain valid.

### 3.2 Expired Credentials Do Not Renew Automatically

STS does not extend an expired credential. The application must request a new session using a credential source that is still valid. If the source is IAM Identity Center, an active login session is required; if the source is an instance profile, the metadata service must be reachable; if the source is OIDC, the token file must be refreshed and the trust relationship must allow role assumption.

A provider can refresh before expiration, yet this works only when:

- The provider knows how to fetch new credentials from the source.
- The source credential or token can still be refreshed.
- The role trust policy and caller permissions still permit creating a new session.
- The application keeps the provider alive rather than replacing it with static credentials.

### 3.3 STS Regions

STS has a global endpoint and regional endpoints. Calling STS in a Region close to your workload reduces latency and aligns with regional operational requirements. Temporary credentials issued by STS can be used to call AWS services globally, subject to policies and service capabilities.

When failures occur in only one Region, check the service request Region, STS endpoint Region, account Region enablement status, and endpoint configuration. Do not confuse the Region used to sign a request with the Region where credentials were issued.

## 4. IAM Policy Evaluation and Sources of AccessDenied

IAM denies requests by default unless explicitly permitted. An `Allow` can permit a request, yet any applicable explicit `Deny` overrides every `Allow`.

### 4.1 Policy Types to Inspect

| Policy | Diagnostic Question | Role |
|---|---|---|
| Identity-based policy | Is the user/role allowed to call the action on the resource? | Grants permissions to principals |
| Resource-based policy | Does the bucket, key, queue, secret, or resource grant the principal access? | Grants permissions directly on resources |
| Role trust policy | Is the source principal allowed to assume the target role? | Controls who can assume the role |
| Permissions boundary | Does the boundary cap maximum permissions below the identity policy? | Caps IAM user/role permissions |
| Session policy | Was the session scoped down when STS issued the credentials? | Narrows session permissions |
| Service control policy (SCP) | Does AWS Organizations restrict the principal's actions? | Caps maximum permissions within an organization |
| Resource control policy (RCP) | Does the organization restrict permissions on the resource? | Caps maximum permissions for resources |
| VPC endpoint policy | Is the request traversing an endpoint blocked by the endpoint policy? | Controls requests over a VPC endpoint |

Policies are evaluated depending on request type and service. Not every request involves every policy type. Inspect the error context, CloudTrail, and authorization details where available to see which policies participated in evaluation.

### 4.2 Explicit Deny vs. Implicit Deny

- **Explicit deny:** a statement with `Effect: Deny` matches the request's action, resource, and conditions. An applicable explicit deny blocks the request regardless of other allow policies.
- **Implicit deny:** no explicit deny exists, yet no matching `Allow` exists across the required policies. For instance, a role has `s3:GetObject` on prefix `reports/`, while the application reads `archive/`.

Newer error messages may identify the policy type or ARN causing an explicit deny, such as an SCP, RCP, permissions boundary, session policy, or identity policy. Not all services return the same format, and if multiple policies deny, the message may show only partial context.

### 4.3 Cross-Account Access

When accessing resources in another account, distinguish two models:

1. **Assuming a role into the target account:** the source principal must be allowed to call `sts:AssumeRole`, the target role's trust policy must trust that principal, and the target role must hold the required permissions once assumed. Cross-account requires both the caller's policy and the target role's trust policy to allow it. Within the same account, permissions can be granted via identity policies when the trust policy trusts the account, or by naming a specific principal directly in the trust policy; if the principal has a permissions boundary, the boundary must still allow `sts:AssumeRole`.
2. **Direct cross-account resource access:** the principal's policy and the resource policy in the resource-owning account must work together according to service rules. For instance, an S3 bucket policy can allow a role in another account to read objects while the role's identity policy must also allow the action.

When using AssumeRole, inspect both sides: the caller's policy and the target role's trust policy. Having `s3:GetObject` on a role does not mean everyone can assume that role.

### 4.4 Trust Policies and `iam:PassRole` Are Different Things

`sts:AssumeRole` allows a principal to request a role session. `iam:PassRole` allows a configurator to pass an IAM role to an AWS service to use, such as attaching an execution role to Lambda or a task role to an ECS task. `iam:PassRole` does not issue temporary credentials to the caller and does not replace a trust policy.

When seeing `not authorized to perform: iam:PassRole`, inspect the resource creator's `PassRole` permissions, the passed role ARN, and the service principal in the trust policy. When seeing `sts:AssumeRole` errors, focus on caller permissions, trust relationships, and trust policy conditions.

## 5. Credential Provider Chain: Where Does the Application Get Credentials?

The AWS CLI and AWS SDKs search multiple sources for credentials. The first source found may differ from what a developer expects. A stale environment variable can keep an application using wrong credentials even after a profile is fixed.

### 5.1 AWS CLI

The AWS CLI can obtain credentials from:

- Command-line/profile selection and environment variables.
- IAM roles configured in profiles via `source_profile` or `credential_source`.
- Web identity tokens.
- IAM Identity Center (SSO).
- Shared credentials/config files.
- `credential_process`.
- ECS container credential endpoint.
- EC2 instance metadata service.

Order and precedence depend on the provider. Notably, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in the environment can override credentials in a profile selected via `AWS_PROFILE` or `--profile`. Thus, passing `--profile dev` does not guarantee the CLI uses the access keys defined inside that profile.

Common environment variables:

| Variable | Purpose |
|---|---|
| `AWS_PROFILE` | Selects the default named profile |
| `AWS_ACCESS_KEY_ID` | Access key ID |
| `AWS_SECRET_ACCESS_KEY` | Secret access key |
| `AWS_SESSION_TOKEN` | Session token for temporary credentials |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Default Region for requests |
| `AWS_SHARED_CREDENTIALS_FILE` | Path to credentials file |
| `AWS_CONFIG_FILE` | Path to config file |
| `AWS_EC2_METADATA_DISABLED` | Disables EC2 metadata provider access when set to `true` |

`aws configure list` shows the profile, credential source, and Region selected by the CLI. Access key/secret values are partially masked; this command helps trace credential sources without printing secrets to the terminal.

### 5.2 AWS SDK for Java 2.x

`DefaultCredentialsProvider` in AWS SDK for Java 2.x searches for credentials in the following general order:

1. Java system properties (`aws.accessKeyId`, `aws.secretAccessKey`, `aws.sessionToken`).
2. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`).
3. Web identity token and role ARN.
4. Shared `credentials` and `config` files, including profiles, IAM Identity Center, AssumeRole, and `credential_process`.
5. ECS container credentials.
6. EC2 instance profile credentials via the metadata service.

The provider chain stops at the first source with valid configuration. Therefore, stale Java system properties or environment variables can shadow the SSO profile, web identity, or instance role you intended to use.

Do not assume every language SDK uses the exact same provider order. Check the documentation for the SDK in use and inspect the actual credential source inside the target process/container.

### 5.3 Static Providers vs. Refreshable Providers

A static credentials provider only holds the values passed into it. If those values are temporary credentials, the provider will not call STS to obtain a new session. Once credentials expire, the client keeps signing requests with the old values and fails.

Standard providers for STS, web identity, containers, and instance profiles include caching and refresh mechanisms. When applications use standard providers without copying credentials into fixed strings, the SDK can fetch fresh credentials before the current session expires.

## 6. Verifying Active Identity with the AWS CLI

Before altering policies, confirm which principal the CLI is actually using.

```bash
aws --version
aws configure list
aws sts get-caller-identity
```

With a named profile:

```bash
aws configure list --profile dev
aws sts get-caller-identity --profile dev
```

`get-caller-identity` returns `Account`, `Arn`, and `UserId`. The ARN reveals whether requests use an IAM user, assumed role, or federated session. Example:

```json
{
  "UserId": "AROAXXXXXXXXXXXXX:build-session",
  "Account": "111122223333",
  "Arn": "arn:aws:sts::111122223333:assumed-role/DeploymentRole/build-session"
}
```

`GetCallerIdentity` requires no explicit IAM permissions to return the calling identity. However, its output only confirms the principal; it does not prove the principal has permissions for other services/resources.

### 6.1 Checking Environment Variables Without Printing Secrets

In PowerShell, list only variable names:

```powershell
Get-ChildItem Env:AWS_* | Select-Object -ExpandProperty Name
```

In Bash:

```bash
env | cut -d= -f1 | grep '^AWS_'
```

If stale credential variables exist, trace their source and clear them from the shell/session or CI/CD config. Never print the entire environment to logs, as it can leak secrets.

### 6.2 Temporarily Cleaning Up Environment Variables

PowerShell:

```powershell
Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
$env:AWS_PROFILE = 'dev'
aws sts get-caller-identity
```

Bash:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_PROFILE=dev
aws sts get-caller-identity
```

These commands affect only the current shell environment. If variables are set in shell profiles, IDEs, service units, or CI runners, fix them at process startup so the issue does not return.

## 7. Configuring IAM Identity Center and AssumeRole in the AWS CLI

### 7.1 IAM Identity Center

For organizations using AWS IAM Identity Center, configure an SSO profile:

```bash
aws configure sso
```

After configuration, sign in and verify identity:

```bash
aws sso login --profile dev
aws sts get-caller-identity --profile dev
```

The CLI caches the login and automatically fetches temporary credentials from the permission set as needed. When the IAM Identity Center session expires, sign in again using `aws sso login`. Automatic refreshing of AWS role credentials does not mean the underlying SSO login token lasts indefinitely.

### 7.2 Assume Role Profiles

You can configure a profile that uses a source profile to assume a role in another account:

```ini
[profile dev]
region = ap-southeast-1
output = json

[profile prod-readonly]
role_arn = arn:aws:iam::444455556666:role/ProductionReadOnly
source_profile = dev
role_session_name = analyst-session
region = ap-southeast-1
duration_seconds = 3600
```

After signing into the source profile if needed, run:

```bash
aws sso login --profile dev
aws sts get-caller-identity --profile prod-readonly
aws s3 ls s3://company-prod-reports/ --profile prod-readonly
```

The CLI automatically calls STS to assume the role and caches temporary credentials. When the role session expires, the CLI can request credentials from the source profile and assume the role again. If the source profile uses SSO and the SSO session expires, you must sign in to SSO again.

### 7.3 Using an Instance Role as the Source

On EC2, you can configure a target profile to use credentials from the instance profile:

```ini
[profile audit-reader]
role_arn = arn:aws:iam::444455556666:role/AuditReadOnly
credential_source = Ec2InstanceMetadata
region = ap-southeast-1
```

Common `credential_source` values are `Environment`, `Ec2InstanceMetadata`, and `EcsContainer`. Do not specify both `source_profile` and `credential_source` in the same profile. For workloads that already have an appropriate instance/task role, assuming an extra role is often unnecessary.

## 8. Automatic Credential Refreshing in AWS SDK for Java 2.x

### 8.1 Using the Default Credentials Provider

For applications running on developer workstations, EC2, ECS, EKS, or Lambda, the simplest approach is letting the SDK use the default provider chain. Never hardcode access keys/secret keys in source code.

```java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

public class S3AccessExample {
    public static void main(String[] args) {
        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            s3.listBuckets().buckets().forEach(
                    bucket -> System.out.println(bucket.name()));
        }
    }
}
```

The SDK uses `DefaultCredentialsProvider` automatically when no explicit provider is specified. In AWS environments, attach an appropriate role to the workload and let the provider fetch credentials from the runtime.

### 8.2 AssumeRole with a Refreshable Provider

When an application must assume another role, use `StsAssumeRoleCredentialsProvider`. The provider caches the session and requests a new session before current credentials expire while source credentials remain valid.

```java
import java.time.Duration;

import software.amazon.awssdk.auth.credentials.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;

public class AssumeRoleS3Example {
    public static void main(String[] args) {
        StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();

        StsAssumeRoleCredentialsProvider credentials =
                StsAssumeRoleCredentialsProvider.builder()
                        .stsClient(sts)
                        .refreshRequest(AssumeRoleRequest.builder()
                                .roleArn("arn:aws:iam::444455556666:role/ReportReader")
                                .roleSessionName("report-service")
                                .durationSeconds(3600)
                                .build())
                        .prefetchTime(Duration.ofMinutes(10))
                        .staleTime(Duration.ofMinutes(2))
                        .asyncCredentialUpdateEnabled(true)
                        .build();

        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(credentials)
                .build()) {
            s3.listObjectsV2(request -> request
                    .bucket("company-prod-reports")
                    .maxKeys(10));
        } finally {
            credentials.close();
            sts.close();
        }
    }
}
```

This example requires `software.amazon.awssdk:sts` and `software.amazon.awssdk:s3` dependencies of the same AWS SDK for Java 2.x version. `prefetchTime` lets the provider begin fetching a new session before expiration; `staleTime` defines when credentials are considered stale. Enabling asynchronous refresh avoids forcing the first request after idle periods to block synchronously on STS, though errors must still be handled if source credentials become invalid.

### 8.3 Common Mistakes in Java Applications

- Constructing a `StaticCredentialsProvider` from an STS response and keeping the client long-lived: the provider never calls STS to refresh.
- Caching `AwsSessionCredentials` in a singleton without tracking expiration or implementing refresh logic.
- Creating `StsAssumeRoleCredentialsProvider` while source credentials are expired or lack `sts:AssumeRole` permissions.
- Placing static credential environment variables inside a container so they take precedence over web identity or container providers.
- Creating a new STS client or credentials provider per request, increasing latency and STS call volume.
- Failing to close providers/clients on application shutdown, causing thread or connection leaks.

Share one credentials provider across the application lifecycle so the AWS SDK manages caching and refreshing. When selecting a specific profile is required, use `ProfileCredentialsProvider`; when running in EKS/ECS/EC2, prefer standard runtime providers.

## 9. Credential Sources by Runtime Environment

| Environment | Recommended Credential Source | What to Check on Failure |
|---|---|---|
| Developer workstation | IAM Identity Center or named profile | SSO login, `AWS_PROFILE`, environment variables, and profile paths |
| Amazon EC2 | Instance profile / instance role | Attached role, IMDSv2, routing, and `AWS_EC2_METADATA_DISABLED` |
| Amazon ECS | Task role | Task definition, task role ARN, container credential endpoint, and networking |
| Amazon EKS with IRSA | OIDC web identity token + IAM role | ServiceAccount annotation, OIDC provider, trust policy `aud`/`sub`, token file |
| Amazon EKS Pod Identity | EKS Pod Identity association and agent | Namespace/service account association, agent, and role trust |
| AWS Lambda | Execution role | Execution role ARN, policy permissions, and runtime credential provider |
| External CI/CD | OIDC federation or credential broker | OIDC issuer, audience, subject claim, trust policy, and token lifetime |
| CI/CD running on AWS | Instance/task role or role chaining | Source role, `sts:AssumeRole`, trust policy, and session duration |

### 9.1 EC2 Instance Metadata Service

EC2 instance profiles deliver temporary credentials via the Instance Metadata Service (IMDS). Use IMDSv2 and restrict metadata endpoint access per instance security design. If an application fails to fetch credentials, check:

- Whether an IAM role is attached to the instance profile.
- Whether the instance can reach the metadata endpoint.
- Whether a firewall, proxy, or host config blocks the IMDSv2 token flow.
- Whether the hop limit accommodates containerized applications.
- Whether `AWS_EC2_METADATA_DISABLED=true` accidentally disabled the provider.

Never copy credentials from the metadata endpoint into files. SDKs and the CLI include providers that fetch and refresh credentials automatically.

### 9.2 ECS Task Roles

In ECS, distinguish the task role from the task execution role. The task role grants permissions to code running inside the container. The task execution role lets the ECS agent pull images or send logs. If containerized code calls S3 while permissions were granted only to the execution role, the application will still receive `AccessDenied`.

SDKs/CLI retrieve credentials from the container credential endpoint provided by the ECS agent. If the endpoint or authorization token file is unreachable, inspect task metadata environment variables, the task definition, and the agent.

### 9.3 EKS IRSA and Pod Identity

IRSA uses a Kubernetes ServiceAccount OIDC token to call `AssumeRoleWithWebIdentity`. The role's trust policy must match the OIDC provider, `aud`, and `sub` (namespace/service account). If the token file is not mounted or the service account is misannotated, the SDK may fall through to another provider or report no credentials found.

EKS Pod Identity uses associations and an agent to supply pod credentials. Confirm the association points to the correct cluster, namespace, service account, and role. Avoid static access keys in pod environment variables, as they can shadow IRSA/Pod Identity credentials.

## 10. Credential and IAM Troubleshooting Matrix

| Error / Symptom | Common Cause | First Troubleshooting Step |
|---|---|---|
| `ExpiredToken` / `ExpiredTokenException` | STS credentials expired or app cached an old session | Refresh the source session; verify whether the provider refreshes or uses static credentials |
| `InvalidClientTokenId` | Invalid access key/session token, missing token, or mismatched credential tuple | Run `aws configure list`; verify profile and `AWS_SESSION_TOKEN` without printing secrets |
| `InvalidAccessKeyId` | Access key does not exist, was deleted, or is misconfigured | Identify the credential source, key status, and active profile |
| `UnrecognizedClientException` | Credentials or token not recognized by AWS | Inspect key/token tuple, profile, source credentials, and request signing |
| `AccessDenied` / `AccessDeniedException` | Valid principal, yet policy denies or lacks allow | Identify action/resource/principal, then review all applicable policies |
| `not authorized to perform: sts:AssumeRole` | Caller lacks assume permissions or trust policy denies | Inspect both the caller's identity policy and target role trust policy |
| `not authorized to perform: iam:PassRole` | Resource creator cannot pass role to service | Check `iam:PassRole` on the exact role ARN and trust relationship |
| `SignatureDoesNotMatch` | Wrong secret, mismatched session token, bad canonical request, or clock skew | Verify credential source, signing Region/service, and clock sync |
| `RequestExpired` | Request timestamp outside AWS acceptance window | Check NTP/system clock, proxies, and signing time |
| `InvalidIdentityToken` | Expired OIDC token, issuer/audience mismatch, or bad provider/trust | Check token file, OIDC provider, and `aud`/`sub` conditions |
| `SdkClientException: Unable to load credentials from any of the providers in the chain` | SDK could not find any valid credential source | Inspect provider chain, profile path, SSO, container endpoint, or IMDS |
| Works locally yet fails in container | Local profile differs from task/pod role; env vars shadow provider | Confirm principal with `get-caller-identity` inside the container |
| Works briefly then fails | Session expired, source token expired, or refresh provider inactive | Check expiration, provider type, refresh logs, and source session |

Never alter policies solely upon seeing `AccessDenied`. First verify which principal made the request and which action/resource was denied.

## 11. Workflow for Investigating ExpiredToken and InvalidClientTokenId

Follow these steps in order to isolate the problem quickly.

### Step 1: Confirm the Credential Source

```bash
aws configure list
aws sts get-caller-identity
```

If the second command reports an expired/invalid token, the problem lies in the credential source or signing/authentication before investigating S3, EC2, or target service permissions.

### Step 2: Check Profiles and Environment

- Confirm `AWS_PROFILE` or `--profile` is correct.
- Check whether stale `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN` variables exist.
- Verify credentials/config files belong to the right user, container, or service account.
- Check `AWS_SHARED_CREDENTIALS_FILE` and `AWS_CONFIG_FILE` if using custom paths.
- Ensure no static profile overrides SSO or role providers.

### Step 3: Refresh by Source Type

| Source | Recovery Action |
|---|---|
| IAM Identity Center | Run `aws sso login --profile <profile>` |
| CLI AssumeRole profile | Refresh the source profile, then let the CLI re-assume the role |
| EC2 instance profile | Check metadata endpoint, role attachment, and IAM instance profile |
| ECS task role | Check task role and container credential endpoint |
| EKS IRSA | Check projected token file, OIDC trust, and service account |
| EKS Pod Identity | Check association, agent, and role trust |
| Java STS provider | Use a refreshable provider; verify STS source credentials remain valid |
| Long-term IAM user access key | Check key status, secret, profile, and rotation process; this is not STS expiry |

### Step 4: Re-Confirm the Principal

After refreshing, re-run `aws sts get-caller-identity` inside the exact shell, container, or runtime. If the ARN changed, verify the new principal matches your design and holds required policies.

### Step 5: Test the Target Service Request

Only after `get-caller-identity` succeeds should you retry the target service call. If that request returns `AccessDenied`, move to the authorization analysis workflow below.

## 12. Workflow for Investigating AccessDenied

### Step 1: Read the Full Error Context

Record these fields:

- Principal ARN in the error message.
- Denied action, e.g., `s3:GetObject` or `kms:Decrypt`.
- Resource ARN.
- Policy type mentioned in `because ...` or `with an explicit deny ...`.
- Policy ARN if provided by AWS.
- Region, timestamp, request ID, and source IP/network path if available.

Example:

```text
User: arn:aws:sts::111122223333:assumed-role/ReportReader/job-42
is not authorized to perform: s3:GetObject
on resource: arn:aws:s3:::company-prod-reports/finance/q4.csv
because no identity-based policy allows the s3:GetObject action
```

This message pinpoints the assumed role session and action to check. Inspect policies attached to IAM role `ReportReader`, permissions boundaries, session policies, and any other applicable policies.

### Step 2: Check Roles and Trust Relationships

For role assumption, verify:

1. Is the source principal allowed to call `sts:AssumeRole` under the trust model used? Cross-account requires the caller policy to allow it; within the same account, the trust policy can grant access directly to a specific principal.
2. Does the target role's trust policy allow that principal/service/OIDC provider to assume it?
3. Do conditions require MFA, ExternalId, source IP, principal tags, `aws:SourceArn`, `aws:SourceAccount`, `aud`, or `sub`?
4. Is the role constrained by an SCP/RCP or another explicit deny?
5. Does `DurationSeconds` exceed the maximum session duration or the one-hour role chaining cap?

Minimal trust policy example for a role assumed by another IAM role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/BuildRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

This illustrates only the trust relationship. In production, scope principals tightly, add appropriate conditions, and verify `BuildRole`'s policy allows `sts:AssumeRole` on the target role.

### Step 3: Audit Effective Policies

Inspect identity policies, resource policies, permissions boundaries, session policies, SCPs, RCPs, and VPC endpoint policies for the request. Never read only a single attached role policy and jump to conclusions.

Common condition failures:

- `aws:RequestedRegion` mismatches the request Region.
- `aws:SourceIp` or `aws:VpcSourceIp` mismatches the network path.
- `aws:MultiFactorAuthPresent` requires MFA while the session lacks MFA context.
- `aws:PrincipalTag` or `aws:ResourceTag` mismatches.
- `aws:RequestTag` or `aws:TagKeys` missing tags during resource creation.
- `kms:EncryptionContext` mismatches the request encryption context.
- `sts:ExternalId`, `aws:SourceArn`, or `aws:SourceAccount` mismatches the trust policy.

### Step 4: Use the IAM Policy Simulator

IAM Policy Simulator evaluates outcomes for supported actions/resources and policy contexts without sending mutating requests to real resources.

CLI example:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportReader \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::company-prod-reports/finance/q4.csv
```

Inspect `EvalDecision`, `MatchedStatements`, and context evaluations. Simulator outcomes can differ from reality because the simulator does not automatically reproduce every context key, resource policy, service behavior, or runtime condition. Use it to narrow down causes, then confirm with controlled real requests.

### Step 5: Use Authorization ID When Provided by AWS

Some supported `AccessDenied` responses include an authorization ID and a link to policy evaluation explanations. These details show how checks such as SCPs, RCPs, VPC endpoints, resource policies, principal policies, permissions boundaries, and sessions were evaluated when the request failed.

If an authorization ID is present, open authorization details in the IAM console or run the IAM Toolbox command in the same Region (where supported by your account/CLI):

```bash
aws iam-toolbox get-request-authorization-details \
  --region ap-southeast-1 \
  --authorization-id AUTHORIZATION_ID_FROM_ERROR
```

An authorization ID is not guaranteed on every error or service. If unavailable, continue using error context, CloudTrail, and Policy Simulator.

### Step 6: Inspect CloudTrail

CloudTrail helps identify the principal, session issuer, action, resource, timestamp, and request context for many management API events. Search for related events such as `AssumeRole`, `AssumeRoleWithWebIdentity`, or the denied service API. Cross-check:

- `userIdentity.type`, `userIdentity.arn`, and `sessionContext.sessionIssuer.arn`.
- `accessKeyId` to correlate requests with credentials/sessions (never the secret key).
- `eventSource`, `eventName`, `awsRegion`, `sourceIPAddress`, and `errorCode`.
- `requestParameters` and resource ARNs if logged.

CloudTrail never stores secret access keys or session tokens. Some data events require enabling data event logging separately; not every denied request appears in Event history. Verify event types and trail configuration before concluding an absent log means a request never occurred.

## 13. Clock Skew and SigV4 Signatures

AWS Signature Version 4 incorporates timestamps, credential scope, and request content into signing. If the OS clock drifts significantly from AWS time, requests can be rejected even with valid access keys.

Common causes:

- Virtual machines resuming from sleep/hibernate before re-syncing time.
- Containers or hosts with drifted clocks.
- NTP service disabled or unable to reach time sources.
- Proxies/gateways altering requests or headers.
- Application signing with a Region/service scope mismatched to the endpoint.
- Secret keys corrupted by scripts or shell quoting.
- Temporary credentials used without sending the session token.

Check system time:

```bash
date -u
timedatectl status
```

On Windows PowerShell:

```powershell
Get-Date -AsUTC
w32tm /query /status
```

If the clock is skewed, synchronize via NTP or your organization's managed time service. Never work around skew by hardcoding timestamps in application code. For `SignatureDoesNotMatch`, besides clock skew, inspect credential sources, signing Region, service endpoint, canonical headers, and proxies.

## 14. Rotating IAM Access Keys and Credential Hygiene

Long-term IAM user access keys have no STS expiration. If an organization still relies on such keys, establish rotation workflows and usage tracking.

Commands to inspect key metadata:

```bash
aws iam list-access-keys --user-name legacy-app-user
aws iam get-access-key-last-used --access-key-id AKIAEXAMPLEACCESSKEY
```

Credential reports provide MFA status, active keys, rotation timestamps, and last-used times for IAM users in an account. Last-used data has latency and is not real-time telemetry.

Safe rotation workflow:

1. Identify the application, owner, and workload using the old key.
2. Create a new key within IAM user limits.
3. Update the secret store or credential distribution system.
4. Test requests with the new key and confirm principal/permissions.
5. Cut workloads over completely to the new key.
6. Deactivate the old key and monitor for errors over a validation window.
7. Delete the old key once certain no workloads depend on it.

For new architectures, replace long-term keys with IAM roles, IAM Identity Center, web identity, or workload identity. Never commit keys to Git, Docker images, AMIs, unprotected Terraform state, or shared config files.

## 15. Security During Error Investigation

Debugging can expose credentials if logging is overly verbose. AWS CLI `--debug` helps inspect request flow, endpoints, retries, and responses, yet output can contain headers, request metadata, or sensitive details.

Investigation guidelines:

- Never paste `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, presigned URLs, or raw authorization headers into tickets/chat.
- Mask account IDs, role ARNs, or resource names if required by security policy.
- Enable debug logging only briefly and restrict access to log outputs.
- Do not enable HTTP wire-level logging in production without a risk assessment.
- Purge temporary logs containing sensitive data per retention policies.
- If a secret is exposed, immediately revoke/rotate credentials and audit usage scope.
- Never broaden policies to `Action: "*"`, `Resource: "*"` just to test whether an error disappears.

## 16. Case Study: Java Application on ECS Hitting ExpiredToken After Several Hours

A Java service on ECS reads reports from S3. It works right after deployment, yet after a few hours starts receiving `ExpiredToken`.

### Step 1: Confirm the Principal Inside the Container

Run `aws sts get-caller-identity` inside the same task/container (if CLI is installed) or safely log the principal ARN from the app. Confirm requests use the task role rather than an IAM user access key.

### Step 2: Check the Provider Chain

Inspect environment variables. If the container has `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` injected from an old secret, they can take precedence over the container credential provider. Remove static credential injection and let the SDK use the task role.

### Step 3: Inspect the Java Client

If the app constructs a `StaticCredentialsProvider` from a single `AssumeRole` call, the client holds those credentials until process restart. Replace it with `DefaultCredentialsProvider` so the SDK reads ECS task role credentials, or use `StsAssumeRoleCredentialsProvider` if assuming an additional role is genuinely required.

### Step 4: Inspect the IAM Role

Ensure the task definition attaches the right task role, the role allows `s3:GetObject` on the target prefix, and no bucket policy blocks access. If the role assumes another role, check caller permissions and the trust policy.

### Step 5: Test After Fixing

Run the task long enough to pass the initial credential cycle, monitor refresh logs, and run periodic S3 operations. Confirm requests succeed across multiple refreshes. If errors shift to `AccessDenied`, credentials refreshed successfully yet the role/session policy lacks resource permissions.

## 17. Operations and Prevention Checklist

- [ ] Confirm active principal with `aws sts get-caller-identity` in the exact runtime.
- [ ] Inspect credential sources via `aws configure list` and environment variables.
- [ ] Prefer IAM roles or federation over long-term IAM user keys whenever possible.
- [ ] Always use temporary credentials alongside their session token.
- [ ] Match session duration to workload needs; keep role chaining within one hour.
- [ ] Use refreshable providers in the AWS SDK; never store STS credentials in static providers.
- [ ] Attach appropriate workload roles to EC2/ECS/EKS/Lambda.
- [ ] Scope IAM role trust policies to exact principals/services/OIDC identities.
- [ ] Review identity policies, resource policies, boundaries, session policies, SCPs/RCPs, and endpoint policies on AccessDenied.
- [ ] Verify Region, system clock, SigV4, and proxies on signature errors.
- [ ] Ensure CloudTrail logging and retention suffice for investigating critical requests.
- [ ] Use Policy Simulator as a diagnostic aid, then verify with real requests.
- [ ] Ensure secrets never appear in logs, source control, or shared debug outputs.
- [ ] Track owners, rotation plans, and last-used telemetry for legacy IAM access keys.
- [ ] Maintain alerts and runbooks for `ExpiredToken`, `AccessDenied`, and credential provider chain failures.

## 18. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| `ExpiredToken` means the IAM policy lacks permissions | It is a temporary credential expiration error; refresh the credential source first |
| Granting `AdministratorAccess` fixes expired credentials | Policies cannot revive an expired session token |
| Access key ID and secret key suffice for an STS session | Temporary credentials also require the session token |
| `AWS_PROFILE` always overrides environment credentials | Environment credentials can take precedence over profiles |
| `GetCallerIdentity` succeeding means S3 permissions exist | It only confirms the calling principal |
| A role with `s3:GetObject` can be assumed by anyone | Caller permissions and role trust policies must still permit assumption |
| `iam:PassRole` and `sts:AssumeRole` are the same | One passes a role to a service; the other creates a role session |
| Increasing role session duration fixes all expiration errors | Source sessions may expire earlier; role chaining is capped at one hour |
| The AWS SDK refreshes every type of credential automatically | Static/environment/system-property providers do not fetch fresh STS credentials |
| `AccessDenied` is always caused by identity policies | Resource policies, boundaries, session policies, SCPs/RCPs, trusts, or VPC endpoints can also deny |
| Policy Simulator guarantees production requests will succeed | The simulator does not replicate every context and service behavior |
| `SignatureDoesNotMatch` always means a wrong secret key | Clock skew, Region/service scope, proxies, or canonical requests can also cause it |

## References

- [Troubleshoot access denied error messages](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html)
- [Troubleshoot access denied using authorization ID](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied-authorization-id.html)
- [IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
- [Access management for AWS resources](https://docs.aws.amazon.com/IAM/latest/UserGuide/access.html)
- [Temporary security credentials in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html)
- [Request temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_request.html)
- [Compare AWS STS credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_sts-comparison.html)
- [Troubleshoot IAM roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_roles.html)
- [AssumeRole API reference](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [IAM roles and role chaining](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)
- [AWS CLI troubleshooting](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-troubleshooting.html)
- [AWS CLI configuration and credentials precedence](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)
- [Using IAM roles in the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html)
- [IAM Identity Center authentication with the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [Credential and configuration files](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
- [Default credentials provider chain for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [Credentials caching in AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credential-caching.html)
- [AWS SDK for Java 2.x credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-providers.html)
- [IAM policy simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)
- [Generate IAM credential reports](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_getting-report.html)
- [Get the last use of an access key](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-keys-admin-managed.html)
- [AWS Signature Version 4](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv.html)
- [AWS STS regional endpoints](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_enable-regions.html)
