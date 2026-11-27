# Hands-On: Migrating a Three-Tier Application to Google Cloud

Migrating a three-tier application is more than copying servers. The delivery team must move the **traffic ingress path**, **business-logic tier**, and **database** to the new environment, maintain valid connectivity and permissions, and ensure zero lost orders or duplicate writes during cutover. This hands-on lab simulates an order-management application running in an on-premises data center and walks through migrating it to Google Cloud via verifiable, stoppable, and reversible steps.

In the **CLOUD_PROVIDERS_GCP** module, learners have already covered project structure, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases. This lesson pulls those concepts into an end-to-end project: choosing target services, securing resources, automating releases, monitoring reliability, and controlling post-migration costs.

**Objective:** migrate a three-tier system from on-premises NGINX + Spring Boot + PostgreSQL to Cloud Run frontend + Cloud Run backend + Cloud SQL for PostgreSQL—complete with staging tests, private connectivity, continuous data sync, and a cutover/rollback runbook.

After this lesson, you will be able to:

- Build an application inventory, dependency graph, RTO/RPO targets, and acceptance criteria.
- Choose rehost vs. replatform per tier and explain trade-offs.
- Prepare the landing zone, IAM, VPC, connectivity, and secrets.
- Deploy frontend/backend services to Cloud Run and connect the backend to Cloud SQL over private IP.
- Use Database Migration Service (DMS) for PostgreSQL with initial load and change data capture (CDC).
- Verify data consistency, performance, security, and reliability before cutover.
- Execute cutover with a write freeze, monitor replication lag, and shift traffic safely.
- Design proper rollback plans both before and after new writes hit the target system.

**Scope note:** this is a lab guide and does not automatically provision real resources. Project names, images, IPs, timelines, and thresholds are illustrative placeholders. Only create, modify, promote, or shift traffic in authorized environments.

## 1. Source Scenario: Three-Tier Application

Assume the **Orders** system runs in a private data center with an ordering web UI, a Java Spring Boot API, and self-managed PostgreSQL.

| Tier | Source Infrastructure | Responsibility | Dependencies |
|---|---|---|---|
| Presentation | Two NGINX VMs | Serve HTML, reverse-proxy to API | DNS, TLS, API, sessions |
| Application | Two Java 17/Spring Boot VMs | Process orders, check inventory | PostgreSQL, email, object storage |
| Data | PostgreSQL 14 on VM | Store orders, customers, statuses | Disk, backups, WAL, extensions |
| Supporting | SMTP/email API, invoice storage | Send notifications, store files | Outbound network, credentials |

~~~mermaid
flowchart LR
    USER["Users"] --> DNS["DNS / TLS"]
    DNS --> WEB["NGINX web VMs"]
    WEB --> API["Spring Boot app VMs"]
    API --> PG["PostgreSQL VM"]
    API --> OUT["Email / file storage"]
~~~

### 1.1. Assumptions

- The app already has a Dockerfile or can be containerized without major logic changes.
- The frontend can run in a web container; API requests are proxied server-side.
- The source database runs a DMS-supported PostgreSQL version.
- The team has an approved maintenance window and a mechanism to switch the app to read-only mode.
- Payment/ERP integrations and IP allowlists will be re-verified on the cloud.
- No major business schema redesign happens concurrently with the migration.

### 1.2. Inventory and Baseline

| Attribute | Sample Details to Record |
|---|---|
| Production domain | `orders.example.com` |
| Concurrent users | Normal business hours and peak-hour baselines |
| Requests/minute | P50/P95 and 24-hour peaks |
| Database size | Tables, indexes, WAL, daily growth rate |
| Transactions/second | Reads, writes, and slow queries |
| P95 latency | Per endpoint from APM/logs |
| Target RTO | E.g., no more than 60 minutes during cutover |
| Target RPO | Zero loss of confirmed transactions |
| External dependencies | SMTP, SSO, payment providers, object storage |
| Versions | JDK, Spring Boot, PostgreSQL, extensions |
| Data compliance | Region, retention, backups, audit, and key management |

**RTO** is maximum acceptable outage time; **RPO** is maximum acceptable data loss. These are business targets requiring sign-off—not built-in guarantees from Cloud Run or DMS. Near-zero RPO at cutover requires freezing all source writers, waiting for CDC to catch up, and reconciling data.

## 2. Pre-Migration Dependency Discovery

~~~mermaid
flowchart TD
    BROWSER["Browser"] --> WEB["Presentation"]
    WEB --> AUTH["SSO / Identity provider"]
    WEB --> APP["Orders API"]
    APP --> PG["PostgreSQL"]
    APP --> STOCK["Inventory service"]
    APP --> EMAIL["SMTP / Mail API"]
    APP --> FILE["Invoice storage"]
    APP --> AUDIT["Audit / logs"]
~~~

Record latency, protocols, ports, authentication details, owners, and failure handling for every edge.

Key questions:

1. Does the frontend store sessions in RAM, local disk, or a shared store?
2. Does the app have cron jobs, background threads, local file uploads, or in-memory caches?
3. Does PostgreSQL rely on special extensions, triggers, stored functions, roles, or sequences?
4. Do batch jobs, reports, or external integrations write directly to the database outside the app?
5. Are IPs, hostnames, TLS certificates, or SMTP endpoints hardcoded?
6. Are there long-running transactions or table-locking queries during peak hours?
7. Are there data residency, PITR, retention, or audit mandates?
8. Which system is the source of truth at each stage of cutover?
9. Are there OS daemon, raw TCP protocol, or local filesystem dependencies incompatible with Cloud Run?
10. What is the DNS TTL, and who controls DNS changes?

If the app relies heavily on OS daemons or local state, rehost to Compute Engine first or decouple those components. Do not pick Cloud Run merely for autoscaling if the app does not yet fit a stateless architecture.

## 3. Choosing Strategy by Tier

| Strategy | Web/App | Data | Pros | Trade-offs |
|---|---|---|---|---|
| Rehost | Compute Engine | Compute Engine or Cloud SQL | Minimal code changes, fits legacy apps | Must manage VMs, OS patching, backups |
| Replatform | Cloud Run or GKE | Cloud SQL | Less server toil, autoscaling | Requires containerization, externalizing state, network/IAM setup |
| Refactor | Microservices/event-driven | Cloud SQL/Spanner/other | Long-term agility | Higher scope, risk, and timeline |

**This lab selects controlled replatforming:** keep Spring Boot logic and the PostgreSQL schema intact, package frontend/backend as containers, and migrate data to Cloud SQL via DMS. Do not refactor business behavior in the same release.

If an application cannot be containerized yet, choose **Migrate to Virtual Machines** following onboard → replicate → target details → test-clone → cutover → finalize. Isolate test-clones from the source environment to prevent side effects, and remember VM cutover stops the source for final sync. Never run two migration strategies simultaneously against the same workload.

## 4. Target Architecture on Google Cloud

~~~mermaid
flowchart TD
    USER["Browser / mobile"]
    DNS["DNS"]
    LB["HTTPS Load Balancer + Cloud Armor<br/>optional for production"]
    FRONT["Cloud Run: orders-web<br/>Presentation"]
    API["Cloud Run: orders-api<br/>Business logic + IAM"]
    VPC["Custom VPC / subnet<br/>Direct VPC egress"]
    SQL["Cloud SQL for PostgreSQL<br/>Private IP"]
    SM["Secret Manager"]
    OBS["Cloud Logging / Monitoring"]
    ART["Cloud Build / Artifact Registry"]

    USER --> DNS --> LB --> FRONT
    FRONT -->|"HTTPS + ID token"| API
    API --> VPC --> SQL
    API --> SM
    API --> OBS
    FRONT --> OBS
    ART --> FRONT
    ART --> API
~~~

- **Web tier:** Cloud Run `orders-web` serves HTML/SSR and proxies API calls over server-side HTTPS. An External HTTPS Load Balancer with serverless NEGs is an optional production layer for custom domains, TLS, Cloud Armor, and routing.
- **Application tier:** Cloud Run `orders-api` runs Spring Boot. The service rejects unauthenticated invocations; only the frontend service account holds `roles/run.invoker`.
- **Data tier:** Cloud SQL for PostgreSQL on private IP. The backend uses Direct VPC egress and the Cloud SQL Java Connector (or a matching TLS/driver mechanism) to connect.

In a lab, you can test directly with Cloud Run URLs instead of a Load Balancer. In production, configure ingress/auth, WAF, TLS, and domains per corporate policy.

**Cloud Run Direct VPC egress is strictly for outbound traffic** from the service into the VPC—it does not give the service a private IP reachable via inbound TCP. The frontend calls the backend over HTTPS using a Google-signed ID token scoped to the target audience.

### Mandatory vs. Optional Components

| Service | Lab | Purpose |
|---|---|---|
| Project + billing | Mandatory | Scoping and billing |
| VPC + subnet | Mandatory | Private IP path |
| Cloud Run frontend/backend | Mandatory | Web and application tiers |
| Cloud SQL for PostgreSQL | Mandatory | Data tier |
| Artifact Registry | Mandatory | Container images |
| Secret Manager | Recommended | Credential management |
| Cloud Logging/Monitoring | Mandatory | Troubleshooting and alerting |
| DMS | Mandatory for CDC | Low-downtime data migration |
| Cloud VPN/Interconnect | Source-dependent | Hybrid connectivity |
| External HTTPS Load Balancer | Design-dependent | Domains, certificates, WAF |
| Terraform | Recommended | IaC and infrastructure review |

## 5. Preparing the Landing Zone and Separating Environments

Example project structure:

~~~text
orders-migration-sandbox
orders-migration-staging
orders-production
~~~

Each environment should isolate state, secrets, IAM, budgets, and networking. In larger enterprises, use a standard landing zone, Shared VPC, and organization policies instead of ad-hoc per-project VPCs.

| Resource | Example Name |
|---|---|
| Region | `asia-southeast1` |
| VPC | `orders-vpc` |
| Subnet | `orders-run-subnet` |
| Database instance | `orders-db` |
| Web service | `orders-web` |
| API service | `orders-api` |
| Artifact Registry repository | `orders` |
| Runtime service accounts | `orders-web-sa`, `orders-api-sa` |
| DMS job | `orders-postgres-migration` |

### 5.1. APIs to Enable

~~~bash
PROJECT_ID="orders-migration-staging"
REGION="asia-southeast1"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  compute.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  servicenetworking.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  datamigration.googleapis.com \
  --project="$PROJECT_ID"
~~~

This is the minimum set for the illustrative architecture; DNS, Load Balancing, VPN, or CI/CD may require additional APIs.

### 5.2. Runtime IAM

~~~bash
gcloud iam service-accounts create orders-web-sa \
  --display-name="Orders web runtime"

gcloud iam service-accounts create orders-api-sa \
  --display-name="Orders API runtime"
~~~

Grant least privilege:

| Principal | Appropriate Role | Why |
|---|---|---|
| `orders-web-sa` | `roles/run.invoker` on `orders-api` | Invoke authenticated backend |
| `orders-api-sa` | `roles/cloudsql.client` | Connect to Cloud SQL via Java Connector |
| `orders-api-sa` | `roles/secretmanager.secretAccessor` on specific secret | Read DB password if using built-in DB user |
| Build/deploy identity | Artifact Registry writer + build/deploy roles + scoped Service Account User | Publish images and Cloud Run revisions |
| DMS migration identity | DMS permissions and source DB replication user | Migrate database, separate from app runtime |

If using IAM database authentication, grant `roles/cloudsql.instanceUser` and configure matching IAM DB users and SQL `GRANT`s. Never grant Owner/Editor just so an app can reach the database.

## 6. Designing VPC and Private IP Connectivity

### 6.1. Create a Custom VPC and Subnet

~~~bash
gcloud compute networks create orders-vpc \
  --subnet-mode=custom

gcloud compute networks subnets create orders-run-subnet \
  --network=orders-vpc \
  --region="$REGION" \
  --range=10.60.10.0/24 \
  --enable-private-ip-google-access
~~~

Direct VPC egress requires a sufficiently large subnet—at least `/26` per Cloud Run docs. This lab uses `/24` to leave headroom for autoscaling and concurrent old/new revisions. Ensure CIDRs do not overlap with on-premises networks, other subnets, or Private Services Access ranges.

### 6.2. Prepare Private Services Access for Cloud SQL

For Cloud SQL private IP via Private Services Access, allocate an internal IP range and connect service networking. Run this example **only if the VPC is not yet configured**:

~~~bash
gcloud compute addresses create google-managed-services-orders-vpc \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="projects/$PROJECT_ID/global/networks/orders-vpc"

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-orders-vpc \
  --network=orders-vpc \
  --project="$PROJECT_ID"
~~~

Never arbitrarily delete or alter shared peering: Cloud SQL and other services may actively depend on it. In production, the network team typically manages this via IaC.

This lab has DMS create a **new Cloud SQL destination**. Once private service connectivity is ready, select the network and region in the DMS wizard. Do not pre-create an instance with the same name via `gcloud sql instances create` if DMS will provision the destination.

### 6.3. Hybrid Connectivity

| Option | When to Use | Notes |
|---|---|---|
| Cloud VPN | Testing or moderate hybrid traffic | IPsec, routing, HA |
| Dedicated/Partner Interconnect | High throughput, enterprise network SLAs | Requires circuits, BGP, and redundancy |
| DMS connectivity method | Depends on engine and source environment | May use private connectivity, allowlisting, or reverse SSH |

Choose the exact connectivity method DMS supports for your source. Never open TCP `5432` to the entire Internet to quickly work around a migration error. Verify firewalls, routes, DNS, and authentication for the chosen method.

## 7. Preparing the Application for Cloud Run

Cloud Run fits stateless services. Remove host-bound state dependencies:

| Current State | Change |
|---|---|
| HTTP sessions in RAM / local NGINX | Stateless tokens or shared session store |
| File uploads written to local disk | Cloud Storage or appropriate storage |
| Cron/background jobs on VM | Cloud Scheduler, Cloud Tasks, or Cloud Run Jobs |
| Hardcoded DB host/IP | Environment variables and Secret Manager |
| TLS cert inside container | Terminate TLS at Cloud Run / load balancer |
| Local log files | Structured logs to stdout/stderr |
| Returning HTTP response before finishing background work | Offload work to a durable queue |
| Outbound APIs requiring IP allowlists | Configure VPC egress/NAT/static IP as needed |

**Do not refactor into microservices in the same cutover.** Package the existing app, preserve behavior, pass regression tests, and optimize later.

### 7.1. Sample Backend Dockerfile

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/orders-api.jar app.jar

ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The Spring Boot app must listen on `0.0.0.0` and the Cloud Run-provided port. Sample Spring settings or environment overrides:

~~~properties
server.port=${PORT:8080}
management.endpoints.web.exposure.include=health,info
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.connection-timeout=10000
~~~

These are sample parameters; in production, `server.port` should bind the `PORT` environment variable or equivalent Spring Boot configuration. Never bake passwords into images or Dockerfiles.

## 8. Deploying the Backend to Cloud Run

Example image URIs (assuming images are already built and pushed):

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/orders/orders-api:v1
asia-southeast1-docker.pkg.dev/PROJECT_ID/orders/orders-web:v1
~~~

### 8.1. Database Connectivity

Assume the Cloud SQL destination has:

~~~text
INSTANCE_CONNECTION_NAME=PROJECT_ID:asia-southeast1:orders-db
DB_NAME=orders
DB_USER=orders_runtime
~~~

For Spring Boot JDBC using the Cloud SQL Java Connector:

~~~properties
spring.datasource.url=jdbc:postgresql:///orders?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE&cloudSqlRefreshStrategy=lazy&sslmode=disable
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
~~~

The app reads `DB_PASSWORD` injected via Secret Manager rather than hardcoding it. The socket factory requires pgJDBC and a matching Cloud SQL PostgreSQL Socket Factory dependency. On the **connector path**, TLS is managed by the connector itself, which is why `sslmode=disable` appears at the pgJDBC layer; never set `sslmode=disable` when connecting to PostgreSQL directly over raw IP without equivalent TLS.

Before promoting the DMS destination, never run API tests that `INSERT`/`UPDATE` into the actively replicating database. Use a separate staging database or strictly controlled read-only checks.

### 8.2. Example Deployment Command

~~~bash
API_SA="orders-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
API_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders/orders-api:v1"

gcloud run deploy orders-api \
  --image="$API_IMAGE" \
  --region="$REGION" \
  --service-account="$API_SA" \
  --no-allow-unauthenticated \
  --ingress=all \
  --network=orders-vpc \
  --subnet=orders-run-subnet \
  --vpc-egress=private-ranges-only \
  --set-env-vars="INSTANCE_CONNECTION_NAME=$PROJECT_ID:$REGION:orders-db,DB_NAME=orders,DB_USER=orders_runtime" \
  --set-secrets="DB_PASSWORD=orders-db-password:latest" \
  --max-instances=5
~~~

Prerequisites: the secret exists with `secretAccessor` granted to the API SA; the Cloud SQL target exists; the image is pushed; the runtime identity holds Cloud SQL Client; and the network/subnet are in the same region. The command sets `--ingress=all` yet **blocks unauthenticated invocation**; IAM still rejects any caller lacking `run.invoker`. If your environment requires stricter network ingress, design an internal ingress route rather than copying the example verbatim.

### 8.3. Connection Pool Budget

Each Cloud Run instance maintains its own pool. With 5 max instances and Hikari `maximumPoolSize=5`, up to roughly 25 physical connections may be needed, excluding migration tools, consoles, and other workloads.

\[
\text{Connection budget} \approx \text{Max Cloud Run instances} \times \text{Pool size}
\]

Do not raise pool sizes indefinitely when hitting timeouts. Inspect Cloud SQL active connections, slow queries, CPU, locks, and pool acquire wait times.

## 9. Deploying the Frontend and Service-to-Service IAM

The frontend is a public Cloud Run web service calling the backend with a Google-signed ID token. Browsers must never receive the service account ID token.

### 9.1. Grant Backend Invocation Permission

~~~bash
WEB_SA="orders-web-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding orders-api \
  --region="$REGION" \
  --member="serviceAccount:$WEB_SA" \
  --role="roles/run.invoker"
~~~

### 9.2. Generating an ID Token in the Frontend Server

Example Node.js web server using `google-auth-library`:

~~~javascript
const {GoogleAuth} = require("google-auth-library");
const auth = new GoogleAuth();
const backendUrl = process.env.BACKEND_URL;

async function fetchOrders() {
  const client = await auth.getIdTokenClient(backendUrl);
  const response = await client.request({
    url: backendUrl + "/api/orders",
    method: "GET"
  });
  return response.data;
}
~~~

`getIdTokenClient` creates a client that fetches an ID token scoped to the Cloud Run backend audience. Browsers receive data only through the frontend; end-user authentication and authorization at the application layer must still enforce business rules.

### 9.3. Deploy the Web Service

~~~bash
API_URL=$(gcloud run services describe orders-api \
  --region="$REGION" \
  --format="value(status.url)")

WEB_IMAGE="asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders/orders-web:v1"

gcloud run deploy orders-web \
  --image="$WEB_IMAGE" \
  --region="$REGION" \
  --service-account="$WEB_SA" \
  --allow-unauthenticated \
  --set-env-vars="BACKEND_URL=$API_URL" \
  --max-instances=5
~~~

`--allow-unauthenticated` is appropriate only for public websites. For employee-only apps, enforce authentication/IAP or policy-compliant ingress. In production, place the frontend behind an HTTPS Load Balancer with a serverless NEG and Cloud Armor.

## 10. Migrating PostgreSQL with Database Migration Service

DMS continuous migration combines an **initial load** of existing data with **change data capture** to sync ongoing mutations while the source remains writable. This shrinks cutover downtime, though source writes must still freeze in the final step.

~~~mermaid
flowchart LR
    SRC["On-prem PostgreSQL<br/>Primary / writes"] --> SNAP["Initial load"]
    SRC --> WAL["Logical replication / WAL"]
    SNAP --> DMS["DMS migration job"]
    WAL --> DMS
    DMS --> DST["Cloud SQL PostgreSQL<br/>Destination / no app writes"]
    DST --> PROMOTE["Write freeze → lag near 0 → promote"]
    PROMOTE --> API["Cloud Run Orders API"]
~~~

### 10.1. Source Checks

Before starting a job, ensure the source is supported, backups have passed restore tests, the replication user holds required privileges, `pg_hba.conf` and firewalls allow access, WAL and connection capacity suffice, and schemas/extensions are checked.

Diagnostic queries:

~~~sql
SHOW server_version;
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW max_worker_processes;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

For **standard continuous migration** of self-managed PostgreSQL, DMS requires logical replication/`pglogical`, a migration user, and properly sized replication slots/WAL senders. Changing WAL parameters may require restarting PostgreSQL; never do so on production without an approved maintenance window.

### 10.2. Schema Checks

| Item | Risk | Mitigation |
|---|---|---|
| Tables without primary keys | `UPDATE`/`DELETE` may not replicate in standard `pglogical` mode | Add PKs or pick a mode supporting `REPLICA IDENTITY` |
| Extensions | Cloud SQL does not support every extension | Cross-check allowed extensions and test |
| Schema DDL | Ordinary DDL does not auto-replicate in standard flow | Freeze schemas or follow supported workflows |
| Sequences | Post-migration values may need alignment | Check `MAX(id)`, `last_value`, ownership |
| Roles/GRANTs | Permissions differ on destination | Inventory, recreate, and test |
| Time zones/collations | Comparison/sort order may differ | Run contract/golden queries |
| Long transactions/WAL | CDC lag spikes and prolonged WAL retention | Monitor replication slots, lag, disk |
| Large objects | Support depends on migration method | Test against DMS known limitations |

DMS also offers a quick-start mode using `pgnative` with behaviors differing from standard `pglogical`. **Do not mix requirements across the two modes**; this lesson illustrates standard continuous migration.

### 10.3. Creating the Job via Console

1. Open **Database Migration Service → Migration jobs**.
2. Choose PostgreSQL source and Cloud SQL for PostgreSQL destination.
3. Choose **Continuous** migration type.
4. Create the source connection profile and migration user.
5. Select **new Cloud SQL destination instance**, region, VPC, and private IP.
6. Configure connectivity from the migration service/destination to the source.
7. Click **Test job** and resolve all errors before starting.
8. Start the migration job; monitor initial load, CDC lag, source WAL, and the destination.

DMS is regional; connection profiles, migration jobs, and destinations must align on region. While DMS provisions and populates the destination, avoid running DDL/DML against migrating data to prevent conflicts.

Query job status:

~~~bash
gcloud database-migration migration-jobs list \
  --region="$REGION" \
  --project="$PROJECT_ID"

gcloud database-migration migration-jobs describe orders-postgres-migration \
  --region="$REGION" \
  --project="$PROJECT_ID"
~~~

Never start cutover if initial load is incomplete or CDC lag is rising.

### 10.4. Protecting the Destination Database

During standard continuous migration:

- The destination may be technically writable, yet **never allow apps or batches to write to replicated tables**.
- Use strictly controlled reads or an isolated staging database during tests.
- Automated backups/PITR may be paused while migrating to a new destination; re-enable and verify them immediately after promotion.
- Do not add read replicas to the destination until promotion succeeds.
- DMS may adjust Cloud SQL settings; if using Terraform, reconcile configuration drift **after** migration rather than overwriting settings mid-CDC.

## 11. Testing Data and Application Behavior

### 11.1. Data Comparison

Sample queries:

~~~sql
SELECT COUNT(*) AS orders_count,
       MIN(created_at) AS earliest_order,
       MAX(created_at) AS latest_order
FROM public.orders;

SELECT status, COUNT(*) AS total
FROM public.orders
GROUP BY status
ORDER BY status;

SELECT COUNT(*) AS customers_count
FROM public.customers;
~~~

Counting rows at two unaligned timestamps while the source takes writes **does not prove consistency**. Compare only on a consistent snapshot or after write freeze with CDC lag near 0. Also reconcile batch/PK checksums, daily order totals, business statuses, and domain edge cases.

### 11.2. Application Test Suite

| Category | Test Case | Criterion |
|---|---|---|
| API | `GET /health`, `GET /api/orders` | 2xx and valid schema |
| Auth | User lacking required role | 401/403 with zero data leak |
| Business | Create, update, cancel order | Accurate transactions/audits |
| Idempotency | Duplicate request key | Never creates two orders |
| Data | Counts, totals, statuses, sample IDs | Matches snapshot |
| Performance | Peak-hour load test | P95/P99 meet SLO |
| Reliability | Staging DB failover | Bounded retries, zero lost transactions |
| Security | IAM, Secret Manager, egress, TLS | PASS |
| Observability | Logs, metrics, traces | Root cause traceable |

Before promotion, run write tests only against an **isolated staging DB**, never against the DMS destination undergoing CDC.

### 11.3. Supporting Integrations

If the app integrates with payment gateways or email, point staging to sandbox endpoints and synthetic data. Verify IP allowlists, SMTP egress, DNS, timeouts, and credentials after moving workloads. Never send real emails or process real payments during migration rehearsals.

## 12. Dashboards, Baselines, and Alerts

Build dashboards before cutover:

| Signal | Source | Meaning |
|---|---|---|
| HTTP requests / 4xx / 5xx | Cloud Run / Load Balancer | Traffic and error rates |
| P50/P95/P99 latency | Monitoring / traces | SLO health |
| Cloud Run instance count | Cloud Run | Autoscaling and cold starts |
| DB CPU, memory, connections | Cloud SQL | Capacity |
| Slow queries / lock waits | Cloud SQL Query Insights | Bottlenecks |
| DMS replication lag | Database Migration Service | Source → target delay |
| Source PostgreSQL WAL/disk | On-prem metrics | Disk exhaustion risk |
| Secret/permission errors | Cloud Audit Logs / app logs | IAM regressions |
| Budget alerts | Cloud Billing | Migration spend |

Tag logs with environment, version, image digest, and release ID to correlate source and target behavior. Never log passwords, tokens, or customer data.

## 13. Cutover Rehearsal and Go/No-Go Criteria

A cutover runbook requires accountable owners, explicit steps, commands, verification evidence, and abort conditions. Rehearse in staging with a representative dataset first.

### 13.1. DNS and Load Balancers

Lower DNS TTL **ahead** of the maintenance window per policy. Low TTL does not guarantee every cache/client switches instantly; keep-alive connections and proxies may stick to old IPs. If using a global HTTPS Load Balancer, configure serverless NEGs, certificates, URL maps, and Cloud Armor upfront and validate with a staging hostname.

### 13.2. Roles

| Role | Responsibility |
|---|---|
| Migration lead | Go/No-Go decision |
| Database lead | Source freeze, CDC lag, DMS promote |
| App lead | Cloud Run revisions, smoke tests |
| Network/DNS lead | LB/DNS/TLS and connectivity |
| Security lead | IAM, secrets, audits, WAF |
| Business owner | Validates order flows and data accuracy |

### 13.3. Go Criteria

- DMS initial load complete; CDC stable.
- Replication lag below threshold and trending down.
- Backups/source recovery point restore-verified.
- Image digests and test results approved.
- IAM, private SQL path, secrets, metrics/alerts PASS.
- Users notified of the maintenance window.
- Phased rollback runbook approved.

Do not call Go if WAL grows uncontrollably, unresolved DMS errors exist, or no plan covers new writes on the destination.

## 14. Production Cutover Runbook

| Milestone | Action | Evidence |
|---|---|---|
| T-30 min | Verify DMS, DB, images, DNS, secrets, dashboards | Go/No-Go |
| T-10 min | Stop batches, schedulers, integration writers | Logs and job states |
| T0 | Put source app in maintenance/read-only; freeze all source writes | Zero active write transactions |
| T+ | Wait for open transactions to drain and CDC lag near 0 | DMS metrics, SQL checks |
| T+ | **Promote** DMS migration job | Job and Cloud SQL status healthy |
| T+ | Verify users, GRANTs, sequences, schemas, backups/PITR | SQL + Cloud SQL settings |
| T+ | Route Cloud Run production revision, verify SQL connectivity | Health and logs |
| T+ | Switch frontend/LB/DNS per plan | Request logs |
| T+ | Smoke-test GET, authenticated POST, idempotency | Business sign-off |
| T+ | Monitor P95/5xx/DB connections during hypercare | Dashboard |
| T+N days | Decommission source after approval/retention | Handover |

**At T0, block every writer**, not just the web frontend. Queue consumers, cron jobs, ETL pipelines, admin tools, and partner integrations may still write directly to PostgreSQL.

### 14.1. DMS Promotion

In the Console, select the job in CDC phase, confirm lag is drained, and click **Promote**. Promotion disconnects the destination from the source and turns Cloud SQL into an independent primary.

DMS allows promoting while lag is non-zero, yet doing so risks losing recent changes. This lab enforces No-Go if lag has not caught up, unless the business owner explicitly approves a different RPO.

After promotion:

- Test read/write queries and DB privileges on Cloud SQL.
- Verify schemas, sequences, extensions, and migration version tables.
- Re-enable or confirm automated backups/PITR and retention.
- Reconcile Terraform drift if DMS temporarily altered Cloud SQL flags/settings.
- Confirm a fresh recovery point exists.

### 14.2. Shifting Traffic

Traffic splitting across Cloud Run revisions is safe only when all active revisions target the same valid primary database with compatible schemas. **Never run two primaries accepting concurrent writes.**

For database migrations, switch write authority once upon promotion; the frontend can still roll out via canary groups and ramp up. While DNS caches still send trickle traffic to the old source, keep the source app in read-only or maintenance mode so stale writes never land on the retired database.

## 15. Rollback Before and After Target Writes

Rollback is not just flipping DNS. Once promoted, DMS replication from source to target has ended. If Cloud SQL has accepted new orders, the old source PostgreSQL **does not have those transactions**.

### Case A: Target Has Accepted Zero Writes

1. Hold maintenance mode or block traffic.
2. Confirm the source can still accept writes cleanly without external tampering.
3. Point connections/frontend/LB back to the source per runbook.
4. Reopen source writes once single-primary authority is confirmed.
5. Record the rollback timestamp and root cause.

### Case B: Target Has Accepted New Writes

**Do not flip DNS straight back to the old source.** Pre-designed options are:

- Halt writes on the target; export and reconcile new transactions by business key and transaction ID.
- Execute a separately designed and tested compatible reverse-sync pipeline (complex).
- Prefer **fix-forward** if Cloud SQL is already the source of truth: roll back or patch the Cloud Run revision/config or restore service on the target.

The database lead and business owner must approve the choice, preserving required RPO even if RTO extends.

| Incident | Priority Action | Risk |
|---|---|---|
| Frontend bug, DB healthy | Roll back Cloud Run web revision | Low |
| API code bug, schema still compatible | Roll back API revision | Low/moderate |
| Incompatible schema issue | Freeze writes, evaluate fix-forward | High |
| Cloud SQL IAM/network error, zero writes | Fix config or roll back to source | Potentially low |
| Cloud SQL already accepted new writes | Reconcile/reverse sync or fix-forward | High if DNS is simply flipped back |
| CDC lag not near 0 before cutover | Do not Go | Prevents data loss |

## 16. Acceptance and Hypercare

### Technical Gates

- Frontend/backend run in the expected project and region.
- HTTPS, IAM, authorization, and ingress match design.
- Cloud SQL serves as the **sole primary** over private connectivity.
- Data reconciles via SQL queries and business aggregates.
- Database users, GRANTs, sequences, and extensions are valid.
- P95/5xx sit within SLOs with zero abnormal connection spikes.
- Audit logs, metrics, traces, and alerts emit telemetry.
- Cloud SQL backups, PITR, and restore procedures are verified.
- DR runbooks and ownership records are updated.

### Business Gates

1. Log in as an authorized user.
2. Place a new order.
3. View the order from a second session.
4. Update/cancel an order according to role permissions.
5. Verify invoices, inventory, notifications, and payment sandbox callbacks.
6. Confirm summary reports reflect new transactions.
7. Confirm zero duplicate orders from retries or cutover.

During 24–72 hours of hypercare (duration set by the organization), monitor P95 latency, 5xx errors, DB CPU/connections, slow queries, autoscaling, spend, and user feedback. Decommission the source only after business sign-off, backup retention, and zero remaining dependencies.

## 17. Migration Security and Cost

### 17.1. Security

- Enforce least-privilege IAM, separating web, API, deploy, and migration service accounts.
- Use ID tokens and `roles/run.invoker` for service-to-service calls; never leak tokens to browsers.
- Use Cloud SQL private IP, dedicated database users, and Secret Manager.
- Secure ingress/egress; place Cloud Armor in front of public websites needing WAF.
- Audit-log IAM, database, promotion, deployment, and break-glass actions.
- Enforce data residency, retention, and TLS/encryption per compliance rules.

### 17.2. Cost

| Service | Cost Drivers |
|---|---|
| Cloud Run | CPU/memory, requests, min instances, concurrency |
| Cloud SQL | Machine size, HA, storage, backups, networking |
| Artifact Registry | Storage, data transfer |
| Load Balancing/Cloud Armor | Policies, rules, traffic |
| DMS | Migration service, destination DB, connectivity |
| Cloud VPN/Interconnect | Tunnels/gateways/circuits |
| Cloud Logging/Monitoring | Ingestion, retention, custom metrics |
| Data transfer | Egress, hybrid, cross-region traffic |

Set budget alerts before migrating. Costs rise temporarily during parallel source/target operation, initial load, performance testing, and hypercare. Do not dangerously downsize Cloud SQL ahead of cutover just to trim cost.

## 18. Common Hands-On Pitfalls

| Symptom | Cause | Remediation |
|---|---|---|
| DMS Test job fails | Wrong user, `pg_hba.conf`, route, port, or TLS | Check connection profile and replication privileges |
| CDC lag climbs | Heavy WAL, long transactions, network bottleneck | Inspect source WAL, slots, lag, bandwidth |
| Missing `UPDATE`/`DELETE` at sink | Table lacks primary key in standard mode | Add PK or switch to a supported replication strategy |
| DMS replication conflict | App/batch wrote to the destination | Stop target writers, analyze, and recover job |
| Extension mismatch | Unsupported on Cloud SQL | Check allowed extensions list |
| Cloud Run API returns 403 | Missing invoker role or wrong ID token audience | Check web SA and backend IAM |
| API cannot reach Cloud SQL | Wrong VPC, peering, egress, or permissions | Check networking/roles and connector |
| API returns 500 | Missing secret, DB user/GRANT, or schema mismatch | Inspect logs and SQL errors |
| DB runs out of connections | Per-instance Cloud Run pool too large | Calculate instances × pool; tune queries/capacity |
| Custom domain fails | Wrong DNS/LB/TLS/NEG | Check TTL, certificates, backend mappings |
| Traffic still hits source | DNS caching / keep-alive | Keep source read-only; watch access logs |
| Rollback after target writes | Missing reverse sync | Freeze writes, fix-forward, or reconcile |

## 19. Handover Checklist

- [ ] Inventory, dependency graph, and owners are complete.
- [ ] CPU/memory/request/DB/P95 baselines and RTO/RPO are approved.
- [ ] Source backups passed restore tests.
- [ ] Rehost/replatform choice matches workload compatibility.
- [ ] Projects, VPC, CIDRs, and VPN/Interconnect (if needed) are ready.
- [ ] Cloud SQL private IP, source link, and DMS connectivity PASS.
- [ ] IAM service accounts are separated by function.
- [ ] Images are built, tested, scanned, and recorded by digest.
- [ ] Web service invokes API with ID tokens; backend blocks unauthenticated calls.
- [ ] Secret Manager, DB users, and GRANTs are valid.
- [ ] Initial load completed and CDC lag is stably monitored.
- [ ] Zero writes hit the DMS destination during CDC.
- [ ] Unit/integration/E2E/load tests PASS in staging.
- [ ] Data counts, checksums, roles, and sequences are reconciled.
- [ ] DNS/TLS/LB and maintenance mode are tested.
- [ ] Cutover runbook defines Go/No-Go gates and owners.
- [ ] Every source writer is frozen prior to promotion.
- [ ] CDC lag is near 0 before promotion.
- [ ] Cloud SQL backups/PITR are verified post-promotion.
- [ ] Production smoke tests and business sign-off PASS.
- [ ] Hypercare monitoring, incident runbooks, and budget alerts are active.
- [ ] Source is decommissioned only after retention and approval.

## 20. Self-Check Questions

**1. Why not just move the two web VMs to the cloud and leave PostgreSQL on-premises permanently?**

App-to-DB latency across VPN can spike, hybrid links add failure modes, and cutover remains incomplete. That setup is viable only as an intentional choice backed by measured performance and risk analysis.

**2. How does rehost differ from replatform?**

Rehost moves VMs to Compute Engine with minimal code changes; replatform adopts Cloud Run/Cloud SQL, reducing OS management while requiring containerization, externalized state, IAM, and VPC connectivity.

**3. What does DMS continuous migration provide?**

Initial load followed by CDC keeps the target caught up with writes while the source runs, shrinking cutover transfer volume. However, you still need a write freeze, near-zero lag, and promotion.

**4. Why must you not write to the Cloud SQL destination during CDC?**

The source is still primary. Destination writes can conflict with DMS, causing replication errors or data divergence.

**5. May the frontend pass its service account ID token into JavaScript sent to the browser?**

No. The frontend server calls the backend using its own ID token and `roles/run.invoker`. Browsers receive only responses and data authorized for the end user.

**6. To achieve near-zero RPO, which condition matters most?**

Stop every source writer, wait for CDC to catch up, verify consistency, and only then promote. Simply enabling DMS does not guarantee RPO=0.

**7. Why can rolling back DNS lose orders after promotion?**

The old source lacks transactions committed at the target after cutover. You need reconciliation, tested reverse sync, or fix-forward.

## 21. References

- [Google Cloud Migration Center](https://cloud.google.com/migration-center/docs/migration-center-overview)
- [Migrate to Virtual Machines overview](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/overview)
- [Migrate individual VMs: lifecycle, test-clone, cutover](https://cloud.google.com/migrate/virtual-machines/docs/5.0/migrate/migrating-vms)
- [Database Migration Service for PostgreSQL overview](https://cloud.google.com/database-migration/docs/postgres/overview)
- [DMS PostgreSQL: Configure source](https://cloud.google.com/database-migration/docs/postgres/configure-source-database)
- [DMS PostgreSQL: Create migration job](https://cloud.google.com/database-migration/docs/postgres/create-migration-job)
- [DMS PostgreSQL: Known limitations](https://cloud.google.com/database-migration/docs/postgres/known-limitations)
- [DMS PostgreSQL: Promote migration](https://cloud.google.com/database-migration/docs/postgres/promote-migration)
- [Cloud SQL: Configure private services access](https://cloud.google.com/sql/docs/postgres/configure-private-services-access)
- [Cloud SQL: Connect from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud Run: Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Cloud Run: Service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [External Application Load Balancer](https://cloud.google.com/load-balancing/docs/https)
- [Cloud VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
