# AWS Management Console, CloudShell, and AWS CLI

In the Amazon Web Services (AWS) ecosystem, a resource such as an EC2 instance, S3 bucket, or VPC can be managed via a web interface, a browser-based terminal, or a command-line tool installed on your local machine. The three common approaches are the **AWS Management Console**, **AWS CloudShell**, and the **AWS Command Line Interface (AWS CLI)**. Understanding their similarities, differences, and authentication mechanisms is a foundational skill before deploying applications securely, monitoring operations, or automating infrastructure.

> **Lesson scope:** Learn how to access and interact with AWS using the Console, CloudShell, and AWS CLI; identify the correct account, IAM principal, and Region; practice read-only resource inspection commands; troubleshoot common errors; and choose the right tool for each task. Examples use the `ap-southeast-1` (Singapore) Region, which you can replace with a Region approved by your organization.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish the Console, CloudShell, and AWS CLI by execution environment, authentication method, repeatability, and intended use.
2. Verify the **AWS account**, **IAM identity/role**, and **Region** before acting; understand why a successful login does not automatically grant access to every resource.
3. Launch CloudShell, use the pre-installed AWS CLI, and know which data persists across sessions.
4. Install AWS CLI v2 on a local machine, create a profile via **AWS IAM Identity Center**, and execute commands with explicit profile and Region flags.
5. Read JSON output, filter with `--query`, and understand how pagination behaves.
6. Practice inspecting AWS resources under least privilege while avoiding unintended charges.

## 2. Three Ways to Work with the Same AWS System

Every method targets **AWS service APIs** and goes through AWS access evaluation. Changing the interface never bypasses IAM authorization rules.

| Criterion | AWS Management Console | AWS CloudShell | Locally installed AWS CLI |
|---|---|---|---|
| Access point | Web browser, visual UI | Browser-based terminal launched from the Console | Terminal on Windows, macOS, Linux, or automation environments |
| Setup | Web browser and login credentials | Active Console session and CloudShell permission; CLI pre-installed | Install AWS CLI and configure how credentials are obtained |
| Authentication | AWS login session, typically via IAM Identity Center/role | Inherits credentials from the Console session | IAM Identity Center profile, IAM role, or other credential source |
| Best suited for | Exploring services, viewing configs, low-step operations | Quick checks, running short commands/scripts without local installs | Repetitive tasks, batch operations, shell/CI integration |
| Watch out for | Easy to lose track of account or Region when switching screens | Session timeouts, storage limits, and Regional availability | Must manage profiles, login sessions, CLI versions, and local environment |

~~~mermaid
flowchart TD
    U[Operator] --> C[AWS Management Console]
    C --> H[AWS CloudShell]
    U --> L[AWS CLI on local machine/CI]
    C --> A[AWS service APIs]
    H --> A
    L --> A
    A --> P[Evaluate IAM permissions and related policies]
    P --> R[Resources in AWS account and Region]
~~~

**Example:** When checking why an EC2 instance fails to start, a beginner can open **EC2 → Instances** in the Console to inspect its state. An operator can use CloudShell to run `aws ec2 describe-instances` to fetch data quickly. An AWS CLI script can run the same read command across multiple authorized accounts/Regions. Regardless of the tool, commands that modify or delete resources still require appropriate AWS permissions.

### 2.1. Four Concepts to Distinguish

- **Account:** An administrative boundary identified by a 12-digit AWS account ID. An organization may separate development, staging, and production accounts.
- **Identity/principal:** The IAM user or role being assumed; when users sign in via IAM Identity Center, they typically access an account through an IAM role with an assigned permission set.
- **Region:** A geographic area containing Region-scoped services/resources, such as VPC and EC2. Singapore has code `ap-southeast-1`; Tokyo has code `ap-northeast-1`.
- **Availability Zone (AZ):** One or more isolated data centers within a Region. For example, a subnet belongs to one AZ, whereas a VPC spans the Region.

Not all services share the same scope. **IAM** is global at the account level; **Amazon CloudFront** manages global distributions; **EC2/VPC** are Regional. **S3 bucket names** must be unique within the applicable bucket namespace, yet each general purpose bucket belongs to a specific Region. Consequently, switching the Region in the Console can make the EC2 list look empty while resources actually exist in another Region.

## 3. AWS Management Console

The AWS Management Console is a web UI for browsing services, inspecting resources, configuring permissions, viewing monitoring metrics, and performing many administrative tasks without crafting raw API requests.

### 3.1. Signing In and Confirming Context

1. Open the [AWS Management Console](https://console.aws.amazon.com/) or the **AWS access portal** provided by your organization.
2. In organizational environments, prefer **IAM Identity Center**, sign in with multi-factor authentication (MFA), and select the right AWS account and assigned role/permission set.
3. Verify the account name/ID and active role in the identity menu, especially when working across `dev`, `staging`, and `prod` accounts.
4. Select the Region in the navigation bar, for example **Asia Pacific (Singapore) – `ap-southeast-1`**.
5. Use the service search bar to open **EC2**, **VPC**, **S3**, **CloudWatch**, or **IAM**.

**Do not use the root user for day-to-day work.** Root holds special account-level privileges suited for specific mandatory administrative tasks and must be strictly protected with MFA. Signing into an account still does not mean you can create, edit, or view every resource: IAM policies, permission boundaries, service control policies (SCPs), and resource policies may restrict access.

### 3.2. A Safe Exploration Walkthrough

Suppose you want to inspect existing network infrastructure:

1. Check the **account and Region** in the top header bar.
2. Go to **VPC → Your VPCs** and note the VPC ID, IPv4 CIDR, state, and whether it is a default or custom VPC.
3. Go to **VPC → Subnets** to see which AZ each subnet resides in.
4. Go to **EC2 → Instances** to view instance IDs, instance types, states, and associated VPCs/subnets.
5. If you do not see resources, re-check the Region, UI filters, and read permissions; do not rush to create new resources.

Some Console features use multi-step wizards that may subtly pre-select creating security groups, volumes, public IPs, or companion resources. Before clicking **Create**, **Save**, **Delete**, or **Terminate**, review every option, cost estimate, and impact. Simply opening pages and reading settings carries far less risk than mutating state.

### 3.3. Advantages and Limitations

The Console is convenient for discovering unfamiliar attributes and seeing relationships between services. However, repeated mouse clicks are hard to reproduce accurately, especially across dozens of VPCs, instances, or accounts. Once you understand an operation, you can express it with the AWS CLI and eventually move repeatable infrastructure changes into Infrastructure as Code (such as CloudFormation or Terraform) with change review and source history.

## 4. AWS CloudShell

**AWS CloudShell** is an AWS-managed shell environment launched directly in the browser from the Console. The standard environment is based on Amazon Linux 2023, supports Bash, PowerShell, and Z shell, and comes with **AWS CLI v2** and common utilities pre-installed. CloudShell lets you practice AWS commands without installing the CLI or storing access keys on a personal computer.

### 4.1. Launching CloudShell and Checking the Session

1. Sign into the Console with an identity permitted to use CloudShell.
2. Select a Region, locate the **CloudShell** icon in the navigation bar or Console toolbar, and open the terminal.
3. Wait for the environment to initialize and enter the following commands:

~~~bash
aws --version
aws sts get-caller-identity
aws configure list
echo "$AWS_REGION"
~~~

`aws --version` shows the installed CLI version. `aws sts get-caller-identity` returns the `UserId`, `Account`, and `Arn` of the principal actually making the request. This is the single most important check before running commands that modify resources. `aws configure list` displays the **sources** of configuration/credentials for diagnostics; never print secret access keys or session tokens into documentation, tickets, or logs. `AWS_REGION` shows the Region currently set as default in the environment.

When launching CloudShell from a Console session, **credentials are provided automatically**, so you typically **do not need `aws configure`** to enter access keys. API permissions belong to that principal and are never automatically elevated to administrator. An identity needs both permission to use CloudShell (including credential forwarding) and permissions on the target services. The AWS-managed policy `AWSCloudShellFullAccess` is one way to grant CloudShell access when approved by an organization; it is not a requirement to grant administrator rights to every learner.

### 4.2. Regions in CloudShell

CloudShell has a Region where the shell environment runs. Normally this aligns with the Region selected when launching from the Console. The default Region for the AWS CLI inside CloudShell is set via the `AWS_REGION` environment variable.

~~~bash
# Affects only the currently open shell session
export AWS_REGION=ap-southeast-1

# You can always specify the Region explicitly for a single command
aws ec2 describe-vpcs --region ap-southeast-1 --output table
~~~

**Distinction:** The Region hosting the *CloudShell environment* and the target Region where the *AWS CLI calls APIs* can differ. The `--region` parameter on a CLI command specifies the API target; it does not move files inside CloudShell to another Region. Switching the environment Region in the CloudShell UI can open a session with a different home directory.

### 4.3. Files, Session Limits, and Cost

| Component | Behavior to remember |
|---|---|
| `$HOME` directory (standard CloudShell) | Up to **1 GiB** of persistent storage **per Region**, not synchronized across Regions |
| Files outside `$HOME` | Can be wiped when the session/temporary environment ends; do not use for data you need to keep |
| Inactivity in a Region's CloudShell | Home data has a retention policy; per AWS documentation, it may be deleted after **120 days** of inactivity in that Region |
| CloudShell VPC environment | Can connect to VPC resources as configured, but has **no persistent home storage** like the standard environment |
| Shell session | Designed for interactive commands/short scripts; subject to session, idle timeout, and resource limits |
| Cost | CloudShell has no separate charge for the standard environment, though AWS resources created/used and data transfer can incur charges |

Do not store secrets, long-lived access keys, or sensitive customer data in practice scripts. If you need jobs running for hours, stable deployment environments, or automated schedules, use an appropriate service such as AWS Systems Manager, CodeBuild, Lambda, ECS, or a managed CI platform depending on requirements.

### 4.4. When to Use CloudShell?

CloudShell is ideal for inspecting configurations, one-off commands, cross-checking APIs against the Console, or working from a machine without AWS CLI installed. Its limits are compute resources, session duration, storage, and coupling to a Console session; it does not replace long-running job platforms.

## 5. AWS CLI v2 on a Local Machine

The **AWS CLI** is a tool for invoking AWS APIs via command-line syntax. General structure:

~~~text
aws <service> <operation> [operation-parameters] [global-options]
~~~

Examples:

~~~bash
aws sts get-caller-identity
aws ec2 describe-vpcs --region ap-southeast-1 --output json
aws s3 ls
~~~

Here, `sts`, `ec2`, and `s3` are service groups; `get-caller-identity`, `describe-vpcs`, and `ls` are operations. Some services provide both high-level, user-friendly commands like `aws s3 ls` and lower-level commands mapping closer to the API like `aws s3api list-buckets`.

### 5.1. Installation and Verification

AWS CLI v2 has dedicated installers for Windows, macOS, and Linux. Follow the official guide [Installing or updating to the latest version of the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) to get the installer for your OS/architecture, then run:

~~~bash
aws --version
aws help
aws sts help
~~~

`aws --version` should report `aws-cli/2...` if you are using v2. If CLI v1 is already installed on the machine, check your executable path/PATH; both versions are invoked with the `aws` command.

Installing the CLI **does not mean you are authenticated** to AWS: next you need a mechanism to obtain valid credentials.

### 5.2. Signing In via IAM Identity Center (Recommended for Users)

In enterprise environments, administrators typically provide an **AWS access portal URL (SSO start URL)**, the IAM Identity Center Region, and permitted accounts/roles. Create a profile named `dev`:

~~~bash
# Run in a terminal on a machine with AWS CLI v2 installed
aws configure sso --profile dev

# Follow the browser sign-in prompt
# and choose the account, role, default Region, and output format.
aws sso login --profile dev

# Verify the actual identity of the request
aws sts get-caller-identity --profile dev
~~~

`aws configure sso` creates a configuration for the profile to use an SSO session and retrieve **temporary credentials** for a role. `aws sso login` performs sign-in and caches session details using the CLI's mechanism. When an Identity Center session expires, sign in again instead of creating long-lived access keys.

**Two different Regions to notice:** `SSO region` is the Region hosting the IAM Identity Center configuration; `CLI default client Region` is the default Region for AWS API calls when using the profile. They do not have to be the same.

Illustrative example of the `~/.aws/config` file structure (URLs/account/role values are dummy data):

~~~ini
[profile dev]
sso_session = company
sso_account_id = 111122223333
sso_role_name = ReadOnly
region = ap-southeast-1
output = json

[sso-session company]
sso_start_url = https://example.awsapps.com/start
sso_region = ap-southeast-1
sso_registration_scopes = sso:account:access
~~~

The file above is an **example**, not a usable configuration for a real account. In practice, let the CLI generate the file by running `aws configure sso` instead of copying manually; never commit internal configurations or session details to a public repository.

### 5.3. Profiles, Regions, and Precedence Order

One machine can have multiple profiles with different permissions/accounts. Pass `--profile` and `--region` explicitly while learning or when operating on important resources.

~~~bash
aws configure list-profiles
aws configure list --profile dev

aws sts get-caller-identity --profile dev
aws ec2 describe-vpcs --profile dev --region ap-southeast-1
~~~

You can set a default profile for a single terminal session:

~~~bash
# Bash, Z shell (Linux/macOS or CloudShell)
export AWS_PROFILE=dev
export AWS_REGION=ap-southeast-1
~~~

~~~powershell
# PowerShell (Windows)
$env:AWS_PROFILE = 'dev'
$env:AWS_REGION = 'ap-southeast-1'
~~~

For options such as Region, the usual precedence order is **command parameter `--region` → environment variables → profile configuration**. In AWS CLI v2, `AWS_REGION` can override `AWS_DEFAULT_REGION`. For profiles, `--profile` overrides `AWS_PROFILE`. Credential sources have multiple mechanisms and their own precedence rules; if a command uses the wrong identity, check `aws configure list` and relevant environment variables before editing config files.

**Security note:** Do not use `aws configure` with long-lived IAM user access keys as a substitute for SSO sign-in when your organization supports Identity Center. For applications running on EC2/ECS/Lambda, attach an IAM role to the workload to receive temporary credentials rather than copying human credentials onto servers.

### 5.4. Reading Output, Filtering Data, and Finding Help

The AWS CLI supports common output formats:

- `--output json`: convenient for scripts, field parsing, and JSON processing tools.
- `--output table`: convenient for quick human reading in a terminal.
- `--output text`: tab/column-delimited text output; handle carefully when parsing automatically, especially across paginated results.

The `--query` option uses **JMESPath** expressions to filter fields in the returned response. Example querying VPCs:

~~~bash
aws ec2 describe-vpcs \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Vpcs[].{Id:VpcId,Cidr:CidrBlock,Default:IsDefault}' \
  --output table
~~~

The output can display columns `Id`, `Cidr`, and `Default`. If the account has no VPCs in this Region, an empty table is normal. `--query` only filters data **after AWS authorizes the request**; it does not grant extra access or hide data that IAM forbids the user from reading.

To explore commands:

~~~bash
aws help
aws ec2 help
aws ec2 describe-vpcs help
~~~

If CLI v2 enables an output pager, you can add `--no-cli-pager` to print directly to the terminal. **Do not confuse `--no-cli-pager` with `--no-paginate`**: the second option disables automatic pagination of API result pages and may return only the first page. By default, the CLI automatically stitches pages for paginated commands; use `--max-items` / `--starting-token` when intentionally processing data in batches.

## 6. Hands-On Practice: Comparing Console, CloudShell, and CLI

### 6.1. Prerequisites

You need a practice AWS account, appropriate VPC/EC2/S3 read permissions, CloudShell access if using that interface, and (optionally) a local `dev` CLI profile signed in via IAM Identity Center. No new EC2 instances, VPCs, or S3 buckets need to be created in this exercise.

Set two context variables:

- **Target account:** the account ID assigned for your learning environment.
- **Target Region:** `ap-southeast-1` or the Region designated by your administrator.

If using **CloudShell**, the commands below run with credentials inherited from the Console; omit `--profile dev`. If using a **local CLI**, append `--profile dev` to AWS commands or set `AWS_PROFILE` in your terminal.

### 6.2. Step A – Confirm the Right Account and Role

In the Console, open the identity menu and read the account/role. In CloudShell, run:

~~~bash
aws sts get-caller-identity \
  --query '{Account:Account,Principal:Arn}' \
  --output json
~~~

**Illustrative** example output:

~~~json
{
  "Account": "111122223333",
  "Principal": "arn:aws:sts::111122223333:assumed-role/ExampleReadOnly/session-name"
}
~~~

Compare the `Account` field with the account selected in the Console. If `Arn` contains `assumed-role/...`, you are operating through a role session. Do not paste real account outputs into public places unnecessarily.

On a local CLI, run the equivalent check:

~~~bash
aws sts get-caller-identity --profile dev --output json
~~~

### 6.3. Step B – View VPCs by Region

In the Console, open **VPC → Your VPCs**, select Singapore, and note the VPC IDs you are permitted to see. In CloudShell:

~~~bash
aws ec2 describe-vpcs \
  --region ap-southeast-1 \
  --query 'Vpcs[].{VpcId:VpcId,Cidr:CidrBlock,Default:IsDefault,State:State}' \
  --output table
~~~

If no VPCs exist, the API can still succeed and return an empty list. If it reports `AccessDenied`, you need the corresponding `ec2:DescribeVpcs` permission. **Do not create a new VPC just to get output.**

### 6.4. Step C – View EC2 Instances Without Changing State

In the Console, open **EC2 → Instances** and clear unnecessary filters. Run:

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,Type:InstanceType,State:State.Name,Vpc:VpcId}' \
  --output table
~~~

An empty list may mean there are no instances, the wrong Region is selected, a Console filter is active, or permissions are insufficient. These `describe-*` commands are read-only metadata queries; never replace them with `run-instances`, `start-instances`, or `terminate-instances` in a shared account.

### 6.5. Step D – Inspect the S3 Bucket List

~~~bash
aws s3api list-buckets \
  --query 'Buckets[].Name' \
  --output table
~~~

This command requires the appropriate `s3:ListAllMyBuckets` permission. S3 has a different scope model from EC2: listing an account's buckets does not mean all buckets reside in the current Region. For a specific bucket, you can query its location:

~~~bash
# Replace YOUR_BUCKET_NAME with a bucket you are permitted to view.
aws s3api get-bucket-location --bucket YOUR_BUCKET_NAME
~~~

A `LocationConstraint` result of `null` for a bucket in `us-east-1` occurs due to historical API conventions; therefore, do not interpret `null` as the bucket having no Region. Appropriate IAM permissions are required to run `get-bucket-location`.

### 6.6. Step E – Record Evidence and Cross-Check

Record the **account ID**, **principal ARN**, **Region**, number of VPCs, and number of EC2 instances you are permitted to see; use placeholder names/IDs if sharing publicly. Verify whether the Console and CLI show the same account/Region. If results differ, check **identity, Region, filters, and permissions** first before suspecting an AWS outage.

Open the local AWS CLI with the `dev` profile and re-run the VPC command:

~~~bash
aws ec2 describe-vpcs \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Vpcs[].VpcId' \
  --output json
~~~

When identity, Region, and permissions match, the Console and CLI should reflect the same set of resources at query time, aside from differences due to UI filters, timing, or access permissions.

## 7. Safe Operations and Cost Control

### 7.1. Before Running Any Mutating Command

Some CLI commands can create or destroy infrastructure in a single line. Operational habits to build:

1. Run `aws sts get-caller-identity` and confirm the account/role.
2. Specify `--region` and `--profile` (when needed) in important commands or scripts.
3. Review effective permissions, resource names, parameters, and dependencies before creating/modifying/deleting.
4. Inspect first using appropriate `list-*`, `describe-*`, and `get-*` commands; use `--dry-run` **only when the operation genuinely supports it**.
5. For production environments, follow your organization's review/approval workflow and prepare a rollback plan.

### 7.2. Permission Governance

**Least privilege** means granting only the permissions required for the task. An account might allow `ec2:DescribeInstances` while denying `ec2:TerminateInstances`. AWS evaluates authorization across multiple policy layers: identity-based policies, resource-based policies, permission boundaries, session policies, SCPs in AWS Organizations, and explicit denies where applicable. Granting permission to use CloudShell does **not** equal granting permission to manage EC2/S3.

Use IAM Identity Center + MFA for human users. For workloads, prefer temporary credentials from IAM roles. Never write access keys/secret keys into source code, shell history, issue trackers, or CI logs. Do not use `--no-verify-ssl` to "quick-fix" certificate errors, because that disables TLS verification; fix the trust store or proxy properly instead.

### 7.3. Observability and Auditing

AWS CloudTrail can record AWS API calls according to your trail/event history configuration and event types; CloudWatch supports metrics, logs, and alarms per service. When investigating infrastructure changes, examine the principal, action, timestamp, Region, resource, and request outcome. The Console and CLI are **access paths**; whichever interface a user chooses does not alter the organization's logging, monitoring, and auditing requirements.

### 7.4. Cost

The Console and AWS CLI are control interfaces, not a "free mode" for created resources. Standard CloudShell has no separate environment charge, but creating EC2 instances, writing to S3, transferring data, or using other services can still incur charges. Before hands-on labs that create resources, review the Pricing Calculator, budgets/cost alerts, permission limits, and cleanup plans.

## 8. Common Issues and Troubleshooting

| Symptom | Common cause | How to check/resolve |
|---|---|---|
| `Unable to locate credentials` | Local CLI profile/role not configured, or credential source not found | Run `aws configure list --profile dev`; with Identity Center, configure SSO and log in |
| `The SSO session associated with this profile has expired` | Identity Center session expired | Re-run `aws sso login --profile dev` |
| `AccessDenied` / `UnauthorizedOperation` | IAM missing required action/resource; explicit deny from policy/SCP/boundary | Check required action, account, principal, and policies; request least-privilege access via org process |
| `You must specify a region` | Command needs a Regional endpoint with no default value set | Add `--region ap-southeast-1` or configure the profile's Region |
| Console shows resources but CLI returns empty | Different account/role/Region, filter, or query timing | Run `get-caller-identity`, verify Region, remove filters, and re-query |
| `aws: command not found` / `aws is not recognized` | AWS CLI not installed or PATH misconfigured | Check official installer, reopen terminal, run `aws --version` |
| CloudShell fails to start | Missing CloudShell permissions, unsupported Region, session error, or quota | Check CloudShell/Region permissions and Console messages; contact admin if needed |
| Missing CloudShell files from previous session/Region | Saved outside `$HOME` or switched Region; VPC environment has no persistent storage | Verify the right Region, home directory, and storage limits |
| CLI returns only part of a list | Used `--no-paginate` or `--max-items` limit | Check pagination settings, `NextToken`, and pager options |

Use `--debug` only when deep diagnostics are needed and in an appropriate environment: debug output may contain URLs, headers, request metadata, or sensitive details. Always review and redact data before sharing logs.

## 9. Choosing the Right Tool in Real-World Scenarios

| Need | Reasonable starting choice | Reason |
|---|---|---|
| Learning VPC, IAM, EC2 and inspecting configuration fields | Console | Easy to see resource relationships, filters, and settings |
| Already in the Console and want to check account/Region immediately | CloudShell | Has AWS CLI v2, inherits credentials, zero local setup |
| Need to run an inspection command from a personal workstation | AWS CLI + SSO profile | Easy to re-run, keeps command history and profile management |
| Need to collect reports across multiple accounts/Regions | AWS CLI in a managed script | Easy to loop, supports assuming roles and processing JSON output |
| Need repeatable infrastructure deployments with version review | Infrastructure as Code + CI/CD | Declares desired state, supports change review and better lifecycle control |
| Need a long-running, scheduled, or highly reliable process | Dedicated operations service | CloudShell is built for interactive sessions, not durable background jobs |

**Integrated scenario:** An operations team discovers an application cannot connect to an RDS database. They can use the Console to identify the Region, VPC, security groups, and DB state; open CloudShell for quick metadata queries; and run CLI scripts to gather parameters across environments. These steps require initial read permissions and corresponding approval if network rules, database settings, or application restarts are subsequently needed.

## 10. Post-Lesson Self-Check

You have mastered this topic when you can complete this entire sequence in an authorized practice account:

- Explain why the Console, CloudShell, and CLI return the same data for the same principal/Region, yet show different views if the account or filters change.
- Locate the account ID/role in the Console and verify it with `aws sts get-caller-identity`.
- Open CloudShell, confirm `aws --version`, and successfully run at least one `describe-*` command or clearly explain any permission error.
- State the differences between CloudShell's environment Region, the API Region, the IAM Identity Center Region, and AZs.
- Create an SSO-based CLI profile and run read-only commands with explicit `--profile` and `--region` flags.
- Use `--query` to display needed fields and never confuse `--no-cli-pager` with `--no-paginate`.
- Explain why permission to use CloudShell does not grant resource administration rights, and why a `create-*` command can incur costs.

## Official Reference Documentation

1. [AWS Management Console](https://docs.aws.amazon.com/awsconsolehelpdocs/latest/gsg/what-is.html) – Concepts and how to use the Console.
2. [What is AWS CloudShell?](https://docs.aws.amazon.com/cloudshell/latest/userguide/) – Shell environment, authentication, and included tools.
3. [AWS CloudShell: Working in AWS Regions](https://docs.aws.amazon.com/cloudshell/latest/userguide/working-with-aws-cloudshell.html) – Regions, environment variables, and persistent storage.
4. [AWS CloudShell: Service quotas and restrictions](https://docs.aws.amazon.com/cloudshell/latest/userguide/limits.html) – Quotas and storage retention policies.
5. [AWS CloudShell: Managing access with IAM](https://docs.aws.amazon.com/cloudshell/latest/userguide/sec-auth-with-identities.html) – CloudShell permissions and service invocation permissions.
6. [AWS CLI v2: Install or update](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) – OS-specific installation.
7. [AWS CLI v2: Configure IAM Identity Center](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) – Creating SSO profiles and signing in.
8. [AWS CLI: Environment variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html) – Configuration and precedence order.
9. [AWS CLI: Pagination](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-pagination.html) – Retrieving complete multi-page results.

> **Takeaway:** Before every AWS operation, verify **who is calling (principal), which account, which Region, what permissions are required, and whether the command changes resources or costs**. This is the foundation for using compute, storage, database, networking, serverless, monitoring, and recovery services with control.
