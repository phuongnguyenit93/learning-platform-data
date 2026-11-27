# IAM user, group, role, and policy

> **Chapter:** IAM and Permissions  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem from Regions/Availability Zones (AZs), IAM, and VPC to compute, storage, databases, integration, and serverless; practice selecting services and designing secure, observable, resilient, and cost-controlled applications.

## Learning Objectives

After this lesson, learners can:

1. Distinguish between **IAM user**, **IAM group**, **IAM role**, and **IAM policy**; explain the role of each component in AWS access governance.
2. Analyze the difference between long-term identities and temporary access sessions from AWS Security Token Service (STS).
3. Read and write basic JSON policies, clearly identifying **Effect**, **Action**, **Resource**, and **Condition**.
4. Distinguish a **permissions policy** from a **trust policy** and explain how a service or another account can assume a role.
5. Predict permission evaluation outcomes using implicit deny, allow, explicit deny, and guardrails such as SCPs, permissions boundaries, and session policies.
6. Design least-privilege permissions for operators and applications using S3, EC2, Lambda, and RDS in a VPC; inspect configurations and troubleshoot AccessDenied errors.

## 1. What Problem Does IAM Solve?

When first getting started with AWS, one person might launch EC2 instances, read S3 objects, modify RDS database tables, or deploy Lambda functions from the same account. If everyone shares credentials with full permissions, it becomes hard to track who performed which operation, credentials are easily exposed, and a compromised account can cause severe damage.

**AWS Identity and Access Management (IAM)** is the service that determines **who or which workload is allowed to perform which actions on which resources, under what conditions**. IAM centers on two core concepts:

- **Identity (principal):** the user or software sending a request to AWS. An identity can be an IAM user or a session issued from an IAM role, along with other principal types supported by AWS.
- **Policy:** rules describing permissions that are allowed or denied for actions on specific resources.

For example, an order-processing API running on Lambda only needs to read invoices under one prefix in S3. Instead of attaching administrative permissions, we create a dedicated role and grant only **s3:GetObject** on the objects it needs to read.

A key design question is: **Who needs what permissions to do their job, for how long, and with how narrow a scope?** This is the principle of **least privilege**.

### IAM is a global service, though access permissions can relate to specific Regions

IAM users, groups, roles, and policies in an AWS account are not created separately per Region the way EC2 instances or subnets are. However, an identity's permissions can apply to resources with Region-scoped ARNs, and restrictions can still apply by policy, organization, service, or access conditions. Switching Regions in the AWS Console does not create a new set of IAM users.

IAM is part of the **Shared Responsibility Model**: AWS operates the IAM platform; customers decide on identities, credentials, policies, MFA, and how permissions are used in their own environment.

## 2. Four Core Components

| Component | Nature | Can it directly sign in / send requests to AWS? | Where permissions are typically granted or attached |
| --- | --- | --- | --- |
| **IAM user** | Long-term identity within an AWS account; can have a console password and/or access keys. | Yes, if issued appropriate credentials. | Direct policy or inherited policy through a group. |
| **IAM group** | Collection of IAM users for managing permissions by group. | **No**. A group is not a principal that signs in or gets assumed. | Policies attached to a group apply to member users. |
| **IAM role** | Identity containing permissions that a trusted principal **assumes** to obtain a temporary access session. | Yes, via a role session/temporary credentials; the role itself has no password or long-term access keys. | Permissions policy attached to the role, combined with a trust policy deciding who can assume it. |
| **IAM policy** | Policy document, usually in JSON format, defining allow/deny rules and conditions. | No. | Can be attached to an identity, a supported resource, or used as a boundary/trust policy depending on type. |

Do not think of a **group as a type of role**, or a **role as only for servers**. Groups organize permissions for IAM users; roles can be assumed by an AWS service, an IAM principal, or a human user signing in through an appropriate identity federation mechanism.

~~~mermaid
flowchart LR
    U["IAM user"] -->|"is a member of"| G["IAM group"]
    G -->|"attaches"| GP["Permissions policy"]
    U -->|"can attach directly"| UP["Permissions policy"]
    X["Application / user / trusted principal"] -->|"STS: assume role"| R["IAM role"]
    T["Trust policy"] -->|"defines who can assume"| R
    R -->|"attaches"| RP["Permissions policy"]
    GP --> RES["Access to AWS resources"]
    UP --> RES
    RP --> RES
~~~

This diagram illustrates the relationships; **effective access still depends on all applicable policies and other control conditions**—simply having an Allow policy does not guarantee access is permitted.

## 3. IAM User: Long-Term Identity Within an Account

An IAM user represents an identity managed directly inside an AWS account. A user can have:

- A **Console password** to sign in to the AWS Management Console.
- An **Access key ID and secret access key** to sign API/CLI/SDK requests using the access key mechanism.
- **MFA** and additional security settings.
- Policies attached directly or inherited through IAM groups.

**Not every IAM user needs both a console password and access keys.** Issuing extra credentials when unnecessary increases the attack surface.

For example, a legacy system that only supports long-term credentials might need a dedicated IAM user if role/federation cannot yet be used. The operations team must protect the secrets, scope the policies tightly, monitor usage, and plan to migrate to temporary credentials when feasible.

### The root user differs from an IAM user

When an AWS account is created, it has a **root user** associated with that account. The root user is not a regular IAM user and can perform sensitive account-level tasks. Protect the root user with MFA, never share its credentials, avoid creating root access keys, and use it only when tasks specifically require the root user.

### The enterprise user option: IAM Identity Center

For humans who regularly sign in to AWS environments, AWS recommends prioritizing **federation and temporary credentials**. AWS IAM Identity Center helps grant users access across multiple AWS accounts and applications via **permission sets**. When signing in, users receive an access session based on the appropriate role; each employee does not need an IAM user with long-term access keys in every account.

**Distinction:** IAM Identity Center users/groups belong to the identity system managed by Identity Center or a connected identity source; they are not the same as IAM users/groups created directly inside an AWS account.

## 4. IAM Group: Managing Permissions by Job Function

Groups let you combine users with the same access requirements. For example:

| Example group | Desired permissions | Should not be granted |
| --- | --- | --- |
| **S3ReportReaders** | Read reports in a designated bucket. | Delete buckets, edit policies, launch EC2. |
| **SupportViewers** | View required operational information. | Modify production infrastructure. |
| **BillingReviewers** | View authorized billing/cost data. | Change IAM or application resources. |

When a policy is attached to a group, members receive the permissions defined by the group policy, subject to all other boundaries and denies applying to that user. If a user leaves the group, permissions originating from that group no longer apply, though they may still have permissions from other policies.

Key points to remember:

1. A group contains only **IAM users** in that AWS account; it cannot contain roles or other groups.
2. A group does **not** have a password, access keys, or a trust policy, and cannot be assumed.
3. Groups manage permissions effectively when there are many IAM users; in organizations using Identity Center, manage groups/permission sets in the corresponding Identity Center mechanism.
4. Using groups does not automatically guarantee least privilege: a policy attached to a group can still be overly broad.

## 5. IAM Role: Permissions via Temporary Access Sessions

A role holds a set of permissions but has no long-term credentials like an IAM user. A trusted principal can **assume a role** to obtain temporary credentials, typically via AWS STS. This session has an expiration time and appears in CloudTrail with the role session's identity details.

Typical scenarios:

- A **Lambda execution role** allows a function to write logs and access S3/DynamoDB/RDS or other services as required.
- An **EC2 instance role** lets an application running on EC2 retrieve temporary credentials via an instance profile/instance metadata instead of embedding access keys in source code.
- An **ECS task role** grants permissions specifically to the application inside a task; distinct from the task execution role used for operations ECS/Fargate itself needs to perform.
- A **Cross-account role** allows a principal in AWS account A to assume a role belonging to account B.
- **Federated access** lets employees sign in through an external authentication mechanism and receive an issued role session.

### 5.1. A role has two important types of policies

A **Trust policy** (role trust policy) answers the question: **Which principals are allowed to assume this role, and via what actions/conditions?**

A **Permissions policy** answers the question: **After successfully assuming the role, what actions can the role session perform on which resources?**

These two policies complement each other. An **overly broad trust** lets too many principals assume the role; **overly broad permissions** let the role do too much. Secure design requires restricting both.

### 5.2. Example: Lambda execution role

Suppose the **InvoiceReader** function reads invoices in S3. The role's trust policy might be:

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

- **Principal** specifies that the Lambda service is allowed to assume the role per the service's mechanism.
- **Action** is **sts:AssumeRole**; this is the permission to assume the role, not the permission to read S3.
- When attaching the role to a function, the deployer must also have permissions to create/update the function and the appropriate **iam:PassRole** permission; having PassRole alone does not mean having permission to assume the role.

The permissions policy attached to the role itself:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadInvoicesOnly",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::example-private-invoices/approved/*"
      ]
    }
  ]
}
~~~

This role receives only **s3:GetObject** permission for objects under the **approved/** prefix in the example bucket. It does not automatically have permission to delete objects, list the bucket, read other buckets, or modify IAM. If the function also needs to write logs or call other services, appropriate permissions must be reviewed and granted separately—for instance, via a properly scoped CloudWatch Logs write policy.

**Bucket ARN and object ARN are different:**

- **arn:aws:s3:::example-private-invoices** points to the bucket.
- **arn:aws:s3:::example-private-invoices/approved/*** points to the set of objects whose keys start with **approved/**.

In an identity-based policy, **s3:ListBucket** typically requires a bucket-level ARN; **s3:GetObject** requires an object-level ARN. Confusing these two ARN types is a very common cause of AccessDenied.

### 5.3. Role assumption flow

~~~mermaid
sequenceDiagram
    participant P as Principal / application
    participant S as AWS STS
    participant R as IAM role
    participant A as AWS service
    P->>S: Request to assume role
    S->>R: Check trust and related conditions
    R-->>S: Allowed to assume?
    S-->>P: Temporary credentials if valid
    P->>A: Send API request signed with role session credentials
    A-->>P: Allow or AccessDenied per policy evaluation
~~~

A role is not a "login account" with a fixed password. One role can be assumed by many sessions simultaneously, and each session has a time limit. When a session expires, the application needs to obtain a new session via the mechanism supported by the service/SDK.

### 5.4. Cross-account access

Suppose a deployment system in account **111122223333** needs to read certain resources in account **444455556666**. The common pattern:

1. In the target account, create a **ReportReader** role with a **permissions policy** allowing the exact actions on the exact resources.
2. The target account role's trust policy allows a specific principal from the source account to assume the role.
3. The source principal has **sts:AssumeRole** permission for the target role and satisfies related conditions.
4. The source principal assumes the role, receives temporary credentials, and then uses the target role's permissions.

Example trust policy in the target account restricting assume permission to the **DeployOperator** role in the source account:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/DeployOperator"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This is an illustrative example with fictional account IDs. With third-party providers, a **sts:ExternalId** condition and additional controls may be needed to mitigate the confused deputy risk. You should trust an appropriate specific principal and avoid unnecessarily opening trust to an entire account.

## 6. IAM Policy: Describing Permissions in JSON

An IAM policy is a policy document consisting of statements. Basic syntax:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ViewOneObjectPrefix",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::example-training-data/tutorials/*"
      ]
    }
  ]
}
~~~

| Element | Meaning | What to watch out for |
| --- | --- | --- |
| **Version** | IAM policy language version. | **2012-10-17** is the standard syntax version, **not** the policy creation date. |
| **Statement** | One or more rules. | Each statement contains Effect, Action/NotAction, and Resource/NotResource depending on policy type. |
| **Sid** | Optional statement identifier. | Naming statements helps with reviews and investigations. |
| **Effect** | **Allow** or **Deny**. | An explicit Deny has very high precedence in permission evaluation. |
| **Action** | API/operation being controlled, such as **s3:GetObject**. | Permission action names do not always match API names verbatim. |
| **Resource** | ARN of the affected resource. | Not all actions support resource-level restrictions; check the service's action documentation. |
| **Condition** | Additional conditions, e.g., prefix, tags, VPC endpoint, MFA, or principal attributes when supported. | Choose the right condition key and understand what context data AWS actually provides. |
| **Principal** | Principal specified in resource-based policies/trust policies. | Normally **do not** include Principal in an identity-based permissions policy. |

A policy can contain multiple statements. Writing multiple small, named, narrowly scoped statements is usually easier to audit than one statement packed with unrelated actions and resources.

### 6.1. Two S3 permissions that look similar but have different scopes

Suppose a reporting tool needs to list **only the reports/2026/ prefix** and read the objects inside it:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyReportPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::example-private-reports",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "reports/2026/",
            "reports/2026/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadOnlyReportObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-private-reports/reports/2026/*"
    }
  ]
}
~~~

How to read this policy:

- **ListBucket** acts at the **bucket level**, restricted by the request prefix.
- **GetObject** acts at the **object level**, allowing reads only on objects matching the allowed ARN pattern.
- The policy does not grant **s3:PutObject**, **s3:DeleteObject**, or **s3:PutBucketPolicy**.
- Effective permissions can still be blocked by a bucket policy, SCP, KMS key policy, or other restrictions.

**The s3:prefix condition only controls list requests when the action and context support that condition**; it cannot be used as a substitute for restricting the object ARN of GetObject.

### 6.2. Managed policy and inline policy

| Type | Characteristics | When appropriate |
| --- | --- | --- |
| **AWS managed policy** | Created and maintained by AWS; quick to use for common roles. | Learning how permissions work or building an initial baseline; requires review because it may be broader than actual needs. |
| **Customer managed policy** | Created by the customer, version-managed, and attachable to multiple IAM identities. | Suitable when reusing a tightly controlled set of permissions. |
| **Inline policy** | Embedded directly with a lifecycle tied to a single user, group, or role. | Specific permissions meant exclusively for one identity and tightly bound to that identity. |

A policy attached to an IAM user/group/role is an **identity-based policy**. A policy attached to a resource such as an S3 bucket or AWS KMS key can be a **resource-based policy**. These two categories differ in where the policy lives, whether Principal is specified, and how they participate in permission evaluation.

### 6.3. A trust policy is a special case of a resource-based policy

A role trust policy declares which principals can assume the role. It does not grant permissions to operate on S3 or EC2 after assuming. The permissions policy attached to the role describes the actions allowed within that session. Only when both the assume-role conditions and the post-assume API conditions are satisfied will the workflow succeed.

## 7. How Does AWS Evaluate an Access Request?

Foundational rules:

1. **Implicit deny (default deny):** if no matching Allow permission is found, the request is denied.
2. **Explicit Allow:** a statement allowing the action on the resource in the matching context can open the path for the request.
3. **Explicit Deny:** if an applicable policy explicitly denies the request, it is denied—even if another policy has an Allow.
4. **Higher-level guardrails:** policy types such as permissions boundaries, SCPs/RCPs in AWS Organizations, and session policies can cap effective permissions; on their own, they **do not grant permissions**.
5. **Service controls:** resource policy conditions, KMS key policies, ownership, networking, or service-specific requirements can still affect whether the operation completes.

### 7.1. High-level model

~~~mermaid
flowchart TD
    Q["API request: principal + action + resource + context"] --> D{"Is there an applicable explicit Deny?"}
    D -->|"Yes"| NO["Deny"]
    D -->|"No"| A{"Is there a valid Allow?"}
    A -->|"No"| NO
    A -->|"Yes"| L{"Satisfies boundaries like SCP, permissions boundary, session policy, and service rules?"}
    L -->|"No"| NO
    L -->|"Yes"| YES["May Allow"]
~~~

This diagram is a **learning model** and does not replace AWS's complete evaluation algorithm: permissions from identity-based and resource-based policies are typically evaluated together; exceptions depend on principal type, permissions granted directly to a role session or user, resource policy type, and cross-account models. For cross-account access, appropriate permissions are also required on both the caller side and the target resource/account depending on the access pattern. When a definitive conclusion is needed, consult AWS's **Policy evaluation logic** for the exact scenario.

### 7.2. Common policy types involved in a request

| Policy | Purpose | Does it grant resource access on its own? |
| --- | --- | --- |
| **Identity-based permissions policy** | Grants or denies actions for a user, group, or role. | Can grant Allow, if not blocked by other policies/conditions. |
| **Resource-based policy** | Grants or denies access to a supported resource, specifying appropriate principals. | Can grant Allow depending on service mechanism/principal type. |
| **Role trust policy** | Defines who is allowed to assume a role. | Only governs assuming the role; does not grant access to other services. |
| **Service control policy (SCP)** | Sets maximum permission boundaries for accounts/principals managed by AWS Organizations within its scope. | No. |
| **Resource control policy (RCP)** | Restricts maximum permissions for accessing resources within scope in Organizations, for supported resource types. | No. |
| **Permissions boundary** | Caps the maximum permissions that identity-based policies can grant to an IAM user or role. | No. |
| **Session policy** | Can further restrict permissions of a role/federated session when creating the session. | No. |
| **KMS key policy** | Defines who can manage or use a KMS key, alongside other KMS permission mechanisms. | Can grant permissions in the KMS context, per KMS's own evaluation model. |

### 7.3. Example comparing Allow and Deny

A user has a policy attached that Allows **s3:GetObject** on all objects in bucket A. However, the bucket policy has an explicit Deny for an access condition that this user's request violates. Result: **AccessDenied**. Reasoning that "the user already has Allow, so they can definitely read it" is wrong because all applicable policies must be evaluated.

Another example: a role has a policy Allowing **ec2:TerminateInstances**, but the organization's SCP does not allow that action in the relevant account. The role's permissions policy cannot bypass the limit imposed by the SCP.

### 7.4. Policies are access control, not all of security

Having permission to call an API does not mean network connectivity will succeed or data will be usable:

- **VPC/Security Groups** can block connections to RDS even if IAM allows related control-plane operations.
- **KMS** may require permission to use the key and an appropriate key policy configuration to decrypt objects encrypted with a KMS key.
- **Databases** may require credentials and DB-layer GRANT/REVOKE permissions, depending on the authentication method.
- **Applications** still need to enforce end-user business authorization—do not confuse workload IAM with authorization inside the application.

## 8. IAM in Real-World AWS Architecture

Consider an order management application running across two AZs:

- An ALB handles HTTPS in front of the service.
- EC2 runs the API in private subnets, or it could be moved to Lambda when the design fits.
- RDS stores order data; S3 stores invoices/documents.
- CloudWatch/CloudTrail monitor activity; KMS helps protect data as required.
- The deployment team uses IAM Identity Center to access AWS accounts through assigned roles.

~~~mermaid
flowchart TB
    H["Operations engineer"] -->|"SSO / temporary credentials"| IIC["IAM Identity Center"]
    IIC -->|"permission set / role session"| DEP["Deployment role"]
    DEP -->|"deploys appropriate resources"| APP["EC2 or Lambda application"]
    APP -->|"temporary credentials from runtime role"| IAM["Application IAM role"]
    IAM -->|"prefix-scoped s3:GetObject"| S3["Invoices S3"]
    IAM -->|"AWS API permissions if needed"| DB["RDS / other AWS services"]
    OBS["CloudTrail / CloudWatch"] -.->|"records activity per configuration"| IAM
~~~

Note that the arrow from the role to RDS only depicts **permissions to call relevant AWS APIs**; SQL connections to the database are a separate networking and authentication flow and do not automatically come from an IAM role (unless a supported IAM database authentication mechanism is explicitly configured).

### Separating roles by function

| Workload/user | Recommended role/permissions | Reason |
| --- | --- | --- |
| Developers | Role via Identity Center for dev environments; production access via controlled workflows. | Avoid long-term access keys on personal laptops or unnecessary admin rights. |
| CI/CD pipeline | Dedicated deployment role with trust restricted to the deployer and session conditions; PassRole scoped to required deployment roles. | Limits ability to alter infrastructure and reduces privilege escalation risk. |
| EC2 API | Instance role with only the S3 prefixes, secrets, and APIs actually needed. | Application receives temporary credentials without embedding AWS secrets. |
| Document-processing Lambda | Execution role with read/write permissions for relevant resources and appropriate logging. | Isolates permissions per function and simplifies auditing. |
| Support team | Role to read only required metrics/logs within assigned scope. | Troubleshoot incidents without modifying infrastructure or data. |

**Separate roles by environment:** Dev, staging, and production have different goals, data, and risk levels. Separating IAM roles/policies—and AWS accounts when appropriate—limits the blast radius of mistakes.

**Separate deploy permissions from runtime permissions:** A pipeline may need permissions to update functions and PassRole, whereas Lambda at runtime does not need permissions to create IAM roles. Never combine them into a single full-access role.

### Using IAM to protect cost controls and recovery

IAM does not directly determine resource consumption or service pricing, but restricting who can launch expensive resource types, delete backups, alter logging, or modify policies helps safeguard cost and recovery controls. Tools like AWS Budgets, Cost Explorer, CloudTrail, and approval workflows still need to be configured properly alongside IAM.

## 9. Practice Reading and Inspecting Permissions

This section uses the **AWS CLI in read-only and simulation modes**; do not create or delete IAM users, roles, or policies on your own. You need AWS CLI configured, an identity permitted to run the corresponding commands, and to replace placeholder names with resources you have permission to inspect in your practice environment.

### 9.1. Identify the current identity session

~~~bash
aws sts get-caller-identity
~~~

For example, when the CLI is using a role session, the returned ARN might look like:

~~~text
arn:aws:sts::111122223333:assumed-role/ReportingReader/session-name
~~~

This indicates the CLI is using a session of the **ReportingReader** role, which differs from the role definition ARN:

~~~text
arn:aws:iam::111122223333:role/ReportingReader
~~~

The AWS CLI and SDKs can obtain temporary credentials automatically from the role attached to the runtime environment, an SSO profile, or an appropriate federation mechanism; do not copy secrets into source code or commit credentials to Git.

### 9.2. Inspect existing users, groups, and roles

~~~bash
# List IAM users, groups, and roles (requires appropriate iam:List* permissions).
aws iam list-users
aws iam list-groups
aws iam list-roles

# Check which groups a user belongs to.
aws iam list-groups-for-user --user-name ExampleAnalyst

# View role details, including AssumeRolePolicyDocument (trust).
aws iam get-role --role-name ReportingReader

# List managed policies attached to the role.
aws iam list-attached-role-policies --role-name ReportingReader

# List inline policies attached to the role.
aws iam list-role-policies --role-name ReportingReader
~~~

These commands may return **AccessDenied** if the learner's own session lacks IAM read permissions. That is a valid permission boundary, not proof that the identity or resource does not exist.

### 9.3. Read a managed policy version

~~~bash
# Check metadata, especially DefaultVersionId.
aws iam get-policy \
  --policy-arn arn:aws:iam::111122223333:policy/ReadReports

# Replace v1 with the DefaultVersionId obtained from the command above.
aws iam get-policy-version \
  --policy-arn arn:aws:iam::111122223333:policy/ReadReports \
  --version-id v1
~~~

A customer managed policy can have multiple versions; only the default version is active. Do not guess from the policy name alone; read the actual JSON content and other guardrails.

### 9.4. Simulate a request

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportingReader \
  --action-names s3:GetObject s3:DeleteObject \
  --resource-arns arn:aws:s3:::example-private-reports/reports/2026/demo.pdf
~~~

In the output, check **EvalDecision** per action and resource. The result can be **allowed**, **implicitDeny**, or **explicitDeny** in supported simulation scenarios.

**Simulation limitations:** The IAM policy simulator does not fully simulate every policy type, context, delegation mechanism, or real-world condition (especially certain resource policy, cross-account, SCP/RCP, and service-specific control cases). Simulation results do not replace safe testing with an appropriate identity and verifying actual access. Before concluding, read all warnings and details returned by the tool.

### 9.5. Troubleshooting AccessDenied errors systematically

When a program gets permission denied, answer these questions in order:

1. **Who is sending the request?** Check the identity from **sts get-caller-identity** in the exact environment where the error occurs. In Lambda/EC2, verify which role the workload is using.
2. **Which action is denied?** Distinguish the permission action in the error message from the API call made by the application.
3. **Is the Resource ARN accurate?** Check the account, Region (if the resource is Regional), resource type, bucket name, prefix, or path.
4. **Is there a required Allow?** Check managed/inline policies, group memberships, policy versions, conditions, and tags.
5. **Is there a Deny or other boundary?** Check SCPs, permissions boundaries, session policies, resource policies, KMS key policies, and applicable service-specific conditions.
6. **If assuming a role:** Check the trust policy, the caller's sts:AssumeRole permission, ExternalId/MFA/session tag conditions, and session duration.
7. **Verify with evidence:** Cross-check CloudTrail, application logs, and safe reproduction steps. Do not fix errors by temporarily granting AdministratorAccess to every principal.

**Common scenario:** A Lambda has GetObject permission in its policy but still cannot read an S3 object encrypted with a customer managed KMS key. Beyond S3 permissions and related resource policies, check **kms:Decrypt** and the key policy/key usage conditions; adding s3:* will not fix the root cause.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Why it is dangerous or causes errors | Recommended approach |
| --- | --- | --- |
| Using the root account to run scripts. | Too many privileges; hard to scope down. | Use roles/temporary credentials with least privilege. |
| Embedding access keys in source code, images, or uncontrolled environments. | Secrets can leak via Git, logs, artifacts, or configs. | Prefer roles/STS; manage secrets by design when truly necessary. |
| Using **Action: "*"**, **Resource: "*"** to eliminate AccessDenied. | Grants overly broad permissions and hides the root cause. | Identify exact actions/resources/conditions; add verified required permissions. |
| Treating an IAM group as an assumable identity. | Wrong model; groups cannot create role sessions. | Use groups to assign permissions to IAM users; use roles for access sessions. |
| Checking only the permissions policy while ignoring the trust policy. | Caller cannot assume the role even if the role has S3 permissions. | Check both trust and permissions, as well as the caller's permissions. |
| Treating a trust policy as granting full permissions. | Trust only defines the assume relationship, not S3/EC2 permissions. | Evaluate trust policy and effective post-assume permissions separately. |
| Granting **iam:PassRole** with a broad scope. | Can allow a principal to deploy services running with highly privileged roles. | Restrict which roles can be passed and which services can receive them where appropriate. |
| Checking only IAM and ignoring S3 bucket policies/KMS key policies. | Resource policies or key permissions can block or open access. | Evaluate all applicable policies and service mechanisms. |
| Assigning the same role to the deploy pipeline and runtime application. | The workload can carry unnecessary deployment privileges. | Separate administrative/deployment permissions from runtime permissions. |
| Confusing IAM users/groups with Identity Center users/groups. | Easy to grant wrong permissions and duplicate administration. | Pick one primary identity mechanism for employees; use properly scoped permission sets. |
| Treating simulator Allow as an end-to-end guarantee. | Simulation does not reflect every condition or application layer. | Combine policy reviews, boundary testing, and real logs. |

## 11. Practice Scenarios

### Scenario A — Employees only need to view reports on S3

**Requirement:** Analysts view files in **reports/2026/**, and must not delete files or view HR documents.

**Design:** In an organization using Identity Center, assign the corresponding permission set to the appropriate employee group. If the environment genuinely uses IAM users, the **S3ReportReaders** group can attach a customer managed policy allowing only ListBucket with a prefix condition and GetObject on object ARNs under that prefix. Do not use groups to hold roles.

**Verification:** Users successfully read the right prefix; attempts to DeleteObject or read other prefixes must be denied. Check bucket policies and encryption permissions if objects use KMS.

### Scenario B — Lambda only writes one type of invoice

**Requirement:** Lambda generates PDF invoices and writes them to **invoices/generated/**.

**Design:** Execution role trusts **lambda.amazonaws.com**, permissions policy has **s3:PutObject** on the prefix's object ARN and necessary logging permissions. If the function needs a KMS key, grant appropriate key permissions. Deployers have **iam:PassRole** scoped to the exact role allowed for the Lambda.

**Verification:** The function can create objects only in the required prefix, cannot read other confidential buckets, and cannot modify IAM policies. Add permissions only when backed by a verified business requirement.

### Scenario C — Reading logs from another account

**Requirement:** A monitoring team in account A reads authorized logs in account B.

**Design:** Account B has a role trusting a specific principal from account A; account A has permission to assume the target role; the target role is granted read permissions for the exact log source. All requests use temporary credentials. If logs are encrypted with a KMS key, permissions to use that key are required.

**Verification:** Assume succeeds for the permitted principal and fails for other principals; read actions are restricted to the right log source. Cross-check CloudTrail across relevant accounts when appropriate.

### Scenario D — EC2 application gets AccessDenied reading S3

**Symptom:** EC2 is running normally, but the SDK reports an S3 AccessDenied error.

**Workflow:** Check whether the instance has an instance profile with the right role attached; which profile/credentials the SDK is using; whether the policy allows GetObject on the exact object ARN; whether the bucket policy has a Deny; whether the object uses a KMS key requiring Decrypt. Having EC2 and S3 in the "same Region" or placing EC2 in a private subnet does not automatically grant S3 read permissions.

## 12. Self-Check Questions

**Question 1.** Can an IAM group be assumed by Lambda?  
**Answer:** No. Groups only organize IAM users and their policies. Lambda assumes an execution role with an appropriate trust policy.

**Question 2.** A role trust policy allows lambda.amazonaws.com to assume the role. Does the function automatically gain read access to every S3 bucket?  
**Answer:** No. Trust only allows Lambda to use the role; the role's specific permissions and other policies/conditions determine whether S3 requests are accepted.

**Question 3.** Why is it necessary to distinguish between a bucket ARN and an object ARN when granting S3 permissions?  
**Answer:** Actions like ListBucket apply at the bucket level; GetObject applies at the object level. Picking the wrong ARN can cause an implicit deny even when the policy looks right.

**Question 4.** A user has an Allow GetObject policy, but a resource policy has an explicit Deny for the request under evaluation. What is the outcome?  
**Answer:** Deny; an applicable explicit Deny overrides Allow.

**Question 5.** Can a permissions boundary or SCP grant GetObject permission on its own?  
**Answer:** No. They limit effective permissions within their scope; the principal still needs a valid Allow source and must not be blocked by other policies.

**Question 6.** When an EC2 application needs to call AWS APIs, why is using an instance role usually better than storing access keys in source code?  
**Answer:** An instance role provides temporary credentials through AWS mechanisms, reducing long-term secret management and leakage risks while making it easy to scope permissions per workload.

**Question 7.** Does the **iam:PassRole** permission mean the caller is allowed to assume the role?  
**Answer:** No. PassRole lets the caller pass a role to a supported service during certain deployment operations, whereas assuming a role is governed by the trust policy and STS/related permissions.

**Question 8.** Should you create a separate IAM user with long-term access keys for every employee in every AWS account?  
**Answer:** Usually no. For humans, prioritize identity federation/IAM Identity Center and temporary credentials; IAM users should only be used when there is a verified need and credentials must be strictly controlled.

## 13. Key Takeaways

- A **User** is an IAM identity that can be issued long-term credentials.
- A **Group** is a way to organize IAM users for policy management; a group is not a principal.
- A **Role** is an identity assumed by a trusted principal, typically providing temporary credentials for a work session.
- A **Policy** expresses permissions using **Effect + Action + Resource + Condition**; distinguish trust policies from permissions policies.
- **Implicit deny** is the default state; **explicit deny** takes precedence; effective permissions are also affected by other boundaries and service rules.
- **Least privilege** must be verified per workload, per environment, and per operation, combining IAM with VPC, encryption, monitoring, and operational processes.

When designing AWS applications, choose the right identity type for the actor (human, pipeline, or workload), define trust boundaries, grant the smallest verifiable permissions, avoid storing long-term credentials, and regularly audit with logs, policy analysis tools, and controlled testing.

### Further AWS Reading

- [AWS IAM User Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html) — overview of IAM and identity types.
- [IAM identities: users, user groups, and roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id.html) — characteristics of users, groups, and roles.
- [IAM JSON policy elements reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements.html) — syntax, Action, Resource, Condition, Principal.
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — how AWS combines permissions and boundaries.
- [AWS IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html) — recommendations on federation, roles, least privilege, and credential protection.
