# Organizing Source Code and Azure Deployment Environments

## 1. Real-world problem: from Git commit to production

A development team builds a commerce system on Azure: Java/Spring Boot **orders-api**, a **payment-worker**, a frontend, Azure Container Registry, Azure Container Apps or AKS, Azure SQL, Storage, Key Vault, and Application Insights. Initially, an engineer builds images on a personal machine, stores configuration in files, and deploys directly into a single resource group.

As the project grows, problems emerge:

- Each team member's environment differs, making bugs impossible to reproduce.
- For the same commit, staging and production run different builds.
- A developer has permissions to modify production resources and secrets.
- Java code is duplicated into dev/test/prod folders and drifts apart over time.
- CI does not check tests, dependency vulnerabilities, or IaC security.
- It is unknown which commit, build, and dependencies produced the running artifact.
- A command modifying a firewall or changing a database schema breaks the application.
- Logs, budgets, and administrative permissions across environments are mixed together.

**Organizing source code and Azure deployment environments** is the design of repositories, application structure, artifact sources, Infrastructure as Code, identities, and the promotion process so that applications can change rapidly while remaining traceable, verifiable, and recoverable.

This lesson belongs to the **CI/CD and Software Supply Chain** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module context covers Azure subscription/resource group, Microsoft Entra ID, networking, compute, storage, data, monitoring, security, and cost management. The focus is the **source → artifact → environment** boundary, not just a single build/deploy command.

Environment names, resources, regions, and numbers in this lesson are all **hypothetical examples**. Execute only on authorized subscriptions.

## 2. Learning objectives

After this lesson, learners will be able to:

1. Distinguish between source, commit, artifact, deployment, release, and runtime environment.
2. Choose monorepo, polyrepo, or hybrid based on ownership and release cadence.
3. Organize folders for services, libraries, IaC, CI/CD, docs, tests, and runbooks.
4. Apply protected branches, pull requests, CODEOWNERS, and quality gates.
5. Design dev/test/staging/prod using appropriate Azure subscriptions, RGs, permissions, and networking.
6. Manage environment parameters using config and secrets instead of forking source code.
7. Write modular Bicep/Terraform parameterized by environment.
8. Understand OIDC/workload identity federation for GitHub Actions or Azure Pipelines.
9. Implement build once, promote the same artifact image digest across multiple environments.
10. Use SBOMs, dependency/secret scanning, provenance, and artifact signing where appropriate.
11. Design migrations, approval gates, rollbacks, canaries, and feature flags.
12. Measure SLOs, post-deploy errors, pipeline lead time, security incidents, and cost per environment.

## 3. Core concepts

| Concept | Meaning | Example |
|---|---|---|
| **Source repository** | Source code managed with Git | Java, tests, Dockerfile, Bicep |
| **Commit** | Snapshot of changes with a Git hash | PR merge commit |
| **Build artifact** | Output produced by CI | JAR, OCI container image |
| **Artifact digest** | Content identifier independent of tag name | SHA-256 image digest |
| **Deployment environment** | Set of resources, data, identity, and policy | dev, staging, prod |
| **Infrastructure as Code** | Describing cloud resources in code | Bicep, Terraform |
| **Deployment** | Placing an artifact and configuration into runtime | Container Apps revision |
| **Release** | Exposing changes to users | Canary or enabling a feature flag |
| **Runtime identity** | Principal used by the application to access Azure | User-assigned managed identity |
| **Deployment identity** | Principal used by CI/CD to manage resources | OIDC federated service principal |
| **Policy gate** | Condition blocking promotion if unmet | Required checks, manual approval |

### 3.1. Deploy is different from release

An application may already be deployed while a feature remains turned off behind a feature flag. Only when the flag is enabled for a group of users is it a release in the product sense. This approach reduces the need to redeploy to toggle a capability on or off, though flags must also be governed.

### 3.2. An environment is not a Git branch

A branch named `prod` does not prove that code is safe or running in production. An environment consists of Azure resources with specific permissions, networking, data, and configuration. Trunk-based development can still deploy from the same `main` commit through dev → staging → prod.

### 3.3. A repository is not an artifact registry

Git stores source code and versionable configuration. ACR or an artifact repository holds build artifacts and metadata. Do not commit binary JARs and container layers into Git as a substitute for artifact management.

## 4. End-to-end source → Azure model

~~~mermaid
flowchart LR
    DEV[Developer / Pull Request] --> GIT[Git repository]
    GIT --> CI[CI: test, scan, build]
    CI --> ART[Artifact + digest + SBOM]
    ART --> ACR[(Azure Container Registry)]
    GIT --> IAC[IaC plan and policy checks]
    IAC --> INFRA[Azure subscriptions / RG / network / identity]
    ACR --> CD[CD: approvals + promotion]
    CD --> D[Development / QA]
    D --> S[Staging]
    S --> P[Production]
    INFRA --> D
    INFRA --> S
    INFRA --> P
    P --> MON[Azure Monitor / Application Insights]
    MON --> GATE[Verification and rollback decision]
~~~

The two streams are related but require separated permissions:

- **Application delivery:** source code, tests, build, scan, artifact, deploy.
- **Infrastructure management:** Azure Policy, network, IAM, Key Vault, workloads, budgets, IaC state.

A routine pull request workflow should not hold Owner permissions across an entire subscription merely to deploy an application.

## 5. Repository design principles

1. **Single source of truth:** every resource/module has a primary owner and location of management.
2. **Bounded contexts:** organize code by domain/service instead of an unbounded shared folder.
3. **Reproducible builds:** pin toolchains, dependency versions, and maintain appropriate lock/manifest files.
4. **Build artifacts contain no secrets.**
5. **Non-secret configuration and secrets are separated from business code.**
6. **IaC is reviewed:** limit drift from manual Portal changes.
7. **CI must validate before publishing or deploying.**
8. **Audit trail:** know who approved a change and which digest is running.
9. **Least privilege:** reviewers, CI, deploy principals, and runtime apps hold distinct permissions.
10. **Testability:** business modules do not require production resources for unit testing.

### 5.1. Do not duplicate source by environment

Avoid maintaining three copies—**orders-api-dev**, **orders-api-stage**, **orders-api-prod**—containing nearly identical Java code. A single codebase with a shared artifact and per-environment configuration makes it easy to verify that the code tested in staging is the exact code promoted.

### 5.2. Do not dump everything into a utils folder

Shared code needs an owner, version, tests, compatibility contract, and clear API. A massive `helpers` directory creates cross-service coupling.

### 5.3. Deployable boundary differs from library boundary

A microservice is deployed independently; a shared library is only a dependency. Do not create a new microservice without a clear reason around ownership, scaling, security, or release cadence.

## 6. Monorepo, polyrepo, and hybrid

| Type | Definition | Pros | Trade-offs |
|---|---|---|---|
| **Monorepo** | Multiple services/libraries/IaC in one repo | Easy cross-service refactoring, unified CI | Selective builds, permissions, and dependency graph are complex |
| **Polyrepo** | One repo per service or library | Independent ownership/release cadence | More contract/version coordination and automation required |
| **Hybrid** | Separate service repos, separate platform/IaC/GitOps repo | Separates security boundaries, shares policy | Requires consistent artifact/config version management |

### 6.1. When monorepo fits

Services change together, teams are not overly fragmented, contracts are centrally managed, and CI has reliable path filters and dependency graphs.

### 6.2. When polyrepo fits

Teams have distinct security permissions, release cadences, and business ownership. Transparent versioning, API contract tests, and build dependencies are required.

### 6.3. Hybrid for an Azure landing zone

The platform team can own repositories for subscription policies, hub networking, and identities; each application team owns its service repository; the deployment/GitOps configuration repository is protected. This ensures application CI does not need permissions to modify management groups.

### 6.4. Do not default to the most complex topology

The number of services, team size, permissions, cross-repo changes, and lead time should drive the choice. Changing repository topology later requires preserving Git history, releases, dependency paths, and automation.

## 7. Suggested monorepo structure

~~~text
commerce-platform/
  README.md
  CODEOWNERS
  .editorconfig
  .gitignore
  .github/
    workflows/
      pr-verify.yml
      publish-image.yml
      deploy.yml
  docs/
    architecture/
      adr/
    runbooks/
    security/
  services/
    orders-api/
      pom.xml
      Dockerfile
      src/
        main/
          java/
          resources/
            application.yml
        test/
          java/
    payment-worker/
      pom.xml
      Dockerfile
      src/
        main/
        test/
  libraries/
    event-contracts/
      pom.xml
  infra/
    modules/
      network.bicep
      identity.bicep
      monitoring.bicep
      container-app.bicep
    environments/
      dev/
        main.bicep
        main.bicepparam
      staging/
        main.bicep
        main.bicepparam
      prod/
        main.bicep
        main.bicepparam
  deploy/
    dev.yml
    staging.yml
    prod.yml
  scripts/
    validate-config.ps1
    smoke-test.sh
  security/
    threat-model.md
    supply-chain-policy.md
~~~

This is a theoretical example, not actual files existing in the learner's workspace.

### 7.1. Role of each area

- **services/**: independently deployed applications.
- **libraries/**: shared contracts and libraries.
- **infra/modules/**: reusable resource components.
- **infra/environments/**: per-environment compositions and parameters.
- **deploy/**: non-secret configuration values.
- **.github/workflows/**: CI/CD and permission controls.
- **docs/architecture/adr/**: rationale and trade-offs behind decisions.
- **docs/runbooks/**: operations, incident, rollback, and recovery guides.

### 7.2. Terraform instead of Bicep

If using Terraform, the same modules/environments principles apply; additionally, remote state, locking, provider pinning, and approvals are required. Never let two IaC engines independently manage the same Azure resource without clearly defined ownership.

### 7.3. Do not commit secrets into deploy/prod.yml

Store only non-secret parameters: resource names, replica limits, image digests, or non-exposing Key Vault references. Never store passwords, SAS tokens, service principal secrets, or real customer data.

## 8. Domain boundaries in Java

Example package layout for `orders-api`:

~~~text
com.example.orders
  api/
    OrderController.java
    request/
    response/
  application/
    CreateOrderService.java
    OrderQueryService.java
  domain/
    Order.java
    OrderStatus.java
  ports/
    OrderRepository.java
    EventPublisher.java
  adapters/
    persistence/
      CosmosOrderRepository.java
    messaging/
      ServiceBusEventPublisher.java
  config/
    AzureClientsConfiguration.java
  observability/
    RequestTracing.java
~~~

### 8.1. Business logic should not depend too deeply on SDKs

The `domain/application` layer can rely on interfaces (ports). Adapters use the Cosmos DB, Azure SQL, or Service Bus SDKs to implement them. This allows unit tests to run without an Azure subscription and lowers the cost of changing storage technologies.

### 8.2. API/event contracts

Maintain versioned HTTP API schemas or event contracts across multiple services. Do not casually share internal database entities because a mapping change can break downstream consumers.

### 8.3. Test pyramid

Unit tests verify business rules, contract tests verify compatibility, integration tests use appropriate Azure test resources or emulators, and end-to-end tests verify the deployment path.

## 9. Branching, pull requests, and ownership

Two common models:

- **Trunk-based:** small PRs → protected `main` → CI → build/promotion, using feature flags when needed.
- **GitFlow:** develop/release/hotfix branches supporting scheduled releases, with higher merge and divergence overhead.

A sensible policy for the sample system:

1. `main` is protected; no arbitrary force-pushes.
2. PRs require reviewers per `CODEOWNERS`.
3. Required CI checks must pass before merging.
4. IaC/security changes require platform/security review.
5. Pull requests from forks run in a context without production secrets or deploy permissions.
6. Release tags and image digests are governed and tied explicitly to commits.
7. Emergency hotfixes still require traceability and post-deployment review.

### 9.1. Path filters in a monorepo

A PR modifying only `orders-api` can run focused tests; a PR modifying a shared contract, parent BOM, or IaC module must trigger tests for dependents. Path filters do not replace a dependency graph.

### 9.2. Do not map branch names to authorization

A `prod` branch does not by itself guarantee deployment authorization. CI deployment identity, protected environments, approvals, and artifact checks must enforce the decision.

### 9.3. PRs from forks may contain untrusted code

Do not use a workflow with a privileged token to check out and arbitrarily execute untrusted contributor code. Separate test jobs (read-only) from release jobs (restricted Azure permissions).
## 10. Designing dev, test, staging, and production

Each environment must have a clear **verification purpose**, access boundary, and data policy.

| Environment | Objective | Data | Permissions and controls |
|---|---|---|---|
| **Development** | Development, integration experiments | Fake/synthetic | Dev identity, low budget |
| **Test/QA** | Functional/contract/regression | Synthetic matching production schema | QA pipeline identity |
| **Staging/Preprod** | Verify prod-like topology | Synthetic or privacy-sanitized | Release identity, gated deploy |
| **Production** | Real users | Protected real data | Prod-only identity, approvals/SLO |
| **Ephemeral PR** | Temporary per-PR preview | Test data | Unique names, auto-cleanup, TTL |

### 10.1. Are all four environments mandatory?

No. Small teams can use dev–staging–prod. An environment without specific test suites or operational purpose only increases cost and drift.

### 10.2. Do not copy raw production data down to QA

Use synthetic data or verified masking in compliance with privacy policies. Do not grant QA direct read access to production Key Vaults or databases just for quick debugging.

### 10.3. Staging must mirror production on key risks

Authentication, private networking, TLS, app identity, database migrations, ingress, observability, and deployment mechanisms must be tested in an equivalent topology. Scale such as RU/s or replica counts may differ if trade-offs are documented.

### 10.4. Ephemeral environments need an owner and expiration

Previews must have unique suffixes, tags, cost limits, and controlled teardown when a PR closes to avoid leaving unmanaged clusters, databases, or secrets running indefinitely.

## 11. Azure tenant, management groups, subscriptions, and RGs

~~~text
Microsoft Entra tenant
  |
Management Group hierarchy
  |
  +-- Nonproduction subscription
  |      +-- rg-commerce-dev
  |      +-- rg-commerce-test
  |
  +-- Production subscription
         +-- rg-commerce-staging (if policy allows)
         +-- rg-commerce-prod
~~~

- **Entra tenant:** identities and directory controls.
- **Management group:** applies governance/policy across multiple subscriptions.
- **Subscription:** billing, quotas, Azure RBAC, and governance scope.
- **Resource group:** organizes resources by lifecycle/management.
- **Resource:** compute, data, storage, network, secrets, monitoring.

### 11.1. A resource group is not a firewall

Resources in two different RGs can still connect or share permissions. Isolation must use networking, authentication, RBAC, and service policies.

### 11.2. When should prod have its own subscription?

When independent budgets, permissions, quotas, guardrails, or compliance are required; separating prod from nonprod limits the administrative blast radius.

### 11.3. Do not proliferate subscriptions endlessly

More subscriptions add overhead for networking, monitoring, quotas, billing, and role management. Follow your organization's Azure landing zone/governance rather than inventing an ad-hoc hierarchy.

## 12. Resource isolation matrix

| Component | Nonprod | Staging | Prod |
|---|---|---|---|
| **Resource group** | Separate | Separate | Separate |
| **ACR** | Controlled shared or separate | Pull verified image | Pull-only, digest pinning |
| **Key Vault** | Test secrets | Staging secrets | Dedicated production vault/permissions |
| **Database** | Fake data | Schema-accurate fake data | Real data + backup policy |
| **Managed identity** | Sandbox role | Preprod role | Least-privilege production identity |
| **Private network** | Configured as feasible | Test prod topology | Private DNS/endpoint/firewall per policy |
| **Log Analytics** | Short retention/budget | Release telemetry | Separate retention and access |
| **Budget** | Capped | Forecast | Alert + chargeback |

### 12.1. A shared ACR can make sense

A shared ACR holding build artifacts enables promoting the exact same digest. However, CI push scope, prod pull scope, network/trust, and artifact integrity must remain separated.

### 12.2. Do not share the production DB as staging

Even with the same schema, deploying migrations or running load tests can impact real user data and performance.

### 12.3. Differences between staging and production must be documented

An intentional difference such as fewer replicas is less dangerous than an unknown difference, such as prod connecting exclusively via private endpoints while staging always uses public endpoints.

## 13. Naming, tagging, and Azure Policy

Example naming convention:

~~~text
rg-<app>-<env>-<region>
ca-<app>-<service>-<env>
kv-<app>-<env>-<suffix>
mi-<app>-<service>-<env>
law-<app>-<env>
acr<app><env><suffix>
~~~

**Naming constraints vary by Azure resource type**, so verify allowed characters, length, and global uniqueness requirements instead of applying one template blindly across all services.

Suggested tags:

~~~text
application = commerce
environment = prod
owner = platform-team
costCenter = cc-200
dataClassification = confidential
businessCriticality = high
managedBy = iac
~~~

### 13.1. Tags do not grant or enforce permissions

A tag `environment=prod` does not make a resource secure. Entra/RBAC, network policies, and Azure Policy assignments provide the actual controls.

### 13.2. Azure Policy and guardrails

Allowed regions, required tags, public access restrictions, and security baselines can be enforced with policies. Management-group or subscription-wide changes require separate review due to their wide blast radius.

### 13.3. Never put secrets or PII in tags

Names and tags can appear in the Portal, diagnostics, and billing exports; store only approved governance metadata.

## 14. Runtime configuration without forking code

~~~text
Nonsecret code defaults
   + Environment config
   + Deployment settings
   + Managed identity / Key Vault
   + Feature flags
   = Runtime configuration
~~~

Example **Spring Boot application.yml** using environment placeholders:

~~~yaml
spring:
  application:
    name: orders-api

app:
  storage:
    endpoint: ${AZURE_BLOB_ENDPOINT}
  messaging:
    namespace: ${AZURE_SERVICEBUS_NAMESPACE}
  features:
    newCheckout: ${FEATURE_NEW_CHECKOUT:false}
~~~

Placeholders in the generated Markdown file use Spring syntax with a dollar sign and curly braces. Actual values are injected via the deployment runtime rather than hardcoding production URLs or secrets.

### 14.1. Values safe to version

Logical environment names, non-secret resource names, quotas/replicas, feature defaults, timeouts, approved regions, and policy-compliant Key Vault references.

### 14.2. Never commit

Database passwords, SAS/storage account keys, service principal secrets, access tokens, private certificates, raw production customer data, or connection strings containing credentials.

### 14.3. A Spring profile is not a security boundary

`spring.profiles.active=prod` only selects configuration. Pipelines must independently verify target subscriptions/resources and runtime identities.

## 15. Microsoft Entra, workload identity, and Key Vault

~~~mermaid
flowchart LR
    PIPE[CI/CD federated identity] --> ARM[Azure control plane]
    ARM --> APP[Azure runtime app]
    APP --> MI[Runtime managed identity]
    MI --> DB[(Azure SQL / Cosmos)]
    MI --> BLOB[(Azure Storage)]
    MI --> BUS[Service Bus]
    MI --> KV[Azure Key Vault]
~~~

### 15.1. Separate identities by responsibility

- **CI identity:** deploys only to the designated resources/environment.
- **Runtime managed identity:** data-plane roles for Storage, Service Bus, SQL/Cosmos, and Key Vault per business needs.
- **Developer identity:** dev/sandbox access, no default production access.

### 15.2. Avoid long-lived client secrets when federation is available

OIDC/workload identity federation lets CI obtain short-lived tokens through Microsoft Entra. Configure strict trust for repo/branch/environment and audience per provider; never grant subscription Owner unnecessarily.

### 15.3. Key Vault and App Configuration

Key Vault is for secrets, certificates, and keys. Non-secret configuration and feature flags can use App Configuration where appropriate. Verify refresh/cache behavior, identity permissions, and rotation.

### 15.4. When secrets leak into Git

Simply deleting the line of code is insufficient. Revoke/rotate credentials, inspect history, forks, and artifact logs, assess access, and execute incident response.

## 16. Networking must be tested from the real runtime

~~~mermaid
flowchart LR
    USERS[Users] --> EDGE[Front Door / Ingress]
    EDGE --> APP[App Service / AKS / Container Apps]
    APP --> DNS[Private DNS]
    DNS --> PE[Private Endpoints]
    PE --> DB[(Database)]
    PE --> KV[(Key Vault)]
    PE --> STORAGE[(Storage)]
    APP --> MON[Azure Monitor]
~~~

### 16.1. Private DNS and networking are part of the environment

If dev uses a public DB while production uses a private endpoint, DNS or firewall bugs may surface only at release time. Design staging to exercise the same critical paths.

### 16.2. Networking differs from RBAC

Successful DNS/TLS does not prove a principal has database or Key Vault permissions. Distinguish clearly between network errors, authentication failures, and data-plane authorization.

### 16.3. Do not fix connectivity issues by disabling security

Never enable allow-all public access, skip TLS certificate validation, or put production credentials into CI as a temporary workaround without approval.

### 16.4. Cross-subscription shared resources need access contracts

ACR, private DNS, and central logging may reside in a platform subscription. Ensure roles/scopes, network routes, data residency, and ownership are clearly defined.
## 17. IaC: a single definition source for Azure resources

Two common approaches:

- **Bicep/ARM**: describes Azure Resource Manager resources by schema, supporting modules and parameter files.
- **Terraform**: manages multi-provider infrastructure via plan/apply, provider versions, and a state backend.

Both can coexist in an organization when **scope and ownership are clearly delineated**; avoid having two IaC engines independently apply changes to the same resource.

### 17.1. Sample Storage Bicep module

~~~bicep
targetScope = 'resourceGroup'

@description('Storage account name must be globally unique')
param storageName string

param location string = resourceGroup().location

param commonTags object = {
  environment: 'dev'
  application: 'commerce'
  managedBy: 'bicep'
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  tags: commonTags
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageResourceId string = storage.id
~~~

This is an educational sample. Verify the Azure API version, allowed regions, naming rules, network restrictions, encryption/backup, and organizational policies before applying.

### 17.2. Separate modules and composition

**infra/modules** holds networking, identity, app runtime, monitoring, and database components; **infra/environments** composes modules with parameter sets for dev/staging/prod. This reduces duplicate definitions.

### 17.3. Do not re-provision all production infrastructure on every code deploy

Normal application CI/CD only updates the app artifact/config within its scope. Foundation management—such as policies, hub VNets, and Azure SQL provisioning—follows separate release/change controls.

### 17.4. Review IaC like source code

Inspect permissions, network exposure, resource deletions, retention, cost, destructive changes, regional availability, and compliance before applying.

## 18. Per-environment parameter files

Assuming **infra/environments/dev/main.bicep** defines the corresponding parameters, a parameter file may look like:

~~~bicep
using './main.bicep'

param location = 'southeastasia'
param environment = 'dev'
param minReplicas = 1
param maxReplicas = 2
param storageAccountName = 'commerceorderdev001'
~~~

### 18.1. A sample is not a complete deployment command

The main file must declare the parameters above along with concrete modules/resources. The Storage name is an example and may not be globally unique. The region is illustrative, not a default for every organization.

### 18.2. Configuration contains no secrets

Bicep parameters in Git should only contain non-secrets. If a secret input is needed, use secure parameters or Key Vault integration per supported mechanisms and policy. Never print secret values in job logs.

### 18.3. One composition, multiple parameter sets

Share the same Bicep modules across dev/test/staging/prod via parameter files. Differences must be reviewed rather than duplicating Bicep files four times and letting them drift.

## 19. Terraform state is sensitive data

When using Terraform:

- Pin provider and Terraform versions.
- Use a **remote backend** with access control and encryption.
- Enable locking when supported by the backend to prevent concurrent applies.
- Keep **separate state per environment/ownership boundary**.
- Protect snapshots/backups and avoid printing state into PR logs.
- Review the plan and policy compliance before applying.
- Perform migrations, imports, or state moves under controlled procedures rather than ad-hoc state edits.

### 19.1. Terraform workspaces do not replace Azure subscriptions

Terraform workspaces separate state but do not create RBAC, network, or billing boundaries. For production environments with high security requirements, use isolated backends/states with approved principals and scopes.

### 19.2. Do not let PR jobs auto-apply or destroy

Pull request validation typically runs lint/validate/plan in a restricted context. Apply/destroy requires an identity authorized for that environment, manual/reviewer gates for sensitive changes, and audit logging.

### 19.3. Sensitive outputs do not mean state is secret-free

Terraform state can store raw sensitive attributes. Apply RBAC, encryption, and secure pipelines, and minimize generating secrets inside Terraform when unnecessary.

## 20. Drift detection, what-if, and infrastructure change workflow

**Drift** is divergence between actual Azure infrastructure and desired state in IaC—for instance, an operator enabling public network access to debug an issue without updating IaC.

Workflow:

1. Inventory the exact subscription, resource group, and owner.
2. Run Bicep what-if or Terraform plan.
3. Review network, IAM, data loss, change impact, and cost.
4. Obtain approval commensurate with risk.
5. Deploy/apply using a properly scoped principal.
6. Read back state and critical properties from Azure.
7. Run integration, smoke, and policy checks.
8. Record deployment ID/commit and reconcile any remaining drift.

### 20.1. What-if does not prove production is completely safe

Provider/API responses may lack full runtime details. Changes to networking, database schemas, RBAC, and deletions still require owner review.

### 20.2. Emergency Portal changes

If rapid changes are needed to restore service, log an incident/change record and backport them into IaC afterward. Never allow production configuration to exist solely out-of-band without Git reflecting it.

### 20.3. Prevent destructive cleanup

Scripts must verify subscription ID, RG, environment tags, and approval before deleting anything. Never use wildcards or potentially empty shell variables as the target for deleting a resource group.

## 21. Data and database migrations across environments

**Dev/test** uses synthetic data; **staging** uses production-like schema and connectivity; **prod** enforces dedicated backup/restore, retention, and change policies.

### 21.1. Expand–migrate–contract

A safe database schema change generally proceeds through:

1. **Expand:** add new fields/columns while old code continues running.
2. **Migrate:** backfill or dual-read/write as needed and verify data quality.
3. **Contract:** remove old fields only after all consumers have migrated and the rollback window has closed.

### 21.2. Application rollback does not roll back the database

If the new release has written a new format, the old image may not be able to read it. Design for backward compatibility and forward-fix rather than assuming a commit revert restores all state.

### 21.3. Avoid running migrations on every Pod startup

20 replicas running a destructive migration concurrently can cause conflicts. Use a dedicated release migration job with locking/idempotency, verification, and approval.

### 21.4. Do not use the production DB for load tests

Load/performance tests can mutate data, create locks, spike RU/s, or trigger billing surges. Run them in an environment with representative synthetic datasets and sizing.

## 22. What is CI and what evidence should it produce?

**Continuous Integration (CI)** validates changes before merge or builds trustworthy artifacts.

A CI pipeline for Java/containers should include:

~~~text
Checkout exact commit
    |
Toolchain setup + pinned dependencies
    |
Formatting / lint
    |
Compile + unit tests
    |
Appropriate contract + integration tests
    |
SAST / SCA / license + secret scan
    |
IaC validation (if changed)
    |
Build OCI image / JAR
    |
Image and dependency scan
    |
SBOM + provenance / signing per policy
    |
Push immutable artifact to registry
~~~

### 22.1. Never merge with failing tests hoping deploy will fix it

Required checks must run from trusted pipeline configuration. Maintain branch protection and review even when tests are fast.

### 22.2. Dependency cache is not a source of truth

Caching speeds up builds, but dependency resolution must still enforce version pinning and source verification. Never cache credentials or untrusted artifacts and reuse them in privileged release jobs.

### 22.3. PR context differs from release context

PR verification should have read-only access and require no Azure production credentials. Publish/release jobs run only on protected refs with separate approvals and identities.

## 23. CI build once, deploy many times

The **build once, promote the same artifact** principle:

~~~text
Source commit A
    |
CI build and verify
    |
Image: acr.example.azurecr.io/orders-api@sha256:<digest>
    |
    +--> Development
    |
    +--> Staging
    |
    +--> Production
~~~

### 23.1. Why does the digest matter?

A tag like **latest**, **stable**, or **v1.2.3** can be reassigned if the registry lacks proper controls. An **image digest** references the artifact content and confirms that the exact image tested is the image deployed.

### 23.2. Do not rebuild during promotion

If staging rebuilds from the same source, differences in dependency resolution or toolchains can alter the artifact. Promotion must carry forward the verified digest, version, and provenance rather than recompiling production in another job.

### 23.3. Registry artifacts and deployment config are independent

The image digest is part of the release manifest. Environment-specific config, database connectivity, managed identity, and compute sizing are supplied at deploy time. The image does not need to contain secrets.

### 23.4. Copying images across registries

If policy requires separate ACRs, promote images via supported import/copy mechanisms. Verify the image manifest/digest, signatures/provenance, and policies—do not rely solely on matching tag names.

## 24. Choosing platforms for artifacts and runtime

| Workload | Artifact format | Suitable Azure runtime options |
|---|---|---|
| Spring Boot REST API | OCI image or JAR | Container Apps, AKS, App Service |
| Java batch/worker | OCI image | Container Apps Jobs, AKS Jobs, VM |
| Azure Functions | Function app package/container by hosting plan | Azure Functions |
| Frontend static | Built static assets | Static Web Apps, Storage/CDN as needed |
| Shared Java library | Maven package | Managed artifact repository |
| IaC | Bicep/Terraform modules | CI/CD deployment engine |

### 24.1. Can one image target multiple runtimes?

Not every image is completely portable: ports, probes, filesystems, env vars, networking, identity integration, and architecture must match. Even with the same digest, runtime behavior still depends on the environment.

### 24.2. AKS or Container Apps?

AKS fits when fine-grained Kubernetes, networking, and policy control is needed. Container Apps provides a container PaaS model with revisions and scaling suited for many workloads. Choose based on operational requirements, not just "easier CI/CD" at the expense of networking or data needs.

### 24.3. ACR permissions

Publishers need push permissions as appropriate. Runtime identities need pull access. Do not enable the ACR admin user as a default shortcut when Entra RBAC/managed identity is available.

## 25. CD: gated promotion flow

~~~mermaid
flowchart TD
    B[Verified artifact digest] --> D[Deploy Dev]
    D --> T{Smoke / Integration PASS?}
    T -- No --> X[Stop + investigate]
    T -- Yes --> S[Deploy Staging]
    S --> Q{E2E / Security / Performance PASS?}
    Q -- No --> X
    Q -- Yes --> A{Protected approval / change policy}
    A -- No --> X
    A -- Yes --> P[Deploy Production gradually]
    P --> H{Health and SLO within budget?}
    H -- No --> R[Rollback or halt rollout]
    H -- Yes --> F[Record release provenance]
~~~

### 25.1. Human approval is not required for every nonprod deploy

Dev can deploy automatically once CI passes. Production requires gates commensurate with risk and compliance; platforms support protected environments, reviewers, required checks, or approvals within the chosen toolchain.

### 25.2. Promote artifacts that passed staging

Record the digest, source commit, build workflow run, scan reports, and approval change ID. Do not allow deploying an arbitrary unvetted tag from the registry.

### 25.3. Idempotent deployments

Re-running a deployment with the same manifest/digest should converge to the expected state without creating unbounded resources or duplicate business operations.

### 25.4. IaC and app deployments can have different lifecycles

A network or database change may require migration or staged rollout before deploying the image. The release orchestrator must understand dependencies and compatibility rather than simply running files alphabetically.

## 26. GitHub Actions and Azure Pipelines: choose the tool, keep the principles

Both **GitHub Actions** and **Azure DevOps Pipelines** can automate CI/CD with Entra/federated identities, reusable pipeline templates, and approval controls per product capabilities.

| Purpose | GitHub Actions | Azure Pipelines |
|---|---|---|
| PR checks | workflows and branch rules | PR validation/policies |
| Build Java | runner + Maven/JDK setup | agent + Maven/Java tasks |
| Azure authentication | OIDC via `azure/login` when configured | Workload identity federation service connection |
| Protected production | GitHub environments/rules | Environments/approvals/checks |
| Artifact metadata | build artifacts/packages, container registry | pipeline artifacts/packages, ACR |
| IaC checks | Bicep/Terraform CLI/actions | CLI/tasks/templates |
| Logs/audit | Workflow/job records | Pipeline run logs and approvals |

### 26.1. Do not put all of CI and CD under one permission set

PR jobs do not need production deploy permissions. Release jobs have dedicated trust/policies and principals. Avoid reusable workflows that accept arbitrary scripts from untrusted callers and run them with privileged tokens.

### 26.2. Pin actions, tasks, and tool versions

Use approved action versions, and preferably pin immutable commit digests per supply-chain policy. Maintain a review process for updates rather than tracking uncontrolled action branches.

### 26.3. Self-hosted runners carry distinct risks

Runners shared between untrusted PRs and production deployments risk token theft and persistent compromise. Use isolated ephemeral runners or managed trusted environments, patch regularly, and never keep long-lived secrets on disk.
## 27. Sample CI workflow for Java Maven

GitHub Actions can validate PRs and commits on `main`:

~~~yaml
name: verify-orders

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-dependency-path: services/orders-api/pom.xml
      - name: Verify Java code
        working-directory: services/orders-api
        run: mvn -B -ntp verify
~~~

### 27.1. PR jobs only need `contents: read`

PR verification does not need an OIDC token, ACR push, or Azure resource deployment. This reduces risk when running code from untrusted contributors.

### 27.2. Quality gates to add

The example only runs `mvn verify`. Real CI requires static security analysis, dependency/secret scanning, license checks, contract/integration tests, and IaC security checks as appropriate, with required checks protecting `main`.

### 27.3. Pin dependencies and actions

Major versions like `checkout@v4` are illustrative. Stricter policies may require pinning immutable commit SHAs and reviewing updates. Maven plugin and dependency versions must also be managed rather than relying blindly on caches.

## 28. OCI images and publishing workflow via ACR

Illustrative Dockerfile for a Spring Boot service:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /app
COPY pom.xml ./
COPY src ./src
RUN mvn -B -ntp verify

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Before production:** pin the base image digest, scan OS packages, use a deterministic JAR path instead of a wildcard if multiple artifacts exist, never `COPY` secrets, verify file ownership and non-root runtime, and observe JVM memory/probes.

Sample workflow to build and push from protected `main` once OIDC identity/ACR permissions are configured:

~~~yaml
name: publish-orders

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: build
    steps:
      - uses: actions/checkout@v4

      - name: Azure login via OIDC
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Login to ACR
        run: az acr login --name "${{ vars.ACR_NAME }}"

      - name: Build and push image
        id: image
        uses: docker/build-push-action@v6
        with:
          context: services/orders-api
          push: true
          tags: ${{ vars.ACR_LOGIN_SERVER }}/orders-api:${{ github.sha }}

      - name: Record digest
        run: echo "Image digest: ${{ steps.image.outputs.digest }}" >> "$GITHUB_STEP_SUMMARY"
~~~

### 28.1. What the workflow assumes

- Protected `main` and the `build` environment have governance configured.
- The Entra federated identity credential trusts the exact repository/ref/environment.
- The principal holds ACR push permissions under the current permission model.
- Registry, networking, and runner are already configured.
- The Docker build context is valid and tests/security checks are enforced as required gates.

### 28.2. Tags do not replace digests

Commit-based tags aid lookup, but release manifests should record the actual OCI digest to verify exact image contents. Tags can move unless locked by policy.

### 28.3. The sample lacks full supply-chain gates for prod

You must add SBOMs, signatures/provenance, vulnerability/secret scanning, and release metadata verification per policy. Do not treat a successful push workflow as proof that an image is trustworthy.

## 29. Staging-only CD example by digest

~~~yaml
name: deploy-orders-staging

on:
  workflow_dispatch:
    inputs:
      image_digest:
        description: 'Approved OCI digest sha256:...'
        required: true
        type: string

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Update Container App image
        shell: bash
        env:
          RG: ${{ vars.RESOURCE_GROUP }}
          APP: ${{ vars.CONTAINER_APP }}
          REGISTRY: ${{ vars.ACR_LOGIN_SERVER }}
          DIGEST: ${{ inputs.image_digest }}
        run: |
          set -euo pipefail
          [[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 2
          az containerapp update \
            --resource-group "$RG" \
            --name "$APP" \
            --image "$REGISTRY/orders-api@$DIGEST"
~~~

### 29.1. Regex only checks digest format

The sample validates the `sha256` string format, **not provenance, signatures, CI origin, or a release allowlist**. Production workflows must pull digests from a verified release manifest and enforce trust verification gates.

### 29.2. Registry and runtime identities

The Container App needs a valid way to pull images via registry configuration/managed identity and appropriate roles. The deployment pipeline should only have permission to update the target app/resource group.

### 29.3. Production uses separate identities and approvals

Do not simply swap the `staging` environment for `production` and let any contributor trigger it. Production requires protected release refs, reviewed digests, approvers, narrowly scoped OIDC trust, and post-deployment SLO checks.

### 29.4. Deploy CLI success does not mean the release is healthy

Verify app revision readiness, probes, ingress, database connectivity, logs/traces, and synthetic business tests after the update command.

## 30. OIDC / workload identity federation

~~~mermaid
sequenceDiagram
    participant CI as CI runner
    participant ISS as OIDC issuer
    participant ID as Microsoft Entra ID
    participant AZ as Azure Resource Manager
    CI->>ISS: Request identity token
    ISS-->>CI: Signed short-lived token
    CI->>ID: Exchange for Azure access token
    Note over ID: Verify issuer, subject, audience, federation
    ID-->>CI: Azure token
    CI->>AZ: Deploy at authorized scope
    AZ-->>CI: Result
~~~

### 30.1. Must be configured consistently

1. Principal exists in the correct Entra tenant.
2. Federated credential issuer/subject/audience match.
3. Pipeline has `id-token` permission.
4. Azure role is assigned at the exact RG/resource scope.
5. Protected ref/environment checks are enabled.
6. Azure login, runner, and DNS/network can communicate.

### 30.2. CI identity differs from runtime identity

The CI token updates Azure resources; the application uses a separate managed identity to call SQL, Storage, Key Vault, and Service Bus. Never embed CI tokens inside images or app config.

### 30.3. When OIDC login fails

Check the tenant, subject, environment name, audience, RBAC, and principal/client ID. Never store a production client secret in Git as a quick fix.

## 31. Azure Pipelines and GitHub Actions share the same principles

With Azure DevOps, you can use **service connections** backed by workload identity federation, protected Environments/approvals/checks, pipeline artifacts, and reusable YAML templates.

| Capability | GitHub Actions | Azure Pipelines |
|---|---|---|
| PR validation | Workflow + branch rules | PR validation/policies |
| Azure auth | OIDC/federated identity | Federated service connection |
| Protected deployments | Environments/reviewers | Environments/approvals/checks |
| Artifacts | OCI registry/build artifacts | Pipeline artifacts/ACR |
| IaC | Azure CLI/Bicep/Terraform tasks | Azure CLI/Bicep/Terraform tasks |
| Audit | Workflow/deployment records | Runs/approvals/service connection logs |

### 31.1. Do not grant Owner just to deploy

The deployment identity should have least privilege on the exact Azure resource/RG. Permissions to assign roles or modify policies belong to a dedicated deployment pipeline with approvals.

### 31.2. Build artifacts remain unchanged across stages

The prod stage consumes the metadata/digest created by CI and verified in staging; do not run a separate Maven rebuild before prod and lose control over dependencies.

### 31.3. Self-hosted runner/agent isolation

Do not run untrusted PRs and production deployment tokens on the same long-lived host sharing workspace, cache, or container socket. Use isolated/ephemeral runners and enforce secret hygiene.

## 32. SBOM: knowing what components an artifact contains

A **Software Bill of Materials (SBOM)** lists the dependencies, versions, licenses, and components of a release in formats such as **CycloneDX** or **SPDX**.

### 32.1. Example components

- Java Maven direct and transitive dependencies.
- OS packages in the container base image.
- Third-party binaries/tools inside the image.
- Metadata on build tools, artifact digest, and licenses.

### 32.2. Value during a CVE

When a library vulnerability is disclosed, teams can locate affected artifacts/digests, their owners, and the deployment environments running them.

### 32.3. An SBOM does not guarantee security

It can be incomplete or inaccurate. Continuous source integrity, dependency/SCA scanning, policy enforcement, updates, and vulnerability management are still needed.

### 32.4. Bind SBOMs to immutable digests

Do not leave an SBOM describing a `latest` tag whose image has changed. Apply access control to internal SBOMs if they expose sensitive dependency lists.

## 33. Provenance, signatures, and deployment trust

**Build provenance** records source revision, builder/workflow identity, build inputs, and metadata associated with an artifact. Combine this with signing/attestations suited to your toolchain.

~~~text
Protected source ref
   -> Reviewed code + dependency policies
   -> Trusted builder
   -> Tests / scans
   -> Immutable digest
   -> SBOM + provenance + signature
   -> Controlled OCI registry
   -> Verification gate at deployment
   -> Runtime audit + monitoring
~~~

### 33.1. Signing requires verification

A tool such as cosign/Sigstore can help sign and verify OCI artifacts under a trust policy. However, signing an image without verifying the signature/provenance in CD provides no actual deployment gate.

### 33.2. A trust chain has many links

Source protection, token scoping, runner isolation, dependency pinning, registry permissions, and artifact verification all matter. A signature alone does not replace tests or security reviews.

### 33.3. Do not mistake build provenance for application correctness

Provenance answers "where did the artifact come from," not "is the logic bug-free" or "is the database migration safe." Testing and production monitoring remain mandatory.
## 34. Dependency security, SAST/SCA, and license policy

A green Java/container build can still contain vulnerable libraries, outdated transitive dependencies, or malicious code in the build chain. Pipelines should include:

1. **Static Application Security Testing (SAST)** for code.
2. **Software Composition Analysis (SCA)** for dependencies and CVEs.
3. **Container image scanning** for OS packages/layers.
4. **Secret scanning** across source, history, and IaC per policy.
5. **License compliance** for dependency distribution.
6. **IaC scanning** for public exposure, wildcard permissions, encryption, and networking.
7. **Artifact provenance** and signed verification.
8. **Dependency updates** and rebuilds from patched base images.
9. **Finding triage** by severity, exposure, and exploitability.
10. **Exception approvals** with owner, rationale, and expiration.

### 34.1. Do not use CVSS as the sole criterion

A critical finding is evaluated alongside reachability, exploit availability, internet exposure, and compensating controls. Nevertheless, do not disable security gates merely to keep pipelines "green."

### 34.2. Pinning and reproducibility

Use version pinning for Java/Maven plugins, base image digests, and workflow actions per security policy. Floating version tags mean rebuilding the same commit can produce a different artifact.

### 34.3. Post-release vulnerabilities

SBOMs/provenance identify artifacts containing affected dependencies. Maintain a workflow to rebuild, retest, and promote patches rather than scanning only once at PR time.

### 34.4. Do not let scanners read production secrets

Security scanners are software running in the pipeline too. Govern their tokens, filesystem scope, network access, and report destinations as part of supply-chain risk management.

## 35. Secrets scanning and runner hardening

### 35.1. Secrets can leak outside Git

Build logs, environment dumps, Docker build args, crash reports, custom SBOM metadata, artifact uploads, and diagnostic archives can all expose tokens. Avoid verbose shell tracing when running commands with credentials.

### 35.2. Untrusted PRs and privileged workflows

PRs from forks must run only under safe permission and secret policies. Never switch a workflow to a privileged event and then check out and execute untrusted PR code.

### 35.3. Reusable workflow input validation

Allow only deployment inputs such as **verified digest, approved environment, release ID**. Never accept arbitrary shell scripts from untrusted callers and run them in a release identity context.

### 35.4. OIDC still requires pipeline protection

Short-lived tokens reduce long-lived secret risk, but a compromised workflow or overly broad federation trust can still request Azure tokens. Protect branches, environments, runners, identities, and permissions together.

## 36. Deployment strategies: rolling, blue/green, canary

| Strategy | How it works | Considerations |
|---|---|---|
| **Rolling update** | Replaces replicas gradually | Readiness, schema compatibility, disruption budget |
| **Blue/green** | Two versions coexist, traffic switches | Temporary extra capacity, data migrations |
| **Canary** | Sends a small share of traffic to the new version | Metrics, routing, stop conditions |
| **Feature flags** | Deploy first, enable later | Flag governance, rollout and rollback state |
| **Manual cutover** | Switches upon approval | Downtime and switch-back plan |

### 36.1. AKS rolling deployments

Requires startup/readiness/liveness probes, resource requests/limits, networking, rollout configuration, and PodDisruptionBudgets where appropriate. Kubernetes reporting rollout success does not prove business APIs are working properly.

### 36.2. Azure Container Apps revisions

Container Apps supports revisions and traffic management depending on mode/capabilities, fitting certain canary patterns. Verify actual ingress, revision mode, and traffic weights rather than assuming identical behavior to App Service slots.

### 36.3. Azure App Service deployment slots

Slots can provide staging/prod swaps depending on App Service plan/support, but slot-sticky settings, managed identities, warmup, and network/database config must be evaluated. Swapping is not guaranteed zero-risk.

### 36.4. Keep application state outside replicas

Rolling/canary updates are safer when in-memory state is not the sole store of business data. Payment workflows require durable state and idempotency to avoid duplicates when requests or retries span revisions.

## 37. Feature flags and configuration rollout

Feature flags reduce the need for long-lived branches and can decouple deployment timing from feature activation timing.

### 37.1. Flag categories

- **Release flags:** expose new features to targeted user groups.
- **Operational flags:** disable failing integrations or switch to fallbacks.
- **Experiment flags:** A/B testing with proper statistical rigor.
- **Permission flags:** only supplement UI/config; **never replace backend authorization**.

### 37.2. Flags must be managed like code

Define an owner, purpose, removal date/TTL, default value, target environments, and tests for both on and off states. Flags left alive for years turn code into an unmaintainable matrix of conditions.

### 37.3. Azure App Configuration

When appropriate, Azure App Configuration can store non-secret config/feature flags using managed identity for access. Check label/refresh semantics, data-plane roles, and supported SDK/runtime integrations.

### 37.4. Rolling back a flag does not undo side effects

If a feature has already transferred funds or written data, turning off the flag stops new operations but does not automatically compensate past transactions.

## 38. Database schema compatibility before and after deployment

A sound pipeline accounts for old and new application versions running concurrently during rollout.

### 38.1. Expand–migrate–contract

1. **Expand:** add new tables/columns/fields in a compatible way.
2. **Migrate:** backfill or dual-read/write under a verified plan.
3. **Contract:** remove old fields once all consumers have migrated and the rollback window has passed.

### 38.2. Dedicated database migration job

Avoid running destructive migrations on startup across 20 Pods. Use a separate job with ownership/locking/idempotency, minimal database permissions, and backups as required.

### 38.3. Code rollback does not automatically roll back schema

If the new release writes `schemaVersion 2`, the old version may fail to parse it. Plan for forward-fix or a compatibility window; blind image rollback can worsen failures.

### 38.4. Event schema evolution

Different versions of `payment-worker` may process messages produced by different versions of `orders-api`. Use schema compatibility tests, versioned events, idempotent consumers, and policy-driven DLQs.

## 39. Post-deploy observability: what defines success?

Record a **release marker** containing:

~~~text
environment = production
service = orders-api
sourceCommit = <git-sha>
imageDigest = sha256:<digest>
releaseId = <release-id>
deployedAtUtc = <UTC timestamp>
approvedBy = <workflow/approver record>
~~~

Never log tokens or secrets in the release marker.

### 39.1. Signals to monitor

| Signal | Purpose |
|---|---|
| Successful requests/s | Demand and throughput |
| Error rate/5xx | Post-deploy quality |
| p95/p99 latency | Long-tail failures |
| Pod/revision readiness | Runtime rollout status |
| Database 429/deadlocks/timeouts | Data layer saturation |
| Queue backlog/age/DLQ | Slow or failing workers |
| JVM heap/GC/CPU | Resource pressure |
| Dependency errors | Azure SQL, Storage, Service Bus |
| Cost per operation | Budget impact |
| Correlation/traces | Cross-service root cause analysis |

### 39.2. Azure Monitor and Application Insights

Use metrics, logs, traces, workbooks, and alerts tailored to the Azure runtime. `CorrelationId`/`traceId` links API requests across SQL, Storage, and Service Bus operations. Avoid high-cardinality tags containing user IDs or PII.

### 39.3. Alerting is not just for production

Staging needs signals to detect failed smoke or performance tests. Production requires monitors independent of the deployment tool to catch failures even after the pipeline finishes.

### 39.4. Set SLOs and rollback thresholds before release

Do not arbitrarily pick "p99 under 100 ms" when production workloads legitimately require 500 ms. Base thresholds on baselines, user impact, error budgets, and business-critical transactions.

## 40. Verification, rollback, and forward-fix

Production release workflow:

1. Verify CI artifact digest, SBOM/provenance, and approval.
2. Verify target subscription, resource, and app.
3. Deploy canary or rolling update per policy.
4. Check runtime readiness and smoke tests.
5. Compare error rate and p95/p99 against baseline.
6. If healthy, shift traffic incrementally.
7. If failing, halt/rollback image or disable feature flag per runbook.
8. Record results and reconcile the release manifest.

### 40.1. Previous known-good digest

Record the previous digest **before** release; rollbacks must specify a compatible digest/manifest explicitly rather than using a mutable `latest` tag.

### 40.2. Rolling back IaC can be dangerous

A `git revert` does not restore deleted or lost data; network, policy, or SQL changes may require a different recovery plan. Destructive IaC changes require backups and approval.

### 40.3. When forward-fix is better

If the database has migrated to a new schema incompatible with the previous version, deploy a hotfix compatible with the DB migration rather than restoring the old image and hoping it works.

### 40.4. DR differs from deployment rollback

Regional outages, replication, and failover differ from faulty release rollouts. DR documentation must address RPO/RTO, data consistency, region restrictions, secrets, and DNS/cutover.

## 41. Azure Cost Management across environments

Costs can arise from:

- Compute: App Service, Container Apps, AKS/node pools, Functions.
- ACR image storage and network transfer.
- Azure SQL/Cosmos DB storage and throughput.
- Azure Storage operations, capacity, snapshots/backups.
- Application Insights/Log Analytics ingestion and retention.
- Private Link, firewalls/NAT, and egress.
- CI runners/agents and test resources.
- Leftover ephemeral PR environments.
- Multi-region replication/DR.

### 41.1. Budgets by environment and owner

Tags, subscriptions, and RG boundaries support chargeback, though cost allocation scopes must be verified. Set separate budget alerts and forecasts for nonprod and prod.

### 41.2. Scaling compute does not automatically improve throughput

HPA adding Pods while database RU/s remain fixed can trigger 429s and retries. Size total system capacity, not just compute.

### 41.3. Production and staging can differ in scale

Preserve critical topology and security constraints, but staging does not need identical capacity when not running full-scale performance tests. Document the differences.

### 41.4. Preview cleanup is a CI/CD feature

PR-created environments must have TTLs, ownership, resource tags, and guardrailed cleanup jobs to prevent accumulating billable resources for weeks.

## 42. Policy-as-code and change control

An organization can use Azure Policy, IaC security tools, branch rules, and deployment gates to enforce:

- Allowed regions/SKUs.
- Required tags/ownership.
- No public access for sensitive data.
- Encryption/TLS minimums.
- Identity/RBAC boundaries.
- Protected environments and reviewers.
- Artifact integrity/provenance.
- Budget/retention policies.
- Backup, disaster recovery, and monitoring baselines.

### 42.1. Multiple policies form layered controls

Azure Policy rules validate resources; pipeline rules validate code/artifacts; Spring Security enforces user actions; network security guards data paths. No single tool replaces the others.

### 42.2. Time-bound exceptions

If a service needs a legitimate policy exemption, document the owner, rationale, expiration date, scope, and compensating controls. Never disable policy across an entire subscription just because one small test failed to deploy.

### 42.3. Break-glass access

Emergency permissions must be governed, monitored, and audited; never use break-glass accounts as routine pipeline credentials.

## 43. Runbook: wrong environment or wrong artifact released

**Scenario:** a new staging artifact was accidentally deployed to production without approval.

### Step 1 — Contain impact

Halt the promotion pipeline and determine blast radius and customer impact. Do not blindly trigger another deploy before understanding the current state.

### Step 2 — Gather evidence

Collect the pipeline run ID, Git commit, artifact digest, resource group/subscription ID, timestamp, principal, and change ticket.

### Step 3 — Assess state and side effects

Have any schema migrations, payment/business events, or data mutations occurred? Is an image rollback safe?

### Step 4 — Recover

If compatible, deploy the previous known-good digest or shift traffic back to the prior revision/slot. If data/schema is incompatible, execute an approved forward-fix or compensation plan.

### Step 5 — Verify

Check smoke tests, readiness, error rates, queues, database metrics, and traces. Confirm the running artifacts by digest, not just by tag.

### Step 6 — Fix root cause

Review GitHub environment rules/Azure DevOps approvals, OIDC trust subjects, RBAC scopes, workflow triggers, and principal permissions. Add hard gates to prevent recurrence.

### Step 7 — Post-incident

Archive the incident report, timeline, owner, and action items. Never include secrets or production customer data in public reports.
## 44. Decision matrix for repository and environment organization

Make choices based on risk and team workflow rather than trending tools.

| Question | When the answer is "yes" | Recommended direction |
|---|---|---|
| Do multiple services always change together? | High contract/service coupling | Consider a monorepo and dependency-aware CI |
| Do teams have different release cadences/permissions? | Separate permissions and ownership | Polyrepo/hybrid |
| Are production network/IAM highly sensitive? | Compliance/segregation of duties required | Dedicated platform IaC repo/pipeline |
| Must applications be reproducible from commit? | Audit/rollback requirements exist | Version pinning, digests, provenance |
| Are PR environments needed? | Frequent UI/integration reviews | Ephemeral envs with TTL and bounded cost |
| Does staging differ from prod in identity/network? | Risk of production-only failures | Add preprod parity tests |
| Does DB schema change frequently? | Multiple active consumers | Expand–migrate–contract and contract tests |
| Is fast rollback required? | High SLO and change frequency | Immutable artifacts, canary, previous digest |
| Are there regional data residency requirements? | Specific data residency rules | Region/subscription/workspace boundaries |
| Are nonprod costs growing uncontrollably? | Many leftover preview/test resources | Tags/budgets/cleanup automation |

### 44.1. Architecture Decision Record (ADR)

A short ADR should capture **context, options, decision, rationale, security/privacy impacts, cost, rollback/migration plan, and owner**. For example, choosing a monorepo for 3 services owned by one team while separating the platform subscription repo due to distinct administrative permissions.

### 44.2. Do not choose what cannot be operated

A multi-layer signing/permission pipeline that nobody knows how to troubleshoot when it fails can stall releases. Factor operability, runbooks, and training into architectural decisions.

## 45. Lab 1: design a repository structure for an Azure system

**Objective:** translate business requirements into module/ownership boundaries and source layout.

### A. Hypothetical scenario

Includes `orders-api`, `payment-worker`, frontend, shared event schemas, ACR, Key Vault, Azure SQL, Service Bus, Application Insights, and network policies.

### B. Design

1. Choose monorepo, polyrepo, or hybrid and justify the choice.
2. Draw the source tree covering services, libraries, infra, deploy, docs, and CI.
3. Define `CODEOWNERS` for services, platform IaC, and security.
4. List build dependencies between modules.
5. Define shared contract versioning and test scope when a contract changes.
6. Describe the principle of configuration without forking code.

### C. Anti-pattern check

- Are there secrets in `application-prod.yml`?
- Are Docker images or JAR binaries committed to Git?
- Does CI rerun all dependent tests when a shared contract changes?
- Do developers have permission to modify production platform policies?
- Does the repo include deployment/rollback runbooks and ADRs?

### D. Deliverable

A directory tree as in Section 7, an ownership table, PR/branch rules, and a concise ADR outlining trade-offs. **This is a design lab; no real subscription needs to be created.**

## 46. Lab 2: provision Azure environments with IaC

**Practice only on an authorized Azure lab subscription and resource group; never use a production subscription.**

### A. Define targets

- Dev has a small Storage account or Container Apps environment.
- Staging has its own identity, network rules, and logs.
- Prod is described only via parameters and policies; no real deployment is needed in the lab.
- All resources include tags and an owner.

### B. Bicep or Terraform

1. Choose an authorized IaC engine.
2. Create minimal storage/network/identity modules per service support.
3. Create dev/staging parameter sets.
4. Declare region, tags, unique resource names, and SKU.
5. Do not embed storage account keys or database secrets.
6. Add validate/what-if or plan review.
7. Run against the confirmed target subscription/RG.
8. Read back properties/identity from Azure.
9. Record plan/apply evidence and smoke check results.
10. Clean up **only the lab's own resources** after review.

### C. Sample Azure CLI scope check

~~~bash
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" -o table

az group list \
  --query "[].{name:name,location:location}" -o table
~~~

This is an illustrative **read-only inspection**. Before running any create/delete command, verify the exact account and RG. Do not include a generic destroy command in the lab without proving isolated lab scope.

### D. Completion criteria

A module can be redeployed idempotently; dev/staging environments have sensible differing parameters; there is no policy-violating public data exposure; plan/readback results match; no orphaned resources remain.

## 47. Lab 3: PR validation, OCI image, and supply-chain metadata

### A. Preparation

1. Select a test repo containing a Java 17/Spring Boot app and Dockerfile.
2. Enable protected branches/PRs according to granted permissions.
3. Run Maven verify automatically.
4. Add SAST/SCA/secret scans per toolchain.
5. Verify that a PR with failing tests is blocked from merging.
6. Verify that a PR from a fork does not receive production deployment tokens.

### B. Build and ACR

1. Configure Entra OIDC trust for the **build** environment matching repo/ref.
2. Grant scoped registry push permissions, not subscription Owner.
3. Build the image from protected `main`.
4. Push a tag matching the commit SHA.
5. Record the OCI digest returned by the registry/build action.
6. Generate SBOM and provenance using approved tools.
7. Scan the image/dependencies and document findings.
8. If signing policy applies, generate and verify the signature/attestation.
9. Ensure no secrets exist in Docker layers.

### C. Evidence table

| Attribute | Verification source |
|---|---|
| Git commit | CI run |
| Builder workflow/run ID | CI system |
| Artifact registry/path | ACR |
| Image digest | OCI manifest |
| SBOM ID/format | Artifact metadata |
| Provenance/signature | Approved verifier |
| SAST/SCA/container scan | Security reports |
| Reviewer/approval | PR/change record |

### D. Criteria

From a digest, one can trace back to the commit/build, inspect test/scan outcomes, and determine whether the image remains trusted under policy.

## 48. Lab 4: promote the same digest through staging

### A. Preparation steps

1. Have a CI-approved image digest.
2. Have a dedicated Container App/AKS test resource.
3. Runtime identity has ACR pull permission.
4. Staging environment has an Entra federated deployment identity.
5. Have non-secret staging config and separate Key Vault references.
6. Have readiness/smoke checks and monitoring ready.

### B. Deployment practice

1. Retrieve the digest from the release manifest—**do not rebuild**.
2. Verify provenance/signature per lab capabilities.
3. Execute staging deployment against the exact target scope.
4. Read back the actual running image digest from the Container App revision/AKS workload.
5. Verify HTTPS/ingress/TLS.
6. Verify Storage/SQL/Service Bus connectivity with synthetic data.
7. Measure p95, error rate, and correlation logs.
8. Record release ID, commit, digest, and approval.
9. Test redeploying the same digest to confirm idempotency.

### C. Failure scenarios

- Azure login 401/403: check federation subject, principal, and RBAC.
- ACR pull failure: check registry identity and networking.
- Revision not ready: check startup/probes/config and logs.
- SQL/Storage timeout: check private DNS, routing, and data-plane roles.
- Wrong digest: block deploy; do not accept a similar-looking tag.

### D. Do not deploy to real prod

The lab only requires proposing a **production promotion design** with protected environments, approvers, verified image provenance, and rollout gates. Do not grant learners production access.

## 49. Lab 5: canary, rollback, and incident simulation

### A. Simulate a bad release

In the staging lab, create a version with a synthetic bug that raises HTTP 500s or request latency within safe bounds, without calling production APIs.

### B. Run canary

1. Route a small portion of test traffic to the new revision if supported by the platform.
2. Monitor error rate, latency, logs, and request correlation.
3. Compare against the previous baseline version.
4. Define rollout stop thresholds before testing.
5. On failure, halt traffic shifting and revert to the healthy revision/digest.

### C. Rollback must not create duplicates

1. Send synthetic order requests with an idempotency key.
2. Trigger a timed-out request and retry across old/new versions.
3. Ensure no duplicate payments/orders are created.
4. Verify the database schema remains compatible with the rolled-back image.
5. If incompatible, write a forward-fix proposal.

### D. Post-release verification

| Signal | Before | After | Conclusion |
|---|---|---|---|
| Error rate | Baseline | Measured | Pass/fail |
| p95/p99 latency | Baseline | Measured | Pass/fail |
| Revision readiness | Stable | Measured | Pass/fail |
| Payment smoke outcome | Pass | Measured | Pass/fail |
| Queue backlog | Baseline | Measured | Pass/fail |
| DB retries | Baseline | Measured | Pass/fail |
| Running digest | Good digest | Measured | Rolled back correctly? |

### E. Criteria

Learners must demonstrate the deployment audit trail, rollback decision, artifact identity, and proof that data was not corrupted across version transitions.

## 50. Production readiness checklist before opening deploy permissions

- [ ] Repository topology has an ADR and clear ownership.
- [ ] Code is not duplicated across dev/staging/prod.
- [ ] Branch protection and CODEOWNERS are enabled per policy.
- [ ] PR verification holds no production credentials.
- [ ] Formatting, compile, and unit/integration/contract tests exist.
- [ ] SAST, SCA, and dependency/secret/license/IaC security checks exist.
- [ ] Build toolchain, dependencies, and actions are pinned and reviewed.
- [ ] Docker build embeds no secrets and runs non-root where appropriate.
- [ ] Artifacts are stored in a registry and referenced by immutable digest.
- [ ] SBOM/provenance/signatures are attached to digests as required.
- [ ] Deployment checks trust and policy, not merely digest regex.
- [ ] Dev/test/staging/prod have clear verification objectives.
- [ ] Resource groups/subscriptions and scopes are defined.
- [ ] Raw production data is never copied into nonprod.
- [ ] Environment identities are distinct and follow least privilege.
- [ ] OIDC trust subject/audience/issuer are strictly configured.
- [ ] Runtime managed identity is separated from CI deployment identity.
- [ ] Key Vault secrets never appear in Git, images, or logs.
- [ ] Networking/private DNS/TLS are tested from the real runtime.
- [ ] Azure Policy/tags/regions/cost budgets align with governance.
- [ ] Bicep/Terraform state/parameters have owners and change approval.
- [ ] IaC plan/what-if, security, and destructive changes are reviewed.
- [ ] Two IaC tools do not manage the same unowned resource.
- [ ] CI pushes artifacts only after required tests and scans pass.
- [ ] CD promotes the same digest without rebuilding per environment.
- [ ] Staging smoke/performance/security pass before production.
- [ ] Production has protected approvals and a dedicated identity.
- [ ] Canary/rolling/blue-green strategy is chosen to match runtime.
- [ ] Readiness/liveness probes and application metrics are accurate.
- [ ] Release markers record commit, digest, runtime, and approval.
- [ ] Previous known-good digest and rollback runbook are ready.
- [ ] DB migrations are compatible, idempotent, and backed by a backup plan.
- [ ] Feature flags have an owner, default, and expiration.
- [ ] App/DB/queue/network quotas are sized consistently.
- [ ] Monitoring/alerting covers p95/p99, errors, backlogs, and logs.
- [ ] SLO/error-budget stop conditions exist for rollouts.
- [ ] Cost Management is tracked by environment and service owner.
- [ ] Preview environments have TTL/auto-cleanup/guardrails.
- [ ] Runbooks exist for deploying to the wrong resource, artifact, or identity.
- [ ] Break-glass changes are audited and backported into IaC.
- [ ] Post-deployment verification and change records exist.
- [ ] Recovery/DR is tested against required RPO/RTO targets.

## 51. Self-check questions

1. How do source code, artifacts, and environments differ?
2. Why should you not keep three copies of Java code for dev/test/prod?
3. Does deploying automatically mean releasing to users?
4. What advantage does a monorepo have when changing a shared API contract?
5. When should you use a polyrepo or hybrid approach?
6. Does CODEOWNERS replace CI tests?
7. Why must PRs from forks never use production identities?
8. Does a branch named `prod` guarantee authorization?
9. How do Azure management groups, subscriptions, and resource groups differ?
10. Does a resource group automatically create network isolation?
11. Why can a dedicated production subscription reduce blast radius?
12. In what critical aspects must staging match production?
13. Should raw production customer data be copied into staging?
14. Why must ephemeral PR environments have a TTL?
15. Do resource tags replace RBAC or Azure Policy?
16. What types of configuration are safe to store in Git?
17. Why must database keys not be embedded into a Docker image?
18. How does a deployment identity differ from a runtime managed identity?
19. Does Key Vault replace Spring Security or business authorization?
20. What risks does OIDC reduce compared to long-lived client secrets?
21. When OIDC login fails, what should you inspect first?
22. Where do DCR/monitoring and IaC belong in the source layout?
23. Why are Bicep/Terraform modules and parameter files needed?
24. Can Terraform state contain secrets?
25. How do you detect drift caused by manual Azure Portal edits?
26. Does what-if guarantee a completely safe apply?
27. What evidence should CI produce beyond compilation results?
28. How does build once / promote same digest differ from rebuild-on-prod?
29. Why is an image tag insufficient to identify an artifact?
30. How do ACR push permissions differ from runtime pull permissions?
31. What is an SBOM and how does it help locate CVEs?
32. Do provenance and signatures replace security testing?
33. Why must deployment verify signing/provenance when policy requires it?
34. How does a GitHub environment approval differ from code review?
35. When are rolling, blue/green, or canary strategies appropriate?
36. Why does green readiness not prove business flows are correct?
37. Do feature flags automatically roll back data or transactions?
38. How does DB expand–migrate–contract help when two app versions coexist?
39. Why does rolling back an image not roll back the database schema?
40. Which metrics should be monitored immediately after a release?
41. Does scaling Azure compute automatically scale SQL/Cosmos capacity?
42. How are preview environment costs controlled?
43. If deployed to the wrong subscription, what is the first action?
44. How should a break-glass Portal change be handled afterward?
45. When is a forward-fix needed instead of a rollback?
46. How do RPO and RTO relate to deployment rollback?
47. How do you verify the running image matches the approved digest?
48. Why must promotion have an audit trail and release manifest?
49. Why can a "green" pipeline still cause a production incident?
50. What are the three most important decisions when designing Azure environments?

## 52. Summary

**Organizing source code and Azure deployment environments** requires an end-to-end design from repository to runtime. Source layouts must reflect **service ownership, testability, and module boundaries**; dev/test/staging/prod environments must differ by **verification purpose, data, identity, policy, networking, cost, and deployment permissions**, not merely folder names or Git branches.

A reliable pipeline builds artifacts from reviewed commits, runs **tests and security gates**, records **SBOM, provenance, and immutable digests**, and **promotes that exact artifact** through protected environments. Bicep/Terraform manage infrastructure via IaC; Microsoft Entra/OIDC and managed identities eliminate many long-lived credentials; Azure Policy, Key Vault, network controls, and separated environments limit the blast radius.

A production release does not end when the CLI returns success. It requires **readiness, smoke tests, telemetry, SLOs, approvals, previous known-good digests, database compatibility, and rollback/forward-fix runbooks**. With Azure Monitor, Cost Management, and subscription/resource group governance, development teams can ship software frequently while preserving traceability, security, resilience, and cost control.
