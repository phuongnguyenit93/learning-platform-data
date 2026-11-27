# DefaultCredentialsProvider and the Region Lookup Chain

## 1. Why Does a Spring Boot Application Need to Understand Credentials and Region?

A Spring Boot application can be written very concisely to store files in Amazon S3 or receive messages from Amazon SQS thanks to Spring Cloud AWS by **AWSpring**. However, before sending an AWS request, the client must answer two independent questions:

1. **With which identity is AWS being called?** The SDK needs appropriate credentials to sign and authenticate the request. The resulting identity is ultimately constrained by IAM roles, policies, and resources.
2. **Which AWS region is being called?** The SDK needs a `Region` to construct the regional endpoint and sign the request in the right service context.

This is foundational knowledge in the **AWS Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud; identity and permission management, storage, messaging, data, secrets, and integration testing. In this lesson, the focus is on the default mechanisms of **AWS SDK for Java 2.x**, the foundation typically used by Spring Cloud AWS 3.x.

**Learning objectives**:

- Accurately describe the order in which `DefaultCredentialsProvider` tries credential sources.
- Distinguish credentials, IAM permissions, AWS accounts, profiles, roles, and regions.
- Explain the lookup order of `DefaultAwsRegionProviderChain` and when to specify a region explicitly.
- Configure Spring Boot/AWSpring on laptops, CI, ECS, EKS, and EC2 without putting long-lived access keys into source code.
- Accurately diagnose error categories: missing credentials, wrong region/endpoint, `AccessDenied`, expired tokens, and missing resources.
- Write reproducible tests without accidentally using production credentials.

> **Version scope:** Class names, environment variables, and lookup order describe **AWS SDK for Java v2**. The AWSpring ecosystem, Spring Boot, and AWS environments change across versions. Before applying to production, consult the documentation for the exact SDK/AWSpring version in use and inspect which bean configurations may override the defaults.

## 2. Two Separate Lookup Chains

`DefaultCredentialsProvider` resolves **credentials**. `DefaultAwsRegionProviderChain` resolves the **region**. They are neither synonymous nor interchangeable.

~~~mermaid
flowchart LR
    APP["Spring Boot service"] --> AWS["AWSpring auto-configuration / AWS SDK v2 client"]
    AWS --> C["Credentials provider"]
    AWS --> R["Region provider"]
    C --> ID["Access key ID + secret + optional session token"]
    R --> REG["Region, e.g. ap-southeast-1"]
    ID --> SIGN["Sign request"]
    REG --> SIGN
    SIGN --> API["AWS service endpoint"]
    API --> IAM["AWS authenticates and evaluates IAM/resource policy"]
~~~

Conceptually, an SDK client requires configuration like:

~~~java
S3Client client = S3Client.builder()
        .credentialsProvider(credentialsProvider)
        .region(region)
        .build();
~~~

When `credentialsProvider(...)` or `region(...)` is omitted, many SDK v2 clients use the corresponding default provider chain. **Valid credentials do not imply a valid region**, and knowing the region does not grant IAM permissions.

| Concept | Example | Meaning |
| --- | --- | --- |
| Credential | Access key, secret key, session token | Material for the SDK to authenticate/sign requests |
| Principal | IAM role for an ECS task | The AWS identity evaluated for permissions |
| Policy | Allow `s3:PutObject` on an ARN | Principal permissions and resource-level policies |
| Region | `ap-southeast-1` | Regional endpoint/service location being accessed |
| Profile | `dev-sandbox` | Name of a local configuration set that may specify how to obtain credentials and a region |
| Endpoint | Service URL or LocalStack emulator URL | Network destination of the client; related to region but not the region itself |

**Example:** Production role credentials are present, but the region is set to `us-east-1` while the SQS queue only exists in `ap-southeast-1`. The SDK can still retrieve credentials and sign the request; the request then fails due to an incompatible endpoint/queue/region. This is not a reason to create additional access keys.

## 3. What Is DefaultCredentialsProvider?

In AWS SDK for Java v2, `software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider` is a built-in provider representing **a chain of credential sources**. It tries sources sequentially in priority order; the first source that returns valid credentials during resolution is used.

Calling:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;

var provider = DefaultCredentialsProvider.create();
~~~

does not create an IAM user, does not log in to AWS, and does not grant permissions to the application. The provider only knows **how to obtain credentials at runtime**. The credentials may be a static key pair in a development environment or temporary credentials from a role/workload identity when running in production.

### 3.1. Credential Lookup Order in SDK v2

With the standard `DefaultCredentialsProvider`, the order is described as follows:

| Priority | Child provider | Primary data source | Common use cases |
| --- | --- | --- | --- |
| 1 | `SystemPropertyCredentialsProvider` | Java system properties `aws.accessKeyId`, `aws.secretAccessKey`; token if present | Java apps launched with `-D...` |
| 2 | `EnvironmentVariableCredentialsProvider` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`; `AWS_SESSION_TOKEN` for temporary credentials | Shells, containers, CI |
| 3 | `WebIdentityTokenFileCredentialsProvider` | `AWS_WEB_IDENTITY_TOKEN_FILE` + `AWS_ROLE_ARN`, or corresponding Java system properties | EKS IRSA, OIDC/web identity |
| 4 | `ProfileCredentialsProvider` | Profile in AWS shared config/credentials files | Developer laptops, AWS CLI profiles, role/SSO via profile |
| 5 | `ContainerCredentialsProvider` | Credential endpoint exposed by container environment, usually via `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` / `AWS_CONTAINER_CREDENTIALS_FULL_URI` | ECS task roles and some container workload identity mechanisms |
| 6 | `InstanceProfileCredentialsProvider` | IAM role via the EC2 Instance Metadata Service (IMDS) | EC2 instance profiles |

Sources are checked **in order**, not merged together. If a higher-priority source supplies credentials, lower-priority sources are normally not consulted for that resolution. Caching of the resolved provider can also cause the application to keep using the selected source for subsequent resolutions.

~~~mermaid
flowchart TD
    A["DefaultCredentialsProvider"] --> B{"Java system properties have credentials?"}
    B -->|Yes| Z["Use credentials"]
    B -->|No| C{"AWS_* credentials in environment?"}
    C -->|Yes| Z
    C -->|No| D{"Web identity token + role ARN?"}
    D -->|Yes| Z
    D -->|No| E{"Shared AWS profile has credentials?"}
    E -->|Yes| Z
    E -->|No| F{"Container credential endpoint?"}
    F -->|Yes| Z
    F -->|No| G{"EC2 instance profile via IMDS?"}
    G -->|Yes| Z
    G -->|No| H["No credentials found -> resolve failure"]
~~~

**Dependency caveat:** Certain provider types—such as web identity, assume-role, and SSO login via profiles—require the corresponding STS/SSO support SDK modules on the classpath. If a required module is missing or a source is misconfigured, the chain cannot "auto-heal" the error. The actual error message typically lists the providers attempted and their respective causes.

### 3.2. Java System Properties vs. Environment Variables

These two mechanisms are **distinct** priority sources:

~~~text
# Java system property; syntax illustration, DO NOT insert real secrets into commands:
-Daws.accessKeyId=EXAMPLE -Daws.secretAccessKey=EXAMPLE

# Environment variables; names recognized by AWS SDK for Java v2:
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
~~~

Never put real keys into command arguments, logs, CI output, or repositories; they can leak through shell history or process metadata. The example is purely for recognizing names and precedence. For production on AWS, prefer IAM roles and temporary credentials.

If a container simultaneously has `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` **and** an ECS task role, the SDK can pick up credentials from the environment before reaching the container credential endpoint. This is a common cause of an application "having the right role attached yet still calling as another account."

### 3.3. Web Identity in EKS and OIDC Workloads

Web identity allows a workload to prove its identity via a token from an external system and then use AWS STS to obtain temporary AWS credentials. In EKS, **IAM Roles for Service Accounts (IRSA)** typically provides:

~~~text
AWS_ROLE_ARN
AWS_WEB_IDENTITY_TOKEN_FILE
~~~

The SDK/STS reads the token, invokes the appropriate assume-role flow, and receives temporary credentials. The token file must exist and the IAM role's trust policy must allow the exact identity/OIDC provider.

**Do not confuse IRSA with EKS Pod Identity.** IRSA typically goes through the web identity provider; EKS Pod Identity uses a corresponding agent/container credential endpoint mechanism. Both aim to supply temporary credentials without embedding static secrets in the application, but their provider paths differ.

### 3.4. An AWS Profile Supports Multiple Credential Types, Not Only Access Keys

`ProfileCredentialsProvider` reads profiles from shared config and credentials files (typically located at `~/.aws/config` and `~/.aws/credentials`). A profile can describe:

- Static credentials or credentials with a session token in development environments.
- SSO/IAM Identity Center, with tokens prepared through an approved login workflow.
- Assume role based on `source_profile` or a credential source.
- A `credential_process` outputting credentials in a format supported by the SDK.

Example of a `~/.aws/config` file containing only region settings and a profile name, **with no secrets**:

~~~ini
[profile dev-sandbox]
region = ap-southeast-1
output = json
~~~

Before running the application locally, you can select a profile via an environment variable:

~~~bash
export AWS_PROFILE=dev-sandbox
~~~

On Windows PowerShell, you can use:

~~~powershell
$env:AWS_PROFILE = "dev-sandbox"
~~~

Selecting a profile does not automatically sign in, create credentials, or add IAM permissions. If the profile relies on SSO, you must sign in via your organization's allowed workflow. If the profile only defines a region without a valid credential source, the SDK will still fail to locate credentials.

**Key takeaway:** the profile name affects both how the SDK selects credential configuration *and* which profile is consulted during region lookup, yet the two lookup chains remain independent; either one can be overridden by a higher-priority source.

### 3.5. How Are Temporary Credentials Refreshed?

Temporary AWS credentials consist of an access key ID, a secret access key, and a **session token**, with an expiration time. Role-based providers (web identity, ECS tasks, EC2 instance profiles, profile assume-role, etc.) are designed to retrieve and refresh credentials according to the source's capabilities.

Do not copy the result of `resolveCredentials()` into a `StaticCredentialsProvider` to reuse all day; doing so strips away the refresh mechanism and triggers `ExpiredToken`. Similarly, do not cache the access key/secret/token strings in global variables and attach tokens manually to requests.

If your organization uses STS assume-role programmatically, design the lifecycle/refresh of `StsAssumeRoleCredentialsProvider` instead of calling assume-role once at startup and holding onto the result forever.

## 4. Region Lookup Chain in AWS SDK for Java v2

Regional AWS SDK clients need to know the region when building and signing requests. With SDK v2 defaults, `DefaultAwsRegionProviderChain` follows this basic lookup order:

| Priority | Region source | Example | Notes |
| --- | --- | --- | --- |
| Before chain | `.region(Region...)` set directly on the client builder | `Region.AP_SOUTHEAST_1` | Explicit configuration takes precedence over the client's region chain |
| 1 | Java system property `aws.region` | `-Daws.region=ap-southeast-1` | Takes precedence over environment variables |
| 2 | Environment variable `AWS_REGION` | `AWS_REGION=ap-southeast-1` | Suitable for containers/CI |
| 3 | Region in shared AWS profile | `region = ap-southeast-1` | Based on selected profile; usually in `~/.aws/config` |
| 4 | EC2 instance metadata (IMDS) | Region of the running EC2 instance | Only available when metadata is reachable and permitted |

If no valid source is found, the SDK can report that it cannot determine the region—for instance raising `SdkClientException` when building the client or executing a request. **There is no mechanism to "infer any region" from an access key alone**.

Some AWS tools and languages support `AWS_DEFAULT_REGION`. With **AWS SDK for Java v2**, do not rely solely on that name to configure the region: use `AWS_REGION`, `aws.region`, a profile, or an explicit builder call as documented by the SDK. This is an easy pitfall when moving from the AWS CLI or other language SDKs.

### 4.1. Explicit Region and Endpoint Override Mean Different Things

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

try (S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {
    // S3 client uses default credential chain if no specific override is provided.
}
~~~

`.region(...)` selects the region the client uses to determine the endpoint and sign requests. In local testing, `.endpointOverride(...)` lets you target a different URL, but **a region is still required for signing** and request processing. An endpoint override is not a complete replacement for a region.

### 4.2. Region Errors Are Not Credential Errors

Suppose a developer sets:

~~~text
AWS_PROFILE=dev-sandbox
AWS_REGION=us-east-1
~~~

while the profile in `~/.aws/config` states `region = ap-southeast-1`. Because the region from the environment variable has higher precedence than the profile, the default client may use `us-east-1`. If the SQS queue only exists in Singapore, the request can query the wrong region or fail.

Conversely, `AWS_REGION` may be right while credentials come from an old environment key whose permissions were revoked. Fixing the region will not resolve `AccessDenied`. Diagnose these two paths separately.

## 5. How Do AWSpring and Spring Boot Interact with the Provider Chain?

Spring Cloud AWS integrates the SDK via beans/auto-configuration and Spring Boot properties. In the common AWSpring 3.x line, you can explicitly configure the region for beans managed by AWSpring:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  storage:
    bucket: ${APP_S3_BUCKET}
  messaging:
    queue: ${APP_SQS_QUEUE}
~~~

The example above expects the application to have environment variables `AWS_REGION`, `APP_S3_BUCKET`, and `APP_SQS_QUEUE`; they are **not created automatically**. The `spring.cloud.aws.region.static` path belongs to AWSpring configuration, not the SDK's Java system property `aws.region`; AWSpring can use it to configure its SDK beans.

When Spring Boot configuration specifies a region or when the application declares its own client bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class AwsClientConfiguration {
    @Bean
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

the bean above uses the region set directly on the builder, even if an external `AWS_REGION` differs. Default credentials are still used because no custom provider was configured.

**Important boundary:** AWSpring provides mechanisms to configure credential profiles, static keys, regions, and custom beans depending on the version. When an `AwsCredentialsProvider` or client bean is configured explicitly, SDK defaults may be replaced. Therefore, if the actual credentials or region differ from expectations, check **all** of Spring properties, custom configuration beans, Java system properties, and runtime environment variables.

Do not add properties containing static access keys/secret keys into `application.yml` or commit `application-prod.yml` files containing secrets. On AWS, prefer letting workload identity/roles supply temporary credentials and letting the application use the default provider chain.

### 5.1. SDK v2 Code Using Full Defaults

If credentials and region are already configured via environment or profile, the client can be as simple as:

~~~java
import software.amazon.awssdk.services.s3.S3Client;

try (S3Client s3 = S3Client.create()) {
    // When calling S3, the SDK uses default credentials and region.
}
~~~

`S3Client.create()` is convenient for pure SDK applications; in a Spring Boot application using AWSpring, prefer injecting the Spring-managed `S3Client` bean if provided by the starter/configuration. This preserves consistent configuration, lifecycle, tracing, and customization.

Service example:

~~~java
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;

@Service
public class FileInfoService {
    private final S3Client s3;

    public FileInfoService(S3Client s3) {
        this.s3 = s3;
    }

    public long fileSize(String bucket, String key) {
        return s3.headObject(req -> req.bucket(bucket).key(key))
                 .contentLength();
    }
}
~~~

The application requires a starter/module that creates the `S3Client` bean or an intentionally configured bean, along with appropriate IAM permissions to read object metadata.

### 5.2. When Should You Pin the Region in Configuration?

- **Configure explicitly** if the application strictly serves buckets/queues/tables in one clear region, deploys across multiple environments, or does not run on EC2.
- **You can use the chain** if deployment infrastructure standardizes `AWS_REGION`/profiles and the application has startup configuration validation.
- **Do not hard-code a single region for all resources** in multi-region applications: build clients per region/resource source and explicitly control endpoints.

In a multi-region architecture, do not mutate `AWS_REGION` globally at runtime to switch clients. SDK clients are configured at build time; create clients with dedicated regions or use an appropriate factory, and manage their lifecycles.

## 6. Configuration by Runtime Environment

| Environment | Preferred credential source | How region is determined | Common mistakes |
| --- | --- | --- | --- |
| Developer machine | AWS profile, SSO/IAM Identity Center, profile assume-role | `AWS_REGION` or region in profile | Old environment keys overriding the profile |
| Local container | Mounted profile/SSO with proper permissions, or temporary credentials from dev tooling | Explicit `AWS_REGION` | Container lacks host config/profile files |
| ECS/Fargate | **Task role**, via container credential provider | Usually `AWS_REGION` from deployment environment | Confusing task execution role with application task role |
| EKS with IRSA | Web identity token + role ARN | `AWS_REGION` or application config | Missing trust policy / required STS module |
| EKS Pod Identity | Credential endpoint provided by agent | `AWS_REGION` or explicit config | Assuming the mechanism is identical to IRSA |
| EC2 | Instance profile via IMDS | `AWS_REGION`/profile or IMDS if available | IMDS disabled/blocked, wrong instance role permissions |
| CI outside AWS | OIDC federation/assume-role or temporary credentials via CI system | Job environment variables | Storing long-lived access keys in CI secrets |
| LocalStack tests | Fake static credentials **only in tests**, with endpoint override | Simulated region chosen explicitly | Letting test endpoint/credentials leak into production |

### 6.1. ECS Task Role vs. Task Execution Role

ECS uses the **task execution role** for platform responsibilities such as pulling images or sending configured logs; the **task role** is the principal your application code inside the container normally uses to call S3, SQS, or Secrets Manager. If `AccessDenied` occurs, check the role actually attached as the task role—do not look only at the execution role.

ECS typically exposes a path to obtain temporary credentials for containers via platform-managed endpoints and environment variables. SDK v2's `ContainerCredentialsProvider` fetches credentials from this endpoint when higher-priority sources do not supply credentials.

### 6.2. EKS and the Importance of Precedence

If a Pod has IRSA configured properly but the container image includes `AWS_ACCESS_KEY_ID`, the environment provider can take precedence over web identity. The Pod may send requests under a different IAM principal than expected.

Check these factors:

- Service account, role ARN, OIDC provider, and trust policy (for IRSA).
- Pod identity association/agent and the exposed credential endpoint (for Pod Identity).
- Whether environment variables or JVM system properties are overriding the provider chain.
- Required STS dependency when the mechanism uses STS; actual permissions on target S3/SQS/KMS resources.

Do not copy node credentials into Pods; doing so weakens IAM boundaries between workloads.

### 6.3. EC2, IMDS, and Network Conditions

IMDS provides instance profile metadata and temporary credentials according to EC2 policy and infrastructure. The SDK must be allowed to reach the metadata endpoint; if IMDS is disabled, blocked by network policies, or the instance lacks an appropriate role, `InstanceProfileCredentialsProvider` cannot retrieve credentials.

When running outside EC2, do not expect IMDS to be available. The SDK may try this source at the end of the chain and fail; the proper fix is configuring a valid credential source for the actual environment.

## 7. Safe Diagnosis of Credential and Region Errors

An effective approach is to first verify **how Spring/SDK constructs the client**, then inspect **credential source, region, IAM, and resource** in order.

### 7.1. Unable to Find Credentials

Common signs: `Unable to load credentials from any of the providers in the chain` or an `SdkClientException` listing the providers tried.

Investigation steps:

1. Verify the SDK is v2 and the expected provider is active; check for custom beans/`credentialsProvider(...)` overrides.
2. Check the environment type: local profile/SSO, ECS task role, EKS web identity/Pod Identity, EC2 instance profile.
3. Verify required environment variable names and Java system properties, **confirming only that variables exist**; never print secrets.
4. For SSO/assume-role: check login session, trust policy, and presence of supporting SDK modules.
5. For containers/EC2: check role configuration, credential endpoint/IMDS, and endpoint reachability from the workload.

**Never fix this by hard-coding credentials in source code.** Doing so temporarily masks configuration errors while creating security and secret-rotation risks.

### 7.2. Credentials Present, Permissions Missing

`AccessDeniedException`, HTTP 403, or equivalent access denied errors indicate the request reached AWS but is not permitted or violates policy constraints. Analyze:

- Who the actual AWS principal is.
- Whether the specific operation and resource ARN are permitted by the IAM identity policy.
- Whether the bucket/queue/secret resource policy imposes additional restrictions.
- If encrypted with a KMS customer-managed key, whether key policy/decrypt permissions are sufficient.
- Whether SCPs, permission boundaries, session policies, or VPC endpoint/IP/tag conditions are blocking the call.

The credential chain **does not fall back to a lower-priority source simply because the active principal received a 403**. That is an authorization error for the selected credentials, not a signal to keep trying other IAM roles.

### 7.3. Region Not Found or Wrong Region

Signs: `Unable to load region from any of the providers in the chain`, endpoint errors, resource not found, signature mismatch, or cross-region redirects depending on the service.

Check:

- Whether the client builder has `.region(...)` or an AWSpring-created bean sets the region.
- Which has precedence between `aws.region` (Java system property) and `AWS_REGION` (environment).
- Which profile is selected and whether it declares a region.
- Which region the bucket/queue/table actually lives in; which region the queue URL/ARN encodes.
- Whether a test-only endpoint override is active.

**A wrong region can produce error messages resembling "resource not found."** Do not rush to recreate buckets/queues before verifying the region.

### 7.4. Identifying the AWS Principal Without Printing Credentials

With appropriate STS access, use `GetCallerIdentity` to confirm the account and ARN used by the client:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;

public class IdentityCheck {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var identity = sts.getCallerIdentity();
            System.out.println("Account: " + identity.account());
            System.out.println("Caller ARN: " + identity.arn());
        }
    }
}
~~~

This example requires the `software.amazon.awssdk:sts` Maven/Gradle module; the region must match the STS endpoint used in your environment. Never log access keys, secret keys, or session tokens; account IDs and ARNs can also be internal details, so avoid writing them to public logs.

`GetCallerIdentity` returns the identity of the credentials used, **not directly which child provider in the chain was chosen**. Combine it with workload configuration and sanitized diagnostic logs to trace the credential source rather than treating STS as a provider-attribution tool.

## 8. Testing the Provider Chain Without Hitting Real Accounts by Mistake

Tests should not silently pick up `DefaultCredentialsProvider` from a developer laptop or CI runner and call real cloud resources. Tests need isolated configuration with explicit visibility into which resources will be accessed.

### 8.1. Unit Tests: Fake Adapters, No AWS Credentials Needed

For business logic, separate the AWS communication adapter from the service. Unit tests mock the adapter or client and verify data processing, mapping, and error handling; the SDK does not need to resolve credentials or regions. This approach is fast, deterministic, and incurs no cloud cost.

### 8.2. Integration Tests: Explicit Test Endpoints and Test Credentials

When using LocalStack or a similar service emulator, build test clients with the emulated endpoint and fake credentials. For example:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

public class LocalS3ClientFactory {
    public static S3Client create(URI localEndpoint) {
        return S3Client.builder()
                .endpointOverride(localEndpoint)
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

In real tests, `localEndpoint` must come from the LocalStack/container instance started by the test. The `test/test` pair is strictly for emulated environments and **must never be used as real AWS credentials**. Test clients should be closed when the test lifecycle ends.

Exercise two categories of scenarios:

- **Wiring:** S3/SQS beans, conversion, bucket/queue names, endpoint override, and test region work properly.
- **Failures:** missing bucket/queue, client network errors, duplicate message handling, and permission denials in a suitable simulated environment.

LocalStack and emulators do not fully emulate IAM policies, STS, IMDS, roles, or every AWS regional difference. Do not treat emulated test results as proof that production IAM is correct.

### 8.3. Smoke Tests on a Dedicated AWS Account

After integration tests, run a constrained smoke test with:

1. A role **dedicated exclusively to the test environment** and cost-controlled AWS test resources.
2. Explicitly specified region and pre-provisioned test buckets/queues.
3. Credentials obtained via IAM role/OIDC matching the CI or workload environment, with no committed static keys.
4. Small verification calls using STS to confirm the principal, S3/SQS operations, and cleanup of test resources where appropriate.
5. Assertions on target account, ARN, or resource before mutating actions; never allow tests to modify or delete production data.

This test verifies IAM permissions, networking, region, encryption, and real behavior better than unit tests or emulators, though it still does not replace load testing and long-running operational validation.

## 9. Security, Secrets, and Operations

### 9.1. Identity Configuration Rules

- **Prefer temporary credentials and IAM roles** for workloads running on AWS.
- Never write long-lived access keys in Git, Dockerfiles, build artifacts, shared `application*.yml` files, or logs.
- Never reset keys globally with `System.setProperty(...)` at runtime to "switch accounts"; this affects the whole process and introduces race conditions.
- If cross-account calls are required, design explicit STS assume-role or role profiles with appropriate trust policies and session durations.
- **Authentication credentials** and **resource permissions** are two layers. IAM policies, bucket policies, KMS, and network policies still require testing.

### 9.2. Region Configuration Rules

- Configure regions per deployment environment and according to actual resource locations.
- For multi-region applications, manage clients per region instead of relying on a single global variable.
- Ensure storage, queue, database, and secret adapters use matching regions/resource IDs.
- In CI, set the region explicitly rather than relying on a runner's default profile.

### 9.3. Observability and Incident Handling

Logs should record **service, operation, intended region, request ID/correlation ID, and error type**, while scrubbing credentials, session tokens, and secret contents. Enable verbose SDK logging only in controlled environments and follow sensitive-data masking policies. Track metrics on `AccessDenied` counts, region configuration errors, and retries/network failures to quickly catch issues during role changes or multi-region rollouts.

Changing a credential provider can change the principal evaluated by IAM. Any change to roles, profiles, environment variables, or config beans should be tested prior to rollout.

## 10. Connections to Azure and Google Cloud

The multi-cloud Spring Boot integration module recognizes the same general requirement: **an application needs an identity and a resource location/endpoint to call a managed service**. However, provider names and lookup orders differ across ecosystems.

| Ecosystem | Common identity mechanisms | How location/resource is determined |
| --- | --- | --- |
| AWS SDK Java v2 / AWSpring | `DefaultCredentialsProvider`, IAM roles, STS, profiles | `DefaultAwsRegionProviderChain` or explicit region |
| Azure SDK / Spring Cloud Azure | Mechanisms such as `DefaultAzureCredential` and Managed Identity, depending on library/version | Resource endpoint, subscription, and service deployment region |
| Google Cloud client libraries / Spring Cloud GCP | **Application Default Credentials (ADC)** and service accounts/workload identity | Project ID, location, and per-service endpoints |

This is a **conceptual comparison**; it does not mean the chains share identical order, policies, or semantics. For example, AWS `AWS_REGION` is not a universal environment variable controlling Azure Storage or Google Cloud Storage. When designing multi-cloud adapters, separate business code from each provider's specific identity and location configuration.

## 11. Hands-On Exercise

**Scenario:** A Spring Boot service stores contracts in S3 and sends events to SQS. The service runs on developer machines, CI, and production ECS. The system uses AWSpring and AWS SDK for Java v2.

### Task 1: Predict the Selected Provider

For each scenario below, state which provider is most likely used first and explain why:

| Scenario | Available configuration |
| --- | --- |
| A | Local machine has a valid `dev` profile, no static keys in environment |
| B | Valid ECS task role, but container has valid `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` for another account |
| C | EKS IRSA has `AWS_ROLE_ARN` + token file, no credentials in system properties/environment |
| D | EC2 has an instance profile, no higher-priority credential sources |
| E | CI has no valid role, profile, token, or keys |

**Hint:** A → profile; B → environment; C → web identity; D → IMDS/instance profile; E → unable to resolve credentials error. Actual runtime results still depend on whether the source is configured properly and whether the SDK has the required support modules.

### Task 2: Region Lookup

A developer sets:

~~~text
Java property: aws.region=eu-west-1
Environment:   AWS_REGION=ap-southeast-1
AWS profile:   region=us-east-1
~~~

Which region will `S3Client.create()` prioritize? What if `S3Client.builder().region(Region.US_WEST_2).build()` is used?

**Check answer:** With the default client, the Java system property `aws.region` takes precedence, so it resolves to `eu-west-1`. With the builder specifying `Region.US_WEST_2`, the client region is `us-west-2`. Both outcomes are independent of the credential chain.

### Task 3: Diagnose Real-World Incidents

1. An ECS task reports `AccessDenied` even though the task role already has `s3:PutObject`. Verify which credentials were selected and whether environment keys are overriding; then inspect the object ARN, bucket policy, and KMS.
2. A local IDE reports `Unable to load region` even though `aws sso login` succeeded. Check the region in the profile, `AWS_REGION`, or client beans; SSO only solves part of the identity problem.
3. An EKS IRSA Pod fails to find credentials. Check the token file, role ARN, trust policy, STS module, provider overrides, and STS reachability.
4. Integration tests pass with LocalStack, but production fails when calling SQS. Check IAM/queue policies, queue region, URL/ARN, listener configuration, and the workload's credential provider.

### Task 4: Design Secure Configuration

Propose configuration for three environments:

- **Local:** `AWS_PROFILE` pointing to the dev-sandbox profile, region from config or `AWS_REGION`.
- **CI:** OIDC/temporary role credentials and explicit `AWS_REGION`; isolated test resources.
- **ECS:** task role, clearly defined region, no static environment keys.

Explain how to detect early if the application connects to the wrong account or region, and how to verify via `GetCallerIdentity`, filtered logs, and smoke tests.

## 12. Key Takeaways

**DefaultCredentialsProvider** selects credential sources in priority order: **Java system properties → environment variables → web identity → shared profile → container credentials → EC2 instance profile**. **DefaultAwsRegionProviderChain** resolves regions in priority order: **Java system property `aws.region` → `AWS_REGION` → shared profile → EC2 metadata**, unless the region is set directly on the client. Spring Cloud AWS can configure beans/regions/credentials via properties or custom configuration, so inspect both Spring and the SDK when diagnosing issues.

Applying both chains correctly helps Spring Boot applications safely use roles on AWS, run consistently across environments, connect to the right resource region, and separate identity, IAM, and endpoint issues from business logic errors. This forms the foundation for expanding into S3, SQS, secrets, databases, and comparing integration patterns across AWS, Azure, and Google Cloud.
