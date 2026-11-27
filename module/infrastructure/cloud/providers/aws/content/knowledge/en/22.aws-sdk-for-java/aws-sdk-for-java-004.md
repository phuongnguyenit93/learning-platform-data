# Region Provider Chain, Endpoints, and AWS Signature Version 4

> **Chapter:** AWS SDK for Java  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem across Region/AZ infrastructure, IAM, VPC, compute, storage, databases, integration, and serverless. Learners develop the skills to select services and design and deploy applications that are secure, observable, resilient, and cost-controlled.

## Learning Objectives

A Java application running on a personal workstation, CI pipeline, Amazon ECS, and Amazon EC2 can call the same AWS service, yet each environment differs in **Region, credentials, networking, and endpoints**. If the application hardcodes hostnames or signs HTTP requests manually, it can easily target the wrong Region, use the wrong partition, generate invalid signatures, or leak secrets.

**AWS SDK for Java 2.x** handles most of this through provider chains, endpoint rules, and request signers. This lesson focuses on three questions:

1. Where does the SDK resolve the **Region** from, in what order, and when do explicit configurations take effect?
2. How does the SDK select a **service endpoint**, and when are endpoint overrides, FIPS, dual-stack, or specialized endpoints needed?
3. How does **AWS Signature Version 4 (SigV4)** sign requests, and why must Region, service, headers, body, and timestamp match?

After this lesson, you will be able to:

- Distinguish between service Region, SSO login Region, Availability Zone, and AWS partition.
- Describe the default Region provider chain and profile configuration in Java SDK v2.
- Distinguish between the Region provider chain and the credentials provider chain.
- Configure an explicit Region, `Region.of(...)`, and `DefaultAwsRegionProviderChain`.
- Understand endpoint resolution, `endpointOverride`, FIPS, dual-stack, and service-specific endpoint rules.
- Design connections to LocalStack/custom endpoints while keeping signing Region semantics accurate.
- Explain SigV4 canonical request, string to sign, credential scope, signing key, and signature.
- Understand temporary credentials, session tokens, presigned URLs, and SigV4a.
- Troubleshoot `NoRegion`, `UnknownHost`, `SignatureDoesNotMatch`, `InvalidSignatureException`, and clock skew errors.
- Write Java SDK v2 code following least privilege, client reuse, no credential logging, and configuration testing.

## 1. How Are Region, Endpoint, and Signature Related?

### 1.1. Three Separate Decisions That Must Stay Consistent

| Component | Question | Example |
|---|---|---|
| **Region** | Which Region does the API request target? | `ap-southeast-1` |
| **Endpoint** | Which hostname/URL is the HTTP request sent to? | `dynamodb.ap-southeast-1.amazonaws.com` |
| **Signing context** | Which credentials, Region, and service scope sign the request? | `AWS4-HMAC-SHA256 / ap-southeast-1 / dynamodb` |

The Region typically affects both **endpoint resolution** and the **SigV4 credential scope**. Changing an endpoint URL without understanding the signing Region can lead to authentication failures.

~~~mermaid
flowchart TD
    APP[Java application] --> CFG[Client configuration]
    CFG --> R[Region provider]
    CFG --> C[Credentials provider]
    R --> E[Endpoint resolution]
    R --> S[Signing Region]
    C --> S
    E --> HTTP[HTTP request]
    S --> SIGN[SigV4 signer]
    HTTP --> SEND[Signed request]
    SIGN --> SEND
    SEND --> AWS[AWS service endpoint]
~~~

For standard service clients, the SDK handles these steps automatically. Developers primarily choose the right **Region, credentials provider, endpoint behavior, and HTTP client**.

### 1.2. Region Is Not Availability Zone

An **AWS Region** is an independent geographic area composed of multiple Availability Zones. An **Availability Zone (AZ)** is an isolated infrastructure location within a Region. Java SDK service clients generally configure a **Region**, not an AZ.

~~~text
Region: ap-southeast-1
  AZ: ap-southeast-1a
  AZ: ap-southeast-1b
  AZ: ap-southeast-1c
~~~

AZ suffixes such as `a`, `b`, `c` can map differently across AWS accounts. Do not treat one account's AZ name as a fixed global identifier.

### 1.3. Choosing a Region Based on Workload Requirements

Consider:

- User proximity and latency;
- Data residency, compliance, and retention policies;
- Available services, engines, and instance types;
- AZ count and disaster recovery requirements;
- Pricing, data transfer, and dependencies;
- VPC connectivity, private endpoints, and cross-Region traffic.

Supporting S3 in a Region does not mean every feature of every service is available there. Verify service availability, feature availability, and quotas before deploying.

### 1.4. AWS Partitions

AWS operates multiple **partitions**, for example:

| Partition | Example Region | Common DNS Suffix |
|---|---|---|
| `aws` | `ap-southeast-1`, `us-east-1` | `amazonaws.com` |
| `aws-cn` | `cn-north-1` | `amazonaws.com.cn` |
| `aws-us-gov` | `us-gov-west-1` | `amazonaws.com` |

An ARN typically follows the structure:

~~~text
arn:<partition>:<service>:<region>:<account-id>:<resource>
~~~

Illustrative examples:

~~~text
arn:aws:dynamodb:ap-southeast-1:111122223333:table/LearningCore
arn:aws-cn:dynamodb:cn-north-1:111122223333:table/LearningCore
~~~

Never hardcode the `aws` DNS suffix or ARN partition into shared libraries intended for China/GovCloud. The SDK and endpoint rules are Region/partition-aware; applications should obtain ARNs and Regions from trusted configuration.

## 2. The Default Region Provider Chain in Java SDK v2

### 2.1. Why Have a Provider Chain?

An application might run on a developer laptop, CI, ECS, EKS, EC2, or Lambda. Each environment provides the Region differently. Instead of writing conditional configuration branches, Java SDK v2 provides **`DefaultAwsRegionProviderChain`** to resolve the Region in a defined order.

### 2.2. Provider Chain Order

The Java SDK 2.x default Region provider chain checks in sequence:

1. **JVM system property** `aws.region`;
2. **Environment variable** `AWS_REGION`;
3. **AWS shared config file** — Region of the selected profile;
4. **EC2 Instance Metadata Service (IMDS)** — Region of the EC2 instance when metadata is accessible.

~~~mermaid
flowchart TD
    A[Resolve Region] --> B{JVM property aws.region?}
    B -->|Yes| R1[Use system property]
    B -->|No| C{Environment AWS_REGION?}
    C -->|Yes| R2[Use AWS_REGION]
    C -->|No| D{Selected profile has region?}
    D -->|Yes| R3[Use shared config profile region]
    D -->|No| E{EC2 IMDS available?}
    E -->|Yes| R4[Use EC2 instance Region]
    E -->|No| F[No Region found / exception]
~~~

**The first valid value found wins.** For example, `aws.region=us-west-2` in JVM system properties takes precedence over `AWS_REGION=ap-southeast-1`.

### 2.3. Do Not Confuse AWS_REGION and AWS_DEFAULT_REGION

For the Java SDK v2 default Region provider chain, the documented environment variable is:

~~~text
AWS_REGION=ap-southeast-1
~~~

`AWS_DEFAULT_REGION` is common in the AWS CLI and some other tools, but **do not assume Java SDK v2 reads it like AWS_REGION**. If a Java app gets its Region from the environment, use `AWS_REGION` or configure the Region explicitly.

Do not assume SDKs for other languages use the exact same provider chain or precedence order.

### 2.4. Configuring the JVM System Property

Running the application:

~~~bash
java -Daws.region=ap-southeast-1 -jar application.jar
~~~

Or before building clients:

~~~java
System.setProperty("aws.region", "ap-southeast-1");
~~~

Set the system property before the SDK resolves the Region and constructs clients. Avoid mutating global system properties while the application is running: already-created clients do not dynamically switch Regions.

### 2.5. Configuring the Environment Variable

Linux/macOS:

~~~bash
export AWS_REGION=ap-southeast-1
java -jar application.jar
~~~

PowerShell:

~~~powershell
$env:AWS_REGION = "ap-southeast-1"
java -jar application.jar
~~~

Environment variables are process-scoped configuration. Region is generally not a secret, yet it still requires proper management to avoid deploying into the wrong environment.

### 2.6. Shared Config File and Profiles

Example `~/.aws/config`:

~~~ini
[default]
region = ap-southeast-1
output = json

[profile dev]
region = ap-southeast-1
output = yaml

[profile staging]
region = ap-southeast-2

[profile prod]
region = ap-southeast-1
~~~

A profile is selected via `AWS_PROFILE` or JVM system property `aws.profile`:

~~~bash
export AWS_PROFILE=dev
~~~

In the shared config file, `[default]` omits the `profile` prefix, whereas named profiles use `[profile dev]`. The Region in the selected profile serves as the Region provider chain source when higher-priority sources are absent.

**Note:** Profile Regions live in the **shared config file** `~/.aws/config`; `~/.aws/credentials` primarily stores credentials. Do not put a Region in the credentials file expecting the SDK to read it from there.

### 2.7. Custom Config File Paths

| Variable | Meaning |
|---|---|
| `AWS_PROFILE` | Select profile |
| `AWS_CONFIG_FILE` | Path to shared config file |
| `AWS_SHARED_CREDENTIALS_FILE` | Path to shared credentials file |
| `AWS_REGION` | Region for Java SDK v2 default chain |
| `AWS_DEFAULT_REGION` | Common in AWS CLI/tooling; do not rely on it for Java SDK v2 |

Never commit shared credentials files to a repository. On laptops, use profiles/SSO per organizational policy; in production, prefer workload roles.

### 2.8. sso_region Is Not the Service Client's Region

An IAM Identity Center profile may contain:

~~~ini
[profile dev-sso]
sso_session = company
sso_account_id = 111122223333
sso_role_name = Developer
region = ap-southeast-1
sso_region = ap-southeast-2
sso_start_url = https://example.awsapps.com/start

[sso-session company]
sso_region = ap-southeast-2
sso_start_url = https://example.awsapps.com/start
sso_registration_scopes = sso:account:access
~~~

`sso_region` targets the **IAM Identity Center/SSO service** to acquire tokens; `region` is the default Region for AWS service clients when that profile is active. The two values may differ.

Sign in following your organization's workflow, e.g., `aws sso login --profile dev-sso`, and let the Java SDK use the profile/SSO credentials provider. Do not treat `sso_region` as your DynamoDB/S3 Region.

### 2.9. IMDS on EC2

When earlier sources lack a Region, the SDK can read EC2 instance metadata via the **Instance Metadata Service (IMDS)**.

- IMDSv2 uses session tokens; instance metadata options may enforce token usage;
- IMDS may be disabled or blocked by instance settings, proxies, or network controls;
- Container/proxy settings must avoid forwarding metadata requests externally;
- Do not rely on IMDS on a local laptop or non-EC2 runtimes;
- Never broaden metadata permissions merely to mask a missing Region config.

If no provider yields a Region, the SDK throws an error like **Unable to load region from any of the providers in the chain**. Configure a valid Region source or pass the Region explicitly.

## 3. Region Provider Chain vs. Credentials Provider Chain

### 3.1. Two Chains Answering Two Questions

| Provider Chain | Answers | Example |
|---|---|---|
| Region provider | Which AWS Region to call? | `ap-southeast-1` |
| Credentials provider | Which identity signs/authenticates? | IAM role, SSO, access key session |

Having a Region **does not imply having credentials**. Having credentials **does not mean the SDK knows the Region**. A client normally needs both to send a signed request.

### 3.2. Default Credentials Provider Chain

Java SDK v2 `DefaultCredentialsProvider` searches for credentials across sources including:

- JVM system properties;
- Environment variables;
- Web identity tokens / role credentials;
- Shared profile/configuration, including profile-declared providers;
- Container credentials;
- EC2 instance profile credentials via IMDS.

Profiles can use IAM Identity Center/SSO, assume-role, `credential_process`, and other SDK-supported mechanisms when matching dependencies and configuration are present.

**Do not confuse the Region chain order with the credentials chain order.** The Region chain inspects `aws.region`, `AWS_REGION`, shared config Region, and IMDS; the credentials chain resolves identity/secret credentials using its own rules.

### 3.3. Workload Identity Instead of Long-Lived Access Keys

| Environment | Common Credential Source |
|---|---|
| Developer laptop | IAM Identity Center/SSO profile or organization-managed profile |
| CI workload | OIDC federation → assume role, when supported by the platform |
| Amazon ECS | Task role |
| Amazon EKS | EKS Pod Identity or IRSA per architecture |
| Amazon EC2 | Instance profile role |
| AWS Lambda | Execution role |

Never embed `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in Java source code, Docker images, Maven settings, or logs. Temporary credentials have an expiration and session token; SDK providers handle refreshing them appropriately.

### 3.4. Explicit Credentials Provider Configuration

Default provider:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;

DefaultCredentialsProvider credentialsProvider =
    DefaultCredentialsProvider.create();
~~~

Specific profile:

~~~java
import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;

ProfileCredentialsProvider profileProvider =
    ProfileCredentialsProvider.builder()
        .profileName("dev")
        .build();
~~~

Use an explicit profile when developer tools require a specific profile; production services should use runtime-appropriate role providers. Never hardcode profile `dev` in applications deployed to ECS/EC2/Lambda.

### 3.5. Web Identity and Container Credentials

In containers/EKS, workload identity grants each workload a scoped IAM role. Avoid mounting a node's shared credentials file into every pod or granting one broad node role to all applications.

Some providers rely on runtime-injected endpoint/metadata environment variables. Do not set `AWS_CONTAINER_CREDENTIALS_*` or `AWS_WEB_IDENTITY_TOKEN_FILE` manually unless you understand the trust policy and token audience.

### 3.6. Checking Region and Identity Separately

A startup diagnostic might log:

~~~text
service=dynamodb
region=ap-southeast-1
credential_source=task-role (category only)
endpoint_mode=standard
~~~

Log only non-sensitive source/configuration details. Never log access keys, secrets, session tokens, SSO caches, credential objects, or Authorization headers. To verify caller identity, call STS `GetCallerIdentity` as allowed by network/policy; responses contain account/ARN details and should also be treated as internal metadata.

## 4. Configuring Region in Java SDK v2

### 4.1. Passing the Region Explicitly

The most predictable approach:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();
~~~

`builder.region(...)` overrides the Region provider chain for that client. This fits when the deployment Region is fixed and injected from controlled configuration.

### 4.2. Using the Default Region Provider Chain to Inspect the Effective Region

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.DefaultAwsRegionProviderChain;

Region region = new DefaultAwsRegionProviderChain().getRegion();

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(region)
    .build();
~~~

When the builder omits a Region, the SDK uses the default chain internally as well. Invoking the chain explicitly is helpful when you want to **log/validate the effective Region** before initializing multiple service clients.

If the chain fails to find a Region, fail startup with a clear configuration error; do not silently fall back to `us-east-1` unless that is an approved architectural decision.

### 4.3. New Regions or Missing Enum Constants

Use the `Region.of("region-name")` factory:

~~~java
Region region = Region.of("ap-southeast-5");
~~~

This lets you pass a Region string even before your SDK version defines a constant for it, provided the service/endpoint supports it and SDK endpoint rules handle it. Still, upgrade the SDK to a version that officially supports the new Region to get updated endpoint metadata, signing behavior, and bug fixes.

**Never infer a Region is valid just because a `Region` object constructs cleanly.** AWS must still support the service and feature there.

### 4.4. Multiple Service Clients Sharing One Region Config

~~~java
Region region = Region.of(configuredRegion);

try (DynamoDbClient dynamoDb = DynamoDbClient.builder()
         .region(region)
         .build();
     S3Client s3 = S3Client.builder()
         .region(region)
         .build();
     SqsClient sqs = SqsClient.builder()
         .region(region)
         .build()) {
    // Reuse clients for application operations.
}
~~~

Service clients are thread-safe and should be **reused** across the application lifecycle. Never create a client per HTTP request; each client owns its own HTTP connection pool, retry/config state, and lifecycle.

### 4.5. An Application Can Call Multiple Regions

~~~java
S3Client mediaS3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();

DynamoDbClient metadataDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_2)
    .build();
~~~

Do not use a single global Region for every client in a multi-Region architecture. Name configurations after their service/workload to prevent mix-ups. Cross-Region requests can increase latency/data transfer costs and carry distinct IAM/network requirements.

### 4.6. Do Not Mutate Region After Building

The Region is fixed in the client configuration at build time. To call a different Region, create a **separate client for that Region** and reuse it, rather than mutating global `AWS_REGION` at runtime.

Never create a static global DynamoDB client using a Region taken directly from user input. If tenants span multiple Regions, build a routing layer with an allowlist, trusted mapping, and managed client lifecycle/caching.

## 5. Endpoint Resolution in Java SDK v2

### 5.1. What Is an Endpoint?

An endpoint is the URL/hostname of an AWS service API. For example:

~~~text
https://dynamodb.ap-southeast-1.amazonaws.com
https://s3.ap-southeast-1.amazonaws.com
https://sqs.ap-southeast-1.amazonaws.com
~~~

An endpoint can include scheme, host, port, and path/base path. The SDK applies **service endpoint rules** to determine the endpoint from:

- Service;
- Region and partition;
- Endpoint parameters;
- FIPS/dual-stack flags;
- ARN/resource Region for applicable services;
- Endpoint override if configured;
- Service-specific behavior such as S3 addressing/access points.

**Do not hardcode hostnames using the template** `service.region.amazonaws.com` for every service. Some services are global, have special endpoint rules, use partition-specific DNS suffixes, or route by ARN.

### 5.2. Region Determines the Default Endpoint

When a client is built with Region `ap-southeast-1`, SDK endpoint rules typically select the matching regional endpoint:

~~~java
DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();
~~~

The SDK handles the endpoint host and signing context. Applications should supply the **Region** instead of concatenating URL strings manually, unless an intentional endpoint override is required.

### 5.3. Endpoint Override

`endpointOverride(URI)` is used to send requests to a specific URL, such as LocalStack, a mock server, a compatible gateway, or a private test endpoint:

~~~java
import java.net.URI;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .build();
~~~

**Region is still required** because the SDK uses it in the signing context even when the host is overridden. Custom endpoints may require specific service/Region signing behavior; overriding the endpoint does not disable SigV4.

### 5.4. Endpoint Override Does Not Create Network Connectivity

Setting the endpoint URL to `http://localhost:4566` does not start LocalStack. Specifying a private endpoint DNS name does not configure VPC routes, security groups, TLS trust, or DNS resolution.

Before using an endpoint override, verify:

1. The hostname resolves from the runtime;
2. The port is open and network routing is valid;
3. TLS certificates/CAs are valid if using HTTPS;
4. The endpoint speaks the expected protocol/API;
5. Signing service/Region match;
6. The endpoint supports the IAM/authentication mode;
7. Client timeouts/retries do not mask connectivity errors.

### 5.5. FIPS Endpoints

Certain AWS services and Regions offer **FIPS (Federal Information Processing Standards)** endpoints.

- Enable only when supported by the service and Region;
- Do not guess and manually append `-fips` to hostnames;
- SDK service clients/endpoint rules provide FIPS configuration options;
- A FIPS endpoint alone does not make all application data and workflows compliant with an entire compliance standard.

### 5.6. Dual-Stack Endpoints

Dual-stack endpoints support **IPv4 and IPv6** where supported by the service, Region, and network. Enabling dual-stack does not automatically route all traffic over IPv6; DNS, VPCs, routes, firewalls, and the client network stack must still allow it.

FIPS and dual-stack can be combined where endpoint rules support both. Never hardcode hostname suffixes to enable dual-stack.

### 5.7. Service-Specific Endpoint Rules

Several services have specialized rules:

- **Amazon S3:** virtual-hosted/path-style addressing, access point ARNs, Multi-Region Access Points, accelerate, and dual-stack;
- **STS:** global vs. regional endpoint options and signing Region behavior per configuration;
- **DynamoDB/SQS/Lambda:** typically regional endpoints, still governed by service/partition endpoint rules;
- **IAM/Route 53/CloudFront:** special endpoint scopes/behaviors; consult service documentation rather than applying a generic regional hostname pattern.

SDK v2 uses endpoint rules to handle many of these cases. For custom endpoints or ARN-based Region routing, test with realistic requests.

### 5.8. Endpoint Discovery

Some services support **endpoint discovery** or return dedicated endpoints per resource/operation. This is a service-specific capability, not something every service client performs automatically.

When a service API returns endpoint metadata, the SDK can discover and cache endpoints according to client configuration. Read the specific service's guide; never cache discovered endpoints indefinitely or ignore expiration/refresh semantics.

## 6. Endpoint Behavior for S3 and Special Cases

### 6.1. Virtual-Hosted-Style vs. Path-Style

S3 has two URL formats for representing buckets and objects:

~~~text
Virtual hosted:
https://my-bucket.s3.ap-southeast-1.amazonaws.com/folder/file.txt

Path style:
https://s3.ap-southeast-1.amazonaws.com/my-bucket/folder/file.txt
~~~

Virtual-hosted style is standard. Path-style support has limitations and feature-specific behavior across S3 endpoints; do not assume every bucket or feature works with path-style addressing.

### 6.2. Access Point ARNs and Multi-Region Access Points

S3 Access Point ARNs and Multi-Region Access Point ARNs can invoke special **endpoint rules**. The SDK understands ARN/Region routing when using an appropriately configured client.

Do not parse ARNs manually to assemble hostnames when the SDK already has an endpoint resolver; manual parsing easily breaks partition handling, DNS suffixes, signing Regions, and SigV4a requirements.

### 6.3. Accelerate, Dual-Stack, and FIPS

S3 options such as accelerate, dual-stack, path-style, and FIPS each have specific support conditions. Never enable all options simultaneously without verifying valid combinations. Bucket naming, TLS certificate hostnames, and S3 access point ARNs can all affect endpoint selection.

### 6.4. LocalStack and Mock Endpoints

LocalStack is useful for integration testing, but **it is not real AWS**:

- Not every service API, feature, or quota is fully emulated;
- IAM enforcement, eventual consistency, and retry semantics may differ;
- Endpoint overrides belong in test profiles, never in production;
- Passing tests against LocalStack does not prove production endpoints, IAM, or credential refresh are configured correctly.

~~~java
S3Configuration s3Configuration = S3Configuration.builder()
    .pathStyleAccessEnabled(true)
    .build();

S3Client localS3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .serviceConfiguration(s3Configuration)
    .build();
~~~

`S3Configuration.pathStyleAccessEnabled(true)` is an S3-specific setting; enable it only if the emulator requires path-style requests. For production S3, let the SDK apply standard endpoint rules.

### 6.5. Do Not Log Endpoint URLs Containing Query Secrets

Some custom gateways and presigned URLs carry authentication material in query parameters. Avoid logging full URLs, Authorization headers, or signing details. Log redacted service, Region, endpoint mode, and request/correlation IDs.

## 7. AWS Signature Version 4: Purpose and Scope

### 7.1. Why Does AWS Sign Requests?

SigV4 enables AWS to verify the signing credentials, HTTP method/URI/query/headers, payload hash (when payload signing is active), date/Region/service scope, and temporary credential session token.

SigV4 **is not encryption**. HTTPS/TLS protects data in transit; SigV4 authenticates the request and protects the integrity of signed elements. A validly signed request still requires IAM policies permitting the action and resource.

### 7.2. High-Level Signing Pipeline

~~~text
HTTP request
  -> Canonical Request
  -> SHA-256 hash of Canonical Request
  -> String to Sign
  -> Derived Signing Key
  -> HMAC-SHA256 Signature
  -> Authorization header or presigned query parameters
~~~

### 7.3. The SDK Signs Requests Automatically

For standard service clients, SDK v2 fetches credentials from the provider, obtains the UTC timestamp, builds the canonical request, derives the signing key/signature, attaches the Authorization/session token headers, and sends the request over HTTP.

**Never implement your own SigV4 signer in business code** and never set the `Authorization` header manually when using an AWS SDK service client. Manual signing is prone to errors in encoding, headers, payload hashing, session tokens, clock skew, and endpoint routing.

### 7.4. SigV4 Does Not Replace IAM Authorization

A properly signed request from a role lacking `dynamodb:PutItem` still receives `AccessDeniedException`. SigV4 proves which credentials signed the request; IAM/resource policies/SCPs/KMS/endpoint policies decide whether the action is permitted.

| Error | Common Meaning |
|---|---|
| `SignatureDoesNotMatch` / `InvalidSignatureException` | Signature or canonicalization/signing scope mismatch |
| `ExpiredToken` / `InvalidClientTokenId` | Expired, wrong, or invalid credentials |
| `AccessDenied` | Credentials authenticated, but policy denies or a policy condition blocks |

## 8. SigV4: Canonical Request

### 8.1. Structure

A canonical request has the form:

~~~text
HTTPMethod
CanonicalURI
CanonicalQueryString
CanonicalHeaders

SignedHeaders
HashedPayload
~~~

Lines are separated by newlines per the specification. Canonical headers end with a newline, resulting in a blank line before `SignedHeaders` in standard representations.

### 8.2. HTTP Method

Use the actual method: `GET`, `POST`, `PUT`, `DELETE`, etc. The method must match the outgoing request. Do not sign as `POST` and later switch to `GET`.

### 8.3. Canonical URI

The canonical URI is the path encoded according to SigV4 rules:

- Path encoding must follow UTF-8/percent-encoding rules;
- Do not arbitrarily normalize slashes;
- S3 has special path rules handled per service by the SDK;
- Do not double-encode, or decode and re-encode in a proxy without understanding signer behavior.

Requests to object keys with special characters can fail if a gateway alters `%2F`, `%20`, `+`, or Unicode characters after signing.

### 8.4. Canonical Query String

Query parameters are encoded and sorted by key/value according to SigV4 rules. Do not assume original query order is preserved in the canonical form.

~~~text
GET /?Action=ListUsers&Version=2010-05-08
~~~

The canonical query string is constructed from encoded parameter pairs in sorted order. Duplicate parameters or empty values must follow exact encoding and sorting rules.

### 8.5. Canonical Headers

Headers are normalized:

- Header names in lowercase;
- Sorted lexicographically;
- Whitespace trimmed and collapsed;
- Essential headers include `host` and relevant `x-amz-*` headers per request;
- `SignedHeaders` lists signed header names separated by semicolons.

Example:

~~~text
content-type:application/x-amz-json-1.0
host:dynamodb.ap-southeast-1.amazonaws.com
x-amz-date:20261120T035000Z
x-amz-target:DynamoDB_20120810.GetItem
~~~

If a reverse proxy rewrites `Host`, alters a signed header, modifies the body, or alters whitespace after signing, AWS may fail to verify the signature.

### 8.6. Hashed Payload

Typically the payload hash is:

~~~text
Hex(SHA256(request body bytes))
~~~

For an empty request body, the hash is still the SHA-256 of empty bytes. Some services, operations, or streaming modes use different payload rules, such as unsigned payloads or chunked signing. **Never hardcode `UNSIGNED-PAYLOAD` for every service**; the SDK applies the appropriate rule.

### 8.7. Canonical Request Must Match the Wire Request

A common bug is signing serialized JSON and having a serializer or proxy later change bytes or encoding. SigV4 protects the hash of body bytes according to the signing mode; changing even a single byte changes the signature.

Use SDK request models rather than signing raw JSON manually. When traversing an API gateway or reverse proxy, ensure signed headers, path, query, and body are not modified.

## 9. String to Sign, Credential Scope, and Signing Key

### 9.1. String to Sign

The String to Sign has the structure:

~~~text
AWS4-HMAC-SHA256
YYYYMMDD'T'HHMMSS'Z'
YYYYMMDD/region/service/aws4_request
Hex(SHA256(CanonicalRequest))
~~~

Example:

~~~text
AWS4-HMAC-SHA256
20261120T035000Z
20261120/ap-southeast-1/dynamodb/aws4_request
<canonical-request-sha256-hex>
~~~

The timestamp and credential scope must match the request's date, Region, and service.

### 9.2. Credential Scope

The credential scope has four parts:

~~~text
<date>/<region>/<service>/aws4_request
~~~

Example:

~~~text
20261120/ap-southeast-1/dynamodb/aws4_request
~~~

If a client sends to DynamoDB in `ap-southeast-1` while the signer uses `ap-southeast-2`, the scope mismatches the endpoint and the request is rejected. Even with a custom host via `endpointOverride`, the signing Region and service must match what the AWS-compatible endpoint expects.

### 9.3. Derive the Signing Key

SigV4 derives keys iteratively using HMAC-SHA256:

~~~text
kDate    = HMAC-SHA256("AWS4" + SecretAccessKey, YYYYMMDD)
kRegion  = HMAC-SHA256(kDate, Region)
kService = HMAC-SHA256(kRegion, Service)
kSigning = HMAC-SHA256(kService, "aws4_request")
~~~

`SecretAccessKey` is a secret. Derived signing keys are also sensitive material; never log or persist them.

### 9.4. Compute the Signature

~~~text
Signature = Hex(
    HMAC-SHA256(kSigning, StringToSign)
)
~~~

AWS receives the `Authorization` header, recomputes the canonical request, scope, and signature using the corresponding credentials, and compares them. If everything matches and the credentials are valid, the request proceeds to authorization.

### 9.5. Authorization Header

Illustrative format:

~~~text
Authorization: AWS4-HMAC-SHA256
 Credential=AKIAEXAMPLE/20261120/ap-southeast-1/dynamodb/aws4_request,
 SignedHeaders=content-type;host;x-amz-date;x-amz-target,
 Signature=<signature-hex>
~~~

The access key ID appears in the Credential scope, but **the secret access key is never transmitted**. The signature is not a substitute secret for the access key; headers and tokens must still be protected.

## 10. Temporary Credentials and Session Tokens

### 10.1. STS Credentials Have Three Components

Temporary credentials typically include:

~~~text
AccessKeyId
SecretAccessKey
SessionToken
Expiration
~~~

The SDK provider supplies complete credentials and refreshes them over time. When signing with temporary credentials, requests must carry the **session token** (typically via the `X-Amz-Security-Token` header or a query parameter in presigned URLs).

### 10.2. Why Is the Session Token Critical?

If a request is signed with valid access key/secret but omits the session token or uses an expired token, AWS returns `InvalidToken`, `ExpiredToken`, or a similar error.

Never copy just the access key and secret from a role session while dropping the token. Use `DefaultCredentialsProvider`, web identity/container/instance profile providers, or another full provider so the SDK manages the entire credential tuple.

### 10.3. Credential Refresh

- IAM role credentials expire and supported providers refresh automatically;
- SSO credentials require a valid login/session and supporting SDK modules/providers;
- Static credentials do not rotate automatically;
- Custom credentials providers must handle refresh, thread safety, expiration, and errors.

Never build a `StaticCredentialsProvider` once from temporary credentials and leave the application running for hours without refreshing. Let the SDK use runtime providers.

## 11. Presigned URLs

### 11.1. What Is a Presigned URL?

A presigned URL is a pre-signed URL allowing its holder to execute a specific request within a limited time window, commonly used for direct S3 uploads/downloads without giving AWS credentials to the client.

The URL may include query parameters such as:

~~~text
X-Amz-Algorithm
X-Amz-Credential
X-Amz-Date
X-Amz-Expires
X-Amz-SignedHeaders
X-Amz-Security-Token (if temporary credentials)
X-Amz-Signature
~~~

**A presigned URL is a bearer capability**: anyone holding the URL can use it within the signed method, resource, and expiration window. Do not log it, send it to analytics, or leave it exposed publicly after it is no longer needed.

### 11.2. Expiration

For SigV4 S3 presigned URLs, the common maximum `X-Amz-Expires` is **7 days (604800 seconds)** when signed with credentials valid for that duration. When signed with temporary credentials, the URL **becomes invalid when those credentials expire**, even if `X-Amz-Expires` specifies a longer duration.

Policies, bucket/object state, credential revocation, and service conditions can also invalidate a URL before expiration. Use the shortest expiration suited to the workflow.

### 11.3. Java S3Presigner

~~~java
import java.time.Duration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

S3Presigner presigner = S3Presigner.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(DefaultCredentialsProvider.create())
    .build();

GetObjectRequest getObject = GetObjectRequest.builder()
    .bucket("private-course-assets")
    .key("courses/c1/lesson-1.pdf")
    .build();

GetObjectPresignRequest presignRequest =
    GetObjectPresignRequest.builder()
        .signatureDuration(Duration.ofMinutes(10))
        .getObjectRequest(getObject)
        .build();

String url = presigner.presignGetObject(presignRequest)
    .url()
    .toExternalForm();
~~~

This example presigns a download. Production systems must verify the user is authorized to access the object rather than relying on bucket/key secrecy; keep the bucket private and scope the signing role's `s3:GetObject` permissions to the required prefix/resource. Close `S3Presigner` on application shutdown.

### 11.4. Presigned PUT

For uploads, sign a `PutObjectRequest` with an appropriate `signatureDuration` and include any signed headers. If Content-Type, checksum, or encryption headers are signed, the uploading client must send the exact same values; altering headers after signing causes a signature mismatch.

### 11.5. A Presigned URL Is Not a Proxy

Clients using a presigned URL talk directly to S3; the application server does not need to proxy the file bytes. Consider browser CORS, opaque/random object keys, upload size limits, checksums, malware scanning, and object lifecycle policies. The URL is not inherently single-use.

## 12. SigV4a and Multi-Region Signing

### 12.1. SigV4 vs. SigV4a

**SigV4** signs for a single specific Region in the credential scope. **SigV4a** is a variant supporting multi-Region requests with a different signing algorithm/behavior, used by features such as S3 Multi-Region Access Points and other supported AWS services/features.

Do not manually replace `AWS4-HMAC-SHA256` or force SigV4a on every request. The SDK selects the right signer and endpoint behavior when required by the API and resource.

### 12.2. ARNs and Multi-Region Routing

Some ARNs embed a Region, while certain resources/service APIs apply custom routing rules. For S3 MRAP, the SDK uses endpoints and SigV4a to route across multi-Region endpoints. Never extract an ARN's Region or hostname assuming it always dictates the signing Region for every API.

### 12.3. SigV4a Does Not Cross Partition Boundaries

SigV4a does not bypass partition, IAM, network, or resource policy boundaries. Resources must still be supported within the target partition and service configuration. Never assume a multi-Region signed request can cross arbitrarily between commercial, China, and GovCloud partitions.

## 13. Java SDK v2: Dependencies and Client Lifecycle

### 13.1. Maven BOM and Service Modules

Maven example:

~~~xml
<properties>
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
    <artifactId>auth</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>regions</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sts</artifactId>
  </dependency>
</dependencies>
~~~

`2.x.y` is a placeholder, not a released version. Pick a tested SDK v2 version for your project and import the BOM so all modules align. Never mix SDK v1 (`com.amazonaws`) and v2 (`software.amazon.awssdk`) in the same configuration scheme.

If a profile uses IAM Identity Center/SSO, include the SDK modules required for the SSO provider per your SDK version's documentation. Having an SSO profile file on disk does not put SSO modules on the application classpath.

### 13.2. Client Factory and Reuse

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;

public final class AwsClients implements AutoCloseable {
    private final DefaultCredentialsProvider credentials;
    private final DynamoDbClient dynamoDb;
    private final S3Client s3;
    private final StsClient sts;

    public AwsClients(Region region) {
        this.credentials = DefaultCredentialsProvider.create();

        this.dynamoDb = DynamoDbClient.builder()
            .region(region)
            .credentialsProvider(credentials)
            .build();

        this.s3 = S3Client.builder()
            .region(region)
            .credentialsProvider(credentials)
            .build();

        this.sts = StsClient.builder()
            .region(region)
            .credentialsProvider(credentials)
            .build();
    }

    public DynamoDbClient dynamoDb() { return dynamoDb; }
    public S3Client s3() { return s3; }
    public StsClient sts() { return sts; }

    @Override
    public void close() {
        dynamoDb.close();
        s3.close();
        sts.close();
        credentials.close();
    }
}
~~~

In production, manage clients through dependency injection and application lifecycle; never instantiate a factory per request. Clients are thread-safe and should be reused. When sharing a credentials provider, close it only after all clients using it have stopped.

### 13.3. Validate Effective Region at Startup

~~~java
import java.util.Set;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.DefaultAwsRegionProviderChain;

Region region = new DefaultAwsRegionProviderChain().getRegion();

Set<String> allowed = Set.of("ap-southeast-1", "ap-southeast-2");
if (!allowed.contains(region.id())) {
    throw new IllegalStateException("Configured AWS Region is not allowed");
}

log.info("AWS service Region configured: {}", region.id());
~~~

`getRegion()` throws an exception if resolution fails; translate it into a clear startup error. An allowlist suits apps with fixed deployment Regions; do not hardcode an allowlist if the app is designed for multi-Region operation with its own configuration policy.

Never log credentials. If account/Region values are treated as internal metadata, log only to the extent permitted by organizational policy.

### 13.4. Endpoint Override in Test Profiles

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient testClient = DynamoDbClient.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .credentialsProvider(
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create("test", "test")))
    .build();
~~~

These are **test-only credentials and endpoint**. Never use static `AwsBasicCredentials` in production. LocalStack generally accepts dummy credentials, which proves nothing about production AWS IAM policies, STS, or credential refreshes.

Keep endpoint overrides in isolated test configuration so developer environment variables cannot leak into production containers.

### 13.5. HTTP Clients and Timeouts

SDK v2 supports synchronous and asynchronous HTTP clients. Select based on concurrency, streaming, application framework, and operational requirements:

- Sync clients use the configured HTTP implementation, such as Apache or URLConnection;
- Async clients typically use Netty/AWS CRT depending on dependencies and configuration;
- Set connection timeout, API call timeout, and attempt timeout to align with SLOs;
- Reuse HTTP connection pools;
- Never disable TLS verification;
- Retry only appropriate errors, accounting for write idempotency.

Never use huge timeouts to mask network failures, and never retry every exception indiscriminately; configuration or authorization errors will not resolve on retry.

## 14. AWS CLI vs. Java SDK: Configurations Can Differ

### 14.1. Checking Region/Identity via the CLI

**Read-only** commands:

~~~bash
aws configure list
aws configure get region --profile dev
aws sts get-caller-identity --region ap-southeast-1
~~~

`aws configure list` shows the CLI's configuration sources, which does not prove Java SDK v2 resolves the exact same values. The CLI and Java SDK can differ in provider chain, version, and configuration.

### 14.2. Checking Environment Variables

Linux/macOS:

~~~bash
printenv AWS_REGION
printenv AWS_PROFILE
~~~

PowerShell:

~~~powershell
Get-ChildItem Env:AWS_REGION
Get-ChildItem Env:AWS_PROFILE
~~~

Never dump the entire environment into logs or CI output, as that can expose secret variables.

### 14.3. Reading Profile Config

~~~ini
[profile dev]
region = ap-southeast-1
output = json
credential_process = /usr/local/bin/company-credential-helper

[profile staging]
region = ap-southeast-2
role_arn = arn:aws:iam::111122223333:role/StagingDeveloper
source_profile = default
~~~

When using `credential_process`, the helper must be secure, executable from the Java environment, and emit output matching the expected protocol; never write credentials to stdout/stderr outside the required JSON schema. In production, prefer workload roles.

### 14.4. Why Does the CLI Succeed While the Java SDK Fails?

Common causes:

- CLI profile was selected via `AWS_PROFILE`, but the Java process did not inherit that variable;
- CLI uses `AWS_DEFAULT_REGION`, whereas Java SDK requires `AWS_REGION`/profile/explicit Region;
- CLI version supports SSO/`credential_process`, while Java SDK lacks the required module/dependency or compatible version;
- Java runs inside a container without mounted config/cache;
- Java process has `-Daws.region` set differently from the environment;
- SDK v1/v2 or service module versions are out of sync;
- Proxy, trust store, DNS, or HTTP client settings differ from the CLI;
- Java client has a different `endpointOverride` or signing Region.

**Never run `aws sts get-caller-identity` and assume the Java app uses the same identity.** Diagnose directly inside the Java runtime using redacted credential/Region source diagnostics.

## 15. Troubleshooting Region and Endpoint Errors

### 15.1. NoRegion / Unable to Load Region

Causes:

- Missing `aws.region`, `AWS_REGION`, and profile Region;
- Wrong profile selected;
- Java process cannot see `~/.aws/config`;
- IMDS unavailable;
- `AWS_CONFIG_FILE` points to the wrong path.

Resolution steps:

1. Log the profile name safely without logging secrets;
2. Check `AWS_REGION`;
3. Check JVM system properties;
4. Inspect the selected profile in shared config;
5. If on EC2, check IMDS options/networking;
6. Or pass `.region(Region...)` explicitly.

### 15.2. UnknownHostException / Connection Timeout

Check:

- Whether endpoint rules generated the expected hostname;
- DNS resolvers and VPC DNS settings;
- PrivateLink interface endpoint / Private DNS;
- Route tables, NACLs, security groups, and proxies;
- Service Region and endpoint availability;
- Whether a test `endpointOverride` was accidentally left in production config.

Successful DNS resolution alone does not prove ports, TLS, or IAM are working.

### 15.3. Unsupported Region / Endpoint

An older SDK version may lack endpoint metadata for a newer Region or service. Update AWS SDK v2 to an organization-supported version. `Region.of(...)` constructs a `Region` object, but does not add new service support or endpoint rules.

### 15.4. Endpoint Region Differs from Signing Region

Symptoms can include signature mismatch or authorization errors. Check:

- Client `.region(...)`;
- Region in the endpoint hostname;
- The custom endpoint's expected signing Region;
- ARN Region and service-specific routing;
- STS regional/global endpoint configuration if applicable.

Never "fix" this by guessing random Regions until requests succeed; that can send data to the wrong Region.

### 15.5. FIPS/Dual-Stack Endpoint Does Not Exist

The service/Region/partition may not support the requested combination yet. Check AWS service endpoints documentation, SDK endpoint rules, and DNS. Never hardcode suffixes instead of using FIPS/dual-stack configuration options.

## 16. Troubleshooting SigV4 and Credentials Errors

### 16.1. SignatureDoesNotMatch

Check in order:

1. Signing Region and endpoint Region;
2. Service signing name (`dynamodb`, `s3`, `execute-api`, etc.);
3. Host UTC clock accuracy;
4. Whether a proxy modified the HTTP method/path/query;
5. Whether signed headers were altered or stripped;
6. Whether payload bytes changed after signing;
7. Whether the temporary session token was included;
8. Whether the access key and secret belong to the same credentials tuple;
9. S3 path encoding and virtual-hosted-style formatting.

Never share `Authorization` headers or secret keys for debugging. Use SDK wire logging only in sandboxes and **redact** sensitive headers and bodies.

### 16.2. Clock Skew

SigV4 requests include a UTC timestamp; clock drift can cause AWS to reject requests. Synchronize host/container nodes via NTP or time sync services. Never manually adjust timestamps or disable signature verification.

### 16.3. ExpiredToken / InvalidToken

Check expiration and session tokens; verify whether the credentials provider refreshes properly, whether SSO login expired, or whether the container/instance role endpoint is reachable. Replace static temporary credentials with an auto-refreshing provider.

### 16.4. AccessDenied Is Not Always a Bad Signature

A request may be validly signed yet denied by:

- IAM identity policies;
- Resource policies (S3 bucket, SQS queue, KMS key, Lambda permission, etc.);
- SCPs / permission boundaries / session policies;
- VPC endpoint policies;
- KMS key policies;
- Explicit `Deny` or unmet conditions;
- Region/resource/account mismatches.

Use CloudTrail and IAM policy evaluation within your authorized permissions; never grant `AdministratorAccess` as a diagnostic shortcut.

### 16.5. Error Differentiation Table

| Error | Layer | Where to Fix |
|---|---|---|
| `NoRegion` | Configuration | Region provider chain/profile |
| `UnknownHost` | DNS/network | Hostname, VPC DNS, endpoint |
| Connect timeout | Network | Routes, SG/NACL, port |
| TLS handshake/cert error | Transport security | CA bundle, hostname, trust store |
| `SignatureDoesNotMatch` | SigV4 canonicalization/scope | Region, service, timestamp, request bytes |
| `ExpiredToken` | Credentials | Refresh/session login |
| `AccessDenied` | Authorization | IAM/resource/SCP/KMS/endpoint policy |
| `ThrottlingException` | Service quota/load | Backoff, capacity, request patterns |
| `SerializationException` | Protocol/model | SDK module/version/request model |

## 17. Security Best Practices

### 17.1. Least Privilege

- Use IAM roles for workloads;
- Allow only the required actions and resources;
- Separate roles by service and environment;
- Scope S3 prefixes, DynamoDB tables/indexes, and KMS keys;
- Never embed long-lived keys;
- Never grant `AdministratorAccess` to applications.

### 17.2. Region Allowlisting and Data Residency

If an application is restricted to Singapore/Australia, validate the Region from deployment configuration before building clients. Never let user requests pass `region=...` directly to instantiate clients for arbitrary Regions.

### 17.3. TLS and Endpoint Security

- Use HTTPS/TLS for AWS endpoints;
- Never disable certificate verification;
- For PrivateLink endpoints, verify Private DNS, security groups, and endpoint policies;
- Custom endpoints must lie within the trust boundary;
- Never let untrusted input control `endpointOverride`, as that can introduce SSRF.

### 17.4. Never Log Secrets or Request Signatures

Redact:

- `Authorization`;
- `X-Amz-Security-Token`;
- Access keys and session tokens;
- Presigned URL query strings;
- Sensitive request bodies;
- SSO cache/token files.

You may log normalized service, operation, Region, request ID, latency, retry count, and endpoint mode.

### 17.5. Presigned URLs Are Access Capabilities

- Short expiration;
- Specific HTTP method and object key;
- Keep the S3 bucket private;
- Validate authorization before signing;
- Never treat a presigned URL as a user identity;
- Never log or forward URLs to untrusted systems;
- Enforce checksums, content-type/size policies, and malware scanning for uploads.

## 18. Testing Region, Endpoints, and SigV4

### 18.1. Unit Tests for Configuration

Test precedence using **isolated processes**, since system properties and environment variables are process-global. Do not mutate the environment across parallel tests and expect deterministic results.

| Case | System Property | Env | Profile | Expected |
|---|---|---|---|---|
| 1 | `aws.region=us-west-2` | `AWS_REGION=ap-southeast-1` | `eu-west-1` | `us-west-2` |
| 2 | none | `AWS_REGION=ap-southeast-1` | `eu-west-1` | `ap-southeast-1` |
| 3 | none | none | `region=eu-west-1` | `eu-west-1` |
| 4 | none | none | none, no IMDS | `NoRegion` exception |
| 5 | explicit builder Region | any | any | Explicit Region |

Do not run Case 4 on an EC2 instance with active IMDS if verifying "no provider found"; isolate the environment or inject a test provider.

### 18.2. Endpoint Tests

- Default endpoint for service + Region;
- China/GovCloud partitions if supported by the app;
- Endpoint override in test profiles;
- Supported FIPS/dual-stack combinations;
- S3 access point / MRAP ARNs;
- PrivateLink DNS and network paths;
- Verify custom endpoints are not accidentally enabled in production.

### 18.3. SigV4 Integration Tests

Use an AWS sandbox or an appropriate service emulator:

- Requests carry valid signed headers;
- Temporary credentials include the session token;
- Expired tokens and clock skew are classified accurately;
- Proxies preserve path/query/host/body intact;
- Presigned URL method, expiry, and headers match;
- IAM `AccessDenied` is distinguished from signature failures;
- Credentials and `Authorization` headers never appear in test reports.

### 18.4. Checking Caller Identity in Java

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

try (StsClient sts = StsClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {
    GetCallerIdentityResponse identity = sts.getCallerIdentity();
    log.info("AWS account={}, arn={}",
        identity.account(), identity.arn());
}
~~~

`GetCallerIdentity` reveals which AWS principal the client is using. Although the action typically requires no explicit IAM allow, network and endpoint reachability must still work. Account/ARN may be internal metadata; log only to the degree permitted.

## 19. Scenario Exercise

### 19.1. Problem Statement

A Java 17 Spring Boot service runs in three environments:

- Developer laptops using IAM Identity Center profile `dev`;
- CI using OIDC assume role;
- Production running with an ECS task role in `ap-southeast-1`.

The service calls DynamoDB and S3. Integration tests use LocalStack. Some customers in Australia store metadata in `ap-southeast-2`. The application needs a presigned S3 download URL valid for 10 minutes.

Design:

1. Region config for each service/environment;
2. Credentials providers for laptop/CI/ECS;
3. Endpoint override enabled only in tests;
4. Reusable DynamoDB/S3 clients per Region;
5. SigV4 signing context matching service/Region;
6. Presigned URL expiry/authorization;
7. Logging/monitoring without exposing secrets;
8. Fail-fast startup if production has the wrong Region configured.

### 19.2. Reference Configuration

~~~text
Developer laptop:
  AWS_PROFILE=dev
  ~/.aws/config profile dev region=ap-southeast-1
  IAM Identity Center login via AWS CLI

CI:
  OIDC -> assume role
  AWS_REGION=ap-southeast-1
  no long-lived static keys

Production ECS:
  Task role
  AWS_REGION=ap-southeast-1
  no shared credentials file
  private VPC endpoint/network as required

LocalStack test:
  endpointOverride=http://localhost:4566
  Region=us-east-1 (test signing context)
  dummy test credentials
  isolated test data only
~~~

Australia workload:

~~~text
DynamoDB client for Singapore -> ap-southeast-1
DynamoDB client for Australia -> ap-southeast-2
S3 presigner -> Region of the bucket/resource selected by trusted config
~~~

Never accept Region from an untrusted request parameter. Resolve tenant-to-Region mappings from authenticated backend configuration or metadata.

### 19.3. Design Analysis

- **Laptop:** profile `dev` holds the Region and SSO settings; the SDK uses the appropriate profile credentials provider.
- **CI:** OIDC federation supplies temporary role credentials; no static access keys are stored.
- **ECS:** the task role supplies credentials; environment/config sets the Region; no developer credentials are mounted.
- **LocalStack:** endpoint override is activated only in the test profile, with dummy credentials and isolated synthetic data.
- **Multi-Region:** build and reuse separate clients for `ap-southeast-1` and `ap-southeast-2`; Region mapping is controlled by the backend.
- **Presigned URL:** verify authorization to the object before signing; 10-minute expiration; never log the URL.
- **SigV4:** the SDK signs requests automatically using the matching credentials and Region; never assemble `Authorization` headers manually.

### 19.4. Self-Assessment Questions

1. What sources does Java SDK v2's default Region provider chain check, and in what order?
2. How do `aws.region` and `AWS_REGION` differ?
3. Is `AWS_DEFAULT_REGION` a standard environment variable for Java SDK v2's default Region chain?
4. How does the Region provider chain differ from the credentials provider chain?
5. What does `AWS_PROFILE` select? Which file typically stores the profile's Region?
6. How does `sso_region` differ from the service client's `region`?
7. When does the SDK use IMDS to resolve the Region?
8. Why does `Region.of(...)` not guarantee that a service or Region is supported?
9. Why does explicit `.region(...)` override the default chain?
10. Why does an endpoint override still require a Region?
11. How does endpoint resolution differ from hardcoding hostnames?
12. Do FIPS and dual-stack automatically guarantee compliance or IPv6 connectivity?
13. What components make up a canonical request?
14. Why must the `Host` header and signed headers remain unchanged after signing?
15. A credential scope contains date, Region, service, and which final string?
16. Through which steps is the signing key derived?
17. What additional fields do temporary credentials require besides access key and secret?
18. Does SigV4 encrypt data in place of TLS?
19. Why can a request with a valid signature still fail with `AccessDenied`?
20. In what sense is a presigned URL a bearer capability, and how must it be protected?
21. Why can temporary credentials cause a presigned URL to expire before `X-Amz-Expires`?
22. How does SigV4a differ from SigV4 in purpose and Region handling?
23. Why does a successful AWS CLI command not prove the Java SDK uses the same profile or Region?
24. When should you reuse SDK clients instead of building one per request?
25. Why should you never implement a custom SigV4 signer in business code?

### 19.5. Suggested Answers

1. JVM `aws.region` → `AWS_REGION` → selected shared config profile → EC2 IMDS.
2. One is a JVM system property, the other an environment variable; the system property takes precedence.
3. Do not rely on `AWS_DEFAULT_REGION` for Java SDK v2; use `AWS_REGION`, a profile, or explicit Region.
4. The Region chain selects the Region; the credentials chain selects identity/secret credentials.
5. `AWS_PROFILE` selects the profile; Region resides in `~/.aws/config`.
6. `sso_region` targets the Identity Center service; `region` is the default for AWS service clients.
7. When earlier providers find no Region and EC2 metadata is reachable.
8. Constructing the object does not mean the AWS service endpoint or feature exists there.
9. Explicit builder configuration is used directly by the client instead of resolving the chain.
10. The Region is still required for the signing scope and service behavior.
11. The SDK applies service rules, partitions, and features; manual hostnames are error-prone.
12. No; you must verify service support, routes, DNS, policies, and overall compliance.
13. Method, canonical URI, canonical query, canonical headers, signed headers, and payload hash.
14. Because the signature is computed over the canonical representation; post-signing mutations invalidate the hash/signature.
15. `aws4_request`.
16. Secret+date → Region → service → `aws4_request`.
17. Session token and expiration.
18. No; TLS encrypts the transport, whereas SigV4 signs/authenticates the request.
19. IAM, resource, SCP, KMS, or VPC endpoint policies can still deny it.
20. Anyone possessing the URL can execute the signed request; keep expiry short and never log or share publicly.
21. A presigned URL cannot outlive the credentials used to sign it.
22. SigV4 scopes to a specific Region; SigV4a supports multi-Region signing for eligible features.
23. The CLI and Java SDK can read different variables, profiles, and dependencies.
24. SDK clients are thread-safe and manage HTTP pools; reuse avoids overhead and socket/resource churn.
25. Canonicalization, session tokens, endpoint rules, streaming, and clock skew are easy to get wrong.

## 20. Production Deployment Checklist

### Region and Identity

- [ ] Region is set explicitly or resolved from a tested provider chain.
- [ ] `AWS_DEFAULT_REGION` is not relied upon for Java SDK v2 without verified behavior.
- [ ] The right profile is selected; `region` and `sso_region` are not confused.
- [ ] Workload credentials use SSO/OIDC/task role/instance role appropriately.
- [ ] No long-lived access keys exist in source, images, or CI logs.
- [ ] Region/partition is allowlisted per data residency and compliance rules.

### Endpoint and Network

- [ ] Service endpoints are resolved by SDK Region/partition rules.
- [ ] `endpointOverride` is enabled only in environments that need it.
- [ ] Endpoint overrides still carry the proper signing Region.
- [ ] FIPS/dual-stack options are enabled only where supported by the service and Region.
- [ ] PrivateLink/DNS/security groups/routes/TLS have been tested from the runtime.
- [ ] S3 addressing/access point/MRAP behavior has been tested.
- [ ] Full presigned URLs and auth query strings are never logged.

### SigV4 and Security

- [ ] The SDK signer is used instead of manual `Authorization` headers.
- [ ] Region, service signing name, timestamp, and credential scope are consistent.
- [ ] Temporary credentials include session tokens and refresh properly.
- [ ] Host/path/query/body/headers are not modified by proxies after signing.
- [ ] Clock sync/NTP is active and healthy.
- [ ] TLS certificate and hostname verification are enabled.
- [ ] Least privilege is enforced; valid signatures are not mistaken for IAM authorization.
- [ ] Secrets, `Authorization`, session tokens, and presigned URLs are redacted.

### Reliability and Operations

- [ ] SDK clients are reused and closed per application lifecycle.
- [ ] Timeouts, retries, and backoff match SLOs and idempotency guarantees.
- [ ] Startup validation clearly reports Region/profile/endpoint errors.
- [ ] CloudTrail, metrics, and request IDs are used for diagnostics.
- [ ] Unit/integration tests cover Region precedence, endpoint overrides, and SigV4.
- [ ] LocalStack/test credentials cannot leak into production.
- [ ] SDK versions/BOM are managed and updated per dependency policy.

**Expected outcome:** learners can properly configure Regions and endpoints for Java SDK v2 across laptops, CI, and AWS workloads; distinguish Region and credentials chains; explain and handle SigV4 signing; use presigned URLs safely; and diagnose endpoint/signature errors without exposing credentials.

## Official AWS Documentation

- [AWS SDK for Java 2.x — Region selection](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html)
- [AWS SDK for Java 2.x — Credentials](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html)
- [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [AWS SDK for Java 2.x — Configuration and profiles](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-profiles.html)
- [AWS SDK for Java 2.x — Endpoint configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-config.html)
- [AWS SDK for Java 2.x — Endpoint discovery](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-discovery.html)
- [AWS SDK for Java 2.x — FIPS endpoints](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/fips-endpoints.html)
- [AWS SDK for Java 2.x — Dual-stack endpoints](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dualstack-endpoints.html)
- [AWS SDK for Java 2.x — IAM Identity Center credentials](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-sso.html)
- [AWS SDK for Java 2.x — Best practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html)
- [AWS Signature Version 4 signing process](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-signing-elements.html)
- [Create a canonical request for SigV4](https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html)
- [Derive a signing key for SigV4](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html)
- [Signing AWS API requests](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv.html)
- [SigV4 presigned URL considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [AWS Signature Version 4A](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-signing-elements.html)
- [AWS service endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/aws-service-information.html)
- [AWS partitions and ARNs](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference-arns.html)
- [Amazon EC2 instance metadata and IMDSv2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Application note:** Profiles, Regions, account IDs, hostnames, credentials, endpoint URLs, and code in this lesson are **training examples**. Never use placeholder credentials in production. Endpoint availability, signer behavior, and SDK APIs can vary by service, Region, and SDK version; verify current AWS documentation, test in a sandbox, protect secrets, and follow change approval processes.
