# IAM Access Analyzer, Policy Simulator, and Troubleshooting AccessDenied

An application running on AWS can hit **AccessDenied** errors even when an engineer has attached an IAM policy with **Effect: Allow**. Sometimes the cause is the wrong principal, wrong resource ARN, a missing action, a mismatched condition, an **explicit deny** in another policy, or cross-account access not approved on both sides. To troubleshoot effectively, combine **IAM Access Analyzer**, **IAM Policy Simulator**, **AWS CloudTrail** logs, and AWS policy evaluation logic.

This lesson is in the **IAM and Permissions** chapter of the **CLOUD_PROVIDERS_AWS** module. Along the learning path covering Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless, understanding access control helps learners choose services and deploy applications that are secure, observable, recoverable, and cost-controlled.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish the purposes of **IAM Access Analyzer**, **policy validation**, **IAM Policy Simulator**, and **CloudTrail**.
2. Explain why an **Allow** in one policy is insufficient to conclude an API request will succeed.
3. Use policy validation and policy simulation to check policy errors, granted permissions, context, and guardrails.
4. Build a workflow to trace AccessDenied errors across IAM, S3, KMS, and STS AssumeRole, including **cross-account** setups.
5. Interpret **allowed**, **explicitDeny**, and **implicitDeny** outcomes and recognize when live-environment testing is required.
6. Propose fixes following **least privilege** instead of over-widening permissions just to make errors disappear.

## 2. Foundation: How Does AWS Decide Allow or Deny?

Every AWS API request has a context containing **principal** (who is calling), **action** (doing what), **resource** (on which target), and **condition** attributes (when, from where, via what path). A principal can be an IAM user, IAM role session, or service principal. ARNs identify resources and identities.

For example, an application uses role **ReportReader** to call **s3:GetObject** on **arn:aws:s3:::training-report-bucket/reports/november.csv**. AWS may evaluate:

| Control layer | Investigation question |
|---|---|
| **Identity-based policy** | Is the role/user allowed to perform **s3:GetObject** on the exact ARN? |
| **Resource-based policy** | Does the bucket, queue, key, or target resource have a policy allowing/denying the principal? |
| **Permissions boundary** | Is the role/user capped by a permission ceiling? |
| **Session policy** | Is the current STS session narrowed further? |
| **AWS Organizations SCP/RCP** | Is the account or resource subject to an organization-level guardrail? |
| **Service-specific controls** | Do S3 Block Public Access, object ownership, KMS key policy, VPC endpoint policy, or service-specific restrictions apply? |
| **Request context** | Do conditions such as tags, principal, TLS, IP, Region, or source ARN actually match? |

Three fundamental principles:

- **Implicit deny (default deny):** without a valid Allow, the request is denied.
- **Explicit allow:** a matching **Allow** statement can grant permission, subject to boundaries and resource-side requirements.
- **Explicit deny:** an applicable explicit **Deny** blocks the operation, even when Allow exists elsewhere.

Within the **same account**, permissions from identity-based and resource-based policies are typically combined via union, yet the outcome still depends on permissions boundaries, session policies, SCPs/RCPs, and whether the resource-based policy names an IAM user, role, or **role session**. For **cross-account** access, permissions must be checked in both **the principal's account** and **the resource-owning account**. Do not apply a single union/intersection formula across every principal type and service.

## 3. Choosing the Right Tool

| Tool | Primary question | Output | Limitations to remember |
|---|---|---|---|
| **IAM Access Analyzer — external access findings** | Which resources are accessible from principals outside the defined zone of trust? | Findings on unintended external access, per supported resource types | Not all services/resources are analyzed; findings reflect policies and analyzer scope, not proof that access occurred |
| **IAM Access Analyzer — unused access findings** | Which permissions, roles, or users show signs of being unused during the analysis window? | Findings for trimming excess permissions | Historical observation has limits; unused permissions might still be required for rare workflows |
| **IAM Access Analyzer — policy validation** | Does the JSON policy have syntax errors, warnings, suggestions, or known security issues? | Findings by severity: error, security warning, warning, suggestion depending on type | Static check; **does not confirm an API call will be Allowed** |
| **IAM Policy Simulator** | Given a simulated action, resource, and context, is the principal likely Allowed or Denied? | **allowed**, **explicitDeny**, **implicitDeny**, plus statement/context details where supported | Simulation does not reproduce all service controls or live runtime state |
| **AWS CloudTrail** | Which API calls occurred? Who called them, when, on which endpoint, and with what error? | Events for actual requests and related fields | Check which event categories are logged; **S3 object-level data events** usually require configuration |
| **STS get-caller-identity** | Which principal do the current credentials actually represent? | Account, UserId, ARN | Identifies the caller; **does not confirm permission to execute target actions** |

Effective order of use:

1. Use **Access Analyzer** to detect unintended sharing and validate policy structure before or after changes.
2. Use **Policy Simulator** to identify policies/conditions likely affecting a specific action.
3. Use **CloudTrail** and controlled test calls to verify real behavior, especially when cross-account or service-specific policies apply.

## 4. IAM Access Analyzer: Policy-Level Permission Analysis

IAM Access Analyzer offers features with distinct goals. Distinguish **access findings** produced by an active analyzer from **policy validation** run against JSON content; those two outputs are not equivalent.

### 4.1. External access findings: resources shared externally

When creating an analyzer, you define a **zone of trust**, typically an AWS account or AWS Organizations organization. Access Analyzer examines policies of **supported resource types** to detect access potentially granted to principals **outside** that trust boundary.

Example: an S3 bucket policy accidentally grants access to a partner account role outside the organization. The analyzer generates a finding so security teams can verify whether that sharing is intentional.

Workflow:

1. Select the right **Region**, account, and analyzer scope; certain analyzer types/findings have specific Region or service support requirements.
2. Inspect the principal, resource, actions, conditions, status, and basis of the finding.
3. Classify the sharing as **intentional and controlled** or **unintended**.
4. For unwanted access, update the resource policy/trust policy or related protective controls.
5. For approved exceptions, record justification, owner, and review schedule; manage findings/archive rules per organizational process.

**Note:** zero findings does not guarantee **all access is secure**. Analyzers have defined scopes, supported resource types, and reasoning models; findings about **potential reachability** also do not prove a principal actually read any data.

### 4.2. Unused access findings: reviewing unused permissions

Unused access analysis helps identify IAM users/roles or permissions that appear unused over a configured tracking window. This provides evidence for **tightening permissions**, reducing blast radius if credentials leak.

For example, a role is granted **s3:GetObject**, **s3:PutObject**, and **s3:DeleteObject**, yet recorded usage shows mainly read activity. Engineering must check whether delete actions belong to a rare periodic workflow before removing them.

Never automatically strip every permission flagged as unused without checking business needs, disaster recovery events, seasonal jobs, and observation data limits. Feature availability and pricing should be verified in your target account/Region.

### 4.3. Validate policy: catching issues before deployment

**Policy validation** inspects JSON content for issues such as syntax errors, unsupported elements, mismatched actions/resources, or risky policy patterns. Findings can be **ERROR**, **SECURITY_WARNING**, **WARNING**, or **SUGGESTION**, with locations and guidance when available.

Example syntactically valid identity-based policy allowing only reading objects under a prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReports",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::learning-reports-demo/reports/*"
    }
  ]
}
~~~

Suppose this content is saved in **identity-policy.json** in a test environment. Validation command:

~~~bash
aws accessanalyzer validate-policy \
  --policy-type IDENTITY_POLICY \
  --policy-document file://identity-policy.json
~~~

For a resource-based policy, choose **RESOURCE_POLICY** and supply any extra parameters required by the API for that resource type. Learners should read every finding to understand its meaning; a policy with **zero findings** may still lack **s3:GetObject** for the real ARN, specify the wrong principal, or be Denied by another policy.

**Policy validation is a static check, not a simulation of an API call.**

### 4.4. Generating policies from observed activity

IAM Access Analyzer can generate policy drafts based on activity recorded in **CloudTrail** for supported scopes. This helps operations teams start from observed usage to narrow overly broad policies.

However, policies generated from history are not guaranteed to include rarely used APIs or optimal conditions/resources. Learners must review required actions, ARNs, conditions, and administrative/recovery operations, then test before deploying to production.

## 5. IAM Policy Simulator: Simulating Allow/Deny Decisions

IAM Policy Simulator lets you supply a **principal or set of policies**, **actions**, **resources**, and optionally **context** to calculate expected outcomes. It provides a web UI and APIs such as **SimulatePrincipalPolicy** and **SimulateCustomPolicy**.

### 5.1. Simulate whether a role can read an S3 object

Suppose role **ReportReader** in account **111122223333** has the policy from section 4.3:

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportReader \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::learning-reports-demo/reports/november.csv \
  --query 'EvaluationResults[].[EvalActionName,EvalResourceName,EvalDecision,MissingContextValues]' \
  --output json
~~~

This is a **simulation** command; it does not read the object or alter live permissions. ARNs, accounts, and buckets are illustrative data; replace them with values from your authorized lab. To run successfully, the caller's credentials must also have permission to call the simulation API.

**EvalDecision** typically returns one of these values:

| Result | Meaning | Next check |
|---|---|---|
| **allowed** | Within the supplied model, simulated policies/context allow the request | Check resource policies, target service, live session, and boundaries not fully simulated |
| **implicitDeny** | No effective Allow found for the request within simulation scope | Check action, Resource ARN, principal, and missing context |
| **explicitDeny** | An explicit Deny applies in the evaluated policies | Inspect Deny statement, conditions, and protective intent before changing |

**MissingContextValues** reports context keys needed for the tool to accurately evaluate policy conditions. An **implicitDeny** result may stem from missing context, or from lacking any matching Allow.

### 5.2. Running multiple actions to pinpoint missing permissions

An SDK-based application might call **ListObjectsV2** before **GetObject**. These actions require different resources:

- **s3:GetObject** applies to an **object** ARN, e.g., **arn:aws:s3:::learning-reports-demo/reports/file.csv**.
- **s3:ListBucket** applies to a **bucket** ARN, e.g., **arn:aws:s3:::learning-reports-demo**.

If you simulate only **s3:GetObject**, an **allowed** result will not explain why the list step fails. You must simulate the exact action and ARN corresponding to the denied API:

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportReader \
  --action-names s3:ListBucket \
  --resource-arns arn:aws:s3:::learning-reports-demo
~~~

Once you identify the missing permission and confirm listing is required by business logic, design **s3:ListBucket** with an appropriate **s3:prefix** condition instead of granting **s3:***.

### 5.3. Simulating context: conditions can flip the outcome

A policy may restrict requests by source IP, principal tag, resource tag, MFA, or specialized context keys. If learners omit context, results will not represent real requests.

For example, an Allow takes effect only when **aws:PrincipalTag/team** equals **finance**. Simulating without supplying this tag may report missing context or a different decision than expected. Extract the relevant keys from the policy and supply accurate values, using the **GetContextKeysForPrincipalPolicy** API when helpful.

**Never fabricate convenient condition values** that differ from the real session. The goal is reproducing the actual request, not creating an artificial case that passes Allow more easily.

### 5.4. Simulator limitations

- Does not fully simulate all **resource-based policies**, **IAM role trust policies**, **SCPs/RCPs**, network controls, or service-specific rules. Support depends on principal type, policy, and API.
- Results reflect only **the policies, resources, and context actually supplied**. Policy changes after running a simulation invalidate prior results.
- **Allowed** does not prove the S3 bucket exists, the object is present, network connectivity works, KMS allows decryption, or production API calls will succeed.
- For cross-account access, policies on both caller and resource sides must be evaluated; simulating a single identity policy is insufficient.

Use the simulator to **narrow down the investigation**, then verify against resource policies and live requests.

## 6. CloudTrail and STS: Finding Evidence of Live Calls

### 6.1. Confirm the principal first

Using the wrong principal is a very common root cause. Local environments use one profile, EC2 uses an instance role, ECS uses a task role, Lambda uses an execution role, and CI/CD often uses short-lived STS sessions.

~~~bash
aws sts get-caller-identity
~~~

Example fictional output:

~~~json
{
  "UserId": "AROAXAMPLE:report-job-17",
  "Account": "111122223333",
  "Arn": "arn:aws:sts::111122223333:assumed-role/ReportReader/report-job-17"
}
~~~

This is an **assumed-role session ARN**, not the underlying role ARN **arn:aws:iam::111122223333:role/ReportReader**. When investigating, trace back to the base role to inspect its permissions policies, boundary, and trust policy; also inspect any session policies or session tags attached to the STS session.

If a learner inspects role **ReportReader** while the application actually runs under **DeploymentRole**, adding permissions to ReportReader will not fix the error.

### 6.2. Reading an AccessDenied event

In CloudTrail (Event history, trails, or CloudTrail Lake depending on scope), locate the event matching the timestamp and operation. Key fields to inspect:

| Common field | Information to extract |
|---|---|
| **eventTime**, **eventSource**, **eventName** | When, which service, and which API was called |
| **awsRegion** | Region/endpoint of the request, especially when troubleshooting Regional resources |
| **userIdentity** | IAM user, assumed-role session, or service principal |
| **recipientAccountId** | Receiving account ID when populated |
| **requestParameters**, **resources** | Bucket/key, role ARN, KMS key, or related resources when recorded |
| **errorCode**, **errorMessage** | Denial error code and description, if provided by the event |
| **sourceIPAddress**, **userAgent**, **additionalEventData** | Connection origin and extra context when available |

Messages from some services and same-account scenarios may name the policy type causing an **explicit deny** or state that **no identity-based policy allows** the action. However, **not every AccessDenied error provides detailed messages**; especially in cross-account, service-specific, or organization-policy flows, details may be omitted or redacted.

**Pay attention to event types:** Default CloudTrail Event history mainly provides **management events**. S3 object operations like **GetObject** are **data events**, which usually do not appear in Event history unless explicitly configured via a trail or CloudTrail Lake. Not seeing GetObject in Event history does not prove GetObject was never called.

### 6.3. Gathering evidence layer by layer

When encountering **AccessDenied**, gather evidence across layers:

1. Actual command/error with timestamp, action, account, Region, and ARN.
2. Live identity via **get-caller-identity**, plus session name/tags where relevant.
3. IAM policies attached to the user/role and any **permissions boundary/session policy**.
4. Resource policy, role trust policy, or KMS key policy on the target resource.
5. SCPs/RCPs, endpoint policies, and specialized controls if present.
6. Policy simulation results with the exact **context** used.
7. Corresponding CloudTrail events or application logs confirming the real request.

Prioritize concrete evidence to pinpoint **the exact denying link**, rather than blindly granting unlimited permissions to the role.

## 7. End-to-End AccessDenied Troubleshooting Workflow

~~~mermaid
flowchart TD
    A["Record AccessDenied\nAPI, timestamp, ARN, Region"] --> B["Identify actual principal\nSTS GetCallerIdentity"]
    B --> C["Verify action and resource ARN\nCorrect bucket/object/key/role format?"]
    C --> D{"Same-account\nor cross-account?"}
    D -->|"Same account"| E["Check IAM + resource policies\nand any explicit deny"]
    D -->|"Cross-account"| F["Check both sides\ncaller and resource owner"]
    E --> G["Check boundary/session\nSCP, RCP, and conditions"]
    F --> G
    G --> H["ValidatePolicy + Policy Simulator\nwithin supported scope"]
    H --> I["Cross-check CloudTrail\nand service-specific rules"]
    I --> J["Apply minimal permission fix\nonly after confirming root cause"]
    J --> K["Test actions that must Allow\nand actions that must Deny"]
~~~

### Step 1 — Capture full error context

Collect **API name**, **timestamp**, **principal**, **ARN**, **account**, **Region**, **request origin**, and **error code**. Example: app running as role **ReportReader** calling **s3:GetObject** on **arn:aws:s3:::learning-reports-demo/reports/november.csv** at a specific timestamp. Avoid vague notes like "S3 blocked access."

### Step 2 — Verify active credentials and session

Run **sts get-caller-identity** using the exact profile or runtime environment reporting the error. If the app runs on Lambda/ECS/EC2, inspect the workload's actual attached role. For **AssumeRole**, distinguish **caller role**, **target role**, **role session**, and session policy.

### Step 3 — Match action to ARN

Many errors come from granting the right action with the wrong Resource format:

- **s3:ListBucket** needs a bucket ARN; **s3:GetObject** needs an object ARN.
- **sts:AssumeRole** must match the target role ARN and trust policy.
- **kms:Decrypt** requires permission on the appropriate key; check the KMS key policy as well.
- Some actions only support **Resource: \*** in identity-based policies. Check the service authorization reference table before applying.

### Step 4 — Search for Denies and missing Allows

List all active identity-based policies, resource policies, boundaries/session policies, and organizational limits. For **implicit deny**, find the exact missing Allow in that context. For **explicit deny**, read **Condition** and protective rationale before editing; sometimes Denies are intentional security guardrails.

### Step 5 — Check the cross-account path

If the resource belongs to another account, identify the mechanism:

- **Direct access via resource-based policy:** caller side needs matching permissions and resource side must accept the principal (per service mechanics).
- **AssumeRole into target account:** caller must be allowed to assume, target role's trust policy must trust caller, and the **target role's** permissions must allow the final action.

Do not mistakenly edit policies in account A when the Deny actually resides in a bucket policy or key policy in account B.

### Step 6 — Use tools to test hypotheses

Run **ValidatePolicy** on the candidate policy; run **Policy Simulator** with the exact action, ARN, principal, and context. If the simulator returns **allowed** yet the live API still returns AccessDenied, focus on factors not fully simulated: resource policies, KMS, endpoint policies, SCPs/RCPs, session state, request conditions, or a different live principal.

### Step 7 — Apply the minimal fix and retest

Modify only the failing statement and scope permissions to **least privilege**. Test both actions **that must be allowed** and actions **that must be denied**; verify in CloudTrail or appropriate logs. Record root cause, policy change, owner, and post-fix verification results.

## 8. Real-World Scenario A: Lambda Reads S3 but Lacks ListBucket

**Context:** A Lambda uses execution role **DailyReportJob**. Its role policy has only:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::learning-reports-demo/reports/*"
    }
  ]
}
~~~

The app calls **ListObjectsV2** to find new reports before calling **GetObject**. The error occurs on the very first operation.

**Analysis:** **ListObjectsV2** checks the IAM permission **s3:ListBucket**, not **s3:GetObject**. The simulator might return **allowed** for GetObject yet **implicitDeny** for ListBucket on the bucket ARN.

If business logic genuinely needs to list the reports prefix, add this statement to the role's **identity-based policy**:

~~~json
{
  "Sid": "ListOnlyReportsPrefix",
  "Effect": "Allow",
  "Action": "s3:ListBucket",
  "Resource": "arn:aws:s3:::learning-reports-demo",
  "Condition": {
    "StringLike": {
      "s3:prefix": [
        "reports/",
        "reports/*"
      ]
    }
  }
}
~~~

This statement demonstrates restricting listing by prefix. Application code must pass a prefix matching the condition; also check any other boundaries if present. **Never grant s3:*** just to resolve listing.

## 9. Real-World Scenario B: Cross-Account S3 Access and KMS

Suppose:

- **Account A — 111122223333:** role **AnalyticsReader** runs the data-reading app.
- **Account B — 222233334444:** S3 bucket **shared-data-demo-222233334444** holds objects encrypted via SSE-KMS with a customer managed key.

For **direct S3 access using Account A's role**, you typically need:

1. **AnalyticsReader**'s identity-based policy in A allowing **s3:GetObject** on the object ARN in B.
2. B's bucket policy allowing the specific role in A to read those corresponding objects.
3. Because a customer managed KMS key is used, appropriate **kms:Decrypt** permission on the caller along with the **KMS key policy** in the key-owning account.
4. No Deny or extra control blocking the access path (SCP/RCP, endpoint policy, conditions, etc.).

**Step-by-step diagnosis:**

| Check | Clue | Fix direction |
|---|---|---|
| Role A's identity policy | Missing Allow s3:GetObject | Add minimal action and object ARN |
| Bucket policy in B | Does not accept role A | Fix Principal/Resource and conditions per approved sharing path |
| KMS key policy | S3 allows read yet decrypt is denied | Verify KMS key ARN, key policy, `kms:Decrypt` permission, and context |
| SCP/RCP/boundary/endpoint | Isolated simulator says Allow yet live API Denies | Inspect guardrail policies and request context |

If opting for **AssumeRole into Account B** instead of direct access, analyze from the target role session instead; avoid mixing the two patterns. Adjust bucket policies or key policies only with proper justification and administrative authority.

## 10. Real-World Scenario C: sts:AssumeRole Error

Suppose a pipeline in Account A wants to assume **DeploymentRole** in Account B. Check both sides:

- **Caller permissions:** the source principal's identity-based policy must normally allow **sts:AssumeRole** on the target role ARN.
- **Target trust policy:** **DeploymentRole**'s trust policy in B must allow the source principal to assume it, and any configured conditions such as **sts:ExternalId**, MFA, principal tags, or request origin must be satisfied.

Illustrative trust policy for a known role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustDeploymentCaller",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/CICDCaller"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

If the real caller is a different role, or the caller is blocked by an SCP, this configuration is insufficient. After **AssumeRole succeeds**, **DeploymentRole**'s permissions policy determines which services the pipeline can manipulate; the trust policy does not automatically grant **cloudformation:CreateStack**, **s3:PutObject**, or other deployment permissions.

### Example of misreading simulation results

An engineer simulates **s3:GetObject** on the **source role**, sees allowed, and concludes the post-AssumeRole deployment must be able to read the object. That conclusion is wrong because after AssumeRole the app uses **DeploymentRole's role session**, no longer carrying the source role's effective permissions. Always test the exact principal **active when the API call happens**.

## 11. Common Causes of AccessDenied

| Error / symptom | Possible cause | Priority tool or evidence |
|---|---|---|
| CLI call succeeds, Lambda fails | CLI and Lambda use different principals | **STS get-caller-identity**, execution role config, CloudTrail |
| **implicitDeny** on GetObject | Wrong action, object ARN, or missing Allow | Policy Simulator, identity policy |
| **explicitDeny** despite Allow | Deny in bucket, IAM, boundary, or org level | Error details, applicable policies, conditions |
| GetObject works, ListObjectsV2 denied | Missing **s3:ListBucket** on bucket ARN | Actual action, simulator, Service Authorization Reference |
| Cross-account S3 read fails | Missing permission on one side or mismatched condition | IAM role policy in A, bucket policy in B |
| Reading SSE-KMS object gets AccessDenied | Missing KMS permission or key policy lacks grant | KMS key policy, IAM policy, key ARN |
| AssumeRole denied | Trust policy, caller permission, or condition incorrect | CloudTrail STS, role trust policy, SCP |
| Simulator says **allowed**, live API Denies | Overlooked resource policy, session/context, SCP/RCP, or service rules | CloudTrail, request context, end-to-end check |
| Access Analyzer shows no findings despite unintended reads | Analyzer doesn't cover all access paths, resource types, or history | Check analyzer scope; CloudTrail/data events, live logs |
| Error appears after changing tags or network path | Condition key no longer matches | Session/principal/resource tags, SourceIp, VPC endpoint, logs |
| S3 bucket allows yet anonymous/public access stays blocked | S3 Block Public Access and service configuration | S3 Block Public Access, bucket policy, and ownership |
| Message omits which policy caused Deny | Service/scenario does not return details | Gather all policy layers, use simulator and test calls |

## 12. Practices to Avoid

**Never add broad permissions like Action: "*" or Resource: "*" just to silence errors.** It may make a test call pass while opening unauthorized access paths.

**Never remove an explicit deny without understanding its purpose.** Denies often protect sensitive data, enforce TLS, restrict Regions, or block destructive operations.

**Never equate "valid policy" with "sufficient permissions."** IAM Access Analyzer policy validation does not know all of your application's requirements.

**Never treat "simulator: allowed" as final proof.** Policy Simulator does not capture live resources, sessions, and every service policy at live call time.

**Never conclude "no CloudTrail logs" means no access occurred.** Verify the required event types, Region, account, log retention, and data logging settings.

**Never edit policies on an identity that isn't actually calling the API.** Confirm the principal and credentials before changing any permissions.

**Never modify production policies based solely on one simulation.** Test in an appropriate environment, document impact, and follow approval workflows.

## 13. Practice Exercise: Analyze an Error and Propose a Minimal Fix

**Prompt:** a reporting job running under role **ReportReader** in Account A needs to:

- List objects under prefix **reports/** of bucket **learning-reports-demo**.
- Read CSV files under that prefix.
- Not write, edit, delete, or read other prefixes.

The active policy contains only **s3:GetObject** on objects prefixed **reports/** in the bucket. After running the job, learners hit an **AccessDenied** error on the listing operation.

### Tasks

1. Identify the real IAM action for the **ListObjectsV2** API and the required resource ARN.
2. Use the simulator to predict that GetObject is allowed while ListBucket gets implicit deny, assuming no other policies apply.
3. Add an **s3:ListBucket** statement with an appropriate prefix condition.
4. Use **ValidatePolicy** to verify the complete JSON, then test a ListObjectsV2 request with prefix **reports/**.
5. Verify that **s3:DeleteObject** or accessing another prefix remains denied.
6. Document assumptions not covered by the simulator, such as bucket policies, SCPs, and other guardrails.

**Expected outcome:** distinguish **missing Allow on a specific action** from **explicit deny**, grant scoped listing permissions without widening read/write access, and describe how to validate via live calls.

### Extension question

Suppose a bucket policy also **Denies** all non-TLS connections (**aws:SecureTransport = false**). Why does an HTTP request still fail even after adding ListBucket?

**Hint:** a matching explicit deny overrides Allow; learners must fix the connection transport and verify request context, rather than removing a Deny protecting data.

## 14. Troubleshooting Checklist Before Closing an Incident

- [ ] Recorded **timestamp**, **API/action**, **Region**, **resource ARN**, and error message.
- [ ] Confirmed actual principal, including **assumed-role session**.
- [ ] Identified same-account vs. cross-account, direct access vs. AssumeRole.
- [ ] Reviewed Allow/Deny in identity policies, resource policies, and trust policies where applicable.
- [ ] Checked permissions boundaries, session policies, SCPs/RCPs, and critical conditions.
- [ ] Considered KMS, S3 Block Public Access, endpoint policies, and service-specific requirements.
- [ ] Validated JSON and simulated exact actions, ARNs, and principal/context within supported scope.
- [ ] Cross-checked CloudTrail or live logs, verifying which event types are collected.
- [ ] Applied a root-cause fix following **least privilege** without over-widening permissions.
- [ ] Retested actions that must be allowed, actions that must be denied, and documented results.

## 15. Key Takeaways

**IAM Access Analyzer** detects access outside trust boundaries, potentially unused permissions, and policy issues prior to deployment. **Policy Simulator** answers "given this action, resource, and context, what is the policy expected to decide?". **CloudTrail** provides evidence of recorded live API calls. When troubleshooting **AccessDenied**, the most effective sequence is **confirm actual principal → verify exact action/resource → check Allow/Deny and guardrails → simulate/cross-check logs → apply minimal fix and retest**.

### Official AWS Documentation for Reference During Implementation

- [AWS IAM Access Analyzer — User Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html) — analyzer scope and core capabilities.
- [Validate your IAM policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) — finding types during policy validation.
- [IAM Policy Simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html) — how simulation works and its limits.
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — Allow, Deny, and boundary layer rules.
- [Troubleshoot access denied error messages](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html) — interpreting access denied errors.
- [Cross-account policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic-cross-account.html) — evaluating permissions across two accounts.
- [CloudTrail concepts](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-concepts.html) — management/data events and API events.
- [Actions, resources, and condition keys for AWS services](https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html) — looking up appropriate actions and Resource ARNs.
