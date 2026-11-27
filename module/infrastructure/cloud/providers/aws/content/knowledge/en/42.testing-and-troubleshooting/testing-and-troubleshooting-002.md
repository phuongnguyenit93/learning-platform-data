# Sandbox Accounts, Test Data, and Environment Isolation

In AWS, a sandbox is an environment with controlled access, data, costs, and lifecycle so development teams can experiment without affecting other workloads. A sandbox is not a standalone AWS service. It is typically built using dedicated AWS accounts, AWS Organizations, IAM Identity Center, Service Control Policies (SCPs), dedicated VPCs, prepared test data, and automated resource provisioning/cleanup workflows.

An AWS account is a critical boundary for isolating resources, access permissions, billing, and many service quotas. Therefore, production environments should be separated from development, test, and sandbox environments using separate accounts whenever security requirements or blast radius warrant it. AWS Control Tower and Account Factory help standardize account creation; AWS Organizations manages Organizational Units (OUs) and guardrails; IAM Identity Center issues temporary permissions; and AWS Budgets and IaC help track costs, recreate environments, and clean them up.

This lesson covers how to design sandboxes in the AWS ecosystem, how to choose account and network boundaries, how to generate safe test data, how to control access and costs, and how to decommission a temporary environment without leaving orphaned resources behind.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Explain the purpose of a sandbox and distinguish a sandbox from dev, test, staging, and production.
- Explain why an AWS account is a critical isolation boundary.
- Design an AWS Organizations structure with OUs and workload accounts.
- Use AWS Control Tower Account Factory to provision accounts against a baseline.
- Grant developer access using IAM Identity Center and permission sets.
- Explain the role, limitations, and testing approach for SCPs.
- Isolate VPCs, subnets, routes, security groups, endpoints, and cross-account connectivity.
- Choose synthetic, masked, or anonymized data for testing.
- Use AWS Glue DataBrew or AWS DMS when sensitive data processing is required.
- Understand the risks of cloning or restoring production data into test environments.
- Separate secrets, KMS keys, databases, and buckets per environment.
- Standardize environments using CloudFormation, CDK, or Terraform.
- Set budgets, alerts, tags, and quota limits for sandboxes.
- Create automated expiration and resource cleanup workflows.
- Build a checklist for checks before, during, and after an experiment.

## 2. What Is a Sandbox and When Should You Use One?

A sandbox is a testing environment with constrained permissions and resources. Users can create, modify, and delete resources to learn, build prototypes, test service integrations, or experiment with infrastructure changes.

Common scenarios:
- Learning a new AWS service such as Lambda, DynamoDB, S3, or EventBridge.
- Prototyping a proof of concept (PoC) architecture.
- Testing IAM policies, SCPs, or network configurations.
- Running integration tests across multiple services.
- Testing migrations, schema changes, or data pipelines.
- Trying a new application version before promoting it to staging.
- Training new engineers without granting access to production.

A sandbox needs explicit limits:
- Who is allowed to create and delete resources?
- Which Regions and services are permitted?
- What data is allowed inside?
- What is the expected maximum spend?
- How long does the environment exist?
- Who is responsible for cleanup?
- Which resources are retained after the experiment?

A sandbox account can still incur real charges. EC2, NAT Gateways, RDS, EBS, snapshots, public IPv4 addresses, data transfer, and many other services continue billing when users forget to stop or delete resources.

## 3. Distinguishing Environments

| Environment | Purpose | Data | Access | Lifecycle |
|---|---|---|---|---|
| Local | Unit tests, logic checks without real cloud resources | Small fixtures, synthetic | Developer on workstation | Per work session |
| Sandbox | Learning, PoCs, testing services or architectures | Synthetic or sanitized data | Constrained experimental access | Temporary, with TTL |
| Development | Feature development and continuous integration | Synthetic, fixtures, or masked | Developers and pipelines | Maintained per sprint |
| Test/QA | Functional, regression, and integration testing | Managed test suites | QA and CI/CD | Per release |
| Staging | Near-production verification, release rehearsals | Representative synthetic/masked data | Release and operations teams | Per release or long-lived |
| Production | Serving real users | Real data per policy | Restricted, approval-gated | Continuous |

Not every organization needs a separate account for every environment. However, account-level separation is strongly recommended when workloads handle sensitive data, have compliance requirements, require different operational permissions, or have a large blast radius.

A small team might use a single non-production account for dev/test with separate VPCs and roles. As the number of teams, data sensitivity, or risk grows, split into separate accounts per workload or environment. Production and staging should have separate accounts with distinct controls.

## 4. Why Isolate Using AWS Accounts?

An AWS account is a resource container and an isolation boundary for access control, billing, and many service quotas. Separating accounts helps:

- Reduce the blast radius when a developer accidentally creates or deletes resources.
- Separate costs by project or workload.
- Scope permissions and policies per environment.
- Manage service quotas and API request rates independently across many services.
- Easily apply different guardrails for sandbox, non-production, and production.
- Reduce the risk of test jobs or scripts impacting production.
- Easily close an expired sandbox account.

For example, an accidental database deletion command executed in a sandbox account will not directly delete the database in the production account without explicit cross-account permissions.

However, an account boundary does not automatically prevent all cross-account access. If IAM role trusts, resource policies, KMS key policies, VPC peering, Transit Gateway, shared resources, or shared credentials exist, two accounts can still interact. Therefore, every cross-account connection must be explicitly designed and authorized.

### 4.1 When Is One Account Not Enough?

Consider splitting into additional accounts when:
- Development teams have broad AdministratorAccess permissions.
- Test data has a different sensitivity level than staging data.
- An experiment could generate heavy load or high costs.
- You need to test guardrails, account vending, or landing zones.
- Compliance or audit separation is required.
- One workload requires access to different services than another.
- You need to prevent one team from exhausting another team's quotas.

Do not create new accounts solely to rename an environment if there is no clear governance benefit. Too many accounts without automation increase operational overhead for logging, identity, billing, and baselines.

## 5. Designing AWS Organizations and OUs

AWS Organizations centrally manages multiple AWS accounts within an organization. OUs group accounts with similar governance requirements. SCPs attach to the root, an OU, or an account to define the maximum permissions principals in member accounts can use.

Reference structure:

~~~text
AWS Organization
|
+-- Root
    |
    +-- Security OU
    |   +-- Log Archive account
    |   +-- Audit / Security account
    |
    +-- Infrastructure OU
    |   +-- Network account
    |   +-- Shared Services account
    |
    +-- Sandbox OU
    |   +-- Sandbox-Training account
    |   +-- Sandbox-Team-A account
    |
    +-- NonProduction OU
    |   +-- Development account
    |   +-- Test account
    |   +-- Staging account
    |
    +-- Production OU
        +-- Workload-Production account
~~~

Meaning:
- **Management account:** manages the organization and billing; access must be tightly restricted.
- **Log Archive account:** centrally stores logs according to organizational architecture.
- **Audit/Security account:** dedicated to auditing and security operations.
- **Infrastructure OU:** holds networking, shared services, or shared platform components.
- **Sandbox OU:** holds experimental accounts with dedicated quotas, budgets, and guardrails.
- **NonProduction OU:** holds dev/test/staging environments.
- **Production OU:** holds workloads serving real users with stricter policies.

You do not have to use the exact OU names from the example. Design OUs around workload groupings and required controls rather than organizational charts.

### 5.1 Different Guardrails per OU

Examples:
- Sandbox OU allows creating many types of experimental resources while restricting Regions, sensitive services, and permissions to alter audit controls.
- NonProduction OU permits automated CI/CD deployments and access to test data.
- Production OU requires change approvals, dedicated deployment roles, and restricted operational access.
- Security OU holds centralized observability and audit access.

AWS Control Tower provides a landing zone and controls for governing a multi-account environment. Account Factory supports provisioning new accounts according to registered configurations. Account Factory Customization or Account Factory for Terraform (AFT) can help automate baselines and custom configurations as needed.

## 6. Provisioning Sandbox Accounts with AWS Control Tower

Account Factory is the standard way to create or update member accounts in an AWS Control Tower landing zone. Operators select the OU, account email, and access configuration. Organizations can automate account provisioning using APIs, Lambda, or AFT.

Suggested provisioning workflow:

1. User submits a sandbox request with project, owner, purpose, and duration.
2. System verifies the requester is authorized to create a sandbox.
3. Select the Sandbox OU and appropriate baseline.
4. Provision the account via Account Factory.
5. Assign users/groups in IAM Identity Center.
6. Apply SCPs, logging, Config, and security baselines.
7. Create budgets, standard tags, and expiration metadata.
8. Deploy the required VPC, roles, and templates.
9. Deliver account access to the owner.
10. Record account ID, owner, expiry date, and cost center.

A sandbox account should track governance metadata:
- Account alias or display name.
- Account ID.
- Project/experiment ID.
- Owner/team.
- Request ticket or creation reason.
- Creation date and expiration date.
- Budget and alert recipients.
- OU and baseline.
- Permitted Regions.
- Permitted data classification.
- Renewal or account closure process.

Do not create accounts by sharing root credentials. Root account emails, MFA, and recovery processes must be managed centrally.

## 7. Managing Access with IAM Identity Center

AWS IAM Identity Center lets you grant access across multiple AWS accounts using users/groups and permission sets. This is the right way for developers to access sandboxes without creating long-lived IAM users inside each account.

A simple model:

| Group | Sandbox | Development/Test | Production |
|---|---|---|---|
| Developer | Scoped power user | Deploy/dev role | Read-only or no access |
| QA | Service testing permissions | Test role | Read-only when needed |
| Platform | Task-based admin | Admin/deploy | Platform operations role |
| Security | Audit/read-only and security tools | Audit | Security audit |
| CI/CD | Scoped deploy role | Deploy role | Approval-gated production deploy role |

Permission sets can be based on managed policies or custom policies. Do not assign AdministratorAccess to every developer by default. Grant only the necessary services, resources, and actions; separate deployment permissions from organization administration permissions.

Principles:
- Use federation and temporary credentials.
- Enable MFA.
- Do not share access keys among team members.
- Do not embed credentials in source code or AMI/container images.
- Use dedicated roles for CI/CD.
- Set appropriate session durations.
- Revoke assignments when members leave the team or the sandbox expires.
- Use CloudTrail to audit API activity.

Use the root user only for tasks that strictly require root. Protect root with MFA and do not create root access keys.

## 8. SCPs: Guardrails for Sandbox Accounts

An SCP is an AWS Organizations policy used to define the maximum permissions available to principals in member accounts. SCPs do not grant permissions. An API call succeeds only when allowed by IAM/resource policies and not denied by any applicable SCP.

Example SCP for a Sandbox OU to protect organization membership and audit controls:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PreventLeavingOrganization",
      "Effect": "Deny",
      "Action": [
        "organizations:LeaveOrganization",
        "account:CloseAccount"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ProtectAuditConfiguration",
      "Effect": "Deny",
      "Action": [
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail",
        "config:StopConfigurationRecorder",
        "config:DeleteConfigurationRecorder"
      ],
      "Resource": "*"
    }
  ]
}
~~~

This is an illustrative guardrail to review and test in a dedicated account/OU. Before rolling it out broadly, verify service integrations, the CloudTrail organization trail, the AWS Config recorder, and required automation.

Important limitations:
- SCPs do not grant IAM permissions.
- SCPs do not apply to the management account.
- SCPs do not restrict permissions attached directly to service-linked roles.
- SCPs affect even the root user in member accounts.
- A Deny at any level (root/OU/account) along the hierarchy path takes effect.
- An overly broad SCP can block pipelines, logging, or cleanup workflows.

Test SCPs in a policy staging account/OU first. Verify create, update, delete, logging, backup, and operational support tasks.

### 8.1 Example Region-Restriction Policy

A sandbox might only be allowed to create resources in organization-approved Regions. When writing SCPs using the `aws:RequestedRegion` condition, note that some global services and APIs are not bound to Regions in the same way as regional resources. Maintain an exception list of services based on your actual architecture, test in an isolated account, and validate foundational services before applying.

Do not copy a deny-all-except-region policy to the organization root without evaluating its impact on IAM, billing, support, CloudFront, Route 53, IAM Identity Center, and global endpoints.

## 9. Network Isolation Between Environments

Account separation is a critical isolation layer; network isolation is an additional layer. A dedicated VPC per workload/account helps control routes, security groups, subnets, and connectivity.

A reference sandbox design:
- Dedicated VPC CIDR that does not overlap with other VPCs.
- Public subnets reserved only for components needing public access, such as NAT Gateways or load balancers.
- Private subnets for applications and databases.
- Security groups opening ports only from required sources.
- VPC endpoints for S3, DynamoDB, and supported services to reduce Internet-bound traffic.
- Controlled egress through NAT or a proxy.
- No default peering between sandbox and production.
- Use Transit Gateway or a shared network account when approved connectivity is required.

Example layout:

~~~text
Sandbox Account
  |
  +-- Sandbox VPC
       |
       +-- Public subnet
       |     +-- NAT Gateway (if needed)
       |
       +-- Private app subnet
       |     +-- EC2 / ECS / Lambda ENI (if Lambda is VPC-attached)
       |
       +-- Private data subnet
       |     +-- RDS / ElastiCache
       |
       +-- VPC endpoints
             +-- S3
             +-- DynamoDB
             +-- Systems Manager
~~~

Do not reuse the same CIDR across all sandboxes if VPC-to-VPC connectivity might be needed later. CIDR overlap complicates peering, Transit Gateway, or VPN setups.

### 9.1 Controlling Cross-Account Connectivity

If a sandbox needs to read artifacts or datasets in another account:
- Create a cross-account role with a trust policy specifying the allowed principals.
- Use S3/KMS resource policies to restrict buckets, prefixes, and keys.
- Open network routes only when strictly necessary.
- Use endpoint policies to restrict service access where appropriate.
- Audit and periodically review trust relationships.
- Do not grant access to production databases merely for testing convenience.

### 9.2 Security Groups and Network ACLs

Security groups are stateful and are commonly used to restrict traffic at the network interface level. Network ACLs are stateless and apply at the subnet level. Prefer security groups with small, clear rules; use NACLs for additional subnet-level control requirements.

Avoid `0.0.0.0/0` rules on SSH/RDP or database ports. When administrative access is needed, prefer AWS Systems Manager Session Manager instead of opening management ports to the Internet.

## 10. Isolating Data and Storage Resources

Test data should be separated from production data across multiple layers:
- Separate accounts and buckets/databases.
- Separate KMS keys or environment-specific key policies.
- Separate IAM roles and resource policies.
- Separate secrets and connection strings.
- Backups/snapshots with clear owners and retention.
- No shared production database endpoints.
- No automatic replication of sensitive data to sandboxes.
- Never let sandbox developers read production buckets via wildcard policies.

Example bucket naming convention:
- company-dev-app-data
- company-test-app-data
- company-staging-app-data
- company-prod-app-data

Bucket naming is only a convention. Real security relies on accounts, IAM, bucket policies, KMS key policies, encryption, and network controls.

### 10.1 Separating KMS Keys

Use separate customer managed keys per environment:
- Dev key only for dev roles.
- Test key only for test pipelines.
- Staging key only for staging workloads.
- Production key only for production workloads and security-approved roles.

Do not share one overly broad key policy across all environments. When sharing data cross-account, both IAM permissions and appropriate key policies are required; granting S3 access alone does not allow a principal to decrypt KMS-encrypted objects.

## 11. Choosing Test Data: Synthetic, Masked, or Anonymized?

Test data can be divided into three categories:

| Type | Description | Pros | Risks/Limitations |
|---|---|---|---|
| Synthetic | Generated via generators or fixtures, not taken directly from real users | Controllable, reproducible, low PII risk | Must create realistic data distributions and relationships |
| Masked | Replaces part or all of sensitive values with other values | Preserves some structure and data types | May still be identifiable if masking is insufficient |
| Anonymized | Processed so individuals can no longer be reasonably identified | Suitable for analytics/testing when done properly | Hard to reverse; requires assessing re-identification risk |

Prefer synthetic data for sandboxes. If production-like data is required, evaluate using masked/anonymized datasets before any data leaves the production account.

Do not treat simply renaming columns, dropping names, or replacing emails with random strings as complete anonymization. Data can still be re-identified via addresses, timestamps, linked identifiers, behaviors, or combinations of fields.

### 11.1 Synthetic Data

Synthetic data is generated from schemas, business rules, and statistical distributions. A good dataset should preserve:
- Data types and constraints.
- Primary/foreign key relationships.
- Cardinality and value distributions.
- Null frequencies and missing fields.
- Boundary values: min/max, empty strings, Unicode characters.
- Error cases: duplicates, invalid states, expired records.
- Temporal ordering between events.
- Rare but critical scenarios.

Example e-commerce dataset:
- Customers: customer_id, region, customer_tier.
- Orders: order_id, customer_id, created_at, status.
- OrderItems: order_id, product_id, quantity, unit_price.
- Payments: payment_id, order_id, payment_status.
- Shipments: shipment_id, order_id, delivery_status.

Generators must produce valid foreign keys. If an order points to a nonexistent customer, tests will fail due to invalid data rather than application bugs.

### 11.2 Masked Data

Masking replaces sensitive values with fake or transformed values. Common techniques:
- Substitution: replace with another valid value.
- Shuffling: permute values within the same column.
- Randomization: generate random values.
- Hashing: compute a hash value.
- Tokenization: replace with a token while keeping the mapping in a controlled store.
- Nulling: remove the value.
- Partial masking: obscure part of a value such as a phone number or email.

Choose a technique based on test requirements. If joins across multiple tables rely on customer ID, hashing/tokenization must be consistent across tables. Randomizing each table independently breaks referential integrity.

### 11.3 Anonymization and Re-Identification Checks

Anonymization must consider combinations of fields, not just individual columns. For example, date of birth, postal code, and gender can combine to uniquely identify an individual in a small dataset.

The process should include:
1. Classify data and sensitive fields.
2. Define the test purpose and minimum granularity needed.
3. Mask or aggregate fields.
4. Inspect linking keys and quasi-identifiers.
5. Assess re-identification risk.
6. Document the methodology and dataset version.
7. Transfer only approved datasets into sandboxes.

## 12. AWS Glue DataBrew and AWS DMS for Test Data

### 12.1 AWS Glue DataBrew

AWS Glue DataBrew supports data profiling and transforms to detect and handle PII. Masking techniques can include substitution, shuffling, deterministic/probabilistic encryption, nulling, masking, and hashing.

DataBrew is suitable when preparing analytics or test datasets from files/tables. Verify supported source types, destinations, transforms, and schema handling before building pipelines.

### 12.2 AWS Database Migration Service (DMS)

AWS DMS supports transformation rules to mask certain fields when loading data to a target. Current DMS documentation describes data masking actions including:
- Digits Mask.
- Digits Randomize.
- Hashing Mask.

These rules have specific scopes and limitations; they are not a general-purpose anonymization tool for every data type. Data masking was introduced in AWS DMS replication engine 3.5.4. Check the replication engine version, source/target types, and column rules before relying on DMS to prepare test data.

### 12.3 Do Not Treat Masking as a Compliance Guarantee

Using DataBrew or DMS does not automatically prove data is anonymized. Organizations must still identify which fields require protection, validate outputs, and evaluate re-identification risk. If data can still be linked to individuals, the sandbox environment may remain subject to the same data protection requirements as the source.

## 13. Is Cloning a Production Database Safe?

Amazon Aurora supports cluster cloning via copy-on-write. A clone initially shares data pages with the source and allocates additional storage only when the source or clone modifies data. This makes spinning up test environments faster and more cost-effective than full snapshot restores in many cases.

However, an Aurora clone is not masking. The clone initially contains the exact data from the source. If the source contains PII, payment data, or secrets, the clone contains that data until processed.

A safer workflow:
1. Create the clone in an approved account/environment.
2. Restrict access immediately upon creation.
3. Run tested masking/anonymization scripts.
4. Verify sensitive data has been sanitized.
5. Replace credentials and secrets with non-production versions.
6. Verify network access and logging.
7. Only then grant access to testers/developers.

If data is needed solely to test schemas or queries, prefer synthetic data. If realistic production distributions are needed, cloning followed by masking should only occur with data approval and matching access controls.

## 14. Managing Secrets and Environment Configuration

Each environment needs its own secrets:
- Database username/password.
- API keys.
- OAuth client secrets.
- Third-party credentials.
- Signing keys.
- Encryption keys.
- Webhook secrets.

Use AWS Secrets Manager or Systems Manager Parameter Store to store appropriate configuration. Each account/environment should have dedicated secret paths and access controls.

Example convention:
- /app/dev/database/credentials
- /app/test/database/credentials
- /app/staging/database/credentials
- /app/prod/database/credentials

Do not copy production secrets to sandboxes. Never place secrets in:
- Git repositories.
- Docker images.
- Plaintext CloudFormation parameters.
- User data or logs.
- Committed configuration files.
- CI/CD output.

Use IAM roles and workload identities to retrieve secrets at runtime. Scope `secretsmanager:GetSecretValue` to specific secret ARNs and corresponding KMS keys. Enable rotation when supported by the service and application workflow.

## 15. Standardizing Environments with Infrastructure as Code

Sandboxes should be provisioned from templates so they can be recreated and deleted in a controlled manner. Common tools:
- AWS CloudFormation.
- AWS Cloud Development Kit (CDK).
- Terraform.
- AWS SAM for serverless applications.
- AWS Copilot or workload-appropriate deployment tools.

A good template should parameterize:
- Environment name.
- Project ID.
- VPC CIDR.
- Instance size.
- Database class.
- Data retention.
- KMS key.
- Owner and expiry date.
- Allowed Region.
- Feature flags.

Do not create environments through ad-hoc console clicks without recording configuration. Without IaC, reproducing failures or cleanly tearing down environments is difficult to control.

Abbreviated CloudFormation template example:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Temporary sandbox resource example

Parameters:
  ProjectName:
    Type: String
    Default: device-lab
  Environment:
    Type: String
    Default: sandbox
  Owner:
    Type: String
  ExpiresAt:
    Type: String
    Description: ISO date, for example 2026-12-01
  BucketName:
    Type: String
    Description: Globally unique bucket name

Resources:
  TestBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Ref BucketName
      Tags:
        - Key: Project
          Value: !Ref ProjectName
        - Key: Environment
          Value: !Ref Environment
        - Key: Owner
          Value: !Ref Owner
        - Key: ExpiresAt
          Value: !Ref ExpiresAt

Outputs:
  BucketName:
    Value: !Ref TestBucket
~~~

This example creates only one bucket to illustrate parameters and tags. Production templates must address naming, encryption, public access blocks, versioning, lifecycle rules, and bucket policies.

### 15.1 Drift and Consistency

If users modify resources directly in the console, the environment can diverge from the template. You should:
- Deploy through pipelines from source control.
- Restrict direct modification permissions on critical resources.
- Run CloudFormation drift detection or `terraform plan`.
- Review change sets before applying.
- Version templates and test fixtures.
- Document approved variances.

## 16. What to Test in a Sandbox vs. Other Environments

Not every test type needs a sandbox account. Choose the environment based on scope and risk.

| Test Type | Suitable Environment | Notes |
|---|---|---|
| Unit test | Local/CI | Mock external services where appropriate |
| API contract test | Local/CI or dev | Verify schemas and backward compatibility |
| Integration test | Dev/test account | Use narrowly scoped real resources |
| IAM/SCP test | Dedicated sandbox/policy staging account | Avoid testing new policies on the production OU |
| Data pipeline test | Data sandbox account | Use only synthetic or masked data |
| Migration rehearsal | Staging/test account | Snapshots, rollback, and validation |
| Performance/load test | Representative staging | Never generate production load without permission |
| Security test | Dedicated security test account | Explicit scope and authorization |
| Chaos/fault injection | Isolated test/staging | Set stop conditions and monitor blast radius |
| Release rehearsal | Staging | Configuration as close to production as possible |

A small sandbox can verify functionality but does not represent production performance. When load testing is required, provision staging close enough to production in instances, networking, databases, data, and autoscaling; agree on load limits, runtime, and cost beforehand.

## 17. Budgets and Cost Limits

AWS Budgets tracks cost/usage and sends notifications when actual or forecasted spend exceeds thresholds. Budgets can be created by account, service, Region, or appropriate project dimensions.

Example alert thresholds for a sandbox:
- 50% budget: notify owner.
- 80% budget: notify owner and platform team.
- 100% budget: review resources and halt experiments if needed.
- Forecast exceeds threshold: investigate early before continuing.

AWS Budgets supports budget actions. Depending on configuration, actions can apply IAM policies or SCPs, or target certain EC2/RDS resources in the account; actions can run automatically or await approval.

Budgets are not hard spending caps. AWS Budgets refreshes billing data at most a few times per day; updates are typically 8–12 hours apart, and alerts may arrive after resources have already accrued additional charges. Therefore, combine budgets with:
- SCP/permission guardrails.
- Instance type and Region restrictions.
- Quotas and service access controls.
- Scheduled stops for eligible resources.
- Automated cleanup.
- Dashboards and cost anomaly alerts.

### 17.1 Service Quotas

Many service quotas are managed per account and Region. Moving workloads into separate accounts can help prevent one workload from exhausting another workload's quotas. However, not all quotas behave identically or are completely independent; inspect Service Quotas for each service and Region.

In a sandbox:
- Do not request large quota increases without an owner.
- Restrict instance types, instance counts, and database classes.
- Monitor VPCs, ENIs, Elastic IPs, NAT Gateways, and load balancers.
- Check quotas before large-scale tests.
- Delete resources upon completion to free quotas.

## 18. Tagging and Identifying Temporary Resources

Use consistent tags to know who created a resource, which environment it belongs to, and when it expires.

Suggested tags:

| Tag | Example | Purpose |
|---|---|---|
| Project | iot-shadow-lab | Group by project |
| Environment | sandbox | Identify environment |
| Owner | team-platform | Responsible person/team |
| CostCenter | CC-042 | Cost allocation |
| ExpiresAt | 2026-12-01 | Expiration date |
| DataClass | synthetic | Data classification |
| ManagedBy | cloudformation | Identify management tool |

AWS Organizations Tag Policies help standardize tag keys, casing, and values across supported resource types. However, tag policies do not detect completely untagged resources; untagged resources do not automatically appear as noncompliant in some tag policy reports. Combine IaC validation, AWS Config, Resource Explorer, or the Resource Groups Tagging API to find resources missing tags.

Do not rely on tags as the sole security boundary. Tags are useful for cost allocation, automation, and ABAC, but IAM policies, resource policies, and account boundaries are required to protect resources.

## 19. Automating the Sandbox Lifecycle

A sandbox should have an explicit expiration date and renewal workflow.

Reference lifecycle:

~~~text
Request
   |
   v
Approve owner / budget / data class
   |
   v
Provision account and baseline
   |
   v
Deploy IaC stack and test data
   |
   v
Run experiment / test
   |
   v
Review result and request extension?
   |                    |
   | No                 | Yes
   v                    v
Cleanup resources     Extend expiry
   |
   v
Verify no orphan resources
   |
   v
Archive evidence and close sandbox
~~~

This can be implemented with:
- Account Factory for account creation.
- Service Catalog or pipelines to provision templates.
- EventBridge Scheduler or EventBridge rules to trigger scheduled workflows.
- Lambda or Step Functions to inspect ExpiresAt and owners.
- CloudFormation/Terraform to delete stacks.
- AWS Budgets for alerting.
- AWS Config/Resource Explorer to audit remaining resources.

Automation needs safety checks. Do not delete solely because a tag expired if the resource is protected, under legal hold, or marked retain. Require owner confirmation before cleaning up resources with important data.

### 19.1 CloudFormation Stack Cleanup

CloudFormation can delete stack-owned resources when deleting a stack. However:
- Resources with `DeletionPolicy: Retain` may be preserved.
- S3 buckets typically must be emptied before deletion.
- Out-of-stack resources or retained resources can become orphaned.
- Stack deletion cannot be stopped once initiated.
- Verify `DELETE_COMPLETE` and inspect the resource list after cleanup.

Example of a data resource to retain:

~~~yaml
Resources:
  TestArchiveBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
    Properties:
      VersioningConfiguration:
        Status: Enabled
~~~

This example intentionally preserves the bucket and its data when the stack is deleted. If the sandbox requires full cleanup, do not apply `Retain` arbitrarily. Classify ephemeral vs. persistent resources before authoring templates.

### 19.2 Resources to Check After Cleanup

- EC2 instances and Auto Scaling groups.
- EBS volumes and snapshots.
- Elastic IPs and NAT Gateways.
- Load balancers and target groups.
- RDS/Aurora instances, clusters, and snapshots.
- S3 buckets, objects, and multipart uploads.
- CloudWatch log groups and log streams.
- ECR images and repositories.
- Lambda functions, event source mappings, and layers.
- VPC endpoints, security groups, and ENIs.
- Secrets Manager secrets and Parameter Store parameters.
- KMS keys and scheduled deletions.
- Route 53 records, hosted zones, and certificates.
- CloudFormation stacks, nested stacks, and StackSet instances.

Some resources must be deleted in dependency order. If cleanup fails, inspect service events/errors, resolve dependencies, and retry. Do not force-delete blindly, as it can leave behind uncontrolled resources or data.

## 20. Logging, Auditing, and Security Monitoring

A sandbox still requires auditing to investigate actions and costs.

Services to use:
- **AWS CloudTrail:** records API activity and acting principals.
- **AWS Config:** records resource configurations and evaluates rules.
- **Amazon GuardDuty:** detects suspicious activity.
- **AWS Security Hub:** aggregates security findings.
- **CloudWatch Logs/Metrics:** monitors applications and services.
- **Amazon S3 log archive:** centrally stores logs per retention policies.

Do not disable logging to cut sandbox costs if organizational policy requires auditing. If a sandbox is permitted to disable certain integrations, follow an explicit baseline with prior approval.

Distinguish test logs from audit logs. Application logs may contain tokens, emails, payloads, or PII; control log levels, redaction, and retention.

## 21. Reference Architecture: Sandbox Account for an AWS Application

An IoT development team needs to test Lambda, API Gateway, DynamoDB, and S3. Suggested architecture:

~~~text
AWS Organization
|
+-- Security OU
|   +-- Log Archive
|   +-- Audit
|
+-- Sandbox OU
    +-- Sandbox-IoT account
         |
         +-- IAM Identity Center assignment
         |     +-- DeveloperSandbox permission set
         |
         +-- SCP guardrails
         |     +-- Protect audit configuration
         |     +-- Restrict selected Regions
         |
         +-- Sandbox VPC
         |     +-- Private subnets
         |     +-- VPC endpoints
         |
         +-- Application stack
         |     +-- API Gateway
         |     +-- Lambda
         |     +-- DynamoDB
         |     +-- S3 test bucket
         |
         +-- Test data
         |     +-- Synthetic dataset
         |     +-- Versioned fixtures
         |
         +-- Cost and lifecycle
               +-- AWS Budget
               +-- Owner / ExpiresAt tags
               +-- Cleanup workflow
~~~

Workflow:
1. Developer requests an account and declares the test objective.
2. Platform team provisions an account in the Sandbox OU.
3. IAM Identity Center assigns the permission set.
4. The baseline sets up logging, networking, and guardrails.
5. CI/CD deploys the stack from templates.
6. Pipeline loads synthetic test data.
7. Developer runs integration tests.
8. Dashboards track costs and errors.
9. Upon expiration, the workflow cleans up the stack and verifies resources.
10. Test results and evidence are archived per retention policy.

## 22. End-to-End Safe Testing Procedure

### Before Testing

1. Define objectives, scope, and test types.
2. Select the appropriate account/OU.
3. Confirm the owner and budget.
4. Confirm permitted Regions/services.
5. Verify data is synthetic or masked.
6. Verify IAM permissions and SCPs.
7. Confirm VPC, routes, and security groups.
8. Confirm non-production secrets and KMS keys.
9. Deploy using IaC.
10. Record the baseline state.

### During Testing

1. Monitor cost, quotas, and service health.
2. Record template, image, and dataset versions.
3. Never introduce production credentials into the sandbox.
4. Never open production connections outside approved scope.
5. Monitor CloudTrail and CloudWatch logs.
6. Stop testing if stop conditions are breached or sensitive data is detected.
7. Log failures and reproduction steps.

### After Testing

1. Save required results and evidence.
2. Delete ephemeral resources.
3. Inspect retained and orphaned resources.
4. Check S3 objects, snapshots, log groups, and EIPs.
5. Verify temporary secrets and credentials are revoked.
6. Confirm budgets/costs do not continue rising unexpectedly.
7. Renew or close the sandbox account.
8. Update templates with new lessons learned.

## 23. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Developer cannot access the account | Group/permission set not assigned or provisioning incomplete | Check IAM Identity Center assignments and account provisioning status |
| Resource creation gets AccessDenied | IAM policy or SCP does not allow it | Identify which policy layer caused the deny using CloudTrail and the policy simulator |
| Service unavailable in Region | SCP Region guardrail or unsupported service | Check the requested Region and required exceptions |
| Sandbox can read production bucket | Overly broad resource policy or trust policy | Narrow principals, bucket prefixes, KMS keys, and cross-account roles |
| Test data contains PII | Dataset not masked or profiling insufficient | Stop sharing, isolate the dataset, reprocess, and validate output |
| Database clone contains real data | Cloning does not mask data automatically | Restrict access and run masking/anonymization before granting access |
| Budget alerts arrive late | Billing data refresh has latency | Use quotas, SCPs, scheduled stops, and cleanup as additional guardrails |
| Costs rise after stack deletion | Retained resources or out-of-stack resources | Inspect stack resources, orphaned resources, and billing dimensions |
| Stack deletion fails | Bucket still has objects or resource dependencies | Inspect stack events, resolve dependencies, and retry |
| Resources lack tags | Created manually in console or service lacks create-time tagging | Use IaC validation, Config/Resource Explorer, and remediation |
| Quotas exhausted | Sandbox shares an account with other workloads | Separate accounts or manage quotas per project/Region |
| Load test differs from production | Smaller instances/data/network or different config | Use representative staging and realistic synthetic data |

When investigating, identify the account, Region, principal, resource ARN, and request ID first. Never resolve AccessDenied by granting broad AdministratorAccess without finding the root cause.

## 24. Production-Ready Sandbox Design Checklist

- [ ] Sandbox objective and owner are defined.
- [ ] Sandbox resides in AWS Organizations under the appropriate OU.
- [ ] Production is separated into its own account per isolation requirements.
- [ ] Accounts are provisioned via a standard workflow or Account Factory.
- [ ] Baseline logging, Config, and security controls are in place.
- [ ] Developers access via IAM Identity Center.
- [ ] MFA and temporary credentials are enforced.
- [ ] Root credentials or access keys are never shared.
- [ ] SCPs have been tested in a staging account/OU.
- [ ] Team understands SCPs do not grant permissions and do not apply to the management account/service-linked roles.
- [ ] VPC CIDRs do not overlap with networks requiring connectivity.
- [ ] No default routes exist from sandbox to production.
- [ ] Security groups allow only required traffic.
- [ ] Secrets, databases, and KMS keys are separated per environment.
- [ ] Synthetic datasets are prioritized.
- [ ] Production-like data is masked/anonymized and verified.
- [ ] Aurora clones are never treated as masked datasets.
- [ ] Test fixtures are schema-validated and versioned.
- [ ] IaC templates can recreate the environment.
- [ ] Drift detection or change reviews are enabled.
- [ ] Budget alerts and alert owners are configured.
- [ ] Additional guardrails exist because budgets are not hard caps.
- [ ] Resources carry Project, Environment, Owner, and ExpiresAt tags.
- [ ] Cleanup workflows and orphan checks are in place.
- [ ] Retention policies exist for logs, snapshots, and test data.
- [ ] Audit trails cover account access and API activity.
- [ ] Runbooks exist for sandbox expiration or sensitive data discovery.

## 25. Hands-On Exercises

### Exercise 1: Choosing Environment Boundaries

A company has one production application and three independent development teams. Each team needs permissions to create Lambda, RDS, and VPC resources for experimentation.

Task: propose an account/OU structure.

Suggested answer: place the production workload in a separate Production OU/account; give each team its own sandbox account or workload- and permission-isolated sandbox account; use IAM Identity Center for access assignments; apply SCPs and budgets per OU/account.

### Exercise 2: Evaluating SCPs

A developer has an IAM policy allowing EC2 creation, but `CreateInstances` fails with AccessDenied. An SCP on the Sandbox OU has an explicit Deny for EC2.

Task: explain the result.

Answer: SCPs set the maximum permission boundary. An IAM Allow cannot override an explicit Deny in an SCP. Inspect CloudTrail and applicable policies; do not add more IAM Allow statements trying to bypass an SCP.

### Exercise 3: Detecting Data Exposure

A developer restores a production database snapshot into a sandbox to test queries.

Task: list the steps required before opening access to the team.

Answer: isolate the database, check data classification, run masking/anonymization, verify PII removal, rotate/replace credentials, inspect KMS/network/policies, and get dataset approval before granting access.

### Exercise 4: Choosing Test Data

A test only needs to verify an order workflow and relationships across customer, order, and payment.

Task: choose the data type and constraints to preserve.

Answer: synthetic data is the first choice; preserve foreign keys, order/payment states, value distributions, and edge cases under test.

### Exercise 5: Relational Masking

Customer ID appears in Customers, Orders, and Payments. If each table is randomized independently, what happens?

Answer: foreign keys no longer match. Use consistent mapping/tokenization or deterministic transformations for the same ID across all tables.

### Exercise 6: Exceeding Budget

AWS Budgets alerts that the sandbox has reached 100% of its budget, yet EC2 instances are still running.

Task: explain why and propose countermeasures.

Answer: budget alerts have latency and do not act as automatic hard caps. Combine appropriately approved budget actions, SCP/IAM guardrails, scheduled stops, and cleanup workflows.

### Exercise 7: Failed Cleanup

A CloudFormation stack is stuck in `DELETE_FAILED` because an S3 bucket still contains objects.

Task: how do you resolve it?

Answer: inspect stack events, determine which objects to keep/delete, empty the bucket per retention policy, and retry. If using `Retain`, document the retained resource and assign an owner.

### Exercise 8: Tag Policy

A newly created resource has no `Owner` tag, yet the tag policy report does not list it as noncompliant.

Task: explain why and how to detect it.

Answer: tag policies do not evaluate completely untagged resources in some reports. Use IaC validation, AWS Config, or a Resource Explorer `tag:none` query to locate untagged resources.

### Exercise 9: Aurora Clone

An Aurora clone was created to test schemas. The team assumes that because the clone is separate from production, developers can access it directly.

Answer: the clone has an independent volume, yet its initial data consists of the source's data pages via copy-on-write. You must mask/anonymize data and replace secrets before granting access.

### Exercise 10: Choosing a Load-Testing Environment

A team wants to load test using a sandbox instance 10x smaller than production.

Answer: a sandbox can verify load logic on a limited scale, but it is not representative of production performance. Use staging with near-production sizing and data, under agreed load limits and approval.

## 26. Self-Check Questions

1. What is a sandbox and when is it used?
2. Which isolation boundaries does an AWS account provide?
3. Why should production be separated from dev/test?
4. What are OUs used for in AWS Organizations?
5. How does AWS Control Tower Account Factory help?
6. How does IAM Identity Center differ from long-lived IAM users?
7. Do SCPs grant permissions to principals?
8. Do SCPs apply to the management account?
9. Why should SCPs be tested before attaching them to a large OU?
10. Does an account boundary automatically prevent cross-account access?
11. What additional protection layer does VPC isolation provide?
12. Why does CIDR overlap cause problems?
13. How does synthetic data differ from masked data?
14. Why is renaming columns insufficient for anonymization?
15. How can AWS Glue DataBrew help handle PII?
16. Which transformation types does AWS DMS data masking support?
17. Why is an Aurora clone not equivalent to a masked dataset?
18. Why does each environment need separate secrets and KMS policies?
19. How does IaC give a sandbox a controlled lifecycle?
20. Is AWS Budgets a hard spending cap?
21. Why combine budgets with SCPs/quotas/cleanup?
22. Do tag policies detect every untagged resource?
23. Which resources are commonly overlooked during cleanup?
24. Why is staging better suited than a small sandbox for load testing?
25. What evidence should be retained after a test run?

Suggested answers:

1. A testing environment with scoped permissions, data, cost, and duration.
2. Resources, access control, billing, and many service quotas.
3. To reduce blast radius and prevent test actions from affecting real workloads.
4. Grouping accounts by shared policies and controls.
5. Standardizes and automates creating/updating accounts in a landing zone.
6. Identity Center uses federation and temporary role credentials.
7. No; SCPs only set maximum permission boundaries.
8. No; SCPs do not restrict the management account.
9. Denies can block pipelines, logging, or operations.
10. No; cross-account trusts and resource policies can still allow access.
11. Routes, subnets, security groups, egress, and endpoints.
12. Routes between VPCs become ambiguous or cannot be routed properly.
13. Synthetic data is newly generated; masked data transforms existing source data.
14. Other fields can combine to re-identify individuals.
15. Profiles data and applies transforms to redact/mask PII.
16. Digits mask, digits randomize, and hashing mask.
17. The clone initially shares the source's data pages.
18. To avoid shared credentials/keys and scope access per environment.
19. Recreates consistently, checks drift, and deletes cleanly by stack.
20. No; alerts have latency and do not automatically block all resources.
21. To reduce cost risk before billing alerts update.
22. No; untagged resources may not be evaluated in reports.
23. EBS/snapshots, EIPs, NAT Gateways, log groups, buckets, secrets, KMS keys, and out-of-stack resources.
24. Because its configuration can more closely represent production.
25. Test scope, dataset version, IaC version, logs, results, costs, and cleanup evidence.

## 27. Official References

- [AWS multi-account strategy for an AWS Control Tower landing zone](https://docs.aws.amazon.com/controltower/latest/userguide/aws-multi-account-landing-zone.html)
- [AWS Well-Architected: Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/framework/sec_securely_operate_multi_accounts.html)
- [AWS Organizations best practices](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_best-practices.html)
- [Provision accounts with AWS Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/methods-of-provisioning.html)
- [AWS Organizations Service Control Policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [IAM Identity Center account access](https://docs.aws.amazon.com/singlesignon/latest/userguide/manage-your-accounts.html)
- [AWS Well-Architected: Experimental and temporary environments](https://docs.aws.amazon.com/wellarchitected/latest/framework/fnd01-bp04.html)
- [AWS Glue DataBrew: Identifying and handling PII](https://docs.aws.amazon.com/databrew/latest/dg/personal-information-protection.html)
- [AWS DMS: Data masking](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.SelectionTransformation.Masking.html)
- [Amazon Aurora cloning](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Managing.Clone.html)
- [AWS Budgets: Managing costs](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [AWS Budgets: Configuring budget actions](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html)
- [AWS Organizations tag policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_tag-policies.html)
- [CloudFormation: Delete a stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-console-delete-stack.html)
- [CloudFormation: Managing stacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacks.html)
- [AWS Prescriptive Guidance: Automate deletion of CloudFormation stacks](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/automate-deletion-cloudformation-stacks-associated-resources.html)

Account Factory capabilities, Control Tower controls, SCPs, quotas, masking, and service integrations may vary by Region, landing zone version, and service version. Before applying organization-wide, test in an isolated account/OU, verify permissions and policy impact, validate output datasets, and then expand to other workloads.
