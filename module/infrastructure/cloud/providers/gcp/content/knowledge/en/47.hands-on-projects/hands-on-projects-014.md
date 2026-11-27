# Capstone Project: From Architecture Design to Operational Handover

A Google Cloud project does not end the moment an application returns HTTP 200. A system is truly production-ready only when it has **approved requirements, architecture backed by documented rationale, code-controlled resources, protected data, verified tests, release and rollback workflows, monitoring, runbooks, and an accountable operations handover owner**.

This capstone belongs to the **GCP Hands-On Projects** chapter of the **CLOUD_PROVIDERS_GCP** module. The module builds skills from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases; through deployment scenarios, learners practice selecting services, protecting resources, automating releases, and tracking reliability and cost. This lesson pulls those skills into a capstone evaluated by concrete outputs, not merely a checklist of enabled services.

**Problem Statement:** Design, test-deploy, operationalize, and hand over a multi-tier order management application named **ShopFlow Orders**. The goal is to keep the order flow secure and reliable on Google Cloud with data recovery capability, cost visibility, and clear incident procedures.

**Safety Convention:** All project IDs, accounts, IPs, database names, load numbers, and budgets in this lesson are illustrative examples. Run `gcloud`/Terraform commands only in an authorized sandbox or staging project, because many commands provision billable resources. Never deploy, delete, or cut over production without change approval.

After completing this lesson, you will be able to:

- Translate business needs into SLOs, RTO/RPO, acceptance criteria, and a requirements traceability matrix.
- Design a three-tier Google Cloud architecture with networking, identity, data flows, and trust boundaries.
- Select among Cloud Run, Cloud SQL, Cloud Storage, Pub/Sub, Artifact Registry, Cloud Build, and Secret Manager based on explicit trade-offs.
- Organize projects, IAM, VPCs, IaC/Terraform, and staging/production environments.
- Build workflows for testing, building, scanning, deploying, releasing, canarying, and rolling back.
- Operate with Cloud Monitoring/Logging, alerting, backups, PITR, DR, and FinOps.
- Prepare an operational handover pack, executable runbooks, RACI matrix, and Go/No-Go gates.

## 1. Mandatory Capstone Deliverables

Do not grade a project solely from Console screenshots. A completing team must produce the following evidence pack:

| ID | Deliverable | Acceptance Criterion |
|---|---|---|
| D01 | Project charter and scope | Includes business owner, current system, boundaries, and assumptions |
| D02 | Functional/non-functional requirements | Includes IDs, priorities, quantitative targets, and owners |
| D03 | Architecture Decision Records (ADRs) | Evaluates at least two options and explains why each was chosen or rejected |
| D04 | Architecture, data flow, and trust boundary diagrams | Shows ingress/egress, services, data stores, and identities |
| D05 | Landing zone and resource register | Project, region, VPC/CIDR, IAM, labels, APIs, owner |
| D06 | Infrastructure as Code | Terraform plans, state/backend, reviews, and drift policy |
| D07 | Code, images, and CI/CD | Test results, image digests, scans, and provenance if applicable |
| D08 | Data protection and security plan | Secrets, backups, PITR, permissions, and threat model |
| D09 | Test evidence | Unit/integration/load/security/DR tests, defects, and mitigations |
| D10 | Release/cutover and rollback plan | Go/No-Go criteria, traffic shifts, data safety, and approvals |
| D11 | SLO dashboard, alerts, and cost report | Baselines, thresholds, notifications, and budgets |
| D12 | Operational handover pack | Runbooks, on-call, RACI, inventory, sign-off |

**D01–D12 are deliverable names for this exercise**, not pre-generated files. Learners can store them in an organization-approved doc store, repository, or issue tracker. Every deliverable should carry a version, approver, and link to a commit/release.

### Control Gates

~~~mermaid
flowchart LR
    A["G0: Scope/BIA"] --> B["G1: ADR + design review"]
    B --> C["G2: IaC + security readiness"]
    C --> D["G3: Staging tests"]
    D --> E["G4: Production Go/No-Go"]
    E --> F["G5: Hypercare + handover"]
~~~

Never skip G3/G4 merely because a CI build passed. Production readiness rests on **integration evidence and operational capability**, not compilation status alone.

## 2. Business Context and Scope

ShopFlow has three user groups:

- Buyers who place orders and check order status.
- Operations staff who handle failed orders.
- Finance staff who export invoices and reconcile records.

Primary business flow:

1. Buyer signs in via the application's identity mechanism.
2. Client sends `POST /api/orders` with an idempotency key.
3. Backend validates input and writes the order inside a PostgreSQL transaction.
4. Backend writes an **outbox event** inside the exact same transaction.
5. A worker relays the outbox event to Pub/Sub; consumers execute post-processing and notifications.
6. A PDF invoice is generated and stored in Cloud Storage, with metadata saved in the database.
7. Buyer sees updated status and staff can trace failures via a trace ID.

### 2.1. In Scope

- Web frontend container on Cloud Run.
- Java/Spring Boot backend on Cloud Run.
- Cloud SQL for PostgreSQL over private networking.
- Secret Manager for database passwords or evaluated IAM database authentication.
- Cloud Storage for invoice objects.
- Pub/Sub for business events and asynchronous processing.
- Artifact Registry, Cloud Build, and image promotion workflow.
- IAM, VPC, Terraform, Monitoring, Logging, and budgets/alerts.
- Staging testing, one controlled release, and operational handover.

### 2.2. Out of Scope

- Collecting raw payment card details directly or achieving PCI DSS certification.
- Multi-region active-active deployment with zero RPO.
- Rewriting the entire application into microservices or executing major schema rewrites during cutover.
- Processing live personal data in a lab environment.
- Guaranteeing that every customer system matches these illustrative SLO numbers.

To contain risk, simulated or third-party payment systems use sandbox endpoints only; never use real cardholder data.

## 3. Turning Requirements into Verifiable Objectives

Suppose the product defines the following requirements (business owners must confirm before applying outside a lab):

| ID | Requirement | Illustrative Target | Measurement |
|---|---|---|---|
| F01 | Create order | POST creates one unique order per idempotency key | Functional/API tests |
| F02 | View order | GET returns only orders the user is authorized to view | Authz integration tests |
| F03 | Emit event | `order.created` publishes/retries without duplicate side effects | Outbox/consumer tests |
| F04 | Store invoice | Object and DB metadata stay accurately linked | E2E storage tests |
| N01 | API latency | P95 under 500 ms under target load | Load tests and traces |
| N02 | Availability | 99.9% SLO over a 30-day window | SLI good/total requests |
| N03 | Data durability | Confirmed orders are never silently lost | Transaction/outbox/recovery tests |
| N04 | RPO | At most 15 minutes under approved scenarios | Recovery point/drills |
| N05 | RTO | At most 2 hours under approved scenarios | Business restore drills |
| N06 | Security | Least privilege, no public DB, no secrets in repos/images | IAM/security reviews |
| N07 | Audit | Trace IDs, release IDs, and audit trails for key changes | Log/trace inspection |
| N08 | Cost | Within approved budget with active alerts | Billing budget reports |

### 3.1. SLOs and Error Budgets

With an Availability SLO of 99.9% over 30 days:

\[
30 \times 24 \times 60 \times (1-0.999)=43.2\ \text{minutes}
\]

43.2 minutes is an **illustrative time-equivalent error budget** for continuous availability measurement; in practice, request-based SLIs use good/valid requests, so failures do not always translate directly into minutes.

Example SLI definition:

~~~text
SLI_availability = good_requests / eligible_requests

good_requests:
  Successful HTTP responses per business contract,
  excluding client-input 4xx errors from server outages

eligible_requests:
  Valid HTTP requests within the agreed product scope
~~~

Clearly agree upfront on how to exclude client errors, synthetic probes, bot traffic, planned maintenance, and timeouts. Never redefine an SLI retroactively after an outage.

### 3.2. RPO and RTO

- **15-minute RPO:** recovered data must be no older than 15 minutes before the incident for in-scope data.
- **2-hour RTO:** order creation/viewing resumes within two hours, covering detection, decision, restore, verification, and traffic cutover.
- RTO/RPO must be measured via restore drills, never inferred from a "backups enabled" flag.

If F01 mandates zero loss of any order already confirmed to a customer, a 15-minute RPO is merely an **infrastructure ceiling**; you must also design business reconciliation/replay to handle transactions lost during restore.

## 4. Architecture Selection and Writing ADRs

Options to evaluate before selecting services:

| Criterion | Compute Engine VM | GKE | Cloud Run |
|---|---|---|---|
| Stateless/containerized app | Supported | Good fit | Strong fit |
| OS/network control | High | Medium/high | Runtime-bounded |
| Autoscaling | Needs MIG or custom design | HPA/cluster | Service-managed |
| Infrastructure ops | High | Medium/high | Lower |
| Stateful/kernel-dependent workloads | Flexible | Constrained | Not first choice |
| CI/CD integration | Yes | Yes | Yes |
| Required skills | VM/OS | Kubernetes/SRE | Containers/serverless/IAM |

**ADR-001:** Choose Cloud Run for the frontend and Orders API because both are stateless, traffic varies hourly, and the team wants lower node management overhead. Cloud SQL handles relational transactions; Cloud Storage holds binary objects; Pub/Sub decouples post-transaction processing.

**Accepted trade-offs:** cold starts, concurrency/timeout limits, egress setup, and database connection pressure under scaling. Do not pick Cloud Run if a workload needs local persistent filesystems, kernel privileges, or unsupported protocols without redesigning.

### 4.1. Short ADR Template

~~~markdown
# ADR-001: Run Orders API on Cloud Run

Status: Accepted (only after design review)
Context:
- Stateless Java Spring Boot storing data in PostgreSQL.
- Needs autoscaling and reduced VM operations.
Decision:
- Cloud Run backend, Cloud SQL PostgreSQL, and Direct VPC egress.
Alternatives:
- Compute Engine MIG: more flexible, higher OS maintenance.
- GKE: appropriate when broader Kubernetes capabilities are needed.
Consequences:
- Must calculate DB connection budgets and cold-start SLOs.
- Must decouple state and background jobs from HTTP requests.
Review date:
- When traffic scale or workload characteristics change.
~~~

An ADR is a **decision record**, not a blanket claim that Cloud Run is always better than GKE.

## 5. Three-Tier Reference Architecture

~~~mermaid
flowchart TD
    USER["Users / browser"]
    EDGE["HTTPS / custom domain<br/>Optional external Application LB"]
    WEB["Cloud Run: shopflow-web<br/>Public presentation + app auth"]
    API["Cloud Run: shopflow-api<br/>IAM-protected backend"]
    VPC["Custom VPC subnet<br/>Direct VPC egress"]
    DB["Cloud SQL PostgreSQL<br/>Private IP + backups/PITR"]
    SEC["Secret Manager"]
    GCS["Cloud Storage: invoices"]
    PUB["Pub/Sub: order-events"]
    WORKER["Worker / Cloud Run<br/>Event consumer"]
    BUILD["Cloud Build + Artifact Registry"]
    OBS["Logging, Monitoring, Tracing"]
    USER --> EDGE --> WEB
    WEB -->|"HTTPS + ID token"| API
    API --> VPC --> DB
    API --> SEC
    API --> GCS
    API -->|"Transactional outbox publisher"| PUB
    PUB --> WORKER
    BUILD --> WEB
    BUILD --> API
    API --> OBS
    WEB --> OBS
    WORKER --> OBS
~~~

A load balancer, Cloud Armor, and Cloud CDN can be added in production when WAF, custom domains, edge caching, and centralized policies are needed. In the lab, you can use the frontend's Cloud Run URL directly to lower cost and complexity.

### 5.1. Data Flows and Trust Boundaries

| Flow | Protocol | Identity / Permission | Control Point |
|---|---|---|---|
| Browser → Web | HTTPS | App-level user identity/session | TLS, CSRF/XSS, session validation |
| Web → API | HTTPS | Web runtime SA + `roles/run.invoker` | Google-signed ID token and app authorization |
| API → Cloud SQL | PostgreSQL via connector | API runtime SA + DB user | `Cloud SQL Client`, VPC route, DB GRANTs |
| API → Cloud Storage | HTTPS API | API runtime SA | Bucket-level object creator/reader |
| API → Secret Manager | HTTPS API | API runtime SA | `secretAccessor` on exact secret/version |
| Outbox publisher → Pub/Sub | HTTPS API | Publisher SA | `pubsub.publisher` on topic |
| Pub/Sub → consumer | Push HTTPS or pull | Subscriber/push identity | Consumer IAM, idempotency, retries |
| Operator → control plane | Google Cloud API | Staff via IAM/WIF/MFA | Audit Logs, change approvals |

Cloud Run **services** use Direct VPC egress to reach VPC resources; they do not inherently expose a VM-style private ingress. The backend uses an HTTPS service URL and enforces IAM invoker. If stricter ingress is desired, engineer a valid service-to-service path rather than flipping to `internal-only` without testing reachability.

### 5.2. Data Placement and Egress Control

- Co-locate Cloud Run, Cloud SQL, buckets, and Artifact Registry in the same region where appropriate to reduce latency and cross-region charges.
- Choose regions per organizational data residency and service availability; the lab's `asia-southeast1` is illustrative, not mandatory.
- Cloud SQL private IP requires VPC connectivity plus access to Google APIs for the Cloud SQL Connector.
- Cloud Storage/Pub/Sub/Secret Manager use Google HTTPS APIs; assess egress and permissions separately.
- Never pass raw customer credentials or service account keys to the browser.
- Configure object expiry/retention/lifecycle rules to avoid runaway storage costs.

## 6. Landing Zone and Environment Isolation

Never share secrets, service accounts, or databases between staging and production.

~~~text
organization / folder per enterprise policy
  platform-shared (if the organization uses a shared network)
  shopflow-staging
    shopflow-vpc, subnet, Cloud SQL staging, buckets, services
  shopflow-production
    production network/Cloud SQL, buckets, services
  security-logging (if a centralized logging project exists)
~~~

In a small setup, each environment is an independent project. In an enterprise, Shared VPCs, folder policies, and billing boundaries follow the standard landing zone.

### 6.1. Resource Naming and Labels

| Type | Staging Example | Labels / Owner |
|---|---|---|
| Project | `shopflow-staging-001` | `env=staging`, `team=commerce` |
| VPC | `shopflow-vpc` | `owner=platform` |
| Subnet | `shopflow-run-subnet` | `region=asia-southeast1` |
| Cloud Run frontend | `shopflow-web` | `app=shopflow`, `tier=web` |
| Cloud Run backend | `shopflow-api` | `app=shopflow`, `tier=api` |
| Cloud SQL | `shopflow-db` | `data_class=confidential` |
| Bucket | `shopflow-invoices-staging-UNIQUE` | `retention=business-approved` |
| Pub/Sub topic | `shopflow-order-events` | `owner=commerce` |
| Artifact Registry | `shopflow-images` | `team=platform` |
| Service accounts | `shopflow-web-sa`, `shopflow-api-sa` | `purpose=runtime` |

Bucket names must be **globally unique**; never assume these sample names are available. Apply tags/labels within each service's character and syntax limits.

### 6.2. APIs and Quotas

Example commands to run **strictly in an authorized staging project**:

~~~bash
PROJECT_ID="shopflow-staging-001"
REGION="asia-southeast1"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  compute.googleapis.com \
  sqladmin.googleapis.com \
  servicenetworking.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project="$PROJECT_ID"
~~~

Permission to enable APIs does not grant permission to deploy every service. Before provisioning, verify organization policies, region availability, quotas, billing accounts, and dependent APIs. In production, enable APIs via reviewed IaC.

## 7. Identity, IAM, and Secret Protection

Create at least two separate runtime service accounts plus a build/deploy identity per organizational policy:

~~~bash
gcloud iam service-accounts create shopflow-web-sa \
  --display-name="ShopFlow web runtime" \
  --project="$PROJECT_ID"

gcloud iam service-accounts create shopflow-api-sa \
  --display-name="ShopFlow API runtime" \
  --project="$PROJECT_ID"
~~~

### 7.1. IAM Matrix

| Principal | Sample Least-Privilege Permission | Scope |
|---|---|---|
| Web runtime SA | `roles/run.invoker` | On Cloud Run `shopflow-api` |
| API runtime SA | `roles/cloudsql.client` | Project containing Cloud SQL instance |
| API runtime SA | `roles/secretmanager.secretAccessor` | Specific DB password secret |
| API runtime SA | `roles/storage.objectCreator` | Invoices bucket if write-only |
| Outbox publisher SA or API SA | `roles/pubsub.publisher` | `order-events` topic |
| Consumer runtime SA | Subscriber or matching service permissions | Subscription and target resources |
| CI build SA | Build, read source, push image | Needed project/repository |
| CD deploy SA | Cloud Run deploy + `iam.serviceAccountUser` | Approved service and runtime SA |
| Operator | Viewer/Monitoring and controlled break-glass | Project/service scope |

Use resource-level bindings wherever services support them; never grant Owner/Editor to app SAs. Developers do not need `Secret Manager accessor` on every secret or production write access just to run unit tests.

### 7.2. Three Authentication Layers That Must Not Be Collapsed

1. **End user:** authenticates and authorizes viewing/creating orders per user or tenant.
2. **Service-to-service:** web SA calls the backend Cloud Run service using an ID token with the backend URL audience.
3. **Database:** Cloud SQL Connector authenticates IAM at the transport layer, while PostgreSQL users/GRANTs enforce read/write privileges.

Never assume `roles/run.invoker` on the backend replaces end-user authorization. Every order create/view request must verify owner/tenant in the business layer.

### 7.3. Secret Lifecycle

- Never put passwords into default Terraform variables, Git, Dockerfiles, or image layers.
- Provision secrets through a protected workflow, storing and rotating them per policy.
- Pin exact secret versions when deterministic rollbacks are needed; using `latest` requires tested version/rotation handling.
- Restrict which principals hold `secretAccessor`.
- Rotation must account for active DB connections and rollout timing.
- Enable appropriate audit logging and never log secret values.

## 8. Network Design and Private Data Path

~~~mermaid
flowchart LR
    WEB["Cloud Run web"] -->|"HTTPS ID token"| API["Cloud Run API"]
    API -->|"Direct VPC egress"| SUB["Subnet 10.80.8.0/24"]
    SUB --> PSA["Private Services Access"]
    PSA --> SQL["Cloud SQL private IP"]
    API --> GOOGLE["Google APIs 443<br/>Cloud SQL Admin / PubSub / Storage"]
~~~

### 8.1. VPC and Subnet

CLI example when standing up a **new** staging environment without Shared VPC:

~~~bash
gcloud compute networks create shopflow-vpc \
  --subnet-mode=custom \
  --project="$PROJECT_ID"

gcloud compute networks subnets create shopflow-run-subnet \
  --network=shopflow-vpc \
  --region="$REGION" \
  --range=10.80.8.0/24 \
  --enable-private-ip-google-access \
  --project="$PROJECT_ID"
~~~

For Cloud Run services, Direct VPC egress needs a sufficiently large subnet, at least `/26`. `/24` here provides headroom for scaling and revision rollouts. Check `10.80.8.0/24` against your organization's network ranges to prevent overlap.

### 8.2. Private Services Access for Cloud SQL

Cloud SQL private IP via Private Services Access needs a reserved IP range and a service networking connection. Example **applies only when the network does not yet have a private services connection**:

~~~bash
gcloud compute addresses create google-managed-services-shopflow \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="projects/$PROJECT_ID/global/networks/shopflow-vpc" \
  --project="$PROJECT_ID"

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-shopflow \
  --network=shopflow-vpc \
  --project="$PROJECT_ID"
~~~

Never create overlapping allocations, alter existing peerings, or delete shared ranges. In production Shared VPCs, the host project/network team typically owns this. The Cloud SQL instance must be created with a private IP on the right network; never turn on public IP just because staging connectivity failed.

### 8.3. Backend SQL Connectivity

Spring Boot example using Cloud SQL Java Connector and the PostgreSQL JDBC socket factory (requires compatible `pgJDBC` and `postgres-socket-factory` dependencies):

~~~properties
server.port=8080
spring.datasource.url=jdbc:postgresql:///orders?cloudSqlInstance=PROJECT_ID:asia-southeast1:shopflow-db&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE&cloudSqlRefreshStrategy=lazy&sslmode=disable
spring.datasource.username=shopflow_app
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.minimum-idle=0
spring.datasource.hikari.connection-timeout=10000
~~~

In real applications, **never hard-code the instance connection name**; load it from reviewed config/environment variables. Load the password from `SPRING_DATASOURCE_PASSWORD` injected via Secret Manager—never write it in properties files.

Setting `sslmode=disable` at the **pgJDBC layer when using Cloud SQL Java Connector** does not mean traffic to Cloud SQL is plaintext: TLS is managed by the connector. Never use that setting for direct IP JDBC connections without properly configured TLS.

### 8.4. Connection Budget

If the API allows up to 10 Cloud Run instances and each instance sets Hikari max pool size to 5:

\[
C_{\text{expected max}} \approx 10 \times 5 = 50\ \text{connections}
\]

That is 50 connections for the backend alone, excluding migrations, admin tools, reporting, and other workloads. Size pools to Cloud SQL capacity and monitor active/pending connections, latency, and query locks. Raising Cloud Run concurrency does not magically increase database capacity.

## 9. Data Model, Transactions, and Idempotency

### 9.1. Minimal Schema

~~~sql
CREATE TABLE orders (
  id BIGSERIAL PRIMARY KEY,
  customer_id UUID NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  total_amount_minor BIGINT NOT NULL,
  currency CHAR(3) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (customer_id, idempotency_key)
);

CREATE TABLE order_outbox (
  event_id UUID PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id),
  event_type VARCHAR(128) NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at TIMESTAMPTZ
);
~~~

Never store monetary values in floating point where precision matters; use minor units per currency alongside approved rounding rules. Manage schema versions with a migration tool (Flyway/Liquibase); avoid uncontrolled auto-DDL on every app startup.

### 9.2. Transactional Outbox

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Orders API
    participant DB as Cloud SQL
    participant PUB as Outbox publisher
    participant PS as Pub/Sub
    U->>API: POST order + idempotency key
    API->>DB: Transaction: INSERT order + outbox event
    DB-->>API: COMMIT
    API-->>U: 201 order_id
    PUB->>DB: Poll unsent outbox
    PUB->>PS: Publish event_id + payload
    PS-->>PUB: Ack
    PUB->>DB: Mark published_at
~~~

Writing the order and outbox row **inside the same DB transaction** prevents "order committed without a retryable event record". However, if the publisher publishes to Pub/Sub and crashes before updating `published_at`, the event may be sent again. Consumers must still be idempotent on `event_id`.

**Never promise end-to-end exactly-once** solely by choosing Pub/Sub. Exactly-once business outcomes require atomic deduplication in consumers and/or idempotency keys.

### 9.3. API Contract

| API | Input | Expected Status | Mandatory Tests |
|---|---|---|---|
| `POST /api/orders` | JSON items + `Idempotency-Key` header | 201 or existing order response | Duplicate key, atomic transaction |
| `GET /api/orders/{id}` | Order ID | 200 or 404/403 per policy | Tenant isolation |
| `GET /healthz` | No business payload required | 200 when app is alive | Liveness |
| `GET /readyz` | DB connectivity/readiness per policy | 200/503 | Readiness |
| `GET /api/orders` | Pagination, filters | 200 | Authz, query performance |

Sample request:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-request-7d9a

{
  "items": [
    {"sku": "book-01", "quantity": 2}
  ],
  "currency": "VND"
}
~~~

Sample response:

~~~json
{
  "id": 14572,
  "status": "CREATED",
  "currency": "VND",
  "totalAmountMinor": 240000,
  "traceId": "c84f-example"
}
~~~

Sample data is illustrative. Real systems must look up and validate prices on the server rather than trusting client-supplied amounts. Avoid running heavy DB queries inside health endpoints that amplify database load as instances scale.

## 10. Repository Structure and Ownership

~~~text
shopflow/
  README.md
  docs/
    charter.md
    requirements.md
    architecture.md
    adr/
      001-cloud-run.md
      002-database.md
    security-threat-model.md
    runbooks/
      api-5xx.md
      db-restore.md
      release-rollback.md
    handover/
      resource-register.md
      raci.md
      acceptance.md
  services/
    shopflow-web/
      Dockerfile
      src/
      tests/
    shopflow-api/
      Dockerfile
      pom.xml
      src/main/
      src/test/
  infrastructure/
    modules/
      network/
      sql/
      cloud-run/
      observability/
    envs/
      staging/
      production/
  pipelines/
    cloudbuild-api.yaml
  tests/
    api-contract/
    load/
    dr/
~~~

This is a **recommended layout for learners to create in their own repository**, not a list of files for this task to write. Never commit secrets, kubeconfigs, Terraform state, private keys, or build credentials to repositories.

### 10.1. Branching and Change Control

- Pull requests require code review and passing status checks.
- Infrastructure changes require saved `terraform plan` outputs as evidence and approvals.
- Database schema migrations receive separate review with backward-compatibility checks.
- Production deployments promote the exact image digest verified in staging; never rebuild from the same branch and assume identical artifacts.
- Enforce `CODEOWNERS` or reviewer rules for security/IAM/network/DR paths.
- Never edit production manually via Console without logging a change record and reconciling drift.

## 11. IaC: Turning Architecture into Repeatable Resources

Terraform defines the VPC, subnets, IAM, Cloud SQL, Cloud Run, Monitoring, and supporting resources. Teams should maintain **centralized backend state with locking**.

### 11.1. Bootstrapping Remote State

Before running `terraform init`, the platform team creates a dedicated GCS state bucket with restricted IAM, public access prevention, versioning, and recovery procedures. Terraform's backend cannot create the very bucket it needs to store state.

Backend example:

~~~hcl
terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
  backend "gcs" {
    bucket = "ORG-APPROVED-TF-STATE-BUCKET"
    prefix = "shopflow/staging"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
~~~

**Note:** select and pin provider versions via `.terraform.lock.hcl` after testing; this skeleton omits version pins because it is not a complete production Terraform module.

### 11.2. Small Network Module

~~~hcl
variable "project_id" { type = string }
variable "region" { type = string }

resource "google_compute_network" "shopflow" {
  name                    = "shopflow-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "run" {
  name                     = "shopflow-run-subnet"
  region                   = var.region
  network                  = google_compute_network.shopflow.id
  ip_cidr_range            = "10.80.8.0/24"
  private_ip_google_access = true
}
~~~

This minimal module is not yet enough for Cloud SQL private IP: you still need the service networking reserved range/connection and DB instance. IAM bindings and service APIs must also be managed. Avoid placing database passwords directly into Terraform state whenever possible; use Secret Manager via a secure workflow.

### 11.3. Infrastructure Change Workflow

~~~bash
terraform fmt -check
terraform validate
terraform plan -out=staging.tfplan
# Authorized reviewer inspects plan, cost, and IAM/network changes.
terraform apply staging.tfplan
~~~

`apply` **mutates real infrastructure** and can incur costs. Plan and state files may contain sensitive metadata; store them in restricted locations and never paste them into public chats or tickets.

A good production pipeline never runs `terraform destroy` automatically. For Cloud SQL, enforce deletion protection, backup retention, and approved change workflows. Never treat every state-vs-infra diff as safe to immediately overwrite during an active migration or incident.

## 12. Artifacts, Builds, and CI

Only deploy tested, traceable images. CI flow:

~~~mermaid
flowchart LR
    PR["Pull request"] --> T["Unit/integration + SAST"]
    T --> B["Build container"]
    B --> SCAN["Dependency/container scan"]
    SCAN --> REG["Artifact Registry: digest"]
    REG --> ST["Staging deploy + tests"]
    ST --> APPROVE["Approval / promotion"]
    APPROVE --> PROD["Production release"]
~~~

### 12.1. Cloud Build Example for Orders API

This example assumes source and `Dockerfile` reside in `services/shopflow-api`, with Maven building the JAR before Docker builds the image. Substitutions must be configured in the Cloud Build trigger/job.

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _REPO: shopflow-images

steps:
  - name: 'maven:3.9-eclipse-temurin-17'
    dir: 'services/shopflow-api'
    entrypoint: 'mvn'
    args: ['-B', '-ntp', 'verify']

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - '$_REGION-docker.pkg.dev/$PROJECT_ID/$_REPO/shopflow-api:$BUILD_ID'
      - 'services/shopflow-api'

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - '$_REGION-docker.pkg.dev/$PROJECT_ID/$_REPO/shopflow-api:$BUILD_ID'

images:
  - '$_REGION-docker.pkg.dev/$PROJECT_ID/$_REPO/shopflow-api:$BUILD_ID'
~~~

This is an **illustrative build pipeline**, not an automated production deployment. Configure the build service account, repository push permissions, APIs, triggers, scan policies, and record the artifact digest. Real test suites require unit tests, integration tests, migration/DB compatibility tests, and scoped security checks.

### 12.2. Image Provenance and Release Manifest

Minimal release record:

~~~yaml
release_id: shopflow-2026-11-example
git_commit: REPLACE_WITH_COMMIT_SHA
image_digest: sha256:REPLACE_WITH_VERIFIED_DIGEST
pipeline_run: REPLACE_WITH_CLOUD_BUILD_ID
environment: staging
tested_at: REPLACE_WITH_TIMESTAMP
approved_by: REPLACE_WITH_APPROVER
terraform_plan_ref: REPLACE_WITH_REVIEWED_PLAN_REFERENCE
db_migration_version: V12
~~~

This record must be **populated with real results** from CI/testing, never simulated placeholders. When promoting staging → production, use the exact same digest and compatible database migrations instead of rebuilding from the branch. Evaluate SBOMs, vulnerability scanning, and build provenance/attestations per organizational supply-chain policy.

## 13. Deploying Staging in Dependency Order

Do not fire off commands in bulk while ignoring intermediate failures. Design **gates** so failures stop cleanly at a single layer.

| Step | Action | PASS Condition |
|---|---|---|
| S1 | Project, APIs, billing, org policies | Owner, quotas, and valid permissions confirmed |
| S2 | VPC/subnet, private service networking | CIDR/route review PASS |
| S3 | Runtime SAs, secrets, bucket, topic, repository | IAM matrix and security review PASS |
| S4 | Cloud SQL, DB roles, migrations, backups/PITR | Private instance, recovery settings verified |
| S5 | Build/test/scan frontend and API | Pipeline PASS, image digest recorded |
| S6 | Deploy Cloud Run backend | Ready, SQL connectivity works, IAM enforced |
| S7 | Grant invoker and deploy frontend | Web calls API via service identity |
| S8 | Outbox publisher and Pub/Sub consumer if used | Retry/dedup/DLQ tests PASS |
| S9 | E2E, load, security, and recovery tests | Zero open critical defects |
| S10 | Dashboard, alerts, SLOs, and runbooks | Ops owner confirmed |
| S11 | Production Go/No-Go | Valid approval recorded |

### 13.1. Staging Cloud SQL

In the Console or a reviewed Terraform module:

1. Select a PostgreSQL version compatible with your tested runtime and driver.
2. Pick a region close to Cloud Run to cut latency and cross-region risk.
3. Create the instance with **private IP** on the right VPC and Private Services Access.
4. Create the `orders` database and a non-superuser runtime DB user.
5. Enable backups and verify **PITR is genuinely enabled** per edition/creation flow; never assume it defaults on everywhere.
6. Size storage, maintenance windows, deletion protection, and HA per requirements and budget.
7. Run schema migrations under a separate DDL identity, not the runtime application user.
8. Test connectivity and privileges from **Cloud Run staging**; laptop tests do not substitute for this.

### 13.2. Deploying the Backend with a Verified Image

Variables below must come from the approved release manifest:

~~~bash
PROJECT_ID="shopflow-staging-001"
REGION="asia-southeast1"
API_SA="shopflow-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
API_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/shopflow-images/shopflow-api:REVIEWED_BUILD_ID"
SQL_CONN="$PROJECT_ID:$REGION:shopflow-db"

gcloud run deploy shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$API_IMAGE" \
  --service-account="$API_SA" \
  --no-allow-unauthenticated \
  --ingress=all \
  --network=shopflow-vpc \
  --subnet=shopflow-run-subnet \
  --vpc-egress=private-ranges-only \
  --set-env-vars="INSTANCE_CONNECTION_NAME=$SQL_CONN,SPRING_PROFILES_ACTIVE=staging,SPRING_DATASOURCE_USERNAME=shopflow_app" \
  --set-secrets="SPRING_DATASOURCE_PASSWORD=shopflow-db-password:5" \
  --max-instances=10
~~~

**Preconditions:** image and secret version 5 already exist; SA holds `roles/cloudsql.client` and read access on the specified secret; VPC/subnet/Cloud SQL private IP are configured properly; and the app loads `INSTANCE_CONNECTION_NAME` to construct its JDBC URL. This sample command does not guarantee all prerequisites are satisfied.

`--ingress=all` accepts HTTP connections to the service URL, while `--no-allow-unauthenticated` still enforces IAM invoker checks. If organizational policy demands stricter ingress, redesign the frontend→backend path and test thoroughly rather than switching arbitrarily to `internal-only`.

### 13.3. Frontend Authenticating to Backend

Once the backend exists:

~~~bash
WEB_SA="shopflow-web-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$WEB_SA" \
  --role="roles/run.invoker"
~~~

Node.js example running on the **web server** (never in the browser):

~~~javascript
const {GoogleAuth} = require("google-auth-library");
const auth = new GoogleAuth();
const apiOrigin = process.env.API_ORIGIN;

async function getOrder(orderId) {
  const client = await auth.getIdTokenClient(apiOrigin);
  const response = await client.request({
    url: apiOrigin + "/api/orders/" + encodeURIComponent(orderId),
    method: "GET"
  });
  return response.data;
}
~~~

The ID token's audience is the **Cloud Run service URL or configured custom audience**, never an arbitrary custom domain. The backend must still authenticate/authorize the end user at the application level; IAM invoker verifies only the calling service's identity.

### 13.4. Deploying the Frontend

~~~bash
API_URL=$(gcloud run services describe shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)")

WEB_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/shopflow-images/shopflow-web:REVIEWED_BUILD_ID"

gcloud run deploy shopflow-web \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$WEB_IMAGE" \
  --service-account="$WEB_SA" \
  --allow-unauthenticated \
  --set-env-vars="API_ORIGIN=$API_URL" \
  --max-instances=10
~~~

Use `--allow-unauthenticated` only if the frontend is genuinely an approved public website. For internal apps, enforce appropriate identity/edge ingress policies and test the authenticated path.

## 14. How Are Outbox, Pub/Sub, and Consumers Operated?

The outbox → Pub/Sub → consumer flow has multiple failure points even after an order-creation request COMMITs.

| Component | Permission and Control | Test Scenario |
|---|---|---|
| Outbox publisher | `Pub/Sub publisher` on topic | Published, then crashed before marking DB |
| Pub/Sub topic/subscription | Retention, retry policy, DLQ | Backlog, poison messages, redelivery |
| Push subscription | Push service identity and invoke right on Cloud Run consumer | Wrong audience, 401/403 |
| Pull consumer | `pubsub.subscriber` on subscription | Ack deadline expiry, reconnect |
| Worker application | Atomic event deduplication | Duplicate invoice/email sends |
| Dead-letter flow | Alerts, operator, publish/consume permissions | Failing events not retried forever |

For Pub/Sub push to Cloud Run, configure push authentication with an authorized service account; the push SA needs `roles/run.invoker` on the worker, and the Pub/Sub service agent needs permission to mint OIDC tokens. Never make the worker unauthenticated to fix 403 errors.

### 14.1. Consumer Idempotency

~~~sql
CREATE TABLE processed_events (
  event_id UUID PRIMARY KEY,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
~~~

Processing within a transaction:

1. Insert `event_id` with a uniqueness guard (if already present, return early).
2. Perform DB side effects inside the same transaction wherever possible.
3. Commit first, then ACK.
4. For external side effects like emails, use an idempotency key/ledger or follow-on outbox because an email may have been sent before the process recorded state.

Pub/Sub can redeliver. **Never claim pipeline-wide exactly-once semantics** merely because you use Pub/Sub, an outbox, or a single successful ACK.

## 15. Pre-Production Test Matrix

| Layer | Case | Environment | Evidence |
|---|---|---|---|
| Unit | Validation, pricing, state transitions, idempotency | JVM/local | JUnit report |
| Component | Repositories, outbox, transaction rollbacks | DB testcontainers/fakes | Integration report |
| API contract | Response schemas, 401/403/409, pagination | Staging | API tests |
| Cloud integration | Cloud SQL/Secret Manager/Bucket/Pub/Sub permissions | Staging | Logs + resource states |
| Security | Secret scan, SAST, dependency scan, user authz | CI/staging | Findings/approvals |
| Load | Baseline and peak traffic | Staging with quota | P95, 5xx, DB pool |
| Failure | DB timeout, Pub/Sub backlog, expired secret | Isolated staging | Recovery/retry results |
| Backup/DR | PITR, restore, and data correctness | Recovery staging | RPO/RTO timestamps |
| E2E | Sign-in → place order → inspect order/invoice/event | Staging | Business sign-off |

### 15.1. Mandatory Test Cases

- Two concurrent POSTs with the same idempotency key create only one order.
- Runtime SA cannot read out-of-scope secrets.
- Anonymous requests to the backend API are rejected.
- User A cannot read User B's orders, even through a valid frontend SA.
- Failed outbox publishes replay cleanly after restart.
- Pub/Sub redeliveries produce zero duplicate side effects.
- Database migrations do not break older revisions during a canary.
- Database connection timeouts fail boundedly without infinite retries.
- After restore, `orders` rows and invoice metadata link accurately to Cloud Storage.

### 15.2. HTTP Smoke Test

Only if the frontend exposes a `/healthz` endpoint:

~~~bash
WEB_URL=$(gcloud run services describe shopflow-web \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)")

curl -i "$WEB_URL/healthz"
~~~

Never open public access to the backend or pass ID tokens in query strings. Direct backend tests require a principal with `run.invoker` and a Google-signed ID token with the exact target audience.

### 15.3. Load Testing and Connection Budget

| Load Level | API P95 | 5xx | Active DB Connections | Conclusion |
|---|---:|---:|---:|---|
| 20 requests/s | Measure | Measure | Measure | Pass/fail |
| 100 requests/s | Measure | Measure | Measure | Pass/fail |
| 200 requests/s | Measure | Measure | Measure | Pass/fail |
| 5-minute burst | Measure | Measure | Measure | Pass/fail |

These cells intentionally say "Measure": never fabricate evidence without running the tests. Test with realistic request mixes rather than hitting `/healthz` alone. Load-test only approved environments.

## 16. Threat Model and Security Testing

| Threat | Boundary | Control | Evidence |
|---|---|---|---|
| Anonymous call to backend | Cloud Run IAM | `no-allow-unauthenticated` + invoker | Negative test |
| Broken object authorization | Backend/data | Tenant ownership checks | Cross-user access test |
| SQL injection | Java → PostgreSQL | Prepared statements / binding | SAST + tests |
| Secrets in code/logs | CI/runtime | Secret Manager, scanning, redaction | Scan results |
| Spoofed/duplicate Pub/Sub event | Topic/worker | Publisher IAM, schema, dedup | Replay test |
| Unauthorized invoice read | Bucket/application | Object IAM, policy-backed signed access | IAM negative test |
| Accidental DB deletion | Database | Deletion protection, PITR, role separation | Restore drill |
| Compromised CI | Deployment | Workload Identity Federation, approvals, provenance | IAM/audit review |
| Supply-chain dependency | Container | Dependency scan, SBOM, artifact digest | CI evidence |

Cloud encryption at rest does not automatically prove compliance with every control. When using CMEK, design Cloud KMS key lifecycles and recovery before enabling it, because unavailable keys render backups unusable.

## 17. Dashboards, SLIs, and Alerting

| Signal | Source | Responder |
|---|---|---|
| Good/eligible requests and 5xx | Cloud Run/Monitoring | App on-call |
| P50/P95/P99 per endpoint | Tracing/APM | App/SRE |
| Order success, duplicates prevented | Custom application metrics | Commerce/App |
| CPU, disk, connections, slow queries | Cloud SQL Monitoring | DBA |
| Outbox age / oldest unacked message | App/Pub/Sub | Event worker owner |
| Invoice write failures | Storage metrics/app logs | App |
| Secret/IAM denials | Audit Logs | Security/App |
| Cloud Run revision rollouts | Deploy logs/revision metrics | Platform |
| Budget anomalies | Cloud Billing | FinOps |

Example structured application log:

~~~json
{
  "severity": "INFO",
  "service": "shopflow-api",
  "environment": "staging",
  "release": "image-digest-placeholder",
  "traceId": "example-trace",
  "event": "order_created",
  "orderId": 14572,
  "durationMs": 87,
  "outcome": "success"
}
~~~

Never log passwords, access tokens, card numbers, or raw invoice data. Configure PII handling and log retention per policy.

### 17.1. Actionable Alerts

| Alert | Example Trigger | Runbook |
|---|---|---|
| Error budget fast burn | Rapid SLO burn per policy | `api-5xx` |
| Cloud SQL connection exhaustion | Rising pending/acquire timeouts | `db-connection` |
| Backup failure | No recent valid recovery point | `db-restore` |
| Rising Pub/Sub oldest unacked age | Exceeds data freshness SLO | `event-backlog` |
| Rising secret access denials | After release or rotation | `iam-secret` |
| Budget forecast exceeds threshold | Real anomaly | `cost-review` |

Every alert needs an owner, notification route, and simulated test. Alerts without runbooks create noise rather than reliability.

## 18. Evidence-Backed Backups, PITR, and DR

Data classification:

| Data | Source of Truth | Protection |
|---|---|---|
| Orders, outbox | Cloud SQL | Backups, PITR, restore |
| Invoice binaries | Cloud Storage | Appropriate soft delete/versioning/retention |
| Pub/Sub events | Topic/subscription | Retention/DLQ/replay, outbox |
| IaC state | GCS backend | Versioning, IAM, access recovery |
| Images | Artifact Registry | Digests, retention, rebuild plan |
| Secrets/keys | Secret Manager/Cloud KMS | Backup/access recovery per policy |
| Docs/runbooks | Repo/document store | Versioning and out-of-band failure-domain access |

**Cloud SQL PITR creates a new instance** rather than mutating the running instance in place. Therefore, RTO includes instance creation, data validation, updating connections/secrets/networking, redeploying if needed, testing business flows, and shifting traffic.

### 18.1. Recovery Drill

Simulate logical corruption at 10:00, with the clean recoverable point at 09:55:

1. Record UTC incident timestamp and the DR decision-maker.
2. Freeze writes if corruption is spreading.
3. Create a **new PITR instance** in the recovery environment.
4. Reconcile schema, order counts, and business checksums.
5. Connect a read-only test app to the recovered database.
6. Run authenticated GETs and appropriate business validation.
7. Record reconciliation outcomes and verify outbox/event state.
8. Measure actual RPO/RTO, capture evidence, and log action items.

\[
RPO_{\text{observed}}=10{:}00-09{:}55=5\ \text{minutes}
\]

If users regain order placement at 11:25, measured RTO = 85 minutes. Never stop the clock simply when the database instance reports Ready.

### 18.2. Zone HA vs. Region DR

Cloud SQL regional HA reduces downtime during zone failures, yet **does not automatically protect against losing an entire region**. If N04/N05 apply to regional outages, plan for a secondary region, data replication/backups, IAM/keys/networking/quotas, and live failover drills.

A tabletop review does not prove real RTO. If a live cross-region drill has not been executed, mark it explicitly as an **unverified risk** with an assigned owner.

## 19. API 5xx Runbook

### Trigger

- Error budget burn or 5xx rate crosses P1/P2 threshold.
- Verified user-facing issue.
- Synthetic checkout failures exceed tolerance.

### Procedure

1. Open an incident record; log UTC start time, severity, and Incident Commander.
2. Inspect recently deployed Cloud Run revisions, latency, 5xxs, SQL connections, and Pub/Sub backlog.
3. Check IAM denials, Secret Manager access, and network egress.
4. If correlated with a release, check whether rolling back the revision breaks the schema.
5. For DB outages, execute the DB runbook rather than triggering retry storms.
6. Test the order create/view business flow and verify events/invoices.
7. Downgrade severity only after SLIs and live transactions recover.
8. Document timeline, impact, data reconciliation, and postmortem.

Read-only inspection commands:

~~~bash
gcloud run services describe shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(status.url,status.traffic,status.conditions)"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service=shopflow-api
~~~

**Impactful** rollback command, run only after approval:

~~~bash
gcloud run services update-traffic shopflow-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --to-revisions=KNOWN_GOOD_REVISION=100
~~~

Rolling back an application revision **does not roll back database schemas or data**. If a non-backward-compatible migration ran, execute a dedicated fix-forward or data recovery plan.

## 20. Releases, Canaries, and Rollbacks

~~~mermaid
flowchart LR
    OLD["Old revision"]
    NEW["New revision"]
    SERVICE["Cloud Run service traffic"]
    CLIENT["Client requests"]
    OLD -->|"95% illustrative"| SERVICE
    NEW -->|"5% illustrative"| SERVICE
    SERVICE --> CLIENT
~~~

During a canary, compare error rate, P95 latency, DB contention, event schema compatibility, and order success rate between revisions. Increase traffic only per policy once evidence supports it; revert to the old revision if metrics breach thresholds.

### 20.1. Expand–Migrate–Contract

For database changes:

- **Expand:** add columns/indexes while the older version keeps working.
- **Migrate:** backfill data and deploy code reading the new schema without breaking old revisions.
- **Contract:** drop legacy fields only after no clients or revisions depend on them.
- Back up and record schema versions before each step.
- Test rolling back from canary to old code against the expanded database.

When replacing a legacy on-prem system with live data, include data migration (e.g., DMS for PostgreSQL), initial load/CDC, write freeze, reconciliation, and cutover. **Never let source and target accept concurrent writes** without an explicitly engineered multi-writer architecture.

## 21. Pre-Production Go/No-Go

| Gate | Go When | No-Go When |
|---|---|---|
| Business | Scope/SLO/RPO/RTO approved | Missing owner or acceptance criteria |
| Architecture | ADR/network/data flow reviewed | Unclear trust boundaries |
| Security | IAM/secret/threat tests PASS | Critical finding open |
| Data | Backups/PITR/permissions/migrations PASS | Restore untested |
| Functional | Order, authz, outbox, and consumer PASS | Major business defect |
| Performance | P95/5xx/connection budget met | Fails peak load test |
| Operations | Dashboard, alerts, on-call, and runbooks PASS | Nobody accountable for incidents |
| FinOps | Budgets/quotas/cost owners approved | Over budget with no mitigation |
| Deployment | Immutable digest and rollback tested | Known-good revision unknown |

Sample Go/No-Go record:

~~~text
Release: ShopFlow 1.0
Environment: production
Business owner: [approver]
Platform owner: [approver]
DB owner: [approver]
Security: [approver]
Approved image digest: [digest]
Terraform plan: [reference]
Schema migration version: [version]
Go/No-Go timestamp (UTC): [time]
Decision: GO / NO-GO
~~~

Never mark GO without real approval. Supporting evidence includes dashboards, test reports, IAM diffs, DR drills, and change tickets.

## 22. Cutover and Hypercare Runbook

For a greenfield system with no legacy data, cutover is mainly opening traffic. When replacing a legacy app with data, cutover must also establish the **primary database**, write fencing, and in-flight transactions.

### 22.1. Illustrative Timeline

| Milestone | Task | Owner | Evidence |
|---|---|---|---|
| T-1 day | Lock image digest, Terraform plan, backups, DNS/SSL | Release lead | Approval |
| T-30 min | Staging health, alerts, dashboard, notification channels | SRE | G0–G8 PASS |
| T-10 min | Stop source writers/batches if migrating data | Database lead | Zero active writers |
| T0 | Promote/cut over database per runbook if needed | Database lead | CDC lag / data validation |
| T+ | Canary frontend/API traffic | Platform | Revision metrics |
| T+ | Smoke-test orders, tenant auth, outbox, invoices | QA/Business | Business evidence |
| T+ | Watch P95, 5xx, connections, queues, and cost | On-call | Dashboard |
| T+N days | End hypercare, hand over, then decommission legacy | Business/Platform | Sign-off |

Never rely on low DNS TTLs as a guarantee that all clients switch instantly: caches and keep-alive connections persist. If the target has already accepted new transactions, rolling back to the old source without reverse-syncing loses data. Prefer fix-forward or approved reconciliation instead.

### 22.2. Hypercare

Over 24–72 hours or the approved window:

- Track error rate, P95/P99, order creation counts, DB locks/connections, and Pub/Sub backlog.
- Compare against pre-migration baselines and across Cloud Run revisions.
- Verify Cloud SQL backups/PITR, object storage, and alert notifications.
- Monitor budgets/anomalies to catch unintended resources spawned by the rollout.
- Log all issues with severity, owner, deadline, workaround, and root cause.
- Never delete source/recovery resources until retention ends and business sign-off is granted.

## 23. FinOps: Cost Estimation, Monitoring, and Optimization

A capstone should secure budget approval **before provisioning resources**, not merely summarize costs after the invoice arrives.

| Component | Cost Drivers | Control Points |
|---|---|---|
| Cloud Run | CPU, memory, requests, min instances, concurrency | Right-size, tune timeouts and caching |
| Cloud SQL | Compute tier, HA, storage, backups, PITR logs | Right-size to P95 and query load |
| Cloud Storage | Stored bytes, operations, retrieval, egress | Lifecycle and approved retention |
| Pub/Sub | Published/delivered bytes, subscription retention | Payload size and retry limits |
| Artifact Registry | Storage/transfer | Retention aligned to release policy |
| Cloud Build | Build minutes, build pools | Caching and pipeline optimization |
| Network | Egress, LB/NAT if used, inter-region transfer | Co-locate services and check flows |
| Observability | Log ingestion, custom metrics, trace volume | Sampling, retention, cardinality |
| DR | Backup storage, recovery replicas/drills | Policies aligned to RPO/RTO |

~~~text
Monthly estimate =
  Cloud Run compute/requests
+ Cloud SQL compute/storage/backup
+ Cloud Storage + Pub/Sub + Artifact Registry
+ Network/LB/NAT
+ CI + Logging/Monitoring + DR
+ applicable taxes and contractual discounts
~~~

Do not put made-up USD figures into a table and treat them as current pricing. Use the Google Cloud Pricing Calculator for your real region/tier/requests and reconcile against SKU-level Cloud Billing Reports after staging runs.

### 23.1. Budget Alerts Do Not Automatically Stop Spend

Set budgets and alerts at, say, 50%, 80%, and 100% of forecast, plus anomaly detection for unexpected spikes. Budget alerts typically notify only; any automated shutdown must be engineered separately to avoid data loss or production outages.

### 23.2. Value of Labels and Ownership

Consistently apply `environment`, `application`, `team`, `cost-center`, and `business owner` labels on supported resources. For shared infrastructure, agree on an approved allocation/chargeback rule rather than dumping the entire bill onto a single service.

## 24. Operational Handover Pack

The engineering team hands over to SRE/Platform/DBA with **versioned records linked to real evidence**:

| Document | Minimum Contents | Recipient |
|---|---|---|
| H01 – Service catalog | Service names, projects, regions, URLs, owners, tags | SRE |
| H02 – Architecture | Diagrams, trust boundaries, ADRs, flow IDs | SRE/Security |
| H03 – Resource register | IDs, quotas, networking, IAM, secret references | Platform |
| H04 – Code/deployment | Repos, release manifests, digests, pipeline triggers | DevOps |
| H05 – Data | Schemas, migrations, roles, backup retention, PITR | DBA |
| H06 – Observability | Dashboards, SLOs, alert rules, escalation | On-call |
| H07 – Runbooks | 5xx, DB outage, Pub/Sub backlog, rollback, restore | Incident commander |
| H08 – Security | Threat model, IAM reviews, rotation, audit controls | Security |
| H09 – FinOps | Budgets, spend baseline, SKU reports, optimization backlog | FinOps |
| H10 – Open risks | Known limits, exceptions, owners, due dates | Business/Platform |
| H11 – DR evidence | Actual RPO/RTO, restore tests, remediation | DBA/SRE |
| H12 – Acceptance | Handover training, approvers, support model | Operations lead |

A repository link alone is insufficient. Recipients must **have access to dashboards, scoped permissions to execute runbooks, clear escalation contacts, and have rehearsed at least one incident drill**.

### 24.1. Illustrative Handover Record

~~~yaml
service: shopflow-orders
environment: production
business_owner: commerce-lead
technical_owner: shopflow-team
operations_owner: sre-team
release_digest: REPLACE_WITH_REAL_DIGEST
region: asia-southeast1
rpo_target_minutes: 15
rto_target_minutes: 120
slo_availability: 0.999
dashboards:
  - REPLACE_WITH_REAL_MONITORING_URL
runbooks:
  - api-5xx
  - db-restore
  - event-backlog
last_drill:
  date: null
  actual_rpo_minutes: null
  actual_rto_minutes: null
acceptance:
  security: pending
  data: pending
  operations: pending
  business: pending
~~~

Leave fields `null`/`pending` until real measurements exist. Never copy target RPO/RTO values into actual RPO/RTO fields.

## 25. RACI: Post-Handover Responsibility Matrix

RACI stands for Responsible, Accountable, Consulted, and Informed.

| Task | Product | App | Platform/SRE | DBA | Security |
|---|---|---|---|---|---|
| Define SLO/impact | A | C | R | C | I |
| Code release/rollback | I | A/R | R | C | C |
| Cloud Run/VPC/CI platform | I | C | A/R | I | C |
| Database/schema/backups | I | R | C | A/R | C |
| IAM/secret policy | I | R | R | C | A |
| Incident command | I | R | A/R | R | C |
| Data reconciliation | A | R | C | R | I |
| DR drill | C | R | A/R | R | C |
| Cost review | A | R | R | C | I |

Adapt this template to your organization. Avoid tasks with no `A` or conflicting multiple `A`s—especially around DB promotion, emergency rollbacks, and failback.

## 26. Operational Readiness Review (ORR)

Before accepting the service, operations checks:

| Axis | Question | Evidence |
|---|---|---|
| Reproducibility | Can a revision be rebuilt/redeployed from its image digest? | CI/CD replay or deployment record |
| IAM | Do runtime SAs hold least privilege? | IAM diff + negative tests |
| Database | Does PITR restore work with consistent data? | Drill report |
| Dependencies | How does the app react when SQL/Secret/Pub/Sub fail? | Fault-injection tests |
| Monitoring | Do P1 alerts reach on-call and remain actionable? | Notification test |
| Rollback | Can the prior revision run against the current schema? | Rehearsal |
| Capacity | Is the DB pool sized for autoscaling? | Load test |
| Cost | Is someone monitoring and resolving spend anomalies? | Budget/FinOps plan |
| Documentation | Do runbooks match the live release? | Owner review |
| Ownership | Who approves failover and decommissioning? | RACI and escalation |

A system with 100% unit tests that has never restored its database, has no alert recipient, or lacks a known rollback digest **fails ORR**.

## 27. Requirements – Testing – Evidence Traceability Matrix

| Requirement | Implementation / Control | Test ID | Evidence |
|---|---|---|---|
| F01: idempotent order | Unique key + DB transaction | T-API-01 | DB state + test output |
| F03: event publishing | Transactional outbox + Pub/Sub | T-EVT-02 | Duplicate replay |
| N01: P95 API | Cloud Run sizing + Cloud SQL indexing | T-PERF-01 | Traces + load report |
| N02: 99.9% availability | Monitoring SLIs/alerts | T-SLO-01 | Dashboard |
| N03: data durability | DB backups/outbox + reconciliation | T-DATA-01 | Consistency report |
| N04: RPO | PITR/backups | T-DR-01 | Recovered timestamp |
| N05: RTO | Restore runbook | T-DR-02 | Incident-like timeline |
| N06: security | IAM matrix/Secret Manager | T-SEC-01 | Permissions/scan |
| N08: FinOps | Budgets/labels/Billing Reports | T-COST-01 | SKU-level cost baseline |

When a critical requirement lacks evidence, mark it explicitly as **NOT VERIFIED** or **BLOCKED**—never quietly flip it to PASS.

## 28. Session-by-Session Practice Schedule

| Session | Activity | Deliverable |
|---|---|---|
| 1 | Stakeholder workshop, BIA, scope | D01–D02 |
| 2 | ADRs/diagrams/threat model/cost estimate | D03–D04 |
| 3 | Project/IAM/VPC/Terraform plans | D05–D06 |
| 4 | Cloud SQL/Storage/Pub/Sub and images | D07–D08 |
| 5 | CI, staging deploy, API contract tests | D07–D09 |
| 6 | Load/security/failure/restore tests | D08–D09 |
| 7 | Release rehearsal, rollback, Go/No-Go | D10 |
| 8 | SLO dashboards, budgets, ORR, handover | D11–D12 |

This is a **training sequence**, not a promise to reach production in eight days. Scale, quotas, approvals, data migrations, and policies can extend each phase.

## 29. Project Grading Rubric

| Category | Points | Good Criteria |
|---|---:|---|
| Requirements/traceability | 10 | Clear, testable SLO/RPO/RTO with owners |
| ADR/architecture/data flow | 15 | Alternatives, trust boundaries, and trade-offs |
| IaC/environment separation | 15 | State, plan reviews, secure IAM/VPC |
| App/data correctness | 15 | Idempotency, outbox, data consistency |
| CI/CD/supply chain | 10 | Digests, scans, release approvals |
| Security | 10 | Evidence-backed IAM/secret/threat tests |
| SRE/observability/FinOps | 10 | Actionable alerts/runbooks/budgets |
| DR and handover | 15 | Restore drill, RACI, sign-off |
| **Total** | **100** | |

**Blocking conditions independent of total score:** unintentionally public backend, leaked secrets, cross-tenant data access, zero backup/restore evidence, production migration lacking safe rollback/failback, or no operational owner.

## 30. Final Acceptance Checklist

- [ ] Scope, owners, and F/N requirements approved.
- [ ] SLO/RTO/RPO, ADRs, diagrams, and traceability complete.
- [ ] Staging and production isolate projects, identities, secrets, databases, and state.
- [ ] Cloud Run backend blocks anonymous invocations.
- [ ] Web→API uses ID tokens with the exact audience; separate user-level authorization enforced.
- [ ] Cloud SQL private IP, VPC routes/peering, and least-privilege DB users active.
- [ ] DB pool budget aligns with Cloud Run max instances.
- [ ] API uses a transactional outbox; consumers are idempotent.
- [ ] Invoice bucket enforces policy-compliant IAM, lifecycle, and retention.
- [ ] Terraform plan reviewed; backend state has IAM and versioning.
- [ ] CI runs unit/integration/security scans and records image digests.
- [ ] Staging performance/security/failure tests PASS.
- [ ] Production canary, rollback, and Go/No-Go approved.
- [ ] SLO dashboards, alerts, log retention, and on-call verified.
- [ ] PITR/restore drill records actual RPO/RTO and data reconciliation.
- [ ] Budgets, cost baselines, labels, and cost owners exist.
- [ ] Handover pack, RACI, ORR, and operations sign-off completed.
- [ ] Open risks carry owners, deadlines, or explicit BLOCKER statuses.

## 31. Self-Check Questions

**1. Why write an ADR once you have already chosen Cloud Run?**

Because an ADR documents context, alternatives evaluated, trade-offs accepted, and triggers to revisit the choice. Services must fit the workload, not merely team familiarity.

**2. Does `roles/run.invoker` on the web SA authorize viewing every order?**

No. IAM authenticates the calling service. The API must still verify end-user or tenant authorization on every order.

**3. Why is a transactional outbox better than calling Pub/Sub right after COMMITting an order?**

An outbox allows reliable retries when the DB commit succeeds but publishing fails. It does not eliminate duplicate deliveries, so consumers must still deduplicate.

**4. Does Cloud SQL PITR mean RTO equals the time it takes to click Restore?**

No. PITR creates a new instance; you must verify data, permissions, routing, connection configs, health, and business flows before restoring user access.

**5. Why calculate Cloud Run instances × DB pool size?**

Because each instance maintains its own pool; total connections can exceed Cloud SQL capacity during autoscaling, causing timeouts even when Cloud Run CPU looks low.

**6. When is rolling back a Cloud Run revision insufficient?**

When database schemas or data changed incompatibly with older code, or when the target DB already accepted post-migration writes. You then need a forward fix, data reconciliation, or a dedicated recovery plan.

**7. Why does a passing build not qualify a service for operational handover?**

Because missing restore drills, on-call alerts, runbooks, budgets, owners, and test evidence can leave real incidents unresolvable.

**8. Can the legacy source system be decommissioned immediately after cutover?**

No. Only after hypercare, business sign-off, backup/retention verification, and confirmation that no dependencies or unreconciled data remain.

## 32. References

- [Google Cloud Architecture Framework](https://cloud.google.com/architecture/framework)
- [Cloud Run overview](https://cloud.google.com/run/docs/overview/what-is-cloud-run)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Run rollouts, rollbacks and traffic migration](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Cloud SQL: connect from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud SQL: private IP](https://cloud.google.com/sql/docs/postgres/configure-private-ip)
- [Cloud SQL: PITR](https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Cloud SQL: backup and recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Secret Manager documentation](https://cloud.google.com/secret-manager/docs/overview)
- [Cloud Storage soft delete](https://cloud.google.com/storage/docs/soft-delete)
- [Pub/Sub: subscriber guide](https://cloud.google.com/pubsub/docs/subscriber)
- [Cloud Build: deploy to Cloud Run](https://cloud.google.com/build/docs/deploying-builds/deploy-cloud-run)
- [Cloud Deploy overview](https://cloud.google.com/deploy/docs/overview)
- [Artifact Registry](https://cloud.google.com/artifact-registry/docs/overview)
- [Terraform on Google Cloud](https://cloud.google.com/docs/terraform)
- [Google Cloud SLO monitoring](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports)
- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/manage-budgets)
