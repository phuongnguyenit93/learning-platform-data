# Region, Endpoint, RAM Role, and STS Credentials

## 1. Problem Statement and Objectives

A Spring Boot application running on ECS needs to query instance details, read/write objects in OSS, and call several other Alibaba Cloud OpenAPIs. The application must know which region the resource resides in, whether to connect via a public or VPC endpoint, and which identity to authenticate with. If any of these three parts is misconfigured, requests may be sent to the wrong service/region, denied due to missing permissions, or fail when an STS token expires.

Four core concepts:

- **Region** identifies the cloud area where resources are created and managed.
- **Endpoint** is the network address of a product API to which the SDK sends requests.
- **RAM role** is an identity without long-lived AccessKeys; a trusted principal must assume the role to obtain permissions.
- **STS credentials** are temporary authentication credentials issued by Security Token Service for a role session.

This lesson belongs to the **Alibaba Cloud** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module teaches practical Spring Boot integration with managed services from AWS, Azure, Google Cloud, and Alibaba Cloud through their respective libraries; learners need to configure identity/permissions, storage, messaging, data, secret protection, integration testing, and evaluate differences across cloud providers.

After completing this lesson, you will be able to:

1. Distinguish region ID, endpoint, public/VPC endpoints, and resource location.
2. Select the right endpoint when creating, querying, or updating resources.
3. Explain the trust policy and permission policy of a RAM role.
4. Describe the AssumeRole flow and the three components of STS credentials.
5. Choose RAM roles on ECS, OIDC/RRSA on ACK, or AssumeRole for external systems.
6. Configure the Alibaba Cloud Java SDK V2 Credentials tool in Spring Boot.
7. Use a caching/auto-refreshing credential provider and handle token expiry and endpoint errors.

## 2. Region and Endpoint Are Two Different Pieces of Information

### 2.1. Region Identifies Where a Resource Exists

A **Region ID** is an area code, for example:

- Singapore: **ap-southeast-1**
- Malaysia (Kuala Lumpur): **ap-southeast-3**
- Indonesia (Jakarta): **ap-southeast-5**
- China (Hangzhou): **cn-hangzhou**

The list of regions is published per product by Alibaba Cloud and may change. Not every service is available in every region. When creating a database, bucket, instance, or queue, the resource is typically bound to the selected region; read/update/delete operations must target the exact region hosting that resource.

The **application's region** may differ from the resource's region. For example, an application running in Singapore may need to query a bucket in Malaysia. The SDK must send requests to the bucket's region endpoint; do not use the host machine's region as a substitute for the resource's location.

### 2.2. Endpoint Identifies the Target API

An **Endpoint** is the domain name a client connects to in order to invoke a product's API. Endpoints can vary by:

- Product (ECS, OSS, RDS, SMS, SLS, etc.).
- Region where the product is deployed.
- Centralized versus regional deployment model.
- Network path: public internet or private/VPC.
- Product control plane versus data plane API.

For example, the public endpoint of ECS in Singapore has the form:

~~~text
ecs.ap-southeast-1.aliyuncs.com
~~~

For example, the public OSS endpoint of Singapore has the form:

~~~text
oss-ap-southeast-1.aliyuncs.com
~~~

Do not guess a product's endpoint by substituting the product name into another product's pattern. Some services use centralized endpoints with no region in the hostname; others use per-region endpoints. Look up endpoints in the product documentation or OpenAPI Explorer.

### 2.3. Public Endpoints and VPC Endpoints

| Endpoint Type | Connection Path | When to Use |
| --- | --- | --- |
| **Public endpoint** | Over the internet/public network | Local development, applications outside Alibaba Cloud, or workloads needing public API access |
| **VPC endpoint** | Over a private network inside a VPC | ECS/ACK and resources in the same region calling services over a private network |
| **Product-specific internal endpoint** | Internal domain following product conventions | Services like OSS provide dedicated internal endpoints |
| **Central endpoint** | API served from one or a few central regions | Products that publish centralized endpoints; do not prepend a region to the hostname |

VPC endpoints can reduce latency and avoid public traffic, but typically require the workload to be in the matching region/VPC with permissive network policies. Each product's VPC endpoint has its own format; SDK documentation recommends specifying the exact endpoint rather than assembling hostnames manually.

**Endpoint selection rules:**

- When **creating a new resource**, pick a region close to the workload/users that satisfies data, compliance, and availability requirements.
- When **reading, updating, or deleting an existing resource**, use the endpoint for the region where the resource resides.
- When the application runs inside a VPC, verify supported VPC endpoints and DNS/routing paths.
- When running locally or outside a VPC, use the appropriate public endpoint.
- When configuring an endpoint explicitly, verify the HTTPS protocol, hostname, and resource region.

### 2.4. Exception to Remember for OSS

OSS introduces the additional concept of a **Dedicated Region ID**. For example:

| Concept | Example |
| --- | --- |
| General Region ID | **ap-southeast-1** |
| OSS Dedicated Region ID | **oss-ap-southeast-1** |
| OSS public endpoint | **oss-ap-southeast-1.aliyuncs.com** |
| OSS internal endpoint | **oss-ap-southeast-1-internal.aliyuncs.com** |
| Bucket domain | **my-invoice-bucket.oss-ap-southeast-1.aliyuncs.com** |

Some APIs/SDKs use the general Region ID, while OSS endpoints or OSS-specific parameters use the dedicated region ID. Read the exact field specification in the SDK docs instead of mechanically altering prefixes.

For instance, OSS Java SDK V2 requires configuring credentials and a region/endpoint matching the bucket. If using SDK V1 with Signature Version 4, you must specify the region as required by that SDK version. A bucket created in Hangzhou accessed via a Singapore endpoint will be rejected by OSS with an instruction to resend the request to the correct endpoint.

## 3. RAM User, RAM Role, and STS

### 3.1. RAM User and RAM Role

**RAM (Resource Access Management)** manages identities and access permissions on Alibaba Cloud.

| Characteristic | RAM User | RAM Role |
| --- | --- | --- |
| Identity represented | A specific user or application | A set of permissions assumed by a trusted principal |
| Long-lived AccessKey | May have one | Does not have one |
| Usage | Calls APIs directly using the user's credentials | Assumed to receive temporary credentials |
| Credential lifetime | Long-lived until rotated/revoked | Expires at the end of the role session |
| Trust policy | Not used in the role-assumption model | Mandatory; defines which principals may assume the role |
| Use cases | Local developers, legacy automation, or initial bootstrap credential | Cloud workloads, cross-account access, federation, and temporary access |

Never use the Alibaba Cloud root account's AccessKey in applications. If a long-lived AccessKey is needed for development or to assume a role, use a dedicated least-privilege RAM user and store the secret in a secret manager.

A RAM role is not just a RAM user with a different name. A role has no password or standalone AccessKey; STS issues a set of temporary credentials when a principal successfully assumes the role.

### 3.2. Two Policies with Distinct Roles

When configuring a RAM role, distinguish between:

1. **Trust policy** (a resource-based policy attached to the role): defines who is allowed to assume the role.
2. **Access/permission policy** (an identity-based policy attached to the role): defines what the role is allowed to do once assumed.

For example, a role named **InvoiceUploaderRole** might allow only an ECS service or an ACK workload to assume it. Once assumed, the role may only upload objects to an invoice bucket/prefix. The trust policy does not grant upload permissions by itself; the access policy does not permit arbitrary principals to assume the role.

For standard AssumeRole, both conditions must hold:

- The principal calling STS has an identity-based permission allowing **sts:AssumeRole** on the target role.
- The target role's trust policy permits that principal under its **Principal**, **Action**, and **Condition** sections.

If either is missing, STS denies the request. For federation via **AssumeRoleWithOIDC** or **AssumeRoleWithSAML**, configure the IdP and trust policy according to the protocol; do not mechanically apply RAM user AssumeRole permissions.

### 3.3. Sample Trust Policy for Cross-Account Access

Suppose account A owns the target role; account B has a CI/CD RAM role that needs temporary access. The role's trust policy in account A can trust that specific role from account B:

~~~json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Principal": {
        "RAM": [
          "acs:ram::111122223333:role/ci-deployer"
        ]
      }
    }
  ]
}
~~~

This is an illustrative example. Replace the account ID and role ARN with real values and add conditions matching your security requirements. Avoid overly broad principals such as an entire account when unnecessary. For third-party integrations, consider **ExternalId** to mitigate confused-deputy risks.

The role in account A also needs its own access policy, such as allowing only reads from a reporting bucket. The principal in account B likewise needs permission to assume the role under its own policies. Both sides must be verified.

### 3.4. Session Policy and RoleSessionName

When calling AssumeRole, you can pass a **session policy** to further narrow permissions for that session. Effective permissions are the intersection of the permission policies attached to the role and the session policy; a session policy can never expand a role's permissions.

**RoleSessionName** names the assume-role session and appears in ActionTrail, making it possible to trace which actor or workload performed an action. Use a descriptive name such as **order-api-prod** or **invoice-worker-2026-11**; never put secrets or personal data in the session name.

## 4. How Does STS Work?

### 4.1. AssumeRole Flow

~~~mermaid
sequenceDiagram
    participant App as Spring Boot workload
    participant RAM as RAM
    participant STS as Security Token Service
    participant OSS as OSS API

    App->>STS: AssumeRole / AssumeRoleWithOIDC
    STS->>RAM: Verify caller and trust policy
    RAM-->>STS: Allow if conditions are met
    STS-->>App: Temporary credentials + Expiration
    App->>OSS: Signed API request + SecurityToken
    OSS->>RAM: Evaluate role permissions
    RAM-->>OSS: Allow / Deny
    OSS-->>App: API response
~~~

1. The application holds a source identity (RAM user, RAM role, ECS instance role, or OIDC identity).
2. The application calls STS to assume the role.
3. RAM verifies whether the principal is trusted and authorized to assume the role.
4. STS returns temporary credentials.
5. The application uses these credentials to sign requests to OSS, ECS, or other services.
6. When credentials expire, the provider acquires a new session via its supported refresh mechanism.

### 4.2. What Do STS Credentials Contain?

A set of STS credentials consists of three components:

- **AccessKeyId**: the temporary AccessKey ID.
- **AccessKeySecret**: the corresponding secret used to sign requests.
- **SecurityToken**: the token proving the credentials were issued by STS for a role session.

Additionally, the response includes **Expiration** indicating when the credentials expire. When using STS, you must pass all three components as required by the SDK. Providing only AccessKeyId and AccessKeySecret without SecurityToken will cause requests to be rejected.

### 4.3. Session Duration

According to current RAM/STS documentation:

- The default duration of the AssumeRole API is **3,600 seconds (1 hour)**.
- The requested duration can range from **900 seconds (15 minutes)** up to the role's maximum session duration.
- A role's maximum session duration can be configured between **1–12 hours**.
- The actual duration cannot exceed the maximum session duration configured on the role.

Choose the shortest duration that satisfies the task. For brief upload tasks, a shorter session limits the window of misuse if credentials leak. For continuously running workloads, use a caching and auto-refreshing credential provider instead of manually minting tokens too frequently.

### 4.4. STS Tokens Do Not Auto-Refresh in Every Case

Static STS credentials passed into an application have an expiration time. Once expired, the application must obtain fresh credentials from the issuer. Providers such as **ram_role_arn**, **ecs_ram_role**, **oidc_role_arn**, and **credentials_uri** in the Alibaba Cloud Credentials tool support caching and automatic refresh. Use a singleton client/provider to reuse that cache.

Never call AssumeRole on every incoming HTTP request to your application. Doing so increases latency, load on STS, and the risk of throttling.

## 5. Choosing a Credential Mechanism by Environment

| Environment | Suitable Mechanism | Notes |
| --- | --- | --- |
| Developer workstation | Alibaba Cloud CLI profile or test RAM user via environment variables | Use a test account and least-privilege permissions |
| ECS | Instance RAM role | SDK retrieves STS credentials via metadata; do not bake AccessKeys into images |
| ECI | RAM role attached to the instance/container per supported feature | Use the appropriate credential provider |
| ACK | RRSA/OIDC RAM role for Kubernetes ServiceAccount | Role is assumed using an OIDC token file |
| CI/CD outside Alibaba Cloud | OIDC federation or RAM role via STS | Prefer federation; use ExternalId for third-party integrations |
| Mobile/browser client | Scoped STS credentials or signed URLs | Never distribute long-lived AccessKeys to clients |
| Legacy external application | RAM user AccessKey managed in a secret manager, used to assume a role | Plan rotation and migration to federation |

### 5.1. ECS Instance RAM Role

When a workload runs on ECS:

1. Create a RAM role with the ECS service as its trust principal per product guidelines.
2. Attach an access policy permitting only needed APIs, such as reading metadata or writing to a specific bucket.
3. Attach the role to the ECS instance.
4. Initialize the Credentials tool using the default chain or type **ecs_ram_role**.
5. The SDK retrieves temporary credentials from the Instance Metadata Service (IMDS) and refreshes them automatically.

An ECS instance can have only one instance RAM role attached at a time. If the application needs additional permissions, adjust the policy attached to that role following least privilege rather than placing multiple AccessKeys on the machine.

The Alibaba Cloud Credentials tool uses metadata in **IMDSv2** security-hardened mode. For the Java Credentials tool, security-hardened mode requires **credentials-java 0.3.10 or higher**. You can set **ALIBABA_CLOUD_ECS_METADATA** to specify the role name explicitly and save one metadata query. When enforcing security-hardened mode, configure **ALIBABA_CLOUD_IMDSV1_DISABLED=true** per the SDK docs; if metadata is unreachable, the application should fail loudly rather than silently falling back to static credentials.

### 5.2. ACK RRSA/OIDC

For applications running in ACK Kubernetes, **RRSA (RAM Roles for Service Accounts)** lets you bind an OIDC identity to a Kubernetes ServiceAccount. Workflow:

1. Enable RRSA/OIDC on the cluster and ensure an OIDC provider exists in RAM.
2. Create a RAM role that trusts the OIDC provider.
3. Restrict trust conditions by issuer, audience, and the target subject/ServiceAccount.
4. Annotate the ServiceAccount with the role ARN per ACK documentation.
5. The Credentials tool reads the OIDC token file and calls **AssumeRoleWithOIDC**.
6. The SDK uses STS credentials and refreshes them automatically.

The Java Credentials tool's default credential chain recognizes these variables:

~~~text
ALIBABA_CLOUD_ROLE_ARN
ALIBABA_CLOUD_OIDC_PROVIDER_ARN
ALIBABA_CLOUD_OIDC_TOKEN_FILE
~~~

Do not reuse another pod's token file or share an overly privileged ServiceAccount across multiple workloads. Each service account should carry only the exact permissions it needs.

### 5.3. Systems Outside Alibaba Cloud

If the application runs in another cloud or an on-premises data center, you can use OIDC federation if that platform issues compatible identity tokens. If federation is unavailable, a dedicated RAM user can use an AccessKey to call AssumeRole; the source credentials should only have permission to assume the target role.

For third-party integrations, use an **ExternalId** generated by the third party and constrain the principal/trust policy. Never share the account owner's AccessKey. Whenever the workload supports OIDC, prefer OIDC to avoid storing long-lived secrets.

## 6. Alibaba Cloud Java SDK Credentials Tool

### 6.1. Installing Dependencies

Maven example for the ECS Java SDK V2 and Credentials tool:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>credentials-java</artifactId>
        <version>${credentialsVersion}</version>
    </dependency>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>ecs20140526</artifactId>
        <version>${ecsSdkVersion}</version>
    </dependency>
</dependencies>
~~~

Pick current versions from Maven Repository or SDK Center for each artifact; do not copy the ECS SDK version into the Credentials tool. If you use credentials-java standalone without a product SDK pulling in the Tea dependency, add **com.aliyun:tea** per the Credentials tool documentation.

SDK V2 organizes packages by product name/API version, such as **com.aliyun:ecs20140526**. SDK V1 uses different artifacts and packages; do not mix configuration snippets or classes between V1 and V2.

### 6.2. Default Credential Chain

If you instantiate the Credentials tool without passing a Config, it searches for credentials along the default chain. Current Java Credentials tool documentation specifies this order:

1. Java system properties.
2. Environment variables containing an AccessKey or STS token.
3. OIDC RAM role via environment variables.
4. Shared credentials file at the default path, e.g., **~/.aliyun/config.json**.
5. ECS instance RAM role via metadata.
6. Credentials URI.

Key environment variable names:

| Variable | Meaning |
| --- | --- |
| **ALIBABA_CLOUD_ACCESS_KEY_ID** | AccessKey ID of a RAM user or STS session |
| **ALIBABA_CLOUD_ACCESS_KEY_SECRET** | AccessKey secret |
| **ALIBABA_CLOUD_SECURITY_TOKEN** | SecurityToken when using STS |
| **ALIBABA_CLOUD_ROLE_ARN** | RAM role ARN |
| **ALIBABA_CLOUD_OIDC_PROVIDER_ARN** | OIDC provider ARN |
| **ALIBABA_CLOUD_OIDC_TOKEN_FILE** | Path to the file containing the OIDC token |
| **ALIBABA_CLOUD_ECS_METADATA** | Role name on ECS, if specified explicitly |
| **ALIBABA_CLOUD_CREDENTIALS_URI** | URI serving temporary credentials |

**Ordering note:** if the host/container still has ALIBABA_CLOUD_ACCESS_KEY_ID and ALIBABA_CLOUD_ACCESS_KEY_SECRET set, the SDK will match the static credentials before OIDC or the ECS role. This can cause the application to accidentally authenticate as a RAM user instead of the intended role. Remove leftover environment variables from production when using workload identity.

### 6.3. Creating Singleton Credential and Product Clients

Spring Boot example configuring a Credentials client via the default chain and passing the provider into ECS Java SDK V2:

~~~java
package demo.cloud;

import com.aliyun.credentials.Client;
import com.aliyun.teaopenapi.models.Config;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AlibabaCloudClientConfiguration {

    @Bean
    public Client alibabaCredentialsClient() throws Exception {
        // Retrieve credentials from the default chain: OIDC, ECS role,
        // shared profile, or the source configured for the environment.
        return new Client();
    }

    @Bean
    public com.aliyun.ecs20140526.Client ecsClient(
            Client credentialsClient,
            @Value("${aliyun.ecs.endpoint}") String endpoint) throws Exception {

        Config config = new Config();
        config.setCredential(credentialsClient);
        config.setEndpoint(endpoint);

        return new com.aliyun.ecs20140526.Client(config);
    }
}
~~~

Create the clients once in the Spring context to reuse connections and credential caches. Do not instantiate a new Credentials client or product client per request. Product SDK clients are reusable; follow the specific SDK's guidance on lifecycle and resource closing.

### 6.4. Configuring application.yml

~~~yaml
aliyun:
  region-id: ${ALIBABA_CLOUD_REGION_ID:ap-southeast-1}
  ecs:
    endpoint: ${ALIBABA_CLOUD_ECS_ENDPOINT:ecs.ap-southeast-1.aliyuncs.com}
~~~

The example above uses the Singapore ECS public endpoint. When the workload runs in a VPC, replace it with the official VPC endpoint for that ECS region if supported. Do not use an OSS endpoint for ECS or vice versa.

In API-calling code, the resource region can still be passed as a request parameter. Example querying ECS instances in Singapore:

~~~java
import com.aliyun.ecs20140526.models.DescribeInstancesRequest;
import com.aliyun.ecs20140526.models.DescribeInstancesResponse;
import com.aliyun.teautil.models.RuntimeOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class EcsQueryService {
    private final com.aliyun.ecs20140526.Client ecsClient;
    private final String regionId;

    public EcsQueryService(
            com.aliyun.ecs20140526.Client ecsClient,
            @Value("${aliyun.region-id}") String regionId) {
        this.ecsClient = ecsClient;
        this.regionId = regionId;
    }

    public DescribeInstancesResponse describeInstances() throws Exception {
        DescribeInstancesRequest request =
                new DescribeInstancesRequest().setRegionId(regionId);

        return ecsClient.describeInstancesWithOptions(
                request, new RuntimeOptions());
    }
}
~~~

The workload's IAM/RAM role needs permission to read ECS instances, such as an appropriate read-only policy or a custom policy scoped to the needed APIs/resources. If it only calls DescribeInstances, do not grant permissions to create or delete instances.

### 6.5. Configuring an Explicit Provider When Needed

If you do not want to rely on the default chain, the Credentials tool supports provider types such as **ram_role_arn**, **ecs_ram_role**, **oidc_role_arn**, and **credentials_uri**. Example for ACK OIDC:

~~~java
import com.aliyun.credentials.Client;
import com.aliyun.credentials.models.Config;

Config credentialConfig = new Config();
credentialConfig.setType("oidc_role_arn");
credentialConfig.setRoleArn(System.getenv("ALIBABA_CLOUD_ROLE_ARN"));
credentialConfig.setOidcProviderArn(
        System.getenv("ALIBABA_CLOUD_OIDC_PROVIDER_ARN"));
credentialConfig.setOidcTokenFilePath(
        System.getenv("ALIBABA_CLOUD_OIDC_TOKEN_FILE"));

Client credentialClient = new Client(credentialConfig);
~~~

This snippet demonstrates how to configure the provider. In Spring Boot, place it in a singleton @Bean. The OIDC provider automatically calls AssumeRoleWithOIDC and refreshes STS credentials. Never print the token file contents or credential values to logs.

## 7. Manual AssumeRole and When to Use It

### 7.1. RAM User AccessKey → RAM Role Flow

For a system outside Alibaba Cloud that does not yet support OIDC, the Credentials tool can use a RAM user's AccessKey as the source credential and then assume a role:

~~~java
import com.aliyun.credentials.Client;
import com.aliyun.credentials.models.Config;

Config credentialConfig = new Config();
credentialConfig.setType("ram_role_arn");
credentialConfig.setAccessKeyId(System.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID"));
credentialConfig.setAccessKeySecret(System.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET"));
credentialConfig.setRoleArn(System.getenv("ALIBABA_CLOUD_ROLE_ARN"));
credentialConfig.setRoleSessionName("invoice-worker");
credentialConfig.setRoleSessionExpiration(3600);

Client credentialClient = new Client(credentialConfig);
~~~

The source credentials need the **sts:AssumeRole** permission and the target role must trust that principal. The Credentials tool will call STS and cache/refresh the role credentials via its supported mechanism. If the environment already provides an ECS role or OIDC, do not create a source AccessKey just to run this snippet.

### 7.2. When to Use STS Tokens Directly?

Short-lived STS credentials can be issued to a mobile/browser client to upload directly to OSS, or for a temporary task. You must enforce these limits:

- The role only has permissions on the required bucket/prefix.
- A session policy further narrows permissions for the session when appropriate.
- The duration is short and tailored to the task.
- The token is never stored in local storage/logs or transmitted over insecure channels.
- The client has no permissions to call administrative APIs beyond its needs.

For file uploads/downloads, signed URLs may be simpler when only a single specific operation needs authorization. If using STS, the backend must manage token issuance and avoid issuing overly broad tokens.

### 7.3. Avoid Static STS Credentials in Long-Running Applications

The **sts** provider type takes an existing AccessKeyId, AccessKeySecret, and SecurityToken. Once the token expires, the application must have logic to fetch a new token and update the client. Do not initialize static STS credentials at startup and let a service run indefinitely.

Prefer self-refreshing providers such as RAM role ARN, ECS RAM role, OIDC role ARN, or Credentials URI. These providers cache tokens and refresh them upon expiration; the ECS role provider even proactively refreshes before expiration.

## 8. Security and Operations

### 8.1. Least Privilege

- Create one role per workload or group of workloads sharing the same responsibility.
- Grant only necessary actions and specific resource ARNs/prefixes.
- Separate read, write, administrative, and deployment roles when responsibilities differ.
- Narrow trust policies to the exact account, role, service, or OIDC subject required.
- Use session policies to further reduce permissions for a single assumption if needed.
- Set meaningful RoleSessionName values for ActionTrail traceability.

### 8.2. Protecting Credentials and Metadata

- Never hardcode AccessKeys/STS tokens in source code, Docker images, committed YAML, or logs.
- Never use the root AccessKey.
- Use RAM roles/short-lived STS for workloads on Alibaba Cloud.
- Protect IMDS against SSRF and restrict metadata access from untrusted processes.
- On ECS, prefer IMDSv2/security-hardened mode per the Credentials tool docs.
- On ACK, never mount a ServiceAccount's OIDC token into containers that do not need those permissions.
- If a long-lived AccessKey is exposed, disable/rotate it immediately, inspect ActionTrail, and assess potentially accessed resources.

### 8.3. Never Log Authentication Secrets

You may log diagnostic details such as:

- Region ID and endpoint type (public/VPC), without logging tokens.
- Approved role ARN or role name for logging.
- Request ID, service code, and error code.
- Request timestamp, latency, and retry count.
- Profile/provider name in use, without printing full AccessKey ID/secret or SecurityToken values.

Do not log full request/response payloads if they contain personal data, secret contents, or tokens.

## 9. Testing Region, Endpoint, and STS Configurations

### 9.1. Test Matrix

| Test | Configuration | Expected Result |
| --- | --- | --- |
| Correct region | Resource and API request in the same region | API locates the resource |
| Correct endpoint | Endpoint matches the resource's service and region | Request connects and is processed |
| Public endpoint | Workload has appropriate internet connectivity | Connects to the API |
| VPC endpoint | Workload in the same region/VPC with valid DNS/routing | Request travels over private network |
| Wrong-region endpoint | Using an endpoint from a different region than the resource | Endpoint/resource location error or resource not found |
| RAM role missing permissions | Role lacks the API action being called | Rejected with AccessDenied |
| Invalid trust policy | Principal is not listed in the trust policy | AssumeRole is denied |
| Caller missing sts:AssumeRole | Source identity lacks assume permission | STS denies before issuing a token |
| Expired STS | Static token used past expiration | Request denied; auto-refresh provider should issue a new session |
| Wrong OIDC subject | Token does not match trust policy conditions | AssumeRoleWithOIDC fails |
| Leftover AK env vars | AK env vars set alongside OIDC/ECS role | Default chain may pick AK ahead of the role |

### 9.2. Troubleshooting Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| **InvalidEndpoint / 404** | Wrong product, wrong region, or wrong network path in endpoint | Look up endpoint in product docs/OpenAPI Explorer |
| **The bucket must be addressed using the specified endpoint** | OSS client sent request to an endpoint not matching the bucket's region | Use the endpoint for the bucket's location |
| **AccessDenied** on API call | Role lacks action/resource permission or policy condition does not match | Check runtime principal and access policy |
| **AssumeRole denied** | Caller lacks sts:AssumeRole or trust policy does not trust caller | Check both policies on the source and target role |
| **InvalidAccessKeyId** | Wrong or disabled AccessKey, or SDK picked an unintended credential | Check credential source and RAM user status |
| **InvalidSecurityToken / token expired** | Missing SecurityToken or expired token | Supply all three STS fields and enable an auto-refresh provider |
| **SignatureDoesNotMatch** | Wrong secret, mismatched endpoint/region/signature config, or clock skew | Check credentials, endpoint, region, and system clock |
| **OIDC AssumeRoleWithOIDC failure** | Wrong provider ARN, role ARN, token file, issuer/audience/subject, or trust condition | Check RRSA, ServiceAccount, and trust policy |
| **ECS metadata timeout** | Role not attached, metadata blocked, or incompatible security mode | Check instance role, IMDS, and credentials-java version |
| **Credential provider not refreshing** | Using static STS credentials or recreating providers repeatedly | Use a singleton auto-refreshing provider |

### 9.3. Ordered Investigation Runbook

1. Identify which service the application is calling and which region the resource resides in.
2. Verify the endpoint matches the product, region, and network path.
3. Determine which credential provider is actually selected; watch out for higher-priority environment variables.
4. Check the active principal/role ARN without logging secrets.
5. If assuming a role, verify the caller's sts:AssumeRole permission and the target role's trust policy.
6. Check the role's access policy for the API action and resource.
7. Check STS Expiration and the auto-refresh provider.
8. Record RequestId/ErrorCode and inspect corresponding logs/audit trails.

Do not fix issues by granting Administrator permissions or swapping endpoints randomly. Pinpoint the exact failing layer: network, endpoint, identity, trust, permission, or expiration.

## 10. Hands-on Exercise

**Exercise:** Deploy a Spring Boot service on ECS to read ECS metadata and upload invoices to OSS using a RAM role and STS.

1. Pick a test region, create an OSS bucket, and launch an ECS instance in an appropriate region.
2. Create a RAM role for ECS whose trust policy allows the ECS service to assume the role.
3. Attach an access policy restricting object uploads to the test bucket/prefix.
4. Attach the role to the ECS instance; do not configure static AccessKeys in the environment.
5. Configure ECS and OSS endpoints matching the region/network.
6. Add Alibaba Cloud Credentials tool and SDK V2 product dependencies.
7. Create a singleton credential client and singleton product clients in the Spring context.
8. Call a read-only ECS API to verify identity and endpoint connectivity.
9. Upload a test file to OSS and confirm the object is created.
10. Temporarily remove upload permissions, point to a wrong endpoint, and let credentials expire to observe errors and auto-refresh behavior.
11. If deploying on ACK, repeat using RRSA/OIDC and compare trust policies.

**Review Questions:**

1. How do Region ID and endpoint differ?
2. Why do OSS endpoints follow a different convention from ECS endpoints?
3. When should you use a public endpoint versus a VPC endpoint?
4. How does a RAM role differ from a RAM user in credential lifecycle?
5. What are the responsibilities of a trust policy versus an access policy?
6. Why does AssumeRole require checking both the caller's permissions and the target role's trust policy?
7. What fields make up STS credentials and why is SecurityToken mandatory?
8. What is the default lifetime of an STS token? What determines its minimum and maximum limits?
9. Why should ECS/ACK workloads use a RAM role or OIDC instead of static AccessKeys?
10. Under what circumstances can the default credential chain accidentally pick a static AccessKey?
11. Why are a singleton Credentials client and an auto-refreshing provider necessary?
12. When encountering SignatureDoesNotMatch or AccessDenied, which layer should be checked first?

## 11. References

- [Alibaba Cloud SDK — Manage credentials (Java V2)](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-manage-access-credentials): credential types, default chain, ECS roles, OIDC, and auto-refresh.
- [RAM — RAM role overview](https://www.alibabacloud.com/help/en/ram/user-guide/ram-role-overview): principals, trust policies, role sessions, and permission policies.
- [RAM — Assume a RAM role](https://www.alibabacloud.com/help/en/ram/user-guide/assume-a-ram-role): AssumeRole, caller permissions, trust policies, and session duration.
- [STS overview](https://www.alibabacloud.com/help/en/ram/user-guide/what-is-sts): temporary credentials, role assumption, and session policies.
- [Alibaba Cloud SDK — Configure endpoints](https://www.alibabacloud.com/help/en/sdk/developer-reference/endpoint-configuration): public/VPC endpoints and Java SDK V2 configuration.
- [OpenAPI — Endpoint types](https://www.alibabacloud.com/help/en/openapi/endpoints): centralized, regional, and VPC endpoints.
- [OSS — Regions and endpoints](https://www.alibabacloud.com/help/en/oss/user-guide/regions-and-endpoints): region IDs, public/internal endpoints, and network paths.
- [OSS — Access OSS via endpoints and bucket domains](https://www.alibabacloud.com/help/en/oss/user-guide/access-oss-via-bucket-domain-name): Region ID, Dedicated Region ID, endpoints, and bucket domains.
- [ECS — Attach an instance RAM role](https://www.alibabacloud.com/help/en/ecs/user-guide/attach-an-instance-ram-role-to-an-ecs-instance): RAM roles, metadata, and STS credentials.
- [ECS — Java SDK V2 examples](https://www.alibabacloud.com/help/en/ecs/developer-reference/use-sdk-for-java): Maven dependencies, client initialization, and DescribeInstances sample.

**Expected Outcome:** Learners properly configure regions and endpoints for their resources, understand RAM roles/trust policies/access policies, use short-lived self-refreshing STS credentials, and integrate safely with Spring Boot on local workstations, ECS, ACK, or environments outside Alibaba Cloud.
