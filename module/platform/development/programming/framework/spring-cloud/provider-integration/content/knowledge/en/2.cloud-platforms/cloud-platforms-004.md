# Shared Responsibility Model Between Application and Provider

When deploying Spring Boot to AWS, Azure, or Google Cloud, much of the infrastructure work is managed by the provider: data centers, physical servers, underlying storage systems, and parts of service operations. However, using a **managed** service does not mean the provider automatically ensures proper data access permissions, bug-free application code, safe secret storage, or that the application can always recover from incidents.

That is why the **shared responsibility model** exists: the provider and the customer each hold specific security, operational, and compliance responsibilities, and this boundary shifts depending on the service type and configuration. For the **SPRING_CLOUD_PROVIDER_INTEGRATION** module in the **Cloud Platforms** chapter, understanding this model accurately is a prerequisite before integrating Spring Boot with managed storage, messaging, databases, secrets, and Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP libraries.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what the provider is typically responsible for **underneath the platform** and what the application team must own **when using the platform**.
- Distinguish responsibility models across **IaaS**, managed container platforms, **PaaS/managed services**, **serverless**, and **SaaS**.
- Identify who owns IAM/RBAC, access configuration for storage, messaging, databases, secrets, encryption keys, backups, logs, and recovery plans.
- Compare how AWS, Azure, and Google Cloud describe and implement responsibility boundaries.
- Apply shared responsibility to Spring Boot design, coding, configuration, and integration testing.
- Translate abstract responsibilities into **owners, controls, verification evidence**, and incident response procedures.

## 2. Understanding Shared Responsibility Properly

### 2.1. Two Sides of a Cloud System

The provider typically secures and operates **the infrastructure it controls**: physical facilities, power, underlying network, hardware, virtualization, and managed service layers per product commitments. The customer is responsible for **what they configure and run on the cloud**: accounts, identities, permission policies, data, application code, security choices, networking, and business workflows.

AWS often summarizes this by calling AWS's responsibility **security of the cloud** and the customer's responsibility **security in the cloud**. Azure describes how responsibilities shift across deployment models and service types. Google Cloud uses a shared responsibility model while emphasizing **shared fate**: the provider supplies designs, tools, and guidance to help customers operate more securely. These phrasings differ, yet **they do not remove the application's responsibility for its data and service usage**.

~~~mermaid
flowchart TB
    C["Customer / application team"] --> A["Data, business logic, access permissions, configuration"]
    A --> M["Boundary varies by service type"]
    M --> P["Managed platform, runtime, host, physical network"]
    P --> V["Cloud provider"]
    S["Policy, monitoring, recovery, compliance"] -. "Requires coordination and clear ownership" .-> M
~~~

This diagram shows responsibilities only at a conceptual level. For each service, consult the actual **responsibility documentation, SLA, features, configuration, contract, and support scope**. Do not use a generic diagram as proof that every security or backup feature is enabled.

### 2.2. Provider-Managed Service Does Not Mean Application-Managed

Suppose a Spring Boot application writes invoices into a bucket:

1. The provider maintains the object storage infrastructure, networking, and published durability/availability mechanisms for the service type and configuration.
2. The application team decides **which invoices are written**, how objects are named, whether contents include personal data, who can read/delete them, versioning/retention requirements, and recovery policies.
3. The platform team may manage provisioning, bucket policies, networking, and encryption settings. The security team may define guardrails; the data owner decides retention periods and usage rights.
4. If Spring Boot code accidentally writes data to another system's production bucket, the storage service working as designed **does not turn a business logic bug into the provider's responsibility**.

**Shared responsibility does not necessarily mean every task is split 50/50.** Some tasks fall primarily on the provider, some primarily on the customer, and some require collaboration between both. Internally on the customer side, tasks must still be explicitly assigned across platform, security, development, and operations.

## 3. Responsibilities Shift by Service Model

Moving from self-managed virtual machines to higher-level managed services, the provider generally assumes more underlying platform layers. Responsibility for **data, access permissions, and business logic** still remains on the customer side.

| Work Layer | IaaS: Self-Managed VMs | Managed Containers / Kubernetes | Managed Database / PaaS | Application Serverless |
|---|---|---|---|---|
| Data centers, physical machines, underlying infra | Provider | Provider | Provider | Provider |
| Workload host operating system | Customer patches and hardens guest OS | Depends on self-managed vs. managed nodes; provider manages certain layers | Provider usually manages service OS | Provider usually manages underlying host/runtime per commitment |
| Container images and app packages | Customer if using containers | Customer | Customer for self-deployed components | Customer for code, packages, and supplied images/layers |
| Middleware/DB software versions and config | Customer | Varies by component, node, and add-on | Shared per service, version selection, and upgrade policies | Varies by runtime, image, and platform config |
| Identities and application authorization | Customer | Customer | Customer | Customer |
| Data, classification, and data lifecycle | Customer | Customer | Customer | Customer |
| Network, endpoint, firewall config | Customer within provided scope | Customer within provided scope | Customer selects policies and connectivity modes | Customer selects supported policies and connectivity modes |
| Business-level backup, restore, DR | Customer designs and executes | Customer designs and executes | Provider supplies features; customer selects, tests, and drills | Customer designs data/state recovery |

Examples:

- With **EC2, Azure Virtual Machines, and Compute Engine**, the provider does not automatically patch Java, Spring Boot, or OpenSSL inside the guest OS on the customer's behalf.
- With **EKS/AKS/GKE**, who patches nodes and add-ons depends on the cluster type, node pool, managed mode, and configuration. The provider managing the control plane or certain node layers **does not mean** code inside containers is automatically secure.
- With **RDS, Azure SQL Database, and Cloud SQL**, the provider operates the database infrastructure layers per product specs; the customer still manages schemas, data, user privileges, configurable settings, backup/restore strategy, and connectivity.
- With **AWS Lambda, Azure Functions, and Cloud Run**, the provider handles much of the server management and scaling; the customer must care for dependencies, customer-controlled runtime behavior, IAM, input validation, secrets, and data.
- With **SaaS**, the provider typically takes on more of the application stack; the customer still needs to manage identities, input data, sharing configuration, and usage compliance.

To assign a specific task, ask: **can we still modify this layer, must we choose configurations, and what does the service commit to operating automatically?** Never treat the marketing label "fully managed" as a security conclusion.

## 4. Responsibility Matrix for a Spring Boot System

| Component | Provider Usually Owns | Application/Platform Team Must Own |
|---|---|---|
| Physical and underlying infra | Protecting data centers, hardware, and underlying network | Choosing Region, services, and architecture meeting requirements |
| Cloud identity | IAM/token services and identity verification mechanisms | Creating/selecting principals, granting least privilege, managing trust and auditing |
| Managed service networking | Underlying infra and committed connectivity interfaces | Firewalls, subnets, ingress/egress, private endpoints, DNS/TLS within configurable scope |
| Storage | Durability and storage features per service tier | Data classification, bucket/container policies, retention, versioning, replication |
| Messaging | Managed queue/topic systems and published delivery semantics | Controlling producers/consumers, idempotency, DLQs, retries, retention, permissions |
| Database | Database infra and service-performed maintenance tasks | Schemas, SQL accounts, queries, data, backups/restores, and RPO/RTO |
| Secret manager | Secret storage service and retrieval protocols | Secret permissions, rotation, in-app handling, keeping secrets out of logs |
| Encryption/KMS | Implementing cryptographic algorithms and key-service infra | Selecting modes/keys, key policies, lifecycle, separation of duties, residency needs |
| Application runtime | Published managed host/runtime layers | Source code, libraries, self-managed patches, security testing |
| Observability and response | Provided logging/metric/audit services and support capabilities | Enabling required logs, alerts, retention, analysis, and response runbooks |
| Incident recovery | Service-level HA, backup, replication/failover features | Defining RTO/RPO targets, choosing settings, testing restores, traffic shifting |
| Compliance | Certifications/attestations within the offered service scope | Assessing data scope, internal policies, authorization, operational evidence |
| Cost/quotas | Metering and providing billing/quota tooling | Selecting capacity, setting budgets, monitoring usage, optimizing |

**"Feature available" differs from "enabled and verified".** For example, a service supporting geo-replication does not mean every instance already has a cross-Region replica; a provider offering audit logging does not mean the application team has enabled all log streams needed to investigate incidents.

## 5. AWS: Customer Responsibilities per Managed Service

### 5.1. Amazon S3

AWS manages the object storage infrastructure and service capabilities according to storage type, class, Region, and published commitments. The customer decides **which objects are stored, how access is granted, and which lifecycle policies apply**.

- Choose the appropriate bucket, Region, storage class, lifecycle, retention, and replication.
- Use IAM roles and bucket policies with least privilege; consider **S3 Block Public Access**, Object Ownership, and other safeguards.
- Use versioning, Object Lock, or backups when recovery from accidental deletion, overwrites, or ransomware is required. Enabling encryption at rest alone does not create version history.
- When using SSE-KMS with customer-managed keys, design encrypt/decrypt permissions, key policies, and key lifecycles.
- Sanitize sensitive data before upload; validate object keys and metadata from inputs, and avoid exposing uncontrolled access URLs or leaking data via logs.

A bucket can be encrypted and highly durable yet still **leak data** due to overly broad access policies or **lose active data** when the application overwrites/deletes objects without a proper recovery mechanism.

### 5.2. Amazon SQS/SNS

AWS operates the messaging system and published delivery characteristics. The application team decides IAM/topic/queue policies, message retention duration, retry mechanisms, dead-letter queues (DLQs), retry limits, and how payload data is handled.

**Never assume "received a message" means exactly-once processing.** Spring Boot consumers must handle duplicates safely, enforce idempotency, and only acknowledge/delete messages after processing completes per queue/SDK semantics. Payloads should not contain raw secrets or unnecessary sensitive information.

### 5.3. Amazon RDS and AWS Secrets Manager

With RDS, AWS manages the published database service layers, yet users still determine network exposure, database credentials, SQL privileges, schemas, migrations, logs, backup retention, Multi-AZ, and recovery per service configuration. With Secrets Manager, AWS provides storage and retrieval capabilities; **GetSecretValue permissions, rotation, how the application caches/reads secrets, and distributing values to the DB** must still be designed.

Do not confuse permissions to manage an **RDS instance** with privileges to query **data tables** over JDBC. An IAM role may be able to view DB metadata without having a valid SQL user or table grants.

### 5.4. AWS Runtimes and Governance Tools

With ECS/EKS/EC2/Lambda, verify who manages the guest OS, task image, node AMI, runtime, layers, and dependencies. AWS IAM, CloudTrail, CloudWatch, AWS Config, Security Hub, or similar services provide security/operational support mechanisms; **the customer must configure collection scope, alerts, and response procedures**. Do not treat having a dashboard as proof of protection.

## 6. Azure: Ownership Layers Across Managed Services

Azure provides the platform and numerous security/management services, while the customer still owns decisions around data, identities, and access configuration.

| Azure Service | Platform Layers Managed by Microsoft per Product | Application-Managed Layers |
|---|---|---|
| Azure Blob Storage | Storage infrastructure, redundancy capabilities per SKU | Container/blob ACLs, Azure RBAC data roles, networking, soft delete/versioning, replication |
| Azure Service Bus | Managed broker/namespace infra and delivery capabilities | Sender/receiver identities, access keys if used, retry/DLQ, duplicate message handling |
| Azure SQL Database | Database platform and service-performed maintenance tasks | Firewall settings, SQL/Entra users, schemas, backup/restore, chosen HA/DR |
| Azure Key Vault | Secret/key/certificate storage infra and security APIs | Who can read secrets, policy/RBAC mode, rotation, networking, key lifecycle |
| Azure App Service / Functions | Managed host/runtime within service scope | App code, packages, identity, app settings, dependencies, exposure settings |
| Azure Kubernetes Service | AKS-managed Kubernetes components per configuration | Workload security, RBAC, images, networking, customer-managed nodes and add-ons |

### 6.1. Azure RBAC and Data Permissions

A defining characteristic is the separation between Azure Resource Manager's **management plane** and the **data plane** of many services. For example, **Reader** on a Storage Account can inspect management metadata but does not inherently allow reading blobs with Microsoft Entra. Workloads usually need **Storage Blob Data Reader/Contributor** at the right scope alongside appropriate network rules.

**Managed Identity** lets workloads obtain tokens without storing long-lived application passwords, yet administrators must still **assign the right roles** and specify the right identity. Obtaining a token successfully does not mean data-plane roles were granted. If storage account keys or SAS are used, manage their scope, lifetime, and exposure risk; certain management permissions can indirectly allow retrieving keys, so account for this risk when assigning roles.

### 6.2. Key Vault, Private Endpoints, and Backups

Key Vault supports authorization via Azure RBAC or access policies depending on vault configuration. Resource management permissions do not automatically grant permission to read secret values. With private endpoints, application/platform teams must also manage DNS, routing, firewalls, and data permissions. **A private endpoint does not revoke overly broad roles**, nor does it guarantee backups stay in the required geographical location.

For Azure Storage, LRS/ZRS/GRS/GZRS are redundancy options with distinct meanings and limitations; do not infer that "having GRS makes logical data loss impossible". To protect against accidental deletion or bad writes, evaluate soft delete, versioning, retention, and restore plans alongside redundancy.

## 7. Google Cloud: Shared Responsibility and Shared Fate

Google Cloud manages physical infrastructure and published service layers. Customers must still decide who accesses data, access restrictions, network configuration, application code, and reliability design. The **shared fate** concept emphasizes proactive measures and tools that help customers deploy more securely; it does not mean Google assumes the customer's responsibility for data, IAM, or business logic bugs.

| Google Cloud Service | Managed Portion | Customer Decisions Required |
|---|---|---|
| Cloud Storage | Object storage infra and replication per location type | Bucket IAM, object retention, versioning, lifecycle, location, keys, and backups |
| Pub/Sub | Messaging infra and delivery per product capabilities | Topic/subscription policies, retry/ack, dead-letter policies, data location policies |
| Cloud SQL | Managed database infra, backup/HA per service features | DB users/grants, schemas, instance settings, HA, backups, and restore drills |
| Secret Manager | Secret storage infra and retrieval APIs | IAM secret accessor, replication policy, rotation, preventing secret leakage |
| Cloud Run | Container execution infra and scaling per platform config | Container image, code, service account, ingress/egress, concurrency, timeouts |
| GKE | Control plane/nodes per chosen mode and service | Workload/pod security, images, K8s policies, networking, customer-managed node parts |

### 7.1. Service Accounts, Permissions, and Organization

The provider protects and operates IAM/token mechanisms, while the deployment team decides which service account runs Spring Boot, which roles are assigned at organization/folder/project/bucket/topic/secret levels, and which access conditions apply. **Being in the same project or organization does not automatically allow every workload to read all data.**

For example, a Cloud Run application downloading objects from Cloud Storage usually needs object read permissions on the target bucket, not bucket creation permissions. Creating a Pub/Sub topic requires a different permission from publishing messages. Service APIs can mix management and data operations in the same client, so always verify **actual methods and IAM permissions**.

### 7.2. Location, Secrets, and Encryption

Cloud Storage offers regional, dual-region, and multi-region choices; Secret Manager and Cloud KMS have their own location/replication properties. Picking a project in Singapore does not automatically confine all data to a single region. Application teams must verify **locations of primary data, replicas, backups, secrets, and logs**, along with Organization Policy constraints supported by each service.

A provider-managed or customer-managed encryption key does not waive responsibility for IAM, key usage permissions, rotation, key recovery, and resource decommissioning procedures. Disabling or deleting a key at the wrong time can render valid data permanently unreadable.

## 8. Four Boundaries That Must Have Clear Owners

### 8.1. Identity and Authorization

The provider supplies IAM, tokens, and policy mechanisms. The customer must decide:

- Which identities represent the Spring Boot application in dev, staging, and production.
- Whether permission scopes sit at the bucket, topic, namespace, queue, resource group, subscription, or project level.
- Which role belongs to CI/CD to create and configure resources, and which role belongs to the runtime to consume data.
- How to revoke permissions, rotate credentials when needed, inspect trust/cross-account/cross-project setups, and monitor privileged access.

**Least-privilege principle:** the runtime receives only permissions required for its business function. If an app only downloads invoices, do not grant permissions to create or delete entire buckets. If a worker only receives and acknowledges messages, do not grant permissions to delete the queue.

### 8.2. Network and Endpoints

The provider operates underlying infrastructure and public/private connectivity options. The customer configures security groups, VPC/VNets, firewalls, private endpoints, routes, DNS, and TLS within their control scope. An endpoint inside a private network can still be exploited if identity, application logic, or data is mismanaged.

Conversely, an application with accurate IAM/RBAC can still fail due to firewalls, DNS, or wrong-Region endpoints. Treat **networking and authorization as two independent layers**.

### 8.3. Data, Encryption, and Secrets

The application team knows which data is sensitive and must enforce controls over it:

1. **Data classification:** personal data, payments, tokens, invoices, logs, and test data.
2. **Access restrictions:** who can view, update, delete, and export data.
3. **Encryption:** TLS in transit, encryption at rest, key selection, key usage permissions.
4. **Lifecycle:** how long data is retained, where it is deleted, and whether version history/backups exist.
5. **Location:** primary, replicas, backups, logs, and supporting services residing within approved geographic boundaries.

Many services provide encryption at rest by default, yet system policies must still specify **encryption mode, permissions, key ownership, and protection goals**. Never place access keys, connection strings, or secret values in repositories, container images, logs, or example documentation.

### 8.4. Runtime, Application Code, and Dependencies

Even on serverless platforms, the provider does not automatically fix SQL injection, SSRF, insecure deserialization, or business-level authorization flaws in Spring Boot. Development teams must update Spring Boot/Spring Cloud and libraries using a compatible BOM, manage CVEs/SBOMs, validate inputs, control outbound requests, handle errors, and log safely.

On VMs, customer responsibility for OS/Java patching is higher. On managed runtimes, the provider may manage the host and certain runtime layers; customers must still track runtime version selection policies and lifecycles of container images or custom runtimes/layers. **Serverless reduces host administration; it does not eliminate responsibility for code.**

## 9. Reliability and Recovery Are Also Shared Responsibilities

Providers typically publish SLAs, durability characteristics, HA capabilities, and backup/replication options. Application teams must select configurations and build resilient business workflows.

| Issue | Provider Capability | Application Responsibility |
|---|---|---|
| Single machine/zone failure | Managed failover, regional HA, or redundant storage depending on service | Choose the right mode and eliminate single points of failure |
| Whole Region outage | Cross-region replication, secondary resources, failover tools per service | Design DR, routing, identities, and data in the standby region |
| Accidental object deletion | Versioning, soft delete, retention, or backups if enabled | Enable proper settings, restrict Delete, and test restores |
| Bad data written to database | Backups, point-in-time restore per service | Choose retention, verify RPO/RTO, restore, and fix logic |
| Duplicate message processing | Delivery/ack semantics and dedup per service | Idempotency, transactions, retries, DLQs, and business-level dedup |
| Brief API disruptions | Throttling/retry hints, load balancing | Timeouts, retries with backoff/jitter, circuit breakers, retry caps |
| Quota exhaustion or cost spikes | Metrics, quota/billing APIs, budget alerts | Monitoring, alerting, capacity planning, cleanup |

**RTO** is the target maximum downtime during recovery; **RPO** is the maximum acceptable data loss measured in time. In-Region HA, geo-replication, and backups protect against different failure modes. **Replication does not replace backups**, because logic bugs or deleted data can propagate to replicas.

~~~mermaid
flowchart TD
    U["Client"] --> LB["Load balancer / service entrypoint"]
    LB --> A["Spring Boot instance A"]
    LB --> B["Spring Boot instance B"]
    A --> DB["Managed database: HA configured"]
    B --> DB
    DB -. "Backup/replica per policy" .-> R["Restore / DR target"]
    O["Application + platform teams"] --> T["Test failover, restore, RTO/RPO"]
    T --> DB
    T --> R
~~~

A high service SLA does not automatically guarantee an **end-to-end application SLO**: bugs in code, networking, database schemas, credentials, or dependencies can still cause downtime. Define and measure SLOs across the entire user journey, not just the "healthy" status of one managed service.

## 10. Separating Responsibilities Across IaC, Spring Boot, and Operations

Consider an order system using object storage for invoices, a message broker for order processing, a managed database, and a secret manager for connection details.

~~~mermaid
flowchart LR
    SEC["Security / Platform: guardrails"] --> PIPE["IaC + deployment pipeline"]
    PIPE --> MGMT["Resource management APIs"]
    MGMT --> RES["Bucket, queue/topic, DB, secret"]
    APP["Spring Boot runtime"] --> ID["Workload identity"]
    ID --> DATA["Data APIs / JDBC"]
    DATA --> RES
    OPS["Operations: monitoring + restore"] --> RES
    SEC -. "Policy and review" .-> APP
~~~

A verifiable division of duties:

- **Platform/IaC:** provision resources in the right account/subscription/project and Region, restrict public access, configure encryption, networking, backups/replication, and assign workload roles.
- **Development/Spring Boot:** consume provisioned resource IDs, enforce business authorization, validate inputs, implement retries/idempotency, handle secrets safely, update dependencies, and write tests.
- **Security:** define policies/guardrails, identity standards, data residency requirements, logging standards, and permission reviews.
- **Operations/SRE:** monitor, alert, handle incidents, rehearse recovery drills, verify RTO/RPO, and manage resource lifecycles.
- **Data owner/business:** determine what data is stored, who is allowed to access it, retention periods, and acceptable impact of data loss or downtime.

A small team can wear multiple hats. What matters is that **every control has an explicit owner and operational evidence**. Never let a task fall into the gap between "the cloud handles it" and "another team handles it".

### 10.1. Controls Must Be Paired with Evidence

| Control | Intended Owner | Evidence to Collect |
|---|---|---|
| Runtime lacks create/delete bucket permissions | Platform + security | IAM/RBAC review, policy tests in staging |
| Invoices are protected as required | Development + data owner | Authorization tests, encryption metadata, access logs |
| Secrets never appear in source/logs | Development + security | Secret scans, log reviews, integration tests |
| Queue handles duplicate deliveries safely | Development | Duplicate/retry integration tests, DLQ metrics |
| Database meets RPO/RTO recovery targets | Operations + platform | Restore rehearsal reports, backup configuration |
| Resources reside in approved regions | Platform + compliance | IaC policies, resource location/replication inventory |
| Costs do not grow unchecked | Platform + operations | Budgets, alerts, billing dashboards, response runbooks |

## 11. Technical Example: Responsibility-Aligned S3 Integration in Spring Boot

Suppose the pipeline has created the bucket **orders-prod-invoices** in region **ap-southeast-1**, configured security policies, and assigned an IAM role to the runtime. Spring Boot only needs to read/write objects under one application prefix.

### 11.1. Application Configuration

~~~yaml
app:
  storage:
    bucket: orders-prod-invoices
    region: ap-southeast-1
    object-prefix: invoices/
~~~

These are **application-defined properties**, not default configurations across all Spring Cloud AWS versions. Bind and validate them in code. Never place access keys or secret keys in this file or in container images.

### 11.2. AWS SDK v2 Client Bean

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class StorageClientConfiguration {

    @Bean
    S3Client s3Client(@Value("${app.storage.region}") String region) {
        return S3Client.builder()
                .region(Region.of(region))
                .build();
    }
}
~~~

AWS SDK v2 uses its **credential provider chain** by default to locate appropriate credentials; in AWS environments, prefer an IAM role/workload identity with short-lived credentials. This code requires the AWS SDK v2 S3 dependency and appropriate Spring Boot setup. How Spring Cloud AWS auto-configures clients, properties, and starters depends on version, so avoid unintentionally declaring two client beans and choose a compatible BOM.

The application **does not need** to call CreateBucket on startup and does not need permission to modify bucket policies. If applying per-tenant prefixes, code must also verify tenant identity and prevent users from choosing keys outside their permitted scope.

### 11.3. Least-Privilege IAM for Object Operations

The example IAM policy below illustrates **GetObject/PutObject** permissions scoped to the exact prefix; adjust according to actual data flows and SDK methods.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::orders-prod-invoices/invoices/*"
    }
  ]
}
~~~

This policy **does not grant** CreateBucket, DeleteBucket, PutBucketPolicy, ListBucket, or DeleteObject. If the application uses SSE-KMS with a dedicated key or multipart/other APIs, additional permissions may be required. Alongside the role policy, inspect the bucket policy, KMS key policy, explicit denies, and organization-level constraints. Prefix restrictions in IAM do not replace **business authorization** deciding which user can read which invoice.

### 11.4. Conceptual Equivalents on Azure and Google Cloud

| Goal | AWS | Azure | Google Cloud |
|---|---|---|---|
| Runtime identity | IAM role / workload identity | Managed identity | Service account / Workload Identity |
| Object read permission | s3:GetObject on object ARN | Storage Blob Data Reader at matching container/scope | Storage Object Viewer on bucket |
| Message send permission | sqs:SendMessage for queue | Service Bus Data Sender for matching namespace/queue | Pub/Sub Publisher on topic |
| Secret read permission | secretsmanager:GetSecretValue | Secret data permission per Key Vault RBAC/access policy | Secret Manager Secret Accessor |
| Resource provisioning management | Dedicated CI/CD IAM role | Dedicated Azure RBAC/IaC identity | Dedicated IAM provisioning service account |

This table illustrates **authorization concepts**, not one-to-one equivalent roles in scope and capabilities. Authentication mechanisms, inheritance scopes, endpoints, encryption keys, APIs, and SDK versions all differ. For Azure Blob using Entra, a **data-plane** role is required; on GCP, bucket metadata view permission does not imply object read permission.

## 12. Security Process and Integration Testing

### 12.1. Positive and Negative Testing

In an isolated test environment, cover both categories:

| Case | Expected Outcome | Proof Responsibility |
|---|---|---|
| Workload uploads invoice to right bucket/container | Succeeds | Dev + platform: data permissions, endpoint, encoding, retry |
| Workload reads invoice outside tenant/scope | Denied | Dev: business authorization; platform: resource scope |
| Workload creates or deletes a bucket | Denied unless required by business logic | Platform/security: minimal control-plane permissions |
| Worker processes the same message twice | No unintended duplicate business transactions | Dev: idempotency, transactions, and retries |
| Workload fetches an in-scope test secret | Succeeds, value not logged | Dev/platform: IAM/RBAC, networking, secret handling |
| DB user queries an unauthorized table | Denied | DBA/dev: SQL grants and data privileges |
| Resource accidentally deleted/overwritten in staging | Recoverable within targets | Platform/operations: versioning, backups, restores |
| Service in one AZ/instance is disrupted | Recovers within defined SLO | SRE/platform: HA, routing, and runbooks |

Testing only "upload succeeds" does not prove the bucket is protected against public exposure or accidental deletion. Merely enabling backups does not prove restores work. Therefore, test **happy paths**, **denied paths**, and **recoverability**.

### 12.2. Three Layers of Verification

1. **In code:** unit-test business authorization, input validation, idempotency, exception handling, and zero secret logging. Scan dependencies/secrets before builds.
2. **In pipeline/IaC:** policy-as-code checking public exposure, IAM scope, encryption, location, backups, tags/labels, and budgets. Use a separate deployment identity.
3. **In cloud staging:** test real runtime identities, private/public endpoints, quotas, fault handling, backup restores, metrics/alerts, and audit trails.

Mocks/emulators only validate integration logic; they **do not verify** IAM/RBAC conditions, real networking, data residency, backup services, or cloud provider SLAs. For operational proof, test on real cloud resources with controlled scope and cost.

### 12.3. Signals to Observe

For each service, collect signals for 403/PermissionDenied errors, authentication failures, 429/throttling, p95/p99 latency, queue backlog/DLQs, database connection errors, replication lag, backup/restore jobs, disk/quotas, costs, and IAM/resource policy changes. Retain sanitized request IDs, trace IDs, and resource IDs; **never log tokens, secret payloads, or unnecessary personal data**.

A cloud provider offering a logging service only provides the **capability** to observe. The operations team must enable required logs, configure log access permissions, retention, alert rules, and on-call responders. Never assume all data access is audited simply because administrative logging is enabled.

## 13. Real-World Scenarios and Determining Responsibility

### Scenario A: Bucket Works Yet Leaks Invoices

Spring Boot uploads invoices to the bucket without errors. Later it is discovered that a public access policy is overly broad or the application returns unauthenticated URLs. The provider may have operated object storage strictly per commitment; the root cause lies in **permission configuration, business authorization, and review processes**. Restrict permissions, block public access as required, inspect access history, and audit issued URLs; the application/platform teams are responsible for verifying remediation.

### Scenario B: Azure SQL Is Healthy Yet Users Cannot Place Orders

Azure SQL Database reports normal service health, yet Spring Boot's connection pool is exhausted or a migration locks a table. This is an application/database workload operational issue: investigate connection management, queries, schema migrations, timeouts, retries, and rollback capability. The platform team and provider only engage for layers involving infrastructure or service incidents.

### Scenario C: Cloud Run Scales Properly Yet Pub/Sub Creates Duplicate Transactions

When a consumer is retried after a timeout, an event can be redelivered. Pub/Sub has delivery semantics based on mode and product specs; **the consumer must implement idempotency**. If a duplicate message creates two invoices, the application team must fix transaction/deduplication keys and retest, rather than expecting the serverless platform to enforce business correctness automatically.

### Scenario D: Disabled KMS Key Renders Data Unreadable

Encrypted data remains safely in managed storage, yet the required key is unavailable or the workload's decrypt permission was revoked. The provider may be operating both storage and KMS normally; the outage stems from **customer-configured key lifecycle, policies, and recovery plans**. The fix involves governing key changes, separating key administration from key usage, and practicing recovery drills.

### Scenario E: A Region Fails and Service Does Not Fail Over to DR

The cloud may provide backup, replication, and failover features, yet the workload never enabled them or lacks endpoints, IAM, database replicas, secrets, or DNS in the standby Region. Designing RTO/RPO and rehearsing regional failover belong to the system owner; the provider is responsible for committed infrastructure and features. Read each service's specific terms rather than assuming "multi-AZ" equals "multi-region".

## 14. Misconceptions to Avoid

| Misconception | Correct Understanding |
|---|---|
| "Using a managed database means no backup/restore tests needed" | Provider supplies the feature; customer still chooses retention, verifies restores, and owns data targets |
| "Cloud encrypts data so leaks are impossible" | Encryption does not replace IAM, authorization, classification, and export controls |
| "With serverless, provider patches my Java code and dependencies" | Underlying host/runtime may be provider-managed; code, packages, and runtime choices remain customer-owned |
| "Resources in a private network don't need IAM" | Network isolation and authorization are two independent layers |
| "A Contributor/Owner role is the fastest way to fix 403s" | Find the exact required operation and permission, scope it tightly, and also check networking/endpoints |
| "Region/zone redundancy means data cannot be lost" | Logic bugs, accidental deletion, corruption, and other failure modes still require backups and restores |
| "Cloud provider offers logs so monitoring is covered" | Logs must be enabled, retained, protected, analyzed, and wired to alerts/responses |
| "Provider has compliance certifications so my app is compliant" | Certifications are scoped; customers must still demonstrate compliant configuration and data handling |
| "CI/CD and runtime can share admin credentials for convenience" | Separating principals limits blast radius and keeps audit trails accurate |
| "Shared fate means Google takes all responsibility on GCP" | Customer responsibility still applies to data, identity, code, configuration, and operations |

## 15. Verifiable Deployment Checklist

Before promoting a Spring Boot integration with AWS/Azure/GCP to production, verify:

- **Service boundaries:** IaaS/managed/container/serverless type; which layers the provider manages and which layers the customer still controls.
- **Ownership:** every control has a clear owner across development, platform, security, SRE, and data owners.
- **Identities:** CI/CD and runtime use separate principals; IAM/RBAC grants only genuinely needed data and management permissions.
- **Application code:** Spring Cloud BOM compatible with Spring Boot, safe input handling, authorization, retries, idempotency, dependency hygiene, and safe logging.
- **Storage/messaging/database:** verified permissions, retention, versioning/soft delete, retries/DLQs, schema grants, backups, and restores.
- **Secrets and encryption:** secrets kept out of code, rotation and read permissions controlled, key lifecycle governed by change procedures.
- **Network/location:** endpoints, Regions, private/public access, DNS/TLS, data residency of primaries, replicas, backups, and logs.
- **Evidence:** positive/negative staging tests, policy reviews, audit trails, restore rehearsals, alerts, and runbooks.
- **Reliability:** RTO/RPO/SLO targets defined and measured against realistic failure scenarios.
- **Cost:** budgets, quotas, and ownership for monitoring replication, egress, log retention, and idle resources.

## 16. Summary

The shared responsibility model answers **who must implement and verify each control** when running applications in the cloud. AWS, Azure, and Google Cloud manage extensive infrastructure and managed service layers, yet **data, identities, authorization, resource configuration, application code security, business correctness, and recovery plans** remain active customer responsibilities along each service's boundaries.

When integrating Spring Boot with Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP, turn this model into a concrete checklist: **resource → operation → principal → permission → protection config → owner → verification evidence**. With that list in place, development teams can leverage managed services while retaining firm control over data security, recoverability, and operational accountability.
