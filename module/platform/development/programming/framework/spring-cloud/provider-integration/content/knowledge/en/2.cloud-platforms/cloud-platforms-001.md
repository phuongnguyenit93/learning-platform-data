# Accounts, Subscriptions, Projects, Tenancy, and Resource Boundaries

When integrating Spring Boot with Amazon Web Services (AWS), Microsoft Azure, or Google Cloud, the first question is often "which API does the application call?". However, before choosing Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP, you need to determine **which identity the application runs under, which administrative scope the resources belong to, and who has permission to access those resources**. An application connecting to the wrong account or project might read data from another environment, incur costs in the wrong place, or be denied even when the source code is completely correct.

This lesson belongs to the **Cloud Platforms** chapter and focuses on the concepts of accounts, subscriptions, projects, tenant/tenancy, and resource boundaries. This serves as the foundation for practicing identity and permission configuration, integrating storage, messaging, data, secrets, integration testing, and comparing providers in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between **identity units**, **resource governance units**, **billing units**, and **environment isolation units** across the three clouds.
- Explain the hierarchies AWS Organizations → account; Azure tenant → management group → subscription → resource group; Google Cloud organization → folder → project.
- Identify why a Spring Boot workload can authenticate successfully yet still not be allowed to access a bucket, queue, database, or secret.
- Design boundaries for dev, staging, and production, choose appropriate places to grant permissions, apply least privilege, and avoid relying on long-lived access keys.
- Verify identity and resource scope before running an application or integration tests.

## 2. Distinguishing Five Easily Confused Concepts

**Identity** is the principal calling a service: a user, IAM role, service principal, managed identity, or service account. An identity is used for *authentication*, after which policies decide which actions are permitted (*authorization*).

**Tenant/tenancy** is the scope for leasing and governing shared services. The word "tenant" is used differently across providers: Azure has a **Microsoft Entra tenant** as an identity boundary; Google Cloud has an **organization** tied to an organization; AWS typically uses an **account** as the primary isolation boundary. You should not infer that these three terms map one-to-one. "Multi-tenant application" is also an application-layer concept referring to software serving multiple customers; it does not require each customer to have a separate cloud account/subscription/project.

**Account/subscription/project** are the foundational units for owning and managing resources, though their detailed roles differ. An AWS account, Azure subscription, and Google Cloud project are usually suitable units for separating environments or systems.

**Resource hierarchy** describes which organization, group, account, or project a resource sits under. Parent levels often propagate governance policies, constraints, and access permissions downward according to each cloud's own rules.

**Billing boundary** is where costs are aggregated, allocated, or tracked against limits. This boundary is **not automatically synonymous** with a security boundary: multiple accounts can use centralized billing, multiple projects can share a billing account, and a single subscription can still contain multiple workloads that need separated permissions.

| Perspective | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Primary resource ownership unit | AWS account | Subscription | Project |
| Upper organizational levels | AWS Organizations, organizational unit (OU) | Microsoft Entra tenant, management group | Organization, folder |
| Common identifiers | Account ID (12 digits) | Subscription ID (UUID); tenant ID | Project ID, project number |
| Internal resource grouping | Resources belong to an account, often scoped to a Region; tags for categorization | Resource group within a subscription | Resources belong to a project; folders are parent levels of projects |
| Common workload identity | IAM role and temporary credentials | Managed identity or service principal | Service account or Workload Identity Federation |
| Billing and cost allocation | Account; optional consolidated billing in Organizations | Subscription, billing account/profile, and related scopes | Billing account linked to a project |
| Organization-level controls | Service control policy (SCP), other guardrails | Azure Policy, RBAC, management group | Organization Policy, IAM policy |

> **Principle:** before making a cloud API call, always be able to answer **who is calling**, **which resource is being called**, **which scope the resource belongs to**, **which policies allow or block it**, and **where costs are recorded**.

## 3. AWS: Account as the Core Isolation Boundary

### 3.1. Organizations, Organizational Units, and Accounts

An **AWS account** has its own Account ID, contains resources, and serves as a critical boundary for permissions, quotas, configurations, and cost allocation. **AWS Organizations** lets you govern multiple accounts, group them into **organizational units (OUs)**, and apply organization-level policies.

~~~mermaid
flowchart TD
    O["AWS Organizations"] --> OU1["OU: Non-production"]
    O --> OU2["OU: Production"]
    OU1 --> D["AWS account: dev"]
    OU1 --> S["AWS account: staging"]
    OU2 --> P["AWS account: production"]
    P --> S3["S3 bucket"]
    P --> Q["SQS queue"]
    P --> DB["RDS database"]
~~~

An OU does **not** directly contain buckets or databases; it groups accounts. Resources belong to a specific account. Some services are account-wide or global by service design, while many other resources (such as SQS queues or RDS instances) also have a **Region** scope. Therefore, account and Region are two distinct dimensions: choosing the right account but the wrong Region can still result in a "resource not found" error.

A **Service control policy (SCP)** defines the maximum permission boundary for principals governed by the SCP in the organization; **an SCP by itself does not grant permissions**. An IAM role must be allowed by the relevant IAM/resource policies and not blocked by other mechanisms.

An **IAM role** can be used by a workload via an EC2 instance profile, ECS task role, EKS workload identity, or an equivalent mechanism. Applications should obtain **temporary credentials**, rather than packaging static access keys in configuration files.

### 3.2. Access Across AWS Accounts

Suppose an application runs in the *dev* account but must read an object in a bucket belonging to the *shared-data* account. Two accounts do not automatically have permissions to each other. One approach is to set up **cross-account AssumeRole**: a role in the target account has a trust policy allowing the source principal to assume the role, while the relevant permission policy and resource policy grant the appropriate S3 actions. Bucket policies, KMS key policies, network conditions, and organization-level limits can still affect the outcome.

You cannot conclude that "being logged into AWS" means "being able to read every S3 bucket". When debugging, inspect the **actual principal**, **account owning the bucket**, **Region**, **action**, **resource ARN**, and all relevant policies.

## 4. Azure: Tenant, Subscription, and Resource Group Have Distinct Roles

### 4.1. Three Non-Interchangeable Layers

- **Microsoft Entra tenant** manages the identity directory and authentication mechanisms. An organization can have multiple tenants; a subscription is associated with one tenant at a time and can be transferred between tenants through administrative procedures.
- **Management group** organizes subscriptions to apply governance policies and permissions in an upper hierarchy.
- **Subscription** is a critical boundary for governance, billing, many quotas, and environment separation.
- **Resource group** is a logical grouping of resources within **a single subscription**, used for lifecycle management, RBAC, policies, and deployment operations. Resources in the same resource group **do not have to** be in the same Region; the resource group itself also has a location attribute for management metadata.

~~~mermaid
flowchart TD
    T["Microsoft Entra tenant"] --> M["Management group"]
    M --> D["Subscription: dev"]
    M --> P["Subscription: production"]
    P --> R1["Resource group: rg-orders"]
    P --> R2["Resource group: rg-shared"]
    R1 --> B["Storage account / Blob container"]
    R1 --> SB["Service Bus namespace / queue"]
    R2 --> KV["Key Vault"]
~~~

Azure RBAC has common scopes: **management group → subscription → resource group → resource**. Permissions granted at a parent scope can apply to child scopes. This is why you should avoid granting overly broad permissions at the subscription level when a service only needs to interact with a single storage account or queue.

### 4.2. Control Plane Differs from Data Plane

In Azure, **resource management** permissions and **data read/write** permissions are often two separate groups. For example, the **Reader** role on a storage account allows viewing management metadata but **does not inherently** allow reading blob contents using Microsoft Entra ID. A workload reading blobs needs an appropriate data role (such as **Storage Blob Data Reader**) at the required scope, along with any relevant access conditions.

A **Managed identity** is an identity managed by Azure for workloads running on supported services, enabling applications to obtain tokens without storing long-lived client secrets. RBAC must be assigned to the managed identity on the exact resource or an appropriate parent scope. If an application needs to access a resource in another subscription, permissions in the target subscription and the tenant relationship must be evaluated; being in the same tenant does not automatically grant permissions. Across different tenants, additional trust mechanisms or cross-tenant access must be configured appropriately.

## 5. Google Cloud: Project as the Common Deployment Boundary

### 5.1. Organization, Folder, Project

In Google Cloud, the **organization** is the top-level organizational node if an enterprise has an organization resource; a **folder** is an optional grouping level; a **project** is where most resources are owned and service APIs are enabled. Small organizations or testing environments may have projects that do not sit under an organization.

~~~mermaid
flowchart TD
    O["Google Cloud organization"] --> F1["Folder: Non-production"]
    O --> F2["Folder: Production"]
    F1 --> D["Project: orders-dev"]
    F2 --> P["Project: orders-prod"]
    P --> GCS["Cloud Storage bucket"]
    P --> PS["Pub/Sub topic / subscription"]
    P --> SM["Secret Manager secret"]
    BA["Cloud Billing account"] -. "Billing link" .-> D
    BA -. "Billing link" .-> P
~~~

**Project ID** is a string identifier widely used in APIs and must be unique across Google Cloud; **project number** is a numeric identifier. A project's display name is distinct from both identifiers. A project can be linked to one Cloud Billing account at a time; multiple projects can share the same billing account. A billing account is a billing relationship, **not** a parent node in the resource hierarchy tree.

**IAM policy** can be assigned at the organization, folder, project, or specific resource level depending on the service. **Organization Policy** applies governance constraints such as restricting locations or resource usage; similar to SCP in guardrail intent, its syntax and evaluation model **differ from AWS**.

### 5.2. Service Accounts and Cross-Project Permissions

Spring Boot applications on Cloud Run, GKE, or supported infrastructure commonly use a **service account** via the runtime environment's secure token issuance mechanism. If a workload in project A needs to access a bucket in project B, an administrator must grant appropriate permissions to the workload's principal on the target resource or scope; both projects belonging to the same organization **does not automatically grant permissions**.

When deploying outside Google Cloud, **Workload Identity Federation** can help workloads use an identity from a trusted system to obtain short-lived credentials, reducing the need to store JSON service-account keys. Always verify that required APIs are enabled on the relevant project, along with IAM conditions, quotas, and data locations.

## 6. Resource Boundaries: Five Questions to Verify

In practice, a "boundary" consists of multiple independent layers. No single ID alone defines all permissions and the scope of an application.

| Boundary | Verification Question | Common Integration Mistakes |
|---|---|---|
| **Identity** | Whose credential/token is the workload actually obtaining? | Laptop uses a personal account, while deployed environment uses a different role/service account |
| **Authorization** | Which actions is the principal granted on the specific resource? | Has permission to create/view metadata, but lacks permission to read objects/messages/secrets |
| **Resource ownership** | Which account/subscription/project owns the bucket, database, queue, or secret? | Endpoint format is valid but points to another environment |
| **Location and network** | Which Region/location is the resource in; which paths do endpoint, VPC/VNet/firewall/private endpoint allow? | IAM is correct but network denies the connection, or wrong Region is called |
| **Governance, billing, and quota** | Where do upper-level policies, budgets, quotas, and cost labels apply? | API is blocked by policy; quota is exhausted; costs are attributed to the wrong project |

These layers interact with one another:

~~~mermaid
flowchart LR
    App["Spring Boot application"] --> ID["Runtime identity"]
    ID --> Auth["IAM / RBAC policy evaluation"]
    Auth --> Net["Network + location constraints"]
    Net --> Res["Storage / messaging / database / secret"]
    Gov["Organization guardrails"] -. "Constrains" .-> Auth
    Scope["Account / subscription / project"] -. "Owns" .-> Res
    Scope -. "Cost and quota" .-> Cost["Billing / quota"]
~~~

This diagram is a **conceptual verification model**, not a fixed technical evaluation order across all clouds. A request can fail at multiple layers; an HTTP 403 error alone is not enough to pinpoint the root cause solely from the cloud name.

## 7. Designing Dev, Staging, and Production

For example, a team developing an order service has three environments. Each environment has its own invoice bucket, order processing queue, database, and secrets. To reduce the risk of cross-environment impact, you should establish a primary governance scope for each environment:

| Environment | AWS | Azure | Google Cloud |
|---|---|---|---|
| Development | Account `orders-dev` | Subscription `orders-dev` with related resource groups | Project `orders-dev` |
| Staging | Account `orders-staging` | Subscription `orders-staging` | Project `orders-staging` |
| Production | Account `orders-prod` | Subscription `orders-prod` | Project `orders-prod` |

This is a **design pattern**, not a mandatory requirement of each cloud. Small-scale setups can group multiple applications within a single subscription/project; in that case, clear resource-level IAM/RBAC, naming, networking, and policies must be enforced. For sensitive data or multiple independent teams, separating accounts/subscriptions/projects generally makes it easier to manage blast radius, permissions, and costs.

Example of a desired permission matrix:

| Identity | Storage dev | Queue dev | Storage prod | Queue prod |
|---|---|---|---|---|
| Workload dev | Required read/write | Required send/receive | Not granted | Not granted |
| Workload prod | Not granted | Not granted | Required read/write | Required send/receive |
| CI/CD deployment | Deploy within dev scope | Deploy within dev scope | Only via pipeline and prod approval | Only via pipeline and prod approval |
| Operations staff | Per support role | Per support role | Least privilege, controlled | Least privilege, controlled |

Environment separation is effective when **both principals and resources are separated**, organization-level policies restrict privilege escalation, and pipelines select the exact deployment target. Naming a resource `prod` **does not by itself create a security boundary**. If shared services are used, map out all allowed cross-environment accesses and review them separately.

### 7.1. Naming Conventions and Tagging/Labeling

Names should reflect the system, environment, function, and location when needed, such as `orders-prod-events` or `rg-orders-prod-sea`. However, actual naming rules vary by service (allowed characters, length, uniqueness), so you must check service-specific constraints before creating resources.

Standardize tags/labels such as `environment`, `service`, `team`, and `cost-center` for filtering and cost allocation. **Tags/labels do not replace IAM/RBAC**, except when specific policies explicitly use them as permission conditions. Set up budgets and alerts at the appropriate billing scope or resource unit; standard budget alerts **are not automatic kill switches that stop all spending**.

## 8. Applying This When Configuring Spring Boot and Spring Cloud

### 8.1. Runtime Scope Identity Differs from Target Resource Configuration

An application needs at least two groups of information:

1. **Runtime context:** the actual identity provided by the environment, default cloud/Region or project, and the scope the deployment is permitted to use.
2. **Integration targets:** the name or identifier of the bucket/container, queue/topic, database, secret, and their endpoint/Region.

You should not infer integration targets solely from the Spring Boot profile name. The `prod` profile only selects application configuration; it **does not guarantee** that the credentials belong to the production account/subscription/project. Conversely, having production credentials alone does not automatically select the right storage account or bucket.

| Spring Boot Need | AWS | Azure | Google Cloud |
|---|---|---|---|
| Object storage | Amazon S3 via Spring Cloud AWS / AWS SDK | Azure Blob Storage via Spring Cloud Azure / Azure SDK | Cloud Storage via Spring Cloud GCP / Google Cloud Java client |
| Messaging | SQS/SNS or appropriate service | Service Bus or appropriate service | Pub/Sub |
| Secret | AWS Secrets Manager / Parameter Store | Azure Key Vault | Secret Manager |
| Preferred cloud identity | IAM role with temporary credentials | Managed identity | Service account via runtime environment |
| Scope to verify | Account ID, Region, resource ARN | Tenant ID, subscription ID, resource ID | Project ID/number, resource name/location |

Spring Cloud and Spring Boot library versions must use a **compatible BOM**. Specific configuration properties and starters may change between versions; this lesson focuses on resource boundaries and does not treat illustrative examples as a complete configuration ready for every release.

Example of an application using a **team-defined** set of properties to verify the environment target before creating clients:

~~~yaml
app:
  deployment:
    environment: prod
    provider: aws
    expected-account-id: "123456789012" # Example ID, replace with your system's value
  storage:
    bucket: orders-prod-invoices
    region: ap-southeast-1
~~~

Properties under `app.*` **are not Spring Cloud auto-configuration properties**. They only take effect when the application binds and validates them itself. For example, with AWS SDK v2, the application can perform an account verification step at startup:

~~~java
import software.amazon.awssdk.services.sts.StsClient;

public final class AwsAccountGuard {
    public static void verifyAccount(String expectedAccountId) {
        try (StsClient sts = StsClient.create()) {
            String actual = sts.getCallerIdentity().account();
            if (!expectedAccountId.equals(actual)) {
                throw new IllegalStateException(
                    "Unexpected AWS account: " + actual);
            }
        }
    }
}
~~~

This illustrative code requires the **AWS SDK v2 STS** dependency and is invoked during application initialization. It only checks **the account of the current credentials**, does not prove the target bucket belongs to that account, does not replace IAM checks, and does not check the Region. In an AssumeRole architecture, the returned account is the account of the assumed role. With Azure/GCP, a similar check can be performed by comparing the workload's tenant/subscription/project and resource IDs from the configuration management system; you should not assume every SDK verifies this relationship automatically.

### 8.2. Finding and Verifying Context via CLI

The following commands are **read-only inspection operations**, useful when comparing a local environment against deployment configuration. They require the CLI to be installed and logged in or provided with appropriate credentials.

**AWS CLI**

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

`get-caller-identity` shows the principal ARN and Account ID of the effective credentials. The Region value configured in a CLI profile does not guarantee every SDK client uses that same Region; environment variables and explicit configuration can take different precedence.

**Azure CLI**

~~~bash
az account show --query "{tenantId:tenantId,subscriptionId:id,name:name}" --output json
az group list --query "[].{name:name,location:location}" --output table
~~~

`az account show` shows the default subscription of the Azure CLI session. Permissions of a managed identity when the application runs on Azure can be **completely different** from the permissions of a login session on a laptop.

**Google Cloud CLI**

~~~bash
gcloud auth list --filter="status:ACTIVE" --format="value(account)"
gcloud config get-value project
gcloud projects describe PROJECT_ID
~~~

Replace `PROJECT_ID` with the actual project. The active user account in `gcloud`, the **Application Default Credentials (ADC)** used by the SDK, and the runtime service account can differ; verify which credential type the application actually uses.

### 8.3. Integration Testing with Clear Boundaries

When testing object uploads, sending messages, or reading secrets from Spring Boot:

1. Confirm the test environment scope and executing principal. Use dedicated fixtures for tests and avoid real data.
2. Create or reference test resources in the right account/subscription/project and right Region/location; ensure the role has least-privilege permissions.
3. Explicitly configure resource names/IDs in test configuration; do not reuse production endpoints by default.
4. Execute the write → read/receive → test-data cleanup cycle, observe logs, and check related costs/quotas.
5. Re-run under a production-like identity in the staging environment; also test **denied** cases when attempting to access out-of-scope resources.

**Mocks/emulators/local tests** help verify API-calling logic, but they do not validate IAM/RBAC, organization policies, private networking, or real cloud quotas. Therefore, complete integration requires a test layer on cloud infrastructure with isolated resources and cost controls.

## 9. Common Misconceptions That Cause Incidents

| Misconception | Correct Understanding |
|---|---|
| "Logged into the right cloud means I can read resources" | Authentication only identifies the principal; authorization is evaluated against specific actions, resources, policies, and conditions. |
| "An Azure tenant is the subscription" | A tenant manages identities; a subscription governs resources/billing, and there can be multiple subscriptions under one tenant. |
| "A resource group determines the Region of all Azure resources" | A resource group has its own location for metadata; resources inside it can be in multiple Regions. |
| "A Google Cloud billing account is the parent of a project" | A billing account is linked to a project for billing and is not in the organization/folder/project tree. |
| "An AWS OU directly contains buckets or databases" | An OU groups accounts; resources belong to an account with a specific service/Region scope. |
| "Same organization/tenant means workloads can access each other" | Belonging to the same organization does not automatically grant permissions across accounts, subscriptions, or projects. |
| "The Reader role can read blob content" | Azure management-plane Reader does not inherently include data-plane permissions for blobs. |
| "Setting Spring profile to prod isolates production" | A Spring profile does not replace credentials, resource scopes, and cloud policies. |
| "Having correct IAM guarantees the connection succeeds" | Network, Region, encryption keys, endpoints, upper-level policies, and service status can still block it. |
| "A budget alert will stop all resources when exceeded" | Cost alerts usually only notify; automatic actions require separate configuration and an understanding of their impact. |

## 10. Practical Diagnostic Scenarios

**Scenario A — S3 returns AccessDenied when running on ECS:** The local application used an IAM user with broad permissions, while the ECS task uses a restricted task role. Retrieve the runtime task's account/principal, and cross-check the bucket owner, IAM policy, bucket policy, and KMS policy if objects are KMS-encrypted. Do not resolve this by attaching account-wide admin permissions.

**Scenario B — Azure Blob works with a connection string but returns 403 when switching to managed identity:** A connection string may use shared key authentication, whereas managed identity goes through Microsoft Entra and Azure RBAC. Assign the proper **data role** to the managed identity on the storage account/container and check network/firewall rules. Adding the standard Reader role will not grant blob read access.

**Scenario C — Pub/Sub cannot find a topic when deployed on GCP:** The application may be using a default project different from the project containing the topic. Check the `project-id` used by the client, the full resource name, the service account running the workload, permissions on the topic/subscription, and whether the API is enabled in the appropriate project.

**Scenario D — Staging data appears in production:** The Spring profile changed, yet an environment variable still points to the staging queue, or the deployment pipeline uses a service principal/service account granted permissions in both places. Fix this by separating credentials, validating resource IDs before startup, controlling cross-environment permissions, and adding access-denied tests.

## 11. Checklist Before Connecting a Managed Service

- **Identity:** identify the runtime principal, how tokens/credentials are obtained, and credential lifetime; prefer platform-managed identity mechanisms.
- **Permissions:** grant only required actions at the smallest possible resource/scope; distinguish management permissions from data-operation permissions.
- **Resources:** record the account/subscription/project, resource ID or ARN, Region/location, and specific endpoint; verify cross-account/cross-project access separately.
- **Security:** check secrets, encryption keys, network/private endpoints, organization-level policies, and audit logs; never embed long-lived access keys in source code or artifacts.
- **Operations:** maintain environment separation rules, tags/labels, budgets, quotas, cleanup lifecycles, and an isolated integration testing strategy.

## 12. Conclusion and Next Steps

AWS centers isolation on the **account**; Azure clearly separates the **Entra tenant** for identity, the **subscription** for governance/billing, and the **resource group** for grouping resources; Google Cloud uses **organization/folder/project**, where the **project** is typically the main deployment and permission scope. These concepts share similarities but differ in policy evaluation models, billing, quotas, and the relationship between identities and resources.

Before writing Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP code, draw the diagram **principal → permissions → resource → account/subscription/project → location → billing** for the intended service. When this model is clear, integrating storage, messaging, databases, secrets, and designing tests becomes easier to control while reducing cross-environment access errors.
