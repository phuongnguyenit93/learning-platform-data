# Choosing Secrets Manager or Parameter Store

AWS applications frequently need to read values such as service endpoints, bucket names, feature settings, API keys, database passwords, or external provider tokens. These values vary in sensitivity and lifecycle. Storing everything in configuration files, static environment variables, or source code makes it easy to leak sensitive information, hard to control access, and risky to change as the system scales.

AWS provides two services commonly considered for this need:

- **AWS Secrets Manager** is designed to manage secrets such as database credentials, API keys, and tokens. It provides specialized capabilities including secret rotation, integration with certain data services, cross-Region secret replication, and state-based version management.
- **AWS Systems Manager Parameter Store** manages configuration data by name and hierarchy. It supports **String**, **StringList**, and **SecureString** types, integrates with IAM/KMS, retains version history, and offers tiers with different limits, policies, and pricing models.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, the right choice ensures applications running on EC2, ECS, EKS, Lambda, or CI/CD pipelines receive configuration and credentials in a controlled manner. The module aims to help learners design and deploy applications that are secure, observable, recoverable, and cost-controlled; therefore, you must weigh data sensitivity, how the application consumes data, IAM permissions, KMS, change lifecycles, and operational requirements.

## 1. Two Services Addressing Two Sets of Needs

Secrets Manager and Parameter Store overlap: both store values outside source code, enforce access controls, and let applications retrieve values via APIs or SDKs. In Parameter Store, only the `SecureString` type uses KMS to encrypt values this way. However, the two services have different focuses.

Parameter Store fits centralized configuration management such as service URLs, queue names, approved AMI IDs, feature limits, bucket names, or simple sensitive values encrypted as `SecureString`. Hierarchies organize parameters by application, environment, and component.

Secrets Manager fits values that are credentials or tokens with a dedicated security lifecycle. It tracks secret versions, schedules rotation, coordinates updating credentials on target systems, and supports cross-Region replication. Some AWS services can create and manage secrets on the user's behalf.

| Question | Starting point to consider |
|---|---|
| Is the value non-sensitive configuration such as an endpoint, queue name, or AMI ID? | Parameter Store `String` |
| Does the value need encryption, without a dedicated rotation mechanism? | Parameter Store `SecureString` |
| Do you need to store a DB password, API key, or token with a secret lifecycle? | Secrets Manager |
| Do you need automatic credential rotation that updates the target system? | Secrets Manager |
| Do you need to store many configs by path and read them as a group? | Parameter Store |
| Do you need to share advanced parameters across accounts? | Parameter Store advanced shared parameters |
| Do you need to replicate secrets to another Region for multi-Region apps? | Secrets Manager replication |
| Do you need expiration policies or alerts when a parameter has not changed for too long? | Parameter Store advanced parameter policies |

Do not decide based solely on whether a value is a password. Also ask who reads the data, how often it changes, whether rotation is required, whether the target system supports rotation, whether the application tolerates disruption during credential swaps, and what the cost looks like at scale.

## 2. Comparing Core Capabilities

| Criterion | AWS Secrets Manager | Systems Manager Parameter Store |
|---|---|---|
| Primary purpose | Secret management and credential lifecycle | Centralized configuration and parameter management |
| Data types | Secret value typically string or JSON; can hold multi-field credentials | `String`, `StringList`, `SecureString` |
| Encryption | Encrypts secrets with AWS KMS | `SecureString` uses KMS to encrypt values |
| Automatic rotation | Managed rotation for certain secrets and Lambda-based rotation for others | No built-in dedicated credential rotation workflow; custom automation possible |
| Versioning | Version IDs and staging labels such as `AWSCURRENT`, `AWSPREVIOUS`, `AWSPENDING` | Incremental numeric versions and parameter labels |
| Naming hierarchy | Secret names and tags; no path hierarchy equivalent to Parameter Store | Path-based hierarchy, up to 15 levels |
| Multi-Region replication | Supports replicating secrets to other Regions | No equivalent multi-Region parameter replica model; requires separate deployment/sync |
| Cross-account sharing | Resource policy, IAM, and customer managed KMS key | Shared advanced parameters via AWS RAM |
| Parameter policies | Does not follow Parameter Store's expiration/no-change model | Advanced tier supports `Expiration`, `ExpirationNotification`, `NoChangeNotification` |
| Service integrations | Specialized integrations with certain services and rotation workflows | Broad integration with Systems Manager, EC2, CloudFormation, and other workflows |
| Cost | Charged per stored secret and API call; rotation may incur Lambda charges | Standard has no storage surcharge; advanced tier and high throughput incur charges |

Limits, pricing, and features can change by Region and over time. Before designing a production system, check current AWS documentation and pricing pages rather than hardcoding static numbers into architectures.

## 3. Classifying Data Before Choosing a Service

Classify values by sensitivity and usage pattern. An e-commerce application might have the following data:

| Data | Nature | Reference choice |
|---|---|---|
| `ORDERS_QUEUE_URL` | Endpoint, non-secret | Parameter Store `String` |
| `PAYMENTS_API_BASE_URL` | Endpoint, non-secret | Parameter Store `String` |
| `FEATURE_CHECKOUT_V2` | Configuration flag | Parameter Store, or AWS AppConfig if rollout management is needed |
| `DATABASE_PASSWORD` | Credential likely needing rotation | Secrets Manager |
| `PAYMENT_PROVIDER_API_KEY` | Externally issued API key needing lifecycle management | Secrets Manager |
| `LICENSE_KEY` | Sensitive value, rarely changes | Parameter Store `SecureString` or Secrets Manager depending on audit and lifecycle needs |
| `APPROVED_AMI_ID` | Approved resource ID | Parameter Store `String` |
| `PRIVATE_SIGNING_KEY` | Cryptographic key with special usage and protection requirements | Consider AWS KMS or AWS CloudHSM; do not store raw private keys as an ordinary parameter by default |

A secret is sensitive data requiring strict control over who reads it, when it is read, and how it is changed. A configuration parameter describes an application's behavior or runtime environment. Non-sensitive configuration values can still be critical for availability; conversely, an infrequently changing secret still demands strict protection.

If an application needs percentage-based feature flag rollouts, pre-release config validation, or controlled deployments, consider AWS AppConfig. Parameter Store works well for storing configuration, while AppConfig adds configuration deployment workflows and rollout controls. Both services can work together.

## 4. Parameter Store: Structure and Parameter Types

Parameter Store is a capability of AWS Systems Manager. Parameters have unique names within an account and Region. You can use hierarchical paths to organize data by application, environment, and configuration group.

Example:

~~~text
/shop/orders/dev/database/host
/shop/orders/dev/database/port
/shop/orders/prod/database/host
/shop/orders/prod/database/password
/shop/payments/prod/provider/api-url
/shop/payments/prod/provider/api-key
/platform/approved-amis/al2023
~~~

Parameter names organize data, but a path itself is not an automatic security boundary. IAM policies determine which principals can read or write parameters. Design paths alongside policies, especially when using `GetParametersByPath`.

### 4.1. String

`String` stores plaintext not encrypted by KMS like a `SecureString`. Use it for non-sensitive configuration such as endpoints, queue names, AMI IDs, or boolean strings.

~~~bash
aws ssm put-parameter \
  --name "/shop/orders/prod/feature/checkout-v2" \
  --type "String" \
  --value "enabled" \
  --description "Enable checkout v2"
~~~

Do not store passwords or tokens in a `String` just because the parameter sits under `/prod`. The path does not encrypt values and does not replace authorization.

### 4.2. StringList

`StringList` stores a comma-separated list of values. For example, a list of subnet IDs or endpoint names can be stored in one parameter. This type is convenient for simple lists, but it is not a general JSON format and does not support nested structures.

~~~bash
aws ssm put-parameter \
  --name "/shop/orders/prod/allowed-regions" \
  --type "StringList" \
  --value "ap-southeast-1,ap-southeast-2"
~~~

If an application needs complex objects, use JSON inside `String`/`SecureString` where appropriate, or split into clearly named separate parameters.

### 4.3. SecureString

`SecureString` is for values needing AWS KMS protection, such as license keys, tokens, or infrequently changing credentials. Parameter Store encrypts the value on write and returns plaintext only when the caller requests decryption, such as calling `GetParameter` with `WithDecryption=true`.

~~~bash
aws ssm put-parameter \
  --name "/shop/orders/prod/integration/license-key" \
  --type "SecureString" \
  --key-id "alias/shop-parameter-key" \
  --value "REPLACE_WITH_SECRET_VALUE" \
  --description "License key for Orders integration"
~~~

The example uses a placeholder instead of a real credential. Never put real secret values directly in shell history, CI logs, committed scripts, or logged command lines. In automation, pull values from a secure channel and restrict who can run the command.

To read the parameter:

~~~bash
aws ssm get-parameter \
  --name "/shop/orders/prod/integration/license-key" \
  --with-decryption
~~~

Without `--with-decryption`, the API returns the ciphertext/protected value instead of plaintext. The caller needs `ssm:GetParameter` and `kms:Decrypt` on the key used for decryption.

## 5. Parameter Tiers and Throughput

Parameter Store has Standard and Advanced tiers. Tiers govern storage limits, value sizes, parameter policies, and cross-account sharing. Tier is distinct from throughput: throughput governs request rate, not parameter capacity.

| Attribute | Standard | Advanced |
|---|---:|---:|
| Maximum count per account/Region | 10,000 | 100,000 |
| Maximum value size | 4 KB | 8 KB |
| Parameter policies | No | Yes |
| Cross-account sharing | No | Yes, via AWS RAM |
| `DataType` values `url`, `json`, `jsonc` | Not supported | Supported |
| Storage cost | No surcharge | Charged |
| Tier upgrade | Yes | Cannot downgrade to Standard |

Use Standard for most ordinary configuration. Choose Advanced only when you need larger values, counts exceeding Standard limits, parameter policies, or cross-account sharing. Promoting a parameter to Advanced should be treated as a lifecycle decision because an Advanced parameter cannot be downgraded back to Standard.

### Parameter Policies

Advanced parameters support policies for lifecycle management:

- **Expiration:** deletes the parameter at a specified time.
- **ExpirationNotification:** emits an EventBridge event notifying ahead of expiration.
- **NoChangeNotification:** emits an event if the parameter has not changed within a configured interval.

For example, a policy can remind operations to review an approved AMI ID if the parameter has not been updated in 60 days. This is a parameter lifecycle notification mechanism, not an automated credential rotation mechanism equivalent to Secrets Manager.

### Throughput

If an application calls Parameter Store at high frequency, review default throughput and high-throughput settings per account/Region. High throughput can incur charges. Do not raise throughput before measuring request rates, using appropriate caching, and eliminating redundant reads.

## 6. Secrets Manager: Secrets, Versions, and Staging Labels

Secrets Manager stores a secret as a secret resource with metadata, versions, and staging labels. The value can be a plain string or JSON, for example:

~~~json
{
  "username": "orders_app",
  "password": "REPLACE_WITH_SECRET_VALUE",
  "engine": "mysql",
  "host": "orders-db.example.internal",
  "port": 3306,
  "dbname": "orders"
}
~~~

Applications can retrieve the full JSON and parse needed fields. Avoid placing passwords in descriptions, tags, or secret names because metadata is often readable by broader principals than secret values.

Secrets Manager manages versions. A version can carry one or more staging labels; common labels include:

- **AWSCURRENT:** the version currently considered the active credential.
- **AWSPREVIOUS:** the previous version.
- **AWSPENDING:** the version being prepared during a rotation workflow.

Applications normally read `AWSCURRENT` unless specifying another version. When rotation finishes, the current label moves to the new version. Consequently, applications do not need to know a specific version number each time they retrieve the secret.

You can create a secret via CLI:

~~~bash
aws secretsmanager create-secret \
  --name "shop/orders/prod/database" \
  --description "Database credentials for Orders production" \
  --secret-string '{"username":"orders_app","password":"REPLACE_WITH_SECRET_VALUE"}'
~~~

Never use real passwords in illustrative commands or logs. In production, prefer creating secrets via console, IaC, or secure automation, passing secret values from secure sources.

## 7. Encryption with AWS KMS and Access Permissions

### 7.1. Secrets Manager

Secrets Manager encrypts secret values using AWS KMS. You can use the AWS managed key `aws/secretsmanager` or a customer managed KMS key. A customer managed key is useful when you need key policy control, decryption auditing, per-application permission isolation, or cross-account sharing.

Callers typically need `secretsmanager:GetSecretValue`. When a secret uses a customer managed key, callers and services need appropriate KMS permissions to decrypt. For cross-account sharing, the AWS managed key `aws/secretsmanager` cannot be used; you need a customer managed key and a key policy allowing the target account/principal.

### 7.2. Parameter Store SecureString

`SecureString` uses KMS to encrypt values. With the default `aws/ssm` key, fine-grained control over who can decrypt is more limited because principals in the account with permission to read the parameter may be allowed to decrypt under the default key configuration. If you need to separate read/decrypt permissions across groups of secrets, use a customer managed key with properly scoped IAM/key policies.

To read a `SecureString`, a principal needs:

1. Systems Manager permissions such as `ssm:GetParameter` on the parameter ARN.
2. `kms:Decrypt` on the KMS key used to encrypt the parameter.
3. Permission from the key policy to use the key.

For standard `SecureString`, writes use KMS `Encrypt`; for advanced `SecureString`, Parameter Store uses a data key and requires corresponding KMS permissions such as `kms:GenerateDataKey`. Grant permissions matching the tier and current KMS guidance.

### 7.3. Least Privilege and Path Hierarchy

Permissions can be scoped by parameter ARN, but pay attention to how `GetParametersByPath` is authorized by IAM. If a principal has permission to read a parent path with `recursive=true`, the principal can read child parameters beneath that path—even if a policy attempts a conventional deny on a child resource in certain patterns. Therefore, do not share a broad parent path with a role that should only read a single sensitive parameter.

For example, separate paths by application and environment:

~~~text
/shop/orders/dev/*
/shop/orders/prod/*
/shop/payments/prod/*
~~~

Then assign roles per application and environment, checking `GetParameter`, `GetParameters`, `GetParameterHistory`, and `GetParametersByPath`. `GetParameterHistory` can return versions including the current version, so do not overlook this API when restricting reads. For `GetParametersByPath`, check permissions on all parent paths callable in recursive mode. For `SecureString`, restricting `kms:Decrypt` with a customer managed key adds another layer of decryption control.

## 8. Rotation: When Do You Need Secrets Manager?

Rotation updates credentials in both the secret store and the target system. Changing a password only in Secrets Manager without updating the database or API provider breaks application connectivity. Likewise, changing credentials on the target system without updating the secret breaks all clients using the old credential.

Secrets Manager offers three main approaches:

1. **Managed rotation:** used for certain secrets managed by AWS services, such as secrets created through integrated data-service workflows. The service handles rotation without customers writing a rotation Lambda.
2. **Lambda rotation:** Secrets Manager invokes a Lambda function on schedule. The function updates credentials on the target system and versions the secret.
3. **Managed external secrets rotation:** used for certain supported partner secrets, enabling rotation on external systems via built-in integrations.

With Lambda rotation, the standard process has four steps:

| Step | Purpose |
|---|---|
| `createSecret` | Create a new version and attach a pending stage such as `AWSPENDING` |
| `setSecret` | Update the credential in the database or target system |
| `testSecret` | Attempt authentication using the new credential |
| `finishSecret` | Move `AWSCURRENT` to the new version and complete rotation |

Rotation schedules use `rate()` or `cron()` expressions evaluated in UTC. Choose a window aligned with maintenance hours, retry capability, and application fault tolerance.

### Single-User and Alternating-Users

With the **single-user** strategy, rotation changes one user's password. This is simple and fits many scenarios, though there is a brief window during password replacement where applications may see authentication failures if they fetch secrets or open new connections right as the credential changes. Applications need proper retries and connection pools may need to open fresh connections.

With the **alternating-users** strategy, two equivalent users are updated alternately. During rotation, one user remains valid while the other user's credential changes, reducing disruption risk for high-availability applications. This pattern requires careful database permission design and an administrative credential authorized to clone or update the alternate user.

Not every target system supports managed rotation. For external provider API keys, verify whether the provider API can issue a new key, keep old and new keys active concurrently during cutover, and expose a key revocation endpoint. If no API supports this, you may need a custom workflow or controlled manual rotation process.

## 9. Scheduling Rotation and Operating Safely

Example configuring rotation for a secret that already has a rotation Lambda function:

~~~bash
aws secretsmanager rotate-secret \
  --secret-id "shop/orders/prod/database" \
  --rotation-lambda-arn "arn:aws:lambda:ap-southeast-1:111122223333:function:RotateOrdersDatabaseSecret" \
  --rotation-rules '{"ScheduleExpression":"rate(30 days)","Duration":"2h"}'
~~~

This illustrates the CLI structure. The Lambda function, invoke permissions, database connectivity, and secret must be configured beforehand. Never copy placeholder ARNs into production.

Items to check:

- The rotation Lambda can reach both the secret and the target system over the network.
- The Lambda execution role has only required permissions.
- The secret resource policy and KMS key policy permit the appropriate operations.
- The target system accepts credential updates and has retry handling.
- Logs never record plaintext passwords or tokens.
- CloudWatch alarms monitor rotation failures and execution duration.
- A runbook exists to stop rotation and resolve stuck `AWSPENDING` states.
- Applications refresh secrets when needed rather than caching stale credentials indefinitely.

If rotation fails, investigate step by step: `createSecret`, `setSecret`, `testSecret`, `finishSecret`, IAM/KMS permissions, networking, database connectivity, and version staging labels. Never manually delete versions or move labels without understanding the target system's state.

## 10. How Do Applications Retrieve Secrets and Parameters?

Applications should retrieve values using the SDK with an IAM role attached to the workload. EC2 uses an instance profile; ECS uses a task role; Lambda uses an execution role; EKS can use IAM Roles for Service Accounts or EKS Pod Identity per the configured model. Never bake static access keys into container images or source code.

### Retrieving Secrets from Secrets Manager via AWS CLI

~~~bash
aws secretsmanager get-secret-value \
  --secret-id "shop/orders/prod/database" \
  --query SecretString \
  --output text
~~~

This command prints the secret value to the terminal; use it only for illustration in a secure environment. Never print results into CI logs, shell transcripts, or tickets.

### Retrieving Parameters via AWS CLI

~~~bash
aws ssm get-parameters \
  --names "/shop/orders/prod/database/host" "/shop/orders/prod/database/port" \
  --with-decryption
~~~

When reading a `SecureString`, the caller needs `kms:Decrypt`. For multiple parameters, `GetParameters` reduces call counts compared to fetching each parameter individually.

### Caching to Reduce Latency and API Calls

Applications can use the AWS Secrets Manager caching client or a controlled cache to reduce API calls and latency. Parameter Store values can also be cached in the application or via an appropriate extension/integration. Caches need a TTL and refresh mechanism for when secrets rotate or config changes.

An overly long TTL causes applications to keep using old credentials after rotation. An overly short TTL increases API requests and cost. With connection pools, ensure the application opens new connections using the new credential when the cache refreshes; do not assume existing connections automatically re-authenticate.

## 11. CloudFormation and Infrastructure as Code Integration

Never write plaintext secrets directly into templates, parameter files, or outputs. CloudFormation supports dynamic references to resolve values from Secrets Manager or Parameter Store during stack operations.

### Secrets Manager Dynamic Reference

Example using a JSON secret as a database password:

~~~yaml
Resources:
  OrdersDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      Engine: mysql
      DBInstanceClass: db.t4g.small
      AllocatedStorage: 20
      MasterUsername: orders_admin
      MasterUserPassword: '{{resolve:secretsmanager:shop/orders/prod/database:SecretString:password}}'
~~~

This example illustrates reference syntax only. Production templates need subnet groups, security groups, storage encryption, backups, deletion protection, and appropriate RDS properties. Do not use dynamic references in properties forming primary resource identifiers or anywhere values could be exposed in resource names or outputs.

### Parameter Store SecureString Dynamic Reference

CloudFormation can reference a `SecureString` using `ssm-secure` syntax in supported resource properties:

~~~yaml
Resources:
  OrdersDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      Engine: mysql
      MasterUsername: orders_app
      MasterUserPassword: '{{resolve:ssm-secure:/shop/orders/prod/database/password:3}}'
~~~

The `ssm-secure` dynamic reference requires a parameter name and optionally a numeric version. CloudFormation does not support accessing cross-account Parameter Store `SecureString` values via this reference type; parameter labels and public parameters are also unsupported in dynamic references. Use it only in AWS-supported resource properties.

Dynamic references avoid storing plaintext in templates, but they do not replace IAM permissions on the CloudFormation execution role or KMS permissions. Additionally, resolved values may be passed to the target service to create/update the resource; verify how the target service stores or displays those values.

## 12. Sharing Across Accounts and Regions

### 12.1. Cross-Account Secrets Manager

For a principal in another account to read a secret, coordinate:

1. A resource-based policy attached to the secret in the owning account.
2. An identity-based policy for the principal in the consuming account.
3. A customer managed KMS key and key policy permitting decryption.

The AWS managed key `aws/secretsmanager` is unsuitable for cross-account access. Restrict to specific principals, required actions, and resources; enable `BlockPublicPolicy` when creating resource policies to help prevent public exposure. Avoid granting broad `PutResourcePolicy` permissions since a principal could alter the policy to widen access.

### 12.2. Secrets Manager Multi-Region Replication

Secrets Manager supports replicating a secret from a primary Region to one or more replica Regions. When the secret value changes in the primary, changes propagate to replicas via replication. This process can be asynchronous, so applications in receiving Regions must handle propagation lag and replication status.

Replicas can use a KMS key in the target Region. If applications require failover, test reading the secret in the standby Region, IAM/KMS permissions, networking, and replica status before an outage happens. Do not treat merely creating a replica as completing an entire DR plan.

### 12.3. Cross-Account Parameter Store

Parameter Store supports sharing Advanced parameters across accounts via AWS Resource Access Manager (AWS RAM). Standard parameters cannot be shared this way. Consuming accounts must accept the resource share when required by configuration, have permission to access the parameter, and have appropriate KMS permissions if the parameter is a `SecureString` encrypted with a customer managed key.

Parameter Store does not provide a multi-Region replica model like Secrets Manager. If the same configuration is needed across multiple Regions, manage it via IaC or synchronization pipelines, clearly defining which Region is the source of truth and how partial update failures are handled.

## 13. Integration with EC2, ECS, EKS, Lambda, and CI/CD

### EC2

Attach an instance profile with read-only permissions for the parameters/secrets needed by applications on the host. Use SSM Agent, startup scripts, or application initialization to retrieve configuration; avoid placing secrets in user data because user data can be retrieved from instance metadata or management APIs by principals with sufficient permissions.

### ECS

ECS task definitions can reference secrets from Secrets Manager or Parameter Store via ECS native integration. When injecting secrets into environment variables, values are loaded at container startup; if a secret rotates, running tasks do not automatically receive new values. Deploy new tasks or use runtime retrieval and refresh mechanisms.

### EKS

Workloads on EKS can retrieve secrets via the AWS SDK using IAM roles through EKS Pod Identity or IRSA. If using the Secrets Store CSI Driver with the AWS provider, secrets can be mounted into pods per configuration. Choose mounted files or runtime APIs based on update requirements, access controls, and how the application reloads files.

### Lambda

The Lambda execution role needs read access only to specific secrets/parameters. Use the AWS Parameters and Secrets Lambda Extension or in-app caching to cut API calls. If secrets rotate, set appropriate TTLs and refresh logic; avoid writing plaintext to logs or returning it in error messages.

### CI/CD

CodeBuild, CodePipeline, or external CI systems should use roles or federation to retrieve secrets only when jobs need them. Never store secrets in repositories, plaintext buildspecs, or artifacts. Limit credential lifetimes, scope permissions by project/environment, and mask sensitive values in logs.

## 14. Cost and Scaling Choices

Cost must be evaluated against usage patterns, not just configuration line counts.

For Secrets Manager, primary factors include the number of stored secrets, API requests, replicas, and supporting rotation components like Lambda. A secret queried continuously by many containers can generate high API call volume without caching.

For Parameter Store, Standard parameters have no storage surcharge per AWS pricing documentation; Advanced parameters and high throughput incur charges. If you pick Advanced solely for small configs without using parameter policies or cross-account sharing, reconsider Standard.

An estimation approach:

1. Count secrets/parameters per application, environment, and Region.
2. Estimate workload instance counts and read frequencies per workload.
3. Determine cache TTLs and refresh rates.
4. Estimate rotation frequency and associated API calls.
5. Account for KMS keys, rotation Lambdas, S3/CloudTrail, or related services if used.
6. Weigh cost against risk impact if credentials are unrotated or configuration is uncontrolled.

Do not try to save money by moving credentials that need rotation into Parameter Store if you end up building and operating a complex custom rotation system. Conversely, you do not need Secrets Manager for every non-sensitive endpoint or ID.

## 15. Common Design Mistakes

### Storing Secrets in a String Parameter

`String` does not provide KMS encryption for values like `SecureString`. Move sensitive values to `SecureString` or Secrets Manager, then audit logs and change history to determine whether plaintext was ever exposed.

### Using SecureString with the Default Key While Expecting Granular Decryption Control

The AWS managed key `aws/ssm` is unsuitable when separating decrypt permissions across teams. Use a customer managed key, key policies, and least-privilege IAM policies.

### Granting Overly Broad Parent Path Read Permissions

`GetParametersByPath` permission on a parent path can allow reading child parameters during recursive calls. Split paths along security boundaries and test path-based read APIs.

### Failing to Account for Rotation in Applications

Secrets may rotate while applications retain credentials in caches or connection pools for too long. Design TTLs, refreshes, retries, and new connection creation; test rotation under realistic load.

### Injecting Secrets into Environment Variables Assuming Automatic Updates

Container-startup secret injection does not update running containers after rotation. Restart tasks/pods via deployment workflows or read secrets at runtime.

### Writing Secrets to Logs or Command History

Never print plaintext, pass secrets on logged command lines, or include secrets in error messages. Use SDKs and secure configuration sources.

### Sharing One Secret Across Multiple Applications

A shared credential widens the blast radius on compromise and complicates per-application revocation. Create separate secrets per workload or trust boundary when the target system permits.

### Copying Secrets Without a Synchronization Process

Manually copying secrets to another Region or account leads to version drift. Use Secrets Manager replication where appropriate or build a synchronized workflow with a source of truth, status checks, and failure alerts.

### Using Dynamic References Where Data Can Leak

Do not reference secrets in primary identifiers, outputs, or custom resources without checking behavior. Verify limits and supported resource properties before using.

## 16. Decision and Implementation Workflow

Use this workflow for each configuration value:

1. **Classify:** determine whether the value is internal non-secret config, sensitive data, or a credential.
2. **Define lifecycle:** who creates, reads, and updates it, how often it changes, and when it expires.
3. **Define rotation:** does the credential need periodic rotation; does the target system have supporting APIs; can the application tolerate swaps?
4. **Define scope:** single app, multiple environments, multiple accounts, or multiple Regions.
5. **Select service:** Parameter Store `String`/`SecureString` for fitting configuration; Secrets Manager for secrets needing dedicated lifecycles.
6. **Design permissions:** per-workload IAM, KMS key policies, resource policies, or RAM shares as needed.
7. **Design consumption:** SDK, extension, dynamic reference, or secret injection; define caching and refresh.
8. **Design auditing:** CloudTrail, rotation logs, policy changes, approvers, and test evidence.
9. **Estimate cost:** storage, API requests, KMS, Lambda, throughput, and replication.
10. **Test failure modes:** access denied, disabled KMS key, missing secret, failed rotation, unreachable Region, and revoked old credentials.

### Example Decision Matrix

| Scenario | Recommended choice | Reason |
|---|---|---|
| Internal URL for Orders service | Parameter Store `String` | Non-secret config needing hierarchy |
| Standard AMI ID per Region | Parameter Store `String` | Configuration data reused in IaC |
| Rotatable third-party API token | Secrets Manager | Needs secret lifecycle and rotation workflow |
| RDS password requiring rotation | Secrets Manager | Built-in rotation integration for supported data services |
| Encrypted license key, rarely changes, no rotation | Parameter Store `SecureString` or Secrets Manager | Choose based on audit, permission, and lifecycle needs |
| Advanced config shared across accounts | Parameter Store Advanced + AWS RAM | Supports shared parameters |
| Credential needing replica for multi-Region DR | Secrets Manager | Built-in secret replication |
| Feature flag needing gradual rollout | AWS AppConfig, optionally backed by Parameter Store | AppConfig manages configuration deployment and rollouts |

## 17. Operational and Audit Evidence

To demonstrate secrets/parameters are managed securely, retain evidence covering permissions, changes, rotation, and how applications consume data.

| Audit question | Evidence |
|---|---|
| Who can read the secret? | IAM policies, secret resource policy, KMS key policy |
| Who can read the `SecureString`? | IAM policy for `ssm:GetParameter*`, KMS decrypt permissions, and path policies |
| When was the secret rotated? | Rotation schedule, CloudTrail events, rotation status, and sanitized Lambda logs |
| Did the new credential work? | `testSecret` results, health checks, and application logs |
| Were parameters reviewed? | Version history, labels, parameter policies, and EventBridge notifications |
| Does the secret have a DR replica? | Replication status, target Region, KMS key, and failover test results |
| Who modified access permissions? | CloudTrail, change requests, and approvers |
| Was plaintext exposed? | Reviews of CI logs, CloudWatch Logs, shell history, artifacts, and tickets |

CloudTrail records API activity and administrative changes, but API logs must never be treated as a place to store secret values. For rotation Lambdas, inspect logs and metrics to confirm the function never prints plaintext. Application logs should record only secret ARN/name or retrieval status, never values.

## 18. Pre-Production Checklist

- [ ] Configuration and credentials are clearly classified.
- [ ] `String` is used for non-sensitive config; `SecureString` or Secrets Manager for sensitive data.
- [ ] Standard vs. Advanced Parameter Store tier is chosen based on actual limits and features needed.
- [ ] Secrets requiring rotation have workflows updating both the target system and applications.
- [ ] Rotation was tested in non-production before enabling schedules.
- [ ] Applications have appropriate cache TTLs, refresh, retries, and connection pool handling.
- [ ] Each workload's IAM role reads only its required secrets/parameters.
- [ ] KMS key policies and IAM policies are verified; customer managed keys are used when granular decrypt permissions are needed.
- [ ] Parameter hierarchies do not grant overly broad parent-path reads.
- [ ] Cross-account/Region sharing includes resource policies, KMS permissions, and replication status monitoring.
- [ ] CloudFormation dynamic references are used only in supported resource properties.
- [ ] No plaintext appears in source code, build logs, user data, artifacts, or tickets.
- [ ] CloudTrail and rotation/parameter policy alerts are configured.
- [ ] Procedures exist for restoring versions, recovering failed rotations, and revoking old credentials.
- [ ] Storage, API, KMS, Lambda, throughput, and replication costs are estimated.

## 19. Takeaways

Parameter Store is the right fit for centralized configuration and `SecureString` values with straightforward protection needs. The Standard tier covers most normal configuration; the Advanced tier adds capacity, parameter policies, and cross-account sharing at a cost. Design IAM and KMS carefully, especially around path hierarchies and `GetParametersByPath`.

Secrets Manager fits credentials and tokens with dedicated security lifecycles. It manages versions, rotation, integrations with certain AWS services, and multi-Region replication. When rotating, both the secret and the target system must be updated, the new credential tested, and applications ensured to refresh on time.

Sound decisions start with data classification, lifecycle requirements, and how workloads consume values. Combining IAM roles, KMS, caching, CloudTrail, and change procedures lets AWS applications fetch configuration securely, preserve availability, and control costs.

## References

- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [Choosing Parameter Tiers in Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-advanced-parameters.html)
- [Working with Parameter Hierarchies](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-hierarchies.html)
- [Assigning Parameter Policies](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-policies.html)
- [KMS Encryption for Parameter Store SecureString](https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html)
- [Restricting Access to Specific Parameters and Paths](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-restrict-parameter-access.html)
- [What is AWS Secrets Manager?](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [Rotate AWS Secrets Manager Secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html)
- [Rotation Schedules](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html)
- [Rotation by Lambda Function](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda.html)
- [Lambda Rotation Strategies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html)
- [Access Secrets from a Different Account](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_examples_cross.html)
- [Replicate Secrets Across Regions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/replicate-secrets.html)
- [CloudFormation Dynamic References](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html)
- [Secrets Manager Dynamic References](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html)
- [Parameter Store SecureString Dynamic References](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-ssm-secure-strings.html)
