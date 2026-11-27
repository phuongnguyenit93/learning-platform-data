# SSO, AssumeRole, and Automatic Credential Refresh

## Learning Objectives

After this lesson, learners can:

- Distinguish between **authentication** (verifying identity) and **authorization** (permission to perform an action).
- Explain how **AWS IAM Identity Center (SSO)** grants access to AWS accounts through **permission sets** and provisioned IAM roles.
- Configure an **SSO token provider profile** in `~/.aws/config`, sign in with the AWS CLI, and use the profile from AWS SDK for Java 2.x.
- Distinguish between SSO access tokens, AWS role credentials, STS session credentials, long-term access keys, and credential providers.
- Understand **STS AssumeRole**, source credentials, trust policies, identity policies, cross-account access, and role chaining.
- Design profiles using `source_profile`, `role_arn`, `credential_source`, `external_id`, `role_session_name`, and understand Java SDK 2.x-specific support limits.
- Use `ProfileCredentialsProvider`, `DefaultCredentialsProvider`, and `StsAssumeRoleCredentialsProvider` in Java; configure refresh/cache/prefetch.
- Explain why you should not fetch credentials once and store them in `StaticCredentialsProvider`, hardcode access keys/secrets/session tokens, or write a manual refresh timer.
- Separate credentials by environment across local, EC2, ECS, EKS, and CI/CD; choose appropriate federation/roles instead of IAM user keys.
- Diagnose `Unable to load credentials`, `ExpiredToken`, `InvalidGrant`, `AccessDenied`, `IDPRejectedClaim`, `RegionDisabled`, and trust/permission errors.
- Verify identity using STS `GetCallerIdentity`, audit sessions via CloudTrail, protect the SSO cache, and close providers/clients cleanly at lifecycle end.

**Module context:** This lesson belongs to the **AWS SDK for Java** chapter in `CLOUD_PROVIDERS_AWS`. Learners explore AWS from Region/AZ, IAM, and VPC to compute, storage, database, integration, and serverless. Java applications must obtain credentials securely, refresh them before expiration, scope permissions, and maintain an audit trail on both personal workstations and AWS runtimes.

> **Scope:** Examples use **AWS SDK for Java 2.x**, AWS CLI v2, IAM Identity Center, and AWS STS. Profile names, account IDs, role ARNs, URLs, Regions, and buckets are illustrative data. This lesson does not require creating IAM user access keys. APIs, session limits, and configurations may vary by SDK/CLI version, permission set, and organization.

## 1. The Problem: Why Does an Application Run for an Hour and Suddenly Throw ExpiredToken?

A Java application calls S3 to download reports. At startup, a developer grabs temporary credentials from the AWS access portal and puts the three values into configuration:

- Access key ID;
- Secret access key;
- Session token.

The application runs fine, then after a while starts failing with `ExpiredToken`. The developer restarts the app to paste fresh credentials. When deployed to production, this turns into a recurring outage.

~~~mermaid
flowchart LR
    Dev[Developer / CI] -->|SSO login| Portal[IAM Identity Center]
    Portal -->|Temporary role credentials| App[Java application]
    App --> S3[(Amazon S3)]
    App -->|Credentials expired| Fail[ExpiredToken]
    Fail --> Restart[Manual restart]
    Restart --> Portal
~~~

The root cause is not S3. The application **treated temporary credentials as if they were permanent**.

The proper solution is to let a **credential provider** manage the lifecycle:

1. Identify the credential source (SSO, profile, EC2 instance role, ECS task role, EKS web identity, or STS AssumeRole).
2. The provider fetches temporary credentials and caches them in memory per the SDK's mechanism.
3. The provider checks expiration timestamps and refreshes before needed.
4. Service clients use the provider on every request without storing hardcoded access keys/secrets in business code.
5. If the underlying login session expires or is revoked, the application reports an authentication error so a user or operator can re-authenticate or re-issue access.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant P as Credentials provider
    participant SSO as IAM Identity Center / STS
    participant S3 as Amazon S3
    App->>P: resolveCredentials()
    P->>SSO: Get/refresh temporary credentials
    SSO-->>P: Credentials + expiration
    P-->>App: Current cached credentials
    App->>S3: Signed API request
    Note over P: Prefetch / refresh before expiry
    App->>P: resolveCredentials() on later request
    P-->>App: Refreshed credentials
    App->>S3: Signed request with current credentials
~~~

**Core point:** `AwsCredentialsProvider` is a credential source that lives for the application's lifecycle. `AwsCredentials` is merely a snapshot of values at a single point in time.

## 2. Authentication, Authorization, and Credentials

Three concepts must be kept distinct:

| Concept | Question | AWS Example |
| --- | --- | --- |
| **Authentication** | Who are you? | User logs in to IAM Identity Center; workload receives an IAM role |
| **Authorization** | What are you allowed to do? | IAM policies allow `s3:GetObject` on a bucket |
| **Credentials** | What proves identity on the request? | Access key ID + secret access key + session token |

The AWS SDK signs requests using **AWS Signature Version 4 (SigV4)**. With temporary credentials, the session token must also be included during signing/verification. You cannot copy only the access key ID and secret access key while omitting the session token.

### Long-Term Credentials vs. Temporary Credentials

| Type | Components | Lifecycle | Recommended Usage |
| --- | --- | --- | --- |
| IAM user access key | Access key ID + secret | Long-lived until rotated/revoked | Only in controlled legacy exceptions |
| STS credentials | Access key ID + secret + session token | Has expiration | Workload/user federation |
| IAM Identity Center credentials | SSO token and role credentials issued via portal | Tied to Identity Center session and role session | Developers, operators, human access |
| EC2 instance profile | Credentials from IAM role via IMDS | SDK auto-refreshes | EC2 workloads |
| ECS task role | Credentials from container credential endpoint | SDK auto-refreshes | ECS workloads |
| EKS web identity | OIDC token exchanged via STS AssumeRoleWithWebIdentity | Time-limited token/role session | Pods needing IAM permissions |

**Never place long-term access keys in source code, Git, Docker images, AMIs, user data, build logs, or committed config files.** Temporary credentials limit the window of exposure if a credential leaks; least privilege remains a separate requirement.

## 3. IAM Identity Center: How SSO Grants Access via Permission Sets

**AWS IAM Identity Center** is a centralized access management service for users and groups. An administrator assigns a **permission set** to a user or group across one or more AWS accounts.

When a user logs in to the AWS access portal and selects an account + permission set:

1. Identity Center authenticates the user against the organization's identity source and MFA policy.
2. The permission set defines permissions, session duration, and related settings.
3. AWS provisions a corresponding IAM role in the target account (typically named `AWSReservedSSO_...`).
4. The portal issues short-term credentials for the role session.
5. The CLI/SDK uses those credentials to sign requests to AWS services.

~~~mermaid
flowchart TB
    User[User / Group] --> IdP[Identity source + MFA]
    IdP --> Center[IAM Identity Center]
    Admin[Administrator] --> Assign[Assign permission set to account]
    Assign --> Center
    Center --> Portal[AWS access portal]
    Portal --> Account[Target AWS account]
    Account --> Role[IAM role provisioned from permission set]
    Role --> Policies[Identity-based permissions]
    Role --> Temp[Temporary role credentials]
    Temp --> SDK[AWS SDK for Java]
    SDK --> Service[S3 / DynamoDB / other services]
~~~

### A Permission Set Is Not a Credentials File

A permission set is a **definition of permissions and session parameters**. Users do not receive permanent access keys in the portal. On login, the system issues temporary role credentials matching the assigned permissions.

### IAM Identity Center Region and Application Region May Differ

- `sso_region`: the Region where the IAM Identity Center instance is configured.
- `region` in the profile or service client: the Region of the AWS service the application calls.

For example, Identity Center may reside in `us-east-1`, while the S3 bucket is in `ap-southeast-1`. These two values can differ. Setting `sso_region` to the bucket's Region by mistake is a common configuration error.

## 4. SSO Token and AWS Role Credentials Are Two Separate Layers

With the modern SSO token provider configuration, there are two credential layers:

1. **IAM Identity Center access token**: proves the login session with Identity Center; cached locally per SSO session.
2. **AWS role credentials**: access key ID, secret access key, and session token for the role/permission set in the AWS account; issued when requested by the SDK/CLI.

~~~mermaid
sequenceDiagram
    participant User as Developer
    participant CLI as AWS CLI
    participant Cache as SSO token cache
    participant Portal as IAM Identity Center
    participant Role as AWS account role
    participant SDK as Java SDK
    User->>CLI: aws sso login
    CLI->>Portal: Browser/device authorization
    Portal-->>CLI: Access token + refresh token
    CLI->>Cache: Store SSO token cache
    SDK->>Cache: Read valid SSO token
    SDK->>Portal: Request account role credentials
    Portal->>Role: Resolve permission set role
    Role-->>SDK: Temporary AWS role credentials
    SDK->>SDK: Cache credentials until refresh window
~~~

**The access token is not the SigV4 session token.** When calling standard AWS services like S3 or DynamoDB, the SDK uses AWS role credentials; the SSO access token is the authentication layer used to obtain those credentials.

### When Must You Re-Authenticate?

With the modern SSO token provider configuration:

- AWS role credentials refresh before expiration as long as the SSO session remains valid.
- The SSO access token refreshes using the refresh token within the allowed session lifetime.
- When the refresh token/extended session expires, is revoked, or policy requires re-authentication, the user must log in again via `aws sso login`.
- `aws sso logout` removes the user's cached SSO credentials; applications relying on that session will no longer be able to obtain new credentials.

**Automatic refresh does not mean permanent login or bypassing MFA/re-authentication policies.**

## 5. Shared AWS Config: Modern SSO Token Provider Configuration

The AWS CLI and SDK read shared configuration files, typically located at:

- Linux/macOS: `~/.aws/config` and `~/.aws/credentials`.
- Windows: `%USERPROFILE%\.aws\config` and `%USERPROFILE%\.aws\credentials`.
- Paths can be customized using supported environment variables.

The modern SSO token provider configuration isolates the SSO session into an `[sso-session ...]` section and links profiles to that session.

~~~ini
[profile dev-sso]
sso_session = company-dev
sso_account_id = 111122223333
sso_role_name = DeveloperAccess
region = ap-southeast-1
output = json

[sso-session company-dev]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access
~~~

Field meanings:

| Key | Purpose |
| --- | --- |
| `sso_session` | Name of the SSO session section used by the profile |
| `sso_start_url` | AWS access portal URL or appropriate issuer URL |
| `sso_region` | Region hosting the IAM Identity Center instance |
| `sso_account_id` | Target AWS account |
| `sso_role_name` | Name of the permission set/role provisioned in the account |
| `sso_registration_scopes` | OAuth scopes; `sso:account:access` enables account/role access |
| `region` | Default Region for AWS service calls |
| `output` | CLI output format; does not affect authorization |

Multiple profiles can reference the same `[sso-session company-dev]` when sharing one Identity Center session across different accounts or permission sets.

### Why Is `sso_registration_scopes` Needed?

`sso:account:access` is the base scope for listing accounts/roles and obtaining refresh tokens under the SSO token provider configuration. If your organization requires additional scopes, add only those specified by your administrator and needed by the service.

## 6. Configuring and Signing In with AWS CLI v2

### 6.1. Create a Profile

~~~bash
aws --version
aws configure sso --profile dev-sso
~~~

The wizard prompts for:

- SSO session name;
- SSO start URL/issuer URL;
- SSO Region;
- Registration scopes;
- Account and permission set/role;
- Default service Region;
- Output format;
- Profile name.

Starting with AWS CLI v2.22.0, **PKCE authorization is the default flow** on devices with a browser. If an environment suits device authorization, you can use `--use-device-code` per organizational policy.

### 6.2. Sign In

~~~bash
aws sso login --profile dev-sso
~~~

The CLI opens a browser (or prints authorization instructions if a browser cannot be launched), and the user authenticates and approves access. The CLI then stores the SSO token cache in its managed location.

### 6.3. Verify the Actual Identity

~~~bash
aws sts get-caller-identity --profile dev-sso
aws s3 ls --profile dev-sso --region ap-southeast-1
~~~

`get-caller-identity` returns the account, user/role ARN, and user ID of the **identity actually being used**. Always check the account ID/role ARN before running commands that mutate data.

### 6.4. End the Session

~~~bash
aws sso logout
~~~

The logout command clears cached SSO credentials for associated sessions on the machine. Do not run logout in a shared shell/process serving other users.

## 7. Legacy SSO Profiles: Why New Setups Should Avoid the Old Format

Legacy configuration placed SSO keys directly inside the profile:

~~~ini
[profile legacy-dev]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_account_id = 111122223333
sso_role_name = DeveloperAccess
region = ap-southeast-1
output = json
~~~

Legacy configuration has a **fixed session (typically 8 hours)** and does not support automatic SSO token refresh like the modern SSO token provider configuration. Once the session expires, the application cannot obtain new credentials until the user logs in again.

| Characteristic | Modern SSO Token Provider | Legacy SSO Profile |
| --- | --- | --- |
| Structure | `sso-session` + profile reference | SSO settings placed directly in profile |
| Refresh token flow | Yes | No automatic token refresh |
| Extended session | Governed by Identity Center policy/settings | Old fixed session |
| Recommended for new configs | **Yes** | No |

If inheriting a legacy config, migrate using the `aws configure sso` wizard and verify that your application has an SDK version/dependencies supporting the modern SSO token provider. Never hand-edit token cache files to extend a session.

## 8. Java SDK 2.x: Adding SSO, SSO OIDC, and STS Dependencies

To allow the Java SDK to read SSO profiles and call AssumeRole, the project needs the matching modules. Maven example using the AWS SDK BOM to keep all artifacts on the same version:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <aws.sdk.version>2.x.y</aws.sdk.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sso</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>ssooidc</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
</dependencies>
~~~

`2.x.y` is a placeholder. Pick **a supported AWS SDK for Java 2.x version**, replace the placeholder with the real version, and keep all SDK modules aligned via the BOM. Never randomly mix 2.x artifacts of different versions.

When using an SSO profile, `sso` and `ssooidc` are essential dependencies. When using `StsAssumeRoleCredentialsProvider`, `sts` is required. Add service artifacts (`s3`, `dynamodb`, `sqs`, etc.) matching the clients the application calls.

## 9. Using an SSO Profile from Java with ProfileCredentialsProvider

A simple pattern for local development: use the exact profile already authenticated via the CLI.

~~~java
package com.example.aws;

import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ListBucketsResponse;

public final class SsoS3Example {
    public static void main(String[] args) {
        try (ProfileCredentialsProvider credentials =
                 ProfileCredentialsProvider.create("dev-sso");
             S3Client s3 = S3Client.builder()
                 .region(Region.AP_SOUTHEAST_1)
                 .credentialsProvider(credentials)
                 .build()) {

            ListBucketsResponse response = s3.listBuckets();
            response.buckets().forEach(
                bucket -> System.out.println(bucket.name())
            );
        }
    }
}
~~~

Sequence:

1. Run `aws sso login --profile dev-sso`;
2. `ProfileCredentialsProvider` reads the shared config;
3. The provider recognizes the SSO token provider profile;
4. The SDK uses `sso`/`ssooidc` modules to fetch AWS role credentials;
5. `S3Client` signs requests with the current credentials;
6. The provider maintains/refreshes credentials via supported mechanisms.

**You do not need to read `~/.aws/sso/cache`, parse JSON tokens, or call SSO APIs manually.** The cache is an implementation detail managed by the AWS CLI/SDK.

### Selecting a Profile via the Environment

If you want the profile driven by the environment instead of hardcoding the profile name:

~~~bash
# Linux/macOS
export AWS_PROFILE=dev-sso

# Windows PowerShell
$env:AWS_PROFILE = "dev-sso"
~~~

When using `DefaultCredentialsProvider`, the SDK can read the profile selected by `AWS_PROFILE` at the profile provider stage. However, credentials at higher-priority steps may be chosen before the profile; see Section 10.

## 10. Default Credentials Provider Chain: Order and Precedence Pitfalls

When no provider is specified, a Java SDK 2.x service client uses the **default credentials provider chain**. The SDK searches credential sources in primary order:

1. Java system properties;
2. Environment variables;
3. Web identity token;
4. Shared AWS `config`/`credentials` profile;
5. ECS container credentials;
6. EC2 instance profile credentials.

~~~mermaid
flowchart TD
    Start[Service client needs credentials] --> Sys[Java system properties]
    Sys -->|No complete credentials| Env[Environment variables]
    Env -->|No complete credentials| Web[Web identity token]
    Web -->|No complete credentials| Profile[Shared profile files]
    Profile -->|No complete credentials| ECS[ECS container endpoint]
    ECS -->|No complete credentials| EC2[EC2 instance metadata]
    EC2 -->|No provider succeeds| Error[SdkClientException: unable to load credentials]
~~~

### Pitfall: SSO Profile Is Logged In, Yet Java Uses Different Credentials

Suppose a developer ran `aws sso login --profile dev-sso`, but the shell still has:

~~~bash
AWS_ACCESS_KEY_ID=OLD_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=OLD_SECRET_KEY
AWS_SESSION_TOKEN=OLD_SESSION_TOKEN
AWS_PROFILE=dev-sso
~~~

Because environment variables precede profiles, the SDK may use the **stale environment credentials** rather than the SSO profile. `AWS_PROFILE` does not invert the precedence of the provider chain.

How to check:

- Inspect whether `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, and JVM `-Daws.*` properties are set.
- Run `aws sts get-caller-identity --profile dev-sso` to verify the profile.
- In Java, temporarily specify `ProfileCredentialsProvider.create("dev-sso")` when isolating the source.
- Never log secrets or session tokens to debug.

### Choosing a Provider by Environment

| Runtime | Preferred Provider |
| --- | --- |
| Local developer | `ProfileCredentialsProvider` with SSO token provider |
| CI/CD | OIDC federation or workload role assumed by runner |
| EC2 | Instance profile via `DefaultCredentialsProvider` |
| ECS | Task role / container credentials |
| EKS | Pod Identity or IRSA/web identity per cluster setup |
| Cross-account | Source provider + `StsAssumeRoleCredentialsProvider` or assume-role profile |
| External IdP | Web identity/SAML federation per approved architecture |

Do not force every environment to share a developer's SSO profile. AWS runtimes should use workload identities/roles to avoid depending on a personal workstation's cache.
## 11. STS AssumeRole: Obtaining Credentials for Another Role

**AWS Security Token Service (STS)** provides the `AssumeRole` API to exchange current source credentials for a set of **temporary security credentials** belonging to a target IAM role:

- Access key ID;
- Secret access key;
- Session token;
- Expiration timestamp.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Source as Source credentials
    participant STS as AWS STS
    participant Role as Target IAM role
    participant S3 as Amazon S3
    App->>Source: Resolve current credentials
    Source-->>App: Source temporary credentials
    App->>STS: AssumeRole(target role ARN)
    STS->>Role: Evaluate trust + caller permissions
    Role-->>STS: Role permissions / session constraints
    STS-->>App: Temporary role credentials
    App->>S3: SigV4 request using assumed role
    S3-->>App: Response if authorized
~~~

### Practical Example

A developer has the `DeveloperAccess` SSO permission set in account A, but needs to read a log bucket in account B. Instead of granting permissions directly to the user/permission set, an administrator can:

1. Create role `CrossAccountLogReader` in account B;
2. Configure a trust policy allowing the appropriate principal from account A to assume the role;
3. Grant `sts:AssumeRole` permission to the source principal in account A;
4. Attach read permissions for the target bucket/prefix to the target role;
5. Have the Java SDK assume the role and use the new credentials to call S3.

**AssumeRole does not combine source and target permissions.** When acting as the target role, requests are evaluated solely against the target session's permissions, subject to session policies, permissions boundaries, SCPs, and explicit denies.

## 12. Both Policies Must Match: Trust Policy and Caller Identity Policy

This is the most common source of `AccessDenied` errors during cross-account role assumption.

### 12.1. Trust Policy in the Target Account

The trust policy answers: **which principal is allowed to assume this role?**

Example target role in account `222233334444` trusting a specific source role in account `111122223333`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustSourceDeveloperRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/SourceDeveloperRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

In organizations using IAM Identity Center, source roles are typically provisioned as `AWSReservedSSO_<PermissionSet>_<suffix>` and the path may include a Region. Never guess the ARN from the permission set name; retrieve the actual ARN from the account/CloudTrail/IAM console and check for changes if the permission set is re-provisioned.

### 12.2. Identity Policy in the Source Account

The source principal must also be allowed to call `sts:AssumeRole` on the target ARN (especially cross-account):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeLogReaderRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::222233334444:role/CrossAccountLogReader"
    }
  ]
}
~~~

### 12.3. Target Role Permissions Policy

The target role needs a policy permitting the operations the application will execute. For example, reading objects under a prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadApplicationLogs",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::company-logs",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "application/orders/*"
          ]
        }
      }
    },
    {
      "Sid": "GetApplicationLogObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-logs/application/orders/*"
    }
  ]
}
~~~

**These three layers serve distinct purposes:**

| Component | Configured Where? | Answers Question |
| --- | --- | --- |
| Trust policy | Target role | Who is allowed to assume the role? |
| Source identity policy | Source user/role | Is the source allowed to call `sts:AssumeRole` on this ARN? |
| Target permissions policy | Target role | Once assumed, what can the session do? |

For cross-account access, verify both sides: the target account must trust the source principal, and the source principal must be permitted to assume it. For same-account access, permissions can sometimes be granted via trust/resource policies; still evaluate the entire policy chain.

## 13. Using `source_profile` and `role_arn` in Shared Config

One profile can reference another profile to obtain source credentials and then assume a role.

~~~ini
[profile dev-sso]
sso_session = company-dev
sso_account_id = 111122223333
sso_role_name = DeveloperAccess
region = ap-southeast-1

[sso-session company-dev]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile target-log-reader]
role_arn = arn:aws:iam::222233334444:role/CrossAccountLogReader
source_profile = dev-sso
role_session_name = java-log-reader
region = ap-southeast-1
external_id = unique-value-from-target-admin
~~~

When Java or the CLI uses profile `target-log-reader`:

1. Reads profile `dev-sso`;
2. Obtains source credentials from IAM Identity Center;
3. Calls STS `AssumeRole` with `role_arn`;
4. Uses temporary credentials for `CrossAccountLogReader` on service calls.

Only include `external_id` when the target trust policy requires it. For third-party access, the external ID is provided by the target account owner and validated in the trust policy; never invent an arbitrary value expecting IAM to trust it automatically.

### `source_profile` vs. `credential_source`

| Setting | When to Use |
| --- | --- |
| `source_profile` | Source credentials reside in another named profile (SSO, role profile, credential process, etc.) |
| `credential_source = Environment` | Obtain source credentials from environment/system settings |
| `credential_source = Ec2InstanceMetadata` | Obtain source credentials from EC2 instance profile |
| `credential_source = EcsContainer` | Obtain source credentials from ECS container role endpoint |
| `web_identity_token_file` | Use an OIDC token file to call `AssumeRoleWithWebIdentity` |

**Never declare both `source_profile` and `credential_source` in the same role profile.**

### Differences Between Java SDK 2.x and AWS CLI

Per the AWS SDKs and Tools Reference Guide support matrix, assume-role profile configuration in **AWS SDK for Java 2.x has certain limitations**:

- `mfa_serial` is not supported via shared assume-role profile config;
- `duration_seconds` is not supported via shared assume-role profile config;
- other settings such as `role_arn`, `source_profile`, `external_id`, and `role_session_name` are supported by the profile provider.

Therefore, **do not copy a CLI profile containing MFA or `duration_seconds` into Java assuming the SDK behaves identically to the CLI**. To control session duration in Java, use `StsAssumeRoleCredentialsProvider` and configure `AssumeRoleRequest` explicitly. If interactive MFA is required, design an appropriate authentication flow instead of hardcoding TOTP codes.

## 14. Java SDK 2.x: `StsAssumeRoleCredentialsProvider` Caches and Refreshes Automatically

This is the explicit way to:

- Choose the source credentials provider;
- Choose the STS Region;
- Choose the target role ARN and session name;
- Set session duration in the request;
- Prefetch credentials before expiration;
- Enable background refresh so requests do not stall fetching credentials at the last moment.

~~~java
package com.example.aws;

import java.time.Duration;

import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;

public final class AssumeRoleS3Example {

    public static void main(String[] args) {
        try (ProfileCredentialsProvider source =
                 ProfileCredentialsProvider.create("dev-sso");
             StsClient sts = StsClient.builder()
                 .region(Region.AP_SOUTHEAST_1)
                 .credentialsProvider(source)
                 .build();
             StsAssumeRoleCredentialsProvider assumed =
                 StsAssumeRoleCredentialsProvider.builder()
                     .stsClient(sts)
                     .refreshRequest(r -> r
                         .roleArn("arn:aws:iam::222233334444:role/CrossAccountLogReader")
                         .roleSessionName("java-log-reader")
                         .durationSeconds(3600))
                     .prefetchTime(Duration.ofMinutes(10))
                     .staleTime(Duration.ofMinutes(5))
                     .asyncCredentialUpdateEnabled(true)
                     .build();
             S3Client s3 = S3Client.builder()
                 .region(Region.AP_SOUTHEAST_1)
                 .credentialsProvider(assumed)
                 .build()) {

            s3.listObjectsV2(b -> b
                .bucket("company-logs")
                .prefix("application/orders/"))
              .contents()
              .forEach(object -> System.out.println(object.key()));
        }
    }
}
~~~

### Reading the Code Step by Step

1. `ProfileCredentialsProvider` fetches source credentials from the authenticated SSO profile.
2. `StsClient` uses the source provider to sign STS requests.
3. `StsAssumeRoleCredentialsProvider` calls `AssumeRole` and caches the returned credentials.
4. `prefetchTime(10 minutes)` initiates fetching new credentials ahead of expiration within the configured window.
5. `staleTime(5 minutes)` defines when credentials are considered stale and must be refreshed to keep supplying valid credentials.
6. `asyncCredentialUpdateEnabled(true)` enables background refreshing.
7. `S3Client` always obtains credentials through the provider without business code tracking expiration or updating access keys.

### Provider and Client Lifecycle

- Create the provider/client **once per application lifecycle**, such as a singleton bean or service-level resource.
- Do not instantiate `StsClient` and `StsAssumeRoleCredentialsProvider` per HTTP request.
- Close the service client, assume-role provider, STS client, and source provider at application shutdown.
- In try-with-resources, Java closes resources in reverse declaration order.
- If a provider is shared across multiple service clients, do not close the provider until all clients stop using it.

**Never call `AssumeRole` manually inside every business operation.** The provider implements caching and refresh strategies to reduce STS calls, latency, and throttling risk.

## 15. When to Use an AssumeRole Profile vs. an Explicit Provider

| Criterion | Assume-Role Profile | `StsAssumeRoleCredentialsProvider` |
| --- | --- | --- |
| Configuring role ARN/source profile | Shared `config` file | Java builder/request |
| Convenience for CLI and local tooling | **Very convenient** | Requires code |
| Custom session duration | Java SDK 2.x profiles limit `duration_seconds` | Configurable in `AssumeRoleRequest` |
| MFA in shared profile | Java SDK 2.x does not support `mfa_serial` per support matrix | Can pass MFA parameters if app flow supports it |
| Dynamic session tags/source identity | Profile depends on static/shared settings | Configurable dynamically per request |
| Explicit lifecycle/refresh behavior | Managed by profile provider | Explicit stale/prefetch/async options |
| Best fit | Simple cross-account roles | Apps needing custom AssumeRole behavior |

### Using a Profile in Java

If the role profile only needs `role_arn`, `source_profile`, `external_id`, and `role_session_name`:

~~~java
try (ProfileCredentialsProvider credentials =
         ProfileCredentialsProvider.create("target-log-reader");
     S3Client s3 = S3Client.builder()
         .region(Region.AP_SOUTHEAST_1)
         .credentialsProvider(credentials)
         .build()) {

    s3.listBuckets();
}
~~~

## 16. Session Duration, Expiration, and Role Chaining

### STS AssumeRole Duration

Per the STS API:

- Minimum `DurationSeconds`: **900 seconds (15 minutes)**.
- Default if omitted: **3,600 seconds (1 hour)**.
- Maximum: **the target role's maximum session duration**, configurable between 1 and 12 hours.
- If the request exceeds the role's configured limit, STS rejects it.

### Role Chaining Is Capped at One Hour

**Role chaining** occurs when a role session uses its temporary credentials to assume yet another role.

Example:

~~~text
IAM Identity Center permission set role
          |
          | AssumeRole
          v
CrossAccountLogReader role
          |
          | AssumeRole
          v
EmergencyReadOnly role
~~~

When source credentials are already assumed-role credentials, the subsequent `AssumeRole` is capped at **1 hour maximum**, even if the target role allows 12-hour sessions. You cannot bypass the chaining cap by passing `duration_seconds = 43200`.

### Distinguishing Three Types of Durations

| Duration | Controlled By | Meaning |
| --- | --- | --- |
| IAM Identity Center session | Identity Center session duration/policy | How long the user's SSO session and refresh token remain valid |
| STS role session | `DurationSeconds` and role maximum session duration | How long temporary role credentials remain valid |
| Credential provider refresh window | `prefetchTime`, `staleTime`, provider implementation | When the SDK fetches fresh credentials ahead of expiry |

**Do not add durations across layers.** A 1-hour role session does not extend the SSO session; once the SSO session expires, the provider loses its source token for obtaining new role credentials.

## 17. MFA, ExternalId, Session Tags, and Source Identity

### 17.1. MFA in AssumeRole

A target role can require MFA via its trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/SourceDeveloperRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "Bool": {
          "aws:MultiFactorAuthPresent": "true"
        }
      }
    }
  ]
}
~~~

When calling the STS API directly, the request may need:

- `SerialNumber`: ARN/serial of the MFA device;
- `TokenCode`: current TOTP code.

MFA codes are short-lived. **Never hardcode token codes in source/config, never write them to logs, and never store TOTP codes as long-lived secrets.**

For Java SDK 2.x, `mfa_serial` is not supported via shared assume-role profile config under the current support matrix. If the target role requires MFA, select a supported authentication flow (such as Identity Center/MFA policy) or build a secure interactive provider/request flow; do not expect a Java profile to prompt interactively like the AWS CLI.

### 17.2. ExternalId

An External ID is typically used when a **third-party service provider** assumes a role in a customer account. The target account owner supplies a unique value; the trust policy validates it via `sts:ExternalId`.

External ID:

- Does not replace trust policies or least privilege;
- Is not a user password;
- Does not need to be added to every internal AssumeRole within the same organization;
- Should be issued and scoped per customer relationship in third-party access models.

### 17.3. Session Tags and ABAC

STS can attach **session tags** to a role session. IAM policies can reference principal/session tags for **attribute-based access control (ABAC)**.

Example tags:

~~~json
{
  "Tags": [
    {
      "Key": "Environment",
      "Value": "Development"
    },
    {
      "Key": "Team",
      "Value": "Orders"
    }
  ],
  "TransitiveTagKeys": [
    "Team"
  ]
}
~~~

To pass tags, the caller needs `sts:TagSession` permission when required by policy; the trust policy can restrict allowed keys and values. Transitive tags propagate across a role chain when configured.

### 17.4. SourceIdentity and RoleSessionName

- **RoleSessionName** distinguishes sessions in the assumed-role ARN and CloudTrail.
- **SourceIdentity** preserves the originating identity across role chaining; the target trust policy and caller permissions must allow `sts:SetSourceIdentity` as required.
- Never put emails, phone numbers, customer secrets, or unnecessary personal data into session names or tags.

A descriptive session name like `orders-api-prod` or `audit-job-20261120` is much easier to investigate than `session1`, while avoiding PII.

## 18. Effective Permissions After AssumeRole: Session Policies Only Restrict

When STS issues temporary credentials, effective permissions are not simply the union of all policies.

Conceptually:

~~~text
Effective permissions
  = target role identity permissions
  intersect session policy (if present)
  intersect permissions boundary / organization guardrails
  intersect resource policy evaluation
  minus explicit denies
~~~

- **Target role policy** defines the maximum permissions the role can grant.
- **Session policy** (inline or managed policy ARN) can further restrict what the session can do.
- A session policy **cannot grant permissions beyond the target role policy**.
- SCPs, permissions boundaries, resource policies, KMS key policies, and explicit denies can still block the request.

### Example

The target role grants `s3:GetObject` across the entire `company-logs` bucket, while a session policy restricts access to prefix `application/orders/`. The session can read only that prefix.

**Never treat a session policy as a fix for a broken trust policy.** If STS denies `AssumeRole`, fix the trust/caller permissions; if `AssumeRole` succeeds but S3 denies access, inspect target role, session, resource, and KMS policies.

## 19. How Credentials Refresh Works in Java SDK 2.x

Many providers maintain an internal credentials cache and refresh automatically, including:

- `StsAssumeRoleCredentialsProvider`;
- `StsAssumeRoleWithWebIdentityCredentialsProvider`;
- `WebIdentityTokenFileCredentialsProvider`;
- `ContainerCredentialsProvider`;
- `InstanceProfileCredentialsProvider`;
- `ProfileCredentialsProvider` when the profile uses SSO or AssumeRole.

### Stale Time and Prefetch Time

- **Prefetch time:** when the provider begins attempting to obtain fresh credentials before the current ones expire.
- **Stale time:** when credentials are considered stale and the provider must refresh to continue supplying valid credentials.
- **Async update:** background refresh, reducing the chance that the first request after a refresh boundary stalls waiting on STS.

Example:

~~~text
Temporary credentials expire at 12:00

11:50  Prefetch window begins (10 minutes before expiry)
11:55  Credentials considered stale (5 minutes before expiry)
12:00  Old credentials expire

The provider tries to refresh before the expiration boundary.
~~~

This is an illustrative timeline, not an SLA guaranteeing STS always returns fresh credentials at an exact timestamp. Network issues, STS throttling, permission changes, or SSO session expiration can still cause refresh failures.

### Java SDK 2.x Default Refresh Behavior

- STS-based providers cache temporary credentials.
- The SDK performs pre-expiration refresh with default prefetch/stale windows.
- Asynchronous refresh **is not enabled by default on every provider in Java SDK 2.x**; configure the builder when background refresh is desired.
- If a background refresh fails, the provider may continue serving the current credentials while they remain valid; once expired, requests will fail.
- Keep providers long-lived so the cache is reused; recreating providers repeatedly increases STS calls and latency.

**Do not schedule your own timer to call `resolveCredentials()`.** Service clients invoke the provider during request signing, and the provider handles returning valid credentials.

## 20. Anti-Patterns: Practices That Cause Outages or Leak Secrets

| Anti-Pattern | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Hardcoding access keys/secrets in Java | Leaks via Git/images/logs, hard to rotate | SSO/workload roles/credential providers |
| Fetching STS credentials once at startup | Credentials expire while the app keeps stale values | Use a provider with caching/refresh |
| Creating an STS provider per request | Amplifies `AssumeRole` calls, increases latency/throttling | Application-scoped/singleton provider |
| Using `StaticCredentialsProvider` with STS values | Provider does not know how to refresh the session | Use `StsAssumeRoleCredentialsProvider` |
| Logging session tokens | Tokens are active credential material that can be abused | Log identity ARN, request ID, and safe expiration metadata |
| Using legacy SSO profiles for long-running processes | SSO token does not auto-refresh | Use the modern SSO token provider config |
| Assuming `AWS_PROFILE` always overrides env vars | Environment credentials have higher precedence | Clear stale env vars or select an explicit provider |
| Granting `AdministratorAccess` to fix `AccessDenied` | Over-privileges workload and masks real policy bugs | Analyze trust, identity, target, resource, and KMS policies |
| Requesting 12h duration in role chaining | STS caps role chaining at 1 hour | Shorten role chains, rely on provider refresh |
| Copying MFA TOTP into config files | Short-lived code leaks and expires quickly | Use supported authentication flows |
| Using one generic role session name everywhere | Makes CloudTrail auditing difficult | Use meaningful session names without PII |
| Closing a provider while service clients still use it | Subsequent requests lose a valid credential provider | Manage lifecycle in DI/application scope |

## 21. Local Development, CI/CD, and AWS Runtimes: Choosing the Right Credential Source

### Local Developer

Use an IAM Identity Center SSO token provider profile:

~~~text
aws configure sso
aws sso login --profile dev-sso
Java → ProfileCredentialsProvider("dev-sso")
~~~

Each developer signs in with their personal identity and receives a permission set tailored to their role. Never share SSO caches or credentials between individuals.

### CI/CD

Prefer OIDC federation or a role the CI runner is authorized to assume:

~~~text
CI job → OIDC identity token
       → STS AssumeRoleWithWebIdentity
       → Temporary role credentials
       → Deploy AWS resources
~~~

Scope the trust policy to the exact issuer, audience, and subject/repository/environment for your CI provider. Never store long-lived IAM user secret keys in repository secrets when federation is available.

### Amazon EC2

Attach an IAM role via an instance profile. The Java SDK uses `DefaultCredentialsProvider`/`InstanceProfileCredentialsProvider`, retrieving and refreshing credentials via IMDS.

### Amazon ECS

Assign a **task role** to the ECS task. The container credentials endpoint supplies dedicated credentials to the application task. Never confuse the task role with the **task execution role** used by the ECS agent to pull images, write logs, or fetch container startup secrets.

### Amazon EKS

Use **EKS Pod Identity** or **IAM Roles for Service Accounts (IRSA)** per cluster architecture. The SDK picks up the web identity token/credentials from the configured environment. Never mount long-term keys in Kubernetes Secrets unless a controlled exception applies.

### Cross-Account Workloads

If an ECS task role or EC2 instance role needs access to another account:

1. Grant a minimal role to the source workload;
2. Configure the target role to trust the workload role ARN/account;
3. Grant `sts:AssumeRole` to the source role;
4. Use `StsAssumeRoleCredentialsProvider` or a profile with `credential_source`;
5. Configure appropriate session names/auditing, duration, and resource permissions.

## 22. Lab 1: SSO Login and Verifying Account Identity Before Running Java

> **Prerequisites:** AWS CLI v2, Java 17+ (or project-compatible version), Maven, and a permission set assigned by your organization. This lab only reads identity and lists buckets; it does not require creating or deleting AWS resources.

### Step 1: Configure an SSO Profile

~~~bash
aws configure sso --profile dev-sso
~~~

Complete the wizard with the start URL, SSO Region, account, permission set, service Region, and profile name.

### Step 2: Sign In

~~~bash
aws sso login --profile dev-sso
~~~

### Step 3: Verify Identity

~~~bash
aws sts get-caller-identity --profile dev-sso
aws configure list --profile dev-sso
~~~

Verify the account ID and ARN. If the account or role is wrong, stop before running any state-changing commands.

### Step 4: Run the Java Example

Run `SsoS3Example` from Section 9 after adding the `sso`, `ssooidc`, and `s3` dependencies. If your organization does not grant `s3:ListAllMyBuckets`, swap in a read-only API your permission set actually allows.

## 23. Lab 2: Verifying AssumeRole with CLI and Java

### Step 1: Use the Source SSO Profile

~~~bash
aws sts get-caller-identity --profile dev-sso
~~~

### Step 2: Test AssumeRole with the CLI

~~~bash
aws sts assume-role \
  --profile dev-sso \
  --role-arn arn:aws:iam::222233334444:role/CrossAccountLogReader \
  --role-session-name lab-log-reader \
  --duration-seconds 3600
~~~

If the target requires an external ID, add `--external-id` with the value provided by the target account administrator. Never put MFA TOTP codes or external IDs into logs.

**The CLI response contains secrets and a session token.** Never paste the output into chat, tickets, or logs. Only verify that credentials and expiration are returned; use `--query` to restrict output when needed.

### Step 3: Test the Java Provider

Run `AssumeRoleS3Example` from Section 14 against your lab target role and bucket/prefix. The provider fetches and refreshes credentials automatically; do not export STS output into environment variables.

### Step 4: Verify Identity After AssumeRole

In Java, construct an `StsClient` using the same assumed provider and call `getCallerIdentity()` to observe the ARN/account of the **target role session**. Compare it with the source identity from the initial profile.

~~~java
GetCallerIdentityResponse identity = stsClient.getCallerIdentity();
System.out.println("Account: " + identity.account());
System.out.println("Arn: " + identity.arn());
~~~

Never print the access key, secret key, or session token.

## 24. Lab 3: Observing Refresh Without Waiting for Credentials to Expire

In a lab environment, configure an explicit provider:

- Session duration: 900 seconds or 3600 seconds per target role;
- `prefetchTime`: 5–10 minutes;
- `staleTime`: 1–5 minutes;
- `asyncCredentialUpdateEnabled(true)`.

Log **when the provider fetches credentials, STS request IDs, and expiration metadata** using safe logging, without recording credential values. Monitor CloudTrail `AssumeRole` events to confirm when refreshes occur.

~~~text
Application starts
  → First service call resolves credentials
  → STS AssumeRole event appears
  → Provider caches expiration
  → Prefetch window begins
  → Provider requests new credentials
  → Later service calls use refreshed session
~~~

**Do not run load tests by repeatedly invoking AssumeRole.** Providers are designed to cache; test refresh using a short lab session or low-frequency log/CloudTrail observation.

## 25. CloudTrail and Auditing: Knowing Who Uses Which Role

STS `AssumeRole` generates audit events in CloudTrail. When investigating, check:

- Source principal (which user or role called STS);
- Target role ARN;
- Role session name;
- Source identity (if present);
- External ID condition/assume context per the event;
- Timestamp, Region, source IP, and user agent;
- Service API calls made after the role was assumed;
- `AccessDenied`/explicit denies at the target service or KMS.

**`RoleSessionName` is not an authorization mechanism.** It identifies the session in logs; trust policies and permissions policies govern who can assume a role and what they can do.
## 26. Troubleshooting: From Credential Source to Service Permissions

| Symptom | Common Cause | How to Check / Fix |
| --- | --- | --- |
| `Unable to load credentials from any provider` | No source credentials, wrong profile/path, missing SSO modules, not logged in | Check `AWS_PROFILE`, config path, `sso`/`ssooidc`/`sts` dependencies, run `aws sso login` |
| SSO profile works in CLI but Java fails | Java SDK missing SSO dependencies/version or using a different profile name | Add `sso` + `ssooidc`, verify BOM/version, pass exact profile to `ProfileCredentialsProvider` |
| Java uses the wrong account/role | System properties or environment variables precede the profile | Check `AWS_ACCESS_KEY_ID`, `AWS_SESSION_TOKEN`, JVM `-Daws.*`, call `GetCallerIdentity` |
| `InvalidGrant` / refresh token invalid | SSO session expired, revoked, or token cache corrupted | Re-login with `aws sso login`; never hand-edit the token cache |
| `ExpiredToken` | Static credentials expired, provider does not refresh, or source session expired | Use a caching/refreshing provider; verify SSO session and role expiration |
| `AccessDenied` calling `sts:AssumeRole` | Source role lacks `sts:AssumeRole` or target trust does not trust source | Check both policies, principal ARN, account, SCPs, and permissions boundaries |
| AssumeRole succeeds but S3/DynamoDB returns `AccessDenied` | Target role policy, resource policy, bucket policy, KMS key policy, or session policy lacks permissions | Verify target caller ARN and resource-level permissions |
| Role chaining duration validation error | `DurationSeconds` greater than 3600 when source is already a role session | Reduce session to at most 1 hour or shorten the role chain |
| Invalid external ID | `ExternalId` mismatches trust policy or was omitted when required | Obtain exact value from account owner; check spelling/condition |
| MFA serial not supported in Java profile | Java SDK 2.x does not support `mfa_serial` in shared assume-role profiles | Use a supported auth flow or explicit STS request if app handles MFA securely |
| STS request `RegionDisabled` | STS Region/endpoint disabled or misconfigured endpoint in account | Check STS Region, regional endpoint, account settings, and networking |
| `SignatureDoesNotMatch` / `RequestTimeTooSkewed` | Clock skew on host/container, proxy mutating request, or Region/signing mismatch | Sync NTP, verify Region and HTTPS proxy |
| SSO login works but app cannot reach endpoints | Egress/DNS/proxy to IAM Identity Center, SSO OIDC, or STS blocked | Verify DNS, TLS, outbound HTTPS, and proxy settings |
| Continuous STS calls for refresh | Provider recreated repeatedly, stale/prefetch windows too tight, or replicas not sharing cache | Use a process-wide singleton provider; inspect CloudTrail and refresh settings |
| Background refresh enabled yet still fails | Refresh denied or failed on network, SSO session expired, or target trust changed | Inspect root exception, CloudTrail `AssumeRole`, SSO login, and role policy |
| App loses credentials after logout | `aws sso logout` deletes the cached session | Log in again; avoid logging out sessions shared with running apps |
| Hard to distinguish callers in CloudTrail | Generic `RoleSessionName` or missing `SourceIdentity` | Use meaningful session names, `SourceIdentity`/session tags when policy permits |

### Ordered Investigation Workflow

~~~text
1. Identify whether the app runs locally, on EC2, ECS, EKS, or CI/CD.
2. Call GetCallerIdentity to verify the actual account and ARN.
3. Check the explicit provider or default chain precedence.
4. If SSO: check sso-session config, login status, sso_region,
   sso/ssooidc dependencies, and refresh-token session.
5. If AssumeRole: check source credentials, target trust policy,
   source sts:AssumeRole permission, role ARN, and session duration.
6. If target service AccessDenied: check target role policy,
   resource policy, KMS key policy, session policy, and explicit denies.
7. If ExpiredToken: verify whether the provider refreshes or holds static values.
8. Check STS Region/network, clock sync, and CloudTrail events.
9. Fix the exact failing layer in lab/staging; never grant admin rights to test.
10. Re-verify identity ARN, successful service calls, and refresh behavior.
~~~

## 27. Securing Credentials and IAM Roles in Production

### Least Privilege for Both Roles

- The source role only needs permission to assume the exact target role ARN.
- The target role only grants the required actions and resources.
- Restrict the trust principal; never trust an entire account when only one workload or user role needs access.
- Use appropriate condition keys such as `aws:PrincipalOrgID`, `aws:PrincipalArn`, `aws:MultiFactorAuthPresent`, or `ExternalId` when supported by the architecture.
- Inspect SCPs, permissions boundaries, session policies, and resource policies; explicit denies always take precedence and must be addressed.

### Protecting the SSO Cache and Source Credentials

- The SSO cache lives on the user's machine; protect OS accounts, filesystem permissions, disk encryption, and endpoint security posture.
- Never copy the SSO cache directory to shared drives, container images, or repositories.
- Never send tokens, access keys, secret keys, or session tokens in tickets, chat, or email.
- Never enable debug logging that could print Authorization headers or credentials.
- On shared workstations, log out when finished and never share user profiles.
- Never read or parse the token cache in business code.

### STS, Networking, and System Time

- Use STS regional endpoints matching the approved Region and architecture.
- Permit outbound HTTPS/TLS to IAM Identity Center, SSO OIDC, STS, and required AWS service endpoints.
- Synchronize host/container clocks with NTP; SigV4 signatures depend on accurate timestamps.
- Enforce TLS certificate validation; never disable hostname verification to work around proxy or certificate issues.
- Monitor CloudTrail and alert on `AssumeRole` calls from unexpected principals, Regions, or session names.

### Managing Session Tags and Auditing

Session tags serve as attributes for ABAC; permit only controlled keys and values. `SourceIdentity` and `RoleSessionName` aid investigation, but do not replace permissions. Avoid putting PII or secrets into session metadata since metadata appears in logs and audit records.

## 28. Credential Architecture Patterns by Environment

| Need | Recommended Design | Reason |
| --- | --- | --- |
| Developer running Java on a laptop | IAM Identity Center + SSO token provider + `ProfileCredentialsProvider` | No IAM user access keys needed; refreshes while SSO session is valid |
| Java service on ECS | ECS task role + `DefaultCredentialsProvider` | Container credentials provisioned and refreshed by runtime |
| Java service on EC2 | Instance profile + `DefaultCredentialsProvider` | No keys stored on the instance |
| Java service on EKS | Pod Identity or IRSA/web identity | Credentials bound to workload/service account |
| CI/CD deploying to another account | OIDC identity + `AssumeRoleWithWebIdentity` or runner role + `AssumeRole` | Federation, no long-term keys needed |
| Developer reading data in another account | SSO source profile + target role profile/provider | Separates personal permission set from target permissions |
| Third-party vendor accessing customer account | Cross-account role + `ExternalId` + least privilege + CloudTrail | Mitigates confused-deputy risk and enables auditing |
| Break-glass support | Dedicated role, MFA/approval, short duration, session auditing | Controlled emergency access |

### A Key Design Principle

**Humans authenticate via federation; workloads obtain roles from their runtime.** Never use a developer's SSO cache to run production ECS/EKS/EC2 workloads, and never use static access keys in place of a runtime role on AWS when a runtime role fits.

## 29. Practice Exercises and Self-Check Questions

### Exercise 1 — SSO Token Provider

A developer puts `sso_start_url`, `sso_region`, `sso_account_id`, and `sso_role_name` directly inside a profile. The Java application runs for 8 hours and then fails authentication.

**Task:** Explain why the legacy profile lacks automatic refresh; rewrite the configuration using `sso-session`, `sso_registration_scopes`, profile references, and login/`get-caller-identity` commands.

### Exercise 2 — Credentials Precedence

A workstation is logged in to SSO profile `dev-sso`, yet Java keeps accessing an old account. The shell has `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` set.

**Task:** Explain the provider chain order, how to inspect JVM system properties/environment variables, and when to use `ProfileCredentialsProvider` directly.

### Exercise 3 — Cross-Account AssumeRole

Account A has source role `SourceDeveloperRole`; account B has `CrossAccountLogReader`. STS returns `AccessDenied`.

**Task:** Check account B's trust policy, account A's source identity policy, the target permissions policy, and guardrails (SCPs/permissions boundaries/resource policies). Diagram the flow source → STS → target role → S3.

### Exercise 4 — Role Chaining Duration

A developer uses SSO credentials to assume Role A, and Role A assumes Role B. Target Role B allows a 12-hour max session, yet STS rejects a 7200-second duration request.

**Task:** Explain the 1-hour role chaining cap and propose reducing role hops or setting an appropriate duration.

### Exercise 5 — Java SDK Refresh

A service creates `StsAssumeRoleCredentialsProvider` on every HTTP request and calls `AssumeRole` each time.

**Task:** Describe STS call amplification and latency/throttling risks; rewrite the provider as a singleton with `prefetchTime`, `staleTime`, `asyncCredentialUpdateEnabled`, and proper close lifecycle.

### Exercise 6 — MFA and ExternalId

A target role requires MFA and `ExternalId`. A team adds `mfa_serial` to a Java shared profile expecting the SDK to prompt for TOTP.

**Task:** State the Java SDK 2.x support matrix limitation; distinguish MFA serial/token code from `ExternalId`; propose an appropriate interactive/federated flow and safe logging practices without secrets.

### Exercise 7 — Production on ECS

A Java app runs on ECS Fargate, but a developer copied their laptop SSO config/cache into the container to access another account.

**Task:** Redesign using the task role as source credentials to assume the target cross-account role. Distinguish the task role from the task execution role; specify STS permissions and the trust policy.

### Exercise 8 — CloudTrail Auditing

CloudTrail records numerous `AssumeRole` events all using a generic session name `app-session`.

**Task:** Propose appropriate `RoleSessionName`, `SourceIdentity`, and session tags to trace service, team, and environment without putting PII or secrets into metadata.

### Short Questions

1. **What is an AWS IAM Identity Center permission set?** A set of permissions assigned to a user/group on an AWS account.
2. **Is the SSO access token a SigV4 session token?** No.
3. **How does the modern SSO token provider profile differ from legacy?** It supports a refresh-token flow; legacy does not automatically refresh the SSO token.
4. **Which AWS SDK for Java 2.x modules are needed for SSO profiles?** `sso` and `ssooidc`.
5. **Does the default credentials provider chain check environment variables or profiles first?** Environment variables before profiles.
6. **What does `ProfileCredentialsProvider` do?** Reads a named profile and resolves source/SSO/role credentials.
7. **What does `AssumeRole` return?** Access key ID, secret access key, session token, and expiration.
8. **Which sides must be checked for cross-account access?** Target trust policy and source `sts:AssumeRole` permission, along with effective permissions.
9. **What is the maximum duration for role chaining?** One hour.
10. **What is the minimum `AssumeRole` duration?** 900 seconds.
11. **How high can a target role's max duration go?** Up to 12 hours if role settings allow and it is not capped by role chaining.
12. **Can a session policy expand a target role's permissions?** No; it can only restrict them.
13. **Is `ExternalId` a password?** No; it is an anti-confused-deputy identifier for third-party access.
14. **Does Java SDK 2.x shared assume-role profile support `mfa_serial`?** No, per the current support matrix.
15. **Does Java SDK 2.x shared assume-role profile support `duration_seconds`?** No, per the current support matrix.
16. **Does `StsAssumeRoleCredentialsProvider` cache credentials?** Yes.
17. **Is async refresh always enabled by default in Java SDK 2.x?** No; configure it on the builder when needed.
18. **Should you create a credentials provider per request?** No; reuse it across the application lifecycle.
19. **Do EC2/ECS need access keys copied into the app?** No; use instance/task roles.
20. **Does `AWS_PROFILE` always override `AWS_ACCESS_KEY_ID`?** No; environment credentials take precedence over the profile stage.

## 30. Pre-Production Checklist

- [ ] Local developers use the modern IAM Identity Center SSO token provider config without creating long-term access keys.
- [ ] `sso_start_url`, `sso_region`, `sso_account_id`, `sso_role_name`, and `sso_registration_scopes` are configured accurately.
- [ ] SSO access tokens are clearly distinguished from AWS role credentials/session tokens.
- [ ] The Java project uses a unified BOM/version and includes `sso`, `ssooidc`, `sts`, and required service modules.
- [ ] The active provider's account/role has been verified via `GetCallerIdentity`.
- [ ] System properties and environment variables have been checked to ensure they do not unintentionally override the SSO profile.
- [ ] Cross-account roles have a trust policy matching the exact principal, source `sts:AssumeRole` permission, and least-privilege target permissions.
- [ ] `ExternalId` is used only when required by the target trust policy, with the value supplied by the target account owner.
- [ ] MFA requirements follow a supported flow; `mfa_serial` is not assumed to work in Java shared profiles.
- [ ] `RoleSessionName`, `SourceIdentity`, and session tags aid auditing and contain no PII/secrets.
- [ ] Role chaining does not request a duration exceeding 1 hour.
- [ ] Session duration does not exceed the target role's maximum session duration.
- [ ] `StsAssumeRoleCredentialsProvider` is reused, with caching, prefetch/stale settings, and async refresh where appropriate.
- [ ] Providers and clients are closed in the right order at application shutdown.
- [ ] EC2/ECS/EKS runtimes use workload roles/identities; personal SSO caches are never copied from laptops.
- [ ] CI/CD uses OIDC/workload federation where possible rather than relying on long-term IAM user keys.
- [ ] CloudTrail records `AssumeRole` events; session names and source identity support traceability.
- [ ] IAM policies are reviewed for least privilege, resource policies, KMS key policies, SCPs, and permissions boundaries.
- [ ] SSO caches, tokens, and session tokens never appear in Git, logs, tickets, or container images.
- [ ] Network, DNS, TLS, STS regional endpoints, and system clocks are verified.
- [ ] Runbooks exist for SSO session expiration, AssumeRole `AccessDenied`, `ExpiredToken`, and credential refresh failures.
- [ ] Refresh has been tested in a lab with a short session, verified via CloudTrail, and confirmed to keep service calls working.
- [ ] AWS SDK modules are pinned to the same version via the BOM; SDK versions are never mixed.
- [ ] A clear re-authentication procedure exists when an extended SSO session expires or is revoked.

## 31. Summary

**SSO** authenticates users and provides a path to temporary role credentials tied to permission sets. **STS AssumeRole** lets a source identity transition to another role when trust relationships and caller permissions allow it. **Credential providers** bridge these mechanisms to service clients while managing caching and refreshes.

Key points to remember:

1. For local development, prefer **IAM Identity Center SSO token provider profiles** using `sso-session`; legacy SSO profiles do not support automatic token refresh.
2. AWS SDK for Java 2.x needs the **sso** and **ssooidc** modules for SSO profiles, and **sts** when using STS providers.
3. The default credentials chain checks system properties and environment variables before shared profiles; stale env credentials can make the SDK use the wrong account.
4. Cross-account `AssumeRole` requires both a target trust policy and source `sts:AssumeRole` permission; target role permissions govern actions after assuming the role.
5. Role chaining is capped at one hour; a role's duration does not extend the SSO session or source session.
6. `StsAssumeRoleCredentialsProvider` caches credentials and can prefetch/refresh in the background; keep providers long-lived instead of storing access keys, secrets, or session tokens yourself.
7. On EC2/ECS/EKS/CI, prefer workload identities and federation; never use personal SSO caches or long-term keys for production workloads.
8. Least privilege, CloudTrail, session metadata, TLS, network reachability, and secret hygiene are mandatory parts of credential design.

### Official AWS Reference Documentation

- [AWS SDK for Java 2.x — Using credentials](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html)
- [Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [Specify a credentials provider](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-providers.html)
- [Credentials caching in Java SDK 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credential-caching.html)
- [Access credentials for interactive development](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-temporary.html)
- [IAM Identity Center credential provider](https://docs.aws.amazon.com/sdkref/latest/guide/feature-sso-credentials.html)
- [Configure IAM Identity Center with AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [AWS CLI IAM Identity Center concepts](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso-concepts.html)
- [Assume role credential provider settings](https://docs.aws.amazon.com/sdkref/latest/guide/feature-assume-role-credentials.html)
- [AWS STS AssumeRole API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [STS examples using AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sts_code_examples.html)
- [AWS IAM role chaining and session duration](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)
- [AWS SDK for Java 2.x troubleshooting](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/troubleshooting.html)

**Operational note:** SDK/CLI versions, SSO session durations, role maximum session durations, permission sets, STS Regions, and provider refresh behavior can vary by organization and account. Check the support matrix for your Java SDK 2.x version, test in a lab account, and verify identity/expiration via STS and CloudTrail before moving to production.
