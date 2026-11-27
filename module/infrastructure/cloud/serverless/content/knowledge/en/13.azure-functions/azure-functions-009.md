# Releasing functions and using deployment slots when supported

Azure Functions supports deploying code in several ways: ZIP packages, package deployment, container images, or CI/CD pipelines. A deployment can restart the host and interrupt in-flight invocations. On hosting plans that support deployment slots, teams can deploy a new version to a staging environment, verify the application, and promote that slot to production via a swap operation.

Deployment slots are useful for validating new releases, warming up the application before receiving traffic, and rolling back quickly to the previous version. However, a slot is not a completely isolated production environment: slots belong to the same Function App and App Service plan, sharing certain resources and limits; which settings travel with code and which stay with the slot must be clearly defined. Nor does a swap guarantee every in-flight invocation will remain uninterrupted.

Support depends on the hosting plan. Consumption, Premium, and Dedicated support slots with varying slot counts; Flex Consumption currently does not support deployment slots; Azure Functions running on Azure Container Apps uses revisions. Therefore, before designing a release pipeline, determine the hosting plan, operating system, packaging method, and availability requirements of your application.

## 1. Release lifecycle of a Function App

A solid release starts from a built and tested artifact, deploys to a verification environment, validates behavior, and only then promotes to production. With slots, a common flow is:

~~~mermaid
flowchart TD
    A["Commit source code"] --> B["Build and test Java project"]
    B --> C["Create deployment artifact"]
    C --> D["Deploy to staging slot"]
    D --> E["Verify configuration and warm-up"]
    E --> F["Smoke test / integration test"]
    F --> G{"Meets release criteria?"}
    G -->|"No"| H["Fix issue or deploy new artifact"]
    H --> D
    G -->|"Yes"| I["Swap staging with production"]
    I --> J["Verify production"]
    J --> K{"Stable?"}
    K -->|"Yes"| L["Keep release"]
    K -->|"No"| M["Swap rollback"]
~~~

These steps can be automated with Azure Pipelines, GitHub Actions, or other release tools. The key principle is that the exact same tested artifact must go to staging and then be promoted to production. Avoid rebuilding a separate package at the production step, as the two environments could receive different code.

A Function App can hold multiple functions. Consequently, a deployment typically replaces the package for the entire Function App rather than an individual function. If functions have different release schedules, dependencies, or security boundaries, consider splitting them into separate Function Apps.

## 2. Which hosting plans support deployment slots?

Per current Azure Functions documentation, slot counts include the production slot:

| Hosting option | Slot count (including production) | Corresponding release method |
|---|---:|---|
| Consumption plan | 2: production and one staging | Deployment slots and swaps are supported |
| Flex Consumption plan | Not supported | Uses site update strategy; can configure rolling updates |
| Premium plan | 3 | Deployment slots and swaps |
| Dedicated (App Service) plan | 1–20, depending on tier | Deployment slots and swaps |
| Azure Container Apps | Slots not applicable | Uses revisions to manage versions and traffic |

Actual slot counts also depend on tier and subscription service limits. Check your plan's quota before creating new slots.

Three points to keep in mind:

- **Flex Consumption:** has no deployment slots. To control releases and reduce downtime, use rolling updates via Flex Consumption's site update strategy alongside a test pipeline.
- **Azure Container Apps:** Function Apps release via container images and revisions. Revisions can receive traffic according to Container Apps strategies; App Service slot swap commands are not used.
- **Consumption, Premium, and Dedicated:** can deploy to a separate slot and swap with production. Slot counts and scaling capabilities depend on the hosting plan.

Do not pick a hosting plan solely to get slots. Also evaluate execution duration, scaling, networking, memory, concurrency, cost, and workload operability.

## 3. What is a deployment slot?

A deployment slot is a separate Function App instance with its own hostname. A Function App always has a production slot and can have one or more additional slots such as staging, test, or canary if supported by the plan.

Example hostnames:

~~~text
orders-api.azurewebsites.net
orders-api-staging.azurewebsites.net
~~~

Each slot can receive deployments and be tested through its own endpoint. When swapping staging with production, Azure changes which slot is treated as production and switches routing per the swap workflow.

Slots help:

- Validate a new version on the staging endpoint before shifting traffic.
- Start the application and warm up components before release.
- Verify environment-specific configuration.
- Retain the prior production version in the remaining slot for fast rollback.
- Perform controlled releases from a pipeline.

Slots still belong to the same Function App and App Service plan. Slots share plan capacity and are affected by shared configuration, quotas, networking, and underlying platform resources. A slot is not equivalent to a separate subscription or an independent security boundary. If staging requires strict data or access isolation, design appropriate identities, networks, storage, and resource permissions.

## 4. Creating and managing slots

Slots can be created via the Azure Portal or Azure CLI. Example creating a slot named staging:

~~~bash
az functionapp deployment slot create \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging
~~~

After creation, inspect slots and hostnames:

~~~bash
az functionapp deployment slot list \
  --name orders-api \
  --resource-group rg-orders-prod \
  --output table
~~~

A new slot must be configured before receiving traffic or processing events. Never assume every setting is copied or isolated exactly as the team expects. When creating a slot, Azure may initialize certain settings from production; review the slot's entire configuration before deploying.

Common management operations:

- Create a slot for staging or testing.
- Update app settings and connection strings.
- Deploy a package to the slot.
- Test the slot via its dedicated hostname.
- Swap the slot with production.
- Swap back to roll back.
- Delete the slot when no longer needed.

Use slot names that reflect purpose and environment. Avoid creating many temporary slots without a cleanup process, as they still consume resources and add operational complexity.

## 5. Packaging a Java application for Azure Functions

Azure Functions Java projects are typically built with Maven. The Azure Functions plugin generates a deployment-ready directory structure in the target folder, typically:

~~~text
target/
  azure-functions/
    orders-api/
      host.json
      orders-api.jar
      FunctionName/
        function.json
      lib/
        dependency-1.jar
        dependency-2.jar
~~~

The Function App directory must be packaged so that host.json sits at the root of the package once extracted. If the ZIP includes an extra parent directory, the runtime may fail to locate host.json or function metadata.

A common build command:

~~~bash
mvn -B clean verify
~~~

With the Azure Functions Maven plugin, the standard deploy command looks like:

~~~bash
mvn azure-functions:deploy
~~~

The Maven deploy command works well for deploying directly to a Function App per pom.xml settings. When a pipeline needs to release through a slot, confirm the deployment method and plugin version's slot support in your project; you can use Azure CLI ZIP deployment or a CI/CD task with an explicit slot parameter. Do not assume all Maven plugin versions share identical slot-selection capabilities.

When using ZIP deployment, create the archive from the contents of the output folder so host.json sits right at the root. Example in PowerShell:

~~~powershell
$functionOutput = "target/azure-functions/orders-api"
Compress-Archive -Path "$functionOutput/*" -DestinationPath "orders-api.zip" -Force
~~~

Before uploading, inspect the ZIP contents. The package must contain host.json, the application JAR, function metadata, and runtime dependencies. Do not package the entire source tree if that structure is not the built deployment output.

## 6. Choosing deployment technology by hosting plan

Deployment methods vary by hosting plan and operating system. Primary options:

| Hosting plan | Common deployment technology | Notes |
|---|---|---|
| Flex Consumption | Managed package deployment | Package deployment is the supported code deployment method; app runs directly from package |
| Consumption | ZIP deployment; some legacy Linux cases use external package URL | Check OS and current plan guidance |
| Premium | ZIP deployment or container image on Linux | ZIP deployment is the common choice for code |
| Dedicated | ZIP deployment or container image on Linux | Can use slots if supported by tier |
| Azure Container Apps | Container image | Uses revisions instead of slots |

With ZIP deployment on Consumption, Premium, and Dedicated, you can configure the app to run directly from the package via setting WEBSITE_RUN_FROM_PACKAGE=1 on supported plans/OSes. This mounts the package as a read-only wwwroot directory, avoiding certain file-locking issues and clarifying what code is running.

Flex Consumption uses managed package deployment and runs from package by default; do not add WEBSITE_RUN_FROM_PACKAGE from traditional ZIP deployment guides. Flex also does not support slots, so use the release strategy tailored for this plan.

Azure Container Apps deploys a new image as a revision. Use Container Apps' traffic splitting and revision management mechanisms for canary releases or rollbacks.

## 7. Deploying a Java package to a staging slot

When slots are supported, Azure CLI ZIP deployment can push the artifact to staging. Example:

~~~bash
az functionapp deployment source config-zip \
  --resource-group rg-orders-prod \
  --name orders-api \
  --slot staging \
  --src orders-api.zip
~~~

This command deploys the ZIP into the staging slot. The Azure CLI account must be authenticated and authorized to deploy to the Function App. The package must match the Function App's runtime, operating system, and architecture.

After deploying:

1. Verify the deployment command finished successfully.
2. Verify the staging Function App starts up and the host indexes the expected functions.
3. Verify app settings, connection strings, and managed identity.
4. Call the staging HTTP endpoint if HTTP triggers exist.
5. Run smoke tests using test data.
6. Check logs and dependency connectivity.
7. Only swap once release criteria are satisfied.

For GitHub Actions, the Azure Functions deploy action supports a slot-name parameter on hosting plans with slots. For Azure Pipelines, the AzureFunctionApp task can specify a deployment slot. Flex Consumption does not support slot-name; pipelines must use Flex's package deployment and site update strategy.

## 8. Configuring slot-specific settings and sticky settings

One of the most common mistakes during a swap is confusing which settings travel with code and which settings must stay with the environment.

A **Sticky setting** (also called a deployment slot setting) is a setting that stays pinned to its slot during a swap. For example, staging needs a test database, storage account, or queue; production needs production resources. These settings must be marked as slot-specific so values do not get swapped across environments.

Settings commonly requiring review:

- Database connection strings and endpoints.
- Environment-specific storage accounts or containers.
- Staging queues, topics, event hubs, or subscriptions.
- Environment-specific secret references or dependency configurations.
- Staging-only feature flags.
- Flags to disable triggers in staging.
- Settings indicating environment name or telemetry destination.

Example configuring app settings for staging:

~~~bash
az functionapp config appsettings set \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging \
  --slot-settings \
    "APP_ENV=staging" \
    "ORDERS_TABLE=orders-staging" \
    "AzureWebJobs.QueueTrigger.Disabled=true"
~~~

Depending on the CLI version, you may need to pass the settings list using appropriate shell syntax. Verify the result after updating and ensure settings are marked as slot-specific.

If a setting must exist in both staging and production, keep the same key name in both slots with environment-appropriate values. This prevents code from failing due to missing settings after a swap. Never put secrets directly into pipeline files or source control; use Key Vault references or a suitable secret management mechanism.

Not every configuration item can be marked sticky. Some platform properties—such as hostnames, publishing endpoints, private certificates, IP restrictions, diagnostic settings, CORS, private endpoints, or scale settings—remain pinned per slot per App Service rules. Virtual network integration and certain other network configs also have specific semantics. Review the current swap/non-swap settings list before designing.

## 9. Preventing staging from processing production events

For HTTP triggers, staging has its own hostname and can be invoked directly during testing. For queue triggers, timer triggers, or event triggers, staging can start listeners and consume events if configured to point at the same production source.

If both staging and production read from the same queue or subscription, the same event could be processed by two slots or drained by the unintended slot. This can cause duplicate side effects, test data polluting production, or loss of processing order control.

Ways to mitigate this risk:

- Use dedicated queues, topics, storage, or databases for staging.
- Mark event source connection settings as sticky.
- Disable functions that should not run in staging via slot-specific settings.
- Only enable triggers in staging when intentionally testing.
- Enforce idempotency and conditional updates in consumers.
- Verify each slot's managed identity permissions.
- Test swapping with event sources and bindings prior to production.

Azure Functions supports a per-function setting to disable a function, for example:

~~~text
AzureWebJobs.QueueTrigger.Disabled=true
~~~

Create this setting as a slot-specific setting on staging if you want the trigger to stay disabled in staging after a swap. When staging swaps into production, sticky values stay on their slot; therefore, prepare the right values for both slots and verify trigger status after release.

For Timer Triggers, take extra care so two hosts do not unexpectedly execute the same periodic job concurrently. Use the platform's host lock mechanism properly, keep configurations isolated per slot, and design tasks to be idempotent.

## 10. Warm-up and readiness checks before swapping

Slots allow deploying a new version before shifting traffic. However, a completed package upload does not prove the app is ready. A Java function may need to start the JVM, load classes, initialize dependencies, read configuration, and establish connections.

Prepare an appropriate health endpoint or check mechanism. For HTTP functions, a readiness endpoint can verify:

- The Function host has started.
- Required configuration has been read.
- Critical dependencies are reachable.
- The database schema is compatible.
- Secret references or managed identities are working.
- The application is not in maintenance mode.

App Service supports configuring a warm-up path for slot swaps using app settings such as:

~~~text
WEBSITE_SWAP_WARMUP_PING_PATH=/api/health
WEBSITE_SWAP_WARMUP_PING_STATUSES=200,202
~~~

The path must return an accepted status code. If the endpoint requires a function key or authentication that the warm-up request cannot provide, warm-up may fail. Design the health endpoint safely—exposing no sensitive details and returning only necessary readiness status.

Warm-up reduces the risk of routing traffic to an unready instance, but does not replace smoke tests and does not turn slot swaps into a zero-downtime guarantee.

## 11. Swapping staging with production

Once staging is verified, run a swap to move the new version into production:

~~~bash
az functionapp deployment slot swap \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging \
  --target-slot production
~~~

During a swap, Azure applies settings per slot rules, prepares and starts the source slot instances with target settings, and switches routing once readiness conditions are met. After the swap, staging typically holds the version that was previously running in production; this is useful for rollbacks.

Before starting, verify:

- Production is the target slot.
- App settings and connection strings are properly categorized as sticky.
- Event sources and bindings point to the right resources.
- Unwanted functions in staging are disabled.
- Database migrations are compatible with both old and new versions.
- Warm-up endpoints return valid status codes.
- Monitoring and rollback plans are ready.

Swaps can affect in-flight invocations. Azure Functions documentation warns that slot swaps do not guarantee zero downtime; executing functions may be terminated and scaled apps may experience availability dips during the transition. Therefore, functions must be stateless, idempotent, and resilient to invocation retries.

## 12. Rollback after release

If the new version causes errors after a swap, swap staging back into production to restore the previous version:

~~~bash
az functionapp deployment slot swap \
  --name orders-api \
  --resource-group rg-orders-prod \
  --slot staging \
  --target-slot production
~~~

The rollback command uses the same staging-to-production swap direction because after the first swap, staging holds the older version. Before rolling back, confirm which slot currently contains the version to restore.

Rolling back code does not automatically roll back data. If a release ran an incompatible database migration, reverting code to the previous version can make errors worse. Use the expand/contract strategy:

1. Add new schemas or fields in a backward-compatible way.
2. Deploy code capable of reading both old and new formats.
3. Shift traffic and verify.
4. Migrate data or deprecate the old schema.
5. Remove old structures only after no running version depends on them.

Keep released artifacts in your CI/CD artifact store. Slots are not long-term release history storage; a subsequent deployment overwrites slot contents. Versioned artifacts with checksums and build metadata let you reproduce the exact build needed for rollback.

## 13. Limitations and risks of slot swaps

Slots enable controlled releases, but carry several limitations to factor in:

- **No zero-downtime guarantee:** in-flight invocations can be terminated during a swap.
- **Shared capacity:** slots share App Service plan capacity; heavy load testing on staging can impact production.
- **Unintended trigger execution:** staging can receive events if source settings are not isolated or disabled.
- **Wrong sticky settings:** connection strings or queues can swap across environments.
- **Incompatible database schemas:** code rollback does not revert schema changes.
- **Secret and key behavior:** certain secret storage configs behave specially during swaps. For example, swaps can reset function keys if the app uses AzureWebJobsSecretStorageType=files.
- **Network-secured storage:** slot swaps can fail in certain configurations using protected storage accounts as AzureWebJobsStorage; check relevant documentation and diagnostics.
- **Function App name:** Microsoft recommends keeping Function App names under 32 characters to avoid host ID collisions in certain scenarios.
- **Non-swapped settings:** managed identities, private endpoints, IP restrictions, and certain network/diagnostic settings follow dedicated rules.

Do not treat a staging slot as a completely risk-free replica of production. Audit access permissions, data, triggers, networking, and configuration before testing.

## 14. Automating releases with CI/CD

A release pipeline should have clear stages:

1. Check out source and identify the commit.
2. Build Java with Maven.
3. Run appropriate unit and integration tests.
4. Package and store a versioned artifact.
5. Deploy the artifact to the staging slot.
6. Update slot-specific settings if managed by the pipeline.
7. Run smoke tests and readiness checks.
8. Require approval if dictated by release policy.
9. Swap staging into production.
10. Monitor health, errors, latency, and business metrics.
11. Roll back if post-release criteria fail.

Condensed Azure Pipelines example for slot deployment and swap:

~~~yaml
steps:
  - task: AzureFunctionApp@2
    displayName: Deploy Java Function to staging
    inputs:
      azureSubscription: $(AZURE_SERVICE_CONNECTION)
      appType: functionAppLinux
      appName: orders-api
      package: $(Pipeline.Workspace)/drop/orders-api.zip
      deployToSlotOrASE: true
      resourceGroupName: rg-orders-prod
      slotName: staging

  - script: |
      echo "Run smoke tests against the staging hostname here"
    displayName: Validate staging

  - task: AzureAppServiceManage@0
    displayName: Swap staging into production
    inputs:
      azureSubscription: $(AZURE_SERVICE_CONNECTION)
      WebAppName: orders-api
      ResourceGroupName: rg-orders-prod
      SourceSlot: staging
      SwapWithProduction: true
~~~

This is a pipeline skeleton; configure the service connection, Azure Resource Manager permissions, package artifact, and test commands for your repository. The AzureFunctionApp task supports slots on hosting plans with deployment slots. Do not use slot tasks for Flex Consumption.

With GitHub Actions, the Azure Functions deploy action includes a slot-name parameter for plans supporting slots. Prefer workload identity federation/OIDC with azure/login over storing long-lived publish profiles when supported by the environment. Never commit credentials into workflows.

## 15. IaC configuration for deployment slots

Slots should be managed alongside the Function App via Bicep or ARM templates. Slot resources use resource type Microsoft.Web/sites/slots. Condensed example:

~~~bicep
resource functionApp 'Microsoft.Web/sites@2022-09-01' existing = {
  name: 'orders-api'
}

resource stagingSlot 'Microsoft.Web/sites/slots@2022-09-01' = {
  parent: functionApp
  name: 'staging'
  location: resourceGroup().location
  properties: {
    serverFarmId: functionApp.properties.serverFarmId
  }
}
~~~

This example only illustrates resource relationships. Real templates must specify runtime configuration, app settings, identity, networking, and dependencies per supported API version. Do not manually set WEBSITE_CONTENTSHARE in slot definitions if platform guidance requires slot creation to auto-generate that setting.

For settings that must be sticky, ARM/Bicep can express slot settings using the slotSetting property inside the app settings structure per schema. Manage both staging and production values together so code always sees required keys.

IaC prevents manual configuration drift across environments. However, review deployment diffs carefully because slot config changes can restart the app or alter trigger behavior.

## 16. Release strategies without slots

When using Flex Consumption, there are no deployment slots. Control releases using approaches suited to the plan:

- Use Flex Consumption's managed package deployment.
- Build immutable artifacts and store them in the pipeline.
- Use rolling updates via Flex Consumption's site update strategy.
- Run pre-deploy tests and post-deploy verification.
- Design functions to be stateless, idempotent, and retry-tolerant.
- Keep database schemas backward-compatible to release new versions safely.
- Maintain a plan to restore the prior package per Flex Consumption guidance.

With Azure Container Apps, use revisions. You can deploy a new revision, validate it, and shift traffic between revisions per Container Apps configuration. This is a distinct release model; do not use App Service slot swaps.

If a workload requires canary traffic splitting, compare revision-based rollouts, slot swaps, and API Management/Front Door routing against your hosting plan. Choose a strategy based on actual service support rather than just the word "staging".

## 17. Observing releases and deciding when to roll back

A deployment can succeed technically while failing functionally. Checking deploy status alone is insufficient. Observe before, during, and after the swap.

Signals to watch:

- Deployment status and build/deploy task logs.
- Function host startup and function indexing errors.
- Invocation count, error count, duration, and timeouts.
- HTTP 4xx/5xx rates and p50/p95/p99 latency.
- Queue age, retries, poison messages, or dead-letter counts.
- Database connection failures and dependency latency.
- Application Insights traces/exceptions.
- Business metrics such as orders created successfully, completed jobs, and blocked duplicate events.

Define rollback criteria prior to release—for example, error rate exceeding threshold, health check failures, rapidly growing queue backlogs, or dropping business success rates. Rollback should be a logged pipeline action with approvals per organizational policy.

Include deployment ID, commit SHA, package version, and slot name in telemetry to identify which release ran each invocation. Avoid logging secrets, tokens, or sensitive payloads solely for diagnostics.

## 18. Azure Functions production release checklist

Before deploying, verify:

1. Does the hosting plan support slots? If not, what is the alternative release strategy?
2. Are enough slots available under the tier and quota?
3. Are the Java version, Functions runtime, and package compatible?
4. Does the ZIP have host.json at its root and include all JARs, function metadata, and dependencies?
5. Is the artifact built once and retained for rollback?
6. Does staging point to staging's database, storage, queues, and secrets?
7. Are sticky app settings and connection strings marked properly?
8. Are unwanted triggers in staging disabled?
9. Are managed identities and permissions verified for each slot?
10. Does the health/warm-up endpoint return a valid status?
11. Do smoke tests verify both HTTP and critical dependencies?
12. Are database migrations compatible with both old and new code?
13. Can in-flight invocations be terminated during a swap, and are handlers resilient to that?
14. Are there clear criteria for swapping and rolling back?
15. Does the pipeline monitor error rates, latency, queue age, and business metrics post-deploy?
16. For Flex Consumption, are rolling updates configured instead of slots?
17. For Azure Container Apps, are revisions and traffic configurations tested?

## References

- [Azure Functions deployment slots](https://learn.microsoft.com/azure/azure-functions/functions-deployment-slots)
- [Deployment technologies in Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-deployment-technologies)
- [Package-based deployment for Azure Functions](https://learn.microsoft.com/azure/azure-functions/deployment-zip-push)
- [Continuous deployment for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-continuous-deployment)
- [Java developer reference for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java)
- [Set up staging environments in Azure App Service](https://learn.microsoft.com/azure/app-service/deploy-staging-slots)

## Conclusion

Releasing Azure Functions requires matching deployment technology to the hosting plan, packaging with the right directory structure, testing artifacts, and automating releases with CI/CD. On Consumption, Premium, and Dedicated plans, deployment slots allow deploying a new version to staging, validating, warming up, and swapping into production. Sticky settings keep connections, storage, queues, and environment configs bound to the right slot; staging triggers must be controlled to prevent unintended processing of production events.

Slots do not guarantee zero downtime and do not replace stateless, idempotent function design or backward-compatible database migrations. Flex Consumption uses package deployment and rolling updates instead of slots; Azure Container Apps uses revisions. When pipelines retain immutable artifacts, verify readiness, monitor telemetry, and maintain a rollback plan, teams can release Java Function Apps with control and recover quickly if a new version misbehaves.
