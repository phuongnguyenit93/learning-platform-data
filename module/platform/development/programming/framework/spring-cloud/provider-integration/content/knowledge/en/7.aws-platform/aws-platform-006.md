# STS AssumeRole and Cross-Account Resource Access

## 1. Context and Learning Objectives

Suppose an order-processing **Spring Boot** application runs in **AWS Account A**, yet the receipt data it needs to read resides in **Amazon S3 in AWS Account B**. The application cannot obtain permissions on bucket B simply by adding the Spring Cloud AWS starter, creating an `S3Client`, or changing `AWS_REGION`. AWS must determine **which principal is authorized to access Account B**, whether the identity transition is valid, and whether the target resource permits the operation.

This lesson belongs to the **AWS Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The scope of the full module is practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud: configuring identity and permissions, accessing storage, messaging, and data, protecting secrets, integration testing, and evaluating differences across providers. This lesson specifically focuses on **AWS Security Token Service (STS) `AssumeRole`** and how a Spring Boot application uses **temporary credentials** to call resources in another account.

**Objectives after this lesson:**

- Distinguish direct access via resource-based policies from assuming a role in the target account.
- Understand the flow `Account A principal → STS AssumeRole → role session in Account B → AWS service`.
- Construct a **trust policy**, source **identity-based policy**, and target role **permissions policy**.
- Integrate `StsAssumeRoleCredentialsProvider` from **AWS SDK for Java v2** into Spring Boot/Spring Cloud AWS with credential refresh and client lifecycle management.
- Distinguish failure to assume a role from assuming a role successfully yet being denied by S3/SQS/Secrets Manager.
- Design least privilege, session controls, AWS regions, cross-account KMS, and safe end-to-end testing.

> **Version note:** Java examples use AWS SDK for Java **2.x**, matching the common integration path of Spring Cloud AWS 3.x. Different releases may carry distinct Java, Spring Boot, BOM, and SDK requirements; consult documentation for the exact release in use before applying. Account IDs, ARNs, buckets, queues, and URLs in this lesson are **illustrative sample data for learning**.

## 2. Why Separate Multiple AWS Accounts?

AWS Organizations and multi-account strategies commonly use distinct accounts for development, testing, production, security, or partner data. For example:

| Account | Illustrative Account ID | Role |
| --- | --- | --- |
| Account A – application | `111122223333` | Runs `receipt-api` using an ECS task role |
| Account B – data | `444455556666` | Manages bucket `example-partner-receipts` and a data-reading IAM role |

Separating accounts yields clearer governance, billing, quota, IAM, and organizational policy boundaries. However, when service A needs to read data in B, **cross-account access** must be configured deliberately. Two accounts belonging to the same AWS Organization do **not automatically** gain permission to read each other's resources.

Two common access patterns exist:

1. **Resource-based policy for the source principal:** resource B (such as an S3 bucket or SQS queue) directly allows a specific role from A to perform operations. The principal remains A's role/session.
2. **STS AssumeRole:** a role in A is allowed to assume a role managed by B; STS returns temporary credentials for a **role session in B**, and the client uses those credentials to call B's S3/SQS/Secrets Manager.

Not every AWS service supports resource-based policies in the same way, and some security requirements make the assume-role model easier to govern. Choose based on each service's semantics and policies.

### 2.1. Comparing the Two Approaches

| Criterion | Direct access via resource policy | Assume role in target account |
| --- | --- | --- |
| Principal signing requests to resource B | Principal from A | Session of a role belonging to B |
| Core prerequisites | Policy in A and resource policy in B permit the required actions | `sts:AssumeRole` permission in A; trust on role B; resource permissions for role B |
| Best suited when | Service supports clear resource policies and only a few operations are needed | You want role B as a centralized permission boundary across multiple operations/resources |
| STS step in app? | Not required | Yes, performed by the SDK or profile |
| Role session refresh mechanism | No role B session to refresh | Must refresh temporary credentials for role B |
| Must evaluate KMS / denies / SCPs? | Yes | Yes |

For example, S3 bucket B can grant a bucket policy to role A, yet objects encrypted with SSE-KMS may still require permissions on the KMS key. With AssumeRole, role B's permissions are usually administered within Account B; bucket policies, KMS policies, and explicit denies can still impose further constraints.

## 3. Architecture of STS AssumeRole Between Two Accounts

A typical flow:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot in Account A
    participant Base as Source Role A
    participant STS as AWS STS
    participant RoleB as Target IAM Role B
    participant S3 as Account B S3 Bucket

    App->>Base: Retrieve workload credentials
    App->>STS: AssumeRole(RoleArn B, RoleSessionName)
    Note over STS,RoleB: Check sts:AssumeRole permission in A<br/>and role B trust policy
    STS-->>App: Temporary credentials for role session B
    App->>S3: GetObject (signed with credentials B)
    Note over RoleB,S3: Check role permissions, bucket policy,<br/>KMS policy, and related denies/conditions
    S3-->>App: Object or specific error
~~~

**Key point:** STS does not transfer resource ownership and does not copy role B into Account A. It issues **a temporary session** of IAM role B to an eligible client. When calling S3, AWS evaluates permissions against that session and all applicable policies.

### 3.1. Distinguishing Three Principals

- **Initiating user or workload:** e.g., an ECS task in A using role `receipt-api-task-prod`.
- **Target IAM role:** e.g., `arn:aws:iam::444455556666:role/partner-receipt-reader`. The role has a trust policy and a permissions policy.
- **Assumed-role session:** the temporary principal, typically having an ARN like `arn:aws:sts::444455556666:assumed-role/partner-receipt-reader/receipt-reader-prod`.

The ARN syntax of an IAM role and an assumed-role session are **not identical**. When analyzing CloudTrail or checking STS `GetCallerIdentity`, distinguish the configured role from the actual session sending the request.

### 3.2. Prerequisites for AssumeRole to Succeed

In a standard cross-account scenario, all of the following must hold simultaneously:

1. **Source principal A** is permitted by an identity-based policy to call `sts:AssumeRole` on the exact role ARN in B.
2. **Role B's trust policy** permits source principal A to assume the role via `sts:AssumeRole` and satisfies all trust conditions.
3. No explicit deny or other organizational/session constraint blocks assuming the role.
4. If role B requires an **ExternalId, MFA, session tags, or source identity**, the request provides matching values.
5. Source credentials are still valid to sign the STS request.

After assuming the role succeeds, **role B** still needs permissions for the specific operation/resource. Never equate success at the STS step with permission to read a bucket or secret.

## 4. Designing Policies: Source A, Trust B, Permissions B

Assume:

- Account A: `111122223333`.
- Source role in A: `arn:aws:iam::111122223333:role/receipt-api-task-dev`.
- Account B: `444455556666`.
- Target role in B: `arn:aws:iam::444455556666:role/partner-receipt-reader-dev`.
- S3 bucket in B: `example-partner-receipts`.
- Read-only prefix: `receipts/dev/`.

All values are **illustrative data**. Real deployments must substitute valid ARNs and apply changes via Infrastructure as Code and established authorization workflows.

### 4.1. Account A: Allow Source Role to Call STS AssumeRole

Identity-based permissions policy attached to the source role in A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumePartnerReceiptReader",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/partner-receipt-reader-dev"
    }
  ]
}
~~~

This policy does **not** directly grant permission to read S3 objects in B. It only allows A to ask STS to assume that specific target role. If the application must assume two distinct roles, list their specific ARNs rather than setting `"Resource": "*"`.

In this model, **`iam:PassRole` does not replace `sts:AssumeRole`**. `iam:PassRole` generally relates to passing a role to an AWS service when creating or configuring resources like an ECS task, whereas here application code asks STS to create a role session.

### 4.2. Account B: Trust Policy of the Target Role

Trust policy attached to `partner-receipt-reader-dev`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustReceiptApiTaskRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/receipt-api-task-dev"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Meaning: role B accepts assume-role requests only when authenticated as that specific IAM role in A (while other policy/organization conditions still apply).

Avoid opening trust to an entire account or unnecessary principals. For external partners, consider `sts:ExternalId` conditions, principal scoping, session duration limits, and proper approval workflows.

**A trust policy belongs to an IAM role**, not a bucket policy. Putting a trust policy inside S3 bucket configuration will not make STS `AssumeRole` succeed.

### 4.3. Account B: S3 Permissions of the Target Role

Permissions policy attached to role B itself:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPartnerReceiptsOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::example-partner-receipts/receipts/dev/*"
    }
  ]
}
~~~

Role B can read only objects under prefix `receipts/dev/` provided no other policy blocks it. `s3:ListBucket` is not needed if code only calls `GetObject` with known keys. If object listing is required, grant `s3:ListBucket` on the **bucket ARN** with an appropriate prefix condition.

When the bucket is in the same Account B as target role B, the role's identity-based policy may suffice for basic S3 access; however, an **explicit deny in a bucket policy**, VPC endpoint policy, KMS key policy, or organizational conditions can still block access. For objects encrypted with a customer-managed KMS key, evaluate `kms:Decrypt` and the key policy per your encryption design.

### 4.4. Reading the Three Policies in Order

| Stage | Question to verify | Where does it live? |
| --- | --- | --- |
| A calls STS | Does source role A have `sts:AssumeRole` on role B? | Identity policy A |
| STS approves | Does role B trust source principal A and matching conditions? | Trust policy B |
| Role B calls S3 | Is role B granted `s3:GetObject` on the exact object ARN? | Permissions policy B |
| S3/KMS responds | Is there any deny from bucket policy/SCP/endpoint/KMS? | Related policies, accounts, and resources |

**Failure at step 1/2:** you do not receive temporary credentials for role B. **Failure at step 3/4:** STS succeeds, yet `GetObject` still fails with `AccessDenied`. These two error groups must be investigated separately.

## 5. Choosing the Initial Credential Source for Account A

The application must hold valid source credentials to call STS.

| Spring Boot runtime environment | Credential source to use | What to avoid |
| --- | --- | --- |
| Developer laptop | AWS CLI profile + IAM Identity Center, sandbox permission set | Putting static access keys into `application.yml` |
| CI outside AWS | OIDC federation/STS, restricted role for test jobs | Long-lived access keys stored in pipelines |
| EC2 | Instance profile of source role A | Mixing credentials from multiple profiles/env vars |
| ECS/Fargate | **Task role** of service A | Confusing task execution role with task role |
| EKS | IRSA or EKS Pod Identity for Pod A | Sharing the node role across all Pods |

With **AWS SDK for Java v2**, `DefaultCredentialsProvider` checks sources in the standard order: Java system properties → environment variables → web identity → shared profile → container credentials → EC2 instance profile. Therefore, an old environment key can override the ECS/Pod role configured by operators.

If the application runs under source role A, the SDK `StsClient` should be constructed using the **same verified source credential strategy**. Never initialize an STS client with static credentials copied from a developer machine and deploy it to production.

## 6. Preparing AWS SDK v2 and Spring Cloud AWS Dependencies

### 6.1. Separating Library Responsibilities

**AWSpring/Spring Cloud AWS** configures beans, templates, listeners, and SDK integration in Spring Boot applications. However, **`AssumeRole` is an STS API in the AWS SDK**; at the Java level, the key classes belong to packages:

- `software.amazon.awssdk.services.sts.StsClient`.
- `software.amazon.awssdk.services.sts.model.AssumeRoleRequest`.
- `software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider`.
- `software.amazon.awssdk.auth.credentials.AwsCredentialsProvider`.

Distinguish these from SDK v1 under `com.amazonaws.*`; never mix sample code from both generations.

### 6.2. Illustrative Maven Dependencies

Assuming the Spring Boot project already selected a compatible AWSpring BOM and dependency management controls SDK versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>

    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>

    <!-- Declare directly when application code imports S3Client -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
</dependencies>
~~~

This snippet **omits** the Spring Boot parent and BOM that a real project requires. If Maven reports an unmanaged version, add a compatible BOM or verified SDK version. Do not pick an arbitrary `sts` version that differs from other resolved SDK v2 modules.

In Gradle Kotlin DSL:

~~~kotlin
dependencies {
    // Assumes the project already imports compatible AWSpring and SDK platforms/BOMs.
    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("software.amazon.awssdk:sts")
    implementation("software.amazon.awssdk:s3")
}
~~~

Beyond compile time, inspect **`runtimeClasspath`**: the STS client relies on auth, HTTP, and related SDK modules. An SDK version mismatch causes runtime errors like `NoSuchMethodError` or `NoClassDefFoundError`; check the dependency tree instead of blaming IAM.

## 7. Using StsAssumeRoleCredentialsProvider in Spring Boot

### 7.1. Why Choose a Refreshing Provider?

`AssumeRole` returns temporary AWS credentials with an expiration timestamp. Calling STS manually once and placing the access key/secret/session token strings into a `StaticCredentialsProvider` causes long-running applications to fail with `ExpiredToken`.

AWS SDK for Java v2 provides `StsAssumeRoleCredentialsProvider` to **fetch and refresh** credentials for the target role. This provider performs STS calls via a **source `StsClient`**, then supplies role B credentials to service clients such as S3.

~~~mermaid
flowchart LR
    A["DefaultCredentialsProvider: source role A"] --> B["StsClient"]
    B --> C["StsAssumeRoleCredentialsProvider"]
    C --> D["Cross-account S3Client"]
    D --> E["Account B S3 bucket"]
    C -. "Refresh before/when session needs renewal" .-> B
~~~

### 7.2. Application Configuration

Configuration contains only **role ARN and regions**, with no secrets:

~~~yaml
app:
  aws:
    sts:
      region: ${AWS_STS_REGION:ap-southeast-1}
    cross-account:
      role-arn: ${APP_TARGET_ROLE_ARN}
      s3-region: ${APP_TARGET_S3_REGION:ap-southeast-1}
      bucket: ${APP_TARGET_BUCKET}
~~~

`AWS_STS_REGION` specifies the STS endpoint called by the source client, whereas `APP_TARGET_S3_REGION` is the region of the target S3 bucket. The two regions can differ in configuration/routing and must not be confused with the role's **AWS account ID**.

This configuration assumes required variables are supplied when the application runs. In production, provide the role ARN/region/bucket through deployment configuration or a secrets manager per organizational policy; never hard-code production accounts in shared code.

### 7.3. Declaring STS, Provider, and S3 Client Beans

A Spring Boot configuration can be written as:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;

@Configuration
public class CrossAccountAwsConfiguration {

    @Bean(destroyMethod = "close")
    StsClient sourceStsClient(
            @Value("${app.aws.sts.region}") String stsRegion) {
        // By default, obtain source credentials from the runtime environment:
        // local profile / ECS task role / EKS workload identity / EC2 role.
        return StsClient.builder()
                .region(Region.of(stsRegion))
                .build();
    }

    @Bean(destroyMethod = "close")
    StsAssumeRoleCredentialsProvider crossAccountCredentials(
            StsClient sourceStsClient,
            @Value("${app.aws.cross-account.role-arn}") String roleArn) {

        AssumeRoleRequest request = AssumeRoleRequest.builder()
                .roleArn(roleArn)
                .roleSessionName("receipt-reader-dev")
                .durationSeconds(3600)
                .build();

        return StsAssumeRoleCredentialsProvider.builder()
                .stsClient(sourceStsClient)
                .refreshRequest(request)
                .build();
    }

    @Bean(name = "crossAccountS3Client", destroyMethod = "close")
    S3Client crossAccountS3Client(
            @Qualifier("crossAccountCredentials")
            StsAssumeRoleCredentialsProvider credentials,
            @Value("${app.aws.cross-account.s3-region}") String region) {

        return S3Client.builder()
                .region(Region.of(region))
                .credentialsProvider(credentials)
                .build();
    }
}
~~~

**Step-by-step explanation:**

1. `sourceStsClient` uses the default credentials chain when no other provider is configured: on ECS it prioritizes task credentials unless overridden by another credential source.
2. `AssumeRoleRequest` specifies target role ARN B, session name, and requested duration.
3. `StsAssumeRoleCredentialsProvider` is responsible for retrieving and refreshing credentials for **role B**.
4. `crossAccountS3Client` uses provider B to access bucket B in the appropriate region.
5. Spring manages the beans and invokes `close()` on context shutdown.

**Auto-configuration note:** if the project also uses the AWSpring S3 starter, defining your own `S3Client` bean can affect auto-configuration/back-off behavior for the default client. Do not assume `S3Template` or other S3 beans will automatically use the cross-account role. When an application needs **two clients for two accounts**, use explicit names/qualifiers, verify auto-configuration conditions for your exact AWSpring version, and wire each adapter to the right client.

In systems with many target accounts, prefer a bounded client factory/cache keyed by account + role + region and close unused clients; never instantiate a fresh STS client/S3 client per HTTP request.

### 7.4. Using the Client Wired with Role B Credentials

Example receipt-reading adapter:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import java.nio.file.Path;

@Service
public class PartnerReceiptReader {
    private final S3Client partnerS3;
    private final String targetBucket;

    public PartnerReceiptReader(
            @Qualifier("crossAccountS3Client") S3Client partnerS3,
            @Value("${app.aws.cross-account.bucket}") String targetBucket) {
        this.partnerS3 = partnerS3;
        this.targetBucket = targetBucket;
    }

    public void download(String key, Path destination) {
        if (!key.startsWith("receipts/dev/")) {
            throw new IllegalArgumentException("Key is outside the scope of this lab");
        }

        partnerS3.getObject(
                GetObjectRequest.builder()
                        .bucket(targetBucket)
                        .key(key)
                        .build(),
                destination);
    }
}
~~~

This example simplifies path handling. Real applications must validate keys against business rules, prevent unintended file overwrites, enforce size limits, timeouts, I/O error handling, metadata checks, and security rules. Checking prefixes in Java **does not replace** IAM policies: role B must also be restricted to the prefix.

**Important:** Provider B must be attached only to clients needing access to B. Clients accessing resources in A should keep using source role A. Never mutate a global credential provider ambiguously so all services switch accounts implicitly.

## 8. Simpler Approach for Local Development: AWS CLI Role Profile

To test cross-account access before writing Java code, you can configure a **source profile** authenticated via IAM Identity Center, then create a target profile specifying `role_arn` and `source_profile`. The AWS CLI/SDK handles the assume-role step based on the profile configuration.

Example `~/.aws/config`:

~~~ini
[sso-session team-sso]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile dev-source]
sso_session = team-sso
sso_account_id = 111122223333
sso_role_name = DeveloperSandbox
region = ap-southeast-1

[profile dev-target-reader]
role_arn = arn:aws:iam::444455556666:role/partner-receipt-reader-dev
source_profile = dev-source
role_session_name = local-receipt-reader
region = ap-southeast-1
~~~

These values are illustrative only. Identity Center must grant the corresponding permission set, the source principal must hold permission to assume role B, and B's trust policy must accept the role/session actually used by the source profile.

Sign in to the source profile and verify:

~~~bash
aws sso login --profile dev-source
aws sts get-caller-identity --profile dev-source
aws sts get-caller-identity --profile dev-target-reader
~~~

Expected result: the second command returns Account A; the third, **if assuming the role succeeds**, returns Account B and an `assumed-role/...` ARN. Never paste credentials, tokens, or sensitive output into public channels.

When running the application locally with the default provider chain, you can set:

~~~bash
export AWS_PROFILE=dev-target-reader
export AWS_REGION=ap-southeast-1
~~~

If the application uses `dev-target-reader`, the SDK can perform assume-role via the profile as long as the classpath contains the matching SSO/STS SDK modules. An assume-role profile requires `sts`; an Identity Center source profile may additionally require `sso` and `ssooidc` depending on SDK version.

**Pick one clear path:** if code already uses `StsAssumeRoleCredentialsProvider` to assume role B, the source profile used for the STS client should be **`dev-source`**. Setting `AWS_PROFILE=dev-target-reader` while code also assumes role B again can accidentally create **role chaining**, yield an unexpected principal, or complicate debugging. For this exercise, choose **either a self-assuming profile** *or* **Java code assuming role B from the source profile**, then verify the principal.

## 9. STS Sessions: Duration, Chaining, and Refresh

### 9.1. What Do Temporary Credentials Contain?

STS `AssumeRole` returns `Credentials` containing:

- Access key ID.
- Secret access key.
- Session token.
- Expiration time.

These credentials are **security-sensitive material**, not public metadata. Never log them, write them to unprotected files, include them in HTTP responses, or embed them in CI artifacts.

`GetCallerIdentity` called with credentials B returns the role session ARN, suitable for verifying the target identity. However, this API does not prove all resource permissions in B are granted.

### 9.2. DurationSeconds and Maximum Session Duration

Role B has a configured **maximum session duration**. `DurationSeconds` in the request must comply with STS/role limits. With **role chaining** (using credentials from one assumed role to assume another role), each new assume-role session is capped at a **1-hour maximum** under AWS STS rules. Because EC2/ECS/EKS workloads already run on role credentials, do not assume multi-hour session requests will be valid in every environment.

The code snippet uses `durationSeconds(3600)` for illustration; shorter durations may be chosen depending on policy and refresh cadence. Let the SDK provider refresh credentials as expiration approaches instead of caching a single STS call yourself.

### 9.3. Session Policies Only Restrict, Never Expand Permissions

`AssumeRole` can accept a **session policy** (inline/managed) to narrow effective permissions below role B's permissions policy. Session permissions equal the intersection of the role's permissions and the session policy, further subject to applicable AWS policies. A session policy **cannot add permissions** that role B lacks.

For instance, role B allows reading `receipts/*`, yet one session should only read `receipts/dev/*`: a session policy can add that restriction alongside environment-specific roles. Never use session policies as a substitute for properly scoped trust and role permissions.

### 9.4. SourceIdentity and Session Tags

In systems where multiple services make cross-account calls, `RoleSessionName`, **source identity**, or **session tags** can aid traceability and ABAC under organizational policy. Passing session tags may require `sts:TagSession` in role trust; using source identity may require `sts:SetSourceIdentity` and corresponding trust/permissions.

These values help auditing and policy conditions, yet cannot serve as sole security proof if callers can supply arbitrary strings. Bind trust conditions, source identities, and tag generation to trusted sources.

## 10. ExternalId, MFA, and the Confused Deputy Problem

### 10.1. When Is ExternalId Needed?

In **third-party access** models, multiple customers allow the same vendor to assume roles in their accounts. This introduces the **confused deputy** risk: another party exploits the vendor's permissions to act on an account they do not own.

The `sts:ExternalId` condition in a trust policy lets the vendor prove requests originate from the intended customer relationship.

Example of trust policy B hardened with a condition:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/receipt-api-task-dev"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "partner-contract-example-2026"
        }
      }
    }
  ]
}
~~~

Then `AssumeRoleRequest` must supply the matching external ID:

~~~java
AssumeRoleRequest request = AssumeRoleRequest.builder()
        .roleArn(targetRoleArn)
        .roleSessionName("receipt-reader-dev")
        .externalId("partner-contract-example-2026")
        .build();
~~~

**ExternalId is not a password or a replacement for a trust policy.** It must be designed around the exact vendor/customer relationship and provisioning process; do not confuse it with an access key, OAuth token, or session token. Between two internal accounts with tightly scoped trust, ExternalId is not automatically mandatory for every flow.

### 10.2. MFA for Sensitive Operations

Some trust policies enforce an MFA condition. That fits interactive human actions in certain cases, whereas automated workloads on ECS/EKS/EC2 cannot enter an MFA code every time a provider refreshes credentials.

When strong controls are required, separate **interactive operational roles requiring MFA** from **automated application roles** with tightly scoped trust and permissions, combined with deployment controls, auditing, and approvals. Never build pipelines requiring production workloads to wait for manual MFA input.

## 11. Accessing S3, SQS, Secrets Manager, and KMS in Account B

### 11.1. S3: Object ARNs Differ from Bucket ARNs

For `s3:GetObject`, the ARN typically looks like:

~~~text
arn:aws:s3:::example-partner-receipts/receipts/dev/*
~~~

If `ListObjectsV2` is needed, `s3:ListBucket` must attach to the bucket ARN:

~~~text
arn:aws:s3:::example-partner-receipts
~~~

Prefixes can be restricted with appropriate conditions when designing `ListBucket`. Never grant `s3:*` across all buckets for a service that only reads receipts. When object ownership or bucket policies impose constraints, verify actual runtime behavior as well.

### 11.2. SQS: Region, Queue ARN, and Queue Policy

For a queue in B, `sqs:SendMessage` can be granted to target role B on the exact queue ARN, for example:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:partner-events-dev"
    }
  ]
}
~~~

The SQS client must target the right **region** and queue URL/name expected by the API. If an application chooses to grant role A direct access instead of AssumeRole, both the **SQS queue resource policy** in B and A's identity policy must be evaluated. Message delivery rules, DLQs, retries, visibility timeouts, and idempotency do not change simply because requests are signed with cross-account credentials.

### 11.3. Secrets Manager: Secret Scope and Version

If target role B reads a secret, grant `secretsmanager:GetSecretValue` strictly on the required secret ARN. When using a customer-managed KMS key, `kms:Decrypt` and a matching key policy may also be required.

Do not confuse **secrets stored in Secrets Manager** with **AWS role credentials**. An application does not need to fetch an "AWS access key" secret from Secrets Manager just to call S3/SQS when an STS role session can be used. Secrets Manager is intended for API tokens, database passwords, or actual application secrets that must be persisted.

### 11.4. Cross-Account KMS: Two Sides of Authorization

When a resource in B is encrypted with a customer-managed KMS key, IAM permissions on role B may **not be enough** if the key policy/grants do not permit key usage. Check:

- Both the key policy and IAM permissions applying to the request's actual principal.
- Actions `kms:Decrypt`, `kms:Encrypt`, `kms:GenerateDataKey` depending on the operation.
- Region of the KMS key and the service using it.
- Encryption context/conditions or service-limiting policies if configured.

A request may assume the role successfully and hold `s3:GetObject`, yet be denied `kms:Decrypt` when reading an object. Diagnose errors across both S3 and KMS rather than widening all S3 permissions.

## 12. Diagnosing Cross-Account Issues Stage by Stage

### 12.1. Unable to Assume Role

Errors often involve `AccessDenied` on `sts:AssumeRole` or trust policy constraints. Check:

1. Actual **source principal** via STS `GetCallerIdentity` using source credentials.
2. Does source role A's identity policy allow `sts:AssumeRole` on the **exact ARN** of role B?
3. Does role B trust the exact source principal/role ARN, service/federated principal, and conditions?
4. Does the request include `ExternalId`, MFA, or session tags/source identity when trust requires them?
5. Is an SCP, permissions boundary, session policy, or explicit deny blocking it?
6. Have source credentials expired or been overridden unintentionally by system properties/environment credentials?

If STS does not issue temporary credentials, adding `s3:GetObject` to role B **will not fix the AssumeRole error**. Fix the role-assumption stage first.

### 12.2. Assume Succeeds, Yet Resource Access in B Is Denied

Check:

- Is the S3/SQS client actually using **role B's credentials**, or is it still calling as source role A?
- Does role B hold permissions for the exact **action and resource ARN**?
- Is a bucket/queue/secret policy, KMS key policy, VPC endpoint policy, or SCP denying the request?
- Is the resource in the right region/account with the exact name/ARN?
- Does the actual operation invoke auxiliary APIs such as `ListBucket`, `GetQueueUrl`, or `Decrypt` that lack permissions?

One verification method is building an `StsClient` with **the exact target credentials provider** and calling `GetCallerIdentity`; if it returns an assumed-role ARN in B, the client is confirmed to carry the target identity.

### 12.3. Wrong Role Chaining, Expired Tokens, or Session Duration

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `ExpiredToken` after running for some time | STS credentials hard-cached; provider not refreshing | Use `StsAssumeRoleCredentialsProvider` or a refreshing provider |
| AssumeRole requests too long a duration | Exceeds role max session or 1-hour cap during role chaining | Lower duration and inspect credential source |
| STS returns right account, unexpected session ARN | Assuming multiple times across profile and Java code | Inspect profile source, role ARN, and identity at each hop |
| 403 S3/KMS | Role B lacks permissions or policy/resource condition blocks | Check action, ARN, key policy, endpoint |
| Resource "not found" | Wrong region/queue URL/key/bucket; missing permissions can also affect errors | Verify location and permissions |
| Wrong account despite right `AWS_PROFILE` | Higher-priority credential source or custom client provider | Inspect provider chain and principal from actual client |

### 12.4. Error Identification Map

~~~mermaid
flowchart TD
    A["Cross-account application failure"] --> B{"Are source credentials valid?"}
    B -->|No| C["Fix profile / workload role / provider chain"]
    B -->|Yes| D{"Did STS AssumeRole succeed?"}
    D -->|No| E["Check sts:AssumeRole in A + trust in B + conditions"]
    D -->|Yes| F{"Is the service client using role session B?"}
    F -->|No| G["Fix client/provider/qualifier"]
    F -->|Yes| H{"Right account, region, resource?"}
    H -->|No| I["Fix target ARN / region / endpoint configuration"]
    H -->|Yes| J["Check permissions B, resource policy, KMS, SCP"]
~~~

## 13. Safe Integration Testing

### 13.1. Unit Tests Without Real STS Calls

Place a business interface at the application layer:

~~~java
public interface ReceiptStorage {
    byte[] loadReceipt(String receiptKey);
}
~~~

The service depends only on `ReceiptStorage`, while the AWS adapter uses the cross-account `S3Client`. Unit tests use fake/mock adapters to verify error handling, key validation, and business retries. Never call real STS credentials just to test an `if` branch or data mapping.

### 13.2. Integration Tests with LocalStack: Limitations to Understand

You can use LocalStack or an emulator to verify beans, SDK clients, request serialization, endpoint overrides, and basic S3/SQS operations. Explicitly set test-only endpoints, regions, and fake credentials so tests never touch production accounts accidentally.

However, emulators **do not fully verify** IAM role trust, real STS AssumeRole, SCPs, resource policies, cross-account KMS, or all session expiration scenarios. If AssumeRole must be tested end-to-end, dedicated sandbox AWS accounts and real permissions are required.

### 13.3. Smoke Test Across Two Test Accounts

A reliable workflow for flow A → B:

1. Create dedicated test source role A and target role B with constrained trust and permissions.
2. Provision a test bucket and dummy object in B; use a specific key and region.
3. From **Account A's actual workload environment**, verify the source principal via STS.
4. Call `AssumeRole` on B using source credentials; verify the assumed-role principal using the same target credentials provider.
5. Call `GetObject` on the allowed prefix and verify data; test a key outside the prefix and expect denial when the IAM policy is designed that way.
6. Test an invalid ExternalId or untrusted source principal (if used); verify assumption fails.
7. Test KMS-dependent operations on a test object if encryption is enabled; document key policy conditions.
8. Clean up test data via a dedicated cleanup process and role, without granting broad destructive permissions to the runtime role.

This smoke test validates trust, permissions, regions, and the real execution path. It does not validate high-load resilience, every edge case, or multi-day rotation behavior.

### 13.4. Monitoring via Logs and CloudTrail

Log event name, target role ARN (when approved for display), service operation, region, correlation ID, and error type. **Never log temporary access keys, secret keys, or session tokens.**

CloudTrail can help correlate `AssumeRole` requests with subsequent service calls, along with role session and account details. Note that **S3 object-level data events** appear only when configured in CloudTrail; do not assume every `GetObject` generates a data event log by default. Timing, trail settings, and log locations may differ between A and B.

## 14. Security and Operations in Spring Boot Applications

### 14.1. Least Privilege in Both Accounts

- Role A may only assume the exact target role ARNs in B it needs; avoid `sts:AssumeRole` on `Resource: "*"` wherever possible.
- Role B holds permissions only on the exact resources/prefixes/queues/secrets in B the application requires.
- Trust policy B locks to the exact principal A; enforce `ExternalId` in third-party relationships where appropriate.
- Separate dev/staging/prod roles, account IDs, resource ARNs, and KMS keys; never use production roles for local testing.
- If an app accesses multiple partner accounts cross-account, consider separate roles per relationship and audit by role session.

### 14.2. Reproducibility and Configuration Management

Externalize role ARNs, regions, and bucket/queue/secret IDs per environment. Avoid hard-coding local profile names in shared code. With AWSpring, check how auto-configured beans and custom SDK clients interact, especially when an application accesses both Account A and Account B.

Never construct a new `StsClient` and `S3Client` per HTTP request. Use managed beans/factories with proper lifecycle, connection reuse, retries/timeouts, and ensure clients and credential providers close on shutdown.

### 14.3. Retries and Side Effects

STS AssumeRole prepares credentials, while actual S3/SQS operations still face timeouts and retries. For SQS or resource-creating operations, design business idempotency to avoid duplicate side effects during ambiguous network failures. AssumeRole **does not create distributed transactions** between Account A and Account B.

For high-scale operations, evaluate STS quotas/rate limits, provider caching/refresh behavior, session durations, and multi-role usage. Design bounded client factories to prevent unnecessary `AssumeRole` bursts.

## 15. Hands-On Scenario

**Problem statement:** A Spring Boot application `invoice-api` runs on ECS in **Account A**, needs to read receipts from S3 in **Account B**, and sends an event to SQS in B. Code uses AWS SDK v2 and Spring Cloud AWS for Spring integration. In dev, developers sign in via AWS CLI + IAM Identity Center; staging/prod run with dedicated task roles.

### Task A — Policy Design

1. Diagram the flow: ECS task role A → STS AssumeRole B → temporary credentials B → S3/SQS B.
2. Write identity policy A for `sts:AssumeRole` targeting the exact role ARN in B.
3. Write trust policy B restricted to the exact role in A.
4. Write permissions policy B: `s3:GetObject` on the exact prefix and `sqs:SendMessage` on the exact queue ARN. Determine whether `kms:Decrypt`/`kms:GenerateDataKey` is also required.
5. Explain the impact of SCPs/resource policies and why STS success does not guarantee S3 success.

### Task B — Spring Boot Configuration

1. Declare compatible BOM/dependencies, adding `sts` and the `s3`/`sqs` SDK modules actually used.
2. Build `StsAssumeRoleCredentialsProvider` using the source role from the default credential chain, setting role ARN B and a session name.
3. Create a client qualified as `crossAccountS3Client`, ensuring Account A adapters do not accidentally use credentials B.
4. Externalize role ARN, region, and bucket/queue into environment configuration; keep access keys and session tokens out of YAML.
5. Design bean lifecycle management, credential refresh, and `ExpiredToken` error handling.

### Task C — Analyze Three Failures

| Error | Questions to answer |
| --- | --- |
| `AccessDenied` calling `AssumeRole` | Does source A have `sts:AssumeRole`? Does trust B permit the right source role? Do ExternalId/session policy conditions match? |
| `AssumeRole` succeeds, `GetObject` fails | Is the client using role B's session? Right object ARN/prefix? Are bucket policy or KMS blocking? |
| Works locally, fails on production ECS | Is the STS client using a local IAM Identity Center profile or the ECS task role? Are env credentials overriding? Are production region/role ARN right? |

### Task D — Evaluate Two Architectures

Compare:

- Bucket policy B directly granting access to IAM role A.
- IAM role B assumed by A via STS.

Discuss trade-offs around trust management, permission scoping, role session auditing, service support, session refresh, and testing. Identify when a service only needs a resource policy without custom Java `AssumeRole` code.

### Self-Assessment Criteria

A complete solution includes **policy in A, trust in B, and permissions on role B**, accurate region/role/session configuration, a refreshing SDK provider, zero leakage of temporary credentials, and a smoke test plan across two isolated sandbox accounts. You should be able to explain why `iam:PassRole` does not replace `sts:AssumeRole` and why `GetCallerIdentity` does not prove read access to all resources.

## 16. Connections to Azure and Google Cloud

AWS's cross-account model sits alongside cross-organization/cross-project authorization models on other clouds, though **APIs and trust mechanisms are not identical**.

| Need | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Workload identity | IAM role, temporary STS credentials | Managed Identity / Microsoft Entra workload identity | Service account / Workload Identity Federation |
| Cross-boundary access | Cross-account IAM role trust + `AssumeRole` or resource policy | RBAC/resource access across subscriptions/tenants via appropriate identity mechanisms | IAM bindings on project/resource for appropriate principals; service-account impersonation when designed |
| SDK client authentication | AWS SDK `DefaultCredentialsProvider` / STS providers | Corresponding credential providers in Azure SDK | Application Default Credentials / credential impersonation as appropriate |
| What to check | Source action, target trust, permissions, SCP/resource/KMS | Tenant, identity, assignment, and resource scope | Project, principal/service-account policy, and resource scope |

The similarity lies in the principle of **explicitly authorizing identity and scope**, not in role ARN syntax, token refresh behavior, or credential chain ordering. For multi-cloud Spring Boot systems, keep business code dependent on adapters; place `AssumeRole`, Azure RBAC, or GCP service-account impersonation logic in the respective integration layer.

## 17. Conclusion

**STS `AssumeRole`** lets a trusted principal obtain **temporary credentials for a target role**, enabling controlled access to resources in another AWS account. In a standard cross-account flow, you must align **source role A's `sts:AssumeRole`**, **target role B's trust policy**, and **B's permissions/resource/KMS policies**; each serves a distinct purpose.

With Spring Boot, AWSpring integrates clients into Spring, while AWS SDK for Java v2 provides `StsClient` and `StsAssumeRoleCredentialsProvider` to acquire and refresh role credentials. Success at the STS step only proves the role can be assumed; reading/writing S3, SQS, or secrets still depends on actions, ARNs, regions, endpoints, and related policies. Clarifying each stage and testing with the actual workload identity provides a safe foundation for multi-account AWS service integration.
