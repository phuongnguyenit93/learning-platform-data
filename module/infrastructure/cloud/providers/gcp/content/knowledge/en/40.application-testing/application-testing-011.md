# Hands-On Testing Pipeline with Quota and Cost Controls

An automated testing pipeline catches bugs early, yet if every pull request provisions a database, fires hundreds of parallel tasks, and leaves test environments running afterward, teams hit two problems: exhausting Google Cloud quotas and incurring unnecessary charges. Conversely, setting limits too low stalls tests, slows down pipelines, and blocks releases.

This lesson guides you through building a **Java/Spring testing pipeline on Google Cloud with an intentional resource budget**. Most tests run locally inside Cloud Build using mocks or emulators; only targeted integration steps hit live services in a staging project. Paid steps enforce trigger conditions, deadlines, concurrency caps, IAM scoping, isolated test data, and cleanup workflows.

This lesson belongs to the **GCP Application Testing** chapter of the **CLOUD_PROVIDERS_GCP** module. Knowledge of projects, IAM, Cloud Run, storage, databases, reliability monitoring, and cost management transfers directly to applying the same testing workflow to real workloads.

## 1. Expected Outcomes

After this lesson, you will be able to:

- Select the right testing tier: unit, component, emulator-based integration, and smoke/end-to-end against live services.
- Configure Cloud Build for Maven/Spring applications with per-step and overall build timeouts.
- Bound trigger frequency, concurrent resources, and permissions to create billable resources.
- Separate low-cost pull-request pipelines from gated staging pipelines requiring permissions and approvals.
- Design a Cloud Run Job for testing with explicit task count, parallelism, retries, and timeout.
- Monitor quotas, total build-minutes, and costs by project/label, and set budget alerts.
- Handle `RESOURCE_EXHAUSTED`, `429`, timeouts, retry storms, and uncleaned test environments.
- Evaluate test outcomes alongside actual cost before increasing run frequency or machine sizes.

## 2. Sample Problem and Practice Boundaries

Suppose a team builds the `checkout-api` application using Java 21 and Spring Boot. The application uses Cloud Run, Pub/Sub, Cloud SQL, and Cloud Storage. The team needs fast defect feedback on every pull request while also verifying live Google Cloud interactions prior to release.

Three pipeline modes are proposed:

| Run Type | Trigger | Test Scope | GCP Resources |
|---|---|---|---|
| Fast PR | Every pull request with code changes | Unit, component, integration with fakes/emulators | Cloud Build worker only, minimal logs and artifacts |
| Controlled staging | Merge to main, scheduled, or approved manual run | Smoke/API contracts against live services | Staging project; small task count and tight deadline |
| Release | After staging passes, with approval | Selective tests and deployment verification | Release project under separate permission boundaries |

**Goal of the PR pipeline:** catch most bugs within minutes without creating persistent billable resources. **Goal of the staging pipeline:** verify behaviors emulators cannot replicate, such as IAM, networking, quotas, TLS, and managed-service behavior.

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Static check + unit test"]
    B --> C["Component/integration with fakes and emulators"]
    C --> D{"Pass?"}
    D -->|No| E["Report error and stop"]
    D -->|Yes| F["Allow review / merge"]
    F --> G["Trigger controlled staging"]
    G --> H["Check budget, quota, permissions, and approval"]
    H --> I{"Eligible?"}
    I -->|No| J["Pause / cancel run"]
    I -->|Yes| K["Cloud Run Job smoke: task=1, parallelism=1"]
    K --> L["Collect results and logs"]
    L --> M["Clean up test data/resources"]
    M --> N{"Tests + cleanup pass?"}
    N -->|Yes| O["Allow release step"]
    N -->|No| P["Create issue and hold release"]
~~~

Never give a pipeline running on every PR full production permissions. Unreviewed changes could execute arbitrary code on build workers; the PR pipeline's service account must hold least privilege, especially for pull requests from external sources.

## 3. Understanding Quotas, Resource Limits, and Costs

**Quota** is the consumption or API rate cap enforced by a service, typically per project and region. A **limit** is a technical bound on a resource. **Cost** is the monetary charge accrued from runtime duration, request volume, data transferred, or storage mode.

These three concepts are related but not interchangeable:

- Cloud Build enforces quotas on concurrent builds, concurrent CPUs, and API call rates. Values vary by project, region, and worker pool; check the Quotas page before configuring.
- Cloud Run Jobs have task counts, parallelism, task timeouts, CPU/memory, and retries. Excessive tasks or retries can overwhelm Cloud SQL or other APIs.
- Cloud SQL, Pub/Sub, Cloud Storage, and Networking have their own independent quotas; lowering Cloud Build quotas does not automatically protect those services.
- Cloud Billing Budgets in **alerts-only** mode notify you, **and do not impose a hard spending cap**. Certain spend-cap capabilities may be supported within specific scopes; verify service and project support.

For example, a test pipeline launches 20 job tasks, each opening 10 database connections. Even though Cloud Build runs only one build, the workload can open nearly 200 concurrent connections and exceed Cloud SQL limits. Control concurrency across the job, test runner, and connection pool layers.

### 3.1. Resource Budget Table for the Lab

| Item | Recommended Lab Limit | Rationale |
|---|---|---|
| Overall Cloud Build | 15 minutes per run | Prevents hung builds or tests |
| Unit tests | Maximum 5 minutes | Flags abnormally slow tests |
| Integration with fakes/emulators | Maximum 8 minutes | Bounds prolonged retries and deadlocks |
| Live smoke test | One Cloud Run Job task | Avoids heavy load on staging |
| Job parallelism | 1 | Keeps concurrent request count predictable |
| Job task timeout | 300 seconds | Caps billable runtime per task |
| Job retries in lab | 0 | Prevents multiplying runs while learning |
| Test data | Names include run ID and retention TTL | Prevents long-term accumulation |
| Build triggers | Narrow PR scope; live tests gated only | Cuts duplicate and unnecessary runs |

These are **illustrative bounds**, not Google Cloud defaults or fixed prescriptions for every application. In production, base limits on test coverage, real resource capacity, project quotas, and pipeline SLOs.

## 4. Preparing Projects, IAM, and Cost Visibility

Use at least two projects:

- **BUILD_PROJECT_ID:** runs Cloud Build and stores test logs and results.
- **STAGING_PROJECT_ID:** hosts Cloud Run services, databases, or resources used for smoke tests.

The production project remains completely isolated; PR pipelines have zero permission to create resources or write data in staging or production.

Before testing:

1. Verify billing accounts and permissions on both projects.
2. Enable the Cloud Build API in the build project and the Cloud Run API in staging if using Jobs.
3. Create a dedicated build service account; never grant Editor or Owner to test pipelines.
4. Scope the smoke test's service account strictly to required APIs.
5. Configure Cloud Billing Budgets filtered by relevant projects/labels with early alert thresholds.
6. Inspect **IAM & Admin → Quotas & System Limits** for Cloud Build and Cloud Run in your target region.
7. Set up a dashboard or Billing query to review weekly costs.

Example enabling APIs using a suitably privileged bootstrap identity:

~~~bash
gcloud services enable cloudbuild.googleapis.com \
  --project=BUILD_PROJECT_ID

gcloud services enable run.googleapis.com \
  --project=STAGING_PROJECT_ID
~~~

Only administrators or authorized IaC workflows should enable APIs and grant IAM. Never assign project-admin permissions to a service account that only runs unit tests.

### 4.1. Least-Privilege IAM

| Principal | Roles/Permissions to Consider | Not Needed |
|---|---|---|
| PR build identity | Run Cloud Build and write logs; typically needs no access to other services | Cloud Run Admin, Cloud SQL Admin, Project Editor |
| Staging-gate build identity | Permission to execute **one** Cloud Run Job, e.g., `roles/run.invoker` on the Job | Permission to edit all Jobs or deploy production |
| Cloud Run Job service identity | Permission to read required test data or call staging endpoints | Access to production data |
| Trigger administrator | Trigger management and scoped `iam.serviceAccounts.actAs` | Long-lived service account keys |
| Billing/quota viewer | Billing, Monitoring, and Service Usage viewer permissions | Permission to modify unrelated resources |

When using a **user-managed service account** for Cloud Build and writing logs to Cloud Logging, set `options.logging: CLOUD_LOGGING_ONLY` and grant log-writing permissions such as `roles/logging.logWriter` in the build project. If storing logs in a Cloud Storage bucket, use a controlled bucket with matching write permissions.

Note: for triggers, the service account configured on the **trigger** takes precedence; setting `serviceAccount` in YAML does not override the trigger identity. Inspect both places so a workflow never runs under a stronger identity than intended.

## 5. Choosing an Efficiency-First Testing Strategy

Lower costs usually come from **shifting where tests run** rather than merely downsizing worker machines.

| Tier | Java/Spring Example | GCP Usage | When It Runs |
|---|---|---|---|
| Unit | JUnit 5, Mockito testing business rules | None | Every commit/PR |
| Component | `@WebMvcTest`, MockMvc, fake outbound adapters | None | Every PR |
| Isolated integration | Pub/Sub/Firestore emulators; WireMock; Testcontainers where supported | No live cloud project, consumes build CPU/RAM | PR/merge depending on duration |
| Live integration | Testing IAM, live Cloud Storage/SQL/Pub/Sub interactions | Consumes quota and incurs cost | Merge, staging, or scheduled |
| End-to-end | Smoke tests across staging services/gateways | Yes | Pre-release and post-deploy |
| Load/soak | Testing throughput, autoscaling, and service limits | Can incur significant cost | Dedicated schedule with approval/budget |

Emulators do not fully replicate IAM, quotas, billing, distributed operations, or every live service behavior. Thus, a small set of smoke tests on real GCP remains necessary. Avoid letting every pull request spin up a Cloud SQL instance or private network when a fake adapter suffices.

For projects with heavy suites, split test categories via Maven Surefire/Failsafe. Run live integration only on approved triggers with prepared test inputs.

## 6. Preparing the Maven Project and Test Groups

Assume the application layout:

~~~text
checkout-api/
├── pom.xml
├── src/
│   ├── main/java/com/example/checkout/
│   └── test/java/com/example/checkout/
│       ├── PriceCalculatorTest.java
│       ├── CheckoutControllerTest.java
│       └── CheckoutRepositoryIT.java
├── cloudbuild.yaml
└── README.md
~~~

By Maven conventions, Surefire runs `*Test` in the `test` phase and Failsafe runs `*IT` in the `integration-test` and `verify` phases. With Gradle, apply the same separation using `test` and `integrationTest` tasks.

Partial `pom.xml` example separating unit and integration tests:

~~~xml
<properties>
  <skipUnitTests>false</skipUnitTests>
  <skipITs>false</skipITs>
</properties>
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <skipTests>${skipUnitTests}</skipTests>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <skipITs>${skipITs}</skipITs>
      </configuration>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

In the plugin configuration above, the two Maven property expressions `${skipUnitTests}` and `${skipITs}` toggle each test group. Override them via `-D` flags in the commands below.

Run on a developer workstation:

~~~bash
# Unit tests: run fast, no real GCP service calls.
mvn -B -ntp -DskipITs=true test

# Integration tests: skip unit tests already run in the previous step.
mvn -B -ntp -DskipUnitTests=true -DskipITs=false verify
~~~

Ensure `*IT` tests use scoped emulators/fakes or dedicated test databases. Never write integration tests that connect directly to production by default via a developer's Application Default Credentials.

### 6.1. A Key Principle on Retries

Separate **infrastructure retries** from **assertion retries**:

- Use short retries with backoff when an emulator/service is starting up or encounters transient network errors.
- Never auto-retry the entire test suite repeatedly just to mask flakiness.
- Log retry counts, causes, and wait durations.
- On `429 RESOURCE_EXHAUSTED`, reduce concurrency or request rate before requesting higher quotas.

When tests produce side effects, attach a unique run ID and idempotency key so retries never create duplicate data or unexpected charges.

## 7. Practicing Cloud Build for a Low-Cost Pipeline

Below is an illustrative **`cloudbuild.yaml` sample** inside the application repository. Do not create new YAML files in this lesson; copy the snippet into your own project.

~~~yaml
steps:
  - id: unit
    name: maven:3.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -euc
      - |
        mvn -B -ntp -DskipITs=true test
    timeout: 300s
    volumes:
      - name: m2-cache
        path: /root/.m2

  - id: integration
    name: maven:3.9-eclipse-temurin-21
    waitFor: [unit]
    entrypoint: bash
    args:
      - -euc
      - |
        mvn -B -ntp -DskipUnitTests=true -DskipITs=false verify
    timeout: 480s
    volumes:
      - name: m2-cache
        path: /root/.m2

  - id: staging-smoke
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    waitFor: [integration]
    entrypoint: bash
    args:
      - -euc
      - |
        if [ "$_RUN_LIVE_TESTS" != "true" ]; then
          echo "SKIP live smoke: flag is disabled"
          exit 0
        fi
        gcloud run jobs execute "$_SMOKE_JOB" \
          --project="$_STAGING_PROJECT" \
          --region="$_REGION" \
          --wait
    timeout: 420s

substitutions:
  _RUN_LIVE_TESTS: "false"
  _SMOKE_JOB: "checkout-smoke"
  _STAGING_PROJECT: "example-staging"
  _REGION: "asia-southeast1"

timeout: 900s

options:
  logging: CLOUD_LOGGING_ONLY
~~~

**How it works:**

1. The `unit` step is capped at 300 seconds; if it fails, dependent steps do not run.
2. The `integration` step runs after unit tests, capped at 480 seconds inside the Cloud Build worker. The Maven repository cache resides on a temporary volume to avoid re-downloading dependencies between steps.
3. The `staging-smoke` step executes the Cloud Run Job only when `_RUN_LIVE_TESTS` is `true`. By default, live tests are skipped.
4. `timeout: 900s` caps total build duration; each step's timeout bounds only that individual step.
5. `CLOUD_LOGGING_ONLY` writes build logs to Cloud Logging; the build identity needs matching log-write permissions.
6. None of the steps call `gcloud run jobs update` or create Cloud SQL instances, so PRs create no persistent billable services by default.

Individual step timeouts do not sum to a guaranteed total because of queuing, image pulls, and startup overhead. The overall 900-second build timeout is an independent cap. Cloud Build's default timeout is longer; declare it explicitly to cut off wedged jobs.

**Security condition:** the `_RUN_LIVE_TESTS=true` flag is purely a behavior switch. It is **not an IAM boundary**. The build identity must be authorized to execute the staging Job only under approved policies. For untrusted PRs, use a trigger/service account with zero staging access; ideally isolate live-test configurations or triggers completely from the PR pipeline.

### 7.1. Testing the Pipeline in Both Modes

Default run in the configured build project:

~~~bash
gcloud builds submit . \
  --project=BUILD_PROJECT_ID \
  --region=asia-southeast1 \
  --config=cloudbuild.yaml
~~~

Live smoke run when authorized, within quota, and approved:

~~~bash
gcloud builds submit . \
  --project=BUILD_PROJECT_ID \
  --region=asia-southeast1 \
  --config=cloudbuild.yaml \
  --substitutions=_RUN_LIVE_TESTS=true,_STAGING_PROJECT=STAGING_PROJECT_ID
~~~

Each `gcloud builds submit` uploads source code to Cloud Build and can incur compute, storage/log, and data transfer charges. Run only in assigned environments; do not assume the example staging project or region already exists.

### 7.2. Configuring Triggers

In Cloud Build Triggers, configure:

- A PR trigger using `cloudbuild.yaml` that runs only when Java directories, `pom.xml`, or relevant test files change; configure included/ignored file filters.
- A staging trigger invoked on merge to main, on schedule, or manually, running under a service account permitted to execute the smoke Job.
- An **approval** gate before launching live triggers where required by environment and process.
- Mandatory review for pipeline configuration changes, Maven/image upgrades, or test infrastructure edits.
- Never allow untrusted forks or PRs to inherit staging credentials.

Cloud Build supports trigger-level approvals. Approvals pause builds until an authorized reviewer approves; they do not replace IAM, quotas, or budgets. When commits touch only unrelated files, trigger filtering cuts total build volume.

## 8. Creating a Bounded Cloud Run Job for Smoke Tests

The smoke Job should use a separately built and verified test container image. For instance, the image invokes staging endpoints and exits 0 on pass or non-zero on failure. Creating and configuring the Job is a one-time bootstrap step, not repeated on every PR.

Illustrative staging administrator command:

~~~bash
gcloud run jobs create checkout-smoke \
  --project=STAGING_PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/STAGING_PROJECT_ID/qa/checkout-smoke:approved \
  --tasks=1 \
  --parallelism=1 \
  --max-retries=0 \
  --task-timeout=300s \
  --cpu=1 \
  --memory=512Mi
~~~

Replace `:approved` with a verified image digest in release workflows when immutability is required. Configure this Job with a dedicated least-privilege service identity able only to call the target staging services.

**Meaningful bounds:**

- `--tasks=1`: one task per execution in the lab; prevents spawning dozens of workers at once.
- `--parallelism=1`: runs no concurrent tasks.
- `--max-retries=0`: if the test fails, stop for investigation instead of auto-retrying and burning budget. Production jobs may use controlled retries.
- `--task-timeout=300s`: prevents tasks from running indefinitely.
- Small CPU and memory sufficient for short smoke tests; scale up only with OOM or CPU-starvation evidence.
- The Job runs only when the staging-gate pipeline is permitted to call `jobs.execute`.

Run manually to verify:

~~~bash
gcloud run jobs execute checkout-smoke \
  --project=STAGING_PROJECT_ID \
  --region=asia-southeast1 \
  --wait
~~~

Passing `--wait` instructs the CLI to wait for Job execution completion so the pipeline captures pass/fail status and halts release if needed. Never check only whether the execution creation request was accepted.

### 8.1. Managing Test Data

If tests write to Firestore, Cloud SQL, or Cloud Storage, namespace by build ID:

~~~text
test-runs/
  run-<BUILD_ID>/
    orders/
    receipts/
    logs/
~~~

Principles:

- Use synthetic data only, with zero production PII.
- Embed a test-run identifier key across all rows, object prefixes, or schemas.
- Share baseline infrastructure wisely: a single Job task suffices; never spin up a new database instance per run.
- Maintain `finally`, cleanup steps, scheduled sweepers, or lifecycle rules with fallback TTLs.
- If cleanup fails, the pipeline must record leftover resources and raise an alert.
- For Cloud Storage, consider lifecycle policies on test prefixes/buckets; for databases, clean up by run ID and TTL where supported.

Never delete an entire shared bucket or database during cleanup. Test resources must carry labels/ownership so sweepers scope deletions accurately.

## 9. Managing Quotas at Each Layer

### 9.1. Cloud Build

Cloud Build enforces quotas for concurrent builds, active CPUs, and API call rates. Quotas vary by region, pool type, project, and usage history, so never hard-code one quota figure as universal across projects. When queues grow:

1. Check the Quotas page and build history by region.
2. Inspect running/queued builds and trigger frequency.
3. Eliminate redundant triggers, cut retries, and coalesce duplicate-commit builds.
4. Separate fast vs. costly tests so live tests run only at gates.
5. Request quota increases only after optimizing the pipeline and confirming genuine demand.

**Queued** builds do not accrue active build-minutes, though they lengthen release lead times. Raising concurrency speeds up delivery in some cases without necessarily lowering total cost.

### 9.2. Cloud Run and Backing Services

Concurrency limits extend beyond `parallelism`. If a Job runs 1 task that spawns 100 parallel requests inside Java, the API/DB still takes 100 concurrent requests.

Add in-runner concurrency guards, for example:

~~~java
import java.util.concurrent.Semaphore;

public final class ApiRateGate {
    private final Semaphore slots = new Semaphore(3);

    public void run(Runnable request) throws InterruptedException {
        slots.acquire();
        try {
            request.run();
        } finally {
            slots.release();
        }
    }
}
~~~

This example caps concurrency at three simultaneous executions **within a single JVM**. A `Semaphore` does not coordinate across multiple Job instances or rate-limit requests over time; when RPS caps are required, use a rate limiter with backoff/jitter and system-wide coordination.

Keep staging connection pools small, use small page sizes for test queries, and avoid tight polling loops on errors. For Pub/Sub tests, size message counts and ack deadlines conservatively; for Cloud SQL, watch `max_connections` and instance counts; for Cloud Storage, avoid uploading/downloading huge objects just to verify a contract.

### 9.3. Rate Limits and Bounded Retries

A safe retry strategy:

- Retry only recognized transient errors such as `429`, `503`, or network timeouts.
- Use exponential backoff with jitter and a finite total attempt cap.
- Enforce an overall deadline per operation, not just per-attempt timeouts.
- Log attempt counts and reasons on each request; use idempotency keys whenever side effects occur.
- If quota remains exhausted, abort or throttle rather than retrying forever.

A healthy test suite should fail clearly when quota is insufficient and alert operators with the root cause rather than silently hanging for hours.

## 10. Multi-Layer Cost Control

A sound operational budget combines multiple controls:

| Layer | Control | Effect |
|---|---|---|
| Pre-run | Trigger filters, approvals, test categorization | Cuts unnecessary expensive builds |
| During build | Build timeouts, step timeouts, right-sized machines | Caps consumed time and CPU |
| During live tests | Task count, parallelism, retries, request rate | Bounds downstream load and cost |
| Test resources | Dedicated project, resource labels, TTLs, cleanup | Prevents lingering post-test resources |
| Monitoring | Billing budgets, alerts, billing export, Monitoring | Detects abnormal spend trends |
| Policy | IAM, quotas, and service-enablement controls | Blocks out-of-scope paid actions |

**Never treat budget alerts as an automatic circuit breaker.** Billing data lags; spend can overshoot thresholds before email or Pub/Sub alerts arrive. Some services offer spend caps or specific hard limits, though availability, stop semantics, and workload impact must be verified before relying on them.

### 10.1. Estimating Cloud Build Costs

Cloud Build bills by **active build-minutes** according to machine type and region; queued time does not accrue build-minutes. Additional charges can come from Cloud Logging, Cloud Storage, network egress, Artifact Registry, and tested services.

Simple formulas:

~~~text
Estimated build cost ≈ billable build-minutes × unit price by worker type/region

Total pipeline cost ≈ Cloud Build + Cloud Run Job + API/DB/storage
                     + logging + egress + orphaned resources
~~~

Budget check example: a team runs 60 builds per day, averaging 5 minutes each, 20 days per month:

~~~text
60 builds/day × 5 minutes/build × 20 days = 6,000 build-minutes/month
~~~

Cloud Build pricing documentation at the time of writing includes a per-billing-account free tier for eligible machine types in the default pool; promotions, unit prices, and limits are subject to change. **Assuming** the full 2,500 free minutes/month apply and an illustrative rate of 0.006 USD/minute, the remainder in this scenario is:

~~~text
(6,000 − 2,500) × 0.006 USD ≈ 21 USD/month
~~~

This figure illustrates **build-minutes alone**, excludes other resources, and holds only under those assumed tier/rate parameters. In practice, verify the Cloud Build Pricing page for your region, machine type, billing account, taxes, and ancillary fees.

The biggest cost savings usually come from cutting redundant runs or shifting live tests to emulators rather than always picking the smallest worker. An undersized machine can lengthen execution enough to cost more total build-minutes.

### 10.2. Live Test Costs

Cloud Run Jobs accrue vCPU-seconds, GiB-seconds, and related charges based on configuration; services invoked by the Job also incur usage fees. If a Job retries repeatedly, billable runtime multiplies per attempt.

To estimate, compute `tasks × attempts × duration × allocated resources`, then apply regional Cloud Run pricing. Add Cloud SQL, Pub/Sub, Storage, logs, and egress costs. Label staging infrastructure and log `BUILD_ID` to pinpoint cost spikes.

## 11. Monitoring Quotas, Quality, and Cost

In Cloud Build, track:

- p50/p95 build duration, failure rates, and timeouts.
- Queued/running builds, plus invocations by trigger and branch.
- Separate durations for unit, integration, and live smoke steps.
- Flaky test rates, retry counts, and `429`/`RESOURCE_EXHAUSTED` errors.
- CPU/memory or machine type selected and total build-minutes.

In Cloud Run / Cloud Monitoring, track:

- Execution counts, succeeded/failed executions, and task retries.
- Task duration, memory/CPU utilization, and downstream API errors.
- Cloud SQL connection counts and saturation.
- Pub/Sub backlogs, test message counts, retries, and dead-letters.
- Cloud Logging ingestion volume and test data storage.

In Cloud Billing:

- Costs by **project**, service, SKU, and labels where supported.
- Week-over-week and month-over-month spend before and after trigger changes.
- Budget alert thresholds aligned to real budgets.
- For deeper analysis, enable Cloud Billing export to BigQuery to estimate cost per build or cost per test suite from correlatable fields; note that costs do not always map directly to a single build ID.

### Setting Internal Alert Thresholds

Operational trigger examples:

| Signal | Action |
|---|---|
| PR pipeline p95 exceeds target | Investigate slow tests, caching, and duplicate triggers |
| Cloud Build queue grows | Trim parallel builds/redundant triggers, inspect regional quotas |
| Recurring 429 errors | Lower request concurrency, add bounded backoff |
| Cloud Run Job runs close to timeout | Investigate deadlocks/latency and test data size |
| Budget reaches 50% or 80% early | Audit spend by SKU and pipeline trigger frequency |
| Staging resources found without owner/TTL | Pause live triggers and sweep by run ID |

The 50% and 80% thresholds are illustrative alert policies; tailor them to your spend level, billing cycle, and reporting latency. Never auto-delete production resources when a budget alert fires.

## 12. End-to-End Lab Workflow

### Step 1 — Establish a Baseline

Record daily builds, average build duration, concurrent build quotas, staging Job runs, prior month's spend, and current flaky tests. If starting fresh, test on one branch and measure several runs before enabling broad triggers.

### Step 2 — Run Local Tests

Run Maven unit tests and emulator/fake-backed integration tests locally. Verify tests use no GCP credentials and hit no production endpoints, and that test classes align cleanly with `*Test` and `*IT` conventions.

### Step 3 — Submit Cloud Build in Default Mode

Use the configuration from Section 7 with `_RUN_LIVE_TESTS=false`. Inspect step durations, total build time, logs, and test outcomes. Tune timeouts tightly with reasonable headroom rather than setting multi-hour limits to mask hangs.

### Step 4 — Provision the Live Smoke Job Once

In the staging project, create the `checkout-smoke` Job as in Section 8 using a reviewed test image. Verify task count, parallelism, retries, CPU, memory, and task timeout. Assign a service identity permitted only on target staging test resources.

### Step 5 — Trigger with Approval

Use a dedicated staging trigger or run `gcloud builds submit` with `_RUN_LIVE_TESTS=true` using an authorized identity. Never allow untrusted PRs to enable live tests via substitutions.

### Step 6 — Verify Results and Clean Up Data

Confirm the Job execution succeeded, inspect logs/metrics, and delete data scoped to the run ID. Run an independent scheduled cleanup job where needed to reclaim resources if a build cancels mid-cleanup.

### Step 7 — Measure and Tune

Compare build-minutes, live Job executions, p95 duration, and spend against the baseline. Increase parallelism or machine size only when measured gains outweigh cost and stay within downstream quotas.

### Step 8 — Enforce Release Gates on Failure

Wire pipeline results into branch protection and release gates. Permit deployment only after quality criteria pass and required approvals are granted. A passing test run that fails to clean up resources or report status to the release gate is operationally incomplete.

## 13. Incident Scenarios and Remediation

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Cloud Build reports quota exceeded or long queues | Too many concurrent builds, low CPU quota | Check regional/pool quotas, trim duplicate triggers and concurrency |
| Integration test hits 429 | Calling APIs too fast or too many clients | Throttle requests, apply exponential backoff with jitter, cap parallelism |
| Cloud Run Job loops on failure and spikes cost | `max-retries` too high on non-recoverable errors | Lower retries, fix root cause, enforce deadlines |
| Cloud SQL runs out of connections | Too many tasks, oversized pools, or leaks | Cap job tasks and pools, ensure clean connection closure |
| CI spends too long downloading dependencies | Missing cache or slow network | Configure build caching appropriately, pin dependencies, measure impact |
| Tests pass yet live step was skipped | `_RUN_LIVE_TESTS=false` | Check trigger type and release gates; never treat PR pass as live pass |
| Budget alert arrives after spend spiked | Billing latency; alerts are not hard caps | Enforce quotas, IAM, timeouts, and TTLs as primary guardrails |
| Staging resources linger too long | Cleanup skipped on cancelled builds | Enforce TTLs/lifecycle rules and independent scheduled sweepers |
| Concurrent PRs collide on shared test data | Missing run ID or namespace | Isolate namespaces and test fixtures |
| Live smoke fails with permission error | Build service account lacks Job execution permission | Grant execute permission on the specific Job only; never project-wide edit |

### Distinguishing Quota Errors from Application Bugs

When tests fail, investigate in order:

1. Do logs show an assertion failure or infrastructure errors (`429`, `503`, `RESOURCE_EXHAUSTED`)?
2. How many requests or job tasks ran concurrently? Is there a retry storm?
3. Which quota applied: Cloud Build, Cloud Run, Cloud SQL, Pub/Sub, or another service?
4. Do project, region, and service account match the intended environment?
5. Are leftover resources/data from a previous run causing contention?
6. Did costs spike due to build duration, live Jobs, logs, storage, or orphaned data?
7. After throttling load or fixing the test, does the same test reproduce the failure?

Never automatically request a quota increase the moment you see `429`. Quotas may be protecting a shared staging service from being overwhelmed by a runaway pipeline.

## 14. Design Mistakes to Avoid

- **Running every test against live cloud:** slows pipelines, inflates cost, and hits quotas.
- **Omitting deadlines:** lets hung tests run for hours or wait indefinitely on APIs.
- **Infinite retries:** turns a brief glitch into thousands of billable requests.
- **Treating budgets as hard caps:** alerts lag and do not stop resource usage.
- **Using an admin service account:** lets PRs touch resources outside test boundaries.
- **Skipping trigger path filters:** documentation edits trigger full integration suites.
- **Upgrading build workers before measuring:** larger machines can raise cost without meaningfully improving p95.
- **Uncapped live Job tasks/parallelism:** overloads Cloud SQL or staging APIs.
- **Cleaning up only in a final build step:** cancelled builds leave test data and infrastructure behind.
- **Not connecting tests to release gates:** releases can bypass smoke tests even with green CI badges.

## 15. Readiness Checklist

- [ ] PR pipeline runs unit and isolated integration tests.
- [ ] Live integration/smoke tests are isolated from untrusted PRs.
- [ ] Cloud Build defines both step timeouts and an overall build timeout.
- [ ] Trigger frequency and file paths are reasonably filtered.
- [ ] Cloud Build service account holds least-privilege IAM and proper logging config.
- [ ] Cloud Build and downstream service quotas are checked by project and region.
- [ ] Staging Cloud Run Job sets explicit task count, parallelism, timeout, and retries.
- [ ] Tests use synthetic data, unique run IDs, and never write to production.
- [ ] API calls enforce timeouts, concurrency guards, and finite retries.
- [ ] Staging enforces automated cleanup plus fallback TTL/lifecycle policies.
- [ ] Billing Budget alerts are active, with clear understanding that alerts are not hard caps.
- [ ] Dashboards track logs, test failures, 429s, build-minutes, and spend.
- [ ] Live test outcomes feed directly into release gates.
- [ ] Owners and runbooks exist for sudden quota or cost spikes.

## 16. Self-Check Questions

1. Why should unit tests and emulator-backed integration tests run before live Google Cloud smoke tests?
2. How do Cloud Build step timeouts differ from the overall build timeout?
3. If `_RUN_LIVE_TESTS=false`, does the pipeline provide sufficient evidence that staging Cloud SQL connectivity works?
4. Why should the PR service account not hold permission to run the staging Job?
5. Do alerts-only Cloud Billing Budgets stop spending when usage reaches 100%?
6. What does a Cloud Run Job with 20 tasks and parallelism set to 1 mean?
7. Why is increasing retries a poor fix when APIs repeatedly report quota exhausted?
8. If a build is cancelled before the cleanup step runs, what mechanism must reclaim test data?
9. Which metrics should you measure before increasing Cloud Build worker CPU?

**Answer Key**

1. Local/fake tests run fast and cheaply while conserving quota-bound API calls; live cloud smoke tests focus on real integration verification.
2. A step timeout caps one individual step, whereas the build timeout caps the entire build execution.
3. No; the pipeline only verified tests that do not require live GCP and has not verified staging IAM or networking.
4. Because untrusted PR code can execute arbitrarily; staging IAM must belong to controlled triggers and workflows.
5. No. Alerts-only budgets only send notifications and impose no hard spending cap.
6. The Job executes at most one task at a time; remaining tasks are scheduled sequentially as slots free up.
7. Uncontrolled retries multiply requests, prolong execution, and raise costs; throttle load, apply backoff, and inspect quotas instead.
8. TTL/lifecycle policies or an independent scheduled cleanup job decoupled from the pipeline.
9. p50/p95 build duration, run volume, cost by worker type, failure rate, queue times, and actual CPU saturation.

## References

- [Google Cloud: Cloud Build quotas and limits](https://docs.cloud.google.com/build/quotas)
- [Google Cloud: Build config file schema and timeout](https://docs.cloud.google.com/build/docs/build-config-file-schema)
- [Google Cloud: Cloud Build pricing](https://cloud.google.com/build/pricing)
- [Google Cloud: Create and manage build triggers](https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [Google Cloud: Substituting variable values in Cloud Build](https://docs.cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Google Cloud: User-managed service account for Cloud Build](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Google Cloud: Run Cloud Run jobs](https://docs.cloud.google.com/run/docs/execute/jobs)
- [Google Cloud: Cloud Run jobs parallelism](https://docs.cloud.google.com/run/docs/configuring/parallelism)
- [Google Cloud: Cloud Run jobs maximum retries](https://docs.cloud.google.com/run/docs/configuring/max-retries)
- [Google Cloud: Create and manage budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Apache Maven: Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven: Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
