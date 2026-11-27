# Region, Availability Zone, Endpoint, and Data Storage Location

A Spring Boot application may run in Singapore, call an API through a global domain name, write data to a bucket in another region, and replicate a copy to a third region. Looking only at the endpoint makes it easy to misunderstand **where data resides**, **which failures the service can tolerate**, and **who pays for cross-region data transfer**. This lesson separates four concepts: **region**, **availability zone**, **endpoint**, and **data location**.

Within the **Cloud Platforms** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, these concepts are prerequisites for practicing Spring Boot integration with managed services on **AWS, Microsoft Azure, and Google Cloud** via the corresponding Spring Cloud libraries. Choosing the right location directly affects access to storage, messaging, databases, secrets, identity and permission configuration, integration testing, latency, availability, cost, and data residency requirements.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between a region, availability zone (AZ), edge/local location, global endpoint, and regional endpoint.
- Determine **data storage location** from resource attributes and replication policies, rather than guessing from URLs or application placement.
- Compare Region/AZ concepts across AWS, Azure, and Google Cloud, recognizing support limits that vary by service and location.
- Design multi-AZ and multi-region deployments aligned with RTO/RPO targets and data requirements, understanding the difference between fault tolerance and backup.
- Configure Spring Boot/Spring Cloud clients to target the right destination; verify latency, networking, permissions, data residency, and cost risks.
- Diagnose common issues: wrong Region, mismatched endpoint, a single zone failure, or replicated data placed outside permitted boundaries.

## 2. Four Core Concepts

**Region** is a geographical area published by a cloud provider for deploying resources. Each provider uses its own region code naming scheme; they do not share a common catalog. Many services require selecting a region when creating a resource; some services have global or multi-region scope.

**Availability zone (AZ)** is an infrastructure zone within a region, designed as a **failure domain** relatively independent from other zones in power, networking, or physical infrastructure. AZs help distribute localized failure risk, but do not guarantee complete independence from every incident and **do not replace** a multi-region strategy.

**Endpoint** is the DNS/URL address or network port that a client connects to for a service. Endpoints can be global, regional, private via private networking, or provider-routed. **An endpoint's location is not sufficient to conclude data location.** A global domain can still serve data stored in a specific region; a regional endpoint does not by itself guarantee that all replicas and logs remain solely in that region.

**Data location** is where a system stores or processes data, including primary data, synchronous/asynchronous replicas, backups, snapshots, logs, metadata, and data flowing through supporting systems. Guaranteed scope depends on **the specific service, replication configuration, data type, and product terms**.

| Term | Answers the Question | Determined By |
|---|---|---|
| Region | In which geographical area is the resource's logical infrastructure placed? | Configuration at resource creation, sometimes immutable afterward |
| Availability zone | In which failure domain within a region does the specific resource run? | Zonal/zone-redundant options, scheduler, and service support |
| Endpoint | Which address and network path does the application call? | SDK/client, DNS, routing, public/private endpoint |
| Data location | Where can actual data copies, backups, logs, and replicas reside? | Resource attributes, replication/backup, geographic policies, and service commitments |

### 2.1. Region Is Not AZ; Endpoint Is Not Data Location

~~~mermaid
flowchart LR
    App["Spring Boot workload<br/>Region A"] --> DNS["Service endpoint<br/>global / regional / private"]
    DNS --> R["Primary data resource<br/>Region A"]
    R --> Z1["Availability Zone 1"]
    R --> Z2["Availability Zone 2"]
    R -. "Replicated if enabled" .-> DR["Standby replica<br/>Region B"]
    DNS -. "Does not determine" .-> DR
~~~

This diagram illustrates **conceptual relationships**, not a mandatory deployment diagram for a single service. For instance, an object storage bucket is typically described at the location/region level; users may not see which physical AZ stores each object. Similarly, a managed database may support multi-AZ but require enabling HA mode and paying additional fees.

### 2.2. Regional Scope Can Have Multiple Levels

Common levels include: **zonal** (a single zone), **regional** (a single region, potentially spanning multiple zones), **dual-region / multi-region** (multiple regions per service model), and **global** (global governance or serving scope). Two resources both labeled "regional" do not necessarily share the same replication mechanism, consistency model, or availability guarantees. You must check the characteristics of the **exact service type** being used.

Do not infer: "region = data stays in a single datacenter", "multi-zone = cross-region backup", or "global API = data stored worldwide". Those are independent dimensions.

## 3. AWS: Region, AZ, and How Endpoints Are Used

### 3.1. Region and AZ in AWS

AWS uses region codes such as `ap-southeast-1` (Singapore), `ap-northeast-1` (Tokyo), and `us-east-1` (N. Virginia). AZs usually appear with names like `ap-southeast-1a` and `ap-southeast-1b`. However, **AZ letters can map to different physical AZs across AWS accounts**. When you need to compare the same failure domain across multiple accounts, use the **AZ ID** (for example, `apse1-az1`) provided by AWS, rather than comparing `a`/`b` letters.

With VPC, subnets belong to a single AZ; EC2 instances reside in a specific subnet/AZ. To improve fault tolerance, a system can run workloads across multiple subnets in different AZs, use an appropriate load balancer, and deploy a database with high availability enabled. Different managed services have their own fault-tolerance models; do not assume every service deploys across multiple AZs simply because a region has multiple AZs.

AWS also offers Local Zones, Wavelength Zones, and Outposts for specific latency or placement scenarios. They are not equivalent to an independent AWS Region, and **service support, data storage, and fault tolerance** must be checked separately.

~~~mermaid
flowchart TD
    AWS["AWS Region: ap-southeast-1"] --> A["AZ: ap-southeast-1a"]
    AWS --> B["AZ: ap-southeast-1b"]
    A --> EC1["Application / subnet A"]
    B --> EC2["Application / subnet B"]
    EC1 --> LB["Load balancing / service routing"]
    EC2 --> LB
    LB --> DB["Managed database<br/>HA per service configuration"]
~~~

### 3.2. Endpoints and Locations of AWS Services

- **Amazon S3:** a bucket has a **Region** chosen at creation time. Endpoints can take forms like `<bucket>.s3.<region>.amazonaws.com` (an illustrative example of a common structure). Standard S3 buckets are not pinned to an application-chosen AZ; specialized bucket types can have different zonal models. An SDK choosing the wrong Region can trigger redirects, signature errors, or location errors.
- **Amazon SQS:** queues are tied to a Region. Queue URLs include the region and account, such as `https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-prod`. Obtain the exact queue URL and configure the client with the right Region; pay attention to AWS partitions and specialized endpoints.
- **Amazon RDS:** a DB instance belongs to a Region, has an Availability Zone, and can be configured for Multi-AZ depending on the engine/mode. **Multi-AZ HA within a Region** differs from cross-Region replicas and differs from a backup strategy restored in another Region.
- **Secrets Manager and AWS KMS:** secrets and keys are region-scoped; synchronization/replication may be available depending on the service, but it must be configured explicitly while reviewing permissions, encryption, and each replica's location.
- **Global or special-scope services:** a single endpoint convention does not apply across Route 53, CloudFront, IAM, STS, or other services. For example, STS supports regional endpoints; behavior can depend on SDK configuration and endpoints.

A connection through a **VPC endpoint** or PrivateLink can keep traffic on a provided private network path, but the private networking mechanism itself **does not move** a bucket/database into the VPC's Region and does not guarantee all processing stays in a single place.

## 4. Azure: Region, Availability Zone, and Resource Location

Azure uses region names such as `southeastasia` (Southeast Asia) and `eastasia` (East Asia). Availability zones are typically represented by numbers `1`, `2`, `3` **in regions and services that support them**. Not every region, SKU, or service allows selecting zones or supports zone redundancy.

In Azure, distinguish carefully between:

- **Resource group location** is the location of the resource group's management metadata. Resources inside the same resource group can reside in different regions; do not infer that the resource group's location is where a storage account or database stores its data.
- **Resource location** is the location attribute of an individual resource, such as a storage account, virtual machine, or managed database. For certain services, the primary location can differ from where data is replicated.
- **Zonal resources** are pinned to a chosen zone; **zone-redundant resources** are distributed or provided with fault tolerance across zones depending on the service. Some managed services do not let users directly inspect or pick individual zones.
- **Region pairs and geo-redundancy** are distinct from zone redundancy. Azure defines region-pair relationships for many regions, but **having a region pair does not mean every resource automatically replicates or fails over**. Geo-replication and failover capabilities depend on each service/SKU configuration.

### 4.1. Data Location and Redundancy Levels of Azure Storage

Azure Storage offers common redundancy options (availability depends on account type, service, and region):

| Mode | General Meaning | Notes |
|---|---|---|
| **LRS** | Maintains replicas within a single location/datacenter in the primary region per service model | Should not be considered protection against loss of an entire region |
| **ZRS** | Synchronizes data across multiple availability zones within one region | Available only in supported regions/SKUs/services |
| **GRS** | Combines primary-region replication with asynchronous geo-replication to a secondary region | RPO may be non-zero; does not automatically mean secondary data is readable |
| **GZRS** | Combines zone redundancy in the primary region with geo-replication to a secondary region | Has specific support limits and pricing |
| **RA-GRS / RA-GZRS** | Variants allowing read access to secondary-region replicas per service mechanism | Secondary reads can lag; does not replace a data consistency strategy |

Public Blob Storage endpoints typically take the form `https://<storage-account>.blob.core.windows.net`. **The hostname does not contain the region**; the region is determined when creating the storage account and by redundancy options. If using private endpoints, private domain names and DNS relate to networking and **do not represent a new statement about data storage location**.

Azure Service Bus namespaces, Azure SQL Database, Key Vault, and other services also have their own **resource location** and geo-disaster recovery/replication rules. Do not carry over assumptions about Blob Storage redundancy directly to messaging or databases.

### 4.2. Placing a Spring Boot Application in Azure

Suppose Spring Boot runs in Azure App Service in `southeastasia`, while the Azure Storage account is in `eastasia`. The application can still connect via a valid endpoint and a properly authorized Managed Identity, but the data path will cross regions: latency and egress costs may increase, and residency requirements must be assessed. **Being in the same Azure subscription/resource group does not mean being in the same region**.

## 5. Google Cloud: Region, Zone, and Managed Service Location

Google Cloud has the region `asia-southeast1` (Singapore) and zones like `asia-southeast1-a`, `asia-southeast1-b`, and `asia-southeast1-c` where available. **These region codes differ from AWS and Azure codes** even when representing the same geographical area. Do not map region codes directly across providers in multi-cloud deployments.

Compute Engine has zonal resources like VMs, regional resources like regional managed instance groups, and broader-scoped resources. GKE supports zonal/regional clusters depending on configuration. Cloud Run is deployed regionally while zone-level scheduling details are managed by the platform.

### 5.1. Cloud Storage Location

A Cloud Storage bucket has a **location** and a **location type**: regional, dual-region, or multi-region depending on selection. For example, a regional bucket has location `ASIA-SOUTHEAST1`; a multi-region bucket can use a broad scope like `ASIA` per Cloud Storage rules. **Setting location `ASIA` does not mean data is stored only in Singapore**. With dual-region/multi-region setups, understand the replica placement scope, how replication works, and specific replication options.

A client calling `storage.googleapis.com` can operate on a bucket stored in Singapore. That hostname **does not verify** that the bucket is in Singapore; you must inspect the bucket metadata. Object URLs, DNS, or the region where the application runs do not substitute for the bucket location attribute.

### 5.2. Messaging, Databases, and Secrets

- **Pub/Sub:** the API may use default endpoints or location-specific endpoints depending on features; where message data is permitted to be stored relates to the topic's **message storage policy** and service configuration. Selecting a project or endpoint alone is not enough to deduce where message data is stored.
- **Cloud SQL:** instances are bound to a region and zone, with cross-zone HA options; cross-region replicas/backups are separate configuration scopes. A client location differing from the instance location does not move the database.
- **Secret Manager:** secrets have service-defined replication options (for example, automatic or user-managed across supported locations). Check replication policies whenever secrets carry residency requirements.
- **Cloud KMS:** key rings have a location; key location, the region of encrypted data, and how the key is used are three factors that must be evaluated separately.

Organization Policy can apply location constraints to resources **where supported by the policy/service**. Do not assume one constraint governs every data type, backup, or network flow across all services.

## 6. Quick Comparison Across AWS, Azure, and Google Cloud

| Question | AWS | Azure | Google Cloud |
|---|---|---|---|
| Example region in Singapore | `ap-southeast-1` | `southeastasia` | `asia-southeast1` |
| Example zone | `ap-southeast-1a` (name mapped per account) | Zone `1` in supported regions | `asia-southeast1-a` |
| Object storage resource | S3 bucket has a Region; type/options determine storage model | Storage account has location and redundancy SKU | Cloud Storage bucket has location/locationType |
| Common endpoints | Often Region-based, though many exceptions exist | Many resource-name endpoints without Region in hostname | Many global API endpoints; service-specific options exist |
| Multi-zone | Managed services may provide automatically or require config | Zonal/zone-redundant depending on service/SKU | Zonal/regional and HA depending on service |
| Cross-region replication | Depends on resource type and replication configuration | Geo-redundancy/DR per service and SKU | Dual/multi-region, cross-region replication, or DR per service |
| Residency conditions | Choose location, replicas, backups, logs, guardrails | Choose region, redundancy, geo-copy, policy | Choose location, replication, policy, and data scope |

**Key takeaway:** even though all three clouds talk about "region", "zone", and "redundant", the exact meaning of **a redundancy option** depends on the service and cannot be mechanically translated into equivalent features across providers.

## 7. Choosing a Location for a Spring Boot System: Six Factors

### 7.1. Latency

If an application in Singapore reads a database in a distant region, every synchronous query or transaction pays the network round-trip cost. Operations involving many sequential calls are usually impacted more severely than batched calls. To reduce latency, co-locate workloads and synchronously accessed data whenever possible; measure **p50/p95/p99 latency** from the actual runtime environment and over the actual network type.

### 7.2. Availability

Choosing a region with multiple AZs is **not enough**. Verify whether the workload runs across multiple AZs, whether the load balancer routes to healthy AZs, whether the database has HA/failover configured, and what fault tolerance the messaging service commits to. Test failure modes in staging and review each service's SLO/SLA.

### 7.3. Cost and Data Transfer

Costs can arise when:

- Calling services across regions, or transferring data across regions or over the internet.
- Replicating backups, objects, databases, logs, and events to a standby location.
- Using higher redundancy SKUs, replica storage capacity, or private endpoints.
- Transferring data across AZs or through load balancers/NAT/gateways according to network topology and service pricing.

Do not assume every data transfer flow **within the same region** is free. Pricing varies by provider, service, network path, and transfer direction.

### 7.4. Data Residency Compliance

A requirement that "customer data must be stored in approved regions" must be clearly interpreted: does it apply to **primary data, replicas, backups, logs, metadata, temporary processing data, and which supporting services**? Define the permitted geographic boundaries via organizational policies and contracts, then inspect the residency documentation of **each managed service**. A resource's Region is an important input, but **not an automatic compliance certification**.

### 7.5. Identity, Permissions, and Encryption Keys

Roles/IAM/RBAC determine who can act; Region and endpoint determine what is accessed. A workload with a valid identity can still lack permissions to secrets or keys in another region/resource. KMS/Key Vault/Cloud KMS have different policies and locations; verify that decryption keys align with the replication/failover design.

### 7.6. Service Availability

Not every region supports the same services, engine versions, machine SKUs, storage redundancies, availability zones, or quotas. Before finalizing an architecture, confirm that the service is actually available in the target region, which HA/replication configurations are supported, and whether there are constraints around creation time or region migration.

## 8. Single AZ, Multi-AZ, or Multi-Region?

| Model | Protects Against | Does Not Automatically Protect Against | Use When |
|---|---|---|---|
| Single AZ | Certain app failures with isolated restarts/backups | Loss of an entire AZ, regional outage | Dev/lab or workloads tolerating downtime |
| Multi-AZ in one region | Loss of one AZ if all components are designed for HA | Loss of entire region; logic bugs, accidental deletion, data corruption | Production needing regional HA |
| Multi-region | Can reduce impact of a regional outage with complete DR | Widespread app bugs, synchronized deletion, shared DNS/identity outages | High SLOs, where geographic DR is permitted |
| Isolated backups | Supports recovery from logic errors or data loss within backup guarantees | Does not by itself enable instant failover | Any environment with data recovery requirements |

**RTO (Recovery Time Objective)** is the target maximum acceptable downtime; **RPO (Recovery Point Objective)** is the target maximum acceptable data loss measured in time. Asynchronous cross-region replication can yield an RPO greater than 0; synchronous replication/zone redundancy also does not replace backups for protecting against accidental deletion or corruption. Never claim RPO=0 or automatic failover if the services and design do not guarantee them.

~~~mermaid
flowchart TD
    U["Users"] --> G["DNS / ingress"]
    G --> P["Primary Region"]
    P --> A1["AZ 1: Spring Boot"]
    P --> A2["AZ 2: Spring Boot"]
    A1 --> DB["Database HA in Region"]
    A2 --> DB
    DB -. "Replication/backup per policy" .-> DR["Secondary Region: DR"]
    DR --> S["Verify RPO/RTO and residency"]
~~~

Two application AZs backed by a single-AZ database still leave a **single point of failure**. Likewise, two regions with a database replica—but missing traffic shifting, secrets, permissions, DNS, infrastructure as code, and recovery drills—do not constitute a working DR system.

## 9. Configuring Spring Boot Clients for the Right Region and Endpoint

### 9.1. Defining a "Source of Truth" for Integration Targets

An application typically has **three locations to verify separately**:

1. **Runtime location:** where Spring Boot executes (VM/container/managed runtime).
2. **Client target:** the Region/endpoint/project/resource ID to which the SDK sends requests.
3. **Data placement:** the location of the resource and its configured replicas/backups.

A Spring profile such as `prod` only selects a set of application configuration properties; it does not guarantee those three locations match. Manage locations through environment variables, deployment configuration, or controlled secret/config services, and validate effective values on startup or before writing data.

Example of **custom application-defined configuration** (not automatic keys for every Spring Cloud starter):

~~~yaml
app:
  deployment:
    provider: aws
    environment: production
    runtime-region: ap-southeast-1
  destinations:
    invoices:
      resource-name: orders-prod-invoices
      expected-region: ap-southeast-1
    orders-queue:
      resource-url: https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-prod
      expected-region: ap-southeast-1
~~~

Keys under `app.*` only take effect if code binds and validates them. When using Spring Cloud AWS/Azure/GCP, actual **properties and starters depend on the version**; use a BOM compatible with Spring Boot and the corresponding documentation, and avoid copying keys from one library generation to another.

### 9.2. AWS SDK v2 Example: Explicit Region Selection

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class S3ClientConfig {
    @Bean
    S3Client s3Client(@Value("${app.aws.s3-region}") String region) {
        return S3Client.builder()
                .region(Region.of(region))
                // Credentials come from the SDK default provider chain.
                .build();
    }
}
~~~

~~~yaml
app:
  aws:
    s3-region: ap-southeast-1
~~~

This example requires an AWS SDK v2 S3 dependency compatible with the project. **`app.aws.s3-region` is a property defined by this lesson**, not a default Spring Cloud AWS property. The code selects a Region for the S3 client, yet **does not prove** the bucket exists in that Region: verify the bucket region via API or IaC, and cross-check the bucket ARN/name, permissions, and any endpoint override. If you intend to use Spring Cloud AWS auto-configuration, verify how the framework provides beans and properties for your version to avoid configuring two conflicting clients.

Do not embed access keys or secret keys in example code. On AWS, use roles/temporary credentials; locally, use profiles or controlled credential mechanisms. If you need to connect to a mocked endpoint in tests, configure endpoint overrides **strictly for tests**, never carrying them into production.

### 9.3. Azure and Google Cloud: Location Is Not Necessarily in the URL

**Azure Blob Storage:** clients are typically created from the **storage account** endpoint (for example, `https://ordersprod.blob.core.windows.net`) and credentials from `DefaultAzureCredential`/Managed Identity where appropriate. The storage account name does not reveal the region; query the account's **`location`, `primaryLocation`, and `sku`**, then evaluate geo-redundancy. Running the application in the same region does not automatically guarantee the data plane and backups stay there.

**Google Cloud Storage:** the SDK accesses buckets by name and appropriate project/identity, usually through an API host that contains no region. Inspect the **bucket location and locationType** using the API or admin tools. A valid `project-id` does not ensure the project's buckets reside in the desired location; buckets have their own locations.

**Messaging and databases:** use **fully qualified identifiers** for namespaces/topics/queues/databases, the endpoint/region properties required by the SDK, and verify the target resource's location. For Azure Service Bus, namespace endpoints look like `<namespace>.servicebus.windows.net`; SQS URLs contain the Region; Pub/Sub project/topic IDs must be specified explicitly. Do not apply S3 configuration patterns blindly to all services.

### 9.4. Public, Private, and DNS Endpoints

A public endpoint is a service address reachable over the public network if security policies permit; a private endpoint connects to the service over an appropriate private network (AWS VPC endpoints, Azure Private Endpoint, Google Cloud Private Service Connect, or equivalent mechanisms depending on the service). These choices can change **network paths, DNS, firewalls, certificates/TLS, and costs**, but do not automatically alter resource location or replication.

When overriding endpoints, do not disable hostname validation/TLS in production. If an SDK routes automatically to regional endpoints, specifying an arbitrary endpoint may disable or alter automatic behavior. Use the exact domain names and parameters published by the provider for the corresponding service and partition/cloud.

## 10. Verifying Actual Location via CLI

The commands below are intended for users with the CLI installed and appropriate **metadata read** permissions. Replace example names with real resources; do not rely solely on a local machine's default profile to infer the application's production identity.

### 10.1. AWS CLI

~~~bash
# Effective identity/account
aws sts get-caller-identity

# S3 bucket Region (some results follow historical conventions)
aws s3api get-bucket-location --bucket orders-prod-invoices

# Zones in the region and corresponding AZ IDs
aws ec2 describe-availability-zones --region ap-southeast-1 \
  --query "AvailabilityZones[].{Name:ZoneName,Id:ZoneId,State:State}"
~~~

`get-bucket-location` has historical return quirks for certain Regions; for example, `null` can represent `us-east-1`. In newer programs, AWS recommends considering the **HeadBucket** API to determine Region in a manner consistent with the SDK. Do not infer location solely from a bucket name suffix. To know replication status, inspect replication configuration separately.

### 10.2. Azure CLI

~~~bash
# Subscription and tenant currently used by Azure CLI
az account show --query "{tenant:tenantId,subscription:id,name:name}"

# Actual location of the storage account and redundancy SKU
az storage account show --name ordersprod --resource-group rg-orders-prod \
  --query "{name:name,location:location,primary:primaryLocation,secondary:secondaryLocation,sku:sku.name}"

# Location of any resource by Azure resource ID
az resource show --ids RESOURCE_ID --query "{name:name,type:type,location:location}"
~~~

On Azure, `resource group location` can differ from `resource location`. The `secondaryLocation` field may be empty if the account type has no secondary-region replica, or unavailable depending on the product. To verify the actual data path, also examine storage replication, networking, and the data types in use.

### 10.3. Google Cloud CLI

~~~bash
# CLI default project (distinct from resource location)
gcloud config get-value project

# Bucket location and location type
gcloud storage buckets describe gs://orders-prod-invoices \
  --format="yaml(name,location,locationType)"

# Region/HA mode of the Cloud SQL instance
gcloud sql instances describe orders-db \
  --format="yaml(region,settings.availabilityType)"
~~~

A project is not a region; bucket and database placement are attributes of each individual resource. `gcloud auth`, Application Default Credentials, and the runtime service account can differ. In automation, specify project/credentials explicitly and log the verified scope **without logging tokens or secrets**.

## 11. Designing Three-Cloud Integration Tests

Suppose a Spring Boot service receives orders, writes invoices to object storage, sends messages to a queue/topic, and stores state in a managed database. The team deploys in Singapore and requires business data to remain in approved locations.

| Layer | AWS | Azure | Google Cloud |
|---|---|---|---|
| Runtime | ECS/EKS/EC2 in `ap-southeast-1` | App Service/AKS in `southeastasia` | Cloud Run/GKE in `asia-southeast1` |
| Object storage | S3 bucket in Region `ap-southeast-1` | Storage account location `southeastasia` | Cloud Storage bucket location `ASIA-SOUTHEAST1` |
| Messaging | SQS queue in the same Region | Service Bus namespace in the same Region | Pub/Sub: check message storage policy and location behavior |
| Database | RDS in matching Region with HA config | Azure SQL/PostgreSQL per supported region and HA | Cloud SQL in matching Region with appropriate HA/backups |
| Recovery | Multi-AZ/backup/cross-region if permitted | ZRS/geo-redundancy/backup per service | Regional HA, backup/replication per service |

The resources in this table serve as a **reference design** and do not imply every service supports the same SKU, redundancy, and location in Singapore. Each provider has its own region codes and deployment capabilities; verify against actual metadata and service documentation.

### 11.1. Test Scenarios Must Include Negative Cases

1. **Correct Region:** write and read data, measure latency, and log the verified resource ID/region.
2. **Wrong Region/endpoint:** intentionally configure a different Region in a test environment; expect the SDK to handle error messages properly or validation to block before writing.
3. **Single AZ outage:** where supported by the service, simulate losing a node/zone or rehearse failover using supported procedures, checking request retries and recovery time.
4. **Endpoint/connectivity failure:** test DNS/private endpoint/network policies, verifying bounded timeouts and retries without creating duplicate messages on retry.
5. **Replicas/backups:** verify recovery points and recovery time from replicas; do not rely solely on a "replication enabled" toggle.
6. **Residency:** query location settings for primary data, replicas, backups, secrets, and logs; detect any resource outside the permitted region list.
7. **Cost:** measure inter-zone/inter-region data transfer and replication costs in a bounded test scenario.

Unit tests and emulators can verify client mapping/configuration, but **do not prove** actual storage placement, zone fault tolerance, data residency policies, or real network charges. These must be verified in an isolated cloud environment.

## 12. Diagnosing Common Location Errors

| Symptom | Hypothesis to Check | Action |
|---|---|---|
| AWS S3 returns redirect/signature error or bucket not found | S3 client configured with wrong Region; bucket is in another region; endpoint override | Check actual bucket Region and S3 client config; avoid hardcoding wrong endpoints |
| SQS queue URL works locally but fails when deployed | SQS client Region differs from Region in queue URL, or role lacks permissions | Compare queue URL, runtime credentials, Region, and IAM policy |
| Azure Blob URL is reachable but latency is high | App is in region A, storage account in region B, or suboptimal network path | Check resource location, routing/private endpoints, measure latency/egress |
| Azure Storage has replicas outside expected boundaries | GRS/GZRS selected or geo-replication configured | Check SKU, primary/secondary location, and data policies |
| GCP Storage API uses a global host and team does not know where data resides | Confusing hostname with bucket location | Inspect bucket location/locationType and replication policies |
| Multi-AZ app still suffers downtime when one AZ goes down | Database, cache, or worker is single-AZ; load balancing and failover misconfigured | Inventory all stateful components and perform controlled failover tests |
| DR switches to secondary region but cannot decrypt data | Keys/secrets or permissions were not prepared in the DR region | Check key location, replicas/permissions, and recovery sequence |
| Network costs rise despite using same-cloud services | Cross-region calls, gateway traffic, replication, inter-zone transfers | Review billing by service/resource and trace against traffic path diagram |

### 12.1. Investigation Sequence

~~~mermaid
flowchart TD
    E["Error or increased latency"] --> I["Verify runtime identity / project / account"]
    I --> C["Read client config: Region + endpoint + resource ID"]
    C --> M["Query resource metadata: location + replication"]
    M --> N["Check DNS, network, IAM, keys, and policies"]
    N --> T["Verify with a traced/metered request"]
    T --> F["Adjust and retest in staging"]
~~~

Do not conclude an error is caused by Region solely because of HTTP 403/404: the message can stem from **permissions**, a missing resource, wrong endpoint, DNS, encryption keys, or networking. Keep correlation IDs/request IDs in logs (never log credentials/tokens), and compare the actual request against target metadata and policies.

## 13. Checklist Before Provisioning Resources or Deploying

- **Region and service availability:** target region is approved and supports the services/SKUs/HA/zones required by the architecture.
- **Zone/HA:** every critical component has an appropriate fault-tolerance model, not just the frontend application.
- **Endpoint:** SDK selects the right Region/host/project/resource ID; TLS, DNS, and private networking are configured properly.
- **Data location:** verify primary data region, replicas, backups, secrets, logs, and metadata against each service's commitments.
- **Identity and keys:** runtime identity, IAM/RBAC, key/secret regions, and failover permissions align.
- **RTO/RPO:** backups exist, restores are tested, drill runbooks exist, and actual targets are verified.
- **Cost:** evaluate data transfer, replication, inter-zone traffic, endpoints, and DR operations.
- **Testing:** include real location checks, negative cases, latency measurements, and isolated cleanup procedures.

## 14. Summary

**Region** defines the geographical/infrastructure scope of a resource; **availability zone** is a fault-tolerance domain within a region; **endpoint** is the address and access path to a service; **data location** depends on resource type and replication, backup, and logging configurations. These four concepts are closely related yet **do not replace one another**.

When integrating Spring Boot with Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP, always cross-check **runtime location → client Region/endpoint → resource location → replication/backup policy** before handling real data. This model helps design sensible latency and HA, prevents accessing the wrong region, controls cross-region costs, and satisfies verifiable data residency requirements.
