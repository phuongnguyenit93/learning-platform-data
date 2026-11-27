# First Connection to a Service Using a Least-Privilege Identity

## 1. Objectives of the Lab

A Spring Boot application should never connect to a cloud service using an administrator account or access keys copied into a configuration file. The application needs its own runtime identity, obtains short-lived credentials from the runtime environment, and is granted only the permissions required for its business logic.

In this lab, you build a Spring Boot endpoint that reads metadata for an object with a known name in object storage. The same business contract is implemented across three providers:

- Amazon S3 with Spring Cloud AWS and AWS SDK for Java 2.x.
- Google Cloud Storage with Spring Framework on Google Cloud.
- Azure Blob Storage with Spring Cloud Azure and Azure Identity.

You choose one provider to run the first lab. The remaining two adapters help you compare how each cloud provisions identities, assigns permissions, and creates clients.

This lesson belongs to the **Hands-on Integration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via their corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson lays the foundation for subsequent integration lessons: the application can authenticate with the cloud, access the right resource, and prove that write permissions are not granted unnecessarily.

After completing this lesson, you will be able to:

- Distinguish between authentication and authorization.
- Create a dedicated runtime identity for a Spring Boot workload.
- Use default credentials providers or workload identity instead of long-lived keys.
- Grant object read permissions on the right bucket/container and at the right scope.
- Configure Spring Cloud AWS, Spring Framework on Google Cloud, or Spring Cloud Azure.
- Use a shared business interface with provider-specific adapters.
- Verify that read requests succeed and write requests are denied.
- Diagnose errors related to credentials, IAM, endpoints, regions, and resource scopes.

> **Lab scope:** This lab uses a metadata read operation for an object with a known name (HEAD/GET properties). There is no need to list buckets/containers, upload, overwrite, or delete. The examples use Java 17+ for records; if your project uses an older Java version, replace records with standard classes. Choose a BOM compatible with the Spring Boot version in use; do not copy versions from one provider to another.

## 2. Architecture and Business Contract

We use a small scenario: a document API service needs to know the size, Content-Type, and version token of a file before passing the file into a processing pipeline.

~~~mermaid
flowchart LR
    CLIENT["Client / curl"] --> API["Spring Boot API"]
    API --> PORT["ObjectMetadataReader"]
    PORT --> AWS["S3 adapter"]
    PORT --> GCP["GCS adapter"]
    PORT --> AZURE["Azure Blob adapter"]
    AWS --> S3["Amazon S3"]
    GCP --> GCS["Google Cloud Storage"]
    AZURE --> BLOB["Azure Blob Storage"]
    ID["Runtime identity"] -. "Temporary credentials / token" .-> AWS
    ID -. "ADC access token" .-> GCP
    ID -. "Microsoft Entra token" .-> AZURE
~~~

The business contract does not need to know which provider is being used:

~~~java
public record ObjectMetadataView(
        String provider,
        String objectKey,
        long sizeBytes,
        String contentType,
        String versionToken) {
}

public interface ObjectMetadataReader {
    ObjectMetadataView readConfiguredObject();
}
~~~

The version token is the value returned by the provider: ETag on S3/Azure or generation on GCS. Do not assume these tokens share the same format or semantics.

Test endpoint:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/storage")
public class StorageMetadataController {

    private final ObjectMetadataReader metadataReader;

    public StorageMetadataController(ObjectMetadataReader metadataReader) {
        this.metadataReader = metadataReader;
    }

    @GetMapping("/sample")
    public ObjectMetadataView sample() {
        return metadataReader.readConfiguredObject();
    }
}
~~~

The endpoint only reads a single configured object. It does not accept arbitrary bucket/container names or object keys from query parameters. When deploying to production, authenticate API callers and verify business authorization before returning metadata.

## 3. Authentication and Authorization

These two steps answer two different questions:

- **Authentication:** Which identity is making the request? For example, an AWS IAM role, a Google Cloud service account, or an Azure managed identity.
- **Authorization:** What actions is that identity allowed to perform on which resources? For example, reading an object in a bucket, receiving messages from a queue, or querying a table.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Identity as Identity provider
    participant Policy as IAM / RBAC
    participant Service as Managed service

    App->>Identity: Request credential/token
    Identity-->>App: Short-lived credential
    App->>Service: Send authenticated request
    Service->>Policy: Check principal, action, resource
    Policy-->>Service: Allow / Deny
    Service-->>App: Metadata or authorization error
~~~

There are three types of identities that typically appear in a deployment:

1. **Developer identity:** a developer running the application on their personal machine.
2. **Deployer/provisioning identity:** the account that creates buckets, configures IAM, creates services, or assigns roles.
3. **Runtime identity:** the identity used by the Spring Boot process when calling cloud services.

The runtime identity should not inherit all permissions of the deployer. Just because the deployer has permissions to create buckets, modify IAM, and delete data does not mean the running application needs those permissions as well.

## 4. Least-Privilege Permissions for Reading Metadata

The lab only needs to read metadata for an object with a known name. The table below shows the required permissions and the permissions that must not be granted.

| Provider | Runtime identity | Required read permission | Permissions not granted in this lab |
| --- | --- | --- | --- |
| AWS S3 | Workload IAM role | s3:GetObject on the object ARN | s3:PutObject, s3:DeleteObject, s3:ListBucket |
| Google Cloud Storage | Service account/workload identity | storage.objects.get on the bucket | storage.objects.create, storage.objects.update, storage.objects.delete |
| Azure Blob Storage | Managed identity or service principal | Storage Blob Data Reader at container scope | Storage Blob Data Contributor, Storage Blob Data Owner |

Some built-in roles include additional permissions:

- AWS s3:GetObject is sufficient for HEAD requests on an object with a known key. s3:ListBucket is not needed if the application does not list buckets. When the object does not exist and the principal lacks s3:ListBucket, S3 may return 403 instead of 404.
- Google roles/storage.objectViewer includes both storage.objects.get and storage.objects.list. If you want to omit list permission, you can create a custom role containing only storage.objects.get and assign it at bucket scope.
- Azure Storage Blob Data Reader allows reading and listing blobs. Assigning the role at container scope narrows its reach; if even narrower permissions are needed, consider a custom Azure RBAC role and an appropriate scope.

Note: these data-read permissions are not metadata-only permissions. For example, s3:GetObject allows retrieving object content; storage.objects.get allows reading object data; Storage Blob Data Reader also allows reading blob content. The lab only calls HEAD/properties APIs to avoid downloading the body, but IAM still grants data-read permission. If API users are only allowed to view selected metadata, filter the fields at the application layer and avoid returning sensitive object names or metadata.

Do not confuse resource management roles with data access roles. For example, Azure Contributor manages the resource and does not implicitly grant permission to read blob data; a data role such as Storage Blob Data Reader is required.

## 5. Choosing Dependencies and BOMs

Each provider has its own BOM. In a single-provider lab, simply add the corresponding starter. If a real application must integrate multiple providers simultaneously, separate adapters into appropriate modules or profiles, check dependency convergence, and run integration tests for each combination.

### 5.1. AWS

Spring Cloud AWS 3.x uses AWS SDK for Java 2.x:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
</dependencies>
~~~

The starter auto-configures S3Client, the region provider, and the credentials provider. Use a BOM compatible with Spring Boot; do not add a separate AWS SDK version without a specific reason.

### 5.2. Google Cloud

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_GCP_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
~~~

The starter auto-configures a Storage bean based on Spring Framework on Google Cloud's CredentialsProvider. The client library uses Application Default Credentials (ADC) to discover the appropriate identity for the environment.

### 5.3. Azure

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AZURE_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

Spring Cloud Azure supports integrating Blob Storage with the Spring Resource abstraction. In the adapter example below, we use BlobServiceClient and DefaultAzureCredential directly to clearly show the connection point between identity and the SDK. You can use the starter/resource abstraction instead of manually building the client once your project standardizes its Azure configuration.

**Version selection rule:** check the Spring Boot/Spring Cloud compatibility matrix for the exact BOM before building. Do not use the same version number for AWS, Google, and Azure just because they are all Spring integration libraries.

## 6. Preparing Sample Resources

Create a test bucket or container for the lab and an object with a fixed key:

~~~text
bucket/container: training-documents-lab
object key:       incoming/sample.txt
content type:     text/plain
content:          first cloud integration
~~~

The resource must be created beforehand by someone with provisioning permissions. The application's runtime identity only reads this object.

You can use a small text file for testing. Do not use customer data or sensitive data in your first hands-on lab.

Separate configuration values from source code:

~~~yaml
app:
  storage:
    aws:
      bucket: training-documents-lab
      key: incoming/sample.txt
    gcp:
      bucket: training-documents-lab
      key: incoming/sample.txt
    azure:
      endpoint: https://YOUR_STORAGE_ACCOUNT.blob.core.windows.net
      container: training-documents-lab
      blob: incoming/sample.txt
~~~

The properties can coexist in the sample file, but only the adapter belonging to the active profile is enabled. In real environments, store environment configuration via deployment config or appropriate secret/config management.

## 7. Track A — Amazon S3 with Spring Cloud AWS

### 7.1. Create an object-read-only IAM policy

Create a policy dedicated to the application. Restrict the resource ARN to the exact object:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOneTrainingObject",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::training-documents-lab/incoming/sample.txt"
    }
  ]
}
~~~

If the application needs to read all objects under the incoming/ prefix, change the resource to arn:aws:s3:::training-documents-lab/incoming/*. Only add s3:ListBucket when business logic genuinely requires listing objects; that permission applies to the bucket ARN, not the object ARN.

Do not add s3:PutObject or s3:DeleteObject. If the application later reads bytes from objects encrypted with SSE-KMS, evaluate adding kms:Decrypt on the KMS key and key policy. The current lab only calls HEAD to retrieve metadata.

### 7.2. Attach the role to the workload

Create an IAM role with a trust policy appropriate for the runtime environment, then attach the object-read policy above.

| Environment | How identity is provided |
| --- | --- |
| EC2 | Instance profile containing an IAM role |
| ECS | Task role attached to the task definition |
| EKS | IAM Roles for Service Accounts (IRSA) or Pod Identity mechanism chosen by the organization |
| Local development | AWS IAM Identity Center/SSO profile |

Do not attach permissions to a shared EC2 instance role if the application actually runs on an ECS task or EKS pod that can receive its own role. Task roles/IRSA isolate permissions across workloads.

Sign in locally using SSO:

~~~bash
aws configure sso --profile storage-reader
aws sso login --profile storage-reader
~~~

Select the profile in the terminal running Spring Boot:

~~~bash
export AWS_PROFILE=storage-reader
~~~

PowerShell:

~~~powershell
$env:AWS_PROFILE = "storage-reader"
~~~

The AWS SDK uses the default credentials provider chain. Spring Cloud AWS also auto-configures DefaultCredentialsProvider, which can obtain credentials from profiles, web identity, ECS task credentials, or EC2 instance profiles. Do not put static access keys/secret keys in application.yml.

### 7.3. Configure the region

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Change the region to match your bucket. If you already use the AWS_REGION environment variable or the environment's region provider, you may not need to declare a static value in the file.

### 7.4. Write the metadata reader adapter

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;

@Component
@Profile("aws")
public class S3ObjectMetadataReader implements ObjectMetadataReader {

    private final S3Client s3Client;
    private final String bucket;
    private final String key;

    public S3ObjectMetadataReader(
            S3Client s3Client,
            @Value("${app.storage.aws.bucket}") String bucket,
            @Value("${app.storage.aws.key}") String key) {
        this.s3Client = s3Client;
        this.bucket = bucket;
        this.key = key;
    }

    @Override
    public ObjectMetadataView readConfiguredObject() {
        HeadObjectResponse response = s3Client.headObject(
                HeadObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build());

        return new ObjectMetadataView(
                "aws-s3",
                key,
                response.contentLength(),
                response.contentType(),
                response.eTag());
    }
}
~~~

HeadObject reads metadata without downloading the body. This API requires s3:GetObject permission on the object. Do not call listObjectsV2 just to find an object whose name is already known.

### 7.5. Verify identity and permissions

Check the AWS identity from the same profile:

~~~bash
aws sts get-caller-identity --profile storage-reader
~~~

Check the object metadata:

~~~bash
aws s3api head-object \
  --bucket training-documents-lab \
  --key incoming/sample.txt \
  --profile storage-reader
~~~

If the second command returns metadata, the current identity has permission to read the object. When running Spring Boot on EC2/ECS/EKS, the SDK retrieves the workload's role credentials; get-caller-identity results from a developer machine do not prove that the production role is attached properly.

## 8. Track B — Google Cloud Storage

### 8.1. Create a dedicated service account

Example:

~~~bash
gcloud iam service-accounts create spring-storage-reader \
  --project=training-platform-dev \
  --display-name="Spring Storage Reader"
~~~

The runtime identity looks like:

~~~text
spring-storage-reader@training-platform-dev.iam.gserviceaccount.com
~~~

Do not grant Owner, Editor, or Storage Admin to this service account.

### 8.2. Grant read-only permissions

A simple approach is assigning roles/storage.objectViewer at bucket scope:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://training-documents-lab \
  --member="serviceAccount:spring-storage-reader@training-platform-dev.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

This role contains both storage.objects.get and storage.objects.list. If you want to omit list permission, create a custom role with only storage.objects.get:

~~~bash
gcloud iam roles create gcsObjectReader \
  --project=training-platform-dev \
  --title="GCS Object Reader" \
  --description="Read object data and metadata without listing objects" \
  --permissions=storage.objects.get \
  --stage=GA
~~~

Bind the custom role at bucket level:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://training-documents-lab \
  --member="serviceAccount:spring-storage-reader@training-platform-dev.iam.gserviceaccount.com" \
  --role="projects/training-platform-dev/roles/gcsObjectReader"
~~~

The storage.objects.get permission allows reading objects and metadata. It does not grant create, update, delete, or list. Creating a custom role requires appropriate IAM administration permissions; that is the responsibility of the provisioning identity.

### 8.3. Local ADC and production service identity

To run locally using a user account that has read permission on the bucket:

~~~bash
gcloud auth application-default login
~~~

ADC is the credential discovery mechanism of Google Cloud client libraries. Credentials created by gcloud auth login for the CLI are different from credentials created by gcloud auth application-default login for applications.

If you want to test locally using the exact service account, you can use impersonation:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=spring-storage-reader@training-platform-dev.iam.gserviceaccount.com
~~~

The user performing impersonation needs permission to create tokens for the service account. Do not download a service account JSON key to your machine just to run the lab.

When deploying to Cloud Run, attach the service account as the service identity:

~~~bash
gcloud run deploy document-api \
  --image=REGION-docker.pkg.dev/training-platform-dev/apps/document-api:latest \
  --region=asia-southeast1 \
  --service-account=spring-storage-reader@training-platform-dev.iam.gserviceaccount.com
~~~

In production on Google Cloud, prefer a service identity attached to the workload and ADC via the metadata server. Do not set GOOGLE_APPLICATION_CREDENTIALS pointing to a JSON key on Cloud Run.

### 8.4. Configure the starter and adapter

The starter auto-creates the Storage bean:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("gcp")
public class GcsObjectMetadataReader implements ObjectMetadataReader {

    private final Storage storage;
    private final String bucket;
    private final String key;

    public GcsObjectMetadataReader(
            Storage storage,
            @Value("${app.storage.gcp.bucket}") String bucket,
            @Value("${app.storage.gcp.key}") String key) {
        this.storage = storage;
        this.bucket = bucket;
        this.key = key;
    }

    @Override
    public ObjectMetadataView readConfiguredObject() {
        Blob blob = storage.get(BlobId.of(bucket, key));

        if (blob == null) {
            throw new IllegalStateException(
                    "Configured object not found");
        }

        return new ObjectMetadataView(
                "google-cloud-storage",
                key,
                blob.getSize(),
                blob.getContentType(),
                String.valueOf(blob.getGeneration()));
    }
}
~~~

Configure the project if the starter needs an explicit value:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: training-platform-dev
~~~

Do not put a private key into spring.cloud.gcp.storage.credentials.encoded-key. Configuring a credential file/encoded key is only for situations where it is truly necessary and must be managed as a secret; workload identity/ADC is usually the better choice.

### 8.5. Verify permissions

Check the identity currently used by the gcloud CLI:

~~~bash
gcloud auth list
~~~

Check the object:

~~~bash
gcloud storage objects describe \
  gs://training-documents-lab/incoming/sample.txt
~~~

Note: gcloud commands use the CLI credential; the Spring application uses ADC. The two credentials may belong to two different principals. Verify the runtime principal via Cloud Run/GKE/VM configuration and audit logs when needed.

## 9. Track C — Azure Blob Storage

### 9.1. Create a managed identity

In Azure environments such as App Service, Container Apps, or VMs, enable a system-assigned managed identity or create a user-assigned managed identity. A managed identity is a principal in Microsoft Entra ID; the application does not have to store a client secret.

If using a user-assigned identity, note the principal/object ID and client ID. If using a system-assigned identity, retrieve the principal ID after enabling the identity on the resource.

### 9.2. Assign the role at container scope

A container scope looks like:

~~~text
/subscriptions/SUBSCRIPTION_ID/resourceGroups/RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/STORAGE_ACCOUNT/blobServices/default/containers/training-documents-lab
~~~

Assign the Storage Blob Data Reader role to the managed identity:

~~~bash
az role assignment create \
  --assignee-object-id=MANAGED_IDENTITY_PRINCIPAL_ID \
  --assignee-principal-type=ServicePrincipal \
  --role="Storage Blob Data Reader" \
  --scope="/subscriptions/SUBSCRIPTION_ID/resourceGroups/RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/STORAGE_ACCOUNT/blobServices/default/containers/training-documents-lab"
~~~

If testing locally with a developer account, sign in to the Azure CLI and assign the data-read role at container scope to the appropriate Microsoft Entra user. Do not use Storage Blob Data Contributor just to read metadata.

Storage Blob Data Reader is a convenient built-in role for the lab, though it includes both read and list blob permissions. When narrower permissions are needed, you can design a custom role with appropriate data actions and scope.

### 9.3. Local and production credentials

Local development:

~~~bash
az login
az account show
~~~

DefaultAzureCredential can use the Azure CLI credential when running on a developer machine. When deployed to Azure, the credential chain can use the managed identity or workload identity configured for the workload.

Do not use a storage account key or connection string containing an account key in application.yml. Anyone with an account key typically has broad access across the storage account, far exceeding the need to read a single container.

### 9.4. Configure BlobServiceClient

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("azure")
public class AzureBlobConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(
            @Value("${app.storage.azure.endpoint}") String endpoint) {

        DefaultAzureCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

This example uses Azure Identity directly to make the credential explicit. If the application uses Spring Cloud Azure auto-configuration, inject the client configured by the starter and avoid creating another credential chain.

### 9.5. Metadata reader adapter

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.BlobProperties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("azure")
public class AzureBlobMetadataReader implements ObjectMetadataReader {

    private final BlobServiceClient blobServiceClient;
    private final String container;
    private final String blobName;

    public AzureBlobMetadataReader(
            BlobServiceClient blobServiceClient,
            @Value("${app.storage.azure.container}") String container,
            @Value("${app.storage.azure.blob}") String blobName) {
        this.blobServiceClient = blobServiceClient;
        this.container = container;
        this.blobName = blobName;
    }

    @Override
    public ObjectMetadataView readConfiguredObject() {
        BlobProperties properties = blobServiceClient
                .getBlobContainerClient(container)
                .getBlobClient(blobName)
                .getProperties();

        return new ObjectMetadataView(
                "azure-blob-storage",
                blobName,
                properties.getBlobSize(),
                properties.getContentType(),
                String.valueOf(properties.getETag()));
    }
}
~~~

Configure the endpoint and target:

~~~yaml
app:
  storage:
    azure:
      endpoint: https://YOUR_STORAGE_ACCOUNT.blob.core.windows.net
      container: training-documents-lab
      blob: incoming/sample.txt
~~~

### 9.6. Verify permissions

If the local user is assigned the role at container scope, you can verify using the Azure CLI:

~~~bash
az storage blob show \
  --account-name STORAGE_ACCOUNT \
  --container-name training-documents-lab \
  --name incoming/sample.txt \
  --auth-mode login
~~~

If the application runs with a managed identity, verify the running resource's identity and role assignment at the right scope. Do not infer production permissions solely from a local command run with a developer user.

## 10. Running One Profile at a Time

Each adapter is activated by a Spring profile. Run AWS:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=aws
~~~

Run Google Cloud:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=gcp
~~~

Run Azure:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=azure
~~~

If running via JAR:

~~~bash
java -jar app.jar --spring.profiles.active=aws
~~~

Do not activate all three profiles simultaneously in this lab because all three adapters implement ObjectMetadataReader. If an application needs to access multiple providers at the same time, assign distinct bean names/qualifiers or use a routing strategy based on business configuration instead of relying on a single bean.

Test endpoint:

~~~bash
curl http://localhost:8080/api/storage/sample
~~~

Sample output:

~~~json
{
  "provider": "google-cloud-storage",
  "objectKey": "incoming/sample.txt",
  "sizeBytes": 25,
  "contentType": "text/plain",
  "versionToken": "1730000000000000"
}
~~~

Actual versionToken and sizeBytes depend on the created object. AWS returns ETag, GCS returns generation, and Azure returns ETag. Do not compare version token values across providers as if they were the same identifier.

## 11. Proving Write Permissions Are Not Granted

A least-privilege lab needs to test both allowed operations and denied operations.

| Check | Expected outcome |
| --- | --- |
| Read metadata of configured object | Succeeds |
| Read another object outside resource scope | Denied |
| List bucket/container | Denied if the role is designed to read only one object |
| Upload a new object | Denied |
| Overwrite object | Denied |
| Delete object | Denied |

The most reliable way to test is to run an integration test using the exact client and runtime identity of the application:

~~~java
assertDoesNotThrow(() -> metadataReader.readConfiguredObject());

// Use a dedicated object key in tests to verify that write access is denied.
// Do not run write tests on real data.
assertThrows(Exception.class, () -> storageWriteProbe.tryCreateProbeObject());
~~~

storageWriteProbe is a test-only adapter; implement it using PutObject, Storage.create, or BlobClient.upload respectively. In production environments, do not expose a write endpoint just to probe permissions.

If testing via CLI, make sure the CLI uses the exact same principal as the application. An administrator account on a developer machine can upload successfully even when the application's runtime role is restricted; that result does not prove the application configuration is wrong.

## 12. Security Principles for Production Applications

### 12.1. Do not store long-lived credentials in source code

Avoid the following configurations:

- AWS access keys/secret keys committed in the repository.
- Service account JSON keys packaged inside a container image.
- Azure storage account keys or connection strings in application properties.
- Tokens manually copied into environment variables and kept long-term.

Use the SDK's credentials providers and workload-bound identities. Temporary credentials are refreshed according to each provider's mechanism.

### 12.2. Separate provisioning and runtime permissions

The provisioning identity can create buckets, containers, IAM roles, and role assignments. The runtime identity is only granted permission to read objects as required by business logic. Administrative permissions must not be inherited automatically into the Spring Boot process.

### 12.3. Narrow the resource scope

- AWS: restrict to an object ARN or prefix ARN.
- Google Cloud: assign roles at bucket or managed-folder scope; avoid granting at project level if only one bucket is needed.
- Azure: assign data roles at container scope; avoid assigning at subscription or resource group level when unnecessary.

### 12.4. Do not let clients control arbitrary resources

If an endpoint accepts a bucket name, container, object key, or provider from the client without validation, the application can become a confused deputy: users exploit the backend's runtime identity to read resources they are not authorized to access.

For this lab, the object key is statically configured. In a real system, map a document ID to a bucket/key in the database after verifying tenant ownership and authorization.

### 12.5. Do not log authentication data

Log the provider, request ID, internal object ID, HTTP status, and processing duration. Do not log secrets, access tokens, service account keys, account keys, or file contents. Metadata such as object name and Content-Type must also comply with the system's data policy.

## 13. Troubleshooting Common Errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| AWS Unable to load credentials | No suitable profile, role, or web identity token | Check AWS_PROFILE, SSO login, task role/instance profile/IRSA |
| AWS AccessDenied on HeadObject | Missing s3:GetObject on object ARN or bucket policy deny | Check actual identity, IAM policy, bucket policy, and resource ARN |
| AWS non-existent object returns 403 | Principal lacks s3:ListBucket so S3 does not disclose object existence | Verify object key with provisioning identity; do not grant list just to change status codes if unnecessary |
| AWS region/redirect error | Client region differs from bucket region | Check spring.cloud.aws.region.static or region provider |
| GCP DefaultCredentialsProvider cannot find credentials | ADC not set up or runtime lacks an attached service account | Run local ADC or configure service identity |
| GCP 403 storage.objects.get | Role assigned to wrong service account, wrong bucket scope, or IAM deny | Check runtime principal and bucket IAM policy |
| GCP using wrong user credential | Local ADC differs from gcloud CLI credential or production service identity | Check ADC, impersonation, and Cloud Run/GKE configuration |
| Azure 403 AuthorizationPermissionMismatch | Missing data role or role only granted at management plane | Assign Storage Blob Data Reader at container scope |
| Azure DefaultAzureCredential fails to authenticate | Credential chain cannot find Azure CLI/managed/workload identity | Check az login, managed identity, and environment credentials |
| Azure newly assigned role still returns 403 | Azure RBAC has not propagated yet or assigned to wrong principal | Check principal/object ID, scope, and wait for role assignment to take effect |
| All three providers return 404 | Wrong bucket/container/object key or object not yet created | Check resource names, prefix, and distinguish object key from filesystem path |
| API returns metadata even though client is unauthorized to call API | Cloud IAM only protects backend-to-storage, not application end users | Add Spring Security/API authentication and domain authorization |

When troubleshooting, check in order: endpoint/region, credential provider, actual principal, resource scope, action permission, and only then check code. Do not fix 403 errors by granting Administrator or Owner roles.

## 14. Automated Testing and Observability

### 14.1. Unit tests

Mock the SDK client and verify the adapter:

- The adapter uses the exact bucket/container and object key from configuration.
- AWS calls headObject.
- GCS calls Storage.get(BlobId).
- Azure calls BlobClient.getProperties().
- Metadata is mapped to ObjectMetadataView.
- Non-existent objects are translated into an appropriate business error.
- There are no upload/delete methods in the read-only interface.

### 14.2. Integration tests

Use dedicated test resources and a test identity with the exact workload role:

1. Create a sample object.
2. Assign read-only permissions at resource scope.
3. Run Spring Boot with the provider profile.
4. Call the metadata endpoint and verify the result.
5. Attempt to read an object outside the granted scope.
6. Attempt to upload/overwrite/delete using the same identity and verify denial.
7. Revoke the role and verify that read requests fail.
8. Re-assign the role and verify the service works after IAM propagation completes.
9. Clean up test resources using the provisioning identity.

Do not use mocks to conclude that IAM works. Only integration tests against real cloud environments or emulators with corresponding IAM models can verify permission boundaries.

### 14.3. Runtime observability

Record:

- Active provider/profile.
- Configured bucket/container name (if permitted to log).
- Internal object ID and version token.
- Request latency and retry count.
- HTTP status or exception category.
- Principal/service identity via the provider's audit logs.

Do not log access tokens or raw credentials. During an incident, correlate application logs with CloudTrail, Cloud Audit Logs, or Azure Activity/Storage diagnostic logs to identify the denied principal and resource.

## 15. Comparing Identity Models Across the Three Clouds

| Aspect | AWS | Google Cloud | Azure |
| --- | --- | --- | --- |
| Workload identity | IAM role | Service account or federated workload identity | Managed identity or service principal |
| Credential provider | AWS SDK default credentials chain | Application Default Credentials | DefaultAzureCredential |
| Runtime credential | STS temporary credentials | Short-lived OAuth access token | Microsoft Entra access token |
| Local development | IAM Identity Center/SSO profile | ADC user credentials or service account impersonation | Azure CLI/Developer credential |
| Kubernetes | EKS IRSA/Pod Identity | GKE Workload Identity Federation | AKS Workload Identity |
| Object read permission | s3:GetObject | storage.objects.get | Storage Blob Data Reader or custom role |
| Resource scope | Object ARN/prefix/bucket | Bucket/managed folder/project | Blob/container/storage account |
| Audit | AWS CloudTrail | Cloud Audit Logs | Azure Activity/Storage diagnostic logs |

These concepts are equivalent in purpose but differ in APIs and semantics. Do not copy roles or policies verbatim from one provider to another. Standardize business interfaces at the application layer while keeping identity, credential chains, and IAM policies provider-specific.

## 16. Extended Exercise

**Context:** The document API service needs to read invoice files under the incoming/ prefix and return metadata so the frontend can display it before downloading the file.

### Task A — Choose a provider

1. Choose AWS S3, Google Cloud Storage, or Azure Blob Storage.
2. Create a test bucket/container and upload a file incoming/sample.txt.
3. Record the region/location, bucket/container, and object key.
4. Create a dedicated runtime identity for the application.

### Task B — Grant least-privilege permissions

1. Grant only object read permissions.
2. Restrict permissions to the required bucket/container or object/prefix.
3. Do not grant create, overwrite, delete, or resource administration permissions.
4. Explain whether the built-in role includes list permissions.
5. If needed, create a custom role containing only the read permission.

### Task C — Connect Spring Boot

1. Add the provider starter and compatible BOM.
2. Configure region/endpoint/bucket/object.
3. Use the SDK's default credentials provider.
4. Write an adapter implementing ObjectMetadataReader.
5. Run the corresponding profile and call /api/storage/sample.
6. Verify size, Content-Type, and version token.

### Task D — Verify security boundaries

- Attempt to read an object outside the resource scope.
- Attempt to upload a new object.
- Attempt to overwrite the sample object.
- Attempt to delete the sample object.
- Verify that all unnecessary operations are denied.
- Revoke read permission and observe the error.
- Inspect audit logs for the runtime principal.

### Task E — Compare providers

- Switch to another provider without changing the controller or business interface.
- Write a new adapter and configure the corresponding identity.
- Document differences in credential chain, role scope, permissions, and error responses.
- Evaluate how to organize multi-cloud modules/profiles to avoid dependency and configuration conflicts.

**Acceptance criteria:** The application reads object metadata using workload identity; IAM only grants read permissions at the appropriate resource scope; no long-lived credentials are used in source code; write/delete operations are denied; and the provider adapter does not alter the business contract.

## 17. Key Takeaways

- Authentication identifies the principal; authorization determines which actions the principal can perform on which resources.
- The runtime identity must be separated from the deployer/provisioning identity.
- AWS uses IAM roles and the default credentials provider; Google Cloud uses service accounts/workload identity with ADC; Azure uses managed identities/workload identity with DefaultAzureCredential.
- S3 HeadObject requires s3:GetObject on the object; s3:ListBucket is not needed when the key is known.
- GCS requires storage.objects.get; roles/storage.objectViewer also includes list, so a custom role can be narrower.
- Azure Storage Blob Data Reader is a data role; assign it at container scope and do not confuse it with Contributor at the management plane.
- Never put AWS keys, service account JSON keys, Azure account keys, or tokens into source code.
- Integration tests must verify both allow and deny operations using the exact runtime identity.
- Keep business interfaces stable while isolating SDKs, credentials, and IAM policies inside provider-specific adapters.

### References

- [Spring Cloud AWS — Getting started, credentials and S3](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [AWS SDK for Java 2.x — IAM role credentials on EC2](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ec2-iam-roles.html)
- [Amazon S3 — HeadObject API permissions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)
- [AWS IAM — Roles for Amazon ECS tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)
- [AWS EKS — IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [Spring Framework on Google Cloud — Cloud Storage](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/storage.html)
- [Google Cloud — Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Run — Service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [Cloud Storage — IAM roles and permissions](https://docs.cloud.google.com/storage/docs/access-control/iam)
- [Cloud Storage — Read objects](https://docs.cloud.google.com/storage/docs/reading-objects)
- [Spring Cloud Azure — Authentication](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/authentication)
- [Spring Cloud Azure — Blob Storage starter for Spring Boot](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-starter-java-app-with-azure-storage)
- [Azure Blob Storage — Assign a role for data access](https://learn.microsoft.com/en-us/azure/storage/blobs/assign-azure-role-data-access)
- [Azure Blob Storage — Java quickstart and DefaultAzureCredential](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-java-how-to-use-blob-storage)
