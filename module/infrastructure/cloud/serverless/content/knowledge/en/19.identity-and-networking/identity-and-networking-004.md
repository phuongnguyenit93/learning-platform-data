# Issuing Temporary Credentials Instead of Static Keys

In the **Identity and Networking** chapter, a credential is the proof a workload uses to establish its identity when calling other services. A Java function may need to read objects, write to a database, send messages, retrieve secrets, or call internal APIs. If long-lived access keys and secret keys are embedded in source code or configuration files, every copy, build, or deployment risks exposing access.

A safer approach is to assign an identity to the workload and let the platform issue temporary credentials with a limited permission scope. The credentials have an expiration, can be refreshed through a provider, and do not need to be stored as static secrets in a repository. On AWS, Lambda typically uses an execution role and AWS Security Token Service (STS); on other platforms, equivalent mechanisms include workload identity, managed identity, or federation.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications, especially Java functions triggered by HTTP, messages, or events. Learners handle triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to determine when to use FaaS. Managing temporary credentials is foundational for functions to access services safely as the number of execution environments changes continuously.

## 1. Why Are Static Keys a Risk?

A long-lived access key typically consists of an access key ID and a secret access key. Some services also require a session token if the credential belongs to a temporary session. When using long-lived keys, an application can continue accessing resources until the key is revoked or disabled.

Common risks:

- Keys are accidentally committed to Git or appear in logs.
- Keys are copied into configuration files, images, or deployment artifacts.
- Multiple developers and services share a single key, making it difficult to trace who performed an action.
- Keys hold broader permissions than a single function requires.
- Key rotation requires updating many places and can cause downtime.
- A leaked key can be used from anywhere that satisfies authentication conditions, not necessarily from the original workload.

Putting keys into environment variables does not automatically make them safe. Environment variables can still be read by processes, debuggers, crash dumps, deployment configurations, or anyone with permission to view configuration. If the value is a long-lived key, the risk persists until the key is revoked.

Temporary credentials shorten the useful window of a compromised credential and allow scoping permissions per session. However, if an attacker obtains temporary credentials while they are still valid, they can still exercise that session's permissions. Therefore, short lifetimes must be combined with least privilege, runtime protection, and monitoring.

## 2. What Do Temporary Credentials Contain?

A set of temporary credentials typically includes:

| Component | Role |
|---|---|
| Access key ID or token identifier | Identifies the credential |
| Secret access key or token proof | Proves possession of the credential |
| Session token or bearer token | Carries session information or the issued token |
| Expiration | Timestamp when the credential ceases to be valid |

With AWS STS, credentials typically consist of an access key ID, secret access key, and session token, along with an expiration timestamp. When calling AWS APIs, the SDK must send all required components; having only an access key ID and secret access key is insufficient for session credentials.

Temporary credentials are issued for an identity or an assumed-role session. The lifetime can be configured within the service's and session type's limits. Do not hardcode expiration times or manually store the three credential values in application config.

A time-limited token does not mean all operations are allowed. Credentials establish identity; IAM policies and resource policies determine what that identity is allowed to do on which resources.

## 3. Distinguishing Authentication, Authorization, and Workload Identity

Three questions must be addressed separately:

1. **Authentication:** Who or which workload is calling the service?
2. **Authorization:** Which actions is that identity allowed to perform on which resources?
3. **Credential delivery:** How does the workload obtain and refresh authentication proof?

For example, a Java Lambda may run with an execution role named `OrderFunctionRole`. That role allows reading a prefix in S3 and writing messages to a queue. AWS supplies temporary credentials to the function so the SDK can sign requests. When the SDK calls S3, AWS authenticates the credentials, then evaluates policies to decide whether to allow `GetObject` on the requested object.

Do not confuse the function's credentials with the end user's credentials. The user sends a JWT to the API; the API validates the JWT and establishes an internal principal. Lambda still uses its own execution role to access AWS resources. Both identities can exist within the same request while serving two distinct security boundaries.

## 4. Three Identities to Separate in Serverless

In a system with a deployment pipeline and function runtime, there are usually at least three identities:

| Identity | When used | Example permissions |
|---|---|---|
| Deployment identity | CI/CD creating or updating functions | Push artifacts, update configuration, attach execution roles |
| Workload identity | Running function | Read S3, write DynamoDB, send messages |
| Caller identity | User or service calling the function | Call APIs, access business data per tenant |

The deployment identity should not be used inside the function. A pipeline may have permission to update Lambda and pass an execution role, but the function should receive only the runtime permissions it needs.

The workload identity should not have IAM administrative permissions or permissions to modify its own role unless required by the business domain. The caller identity should not be trusted merely because a request reached the function; the adapter must still authenticate the caller and verify data-level permissions.

~~~mermaid
flowchart TB
    CI["CI/CD identity"] -->|"deploy code / configure role"| L["Lambda function"]
    IAM["IAM trust policy"] -->|"issues temporary credentials"| L
    L -->|"signed API request"| AWS["S3 / Queue / Database"]
    USER["End user token"] --> API["API Gateway / HTTP adapter"]
    API -->|"verified principal"| L
    L -->|"authorization check"| APP["Application use case"]
~~~

Separating these three identities enables audit logs to answer two distinct questions: who deployed the function and what actions the function performed at runtime.

## 5. AWS Lambda IAM Roles and Execution Roles

A Lambda execution role is an IAM role that Lambda assumes when running the function. The role has two key configuration parts:

- **Trust policy:** defines which principal is allowed to assume the role. For an execution role, the trust policy typically allows the Lambda service to assume the role.
- **Permissions policy:** defines which APIs and resources the function is allowed to call.

Sample trust policy:

~~~json
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
~~~

This is an illustrative trust relationship for a role used by the Lambda service. The permission policy is a separate document. For example, if the function only needs to read objects from one bucket prefix, the policy should limit actions and ARNs to that exact scope rather than granting account-wide S3 permissions.

A least-privilege policy might look like:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::company-orders/incoming/*"
    }
  ]
}
~~~

This example does not yet include permissions for logging, KMS decryption, or other dependencies. In an actual deployment, add the exact permissions required for each operation and check resource policies, bucket policies, KMS key policies, and related conditions.

### 5.1. Lambda Execution Role Differs from Resource-Based Policy

The execution role determines what Lambda can do while running. The function's resource-based policy determines which external principals are allowed to invoke the function. For example, API Gateway or an event source may need permission to invoke the function; that does not mean the function has permission to read the database.

Do not use the execution role to describe external invocation permissions. Configure both invoke permissions and runtime permissions properly.

## 6. Lambda Automatically Supplies Temporary Credentials

When a function has an execution role attached, the Lambda service manages assuming the role and supplying temporary credentials to the execution environment. The Java AWS SDK can acquire credentials via the default credentials provider chain.

The application does not need to create long-lived IAM user access keys, copy secrets into source code, or call STS manually to assume its own execution role.

Key principles:

- Attach the execution role when creating or updating the function.
- Grant only necessary runtime permissions.
- Use the AWS SDK default credentials provider chain.
- Do not pass access keys/secret keys into client constructors.
- Do not persist credentials to files or databases.
- Do not log credentials or session tokens.

The SDK's credential provider is responsible for locating the right credential source. The exact delivery mechanism is determined by the runtime and environment; applications should use the SDK abstraction rather than manually reading or assembling environment variables.

## 7. Using AWS SDK for Java 2.x Without Static Keys

When creating an AWS service client, specify the region and let the SDK select the credential provider:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

public final class StorageClients {
    private StorageClients() {
    }

    public static S3Client createS3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

When no credentials provider is specified, AWS SDK for Java 2.x automatically uses the default credentials provider chain. In Lambda, the SDK retrieves credentials from the execution role supplied by the runtime. Locally, the provider chain can locate a developer profile or another configured credential source. No code changes are needed between local and production just to swap access keys.

You can instantiate the client once at the class level to reuse across the execution environment:

~~~java
public final class OrderHandler {
    private static final S3Client S3 =
            StorageClients.createS3Client();

    public OrderResult handle(OrderEvent event) {
        // Use the initialized S3 client.
        return new OrderResult(event.orderId(), "ACCEPTED");
    }
}
~~~

`OrderEvent` and `OrderResult` are illustrative DTO types. Reusing the client avoids reinitializing connections and credential providers on every invocation. SDK service clients are immutable/thread-safe by SDK design; still verify documentation for the specific client and close clients when the application actually terminates if the environment has an explicit shutdown lifecycle.

Do NOT do the following:

~~~java
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

AwsBasicCredentials credentials = AwsBasicCredentials.create(
        "AKIA...",
        "long-lived-secret");

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(
                StaticCredentialsProvider.create(credentials))
        .build();
~~~

The snippet above illustrates an anti-pattern because it embeds static keys in code. `StaticCredentialsProvider` is suitable when an application has fixed credentials intentionally supplied in certain tests or special cases; it should not be used to store temporary credentials while bypassing refresh capabilities.

## 8. Default Credentials Provider Chain

AWS SDK for Java 2.x includes `DefaultCredentialsProvider` to look up credentials from supported sources. Depending on the environment and SDK version, sources may include:

- Java system properties.
- Environment variables.
- Web identity token and role ARN.
- AWS shared profile or credential process.
- Container credential endpoint.
- Instance metadata service.

The SDK uses the provider chain so applications can run across environments without embedding credentials in code. Exact provider ordering and details may vary by SDK version; when strict control is needed, consult documentation for the exact version in use.

Crucially, the default chain does not make a long-lived key safe. If a developer exports long-lived access keys into the environment, the SDK can still use those credentials. The goal is to configure the environment to provide workload identities or temporary credentials, not merely relocate where keys are stored.

On Lambda, the execution role is the runtime identity source. On developer machines, use AWS IAM Identity Center/SSO or an appropriate profile. In CI/CD, prefer OIDC federation or temporary credential mechanisms over IAM user keys.

## 9. Credential Refresh and Execution Environment Lifecycle

Temporary credentials have an expiration timestamp. Applications must ensure requests are signed with valid credentials. When using a refresh-capable provider, the SDK can fetch new credentials according to the provider's mechanism.

Key principles:

- Retain the credential provider rather than holding onto a single resolved credential object.
- Never resolve credentials once and cache the three fields indefinitely.
- Never construct a `StaticCredentialsProvider` from session credentials if refresh is needed.
- Use dedicated SDK providers for `AssumeRole` or Web Identity.
- Handle refresh errors, network timeouts, and clock skew.
- Set bounded timeouts and retries when calling STS or credential endpoints.

In Lambda, an execution environment can be reused across multiple invocations and terminated at any time. Runtime credentials are managed by the platform; applications should not assume a process stays alive long enough to manage its own credential caching or refresh via a background thread that is not guaranteed to run.

### 9.1. Do Not Hold Expired Credentials

A common mistake is calling `resolveCredentials` once during cold start, extracting the access key/secret/session token, and storing them in static fields. Once the credentials expire, subsequent requests can fail with expired token or invalid signature errors.

Instead, pass the provider to the AWS SDK client. The provider knows how to acquire fresh credentials when needed based on its provider type. For STS assume role or web identity, use refresh-supporting providers rather than managing STS call timing manually.

### 9.2. Retries Do Not Replace Refresh

Retrying a request with the same expired credentials usually does not fix the failure. If the error is credential expiration, credentials must be refreshed before retrying. If the error is `AccessDenied`, retries usually will not help because the policy still denies it. Distinguish authentication, authorization, and network errors to avoid infinite retries.

## 10. AssumeRole via AWS STS When Different Permissions Are Needed

A function sometimes needs to access resources in another account or needs a narrower permission set for a specific task. You can use STS `AssumeRole` to obtain temporary credentials for the target role.

Example using AWS SDK for Java 2.x:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;

public final class CrossAccountCredentials implements AutoCloseable {
    private final StsClient stsClient;
    private final StsAssumeRoleCredentialsProvider provider;

    private CrossAccountCredentials(
            StsClient stsClient,
            StsAssumeRoleCredentialsProvider provider) {
        this.stsClient = stsClient;
        this.provider = provider;
    }

    public static CrossAccountCredentials create() {
        StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();

        AssumeRoleRequest request = AssumeRoleRequest.builder()
                .roleArn("arn:aws:iam::123456789012:role/ReadReportsRole")
                .roleSessionName("reports-reader")
                .build();

        StsAssumeRoleCredentialsProvider provider =
                StsAssumeRoleCredentialsProvider.builder()
                .stsClient(sts)
                .refreshRequest(request)
                .build();

        return new CrossAccountCredentials(sts, provider);
    }

    public AwsCredentialsProvider provider() {
        return provider;
    }

    @Override
    public void close() {
        provider.close();
        stsClient.close();
    }
}
~~~

This is a skeleton example. The source role must have `sts:AssumeRole` permission on the target role, and the target role's trust policy must trust the source role. Keep `CrossAccountCredentials` alive alongside the service client using the provider; call `close` when the application shuts down. In Lambda, you can initialize the resource holder and service client once per execution environment for reuse, then close them if the runtime provides a shutdown hook. Do not create a new client/provider pair on every invocation.

Never assume a role just because a request sends a role ARN. Target roles must be fixed or loaded from trusted configuration, and policies must restrict resources. Never let end clients choose arbitrary roles.

### 10.1. Trust Policy and Permission Policy

`AssumeRole` requires mutual agreement:

- The caller policy allows the source principal to call `sts:AssumeRole` on the target role.
- The target role's trust policy allows the source principal to assume the role.

Next, the target role's permissions policy determines what the session is allowed to do. Missing permission or mismatched trust on either side will cause STS to deny the request.

When a third party is allowed to assume a role in your account, an external ID in the trust condition may be required to mitigate confused deputy risks. The external ID must be issued and verified per the integration contract; never take arbitrary values from public requests.

### 10.2. Session Policy and Session Tags

`AssumeRole` can accept a session policy to narrow a session's permissions and session tags to support attribute-based access control (ABAC) when resource policies use tags. A session policy cannot grant permissions beyond the role's own permissions; it can only further restrict effective permissions.

Never pass an unverified user-supplied tenant ID as a session tag. Session tags are part of the authorization context and can alter resource access permissions.

## 11. Workload Identity Federation and OIDC

When a workload runs outside AWS — such as CI/CD, Kubernetes, or another cloud — do not create IAM user keys just so the pipeline can call AWS. You can use OpenID Connect (OIDC) or a federation mechanism to exchange an external identity token for temporary AWS credentials.

Conceptual flow:

1. The workload proves its identity to an identity provider.
2. The identity provider issues an OIDC token containing issuer, audience, and subject.
3. The workload sends the token to STS.
4. STS verifies the trust policy and token conditions.
5. STS issues temporary credentials for the IAM role.
6. The AWS SDK uses those credentials to call services.

~~~mermaid
sequenceDiagram
    participant W as CI/CD or workload
    participant IDP as OIDC Identity Provider
    participant STS as AWS STS
    participant S as AWS Service
    W->>IDP: Request identity token
    IDP-->>W: Short-lived OIDC token
    W->>STS: AssumeRoleWithWebIdentity
    STS->>STS: Validate issuer, audience, subject
    STS-->>W: Temporary role credentials
    W->>S: Signed API request
    S-->>W: Result per IAM policy
~~~

The trust policy should constrain the specific issuer, audience, and subject. For example, a pipeline is only allowed to assume a role from a specific repository and branch; do not allow every token from the same identity provider to assume the role.

### 11.1. Java SDK Using a Web Identity Token

AWS SDK for Java 2.x supports the web identity token credentials provider. When the environment provides a role ARN and token file following conventions supported by the SDK, `DefaultCredentialsProvider` can select this provider.

It can also be configured explicitly:

~~~java
import software.amazon.awssdk.auth.credentials.WebIdentityTokenFileCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.regions.Region;

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(
                WebIdentityTokenFileCredentialsProvider.create())
        .build();
~~~

The provider reads the token file and exchanges the token for temporary credentials per environment configuration. Do not manually read the token and print it to logs or include it in artifacts. Verify the SDK version and the configuration variables supplied by your runtime/OIDC integration.

### 11.2. Constraining Trust by Claims

An OIDC trust policy should constrain at minimum:

- Issuer matching the registered identity provider.
- Audience matching the service receiving the token.
- Subject matching the exact repository, branch, workflow, namespace, or service account.
- Additional claims if required by the workflow.

Do not use broad wildcards such as all repositories or all namespaces when only one workload needs access. When changing branches or service accounts, update the trust policy in a controlled manner.

## 12. Workload Identity in Kubernetes

In Kubernetes, pods need to access cloud APIs. The legacy approach stored access keys in a Kubernetes Secret and mounted them into containers. That approach still creates long-lived keys, requires rotation, and can be read by workloads or anyone with access to the secret.

On EKS, IAM Roles for Service Accounts (IRSA) allows binding an IAM role to a Kubernetes service account via OIDC. The pod receives a web identity token and the AWS SDK exchanges that token for temporary credentials.

On Kubernetes on other platforms, use workload identity federation or an appropriate credential broker. General principles:

- Each workload or service account has its own identity.
- Tokens have restricted audience and subject.
- Roles hold only necessary permissions.
- Do not share one broad credential across the entire cluster.
- Pods must not access tokens of other service accounts.
- Disable automounting service account tokens if the workload does not need them.

Do not confuse a Kubernetes service account with an IAM role. A service account defines identity inside the cluster; federation maps that identity to a cloud principal.

## 13. Equivalents on Google Cloud and Azure

The workload identity concept is not unique to AWS. Cloud providers offer mechanisms to issue short-lived credentials to workloads.

| Platform | Common mechanism | Java integration |
|---|---|---|
| AWS Lambda | IAM execution role, STS | AWS SDK default credentials provider |
| Google Cloud Functions/Cloud Run | Workload-attached service account, metadata server, Application Default Credentials | Google Auth Library |
| External to Google Cloud | Workload Identity Federation | Application Default Credentials with federation config |
| Azure Functions/App Service | Managed Identity | Azure Identity SDK |
| External to Azure | Workload identity federation/service principal federation | Azure Identity SDK |

### 13.1. Google Cloud Application Default Credentials

On Google Cloud, workloads can run with a service account attached to the runtime. Google client libraries use Application Default Credentials (ADC) to locate suitable credentials, typically via the metadata server inside Google Cloud environments.

Java example:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

GoogleCredentials credentials =
        GoogleCredentials.getApplicationDefault();

Storage storage = StorageOptions.newBuilder()
        .setCredentials(credentials)
        .build()
        .getService();
~~~

Locally, ADC can use the credentials of a developer signed in with Google Cloud tools. In production, attach a least-privilege service account or use Workload Identity Federation instead of long-lived JSON key files.

Never package a service account JSON key into a JAR, container image, or source repository. If an organization mandates a key in an exceptional case, manage it in a secret manager, restrict permissions, and enforce clear rotation.

### 13.2. Azure Managed Identity

On Azure, Managed Identity gives resources a platform-managed identity. The Java SDK can use Azure Identity to obtain tokens without storing client secrets in the application.

Example:

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

DefaultAzureCredential credential =
        new DefaultAzureCredentialBuilder().build();

BlobServiceClient blobClient =
        new BlobServiceClientBuilder()
                .endpoint("https://example.blob.core.windows.net")
                .credential(credential)
                .buildClient();
~~~

`DefaultAzureCredential` supports multiple credential sources based on environment, including developer and managed identity sources. In production, explicitly control which identity is selected; if you want to use only managed identity, configure `ManagedIdentityCredential` accordingly. Data access permissions are granted via Azure RBAC or the appropriate service mechanism.

## 14. End-User Credentials Differ from Workload Identity

A Java function can both use a workload identity to call AWS and process user requests carrying a JWT. These two credential types must not be mixed.

Example:

- The client sends an access token to API Gateway.
- API Gateway or the function validates the token and creates a principal.
- The application checks whether the principal has permission to operate on `orderId` and `tenant`.
- The function uses its execution role to write data or emit events.

Never take a user's token and use it as AWS credentials. Likewise, never use the function's execution role to infer that the end user has permission to access all data the function can read.

If cloud resources must be accessed on behalf of the user, design delegated authorization or token exchange per a mechanism supported by the cloud provider, with explicit audience, scope, and policy. Never forward a bearer token to a service that is not the token's audience.

## 15. Least Privilege and Scoping Credentials

Temporary credentials can still be dangerous if the role holds overly broad permissions. Least privilege is the principle of granting only the right actions, on the right resources, under the right conditions, for the required duration.

Best practices:

- Separate roles by function or clearly bounded functional group.
- Restrict Actions and Resources.
- Use conditions on tags, encryption context, source ARN, or network when appropriate.
- Avoid wildcards on administrative actions.
- Separate read and write permissions.
- Limit role assumption and role chaining.
- Use session policies to narrow permissions when needed.
- Audit permissions based on CloudTrail and actual usage.

A single role shared across dozens of functions allows a compromise in one function to impact the entire group. When a function only needs to read objects, it should not use a role permitted to delete buckets or modify IAM policies.

### 15.1. Deployment Permissions Differ from Runtime Permissions

Pipelines typically need permission to update functions and `iam:PassRole` to attach execution roles to Lambda. `PassRole` permission must be restricted to the exact approved roles. Do not grant the pipeline permission to pass any role in the account.

Execution roles should not have permission to update code or alter trust policies. Separating deployment permissions from runtime permissions limits the impact when a credential is exposed.

## 16. Network Path to Credential-Issuing Services

Credential providers may need to connect to endpoints to exchange tokens or refresh sessions. Network policies therefore directly affect the ability to obtain credentials.

With AWS:

- STS has regional endpoints and a global endpoint; select the endpoint based on Region configuration and organizational policy.
- Workloads in private subnets may need NAT or an appropriate VPC interface endpoint to call STS.
- Web identity federation requires reaching STS and a securely mounted token file.
- Container credential endpoints or metadata endpoints must be properly reachable by the SDK.
- DNS, route tables, security groups, and network ACLs can cause requests to endpoints to fail.

Not every credential refresh in Lambda requires the function to call STS directly. When Lambda provides an execution role, the platform manages runtime credentials. Only configure network paths to STS when the application or SDK explicitly needs to call STS, such as `AssumeRole` or Web Identity inside the workload.

If a function is attached to a VPC, do not assume it has internet access by default. A function in a private subnet typically needs a NAT gateway or VPC endpoint to reach external services. Distinguish endpoints for AWS services from endpoints for third-party identity providers.

## 17. Handling Credential Errors and Triaging Incidents

Common errors:

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Unable to load credentials | No credential source found | Check execution role, provider chain, and environment |
| ExpiredToken | Session credentials expired | Use a refresh-capable provider, check clock and lifecycle |
| InvalidClientTokenId | Wrong or no longer valid credentials | Verify credential source and account |
| SignatureDoesNotMatch | Wrong secret/token, request canonicalization, or clock skew | Check provider, system clock, and request signing |
| AccessDenied | Valid credentials but disallowed by policy | Check IAM, resource policy, SCP, and permissions boundary |
| STS timeout | Unreachable endpoint or blocked network | Check DNS, routes, NAT/VPC endpoint, and timeout |
| AssumeRole denied | Trust policy or caller policy mismatch | Check principal, action, conditions, and role ARN |

Do not retry `AccessDenied` or misconfigured trust policies indefinitely. Those are usually configuration or permission errors. For transient network errors, use bounded retries with backoff. For expired credentials, let the provider refresh credentials and retry within SDK capabilities.

Never write credentials or tokens to logs while investigating. You may log provider type, sanitized role ARN, AWS request ID, operation, and error code. Avoid logging full exception messages if they contain URLs or sensitive details.

## 18. Safely Verifying Runtime Identity

During debugging, you may need to know which role a function is running under. AWS STS `GetCallerIdentity` returns the account, ARN, and user ID of the current caller. This is a way to verify the selected identity, not a way to grant additional permissions.

It can be called in test environments or during controlled startup:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

try (StsClient sts = StsClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build()) {

    GetCallerIdentityResponse identity =
            sts.getCallerIdentity();

    System.out.println("Account: " + identity.account());
    System.out.println("Arn: " + identity.arn());
}
~~~

This example prints only non-secret identity metadata. Do not call `GetCallerIdentity` on every invocation unnecessarily since it is still a network request. In production, verified role/ARN information can be logged at startup or via controlled diagnostics.

## 19. Protecting Tokens and Credentials in Applications

Temporary credentials must still be protected as secrets. Principles:

- Never write access keys, secrets, session tokens, or bearer tokens to logs.
- Never return credentials in HTTP responses or messages.
- Never serialize credentials into business DTOs.
- Never persist credentials in a database as long-lived state.
- Never bake token files into images or artifacts.
- Restrict read permissions on process environment and filesystem.
- Use TLS to protect credentials in transit over the network.
- Restrict debug endpoints or heap dumps in production.
- Remove credentials from test fixtures before committing.
- Use a secret manager for secrets that genuinely must persist long-term, such as legacy passwords or third-party private keys.

Do not self-encrypt a long-lived key and store it next to the application as if that eliminates risk. If the application can decrypt the key, an attacker who compromises the same runtime or decryption permission can retrieve the key as well.

## 20. Local Testing, CI/CD, and Production

Each environment requires an appropriate credential source:

| Environment | Recommended Approach |
|---|---|
| Developer workstation | IAM Identity Center/SSO or limited-privilege developer profile |
| Unit tests | Fake client/provider or stub, no real cloud keys required |
| Integration tests | Temporary role or dedicated sandbox account |
| CI/CD | OIDC federation or temporary credentials |
| AWS Lambda production | Execution role |
| Google Cloud runtime | Service account/workload identity and ADC |
| Azure runtime | Managed Identity |

Never copy production keys onto a laptop for debugging. If production data access is necessary, use a break-glass workflow or an approved, time-bounded, audited role.

Unit tests can inject a fake provider:

~~~java
import software.amazon.awssdk.auth.credentials.AwsCredentials;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;

public final class TestCredentialsProvider
        implements AwsCredentialsProvider {

    @Override
    public AwsCredentials resolveCredentials() {
        return AwsBasicCredentials.create(
                "test-access-key",
                "test-secret-key");
    }
}
~~~

Use fake credentials only in tests and ensure they have no access to real cloud resources. For tests using session credentials, use fake `AwsSessionCredentials` with a dummy session token; never put real production tokens into tests.

## 21. Migrating from Static Keys to Workload Identity

A safe migration plan may include:

1. Inventory where long-lived access keys are currently used: source code, environments, CI secrets, config files, container images, and secret stores.
2. Identify which actions and resources each workload actually requires.
3. Create dedicated roles or workload identities with least privilege.
4. Configure trust relationships for Lambda, OIDC providers, service accounts, or managed identities.
5. Update code to use the SDK default credential provider or a refresh-capable provider.
6. Deploy to a test environment and verify caller identity.
7. Test both allowed and denied operations.
8. Roll out gradually to production, monitoring `AccessDenied` and refresh errors.
9. Revoke old static keys after confirming no workloads remain dependent on them.
10. Audit repositories, CI history, and artifacts to remove exposed credential copies.

If a key was ever committed or shared, deleting the file from the current branch is not enough. You must rotate or revoke the credential because copies may remain in Git history, logs, caches, or artifacts.

## 22. Common Mistakes

**Putting access keys in source code:** Keys can be committed or packaged. Use workload identities and SDK providers.

**Putting keys in environment variables and assuming they are safe:** Environment variables still store long-lived credentials. Migrate to runtime-issued temporary credentials.

**Using an IAM user for Lambda:** Creates unnecessary long-lived keys. Attach an execution role to the function.

**Using one overly broad role for many functions:** One compromised function can affect many resources. Separate roles and restrict permissions.

**Confusing trust policy with permissions policy:** A role can be assumed without permission to call APIs, or vice versa. Verify both sides.

**Storing resolved credentials in static fields:** Credentials expire while the app keeps using stale values. Retain a refresh-capable credential provider.

**Calling AssumeRole on every invocation:** Increases latency and STS load. Assume roles only when a distinct permission boundary is needed; reuse providers/clients over the proper lifecycle.

**Trusting a role ARN from a request:** Clients could ask to assume a different role. Target roles must come from trusted configuration and restricted policies.

**Failing to provide a network route to STS:** The provider needs to call STS, yet the function in a private subnet has no route. Configure NAT or an appropriate VPC endpoint.

**Retrying AccessDenied continuously:** Policy errors do not resolve on their own. Classify errors and fix permissions/trust policies.

**Logging tokens for debugging:** Logs can become a credential leak vector. Log only error codes, request IDs, and non-sensitive metadata.

**Not revoking old keys:** The workload has migrated, yet long-lived keys remain active. Revoke them and check usage locations.

## 23. Pre-Production Checklist

- [ ] Function has its own execution role or workload identity.
- [ ] Deployment identity, workload identity, and caller identity are separated.
- [ ] Trust policy allows only the right service or workload to assume the role.
- [ ] Permissions policy grants only necessary actions and resources.
- [ ] Java SDK uses `DefaultCredentialsProvider` or an appropriate provider.
- [ ] No long-lived access keys exist in source, artifacts, or images.
- [ ] Credential providers are reused and support refresh.
- [ ] Resolved credentials are not cached past expiration.
- [ ] `AssumeRole`/OIDC has trust conditions restricting issuer, audience, and subject.
- [ ] Session policies or session tags are used properly if needed.
- [ ] Runtime role lacks deployment or IAM modification permissions unless required.
- [ ] Network connectivity to STS/metadata/identity endpoints is properly configured.
- [ ] Credentials, tokens, and session secrets are never logged.
- [ ] Authentication, authorization, and network errors are classified separately.
- [ ] Positive and negative permission tests exist.
- [ ] CloudTrail or equivalent auditing is enabled to trace actions.
- [ ] Old static keys have been revoked after migration.
- [ ] Developers and CI/CD use temporary identities instead of production keys.

## Conclusion

Temporary credentials allow workloads to prove their identity without storing long-lived keys in code or artifacts. On AWS Lambda, execution roles combined with STS and AWS SDK credential providers are standard; OIDC federation fits external workloads and CI/CD. Google Cloud ADC/workload identity and Azure Managed Identity apply the same principle on their respective platforms.

For secure implementation, separate deployment identity, workload identity, and caller identity; restrict trust policies and permissions policies; use refresh-capable providers; ensure network paths to required endpoints; and never log credentials. Short-lived credentials reduce the exposure window, while least privilege, identity controls, and auditing remain mandatory layers of defense.
