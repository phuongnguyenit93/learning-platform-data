# Three-Tier Web Application Architecture on Google Cloud

In the `CLOUD_PROVIDERS_GCP` module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners practice selecting services, protecting resources, automating releases, and monitoring reliability alongside cost. The **GCP Architecture Design** chapter connects these skills into a design that can be deployed, verified, and operated.

This lesson designs a **three-tier web application** using an order management system as an example. The reference architecture uses an **External Application Load Balancer**, **Cloud Run** for the presentation and application tiers, and **Cloud SQL for PostgreSQL** for the data tier. The design prioritizes new workloads of small to medium scale where the operations team wants to minimize server administration. You will also learn when to switch to GKE, Compute Engine, or other services.

## 1. What Are the Three Tiers and Why Separate Them?

The three tiers are three **logical responsibilities**, not necessarily three separate virtual machines or three separate VPCs:

| Tier | Responsibility | What Not to Do |
| --- | --- | --- |
| **Presentation (web/UI)** | Serve HTML, CSS, JavaScript; display data; collect input; manage user session experience. | Embed database passwords, let the browser connect directly to the database, or enforce business authorization solely in the UI. |
| **Application (business/API)** | Enforce user authentication/authorization; validate input; execute use cases, transactions, and downstream calls; expose APIs. | Trust browser input; store sessions or business state solely in a single instance's memory. |
| **Data (persistence)** | Store, query, ensure consistency, and recover data. | Expose database ports directly to the Internet; grant administrative SQL privileges to public browsers or frontends. |

Separating tiers delivers four primary benefits:

1. **Clear trust boundaries:** users only reach web/API endpoints; database privileges are granted only to the backend.
2. **Independent scaling:** web scales with static asset traffic; API scales with request volume; the database has its own connection, CPU, storage, and replica strategy.
3. **Independent deployment and maintenance:** UI changes do not necessarily require schema migrations; database upgrades do not force frontend changes.
4. **Observability and cost control:** each tier has appropriate metrics, owners, SLOs, service accounts, and resource sizing.

A system with three packages in a single process can still achieve logical layering, but lacks independent deployment. Conversely, three independently deployed services that share all credentials and directly access the database still have weak security boundaries.

## 2. Reference Architecture on Google Cloud

### 2.1. Overall Diagram

~~~mermaid
flowchart TB
    USER[Browser / Mobile client]
    DNS[Cloud DNS / domain]
    LB[Global external Application Load Balancer\nHTTPS + managed certificate]
    ARMOR[Cloud Armor security policy]
    WEB[Cloud Run web-frontend\nPresentation tier]
    API[Cloud Run orders-api\nApplication tier]
    VPC[Direct VPC egress\nPrivate subnet]
    SQL[(Cloud SQL PostgreSQL\nPrivate IP + HA option)]
    SECRET[Secret Manager]
    OBS[Cloud Logging / Monitoring / Trace]
    ART[Artifact Registry / CI/CD]

    USER --> DNS
    DNS --> LB
    LB --- ARMOR
    LB -->|path: / and static files| WEB
    LB -->|path: /api/*| API
    API --> VPC
    VPC --> SQL
    API -->|runtime IAM| SECRET
    ART -.-> WEB
    ART -.-> API
    WEB -.-> OBS
    API -.-> OBS
    SQL -.-> OBS
    LB -.-> OBS
~~~

**Primary request path:** the browser accesses `https://shop.example.com` via the HTTPS Load Balancer. The URL map routes `/` and web assets to `web-frontend`, and `/api/*` to `orders-api`. The two Cloud Run services are attached to two separate **serverless network endpoint groups (NEGs)** and two load balancer backend services. Only `orders-api` needs connectivity to Cloud SQL over private IP.

In this design, the frontend and API sit **behind the same hostname**. The browser calls the API via the `/api` path on the same origin, reducing CORS configuration and keeping cookies/sessions consistent. By default, URL maps preserve the path when forwarding; if the backend only serves `/orders`, you must configure a URL rewrite or have the API serve `/api/orders`.

### 2.2. Role of Each Service

| Google Cloud Component | Tier / Role | Architectural Decision |
| --- | --- | --- |
| **Cloud DNS** or external DNS provider | Points domain to the load balancer IP. | DNS only resolves names; it is not a firewall or authentication mechanism. |
| **Global external Application Load Balancer** | HTTPS entry point; URL map, managed certificates, routing. | Choose when a shared domain, Cloud Armor, and multi-backend routing are needed. |
| **Serverless NEGs** | Connects LB backend services to Cloud Run. | Each NEG points to a Cloud Run service in the corresponding region. |
| **Cloud Armor** | WAF rules, rate limiting, blocking suspicious patterns at the edge. | An additive layer; does not replace business authorization checks. |
| **Cloud Run `web-frontend`** | Presentation tier, SSR or serving SPA assets. | Stateless; avoid storing sessions solely in RAM. |
| **Cloud Run `orders-api`** | Application tier, REST/GraphQL, order logic. | Uses a dedicated service account, concurrency/instances tuned to load. |
| **Direct VPC egress** | Outbound path from the API to private addresses. | Cloud Run services support **egress** via Direct VPC, without becoming a VM inside the VPC. |
| **Cloud SQL for PostgreSQL** | Data tier with transactions and managed operations. | Private IP, backups, PITR, regional HA when needed. |
| **Secret Manager** | Stores DB passwords or sensitive configs. | Grants only the API runtime SA access to the specific secret; avoid hardcoding. |
| **Artifact Registry + Cloud Build/CI** | Builds and stores images, deploys revisions. | Pin image digests, review changes, and execute controlled rollouts. |
| **Cloud Logging / Monitoring / Trace** | Observes requests, errors, latency, database, and cost. | Correlation/alerts reflecting user experience. |

Not every application needs to run its frontend on Cloud Run. If the UI is a purely static SPA, you can host assets in **Cloud Storage + Cloud CDN** and keep Cloud Run solely for the API. In that case, the presentation tier is distributed as static content rather than a separately running web process.

## 3. Request Flows and Trust Boundaries

### 3.1. Reading the Order List

Example sequence of a request:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant L as HTTPS Load Balancer
    participant W as Cloud Run Frontend
    participant A as Cloud Run API
    participant D as Cloud SQL
    B->>L: GET /orders (HTTPS)
    L->>W: Forward UI request
    W-->>B: HTML/JS/CSS
    B->>L: GET /api/orders (cookie/session)
    L->>A: Forward original path
    A->>A: Authenticate + authorize user
    A->>D: Parameterized SELECT (private TCP)
    D-->>A: Rows
    A-->>B: JSON response
~~~

**Never** embed database credentials in JavaScript sent to the browser. The browser sends end-user session/token credentials; the API authenticates the user identity, checks authorization for each order, and only then runs SQL. The Cloud Run service account is used to call Google Cloud APIs; **it does not by itself determine which user may view an order**.

### 3.2. Writing an Order

The `POST /api/orders` flow should include:

1. Validating the login session, CSRF if using cookies in an applicable context, order creation permissions, and input payloads.
2. Generating an idempotency key or using a request identifier to prevent duplicate orders on browser retries.
3. Opening a short database transaction, writing the order and related line items, and committing.
4. Returning `201 Created` with the ID after commit.
5. If emails or inventory sync are needed, enqueue asynchronous work into Pub/Sub/Cloud Tasks via a reliable mechanism such as the **transactional outbox**; never hold a SQL transaction open while calling external services.

When using Pub/Sub, the system begins expanding into an event-driven architecture while retaining the three core tiers. Event processing should be idempotent because messages can be redelivered.

### 3.3. Public Endpoint Does Not Mean Public Database

The load balancer and web/API may accept Internet traffic per product policy, but:

- Cloud SQL has only a private IP and is not directly reachable from the browser.
- Only the API may connect to the private DB.
- The API runtime service account receives only necessary permissions, not user or deployer credentials.
- The UI has no permission to read DB secrets.
- The application tier must still enforce authorization per resource/tenant.

Network design, IAM, and application authorization are distinct layers; missing one layer cannot be compensated for by another.

## 4. Designing Ingress, Load Balancing, and Caching

### 4.1. Global External Application Load Balancer

An external Application Load Balancer can provide:

- A global external IP and the website's domain.
- HTTPS termination with Google-managed certificates.
- Host/path-based URL maps to route `/api/*` to the API and other paths to the frontend.
- Cloud Armor policies on backend services.
- Cloud CDN for cacheable content.
- Multi-region expansion capabilities, with additional backend and traffic policy configuration.

To use Cloud Run as a backend, create a **serverless NEG** pointing to each service and attach the NEG to a backend service. Serverless NEGs **do not use backend service health checks in the same way VM/GKE NEGs do**. Use synthetic checks, Cloud Run service health / outlier detection when supported by the chosen load balancer, along with Monitoring/alerting. Do not attempt to attach a health-check resource to a backend service containing only serverless NEGs.

### 4.2. Preventing Bypass via the Cloud Run URL

Cloud Run has its own `run.app` URL. If the service still allows ingress from all sources, users can call this URL directly and **bypass Cloud Armor/LB**.

For a backend behind an external Application Load Balancer, configure Cloud Run `ingress=internal-and-cloud-load-balancing`. This setting allows traffic from the external Application Load Balancer and valid internal sources while blocking direct Internet access to `run.app`. You may consider disabling the default `run.app` URL when certain that no Cloud Tasks, Scheduler, Pub/Sub push, or other services need to call it; disabling the URL carries integration implications that must be verified.

Cloud Run Invoker IAM and ingress settings are **distinct**: if the website is open to the public via the LB, you must permit that HTTP invocation at the Cloud Run IAM layer (e.g., organization-approved public invocation), or use Identity-Aware Proxy (IAP) / an appropriate authentication model. Even when Cloud Run allows unauthenticated invocation at the infrastructure layer, the API must still authenticate and authorize **end users** inside the application.

### 4.3. Caching and HTTP Headers

| Content | Recommended Cache | Reason |
| --- | --- | --- |
| JS/CSS/assets with content hashes in filenames | `public, max-age=31536000, immutable` if assets are truly immutable | Leverages CDN and browser caching without risking stale content under the same URL. |
| Frequently updated HTML entrypoint | `no-cache` or short TTL | Clients receive new frontend versions quickly. |
| `GET /api/catalog` public data | Short TTL cacheable when invalidation is clearly designed | Reduces requests hitting API and DB. |
| `/api/orders`, profiles, per-user carts | `private, no-store` when containing sensitive data | Prevents shared caching across users. |
| Responses with `Set-Cookie` or authorization | Cache only with carefully designed cache keys and policies; do not publicly cache by default | Prevents leaking session/tenant data. |

Cloud CDN does not automatically know which responses contain personal data. Cache modes, TTLs, request/response headers, and URL routing must be verified using requests from two different users. A misconfigured cache leak is usually far worse than a slow webpage.

## 5. Application Tier: Cloud Run API

### 5.1. Stateless Service and Scaling

`orders-api` should be a stateless container capable of serving multiple concurrent requests and self-healing by spinning up new instances.

- Store sessions in signed/encrypted cookies or an external session store (if server-side sessions are required), never only inside a single instance.
- Large uploads should go directly to Cloud Storage via appropriate signed URLs, avoiding holding huge byte arrays in API RAM.
- CPU/memory, request concurrency, min/max instances, request timeouts, and startup times should be tuned via load testing.
- Accept only validated and size-bounded inputs, especially for JSON, files, and query pagination.

Cloud Run can automatically scale up instances under load, but it does not automatically increase Cloud SQL's connection limit. If each instance opens a large connection pool, total connections can overwhelm the DB.

### 5.2. Controlling Database Connections

Suppose the API is capped at 20 max instances and each instance has a pool of 5 connections:

\[
\text{Max DB connections created by API} \approx 20 \times 5 = 100
\]

This is the theoretical ceiling of the **application pool**, excluding migration jobs, admin sessions, replicas, or other services. Never configure `max instances × max pool size` above the number of connections the database can safely serve.

With Spring Boot + HikariCP, for example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://PRIVATE_DB_IP:5432/orders
    username: orders_app
    hikari:
      maximum-pool-size: 5
      minimum-idle: 0
      connection-timeout: 5000
      max-lifetime: 1800000
server:
  port: 8080
~~~

The DB password is passed via Secret Manager and the `SPRING_DATASOURCE_PASSWORD` environment variable of the **API container** (or an appropriate secret-mounting mechanism). Never commit passwords to `application.yml`. `PRIVATE_DB_IP` is only a placeholder: replace it with Cloud SQL's private IP and secure the DB connection per TLS/authentication requirements.

Set distinct timeouts for HTTP clients, database pool acquisition/queries, and asynchronous jobs. Configure bounded retries with jitter, and only retry operations that are idempotent or protected against duplicates.

### 5.3. API Contract

Minimal API example:

| Endpoint | Purpose | Required Security |
| --- | --- | --- |
| `GET /health/live` | Liveness, avoiding expensive DB checks. | Return minimal info; do not leak environment details. |
| `GET /health/ready` | Readiness of service logic. | Do not expose sensitive details or trigger heavy load. |
| `GET /api/orders` | Return the user's order list. | Authentication and tenant-aware authorization. |
| `POST /api/orders` | Create an order. | Validation, CSRF/cookie policy, idempotency. |
| `GET /api/orders/{id}` | View a single order. | Object-level authorization; prevent IDOR. |

A pseudocode Spring controller illustrating business boundaries:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderDto> getOrder(
            @PathVariable long id, Principal principal) {

        // Service queries with userId/tenantId from the authenticated principal,
        // never trusting a userId sent directly by the browser.
        OrderDto order = service.findAccessibleOrder(id, principal.getName());
        return ResponseEntity.ok(order);
    }
}
~~~

This snippet is illustrative only. Production requires a Spring Security filter chain, authentication provider, `404/403` handling, DTO mapping, and tenant-checked queries. Never filter orders solely on the frontend while returning all orders from the API.

## 6. Data Tier: Cloud SQL PostgreSQL

### 6.1. Private IP and Egress Path from Cloud Run

Cloud SQL uses a **private IP** so the API accesses it over the VPC. For the Cloud Run service, configure **Direct VPC egress** to a VPC/subnet that can reach Cloud SQL, or use a Serverless VPC Access connector if compatibility requires it.

Prerequisites to verify:

1. The Cloud SQL instance is configured with private networking (e.g., Private Services Access or a supported private connectivity option).
2. Cloud Run Direct VPC egress points to the right network and subnet.
3. VPC routing and firewalls permit connections from the API to the Cloud SQL private IP.
4. The API uses the private IP address and PostgreSQL port `5432`.
5. The DB user has least-privilege application permissions; password/identity is managed separately.
6. DNS, TLS, and connection timeouts are properly configured.

`private-ranges-only` sends traffic destined for matching private/internal addresses through the VPC; `all-traffic` routes all egress through the VPC and may require Cloud NAT/routes if the API also calls the public Internet. **Direct VPC egress does not automatically create private ingress for the Cloud Run service**; the two traffic directions are configured independently.

### 6.2. Data Model and Migrations

Simple schema example:

~~~sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_user_created
    ON orders (user_id, created_at DESC);
~~~

Do not create SQL schemas by running ad-hoc DDL statements on every request. Use **Flyway** or Liquibase with versioned migrations and an approved pipeline. For breaking updates, use **expand-and-contract**: add backward-compatible columns/tables first, update code to read/write both, backfill, verify, and only then drop old schema elements.

Keep transactions short; avoid holding transactions open while calling external payment services. Design indexes for actual queries and grant DB accounts permissions only on required schemas.

### 6.3. HA, Backups, and DR

Cloud SQL **regional high availability** places primary and standby instances in two zones within the same region, minimizing downtime during a zone or instance outage. HA **does not mean** surviving a full-region outage or preventing human data-deletion errors. Therefore:

- Enable automated backups and **point-in-time recovery (PITR)** aligned with RPO requirements.
- Choose an appropriate retention period and consider cross-region backups when disaster recovery requires it.
- Practice restoring into a new instance and measure restoration duration.
- Confirm the application automatically reconnects on DB failover, as open connections can be dropped.
- If recovery from a full-region outage is required, design multi-region DR with replicas/backups and dedicated promotion/failover procedures; do not call Cloud SQL regional HA multi-region DR.

RPO (Recovery Point Objective) is the target maximum acceptable data loss, and RTO (Recovery Time Objective) is the target recovery time. These values must be verified via drills, not assumed merely from enabling HA or backups.

## 7. Security from Edge to Database

| Layer | Control |
| --- | --- |
| DNS/TLS | Managed certificates, HTTP→HTTPS redirect, HSTS after confirming stable HTTPS domain serving. |
| Edge | Cloud Armor WAF/rate limiting, abuse-blocking policies, monitoring HTTP 4xx/5xx. |
| Cloud Run ingress | `internal-and-cloud-load-balancing` to prevent LB bypass; consider disabling the default URL in a controlled manner. |
| Authentication | OIDC/OAuth, `HttpOnly`, `Secure`, `SameSite` session cookies as appropriate; MFA if required; IAP for internal apps. |
| Authorization | API validates user/tenant/resource; never rely on hiding UI buttons. |
| Service identity | Web and API use **two** separate service accounts; API gets permission to read secrets and call required Google Cloud APIs. |
| Network | API uses Direct VPC egress, DB private IP, firewall-restricted traffic; never expose a DB public endpoint. |
| Secrets | DB passwords/API keys in Secret Manager, IAM `secretAccessor` scoped per required secret. |
| Data | Least-privilege DB roles, TLS/auth, backups, and auditing. |
| Supply chain | Artifact Registry, image scanning/signing policies where appropriate, pinned digests, pipeline reviews, rollbacks. |

Cloud Armor protects the edge, but cannot replace input validation, object-level authorization, or anti-fraud logic. Likewise, Cloud SQL private IP shrinks the network attack surface, but does not replace database credentials.

**IAM boundaries:** the Cloud Run `orders-api` runtime service account only needs access to Secret Manager and the Google APIs called by the code. The Cloud Run deployer/CI identity holds deployment permissions and `iam.serviceAccounts.actAs` to attach the service account. End-user identity is a separate principal validated by the application at the HTTP layer. Never grant Owner/Editor just to make a pipeline work.

## 8. Scalability and Reliability

### 8.1. Primary Bottlenecks

| Symptom | Likely Bottleneck | Controlled Remediation |
| --- | --- | --- |
| UI responds slowly while API is healthy | Frontend rendering, static assets, TLS roundtrips, cache misses. | Cache fingerprinted assets, reduce bundle size, optimize SSR/SPA. |
| API p95 rises as traffic grows | Concurrency, cold starts, CPU, pool wait, downstream calls. | Tune concurrency/min instances, profile, load test. |
| Database runs out of connections | `max instances × pool size` too high. | Reduce pool size, cap max instances, optimize queries, or add proxying/pooling where fitting. |
| Slow SQL queries | Missing indexes, lock waits, N+1 queries. | Inspect query plans, add indexes, shorten transactions, and cache properly. |
| Traffic spikes cause 429/5xx | Quotas or downstream saturation. | Rate limiting, backpressure, queues, load tests, and alerts. |
| Single region outage | Workloads and DB co-located in one region. | Design multi-region/failover when RTO/RPO require it. |

Do not raise Cloud Run max instances indefinitely while Cloud SQL is the shared bottleneck. More API instances can amplify load on the database and worsen the outage.

### 8.2. Regional Availability

Cloud Run managed services run within a single **region**; Cloud Run manages infrastructure inside that region, but a single-region deployment does not automatically provide DR to another region. For higher requirements, consider deploying frontend/API across multiple regions and configuring the external load balancer with corresponding serverless backends. However, the **data tier** still governs RTO/RPO: you need a replication, consistency, promotion, and routing strategy for the DB before claiming a multi-region architecture is recoverable.

Do not equate a global load balancer with a multi-region application. The load balancer has a global external IP, yet if all backends and databases reside in one region, a failure of that region still disrupts the service.

### 8.3. Illustrative SLOs

Example for the ordering system:

- Availability of `GET /api/orders`: 99.9% of valid requests succeed over a 30-day window.
- Latency: 95% of `GET /api/orders` requests complete under 400 ms (illustrative threshold).
- Order creation error rate: `5xx` below 0.1% under projected load conditions.

SLOs must derive from user experience and real baselines. Alert on **error budget burn**, 5xx rates, p95/p99 latency, database connection saturation, and synthetic user journeys.

## 9. Step-by-Step Sample Deployment

The example uses project `PROJECT_ID`, region `asia-southeast1`, Artifact Registry repository `web-apps`, network `app-vpc`, subnet `app-subnet`, and domain `shop.example.com`. This is a **reference workflow**: before running, create the project, billing, network/private connectivity, Cloud SQL, secrets, images, and IAM. Do not copy placeholders directly into production.

### Step 1: Prepare APIs and Foundational Resources

~~~bash
gcloud config set project PROJECT_ID

gcloud services enable \
  run.googleapis.com \
  compute.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  --project=PROJECT_ID
~~~

Provision Cloud SQL PostgreSQL with a private IP on a compatible VPC. Create the database and a least-privilege DB user, store the password in Secret Manager, and grant `roles/secretmanager.secretAccessor` to the **API service account** on that specific secret. Build frontend/API images into Artifact Registry via CI; deploy by **image digest** or immutable tag so rollbacks work reliably.

### Step 2: Deploy the Frontend Tier

~~~bash
gcloud run deploy web-frontend \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/web-apps/frontend:VERSION \
  --region=asia-southeast1 \
  --service-account=frontend-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --ingress=internal-and-cloud-load-balancing \
  --allow-unauthenticated \
  --project=PROJECT_ID
~~~

`--allow-unauthenticated` is appropriate only if the website is **public** and organization policies permit it. For internal apps, consider IAP and appropriate Cloud Run invoker permissions instead of opening the whole service publicly. The frontend needs no permission to read DB secrets or connect to the DB.

### Step 3: Deploy the API with Private Egress

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/web-apps/api:VERSION \
  --region=asia-southeast1 \
  --service-account=orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --ingress=internal-and-cloud-load-balancing \
  --network=app-vpc \
  --subnet=app-subnet \
  --vpc-egress=private-ranges-only \
  --set-secrets=SPRING_DATASOURCE_PASSWORD=orders-db-password:1 \
  --set-env-vars=SPRING_PROFILES_ACTIVE=production \
  --allow-unauthenticated \
  --project=PROJECT_ID
~~~

In this public web architecture, `--allow-unauthenticated` on Cloud Run allows the load balancer to forward browser requests to the API; **the API's Spring Security must still authenticate and authorize users**. If public invocation at the infrastructure layer is unacceptable, design IAP or an appropriate authentication layer in front of the API, and check how the LB forwards identity.

Grant `roles/compute.networkUser` or required networking permissions to deployment/runtime identities per the chosen Direct VPC / Shared VPC requirements. For Cloud SQL private IP, set the JDBC URL to the private IP in environment-provided configuration. Never pass the DB password in `--set-env-vars` or commit it to Git. If the API uses the Cloud SQL Java Connector, also check the Cloud SQL Admin API and `roles/cloudsql.client` per the connector method; **direct TCP to private IP and connector-based auth are not identical**.

### Step 4: Set Up the Load Balancer

In the Google Cloud Console or Terraform, create in order:

1. A **global external Application Load Balancer** and a reserved global external IP.
2. A Google-managed TLS certificate for the domain; configure DNS records pointing to the LB IP.
3. One regional serverless NEG pointing to `web-frontend` and one NEG pointing to `orders-api`; place each NEG in the corresponding project/region matching the Cloud Run backend.
4. Two corresponding backend services; attach Cloud Armor policies as required.
5. URL map: `/api/*` to the API backend, default `/*` to the frontend backend. If needed, configure rewrites and confirm the app interprets paths correctly.
6. An HTTPS target proxy and port 443 forwarding rule; an HTTP redirect if required by design.
7. Cloud CDN **only** for appropriate static backends/responses; do not enable public caching for session-scoped responses.

Serverless NEGs have specific constraints regarding health checks, timeouts, and backend configurations. Do not configure VM-style backend health checks. For failover/health behavior, inspect Cloud Run service health / outlier detection features on the load balancer type in use and complement with synthetic monitoring.

### Step 5: Verify Access

~~~bash
curl -I https://shop.example.com/
curl -I https://shop.example.com/assets/app-HASH.js
curl -i https://shop.example.com/api/health/live
curl -i https://shop.example.com/api/orders
~~~

Expected outcomes:

- Web serves HTML/assets over HTTPS with a valid certificate.
- API health returns the defined response.
- Orders API requires a valid session; anonymous users are rejected by design.
- PostgreSQL private IP cannot be reached from the Internet.
- Direct Internet access to the `run.app` URL is blocked by Cloud Run ingress.
- Response times and request logs are observable in Monitoring/Logging.

Do not use `HEAD` to verify an API endpoint if the controller only supports `GET`; a `405` from `curl -I` does not mean the backend is broken. Always test with the matching HTTP method and path.

## 10. Infrastructure as Code and CI/CD

Manage resources in Terraform, Pulumi, or an IaC tool suited to the organization. With Terraform, state/modules can be split into:

~~~text
infrastructure/
  foundation/         # project, APIs, IAM, VPC, private connectivity
  data/               # Cloud SQL, backups, secrets, DB access
  applications/       # service accounts, Cloud Run services
  edge/               # serverless NEGs, backend services, URL map, TLS, Armor
  observability/      # dashboards, alerts, log sinks
~~~

Splitting state prevents an application pipeline from accidentally having permissions to delete the DB or alter all DNS. However, manage cross-state dependencies explicitly via outputs, versioned modules, and reviews.

A simple deployment pipeline:

~~~mermaid
flowchart LR
    CODE[Git commit] --> TEST[Unit + integration tests]
    TEST --> BUILD[Build container + scan]
    BUILD --> REG[Artifact Registry]
    REG --> STAGE[Deploy staging revision]
    STAGE --> SMOKE[Smoke + security + load checks]
    SMOKE --> APPROVAL[Approval]
    APPROVAL --> PROD[Traffic rollout]
    PROD --> OBS[SLI/SLO verification]
    OBS -->|Regression| ROLLBACK[Rollback revision]
~~~

Use Cloud Run revision deployments and traffic splitting for frontend/API. Apply backward-compatible migrations before shifting traffic. For breaking database migrations, code rollback usually **cannot** automatically roll back data; plan forward/backward schema compatibility.

## 11. Logging, Metrics, Traces, and SLOs

In a three-tier system, an HTTP 500 can originate from the frontend, API, or database. Synchronized telemetry helps pinpoint the right tier:

| Tier | Metrics/Logs to Track | Operational Question |
| --- | --- | --- |
| Edge | HTTPS request rate, 4xx/5xx, Cloud Armor blocks, TLS errors, cache hit ratio. | Is there an issue at ingress, WAF, or cache? |
| Frontend | SSR latency, instance count, cold starts, memory, JS errors (RUM if available). | Is the UI slow due to rendering or resource exhaustion? |
| API | Request rate, p50/p95/p99 latency, exceptions, concurrency, retries, auth failures. | Which endpoint or version is degrading? |
| Data | CPU, memory, disk, connection count, active transactions, query latency, lock waits. | Is the database the bottleneck or is the connection pool exhausted? |
| E2E | Synthetic checkout journey, SLI success/latency, error budget burn. | Can users actually complete their workflow? |

Use **OpenTelemetry** to propagate trace context across frontend/server-side calls, APIs, and dependencies. Emit JSON logs containing `traceId`, `spanId`, `service.name`, version, and a non-sensitive request ID. Never log access tokens, cookies, passwords, or personal data in logs or traces. When the DB slows down, traces pinpoint time spent in SQL spans while metrics show whether the connection pool or CPU is saturated.

Configure alerts on user-facing symptoms (5xx, p95, burn rate, journey failures), paired with supporting alerts for disk space, pool saturation, backup failures, and expiring TLS certificates. Every alert must have an owner, severity level, and runbook.

## 12. Cost and Load-Based Optimization

Total cost is more than Cloud Run requests. The design must evaluate these categories:

| Component | Cost Drivers | Optimization Levers |
| --- | --- | --- |
| External ALB + Cloud Armor | Load balancer, rules/policies, request processing. | Review routing/WAF needs; avoid unused rules/configs. |
| Cloud CDN | Cache lookups, data serving/egress. | Cache appropriate assets; avoid caching sensitive data. |
| Cloud Run frontend/API | CPU, memory, requests, instance-based options/min instances. | Tune concurrency, cold-start trade-offs, min/max instances. |
| Cloud SQL | Instance CPU/RAM, storage, HA, backups/PITR, egress. | Right-size tier via observation, tune indexes/queries, set sensible retention. |
| Networking | VPC egress, data transfer, Cloud NAT if used. | Route efficiently; avoid unnecessary cross-region data transfer. |
| Observability | Log ingestion/storage, metrics and trace ingestion. | Structured logs, sampling, retention, cardinality control. |
| Artifact Registry/CI | Image storage, builds, scans, and deployment operations. | Retention policies, cleaning up old images per approval. |

Cloud Run can scale to zero for certain workloads, but **Cloud SQL and the load balancer still incur baseline costs** even with low traffic. For very low-traffic apps, evaluate simpler configurations; for high steady traffic, compare costs against GKE or Compute Engine using real measurements rather than extrapolating from a single resource unit price.

A hypothetical calculation: 10,000 daily users making 10 API requests each yields roughly 100,000 API requests/day. That is **not enough** to calculate a bill: you still need time distribution, CPU/memory per request, cache hit rates, SQL queries, data egress, HA, and backups. Use the Google Cloud Pricing Calculator with sourced assumptions and measure actual costs post-deployment.

## 13. Alternatives and Trade-Offs

| Architecture | When to Choose | Trade-Offs |
| --- | --- | --- |
| **Cloud Run frontend + Cloud Run API + Cloud SQL** (this lesson) | Stateless web/API containers; small team wanting simple operations. | Cold starts, runtime/concurrency limits, database connections require tight management. |
| **Cloud Storage + CDN frontend + Cloud Run API + Cloud SQL** | SPA/static site; no SSR needed. | Very lean hosting, but auth, SEO/SSR, and cache invalidation need careful design. |
| **GKE frontend/API + Cloud SQL** | Many microservices, need Kubernetes primitives/service mesh, deep scheduling control. | Higher cluster operational overhead and networking complexity. |
| **Managed Instance Group + Load Balancer + Cloud SQL** | Legacy workloads or need OS/custom agents, long-running processes. | Managing images, patching, autoscaling, and VM health. |
| **Cloud Run API + Firestore** | Data fits a document model and designed queries. | Different transaction/query model from PostgreSQL, indexing and per-operation pricing. |

Three tiers do not strictly require relational SQL; pick the data tier based on consistency, query patterns, transaction boundaries, RPO/RTO, and team expertise. Nor must you split into many microservices just to “have three tiers”: a modular API service can be easier to operate.

## 14. Two Real-World Investigation Scenarios

### 14.1. API 5xx Spikes During a Promotion

1. Monitoring shows p95 rising and 5xx errors concentrated on `POST /api/orders`.
2. Cloud Run API scales instances rapidly, but Cloud SQL active connections hit near ceiling.
3. Traces reveal most latency is waiting on the connection pool, not the frontend.
4. Inspect `max instances × maximum-pool-size`, query plans, and transaction durations.
5. Dampen bursts with rate limits/queues, adjust concurrency/pool sizes carefully, and optimize transactions/queries.
6. Verify p95 and error budget recovery rather than blindly raising Cloud Run max instances.

### 14.2. Website “Disappears” After Load Balancer Change

1. Check DNS and certificate provisioning, plus HTTP→HTTPS redirects.
2. Verify the URL map routes `/api/*` to the right API backend.
3. Check that serverless NEGs point to the correct Cloud Run services and regions.
4. Check Cloud Run ingress `internal-and-cloud-load-balancing` and Invoker permissions/auth model.
5. Inspect Cloud Armor logs to see if a rule is blocking legitimate traffic.
6. With serverless NEGs, do not look for VM-style “health check firewall” errors; prioritize logs, synthetic probes, and LB/serverless behavior.
7. Test the `run.app` URL directly from the Internet—it should be blocked by design and must not be mistaken for a broken app.

## 15. Design Review Checklist

- [ ] Clearly defined UI, business/API, and data tiers, along with owners and trust boundaries.
- [ ] Web/API share a domain via HTTPS Load Balancer; URL map does not misroute paths.
- [ ] Cloud Armor is configured and rules are tested before enforcing broad blocks.
- [ ] Cloud Run ingress prevents LB bypass; Cloud Run IAM/public-access model matches product requirements.
- [ ] Frontend has no DB credentials or permissions to read DB secrets.
- [ ] API uses a dedicated runtime service account and enforces user/tenant authorization.
- [ ] Cloud SQL uses private connectivity; Direct VPC egress/subnet/routing/firewalls are verified.
- [ ] Database accounts hold only necessary SQL privileges; secrets are absent from Git/images.
- [ ] Connection pooling is configured with a safe `max instances × pool size` cap.
- [ ] Cache policies do not mistakenly cache session content or personal data.
- [ ] Cloud SQL backups, PITR, and restore drills are in place; regional HA evaluated against RTO/RPO.
- [ ] Regional HA is not confused with multi-region DR; a region-outage runbook exists.
- [ ] CI/CD deploys immutable images, backward-compatible migrations, traffic rollouts, and rollbacks.
- [ ] Logs, metrics, traces, SLOs, alerting, and synthetic user journeys are in place.
- [ ] Costs evaluated across load balancer, Cloud Run, Cloud SQL, network, backups, and logs.
- [ ] Verified with real requests: UI, API auth, database reads/writes, failures, and recovery.

## References

- [Google Cloud: Set up a global external Application Load Balancer with serverless backends](https://docs.cloud.google.com/load-balancing/docs/https/setup-global-ext-https-serverless) — load balancer, serverless NEGs, HTTPS, and backend configuration.
- [Serverless network endpoint groups overview](https://docs.cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts) — serverless NEGs, backend limits, and health checks.
- [Cloud CDN with Cloud Run and other serverless backends](https://docs.cloud.google.com/cdn/docs/setting-up-cdn-with-serverless) — CDN through an external Application Load Balancer.
- [Cloud Run ingress settings](https://docs.cloud.google.com/run/docs/securing/ingress) — `internal-and-cloud-load-balancing` and blocking direct Internet calls.
- [Cloud Run security design](https://docs.cloud.google.com/run/docs/securing/security) — IAM, authentication, ingress, and edge controls.
- [Cloud Run Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — networks, subnets, egress modes, and firewalls.
- [Cloud SQL PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — private IP and PostgreSQL connectivity.
- [Cloud SQL PostgreSQL high availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability) — regional HA, zone failover, and recovery considerations.
- [Cloud SQL PostgreSQL point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/configure-pitr) — backups and PITR.
- [Cloud Run: Configure service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity) — workload permissions and service accounts.
- [Secret Manager overview](https://docs.cloud.google.com/secret-manager/docs/overview) — application secret management.
- [Cloud Monitoring SLO monitoring](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring) — designing SLIs/SLOs and error budgets.
