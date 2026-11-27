# AWS Organizations, Organizational Units, and Member Accounts

## Learning Objectives

After this lesson, you will be able to:

- Explain why a long-term growing AWS environment typically requires multiple accounts instead of putting every environment into one account.
- Distinguish between **AWS Organization**, **organization root**, **organizational unit (OU)**, **management account**, and **member account**.
- Design an OU tree suited to groups of accounts with different security and operational requirements.
- Explain policy inheritance in Organizations, especially the relationship between **service control policies (SCPs)** and **IAM** permissions.
- Describe the process of adding accounts, moving accounts between OUs, and managing costs centrally.

## 1. Why Do We Need AWS Organizations?

Suppose a company operates an e-commerce application on AWS. Initially, the team uses a single AWS account containing development, testing, and production environments. As scale grows, this setup causes several problems:

1. **Large blast radius:** a misconfiguration or compromised account can affect multiple environments inside the same account.
2. **Difficult permission scoping:** developers need permissions to experiment in dev but should not have the same permissions in production.
3. **Difficult cost control:** costs across teams, products, and environments get mixed together, even though tags can still be used for allocation.
4. **Difficult operational standardization:** each account needs to enforce baseline rules such as logging, data protection, and restricting dangerous operations.
5. **Resource limits:** many AWS quotas are managed per account and per Region; separating accounts helps manage each workload more clearly, though it does not eliminate all limits.

**AWS Organizations** solves the problem of governing **multiple AWS accounts** from a single central organization. It provides an account grouping hierarchy, organization-level policy management, integration with certain AWS services, and consolidated billing. Organizations does not automatically create a shared network, does not automatically grant IAM permissions to users, and does not automatically deploy applications.

This is the foundation of the **multi-account** approach, which is very useful when studying upcoming topics such as IAM, VPC, compute services, storage, monitoring, and cost control.

## 2. Components of an Organization

| Component | Meaning | Key Point to Remember |
| --- | --- | --- |
| **Organization** | A collection of AWS accounts managed together. | One Organization has a single hierarchical tree. |
| **Organization root** | The top-level node of the tree; created when the Organization is created. | Completely different from the **root user** of an AWS account. |
| **Management account** | The account that manages Organizations and is responsible for consolidated billing. | Avoid running regular workloads here. |
| **Member account** | An account belonging to the Organization, used to host workloads, data, and AWS resources. | Still maintains its own identity, permission, resource, and many quota boundaries. |
| **Organizational unit (OU)** | A group of accounts or child OUs sharing common governance needs. | OUs help apply shared policies; an OU is not an AWS account. |
| **Organization policy** | A policy applied at the root, OU, or account level depending on policy type. | Each policy type has its own evaluation mechanism and scope of impact. |

An Organization has exactly **one management account** and **one root**, and can have many member accounts and OUs. Each account resides directly under **one** parent in the tree: either the root or an OU. An OU can contain child OUs, up to **five levels of OUs** beneath the root.

### Example Organization Tree

```text
Organization: ExampleCommerce
│
└── Root (r-xxxx)
    ├── Management account (billing + organization governance)
    ├── OU: Security
    │   ├── Account: LogArchive
    │   └── Account: SecurityTooling
    ├── OU: Infrastructure
    │   └── Account: SharedNetworking
    ├── OU: Workloads
    │   ├── OU: Production
    │   │   ├── Account: StorefrontProd
    │   │   └── Account: PaymentsProd
    │   └── OU: NonProduction
    │       ├── Account: StorefrontDev
    │       └── Account: StorefrontTest
    └── OU: Sandbox
        └── Account: Experiment
```

In the example above:

- **Management account** is used for organization governance and billing, not as the place to host all of the company's EC2, RDS, or VPC resources.
- **Security OU** centralizes accounts dedicated to logging and security tooling to reduce dependency on application-hosting accounts.
- **Production OU** can receive stricter policies than **NonProduction OU**.
- **Sandbox OU** can restrict services or operations that are not allowed in experimental environments.

The OU and account names are illustrative only. In real-world design, prioritize grouping by **control level and function** (security, infrastructure, production, sandbox) rather than copying an org chart verbatim. An OU does not create a private network or a separate IAM system; those boundaries primarily reside in accounts and the services configured within them.

### Distinguishing `root`, `root user`, and `management account`

Three concepts that are easily confused:

- **Organization root:** an object in AWS Organizations serving as the root node of the OU/account tree and a place where organization-level policies can be attached.
- **Root user:** the highest-privileged identity of **an AWS account**, tied to the account's registration email; not an OU or tree-management object.
- **Management account:** the AWS account that creates/manages the Organization and pays the bill, which has its own root user.

Do not sign in as the root user for daily work. Use properly authorized administrative access mechanisms, preferring IAM Identity Center and MFA.

## 3. How Do the Management Account and Member Accounts Differ?

| Aspect | Management Account | Member Account |
| --- | --- | --- |
| Primary role | Governing organization structure, features, and centralized billing. | Running applications, storing data, networking, databases, or shared services. |
| Billing | Responsible for paying member account charges via consolidated billing. | Incurs costs from the resources used by that account. |
| SCPs | **Not restricted by SCPs** when principals belonging to the management account perform actions. | IAM principals and the root user of member accounts are subject to applicable SCPs, including member accounts designated as delegated administrators. |
| Resources | Can host AWS resources, but should be minimized to reduce risk. | Has its own resource, permission, and configuration boundaries. |
| Access management | Can perform Organizations operations if the identity has the required permissions. | Has its own IAM and can allow access from other accounts via cross-account roles. |

**Key point:** two accounts being in the same Organization **does not automatically allow** users in one account to access resources in the other. Cross-account access requires explicit permission configuration, such as an IAM role with a trust policy and `sts:AssumeRole` permissions, or a service-specific equivalent.

To manage human sign-in access across multiple accounts, you can integrate **AWS IAM Identity Center** with Organizations and assign permission sets to accounts. Organizations manages account structure; IAM/IAM Identity Center manages granting appropriate access.

## 4. Two Feature Sets of AWS Organizations

| Mode | What's Included? | When to Use? |
| --- | --- | --- |
| **Consolidated billing features** | Consolidates billing and cost tracking across accounts. | When you only need unified invoicing. |
| **All features** | Includes consolidated billing plus extended governance capabilities such as organization policies and supported service integrations. | The right choice for most multi-account models requiring centralized security and governance. |

When creating an Organization today, **All features** is the default. You can upgrade from consolidated billing to all features, but you cannot revert back once all features are enabled. For invited accounts, enabling all features for an organization currently in billing-only mode may require confirmation per the AWS workflow.

For example, an enterprise that only wants to combine bills without needing SCPs can start with consolidated billing. When it needs to enforce policies blocking risky actions on the Production OU, the organization must support all features and enable the corresponding policy type.

## 5. Organizing Accounts into OUs

### What Are OUs Used For?

OUs help **group accounts that need a shared set of controls**. When you attach a policy type that supports inheritance to an OU, the accounts in that OU and its child OUs inherit the policy's effects according to each policy type's rules.

For example, all accounts under `Workloads/Production` must be protected against disabling CloudTrail. We attach an SCP restricting that action to `Production`. Both `StorefrontProd` and `PaymentsProd` are subject to this restriction. The `StorefrontDev` account under `NonProduction` will not receive the `Production`-specific SCP.

### What Happens When an Account Moves Between OUs?

When moving `StorefrontDev` from `NonProduction` to `Production`, the effective policies inherited from the old branch are replaced by the policies inherited from the new branch (while policies attached directly to the account still apply according to policy type). Moving an OU **does not automatically move** EC2 instances, VPCs, S3 buckets, or data to another account; the account remains the same account.

Because new policies can block operations that were previously working normally, evaluate the impact on CI/CD pipelines, operational services, IAM roles, and access permissions before moving an account, especially into a production OU.

### OU Tree Design Rules

1. Place broad guardrails at the root level, but only when certain of the scope and policy type.
2. Use OUs to reflect **differences in control requirements**: production and sandbox rarely share the same policies.
3. Keep the structure understandable; avoid deep nesting just because there are many departments.
4. Separate log collection and security tooling accounts from accounts running critical workloads.
5. Evaluate policy changes on a test OU before expanding the scope.

## 6. Organization Policies and Effective Permissions

### 6.1. An SCP Is a "Maximum Permission Boundary," Not a Granted Permission

A **Service Control Policy (SCP)** sets an **upper bound** on the permissions that IAM principals in member accounts can use. SCPs can be attached to the root, an OU, or a member account, and are evaluated along the entire path from root down to the account.

If an action is explicitly **Denied** by an SCP at any level in the path, principals in the member account cannot perform that action, even if IAM attaches `AdministratorAccess`. For an action to be allowed by SCPs, it must be within the `Allow` scope at every level; an explicit `Deny` always wins. AWS typically attaches the `FullAWSAccess` managed SCP so permissions are not immediately restricted when SCPs are enabled; removing it without a replacement Allow policy can unintentionally lock out many operations.

**An SCP does not grant IAM permissions.** If an IAM role does not have `s3:ListBucket`, the fact that an SCP does not forbid that action does not grant the role permission. Effective permissions are also influenced by other mechanisms such as resource policies, permission boundaries, session policies, and applicable access conditions.

| Scenario | IAM Allows? | SCP Allows? | IAM/SCP Result |
| --- | --- | --- | --- |
| Role has `s3:ListBucket`, no blocking SCP. | Yes | Yes | May be allowed, provided other relevant controls also allow it. |
| Role has `s3:DeleteBucket`, Production OU SCP denies it. | Yes | No | **Denied.** |
| Role lacks `ec2:TerminateInstances`, SCP is `FullAWSAccess`. | No | Yes | **Denied** because IAM does not grant the permission. |

SCPs **do not apply** to IAM principals in the management account and do not restrict service-linked roles. When protecting resources, do not treat SCPs as the sole safeguard; you must still configure IAM, logging, resource policies, and appropriate service-level controls.

### 6.2. Example SCP Protecting Logging Operations

Suppose `Production` requires that principals in member accounts cannot arbitrarily stop logging or delete AWS CloudTrail trails. An illustrative SCP:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyStoppingOrDeletingCloudTrail",
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

This is an **example for understanding the mechanism**, not a complete CloudTrail policy set for production. Other configuration-changing operations still need to be reviewed, along with change-management and emergency recovery procedures. When testing `Deny` policies on an OU, maintain the required `Allow` policies at all levels and test the impact in a non-production environment.

### 6.3. Other Policy Types

AWS Organizations also supports other policy types depending on enabled features and policy types, for example:

- **Resource control policy (RCP):** restricts access to resources owned by member accounts for supported services/resources; takes a resource-centric perspective, unlike principal-centric SCPs.
- **Tag policy:** standardizes tagging conventions and can help enforce tag rules in AWS-supported scenarios.
- **Backup policy:** manages backup plans across multiple accounts through AWS Backup integration.
- **Other centralized configuration policies:** have their own application and inheritance rules depending on each AWS service.

**Do not assume** every policy behaves like an SCP. For instance, declarative policies have their own merging rules and scopes; some may also affect the management account, whereas SCPs do not.

## 7. Adding and Managing Member Accounts

There are two main ways to bring an account into an Organization:

| Method | How It Works | Things to Note |
| --- | --- | --- |
| **Create account** | The management account creates a new AWS account directly inside the Organization. | The new account is initially placed under root; AWS Organizations usually creates a cross-account admin IAM role named `OrganizationAccountAccessRole` by default, unless another name is specified. |
| **Invite account** | Sends an invitation to an existing AWS account; the account owner accepts to join. | Organizations **does not automatically create** `OrganizationAccountAccessRole` in invited accounts. Cross-account administrative access must be configured separately if needed. |

In both cases, the member account inherits policies corresponding to its position in the tree upon joining. Accounts retain their separate IDs, resources, and settings. For accounts **newly created** via Organizations, AWS provides centralized root access management; do not assume a new account comes with ready-to-use root credentials for daily use.

Example workflow for adding a test environment:

1. From the management account, create `StorefrontTest` via AWS Organizations, providing the account name and a valid email address not already used by another AWS account.
2. Verify the new account appears under root, then move it into `Workloads/NonProduction`.
3. Inspect effective policies, IAM roles, and how staff sign in via IAM Identity Center.
4. Enable baseline configurations for the new account: logging, monitoring, threat detection, tagging, and budgets.
5. Only then deploy application infrastructure, such as VPC, EC2/Lambda, S3, and RDS according to the system design.

If the organization uses **AWS Control Tower**, use Control Tower's account/OU provisioning and enrollment workflows to maintain the landing zone and associated controls. Organizations is the account management foundation; Control Tower helps set up and govern a structured multi-account environment.

## 8. Consolidated Billing and Cost Control

Consolidated billing allows the management account to view and pay charges for member accounts in the organization. AWS may calculate volume discounts and share certain discount benefits according to each service/program's rules. **Consolidating billing does not mean consolidating resources or access permissions.**

For example, `StorefrontProd` runs EC2 and RDS, while `StorefrontDev` uses Lambda and S3. Their costs can still be viewed and analyzed per account, even though the management account pays the combined bill.

A cost management approach includes:

- Separating production and non-production workloads into different accounts to clearly see where costs originate.
- Applying naming conventions and tags such as `Environment`, `Team`, and `CostCenter` to applicable resources; activating cost allocation tags when reporting is needed.
- Using **AWS Cost Explorer**, **AWS Budgets**, or authorized cost reporting tools to observe trends, set alerts, and track budgets.
- Auditing leftover running test resources and restricting permissions to create expensive resource types in the Sandbox OU.

Each account's costs and access permissions should be viewed as two related but distinct concerns: **Billing** shows where money goes; **IAM and Organizations policies** decide who can do what.

## 9. Hands-On: Reading the Organization Tree with the AWS CLI

The commands below are illustrative and do not execute on their own. Configure the AWS CLI with an identity that has appropriate Organizations permissions, typically an administrative role in the management account. All IDs are placeholder values.

**Step 1 — Check the feature set and existing root:**

```bash
aws organizations describe-organization
aws organizations list-roots
```

From the output, note `FeatureSet` (`ALL` or `CONSOLIDATED_BILLING`) and the root `Id` formatted as `r-...`.

**Step 2 — List OUs and accounts:**

```bash
aws organizations list-organizational-units-for-parent --parent-id r-a1b2
aws organizations list-accounts --query 'Accounts[].{Name:Name,Id:Id,State:State}' --output table
```

The account list can show active status and IDs; check which OU an account belongs to using `list-parents`.

```bash
aws organizations list-parents --child-id 111122223333
```

**Step 3 — Create an OU or move an account (only in authorized environments):**

```bash
aws organizations create-organizational-unit \
  --parent-id r-a1b2 \
  --name NonProduction

aws organizations move-account \
  --account-id 111122223333 \
  --source-parent-id r-a1b2 \
  --destination-parent-id ou-a1b2-f6g7h111
```

Replace `r-a1b2`, `ou-a1b2-f6g7h111`, and `111122223333` with actual IDs; the example assumes the account initially sits directly under root. Before running `move-account`, verify the destination OU and its inherited policies. The account is **not** automatically moved into the newly created OU; the commands above illustrate two independent actions.

**Step 4 — View SCPs attached to an OU:**

```bash
aws organizations list-policies-for-target \
  --target-id ou-a1b2-f6g7h111 \
  --filter SERVICE_CONTROL_POLICY
```

This command returns SCPs **directly attached** to the target OU; when analyzing permissions, you must also inspect policies at the root, parent OUs, and the account itself, along with IAM policies and related permission mechanisms. If the organization has not enabled that policy type, the command may not return the expected results.

## 10. Design Scenarios and Common Misconceptions

**Scenario:** the operations team wants developers to deploy freely in dev, while preventing anyone from deleting CloudTrail logging trails in production. At the same time, finance wants to view dev and production costs separately.

A viable design:

1. Use separate accounts for `StorefrontDev` and `StorefrontProd`.
2. Place the two accounts into `Workloads/NonProduction` and `Workloads/Production`.
3. Apply an SCP restricting sensitive actions to the Production OU after testing.
4. Grant appropriate IAM/Identity Center permissions: developers get deployment permissions in dev, while production only grants permissions required for release workflows.
5. Track costs per account in consolidated billing, adding tags for deeper analysis by application and team.

**Misconception 1: "Attaching an Allow SCP grants users permission to call the API."** False. SCPs only define maximum permission bounds; IAM must still grant the corresponding permissions.

**Misconception 2: "An OU is like a big AWS account or a VPC."** False. An OU is a logical governance group; it does not contain service resources the way an account or VPC does.

**Misconception 3: "Attaching an SCP to root locks down the management account."** False. SCPs do not restrict IAM principals in the management account; the management account must be protected with dedicated controls.

**Misconception 4: "Inviting an account into an Organization immediately gives cross-account administrator access."** False. Invited accounts do not automatically get `OrganizationAccountAccessRole`; access must be set up separately if needed.

**Misconception 5: "Moving an account to another OU is just changing a label."** False. This operation can change effective policies and cause a workload or pipeline to be denied permissions.

## 11. Self-Check

**Question 1.** A company wants to prohibit deleting CloudTrail in all production accounts while still allowing experimentation in dev. Where should the SCP be attached?

**Answer:** On the Production OU (or an equivalent scope containing only the accounts that need the control), after testing. Do not attach it indiscriminately to root unless organization-wide enforcement is required.

**Question 2.** An IAM role in a member account is granted `AdministratorAccess`, but `cloudtrail:DeleteTrail` is `Deny`ed by an SCP. Will the operation succeed?

**Answer:** No. SCPs set the maximum permission limit for principals in member accounts.

**Question 3.** An organization wants both consolidated billing and SCPs. Which feature set should it use?

**Answer:** **All features**, because consolidated billing-only does not provide SCP management capabilities.

**Question 4.** Account `StorefrontDev` in the NonProduction OU is moved to the Production OU. Must its S3 data be migrated to another account?

**Answer:** No. The account and its resources remain unchanged; you must review effective policies since its position in the tree changed.

## Official AWS Documentation

- [AWS Organizations – Terminology and concepts](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_getting-started_concepts.html)
- [Managing organizational units (OUs)](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_ous.html)
- [Service control policies (SCPs)](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [SCP evaluation](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_evaluation.html)
- [Creating a member account](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_create.html)
- [Accessing member accounts](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_access.html)
- [Consolidated billing](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/consolidated-billing.html)

**Takeaway:** AWS Organizations manages **the structure and policies of multiple accounts**; OUs group accounts for governance; member accounts are the primary boundary housing workloads; IAM grants permissions; SCPs cap those permissions; and consolidated billing provides centralized cost visibility and payment.
