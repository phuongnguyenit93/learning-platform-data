# Handing Over Runbooks, Inventory, and Cleaning Up Post-Lab Resources

## 1. Why Finishing a Lab Does Not Mean Operations Are Complete

After a Google Cloud lab session, a Java/Spring Boot application may be running on Cloud Run or GKE, a Compute Engine VM may have served tests, an Eventarc trigger may have delivered events, and Cloud Storage may hold sample data. However, operators still carry critical responsibilities:

- **Handover:** recipients must know what the system does, how it is deployed, where to monitor its health, and how to handle incidents.
- **Inventory:** knowing which resources exist, in which project/region, who owns them, what depends on them, what data they hold, and what costs they incur.
- **Cleanup:** decommissioning unnecessary test resources without accidentally deleting backups, retained data, or dependencies shared by another workload.
- **Verification:** proving a handed-over service still operates properly, or proving cleaned-up resources are truly gone with no lingering spend or failures.

In the **CLOUD_PROVIDERS_GCP** module, this stage ties together project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, databases, storage, CI/CD, reliability, and cost management. A well-engineered system is judged not just by deploying cleanly, but by how safely someone else can take it over or decommission it.

This lesson ends along two clear paths:

1. **Operational handover** for applications staying in service: preserve required resources, documentation, and ownership.
2. **Lab teardown**: preserve required evidence, revoke access, delete remaining resources, and verify billing.

Never mix these two paths inside a single automated script. Keep/delete decisions must be confirmed by the system owner beforehand.

## 2. Minimum Deliverables of a Handover

| Deliverable | Mandatory Contents | Reviewer |
|---|---|---|
| Resource inventory | Project ID, resource name/ID, type, location, owner, environment, state | Platform / FinOps |
| Architecture & dependency map | Entry points, data stores, service calls, networking, IAM, event flows | Tech lead / operations |
| Deployment guide | Code, image digest, CI/CD, IaC revision, configuration, rollback | Developer / DevOps |
| Operational runbook | Health checks, alerts, error handling, escalation, restore | On-call / operations |
| Security & access handoff | Service accounts, IAM roles, secrets, KMS, audit logs | Security / IAM owner |
| Data & backup decision | Keep, export, migrate, retention, delete; RPO/RTO | Data owner |
| Cleanup plan | Target resources, dependency order, rollback, approvals | Resource owner |
| Closure evidence | Logs, before/after inventories, test outcomes, cost checks | Handing-over and receiving owners |

**A chat message saying "deleted everything" cannot replace an inventory record.** Records should link to tickets or change requests, IaC commit hashes, build versions, and exact resource lists. Never store access tokens, service account keys, or secret values in handover documents.

### 2.1. Acceptance Criteria

Handover passes when recipients can perform the following **without asking the original author**:

1. Identify the exact project, environment, and owner.
2. Locate dashboards, logs, and critical alerts.
3. Deploy and roll back through approved workflows.
4. Diagnose common auth, networking, or resource quota errors.
5. Locate data stores, backups, and retention periods.
6. Safely stop or delete specific resources without breaking retained components.

For full lab teardown, acceptance passes when evidence shows target resources are gone, retained resources have owners and retention policies, and lingering spend is tracked.

## 3. Handover Roles: Owner, Approver, and Operator

Before executing changes, build a RACI table or equivalent responsibility model.

| Task | Responsible | Accountable | Consulted |
|---|---|---|---|
| Verify current state and alerts | SRE / DevOps | Service owner | Developer |
| Confirm data is safe to delete | Data owner | Business owner | Security / compliance |
| Finalize keep vs. delete list | Resource owner | Project owner | FinOps |
| Review `terraform destroy` plan | Platform engineer | Infrastructure owner | Security |
| Execute cleanup | Approved least-privilege operator | Change approver | On-call |
| Verify cost/billing | FinOps or project admin | Cost center owner | Platform |
| Archive evidence and close ticket | Handover sender | Handover recipient | Stakeholders |

Never grant a single service account blanket permissions to deploy, rotate secrets, destroy databases, and delete projects. Enforce **separation of duties** for irreversible operations.

### 3.1. Classifying Each Resource's State

Every resource must carry one handover state:

- **KEEP:** still serves active applications or required by retention policy.
- **DELETE:** lab-only and explicitly approved for deletion.
- **MIGRATE:** move data/config to a new environment before deleting the old copy.
- **UNKNOWN:** owner or dependencies unclear; **do not delete** until clarified.
- **BLOCKED:** constrained by retention locks, legal holds, dependencies, IAM restrictions, or open incidents.

Never treat a few hours of zero traffic as proof a resource is unused. Monthly scheduled jobs or backup restore paths do not generate daily traffic.

## 4. Resource Handover Manifest Template

Manifests can live in work-tracking tools or version-controlled YAML files. This example illustrates a **learner output template**, not an instruction to create a file in STEP 4:

~~~yaml
handoff:
  ticket: "LAB-2026-042"
  project_id: "demo-gcp-sandbox"
  environment: "lab"
  owner: "platform-team"
  decision: "CLEANUP_APPROVED"
  approver: "project-owner"
  approved_at_utc: "2026-11-19T09:00:00Z"
  artifacts:
    git_commit: "COMMIT_SHA"
    image_digest: "sha256:IMAGE_DIGEST"
    terraform_revision: "GIT_REVISION"
  evidence:
    inventory_before: "REFERENCE_TO_INVENTORY"
    architecture: "REFERENCE_TO_DIAGRAM"
    restore_check: "REFERENCE_TO_TEST"
    inventory_after: "PENDING"
resources:
  - type: "run.googleapis.com/Service"
    name: "projects/demo-gcp-sandbox/locations/asia-southeast1/services/lab-api"
    owner: "application-team"
    action: "DELETE"
    depends_on: ["artifact-repository"]
  - type: "storage.googleapis.com/Bucket"
    name: "lab-image-output-unique"
    owner: "data-team"
    action: "KEEP"
    reason: "Test evidence retained for 14 days"
    expires_at_utc: "2026-12-03T00:00:00Z"
~~~

**Important:** `expires_at_utc` inside a manifest or custom label does not make Google Cloud delete a resource automatically. Automated cleanup requires dedicated lifecycle rules, TTL policies, or managed schedulers with scoped permissions.

A good manifest states the exact **reason** for `KEEP`/`DELETE`, approver, recovery plan, and evidence links. Never record passwords, service account keys, private tokens, or credential-bearing connection strings.

## 5. What Makes a Good Operational Runbook?

A runbook is an actionable procedure for live situations, not merely an architecture overview.

### 5.1. Recommended Structure

| Section | Contents |
|---|---|
| Title and version | Scenario name, owner, last updated date, commit |
| Scope | Project, region, service, environment, and applicability |
| Trigger | Alerts, user errors, deployment failures, or cleanup requests |
| Preconditions | IAM, approval rights, maintenance windows, backups |
| Blast radius | Which services and data could be affected |
| Diagnostics | Read-only commands, dashboards, logs, trace IDs |
| Actions | Small, incremental steps with checkpoints |
| Verification | Signals proving success |
| Rollback / failback | How to revert safely and limitations |
| Escalation | On-call contacts and required attachments |
| Evidence | Tickets, log queries, sanitized outputs |
| Closure | Timestamps, outcomes, lessons learned, and follow-ups |

Dangerous commands must sit behind explicit checkpoints. Before deleting Cloud SQL, a runbook must verify the exact instance, last backup, replicas, deletion protection, consumers, and approver. Never include `--quiet` to bypass confirmations in learning scripts.

### 5.2. Three Runbook Types to Keep Separate

- **Operate:** inspect deployments, logs, metrics, scaling, and health.
- **Recover:** roll back, restore, fail over, or fix IAM/networking.
- **Decommission:** stop traffic/schedulers, preserve data, remove dependencies, and verify spend.

Mixing incident recovery with resource deletion risks triggering a second outage. A `Cloud Run 503` runbook should never contain a step saying "delete the entire project if errors persist."

## 6. Sample Runbook: Checking Java Application Health on Cloud Run

Assume `orders-api` runs in `asia-southeast1`. First, confirm your active environment and target parameters:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export SERVICE="orders-api"

gcloud auth list
gcloud config get-value project
gcloud projects describe "$PROJECT_ID" \
  --format="value(projectId,lifecycleState)"
~~~

Never rely blindly on `gcloud`'s default project: commands can hit the wrong project if context shifts. Pass `--project` explicitly on every command.

### 6.1. Inspect Deployment and Revisions

~~~bash
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service="$SERVICE"
~~~

Record the traffic-serving revision, container image digest, service account, ingress settings, and **non-sensitive** environment variables. Never dump secret values into tickets.

### 6.2. Read Logs and Alerts

~~~bash
gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=100

gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=ERROR' \
  --project="$PROJECT_ID" \
  --limit=50
~~~

Filter further by service name and actual timeframe before drawing conclusions. `severity>=ERROR` alone captures errors from unrelated services too.

### 6.3. Diagnose and Verify

A quick triage matrix:

| Symptom | First Check | Resolution Path |
|---|---|---|
| 401/403 | ID token, audience, `roles/run.invoker`, ingress | Isolate authn, IAM, or business authz |
| 404 after deploy | URL, path, routing, revision | Check service/revision routing |
| 5xx | Logs, dependency health, exceptions | Roll back or fix root cause |
| Timeouts | Cloud Run concurrency, CPU/memory, DB pool | Tune deadlines and retries |
| Cannot reach DB | Cloud SQL connector, VPC, IAM, firewalls | Inspect networking and identity |
| Sudden cost spike | Instances/concurrency, retries, log volume | Shed load and trace cost drivers |

If recovery fails within RTO, trigger escalation. Runbooks must specify explicit **decision gates** between fixing forward, rolling back, and declaring an incident.

## 7. Sample Runbook: Post-Release Rollback and Verification

When a new revision breaks traffic:

1. Identify the last stable, schema-compatible revision.
2. Check current traffic splits, SLO burn, and impacted user scope.
3. Verify database migrations are backward-compatible.
4. Obtain approval per severity and change policy.
5. Shift traffic back to the target revision via official deploy/rollback tooling.
6. Watch 5xx rates, p95/p99 latency, and transaction outcomes during the verification window.
7. Document the incident, rollback rationale, and follow-up improvements.

**Read-only** inspection examples:

~~~bash
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(status.traffic)"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service="$SERVICE"
~~~

Shifting traffic is a **write operation**—never execute it without verifying target revision, database compatibility, and approval. Some side effects cannot be undone by switching revisions alone and require outbox, reconciliation, or application-specific runbooks.

## 8. Project-Level Inventory with Cloud Asset Inventory

Never rely on memory or resources visible on a single Console page. **Cloud Asset Inventory** searches supported resources across a project, folder, or organization.

### 8.1. General Resource Search

~~~bash
gcloud services list --enabled --project="$PROJECT_ID"

gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(assetType.basename(),name,location,labels)"
~~~

Requires the Cloud Asset Inventory API enabled and `cloudasset.assets.searchAllResources` permission on the scope. Never treat empty output as "project has zero resources" if permissions are missing, the API is disabled, or a resource type is unsupported by Asset Inventory.

### 8.2. Search Resources by Label

Example searching for lab-labeled resources:

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="labels:lab" \
  --format="table(assetType.basename(),name,location,labels)"
~~~

Tailor queries to real labels and resource types. An unlabeled resource is **not automatically production**, and a `lab`-labeled resource is **not automatically safe to delete**.

Cloud Asset Inventory does not cover every asset type, runtime metadata field, or service resource. Cross-check service-specific APIs and billing reports.

### 8.3. Fields to Record per Resource

Minimum fields:

~~~text
project_id
resource_type
resource_full_name
region_or_zone
labels/tags
owner/team
created_at / last_modified_at
service_dependencies
data_classification
backup/retention
state: KEEP | DELETE | MIGRATE | UNKNOWN | BLOCKED
estimated_monthly_cost
approval_reference
~~~

Full resource names matter more than display names because identical short names can exist across multiple projects and regions.

## 9. Service-by-Service Inventory Cross-Checks

Cloud Asset Inventory is a starting point, not the sole source of truth. Run **read-only** listings per service used in the lab.

### 9.1. Compute Engine, GKE, and Networking

~~~bash
gcloud compute instances list --project="$PROJECT_ID"
gcloud compute disks list --project="$PROJECT_ID"
gcloud compute snapshots list --project="$PROJECT_ID"
gcloud compute addresses list --project="$PROJECT_ID"
gcloud compute forwarding-rules list --project="$PROJECT_ID"
gcloud compute reservations list --project="$PROJECT_ID"
gcloud container clusters list --project="$PROJECT_ID"
~~~

Watch for **unattached persistent disks**, static external IPs, reservations, snapshots, instance templates, managed instance groups, load balancers, and firewall/network objects. Deleting a VM can still leave billable disks, static IPs, or reservations behind.

### 9.2. Cloud Run, Event Processing, and Artifact Registry

~~~bash
gcloud run services list --project="$PROJECT_ID"
gcloud run jobs list --project="$PROJECT_ID"
gcloud eventarc triggers list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud pubsub topics list --project="$PROJECT_ID"
gcloud pubsub subscriptions list --project="$PROJECT_ID"
gcloud artifacts repositories list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

A Cloud Run service may be deleted while Artifact Registry images, Eventarc triggers, Pub/Sub resources, or Cloud Tasks queues remain. Cloud Run Jobs and Cloud Scheduler jobs can also relaunch workloads after the primary service stops.

### 9.3. Storage, Databases, and Automation

~~~bash
gcloud storage buckets list --project="$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"
gcloud secrets list --project="$PROJECT_ID"

gcloud scheduler jobs list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud tasks queues list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Filestore, BigQuery datasets, GKE persistent volumes, Memorystore, Spanner, Cloud DNS, VPN/Interconnect, Cloud KMS, and log buckets must also be inventoried **if used**. Never inspect only one region; some resources are global or reside in other locations.

A `gcloud list` command failing due to missing permissions or a disabled API represents an **incomplete inventory**, not proof cleanup is finished.

## 10. Dependency Analysis Before Cleanup

Example image-upload lab application:

~~~mermaid
flowchart TB
    USER[Lab uploader] --> IN[(Input bucket)]
    IN --> TRIG[Eventarc trigger]
    TRIG --> RUN[Cloud Run image-worker]
    RUN --> IN
    RUN --> OUT[(Output bucket)]
    RUN --> SA[Runtime service account]
    TRIG --> TSA[Trigger service account]
    RUN --> IMG[Artifact Registry image]
    RUN --> SECRET[Secret Manager secret]
    RUN --> DB[(Optional Cloud SQL)]
    SA --> KMS[Optional KMS key]
    RUN --> LOG[Logs / metrics]
~~~

Crucial dependency: **triggers can keep firing events after Cloud Run is deleted**. Retries generate errors, operational noise, and unexpected charges. Always stop event sources before deleting receivers.

### 10.1. Standard Teardown Order

1. Announce maintenance and close test upload/traffic entry points.
2. Disable schedulers, Eventarc triggers, Cloud Tasks producers, and workload generators.
3. Drain or handle pending messages per data requirements.
4. Back up, export, or migrate data marked for retention.
5. Remove public routes, load balancers, or DNS records once zero valid clients remain.
6. Delete compute/data workloads: Cloud Run services/jobs, GKE deployments/clusters, VMs, or scoped databases.
7. Hunt down and delete **orphaned resources**: disks, persistent volumes, reserved IPs, images, snapshots, queues, and artifacts.
8. Revoke unused IAM bindings, service accounts, and secrets.
9. Clean up shared infrastructure **last**, only after confirming zero remaining consumers.
10. Re-inventory and monitor billing after cleanup.

This is a logical sequence; real dependencies may dictate reordering specific steps. Never delete VPCs or KMS keys before resources that still depend on them.

## 11. Data and Retention: Gates Before Any Deletion

Before deleting any bucket, database, disk, image, or backup, the data owner must answer:

- Does it contain real/PII/secret data or policy-governed records?
- Are legal holds, retention locks, or audit requirements active?
- Are snapshots or exports needed for rollback or reconciliation?
- Has the backup actually been **restore-tested**, or merely created?
- Must image digests, schemas, logs, or evidence remain to reproduce incidents?
- Do any consumers, CI/CD jobs, schedulers, or other projects rely on it?
- Is deletion permitted? If not, who owns it and when does retention expire?

### 11.1. Cloud Storage

Cloud Storage supports soft delete, Object Versioning, retention policies, and Bucket Lock. Deleting objects or buckets may **not halt charges immediately** if soft-deleted objects remain retained. Conversely, deleting the wrong bucket loses data and releases the bucket name for others to claim.

For buckets holding lab data:

1. List objects/versions and total storage size.
2. Check soft delete, versioning, retention/holds, and lifecycle rules.
3. Export/copy data marked to keep to an owned destination.
4. Obtain written sign-off from the data owner.
5. Only then delete following the bucket's approved procedure.
6. Verify object/bucket status and any policy-retained items.

**Never run recursive deletes** on a bucket merely because its name contains "test."

### 11.2. Cloud SQL

Cloud SQL is a stateful resource. Before deleting:

- Check replicas, backups, deletion protection, and active consumers.
- Take a final backup or export per engine capabilities and policy.
- Verify restore proofs before destroying the instance.
- Confirm no migration jobs, schedulers, or services still point to it.
- Identify retained backups, private endpoints, DNS records, and related network objects.

Deleting an instance can destroy data and backups; some Cloud SQL workflows offer final backups with separate retention rules. Never confuse "delete instance" with "archive database."

### 11.3. KMS, Secrets, and Certificates

Never destroy or disable key versions still encrypting retained snapshots, databases, or buckets. **Destroying key material renders data permanently unreadable.** Cloud KMS permits certain resource deletions under current conditions, yet deleting a key/key ring differs from destroying key material; inspect product lifecycle docs and impact scope carefully.

For Secret Manager, confirm secrets are no longer referenced by apps, triggers, CI, or rotated credentials. Revoke IAM/trust bindings first, then clean up secrets once retention/audit rules permit. Never copy secret payloads into handover tables.

## 12. Checking Costs Before, During, and After Cleanup

### 12.1. Resources That Keep Billing Even After Apps Stop

| Resource Type | Lingering Cost Risk |
|---|---|
| Persistent disks / Hyperdisk | Disks survive after VM deletion |
| Static external IPs | Unused reserved static IPs incur charges per pricing |
| Compute reservations / sole-tenant nodes | Continue billing even when VMs are deleted or stopped |
| Snapshots and machine images | Ongoing storage charges |
| Artifact Registry | Stored container images and versions |
| Cloud SQL | Instances, storage, retained backups, or networking |
| Cloud Storage | Live, noncurrent versioned, and soft-deleted objects |
| GKE | Clusters/nodes, load balancers, persistent disks, and external services |
| Cloud Logging | Configured log retention, sinks, and storage |
| KMS or secret versions | Active versions, storage, and usage per product |

Compute reservations and committed-use discounts (CUDs) are distinct concepts; **deleting VMs does not cancel spending commitments**.

### 12.2. Billing Reports and Budgets

Before cleanup, inspect Cloud Billing Reports / Cost Table by project, service, SKU, labels, and time. Afterward, monitor spending trends across the next few reporting cycles.

**Alerts-only budgets are not hard spending caps.** They fire notifications at thresholds without stopping resources. Certain services support **spend-cap budgets** under specific rules and scopes; verify availability and workload impact before enabling. Never claim all budgets act as hard caps.

Usage and cost data lag behind real time, so charges can still appear after resources are deleted. Therefore:

- Never treat a billing chart minutes after deletion as proof spend dropped to zero.
- Use labels and cost attribution to spot orphaned resources.
- Watch resource charges, network egress, retained backups, and commitments.
- Monitor after closing a lab to catch missed items.

## 13. Six-Gate Safe Cleanup Workflow

### Gate 1 — Identify

Confirm exact project, organization, region, environment, and operator.

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe "$PROJECT_ID" \
  --format="yaml(projectId,projectNumber,lifecycleState)"
~~~

If the project contains shared or production resources, halt bulk cleanup and operate strictly on individually approved resources.

### Gate 2 — Inventory

Capture resources, IAM, dependencies, locations, data policies, and estimated monthly spend. Cross-check Asset Inventory against service APIs; mark any ownerless resource `UNKNOWN`.

### Gate 3 — Protect

Export/back up retained data, verify restore capability, check retention policies, and lock down security controls. Record image digests, Terraform revisions, and migration state.

### Gate 4 — Preview

Write a plan listing every resource to delete, every resource to keep, execution order, and impacts. For Terraform, generate a destroy plan; for Artifact Registry cleanup policies, run dry-run mode.

### Gate 5 — Approve and Execute

Obtain approvals matched to blast radius. Execute in small batches, log every outcome, and halt immediately if unexpected resources or API errors appear.

### Gate 6 — Verify and Close

Re-run inventory, verify data retention, budgets/costs, orphaned resources, leftover IAM bindings, and evidence. Mark `DONE` only after the handover recipient confirms.

~~~mermaid
flowchart TD
    A[Identify project + owner] --> B[Inventory + dependency map]
    B --> C{Any data or resource UNKNOWN?}
    C -- Yes --> D[Stop: clarify owner / retention]
    C -- No --> E[Backup, export, restore proof]
    E --> F[Preview deletion plan]
    F --> G{Approval and scope verified?}
    G -- No --> H[Stop: no destructive action]
    G -- Yes --> I[Disable triggers / execute small batches]
    I --> J[Re-inventory + test + billing follow-up]
    J --> K{Orphans / failed checks?}
    K -- Yes --> L[Investigate, reconcile, re-review]
    K -- No --> M[Close handoff ticket]
~~~

**A successful delete command does not mean overall cleanup succeeded** if dangling dependencies or unmigrated data remain.

## 14. CLI Example: Cloud Run and Eventarc Cleanup Plan

Suppose a lab has an Eventarc trigger `images-finalized` invoking Cloud Run service `image-worker`. Names below are placeholders, not real learner resources.

### 14.1. Read-Only Preflight

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT"
export REGION="asia-southeast1"
export TRIGGER="images-finalized"
export SERVICE="image-worker"

gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service="$SERVICE"
~~~

Check whether the trigger feeds a shared service, whether any backlog/retries remain, and whether any data owner requires retaining outputs.

### 14.2. Cleanup Commands After Approval

**Run only once the ticket is approved and preconditions pass:**

~~~bash
# 1) Stop event delivery before deleting the receiver.
gcloud eventarc triggers delete "$TRIGGER" \
  --project="$PROJECT_ID" \
  --location="$REGION"

# 2) Delete the Cloud Run service after confirming no consumer remains.
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Deleting a Cloud Run service **does not automatically delete** container images in Artifact Registry or Eventarc triggers. Deleting the service removes its revisions, yet the repository must still be managed separately per retention rules.

### 14.3. Verify

~~~bash
gcloud eventarc triggers list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud run services list --project="$PROJECT_ID"
gcloud artifacts repositories list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

If repositories remain, separate lab-only images from images used by other services or jobs. Never delete an entire repository just because one Cloud Run service was deleted.

## 15. Artifact Registry: Dry Runs and Sensible Retention

Artifact Registry stores container images, tags, digests, and versions. These persist after services are deleted or new images deploy.

A cleanup plan should:

1. Inventory repositories and packages by project and location.
2. Identify image digests referenced by Cloud Run, GKE, jobs, or rollback paths.
3. Define retention rules keeping required releases.
4. Define cleanup policies with explicit **delete conditions** and **keep rules**.
5. Run **dry run** and inspect the preview of candidate deletions.
6. Switch to active deletion only after approval and impact review.

**Illustrative preview example** once you have a reviewed policy file:

~~~bash
gcloud artifacts repositories set-cleanup-policies LAB_REPOSITORY \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --policy=REVIEWED_POLICY_FILE.json \
  --dry-run
~~~

No pre-built JSON file is supplied here; learners must author and review their own policy and never run commands with placeholders. Cleanup policies execute asynchronously in the background and take time to reflect. Keep policies protect release artifacts even if they match a delete rule.

Never delete an image digest still referenced by production or staging; a running revision may keep serving temporarily, yet subsequent scaling or redeployments can fail if the image is no longer fetchable per service behavior.

## 16. Compute Engine: VMs, Disks, Static IPs, and Reservations

### 16.1. Why Deleting the VM Alone Is Not Enough

A VM may attach boot/data disks with varying `autoDelete` flags, static external IPs, snapshots, and reservations. Once the VM disappears, several sub-resources can survive and keep billing.

Before deleting a VM:

~~~bash
gcloud compute instances describe LAB_VM \
  --project="$PROJECT_ID" --zone=LAB_ZONE

gcloud compute disks list --project="$PROJECT_ID"
gcloud compute addresses list --project="$PROJECT_ID"
gcloud compute reservations list --project="$PROJECT_ID"
~~~

In the instance description, inspect `disks.autoDelete`, IP addresses, metadata, service accounts, labels, and managed instance group (MIG) membership. If a VM belongs to a MIG, manage it through the MIG rather than deleting the VM manually and letting autohealing recreate it.

### 16.2. Cleanup Sequence After Approval

1. Confirm data disks are safe to delete or already backed up.
2. Check whether the VM belongs to a MIG or autoscaler.
3. Stop triggers or schedulers that recreate VMs.
4. Delete the VM under the approved disk-preservation/deletion setting.
5. Re-list unattached disks, reservations, static addresses, snapshots, and load balancers.
6. Delete each remaining resource **by explicit ID with separate approval**.
7. Verify billing and project inventory.

**Never use wildcards to wipe all disks or snapshots.** Snapshots can serve as required recovery points even after source disks are gone. Some instant snapshots bound to disks follow special lifecycles—read policies before deleting.

## 17. GKE: Cluster-Managed vs. Leftover Resources

GKE provisions many dependent resources: node pools / Compute instances, load balancers, external IPs, persistent volumes, disks, network endpoint groups, logging, and identities.

Before decommissioning a cluster:

- Export Kubernetes manifests, Helm values, or GitOps revisions marked for retention.
- Inspect persistent volumes and reclaim policies; identify shared storage.
- Check `Service type=LoadBalancer` and static IPs.
- Confirm workloads do not share production Cloud SQL, Pub/Sub, or buckets.
- Inspect node pools, autoscaling, cluster mode, and networking.
- Record verified backups prior to deletion.

Read-only commands:

~~~bash
gcloud container clusters list --project="$PROJECT_ID"

# With admin-verified kubeconfig/context:
kubectl config current-context
kubectl get namespaces
kubectl get services --all-namespaces
kubectl get pv
kubectl get pvc --all-namespaces
~~~

**Never delete PVCs/PVs or a cluster before checking reclaim policies and data.** Disks may either linger after cluster deletion or be wiped immediately per reclaim policy; plan for both outcomes.

After deleting an approved cluster, re-check GKE lists, Compute disks, addresses, forwarding rules, and storage resources. If the cluster used Shared VPC, never touch the host project's network.

## 18. Cloud SQL and Stateful Data

Cloud SQL is typically the highest-risk resource to delete in a lab because it holds state and may serve multiple components.

### 18.1. Pre-Deletion Checklist

- [ ] Instance matches exact project and region; owner approved `DELETE`.
- [ ] Zero active application connections or replication/backup consumers remain.
- [ ] Replicas and deletion protection checked.
- [ ] Final export or final backup created if required by policy.
- [ ] Sample restore tested or backup usability verified.
- [ ] Retained backups and retention TTLs documented.
- [ ] CMEK keys and recovery service agents checked.
- [ ] Private endpoints, PSC, DNS records, and network resources flagged for separate cleanup.

Some Cloud SQL deletion flows create a **final backup** retained for a set period, which can continue incurring charges. Never assume deleting an instance immediately purges all backups; read configuration policies and engine docs.

### 18.2. Never Delete Just to Test Whether Anyone Needs It

If unsure whether an instance is still in use, check metrics, connection logs, service configs, and owners. Never disable deletion protection or delete replicas just to force a delete command through.

## 19. Cloud Storage, Pub/Sub, Secret Manager, and Automation

### 19.1. Cloud Storage

~~~bash
gcloud storage buckets list --project="$PROJECT_ID"
gcloud storage ls "gs://LAB_BUCKET/"
gcloud storage buckets describe "gs://LAB_BUCKET"
~~~

These commands are read-only. During cleanup:

- Inspect live, noncurrent, and soft-deleted objects, retention policies, and holds.
- Export important data.
- Audit applications referencing the bucket or signed URLs.
- Delete objects/buckets strictly within approved scope without blind wildcards.
- Watch for soft-deleted storage charges and early-deletion fees where applicable.

### 19.2. Pub/Sub and Queues

Pub/Sub subscriptions may hold unacked messages; Cloud Tasks queues may hold pending tasks. Before deleting:

1. Stop producers, triggers, and schedulers.
2. Reconcile backlogs and business transactions.
3. Decide whether to drain, archive, or discard messages per data owner.
4. Only then delete subscriptions, topics, or queues.
5. Confirm no other event consumers share the topic.

A shared topic can serve consumers in another project. Never infer ownership solely from the project where the topic was created.

### 19.3. Secret Manager, IAM, and Service Accounts

Never delete a service account immediately upon stopping a workload if backup restore processes, sibling workloads, or audit requirements still depend on it. Revoke access in order:

- Remove IAM bindings for the stopped workload on target resources.
- Confirm the service account is no longer referenced by Cloud Run, GKE, Compute, Cloud Build, or triggers.
- Check for leftover keys and rotation/revocation policies.
- Delete the service account with approval and archive IAM change evidence.
- Check for dependent workload identity pools/providers or workforce mappings.

Handle secrets per retention and data policies. Never print secret values as "proof" of cleanup.

### 19.4. Scheduler, Eventarc, and Cloud Tasks

A recurring job can recreate deleted resources, hit dead endpoints, or rack up bills. Always locate and disable producers before deleting consumers. Document **cross-project** dependencies explicitly so nothing is missed.

## 20. Cleanup with Terraform and Infrastructure as Code

### 20.1. Never Blindly Destroy an Entire Workspace

Terraform manages infrastructure declaratively, yet `terraform destroy` can wipe **every resource in the active state**, not only the lab resources you just created. Never run it before verifying backend, workspace, project variables, and state contents.

Safe workflow:

~~~bash
terraform workspace show
terraform state list
terraform plan -destroy -out=destroy.tfplan
terraform show destroy.tfplan
~~~

These commands are examples for learners inside a **verified lab Terraform directory**, not to be run in STEP 4. Store plan files in controlled workspaces; plan files can contain sensitive values, so never commit them to public repositories.

Once an authorized approver reviews the resource list and approves:

~~~bash
terraform apply destroy.tfplan
~~~

Never use `-auto-approve` in environments with real data or shared infrastructure. If the state includes resources that must survive, adjust state/management boundaries via approved procedures instead of destroying indiscriminately.

### 20.2. State Drift and Out-of-Band Resources

Some resources are created via Console/CLI, Cloud Run source deploys, Kubernetes controllers, or service agents, so they **do not appear in Terraform state**. Always run Cloud Asset Inventory and service API inventories after destroying.

If Terraform fails to delete a resource due to dependencies, stop and investigate why. Never manually delete unrelated resources outside the plan just to force `apply` through.

For imported or shared resources, respect safeguards like `prevent_destroy` and state sources of truth. Terraform state can contain secrets—protect backends, access controls, and audit trails.

## 21. When Should You Delete an Entire Project?

In a **completely isolated sandbox project**, after inventorying and safeguarding data, shutting down the project can be simpler than deleting hundreds of individual items. Understand the consequences first:

- Project shutdown makes the project unusable and unlinks Cloud Billing.
- A **standard 30-day recovery window** exists before permanent deletion.
- Certain resources such as Cloud Storage or Pub/Sub may be purged sooner and are not guaranteed recoverable even if the project is restored within 30 days.
- Project IDs cannot be reused after permanent deletion.
- The project can continue counting against quotas until fully purged, and delayed usage charges can still post.
- Restoring a project does not automatically re-link Cloud Billing.

**Only shut down a project when the project owner confirms zero workloads, billing ties, data, or IAM/shared infrastructure must remain.** Never use project deletion to clean up a handful of lab resources inside a shared project.

Read-only status check:

~~~bash
gcloud projects describe "$PROJECT_ID" \
  --format="yaml(projectId,lifecycleState,parent)"
~~~

Project deletion commands are destructive and belong in a dedicated runbook with formal approvals and impact assessment; this lesson omits them from default cleanup scripts.

## 22. Re-Inventory After Cleanup

After execution, re-run the **exact same inventory queries** from before cleanup and compare:

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(assetType.basename(),name,location,labels)"

gcloud compute disks list --project="$PROJECT_ID"
gcloud compute addresses list --project="$PROJECT_ID"
gcloud run services list --project="$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"
gcloud storage buckets list --project="$PROJECT_ID"
~~~

Additionally:

1. Verify Eventarc, Scheduler, Pub/Sub, and Cloud Tasks no longer target deleted endpoints.
2. Check Artifact Registry, snapshots, static IPs, reservations, and backups.
3. Verify IAM bindings and service accounts hold no leftover privileges.
4. Verify retention: only approved, owned data remains retained.
5. Check error logs post-cleanup, especially sudden 404/403 spikes.
6. Monitor Billing Reports as usage data catches up to confirm spend drops.
7. Close the ticket with before/after inventories, outcomes, and any open exceptions.

### 22.1. Sample Cleanup Report

~~~text
TICKET: LAB-2026-042
PROJECT: demo-gcp-sandbox
OPERATOR: platform-engineer
APPROVER: project-owner
APPROVED SCOPE: Eventarc trigger + Cloud Run lab service
START / END: [UTC timestamps]

PRECONDITIONS:
- Data owner approval: PASS
- Backup/export if required: PASS
- Dependency review: PASS
- Terraform state review: N/A

ACTIONS:
- Trigger images-finalized: DELETED
- Cloud Run image-worker: DELETED
- Artifact Registry repository: KEPT (shared with another lab)
- Input/output buckets: KEPT until retention expiry

VALIDATION:
- Post-cleanup inventory: PASS
- Error logs: PASS
- Cost check: PENDING (usage data delay)
- IAM review: PASS
- Residual risks: retained storage costs

FOLLOW-UP OWNER: FinOps / Data owner
FOLLOW-UP DATE: YYYY-MM-DD
~~~

This is a **template**; never mark "cost = 0" immediately before retained storage and billing lags have settled.

## 23. Case Study: Handing Over and Cleaning Up a Java System on GCP

A team deployed a practice application consisting of:

- Cloud Run `orders-api` using Java/Spring Boot.
- An Eventarc trigger firing on uploads to an input Cloud Storage bucket.
- A Pub/Sub topic for notifications.
- A Cloud SQL instance holding sample orders.
- Artifact Registry storing container images.
- Secret Manager holding a test API key.
- A Compute Engine VM used as a temporary bastion/worker.
- Terraform managing part of the stack, with other resources created via `gcloud`.

### 23.1. Phase A — Operational Handover

The team determines `orders-api` is still needed for 14 days for demos. They must:

1. Document the architecture diagram, non-sensitive URLs, runtime service account, and dependency map.
2. Publish a runbook for inspecting Cloud Run logs and diagnosing 401/403, 5xx, and Cloud SQL connectivity.
3. Record exact project/region per service and IAM approvers.
4. Confirm internal SLAs, rollback procedures, and which data stays retained.
5. Record the demo expiration date and accountable owner in the ticket.
6. Preserve necessary backups/retention points; never delete while demos still depend on them.

### 23.2. Phase B — Preparing Cleanup

After 14 days, the project owner approves tearing down the lab, while the data owner asks to retain a PII-free export for evaluation.

The team executes:

1. Verify the export passed integrity checks, checksums, and retention rules.
2. Disable upload sources, schedulers, and the Eventarc trigger.
3. Wait for valid Pub/Sub backlog messages to drain.
4. Confirm Cloud Run and Cloud SQL have zero remaining consumers.
5. Compare Terraform plans against live resources.
6. Delete the app, VM, Cloud SQL, and linked resources per approval.
7. Retain the export and evidence under policy, and revoke unused IAM bindings.
8. Re-inventory to catch lingering static IPs, disks, images, snapshots, or topics.
9. Monitor bills over subsequent days rather than assuming immediate zero spend.

### 23.3. Issues Uncovered During Reconciliation

Post-cleanup inventory discovers:

- A detached persistent disk still incurring charges.
- An Artifact Registry repository still holding lab images.
- A static IP still reserved.
- The Eventarc trigger is gone, yet Pub/Sub topic `orders-events` still feeds another team's consumer.
- A retained Cloud SQL backup remains within its retention period.

**Right decision:** leave the shared topic intact and do not break backup retention policies. File follow-up tasks for the lab-owned disk, static IP, and artifacts, assign an owner to the retained backup, and track residual costs. Cleanup is **not an all-or-nothing pass** that sweeps exceptions under the rug; it succeeds when every resource has an explicit, accountable decision.

## 24. Common Mistakes and Anti-Patterns

| Anti-Pattern | Consequence | Better Practice |
|---|---|---|
| Sending only a Console link at handover | Recipients lack runbooks and owners | Versioned docs, inventory, and evidence |
| Assuming every `lab`-labeled resource is safe to delete | Deletes shared infrastructure | Approve by full resource name |
| Assuming Asset Inventory lists 100% of resources | Misses unsupported types or permission-hidden assets | Cross-check service APIs and billing |
| Deleting Cloud Run while leaving triggers active | Failed retries, log noise, extra cost | Stop event sources first |
| Deleting VMs without checking disks/IPs | Lingering storage/IP charges | Re-inventory Compute resources |
| Deleting buckets without checking soft delete | Continued storage spend or retention violations | Data review and bucket policy inspection |
| Deleting Cloud SQL "to see if anyone screams" | Irreversible data loss | Owner, backup/export, and connectivity checks |
| Running `terraform destroy` in the wrong workspace | Wipes unintended environments | Verify workspace, state, plan, and approval |
| Passing `--quiet` to skip warnings | Removes human safety gates | Confirm per approved scope |
| Destroying KMS key versions before backups | Unreadable encrypted backups | Check key dependencies and policies |
| Treating budget emails as hard spending caps | Budget overruns | Distinguish alerts-only from supported spend caps |
| Checking Billing immediately after deletion | False conclusions due to reporting lag | Follow up across multiple reporting cycles |
| Leaving old IAM bindings and service accounts intact | Long-lived excess privileges | Access reviews and least privilege |
| Deleting a shared project to clean up a lab | Destroys other teams' resources | Clean up scoped resources individually |
| Re-running non-idempotent cleanup scripts | Script failures or hits new resources | Reconcile state, verify preconditions, stop on drift |

## 25. Comprehensive Learner Checklist

### A. Handing Over a Running System

- [ ] Architecture diagram and data flows are up to date.
- [ ] Projects, regions, full resource names, and owners are documented.
- [ ] Image digests, Git commits, IaC revisions, and deployment pipelines are recorded.
- [ ] IAM, service accounts, secrets, KMS, and network dependencies are verified.
- [ ] Dashboards/alerts, SLIs/SLOs, and diagnostic/rollback runbooks are usable.
- [ ] Data owner confirmed backups, retention, and RPO/RTO.
- [ ] Recipient executed a verification check and confirmed takeover.

### B. Inventory and Deletion Planning

- [ ] Cloud Asset Inventory run and cross-checked with service APIs.
- [ ] Compute disks, IPs, reservations, and snapshots listed.
- [ ] GKE nodes, PVs, and load balancers listed if used.
- [ ] Cloud Run, Eventarc, Pub/Sub, Scheduler, and Tasks inventoried.
- [ ] Cloud SQL, Storage, Secret Manager, and Artifact Registry inventoried.
- [ ] Zero `UNKNOWN` resources remain in the deletion plan.
- [ ] Owners/approvers signed off on scope and blast radius.
- [ ] Retained data exported/backed up and verified.

### C. Execution and Verification

- [ ] Producers/triggers stopped before consumers where appropriate.
- [ ] Terraform destroy plans reviewed if using IaC.
- [ ] Destructive steps avoided blind wildcards and `--quiet`.
- [ ] Post-cleanup inventory completed.
- [ ] Redundant IAM bindings and service accounts cleaned up.
- [ ] Retained data/backups have owners and review dates.
- [ ] Logs show no fresh errors from deleted resources.
- [ ] Billing follow-up scheduled accounting for usage data lag.
- [ ] Tickets, evidence, and residual cost items archived.

## 26. Hands-On Practice Exercises

### Exercise 1 — Write a Runbook

A Spring Boot service on Cloud Run returns HTTP 503. Write a runbook covering trigger, operator identity, three read-only diagnostic steps, rollback criteria, verification, and escalation. Explain how to separate Cloud Run runtime faults from Cloud SQL or downstream dependency faults.

### Exercise 2 — Build an Inventory

In a sandbox project, create a table covering at minimum: Cloud Run, Artifact Registry, buckets, Pub/Sub, VMs, disks, static IPs, IAM service accounts, and Cloud SQL (if present). For each row, list full name, owner, location, `KEEP`/`DELETE`/`UNKNOWN` action, and estimated cost. Compare Cloud Asset Inventory against per-service `list` commands.

### Exercise 3 — Review a Cleanup Plan

A teammate proposes:

~~~text
1. Delete Cloud Run service.
2. Delete project immediately.
3. Later decide which Cloud Storage object to keep.
~~~

Identify at least five risks and rewrite the plan to incorporate data owner approval, exports, stopping triggers, dependency reviews, post-validation, and billing follow-up.

### Exercise 4 — Terraform Destroy Plan

In an authorized lab environment, confirm the right workspace/state and inspect `terraform plan -destroy`. Categorize resources missing from state, shared resources, stateful data resources, and resources to keep. **Do not run `apply`** without approval.

### Exercise 5 — Acceptance Report

Write a final report listing deleted resources, retained resources, residual spend, open alerts, follow-up dates, and the accountable recipient. Never mark cost verification `PASS` before billing reports catch up.

## 27. Self-Check Questions

1. Why does a successful deployment not mean a system is ready for handover?
2. How does an operational runbook differ from an architecture overview?
3. When should a resource labeled `lab` still not be deleted?
4. Why can Cloud Asset Inventory miss certain resources?
5. Why must you inventory disks and static IPs after deleting a VM?
6. Why does deleting a Cloud Run service not delete its Eventarc trigger or container images?
7. What must be verified before deleting a Cloud SQL instance?
8. When must retained backups be kept even if you want to cut costs?
9. Why can soft-deleted Cloud Storage objects continue incurring charges?
10. Why is an alerts-only budget not a hard spending cap?
11. Why must Terraform workspace and state be verified before running `destroy`?
12. What risks arise when deleting a consumer while an event subscription still holds backlog?
13. How does destroying a Cloud KMS key version affect encrypted backups?
14. When should you shut down an entire project vs. deleting individual resources?
15. If post-cleanup inventory shows zero VMs yet Billing keeps rising, what do you check?
16. What evidence proves cleanup succeeded and recipients can safely take over?

## References

- [Cloud Asset Inventory: Search for resources](https://docs.cloud.google.com/asset-inventory/docs/search-resources)
- [Cloud Asset Inventory: searchAllResources API](https://docs.cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/searchAllResources)
- [Resource Manager: Delete and restore projects](https://docs.cloud.google.com/resource-manager/docs/delete-restore-projects)
- [Cloud Billing: Budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Billing: Spend cap budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
- [Cloud Billing: Billing reports](https://docs.cloud.google.com/billing/docs/how-to/reports)
- [Compute Engine: Delete instances and preserve resources](https://docs.cloud.google.com/compute/docs/instances/deleting-instance)
- [Compute Engine: Persistent disks deletion](https://docs.cloud.google.com/compute/docs/reference/rest/v1/disks/delete)
- [Cloud Run: Manage and delete services](https://docs.cloud.google.com/run/docs/managing/services)
- [Eventarc Standard: Manage triggers](https://docs.cloud.google.com/eventarc/standard/docs/managing-triggers)
- [Artifact Registry: Configure cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Cloud Storage: Delete buckets](https://docs.cloud.google.com/storage/docs/deleting-buckets)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Cloud SQL: Delete instances](https://docs.cloud.google.com/sql/docs/mysql/delete-instance)
- [Cloud KMS: Destroy and restore key versions](https://docs.cloud.google.com/kms/docs/destroy-restore)
- [Cloud KMS: Delete resources](https://docs.cloud.google.com/kms/docs/delete-kms-resources)
- [Terraform CLI: Destroy infrastructure](https://developer.hashicorp.com/terraform/cli/commands/destroy)
- [Google Cloud Well-Architected Framework: Operational excellence](https://docs.cloud.google.com/architecture/framework/operational-excellence)
