# Bucket Policies, Access Points, and Block Public Access

> **Chapter:** S3 Object Storage  
> **Module:** CLOUD_PROVIDERS_AWS — explore AWS from Region/AZ, IAM, and VPC to compute, storage, databases, integration, and serverless; practice selecting services, protecting data, monitoring, recovering, and controlling costs.

## Learning Objectives

Amazon Simple Storage Service (**Amazon S3**) can hold documents, images, analytics datasets, backups, and diverse business data. The primary risk usually does not lie in the upload call itself, but in answering: **Who can read or modify an object, through which access path, and could an accidental configuration expose data publicly?**

The three central mechanisms in this lesson are:

- **Bucket policy:** a resource-based policy attached to an S3 bucket that controls valid requests based on principal, action, resource, and condition.
- **S3 Access Point:** a named access point attached to a data source such as a general purpose bucket, with its own policy and network origin settings to simplify permissions per application or team.
- **S3 Block Public Access (BPA):** a guardrail that prevents public access from being granted through ACLs and resource policies, configurable at multiple levels.

After this lesson, you will be able to:

1. Read, write, and evaluate bucket policies following the principle of **least privilege**.
2. Distinguish between IAM identity policies, bucket policies, Access Point policies, and Block Public Access.
3. Explain the four flags: `BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`, and `RestrictPublicBuckets`.
4. Design Access Points for distinct application groups, optionally restricting them to a VPC, and understand their relationship with bucket policies.
5. Inspect permissions using the AWS Console, IAM Access Analyzer, AWS CLI, and access logs/trails.
6. Perform a sandbox lab: verify protection status, create a private test bucket, optionally create an Access Point, and clean up resources.
7. Identify scenarios prone to `AccessDenied` or accidental public exposure, and apply safe remediation steps.

## 1. Where Is S3 Access Determined?

### 1.1. Conceptual Evaluation Flow

An application on EC2, Lambda, or a local machine sends a request to S3, such as `s3:GetObject`. AWS evaluates the calling identity, the target resource, and all relevant policies. If an **explicit Deny** applies, the request is rejected. When `Allow` statements are needed, they must align with the identity/resource policy model and not be blocked by SCPs, permissions boundaries, session policies, or other controls.

~~~mermaid
flowchart TD
    A[Application / IAM principal] --> B[GetObject / PutObject / ListBucket request]
    B --> C{Via Access Point?}
    C -->|Yes| D[Access Point: network origin + policy + BPA]
    C -->|No| E[Standard bucket endpoint]
    D --> F[Underlying bucket policy]
    E --> F
    F --> G[Evaluate IAM and related policies]
    G --> H[Does Block Public Access apply?]
    H --> I{Request allowed?}
    I -->|Yes| J[Read/write object]
    I -->|No| K[AccessDenied / rejected]
~~~

The diagram illustrates the **control checkpoints**, not the exact internal evaluation sequence of the service. A resource-based policy can sometimes grant permissions directly to a principal in the same account, whereas cross-account access has distinct requirements. What is certain is that **BPA never creates an `Allow` on its own**, and an Access Point never bypasses the underlying bucket policy.

### 1.2. Four Commonly Confused Mechanisms

| Mechanism | Attached Where? | Purpose | Can It Grant Permissions Itself? |
|---|---|---|---|
| **IAM identity-based policy** | IAM user, group, role | Defines which APIs the principal can call | Yes, via `Allow` |
| **S3 bucket policy** | Bucket | Defines principals, actions, resources, and conditions for accessing the bucket/objects | Yes, via `Allow`, or blocks via `Deny` |
| **S3 Access Point policy** | A specific Access Point | Restricts/grants permissions for requests routed **through that Access Point** | Can grant within the Access Point's scope, though the underlying bucket must also permit it |
| **S3 Block Public Access** | Organization, account, bucket, Access Point | Blocks **public** configurations/permissions that risk exposing data | No; only restricts public access |

In addition, there are **bucket Object Ownership**, ACLs, **VPC endpoint policies**, **KMS key policies** when using SSE-KMS, AWS Organizations policies, and other organizational controls. Do not treat these four mechanisms as the entirety of the authorization system.

## 2. Bucket Policies: Resource-Level Authorization Language

### 2.1. JSON Structure

A bucket policy is a JSON document written in AWS policy language. Each statement can include:

| Component | Function | Example |
|---|---|---|
| `Version` | Policy language version | `2012-10-17` |
| `Statement` | List of rules | One or more statements |
| `Sid` | Human-readable rule identifier | `AllowReaderGetReports` |
| `Effect` | `Allow` or `Deny` | `Allow` |
| `Principal` | Target identity; a bucket policy is a resource-based policy | Role ARN or AWS service principal |
| `Action` | Controlled API action | `s3:GetObject` |
| `Resource` | Bucket and/or object ARN | `arn:aws:s3:::bucket-name/reports/*` |
| `Condition` | Request conditions | `aws:SecureTransport`, `aws:PrincipalOrgID`, `s3:ExistingObjectTag`, etc. |

**Distinguishing bucket ARNs and object ARNs:**

~~~text
Bucket ARN:
arn:aws:s3:::aws-lab-private-demo

Object ARN:
arn:aws:s3:::aws-lab-private-demo/reports/2026/report.csv

All objects under prefix reports/:
arn:aws:s3:::aws-lab-private-demo/reports/*
~~~

- `s3:ListBucket` typically uses the **bucket ARN**.
- `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` typically use **object ARNs**.
- Other operations such as listing versions, managing policies, multipart uploads, and tagging have their own specific permissions; do not guess based on API names alone.

### 2.2. Example 1 — Granting Read-Only Access to One Prefix for One Role

Suppose a hypothetical bucket `aws-lab-private-demo` holds report data under the `reports/` prefix. Role `aws-lab-report-reader` in account `111122223333` only needs to read objects under this prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReportReaderRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/aws-lab-report-reader"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-private-demo/reports/*"
    }
  ]
}
~~~

This is an example of a **resource policy** allowing only the specified role to read objects under the prefix. For the role to **list** objects, add `s3:ListBucket` on the bucket ARN and restrict with `s3:prefix` if desired. If SSE-KMS is used, the principal must also have the corresponding KMS permissions and the KMS key policy must allow it.

Within the same account, a bucket policy can provide an authorization path independently of an identity-based policy, according to AWS policy evaluation rules. For **cross-account** access, the caller generally needs matching permissions on the source account side and the bucket policy in the target account must allow it. Do not oversimplify into "every policy must have an `Allow`" for all principal types without considering the context.

### 2.3. Example 2 — Blocking Non-TLS HTTP Requests

A common guardrail statement denies requests that do not use HTTPS:

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
        "arn:aws:s3:::aws-lab-private-demo",
        "arn:aws:s3:::aws-lab-private-demo/*"
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

This statement grants no permissions; it denies requests matching the non-TLS condition. For AWS service-to-service calls, certain network-related context keys may be omitted; when designing network-conditioned `Deny` rules, review the guidance for **AWS service principals** so you do not break logging, replication, or integrations.

**Rule when updating policies:** a bucket has only **one bucket policy document** at a time. Calling `PutBucketPolicy` writes a complete policy document and replaces the previous policy. When deploying, **merge statements into the existing policy** and verify the result beforehand; never overwrite a production policy with a standalone example JSON snippet.

### 2.4. Conditions to Narrow Permissions

| Condition Key | Common Meaning | Notes |
|---|---|---|
| `aws:SecureTransport` | Checks for HTTPS/TLS | Protects traffic in transit when conditioned properly |
| `aws:PrincipalOrgID` | Restricts principals to a specified AWS Organization | Does not replace per-principal policies; watch out for service principals |
| `aws:SourceVpce` | Requires traffic to come through a specific VPC endpoint | May block Console access or service integrations |
| `aws:SourceVpc` | Identifies the source VPC on supported requests | Present only when the request context supports it |
| `s3:prefix` | Limits the prefix for `ListBucket` | Cannot replace object ARNs for `GetObject` |
| `s3:ExistingObjectTag/<key>` | Checks an existing tag on an object for supported APIs | Object tags are distinct from bucket tags |
| `s3:DataAccessPointArn` | Controls requests routed through a specific Access Point | Useful for delegating authorization to an Access Point |
| `s3:DataAccessPointAccount` | Controls the account owning the Access Point | Suitable for delegating to Access Points within the same account |
| `s3:AccessPointNetworkOrigin` | Checks whether the Access Point origin is `VPC` or `Internet` | Not equivalent to route tables or VPC endpoint policies |

Use **explicit ARNs and fixed values** for sensitive constraints. Understand the differences among `StringEquals`, `StringNotEquals`, `ArnEquals`, `Bool`, and the `IfExists` modifier; an incorrect condition can accidentally block legitimate AWS services or leave access broader than intended.

### 2.5. Explicit Deny and the Risk of Locking Yourself Out

For example, many teams use a bucket policy to force requests through `aws:SourceVpce`:

~~~json
{
  "Sid": "DenyOutsideApprovedVpce",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::aws-lab-private-demo",
    "arn:aws:s3:::aws-lab-private-demo/*"
  ],
  "Condition": {
    "StringNotEquals": {
      "aws:SourceVpce": "vpce-0123456789abcdef0"
    }
  }
}
~~~

This is **an illustrative statement only**, not a production-ready policy. The AWS Console, many applications, and AWS services do not traverse that endpoint and could be denied—including administrators. In real architectures, design controlled administrative/recovery exceptions, account for service principals, and **test thoroughly before enforcing a broad Deny**.

## 3. Block Public Access: Four Flags to Distinguish

### 3.1. What Does "Public" Mean in S3?

Public permissions typically involve ACLs granted to predefined groups such as **AllUsers/AuthenticatedUsers** or resource policies that S3 evaluates as allowing public access. **`Principal: "*"` does not automatically make a policy public in every case**: AWS also inspects trusted fixed-value conditions, such as restricting to a specific principal or organization per S3's policy classification rules.

However, `Principal: "*"` is always a signal that requires **careful review**. Never assume a policy is safe merely because it includes an arbitrary `Condition`. Use **IAM Access Analyzer for S3** and AWS policy validation tools to detect public and cross-account access.

### 3.2. Exact Comparison of the Four Settings

| Block Public Access Flag | When Set to `true` | Does It Delete Existing ACLs/Policies? |
|---|---|---|
| **BlockPublicAcls** | Rejects APIs that set **new public ACLs** on buckets/objects and rejects uploads specifying public ACLs | **No** |
| **IgnorePublicAcls** | Ignores public ACLs during permission evaluation, including pre-existing ones | **No**, existing ACLs can still remain attached |
| **BlockPublicPolicy** | Rejects creating/updating **bucket or access point policies classified as public** within the active scope | **No**, does not delete existing policies |
| **RestrictPublicBuckets** | If a bucket/access point has a public policy, restricts public access and most cross-account access per service rules | **No**, restricts effective access |

**The two ACL flags differ:** `BlockPublicAcls` prevents adding new public ACLs; `IgnorePublicAcls` prevents S3 from **honoring** public ACLs during evaluation. Enabling both provides defense in depth, even when Object Ownership already disables ACLs.

**The two policy flags also differ:** `BlockPublicPolicy` prevents introducing a new public policy but **does not automatically rewrite an existing public policy**; `RestrictPublicBuckets` restricts access whenever an existing policy is evaluated as public, including cross-account delegations that might otherwise be permitted in that policy. This is why enabling all four is the safe default for private data.

### 3.3. Block Public Access Applies at Multiple Levels

In current AWS design, BPA can be configured at:

1. **AWS Organizations**: administrators can apply an S3 organization policy to enforce Block Public Access across member accounts. Organization-level settings enforce **all four flags together** as `all` or `none`.
2. **AWS account**: protects the account's buckets and Access Points across all Regions per S3 rules.
3. **Bucket**: protects the bucket and its associated Access Points.
4. **Access Point**: protects requests routed through a specific Access Point.

~~~mermaid
flowchart TD
    O[AWS Organizations: S3 Block Public Access policy if present]
    O --> A[Account-level Block Public Access]
    A --> B[Bucket-level Block Public Access]
    B --> P[Access Point-level Block Public Access]
    B --> Q[Direct request to bucket]
    P --> R[Request via Access Point]
    Q --> S[Most restrictive combination applies]
    R --> S
~~~

**Rule:** S3 enforces the **most restrictive combination** of applicable BPA settings. An Access Point cannot disable protections imposed at the account, bucket, or organization level. If bucket-level BPA is off while account-level BPA is on, requests still remain protected by the account-level settings. An organization-level policy can also prevent account administrators from lowering centrally managed settings.

**Note:** Modifying BPA does not delete existing policies or ACLs. If protection flags are later turned off, old public permissions can **take effect again**. Always audit policies, ACLs, and access flows before making any changes.

### 3.4. Defaults for New Buckets and Object Ownership

For **new S3 general purpose buckets**, AWS enables **all four Block Public Access settings** by default and sets **Object Ownership: Bucket owner enforced**, disabling ACLs for access control. Under this model:

- The bucket owner owns and controls objects via Object Ownership.
- Manage permissions using **IAM policies, bucket policies, and Access Point policies** instead of ACLs.
- API calls attempting to set unsupported object ACLs can fail with errors such as `AccessControlListNotSupported`.
- Never disable Block Public Access or change Object Ownership merely to work around an upload error before understanding the root cause.

Older buckets created previously may retain legacy settings, so **always inspect the actual configuration** rather than assuming every bucket follows current defaults.

## 4. S3 Access Points: Separating Permissions by Application and Network Origin

### 4.1. Why Are Access Points Useful?

Suppose a bucket holds three data zones:

~~~text
aws-lab-shared-datasets/
├── analytics/
│   └── events-2026.json
├── finance/
│   └── invoices.csv
└── exports/
    └── daily-summary.json
~~~

When multiple applications and teams share one bucket, a single bucket policy can grow long and hard to maintain. One solution is to create Access Points:

- **`ap-analytics-read`**: allows only the analytics app to read `analytics/`.
- **`ap-finance-private`**: allows only the finance role to read or write `finance/` from a VPC.
- **`ap-exports-write`**: allows export workers to write to `exports/`.

Each Access Point has its own **name, ARN, access point policy, network origin, and BPA**. It does not duplicate data into a new bucket: all Access Points point to the **underlying data source**.

~~~mermaid
flowchart LR
    A[Analytics app] --> P1[Access Point analytics-read]
    B[Finance app in VPC] --> P2[Access Point finance-private]
    C[Export worker] --> P3[Access Point exports-write]
    P1 --> S[(Bucket: shared datasets)]
    P2 --> S
    P3 --> S
    D[Bucket policy + IAM + BPA] -. Controls .-> S
~~~

### 4.2. Access Point ARNs Differ from Bucket ARNs

Example Access Point named `ap-analytics-read` in Region `ap-southeast-1` and account `111122223333`:

~~~text
Access Point ARN:
arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read

Object ARN via Access Point:
arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read/object/analytics/events-2026.json

Object prefix via Access Point:
arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read/object/analytics/*
~~~

Compare with:

~~~text
Bucket ARN:
arn:aws:s3:::aws-lab-shared-datasets

Direct object ARN via bucket:
arn:aws:s3:::aws-lab-shared-datasets/analytics/events-2026.json
~~~

**Do not mistakenly use the bucket ARN as the `Resource` in an Access Point policy**. For object actions via an Access Point, the Resource must use the `accesspoint/.../object/...` ARN format; for `s3:ListBucket` via an Access Point, use the appropriate **Access Point ARN**.

S3 also provides an **Access Point alias** for general purpose buckets. An alias can be used in place of a bucket name in many data operations; however, an alias **does not replace the ARN in IAM policies**. API support via Access Points also has limits: for example, you cannot use an Access Point to delete a bucket or configure bucket replication.

### 4.3. Network Origin: Internet and VPC

When creating an Access Point for an S3 general purpose bucket, you select one of two **network origins**:

| Network Origin | Meaning | When to Choose? |
|---|---|---|
| **Internet** | Requests can reach the Access Point over supported network paths if IAM/resource policies allow | Applications not tied to a single VPC; **does not mean public/anonymous** |
| **VPC** | Accepts requests only over the network from the **specified VPC**, per AWS mechanisms and conditions | Private workloads inside a VPC requiring isolated access paths |

With a **VPC**-origin Access Point, requests originating outside the configured VPC are rejected by S3, even if IAM grants `Allow`. You must properly design the **VPC endpoint**, DNS, routing, endpoint policy, and IAM/resource policies along the actual path.

**Immutable after creation:** an Access Point's network origin and VPC ID, as well as the **Access Point's four BPA settings**, cannot be modified after the Access Point is created. If the initial choice was wrong, you must delete and recreate the Access Point with the desired settings while assessing the impact on clients and policies.

**Do not confuse an Access Point with a VPC endpoint:**

- An **S3 Access Point** is a named S3 access endpoint with its own policy.
- An **S3 gateway VPC endpoint** routes traffic from a VPC to S3 via route tables; an **S3 interface VPC endpoint** provides private IPs via AWS PrivateLink in supported scenarios.
- A VPC-origin Access Point requires a valid network path from the chosen VPC; an Access Point does not create a NAT Gateway, VPC endpoint, or route table on its own.

### 4.4. Access Point Policy and Underlying Bucket Policy Must Align

AWS requires **both the Access Point and the underlying bucket to allow** the request under the applicable authorization model. An Access Point policy only applies to requests **routed through that Access Point**; direct requests to the bucket or another Access Point are evaluated via their respective paths.

Two common implementation patterns:

1. **Delegation:** the bucket policy delegates a set of actions to an approved Access Point (or Access Points), and the Access Point policy narrows principals and object prefixes.
2. **Matching permissions:** the bucket policy grants the same principal access on the underlying resource, and the Access Point policy further constrains requests passing through it.

For this lesson, we use the **delegation to a single Access Point** pattern, which makes authorization paths easy to audit and scope.

## 5. Coordinating a Bucket Policy and an Access Point Policy

### 5.1. Objective

An analytics team needs to read data under the `analytics/` prefix in bucket `aws-lab-shared-datasets`. Requirements:

- Only role `aws-lab-analytics-reader` in account `111122223333` may use Access Point `ap-analytics-read`.
- Grant only `s3:GetObject` on the `analytics/` prefix.
- The bucket allows requests **exclusively through this exact Access Point ARN**; the Access Point policy restricts the principal.
- Keep all four BPA flags enabled on the bucket, account, and Access Point.
- If object listing is needed, separately add `s3:ListBucket` with an appropriate `s3:prefix` condition.

**Example 1 — Bucket policy delegating `GetObject` through the Access Point:**

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DelegateAnalyticsReadToOneAccessPoint",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-shared-datasets/analytics/*",
      "Condition": {
        "ArnEquals": {
          "s3:DataAccessPointArn": "arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read"
        }
      }
    }
  ]
}
~~~

Because `Principal` is `*`, **the fixed condition on the Access Point ARN is an essential safeguard**. AWS evaluates whether a policy is public based on detailed rules; before applying any policy, check IAM Access Analyzer and Block Public Access. Never remove the `Condition` in this example.

**Example 2 — Access Point policy restricting role and prefix:**

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReaderOnlyAnalyticsObjects",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/aws-lab-analytics-reader"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read/object/analytics/*"
    }
  ]
}
~~~

**Expected behavior:** a `GetObject` request for `analytics/sample.json` via the Access Point from the authorized role is allowed if all remaining IAM/boundary/session/SCP/BPA/KMS/network checks pass. A `GetObject` request for `finance/invoices.csv` or from an unauthorized role has no matching `Allow` from this Access Point policy.

**Practical considerations to remember:**

- The bucket policy must be **merged** with existing statements; never apply a demo policy as a wholesale replacement in production.
- An Access Point policy **does not automatically close direct access to the bucket** if the bucket still has other policy or identity permissions allowing direct access. To mandate Access Point usage, construct deliberate guardrails and verify S3 feature compatibility.
- If SSE-KMS is used, review the **KMS key policy and IAM permissions**; `GetObject` alone is not sufficient in all cases.
- An Access Point administrator is not always the bucket owner, especially with **cross-account Access Points**. The bucket owner retains ultimate control over the data through the bucket policy.
- An object may be accessible via multiple authorization paths; never judge effective permissions from a single JSON statement in isolation.

### 5.2. Cross-Account Scenarios

Suppose an Access Point is owned by **Account B** while the bucket is owned by **Account A**. In this case:

1. Access Point B is created and attached to bucket A using the appropriate APIs and prerequisites.
2. **Bucket owner A** must permit requests from Access Point B via its bucket policy.
3. Access Point B's policy and the caller's identity policy must both permit the requested action.
4. SCPs, BPA, RCPs (if applicable), KMS, and network conditions must all be evaluated across the relevant accounts, principals, and resources.
5. Account A still decides what data is shared; Account B creating an Access Point does not automatically grant access to bucket A.

S3 Access Points are not a way to bypass account boundaries or data-sharing approval workflows.

## 6. Choosing the Right Access Model

| Requirement | Recommended Design | Rationale |
|---|---|---|
| One internal app, few principals, one bucket | IAM role + bucket policy if needed | Fewer management layers, clear scope |
| Multiple apps accessing different prefixes of one bucket | Multiple **S3 Access Points** with separate policies | Reduces complexity of maintaining one giant bucket policy for many teams |
| Only apps inside a VPC allowed on an access path | **VPC-origin Access Point** + VPC endpoint and matching policy | Enforces network origin and isolates per application |
| Strict requirement to prevent public data | **All four BPA flags enabled** at account/bucket level, consider organization level | Protects against unintended public ACLs/policies |
| Temporary object sharing for authenticated users | **Presigned URL** or an approved distribution mechanism | Signed URL has an expiration and inherits signer permissions; does not make the bucket public |
| Serving public files on the web | **CloudFront + Origin Access Control (OAC)** with a private S3 bucket | Serves publicly via CDN/HTTPS while keeping the S3 origin private |
| Sharing with a partner AWS account | Cross-account role/bucket policy or approved cross-account Access Point | Clear accountability and explicitly named principals |
| Multi-account batch analytics datasets | Evaluate Access Points, data governance, and Lake Formation if appropriate | Access control requires dataset-level governance, not just object permissions |

**You do not have to create an Access Point for every bucket.** If a bucket serves a single application with a simple policy, adding an Access Point may introduce operational overhead without meaningful benefit. Conversely, shared multi-team buckets often benefit significantly from separating access paths and policies.

## 7. AWS CLI Hands-On in a Sandbox

> This lab is strictly for authorized sandbox accounts. Commands create and delete real resources; before running them, verify the target account and Region, use no private/production data, and complete all cleanup steps. Buckets, API requests, stored data, logging, and networking components can incur charges. Examples use **Bash** and **AWS CLI v2**.

### 7.1. Prepare Identity

If using IAM Identity Center, sign in with your sandbox profile:

~~~bash
aws sso login --profile aws-lab-dev

export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity
~~~

Verify that the returned `Account` and `Arn` match the intended **sandbox**. If using **AWS CloudShell** inside a logged-in Console session without the `aws-lab-dev` profile, skip `aws sso login` and `export AWS_PROFILE` and use the current session credentials.

To run the entire lab, your identity needs appropriate permissions for buckets, objects, BPA, and (for the Access Point section) S3 Control APIs; do not attach `AdministratorAccess` just to bypass `AccessDenied`.

### 7.2. Step 1 — Check Existing Account BPA (Read-Only)

~~~bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws s3control get-public-access-block \
  --account-id "$ACCOUNT_ID"
~~~

If you receive `NoSuchPublicAccessBlockConfiguration`, it means **no account-level BPA configuration was returned by this API**; do not assume all resources are public or that organization/bucket-level protections are absent. If the account belongs to an AWS Organization with an S3 policy, reading or editing account-level settings may be centrally managed.

**Learning goal:** inspect the account's active BPA protection, rather than only looking at individual buckets in the Console.

### 7.3. Step 2 — Create a Private General Purpose Bucket

Choose a unique bucket name containing no sensitive information:

~~~bash
BUCKET="aws-lab-policy-$(date +%s)-$RANDOM"
echo "$BUCKET"

aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --create-bucket-configuration "LocationConstraint=$REGION"
~~~

The command above targets **ap-southeast-1**. For **us-east-1**, the creation syntax differs: `LocationConstraint` is typically **omitted**. The bucket name must satisfy S3 naming rules and be unclaimed in the applicable namespace; if `BucketAlreadyExists` occurs, choose another name.

**Do not disable account-level BPA to run the lab.** New buckets are private by default; next, explicitly configure and verify the desired protection state.

### 7.4. Step 3 — Enable All Four BPA Flags on the Bucket

~~~bash
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

aws s3api get-public-access-block \
  --bucket "$BUCKET"

aws s3api get-bucket-ownership-controls \
  --bucket "$BUCKET"
~~~

Expected output: all four flags return `true`; for a newly created bucket, Object Ownership is typically **Bucket owner enforced**. If one of the `get` commands returns `AccessDenied`, check your permissions to read configurations; do not conclude BPA is disabled simply because you cannot read it.

### 7.5. Step 4 — Upload a Test Object

~~~bash
printf 'S3 policy training data\n' > s3-training.txt

aws s3api put-object \
  --bucket "$BUCKET" \
  --key "analytics/sample.txt" \
  --body s3-training.txt

aws s3api head-object \
  --bucket "$BUCKET" \
  --key "analytics/sample.txt"
~~~

The object is uploaded using your active credentials without any public ACL. A private bucket can still be read and written by authorized principals. That is the difference between **private** and **"inaccessible to everyone"**.

### 7.6. Step 5 — Inspect Bucket Policy and Public Status (Read-Only)

~~~bash
aws s3api get-bucket-policy \
  --bucket "$BUCKET"

aws s3api get-bucket-policy-status \
  --bucket "$BUCKET"
~~~

A new bucket with no policy attached returns `NoSuchBucketPolicy` on the first command; this is normal. For `get-bucket-policy-status`, behavior can vary when no policy exists, permissions are missing, or governance is managed at another level. Always combine **BPA + IAM + bucket policy + IAM Access Analyzer** rather than treating a single command output as absolute proof.

This lab **does not require attaching a public bucket policy**. If you want to practice writing JSON policies, save the example policies locally, analyze their effective scope, and deploy only in a sandbox with a review process.

### 7.7. Step 6 (Optional) — Create a VPC-Origin Access Point

**Additional prerequisites:** you have a real sandbox VPC, permissions to create an S3 Access Point, and a valid VPC/network path to S3. Never use the illustrative VPC ID as if it were a real resource.

~~~bash
VPC_ID=vpc-0123456789abcdef0
AP_NAME="aws-lab-analytics-$RANDOM"

aws s3control create-access-point \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME" \
  --bucket "$BUCKET" \
  --vpc-configuration "VpcId=$VPC_ID" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

aws s3control get-access-point \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME"
~~~

Verify that `NetworkOrigin` is `VPC`, `VpcConfiguration.VpcId` matches, and all four BPA flags are enabled.

**Lab scope warning:** creating an Access Point does not by itself grant you permission to read objects **through the Access Point**. You also need **aligned bucket and Access Point policies**, an authorized IAM role, a network path from the VPC, and KMS permissions if using SSE-KMS. Test a valid policy modeled on section 5 beforehand; never open public access "just to make it work."

To view an existing Access Point policy:

~~~bash
aws s3control get-access-point-policy \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME"
~~~

If `NoSuchAccessPointPolicy` is returned, the Access Point has no dedicated policy yet; this is expected right after creation. For a VPC-origin Access Point, calling it from CloudShell or a laptop outside the VPC is not a valid test of that access path.

### 7.8. Step 7 — Clean Up Resources in the Right Order

If you created an Access Point and have delete permissions, delete the Access Point **first**:

~~~bash
aws s3control delete-access-point \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME"
~~~

Only run the command above if you **actually created** the Access Point stored in `AP_NAME`. Next, delete the lab object and bucket:

~~~bash
aws s3api delete-object \
  --bucket "$BUCKET" \
  --key "analytics/sample.txt"

aws s3api delete-bucket \
  --bucket "$BUCKET" \
  --region "$REGION"
~~~

A bucket must be **empty** before deletion. If you enabled versioning, uploaded additional objects, started multipart uploads, or configured replication, clean up those items according to their lifecycle/procedures. You can remove the local `s3-training.txt` file once no longer needed. Verify in the Console/CLI that both the Access Point and lab bucket are gone.

**Never delete shared Access Points or buckets**. Record the names/IDs of resources you create before closing your terminal; losing shell variables does not remove AWS resources.

## 8. Troubleshooting `AccessDenied` and Accidental Public Exposure

### 8.1. Layered Diagnostic Workflow

1. **Identity:** run `aws sts get-caller-identity` to confirm the active IAM principal/role session and account.
2. **Access path:** is the request going **directly to the bucket** or **via an Access Point ARN/alias**?
3. **Network:** for a VPC-origin Access Point, is the client actually inside the designated VPC? Are the VPC endpoint, route table, DNS, and endpoint policy correct?
4. **Action and ARN:** is `ListBucket` using the right bucket/Access Point ARN? Is `GetObject` using the object ARN with the right prefix?
5. **Permissions:** check IAM identity policies, bucket policies, Access Point policies, permissions boundaries, session policies, SCPs/RCPs where applicable, and KMS key policies if using SSE-KMS.
6. **Block Public Access:** is a public ACL or policy being blocked? Has the account or organization enforced stricter flags?
7. **Audit trails:** inspect AWS error messages, CloudTrail (including data events if enabled), S3 server access logs if configured, IAM Access Analyzer findings, and AWS Config/Security Hub if used by your organization.
8. **Minimal fix:** fix the exact missing permission or misconfiguration; never add `Principal: "*"` or disable BPA to bypass an error.

### 8.2. Troubleshooting Matrix

| Symptom | Possible Cause | Remediation Path |
|---|---|---|
| `PutBucketPolicy` reports public policy is blocked | `BlockPublicPolicy` is enabled at bucket/account/organization level | Check for wildcards or untrusted conditions; design a non-public policy |
| `PutObject` with `public-read` is rejected | `BlockPublicAcls` or Object Ownership Bucket owner enforced | Remove public ACL; manage access via policies |
| Legacy ACL shows `AllUsers` but object cannot be read publicly | `IgnorePublicAcls` or another public restriction is active | Keep protections enabled and remove legacy public ACLs via process |
| Bucket policy allows a partner account, yet cross-account requests fail | `RestrictPublicBuckets` because S3 classifies the policy as public, or missing IAM/SCP/KMS permissions | Check `get-bucket-policy-status`, rewrite the policy to be non-public, and verify cross-account permissions |
| Access Point policy has `Allow` but caller still gets `AccessDenied` | Underlying bucket policy does not allow requests via the AP, or IAM/KMS/BPA restricts it | Compare both policies and the object/Access Point ARNs |
| VPC-origin Access Point cannot be used from laptop/CloudShell | Client is not inside the designated VPC | Test from a workload inside the VPC over a valid network path |
| Direct S3 calls still read objects even though the Access Point targets one team | Bucket/identity policies still allow direct bucket access | Audit all grant paths; enforce Access Point usage if appropriate |
| `GetBucketPolicy` returns `NoSuchBucketPolicy` | No bucket policy is attached | Do not confuse this with BPA being off or the bucket being public |
| Bucket/Access Point name errors or conflicts | Violates naming rules, namespace, or Region constraints | Check naming rules and Regional support |
| Cannot change an Access Point's network origin or BPA | Those attributes are immutable after creation | Plan to delete/recreate the AP and update clients |
| Accessing an SSE-KMS object returns 403 despite `s3:GetObject` | KMS permissions, key policy, or condition mismatch | Verify `kms:Decrypt` and the KMS key policy |
| Access Analyzer reports unexpected external access | Bucket policy, Access Point policy, or ACL has a broad grant path | Verify principals/paths, tighten to a non-public policy, and enforce BPA |

### 8.3. Distinguishing Connectivity Issues from Permission Issues

- **Timeouts / DNS failures:** prioritize checking VPC DNS, VPC endpoints, route tables, security groups, and network paths.
- **HTTP 403 AccessDenied:** network connectivity to S3 usually succeeded; analyze policies and request validity.
- **`NoSuchKey` or 404:** verify the object key, bucket/Region, and permissions; for security reasons, S3 may return different error codes depending on whether the principal holds `ListBucket`.
- **`AccessControlListNotSupported`:** check Object Ownership (Bucket owner enforced) and whether upload code is still passing ACL headers.

Never infer a root cause solely from an HTTP status code without reading the full request context.

## 9. Defense-in-Depth Security Architecture

### 9.1. Reference Architecture for Private S3 Applications

~~~mermaid
flowchart LR
    U[Application users] --> A[API Gateway / ALB]
    A --> W[Lambda / EC2 application role]
    W --> V[VPC endpoint if in VPC]
    V --> P[VPC-origin S3 Access Point]
    P --> B[(Private S3 bucket)]
    I[Least-privilege IAM] -.-> W
    E[Access Point policy] -.-> P
    C[Bucket policy + BPA + SSE-KMS] -.-> B
    M[CloudTrail / Access Analyzer / CloudWatch] -. Monitoring .-> B
~~~

Recommended layers:

1. **Identity-based IAM**: grant applications only the specific APIs and object prefixes they require.
2. **Access Points**: isolate access flows across components; use VPC-origin when private network paths are required.
3. **Bucket policy**: delegate to approved Access Points and deny inappropriate request patterns.
4. **Block Public Access**: enable all four flags at account/bucket/AP levels, and consider organization-level enforcement; never open public access for convenience during development.
5. **Encryption**: S3 encrypts new objects server-side by default; if key-level control is required, choose SSE-KMS per policy.
6. **Auditing**: use CloudTrail management events and S3 **data events** when object-level auditing is needed; note that data events can incur additional charges and not every object GET/PUT appears in the default Event history.
7. **Data protection**: versioning, replication, lifecycle rules, Object Lock, or AWS Backup aligned with RPO/RTO and retention rules.
8. **Cost governance**: track storage classes, request counts, lifecycle transitions, replication, KMS requests, logs, and data transfer.

S3 is designed for high durability, but **durability does not protect against accidental deletion, overwrites, misconfigured policies, or compliance gaps**. Select data-protection controls based on recovery objectives.

### 9.2. CloudFront and Presigned URLs

For web applications serving images or files:

- Keep the S3 bucket **private**.
- Use **Amazon CloudFront Origin Access Control (OAC)** so CloudFront reads from the bucket under a scoped policy, paired with caching, TLS, and appropriate CDN protections.
- Use **presigned URLs** to grant temporary access to specific objects; the URL carries a signature backed by the signer's credentials with an expiration time and must be protected against leakage.
- **CORS** only governs browser cross-origin behavior—it is neither IAM authorization nor a mechanism to make objects public.

Never turn off Block Public Access simply to render an image on a frontend; first choose the appropriate file-delivery pattern.

## 10. Design and Effective-Permissions Exercise

### 10.1. Scenario

A company uses a single bucket `school-content` containing:

~~~text
school-content/
├── public-preview/
├── student-reports/
├── teacher-materials/
└── exports/
~~~

There are four workloads:

- **Student API:** reads `student-reports/` under application rules; each student must only see their own data.
- **Teacher Portal:** reads `teacher-materials/` and certain reports.
- **Export worker:** only writes new objects to `exports/` from inside a VPC.
- **Public preview:** preview content for web users, intended to be served via CDN.

Requirements: no anonymous S3 access; team-level permission separation; trackable costs; auditing of permission changes; ability to recover from accidental object deletion.

### 10.2. Proposed Design

| Component | Decision | Rationale |
|---|---|---|
| Bucket | `school-content`, private, all four BPA flags enabled | Blocks public access by default |
| Student API | Dedicated role + Access Point scoped to the needed prefix | Separates application permissions; **per-student** authorization must still be enforced at the application layer |
| Teacher Portal | Dedicated role + Access Point with restricted policy | Avoids sharing a role with the Student API |
| Export worker | VPC-origin Access Point and IAM allowing only `PutObject` to `exports/` | Restricts network origin and write permissions |
| Public preview | CloudFront + OAC | Public distribution via CDN while keeping the S3 origin private |
| Auditing | IAM Access Analyzer, CloudTrail data events as needed, periodic policy reviews | Detects unintended permissions |
| Recovery | Versioning and lifecycle/backups aligned with RPO/RTO | Reduces accidental deletion risk and controls version storage costs |
| Cost | Tags, AWS Budgets, S3 Storage Lens / Cost Explorer as appropriate | Tracks storage, requests, class transitions, and CDN usage |

**Important:** S3 IAM/bucket policies evaluate AWS principals and request context; **S3 does not automatically know which student is logged into your app** when multiple students are served through a single backend IAM role. The backend must authenticate users and validate tenant/student IDs before reading objects, or implement a thoroughly tested identity-to-object-key mapping design.

### 10.3. Practice Questions

1. Why does `s3:ListBucket` require a different ARN than `s3:GetObject`?
2. If a bucket policy has an `Allow` for Role A, while the Access Point policy only allows Role B, will Role A's request through that Access Point succeed? Why or why not?
3. If account-level BPA has all four flags enabled while bucket-level BPA is off, do objects automatically become public?
4. Does an `Internet`-origin Access Point mean anyone on the Internet can view objects?
5. Why shouldn't you turn off `BlockPublicPolicy` just to attach a bucket policy containing `Principal: "*"`?
6. If you want to use `aws:SourceVpce` in a bucket policy, what should you test before applying a broad `Deny`?
7. Does a bucket policy delegating to an Access Point block all direct requests to the bucket?
8. Why is a presigned URL not equivalent to "making the bucket public"?
9. When the Student API shares a single IAM role across all students, does IAM automatically isolate each student's objects?
10. What recovery mechanisms beyond Block Public Access are needed for accidentally deleted data?

## 11. Production Readiness Checklist for S3

### 11.1. Access Control

- [ ] Bucket owner, account, Region, and bucket type are clearly defined.
- [ ] Bucket/Object Ownership is configured appropriately, minimizing or disabling ACLs.
- [ ] Account, bucket, and Access Points have appropriate BPA enabled; consider AWS Organizations-level enforcement.
- [ ] Bucket policies and Access Point policies have been reviewed with IAM Access Analyzer.
- [ ] Principals use temporary role credentials and least privilege; no hardcoded access keys in code.
- [ ] Object ARNs, prefixes, tags, and IAM conditions match the workload accurately.
- [ ] Cross-account access is formally approved and explicitly permitted by the bucket owner.
- [ ] If using VPC-origin APs, VPC endpoints, DNS, routing, network origin, and policies are verified.
- [ ] If using SSE-KMS, KMS key policies and IAM permissions are tested.

### 11.2. Operations

- [ ] CloudTrail logs, data events, and Access Analyzer are configured per audit requirements.
- [ ] Detection is in place for unintended public or cross-account access.
- [ ] Versioning, backups, replication, or Object Lock are configured where data requires them, and restores have been tested.
- [ ] Tagging, lifecycle rules, cost allocation, and budget alerts are configured.
- [ ] Safe policy deployment, lockout recovery procedures, and pre-change testing are established.
- [ ] Decommissioning procedures exist to revoke Access Points, policies, and objects when an app is retired.

## Official AWS Documentation

- [S3 bucket policies and examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html)
- [Bucket policy examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/example-bucket-policies.html)
- [Blocking public access to S3 storage](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)
- [Configuring account-level Block Public Access](https://docs.aws.amazon.com/AmazonS3/latest/userguide/configuring-block-public-access-account.html)
- [S3 Object Ownership](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html)
- [Managing access to shared datasets with S3 Access Points](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points.html)
- [Access Point policy examples and delegation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-policies.html)
- [Creating VPC-restricted S3 Access Points](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-vpc.html)
- [Managing Access Point Block Public Access settings](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-bpa-settings.html)
- [Troubleshooting S3 403 AccessDenied](https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-403-errors.html)
- [IAM Access Analyzer for S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-analyzer.html)
- [AWS Organizations S3 policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_s3_syntax.html)

> **Application Note:** Bucket names, account IDs, VPC IDs, role ARNs, and Access Point ARNs in this lesson are illustrative examples only. Never copy example policies into production without merging them into existing configurations and verifying effective permissions. AWS documentation evolves over time; before deploying, verify feature support, policy behavior, pricing, and current quotas in your Region and account.
