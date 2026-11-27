# Revisions, Traffic Splitting, and Rollbacks in Cloud Run

A Java `orders-api` application on Cloud Run is serving thousands of requests per minute. The team releases a new version to optimize order processing, but wants only **a small fraction of users** exposed before scaling up. If error rates spike, the team needs to **shift requests back to the stable version** without waiting to rebuild a container. This is the domain of **revisions, traffic splitting, and rollbacks**.

Cloud Run manages multiple **immutable revisions** of the same service. Each revision encapsulates an image version and runtime configuration, while the service distributes request percentages across revisions. This enables **canary releases**, **blue/green deployments**, testing a single revision with a **traffic tag**, and **traffic rollbacks** during incidents.

This lesson belongs to the **Cloud Run** chapter of the `CLOUD_PROVIDERS_GCP` module, connecting application deployment with IAM, VPC, Artifact Registry, GKE/Compute Engine, Cloud SQL, Cloud Storage, reliability monitoring, and cost. The content focuses on **Cloud Run services receiving HTTP requests**, and traffic-split commands do not apply by default to **Cloud Run jobs or worker pools**.

## Learning Objectives

After this lesson, you can:

1. Explain the differences between **service**, **revision**, **latest revision**, **serving revision**, **tag**, and **image digest**.
2. Understand why revisions are immutable while **traffic distribution** remains mutable.
3. Deploy a new revision at **0% traffic** and attach a tag for direct smoke testing.
4. Shift traffic incrementally in controlled steps such as 1% → 5% → 25% → 100%.
5. Roll back to a stable revision via `gcloud` or the Console without rebuilding.
6. Distinguish **application/traffic rollbacks** from database, schema, secret, and external side-effect rollbacks.
7. Read request counts, error rates, latency, and logs per revision, and define rollout stop criteria.
8. Evaluate the impact of tags, min instances, autoscaling, and IAM permissions.
9. Author a canary/rollback runbook with verification steps and hands-on exercises.

## 1. Service and Revision Model

A **Cloud Run service** is the logical endpoint that clients call. Whenever you deploy a new image or change **revision template configuration** (such as environment variables, container image, CPU/memory, or runtime service account), Cloud Run creates an **immutable revision**.

~~~mermaid
flowchart TD
    CLIENT["Client / HTTP request"] --> URL["Cloud Run service URL<br/>orders-api"]
    URL --> T{"Traffic configuration"}
    T -->|"95%"| R1["Stable revision<br/>orders-api-00010-abc"]
    T -->|"5%"| R2["Canary revision<br/>orders-api-00011-def"]
    TAG["Tag URL: canary---..."] -->|"Direct access"| R2
    R1 --> DB[("Cloud SQL / Storage / Pub/Sub")]
    R2 --> DB
~~~

| Concept | Meaning |
| --- | --- |
| **Service** | Shared name and URL; configures request routing across revisions |
| **Revision** | Immutable snapshot of the image and revision-level settings at deploy time |
| **Latest created revision** | Most recently created revision; not guaranteed to be ready or receiving traffic |
| **Latest ready revision** | Most recent revision marked ready by Cloud Run |
| **Serving revision** | Revision currently allocated greater than 0% traffic by the service |
| **Traffic split** | Routing requests across multiple revisions by percentage |
| **Traffic tag** | Label generating a dedicated URL to call a specific revision, even at 0% traffic |
| **Image digest** | Content-addressable container image identifier; unlike image tags, it cannot be reassigned |

Example service with two revisions:

~~~text
orders-api-00010-abc   image .../orders-api@sha256:AAA...   traffic 100%
orders-api-00011-def   image .../orders-api@sha256:BBB...   traffic   0%
                                                     tag canary
~~~

The newest revision may **receive zero requests from the main service URL**. This is normal when deploying with `--no-traffic`.

### 1.1. Which Changes Create a Revision?

| Operation | Creates a new revision? |
| --- | --- |
| Deploying a new image | **Yes** |
| Changing environment variables/secret references in the revision template | **Yes** |
| Changing CPU/memory/timeout/concurrency in the revision template | **Yes** |
| Changing traffic split from 90/10 to 50/50 | **No** |
| Adding/removing a tag in traffic configuration | **No** |
| Shifting traffic back to an older revision | **No** |
| Certain service-level settings (e.g., service-level min instances) | **Not necessarily**; depends on configuration level |
| Cloud SQL data or Cloud Storage objects changing | **No** |

**An immutable revision does not mean the surrounding system is immutable**: Cloud SQL schemas, referenced secrets, IAM, external APIs, VPCs, and queues can still change after a revision is created.

### 1.2. A Revision Is Not a Complete Backup

Cloud Run retains older revisions for routing and rollbacks. However, Cloud Run enforces a limit of **1,000 revisions per service**; once exceeded, older revisions may be automatically deleted. A revision does not contain backups of Cloud SQL, Cloud Storage, or external state. For reproducible releases, retain **image digests in Artifact Registry**, release manifests, and data recovery plans.

## 2. How Does Traffic Splitting Work?

A traffic split specifies the **percentage of requests sent to each revision** via the service URL. For example:

| Revision | Percentage | Expected requests out of 10,000 |
| --- | ---: | ---: |
| Stable (A) | 95% | Roughly 9,500 |
| Canary (B) | 5% | Roughly 500 |
| Total | 100% | 10,000 |

These numbers are **statistical expectations**, not guarantees of exact request, user, or session counts. At low traffic, observed percentages can skew; a single client may also send consecutive requests to different revisions.

**Limitations to remember:**

- Splitting happens **per request**, not by user, account, or order by default.
- If **session affinity** is enabled, actual distribution can be affected; consult the relevant guidance.
- Traffic updates are **not instantaneous across all connections**; in-flight requests continue processing, and during propagation requests may hit either the old or new revision.
- Revisions can share the same database and queues, so **data and schemas** must remain compatible while both A and B are active.
- Cloud Run traffic splitting is not a per-user feature flag; if you need cohort-based testing, implement it via an API gateway, feature flags, or application logic.

### 2.1. Canary and Blue/Green

**Canary:** release B at 1–5%, measure health, then gradually ramp to 25%, 50%, and 100% once criteria pass.

**Blue/green:** keep A (blue) at 100%, deploy B (green) at 0%, test via its tag URL, then switch most or all traffic to B. Using a tag for smoke testing **does not automatically shift traffic** on the main service URL.

~~~mermaid
flowchart LR
    A["A stable at 100%"] --> B["Deploy B at 0% + tag"]
    B --> C["Smoke test B directly"]
    C --> D{"Pass gate?"}
    D -->|Yes| E["B 5% / A 95%"]
    E --> F{"SLOs and business metrics met?"}
    F -->|Yes| G["Ramp 25% → 50% → 100%"]
    F -->|No| R["Rollback A 100%"]
    D -->|No| R
~~~

## 3. Preparation Before Modifying the Service

**Lab assumptions:** project `PROJECT_ID`, region `asia-southeast1`, service `orders-api` already exists, only authorized principals can deploy; two tested images exist in Artifact Registry.

~~~text
SERVICE = orders-api
REGION  = asia-southeast1
OLD_REV = orders-api-00010-abc      # example, replace with actual name
NEW_REV = orders-api-00011-def      # example, retrieve after deploy
IMAGE_B = asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST_B
~~~

**These commands can alter production traffic and incur charges.** Run only in a lab project or an approved change window; never treat illustrative revision names as real existing revisions.

### 3.1. IAM, Artifact Registry, and Identities

The principal deploying or updating traffic needs appropriate Cloud Run permissions, typically `roles/run.developer`; when deploying with a service account, `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs`) is also required. For images from Artifact Registry, the identities pulling the image must have read permissions, especially in cross-project setups.

**Never grant Owner/Editor just to run a traffic update.** Verify the active account, project, region, and service before acting:

~~~bash
gcloud auth list
gcloud config get-value project
gcloud run services list \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

### 3.2. Record Current State

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="yaml(status.traffic,status.latestReadyRevisionName,status.latestCreatedRevisionName)"

gcloud run revisions list \
  --service=orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Verify **currently serving revision A**, exact revision names, image digests, traffic split, service URL, IAM/ingress, health status, and the rollback target. Store configuration outside production per GitOps/change records; avoid placing tokens/secrets in logs or reports.

### 3.3. Pick the Rollback Target Before Deploying

Never assume **the previous revision** is automatically safe. Pick a revision that passed smoke tests, has a verified image digest, and remains compatible with current schemas, secrets, and permissions. Record that revision name in the runbook.

## 4. Deploy Revision B at 0% and Attach a Traffic Tag

Cloud Run supports deploying a new revision **receiving no traffic from the service URL**; attach the `canary` tag so testers can call B directly.

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST_B \
  --no-traffic \
  --tag=canary \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

**Deployment notes:**

- Service `orders-api` must exist and already have a stable revision A; `--no-traffic` prevents exposing B immediately to users via the service URL.
- Replace `FULL_DIGEST_B` with the real sha256 digest; `--image` accepts digest references.
- The tag must be valid; the tagged URL is generated by Cloud Run. **Do not guess the URL from the service name alone**, as URL formats can vary.
- If changing runtime identity, networking, secrets, or resource limits at the same time, assess their impact; avoid bundling unrelated changes into a single canary.
- If deploying from source rather than an image, `gcloud run deploy orders-api --source=. --no-traffic --tag=canary` triggers a **new build**; it is not a promotion of an already tested image.

After deploying:

~~~bash
gcloud run revisions list \
  --service=orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="yaml(status.traffic)"
~~~

Retrieve the **exact `NEW_REV`** from the revision list or traffic config. `latestReadyRevisionName` shows the newest ready revision, but when multiple pipelines deploy concurrently, do not rely blindly on `LATEST`.

## 5. Testing Revision B via the Tag URL

The `canary` tag creates a dedicated URL for revision B, even while B receives **0% service traffic**. *Illustrative* URL example:

~~~text
https://canary---orders-api-123456789012.asia-southeast1.run.app
~~~

Fetch the real URL from the Cloud Run Console or the service's `status.traffic[].url` instead of guessing the hostname. A tag URL does not make the service **public**: Cloud Run service IAM and ingress rules still apply.

### 5.1. Smoke Tests Should Include

- `GET /health` or `/actuator/health` (if the app exposes such endpoints).
- Sample HTTP requests **with no side effects**, validating JSON schema/content type.
- Connectivity to Cloud SQL, Cloud Storage, Pub/Sub, and Secret Manager using real runtime permissions.
- An order-creation flow **in a test environment** or using isolated test data.
- Logs confirming revision B handled the request rather than accidentally hitting A.

For a **private Cloud Run service**, callers need `roles/run.invoker` or equivalent permission. When clients use an ID token, **`aud` must be the main service URL** (or configured custom audience), **even when sending requests to the tag URL**.

~~~bash
# SERVICE_URL is the main service URL, NOT the tag URL.
# TAG_URL comes from Cloud Run service traffic status.
gcloud auth print-identity-token --audiences=SERVICE_URL
# A caller with Invoker permission uses a valid token as:
# Authorization: Bearer ID_TOKEN
# GET TAG_URL/health
~~~

Never print real tokens into documentation, CI logs, or pipeline artifacts. When testing from a developer account, `gcloud auth print-identity-token --audiences` has support conditions depending on credential type; use service account impersonation or client libraries with ADC as appropriate. Never change IAM to `allUsers` "just to make testing easier."

### 5.2. Tag URLs Do Not Represent Traffic Percentages

Testing B via a tag URL executes on B, but **does not increase its traffic share on the main service URL**. Conversely, once a 5% canary starts, callers hitting the main service URL can reach B without using the tag URL.

## 6. Splitting Traffic by Revision Name

Once smoke tests on B pass, shift traffic from A to B in steps. **The commands below alter live routing.** Run them only when revisions A/B are verified and within an approved change window.

### 6.1. 95% A / 5% B

~~~bash
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=95,orders-api-00011-def=5 \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

This illustrative example assumes the revision names from Section 3. In a real environment, **replace both with actual revision names**. Percentages must sum to **100%**.

### 6.2. Ramp to 25%, 50%, then 100%

~~~bash
# Once 5% meets SLO criteria:
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=75,orders-api-00011-def=25 \
  --region=asia-southeast1 --project=PROJECT_ID

# After 25% meets criteria:
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=50,orders-api-00011-def=50 \
  --region=asia-southeast1 --project=PROJECT_ID

# When full release is approved:
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00011-def=100 \
  --region=asia-southeast1 --project=PROJECT_ID
~~~

**After each adjustment**, verify the traffic assignment and monitor for an adequate time/request volume. Do not advance automatically just because the CLI command returned 0; the deciding question is: **does B satisfy health/SLOs and business logic?**

### 6.3. `--to-latest` Differs from Pinning a Revision

~~~bash
gcloud run services update-traffic orders-api \
  --to-latest \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

`--to-latest` routes 100% of traffic to the **latest revision** and keeps routing pinned to **latest/future revisions**. Thus a subsequent deployment may automatically receive traffic. In CI/CD setups with multiple pipelines, that can cause **unintended** cutovers.

For strictly controlled rollouts, specify **explicit revision names** in `--to-revisions` instead of relying on `LATEST`. Traffic splits pointing to older revisions can persist across subsequent deployments; verify the current policy before every release.

## 7. Rollback: Shift 100% of Traffic Back to Revision A

If canary B spikes errors or breaks business rules, stop ramping B and roll back:

~~~bash
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=100 \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Verify:

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --format="yaml(status.traffic)"

gcloud run revisions list \
  --service=orders-api \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

In the Console: **Cloud Run → Services → orders-api → Revision history → Manage traffic → Send all traffic to one revision**, select A, and save.

**What a traffic rollback does and does not do:**

| Rollback to A | Result |
| --- | --- |
| Routing new requests via service URL | Redirects target to A; routing updates take time to propagate |
| In-flight requests already executing | May continue running on B until completion |
| Revision B image/config | B still exists and may retain tags |
| New revision | **Not created** merely by changing traffic |
| Database schema/data | **Not automatically reverted** |
| Published messages, emails, payments | **Not undone** |
| External IAM/secrets/Cloud SQL state | **Not automatically changed** |
| Pre-rollback health check on A | Cloud Run **does not re-run deployment health checks or dependency checks** before switching routing |

Never declare a rollback "completely successful" simply because the service shows `100% A`. Observe real requests, latency, error rates, database connections, and business data after the switch.

### 7.1. When A Is No Longer Database-Compatible

Suppose B migrated a `status` column from an old enum to a new schema, while A only reads the old schema. Rolling traffic back to A can make errors **increase instead of decrease**.

Therefore use **expand–migrate–contract**:

1. Deploy a new schema **compatible with both A and B** (expand).
2. Deploy B and observe the canary.
3. Migrate data via a controlled job, with backups/PITR where applicable.
4. Remove the old schema (contract) **only after rolling back to A is no longer needed**.

If data changes are irreversible, your rollback plan must include runbooks for databases, queues, and side effects—not just `update-traffic`.

## 8. Monitoring the Canary Per Revision

Do not measure only aggregate service metrics because A handling 95% of traffic can **mask errors on B**. Break down metrics by `revision_name`.

| Signal group | What to monitor |
| --- | --- |
| **Traffic** | Request count and actual share received by B |
| **Availability** | 5xx rate, startup errors, timeouts, incomplete requests |
| **Latency** | p50, p95, p99 per revision and endpoint |
| **Runtime** | CPU/memory, instance count, concurrency, cold starts visible in logs/metrics |
| **Dependencies** | Cloud SQL connections, Pub/Sub backlog, Cloud Storage errors |
| **Business** | Successful orders, duplicate payments, invalid state transitions |
| **Costs** | CPU/memory billing, min instances, logs, egress |
| **Deploy safety** | Image digest, revision readiness, secret access, IAM and network changes |

Cloud Monitoring provides **Cloud Run metrics** such as request count, request latencies, and instance count. Select metrics by service and filter/group by **revision**, status class, and region where available.

### 8.1. Logs Explorer Filter

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
resource.labels.revision_name="orders-api-00011-def"
severity>=ERROR
~~~

This filter helps isolate errors on B. You can add `httpRequest.status>=500` or trace/request IDs based on your actual log schema. Never conclude "B has no errors" after only 3 requests.

### 8.2. Example Canary Decision

Suppose over 20 minutes:

| Metric | Stable A | Canary B 5% | Illustrative threshold |
| --- | ---: | ---: | --- |
| Request count | 19,000 | 1,000 | Sufficient sample on B to inspect trends |
| HTTP 5xx rate | 0.2% | 2.0% | No more than 0.5% |
| p95 latency | 180 ms | 420 ms | No more than 300 ms |
| Order creation success rate | 99.8% | 98.7% | No lower than 99.5% |

**Decision:** roll back B because it breached error and latency thresholds; do not increase traffic. These numbers are **purely illustrative**, demonstrating how to define gates. When B has only 1–10 requests, wait for sufficient samples or use active testing rather than treating tiny percentages as conclusive.

### 8.3. Updates Are Not Instantaneous

Cloud Run explicitly documents that routing updates are **not instantaneous** and do not abort in-flight requests. Consequently, right after a rollback command, B may still appear in logs or metrics for a short period. Check **request timestamps**, open connection lifetimes, traffic hitting the tag URL, and metric ingestion lag before concluding a rollback failed.

## 9. Tags, Min Instances, and Cost

A revision receiving zero requests normally **consumes no compute resources and incurs no compute charges** if it has no min instances configured and receives no tag traffic. However:

- With **service-level minimum instances**, Cloud Run allocates minimum instances proportionally across **revisions in the traffic split**. A 0% tagged revision does not automatically receive service-level min instances.
- With **revision-level minimum instances**, a tagged revision can still keep min instances warm **even at 0% traffic**, incurring costs.
- Test requests via a tag URL still run containers and can incur request/compute/logging charges.
- If **instance-based billing** or specialized scaling settings are enabled, idle/runtime charges differ from request-based billing.
- Stale tags left behind after testing leave dedicated paths to older revisions; govern IAM/ingress and remove tags when no longer needed.

Remove the `canary` tag once testing finishes:

~~~bash
gcloud run services update-traffic orders-api \
  --remove-tags=canary \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

This command **removes the tag** and does not alter traffic splits by itself. Before removing it, confirm no monitoring probe or authorized tester still depends on that URL.

**Cost optimization does not mean minimizing canary percentage at all costs.** For a Java revision B with noticeable cold starts, a 1% sample might starve of data or be skewed by cold starts; pre-warming/min instances may be justified based on approved needs and clear cost measurements.

## 10. Safe Release Workflow with CI/CD

A production canary pipeline should be orchestrated by a **single source of traffic changes** (GitOps/IaC/Cloud Deploy or an approved pipeline), avoiding two competing pipelines mutating the service.

~~~mermaid
flowchart TD
    SOURCE["Git commit + tests"] --> IMAGE["Build/push Artifact Registry<br/>record image digest"]
    IMAGE --> DEPLOY["Deploy B --no-traffic --tag=canary"]
    DEPLOY --> SMOKE["Smoke test tag URL, auth, and dependencies"]
    SMOKE --> GATE{"Tests pass?"}
    GATE -->|No| CLEAN["Halt release, keep A 100%"]
    GATE -->|Yes| STEP["Canary B 5%"]
    STEP --> OBS{"SLOs + business gates met?"}
    OBS -->|Yes| RAMP["Ramp 25% → 50% → 100%"]
    OBS -->|No| ROLLBACK["Rollback A 100%"]
    RAMP --> FINAL["Verify, save release record"]
~~~

**Mandatory controls:**

1. **Build once, deploy digest:** record Git SHA, image digest, config version, and release ID.
2. **Test in staging first:** integration/load/security tests before deploying to production at 0%.
3. **Clear separation of permissions:** build identity pushes to registry, deployer updates service/traffic, runtime identity accesses only required APIs.
4. **Database backward compatibility:** A/B share external resources; avoid one-way schema changes during a canary.
5. **Bounded progression:** each traffic step needs sufficient request samples and an adequate observation window.
6. **Bounded automated stop/rollback:** alert/gate on SLOs and business metrics without letting a pipeline loop rollbacks endlessly.
7. **Release audit:** record old/new revision names, traffic percentages, timestamps, approvers, and smoke test evidence.
8. **Rollback drill:** rehearse shifting traffic back to A in a test environment, including handling side effects.

### 10.1. Managing with Terraform or YAML

Cloud Run `spec.traffic` can express revisions and percentages:

~~~yaml
# Excerpt from Cloud Run Service (Knative API)
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  traffic:
    - revisionName: orders-api-00010-abc
      percent: 95
    - revisionName: orders-api-00011-def
      percent: 5
      tag: canary
~~~

This is a **traffic-focused excerpt**, not a complete standalone service manifest for creating a service from scratch. If using `gcloud run services replace`, export and inspect the **entire current service YAML** before replacing; accidentally changing template or IAM-related configuration can create an unintended revision.

With Terraform `google_cloud_run_v2_service`, traffic blocks use `type`/`revision` or `tag` per the provider schema. **Never mutate traffic via CLI and Terraform simultaneously** if a pipeline will `apply` the old config right back; choose one governed source of state.

## 11. Common Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| After deploying B, service URL still serves A | Deployed with `--no-traffic` | Expected behavior; use tag URL or `update-traffic` once approved |
| Tag URL returns `403` | Private service, caller missing Invoker/ID token, or wrong token audience | Check IAM and use the **main service URL as audience**, not the tag URL |
| Tag URL returns `404` | Guessed wrong URL, tag not attached, or tag removed | Retrieve actual URL from service traffic status |
| B receives fewer requests than expected at 1% | Low request volume, session affinity, propagation delay | Gather sufficient samples and verify routing |
| Called `--to-latest`, then next deploy goes straight to production | Routing points to `LATEST` | Pin explicit revision names and check traffic policy |
| Shifted traffic but no new revision appeared | Only traffic changed, no image/config deploy | Check revision list; normal behavior |
| B returns 5xx while A is healthy | App config, secret, dependency/schema, cold start | Compare logs/metrics per revision |
| After rolling back to A, B still appears in logs | In-flight requests, tag URL calls, or propagation | Check request timestamps, tag traffic, and update status |
| Rolling back to A causes database errors | B's migration is incompatible with A | Use expand–contract and a DB rollback runbook |
| Canary causes Cloud SQL to hit connection limits | A and B scale independently | Bound instances/concurrency, connection pools, DB quotas |
| 0% tagged revision still incurs charges | Revision-level min instances or test requests | Inspect scaling/billing config and remove tag when done |
| `update-traffic` fails with `403`/`404` | Wrong project/region/IAM/service or revision name | Verify context, role, and list revisions |
| Traffic gets overwritten by another pipeline | IaC/Cloud Deploy/CI racing with manual commands | Identify the single orchestrator and lock rollout |

## 12. End-to-End Scenario: Canarying Orders API

**Context:** Java 21 `orders-api` on Cloud Run using Cloud SQL PostgreSQL, Pub/Sub, and Cloud Storage. Revision A handles 100% traffic. Revision B introduces a new promotion algorithm and writes an additional metadata field.

**Requirements:** zero downtime, limit blast radius of bugs in B, and fast rollback.

| Phase | Traffic | Gate to proceed |
| --- | --- | --- |
| Prepare | A 100%, B does not exist | Tests/scans, image digest, compatible DB schema |
| Deploy | A 100%, B 0% + tag | Smoke tests / tag URL verified |
| Canary 1 | A 99%, B 1% | No critical errors, adequate request sample |
| Canary 2 | A 95%, B 5% | 5xx, p95, business conversion meet targets |
| Canary 3 | A 75%, B 25% | Cloud SQL/pool/queue remain stable |
| Complete | B 100% | SLOs met throughout observation window |
| On failure | A 100% | Verify rollback and business data integrity |

**Key design point:** both revisions share the **same Cloud SQL database**, so schema additions must remain compatible with A; never let B write records A cannot read. Likewise, 5% traffic does not mean Cloud SQL uses exactly 5% of the connection pool: instance counts and connection behavior also depend on cold starts and concurrency.

After the release, record: digests of A/B, traffic steps, logs/metrics, SLO outcomes, start/end timestamps, and approver. Remove the canary tag when no longer needed; do not immediately delete revision A while it remains part of the rollback plan.

## 13. Self-Check Exercises

**Question 1.** Revision B is deployed with `--no-traffic`, and the service URL still returns A. Did the deploy fail?

*Suggested answer:* No; B was created with 0% allocation and can be tested via its tag URL.

**Question 2.** Does changing the A/B split from 90/10 to 50/50 create a new revision?

*Answer:* No, that only updates the service's traffic configuration.

**Question 3.** Does a 5% canary guarantee that exactly 5% of users are served by B?

*Answer:* No. Distribution is per-request and subject to statistical variance and session affinity.

**Question 4.** Is the latest revision always serving 100% of traffic?

*Answer:* No. It could be newly deployed at 0% or not yet ready.

**Question 5.** To test B while B is at 0%, should you use the service URL or the tag URL?

*Answer:* The tag URL targets B directly without altering main service traffic.

**Question 6.** For a private Cloud Run service, what should the JWT audience be when calling a tag URL?

*Answer:* The **main service URL** (or configured custom audience), not the tag URL.

**Question 7.** Does `--to-revisions=A=100` immediately abort requests currently running on B?

*Answer:* No. In-flight requests may continue; routing updates also take time to propagate.

**Question 8.** Does Cloud Run re-run A's deployment health check before shifting rollback traffic back to A?

*Answer:* No. You must independently verify external dependencies and application behavior.

**Question 9.** If B already ran a migration dropping a column that A requires, is a traffic rollback guaranteed to be safe?

*Answer:* No. You need backward-compatible schemas, expand–contract, and a data rollback runbook.

**Question 10.** Is a 0% tagged revision always free of compute charges?

*Answer:* No. Revision-level min instances or requests sent to the tag URL can incur charges.

**Question 11.** Why compare B's 5xx rate instead of looking only at total service 5xx?

*Answer:* A large traffic share on A can mask a high error rate on B.

**Question 12.** Why should production rollouts pin a revision name or image digest instead of casually using `LATEST`/`:latest`?

*Answer:* `LATEST` can shift to a later deployment, and image tags can be overwritten. Pinning ensures exact artifact and routing reproducibility.

## 14. Pre-Production Checklist

- [ ] Verify project, region, service, owner, and deploy/traffic permissions.
- [ ] Record old revision name, image digest, runtime config, and rollback target.
- [ ] Confirm CI tests, image scans, smoke tests, and A/B-compatible database migrations.
- [ ] Deploy B at **0% + tag**, without shifting traffic immediately.
- [ ] Test tag URL with valid IAM/ingress; use main service URL as token audience.
- [ ] Each traffic step has explicit percentages summing to 100%.
- [ ] Define SLO thresholds, sufficient sample sizes, and per-**revision** and business metrics.
- [ ] Verify Cloud SQL connections, Pub/Sub, Cloud Storage, secrets, and VPC egress.
- [ ] Prepare the 100% rollback command to A and a rollback verification procedure.
- [ ] Understand that traffic rollback does not undo database writes, messages, or side effects.
- [ ] Avoid `--to-latest` unless future deployments should automatically receive traffic.
- [ ] Check service/revision-level min instances, active tags, and costs.
- [ ] Ensure CI/CD, GitOps, or Terraform acts as the single source of truth for traffic.
- [ ] Retain A's digest/revision for the rollback window; remove the canary tag when done.
- [ ] Save the release record and rehearse rollbacks periodically.

## 15. Conclusion

**A Cloud Run revision is an immutable release; traffic configuration is the routing switch.** By deploying with `--no-traffic`, attaching tags, shifting request percentages gradually, and rolling back with `--to-revisions=OLD_REV=100`, teams can release Java services incrementally without rebuilding images to revert to a stable version. However, rollback only adjusts **request routing**: data, events, and downstream dependencies must stay compatible for a rollback to be truly safe.

## Official References

- [Manage Cloud Run revisions](https://cloud.google.com/run/docs/managing/revisions)
- [Rollbacks, gradual rollouts and traffic migration](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [gcloud run services update-traffic](https://cloud.google.com/sdk/gcloud/reference/run/services/update-traffic)
- [gcloud run deploy](https://cloud.google.com/sdk/gcloud/reference/run/deploy)
- [Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Configure minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)
- [Monitor Cloud Run services](https://cloud.google.com/run/docs/monitoring)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
