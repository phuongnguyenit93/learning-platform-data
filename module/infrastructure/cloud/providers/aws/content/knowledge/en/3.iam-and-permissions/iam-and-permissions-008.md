# Permissions Boundaries, Session Policies, and Relationship with SCPs

> **Chapter:** IAM and Permissions  
> **Module:** `CLOUD_PROVIDERS_AWS` — the AWS ecosystem, from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless services.

## Learning Objectives

When designing applications on AWS, a permission marked `Allow` in an IAM policy **is not guaranteed to execute**. AWS also evaluates other boundary mechanisms at the identity, session, and organization levels. Understanding these layers helps design secure authorization, delegate administration safely without exceeding limits, diagnose `AccessDenied`, and protect both lab and production environments.

After this lesson, you can:

1. Explain the differences between **identity-based policies**, **permissions boundaries**, **session policies**, **Service Control Policies (SCPs)**, and **resource-based policies**.
2. Predict effective permissions when multiple `Allow`/`Deny` layers apply, distinguishing **implicit deny** from **explicit deny**.
3. Understand when a boundary is attached to an IAM user/role, when a session policy is passed to AWS STS, and when an SCP applies to an AWS account.
4. Design examples for safe IAM role delegation, restricting data-handling sessions, and blocking cost-generating services.
5. Recognize **resource-based policy exceptions**, multi-account governance, and methods for troubleshooting permission errors.

## 1. Why Are Multiple Permission Boundary Layers Needed?

Suppose a development team is building a serverless application:

- A Lambda's IAM role is allowed to read and write objects in S3.
- An operator wants to create additional roles for labs, without granting permissions beyond an approved boundary.
- A customer support session should only have read access, even though the role it assumes has write permissions.
- The AWS Organizations governance team wants to prevent lab accounts from creating certain expensive services or configurations.

Relying on a single IAM policy attached to a role makes it very difficult to satisfy all of these requirements simultaneously. AWS uses the following primary layers:

| Mechanism | Where attached or configured? | Effect | Does it grant permissions on its own? |
|---|---|---|---|
| **Identity-based policy** | IAM user, group, or role | Grants/denies operations for an identity | **Can grant** via `Allow` |
| **Permissions boundary** | IAM user or IAM role | Defines the permission ceiling for identity-based policies | **No** |
| **Session policy** | Passed when creating certain temporary STS sessions | Narrows session permissions relative to the underlying identity | **No** |
| **SCP** | Root/OU/account in AWS Organizations | Maximum permission limit for principals in member accounts | **No** |
| **Resource-based policy** | Resources like S3 buckets, KMS keys; IAM role trust policy is a special case | Allows/denies principals accessing the resource or assuming the role | **Can grant**, depending on resource type and context |
| **RCP** (*Resource Control Policy*) | Root/OU/account in Organizations, affecting resources in the account | Limits permissions on resources in governed accounts | **No** |

This lesson focuses on **permissions boundaries, session policies, and SCPs**; mechanisms such as RCPs, VPC endpoint policies, ACLs, and KMS-specific requirements are mentioned so learners know additional conditions may apply in practice.

### 1.1. Mental diagram of boundaries

~~~mermaid
flowchart TD
    A[API request: principal + action + resource + context] --> B{Is there an applicable explicit Deny?}
    B -- Yes --> X[Deny]
    B -- No --> C{Is there a valid Allow path?}
    C -- No --> X
    C -- Yes --> D[Evaluate applicable boundary layers]
    D --> E[Permissions boundary if attached]
    D --> F[Session policy if passed]
    D --> G[SCP on member account]
    D --> H[RCP / service-specific policies if applicable]
    E --> I{Conditions satisfied to allow?}
    F --> I
    G --> I
    H --> I
    I -- Yes --> Y[Allow]
    I -- No --> X
~~~

**This diagram illustrates conceptual reasoning**, not a complete simulation of AWS's internal evaluation order. In particular, **resource-based policies granting permissions directly to certain principal types** can alter how implicit deny from boundaries/session policies applies; see section 6.

### 1.2. Most important rules

- **Default is deny** (*implicit deny*): without a valid `Allow`, the request is not granted.
- **Explicit Deny always overrides** `Allow` in any policy effective for the request.
- **Boundaries, session policies, and SCPs are all limits**, so merely writing `Allow` in a boundary mechanism creates no new permissions.
- For permissions granted via an **identity-based policy**, when boundaries apply together, the operation is allowed only if the **identity-based policy, boundary, session policy, and SCP** each permit it, and no other policy layer blocks it.
- Effects of `Condition`, principal, resource ARN, Region, and request type must still be evaluated; comparing action names alone is insufficient.

## 2. Permissions Boundary: Permission Ceiling for an IAM User or Role

### 2.1. Concept and lifecycle

A **Permissions boundary** is an **IAM managed policy** selected as a permission limit for an **IAM user or IAM role**. It limits the maximum permissions that identity-based policies can grant to that entity.

- Each user/role can have **one** permissions boundary attached at a time.
- Boundaries use a **managed policy**, not an inline policy attached directly as a boundary.
- Boundaries cannot be attached to IAM groups and do not grant permissions independently.
- When editing a managed policy used as a boundary, effective permissions of every user/role referencing that boundary can change; version control and approval workflows are needed.
- A boundary remains attached to a user/role after someone assumes the role; in standard cases, it continues limiting permissions granted through the role's identity-based policies.

**Example:** Role `aws-lab-dev-operator` has an identity policy allowing `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject`. Its boundary only allows `GetObject` and `PutObject`. Result: `DeleteObject` receives **implicit deny from the boundary**, even though the identity policy has `Allow`.

Simple way to reason about it:

~~~text
Permissions from identity-based policy
                ∩
        Permissions boundary
                =
Identity-based permissions after boundary
~~~

### 2.2. Example IAM managed policy used as a boundary

Suppose the practice bucket is named `aws-lab-demo-data`. The policy below can be created as customer managed policy `aws-lab-boundary` and attached as a boundary to an IAM role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTrainingBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::aws-lab-demo-data"
    },
    {
      "Sid": "ReadWriteTrainingObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::aws-lab-demo-data/*"
    }
  ]
}
~~~

This is an **illustrative permission boundary**, not a complete permission set for operating an application. Suppose the role's identity-based policy also includes `s3:DeleteObject`; the boundary above does not allow `DeleteObject`, so the role cannot delete objects via its identity-based permission path.

Notes when reading the JSON:

- `s3:ListBucket` uses the **bucket ARN**; `s3:GetObject` and `s3:PutObject` use the **object ARN** with `/*`.
- `Allow` in a boundary only sets the upper limit; if the role lacks a matching `Allow` in its identity-based policy, it still has no permission.
- The boundary must account for every action the application actually uses, including supporting actions for KMS encryption, tagging, or accessing other resources.
- Explicit `Deny` statements inside a boundary still take effect under policy evaluation logic.

### 2.3. Delegating role management while enforcing a boundary

Common scenario: the platform team wants application teams to create their own workload roles, provided every new role is constrained by `aws-lab-boundary`. The delegated user needs role-creation permission conditioned on requiring that boundary.

Example statement in the **delegated user's identity-based policy**:

~~~json
{
  "Sid": "CreateRolesOnlyWithApprovedBoundary",
  "Effect": "Allow",
  "Action": "iam:CreateRole",
  "Resource": "arn:aws:iam::111122223333:role/aws-lab-dev-*",
  "Condition": {
    "StringEquals": {
      "iam:PermissionsBoundary": "arn:aws:iam::111122223333:policy/aws-lab-boundary"
    }
  }
}
~~~

**Account ID `111122223333` is illustrative only.** The example above constrains **CreateRole**; to build a complete delegation model, administrators must also:

1. Restrict `iam:AttachRolePolicy`, `iam:PutRolePolicy`, `iam:UpdateAssumeRolePolicy`, and related actions to the approved set of manageable roles.
2. Prevent delegated users from **removing or replacing the boundary** with a weaker one by controlling `iam:DeleteRolePermissionsBoundary`, `iam:PutRolePermissionsBoundary`, and permissions to edit the managed policy used as the boundary.
3. Control `iam:PassRole` and which roles can be passed to EC2/Lambda to avoid privilege escalation paths.
4. Check the trust policy: **who can assume the role** is a separate question from **which APIs the role may call**.

**Mistake to avoid:** assuming enforcing a boundary at role creation eliminates all escalation paths. Someone able to change boundaries, alter related policies, or pass a privileged role can bypass the original intent.

## 3. Session Policy: Narrowing Permissions for a Temporary Session

### 3.1. When does a session policy apply?

A **Session policy** is a JSON policy passed into certain **AWS Security Token Service (STS)** APIs when creating a session via a role or federation, such as:

- `AssumeRole`
- `AssumeRoleWithSAML`
- `AssumeRoleWithWebIdentity`
- `GetFederationToken` (with its own rules)

With `AssumeRole`, you can pass one **inline session policy** via the `Policy` parameter, and/or ARNs of up to **10 managed session policies** via `PolicyArns`; also check the API's plaintext and packed policy size limits. Referenced managed session policies must reside in the same account as the role.

A session policy **does not modify** the IAM role; it restricts permissions only for **the newly created STS session**. Other sessions assuming the same role without passing this session policy can have different effective permissions, subject to applicable policies.

> **Not every temporary session carries a user-supplied session policy.** Without an additional session policy, no narrowing comes from that parameter; the role remains governed by IAM, boundaries, SCPs, resource policies, and related mechanisms.

### 3.2. Example downgrading permissions for an S3 session

Suppose role `aws-lab-dev-operator` has permission to read and write objects in a bucket. During a support session, a user only needs read access. Create file `session-read-only.json`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOnlyTrainingObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-demo-data/*"
    }
  ]
}
~~~

If the current principal is permitted to assume the role and the role's trust policy allows it, you can run:

~~~bash
aws sts assume-role \
  --role-arn arn:aws:iam::111122223333:role/aws-lab-dev-operator \
  --role-session-name training-read-only \
  --policy file://session-read-only.json \
  --query '{SessionArn:AssumedRoleUser.Arn,Expires:Credentials.Expiration}' \
  --output json
~~~

The example command **prints only the ARN and expiration**, avoiding printing credential fields to the terminal. To actually call S3 with the new session, the client must use the temporary credentials returned by STS through secure handling; never paste access key/secret/session token values into exercises, repositories, logs, or shared screens.

Points to distinguish:

- The role trust policy determines whether the principal can **assume the role**; the caller's identity policy or equivalent permissions may also be needed for `sts:AssumeRole`.
- This session policy allows only `s3:GetObject`; it does not allow `s3:PutObject` even if the role has `Allow`.
- If the role lacks `Allow` for `s3:GetObject`, the session policy cannot open read access on its own.
- If a boundary or SCP blocks `GetObject`, a session policy `Allow` still cannot make the operation succeed.
- For permissions granted via a resource-based policy directly to an **STS session ARN**, exceptions apply; see section 6.

### 3.3. How does a session policy differ from a permissions boundary?

| Criterion | Permissions boundary | Session policy |
|---|---|---|
| Target restricted | IAM user/role | Specific STS session |
| How applied | Select a managed policy as boundary on the IAM entity | Pass inline/managed policies when creating the session |
| Active duration | For as long as the boundary remains attached to the entity | Only for the lifetime of the temporary session |
| Modifies role policy? | No | No |
| Used for | Safe administrative delegation, long-term permission caps | Granting only needed permissions for a single work session |
| Grants new permissions? | No | No |

**Easy-to-remember analogy:** a boundary is like a **fixed fence around the role**, whereas a session policy is like **the approved scope of work for one work session**. Neither replaces granting permissions in an identity-based policy.

## 4. SCP: Guardrails at the AWS Organizations Level

### 4.1. Where do SCPs apply?

A **Service Control Policy (SCP)** is managed through **AWS Organizations**, requiring **all features** enabled in the organization. SCPs can be attached to the **organization root, an Organizational Unit (OU), or a member account**.

~~~mermaid
flowchart TD
    R[Organization root: SCP] --> O[Sandbox OU: SCP]
    R --> P[Production OU: SCP]
    O --> A[Member account Lab A]
    O --> B[Member account Lab B]
    P --> C[Member account Prod]
    A --> U[IAM users, roles, root in Lab A]
~~~

For member accounts, SCPs at each applicable organizational level can restrict permissions. This lets platform teams enforce shared rules: e.g., blocking resource creation in unapproved Regions, disabling unused services, protecting logging, or limiting cost-risky actions.

**Scope limitations to remember:**

- SCPs affect **IAM users and roles in member accounts**, including the member account's **root user**, subject to AWS-documented exceptions.
- SCPs **do not apply to principals in the management account**.
- SCPs **do not restrict service-linked roles**.
- An SCP does not directly restrict a principal from another account solely because the target resource lives in a member account with an SCP; see cross-account scenarios and RCPs.
- SCPs **do not grant permissions**, even when containing `"Effect": "Allow", "Action": "*"`.

### 4.2. Allow-list and deny-list strategies with SCPs

AWS Organizations typically attaches the managed SCP `FullAWSAccess` by default when SCPs are enabled. In a **deny-list** model, additional `Deny` SCPs block specific actions; everything else still requires IAM permission.

Example SCP **blocking EC2 instance and NAT Gateway creation** in a sandbox OU:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BlockSelectedComputeAndNetworkCreation",
      "Effect": "Deny",
      "Action": [
        "ec2:RunInstances",
        "ec2:CreateNatGateway"
      ],
      "Resource": "*"
    }
  ]
}
~~~

This snippet **illustrates only part of a guardrail**. Before real deployment, evaluate workflow impacts, exception mechanisms, services acting on behalf of users, and administrator privileges. SCPs do not stop already-running resources or enforce budget caps.

In an **allow-list** model, the organization proactively permits only a defined set of actions. For a permission to be allowed, every applicable level along **root → OU → account** must allow it; an `Allow` at the account level cannot overcome a missing `Allow` at the OU or root.

**Example:** Root SCP allows `s3:*` but omits `ec2:RunInstances`. Even if an IAM role in a member account has `AdministratorAccess`, it cannot launch EC2 instances under permissions constrained by that SCP.

### 4.3. How do SCPs differ from permissions boundaries?

| Perspective | SCP | Permissions boundary |
|---|---|---|
| Governance unit | Organizations: root/OU/account | IAM entity: user or role |
| Who sets it? | Organization administrators, appropriately authorized principals | IAM administrators with corresponding permissions |
| Target | Principals in member accounts, with AWS-specified exceptions | The user/role to which the boundary is attached |
| Restricts root user? | Yes, root of **member accounts** | Boundaries cannot be attached directly to root |
| Restricts service-linked roles? | No | Not a standard mechanism applied to service-linked roles |
| Grants permissions? | No | No |
| Typical purpose | Governance, Region/service/shared guardrails | Delegated administration, per-user/role permission ceiling |

You cannot use a role's permissions boundary to replace a mandatory account-wide policy. Conversely, SCPs are usually too coarse to replace tailored permission narrowing across individual roles or sessions.

## 5. How Do the Three Layers Combine with Identity-Based Policies?

### 5.1. Mental formula for the standard case

For **permissions granted via identity-based policies** of an assumed role, when a boundary, session policy, and SCP apply:

~~~text
Effective Allow (via identity-based policy)
    = Identity Allow
      ∩ Boundary Allow       (if boundary attached)
      ∩ Session Allow        (if session policy passed)
      ∩ SCP Allow            (if SCP applies)
      ∩ Other boundaries     (if applicable)
      - Any applicable explicit Deny
~~~

The `∩` symbol here denotes **permission intersection**. It is a mnemonic for the typical case; it does not capture special **resource-based policy** rules or cross-account checks. Policies with `Condition` must be evaluated against live request context rather than treated as static action sets.

### 5.2. Combined scenario with four operations

Role `aws-lab-dev-operator` in sandbox has four permissions allowed by its identity-based policy:

~~~text
s3:GetObject
s3:PutObject
s3:DeleteObject
s3:ListBucket
~~~

With these boundaries:

- **Boundary:** allows `GetObject`, `PutObject`, `DeleteObject`; omits `ListBucket`.
- **Session policy:** allows only `GetObject`, `DeleteObject`; omits `PutObject` and `ListBucket`.
- **SCP:** allows S3 generally, but has an **explicit Deny** on `s3:DeleteObject`.

Assuming actions, ARNs, and `Condition` match, and no alternative resource-policy grant path exists:

| Action | Identity | Boundary | Session | SCP | Result |
|---|---|---|---|---|---|
| `s3:GetObject` | Allow | Allow | Allow | Allow | **Allow** |
| `s3:PutObject` | Allow | Allow | Missing Allow | Allow | **Deny — session policy** |
| `s3:DeleteObject` | Allow | Allow | Allow | **Explicit Deny** | **Deny — SCP** |
| `s3:ListBucket` | Allow | Missing Allow | Missing Allow | Allow | **Deny — boundary and session** |
| `ec2:RunInstances` | Missing Allow | Missing Allow | Missing Allow | Depends on SCP | **Deny — no base permission** |

This explains the common question: **"The IAM role already has Allow, why does AWS still return AccessDenied?"**. To pinpoint which layer denied access, inspect **all policies actually applying to the request** and check error messages or CloudTrail, not just policies attached directly to the role.

### 5.3. Explicit Deny vs. implicit deny

| Type | When does it occur? | What happens if Allow exists elsewhere? |
|---|---|---|
| **Implicit deny** | No matching `Allow` in a required permitting layer; or missing base permission | Not granted via that permission path; rules also depend on resource policies |
| **Explicit deny** | An `"Effect": "Deny"` statement matches principal/action/resource/condition | **Denied**, even when multiple other policies have `Allow` |

For instance, an explicit `Deny` on `s3:DeleteObject` in an SCP is an intentional guardrail. A boundary listing only `GetObject` and `PutObject` produces an **implicit deny** for `DeleteObject` along the identity-based permission path.

## 6. Critical Exception: Resource-Based Policies and Principal ARNs

The intersection formulas above **do not cover every case**. Within the same AWS account, certain resource-based policies can grant permissions **directly** to a principal, altering the effect of *implicit deny* in identity-based policies, boundaries, or session policies.

### 6.1. Distinguishing role ARN and role-session ARN

These two ARNs are **not equivalent**:

~~~text
IAM role ARN:
arn:aws:iam::111122223333:role/aws-lab-dev-operator

STS assumed-role session ARN:
arn:aws:sts::111122223333:assumed-role/aws-lab-dev-operator/training-read-only
~~~

When using credentials from an assumed role, AWS identifies the STS session principal. A resource policy can specify either the **role** or the **role session** as principal; boundary behavior can differ accordingly.

| Principal directly allowed by resource-based policy (same account) | Effect of implicit deny in boundary/session policy |
|---|---|
| **IAM user ARN** (not a federated user session) | Implicit deny in identity policy or boundary typically **does not block** permissions granted directly this way |
| **IAM role ARN** | Implicit deny in boundary or session policy **can still block** permissions granted to the role |
| **STS assumed-role session ARN** | Permissions granted **directly to the session ARN** typically **are not restricted by implicit deny** in identity policy, boundary, or session policy |
| **STS federated user session ARN** | Rules have nuances per specified principal; consult AWS docs for the exact scenario |

In all cases, **any matching explicit Deny still wins**. SCPs apply to member-account principals within scope; other layers such as **RCPs, KMS key policies, VPC endpoint policies, and service-specific authorization** can also restrict requests.

**Scenario requiring caution:** An S3 bucket policy directly allows `arn:aws:sts::111122223333:assumed-role/aws-lab-dev-operator/training-read-only` to read objects. This direct grant may not be narrowed by an implicit deny in the session policy the way granting to the IAM role ARN would. Therefore, never treat permissions boundaries or session policies as the sole mechanism capable of blocking every permission potentially granted by resource-based policies.

AWS recommends using an **IAM role principal** instead of a **role session principal** when appropriate, combined with `Condition` to restrict subjects and context. For resource policies using a wildcard principal with `aws:PrincipalArn`, boundary rules also have nuances; always review IAM evaluation logic before designing sensitive permission paths.

### 6.2. Relationship with SCPs in cross-account access

Suppose **account A** inside an organization owns an S3 bucket, while **account B** outside the organization has a principal needing access:

- An SCP attached to **account A** does not directly apply to a principal in **account B** solely because it calls APIs on A's bucket.
- The principal in B must satisfy **caller/identity-side** policies (and B's SCP if applicable), while A's resource policy must permit appropriate access; service-specific conditions may also apply.
- If account A is subject to an **RCP**, that policy can restrict access to resources owned by A. RCP is a distinct mechanism from SCP.
- If the principal belongs to **member account A**, then SCPs apply to that principal even when accessing resources in another account per AWS-defined scope.

Therefore, when analyzing cross-account requests, clearly separate **the principal-owning account**, **the resource-owning account**, and the policies effective on each side.

## 7. Real-World Design: Multi-Layer Guardrails for an AWS Environment

### 7.1. Role model and objectives

Suppose an organization has a **sandbox** account, a **production** account, and a **platform** governance team. Applications use VPC, Lambda, S3, and RDS; developers can deploy experiments, but cannot grant themselves full administrative rights.

~~~mermaid
flowchart LR
    A[Platform / AWS Organizations] -->|SCP for sandbox OU| B[Sandbox account]
    B --> C[Workload role]
    B --> D[Developer-created role]
    E[Managed permissions boundary] --> D
    F[Identity policy / deployment permissions] --> D
    G[STS session policy] --> H[Read-only support session]
    D --> H
    C --> I[S3 / Lambda / VPC / RDS]
    H --> I
~~~

Layered enforcement:

1. **SCP:** organization-level controls, such as blocking NAT Gateway creation in sandbox or restricting unapproved Regions. SCPs do not enforce monetary spending limits; pair with AWS Budgets, alerts, and resource cleanup policies.
2. **Permissions boundary:** every role developers are permitted to create must stay within the boundary, e.g., operating only on project resources and not managing IAM outside approved scope.
3. **Identity-based policy:** each workload role receives only the actions genuinely needed: Lambda reads S3, worker sends SQS messages, app connects to RDS via the chosen auth method.
4. **Session policy:** during incident triage sessions, operators receive only permissions to read logs or objects needed for investigation; avoid mutating production during support sessions.
5. **Resource-based policies and other conditions:** bucket policies, KMS key policies, trust policies, networking, and supporting governance controls are reviewed so no unintended permission path opens.

### 7.2. Separating policy responsibilities

| Requirement | Appropriate primary tool | Why? |
|---|---|---|
| No sandbox member account may create a NAT Gateway | SCP on sandbox OU | Consistent multi-account constraint |
| Developers can create roles without exceeding approved ceiling | Permissions boundary + IAM API controls | Ensures self-created roles remain within approved limits |
| A 30-minute support session may only read objects | Session policy + STS duration limit | Narrows per individual session |
| Lambda may only read prefix `incoming/` | Identity-based policy and/or bucket policy | Grants exact permissions to the workload |
| Only authenticated sources may assume deployment role | Trust policy and identity conditions | Controls the role's entry door |
| Protect data across accounts and by resource owner | Resource-based policy, RCP, and related mechanisms | Governs resources and external access |

**Principle:** enforce each defensive layer at the exact level it governs, then test effective permissions across realistic scenarios. Overly broad policies topped with untested guardrail layers often make systems harder to operate without actually making them safer.

## 8. Guided Practice: Reasoning About and Inspecting Permissions

This exercise has **two options**. Learners without a sandbox or IAM read access can complete **Part A on paper**. Part B uses **read-only** commands, applicable when your organization provides an appropriate role.

### 8.1. Part A — Calculate effective permissions

Suppose the policies are:

- Role identity policy: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`.
- Boundary: only `s3:GetObject` and `s3:PutObject`.
- Session policy: only `s3:GetObject`.
- SCP on member account: `FullAWSAccess` is active, plus `Deny s3:DeleteObject`.
- No special resource-based `Allow` or other restrictions affect this example.

**Determine** whether the session can invoke the three actions above. Answers:

| Action | Result | Explanation |
|---|---|---|
| `s3:GetObject` | **Allow** | Every required layer permits it |
| `s3:PutObject` | **Deny** | Session policy does not allow it |
| `s3:DeleteObject` | **Deny** | Boundary omits it, session policy omits it, and SCP explicitly denies it |

Try varying one factor at a time: if you **omit the session policy**, `PutObject` becomes allowed via role and boundary; if you **expand the identity policy** to `s3:*`, boundary and SCP still do not expand; if you **remove the boundary**, you still must check session/SCP and resource policies before concluding.

### 8.2. Part B — Inspect policies of an assigned role

**Prerequisite:** you have an AWS CLI profile and permission to view IAM roles in sandbox. **Do not use root, and do not create/delete roles or alter policies just for this exercise.** Replace `aws-lab-dev-operator` with the actual role name provided by your administrator.

~~~bash
aws sts get-caller-identity --profile aws-lab-dev

aws iam get-role \
  --role-name aws-lab-dev-operator \
  --profile aws-lab-dev \
  --query 'Role.{Arn:Arn,Trust:AssumeRolePolicyDocument,Boundary:PermissionsBoundary}'

aws iam list-attached-role-policies \
  --role-name aws-lab-dev-operator \
  --profile aws-lab-dev

aws iam list-role-policies \
  --role-name aws-lab-dev-operator \
  --profile aws-lab-dev
~~~

Reading the output:

- **STS identity:** do the account/ARN match the session you intended to inspect? An ARN like `arn:aws:sts::...:assumed-role/...` is a **session**, not the IAM role definition ARN.
- **Trust:** which principals can the role be assumed by, and under what conditions?
- **Boundary:** is the `PermissionsBoundary` field present? If so, read that managed policy's content with appropriate permissions; if absent, the role currently has no boundary.
- **Identity policy:** which managed/inline policies grant permissions?
- **Session policy:** cannot be fully inferred from `get-role` alone; you must inspect the STS request used to issue the session, since a session policy may have been passed at session creation.
- **SCP:** viewing SCPs requires corresponding AWS Organizations permissions; in an enterprise environment, ask administrators to confirm SCPs at root/OU/account levels.

**Never run mutating commands in shared or production accounts** without an approved change process.

### 8.3. Checking permissions with the right tools

- **IAM Policy Simulator:** simulates many scenarios for user/role policies and boundaries, though it has limits; it does not by default reproduce all session policies, complex SCPs, resource policies, and live service contexts.
- **IAM Access Analyzer:** helps audit access, validate policies, and detect unintended external access within supported features.
- **CloudTrail:** identifies the actual principal and API called, plus timestamps and denied requests, depending on enabled event logging.
- **API error messages:** sometimes include hints like `because no permissions boundary allows...`, `because no session policy allows...`, or `explicit deny in a service control policy`; detail varies by context and service.
- **Testing in sandbox:** only with low-impact actions, and always verify account/Region/role before running.

## 9. Layer-by-Layer AccessDenied Diagnosis

When a command is denied, check in sequence:

1. **Who called the API?** Use `sts:GetCallerIdentity` to verify session ARN, role, and account.
2. **What was the request?** Record action, resource ARN, Region, and related conditions (e.g., tags, VPC endpoint, MFA, encryption).
3. **Does base permission exist?** Check identity-based policies/trust policy, resource-based policies, and any applicable `Deny`.
4. **Is there a boundary?** Inspect the IAM user/role and the managed policy attached as its boundary.
5. **Is there a session policy?** Inspect the federation/STS call that issued credentials, session conditions, and validity window.
6. **Is there an SCP or RCP?** Check the Organizations hierarchy and contact organization admins if you lack read access.
7. **Are there specialized constraints?** E.g., bucket policies, KMS key policies, cross-account requirements, VPC endpoint policies, or service-specific conditions.
8. **Apply the minimal fix:** grant only missing permissions or adjust guardrails via approved change workflows; document root cause and never add `Action: "*"` to work around errors.

| Symptom | Causes worth checking | Next step |
|---|---|---|
| Role has `s3:PutObject` yet is still denied | Boundary or session policy lacks `PutObject`; SCP/resource policy has `Deny` | Cross-check all three layers against the object ARN |
| Using `AdministratorAccess` yet cannot launch EC2 | SCP or another account-level guardrail | Check error message and contact Organizations admins |
| One assumed-role session can read, another cannot | Different session policy / role-session context | Compare STS requests, principal ARNs, and passed policies |
| Cannot assume role | Trust policy, `sts:AssumeRole`, MFA, `ExternalId`, or related conditions | Check caller permissions and role trust policy |
| Cannot create role despite having `iam:CreateRole` | `iam:PermissionsBoundary` condition or role path/name mismatch | Use the exact approved boundary ARN and role path |
| Bucket policy grants unexpected access despite boundary | Resource policy grants directly to IAM user or session ARN | Check the exact principal and resource-based policy rules |
| Permissions suddenly change across many roles | Managed boundary policy edited; OU-level SCP changed | Inspect policy version history and CloudTrail |

## 10. Common Misconceptions

**"I attached a boundary with `Allow s3:*`, so the role now has S3 permissions."** False. A boundary grants no permissions; an identity-based policy or another valid grant path must still allow it.

**"SCP `FullAWSAccess` is the same as IAM `AdministratorAccess`."** False. `FullAWSAccess` simply imposes no extra restriction at that SCP layer; it grants no API permissions itself.

**"A session policy saying `Allow ec2:RunInstances` can bypass a boundary."** False for permissions granted through identity-based policies. Session policies cannot expand role permissions, and boundaries/SCPs still apply.

**"An SCP on the bucket's account always blocks external users from reading the bucket."** False. SCPs govern principals in member accounts; to control external resource access, inspect bucket policies, RCPs, and related mechanisms.

**"Boundaries and session policies always block every `Allow` in a resource policy."** False in certain scenarios involving direct grants to an IAM user ARN or STS session ARN in the same account. Distinguishing principal types and explicit `Deny` is essential.

**"Every `AccessDenied` can be fixed by adding `Allow` to the role."** False. A `Deny` in an SCP, boundary, session/resource policy, or service constraint can block access even when the identity policy is already broad enough.

## 11. Self-Check

1. What policy type does a permissions boundary use, and can it be attached to an IAM group?
2. If an identity-based policy allows `s3:GetObject` and the session policy allows it too, but an OU SCP explicitly denies it, what is the outcome?
3. When a developer has `iam:CreateRole`, which additional APIs must be controlled so the boundary cannot be removed or swapped?
4. What is the difference between `arn:aws:iam::...:role/...` and `arn:aws:sts::...:assumed-role/.../session-name`, and why does it affect resource-based policies?
5. Why is an SCP on the S3 bucket's owning account insufficient to control principals in external accounts?
6. Where should you look if two sessions assuming the same role have different effective permissions?
7. In a scenario where a Lambda reads S3, which policies directly **grant** read permission, and which policies only **restrict** it?

**Completion criteria:** You can identify which layer grants permissions, which layers restrict permissions, and why an `Allow` in one place is not sufficient. Given a specific AWS request, you know how to verify the principal, action, resource, applicable policies, and how to determine `Allow`/`Deny` without over-privileging.

## Official AWS Documentation

- [Permissions boundaries for IAM entities](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [Policies and permissions in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html)
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
- [Policy evaluation: deny and allow](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-denyallow.html)
- [AWS STS AssumeRole API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [Service control policies in AWS Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [Troubleshoot access denied errors](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html)

> **Application note:** Examples use fictional account IDs and bucket names; never apply illustrative policies to production without impact analysis. IAM, Organizations, API limits, and simulator support can vary by service; always verify against current AWS documentation before deploying.
