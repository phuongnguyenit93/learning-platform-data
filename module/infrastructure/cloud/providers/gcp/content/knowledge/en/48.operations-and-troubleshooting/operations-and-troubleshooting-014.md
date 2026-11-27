# Managing API, Runtime, and Deprecation Notices

A Spring Boot service can run smoothly on Google Cloud for months and then break during a GKE cluster upgrade, a PostgreSQL version upgrade, a container JDK bump, or a redeployment of a Cloud Run function using a decommissioned runtime. Chances are Google Cloud had already announced it through release notes, emails, support policies, or deprecation insights. When notices lack an assigned owner, are never mapped to running resources, and are never turned into deadline-tracked tasks, a "surprise" breaking change is actually **unmanaged technical debt**.

This lesson in the **Operations and Troubleshooting** chapter of **CLOUD_PROVIDERS_GCP** establishes a lifecycle process for tracking **APIs, runtimes, service versions, and deprecation notices** from intake through impact assessment, testing, rollout, measurement, and evidence archiving. It applies across projects using IAM/VPC, Compute Engine, GKE, Cloud Run, storage services, Cloud SQL, and Java applications, linking directly to security, release automation, SLOs, and cost. The goal is planned operations rather than postponing upgrades until builds or deployments fail.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish launch stage, deprecation, end of standard support, extended support, decommission, and API removal.
- Build an inventory/API-runtime dependency register with owners, usage locations, EOL dates, and evidence.
- Configure intake channels via Essential Contacts, product release notes, and triage workflows without confusing them with live incident alerts from Personalized Service Health.
- Identify impacts from GKE Kubernetes deprecated APIs, Cloud Run runtimes, Cloud SQL major versions, `gcloud`/SDKs, and client libraries.
- Plan Java/Spring, Kubernetes manifest, and database upgrades using contract tests, compatibility checks, and progressive delivery.
- Write a change-control runbook with go/no-go gates, rollbacks, audits, and procedures for unsupported/overdue versions.

## 1. Lifecycle Terms: Do Not Lump Everything Under "EOL"

| Term | Operational Meaning | Required Action |
|---|---|---|
| Preview / Pre-GA | Experimental feature; SLAs and change guarantees differ from GA | Bound usage; keep an exit path if APIs change |
| GA | Generally available under applicable terms and policies | Track patches, security notices, and release notes |
| Deprecated | Google or upstream recommends stopping use; may still run temporarily | Freeze new dependencies; schedule migration |
| End of standard/regular support | No longer receives full regular support; some services offer Extended | Assess security risk, fees, and upgrade deadline |
| Extended support | Limited continued support, sometimes with extra fees | Use temporarily under an approved upgrade plan |
| End of support (EoS/EOL) | Version no longer supported under policy | Treat as high risk; may face auto-upgrades or zero support |
| Decommission / removal / shutdown | Creation/deployment blocked or API/feature removed; running workloads may stop | Must migrate beforehand; rolling back to old versions may fail |
| Breaking change | Behavior, contract, permission, schema, or response change breaking clients | Contract tests, parallel rollout, and rollback planning |

**No single fixed notice window applies to all GCP services.** Google Cloud deprecation terms apply per service and contract, and Pre-GA features may follow separate policies. Runtimes, database engines, and GKE each follow their own schedules. Always read the lifecycle page for your exact product, version, and region—never assume "12 months notice" as a blanket guarantee.

### Things That Still Run Yet Are Already Dangerous

- A Java 11 container still boots, yet its base image receives no security patches and its build pipeline is no longer reproducible.
- An old PostgreSQL major runs in Cloud SQL on extended support, yet extra fees rise while the deprecation cutoff approaches.
- Kubernetes `v1beta1` APIs still sit in CI manifests/templates even though existing cluster objects survive; after an upgrade, creating or updating resources fails.
- An API method still returns 200, yet a new response field or enum breaks parsers using rigid `switch` statements.
- An old library works today, yet its build chain relies on unsupported TLS/certificates, auth flows, or endpoints.

Operations must measure **the ability to deploy and recover**, not merely whether current workloads say `Running`.

## 2. Closed-Loop Change Governance

An organized response to deprecation notices follows this chain:

~~~mermaid
flowchart LR
  SRC[Official notice sources] --> IN[Intake, classify, archive evidence]
  IN --> MAP[Map against inventory & dependencies]
  MAP --> RISK[Assess risk and deadlines]
  RISK --> PLAN[Owner + upgrade plan]
  PLAN --> TEST[Compatibility + contract tests]
  TEST --> DEPLOY[Canary / rollout + rollback]
  DEPLOY --> VERIFY[SLOs + security + cost]
  VERIFY --> CLOSE[Close ticket, update inventory]
  CLOSE -. periodic review .-> SRC
~~~

**Receiving a notice is not finishing the job.** Every notice needs a ticket recording:

- `notice_id`, source URL, publication/last-update date, and **effective date** (if known).
- Affected products, APIs/runtimes/versions/regions/projects, and confidence level.
- Technical owner, approver, internal deadline, priority, and status.
- List of workloads, resource IDs, clients/SDKs, IaC/configs, and dependency types.
- Migration approach, test/canary/rollback plans, change window, and SLO monitors.
- PR/change-request links, test evidence, rollout timestamp, and closure criteria.

Never mark a ticket "resolved" simply because one Helm chart in Git was updated while CronJobs, CI runners, or release branches still call the old API. Find **every remaining writer and reader** and verify in live environments.

## 3. Who Owns Which Version?

| Layer | Google Cloud Manages | User / Operations Must Manage |
|---|---|---|
| Google Cloud managed API/service | Service infrastructure, endpoints, and published lifecycle policy | Client contracts, IAM, quotas, usage, and API behavior changes |
| GKE control plane/nodes | Upgrades per release channel and policy | Channel/maintenance window choices, Kubernetes manifests, add-ons, app compatibility |
| Cloud Run functions using Google-managed runtime | Base image/runtime and corresponding lifecycle | Upgrading runtime IDs, libraries, code, deploys, and tests |
| Cloud Run self-built containers | Container runtime execution and platform | Base OS/JDK, CVEs, rebuilds, SBOMs, and Java/Spring lifecycle |
| Cloud SQL | Managed database engine, maintenance, and version policy | Major upgrade planning, drivers, schemas, extensions, query compatibility |
| Cloud Storage / Pub/Sub | Managed services/APIs | Client libraries, IAM, schemas/events, retries/idempotency, and consumers |
| Compute Engine VMs | Host virtualization and managed services per policy | Guest OS, JDK, packages, agents, image lifecycle, and configured patching |
| Terraform / `gcloud` / SDKs | Tool releases and tool lifecycles | Version pinning, module updates, CI runners, and regression tests |

**Shared responsibility** does not mean Google Cloud upgrades the JDK inside a container image you built. Conversely, a managed platform may apply patches or minor upgrades inside a maintenance window even when your app code never changed—so compatibility testing and release tracking remain essential.

### Sample RACI

| Task | Application Owner | Platform / SRE | Security | DBA / Data | Change Manager |
|---|---|---|---|---|---|
| Intake notice and log ticket | C | R | C | C | I |
| Map active runtimes/APIs | R | R | C | R for DBs | I |
| Assess impact / SLO risk | A | R | C | C | I |
| Select target version and test plan | R | R | C | R for DBs | A per policy |
| Approve EOL exception | A | R | A for security risk | C | A for change window |
| Canary/rollout and rollback | R | R | C | R for schema migrations | A |
| Confirm ticket closure | A | R | C | C | I |

`R` is Responsible, `A` is Accountable/Approver per process, `C` is Consulted, `I` is Informed. This matrix is illustrative; in practice, ensure **every decision has one clear final Accountable owner** rather than conflicting `A`s on the same approval.

## 4. Information Sources: Separating Product Changes from Service Incidents

| Source | Best Used For | Limitation |
|---|---|---|
| Google Cloud **product release notes** and feeds | New features, changes, bug fixes, deprecated functionality, support schedules | Does not tell you which internal workloads use them |
| **Product-specific lifecycle/deprecation pages** | Support and removal dates for GKE, Cloud Run runtimes, Cloud SQL engines, etc. | Dates can shift; always check the authoritative page |
| **Essential Contacts** | Recipients for Product Updates, Technical, Security, Billing, etc. | Contact directory only; not a ticket or monitoring system |
| **Communication/notification preferences** | Individual opt-in for project maintenance/upgrade notices | Per-user settings; does not replace org-wide Essential Contacts |
| GKE **deprecation insights / Recommender** | Detected usage of Kubernetes APIs/features scheduled for removal | Cannot catch every case, especially rarely run jobs |
| **Cloud Audit Logs** and app telemetry | API callers, deprecated APIs, post-change errors, execution permissions | Only sees logged behavior; Data Access has sampling/cost |
| **Personalized Service Health** | Live disruptions/incidents affecting products, regions, and projects | Not the primary feed for runtime or API EOL schedules |
| Vendor/upstream security advisories | CVEs and lifecycles for Java, Spring, Kubernetes, PostgreSQL, base images | Dates can differ from GCP managed-service support windows |

**Personalized Service Health (PSH)** tracks live disruptions and incident response; a notice that "Java runtime decommissions next year" belongs to **lifecycle/product change management** with dedicated feeds and workflows. PSH enriches operational dashboards, yet never replaces release notes and Essential Contacts.

### Essential Contacts: Setting Them Up Properly

Google Cloud supports categories: `BILLING`, `LEGAL`, `PRODUCT_UPDATES`, `SECURITY`, `SUSPENSION`, `TECHNICAL`, `ALL`. Organizations can configure contacts at organization, folder, or project level—choose the scope matching your governance model. Always use **team mailboxes/distribution lists** with backup owners (such as platform/on-call and security aliases) rather than individual emails that break when someone leaves.

~~~bash
# Example: list contacts in the current project (read-only).
gcloud essential-contacts list

# Check gcloud CLI/roles before adding or editing contacts via Console.
gcloud essential-contacts --help
~~~

To inspect contacts on a specific project/folder/organization, check `--project`, `--folder`, and `--organization` flags for your CLI version; Resource Manager contact resource names use **project number**, not project ID. After configuring, send a test email per service guidance or confirm the mailbox receives category notices.

Essential Contacts **does not send emails itself**; it supplies recipient lists to Google Cloud notification services. Never treat "added contact" as complete unless that mailbox has triage, escalation, and ticketing workflows attached.

## 5. Building an Inventory: Finding Every API and Runtime Dependency

A list of GCP projects is never enough. APIs and runtimes hide in Java source code, Helm/Kustomize manifests, Terraform state, Cloud Build runners, VM startup scripts, cron/batch jobs, SDK containers, and SaaS integrations. Your inventory must track both cloud resources and **the actual calling clients**.

| Field | Illustrative Dummy Value | Why Track It |
|---|---|---|
| Workload / owner | `orders-api` / Commerce | Establishes upgrade accountability |
| Environment / project | `prod` / `commerce-prod` | Defines blast radius, IAM, and change windows |
| Product + resource | GKE `orders-cluster`; Cloud SQL `orders-pg` | Traces exact live versions |
| Version / channel | Kubernetes `1.xx`, Release Channel `Regular` | Drives support and upgrade scheduling |
| Runtime / toolchain | Java 17, Spring Boot release line, Docker base image digest | Tracks upstream EOL and CVEs |
| API dependency | `apps/v1`, Google API method, REST `v1` | Flags deprecated paths and compatibility |
| Client libraries | `com.google.cloud:google-cloud-storage` + version | Pinpoints build dependency edits |
| Exposure confidence | Observed / declared / inferred | Prevents mistaking "unseen" for "unused" |
| EOL date / source | Lifecycle URL + last-checked date | Tracks shifting dates |
| Risk / SLO | High / checkout SLO | Prioritizes remediation |
| Target version / action | Java 21, stable K8s APIs... | Actionable target state |

### Example Inventory CSV (Custom Format)

~~~csv
workload,project,component,observed_version,channel,owner,deadline,status,source
orders-api,commerce-prod,java-runtime,17,,commerce-team,2027-06-01,assessment,cloud-run-runtime-docs
orders-api,commerce-prod,gke-cluster,1.xx,regular,platform-team,TO_VERIFY,discovered,gke-versioning
orders-db,commerce-prod,postgresql,13,,dba-team,2027-01-15,upgrade-planned,cloud-sql-db-versions
~~~

`TO_VERIFY` intentionally marks unverified state rather than an official date. The two dates in this example are **illustrative internal deadlines**, not official Google Cloud EOL dates. Always store `official_notice_date` and `internal_deadline` in separate fields; never conflate them.

### Read-Only Inventory Commands

~~~bash
# Check active project before running commands.
gcloud config get-value project

# GKE: cluster version, location, channel (subject to API field support).
gcloud container clusters list \
  --project=PROJECT_ID \
  --format="table(name,location,currentMasterVersion,releaseChannel.channel)"

# Cloud SQL: databaseVersion, tier, region.
gcloud sql instances list --project=PROJECT_ID \
  --format="table(name,region,databaseVersion,settings.tier)"

# Cloud Run: list services; inspect Docker images/runtimes per revision next.
gcloud run services list --project=PROJECT_ID --region=REGION

# Enabled APIs do not prove whether active requests use them:
gcloud services list --enabled --project=PROJECT_ID
~~~

These commands expose resource metadata, **not** every library or API caller. Cross-check Git repositories, image SBOMs, Maven dependency trees, Terraform lockfiles, audit logs, network traces, and vendor integrations. Only read data within authorized scope and never export secrets.

## 6. GKE: Minor Version Support, API Deprecations, and Auto-Upgrades

A Kubernetes minor version and a Kubernetes API version are **two separate things**:

- Minor version (e.g., `1.xx`) identifies the Kubernetes/GKE version of the control plane and nodes.
- API version (`apps/v1`, `networking.k8s.io/v1`, etc.) identifies the schema used by `kubectl`, controllers, Helm charts, or CI to create/update objects.
- A deprecated Kubernetes API may still be accepted across several minor versions before being **removed** in a later release. Existing objects still running do not guarantee old manifests or automation still work.

### Support Lifecycle by Release Channel

Per current GKE documentation, a minor version receives roughly **14 months of standard support** from entering the Regular channel. The Extended channel can provide **up to roughly 24 months of total support**, where the post-standard phase focuses on security patches and may carry **additional fees**. Exact dates depend on minor version, channel, region, rollout waves, and Google updates; always check the **GKE release schedule** before every review cycle.

| Configuration Type | Key Behavior |
|---|---|
| Rapid / Regular / Stable | Different release velocities; subject to lifecycle auto-upgrades |
| Extended channel | Extends minor version support within bounds and potential fees; does not freeze a version forever |
| Maintenance windows / exclusions | Controls timing or temporarily pauses within supported limits; does not disable auto-upgrades permanently |
| Deprecated API insights | GKE may pause upgrades into a minor version removing an API when usage is detected, yet cannot guarantee catching every case |
| End of support | GKE may upgrade clusters onto supported versions despite prior deferral constraints |

**Never treat "auto-upgrade is paused" as proof a workload is safe.** Once a minor version leaves support, security patches and technical support narrow, and GKE eventually upgrades clusters off unsupported versions. Rollout schedules can shift; every maintenance exclusion needs an expiration date, justification, owner, and remediation plan.

### Finding Clients Calling Soon-to-Be-Removed Kubernetes APIs

GKE provides **deprecation insights/recommendations** in Recommender when it detects clusters using APIs/features scheduled for removal in an upcoming minor release. Insights may identify client traces. Some APIs are only called by quarterly batch jobs or disaster-recovery scripts, so they **miss recent observation windows**. GKE docs note that roughly 30 days with no observed deprecated usage can allow auto-upgrades to resume—never assume zero recent insights means your entire organization is clean.

Beyond the Console, query Cloud Logging:

~~~text
resource.type="k8s_cluster"
labels."k8s.io/removed-release"="1.XX"
protoPayload.authenticationInfo.principalEmail:("system:serviceaccount" OR "@")
protoPayload.authenticationInfo.principalEmail!~("system:serviceaccount:kube-system:")
~~~

Replace `1.XX` with the Kubernetes minor version removing the API; check version-specific docs. GKE Admin Activity audit logs capture write calls to deprecated APIs. To observe **read calls**, you may need to enable corresponding **Data Access audit logs**, weighing log volume/cost and data policy.

**How to catch all usage:** combine deprecation insights, audit queries, scanning `apiVersion:` in Helm/Kustomize/GitOps repos, rendered `helm template` outputs, CronJobs/Operators, and staging apply/update tests. With admission webhooks or CRDs, check conversion webhooks, `admissionReviewVersions`, and controller compatibility. Valid new YAML paired with an outdated controller can still break rollouts.

### Surprise-Free GKE Upgrade Workflow

1. Review release schedules, current control plane/node versions, release channels, and maintenance windows.
2. In a staging cluster matching production features, verify Ingress/Gateway, CSI, mesh, policies, CNI, metrics, node OS, and operators.
3. Hunt down all deprecated API usage across logs and repos; update manifests, charts, pipelines, and client SDKs first.
4. Check `kubectl` and tool version skew; run `helm template`, schema validation, and integration tests.
5. Upgrade control plane/nodes using supported GKE procedures—canary node pools and PodDisruptionBudgets on Standard, or supported version/timing controls on Autopilot.
6. Monitor Pod scheduling, readiness, rollouts, 5xx, request latency, cluster events, HPA, and Cloud SQL connections.
7. Update baselines and close deprecation insights only once **live usage is truly gone**, not merely because the upgrade finished.

**Rolling back a Kubernetes minor version is not an arbitrary undo** like rolling back a Deployment. Depending on product and upgrade stage, control plane or node downgrades may be unsupported. Build safety via staging, compatibility checks, node pool rollouts, and app/IaC rollbacks—never promise "we'll just downgrade GKE if anything breaks."

## 7. Cloud Run: Managed Runtimes vs. Self-Built Containers

For **Cloud Run functions** and workloads using **Google-managed runtime base images**, the Cloud Run runtime lifecycle follows **GA → Deprecated → Decommissioned**. While deprecated, some deploys/updates may still work without GA runtime support. After decommission, new creations and updates on that runtime are blocked, and running revisions **may be disabled**. Cloud Run announces deprecations ahead of time per policy.

**Crucial distinction:** if you deploy **your own container image built by your team directly to Cloud Run**, the "Google-managed runtime lifecycle" policy **does not directly govern the runtime inside your image**. However, you remain fully responsible for OS/JDK/base-image vulnerabilities, library EOLs, and reproducible rebuilds. Never interpret this as "self-built containers can ignore EOL."

### Sample Java Runtime Schedule to Verify Yourself

At the time of writing (November 19, 2026), Cloud Run's runtime lifecycle page listed illustrative entries:

| Managed Java Runtime | Illustrative Status / Dates from Policy | Action |
|---|---|---|
| Java 11 (`java11`) | Deprecated Oct 31, 2024; decommissioned Oct 31, 2025 | Do not select for new deploys; move to a supported Java LTS |
| Java 17 (`java17`) | Scheduled deprecation October 2027 | Plan version upgrade; verify latest dates before changes |
| Java 21 (`java21`) | Supported at time of writing; later dates per runtime table | Standardize on Java 21 LTS where dependencies allow and keep monitoring |
| Java 25 (`java25`) | Listed in runtime table; supported per matching configuration | Adopt once libraries/frameworks are compatible—not merely because it is newest |

These dates **can change**. Before every release or upgrade, check Cloud Run's live runtime lifecycle table directly. Runtime IDs in that table apply to managed-runtime workloads; they are **not mandatory flags** when deploying self-built containers with `gcloud run deploy --image=...`.

### Checklist When Changing Java Runtimes

- Verify Spring Boot/Spring Framework, Jakarta namespaces, PostgreSQL JDBC, gRPC, Netty, and crypto libraries support the target JDK.
- Check `--release` or compiler targets, container JVM flags, TLS defaults, truststores, timezones/locales, CA certificates, and base OS.
- Build and test on the exact target runtime and container image—never rely solely on a developer laptop's JDK.
- Enable health checks and canary traffic; monitor startup time, CPU, memory, GC, threads, p99 latency, and error budgets.
- Track image digests, SBOMs, and build provenance, and retain prior revisions **if the runtime still permits rollbacks**.
- For decommissioned runtimes, redeploying old revisions may be blocked; finish migrating before the deadline instead of counting on emergency redeploys.

## 8. Cloud SQL: Major Versions, Extended Support, and Delay Costs

Cloud SQL for PostgreSQL and MySQL follow **regular support**, **extended support**, and **deprecation** policies per major version. After upstream community EOL, Cloud SQL may offer extended support for **three years** with **additional charges** for those database versions; after deprecation, versions may be auto-upgraded to a service-designated default. Cloud SQL notifies project owners per product policy, yet organizations must still keep owners/Essential Contacts current and monitor version policy pages.

Illustrative example from published Cloud SQL for PostgreSQL schedules at the time of writing:

| PostgreSQL Major | Extended Support Starts | Published Deprecation Date | Meaning |
|---|---|---|---|
| 13 | Feb 1, 2026 | Feb 1, 2029 | Currently in extended phase; major upgrade plan needed |
| 14 | Feb 1, 2027 | Feb 1, 2030 | Standard support ending soon; avoid creating new dependencies |
| 15 | Feb 1, 2028 | Feb 1, 2031 | Still verify extension/driver compatibility and planned schedule |

**Never apply PostgreSQL dates to MySQL or SQL Server.** Follow each engine's official version page. Published dates can shift, and Cloud SQL major deprecation differs from minor maintenance: **minor** patches apply inside maintenance windows, whereas **major** upgrades require thorough compatibility testing.

### Production PostgreSQL Upgrade Sequence

1. Inventory instance versions, flags, extensions, JDBC drivers, schemas, read replicas, HA, backup/PITR, and workload transactions.
2. Verify Cloud SQL–supported target majors, migration prerequisites, extension compatibility, and replica/HA constraints.
3. Restore a backup into staging and test schema migrations, query correctness, indexes, collations, timezones, and load performance.
4. Choose **in-place upgrade** vs. **migration to a new instance**; define downtime, replication/switchover, DNS/connection strings, and rollback limits.
5. Pause/drain writes per runbook, checkpoint and verify replication lag, run the upgrade, run smoke tests, then reopen writes.
6. Monitor DB CPU/memory, connections, lock contention, slow queries, p95/p99 latency, and application correctness.
7. Close the ticket only after backup/restore, rollback constraints, and data integrity are verified, and update the database version in CMDB.

**A major-version downgrade is not always available as a rollback.** DB upgrades can alter on-disk formats, extensions, and query planner behavior; reverting usually means restoring a backup or failing back to a pre-cutover instance while reconciling post-cutover writes. Never promise a "5-minute rollback" without rehearsing data recovery.

## 9. API Versioning and Google Cloud Client Libraries

When an API promotes from `v1beta1` to `v1`, or a field/endpoint is deprecated, risk extends beyond servers: clients and automation may still call old endpoints via Java SDKs, `gcloud` CLI, Terraform providers, third-party integrations, or generated API clients.

Separate three change types:

1. **API surface:** methods, resources, versions, or fields removed, or required permissions changed.
2. **Behavior / schema:** new fields, new enum values, new defaults, pagination, error codes, rate limits, or retry semantics.
3. **Toolchain / client:** client library major upgrades, minimum Java versions, gRPC/protobuf, auth libraries, or build plugins.

Google Cloud client libraries version by artifact; **never equate** a Maven package version with a service API `v1` or `gcloud` CLI version. Upgrading a library does not mean the backend API changes immediately, and API updates do not always force a major library bump. Read separate release notes and changelogs.

### Inventorying Java Dependencies and Tooling

~~~bash
# Run inside your Java repository, never on production hosts.
./mvnw -B dependency:tree

# For Gradle projects:
./gradlew dependencies --configuration runtimeClasspath

# Check SDK/CLI versions used in CI runners.
gcloud version
kubectl version --client
terraform version
~~~

In Spring Boot, inspect the **BOM** managing `google-cloud-*`, Spring Cloud GCP, JDBC drivers, HTTP clients, and protobuf versions. Never override individual transitive dependencies casually when a BOM coordinates compatibility; document CVE overrides and run full regression suites. Use dependency scanners/SBOMs, Renovate/Dependabot, or equivalents to spot aging versions—bots open PRs, yet owners must still evaluate breaking changes.

### API Contract Compatibility

For public or shared internal APIs:

- Prefer **additive changes**: add optional fields and keep old field semantics during transition windows.
- Never alter field types, remove enum values, or drop endpoints without a proper deprecation window.
- Configure clients to tolerate unknown fields and unknown enum values per serialization library capabilities; test expanded payloads.
- Run `consumer-driven contract tests`, OpenAPI/protobuf compatibility checks, and staging end-to-end smoke tests.
- Roll out server/API and client changes via **expand → migrate → contract**; remove old fields only after proving zero active consumers remain.
- For IAM, verify new permissions on least-privilege principals; a post-upgrade 403 does not always mean a service outage.

Once an old API is decommissioned, rolling a client back **cannot restore a deleted server endpoint**. Finish migrating before the removal date rather than counting on rolling back to removed runtimes or APIs.

## 10. Designing a Unified Multi-Product Change Calendar

Every notice should become an item on a **change calendar** with an owner, internal deadline, and verification evidence. Never rely solely on a quarterly "upgrade day" that ignores urgent product cutoffs, nor route every release-note email to on-call pagers.

### Priority Tiers

| Tier | Signal | Internal Response Target |
|---|---|---|
| P0 — Urgent | Breaking change already causing outages, critical security risk, or lost functionality | Trigger incident response immediately |
| P1 — Imminent deadline | Shutdown or forced upgrade approaching while critical workloads still depend on it | Owner prioritizes immediately; track daily |
| P2 — Lead time available | Dated EOL/deprecation impacting production with enough time to test | Schedule into sprints/release trains; review weekly |
| P3 — Watch | Product change with unclear impact or dev-only exposure | Verify inventory, archive source, review periodically |

This is an **illustrative internal matrix**, not Google Cloud severity tiers. A sandbox-only notice ranks lower than one affecting production checkout/payments; base priority on impacted data, compliance, SLOs, rollback paths, and remaining lead time.

### Suggested Governance Milestones

For a deprecation with published decommission date `D`:

| Suggested Milestone | Required Deliverable |
|---|---|
| Immediately on detection | Ticket, source URL, owner, impacted resources, and severity |
| ~90 days before D (if lead time allows) | Target version/architecture decision, design review, and test plan |
| ~60 days before D | Staging tests, migration scripts, compatibility matrix, security review |
| ~30 days before D | Production rollout/canary, rollback rehearsal, post-deploy monitoring |
| ~14 days before D | Zero remaining usage; verify backup automation and DR tooling |
| Before D and post-rollout | Confirm zero residual dependencies, update inventory, final sign-off |

These day counts are **proposed internal targets**, not Google Cloud deadlines. If a notice arrives with only 21 days left, compress the schedule or obtain signed risk acceptance—never assume Google will grant an extension.

### Working Calendar Entry in YAML (Not a Google API)

~~~yaml
change_id: CHG-2026-014
source_url: https://docs.cloud.google.com/kubernetes-engine/versioning
product: GKE
change_type: kubernetes-minor-upgrade
discovered_at: 2026-11-19
official_effective_at: TO_CONFIRM
internal_deadline: 2027-01-20
affected:
  - project: ecommerce-prod
    workload: orders-api
    resource: orders-gke
    owner: platform-team
impact:
  criticality: high
  possible_breakages:
    - deprecated-api-manifest
    - ingress-controller-compatibility
verification:
  - static-manifest-scan
  - staging-cluster-contract-tests
  - production-canary
rollback:
  - application-rollout-undo
  - restore-previous-compatible-manifests
status: assessment
~~~

`official_effective_at: TO_CONFIRM` highlights that exact official dates must be pulled directly from the GKE release schedule. `internal_deadline` is illustrative and set by change owners. Never store tokens, credentials, or customer data in tickets.

## 11. Automated Discovery Always Needs Human Verification

You can build pipelines ingesting official release notes/changelogs to generate tickets. Google Cloud offers **product release notes**, product-specific release note pages, RSS feeds (for select products), and BigQuery release notes access per documentation. Custom HTML scrapers break easily when page layouts change; prefer feeds, APIs, or official published datasets while respecting terms/access rules.

Example pipeline flow:

~~~mermaid
flowchart LR
  RSS[Release notes / RSS / BigQuery] --> PIPE[Scheduled collector]
  EMAIL[Essential Contacts mailbox] --> TRIAGE[Email triage / parser]
  PIPE --> NORMALIZE[Normalize URL, date, product, type]
  TRIAGE --> NORMALIZE
  NORMALIZE --> DEDUP[Deduplicate notices]
  DEDUP --> MATCH[Match CMDB / inventory]
  MATCH --> TICKET[Ticket owner + deadline + priority]
  TICKET --> REVIEW[Human review / approval]
  REVIEW --> CHANGE[Staging, canary, and sign-off]
~~~

**The collector and parser are reference designs only**—they do not exist or run automatically from reading this lesson. Provision mailbox/BigQuery access, budgets, log retention, and notification controls. Filter notices to products/projects you actually use; never auto-upgrade or delete resources simply because the word "deprecation" appears.

### Notice Deduplication and Updates

Notices get updated, products get renamed, and dates get revised. Key deduplication on `product + official URL + feature/API identifier`, storing revision history, `first_seen`, `last_seen`, `source_updated_at`, and observation timestamps. If an EOL date shifts, update the **original ticket** and notify the owner instead of spawning five duplicate tickets.

Schedule governance cadences:

- Daily: triage important Product Updates/Technical/Security notices, urgent advisories, and product deadlines.
- Weekly: review unowned tickets, production impacts, schedule shifts, and blocked migrations.
- Monthly: audit stale inventory entries, upcoming 90/180-day EOLs, and overdue risks.
- After every release: update runtimes, image digests, API usage, and evidence; re-scan rarely executed CI/DR jobs.

**Common trap:** a 20-person email alias where nobody owns turning emails into tickets. Route directly into a platform/SRE intake queue with response SLAs, backup owners, and escalation to technical owners.

## 12. Pre-Deployment Compatibility Testing

A runtime or API change can cause indirect side effects: altered CPU/memory/G1 GC behavior, updated JVM TLS truststores, serialization failures, stricter IAM checks, shifted PostgreSQL query plans, mismatched webhook versions, or CRDs incompatible with the Kubernetes control plane.

### Four Testing Layers

| Layer | What to Verify | Evidence |
|---|---|---|
| Static / inventory | Dependency trees, SBOMs, IaC manifests, deprecated API versions | CI reports, usage scans, static scan outputs |
| Unit / contract | Schema/API compatibility, validation, new enums/fields, serialization | Unit tests, Pact/OpenAPI/protobuf contract tests |
| Integration | Auth/IAM, DB drivers, transactions, Pub/Sub retries, secrets, network/TLS | Staging tests on target runtime/service versions |
| Operational / non-functional | p95/p99 latency, CPU/memory, GC, scaling, failover, rollback, RTO/RPO | Load tests, canary metrics, game-day evidence |

**Never test only the happy path.** Test API responses containing unknown fields, `null`s, unknown enums, timeouts, HTTP 429/403, phased schema migrations, mixed old/new app versions running concurrently, and reconnection after DB maintenance. Where idempotency is used, test retries after lost responses.

### Expand–Migrate–Contract

Suppose you rename column `customer_name` to `customer_display_name`:

1. **Expand:** add the new column or compatibility view; deploy code capable of reading both.
2. **Migrate:** backfill data, update writers and readers service-by-service, and measure reads/writes hitting the old field.
3. **Contract:** drop the old column only after all consumers, batch jobs, and DR scripts stop referencing it.

Apply the same pattern to REST endpoints, Pub/Sub event schemas, and Kubernetes API manifests. Dropping an old field in a single release is hazardous when clients deploy across projects and regions on staggered schedules.

## 13. Progressive Delivery, Verification, and Rollback

Once compatibility is verified, roll out step by step:

1. Pin images, base images, and tool versions by digest for reproducible builds and clean comparisons.
2. Deploy to sandbox/staging; establish baselines for request latency, error rates, memory, and database connections.
3. Run smoke, contract, and integration tests, plus permission and config scans.
4. Canary a small traffic slice or single workload/node pool first; watch SLOs and security signals.
5. Promote at checkpoints only if error budget burn stays normal, with a named stop/go owner.
6. Close the rollout after verifying every client path works; update inventory, docs, and tickets.

### Knowing What Can Actually Roll Back

| Change | Rollback Feasibility | Fallback When Direct Undo Fails |
|---|---|---|
| Spring Boot Deployment image | Usually reversible via rollout undo to a compatible image | Keep image digests, configs, and schemas backward-compatible |
| Cloud Run revision | Shift traffic back while old revision/runtime stays supported | Rebuild on a supported runtime; never depend on decommissioned runtimes |
| GKE minor / control plane | Downgrade is not a standard supported fallback | Test in staging, canary node pools, verify manifests pre-upgrade |
| Cloud SQL major version | Direct downgrade may be unavailable | Backup/restore or migrate to a separate instance and reconcile writes |
| Provider-side API removal | Old clients cannot "resurrect" a deleted endpoint | Finish migrating before the removal deadline |
| Terraform provider/module | Can pin older versions, though state/schema compatibility varies | Back up plans/state, read provider notes, upgrade incrementally |

**A rollback must be tested**, not just a line in a change ticket. For data layers, if a new release wrote records unreadable by old schemas/code, rolling back the application makes things worse. In multi-region incidents, switching safely to read-only or degraded mode beats "rolling back at all costs."

## 14. Intake and Overdue-Risk Handling Runbook

### Step A — On Receiving a Notice

1. Verify authenticity: official URLs, legitimate Console/email domains; never click suspicious links.
2. Read full details: product, locations, support phase, old/new APIs, impact on create/update/run, start date, and final cutoff.
3. Open a ticket/record with minimal extracted facts, source link, and assigned owner.
4. Cross-check inventory: projects, service accounts, client libraries, Terraform/CI/Helm, runtime images, and batch/DR scripts.
5. Classify risk; if data is missing, mark `unknown` explicitly with a verification deadline.

### Step B — Planning

6. Identify the supported GA target version and official migration guide.
7. Assess compatibility across app code, IAM, networking, databases, and data consistency.
8. Build test plans, rollout windows, canary cohorts, go/no-go gates, and rollback constraints.
9. Obtain change approval and notify owners, on-call, and customers if SLAs require.

### Step C — Execution

10. Execute staging, integration, load, security tests, and rehearsals.
11. Deploy in phases while monitoring error rates, latency, backlogs, DB health, cluster events, and logs.
12. If thresholds breach, halt promotion and roll back **whatever is reversible**; if not, trigger the incident runbook.
13. Confirm zero legacy usage via audits, inventory, repo scans, metrics, and rarely executed job tests.

### Step D — Close the Loop

14. Record change results, deployed versions, timestamps, SLO impact, and any incident links.
15. Close the ticket only when exposure hits zero or a signed, time-bound risk acceptance exists.
16. Review why any notice was missed; tighten alerts, ownership, CI guardrails, and review cadences.

### If Past Deadline or Running an Unsupported Version in Production

Never panic-delete resources or blindly upgrade production without a plan. Confirm urgency and whether workloads still run; freeze further changes; apply interim mitigations such as network isolation, reduced exposure, or added logging; and contact vendors or Google Cloud Customer Care per support tier to confirm a supported path. You may need an emergency change with bounded rollback and a DR plan. A waiver only documents **time-bound risk acceptance**—it never turns an unsupported version into a supported one.

## 15. Real-World Scenario: Spring Boot on GKE, Cloud SQL, and Cloud Run

**Assumed system:** a company runs `orders-api` in Java/Spring Boot on GKE, `billing-worker` as a Cloud Run function on a managed Java runtime, PostgreSQL on Cloud SQL, and a GitOps pipeline with Helm charts. Checkout carries strict SLOs. The team just spotted three notices:

1. GKE is nearing standard support EOL on its current Kubernetes minor version; an older Helm chart still uses deprecated Kubernetes APIs.
2. `billing-worker` runs an older Java runtime with no integration tests after a JDK bump.
3. Cloud SQL PostgreSQL 13 entered extended support on Feb 1, 2026, introducing support and fee risks.

### Abbreviated Inventory

| Resource / Owner | Exposure | Risk | Remediation |
|---|---|---|---|
| GKE `orders-gke` / Platform | Minor upgrade needed; Helm chart/Operator holds old APIs | CI deploys fail or controllers break post-upgrade | Combine deprecation insights + audit logs + static chart scans; upgrade charts/controllers |
| Cloud Run function `billing-worker` / Billing | Old managed Java runtime | Blocked create/redeploy after decommission; missing patches | Upgrade to supported Java LTS, test framework/auth, deploy fresh revision |
| Cloud SQL `orders-pg` / DBA | PostgreSQL 13 extended support | Extra fees, approaching deprecation; driver/extension incompatibility | Backup/PITR + clone/staging upgrade, benchmark queries, cutover with rollback |
| GitOps / CI / Developer Experience | Old `kubectl`/Helm/providers | Tools incompatible with newer cluster | Pin and upgrade via compatibility matrix; scan repos |

**Important:** one upgrade often cascades into another. If upgrading Spring Boot requires a newer JDK while Cloud SQL major requires a newer driver, do not blindly bundle all three into one weekend cutover. Split into small independent changes whenever possible, each with its own SLO baseline and rollback. Tightly coupled changes must share end-to-end integration and DR tests.

### Suggested Rollout Waves

**Wave 0 — Inventory & risk:** owners verify live versions, official EOL links, all clients, CI/DR scripts, network identities, and data volumes.

**Wave 1 — Compatibility testing:** update Helm templates and controllers, test Java upgrades, build Spring Boot on the target JDK, and clone Cloud SQL to test migration. Run API contract tests, SQL correctness tests, and load tests.

**Wave 2 — App & automation upgrades:** deploy client versions and manifests compatible both before and after platform upgrades, then confirm via logs that zero legacy API calls remain.

**Wave 3 — Separate control plane and DB upgrades:** schedule maintenance windows, staff on-call, verify backups/restores and metric gates, and enforce SLO/rollback checks.

**Wave 4 — Close risk:** collect production version/API usage evidence, test DR assets and rarely run workflows, update CMDB/BOM, and close tickets.

### Example Mid-Upgrade Incident

Right after a GKE minor upgrade, GitOps `kubectl apply` fails with `no matches for kind` because a chart still uses a removed API. **Never run `kubectl delete --all` as a quick fix.** Pause auto-sync if it is breaking resources, identify the chart and updated API version, render compatible manifests, validate in staging, and apply the reviewed change. Check live workloads and health metrics rather than assuming an `apply` error means every Pod stopped.

If a Cloud SQL major upgrade shifts a query planner decision and p99 latency breaches SLO, do not assume "downgrade." Hunt down slow queries/indexes/extensions, roll back compatible app changes if relevant, or execute your prepared recovery/migration plan. For a decommissioned runtime, move to a supported runtime—**never expect `gcloud` to let you redeploy a removed runtime version**.

## 16. Reporting, Alerting, and Operational Metrics

Change management is not just compliance paperwork—it directly shapes uptime, security, and spend. Build a governance dashboard tracking:

| Metric | How to Read It | Action |
|---|---|---|
| Workloads with verified owner and runtime/version | Inventory coverage | Assign owners to orphaned assets |
| Days remaining until deadline | Exposure window | Escalate approaching notices |
| Deprecated APIs still called | Measured via logs/insights | Fix remaining clients/automation |
| Unsupported / EOL runtime count | Security and support risk | Schedule remediation and waiver expirations |
| Cloud SQL instances in extended support | Cost and major-upgrade risk | Weigh upgrade effort against recurring fees |
| Upgrade / canary success rate | Change quality | Improve testing and rollouts |
| Change failure rate & rollback frequency | Deployment safety | Shrink blast radius; add contract tests |
| Post-change MTTD / MTTR | Detection and recovery capability | Refine alerts and runbooks |
| Age of unverified Essential Contacts | Risk of missed notices | Test mailboxes and backup owners |

You can adopt an **internal policy** such as "every production workload must have an owner/version inventory and zero P1 deprecation notices lacking an approved plan within 30 days." This is a suggested internal rule, not a Google Cloud SLA or mandate.

### Separating Notices from Paging

- **Pager:** strictly for active outages, critical security threats, or imminent shutdowns.
- **Tickets + chat/email:** deprecation dates, runtime EOLs, and policy shifts needing planned investigation and migration.
- **Change calendar:** maintenance windows, rollout approvals, and DR drills.
- **Knowledge base:** official links, lessons learned, migration patterns, and known incompatibilities.

Never turn every product release note into a pager alert: alert fatigue guarantees responders miss real emergencies.

## 17. Common Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Adding only a personal email to Essential Contacts | Notices vanish when that person leaves or is off-shift | Use group mailboxes, backup owners, and delivery tests |
| Treating Personalized Service Health as an EOL feed | Missing API/runtime deadlines with no prior outage | Dedicated product release notes + lifecycle tracking |
| Confusing deprecation with decommission | Discovering deployments are blocked on cutoff day | Separate support phases from stop-create/update/run dates |
| Assuming GKE upgrades require no manifest edits | Removed APIs break GitOps/CI deploys | Audit/API scans + staging upgrades |
| Relying solely on GKE insights without alerts | Rarely run batch/cron jobs keep calling old APIs | Repo IaC scans + long log windows + owner sign-off |
| Leaving maintenance exclusions active indefinitely | Clusters lose support and face forced upgrades | Enforce expiration dates and remediation plans |
| Confusing Cloud Run managed runtimes with custom images | Team fails to patch self-owned JDK/OS | SBOM/base image scanning and rebuild policies |
| Trying to upgrade runtime, DB, and GKE all at once | Hard to isolate faults; messy rollbacks | Split into waves with separate tests and checkpoints |
| Ignoring Cloud SQL extended support fees | Rising bills and missed upgrade windows | Engine lifecycle inventory + FinOps reviews |
| Skipping client tests for new fields/enums | Parsers crash or miscalculate | Contract tests and forward compatibility |
| "Rolling back" to a removed API | Cannot restore service | Finish migration before removal; verify rollback feasibility |
| Monitoring only `Running` status | Misses transaction failures, timeouts, and bad data | SLOs, synthetic transactions, and consistency checks |
| Omitting sources and last-checked dates | Relying on stale EOL dates | Official links, timestamps, and periodic reviews |

## 18. Hands-On Practice Exercise

**Hypothetical scenario:** a team runs a GKE `app-cluster`, a Java 17 Cloud Run function, Cloud SQL PostgreSQL 13, and 10 Spring Boot repositories. Practice in read-only mode or an authorized sandbox—**never upgrade or delete production resources**.

1. **Build inventory:** list the 10 repos, owners, JDKs, Spring Boot versions, Docker base images, SDKs, Helm charts, and GKE/Cloud SQL/Cloud Run versions.
2. **Verify sources:** locate official lifecycle pages for GKE, Cloud Run Java, and Cloud SQL PostgreSQL; record query timestamp, actual support dates, and links.
3. **Audit contacts:** inspect contacts for Product Updates/Technical/Security, mailbox owners, and ticketing flows (metadata only within permissions).
4. **Find Kubernetes deprecated APIs:** scan source/manifests and check deprecation insights; confirm a rarely run CronJob is not missed.
5. **Build impact matrix:** assign P1/P2/P3 to each notice based on SLOs, time-to-EOL, security, and dependencies.
6. **Write migration plan:** Java 17 → a supported Java LTS aligned with runtimes/dependencies; PostgreSQL 13 → a Cloud SQL–supported target major; upgrade GKE release channel/minor safely.
7. **Testing:** detail contract tests, database restore/performance tests, staging cluster upgrades, canaries, and timeout/error handling.
8. **Rollback plan:** specify which changes can roll back vs. which require alternate recovery paths, with checkpoints and approvers.
9. **Design alerting:** sketch a workflow ingesting RSS/emails, normalizing metadata, creating tickets, and deduplicating.
10. **Acceptance checklist:** prove zero deprecated API calls remain, runtimes are updated, SLOs held, and on-call/DR docs are updated.

### Sample Scoring Rubric

| Criterion | Points |
|---|---:|
| Complete inventory with accurate owners and resources | 20 |
| Accurate distinction of support phases, dates, and official sources | 15 |
| Evidence-backed impact and dependency analysis | 15 |
| Test plan and security review | 20 |
| Viable canary, rollback, and DR plans | 20 |
| Notifications, auditing, closure, and FinOps | 10 |
| **Total** | **100** |

Submission package: sanitized CSV/YAML inventory, three lifecycle links with verification timestamps, sample change ticket, contract test plan, rollout/rollback plan, and governance dashboard metrics. Never include project credentials, service account keys, or unauthorized personal emails.

## 19. Periodic Operations Checklist

- [ ] Asset catalog links every workload to owners, environments, runtimes, API versions, client libraries, toolchains, and source URLs.
- [ ] Every Product Updates/Technical/Security notice routes to a group mailbox with backup owners, triage, and ticketing.
- [ ] Product release notes and lifecycle pages are reviewed periodically rather than relying solely on incident feeds.
- [ ] GKE cluster versions, release channels, maintenance windows, and end-of-support dates are inventoried.
- [ ] Deprecated Kubernetes APIs are scanned across Git/Helm/GitOps, audit logs, and Recommender, including rare batch jobs.
- [ ] Inventory separates Cloud Run managed runtimes from **self-built** container images with their own JDK/OS EOLs.
- [ ] Inventory tracks Cloud SQL major versions, extended support, maintenance schedules, backups/PITR, and fees.
- [ ] Maven/Gradle dependencies, SDKs, `gcloud`, `kubectl`, and Terraform/providers have pinned versions and update processes.
- [ ] Notices track official effective dates, internal deadlines, owners, priorities, and escalation paths.
- [ ] Test plans cover compatibility, contract tests, IAM, migrations, performance, security, and fault injection.
- [ ] Production rollouts enforce canary/traffic gating and explicit SLO thresholds.
- [ ] Rollbacks are promised only where genuinely viable; schema, major-version, and API-removal paths have dedicated recovery plans.
- [ ] Updates are verified across DR scripts, batch jobs, CronJobs, and third-party callers.
- [ ] Change records capture evidence, approvers, deployed versions, SLO impact, and closure timestamps.
- [ ] Zero unowned or open-ended EOL exceptions exist; every waiver has a remediation plan and review date.
- [ ] Dashboards separate live incident alerts from deprecation/lifecycle backlogs.

## 20. Conclusion

**Managing API, runtime, and deprecation changes is an operational lifecycle, not reading release notes in spare time.** Google Cloud manages the platform and publishes per-product policies, yet application teams must still track which API/JDK/DB versions they run, who receives notices, where impact sits, and how to test, roll out, and recover. Essential Contacts, release notes, GKE deprecation insights, Cloud SQL/Cloud Run lifecycle pages, and telemetry complement one another—**no single feed replaces an accurate inventory and owner sign-off**. Turning every notice into a deadline-driven ticket with test plans, change gates, and closure evidence cuts security exposure, surprise deployment failures, downtime, and avoidable extended-support fees.

## References

- [Google Cloud — Services subject to the Deprecation Policy](https://cloud.google.com/terms/deprecation)
- [Google Cloud — All release notes](https://cloud.google.com/release-notes)
- [Google Cloud — Essential Contacts overview](https://docs.cloud.google.com/resource-manager/docs/managing-notification-contacts)
- [Google Cloud — Manage Essential Contacts](https://docs.cloud.google.com/resource-manager/docs/manage-essential-contacts)
- [Google Cloud — Notification preferences](https://docs.cloud.google.com/resource-manager/docs/managing-notifications)
- [Personalized Service Health — Overview](https://docs.cloud.google.com/service-health/docs/overview)
- [Personalized Service Health — Incident communication](https://docs.cloud.google.com/service-health/docs/incident-communication)
- [GKE — Versioning and support](https://docs.cloud.google.com/kubernetes-engine/versioning)
- [GKE — Release schedule](https://docs.cloud.google.com/kubernetes-engine/docs/release-schedule)
- [GKE — Feature and API deprecations](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations)
- [GKE — View deprecation insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations/viewing-deprecation-insights-and-recommendations)
- [GKE — Kubernetes deprecated API migration guidance](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations/apis-1-32)
- [Cloud Run — Runtime lifecycle](https://docs.cloud.google.com/run/docs/runtime-support)
- [Cloud Run — Java runtime](https://docs.cloud.google.com/run/docs/runtimes/java)
- [Cloud SQL — Database version policies](https://docs.cloud.google.com/sql/docs/db-versions)
- [Cloud SQL for PostgreSQL — Database versions](https://docs.cloud.google.com/sql/docs/postgres/db-versions)
- [Cloud SQL for PostgreSQL — Major version upgrade](https://docs.cloud.google.com/sql/docs/postgres/upgrade-major-db-version-inplace)
- [Google Cloud CLI — Release notes](https://cloud.google.com/sdk/docs/release-notes)
- [Spring Boot — Reference documentation](https://docs.spring.io/spring-boot/reference/)
- [Kubernetes — Deprecation policy](https://kubernetes.io/docs/reference/using-api/deprecation-policy/)
