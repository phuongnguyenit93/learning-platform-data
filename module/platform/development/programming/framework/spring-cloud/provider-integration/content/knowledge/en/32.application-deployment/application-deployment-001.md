# Separating Resource Provisioning from Business Operations

A Spring Boot application may require Event Hubs, Event Grid, Service Bus, Blob Storage, S3, SQS, Pub/Sub, Cloud Storage, or a managed database to execute its business logic. These resources must be created, configured, and authorized before the application uses them. If each instance is allowed to create resources on its own at startup or during request processing, the application must hold broad administrative permissions, multiple replicas can race when creating the same resource, startup becomes dependent on administrative operations, and infrastructure changes become difficult to control.

The proper organization is to separate **provisioning** from **runtime**. An infrastructure pipeline uses Infrastructure as Code (IaC) to create resources, networking, identities, and role assignments. An application pipeline deploys the built artifact. At runtime, Spring Boot only receives endpoints, resource IDs, queue/topic/container names, and workload identity credentials to call data plane APIs for business operations. Creating or modifying resources is managed through a dedicated deployment workflow with change inspection and lifecycle control.

This lesson belongs to the **Application Deployment** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module provides hands-on practice integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on the boundary between resource provisioning and business operations, managing infrastructure with IaC, separating control plane and data plane permissions, passing outputs into Spring Boot configuration, and operating multiple environments.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between provisioning, application deployment, and business runtime.
- Explain why an application should not create cloud resources on its own during each startup or request.
- Describe the control plane and data plane boundary across AWS, Azure, and Google Cloud.
- Choose CloudFormation, Bicep, Terraform, or Google Cloud Infrastructure Manager for each workflow.
- Declare resources, dependencies, outputs, and identities using IaC.
- Separate provisioner pipeline permissions from workload runtime permissions.
- Pass endpoints and resource names from the pipeline into Spring Boot using externalized configuration.
- Use Managed Identity, IAM roles, or Workload Identity instead of static administrative credentials.
- Manage database migrations and secrets with separate lifecycles.
- Control drift, destructive changes, cost, and rollout ordering.
- Test that the application only uses provisioned resources and lacks permissions to create unexpected resources.

## 2. Three Types of Work to Separate

A cloud-native system typically involves three distinct types of changes:

| Type of Work | Scope | Execution Timing | Typical Identity |
|---|---|---|---|
| **Infrastructure provisioning** | Create VPC/VNet, subnets, storage, queues, topics, Event Hubs, databases, key vaults, identities, role assignments | Before deploying workloads or when changing infrastructure | Provisioner pipeline or platform team |
| **Application deployment** | Build image/JAR, deploy revisions, configure replicas, health probes, rollout/rollback | On each application version release | CI/CD deploy identity |
| **Business runtime** | Send events, receive messages, read/write objects, query databases, process requests | While the application is serving traffic | Application workload identity |

These three types of work can run within the same overall pipeline, but they require separate steps, permissions, and state. For example, a release pipeline may invoke an IaC module first and then deploy the application; that does not mean the Java service should call administrative APIs to create an Event Hub on every request.

### 2.1. Provisioning

Provisioning describes the desired state of the infrastructure:
- Which resources must exist?
- Which subscription/account/project and region do the resources belong to?
- How are networking, encryption, retention, capacity, and backup configured?
- Which workload identities are allowed to send/receive data?
- Who has permission to modify or delete resources?
- Should resources be retained when a stack/module is deleted?

Provisioning requires change history, review, plan/preview, and environment reproducibility.

### 2.2. Application Deployment

Application deployment delivers a built artifact to a compute platform such as Kubernetes, App Service, ECS, Cloud Run, or VMs. Deployment configures the image/version, environment variables, secret references, replicas, probes, and rollout strategy.

Deploying a new version should not recreate a storage account, queue, or database. If an application needs a resource change, that change must appear explicitly in an IaC change and the config contract.

### 2.3. Business Runtime

The runtime only uses resources that have already been provisioned:
- Send events to an existing topic.
- Read messages from an existing queue/subscription.
- Write objects to an existing bucket/container.
- Call an existing database.
- Read secrets according to workload permissions.
- Return clear errors when a resource does not exist or the identity lacks permissions.

An SDK client builder usually only constructs a client object and configures connections. Commands such as create bucket, create queue, create topic, create container, or create role assignment are provisioning operations. Do not confuse initializing an SDK client with creating a cloud resource.

## 3. Architecture Separating Provisioning and Runtime

~~~mermaid
flowchart TD
    DEV["Platform / application team"] --> CODE["IaC source + application source"]
    CODE --> PIPE["CI/CD pipeline"]
    PIPE --> VALIDATE["Validate, policy check, plan / what-if"]
    VALIDATE --> APPROVE["Review infrastructure change"]
    APPROVE --> PROVISION["Provision resources + identity + RBAC"]
    PROVISION --> OUTPUTS["Resource outputs / config contract"]
    OUTPUTS --> DEPLOY["Deploy application artifact"]
    DEPLOY --> RUNTIME["Spring Boot runtime"]
    RUNTIME --> DATA["Existing managed resources"]
    RUNTIME --> OBS["Logs, metrics, traces"]
    PROVISION --> AUDIT["Infrastructure state / audit"]
    DEPLOY --> AUDIT
~~~

This flow establishes a clear contract between the platform and the application:

1. IaC defines the resources and desired configuration.
2. The pipeline validates changes before applying them.
3. The provisioner creates resources and assigns permissions to the workload identity.
4. The pipeline collects non-sensitive outputs such as endpoints, resource IDs, and destination names.
5. Application deployment injects those values into environment configuration.
6. Spring Boot initializes SDK clients using runtime credentials.
7. Business handlers only call data plane APIs.

If provisioning fails, the pipeline stops before deploying a revision that depends on that resource. If the application cannot connect to the resource, readiness checks and smoke tests detect the failure before receiving traffic.

## 4. Why Not Create Cloud Resources in Business Flows?

Letting an application create resources on its own may be convenient in a small demo, but it causes many issues in production:

- **Overly broad permissions:** the application must hold permissions to manage resources, create policies, or assign roles instead of only sending/receiving data.
- **Race conditions:** multiple pods starting simultaneously can concurrently try to create the same queue, container, or subscription.
- **Slow startup:** the application must wait on management APIs, retries, and eventual consistency before becoming ready.
- **Hard to control costs:** each deployment or request can create unexpected new resources.
- **Drift:** configuration created by runtime code is no longer tracked in IaC state/templates.
- **Unclear lifecycle:** it becomes unclear which resources should be retained and which can be deleted when scaling down.
- **Difficult auditing:** administrative operations mix with business activity, making it hard to identify who changed infrastructure.
- **Difficult rollback:** rolling back the application does not safely revert resources to their previous state.

For example, suppose a handler creates a storage container if it does not exist before uploading a file. With 20 replicas, all of them may call create-if-not-exists concurrently. Even if the SDK supports idempotent operations, the application still needs management permissions, creates extra coupling, and can hide the fact that the pipeline failed to provision the proper resource.

In production, the container must be created by IaC. The runtime only obtains a client for the known container and writes objects. If the container is missing, the application reports a readiness/operation failure so the platform can fix provisioning.

## 5. Control Plane and Data Plane

Cloud providers typically separate resource management APIs from data usage APIs.

| Cloud | Control plane / management API | Data plane / runtime API |
|---|---|---|
| AWS | CloudFormation, EC2, IAM, S3 control APIs, SQS CreateQueue | S3 GetObject/PutObject, SQS SendMessage/ReceiveMessage, EventBridge PutEvents |
| Azure | Azure Resource Manager, Microsoft.Resources/deployments, role assignments | Blob data operations, Service Bus Data Sender/Receiver, Event Hubs send/receive |
| Google Cloud | Resource Manager, Cloud APIs managing projects/resources/IAM | Pub/Sub publish/pull, Cloud Storage object operations, database queries |

Specific API names vary by service, but the permission principle remains the same:

- The provisioner needs permissions to create/update resources and role assignments within its assigned scope.
- The runtime needs only the data operations required on existing resources.
- The runtime should not hold Owner, Contributor, Project Editor, or IAM administrator roles just to send events or write objects.
- Reading resource metadata may be needed for health checks, but that does not imply needing permission to create or delete resources.

### 5.1. Example Permission Separation

| Task | Provisioner | Spring Boot runtime |
|---|---:|---:|
| Create Event Hub/queue/topic | Yes | No |
| Create storage account/bucket | Yes | No |
| Create database server/instance | Yes | No |
| Assign IAM/RBAC role | Yes (scoped) | No |
| Send events | Possible | Yes, if business logic requires it |
| Receive messages | Possible | Yes, if business logic requires it |
| Read/write objects | Possible | Only required object permissions |
| Read runtime secrets | Not required | Only granted secrets |
| Delete production resources | Separate controlled process | No |

A provisioner pipeline may use broader permissions than a workload, but it must be restricted by environment, subscription/account/project, and module. Provisioning permissions also require review, auditing, and separation from application deployment permissions.

## 6. Choosing IaC Tools on AWS, Azure, and Google Cloud

| Provider | Common Tools | Characteristics |
|---|---|---|
| AWS | CloudFormation, AWS CDK, Terraform | CloudFormation manages resources by stack; CDK synthesizes source code into templates; Terraform uses providers and state |
| Azure | Bicep/ARM, Terraform | Bicep is a declarative language for Azure Resource Manager, supporting modules and what-if |
| Google Cloud | Terraform, Google Cloud Infrastructure Manager | Infrastructure Manager uses Terraform configurations to manage deployments/revisions and infrastructure previews |
| Multi-cloud | Terraform or multi-provider IaC tools | Shared workflow, though you must still understand IAM, network, storage, and lifecycle differences per cloud |

There is no need to force every cloud to use the same DSL if the platform already has standardized tooling. What matters is that all production resources have a source of truth, review process, and managed pipeline.

### 6.1. AWS CloudFormation

A CloudFormation template describes resources; a stack is the unit for creating, updating, and deleting a set of resources. Change sets let you preview which resources will be added, modified, replaced, or deleted before execution. Drift detection compares actual resource state against the managed template and parameters.

Condensed CloudFormation example:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Provision resources for the order application

Resources:
  OrdersEventBus:
    Type: AWS::Events::EventBus
    Properties:
      Name: orders-events

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-processing
      VisibilityTimeout: 60

  OrdersBucket:
    Type: AWS::S3::Bucket
    Properties:
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256

Outputs:
  EventBusName:
    Value: !Ref OrdersEventBus
  QueueUrl:
    Value: !Ref OrdersQueue
  BucketName:
    Value: !Ref OrdersBucket
~~~

The template above describes resources and outputs. Workload IAM roles/policies should be defined in a separate module or a reviewed security resource section. Do not place access keys in Outputs; outputs should be non-sensitive names/ARNs/URLs needed for deployment configuration.

### 6.2. Azure Bicep

Bicep declares Azure resources using declarative syntax. Azure Resource Manager handles dependencies between resources; modules help split infrastructure into reusable parts. What-if preview shows which resources/properties may be created, modified, or deleted before deployment.

Example provisioning Event Hubs and a Blob container as a checkpoint store:

~~~bicep
param location string = resourceGroup().location
param namespaceName string
param eventHubName string
param storageAccountName string

resource namespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: namespaceName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: namespace
  name: eventHubName
  properties: {
    partitionCount: 4
    messageRetentionInDays: 7
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource checkpointContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'eventhub-checkpoints'
  properties: {
    publicAccess: 'None'
  }
}

output namespaceName string = namespace.name
output eventHubName string = eventHub.name
output storageAccountName string = storage.name
output checkpointContainerName string = checkpointContainer.name
~~~

This is a condensed infrastructure example; production needs network/private endpoints, diagnostic settings, tags, SKU/capacity, retention, backup, and role assignments according to platform standards. The Event Hubs namespace and Blob Storage are created during the provisioning stage. Spring Boot does not need permission to create them.

The pipeline can run what-if before deploying:

~~~bash
az deployment group what-if \
  --resource-group rg-orders-prod \
  --template-file main.bicep \
  --parameters namespaceName=orders-prod eventHubName=order-events storageAccountName=ordersstateprod
~~~

Only after reviewing the result should the pipeline execute the deployment. What-if is a forecast of changes, not an absolute guarantee that every runtime impact has been simulated; carefully read Create, Modify, Delete changes and any warnings that could not be evaluated.

### 6.3. Google Cloud Terraform and Infrastructure Manager

Terraform describes Google Cloud resources; Infrastructure Manager is a managed service for Terraform deployments on Google Cloud. The service supports storing configurations in Cloud Storage, a Git repository, or a local directory, managing deployments/revisions, and previewing deployments. Infrastructure Manager manages infrastructure; deploying applications to Cloud Run/GKE or other compute is a separate workflow.

Condensed Terraform example:

~~~hcl
resource "google_pubsub_topic" "orders" {
  name = "orders-events"
}

resource "google_pubsub_subscription" "orders_consumer" {
  name  = "orders-processing"
  topic = google_pubsub_topic.orders.id

  ack_deadline_seconds = 30
}

resource "google_storage_bucket" "application_state" {
  name                        = var.state_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
}

output "orders_topic_id" {
  value = google_pubsub_topic.orders.id
}

output "orders_subscription_id" {
  value = google_pubsub_subscription.orders_consumer.id
}

output "state_bucket_name" {
  value = google_storage_bucket.application_state.name
}
~~~

Terraform requires a managed and protected state backend, access control on state, locking supported by the backend, and a plan/apply workflow. Do not store production state on a personal laptop or commit state files that may contain sensitive data to Git.

### 6.4. Outputs as the Contract Between Provisioning and Deployment

Outputs may include:
- Resource ID/ARN.
- Service endpoint or FQDN.
- Queue, topic, subscription, bucket, or container name.
- Region/project/subscription/account.
- Identity resource ID or principal ID to reference when assigning permissions.
- Secret reference name, not the secret value.

The pipeline reads outputs and passes them into deployment configuration. Do not use outputs to pass private keys, passwords, SAS tokens, or connection strings containing secrets. If the application uses workload identity, in most cases it only needs endpoints/resource names and the credential chain.

## 7. Designing IaC Modules and Dependencies

You should not place an organization's entire infrastructure in a single large file that is hard to review. It can be split by responsibility:

| Module | Typical Resources | Owner |
|---|---|---|
| Network | VPC/VNet, subnets, routes, private endpoints, firewalls | Platform/network |
| Identity | Managed identities, service accounts, IAM roles, role assignments | Platform/security |
| Messaging | Event Grid, Event Hubs, Service Bus, SNS/SQS, Pub/Sub | Messaging/platform |
| Storage | S3, Blob Storage, Cloud Storage, encryption, lifecycle | Platform/data |
| Database | Managed DB, subnet integration, backup, parameter groups | Data/platform |
| Observability | Log groups, diagnostic settings, metric alerts, dashboards | SRE/platform |
| Application deployment | Container apps, Kubernetes workloads, services, ingress | Application/platform |

Modules must declare clear inputs and outputs. For example, the messaging module receives the workload's principal ID and returns the event endpoint, topic name, and resource ID. The identity module does not need to know business payloads; the application module does not need to create queues.

### 7.1. Dependency Graph

A deployment may have the following dependency relationships:

~~~mermaid
flowchart TD
    NET["Network and private endpoints"] --> DATA["Storage / database / messaging"]
    ID["Workload identity"] --> RBAC["Data-plane role assignments"]
    DATA --> RBAC
    DATA --> OUTPUT["Resource outputs"]
    RBAC --> OUTPUT
    OUTPUT --> APP["Deploy Spring Boot"]
    APP --> SMOKE["Readiness and smoke test"]
    SMOKE --> TRAFFIC["Enable traffic"]
~~~

Create networking and identities first; create resources; assign permissions; emit configuration; then deploy the application. If resources and role assignments are deployed in parallel without proper dependencies, the application may start before role assignments propagate.

Role assignments often have propagation latency. The pipeline can include a readiness check step with bounded retry/backoff, but you should not grant administrative permissions to the runtime just to work around propagation time.

## 8. Separating Provisioner and Workload Runtime Identities

A secure system has at least two distinct identities:

**Provisioner identity**
- Used by the pipeline to create/update infrastructure.
- Holds management plane permissions within the required scope.
- Can assign roles to workload identities if permitted by the workflow.
- Has audit logging and approvals for production changes.
- Must not be embedded in the application image or environment.

**Workload identity**
- Used by Spring Boot at runtime.
- Holds data plane permissions matching business needs.
- Lacks permissions to create/delete queues, buckets, topics, or IAM policies.
- Can differ per service, environment, and workload.
- Does not share a single broad-permission principal across all applications.

Example roles by provider:

| Provider | Provisioner | Runtime |
|---|---|---|
| AWS | CloudFormation deployment role, IAM deployment permissions | ECS task role, EKS IRSA/Pod Identity, or EC2 instance profile with required S3/SQS/EventBridge actions |
| Azure | Service principal/workload identity with ARM/Bicep deployment and scoped role assignment permissions | Managed Identity/Workload Identity with Event Hubs Data Receiver, Service Bus Data Sender/Receiver, Storage Blob Data Contributor as needed |
| Google Cloud | CI service account with permissions to create resources and IAM bindings in the assigned project/folder | Workload service account with Pub/Sub Publisher/Subscriber, Storage Object User, or narrower roles |

Do not grant permissions based solely on service name. Identify the exact actions the application performs, the resource scope, and the appropriate built-in or custom role. For instance, a consumer that only reads messages does not need publish permission; a service that only writes objects does not need permission to delete a bucket.

## 9. Passing Resource Outputs into Spring Boot

Spring Boot supports externalized configuration from YAML/properties, environment variables, command line arguments, and other configuration sources. Use a typed contract to receive the values emitted by the provisioning pipeline.

Example runtime configuration:

~~~yaml
app:
  cloud:
    provider: azure
    event-grid-endpoint: https://orders-prod.region.eventgrid.azure.net/api/events
    event-hub-namespace: orders-prod.servicebus.windows.net
    event-hub-name: order-events
    checkpoint-storage-endpoint: https://ordersstateprod.blob.core.windows.net
    checkpoint-container: eventhub-checkpoints
~~~

The values above are non-secret examples. In production, the pipeline replaces them with outputs for the corresponding environment or injects them from a config service. Do not hardcode production resource names inside the JAR.

### 9.1. Binding Configuration with ConfigurationProperties

To validate Jakarta Validation annotations when binding configuration, add the validation starter if the project does not already have it:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cloud")
public record CloudResourceProperties(
        @NotBlank String provider,
        @NotBlank String eventGridEndpoint,
        @NotBlank String eventHubNamespace,
        @NotBlank String eventHubName,
        @NotBlank String checkpointStorageEndpoint,
        @NotBlank String checkpointContainer) {
}
~~~

Register the properties:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(CloudResourceProperties.class)
class CloudResourceConfiguration {
}
~~~

When an endpoint or resource name is missing, validation causes the application to fail fast right at configuration binding time. This is a configuration error that should be caught during the deploy stage, not a reason for the runtime to create the resource itself.

### 9.2. Injecting the Credential Chain and Creating SDK Clients

Azure example using DefaultAzureCredential:

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AzureIdentityConfiguration {

    @Bean
    DefaultAzureCredential defaultAzureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }
}
~~~

Example publisher client constructed from the provisioned endpoint:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.messaging.eventgrid.EventGridEvent;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import com.azure.messaging.eventgrid.EventGridPublisherClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventGridClientConfiguration {

    @Bean
    EventGridPublisherClient<EventGridEvent> eventGridPublisher(
            CloudResourceProperties properties,
            TokenCredential credential) {
        return new EventGridPublisherClientBuilder()
                .endpoint(properties.eventGridEndpoint())
                .credential(credential)
                .buildEventGridEventPublisherClient();
    }
}
~~~

The client builder creates a client object to call an existing endpoint; it does not create an Event Grid topic. The runtime identity must hold EventGrid Data Sender on the topic. If the topic has not been provisioned or the endpoint is wrong, send operations will fail and must be handled as configuration/connectivity errors.

### 9.3. Business Service Only Uses the Client

~~~java
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridEvent;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {
    private final EventGridPublisherClient<EventGridEvent> publisher;

    OrderEventPublisher(
            EventGridPublisherClient<EventGridEvent> publisher) {
        this.publisher = publisher;
    }

    public void publish(OrderCreated order) {
        EventGridEvent event = new EventGridEvent(
                "/orders/" + order.orderId(),
                "com.example.orders.created",
                BinaryData.fromObject(order),
                "1.0")
                .setId(order.eventId());

        publisher.sendEvent(event);
    }
}

record OrderCreated(
        String eventId,
        String orderId,
        long totalAmount) {
}
~~~

The business service does not call topic management APIs, create role assignments, or store connection strings. The event ID is generated deterministically by the business/outbox layer so consumers can deduplicate when the publisher retries.

## 10. Should the Runtime Fail Fast or Retry?

Separating provisioning does not mean the application skips checking resources. The runtime still needs to verify configuration and accessibility, but its response must match the failure type.

| Scenario | Runtime Behavior |
|---|---|
| Missing endpoint or resource name | Fail fast during configuration binding |
| Resource does not exist | Report clear error; deployment/readiness fails |
| Identity lacks data-plane role | Report 403/authorization failure; platform fixes role assignment |
| Network/private endpoint not ready yet | Bounded retry or readiness remains unhealthy |
| Service throttling / temporarily unavailable | Retry according to SDK policy, backoff, and deadline |
| Invalid event payload | Reject/quarantine according to business rules |
| Resource needs capacity/retention change | Create a separate IaC change, review, and deploy |

Do not automatically create resources when encountering 404 or 403. A 404 may indicate a wrong endpoint, a deleted resource, or an incomplete deployment; a 403 usually indicates a wrong identity/scope. If the runtime creates resources on error, it masks the root cause and unintentionally expands permissions.

Readiness checks can verify connectivity/metadata using read-only permissions if the SDK and service support it. Liveness checks should only verify that the process is still alive, avoiding restarting the entire pod simply because a cloud service is temporarily slow.

## 11. Prevent Binders or Frameworks from Auto-Provisioning Production Resources Unintentionally

Some SDKs, Spring Cloud binders, or frameworks may support auto-creating destinations, queues, topics, subscriptions, or containers depending on the provider and configuration. This feature is useful in local development, integration tests, or ephemeral environments.

In production:
- Check the documentation of the binder/starter in use to understand its auto-provision behavior.
- Disable auto-create when IaC is the source of truth.
- Ensure queues/topics/subscriptions are created before deploying the application.
- If the framework requires resources to exist, fail startup/readiness clearly.
- Do not grant destination-creation permissions to the workload just so the binder can auto-create them.
- Specify destination names in deployment config and verify the correct environment.

There is no single shared property to disable auto-create across all Spring Cloud providers. Property names and behavior differ across Spring Cloud AWS, Spring Cloud Azure, and Spring Cloud GCP; you must check the exact binder version in use.

## 12. Managing Database Schema Migrations Separately

The database server/instance, subnet, firewall, backup, encryption, and credential store belong to provisioning. Tables, indexes, constraints, and schema versions belong to the application's data lifecycle.

You should not let every replica run DDL or auto-create database schemas at production startup:
- Multiple replicas can run migrations concurrently.
- The runtime identity would need broad DDL permissions.
- A migration that breaks backward compatibility can break older running versions.
- Rolling back the application does not safely roll back data automatically.

Use Flyway/Liquibase or a dedicated migration job:
1. Provision the database and runtime/migration identities.
2. Deploy the migration job with restricted DDL permissions.
3. Run the migration with locking/version tracking.
4. Verify the migration succeeded.
5. Deploy the application revision compatible with the new schema.
6. Revoke or do not grant DDL permissions to the runtime identity.

Production Hibernate configuration typically uses `validate`/`none` instead of `update`/`create`. Choose a backward-compatible migration strategy (expand-and-contract) when rolling out multiple versions simultaneously.

## 13. Secrets and Configuration Are Not the Same Type of Output

IaC outputs typically contain endpoints, resource IDs, queue/topic names, and non-sensitive values. Secrets such as passwords, private keys, SAS tokens, connection strings with shared keys, and client secrets must be stored in a secret manager.

| Value Type | Examples | Delivery Mechanism |
|---|---|---|
| Resource identifier | ARN, resource ID, project ID | IaC output → deployment config |
| Endpoint | FQDN, URL, region | IaC output → environment/config |
| Destination name | Queue/topic/container | IaC output → ConfigurationProperties |
| Secret reference | Key Vault secret URI, Secrets Manager ARN, Secret Manager resource name | Config reference → runtime identity reads secret |
| Secret value | Password, private key, SAS token | Secret manager or mounted secret, never written to outputs/logs |
| Workload identity | Managed identity ID, service account binding | Created by IaC; platform attaches to workload |

Prefer workload identity so the runtime obtains short-lived tokens from the cloud identity provider. When secrets must be used, the application should read them with least privilege, rotation, auditing, and no logging of secret values.

Spring Boot supports externalized configuration and configuration trees. You can mount secrets as files or use platform-appropriate secret integrations. Do not pass secrets via command-line arguments because they can appear in process lists or pipeline logs.

## 14. Separating Environments and Ownership

Dev, test, staging, and production require separate resource boundaries:
- AWS account/OU, Azure subscription/resource group, Google Cloud project/folder.
- Separate networking, storage, queues/topics, and databases per environment.
- Separate workload identities; never use production principals in dev.
- Separate IaC state/backends with restricted state read access.
- Resource tags/labels recording owner, environment, cost center, and service.
- Retention, backup, deletion protection, and alerting tailored by criticality.

Resource names can follow a convention including service, environment, region, and purpose. Avoid generating random resource names on every deployment; stable names keep app config, RBAC, monitoring, and auditing consistent.

Ownership must be clear:
- Platform team owns networking, baseline security, and reusable modules.
- Application team owns resource-specific parameters, event contracts, and runtime behavior.
- Security team reviews role assignments, secret access, and network exposure.
- SRE/operations owns alerts, backups, recovery, and runbooks.

## 15. Updating Resources Without Disrupting Business Operations

An IaC change may modify properties in place, replace a resource, or delete a resource. Changes must be classified before applying.

| Change Type | Examples | Handling |
|---|---|---|
| Non-breaking | Adding tags, increasing capacity within limits | Preview, apply, observe |
| Config change | Retention, network rules, encryption | Check impact and compatibility |
| Replacement | Changing a property that forces resource recreation | Create new resource, migrate/cutover |
| Destructive | Deleting a bucket, queue, or database | Backup, retention, approval, recovery plan |
| Identity change | Changing role assignments or workload principal | Grant new permissions first, deploy, then revoke old permissions |

Do not assume an IaC update is always an in-place operation. Read the change set/plan/what-if to see which resources will be replaced or deleted. For stateful resources storing data, configure appropriate retain/deletion protection/backup policies; never let stack deletion accidentally wipe production data.

### 15.1. Blue-Green for Stateful Resources

When replacing a queue/topic/database or storage:
1. Provision the new resource via an IaC module.
2. Assign permissions to the workload identity.
3. Emit the new endpoint/name.
4. Deploy consumers/publishers compatible with both old and new resources if needed.
5. Sync/backfill data or shift traffic according to the chosen strategy.
6. Observe metrics and confirm no producers/consumers still use the old resource.
7. Retain the old resource for the defined rollback window.
8. Delete the old resource in a separate change after verification.

Do not delete the old resource in the same rollout if older application versions are still running or unprocessed events remain.

## 16. Drift Detection and Out-of-Band Changes

Drift occurs when actual resources diverge from the IaC source of truth, typically due to direct edits via console/CLI or another automation tool.

Detection methods by provider:
- AWS CloudFormation: drift detection and drift-aware change sets.
- Azure Bicep/ARM: what-if to preview expected changes prior to deployment; Azure Policy can audit configuration compliance.
- Google Cloud Infrastructure Manager: preview deployments and manage deployments/revisions based on Terraform configurations.
- Terraform: plan compares state/config against the provider; note that state may not yet reflect every out-of-band change.

Drift handling workflow:
1. Detect and identify the differing resource/property.
2. Determine whether the change came from an incident, manual action, or a buggy IaC module.
3. Decide whether to update the source of truth or revert the resource to the declared state.
4. Review impacts, especially networking, encryption, IAM, and data retention.
5. Apply the change through the pipeline.
6. Record in audit logs and update runbooks if needed.

Do not automatically overwrite all drift in production without review. A manual change might be an active incident mitigation; an IaC apply could overwrite that fix.

## 17. Recommended CI/CD Pipeline

A pipeline can be structured as follows:

~~~mermaid
flowchart TD
    SRC["Commit application + IaC"] --> CHECK["Lint, unit test, policy checks"]
    CHECK --> PLAN["IaC plan / change set / what-if"]
    PLAN --> REVIEW["Review infrastructure diff"]
    REVIEW --> APPLY["Provision / update resources"]
    APPLY --> EXPORT["Publish non-secret outputs"]
    EXPORT --> BUILD["Build and scan application artifact"]
    BUILD --> DEPLOY["Deploy application revision"]
    DEPLOY --> READY["Readiness and smoke tests"]
    READY --> ROUTE["Enable traffic / complete rollout"]
    READY -->|Failure| ROLLBACK["Rollback application revision"]
~~~

Some organizations build artifacts in parallel with infrastructure planning to save time; however, do not deploy a revision before the required resources and permissions are ready.

### 17.1. Control Gates

- **Lint/validate:** check template syntax, modules, dependencies, and versions.
- **Policy check:** block public storage, wildcard IAM, missing encryption, or disallowed regions.
- **Plan/preview:** generate a plan, CloudFormation change set, or Bicep what-if.
- **Review:** inspect Create/Modify/Replace/Delete changes and role assignments.
- **Apply:** use a scoped provisioner identity.
- **Output:** export endpoints/resource names; never export secret values.
- **Deploy:** inject configuration and workload identity into the application.
- **Readiness:** verify app startup, connectivity, and data plane permissions.
- **Smoke test:** send/receive a test event or read/write a test object within a test scope.
- **Observe:** monitor error rates, latency, backlog, cost, and drift.

Production applies typically require approvals matching the blast radius. Dev/test can be more automated if resources are isolated and cost/cleanup are controlled.

## 18. Testing the Provisioning/Runtime Boundary

Both sides must be tested: IaC creates the right resources, and the application lacks permission to create resources.

| Test | How to Execute | Expected Result |
|---|---|---|
| IaC validation | Lint/validate templates/modules | Valid configuration |
| Plan review | Modify a resource on a branch | Diff shows the exact resource/property |
| Provisioning integration | Deploy to a test subscription/account/project | Resources exist and outputs are correct |
| RBAC test | Use the runtime workload identity | Only permitted data plane operations succeed |
| Negative permission test | Attempt to create/delete a resource using runtime identity | Denied |
| Runtime startup | Deploy Spring Boot with provided outputs | Configuration binds successfully |
| Missing resource | Use an invalid container/queue name in test | Readiness/operation fails; app does not auto-create resource |
| Missing permission | Revoke data-plane role in test | Clear authorization error |
| Rollout | Deploy a new revision using the same resources | No duplicate resources created |
| Drift | Modify a test resource outside IaC | Drift/plan detects the change |
| Destroy | Tear down the test environment | Data retention and cleanup follow policy |

Local development can use Testcontainers, LocalStack, Azurite, or an appropriate emulator to spin up ephemeral resources. That is provisioning for a test harness, not production business logic. Keep local configuration isolated and never use production credentials.

## 19. Common Issues and Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Pod creates queue/container at startup | Auto-provision is enabled or code calls create-if-not-exists | Disable auto-create in production; provision via IaC |
| App receives 403 when sending events | Runtime identity lacks data-plane role or wrong scope | Check principal and role assignment |
| App receives 404 | Wrong endpoint/name or resource not provisioned yet | Check pipeline outputs and deployment config |
| Deploy succeeds but app is not ready | Role assignment not propagated yet or network not ready | Use bounded readiness retries; verify RBAC/network |
| Multiple duplicate resources with random suffixes | Resources created per deployment | Use naming conventions and stable IaC state |
| Stack change deletes data | Retain/backup/deletion protection not configured | Review delete/replace actions and lifecycle policies |
| Plan always reports changes | Drift, computed fields, or unstable outputs | Investigate diff; do not apply blindly |
| Dev app accesses production | Shared principal/config/state | Separate environments and identities |
| Secrets appear in pipeline logs | Outputs/command line contain secrets | Use secret references, mask logs, and rotate |
| Runtime requires Contributor role | Code is creating resources or reading unnecessary management APIs | Move provisioning to pipeline; narrow permissions |
| Database migration runs on every pod | Migration attached to each replica's startup | Move to a migration job with locking/versioning |
| App rollback fails | New resource/schema incompatible with old version | Use expand-and-contract and compatible rollouts |

## 20. Pre-Production Checklist

- **Ownership:** Every resource/module has an owner and operational runbook.
- **IaC:** Production resources are declared and managed through a source of truth.
- **Separation:** Provisioning, application deployment, and business runtime have separate steps and identities.
- **Control plane:** Only the provisioner has permissions to create/update/delete resources.
- **Data plane:** The runtime only has send/receive/read/write permissions required by business logic.
- **Identity:** Managed Identity, IAM role, or Workload Identity is attached to the right workload.
- **Outputs:** Endpoints/resource IDs are passed via config; no secret values appear in outputs.
- **Configuration:** Spring Boot binds configuration using ConfigurationProperties and validates required fields.
- **Auto-provision:** Binder/SDK auto-create behavior is verified and disabled in production when IaC manages resources.
- **Database:** Migrations run via a controlled job; runtime does not hold broad DDL permissions.
- **Network:** Private endpoints, firewalls, DNS, TLS, and egress are declared.
- **Lifecycle:** Backup, retention, deletion protection, and replacement strategies are clear.
- **Change review:** Plans/change sets/what-if outputs are previewed; destructive changes require approval.
- **Drift:** A schedule for detection and a drift resolution process are in place.
- **Testing:** Negative tests prove the runtime cannot create/delete resources.
- **Observability:** Provisioning audits, runtime errors, readiness, and resource metrics are monitored.
- **Cost:** Tags/labels, budgets, quotas, and cleanup policies are configured.
- **Recovery:** Rollback/cutover and recovery plans exist when resource provisioning fails.

## 21. Summary

Separating resource provisioning from business operations establishes a clear boundary between the **control plane** and the **data plane**. An IaC pipeline uses CloudFormation, Bicep, Terraform, or Google Cloud Infrastructure Manager to create resources, networking, identities, and role assignments. The application pipeline deploys the artifact and passes non-sensitive outputs into Spring Boot. The runtime only uses SDK clients with a workload identity and least-privilege data plane permissions.

This organization reduces administrative permissions inside the application, prevents startup races across replicas, enables infrastructure change reviews, and controls resource lifecycles. When a resource is missing or permissions are misconfigured, the application surfaces a clear error for deployment/platform handling; it does not escalate its own permissions or create infrastructure inside business requests. Combining IaC plan/preview, externalized configuration, managed identities, database migration jobs, drift detection, and negative permission tests ensures Spring Boot systems integrated with AWS, Azure, and Google Cloud can be deployed reproducibly, audited, and operated safely.

## References

- [AWS CloudFormation stacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacks.html)
- [AWS CloudFormation change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- [AWS CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-stack.html)
- [What is Bicep?](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview)
- [Bicep What-If preview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if)
- [Bicep outputs](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/outputs)
- [Google Cloud Infrastructure Manager overview](https://docs.cloud.google.com/infrastructure-manager/docs/overview)
- [Infrastructure as Code on Google Cloud](https://docs.cloud.google.com/docs/terraform/iac-overview)
- [Azure Event Grid client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/messaging-eventgrid-readme?view=azure-java-stable)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
