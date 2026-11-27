# Environment Configuration, Access Permissions, and Azure Deployment

## 1. Objective: Bringing Spring Cloud Function to Azure Safely

**Spring Cloud Function (SCF)** enables building reusable business logic with `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. `FunctionCatalog` registers and looks up functions, supports composition, and adapters allow the same logic to be invoked via HTTP, queues, events, or other serverless runtimes.

When bringing an application to **Azure Functions**, code and packaging are only part of releasing. The Function App also requires environment configuration, access permissions to external services, caller authentication, and a deployment strategy suited to the hosting plan.

This lesson follows a practical scenario: an order-processing Function App that reads a priority threshold from configuration, accepts HTTP requests, writes data or sends messages to Azure Storage/Service Bus, and connects to Key Vault when secrets are needed.

After this lesson, you will be able to:

1. Separate configuration across source code, Spring Boot properties, Azure Host settings, local settings, and Azure App Settings.
2. Use Spring profiles and `@ConfigurationProperties` to configure business logic per environment.
3. Distinguish Function App deployment permissions from application runtime permissions.
4. Enable system-assigned or user-assigned managed identities.
5. Grant Azure RBAC roles at the right scope with the right data-plane roles.
6. Use identity-based connections for `AzureWebJobsStorage` and bindings.
7. Use Key Vault references or the Azure SDK when services still require secrets.
8. Distinguish inbound HTTP authentication from outbound authentication to Azure resources.
9. Choose deployment methods per hosting plan and design CI/CD, smoke tests, and rollbacks.

**Overarching principle:** every environment needs its own configuration and identity; the runtime identity gets only least-privilege permissions to do its job; the deployment identity gets only the permissions needed to release code and configuration.

## 2. Map of Configuration Layers

An Azure Function App typically draws configuration from several sources, each with its own scope and evaluation time.

| Source | Read By | Scope | Example |
| --- | --- | --- | --- |
| Java source / default values | Application | Business logic and safe defaults | Parse rules, default threshold. |
| `application.properties` | Spring Boot | Spring Environment / bean configuration | `orders.threshold`, log levels. |
| Spring profile files | Spring Boot | An activated profile | `application-prod.properties`. |
| `host.json` | Azure Functions Host | All functions in the Function App | Host logging, timeouts, extension options. |
| `local.settings.json` | Local Core Tools | Dev machine execution environment | `FUNCTIONS_WORKER_RUNTIME`, local connections. |
| Azure App Settings | Azure platform and runtime process | Function App in the cloud | `MAIN_CLASS`, `SPRING_PROFILES_ACTIVE`, connection settings. |
| Managed Identity / Azure RBAC | Microsoft Entra ID and target services | Runtime or deployment identity | Reading Key Vault, writing to Queues. |
| Key Vault | Azure platform or Azure SDK | Secret values | Database passwords, API tokens when direct identity isn't supported. |

Azure stores App Settings at the Function App level and injects them into the process as **environment variables**; all functions in the same Function App share that configuration. Changing App Settings typically restarts the Function App. Therefore, workloads needing distinct configurations or scaling schedules should be split into separate Function Apps when operationally justified. See [Function App settings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-use-azure-function-app-settings) and [App settings reference](https://learn.microsoft.com/en-us/azure/azure-functions/functions-app-settings).

### 2.1. Do Not Confuse the Three Configuration Files

**`host.json`** belongs to the Azure Functions Host, not Spring Boot. It applies to all functions in the same Function App.

**`local.settings.json`** is used by Azure Functions Core Tools during local runs. It holds a local copy of app settings for the dev machine; it is not automatically published to Azure by default and may hold secrets, so never commit it.

**`application.properties`** belongs to Spring Boot. It configures Spring beans, profiles, logging, and business rules. Spring Boot can also receive overrides from environment variables supplied by Azure App Settings.

### 2.2. Boundary Between Host Settings and Business Settings

Example:

~~~json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true
      }
    }
  }
}
~~~

This is an illustrative host configuration snippet. Order thresholds, partner URLs, or feature flags belong in **Spring/application configuration**, not stuffed into `host.json` merely because they run in Azure.

## 3. Designing Dev, Staging, and Production Environments

An operationally clean structure separates environments using **dedicated Function Apps and supporting resources**:

~~~mermaid
flowchart TB
    subgraph Dev["Development"]
      D["Function App: orders-dev"]
      DS["Storage dev"]
      DK["Key Vault dev"]
      DI["Managed Identity dev"]
      D --> DS
      D --> DK
      D --> DI
    end
    subgraph Stage["Staging"]
      S["Function App: orders-staging"]
      SS["Storage staging"]
      SK["Key Vault staging"]
      SI["Managed Identity staging"]
      S --> SS
      S --> SK
      S --> SI
    end
    subgraph Prod["Production"]
      P["Function App: orders-prod"]
      PS["Storage prod"]
      PK["Key Vault prod"]
      PI["Managed Identity prod"]
      P --> PS
      P --> PK
      P --> PI
    end
    A["Same source code / versioned artifact"] --> D
    A --> S
    A --> P
~~~

Each Function App can run the exact same code artifact while having separate App Settings, identities, RBAC, network access, and downstream resources.

| Property | Dev | Staging | Production |
| --- | --- | --- | --- |
| Storage | Test account | Pre-prod account | Production account |
| Key Vault | Dev vault | Staging vault | Production vault |
| Managed identity | Dev-only permissions | Test permissions | Strict least privilege |
| Spring profile | `dev` | `staging` | `prod` |
| Telemetry | Debug-oriented logs | Smoke/load test monitoring | Alerts, retention, and audit |
| Inbound access | Restricted to dev group | Testers/gateway | Entra auth/API gateway/network policies |
| Deploy | From dev branch | Post-testing | Via release gate and approval |

Never share a production storage account with local testing or staging just to save setup effort. Triggers can actually consume messages, write data, and cause side effects. Isolating data makes testing rollbacks, retries, and idempotency much safer.

### 3.1. A Function App Is a Configuration and Scaling Boundary

Functions in the same Function App:

- Share App Settings and host configuration.
- Are deployed together.
- Share per-instance resources when scaling.
- Share OS/runtime/hosting plan constraints.

If two groups of functions require different secrets, permissions, network policies, scaling, or release schedules, consider splitting them into separate Function Apps. Do not split solely because you have multiple `@Bean Function` beans; Spring function beans can still be composed and reused inside one application.

## 4. Business Configuration in Spring Boot

### 4.1. Defining Configuration Properties

Do not hard-code order thresholds inside functional beans. Create `src/main/java/example/azure/OrderProperties.java`:

~~~java
package example.azure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public record OrderProperties(
        long threshold,
        String prefix) {
}
~~~

In the main Spring Boot class, enable configuration properties scanning:

~~~java
package example.azure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionApplication.class, args);
    }
}
~~~

`OrderProperties` is business configuration. It has no Azure SDK dependency, so the same class works in unit tests or with another adapter.

### 4.2. Default Values in application.properties

`src/main/resources/application.properties`:

~~~properties
orders.threshold=1000000
orders.prefix=REF-
spring.application.name=orders-function
~~~

These are **safe default configs**, not secrets. Azure App Settings or profile-specific properties can override these values.

### 4.3. Function Beans Using Configuration

~~~java
@Bean
Function<String, String> normalizeOrder(OrderProperties properties) {
    return raw -> {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Order code is blank");
        }
        return properties.prefix()
                + raw.strip().toUpperCase(Locale.ROOT);
    };
}

@Bean
Function<OrderInput, OrderDecision> classifyOrder(
        OrderProperties properties) {
    return order -> new OrderDecision(
            order.id(),
            order.totalVnd(),
            order.totalVnd() >= properties.threshold()
                    ? "PRIORITY" : "STANDARD");
}
~~~

These illustrative methods belong in a Spring configuration class with the matching imports and domain records. The beans remain plain `Function`s; configuration is injected when the Spring context starts.

### 4.4. Overriding with Environment Variables

Spring Boot maps canonical property names to environment variables by replacing dots with underscores, removing hyphens, and uppercasing. Thus:

| Spring Property | Environment Variable |
| --- | --- |
| `orders.threshold` | `ORDERS_THRESHOLD` |
| `orders.prefix` | `ORDERS_PREFIX` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |

Example App Settings for staging:

~~~text
SPRING_PROFILES_ACTIVE=staging
ORDERS_THRESHOLD=1500000
ORDERS_PREFIX=STG-
~~~

Do not use `ORDERS_PRIORITY_THRESHOLD` for `orders.priority-threshold` without checking binding rules; hyphens are stripped in Spring Boot's environment variable mapping.

### 4.5. Spring Profiles

You can create:

~~~text
application.properties
application-dev.properties
application-staging.properties
application-prod.properties
~~~

Example `application-prod.properties`:

~~~properties
orders.threshold=2000000
orders.prefix=ORD-
logging.level.example.azure=INFO
~~~

Activate the profile via App Setting `SPRING_PROFILES_ACTIVE=prod`. Check startup logs to confirm which profile is active. Never bundle secrets into `application-prod.properties` inside the source repository.

## 5. Managing Azure App Settings

### 5.1. Common Settings

| Setting | Role |
| --- | --- |
| `FUNCTIONS_WORKER_RUNTIME=java` | Selects the Java language worker. |
| `FUNCTIONS_EXTENSION_VERSION=~4` | Selects the Azure Functions 4.x runtime. |
| `MAIN_CLASS` | Spring application class when the adapter/build requires explicit declaration. |
| `SPRING_PROFILES_ACTIVE` | Active Spring profile. |
| `ORDERS_THRESHOLD` | Example business configuration. |
| `AzureWebJobsStorage` | Host storage connection or identity-based connection. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Application Insights connection when using connection string auth. |

Declare only settings actually required by your app and hosting plan. Some settings are pre-populated by Azure when provisioning the Function App; do not overwrite them arbitrarily.

### 5.2. Setting Values via the Azure Portal

1. Open the target environment's Function App.
2. Go to **Settings -> Environment variables -> App settings**.
3. Add or update setting names and values.
4. Save changes and confirm the app restart if prompted by the platform.
5. Verify function startup and behavior after restart.

App Settings are encrypted at rest by Azure, yet anyone with config-read permissions can still view them. Never treat "encrypted at rest" as an excuse to store raw passwords/tokens in settings; prefer Managed Identity or Key Vault references.

### 5.3. Setting Values via Azure CLI

Example updating non-secret values:

~~~bash
az functionapp config appsettings set \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --settings \
    SPRING_PROFILES_ACTIVE=staging \
    ORDERS_THRESHOLD=1500000 \
    ORDERS_PREFIX=STG-
~~~

This command **modifies cloud configuration** and typically restarts the Function App. Replace placeholders with authorized resources and verify your active subscription beforehand. Never pass plaintext secrets on the command line, as they can persist in shell history or pipeline logs.

Inspect configuration with:

~~~bash
az functionapp config appsettings list \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

The output may include sensitive values; never paste full outputs into issues, chat, or CI logs.

### 5.4. Configuration Changes Can Restart the App

Changing App Settings normally restarts the Function App across hosting plans, which can interrupt running invocations. When changing multiple settings:

- Batch changes into a single tested release.
- Use a staging slot if supported by your plan.
- On Flex Consumption, evaluate the current rolling update / site update strategy.
- Re-measure cold starts and verify triggers after restart.
- Never assume changing one config value affects only a single function method.

## 6. Managed Identity: Secretless Outbound Authentication

A **Managed Identity** is an identity managed by Microsoft Entra ID for an Azure resource. The Function App uses it to obtain access tokens and access Key Vault, Storage, Service Bus, or other Microsoft Entra-enabled services without storing client secrets in source or config.

### 6.1. System-Assigned vs. User-Assigned

| Characteristic | System-Assigned | User-Assigned |
| --- | --- | --- |
| Lifecycle | Tied to one Function App; deleting the app deletes the identity. | Standalone Azure resource; can be attached to multiple apps. |
| Cardinality | One system-assigned identity per app. | Multiple user-assigned identities can be attached. |
| When created | Enabled on the Function App. | Created independently first, then assigned to the app. |
| Use cases | App has an independent lifecycle and dedicated permissions. | Identity must survive app replacement or be shared cleanly. |
| Connection config | Used by default if no user-assigned identity is specified. | Usually requires client ID or resource ID in connection settings. |

**Recommendation:** use system-assigned when a Function App has its own lifecycle and permissions; use user-assigned when the identity must outlive app recreation or needs permissions pre-assigned before the Function App exists.

### 6.2. Enabling System-Assigned Identity

Via Azure Portal:

1. Open the Function App.
2. Select **Settings -> Identity**.
3. On the **System assigned** tab, switch Status to **On**.
4. Save and record the Principal/Object ID.
5. Assign RBAC roles on target resources.

Via Azure CLI:

~~~bash
az functionapp identity assign \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

Inspect the identity:

~~~bash
az functionapp identity show \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

Enabling an identity does not grant access to target services on its own. Role assignments at the proper scope are still required.

### 6.3. User-Assigned Identity

Create a standalone identity:

~~~bash
az identity create \
  --name <IDENTITY_NAME> \
  --resource-group <RESOURCE_GROUP>
~~~

Retrieve the identity's name, resource ID, and client ID; the following CLI snippet uses the identity name:

~~~bash
az functionapp identity assign \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --identities <USER_ASSIGNED_IDENTITY_NAME>
~~~

When multiple identities are attached, specify the exact client ID or resource ID in each connection. Do not set one global identity variable and expect every binding/SDK to pick the right identity in all cases.

### 6.4. Deployment Slot Identities

When using deployment slots, each slot has its own scoped identity and identity settings. Never assume a staging slot automatically inherits the production slot's managed identity or role assignments. Verify the identity on **the exact target slot** before running smoke tests.

## 7. Azure RBAC: Granting the Right Role at the Right Scope

A Managed Identity requires permissions via **Azure Role-Based Access Control (RBAC)**. Being able to read ARM resource metadata does not grant data-plane read/write permissions.

### 7.1. Control Plane vs. Data Plane

| Permission Type | Examples | Used For |
| --- | --- | --- |
| Control plane | Reader, Contributor, Website Contributor | Managing resources, configuring apps, deploying code within role scope. |
| Data plane | Storage Blob Data Reader, Storage Queue Data Message Processor, Key Vault Secrets User | Reading/writing blobs, consuming queues, reading secrets. |

A `Contributor` role on a resource group does not implicitly allow reading blobs or secrets. Conversely, `Storage Blob Data Reader` does not allow deploying code or editing Function App settings.

### 7.2. Principles of Permission Assignment

- Assign roles at the **smallest possible resource scope**: specific storage account, queue, container, or vault.
- Use built-in roles granting only what the app requires.
- Never assign `Owner` or `Contributor` to a runtime identity just to silence 403 errors.
- Separate read permissions from write permissions.
- Role assignments can take several minutes to propagate; an immediate 403 after assigning a role does not always mean misconfiguration.
- Each trigger/binding may need different roles, even against the same storage account.

### 7.3. Example: Granting Permission to Read Key Vault Secrets

For Key Vault using Azure RBAC, the standard role for secret-reading apps is **Key Vault Secrets User**. Assign it at vault scope:

~~~bash
az role assignment create \
  --assignee-object-id <FUNCTION_APP_PRINCIPAL_ID> \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope <KEY_VAULT_RESOURCE_ID>
~~~

If the vault uses legacy access policies instead of Azure RBAC, grant the corresponding secret `Get` permission under that model. Never treat RBAC roles and access policies as the same mechanism.

### 7.4. Example: Storage Roles for Host and Queue Trigger

For host-required `AzureWebJobsStorage`, Microsoft lists `Storage Blob Data Owner` as the minimum role for managed-identity host storage connections. Some diagnostic events also require `Storage Table Data Contributor`.

With a Queue Trigger, binding roles also depend on operations:

| Component | Reference Role |
| --- | --- |
| Host-required `AzureWebJobsStorage` | `Storage Blob Data Owner` |
| Queue Trigger (receive only) | `Storage Queue Data Message Processor` (or the role required by docs/extension for the scenario). |
| Queue output / send message | `Storage Queue Data Message Sender`. |
| Queue input + output needing multiple ops | Pick the least-privilege role covering actual ops; typically `Storage Queue Data Contributor`. |

A Blob Trigger may need permission to write poison messages to a Queue; hence a Blob Trigger's role is broader than plain Blob read access. Consult the [identity-based connections role matrix](https://learn.microsoft.com/en-us/azure/azure-functions/manage-connections) for your exact extension/version and binding.

### 7.5. Granting Permissions with Azure CLI

Retrieve the Function App's Principal ID:

~~~bash
az functionapp identity show \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --query principalId \
  --output tsv
~~~

Assign the role at resource scope:

~~~bash
az role assignment create \
  --assignee-object-id <PRINCIPAL_ID> \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Queue Data Message Processor" \
  --scope <STORAGE_ACCOUNT_RESOURCE_ID>
~~~

This command grants real permissions. Verify subscription, principal, and resource scope before running. If the app only consumes one specific queue and the role/extension supports narrower scope, scope down to the queue instead of the entire storage account.

### 7.6. Never Grant Runtime and Deployment Permissions to the Same Identity

Separate the two identities:

- **Deployment principal:** pipeline/operator releasing code, needing permissions to update the Function App, package, and settings at app scope.
- **Runtime managed identity:** running process, needing only permissions to read/write data, secrets, or telemetry for business logic.

If the runtime app is compromised, the runtime identity must not be able to create role assignments, delete resources, or replace code. This is a vital boundary in least-privilege design.


## 8. Identity-Based Connection for AzureWebJobsStorage

`AzureWebJobsStorage` is a **host-required connection**. Azure Functions uses default storage to coordinate timer/singleton execution, store function keys, and perform other host tasks. Function Apps usually fail to start without it.

### 8.1. Using Managed Identity with Standard Azure DNS Storage Accounts

With a system-assigned identity, App Settings can declare:

~~~text
AzureWebJobsStorage__accountName=<STORAGE_ACCOUNT_NAME>
AzureWebJobsStorage__credential=managedidentity
~~~

With a user-assigned identity, add the client ID:

~~~text
AzureWebJobsStorage__accountName=<STORAGE_ACCOUNT_NAME>
AzureWebJobsStorage__credential=managedidentity
AzureWebJobsStorage__clientId=<USER_ASSIGNED_IDENTITY_CLIENT_ID>
~~~

The Azure Functions Host interprets settings prefixed with `AzureWebJobsStorage__` as properties of an identity-based connection. Never leave an old connection string under the same setting name after switching to identity-based connections; inspect existing settings to prevent conflicts.

### 8.2. Storage Accounts Using Custom DNS or Sovereign Clouds

When an account does not use standard Azure DNS endpoints, you may need explicit service URIs:

~~~text
AzureWebJobsStorage__blobServiceUri=https://<ACCOUNT>.blob.contoso.com
AzureWebJobsStorage__queueServiceUri=https://<ACCOUNT>.queue.contoso.com
AzureWebJobsStorage__tableServiceUri=https://<ACCOUNT>.table.contoso.com
AzureWebJobsStorage__credential=managedidentity
~~~

Use the real URIs and DNS of your cloud/storage account. Never use `contoso.com` in real environments.

### 8.3. Granting Permissions for Host Storage

With managed identity, `Storage Blob Data Owner` is the minimum role documented by Microsoft for host-required `AzureWebJobsStorage` in the current model. Diagnostic events written to Table Storage may additionally need `Storage Table Data Contributor`.

Some triggers impose extra host storage requirements:

| Trigger / Feature | Additional Permissions Potentially Needed |
| --- | --- |
| Timer Trigger | Blob lock/coordination on host storage; check runtime role matrix. |
| Blob Trigger | `Storage Blob Data Owner` and Queue permissions needed to write poison blobs. |
| Event Hubs Trigger | `Storage Blob Data Owner` on host storage for checkpointing when using the storage checkpoint store. |
| Durable Functions | Blob, Queue, and Table data roles per extension configuration. |

Never apply a single blanket role to all extensions. The binding extension version, trigger type, and host storage config determine exact roles. See [Configure connections to remote services](https://learn.microsoft.com/en-us/azure/azure-functions/manage-connections).

### 8.4. Managed Identity for Host Storage by Hosting Plan

Identity-based `AzureWebJobsStorage` has limitations involving Azure Files:

| Hosting Plan | Managed Identity for Host Storage | Notes |
| --- | --- | --- |
| Flex Consumption | Fully supported per current docs. | Does not use Azure Files for content shares in the legacy model. |
| Dedicated (App Service) | Fully supported. | No dynamic Azure Files scaling as in Consumption/Premium. |
| Consumption | Supports identity for Blob/Queue/Table in supported cases. | `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` may still need secrets/Key Vault when using Azure Files. |
| Elastic Premium | Supports identity for Blob/Queue/Table in supported cases. | Azure Files content shares still have separate requirements. |

If Azure Files cannot be removed on Consumption/Premium, Microsoft recommends protecting `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` with Key Vault. Check your specific hosting plan before removing that connection string; removing it improperly can prevent mounting the content share or starting the app.

### 8.5. Local vs. Cloud Differences

Locally, the Azure Functions Host uses the **developer identity**, not a Function App managed identity. For local identity-based connections, sign in via Azure CLI or developer tooling, grant permissions to the developer account at storage scope, and follow the binding's local guide. Do not force `credential=managedidentity` into `local.settings.json` when using a developer identity; that property is for hosted managed-identity environments.

For local runs using Azurite, `AzureWebJobsStorage` can stay `UseDevelopmentStorage=true`. These are two distinct approaches: the local emulator does not verify Azure RBAC or managed identities.

## 9. Identity-Based Connections for Queue, Blob, and Service Bus

Beyond host storage, each trigger/binding can use its own connection. The `connection` name in the annotation must match the App Setting prefix.

### 9.1. Azure Storage Queue

Example handler:

~~~java
@FunctionName("receiveOrder")
public void receiveOrder(
        @QueueTrigger(
                name = "message",
                queueName = "orders-input",
                connection = "OrdersQueue")
        String payload,
        ExecutionContext context) {
    // Validate payload then invoke FunctionCatalog/service.
}
~~~

With standard Azure Storage endpoints and system-assigned identity, configure:

~~~text
OrdersQueue__queueServiceUri=https://<STORAGE_ACCOUNT>.queue.core.windows.net
OrdersQueue__credential=managedidentity
~~~

With user-assigned identity, add:

~~~text
OrdersQueue__clientId=<USER_ASSIGNED_IDENTITY_CLIENT_ID>
~~~

The prefix `OrdersQueue` must match `connection = "OrdersQueue"` exactly. If you change the annotation to `connection = "OrderEvents"`, update the connection settings prefix to match.

### 9.2. Azure Blob Storage

Example settings for connection `OrdersBlob`:

~~~text
OrdersBlob__blobServiceUri=https://<STORAGE_ACCOUNT>.blob.core.windows.net
OrdersBlob__credential=managedidentity
~~~

A Blob Trigger may also need the Queue service URI of the same storage account to write poison blob metadata/queue entries:

~~~text
OrdersBlob__queueServiceUri=https://<STORAGE_ACCOUNT>.queue.core.windows.net
~~~

Required roles are typically broader than plain Blob Reader when the trigger must update checkpoints/poison queues. Check the extension's role table and grant the exact permissions for your trigger.

### 9.3. Azure Service Bus

A Microsoft Entra ID connection looks like:

~~~text
OrderBus__fullyQualifiedNamespace=<NAMESPACE>.servicebus.windows.net
OrderBus__credential=managedidentity
~~~

With user-assigned identity:

~~~text
OrderBus__clientId=<USER_ASSIGNED_IDENTITY_CLIENT_ID>
~~~

In trigger annotations, use `connection = "OrderBus"`. For queue consumers, the role is typically `Azure Service Bus Data Receiver`; for senders/outputs, `Azure Service Bus Data Sender`. If a trigger listens to a topic subscription, the role assignment must have effective scope at the **subscription** level per extension requirements; assigning only at topic level without subscription coverage can cause authorization errors.

### 9.4. One Connection Prefix per Purpose

Do not reuse `AzureWebJobsStorage` as the connection name for every binding just because it already exists. Even if they share the same underlying storage account, separate connection prefixes help:

- Clarify which binding uses which identity and endpoint.
- Grant distinct roles for host storage vs. data bindings.
- Swap the storage account for one binding without changing the host connection.
- Distinguish host startup errors from message-processing errors.

### 9.5. Version and Extension Compatibility

Identity-based connections require Azure Functions runtime 4.x or newer, along with a supporting binding extension version. When upgrading host/runtime/extensions, re-verify:

1. App Settings prefixes are accurate.
2. The managed identity is attached to the right Function App/slot.
3. RBAC roles have propagated.
4. Storage/Service Bus firewalls and private endpoints allow network traffic.
5. Triggers can receive/send messages and retry as expected.

## 10. Azure Key Vault: Storing Secrets When Managed Identity Cannot Be Used Directly

Prefer direct managed identity for services supporting Microsoft Entra ID. When a service only accepts a password, connection string, or API key, use **Azure Key Vault** for secret storage, rotation, and auditing.

Two common integration options exist:

1. **Key Vault references in App Settings:** the platform resolves the secret, and Spring/Java reads it like a normal environment variable.
2. **Azure SDK in code:** a Java client queries Key Vault using `DefaultAzureCredential`.

### 10.1. Creating a Key Vault Reference

Suppose a secret is named `partner-api-key`. An Azure App Setting can be set to:

~~~text
PARTNER_API_KEY=@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/partner-api-key)
~~~

The application reads it via environment variable or Spring configuration:

~~~java
String apiKey = environment.getProperty("PARTNER_API_KEY");
~~~

Code does not need to call Key Vault itself when using references. The platform substitutes the secret value when injecting the setting into the process.

**Never commit secret values**, and omit a pinned secret version in the URI if you want automatic pickup of new versions upon rotation—unless your release process intentionally pins versions.

### 10.2. Granting Permission to Read Key Vault

For RBAC-enabled Key Vaults, the standard role for secret-reading apps is **Key Vault Secrets User**, assigned at vault scope. Under legacy access policies, grant `Get` secret permission via that model.

Key Vault references default to the Function App's system-assigned identity. If using a user-assigned identity, attach it to the app and set `keyVaultReferenceIdentity` to the identity's **resource ID**.

If Key Vault has network restrictions, the app also needs a valid network path to the vault. Correct RBAC paired with broken DNS/private endpoint/VNet routing will still fail access.

### 10.3. Rotation and Caching of Key Vault References

When the reference omits a secret version, the platform tracks the latest version. Refreshes can take time due to App Service caching; current docs note automatic updates occur within roughly 24 hours. Restarts or configuration updates can trigger an earlier fetch.

Therefore, when rotating secrets:

- Ensure the new secret is created and accepted by the target service.
- Check the Key Vault reference resolution status.
- Confirm the app picks up the new value.
- If immediate refresh is needed, use Microsoft's supported reference refresh procedure.
- Never delete the old secret before all instances and consumers have transitioned to the new secret.

### 10.4. Diagnosing Key Vault References

If a reference fails to resolve, the platform may pass the literal `@Microsoft.KeyVault(...)` string into the process. Code expecting a password then receives the reference text instead.

Check:

- Secret name and URI are accurate.
- Managed identity is enabled and authorized to read secrets.
- Vault network/firewall/private DNS permits the app.
- Key Vault reference status in the Azure Portal.
- Secret is not disabled, expired, or deleted.
- If using a user-assigned identity, `keyVaultReferenceIdentity` holds the exact resource ID.


## 11. Accessing Key Vault Directly from Java with the Azure SDK

If secrets must be queried dynamically at runtime, use the Azure SDK instead of App Setting references.

### 11.1. Maven Dependencies

Manage versions using the Azure SDK BOM or project dependency management, then add:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
</dependency>
~~~

Do not pick arbitrary individual versions for Azure SDK modules if your project already uses a BOM; keep them aligned with the Spring Boot/SCF release train.

### 11.2. SecretClient with DefaultAzureCredential

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

SecretClient client = new SecretClientBuilder()
        .vaultUrl("https://<VAULT_NAME>.vault.azure.net/")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

String secret = client.getSecret("partner-api-key").getValue();
~~~

`DefaultAzureCredential` selects a credential suitable for the environment. Locally, developers can authenticate via Azure CLI/IDE credentials; on Azure, the credential chain uses the managed identity assigned to the Function App. Grant secret-read permission to the **exact identity** selected.

### 11.3. Registering the Client Once

Azure SDK clients should be reused across invocations. Register a singleton bean:

~~~java
@Configuration
class KeyVaultClientConfiguration {

    @Bean
    SecretClient secretClient(Environment environment) {
        String vaultUrl = environment.getRequiredProperty(
                "AZURE_KEY_VAULT_URL");

        return new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
~~~

This is a Spring configuration example requiring `org.springframework.context.annotation.Bean`, `Configuration`, and `org.springframework.core.env.Environment`. Never call `new SecretClientBuilder()` inside every function invocation. Never log secret values, store secrets in static mutable fields, or return secrets in HTTP responses.

### 11.4. Choosing Key Vault References vs. Azure SDK

| Criterion | App Setting Key Vault Reference | Azure SDK in Java |
| --- | --- | --- |
| Code changes needed | Usually none. | Yes. |
| Reading secrets | Platform resolves into an App Setting. | Application explicitly calls Key Vault. |
| Dynamic multi-secret lookup | Less convenient than SDK. | Better suited. |
| Rotation / caching | Managed by platform reference/cache. | Application manages refresh/cache/lifecycle. |
| Testing | Check resolution and setting values. | Mock/test client or dev vault. |
| Permissions | Function App identity reads the secret. | Active SDK credential reads the secret. |

If you only need a fixed connection string, a Key Vault reference is usually simpler. If business logic must fetch many secrets by tenant or dynamic secret name, consider the SDK and design caching, rotation, timeouts, and error handling.

## 12. Authenticating HTTP Callers and Authorizing Resource Access Are Separate Concerns

The **Managed Identity** covered above lets the Function App make **outbound** calls to Azure resources. It does not authenticate users calling your HTTP Trigger.

### 12.1. Function Keys Are Not User Authentication

An HTTP Trigger may declare:

~~~java
@HttpTrigger(
        name = "request",
        methods = {HttpMethod.POST},
        authLevel = AuthorizationLevel.FUNCTION,
        route = "orders")
HttpRequestMessage<Optional<String>> request
~~~

Common levels:

| Auth Level | Meaning |
| --- | --- |
| `ANONYMOUS` | No function key required at the trigger layer. |
| `FUNCTION` | Requires a function-specific or host key. |
| `ADMIN` | Requires the master key; overly broad, never use for normal APIs. |

A function key is a shared secret for invoking an endpoint, not a user identity, and does not replace role- or tenant-based authorization. When user/app authentication is needed, use Microsoft Entra ID authentication (App Service Authentication), API Management, or a suitable gateway.

If enabling App Service Authentication while keeping `authLevel=FUNCTION`, test both layers: callers might need both an Entra token and a function key depending on configuration. Clearly designate which layer authenticates callers and which enforces business authorization; avoid accidental double credential requirements.

### 12.2. Microsoft Entra Authentication and API Management

For externally consumed APIs:

- Configure App Service Authentication to require Microsoft Entra ID tokens where appropriate.
- Validate issuer, audience, tenant, and claims/roles at the right layer.
- Use API Management when you need quotas, versioning, request transformation, subscription management, or policies.
- Never rely solely on a function key to decide which tenant's orders a user may access.
- Enforce both authentication and authorization at business boundaries.

### 12.3. CORS, Access Restrictions, and Private Endpoints

- **CORS** controls browser origins; it is not authentication.
- **Access restrictions** limit which network sources can reach the Function App.
- **Private endpoints** restrict inbound traffic to a private network.
- **VNet integration** enables outbound connectivity to private/network-restricted services.
- Key Vault/Storage firewalls and private DNS must align with the Function App's network path.

When enabling private endpoints and disabling public network access, your deployment pipeline also needs network connectivity/DNS to the deployment endpoint. Not just the runtime, but build/runner agents may need to reside inside an allowed network.

### 12.4. Function Keys and Where They Are Stored

Azure Functions stores function/host keys in secret storage per host config, using Blob Storage or Key Vault on supported runtimes. When moving key storage to Key Vault, configure `AzureWebJobsSecretStorageType` and `AzureWebJobsSecretStorageKeyVaultUri` per docs; grant the key-management permissions the host needs, rather than confusing them with `Key Vault Secrets User` used for reading ordinary secrets.

For a Key Vault used to **store function keys**, the host needs secret management permissions such as `Get`, `Set`, `List`, and `Delete` per configuration/runtime—a different use case from Key Vault references. Use a dedicated vault for each Function App's key storage because keys stored in a shared vault risk collisions or overwrites.

Never share the master key with clients. Prefer Entra authentication/gateways for production APIs and manage function keys as rotatable credentials.

## 13. Local Development and Developer Identity

There is no Function App managed identity on a local machine. With the Azure SDK's `DefaultAzureCredential`, the credential chain can pick up a signed-in Azure CLI or developer tool identity. With identity-based Azure Functions bindings, local development similarly uses the developer identity per each binding's guide.

### 13.1. Signing In with Azure CLI

~~~bash
az login
az account show
~~~

Confirm you are in an authorized dev subscription and tenant. Never use a production identity just to run locally.

### 13.2. Granting Permissions to the Developer

If a local function needs to read Queue/Blob/Key Vault via Entra ID, assign the proper role to the **developer account** at dev resource scope. Never assign a role to a developer user and assume the Function App's managed identity inherits it; they are two separate principals.

### 13.3. Local Settings Differ from Cloud App Settings

Example `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionApplication",
    "SPRING_PROFILES_ACTIVE": "dev",
    "ORDERS_THRESHOLD": "1000000",
    "ORDERS_PREFIX": "DEV-",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

Settings in `Values` are loaded into the process environment by Core Tools locally. On publish, Core Tools does not automatically push them to Azure by default. Provision cloud App Settings separately with proper connections/identities.

Never commit `local.settings.json` if it contains secrets, connection strings, or local credentials. Use `.gitignore`, secret managers, and isolated dev resources.


## 14. Networking, Private Endpoints, and Connectivity to Target Services

Managed identity solves **authentication**, not **network connectivity**. A Function App holding a valid token can still fail to reach Storage, Key Vault, or Service Bus if blocked by firewalls, DNS, or routing.

### 14.1. Inbound and Outbound Networking

| Mechanism | Traffic Direction | Purpose |
| --- | --- | --- |
| Function App private endpoint | Inbound | Private network clients reach the Function App. |
| VNet integration | Outbound | Function App reaches private resources inside a VNet/peered network. |
| Key Vault/Storage private endpoint | Inbound to target resource | Accepts traffic only from permitted networks. |
| Access restrictions | Inbound | Allows/blocks IPs/subnets per policy. |
| Private DNS zone | Name resolution | Ensures service hostnames resolve to the right private IPs. |

Do not confuse a Function App's inbound private endpoint with outbound VNet integration. An app with an inbound private endpoint still requires separate outbound networking to reach private storage or vaults.

### 14.1.1. Networking Support Depends on the Hosting Plan

| Hosting Plan | Inbound Access Restrictions | Function App Private Endpoint | Outbound VNet Integration |
| --- | --- | --- | --- |
| Flex Consumption | Yes | Yes | Yes |
| Consumption (legacy) | Yes | No | No |
| Elastic Premium | Yes | Yes | Yes |
| Dedicated (App Service) | Yes | Yes | Yes |
| Azure Container Apps | Managed by Container Apps environment | Does not use legacy App Service private endpoints for Function Apps; uses environment networking | Managed by environment |

Therefore, never assume private endpoints or VNet integration exist on every plan. Legacy Consumption does not support outbound VNet integration; if workloads need private network access, choose a plan/architecture that supports it.

### 14.2. Key Vault Network Restrictions

If Key Vault permits only private networks:

1. Enable VNet integration supported by your hosting plan.
2. Create a private endpoint and configure private DNS.
3. Verify the Function App routes traffic to the subnet/endpoint.
4. If the plan/OS requires routing all traffic, enable it per Microsoft documentation.
5. Check Key Vault reference resolution status and audit logs.

In Flex Consumption, some routing behaviors differ from Linux Consumption/Premium; never copy VNet setup commands blindly from another plan. Check [Azure Functions networking options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-networking-options) for your exact plan and OS.

### 14.3. Storage Firewalls and Host Startup

If public network access is restricted on the storage account used for `AzureWebJobsStorage`, the Azure Functions Host must still be able to reach that account. Otherwise, the host may fail to start, timer/queue coordination may break, or triggers may fail to fire.

Verify all of the following:

- Storage account network rules.
- Private endpoints for the required Blob/Queue/Table services.
- DNS resolution from both the Function App and deployment runners.
- Managed identity RBAC data roles.
- Connection settings and matching identity prefixes.

### 14.4. A 403 Error Is Not Always an RBAC Issue

A 403 response can stem from:

- Missing data-plane role on the identity.
- Wrong role assignment scope or unpropagated assignment.
- Key Vault/storage firewall rejecting the source IP/subnet.
- Private DNS resolving to the public endpoint instead.
- Function App using the wrong system-assigned or user-assigned identity.
- App Setting connection prefix mismatching the binding.

Inspect response details/diagnostic logs and network paths before granting broader permissions.

## 15. Deployment: Decoupling Runtime Configuration from Deployment Artifacts

A deployment artifact should package code, dependencies, and required metadata; environment-specific settings are supplied separately on each Function App. That lets the exact same artifact version progress across dev, staging, and production.

### 15.1. Maven Deployment Workflow

Once build/packaging succeeds and the Azure Functions Maven plugin is configured:

~~~bash
./mvnw clean package
./mvnw azure-functions:deploy
~~~

The deploy command updates running code and can provision resources or incur costs depending on plugin settings. Before executing, verify subscription, resource group, Function App name, Java runtime, hosting plan, app settings, and identities. Never put secrets in `pom.xml` or on the command line.

### 15.2. Core Tools Publish

For a project with a compatible package:

~~~bash
func azure functionapp publish <FUNCTION_APP_NAME>
~~~

This command suits direct dev/publish workflows. Production should use pipelines with builds, tests, artifact versioning, and release gates.

### 15.3. Deployment Methods Depend on the Hosting Plan

| Hosting Plan | Deployment Behavior | Release Strategy |
| --- | --- | --- |
| Flex Consumption | Flex package deployment; code package stored in a deployment container. | Use Flex-supported tooling; rolling updates / site update strategy where supported. No deployment slots. |
| Consumption (legacy) | ZIP/external package depending on OS and deployment path. | Verify Windows/Linux specifics and storage constraints. |
| Elastic Premium | ZIP/external package and deployment slots where supported. | Deploy to a staging slot and swap after smoke tests. |
| Dedicated (App Service) | ZIP and slots per App Service plan. | Staging slot / release pipeline. |
| Azure Container Apps | Container images and revisions. | Manage image tags/digests and revision traffic. |

Never apply a single ZIP deployment command to every plan. Flex Consumption uses its own deployment technology; Premium/Dedicated can use slots. See [Deployment technologies in Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-technologies).

### 15.4. Deployment Slots and Identity

On plans supporting slots:

- Each slot is a distinct running environment with its own configuration and identity.
- Verify slot-specific App Settings and connection strings.
- Grant RBAC roles to each slot's managed identity.
- Run smoke tests in the staging slot before swapping.
- After swapping, verify identities, secret references, storage, and network policies remain intact.

Flex Consumption currently does not support deployment slots. Use a separate staging Function App or the rolling update / site update strategy documented for the plan.

### 15.5. App Settings Changes Can Restart the App

Updating App Settings typically restarts the Function App. When updating settings alongside code deployments, account for restarts/cold starts and in-flight invocations. For event-driven workloads, design stateless, idempotent handlers to absorb redeliveries during restarts.

## 16. CI/CD and Deployment Identity

### 16.1. Separating Pipeline Identity from Runtime Identity

| Identity | Responsibility | Recommended Permissions |
| --- | --- | --- |
| Developer identity | Local runs, debugging, reading dev resources. | Scoped strictly to dev environments. |
| CI/CD identity | Deploying packages, updating App Settings if managed by the pipeline. | Deployment role such as `Website Contributor` scoped to the Function App/resource; never subscription-wide `Owner`. |
| Runtime managed identity | Accessing storage, queues, vaults, databases, telemetry. | Only the data roles required by the workload. |

Never reuse runtime credentials to authenticate CI/CD, and never grant resource administration roles to a Function App's runtime identity.

### 16.2. Using Workload Identity Federation

For GitHub Actions or Azure DevOps, prefer OIDC / workload identity federation over static client secrets where supported. The pipeline exchanges federated tokens via trust configured in Microsoft Entra ID, eliminating long-lived passwords in repository secrets.

Configure:

- Federated credentials scoped to the exact repository/branch/environment or service connection.
- Deployment role scoped to the target Function App/resource group.
- Separate App Settings update permissions if the pipeline manages settings.
- Role assignment creation permissions separated and granted only when IAM provisioning is explicitly intended.
- Approval gates before production.

### 16.3. One Artifact Across Multiple Environments

~~~mermaid
flowchart LR
    A["Commit / Pull request"] --> B["Build + unit tests"]
    B --> C["Spring context + catalog tests"]
    C --> D["Azure package + artifact hash"]
    D --> E["Deploy dev"]
    E --> F["Deploy staging"]
    F --> G["Smoke test + approval"]
    G --> H["Deploy / promote production"]
    H --> I["Monitor + rollback if needed"]
~~~

Never rebuild the same source with unpinned dependency versions for each environment. Build one artifact with a clear version/hash, then inject settings, secrets, and identities per Function App.

### 16.4. Managing Infrastructure with IaC

Use Bicep, Terraform, or ARM templates to declare:

- Function App and hosting plan.
- Storage, Key Vault, and Application Insights.
- Managed identity assignments.
- RBAC role assignments.
- VNets, private endpoints, and DNS.
- App Settings and deployment configuration.

Keep secrets out of state files if the state backend might store them in plaintext. For Key Vault references, IaC declares the reference URI rather than the secret value.

## 17. Post-Deploy Verification, Rollback, and Operations

### 17.1. Smoke Test Checklist

After deploying to staging:

1. Function App is `Running` on the expected Java/runtime version.
2. Azure Host discovers all `@FunctionName` methods.
3. Spring context initializes and `FunctionCatalog.lookup(...)` succeeds.
4. `SPRING_PROFILES_ACTIVE` and business settings match the environment.
5. The app/slot managed identity matches the intended identity.
6. The identity resolves Key Vault references and connection settings.
7. Storage/Queue/Service Bus/Database bindings reach the right dev/staging resources.
8. HTTP auth, function key/Entra policies, and network restrictions behave properly.
9. Logs include invocation IDs/correlation IDs and leak no secrets or sensitive payloads.
10. Queue retries, poison/DLQ handling, idempotency, and output bindings work as designed.

### 17.2. Verifying Configuration Without Leaking Secrets

Never dump all App Settings to console or CI logs. Expose a health/config diagnostic endpoint or startup log printing only:

- Active Spring profile.
- Non-sensitive resource/endpoint names.
- Managed identity name/client ID if policy allows.
- Dependency resolution status (never secret values).
- Artifact version / commit SHA.

Never log connection strings, API keys, function keys, tokens, or secret values.

### 17.3. Rollback

If a release fails:

1. Halt promotion if staging smoke tests fail.
2. On slot-enabled plans, swap/revert back to the stable slot per procedure.
3. On package deployments, redeploy the previously stored artifact using the matching tool/plan.
4. Restore App Settings or Key Vault secret versions if a config change caused the failure.
5. Verify identities, RBAC, and network rules were not altered unexpectedly.
6. Confirm trigger discovery, HTTP requests, and event processing after rollback.
7. Reconcile retried/redelivered messages; ensure idempotency prevents duplicate side effects.

Rolling back code does not automatically roll back database schemas, event schemas, or already-sent messages. Those require separate backward-compatible migration strategies.

### 17.4. Monitoring

Track at minimum:

- Spring/Java startup failures and dependency injection errors.
- Function discovery and binding errors.
- HTTP 4xx/5xx rates, latencies, and cold starts.
- Queue backlogs, retries, and poison/dead-letter queues.
- Storage/Key Vault/Service Bus 401/403/timeout errors.
- RBAC changes and secret access audits.
- Memory, concurrency, and dependency response times.
- Deployment status and active running version.


## 18. Troubleshooting Configuration, Identity, and Deployment

| Symptom | Layer to Check | Remediation |
| --- | --- | --- |
| Spring uses wrong threshold/prefix | Spring config binding | Check `SPRING_PROFILES_ACTIVE`, env var names, and precedence. |
| App Setting changed but code didn't pick it up | App restart / config cache | Confirm saved setting, restart/startup logs, and active profile. |
| Function App fails to start after storage change | Host-required connection | Check `AzureWebJobsStorage`, identity, roles, and DNS/network. |
| 401 from Azure Storage / Key Vault | Authentication | Check identity assignment, token audience, and credential chain. |
| 403 from Storage | Data-plane RBAC or firewall | Check role, scope, propagation, and network rules. |
| 403 from Key Vault | RBAC/access policy or private network | Check `Key Vault Secrets User`/Get permission, DNS/VNet, and reference status. |
| Binding receives no messages | Connection prefix / extension | Does `connection` match the setting prefix? Does extension version support identity? |
| Queue Trigger reads but fails to write output | Role lacks send/write permissions | Grant data-plane role matching the output operation. |
| Works locally, fails identity on Azure | Developer credential vs. managed identity | Check runtime principal and cloud role assignments. |
| App uses wrong user-assigned identity | Client ID / resource ID | Check `__clientId` or `__managedIdentityResourceId` under the connection prefix. |
| Timer/Blob/Event Hub fails after moving host storage to MI | Host storage permissions | Check extra required roles and extension support. |
| Premium/Consumption fails after removing Azure Files connection | Content share | Check `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING` and plan requirements. |
| Key Vault reference resolves as literal string | Reference resolution failure | Check URI, identity, role, secret status, network, and reference diagnostics. |
| New secret not picked up yet | Reference cache / refresh | Check version, refresh policy, restart/config update. |
| HTTP endpoint accessed without authorization | Inbound auth | Function keys do not replace Entra auth; check App Service Auth / API gateway. |
| Deploy succeeds, triggers do not appear | Package / trigger sync | Check package metadata and deployment tech; sync triggers if required. |
| Pipeline deploy gets 403 | Deployment identity | Check federated credentials and role scope for the pipeline principal. |
| Pipeline cannot reach deployment endpoint | Networking | Check self-hosted runner, VNet, DNS, and private endpoint connectivity. |
| Staging slot cannot read Key Vault | Slot identity / settings | Assign identity/RBAC to the slot and verify slot-specific settings. |
| Flex app rejects legacy slot/ZIP instructions | Hosting plan | Use Flex package deployment and plan-appropriate site update strategy. |

### 18.1. 401/403 Investigation Sequence

~~~text
1. Principal: is the Function App using system-assigned or user-assigned identity?
2. Credential: did the connection prefix/DefaultAzureCredential pick the right identity?
3. Authentication: was the token issued for the right service?
4. Authorization: is the RBAC role the right data-plane role and scope?
5. Propagation: has the role assignment had time to propagate?
6. Network: do firewall/private endpoint/DNS/VNet allow traffic?
7. Service: does the binding extension/SDK version support identity mode?
8. Settings: are the app setting name and connection prefix accurate?
~~~

Never grant subscription-wide `Contributor` "just to see if the 403 goes away." That masks the root cause and leaves excessive permissions in place.

## 19. Practice Exercises and Self-Assessment Questions

### 19.1. Exercises

1. **Separate environments:** create a settings matrix for dev/staging/prod using the same artifact with different thresholds/prefixes.
2. **Spring binding:** create `OrderProperties` with `@ConfigurationProperties` and override it via `ORDERS_THRESHOLD`.
3. **App Settings:** update a non-secret setting via Azure CLI; observe the restart and verify the active profile.
4. **System-assigned identity:** enable identity on a dev Function App and record its principal ID.
5. **RBAC scope:** assign `Storage Queue Data Message Processor` to the identity on a dev queue/storage account and test receiving messages.
6. **Queue output:** add an output binding and grant only the send role; verify read and write roles are distinct.
7. **AzureWebJobsStorage:** switch to an identity-based connection in a test environment, and check timer/host startup and storage-backed extensions.
8. **Key Vault reference:** create a dev secret, grant `Key Vault Secrets User`, and configure an app setting reference.
9. **Secret rotation:** add a new secret version, observe refresh/caching behavior, and verify the app reads the new value.
10. **Java SDK:** use `DefaultAzureCredential` to read a secret from Key Vault; run locally with Azure CLI identity, then test with the Function App's managed identity.
11. **Inbound auth:** test Function keys alongside Microsoft Entra authentication; explain the separate layers they protect.
12. **Networking:** restrict public access on a dev vault/storage account, configure private endpoints/DNS/VNet, and verify connectivity.
13. **CI/CD:** build a pipeline using workload identity federation and a deployment identity scoped to the Function App.
14. **Rollback:** store a prior artifact version, deploy a new version to staging, simulate failure, and roll back to the stable version.
15. **Troubleshooting:** trigger a 403 from a missing role in dev, and pinpoint the principal/scope/role rather than granting `Contributor`.

### 19.2. Self-Assessment

- What are the differences between `host.json`, `local.settings.json`, and Azure App Settings?
- Why do App Settings changes typically restart a Function App?
- Which environment variable does Spring property `orders.threshold` map to?
- How does a system-assigned identity differ in lifecycle from a user-assigned identity?
- Why isn't enabling a managed identity alone enough to access Storage?
- What is the difference between control-plane `Contributor` and data-plane `Storage Blob Data Reader`?
- Why is `AzureWebJobsStorage` a host-required connection?
- Why might Consumption/Premium still need an Azure Files connection even when using managed identity for host storage?
- How does `connection="OrdersQueue"` relate to `OrdersQueue__queueServiceUri`?
- When should you choose a Key Vault reference vs. the Azure SDK?
- Why is a local developer identity distinct from a Function App managed identity?
- Does a function key replace Microsoft Entra authentication?
- How does an inbound private endpoint differ from outbound VNet integration?
- Why should a deployment identity never be the same as the runtime identity?
- How does the hosting plan impact deployment methods, slots, and rollbacks?

## 20. Official References

- [Microsoft Learn — Configure function app settings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-use-azure-function-app-settings): App Settings, environment variables, restarts, and Azure CLI.
- [Microsoft Learn — App settings reference for Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-app-settings): host/runtime settings and application settings.
- [Microsoft Learn — Configure connections to remote services](https://learn.microsoft.com/en-us/azure/azure-functions/manage-connections): host-required connections, binding connections, identity-based settings, and RBAC role matrix.
- [Microsoft Learn — Use managed identities for App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/overview-managed-identity): system-assigned/user-assigned identities, assigning identities, and granting permissions.
- [Microsoft Learn — Key Vault references as App Settings](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references): reference syntax, managed identities, network restrictions, and rotation/caching.
- [Microsoft Learn — Azure Key Vault Secret client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/security-keyvault-secrets-readme): `SecretClient` and `DefaultAzureCredential`.
- [Microsoft Learn — Azure Functions networking options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-networking-options): VNet integration, private endpoints, and networking.
- [Microsoft Learn — Authentication and authorization in Azure App Service and Azure Functions](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization): built-in authentication (Easy Auth), identity providers, and authorization.
- [Microsoft Learn — Deployment technologies in Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-technologies): ZIP/package deployment, Flex Consumption, slots, remote packages, and trigger syncing.
- [Microsoft Learn — Azure Functions GitHub Actions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-github-actions): CI/CD and federated identity.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): environment variables, property sources, profiles, and configuration binding.
- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, `FunctionCatalog`, Java handlers, and packaging.

**Conclusion:** A Spring Cloud Function application on Azure requires managing **Spring configuration**, **Function App App Settings**, **runtime identities**, **Azure RBAC permissions**, **inbound authentication**, and the **deployment pipeline** together. Use Spring profiles/`@ConfigurationProperties` for business configuration; use managed identities and least-privilege roles for Entra ID-enabled services; use Key Vault where shared secrets are unavoidable; and choose deployment methods matching your hosting plan. Keep deployment identities separate from runtime identities, verify networking and trigger bindings, and run controlled smoke tests and rollbacks before production.




