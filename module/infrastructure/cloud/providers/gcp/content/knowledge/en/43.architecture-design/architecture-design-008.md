# Multi-Tenant Design and Data Isolation on GCP

## 1. Goals and Problem Statement

In a **Software as a Service (SaaS)** system, many customers share the same product, yet each customer's data, configuration, access permissions, and resources must be properly separated. Each served customer or organizational unit is called a **tenant**. A tenant may be a company, a department, or an organization; a single tenant typically has many users, role groups, and datasets.

For example, an invoice management platform serves three companies: A, B, and C. Employees of company A may view authorized invoices within A, but must never read invoices, attachments, reports, caches, or logs containing B's data. If A suddenly uploads millions of files, A's resource consumption must also not degrade or halt B beyond agreed limits.

**Multi-tenant isolation** spans multiple dimensions: data security, resource limits, identity management, networking, encryption keys, operations, and recovery. Simply adding a `tenant_id` column to a database table does not create a securely isolated system.

This lesson belongs to the **GCP Architecture Design** chapter of the **CLOUD_PROVIDERS_GCP** module. Learners apply project organization, IAM, VPC, Cloud Run, GKE, storage/database services, release automation, reliability monitoring, and cost management to choose the right isolation level for real-world applications.

After this lesson, learners will be able to:

1. Distinguish shared-resource, dedicated-resource, and hybrid architectures.
2. Define tenant boundaries across authentication, authorization, request handling, data, and background jobs.
3. Design isolation using projects, service accounts, Cloud Run/GKE, Cloud Storage, Cloud SQL, Spanner, Firestore, and BigQuery.
4. Reduce risks of cross-tenant access and data leakage via caches, logs, backups, and asynchronous tasks.
5. Propose metrics, tests, and operational procedures across the entire tenant lifecycle.

## 2. Understanding Tenant Concepts and Trust Boundaries

A **Tenant** is a unit with its own data and access policies. A **User** is a person or service belonging to one or more tenants. A user permitted in two tenants does not mean those two tenants share data. **Tenant identity**, **user identity**, **runtime identity**, and **Google Cloud project identity** are four distinct concepts:

| Identity | Example | Purpose |
|---|---|---|
| Tenant | `tenant-acme` | Identifies the organization and business data scope |
| User | `user-123` | Authenticates the operator, checks membership/roles |
| Workload | Cloud Run service account | Calls GCP APIs and resources allowed by IAM |
| Project | `saas-prod-acme` | Manages boundaries for IAM, quotas, APIs, billing, and GCP resources |

Common failures begin when systems conflate these identities. For instance, a Cloud Run service running under one service account for all tenants might be granted IAM permission to read both bucket A and bucket B. In that case, Google Cloud only sees the **service account** reading; the application tier must ensure A's request never selects B's path. You cannot expect IAM to inspect a `tenant_id` inside an HTTP request on its own.

### Threat Actors and Attack Scenarios

- **Legitimate but curious user:** alters the tenant ID or document ID in a URL to view another customer's data.
- **Application bug:** omits a `tenant_id` clause in a query, writes to the wrong bucket, or builds a cache key without the tenant.
- **Compromised service account:** an overly broad workload token allows reading data across many tenants.
- **Noisy-neighbor tenant:** exhausts connection pools, CPU, API quotas, or queues.
- **Over-privileged operator:** runs debug commands or restores into the wrong tenant, or exports data beyond job scope.
- **Background tasks:** retried jobs or events missing tenant metadata write to the wrong partition.
- **Secondary data copies:** backups, snapshots, export files, BigQuery analytical copies, or logs holding uncontrolled data.

**Design principle:** deny access by default whenever a trustworthy tenant cannot be determined. Verify the tenant at ingress and preserve the constraint across every processing, storage, export, and administrative layer.

## 3. Three Common Architectural Models

### 3.1 Pool — Shared Resources

All tenants share one or more Cloud Run/GKE services, caches, databases, and buckets. Data is logically partitioned by `tenant_id`, collection, schema, partition, or object prefix depending on the product.

**Pros:** high resource utilization, fast onboarding, centralized upgrades, and potentially low fixed cost per tenant.

**Trade-offs:** demands strict authorization at the application/data layers; large blast radius on failure; one tenant can exhaust shared capacity; per-tenant backup/restore is harder.

### 3.2 Silo — Dedicated Resources per Tenant

Each tenant gets at least one dedicated set of resources, potentially including its own GCP project, VPC, Cloud Run service, database, bucket, service account, and Cloud KMS key. Data paths do not traverse shared memory or a shared service account holding access to all tenants, except through controlled orchestration components.

**Pros:** sharper IAM and resource boundaries, smaller blast radius, per-tenant customization of data residency, security policies, versions, and cost attribution.

**Trade-offs:** higher baseline cost, project/quota scaling limits, and requires automation to provision/delete resources, release, and monitor many environments.

### 3.3 Bridge (Hybrid) — Combined Architecture

Shared components such as login, routing, and API gateways serve everyone; sensitive workloads, sensitive data, or tenants with special contracts live in dedicated projects/databases/buckets.

**Example:** 500 Standard-tier tenants share compute and a database enforced via `tenant_id`; 10 Enterprise tenants get dedicated projects and databases while still sharing the control plane for signup, plan management, and routing.

| Criterion | Pool | Silo | Bridge |
|---|---|---|---|
| Data boundary | Primarily in app, queries, policies | Dedicated resources and IAM | Varies per component |
| Baseline cost/tenant | Usually low | Usually higher | Optimizable by tier |
| Per-tenant customization | More limited | High | Flexible |
| Noisy neighbor risk | Requires strict throttling | Reduced via resource isolation | Depends on what is isolated |
| Onboarding | Simpler | Needs automated provisioning | Medium/high complexity |
| Per-tenant audit & restore | Must be custom-built | Usually clearer | Depends on per-data boundaries |
| Best fit | Many small customers, similar load | Strong isolation needs, sensitive data | Multi-tier SaaS products |

**No single model is universally safest.** Isolation levels must match data classification, compliance standards, contracts, RTO/RPO, tenant count, SLOs, trust models, and cost.

## 4. Reference Model: Control Plane and Data Plane

~~~mermaid
flowchart TD
    U["Tenant A / B users"] --> G["HTTPS / API gateway / Load balancer"]
    G --> ID["Token authentication and tenant authorization"]
    ID --> CAT[("Tenant catalog: status, membership, resource mapping")]
    ID --> RT["Router by verified tenant"]
    RT --> SH["Shared application tier (Pool)"]
    RT --> A["Dedicated workload - tenant A (Silo)"]
    RT --> B["Dedicated workload - tenant B (Silo)"]
    SH --> DB[("Shared DB: tenant_id + access control")]
    SH --> OBJ[("Shared bucket: managed folder / per-tenant object key")]
    A --> DA[("Tenant A database + bucket + IAM")]
    B --> DBB[("Tenant B database + bucket + IAM")]
    CAT -.-> O["Provisioning / policy / billing / offboarding"]
    O -.-> A
    O -.-> B
~~~

The **Control plane** holds tenant management metadata: tenant ID, status, service plan, data owner, storage region, mappings to projects/databases/buckets, resource limits, versions, and lifecycle events. The control plane should store **minimal metadata**, never arbitrarily centralizing business content from isolated tenants.

The **Data plane** handles requests, reads/writes data, runs background jobs, and returns results for the tenant. It must obey the tenant context authorized by the control plane and authentication service.

Illustrative tenant catalog record:

~~~yaml
tenant_id: tenant-acme            # Stable internal ID; never use company name as a permission key
status: ACTIVE                     # PENDING | ACTIVE | SUSPENDED | DELETING
plan: ENTERPRISE
isolation_model: SILO
gcp_project_id: saas-prod-acme
region: asia-southeast1
database_ref: orders-acme
bucket_ref: saas-orders-acme
kms_key_ref: projects/.../cryptoKeys/tenant-acme
~~~

This record is **not a complete deployment config**. In production, validate metadata schemas/versions, access rights to the tenant catalog, data region transitions, and service account permissions.

## 5. Authentication, Authorization, and Resolving a Trustworthy Tenant

A typical multi-tenant API follows these steps:

1. Verify the OAuth 2.0/OIDC token server-side: signature, issuer, audience, expiration, subject, and claims per the chosen IdP flow.
2. Identify the authenticated user or workload.
3. If the client selects a tenant, **verify membership and roles** using trusted claims or server-side authorization data. Never accept a `tenant_id` in URLs/headers/bodies as proof of access.
4. Check that the tenant is `ACTIVE`, check its service plan, action permissions, and object-level ownership.
5. Construct an **internal tenant context** and propagate it across repositories, caches, events, jobs, exports, and logs.
6. Every layer uses the tenant context to select resources and scope reads/writes; missing context must fail closed.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Cloud Run API
    participant AUTH as Identity & Tenant directory
    participant DB as Tenant data store
    C->>API: GET /tenants/A/orders/42 + Bearer token
    API->>AUTH: Verify token + membership + role in A
    alt Valid
        AUTH-->>API: Principal + allowed tenant A
        API->>DB: SELECT ... WHERE tenant_id=A AND order_id=42
        DB-->>API: Record A or no data
        API-->>C: 200 or 404
    else Invalid
        AUTH-->>API: Deny
        API-->>C: 403
    end
~~~

### Application-layer pseudocode

~~~java
// Illustrative pseudocode, not a complete Spring Boot class.
Order getOrder(VerifiedPrincipal principal, String requestedTenant, UUID orderId) {
    // Verify via server-side data/permissions, including tenant status.
    TenantContext ctx = tenantAuthorization.requireMembershipAndRole(
        principal, requestedTenant, "orders:read");

    // Repository MUST enforce the tenant constraint inside the query itself.
    return orderRepository.findByTenantIdAndOrderId(ctx.tenantId(), orderId)
        .orElseThrow(NotFoundException::new);
}
~~~

Key considerations:

- Clients can pick a tenant when a user belongs to multiple tenants, yet **the server must authorize each choice independently**.
- Never let clients self-assert `role=admin` or an arbitrary `tenant_id` inside a client-forged JWT.
- **Tenant-wide** permissions do not replace object-level permissions: two employees in the same company might not be allowed to read every invoice.
- Mask sensitive details in `403/404` responses to prevent resource ID enumeration.
- When changing roles or suspending a tenant, token/membership caches need short TTLs or revocation mechanisms so stale permissions do not linger.
- Pass tenant context via internal headers only after authenticating the sender and preventing spoofing; prefer building the context directly inside the backend.
- When support staff need access to customer data, use an approved, scoped, time-bound, and audit-logged **break-glass** mechanism; never keep permanently active super-admin support accounts.

## 6. Isolation Across Google Cloud Projects, IAM, Networking, and Compute

### 6.1 Projects, Folders, and Organizations

Depending on security requirements, you can provision **one project per tenant**. Projects establish boundaries for IAM, API enablement, quotas, billing labels, and most resources. Organize projects under folders such as `production`, `sandbox`, and `dedicated-tenants`, applying appropriate Organization Policies and governance rules. Even a dedicated project must be hardened carefully because permissions granted at folder/organization levels inherit down into projects.

In a pool model, a project is a boundary shared by multiple tenants; never claim a GCP project is an isolated data boundary when all tenants share it.

**Silo permission pattern:**

- Tenant A's workload service account only holds required permissions on A's project/bucket/database;
- Tenant B's service account holds matching permissions on B;
- The control plane holds only provisioning/management permissions, separated from reading business data;
- CI/CD pipelines hold deployment permissions per project or granted scope, without default data-read rights;
- Grant permissions at the narrowest resource possible, avoiding project-level Editor/Owner for runtimes.

GCP **IAM** governs which principal may act on GCP resources; it does not automatically verify SaaS user memberships inside your application.

### 6.2 Cloud Run

**Cloud Run service identity** is the service account a container uses when calling Google Cloud APIs. A service running under one pooled service account could read multiple tenants' data if that service account is overly privileged. Therefore:

- **Pool:** use a least-privilege service account, enforce tenant checks inside the app, and add data-layer restrictions where supported.
- **Silo:** deploy separate Cloud Run services/jobs per tenant with dedicated service accounts; grant IAM on each tenant's bucket/database accordingly.
- **Bridge:** keep shared APIs/routers, but dispatch to tenant services or strictly controlled resource accessors. Never let a public gateway dynamically pick a high-privilege service account from arbitrary parameters.
- Prefer automatic credentials via runtime **Application Default Credentials**; avoid embedding long-lived service account keys in containers.
- When running untrusted tenant-supplied code, evaluate dedicated project-level isolation and extra sandboxing; separating each tenant into its own project is Google Cloud's recommended pattern here.

### 6.3 GKE

GKE supports multi-tenancy via **namespaces, Kubernetes RBAC, NetworkPolicy, ResourceQuota, LimitRange, Pod security controls**, and **Workload Identity Federation for GKE**. A pooled design often assigns a namespace per team/tenant and a dedicated Kubernetes ServiceAccount per workload.

However, **namespaces are not an absolute security boundary**: tenants may still share the control plane, nodes, add-ons, and host kernel depending on layout. Separate node pools, GKE Sandbox (where supported), admission policies, and network policies reduce risk, yet do not replace project/cluster boundaries when strict isolation or untrusted code execution is required.

Workload Identity Federation for GKE lets workloads authenticate to Google Cloud without manually storing service account keys. Note that workload identities tie to the project's workload identity pool; if multiple clusters in the same project reuse identical namespace/service-account names, evaluate the impact on resource access.

### 6.4 Networking and VPC Service Controls

VPCs, firewalls, egress policies, Private Service Connect, network policies, and private connectivity shrink the attack surface and block lateral movement. **VPC Service Controls** add service perimeters around supported Google-managed services (such as Cloud Storage and BigQuery) to mitigate data exfiltration outside approved boundaries. This does not replace `tenant_id` checks, IAM, or row-level access: two tenants inside the same perimeter still require separate access boundaries.

## 7. Data Isolation by Service Type

### 7.1 Cloud SQL for PostgreSQL: `tenant_id` Constraints and RLS

In a pool model, a single database may hold orders/documents tables for many tenants. At minimum:

- `tenant_id` is **NOT NULL** and included in primary or unique keys where appropriate;
- Every query filters by a verified `tenant_id`, including **`UPDATE/DELETE`, `JOIN`, batch jobs, and exports**;
- Indexes include `tenant_id` aligned with query patterns;
- Foreign keys across multi-tenant tables include `tenant_id` to prevent linking rows across tenants;
- Use PostgreSQL **Row-Level Security (RLS)** as an extra defense-in-depth layer.

PostgreSQL SQL example, assuming role **`app_runtime`** does not own the table, lacks `BYPASSRLS`, and has no special administrative privileges:

~~~sql
CREATE TABLE documents (
  tenant_id   text NOT NULL,
  document_id uuid NOT NULL,
  title       text NOT NULL,
  PRIMARY KEY (tenant_id, document_id)
);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_documents_policy
  ON documents
  FOR ALL
  TO app_runtime
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- SELECT/INSERT/UPDATE/DELETE privileges are granted separately as needed.
-- Never run the application as superuser, table owner, or a BYPASSRLS role.
~~~

After authenticating the tenant, the app sets transaction-local context and runs parameterized queries:

~~~sql
BEGIN;
SELECT set_config('app.tenant_id', 'tenant-acme', true);
SELECT document_id, title
FROM documents
WHERE tenant_id = 'tenant-acme'
ORDER BY document_id;
COMMIT;
~~~

This snippet is illustrative only: in production, the tenant value must come from server-side authorization and be bound as a parameter; never concatenate untrusted strings. Set context and execute queries within **the same transaction/connection**, avoiding stale context leaks across connection pools. Unset values must fail closed under the policy. Notably, anyone permitted to run arbitrary SQL as the app role could overwrite that PostgreSQL custom setting; therefore, **never give tenants direct DB connectivity** and do not treat this RLS setup as a boundary against a compromised application server.

A silo design can use **a dedicated database or instance per tenant** for stronger isolation, factoring in connection limits, baseline costs, backups/restores, and automated schema migrations.

### 7.2 Cloud Storage: Dedicated Buckets or Managed Folders

**Silo:** dedicated bucket per tenant (or dedicated project + bucket), with an IAM service account permitted to read/write only the required bucket. Encryption, retention, lifecycle, logging, and storage locations can be tailored per tenant.

**Pool:** shared bucket with object keys organized by tenant, e.g.:

~~~text
gs://saas-shared-documents/tenants/tenant-acme/contracts/2026-001.pdf
gs://saas-shared-documents/tenants/tenant-beta/contracts/2026-008.pdf
~~~

An object prefix is a **naming convention**, not an authorization boundary. When prefix-level IAM is required, Cloud Storage supports **managed folders** with IAM policies on matching object groups; managed folders require **uniform bucket-level access**. IAM permissions granted at bucket/project level can still override narrower permissions at a managed folder. Design permissions top-down—never assume a narrow folder policy negates inherited broad permissions.

Signed upload/download URLs must be generated backend-side **after verifying tenant and specific object permissions**, scoping the HTTP verb, expiry, and path; never sign URLs using unvalidated client-supplied filenames or prefixes.

### 7.3 BigQuery: Dedicated Datasets, Row-Level and Column-Level Security

For analytical data, options include:

- **Dedicated dataset/table per tenant:** cleaner IAM separation and easier per-tenant export/deletion/reconciliation, at the cost of managing more datasets/tables.
- **Shared table with `tenant_id`:** reduces management overhead at large scale, but requires access boundaries inside BigQuery or at the application layer.
- **Row-level security:** policies filtering rows by authorized principal.
- **Column-level security or data masking:** protects sensitive columns independently of row boundaries.

Example using **GoogleSQL** for a group authorized to read `tenant-acme` data (assuming `analytics.orders` has a `tenant_id` column):

~~~sql
CREATE ROW ACCESS POLICY acme_orders_read
ON analytics.orders
GRANT TO ('group:acme-analysts@example.org')
FILTER USING (tenant_id = 'tenant-acme');
~~~

Project/dataset/table IAM permissions must still allow the principal to query; row access policies determine which **rows** are visible. Row access policies follow specific union semantics across principals, so audit against overly broad grants.

If **a single shared service account** runs queries for all tenants, BigQuery sees the same principal on every request. Principal-based policies cannot distinguish which SaaS user sits behind that shared service account. Use distinct identities for direct querying, separate datasets, or enforce trusted tenant filtering inside the backend. Avoid granting broad BigQuery admin roles to runtimes needing scoped queries.

### 7.4 Firestore: Security Rules vs. Server Identity

For web/mobile clients accessing Firestore directly, structure documents under tenant paths and check **Firebase Authentication / custom claims** issued by a trusted backend. Simple example when each token carries an active `tenant_id` claim:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /tenants/{tenantId}/documents/{docId} {
      allow read, write: if request.auth != null
        && request.auth.token.tenant_id == tenantId;
    }
  }
}
~~~

This is a **minimal illustration**—it does not yet check roles, per-document ownership, schemas, field mutability, or multi-tenant user access. Claims must be refreshed/revoked when permissions change, and rules must be tested before deployment. Security Rules **do not act as query filters**; client queries must match the scope permitted by the rule.

**Critical trap:** Firestore server client libraries and many server/API paths use **IAM**, bypassing Firestore Security Rules entirely. If a Cloud Run backend uses the Admin SDK to read Firestore, the application must enforce its own tenant authorization. Never rely on client Security Rules to protect backend access.

### 7.5 Spanner and Distributed Data

Spanner supports **fine-grained access control (FGAC)** via database roles bound to IAM principals for tables, columns, views, and supported objects. This is not an automatic per-row `tenant_id` filter. For pooled tables, design schemas and queries with `tenant_id`; for silos, separate databases or instances depending on isolation and cost needs.

At large scale, order primary key columns starting with `tenant_id` (or a fitting composite) aligned with query patterns and load distribution. Avoid naive sequential keys that concentrate writes onto one split: evaluate key strategies and hotspots against Spanner architecture.

### 7.6 Pub/Sub, Cloud Tasks, Caches, Search, and Secondary Copies

Tenant isolation must extend across **every copy and processing pipeline**, not stop at the primary database:

- **Pub/Sub / Cloud Tasks:** include a verified `tenant_id` in payloads or attributes; consumers must resolve and re-verify context before writing. Authenticate publishers/consumers with IAM and manage dead-letter/retry flows.
- **Cloud Storage exports/imports:** bind filenames, manifests, and target buckets to the valid tenant.
- **Caches (e.g., Memorystore):** key with `tenant_id`, resource type, ID, and version; limit sensitive data, TTLs, and admin tooling read access.
- **Search indexes / vector stores:** every query must include a tenant filter; client-side filtering alone is insufficient.
- **BI / BigQuery datasets:** copying data from an operational DB to a warehouse creates **a new permission system** that must be governed separately.
- **Logs, traces, error reporting:** tag internal `tenant_id` codes, but never log tokens, sensitive payloads, invoice contents, or personal data just for debugging convenience.

Example of properly scoped cache keys:

~~~text
tenant-acme:order:fa1d...:v3
tenant-beta:order:fa1d...:v3
~~~

An event processed multiple times needs a **tenant-scoped idempotency key**. If an idempotency key relies solely on order ID and two tenants happen to share an ID, one tenant's request could accidentally skip or overwrite the other's.

## 8. Encryption, Keys, Backups, and Compliance

### Encryption and Key Management

Google Cloud encrypts data at rest and in transit according to service mechanisms. For customer-managed key requirements, evaluate **Cloud KMS / CMEK** for supported services and resource scopes. Some silo designs use per-tenant keys to satisfy operational policies or crypto-shredding.

Do not assume **a separate KMS key alone guarantees tenant isolation**: who can decrypt, who can read encrypted data, who administers keys, and key selection paths must all be controlled. CMEK granularity varies by service, resource, and configuration; verify before signing contracts.

### Backups, Restores, and Data Deletion

Answer these questions before selling the service:

1. Can you **restore a single tenant** without overwriting other tenants' data?
2. Do backups mix multiple tenants in one snapshot? How do you extract one tenant's dataset cleanly?
3. When deleting a tenant post-contract, does deletion cover object versions, BI copies, caches, search indexes, logs, and backups per retention schedules?
4. Which retention durations, legal holds, RPO/RTO targets, and regions apply to each tenant?
5. Are deletion certificates or support-access audit reports required?

In a pool model, full-database PITR/snapshots usually do not equate to single-tenant recovery. You need tenant-filtered export/import tooling, isolated restore staging environments, and checks to prevent cross-tenant overwrites. In a silo model, restoring a dedicated project/database is simpler, yet shared dependencies still need verification.

## 9. Preventing Noisy Neighbors and Tracking Usage

**Noisy neighbor** occurs when one tenant's abnormal load spikes latency, error rates, or costs for other tenants. Risks arise in CPU, RAM, connection pools, Cloud Run concurrency limits, Pod counts, API quotas, database throughput, or BigQuery slots.

Practical controls:

| Layer | Approach |
|---|---|
| API | Per-tenant and per-user quotas, rate limiting; payload and concurrency caps |
| Cloud Run | Appropriate concurrency/max-instance caps; split dedicated services for huge tenants if needed |
| GKE | `ResourceQuota`, `LimitRange`, autoscaling, dedicated node pools / priority classes |
| Database | Per-tenant or per-tier connection pools, timeouts, query limits, `tenant_id`-indexed queries |
| Jobs / events | Dedicated or fair queues, per-tenant worker limits, backpressure, retries with jitter |
| BigQuery | Track jobs/workloads, apply quotas or reservations per fitting model |
| Cost | Labels/tags, measuring GB, requests, CPU, query bytes, budgets, and chargeback/showback |

Define SLOs **per tenant or service tier**, not solely system-wide averages. Track HTTP 5xx rates, p95 latency, event processing lag, job backlogs, throttling rates, and cost per tenant per 1,000 requests. Avoid placing unbounded high-cardinality `tenant_id` labels on metrics without cardinality controls; aggregate by tier or key tenants where fitting.

**Pool costs** cannot be inferred accurately from project labels alone because tenants share resources. Supplement with application-level per-tenant usage telemetry and an allocation model for shared infrastructure. **Silo costs** separate more cleanly by project, though shared control planes, networking, and operational overhead still require allocation.

## 10. Tenant Lifecycle and Automated Operations

A sound multi-tenant platform needs consistent workflows:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROVISIONING
    PROVISIONING --> ACTIVE
    ACTIVE --> SUSPENDED
    SUSPENDED --> ACTIVE
    ACTIVE --> DELETING
    SUSPENDED --> DELETING
    DELETING --> DELETED
    DELETED --> [*]
~~~

### Onboarding

- Generate an immutable `tenant_id` and a tenant catalog record in `PENDING` state.
- Validate data residency, service tier, isolation model, key requirements, and budget.
- Use Infrastructure as Code (e.g., Terraform) to provision projects, service accounts, IAM, networks, buckets, databases, and policies if required by the model.
- Apply schema migrations and configure monitoring, backups, logs, quotas, and secure defaults.
- Run access verification tests: account A cannot read/write B's data; failed provisioning must roll back/clean up cleanly.
- Transition to `ACTIVE` only after provisioning finishes with verified health and evidence.

### Plan Changes or Migrating Pool to Silo

- Provision target resources and verify a consistent data-migration strategy.
- Use batch copy/CDC or suitable replication, recording watermarks and verifying checksums/counts.
- Version mappings in the tenant catalog so routers never split requests across incompatible destinations.
- Cut over traffic in a controlled window, validating delta data, rollback plans, and acceptable downtime.
- Revoke source permissions and decommission old resources per policy only after sign-off.

### Offboarding

- Lock tenant access, block new jobs, and cancel obsolete retries.
- Perform contractual data exports, revoke service account tokens/access rights, and invalidate active signed URLs where mechanisms exist.
- Delete or schedule deletion of primary data, backups, object versions, search/cache entries, and exports in accordance with retention/legal holds.
- Audit-log cleanup steps and transition to `DELETED` only after verification gates pass.

**Note:** deleting a project does not guarantee cleanup of data already exported to shared projects or external services. Inventory data flows from the start.

## 11. Testing Data Isolation and Security

Tests must verify **access denials**, not only happy paths. Minimum test suite:

| Scenario | Expected Outcome |
|---|---|
| User A requests tenant B's data URL | Denied per policy; zero leakage of B's data |
| User A tampers with `tenant_id` in JSON body | Cannot write objects into B |
| User belongs to A and B, but holds read-only role in B | Cannot write in B |
| Query missing tenant context | Fails closed; never returns full table |
| Same record ID exists in both A and B | Query/update affects only the authorized tenant |
| Colliding cache keys, job IDs, or event IDs | Never mixes results, retries, or states |
| Worker receives event with forged `tenant_id` | Verifies sender/context and rejects |
| Workload A service account tries reading bucket B | Denied by IAM in Silo model |
| BigQuery row policy for group A | Sees zero tenant B rows; no additive grant widens scope |
| Tenant A traffic spike | Tenant B stays within latency/error-rate SLOs |
| Restore/export of tenant A | Does not touch or expose tenant B data |
| Suspending tenant A | Requests and background jobs stop promptly |
| Support agent accesses tenant A | Requires approval/scoped role/expiry and writes audit logs |

Example SQL test plan:

~~~sql
-- Within a transaction where tenant A is set from a trusted backend:
SELECT COUNT(*) FROM documents WHERE tenant_id = 'tenant-acme';

-- Attempt out-of-scope query while PostgreSQL RLS holds tenant A context:
SELECT * FROM documents WHERE tenant_id = 'tenant-beta';
-- Expected: returns zero tenant-beta rows for role app_runtime.
~~~

Test other logic bugs: SQL JOINs missing tenant predicates, backups restored to the wrong DB, signed URLs minted from unverified object keys, BigQuery policies granted to a group accidentally containing user B, search queries missing filters, and requests hitting admin endpoints.

Automate these tests in an environment with at least two synthetic tenants sharing identical data formats and colliding IDs. Regularly review the threat model and run scheduled recovery drills.

## 12. Design Case Study: Contract Management SaaS

A team is building a Google Cloud product expected to serve **500 small businesses** and **10 Enterprise customers**. Each tenant manages PDF contracts, signer records, approval history, and reports. Enterprise clients require regional residency, isolated recovery, and detailed auditing.

### Proposed Design

- **Shared control plane:** tenant registry, authentication, billing, and provisioning services holding only essential metadata.
- **Standard (pool):** API on Cloud Run; transactional data in Cloud SQL for PostgreSQL with `tenant_id`, composite keys, tenant-filtered queries, and RLS as defense-in-depth; PDFs in Cloud Storage with appropriate managed folder/bucket policies.
- **Enterprise (silo):** dedicated project, Cloud Run service identity, database, bucket, and backup configuration; separated processing regions where contractually required, with least-privilege IAM.
- **Reporting:** dedicated BigQuery datasets for Enterprise or shared tables with principal-based row access controls; ETL flows must carry verified `tenant_id`.
- **Asynchronous tasks:** Pub/Sub/Cloud Tasks carrying validated tenant context, per-tenant retries and idempotency, capping backlog impact from heavy tenants.
- **Observability:** overall SLOs plus p95/5xx/job lag/cost metrics for key tenants; audit reports scoped by granted permissions.

### Illustrative Request Flow

1. An ACME user logs in and requests to download contract 77.
2. Backend verifies token, checks membership and read role in tenant ACME.
3. Router identifies ACME as Enterprise and looks up the mapping to ACME's project/services.
4. ACME's workload uses its dedicated service identity to fetch metadata and the object from ACME's bucket; IAM grants zero access to Beta's project.
5. Backend issues a short-lived signed URL scoped strictly to that authorized object.
6. Audit log records principal, internal tenant ID, object ID, outcome, and request trace—without logging contract contents.

If ACME upgrades from Standard to Enterprise, the platform must run a controlled migration and verify post-move data integrity. If a temporary migration service account needs read access to both buckets during transfer, keep permissions narrowly scoped and revoke them promptly afterward.

### Decision Analysis

For Standard, pooling optimizes initial cost while requiring rigorous tenant authorization testing in both app and data layers. For Enterprise, siloing better satisfies isolation and independent recovery needs at higher operational cost. Bridge is a pragmatic choice when serving distinct customer segments and the team has automated provisioning capabilities.

## 13. Pre-Approval Architecture Checklist

1. [ ] Tenant, user, membership, roles, and valid tenant-selection flows are clearly defined.
2. [ ] Data classification, required isolation level, and rationale for pool/silo/bridge are documented.
3. [ ] Tenant context is verified at the API and propagated to every query, event, job, cache, export, and log.
4. [ ] Runtime IAM follows least privilege; project/service-account/database/bucket boundaries are defined.
5. [ ] Per-service data protections are verified: SQL RLS, BigQuery row policies, Cloud Storage IAM/managed folders, Firestore rules, or IAM.
6. [ ] Key caveats are understood: Cloud Run service accounts are not SaaS end-user identities; GKE namespaces are not hard boundaries; Firestore server SDKs bypass Security Rules.
7. [ ] Noisy-neighbor protections and per-tenant quotas are in place.
8. [ ] Per-tenant onboarding, suspension, migration, backup/restore, and offboarding procedures exist.
9. [ ] Audit logs, metrics, billing, secondary copies, and support-staff access are governed.
10. [ ] Cross-tenant access tests and recovery drills are automated prior to production.

## 14. Key Takeaways

- Multi-tenant isolation is a **cross-cutting architecture concern** spanning identity, application logic, data, networking, workloads, operations, and cost.
- **Pool** suits high tenant density with strong app/data tenant enforcement; **silo** strengthens separation at higher cost; **bridge** blends both per business tier.
- Google Cloud **IAM secures GCP resources by principal**; IAM does not inherently know which SaaS customer sits behind a shared service account request.
- Partition keys, bucket prefixes, or GKE namespaces are organizational tools; they are secure only when paired with properly scoped access controls.
- Defense in depth: server-side tenant verification, least-privilege IAM, tenant-scoped queries, database policies where possible, cross-tenant testing, observability, and operational discipline.
- The goal of sound design is ensuring **a single bug cannot easily cause broad data leakage or widespread outages**, while leaving room to scale as tenants grow.

## Official Documentation for Implementation Reference

- [Google Cloud — App Lifecycle Manager: silo, pool, and hybrid models](https://docs.cloud.google.com/app-lifecycle-manager/overview)
- [Cloud Run — Multi-tenant platforms running untrusted code](https://docs.cloud.google.com/run/docs/securing/multi-tenant)
- [Cloud Run — Introduction to service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [GKE — Cluster multi-tenancy](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/multitenancy-overview)
- [GKE — Best practices for enterprise multi-tenancy](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/enterprise-multitenancy)
- [GKE — Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Cloud Storage — Managed folders](https://docs.cloud.google.com/storage/docs/managed-folders)
- [BigQuery — Row-level security overview](https://docs.cloud.google.com/bigquery/docs/row-level-security-intro)
- [BigQuery — Managing row-level security](https://docs.cloud.google.com/bigquery/docs/managing-row-level-security)
- [Firestore — Structure security rules](https://docs.cloud.google.com/firestore/native/docs/security/rules-structure)
- [Firestore — Security for server client libraries](https://docs.cloud.google.com/firestore/native/docs/security/iam)
- [Spanner — Fine-grained access control overview](https://docs.cloud.google.com/spanner/docs/fgac-about)
- [VPC Service Controls — Overview](https://docs.cloud.google.com/vpc-service-controls/docs/overview)
