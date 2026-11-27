# Parameter Store, Hierarchies, and Configuration Access Control

> **Chapter:** Systems Manager Operations  
> **Module:** CLOUD_PROVIDERS_AWS  
> **Objective:** design a centralized configuration storage system using AWS Systems Manager Parameter Store; organize parameters by hierarchy; control read, write, decryption, and sharing permissions; and safely manage versions, policies, throughput, and configuration lifecycle.

## 1. The Problem: Scattered Configuration Hurts Operations

An e-commerce system running on AWS has multiple components:

- Spring Boot APIs on Amazon ECS.
- Message-processing workers on Lambda.
- EC2 instances running background tasks.
- CI/CD pipelines deploying across multiple environments.
- Services sharing endpoints, feature flags, timeout limits, and connection settings.

If each service keeps configuration in separate files, environment variables, or AMIs, operations teams easily run into issues:

- An endpoint changes, yet only a subset of instances is updated.
- Dev and production accidentally read each other's settings.
- Stale values linger inside containers after deployment.
- Developers hold read access to production config when they only need development.
- Secrets get committed to Git or printed to logs.
- Nobody knows who changed a value, when it changed, or which version to roll back to.
- During scale-out, hundreds of instances call configuration APIs simultaneously and get throttled.

AWS Systems Manager Parameter Store provides a managed configuration store accessible via API, integrated with IAM/KMS, and structured along hierarchical paths.

Example parameter group:

```text
/shop/dev/api/log-level
/shop/dev/api/request-timeout
/shop/dev/api/payment-endpoint
/shop/prod/api/log-level
/shop/prod/api/request-timeout
/shop/prod/api/payment-endpoint
/shop/prod/api/database-password
/shop/prod/worker/queue-url
```

Applications read only the parameters belonging to the environment and service they are authorized to access. The platform team centrally governs naming conventions, policies, encryption, and access reviews.

## 2. What Is Parameter Store and What Is It Used For?

Parameter Store is an AWS Systems Manager capability for storing configuration data as key/value parameters. Applications and automations can create, update, retrieve, and manage parameters via the Console, AWS CLI, SDKs, or APIs.

Common use cases:

- Application configuration: log levels, timeouts, endpoints, simple feature settings.
- Environment-specific settings: dev, staging, production.
- Operational values: approved AMI IDs, release channels, agent versions.
- Resource identifiers: VPC/subnet IDs, queue URLs, bucket names.
- Secure configuration: sensitive values requiring KMS encryption.
- Automation: runbooks, EC2 bootstrap, deployment scripts, and CloudFormation.

Parameter Store fits well when you need a centralized, hierarchical configuration store integrated with Systems Manager. It does not automatically push configuration into every application: workloads must have API permissions, a retrieval mechanism, a cache/refresh strategy, and handling for parameter changes.

### 2.1. Choosing the Right Service for Your Data

| Need | Service to Evaluate | Rationale |
|---|---|---|
| Simple configuration, small values, API retrieval | Parameter Store | Hierarchies, IAM, versions, and Systems Manager integration |
| Database passwords/API keys needing automatic rotation | AWS Secrets Manager | Dedicated secrets management and rotation integrations |
| Feature flags, dynamic configuration rollouts | AWS AppConfig | Deployment strategies, validators, gradual rollouts, and rollbacks |
| Large configuration files or artifacts | Amazon S3 | Built for objects/files, versioning, and lifecycle |
| Secrets in Kubernetes workloads | AWS Secrets Manager or platform-native integration | Secret lifecycle and workload integration |

Do not store database passwords or API keys in `String`/`StringList`. Simple sensitive data can use `SecureString`, but when automatic rotation, cross-account secret lifecycles, or dedicated credential management is needed, AWS recommends Secrets Manager.

### 2.2. Parameter Store Is Not a Dynamic Configuration Rollout Engine

An application reading a parameter at startup typically keeps that value in memory until it reloads or restarts. Parameter Store does not push notifications directly to every running process.

If you need percentage-based configuration rollouts, pre-publish validation, gradual deployments, or automated configuration rollbacks, evaluate AWS AppConfig. Parameter Store can still serve as a configuration source for AppConfig when supported by your architecture.

## 3. Parameter Model and Data Types

Each parameter has these core attributes:

- **Name:** unique within a Region, optionally structured as a hierarchy path.
- **Value:** the configuration value.
- **Type:** `String`, `StringList`, or `SecureString`.
- **Tier:** `Standard` or `Advanced` (Intelligent-Tiering can be set as the default tier).
- **Version:** monotonically increasing version number on updates.
- **Description:** documents purpose, owner, or change reference.
- **DataType:** additional data type, such as `text`, `aws:ec2:image`, or `aws:ssm:...` as supported by the service.
- **Tags:** metadata for governance and ownership attribution where supported by APIs/services.

Parameter names, descriptions, and metadata are not encrypted like `SecureString` values. Never place passwords, tokens, or PII in parameter names, descriptions, or tags.

### 3.1. String

Used for a single value:

```text
INFO
https://api.example.internal
3000
true
```

Example:

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/api/log-level" --type String --value "INFO" --description "Application log level"
```

`String` does not provide `SecureString` encryption with a selectable KMS key and separate decrypt permissions. Parameter Store still protects data at rest and in transit using AWS-managed encryption and TLS, but never use `String` for passwords, API tokens, private keys, or secrets requiring decryption access control.

### 3.2. StringList

Used for comma-separated lists of values without general escaping semantics for arbitrary data types:

```text
subnet-0123456789abcdef0,subnet-0abcdef0123456789
```

Applications must parse the format properly. If a value needs complex JSON, nested structures, or explicit escaping, use a `String` parameter holding JSON where tier/data type permits, or S3/AppConfig depending on the goal.

### 3.3. SecureString

Used when the value must be encrypted with AWS KMS:

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/api/partner-token" --type SecureString --key-id alias/shop-prod-parameters --value "REPLACE_WITH_SECRET_VALUE"
```

When reading via CLI, plaintext is returned only when `--with-decryption` is specified:

```bash
aws ssm get-parameter --region ap-southeast-1 --name "/shop/prod/api/partner-token" --with-decryption
```

Do not run this in publicly recorded terminals or unprotected CI logs. Avoid putting literal secrets in shell history, command arguments, or pipeline logs. In production, use secret injection/SDKs with temporary credentials and avoid printing the response object.

### 3.4. DataType and AMI Validation

Parameters can use the `aws:ec2:image` data type for AMI IDs. Parameter Store can validate AMI IDs through EC2 integration; validation occurs asynchronously, so `PutParameter` may return before validation completes.

Example:

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/ec2/approved-ami" --type String --data-type aws:ec2:image --value "ami-0123456789abcdef0"
```

Applications/automations should not assume a parameter is valid the moment the write API succeeds. Check status/value after validation completes and handle validation failures.

## 4. Hierarchies: Designing Purposeful Paths

A hierarchy is a parameter naming structure separated by `/` delimiters. For example:

```text
/<organization>/<environment>/<application>/<component>/<setting>
```

A possible convention:

```text
/shop/prod/orders-api/database/host
/shop/prod/orders-api/database/port
/shop/prod/orders-api/http/read-timeout
/shop/prod/orders-api/logging/level
/shop/prod/payment-worker/queue/url
/shop/staging/orders-api/database/host
```

A parameter can sit at any level. Parameter Store supports up to 15 hierarchy levels. Parameter names must be unique within a Region; the same name in two Regions represents two separate parameters.

### 4.1. Hierarchy Design Rules

A well-designed hierarchy should:

1. Separate accounts/environments along governance boundaries.
2. Separate applications/services to limit blast radius.
3. Group by data domain: networking, database, logging, features, security.
4. Stay concise enough not to exceed depth/name limits.
5. Never encode sensitive data in path segments.
6. Have an owner and naming convention recorded in platform documentation.

Examples:

| Path | Meaning |
|---|---|
| `/shop/dev/orders-api/...` | Development configuration for Orders API |
| `/shop/staging/orders-api/...` | Staging configuration |
| `/shop/prod/orders-api/...` | Production configuration |
| `/shared/prod/network/...` | Shared network configuration |
| `/platform/prod/agents/...` | Platform agent configuration |

### 4.2. Choose Account Boundaries Before Hierarchies

Never use a hierarchy to replace account isolation. For systems requiring production isolation:

- Production parameters can reside in the production account.
- Shared configuration can reside in a platform account and be shared under strict controls.
- Development accounts should have no permission to read production `SecureString` parameters.
- Cross-account sharing is supported only for Advanced parameters and requires AWS RAM.
- Each Region has its own parameter namespace; do not assume parameters replicate automatically across Regions.

### 4.3. Avoid Overly Broad Hierarchies

A path like `/shop` can span all environments, services, and secrets. If a role can call `GetParametersByPath` recursively on `/shop`, the blast radius is huge.

Split paths by application/environment and grant access only to leaf paths. For sensitive data, combine IAM path restrictions with KMS decrypt permissions.

### 4.4. Distinguishing Path from Parameter Name

Example:

- Path: `/shop/prod/orders-api/database`
- Parameter name: `/shop/prod/orders-api/database/host`
- Parent path: `/shop/prod/orders-api`
- Full ARN: `arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api/database/host`

When calling `GetParametersByPath`, the `Path` argument is the hierarchy path; it does not include the trailing parameter leaf name. Use `Recursive=true` to retrieve descendants across all levels, while carefully reviewing IAM permissions.

## 5. Naming, Ownership, and Tagging Strategy

A parameter should have more than a memorable name; it needs an owner and operational purpose.

Example naming convention:

```text
/<business-unit>/<environment>/<application>/<domain>/<setting>
```

Examples:

```text
/commerce/prod/checkout-api/database/host
/commerce/prod/checkout-api/http/connection-timeout-ms
/commerce/prod/checkout-api/feature/new-checkout-enabled
/commerce/dev/checkout-api/logging/level
```

Tags useful for governance:

| Tag | Example | Purpose |
|---|---|---|
| `Owner` | `checkout-team` | Responsible team |
| `Environment` | `prod` | Environment separation |
| `Application` | `checkout-api` | Application group |
| `DataClass` | `confidential` | Data classification |
| `CostCenter` | `CC-420` | Cost allocation |
| `ManagedBy` | `platform-iac` | Configuration management source |

Tags do not replace IAM path policies or KMS permissions. Not every Parameter Store API supports resource-level tag conditions identically; check the authorization reference for each action before relying on tags to protect data.

### 5.1. Do Not Treat Parameter Names as Secrets

A name like `/shop/prod/database/admin-password` reveals architecture and credential type. Prefer functional names without values/PII, and restrict `DescribeParameters`/`GetParametersByPath` if metadata itself is sensitive.

### 5.2. Ownership and Change Requests

Every production parameter should have:

- Owner/team.
- Purpose and consumers.
- Data classification.
- Change approval if production-impacting.
- KMS key and IAM access model.
- Expected refresh behavior.
- Rollback version/previous value handling.
- Retention/deletion policy if temporary configuration.

## 6. Standard and Advanced Tiers

Parameter tier governs storage limits and features. It is independent of throughput settings.

| Attribute | Standard | Advanced |
|---|---:|---:|
| Max parameters per account/Region | 10,000 | 100,000 |
| Max value size | 4 KB | 8 KB |
| Parameter policies | No | Yes |
| Cross-account sharing via AWS RAM | No | Yes |
| Max parameter policies per parameter | 0 | 10 |
| Data types | Most, except certain types like URL/JSON/JSONC | Full support for published data types |
| Tier conversion | Can be upgraded to Advanced | Cannot be downgraded to Standard |
| Storage charge | No Parameter Store charge for Standard | Advanced fee per current pricing |

Limits and pricing can change; check AWS Systems Manager quotas and pricing before designing at large scale.

### 6.1. When to Choose Standard?

- Simple configurations smaller than 4 KB.
- No parameter policies needed.
- No cross-account sharing needed.
- Total parameters fit within Standard quotas.
- Want to use Parameter Store's free tier.

### 6.2. When to Choose Advanced?

- Value exceeds 4 KB up to 8 KB.
- Expiration or no-change notification policies are required.
- Sharing parameters via AWS RAM is required.
- Count exceeds Standard quotas.
- Advanced-only data types are required.

The Advanced tier incurs charges. Do not upgrade every parameter to Advanced just because a few settings need policies or sharing.

### 6.3. Intelligent-Tiering

Parameter Store allows setting the account/Region default parameter tier to `Standard`, `Advanced`, or `Intelligent-Tiering`. With Intelligent-Tiering, Parameter Store creates a Standard parameter when the request fits Standard limits and automatically upgrades to Advanced when Advanced features/limits are needed—such as values over 4 KB, parameter policies, cross-account sharing, Advanced-only data types, or exceeding Standard quotas. This keeps ordinary configs on Standard while scaling up on demand; monitor Advanced charges and verify current pricing.

The default tier applies to new parameters when requests omit a tier. You can override the tier per parameter using `PutParameter`.

### 6.4. Upgrading Standard to Advanced

You can upgrade a Standard parameter to Advanced when higher limits or features are required. You cannot downgrade Advanced back to Standard. When changing tiers, evaluate billing and lifecycle; if you must return to Standard, plan to create a new parameter and migrate consumers in a controlled manner.

## 7. Versioning, Labels, and Change History

Every time a value is updated, Parameter Store creates a new version. Example:

| Version | Value | Meaning |
|---:|---|---|
| 1 | `INFO` | Initial value |
| 2 | `WARN` | Reduce log volume |
| 3 | `DEBUG` | Temporary incident investigation |

Parameter history supports retrieving older versions and change metadata. Parameter Store retains up to 100 versions per parameter; once exceeded, the oldest version may be evicted per service rules. Do not treat Parameter Store history as an immutable archive or long-term audit ledger.

### 7.1. Labels

Labels are custom aliases attached to a version, such as:

- `current`
- `candidate`
- `stable`
- `rollback`

A label can be moved between versions. This lets consumers or release pipelines reference meaningful versions, though labels are not immutable pointers.

Example:

```bash
aws ssm label-parameter-version --region ap-southeast-1 --name "/shop/prod/orders-api/logging/level" --parameter-version 3 --labels stable
```

Do not let multiple deployment pipelines move the same label arbitrarily without clear ownership and locking.

### 7.2. Rollback

You can roll back by writing the desired previous value/version as a new version. Never assume an old version remains stored forever. A production procedure should:

1. Record the previous value/version before making the change.
2. Obtain change approval.
3. Write the new value.
4. Confirm consumers picked up the new value.
5. On error, write the previous value back as a new version.
6. Record the change reference, operator, and timestamp.

### 7.3. GetParameterHistory Is Sensitive Data

Parameter history can return previous versions, including `SecureString` values. When a request enables `WithDecryption` and the principal holds `kms:Decrypt`, `SecureString` values can be returned in plaintext. Restrict `ssm:GetParameterHistory`. A principal denied `GetParameter` yet allowed `GetParameterHistory` can still read the current value via the history API per AWS-documented behavior.

In the AWS CLI, `get-parameter-history` accepts `--with-decryption`; use it only when the role is authorized to decrypt and output is protected.

Therefore, retrieval access policies must govern all of `GetParameter`, `GetParameters`, `GetParametersByPath`, and `GetParameterHistory`.

## 8. IAM: Controlling Who Reads and Modifies Parameters

Parameter Store authorization relies on IAM. Principals may be IAM roles/users, EC2 instance profiles, Lambda execution roles, ECS task roles, CodeBuild service roles, or other service roles. Prefer narrow `Allow` statements scoped to the exact parameters/paths a workload needs; isolate sensitive parameters under separate paths to simplify access control.

Common actions:

| IAM action | Effect |
|---|---|
| `ssm:PutParameter` | Create/update a parameter |
| `ssm:GetParameter` | Read a single parameter |
| `ssm:GetParameters` | Read multiple parameters by name |
| `ssm:GetParametersByPath` | Read parameters under a hierarchy path |
| `ssm:DescribeParameters` | View metadata/list parameters |
| `ssm:GetParameterHistory` | Read version history |
| `ssm:DeleteParameter` / `ssm:DeleteParameters` | Delete one or more parameters |
| `ssm:AddTagsToResource` / `ssm:RemoveTagsFromResource` | Manage tags |

### 8.1. Path-Based Authorization

Example of an ECS task role that only needs to read production Orders API configuration:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersApiProductionParameters",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": [
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api/*"
      ]
    }
  ]
}
```

This policy illustrates ARN scoping. Verify resource ARNs and which actions support resource-level permissions in the IAM Service Authorization Reference. If the workload reads `SecureString`, it also needs `kms:Decrypt` on the exact KMS key.

### 8.2. Critical Warning: Recursive GetParametersByPath

AWS Parameter Store authorizes `GetParametersByPath` against the **requested path**, not by evaluating each returned parameter individually.

Example:

- A role has permission to call `GetParametersByPath` on `/shop/prod`.
- The request specifies `Recursive=true`.
- The response can include `/shop/prod/orders-api/database/password` and other descendants.
- An explicit deny on a child parameter ARN for certain retrieval actions does not prevent an ancestor path API call from returning that parameter.

This is a subtle IAM pitfall when designing hierarchies.

To block a child parameter from recursive path retrieval, you must deny `ssm:GetParametersByPath` on every ancestor path that could encompass that parameter. For example, to protect `/shop/prod/restricted/db-password`, evaluate denies on `/shop/prod/restricted`, `/shop/prod`, `/shop`, and `/` depending on which paths the principal may request.

### 8.3. Denying Other Read Paths Too

A policy protecting sensitive parameters must cover all retrieval actions:

- `ssm:GetParameter`
- `ssm:GetParameters`
- `ssm:GetParametersByPath`
- `ssm:GetParameterHistory`

You can use the `ssm:GetParameter*` action pattern to deny retrieval paths starting with `GetParameter`, but test with the policy simulator to avoid accidentally blocking other required APIs. `GetParameterHistory` can return the current version; do not leave history permissions as a bypass around a `GetParameter` deny.

Similarly, parameter deletion has two independent API authorizations: `ssm:DeleteParameter` and `ssm:DeleteParameters`. To prevent deletion, deny both or use `ssm:DeleteParameter*` on the appropriate resource scope.

### 8.4. Explicit Deny Example for Sensitive Paths

The pattern below illustrates denying recursive retrieval on ancestor paths. ARNs/resource paths must match actual request paths in your environment:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyRecursiveReadOfRestrictedPaths",
      "Effect": "Deny",
      "Action": "ssm:GetParametersByPath",
      "Resource": [
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/*",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/restricted"
      ]
    },
    {
      "Sid": "DenyOtherReadPathsForRestrictedParameter",
      "Effect": "Deny",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParameterHistory"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/restricted/db-password"
    }
  ]
}
```

This example must be tested and tailored to your actual access paths; do not copy it verbatim into production. Use the IAM Policy Simulator and test every API with the restricted principal.

### 8.5. Testing Permissions Across Every Retrieval API

For a principal allowed to read `/shop/prod/orders-api` but forbidden from reading `/shop/prod/restricted`, test:

1. `GetParameter` for an allowed parameter.
2. `GetParameters` mixing allowed and forbidden names.
3. `GetParameterHistory` on a forbidden parameter.
4. `GetParametersByPath` with `Recursive=false`.
5. `GetParametersByPath` with `Recursive=true` at each ancestor path.
6. `WithDecryption=true` for `SecureString`.
7. `DescribeParameters` to check what metadata remains visible.

Do not test only one Console action. The API, CLI, and SDK share the same IAM authorization model.

## 9. SecureString and AWS KMS

### 9.1. How Encryption Works

`SecureString` uses AWS KMS to encrypt the value. Parameter Store does not implement encryption algorithms itself; it calls KMS with an encryption context binding the parameter ARN.
Parameter Store supports only symmetric KMS keys for `SecureString`; asymmetric keys cannot be used for this parameter type.

- For Standard `SecureString`, Parameter Store calls KMS `Encrypt`.
- For Advanced `SecureString`, Parameter Store uses envelope encryption and KMS `GenerateDataKey`.
- When reading with `WithDecryption`, Parameter Store calls KMS `Decrypt`.
- Plaintext is transmitted over TLS during request/response.

The encryption context contains key `PARAMETER_ARN` with the parameter's ARN as its value. This binds ciphertext to the specific parameter and supports auditing/controls in KMS policies.

### 9.2. Required KMS Permissions

| Action | Typical KMS Permission Needed |
|---|---|
| Create/update Standard `SecureString` | `kms:Encrypt` |
| Create/update Advanced `SecureString` | `kms:GenerateDataKey` |
| Read `SecureString` with decryption | `kms:Decrypt` |

The principal needs both the SSM permissions and the KMS permissions. Both the IAM policy and the KMS key policy must allow the operation; an explicit `Deny` in either layer blocks it.

### 9.3. AWS Managed Key or Customer Managed Key?

Parameter Store has a default AWS managed key with alias `aws/ssm`.

Important limitation: the AWS managed key `aws/ssm` allows IAM principals in the account with appropriate SSM retrieval permissions to decrypt `SecureString` values. You cannot craft fine-grained key policies on that AWS managed key.

When you need decryption isolation across teams/applications, use customer managed KMS keys:

- One key for production database parameters.
- A separate key for payment credentials.
- Key administrators separated from application operators.
- Task roles granted `Decrypt` only on required keys.
- Key policies restricting principals and optionally enforcing encryption context conditions.
- Review grants, key rotation, and lifecycle.

### 9.4. Scoping Decrypt Permissions via Encryption Context

Example KMS policy scoping `Decrypt` to parameter ARNs under an application path:

```json
{
  "Effect": "Allow",
  "Action": "kms:Decrypt",
  "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/EXAMPLE-KEY-ID",
  "Condition": {
    "StringLike": {
      "kms:EncryptionContext:PARAMETER_ARN": "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api/*"
    }
  }
}
```

This is an illustrative condition; verify actual key policies, IAM policies, and encryption contexts. Never grant account-wide decrypt when a workload needs only a subset of parameters.

### 9.5. Metadata Can Still Be Exposed

`SecureString` encrypts only the **parameter value**. Name, description, tags, and certain metadata are unencrypted. Therefore:

- Never put secret values in names/descriptions/tags.
- Restrict `DescribeParameters`/list access when metadata is sensitive.
- Never print parameter values into application logs.
- Never expose decrypted responses in metrics, traces, or error messages.
- Use Secrets Manager when dedicated rotation workflows are required.

## 10. Parameter Policies: Expiration and Notification

Parameter policies are available only in the Advanced tier. They let you attach policies to parameters to trigger time-based actions automatically.

Main policy types:

| Policy | Behavior |
|---|---|
| `Expiration` | Deletes the parameter at the configured timestamp |
| `ExpirationNotification` | Emits a notification before the parameter expires |
| `NoChangeNotification` | Emits a notification if the parameter has not been updated within the specified period |

Parameter Store enforces policies via asynchronous/periodic scans. Do not treat expiration as a second-accurate scheduler.

### 10.1. Combined Policies Example

Example of a temporary parameter scheduled for deletion at year-end, notifying 7 days beforehand and alerting if unchanged for 90 days:

```json
[
  {
    "Type": "Expiration",
    "Version": "1.0",
    "Attributes": {
      "Timestamp": "2026-12-31T00:00:00.000Z"
    }
  },
  {
    "Type": "ExpirationNotification",
    "Version": "1.0",
    "Attributes": {
      "Before": "7",
      "Unit": "Days"
    }
  },
  {
    "Type": "NoChangeNotification",
    "Version": "1.0",
    "Attributes": {
      "After": "90",
      "Unit": "Days"
    }
  }
]
```

### 10.2. Attaching Policies When Creating a Parameter

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/temporary/partner-endpoint" --type String --tier Advanced --value "https://partner.example.internal" --policies '[{"Type":"Expiration","Version":"1.0","Attributes":{"Timestamp":"2026-12-31T00:00:00.000Z"}},{"Type":"ExpirationNotification","Version":"1.0","Attributes":{"Before":"7","Unit":"Days"}},{"Type":"NoChangeNotification","Version":"1.0","Attributes":{"After":"90","Unit":"Days"}}]'
```

### 10.3. Be Careful When Updating Policies

When updating parameter policies, the new policy list replaces the existing list. To add one policy, re-submit all existing policies alongside the new one; sending only the new policy removes the prior ones.

### 10.4. Expiration Does Not Replace Secret Rotation

`Expiration` deletes the parameter; it does not generate a new secret or update consumers. For passwords/API credentials needing rotation, use Secrets Manager rotation or a purpose-built workflow.

`ExpirationNotification`/`NoChangeNotification` can emit events for automation to send alerts or open tickets. Configure EventBridge targets/permissions if automating handling.

## 11. Sharing Parameters Across AWS Accounts with AWS RAM

Parameter Store supports sharing **Advanced parameters** via AWS Resource Access Manager (RAM). This lets you manage shared configuration across multiple accounts without manually copying values on every update.

### 11.1. Sharing Prerequisites

- The parameter must be in the Advanced tier.
- The sharing account must own the parameter; you cannot re-share a parameter shared with you.
- Consumer accounts receive read-only access under a RAM managed permission set.
- Consumers cannot update/delete the source parameter or share it further to a third account.
- Parameters can be shared with specific accounts, OUs, or the entire Organization if AWS Organizations sharing is enabled.

### 11.2. Sharing SecureString

When sharing a `SecureString`:

- The parameter must use a customer managed KMS key.
- The AWS managed key `aws/ssm` cannot be shared cross-account.
- The KMS key must be separately shared/authorized for the consumer account.
- IAM permissions and the KMS key policy on both sides must permit read/decrypt.
- Do not share a broad KMS key when only a few parameters are needed.

### 11.3. Consumer Parameter Reads

Consumers must use the full parameter ARN to retrieve a parameter from another account:

```bash
aws ssm get-parameter --region ap-southeast-1 --name "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shared/prod/network/private-subnet-ids"
```

Consumers use the read-only permissions granted by the RAM managed permission set. A permission set allowing history reads exists; select it only if consumers truly need history.

### 11.4. When Should You Not Share?

- Each environment needs independent configuration.
- Parameters contain credentials needing separate rotation/lifecycle.
- Consumers do not need the same shared configuration source.
- Cross-account trust has not been reviewed.
- KMS key ownership/rotation is not agreed upon.

Do not use parameter sharing to bypass proper account boundary design. Sharing requires an owner, consumer list, purpose, KMS policy, review date, and revocation process.

## 12. Throughput and Throttling

Parameter tier and throughput are independent settings:

- **Tier** governs parameter count, size, and features.
- **Throughput** governs how many API transactions per second the account/Region can serve.

### 12.1. Default Throughput

Per current Parameter Store quotas, retrieval APIs `GetParameter`, `GetParameters`, and `GetParametersByPath` share a default quota of 40 transactions/second per account/Region. One API call can return multiple parameters; billing interactions and TPS transactions are distinct concepts.

Other APIs have separate quotas, such as `PutParameter`, `DescribeParameters`, `DeleteParameter`, and `GetParameterHistory`.

### 12.2. Higher Throughput

Higher throughput can be enabled per account/Region. Current published quotas for the higher-throughput retrieval tier include, for example:

| API | Default | Higher throughput |
|---|---:|---:|
| `GetParameter` | Shared 40 TPS | 10,000 TPS |
| `GetParameters` | Shared 40 TPS | 1,000 TPS |
| `GetParametersByPath` | Shared 40 TPS | 500 TPS |

These are reference quotas per current documentation; check Service Quotas / Systems Manager endpoints and quotas for your Region before relying on them. Higher throughput incurs additional charges per Parameter Store API interaction.

### 12.3. Throttling Example During Scale-Out

An ECS service normally runs 5 tasks, each reading 12 parameters at startup. During a deployment replacing tasks while autoscaling spikes to 50 tasks quickly, new tasks may call `GetParametersByPath` simultaneously. The burst can exceed the default quota.

Common symptoms:

- SDK throws `ThrottlingException` or `RateExceeded`.
- Slow task startup or failed health checks.
- Retries raise latency and generate even more requests.
- Deployments drag out even with bug-free application code.

### 12.4. Ways to Reduce Throttling

1. Cache parameter values in process instead of reading on every HTTP request.
2. Use `GetParameters`/`GetParametersByPath` to batch required values.
3. Spread startup/reload calls using jitter.
4. Use bounded exponential backoff and retry budgets.
5. Avoid polling `DescribeParameters` continuously for discovery.
6. Enable higher throughput if the workload genuinely needs it and costs are accounted for.
7. Limit how many parameters are read at startup; never load the entire root hierarchy.
8. Monitor CloudWatch metrics/SDK errors and application latency.

Parameter Store should not be a synchronous dependency on every user request. Reading configuration at startup or refreshing on a reasonable cadence reduces latency and API consumption.

### 12.5. Higher Throughput Cost

Higher throughput is billed per API interaction; a single API call returning multiple parameters can count as multiple interactions. Estimate expected usage from returned parameter counts, workload counts, refresh cadence, and account/Region before enabling.

Do not confuse Advanced parameter storage fees with higher-throughput fees. They are independent and can both apply simultaneously.

## 13. Reading Parameters via API and CLI

### 13.1. Reading a Single Parameter

```bash
aws ssm get-parameter --region ap-southeast-1 --name "/shop/prod/orders-api/logging/level"
```

For `SecureString`, add `--with-decryption` when the principal holds KMS `Decrypt`.

### 13.2. Reading Multiple Parameters by Name

```bash
aws ssm get-parameters --region ap-southeast-1 --names "/shop/prod/orders-api/logging/level" "/shop/prod/orders-api/http/read-timeout-ms"
```

The API caps how many names fit in one request. For larger sets, batch within API limits and handle `InvalidParameters` if some names do not exist or are inaccessible.

### 13.3. Reading by Hierarchy Path

```bash
aws ssm get-parameters-by-path --region ap-southeast-1 --path "/shop/prod/orders-api" --recursive --with-decryption
```

- `--path` specifies the root path.
- `--recursive` retrieves all descendant levels.
- `--with-decryption` decrypts `SecureString` values if IAM/KMS allow.
- The API paginates; the CLI paginates automatically by default, while SDK scripts must iterate `NextToken`.
- Do not use root path `/` for application workloads unless strictly necessary.

Path reads can return more values than expected. Combine path design, IAM policies, and recursive access testing.

### 13.4. Inspecting Metadata and Version History

```bash
aws ssm describe-parameters --region ap-southeast-1 --parameter-filters "Key=Path,Option=Recursive,Values=/shop/prod/orders-api"
```

```bash
aws ssm get-parameter-history --region ap-southeast-1 --name "/shop/prod/orders-api/logging/level"
```

`DescribeParameters` returns metadata and is not meant for bulk value retrieval. History access must be restricted because it can expose current and past values.

### 13.5. Pagination and API Limits

When using SDKs:

- Handle `NextToken` for `GetParametersByPath`.
- Never assume one response holds the entire hierarchy.
- Check `InvalidParameters`.
- Batch within API quotas.
- Enforce explicit timeouts and retry policies.
- Never log plaintext values while debugging.

## 14. Integrating Parameter Store with Workloads

### 14.1. EC2 Instance Profiles

EC2 instances can use an instance profile role to read parameters. Never embed long-lived access keys in user data or configuration files.

Example:

1. EC2 instance boots.
2. Instance profile supplies temporary credentials.
3. Bootstrap script calls SSM `GetParameter`.
4. Application receives config via restricted-permission files or protected environment.
5. IAM role can read only the required paths.

User data can often be read via instance metadata/control plane with appropriate permissions; never put plaintext secrets in user data.

### 14.2. ECS Task Roles

For ECS:

- The task execution role lets the ECS agent pull images, send logs, and fetch secrets declared in the task definition.
- The task role is used by application code calling the Parameter Store API.
- The task role should scope `ssm:GetParameter*` to the paths the service needs.
- When reading `SecureString` encrypted with a customer-managed KMS key, add `kms:Decrypt` with the matching encryption context.
- Do not grant every task read access to all of `/shop/prod`.

If injecting parameters via the task definition, verify the exact secret/config injection mechanism and refresh behavior. Already-running tasks/containers do not update environment variables automatically when a parameter changes; task replacement or an application refresh mechanism is usually needed.

### 14.3. Lambda

Lambda functions can read Parameter Store via the SDK or the AWS Parameters and Secrets Lambda Extension where appropriate.

- The execution role needs SSM permissions and KMS decrypt if needed.
- The extension caches with a TTL; account for cache invalidation/refresh.
- Avoid calling Parameter Store on every invocation when caching works.
- Factor in cold starts, concurrency bursts, and default throughput.
- Never return secret values in function responses or logs.

### 14.4. Systems Manager Automation and Run Command

Parameters can be referenced inside SSM documents/runbooks, letting automations reuse configuration. When a document accepts a parameter name as input, check whether callers could supply out-of-scope paths. Scope the Automation/managed node IAM role to the exact paths needed.

### 14.5. CloudFormation Dynamic References

CloudFormation supports dynamic references to Parameter Store in certain resource properties:

```yaml
Resources:
  AppLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /shop/prod/orders-api
      RetentionInDays: "{{resolve:ssm:/shop/prod/logging/retention-days}}"
```

Dynamic references resolve during stack operations; they are not subscriptions that auto-update resources whenever a parameter changes. Some resources/service integrations have specific limitations; verify CloudFormation dynamic reference support and permissions.

For `SecureString` dynamic references, CloudFormation restricts support by resource/property and usage. Do not assume every `SecureString` can be referenced in any resource. Use Secrets Manager dynamic references where supported by the use case and resource, or grant runtime roles for applications to fetch secrets.

### 14.6. Parameter Store in CodeBuild/CI

Build/deploy roles can read build configuration from Parameter Store. Separate:

- Non-sensitive build-time configuration.
- Deployment-time configuration.
- Runtime `SecureString`.
- Credentials needing rotation.

Never expose `SecureString` plaintext in build logs, artifacts, or caches. Restrict build roles from reading production values if builds only compile and test.

## 15. Safe Configuration Change Management

### 15.1. Change Process

A production workflow should:

1. Identify the parameter, owner, consumers, and impact.
2. Review the value/schema and change request.
3. Verify IAM/KMS permissions.
4. Write the new version.
5. Validate the parameter value in staging/consumers.
6. Roll out or refresh consumers per deployment strategy.
7. Monitor error rates/latency and active config version.
8. Roll back if regressions appear.
9. Record operator, timestamp, version, and approval.

### 15.2. Do Not Change Value Schemas Arbitrarily

If a parameter holds JSON and applications expect field `timeoutMs`, changing the structure can break all consumers at once. Use schema versions or a new parameter name for breaking contract changes.

### 15.3. Refresh and Cache Strategies

| Pattern | Advantage | Trade-off |
|---|---|---|
| Read at startup | Few API calls, stable config within process | Requires restart/rollout to pick up new values |
| Periodic refresh | Picks up changes without restart | Introduces lag and ongoing API usage |
| Cache with TTL | Reduces latency/API calls | May serve stale values during TTL |
| Read every request | Picks up new values quickly | Raises latency, throttling risk, and dependency coupling |

Set TTLs based on configuration sensitivity. Never cache secrets indefinitely if rotation/lifecycle requires refreshes.

### 15.4. Parameter Store vs. AppConfig

Use Parameter Store for simply structured key/value configuration. Use AppConfig when you need:

- Pre-deployment configuration validation.
- Canary/linear deployment strategies.
- Gradual rollouts by percentage or target.
- Automatic rollback driven by CloudWatch alarms.
- Feature flags and dynamic configuration.
- Application-level polling/agent integration.

Both services can work together; do not force every configuration pattern into a single service.

## 16. Infrastructure as Code for Parameter Store

### 16.1. Creating Parameters with CloudFormation

The CloudFormation `AWS::SSM::Parameter` resource fits non-sensitive configuration managed alongside infrastructure. Example:

```yaml
Resources:
  OrdersApiLogLevel:
    Type: AWS::SSM::Parameter
    Properties:
      Name: /shop/prod/orders-api/logging/level
      Type: String
      Tier: Standard
      Description: Log level for Orders API
      Value: INFO
      Tags:
        Owner: orders-team
        Environment: prod
        ManagedBy: cloudformation
```

This resource creates `String`/`StringList` per CloudFormation schema support; never use it to store plaintext secrets or assume it creates `SecureString`. Manage `SecureString` through proper mechanisms such as API/CLI/SDK with a customer-managed KMS key, or reference secrets via supported integrations.

### 16.2. Dynamic References to SecureString

In CloudFormation-supported resource properties, you can use secure dynamic references:

```yaml
Resources:
  SomeSupportedResource:
    Type: AWS::SomeService::Resource
    Properties:
      CredentialValue: "{{resolve:ssm-secure:/shop/prod/integration/api-token:3}}"
```

This syntax is illustrative; substitute an actual resource/property supporting secure dynamic references. CloudFormation resolves it only during stack operations; changing the parameter does not automatically update existing resources. Limit usage where plaintext could appear in resource state, outputs, or logs.

### 16.3. Drift and Ownership

If a parameter is managed by CloudFormation yet edited directly via the Console/CLI, the stack can drift. Choose one source of truth:

- Infrastructure as Code manages naming, description, type, tier, and non-secret values.
- Secrets Manager/secure workflows manage secret values.
- CI/CD pipelines execute approved changes.
- CloudTrail logs API activity for operator auditing.
- Drift detection and periodic reconciliation catch out-of-band edits.

Never let CloudFormation, Terraform, manual console edits, and runtime applications overwrite the same parameter without clear ownership.

## 17. AWS CLI: Creating, Updating, and Inspecting Parameters

> The commands below include both read-only and mutating operations. Run in an authorized account/Region; replace sample paths/values with lab data. Never put real secrets on the command line or in shell history.

### 17.1. Create a Standard String

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/dev/orders-api/logging/level" --type String --tier Standard --value "INFO" --description "Orders API log level"
```

### 17.2. Update a Parameter

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/dev/orders-api/logging/level" --type String --value "WARN" --overwrite
```

The command returns the new version. When updating, check parameter type, tier, policies, and consumer compatibility.

### 17.3. Create an Advanced Parameter with a Policy

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/dev/temporary/test-endpoint" --type String --tier Advanced --value "https://test.example.internal" --policies '[{"Type":"NoChangeNotification","Version":"1.0","Attributes":{"After":"60","Unit":"Days"}}]'
```

### 17.4. Read a SecureString

```bash
aws ssm get-parameter --region ap-southeast-1 --name "/shop/prod/orders-api/database/password" --with-decryption
```

Run only with a role authorized to read and decrypt. Never paste plaintext output into tickets/chat/logs.

### 17.5. Read a Path with Pagination

```bash
aws ssm get-parameters-by-path --region ap-southeast-1 --path "/shop/dev/orders-api" --recursive --with-decryption --max-results 10
```

The CLI can paginate automatically; when writing SDK scripts, loop on `NextToken` until exhausted. Scope paths narrowly so you do not accidentally load another service's config/secrets.

### 17.6. View History

```bash
aws ssm get-parameter-history --region ap-southeast-1 --name "/shop/dev/orders-api/logging/level"
```

Do not grant history permissions merely for debugging convenience; history can expose current and previous values.

### 17.7. Delete a Parameter

```bash
aws ssm delete-parameter --region ap-southeast-1 --name "/shop/dev/temporary/test-endpoint"
```

`DeleteParameter` is a mutating operation. Deleting a parameter can immediately break consumers on their next read; verify dependencies and approval before running. For multiple parameters, `DeleteParameters` has distinct API semantics and authorization.

### 17.8. Check Higher Throughput Setting

```bash
aws ssm get-service-setting --region ap-southeast-1 --setting-id "arn:aws:ssm:ap-southeast-1:111122223333:servicesetting/ssm/parameter-store/high-throughput-enabled"
```

This is a read-only command to inspect the setting. Enabling higher throughput via `UpdateServiceSetting` changes billing and throughput behavior; perform it only after a capacity and cost review.

## 18. Troubleshooting Parameter Store

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `AccessDenied` on `GetParameter` | Missing `ssm:GetParameter` or wrong resource ARN | IAM policy, Region/account, parameter ARN |
| `SecureString` fails to decrypt | Missing `kms:Decrypt` or KMS key policy denies it | Key policy, grants, encryption context |
| `GetParametersByPath` returns too many values | Path too broad with `Recursive=true` | Narrow path, inspect ancestor path IAM |
| Child parameter explicitly denied yet visible via path | Authorization checks requested path, not individual returned parameters | Deny `GetParametersByPath` on ancestor paths |
| `GetParameterHistory` reads denied value | History API is a separate retrieval path | Deny `ssm:GetParameterHistory` and check KMS decrypt |
| `ParameterNotFound` | Wrong Region/path/name or parameter expired/deleted | Region, full name, history/CloudTrail |
| Parameter tier quota exceeded | Reached Standard/Advanced quota | `DescribeParameters`, quotas, and tier strategy |
| Parameter value too large | Exceeded 4 KB Standard or 8 KB Advanced | Switch to Advanced if appropriate or use S3/AppConfig |
| Parameter policies not running | Parameter is not Advanced or invalid policy JSON | Tier, policy schema, async scan/event delivery |
| `ExpirationNotification` missing | EventBridge/notification target unconfigured or scan not yet run | EventBridge rule, target permissions, policy attributes |
| `PutParameter` throttled | Default write quota exceeded | Backoff, reduce writes, higher throughput |
| `GetParameter` throttled during scale-out | Concurrent read burst | Cache, batch, jitter, higher throughput |
| RAM consumer cannot read | Share not accepted or missing KMS permissions | RAM resource share, full ARN, key policy |
| Shared `SecureString` fails to decrypt | Using AWS managed key or unshared CMK | Use customer managed key and share separately via KMS |
| App uses stale config | Cache/environment variable did not refresh | TTL, reload mechanism, task/instance restart |
| Parameter changed but CloudFormation resource didn't | Dynamic references resolve only during stack operations | Update stack/roll out resource per workflow |
| AMI ID invalid right after `PutParameter` | Asynchronous `DataType` validation | Wait for validation and inspect result |
| Parameter name/metadata exposed | Name/description/tags are unencrypted | Minimize sensitive metadata and restrict `Describe` access |

### 18.1. Runbook: ECS Task Cannot Read Production Parameter

1. Confirm the task runs in the expected account/Region.
2. Confirm the application uses the task role; do not confuse it with the execution role.
3. Identify the full parameter ARN and path.
4. Inspect IAM `ssm:GetParameter*` resource scope.
5. If using `GetParametersByPath`, check the request path and `Recursive` flag.
6. If `SecureString`, verify KMS key ARN, key state, key policy, and `kms:Decrypt`.
7. If the KMS condition checks encryption context, confirm `PARAMETER_ARN` matches.
8. Verify parameter type/tier and confirm the parameter still exists.
9. Check for throttling/retries and API quotas.
10. Do not log plaintext; record request ID/error code and remediate using an authorized role.

### 18.2. Runbook: Production Configuration Changed Unexpectedly

1. Retrieve CloudTrail events for `PutParameter`, `DeleteParameter`, or `LabelParameterVersion`.
2. Identify principal, assumed role, source IP, user agent, account, Region, and event time.
3. Retrieve parameter history if the investigating role is authorized.
4. Identify consumers and their config refresh/cache behavior.
5. If rollback is needed, write the approved value as a new version.
6. Check related IAM policy/tag/role changes.
7. Document the change ticket, approval, and post-incident evidence.
8. Review `ssm:PutParameter`, `ssm:DeleteParameter*` permissions and pipeline ownership.

## 19. Scenario Exercises and Answers

### Exercise 1 — Designing a Hierarchy

A system has an Orders API and a Payment Worker across dev/staging/prod. Propose a hierarchy.

**Answer:** Use `/shop/<environment>/<application>/<domain>/<setting>`, such as `/shop/prod/orders-api/database/host` and `/shop/prod/payment-worker/queue/url`. Separate production into its own account boundary when security requires it.

### Exercise 2 — Choosing a Parameter Type

A public endpoint and a database password need to be stored in Parameter Store. Which types should you choose?

**Answer:** Use `String` for the endpoint; use `SecureString` with a customer-managed KMS key for the database password if fine-grained decrypt permissions are needed. If automatic rotation is required, evaluate Secrets Manager.

### Exercise 3 — Standard or Advanced?

A parameter value is 6 KB and needs an expiration policy. Which tier should you choose?

**Answer:** `Advanced`, because Standard caps values at 4 KB and does not support parameter policies; Advanced supports values up to 8 KB.

### Exercise 4 — Downgrading Tiers

A parameter was upgraded to Advanced, and later its value shrank to 1 KB. Can it be downgraded to Standard?

**Answer:** No. Advanced cannot be downgraded. If Standard is needed, create a new parameter, migrate consumers, and retire the old parameter via change control.

### Exercise 5 — GetParametersByPath Security

A role is denied `/shop/prod/restricted/password` but allowed recursive reads on `/shop/prod`. Can it still read the password?

**Answer:** Yes. `GetParametersByPath` authorization evaluates the requested path. You must deny this action on ancestor paths that could encompass restricted parameters, and verify with the IAM simulator/APIs.

### Exercise 6 — GetParameterHistory

A role is denied `GetParameter` yet holds `GetParameterHistory`. What is the risk?

**Answer:** `GetParameterHistory` can return the current parameter version, including `SecureString` if the role holds decrypt permission. Restrict both the history API and KMS decrypt.

### Exercise 7 — SecureString and KMS

An application has `ssm:GetParameter`, yet receives `AccessDenied` when reading a `SecureString` with decryption. What should you check?

**Answer:** KMS `Decrypt` permission, KMS key policy/grants, key state, and encryption context. SSM read permissions do not grant decryption automatically.

### Exercise 8 — AWS Managed Key

Two teams in the same account need separate `SecureString` decryption boundaries. Is the default `aws/ssm` key appropriate?

**Answer:** No, it does not fit fine-grained separation because the AWS managed key permits decryption for IAM principals in the account under default behavior. Use customer-managed KMS keys with key policies and encryption context conditions.

### Exercise 9 — Parameter Policies

A temporary endpoint must be deleted after 30 days with a 5-day advance notice. Which tier and policies are needed?

**Answer:** Advanced tier with `Expiration` and `ExpirationNotification`. Policy enforcement is asynchronous; do not rely on it as an exact timer or for secret rotation.

### Exercise 10 — Policy Overwrite

A parameter has `Expiration` and `NoChangeNotification`. An operator updates it sending only an `ExpirationNotification` policy. What is the risk?

**Answer:** The new policy list replaces existing policies. You must re-submit all policies you want to keep alongside the new policy.

### Exercise 11 — Shared Parameters

Account A wants to share a `SecureString` with Account B. What are the key prerequisites?

**Answer:** Advanced parameter, customer-managed KMS key, and separately sharing the KMS key via KMS. Use AWS RAM; the consumer reads via the full parameter ARN with read-only access.

### Exercise 12 — Throttling

50 ECS tasks start together and each reads 10 parameters. What is the risk?

**Answer:** The read burst can exceed the default 40 TPS shared quota. Use caching, batching, jitter, retry budgets, or higher throughput after assessing cost.

### Exercise 13 — App Still Uses Old Value

A parameter was updated, yet running ECS tasks still use the old value. Why?

**Answer:** Running tasks may have cached the value or environment variable at startup. Implement application refresh/TTL or replace tasks; Parameter Store does not push updates to running processes.

### Exercise 14 — CloudFormation Dynamic References

A parameter is used via a CloudFormation dynamic reference. When the parameter changes, does the resource update automatically?

**Answer:** No. Dynamic references resolve during stack operations. Perform a stack update/resource rollout per change procedures.

### Exercise 15 — AMI DataType

`PutParameter` with `aws:ec2:image` succeeds, yet the AMI is not immediately usable. Why?

**Answer:** Data type validation happens asynchronously. Check validation status/result before consuming the value.

### Exercise 16 — Deleting a Parameter

A parameter has multiple consumers. An operator wants to call `DeleteParameter` to clean up old config. What must be done first?

**Answer:** Identify consumers, logs/CloudTrail, deployment references, IAM roles, and get approval; migrate consumers before deleting. `DeleteParameter` can break runtime immediately on the next read.

### Exercise 17 — Version Labels

A release pipeline uses the `stable` label pointing to version 4. Another pipeline moves the label to version 5. What is the risk?

**Answer:** Labels can be moved between versions; they are not immutable pointers. Enforce single ownership/locking/change control for labels and log release metadata.

### Exercise 18 — Secret Rotation

A database password must rotate automatically every 30 days and applications must receive new credentials. Is Parameter Store the default choice?

**Answer:** No. AWS Secrets Manager fits credentials requiring automatic rotation better. If using Parameter Store, you must build rotation, consumer refresh, rollback, and audit workflows yourself.

### Exercise 19 — IAM History Path

A developer only needs to read a log level, yet is granted `ssm:GetParameter*` on `/shop/prod/*`. What is wrong?

**Answer:** The wildcard is overly broad, spanning multiple retrieval APIs and exposing parameter history/other paths. Narrow the resource ARN to the specific path and grant only required actions.

### Exercise 20 — Traffic-Percentage Config Rollouts

A team wants to roll out a feature flag to 5% of users, watch alarms, and auto-roll back. Is Parameter Store sufficient?

**Answer:** Parameter Store is a key/value store; it does not provide that full deployment strategy. Evaluate AWS AppConfig for gradual rollouts, validators, and alarm-based rollbacks.

## 20. Production Checklist for Parameter Store

1. **Use case:** is the data config, a secret, a feature flag, or a file/artifact?
2. **Service choice:** is Parameter Store, Secrets Manager, AppConfig, or S3 the best fit?
3. **Hierarchy:** naming convention, environment/application/domain, and depth at or below 15?
4. **Account/Region:** production isolation, Region coverage, and replication strategy?
5. **Type:** right `String`/`StringList`/`SecureString` and `DataType`?
6. **Tier:** `Standard`/`Advanced`/`Intelligent-Tiering` chosen based on quotas/features/cost?
7. **Size:** value within the 4 KB/8 KB limit?
8. **IAM:** least-privilege permissions for Get/Put/Delete/History/Describe actions?
9. **Recursive path:** ancestor paths controlled for `GetParametersByPath`?
10. **KMS:** customer-managed key, key policy, encryption context, and decrypt roles?
11. **Metadata:** names/descriptions/tags free of secrets or PII?
12. **Versioning:** rollback, labels, and history retention process defined?
13. **Policies:** async semantics of expiration/no-change notifications understood?
14. **Sharing:** AWS RAM principals, consumer permissions, and KMS key sharing?
15. **Throughput:** default TPS, bursts, higher throughput, and API interaction costs?
16. **Caching:** startup/TTL/refresh strategy appropriate?
17. **Workload role:** EC2 instance profile, ECS task role, Lambda execution role?
18. **CloudFormation:** dynamic reference limitations and resource refresh behavior?
19. **CI/CD:** build roles prevented from reading production secrets unless necessary?
20. **Audit:** CloudTrail events, change approvals, and owner metadata?
21. **Monitoring:** `AccessDenied`, throttling, API errors, stale config, and expiration events?
22. **Testing:** IAM policy simulator and tests across all retrieval APIs?
23. **Recovery:** previous value/version and rollback procedure rehearsed?
24. **Deletion:** consumer inventory and approval before `DeleteParameter`?
25. **Cost:** Advanced storage, higher throughput, KMS, and cross-account usage?

**Final takeaway:** Parameter Store helps organize configuration centrally by hierarchy and enforce access via IAM. A secure design must combine path naming, account boundaries, retrieval API controls, KMS encryption, version/policy lifecycles, and throughput planning. In particular, recursive `GetParametersByPath` and `GetParameterHistory` are retrieval paths that require explicit controls. Use Secrets Manager for credentials needing rotation, AppConfig for controlled configuration rollouts, and test permissions using the exact roles your workloads will assume.

## Official AWS Documentation

- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [Parameter Store reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-a-parameter.html)
- [Working with parameter hierarchies](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-hierarchies.html)
- [Restricting access to specific parameters and paths](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-restrict-parameter-access.html)
- [Setting up Parameter Store and IAM permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-setting-up.html)
- [Choosing parameter tiers](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-advanced-parameters.html)
- [Specifying a default parameter tier](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-default-tier.html)
- [Parameter data types](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-data-types.html)
- [Assigning parameter policies](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-policies.html)
- [Managing Parameter Store throughput](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-throughput.html)
- [Systems Manager endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html)
- [Encrypting SecureString parameters with AWS KMS](https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html)
- [Restricting SecureString decryption](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-restrict-decryption.html)
- [Working with shared parameters](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-shared-parameters.html)
- [Parameter Store data protection](https://docs.aws.amazon.com/systems-manager/latest/userguide/data-protection.html)
- [AWS Systems Manager pricing](https://aws.amazon.com/systems-manager/pricing/)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [AWS AppConfig](https://docs.aws.amazon.com/appconfig/latest/userguide/what-is-appconfig.html)
- [CloudFormation dynamic references](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html)
- [AWS::SSM::Parameter CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ssm-parameter.html)
- [AWS Pricing Calculator](https://calculator.aws/)
