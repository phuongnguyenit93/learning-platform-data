# Deployment Slots, Warm-Up, and Version Swaps

A web application running on Azure App Service typically needs to deploy new releases repeatedly. Deploying new code directly onto the live app serving customers means process restarts, library loading, database connection setup, or configuration loading can create downtime. Even if the app starts successfully, the new version may still fail because production settings differ from development.

**Deployment slots** let you stage a new version in a separate deployment environment belonging to the same App Service, test and warm up the app, and then **swap** that version into production. This is a useful mechanism to reduce release risk and enable fast rollbacks at the application code layer. However, a swap **does not automatically roll back** changes to databases, message queues, user data, or external systems.

In the CLOUD_PROVIDERS_AZURE module, this lesson connects Azure App Service with subscriptions, resource groups, Microsoft Entra ID, networking, Key Vault, monitoring, and cost control. The goal is **verifiable and recoverable** deployments—not merely running a swap command that succeeds.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain deployment slots, slot hostnames, the production slot, and staging slots.
2. Distinguish between content/configuration that moves during a swap and **slot-specific** (sticky) configuration.
3. Describe the phases of swapping, warm-up, swap with preview, and restart behavior across slots.
4. Design health/readiness endpoints and warm-up settings for an application.
5. Practice creating slots, deploying to staging, validating, swapping, and rolling back with Azure CLI.
6. Avoid risks when database migrations, background jobs, queue consumers, sessions, and secrets interact with a swap.
7. Build a release pipeline with approvals, telemetry, rollback plans, and cost monitoring.

Prerequisites: App Service Plans, App Service Web Apps, HTTP/HTTPS, CI/CD, environment variables, Azure RBAC, Azure Monitor, and deployment artifacts. CLI examples use illustrative resource names, **are not executed automatically**, and can incur charges when provisioning real resources.

## 2. Why not deploy directly to production?

Suppose `orders-api` runs on Azure App Service in Southeast Asia. A release updates Java code, adds environment variables, and changes a database interaction API. If the pipeline deploys straight to production:

- App Service may restart or recycle workers when receiving new code/config.
- The Java runtime/JIT, dependency injection, database connections, caches, and libraries may take time to warm up.
- If startup fails, production is impacted before smoke tests can even run.
- Rollback is hard if the prior artifact is unavailable or database schemas changed incompatibly.
- Environment configuration mistakes can make the app use the wrong credentials or endpoints.

Deployment slots separate **placing an artifact into an environment** from **exposing live users to the new version**. Staging has its own URL for testing. Swapping prepares the version in the source slot and transitions it to the target slot in a controlled way.

A key benefit: instead of waiting for cold starts after production traffic switches over, App Service can warm up the source slot with the target configuration before completing the version switch.

**Limitation:** do not view a swap as an atomic transaction across an entire distributed system. Open connections, background processing, database migrations, message queues, external Azure settings, and app-managed sessions must all be accounted for separately.

## 3. Deployment slots in App Service

### 3.1. Logical structure

An App Service Web App has a default production slot and can add named slots such as `staging` or `preprod`.

~~~mermaid
flowchart TB
    U["Users / clients"] --> P["production<br/>orders-web.azurewebsites.net"]
    T["QA / test pipeline"] --> S["staging<br/>orders-web-staging.azurewebsites.net"]
    P --> D["App Service Plan<br/>shared compute"]
    S --> D
    S -. "After testing: warm-up and swap" .-> P
~~~

Example structure:

~~~text
Subscription: sub-commerce-prod
Resource group: rg-orders-prod
App Service Plan: asp-orders-prod
Web App: orders-web
  ├── production (default slot)
  │   └── https://orders-web.azurewebsites.net
  └── staging
      └── https://orders-web-staging.azurewebsites.net
~~~

The hostnames above are illustrative; real web app names must be validly provisioned and actual URLs retrieved from Azure.

**Production is also a slot.** The production slot does not carry a suffix like `staging`/`preprod`, yet it is a special target in swap operations. Slots belong to the same Web App and share the App Service Plan and its compute pool. Each slot is a live app with its own hostname and configuration per App Service rules.

### 3.2. Support prerequisites

- Deployment slots are available on **supported App Service Plan tiers**, typically Standard, Premium, or Isolated; Free/Shared/Basic do not offer the same capability.
- Maximum slot counts depend on the tier and current service limits.
- A staging slot consumes the App Service Plan's compute resources just like any running app, even with zero production user traffic.
- Slots in the same web app are not two independent regions or completely isolated fault domains.
- Slots do not replace deploying to a different App Service Plan, different app, or different region; those cases require external routing/blue-green setups.

Check tier/region support and deployment slot limits before creating them. Do not take a set of Premium commands and run them on a Basic app without upgrading the plan first.

### 3.3. Easily confused concepts

| Concept | Role | What NOT to assume |
|---|---|---|
| Slot | Application runtime environment within a Web App | Not a separate resource group or region |
| Production slot | Endpoint receiving live customer traffic per production routing | Not necessarily isolated from staging in network/data permissions unless configured |
| Staging slot | Environment for deploying and validating a new release | Not automatically isolated from production resources |
| Slot hostname | Dedicated URL for accessing the slot | Not automatically private or restricted to QA |
| Swap | Operation exchanging swappable elements between source and target | Does not swap every setting, secret, DNS entry, or database |
| Sticky setting | App setting/connection string marked as a deployment slot setting | Do not generalize its behavior to every Azure configuration property |
| Warm-up | Startup and readiness validation phase before shifting traffic | A single HTTP 200 does not prove every business workflow works |
| Rollback via reverse swap | Returning prior code/config to production when safe | Does not automatically undo changes outside App Service |

## 4. What swaps and what stays pinned to a slot?

This is the most critical section for avoiding misconfigured environments and data corruption.

### 4.1. Content/configuration that can swap

When swapping between staging and production, App Service swaps **content and settings not marked sticky** according to service rules. Depending on the platform/feature set, swapped items may include:

- Application code or deployment artifacts.
- App settings and connection strings **not marked as deployment slot settings**.
- Certain version-portable app settings per App Service's swap matrix.

Never assume every setting in the Portal swaps. App Service defines an explicit list of settings that swap versus settings that stay pinned per current docs; features like authentication, custom domains, certificates, VNet integration, managed identities, health checks, or external resource policies must be evaluated individually.

### 4.2. Sticky settings

Values that must remain tied to an environment can be marked **Deployment slot setting**. For example:

~~~text
production:
  APP_ENV=production
  ORDERS_DB_ENDPOINT=<production-db>
  PAYMENT_MODE=live

staging:
  APP_ENV=staging
  ORDERS_DB_ENDPOINT=<staging-db>
  PAYMENT_MODE=sandbox
~~~

When marked slot-specific, values are managed as per-slot settings under App Service rules rather than moving with the artifact during version swaps. This is vital for database connections, API keys, secret references, and operational mode flags.

**Not every setting has a sticky toggle.** Which settings are inherently slot-pinned, which swap, and special exceptions depend on the platform. Always check the official reference table instead of guessing.

### 4.3. Critical trap: warm-up can run with the target slot's configuration

During swap preparation, App Service can **apply the target slot's configuration to the source slot, restart instances, and run warm-up** before completing traffic cutover. Therefore, never assume an app sitting in staging will **only** talk to the test database right up until the final instant.

Example:

- Source = staging running artifact v2.
- Target = production running artifact v1.
- During swap prep, v2 may boot/warm up with target production settings per service workflow.
- If startup code automatically runs database migrations, consumes queues, or sends emails on boot, those actions can affect **live systems before the swap even completes**.

**Mitigation:** health/readiness endpoints must have zero side effects; schema migrations must run in a separate, dual-version-compatible process; background jobs need coordination/locking at the system layer, not just slot name checks. Test swaps in an authorized non-prod environment before using them in production.

### 4.4. Example setting classification

| Setting / config source | Strategy | Reason |
|---|---|---|
| RELEASE_VERSION | Travels with artifact; swaps with code | Used for build traceability |
| LOG_LEVEL | Per environment/policy | May differ for diagnostics without leaking data |
| DATABASE_URL | Sticky per slot, securely managed | Prevents cross-environment mix-ups on config/swap |
| PAYMENT_API_KEY | Sticky or matching Key Vault reference | Never embed live keys in artifacts |
| FEATURE_CHECKOUT_V2 | Can decouple feature flags/rollouts from swaps | Reduces coupling between deploying and enabling features |
| MIGRATION_ENABLED | Disabled by default in web process; run via dedicated migration job | Avoids duplicate migrations and running during warm-up |
| APP_BUILD_SHA | Travels with build version | Verifies active release |
| BACKGROUND_WORKER_ENABLED | Controlled safely via orchestration and app-level locks | Prevents two slots from consuming the same queue simultaneously |

Marking a setting sticky does not replace authorization in the database or Key Vault. Verify identities, roles, firewalls, and secret references for both production and staging.

## 5. What stages does a swap go through?

### 5.1. Standard deployment flow

~~~mermaid
sequenceDiagram
    participant C as CI/CD Pipeline
    participant S as Staging Slot
    participant A as App Service Swap
    participant P as Production Slot
    participant M as Monitoring
    C->>S: Deploy artifact v2
    C->>S: Smoke test v2
    C->>A: Request staging → production swap
    A->>S: Apply target settings, restart
    A->>S: Warm-up / readiness check
    S-->>A: Ready per service criteria
    A->>P: Swap prepared version into target
    C->>M: Check API, logs, p95, errors
    M-->>C: Pass or trigger rollback alert
~~~

This diagram illustrates logical sequence; internal steps, restart counts, and timing of config application vary by App Service type and swap scenario. Check exact behavior for Linux/Windows, your runtime, and app configuration.

### 5.2. Preparation (pre-swap)

App Service prepares the source slot to match target settings, restarts instances as needed, and performs warm-up. If preparation fails, the swap may abort and the team must investigate rather than forcing an unready release onto production.

Defining **ready** clearly is essential—do not rely merely on the process starting or a static HTML page returning 200 when the app has not connected to mandatory dependencies.

### 5.3. Completing the swap

Once the source passes checks, App Service switches the swappable elements. The production URL stays the familiar production URL; users never switch to a staging hostname. The previous version may remain in the other slot, supporting rollback where appropriate.

**Swapping does not migrate databases** or synchronize external data outside the slot. Nor is it a multi-region failover strategy.

### 5.4. Swap with preview

Where supported by the scenario and platform, **swap with preview** splits the operation into phases:

1. **Prepare/preview:** prepares the source with target settings and lets operators verify state before shifting traffic.
2. **Complete:** finishes the swap when operators decide to proceed.
3. **Cancel/reset:** aborts preview if anomalies arise, restoring pre-preview state per service mechanics.

Preview provides a helpful checkpoint before impacting live traffic. However, **never assume every App Service configuration supports preview**; some OS, authentication, or platform combinations have restrictions. Verify swap-with-preview support for your exact App Service before writing automation that assumes preview works everywhere.

Also do not treat preview as total isolation from production: during preparation, the app may already be running with target settings. Self-starting background tasks remain a hazard to manage.

## 6. What are warm-up and readiness?

### 6.1. Warm-up is more than one HTTP request

For Java, .NET, or Node.js apps, a cold start may involve:

- Starting the runtime, loading modules, initializing dependency injection and JIT compilation.
- Reading configuration and testing database or Key Vault connectivity.
- Loading templates, metadata, rules, or local caches.
- Opening connection pools and initializing HTTP clients.
- Completing dependency registration and starting to serve requests.

For App Service containers, it also includes pulling images, launching containers, binding ports, and runtime startup. Warm-up reduces the chance of a new release receiving traffic before it is ready.

### 6.2. Distinguishing liveness, readiness, and deep health

| Endpoint | Question | Example response |
|---|---|---|
| `/health/live` | Is the process still alive? | 200 if process/event loop is responsive |
| `/health/ready` | Can the instance serve business requests? | 200 when ready, 503 while starting up |
| `/health/deep` | Are databases and dependencies healthy? | Detailed output restricted to authorized operators |

**Readiness** for swaps should reflect essential serving conditions. However, avoid overly deep checks or side effects: an endpoint must never create tables, alter schemas, charge payments, send emails, write orders, or consume queues to prove it is "ready."

Example JSON:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"status":"ready","version":"v2.3.0"}
~~~

When not ready:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Cache-Control: no-store

{"status":"not_ready"}
~~~

If the endpoint returns a 302 login redirect or 401, warm-up probes may misinterpret readiness. Design an endpoint that leaks no sensitive data, is appropriately reachable by platform probes, and returns HTTP codes aligned with your configured warm-up rules.

### 6.3. App settings for swap warm-up

App Service provides app settings for swap warm-up:

- **WEBSITE_SWAP_WARMUP_PING_PATH:** URL path pinged to warm up the app during swap, e.g., `/health/ready`.
- **WEBSITE_SWAP_WARMUP_PING_STATUSES:** HTTP status codes considered successful for warm-up, e.g., `200`.

Example (illustrative values):

~~~text
WEBSITE_SWAP_WARMUP_PING_PATH=/health/ready
WEBSITE_SWAP_WARMUP_PING_STATUSES=200
~~~

**Easy pitfall to miss:** if you do not restrict accepted HTTP statuses as supported, an unintended response (such as a redirect or error) might fail to block warm-up as expected. Specify accepted codes explicitly and verify during a test swap.

Additionally, App Service has other startup/warm-up mechanisms, such as `WEBSITE_WARMUP_PATH` in certain container scenarios or Application Initialization on Windows/IIS. **Do not conflate** container-startup warm-up with slot-swap warm-up. Names, effects, and support vary by platform.

### 6.4. Java Spring Boot readiness example

With Spring Boot and Spring Boot Actuator properly configured, the app can expose health probe endpoints. Reference configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Once readiness probes are enabled, the reference path can be:

~~~text
/actuator/health/readiness
~~~

Include the Spring Boot Actuator dependency in your build and secure health endpoints appropriately. If using a custom readiness path like `/health/ready`, implement or route it to a real endpoint; **never point `WEBSITE_SWAP_WARMUP_PING_PATH` to a nonexistent path**.

The health response should reflect defined readiness criteria, such as Spring lifecycle completion. If a database check is mandatory, design an appropriate health contributor without running writes or heavy queries on every probe.

### 6.5. Using Application Insights and testing cold starts

Observe:

1. Time from startup to readiness.
2. Error rates during the first few minutes after deploy or swap.
3. p95/p99 latency on the first hits to business endpoints.
4. Count of unready instances or restart loops.
5. Dependency errors such as DB timeouts, DNS issues, or Key Vault unavailability.

Do not claim "zero downtime" just because a warm-up ping returned 200. Test under high load, scale-out, and dependency failures.

## 7. Hands-on: creating a slot and deploying a staging release

Assume `orders-web` belongs to resource group `rg-orders-prod` on an App Service Plan supporting deployment slots. The web app is already created and serving v1 in production.

### Step 1: Confirm subscription and app

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az webapp show \
  --resource-group rg-orders-prod \
  --name orders-web \
  --query "{name:name,kind:kind,state:state,host:defaultHostName,plan:serverFarmId}" \
  --output json
~~~

Check the linked App Service Plan's SKU/tier; do not upgrade tiers without cost approval.

### Step 2: Create a staging slot

~~~bash
az webapp deployment slot create \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging
~~~

Depending on the scenario, you can clone settings from an existing slot via CLI options or the Azure Portal. If cloning production, review **every** setting, connection string, permission, webhook, and background task before letting staging start.

List slots:

~~~bash
az webapp deployment slot list \
  --resource-group rg-orders-prod \
  --name orders-web \
  --output table
~~~

Slot URL (when configured and permitted):

~~~text
https://orders-web-staging.azurewebsites.net
~~~

The staging slot is a live endpoint; by default, do not assume this URL is protected from public access. Depending on the environment, apply App Service access restrictions, authentication, or private networking as supported.

### Step 3: Separate configuration per slot

Example setting an environment marker with the slot-specific flag:

~~~bash
az webapp config appsettings set \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --slot-settings APP_ENV=staging

az webapp config appsettings set \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot-settings APP_ENV=production
~~~

The **--slot-settings** flag marks app settings as deployment slot settings. Do not put raw secrets into commands in production examples where they can leak via terminal history, logs, or pipeline output; prefer managed identity and Key Vault references as supported by App Service.

Inspect metadata to verify settings and `slotSetting` flags:

~~~bash
az webapp config appsettings list \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

**Never print setting values when secrets may be present.** Some CLI commands return secret values in raw output; restrict fields with `--query` during audits.

### Step 4: Configure warm-up

Assume the app exposes `/health/ready`. Configure warm-up for staging using supported platform app settings:

~~~bash
az webapp config appsettings set \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --settings WEBSITE_SWAP_WARMUP_PING_PATH=/health/ready WEBSITE_SWAP_WARMUP_PING_STATUSES=200
~~~

Re-check setting names/`slotSetting` flags and product docs to confirm whether settings should follow the app version or stay pinned to a specific slot. Do not blindly mark a setting sticky merely because its name starts with `WEBSITE_` without knowing its swap behavior.

Once configured, probe the staging endpoint:

~~~bash
curl -i https://orders-web-staging.azurewebsites.net/health/ready
~~~

Verify final HTTP status, response body, latency, access controls, and consistency across instances. A single 200 response is insufficient as an acceptance test.

### Step 5: Deploy the artifact to staging

You can deploy via Azure DevOps, GitHub Actions, or Azure CLI. Example deploying a built ZIP matching the web app runtime:

~~~bash
az webapp deploy \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --src-path "./orders-web-v2.zip" \
  --type zip
~~~

This command deploys an artifact; it does not compile the project. For Java App Service, JAR/WAR/ZIP packaging, runtime startup commands, and deploy targets depend on your chosen stack; use a compatible artifact type rather than renaming an arbitrary file to `.zip`.

A safe pipeline should **build once, track checksums/artifact IDs, and deploy the approved artifact** instead of rebuilding between staging and production.

### Step 6: Smoke test before swapping

From an authorized test machine/channel:

~~~bash
curl -i https://orders-web-staging.azurewebsites.net/health/ready
curl -i https://orders-web-staging.azurewebsites.net/api/version
~~~

Verify at minimum:

- HTTP status, readiness, and version/build SHA.
- Read-only API endpoints without side effects.
- Authentication, authorization, and CORS configuration per policy.
- Database queries in an authorized environment with compatible schemas.
- Key Vault, Storage, outbound network, and DNS dependencies.
- Application Insights telemetry, 5xx errors, latency, and restarts.
- Staging URL protection and absence of secrets in responses.
- Background jobs behaving safely when slot swap preparation runs.

Only advance the release to swap approval after all acceptance criteria pass.

## 8. Performing the swap and post-release verification

### 8.1. Swap staging to production

Once approved:

~~~bash
az webapp deployment slot swap \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --target-slot production
~~~

Run using a principal with appropriate permissions on the App Service resource. This swap changes the live version serving users; do not treat it as a harmless production experiment.

Verify:

~~~bash
curl -i https://orders-web.azurewebsites.net/health/ready
curl -i https://orders-web.azurewebsites.net/api/version
~~~

Beyond HTTP checks, monitor Azure Monitor/Application Insights, HTTP 5xx rates, dependency failures, p95 latency, CPU/memory, restarts, queue backlogs, and business error rates over an agreed observation window.

### 8.2. Rolling back via reverse swap

After a successful swap, the prior code version can often be restored to production via a reverse swap, **provided both slots and artifacts remain in a compatible state**.

Example:

~~~bash
az webapp deployment slot swap \
  --resource-group rg-orders-prod \
  --name orders-web \
  --slot staging \
  --target-slot production
~~~

The command uses the same source/target arguments because after the first swap, staging holds the previous version. Verify the **actual build SHA and configuration in both slots before executing**; if the pipeline already deployed a newer artifact to staging, this command will no longer roll back to the expected prior release.

Record every rollback: approver, trigger condition, data state, verification results, and root-cause remediation plan.

### 8.3. Rollback limitations

A reverse swap **does not** undo:

- Database schema migrations or mutated data.
- Dispatched messages, consumed queues, or processed payments.
- Changes to Key Vault secrets, DNS, firewalls, or storage outside the slot.
- Altered sessions/caches or ephemeral in-memory state.
- External systems that already received requests from the new version.

Effective rollbacks require designing **compatibility and reversibility** upfront, not just keeping artifact v1 around.

### 8.4. Swap with preview in gated pipelines

In environments supporting preview, preparation and completion can be split for operator checks/approvals per docs. The CLI provides corresponding action options in supported versions; verify help for your exact Azure CLI:

~~~bash
az webapp deployment slot swap --help
~~~

Do not ship automation built on unverified preview flags or assume all platforms support preview identically. Where preview is unsupported, use staging smoke tests and standard swaps backed by approvals, telemetry, and rollback plans.

## 9. Risks involving databases and background processing

### 9.1. Database migrations

Suppose release v2 adds a new column to the `orders` table. While v1 still runs concurrently, the new schema must preserve v1 behavior until v2 stabilizes.

The **expand–migrate–contract** pattern:

1. **Expand:** add tables/columns/indexes in a backward-compatible way.
2. **Migrate:** backfill via an isolated, retryable, idempotent, monitored job.
3. **Deploy v2:** deploy to staging, warm up, smoke test, and swap.
4. **Observe:** confirm v2 health while retaining the ability to roll back to v1 code if needed.
5. **Contract:** drop legacy schema elements only after all dependent versions are gone and approval is granted.

**Never place breaking schema migrations directly inside an application startup hook.** Startup can run multiple times across multiple instances in both staging and production—and can be triggered during warm-up.

### 9.2. Queue consumers and scheduled jobs

Both slots can run background processes simultaneously. If v2 in staging runs a worker that automatically listens to the production queue, it can consume jobs before the swap—causing duplicate processing, duplicate emails, or data races.

Mitigations:

- Separate web apps from worker services with independent release lifecycles.
- Use dedicated test queues/endpoints, bearing in mind warm-up may apply target settings.
- Use distributed locks or leases where only one worker may run.
- Use system-level feature flags or orchestration policies to block unapproved side effects.
- Design idempotent event/message handling and safe transactions.
- Monitor queue backlogs, dead-letter queues, and processing metrics across the swap.

**Do not rely solely on `APP_ENV=staging` to prevent side effects** when target settings are applied to the source slot. Test actual execution paths and swap behavior.

### 9.3. Sessions and temporary files

App Service slots should not be treated as immutable session storage. In scaled-out apps, requests can hit different instances; during swaps, instance restarts or route changes can wipe in-memory sessions.

Use a supported external session store (such as a distributed cache), proper cookie/session design, and persistent storage for durable data. For WebSockets or long-lived connections, verify reconnection logic and interruption handling.

### 9.4. Feature flags

Deployment slots separate **deploying code** from **routing production traffic**, but do not automatically separate **enabling business features**. For major changes, use controlled feature flags so capabilities can be enabled incrementally by user segment after the swap.

Ensure feature flags are read/cached with sensible refresh strategies; rolling back a flag does not replace a code rollback if severe startup or dependency bugs occur.

## 10. Canary releases and traffic routing vs. swap

Azure App Service supports **traffic routing between production and deployment slots** in supported configurations. This routes a percentage of users to a staging slot, unlike a swap which promotes the staged version to production.

| Criterion | Swap | Traffic routing / canary |
|---|---|---|
| Goal | Promote prepared release to production | Route a fraction of requests/clients to a test slot |
| Selection mechanism | Release transition between source and target | App Service traffic distribution rules |
| Timing | After smoke tests and warm-up | Before swap or during a dedicated experiment phase |
| User exposure | New version becomes production via swap | Only a subset of users hit the new slot via routing/cookie |
| Data risk | Still impacts databases/queues/shared services | Demands strict backward compatibility since both versions serve simultaneously |
| Rollback | Reverse swap if state is compatible | Reset traffic percentage to 0 or update rules, then handle data |
| Constraints | Supported content/settings only | Must account for sticky routing cookies, sessions, UX, and tier features |

Do not treat routing percentages as an exact split over very short intervals: sticky routing cookies and client distribution skew short-term observations. During canary testing, slice telemetry by **release version/slot**, not just overall production aggregates.

If Front Door or Application Gateway sits in front of App Service, canary/blue-green routing is also possible at that external layer. Do not confuse external routing rules with in-app slot swaps.

## 11. Staging security and secret management

### 11.1. Staging slots are not automatically secure

Staging has its own hostname and can be reachable from the internet if web app/network settings allow it. It may contain unreleased code, debug endpoints, seed data, or fresh bugs. You must:

- Restrict slot access using access restrictions, authentication, or private networking per supported patterns.
- Avoid using real production secrets in staging unless explicitly approved.
- Disable debug endpoints, stack traces, and sensitive version banners.
- Never place real customer data in staging without appropriate safeguards.
- Control who can deploy to the slot, view settings, and trigger swaps.
- Enforce HTTPS, logging, and vulnerability scanning just like production.

### 11.2. Key Vault references and managed identity

When using Key Vault references in app settings, inspect how references evaluate, which identity authenticates, and the network path for each slot. Managed identities and certain resource-specific properties do not automatically swap with code. For staging/production, clarify:

- Which identity does each slot use, and what Key Vault role does it hold?
- Which Key Vault references are sticky?
- Which Key Vault network rules or private endpoints apply?
- Can secrets rotate without breaking startup?
- Does the app cache secrets too aggressively, requiring a restart or refresh on rotation?

If warm-up with target settings requires access to production Key Vault, the source slot during preparation must hold approved permissions and config **per architecture**. Never grant broad permanent permissions to staging just to get past a swap error; review identity design and prevent side effects.

### 11.3. Azure RBAC and auditing

Artifact deployment permissions and production swap permissions can be separated across pipelines and role assignments under your governance model. A common pattern:

1. CI service principal/managed identity deploys to staging with least privilege.
2. QA/service owner validates and records acceptance.
3. Release manager or approval gate authorizes the swap.
4. Release pipeline logs artifact SHA, source/target slots, approver, and timestamp.
5. Azure Activity Log, deployment logs, and App Insights retain audit trails.

Never assume anyone allowed to update staging should also be allowed to promote to production.

## 12. Monitoring swap effectiveness

### 12.1. Observing before, during, and after a swap

| Phase | Data to inspect |
|---|---|
| Pre-deploy | Production p50/p95 latency, 5xx, CPU, memory, dependency errors |
| Staging warm-up | Startup duration, readiness, config/Key Vault/DB errors, restarts |
| Immediately post-swap | HTTP status, request rate, version/build SHA, latency, dependency duration |
| Observation window | Business errors, queue backlog, logins/sessions, resource usage, retry rates |
| On rollback | Recovery time, error trends, and data impact |
| Post-release | Release record, retrospective, alert/runbook improvements |

Use Application Insights, Azure Monitor metrics/logs, Availability Tests, and internal APM tools. Exact KQL tables and fields depend on the Application Insights version and workspace-based mode.

### 12.2. Reference KQL for request errors

If the workspace uses the `AppRequests` table (workspace-based Application Insights):

~~~kusto
AppRequests
| where TimeGenerated > ago(30m)
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P95ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Schemas can vary by workspace; before relying on it, verify table names, `DurationMs` types, and how `Success` is recorded in your real resource. Do not assume this query runs unchanged in classic/legacy modes or across every telemetry source.

KQL split by version if the app records custom dimensions or cloud role names:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize Requests=count(), Failed=countif(Success == false)
  by AppRoleName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

To distinguish staging from production when both share an Application Insights resource, configure explicit cloud role names or version/slot properties; do not assume default role names always separate two slots.

### 12.3. Alerts and rollback triggers

Illustrative internal release gates (purely example thresholds, not Azure SLAs):

- Production HTTP 5xx exceeds 2% for 5 consecutive minutes.
- p95 latency doubles baseline at comparable traffic.
- Dependency failure rates or queue backlogs breach agreed limits.
- Payment/order transaction errors appear.
- Readiness probes return 503 across multiple instances.

Decide in advance what happens when thresholds trip: immediate rollback, hold for investigation, or dial back canary traffic. Avoid fully unguarded auto-rollbacks when database migrations or irreversible transactions are involved.

## 13. Cost, performance, and availability

### 13.1. Deployment slot costs

A staging slot does not typically incur a separate App Service Plan fee just for existing, yet it consumes **the App Service Plan's compute**. If staging burns heavy CPU/RAM, production on the same plan can slow down. Verify supported features, slot limits, and tier pricing at deployment time.

Items to review:

- App Service Plan tier supporting slots and instance/scale-out costs.
- Combined CPU/RAM usage across production and staging.
- Application Insights/Log Analytics ingestion and retention.
- Networking, private endpoints, VNet integration, NAT Gateway, and egress if used.
- Databases, Key Vault, Storage, and downstream services staging connects to.
- Testing, load-test, and CI/CD infrastructure costs.

Do not run unbounded stress tests in staging on an App Service Plan shared with production without assessing instance load and pressure.

### 13.2. Scaling and high availability

Slots are a **software release tool**, not an independent HA/multi-region solution. Slots share an App Service Plan and can fail together on plan, region, or dependency outages. To raise availability, look at autoscaling, multiple instances, zone redundancy where supported by tier/region, multi-region routing, and data recovery mechanisms.

Warm-up lowers cold-start risk for a new version, but does not guarantee zero dropped connections or zero p95 latency spikes. **Measure real application behavior.**

## 14. Sample scenario: deploying a Java orders application

**Context:** An enterprise runs `orders-web` on Spring Boot in Azure App Service. Version v1 serves production. Version v2 adds an order-filtering API, adds an optional data column, and updates the admin UI.

### 14.1. Release plan

1. Prepare a backward-compatible database migration: add a nullable column so v1 keeps working.
2. Build artifact v2 once, sign/hash it, and store it in the artifact repository.
3. Deploy v2 to the staging slot with controlled settings, identity, and permissions.
4. Smoke test version, auth, read APIs, readiness endpoint, and dependency connectivity.
5. Disable or isolate unauthorized background tasks in staging and verify warm-up has no side effects.
6. Execute staging → production swap after approval.
7. Monitor 5xx errors, p95 latency, failed transactions, queue backlogs, and database connections.
8. On severe failures: assess data state and reverse-swap to the old version if still safe.
9. Once v2 stabilizes: complete remaining planned migrations and only then consider removing legacy schema elements.

### 14.2. Example rollback runbook

~~~yaml
releaseId: ORDERS-2026-11-20-02
app: orders-web
sourceSlot: staging
targetSlot: production
artifactVersion: v2.3.0
preSwap:
  - "Verify build SHA and artifact checksum"
  - "Readiness returns HTTP 200"
  - "Smoke tests pass"
  - "Backward-compatible schema migration completed"
  - "No unsafe background task in warm-up"
approval:
  required: true
postSwap:
  - "Check production /api/version"
  - "Monitor 5xx, p95 latency, dependency failures"
  - "Verify order creation and read flows safely"
rollback:
  - "Confirm previous version remains in staging"
  - "Assess database and external side effects"
  - "Run approved slot swap if safe"
  - "Verify production and record incident"
~~~

This is a release-governance template, not a valid Azure DevOps/GitHub Actions YAML schema or real release log.

### 14.3. Cases where a slot alone cannot roll back

- v2 dropped a column still required by v1.
- v2 sent notifications, charged payments, or consumed queues whose state v1 does not understand.
- v2 wrote backward-incompatible data formats.
- v2 modified secrets outside App Service.
- Artifact v1 in staging was already overwritten by another build.

These scenarios require dedicated data protocols, event-processing designs, and recovery plans.

## 15. Common errors and remediation

| Symptom | Possible cause | Check |
|---|---|---|
| Cannot create deployment slot | App Service Plan tier unsupported or quota reached | Check SKU and slot limits |
| Staging fails on access | Wrong artifact/runtime/startup command, auth, or access restriction | Deployment logs, application logs, hostname, and routes |
| Swap hangs or fails during warm-up | Readiness doesn't return accepted status, restart loop, or target config fails | `WEBSITE_SWAP_WARMUP_PING_PATH`/`STATUSES`, startup logs, dependencies |
| Warm-up returns 302 yet passes as ready | Accepted status codes not restricted | Enforce 200 and design proper health endpoint |
| Post-swap app connects to wrong database | Missing sticky setting, wrong secret reference, or target config | Inspect `slotSetting`, app settings, Key Vault references, and history |
| Staging modifies production data | Background job/migration ran during warm-up or source had prod permissions | Isolate tasks, check startup hooks, and use leases/flags |
| Production fails despite staging passing | Different target settings, domains, auth, networking, or dependencies | Inspect target settings, post-swap logs, and roles |
| Prior version missing from staging | Pipeline deployed again after swap or modified the artifact | Verify build SHA in both slots and release logs |
| Reverse swap does not restore data | DB migration or external side effects already occurred | Execute planned data rollback, not just code |
| 5xx/p95 spikes during swap | Restarts, cold caches, connection pooling, scaling, or dependencies | App Insights, startup times, health/readiness |
| Preview option unavailable | Current platform/feature does not support preview | Check App Service type and feature docs |
| Errors appear only on scale-out | In-memory sessions, local files, startup races, shared resources | Distributed session store, idempotency, per-instance telemetry |
| Secrets appear in logs | Scripts printing app settings, debug dumps, or pipeline output | Revoke secrets, restrict logs, fix pipeline, audit access |

### 15.1. Separating App Service issues from application issues

When a swap fails, check in order:

1. App Service Plan tier and slot limits.
2. Deployment status and exact artifact in staging.
3. Startup command, runtime, logs, and health endpoint.
4. App settings/connection strings and sticky configuration.
5. Networking, DNS, Key Vault, and slot identity.
6. Database schemas and queues/background jobs.
7. Swap operation status and Application Insights.
8. Live production version and rollback criteria.

Do not change multiple production settings simultaneously before capturing configuration and logs. Doing so obscures root cause and can break rollback paths.

## 16. Production deployment checklist

### Before deployment

- [ ] App Service Plan supports deployment slots and has available quota.
- [ ] Both production and staging have owners, RBAC, logging, and network protection.
- [ ] Traceable artifact version/build SHA exists.
- [ ] App settings and connection strings are classified as sticky vs. non-sticky.
- [ ] Key Vault references and managed identities are verified for each slot.
- [ ] Readiness endpoint has no side effects and returns clear status codes.
- [ ] `WEBSITE_SWAP_WARMUP_PING_PATH` and `STATUSES` are designed and tested.
- [ ] Migrations are backward-compatible and never run destructively on startup.
- [ ] Queue consumers, scheduled jobs, and external integrations are controlled.
- [ ] Baselines for 5xx/p95 latency/functional errors and an approval gate are ready.
- [ ] Prior artifact and DB/data recovery plan are available.

### After deploying to staging

- [ ] Staging is actually running the new release.
- [ ] Version/build SHA API matches the artifact.
- [ ] Smoke tests, auth, permissions, and DB/Key Vault connectivity pass.
- [ ] No startup errors, restart loops, or secret-leaking logs.
- [ ] Warm-up tested with target settings in an authorized environment.
- [ ] Approver confirms the release is ready to swap.

### After swap

- [ ] Production URL serves the new version and passes readiness.
- [ ] Error rates, latency, and dependency failures remain within thresholds.
- [ ] Critical business transactions succeed.
- [ ] Queue backlogs and background jobs show no duplicate processing.
- [ ] Previous version remains intact for rollback if needed.
- [ ] Release record logs UTC timestamp, approver, and outcome.
- [ ] No lingering debug configs or overly broad staging permissions.

## 17. Self-check questions

1. **What is a deployment slot?** An app runtime environment with its own hostname and configuration inside the same App Service Web App, used to stage a release before promoting it to production.
2. **Does a staging slot mean a completely separate server/region?** No; slots share an App Service Plan and underlying dependencies.
3. **Does a swap automatically migrate databases?** No. Swaps apply only to supported App Service content and configuration.
4. **What is the purpose of sticky settings?** To keep certain settings pinned to a slot rather than moving with the code version during a swap.
5. **Why can warm-up be dangerous if startup runs migrations?** The source slot may boot with target settings before traffic shifts; migrations could alter the live database.
6. **Does a 200 warm-up response prove all production transactions are safe?** No; it is only one readiness signal—smoke tests and monitoring are still required.
7. **What is `WEBSITE_SWAP_WARMUP_PING_PATH` used for?** Specifies the URL path for warm-up probes during a swap per App Service capabilities.
8. **Why configure `WEBSITE_SWAP_WARMUP_PING_STATUSES`?** To restrict which HTTP codes count as warm-up success, avoiding false positives on redirects/errors.
9. **When is swap with preview used?** When supported and you want to inspect the prepared state before completing the swap.
10. **Does rolling back via reverse swap restore database schemas?** No; databases and external side effects need separate plans.
11. **Can staging accidentally consume production messages?** Yes, if workers/queues and settings are not properly isolated.
12. **Why shouldn't secrets be hard-coded into artifacts?** Because artifacts move between slots and can leak via repos/logs; use managed identities and secret management.
13. **How does canary traffic routing differ from swap?** Canary splits a percentage of traffic to a slot; swap promotes the prepared version to production in a release action.
14. **Why is Application Insights still needed after a swap?** To catch 5xx errors, latency shifts, dependency issues, and bugs invisible to readiness pings.
15. **Is a "swap succeeded" status enough to declare a release finished?** Not yet. Business criteria, monitoring, and owner sign-off are required.

## 18. References

- [Azure App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — slot creation, swapping, preview, sticky settings, and warm-up.
- [Azure App Service overview](https://learn.microsoft.com/azure/app-service/overview) — application platform, App Service Plans, and hosting.
- [Configure App Service app settings](https://learn.microsoft.com/azure/app-service/configure-common) — app settings and connection strings.
- [Azure App Service configuration reference](https://learn.microsoft.com/azure/app-service/reference-app-settings) — supported application settings, including scenario-specific warm-up settings.
- [App Service health check](https://learn.microsoft.com/azure/app-service/monitor-instances-health-check) — instance health checks and usage.
- [Application Insights documentation](https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview) — release telemetry and error investigation.
- [App Service access restrictions](https://learn.microsoft.com/azure/app-service/app-service-ip-restrictions) — restricting access to apps and slots.
- [App Service Key Vault references](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — configuring secrets via Azure Key Vault.
- [Azure App Service pricing](https://azure.microsoft.com/pricing/details/app-service/) — checking current tiers and pricing.

**Conclusion:** Deployment slots decouple installing a new release from exposing users to it; warm-up lowers cold-start risk; and swapping promotes a prepared version to production without changing customer URLs. To keep the workflow genuinely safe, understand sticky settings and target config during warm-up, keep migrations backward-compatible, control background jobs, verify via telemetry, and maintain rollback plans for both code and data.
