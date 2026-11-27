# Checking Policies, Secrets, and Secure Configurations in IaC

A team deploys a Java application on AWS using CloudFormation. The template creates an IAM role for Lambda, an S3 bucket storing documents, a DynamoDB table, an RDS database, security groups, and secrets required by the application. A template that deploys cleanly does not mean the infrastructure is secure: an IAM policy might grant overly broad permissions, a bucket might be public, a security group might expose management ports to the Internet, or a password might have been committed to Git.

Infrastructure as Code (IaC) turns infrastructure into source code that can be reviewed, tested, and reproduced. That also means a security flaw in a template can be deployed repeatedly across multiple environments. Therefore, security checks must become part of the development lifecycle: from template authoring, through pull requests, before creating change sets, and during runtime operations.

This lesson belongs to the **Infrastructure as Code** chapter of the **CLOUD_PROVIDERS_AWS** module. We focus on three control areas:

- **Policy:** IAM identity/resource policies, trust policies, KMS permissions, security groups, and guardrails.
- **Secret:** passwords, API keys, tokens, private keys, dynamic references, and rotation lifecycles.
- **Secure configuration:** encryption, public access, network exposure, logging, backups, validation, and policy-as-code.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why IaC templates must undergo security checks before deployment.
2. Distinguish identity policies, resource policies, trust policies, permission boundaries, and SCPs.
3. Design IAM policies following least privilege and restrict `iam:PassRole` permissions.
4. Identify wildcard, public principal, trust relationship, and confused deputy risks.
5. Manage secrets using AWS Secrets Manager, Systems Manager Parameter Store, and CloudFormation dynamic references.
6. Explain the limitations of NoEcho and why secrets should not be passed via parameters or outputs.
7. Design rotation, runtime retrieval, caching, and secret read permissions.
8. Configure encryption, S3 public access blocks, TLS, security groups, and secure logging.
9. Use cfn-lint, CloudFormation Guard, IAM Access Analyzer, and CloudFormation change sets for verification.
10. Organize policy-as-code, security gates, and time-bound exception handling.
11. Detect exposed secrets in Git, templates, CI logs, or CloudFormation outputs.
12. Build a security checklist before deploying IaC to production.

## 2. IaC Security: Checking from Source Code to Runtime

A CloudFormation template can be syntactically valid yet still create dangerous configurations. For example, `SecurityGroupIngress` might open SSH to the entire Internet; a role might receive `s3:*` on every bucket; or a Lambda environment variable might hold a hardcoded token.

Checks should happen across multiple stages:

| Stage | Checks | Goal |
|---|---|---|
| Authoring | Secure defaults, reusable modules, review | Prevent flaws from entering the template |
| Pull request | Lint, policy-as-code, secret scan, IAM validation | Catch issues before merging |
| Pre-deployment | Change set, policy review, deployment role | Understand changes about to be applied |
| Deployment | CloudFormation Hooks, SCP, IAM, permission boundaries | Block non-compliant configurations |
| Runtime | AWS Config, Security Hub, CloudTrail, drift detection | Detect post-deployment drift and violations |
| Incident response | Rotate/revoke secrets, rollback, audit | Limit impact and recover |

No single tool catches every flaw. Linters catch structural errors and certain misconfigurations; policy-as-code checks organizational rules; IAM Access Analyzer checks policy semantics; runtime controls observe live state.

## 3. Policy Model in AWS

Before writing a policy, know where that policy attaches and what it protects.

| Policy type | Attached to | Purpose |
|---|---|---|
| Identity-based policy | IAM user, group, role | Defines which actions a principal can invoke on which resources |
| Resource-based policy | S3 bucket, KMS key, SQS queue, Lambda function... | Defines which principals can access the resource |
| Trust policy | IAM role | Defines which principals can AssumeRole |
| Permissions boundary | IAM user/role | Sets the maximum permissions an identity policy can grant |
| Service Control Policy (SCP) | AWS Organizations account/OU/root | Sets maximum permission boundaries for member accounts |
| Session policy | STS session | Narrows permissions for a specific session |

IAM evaluation spans multiple layers. Explicit Deny always overrides Allow. An Allow in an identity policy does not guarantee a request succeeds if a resource policy, permissions boundary, SCP, session policy, or another condition forbids it.

SCPs do not grant permissions themselves. SCPs cap permissions for principals in member accounts; identity/resource policies must still grant the necessary access. SCPs do not apply the same way to the management account, and certain service-linked roles have exceptions per AWS documentation.

## 4. Least Privilege for IAM Identity Policies

The principle of least privilege means granting only the exact actions, resources, and conditions required by the workload.

An overly broad policy:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "*",
          "Resource": "*"
        }
      ]
    }

This policy grants a principal access across vast services and resources. If credentials leak or the workload is compromised, the blast radius can be severe.

Example role needing only to read objects in one bucket:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "ReadInvoiceObjects",
          "Effect": "Allow",
          "Action": [
            "s3:GetObject"
          ],
          "Resource": "arn:aws:s3:::company-invoices-prod/*"
        }
      ]
    }

If the workload needs to list the bucket, add `s3:ListBucket` on the bucket ARN, typically paired with a prefix condition where appropriate. An S3 bucket ARN and object ARN are two distinct resource types.

### 4.1. Wildcards Are Not Always Wrong, But Must Be Justified

Some actions do not support resource-level permissions and require `Resource: "*"`. Some services require wildcards for a specific scope of actions. Therefore, do not apply a rigid rule treating every asterisk as an error.

When reviewing wildcards, ask:

- Does the action support resource-level permissions?
- Can it be scoped by ARN, account, Region, tag, or condition?
- Does the workload need write/delete permissions or only read?
- Should permissions span all environments and tenants?
- Can statements be split by resource/action to narrow scope?

Write policies aligned with workload functionality; never attach `AdministratorAccess` to an application merely to silence `AccessDenied` errors.

### 4.2. Separating Administrative Permissions and Runtime Permissions

A Lambda processing invoices typically only needs to read objects, write logs, and access a specific secret. It does not need permission to create IAM roles, edit bucket policies, or delete databases.

Separate roles:

- Deployment role: creates and updates resources within stack scope.
- Runtime role: permissions needed by the application while running.
- Break-glass/admin role: privileged administrative access, tightly controlled and audited.
- Read-only/audit role: inspects configurations and logs.

Never reuse a deployment role as an application's execution role.

## 5. Trust Policies and AssumeRole Permissions

A trust policy determines who is permitted to obtain temporary credentials for a role. Example role for the Lambda service:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {
            "Service": "lambda.amazonaws.com"
          },
          "Action": "sts:AssumeRole"
        }
      ]
    }

A trust policy is not a permission policy. It does not grant access to S3 or DynamoDB; it solely specifies which principals can assume the role.

### 5.1. Cross-Account Access

When a role in account A is assumed from account B, configure both sides:

1. The trust policy on the role in account A allows the principal/role in account B.
2. The identity policy on the principal in account B permits `sts:AssumeRole` targeting the role ARN in account A.
3. Conditions such as `ExternalId`, MFA, or source identity are included when appropriate to the trust model.

For third-party SaaS accessing customer accounts, `ExternalId` helps mitigate confused deputy risks. Never reuse one fixed `ExternalId` across all customers when each tenant needs distinct identification.

### 5.2. Service Principals and Confused Deputy

When granting an AWS service principal access to a resource, restrict the calling source using conditions when supported by the service. For example, resource policies or role trust policies can use `aws:SourceArn` and `aws:SourceAccount` to constrain which resource/account can invoke the call.

Do not add conditions mechanically: exact condition names and support depend on the service and integration. Cross-check the specific service documentation before applying.

## 6. Controlling iam:PassRole

`iam:PassRole` allows a principal to pass an IAM role to an AWS service so the service runs a workload with that role. If this permission is overly broad, a deployer could create or modify a resource to use a higher-privileged role.

A tightly scoped policy:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "iam:PassRole",
          "Resource": "arn:aws:iam::123456789012:role/app-lambda-runtime",
          "Condition": {
            "StringEquals": {
              "iam:PassedToService": "lambda.amazonaws.com"
            }
          }
        }
      ]
    }

Replace the account ID and role ARN with values from your deployment environment. Never grant `iam:PassRole` on all roles if deployments only need to pass specific known roles.

Also review `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, and `iam:UpdateAssumeRolePolicy`. A principal could create a new role, attach strong permissions, and pass that role to a service if these permissions go unchecked.

## 7. Resource Policies: Checking Principal and Condition

Resource policies commonly appear on S3, KMS, SQS, SNS, Lambda, and Secrets Manager.

Example S3 bucket policy permitting requests only over HTTPS:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "DenyInsecureTransport",
          "Effect": "Deny",
          "Principal": "*",
          "Action": "s3:*",
          "Resource": [
            "arn:aws:s3:::company-invoices-prod",
            "arn:aws:s3:::company-invoices-prod/*"
          ],
          "Condition": {
            "Bool": {
              "aws:SecureTransport": "false"
            }
          }
        }
      ]
    }

The wildcard principal in this `Deny` statement does not open public access; it denies non-TLS requests. When reviewing policies, read `Effect`, `Principal`, `Action`, `Resource`, and `Condition` together rather than merely searching for `*`.

For policies with `Effect: Allow` and `Principal: "*"`, inspect access conditions very carefully. Public access can arise from bucket policies, ACLs, or other settings. For modern S3, enable Block Public Access and BucketOwnerEnforced ownership controls where appropriate.

## 8. KMS Key Policies and Decryption Permissions

A KMS key policy dictates which principals can use or administer a customer managed key. Even if an identity policy has `Allow` for `kms:Decrypt`, the operation can still be denied if the key policy does not authorize that principal.

Separate roles:

- Key administrators: manage key policies, rotation, enable/disable, and lifecycle.
- Key users: use the key for `Encrypt`/`Decrypt`/`GenerateDataKey` within required scope.
- Application roles: use only the key belonging to their specific resource/workload.

Example restricting decryption strictly through Secrets Manager in the appropriate Region:

    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.ap-southeast-1.amazonaws.com"
        }
      }
    }

This illustrates a specific workload. KMS key policies, grants, encryption contexts, and service integrations must be designed coherently. Never copy example ARNs/Regions into production.

Never grant `kms:*` across all keys to a runtime role. Also protect permission to modify key policies: someone allowed to alter key policies unchecked can expand their own access.

## 9. Secrets: Identifying and Classifying Sensitive Data

A secret is data used to authenticate, sign, or access systems:

- Database passwords.
- API keys and OAuth client secrets.
- Long-lived access keys.
- Private keys and certificate private material.
- Signing keys and webhook secrets.
- Third-party service tokens.

Not every setting is a secret. Regions, table names, feature flags, and internal endpoints are typically configuration; still evaluate whether they expose sensitive details.

Classification guides storage and access control choices:

| Data | Appropriate storage |
|---|---|
| Passwords/API keys needing rotation and audit | AWS Secrets Manager |
| Standard configuration values | SSM Parameter Store String |
| Simple secrets requiring KMS encryption | SSM Parameter Store SecureString |
| Supported RDS database master passwords | RDS managed master user password with Secrets Manager |
| Certificates/private keys | Secrets Manager or appropriate certificate management service |
| Temporary AWS credentials | IAM roles/STS, never stored as static secrets |

Never store long-lived AWS access keys in templates or application configuration files. Workloads on Lambda, ECS, EKS, or EC2 should use IAM roles/workload identities to obtain temporary credentials.

## 10. AWS Secrets Manager and Parameter Store

### 10.1. AWS Secrets Manager

Secrets Manager fits well when you need:

- Structured secrets or secret strings.
- Access control via IAM and resource policies.
- Encryption with AWS KMS.
- Access auditing via CloudTrail.
- Automatic rotation or rotation workflows depending on secret/service.
- Version management and staging labels like `AWSCURRENT`, `AWSPREVIOUS`.

A template can create a secret with an auto-generated value:

    Resources:
      ApplicationDatabaseSecret:
        Type: AWS::SecretsManager::Secret
        Properties:
          Name: app/prod/database
          GenerateSecretString:
            SecretStringTemplate: '{"username":"appuser"}'
            GenerateStringKey: password
            PasswordLength: 32
            ExcludePunctuation: true

The template contains no static password. Secrets Manager generates the secret string per configuration and stores the generated value. Read permissions must be granted separately to the runtime role.

### 10.2. Systems Manager Parameter Store

Parameter Store works well for centralized configuration. Parameters can be `String`, `StringList`, or `SecureString` depending on creation method and API usage.

- String / StringList: non-secret configuration.
- SecureString: value encrypted with KMS.
- Parameter hierarchy: groups configuration by application, environment, and component.
- IAM: scopes paths and actions such as `ssm:GetParameter`, `ssm:GetParameters`.

SecureString does not provide built-in rotation workflows like Secrets Manager. When passwords/API keys need automatic rotation and version/staging lifecycle management, consider Secrets Manager.

Never store secrets in parameter names or tags. Metadata can be exposed via permissions that read resource descriptions.

## 11. CloudFormation Parameters and Limitations of NoEcho

CloudFormation supports `NoEcho` to mask parameter values in certain API responses and UI displays.

    Parameters:
      DatabasePassword:
        Type: String
        NoEcho: true
        MinLength: 16

NoEcho is not a secret manager:

- It does not encrypt values inside the template.
- It does not erase secrets from Git, CI logs, or shell history.
- It does not protect values written to Metadata or Outputs.
- It does not make every receiving resource property a secure secret store.
- Principals with runtime/resource access may still read the value via service APIs or the application.

Never set default passwords in Parameters. Avoid passing secrets via command-line arguments whenever possible because process arguments and shell history can be logged.

Never put secrets into Outputs, Metadata, tags, resource names, or stack descriptions. Use a secret store and reference secrets only where supported by services/properties.

## 12. CloudFormation Dynamic References

Dynamic references let CloudFormation fetch values from Secrets Manager or Systems Manager Parameter Store when provisioning resource properties. The template holds a reference string instead of embedding the secret value directly.

### 12.1. Secrets Manager Dynamic Reference

General syntax:

    {{resolve:secretsmanager:secret-id:SecretString:json-key:version-stage:version-id}}

Example retrieving the `password` field from a JSON secret:

    Resources:
      LegacyDatabase:
        Type: AWS::RDS::DBInstance
        Properties:
          Engine: mysql
          DBInstanceClass: db.t3.micro
          MasterUsername: appuser
          MasterUserPassword: '{{resolve:secretsmanager:app/prod/database:SecretString:password}}'

The secret must exist, and the deployment principal/CloudFormation service role must have permission to read the secret along with required KMS permissions. This example only illustrates dynamic references; production RDS should consider direct managed master password integration.

### 12.2. SSM SecureString Dynamic Reference

Syntax:

    {{resolve:ssm-secure:parameter-name:version}}

Example:

    MasterUserPassword: '{{resolve:ssm-secure:/app/prod/database/password:7}}'

The version is optional. When omitted, CloudFormation uses the current version per Parameter Store dynamic reference behavior.

### 12.3. Dynamic References Are Not Runtime Secret Retrieval

CloudFormation resolves dynamic references while creating or updating a resource property. Running applications do not automatically call CloudFormation to fetch new secrets.

When secret rotation happens:

- The secret in Secrets Manager may have moved `AWSCURRENT` to a new version.
- Resources receiving the secret via dynamic reference are not necessarily updated immediately.
- CloudFormation does not automatically trigger a stack update just because a secret version changed.
- Resources needing synchronized passwords require an appropriate rotation integration or safe resource update workflow.

Dynamic references are also unsupported in certain contexts and resource properties. Check dynamic reference limitations—especially with custom resources and metadata/init fields—before using them.

### 12.4. When to Use RDS Managed Master Passwords?

For supported RDS DB instances, you can let RDS manage the master password via Secrets Manager:

    Resources:
      ApplicationDatabase:
        Type: AWS::RDS::DBInstance
        Properties:
          Engine: postgres
          DBInstanceClass: db.t3.micro
          AllocatedStorage: "20"
          MasterUsername: dbadmin
          ManageMasterUserPassword: true
          StorageEncrypted: true
          PubliclyAccessible: false

This avoids passing a master password through the template. RDS creates and manages the associated secret. Verify engine, version, and DB instance type support for this property. For Aurora, configure password management on the corresponding DB cluster resource.

## 13. Applications Retrieving Secrets at Runtime

For Java applications, it is usually better to let the workload identity/IAM role read secrets when needed rather than embedding passwords in templates or build artifacts.

Reference flow:

    Spring Boot service
        |
        | AWS SDK for Java 2.x
        v
    AWS Secrets Manager
        |
        | GetSecretValue
        v
    Secret value (in memory)
        |
        v
    Database connection pool

The runtime role only needs `secretsmanager:GetSecretValue` on the specific secret ARN. If using a customer managed KMS key, `kms:Decrypt` is needed per key policy and appropriate conditions.

### 13.1. Caching and Rotation

Do not call Secrets Manager on every SQL query. Use a cache with a sensible TTL or the language-appropriate AWS Secrets Manager caching client. TTL must balance cost, latency, and how quickly new secrets are picked up after rotation.

During secret rotation:
1. Generate new credentials/version.
2. Update the database or target system per the rotation workflow.
3. Shift staging label/current version per procedure.
4. Applications fetch the new secret upon cache expiration or refresh.
5. Connection pools retire old connections and open new ones.
6. Disable old credentials only after verifying workloads have switched over.

Never cache indefinitely. Never log secrets when parsing fails or database connections error. Never place secrets into exception messages, metric labels, or tracing baggage.

## 14. Secret Scanning and Handling Exposed Secrets

Secret scanning should run on both diffs and repository history. Tools can detect AWS access key patterns, private keys, common tokens, and high-entropy strings, though false positives can still occur.

Options include:

- GitHub secret scanning or equivalent Git platform tooling.
- Gitleaks.
- TruffleHog.
- Secret scanning in CI/security platforms.

When a secret is found in Git:

1. Identify the secret type, environment, and granted permissions.
2. Revoke or rotate the credential immediately based on risk severity.
3. Inspect CloudTrail/service logs for signs of unauthorized use.
4. Switch applications to the new secret and verify.
5. Remove the secret from source and history per organizational procedure; note that rewriting history does not invalidate old credentials.
6. Check forks, artifacts, CI logs, caches, and repository clones.
7. Record the incident and root cause to add preventive rules.

**Deleting a line from Git does not make an exposed secret safe again.** Rotation/revocation is the most critical step.

## 15. Secure Defaults for S3

S3 buckets frequently hold sensitive data, so templates should set clear controls:

    Resources:
      PrivateDocumentsBucket:
        Type: AWS::S3::Bucket
        Properties:
          PublicAccessBlockConfiguration:
            BlockPublicAcls: true
            IgnorePublicAcls: true
            BlockPublicPolicy: true
            RestrictPublicBuckets: true
          OwnershipControls:
            Rules:
              - ObjectOwnership: BucketOwnerEnforced
          BucketEncryption:
            ServerSideEncryptionConfiguration:
              - ServerSideEncryptionByDefault:
                  SSEAlgorithm: aws:kms
                  KMSMasterKeyID: !Ref DataEncryptionKey
                BucketKeyEnabled: true
          VersioningConfiguration:
            Status: Enabled

These properties reduce risks of public access, ACL ownership ambiguity, and storing unencrypted objects contrary to policy. Encryption at rest does not replace access control; principals still need proper permissions.

### 15.1. TLS-Only Bucket Policy

Add an explicit `Deny` with `aws:SecureTransport=false` to reject non-TLS requests. Ensure the bucket policy includes both the bucket ARN and object ARN appropriately.

### 15.2. Logging and Data Protection

Consider CloudTrail data events for object-level auditing, access logging as required, Versioning, lifecycle rules for noncurrent versions, and Object Lock when immutable retention is needed. Data events can increase costs; enable them scoped by bucket/prefix and audit requirements.

## 16. Secure Defaults for Databases, Queues, and Volumes

| Resource | Controls to consider |
|---|---|
| RDS | StorageEncrypted, KmsKeyId, PubliclyAccessible=false, private subnets, DeletionProtection, backup retention, tight security groups |
| DynamoDB | SSESpecification, PITR, IAM table/index ARNs, conditions, and backups |
| EBS | Encrypted=true, KmsKeyId if CMK needed, snapshot policies, volume attached in right AZ |
| SQS | SSE/KMS when needed, tight queue policy, TLS enforcement, DLQ/redrive policy |
| SNS | KMS encryption where appropriate, tight topic policy, TLS, and subscription controls |
| ECR | Image scanning, encryption, immutable tags if workflow supports |
| Lambda | Least-privilege execution role, no static secrets in environment, VPC only when needed, logging and tracing |
| EC2 | Instance profile, IMDSv2, EBS encryption, private networking, and tight security groups |

Example RDS avoiding public access:

    Resources:
      AppDatabase:
        Type: AWS::RDS::DBInstance
        Properties:
          PubliclyAccessible: false
          StorageEncrypted: true
          DeletionProtection: true

Not every resource uses the same properties or encryption mechanisms. Cross-check resource specifications and service documentation before copying configurations.

## 17. Network Security in IaC

Security groups act as stateful firewalls at the network interface/resource level. Rules should reflect actual application traffic flows.

Example where a database accepts PostgreSQL connections only from the application's security group:

    Resources:
      DatabaseIngress:
        Type: AWS::EC2::SecurityGroupIngress
        Properties:
          GroupId: !Ref DatabaseSecurityGroup
          IpProtocol: tcp
          FromPort: 5432
          ToPort: 5432
          SourceSecurityGroupId: !Ref ApplicationSecurityGroup

Avoid rules such as:

- SSH TCP/22 from `0.0.0.0/0` or `::/0`.
- RDP TCP/3389 from the Internet.
- Database ports open to the entire Internet.
- All traffic open to all CIDRs without justification.
- Unrestricted egress in environments requiring strict egress controls.

Not every workload belongs in public subnets. Databases and internal services normally sit in private subnets; public entry points can be an ALB/API Gateway/WAF depending on architecture.

Use VPC endpoints where appropriate so workloads reach AWS services over private connectivity. Endpoint policies and resource policies still require review.

## 18. Validating CloudFormation Templates with cfn-lint

`cfn-lint` checks templates against CloudFormation resource specifications and rules covering structure, properties, intrinsic functions, and best practices.

Install and run in development/CI environments per project workflow:

    pip install cfn-lint
    cfn-lint template.yaml

You can pass multiple template files or formats depending on tool version. Never treat a passing lint check as proof a template is secure: `cfn-lint` does not replace IAM reviews, secret scanning, threat modeling, or policy-as-code.

CloudFormation also provides `validate-template`:

    aws cloudformation validate-template \
      --template-body file://template.yaml

This command verifies basic CloudFormation readability/structural validity. It does not guarantee every resource will provision cleanly and does not prove security settings meet requirements.

## 19. Policy-as-Code with CloudFormation Guard

CloudFormation Guard lets you write rules validating templates against organizational standards. For example, requiring S3 buckets to block public access:

    let s3_buckets = Resources.*[ Type == "AWS::S3::Bucket" ]

    rule s3_buckets_block_public_access when %s3_buckets !empty {
      %s3_buckets.Properties.PublicAccessBlockConfiguration.BlockPublicAcls == true
      %s3_buckets.Properties.PublicAccessBlockConfiguration.IgnorePublicAcls == true
      %s3_buckets.Properties.PublicAccessBlockConfiguration.BlockPublicPolicy == true
      %s3_buckets.Properties.PublicAccessBlockConfiguration.RestrictPublicBuckets == true
    }

Another rule can require encryption:

    rule s3_buckets_use_encryption when %s3_buckets !empty {
      %s3_buckets.Properties.BucketEncryption.ServerSideEncryptionConfiguration[*].ServerSideEncryptionByDefault.SSEAlgorithm
        IN ["AES256", "aws:kms"]
    }

Run validation:

    cfn-guard validate \
      --rules security-rules.guard \
      --data template.yaml

Rules may need adjustment for your Guard version, template structure, conditional resources, and organizational conventions. Test rules with positive/negative fixtures to ensure they catch intended violations without falsely blocking valid templates.

### 19.1. Example Rule for RDS

An organization may require DB instances to be non-public and have storage encryption enabled:

    let db_instances = Resources.*[ Type == "AWS::RDS::DBInstance" ]

    rule rds_instances_are_private when %db_instances !empty {
      %db_instances.Properties.PubliclyAccessible == false
      %db_instances.Properties.StorageEncrypted == true
    }

Do not apply rules to resource types lacking the corresponding properties. With conditions or parameter-derived values, rules must be written to handle them properly; do not treat missing properties as automatically safe.

## 20. IAM Policy Validation with Access Analyzer

IAM Access Analyzer provides policy validation to catch grammar errors, security warnings, general warnings, and suggestions.

Example validating an identity policy:

    aws accessanalyzer validate-policy \
      --policy-document file://runtime-policy.json \
      --policy-type IDENTITY_POLICY

For resource-based policies, choose the matching policy type and supply the resource type if required by the API. Interpret results by finding type:

- ERROR: policy contains an error that must be fixed.
- SECURITY_WARNING: security risk requiring review.
- WARNING: issue or behavior needing attention.
- SUGGESTION: improvement recommendation.

Access Analyzer validation does not replace live permission testing. Use the IAM policy simulator, staging accounts, and integration tests to confirm the workload still has the minimum permissions needed.

## 21. CloudFormation Hooks and Deployment-Time Guardrails

Policy-as-code in CI catches issues early, yet someone could deploy from a different pipeline. CloudFormation Hooks can inspect resources prior to supported lifecycle operations and emit warnings or block the operation depending on hook configuration.

Combine guardrail layers:

- CI lint/Guard/Access Analyzer.
- CloudFormation Hooks in deployment environments.
- SCPs/permission boundaries to cap privileges.
- Least-privilege IAM deployment roles.
- AWS Config rules or conformance packs to detect drift/violations.
- Security Hub to aggregate security findings.

Never assume a Guard rule in CI automatically covers every CloudFormation stack. Protect deployment paths and monitor changes made outside standard pipelines.

## 22. Secrets and Policies in CI/CD Pipelines

Pipelines can become secret leak vectors if they:

- Print all environment variables.
- Enable shell tracing on commands containing tokens.
- Pass secrets via command-line arguments.
- Upload rendered config files into public artifacts.
- Save plans/templates with interpolated secrets.
- Use long-lived IAM user credentials.
- Run jobs from forks/untrusted pull requests with production privileges.

Pipeline design:

1. Use OIDC/federated identities to obtain temporary AWS credentials when supported by the CI platform.
2. Use separate roles for build, test, and deploy.
3. Never expose production secrets to pull requests from forks or untrusted branches.
4. Fetch secrets into job runtime only when needed, limiting lifetime and read scope.
5. Disable shell debug/tracing around secret-handling sections.
6. Mask secrets in logs, without treating masking as the sole safeguard.
7. Never store secrets in artifacts, caches, or test reports.
8. Audit CloudTrail and CI job identities.

## 23. Change Sets and Pre-Deployment Security Review

A change set shows which resources CloudFormation plans to add, modify, delete, or replace. It is a critical checkpoint before applying.

Review changes for:

- Do new IAM roles/policies expand permissions?
- Do trust policies add principals or remove conditions?
- Do resource policies open public or cross-account access?
- Was a secret reference replaced with plaintext?
- Was an encryption key changed or removed?
- Did an S3 bucket change `PublicAccessBlock`, ACLs, ownership, or policies?
- Did RDS become public or disable deletion protection?
- Did security groups open additional ports/CIDRs?
- Are data resources undergoing replacement or deletion?
- Were KMS key policies/grants broadened?

Change sets do not catch every security issue and do not guarantee runtime outcomes. Combine change sets with lint, Guard, Access Analyzer, and manual reviews.

## 24. Drift Detection and Runtime Configuration Checks

IaC describes desired state; operators or services can modify resources directly. CloudFormation drift detection compares selected actual properties against the template.

Drift detection has limitations:

- Not every resource/property supports drift detection.
- Certain properties are excluded or uncomparable.
- Dynamic references do not mean drift detection detects secret rotation or compares resolved plaintext.
- Drift detection does not replace AWS Config, CloudTrail, or service-specific audits.

Use AWS Config to check requirements such as S3 public access, encryption, security group exposure, RDS public access, and logging. Verify Config coverage and recording scope; a rule cannot evaluate a resource if its resource type is not recorded.

## 25. Policy Exceptions and Handling Process

Some workloads legitimately require special permissions or configurations. Do not create permanent exceptions merely because a template failed a gate.

Every exception should specify:

- Specific resource/stack/account/Region.
- Violated rule and business justification.
- Accountable owner.
- Blast radius and risk assessment.
- Compensating controls.
- Expiration date or review date.
- Testing evidence and approvals.

For example, an S3 bucket needing public read for static content distribution must undergo architecture review, WAF/CDN strategy, and clear object scoping. If CloudFront is the distribution point, prefer Origin Access Control with a private bucket rather than opening the bucket directly.

## 26. Incident Response for Exposed Secrets or Policies

### 26.1. Exposed Secret

1. Revoke/rotate the secret or access key.
2. Identify potentially affected principals, resources, accounts, and timeframe.
3. Inspect CloudTrail, Secrets Manager access events, and service logs.
4. Check for signs of persistence or anomalous resources.
5. Update applications and verify new credentials work.
6. Purge the secret from templates, Git, artifacts, and CI logs per procedure.
7. Add secret scanning and policy gates to prevent recurrence.

### 26.2. Overly Broad IAM Policy

1. Identify the overly broad role/user and resources/actions.
2. Check CloudTrail to identify permissions actually used.
3. Author a narrower policy based on real workload access.
4. Test in staging and roll out in a controlled manner.
5. Revoke the old policy and verify applications keep working.
6. Audit other roles sharing the same pattern.
7. Add an automated rule for the detected flaw.

Do not strip permissions actively used in production without understanding dependencies. During severe incidents, containment may take priority over availability; follow your organization's incident response process.

## 27. Example IaC Verification Pipeline

A simple pipeline can run these steps before deployment:

    1. Checkout source
    2. Secret scan on diff and repository
    3. cfn-lint template.yaml
    4. cfn-guard validate --rules security-rules.guard --data template.yaml
    5. IAM Access Analyzer validate-policy for each IAM policy
    6. CloudFormation validate-template
    7. Create change set
    8. Review findings and change set
    9. Approve deployment
    10. Execute change set
    11. AWS Config / runtime security checks

Each gate should emit traceable output: commit SHA, template version, rule-set version, tool version, findings, exception ID, and deployment identity.

Never ignore findings just to turn a pipeline green. If a finding is accepted, record an exception with an owner and expiration date.

## 28. Scenario Exercises

### Exercise A — IAM Policy with Action: "*" and Resource: "*"

A Lambda only needs to read objects from one bucket, yet its role is granted full permissions.

**Answer:** Replace with `s3:GetObject` on the required object ARN and `s3:ListBucket` if the application truly needs to list the bucket. Separate logging and secret permissions into distinct statements.

### Exercise B — Trust Policy Allowing Principal "*"

A role has a trust policy allowing any principal in the policy.

**Answer:** Identify the exact workload principal, restrict accounts/roles, and add appropriate conditions. If cross-account third-party, evaluate `ExternalId` and confused deputy risks.

### Exercise C — iam:PassRole on All Roles

A deployment role has `iam:PassRole` on `Resource: "*"`.

**Answer:** Restrict allowed passable role ARNs and use `iam:PassedToService` where appropriate. Also review permissions to create/modify roles and attach policies.

### Exercise D — Password Inside Template

A developer writes a password directly inside CloudFormation Properties.

**Answer:** Rotate if already committed/shared; move the secret to Secrets Manager or SSM SecureString and use appropriate dynamic references/runtime retrieval.

### Exercise E — NoEcho Enabled

A parameter has `NoEcho: true`, yet the secret still appears in Outputs.

**Answer:** Remove the secret from Outputs. NoEcho does not mask values stored in Outputs or Metadata and does not replace a secret manager.

### Exercise F — Secrets Manager Rotation

A database secret rotated, yet the application still uses the old password.

**Answer:** Check cache TTL, connection pool, rotation workflow, and how the application refreshes secrets. Dynamic references in CloudFormation do not auto-update resources merely because a secret rotated.

### Exercise G — Public S3 Bucket

A template has a bucket policy allowing `Principal: "*"` with no restrictions.

**Answer:** Determine whether public access is truly required; prefer a private bucket with CloudFront Origin Access Control. Enable Block Public Access and restrict the policy.

### Exercise H — Non-TLS S3 Requests

A bucket policy does not deny insecure transport.

**Answer:** Add an explicit `Deny` with condition `aws:SecureTransport=false` covering the bucket and object ARNs, after verifying client compatibility.

### Exercise I — Public RDS Access

A production DB instance has `PubliclyAccessible: true` and a security group opening 5432 to `0.0.0.0/0`.

**Answer:** Move the DB into private subnets, set `PubliclyAccessible` to `false`, and permit only the application security group as the source.

### Exercise J — KMS Decrypt Returns AccessDenied

An IAM role has `kms:Decrypt`, yet the KMS key policy does not allow that principal or appropriate delegation.

**Answer:** Review the key policy, grants, encryption context, and `ViaService`. Never grant `kms:*` on all keys as a quick fix.

### Exercise K — CloudFormation Guard Reports Missing Encryption

An older template lacks `BucketEncryption`.

**Answer:** Assess impact and add standardized encryption configuration. If the bucket already contains data, check existing object behavior and default/bucket policy encryption requirements before rollout.

### Exercise L — Secret Scan Finds Access Key in Git History

A developer deletes the line containing the key in a new commit.

**Answer:** Revoke/rotate the key, audit CloudTrail, scrub the secret from history/artifacts per procedure, and add secret scanning. Deleting from a new commit does not invalidate an exposed key.

### Exercise M — Change Set Swaps Runtime Role

A change set replaces a Lambda's execution role with a broader-privileged role.

**Answer:** Compare trust policies and permission policies, verify resources/actions/conditions, check `iam:PassRole`, and approve only when permissions adhere to least privilege.

### Exercise N — Dynamic Reference for a Secret

A template contains a Secrets Manager dynamic reference, yet the CloudFormation service role lacks permission to read the secret.

**Answer:** Grant `secretsmanager:GetSecretValue` on the specific secret and `kms:Decrypt` if a CMK is required, after verifying which principal actually resolves the reference.

### Exercise O — Drift Detection Misses Secret Rotation

A secret rotated, yet drift detection reports no differences.

**Answer:** Do not treat drift detection as a rotation-detection mechanism. Monitor Secrets Manager versions/staging labels and verify application/resource integration separately.

## 29. Review Questions

1. Why can a syntactically valid template still be insecure?
2. Where do identity policies and resource policies differ?
3. What does an IAM role's trust policy determine?
4. Do SCPs grant permissions to principals by themselves?
5. How is Explicit Deny evaluated relative to Allow?
6. Why should `AdministratorAccess` not be used for runtime roles?
7. When might a wildcard `Resource` be necessary?
8. How does an S3 bucket ARN differ from an object ARN?
9. What action does `iam:PassRole` authorize?
10. What does the `iam:PassedToService` condition help restrict?
11. Which risk does `ExternalId` address?
12. Why does the KMS key policy matter even when the IAM policy already allows `kms:Decrypt`?
13. When should Secrets Manager be chosen over Parameter Store String?
14. Does SecureString provide a built-in rotation workflow?
15. Does NoEcho encrypt secrets inside a template?
16. Why should secrets never be placed in Outputs or Metadata?
17. When are dynamic references resolved?
18. Does secret rotation automatically trigger a CloudFormation update?
19. Why should runtime applications use IAM roles instead of static access keys?
20. What risk arises from caching secrets for too long?
21. Does S3 Versioning replace Block Public Access?
22. Does encryption at rest replace IAM authorization?
23. Why should a database security group accept traffic from the application security group?
24. Does cfn-lint replace IAM Access Analyzer?
25. What does CloudFormation Guard check?
26. How do CloudFormation Hooks differ from CI policy checks?
27. Which changes does a change set help reviewers spot?
28. Does drift detection check every resource/property?
29. When a secret is exposed, why is deleting it from Git insufficient?
30. What information does a policy exception require?

**Quick answers:** (1) it can have flawed permissions/configurations; (2) one attaches to an identity, the other attaches to a resource; (3) which principals can AssumeRole; (4) no; (5) Deny wins; (6) reduces blast radius; (7) when an action lacks resource-level support or the service requires it; (8) bucket ARNs and object ARNs apply to different actions; (9) passing a role to an AWS service; (10) restricts which service receives the role; (11) confused deputy; (12) KMS authorization includes key policies/grants; (13) secrets needing lifecycle/rotation/auditing; (14) no; (15) no; (16) NoEcho does not hide them; (17) when CloudFormation processes the resource property; (18) no; (19) temporary credentials; (20) delayed adoption of new secrets; (21) no; (22) no; (23) narrows the network source; (24) no; (25) custom rules on templates; (26) Hooks can block during deployment lifecycle; (27) Add/Modify/Remove/Replace; (28) no; (29) the credential can still be used; (30) scope, justification, owner, risk, compensating controls, and expiration date.

## 30. Production Checklist

- [ ] IAM identity policies grant only required actions/resources/conditions.
- [ ] Trust policies restrict principals and include appropriate conditions.
- [ ] `iam:PassRole` restricts role ARNs and receiving services.
- [ ] Resource policies do not inadvertently open public or cross-account access.
- [ ] KMS key policies separate key administrators and key users.
- [ ] No plaintext secrets in templates, source, metadata, outputs, or tags.
- [ ] NoEcho is not used as a replacement for a secret manager.
- [ ] Secrets Manager/SSM SecureString have tightly scoped IAM/KMS access.
- [ ] Runtime workloads use IAM roles/temporary credentials.
- [ ] Secret rotation, cache refresh, and connection pools are tested.
- [ ] Dynamic references are used only in supported properties/contexts.
- [ ] S3 Block Public Access and encryption are configured.
- [ ] TLS is enforced for appropriate data access.
- [ ] RDS/DynamoDB/EBS encryption, backups, and deletion controls meet requirements.
- [ ] Security groups do not expose management/database ports to the Internet.
- [ ] cfn-lint, CloudFormation Guard, and IAM Access Analyzer run in CI.
- [ ] Secret scanning checks both changes and repository history.
- [ ] Change sets are reviewed before production deployment.
- [ ] CloudFormation Hooks/SCP/IAM guardrails protect deployment paths.
- [ ] AWS Config, CloudTrail, and Security Hub have appropriate coverage.
- [ ] Drift detection limitations are understood and supplemented with runtime checks.
- [ ] Policy exceptions have owners, justifications, compensating controls, and expiry dates.
- [ ] Procedures exist to rotate/revoke, audit, and recover if a secret/policy is exposed.

## 31. Summary

Checking policies, secrets, and secure configurations in IaC is an end-to-end process protecting infrastructure from source code to runtime:

- IAM policies must follow least privilege; trust policies, resource policies, permission boundaries, and SCPs serve distinct roles.
- Wildcards, public principals, and `iam:PassRole` must be reviewed against actual actions, resources, conditions, and workloads.
- Secrets must be stored in Secrets Manager or SSM SecureString as appropriate; runtimes should use IAM roles and temporary credentials.
- NoEcho only masks certain parameter displays; it does not encrypt templates or protect secrets in Outputs/Metadata.
- Dynamic references avoid plaintext in templates, yet resolve when CloudFormation processes resource properties; rotation does not automatically trigger stack updates.
- S3, RDS, DynamoDB, EBS, KMS, and network resources require service-appropriate secure defaults.
- cfn-lint, CloudFormation Guard, IAM Access Analyzer, secret scanning, change sets, and CloudFormation Hooks form layered checks.
- Runtime controls like AWS Config, CloudTrail, and Security Hub detect post-deployment drift and violations.
- When a secret is exposed, revoking/rotating credentials and auditing usage matter more than merely deleting lines from Git.

Secure IaC makes access explicit, keeps secret lifecycles controlled, and automates security verification before every deployment.

### Official AWS Documentation

1. IAM policies and permissions: https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html
2. IAM policy evaluation logic: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html
3. IAM best practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
4. Grant a user permissions to pass a role to an AWS service: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html
5. IAM Access Analyzer policy validation: https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html
6. CloudFormation dynamic references: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html
7. CloudFormation NoEcho parameters: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html
8. AWS Secrets Manager best practices: https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html
9. Secrets Manager rotation: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html
10. Systems Manager Parameter Store SecureString: https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html
11. CloudFormation Guard: https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html
12. cfn-lint: https://github.com/aws-cloudformation/cfn-lint
13. CloudFormation Hooks: https://docs.aws.amazon.com/cloudformation-cli/latest/hooks-userguide/what-is-cloudformation-hooks.html
14. S3 Block Public Access: https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
15. S3 Object Ownership: https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html
16. RDS encryption: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html
17. DynamoDB encryption at rest: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/EncryptionAtRest.html
18. AWS Config managed rules: https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html
19. AWS CloudTrail: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html
20. AWS Well-Architected Security Pillar: https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html
