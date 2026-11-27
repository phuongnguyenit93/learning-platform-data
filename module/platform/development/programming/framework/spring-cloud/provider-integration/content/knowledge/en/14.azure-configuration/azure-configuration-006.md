# Key Vault References in App Configuration

When a Spring Boot application needs payment tokens, database passwords, or partner API keys, development teams often want to manage **application configuration names** in one place while keeping **secret values** in a store with separate permissions and lifecycles. **Azure App Configuration Key Vault reference** solves that need: App Configuration stores a **URI pointing to the secret**, while the actual value remains in **Azure Key Vault**.

With the **Spring Cloud Azure App Configuration** library, a Key Vault reference key is read like a configuration key. The **application-side** client receives the URI, queries Key Vault using an authorized identity, and places the dereferenced value into the Spring `Environment`. Afterward, `@Value`, `@ConfigurationProperties`, or Spring Boot auto-configuration can consume the property as usual.

This lesson is in the **Azure Configuration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, covering identities/permissions, storage, messaging, data, secrets, integration testing, and provider comparisons. This lesson focuses on **App Configuration Key Vault references**, permissions across **two services**, Spring loading rules, and safe secret rotation.

## 1. What Should You Know and Be Able to Do Afterward?

1. Distinguish **regular App Configuration key-values**, **Key Vault references**, and **direct Key Vault Secrets PropertySource**.
2. Create a secret in Key Vault and a reference containing its URI in App Configuration via the portal or Azure CLI.
3. Grant **App Configuration Data Reader** and **Key Vault Secrets User** to the exact application runtime identity.
4. Configure `spring.config.import=azureAppConfiguration`, select keys/labels, and bind properties received from references into Java.
5. Understand URIs with/without **versions**, the impact of refresh, caching, and bean lifecycles during secret rotation.
6. Diagnose permission/network/selector errors, test binding in isolation, and integration test with both services.

The running scenario is `checkout-service`. The application uses `payments.api-token` to connect to a payment provider and `payments.timeout` to configure the timeout. The secret token resides in Key Vault; the non-sensitive timeout resides in App Configuration. Both ultimately become Spring properties.

## 2. Architecture: References Hold Pointers, Not Secrets

Consider three independent objects:

| Object | Example | What Does It Contain? |
| --- | --- | --- |
| Secret in Key Vault | `payments-api-token` | The actual token value and its versions |
| Key Vault reference in App Configuration | `/application/payments.api-token` | URI `https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token` |
| Property in Spring | `payments.api-token` | The value dereferenced by the client, used at runtime |

**App Configuration does not go to Key Vault to fetch the secret and return that value to Spring**. The configuration provider running inside the application is responsible for receiving the reference and calling Key Vault. The two services do not directly exchange secret values in this flow.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Provider as Spring Cloud Azure App Configuration provider
    participant Config as Azure App Configuration
    participant Vault as Azure Key Vault
    participant Spring as Spring Environment / Bean
    App->>Provider: spring.config.import=azureAppConfiguration
    Provider->>Config: Read /application/payments.api-token
    Config-->>Provider: Key Vault reference containing secret URI
    Provider->>Vault: GET secret with application credential
    Vault-->>Provider: Secret value if authorized
    Provider->>Spring: Property payments.api-token = resolved value
    Note over Spring: Use value, do not log it
~~~

Therefore, you must distinguish **two authentication requirements**:

- The client needs permission to **read key-values** from App Configuration.
- The client needs permission to **read secret values** from Key Vault.

Being able to read App Configuration without Key Vault permissions only reveals the **pointer**, not the token. Conversely, having Key Vault permissions without App Configuration permissions still fails to load the referenced key via this flow.

### 2.1. Which data should use a reference?

| Data | Management Approach | Why |
| --- | --- | --- |
| `payments.timeout=PT3S` | Regular key-value in App Configuration | Non-sensitive operational parameter |
| `payments.api-token` | Key Vault reference in App Configuration | Logical name in App Configuration, secret in Key Vault |
| PostgreSQL password | Secret in Key Vault, optionally referenced from App Configuration | Do not store plaintext in configuration |
| `feature.NewCheckout` | App Configuration Feature Manager | A feature on/off decision, not a secret |
| Non-exportable signing key | Key Vault Keys and Cryptography API | Secret-style Key Vault references do not replace key signing operations |

App Configuration encrypts key-values at rest and in transit, but that encryption does not turn it into a secret lifecycle management system. Secrets should be protected in Key Vault.

## 3. Reference Structure and Key/Label Selection

From Azure App Configuration's perspective, a Key Vault reference is still **a key-value with a key, label, and content type**. The difference is that **the value has a reference structure**, containing no plaintext secret.

| Field | Example |
| --- | --- |
| Key | `/application/payments.api-token` |
| Label | *(No Label)* |
| Content type | `application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8` |
| Value as stored data | JSON with a `uri` property pointing to the Key Vault secret |
| Value after Spring provider processing | Resolved secret value, assigned to `payments.api-token` |

Representation of the reference structure (to understand the data—**do not manually create a regular key-value with this content**):

~~~json
{
  "uri": "https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token"
}
~~~

When created via **Configuration Explorer → Create → Key vault reference** or the `az appconfig kv set-keyvault` command, Azure sets the exact content type. If you manually create a regular key-value containing the plain URL string, Spring will treat it as a **configuration string**, and will not automatically dereference it into a secret.

### 3.1. App Configuration key names differ from Key Vault secret names

Secret names in Key Vault typically use letters, digits, and hyphens `-`, such as `payments-api-token`; dots `.` are not allowed in secret names. By contrast, App Configuration keys can use `.` to form Spring property names, such as `/application/payments.api-token`.

Thus, the mapping in the example is:

~~~text
Azure Key Vault:              payments-api-token
         ^
         | URI pointing to secret
         |
Azure App Configuration:      /application/payments.api-token
         |
         | Spring provider selects /application/*,
         | strips /application/ prefix, resolves Key Vault
         v
Spring Environment:           payments.api-token
         |
         v
@ConfigurationProperties:      PaymentProperties.apiToken()
~~~

Spring code **does not need to know the secret name `payments-api-token`**: it only needs to know the logical property `payments.api-token`.

### 3.2. Labels determine which reference is selected

One key can carry multiple references by label:

| Key | Label | Target Secret URI |
| --- | --- | --- |
| `/application/payments.api-token` | `dev` | Secret `payments-api-token` in the dev vault |
| `/application/payments.api-token` | `staging` | Same-named secret in the staging vault |
| `/application/payments.api-token` | `prod` | Same-named secret in the prod vault |

When no custom label filter is declared, the Spring Cloud Azure App Configuration provider uses **active Spring profiles** to select labels; when there is no active profile, it selects **(No Label)** records. You can configure `label-filter` explicitly to change this behavior.

**Labels are not a security boundary.** The same identity permitted to read the App Configuration store can inspect reference metadata on other labels; secrets remain gated by Key Vault at retrieval time. If dev and prod must separate permissions or networking, consider dedicated App Configuration stores and Key Vaults per environment.

## 4. Preparing the Two Azure Resources

Example resources, to be replaced with actual names:

| Resource | Example Name | Endpoint |
| --- | --- | --- |
| App Configuration store | `demo-checkout-config` | `https://demo-checkout-config.azconfig.io` |
| Key Vault | `demo-checkout-kv` | `https://demo-checkout-kv.vault.azure.net/` |

You need an Azure subscription, Java 17 or higher, Maven, Spring Boot, and network connectivity allowing the runtime to reach **both endpoints**. If either service restricts access to a private endpoint, the workload must have proper DNS/VNet routing.

### 4.1. Creating the secret in Key Vault

In the Azure portal:

1. Open **Key Vault → Secrets → Generate/Import**.
2. Create a secret named `payments-api-token` with a **dummy value for dev/sandbox use only**.
3. Note the **Secret Identifier**, for example `https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token`.
4. Verify the secret is enabled and the reading identity has the permission granted in section 5.

Never place production secrets in CLI commands or illustrative docs because they may be recorded in shell history, pipeline logs, audits, or issues.

### 4.2. Creating a Key Vault reference via the portal

In the Azure portal, open **App Configuration → Configuration Explorer → Create → Key vault reference**:

- **Key:** `/application/payments.api-token`.
- **Label:** leave blank *(No Label)* for the first run.
- **Secret:** select Key Vault `demo-checkout-kv` and secret `payments-api-token`, or enter the secret identifier if supported by the UI.
- **Save:** save the reference.

Also create a regular key-value in **Configuration Explorer**:

| Key | Label | Value |
| --- | --- | --- |
| `/application/payments.timeout` | *(No Label)* | `PT3S` |

After this step, the store contains one regular key and one reference key. No plaintext token has been placed in App Configuration.

### 4.3. Creating a reference with Azure CLI

Syntax supported by the Azure CLI:

~~~bash
az appconfig kv set-keyvault \
  --name demo-checkout-config \
  --key /application/payments.api-token \
  --secret-identifier "https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token" \
  --auth-mode login
~~~

When `--label` is omitted, the reference is created with **(No Label)**. To create a `prod` label reference, add `--label prod` and use the URI belonging to the corresponding production vault.

The command above **writes only the URI**, not the secret value. The identity running the CLI must have **App Configuration data write permissions** (for example `App Configuration Data Owner`), whereas the application only needs read permissions.

To inspect reference **metadata** without resolving/printing the secret value:

~~~bash
az appconfig kv show \
  --name demo-checkout-config \
  --key /application/payments.api-token \
  --auth-mode login
~~~

The output can show the URI and content type; **do not** pass `--resolve-keyvault` or print secret contents to the terminal during verification steps.

## 5. Authorization: Permissions on the Two Services Are Independent

Assume Spring Boot runs on Azure App Service with a **system-assigned Managed Identity** or a workload configured with a user-assigned identity. Under **Azure RBAC**:

| Who Needs Permission | Resource | Appropriate Role | Purpose |
| --- | --- | --- | --- |
| **Spring Boot runtime identity** | App Configuration store | `App Configuration Data Reader` | Read regular keys and Key Vault references |
| **Same runtime identity** | Key Vault | `Key Vault Secrets User` | Retrieve referenced secret values |
| Person/pipeline managing references | App Configuration store | `App Configuration Data Owner` or equivalent write role | Create/update references |
| Person/pipeline managing secrets | Key Vault | Dedicated secret-write role per team policy | Create versions/rotate; never grant to read-only runtime |

If the vault still uses **Vault access policy** instead of Azure RBAC, the required permission to retrieve a secret is `Get`; listing scenarios also require checking `List`. Do not assign `Owner` or `Contributor` just to fix secret-read errors, because resource management roles are not equivalent to **data-plane roles**.

Example logic of role assignments across both resources:

~~~text
Spring workload identity (principal-id = <runtime-principal>)
    |
    +-- App Configuration store: App Configuration Data Reader
    |
    +-- Key Vault:              Key Vault Secrets User
~~~

**Do not grant roles to the App Configuration store's identity assuming the store reads secrets on the app's behalf.** In the Spring provider flow, **the application's identity** is the principal that must read Key Vault.

### 5.1. Selecting credentials across environments

- **Local:** can use `az login` and the Azure SDK credential chain if the local principal has permissions on both resources.
- **Cloud:** prefer **Managed Identity** for the workload; assign roles to the deployed principal.
- **CI/integration tests:** use a dedicated test identity with restricted scope and data.
- **User-assigned identity:** configure the client ID explicitly per Spring Cloud Azure guidance and verify which credential the provider actually picks.

Spring Cloud Azure App Configuration provider can use `DefaultAzureCredential` by default. Without customization, the provider typically uses the same authentication mechanism for both App Configuration and Key Vault. When the two services need different credentials, modern library lines support customizing client builders via `ConfigurationClientCustomizer` and `SecretClientCustomizer`; check the API and credential application order of **the exact version in use**.

**Connecting to App Configuration via connection string does not grant Key Vault read permissions.** An HMAC connection string only authenticates to App Configuration; Key Vault still requires an identity/token and appropriate secret permissions.

## 6. Adding Spring Cloud Azure Libraries

Example of a **Spring Boot 3.5.x**, Java 17, Maven project using the **Spring Cloud Azure 6.x** BOM. `6.5.0` is used as an illustrative version; verify against your project's compatibility matrix and actual artifacts. For Spring Boot 4.x, choose the corresponding Spring Cloud Azure 7.x line.

In `pom.xml` with Spring Boot parent/dependency management already configured:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-azure.version>6.5.0</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-appconfiguration-config-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-cloud-azure-appconfiguration-config-web` loads App Configuration and supports refresh checks driven by Spring Web activity. If you do not use servlet/web or do not need request-driven auto-checks for refresh, `spring-cloud-azure-appconfiguration-config` is sufficient.

**It is not required to add `spring-cloud-azure-starter-keyvault-secrets` solely to resolve Key Vault references.** The App Configuration provider has its own Key Vault reference mechanism. The Key Vault Secrets starter is needed when you want the application to **also** load secrets directly as a Key Vault PropertySource by secret name.

## 7. Declaring Spring Config Data Import

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Set the App Configuration **endpoint** in an environment variable:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-checkout-config.azconfig.io
~~~

PowerShell on Windows:

~~~powershell
$Env:AZURE_APPCONFIG_ENDPOINT = "https://demo-checkout-config.azconfig.io"
~~~

Linux/macOS shell:

~~~bash
export AZURE_APPCONFIG_ENDPOINT="https://demo-checkout-config.azconfig.io"
~~~

Meaning:

- `spring.config.import=azureAppConfiguration` registers the App Configuration provider into the **Spring Config Data API** during configuration bootstrapping.
- `stores[0].endpoint` specifies where to load key-values and references; this endpoint is **not** the Key Vault endpoint.
- By default, the provider fetches keys with prefix `/application/` and label **(No Label)** when there is no active profile.
- For key `/application/payments.api-token`, the provider strips the prefix by default rules and provides Spring property `payments.api-token`.
- When the provider encounters a **Key Vault reference**, it calls Key Vault to resolve the URI using the appropriate credential.

The Key Vault URI **lives inside the reference in App Configuration**, so the example does not need `AZURE_KEYVAULT_ENDPOINT` just to resolve references. Using Key Vault PropertySource directly is a separate configuration.

### 7.1. When a profile is active

On the first test run, run **without activating a Spring profile**, because the two records in section 4 use (No Label). If running profile `dev`, the default provider may select only label `dev` and not automatically fetch No Label.

To use a shared configuration layer (No Label) and then override with an environment label, provided exactly one active profile is always set:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: ',${spring.profiles.active}'
~~~

The **later** label takes precedence on duplicate keys. If `prod` has a reference for the same `/application/payments.api-token`, the production URI overrides the No Label URI in the Azure data layer. Do not use this variant when the profile might be absent without designing a default value for the placeholder.

## 8. Reading References with `@ConfigurationProperties` and `@Value`

The goal is for Java code to receive **logical properties**, without calling Azure APIs and without logging secrets.

### 8.1. Binding into a record with a protected `toString`

Create `src/main/java/com/example/checkout/CheckoutApplication.java`:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Create `src/main/java/com/example/checkout/PaymentProperties.java`:

~~~java
package com.example.checkout;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String apiToken, Duration timeout) {
    public PaymentProperties {
        if (apiToken == null || apiToken.isBlank()) {
            throw new IllegalArgumentException(
                    "Required property payments.api-token is missing");
        }
    }

    @Override
    public String toString() {
        // Default record prints all fields, including secrets.
        return "PaymentProperties[apiToken=REDACTED, timeout=" + timeout + "]";
    }
}
~~~

Mapping result:

| Azure Key | Data Source | Spring Property | Java Field |
| --- | --- | --- | --- |
| `/application/payments.api-token` | Resolved Key Vault reference | `payments.api-token` | `apiToken` |
| `/application/payments.timeout` | Regular key-value `PT3S` | `payments.timeout` | `timeout` |

Spring Binder converts `payments.api-token` to `apiToken` via relaxed binding and `PT3S` to `Duration.ofSeconds(3)`.

### 8.2. Service using the configuration

~~~java
package com.example.checkout;

import org.springframework.stereotype.Service;

@Service
public class PaymentClientSettings {
    private final PaymentProperties properties;

    public PaymentClientSettings(PaymentProperties properties) {
        this.properties = properties;
    }

    public boolean hasCredential() {
        // Expose status only, do not return token.
        return !properties.apiToken().isBlank();
    }

    public long timeoutMillis() {
        return properties.timeout().toMillis();
    }
}
~~~

In a real application, the token is passed to the corresponding HTTP client/gateway via secure authentication APIs. Do not create an endpoint returning `properties.apiToken()`, and do not log `PaymentProperties` even with a redacted `toString()`; other copies of the object could still leak data.

### 8.3. Reading a single property with `@Value`

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayCredentialHolder {
    private final String apiToken;

    public GatewayCredentialHolder(
            @Value("${payments.api-token}") String apiToken) {
        this.apiToken = apiToken;
    }

    public boolean configured() {
        return apiToken != null && !apiToken.isBlank();
    }
}
~~~

`@Value` works well for a single property, while `@ConfigurationProperties` is more convenient when multiple related parameters exist. Both read values from the **Spring Environment** after the reference has resolved; no URI decryption or resolution code is needed in the business layer.

## 9. Differences Between References and Key Vault Secrets PropertySource

These are two **independent** ways to load secrets, and both can coexist in a single Spring Boot application:

| Criterion | App Configuration Key Vault Reference | Key Vault Secrets PropertySource |
| --- | --- | --- |
| Source defining Spring property name | **App Configuration key** like `/application/payments.api-token` | **Secret name in vault** and mapping/alias |
| Where endpoint is configured | `spring.cloud.azure.appconfiguration.stores[]` | `spring.cloud.azure.keyvault.secret.property-sources[]` |
| Required permissions | Read App Configuration **and** Key Vault | Read Key Vault |
| Refresh mechanism | Per App Configuration provider, monitor/reference, and beans | Per KeyVaultPropertySource refresh interval and beans |
| Easy to switch vaults per environment via labels | Yes, via references with same key and different labels | Must change endpoint/configuration per environment |
| Best suited when | Want to manage secret pointers alongside application config keys | Application only needs to read secrets from a vault directly |

If you choose **references**, you do not need to also list `payments-api-token` in Key Vault PropertySource for App Configuration to resolve it. Conversely, if you use PropertySource directly, you can use a placeholder in Spring to alias the secret name without an App Configuration reference.

**Do not confuse** App Configuration Key Vault references with the `@Microsoft.KeyVault(...)` syntax in **Azure App Service application settings**. App Service has its own resolution and caching mechanism, not equivalent to the lifecycle/refresh of the Spring Cloud Azure provider.

## 10. Secret Versioning: Versionless vs. Version-Pinned URIs

A Key Vault secret can have multiple **versions**. A reference allows specifying either a **versionless** URI or a URI pinned to a specific version.

~~~text
Versionless:
https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token

Version-pinned:
https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token/<version-id>
~~~

| URI Type | Characteristic | When Appropriate |
| --- | --- | --- |
| **Versionless** | When re-retrieved, can receive the secret's current version per Key Vault | Want rotation without updating the reference every time |
| **Versioned** | Points fixedly to one specific version; new secrets do not move the URI | Releases that must pin a secret version and control cutover |
| **Different references between dev/prod** | Same Spring key name pointing to different vaults by label/store | Separating environments and permissions |

**Key point:** creating a new secret version in Key Vault **does not guarantee running Spring beans automatically pick up the new value**. Even with a versionless reference, the application may still hold the old value in provider cache, Spring properties, or a previously constructed HTTP client.

### 10.1. Rotation with versionless references

A proactive procedure:

1. Issue the new credential at the payment provider; if possible, keep both old and new credentials active during the transition period.
2. Create a new version of `payments-api-token` in Key Vault via a protected workflow.
3. Trigger secret reload or a **controlled restart** so the client resolves the versionless URI again; verify each instance uses the new credential.
4. Check sandbox transactions, authentication errors, and service availability.
5. Revoke the old credential once certain no instance still depends on it.

If you want to point the reference to **a specific version**, update the URI in App Configuration, then reload configuration/restart, verify the outcome, and only then revoke the old version.

### 10.2. Why is App Configuration monitoring alone not enough?

App Configuration monitoring primarily detects **changes to the key-values it watches inside App Configuration**. If **only the secret value in Key Vault changes** while the URI/reference in App Configuration **does not change**, you should not assume monitoring will always detect and update every application.

You can build a rotation workflow using a reference/sentinel change in App Configuration combined with refresh, or a coordinated application restart. Even then, once the provider loads the new value, beans/HTTP clients storing the token in a field still need recreation or credential replacement according to the application lifecycle.

Note: some **.NET App Configuration provider** guides show specialized APIs like `SetSecretRefreshInterval`. Do not assume the Spring provider has the exact same API or cache guarantees as App Service/.NET; verify the refresh capabilities of **the Java library you are using**.

## 11. Refresh in Spring Cloud Azure

When an application needs runtime configuration updates, you can enable App Configuration provider monitoring. Example with the `-web` variant:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key=/application/config.refresh-sentinel
~~~

Create `/application/config.refresh-sentinel` in the store with the appropriate label and initial value `1`. To publish a configuration change, update the target keys and references first, and finally change the sentinel.

- According to Spring Cloud Azure documentation, the default minimum check interval is typically **30 seconds**.
- With `spring-cloud-azure-appconfiguration-config-web`, checks can be triggered by **servlet request** activity once the interval has elapsed.
- With the non-web provider, you can actively call the library's appropriate refresh API.
- Refresh follows Spring/`@RefreshScope` and binding mechanics; objects caching tokens or sessions themselves still must be handled separately.

**Do not treat 30 seconds as a secret-update SLA.** That interval only governs configuration check scheduling. Actual latency depends on triggers, networking, Key Vault reference caching, instance count, and bean lifecycles.

## 12. Testing and Error Diagnosis

### 12.1. Testing binding without calling Azure

A unit test for `PaymentProperties` binding logic needs no real vault. You can use `MockEnvironment` and `Binder`:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

class PaymentPropertiesBindingTest {
    @Test
    void bindsPropertiesWithoutAzure() {
        var env = new MockEnvironment()
                .withProperty("payments.api-token", "dummy-for-test")
                .withProperty("payments.timeout", "PT3S");

        PaymentProperties props = Binder.get(env)
                .bind("payments", Bindable.of(PaymentProperties.class))
                .orElseThrow();

        assertThat(props.apiToken()).isEqualTo("dummy-for-test");
        assertThat(props.timeout()).isEqualTo(Duration.ofSeconds(3));
        assertThat(props.toString()).doesNotContain("dummy-for-test");
    }
}
~~~

This test verifies **Spring Binder**, **data types**, and the redacted `toString()`. It does not prove the provider dereferences the URI, Azure roles are right, or refresh works.

If using `@SpringBootTest` for a full Spring context, you can disable the provider with `spring.cloud.azure.appconfiguration.enabled=false` and supply dummy properties; verify that disabling takes effect before the import stage in your project version.

### 12.2. Integration testing with dev resources

Use a dedicated App Configuration store, Key Vault, and identity for dev/sandbox:

1. Create dummy secret `payments-api-token` and reference `/application/payments.api-token` with **No Label**.
2. Grant App Configuration Data Reader and Key Vault Secrets User to the test identity.
3. Start Spring Boot, verify `payments.api-token` exists and a sandbox client can authenticate (without printing the value).
4. Switch to the `dev` label and configure the selector; verify the application fetches the right URI/reference.
5. With a test identity lacking Key Vault permission, verify the reference can be read while the secret resolution step fails as expected.
6. Create a new version and test a versionless URI vs. a version-pinned URI; observe after restart/refresh.
7. Try pointing the reference to another vault without permissions granted, confirming the error is caught early.
8. Verify logs and traces contain no secrets or tokens.

**Never use a production vault to test permission loss or rotation.** Such tests can alter credential state and disrupt live services.

### 12.3. Troubleshooting table

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| Spring does not recognize `azureAppConfiguration` | Missing App Configuration dependency, wrong import syntax, or incompatible BOM | Check `pom.xml` and `spring.config.import` |
| `payments.api-token` does not exist | Key/reference does not match `/application/*`, wrong label/profile, or wrong store | Check key name, `key-filter`, `label-filter`, and endpoint |
| Spring receives only the URI instead of the secret | Key created as a regular key-value, missing Key Vault reference content type | Recreate using **Key vault reference** or `set-keyvault` |
| App Configuration returns 403 | Identity lacks `App Configuration Data Reader` or role has not propagated | Verify exact principal and App Configuration scope |
| Reference reads fine but Key Vault returns 403 | Identity lacks `Key Vault Secrets User` or `Get` access policy | Grant permission on the exact vault, check runtime principal |
| Secret returns 404 | Wrong name, URI/version, secret missing or disabled | Inspect URI metadata and secret status |
| Works locally, fails on Azure App Service | Azure workload uses a different identity than local developer | Verify Managed Identity, roles, and networking in cloud |
| After rotation still receives old value | Version-pinned URI, provider cache, no refresh, or bean/client holds old token | Check version, perform reload/restart, and recreate client |
| DNS/timeout/429 | Private endpoint, firewall, DNS, quota, or unsuitable retries | Check connectivity to **both endpoints**, use backoff and monitoring |
| Startup tests accidentally hit Azure | Provider not disabled or missing stubs | Use local binding tests, disable provider in Spring tests not needing Azure |

### 12.4. Observing configuration without leaking secrets

Instead of printing `environment.getProperty("payments.api-token")`, you can check **whether the key exists** and **the PropertySource name** in a dev environment:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class ConfigSourceDiagnostic {
    @Bean
    ApplicationRunner reportSources(ConfigurableEnvironment env) {
        return args -> {
            String key = "payments.api-token";
            System.out.println("Property configured: " + env.containsProperty(key));
            for (PropertySource<?> source : env.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("Source: " + source.getName());
                }
            }
        };
    }
}
~~~

Use only temporarily in test environments. Never expose `/actuator/env` or `/actuator/configprops` to debug secrets. Those endpoints can reveal property names, sources, or values depending on configuration and version.

## 13. Secure Design Pattern for Production Environments

A practical setup:

| Component | dev | prod |
| --- | --- | --- |
| App Configuration store | `checkout-config-dev` | `checkout-config-prod` |
| Key Vault | `checkout-kv-dev` | `checkout-kv-prod` |
| Spring property | `payments.api-token` | `payments.api-token` |
| Reference | URI to dev vault | URI to prod vault |
| Identity | Dev Managed Identity | Prod Managed Identity |
| Role on each store | Data Reader in dev | Data Reader in prod |
| Role on each vault | Secrets User in dev | Secrets User in prod |

Benefit: **Java code stays unchanged**; only the App Configuration endpoint and runtime identity differ. Prod does not have to trust a label inside a shared store to prevent a dev workload from accidentally reading a production URI.

Several principles to apply:

- Grant **read-only permissions** to the application; creating/updating secrets and references belongs to controlled pipelines/operators.
- Use Managed Identity or workload identity federation instead of long-lived client secrets whenever possible.
- Restrict roles and networking on **both** App Configuration and Key Vault; verify private endpoints individually.
- Never log values from `Environment`, Beans, exceptions, trace tags, or telemetry.
- When rotation must be supported, choose versioned vs. versionless URIs based on requirements and redesign client lifecycles accordingly.
- Monitor auth/403 errors, 404 secret errors, timeouts, secret expirations, and refresh latency; never put secrets into metric labels.
- If a key pointing to a secret loses permissions, design the application to **fail safely** rather than falling back to a hard-coded token.

## 14. Practice Exercise

The `shipping-service` application needs:

- `shipping.timeout=PT4S` (non-sensitive).
- Secret `shipping-partner-token` in `shipping-kv-dev`.
- Spring property `shipping.partner-token` sourced from a Key Vault reference.
- An identity with only **read** access to App Configuration and **read** access to Key Vault secrets.
- A plan to rotate the token without changing Java code.

### 14.1. Configuration design

In App Configuration store `shipping-config-dev`:

| Key | Label | Type | Value |
| --- | --- | --- | --- |
| `/application/shipping.timeout` | *(No Label)* | Regular key-value | `PT4S` |
| `/application/shipping.partner-token` | *(No Label)* | Key Vault reference | URI to `shipping-kv-dev/secrets/shipping-partner-token` |

Spring config:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Java binding:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(Duration timeout, String partnerToken) {
    @Override
    public String toString() {
        return "ShippingProperties[timeout=" + timeout + ", partnerToken=REDACTED]";
    }
}
~~~

Enable `@ConfigurationPropertiesScan` and inject `ShippingProperties` into the client that uses the token. Avoid printing the token or any object holding the token.

### 14.2. Self-check questions

1. When a reference points a URI to Key Vault, does App Configuration need to be granted `Key Vault Secrets User` to return the secret to Spring?
2. Why might an identity that has `App Configuration Data Reader` still hit a 403 error when loading a reference?
3. Is an App Configuration key containing a **plain URI string** automatically processed as a Key Vault reference?
4. When publishing a new secret version while keeping a versionless URI, will all running Spring HTTP clients swap tokens immediately?
5. In a multi-environment model, why is separating vaults and identities usually clearer than relying solely on labels?
6. When should you use `spring-cloud-azure-starter-keyvault-secrets` instead of an App Configuration Key Vault reference?

**Guided answers:** (1) no, the application itself reads Key Vault; (2) missing Key Vault permission or URI/network issue; (3) no, it must have the proper reference content type; (4) no, re-resolution and client updates are needed; (5) labels are configuration filters, not authorization boundaries; (6) when you only need to read secrets directly by name/PropertySource and do not need pointers in App Configuration.

## 15. Official Reference Sources

- [Microsoft Learn – Use Key Vault references in a Java Spring app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-key-vault-references-spring-boot): creating secrets/references, granting permissions, and reading via Spring.
- [Microsoft Learn – Spring Boot App Configuration quickstart](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-java-spring-app): Config Data import and dependencies.
- [Microsoft Learn – Azure App Configuration CLI: `set-keyvault`](https://learn.microsoft.com/en-us/cli/azure/appconfig/kv): creating references with the right content type and using versioned/versionless URIs.
- [Microsoft Learn – App Configuration key-value store](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-key-value): keys, labels, and content types.
- [Azure SDK for Java – Spring Cloud Azure App Configuration README](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/spring/spring-cloud-azure-starter-appconfiguration-config/README.md): selectors, credentials, customizers, and monitoring.
- [Microsoft Learn – Spring Cloud Azure configuration reference](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): defining and prioritizing credentials.
- [Microsoft Learn – Dynamic configuration in Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): trigger/request-based refresh.
- [Microsoft Learn – Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): secret authorization.
- [Azure SDK for Java – Spring Versions Mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): choosing a compatible Spring Cloud Azure line.

**Remember:** App Configuration holds **configuration names and reference URIs**, Key Vault holds **secret values**, and the **Spring Cloud Azure provider running inside the application** connects both and places the values into `Environment`. Secure deployment requires controlling the exact identity, both data-reader roles, key/label selection, URI versioning, refresh, and the lifecycle of clients consuming the secret.
