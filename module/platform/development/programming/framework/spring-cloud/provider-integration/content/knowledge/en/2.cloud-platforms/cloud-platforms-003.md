# Distinguishing Resource Management APIs and Data Access APIs

A Spring Boot application may be able to **create a storage account yet fail to read a blob**, or **view database metadata yet fail to query a single row of data**. The reverse also happens: the application reads and writes objects successfully, yet is not permitted to create a new bucket. The root cause usually lies in confusing two groups of operations with different purposes, permissions, and connection mechanisms: **resource management APIs (management/control plane)** and **data access APIs (data plane)**.

Within the **Cloud Platforms** chapter, this lesson belongs to the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing Spring Boot integration with managed services on **AWS, Azure, and Google Cloud** using the respective Spring Cloud libraries. Clearly understanding both API types helps enforce least privilege, properly manage storage, messaging, databases, and secrets, protect credentials, design reliable integration tests, and accurately compare cloud providers.

## 1. Learning Objectives

After this lesson, you will be able to:

- Identify whether an operation belongs to resource management, data access, or sits on a service-dependent boundary.
- Distinguish **resource provisioning**, **configuration**, and **IAM/policies** from **runtime data operations**.
- Understand how AWS, Azure, and Google Cloud organize APIs, permissions, endpoints, and SDKs for both operation groups.
- Explain why authenticating successfully or having metadata management permissions is insufficient to read or write objects, messages, database rows, or secrets.
- Design a model where **CI/CD or Infrastructure as Code (IaC) manages resources, while the Spring Boot application consumes resources** with least privilege.
- Separate control-plane and data-plane testing; diagnose IAM/RBAC, network, endpoint, Region, quota, and policy errors in the right context.

## 2. What Are the Control Plane and Data Plane?

### 2.1. Management/Control Plane

The **control plane** is the set of capabilities used to **create, configure, list, modify, or delete resources and administrative attributes**. For example:

- Creating a bucket, storage account, queue, database instance, or secret.
- Changing replication, network access, retention, encryption, or throughput settings.
- Inspecting deployment metadata: location, status, quotas, service configuration.
- Granting/revoking permissions, attaching policies, managing identities, or assigning roles.
- Enabling a service API, creating a project, or setting organization-level policies.

These operations are typically performed by **platform teams, IaC, deployment pipelines, or operations staff**. However, not every configuration operation has a separate management endpoint; the exact classification varies by service.

### 2.2. Data Plane

The **data plane** is the set of capabilities used to **process data or execute business tasks on existing resources**. For example:

- Reading, writing, or deleting an object in a bucket/container.
- Sending or receiving messages from a queue/topic/subscription.
- Executing SQL statements against a database.
- Accessing managed secret values.
- Writing or querying records in a data store.

In a Spring Boot application, most business requests should use the **data plane** on resources that have already been provisioned and appropriately authorized.

### 2.3. Distinguishing by Operation Purpose

| Question | Management/Control Plane | Data Plane |
|---|---|---|
| Primary purpose | Create, configure, and manage resource lifecycle and policies | Read/write/process business data |
| Typical caller | IaC, CI/CD, platform/admin | Applications, workers, consumers, jobs |
| Storage example | Create bucket/storage account, enable replication | Upload/download object/blob |
| Messaging example | Create queue/topic, configure retry or retention | Publish/send, pull/receive, acknowledge |
| Database example | Create instance, configure backup/HA | Connect via JDBC and run SQL |
| Secret example | Create secret and configure replication/policy | Read secret version to connect to a service |
| Typical risk | Destroying or reconfiguring entire resources | Exposing, modifying, deleting, or corrupting data |
| Least privilege | Management actions scoped to the right resource and lifecycle | Specific data actions on the resource |
| Testing | Create/modify config, verify policies and lifecycle | Write/read/receive, transactions, data permissions |

> **Rule of thumb:** "Am I controlling *which resources exist and how they behave*?" is usually the control plane. "Am I *using a resource to process data*?" is usually the data plane.

This boundary is **functional**; it does not mean "control plane always uses REST, data plane always uses TCP". The data plane can use REST, gRPC, AMQP, JDBC, or other protocols. A single API/SDK/endpoint can contain **both management operations and data operations**. There are also boundary operations: listing object names, viewing queue attributes, managing secret versions, or managing schemas. Rely on **the provider's specific intent and permissions**, not just method names.

## 3. One Application, Two Different Workflows

Consider an order system with a Spring Boot API, an order-processing queue, and object storage holding invoices:

~~~mermaid
flowchart TD
    Dev["Developer / Platform team"] --> CI["CI/CD + IaC"]
    CI --> CP["Management API / control plane"]
    CP --> R["Bucket, queue, database, secret"]
    App["Spring Boot REST API"] --> DP["Data API / data plane"]
    Worker["Spring Boot worker"] --> DP
    DP --> R
    I1["Deployment identity"] -. "Scoped management permissions" .-> CP
    I2["Runtime identity"] -. "Least-privilege data permissions" .-> DP
~~~

**Before deployment:** the pipeline creates resources, configures Region, encryption, backups, private networking, and assigns roles to workloads. These are control-plane operations.

**While the application runs:** the API writes invoice objects and sends messages; the worker receives messages, updates the database, and reads secrets when needed. This is the data plane.

**During operations:** the platform team may change queue retention or scale database redundancy via the control plane while the application continues using the data plane. Always verify whether configuration changes cause downtime or affect data.

A permission allowing **bucket creation** does not necessarily allow **reading objects inside**. A permission to **read objects** does not necessarily allow **changing policies, deleting buckets, or creating new resources**. Separating the two identities limits the blast radius if the application is compromised.

## 4. AWS: Boundaries by IAM Action and Resource Type

### 4.1. No Single Unified Management Endpoint for All AWS Services

AWS organizes APIs per service. For example, the Amazon S3 SDK/CLI contains operations in both groups:

| Service | Management/Control Plane Examples | Data Plane Examples |
|---|---|---|
| Amazon S3 | CreateBucket, PutBucketVersioning, PutBucketReplication | PutObject, GetObject, DeleteObject |
| Amazon SQS | CreateQueue, SetQueueAttributes | SendMessage, ReceiveMessage, DeleteMessage |
| Amazon SNS | CreateTopic, SetTopicAttributes | Publish |
| Amazon RDS | CreateDBInstance, ModifyDBInstance, DescribeDBInstances | SQL via JDBC/PostgreSQL/MySQL protocol to DB endpoint |
| AWS Secrets Manager | CreateSecret, UpdateSecret, PutResourcePolicy | GetSecretValue, application reads secret version |
| Amazon DynamoDB | CreateTable, UpdateTable | GetItem, PutItem, Query, UpdateItem |

Some operations such as **ListBuckets/ListObjectsV2**, **DescribeQueue**, **DescribeTable**, and **PutSecretValue** can serve administrative or business purposes depending on context. This table classifies typical examples only; what governs security is the **exact IAM action** required by the request.

In particular, **the RDS API for managing DB instances is not the SQL query protocol**. An IAM principal may call DescribeDBInstances yet still be unable to log into the database. JDBC connections must go through database authentication or IAM database authentication mechanisms supported and configured for the engine/service, alongside networking, TLS, and in-database grants.

### 4.2. IAM for Both Operation Types

In AWS, policies specify **Action**, **Resource**, and optionally **Condition**. The example below illustrates only S3 data permissions for a workload reading and writing objects in a specific bucket:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::orders-prod-invoices/*"
    }
  ]
}
~~~

This policy does not grant **s3:CreateBucket**, **s3:PutBucketPolicy**, **s3:DeleteBucket**, nor does it implicitly grant **s3:ListBucket**. Depending on the SDK and business flow, additional permissions may be required (e.g., multipart upload, KMS key, list), but do not grant broad permissions before verifying actual need.

For a policy to take effect, you must also evaluate the **role trust policy**, bucket/resource policies, permission boundaries, session policies, service control policies (SCPs), explicit denies, and related safeguards. SCPs typically set **maximum limits** and do not grant permissions by themselves. Cross-account buckets or dedicated KMS keys may require additional permission configuration.

### 4.3. Checking AWS via CLI

Example of managing or viewing resource metadata:

~~~bash
aws sts get-caller-identity
aws s3api get-bucket-location --bucket orders-prod-invoices
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-prod \
  --attribute-names QueueArn
~~~

Example of calling the data plane to inspect an object (if authorized):

~~~bash
aws s3api head-object \
  --bucket orders-prod-invoices \
  --key example-invoice.pdf
~~~

The **HeadObject** command retrieves metadata of **a single object** via the data API; it does not download the body. In S3, required permissions and error codes can depend on context (e.g., bucket policy, GetObject permission, or ListBucket permission when an object does not exist). Therefore, you cannot deduce the cause from a single 403/404 code alone. Account, bucket, queue, and object names in examples must be replaced with real resources.

### 4.4. Spring Cloud AWS SDK and Runtime Permissions

Spring Cloud AWS provides integrations for AWS services depending on the version and starter. Workloads can obtain short-lived credentials via an IAM role on EC2, ECS, EKS, or equivalent runtime environments. **Do not attach bucket creation/deletion or bucket-policy modification permissions to a Spring Boot service just to upload files.**

If an application must create resources dynamically at runtime (for example, a SaaS system provisioning one queue per tenant), that is an **intentional architectural exception**: enforce namespace controls, quotas, naming rules, IAM conditions, and auditing; do not use an unrestricted administrative role.

## 5. Azure: Management Plane and Data Plane Are Fairly Distinct

### 5.1. Azure Resource Manager (ARM)

In Azure, many resource management tasks go through **Azure Resource Manager** with the common management endpoint **management.azure.com**. For example:

- Creating or modifying a **storage account**.
- Creating a **Service Bus namespace**, configuring properties, and certain child entities via ARM.
- Creating a **Key Vault resource**, configuring networking/RBAC.
- Creating an **Azure SQL logical server/database**, changing SKUs or operational settings.

Meanwhile, data endpoints are typically **service-specific endpoints**:

| Service | Management Plane | Data Plane |
|---|---|---|
| Azure Blob Storage | Manage storage account, redundancy, networking via ARM | Read/write blobs at endpoints like **account.blob.core.windows.net** |
| Azure Service Bus | Create namespace, change properties via ARM or supported management APIs | Send/receive messages at namespace endpoint via AMQP/SDK |
| Azure Key Vault | Create vault, update configuration via ARM | Read/write secrets, key operations at endpoints like **vault.vault.azure.net** |
| Azure SQL Database | Create/manage server, database, firewall, SKU via ARM | Execute SQL over database connections |
| Azure Cosmos DB | Create account, database/container via supported management mechanisms | Read/write documents/items via SDK and data endpoint |

Some services allow managing child entities via **service-specific APIs or client SDKs**. Thus, you cannot conclude that "every management action in Azure exists only at management.azure.com". Distinguishing by **action and permission** remains the more reliable approach.

### 5.2. Azure RBAC: Management Roles and Data Roles

Azure RBAC supports scopes **management group → subscription → resource group → resource**, with separate roles for management and data operations. The **Reader** role on a storage account typically allows viewing management details, **without inherently granting permission to read blob content using Microsoft Entra authentication**.

For instance, for Spring Boot to read blobs using a Microsoft Entra identity, the workload usually needs the **Storage Blob Data Reader** role on the container/storage account or appropriate scope. To write blobs, **Storage Blob Data Contributor** is typically suitable depending on requirements. A service that only inspects storage account configuration may need **management-plane Reader**, without needing data access.

Special note: administrative roles capable of **listing or retrieving storage account keys** can open a path to the data plane via shared keys, depending on Shared Key disablement settings and service policies. Therefore, do not assume "management permissions can never indirectly lead to data access". Control **ListKeys**, SAS tokens, key rotation, and prefer Microsoft Entra/RBAC where appropriate.

For **Key Vault**, data-plane permissions depend on the chosen vault authorization model (**Azure RBAC** or **vault access policies** in environments still using them). Vault management roles in ARM do not inherently grant permission to read secret values. Grant the exact **secret read** permission to the workload's managed identity and avoid writing secrets to logs.

### 5.3. CLI Verification Across Both Planes

Management example: retrieving storage account properties via ARM:

~~~bash
az account show --query "{tenant:tenantId,subscription:id}"
az storage account show --name ordersprod \
  --resource-group rg-orders-prod \
  --query "{name:name,location:location,sku:sku.name}"
~~~

Data example: listing blobs using Microsoft Entra login permissions:

~~~bash
az storage blob list \
  --account-name ordersprod \
  --container-name invoices \
  --auth-mode login \
  --query "[].name" --output table
~~~

A successful ARM query **does not prove** data commands will succeed; data commands require a data-plane role and appropriate network access. A local Azure CLI session typically uses a user identity; Spring Boot running on App Service, AKS, or a VM may use a different **managed identity** requiring its own role assignment.

A system may allow ARM network connectivity while blocking the Blob endpoint via firewall or private endpoint rules. **Network policy and RBAC are separate layers**; if the token is valid and the role is right but the request is blocked by the network, adding permissions will not fix it.

## 6. Google Cloud: May Share Service Endpoints While Permissions Differ

### 6.1. Organization/Project and Service APIs

Google Cloud provides **Cloud Resource Manager**, the **Service Usage API**, **IAM**, and service-specific management APIs to create projects, enable APIs, and manage permissions and resources. The data plane typically lives within the service APIs/SDKs themselves or resource-specific protocols.

| Service | Management/Control Plane | Data Plane |
|---|---|---|
| Cloud Storage | Create bucket, update location/retention/lifecycle/IAM | Upload/download objects, read/write objects |
| Pub/Sub | Create topic/subscription, configure retention/filters/policies | Publish messages, pull/acknowledge messages |
| Cloud SQL | Cloud SQL Admin API to create instances, configure backups/HA/users per supported features | SQL via PostgreSQL/MySQL/SQL Server protocol over DB connections |
| Secret Manager | CreateSecret, UpdateSecret, configure replication/IAM | AccessSecretVersion to retrieve secret payload |
| BigQuery | Create dataset/table, update policy/configuration | Submit query jobs, read/write tables via BigQuery mechanisms |
| Firestore | Manage database/indexes/TTL via admin APIs | Read/write documents and transactions |

With **Cloud Storage**, both bucket and object operations may use the same SDK/client or related API endpoints. With **Pub/Sub**, creating a topic and publishing messages can reside on the same API surface. With **Secret Manager**, methods to create secrets and methods to read secret payloads belong to the same service API, yet require different IAM permissions. Hence, **you cannot distinguish control/data solely by hostname, SDK name, or whether the request uses REST/gRPC**.

### 6.2. IAM Permissions and Project Scope

Google Cloud IAM applies policies at the organization, folder, project, or resource level depending on the service. For example, **storage.buckets.create** differs from **storage.objects.get** or **storage.objects.create**. A workload that only needs to download objects should not be granted permission to create buckets.

For example, a Spring Boot service account receives the **Storage Object Viewer** role on a specific bucket to read objects. For Pub/Sub, publishers and subscribers typically require different roles/permissions bound to the exact topic/subscription. If the resource resides in project B while the workload runs in project A, verify the actual principal and policy on the **target** resource; belonging to the same organization does not automatically grant access.

A project calling Google Cloud APIs must also meet requirements for API enablement, quotas, billing where applicable, network restrictions, encryption keys, and organization policies. Having the right role does not guarantee success if the service API is disabled or an organization-level policy blocks it.

### 6.3. CLI Functional Verification

Resource management example:

~~~bash
gcloud config get-value project
gcloud storage buckets describe gs://orders-prod-invoices \
  --format="yaml(name,location,storageClass)"
gcloud pubsub topics describe orders-events
~~~

Data access example, listing objects only (without downloading content):

~~~bash
gcloud storage ls gs://orders-prod-invoices/
~~~

Results depend on the IAM permissions of the active account/credentials. Permission to list objects differs from permission to download a specific object; **reading a list of object names** is also a form of data access that should be restricted if object names contain sensitive information. Permissions attached at the project level can be overly broad compared to a single bucket's needs.

If Spring Boot runs on Cloud Run or GKE, verify the **runtime service account**. The active account in `gcloud`, Application Default Credentials (ADC) locally, and the service account in the runtime environment may all differ.

## 7. Do Not Confuse API Surface, SDK, and Endpoint with Permissions

An object can be managed and consumed using **the exact same client SDK**. Conversely, the same database can expose **two completely different API sets**: an instance creation API and JDBC for running SQL. Thus, the proper reasoning flow runs from **operation → resource → principal → permission → endpoint/network**.

~~~mermaid
flowchart TD
    R["Application requests an operation"] --> Q{"Operation intent?"}
    Q -->|Create / configure / delete resource| C["Control plane operation"]
    Q -->|Process business data| D["Data plane operation"]
    Q -->|Overlap / metadata| X["Check API docs and IAM actions"]
    C --> P["Determine permissions, API, and scope"]
    D --> P
    X --> P
    P --> I["Verify runtime principal"]
    I --> E["Verify endpoint, Region, network, policy"]
~~~

Also distinguish the **identity/authentication plane**: where tokens/credentials are issued and users, roles, service principals, or service accounts are managed. These are generally identity-management functions. However, during a data-plane call, an application must also **authenticate**. Token-issuing endpoints may differ from resource-management endpoints and data endpoints.

| Situation | What Not to Infer | What to Verify |
|---|---|---|
| API returns HTTP 200 for viewing configuration | The app already has data-plane permissions | Read/write permissions on the target data and the active identity |
| Login succeeds and returns an access token | The token works for every API | Audience/scope/token issuer and resource authorization |
| Two APIs share the same hostname | They require the same role | Permissions required by **each method** |
| Endpoint is private | IAM/RBAC is unnecessary | Authentication, authorization, TLS, and networking together |
| Has Owner/Contributor role | Can always read data | Role definition, data actions, and key/token mechanisms |
| App has list or describe permissions | Has permission to get payloads | Specific permissions for data payloads |
| Action has "Admin" in its name | Strictly control plane only | Actual API semantics and policy behavior |

## 8. Designing Spring Boot Architecture Around Two Permission Groups

### 8.1. Separating Provisioning from Runtime

A well-controlled architecture for a Spring Boot application:

1. **IaC repository** defines buckets, queues/topics, databases, secret metadata, networking, IAM/RBAC, and resource locations.
2. **Deployment pipeline** uses a deployment identity with resource management permissions scoped to the project/environment.
3. **Spring Boot runtime** uses a dedicated workload identity with just enough data read/write permissions; resource names/endpoints are supplied via deployment configuration.
4. **Operations** uses a separate role for investigations, lifecycle management, and configuration changes; sensitive operations are audited.

Example:

~~~mermaid
flowchart LR
    Git["IaC templates"] --> Deploy["CI/CD deployment"]
    Deploy --> AdminID["Deployment identity"]
    AdminID --> CloudMgmt["Cloud management APIs"]
    CloudMgmt --> S["Storage / queue / DB / secret"]
    App["Spring Boot API/worker"] --> RuntimeID["Runtime role / managed identity / service account"]
    RuntimeID --> DataAPI["Data APIs / protocols"]
    DataAPI --> S
~~~

On AWS you can use CloudFormation/CDK/Terraform; on Azure, Bicep/ARM/Terraform; on Google Cloud, Terraform or an appropriate IaC mechanism. Choose tools per system while preserving the principles of **controlled provisioning** and **never granting cloud-wide admin permissions to the runtime**.

### 8.2. Configuring Spring Boot to Target Provisioned Resources

Example of **application-defined** logical configuration:

~~~yaml
app:
  environment: production
  storage:
    container-or-bucket: orders-prod-invoices
  messaging:
    queue-or-topic: orders-prod-events
  database:
    jdbc-url: ${APP_JDBC_URL}
~~~

Keys under **app.*** are not automatic properties across Spring Cloud starters. Bind them using **@ConfigurationProperties** or custom configuration in code. Avoid writing credentials into YAML in repositories; use roles/managed identities/service accounts and a secret manager where appropriate. Target resource names, projects/accounts, Regions, and endpoints must be verified by the deployment.

Spring Cloud AWS, Spring Cloud Azure, and Spring Cloud GCP support different integration models depending on version: starters, auto-configuration, underlying SDKs, Spring Messaging/Integration, or Java clients. **The BOM must be compatible with your Spring Boot version**; property and package names should be checked against the docs for your exact version. The control/data separation model holds true regardless of the specific client.

### 8.3. AWS SDK v2 Example: Spring Boot Reading Objects Only

The snippet below demonstrates data-plane access on an existing resource; the application does not need to call CreateBucket:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

@Service
public class InvoiceReader {
    private final S3Client s3;
    private final String bucket;

    public InvoiceReader(
            S3Client s3,
            @Value("${app.storage.container-or-bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public byte[] readInvoice(String key) {
        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();
        return s3.getObjectAsBytes(request).asByteArray();
    }
}
~~~

This assumes the project already includes the **AWS SDK v2 S3** dependency and an **S3Client** bean configured with the right Region/credentials. This method only illustrates small objects; in production, use streaming to avoid loading large files into the heap, add timeouts/retries, validate key inputs, and handle errors. If objects are encrypted with SSE-KMS, **kms:Decrypt** may be needed alongside **s3:GetObject**. Do not grant **s3:CreateBucket** or **s3:PutBucketPolicy** to a read-only service.

The code above is an SDK example used with Spring Boot; it does not claim to auto-wire via a specific Spring Cloud AWS starter. Auto-configuration behavior depends on the library version.

### 8.4. Lifecycle Permission Examples

| Subject | AWS (Illustrative) | Azure (Illustrative) | Google Cloud (Illustrative) |
|---|---|---|---|
| CI/CD provisioning | Role with actions to create/update required resources | Management RBAC within deployment scope | IAM roles/permissions to create/update resources |
| Spring Boot reading objects | s3:GetObject with matching bucket key ARN | Storage Blob Data Reader at appropriate scope | Storage Object Viewer on bucket |
| Spring Boot sending messages | sqs:SendMessage on queue | Azure Service Bus Data Sender | Pub/Sub Publisher on topic |
| Worker receiving messages | sqs:ReceiveMessage/DeleteMessage on queue | Azure Service Bus Data Receiver | Pub/Sub Subscriber on subscription |
| Service reading secrets | secretsmanager:GetSecretValue on secret | Key Vault Secrets User or equivalent data permission per vault mode | Secret Manager Secret Accessor on secret |

These are **starting points** for permission design and do not substitute for accounting for all actual SDK methods (e.g., Describe, GetQueueUrl, KMS, List, IAM conditions, token exchange, message operations). With SQS, **DeleteMessage** removes a processed message rather than **DeleteQueue**; looking solely at the word "Delete" is not enough to identify the plane.

## 9. Authentication, Authorization, and Network Connectivity

A valid call requires multiple independent conditions:

~~~mermaid
flowchart LR
    A["Runtime identity"] --> B["Valid credential / token"]
    B --> C["IAM / RBAC / DB permission"]
    C --> D["Resource scope + policy"]
    D --> E["Endpoint + network + TLS"]
    E --> F["Quota / service state"]
    F --> G["API operation succeeds"]
~~~

This diagram is a **logical checklist**, not a fixed internal evaluation order across every service.

### 9.1. Identity Differs from Permission

- **AWS:** a role authenticates with temporary credentials, yet the action must still be allowed and not denied by relevant policies.
- **Azure:** a managed identity may acquire a Microsoft Entra token successfully, yet the data-plane role on Blob/Service Bus/Key Vault may not be assigned, or the token was requested for the wrong resource/audience.
- **Google Cloud:** a service account can obtain a valid access token yet lack IAM permissions on the target bucket/topic/secret.
- **Database:** cloud IAM allowing connection to an instance does not automatically grant table/schema privileges inside the SQL engine; appropriate database authentication and authorization are required.

### 9.2. Networks and Endpoints Can Differ Between Planes

Azure Resource Manager and Blob endpoints can have different network paths, DNS, and firewalls. In AWS, some data APIs support VPC endpoints/PrivateLink, whereas management/STS APIs or other services have separate connectivity requirements. On Google Cloud, API hosts, private access, VPC Service Controls, and per-service policies can affect traffic paths.

**Correct permissions with wrong networking still fail**. Conversely, reaching a private endpoint does not prove data authorization. When using private endpoints, verify DNS, TLS hostname, routes, firewalls, IAM, and Region. Connectivity options do not automatically change where data is stored.

### 9.3. Quotas and Lifecycles Differ

Control-plane APIs may be subject to provisioning request limits, rate limits, resource state locks, or propagation delays after configuration changes. The data plane has its own throughput, request rates, concurrency, payload sizes, visibility timeouts, transaction limits, and retry characteristics. Never create new resources on every business request to bypass data-plane limits; doing so increases cost, state risk, and governance limits.

## 10. Security Pitfalls and Anti-Patterns

| Anti-pattern | Risk | Mitigation |
|---|---|---|
| Spring Boot app uses cloud admin credentials | A single app vulnerability can create/delete many resources or alter policies | Give workload identity minimal data permissions only |
| Running CreateBucket/CreateQueue on every startup | Fails without permissions, race conditions, provisioning limits, IaC drift | Provision via CI/CD first and configure resource IDs |
| Using Azure ARM Reader expecting to read blobs | Wrong-plane permission; data requests denied | Assign Storage Blob Data Reader/Contributor properly |
| Using broad account keys/SAS when managed identity is available | Bypassing user/role permission boundaries, hard to audit | Prefer Microsoft Entra RBAC; restrict and rotate keys/SAS when unavoidable |
| Assigning roles unnecessarily at project/subscription/account level | Workload can read broad data beyond the application | Assign permissions at bucket/container/queue/secret or minimal scope |
| Only checking if API returns HTTP 200 / client initializes | Actual business action permissions remain untested | Verify real data actions against test resources |
| Logging secret values or tokens for debugging | Credential and sensitive data leakage | Log resource name, operation, request ID, and sanitized error codes |
| Confusing **DeleteMessage** with **DeleteQueue** | Granting wrong permissions or misdesigning processing flow | Verify the exact action and resource targeted by each method |
| Letting runtime edit network/policy to self-fix 403 errors | Expands blast radius and breaks auditability | Investigate root cause; let pipeline/platform update configuration |

Separating permissions does not eliminate all data-plane risks: a principal allowed to **delete objects**, **purge queues**, or **overwrite databases** can still destroy data. You must therefore govern **data operations**, versioning, soft deletes, backups, retention, and auditing—not just the control plane.

## 11. Designing Intentional Integration Tests

To integration-test Spring Boot against managed services:

1. **Pre-provision:** IaC creates test resources in a separate account/subscription/project, setting Region, networking, policies, and tags/labels. This stage requires control-plane permissions.
2. **Run with runtime identity:** the application uses a role/managed identity/service account with only permitted data permissions.
3. **Positive tests:** write and read objects, send and receive messages, execute database transactions, and read a narrowly scoped test secret.
4. **Negative tests:** under the runtime identity, verify forbidden actions such as creating new resources or reading out-of-scope data. Use permission-check/dry-run/simulator APIs where available or isolated test environments to avoid unintended side effects.
5. **Verify networking:** check the endpoint, Region, DNS, private access, and TLS along the actual path.
6. **Verify cleanup:** clean up test objects/messages using appropriate data permissions; tear down test resources via the pipeline/provisioning identity after testing completes.
7. **Audit and observe:** cross-check cloud audit logs, SDK request IDs, and application traces while excluding secrets/tokens from logs.

**Mock unit tests** confirm code calls the right methods, but do not validate real IAM/RBAC, endpoints, networking, or quotas. **Cloud integration tests** verify real behavior; there is no need to grant admin permissions to the application just because tests need to create resources. Fixtures can be prepared by a separate pipeline or test harness using distinct credentials in a controlled manner.

### 11.1. Recommended Test Matrix

| Scenario | Expected Outcome | Cause to Check if Wrong |
|---|---|---|
| Deployment identity creates test queue | Succeeds | Management scope, policy, Region, quota |
| Runtime identity sends message to target queue | Succeeds | Data permission, endpoint, network |
| Runtime identity modifies queue configuration | Denied if no admin requirement | Overly broad control-plane permissions |
| Runtime identity reads blob outside allowed container | Denied | Role/resource scope, inherited permissions, keys/SAS |
| Runtime identity reads in-scope test secret | Succeeds | Secret/data role, token audience, vault mode |
| Runtime identity deletes database instance | Denied | Management-plane permissions and upper-level policies |
| JDBC connects and runs SELECT | Per specific DB user grants | DB auth, schema/table privileges, network |

Do not test deleting production resources just to "prove" permissions are blocked. Use isolated resources, IAM simulation/policy inspection, or safe test plans.

## 12. Layer-by-Layer Error Diagnosis

### 12.1. Investigation Workflow

~~~mermaid
flowchart TD
    E["Cloud API call fails"] --> O["Identify operation + resource ID"]
    O --> P{"Control or data?"}
    P -->|Control| C["Management role / policy / quota"]
    P -->|Data| D["Data role / object, queue, SQL, secret permissions"]
    P -->|Unclear| M["Read provider IAM action/method docs"]
    C --> I["Verify actual principal"]
    D --> I
    M --> I
    I --> N["Check scope, network, endpoint, Region"]
    N --> T["Retest with least privilege in staging"]
~~~

### 12.2. Common Symptoms

**AWS — allowed to list buckets yet GetObject returns AccessDenied:** inspect `s3:GetObject` on the object ARN, bucket policy, KMS decrypt, explicit denies, object/bucket owning account, endpoint Region, and networking. Permission to list bucket names does not automatically allow reading every object.

**AWS — RDS DescribeDBInstances succeeds yet JDBC times out:** Describe uses the management API; JDBC uses the DB endpoint and its own protocol. Check security groups, subnets, routing, ports, TLS, and DB credentials. If connection succeeds but SELECT is denied, check SQL privileges inside the database.

**Azure — Storage Account Contributor yet Blob read returns 403:** check data-plane roles, the active auth mechanism (Entra token vs. key/SAS), role assignment scope, and firewalls/private endpoints. Some management roles can retrieve account keys; avoid automatically switching to shared keys as a way to "fix" permission errors.

**Azure — Key Vault created successfully yet SecretClient cannot read:** determine whether the vault uses Azure RBAC or access policies; verify the runtime principal, secret data permissions at the appropriate vault/secret level, token audience, firewalls, and private endpoints.

**Google Cloud — creating a Pub/Sub topic works yet publish returns PermissionDenied:** check the runtime identity's IAM publish permission on the target topic, actual project, API enablement, organization policies, and resource state. The deployer and workload may be two different service accounts.

**Google Cloud — Cloud SQL Admin API views instance yet JDBC fails:** instance management permissions are not SQL engine privileges; verify connector/proxy if used, networking, database login, TLS, and user grants.

**Some errors are not missing permissions:** HTTP 404 from wrong project/Region/resource name, 429 from quotas, timeouts from private DNS, blocked endpoints, or disabled services. Never broaden IAM/RBAC before identifying **operation**, **principal**, **resource**, and **failure mode**.

## 13. Checklist When Integrating a New Service

- **Operation:** classify each SDK/API method by purpose; explicitly record the required actions/permissions.
- **Identity:** define CI/CD, runtime, and operational identities; prefer temporary credentials, managed identities, or service accounts.
- **Scope:** grant management and data permissions at the smallest scope; avoid Owner/Admin solely to read or write data.
- **Provisioning:** create resources, networking, replicas, backups, policies, and keys via IaC or audited processes.
- **Runtime:** configure only resource IDs, endpoints/Regions, auth, and retries; verify data-plane behavior from the actual deployment environment.
- **Secret:** protect secret values; separate permissions to create/manage secrets from permissions to read payloads.
- **Network:** verify API hosts, private/public endpoints, DNS, TLS, firewalls, and data location rules.
- **Testing:** include positive/negative tests per plane and audit real requests using isolated test data.
- **Operations:** monitor quotas, costs, configuration drift, logs, and incident recovery procedures.

## 14. Summary

The **control plane** determines how resources are created, configured, managed, and constrained. The **data plane** covers operations that use those resources to process data and business requests. AWS typically places both inside per-service APIs/SDKs and distinguishes them via **IAM actions**; Azure clearly separates **ARM management** from **data endpoints/roles** across many services; Google Cloud provides resource-management APIs alongside service APIs that combine management and data operations, distinguished by **IAM permissions**.

When building Spring Boot systems with Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP, define **who provisions resources**, **who reads/writes data**, **which methods each principal may invoke**, **where resources are scoped**, and **how endpoints/networks behave**. This model protects data, reduces excessive permissions, clarifies integration failures, and separates deployment responsibilities from business processing.
