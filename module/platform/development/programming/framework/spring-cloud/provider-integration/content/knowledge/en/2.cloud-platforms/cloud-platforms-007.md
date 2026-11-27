# Separating Development, Testing, and Production Resources

A Spring Boot application may run fine on a developer's machine yet cause an incident when deployed: a test job deletes real objects, a staging consumer picks up production messages, a pipeline uses the wrong cloud identity, or a database configuration in the test profile points at the customer-facing database. Such cases usually stem from **missing environment boundaries** rather than bugs in storage, messaging, or database APIs.

Within the **Cloud Platforms** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, this lesson focuses on separating **development (dev), testing/integration test, staging/pre-production, and production (prod)** when integrating Spring Boot with managed services on **AWS, Azure, and Google Cloud** via the corresponding Spring Cloud libraries. The goal is to protect data and secrets, control access permissions, limit failure blast radius, govern costs, and still test storage, messaging, data, and remote integrations effectively.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why environment separation is required and distinguish **governance boundaries**, **IAM boundaries**, **data boundaries**, **network boundaries**, and **operational boundaries**.
- Choose an appropriate environment-separation model across **AWS accounts**, **Azure subscriptions/resource groups**, and **Google Cloud projects**.
- Design dedicated workload identities, service principals/service accounts, secrets, policies, and resource naming per environment.
- Build pipelines that provision resources with Infrastructure as Code (IaC), deploy the same artifact across environments, and enforce pre-production gates.
- Configure Spring Boot, Spring profiles, and Spring Cloud SDKs so applications access only authorized resources in the right environment.
- Design safe integration tests, sanitized test data, lifecycle-managed temporary resources, and access-denied tests.
- Spot misconfigurations that cause cross-environment impact: wrong endpoints, shared credentials, mixed backup/test data, shared queues/topics, or production secrets appearing in staging.

## 2. An Environment Is a Set of Boundaries, Not Just a Profile Name

An **environment** is a collection of resources, identities, data, configuration, networking, policies, and deployment workflows serving a specific purpose. Common environments:

| Environment | Primary Purpose | Appropriate Data | Operational Rules |
|---|---|---|---|
| **Local development** | Write code and iterate quickly on logic | Synthetic data, mocks, emulators, or isolated dev resources | Minimal permissions; never touch production automatically |
| **Development (dev)** | Integrate unstable changes | Synthetic test data; resettable | Automated deployments, controlled creation/deletion of resources |
| **Integration test / QA** | Verify multiple components interact properly | Isolated, reproducible fixtures | Cleanup-enforced tests without mutating real data |
| **Staging / pre-production** | Rehearse production-like behavior before release | Synthetic or safely anonymized data | Production-like configuration and topology when needed |
| **Production** | Serve real users and business data | Real data governed by policies | Tight permissions, auditing, backups, DR, release gates, and monitoring |

Dev, QA, and staging may be consolidated at small scale, provided **accepted risks are explicitly documented**. Combining environments to save cost does not mean applications may share admin permissions or production data.

### 2.1. Layers That Must Be Separated

~~~mermaid
flowchart TB
    Org["Organization / governance level"]
    Org --> D["DEV environment"]
    Org --> S["STAGING environment"]
    Org --> P["PROD environment"]
    D --> D1["Identity + IAM"]
    D --> D2["Storage + queue + DB + secret"]
    S --> S1["Identity + IAM"]
    S --> S2["Storage + queue + DB + secret"]
    P --> P1["Identity + IAM"]
    P --> P2["Storage + queue + DB + secret"]
    CI["CI/CD - shared artifact"] --> D
    CI --> S
    CI --> P
~~~

This diagram illustrates splitting into isolated deployment scopes. In practice, pipeline permissions must also be separated per environment; reusing a single artifact **does not mean** sharing a single credential.

Boundaries can be verified using five questions:

1. **Governance:** which account/subscription/project owns the resources and records costs?
2. **Identity and permissions:** who is allowed to execute which operations on target resources?
3. **Data:** which environment owns primary data, replicas, backups, logs, and messages?
4. **Network:** which endpoints does the workload connect to, and via which VPC/VNet/firewall/private endpoint?
5. **Change control:** who can create, modify, delete, and deploy resources/code in that environment?

A **Spring profile** such as `dev` or `prod` is purely an application configuration selector. It **creates no security boundary** in IAM or on the cloud platform. An app running with the `dev` profile yet holding production credentials can still modify production data if policies allow it.

## 3. Why Separate Environments?

### 3.1. Reducing Blast Radius

If dev and production share a database, a migration or accidental delete on dev can destroy real data. If databases are separated yet share a broad IAM role, a configuration mistake can still allow accidental cross-access. Therefore, boundaries must be enforced across both **resources** and **principals/policies**.

For example, a test-data cleanup job should be allowed to delete objects in `orders-dev-invoices` while being denied deletion in `orders-prod-invoices`, even if a developer accidentally passes the production bucket name.

### 3.2. Keeping Tests Reproducible

Integration tests must know initial state, emitted events, consumers, cleanup timing, and error conditions. When multiple environments share a queue, tests can consume production messages or real consumers can process fake events. Separating queues/topics/subscriptions and databases lets you build clean fixtures, reset state, and reproduce behavior.

### 3.3. Controlling Changes and Access

Dev may allow continuous deployment; staging may enforce test gates; production requires formal approvals, rollback plans, and auditing. Development teams can hold broader operational privileges in dev, while production enforces **least privilege**, separation of duties, and audited break-glass procedures.

### 3.4. Controlling Costs, Quotas, and Performance

A heavy test batch should not exhaust production quotas, DB connections, messaging throughput, or budget. Separating accounts/subscriptions/projects clarifies budgeting and billing, though specific quotas still depend on provider, Region, and service. Some organization-level shared resources can still affect multiple units, so verify exact limits.

### 3.5. Protecting Data and Meeting Compliance

Production holds real data, including information protected by regulations or internal policies. Never assume copying a production database into test is safe. Even copies with masked fields can still re-identify individuals or retain secrets/tokens if sanitization is incomplete.

## 4. Choosing Separation Granularity: From Resources to Independent Accounts

Boundaries can be placed at several levels with varying degrees of isolation:

| Separation Level | Example | Advantages | Limitations / Risks |
|---|---|---|---|
| **Prefix/name only** | Two tables or object prefixes in one resource | Easy and cheap in labs | Permissions/network/quotas often shared; accidental deletion spreads |
| **Separate resources, same governance scope** | Dedicated buckets/queues/DBs in one account/project | Resources have separate IAM and lifecycles | May share quotas, inherited parent permissions, billing, and network |
| **Separate resource groups in an Azure subscription** | `rg-orders-dev`, `rg-orders-prod` | Lifecycle and RBAC management per resource group | Does not create independent subscription/billing/quota boundaries |
| **Separate account/subscription/project** | Dedicated AWS account, Azure subscription, or GCP project per env | Clear permissions, governance, cost tracking, guardrails, and small blast radius | Higher operational overhead for IAM, networking, IaC, and cost governance |
| **Independent organization/tenant when truly needed** | Distinct legal, identity, or compliance structure | Additional identity/governance boundary | Significant governance and integration complexity |

For production holding critical data or workloads, **a dedicated primary resource unit for production** is usually a strong starting point. Still, there is no rigid rule that every tiny app requires a separate cloud organization or subscription; base the choice on data sensitivity, scale, and operational capacity.

### 4.1. Soft Boundaries vs. Enforced Boundaries

**Soft boundaries** are conventions: naming with a `-prod` suffix, tagging `environment=prod`, or placing resources in separate folders. Conventions help organization and observability, yet do not reject unauthorized access on their own.

**Enforced boundaries** are mechanisms such as IAM/RBAC, resource policies, organization guardrails, network isolation, service perimeters, encryption-key access, and deployment approvals. Verify by testing that **a dev workload cannot read or write production resources**, rather than relying on architecture diagrams alone.

## 5. AWS: Separating Accounts, Roles, and Resources by Environment

### 5.1. AWS Organizations and Accounts

A common pattern uses **AWS Organizations** to govern multiple accounts placed into organizational units (OUs) by role or environment:

~~~mermaid
flowchart TB
    O["AWS Organizations"] --> NP["OU: NonProduction"]
    O --> PR["OU: Production"]
    NP --> DEV["AWS account: orders-dev"]
    NP --> ST["AWS account: orders-staging"]
    PR --> PRO["AWS account: orders-prod"]
    DEV --> DA["IAM role + S3/SQS/RDS dev"]
    ST --> SA["IAM role + S3/SQS/RDS staging"]
    PRO --> PA["IAM role + S3/SQS/RDS production"]
~~~

An OU **groups accounts**; it does not directly contain buckets or databases. An AWS account is typically the major boundary for permissions, resources, and quotas; regional resources also carry a **Region**. A **Service control policy (SCP)** can enforce maximum permission ceilings at organization/OU/account level, yet **does not grant permissions itself**. Attach matching identity/resource policies and check for explicit denies.

For example, each environment gets:
- Its own invoice S3 bucket.
- Its own SQS queue/SNS topic; dev consumers never subscribe to production topics.
- Its own RDS instance or cluster; never copy raw production DBs into dev.
- Appropriately scoped Secrets Manager secrets and KMS keys.
- Dedicated runtime ECS task roles / EKS workload identities / EC2 instance roles.

### 5.2. Pipeline Roles Differ from Runtime Roles

Pipelines receive permissions to **provision/deploy** resources in the target account; the Spring Boot runtime receives only the **data operations** needed by the application. A dev IAM role must never be trusted to assume a production role, barring explicitly approved exception workflows.

One deployment model uses OIDC or appropriate federation so CI/CD obtains **short-lived** credentials, with trust policies restricting repository/branch/environment and permissions on the target account. Never commit long-lived access keys to repositories or copy production credentials onto dev runners.

Least-privilege sample for an application that only **reads/writes objects under a dev prefix**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::orders-dev-invoices/invoices/*"
    }
  ]
}
~~~

This is an illustrative role permission snippet, not a complete configuration. If using KMS, multipart uploads, list calls, cross-account policies, or other features, inspect the required actions. It does not grant `s3:CreateBucket`, `s3:DeleteBucket`, `s3:ListBucket`, nor allow access to production buckets. Also evaluate bucket policies, key policies, SCPs, role trust policies, and Region.

### 5.3. Tools and Verification Commands

~~~bash
# Check account/principal currently used by AWS CLI
aws sts get-caller-identity

# Check dev bucket Region (metadata)
aws s3api get-bucket-location --bucket orders-dev-invoices

# Check queue ARN given its URL
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-dev \
  --attribute-names QueueArn
~~~

These commands inspect the **active CLI context**, not the application's IAM role running inside ECS/EKS. Applications or pipelines must check **effective** credentials inside the runtime environment. Account, bucket, and queue values above are illustrative only.

## 6. Azure: Tenant, Subscription, Resource Group, and Managed Identity

### 6.1. Each Level Serves a Distinct Purpose

**Microsoft Entra tenant** manages identities. **Management groups** organize subscriptions for governance. **Subscriptions** serve as key boundaries for resources, quotas, and billing. **Resource groups** group resource lifecycles within a subscription; assigning RBAC and policies at the resource group level is useful, yet a resource group **does not create a new subscription**.

~~~mermaid
flowchart TD
    T["Microsoft Entra tenant"] --> MG["Management group"]
    MG --> D["Subscription: orders-dev"]
    MG --> P["Subscription: orders-prod"]
    D --> RD["Dev resource groups"]
    P --> RP["Prod resource groups"]
    RD --> SD["Blob / Service Bus / SQL / Key Vault dev"]
    RP --> SP["Blob / Service Bus / SQL / Key Vault prod"]
~~~

Small apps may use one subscription with multiple resource groups, provided you remember that subscription-level Owner/Contributor roles reach far wider than group-level roles. For critical production workloads, a dedicated subscription usually lowers the risk of accidental admin operations and simplifies quota/cost and policy governance.

### 6.2. Managed Identity and Data Roles

App Service, VMs, Functions, or supported Azure workloads can use **Managed Identity** to acquire tokens without storing long-lived client secrets. Each environment must receive the right identity and **data-plane roles** on target resources:

| Service | Dev Workload | Production Workload |
|---|---|---|
| Azure Blob Storage | Read/write dev containers only with required role | Prod containers only with required role |
| Azure Service Bus | Dev namespace/queue only | Prod namespace/queue only |
| Azure SQL Database | DB login/Entra user with test schema grants | Minimal-privilege DB principal on production |
| Azure Key Vault | Read dev secrets | Read production secrets only as strictly needed |

The resource management **Reader** role does not inherently permit reading blobs via Microsoft Entra. Assign the matching data role, such as **Storage Blob Data Reader/Contributor**, at the appropriate scope. For Service Bus, use **Azure Service Bus Data Sender/Receiver**. For Key Vault, depending on RBAC vs. access policy mode, verify data permissions to read secrets.

Also protect the ability of management roles to retrieve **storage account keys/SAS**: certain admin permissions can indirectly open data-plane access via Shared Key. If your organization authenticates via Entra, consider policies restricting Shared Key where supported by services and compatibility needs.

### 6.3. Reading Context with Azure CLI

~~~bash
az account show --query "{tenant:tenantId,subscription:id,name:name}"
az group list --query "[].{name:name,location:location}" --output table
az storage account show \
  --name ordersdevstore \
  --resource-group rg-orders-dev \
  --query "{name:name,location:location,sku:sku.name}"
~~~

The CLI defaulting to one subscription does not prove the app runs in the right subscription or identity. Cross-check full Azure resource IDs, tenant/subscription, and the deployment's actual managed identity. Resource group location also does not dictate the location of every resource inside the group.

## 7. Google Cloud: Separating Projects and Service Accounts

### 7.1. Organization, Folder, Project

A common separation model uses one Google Cloud organization and folders, with **projects** underneath per environment. A project owns resources, enables service APIs, and tracks many quotas/billing settings; folders/organization propagate governance policies within supported scopes.

~~~mermaid
flowchart TD
    O["Google Cloud organization"] --> FD["Folder: NonProduction"]
    O --> FP["Folder: Production"]
    FD --> D["Project: orders-dev"]
    FD --> S["Project: orders-staging"]
    FP --> P["Project: orders-prod"]
    D --> DD["Service account / GCS / PubSub / Cloud SQL dev"]
    S --> SS["Service account / GCS / PubSub / Cloud SQL staging"]
    P --> PP["Service account / GCS / PubSub / Cloud SQL prod"]
    BILL["Cloud Billing account"] -. "Bills project" .-> D
    BILL -. "Bills project" .-> S
    BILL -. "Bills project" .-> P
~~~

One billing account can link to many projects; **a billing account is not an IAM parent node** in the resource hierarchy. Sharing a billing account or organization does not automatically let a dev project's service account read resources in a prod project.

### 7.2. Service Accounts for Workloads and CI/CD

Cloud Run, GKE, or workloads on other platforms should use **dedicated service accounts per environment**; external environments can use Workload Identity Federation rather than downloading long-lived JSON keys. Grant permissions on the bucket, Pub/Sub topic/subscription, Secret Manager secret, or smallest appropriate scope.

- Object-reading workload: consider object/bucket read roles at the right scope, such as **Storage Object Viewer**.
- Producer sending events: **Pub/Sub Publisher** on the allowed topic.
- Consumer reading and ACKing events: **Pub/Sub Subscriber** on the allowed subscription.
- App reading secrets: **Secret Manager Secret Accessor** on the target secret.

Specific IAM permissions, API enablement, network restrictions, locations, and runtime service accounts must all align. When a workload runs in project A while the resource lives in project B, explicitly configure permissions on **the target resource** rather than assuming shared project access.

### 7.3. Checking Project and Bucket Location

~~~bash
gcloud config get-value project
gcloud auth list --filter="status:ACTIVE" --format="value(account)"
gcloud storage buckets describe gs://orders-dev-invoices \
  --format="yaml(name,location,locationType)"
~~~

`gcloud auth list` displays the CLI account, whereas **Application Default Credentials** or the Cloud Run/GKE service account can differ. Project ID alone cannot identify bucket location; read each resource's metadata. Pub/Sub message storage policies, secret replication locations, and DB backups must also be inspected separately.

## 8. Boundary Design Matrix for an Order Service

Suppose an `orders-service` system has a Spring Boot API, an event-processing worker, invoice object storage, a database, and secrets. One reference layout:

| Item | Dev | Integration/QA | Staging | Production |
|---|---|---|---|---|
| Cloud scope | `orders-dev` | `orders-qa` | `orders-staging` | `orders-prod` |
| Runtime identity | `orders-runtime-dev` | `orders-runtime-qa` | `orders-runtime-staging` | `orders-runtime-prod` |
| Object storage | Separate bucket/container | Separate with cleanup | Separate, prod-like config | Separate, proper retention/backups |
| Messaging | Separate queue/topic | Separate queue/topic | Separate queue/topic | Live queue/topic |
| Database | Synthetic schema/data, resettable | Isolated test DB or schema | Dedicated DB, migration rehearsal | Live data DB |
| Secrets | Dev/test secrets | Test secrets | Staging secrets | Production secrets |
| Network | Dev segment as needed | Test segment | Prod-like yet independent | Controlled ingress/egress, private access as needed |
| Deployment | Automated CI | CI + tests | Gated pipeline | Gates, audits, rollback, and change control |
| Data | Synthetic | Synthetic | Synthetic / safely transformed | Authorized live data |
| Cost | Small budget, auto-cleanup | TTL on test resources | Estimated per test plan | Budgets, alerts, capacity, and DR |

These names are **illustrative**, not provider-enforced naming mandates. When a single cloud resource can host multiple workloads, evaluate actual authorization and quotas rather than relying on names alone.

### 8.1. Tracing Data Paths

~~~mermaid
flowchart LR
    DAPI["Spring Boot DEV"] --> DQ["Queue DEV"]
    DAPI --> DDB["DB DEV"]
    DAPI --> DS["Storage DEV"]
    PAPI["Spring Boot PROD"] --> PQ["Queue PROD"]
    PAPI --> PDB["DB PROD"]
    PAPI --> PS["Storage PROD"]
    PX["Dev identity"] -. "Denied permission" .-> PQ
~~~

This diagram highlights an essential test: if an administrator accidentally puts the production queue URL in dev configuration, **the dev runtime identity must still be denied** at the target resource/policy. Accurate configuration and IAM enforcement must reinforce each other.

## 9. Data Separation: Never Copy Raw Production Data into Test

Data is often the hardest boundary. Safe options in priority order:

1. **Synthetic data generation:** generate users, orders, invoices, events, and payloads unrelated to real individuals. Suitable for most integration tests.
2. **Team-controlled fixtures:** small, versioned datasets with expected outcomes, reproducible via migrations/seeds.
3. **Risk-mitigated transformed data:** only when production data distributions are genuinely needed; evaluate masking, tokenization, anonymization, and re-identification risks, with formal internal policy approval.
4. **Tightly controlled production data:** only when business/compliance permits, with explicit permission design, auditing, and test scope; never treat as default.

**Masking does not automatically equal anonymization.** Replacing emails with `masked` while keeping IDs, addresses, birth dates, or join keys can still identify people. Also inspect attachments, object metadata, logs, event payloads, backups/snapshots, and embedded secrets/tokens.

### 9.1. Seeding and Cleanup Plans

A reliable integration test should:

- Create isolated test resources/namespaces or prefixes where appropriate, tagged with a test-run ID.
- Seed data with run-scoped IDs to avoid colliding with concurrent jobs.
- Constrain test principal permissions with zero access to prod.
- Clean up data by ID/run or destroy temporary resources via an appropriately scoped pipeline.
- Enforce **TTLs/lifecycles** on temporary resources and detect orphaned resources.
- Ensure tests can run in parallel without consuming one another's messages or rows.
- Never write secrets or sensitive data to test artifacts or logs.

If a test aborts mid-run, background cleanup or lifecycle policies must purge leftover data. Never run broad prefix deletions or cleanup scripts under a production identity.

### 9.2. Testcontainers, Mocks, and Cloud Integration Tests

**Testcontainers** or emulators can mimic partially compatible databases/queues/storage for fast logic tests. They do not prove IAM/RBAC policies, quota limits, endpoints, private networking, managed service behavior, or real data residency.

Therefore, maintain at least two layers: **cheap, fast, repeatable local tests**, plus **integration tests in an isolated cloud test scope** verifying identities, permissions, networking, service semantics, and lifecycles. Production data is not needed to verify any of these.

## 10. Spring Boot: Profiles Select Configuration, Cloud IAM Enforces Boundaries

### 10.1. Separating Application Configuration from Credentials

Spring Boot supports profiles and multiple configuration sources (environment variables, config trees, secret providers, config servers). Separate these categories cleanly:

- **Non-sensitive configuration:** bucket/container names, queues/topics, Region, project IDs, endpoints, feature flags.
- **Runtime identity:** IAM role / Managed Identity / service account bound to the workload per environment.
- **Secrets:** retrieved from a secret manager or controlled injection; never commit passwords or access keys.
- **Boundary policies:** IAM/RBAC, policies, firewalls, quotas, and audits live in cloud IaC, independent of profile values.

The example below uses **custom application-defined properties**:

~~~yaml
app:
  cloud:
    environment: dev
    provider: aws
    expected-account-id: "111122223333"
    region: ap-southeast-1
  storage:
    invoice-bucket: orders-dev-invoices
  messaging:
    orders-queue-url: https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-dev
~~~

Keys under `app.*` are not shared auto-configuration properties across Spring Cloud AWS/Azure/GCP. Bind and validate them in code. When promoting to production, supply production values through a trusted deployment system; **never simply flip `environment: prod`** while leaving dev targets intact.

When using Spring Cloud AWS, Spring Cloud Azure, or Spring Cloud GCP, pick a **BOM/starter compatible with your Spring Boot version**. Auto-configuration, property names, and credential discovery behavior can differ across library generations.

### 10.2. Blocking Startup If AWS Runtime Enters the Wrong Account

This is an **additional guard** in Spring Boot using AWS SDK v2 STS. The snippet verifies the account of effective credentials before the app serves traffic. It assumes Spring Boot 3.x, the AWS SDK v2 STS dependency, and `app.cloud.expected-account-id` configured.

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.sts.StsClient;

@ConfigurationProperties(prefix = "app.cloud")
record CloudBoundaryProperties(
        String environment, String provider,
        String expectedAccountId, String region) {}

@Configuration
@EnableConfigurationProperties(CloudBoundaryProperties.class)
class CloudBoundaryConfiguration {

    @Bean
    StsClient stsClient() {
        return StsClient.create();
    }

    @Bean
    ApplicationRunner verifyAwsAccount(
            StsClient sts, CloudBoundaryProperties properties) {
        return args -> {
            if (!"aws".equalsIgnoreCase(properties.provider())) {
                return;
            }
            String expected = properties.expectedAccountId();
            if (expected == null || expected.isBlank()) {
                throw new IllegalStateException("Missing expected AWS account ID");
            }
            String actual = sts.getCallerIdentity().account();
            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                        "Cloud account mismatch; deployment blocked");
            }
        };
    }
}
~~~

Notes:

- `GetCallerIdentity` returns **the account of the active principal**, without proving every target bucket/queue/DB belongs to that account. With **cross-account roles**, it returns the account of the assumed role.
- Integrate this into a real **startup gate** per your architecture. It catches misconfiguration early rather than replacing IAM/resource policies.
- The expected account ID must come from trusted deployment config, never end-user input. While not a secret, an account ID is still configuration requiring governance.
- Verify target endpoints/resource IDs, Regions, and permissions on target resources as well; never rely solely on resource name suffixes.
- On Azure, cross-check tenant/subscription/resource IDs and managed identity; on GCP, cross-check project ID/number, service account, and resource locations. Tools, SDKs, and permissions differ from AWS; do not copy STS logic blindly.
- **This account guard is skipped** when `provider` is not AWS. The snippet illustrates the pattern; add dedicated guards for other providers rather than assuming they are checked.

### 10.3. Profiles, Runtime Identities, and Endpoints Can Drift

A deployment can land in several combinations:

| Spring Profile | Runtime Credential | Resource Target | Assessment |
|---|---|---|---|
| dev | Dev role | Dev bucket | Valid if permissions are correct |
| dev | Dev role | Prod bucket | Must be blocked by IAM |
| prod | Dev role | Prod bucket | Identity/config mismatch; block at startup |
| prod | Prod role | Dev bucket | Target mismatch; block in config or policy |
| prod | Prod role | Prod bucket | Identity/resource aligned; still check RBAC/networking |

Rely on **effective credentials**, not config files alone. A laptop logged into the CLI with a personal user differs from a container's runtime role; local profiles, Azure CLI, gcloud, and Application Default Credentials do not always match the runtime's workload identity.

## 11. Environment-Scoped CI/CD and IaC Configuration

### 11.1. Build Once, Deploy Per Target

An auditable deployment pipeline:

~~~mermaid
flowchart TD
    C["Commit + automated tests"] --> B["Build / scan single artifact"]
    B --> DEV["Deploy DEV with DEV identity"]
    DEV --> QA["Integration tests on QA resources"]
    QA --> STG["Deploy STAGING same artifact"]
    STG --> G["Approval / policy / release gate"]
    G --> PRD["Deploy PROD with PROD identity"]
    PRD --> OBS["Health check, telemetry, rollback plan"]
~~~

Promote the same binary/container image digest across environments where appropriate to eliminate code drift. What varies per environment is **configuration, runtime identity, secrets, endpoints, and capacity**, managed by the pipeline and platform.

### 11.2. IaC Keeps Resources Separated and Reproducible

Terraform, AWS CloudFormation/CDK, Azure Bicep/ARM, or appropriate Google Cloud IaC tools describe resources with explicit identifiers. With Terraform, for instance, keep **state/backends and workspaces/stacks strictly isolated per environment**; sharing a single state between `dev` and `prod` risks catastrophic plan/apply mistakes.

A critical rule: the dev pipeline holds credentials and permissions only to create/modify **dev resources**. Production pipelines require explicit approval gates, reviewing the change plan (IaC plan), evaluating deletions/recreations, and checking migrations before applying.

### 11.3. Prefer Federation Over Static Keys Whenever Possible

- **AWS:** IAM roles with OIDC/federation and trust policies scoped by workflow/branch/environment.
- **Azure:** workload identity federation or scoped service connections; Managed Identity for supported runtimes.
- **Google Cloud:** Workload Identity Federation and environment-scoped service accounts.

These eliminate static CI keys. Still enforce strict **trust conditions**, resource scopes, short token lifetimes, and auditing.

### 11.4. Production Entry Gates

A production release should verify:
- Unit and integration tests in isolated environments.
- Dependency/container security scans and secret scanning.
- IaC/policy reviews covering IAM, network exposure, encryption, Region, replication, and backups.
- Backward-compatible DB migrations or tested rollback plans.
- Verified artifact digest, target account/subscription/project, Region, and workload identity.
- Rollback strategy, health monitoring, and designated incident owners.
- Blast-radius controls during rollout: canary, progressive delivery, or feature flags where appropriate.

An approval based merely on a job name like `deploy-prod` is insufficient. Verify the **actual deployment target** and the permissions of the token/credential used by the pipeline.

## 12. Secrets and Encryption Keys Must Be Environment-Scoped

Production secrets such as database passwords, partner API keys, signing keys, or tokens are managed separately. Dev/test secrets should be test-only values or narrowly scoped sandbox credentials.

| Asset Type | Dev/Test | Production | Why Separate |
|---|---|---|---|
| DB credentials | Test user/role | Production DB user | Prevents tests from querying live data |
| External API credentials | Provider sandbox account | Production integration account | Prevents tests from triggering real transactions |
| Signing/encryption keys | Separate key, test lifecycle | Key with strict protection policies | Prevents test tokens/objects from working in prod |
| Secret manager | Test secret path/vault/project | Prod secret path/vault/project | Independent permissions and rotation |
| Webhook endpoints | Test URL | Production URL | Prevents synthetic events from hitting live systems |
| OAuth/OIDC clients | Test redirect URI/audience | Production client and audience | Prevents token/callback confusion |
| Monitoring/export keys | Test sink | Production sink | Prevents polluted logs or mixed metrics |

When granting workloads secret read access, inspect **data-plane permissions** (such as AWS Secrets Manager `GetSecretValue`, Azure Key Vault secret data roles, or Google Secret Manager Secret Accessor) plus encryption-key access if required. Managing a secret resource does not grant permission to read its payload.

Never place real secrets in logged environment variables, Git-committed `application.yml` files, test fixtures, container images, or helper scripts. When secrets must appear in the runtime environment, restrict process/env metadata access and rotate them appropriately.

## 13. Separating Networks, Endpoints, and Data Storage Locations

IAM is an essential safeguard, yet network paths must also be defined:

- AWS: VPC/subnets/security groups/routes and service VPC endpoints; optionally separate VPCs/accounts per environment.
- Azure: VNets, network security rules, Private Endpoints, firewalls, and DNS; separate subscriptions/resource groups by design.
- Google Cloud: VPCs, firewall rules, Private Service Connect, VPC Service Controls, or appropriate service mechanisms; separate projects and service account permissions.

**Private endpoints do not replace IAM/RBAC**, nor do they move data into a different Region. Production resources may tighten network restrictions, while QA resources only open connectivity to test runners. If CI runs outside the cloud, design egress, firewalls, private runners, and DNS accurately.

### 13.1. Region, Replicas, and Residency

Production may enforce data residency. When standing up staging, never assume using a different Region or copying backups/data elsewhere is allowed. Verify **primary data, replicas, backups, snapshots, object versions, logs, messages, and secret locations** against compliance boundaries.

**Sharing a project/subscription/account does not guarantee every resource sits in the same Region.** Inspect each managed resource's metadata and replication settings. For Pub/Sub or systems with global API hosts, endpoints alone do not reveal where message payloads are stored.

### 13.2. Cross-Environment Access Must Be a Controlled Exception

Some platforms run shared services such as centralized logging, artifact registries, or identity providers that require limited dev/staging/prod connectivity. Explicitly document **which cross-environment flows are permitted**, including source principal, target resource, action, network path, and justification. Never let a dev runtime accidentally write to a production database/queue simply because both share an organization.

If production copies must feed analytics/testing, build a **one-way** pipeline with controlled filtering/masking, dedicated accounts, auditing, and retention/cleanup policies.

## 14. Quotas, Costs, and Resource Cleanup

Environment separation also supports financial governance: dev/test can use smaller tiers, auto-stop schedules, and TTLs on ephemeral resources; production maintains proper budgets, capacity planning, and DR. Keep in mind:

- **Dev should not arbitrarily run production tiers just to match an architecture diagram.** Some tests require prod-like HA or limit behavior; scale up only where specifically needed.
- **Budget alerts usually only notify**, rather than hard-stopping all cloud resources automatically.
- **Quotas carry explicit scopes:** AWS account/Region, Azure subscription/Region, Google project/Region/API, depending on the service.
- **Idle resources can still bill:** managed databases, disks, premium messaging tiers, reserved capacity, private networking, backups, and retained logs.
- **Tag/label test resources with expiration:** `environment=qa`, `service=orders`, `test-run-id`, `owner`, `expires-at` where supported.
- **Deletion protection** can guard critical production resources; pair it with backups and change workflows rather than treating it as a substitute for recovery.

A QA teardown job should hold delete permissions **only for resources created by QA runs or within the QA scope**. Wildcard deletes resembling prod names or ambiguous default projects are hazards that must be blocked via resource IDs and IAM.

## 15. Isolation Testing Scenarios

Environment-separation testing is part of **integration/security testing**, not just verifying that the app boots.

| Test | How to Execute in Test Environment | Expected Result |
|---|---|---|
| Correct account/project/subscription | Inspect effective runtime identity and resource IDs | Matches environment manifest |
| Dev accesses production storage | Test dev identity against prod resource ID in a safe permission test | Denied; zero reads/writes to live data |
| Dev publishes to production queue | Check IAM policy or controlled request | Publish denied |
| Staging reads production secret | Inspect scoped policy permissions | Denied |
| QA runs migrations | Execute against seeded QA database | Production schema untouched |
| Post-failure test cleanup | Interrupt a QA run and invoke cleanup | Only that run's QA resources are cleaned up |
| Changed target Region | Mismatched target config in QA environment | Deployment/startup validation fails |
| Same event ID redelivered | Redelivery/duplicate in QA queue | Zero duplicate business side effects |
| Prod pipeline uses dev identity | Check release gate/configured role | Blocked before deployment |
| Cross-environment wrong key/token | Test with test token/secret against another resource | Denied or rejected as invalid |
| QA resource budget/TTL | Provision TTL-tagged resource and verify alerts | No unbounded orphaned test resources |
| Production restore rehearsal | Restore backup into isolated scope with proper permissions | Restores cleanly without overwriting live systems |

**Negative tests** should use **IAM policy simulators/dry-runs, policy inspection, or test resources** whenever possible. Never delete or write to production resources merely to prove access is denied.

### 15.1. Provider-Specific Verification Matrix

| Requirement | AWS | Azure | Google Cloud |
|---|---|---|---|
| Verify identity | Workload's STS GetCallerIdentity | Managed Identity principal/tenant and token scope | Service account/ADC and project |
| Verify resource scope | Account ID, ARN, Region | Subscription ID, resource group, resource ID | Project ID/number, resource name/location |
| Verify cross-access block | IAM + resource policies + relevant SCPs | Azure RBAC/role scope + network | IAM + Organization Policy/perimeters where used |
| Verify target storage | S3 bucket + Region | Storage account/container + location | Cloud Storage bucket + location |
| Verify target messaging | SQS URL/SNS ARN | Service Bus namespace/queue/topic | Pub/Sub project/topic/subscription |
| Verify secrets | Secrets Manager ARN, KMS key | Key Vault URI, data role/access policy | Secret resource name and IAM |
| Verify database | Endpoint/VPC + DB grants | SQL endpoint/network + DB permissions | Cloud SQL endpoint/network + DB permissions |

Do not assume these role sets or verification mechanisms are identical one-to-one. They represent **similar isolation goals** implemented differently.

## 16. Common Real-World Mistakes and Fixes

### 16.1. Tests Run with Production Credentials on a Laptop

A developer logged AWS CLI/Azure CLI/gcloud into a production scope while Spring's profile is set to `test`. The SDK credential chain automatically picks up the overly broad principal. Separate dev profiles/accounts, use short-lived credentials, and check effective identity before integration runs; optionally block startup on expected account/subscription/project mismatches.

### 16.2. Staging Service Bus or Pub/Sub Consumers Read Live Messages

Both staging and prod share the same queue/subscription or overly broad IAM permissions. Test events and real events mix; one consumer even ACKs messages meant for the other. Fix by provisioning dedicated messaging resources, assigning narrow data roles, locking namespace/topic/subscription IDs in deployment manifests, and adding cross-env deny tests.

### 16.3. "Prod-Like" Staging Connects Directly to the Production Database

Wanting realistic test data, a team points staging's JDBC URL at the production database. Migrations or cleanup jobs can corrupt live data. Create an independent staging database with fixtures—or safely sanitized copies if justified—and validate the database endpoint/principal at startup.

### 16.4. CI/CD Uses One Owner Service Account Across All Projects

A leaked runner token or mis-targeted pipeline can alter every environment. Replace with environment-scoped federation/short-lived identities, least-privilege roles, branch/workflow conditions, production gates, and deployment audits. Resource-level policies must never let a dev CI role write to prod.

### 16.5. Overly Broad QA Cleanup Script

A test job uses a wildcard like `orders-*` and accidentally deletes a production bucket or queue. Use separate projects/accounts, generated run-scoped resource names, QA-only teardown permissions, explicit ID checks before deletion, and deletion protection on critical resources.

### 16.6. Same Secret Shared Between Staging and Production

A secret leaked in staging grants access to production APIs or decrypts prod data. Separate secrets, keys, and API credentials, use third-party sandbox endpoints, scope roles/secret paths by environment, and manage rotation and token scopes independently.

### 16.7. Network Isolation Is Correct, Yet IAM Remains Too Broad

Dev cannot reach the prod database directly over the network, yet holds a high-privilege role capable of altering firewall rules or retrieving account keys. Protect both the **management plane** and **data plane**: control who can edit networking, retrieve keys, modify IAM, and read data.

## 17. Pre-Production Architecture Review Checklist

- **Resource ownership:** each environment has a clearly protected account/subscription/project or scope; record IDs rather than display names alone.
- **Identity:** workloads and CI/CD use separate principals; dev/QA roles have zero data or admin permissions on prod.
- **Data:** databases, object storage, queues, topics, secrets, keys, backups, and logs have clear boundaries and lifecycles.
- **Network:** DNS, endpoints, firewalls/VPC/VNets/private access are verified per environment; never rely on profile names alone.
- **Configuration:** maintain a trusted source manifest for expected environment, account/project, Region, and resource IDs; catch drift with startup guards before traffic arrives.
- **Release:** build the artifact once, deploy with the right target identity, enforce test gates, require approvals as needed, inspect IaC diffs, and keep rollback ready.
- **Testing:** use synthetic fixtures, run-ID cleanup, negative IAM tests, duplicate/retry tests, and isolated restore tests.
- **Secrets:** never share production credentials; never log or commit secrets; rotate and revoke independently per environment.
- **Resilience:** prod HA/backups/DR meet RTO/RPO; dev/QA keep costs bounded while still validating required behavior.
- **Cost:** configure budgets/alerts, tags/labels, quotas, TTLs, and test-resource reclamation workflows.
- **Observability:** logs and metrics carry environment/resource IDs; audit policies, releases, cross-env errors, and permission changes.
- **Reviews:** periodically detect orphaned resources, excess permissions, endpoint drift, and obsolete cross-env exceptions.

## 18. Summary

**Separating dev, test, staging, and production means separating the ability to affect data and resources**, not merely swapping config filenames. AWS typically uses **accounts**; Azure typically uses **subscriptions** paired with resource groups and Entra identities; Google Cloud typically uses **projects**, folders, and service accounts to build governance boundaries. Across all three clouds, IAM/RBAC, networking, keys, data, endpoints, and CI/CD determine true isolation.

When practicing Spring Boot with Spring Cloud AWS/Azure/GCP, start from **environment → principal → resource ID → permissions → data → network path → deployment/testing lifecycle**. Once every boundary has verifiable evidence, development teams can iterate rapidly without risking cross-environment impact on customer-facing systems.
