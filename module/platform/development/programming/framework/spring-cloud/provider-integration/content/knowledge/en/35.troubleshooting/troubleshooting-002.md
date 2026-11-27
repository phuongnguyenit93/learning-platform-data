# Identity not found or wrong account, tenant, or project selected

A Spring Boot application may successfully connect to a cloud endpoint yet still be denied access, or a request may succeed while running under an unexpected account. This error commonly occurs when an SDK automatically selects credentials from multiple sources: environment variables, CLI profiles, workload identity, managed identity, service accounts, or metadata servers.

When integrating AWS, Azure, and Google Cloud in the same application, you must determine two independent things for every request:

- **Which identity is signing the request?** For example, an AWS IAM role, a Microsoft Entra service principal/managed identity, or a Google service account/federated principal.
- **Which resource and scope is the request targeting?** For example, an AWS account and region, an Azure tenant/subscription/resource, or a Google Cloud project and resource name.

Selecting the right project or subscription does not automatically change the identity. Authenticating with the right service account does not automatically select the right project containing a bucket or topic either. This article guides you through tracing the actual credential source, verifying the principal, fixing account/tenant/project configuration, and distinguishing authentication errors from authorization errors.

## 1. Distinguishing identity from resource context

| Provider | Authentication identity | Resource selection context | Example |
| --- | --- | --- | --- |
| AWS | IAM user, IAM role, assumed role session, or web identity | AWS account, region, ARN/resource ID | Role `orders-runtime` in account `123456789012`; bucket in `ap-southeast-1` |
| Azure | Microsoft Entra user, service principal, managed identity, or federated workload identity | Tenant, subscription, resource group, resource ID, and Azure cloud | Managed identity in tenant A; Storage Account in subscription B |
| Google Cloud | User, service account, or federated principal | Project ID/number, folder/organization, and resource name | Service account of project `app-prod` writing an object to a bucket in `archive-prod` |

These concepts are related but not interchangeable:

- **AWS account ID** identifies the account owning the IAM principal or resource. **Region** specifies the service location; a region is not an identity.
- **Azure tenant ID** identifies the Microsoft Entra directory where the principal is authenticated. **Subscription ID** defines the Azure resource management scope; one tenant can have multiple subscriptions.
- **Google Cloud Project ID** identifies the project context of an API or resource. **Principal** comes from credentials; the project ID does not decide which account signs the request.
- **Full resource name** can explicitly point to a different project/account/resource than the application's default project.
- **Quota/billing project** can differ from the project owning the resource and also does not change the principal.

When receiving a 403 error, record both the actual principal and the target resource. When data is written to the wrong account/project, inspect both the credential source and the resource identifier.

## 2. General diagnostic workflow in Spring Boot

Follow these steps in order to avoid changing credentials when the bug is actually in the resource context:

1. Identify the service client raising the error: AWS S3/SQS, Azure Blob/Service Bus, or Google Cloud Storage/Pub/Sub.
2. Identify the injected bean/client, qualifier name, active profile, and active properties.
3. Identify the credential provider used by the client: default chain, explicit credentials, CLI credentials, managed identity, or workload identity.
4. Verify the principal using the provider's own tools or APIs.
5. Verify the account/tenant/project/subscription and region/resource name.
6. If both principal and resource are correct, check IAM/RBAC/data-plane permissions, API enablement, endpoints, and networking.
7. Repeat the check in the exact runtime environment of the application: the same container, pod, VM, service definition, and environment variables.

A CLI command run on a developer's machine does not prove the Java process is using the same credentials. The application may receive different environment variables from the IDE, Docker Compose, Kubernetes, systemd, CI/CD, or deployment platform.

## 3. AWS: determining which IAM principal SDK for Java 2.x is using

### 3.1. Default Credentials Provider Chain order

AWS SDK for Java 2.x uses `DefaultCredentialsProvider` when a client does not specify a custom credentials provider. The chain searches for credentials in this order:

1. Java system properties: `aws.accessKeyId`, `aws.secretAccessKey`, `aws.sessionToken`.
2. Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`.
3. Web identity token: `AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_ROLE_ARN`, and optional session name.
4. Shared credentials/config files via the profile provider.
5. ECS container credentials endpoint.
6. EC2 instance profile via the Instance Metadata Service (IMDS).

The first provider that finds valid credentials terminates the search. Therefore, leftover environment variables from a local machine or CI can cause the application to use a different IAM user/role instead of the intended task role or EC2 instance role.

For example: a container runs on ECS with the `orders-runtime` task role, but the Docker image or task definition still passes `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. The SDK will find the environment variables before the ECS container credentials and use the identity from that key pair.

### 3.2. Verifying identity with AWS STS

Run in the exact environment and profile you want to check:

```bash
aws configure list
aws sts get-caller-identity
```

If using a specific profile:

```bash
aws configure list --profile orders-prod
aws sts get-caller-identity --profile orders-prod
```

`aws configure list` shows the profile, region, and source of each configuration value. Access keys are partially masked; do not share output containing sensitive information.

`aws sts get-caller-identity` returns:

- `Account`: the caller's AWS account.
- `Arn`: the ARN of the IAM user or role session.
- `UserId`: the caller identifier.

For example, the ARN might be `arn:aws:sts::123456789012:assumed-role/orders-runtime/session-name`. An `assumed-role` ARN indicates the request is using a role session; verify the account ID and role name against the expected environment.

The `GetCallerIdentity` API requires no standard IAM permissions to return caller details. This is a useful check before investigating resource access permissions.

To verify the exact credential provider your Java client uses, you can call STS using the exact provider passed into the client:

```java
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

AwsCredentialsProvider credentialsProvider =
        DefaultCredentialsProvider.create();

try (StsClient sts = StsClient.builder()
        .region(Region.US_EAST_1)
        .credentialsProvider(credentialsProvider)
        .build()) {
    GetCallerIdentityResponse caller = sts.getCallerIdentity();
    System.out.printf("AWS caller account=%s arn=%s%n",
            caller.account(), caller.arn());
}
```

If the S3 client uses a different explicit provider, pass that exact provider into the STS client. This example requires the AWS SDK STS module at the same version as the rest of your AWS SDK modules. Only log the account/ARN when needed for diagnostics; never log credentials or session tokens.

### 3.3. Checking credential sources taking unintended precedence

Inspect environment variable names without printing secret values:

```bash
env | cut -d= -f1 | grep -E '^(AWS_PROFILE|AWS_REGION|AWS_DEFAULT_REGION|AWS_ACCESS_KEY_ID|AWS_WEB_IDENTITY_TOKEN_FILE|AWS_ROLE_ARN|AWS_CONTAINER_CREDENTIALS_RELATIVE_URI)$'
```

On Windows PowerShell:

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -in @('AWS_PROFILE','AWS_REGION','AWS_DEFAULT_REGION','AWS_ACCESS_KEY_ID','AWS_WEB_IDENTITY_TOKEN_FILE','AWS_ROLE_ARN') } | Select-Object -ExpandProperty Name
```

Merely seeing that `AWS_ACCESS_KEY_ID` is set is enough to investigate whether static credentials are being injected; there is no need to print or transmit the secret key. If the application needs an ECS task role, EC2 instance profile, or EKS web identity, remove unnecessary static credentials from the deployment configuration.

`AWS_PROFILE` selects a profile when the SDK reaches the profile provider in the chain. It does not guarantee the profile will override higher-precedence credential sources such as Java system properties or environment credentials. When testing a profile, pass the same `--profile` to the AWS CLI and ensure the Java process has no higher-priority credential sources.

### 3.4. Region is a separate setting

Credentials determine the IAM principal; region selects the service endpoint. You can check the region currently used by the CLI with:

```bash
aws configure list
aws configure list --profile orders-prod
```

In Spring Cloud AWS, static region configuration can be set per the release line, for example:

```yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
```

When manually constructing an SDK client, specify the region explicitly:

```java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3Client = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build();
```

If accessing a bucket in another region, verify the bucket's region and API endpoint/redirects. Do not swap IAM roles just to fix a region mismatch error.

### 3.5. Distinguishing identity, trust policy, and resource policy

- **Credentials provider** locates the identity used by the SDK.
- **AssumeRole trust policy** determines which principals are permitted to assume a role.
- **Identity policy** grants permissions for a role/user to call services.
- **Resource policy** on a bucket/queue/key can allow or deny a principal.
- **SCP, permission boundary, and session policy** can restrict effective permissions.

If STS returns the right ARN but S3 returns AccessDenied, the identity is already confirmed; check the bucket policy, IAM policy, KMS key policy, SCP, and data-plane permissions. If STS returns a different account/role, fix the credential chain first.

## 4. Azure: determining tenant, principal, and subscription

### 4.1. DefaultAzureCredential selects credentials via a chain

Azure Identity Java provides `DefaultAzureCredential`, a chain comprising multiple authentication sources. Per current documentation, the default chain attempts the following in order:

1. `EnvironmentCredential`.
2. `WorkloadIdentityCredential`.
3. `ManagedIdentityCredential`.
4. `IntelliJCredential`.
5. `VisualStudioCodeCredential` when the required broker component is installed.
6. `AzureCliCredential`.
7. `AzurePowerShellCredential`.
8. `AzureDeveloperCliCredential`.
9. Broker credential if the broker dependency is installed.

The order and available credentials depend on the `azure-identity` version and builder configuration. The chain stops as soon as one credential acquires a token. A valid token does not guarantee that principal has permissions on the Storage Account or Service Bus being called.

A common scenario: a dev machine already has `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_CLIENT_SECRET` set for an old service principal. `EnvironmentCredential` comes before Managed Identity and Azure CLI, so Java may keep using that service principal even though you just ran `az login` with another account.

### 4.2. Checking Azure CLI tenant and subscription

View the default subscription and tenant:

```bash
az account show --query "{tenantId:tenantId, subscriptionId:id, subscriptionName:name, user:user.name}" --output json
```

List subscriptions accessible to the current account:

```bash
az account list --all --output table
```

Log in to the desired tenant:

```bash
az login --tenant TENANT_ID
```

Select a specific subscription for Azure CLI commands:

```bash
az account set --subscription SUBSCRIPTION_ID
az account show
```

`az account set` changes the Azure CLI's default subscription. It does not change the tenant or principal of a credential constructed explicitly in Java, and it does not grant permissions on resources.

If a newly granted subscription has not appeared yet, refresh the CLI session by logging in again and checking subscription access. If the subscription still does not appear, verify whether the subscription belongs to the tenant the account is signed into and whether the account holds an appropriate role.

### 4.3. Checking EnvironmentCredential and Workload Identity

Inspect environment variable names without printing secrets:

```bash
env | cut -d= -f1 | grep -E '^(AZURE_TENANT_ID|AZURE_CLIENT_ID|AZURE_CLIENT_SECRET|AZURE_CLIENT_CERTIFICATE_PATH|AZURE_FEDERATED_TOKEN_FILE)$'
```

On Windows PowerShell:

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -in @('AZURE_TENANT_ID','AZURE_CLIENT_ID','AZURE_CLIENT_SECRET','AZURE_CLIENT_CERTIFICATE_PATH','AZURE_FEDERATED_TOKEN_FILE') } | Select-Object -ExpandProperty Name
```

These variables can configure a service principal or workload identity. If running on an Azure VM/App Service/Container Apps with managed identity, ensure no leftover service principal environment variables stop the chain before managed identity.

With AKS Workload Identity, verify that `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_FEDERATED_TOKEN_FILE` point to the correct tenant, application/user-assigned identity, and pod projected token file. Verify that the federated identity credential on the Entra application/managed identity has its subject and audience matching the Kubernetes ServiceAccount.

### 4.4. Selecting the right managed identity

Azure has system-assigned and user-assigned managed identities:

- **System-assigned:** lifecycle is tied to the Azure resource; when the resource is deleted, the identity is also deleted.
- **User-assigned:** a standalone resource that can be attached to multiple Azure resources; applications typically select it by Client ID.

If a VM or App Service has multiple user-assigned identities, merely enabling managed identity generally may not be enough to identify which identity to use. You can configure the client ID explicitly.

Java example selecting a user-assigned managed identity:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String managedIdentityClientId = System.getenv("AZURE_CLIENT_ID");

TokenCredential credential = new ManagedIdentityCredentialBuilder()
        .clientId(managedIdentityClientId)
        .build();
```

This is an explicit credential. If using Spring Cloud Azure, the corresponding global properties may look like:

```yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID
      profile:
        tenant-id: AZURE_TENANT_ID
        subscription-id: AZURE_SUBSCRIPTION_ID
```

`client-id` takes its meaning from the chosen credential type; in managed identity configuration, it selects the user-assigned identity. `tenant-id` selects the tenant for tenant-scoped authentication flows. `subscription-id` sets the subscription context for integrations needing Azure Resource Manager. They are not interchangeable values.

### 4.5. Enabling logging to see which credential the chain selected

In local or staging environments, enable logging for Azure Identity:

```yaml
logging:
  level:
    com.azure.identity: DEBUG
```

Logs can show whether `EnvironmentCredential`, `WorkloadIdentityCredential`, `ManagedIdentityCredential`, or `AzureCliCredential` was tried and which credential acquired a token. Do not enable sensitive body/header logging in production; never write access tokens to logs.

In supported `azure-identity` versions, `AZURE_TOKEN_CREDENTIALS` can be used to restrict the credential group or specify a particular credential. Supported values and minimum versions are documented in the Azure Identity Java documentation. Do not set this variable based on an example from another version without checking the running dependency.

### 4.6. Tenant, subscription, and data-plane RBAC

An access token carries a specific issuer/tenant and principal. An Azure subscription is a resource management scope. For example:

- Azure Resource Manager may require a subscription ID to look up or manage resources.
- Blob Storage requires data-plane permissions such as Storage Blob Data Reader/Contributor on the account/container.
- Service Bus requires an appropriate data-plane role such as Azure Service Bus Data Sender/Receiver.
- Key Vault requires data-plane permissions matching either the access policy model or Azure RBAC.

Having subscription Contributor does not automatically grant permission to read blob contents or send messages over Service Bus. If a token is acquired but the API returns 403, check the tenant, principal object ID, role assignment scope, and control-plane vs. data-plane role type.

## 5. Google Cloud: distinguishing gcloud CLI, ADC, and project

### 5.1. ADC searches for credentials in order

Google Cloud Client Libraries use Application Default Credentials (ADC). The current search order is:

1. The `GOOGLE_APPLICATION_CREDENTIALS` environment variable.
2. The ADC file created by `gcloud auth application-default login`.
3. The service account attached to the runtime, retrieved via the metadata server.

If `GOOGLE_APPLICATION_CREDENTIALS` points to an old JSON file, ADC uses that file ahead of both the local ADC file and the attached service account. This frequently causes Cloud Run/GCE/GKE workloads to run under a different identity than the expected service account.

`GOOGLE_APPLICATION_CREDENTIALS` can point to a Workload Identity Federation/Workforce Identity Federation credential configuration or a service account key. Avoid long-lived service account keys when workload identity or an attached service account meets your requirements.

### 5.2. gcloud CLI account is not the ADC identity

These commands check which identity Google Cloud CLI is using:

```bash
gcloud auth list
gcloud config list
gcloud config get-value account
```

Select an already-authenticated CLI account:

```bash
gcloud config set account developer@example.com
```

However, Google Cloud Client Libraries use ADC. ADC is configured separately:

```bash
gcloud auth application-default login
```

These two credential sets are independent. `gcloud auth list` may show user A active in the CLI while the Java application uses user B's ADC or service account impersonation.

If you want local Java execution to use service account impersonation, you can create ADC with:

```bash
gcloud auth application-default login --impersonate-service-account=orders-runtime@provider-integration-prod.iam.gserviceaccount.com
```

The signed-in user needs permission to impersonate the target service account. This ADC still remains separate from the active account of `gcloud` CLI.

### 5.3. Default project does not change the principal

Check the project currently used in gcloud configuration:

```bash
gcloud config get-value project
gcloud config list
```

Change the default project of gcloud CLI:

```bash
gcloud config set project provider-integration-prod
```

In Spring Framework on Google Cloud, the default project can be set with:

```yaml
spring:
  cloud:
    gcp:
      project-id: provider-integration-prod
```

Or via an environment variable:

```bash
export GOOGLE_CLOUD_PROJECT="provider-integration-prod"
```

`gcloud config set project` changes the gcloud CLI's default project; it does not automatically change `spring.cloud.gcp.project-id`, full resource names, or the ADC principal. A service account in project A can still access a bucket in project B if IAM policy allows it.

When publishing to Pub/Sub, a full resource name explicitly specifies the project owning the topic:

```text
projects/messaging-prod/topics/orders-created
```

If the topic resides in a different project from the default project, check both the topic name and the IAM bindings on that topic. Do not change credentials simply because the request targets a different project.

### 5.4. Verifying the runtime service account

On Cloud Run, Compute Engine, or GKE, identify the service account attached to the workload:

- Cloud Run: check the service account of the revision serving traffic.
- Compute Engine: check the service account attached to the VM and access scopes if still applicable.
- GKE: check the Kubernetes ServiceAccount, Workload Identity Federation for GKE, and bindings to the Google service account if impersonation is used.
- Workloads outside Google Cloud: check whether `GOOGLE_APPLICATION_CREDENTIALS` points to an external account credential configuration with the correct pool/provider.

To verify the principal actually making API calls, inspect Cloud Audit Logs for the target resource/service. Fields such as `principalEmail` or `principalSubject` help verify which identity made the request. Do not log access tokens to try to identify the principal.

## 6. Configuring Spring Boot when one application uses multiple cloud providers

An application may have an AWS client, an Azure client, and a Google Cloud client. Each client needs its own credential source and resource context. Never pass a credential object from one provider into another provider's SDK.

Example environment-based configuration:

```yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
    azure:
      credential:
        managed-identity-enabled: false
        client-id: USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID
      profile:
        tenant-id: AZURE_TENANT_ID
        subscription-id: AZURE_SUBSCRIPTION_ID
    gcp:
      project-id: provider-integration-dev

app:
  cloud:
    azure:
      blob-endpoint: https://ordersarchive.blob.core.windows.net
    aws:
      bucket: orders-archive
    gcp:
      bucket: orders-archive
```

These properties select the region, tenant, subscription, project, and endpoint. They do not contain secret credentials. Identities still come from the AWS provider chain, Azure credential chain, and Google ADC.

If you need to create custom clients, use explicit bean names/qualifiers:

```java
@Configuration
public class CloudClientConfiguration {

    @Bean("ordersS3Client")
    S3Client ordersS3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }

    @Bean("ordersBlobClient")
    BlobServiceClient ordersBlobClient() {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint("https://ordersarchive.blob.core.windows.net")
                .credential(credential)
                .buildClient();
    }

    @Bean("ordersGcsClient")
    Storage ordersGcsClient() throws IOException {
        return StorageOptions.newBuilder()
                .setProjectId("provider-integration-dev")
                .build()
                .getService();
    }
}
```

This example applies when the application manages clients manually. If a starter already creates a default client, avoid accidentally declaring a duplicate bean of the same type; use `@Qualifier` to inject the intended client. In this example, the Google Cloud client uses ADC, the Azure client uses `DefaultAzureCredential`, and the AWS client uses `DefaultCredentialsProvider`.

Example injecting specific clients:

```java
@Service
public class CloudArchiveService {

    private final S3Client s3Client;
    private final BlobServiceClient blobServiceClient;
    private final Storage storage;

    public CloudArchiveService(
            @Qualifier("ordersS3Client") S3Client s3Client,
            @Qualifier("ordersBlobClient") BlobServiceClient blobServiceClient,
            @Qualifier("ordersGcsClient") Storage storage) {
        this.s3Client = s3Client;
        this.blobServiceClient = blobServiceClient;
        this.storage = storage;
    }
}
```

In production, prefer an AWS task/instance role or web identity, Azure managed/workload identity, and a Google attached service account/WIF. Do not put static keys, client secrets, or service account JSON files into container images or source control just to make three clients share a configuration.

## 7. Distinguishing authentication, authorization, and resource context

| Stage | Question | Error signs |
| --- | --- | --- |
| Credential discovery | Can the SDK find credentials? | AWS `Unable to load credentials`; Azure `CredentialUnavailableException`; Google no credentials found |
| Authentication | Does the identity provider issue a token/credentials? | Invalid client secret, expired token, tenant mismatch, STS assume-role failure |
| Identity selection | Which principal was actually selected? | STS ARN, Entra principal, or Audit Log differs from expectations |
| Resource context | Does the request target the right account/project/subscription/region? | Resource not found, wrong region, wrong project, subscription/resource ID mismatch |
| Authorization | Does the principal have permissions on the resource? | `AccessDenied`, `AuthorizationPermissionMismatch`, `PERMISSION_DENIED`, HTTP 403 |
| Network/endpoint | Can the client reach the right endpoint? | DNS, TLS, timeout, private endpoint, or proxy failure |

Common scenarios:

- AWS `GetCallerIdentity` returns the right role, but S3 returns `AccessDenied`: check IAM/resource policies, KMS, SCP, and the bucket's account.
- Azure `DefaultAzureCredential` obtains a token successfully, but Blob returns 403: check the tenant/principal and Storage Blob Data role on the right account/container.
- Google ADC obtains credentials successfully, but Pub/Sub returns `PERMISSION_DENIED`: check the principal and Publisher role on the topic in the right project.
- Resource not found: verify account/project/region/resource name before changing IAM.
- Credentials not found: check the chain, environment variables, and metadata endpoint before modifying resource roles.

## 8. Symptom-based troubleshooting table

| Symptom | Possible cause | How to check and fix |
| --- | --- | --- |
| AWS uses IAM user instead of EC2/ECS role | System property or environment credentials took precedence | Check `aws.accessKeyId`, `AWS_ACCESS_KEY_ID`; remove old static sources if unneeded |
| AWS uses wrong account locally | Wrong default profile or `AWS_PROFILE`; environment credentials override profile | Run `aws configure list` and `aws sts get-caller-identity` with the expected profile |
| AWS SDK reports no credentials found | No valid profile, web identity, container credentials, or instance role | Read the full provider chain error; check IMDS/ECS endpoint and role attachment |
| AWS assume role denied | Wrong trust policy, source identity, or external ID | Check role ARN, trust relationship, source credentials, and `sts:AssumeRole` |
| AWS calls wrong region | `AWS_REGION`, profile region, or client configuration override | Check `aws configure list` and the region passed into the builder |
| Azure gets token from Azure CLI user instead of managed identity | Environment/workload identity did not match or managed identity unavailable; chain fell through to CLI | Enable `com.azure.identity` `DEBUG` and identify which credential returned the token |
| Azure uses wrong service principal | Old `AZURE_CLIENT_ID`/`TENANT_ID`/`CLIENT_SECRET` still present | Check environment variables; remove unused configuration and re-verify the chain |
| Azure cannot find subscription | CLI signed into wrong tenant or user has not been granted the subscription | Run `az account show`, `az account list`, log in to the right tenant, then select the subscription |
| Azure acquires right token, but Blob/Service Bus returns 403 | Missing data-plane RBAC or role granted at a different scope | Check principal object ID, role assignment, and resource scope |
| Azure uses wrong user-assigned identity | Multiple managed identities exist, but client ID is not specified | Set the desired identity's client ID in the credential builder/property |
| Google uses old user locally | `GOOGLE_APPLICATION_CREDENTIALS` or stale ADC file took precedence | Check env var, re-run ADC setup, and verify principal via audit logs |
| Google uses service account key instead of attached identity | Env var points to JSON key | Remove key file from runtime and use attached service account/WIF |
| Google CLI has right account, but Java has wrong account | `gcloud` CLI credentials differ from ADC | Run `gcloud auth application-default login` for local ADC; inspect ADC source separately |
| Google calls wrong project | Wrong `spring.cloud.gcp.project-id`, `GOOGLE_CLOUD_PROJECT`, or resource name | Check default project and full resource name |
| Google project is right, but returns 403 | Principal lacks role on resource or another project | Check Audit Logs and IAM policy on the bucket/topic/secret |
| Multiple cloud clients share one credentials bean | Shared configuration or incorrect bean override | Create separate credential/client beans and qualify them by provider |
| Works locally, but deployed runtime uses wrong identity | Local machine has CLI credentials or different env from runtime | Inspect directly inside the container/pod/service runtime and audit logs |
| After credential rotation, application still uses old identity | Client or process caches old provider/configuration; env not refreshed | Verify credential refresh behavior, restart/roll out as required by the platform |

## 9. Lab: verifying three identities before calling services

Goal: Orders API writes objects to AWS S3, Azure Blob Storage, and Google Cloud Storage. Each provider uses a separate identity; each resource may belong to a different account/project from where the application is deployed.

### Step 1 — Record expected identities

| Provider | Runtime identity | Resource context |
| --- | --- | --- |
| AWS | IAM role `orders-runtime` | Account `123456789012`, bucket `orders-archive`, region `ap-southeast-1` |
| Azure | User-assigned managed identity `orders-runtime` | Tenant `TENANT_ID`, subscription `SUBSCRIPTION_ID`, Storage Account `ordersarchive` |
| Google Cloud | Service account `orders-runtime@provider-integration-prod.iam.gserviceaccount.com` | Project `archive-prod`, bucket `orders-archive` |

These values are examples. Replace them with your actual account ID, tenant, subscription, project, region, and resources.

### Step 2 — Verify the AWS caller

```bash
aws configure list
aws sts get-caller-identity
```

Confirm that `Account` and `Arn` match the expected account/role. If not, inspect Java system properties, environment variables, web identity, profile, and container/instance metadata in exact chain order.

### Step 3 — Verify Azure tenant and subscription

```bash
az account show --query "{tenantId:tenantId, subscriptionId:id, user:user.name}" --output json
az account list --all --output table
```

Select the subscription for resource management if needed:

```bash
az account set --subscription SUBSCRIPTION_ID
```

Then enable Azure Identity logging in the staging application to confirm which credential source actually issues the token. Verify the Client ID of the user-assigned managed identity and the data-plane role on the Storage Account.

### Step 4 — Verify Google ADC and project

```bash
gcloud auth list
gcloud config list
gcloud config get-value project
```

These commands verify the `gcloud` CLI. If Java uses local ADC, verify it separately with:

```bash
gcloud auth application-default login
```

If deployed on Google Cloud, verify the service account attached to the runtime and ensure `GOOGLE_APPLICATION_CREDENTIALS` does not override the expected metadata source. Cross-check the actual principal in Cloud Audit Logs after a test request.

### Step 5 — Verify resources and permissions

- AWS: test writing an object to the right bucket; confirm the bucket policy and IAM role allow the operation.
- Azure: test writing a blob to the right container; confirm the Storage Blob Data Contributor role or a narrower appropriate permission.
- Google Cloud: test writing an object to the right bucket; confirm the Storage Object Creator role on the bucket.

Do not use Owner/Administrator permissions for testing. Use the exact runtime identity and minimum expected permissions of the application.

### Step 6 — Record the results

For each request, record:

- Provider and client bean name.
- Verified principal/account/tenant/project.
- Full resource identifier.
- API result and request/correlation ID.
- Checked IAM/RBAC scope.

Never store access tokens, secret keys, client secrets, or credential file contents in logs or reports.

## 10. Operational principles to avoid selecting the wrong identity

- Separate identities by workload and environment; do not use one admin account for all services.
- Avoid static credentials in environment variables if the platform provides roles, managed identity, workload identity, or attached service accounts.
- Use explicit profiles/credentials when local diagnostics require them; production should have a single clear identity source.
- Remove stale credential environment variables from IDEs, shells, container images, CI variables, and service definitions.
- Configure region, tenant, subscription, project, and resource names via dedicated properties; do not infer them from a principal's email or ARN.
- If an application uses multiple cloud providers, define separate client/credential beans and inject them with `@Qualifier`.
- Enable credential-chain logging in local/staging when needed; never log tokens or secrets.
- Verify the actual identity with STS, Azure Identity diagnostics, and Google Cloud Audit Logs.
- After changing a role, managed identity, WIF binding, or ADC, re-verify both the principal and permissions with a test request.
- Grant permissions at the smallest resource scope; distinguish control-plane from data-plane permissions.

## 11. Key takeaways

- Identity and resource context are two separate settings: an AWS role is not a region; an Azure principal is not a tenant/subscription; a Google service account is not a project.
- AWS SDK for Java 2.x checks system properties, environment variables, web identity, profile, ECS, and EC2 metadata in order. Static variables can shadow a task/instance role.
- `aws sts get-caller-identity` reveals the actual account and ARN; `aws configure list` helps locate the source of region/profile/credentials.
- Azure `DefaultAzureCredential` tries Environment, Workload Identity, Managed Identity, and developer credentials in a chain. The chain stops once a token is acquired, even if that token belongs to an account lacking permissions on the resource.
- `az account set` changes the CLI's default subscription; it does not change the principal of an explicitly created Java credential.
- Spring Cloud Azure has dedicated properties for tenant, subscription, client ID, and managed identity; pick the right tenant/principal first, then inspect data-plane RBAC.
- Google ADC prioritizes `GOOGLE_APPLICATION_CREDENTIALS`, then the local ADC file, and finally the attached service account. An env var pointing to a stale file can shadow the runtime identity.
- `gcloud auth list` and `gcloud config set project` manage the gcloud CLI; Java Cloud Client Libraries use ADC. The two credential sets are not identical.
- `spring.cloud.gcp.project-id` or `GOOGLE_CLOUD_PROJECT` selects the project context; a full resource name can point to a different project without changing the principal.
- When authentication succeeds but the API returns 403, check IAM/RBAC on the resource. When the principal is wrong, fix the credential chain before changing permissions.

## Official reference documentation

1. [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
2. [AWS STS — GetCallerIdentity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html)
3. [AWS CLI — configure list and configuration sources](https://docs.aws.amazon.com/cli/latest/reference/configure/list.html)
4. [Azure Identity Java — Credential chains and DefaultAzureCredential](https://learn.microsoft.com/en-us/azure/developer/java/sdk/authentication/credential-chains)
5. [Azure CLI — sign in and select subscription](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively)
6. [Azure CLI — manage subscriptions](https://learn.microsoft.com/en-us/cli/azure/manage-azure-subscriptions-azure-cli)
7. [Spring Cloud Azure — Global configuration properties](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration-properties-global)
8. [Google Cloud — How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
9. [Google Cloud CLI — Authenticate for the gcloud CLI](https://docs.cloud.google.com/sdk/docs/authenticate)
10. [Google Cloud CLI — gcloud auth list](https://docs.cloud.google.com/sdk/gcloud/reference/auth/list)
11. [Spring Framework on Google Cloud — Core configuration](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/core.html)

Credential chain order and properties depend on the SDK/provider version. When troubleshooting a real application, cross-reference the running dependency version against the corresponding documentation; in particular, inspect environment variables and profiles inside the actual Java process rather than only in an interactive terminal.
