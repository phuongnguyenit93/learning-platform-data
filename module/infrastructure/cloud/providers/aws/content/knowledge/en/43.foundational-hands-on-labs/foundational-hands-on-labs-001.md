# Setting up a Secure Sandbox with SSO and Budget Alerts

## Learning Objectives

After this hands-on lab, you will be able to:

- Explain why a sandbox should reside in a dedicated AWS member account.
- Distinguish AWS Organizations, AWS Control Tower, and IAM Identity Center in the account provisioning and sign-in workflow.
- Choose the correct organization instance of IAM Identity Center to grant access to AWS accounts.
- Create a group, user, and enable MFA for learners.
- Create a permission set following least privilege and assign permissions to the correct sandbox account.
- Sign in to the AWS Management Console and AWS CLI using SSO without creating long-term access keys.
- Enable IAM access to the Billing console following a secure bootstrap workflow.
- Create a monthly cost budget with actual and forecasted spend alerts.
- Verify email/SNS subscribers and understand cost data latency.
- Distinguish budget alerts from actual spending limit mechanisms.
- Revoke lab permissions and retain necessary guardrails after completion.

## 1. Expected Outcome

At the end of the lab, the architecture has a dedicated AWS account for hands-on practice, a user group signing in via IAM Identity Center, a least-privilege permission set, and a cost budget sending alerts to the responsible owner.

~~~mermaid
flowchart TD
    IDP["Identity Center directory / external IdP"] --> SSO["IAM Identity Center organization instance"]
    SSO --> G["Group: Sandbox-Learners"]
    G --> PS["Permission set: Sandbox-ViewOnly"]
    PS --> A["Sandbox member account"]
    ROOT["Account root: bootstrap only + MFA"] --> BILL["Enable IAM access to Billing"]
    BILL --> B["Monthly AWS Budget"]
    B --> N["Email / SNS notifications"]
    A --> W["Lab resources in allowed Regions"]
    W --> COST["Cost and usage data"]
    COST --> B
~~~

The sandbox account is the most important isolation boundary. SSO provides identity and temporary sign-in sessions; the permission set defines permissions within the account; the budget alerts when costs approach the configured threshold.

## 2. Security Model and Lab Scope

An AWS account can incur charges and contain resources independently of the signing-in identity. Therefore, do not use the AWS Organizations management account to test workloads when you can create a separate member account.

Recommended model:

- **Management account:** manages the AWS Organization, IAM Identity Center, and account-level policies.
- **Sandbox OU:** contains member accounts for learning, experimentation, and disposable resources.
- **Sandbox member account:** where learners deploy labs.
- **IAM Identity Center:** grants permissions by user/group and permission set.
- **AWS Budgets:** tracks costs of the sandbox account and sends alerts.

This lab only configures identity, permissions, and budgets. The examples do not create EC2, RDS, or billable workload resources. When using a real account, review service pricing, Region, and retention duration before creating resources.

Do not treat a sandbox account as a free environment. Some services charge based on time, capacity, requests, data transfer, or provisioned resources even without traffic.

## 3. Prerequisites

Before starting, you need:

- An AWS account legally managed by you or your organization.
- Administrative access to the AWS Organizations management account if you need to create a member account or enable an organization instance.
- Administrative access to IAM Identity Center to create groups, permission sets, and account assignments.
- An email address capable of receiving and confirming budget notifications.
- An MFA device such as a security key or authenticator app.
- AWS CLI version 2 if you want to verify SSO from the terminal.
- The planned Region for IAM Identity Center and the Region for deploying workloads.

If this is a company-provided account, request a sandbox member account and an SSO group from your cloud/platform administrator. Do not create an AWS Organization or modify your organization's identity source without authorization.

## 4. Choosing How to Create the Sandbox Account

### 4.1 Organizations Already Using AWS Control Tower

Use AWS Control Tower Account Factory to create a member account in the sandbox OU. Account Factory applies the baseline and controls according to the configured landing zone.

General workflow:

1. Sign in to AWS Control Tower with an identity granted provisioning permissions.
2. Open Organizations or Account Factory.
3. Choose Create account.
4. Give it a clear name, for example `aws-sandbox-learning`.
5. Use an email address not attached to another AWS account for the new account's root identity.
6. Select the Sandbox OU registered in Control Tower.
7. Review the account owner/SSO access configuration.
8. Create the account and wait for provisioning to complete.
9. Confirm the account appears in the correct OU.

Do not create a member account directly via AWS Organizations to bypass Account Factory if your organization's landing zone requires a Control Tower baseline. Accounts created outside Account Factory may not be enrolled or may lack the expected controls.

### 4.2 Organizations Using AWS Organizations Without Control Tower

Sign in to the management account using an approved administrative role, open AWS Organizations, select AWS accounts, and create a member account. Use a unique email address not attached to another AWS account. Once created, move the account into the Sandbox OU and apply organization-managed Service Control Policies (SCPs) or guardrails.

An AWS Organizations member account is separate in terms of identity and billing, though billing can be consolidated at the management account. Sandbox workload resources should be created inside the member account.

SCPs set the maximum boundaries for permissions usable in member accounts; SCPs do not grant permissions to users or roles on their own. Users still need a permission set/IAM policy allowing the action.

### 4.3 You Only Have a Standalone AWS Account

You can enable IAM Identity Center using an organization instance. When done from a standalone account, AWS creates an AWS Organization and the current account becomes the management account of that organization. Afterward, you can create a separate member account to serve as the sandbox.

An account instance of IAM Identity Center does not support permission sets and does not grant sign-in access to AWS accounts. Account instances only serve supported applications within that same account. If the goal is SSO into AWS accounts, use an organization instance.

If you do not have permission or are not ready to manage an AWS Organization, use a sandbox account provided by your instructor or organization. Do not turn a production account into a management account just to complete a lab.

## 5. Protecting the Root User and Completing Bootstrap

The root user has full privileges over the account. Only use root for bootstrap tasks or account-level settings that strictly require root.

Perform the following steps for a new account:

1. Set a strong, unique root password and store it in a password manager.
2. Register MFA for root, preferring a security key or strong authenticator.
3. Do not create root access keys.
4. Do not use root to run AWS CLI, create workloads, or sign in daily.
5. Update billing, security, and operations alternate contacts with appropriate team emails.
6. Verify payment information and the account owner.
7. Sign out of root after completing bootstrap tasks.

The root email should be controlled by the account owner or corporate governance process. Do not use an individual employee's personal email as the sole recovery address for an enterprise account.

## 6. Enabling the IAM Identity Center Organization Instance

An organization instance is the IAM Identity Center type that supports multi-account permissions and permission sets. AWS recommends using an organization instance for centralized workforce access management.

Steps:

1. Sign in to the AWS Organizations management account with an administrative role.
2. Select the Region that will store and manage IAM Identity Center.
3. Open the IAM Identity Center console.
4. If no instance exists yet, choose Enable.
5. Choose to enable with AWS Organizations to create an organization instance.
6. Confirm the Region and instance configuration.
7. Wait for the instance to transition to the enabled state.

Choose the Region carefully. An IAM Identity Center organization instance has a primary Region; you cannot change the primary Region after creation. Sandbox workload resources can still run in other Regions if policies allow. Multi-Region replication is an additional configuration and is not required for a single-Region lab.

If your organization already has an IAM Identity Center organization instance, do not create a second instance. Use the existing instance and ask the administrator to provision your group/permission set.

## 7. Choosing an Identity Source

IAM Identity Center can use its built-in directory, Active Directory, or an external identity provider.

| Identity source | When appropriate | Preparation required |
|---|---|---|
| Identity Center directory | Personal labs or small teams | Create users/groups in Identity Center |
| External IdP such as Entra ID/Okta | Organizations already managing workforce identity centrally | SAML federation, SCIM provisioning, and MFA at the IdP |
| Active Directory | Organizations using Microsoft AD | Directory connectivity, group mapping, and MFA strategy |

For personal labs, the Identity Center directory is the simplest option. For enterprises, keep the identity lifecycle in the central IdP; do not create fragmented users across multiple systems when a standard identity source already exists.

When using an external IdP, MFA configuration resides at the IdP. IAM Identity Center MFA settings do not replace the external IdP's MFA policy.

## 8. Configuring MFA for the AWS Access Portal

MFA helps reduce the risk of compromised passwords. With the Identity Center directory, open IAM Identity Center, go to Settings, the Authentication tab, the Multi-factor authentication section, and choose Configure.

For learning or production environments with high security requirements:

- Choose to require users to register MFA before accessing.
- Set Prompt users for MFA to Every time they sign in if policy requires authentication on every login.
- Allow security keys or authenticator apps per policy.
- Encourage users to register a backup method.
- Test the recovery process when an MFA device is lost.

Context-aware MFA can reduce the number of prompts when the device and login context are trusted, but it offers a different protection level than always-on. Do not choose Never/disabled for a workforce portal without an approved security justification.

## 9. Creating a Group and User for the Sandbox

Open IAM Identity Center:

1. Select Users and create a user for the learner, for example `learner01`.
2. Use a real email address controlled by the learner to receive notifications and recovery messages.
3. Select Groups and create the group `Sandbox-Learners`.
4. Add user `learner01` to the group.
5. If using an external IdP, create the group in the IdP and sync it using SCIM per your organization's configuration.
6. Confirm the user and group appear in Identity Center.

Assign permissions to groups rather than assigning directly to individual users. When someone leaves the learning group, you only need to remove them from the group or revoke the assignment according to procedure.

Do not create a single shared user for the entire class. Each person needs an individual identity for accurate auditing, MFA, and permission revocation.

## 10. Creating a Least-Privilege Permission Set

A permission set is a template containing IAM policies that Identity Center provisions as an IAM role in the assigned AWS account. When a permission set changes, Identity Center updates the corresponding role in the account.

Create a permission set:

1. Go to IAM Identity Center, Multi-account permissions, Permission sets.
2. Choose Create permission set.
3. Choose Custom permission set if an inline policy is needed, or predefined permission set if using an AWS managed policy.
4. Set a name, for example `Sandbox-ViewOnly`.
5. Choose a one-hour session duration for short labs.
6. Review permissions and create the permission set.

To test SSO safely, you can use the AWS managed policy `ViewOnlyAccess` on the sandbox account. This policy allows viewing many resources; do not assign it to production accounts unnecessarily.

If future labs need to create resources, create a separate permission set with a policy scoped by service, bucket, Region, and resource ARN. Do not elevate `Sandbox-Learners` to `AdministratorAccess` just to avoid `AccessDenied` errors.

### 10.1 Example Policy Scoped to an S3 Lab Bucket

The example below allows exploring the account and reading/writing objects in a bucket pre-created by an administrator. Replace the bucket name with the actual lab bucket. The policy does not allow creating buckets or accessing objects in other buckets.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DiscoverLabEnvironment",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeRegions",
        "ec2:DescribeAvailabilityZones",
        "s3:ListAllMyBuckets",
        "cloudwatch:ListMetrics",
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ListOnlyLabBucket",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::aws-lab-example-123456"
    },
    {
      "Sid": "ManageOnlyLabObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::aws-lab-example-123456/*"
    }
  ]
}
~~~

This is a sample policy for an S3 lab, not a general policy for all AWS services. If the bucket uses SSE-KMS, you must add KMS permissions scoped to the exact key and the key policy must allow the role. If multipart uploads or object tagging are needed, add the corresponding actions for the use case.

Do not broadly add `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, or `iam:PassRole` to a learner permission set. Permissions to create or pass IAM roles can open privilege escalation paths if not tightly restricted.

## 11. Assigning the Group to the Sandbox Account

In IAM Identity Center, open Multi-account permissions, AWS accounts:

1. Select the correct sandbox member account.
2. Choose Assign users or groups.
3. Select the group `Sandbox-Learners`.
4. Select the permission set `Sandbox-ViewOnly`.
5. Review the account ID, group, and permission set.
6. Choose Submit.
7. Wait for provisioning to complete.

A user can be assigned multiple permission sets. For a learning account, assign only the permissions needed for that single sandbox account. Do not assign the learner group to the management account.

When separate billing permissions are needed, use a group/permission set intended for cost administrators. Learners who only need to view resources do not necessarily need permission to modify budgets or payment settings.

## 12. Signing In to the AWS Access Portal

Open the user portal URL displayed in IAM Identity Center Settings. The learner performs the following:

1. Sign in with the identity source username and password.
2. Complete MFA.
3. Locate the sandbox account in the AWS accounts list.
4. Select the account and the assigned permission set.
5. Choose Management console to open the AWS Console.
6. Verify the account ID in the account menu at the top right.

If the portal displays multiple accounts, choose the account labeled sandbox. Do not infer the account solely from its display name; compare the 12-digit account ID against the details provided by the administrator.

## 13. Configuring the AWS CLI with SSO

Use AWS CLI version 2. Do not run `aws configure` with an access key/secret key for this lab.

Run:

~~~bash
aws configure sso --profile aws-sandbox
~~~

The CLI will prompt for:

- SSO session name, for example `company-sso`.
- SSO start URL, obtained from IAM Identity Center.
- SSO Region, which is the Region of IAM Identity Center.
- SSO registration scopes, typically `sso:account:access`.
- The account and permission set you want to use.
- Default CLI Region for workloads, for example `ap-southeast-1`.
- Output format, for example `json`.

Sign in:

~~~bash
aws sso login --profile aws-sandbox
~~~

Verify identity:

~~~bash
aws sts get-caller-identity --profile aws-sandbox
~~~

The output must show Account as the sandbox account ID and an ARN containing the role provisioned from the permission set. If the account ID belongs to the management account or a production account, stop and fix the profile before running resource creation commands.

Sign out when finished:

~~~bash
aws sso logout --profile aws-sandbox
~~~

Example configuration in the AWS CLI config file after running configure:

~~~ini
[sso-session company-sso]
sso_start_url = https://d-1234567890.awsapps.com/start
sso_region = ap-southeast-1
sso_registration_scopes = sso:account:access

[profile aws-sandbox]
sso_session = company-sso
sso_account_id = 111122223333
sso_role_name = Sandbox-ViewOnly
region = ap-southeast-1
output = json
~~~

Replace the start URL, account ID, and role name with actual values. Do not commit config files containing internal account metadata if the repository is not authorized to store them. The config file does not contain access keys; the CLI caches temporary credentials after SSO login.

## 14. Verifying Permissions After Sign-In

Run:

~~~bash
aws sts get-caller-identity --profile aws-sandbox
aws ec2 describe-regions --profile aws-sandbox --region ap-southeast-1
aws s3 list-buckets --profile aws-sandbox --region ap-southeast-1
~~~

With the `ViewOnlyAccess` permission set, appropriate read commands will succeed. Test a write operation like creating a bucket only in an authorized lab; if the permission set does not allow it, `AccessDenied` is the expected result.

Check additionally:

- The Account ID matches the sandbox account.
- The Role name matches the permission set.
- The session duration matches the configuration.
- MFA was required.
- No long-term access keys exist in the environment.
- No root profile or IAM user profile is being used.

If an API returns `AccessDenied`, check the permission set, account assignment, SCP, resource policy, and Region. Do not resolve it by immediately assigning `AdministratorAccess`.

## 15. Enabling SSO Role Access to the Billing Console

By default, IAM users and roles cannot access the Billing and Cost Management console solely via an IAM policy. The account root user must enable the option `IAM user and role access to Billing information`.

Perform this specifically in the account where the budget is managed:

1. Open Billing and Cost Management and go to Account settings.
2. Locate `IAM user and role access to Billing information`.
3. Check `Activate IAM access`. If the setting is currently off, the account root user must enable it and save changes.
4. For newly created member accounts in AWS Organizations, this setting is often enabled by default; still verify it before troubleshooting permission errors.
5. If you need to change the setting, use root only for this account-level task and then sign out.
6. Sign back in using an SSO role with appropriate permissions.

This setting only controls IAM access to Billing console pages; it does not grant permission to read or modify budgets on its own. The role still requires corresponding IAM policies. This setting does not control permissions to call Billing and Cost Management SDK APIs such as the AWS Budgets API.

If the organization creates budgets centrally in the management account, root/admin must enable IAM billing access in the management account and the SSO role must be granted permissions in that account. Member accounts do not automatically see budgets created in the management account.

## 16. Creating a Dedicated Permission Set for Budget Administrators

Budget management permissions should not be granted to all learners. Create a separate group such as `Sandbox-Cost-Admins` and a permission set `Sandbox-Budget-Manager`.

AWS Budgets uses IAM actions such as:

- `budgets:ViewBudget` to read budgets and related information.
- `budgets:ModifyBudget` to create, edit, delete budgets, and configure notifications/subscribers.
- `budgets:CreateBudgetAction` or actions managing budget actions if the organization actively uses budget actions.

For a lab that only creates notifications, grant only the permissions to view and modify budgets as needed. Do not grant budget-action execution permissions without an approval and testing workflow. When creating a budget via the console, AWS also requires permissions to view billing information, create CloudWatch alarms, and create SNS notifications; exact permissions depend on the alert delivery method and organizational policy. For automation via the Budgets API, use a dedicated role with IAM actions scoped to requirements.

Assign this permission set to the cost administrators group in the account where the budget is managed. Learners may only be assigned `Sandbox-ViewOnly`.

## 17. Creating a Monthly Cost Budget

Open Billing and Cost Management, select Budgets, then Create budget.

Illustrative configuration:

| Field | Example value |
|---|---|
| Budget name | sandbox-monthly-cost |
| Budget type | Cost budget |
| Period | Monthly |
| Budget amount | 25 USD |
| Cost metric | Unblended cost or metric per FinOps policy |
| Account scope | Sandbox account |
| Region/service filter | Add only if tracking a subset of costs |

25 USD is only an illustrative figure to practice configuration. Choose a realistic budget based on workload, Region, support plan, data transfer, storage, and resource retention duration. There is no universal budget figure that guarantees an account will not exceed cost thresholds.

If creating a budget in a member account, the budget tracks that account's costs by default. If creating a budget from the management account and wanting to track a specific member account, use the Linked account filter to scope to the exact account ID.

## 18. Configuring Alert Thresholds

For the initial lab, create one actual threshold and one forecasted threshold:

| Type | Threshold | Meaning |
|---|---:|---|
| Actual | 50% | Early warning when actual costs have been incurred |
| Forecasted | 80% | Warning when end-of-period forecast may exceed 80% |

With a 25 USD budget, the 80% threshold equals 20 USD. You can use either an absolute value or a percentage of the budget.

Once you understand how notifications work, you can add other thresholds per your organization's FinOps process. Each budget has a limit on the number of notifications; check quotas and alert behavior for each threshold before scaling out.

An actual alert is sent when actual recorded costs reach the threshold. A forecasted alert is based on the end-of-period cost forecast; the forecast can change as usage data arrives.

Do not configure budget actions that automatically stop EC2/RDS or attach SCPs in a foundational lab. Only use notifications to learn how to monitor and verify alerts.

## 19. Sending Alerts via Email or SNS

In Notification preferences:

- Add the email of the account owner or FinOps team.
- You can add up to 10 email recipients per notification.
- Recipients must verify their email before receiving budget alerts.
- If using an SNS topic, enter the exact topic ARN and confirm the SNS subscription via email.
- SNS can be used to route alerts to Lambda, SQS, or an organization-approved notification system.

After creating the budget, check subscriber status. If using SNS, open the email subscription confirmation and choose Confirm subscription. An unconfirmed topic can prevent alerts from reaching recipients.

## 20. Understanding AWS Budgets Latency

AWS Budgets is not a real-time cost metering system.

- Budgets data is updated up to three times per day, typically around 8–12 hours apart.
- There is latency between when resources generate usage and when usage is recorded in billing data.
- Actual alerts are sent only once per budget in a budget period when the actual threshold is first crossed.
- Forecasted alerts can be sent multiple times if the forecast exceeds the threshold, drops below, and exceeds it again.
- AWS requires about five weeks of usage history to generate a forecast; forecast alerts may not activate during the early days of a new account.

Therefore, an account can incur costs exceeding the threshold before an alert email is sent. Actual costs can also continue rising after an alert arrives. Do not use budget notifications as an absolute spending blocker.

## 21. Verifying the Budget and Notifications

After creating the budget:

1. Open Budgets and select `sandbox-monthly-cost`.
2. Verify the budget amount, period, and cost metric.
3. Verify account/service/Region filters.
4. Verify actual and forecasted thresholds.
5. Verify the list of email subscribers.
6. Verify SNS subscription status if using SNS.
7. Verify the budget was created in the correct account.
8. Record the owner, review date, and alert recipient email.

You can use the AWS CLI to list budgets:

~~~bash
aws budgets describe-budgets \
  --account-id 111122223333 \
  --region us-east-1 \
  --profile aws-sandbox
~~~

The AWS Budgets API endpoint is a global service endpoint; the CLI command still requires a Region for client configuration. Use the exact account ID of the account that owns the budget. If the CLI role lacks `budgets:ViewBudget` permission, the command will return `AccessDenied`.

## 22. Budget Actions and Spend Control

AWS Budgets supports budget actions in certain scenarios. An action can apply an IAM policy, attach a Service Control Policy from the management account, or target EC2/RDS resources. Actions can require approval or run automatically depending on configuration.

A budget action is a reactive measure with operational impact. For example, a deny policy can halt pipelines, an SCP can block administrative operations, and stopping EC2/RDS can disrupt applications. Only deploy when:

- There is an accountable owner.
- Testing has been performed in a sandbox.
- There is an action role with least privilege.
- There is an approval/rollback procedure.
- Affected users are notified.

A budget alert is still not a hard spending cap. If a spending limit is needed for a new project that has a dedicated spend limit feature, evaluate the specific account/project type and AWS support conditions; do not confuse it with standard cost budget notifications.

## 23. Organizing Tags and Cost Visibility

To analyze costs by lab or team, standardize tag keys before creating workloads:

| Tag key | Example | Purpose |
|---|---|---|
| Project | aws-learning | Group costs by project |
| Environment | sandbox | Distinguish environments |
| Owner | learner-team | Identify accountable owner |
| CostCenter | training | Internal cost allocation |
| ExpiryDate | 2026-12-01 | Remind for cleanup |

Cost allocation tags must be activated in the Billing console before appearing in corresponding cost allocation reports. Not all services apply tags the same way. Tags do not automatically block costs or delete expired resources.

For sandboxes, name resources with a consistent prefix and record an expiry date. Use AWS Config, automation, or inventory reports to find forgotten resources if your organization has deployed them.

## 24. Case Study: AWS Learning Group Using a Sandbox Account

A team of 12 people needs to practice S3, Lambda, and CloudWatch for two weeks. The organization has AWS Organizations and Control Tower.

### Design

1. The platform team creates account `aws-training-sandbox` via Account Factory in the Sandbox OU.
2. Control Tower baselines and organizational SCPs are applied.
3. IAM Identity Center group `Sandbox-Learners` contains the 12 learners.
4. Permission set `Sandbox-ViewOnly` grants observation permissions.
5. A separate permission set `Sandbox-Builder` is scoped to designated buckets, Lambda functions, and log groups.
6. Group `Sandbox-Cost-Admins` has permissions to manage budgets.
7. Budget `sandbox-monthly-cost` is set to 25 USD with 50% actual and 80% forecast thresholds.
8. Email alerts are sent to the team's shared mailbox and the FinOps lead.

### Operations

- Learners sign in using SSO and MFA.
- All CLI commands use the `aws-sandbox` profile.
- The platform team verifies the account ID before each workshop.
- Budget alerts are sent to the shared mailbox.
- At the end of the session, learners delete lab resources; the platform team reviews leftovers.
- The budget is retained to continue alerting while the account remains active.

### Expected Outcome

Each person has an individual identity, permissions are centrally managed, workloads reside in an isolated account, and costs are monitored against a shared threshold. If someone leaves the group, the administrator revokes group membership or assignment without rotating access keys.

## 25. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| AWS accounts not visible in portal | Using an account instance or missing account assignment | Check organization instance and group/permission set assignment |
| Cannot create permission set | IAM Identity Center account instance does not support permission sets | Use an organization instance |
| User can sign in but does not see sandbox | Group not assigned to account or provisioning incomplete | Check AWS accounts assignments |
| AccessDenied when opening a service | Blocked by permission set, SCP, or resource policy | Identify the explicit deny and request minimum required permissions |
| CLI reports missing SSO profile | AWS CLI unconfigured or outdated version | Use AWS CLI v2 and run `aws configure sso` |
| CLI returns wrong account ID | Wrong account/profile selected | Check `aws sts get-caller-identity` |
| MFA prompt does not appear | MFA managed by external IdP or setting not applied | Check identity source and MFA policy in the right place |
| SSO role cannot open Billing console | IAM Billing access not enabled in the account | Root enables `Activate IAM access`; check role policy |
| Cannot create budget | Missing `budgets:ModifyBudget` or billing permissions | Check permission set and Billing console access |
| Cannot view budget | Missing `budgets:ViewBudget` or in wrong account | Check permission set and account ID |
| Budget alert email not sent | Email unverified or wrong subscriber address | Verify email and review notification settings |
| SNS not receiving alerts | SNS subscription unconfirmed or wrong topic ARN | Confirm subscription and check topic policy |
| Forecast alert not working yet | Account lacks sufficient usage history | Wait about five weeks for data or rely on actual alerts |
| Costs exceeded threshold before alert | Billing data and Budgets have latency | Check Cost Explorer/Bills; budget is not a real-time cap |
| Budget displays inaccurate sandbox costs | Budget created in management account without linked account filter | Add the exact Linked account filter |
| User still has access after group removal | Session or assignment not yet expired | Revoke assignment, end active sessions, and check group sync |
| Member account lacks Control Tower controls | Account created outside Account Factory or not enrolled | Follow Control Tower enrollment/baseline procedures |

## 26. Post-Lab Cleanup

Retain necessary guardrails:

- Keep the monthly cost budget and notifications while the account is in use.
- Keep MFA and root account protections.
- Keep groups and permission sets if the class continues.
- Delete workload resources created in other labs according to their respective checklists.
- Revoke permission set assignments for users no longer participating.
- Delete test users only when there are no remaining dependencies or audit history to retain.
- Confirm SSO CLI logout and ensure no temporary access keys remain in the environment.
- Review Budgets subscribers when the email owner changes.

Do not delete the IAM Identity Center organization instance or close the AWS account just to clean up a short lab. If closing a sandbox account is needed, follow the organization's account closure process and verify no resources, invoices, or dependent workloads remain.

## 27. Self-Check Exercises

1. Why should sandbox workloads reside in a dedicated member account?
2. What is the AWS Organizations management account used for?
3. How does AWS Control Tower Account Factory help when creating a sandbox account?
4. How do an organization instance and an account instance of IAM Identity Center differ?
5. Which IAM Identity Center instance type supports permission sets and AWS account access?
6. Why must the IAM Identity Center Region be chosen carefully?
7. Does Identity Center MFA override external IdP MFA?
8. Why does each learner need a separate user?
9. What is a permission set?
10. Why should you assign a group to an account instead of assigning users manually?
11. Which phase is `ViewOnlyAccess` suitable for?
12. Why should you not grant `AdministratorAccess` to the entire class?
13. Which AWS CLI SSO command configures a profile?
14. Which command confirms the current account ID and principal?
15. Why should the root user not be used daily?
16. Does the `Activate IAM access` option grant Billing permissions on its own?
17. How do a cost budget and a budget action differ?
18. Why is a budget alert not a hard spending cap?
19. How frequently does AWS Budgets update its data?
20. Roughly how many weeks of usage history does a forecast alert require?
21. How do actual alerts and forecast alerts differ?
22. What must an email subscriber do before receiving notifications?
23. Why is a Linked account filter needed when creating a budget in the management account?
24. Do tags automatically prevent resources from incurring costs?
25. When should a budget action be used?

### Suggested Answers

1. A separate account establishes a boundary for permissions, costs, resources, and cleanup.
2. Managing the organization, member accounts, OUs, and policies.
3. Provisions member accounts with the landing zone's baseline and controls.
4. An organization instance supports multi-account management and permission sets; an account instance only supports certain applications within a single account.
5. Organization instance.
6. The primary Region of an organization instance cannot be changed after creation.
7. No. External IdPs manage MFA for their own identities.
8. For auditing, MFA, revocation, and individual access assignment.
9. A template of IAM policies provisioned as a role inside the assigned account.
10. Consistent lifecycle and access assignment management.
11. When learners only need to observe and verify SSO.
12. Broad permissions increase the blast radius and risk of creating costly resources.
13. `aws configure sso`.
14. `aws sts get-caller-identity`.
15. Root has full privileges and is hard to restrict; use it only for special account-level tasks.
16. No. It only allows IAM identities to access the Billing console when policies also permit it.
17. A budget action can execute reactive measures; a budget alert only sends notifications.
18. Billing data and notifications have latency; resources can still incur charges.
19. Up to three times per day, typically around 8–12 hours apart.
20. About five weeks.
21. Actual is based on recorded charges; forecast is based on end-of-period projections.
22. Verify the email address or confirm the SNS subscription.
23. So the budget only tracks costs for that specific member account.
24. No. Tags are for cost classification and allocation.
25. When there is an owner, policy, approval, rollback, and impact testing in place.

## 28. Interview Questions

### Why does AWS recommend the organization instance of IAM Identity Center?

Because it fully supports multi-account permissions, permission sets, centralized identity management, and application assignments across an AWS Organization. An account instance is only suitable for certain supported applications within a single account.

### Is a permission set an IAM role?

Not directly. A permission set is a template in IAM Identity Center. When assigned to an AWS account, Identity Center provisions a managed IAM role in that account and attaches the corresponding policies.

### Does MFA replace least privilege?

No. MFA protects user authentication; permission sets and IAM policies control which actions a user is permitted to perform after signing in.

### Why should you not use PowerUserAccess for all learners?

`PowerUserAccess` is very broad across many AWS services. If assigned to the wrong account or if learners can create large resources, costs and blast radius increase. Use specialized permission sets with resource scoping.

### Can AWS Budgets stop all spending when reaching 100%?

Not via standard cost budget alerts. A budget action can perform certain configured IAM/SCP/EC2/RDS actions, but there is latency and it can cause disruptions. Do not treat it as an account-wide hard cap.

### Why should actual and forecasted alerts be configured separately?

Actual alerts trigger when recorded costs reach the threshold; forecasted alerts provide early warning based on projections. Forecasts require usage history and can fluctuate multiple times within a period.

### When do you need to enable IAM Billing access?

When you want IAM roles/users to access the Billing and Cost Management console. The setting must be enabled by root in the respective account; IAM policies still need to grant specific actions.

### Why must you verify the account ID before running CLI commands?

An SSO profile can be configured for multiple accounts/permission sets. Verifying the account ID prevents resource creation or deletion commands from accidentally running against the management or production account.

## 29. Production Checklist

### Account isolation

- [ ] Sandbox is a dedicated member account or organization-approved learning account.
- [ ] Management account does not host hands-on workloads.
- [ ] Sandbox OU has appropriate guardrails/SCPs.
- [ ] If using Control Tower, account is provisioned/enrolled via Account Factory.
- [ ] Alternate contacts and payment details are updated.

### Root and SSO

- [ ] Root user has strong MFA.
- [ ] Root has no access keys.
- [ ] Organization instance is enabled in the correct Region.
- [ ] Identity source and MFA policy are confirmed.
- [ ] Each user has an individual identity.
- [ ] Groups and permission sets follow least privilege.
- [ ] Session duration is reasonable.
- [ ] User portal and CLI login are tested.

### Permissions

- [ ] Permission sets are assigned only to the correct sandbox account.
- [ ] `AdministratorAccess` is not granted to the learner group.
- [ ] Resource-specific policies use accurate ARNs and Regions.
- [ ] IAM `PassRole`/`CreateRole` are not broadly granted.
- [ ] Cost management permissions are separated from developer permissions.
- [ ] SCPs and resource policies have been reviewed.

### Budget and alerts

- [ ] Monthly cost budget has an owner.
- [ ] Budget amount aligns with workload and currency.
- [ ] Actual thresholds are configured.
- [ ] Forecast threshold is configured if sufficient history exists.
- [ ] Email recipients are verified.
- [ ] SNS subscriptions are confirmed.
- [ ] Account/Region/service filters are accurate.
- [ ] Owner understands latency and does not treat budget alerts as a hard cap.
- [ ] Budget actions are enabled only after review, approval, and rollback testing.

### Operations

- [ ] Scheduled or daily cost review process is in place.
- [ ] Lab resource cleanup process is in place.
- [ ] SSO groups and permission sets have an owner.
- [ ] Assignment revocation process exists when users leave the group.
- [ ] Runbooks exist for `AccessDenied`, MFA recovery, and budget alerts.
- [ ] Review schedule exists for budget amounts and subscribers.

## 30. Official References

### AWS account and isolation

- [AWS Organizations: Create a member account](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_create.html)
- [AWS Control Tower: Account Factory](https://docs.aws.amazon.com/controltower/latest/userguide/account-factory.html)
- [Provision accounts in AWS Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/methods-of-provisioning.html)
- [AWS account root user best practices](https://docs.aws.amazon.com/accounts/latest/reference/root-user.html)
- [Update alternate contacts for an AWS account](https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-update-contact-alternate.html)

### IAM Identity Center and SSO

- [Organization and account instances of IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-instances.html)
- [Organization instances of IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/organization-instances-identity-center.html)
- [Enable IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/enable-identity-center.html)
- [Manage AWS accounts with permission sets](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetsconcept.html)
- [Create and manage permission sets](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsets.html)
- [Assign user or group access to AWS accounts](https://docs.aws.amazon.com/singlesignon/latest/userguide/assignusers.html)
- [Configure MFA in IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/mfa-configure.html)
- [Prompt users for MFA](https://docs.aws.amazon.com/singlesignon/latest/userguide/mfa-getting-started.html)
- [Configure user access with the default Identity Center directory](https://docs.aws.amazon.com/singlesignon/latest/userguide/quick-start-default-idc.html)
- [Configure AWS CLI to use IAM Identity Center](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)

### Billing and AWS Budgets

- [Manage access permissions for Billing and Cost Management](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/control-access-billing.html)
- [Create a cost budget](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html)
- [Best practices for AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)
- [Managing costs with AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [Configure a budget action](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-action-configure.html)
- [AWS Budgets IAM actions and resource types](https://docs.aws.amazon.com/service-authorization/latest/reference/list_budgets.html)
- [CreateBudget API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_budgets_CreateBudget.html)
