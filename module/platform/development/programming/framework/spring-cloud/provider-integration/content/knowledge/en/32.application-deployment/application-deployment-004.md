# Assigning Identities to Applications on VMs, Containers, and Kubernetes

A Spring Boot application often needs to access multiple managed services: reading objects from S3 or Cloud Storage, writing to Blob Storage, sending messages to Service Bus, SQS, or Pub/Sub, or reading secrets from Key Vault or Secret Manager. For those operations to be permitted, the application must hold an identity recognized by the cloud provider with appropriate permissions on the target resources.

On virtual machines, the identity is typically attached to the VM or instance. For containers, an identity can be attached individually to each task or service. On Kubernetes, a Pod uses a Kubernetes ServiceAccount, and the platform binds that identity to an IAM role, Managed Identity, or Google Cloud service account. When properly configured, the application obtains short-lived credentials from the runtime environment and the SDK refreshes tokens automatically. There is no need to package access keys, client secrets, or service account keys inside the JAR or image.

This lesson belongs to the **Application Deployment** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module provides hands-on practice integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on assigning identities to workloads on VMs, containers, and Kubernetes, establishing trust relationships, granting least-privilege permissions, and using Java SDK credential providers in Spring Boot.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between user identity, workload identity, Kubernetes ServiceAccount, and cloud service accounts.
- Explain the relationship between authentication, authorization, principal, role, and resource scope.
- Assign IAM roles to Amazon EC2, ECS tasks, and EKS Pods, and choose between IRSA and EKS Pod Identity.
- Use system-assigned or user-assigned Managed Identities on Azure VMs and container platforms.
- Configure Microsoft Entra Workload ID for Pods on AKS using OIDC federation.
- Attach service accounts to Compute Engine VMs and Cloud Run services.
- Configure Workload Identity Federation for GKE for Kubernetes workloads.
- Use the AWS SDK credential provider chain, Azure Identity, and Google Application Default Credentials.
- Separate permissions for nodes, agents, deployment identities, and application workloads.
- Protect metadata endpoints, projected tokens, and federated trust.
- Test identities, role assignments, token refresh, and data plane access permissions.

## 2. Identity, Credentials, and Permissions Are Three Separate Concepts

These concepts are related but not interchangeable:

- **Identity/principal:** an identity recognized by the cloud provider, such as an IAM role, Managed Identity, or service account.
- **Credential:** proof demonstrating that a workload represents that principal, such as temporary AWS credentials, a Microsoft Entra access token, or a Google OAuth access token.
- **Authentication:** verifying which principal a credential belongs to.
- **Authorization:** deciding which actions a principal may perform on which resources.
- **Role/policy:** a collection of permissions assigned to a principal or used in a trust relationship.
- **Trust relationship:** defines who or which workload is allowed to assume or receive an identity.

Consider a Spring Boot consumer reading messages from Azure Service Bus:

1. The Pod runs under a Kubernetes ServiceAccount named `orders-consumer`.
2. AKS issues a projected OIDC token for the ServiceAccount.
3. Microsoft Entra ID validates the token's issuer, subject, and audience against a federated identity credential.
4. Entra ID issues an access token for the linked Managed Identity.
5. Service Bus evaluates Azure RBAC for that identity.
6. Only if the identity holds the proper data-plane role can the consumer receive messages.

Holding a valid token does not guarantee permission to read a queue. Conversely, assigning a role to an identity does not help the application if the runtime cannot obtain credentials for that identity.

### 2.1. Distinguishing Operator Identities from Workload Identities

| Identity Type | Used For | Examples |
|---|---|---|
| Human identity | Developers, operators, administrators signing in and taking actions | Microsoft Entra user, AWS IAM Identity Center user, Google user |
| CI/CD identity | Pipelines creating resources or deploying applications | OIDC federated role, service principal, deployment service account |
| Node identity | Agents or components running on the VM/node | EC2 instance profile, VM Managed Identity, GKE node service account |
| Workload identity | A specific application or workload | ECS task role, EKS Pod role, AKS Workload ID, Cloud Run service identity |
| Kubernetes identity | Authenticating with the Kubernetes API and attached to Pods | Kubernetes ServiceAccount |

Never use a developer's user account as a production identity. Never assign an identity with infrastructure admin permissions to Spring Boot merely because the pipeline already has that credential available.

## 3. Architecture for Assigning Workload Identities

~~~mermaid
flowchart TD
    subgraph PLATFORM["Cloud / Kubernetes platform"]
        PROVISION["Create identity and trust"]
        ROLE["Grant least-privilege role"]
        TOKEN["Issue or expose short-lived credential"]
    end
    subgraph APP["Spring Boot workload"]
        POD["VM process / container / Pod"]
        SDK["Java SDK credential provider"]
        CLIENT["Service client"]
    end
    RESOURCE["Managed resource: storage / messaging / database"]
    PROVISION --> ROLE
    ROLE --> TOKEN
    TOKEN --> SDK
    POD --> SDK
    SDK --> CLIENT
    CLIENT --> RESOURCE
    ROLE --> RESOURCE
~~~

General workflow:

1. Create a dedicated principal for the workload or service.
2. Establish trust so only the intended compute resource or OIDC subject can assume the identity.
3. Assign roles on the exact resources and scopes needed.
4. Attach the identity to the VM, task, service, or Kubernetes ServiceAccount.
5. Initialize SDK clients using the appropriate credential provider.
6. Verify permissions using real data-plane operations.
7. Monitor authentication/authorization errors and token lifecycles.

The provisioner needs permissions to create identities and role assignments. The workload only needs permissions to obtain its own credentials and call data services. Never grant the workload permissions to create roles or modify trust policies.

## 4. Identity Scope Across Runtime Environments

| Runtime Environment | Where Identity Is Attached | Typical Permission Scope |
|---|---|---|
| VM/EC2/Compute Engine | Instance profile, Managed Identity, attached service account | Usually applies to processes on the same VM |
| Container on ECS/Fargate | Task role | Per individual task |
| Container on Azure Container Apps | Container app/revision Managed Identity | Per container app or selected identity |
| Cloud Run | Service identity | Per Cloud Run service/job |
| EKS | IAM role linked to Kubernetes ServiceAccount via IRSA or Pod Identity | Per ServiceAccount/Pod |
| AKS | Microsoft Entra Workload ID linked to ServiceAccount | Per ServiceAccount/Pod |
| GKE | Workload Identity Federation for GKE | Per Kubernetes ServiceAccount or linked IAM service account |

Key point to remember: **a Kubernetes ServiceAccount is not automatically an IAM role or an Azure Managed Identity.** It is an identity inside Kubernetes. The cloud provider requires federation or association configuration to map the ServiceAccount to a cloud principal.

## 5. AWS: IAM Roles for Applications on Amazon EC2

### 5.1. Instance Profiles

On Amazon EC2, applications receive permissions through an IAM role attached to an instance profile. An EC2 instance profile is the container for an IAM role attached to an instance. AWS SDK for Java 2.x can retrieve temporary credentials from the EC2 Instance Metadata Service without any access keys in configuration files.

Minimum trust policy for an EC2 role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

After creating the role, attach a policy allowing the application to operate only on the required bucket. Example policy to read objects under a specific prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::orders-production/incoming/*"
    }
  ]
}
~~~

If the application needs to list objects, add `s3:ListBucket` on the bucket ARN and restrict the prefix using an appropriate condition. Never grant `s3:*` across all buckets just for testing.

Attach the role to the EC2 instance via an instance profile using IaC or your provisioning workflow. The application never needs to know an access key or secret key. When credentials approach expiration, the SDK fetches fresh credentials from the metadata service.

An EC2 instance attaches only one instance profile role at a time; processes on that VM can use that same role. If multiple applications on the same VM require different permission sets, split workloads into separate compute boundaries or use a container service with per-task roles. Do not treat containers running on EC2 as a sufficient security boundary to prevent access to host metadata.

### 5.2. Protecting the Instance Metadata Service

The metadata endpoint can issue temporary credentials for the instance role. If an application has an SSRF vulnerability or an untrusted container can reach metadata, credentials can be abused.

For production EC2:

- Enforce IMDSv2 with `HttpTokens=required`.
- Disable IMDS if the workload does not need metadata.
- Restrict the permissions of the instance role.
- Do not let untrusted containers access host metadata credentials.
- For containers on EC2, verify hop limit and network isolation; a hop limit of 1 may prevent some containers from receiving IMDSv2 responses, though increasing it to 2 does not replace access isolation.
- Monitor `MetadataNoToken` before migrating legacy instances to required IMDSv2.

Example Launch Template metadata options:

~~~yaml
MetadataOptions:
  HttpEndpoint: enabled
  HttpTokens: required
  HttpPutResponseHopLimit: 2
~~~

A hop limit of 2 is a setting often considered when containers on EC2 must reach IMDSv2. Enable it only according to a tested architecture; never widen the hop limit arbitrarily.

## 6. AWS: Distinguishing ECS Task Role and Execution Role

ECS has two roles that are frequently confused:

- **Task execution role:** used by the ECS agent to pull images from ECR, push logs via the `awslogs` driver, and fetch secrets referenced in the task definition.
- **Task role:** credentials provided to the code running inside the container to call AWS APIs such as S3, SQS, or DynamoDB.

The task definition has two separate fields:

~~~json
{
  "family": "orders-api",
  "taskRoleArn": "arn:aws:iam::111122223333:role/orders-runtime-role",
  "executionRoleArn": "arn:aws:iam::111122223333:role/orders-task-execution-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:1.0.0",
      "essential": true
    }
  ]
}
~~~

If the application calls S3, `s3:GetObject` belongs to the task role. Pulling images and writing logs belong to the execution role. Do not add business permissions to the execution role because the application container does not use that role for business calls.

With ECS on EC2, the container instance role serves the ECS agent/instance; the task role remains the identity for the application container. With Fargate, there are no user-managed EC2 workers, yet task role and execution role remain two distinct concepts.

## 7. AWS EKS: IAM Roles for Service Accounts (IRSA)

IRSA links an IAM role to a Kubernetes ServiceAccount via OIDC federation.

How it works:

1. The EKS cluster has an OIDC issuer.
2. IAM has an OIDC identity provider matching that issuer.
3. The IAM role trust policy allows tokens with a specific audience and subject to assume the role.
4. The Kubernetes ServiceAccount is annotated with the role ARN.
5. The Pod specifies the corresponding `serviceAccountName`.
6. EKS injects a projected token and required environment variables.
7. The AWS SDK uses the web identity token to call STS `AssumeRoleWithWebIdentity` and receive temporary credentials.

### 7.1. Trust Policy Scoped to the Exact Namespace and ServiceAccount

Example IRSA trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDC"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDC:aud": "sts.amazonaws.com",
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDC:sub": "system:serviceaccount:orders:orders-api"
        }
      }
    }
  ]
}
~~~

The `sub` condition binds the role specifically to the `orders-api` ServiceAccount in the `orders` namespace. Do not use wildcards for namespaces or ServiceAccounts unless workloads genuinely need to share an identity.

### 7.2. Kubernetes ServiceAccount and Deployment

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/orders-runtime-role
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
~~~

The role policy determines what the application can do; the trust policy determines which workload can assume the role. Both are required. Annotating a ServiceAccount does not automatically grant S3 access if the IAM policy lacks that permission.

## 8. AWS EKS Pod Identity

EKS Pod Identity is a different mechanism from IRSA. EKS creates an association between a cluster, namespace, Kubernetes ServiceAccount, and IAM role. The EKS Pod Identity Agent on the node delivers credentials to the Pod. You do not need to add a role ARN annotation to the ServiceAccount as in IRSA.

The trust policy for a Pod Identity role uses a service principal:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "pods.eks.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ],
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/kubernetes-namespace": "orders",
          "aws:RequestTag/kubernetes-service-account": "orders-api"
        }
      }
    }
  ]
}
~~~

Create the association via the AWS CLI:

~~~bash
aws eks create-pod-identity-association \
  --cluster-name orders-prod \
  --namespace orders \
  --service-account orders-api \
  --role-arn arn:aws:iam::111122223333:role/orders-runtime-role
~~~

The Pod still specifies the ServiceAccount:

~~~yaml
spec:
  serviceAccountName: orders-api
~~~

Points to verify:

- The EKS Pod Identity Agent must be installed on the cluster, except in environments like EKS Auto Mode where it is built in.
- The IAM role needs a trust policy for `pods.eks.amazonaws.com`.
- The association must target the exact cluster, namespace, and ServiceAccount.
- The principal creating the association needs `iam:PassRole` permission for the attached IAM role.
- The AWS SDK version must support this credential mechanism and use the default credential provider chain.
- Cross-account access may require role chaining or dedicated delegation configuration; a basic association attaches a role in the same account as the cluster.

### 8.1. Choosing IRSA vs. EKS Pod Identity

| Criterion | IRSA | EKS Pod Identity |
|---|---|---|
| Federation | Cluster OIDC provider and STS AssumeRoleWithWebIdentity | EKS Auth service and Pod Identity Agent |
| ServiceAccount configuration | Role ARN annotation | No role annotation needed |
| Node component | Projected OIDC token | Pod Identity Agent |
| Trust policy | Federated OIDC principal, subject, and audience | Service principal `pods.eks.amazonaws.com` |
| Scope | Each ServiceAccount linked to a role | Association by cluster/namespace/ServiceAccount |
| SDK | Supports web identity provider | Default provider chain supports container credentials |
| Best fit | Widely used OIDC mechanism, broad compatibility | Centralized association management on EKS |

Do not arbitrarily configure both mechanisms simultaneously for the same workload. Pick one mechanism, verify the SDK version, and test actual credentials inside the Pod.

## 9. Azure: Managed Identity on VMs and Container Services

Azure Managed Identity is an identity managed by Microsoft Entra for an Azure resource. The application retrieves short-lived access tokens; Azure manages the underlying credentials and rotation.

There are two types:

| Type | Lifecycle | When Suitable |
|---|---|---|
| System-assigned | Created with the resource; deleted when the resource is deleted | A single VM or app with its own dedicated identity |
| User-assigned | Standalone identity resource that can be attached to multiple resources | Multiple instances need the same principal or identity lifecycle must be independent |

If you share a user-assigned identity across multiple VMs/containers, every workload attached to that identity receives the exact same set of permissions. Share only when that blast radius is acceptable.

### 9.1. Assigning Data-Plane Roles

For example, a VM needs to write to Blob Storage. Assign the `Storage Blob Data Contributor` role to the Managed Identity's principal at the appropriate storage account or container scope:

~~~bash
az role assignment create \
  --assignee-object-id MANAGED_IDENTITY_PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/SUBSCRIPTION_ID/resourceGroups/RG_NAME/providers/Microsoft.Storage/storageAccounts/ORDERS_STORAGE
~~~

This is a data-plane role for blob operations. The `Contributor` role on a resource group is an Azure Resource Manager management role and is not a substitute for reading/writing blobs.

Similarly:
- `Key Vault Secrets User` for applications that only read secrets.
- `Azure Service Bus Data Receiver` for consumers.
- `Azure Service Bus Data Sender` for publishers.
- `Azure Event Hubs Data Receiver` or `Data Sender` matching consumer/publisher roles.

Choose roles based on actual operations and limit resource scope.

### 9.2. Token Endpoint on Azure VMs

Azure Instance Metadata Service provides a Managed Identity endpoint. Direct REST requests require the `Metadata: true` header to mitigate SSRF risks:

~~~bash
curl "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F" \
  -H Metadata:true
~~~

Java applications generally do not call this endpoint over HTTP manually. The Azure Identity SDK handles token acquisition, caching, and refresh. Never log access tokens or responses containing tokens.

If a VM has multiple user-assigned identities, the credential must select the identity by client ID or resource ID. Never let the SDK pick a default identity ambiguously when a VM has multiple principals attached.

### 9.3. Azure Container Apps

Azure Container Apps supports both system-assigned and user-assigned Managed Identities. The platform provides an identity endpoint along with a protective header inside the container's environment. The Azure Identity SDK can use the corresponding credential; do not write a custom HTTP client to fetch tokens when the SDK already supports the platform.

With a user-assigned identity, configure the identity attached to the Container App and select the matching client ID when creating the credential. Do not pass a client secret just to replace Managed Identity.

Example enabling system-assigned identity:

~~~bash
az containerapp identity assign \
  --name orders-api \
  --resource-group rg-orders-prod \
  --system-assigned
~~~

Retrieve the principal ID from the command output to create Azure RBAC role assignments on target resources. If using a user-assigned identity, create the standalone identity first and then attach its resource ID to the Container App.

## 10. Azure AKS: Microsoft Entra Workload ID

AKS Workload ID uses OIDC federation to map a Kubernetes ServiceAccount to a user-assigned Managed Identity or a Microsoft Entra application. This is the mechanism for Pod identities, distinct from node or cluster control plane identities.

Flow:

1. Enable OIDC issuer and Workload Identity on AKS.
2. Retrieve the cluster's issuer URL.
3. Create a user-assigned Managed Identity.
4. Create a federated identity credential with issuer, subject, and audience.
5. Assign Azure RBAC data-plane roles to the Managed Identity.
6. Annotate the Kubernetes ServiceAccount with the client ID.
7. Add the required label to the Pod template.
8. The Azure workload identity webhook injects a projected token and environment variables.
9. The Azure Identity SDK uses `WorkloadIdentityCredential` to exchange the token for an access token.

### 10.1. Federated Identity Credential

The subject must match exactly:

~~~text
system:serviceaccount:orders:orders-api
~~~

The standard audience is:

~~~text
api://AzureADTokenExchange
~~~

Create the federated credential with the Azure CLI:

~~~bash
az identity federated-credential create \
  --name orders-api-federation \
  --identity-name orders-api-identity \
  --resource-group rg-orders-prod \
  --issuer AKS_OIDC_ISSUER_URL \
  --subject system:serviceaccount:orders:orders-api \
  --audiences api://AzureADTokenExchange
~~~

Replace the issuer URL with the cluster's actual OIDC issuer. The federated credential only allows exchanging the token for the identity; it does not automatically grant permission to read Key Vault or send Service Bus messages. Roles must be assigned separately to the Managed Identity.

### 10.2. ServiceAccount and Pod Manifest

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "USER_ASSIGNED_IDENTITY_CLIENT_ID"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
~~~

The `azure.workload.identity/use: "true"` label is required for the webhook to mutate the Pod and inject workload identity configuration. If you update the ServiceAccount annotation, restart Pods for the new configuration to take effect.

### 10.3. Java Credential for AKS Workload ID

Azure Identity provides `WorkloadIdentityCredential`. Inside the Pod, the webhook provides environment variables such as `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_FEDERATED_TOKEN_FILE`.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.WorkloadIdentityCredential;
import com.azure.identity.WorkloadIdentityCredentialBuilder;

class AzureWorkloadCredentialFactory {

    static TokenCredential create() {
        return new WorkloadIdentityCredentialBuilder()
                .clientId(System.getenv("AZURE_CLIENT_ID"))
                .tenantId(System.getenv("AZURE_TENANT_ID"))
                .tokenFilePath(System.getenv("AZURE_FEDERATED_TOKEN_FILE"))
                .build();
    }
}
~~~

This snippet is intended for Pods configured with Microsoft Entra Workload ID. When running on Azure VMs or Container Apps using Managed Identity, select `ManagedIdentityCredential` or an appropriate credential chain instead of `WorkloadIdentityCredential`.

## 11. Google Cloud: Service Accounts on Compute Engine VMs

A Compute Engine VM can run under a Google Cloud service account attached when creating or updating the VM. Client libraries use Application Default Credentials (ADC) to fetch credentials from the metadata server.

You should create a dedicated user-managed service account for the application instead of using the Compute Engine default service account, which may carry overly broad project-level permissions. Grant the necessary IAM roles to the service account and attach it to the VM.

Example creating a VM with a service account:

~~~bash
gcloud compute instances create orders-worker \
  --zone asia-southeast1-b \
  --service-account orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --scopes https://www.googleapis.com/auth/cloud-platform
~~~

The `cloud-platform` access scope allows the VM to call Google Cloud APIs permitted by the service account's IAM policy. Access scopes do not grant additional IAM permissions; IAM roles still govern permitted actions. This is recommended over relying on narrow OAuth scopes as the primary authorization layer.

For example, a service account that only publishes to a topic should receive `roles/pubsub.publisher` at the topic or project scope per organizational policy. Never grant `Project Editor` to a workload.

Grant publish permission at the topic scope:

~~~bash
gcloud pubsub topics add-iam-policy-binding orders-events \
  --project PROJECT_ID \
  --member "serviceAccount:orders-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --role roles/pubsub.publisher
~~~

## 12. Google Cloud: Service Identity for Cloud Run

A Cloud Run service or job uses a service account as its service identity when calling Google Cloud APIs. Create a dedicated service account for each workload or group of workloads sharing the same permissions.

Deploy Cloud Run with a service account:

~~~bash
gcloud run deploy orders-api \
  --image asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:1.0.0 \
  --region asia-southeast1 \
  --service-account orders-runtime@PROJECT_ID.iam.gserviceaccount.com
~~~

Two permissions must be distinguished:

- The deployer needs permission to attach the service account to the Cloud Run service, typically Service Account User on the chosen service account.
- The service identity needs IAM roles on the resources the application accesses, such as Pub/Sub Publisher or Storage Object Viewer.

The role commonly used by the deployer is `roles/iam.serviceAccountUser` on the attached service account. This role allows the deployer to perform the `actAs` operation; it does not grant publish/read data permissions to the Cloud Run service itself.

Do not grant runtime roles to the deployer merely because the pipeline needs to deploy the service. Do not use the project's default service account when a workload needs its own permission set.

## 13. Google Kubernetes Engine: Workload Identity Federation for GKE

GKE Workload Identity Federation allows Pods to use a Kubernetes ServiceAccount to obtain an IAM identity without service account key files. The GKE metadata server handles credential requests from client libraries and exchanges projected Kubernetes tokens for federated access tokens.

There are two common approaches:

- **Direct resource access:** grant IAM roles directly to the principal representing the Kubernetes ServiceAccount.
- **Impersonate a Google service account:** link the Kubernetes ServiceAccount to a Google service account; grant `roles/iam.workloadIdentityUser` to the KSA on the GSA, then grant resource permissions to the GSA.

Example linking a KSA to a GSA:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:PROJECT_ID.svc.id.goog[orders/orders-api]"
~~~

Annotate the Kubernetes ServiceAccount:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    iam.gke.io/gcp-service-account: orders-runtime@PROJECT_ID.iam.gserviceaccount.com
~~~

Grant publish permission to the Google service account on the target topic, such as `roles/pubsub.publisher`. Then the Pod uses the KSA:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
~~~

Both the IAM policy binding on the GSA and the annotation on the KSA are required when using this linked model. GKE Workload Identity Federation must be enabled on the corresponding cluster/node pool.

Do not use the node's service account as a shared identity for all Pods. If Pods share the node identity, one workload can inherit permissions intended for another.

Pods running with `hostNetwork: true` do not route through the GKE metadata server in the way Workload Identity Federation for GKE expects. Avoid enabling host networking for workloads that need dedicated identities, or evaluate the credential mechanism carefully before deploying.

## 13.1. Dependencies for Java SDK Examples

The code snippets below require the corresponding SDK libraries. Use a BOM managed by your project or Spring Cloud release train to keep versions compatible; do not mix independent versions arbitrarily:

| Provider | Maven artifact | Purpose |
|---|---|---|
| AWS | `software.amazon.awssdk:s3` | S3 client and AWS SDK credential provider chain |
| Azure | `com.azure:azure-identity` | `ManagedIdentityCredential` and `WorkloadIdentityCredential` |
| Google Cloud | `com.google.cloud:google-cloud-pubsub` | Pub/Sub `Publisher` and ADC integration |

The Spring bean examples share a common configuration object. Register the record with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cloud")
public record CloudProperties(
        String region,
        String projectId,
        String topicName,
        String managedIdentityClientId) {
}
~~~

Example `application.yml`:

~~~yaml
app:
  cloud:
    region: ap-southeast-1
    project-id: PROJECT_ID
    topic-name: orders-events
    managed-identity-client-id:
~~~

If using Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP starters, prefer the BOM matching your project's Spring Boot version. Starters may auto-configure credentials/clients; only define manual beans when your application needs custom configuration and you have verified there are no conflicts with auto-configuration.

## 14. Spring Boot and the AWS SDK for Java 2.x Credential Provider

AWS SDK for Java 2.x provides `DefaultCredentialsProvider`. The provider chain searches for credentials in order, including system properties, environment variables, web identity tokens, shared profiles, ECS container credentials, and the EC2 instance profile.

This lets the same code run on:
- EC2 with an instance profile.
- ECS with a task role.
- EKS IRSA with a web identity token.
- EKS Pod Identity with a container credential endpoint.
- Local development with a developer profile.

Example Spring bean for S3:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class AwsClientConfiguration {

    @Bean
    S3Client s3Client(CloudProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

If `credentialsProvider` is omitted, the AWS SDK also uses the default provider chain. Specifying it explicitly makes it clear to readers that the application relies on the runtime identity.

Note the chain precedence: system properties and environment variables are checked before web identity/container/instance profiles. If an image or Pod accidentally contains stale `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` variables, the SDK may use them instead of the workload's attached role. Production must remove static credential environment variables and verify the active principal.

Never create a `StaticCredentialsProvider` with embedded access keys in code. Never mount `~/.aws/credentials` into a production Pod.

## 15. Spring Boot and Azure Identity

The Azure Java SDK uses `TokenCredential`. On VMs or Azure-hosted services with Managed Identity, use `ManagedIdentityCredential`. On AKS Workload ID, use `WorkloadIdentityCredential`. Local development can use `DefaultAzureCredential` to locate credentials from Azure CLI or an IDE.

Example Managed Identity on a VM or Container Apps:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AzureCredentialConfiguration {

    @Bean
    TokenCredential tokenCredential(CloudProperties properties) {
        var builder = new ManagedIdentityCredentialBuilder();

        if (properties.managedIdentityClientId() != null
                && !properties.managedIdentityClientId().isBlank()) {
            builder.clientId(properties.managedIdentityClientId());
        }

        return builder.build();
    }
}
~~~

If a VM only has a system-assigned identity, you can omit the client ID. If multiple user-assigned identities are attached, specify the client ID to select the right principal.

Example local profile using `DefaultAzureCredential`:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;

TokenCredential localCredential =
        new DefaultAzureCredentialBuilder().build();
~~~

Do not let `DefaultAzureCredential` in production accidentally fall back to developer credentials or environment service principals when Managed Identity is intended. In production, choose a platform-specific credential to avoid picking the wrong principal.

On AKS, use `WorkloadIdentityCredential` as shown in Section 10. A Spring Cloud Azure starter may auto-configure credentials based on the environment and properties of the version in use; check the exact BOM/starter version before adding a manual `TokenCredential` bean to avoid creating two competing configurations.

## 16. Spring Boot and Google Application Default Credentials

Google Cloud Java client libraries support ADC. When running on Compute Engine, GKE with Workload Identity Federation, or Cloud Run, ADC retrieves credentials from the runtime environment. Code does not need to read a service account JSON key.

In local development, developers can configure ADC via `gcloud auth application-default login`. Local credentials represent the developer or an impersonated service account; never use a developer machine's ADC file as a production credential.

Example Pub/Sub `Publisher`:

~~~java
import com.google.api.gax.core.FixedCredentialsProvider;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.pubsub.v1.TopicName;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GoogleCloudClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    Publisher ordersPublisher(CloudProperties properties)
            throws IOException {
        var credentials = GoogleCredentials.getApplicationDefault();

        return Publisher.newBuilder(
                    TopicName.of(
                        properties.projectId(),
                        properties.topicName()))
                .setCredentialsProvider(
                    FixedCredentialsProvider.create(credentials))
                .build();
    }
}
~~~

In many Google client builders, ADC is already used by default; the snippet above makes the credential source explicit. The `Publisher` must be shut down properly as part of application shutdown lifecycle.

Never upload a service account JSON key into a Kubernetes Secret to act as ADC in production when Workload Identity Federation can be used. Key files are long-lived credentials, hard to rotate, and easily copied outside the intended environment.

## 17. Distinguishing Kubernetes RBAC from Cloud IAM

Kubernetes RBAC and cloud IAM protect two different systems:

| Mechanism | Controls | Example |
|---|---|---|
| Kubernetes RBAC | Permissions to call the Kubernetes API | Pod allowed to read ConfigMaps or list Pods in a namespace |
| AWS IAM | Permissions to call AWS APIs | Role permitted to run `s3:GetObject` |
| Azure RBAC | Permissions to access Azure resources/data plane | Managed Identity permitted to receive Service Bus messages |
| Google Cloud IAM | Permissions to call Google APIs and access resources | Service account permitted to run `pub/sub.publish` |

A Pod with Kubernetes `get pods` permission does not automatically gain permission to read S3. An IAM role allowed to read S3 does not automatically let a Pod read Secrets or Deployments in the Kubernetes API.

Create a dedicated Kubernetes ServiceAccount for each workload needing a different identity. Never use the `default` ServiceAccount across an entire namespace if workloads require different permission sets. Use specific namespaces and subjects in trust policies.

## 18. Protecting Metadata Endpoints and Tokens in Containers

Short-lived credentials reduce risk compared to long-lived keys, yet metadata endpoints and projected tokens remain sensitive assets.

### 18.1. Metadata Endpoints

- AWS EC2: require IMDSv2, limit hop count, and constrain instance role permissions.
- Azure VM: IMDS token requests require the `Metadata: true` header.
- Azure Container Apps: the platform provides `IDENTITY_ENDPOINT` and `IDENTITY_HEADER`; this header helps mitigate SSRF.
- Google Cloud: the metadata server supplies credentials for the attached service account; metadata requests require the `Metadata-Flavor: Google` header.
- Kubernetes: mount projected ServiceAccount tokens only for workloads requiring federation or Kubernetes API access.

Do not route metadata endpoints through a standard HTTP proxy. Configure proxy bypass for link-local metadata addresses if the SDK or runtime needs access. Block SSRF in the application using URL allow-lists; never let user-controlled URLs call metadata IPs.

### 18.2. Token Files in Kubernetes

Projected ServiceAccount tokens have an audience and expiration. Never copy tokens into ConfigMaps, logs, or images. Never store tokens in shared volumes readable by other Pods. SDK credential providers must support refreshing when token files rotate.

If a workload needs neither the Kubernetes API nor federation, you can disable automatic mounting of the ServiceAccount token. However, if IRSA, AKS Workload ID, or GKE WIF relies on projected tokens, you must retain or configure the appropriate volume projection. Do not blindly set `automountServiceAccountToken: false` and break federation.

### 18.3. Separating Node and Pod Permissions

- Node roles/service accounts should grant permissions only for kubelet, the container runtime, logging agents, or necessary node components.
- Pod roles/identities grant business permissions to the application.
- Never allow Pods to fall back to a shared node identity.
- For special Pods requiring `hostNetwork` or `hostPath`, carefully review metadata and token access.
- Use `NetworkPolicy` or equivalent isolation mechanisms to restrict untrusted workloads.

## 19. Least Privilege and Per-Workload Role Design

Do not create a single shared identity for all microservices. Design by capability:

| Workload | Identity | Example Permissions |
|---|---|---|
| `orders-api` | `orders-api-runtime` | Write `OrderCreated` events and read required config |
| `orders-worker` | `orders-worker-runtime` | Receive messages from `orders-processing` |
| `invoice-worker` | `invoice-worker-runtime` | Read invoice objects and write results |
| `reporting-job` | `reporting-job-runtime` | Read-only access to reporting data |
| `secret-rotation-job` | `secret-rotation-runtime` | Update only the assigned secret |

Principles:
- One identity per service or group of workloads sharing the same responsibility.
- Grant only required actions on specific resources.
- Separate read, write, publish, consume, and admin permissions.
- Separate provisioner roles from runtime roles.
- Avoid resource wildcards whenever ARN/resource ID scoping is possible.
- Review permissions periodically using audit logs and access analyzers.
- Remove role assignments/associations when a workload stops using an identity.

Overly broad permissions widen the blast radius if a container or dependency is compromised. Dedicated identities narrow incident scope and simplify request attribution.

## 20. Testing Identities in Real Environments

Unit tests can verify code wiring and credential bean configuration, but they do not prove cloud role assignments are valid. Run integration tests in an environment with the workload identity attached.

| Scenario | How to Test | Expected Result |
|---|---|---|
| EC2 instance profile | Run app on EC2 with role attached | SDK obtains temporary credentials |
| ECS task role | Assign `taskRoleArn`, omit static keys | Container calls permitted data-plane API |
| ECS execution role | Separate execution role from task role | App does not inherit image pull/log permissions |
| EKS IRSA | Configure OIDC trust and ServiceAccount annotation | Pod assumes the right role |
| EKS Pod Identity | Create association and install agent | Pod receives credentials from agent |
| Azure VM Managed Identity | Attach identity and data-plane role | SDK acquires token and calls resource |
| AKS Workload ID | Configure FIC with matching issuer/subject/audience | Pod exchanges token for Entra token |
| GCP Compute Engine | Attach service account to VM | ADC acquires token |
| GKE WIF | Link KSA to GSA or IAM principal | Pod calls APIs under its own identity |
| Cloud Run service identity | Deploy with dedicated service account | Service accesses intended resource |
| Wrong audience | Present token with wrong audience | Federation rejects it |
| Wrong subject/namespace | Use ServiceAccount outside trust policy | Role assumption fails |
| Missing role | Remove data-plane role in test | API returns 403/permission denied |
| Token refresh | Run workload past access token lifetime | SDK continues calling APIs after refresh |
| Static key leakage | Inject dummy static env credentials in isolated test | Detects provider chain picking wrong credential |

Use test resources and dedicated test principals. Never revoke roles, alter trust policies, or intentionally break production workloads for testing.

## 21. Diagnosing Authentication and Authorization Failures

| Symptom | Possible Cause | Remediation |
|---|---|---|
| AWS SDK `Unable to load credentials` | Missing role, web identity token, or matching credential provider | Check instance profile, task role, ServiceAccount association, and SDK version |
| AWS `AccessDenied` | Role has credentials but policy lacks action/resource | Inspect trust policy, permission policy, boundaries, and resource policies |
| AWS uses wrong identity | Static env/system properties precede web identity in provider chain | Remove static credentials and verify active principal |
| Azure `CredentialUnavailableException` | Managed Identity disabled or Workload ID missing client/tenant/token file | Inspect platform identity and environment variables |
| Azure `401` | Wrong token audience/authority/tenant or expired token | Check resource scope and credential configuration |
| Azure `403` | Entra token valid, but Azure RBAC/data-plane role missing | Assign the proper role at the proper scope |
| AKS workload identity fails | Incorrect OIDC issuer, FIC subject/audience, or Pod label | Cross-check issuer URL, namespace, ServiceAccount, and label |
| GCP ADC finds no credentials | VM/Cloud Run/GKE lacks a service identity | Attach service account or enable WIF |
| GCP `403` | Service account lacks IAM role or API is not enabled | Check IAM bindings and API enablement |
| GKE uses node permissions | Pod not using KSA/WIF properly or metadata server disabled | Check node pool, KSA, and workload identity config |
| Token refresh fails | Token file not rotating, network/metadata endpoint failure | Check projected volume, agent, and metadata access |
| Works locally, fails in production | Local developer credentials masked missing workload identity config | Test inside a runtime matching production |

Distinguish `401` and `403`:
- `401` typically indicates an invalid or unaccepted credential/token.
- `403` typically indicates the principal was recognized but lacks permissions, or a policy denied the request.

However, individual services may surface errors differently. Inspect provider error codes and audit logs rather than relying solely on HTTP status codes.

## 22. Migrating from Static Credentials to Workload Identity

If an application currently uses access keys, client secrets, or service account JSON keys, migrate step-by-step:

1. Identify every service and resource accessed by the current credential.
2. Create a dedicated identity for each workload.
3. Grant least-privilege roles based on actual API calls.
4. Establish trust/associations and attach the identity to the runtime.
5. Update Spring Boot to use the SDK credential provider.
6. Deploy to staging and verify data-plane operations.
7. Confirm logs/audits show the new principal is being used.
8. Cut over production using a rollback-capable rollout.
9. Revoke old static credentials and remove them from CI variables, secret mounts, image layers, and repository history per policy.
10. Monitor `AccessDenied`, token refresh, and credential usage after cutover.

Never delete old keys before verifying the workload uses the new identity. Yet never leave both mechanisms active indefinitely without a retirement deadline, as the SDK can silently pick up old static credentials.

## 23. Pre-Production Checklist

- **Identity:** Every service has an appropriate workload identity.
- **Trust:** Trust policies/OIDC federation restrict issuer, subject, audience, namespace, and ServiceAccount.
- **Roles:** Only required data-plane permissions are granted.
- **Nodes:** Node identities do not carry broad business permissions.
- **Containers:** ECS task roles or container app identities are properly configured.
- **Kubernetes:** Pods use dedicated ServiceAccounts instead of relying on default identities.
- **AWS:** Task role is separated from execution role; IMDSv2 and EKS Pod Identity Agent/IRSA are verified.
- **Azure:** System/user-assigned Managed Identity and AKS Workload ID are distinguished; data-plane roles are assigned properly.
- **Google Cloud:** Dedicated service accounts are used for VMs/Cloud Run; GKE Workload Identity Federation is enabled.
- **SDK:** `DefaultCredentialsProvider`, `ManagedIdentityCredential`/`WorkloadIdentityCredential`, or ADC is used according to runtime.
- **Static keys:** No access keys, client secrets, or service account keys exist in JARs, images, manifests, or logs.
- **Metadata:** IMDS/metadata endpoints are protected against SSRF and untrusted workloads.
- **Tokens:** Short-lived tokens refresh properly; projected tokens are never shared outside the workload.
- **Testing:** Positive and negative tests cover trust, roles, wrong subject/audience, and token refresh.
- **Audit:** Principals are traceable in CloudTrail, Azure Activity/diagnostic logs, or Google Cloud audit logs.
- **Recovery:** Procedures exist to revoke identities and role assignments if a workload is compromised or decommissioned.

## 24. Summary

Assigning identities to applications means binding a specific workload to a cloud principal and restricting that principal's permissions to only the resources it needs. AWS uses IAM roles attached to EC2 instance profiles, ECS task roles, or Kubernetes ServiceAccounts via IRSA/EKS Pod Identity. Azure uses system-assigned/user-assigned Managed Identities on VMs and container platforms, or Microsoft Entra Workload ID for AKS Pods. Google Cloud uses service accounts attached to Compute Engine/Cloud Run and Workload Identity Federation for GKE.

Spring Boot does not need to store access keys or private keys to perform cloud operations. The AWS SDK credential chain, Azure Identity, and Google ADC retrieve short-lived credentials from the runtime environment and refresh them across the token lifecycle. When trust relationships bind the exact workload, IAM/RBAC is scoped to target resources, metadata endpoints are protected, and integration tests verify the real principal, applications can access managed services with least privilege across VMs, containers, and Kubernetes.

## References

- [AWS IAM roles for Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [AWS SDK for Java 2.x default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [Amazon ECS task IAM role and execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-role-overview.html)
- [IAM roles for service accounts in Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Create an IAM role with the trust policy required by EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-role.html)
- [Configure the EC2 Instance Metadata Service](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html)
- [Managed identities for Azure virtual machines](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/how-managed-identities-work-vm)
- [Authenticate Azure-hosted Java apps with Managed Identity](https://learn.microsoft.com/en-us/azure/developer/java/sdk/identity-azure-hosted-auth)
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Authenticate Azure-hosted Java apps with a user-assigned Managed Identity](https://learn.microsoft.com/en-us/azure/developer/java/sdk/authentication/user-assigned-managed-identity)
- [Microsoft Entra Workload ID on AKS](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview)
- [WorkloadIdentityCredentialBuilder for Azure Identity Java](https://learn.microsoft.com/en-us/java/api/com.azure.identity.workloadidentitycredentialbuilder?view=azure-java-stable)
- [Google Cloud service accounts for Compute Engine](https://docs.cloud.google.com/compute/docs/access/service-accounts)
- [Authenticate to Google Cloud APIs from GKE workloads](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Configure service identity for Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/service-identity)
- [Authenticate with Google Cloud client libraries](https://docs.cloud.google.com/docs/authentication/client-libraries)
- [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
