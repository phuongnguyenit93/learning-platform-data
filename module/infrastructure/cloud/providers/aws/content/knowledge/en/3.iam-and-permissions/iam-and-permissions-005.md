# Trust Policies and Role Assumption in AWS IAM

## Learning Objectives

After this lesson, learners can:

- Explain how an **IAM role**, **trust policy**, and **permissions policy** differ; distinguish permissions of the **role assumer** from permissions of the **session after assuming the role**.
- Describe the **AWS Security Token Service (STS) AssumeRole** flow, the type of temporary credentials returned, and how AWS services use them.
- Write and read trust policies for **same-account**, **cross-account**, **AWS service**, and **federated login using OIDC/SAML** scenarios.
- Evaluate security conditions such as **MFA**, **ExternalId**, **SourceArn/SourceAccount**, **session tags**, and **source identity** where appropriate.
- Troubleshoot common errors such as AccessDenied, incorrect principal, and expired sessions; inspect sessions and monitor with CloudTrail.
- Apply role assumption in AWS systems spanning Regions/AZs, IAM, VPC, EC2/ECS/Lambda applications, S3 storage, databases, event integration, and recovery, monitoring, and cost control requirements.

> **Scope:** This lesson focuses on **trust policies and assume role** in the **IAM and Permissions** chapter of the **CLOUD_PROVIDERS_AWS** module. This forms the secure identity and authorization foundation for deploying AWS architectures; a trust policy alone does not replace networking, encryption, backup, or monitoring configurations.

## 1. What Problem Does an IAM Role Solve?

Suppose an application running on Amazon EC2 needs to read data from an S3 bucket; or a job in **AWS account A** needs to read resources in **AWS account B**. There are two approaches:

- Issue long-term access keys to the application and store those keys on servers/CI: hard to rotate, easy to leak, and often reused too broadly.
- Create an **IAM role** with clearly scoped permissions; a trusted entity **assumes the role** to obtain **temporary credentials** and perform only the permitted operations.

The role-based approach aligns with **least privilege**, reduces reliance on long-term keys, and supports access governance across environments, accounts, services, and workloads.

An **IAM role** is an **IAM identity** in an AWS account, not permanently tied to a single human or fixed server. A valid principal can use the role if permitted by trust mechanisms and permission controls. Upon successful assumption, the principal operates under an **assumed-role session** with temporary credentials.

### Terms to Distinguish

| Term | Meaning | Example |
| --- | --- | --- |
| **Principal** | Entity calling or authenticated to call AWS | IAM user, IAM role, service principal, federated identity |
| **IAM role** | Assumable identity carrying permissions and trust configuration | InventoryReadRole |
| **Trust policy** | Policy attached to a role defining **who/what is allowed to assume the role**, via which STS action and conditions | Trust only a role from account A |
| **Identity-based permissions policy** | Policy granting an IAM identity permissions to call APIs on resources | Caller's sts:AssumeRole permission; or role's s3:GetObject |
| **Resource-based policy** | Policy attached directly to a resource; a role trust policy is a type of resource-based policy on an IAM role | Bucket policy; role trust policy |
| **STS** | Service issuing temporary security credentials | AssumeRole API |
| **Role session** | Temporary context after assuming a role; has a session name, tracking metadata, and expiration | assumed-role/InventoryReadRole/report-2026 |
| **Session policy** | Policy narrowing permissions passed when creating certain STS sessions | Allow reading only one prefix in a bucket |
| **Permissions boundary / SCP** | Control layer capping permissions, depending on usage scope | Role boundary; AWS Organizations SCP |

The core idea is that **a role has two sides**:

1. **Trust policy (the front door):** Who can receive the role?
2. **Permission policies (permissions behind the door):** Once the role is received, what can the session do?

A trust policy allowing a principal to assume a role **does not automatically grant** that principal permission to read S3 or modify EC2. Likewise, a role having broad permissions **does not mean** everyone can assume it.

## 2. How Does the STS AssumeRole Flow Work?

~~~mermaid
sequenceDiagram
    participant Caller as Source principal
    participant STS as AWS STS
    participant IAM as IAM Policy Evaluation
    participant Service as Target service (e.g., S3)
    Caller->>STS: AssumeRole(RoleArn, RoleSessionName, ...)
    STS->>IAM: Check trust, caller permissions, and conditions
    alt Allowed
        STS-->>Caller: AccessKeyId + SecretAccessKey + SessionToken + Expiration
        Caller->>Service: Call API signed with session credentials
        Service->>IAM: Evaluate effective session permissions on resource
        IAM-->>Service: Allow or Deny
        Service-->>Caller: API response
    else Denied
        STS-->>Caller: AccessDenied / condition error
    end
~~~

Step-by-step details:

1. **Caller has a starting identity:** This may be a legitimately signed-in human, a workload carrying a role, an AWS service, or a federated identity. Not every source uses the exact STS API named **AssumeRole**.
2. **Caller requests the role:** In the standard case, it calls **sts:AssumeRole** with the role ARN and role session name; optionally including duration, MFA, ExternalId, session tags, source identity, and session policy.
3. **AWS checks permissions:** The role's trust policy, relevant caller-side permissions, conditions, and organizational boundaries all participate in allowing or denying.
4. **STS issues temporary credentials:** Consisting of **AccessKeyId**, **SecretAccessKey**, **SessionToken**, and an **Expiration** timestamp. This set is required to sign AWS requests for the session.
5. **Application uses session credentials:** Subsequent API calls are evaluated based on the effective permissions of the assumed-role session and relevant resource policies.
6. **Session expires:** The application must obtain a new session via an authorized flow; temporary credentials should never be expected to work indefinitely.

Depending on the identity model, AWS provides related STS APIs such as **AssumeRole**, **AssumeRoleWithWebIdentity**, and **AssumeRoleWithSAML**. When workloads retrieve credentials from service-specific metadata/endpoints, SDKs usually handle this automatically according to the role attached to the service.

### Role ARN vs. Session ARN

A role is referenced by an ARN such as:

~~~text
arn:aws:iam::444455556666:role/InventoryReadRole
~~~

After assumption, the session identity typically appears in the form:

~~~text
arn:aws:sts::444455556666:assumed-role/InventoryReadRole/report-2026
~~~

The two ARNs are **different**: the first identifies the **role**; the second identifies **an assumed-role session**. This matters when reading CloudTrail, writing principal-based conditions, and troubleshooting authorization issues.

## 3. Trust Policy Structure

A trust policy is placed directly on the **IAM role**, under **Trust relationships / Assume role policy**. The syntax mirrors an IAM JSON policy document, usually featuring a **Principal** section specifying who is trusted.

Example of a role in account B trusting a specific role from account A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBuildRunnerFromAccountA",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/BuildAuditRunner"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Meaning of each field:

| Field | How to read it |
| --- | --- |
| **Version** | IAM JSON policy language version, typically 2012-10-17; **not** a user-incremented document version |
| **Statement** | List of individual rules |
| **Sid** | Label identifying the rule; does not alter permissions |
| **Effect** | Allow or Deny |
| **Principal** | Who the trust rule applies to, e.g., an AWS role or service principal |
| **Action** | Permitted STS operation, e.g., sts:AssumeRole or sts:AssumeRoleWithWebIdentity |
| **Condition** | Additional constraints based on context keys like sts:ExternalId, aws:MultiFactorAuthPresent |

**Caution:** If an ARN of the form **arn:aws:iam::111122223333:root** is used as the AWS principal in a trust policy, it usually means **delegating trust to the account** so that account decides which principals may assume the role via identity-based permissions; it **does not refer exclusively to the root user**. Specify the exact role ARN when you want to narrow down who can assume the role. Avoid overly broad principals (especially wildcards) without carefully tested defensive conditions.

A trust policy can contain multiple statements and conditions. When debugging, inspect **every** statement, including explicit Denies, not just a single Allow line.

## 4. Cross-Account Assume Role: Both Sides Must Cooperate

Consider a company separating accounts to reduce blast radius:

- **Account A — 111122223333:** holds role **BuildAuditRunner**, which runs a reporting job.
- **Account B — 444455556666:** holds the reporting bucket **audit-inventory-example**, role **InventoryReadRole**, and the target data.
- Goal: the job from A temporarily assumes the role in B to **list and read objects** in B's bucket without sharing IAM user access keys from B.

### 4.1. Side B: Trust policy specifying who can assume the role

On **InventoryReadRole** in B, attach the trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustBuildAuditRunner",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/BuildAuditRunner"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This makes the role in A a trusted principal **at the front door** of the role in B.

### 4.2. Side A: Allow the caller to call AssumeRole

Attach the following identity-based policy to **BuildAuditRunner** in A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MayAssumeInventoryReadRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/InventoryReadRole"
    }
  ]
}
~~~

In a standard **cross-account** scenario, AssumeRole permission must be allowed by **the source account** and accepted by the **target account's trust policy**. If either side is missing, AssumeRole may be denied. SCPs, permissions boundaries, or explicit Denies can restrict it further.

**Advanced note:** For certain **same-account** cases, a trust policy directly listing an IAM principal may suffice to grant assume-role permission without needing a separate identity policy Allow, depending on principal type and grant style. Do not mechanically apply the "two Allows always required" rule to every principal type; evaluate according to context.

### 4.3. Side B: What the role can do once assumed

Identity-based permissions policy attached to **InventoryReadRole** in B:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyReportBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::audit-inventory-example"
    },
    {
      "Sid": "ReadOnlyObjectsInReportBucket",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::audit-inventory-example/*"
    }
  ]
}
~~~

Now the assumed-role session has bucket read permissions per the example above, **but has no permission to write objects, delete the bucket, or manage IAM**. If the bucket has a Deny bucket policy, KMS encryption, or other controls, effective access also depends on those layers.

Three policy documents to remember:

| Location | Policy | Question answered |
| --- | --- | --- |
| Account B, InventoryReadRole | **Trust policy** | Which principal from A can assume the role? |
| Account A, BuildAuditRunner | **Identity policy** | Is the caller allowed to call sts:AssumeRole on this ARN? |
| Account B, InventoryReadRole | **Permissions policy** | After assuming, which resources can the session operate on? |

This is a common pattern for **cross-account CI/CD**, **centralized administration**, **reading reporting data**, or **a workload in one account calling resources in another**.

## 5. Practice Reading and Using Roles with AWS CLI

**Prerequisites:** access to two authorized lab accounts; permission to create or update roles/policies in the learning environment; AWS CLI configured from a valid identity source. The ARNs, account IDs, and bucket names below are **illustrative values** and must be replaced with real resources from your lab environment. Never use production accounts to test learning policies.

### 5.1. Confirm the source principal

First, verify the profile configuration used to call AssumeRole:

~~~bash
aws sts get-caller-identity --profile runner-a
~~~

The expected principal is **BuildAuditRunner** in account A, which may appear as an assumed-role ARN if the source profile itself uses a role. If it is a different principal, the trust policy in B must be updated to match the actual authorized identity; never widen Principal to a wildcard to bypass an error.

### 5.2. Call STS directly to inspect the output

~~~bash
aws sts assume-role \
  --profile runner-a \
  --role-arn arn:aws:iam::444455556666:role/InventoryReadRole \
  --role-session-name inventory-lab-01 \
  --duration-seconds 3600
~~~

An abbreviated response looks like:

~~~json
{
  "Credentials": {
    "AccessKeyId": "ASIA...EXAMPLE",
    "SecretAccessKey": "***",
    "SessionToken": "***",
    "Expiration": "2026-11-20T04:00:00+00:00"
  },
  "AssumedRoleUser": {
    "Arn": "arn:aws:sts::444455556666:assumed-role/InventoryReadRole/inventory-lab-01"
  }
}
~~~

The values above illustrate the structure only, **not usable credentials**. In real operations, **never paste command outputs containing SecretAccessKey and SessionToken into chat, logs, tickets, or repositories**. Be careful with terminal history, CI output, and copying JSON into files.

AWS CLI/SDKs can automatically create and refresh sessions using an assume-role profile, reducing manual handling of secrets. Example configuration in **AWS CLI config**:

~~~ini
[profile inventory-read]
role_arn = arn:aws:iam::444455556666:role/InventoryReadRole
source_profile = runner-a
role_session_name = inventory-lab-01
region = ap-southeast-1
~~~

Once the **runner-a** profile is configured and has valid permissions:

~~~bash
aws sts get-caller-identity --profile inventory-read
aws s3 ls s3://audit-inventory-example --profile inventory-read
~~~

The first command confirms you are in the **assumed role** in B. The second verifies real S3 permissions. If an operation fails, inspect the error message and policy layers before changing permissions.

### 5.3. Observe the audit trail

In **AWS CloudTrail**, filter for STS events named **AssumeRole** around the time of the lab; inspect the role ARN, source principal, session name, and outcome. For resource API calls, you can see the **assumed-role session** as the request caller. Which CloudTrail events are recorded and how they are queried depend on trail/event data store settings, event categories, and services. Never assume all S3 data events are enabled by default.

**After the lab:** Delete or revoke demo roles/policies and resources using your environment's approved process; check associated costs, especially for any companion services used.

## 6. Trusting AWS Services: EC2, Lambda, and ECS

Workloads on AWS should use **service-attached IAM roles** so SDKs automatically fetch short-lived credentials instead of placing access keys into images, environment variables, or config files.

### 6.1. EC2 instance role

Example trust policy for an EC2 role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

The role is attached to EC2 via an **instance profile**. Applications on the instance can use the AWS SDK default credential chain to obtain credentials from the **Instance Metadata Service (IMDS)** instead of managing keys manually. Enable and enforce **IMDSv2** per security best practices; restrict metadata access and avoid giving all processes on one machine overly broad shared permissions if they require separate boundaries.

### 6.2. Lambda execution role

Example trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

An **execution role** grants permissions for the Lambda function to call AWS resources and write logs when granted appropriate permissions. If the function needs to read DynamoDB and write objects to S3, grant only the exact actions/resources required. A **Lambda resource-based policy** allowing another service to **invoke the function** is separate from the function's **execution role**.

### 6.3. ECS task role and task execution role

In Amazon ECS, do not confuse the two roles:

- **Task role:** The identity used by **code inside the container** to call S3, SQS, DynamoDB, or Secrets Manager (if needed).
- **Task execution role:** Permissions used by the task execution agent for operations like **pulling images from ECR, sending logs**, and certain initialization integrations per configuration.

Both typically use **ecs-tasks.amazonaws.com** in their trust policies, but **their permissions policies must differ by responsibility**. If a task needs to read a bucket, that permission belongs on the **task role**—do not put it in the execution role just because the container runs in ECS.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

### 6.4. EKS: Pod identity

For Amazon EKS, two common models are **IAM Roles for Service Accounts (IRSA)** via OIDC and **EKS Pod Identity**. Each has its own trust mechanism and conditions. In IRSA, a Kubernetes ServiceAccount typically maps to the **sub** condition in the OIDC token. With EKS Pod Identity, trust uses the corresponding service principal and required STS actions, while Pod Identity associations are managed through EKS.

**Do not copy trust policies verbatim from EC2, Lambda, or ECS to EKS**: the principals, tokens, and authentication conditions differ. Choosing between them depends on cluster type, workload compatibility, and identity governance.

## 7. Federation: AssumeRoleWithWebIdentity and AssumeRoleWithSAML

In multi-team/multi-software systems, human users or CI/CD runners may already be authenticated by an **identity provider (IdP)** outside AWS. Federation reduces the need to create IAM users with long-term access keys.

### 7.1. OIDC for CI/CD or workloads

For example, GitHub Actions uses OIDC to assume a role in an AWS account. The AWS account needs an IAM OIDC provider with the matching issuer, appropriate audience, and a trust policy restricting claims:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GithubMainBranchOnly",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::444455556666:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:sample-org/sample-repo:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

This example allows only workflows carrying a **subject claim matching the exact repository and main branch** to be considered for assuming the role. In certain GitHub events, the **sub** format changes when using environments, pull requests, or custom claim templates; verify the actual claim values before configuring trust.

**Never use** overly broad conditions like repo:* or omit audience/subject checks without a clear justification. OIDC only proves token origin and accepted claims; **the role's permissions policy must still restrict** deployment or resource-read permissions.

### 7.2. SAML and enterprise sign-in

With SAML 2.0, role trust typically sets the **Federated principal** to an IAM SAML provider, action **sts:AssumeRoleWithSAML**, and conditions on audience or required attributes. Settings must match between the IdP and AWS.

When deploying employee sign-in via **AWS IAM Identity Center**, permissions are usually managed through **permission sets** and account/group/user assignments provided by the service. Never manually edit the trust policies of IAM Identity Center-managed roles outside an official procedure.

### Distinguishing the Role Assumption Mechanisms

| API / mechanism | Used for | Key authentication inputs |
| --- | --- | --- |
| **AssumeRole** | Already-authenticated AWS principal switching to another role | Caller credentials, role ARN, session name; optional MFA/ExternalId |
| **AssumeRoleWithWebIdentity** | OIDC/web identity token from a trusted IdP | ID token, role ARN, session name; trust checks issuer/audience/subject |
| **AssumeRoleWithSAML** | SAML identity federated with AWS | SAML assertion and matching principal/role |
| **Service-supplied credentials** | EC2/ECS/Lambda/EKS via built-in integration | Role attached to workload; SDK fetches/refreshes via credential provider chain |

## 8. Trust Policy Conditions to Reduce Risk

Allowing the right principal is only the first layer. Conditions help prevent the role from being assumed in unintended contexts.

### 8.1. MFA for human administrative operations

When an IAM principal uses STS AssumeRole and MFA is required, the trust policy can require:

~~~json
"Condition": {
  "Bool": {
    "aws:MultiFactorAuthPresent": "true"
  }
}
~~~

This condition must match the right identity type and authentication flow. An automated workload or federated session that does not carry the MFA context key like an IAM caller will be denied. Never blindly insert an MFA condition into EC2/Lambda or OIDC roles.

### 8.2. ExternalId for third parties and the confused deputy problem

Scenario: a company hires a SaaS provider to manage resources inside the customer's AWS account. Many customers may trust the exact same provider principal. Without proper binding, a malicious party could try to trick the provider into using another customer's permissions: the **confused deputy**.

In the provider **AssumeRole** scenario, add a condition:

~~~json
"Condition": {
  "StringEquals": {
    "sts:ExternalId": "tenant-customer-unique-value"
  }
}
~~~

The provider passes that same value in the **ExternalId** parameter of AssumeRole. ExternalId should be **uniquely assigned per customer relationship**, managed by the service provider per the integration design. **ExternalId is not a secret password** and does not replace IAM principal restrictions or caller permissions; it is a contextual constraint reducing customer mix-up risk.

### 8.3. SourceArn and SourceAccount for AWS services

In scenarios where an AWS service calls a role/service on behalf of your resources, conditions like **aws:SourceArn** and **aws:SourceAccount** restrict which source can trigger the request and reduce confused deputy risk.

Sample template **for structural illustration only**:

~~~json
"Condition": {
  "StringEquals": {
    "aws:SourceAccount": "444455556666"
  },
  "ArnLike": {
    "aws:SourceArn": "arn:aws:some-service:ap-southeast-1:444455556666:some-resource/example"
  }
}
~~~

**Do not deploy this verbatim to a real environment:** ARN prefixes, source formats, and available context keys differ by service. Check the documentation of **the exact service** to confirm whether it supports these keys in trust policies and how to format the ARN.

### 8.4. Source identity and session tags

- **Source identity:** In supported STS flows, a source identity can be attached to the session to preserve attribution across role assumptions. Permission to use **sts:SetSourceIdentity** must be allowed in the relevant trust policy; check additional requirements for role chaining.
- **Session tags:** Attach session attributes such as project, team, or environment. To pass tags during AssumeRole, the trust policy must allow **sts:TagSession**; keys/values can be restricted using appropriate STS/AWS conditions.
- **ABAC (Attribute-Based Access Control):** Role permissions can rely on principal tags, resource tags, and consistent conditions. However, **caller-supplied session tags are not automatically trustworthy**. Strictly control who can set which tags and which tags can be overridden.
- **RoleSessionName:** Useful for reading audit logs, and can be constrained via **sts:RoleSessionName** when naming conventions are needed. Avoid putting personal data or secrets into session names.

Source identity, session name, and session tags serve related yet distinct purposes: **source attribution**, **session identification**, and **authorization attributes**.

## 9. Effective Session Permissions: Why Does AccessDenied Happen Even After AssumeRole Succeeds?

AssumeRole only completes the step of **switching/establishing identity context**. When the session calls S3, DynamoDB, KMS, EC2, CloudWatch, or any other API, AWS performs **authorization** evaluation again.

Layers commonly involved:

1. **Identity-based permissions** attached to the role: which Allows are granted for the action/resource?
2. **Session policies**, if passed: further narrow session permissions; cannot grant permissions exceeding the role.
3. **Permissions boundary**, if applied to the role: caps permissions granted via identity policies.
4. **AWS Organizations SCP** (and corresponding organizational control layers): sets permission ceilings for principals in affected member accounts; SCPs do not grant Allow on their own.
5. **Resource-based policy**: can allow or deny depending on resource and principal; interaction with implicit deny in identity/boundary/session policies has exceptions based on the specified principal type, especially when granting directly to an **assumed-role session ARN**.
6. **Explicit Deny and special policies**: an explicit Deny in an applicable policy layer typically overrides Allow; VPC endpoint policies, KMS key policies, and other service conditions may also apply.

Example: role InventoryReadRole has s3:GetObject, but the S3 object is encrypted with **SSE-KMS**. Reading the object can still fail if the session lacks appropriate KMS permissions or the key policy does not permit it. Likewise, a bucket policy with a Deny based on network/identity conditions can still block access.

**Never infer permissions from a single JSON policy.** Inspect the action, resource ARN, principal at call time, request context, session policy, and every applicable control layer. In multi-account setups, inspect both the resource side and the principal side.

### Session policies for narrowing permissions

When calling AssumeRole, the caller can pass an **inline session policy** or **managed session policy ARN** as supported by the API. For example, a role can read an entire bucket, but one session should only read a reports prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::audit-inventory-example/reports/2026/*"
    }
  ]
}
~~~

The assumed-role session receives only the intersection of the role's permissions and the session policy, subject to all other control layers. A session policy **cannot grant s3:PutObject** if the role does not already have it. Passing an overly narrow session policy can cause previously working calls to start returning AccessDenied.

## 10. Session Duration, Refresh, and Role Chaining

- Every STS session has an **Expiration**. Users/applications must refresh before continuing; SDKs and AWS CLI credential providers typically handle this automatically when properly configured.
- For **AssumeRole**, the **DurationSeconds** parameter and the role's **maximum session duration** govern valid lifetime. A role's maximum session duration can typically be configured from **1–12 hours**, though specific APIs/flows have their own limits.
- **Role chaining** is using credentials from one assumed role to assume another role. With STS AssumeRole in role chaining, the new session duration is capped at **1 hour**, even if the target role allows longer.
- Duration of role credentials supplied natively by AWS services follows service-specific mechanisms; do not blindly apply CLI duration rules to every service integration.
- Revoking access: editing a trust policy blocks **future assumptions**, but **already-issued credentials remain valid until expiration** unless appropriate session invalidation/revocation mechanisms are executed. During incident response, active sessions must also be addressed.

### Why never store temporary credentials long-term?

Temporary credentials are still **secrets that can be abused while valid**. Never commit them to Git, Docker images, CI logs, URLs, or shared folders; avoid displaying STS command output on shared screens. Use workload-attached IAM roles and AWS SDK/CLI credential providers so you do not have to manage the access key, secret key, session token trio manually.

## 11. Troubleshooting by Symptom

| Symptom | Common causes | How to check |
| --- | --- | --- |
| **AccessDenied at AssumeRole** | Trust policy does not trust the right principal; caller lacks sts:AssumeRole; Deny/SCP/boundary; missing MFA/ExternalId | Run sts:GetCallerIdentity; inspect trust, caller identity policy, Conditions, and org limits |
| **AccessDenied reading S3 after AssumeRole succeeds** | Role lacks s3:GetObject/ListBucket; resource policy Deny; KMS key policy/permission; overly narrow session policy | Confirm session ARN; verify actual action/resource and resource-side policies |
| **The security token included in the request is expired/invalid** | Expired session; missing SessionToken; mixing credentials from multiple profiles | Check Expiration, credential source/provider chain, and system clock; refresh session |
| **Principal ARN mismatch** | Trust references a different role, IAM principal changed, or role was deleted and recreated | Check GetCallerIdentity, ARNs, and trust relationship; update to the valid principal |
| **OIDC AssumeRoleWithWebIdentity rejected** | Issuer, audience, subject, token expiry, or IAM OIDC provider mismatch | Inspect token claims, trust Condition, provider, and live workflow |
| **Session lasts at most one hour** | Caller is role chaining via AssumeRole | Trace the role chain and redesign credential acquisition appropriately |
| **AWS service cannot use the role** | Wrong service principal, role not attached properly, missing instance profile or role mapping | Check role type and integration config for EC2/ECS/Lambda/EKS |
| **CloudTrail does not show expected data APIs** | Required data event type / logging scope is not enabled | Check trail or event data store configuration, account, and Region |

### Concise Troubleshooting Workflow

~~~text
1. Confirm the actual principal with sts:GetCallerIdentity.
2. Did the failure happen at the STS AssumeRole call or the subsequent service call?
   ├─ At STS: inspect trust policy, caller's sts:AssumeRole,
   │         principal, Condition, SCP/boundary, and STS API type.
   └─ At service: inspect session permissions, session policy, resource policy,
                  key policy, and resource request context.
3. Trace the exact request/timestamp/account in CloudTrail and application logs.
4. Make a minimal change adding only the missing permission; avoid wildcards.
5. Re-verify success and confirm out-of-scope permissions remain denied.
~~~

When complex policy conflicts are suspected, you can use **IAM Policy Simulator** or **IAM Access Analyzer** to assist evaluation within what the tools support, combined with real testing in a controlled environment. Simulation results cannot replace every runtime condition of individual services.

## 12. Multi-Component System Example

An order-processing application deployed in a chosen Region across two Availability Zones for high availability:

~~~mermaid
flowchart TB
    C[Customer] --> ALB[Application Load Balancer]
    ALB --> ECS[ECS task: Order API]
    ECS --> D[(RDS: orders)]
    ECS --> S3[S3: invoices]
    ECS --> Q[SQS: invoice generation requests]
    Q --> L[Lambda: generate invoice]
    subgraph IAM[Role permissions and trust]
        T1[ECS task role]
        T2[Lambda execution role]
        T3[Cross-account reporting role]
    end
    ECS -. SDK credentials .-> T1
    L -. SDK credentials .-> T2
    L --> S3
    Rep[Account A reporting job] --> STS[STS AssumeRole]
    STS --> T3
    T3 -. Controlled report read .-> S3
    ECS --> CW[CloudWatch]
    L --> CW
~~~

**Example permission design:**

| Component | Trust / identity | Least-privilege permissions to consider |
| --- | --- | --- |
| ECS Order API | Task role trusting **ecs-tasks.amazonaws.com** | Only required SQS send actions, S3 actions to create/read invoices; RDS authentication per chosen model |
| Invoice-generating Lambda | Execution role trusting **lambda.amazonaws.com** | Read input and write only to the exact S3 prefix; appropriate CloudWatch logging permissions |
| Reporting job in account A | Role from A assumes a reporting role in account B | AssumeRole permission scoped by ARN; target role reads only the S3 reports prefix |
| Deployment CI/CD | Role trusting OIDC or a controlled federation solution | Update only resources required for deployment; add repo/branch/environment conditions |

**IAM's boundaries:** IAM decides which AWS APIs are allowed; IAM **does not automatically secure** traffic between containers and databases, nor does it set up private subnets, Multi-AZ, backup recovery, or error alerts. To achieve system security and reliability requirements, you must still configure VPC/security groups, TLS, database credentials, logging, CloudWatch alarms, backup/restore plans, and AWS Budgets. As Lambda or ECS scales with load, role permissions stay constant while **the number of sessions/API calls** may grow—watch quotas and corresponding costs.

## 13. Pre-Deployment Trust Policy Checklist

- [ ] Clearly identified **which account** owns the role, who needs to assume it, and why.
- [ ] **Principal** is restricted to the exact role/user/service/IdP, avoiding unnecessary broadening.
- [ ] **STS Action** matches the real flow: AssumeRole, AssumeRoleWithWebIdentity, or AssumeRoleWithSAML.
- [ ] For cross-account access, verified **both target-side trust and source-side caller AssumeRole permission**.
- [ ] For AWS services, verified the **service principal** and proper role attachment method (EC2 instance profile, Lambda execution role, ECS task role...).
- [ ] Applied **MFA, ExternalId, OIDC aud/sub, SourceArn/SourceAccount, source identity/session tags** where supported and required.
- [ ] Role permissions include only **necessary actions/resources**, minimizing wildcards; evaluated session policies, boundaries, SCPs, and resource policies.
- [ ] Temporary credentials are refreshed safely; secrets are never stored in source control or logs.
- [ ] CloudTrail, alerts/checks for trust changes, and procedures to trace who assumed a role are in place.
- [ ] Tested both a **permitted path** and at least one **denied path** to prove permission boundaries actually hold.
- [ ] Considered costs and operations of services accessed via the role, such as S3, KMS, CloudWatch, or multi-AZ deployments.

## 14. Self-Check Questions and Exercises

**Question 1.** A Lambda function successfully assumes its execution role, yet calling S3 GetObject returns AccessDenied. What should you do first: edit the Lambda's trust policy, or check the role's permissions policy, bucket policy, and KMS? **Hint:** determine whether the failure occurred during role assumption or during the S3 API call.

**Question 2.** Account A has a policy allowing role A to call sts:AssumeRole into B. Role B does not yet trust principal A. What happens to the call? **Hint:** having permission to call an API at the source is not enough to pass the trust gate at the destination.

**Question 3.** A CI pipeline uses GitHub OIDC. Why should you restrict aud, repository, and branch/environment in the trust policy? **Hint:** the same token issuer serves many different repositories and workflows.

**Controlled hands-on exercise:**

1. Use two lab accounts or two roles in an authorized learning environment. Create role **ReportReadRole** with trust restricted to one specific principal.
2. Grant the source principal **sts:AssumeRole** to that exact role ARN and attach a policy allowing read-only access to a test bucket/prefix on the target role.
3. Use an AWS CLI profile to assume the role, verify **GetCallerIdentity**, and test reading a permitted object.
4. Try calling **s3:PutObject** or reading an out-of-scope prefix and record **AccessDenied** as proof of least privilege.
5. Inspect the **AssumeRole** event in CloudTrail; note the role ARN, session name, and source/target accounts without saving secrets.
6. Temporarily adjust one trust condition in a controlled manner to cause a denied AssumeRole attempt, then restore the valid policy and re-verify.

**Completion criteria:** Learners can explain **who trusts whom**, **who can call STS**, **what the assumed-role session can do**, and **why a request can still be denied** after AssumeRole succeeds.

## 15. Summary

The **trust policy** is **the front door of an IAM role**. **AssumeRole and related federation mechanisms** provide a session identity with **temporary credentials**. The **permissions policy**, session policy, resource policy, and other control layers decide **which APIs the session can call**. In real-world AWS environments, the safe choice is identifying exact principals, restricting both trust and permissions, letting services/SDKs manage credentials, checking CloudTrail, and verifying permissions in a real environment.

This knowledge connects directly to choosing services, designing Region/AZ systems, running workloads on EC2/ECS/Lambda, accessing S3/RDS, integrating SQS, and monitoring costs. Roles only solve **identity and authorization**; a complete architecture still requires networking, backups, reliability, observability, and cost control.

**Official references for implementation:** AWS IAM documentation on *Role trust policies*, *IAM roles*, and *Policy evaluation logic*; AWS STS documentation on *AssumeRole*, *AssumeRoleWithWebIdentity*, *AssumeRoleWithSAML*, *Session policies*, and *Role chaining*; guides on *Cross-account access*, *AWS Well-Architected Security Pillar*, and *AWS CloudTrail*. Always check the latest policies, context keys, and service limits by principal type and Region before deploying to production.
