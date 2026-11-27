# Policy Structure with Action, Resource, and Condition

> **Chapter:** IAM and Permissions  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem and design secure, observable, resilient, and cost-controlled applications.

In AWS, signing in successfully to an account **does not mean** being allowed to call every API. AWS Identity and Access Management (**IAM**) uses **policies** to describe who can perform what actions, on which resources, and under what conditions. The three components you need to master to write scoped access permissions are **`Action`**, **`Resource`**, and **`Condition`**.

This lesson focuses on policy syntax and reasoning. The examples use fictional bucket names, account numbers, and ARNs; replace them with real values, check service documentation, and test in an appropriate environment before using them in production.

## 1. Learning Objectives

After this lesson, you can:

1. Read the structure of a JSON IAM policy, understanding `Version`, `Statement`, `Effect`, `Action`, `Resource`, and `Condition`.
2. Distinguish **identity-based policies**, **resource-based policies**, and **role trust policies**; know when `Principal` is used.
3. Choose appropriate actions, restrict resource ARNs, and apply conditions based on request context.
4. Explain allow, implicit deny, and explicit deny when multiple statements or multiple policy types are involved.
5. Write and analyze policies following the **least privilege** principle, and troubleshoot common errors using AWS tools.

## 2. Where Do IAM Policies Fit in the Authorization Flow?

An IAM policy is a JSON document describing **rules that grant or deny permissions**. It can be attached to an identity such as an IAM user, group, or role; it can also be attached directly to a resource that supports resource-based policies, such as an S3 bucket.

When an application using an **IAM role** calls an API, AWS inspects the details of the request:

- **Principal:** the identity making the API call, for example a role session from EC2 or Lambda.
- **Action:** the operation requested, for example `s3:GetObject`.
- **Resource:** the target object, for example `arn:aws:s3:::example-company-reports-2026/reports/summary.csv`.
- **Context:** additional attributes such as tags, IP address, endpoint region called, connection method, or authentication details, depending on the API and service.

AWS then evaluates applicable policies along with related boundaries. Never assume "having an Allow statement" guarantees access: there may also be an **explicit Deny**, permissions boundary, session policy, organization policy, or other conditions.

### 2.1. Common Policy Types

| Type | Where attached | Role |
| --- | --- | --- |
| **Identity-based policy** | IAM user, group, role | Describes permissions that an identity can use |
| **Resource-based policy** | Supported resource, e.g., S3 bucket | Describes which principals are allowed or denied access to the resource |
| **Role trust policy** | IAM role | Specifies which principals are allowed to assume the role via STS |
| **Permissions boundary** | IAM user or role | Sets the maximum permissions cap for an identity; does not grant permissions on its own |
| **Service control policy (SCP)** | AWS Organizations (account/OU) | Maximum cap for applicable principals in the organization; does not grant permissions on its own |
| **Session policy** | Supported STS session | Can restrict permissions of a temporary session |

A **Managed policy** is a standalone, reusable policy; it includes AWS managed and customer managed policies. An **Inline policy** is embedded directly into a single identity. These are ways of **packaging/attaching policies** and do not change the fundamental meaning of `Action`, `Resource`, and `Condition`.

## 3. Skeleton of an IAM JSON Policy

A simple identity-based policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReports",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
    }
  ]
}
~~~

This policy allows the identity to which it is attached to call `s3:GetObject` on objects whose keys begin with `reports/` in the example bucket. It does **not** grant permission to list the bucket, upload objects, or read objects outside that prefix.

| Field | Meaning | Notes |
| --- | --- | --- |
| `Version` | Policy language version | Typically `"2012-10-17"`; this is **not** the policy creation date |
| `Statement` | A single statement or list of statements | Each statement describes a group of rules |
| `Sid` | Identifier or label for the statement (optional) | Helps with reviews; does not grant permissions itself |
| `Effect` | `"Allow"` or `"Deny"` | Describes the outcome if the statement matches |
| `Action` / `NotAction` | Targeted operations | Normally use `Action` for clear scope |
| `Resource` / `NotResource` | Targeted resources | Must match what the action supports at the resource level |
| `Condition` | Additional conditions (optional) | Checks condition keys in the request context |
| `Principal` / `NotPrincipal` | Applicable identities in resource-based/trust policies | **Do not put `Principal` in an identity-based policy** |

A document can contain multiple statements. They **do not execute top-to-bottom like programming statements**, and `Sid` does not create priority. Every relevant statement can affect the outcome: a matching explicit Deny overrides Allow.

## 4. Action: Which Operations Are Permitted?

### 4.1. Syntax `service:ActionName`

Typically an IAM action takes the form:

~~~text
s3:GetObject
s3:ListBucket
s3:PutObject
ec2:DescribeInstances
ec2:StartInstances
lambda:InvokeFunction
~~~

The part before `:` is the **service prefix**; the part after is the IAM action name. Action names are often close to API names, but not every application operation maps one-to-one to an API name; consult the service's **Service Authorization Reference** to choose the right permissions.

`Action` can be a string or an array:

~~~json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:GetObjectVersion"
  ],
  "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
}
~~~

The statement above is an **illustrative fragment**, not a complete policy because it lacks the outer `Version` and `Statement`.

### 4.2. Wildcards in Action

AWS supports the wildcards `*` and `?` in many positions of an action string. For example:

- `s3:Get*`: can match many S3 operations starting with `Get`; the actual set of actions may be broader than expected.
- `ec2:Describe*`: covers many EC2 describe operations.
- `"*"`: every action of every service that the policy can evaluate, which is extremely broad.

Do not use wildcards just to shorten a policy. If only one type of data is being read, list the actions actually needed. `NotAction` means "all actions except the listed ones" within the scope of the matching statement; it can easily widen permissions unintentionally and requires very careful evaluation.

### 4.3. One Business Operation May Require Multiple Actions

For example, to display files in a bucket and then download one, an application may need:

1. `s3:ListBucket` to list object names.
2. `s3:GetObject` to read object contents.

These two actions use **different ARN types**. If objects are encrypted with SSE-KMS using a customer managed key, reading may also require appropriate KMS permissions and key policy configuration. When granting permissions, trace the entire actual execution path rather than looking only at application-layer API names.

## 5. Resource: Which Resources Does the Action Target?

### 5.1. Reading an ARN

An ARN (**Amazon Resource Name**) identifies an AWS resource. Common general format:

~~~text
arn:partition:service:region:account-id:resource
~~~

Examples:

~~~text
arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0123456789abcdef0
arn:aws:lambda:ap-southeast-1:123456789012:function:report-processor
arn:aws:s3:::example-company-reports-2026
arn:aws:s3:::example-company-reports-2026/reports/summary.csv
~~~

S3 ARNs omit the Region and account ID in those two slots. How the `resource` portion is formatted varies by service: some use `/`, others use `:`; do not guess an ARN format without checking the documentation.

### 5.2. S3 Buckets and S3 Objects Are Two Different Scopes

| Permission | Appropriate Resource | Meaning |
| --- | --- | --- |
| `s3:ListBucket` | `arn:aws:s3:::example-company-reports-2026` | List objects in the bucket |
| `s3:GetObject` | `arn:aws:s3:::example-company-reports-2026/reports/*` | Read objects under the `reports/` prefix |
| `s3:PutObject` | `arn:aws:s3:::example-company-reports-2026/uploads/*` | Upload objects to the `uploads/` prefix |
| `ec2:StartInstances` | `arn:aws:ec2:ap-southeast-1:123456789012:instance/*` | Start instances matching the ARN scope and conditions |

Because `s3:ListBucket` targets the **bucket**, attaching it to `.../reports/*` will not allow listing a folder as expected. Conversely, `s3:GetObject` targets **objects**, not a bare bucket ARN.

### 5.3. Is Resource `"*"` Always Wrong?

No. Some IAM actions **do not support** resource-level restrictions; when allowing such an action, `Resource` must be `"*"`. For example, `ec2:DescribeInstances` is commonly granted on `"*"`. For actions that do support resource-level permissions, prefer specific ARNs.

Some actions require permissions across multiple resource types in the same operation, or support different condition keys depending on resource type. Always verify against the **Actions, resources, and condition keys** table in the service's authorization reference.

### 5.4. Wildcards in Resource

`arn:aws:s3:::example-company-reports-2026/reports/*` covers every object key starting with `reports/`, including nested paths. S3 uses **object key prefixes** and does not have physical directories with automatic permission inheritance like a traditional filesystem.

Wildcards in resource ARNs must be reviewed carefully because they may match more resources than intended. `NotResource` inverts resource selection and can easily grant unintended scope when combined with Allow; usually you should explicitly list the permitted ARNs.

## 6. Condition: Allow Only When the Context Satisfies Conditions

`Condition` adds constraints such as "only start EC2 instances tagged `Environment=dev`" or "only handle requests over HTTPS."

A condition has the structure:

~~~json
"Condition": {
  "StringEquals": {
    "ec2:ResourceTag/Environment": "dev"
  }
}
~~~

Where:

- **Condition operator**: `StringEquals` specifies how the comparison is performed.
- **Condition key**: `ec2:ResourceTag/Environment` is the resource attribute supplied by EC2 in the context for supported actions.
- **Value**: `"dev"` is the required value.

### 6.1. Useful Operator Groups

| Example operator | Used for | Scenario example |
| --- | --- | --- |
| `StringEquals` | String must match value exactly | Environment tagged `dev` |
| `StringLike` | String may contain `*`, `?` patterns | Object prefix starting with `reports/` |
| `Bool` | Boolean conditions | Check `aws:SecureTransport` |
| `IpAddress` | IPv4/IPv6 and matching CIDRs | Restrict by source IP address where supported |
| `NumericLessThanEquals` | Numeric comparisons | Limit numeric API parameters with a matching condition key |
| `DateLessThan` | Timestamp comparisons | Time-bounded permissions based on timestamp values |
| `ArnEquals`, `ArnLike` | ARN comparisons | Restrict source ARNs in resource-based policies |
| `Null` | Check presence/absence of a key | Require a request to carry an attribute |

AWS has **global condition keys** such as `aws:RequestedRegion`, `aws:PrincipalTag/...`, `aws:SecureTransport`, and **service-specific condition keys** such as `s3:prefix` or `ec2:ResourceTag/...`. Not every condition key exists for every request/action.

### 6.2. How Multiple Conditions Combine

For standard affirmative operators:

- **Different operators** in the same `Condition` block must all be satisfied simultaneously.
- **Different condition keys** under the same operator must also all be satisfied simultaneously.
- **Multiple values** under the same key usually act as alternatives (OR), e.g., a string matching one of two prefixes.

Example:

~~~json
"Condition": {
  "StringEquals": {
    "ec2:ResourceTag/Environment": "dev",
    "aws:RequestedRegion": "ap-southeast-1"
  }
}
~~~

The request must match **both keys**. For negated operators, multi-value sets, or the `ForAnyValue:` and `ForAllValues:` prefixes, evaluation rules differ; do not assume they behave identically to the rules above.

### 6.3. What Happens When a Condition Key Is Missing?

Many affirmative comparisons such as `StringEquals` do not match if the key being checked is absent. However, operators with the `IfExists` suffix, `Null`, or negated comparisons follow special rules. In particular, `...IfExists` inside a **Deny** statement can produce counterintuitive effects.

This matters because request context differs between an IAM user, a role session, an AWS service principal, requests via a VPC endpoint, and traffic from the Internet. When writing security conditions, verify **whether the service/action provides that key** and test the actual call paths.

### 6.4. Two Frequently Misunderstood Condition Keys

- `aws:RequestedRegion` evaluates **the Region of the endpoint being called** for supported requests; it does **not** by itself guarantee that data or all service side effects remain exclusively in that Region. Certain global services require special handling.
- `aws:MultiFactorAuthPresent` must be understood in light of credential type and STS sessions. You cannot simply add an MFA condition and assume all federated logins or API keys are properly enforced; verify the authentication method and test it.

## 7. Complete Example 1: Read Only Reports Under One S3 Prefix

**Problem:** A reporting application needs to list and read objects under `reports/`, but must not upload, delete, or view objects under `private/`.

**Identity-based policy:**

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyReportsPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::example-company-reports-2026",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "reports/",
            "reports/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadOnlyReportObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
    }
  ]
}
~~~

**Analysis:**

1. Statement `ListOnlyReportsPrefix` sets `Action=s3:ListBucket`, `Resource` as the **bucket** ARN, and `Condition` accepting only matching prefix parameters.
2. Statement `ReadOnlyReportObjects` sets `Action=s3:GetObject` on the **object** ARN, restricted to the `reports/*` path.
3. There is no Allow statement for `s3:PutObject`, `s3:DeleteObject`, or `s3:GetObject` at `private/*`.
4. If a request omits a matching prefix, this policy does not grant `ListBucket`; the application must pass the appropriate prefix when calling the list API.

**Self-check table (considering only this example policy):**

| Request | Result per Allow rules in policy | Explanation |
| --- | --- | --- |
| `ListBucket` with `prefix=reports/` | Matches Allow | Correct bucket ARN and condition |
| `ListBucket` with `prefix=private/` | No Allow | Wrong `s3:prefix` |
| `GetObject` on `reports/summary.csv` | Matches Allow | Object ARN matches `reports/*` |
| `GetObject` on `private/payroll.csv` | No Allow | Object outside scope |
| `PutObject` into `reports/new.csv` | No Allow | Action not granted |

"Matches Allow" here is not necessarily the final system outcome: a bucket policy, permissions boundary, SCP, KMS key policy, or explicit Deny elsewhere can still affect it.

## 8. Complete Example 2: Start Only EC2 Instances in Dev

**Problem:** The development team may only start EC2 instances tagged `Environment=dev` in the Singapore Region, in example account `123456789012`.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StartDevInstancesInSingapore",
      "Effect": "Allow",
      "Action": "ec2:StartInstances",
      "Resource": "arn:aws:ec2:ap-southeast-1:123456789012:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/Environment": "dev",
          "aws:RequestedRegion": "ap-southeast-1"
        }
      }
    }
  ]
}
~~~

In this example:

- **Action** is `ec2:StartInstances`; the policy does not grant permission to stop or terminate instances.
- **Resource** is restricted to EC2 instances in one Region and one account.
- **Condition** requires the `Environment=dev` tag while also checking the specified endpoint Region.
- If an instance has no tag, or the tag has a different value, this statement does not grant start permission.

Tags are governance metadata. **If users themselves have permission to attach/edit tags**, they could make an instance that previously didn't match now match the policy. Therefore, tag-based authorization architectures must tightly control permissions like `ec2:CreateTags` and `ec2:DeleteTags`, including when executed through automation.

### 8.1. Extending to ABAC with Tags

In **Attribute-Based Access Control (ABAC)**, instead of writing separate policies for each team, you can compare a principal's tag with a resource's tag.

Illustrative Condition snippet:

~~~json
"Condition": {
  "StringEquals": {
    "ec2:ResourceTag/Team": "${aws:PrincipalTag/Team}"
  }
}
~~~

`${aws:PrincipalTag/Team}` in the snippet represents the **policy variable** `${aws:PrincipalTag/Team}`, which AWS substitutes with the principal's `Team` tag in the appropriate context. To avoid mistakes when reusing this pattern, verify whether the principal tag is reliably issued/controlled, whether the condition key is supported for the action, and whether tag modification permissions are restricted.

## 9. Example 3: Explicit Deny in a Bucket Policy

A **resource-based policy** can enforce secure transport even when a principal has an identity-based policy allowing object reads.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyPlainHttpRequests",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::example-company-reports-2026",
        "arn:aws:s3:::example-company-reports-2026/*"
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

Here:

- `Principal="*"` indicates the resource-based statement applies to all matching principals.
- `Effect="Deny"` blocks S3 requests matching the insecure transport condition.
- Both bucket and object ARNs are included to cover different types of actions.
- This is a **Deny** and does not grant HTTPS permissions by itself. Requests over HTTPS still require a valid Allow source and must pass other checks.

In practice, some AWS service-to-service calls may not forward complete network context keys to the target service. If the bucket is accessed by other AWS services, consult official guidance on `aws:PrincipalIsAWSService`, verify integration paths, and adjust the Deny condition appropriately to avoid unintentionally blocking services.

### 9.1. Why Is `Principal` Absent in Examples 7 and 8?

Examples 7 and 8 are **identity-based policies**, so the subject is already the identity to which the policy is attached. Inserting `Principal` into that policy type is invalid structure.

By contrast, Example 9 is an **S3 bucket policy**, a type of **resource-based policy**; here `Principal` specifies which identities the statement applies to.

## 10. Role Trust Policy: Who Can Assume the Role?

An IAM role typically has at least two related parts serving two distinct functions:

1. **Trust policy:** which principals can call `sts:AssumeRole` (or related mechanism) to assume the role.
2. **Permissions policy:** once the role session is active, which actions it can call on which resources.

Example trust policy for a Lambda execution role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLambdaServiceToAssumeRole",
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

A trust policy is a form of resource-based policy attached to the role, so **`Resource` is not needed** in the example statement: the role containing the trust policy is itself the target resource. This policy does **not** grant the function permission to read S3, write DynamoDB, or call other APIs; an appropriate permissions policy must be attached to the role.

For trust policies targeting external accounts or roles, it is usually necessary to restrict specific principals and add extra conditions such as `sts:ExternalId` where appropriate. Never open a trust policy to all principals just to "fix an AssumeRole error."

## 11. How Does AWS Evaluate Multiple Policies Together?

Foundational reasoning:

1. **Denied by default** (*implicit deny*) if no matching Allow basis exists.
2. A matching **explicit Deny** from an effective policy denies the request, even if an Allow exists elsewhere.
3. One or more Allows must match the action, resource, and condition. The outcome also depends on guardrails and the type of principal involved.

~~~mermaid
flowchart TD
    R["Request: principal + action + resource + context"] --> D{"Is there an applicable explicit Deny?"}
    D -->|Yes| NO["Deny"]
    D -->|No| A{"Is there a matching Allow?"}
    A -->|No| NO
    A -->|Yes| G{"Do other boundaries permit it?"}
    G -->|No| NO
    G -->|Yes| YES["Allow"]
~~~

**This diagram is a simplified mental model** and does not replace IAM's official evaluation algorithm. Details can vary by policy type, principal, role session, and whether access is same-account or cross-account. For example, the interaction between resource-based policies and permissions boundaries has special cases; consult documentation before drawing conclusions about a specific configuration.

### 11.1. Combining Constraints When Designing a System

Suppose a role has:

- An identity policy granting `s3:GetObject` on `reports/*`.
- An SCP restricting which services can be used in the account.
- A permissions boundary capping the role's permissions.
- An S3 bucket policy with an explicit Deny when requests fail to meet secure transport conditions.

A request to read a report can succeed only when it is **not Denied**, has an appropriate Allow grant, and passes all active boundaries. SCPs and permissions boundaries **do not grant Allow on their own**. Having an identity-based Allow also does not bypass conditions from a bucket policy.

For **cross-account** requests, you must inspect policies on both the caller side and the resource side, plus trust/assume-role if applicable. An Allow in the caller's account does not automatically open resources in another account.

## 12. Process for Writing Least-Privilege Policies

A useful practice is to work from **real business operations** to the policy, rather than starting with `Action="*"`.

1. **Identify the principal:** which role runs the application? How do users, CI/CD, EC2, or Lambda assume the role?
2. **List the APIs to call:** record specific actions from the SDK, CloudTrail, or service requirements. Separate read, write, and administrative actions.
3. **Choose Resource:** use the narrowest ARN if the action supports it; know when `"*"` is required.
4. **Add Condition:** include only keys supported by the action with reliable values in the request context.
5. **Split statements:** when actions require different ARN types or conditions, separate them to avoid unintended scope.
6. **Check related policies:** role trust, resource policy, KMS key policy, SCP, permissions boundary, and session policy.
7. **Validate and test:** use IAM Access Analyzer, the simulator, real API calls in a test environment, CloudTrail, and monitor denied requests.
8. **Review periodically:** remove unused permissions, control tag/role/policy editing permissions, and avoid standing permissions when session-based access suffices.

### 12.1. Supporting Tools

**IAM Access Analyzer policy validation** helps detect syntax errors, security warnings, and improvement suggestions. For example, suppose you save an identity policy in `policy.json`:

~~~bash
aws accessanalyzer validate-policy \
  --region ap-southeast-1 \
  --policy-type IDENTITY_POLICY \
  --policy-document file://policy.json
~~~

**IAM Policy Simulator** can test certain principal/action/resource combinations. Example with an illustrative role:

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:role/ReportReader \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::example-company-reports-2026/reports/summary.csv
~~~

These commands are for inspection only; they require AWS CLI with appropriate credentials and permissions. Replace ARNs, filenames, and Region for your real environment. **The simulator has limitations** and does not fully simulate all policy types, conditions, or service behaviors; simulation results do not replace real access testing.

When a real request is denied, examine the **exact action**, ARN, whether the condition key is present, the error message, and related events in **AWS CloudTrail**. CloudTrail helps with investigations, though you should not assume every request type or data event is logged by default; configure event logging accordingly.

## 13. Common Errors and How to Fix Them

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Allowed `s3:ListBucket` but files are not visible | Used object ARN instead of bucket ARN; `s3:prefix` does not match | Check the bucket ARN and the request's prefix parameter |
| Allowed `s3:GetObject` but still getting `AccessDenied` | Bucket/key policy Deny; missing SSE-KMS permissions; wrong object ARN | Inspect all policies, KMS permissions, encryption, and logs |
| `StartInstances` policy does not work | Instance lacks the `dev` tag, or wrong account or Region | Verify resource ARN, action, and condition keys |
| Added `Principal` to an identity policy and got a validation error | `Principal` is only used in applicable policy types | Remove `Principal` from the identity-based policy |
| Used `Action="s3:*"` for "read-only S3" | Wildcard also grants matching write/admin operations | Replace with the specific read actions needed |
| Added a new `Allow` but still getting Deny | There is an explicit Deny or org/boundary restriction | Trace where the Deny or boundary is applied |
| Role cannot be used by Lambda | Trust policy does not allow the service principal to assume the role | Inspect the trust policy and execution role configuration |
| Restricted by tag, but users can edit tags themselves | Tag management permissions are too broad | Restrict tag edits and protect authorization tags |
| Used `aws:SourceIp` to block all non-office access | Network context can differ when using proxies, VPC endpoints, or AWS services | Verify actual access paths and condition keys |

## 14. Policy Reasoning Exercises

### Exercise A — Fill in the three missing pieces

An invoice-processing application must **only upload** objects under the `invoices/incoming/` prefix of bucket `example-invoice-store-2026`. Identify:

1. Which `Action` should be used?
2. Should `Resource` be a bucket ARN or an object ARN?
3. If you want to allow requests only from a specified VPC endpoint, which condition key could you investigate? In what cases might that key be absent?

**Suggested answer:** `s3:PutObject`; `arn:aws:s3:::example-invoice-store-2026/invoices/incoming/*`; look into `aws:SourceVpce` for supported S3 access paths via a VPC endpoint, while checking requests that do not traverse the endpoint. Do not apply this condition blindly across every integration path.

### Exercise B — Explain the outcome

Given two statements applying to the same object:

~~~json
[
  {
    "Effect": "Allow",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
  },
  {
    "Effect": "Deny",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::example-company-reports-2026/reports/secret/*"
  }
]
~~~

Assuming no other policies apply, deduce:

- Reading `reports/summary.csv`: **Allow**, because the Allow statement matches and no Deny matches.
- Reading `reports/secret/finance.csv`: **Deny**, because the Deny statement applies even though Allow also matches.
- Writing `reports/summary.csv`: **implicit Deny**, since there is no Allow for `s3:PutObject`.

### Exercise C — Design for a real-world system

A Lambda service receives API requests and writes user-uploaded images to S3; an operations group needs to view logs but must not read private images. Do the following:

1. Sketch the principal flow: who assumes the Lambda execution role, who calls the API, who reads CloudWatch Logs?
2. Propose **two separate policies** for the application role and the operations support role.
3. Specify the `Action`, `Resource`, and `Condition` to restrict, and where ARN patterns are needed.
4. Think of one privilege-escalation path: if the operations group is allowed to edit the policy of their own role, how could they bypass the "logs-only" restriction? Which IAM administrative permissions must be controlled?

## 15. Key Takeaways

An IAM statement answers three primary questions:

- **`Action`:** which operation?
- **`Resource`:** on which target?
- **`Condition`:** only in what context?

`Effect` determines Allow or Deny; policy type determines scope and whether `Principal` is needed. **Least privilege** is achieved when actions, resources, conditions, and policy-editing permissions are all scoped to actual needs, then verified using tools and real behavior.

### Official AWS Documentation

- [IAM JSON policy elements reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements.html) — structure, `Action`, `Resource`, `Condition`, and related elements.
- [IAM JSON policy elements: Action](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_action.html) — how to specify actions.
- [IAM JSON policy elements: Resource](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_resource.html) — resource ARNs and wildcards.
- [IAM JSON policy elements: Condition](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition.html) — condition operators, keys, and values.
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — how policies, boundaries, SCPs, and Deny combine.
- [Actions, resources, and condition keys for AWS services](https://docs.aws.amazon.com/service-authorization/latest/reference/reference.html) — look up permissions per service/API.
- [IAM Access Analyzer policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) — check policy structure and warnings.
