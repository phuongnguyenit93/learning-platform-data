# Describing Infrastructure as Code and Passing Configuration Outputs to the Application

A Spring Boot application typically does not know the queue, topic, bucket, database, or endpoint names for each environment on its own. Those values only exist after infrastructure is created. Infrastructure as Code (IaC) declares and provisions resources; deployment **outputs** return identifiers and endpoints so the application deployment step can configure the right environment. At startup, Spring Boot binds those values into typed configuration and initializes SDK clients using a workload identity.

This lesson focuses on the output contract between IaC and the application. AWS CloudFormation, Azure Bicep, Terraform, and Google Cloud Infrastructure Manager differ in syntax, result format, and handling of sensitive data. The pipeline must normalize these differences, validate outputs before deployment, transfer non-sensitive values into a configuration store, and keep secrets in a secret manager. Spring Boot receives configuration via externalized configuration, checks for missing or invalid values before serving traffic, and uses the provisioned resources.

This lesson belongs to the **Application Deployment** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module provides hands-on practice integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of IaC outputs in the contract between the infrastructure pipeline and the application pipeline.
- Declare outputs with clear names, data types, descriptions, and scopes.
- Retrieve outputs from CloudFormation, Bicep, Terraform, and Google Cloud Infrastructure Manager.
- Distinguish between public outputs, sensitive outputs, and secret references.
- Normalize multi-cloud outputs into a versioned configuration contract.
- Translate outputs into environment variables, ConfigMaps, or runtime configuration files.
- Bind configuration using Spring Boot ConfigurationProperties and validate at startup.
- Understand property source precedence and relaxed binding rules.
- Use config trees or a secret manager to supply secrets without placing secrets into IaC outputs.
- Test the output contract, config binding, identity, and resource accessibility.
- Handle backward-compatible output changes and multi-version rollouts.

## 2. Outputs as the Contract Between Infrastructure and Application

IaC describes the resources that must exist; outputs return the values that downstream steps need. After creating a messaging resource, the application pipeline may need:

- Resource ID or ARN for auditing and role assignment.
- Endpoint or hostname for the SDK to connect.
- Topic, queue, subscription, or container name.
- Region, project, account, or subscription.
- Workload identity resource ID or principal ID to attach to the compute platform.
- Secret reference for the runtime to read credentials from a dedicated store.

Not every output needs to go into Spring Boot. Some outputs are meant only for the pipeline or platform automation. For example, a principal ID may be needed for the role assignment step, while the runtime only needs the endpoint and destination name.

A good output contract answers four questions:

1. Which resource and environment does this value belong to?
2. Which application or pipeline consumes it?
3. What are the data type and format of the value?
4. When the value changes, can consumers continue running or must they be rolled out again?

### 2.1. Classifying Outputs

| Type | Examples | Consumer |
|---|---|---|
| Resource identifier | ARN, Azure resource ID, project resource name | Pipeline, audit, IAM/RBAC |
| Endpoint | HTTPS URL, FQDN, hostname | Spring Boot SDK client |
| Destination name | Topic, queue, bucket, container | Spring Boot business service |
| Deployment metadata | Region, environment, contract version | Pipeline and application |
| Identity reference | Role ARN, managed identity client ID, service account email | Deployment platform |
| Secret reference | Key Vault URI, Secrets Manager ARN, Secret Manager resource name | Runtime secret integration |
| Secret value | Password, private key, SAS token, connection string with key | Secret manager; never put in regular outputs |

Do not place secret values in the output contract. Endpoints and resource names are generally not secrets, but they can still expose internal topology; supply them only to consumers that need them and avoid printing full outputs into public logs.

## 3. Designing a Multi-Cloud Output Contract

Each provider has its own naming conventions. The application should not need to understand template-specific output names or cloud-specific CLI syntax. The pipeline can translate provider-specific outputs into a unified intermediate structure.

Example JSON contract for an order processing service:

~~~json
{
  "contractVersion": 1,
  "service": "orders",
  "environment": "production",
  "cloudProvider": "azure",
  "region": "southeastasia",
  "messaging": {
    "endpoint": "orders-prod.servicebus.windows.net",
    "destination": "order-events"
  },
  "storage": {
    "endpoint": "https://ordersstateprod.blob.core.windows.net",
    "container": "order-checkpoints"
  },
  "database": {
    "host": "orders-prod.database.example",
    "port": 5432
  },
  "identity": {
    "mode": "workload"
  }
}
~~~

This contract contains only non-sensitive connection details and identifiers. There are no client secrets, account keys, or SAS tokens. The application uses the identity attached to the runtime to obtain tokens.

### 3.1. Naming Conventions

| Prefer | Avoid | Reason |
|---|---|---|
| messagingEndpoint | value1 | Clearly states the role |
| ordersTopicName | topic | Avoids ambiguity when multiple topics exist |
| checkpointContainerName | container | Expresses the workload purpose |
| contractVersion | version | Distinguishes contract version from app version |
| workloadIdentityResourceId | identity | Specifies the identifier type |
| secretReference | password | Passes a reference, not a secret |

Avoid output names containing values that change on every run such as timestamps or random deployment IDs unless they are genuinely part of the resource identity.

### 3.2. Should Outputs Be Primitive Values or Objects?

Primitive outputs are easy to consume in CLIs and pipelines. Objects group related values together, though consumers must understand the object schema.

- Use separate outputs for frequently referenced endpoints, names, and IDs.
- Use objects for a group of settings with a clear version and ownership.
- Do not rely on field ordering inside a JSON object.
- Do not use a single massive output containing all platform metadata.
- You can export both a resource ID and an endpoint if the two values serve different purposes.

## 4. AWS CloudFormation: Declaring and Reading Outputs

CloudFormation has an Outputs section in its template. Values appear in the stack's Outputs tab and can be retrieved with `describe-stacks`. Outputs can also be exported for other stacks to reference.

Example:

~~~yaml
Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-processing

  OrdersBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: orders-state-production
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

Outputs:
  OrdersQueueUrl:
    Description: Queue URL used by the orders runtime
    Value: !Ref OrdersQueue

  OrdersQueueArn:
    Description: Queue ARN used for IAM policy scope
    Value: !GetAtt OrdersQueue.Arn

  OrdersBucketName:
    Description: Bucket name used by the orders runtime
    Value: !Ref OrdersBucket
~~~

After the stack finishes, retrieve outputs using the AWS CLI:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-infrastructure-production \
  --query 'Stacks[0].Outputs' \
  --output json
~~~

The result is a list of outputs containing OutputKey, OutputValue, and optionally ExportName. The pipeline can select the exact keys:

~~~bash
QUEUE_URL="$(aws cloudformation describe-stacks \
  --stack-name orders-infrastructure-production \
  --query "Stacks[0].Outputs[?OutputKey=='OrdersQueueUrl'].OutputValue | [0]" \
  --output text)"

BUCKET_NAME="$(aws cloudformation describe-stacks \
  --stack-name orders-infrastructure-production \
  --query "Stacks[0].Outputs[?OutputKey=='OrdersBucketName'].OutputValue | [0]" \
  --output text)"
~~~

If an output does not exist, the CLI may return `None` or an empty value depending on the query/format. The pipeline must validate the value before exporting; never let the application receive the string `None` as a valid endpoint.

### 4.1. Exporting and Importing Between Stacks

A foundational stack can export an output:

~~~yaml
Outputs:
  SharedVpcId:
    Description: VPC used by application stacks
    Value: !Ref ApplicationVpc
    Export:
      Name: platform-production-vpc-id
~~~

Another stack references it using `Fn::ImportValue`:

~~~yaml
Resources:
  ApplicationSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId:
        Fn::ImportValue: platform-production-vpc-id
      CidrBlock: 10.20.10.0/24
~~~

Exports and `Fn::ImportValue` create tight coupling within the same AWS account and Region. While another stack imports an output, CloudFormation prevents deleting the exporting stack or changing the exported value until all imports are removed. For cross-account or cross-Region sharing, consider `Fn::GetStackOutput` or another contract-sharing mechanism.

Outputs do not automatically update the runtime configuration of a running process. When an endpoint or resource name changes, the pipeline must create a configuration revision and roll out the application accordingly.

### 4.2. Security Limitations of CloudFormation Outputs

CloudFormation does not mask or encrypt values in Outputs. Anyone with permission to view stack outputs can read the values. Never put passwords, private keys, access keys, or connection strings containing secrets here. If credentials must be passed, store them in AWS Secrets Manager or SSM Parameter Store and pass the ARN/name reference.

Stack outputs are also only available after the stack operation finishes; do not treat them as a service discovery endpoint that the runtime continuously queries.

## 5. Azure Bicep: Outputs, Modules, and Deployment History

Bicep defines outputs with the syntax:

~~~bicep
output outputName dataType = value
~~~

Example module creating a storage account and returning its endpoint and container name:

~~~bicep
param storageName string
param location string = resourceGroup().location

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
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
  name: 'order-checkpoints'
  properties: {
    publicAccess: 'None'
  }
}

@description('Resource ID consumed by platform automation.')
output storageAccountId string = storage.id

@description('Blob endpoint consumed by the Spring Boot runtime.')
output blobEndpoint string = storage.properties.primaryEndpoints.blob

@description('Checkpoint container name.')
output checkpointContainerName string = checkpointContainer.name
~~~

After the deployment succeeds, retrieve outputs using the Azure CLI:

~~~bash
az deployment group show \
  --resource-group rg-orders-production \
  --name orders-infrastructure \
  --query properties.outputs \
  --output json
~~~

The result contains an object keyed by output name, usually with `type` and `value`. The pipeline must extract the `value` field and verify the expected type before generating application configuration.

### 5.1. Outputs from Bicep Modules

A Bicep file can invoke another module and read its outputs via `moduleName.outputs.outputName`:

~~~bicep
module storage './modules/storage.bicep' = {
  name: 'orders-storage'
  params: {
    storageName: storageName
    location: location
  }
}

output blobEndpoint string = storage.outputs.blobEndpoint
output containerName string = storage.outputs.checkpointContainerName
~~~

This modularization lets the storage module own its resources and output contract; the application module receives only the values it needs.

### 5.2. Secure Outputs

Bicep supports the `@secure()` decorator for string or object outputs starting in Bicep version 0.35.1. Secure output values are not stored in deployment history and are not logged or displayed like regular outputs. This is useful when a module needs to pass a sensitive value to a parent module.

Even so, application design should prefer secret references to Azure Key Vault and Managed Identity. Do not turn outputs into a channel for passing passwords to pipelines if the runtime can read secrets directly using its identity. When secure outputs must be used, ensure every downstream step also treats the value as a secret and never logs it.

## 6. Terraform: Output Blocks and Sensitive Caveats

Terraform declares outputs in the root module:

~~~hcl
output "orders_topic_id" {
  description = "Pub/Sub topic resource ID for the orders publisher"
  value       = google_pubsub_topic.orders.id
}

output "orders_subscription_name" {
  description = "Subscription name consumed by the orders worker"
  value       = google_pubsub_subscription.orders.name
}

output "state_bucket_name" {
  description = "Bucket used for application state"
  value       = google_storage_bucket.application_state.name
}
~~~

After applying, read outputs:

~~~bash
terraform output
terraform output orders_topic_id
terraform output -json
~~~

The `terraform output -json` command is useful for automation because it returns objects with `value`, `type`, and `sensitive` metadata. The pipeline can parse it with `jq`, but it must filter for non-sensitive outputs and check `sensitive` before exporting.

Example:

~~~bash
set -euo pipefail

TF_OUTPUTS="$(terraform output -json)"

TOPIC_ID="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.orders_topic_id | select(.sensitive == false) | .value')"

BUCKET_NAME="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.state_bucket_name | select(.sensitive == false) | .value')"
~~~

### 6.1. Sensitive Does Not Mean Unstored

An output can be marked:

~~~hcl
output "database_password" {
  description = "Database credential"
  value       = random_password.database.result
  sensitive   = true
}
~~~

`sensitive = true` instructs Terraform to mask the value in certain CLI outputs and plan/apply displays. It **does not remove the value from Terraform state**. When running `terraform output -json` or `-raw`, the sensitive value can still be emitted in plaintext. Anyone who can read the state can access the data stored inside it.

Terraform offers `ephemeral` outputs in supported versions to avoid persisting certain values in state/plan, though with restrictions on where those values can be used. Do not rely on `ephemeral` as a justification to pass secrets through pipelines without a threat model. For Spring Boot applications, it is best to output only secret references and let the workload identity read secrets from a secret manager.

## 7. Google Cloud Infrastructure Manager and Terraform Outputs

Google Cloud Infrastructure Manager deploys Terraform configurations and manages deployments/revisions. In the apply result, `ApplyResults` contains an `outputs` map; each output includes a `value` and a `sensitive` flag.

A Terraform module can declare:

~~~hcl
output "orders_topic_name" {
  description = "Topic consumed by the orders publisher"
  value       = google_pubsub_topic.orders.name
}

output "orders_subscription_name" {
  description = "Subscription consumed by the orders worker"
  value       = google_pubsub_subscription.orders.name
}

output "orders_bucket_name" {
  description = "Storage bucket used by the application"
  value       = google_storage_bucket.orders.name
}
~~~

Example output structure in the apply result:

~~~json
{
  "outputs": {
    "orders_topic_name": {
      "sensitive": false,
      "value": "orders-events"
    },
    "orders_subscription_name": {
      "sensitive": false,
      "value": "orders-processing"
    },
    "orders_bucket_name": {
      "sensitive": false,
      "value": "orders-state-production"
    }
  }
}
~~~

The pipeline uses the apply result or the Infrastructure Manager API response to extract the outputs map. The `gcloud infra-manager deployments describe` command shows deployment and revision status; do not assume all outputs appear in every deployment describe format. Read the actual `ApplyResults.outputs` or the Terraform output source appropriate for your workflow.

The `sensitive` flag is metadata telling automation whether an output is sensitive; the pipeline must still enforce read permissions, logging controls, and storage restrictions. Do not treat this flag as a secret manager.

## 8. Comparing Outputs Across the Four Tools

| Criterion | CloudFormation | Bicep/ARM | Terraform | Google Cloud Infrastructure Manager |
|---|---|---|---|---|
| Declaration | Outputs | output name type = value | output block | Terraform output block |
| Result | Stack outputs | Deployment outputs | Terraform state/output | ApplyResults outputs |
| Common read command | describe-stacks | az deployment group show | terraform output -json | Apply result/API outputs |
| Module outputs | Nested stack/module or export/import | module.outputs.name | Child module outputs | Terraform module outputs |
| Sensitive handling | Does not mask outputs automatically | @secure() for string/object in supported versions | sensitive = true; state still retains value | Includes sensitive flag in output metadata |
| Cross-module reference | Export/import or stack output | Bicep module output | Module output | Terraform module output |
| Key risk to remember | Do not put secrets in Outputs | Regular outputs may appear in deployment history | JSON/raw can expose plaintext; state is sensitive | Check sensitive flag and restrict access to apply results |

All four tools return outputs, but outputs do not automatically become Spring Boot environment variables. The pipeline or deployment platform must perform the translation step.

## 9. Normalizing Outputs into a Configuration Manifest

A testable approach is to generate a JSON/YAML manifest after IaC apply succeeds. The manifest is a pipeline artifact containing the contract version, environment, and non-sensitive values.

Example YAML:

~~~yaml
contractVersion: 1
service: orders
environment: production
cloudProvider: azure
region: southeastasia
resources:
  messaging:
    endpoint: orders-prod.servicebus.windows.net
    destination: order-events
  storage:
    endpoint: https://ordersstateprod.blob.core.windows.net
    container: order-checkpoints
  database:
    host: orders-prod.database.example
    port: 5432
identity:
  mode: workload
~~~

Do not place passwords, client secrets, private keys, or connection strings with shared keys into the manifest. If a secret is needed, the manifest can include a reference:

~~~yaml
secrets:
  databaseCredential:
    provider: azure-key-vault
    reference: https://orders-vault.vault.azure.net/secrets/orders-db
~~~

The manifest should:
- Include `contractVersion`.
- Include `service` and `environment`.
- Undergo schema validation before publishing.
- Contain no secret values.
- Include the owner and creation timestamp in artifact metadata or pipeline attestation.
- Be stored with appropriate access controls and retention.
- Be linked to the deployment revision that produced the outputs.

Do not treat the manifest as a long-lived independent source of truth when values can be queried from the IaC deployment. It is a handoff artifact for deterministic application deployment.

## 10. Converting Outputs to Environment Variables

Spring Boot can read configuration from environment variables. The pipeline can map normalized outputs into environment variable names.

Example mapping:

| Output contract | Environment variable | Spring property |
|---|---|---|
| resources.messaging.endpoint | APP_CLOUD_MESSAGING_ENDPOINT | app.cloud.messaging.endpoint |
| resources.messaging.destination | APP_CLOUD_MESSAGING_DESTINATION | app.cloud.messaging.destination |
| resources.messaging.queueUrl | APP_CLOUD_MESSAGING_QUEUEURL | app.cloud.messaging.queue-url |
| resources.storage.endpoint | APP_CLOUD_STORAGE_ENDPOINT | app.cloud.storage.endpoint |
| resources.storage.container | APP_CLOUD_STORAGE_CONTAINER | app.cloud.storage.container |
| resources.storage.bucketName | APP_CLOUD_STORAGE_BUCKETNAME | app.cloud.storage.bucket-name |
| resources.database.host | APP_CLOUD_DATABASE_HOST | app.cloud.database.host |
| resources.database.port | APP_CLOUD_DATABASE_PORT | app.cloud.database.port |
| deployment.region | APP_CLOUD_REGION | app.cloud.region |
| deployment.projectId | APP_CLOUD_PROJECTID | app.cloud.project-id |
| identity.mode | APP_CLOUD_IDENTITY_MODE | app.cloud.identity.mode |

Spring Boot relaxed binding converts canonical property names to environment variables by replacing dots with underscores, removing hyphens, and converting to uppercase. For example, `app.cloud.messaging.queue-url` becomes `APP_CLOUD_MESSAGING_QUEUEURL`. Therefore, standardize property names and mappings in the pipeline; do not invent arbitrary variable names and hope the binder guesses right.

### 10.1. Reading CloudFormation Outputs in a Pipeline

Bash example fetching the queue URL and bucket name and exporting them for the deploy step:

~~~bash
set -euo pipefail

STACK_NAME="orders-infrastructure-production"

STACK_OUTPUTS="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' \
  --output json)"

QUEUE_URL="$(printf '%s' "$STACK_OUTPUTS" \
  | jq -er '.[] | select(.OutputKey == "OrdersQueueUrl") | .OutputValue')"

BUCKET_NAME="$(printf '%s' "$STACK_OUTPUTS" \
  | jq -er '.[] | select(.OutputKey == "OrdersBucketName") | .OutputValue')"

test -n "$QUEUE_URL"
test -n "$BUCKET_NAME"

export APP_CLOUD_MESSAGING_QUEUEURL="$QUEUE_URL"
export APP_CLOUD_STORAGE_BUCKETNAME="$BUCKET_NAME"
~~~

This illustrates a pipeline shell pattern. An SQS queue URL is the address of a specific queue, not a generic SQS service endpoint; therefore it binds to its own `queue-url` field. Similarly, an S3 bucket name and an Azure Blob container name are two distinct destination types and should not be collapsed into one field if the application supports both providers.

### 10.2. Reading Bicep Outputs in a Pipeline

~~~bash
set -euo pipefail

DEPLOYMENT_OUTPUTS="$(az deployment group show \
  --resource-group rg-orders-production \
  --name orders-infrastructure \
  --query properties.outputs \
  --output json)"

BLOB_ENDPOINT="$(printf '%s' "$DEPLOYMENT_OUTPUTS" \
  | jq -er '.blobEndpoint.value')"

CONTAINER_NAME="$(printf '%s' "$DEPLOYMENT_OUTPUTS" \
  | jq -er '.checkpointContainerName.value')"

test -n "$BLOB_ENDPOINT"
test -n "$CONTAINER_NAME"

export APP_CLOUD_STORAGE_ENDPOINT="$BLOB_ENDPOINT"
export APP_CLOUD_STORAGE_CONTAINER="$CONTAINER_NAME"
~~~

If the output has an unexpected structure or type, `jq -e` halts the pipeline instead of exporting empty values. Do not print full deployment outputs to logs if they might contain sensitive data.

### 10.3. Reading Terraform Outputs in a Pipeline

~~~bash
set -euo pipefail

TF_OUTPUTS="$(terraform output -json)"

TOPIC_NAME="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.orders_topic_name | select(.sensitive == false) | .value')"

SUBSCRIPTION_NAME="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.orders_subscription_name | select(.sensitive == false) | .value')"

export APP_CLOUD_MESSAGING_TOPIC="$TOPIC_NAME"
export APP_CLOUD_MESSAGING_SUBSCRIPTION="$SUBSCRIPTION_NAME"
~~~

If an output is marked `sensitive`, the filter returns nothing and the pipeline fails. This is intentional: secrets must flow through a secret manager rather than accidentally becoming plain environment variables.

### 10.4. Google Cloud Infrastructure Manager

When using Infrastructure Manager, the pipeline retrieves the `outputs` map from the apply result or API response. Each entry contains `sensitive` and `value`; transfer only entries marked non-sensitive. Record the deployment name and revision to trace which outputs were used during application deployment.

Use `gcloud infra-manager deployments describe` to verify the deployment is in a succeeded state and identify the current revision. Output extraction must read the proper apply result or workflow API response, rather than parsing an assumed output field from another response.

## 11. Spring Boot Externalized Configuration

Spring Boot enables the same artifact to run across multiple environments by reading configuration from sources outside the JAR:

- `application.yml` or `application.properties`.
- Configuration files placed alongside the artifact.
- Environment variables.
- Java system properties and command-line arguments.
- `SPRING_APPLICATION_JSON`.
- Configuration trees mounted from volumes/secrets.
- Config data imported from supported configuration sources.

Property sources have an order of precedence. Environment variables override values in configuration files packaged inside the JAR; command-line arguments typically take even higher precedence. Therefore, never hardcode production endpoints in the artifact and expect them to remain unchanged at deployment.

Example default file:

~~~yaml
app:
  cloud:
    provider: local
    region: local
    project-id: local-project
    messaging:
      endpoint: localhost
      destination: orders-local
      queue-url: http://localhost:4566/000000000000/orders-local
    storage:
      endpoint: http://localhost:10000/devstoreaccount1
      container: orders-local
      bucket-name: orders-local
~~~

In production, the deployment platform injects environment variables derived from the output contract to override local/default values.

### 11.1. External Configuration Files Outside the JAR

You can mount an `application-production.yml` file into the container and specify:

~~~bash
SPRING_CONFIG_ADDITIONALLOCATION="optional:file:/etc/orders-config/"
SPRING_PROFILES_ACTIVE="production"
~~~

Use `spring.config.additional-location` when you want to add files outside the JAR; `spring.config.location` replaces default locations and requires more care. Never bake production configuration files containing secrets into image layers or repositories.

### 11.2. Configuration Trees for Secrets

Spring Boot supports `configtree:` to read files inside a directory as properties. Example volume mount:

~~~text
/run/secrets/
  database/
    username
    password
~~~

Import configuration:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

The files are bound as properties matching their paths. This fits platforms that mount secret volumes; you can also use your cloud provider's secret integration so the runtime identity reads secrets directly.

## 12. Binding the Output Contract with ConfigurationProperties

Avoid injecting dozens of scattered values with `@Value`. Use `@ConfigurationProperties` to create a structured, strongly typed object with validation.

If the project does not yet include Jakarta Validation, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Example:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cloud")
public record CloudRuntimeProperties(
        @NotBlank String provider,
        @NotBlank String region,
        String projectId,
        @NotNull @Valid Messaging messaging,
        @NotNull @Valid Storage storage,
        @NotNull @Valid Database database) {

    @AssertTrue(message = "projectId is required when cloud provider is gcp")
    public boolean isProjectIdConfiguredForProvider() {
        return !"gcp".equalsIgnoreCase(provider)
                || (projectId != null && !projectId.isBlank());
    }

    public record Messaging(
            String endpoint,
            String destination,
            String queueUrl) {

        @AssertTrue(message = "Configure a messaging endpoint, destination or queue URL")
        public boolean isDestinationConfigured() {
            return (endpoint != null && !endpoint.isBlank())
                    || (destination != null && !destination.isBlank())
                    || (queueUrl != null && !queueUrl.isBlank());
        }
    }

    public record Storage(
            String endpoint,
            String container,
            String bucketName) {

        @AssertTrue(message = "Configure a storage endpoint, container or bucket name")
        public boolean isStorageLocationConfigured() {
            return (endpoint != null && !endpoint.isBlank())
                    || (container != null && !container.isBlank())
                    || (bucketName != null && !bucketName.isBlank());
        }
    }

    public record Database(
            @NotBlank String host,
            @Positive int port) {
    }
}
~~~

Register the properties using scanning:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

When a required property is missing or invalid, Spring Boot reports a binding/validation error and halts startup. This is far better than letting the application start and later discovering an empty endpoint while handling a request.

### 12.1. Do Not Mix the Output Contract with Credentials

`CloudRuntimeProperties` contains only endpoints, destinations, and resource names. Credentials are built using the provider's SDK credential chain. For example, Azure uses `DefaultAzureCredential`, AWS uses the default credentials provider chain, and Google Cloud uses Application Default Credentials or Workload Identity.

Do not add `accessKey`, `clientSecret`, or `sasToken` to this record if the application can obtain tokens via workload identity. When secrets are strictly necessary, bind them from a config tree or separate secret integration and protect the property source.

## 13. Creating SDK Clients from Bound Configuration

Azure Event Grid publisher example. This bean is registered only under the Azure/Event Grid profile and the output contract must provide the messaging endpoint:

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
            CloudRuntimeProperties properties,
            TokenCredential credential) {
        return new EventGridPublisherClientBuilder()
                .endpoint(properties.messaging().endpoint())
                .credential(credential)
                .buildEventGridEventPublisherClient();
    }
}
~~~

This example illustrates the wiring principle. If `messaging.endpoint` is a Service Bus hostname or the URL of another service, you must use the corresponding SDK client builder; do not use an Event Grid client for every messaging service.

For AWS S3, a Spring service can inject an `S3Client` built with `S3Client.builder()` and the default credentials provider. For Google Pub/Sub, use a client initialized with Application Default Credentials or workload identity. In all three cases, endpoints/resource names come from the config contract, while credentials come from the runtime identity.

AWS SDK for Java v2 example: the region comes from the output/config contract, while the credentials provider resolves the workload's credential chain. The SDK automatically selects the service endpoint for the region when no custom endpoint is configured:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class S3ClientConfiguration {

    @Bean
    S3Client s3Client(CloudRuntimeProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

Google Cloud Pub/Sub example: project ID and topic name come from bound configuration; `Publisher` uses Application Default Credentials to obtain the runtime identity:

~~~java
import com.google.cloud.pubsub.v1.Publisher;
import com.google.pubsub.v1.TopicName;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PubSubClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    Publisher ordersPublisher(CloudRuntimeProperties properties)
            throws IOException {
        return Publisher.newBuilder(TopicName.of(
                properties.projectId(),
                properties.messaging().destination())).build();
    }
}
~~~

These examples require the corresponding dependencies for AWS SDK for Java v2 (S3) or the Google Cloud Pub/Sub client library. In a real application, register client beans only for the active provider/profile; do not initialize all three clients if a deployment targets only one cloud.

Clients should generally be singleton beans reused across the application lifecycle. Never construct SDK clients per request or call management APIs to create resources inside business handlers.

## 14. Validating the Contract Before Deployment

The pipeline should not merely check that outputs exist. It must validate structure and values:

- `contractVersion` is within the set of versions supported by the application.
- `service` and `environment` match the deployment target.
- Provider matches the image/config profile.
- Endpoints use valid schemes and hostnames.
- Destination names are non-empty.
- Resource IDs belong to the expected account/subscription/project.
- No sensitive outputs appear in the manifest.
- All required Spring Boot properties have mappings.
- Resources have completed provisioning and role assignments have been created.
- Workload identity is attached to the compute platform before smoke tests.

You can use JSON Schema or a small validation step in the pipeline to verify the manifest. Avoid logic like "if empty, create resource"; a missing output is a provisioning/configuration pipeline error that must be fixed at the source.

### 14.1. Contract Versioning

When changing output names or structure:
- Increment `contractVersion` if consumers require updates.
- You may add optional fields without breaking older consumers.
- Never change the meaning of an existing field while keeping the same version.
- Maintain a compatibility window during multi-version rollouts.
- Record both the producer IaC revision and consumer application version.
- Include tests verifying the new manifest binds cleanly to the application.

If you change `messaging.destination` into a nested object, older applications may fail to bind. Introduce a new contract version or retain the legacy field during the transition period.

## 15. Rollouts When Outputs Change

Changing an output may mean an endpoint, queue, or resource has changed. The pipeline should sequence provisioning and application rollout in order:

1. Provision the new resource.
2. Grant permissions to the workload identity on the new resource.
3. Wait for role assignment/network propagation.
4. Emit the new output contract.
5. Deploy the application reading the new outputs.
6. Run readiness/smoke tests.
7. Shift traffic or producers to the new resource.
8. Verify that old backlogs and data have finished processing.
9. Revoke old permissions and delete the old resource in a separate change.

Never change the output of an active resource and immediately delete the old one. Queues may still hold messages, databases may have open transactions, or older consumers may still be running. Output versions must be tied to a rollback-capable rollout.

## 16. Outputs, Secret References, and Secret Values

| Value | Examples | Storage Location |
|---|---|---|
| Endpoint | Event Grid URL, Pub/Sub endpoint | IaC output/config manifest |
| Resource ID | ARN, Azure resource ID, project resource name | IaC output |
| Destination | Queue/topic/container name | IaC output/config manifest |
| Workload identity reference | Role ARN, managed identity client ID | IaC output or deployment metadata |
| Secret reference | Key Vault URI, Secrets Manager ARN, Secret Manager version path | Config manifest or platform secret reference |
| Secret value | Password, private key, shared access key | Secret manager, not regular outputs |

Note the key differences:
- CloudFormation Outputs do not mask values.
- Terraform `sensitive` only masks certain displays; state still stores the value and JSON/raw outputs can expose it.
- Bicep supports secure outputs in supported versions, though secrets should still be managed through Key Vault/identity whenever possible.
- Infrastructure Manager flags outputs as `sensitive` in apply results; pipelines must still restrict permissions and avoid logging payloads.

Never assume a redacted output means the value is inaccessible. Audit who can read deployment history, Terraform state, pipeline artifacts, and logs.

## 17. Read Permissions for Outputs and Pipeline Artifacts

Outputs may expose internal details such as private endpoints, resource IDs, and destination names. Restrict:
- Who can read CloudFormation stack outputs.
- Who can read Azure deployment history.
- Who can read Terraform state and Infrastructure Manager deployment results.
- Who can download manifest artifacts.
- Which jobs can inject outputs into application deployments.
- Which logs can print outputs and metadata.

Separate artifacts by environment and service. Never let a dev pipeline download a production manifest or overwrite another service's configuration artifact. If outputs are passed between jobs, use an artifact store with proper access control and retention.

## 18. Readiness and Startup Validation in Spring Boot

Spring Boot should verify that configuration is complete and valid before accepting traffic. This can be divided into:

- **Configuration validation:** required fields are non-empty, URLs/ports are valid, provider is supported.
- **Client construction:** SDK clients can be built from endpoints and the credential chain.
- **Connectivity check:** test dependency connectivity when appropriate.
- **Authorization check:** verify the workload identity has required data-plane permissions.
- **Readiness:** report ready only when the application is fit to serve traffic.
- **Liveness:** reflect only whether the process is alive; avoid restarting pods just because a cloud dependency is temporarily slow.

Never call create topic/queue/bucket inside readiness checks. If a resource does not exist yet, readiness must fail so the pipeline/platform fixes IaC or output mapping.

Not every dependency needs to be pinged during startup. For services subject to throttling or transient startup dependencies, use bounded retries and readiness states rather than hanging startup indefinitely.

## 19. Sample CI/CD Pipeline

A pipeline can include the following stages:

~~~mermaid
flowchart TD
    SRC["IaC source"] --> VALIDATE["Lint and validate"]
    VALIDATE --> PLAN["Plan / what-if / change set"]
    PLAN --> APPROVE["Review infrastructure diff"]
    APPROVE --> APPLY["Apply IaC"]
    APPLY --> OUTPUT["Collect provider outputs"]
    OUTPUT --> CONTRACT["Normalize and validate contract"]
    CONTRACT --> ARTIFACT["Publish config artifact"]
    ARTIFACT --> DEPLOY["Deploy Spring Boot"]
    DEPLOY --> BIND["Bind and validate config"]
    BIND --> SMOKE["Identity and connectivity smoke test"]
    SMOKE --> TRAFFIC["Enable traffic"]
~~~

Key steps to observe:

1. Validate IaC source and output schema.
2. Generate a plan/change set/what-if for review.
3. Apply resources and role assignments.
4. Wait for provisioning to complete.
5. Fetch outputs from the exact deployment revision.
6. Normalize outputs into a versioned contract manifest.
7. Exclude secret values; check `sensitive` flags.
8. Publish artifacts scoped by environment.
9. Inject environment variables/config files into the deployment.
10. Deploy the application and verify configuration binding.
11. Run smoke tests using the workload identity.
12. Shift traffic only when readiness passes.

Application images can be built in parallel with IaC planning to save time, but never deploy a revision that depends on resources before those resources, roles, and networking are ready.

## 20. Testing the Output Contract and Application Configuration

| Scenario | How to Test | Expected Result |
|---|---|---|
| Complete output fields | Apply IaC to a test environment | Manifest contains all required fields |
| Missing output field | Remove an output in a test fixture | Contract validation fails |
| Wrong output type | Return port as text or endpoint as object | Schema validation fails |
| Wrong environment output | Supply dev manifest to prod deployment | Pipeline rejects it |
| Sensitive output | Mark an output sensitive | Excluded from regular manifest |
| CloudFormation stack in progress | Read outputs while stack is still running | Pipeline waits or fails gracefully |
| Bicep module output | Rename a module output | Consumer contract test catches mismatch |
| Terraform sensitive JSON | Mark sensitive then run output -json | Pipeline does not export the value |
| Infrastructure Manager result | Read ApplyResults outputs | Only entries with sensitive=false are used |
| Spring config binding | Inject environment variables into test context | ConfigurationProperties binds correctly |
| Missing required property | Omit endpoint or destination | Application context fails validation |
| Override precedence | Supply env var differing from YAML file | Env var value takes effect |
| Identity | Run integration test with workload identity | Only authorized data-plane actions succeed |
| Wrong resource | Provide nonexistent endpoint/resource name | Readiness/smoke test fails clearly |
| Output version rollout | Deploy new manifest version | Application supports or intentionally rejects version |

Unit tests can use `ApplicationContextRunner` or `@SpringBootTest` to verify binding and validation. Integration tests must run in a cloud test environment to verify actual IAM/RBAC, endpoints, networking, and resources.

## 21. Common Issues and Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Empty environment variable | Pipeline queried wrong output key | Validate manifest before deployment |
| App binds wrong property | Variable name does not follow relaxed binding | Standardize property/env mapping |
| Spring uses value inside JAR | Env var not injected or wrong property name | Inspect property sources and configprops |
| CloudFormation output missing | Stack incomplete or wrong key | Wait for stack completion; check describe-stacks |
| Bicep output is null | Conditional resource or wrong module output | Check conditions and output expressions |
| Terraform output masked | Output marked sensitive | Do not fetch secrets from outputs; use secret manager |
| Terraform state leaks credentials | Secrets stored in state | Rotate credentials and protect state backend |
| GCP output missing | Reading deployment metadata instead of apply result outputs | Use ApplyResults or the right output source |
| App receives 403 | Workload identity lacks data-plane role | Verify role and propagation |
| App receives 404 | Wrong endpoint/destination or resource does not exist | Compare output against actual resource ID |
| Dev uses prod resources | Manifest/artifact used in wrong environment | Separate artifacts and policies per environment |
| Endpoint change causes downtime | Switched output without compatible rollout | Provision new, deploy, cutover, then retire old |

## 22. Pre-Production Checklist

- **Output contract:** Has names, types, descriptions, version, and owner.
- **Provider mapping:** CloudFormation/Bicep/Terraform/Infrastructure Manager outputs are normalized.
- **Validation:** Pipeline checks required fields, types, environment, and resource scope.
- **Sensitive data:** No secret values in regular outputs, manifests, logs, or images.
- **Access control:** Only required pipelines/jobs can read outputs and artifacts.
- **Spring binding:** ConfigurationProperties has validation and fails fast.
- **Property precedence:** Environment/config overrides are tested.
- **Identity:** SDK clients use appropriate workload identity/credential chains.
- **Runtime:** Application only uses provisioned resources.
- **Readiness:** Connectivity and permissions are checked without creating resources.
- **Versioning:** Output contract is versioned with compatibility rules.
- **Rollout:** Plan exists for endpoint or resource name changes.
- **Secrets:** Only secret references are passed; runtime reads secrets with least privilege.
- **Audit:** IaC revision, output artifact, and application revision are traceable together.
- **Testing:** Tests cover missing outputs, wrong types, wrong env, sensitive outputs, 403/404, and config binding.
- **Recovery:** Rollback/cutover plan exists and old resources are retained long enough to drain in-flight data.

## 23. Summary

IaC outputs act as the data contract between infrastructure provisioning and application deployment. CloudFormation returns stack outputs; Bicep returns deployment/module outputs; Terraform returns output values from state; Google Cloud Infrastructure Manager returns an `outputs` map in apply results. Pipelines must read the right source, validate types and environments, normalize them into a configuration contract, and pass non-sensitive values into Spring Boot.

Spring Boot externalized configuration enables the same artifact to run across multiple environments. Use `ConfigurationProperties` to bind and validate endpoints and resource names; use environment variables, config files, or config trees to supply values. Secrets should be referenced via Key Vault, Secrets Manager, or Secret Manager and read using workload identity. When output contracts are versioned, pipelines validate them, and applications fail fast on missing configuration, deploying Spring Boot across AWS, Azure, and Google Cloud becomes repeatable, auditable, and safer.

## References

- [CloudFormation Outputs syntax](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html)
- [Export and import CloudFormation outputs](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html)
- [Outputs in Bicep](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/outputs)
- [Bicep modules and module outputs](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/modules)
- [Use Bicep to manage secrets](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/scenarios-secrets)
- [Terraform output values](https://developer.hashicorp.com/terraform/language/values/outputs)
- [Terraform output block reference](https://developer.hashicorp.com/terraform/language/block/output)
- [Infrastructure Manager ApplyResults](https://docs.cloud.google.com/infrastructure-manager/docs/reference/rest/v1/ApplyResults)
- [View Infrastructure Manager deployments](https://docs.cloud.google.com/infrastructure-manager/docs/view-deployments)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
