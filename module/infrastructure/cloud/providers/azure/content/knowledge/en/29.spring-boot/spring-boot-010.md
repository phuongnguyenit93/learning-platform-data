# Managing Configuration with Azure App Configuration

A **Spring Boot** application typically has values that vary by environment: payment service timeout, retry count, data page size, order limits, new UI feature toggles, or internal service endpoints. When each value is duplicated across `application.yml`, Kubernetes manifests, App Service settings, or environment variables, operations teams easily run into **configuration drift**: production uses a different value from staging, one instance has not been updated, or the team has to rebuild and redeploy just to change a timeout.

**Azure App Configuration** provides a **centrally managed key-value store** with support for **labels**, **feature flags**, **snapshots**, application synchronization, and integration with **Azure Key Vault** to reference secrets. For Java, it can be accessed via the **Azure SDK for Java**; for Spring Boot, it can be integrated via **Spring Cloud Azure App Configuration** to load values into the Spring Environment and, depending on configuration, refresh certain values while the application is running.

This lesson belongs to the **Spring Boot on Azure** chapter in the **CLOUD_PROVIDERS_AZURE** module. Across the Azure learning path from subscriptions, resource groups, and Microsoft Entra ID to compute, networking, storage, and data, this is the configuration design stage to **deploy, operate, secure, monitor, and control costs** for applications consistently.

> **Core principle:** Azure App Configuration is a place to manage **application configuration**, not a store for distributing passwords. App Configuration can hold **Key Vault references**, but secret values must be protected with dedicated identities, Key Vault read permissions, networking, and logging policies. "Changing a key-value in the store" also **does not automatically** mean all Spring Boot instances have seen and applied the change immediately.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **local application.yml**, **environment variables**, **Azure App Configuration**, and **Azure Key Vault**.
2. Explain the structure of key-values, labels, content types, tags, ETags, feature flags, and snapshots.
3. Design naming conventions, scoping by application/environment/tenant, and precedence policies.
4. Choose Azure RBAC roles for **App Configuration Data Reader** and **App Configuration Data Owner**, as distinct from Azure control-plane permissions.
5. Create a store, key-values, and labels in a lab using the Azure Portal/CLI with demo data.
6. Configure the Java SDK to read configuration via **DefaultAzureCredential** or managed identity.
7. Integrate the **Spring Cloud Azure App Configuration starter** according to **Spring Boot/Spring Cloud Azure version compatibility**.
8. Bind configuration to **@ConfigurationProperties**, validate inputs, and avoid hard-coding.
9. Understand **refresh**, **sentinel keys**, **refresh intervals**, caching, and the difference between refreshing the environment and updating bean state.
10. Distinguish feature flags from regular config values and execute controlled rollouts.
11. Combine **Key Vault references** with separate workload access permissions without placing secrets inside the store.
12. Design fail-fast, stale-cache policies, startup fallbacks, and resilience against store outages.
13. Analyze private endpoints, DNS, VNet Integration, role propagation, and 401/403/404/429 errors.
14. Measure end-to-end propagation, logging, auditing, rollback, FinOps, and production testing.

## 2. Running Scenario: Orders API

Orders API runs on Azure App Service or AKS across three environments: **dev**, **staging**, and **prod**. Its parameters:

| Setting | Dev value | Prod value | Where to store? |
|---|---|---|---|
| Checkout timeout | 1500 ms | 800 ms | App Configuration |
| Retry count | 1 | 2 | App Configuration |
| Page size | 20 | 50 | App Configuration |
| Feature: new-checkout | enabled for QA | conditional rollout | App Configuration feature flag |
| Partner payment endpoint | sandbox URL | production URL | App Configuration if non-sensitive |
| Partner API key | demo secret | production secret | Key Vault |
| Instance port | platform-assigned | platform-assigned | Runtime/environment |
| Java heap limit | per host/container | per host/container | Runtime/deployment |
| Database password | not needed with Entra auth | legacy credential if required | Key Vault, or omit completely when using managed identity |

Changing "checkout timeout from 800 to 1000 ms" should not force packaging a new JAR. However, the change must still be **reviewed**, have an owner, be rolled out per environment, have a rollback path, and be verified for impact.

Architecture requirements:

- Configuration must be bound to the **right application and environment**.
- Production loads only the keys it is permitted to use.
- All instances must eventually converge on the desired configuration within the **propagation SLO**.
- Do not place connection strings containing secrets in App Configuration as plain text.
- Handle scenarios where App Configuration is temporarily unavailable.
- Emit telemetry so operators know which revision/version each instance is running.
- Do not grant write permissions to an application that only needs to read.

## 3. Reference Architecture Diagram

~~~mermaid
flowchart LR
    ENG["DevOps / IaC / operators"] --> STORE["Azure App Configuration<br/>keys + labels + feature flags"]
    STORE --> KVREF["Key Vault reference metadata"]
    KVREF --> KV["Azure Key Vault<br/>secret value"]
    MI["Microsoft Entra ID<br/>Managed Identity"] --> APP["Orders API<br/>Spring Boot"]
    APP --> SDK["Spring Cloud Azure<br/>or Java SDK"]
    SDK --> STORE
    SDK --> KV
    APP --> CLIENT["HTTP clients / checkout"]
    OBS["Azure Monitor / App Insights"] -. "metrics / audit" .-> APP
    OBS -. "diagnostics" .-> STORE
    SOURCE["Git + reviewed IaC"] --> ENG
~~~

**Management plane:** authorized operators or pipelines create stores, modify key-values/feature flags/labels, and manage versions/snapshots.

**Data plane:** the application authenticates with Entra ID, accesses the App Configuration endpoint using a reader role, retrieves key-values, and resolves Key Vault references when configured appropriately.

**Application layer:** the Spring Environment or a config service layer converts values into validated typed data, which Spring beans then use to drive behavior.

**Observability layer:** tracks configuration load failures, refresh timing, flag changes, applied revisions, and impact on business SLOs.

App Configuration **does not automatically push** every change into every live Java object. How changes take effect depends on the integration library, refresh activation, caching, and bean lifecycle.

## 4. How App Configuration Differs from Key Vault, application.yml, and Environment

| Tool | Role | Strengths | Limitations |
|---|---|---|---|
| Spring application.yml | Configuration packaged with JAR/environment | Simple, easy for local use | Changes typically require redeployment |
| Environment variables | Runtime/platform parameters, bootstrap | Ubiquitous in containers/App Service | Hard to synchronize/audit across many services |
| **Azure App Configuration** | Managing key-values, labels, feature flags | Centralized, metadata, dynamic refresh patterns | Remote dependency requiring auth/network |
| **Azure Key Vault** | Protecting secrets, keys, certificates | Data-plane authorization, audit, rotation | Not intended for every non-secret parameter |
| Azure App Configuration + Key Vault reference | Configuration + pointer to retrieve secrets | Secret values are not stored in App Config | Still requires roles/network to both services |
| Azure SQL/Cosmos DB | Business state and transactions | Queries/transactions, persistence | Should not be used as a config store unnecessarily |
| Kubernetes ConfigMap | Pod-scoped non-secret config | Native K8s deployment | Drift and rollout depend on cluster operations |
| Kubernetes Secret | K8s secret distribution | Pod integration | Requires protecting etcd/RBAC and separate rotation |

**Prefer direct managed identity** when Azure SQL/Storage/Service Bus supports Entra auth; in that case there is no need to store an account key in Key Vault just for "centralized configuration."

### 4.1. What Not to Put in App Configuration

- Passwords, access tokens, private keys, or shared secrets in plain text.
- Customer data or transaction records.
- Session state, cart state, and locking state.
- Values specific to each HTTP request/user that change continuously.
- Log payloads or continuously updated metrics.
- Configurations that strictly require instantaneous/atomic updates across all instances if the application lacks an appropriate coordination protocol.

## 5. Key-Value Structure and Metadata

An App Configuration entry is identified by **key + label**. Its value can be a string, JSON document, feature flag content, or Key Vault reference depending on its **content type**.

Example:

~~~text
key:         orders:checkout:timeout-ms
label:       prod
value:       800
contentType: text/plain
tags:
    owner=orders-team
    classification=internal
etag:        "revision-from-service"
~~~

### 5.1. Key

A **key** should express the application, area, and setting:

~~~text
orders:checkout:timeout-ms
orders:checkout:retry-count
orders:ui:page-size
orders:payments:endpoint-url
orders:sentinel
~~~

Delimiter conventions should align with the binding strategy. Choose an **application prefix** to make searching, permissions, and operations easier. Never embed PII, access tokens, or tenant secrets in key names.

### 5.2. Label

A **label** distinguishes a key by environment or intentional segment:

~~~text
key: orders:checkout:timeout-ms
label: dev       value: 1500
label: staging   value: 1100
label: prod      value: 800
~~~

A **null label** is an unassigned label, not the literal string **"null"**. A common strategy is:

- Null label: shared defaults.
- dev/staging/prod: environment overrides.
- Canary labels: only when clear selector/precedence design exists.
- Do not create dynamic labels for millions of users/requests.

**Precedence warning:** loading multiple selectors and overrides depends on the library and configuration; explicitly test loading order and conflict resolution. Never assume "label prod" automatically overrides the null label unless the integration is configured to do so.

### 5.3. Content type

Content type differentiates plain text from structured data:

~~~text
text/plain
application/json
application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8
application/vnd.microsoft.appconfig.ff+json;charset=utf-8
~~~

These MIME strings represent common types; verify exact supported syntax against the current API/library version.

### 5.4. Tags, ETag, last modified

Tags support operational metadata such as owner and classification, and do not replace access controls. **ETag** is a version stamp for conditional updates/optimistic concurrency when supported by the SDK/API. Last modified helps investigate changes, but is **not** an atomic deployment protocol across 20 keys.

### 5.5. Snapshot

A **Snapshot** captures a selected set of key-values at a point in time using App Configuration's snapshot feature, helping ensure an application loads a consistent configuration set with clear deployment provenance. A snapshot is an **immutable collection** per service semantics; creation, archiving, revoking, limits, and billing should be verified for the version in use.

Do not confuse:

- An App Configuration snapshot with a full Azure resource backup.
- A snapshot with a Git commit containing secrets.
- A snapshot with a dynamically changing feature flag rollout.

## 6. Naming Conventions, Environments, and Ownership

An organizational example:

~~~text
Application = orders
Environment = dev | staging | prod

Keys:
    orders:checkout:timeout-ms
    orders:checkout:retry-count
    orders:ui:page-size
    orders:payments:endpoint-url
    orders:sentinel

Feature names:
    new-checkout
    shipping-preview

Labels:
    <null>     defaults
    dev        dev overrides
    staging    preprod test
    prod       production overrides
~~~

### 6.1. One Store or Multiple Stores?

| Model | Pros | Cons |
|---|---|---|
| One shared store with environment labels | Simpler cost/administration, default reuse | Large blast radius if permissions are misconfigured |
| Separate stores for dev/staging/prod | Clear boundary, network, and RBAC isolation | More resources, higher cost/operational overhead |
| Separate store per business domain/application | Clear ownership and blast radius | Cross-app defaults require coordination |
| Separate store per tenant | Strong isolation in certain scenarios | Resource sprawl and operational complexity |

**Labels are not security boundaries.** If a principal holds data-reader permissions across the entire store, do not assume it can only read the prod label and not staging. When strict data separation is required by security policy, design appropriate **store/RBAC scopes** instead of relying on naming conventions.

### 6.2. Defining Ownership

- Product teams own business configuration and feature rollouts.
- Platform teams own stores, identity, networking, capacity, and IaC.
- Security teams define secret classification, access reviews, and auditing.
- SRE/operations own refresh SLOs, runbooks, and alerting.
- CI/CD pipelines hold scoped write access and undergo review.
- Application workloads hold **read-only** access and never mutate production config themselves.

## 7. How Feature Flags Differ from Regular Configuration

A **feature flag** represents the ability to toggle a feature or roll it out conditionally, such as **new-checkout**, rather than merely acting as a static boolean setting.

### 7.1. Decision Types

- **Boolean on/off:** enable or disable globally.
- **Time window:** enable only during a specified time interval.
- **Targeting:** enable for specific groups/users or percentages when supported by the feature management library.
- **Canary release:** enable for a small subset first.
- **Kill switch:** turn off a new feature when metrics degrade.

Support for filters, percentage rollouts, targeting, and feature usage analytics depends on App Configuration + the Feature Management library/version and the context passed by the application. A flag does not automatically know **userId** or permission groups unless the backend provides that context.

### 7.2. Feature Flag Example

A structured feature flag key-value carries **id, enabled, conditions**:

~~~json
{
  "id": "new-checkout",
  "description": "Experimental checkout flow",
  "enabled": true,
  "conditions": {
    "client_filters": []
  }
}
~~~

This payload is **illustrative** of the structure. In practice, create/edit flags via the Azure Portal or a compatible Feature Management SDK/CLI to avoid invalid content types or schemas.

### 7.3. Flag Cautions

- Flags **do not replace authorization**: even if a UI button is hidden, the API must still enforce permissions.
- A kill switch has refresh latency; it does not guarantee millisecond shutdown.
- Percentage rollouts require deterministic bucketing so users do not flip between states across requests.
- Stale flags should be cleaned up after rollout to reduce technical debt.
- When a feature involves schema/database migrations, turning the flag off does not automatically roll back the database.
- Flags must not be used to obscure sensitive data leaks or bypass mandatory policies.

## 8. Bootstrap and Configuration Source Precedence in Spring Boot

Spring Boot maintains an **Environment** that combines multiple PropertySources, such as `application.yml`, environment variables, system properties, command-line arguments, and sources added by integration libraries.

### 8.1. Bootstrap Is a Two-Stage Problem

To read App Configuration, the application first needs the **endpoint and credentials**. Those cannot live exclusively inside an App Configuration store that has not been connected yet.

A common design:

~~~text
Bootstrap / application config:
    APP_CONFIG_ENDPOINT
    identity method
    selectors/labels
    refresh/failure policy

Azure App Configuration:
    orders:checkout:timeout-ms
    orders:ui:page-size
    feature flags
    Key Vault reference metadata

Azure Key Vault:
    payment API key / legacy secret values
~~~

**The endpoint URI is not a secret.** If using an App Configuration connection string, the connection string may contain credentials and must be stored and passed through a secure secret mechanism. For Azure workloads, **managed identity + endpoint** is generally the preferred choice.

### 8.2. Spring Cloud Azure Integration

The Spring Cloud Azure App Configuration starter can add a **PropertySource** to the Spring Environment and provide binding and refresh patterns. However:

- Property names and bootstrap mechanisms differ across **Spring Boot major versions, Spring Cloud Azure versions, and Spring Cloud compatibility**.
- Documentation for one version may use **bootstrap.yml**, while another uses **spring.config.import** or a corresponding bootstrap starter.
- Never copy config keys from one library generation into another project without checking the version matrix.
- The low-level SDK does not automatically convert key-values into Spring properties; that is the responsibility of the integration layer or custom code.

### 8.3. Precedence Must Be Tested

Suppose the same property exists in `application.yml`, an environment variable, and App Configuration. The final value depends on PropertySource ordering and naming/binding rules.

Write an integration test verifying that:

1. Default local config loads.
2. App Configuration null-label keys load.
3. The environment label (prod) overrides the intended keys.
4. Environment overrides are permitted or blocked according to policy.
5. When a source fails, fallback is intentional rather than silently using an unsafe default.

Do not claim a single universal precedence order across all Spring Boot/Spring Cloud Azure releases.

## 9. Choosing Java Tools for App Configuration

| Implementation option | When appropriate | Watch-outs |
|---|---|---|
| **Azure SDK for Java: azure-data-appconfiguration** | Custom control over key-values, retrieval, and caching | Must manually map to Spring config/refresh |
| **Spring Cloud Azure App Configuration starter** | Spring Boot apps needing Environment binding | Check version compatibility |
| **Feature Management library** | Feature flags/targeting/conditional gates | Context/filters and refresh behavior |
| **Azure Portal/CLI** | Operators creating key-values and running labs | Correct roles, auditing, networking |
| **IaC + release automation** | Managing stores/labels/snapshots via pipelines | Secret separation, drift detection |
| **Key Vault references** | Config pointing to protected secrets | Separate roles/network to Key Vault |

This lesson covers both the **low-level SDK** (with concrete Java APIs) and **Spring Boot integration** (version-sensitive) so learners understand feature boundaries rather than assuming a starter magically handles every refresh and feature flag pattern.

## 10. Azure CLI Lab: Creating a Store and Label Configuration

The following commands are **illustrative instructions**; no Azure resources were created when authoring this lesson. App Configuration incurs quotas and charges depending on tier; use a lab subscription, budget, and dedicated resource names.

### 10.1. Create a Store

~~~bash
az login
az account set --subscription "<lab-subscription-id>"

RG="rg-appconfig-spring-lab"
LOCATION="southeastasia"
STORE="<unique-appconfig-store-name>"

az group create --name "$RG" --location "$LOCATION"

az appconfig create \
  --name "$STORE" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard

az appconfig show \
  --name "$STORE" \
  --resource-group "$RG" \
  --output table
~~~

**Standard** is used as a lab illustration, not a universal recommendation for every organization. Verify current tiers/regions, features, and pricing. Endpoints usually take the form **https://store-name.azconfig.io**; the endpoint itself is not a credential, whereas connection strings and access keys may contain secrets.

### 10.2. Assign Data-Plane Roles

Common roles:

| Role | Purpose | Identity |
|---|---|---|
| **App Configuration Data Reader** | Read key-values/flags | Spring Boot runtime |
| **App Configuration Data Owner** | Write/manage key-values at the data plane | Approved CI/CD or operator |
| Azure resource Contributor | Manage the resource at the control plane | Platform/IaC; does not automatically grant data-plane access |

Someone authorized to create role assignments can grant write access to a developer **in a lab only**:

~~~bash
STORE_ID=$(az appconfig show \
  --name "$STORE" \
  --resource-group "$RG" \
  --query id --output tsv)

USER_ID=$(az ad signed-in-user show \
  --query id --output tsv)

az role assignment create \
  --assignee-object-id "$USER_ID" \
  --assignee-principal-type User \
  --role "App Configuration Data Owner" \
  --scope "$STORE_ID"
~~~

In production, grant **Data Reader** to the application's managed identity—never Data Owner just to read. Role propagation can take time; do not immediately widen permissions if you see a 403.

### 10.3. Create Non-Secret Keys

Use dot-separated keys for straightforward mapping into Spring Boot:

~~~bash
az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.timeout-ms" \
  --label "prod" --value "800" --yes

az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.retry-count" \
  --label "prod" --value "2" --yes

az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.ui.page-size" \
  --label "prod" --value "50" --yes

az appconfig kv set \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.timeout-ms" \
  --label "dev" --value "1500" --yes
~~~

CLI options depend on the extension version; check **az appconfig kv set --help** before automating. **--auth-mode login** instructs the CLI to use Microsoft Entra identity instead of retrieving an access key.

### 10.4. Inspect Demo Values and Labels

~~~bash
az appconfig kv show \
  --name "$STORE" --auth-mode login \
  --key "orders.checkout.timeout-ms" \
  --label "prod" \
  --query "{key:key,label:label,value:value}" \
  --output json
~~~

Here the value **800** is non-sensitive. Never print or retrieve values containing real API keys in terminal output. For a null label, omitting the label flag has specific semantics; do not pass the literal string **"null"** in place of a null label.

### 10.5. Feature Manager and Snapshots in the Portal

In the Azure Portal, open the store:

1. **Configuration Explorer:** create key-values and labels.
2. **Feature Manager:** create the **new-checkout** flag and inspect conditional targeting if supported by your feature version.
3. **Snapshots:** create reviewed snapshot configuration sets if supported by your tier/feature set.
4. **Access control (IAM):** assign the data-reader role to the runtime identity.
5. **Networking:** apply public firewall rules or a Private Endpoint per policy.
6. **Diagnostic settings:** enable necessary logs and metrics.

Do not assume a preview CLI command for creating snapshots or feature flags works identically across all CLI versions; verify in the Portal first, then turn it into tested automation.

## 11. Low-Level Java SDK: azure-data-appconfiguration

When you need to read keys on demand or manage caching and refresh yourself, use **ConfigurationClient** from **com.azure:azure-data-appconfiguration** and **TokenCredential** from **com.azure:azure-identity**.

### 11.1. Maven Dependencies

~~~xml
<dependencies>
  <!-- Manage versions via Azure SDK BOM or pin approved versions. -->
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-data-appconfiguration</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
</dependencies>
~~~

This is a **POM fragment**; it requires the Azure SDK BOM/explicit versions and the rest of a valid Maven project. **The low-level Azure SDK does not automatically add a PropertySource to the Spring Environment**; that requires separate integration.

### 11.2. Reading a Labeled Key in Java

~~~java
package com.example.orders.config;

import com.azure.core.credential.TokenCredential;
import com.azure.data.appconfiguration.ConfigurationClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.data.appconfiguration.models.ConfigurationSetting;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class AppConfigReadDemo {
    public static void main(String[] args) {
        String endpoint = System.getenv("APP_CONFIG_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException(
                "APP_CONFIG_ENDPOINT is required");
        }

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        ConfigurationClient client =
            new ConfigurationClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildClient();

        ConfigurationSetting setting =
            client.getConfigurationSetting(
                "orders.checkout.timeout-ms", "prod");

        String value = setting.getValue();
        int timeoutMs = Integer.parseInt(value);

        if (timeoutMs < 100 || timeoutMs > 10000) {
            throw new IllegalStateException(
                "Checkout timeout out of permitted range");
        }

        // Only print non-sensitive demo configuration.
        System.out.println("Configured timeout: " + timeoutMs);
    }
}
~~~

Notes:

- **DefaultAzureCredential** selects a credential source according to the SDK/runtime chain; a local Azure CLI account may differ from an Azure workload's managed identity.
- Only an identity with **Data Reader** at the right scope and allowed networking can succeed.
- Java handles parsing and validation; never treat a raw string value as inherently safe.
- Handle 401/403/404/429 errors and timeouts in production.
- Reuse the client instance instead of creating one on every HTTP request.
- Never print secret values or embed an admin connection string in source code.

### 11.3. Listing by Prefix

~~~java
import com.azure.data.appconfiguration.models.SettingSelector;
import com.azure.data.appconfiguration.models.ConfigurationSetting;

SettingSelector selector = new SettingSelector()
    .setKeyFilter("orders.*")
    .setLabelFilter("prod");

for (ConfigurationSetting item :
        client.listConfigurationSettings(selector)) {
    // Inspect metadata; do not log full values.
    String key = item.getKey();
    String label = item.getLabel();
    System.out.println("Loaded metadata for key " + key);
}
~~~

This snippet reuses the **client** created earlier. Queries may paginate and trigger multiple HTTP requests. Never list the entire store on every HTTP request. Keep in mind that key names themselves may be sensitive in some organizations.

### 11.4. Updating a Key-Value in an Operator Tool

~~~java
import com.azure.data.appconfiguration.models.ConfigurationSetting;

ConfigurationSetting item = new ConfigurationSetting()
    .setKey("orders.checkout.timeout-ms")
    .setLabel("dev")
    .setValue("1500");

client.setConfigurationSetting(item);
~~~

**Only an operator/CI identity with Data Owner** should perform writes against an appropriate store. When multiple writers can update the same key, consider **ETag-based conditional writes**/optimistic concurrency via the SDK to prevent unintended overwrites.

## 12. Spring Cloud Azure App Configuration Starter

For Spring Boot, integrating at the **Spring Environment** layer enables binding configuration to **@ConfigurationProperties**. Pin all three version groups:

- Spring Boot.
- Spring Cloud/Spring Cloud Azure release train.
- Java and Azure SDK dependencies.

Property names and bootstrap patterns can differ between generations. Never treat a random snippet found online as guaranteed to work on every Spring Boot version.

### 12.1. Maven BOM Pattern

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure.spring</groupId>
      <artifactId>spring-cloud-azure-dependencies</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_RELEASE</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-appconfiguration-config</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
</dependencies>
~~~

This is a **POM fragment**: you still need the Spring Boot parent/dependency management and must replace the placeholder with a compatible release verified against Microsoft's version matrix. Do not expect Maven to run with placeholders left intact.

### 12.2. Configuration Structure Example

A typical Spring Cloud Azure App Configuration setup:

~~~yaml
# Illustrative pattern: verify property/activation names for the version in use.
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "https://example-appconfig.azconfig.io"
            selects:
              - key-filter: "orders.*"
                label-filter: "prod"
~~~

In real deployments, the endpoint and label are injected from the deployment environment, such as **APP_CONFIG_ENDPOINT** and **APP_CONFIG_LABEL**. Depending on the release, early loading may use **bootstrap.yml**, **spring.config.import**, or an appropriate bootstrap starter; consult the **versioned reference** rather than mixing two approaches blindly.

### 12.3. Selecting Labels per Environment

A standard pattern:

~~~text
APP_CONFIG_ENDPOINT = https://<your-store>.azconfig.io
APP_CONFIG_LABEL    = dev | staging | prod
APP_CONFIG_PREFIX   = orders.
~~~

Bootstrap configuration should obtain the label from the deployment environment or an approved profile. For production, **a missing prod label must fail validation**, never silently fall back to dev.

### 12.4. Key Delimiters in Spring

To bind directly into fields like **timeoutMs**, prefer keys such as **orders.checkout.timeout-ms**. Other examples using colons like **orders:checkout:timeout-ms** may require key transformation/trimming; do not assume the Spring starter automatically converts colons to dots.

### 12.5. Testing Precedence

When the same property exists in `application.yml`, environment variables, and App Configuration, precedence depends on Spring PropertySources and the integration library. Add integration tests verifying:

1. Which local fallbacks are permitted.
2. Whether null-label defaults are loaded.
3. Whether the prod/staging environment label overrides as expected.
4. Whether environment variables are permitted to override remote config.
5. Whether the app fails fast or falls back to last-known-good when the remote store errors.

**Never claim a universal precedence order** across all Spring Boot/Spring Cloud Azure versions.

## 13. @ConfigurationProperties: Typed and Validated Configuration

### 13.1. From Key-Values to a Java Bean

Given keys:

~~~text
orders.checkout.timeout-ms = 800
orders.checkout.retry-count = 2
~~~

Bean:

~~~java
package com.example.orders.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "orders.checkout")
public class CheckoutProperties {
    @Min(100)
    @Max(10000)
    private int timeoutMs = 800;

    @Min(0)
    @Max(5)
    private int retryCount = 1;

    public int getTimeoutMs() { return timeoutMs; }
    public void setTimeoutMs(int value) { this.timeoutMs = value; }

    public int getRetryCount() { return retryCount; }
    public void setRetryCount(int value) { this.retryCount = value; }
}
~~~

Register with **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties**:

~~~java
package com.example.orders;

import com.example.orders.config.CheckoutProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CheckoutProperties.class)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

### 13.2. Using Typed Configuration

~~~java
package com.example.orders.service;

import com.example.orders.config.CheckoutProperties;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final CheckoutProperties config;

    public CheckoutService(CheckoutProperties config) {
        this.config = config;
    }

    public int configuredTimeoutMs() {
        return config.getTimeoutMs();
    }
}
~~~

This example focuses on strongly typed config and omits the HTTP client implementation. If a timeout changes, verify that the bean/client actually reads the new property or gets rebuilt; an already initialized HTTP connection pool may retain the old timeout.

### 13.3. Validation on Startup and Refresh

- Allow timeouts only within safe bounds.
- Keep retry counts bounded, especially when payment POST calls are non-idempotent.
- Validate endpoint URLs against an allowed scheme/host whitelist.
- Missing required critical settings should fail startup if no approved fallback exists.
- On refresh, **also validate** new values before applying them to live traffic.
- Write integration tests because binding/refresh semantics depend on the starter version.

## 14. Default Labels, Overrides, and Blast Radius

An illustrative policy:

~~~text
orders.checkout.timeout-ms [no label] = 1000
orders.checkout.timeout-ms [dev]      = 1500
orders.checkout.timeout-ms [staging]  = 1100
orders.checkout.timeout-ms [prod]     = 800
~~~

Loading defaults followed by overrides requires explicitly configured selectors and precedence; **it does not mean App Configuration automatically prefers prod** if the caller does not specify a label.

**Labels are not security boundaries.** A data reader at store scope can read multiple labels allowed by the role. When dev/prod access requires strict isolation, use separate stores, identities, and networks instead of hoping label names stop unauthorized readers.

When a critical production value is missing, choose fail-safe behavior. Never let a dev default act as an unlogged silent fallback.

## 15. Refreshing Configuration at Runtime

A major strength of App Configuration is managing values centrally **without rebuilding the JAR**, yet **dynamic refresh** is a multi-step process:

~~~mermaid
sequenceDiagram
    participant O as Operator / CI
    participant AC as App Configuration
    participant REF as App refresh monitor
    participant SPR as Spring Environment
    participant B as Business bean
    O->>AC: Update key-values
    O->>AC: Update sentinel last
    REF->>AC: Poll/check trigger after interval
    AC-->>REF: Changed ETag/setting
    REF->>AC: Reload selected configuration
    AC-->>REF: New values
    REF->>SPR: Update PropertySources
    SPR->>B: Rebind/recreate only if supported
    B-->>B: New behavior after validation
~~~

**Never assume** App Configuration sends a direct, instantaneous push to every JVM. Refresh is typically checked via application/library activity, subject to a minimum refresh interval, selected keys, and version-specific caching. A low-traffic instance may apply changes more slowly when refresh is request-driven.

### 15.1. Milestones to Distinguish

| Milestone | Meaning |
|---|---|
| **SettingUpdated** | Operator/CI has written to App Configuration |
| **SentinelUpdated** | The store carries a signal that a batch of changes is complete |
| **RefreshChecked** | An instance checked for changes per policy |
| **PropertySourceUpdated** | Remote values have been loaded into the Spring Environment |
| **BeanApplied** | The Java component is actively using the new value |
| **BusinessMetricVerified** | Observed post-change behavior matches SLO |

Simply seeing CLI **kv set** return success does not prove every instance has applied the configuration.

### 15.2. Sentinel Key

Suppose you want to change three settings together:

~~~text
orders.checkout.timeout-ms [prod] = 800
orders.checkout.retry-count [prod] = 2
orders.ui.page-size [prod]        = 50
orders.settings.revision [prod]    = "2026-11-20-release-1"
~~~

When deploying a new revision:

1. Create/write the related key-values.
2. Validate inputs, types/ranges, and dependencies.
3. **Update the sentinel last** once all data is ready.
4. Instances check the sentinel per the polling policy.
5. When the sentinel changes, refresh the selected configuration.
6. Validate and apply to refresh-aware beans.
7. Track which revision each instance has applied.

A sentinel reduces the chance of clients observing partial key updates, but **does not create an ACID transaction across all clients/instances**. For configs demanding strict atomic consistency, consider **immutable snapshots + explicit promotion** and readiness gating.

### 15.3. Refresh Interval and Quotas

Conceptual refresh configuration pattern:

~~~yaml
# Pseudoconfiguration: property names and bootstrap source
# MUST be verified against the selected Spring Cloud Azure release.
app-config-refresh-policy:
  store: "orders-appconfig"
  environment-label: "prod"
  enabled: true
  sentinel-key: "orders.settings.revision"
  min-check-interval: "30s"
  change-behavior: "reload-selected-keys"
~~~

This is **not** a Spring Cloud Azure starter configuration namespace—do not paste it verbatim into `application.yml` expecting the starter to parse it. It highlights the concepts to look up in your release's documentation: **monitoring.enabled**, **triggers**, **refresh-interval**, **watch keys**, and how refresh is triggered.

To configure the starter directly, check properties along the lines of:

~~~text
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key
spring.cloud.azure.appconfiguration.stores[0].monitoring.refresh-interval
~~~

**Compatibility warning:** exact property names, selects/triggers layout, and refresh execution mechanics are **version-sensitive**; do not treat the lines above as pre-tested config. Consult the versioned Spring Cloud Azure docs and add integration tests on your pinned release.

### 15.4. RefreshScope and Bean Lifecycle

In some Spring Cloud setups, **@RefreshScope** allows recreating a bean upon a refresh signal. Spring Cloud Context example (when that dependency is installed):

~~~java
package com.example.orders.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class DynamicCheckoutTimeout {
    private final int timeoutMs;

    public DynamicCheckoutTimeout(
        @Value("${orders.checkout.timeout-ms}") String rawSetting) {
        // Read from Spring Environment at bean creation time.
        this.timeoutMs = Integer.parseInt(rawSetting);
    }

    public int timeoutMs() {
        return timeoutMs;
    }
}
~~~

**Note:** this example uses Spring's **@Value** placeholder syntax. It requires Spring Cloud Context supporting **@RefreshScope**, a loaded property source, and a corresponding refresh trigger. This snippet alone does not prove the starter emits a refresh signal automatically; verify **PropertySources and refresh context** on your exact release. You can substitute **CheckoutProperties** when binding typed settings.

A more predictable pattern in sensitive systems is an immutable validated **ConfigSnapshot** swapped via an **AtomicReference**:

~~~java
package com.example.orders.config;

public record ConfigSnapshot(int timeoutMs, int retryCount,
                             String revision) {
    public ConfigSnapshot {
        if (timeoutMs < 100 || timeoutMs > 10000) {
            throw new IllegalArgumentException("timeoutMs");
        }
        if (retryCount < 0 || retryCount > 5) {
            throw new IllegalArgumentException("retryCount");
        }
    }
}
~~~

~~~java
package com.example.orders.config;

import java.util.concurrent.atomic.AtomicReference;

public final class DynamicConfig {
    private final AtomicReference<ConfigSnapshot> current;

    public DynamicConfig(ConfigSnapshot initial) {
        this.current = new AtomicReference<>(initial);
    }

    public ConfigSnapshot snapshot() {
        return current.get();
    }

    public void installValidated(ConfigSnapshot candidate) {
        // Candidate has already been validated in the record constructor.
        // Each request can hold a consistent snapshot.
        current.set(candidate);
    }
}
~~~

This model makes the boundary between **"loading a new config set" → "atomically swapping the in-process reference"** explicit. However, multiple JVM instances still apply updates at different times; cross-instance coordination requires its own protocol or rollout strategy.

### 15.5. Impact on HTTP Clients and Resources

A new timeout does not necessarily affect an existing **WebClient/RestClient/connection pool**:

- If the timeout is read per call via a config holder → it may take effect immediately.
- If the HTTP client was built at startup with the old timeout → it must be recreated or its connector adjusted per API capabilities.
- When changing endpoints/base URLs, account for in-flight requests.
- When changing DB pool sizes, merely changing a property does not guarantee the pool resizes itself.
- Critical changes call for canary/rolling restarts if hot refresh is hard to verify.

## 16. Controlling Multi-Key Consistency

### 16.1. Partial Update Risk

Suppose a system currently has:

~~~text
orders.checkout.endpoint = https://partner-v1.example
orders.checkout.api-version = v1
~~~

An operator updates the endpoint first and the API version second. An instance refreshing in between may end up with **endpoint v2 + api-version v1**, causing failures.

### 16.2. Strategy A: Sentinel Updated Last

Pros: simple, fits changes safe to refresh at the end of a batch. Limitation: key-values are still written individually; an app ignoring the sentinel or triggered by another refresh path could still observe partial state.

### 16.3. Strategy B: Immutable Snapshot

Create a validated snapshot and promote a single snapshot/revision reference to the application when supported by your tier/features.

~~~text
snapshot orders-prod-2026-11-20-r1
    endpoint v2
    api-version v2
    checkout timeout 800ms

release manifest references snapshot r1
~~~

The application loads a consistent collection for a release, then canaries forward to r2. Snapshots trade off some dynamic update flexibility in exchange for strong reproducibility and clean rollbacks.

### 16.4. Strategy C: Typed JSON Document

Instead of 5 independent keys, you can store a single JSON config object and validate the entire payload before an in-process atomic swap:

~~~json
{
  "endpoint": "https://partner.example.invalid",
  "apiVersion": "v2",
  "timeoutMs": 800,
  "retryCount": 2,
  "revision": "orders-checkout-r2"
}
~~~

However, large JSON blobs reduce per-property/per-label override flexibility and can complicate Spring binding. Choose this only when an **atomic unit** is required and schema/version migration is handled.

### 16.5. Rollback

Rollback is not just "re-typing the old timeout"—you need to know **which set of keys** and which release were previously active. Use snapshots, versioned release manifests, or IaC source-of-truth to roll back consistently.

## 17. Feature Flags in Spring Boot

### 17.1. A Boolean Config Is Not a Feature-Management Framework

If you only need a simple switch:

~~~text
orders.checkout.new-flow-enabled [prod] = false
~~~

Spring can bind the boolean and a controller/service can inspect it. However, this approach **lacks** targeting, percentage rollouts, scheduling, or full experiment auditing.

With a **proper feature flag**, App Configuration Feature Manager defines the flag and conditions, while the Spring Cloud Azure Feature Management package/library evaluates filters according to the release version.

### 17.2. Rollout Workflow

~~~mermaid
flowchart TD
    DEV["Deploy code: old + new paths"] --> FLAG["Create flag: new-checkout"]
    FLAG --> QA["Enable for QA / dev"]
    QA --> CANARY["Canary subset / percentage"]
    CANARY --> METRIC["Measure errors, latency, conversion"]
    METRIC --> DEC{"SLO acceptable?"}
    DEC -->|Yes| EXPAND["Expand to more users"]
    DEC -->|No| OFF["Disable feature flag"]
    EXPAND --> CLEAN["Remove flag after rollout"]
~~~

**Turning a flag off** incurs latency determined by your refresh mechanism and implementation. Never promise a "sub-1-second kill switch" if the system only polls every 60 seconds.

### 17.3. Feature Context and Targeting

To target users or groups:

- The backend must obtain `userId` from an authenticated session.
- Group/role names must come from validated identity/authorization data.
- Percentage bucketing must be deterministic for the same user to avoid flickering behavior.
- Having a feature flag enabled **does not grant authorization** to view documents or invoke sensitive APIs.
- Every server-side route must still enforce authorization.

### 17.4. Do Not Couple Breaking Schema Migrations to a Simple Flag

If the new checkout feature introduces a non-backward-compatible DB schema change, flipping the flag off will not roll back the database. Use **expand–migrate–contract** or backward-compatible migrations alongside controlled rollouts.

### 17.5. Testing

Always test:

1. Flag absent → safe default.
2. Flag disabled → old path.
3. Flag enabled → new path.
4. Unauthorized target group → access still denied.
5. Slow flag refresh → clear transitional behavior.
6. Two instances receiving the flag at different times → no protocol breakage.
7. Flag cleanup after the release concludes.

## 18. Key Vault References: Configuration and Secrets Are Two Services

### 18.1. Why Not Store API Keys in App Configuration?

If you store a plain value:

~~~text
orders.payment.api-key = REAL_PAYMENT_API_KEY
~~~

Then any principal able to read App Configuration can read the credential, and configuration dumps or debug responses risk leaking it. That violates secret isolation.

Replace it with a **Key Vault reference**:

~~~text
App Configuration key:
    orders.payment.api-key

Content type:
    application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8

Value (reference JSON):
    {"uri":"https://<vault-name>.vault.azure.net/secrets/orders-payment-key/"}
~~~

**App Configuration stores the reference URI, not the plaintext secret.** Still, URIs and secret names can reveal metadata and should be kept out of unnecessary logs.

### 18.2. Secret Retrieval Flow

~~~mermaid
sequenceDiagram
    participant APP as Spring Boot
    participant AC as App Configuration
    participant ID as Entra Identity
    participant KV as Key Vault
    APP->>ID: Acquire credentials
    APP->>AC: Read key-value reference
    AC-->>APP: Key Vault reference URI
    APP->>KV: Resolve secret with allowed identity
    KV-->>APP: Secret value
    APP->>APP: Use secret in server-side component
~~~

This diagram illustrates the model: resolution is performed by the integration layer if configured, or by custom code when using the low-level SDK directly.

### 18.3. Two Permission Sets Are Required

| Service | Data-plane permission | Purpose |
|---|---|---|
| App Configuration | **App Configuration Data Reader** | Read reference key-values |
| Key Vault | **Key Vault Secrets User** or get permission per model | Retrieve secret values |
| Microsoft Entra ID | Valid workload identity | Acquire appropriate tokens for both |
| Networking | Routes + firewall/private endpoint/DNS | HTTPS connectivity to both services |

**Data Reader on App Configuration does not grant Key Vault read access.** Conversely, Key Vault Secrets User does not permit reading App Configuration.

### 18.4. Low-Level SDK Does Not Resolve References Automatically

When calling **ConfigurationClient.getConfigurationSetting** on a Key Vault reference setting, the low-level SDK returns a **ConfigurationSetting** containing the content type and JSON reference—it **does not automatically resolve the JSON into the secret value**.

To consume the secret:

- Enable **Spring Cloud Azure App Configuration Key Vault reference resolution** if supported and explicitly configured for your release.
- Or safely parse the reference URI and use **SecretClient** from `azure-security-keyvault-secrets` with dedicated permissions.
- Never mint overly broad credentials or accept arbitrary URIs from untrusted users.
- Validate allowed vault hosts/tenants/environments to prevent requests to unintended vaults.

### 18.5. Secret Rotation and Config Refresh Have Separate Lifecycles

- An App Configuration reference may continue pointing to a **versionless Key Vault URI**.
- Key Vault creates a new secret version.
- Spring integration or application caches might not have refreshed the secret yet.
- TokenCredential caching is not the same as secret value caching.
- If a version-pinned URI is used, the app continues reading the old version.
- Rotation also requires activating the new credential on the partner system.

Define separate SLOs for **config refresh** and **secret rotation propagation**. Never conflate the two mechanisms.

### 18.6. Handling Key Vault Errors

If App Configuration succeeds but Key Vault returns 403, inspect **Key Vault roles/networking**—do not grant App Configuration Data Owner. Policy may dictate failing startup, briefly retaining last-known-good, or disabling the secret-dependent route; never hard-code a backup secret in code.

## 19. Authentication and Authorization with Microsoft Entra ID

### 19.1. Local Development

On a developer workstation:

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table
~~~

In Java, **DefaultAzureCredential** can pick up a developer identity from Azure CLI or other sources in the SDK-defined credential chain. If the environment has multiple credential variables or IDE accounts, the active principal may not be the one you just signed into via `az login`.

**Having an Entra token is not enough:** the identity must hold **App Configuration Data Reader** (or the appropriate role) on the store and be permitted by networking rules.

### 19.2. App Service System-Assigned Identity

Steps:

1. Enable system-assigned managed identity on the App Service.
2. Retrieve the managed identity's **principal object ID** (do not confuse with client ID).
3. Assign **App Configuration Data Reader** on the store or supported scope.
4. If using Key Vault references, assign **Key Vault Secrets User** / get permission at the vault.
5. Set **APP_CONFIG_ENDPOINT** and the environment label.
6. Verify outbound VNet routing and private DNS if the store is private.
7. Deploy the Spring Boot app.
8. Verify identity principal, loaded config, refresh behavior, and audit logs.
9. Keep connection strings out of Git and App Service logs.

### 19.3. User-Assigned Managed Identity

When a workload uses a user-assigned identity or has multiple identities, explicitly pass the **client ID** to the credential chain as supported by your library version. Never assign a role to one principal and configure the app with another principal's client ID.

### 19.4. AKS Workload Identity

On AKS, prefer **Microsoft Entra Workload ID** where supported by your organization:

- Kubernetes ServiceAccount carries the proper annotations/config.
- Federated identity credential matches issuer/subject/audience.
- Workload token is mounted properly and readable by the Azure Identity SDK.
- App Configuration role is assigned to the actual Entra principal.
- If using Key Vault references, grant data-plane permission on the vault as well.
- Network paths to both endpoints are valid.

Never bake static connection strings into images, ConfigMaps, or shared Kubernetes Secrets just to bypass workload identity.

### 19.5. CI/CD Writer vs. Runtime Reader

| Principal | Target permissions |
|---|---|
| App runtime identity | App Configuration Data Reader |
| CI/CD config promotion identity | Scoped App Configuration Data Owner, only when approved |
| IaC resource deployment principal | ARM resource create/manage, scoped role assignments |
| Secret rotation identity | Key Vault secret write/management, kept separate from app reader |
| Human operator | JIT/PIM and auditing per policy |

A pipeline authorized to write production configuration can alter business behavior across the entire service. Enforce approvals, branch protection, four-eyes review, and change logging.

## 20. Networking: Private Endpoint, Firewalls, and DNS

### 20.1. App Configuration Endpoints Remain FQDNs

Applications access endpoints of the form:

~~~text
https://<store-name>.azconfig.io
~~~

When using a **Private Endpoint**, DNS inside the VNet must resolve this hostname to the private IP per Private Link rules. The corresponding Private DNS zone is typically:

~~~text
privatelink.azconfig.io
~~~

Always use the proper FQDN so TLS hostname/certificate validation works. **Never replace the client endpoint with a raw private IP** and disable certificate verification.

### 20.2. Network Flow Diagram

~~~mermaid
flowchart TB
    APP["Spring Boot app<br/>App Service / AKS"] --> DNS["VNet DNS resolver"]
    DNS --> PE["App Configuration Private Endpoint"]
    PE --> AC["Azure App Configuration"]
    APP --> EN["Microsoft Entra token endpoint"]
    APP --> KVPE["Key Vault Private Endpoint<br/>if using references"]
    KVPE --> KV["Azure Key Vault"]
    OBS["Azure Monitor"] -. "diagnostics" .-> AC
~~~

### 20.3. App Service VNet Integration vs. App Service Private Endpoint

- **VNet Integration** provides an outbound path from App Service into a VNet/private resources.
- **App Configuration Private Endpoint** is the private endpoint used by the application to reach the store.
- **App Service Private Endpoint** configures inbound private access to the web app itself.
- Network security groups, route tables, Azure Firewall, and DNS each play distinct roles.

Do not merely enable a private endpoint on App Configuration and assume a public App Service without VNet Integration can reach it.

### 20.4. Firewall Denials and HTTP 403

A 403 can occur when:

- The identity has a token but lacks the data-plane role.
- The app is using a different principal or tenant than intended.
- Store auth mode mismatches the client method.
- Firewall/network policies reject the request.
- The feature or tier disallows the request path.

Inspect error details, request IDs, network diagnostics, and the active principal. Never "fix" it by granting Owner or opening public access to the entire internet.

### 20.5. Key Vault References Require a Second Network Path

Successfully reading a **reference URI** from App Configuration does not guarantee secret retrieval will succeed. You also need:

- Key Vault hostname/private DNS, typically involving **privatelink.vaultcore.azure.net**.
- Outbound network path to Key Vault.
- Microsoft Entra token and Key Vault data-plane permission.
- Proper vault RBAC or access policy configuration.
- Dedicated secret refresh/cache/rotation handling.

A 403 from **Key Vault** cannot be "fixed" by assigning App Configuration Data Owner.

## 21. Startup Failures and Fallback Policies

App Configuration is a remote dependency. A Java workload can fail startup if:

- The store endpoint is wrong.
- Role assignments have not propagated yet.
- Private DNS is not working.
- A critical key-value does not exist under the selected label.
- The value cannot be parsed into the expected Java type.
- A Key Vault reference fails authorization.
- The store or network is temporarily unavailable.

### 21.1. Three Strategies

| Policy | Behavior | When appropriate |
|---|---|---|
| **Fail fast** | Refuse to start when critical config fails to load | Payment/authorization/security-critical apps |
| **Use approved local defaults** | Run with reviewed local defaults | Optional UX settings; must not weaken security |
| **Last-known-good** | Temporarily use previously validated config | High-availability apps with defined stale windows |

**Last-known-good** requires explicit policies for TTL, secure storage, and invalidation. It does not appear automatically just by adding the Spring Cloud Azure library; verify support or design it explicitly.

### 21.2. Fail-Open Is Dangerous for Security Settings

If **orders.checkout.fraud-check-enabled** fails to load, defaulting to `false` could disable security checks. For security-sensitive settings, **fail closed** or use a business-approved safe fallback.

### 21.3. Readiness vs. Liveness

Do not put "call App Configuration GET" inside a **liveness probe running every few seconds**. During a store outage, all pods could restart simultaneously and trigger a retry storm. Liveness checks process health; readiness checks whether the app holds sufficient config/state to serve traffic safely.

If the app already holds validated config and policy allows continuing for a bounded window, it can remain ready. Without critical config, mark readiness false or fail startup per policy.

### 21.4. Refresh Failures

When refresh fails:

1. Retain the previous validated active snapshot if permitted.
2. Record metrics and sanitized diagnostics.
3. Retry within a bounded budget and backoff.
4. Never publish partially parsed or invalid state.
5. Alert when the active config's age exceeds the allowed stale SLO.
6. Upon recovery, inspect both the sentinel and selected values.
7. Emit the newly applied revision to telemetry.

Never silently reset configuration back to dev defaults just because the store is unreachable.

## 22. Race Conditions and Multi-Instance Fleets

### 22.1. Instances Converge at Different Times

~~~text
10:00:00 Operator updates timeout in store
10:00:10 Instance A refreshes → timeout=1000ms
10:00:20 Instance B still holds 800ms
10:00:50 Instance B refreshes → timeout=1000ms
~~~

For 40 seconds, identical requests can experience different behavior depending on load balancer routing. If the system cannot tolerate skew, do not rely solely on naive hot config refresh.

### 22.2. Approaches When Stronger Consistency Is Needed

- Canary or rolling deployments pinned to **immutable snapshots/versions**.
- Keep a feature disabled until all instances report loading the target revision.
- Release gates checking instance-reported revisions against the SLO.
- Restrict live changes to backward-compatible settings that tolerate mixed versions.
- For parameters requiring system-wide atomicity, use a dedicated coordination/transaction protocol rather than relying on cache refresh.

### 22.3. Avoiding Stampedes

If 500 instances simultaneously query App Configuration and Key Vault after a sentinel update:

- API operations and throttling risk spike.
- Use minimum refresh intervals and jitter where supported by the SDK/library.
- Cap concurrent refresh operations.
- Never refresh all keys on every business request.
- Never issue unbounded GET retries when throttled with 429.
- Snapshots/versioning help reduce overly frequent updates.

### 22.4. ETag Does Not Make Multi-Key Updates Transactional

ETags support compare-and-set on a single item/operation per the API. They **do not guarantee** atomic updates across 20 key-values or atomic fleet-wide rollouts. Combine sentinels/snapshots/release manifests with proper validation.

## 23. Controlled Feature Flag Rollouts

### 23.1. Progressive Delivery

A sample rollout plan:

| Stage | Audience | Promotion criteria |
|---|---|---|
| Dev | QA team | Functional tests pass |
| Staging | Staging accounts | Regression/performance pass |
| Canary 1 | 1% via stable targeting | No increase in error rate or payment failures |
| Canary 2 | 10–25% | p95 latency, conversion, and retries within bounds |
| Production | 100% | Dashboards and incident plan ready |
| Cleanup | Remove flag and legacy code | Zero remaining dependencies on old path |

Percentages are illustrative, not universal rollout targets for every business domain.

### 23.2. User Bucketing Must Be Stable

If a percentage filter evaluates randomly per request, a user may bounce between checkout flows. Pass a context with a stable ID and use deterministic bucketing supported by the library. Never emit raw PII into logs or counters solely for targeting calculations.

### 23.3. Auditing Flags

Record:

- Flag name, label/snapshot, and revision.
- Timestamp enabled/disabled.
- Actor and approval reference.
- Audience/targeting policy.
- Before/after metrics.
- Rollback instructions.
- Cleanup owner.

Never log secrets or auth tokens from the context into feature flag telemetry.

### 23.4. Kill Switches and Latency

A kill switch requiring a 5-second response **cannot** rely solely on 60-second polling without another mechanism. Design an appropriate trigger/operational control, or use a central safety enforcement mechanism for safety-critical switches.

## 24. IaC Deployment and Configuration as Managed Data

### 24.1. Separate Resource Definitions from Data-Plane Settings

There are two distinct change tracks:

1. **ARM/Bicep/Terraform:** provisions the App Configuration resource, networking, managed identities, role assignments, and diagnostic settings.
2. **Data-plane configuration:** creates/modifies key-values, labels, feature flags, and snapshots.

Permissions and tooling differ between the two tracks. An identity authorized to create resource groups does not automatically hold permission to edit key-values.

### 24.2. Review Workflow

~~~mermaid
flowchart LR
    PR["Pull request<br/>config manifest"] --> REVIEW["Schema/owner/security review"]
    REVIEW --> CI["CI validation<br/>types/ranges/labels"]
    CI --> STAGE["Deploy staging config"]
    STAGE --> TEST["Integration + canary test"]
    TEST --> PROD["Promote prod snapshot / keys"]
    PROD --> OBS["Monitor applied revision"]
    OBS --> ROLLBACK["Rollback if needed"]
~~~

### 24.3. Do Not Treat Portal Edits as the Sole Source of Truth

Manual Portal edits may be appropriate during incident response, but must subsequently be reconciled into your manifest/release records. Otherwise, the next Git-driven deployment can overwrite and erase the emergency fix.

### 24.4. CI/CD Permissions

- Use federated identity/OIDC where supported.
- Grant CI writers only the minimum data-plane permissions on the target store.
- Isolate production deploy jobs from local dev identities.
- Require approvals for settings affecting payments or security.
- Never print access keys or connection strings in build logs.
- Validate values before updating the sentinel.
- Log ETags/revisions without logging sensitive payloads.
- Rate-limit setting writes per second to stay within quotas.

### 24.5. Rollback Is More Than Redeploying an Old JAR

Because configuration lives outside the binary, rolling back code without rolling back config can break backward compatibility. Record **app artifact version + config snapshot/revision + feature flags state** together in a release manifest and roll back as a cohesive unit.

## 25. Monitoring and Telemetry

### 25.1. Metrics to Track

| Layer | Metric/log | Purpose |
|---|---|---|
| App Configuration service | Request counts/errors, throttling/latency per available metrics | Service health |
| Spring bootstrap | Config load succeeded/failed, startup duration | Deployment failures |
| App refresh | Last refresh success time, revision/ETag, refresh failures | Propagation SLO |
| Feature flags | Flag evaluation/targeting counts, outcomes | Rollout quality |
| Key Vault | 401/403/429, latency, secret refresh errors | Secret dependency |
| HTTP business app | Error rate, checkout p95/p99 latency, retry count | Real business impact |
| IaC/operations | Who changed what, when, change ticket | Auditing |
| Cost Management | Store tier/requests, networking, logs, extra resources | FinOps |

Not all of these exist as built-in Azure metrics under these exact names. **ConfigAppliedRevision** or **LastSuccessfulRefreshAge** typically need to be instrumented by the application itself.

### 25.2. Safe Log Content

A safe log entry:

~~~json
{
  "event": "APP_CONFIG_APPLIED",
  "application": "orders-api",
  "environment": "prod",
  "revision": "orders-2026-11-20-r2",
  "result": "SUCCESS",
  "source": "azure-app-configuration",
  "refreshLatencyMs": 55,
  "correlationId": "corr-demo-481"
}
~~~

Numbers above are illustrative. Never log full JSON settings payloads if they might contain sensitive secrets/reference metadata, connection strings, tokens, or user attributes.

### 25.3. Calculating Propagation Latency

~~~text
Operator commits revision r2:       10:00:00
Instance A reports applied r2:      10:00:20
Instance B reports applied r2:      10:00:55

Propagation latency:
    A = 20 seconds
    B = 55 seconds
Fleet converged after 55 seconds in this example
~~~

If the SLO mandates fleet convergence within 30 seconds, this run is a **violation** even though the store update API succeeded.

### 25.4. Alerting

- Prolonged config refresh failures.
- Applied revision lagging behind the expected release revision.
- Label/environment mismatch between deployment and store.
- Increasing store 403/429/5xx responses.
- Key Vault reference resolution errors.
- Unreviewed feature flag changes.
- Spikes in checkout error rate or latency immediately after a config change.
- Unexpected data-plane write identities.
- Secrets or connection strings detected in logs.

## 26. Performance, Quotas, and Caching Strategy

### 26.1. Never GET Config on Every HTTP Request

Suppose an API handles **500 requests/second** and each request reads 3 keys from App Configuration:

~~~text
500 requests/s × 3 key GET/request
= 1,500 config GET/s

In one day:
1,500 × 86,400
= 129,600,000 config GET/day
~~~

This is a load example, not an Azure quota/pricing figure. Such a pattern inflates latency, request volume, throttling risk, and runtime coupling.

### 26.2. Load Once + Refresh

If 40 instances load 20 keys every 5 minutes:

~~~text
40 instances × 20 keys × 12 times/hour × 24 hours
= 230,400 key read operations/day
~~~

This calculation **assumes each refresh reads all 20 keys**. An SDK using caching, ETag checks, sentinel polling, or bulk retrieval can produce fewer or different request counts; do not treat this arithmetic as an exact billing meter formula.

### 26.3. Refresh Interval Trade-Offs

| Refresh interval | Benefit | Trade-off |
|---|---|---|
| Very short | Fast change detection | Quota consumption/traffic/load/races |
| Moderate | Balances latency and operations | Slower propagation |
| Long | Low request volume | Flags/values stay stale longer |
| No dynamic refresh | Reproducible releases | Requires restarts/rollouts |

Choose based on your **propagation SLO** rather than picking an arbitrary number of seconds. Maximum latency guarantees must also account for traffic-driven triggers, startup caches, and outage behavior.

### 26.4. Backoff and Thundering Herd

When the store rejects requests with 429:

- Identify the failing source (App Configuration, Key Vault, Entra, or business API).
- Honor `Retry-After` if present.
- Apply exponential backoff + jitter.
- Bound retries and concurrent refresh attempts.
- Never restart 500 instances simultaneously because of a refresh failure.
- Retain the last validated config when policy permits.
- Never fall back to uncached per-request GET calls that worsen request spikes.

## 27. Cost and FinOps for App Configuration

### 27.1. Cost Drivers

| Component | Cost driver / impact |
|---|---|
| Azure App Configuration | Store tier, request/operation volume, capacity, and plan features |
| Feature flags | Usage/quotas per App Configuration feature support |
| Snapshot | Storage/snapshot counts/operations per tier and pricing model |
| Key Vault | Separate secret-read operations, key/cert protection per pricing |
| Java compute | CPU/RAM on App Service/AKS/Container Apps/VMs |
| Private networking | Private Endpoints, network firewalls, NAT/data transfer |
| Azure Monitor | Diagnostic ingestion, retention, and alerts |
| CI/CD | Config promotion, validation, repeated writes |
| DR/high availability | Multi-store/multi-region setups, operations, and sync |

Exact prices are omitted because Azure pricing varies by region, tier, and time; use the **Azure Pricing Calculator**, Cost Management, budgets, and current quota documentation.

### 27.2. Is a Shared Store Always Cheaper?

Sharing one store across dev/staging/prod reduces resource count, but increases **blast radius** and complicates permission boundaries. The cost of a single production incident or leak can easily exceed the cost of a dedicated production store.

### 27.3. Cost per Safe Configuration Rollout

An operational KPI:

~~~text
Total cost per approved config release
= (App Configuration + Key Vault + compute
   + CI/CD + monitoring + networking + operations)
  / number of releases validated and applied accurately across the fleet
~~~

Do not optimize solely for requests per second. A cheap setup that routinely mixes dev and prod settings fails its purpose.

### 27.4. Optimization

- Never perform remote GETs per request.
- Minimize unnecessary key refreshes.
- Batch changes and use a sentinel where supported.
- Align refresh intervals with actual SLOs.
- Avoid heavy feature targeting semantics if a simple boolean setting suffices.
- Consider snapshots/versioned releases instead of aggressive polling.
- Reduce high-cardinality logging, excessive tags, and PII in logs.
- Use **Key Vault strictly for secrets**—do not put every setting there.
- Clean up unowned lab stores, snapshots, and stale configurations with approval.
- Track data-plane operations and provisioning tiers alongside application compute costs.

## 28. Troubleshooting: Symptom Matrix

| Symptom | Possible cause | Next step |
|---|---|---|
| Java fails to load config at startup | Incorrect endpoint/identity/network/Spring bootstrap | Inspect bootstrap logs and connector setup |
| **401** from App Configuration | Invalid token/audience/credential | Verify TokenCredential and tenant |
| **403** from App Configuration | Missing data-plane RBAC or network/firewall block | Check principal, role, and DNS |
| **404** when fetching key | Missing key or label | Verify exact key+label and null-label handling |
| **429** | Excessive GET/refresh/write volume | Add backoff, TTL, and bounded concurrency |
| **5xx/timeout** | Transient service or network issue | Enforce retry budgets and validated fallback |
| Bean still uses old config | PropertySource refreshed but bean did not rebind | Check `@RefreshScope`/bean lifecycle |
| One instance shows a different value | Unsynchronized refresh | Check convergence SLO and revision telemetry |
| Prod receives dev values | Misconfigured label or precedence | Add deployment label verification |
| Key Vault reference returns JSON instead of secret | Low-level SDK does not auto-resolve references | Use SecretClient or integration resolver |
| Key Vault reference returns 403 | Missing Key Vault role or network access | Grant separate Key Vault data-plane permission |
| Feature flag ignores targeting | Missing feature management filter/context | Verify library and authenticated user/group context |
| Feature flag is off yet API still executes | Flag only hides UI | Enforce server-side gates and auth |
| Config changes work after restart but not live | Missing triggers/monitoring/refresh scope | Test the refresh pipeline end-to-end |
| Sentinel updated yet keys stay stale | Misconfigured triggers, interval, selectors, or cache | Inspect applied revision and polling |
| Incomplete config seen during refresh | Keys updated piecemeal or sentinel updated too early | Update sentinel last or use snapshots |
| Invalid config crashes startup | Good validation working, or unsafe defaults | Fix config with owner approval |
| Logs contain secret values | Config dump/Actuator/HTTP body debug logging | Trigger incident response, redact, rotate |
| Private Endpoint unreachable | Broken Private DNS/route/VNet Integration | Check FQDN resolution and network from the host |
| CLI kv set returns Forbidden | Operator lacks Data Owner | Check role and `--auth-mode login` |
| Rising service costs | Per-request GETs, excessive instances/polling | Review metrics and refresh policy |

### 28.1. Reading Errors at the Right Layer

A backend failure may be wrapped inside a Spring `BeanCreationException` or `IllegalStateException`. Look past the outer exception to find the root cause:

~~~text
Spring ApplicationContext startup
    └── App Configuration PropertySource load
         ├── Azure Identity token acquisition
         ├── App Configuration network request
         ├── RBAC / 403 / network policy
         ├── Label/key selector
         └── Property binding / validation
~~~

If a Key Vault reference fails, also trace the vault endpoint and **Key Vault Secrets User** permission.

### 28.2. Low-Level SDK vs. Starter Error Handling

- Low-level SDK: the application directly catches exceptions thrown by `ConfigurationClient`.
- Spring starter: errors can occur very early during bootstrap, before REST controllers and Actuator start up.
- If optional/fallback behavior is enabled, the app may start with local defaults without surfacing an obvious HTTP error.

Configure startup logging/metrics and explicit readiness tests. Never assume SDK exception behavior matches Spring Boot starter integration.

## 29. Runbook: Resolving 403 on Spring Boot Running in App Service

Common scenario: works locally on a developer machine, fails with 403 once deployed to App Service.

Checklist:

1. **Identify the source of the 403**: App Configuration, Key Vault, a proxy/firewall, or a downstream business API.
2. Inspect environment variables and **APP_CONFIG_ENDPOINT** on the running instance.
3. Confirm App Service managed identity is enabled.
4. Verify the actual **principal object ID**, not a user-assigned client ID by mistake.
5. Verify the **App Configuration Data Reader** role assignment at the store scope.
6. If App Configuration holds references, verify **Key Vault Secrets User** on the vault.
7. Check store auth mode/network rules, Private Endpoint, and VNet Integration.
8. Verify DNS resolution of **store.azconfig.io** from inside the App Service instance.
9. Check whether the credential chain picked up an unintended developer credential from environment variables or tenant mismatch.
10. If the role was newly granted, allow time for propagation instead of blindly escalating to Owner.
11. Test fetching a **non-sensitive** key via SDK/CLI from an authorized network.
12. Inspect the Spring Cloud Azure release, bootstrap config, and startup logs.
13. Once fixed, confirm the applied config revision, readiness, and telemetry.
14. Add a regression test covering identity + network + label accuracy.

### 29.1. When a Key Is Not Found

~~~text
getConfigurationSetting("orders.checkout.timeout-ms", "prod")
→ Not found
~~~

Verify:

- Is the store endpoint pointing to production?
- Does the key use dots or colons?
- Is the label literally `prod` rather than null or `staging`?
- Was the key deleted or renamed?
- Does the prefix filter cover the key?
- Is the setting content type appropriate?
- Is the app pinned to a snapshot that omits the key?
- Could a role/network wrapper be obscuring the real error?

Never auto-create missing production keys from runtime application code on a 404. Writes must go through an approved operator/pipeline.

### 29.2. When Beans Do Not Update After Refresh

Check four checkpoints:

~~~text
Store updated?              YES
Instance refresh detected?  YES
PropertySource updated?     YES
Bean picked new value?      NO
~~~

If only the bean failed to update:

- Is the bean recreated under refresh scope?
- Does it use an immutable constructor snapshot?
- Is the properties bean registered properly?
- Does a service cache the timeout in a `final` field captured at startup?
- Were HTTP clients/DB pools rebuilt?
- Is the refresh event/Actuator trigger compatible with your release?
- Is there a concurrent access race?

Do not blame App Configuration as broken when both the store and Spring Environment reflect the new value but the application lifecycle fails to apply it.

### 29.3. When a Refresh Causes a Production Incident

- Identify the revision, actor, and update timestamp.
- If a configuration manifest supports rollback, revert to the previous snapshot/values.
- Disable a newly rolled-out feature flag if authorized and effective.
- Monitor checkout error rates, latency, and retries.
- Ensure instances do not re-ingest the bad config on subsequent polling cycles.
- Pause config promotion/refresh or recycle instances per runbook.
- Tighten validation constraints to prevent recurrence.

## 30. Data Security and Governance

### 30.1. Boundary Model

~~~mermaid
flowchart LR
    USER["Authenticated user"] --> APP["Spring Boot API"]
    ID["Workload identity"] --> APP
    APP --> AC["App Configuration<br/>non-secret config"]
    APP --> KV["Key Vault<br/>secrets"]
    APP --> DB["Business data"]
    ADMIN["IaC/CI operators"] --> AC
    AUTH["Authorization layer"] -. "tenant/group rules" .-> APP
~~~

Separate the **workload identity** used to read config from the **end-user identity** calling business APIs. Never grant runtime write access just because a user can toggle a UI preference.

### 30.2. App Configuration Data Reader Still Has Broad Scope

If a single store holds both dev and prod configs and an app identity holds Data Reader at the store scope, it can read multiple labels. Separate **stores, identities, and networks** when compliance demands environment isolation. Labels organize variants—they do not replace RBAC.

### 30.3. Config Injection and SSRF Risk

The value of **orders.payments.endpoint-url** comes from a store written by CI/operators. If an attacker compromises write access to the store, they could:

- Redirect the endpoint to a malicious server.
- Alter timeouts/retries to induce an outage.
- Flip an admin feature flag improperly.
- Point a Key Vault reference URI to an unauthorized vault.

Applications must still **validate endpoints and allowed hosts**, treat config write roles as sensitive privileges, audit all changes, and defend against SSRF in downstream HTTP clients.

### 30.4. Key Vault Reference URIs Are Untrusted Metadata in the Low-Level SDK

If parsing URIs manually:

- Permit **https** only.
- Restrict vault hosts via an environment/tenant allowlist.
- Never instantiate a `SecretClient` targeting arbitrary domains.
- Avoid logging `secretName` or URIs unnecessarily.
- Scope Key Vault permissions so an app cannot read vaults outside its remit.

### 30.5. Actuator and Config Endpoints

Depending on configuration, Spring Actuator exposes endpoints like **/env** or **/configprops**, which can leak configuration metadata or values if overly exposed. Restrict network/authorization access, enable sanitization, and never expose full Actuator endpoints over public ingress.

### 30.6. Feature Flags Do Not Replace Authorization

Even if the **admin-dashboard** flag is off, backend routes must still verify user roles. When a flag is enabled for a group, it governs feature behavior only—it **never grants permission to read another tenant's data**.

### 30.7. Secret Rotation When References Change

- The App Configuration writer identity should not be able to read every secret value.
- A separate Key Vault rotation operator updates credentials.
- The app runtime holds `get` permission only for its required secrets.
- Refresh/Key Vault cache policies allow picking up the new version.
- Coordinate credential activation/revocation on the partner side.
- Never log secrets into diffs, IaC state, or feature experiment analytics.

## 31. Testing Strategy and Staging Environments

### 31.1. Unit Tests: No Azure Calls

Test typed configuration and business logic using plain objects:

~~~java
import com.example.orders.config.CheckoutProperties;

CheckoutProperties props = new CheckoutProperties();
props.setTimeoutMs(900);
props.setRetryCount(2);

if (props.getTimeoutMs() != 900 || props.getRetryCount() != 2) {
    throw new AssertionError("Unexpected bound properties");
}
~~~

This snippet illustrates a test body; place it inside a JUnit test method in a real project. To test validation rules, use a Bean Validation / Jakarta Validation test context.

### 31.2. Integration Tests with a Lab App Configuration Store

1. Provision a lab store and authorized test user/managed identity.
2. Populate keys with null, prod, and dev labels.
3. Verify SDK `getConfigurationSetting(key, label)` accuracy.
4. Verify Spring Cloud Azure PropertySource loading and `@ConfigurationProperties` binding.
5. Verify default/override precedence.
6. Test missing required keys → verify fail-fast if required by policy.
7. Update settings and sentinel → measure time to applied revision.
8. Verify beans actively pick up the new value.
9. Verify identities lacking a data role are denied.
10. Verify feature flags on/off and targeting behavior if used.
11. Verify Key Vault references require independent vault permissions.
12. Clean up lab resources per approval and retention policy.

### 31.3. Critical Negative Tests

| Test | Expected result |
|---|---|
| Spring Boot prod launched with label dev | Blocked by deployment validation |
| Runtime identity holds only Azure Contributor | No implicit data-reader access |
| Identity stripped of App Configuration Data Reader | Remote access rejected |
| Key Vault reference present without Secrets User | Secret fails to resolve |
| Key value timeout = -500 | Rejected by validation |
| Retry count = 100 | Rejected by validation |
| Sentinel updated before keys | Test exposes partial-config risk |
| Bean outside refresh lifecycle | Test proves bean does not auto-update |
| User lacks admin role while feature flag is on | Backend authorization still rejects |
| Cross-tenant/config label access | No data leakage per isolation design |
| Store 429/network timeout | Bounded retry and safe fallback |
| Slow feature flag disablement | Propagation SLO measured and alerted |
| Compromised config writer | Permissions revoked, audited, rolled back |

### 31.4. Staging Chaos Tests

- Block outbound traffic to App Configuration for several minutes.
- Force Key Vault reference permission failures in test.
- Inject controlled 429/throttling responses.
- Restart pods mid-refresh.
- Update 10 keys and the sentinel with simulated delays.
- Switch snapshots/references while half the fleet still runs the old revision.
- Execute concurrent requests reading configuration.
- Confirm readiness/liveness probes do not trigger a restart storm.
- Verify logs and Actuator endpoints do not leak keys.
- Measure convergence time and behavioral consistency.

**Never run chaos tests against production stores/vaults or shared resources** without explicit approval.

## 32. End-to-End Spring Boot Lab Walkthrough

These steps serve as a walkthrough guide; no applications or Azure resources were deployed while writing this lesson:

1. Create a Java 17 Spring Boot project with Spring Web and Validation.
2. Pick compatible Spring Boot and Spring Cloud Azure versions from the release matrix.
3. Provision the lab App Configuration store and the 3 dot-separated keys from Section 10.
4. Grant **Data Reader** to the runtime identity; reserve Data Owner for operators.
5. Configure **APP_CONFIG_ENDPOINT** and **APP_CONFIG_LABEL** in deployment settings.
6. Add the Spring Cloud Azure App Configuration starter to Maven and configure the right bootstrap mechanism.
7. Bind the keys into **CheckoutProperties** with Bean Validation enabled.
8. Create a service consuming the injected timeout and retry values.
9. Run locally via **az login**, confirming your user holds the data role.
10. Emit a sanitized startup log showing **configured revision/label**; never dump the entire Environment.
11. Enable refresh/sentinel per your release's syntax; update timeout via CLI.
12. Verify each instance actually changes runtime behavior.
13. Submit an invalid value to confirm validation rejects it.
14. Create the **new-checkout** feature flag and test on/off plus targeting if supported.
15. Create a demo secret in Key Vault and add its reference metadata in App Configuration.
16. Grant Key Vault Secrets User to the runtime identity and verify separate authorization.
17. Test 403/429/Key Vault reference/network errors and verify safe fallback.
18. Enable metrics/diagnostics, then inspect costs and propagation latency.
19. Clean up approved lab resources.

**Lab completion criteria:** the same Spring Boot binary runs in dev and prod using different labels, all settings enforce type/range validation, zero secrets are hard-coded, reader roles follow least privilege, refreshes produce telemetry proving the applied revision, and remote dependency failures stay within policy.

## 33. Choosing a Configuration Approach by Scenario

| Scenario | Recommended approach | Rationale |
|---|---|---|
| Small app, rarely changing settings | `application.yml` + environment | Simple, fewer remote dependencies |
| Multiple Spring Boot services sharing config | Azure App Configuration | Centralized, labels, change management |
| Partner secret needed | Azure Key Vault or direct managed identity | Avoid plaintext secrets in App Config |
| Feature toggles and group targeting | App Configuration Feature Manager | Condition filters and gradual rollouts |
| Same binary deployed across environments | App Configuration labels or separate stores | Avoid rebuilding JARs per environment |
| Strong isolation between prod and dev | Separate stores/identities | Labels are not security boundaries |
| Frequently changing config needing live reload | Starter/SDK + sentinel + applied revision | Verifiable refresh pipeline |
| Config must stay immutable per release | Snapshots/versioned manifests | Consistency and clean rollbacks |
| App has only a handful of non-secret keys | Environment/App Service settings | Avoid unnecessary complexity |
| Unavoidable partner payment API key | Key Vault reference or SecretClient | Rotation and least privilege |
| Per-user or per-request volatile data | Business DB/API | Do not use App Configuration as a session store |
| Live transactional business state | Azure SQL/Cosmos/service API | Config is not transactional business state |
| Multi-service AKS cluster needing config | App Configuration + Workload ID where appropriate | Central governance; K8s ConfigMaps remain useful |
| Security flag requiring sub-1-second cutoff | Dedicated central enforcement/low-latency control | Polling refresh has propagation lag |
| Multiple settings that must change as one unit | Snapshot + canary/release manifest | Prevent incompatible mixed configs |

**Selection rule:** Start from business impact, change frequency, consistency guarantees, security boundaries, and service count. Never introduce App Configuration merely to replace one line of local YAML with no clear operational need.

## 34. Production Checklist

### 34.1. Architecture and Data

- [ ] Classified regular configs, feature flags, secrets, and runtime settings.
- [ ] No plaintext API keys/passwords/private keys stored in App Configuration.
- [ ] Decided which use cases use Key Vault references vs. direct managed identity.
- [ ] Keys follow a consistent naming convention with clear ownership.
- [ ] Dot-separated Spring properties tested for binding without mixing colon/prefix semantics.
- [ ] Dev/staging/prod label precedence verified by tests.
- [ ] Shared stores/labels are not relied upon for security isolation.
- [ ] Snapshot/manifest/sentinel strategy defined when multiple keys must update together.
- [ ] Validation covers timeouts, retries, URLs, feature conditions, and numeric bounds.
- [ ] App Configuration is not used as a database or session store.
- [ ] Fail-open vs. fail-closed policy defined per risk profile.
- [ ] App tracks and reports its active revision/version.

### 34.2. Java / Spring Boot

- [ ] Spring Boot, Spring Cloud Azure, and Java versions verified compatible and pinned.
- [ ] Choice between low-level SDK and Spring starter matches requirements.
- [ ] Bootstrap endpoint and identity come from secure local/platform sources.
- [ ] Remote PropertySource loads cleanly prior to bean binding.
- [ ] `@ConfigurationProperties` verified against chosen keys and labels.
- [ ] Bind and refresh validation tested at startup and runtime.
- [ ] `@RefreshScope`/bean lifecycle or atomic snapshot swap verified.
- [ ] HTTP clients/pools have a policy to reconfigure when timeouts/endpoints change.
- [ ] No new `ConfigurationClient`/credential instantiated per HTTP request.
- [ ] No remote App Configuration GET executed per business request.
- [ ] Remote refresh interval aligned with SLO and quota limits.
- [ ] Circuit breaker, backoff, timeouts, and retry budgets configured for remote calls.
- [ ] Startup and outage fallback behavior decided and tested.
- [ ] Liveness probe does not continuously poll App Configuration or Key Vault.

### 34.3. Security and Operations

- [ ] Workload identity uses Entra/managed identity instead of static connection strings wherever possible.
- [ ] Runtime holds only App Configuration Data Reader or least-privilege equivalent.
- [ ] Config deployment writer role separated from runtime reader.
- [ ] Key Vault references backed by dedicated Key Vault Secrets User permissions.
- [ ] Role assignment scopes and principal IDs verified.
- [ ] Private Endpoint, firewall, DNS, and VNet Integration configured per environment.
- [ ] TLS certificate validation is never disabled.
- [ ] Feature flags do not replace application authorization.
- [ ] Spring Actuator and error pages do not expose config values or secrets.
- [ ] Config change audit trail, approver workflow, and rollback exist.
- [ ] Logs are sanitized and contain no credentials, tokens, or plaintext secrets.
- [ ] Alerts configured for 401/403/429, refresh errors, stale revisions, and label mismatches.
- [ ] Tested multi-instance fleets, reconnect/startup storms, and configuration drift.
- [ ] Owner, budget, quota, and cost dashboards exist for App Configuration and Key Vault.
- [ ] Runbook covers rolling back both binary artifacts and config revisions together.
- [ ] Lab/test identities cannot modify production secrets or feature flags.

## 35. Hands-On Exercises

### Exercise 1: Classify Configuration

For each item below, choose `application.yml`, environment variable, App Configuration, Key Vault, or business database:

1. Checkout timeout.
2. Partner API key.
3. DB connection endpoint without credentials.
4. Legacy DB password.
5. Current SKU inventory count.
6. Feature flag `new-checkout`.
7. Java heap limit.
8. A user's `LastReadNotificationId`.
9. Environment name `prod`.
10. Retry configuration.

Justify each choice in terms of **sensitivity, update frequency, and ownership**.

### Exercise 2: Key-Values and Labels

Setup:

~~~text
orders.checkout.timeout-ms [no label] = 1000
orders.checkout.timeout-ms [dev]      = 1500
orders.checkout.timeout-ms [staging]  = 1100
orders.checkout.timeout-ms [prod]     = 800
~~~

Write a test proving the prod app receives 800 and dev receives 1500. Explain what should happen if the prod key is deleted: fall back to the null label or fail fast?

### Exercise 3: CLI, RBAC, and Managed Identity

1. Create a lab App Configuration store.
2. Have an operator grant Data Owner to the identity seeding demo values.
3. Write 3 dot-separated keys using **--auth-mode login**.
4. Grant Data Reader to the app's managed identity.
5. Run SDK `getConfigurationSetting`.
6. Test with an identity lacking a data role to verify a 403 error.
7. Log the request ID/status without logging any secret.

### Exercise 4: Low-Level Java SDK

Using **ConfigurationClient**:

- Read timeout by key and label.
- Parse the int and validate the 100–10000 range.
- On missing key → handle 404 per policy.
- On 429 → perform bounded retries.
- List a group of keys via a selector and log metadata only.
- Ensure a single `ConfigurationClient` is reused rather than created per request.

### Exercise 5: @ConfigurationProperties

1. Create a Spring Boot class **CheckoutProperties**.
2. Bind `timeoutMs` and `retryCount`.
3. Add Bean Validation constraints for valid ranges.
4. Test that an invalid timeout of **-1** is rejected.
5. Test a missing mandatory partner endpoint.
6. Confirm the prod label never falls back to dev.

### Exercise 6: Sentinel and Refresh

Given 5 instances, a 30-second refresh interval, currently running revision r1:

1. Update 3 keys.
2. Update the sentinel last to r2.
3. Measure how long each instance takes to report r2 applied.
4. One instance receives no traffic and fails to refresh; design how to detect it.
5. Simulate an invalid value in r3.
6. Ensure instances remain on r2 per policy.
7. Write an SLO "99% of instances apply within 90 seconds" and define the metric to verify it.

### Exercise 7: Config Snapshot and Rollback

A release changes both the checkout endpoint and API version. Updating keys one by one risks an instance reading endpoint v2 + version v1.

- Use a snapshot or typed JSON atomic unit.
- Create a release manifest pairing the JAR with the config revision.
- Canary r2.
- Roll back app and config together if errors spike.
- Explain why per-key ETags do not form a multi-key transaction.

### Exercise 8: Feature Flags

Enable **new-checkout** for QA, then 5%, 25%, and 100%.

- Derive the targeting context from authenticated identity.
- Track error rates, conversion, and p95 latency.
- Disable the flag while requests are in flight.
- Explain kill switch limitations caused by refresh latency.
- Include flag cleanup after rollout finishes.

### Exercise 9: Key Vault References

1. Create a demo secret in a lab Key Vault.
2. Store a Key Vault reference URI in App Configuration.
3. Give the app identity App Configuration Data Reader **without** Key Vault Secrets User: verify failure.
4. Grant the missing Key Vault role.
5. Use the SDK/integration resolver to retrieve the secret.
6. Verify the secret value never appears in logs.
7. Rotate the secret version and test refresh separately.

### Exercise 10: Private Endpoint

Diagram the path from App Service to **store.azconfig.io** and from the app to Key Vault:

- VNet Integration.
- Private Endpoint.
- Private DNS.
- TLS hostname.
- Entra token endpoint.
- Data-plane RBAC.

Explain why a 403 does not always mean a missing role and why you should never connect directly to a raw private IP.

### Exercise 11: Outage

Simulate App Configuration being unavailable for 10 minutes:

- Instance A is running with validated config.
- Instance B just scaled out.
- Instance C is refreshing a critical feature flag.

Design fail-fast/last-known-good/readiness behavior for each instance, specifying when stale config is acceptable and when failing closed is mandatory.

### Exercise 12: FinOps

Assume 40 instances, 20 keys, a 5-minute refresh interval, and 500 business requests/s:

1. Calculate theoretical GET operations if reading config per request.
2. Calculate the upper bound if every refresh reads all 20 keys.
3. Analyze how sentinel/ETag caching and bulk requests change actual counts.
4. List cost drivers across App Configuration, Key Vault, networking, and Azure Monitor.
5. Propose optimizations that cut cost while still meeting the refresh SLO.

## 36. Self-Check Questions

1. What problem does Azure App Configuration solve that `application.yml` struggles with across many instances?
2. Why should non-secret configuration be separated from secrets?
3. How does App Configuration differ from Key Vault in purpose and data protection?
4. Besides the key, what field identifies an App Configuration setting?
5. Is a null label equivalent to the string `"null"`?
6. Do labels create a security boundary between dev and prod?
7. Why do naming conventions matter for Spring Boot property binding?
8. When should you use separate stores instead of one store with labels?
9. How does a feature flag differ from a static boolean setting?
10. Where should targeting filters obtain identity context from?
11. Does a feature flag replace application authorization?
12. Does a Key Vault reference store the secret value or a URI?
13. Can an identity with App Configuration Data Reader automatically read Key Vault secrets?
14. Does Azure Contributor implicitly grant Data Reader in App Configuration?
15. Which identity does `DefaultAzureCredential` select locally versus on App Service?
16. How does managed identity compare to connection string access keys?
17. What does the Spring Cloud Azure starter do that the low-level `ConfigurationClient` does not?
18. Why must you check Spring Boot/Spring Cloud Azure version compatibility?
19. At which stage must the App Configuration endpoint be supplied?
20. When should you use `@ConfigurationProperties` instead of parsing strings manually?
21. What types of constraints should `@Validated` enforce?
22. Does refreshing a `PropertySource` always rebuild existing HTTP clients?
23. Does `@RefreshScope` cause App Configuration to push updates automatically?
24. What problem does a sentinel key solve?
25. Why does updating the sentinel last still not create a fleet-wide transaction?
26. How does a snapshot differ from null-label defaults?
27. What role does ETag play in concurrent config updates?
28. Does a config revision take effect on every instance simultaneously?
29. Why must you measure the applied revision rather than stopping at `kv set` success?
30. How does App Service VNet Integration differ from an App Configuration Private Endpoint?
31. What is the typical Private DNS zone name for App Configuration?
32. Why shouldn't you switch the endpoint to a private IP to bypass a DNS issue?
33. Which failure layers do HTTP 401, 403, 404, and 429 typically indicate?
34. Should a runtime identity automatically create missing keys upon encountering a 404?
35. Which configurations warrant startup fail-fast behavior?
36. What risk does last-known-good carry for security-related config?
37. Why shouldn't a liveness probe call remote config every 5 seconds?
38. What factors can delay disabling a feature flag?
39. Why shouldn't an application GET configuration on every request?
40. How do App Configuration store tier, operations, and monitoring affect FinOps?
41. Why is rolling back a JAR without rolling back config dangerous?
42. Does a versionless Key Vault reference guarantee the new secret takes effect instantly?
43. What risk arises when Spring Actuator exposes `/env`?
44. Why must config writer roles be strictly reviewed?
45. When should you use a business database instead of App Configuration?
46. How can you detect an instance still running an older revision?
47. How do you mitigate thundering herds when hundreds of instances refresh together?
48. Why must negative permissions and private networking be tested?
49. What information should be logged for debugging without leaking secrets?
50. When is an architecture using only local `application.yml` still the best choice?

## 37. References

- [Azure App Configuration overview — Microsoft Learn](https://learn.microsoft.com/azure/azure-app-configuration/overview)
- [Keys and values in App Configuration](https://learn.microsoft.com/azure/azure-app-configuration/concept-key-value)
- [Use labels for application configuration](https://learn.microsoft.com/azure/azure-app-configuration/howto-labels)
- [Feature management overview](https://learn.microsoft.com/azure/azure-app-configuration/concept-feature-management)
- [Feature flag schema and conventions](https://learn.microsoft.com/azure/azure-app-configuration/concept-feature-filters)
- [Azure App Configuration snapshots](https://learn.microsoft.com/azure/azure-app-configuration/concept-snapshots)
- [Use Key Vault references in Azure App Configuration](https://learn.microsoft.com/azure/azure-app-configuration/use-key-vault-references-dotnet-core)
- [Azure App Configuration with Java and Spring](https://learn.microsoft.com/azure/azure-app-configuration/quickstart-java-spring-app)
- [Use dynamic configuration in Java Spring apps](https://learn.microsoft.com/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app)
- [Use feature flags in Java Spring apps](https://learn.microsoft.com/azure/azure-app-configuration/quickstart-feature-flag-spring-boot)
- [Azure App Configuration Java SDK documentation](https://learn.microsoft.com/java/api/overview/azure/data-appconfiguration-readme)
- [Azure App Configuration Java client API](https://learn.microsoft.com/java/api/com.azure.data.appconfiguration.configurationclient)
- [Spring Cloud Azure overview](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Spring Cloud Azure App Configuration integration](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-app-configuration)
- [Spring Cloud Azure compatibility reference](https://learn.microsoft.com/azure/developer/java/spring-framework/spring-versions)
- [Azure App Configuration authentication with Microsoft Entra ID](https://learn.microsoft.com/azure/azure-app-configuration/concept-enable-rbac)
- [Azure App Configuration Private Endpoint](https://learn.microsoft.com/azure/azure-app-configuration/concept-private-endpoint)
- [Azure App Configuration monitoring](https://learn.microsoft.com/azure/azure-app-configuration/monitor-app-configuration)
- [Azure Key Vault overview](https://learn.microsoft.com/azure/key-vault/general/overview)
- [Key Vault RBAC permissions](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Azure Managed Identities overview](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot ConfigurationProperties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Cloud refresh scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Azure App Configuration pricing](https://azure.microsoft.com/pricing/details/app-configuration/)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)





