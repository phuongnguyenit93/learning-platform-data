# Service Control Policies and Organization-Wide Permission Boundaries

## 1. Context and Learning Objectives

When an organization has only a single AWS account, administrators can manage most access through AWS Identity and Access Management (IAM). However, as the organization grows to multiple accounts for development, testing, production, security, and billing, configuring the same safety rules inside each account easily leads to inconsistent setups. **AWS Organizations** solves this centralized governance challenge; **Service Control Policies (SCPs)** are one of the key tools for establishing permission boundaries across an organization.

This lesson is part of the **CLOUD_PROVIDERS_AWS** track. Knowledge of SCPs connects directly to AWS topics such as Regions/Availability Zones, IAM, VPC, compute services, storage, databases, serverless, monitoring, recovery, and cost control. When selecting or deploying services, engineering teams need to understand not only what permissions an IAM role *is granted*, but also what maximum permissions the organization *allows that role to use*.

After this lesson, you will be able to:

- Explain what an SCP does, how it differs from an IAM policy, and why an SCP does not grant permissions on its own.
- Determine the scope of an SCP across the Root, Organizational Units (OUs), and member accounts.
- Analyze the outcome of `Allow`/`Deny` rules when multiple SCPs take effect together.
- Write and read JSON SCPs to protect sensitive operations or restrict Regions.
- Establish a workflow for testing, deploying, monitoring, and recovering when an SCP mistakenly blocks a legitimate operation.

## 2. What Is an SCP?

A **Service Control Policy** is a type of *organization policy* in AWS Organizations. An SCP defines the **maximum bounds of usable permissions** for principals governed by the SCP inside member accounts. SCPs are attached to the **Organizations Root**, an **OU**, or a **member account**, and take effect through the hierarchical structure.

Core point: **an `Allow` statement in an SCP does not grant permission to execute an API**. A principal still needs permissions granted through an appropriate AWS authorization mechanism, such as an IAM identity-based policy. Conversely, a `Deny` in an SCP can block an operation that an IAM policy has allowed, even when the principal has `AdministratorAccess` in the member account.

Example: the `DeploymentRole` role has an IAM policy allowing `ec2:RunInstances`. If an effective SCP on the account containing that role denies `ec2:RunInstances`, the role still cannot launch EC2 instances. Attaching another IAM policy with `Allow ec2:*` does not override the SCP.

### 2.1. What Problems Does an SCP Solve?

| Governance Need | Potential Role of an SCP | Additional Controls to Consider |
| --- | --- | --- |
| Prevent member accounts from leaving the organization | Deny `organizations:LeaveOrganization` | Organizations governance processes and management account permissions |
| Reduce risk of CloudTrail logging being stopped | Deny `cloudtrail:StopLogging`, `cloudtrail:DeleteTrail` | CloudTrail, monitoring configuration, and log storage protection |
| Restrict where workloads can be deployed | Deny specific service actions in unapproved Regions | Region strategy, data, global services, real-world testing |
| Prevent a group of accounts from using unapproved services | Design `Deny` boundaries or `Allow` lists | IAM, exception-granting process, cost controls |

SCPs are **access permission guardrails**, not a substitute for operational monitoring, data protection, or hard spending limits. Blocking a resource-creation API call does not stop already-running resources from incurring charges; budget management still requires AWS Budgets, alerts, and operational processes.

## 3. Scope of Application: Root, OUs, and Accounts

Suppose an AWS organization is structured as follows:

```text
Organizations Root
├── OU: Security
│   └── Account: security-audit
└── OU: Workloads
    ├── OU: Development
    │   └── Account: dev-app
    └── OU: Production
        ├── Account: prod-app
        └── Account: prod-data
```

- An SCP attached to the **Organizations Root** affects member accounts beneath the organization tree.
- An SCP attached to **OU Workloads** affects accounts under this OU and its child OUs, but does not affect accounts under OU Security.
- An SCP attached to **OU Production** affects `prod-app` and `prod-data`, and does not affect `dev-app`.
- An SCP attached directly to **Account prod-app** affects only that account.

Each member account is governed by the **entire chain from Root → parent OUs → account**. Moving an account to a different OU can change its effective permission boundaries even if IAM policies inside the account remain unchanged.

> **Distinguish two types of "root":** *Organizations Root* is the top node of the Organizations governance tree. *Root user* is the root identity of an individual AWS account. These are two different concepts.

### 3.1. Who SCPs Do and Do Not Apply To

SCPs apply to principals such as IAM users, IAM roles, and the **root user of a member account**. SCP limits also apply to an IAM role inside a member account when that role is assumed from elsewhere.

Key exceptions and limitations to remember:

1. **SCPs do not restrict principals in the management account** of Organizations. Therefore, you must protect the management account with separate IAM and security controls; you cannot rely on SCPs to lock down permissions of the management account itself.
2. **SCPs do not apply to service-linked roles**. These are roles created and managed by an AWS service for integration with that service.
3. SCPs restrict **principals belonging to member accounts**, not all access to all resources in the account. For cross-account access, you must also evaluate resource-based policies, trust policies, and the location of the calling principal; an SCP on the resource-owning account does not replace those controls.
4. SCPs do not create or modify IAM users, IAM roles, permission boundaries, or resource policies. Those mechanisms continue to serve independent roles.

To use SCPs, AWS Organizations must have **All features** enabled and the **Service control policies** policy type activated. The management account must have permissions to perform the corresponding Organizations administrative actions.

## 4. How Does AWS Evaluate Permissions with SCPs?

For a principal in a member account, picture an SCP as the **outer boundary** of permissions the principal can receive. IAM policies and related policies determine which actions are granted; SCPs bound those actions. **An explicit `Deny` takes precedence over `Allow`.** Conditions such as permission boundaries, session policies, and resource policies can also influence the final outcome.

| Permissions from IAM and Related Mechanisms | Effective SCP | Illustrative Outcome |
| --- | --- | --- |
| Allows `ec2:RunInstances` | Allows and no relevant `Deny` | May be allowed, provided other conditions are also satisfied |
| Allows `ec2:RunInstances` | Has `Deny` for `ec2:RunInstances` | **Denied** |
| No permission for `ec2:RunInstances` | Has `Allow` in SCP | **Denied** because SCP does not grant permissions |
| Principal has `AdministratorAccess` | SCP denies `cloudtrail:StopLogging` | **Denied** for that operation |

For allow-list style policies (*allow-list*), an action must be allowed **at every level along the path** from Organizations Root through OUs down to the account. Even a single level missing a matching `Allow` causes the action to fall outside the allowed boundary, even when IAM has `Allow`.

### 4.1. Two Common Models: Deny-List and Allow-List

The **deny-list model** is usually easier to roll out when first adopting SCPs:

- Keep the `FullAWSAccess` policy attached at the required nodes so the default permission scope is not narrowed.
- Attach additional SCPs containing `Deny` statements for prohibited actions.
- Any `Deny` at the Root, OU, or account level blocks the corresponding action in affected accounts.

`FullAWSAccess` is the default AWS-managed SCP that allows all actions *at the SCP layer*. It does **not** grant IAM permissions and does **not** override an explicit `Deny` in another SCP.

The **allow-list model** uses selective `Allow` SCPs to narrow the set of usable APIs:

- You must ensure an appropriate `Allow` exists **at every level** Root → OU → account.
- If `FullAWSAccess` remains attached at a level you intend to restrict via allow-list, that policy will continue allowing many actions at that level; you must redesign the SCPs directly attached to the relevant node.
- You must evaluate supporting actions that applications or services routinely call, such as `Describe*` calls, IAM operations, or logging actions. An overly narrow allow-list can break workloads.

Conceptual example: Root allows only `ec2:*`, OU allows only `ec2:Describe*`, and the account allows `*`; with no other `Allow` statements, the effective boundary at the SCP layer is only `ec2:Describe*` operations. Even then, an IAM policy must still grant specific permissions before a principal can execute the action.

## 5. Example 1: Protecting Logging and Organization Membership

An organization wants application accounts to be unable to leave AWS Organizations on their own, and unable to stop logging or delete CloudTrail trails. The following JSON SCP expresses both rules:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyLeavingOrganization",
      "Effect": "Deny",
      "Action": "organizations:LeaveOrganization",
      "Resource": "*"
    },
    {
      "Sid": "DenyDisablingCloudTrail",
      "Effect": "Deny",
      "Action": [
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail"
      ],
      "Resource": "*"
    }
  ]
}
```

Breakdown of each part:

- `Version` is the AWS JSON policy language version; `2012-10-17` is the standard value.
- `Statement` contains one or more rules. `Sid` helps operators identify each rule's purpose.
- `Effect: Deny` establishes an explicit denial for the actions listed in `Action`.
- `Resource: "*"` indicates the rule applies across all resources applicable to the action; some organization-level APIs do not have specific resources expressible by ARN.

If this policy is attached to OU Workloads, it affects `dev-app`, `prod-app`, and `prod-data` in the diagram, while not affecting `security-audit` in the other OU. An IAM administrator in the production account is still blocked from performing both categories of actions.

**Limitations of this example:** The policy only blocks the listed APIs. It does not cover every way monitoring could be weakened, such as changing the log destination, altering other logging settings, or modifying access to the log storage bucket. IAM permissions, CloudTrail configuration, and change monitoring must be designed alongside it.

## 6. Example 2: Restricting Regions for EC2

Suppose the organization approves EC2 workloads only in Singapore (`ap-southeast-1`) and Sydney (`ap-southeast-2`). The following SCP blocks EC2 actions when API requests are sent to other Regions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyEC2OutsideApprovedRegions",
      "Effect": "Deny",
      "Action": "ec2:*",
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": [
            "ap-southeast-1",
            "ap-southeast-2"
          ]
        }
      }
    }
  ]
}
```

`aws:RequestedRegion` checks the Region of the **API endpoint receiving the request**. In this example, EC2 actions outside the two specified Regions receive `Deny`; inside the two approved Regions, this SCP does not block them, though IAM and other boundaries still determine actual permissions.

**Do not copy this Region condition verbatim and apply it to `Action: "*"` without careful evaluation.** Many services have global APIs or cross-Region behavior; some operations target an endpoint in one Region while affecting resources in another Region. The `aws:RequestedRegion` condition is not an absolute guarantee of where all data is stored. When designing organization-wide policies, identify which services to target, required exceptions, and test in a non-critical account.

## 7. Permission Analysis Example in a Multi-OU Organization

Consider the following SCPs, assuming `FullAWSAccess` remains attached at every level:

| SCP Attachment Point | Rule |
| --- | --- |
| Organizations Root | `Deny organizations:LeaveOrganization` |
| OU Workloads | `Deny cloudtrail:StopLogging` |
| OU Production | `Deny ec2:*` if Region is not Singapore/Sydney |
| Account prod-app | No additional `Deny` |

An `AppAdmin` role in `prod-app` with an IAM policy allowing `ec2:*` and `cloudtrail:*` produces these outcomes:

| Request | Result | Explanation |
| --- | --- | --- |
| Launch an EC2 instance in `ap-southeast-1` | May be allowed | Not blocked by the SCPs above; still requires sufficient permissions and other conditions |
| Launch an EC2 instance in `eu-west-1` | Denied | SCP inherited from OU Production |
| Call `cloudtrail:StopLogging` | Denied | SCP inherited from OU Workloads |
| Call `organizations:LeaveOrganization` | Denied | SCP inherited from Organizations Root |

If `prod-app` is moved from OU Production to OU Development, the Region restriction attached specifically to OU Production no longer applies via the old OU branch. The two rules at Root and Workloads remain in effect because the account is still under that branch. This is why **moving an account** must be treated as a security control change.

## 8. Safe SCP Deployment Workflow

### Step 1 — Define Actions and Scope

Translate business requirements into specific API lists. For example, "prevent disabling CloudTrail" should be decomposed into relevant actions, then checked for other configuration-change paths that could undermine the goal. Choose the attachment target: Root if every member account needs the constraint; OU if only a subset does; or an account if testing.

Verify that Organizations is in **All features** mode and SCPs are enabled. Document existing SCPs attached at Root, OUs, and accounts, especially `FullAWSAccess` and existing `Deny` rules.

### Step 2 — Author the Policy and Review Impact

Evaluate the policy from the perspectives of console users, applications, CI/CD pipelines, operational roles, and automation. A high-level workflow often invokes multiple supporting APIs. Cross-reference required actions against existing `Deny` or `Allow` rules before attaching the policy.

Pay special attention to Region-sensitive services, cross-account operations, service-linked roles, and incident recovery requirements. Ensure a safe management-account administrative path exists to adjust or detach the SCP if it blocks legitimate traffic by mistake.

### Step 3 — Test on a Non-Critical OU or Account

In the AWS Management Console, go to **AWS Organizations → Policies → Service control policies**, create the policy, and attach it to the appropriate target. If the policy type is not yet enabled, complete the enablement step first.

With the AWS CLI, for example save the JSON from section 5 to `scp-guardrails.json` and create the policy:

```bash
aws organizations create-policy --name GuardrailsBase --description "Protect CloudTrail and organization membership" --type SERVICE_CONTROL_POLICY --content file://scp-guardrails.json
```

The command returns a real `PolicyId`. After confirming the correct ID and test OU, attach the policy:

```bash
aws organizations attach-policy --policy-id p-EXAMPLE --target-id ou-EXAMPLE-EXAMPLE
aws organizations list-policies-for-target --target-id ou-EXAMPLE-EXAMPLE --filter SERVICE_CONTROL_POLICY
```

`p-EXAMPLE` and `ou-EXAMPLE-EXAMPLE` are placeholders for illustration and must be replaced with real IDs. `list-policies-for-target` lists policies **directly attached** to the target; to inspect inherited SCPs, trace up through parent OUs and the Organizations Root.

In the test environment, execute both actions **expected to be allowed** and actions **expected to be denied** using real roles. Inspect `AccessDenied` error messages, CloudTrail logs, and CI/CD role execution paths. Only expand to production OUs once verified, following your organization's change-management process.

### Step 4 — Monitor, Operate, and Recover

Monitor governance changes such as `CreatePolicy`, `UpdatePolicy`, `AttachPolicy`, and `DetachPolicy` via CloudTrail and configuration review workflows. Record JSON versions, change rationale, approvers, and rollback plans.

If an SCP is found to mistakenly block a critical task, authorized personnel in the management account can edit or detach the policy at the appropriate target. Inspect the full Root → OU → account path before making edits: the denial may originate from an inherited SCP at a higher level rather than on the account reporting the error.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Attaching an SCP with `Allow s3:*` grants S3 permissions to staff." | An SCP only places that permission within the maximum allowed boundary; the principal still needs IAM permissions or an appropriate granting mechanism. |
| "AdministratorAccess or a member account's root user bypasses SCPs." | An SCP `Deny` still applies to these principals. Key exceptions are principals in the management account and service-linked roles. |
| "Having FullAWSAccess means every command can run." | FullAWSAccess does not grant IAM permissions on its own and does not override an explicit `Deny`. |
| "An SCP only applies if attached directly to the account." | Accounts also inherit SCPs from parent OUs and the Organizations Root. |
| "Blocking EC2 creation in other Regions guarantees all data stays in approved Regions." | `aws:RequestedRegion` checks the request endpoint; you must evaluate service behavior, data flows, and cross-Region features. |
| "SCPs are a tool for setting AWS spending limits." | SCPs restrict API actions; ongoing charges and running resources require dedicated cost management tools. |
| "An SCP at the Organizations Root locks down the management account too." | SCPs do not restrict principals in the management account; that account must be secured independently. |

## 10. Applied Scenarios and Self-Check

**Scenario A — Production pipeline hits AccessDenied.** The pipeline uses role `DeployProd` with IAM `AdministratorAccess`, yet launching an EC2 instance in `eu-west-1` fails. The account belongs to OU Production with the SCP from section 6. The most likely cause is `DenyEC2OutsideApprovedRegions`, because an IAM `Allow` cannot override the OU boundary. The right response is to check the workload's intended Region and request a guardrail adjustment through governance channels, rather than adding more IAM `Allow` statements.

**Scenario B — An engineer can view S3 bucket details but cannot download objects.** The SCP allows S3-related actions and has no matching `Deny`. This **does not prove** the engineer is permitted to call `s3:GetObject`: you must check IAM policies, bucket policies, KMS permissions (if objects are encrypted), access conditions, and other constraints.

**Scenario C — The Security team proposes attaching an SCP blocking all operations outside a single Region.** Before applying it across the entire Root, the team must inventory services with global endpoints, cross-Region actions, core infrastructure services, and recovery plans. An overly broad Region policy can unexpectedly break IAM, deployment systems, or monitoring tools. Testing on a narrow scope and scoping actions per service is a safer approach.

## 11. Key Takeaways

SCPs enable AWS Organizations to enforce **centralized permission boundaries** across member accounts. Permission to execute an API can exist only when an appropriate granting mechanism allows it **and** effective SCPs do not exclude it. To design AWS infrastructure that is secure, observable, recoverable, and cost-controlled, combine SCPs with IAM, sound account/OU separation, CloudTrail, resource-level protections, deployment testing, and change governance.

### AWS Reference Documentation

- [Service control policies — AWS Organizations User Guide](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [Service control policy examples — AWS Organizations User Guide](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_examples.html)
- [Policy evaluation logic — IAM User Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
