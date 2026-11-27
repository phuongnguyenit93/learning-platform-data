# AWS STS and Temporary Security Credentials

An application needing access to S3, RDS, or DynamoDB, or an administrator needing to inspect VPC/EC2, must prove **identity** and hold **appropriate permissions**. Embedding long-term AWS access keys into source code, containers, or pipelines increases leak risks, complicates key rotation, and makes access scope harder to control. **AWS Security Token Service (AWS STS)** issues **temporary security credentials** for time-bounded access sessions tied to IAM roles, identity federation, or other session-issuing mechanisms.

This lesson is in the **IAM and Permissions** chapter of the **CLOUD_PROVIDERS_AWS** module. STS knowledge connects directly to AWS infrastructure across accounts/Regions/AZs; deploying secure applications on EC2, ECS, EKS, and Lambda; authorization for VPC networking, S3 storage, and databases; tracing with CloudTrail; and controlling operational and cost impacts.

> **Key message:** Have users and workloads **obtain short-lived credentials from a managed identity mechanism**, using IAM roles with least privilege, rather than distributing static access keys. Temporary credentials are still secrets that can be abused for the duration of their validity.

## 1. Learning Outcomes

After this lesson, learners can:

1. Explain AWS STS and the difference between long-term keys and temporary credentials.
2. Identify `AccessKeyId`, `SecretAccessKey`, `SessionToken`, and `Expiration`.
3. Distinguish `AssumeRole`, `AssumeRoleWithWebIdentity`, `AssumeRoleWithSAML`, `GetSessionToken`, `GetFederationToken`, and `GetCallerIdentity`.
4. Describe the three parts of cross-account role assumption: **caller permissions**, **trust policy**, and **target role permissions policy**.
5. Practice using AWS CLI with an assume-role profile and inspecting principals without copying secrets.
6. Explain role chaining, session duration, session policies, MFA, and ExternalId.
7. Apply the STS model to Java/Spring Boot and EC2, ECS, Lambda, EKS, and CI/CD workloads.
8. Troubleshoot wrong identity, expired token, or permission denial errors in a clear sequence.

## 2. What Are Temporary Security Credentials?

### 2.1. Comparison with long-term access keys

| Criterion | IAM user access key | Temporary security credentials |
|---|---|---|
| Components | Access key ID and secret access key | Access key ID, secret access key, **session token**, and expiration timestamp |
| Lifetime | Does not expire automatically per key | Has `Expiration`; afterward AWS rejects requests signed with the old credentials |
| Issued by | Created and managed on an IAM user | AWS STS or an AWS service integrated with a role/federation |
| Permissions | IAM user and related policies/guardrails | IAM role/session or session source, plus related guardrails |
| Best suited for | Certain legacy/unavoidable cases | Human users via IAM Identity Center; workloads via IAM roles |
| Security issue | Keys can be forgotten and remain valid | Reduces exposure window, yet must still be kept secret while token is valid |

**Temporary does not mean harmless.** A leaked set of keys and session token can be used to operate on authorized AWS resources until expiration or until permissions are blocked. Never put secrets/tokens in commits, logs, issue trackers, shell history, screenshots, or public chat channels.

### 2.2. Credential structure

A typical STS response contains:

~~~json
{
  "Credentials": {
    "AccessKeyId": "ASIA...EXAMPLE",
    "SecretAccessKey": "<REDACTED>",
    "SessionToken": "<REDACTED>",
    "Expiration": "2030-01-01T12:00:00Z"
  }
}
~~~

*This is illustrative data, not for authentication.*

- `AccessKeyId`: identifier of the access key; temporary keys typically start with `ASIA`.
- `SecretAccessKey`: secret used to sign AWS Signature Version 4 requests alongside the access key ID.
- `SessionToken`: proof of the temporary session, which must accompany requests, typically in the `X-Amz-Security-Token` header.
- `Expiration`: expiration timestamp in UTC. After this point, fresh credentials must be obtained.

If the session token is missing, even with a valid access key ID and secret access key, requests using temporary credentials are invalid. Conversely, valid credentials are not enough: IAM must still allow the **action** on the corresponding **resource**.

### 2.3. Credential issuance and usage flow

~~~mermaid
sequenceDiagram
    participant W as User / Workload
    participant I as Identity provider / IAM source
    participant S as AWS STS
    participant P as IAM policy evaluation
    participant A as AWS service API
    W->>I: Authenticate identity or receive role from runtime
    I-->>W: Valid identity/token
    W->>S: Request AssumeRole / Federation session
    S->>P: Check trust and conditions
    P-->>S: Allow or Deny
    S-->>W: Temporary credentials + Expiration
    W->>A: Send signed request and session token
    A->>P: Evaluate session action/resource
    P-->>A: Allow or Deny
    A-->>W: API result
~~~

This diagram is a **conceptual model**. With EC2, ECS, Lambda, and IAM Identity Center integrations, the AWS runtime/CLI/SDK usually handles fetching, caching, and refreshing credentials automatically. Applications do not necessarily call `AssumeRole` directly.

## 3. Important AWS STS APIs

| API | When to use | Key things to remember |
|---|---|---|
| `AssumeRole` | An already-authorized AWS principal needs to assume an IAM role, same-account or cross-account | Requires a matching trust policy; in standard cross-account cases, caller also needs `sts:AssumeRole` |
| `AssumeRoleWithWebIdentity` | Federation using OIDC/JWT from a trusted identity provider, e.g., CI or certain EKS patterns | STS validates token/claims and trust conditions; request needs no source AWS access key |
| `AssumeRoleWithSAML` | Enterprise federation based on SAML 2.0 | Uses SAML assertion and trust policy |
| `GetSessionToken` | An IAM user needs temporary credentials, often to call APIs requiring MFA | Session retains IAM user permissions; **does not switch** to a new IAM role |
| `GetFederationToken` | Custom identity broker creating a federated user session | Session policy limits session permissions |
| `GetCallerIdentity` | Inspect caller's account ID, principal ARN, and UserId | **Does not create new credentials** |

### 3.1. AssumeRole and role sessions

Suppose an operations team has a valid identity in account A. They need to query VPCs in account B without maintaining separate IAM users/access keys in B. Administrator B creates IAM role `InventoryViewer`, grants a specific source role in A permission to assume it, and gives `InventoryViewer` only the required EC2 read permissions.

AWS STS creates an **assumed-role session**. Within that session, requests are evaluated according to role B's permissions (and other effective policies). Caller A's permissions are not automatically added to role B's permissions.

### 3.2. Federation: OIDC and SAML

An identity provider (IdP) can authenticate users/workloads **outside AWS**. With OIDC, STS verifies the JWT token from the configured IdP, then evaluates `aud`, `sub`, or matching trust claims/conditions. A valid OIDC token **cannot automatically assume every IAM role**.

For example, GitHub Actions can exchange an OIDC token for a deployment role instead of storing long-term AWS secret keys in CI. The trust policy should constrain the repository/branch or environment, audience, and appropriate conditions. With SAML, AWS processes assertions according to the SAML provider's trust configuration.

### 3.3. GetSessionToken and GetFederationToken

`GetSessionToken` is used primarily by IAM users when programmatic MFA authentication is needed; the resulting temporary credentials inherit the IAM user's permissions and face specific restrictions on certain IAM/STS APIs. `GetFederationToken` serves custom identity brokers, using session policies to constrain federated user permissions.

These two APIs are useful when dealing with legacy systems, while modern applications typically prefer IAM Identity Center for humans and IAM roles for workloads. Never assume every set of temporary credentials is permitted to call additional STS APIs like `GetSessionToken` or `GetFederationToken`.

## 4. Session Duration, Refresh, and Revocation

### 4.1. Time boundaries

| API / mechanism | Relevant limits |
|---|---|
| `AssumeRole` | **15 minutes** up to the role's `MaxSessionDuration`; default request duration is usually **1 hour** |
| IAM role `MaxSessionDuration` | Configurable from **1 to 12 hours** |
| **Role chaining**: role session assuming another role | Subsequent `AssumeRole` is capped at **1 hour** |
| `AssumeRoleWithWebIdentity` / `AssumeRoleWithSAML` | Typically 15 minutes up to the role's maximum, depending on applicable conditions |
| IAM user `GetSessionToken` | 15 minutes to **36 hours**, default typically 12 hours |
| IAM user `GetFederationToken` | 15 minutes to **36 hours**, default typically 12 hours |

**Scenario:** The target role allows a maximum 12-hour session, yet the caller is already using an assumed-role session and calls `AssumeRole` with `--duration-seconds 7200` (2 hours). The request is rejected due to the **1-hour role chaining** limit. Reduce the duration to `3600` seconds or redesign the role assumption flow.

Lifetimes of the AWS access portal, IAM Identity Center login session, IdP token, and STS role session can **differ**. A user still being signed in to the Console does not guarantee old credentials in an SDK remain valid.

### 4.2. Refresh mechanisms

- AWS CLI can automatically use `role_arn` and `source_profile` to call `AssumeRole`, cache credentials, and refresh them as needed.
- AWS SDKs use a **credentials provider** to load/cache/refresh automatically instead of hardcoding static keys in code.
- EC2 instance roles, ECS task roles, Lambda execution roles, and EKS integrations supply temporary credentials via the runtime environment.
- When the source session (e.g., IAM Identity Center) expires, the user may need to sign in again before the CLI can request a new role session.

Do not call STS on every single request to S3/DynamoDB, as it adds latency and consumes quota. Reuse SDK clients/providers and let the runtime manage lifecycle.

### 4.3. Token expiration and credential exposure incidents

After `Expiration`, AWS no longer accepts the old credentials. When exposure is suspected **before that timestamp**, respond immediately: investigate, restrict/block permissions, consider the IAM role's **Revoke active sessions** mechanism, and audit CloudTrail. Deleting keys/tokens from a developer's laptop does not invalidate copies already taken by someone else. Policy/trust edits and revocation mechanisms must be evaluated against the live IAM authorization model.

## 5. Permission Rules During AssumeRole

A **cross-account** flow typically has three parts:

1. **Caller permission policy** in account A allowing `sts:AssumeRole` on role B.
2. **Role trust policy** in account B trusting caller A and checking relevant conditions.
3. **Role permissions policy** in account B allowing the AWS API actions the assumed session may perform.

~~~mermaid
flowchart LR
    C["Account A / caller TeamOperator"] --> CP["Policy allowing sts:AssumeRole"]
    CP --> T{"Trust policy of InventoryViewer role in Account B"}
    T -->|Deny| X["AccessDenied"]
    T -->|Allow| S["AWS STS issues role session"]
    S --> R["Role permissions and session restrictions"]
    R --> E["Evaluate SCP / boundary / resource policies"]
    E --> A["Read EC2 / VPC APIs"]
~~~

AWS has multiple policy types: identity-based, resource-based, session policies, permissions boundaries, service control policies (SCPs), and resource control policies (RCPs) where applicable. **Explicit deny** overrides allows. There are also cases where a resource-based policy grants permissions directly to a **role session ARN**, resulting in special implicit-deny evaluation rules. Therefore, use the three parts above as a baseline model and verify policy evaluation when building real systems.

## 6. Cross-Account IAM Example: Reading Network Resources

Assumptions:

- **Account A:** `111122223333`, source IAM role `TeamOperator`.
- **Account B:** `444455556666`, target IAM role `InventoryViewer`.
- **Goal:** `TeamOperator` assumes `InventoryViewer` to read VPCs, subnets, and instances; no resource creation/deletion.
- **Practice Region:** `ap-southeast-1` (Singapore).

All account IDs and roles are **fictional data**. The policies are for learning only; deploying in real systems requires administrators to verify ARNs/conditions and apply changes through a controlled change workflow.

### 6.1. Source policy: allow calling AssumeRole

Identity-based policy attached to `TeamOperator` in account A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeInventoryViewer",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/InventoryViewer"
    }
  ]
}
~~~

This policy allows **sending an AssumeRole request** to the target role; it does not directly grant `ec2:DescribeVpcs` in account B.

### 6.2. Target trust policy: who can assume?

Trust relationship of `InventoryViewer` in account B:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustTeamOperator",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/TeamOperator"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This trust policy states that the specific source role is allowed to assume it; it does **not** decide which EC2 APIs the role can use once assumed. Standard cross-account access requires both trust and caller permissions, and may also be capped by SCPs, permissions boundaries, and related policies.

### 6.3. Target role permissions policy: what can it do?

Permissions policy for `InventoryViewer`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadEc2VpcMetadata",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeInstances"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Certain EC2 `Describe*` operations use `Resource: "*"` per the API's authorization model. This does not grant every action. It can be combined with Region conditions, organization constraints, or other guardrails when designing systems.

### 6.4. Why Might AccessDenied Still Occur?

| Scenario | Consequence |
|---|---|
| Caller has `sts:AssumeRole` but trust does not trust caller | STS denies AssumeRole |
| Trust trusts caller, but cross-account caller lacks `sts:AssumeRole` | STS denies AssumeRole |
| Assume succeeds, target role does not allow `ec2:DescribeVpcs` | VPC read request is denied |
| Role has Allow, but organization applies a matching explicit deny | Request can still be blocked |
| Caller and role are in the same account, trust directly names an IAM principal | Special resource-based rules apply; do not mechanically apply cross-account conclusions |

**Note on IAM Identity Center:** Roles provisioned by Identity Center typically have ARNs containing `AWSReservedSSO_...`. Do not use the example name `TeamOperator` as your source ARN if your real principal is an SSO role. Verify the real role ARN, account ID, and permissions before configuring trust.

## 7. AWS CLI: Using STS Without Manually Copying Temporary Keys

### 7.1. Check the source profile

Install AWS CLI v2 and prepare a `source-team` profile that already has valid credentials to access the source role. Open a terminal:

~~~bash
aws --version
aws configure list --profile source-team

aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Illustrative example if the source is actually role `TeamOperator`:

~~~json
{
  "Account": "111122223333",
  "Arn": "arn:aws:sts::111122223333:assumed-role/TeamOperator/source-session"
}
~~~

`GetCallerIdentity` shows the **account** and calling **principal ARN**. The `assumed-role/...` value is the role **session** ARN, distinct from the underlying IAM role ARN `arn:aws:iam::...:role/...` used in trust policies.

### 7.2. Define an assume-role profile

In `~/.aws/config` (on Windows, typically `%UserProfile%\.aws\config`), create this profile:

~~~ini
[profile inventory-read]
role_arn = arn:aws:iam::444455556666:role/InventoryViewer
source_profile = source-team
role_session_name = sts-training-006
region = ap-southeast-1
output = json
~~~

`source-team` must be a configured source profile trusted by the target role. AWS CLI uses the source credentials to call STS, retrieves credentials for `InventoryViewer`, caches them, and automatically refreshes them as needed while the source remains valid. **Do not manually write temporary keys** into `~/.aws/credentials`.

If `source-team` is itself a role session, this constitutes **role chaining**, so the next session lasts at most 1 hour.

### 7.3. Verify the target account

~~~bash
aws sts get-caller-identity \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws ec2 describe-vpcs \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query 'Vpcs[].{Id:VpcId,Cidr:CidrBlock,Default:IsDefault}' \
  --output table
~~~

`Account` in the first command will be **444455556666** if permissions and trust are correct. The ARN takes the form `arn:aws:sts::444455556666:assumed-role/InventoryViewer/sts-training-006`. The second command uses the target role to read VPCs; an empty list can be a valid result.

### 7.4. Inspect AssumeRole metadata directly

The `aws sts assume-role` command returns credentials, so **never print the raw response to the screen or a ticket**. You can restrict output to just the session name and expiration:

~~~bash
aws sts assume-role \
  --role-arn arn:aws:iam::444455556666:role/InventoryViewer \
  --role-session-name sts-training-manual \
  --duration-seconds 900 \
  --profile source-team \
  --region ap-southeast-1 \
  --query '{RoleArn:AssumedRoleUser.Arn,ExpiresAt:Credentials.Expiration}' \
  --output json
~~~

Example:

~~~json
{
  "RoleArn": "arn:aws:sts::444455556666:assumed-role/InventoryViewer/sts-training-manual",
  "ExpiresAt": "2030-01-01T12:00:00Z"
}
~~~

This command **does not automatically switch** subsequent commands in your terminal to the target role. The sustainable approach is using the `inventory-read` profile from earlier or an SDK credentials provider.

### 7.5. When the source login is IAM Identity Center

A user in an organization typically obtains source credentials via SSO:

~~~bash
aws configure sso --profile company-sso
aws sso login --profile company-sso
aws sts get-caller-identity --profile company-sso
~~~

The account and role selected through IAM Identity Center must have the necessary permissions; the target role must trust **the actual source IAM role**. If valid and approved by an administrator, the target profile can use `source_profile = company-sso`. If denied, never create an IAM user and long-term access keys to "bypass" the process.

## 8. Session Policies, Session Tags, and Trust Conditions

### 8.1. Session policies can only narrow scope

`AssumeRole` supports an **inline session policy** or **managed session policy ARNs**. Typically, the effective permissions of a role session are the intersection of the role's identity-based policies and the session policy, subject to other guardrails.

For example, `InventoryViewer` can read VPCs, subnets, and instances, but a session for a specific job should only read VPCs:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OnlyDescribeVpcs",
      "Effect": "Allow",
      "Action": "ec2:DescribeVpcs",
      "Resource": "*"
    }
  ]
}
~~~

A session policy **never elevates permissions**. However, do not treat "intersection of two policies" as an absolute formula for every scenario: resource-based policies granting directly to a role session ARN can handle implicit deny limits differently. Always check policy evaluation for your specific design.

### 8.2. RoleSessionName, SourceIdentity, session tags

- **`RoleSessionName`**: session name shown in the assumed-role ARN, useful for CloudTrail tracing. Pick a name reflecting the workload/job, and avoid embedding sensitive personal info.
- **`SourceIdentity`**: preserves an attribution identifier when configured and permitted, which can persist across role chaining steps to aid auditing.
- **Session tags**: key/value pairs (e.g., `team=platform`, `env=dev`) usable in Attribute-Based Access Control (ABAC). Passing tags must be controlled via trust/`sts:TagSession` and related policies.

ABAC example: a role only reads resources tagged `environment=dev` if the principal/session tag `environment` is also `dev`. Never allow callers to arbitrarily set `environment=prod` if that identity is not approved to access production.

### 8.3. MFA

With eligible IAM users/roles, `AssumeRole` or `GetSessionToken` can attach MFA state, and trust/permissions policies can check conditions like `aws:MultiFactorAuthPresent`. Federation via IAM Identity Center or OIDC handles MFA workflows at the IdP; **never assume** every federated session carries the same MFA context that IAM can inspect directly.

### 8.4. ExternalId and the confused deputy problem

A SaaS provider allowed by many customers to assume roles in their accounts could be abused as a *confused deputy*. `sts:ExternalId` in the trust policy mitigates this risk by requiring an ID **generated/controlled per customer by the service provider** when calling `AssumeRole`.

`ExternalId` is **not** a password replacing authentication, nor does it grant permissions; trust/permission policies and provider-side controls are still needed. For OIDC CI/CD, conditions on `sub`, `aud`, and repository/branch/environment play a similar role at the layer restricting who is trusted.

## 9. STS and AWS Regions

STS has a legacy **global endpoint** `https://sts.amazonaws.com` and many **regional endpoints** such as `https://sts.ap-southeast-1.amazonaws.com`. AWS recommends choosing an appropriate regional endpoint to improve latency and failure isolation.

~~~bash
aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1
~~~

The Region where STS **issues credentials** does not have to be the Region where you later query EC2/VPC. Credentials can be used in any Region permitted by IAM policies, Region activation status, and token/endpoint type. Tokens from **regional STS endpoints** are supported in all AWS Regions. Tokens from the global endpoint have specific compatibility rules with manually enabled opt-in Regions; configure appropriately if your system uses opt-in Regions.

**Example:** A worker in Singapore obtains STS credentials via the regional endpoint, then queries CloudWatch or S3 in another enterprise-approved Region. Service calls still need to specify the appropriate target API Region. IAM roles exist at the account scope, whereas EC2/VPC are Regional services.

## 10. Applications with EC2, ECS, Lambda, EKS, and CI/CD

### 10.1. EC2 instance profile

A Spring Boot app running on EC2 needs to read S3 and query Secrets Manager:

1. Create an IAM role with an EC2 trust principal and permissions for the exact S3 bucket/secret needed.
2. Attach the role to EC2 via an **instance profile**.
3. AWS supplies temporary credentials via the **Instance Metadata Service (IMDS)**.
4. The SDK uses a credentials provider to fetch and refresh them; the app does not need to store access keys in `application.yml`.

Use IMDSv2 and enforce appropriate metadata access controls. Giving an instance an overly broad role widens the blast radius of every process able to reach credentials on that machine.

### 10.2. ECS task role vs. task execution role

- **Task role**: permissions for **application code** running in the container, e.g., `dynamodb:GetItem` or `s3:GetObject`.
- **Task execution role**: permissions for the ECS runtime/agent to pull ECR images, send logs, or perform other initialization steps.

If a container receives `AccessDenied` when querying DynamoDB, inspect the **task role**, not just the task execution role.

### 10.3. Lambda execution role

The AWS Lambda runtime supplies temporary credentials for the **execution role** to the function. For example, a function receives notifications from S3, writes to DynamoDB, and emits logs/metrics to CloudWatch. The role should only have permissions on the required resources and actions; never place long-term access keys in environment variables or deployment zip/JARs.

### 10.4. EKS workload identity

On Kubernetes/EKS, do not let every Pod rely on broad permissions from the EC2 node instance profile. You can use **IAM Roles for Service Accounts (IRSA)** based on OIDC/web identity or **EKS Pod Identity**, depending on cluster architecture, so each service account/workload maps to an appropriate role. SDKs obtain credentials via the built-in integration instead of key files inside images.

### 10.5. CI/CD outside AWS

GitHub Actions workflows or OIDC-capable platforms can obtain temporary AWS credentials via federation without putting long-term IAM user keys into CI secrets. Trust should tightly bind repository, branch/environment, and audience. Deployment roles should hold permissions only for the required services, stacks, and Regions.

| Environment | Preferred credential source | Avoid |
|---|---|---|
| AWS CLI users | IAM Identity Center and SSO profiles | Sharing IAM user keys |
| Spring Boot on EC2 | Instance role via IMDS | Secret keys in source code/JAR |
| ECS containers | ECS task role | Overusing task execution role |
| Lambda | Execution role | Static keys in function config |
| EKS | IRSA or EKS Pod Identity | Sharing one node role across all Pods |
| CI/CD outside AWS | OIDC federation into a role | Long-term AWS keys in CI |
| Centralized multi-account read | Cross-account AssumeRole | Distributing high-privilege credentials per account |

## 11. AWS SDK for Java 2.x and the Credentials Provider Chain

AWS SDK for Java 2.x includes **DefaultCredentialsProvider**. If you build a service client without specifying a custom credentials provider, the SDK searches an ordered chain including system properties, environment variables, web identity, shared profiles (including SSO/assume role), and container/instance providers.

Example checking STS identity using Java 2.x (requires dependency `software.amazon.awssdk:sts`, version-managed via the AWS SDK BOM):

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

public class AwsCaller {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            GetCallerIdentityResponse result = sts.getCallerIdentity();
            System.out.println("Account: " + result.account());
            System.out.println("Principal: " + result.arn());
        }
    }
}
~~~

This code **hardcodes no keys** and does not assume administrator permissions. If run on a laptop with the right `AWS_PROFILE`/SSO profile, the SDK reads that profile; on EC2/ECS, the SDK can fetch runtime role credentials.

When an application needs permissions of **another target role** over a long lifetime, use `StsAssumeRoleCredentialsProvider` so the SDK caches and refreshes the session. If you call `StsClient.assumeRole()` and pass the keys into `StaticCredentialsProvider`, long-running applications will hit `ExpiredToken` unless you implement refresh yourself. For serverless/container apps whose execution/task role already holds sufficient permissions, you usually do not need to re-assume **the role you already have** just to refresh credentials.

**Note:** A stale environment variable like `AWS_ACCESS_KEY_ID` or `AWS_SESSION_TOKEN` can take precedence in the provider chain ahead of an instance role. When you see the wrong identity, check provider order and environment variables before changing permissions policies.

## 12. Tracing, Monitoring, and Protecting Sessions

### 12.1. AWS CloudTrail

CloudTrail can record `AssumeRole` events and API calls performed with assumed-role sessions according to event logging scope. Metadata may include `userIdentity.type = AssumedRole`, role/session ARN, request action, Region, and source identity/session tag details depending on configuration.

For example, an on-call team needs to find who modified a security group:

1. Identify the account, Region, timestamp, and API action such as `AuthorizeSecurityGroupIngress`.
2. Locate the CloudTrail event and the principal/session that signed the request.
3. Correlate the session with role trust, original caller, source identity, and deployment pipeline.
4. Inspect IAM permissions alongside the infrastructure change to determine root cause and impact.

Never log `SecretAccessKey`/`SessionToken` in application logs for tracing: ARN/session metadata is the proper starting point.

### 12.2. Protecting temporary credentials

- Grant least privilege and trust only valid callers/IdPs; separate dev, staging, and production roles.
- Encourage MFA/federation for humans; workloads use environment-bound roles.
- Prevent secret leaks via logs, CLI output, shell history, repositories, container images, or ticketing systems.
- Maintain an incident response runbook for active tokens; never assume "waiting for expiration is enough."
- Use session names/source identity/session tags per policy for traceability.
- Monitor for unusual role assumptions and modifications to sensitive resources.

### 12.3. Cost and change management

STS grants authorization; it does not cap billing. A 15-minute session can still launch an EC2 instance that runs for days if the role has `ec2:RunInstances`. Therefore, combine least privilege, IAM/SCPs, AWS Budgets/cost alerts, quotas, tagging, and resource cleanup lifecycles. This lab uses read-only commands and does not require creating billable resources.

## 13. Common STS Troubleshooting Scenarios

| Symptom | Possible cause | How to resolve |
|---|---|---|
| `AccessDenied` on `AssumeRole` | Caller lacks `sts:AssumeRole`; role trust has wrong principal; MFA/ExternalId/tags condition failed | Check source `get-caller-identity`, trust, IAM policies, and guardrails |
| `AccessDenied` on `DescribeVpcs` | Assume succeeded, but target permissions policy is insufficient or has a deny | Check target role caller identity and effective permissions |
| `ExpiredToken` | Temporary credentials expired | Re-login to SSO if needed, let CLI/SDK provider fetch a new session |
| `InvalidClientTokenId` or invalid token | Missing/wrong session token, mixed credential sources, token incompatible with configured endpoint/Region | Check provider and `aws configure list`; never print secrets |
| 2-hour session request fails even though role allows 12 hours | Role chaining is capped at 1 hour | Use `--duration-seconds 3600` or redesign the assumption flow |
| `Unable to locate credentials` | CLI/SDK found no valid credential source | Check profile, SSO login, IMDS/container provider |
| SSO login succeeds, yet target role cannot be assumed | IAM Identity Center source role differs from trusted ARN or lacks permission | Verify actual source role and update configuration via admin |
| CLI/API returns different data than Console | Wrong account/role/Region or Console filter | Compare `get-caller-identity`, `--region`, and filters |
| Static credentials work briefly, then fail | No refresh mechanism | Use a role profile or SDK STS credentials provider |
| OIDC federation fails | Issuer/audience/subject or trust condition mismatch | Inspect OIDC provider, token claims, and trust policy |

### 13.1. Read-only inspection commands (no resource changes)

~~~bash
aws --version
aws configure list-profiles

# Check configuration source for the profile
aws configure list --profile source-team

# Principal before assuming the role
aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1 \
  --output json

# Principal after assuming the role
aws sts get-caller-identity \
  --profile inventory-read \
  --region ap-southeast-1 \
  --output json
~~~

`aws configure list` can show config types/sources, though you should still review output before sharing. `aws sts assume-role` **prints both secret and session token by default**, so use `--query` to select only metadata in demos. `--debug` can expose sensitive request data; use only in controlled environments.

## 14. Self-Check Practice Lab

**Prerequisites:** Learners have two source/target profiles provided by an administrator. If no environment is available, use simulated JSON and analyze permissions following the example in section 6; no need to create IAM roles, EC2 instances, or S3 buckets.

### Step A – Identify the source identity

~~~bash
aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Note the **account ID** and role/session ARN. Point out which part identifies the underlying IAM role and which part identifies the session name.

### Step B – Identify the target identity

~~~bash
aws sts get-caller-identity \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

If the account changed, describe what happened to the principal after `AssumeRole`. If an `AccessDenied` error occurs, identify this as a failure at the role-assumption step, not a VPC read error.

### Step C – Read VPC metadata only

~~~bash
aws ec2 describe-vpcs \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query 'Vpcs[].{VpcId:VpcId,CIDR:CidrBlock,Default:IsDefault}' \
  --output table
~~~

An empty result is valid if the account/Region has no VPCs. If this command is denied while Step B succeeded, check the target role's `ec2:DescribeVpcs` permission.

### Step D – Analyze permissions and durations

Explain these scenarios on your own:

1. Caller has `sts:AssumeRole` but target role trust policy does not trust caller: where is the error?
2. Role trusts caller, yet permissions policy lacks `s3:GetObject`: after assuming, can objects be read?
3. Target role sets `MaxSessionDuration = 12 hours`, but the source is already a role session; is requesting 2 hours valid?
4. A developer pastes the full JSON output of `AssumeRole` into an issue: which fields must be treated as secrets and how should the incident be handled?
5. A role session lasts only 15 minutes yet can run `ec2:RunInstances`: why do the created resources continue incurring costs afterward?

### Step E – Apply to a Java application

Design a Spring Boot app running in ECS that needs to read a DynamoDB table and send logs to CloudWatch. Specify which role must grant `dynamodb:GetItem` to **application code**, which role serves the ECS runtime, how the SDK retrieves credentials, and why long-term access keys do not belong in configuration files.

## 15. Knowledge Self-Assessment

You are ready to move on to AWS networking/compute/storage/serverless lessons if you can:

- Walk through the complete flow **caller → trust → STS session → resource authorization**.
- Read account/ARN accurately from `GetCallerIdentity` and know that this command does not issue credentials.
- Distinguish a persistent IAM role from **an assumed-role session** that has an expiration.
- State the **1-hour** maximum for role chaining, along with how the CLI/SDK automatically refreshes credentials.
- Explain why session policies only narrow permissions and why resource-based policies must be considered.
- Choose the right role/provider for EC2, ECS, Lambda, EKS, and OIDC CI/CD.
- Recognize the exposure risks of temporary credentials throughout their lifetime.
- Connect IAM/STS permissions with CloudTrail, security risk reduction, and cost control.

## Official Documentation

1. [Temporary security credentials in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html) — Foundations and benefits of temporary credentials.
2. [Request temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_request.html) — STS operations.
3. [Compare AWS STS credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_sts-comparison.html) — Comparing APIs, lifetimes, and limits.
4. [AWS STS API: AssumeRole](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html) — Parameters, durations, role chaining, and session policies.
5. [AWS CLI: Using an IAM role](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html) — `role_arn`, `source_profile`, auto-caching/refreshing.
6. [IAM: Switch to a role with AWS CLI](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-cli.html) — Cross-account IAM roles.
7. [IAM policies and permissions](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html) — How effective permissions are evaluated.
8. [AWS STS and Regions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_enable-regions.html) — Regional endpoints and token compatibility.
9. [AWS SDK for Java 2.x: Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — Automatic credential discovery.
10. [AWS SDK for Java 2.x: Credential caching](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credential-caching.html) — Caching/refreshing credentials.
11. [IAM: The confused deputy problem](https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html) — `ExternalId` in cross-account trust.

> **Remember:** STS provides **time-limited** credentials. Secure infrastructure still requires **explicit trust, least privilege, automatic credential refresh, CloudTrail auditing, and controls over resource-modifying and cost-generating actions**.
