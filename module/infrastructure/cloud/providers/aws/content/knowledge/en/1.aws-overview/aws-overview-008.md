# Practice Environment Setup and Naming Conventions

> **Scope:** AWS — AWS Overview  
> **Lesson:** Practice environment setup and naming conventions

When learning AWS, creating a new resource is only the first step. A good practice environment must also let you know **which account you are operating in, in which Region, with which permissions, who owns the resource, and how costs will be tracked**. This lesson builds the shared foundation for continuing hands-on work with IAM, VPC, EC2, S3, databases, integration services, and serverless; these naming, security, monitoring, and cleanup principles also apply when moving from lab exercises to production systems.

## Learning Objectives

After this lesson, you will be able to:

1. Prepare an AWS account or sandbox suitable for learning, configure cost alerts, and secure the account.
2. Distinguish **account**, **Region**, and **Availability Zone (AZ)** scopes as well as the global scope of certain services.
3. Access AWS with an appropriately scoped identity; set up AWS CLI v2 or use AWS CloudShell.
4. Establish resource naming conventions, tags, and a traceable lab directory structure.
5. Create, verify, and clean up a simple S3 resource following the conventions.
6. Recognize common errors involving identity, Region, access permissions, naming collisions, and unexpected costs.

## 1. Designing the Practice Environment Scope

A minimal AWS learning environment should include the following components:

~~~mermaid
flowchart TD
    A[AWS account / sandbox] --> B[Identity and access control]
    A --> C[Cost tracking and alerts]
    A --> D[Practice Region]
    D --> E[AZs and networking / compute resources]
    D --> F[S3, databases, Lambda, and other services]
    B --> E
    B --> F
    E --> G[Consistent names, tags, logs, resource cleanup]
    F --> G
~~~

### 1.1. Choosing a Learning Account

**Prefer a dedicated AWS account for practice** or a sandbox provisioned by your organization. Separate your learning environment from production so experiments cannot affect systems serving live users.

- **Personal account:** verify sign-up steps, payment methods, and current promotional/credit terms in the AWS Console. Never assume every resource labeled "Free Tier" is free or automatically capped.
- **Company/school sandbox:** use the exact account, role, Region, and budget policy assigned to you. If you lack Billing or IAM admin permissions, ask an administrator to configure those settings.
- **AWS Organizations / multi-account:** if your organization provides a dedicated sandbox account, use that account. Service Control Policies (SCPs) can restrict actions even when an IAM role allows them.

Record environment metadata using **codes or environment labels**, never writing passwords, access keys, MFA secrets, or billing details into a repository:

| Attribute | Example used in lesson | Meaning |
|---|---|---|
| Project | **aws-lab** | Identifies the course's group of resources |
| Environment | **dev** | Distinguishes dev, test, prod, sandbox environments |
| AWS account | **assigned sandbox** | Ownership and billing boundary |
| Primary Region | **ap-southeast-1** | Singapore Region, used consistently for illustrations |
| CLI profile | **aws-lab-dev** | Selects the right identity when running commands |
| Owner | **team-cloud** | Responsible contact group, avoiding personal data |
| Tools | AWS Console + CLI v2 | Visual management and repeatable operations |

**Note on Region:** **ap-southeast-1** is only an illustrative choice; prioritize a Region approved by your organization that supports the services you need to learn and matches latency, data residency, and cost requirements. Pricing and service availability vary by Region.

### 1.2. Account, Region, and AZ Are Not the Same Scope

| Scope | Meaning | Practice example / implication |
|---|---|---|
| AWS account | Administrative and billing boundary | Verify the account before creating or deleting resources |
| Region | Geographic area where most services are deployed | VPC/EC2/RDS belong to a Region; switching Regions can make the Console look like resources "disappeared" |
| AZ | One or more independent data centers within a Region, engineered to isolate faults | Subnets live in one AZ; place resources across multiple AZs when learning high availability |
| Global or special-scope services | Do not follow the exact same Region/AZ model | IAM is global; S3 buckets require unique names within the applicable namespace, yet each bucket is created in one Region |

**Do not equate AZ letters across accounts.** A name like **ap-southeast-1a** can map to different physical AZs in different accounts. When accurately comparing AZs across multiple accounts, use the **AZ ID** (e.g., **apse1-az1** format) where supported by the service.

There is no need to create a VPC, NAT Gateway, or RDS in this introductory lesson. Those services have more complex billing and lifecycle characteristics; this first exercise only checks identity, Region, and a simple S3 bucket.

## 2. Setting Up Safety Guardrails Before Creating Resources

### 2.1. Securing the Root Account and Managing Identity

The **root user** has extremely high privileges. Use root only for initial account setup and specific mandatory administrative tasks, never for daily learning activities.

1. Enable **MFA** for the root user and protect account recovery methods; do not create access keys for root.
2. Fill in contact, security, and billing details per account policy.
3. For organizations, prefer federated login or **IAM Identity Center** to obtain permissions via roles/permission sets. For personal environments, choose a login method with MFA and permissions scoped to the lab.
4. Apply **least privilege**: allow only the APIs, resources, and Regions needed. Broad administrative rights belong only to people actively administering the sandbox.
5. Never put access keys, secret keys, session tokens, passwords, private keys, or `.env` files containing secrets into Git, screenshots, or lesson notes.

AWS authenticates API requests by identity (principal) and evaluates permissions against applicable policies. Learners may see **AccessDenied** even when command syntax is valid; the cause may be an IAM policy, SCP, permissions boundary, resource policy, or another security condition.

### 2.2. Cost Alerts Before You Start

Open **Billing and Cost Management** in the AWS Console (requires Billing access permissions), then:

1. Check the cost overview page, active credits/promotions, and the account's Billing access policy.
2. Create an **AWS Budget** for monthly cost with an appropriate threshold, such as **5 USD/month** for a small sandbox; configure alerts at multiple thresholds (e.g., 50%, 80%, 100%) sent to a notification address you monitor.
3. If available, consider **Cost Anomaly Detection** for alerts on unusual spending.
4. Inspect costs by **Service**, **Region**, and **Tag** in Cost Explorer once data is available; cost allocation tags may need to be activated and take time to populate.
5. Build the habit of **cleaning up resources after every study session**. For services billed hourly or by capacity, setting cleanup reminders is helpful.

> **Important warning:** AWS Budgets is a **monitoring and notification** mechanism; it does not by default block resources or impose a hard spending cap. Charges can accrue before an alert fires. Even with credits/promotions, read the pricing page and eligibility terms for each specific service and Region.

Resources commonly forgotten in advanced labs include continuously running EC2 instances, EBS volumes/snapshots, Elastic IPs or public IPv4 addresses, NAT Gateways, load balancers, RDS instances, long-retained logs, and S3 data. Cost-management habits should start on day one.

### 2.3. Logs and Traceability

- **CloudTrail Event history** lets you view recent management events in the account within AWS's supported window; longer retention or broader capture requires configuring a trail or corresponding features and checking costs.
- **CloudWatch** supports service metrics, logs, and alarms; log groups can continue storing data and accruing charges after a workload has stopped.
- **Tags** and **names** help trace a resource's purpose; they do not replace IAM, CloudTrail, or security policies.

## 3. Preparing Your Working Tools

### 3.1. Choosing AWS Console, CloudShell, or AWS CLI

| Method | When appropriate | Notes |
|---|---|---|
| AWS Management Console | Getting familiar with services, viewing settings visually | Verify account name and Region before every action |
| AWS CloudShell | Running AWS CLI directly in the browser without local installation | Uses logged-in identity permissions; check CloudShell Region and environment limits |
| AWS CLI v2 on local machine | Repeating actions, scripting, and testing configs | Requires installing the CLI and configuring credentials securely |
| IaC (Terraform/CloudFormation/CDK) | Later lessons requiring reproducible deployments | Watch state files, deployment permissions, and stack teardown |

On a personal machine, install **AWS CLI v2** following AWS's official guide, then open a new terminal and verify:

~~~bash
aws --version
~~~

If the command is not recognized, check the installation steps and your OS **PATH** variable. You can use Git and a code editor (VS Code or equivalent) to store scripts and notes; you do not need to install an SDK just for this lesson.

### 3.2. Signing In with IAM Identity Center (When Provided)

If your organization provides IAM Identity Center and an access portal URL, configure an interactive profile:

~~~bash
aws configure sso --profile aws-lab-dev
aws sso login --profile aws-lab-dev
aws sts get-caller-identity --profile aws-lab-dev
~~~

During setup, enter the **SSO start URL or issuer URL, SSO Region, AWS account, role, and default Region** exactly as provided by your administrator. The profile name **aws-lab-dev** is only a local alias; it does not determine permissions on AWS. When the session expires, run **aws sso login** again.

If using **CloudShell**, you can skip local SSO configuration and start directly with **aws sts get-caller-identity**. Never create long-lived access keys just because you haven't set up SSO yet.

### 3.3. Fixing Profile and Region for the Practice Session

The example below uses **Bash** (Linux/macOS or another Bash environment):

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity
aws configure list
aws ec2 describe-availability-zones \
  --region ap-southeast-1 \
  --query 'AvailabilityZones[].{Name:ZoneName,Id:ZoneId,State:State}' \
  --output table
~~~

If using **PowerShell on Windows**, set the two session environment variables as follows:

~~~powershell
$env:AWS_PROFILE = "aws-lab-dev"
$env:AWS_DEFAULT_REGION = "ap-southeast-1"

aws sts get-caller-identity
aws configure list
~~~

Inspect the **aws sts get-caller-identity** output to confirm **Account** and **Arn** match your intended sandbox. This is a mandatory check before creating, modifying, or deleting any resource. If the CLI and Console show different results, re-check profile, role, and Region. Avoid posting raw outputs containing account identifiers or ARNs in public places unnecessarily.

## 4. AWS Resource Naming Conventions

Naming conventions serve two goals: helping humans see what a resource does and helping automation target the right resource. Conventions must be simple, consistent, and compliant with each service's constraints.

### 4.1. Basic Naming Structure

Proposed default template:

~~~text
<project>-<environment>-<component>[-<purpose>][-<unique-suffix>]
~~~

Examples used throughout the lesson:

~~~text
aws-lab-dev-network
aws-lab-dev-app
aws-lab-dev-data
aws-lab-dev-artifacts-<unique-suffix>
~~~

| Segment | Convention | Example |
|---|---|---|
| Project | Short, stable project name | **aws-lab** |
| Environment | Consistent set: dev, test, prod, sandbox | **dev** |
| Component | Business or technical function | **api**, **web**, **network**, **data**, **logs** |
| Purpose | Add only when needed to distinguish resources in the same group | **private**, **public**, **backup** |
| Unique suffix | Use only when global/namespace uniqueness or collision avoidance is required | Random string containing no secrets |

**Recommended guidelines:**

- Prefer lowercase letters, digits, and hyphens (**kebab-case**) for team-chosen names, unless service rules require otherwise.
- Put stable segments before variable ones; avoid vague names like **test1**, **new-v2-final**, **my-server**.
- Never put passwords, tokens, personal emails, customer data, or sensitive info into names or tags.
- Avoid embedding dates in every resource name. Add timestamps only when genuinely needed to distinguish short-lived deployments.
- Check length limits, allowed characters, uniqueness scope, and rename rules **for each service** before creating resources.

### 4.2. Not Every Service Uses Names the Same Way

| Service / resource | How naming applies | What to remember |
|---|---|---|
| VPC, subnet, EC2 instance | Assign a **Name tag**, e.g., **aws-lab-dev-network**, **aws-lab-dev-subnet-public-1** | Actual IDs remain AWS-generated IDs (`vpc-...`, `subnet-...`, `i-...`) |
| S3 bucket | **aws-lab-dev-artifacts-<unique-suffix>** | Bucket names must meet S3 DNS rules and be unique in the applicable namespace; buckets are created in one Region |
| Lambda function | **aws-lab-dev-api** | Function names appear in the ARN and have specific naming limits |
| IAM role | **aws-lab-dev-deployer** | IAM is global within an account; role names and paths have dedicated rules |
| RDS DB instance | **aws-lab-dev-db** | DB identifiers have specific character/length rules; instances can incur charges while existing |
| CloudWatch log group | Follow service standard or **/aws-lab/dev/api** | Some log groups are auto-created by services under fixed conventions |
| S3 object key | **raw/2026/11/sample.json** | "Folders" in S3 are primarily prefixes in object keys, not traditional filesystem directories |

Example for **S3 general purpose bucket** names: 3–63 characters, lowercase letters, numbers, hyphens, or dots under specific constraints; avoid dots in labs to prevent compatibility issues. S3 has multiple bucket types with different naming rules; this lesson uses general purpose buckets. **Once created, a bucket name cannot be changed directly**: you normally create a new bucket and migrate data.

For subnets/AZs, you can name them **aws-lab-dev-subnet-public-az1**; remember that **az1** is only a project diagram label and must map explicitly to an actual AZ/AZ ID.

### 4.3. Tags Are for Management, Not Just Display

Names answer "what is this resource?"; tags help answer "who owns it, what is it for, which environment does it belong to, and when can it be cleaned up?". Recommended tag set:

| Tag key | Example value | Purpose |
|---|---|---|
| **Project** | **aws-lab** | Group resources by project |
| **Environment** | **dev** | Distinguish environment criticality |
| **Owner** | **team-cloud** | Responsible team or department |
| **ManagedBy** | **manual** | Distinguish manual, terraform, cloudformation, etc. |
| **Purpose** | **learning** | Reason the resource exists |
| **ExpiresOn** | **YYYY-MM-DD** | Target date to review/clean up resource |
| **CostCenter** | **training** | Optional: allocate costs by business unit |

Tag keys and values are **case-sensitive**: **Environment** differs from **environment**. Standardize one casing across the entire course. Tags have limits and uneven support across services; not every resource supports tagging or tag filtering the same way.

**ExpiresOn does not automatically delete resources.** Automated cleanup requires a separately designed, authorized, and tested mechanism. To use tags in cost reports, you may also need to activate **cost allocation tags** in Billing. Access-control tags must also be protected so users cannot modify them to bypass policies.

### 4.4. Naming Conventions in Code and Documentation

Sample repository structure for AWS hands-on labs:

~~~text
aws-lab/
├── README.md
├── .gitignore
├── docs/
│   ├── account-and-region.md
│   └── naming-conventions.md
├── scripts/
│   ├── verify-environment.sh
│   └── cleanup-lab.sh
└── infrastructure/
    └── examples/
~~~

In **README.md**, document the example profile, target Region, minimum permissions, resources created by the lab, potential costs, and cleanup steps. In scripts, use variables instead of hardcoding accounts/Regions in many places; in IaC, define shared default tags once and propagate them to supported resources.

Example **.gitignore** protecting files likely to hold sensitive data:

~~~gitignore
.env
.env.*
!.env.example
*.pem
*.key
.aws/
.terraform/
*.tfstate
*.tfstate.*
~~~

**.gitignore** does not replace secret scanning; if sensitive data has already been committed, revoke/rotate those credentials and remediate repository history using secure procedures.

## 5. Practice: Creating and Cleaning Up an S3 Bucket by Convention

This lab verifies **the right account, right Region, right permissions, and right naming/tagging conventions** all at once. Use test data containing no sensitive information. S3 can incur charges for storage, requests, and data transfer; complete the cleanup step immediately after the lab.

**Prerequisites:** Working AWS CLI v2, logged-in **aws-lab-dev** profile (or running in CloudShell), and an identity permitted to create/read/delete buckets, manage public access blocks, and manage tags. The commands below are written for **Bash**; in PowerShell, adapt variable syntax accordingly. If using **CloudShell** without an **aws-lab-dev** profile, omit the **export AWS_PROFILE=aws-lab-dev** line in Step 1 to use your active Console session identity.

### Step 1 — Verify Identity and Pick a Unique Name

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity

REGION=ap-southeast-1
BUCKET="aws-lab-dev-artifacts-$(date +%s)-$RANDOM"
echo "$BUCKET"
~~~

Match the account in the **sts get-caller-identity** output against your registered sandbox. The timestamp/random suffix here simply reduces collision probability; if the name is already taken, generate another. Never include sensitive information in a bucket name because bucket names can appear in URLs and logs.

### Step 2 — Create the Bucket in the Selected Region

~~~bash
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --create-bucket-configuration "LocationConstraint=$REGION"
~~~

This example uses **ap-southeast-1**. For **us-east-1**, general purpose bucket creation syntax differs: the **--create-bucket-configuration** parameter is typically omitted. Never change the Region ad hoc without updating both the command and environment variables.

### Step 3 — Protect the Bucket and Apply Tags

New S3 buckets already have important security defaults, yet we explicitly configure **Block Public Access** so learners can observe the desired state:

~~~bash
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

aws s3api put-bucket-tagging \
  --bucket "$BUCKET" \
  --tagging '{"TagSet":[{"Key":"Project","Value":"aws-lab"},{"Key":"Environment","Value":"dev"},{"Key":"Owner","Value":"team-cloud"},{"Key":"ManagedBy","Value":"manual"},{"Key":"Purpose","Value":"learning"}]}'

aws s3api get-public-access-block --bucket "$BUCKET"
aws s3api get-bucket-tagging --bucket "$BUCKET"
~~~

New S3 general purpose buckets enable Block Public Access and **SSE-S3** server-side encryption by default; you should still verify the actual configuration, account-level settings, and organizational encryption requirements. Never disable public access just to "make testing easier." When studying data-sharing patterns, design access permissions intentionally.

### Step 4 — Write, List, and Read Back an Object

~~~bash
printf 'Hello AWS lab!\n' > lab-hello-aws.txt

aws s3 cp ./lab-hello-aws.txt "s3://$BUCKET/demo/lab-hello-aws.txt"
aws s3 ls "s3://$BUCKET/demo/"
aws s3 cp "s3://$BUCKET/demo/lab-hello-aws.txt" ./lab-hello-aws-downloaded.txt
~~~

Check the contents of the downloaded file. Notice:

- **Bucket** is the container for objects in the selected Region.
- **Object key** is **demo/lab-hello-aws.txt**; the **demo/** portion is a prefix used to group objects.
- **Bucket tags** describe the bucket; objects have separate object tagging mechanisms if a workload requires object-level management.

### Step 5 — Clean Up Resources and Verify

~~~bash
aws s3 rm "s3://$BUCKET/demo/lab-hello-aws.txt"

aws s3api delete-bucket \
  --bucket "$BUCKET" \
  --region "$REGION"
~~~

Deleting a bucket requires the bucket to be **empty**. If additional objects were uploaded, versions were created, or other features were enabled, inspect and clean them up appropriately before deleting the bucket. Afterward, check the bucket list in the Console or via CLI to ensure the lab resource is gone; you can remove the two local test files once no longer needed.

**Expected outcome:** you verified your identity, created a uniquely named bucket in the chosen Region, confirmed Block Public Access, applied tags, wrote/read an object, and cleaned up the bucket. If you encounter errors, use the troubleshooting table below before retrying.

## 6. Extending Conventions to Upcoming AWS Lessons

When moving from S3 to other services, keep the same **Project**, **Environment**, **Owner**, and naming structure, while always checking each service's specific characteristics and limits.

| Upcoming practice area | Conventions or checks to maintain |
|---|---|
| IAM / Identity Center | Use roles and temporary sessions; verify principal; name roles by project + environment + function |
| VPC / networking | Name VPCs, subnets, route tables, and security groups by project + environment + purpose; document CIDR and AZ maps clearly |
| EC2 / compute | Apply Name and management tags; check instance types, IPv4/EBS, and stopped/terminated state after labs |
| S3 / storage | Choose unique bucket names and Region; private by default, verify encryption, retention, lifecycle, and versioning |
| RDS / databases | Isolate test environments and data; budget for instance/storage/backup fees, clean up snapshots when appropriate |
| Lambda / API / integration | Name functions, queues, and topics consistently; track requests, duration, retries, and CloudWatch Logs |
| Monitoring / recovery | Define log retention, alarms, and recovery tests; ensure restored resources are also named and tagged |
| IaC deployments | Define project, environment, and region variables; manage state and create/destroy lifecycles cleanly |

In availability lessons, you will learn how to place subnets and workloads across multiple appropriate AZs, design backups, and test recovery. **Multiple AZs do not automatically guarantee application recovery** if dependencies or data still contain single points of failure.

## 7. Common Errors and Troubleshooting

| Symptom | Possible cause | How to inspect and resolve |
|---|---|---|
| **Unable to locate credentials**, **ExpiredToken** | Not signed in or session expired | Check profile; re-authenticate with **aws sso login --profile aws-lab-dev** |
| **AccessDenied**, **UnauthorizedOperation** | Missing IAM permissions, SCP, or related policy | Verify ARN from STS; read the denied API action and request exact required permissions from admin |
| **BucketAlreadyExists** | S3 name already taken in the applicable namespace | Pick a new name with a more unique suffix; never attempt to operate on someone else's bucket |
| **IllegalLocationConstraintException** | Region configuration mismatch during bucket creation | Check **--region** and **LocationConstraint**; note the **us-east-1** exception |
| Cannot see EC2/VPC/RDS in Console | Viewing a different Region or account | Check the Region selector, account, profile, and UI filters |
| Deleting S3 bucket fails with **BucketNotEmpty** | Objects or object versions still remain | List objects/versions and clean them up properly before retrying |
| Charges continue after stopping workload | Leftover EBS, public IPv4, NAT Gateway, RDS, logs, snapshots, etc. | Inspect Billing/Cost Explorer; list resources by Region and tag; clean up remaining resources |
| Tags do not appear in Cost Explorer | Cost allocation tags not activated or data not yet updated | Check cost allocation tags settings and data refresh delay |

When troubleshooting errors, record the **timestamp, profile, Region, service, action, and error message with sensitive information redacted**. This speeds up reproduction without exposing credentials.

## 8. Completion Checklist and Per-Lab Workflow

Before starting a new lesson:

- [ ] Using the right AWS account/sandbox, principal, and Region.
- [ ] Root user protected with MFA; practice account uses properly scoped permissions.
- [ ] Budget alerts configured and you know where to check costs.
- [ ] Consistent project/environment names and tag set defined.
- [ ] Know which resources the lab creates, what charges may apply, and how to delete them.

Before finishing:

- [ ] Documented key APIs, configurations, and observations in lesson notes.
- [ ] Stopped or deleted created resources and checked companion resources (storage, network, logs, snapshots).
- [ ] Re-checked all Regions used; review Billing once updated data arrives.
- [ ] No files containing credentials or sensitive data committed.
- [ ] Reviewed notes: are resource names, tags, and design decisions consistent?

**Self-check comprehension questions:**

1. Why does an EC2 **Name tag** differ from the AWS-assigned instance ID?
2. Why are two accounts with an AZ name ending in **1a** not guaranteed to be in the same physical AZ?
3. If you set a 5 USD Budget, does AWS guarantee all charges will stop at 5 USD?
4. When a CLI command returns **AccessDenied**, which identity and policies should you verify?
5. When deleting EC2 or RDS, which companion resources or leftover data should you check?

You have completed this lesson when you can explain the questions above and execute the full **verify → create → tag and secure → test → clean up** cycle in your practice account.

## Official AWS Reference Documentation

- [AWS Global Infrastructure — Regions and Availability Zones](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/)
- [AWS IAM — Security best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [AWS CLI v2 — Installation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [AWS CLI — Configure IAM Identity Center](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [AWS Budgets — Managing costs](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [S3 general purpose bucket naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html)
- [AWS tagging best practices](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html)

**Reminder:** Pricing, promotional terms, Console UI, and available services are subject to change. Before starting a new lab, check current AWS documentation and pricing for your account and Region.
