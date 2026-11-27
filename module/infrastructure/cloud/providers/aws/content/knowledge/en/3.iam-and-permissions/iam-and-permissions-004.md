# Identity-Based Policies and Resource-Based Policies in AWS IAM

In AWS, **IAM (Identity and Access Management)** determines **who is allowed to do what on which resources and under what conditions**. The two primary ways of granting permissions are **identity-based policies** (policies attached to an identity) and **resource-based policies** (policies attached to a resource). They often appear together in a single architecture: a role is permitted to read data, while the bucket holding that data specifies which principals may access it.

This lesson belongs to the **IAM and Permissions** chapter of the **CLOUD_PROVIDERS_AWS** module, part of the AWS learning path from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless. Understanding IAM mechanics accurately helps learners choose services, deploy applications following least privilege, monitor access, recover reliably, and control operational risks.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain what subjects each policy attaches to and the structural differences between the two types.
2. Read and write basic JSON policies with **Effect, Action, Resource, Principal, Condition**.
3. Distinguish **same-account AWS** access from **cross-account AWS** access.
4. Explain **implicit deny**, **explicit allow**, **explicit deny**, and guardrails such as permissions boundaries, session policies, and SCPs/RCPs.
5. Distinguish **IAM role trust policies**, **role permissions policies**, **S3 bucket policies**, and **KMS key policies**.
6. Decide where to place permissions, verify configurations, and spot common authorization mistakes.

## 2. Foundational Concepts

An access request typically has four main components:

| Component | Meaning | Example |
|---|---|---|
| **Principal** | Identity or session making the request | IAM user, IAM role session, AWS service principal |
| **Action** | Operation to be performed | Reading an S3 object with **s3:GetObject** |
| **Resource** | Target resource, typically identified by an ARN | An object inside an S3 bucket |
| **Context** | Information accompanying the request | Timestamp, network source, tags, principal attributes |

An **ARN (Amazon Resource Name)** identifies an AWS resource, such as **arn:aws:s3:::example-reports/2026/report.csv**. An S3 bucket ARN is **arn:aws:s3:::example-reports**, whereas an object ARN includes the **/key** portion afterward. Not every action supports every ARN type; check the corresponding service's **Actions, resources, and condition keys** table.

AWS IAM evaluates a request based on the policies that actually apply to the principal and resource. **A policy containing an Allow statement does not guarantee the request will be permitted**: context, other guardrail layers, and any explicit Deny must also be evaluated.

## 3. Comparing the Two Policy Types

| Criterion | Identity-based policy | Resource-based policy |
|---|---|---|
| Attached to | IAM **user**, **group**, or **role** | Supported resources, such as **S3 bucket**, **SQS queue**, **SNS topic**, **KMS key**, **Lambda function**, or **IAM role trust policy** |
| Core question | **What can this identity do?** | **Who can do what with this resource?** |
| Specifying who gets permissions | The identity itself to which the policy is attached; normally **no Principal** in JSON | Uses **Principal** to name the allowed account, role, user, session, or service |
| Scope | Can allow operations across many resources/services | Controls access to the specific resource where the policy is attached |
| Managed/inline | Supports **AWS managed**, **customer managed**, and **inline** | Is an **inline policy** attached directly to the resource; no equivalent managed resource policy |
| Cross-account access | Grants permissions to a principal in the source account | Names principals in other accounts permitted to use the target resource, if supported by the service |
| Real-world example | An application role is allowed to read report files | A reports bucket accepts access only from named roles |

> **Common confusion:** An identity-based policy still has a **Resource** field specifying target ARNs. Naming an ARN inside a policy attached to a role **does not turn it into a resource-based policy**. Classification depends on **where the policy is attached**.

### 3.1. Identity-based policy

Identity-based policies travel with an identity or role. For example, a Lambda execution role is allowed to write CloudWatch Logs; an ECS application role is allowed to read an S3 prefix; or a staff group has billing view permissions within organization boundaries.

There are two common management mechanisms:

- **Managed policy:** a standalone policy attachable to multiple identities. AWS managed policies are maintained by AWS; customer managed policies are created and updated by your organization. Editing a managed policy can affect all identities attached to it.
- **Inline policy:** policy content embedded and managed directly within one specific user, group, or role. Suitable when a one-to-one binding is needed, though harder to reuse.

When attaching permissions to an **IAM group**, IAM users in that group inherit permissions from the group's policies. However, a group is **not a principal used to sign in or to name directly in the Principal field of a bucket policy**.

### 3.2. Resource-based policy

Resource-based policies are managed by the resource owner. The policy typically includes **Principal** to specify who may call actions on the resource, optionally paired with **Condition** to narrow the scope.

Important examples:

- **S3 bucket policy:** allows or denies operations on the bucket and objects within the specified scope.
- **SQS queue policy / SNS topic policy:** allows named principals or services to send/receive messages for actions supported by the service.
- **Lambda function resource policy:** can allow another principal or service to **invoke** the function; distinct from the **Lambda execution role** permissions policy used when the function runs.
- **KMS key policy:** determines who can administer or use a KMS key; a required component for every key.
- **IAM role trust policy:** the resource-based policy of the IAM role itself, specifying who can **AssumeRole**. After successfully assuming the role, the **role's permissions policy** determines what actions can be performed using that session.

Not every service supports resource-based policies. When sharing a service that lacks this mechanism across accounts, a **cross-account role** can be the right approach.

## 4. JSON Policy Structure

A policy statement usually contains the following fields:

| Field | Function | Remember |
|---|---|---|
| **Version** | Policy language version | Common value today: **2012-10-17**; not the revision number of the saved policy |
| **Statement** | One or more allow/deny rules | Either a single object or an array of objects |
| **Sid** | Optional statement label | Helps readers identify its purpose |
| **Effect** | **Allow** or **Deny** | Explicit Deny takes precedence |
| **Action** | API/operation under evaluation | Can be a single action name or a list |
| **Resource** | Target resource ARN | Some actions require or only support **\*** |
| **Principal** | Principal to which a resource-based policy applies | Typically present in resource-based/trust policies; **do not put in identity-based policies** |
| **Condition** | Conditions for the statement to take effect | E.g., tags, request source, transport security |

### 4.1. Identity-based policy example: read only files in a prefix

Suppose an application uses role **MonthlyReportReader**. The role only needs to read objects from the **exports/monthly/** path of bucket **team-report-demo**. The identity-based policy attached to the role can be written as:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadMonthlyReportObjectsOnly",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::team-report-demo/exports/monthly/*"
    }
  ]
}
~~~

**Explanation:** this policy allows calling **GetObject** on object ARNs matching the specified prefix. It does **not** automatically grant **s3:PutObject**, **s3:DeleteObject**, or **s3:ListBucket**. For the application to browse object lists via the list API, **s3:ListBucket** must be added on the **bucket ARN**, optionally using the **s3:prefix** condition to restrict which prefixes can be listed.

Because this is an identity-based policy, there is no **Principal**: the principal is already defined by the identity/role to which the policy is attached.

### 4.2. Resource-based policy example: bucket allowing a cross-account role

Consider two illustrative accounts (IDs and bucket names are fictional):

- **Account A: 111122223333** — owns IAM role **ReportReadRole**, where the application runs.
- **Account B: 222233334444** — owns S3 bucket **project-report-demo-222233334444**, containing data under prefix **exports/**.

Bucket policy attached in **Account B**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReportReaderFromAccountA",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/ReportReadRole"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::project-report-demo-222233334444/exports/*"
    }
  ]
}
~~~

**Explanation:** a specific role in Account A is named in **Principal**. The policy is stored on Account B's bucket, making this a **resource-based policy**. It allows only reading objects under the **exports/** prefix, not writing, deleting, or listing the bucket.

To make this standard cross-account access path work, **ReportReadRole** in Account A also needs an identity-based policy allowing **s3:GetObject** on the same object ARN:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReportsFromAccountB",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::project-report-demo-222233334444/exports/*"
    }
  ]
}
~~~

In this example, **both accounts must simultaneously allow** the request under cross-account evaluation rules. If objects are encrypted using **SSE-KMS** with a customer managed KMS key, **kms:Decrypt** permission from an appropriate policy and the **KMS key policy** may also be required; the S3 bucket policy alone is not sufficient.

~~~mermaid
flowchart LR
    subgraph A["Account A — 111122223333"]
        APP["App using ReportReadRole"]
        ID["Identity-based policy\nAllow s3:GetObject"]
        APP --> ID
    end
    subgraph B["Account B — 222233334444"]
        BP["S3 bucket policy\nPrincipal = ReportReadRole"]
        OBJ["S3: exports/report.csv"]
        BP --> OBJ
    end
    ID -->|"Request to Account B"| BP
~~~

The diagram shows **direct access to S3 via a resource-based policy**. This differs from the **AssumeRole into Account B** approach, covered later.

## 5. How Does AWS Evaluate Access Permissions?

### 5.1. Three fundamental principles

1. **Implicit deny (default deny):** if no matching Allow exists, the request is denied. The absence of an Allow statement is **not** an explicit Deny.
2. **Explicit allow:** an **Effect: Allow** statement matching principal, action, resource, and conditions can permit the request, depending on other applicable policies.
3. **Explicit deny:** an **Effect: Deny** statement applying to the request overrides matching Allows.

AWS evaluates all applicable policies together, not in the textual order statements appear in JSON.

### 5.2. Within the same account: permissions are typically the union of both policy types

For requests within the **same account**, AWS typically combines permissions from **identity-based** and **resource-based policies** as a **union**. A valid Allow from either one can suffice, provided no explicit Deny or other restricting mechanism blocks it.

| Identity-based | Resource-based | Basic same-account outcome |
|---|---|---|
| No Allow | No Allow | **Deny** by default |
| Allow | No Allow | **Allow** if not restricted by another guardrail |
| No Allow | Allow directly for matching principal | **Allow** if not restricted by another guardrail |
| Allow | Allow | **Allow** if not restricted by another guardrail |
| Explicit Deny | Allow | **Deny** |
| Allow | Explicit Deny | **Deny** |

This table is a **baseline model** and does not reflect every boundary or exception by principal type or service. For instance, **permissions boundaries**, **session policies**, **AWS Organizations SCPs/RCPs**, or service-specific policies can alter the result.

**Example:** a role in Account A has **s3:GetObject** permission on a bucket in Account A itself. In most cases, the bucket does not need a duplicate Allow statement for that role; however, if the bucket has an applicable Deny, or another active permission boundary applies, access can still be blocked.

### 5.3. Cross-account: check both the caller side and the resource side

For the S3 example in section 4.2, the request must pass two evaluations:

1. **Account A (principal's account):** the role's identity-based policy and applicable boundaries must allow the action.
2. **Account B (resource's account):** the bucket policy must accept the principal/action/resource, and any guardrail or resource-protection policies must also allow it.

If either side returns Deny, the request is not executed. You cannot grant read access to Account B's bucket solely by attaching an IAM policy to a role in Account A.

Note: the actual outcome can also be influenced by **S3 Block Public Access**, object ownership settings, endpoint policies, KMS key policies, AWS Organizations, and service-specific controls. Use these examples as a foundational model rather than a substitute for checking individual service requirements.

### 5.4. Permissions boundaries, session policies, SCPs, and RCPs

Other policy types act as **permission boundaries**, and should not be thought of as additional Allow sources that grant permissions on their own like identity-based policies:

- **Permissions boundary:** sets a permission ceiling for an IAM user/role in applicable contexts; the boundary itself creates no new permissions.
- **Session policy:** can narrow down permissions obtained when using temporary session credentials.
- **Service control policy (SCP):** caps maximum permissions for principals in accounts belonging to AWS Organizations.
- **Resource control policy (RCP):** caps maximum permissions applying to supported resources within scope in AWS Organizations.

**Exception to recognize:** within the same account, a resource-based policy granting permissions **directly to an IAM user ARN or role-session ARN** follows different rules regarding implicit denies in identity-based policies, boundaries, or session policies compared to policies granting to an **IAM role ARN**. For example, a direct grant to a role session might not be blocked solely by an **implicit deny** in a boundary/session policy; an **explicit deny** still applies. Therefore, do not treat a simple intersection of all policies as a universal formula for every case. When designing advanced permissions, verify **the exact ARN type specified in Principal** and consult IAM's policy evaluation documentation.

### 5.5. Explicit deny and condition example

An S3 bucket policy can prevent operations over connections not using HTTPS:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::team-report-demo",
        "arn:aws:s3:::team-report-demo/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
~~~

This is a **conditional Deny**, not a statement making the bucket public. **Principal: \*** here simply means the Deny applies to any matching principal when the connection is insecure. A role with an identity-based Allow is still denied if the request matches this Deny.

## 6. Special Case: IAM Role Trust Policies

An IAM role is both an **identity** carrying a permissions policy and a **resource** having a **trust policy**. The two policies answer separate questions:

| Role policy type | Answers | Common actions |
|---|---|---|
| **Trust policy** | Who or which service can obtain a session for this role? | **sts:AssumeRole** |
| **Permissions policy** | After obtaining a session, which APIs can the role call? | **s3:GetObject**, **dynamodb:Query**, **logs:PutLogEvents**… |

Example: Account B has role **SharedDataReader**. The role's trust policy allows role **ReportReadRole** in Account A to request assumption:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/ReportReadRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

For this cross-account AssumeRole pattern to work, the calling role in Account A typically needs **identity-based permission sts:AssumeRole** on the target role in B. Next, role **SharedDataReader** in B needs a permissions policy allowing **s3:GetObject** on the data it must read. Because the session now assumes a role in **Account B**, access to a bucket in Account B can be granted via that role's identity-based policy under same-account rules, without necessarily adding a separate bucket Allow.

**Do not confuse:** allowing **sts:AssumeRole** in a trust policy **does not automatically grant s3:GetObject**. For Lambda, the trust policy lets the **lambda.amazonaws.com** service assume the execution role; meanwhile, the function's resource policy controls who can call **lambda:InvokeFunction**. These two authorization paths serve different purposes.

## 7. Notable Exception: AWS KMS

A **KMS key policy** is a distinctive resource-based policy. Every KMS key has a key policy, and an IAM identity-based policy stating **kms:Decrypt: Allow** does not guarantee decryption will succeed. **The key policy must grant permission directly or delegate to IAM policies**, alongside mechanisms like grants where appropriate.

For cross-account KMS access, check both the **key policy in the key-owning account** and the **IAM policy in the calling account**. If an S3 object uses SSE-KMS, an **AccessDenied** error can come from KMS even though both the IAM policy and S3 bucket policy allow **s3:GetObject**.

KMS key policies are managed in the Region of the key; do not assume a KMS policy in one Region automatically applies to a key in another Region.

## 8. Choosing the Policy Type in Real-World Scenarios

| Scenario | Where to consider placing permissions | Reason |
|---|---|---|
| An EC2/ECS/Lambda app needs to read a DynamoDB table or S3 object | **Identity-based policy** attached to the appropriate execution/task/instance role | Permissions follow the workload calling the API |
| An S3 bucket in Account B lets a specific role in Account A read data | **Bucket policy** in B **and** **identity policy** in A | Both sides must agree in a standard cross-account access path |
| A service needs to send events to an SQS queue | **SQS queue policy** with service principal and appropriate source-restricting conditions | The queue is the resource receiving requests from another service |
| A principal in Account A needs to assume a role in Account B | **Role trust policy** in B; **sts:AssumeRole** permission in A; **role permissions policy** in B | Governs both obtaining the role and executing actions after assumption |
| Only one role may decrypt using a KMS key | **Key policy** plus IAM/grants where appropriate | Key usage depends on KMS's authorization model |
| Block non-TLS S3 access | **Explicit Deny** in bucket policy | Enforces a resource-level guardrail across matching principals |
| Block sensitive actions across the entire organization | **SCP/RCP** where supported, combined with IAM/resource policies | Establishes an organization-level permission ceiling |

The design principle is to **grant only the permissions needed**, attach permissions where management ownership is clear, and use **IAM roles with short-lived credentials** for workloads rather than distributing long-term access keys.

## 9. Policy Design and Verification Process

### Step 1 — Map out the request flow

Document the principal, principal's account, API action, resource ARN, resource-owning account, and desired conditions. Distinguish **direct access** from **AssumeRole**.

### Step 2 — Check whether the service supports resource policies

Consult the service's IAM reference documentation. Verify whether the service supports **resource-based policies**, permitted principal types, actions per ARN type, and valid condition keys. Never copy an S3 policy to another service without checking syntax and semantics.

### Step 3 — Write minimal Allow and necessary Deny statements

- Restrict **Action** to required APIs; avoid **s3:\*** or **iam:\*** if only one operation is needed.
- Restrict **Resource** to specific ARNs/prefixes when the action supports resource-level permissions.
- For resource policies, restrict **Principal** to specific roles or principals; avoid granting Allow to **Principal: \*** unless part of an approved public-access design.
- Use **Condition** to further narrow by request origin, organization, tags, or TLS if supported by the service/condition key.
- Identify special requirements such as SSE-KMS, endpoint policies, SCPs/RCPs, session policies, and resource management permissions.

### Step 4 — Validate policy documents and test real access

AWS IAM Access Analyzer provides **ValidatePolicy** to catch many errors, configuration warnings, and recommendations. For an **identity policy** drafted in a test environment, you can validate it with:

~~~bash
aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY --policy-document file://identity-policy.json
~~~

For a resource-based policy, use **RESOURCE_POLICY** and check any extra parameters required by the resource type/service. Syntax validation is only the first step; to assess unintended resource-sharing risks, use **IAM Access Analyzer** and appropriate external-access findings checks.

Before tracing a permission error, confirm the active executing identity using:

~~~bash
aws sts get-caller-identity
~~~

Next, check policies attached to the right role/session and policies on the right resource. Test both **actions that should be allowed** and **actions that should be denied** in an authorized test environment. You can use **IAM Policy Simulator** for supported scenarios, though simulation results should not be treated as complete proof for all cross-account, resource policy, or service-specific control mechanisms.

### Step 5 — Monitor and review

Use **AWS CloudTrail** to audit API calls; review **IAM Access Analyzer** to spot unintended sharing; periodically compare granted permissions against actual usage. Permissions must be updated when a role changes function, an application adds new APIs, accounts change, or resources change ownership.

## 10. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Role has Allow but still gets **AccessDenied** reading a cross-account bucket | Target account bucket policy hasn't allowed the principal or another boundary blocks it | Principal ARN in bucket policy, role identity policy, Deny, and conditions |
| Can access objects but cannot list bucket contents | Has **s3:GetObject** but lacks **s3:ListBucket** | Action and bucket ARN vs. object ARN |
| AssumeRole succeeds but reading data fails | Trust policy only grants AssumeRole; target role's permissions policy is missing | Policy of the assumed role and policy of the target resource |
| IAM policy allows decrypt, yet KMS returns **AccessDenied** | Key policy does not allow or enable IAM delegation, or missing appropriate grants/permissions | Key ARN, key policy, IAM policy, and Region |
| Policy includes **Principal** and IAM validator rejects it | Used Principal inside an identity-based policy | Place Principal in resource policies/trust policies where it belongs |
| Bucket policy is saved, yet users are still blocked | Explicit Deny, Block Public Access, mismatched condition, or other protection | Check request context, SCP/RCP, encryption, and policies across layers |
| Using **Resource: \*** everywhere | Actions weren't analyzed by ARN, or copied an overly broad policy | Consult service authorization reference; narrow down where actions support it |
| Granted policy to an **IAM group**, but cannot access as a group | A group is not a sign-in identity or direct principal | Attach policy to the group so users inherit it; use role ARNs in resource policies |

## 11. Applied Exercises

**Scenario 1 — Same account:** A Lambda application in Account A needs to read objects under the **incoming/** prefix of an S3 bucket also in Account A. Where should a minimal design begin?

**Hint:** attach an identity-based policy to the **Lambda execution role** with **s3:GetObject** on the object ARN for the allowed prefix. Add **s3:ListBucket** on the bucket ARN if the code lists objects. Verify there are no other Denies/boundaries. You do not always need to add a duplicate bucket policy Allow for a role in the same account.

**Scenario 2 — Cross-account:** An analytics team in Account A needs to read objects from Account B's bucket without assuming a role in B. The team only added **s3:GetObject** in Account A's IAM policy and hit AccessDenied.

**Hint:** deploy a resource-based policy on the bucket in B specifying Account A's role principal and object ARN while keeping the identity-based Allow in A; check KMS conditions if objects are encrypted with SSE-KMS. Use IAM Access Analyzer and API tests to uncover any additional restrictions.

**Scenario 3 — Role trust:** Account B creates a role allowing a role from Account A to assume it. Is that enough for the source role to delete objects in B?

**Hint:** not yet. You must check the caller's **sts:AssumeRole** permission, the target role's trust policy, **s3:DeleteObject** in the role's permissions policy, and any bucket boundaries/protections. If the business workflow only requires reading, never grant delete permissions.

## 12. Checklist Before Applying an IAM Policy

- [ ] Accurately identified **principal**, **action**, **resource ARN**, **account**, and **condition**.
- [ ] Separated identity-attached permissions from resource-attached permissions.
- [ ] JSON policy has valid fields; identity-based policy does not contain **Principal**.
- [ ] Applied **least privilege**, avoiding overly broad Allows on Action, Resource, or Principal.
- [ ] Determined whether the request is same-account or cross-account, direct access or AssumeRole.
- [ ] Checked permissions boundaries, session policies, SCPs/RCPs, and explicit denies where present.
- [ ] Verified service-specific controls, such as S3 Block Public Access and KMS key policies.
- [ ] Validated the policy and tested both allowed behavior and behavior that must be denied.
- [ ] Set up CloudTrail monitoring and checked for unintended sharing with IAM Access Analyzer.

## 13. Key Takeaways and Official Documentation

An **identity-based policy** answers **"what can this identity do?"**; a **resource-based policy** answers **"who can do what with this resource?"**. Within the same account, the two permission sources typically combine via union under applicable boundaries. For cross-account access, analyze permissions in both the caller's account and the resource's account. **Explicit Deny** and boundary policies can render an Allow insufficient. For IAM roles, separate **assume permissions** from **post-assume execution permissions**.

AWS documentation to consult during implementation:

- [Identity-based policies and resource-based policies — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_identity-vs-resource.html)
- [Policy evaluation logic — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
- [Cross-account policy evaluation logic — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic-cross-account.html)
- [Permissions boundaries for IAM entities — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [Cross account resource access in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies-cross-account-resource-access.html)
- [Bucket policies — Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html)
- [Key policies — AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [Access Analyzer policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html)
