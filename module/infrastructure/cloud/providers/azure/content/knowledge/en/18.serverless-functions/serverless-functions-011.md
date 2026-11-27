# Deploying, Environment Separation, and Function Versioning

An Azure Function may run smoothly on a developer workstation yet fail right after deployment: triggers are not discovered, Storage config is wrong, the Java version mismatches, or staging accidentally consumes production messages. With serverless apps, **a successful deployment does not prove the Function is ready for business traffic**. A reliable release workflow must govern artifacts, runtimes, configuration, data, access permissions, testing, and rollback.

This lesson belongs to the **Serverless with Azure Functions** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Entra ID through virtual networks, compute services, storage, and data, while teaching how to deploy, monitor, secure, and control application costs. The focus here is **deploying Functions consistently across dev, staging, and production and managing versions safely**, with Java/Maven, Azure CLI, and CI/CD examples.

## 1. Learning Objectives

After completing this lesson, you will be able to:

- Distinguish Function, Function App, hosting plan, environment, deployment slot, and release.
- Pick a deployment method by hosting plan: Maven/Core Tools, package, One Deploy, CI/CD, or container image.
- Design **dev, staging, and production** with isolated data sources, identities, Key Vaults, and monitoring.
- Know when to use **separate Function Apps** vs. **deployment slots**.
- Distinguish versions of application code, Azure Functions host, Java worker, binding extensions, and event contracts.
- Design a **build once, test, promote same artifact** pipeline with approvals and auditing.
- Prevent staging Timer/Queue/Event-triggered Functions from touching production data.
- Verify Function discovery, invocations, telemetry, rollback, and post-deploy costs.

## 2. Function, Function App, and Release Units

A **Function** is a handler invoked by a trigger such as HTTP, Timer, Queue, Service Bus, or Event Hubs. A **Function App** is the configuration and deployment boundary containing one or more Functions, sharing a runtime host, app settings, and hosting-plan scaling behavior.

~~~text
Git commit
   |
   | Build + test + package
   v
Versioned Function App artifact
   |
   +----> Function App DEV  ----> Queue / DB / Key Vault dev
   |
   +----> Function App STG  ----> Queue / DB / Key Vault staging
   |
   +----> Function App PROD ----> Queue / DB / Key Vault production
               |
               +-- Azure Functions host
               +-- Java worker
               +-- HTTP Function
               +-- Queue Function
               +-- Timer Function
~~~

| Concept | What It Governs | Do Not Confuse With |
|---|---|---|
| **Function** | Trigger, bindings, and business handler | The entire Azure application |
| **Function App** | Runtime, config, identity, deployment unit for a group of Functions | An individual Java method |
| **Hosting plan** | Compute, scaling, memory, networking, features, and billing | Release version |
| **Deployment artifact** | Code/JAR, `host.json`, function metadata, dependencies | App settings holding secrets |
| **Environment** | Dedicated resources, data, permissions, and processes for dev/stg/prod | A single `APP_ENV` variable |
| **Deployment slot** | Staging/swap execution slot inside a Function App where supported | A completely isolated environment |
| **Release** | Immutable artifact + config revision + tests + approvals | Running a single publish command |

Deploying a new package updates multiple Functions inside the Function App at once. Therefore, if two workloads have different release cadences, scaling needs, or security boundaries, split them into separate **Function Apps** even when they share a Git repository.

## 3. Hosting Plans Determine Deployment Capabilities

Azure Functions hosting models behave differently. Before building CI/CD, verify the **hosting plan, OS, runtime, and support matrix**.

| Hosting Option | Operational Model | Deployment Considerations |
|---|---|---|
| **Flex Consumption** | Serverless with Flex scaling and supported networking/concurrency options | Typically uses **One Deploy** via Flex-supported tooling; do not apply legacy ZIP Deploy/Kudu/slot guides |
| **Consumption (classic model)** | Execution-based billing and scaling | Filesystem, package, and feature limits apply; check current plan documentation |
| **Elastic Premium** | Pre-warmed/always-ready instances and advanced networking | Supports deployment slots where config/tier permits; carries baseline compute cost |
| **Dedicated / App Service Plan** | Tier-based provisioned compute | Slots, Always On, and limits depend on SKU tier |
| **Azure Container Apps hosting** | Container-based Functions per supported features | Deploy container images/revisions; do not assume Kudu/ZIP Deploy like code-based apps |

**There is no universal ZIP Deploy command across every plan.** A historical tutorial using `az functionapp deployment source config-zip` should not be run on Flex Consumption if that method is unsupported. Use Maven, Core Tools, GitHub Actions, or APIs documented for your exact current plan.

### Choosing a Plan for Real Requirements

1. Are your trigger types and Java/.NET/Python/Node runtime supported?
2. Do cold starts, concurrency, timeouts, memory, and scaling fit the workload?
3. Do you need VNet integration, private endpoints, or managed outbound IPs?
4. Do you need deployment slots or **two separate Function Apps** for stronger isolation?
5. Do you need custom containers or specialized OS libraries?
6. What are your RTO/RPO, business limits, and budget?

Do not move all workloads onto Premium solely for slot swaps if two independent apps with proper routing give better isolation at lower cost.

## 4. Version Management: Multiple Layers to Track

The phrase "Function version" carries at least six meanings:

| Layer | Example | Management Approach |
|---|---|---|
| **Code release** | `1.4.2`, commit `a1b2c3` | Git tag/SHA, artifact checksum, changelog |
| **Functions host runtime** | Azure Functions 4.x | `FUNCTIONS_EXTENSION_VERSION`, tracked against support lifecycle |
| **Language worker** | `FUNCTIONS_WORKER_RUNTIME=java`; Java 17 | Stack/OS/JDK bytecode target and deployment settings |
| **Binding extensions** | Storage, Event Hubs, Service Bus extension versions | Maven/`host.json`/bindings, compatibility tests |
| **Infrastructure/config revision** | Bicep/Terraform commit | IaC state, approvals, drift detection |
| **Event/API/data schema** | `order-created.v2`, `/api/v2` | Contract tests, migration/compatibility plans |

**`FUNCTIONS_EXTENSION_VERSION=~4`** selects Functions host major version 4 per supported config; it **does not** mean your business Java Function is release 4.0. **`FUNCTIONS_WORKER_RUNTIME=java`** selects the language worker, yet **does not automatically set the JDK bytecode target** of your artifact.

Every release should maintain an internal manifest:

~~~text
Application: orders-functions
Release: 1.4.2
Commit: a1b2c3d4
Artifact checksum: sha256:<CHECKSUM>
Functions host major: 4
Language worker: Java 17
Infrastructure revision: infra-2026-11-20
Event schema: order-created.v2
Released to: staging then production
~~~

This is **release metadata**, not a `host.json` file or runnable CLI script.

## 5. Traceable Release Example: Java Azure Function

Let's build an HTTP Function **`ReleaseInfo`** that reads two non-sensitive app settings: **`APP_ENV`** and **`APP_VERSION`**.

~~~java
package com.example.functions;

import java.util.Optional;
import com.microsoft.azure.functions.*;
import com.microsoft.azure.functions.annotation.*;

public class ReleaseInfoFunction {
    @FunctionName("ReleaseInfo")
    public HttpResponseMessage run(
        @HttpTrigger(
            name = "req",
            methods = {HttpMethod.GET},
            authLevel = AuthorizationLevel.FUNCTION,
            route = "release-info"
        ) HttpRequestMessage<Optional<String>> request,
        ExecutionContext context
    ) {
        String env = System.getenv().getOrDefault("APP_ENV", "unknown");
        String version =
            System.getenv().getOrDefault("APP_VERSION", "unversioned");

        context.getLogger().info("ReleaseInfo invoked");

        return request.createResponseBuilder(HttpStatus.OK)
            .header("Content-Type", "text/plain; charset=utf-8")
            .body("environment=" + env + "\nversion=" + version)
            .build();
    }
}
~~~

This sample Function requires a Java Functions/Maven project configured with **`azure-functions-java-library`**. The API returns non-sensitive release metadata—never return secrets, access tokens, or full environment variables.

**`AuthorizationLevel.FUNCTION`** requires a Function key on Azure endpoints outside specific platform auth exceptions. Local Core Tools runs may not enforce keys identically to Azure, so **a passing local `curl` does not prove a cloud endpoint is secure**.

### Project Structure

~~~text
orders-functions/
├── pom.xml
├── host.json
├── local.settings.json          # local only, never commit secrets
├── src/main/java/com/example/functions/ReleaseInfoFunction.java
├── src/test/java/...            # test code
└── target/azure-functions/<PACKAGE_NAME>/
    ├── host.json
    ├── ReleaseInfo/function.json
    ├── orders-functions-*.jar
    └── lib/...
~~~

Exact output paths depend on plugin, Maven configuration, and artifact layout. **Never upload a bare JAR** when the Functions host expects `host.json`, `function.json`, and dependencies.

### `host.json` Is Not Runtime 2.x

~~~json
{
  "version": "2.0"
}
~~~

**`version=2.0`** in `host.json` is the file schema version, **not** Functions host major 2 or business code v2.0.

### Maven/Plugin

A Java project requires:

- **`azure-functions-java-library`** for annotations and request/response types.
- **`azure-functions-maven-plugin`** for packaging and optional deployment per configuration.
- Compiler target/JDK matching the Function App's configured runtime.
- Test dependencies and business libraries.

Illustrative **snippet** (not a complete `pom.xml`):

~~~xml
<plugin>
    <groupId>com.microsoft.azure</groupId>
    <artifactId>azure-functions-maven-plugin</artifactId>
    <version>VERSION_TO_VERIFY</version>
    <configuration>
        <appName>orders-functions-lab</appName>
        <runtime>
            <os>linux</os>
            <javaVersion>17</javaVersion>
        </runtime>
    </configuration>
</plugin>
~~~

Replace **`VERSION_TO_VERIFY`** with a supported plugin version, add required POM sections, and consult the official **Java Functions Maven archetype** docs. Never copy an outdated Maven plugin version assuming it supports every hosting plan.

## 6. Local Testing and the Role of `local.settings.json`

A Java project created from an official template runs with a compatible JDK, Maven, **Azure Functions Core Tools v4**, and dependencies.

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "APP_ENV": "local",
    "APP_VERSION": "dev"
  }
}
~~~

Place this in **`local.settings.json`** for local testing only. **`UseDevelopmentStorage=true`** requires Azurite or a compatible local Storage emulator for triggers/host features needing Storage. This file **does not automatically deploy as Azure app settings**, and in real projects it may hold secrets so it must stay out of Git.

From a configured Maven project:

~~~bash
mvn -B clean test
mvn -B package
mvn azure-functions:run
~~~

Once the local host discovers **`ReleaseInfo`**, test the endpoint:

~~~bash
curl -i http://localhost:7071/api/release-info
~~~

Core Tools uses local port 7071 by default, though it is configurable. **Never hardcode port 7071 inside Java methods**: HTTP routing is managed by the Functions host.

Local tests do not automatically validate managed identity, Azure Storage firewalls, VNets, cold starts, concurrency, or plan-specific deployments; run integration tests in an isolated Azure environment.

## 7. Designing True Dev, Staging, and Production Environments

A sound design **separates resources, permissions, and data**, not just `APP_ENV` values.

~~~text
Same tested artifact
      |
      +----> fa-orders-dev  ---> Queue/DB/Storage/KV dev
      |
      +----> fa-orders-stg  ---> Queue/DB/Storage/KV staging
      |
      +----> fa-orders-prod ---> Queue/DB/Storage/KV production
~~~

| Component | Dev | Staging | Production |
|---|---|---|---|
| Function App | `fa-orders-dev` | `fa-orders-stg` | `fa-orders-prod` |
| Host storage | Dev Storage | Staging Storage | Production Storage |
| Queue/topic/consumer group | Synthetic event source | Staging source | Production source |
| Database | Synthetic data | Safe test data | Real data |
| Managed identity | Dev identity | Staging identity | Production identity |
| Key Vault | Dev Vault | Staging Vault | Production Vault |
| App settings | `APP_ENV=dev` | `APP_ENV=staging` | `APP_ENV=production` |
| Monitoring | Dev logs/metrics | Smoke/regression | SLO/on-call alerts |
| Pipeline | Automated deploy | QA gate | Approvals and rollout controls |

Names are illustrative, not pre-created resources. Larger organizations often separate subscriptions or resource groups and enforce Azure Policy/RBAC per environment.

### Risks of Shared Dependencies

- A staging Function's **`QueueTrigger`** accidentally points to the production queue and consumes live messages.
- Two Function Apps improperly share **`AzureWebJobsStorage`/host identity**, causing state/lease conflicts or erratic timer behavior.
- Staging writes to the production database, corrupting live data during integration tests.
- A dev pipeline holds permission to deploy to prod without approvals.
- Staging identity holds read access to the entire production Key Vault.

**`APP_ENV=staging` is not a security boundary.** Verify resource IDs, credential scopes, effective permissions, and network paths.

## 8. Independent Function Apps vs. Deployment Slots?

A **Deployment slot** is a secondary deployment target inside a Function App on supported hosting plans. It helps validate artifacts before **swapping** into production, yet not all plans support slots and slots are not fully isolated environments.

| Criterion | Separate Function Apps | Staging Slot in One Function App |
|---|---|---|
| Compute, resource boundary | Fully independent per app/plan/RG/subscription | Can share plan and many settings |
| Identity and IAM | Cleanly isolated per app | Depends on slot and app properties |
| Event sources | Easy to separate cleanly | **Must be configured separately** to avoid real triggers |
| HTTP rollout | Shift routes/gateway or deploy per app | Swap on supported plans |
| Feature availability | Works across hosting models | Depends on SKU/hosting model |
| Cost | May require separate compute per env | Slots still consume allocated plan resources |

**Do not assume Flex Consumption supports deployment slots and swaps like Premium or Dedicated.** Check current feature matrices, OS, and plan capabilities. If a plan lacks slots or requires strict data isolation, use separate Function Apps.

HTTP Functions generally fit slot swaps far better than Functions running **`TimerTrigger`, `QueueTrigger`, `ServiceBusTrigger`, `EventHubTrigger`, or Durable Functions**. A staging slot is **not automatically read-only** and does not automatically disable triggers.

## 9. App Settings and Permissions Across Environments

App settings control runtime and application behavior. Key settings to know:

| Setting | Meaning | Notes |
|---|---|---|
| `FUNCTIONS_EXTENSION_VERSION` | Functions host major version, e.g. `~4` | Not the code release version |
| `FUNCTIONS_WORKER_RUNTIME` | Language worker, e.g. `java` | Does not change bytecode target |
| `AzureWebJobsStorage` | Host storage/state per supported model | Isolate per env; verify identity/network |
| `APP_ENV` | Business environment label | Does not grant or restrict IAM |
| `APP_VERSION` | Deployed release version | Never store secrets here |
| `RELEASE_COMMIT` | Git SHA from pipeline | Supports auditing |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Telemetry destination | Do not print to logs |
| `OrdersQueueConnection` | Binding/SDK connection name for queue | Dev/stg/prod sources must differ |

**`AzureWebJobsStorage`** supports connection strings or identity-based config depending on runtime, extension, and plan. Either way, verify the actual storage account, data-plane permissions, firewall, and host identity to prevent conflicts.

### Safe Inspection via Azure CLI

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

RG="<FUNCTION_RESOURCE_GROUP>"
APP="<FUNCTION_APP_NAME>"

az functionapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,kind:kind,location:location}" \
  --output json

az functionapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

**Never omit `--query` and print all values into CI logs**, because App settings can contain connection strings or sensitive secret references.

Example updating **non-sensitive** settings on an approved lab Function App:

~~~bash
az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings APP_ENV=dev APP_VERSION=1.4.2
~~~

Updating app settings can **restart/recycle the Function App**, disrupting active invocations and trigger listeners. In production, use IaC, CI/CD, or formal change management rather than ad-hoc edits.

## 10. Managed Identity, Key Vault, and IAM Responsibilities

To protect secrets:

1. Enable **managed identity** on each Function App where supported.
2. Assign least-privilege **data-plane roles** for Storage, Key Vault, Service Bus, or databases.
3. Prefer identity-based connections when supported by bindings and SDKs.
4. Use **Azure Key Vault references** for secrets that cannot yet be eliminated.
5. Ensure DNS, VNet integration, and Private Endpoints work when resources restrict public networks.
6. Implement rotation, auditing, and reference-resolution checks.

Key Vault reference example:

~~~text
@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/<SECRET_NAME>/)
~~~

**Having a managed identity does not equal having permissions.** Functions still hit 403 when missing Storage/Key Vault data roles, or time out when missing Private DNS or egress routes.

Separate three distinct principals:

- **Build identity:** reads source/dependencies and builds artifacts; needs zero prod access.
- **Deployment identity:** deploys only to target apps/slots behind approvals; prefer OIDC/workload identity federation where supported by CI.
- **Runtime managed identity:** accesses business data sources at runtime; needs zero rights to create or delete Function Apps.

Never drop in a full-access shared account key just to bypass an RBAC permission error.

## 11. Sticky Settings and Swap Rules on Deployment Slots

On hosting plans **that support deployment slots**, settings marked as **deployment slot settings** (sticky) remain pinned to their slot during a swap per Azure App Service/Functions rules. This is essential because staging and production need separate connection strings and secret scopes.

~~~text
Function App: fa-orders-prod
  |
  +-- production slot
  |     APP_ENV=production            (sticky)
  |     OrdersQueueConnection=prod    (sticky)
  |     APP_VERSION=1.4.1             (release)
  |
  +-- staging slot
        APP_ENV=staging               (sticky)
        OrdersQueueConnection=stg     (sticky)
        APP_VERSION=1.4.2             (release)
~~~

After swapping, **code 1.4.2** must run against production data rather than pulling the staging queue along with it. Verify which settings **swap**, which stay **sticky**, and plan-specific swap rules.

Settings commonly marked sticky: **`APP_ENV`**, binding connections, database endpoints, `AzureWebJobsStorage` and environment-specific host settings, Key Vault references, and trigger enable/disable flags. Do not mark settings sticky blindly: some platform settings follow special swap rules, and changing settings can trigger host restarts.

Example marking a non-sensitive setting slot-specific:

~~~bash
az functionapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --slot-settings APP_ENV=staging
~~~

**This command applies only when the slot exists and the hosting model supports it.** Before running, review `az functionapp config appsettings set --help` and organizational policy. For secrets, never pass plaintext values in shell history; use Key Vault references.

## 12. Staging Triggers Can Consume Real Events

The biggest hazard with event-driven Functions is that **a staging slot is not an inert copy**. Its triggers can fire as soon as code and bindings start up.

~~~text
Queue: orders-production
            |
            +---- production Function: ProcessOrders
            |
            +---- staging Function: ProcessOrders (MISCONFIGURATION)
                                      |
                                      v
                           Processing production messages!
~~~

Consequences include **stealing messages from production, sending duplicate emails, mutating live data, or failing on incompatible schemas**. With Event Hubs and Service Bus, exact effects depend on consumer groups/subscriptions, checkpoints, and protocols; no single outcome applies to every trigger.

### Controls

- Isolate **queues, topics, consumer groups, and storage** for staging.
- Keep connection settings separated per environment/slot.
- Disable Functions that must not run in staging where supported.
- For `TimerTrigger`, use sandbox schedules or disable them; never leave production cron jobs running in staging.
- Test idempotency, retries, and poison handling strictly on **synthetic data**.
- Inspect logs to verify triggers are not reading production events.

Example app setting disabling a Function named **`ProcessOrders`**:

~~~text
AzureWebJobs.ProcessOrders.Disabled=true
~~~

The name must match the **Function name** discovered by the host. Disabling a function does not replace IAM/resource isolation: a non-sticky setting or redeploy can re-enable the listener. For HTTP triggers, admin/master key behavior differs from event triggers; verify active state in runtime logs.

### Timers, Host IDs, and Storage

TimerMonitor and host state can write coordination data into backing storage. If staging and production share the same **`AzureWebJobsStorage`** or an improperly configured host identity, lease/lock contention or erratic schedules can occur. **Isolate host storage and host identities** per application architecture guidance.

### Durable Functions Are Even More Sensitive

Durable orchestrations persist state and event history across deployments. Changing running orchestrator logic can violate **determinism**. Never treat slot swaps as automatic Durable instance migration. Use versioned orchestrator names, side-by-side support, separate task hubs, and handle in-flight instances per Durable Functions guidance.

## 13. Comparing Deployment Methods

**Build** produces an artifact; **deploy** delivers it to the target environment. Common mechanisms:

| Method | Typical Use | Limits to Verify |
|---|---|---|
| **Maven Azure Functions plugin** | Java Maven Functions | POM `appName`/`resourceGroup`/plan/OS, plugin version, permissions |
| **Functions Core Tools publish** | Developer or pipeline per supported runtime | Plan/language compatibility, local/project settings |
| **ZIP Deploy** | Certain code-based Functions plans | Do not assume support on Flex Consumption |
| **Run from package** | Mounts packaged artifact rather than copying loose files | Filesystem, storage, and settings vary by hosting model |
| **One Deploy** | Flex Consumption and supported tooling | Distinct workflow; do not copy legacy Kudu/ZIP scripts |
| **GitHub Actions / Azure Pipelines** | Build once, approvals, promotion | Choose deploy action/version compatible with the plan |
| **Custom container image** | Custom runtimes/dependencies on supported plans | ACR image version/digest, networking, identity, container startup |

Never edit production code directly via Portal, Kudu, or FTP as a substitute for CI/CD. Governed releases use **immutable artifacts** with checksums, build provenance, and repeatable deployments.

### ZIP Deploy ≠ Run from Package ≠ One Deploy

**ZIP Deploy** pushes a package to supported App Service/Functions environments; **run from package** mounts/reads the packaged archive rather than running from a writable directory; **One Deploy** is the method used for Flex Consumption with compatible tooling. They sound similar, yet **CLI commands are not arbitrarily interchangeable**.

Commands like `az functionapp deployment source config-zip` in older tutorials should only be used after verifying plan and deployment mode support—never apply them blindly to Flex.

## 14. Deploying Java Functions with Maven

In a Java project generated from an official **Azure Functions Maven archetype/template**, the plugin and POM target configuration are pre-wired:

~~~bash
mvn -B clean test
mvn -B package

# Only after verifying app, plan, OS, subscription,
# resource group, and user/service identity in the POM:
mvn -B azure-functions:deploy
~~~

**Deploy commands modify live Azure resources.** Before running, inspect `appName`, `resourceGroup`, `region`, and `runtime` in the POM and check whether the plugin creates or updates the Function App. Never let a lab POM target production.

### Build Once, Deploy Many

To ensure staging and production run the **exact same binary**:

1. CI checks out a pinned **Git SHA**.
2. Builds once using verified JDK, Maven, and dependencies.
3. Runs tests and vulnerability/SCA scans.
4. Archives the complete **Functions deployment package** and checksum.
5. Deploys the package to staging using a plan-supported method.
6. Once staging passes, promotes that **exact archived package** to production.
7. Swaps app settings per environment—**never bake passwords or queue names into the JAR**.

If the production job re-runs `mvn clean package` from source instead of reusing the staging artifact, you cannot claim "promoted the same artifact": even the same commit can build differently if dependencies or toolchains shift.

## 15. CI/CD with Testing and Approvals

~~~mermaid
flowchart TD
    A[Git commit] --> B[Build, unit tests, SCA]
    B --> C[Immutable package + checksum]
    C --> D[Deploy dev]
    D --> E[Dev integration tests]
    E --> F[Deploy staging]
    F --> G[Smoke, event, contract tests]
    G --> H{Production approval?}
    H -- No --> I[Stop and investigate]
    H -- Yes --> J[Promote exact artifact]
    J --> K[Verify release + triggers + SLO]
    K --> L{Healthy?}
    L -- No --> M[Rollback / safe pause]
    L -- Yes --> N[Record release]
~~~

### GitHub Actions or Azure Pipelines

Use **OIDC/workload identity federation** so CI obtains tokens via Microsoft Entra ID instead of storing long-lived client secrets. Separate pipeline identities:

- Build identity holds only repository/dependency read permissions.
- Staging deploy identity updates only the staging app/slot.
- Production deploy identity sits behind approvals with narrow scope.
- Runtime managed identity accesses only required business data sources.

Illustrative **pseudo-workflow** showing stages (**not runnable GitHub Actions YAML**):

~~~yaml
build:
  checkout: fixed-commit
  java: approved-jdk
  test: mvn clean verify
  output: immutable-functions-package-and-checksum

deploy-staging:
  identity: staging-oidc
  artifact: exact-output-from-build
  target: fa-orders-stg
  checks: smoke-tests-and-event-contracts

deploy-production:
  identity: production-oidc
  approval: required
  artifact: exact-output-from-build
  target: fa-orders-prod
  checks: release-info-and-observability
~~~

Real workflows require exact action versions (`azure/login`, plan-compatible Functions deploy actions/tooling), `id-token: write` permission for OIDC, artifact paths, RBAC, and branch/environment protection rules. Never put client secrets or publishing profiles into source code or workflow logs.

### Four Release Control Locks

1. Pinned **Git commit**.
2. Tested **artifact checksum**.
3. Approved **IaC/config revision**.
4. Verified **host/worker/binding compatibility** for the target environment.

## 16. Checking and Creating Deployment Slots When Supported

First list slots on the target Function App:

~~~bash
RG="<FUNCTION_APP_RESOURCE_GROUP>"
APP="<EXISTING_FUNCTION_APP>"

az functionapp deployment slot list \
  --resource-group "$RG" \
  --name "$APP" \
  --output table
~~~

If supported by plan/OS and approved:

~~~bash
az functionapp deployment slot create \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging
~~~

A new slot can execute code/triggers and consume plan compute, carrying **operational and cost impact**. Once created, configure separate event/storage sources, trigger disablement, identity, and sticky settings before deploying code.

### Swapping Verified Code

~~~bash
az functionapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

**This is a production-impacting operation**—never run it casually in a shared lab. Confirm the Function App/plan supports swaps, staging passed tests, sticky settings are right, event triggers are safe, and downtime/rollback plans plus change approvals are ready.

Swaps can trigger restarts, replace running code, and apply configuration per service rules. **A successful swap does not guarantee zero duplicate events, misfired timers, or database side effects.**

## 17. Rolling Out an HTTP-Triggered Function with Slots

Suppose production serves **v1.4.1** and needs to release **v1.4.2**:

1. Build and archive artifact **v1.4.2** with checksum.
2. Verify the staging slot does not point to production DB/queues.
3. Deploy artifact to staging; verify Functions host discovers **`ReleaseInfo`**.
4. Call the staging endpoint with the staging Function key, confirming **`APP_ENV=staging`** and **`APP_VERSION=1.4.2`**.
5. Run smoke/integration tests and inspect latency, errors, and host logs.
6. Confirm sticky settings, approvals, and rollback steps.
7. Swap if supported by the hosting plan.
8. Call the production endpoint to confirm the new release, permissions, dependencies, and SLOs.
9. Retain the previous good artifact for rollback; monitor errors post-cutover.

### Using a Function Key During Smoke Tests

With **`AuthorizationLevel.FUNCTION`**, pass a valid Function key securely:

~~~bash
# FUNCTION_KEY is retrieved from a secret store, never printed to the screen.
curl -fsS \
  -H "x-functions-key: $FUNCTION_KEY" \
  "https://<FUNCTION_APP_HOST>/api/release-info"
~~~

Never put Function keys in shared URLs, plaintext shell history, pipeline logs, or tickets. Never use a broad master key when a Function-scoped key suffices for testing.

**`ReleaseInfo`** verifies the active version—it does not prove downstream dependencies or triggers are healthy. Combine it with synthetic requests, Application Insights, and business workflow tests.

## 18. Event-Driven Releases Differ from HTTP Releases

Event sources push messages to Functions regardless of whether anyone calls an HTTP endpoint. Deploying can restart the host, re-register listeners, or reprocess events depending on trigger semantics.

### `QueueTrigger` Rollout Scenario

1. Lock message schemas and keep consumers **backward/forward compatible** as needed.
2. Build artifact and record checksum.
3. Deploy to a staging Function App reading only the **staging queue**.
4. Test normal, malformed messages, retries, duplicates, out-of-order delivery, and poison handling.
5. Verify idempotency of database writes and notifications.
6. Prepare a pause/drain runbook for major breaking version changes.
7. Deploy to production during an approved window, watching backlogs and errors.
8. On failure, pause safely, verify data/schema compatibility, and roll back only if safe.

Many event platforms and trigger modes produce **at-least-once delivery** or retries. Never build business logic on an absolute **exactly-once** assumption; enforce idempotency/deduplication by event ID or business key and maintain poison/dead-letter procedures.

### Versioned Routing Instead of Sharing One Queue

~~~text
Producer
   |
   +--> orders-v1 queue/topic --> Function v1
   |
   +--> orders-v2 queue/topic --> Function v2
~~~

This logical diagram illustrates controlled migration. Real systems use event schema versions, routes, topics/subscriptions, or consumer groups. Never let v1 and v2 read the same production queue without understanding broker semantics and call it a "canary."

### `TimerTrigger`, Event Hubs, and Durable Functions

- **Timer:** disable staging jobs or use isolated schedules/data; inspect host storage and schedule monitors.
- **Event Hubs:** manage consumer groups, checkpoints, and replays; separate groups can read the same events independently.
- **Service Bus:** understand subscriptions, locks, retries, dead-letter queues, and competing listeners on the same subscription.
- **Durable:** keep orchestrators deterministic, account for in-flight instances and task hubs, and never treat slot swaps as state migration.

## 19. Semantic Versioning for APIs and Event Contracts

Function App versioning requires data compatibility:

| Target | Typically Safer Change | Breaking Change |
|---|---|---|
| HTTP API | Add optional fields while preserving old routes | Remove fields clients read |
| Queue message | Add fields with defaults; consumers ignore unknown fields | Redefine meaning of required fields |
| Database | Expand-and-contract migrations | Drop columns before all consumers upgrade |
| Durable orchestration | Keep old code for in-flight instances | Alter flow and break determinism |
| App settings | Add defaults and config validation | Rename settings without updating IaC |
| Timer job | Idempotency and checkpoints | Assume jobs never retry |

Example of two HTTP API versions:

~~~text
GET /api/v1/orders/{id}
GET /api/v2/orders/{id}
~~~

The **v1/v2** routes version the **API contract**, not the Functions host version. You can host both in one Function App or split them into separate apps depending on SLAs, ownership, and routing.

**Semantic Versioning** communicates impact (`MAJOR.MINOR.PATCH`), while **Git SHA/checksum** identifies the exact running artifact. Never rely on mutable **`latest`** tags as release proof.

## 20. Upgrading Host, Java, and Binding Extensions

### Functions Host Runtime

**`FUNCTIONS_EXTENSION_VERSION`** selects the supported platform host major version. Before upgrading:

- Review official lifecycle support and breaking changes.
- Verify language worker, bindings, `host.json`, and deployment plan.
- Test in staging with isolated equivalent triggers and data sources.
- Retain previous artifacts and IaC revisions for rollback where supported.

### Java Runtime

Align four pieces:

1. CI JDK.
2. **`maven-compiler-plugin`** source/target/release.
3. Java runtime configured on the Azure Function App.
4. Functions Java SDK, Maven plugin, and libraries.

If CI compiles Java 21 bytecode while the Function App runs Java 17, you will hit **`UnsupportedClassVersionError`**. Guessing a different `FUNCTIONS_EXTENSION_VERSION` instead of `~4` will not fix a bytecode mismatch.

### Binding Extensions

Triggers and bindings (Storage Queue, Blob, Service Bus, Event Hubs, etc.) carry separate extension versions and metadata. In Java, the Maven plugin and Functions host generate/load binding metadata like **`function.json`**. Some language models use **extension bundles** in `host.json`, while others reference extension packages differently.

**Do not copy an old `host.json` `extensionBundle` range blindly into every Java project.** Check current Java Functions and hosting runtime documentation, test triggers with real events in a sandbox, and confirm host logs show zero binding load errors.

## 21. Managing Configuration with Infrastructure as Code

A production release depends on more than a JAR:

- Function App, hosting plan, region, OS, and runtime.
- Host storage, queues/topics/event sources, and databases.
- Managed identities and role assignments.
- App settings, Key Vault references, and slot stickiness.
- VNet Integration, Private Endpoints, DNS/egress, and firewalls where used.
- Application Insights, Log Analytics, alert rules, and Action Groups.
- Azure Policy, tags, locks, budgets, and CI/CD roles.

Declare infrastructure via **Bicep, Terraform, or ARM** per organizational standards; avoid manual sequences of Portal clicks that cannot be reproduced.

Conceptual **IaC model example** (not valid Azure Bicep/Terraform/YAML deployment syntax):

~~~yaml
functions:
  - name: fa-orders-stg
    environment: staging
    runtime:
      hostMajor: 4
      worker: java
      javaVersion: 17
    hostStorage: stordersstg
    eventSource: orders-staging
    identity: managed
    appSettings:
      APP_ENV: staging
      ORDERS_QUEUE_NAME: orders-staging
    keyVaultReferences:
      DB_SECRET: staging-db-secret

  - name: fa-orders-prod
    environment: production
    runtime:
      hostMajor: 4
      worker: java
      javaVersion: 17
    hostStorage: stordersprod
    eventSource: orders-production
    identity: managed
~~~

In CI/CD, follow **plan → review → apply** and retain revisions to catch **configuration drift**. If an operator disables a Function during an incident, the IaC pipeline must not silently re-enable it without change reconciliation and approval.

**IaC does not replace data backups or message recovery.** Infrastructure deployment can succeed while Java Functions still fail trigger discovery if the code package is wrong.

## 22. Testing Releases Before and After Deployment

| Stage | Checks | What It Proves |
|---|---|---|
| Pull request | Unit tests, linting, SCA | Code/dependencies have no basic defects |
| Build | Maven compile/package, checksum | Artifact built cleanly and traceable |
| Local | Core Tools + Azurite or test endpoints | Function metadata/logic works locally |
| Dev | Identity/network/binding integration tests | App integrates with dev dependencies |
| Staging | Contract tests, retries, duplicate events, smoke tests | Near-production behavior without risking live data |
| Pre-prod | Config/runtime diff, plan support, approvals | Minimizes config and deployment risk |
| Post-prod | `ReleaseInfo`, triggers, monitoring/SLO | New release works in production |
| Rollback rehearsal | Re-deploy previous version, test event schema | Reliable recovery path exists |

**HTTP smoke tests** must never write live production data. **Event smoke tests** must use sandbox queues/topics and synthetic messages only. When testing Durable Functions, isolate task hubs and instances so live production runs are never touched.

### Package Verification

A Java build produces multiple files under `target`. Before deploying, confirm the package contains:

1. Valid **`host.json`** schema and config.
2. Plugin-generated **`function.json`** for every Function.
3. Complete JAR/class files and dependencies.
4. Function names, routes, and trigger metadata matching source code.
5. Zero `local.settings.json` files with secrets, sensitive source maps, or stray files.

**A successful deploy status does not guarantee the host discovered every Function method.** Always check the target Function list and host logs.

## 23. Post-Deploy Observability with Azure Monitor and Application Insights

A release is safe only when operational signals stabilize:

| Signal | Used to Verify |
|---|---|
| Function discovery and host startup | Host loaded all Functions without extension errors |
| Invocation count/success/failure | Triggers actually invoke code without rising failures |
| Duration p50/p95/p99 | Latency didn't regress or breach SLO |
| Queue depth/oldest event age | Consumers keep pace with producers |
| Retries/dead-letter/poison messages | Which events fail or repeat |
| Dependency failures | Storage/Key Vault/Service Bus/DB IAM or network errors |
| Cold start/instance metrics | Runtime or plan bottlenecks |
| Cost/usage | Executions/compute, Storage, telemetry, egress |

**Application Insights** captures Function requests, exceptions, dependencies, and traces per integration settings. Log Analytics table/column names vary between workspace-based Application Insights and classic setups; never copy queries without verifying your schema.

Example KQL for environments with **`AppRequests`**:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Invocations = count(),
    Failures = countif(Success == false)
  by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

This assumes `AppRequests` exists; for non-HTTP triggers or other telemetry types, query **`AppTraces`, `AppExceptions`**, or your actual schema. Never assume every invocation creates an `AppRequests` row.

Tag telemetry with **`APP_VERSION`**, Git SHA, and environment as custom dimensions where supported by the SDK—**never attach connection strings or sensitive customer identifiers**.

### Alerting on Deployment Regressions

Good production alerts include:

- Error rate or latency thresholds tied to SLOs.
- Observation windows that filter out cold-start or low-traffic noise.
- Absence alerts when metrics stop arriving or triggers stop firing.
- Action Groups/on-call recipients, escalation paths, and runbooks.
- Specific release metadata, rollout window, and rollback criteria.

Never rely solely on a green checkmark in Deployment Center.

## 24. Diagnosing Common Deployment Failures

| Symptom | Possible Cause | Inspection Steps |
|---|---|---|
| Deploy succeeds yet Functions are missing | Wrong package root, missing `function.json`, host load/binding failure | Package output, host logs, Function list |
| Java `UnsupportedClassVersionError` | Compiler target newer than Azure Java runtime | JDK, Maven compiler release, app stack |
| HTTP Function returns 401 | Missing/wrong Function key, `authLevel`, or access control | Endpoint/function key scope, identity |
| HTTP Function returns 500 | Unhandled Java exception, missing settings, dependency failure | Application Insights, worker logs, exceptions |
| `TimerTrigger` does not run | Function disabled, schedule/timezone/host state, Storage permissions | Config, host logs, schedule monitor |
| `QueueTrigger` does not run | Wrong connection/queue, missing permissions, disabled trigger, network | App settings, data RBAC, logs |
| Staging processes production events | Wrong source/sticky settings, triggers left enabled | Queue identity/resource IDs, slot diff |
| Maven deploy fails | Wrong plugin target, version, or Azure permissions | POM, Maven output, plan/OS support |
| ZIP Deploy fails on Flex | Incompatible deployment method | Use One Deploy / Flex-supported tooling |
| Key Vault reference unresolved | Identity lacks permissions, wrong secret URI/DNS/firewall | Reference status, Key Vault IAM, networking |
| Swap breaks production | Non-sticky settings, runtime/config drift | Slot config, logs, smoke tests, rollback |
| Queue backlog grows post-release | Slow/failing consumer, retries, altered batch/concurrency | Invocation duration, retries/dead-letter |
| Code rolled back yet data errors persist | Schema/database/side effects already mutated | Contract/migration/reconciliation plan |
| Host fails to load extension | Incompatible binding version/host runtime | `host.json`, dependency versions, trigger logs |

**Change only one layer at a time** based on evidence. Changing Functions host, Java worker, Storage connection, and artifact simultaneously hides the root cause.

## 25. Scenario A: Staging Reads the Production Queue by Mistake

A team deploys **`ProcessOrders`** to a staging slot. Because the slot copied production settings, the staging `QueueTrigger` connects to **`orders-production`**, and an unapproved version consumes live messages.

### Analysis

This is an **environment isolation** failure, not a Queue Storage bug. Depending on broker and consumer semantics, it may have caused message stealing, duplicate side effects, or partial processing.

### Runbook

1. Stop or disable the **staging listener** in a controlled manner; avoid touching production accidentally.
2. Record timeline, affected message IDs, queue depth, dead-letter state, and audit logs.
3. Compare **resource IDs**, app/slot settings, and managed identity scopes.
4. Configure dedicated staging queues/test sources and enforce sticky settings per policy.
5. Set **`AzureWebJobs.ProcessOrders.Disabled=true`** on staging when triggers should stay off.
6. Test with synthetic messages and confirm staging never touches production.
7. Assess data compensation, replay, or deduplication per business logic.
8. Add CI checks blocking staging from referencing production queues or Key Vaults.

**Never delete production queues or reset checkpoints recklessly as a "quick fix."** Protect unprocessed messages and audit records.

## 26. Scenario B: Java Upgrade Breaks Function Startup

CI upgrades builds from Java 17 to Java 21 while the Azure Function App still runs Java 17. Maven packaging and publishing succeed, then logs show:

~~~text
java.lang.UnsupportedClassVersionError:
... compiled by a more recent version of the Java Runtime
~~~

### Resolution Steps

1. Record artifact checksum, Git SHA, and Azure Java version.
2. Inspect JDK, target bytecode, and dependencies in CI.
3. Verify whether Java 21 is supported on your **current plan, OS, region, and runtime**.
4. If not, **redeploy the verified Java 17 artifact** or rebuild targeting Java 17 (with a new checksum).
5. Run smoke/integration tests and verify host/worker logs.
6. Plan Java runtime upgrades in staging first before touching production.

**Never swap `FUNCTIONS_EXTENSION_VERSION` away from `~4`** trying to fix `UnsupportedClassVersionError`; that is a completely different version layer.

## 27. Scenario C: Rolling Back After an Event Schema Change

Function **v2** starts reading `OrderCreatedV2` and running database migrations. After 20 minutes, errors climb and the team wants to roll back to v1.

Risks:

- New messages contain fields/types v1 cannot parse.
- Some messages were already consumed and persisted by v2.
- The database schema may no longer fit v1 code.
- Durable instances hold history created under v2.

### Runbook

1. If needed, pause producers/consumers without dropping events, capturing snapshots, timelines, and backlogs.
2. Verify the compatibility matrix across **v1 code ↔ v2 messages ↔ current DB**.
3. If v1 cannot process safely, prefer a compatibility hotfix or route messages appropriately rather than rolling back blindly.
4. When safe to revert, deploy the known-good v1 artifact and verify triggers and permissions.
5. Plan controlled backfills, compensation, or data restoration.
6. Monitor dead-letter queues, retries, queue age, and business reconciliation.

**Rolling back code does not undo sent emails, processed orders, or committed transactions.** Plan backward-compatible schema evolution and idempotency before releasing.

## 28. Lab: Designing a Three-Environment Pipeline

### Context

The **`OrdersFunctions`** system includes:

- **`ReleaseInfo`**: HTTP Function reading `APP_ENV` and `APP_VERSION`.
- **`ProcessOrders`**: `QueueTrigger` receiving `order-created` events.
- **`CleanupExpiredOrders`**: `TimerTrigger` purging expired records per policy.

Requirements: dev/staging must never touch production data, production updates only after staging verification, with a rollback plan and observable costs.

### Part A: Build the Resource Matrix

| Component | Dev | Staging | Production |
|---|---|---|---|
| Function App | `fa-orders-dev` | `fa-orders-stg` | `fa-orders-prod` |
| Queue source | `orders-dev` | `orders-stg` | `orders-prod` |
| Timer | Dev schedule/disabled | Disabled or isolated | Approved schedule |
| Host Storage | Dev Storage | Staging Storage | Production Storage |
| Database | Test | Safe test | Production |
| Identity | MI-dev | MI-stg | MI-prod |
| Key Vault | KV-dev | KV-stg | KV-prod |
| Telemetry | Dev workspace/app | Staging | Production alerts |
| Release gate | CI | QA approval | Protected approval |

This represents the **separate Function Apps** approach. If using slots, redesign sticky settings, identities, data sources, and trigger disablement, and confirm plan support.

### Part B: Inspect a Function App via CLI (Read-Only)

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
APP="<LAB_FUNCTION_APP>"

az functionapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,kind:kind}" \
  --output json

az functionapp function list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name}" \
  --output table

az functionapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

Run only against authorized apps. Never drop the `--query` filter when listing app settings, as unfiltered output can expose secrets.

### Part C: Build Java Locally

1. Scaffold a Java Functions Maven project from an official template and add **`ReleaseInfo`** from Section 5.
2. Create `local.settings.json` pointing to Azurite/sandbox Storage without committing secrets.
3. Run **`mvn -B clean test`**, **`mvn -B package`**, and **`mvn azure-functions:run`**.
4. Call **`/api/release-info`** on localhost and confirm environment/version.
5. Record Git SHA, JDK, Maven/plugin versions, and artifact checksum.

### Part D: Sandbox Deployment (If Permitted)

1. Verify **`appName`, `resourceGroup`, `runtime`, `hosting plan`** in Maven/pipeline config.
2. Use a deployment identity scoped strictly to the staging/lab app.
3. Configure `APP_ENV=staging`, `APP_VERSION=1.4.2`, and the staging `QueueTrigger` source.
4. Deploy using a method **supported by the hosting plan**—do not assume ZIP Deploy.
5. Verify Function discovery, authenticated HTTP invocation, and host/worker logs.
6. Run event tests on the **staging queue**: normal, duplicate, invalid payload, and retry cases.
7. Verify telemetry/alerts and draft a written production approval checklist.
8. Never deploy to production or alter live triggers for a lab exercise.

### Evidence Table

| Evidence | What to Record |
|---|---|
| Source/release | Commit, semantic version, artifact checksum |
| Platform | Function App, plan, region, OS, host/Java versions |
| Config | `APP_ENV`, `APP_VERSION`, connection setting names without exposing secrets |
| Isolation | Staging queue, DB, host storage, and identity genuinely separate from prod |
| Function discovery | `ReleaseInfo`, `ProcessOrders`, `CleanupExpiredOrders` matching config |
| Smoke test | HTTP returns expected version; staging events processed |
| Observability | Invocation logs, failures, duration, retries, backlog |
| Rollback | Prior artifact, schema compatibility, event handling plan |
| Security | Managed identity, Key Vault, least-privilege deploy |
| Cost | Created resources, cleanup status, and owner |

If you hold read-only access, completing **Parts A and B** plus the rollout/rollback design is sufficient; you do not need production privileges to demonstrate mastery.

## 29. Cost and Resource Lifecycle

Good environment isolation boosts safety but carries costs:

| Component | Potential Cost Driver |
|---|---|
| Function App execution/compute | Plan model, executions/duration, memory/concurrency, instances |
| Premium/Dedicated plan | Provisioned capacity, even during low traffic |
| Slots/staging | Compute/scale resources and supporting services |
| Azure Storage | Host state, queue events, packages, logs, and transactions |
| Service Bus/Event Hubs | Messages, throughput, retention/tier |
| Application Insights/Log Analytics | Telemetry ingestion, retention, alerts |
| Key Vault/private networking | Secret operations, private endpoints, DNS/NAT |
| CI/CD | Runners, artifact storage, scanning, registries |

Apply **`environment`, `owner`, `application`, `costCenter`** tags per policy and track via Cost Management. **Budget alerts do not automatically stop charges.** A staging Function running a Timer every minute or logging excessively can burn budget even with zero real users.

### Safe Lab Cleanup

- Delete only Function Apps, queues, storage, or resource groups **created and exclusively owned by your lab**.
- Never delete Storage holding host state for other apps or queues with pending real messages.
- On shared apps, restore pre-lab settings with a documented change record.
- Verify resources in ARM and check delayed Cost Management billing updates.

## 30. Production Function Release Checklist

- [ ] Hosting plan, OS, runtime, scaling, and deployment method are compatible.
- [ ] Source SHA, artifact checksum, and release manifest are recorded.
- [ ] Functions host major, language worker, Java target, and binding extensions are tested.
- [ ] Dev/staging/prod have separate data sources, host storage, identities, and IAM—or verified slot isolation.
- [ ] Staging Timer/Queue/Event/Durable triggers cannot touch production data unintentionally.
- [ ] App settings and Key Vault references are scoped cleanly; zero secrets in source or pipeline logs.
- [ ] CI builds once, runs tests/scans/approvals, and promotes the exact same artifact.
- [ ] IaC reviewed with no unapproved drift or accidental overwrite of emergency settings.
- [ ] Deployment slots/swaps used only where supported, with sticky settings and side effects verified.
- [ ] HTTP/event schemas and DB migrations preserve compatibility.
- [ ] Retries, poison/dead-letter handling, idempotency, and backlog runbooks are ready.
- [ ] Azure Monitor, Application Insights, alerts, and release metadata provide full traceability.
- [ ] Rollback plans cover both artifacts **and** data/event side effects.
- [ ] Post-deploy checks confirm Function discovery, trigger health, version, invocations, and SLOs.
- [ ] Budgeted costs across environments, plans, storage, and telemetry.

## 31. Self-Check Questions

1. How does a Function differ from a Function App, and why do deployments usually target the app level?
2. Why shouldn't you run the same ZIP Deploy command across every Functions hosting plan?
3. When should you use separate Function Apps instead of deployment slots?
4. Does `FUNCTIONS_EXTENSION_VERSION=~4` mean Java Function release 4?
5. Does `FUNCTIONS_WORKER_RUNTIME=java` automatically select Java 17 or 21?
6. Does `host.json` `version=2.0` mean Functions host runtime 2?
7. Why is uploading a single JAR often insufficient for the Azure host to discover Functions?
8. What can go wrong if a staging `QueueTrigger` reads the production queue?
9. What do sticky slot settings protect during a swap?
10. Why does sharing `AzureWebJobsStorage` require checking host identity and timer/lease state?
11. Why is `APP_ENV=staging` not a security boundary?
12. How do managed identity and deployment identity differ?
13. Why use Key Vault references instead of plaintext secrets in CI/CD?
14. How does "build once, deploy many" differ from two jobs separately building the same Git commit?
15. When does `UnsupportedClassVersionError` occur?
16. Why must Durable Functions account for in-flight orchestration instances during code upgrades?
17. Does rolling back code undo consumed messages and DB migrations?
18. After the CLI reports deployment succeeded, which telemetry and triggers must you still verify?
19. How does a canary rollout for an HTTP Function differ from an event-driven Function?
20. Why are budget alerts alone insufficient to cap staging costs?

## 32. References

- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview) — Functions concepts and applications.
- [Azure Functions hosting options](https://learn.microsoft.com/azure/azure-functions/functions-scale) — plans, scaling, and limits.
- [Azure Functions deployment technologies](https://learn.microsoft.com/azure/azure-functions/functions-deployment-technologies) — deployment methods.
- [Azure Functions runtime versions](https://learn.microsoft.com/azure/azure-functions/functions-versions) — host and language runtimes.
- [Java developer guide for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java) — Java annotations, Maven, and packaging.
- [Create a Java Function](https://learn.microsoft.com/azure/azure-functions/create-first-function-cli-java) — initialization and deployment workflow.
- [Azure Functions deployment slots](https://learn.microsoft.com/azure/azure-functions/functions-deployment-slots) — slots, swaps, and settings.
- [Azure Functions app settings reference](https://learn.microsoft.com/azure/azure-functions/functions-app-settings) — runtime and connection settings.
- [Disable functions](https://learn.microsoft.com/azure/azure-functions/disable-function) — disabling individual Functions.
- [Azure Functions best practices](https://learn.microsoft.com/azure/azure-functions/functions-best-practices) — reliability and operations.
- [Durable Functions versioning](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-versioning) — long-running workflows.
- [Key Vault references](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — secret references and managed identity.
- [Azure Functions monitoring](https://learn.microsoft.com/azure/azure-functions/functions-monitoring) — telemetry and alerts.
- [Azure CLI `az functionapp`](https://learn.microsoft.com/cli/azure/functionapp) — reading config, deploying, and slots.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating compute, storage, and monitoring costs.

**Conclusion:** Safe Azure Functions deployment goes far beyond publishing source code. You must govern **versioned code and artifacts, compatible host and language runtimes, isolated per-environment configuration and data, trigger safety against cross-environment events, least-privilege permissions, testing, and post-deploy observability**. HTTP Functions can leverage slots where plans allow; event-driven Functions demand extra attention to idempotency, event sources, and in-flight state. A release is complete only when verified by business signals and backed by a genuinely safe rollback plan.
