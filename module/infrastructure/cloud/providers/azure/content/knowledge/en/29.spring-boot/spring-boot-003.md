# Configuring Applications per Azure Environment

A Spring Boot service that works fine on a laptop can fail to start when deployed to Azure App Service, Azure Container Apps, or Azure Kubernetes Service (AKS). The cause is rarely in the Java code: a wrong database connection, the wrong profile activated, a missing environment variable, an expired secret, incorrect Private Endpoint DNS, or a production setting overridden by a testing value. **Configuring applications per Azure environment** is the practice of managing these differences intentionally, verifiably, and with rollback capability.

In the **Spring Boot on Azure** chapter, we combine **Spring Boot externalized configuration** mechanisms with Azure services such as Microsoft Entra ID, Managed Identity, Azure App Configuration, Azure Key Vault, App Service, Container Apps, AKS, Azure SQL, Storage, and observability components. This lesson belongs to the **CLOUD_PROVIDERS_AZURE** module: exploring Azure from subscriptions, resource groups, and Entra ID through virtual networking, compute, storage, and data, while deploying, monitoring, securing, and controlling the cost of an application architecture.

**Core principle:** the same application version or container image should be able to run across multiple environments; differences in endpoints, feature flags, resource limits, permissions, and secrets are supplied **outside the source code**. Never package production passwords, never edit source and rebuild just to change a hostname, and never assume a profile named **prod** automatically provides production security.

> **Version note:** Examples follow **Spring Boot 3.x** and modern Java conventions. Config Data mechanics, Spring Cloud Azure property names, secret delivery, Azure CLI, network capabilities, and Portal UI may differ by version, tier, or platform. Consult the documentation matching the exact Spring Boot, Spring Cloud Azure, and Azure service versions you run. Resource/host/path names are **illustrative**; commands capable of modifying resources are clearly flagged and should only run in authorized lab environments.

## Learning Objectives

After this lesson, you can:

1. Classify **non-sensitive configuration, secrets, connection details, and business runtime state**.
2. Use **application.yml**, **application-{profile}.yml**, **SPRING_PROFILES_ACTIVE**, environment variables, and command-line arguments for their intended purposes.
3. Explain **Spring PropertySource / Config Data precedence** rules and avoid accidental configuration overrides.
4. Bind configuration into Java code using **@ConfigurationProperties**, apply validation, and fail fast when critical values are missing.
5. Compare how configuration is supplied in **Azure App Service, Azure Container Apps, and AKS**.
6. Choose **Azure App Configuration** for centralized config and labels/feature flags, and **Azure Key Vault** for secrets.
7. Understand **Microsoft Entra managed identity**, RBAC, secret rotation, DNS, TLS, and private endpoints.
8. Design startup/readiness/liveness probes, retries/timeouts, observability, and safe rollbacks per environment.
9. Prevent dev/staging/prod mix-ups, secret leaks, and configuration drift through CI/CD and IaC.
10. Build a verifiable Spring Boot configuration lab and production checklist.

## 1. What Is Application Configuration?

**Configuration** is data that adjusts application behavior without changing program logic. Examples:

- Base URL of an internal service.
- JDBC URL, database pool size, and connection timeout.
- Azure Blob container name or Storage endpoint.
- Rollout percentage for a feature per environment.
- Logging level, sampling, and timeouts.
- Redis hostname, Service Bus namespace, queue name.
- Concurrent request limits and batch sizes.

A **Secret** is information requiring stronger protection: database passwords, signing keys, Storage account keys, client secrets, API keys, or access tokens. **Runtime data** such as orders, balances, and user sessions is not configuration even if stored in a database or config-like store.

### Separate Three Data Categories

| Category | Examples | Appropriate management store |
|---|---|---|
| **Standard config** | app.client.timeout, API URL, enabled modules | application.yml, environment variables, Azure App Configuration |
| **Secrets** | Passwords, API keys, private keys, secret tokens | Azure Key Vault or platform-approved secret facilities |
| **Business data** | Orders, inventory, customer records | Azure SQL, Cosmos DB, Storage per requirements |

**Do not treat Azure App Configuration as a plaintext password store** just because it supports key-value pairs; use Key Vault and supported secret references/integrations.

## 2. Application Environments to Distinguish

A system may span multiple environments:

~~~text
Developer laptop
      |
      v
DEV -> TEST -> STAGING -> PRODUCTION
      |       |          |
      |       |          +-- Azure production resources
      |       +------------- Pre-production validation
      +--------------------- Synthetic/sample resources
~~~

| Environment | Purpose | Configuration approach |
|---|---|---|
| **local** | Developer run/debug | Dev endpoints, least-privilege developer credentials |
| **dev** | Integrating new features | Dev resources, controlled verbose diagnostics |
| **test** | Automated/integration tests | Synthetic data, fixtures, deterministic settings |
| **staging** | Pre-release validation | Match prod as closely as possible in config delivery, auth, and networking |
| **prod** | Serving real users | Least privilege, TLS, high availability, bounded retries, alerting |

Spring **profiles** are a mechanism to toggle config sets/beans; a profile name does not replace **resource separation, network policies, RBAC, change management**, or production infrastructure.

### Never Share the Same Database Between Dev and Prod

If a dev API accidentally uses the production JDBC URL, a DELETE integration test can erase real data. Separate subscriptions/resource groups/identities/data sources per policy, and verify endpoints and principals before allowing jobs or migrations.

## 3. Goal: Build Once, Deploy Anywhere

~~~text
Git commit abc123
        |
        v
CI: build + test + scan
        |
        v
Container image digest: sha256:...
        |
        +--> DEV      + env vars + dev identity/Key Vault
        |
        +--> STAGING  + env vars + staging identity/Key Vault
        |
        +--> PROD     + env vars + prod identity/Key Vault
~~~

Using the **same image digest** reduces drift from recompiling with different dependencies. Environment-specific configuration is attached at deployment or runtime rather than baked into the binary. Version non-sensitive configuration and manage secrets separately.

### What Are the Limits of One Artifact Across Environments?

- Different feature flags or endpoints may be required.
- Certain configuration changes require a restart or rollout.
- If the prod DB schema differs from staging, the same artifact does not guarantee identical execution.
- Misconfigured settings can still cause severe outages.

**Build once** is a practice to reduce variables, not a guarantee that the same binary automatically works in every environment.

## 4. Spring Boot Externalized Configuration Mechanism

Spring Boot can load properties from multiple sources:

- Default properties and configuration files packaged inside the application.
- **application.properties** or **application.yml**.
- Profile-specific files such as **application-dev.yml**.
- **Config Data import** sources.
- **Environment variables** from the process/container.
- Java system properties.
- Command-line arguments.
- Custom sources via Spring integrations.

From Java code's perspective, these merge into **Environment** and **PropertySources** in a defined precedence order.

~~~text
application.yml        application-prod.yml
        |                       |
        +----------+------------+
                   |
          External Config Data
                   |
       OS environment variables
                   |
     JVM system / CLI args and others
                   |
                   v
         Spring Environment
                   |
                   v
        @ConfigurationProperties
                   |
                   v
               Beans / SDK clients
~~~

This diagram is **not an absolute precedence table**. Spring Boot defines a detailed order for each source type; file location, import order, document activation, framework-added property sources, and command-line handling all affect the outcome. Check documentation for your exact version and inspect effective values safely when troubleshooting.

## 5. Precedence Rules and Overriding Values

Suppose **application.yml** declares:

~~~yaml
app:
  client:
    timeout: 3s
~~~

And the process environment has:

~~~text
APP_CLIENT_TIMEOUT=500ms
~~~

In a standard Spring Boot setup, the environment variable binds to **app.client.timeout** and overrides the file value. If the command line also passes **--app.client.timeout=200ms**, CLI arguments typically take higher precedence than OS env vars by default.

### General Rules Table

| Source | Notes |
|---|---|
| application.yml | Baseline values; should contain no secrets |
| application-prod.yml | Overrides when the prod profile is active |
| External config file | Can be loaded outside the JAR and override by location |
| Environment variables | Commonly used when deploying Azure apps/containers |
| JVM system properties | **-Dkey=value** options |
| Command-line arguments | **--key=value**, typically high precedence |
| Imported Config Data | Precedence depends on import declaration and Spring Boot version |

**Do not rely solely on this table to predict complex overrides**. Full ordering is governed by Spring Boot; for config imports/providers, verify precedence, refresh behavior, and fail-on-missing rules for your exact version.

### Why Are Overrides Dangerous?

A startup script adding **--spring.datasource.url** can override a production URL supplied properly via the environment. Therefore, production environments must manage startup arguments and config sources as infrastructure changes, not let developers tweak them ad hoc.

## 6. application.yml: Safe Defaults

Example baseline configuration in the repository:

~~~yaml
spring:
  application:
    name: catalog-api

server:
  port: 8080

app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 2
  features:
    recommendations: false

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

These are illustrative values. **connect-timeout**, **read-timeout**, and **max-retries** are custom application properties; they **do not automatically configure any HTTP or Azure SDK client** unless Java beans/code consume and apply them.

### What Must Not Be Placed in This File

- Database passwords or Redis access keys.
- Key Vault secret values.
- Connection strings containing account keys or SAS tokens.
- Production-only credentials or tokens.
- Unmanaged private keys and certificates.

Default values should fail safe: e.g., unverified new features turned off, bounded retry counts, and log levels that do not capture sensitive payloads.

## 7. Profile-Specific Files: application-dev.yml and application-prod.yml

Spring Boot can load profile-specific files:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-staging.yml
  application-prod.yml
~~~

Example **application-dev.yml**:

~~~yaml
logging:
  level:
    com.example.catalog: DEBUG

app:
  features:
    recommendations: true
  client:
    read-timeout: 10s
~~~

Example **application-prod.yml**:

~~~yaml
logging:
  level:
    root: INFO
    com.example.catalog: INFO

app:
  features:
    recommendations: false
  client:
    read-timeout: 3s
~~~

### Two Things to Remember

1. **application-prod.yml** does not activate automatically just by running on Azure: the **prod** profile (or equivalent mechanism) must be explicitly activated.
2. Profile files may hold **non-sensitive** settings, but never commit production passwords. Use Key Vault/secret injection for sensitive values.

Never place **spring.profiles.active** inside a profile-specific document/file expecting Spring to self-activate it: Spring Boot restricts profile-activation properties inside profile-activated documents. Set the active profile from the deployment environment or a non-profile-conditional source.

## 8. Activating Profiles and Verifying Effect

In a CLI/lab environment:

~~~bash
# Linux/macOS, affects only the current shell/process.
export SPRING_PROFILES_ACTIVE=dev
java -jar catalog-api.jar
~~~

Or:

~~~bash
java -jar catalog-api.jar --spring.profiles.active=staging
~~~

When running on Azure, it is more common to set **SPRING_PROFILES_ACTIVE** in application settings, Container App environment variables, or Kubernetes environments.

### Be Careful with Multiple Simultaneous Profiles

~~~text
SPRING_PROFILES_ACTIVE=staging,metrics
~~~

Spring can activate multiple profiles; if the same property appears in multiple sources/profile documents, **order** and Config Data mechanics decide the final value. Never treat profiles as an unordered bag of labels.

### Default Profile

If no active profile is configured, Spring falls back to its framework default profile—it does not infer dev. An app missing a profile may still boot using `application.yml`; therefore **critical config variables require validation** rather than silently connecting to the wrong target.

## 9. spring.config.activate.on-profile and Multi-Document YAML

Spring Boot Config Data supports declaring multiple YAML documents inside a single file:

~~~yaml
app:
  features:
    recommendations: false

---
spring:
  config:
    activate:
      on-profile: dev

app:
  features:
    recommendations: true

---
spring:
  config:
    activate:
      on-profile: prod

app:
  client:
    connect-timeout: 1s
~~~

Documents after **---** apply only when the profile condition matches. This is an alternative to separate `application-dev.yml`/`application-prod.yml` files when a project prefers centralized overrides.

### Pitfalls

- Never put secrets in any YAML document committed to Git.
- Never declare **spring.profiles.active** or profile group definitions inside a document gated by `on-profile`.
- Do not assume YAML document order overrides every property-source rule.
- Once configuration grows complex, splitting files/sources is often easier to review.

## 10. Profile Groups and Avoiding Profile Explosion

An application may need bundles of settings: database, observability, and feature flags. Spring Boot supports **profile groups** in valid configuration sources.

~~~yaml
spring:
  profiles:
    group:
      prod:
        - database-prod
        - observability-prod
~~~

When activating **prod**, the grouped profiles activate per Spring Boot mechanics.

**Declare profile groups only in non-profile-specific/non-activated documents** per Spring Boot restrictions. Also avoid turning profile groups into a 50-combination matrix that is impossible to test.

### Sensible Design

- **Environment profiles:** local, dev, staging, prod.
- **Feature switches:** use feature flags instead of creating a profile per feature.
- **Secrets/config values:** use external config/Key Vault.
- **Genuinely distinct Bean implementations:** use `@Profile` when required.

## 11. Mapping Environment Variables to Spring Properties

Spring Boot uses **relaxed binding**, mapping environment variable names to property names.

| Spring property | Commonly used environment variable |
|---|---|
| spring.profiles.active | **SPRING_PROFILES_ACTIVE** |
| server.port | **SERVER_PORT** |
| spring.datasource.url | **SPRING_DATASOURCE_URL** |
| spring.datasource.username | **SPRING_DATASOURCE_USERNAME** |
| spring.datasource.password | **SPRING_DATASOURCE_PASSWORD** |
| app.client.connect-timeout | **APP_CLIENT_CONNECTTIMEOUT** |
| app.features.recommendations | **APP_FEATURES_RECOMMENDATIONS** |

### Rules to Know

Under Spring Boot's canonical environment-variable binding rules: **dots become underscores, dashes are removed, and letters become uppercase**. Thus **app.client.connect-timeout** maps to **APP_CLIENT_CONNECTTIMEOUT**; do not assume **APP_CLIENT_CONNECT_TIMEOUT** works identically in every scenario.

**Differences exist** between `Environment.getProperty` lookups, `@ConfigurationProperties` relaxed binding, and specific placeholder resolution. For critical custom keys, test the mapping in the real application rather than guessing from naming conventions.

### Why Is This a Frequent Production Bug?

An operator sets a plausible-looking variable like **APP_CLIENT_CONNECT_TIMEOUT**, yet the Java record silently receives the default value. Logs show no warning because validation is missing. Fix: use canonical names, validate with `@ConfigurationProperties`, and verify effective configuration via secret-safe tests.

## 12. Spring config.import and External Config Files

When config resides outside the JAR, Spring Boot provides **Config Data** and **spring.config.import**:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/catalog/overrides.yml"
~~~

**optional:** lets the app continue if the file is absent; use it only when absence is valid. For critical configuration, use mandatory imports or fail-fast validation.

### Terms to Distinguish

- **spring.config.location:** controls where config is searched; can **replace** default locations depending on syntax.
- **spring.config.additional-location:** adds search locations alongside defaults.
- **spring.config.import:** imports additional config data inside a config document; precedence follows Spring Config Data semantics.
- **spring.config.name:** changes the base config file name searched.

Do not mix these properties without checking precedence for your Spring Boot version. In particular, avoid accidentally dropping default `application.yml` by misusing **spring.config.location**.

### Mounted Directories and configtree

For configuration trees (files named after keys containing values), Spring Boot supports **configtree:** imports in supported versions:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/catalog/secrets/"
~~~

This consumes a directory mounted by the platform; it does not create secrets or encrypt them on its own.

## 13. Do Not Use @Value for Every Property

Spring supports **@Value**:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogFeature {
    public CatalogFeature(
            @Value("${app.features.recommendations:false}")
            boolean enabled) {
        // Value is injected when the bean is created.
    }
}
~~~

`@Value` works well for a few simple values, but scattering 20 properties across multiple classes makes validation, documentation, and consistency checks difficult.

**@ConfigurationProperties** should be preferred for structured settings with type safety and validation.

## 14. @ConfigurationProperties: Type-Safe Binding

Suppose:

~~~yaml
app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 2
~~~

With Spring Boot 3.x, a Java record can use constructor binding per framework rules:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(0) int maxRetries) {
}
~~~

Spring Boot application:

~~~java
package com.example.catalog;

import com.example.catalog.config.ClientProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### Requirements

- The project includes **spring-boot-starter-validation** (or a compatible validator) to enforce Jakarta Bean Validation.
- The Spring Boot version supports record constructor binding as shown.
- Properties actually exist and convert cleanly to `Duration`/`int`.
- Java code injects **ClientProperties** to configure HTTP SDKs/clients; the record alone does not alter any API's timeout.

### Business-Level Validation

`@NotNull` prevents null `Duration` values and `@Min(0)` prevents negative retries. However, a **-1s** timeout, an excessively long timeout, or `readTimeout < connectTimeout` may need extra Jakarta constraints or a custom validator depending on design.

## 15. Fail Fast: Refuse to Start If Critical Config Is Missing

For example, a production API needs a catalog backend URL. If the URL is missing and the app falls back to **http://localhost:8081**, an AKS pod may report Running while sending requests to itself or the wrong address.

### Principles

1. Mandatory config must never have defaults pointing to localhost or prod by mistake.
2. Enable validation on `@ConfigurationProperties`.
3. Validate URL schemes (HTTPS when required), hostnames, and timeout bounds.
4. Verify credentials/identity at the appropriate startup phase.
5. Ensure logs report the **missing key name**, never secret values.
6. Never catch all startup errors and continue running with insecure defaults.

### Example to Avoid

~~~yaml
spring:
  datasource:
    password: "${DB_PASSWORD:admin123}"
~~~

If **DB_PASSWORD** is missing, the app may use a hard-coded password. For production secrets, omitting any default fallback is safer:

~~~yaml
spring:
  datasource:
    password: "${DB_PASSWORD}"
~~~

Still, **DB_PASSWORD** remains a secret in the process environment; prefer secret references or managed identity and review container/process access policies.

## 16. Local Development Should Never Mimic Production with Real Secrets

On a laptop:

- Use local services/emulators where appropriate.
- Use narrowly scoped **dev** resources.
- Use Azure CLI/developer identities granted least privilege.
- Use synthetic sample datasets.
- Never download a production dump containing PII just to make testing easier.
- Use `.gitignore` and organization-approved local secret/IDE run configurations.

~~~text
Laptop Spring Boot (local profile)
        |
        +--> Local test DB / dev Azure SQL
        +--> Dev Blob container
        +--> Dev App Configuration
        +--> Dev Key Vault (if needed)
        |
        v
No default access to prod data
~~~

### Never Use an Azure Production Principal for Local Profiles

If a developer uses the same managed identity/service principal granted production rights, one mistaken command or test can alter real data. Dev identities should be blocked by RBAC and network controls even if application config is mispointed.

## 17. Azure App Service: Application Settings

In **Azure App Service**, most configuration is supplied via **Application Settings**. They appear as process environment variables according to the runtime/hosting mode. A Spring Boot web app may receive:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:sqlserver://<sql-fqdn>:1433;databaseName=catalog
APP_CLIENT_CONNECTTIMEOUT=2s
APP_FEATURES_RECOMMENDATIONS=false
~~~

These are illustrative names/values. JDBC URLs and SQL Server encryption settings must use the right driver and organizational TLS policy, not merely rely on the FQDN.

### Deployment Flow

~~~text
Git/CI -> Spring Boot JAR/container image
              |
              v
          Azure App Service
              |
              +-- App Settings (env-specific)
              +-- Managed Identity
              +-- Key Vault references if configured
              +-- VNet Integration + private routes
              |
              v
         Spring Environment
              |
              v
         Application beans
~~~

### Points of Attention

1. **App Service config changes** can trigger a restart or require reload depending on the setting type; do not assume every change is automatically zero-downtime.
2. Never log the full process environment or all app settings.
3. Verify the identity attached to each slot and its distinct permissions.
4. If App Service connects to a database/private endpoint, configure VNet integration, DNS, and firewalls properly.
5. Platform-managed runtime settings such as ports/health probes interact with Spring configuration; do not override them arbitrarily.

## 18. App Service Deployment Slots: Which Settings Swap?

Deployment slots support deploying to staging and swapping to production depending on plan/feature support. However, if settings are not pinned to the right slot, a swap can leave production pointing at staging endpoints or vice versa.

~~~text
App Service: catalog-api
      |
      +-- Slot production
      |      SPRING_PROFILES_ACTIVE=prod
      |      PROD_SQL_ENDPOINT=...
      |      PROD_KEYVAULT_REFERENCE=...
      |
      +-- Slot staging
             SPRING_PROFILES_ACTIVE=staging
             STAGING_SQL_ENDPOINT=...
             STAGING_KEYVAULT_REFERENCE=...
~~~

### What Is a Slot Setting?

Certain application settings can be marked as a **deployment slot setting** (sticky): the value stays bound to the slot and does not move with the app content during a swap under App Service semantics.

### Pre-Swap Checklist

- **prod** profile and production connection targets must stay bound properly.
- Secret references, endpoints/callback URLs, and config service connections classified as sticky vs. non-sticky.
- Each slot's managed identity/roles have permission only for its target resources.
- Health/readiness probes and warm-up behave properly.
- No migration jobs or background tasks run in the wrong slot or duplicate work.
- Swap rollback plan and error-rate monitoring are ready.

**Never assume every setting is automatically sticky**. Check each setting type, slot flags, platform behavior, and swap workflow.

## 19. App Service: Inspecting Metadata via Azure CLI

The following commands **read metadata** and should run in an authorized administrative environment:

~~~bash
az account show \
  --query "{subscription:id,tenant:tenantId}" \
  --output json

az webapp show \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<LAB_WEBAPP>" \
  --query "{name:name,state:state,kind:kind,hostNames:hostNames}" \
  --output json
~~~

**Do not blindly run `az webapp config appsettings list` and share its output**, because some settings may contain secret values. When investigating config, use auditing-safe approaches that show **only key names or redacted values**.

### Configuration Changes Must Follow Change Control

Updating application settings via Portal, CLI, or IaC is a **runtime write operation**. It can be demonstrated in a lab, yet there is no reason to modify production settings just to test a profile. Use staging and an approval workflow.

## 20. Azure Container Apps: Environment Variables and Secrets

**Azure Container Apps** runs containerized apps with revisions, scaling, and networking capabilities scoped to a Container Apps environment. An app can receive configuration from:

- Container environment variables.
- Container Apps secrets and secret references.
- Managed identity.
- Service discovery/ingress settings.
- External config sources such as App Configuration/Key Vault via integrations.

~~~text
Container Apps Environment
          |
          v
Container App: catalog-api
  Revision R1
    Image digest: sha256:...
    SPRING_PROFILES_ACTIVE=prod
    APP_CLIENT_CONNECTTIMEOUT=2s
    DB_PASSWORD=<secret reference, not raw source>
          |
          v
Spring Boot starts with effective config
~~~

### Revisions and Config Changes

Changing the container image or revision-scope properties creates a new revision; application-scope settings behave differently. **Do not assume editing a secret immediately reloads every running revision**: check secret injection, restart, and rollout semantics, then verify.

### Questions to Answer

1. Where are secrets created and who can view/modify them?
2. Are Key Vault references supported and does the identity hold permissions?
3. Are environment variables present at process startup?
4. Has the new revision picked up the updated configuration values?
5. With scale-to-zero, does startup depend on config/network sources with adequate timeouts?
6. Can you roll back to a prior revision and still read compatible secrets/config?

**Container Apps secret store does not replace application-level authorization**; permissions to read Azure SQL/Storage data remain separate.

## 21. AKS: ConfigMap, Secret, and Pod Environment

On **Azure Kubernetes Service (AKS)**, Kubernetes provides:

- **ConfigMap:** non-sensitive configuration data.
- **Secret:** sensitive data; default YAML/base64 format is not encrypted security if stored in Git.
- **Pod env/envFrom:** injects keys into the process environment.
- **Mounted volumes:** delivers file-based config/secrets.
- **Secrets Store CSI Driver and Azure Key Vault provider:** reads secrets from Key Vault per supported configuration.
- **AKS Workload Identity:** uses federated identity to access Azure services per granted roles.

~~~text
Kubernetes Deployment
       |
       +-- ConfigMap -> APP_CLIENT_CONNECTTIMEOUT
       +-- Secret / CSI -> DB_PASSWORD or mounted file
       +-- ServiceAccount -> Workload Identity
       |
       v
Spring Boot container
       |
       v
Database / Key Vault / Storage over approved network
~~~

### ConfigMaps Are Not for Passwords

Never store API keys, database passwords, or private keys in a ConfigMap just because you want them mounted as files. Kubernetes Secrets also require **RBAC, encryption at rest/etcd policies, auditing, cluster access restrictions**, and proper integrations; Base64 is encoding, not encryption.

## 22. AKS: Example Deployment Configuring Spring Boot

**Abbreviated** YAML example for a lab namespace illustrating env names and secret references; not a complete production manifest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: catalog-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: app
          image: myregistry.example/catalog-api:lab-image-digest-placeholder
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "staging"
            - name: APP_CLIENT_CONNECTTIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: catalog-config
                  key: client-connect-timeout
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: catalog-secrets
                  key: db-password
~~~

### Prerequisites for This Manifest to Work

- The Namespace, ConfigMap, and Secret exist in the target cluster/namespace.
- A real container image is built and pullable.
- Kubernetes admission, Pod Security, and resource limits are configured appropriately.
- Service/ingress/probes/volumes must be added per architecture.
- If using AKS Workload Identity, ServiceAccount annotations and federation configuration are required per docs—they do not appear automatically from this snippet.

**Never run `kubectl apply` against production** just to experiment with lesson settings; create resources in a lab cluster with clear ownership and cleanup plans.

### Do ConfigMap/Secret Changes Auto-Reload?

Kubernetes env vars are typically injected at **container start**. Updating a ConfigMap/Secret while a Pod is running **does not automatically update environment variables inside the running process**. Volume mounts follow different update semantics depending on configuration; Spring Boot also does not refresh bean values without an explicit reload mechanism.

Therefore, use a **tested rollout/restart or dynamic refresh integration** rather than updating a Secret and assuming every Pod already sees the new value.

## 23. App Service, Container Apps, and AKS: Comparison

| Aspect | App Service | Container Apps | AKS |
|---|---|---|---|
| Abstraction level | Web app platform | Managed container app/revisions | Managed Kubernetes control plane, self-managed Pods |
| Standard config | Application Settings | Env vars/config revisions | ConfigMap, env, files |
| Secrets | App settings/Key Vault references | Secrets/Key Vault refs per support | Kubernetes Secrets/Key Vault CSI |
| Identity | Managed identity | Managed identity | Workload Identity/managed identities by design |
| Releases | Slots/continuous deployment | Revisions/traffic splitting | Deployments/rollouts, GitOps |
| Networking | VNet Integration and private access per plan | Container Apps environment networking | VNet/CNI/NetworkPolicy/egress |
| Config refresh | Restart/app behavior | Revision/restart/integration | Rollout or supported reload |
| Complexity | Lower for simple web APIs | Moderate, container-oriented | Higher, maximum Kubernetes flexibility |

**No single platform is universally best**. Choose based on platform needs, traffic/scale, networking, compliance, ops team skills, and cost. Configuration delivery must align with the chosen platform.

## 24. Azure App Configuration: Centralized Configuration

**Azure App Configuration** provides centralized management for **key-values, labels, feature flags**, and integrations for applications to consume settings.

~~~text
Azure App Configuration
    Keys / labels / feature flags
       |
       | Authentication via managed identity
       v
Spring Boot application
       |
       +-- Binding to Environment/properties
       +-- Feature management integration
       +-- Refresh behavior (when configured)
       |
       v
Application behavior
~~~

### When to Use It?

- Multiple Spring Boot services share a configuration set.
- You want version/label tracking and controlled config rollouts.
- Feature flags or kill switches are needed.
- Multi-environment configuration must be managed without rebuilding apps.
- A platform/service owner governs key standardization.

### When Is It Unnecessary?

A small app with a handful of non-sensitive variables is often well served by `application.yml` and platform environment variables. Adding App Configuration introduces another **network dependency, identity, billing item, and operational workflow**, so ensure clear value.

## 25. Keys and Labels: Managing Multiple Environments

An App Configuration store can hold settings keyed by key and label:

| Key | Label | Illustrative value |
|---|---|---|
| catalog:client:timeout | dev | 10s |
| catalog:client:timeout | staging | 4s |
| catalog:client:timeout | prod | 2s |
| catalog:features:recommendations | dev | true |
| catalog:features:recommendations | prod | false |
| catalog:checkout:max-retries | prod | 1 |

A **Label** is App Configuration metadata, not a Spring profile itself. Spring profile **prod** and App Configuration label **prod** only correlate when the integration is configured to select that label.

### Key Design Strategy

- Pick a consistent namespace: **service:component:property**.
- Separate global defaults from environment-specific overrides.
- Assign an owner and meaning to every key.
- Never enter secrets as plaintext config values.
- Avoid confusing **key** and **label**.
- Define behavior when a key or label does not exist.

### Multiple Sources Can Conflict

If `application.yml` says `timeout=5s`, App Configuration label `prod` says `2s`, and an environment variable says `1s`, the winning value depends on **how the integration loads PropertySources and Spring Boot precedence**. Test empirically and document which source is authoritative.

## 26. Reading Azure App Configuration via Java SDK

Example **reading only a single non-sensitive key/value** with the Azure SDK for Java:

~~~java
import com.azure.data.appconfiguration.ConfigurationClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.data.appconfiguration.models.ConfigurationSetting;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class AppConfigurationReadLab {
    public static void main(String[] args) {
        String endpoint = System.getenv("APP_CONFIG_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalStateException(
                "Missing APP_CONFIG_ENDPOINT");
        }

        ConfigurationClient client =
            new ConfigurationClientBuilder()
                .endpoint(endpoint)
                .credential(
                    new DefaultAzureCredentialBuilder().build()
                )
                .buildClient();

        ConfigurationSetting setting = client
            .getConfigurationSetting(
                "catalog:client:timeout", "dev");

        // Print only allowed key/label; never log sensitive values.
        System.out.println("Read key: " + setting.getKey());
    }
}
~~~

### Prerequisites

1. Compatible versions of **com.azure:azure-data-appconfiguration** and **com.azure:azure-identity**.
2. An existing App Configuration store/endpoint.
3. Identity granted **App Configuration Data Reader** or equivalent supported permission.
4. Valid firewall/private endpoint/network path.
5. Key **catalog:client:timeout** with label **dev** exists.
6. SDK/API signatures verified against the version in use.

**This is raw SDK code to read a setting**; it does not bind values into Spring `Environment`. For automatic Spring loading, use the Spring Cloud Azure App Configuration integration or an appropriate `PropertySource`.

## 27. Spring Cloud Azure and Spring Boot

**Spring Cloud Azure** supplies starters and integrations connecting Azure services with Spring idioms. Versions must align with **Spring Boot** (never pull old versions from stale blog posts).

Supported modules include:

- Azure App Configuration as a configuration source.
- Azure Key Vault secrets via supported configuration integrations.
- Managed identity/credentials via Azure Identity.
- Starters for Storage, Service Bus, and additional services.

### What Must Be Configured?

An App Configuration integration typically needs:

1. Store endpoint.
2. Credential/managed identity.
3. Key selectors and labels.
4. Optional vs. fail-startup behavior.
5. Refresh rules if needed.
6. Retries, caching, networking/timeouts.

Starter property names and **spring.config.import** protocols can change across versions. **Do not copy a YAML snippet from Spring Cloud Azure 4.x into 5.x/6.x without checking the matching reference documentation**.

### Do Not Arbitrarily Import Two BOMs

Spring Boot and Spring Cloud Azure rely on dependency management to align versions. If an app also imports a standalone Azure SDK BOM, inspect resolved versions of **azure-core, azure-identity, Reactor/Netty** and verify compatibility. Never add blind explicit overrides to silence a runtime error.

## 28. Azure App Configuration and Dynamic Refresh

Some integrations support refreshing configuration without deploying a new image. However, **refresh does not mean every Java bean updates itself automatically**.

~~~text
Operator updates App Configuration key
          |
          v
Store version/ETag changes
          |
          v
Spring integration checks refresh (if configured)
          |
          v
PropertySource / refresh-aware bean updates
          |
          v
Effective application behavior
~~~

### Questions to Confirm

- Does refresh use polling, a sentinel key, or event-driven triggers per the integration?
- What is the refresh interval and maximum stale window?
- Which beans get **refreshed/rebound** vs. needing recreation/restart?
- Does secret/key rotation refresh alongside config?
- When App Configuration is unavailable, does the app use cached values, fail startup, or fall back?
- How do you verify config rollout consistency across 100 replicas?

### Values You Should Not Hot-Reload Arbitrarily

- Database connection URL/username or credentials inside an active connection pool.
- TLS truststores, certificates, or socket settings.
- Large bean graphs with complex initialization dependencies.
- Security policies requiring atomic synchronized transitions.

For such changes, a controlled rollout/restart is usually far more reliable than expecting live beans to reconnect cleanly.

## 29. Feature Flags Differ from Spring Profiles

Spring profiles suit **environment configuration or bean wiring**. **Feature flags** suit toggling behavior without changing environments.

~~~text
Profile: prod
   |
   +-- Database prod
   +-- Secure logging
   +-- Retry policy prod

Feature flag: recommendations-enabled
   |
   +-- Disabled for most users
   +-- Enabled for an approved test segment
   +-- Roll back when latency/errors exceed threshold
~~~

### Feature Management Does Not Automatically Build Rigorous A/B Tests

Percentage or segmented rollouts require identity handling, assignment stickiness, monitoring, and business metrics. Users should not see behavior flip randomly between requests when consistent assignment is expected.

**Never rely on a feature flag as the sole protection for sensitive data**. Server-side authorization, RBAC, and input validation remain mandatory.

### Kill Switch

A feature flag can temporarily disable heavy operations during backend distress, yet if App Configuration itself becomes unreachable, the kill switch might fail to reach the app. Ensure caching, rollout, and fail-safe defaults are tested.

## 30. Azure Key Vault: Where Secrets Belong

Azure Key Vault manages sensitive assets such as **secrets, keys, and certificates** with proper permissions, auditing, and lifecycle governance.

~~~text
App Service / Container App / AKS Pod
        |
        | Managed/Workload Identity
        v
Microsoft Entra ID
        |
        v
Azure Key Vault
        |
        +-- db-password
        +-- api-key
        +-- certificate reference
        |
        v
Spring Boot runtime (secret injected when needed)
~~~

### Do Not Confuse Key Vault with App Configuration

| Azure App Configuration | Azure Key Vault |
|---|---|
| Config key-values, labels, feature flags | Secrets, keys, certificates |
| Selected by environment/service | Protects secrets with granular authorization |
| Supports config refresh per integration | Supports secret versions and rotation workflows |
| Should not store plaintext passwords | Built for safeguarding passwords/API keys when required |
| Requires App Configuration Data Reader role | Requires appropriate Key Vault data-plane permissions |

### Rotating a Secret Is a Workflow

1. Create/publish the new secret version.
2. Ensure the runtime identity has read access.
3. Define version selection (`latest` vs. pinned) and cache TTL.
4. Trigger app refresh/restart/reconnect as needed.
5. Verify authentication against the target system.
6. Revoke the old secret at the appropriate cutover time.

**Updating a Key Vault secret version does not automatically make an active database connection pool using the old password valid or refreshed.**

## 31. Reading a Key Vault Secret via Java SDK

The Java example below builds a **SecretClient** without printing the secret to the console:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class KeyVaultReadLab {
    public static void main(String[] args) {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("Missing KEY_VAULT_URL");
        }

        SecretClient client =
            new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(
                    new DefaultAzureCredentialBuilder().build()
                )
                .buildClient();

        KeyVaultSecret secret = client.getSecret("lab-service-key");
        // In this example only confirm metadata; never log getValue().
        System.out.println("Secret name: " + secret.getName());
    }
}
~~~

### Security Analysis

- The SDK requires **com.azure:azure-security-keyvault-secrets** and **azure-identity**.
- The identity needs **get secret** permission in the Key Vault scope; Azure resource Reader alone is insufficient.
- Use the HTTPS Key Vault FQDN; check DNS, private endpoints, and TLS.
- **getSecret** is a read operation that generates audit logs and service transaction costs.
- Never put secret values in application logs, trace attributes, exceptions, or test snapshots.
- Never run this snippet against a production secret just to verify a lesson exercise.

In real applications, integrations may expose secrets as Spring properties or injected environment variables. Either way, define **in-memory secret lifetime**, reload mechanics, and access boundaries.

## 32. Key Vault References: Resolving References by Platform

Some Azure hosts like App Service support **Key Vault references** in app configuration so the platform resolves secrets on the app's behalf instead of developers pasting raw secrets into settings.

~~~text
App setting DB_PASSWORD
     |
     | Platform Key Vault reference syntax
     v
App Service runtime resolves reference
     |
     | Managed identity with get secret permission
     v
Key Vault
     |
     v
Runtime receives resolved setting
~~~

### Understand Correctly

- A reference is not a magic placeholder that works on every host.
- The platform must support that reference type and have identity configured.
- **Refresh/cache semantics** vary; do not assume changing a secret updates the running process immediately.
- Networking to Key Vault must succeed, especially with private endpoints/firewalls.
- If the secret URI pins a specific version, rotating to a new version will not auto-advance.

On AKS, Kubernetes Secrets/CSI volumes and Workload Identity follow a different model. Never put App Service Key Vault reference syntax into a ConfigMap expecting AKS to resolve it.

## 33. Managed Identity and Workload Identity

Managed identity lets an Azure workload obtain Entra access tokens without storing long-lived client secrets in images or repositories.

~~~text
Spring Boot service running on Azure
       |
       v
Managed Identity / AKS Workload Identity
       |
       v
Microsoft Entra token
       |
       +--> Azure Key Vault
       +--> Azure App Configuration
       +--> Azure Storage (SDK)
       +--> Azure SQL passwordless (when stack supports)
~~~

### Three Essential Steps

1. Create/attach the identity to the compute resource properly.
2. Grant **data-plane roles/permissions** on Key Vault/App Configuration/Storage/SQL.
3. Ensure networking/DNS and SDK/driver auth settings align.

**Attaching an identity does not grant permissions automatically**. An HTTP 403 may stem from missing App Configuration Data Reader, Key Vault Secrets User, or Storage Blob Data Reader depending on the resource and RBAC mode.

### User-Assigned Managed Identity

When an app has multiple identities, specify the intended identity (typically via client ID) per the Azure Identity SDK/integration. Never let `DefaultAzureCredential` silently pick a different identity and access the wrong environment.

## 34. DefaultAzureCredential: Local and Production Differ

In Java:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

TokenCredential credential =
    new DefaultAzureCredentialBuilder().build();
~~~

On a laptop, the credential chain may pick up a signed-in developer tool; in an Azure runtime, it uses managed/workload identity. **Same line of Java code, different underlying principal**.

### Do Not Guess on a 403

A developer can read the dev Key Vault while a production pod gets 403. That does not prove an SDK bug: the production identity may lack a role assignment, or it may be targeting a different vault or tenant.

### Production Security

- Use a workload-bound identity with scoped permissions.
- Verify tenant ID and client ID when needed.
- Prevent developer credentials from slipping into production environments.
- Never set **AZURE_CLIENT_SECRET** inside a container as a quick workaround without a rotation plan.
- Log principal identifiers per audit policy; **never log access tokens**.

## 35. External Secrets Do Not Solve Every Security Requirement

A secret stored in Key Vault can still leak if:

- Process dumps or startup logs print the entire Spring Environment.
- The app exposes sensitive Actuator endpoints.
- Testers save secrets into CI artifacts or reports.
- Containers allow unrestricted `exec`/debug access.
- Service identities hold broader permissions than necessary.
- TLS verification is disabled to bypass Private Endpoint/DNS errors.

### Defense in Depth

1. Least-privilege Key Vault data-plane RBAC.
2. Separate Entra identities per environment.
3. Private networking and TLS where required.
4. Log redaction and minimal Actuator exposure.
5. Rotation/expiry alerts and incident response.
6. Effective data authorization checks inside the application.

No "secret store" renders sensitive values harmless once loaded into application memory.

## 36. Connecting to Azure SQL per Environment

A Spring Boot service typically uses a `DataSource`/JDBC connection pool. Separate JDBC URL, username, authentication, and pool settings per environment:

~~~yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USER}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
~~~

This example represents a **password-based JDBC flow** when permitted by organizational policy; you can adopt Microsoft Entra passwordless authentication where supported by the JDBC driver, Spring Cloud Azure integration, and Azure SQL configuration.

### Do Not Confuse Database URLs with Secrets

A JDBC URL and hostname are usually configuration, yet they can contain usernames/passwords or tokens in query parameters; in that case the whole string is sensitive. Never print full JDBC URLs in error logs without stripping credentials.

### Deployment Verification Points

1. Database server FQDN, region, and database name.
2. Azure SQL firewall/Private Endpoint/DNS/VNet routing.
3. TLS and JDBC driver certificate validation.
4. Database login/Entra principal and **schema/table** permissions.
5. Hikari max pool size scaled against total replica count.
6. Timeouts/retries aligned with request deadlines.
7. Are schema migrations run exactly once with proper approvals?

### Connection Pools and Autoscaling

~~~text
30 replicas
  x 10 connections/replica
  = 300 potential connections
~~~

If the database tier cannot handle that load, autoscaling more pods increases connection pressure. Size pool limits and max replicas together against database connection limits; never treat "pool 100 per pod" as safe just because JVM RAM has headroom.

## 37. Passwordless Connection with Microsoft Entra

An architecture can replace database passwords with Entra authentication:

~~~text
Spring Boot on Azure
       |
       v
Managed/Workload Identity
       |
       v
Microsoft Entra access token
       |
       v
Token-capable JDBC driver / integration
       |
       v
Azure SQL database principal + permissions
~~~

### Is spring.datasource.password Needed?

Not when using a passwordless flow properly, though **this depends on the driver, integration, authentication properties, database principal, and token refresh support**. Do not apply a password-based config file to a passwordless flow and simply substitute a one-time startup token for the password.

### Before Switching

- Verify the Microsoft JDBC Driver for SQL Server and supported authentication mode.
- Create/grant the database principal and permissions for the managed identity.
- Verify token refresh behavior for long-lived connection pools.
- Test reconnects, failovers, network interruptions, and token expiry.
- Keep a rollback plan that does not inject production secrets into source or CI logs.

**Passwordless removes static secret maintenance**, not IAM, TLS, firewall, or auditing requirements.

## 38. Redis, Service Bus, and Storage: Separate Config Too

A microservice may communicate with multiple Azure resources:

~~~text
catalog-api (prod profile)
    |
    +-- Azure SQL:   prod SQL server/database
    +-- Redis:       prod Redis FQDN/TLS port
    +-- Service Bus: prod namespace/queue
    +-- Blob:        prod storage endpoint/container
    +-- Key Vault:   prod vault URL
    +-- App Config:  prod store endpoint/label
~~~

### Custom Keys Example

~~~yaml
app:
  azure:
    blob-container: "${AZURE_BLOB_CONTAINER}"
    service-bus-queue: "${AZURE_SERVICEBUS_QUEUE}"
    redis-host: "${REDIS_HOST}"
    redis-tls-port: "${REDIS_PORT}"
~~~

These are custom properties; instantiating SDK clients requires Java code or the corresponding Spring Cloud Azure integration. Do not share one monolithic **AZURE_CONNECTION_STRING** holding multiple secrets across services just to reduce variable count.

### Isolate Namespaces at Every Layer

Different profiles are not enough if environment variables still point to a production resource. Use **distinct resource identifiers/names, separate identities, RBAC, and network policies** to prevent cross-environment access.

## 39. Private Endpoint and DNS: Config Error or Infrastructure Error?

~~~text
Java pod/App Service
       |
       | resolve storage/database FQDN
       v
DNS resolver + Private DNS zone
       |
       v
Private IP / approved endpoint route
       |
       v
Azure resource with firewall and identity checks
~~~

### A Request Can Fail at Multiple Layers

| Error | Common cause | Check to perform |
|---|---|---|
| UnknownHostException | Wrong hostname or unlinked private DNS | Resolve from the workload runtime |
| Connect timeout | Route, firewall, NSG, port, or endpoint block | Inspect TCP path |
| SSLHandshakeException | CA, hostname, SNI, or truststore | Inspect TLS chain and FQDN |
| HTTP 401 | Credential/token/audience | Entra auth logs and identity |
| HTTP 403 | Data-plane role or service firewall | Principal, RBAC, firewall diagnostics |
| SQL login failed | Database principal/auth mode/permissions | SQL logs and JDBC config |
| Connection pool exhausted | Too many replicas/connections or slow network | Pool metrics and DB limits |

**Never open public network access to all IPs or disable TLS verification just to push past an error**. Private Endpoints require DNS, routing, service firewalls, and identity to align.

### Profiles Do Not Control VNets

Setting **SPRING_PROFILES_ACTIVE=prod** does not route traffic over a Private Endpoint. Networking lives in Azure infrastructure and container environments, managed via IaC and verified independently.

## 40. Actuator: Application Health and Configuration Insights

**Spring Boot Actuator** can expose health, metrics, and management endpoints depending on dependencies and configuration:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Paths may differ if the app customizes the management base path/port or uses different probe paths. Enable only endpoints and probes approved by your organization.

### Three Signal Types

| Signal | Meaning | Avoid |
|---|---|---|
| **Liveness** | Is the process/app still alive to serve? | Unnecessary coupling to external DBs |
| **Readiness** | Can the pod/instance accept traffic right now? | Treating readiness as proof every external service is healthy |
| **Startup** | Has the app had enough time to boot? | Restart loops during slow JVM warm-up/JIT/config fetch |

### A Cascade-Failure Trap

If a liveness probe checks Redis/SQL availability, a brief Redis blip can trigger Kubernetes to restart hundreds of pods simultaneously, amplifying a connection storm.

Keep liveness independent of external dependencies; scope readiness to traffic-serving needs with timeouts and fallbacks. Test on the target platform rather than checking HTTP 200 once.

## 41. Actuator /env and /configprops: Secret Exposure Risks

Spring Boot Actuator offers endpoints like **/actuator/env** and **/actuator/configprops** when enabled. They aid diagnostics yet risk leaking sensitive settings if exposure or sanitization is misconfigured.

### Safety Policy

- Never expose all management endpoints to the public Internet.
- Expose only **health/info** or specifically reviewed endpoints.
- Protect management ports/paths with authentication and network policies where supported.
- Do not rely blindly on default sanitization behavior.
- Never dump the entire Spring Environment at startup.
- Restrict access to logs, heap dumps, thread dumps, and process environments.

**Sensitive data can also leak through exception messages or connection URLs**, not just Actuator. Before enabling debug config output, review what gets emitted.

## 42. Log Levels, Sampling, and Per-Environment Settings

~~~yaml
# application.yml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
~~~

~~~yaml
# application-dev.yml
logging:
  level:
    com.example.catalog: DEBUG
~~~

~~~yaml
# application-prod.yml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
~~~

### What Does Production Debugging Require?

During an incident, you may briefly raise the log level for one package under change control, provided:

- You do not enable payload/header logging containing tokens or passwords.
- There is an automatic revert deadline and an owner.
- Log retention and access are restricted.
- Log ingestion volume and Log Analytics/Application Insights cost are tracked.
- `DEBUG` is never left as the permanent default in prod.

### Correlation IDs

Logs should include **traceId/correlationId, service, environment, application version**, operation outcome, and latency. Never allow PII into environment names and never put secrets into log tags.

## 43. Retries, Timeouts, and Circuit Breakers per Environment

An API running in Azure may call SQL, Redis, Service Bus, or REST services. Timeout and retry policies vary by network and SLO:

~~~yaml
app:
  remote:
    connect-timeout: 1s
    read-timeout: 3s
    max-retries: 2
    circuit-breaker-enabled: true
~~~

### Critical Limits

- If the HTTP SLO is 300 ms, a 3s read timeout will blow the request-path budget; these numbers **only illustrate config structure**.
- Retries need an **overall deadline**, bounded attempts, and backoff/jitter.
- Do not retry 401/403 indefinitely when the principal lacks permissions.
- Side-effecting writes require idempotency.
- Circuit breaker fallbacks must stay business-safe—never bypass authorization or financial limits.

### Config Does Not Activate Behavior Automatically

If code never binds **app.remote.max-retries** to RestClient/WebClient/Resilience4j/SDK clients, changing YAML changes nothing at runtime. Write **integration tests** proving configuration reaches the actual beans.

## 44. Startup When Config Services Fail

An application loading App Configuration/Key Vault at startup follows:

~~~text
Spring Boot startup
      |
      +--> Resolve App Configuration
      +--> Resolve Key Vault secret/reference
      +--> Build database/DataSource clients
      +--> Start web server / readiness
~~~

### Two Policies

**Fail fast:** if mandatory config is missing, refuse to become ready. Appropriate when continuing could connect to the wrong target or create a security gap.

**Graceful fallback:** if optional config is missing, fall back to an approved local/cached value and emit an alert. Suitable for non-critical features that introduce no safety risk.

### When App Configuration Is Unreachable

Do not blindly fall back to defaults. If a **disable-payments** flag cannot be read and the app defaults to enabling payments, business safety fails. Pick fallback behavior per criticality, define stale TTL/ownership, and test with network connectivity severed.

### Configuration Cache

SDKs and integrations cache configuration in different ways. **Config staleness** is an operational property that must be measured and documented, especially when flags serve incident response.

## 45. Configuration Drift and a Single Source of Truth

**Configuration drift** occurs when live runtime state diverges from desired state:

~~~text
IaC (desired):
   APP_FEATURES_RECOMMENDATIONS=false

Portal hotfix:
   APP_FEATURES_RECOMMENDATIONS=true

Actual production:
   true

Next IaC deployment:
   may revert to false or fail on conflict
~~~

### Prevention

1. Manage non-sensitive config via reviewed Git/IaC.
2. Use Key Vault for secrets with auditing/rotation.
3. Restrict direct Portal edits in production.
4. Record an owner and reason for any emergency override.
5. After a hotfix, reconcile **desired state** or perform a deliberate rollback.
6. Run deployment verification to catch mismatched settings.

**Never export full effective configuration containing secrets into diff artifacts**. Compare key names, valid hashes, version IDs, or policy-redacted values.

## 46. IaC and Managing Configuration Across the Application Lifecycle

Tools such as **Bicep, ARM templates, Terraform, Helm, and GitOps** help declare:

- Azure resources and networking.
- App Service settings and slot flags.
- Container Apps environment variables and secret references.
- Kubernetes ConfigMaps/Secret references and rollout behavior.
- Identity assignments and RBAC.
- App Configuration keys/labels per approved workflows.

### Keep Secrets Out of IaC State and Logs

A template with a raw password field can leak via source, pipeline variables, plans/state files, or outputs. Use **Key Vault references, identity-based integrations, and native secret handling** instead of embedding real values.

### Recommended Workflow

~~~text
Pull Request:
  code change
  + config schema/defaults
  + infra config change
      |
      v
CI:
  compile/unit tests
  + config validation
  + IaC plan/policy scan
      |
      v
Approve DEV -> TEST -> STAGING
      |
      v
Canary/slot/revision rollout PROD
      |
      v
Smoke tests + monitor + rollback plan
~~~

You do not need to build a new container image just to flip a feature flag, yet **a critical config change still requires deployment-grade change control**.

## 47. Validating Configuration in CI Before Deployment

Useful validations:

| Category | Example |
|---|---|
| **Schema** | `app.client.read-timeout` parses as a valid `Duration` |
| **Required** | `PROD_SQL_ENDPOINT` is supplied in prod |
| **Range** | `max-retries` is non-negative and within limits |
| **Profiles** | `prod` does not accidentally activate a local-only bean |
| **Secrets** | No passwords or API keys in Git |
| **Identity** | Runtime managed identity holds required roles |
| **Endpoint** | Production never points to localhost or dev FQDNs |
| **Networking** | Private endpoint/DNS/port and TLS checks pass |
| **Security** | Actuator endpoints are restricted |
| **Observability** | Health, traceId, environment, log redaction |

### Separate Config Testing from Production Secret Testing

CI should not need access to all production secrets just to compile. Schema/config binding tests can use dummy values. **Smoke tests** in staging/prod run under each environment's own workload identity and secret references with least privilege.

## 48. Testing Spring Boot Profiles

An integration test can activate a profile:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void testProfileIsActive() {
        assertTrue(environment.acceptsProfiles(
            org.springframework.core.env.Profiles.of("test")
        ));
    }
}
~~~

### What Does This Test Prove?

It proves the Spring `Environment` has the **test** profile active in the test context. It **does not prove** that database URLs, HTTP timeouts, Key Vault permissions, or Azure Private Endpoints are correct.

### Better Tests

Add assertions on bound and validated **ClientProperties**, such as timeouts and `maxRetries` from `application-test.yml`; use dummy external services or container test environments without touching Azure production.

**Never rely on `@ActiveProfiles("prod")` alone to prove Azure production config is valid** when the test pipeline lacks production's external config sources, identities, and network paths.

## 49. Inspecting Effective Config Without Leaking Secrets

A deployment bug happens when `application.yml` sets `timeout=5s`, yet an App Service environment variable overrides it to `50s`. To investigate:

1. Confirm the active profile from **SPRING_PROFILES_ACTIVE**.
2. Record the application version and environment name.
3. Inspect property sources via safe administrative tooling.
4. For non-sensitive keys, compare expected values against what bound into the bean.
5. For secrets, check only **presence**, permitted secret version ID/metadata, or auth outcome—never print values.
6. Verify whether a configuration refresh/restart actually occurred.

### Good Log Example

~~~json
{
  "service": "catalog-api",
  "environment": "staging",
  "version": "1.8.0",
  "profiles": ["staging"],
  "configSource": "App Configuration",
  "configRevision": "approved-revision-42",
  "dbCredentialPresent": true,
  "startup": "success"
}
~~~

The field **configRevision** is an example of controlled metadata, not an automatic built-in property in Spring Boot or App Configuration. Never log **dbCredential** values or full URIs containing secrets.

## 50. Does a Configuration Change Require a Restart?

There is no single rule:

| Change type | What to verify |
|---|---|
| `application.yml` inside JAR | Usually requires a new artifact/restart to reload |
| App Service application setting | Restart/config semantics per platform |
| Container Apps revision env var | Revision/rollout semantics |
| Kubernetes Pod env from ConfigMap/Secret | Usually requires Pod restart/rollout to enter process env |
| Mounted file config | Volume refresh and Spring reload mechanism |
| App Configuration key | Integration refresh, cache interval, and bean rebinding |
| Key Vault new secret version | Secret reference cache/refresh and client reconnect |
| JDBC URL/credentials | Pool recreation/re-auth and business continuity |

### When Is a Deliberate Restart Better?

- Database endpoints or authentication settings change.
- TLS certificates or truststores need updating.
- Bean graphs or connection pools must reinitialize.
- Changing settings without a tested dynamic refresh mechanism.

**Dynamic refresh** fits certain feature flags, timeouts, or settings built to refresh; avoid forcing it onto arbitrary Spring beans.

## 51. Canary, Slot Swap, and Config Rollback

A new configuration can break production even with zero Java code changes:

~~~text
Production: config revision C1
      |
      v
Staging tests: config revision C2
      |
      v
Deploy canary/slot/revision C2
      |
      +-- Error rate/latency OK -> promote C2
      |
      +-- Threshold exceeded -> rollback C1
~~~

### What Must Be Rolled Back?

- Modified config key/label versions.
- Corresponding secret references/versions/identity permissions.
- Container image/Java artifact if code depends on the new config schema.
- DNS/network/Private Endpoint/IaC changes.
- Database schemas or migrations if applicable.

**Config rollback does not automatically roll back data**. For instance, enabling a feature that writes new schema rows and flipping the flag back to `false` leaves new data behind that older code may not understand. Plan backward-compatible migrations and feature rollouts.

### Metrics to Watch After Rollout

1. Startup failures, readiness failures, crash loops.
2. 401/403 identity/secret errors and 5xx backend errors.
3. API p95/p99 latency, timeouts, and retry counts.
4. Database connections and throughput.
5. Feature-level business metrics.
6. Log/telemetry ingestion volume and cost.

## 52. Optimizing Configuration Cost on Azure

Configuration management also incurs cost:

| Component | Cost drivers to evaluate |
|---|---|
| **Azure App Configuration** | Tier, requests, storage/replicas per features and pricing |
| **Azure Key Vault** | Secret/key operations, networking, service tier per pricing |
| **App Service/Container Apps/AKS** | Compute, networking, scaling, log volume |
| **Private Endpoints** | Endpoint/network charges per Azure pricing |
| **Azure Monitor/Log Analytics** | Ingestion, retention, queries |
| **Azure SQL/Redis/Storage** | Connections/load, transactions, data transfer |

### Too Many Reads Create Load Too

If every Java HTTP request calls Key Vault for the same secret, latency, cost, and throttling risk all climb. Normally you need **library- or platform-supported caching/refresh** rather than fetching secrets on every business request.

### Do Not Cache Secrets Indefinitely

Caching too long delays secret rotation taking effect. Balance **cost, rate limits, security policy, and secret refresh SLA**.

### How to Measure

- Request counts to App Configuration/Key Vault per service.
- Configuration refresh/error rates.
- Startup duration and instance scale events.
- Key Vault 429s and authorization failures.
- Log volume.
- Total Azure Cost Management broken down by resources/tags.

Do not hard-code fixed USD unit prices into designs since regions, tiers, and rates change. Estimate using the **Azure Pricing Calculator** and actual billing data.

## 53. Lab A: Verifying Profiles and Environment Precedence

**Objective:** verify whether Spring Boot loads the right values for local, dev, and prod without calling real Azure resources.

### Preparation

- A standalone Spring Boot 3.x Java project in a learning environment.
- `application.yml`, `application-dev.yml`, `application-prod.yml` per sections 6–7.
- `ClientProperties` and registration per section 14.
- Matching JDK and Spring Boot dependencies.
- No production databases or secrets required.

### Steps

1. Set **app.client.connect-timeout=2s** in `application.yml`.
2. Override it to **5s** in `application-dev.yml`.
3. Boot with **SPRING_PROFILES_ACTIVE=dev**.
4. Verify `ClientProperties.connectTimeout()` returns **5s**.
5. Set environment variable **APP_CLIENT_CONNECTTIMEOUT=900ms**.
6. Restart and verify binding returns **900ms**.
7. Clear the override variable and boot with profile **prod**.
8. Verify the timeout returns to the baseline or declared prod value.
9. Pass an invalid `Duration` in a test environment and verify **startup fails** rather than falling back to an insecure default.
10. Stop the app and clear test env variables from the shell/session.

### Acceptance Criteria

| Case | Expected value |
|---|---|
| No active profile, no override | 2s |
| Profile dev | 5s |
| Dev + APP_CLIENT_CONNECTTIMEOUT=900ms | 900ms |
| Profile prod, no matching key override | Baseline/prod value per file |
| Wrong type or validation failure | Startup fails naming the key, without leaking secrets |

**Never print the full Spring Environment** to verify results. Write assertions in unit/integration tests to avoid accidental secret logging.

## 54. Lab B: Spring Boot on Azure App Service Staging

**Objective:** supply configuration from the platform without modifying the JAR. Execute only on a **lab App Service**, never modifying production.

### Prerequisites

1. Authorized lab resource group and App Service.
2. Built test JAR/container image; never use real user data.
3. Permission to edit application settings within lab scope.
4. Dev Key Vault/endpoints if required by the exercise.
5. Confirmed tier supports deployment slots if testing swap.

### Procedure

1. Deploy the artifact to the lab Web App or staging slot.
2. Set **SPRING_PROFILES_ACTIVE=staging** in App Settings.
3. Set **APP_CLIENT_CONNECTTIMEOUT=1s** without hard-coding in the JAR.
4. Add another non-sensitive setting such as **APP_FEATURES_RECOMMENDATIONS=false**.
5. Start/restart per platform behavior and check health/readiness.
6. Test a functional endpoint verifying the bound timeout.
7. Attach managed identity and grant App Configuration Data Reader or Key Vault data access **only if approved for lab scope**.
8. If using Key Vault references, verify reference resolution without printing secret values.
9. Check app logs for absence of raw env vars, access tokens, or connection strings.
10. If testing slot swap, confirm **slot-sticky settings** and rollback readiness; never test swaps on production.

### PASS Criteria

- No rebuild required to change a timeout.
- Staging profile is active.
- App Health reports accurate status.
- Identity and network access only lab resources.
- No secrets in source or logs.
- Configuration change trail and rollback plan exist.

## 55. Lab C: AKS ConfigMap/Secret and Restart Semantics

**Objective:** understand the difference between file/runtime config and environment values already loaded into a running process.

### Preparation

- Lab AKS namespace with restricted RBAC.
- Test Spring Boot image containing no secrets.
- Lab ConfigMap and Secret—**not production**.
- Appropriate Pod security and network policies.

### Procedure

1. Create a ConfigMap containing **client-connect-timeout=2s** per lab guide.
2. Create a lab Secret with an approved dummy string, never a real password.
3. Deploy the illustrative config from section 22 to the lab namespace.
4. Confirm Pod Ready status and correct Spring binding.
5. Update the ConfigMap to **5s**, **without restarting the Pod**.
6. Observe: values injected via Pod environment **do not automatically change** inside the running process.
7. Perform a rollout restart per lab operating instructions.
8. Verify the new Pod picks up **5s**.
9. Confirm the Secret does not appear in logs or ConfigMaps.
10. Clean up lab resources per ownership rules.

### Key Takeaway

Kubernetes ConfigMaps and Secrets are part of platform configuration. Spring Boot does not automatically watch every Kubernetes resource change and refresh beans. Dynamic config requires an explicitly designed and tested **reloader/refresh mechanism**; otherwise perform a deliberate rollout.

## 56. Lab D: App Configuration and Key Vault with Least-Privilege Read

**Objective:** distinguish standard config from secrets while validating data-plane identity.

### Preparation

- Lab App Configuration store.
- Lab Key Vault.
- Narrowly scoped managed identity or developer identity.
- Java project with matching Azure SDK dependencies.
- **Dummy** lab key/value and secret.

### Steps

1. Create key **catalog:client:timeout** with label **dev** and value **2s** in the lab App Configuration.
2. Create secret **lab-service-key** in the lab Key Vault with a non-sensitive test string.
3. Assign App Configuration Data Reader to the target identity.
4. Grant **get** secret permission per the active Key Vault authorization model.
5. Run the read-only Java code from sections 26 and 31.
6. Verify only key/secret names are logged, never secret values.
7. Test an unprivileged identity **only in the lab** to observe the 403 error.
8. Evaluate private DNS, TLS, and networking when firewalls are active.
9. Test secret refresh/rotation without touching production secrets.
10. Remove or revoke lab-specific temporary permissions afterward.

### PASS Criteria

- Standard config is read from App Configuration.
- Secrets stay in Key Vault, readable only by authorized identities.
- Java auth uses Entra/managed identity instead of hard-coded client secrets.
- Logs contain no secret values or access tokens.
- Network errors and RBAC errors are cleanly distinguished.

## 57. Case Study: Multi-Environment Spring Boot E-Commerce Platform

A company runs catalog, checkout, and notification services:

- **Spring Boot 3.x** runs on Azure Container Apps in dev/staging.
- **AKS** runs part of the production Java services.
- **Azure SQL Database** stores orders and inventory.
- **Azure Redis** caches the catalog.
- **Azure Service Bus** handles order confirmation events.
- **Azure Blob Storage** stores product images.
- **Azure App Configuration** manages feature flags and timeouts.
- **Azure Key Vault** holds secrets not yet migrated to passwordless.
- **Microsoft Entra Workload Identity/managed identity** authenticates service access.
- Private Endpoints protect several data services.
- API p95 target is 250 ms; each deployment can scale 3–50 replicas.

### Problem Statement

During a release, staging works fine yet production hits three issues:

1. A new Container Apps revision enters a restart loop because **APP_CLIENT_CONNECT_TIMEOUT** fails to bind to **app.client.connect-timeout**; a wrong fallback config makes the client timeout too long.
2. An AKS Pod reads App Configuration successfully but fails to fetch a Key Vault secret because Workload Identity lacks data-plane permissions.
3. The production API uses a JDBC pool of 30 connections per Pod; when scaling to 50 Pods, the database overloads.

### Analysis Tasks

1. Build a config ownership table: image/default, App Configuration, Key Vault, platform env.
2. Pick the canonical env var name for timeout and add startup validation.
3. Explain why selecting the **prod** profile still fails to guarantee correct endpoints/resources.
4. Separate identities and Key Vault data-plane roles per service.
5. Verify Private Endpoint/DNS/TLS from inside an AKS Pod rather than a laptop.
6. Compute potential total database connections.
7. Tune pool size and max replicas against the Azure SQL tier and load-test measurements.
8. Design retry deadlines compatible with a 250 ms p95 target.
9. Decide which configs should dynamically refresh vs. trigger rollout restarts.
10. Design App Service slots, Container Apps revisions, or AKS rolling updates for canarying.
11. Propose a config rollback strategy that avoids corrupting data.
12. Design alerts for auth failures, startup readiness, and DB connection exhaustion.
13. Reconcile emergency config overrides back into IaC desired state post-incident.
14. Define metrics proving a feature rollout succeeded.

### Solution Direction

**Timeout:** Use canonical **APP_CLIENT_CONNECTTIMEOUT** for **app.client.connect-timeout**, bind to a validated `ClientProperties` record, and test production-like effective config before rollout.

**Key Vault:** Identify the Pod's actual ServiceAccount/workload identity or managed identity, assign secret read permission on the right lab/prod vault scope, and inspect federation, Key Vault networking, and 403 logs. Never embed an access key in source to dodge the error.

**Database:** **50 pods × 30 connections = 1,500 potential connections**, excluding background jobs and rollout surges. Size pools around workload, max replicas, and DB capacity; never scale pods without bounds if SQL cannot handle the connections.

**Rollout:** Keep the image digest fixed, canary config via revision/Deployment, check readiness, p95/5xx/auth errors, and only then ramp traffic. Revert to approved config if metrics degrade; schema/data changes require a separate rollback plan.

## 58. Common Mistakes

| Mistake | Why it is wrong | Alternative |
|---|---|---|
| Storing prod passwords in `application.yml` | Risks committing to Git/images | Key Vault or platform secrets |
| Assuming activating `prod` profile equals security | Does not manage IAM/networking | Separate resources, identities, RBAC, private routes |
| Using `APP_CLIENT_CONNECT_TIMEOUT` assuming it always binds | Relaxed binding follows strict rules | Use canonical env names and test |
| Setting `spring.profiles.active` in `application-prod.yml` | Invalid/unpredictable profile activation | Set from the deployment environment |
| Sharing one secret across dev/prod | Huge blast radius | Isolate secrets and identities |
| Printing `/actuator/env` to debug | Can expose sensitive values | Redacted config metadata and scoped access |
| Assuming Key Vault secret rotation auto-refreshes pools | Caching/connection lifecycle | Tested refresh/restart/reconnect |
| Updating a ConfigMap expects live Pod env updates | Env vars are snapshotted at start | Rollout or supported refresh |
| Storing plaintext tokens in App Configuration | Wrong tool for secret management | Key Vault/managed identity |
| Fixing 403 by granting subscription Owner | Over-privileged and may miss data plane | Identify exact principal/scope/role |
| Assuming Private Endpoint removes need for TLS | Private network and TLS solve different problems | Keep HTTPS/TLS verification |
| Scaling replicas without checking connection pools | Can overload SQL/Redis | Total connection budget |
| Liveness checks SQL/Redis and restarts Pods | Causes cascading failures | Independent liveness, proper readiness/fallbacks |
| Treating feature flags as authorization | Wrong security boundary | Server-side authorization/RBAC |
| Testing canaries with production secrets in dev | Data leaks and blast radius | Environment-isolated identities/secrets |
| Rolling back only the image without config/data | Errors may persist | Plan rollback for config, schema, and identity |
| Passing profile tests proves prod networking works | Lacks real private DNS/roles | Integration/smoke tests in Azure |
| Logging all env vars to debug precedence | Secret leakage | Log key names/redacted values and config revisions |

## 59. Production Deployment Checklist

| Category | Acceptance criterion |
|---|---|
| **Artifact** | One image/JAR version deploys across multiple environments |
| **Profiles** | Active profile explicit, precedence tested, no environment mix-ups |
| **Config schema** | `@ConfigurationProperties` + validation on critical settings |
| **Secrets** | No hard-coding; Key Vault/secret references governed |
| **Identity** | Managed/Workload Identity with least-privilege permissions |
| **Endpoint** | Production never points to dev/localhost |
| **App Configuration** | Key/label namespace, authority, refresh SLA, owner defined |
| **Key Vault** | Secret rotation/reload/reconnect workflow tested |
| **Networking** | Private DNS/TLS/NSG/firewall/Private Endpoint verified |
| **Database** | JDBC auth, `pool size × max replicas` within capacity |
| **Redis/Messaging** | Endpoints, ports, auth mode, retries/idempotency aligned |
| **Platform** | App Service slots, Container Apps revisions, or AKS rollouts governed |
| **Kubernetes** | No secrets in ConfigMaps/Git; Pod restart semantics clear |
| **Health** | Startup/liveness/readiness probes avoid cascade failures |
| **Actuator** | Only required endpoints exposed and protected |
| **Logging** | Redaction, no PII/secrets, log volume within budget |
| **Reliability** | Timeouts/retries/circuit breakers fit request deadlines |
| **CI/CD** | Config validation, policy scans, IaC reviews, smoke tests |
| **Drift** | Desired state tracked and Portal/hotfix changes audited |
| **Rollout** | Canary/slot/revision, traffic controls, and rollback ready |
| **Monitoring** | Startup, 401/403/5xx, latency, refresh, and pool metrics tracked |
| **Cost** | App Configuration/Key Vault calls, platform, network, and logs measured |
| **Runbook** | Clear owners, incident steps, secret rotation, and rollback guides |

## 60. Self-Check Questions

1. How do configuration, secrets, and business data differ?
2. Why build one image to deploy across multiple Azure environments?
3. Does a Spring Boot profile automatically create RBAC and VNet isolation?
4. Under what conditions are `application.yml` and `application-prod.yml` loaded?
5. Should `spring.profiles.active` be placed inside a profile-specific file?
6. What problem does `spring.config.activate.on-profile` solve?
7. Why can multiple active profiles create hard-to-predict overrides?
8. Distinguish `spring.config.location`, `additional-location`, and `import`.
9. What is the canonical environment variable for `app.client.connect-timeout`?
10. How do `@Value` and `@ConfigurationProperties` differ in type safety and validation?
11. When a mandatory key is missing, why is failing fast safer than defaulting to localhost?
12. How does Spring receive App Service Application Settings?
13. Why are slot-sticky settings needed when swapping App Service slots?
14. Are Container Apps revisions and secret refreshes always synonymous?
15. How do ConfigMaps and Kubernetes Secrets differ?
16. Is Base64 inside a Kubernetes Secret encryption?
17. Does changing a Kubernetes ConfigMap automatically update env vars of a running Pod?
18. What configuration does AKS Workload Identity require outside Java code?
19. What kind of data belongs in Azure App Configuration?
20. Do App Configuration labels automatically activate Spring profiles?
21. Does dynamic refresh automatically update every Spring bean?
22. How does a feature flag differ from a profile and from authorization?
23. Does rotating a Key Vault secret version automatically update an active JDBC connection pool?
24. Does a managed identity automatically gain permission to read Key Vault?
25. Does `DefaultAzureCredential` always select the same principal on a laptop and in AKS?
26. How do App Configuration Data Reader and Key Vault data-plane permissions differ?
27. Does a Private Endpoint replace TLS?
28. Why must JDBC pool size be multiplied by maximum replicas?
29. How should liveness and readiness checks depend on the database differently?
30. Why should `/actuator/env` never be exposed to the Internet?
31. Do retry/timeout config settings affect an SDK client automatically before explicit binding?
32. When App Configuration is unreachable, when should an app fail fast?
33. What is configuration drift?
34. Where can Bicep or Terraform accidentally expose secrets?
35. When is dynamic refresh preferable to a rollout restart?
36. Why test effective configuration without logging secret values?
37. Can an HTTP 403 stem from identity, RBAC, or a firewall?
38. Does rolling back an image automatically roll back schema/data changes?
39. Which metrics should be monitored after canarying a configuration change?
40. What are three essential practices for safely managing production environments?

## References

- Spring Boot — *Externalized Configuration*: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — *Profiles*: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot — *Type-safe Configuration Properties*: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot — *Actuator Health/Probes*: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — *Configuration Properties Validation*: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Microsoft Learn — *Configure App Service settings*: https://learn.microsoft.com/azure/app-service/configure-common
- Microsoft Learn — *App Service deployment slots*: https://learn.microsoft.com/azure/app-service/deploy-staging-slots
- Microsoft Learn — *App Service Key Vault references*: https://learn.microsoft.com/azure/app-service/app-service-key-vault-references
- Microsoft Learn — *Azure Container Apps secrets*: https://learn.microsoft.com/azure/container-apps/manage-secrets
- Microsoft Learn — *Azure Container Apps revisions*: https://learn.microsoft.com/azure/container-apps/revisions
- Microsoft Learn — *AKS Workload Identity*: https://learn.microsoft.com/azure/aks/workload-identity-overview
- Kubernetes — *ConfigMaps*: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes — *Secrets*: https://kubernetes.io/docs/concepts/configuration/secret/
- Microsoft Learn — *Azure Key Vault overview*: https://learn.microsoft.com/azure/key-vault/general/overview
- Microsoft Learn — *Azure App Configuration overview*: https://learn.microsoft.com/azure/azure-app-configuration/overview
- Microsoft Learn — *Azure App Configuration key-values and labels*: https://learn.microsoft.com/azure/azure-app-configuration/concept-key-value
- Microsoft Learn — *Azure App Configuration feature management*: https://learn.microsoft.com/azure/azure-app-configuration/concept-feature-management
- Microsoft Learn — *Spring Cloud Azure documentation*: https://learn.microsoft.com/azure/developer/java/spring-framework/
- Microsoft Learn — *Azure SDK for Java authentication*: https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview
- Microsoft Learn — *Azure SQL authentication with Microsoft Entra*: https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-overview
- Microsoft Learn — *Azure Private Endpoint overview*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
- Microsoft Learn — *Azure Monitor/Application Insights for Java*: https://learn.microsoft.com/azure/azure-monitor/app/java-in-process-agent
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
