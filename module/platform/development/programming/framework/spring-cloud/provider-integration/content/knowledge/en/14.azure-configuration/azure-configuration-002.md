# Loading App Configuration into the Spring Configuration Environment

**Azure App Configuration** enables centralized management of operational parameters that a Spring Boot application needs at startup: timeouts, processing limits, display messages, non-sensitive endpoints, and environment-specific settings. Through the **Spring Cloud Azure App Configuration** library, selected values from the store are brought into the Spring `Environment` and consumed using familiar mechanisms: `@Value`, `Environment#getProperty`, and `@ConfigurationProperties`.

This is a hands-on lesson in the **Azure Configuration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, focusing on integrating Spring Boot with Azure's managed service, granting identities/permissions, and verifying integration behavior. The primary goal is to **load App Configuration into Spring's configuration system**, understand exactly which keys are loaded, why values get overridden, and how to diagnose when an application reads the wrong configuration.

## 1. Expected Outcomes

After this lesson, you will be able to:

1. Create key-values in App Configuration following the convention that Spring Cloud Azure can read.
2. Declare the library, `spring.config.import`, endpoint, and access permissions.
3. Receive configuration from the store as Spring properties and bind them to strongly typed Java objects.
4. Select keys/labels by Spring profile and recognize precedence order across sources.
5. Isolate business logic tests from real Azure services, handle startup failures, and understand the boundaries of the refresh mechanism.

Basic startup flow:

~~~mermaid
flowchart TD
    A["Spring Boot reads application.yml"] --> B["Config Data processes spring.config.import"]
    B --> C["Spring Cloud Azure accesses App Configuration"]
    C --> D["Selects key-values by key filter and label"]
    D --> E["Adds PropertySource to Spring Environment"]
    E --> F["Binds @ConfigurationProperties / @Value / Environment"]
    F --> G["Initializes beans using configuration"]
~~~

**Key takeaway:** App Configuration is an **external configuration source**. The library loads it into Spring's `PropertySource` mechanism; business code then does not need to call the Azure SDK to fetch individual timeouts or retry thresholds.

## 2. Spring Environment and the Import Mechanism

In Spring, `Environment` aggregates multiple `PropertySource`s, which may come from:

- `application.yml` and `application-{profile}.yml`;
- environment variables, system properties, command-line arguments;
- imported external configuration data, here **Azure App Configuration**.

When calling `environment.getProperty("catalog.timeout")`, Spring looks up the property according to the **precedence order** of the active sources. `@Value` and `@ConfigurationProperties` read from this same mechanism.

`spring.config.import=azureAppConfiguration` instructs Spring Boot to use the **Config Data API** to bring App Configuration in **during the configuration processing phase**, before Spring creates application beans. This is why you can bind Azure data via `@ConfigurationProperties` without having to load data manually in `@PostConstruct`.

### Distinguishing three types of configuration

| Where Declared | Role |
| --- | --- |
| `application.yml` | Declares how to connect to Azure, profiles, local defaults, and bootstrap settings |
| Azure App Configuration | Stores key-values for business logic and per-environment variants; the provider loads values into `Environment` |
| Azure Key Vault | Stores secrets/keys/certificates; when App Configuration contains a Key Vault reference, a dereferencing mechanism and corresponding Key Vault read permissions are required |

Do not use App Configuration as a place to put plaintext passwords, API keys, or sensitive connection strings. These values belong in Key Vault; App Configuration can store only a reference when needed.

## 3. Preparing the Practice Environment

In this lesson, assume the application is named `catalog-api` and the App Configuration store is named `demo-catalog-config`; replace the example names with your own resources.

Minimum requirements:

- An Azure subscription, an active Azure App Configuration store, and permission to read data from the store.
- JDK 17 or higher, Maven, and a Spring Boot project with Spring Web.
- An **identity** assigned the **App Configuration Data Reader** role on the store if authenticating with Microsoft Entra ID.
- Network connectivity allowing the application to reach the endpoint `https://demo-catalog-config.azconfig.io`.

The examples throughout use **Spring Boot 3.5.x** and BOM **Spring Cloud Azure 6.5.0**. According to the compatibility matrix, Spring Boot 4.0.x uses Spring Cloud Azure 7.x; do not arbitrarily mix these two lines. If your project has a fixed Spring Boot/Spring Cloud version, choose the appropriate Azure version according to the version table at the end of the lesson.

### 3.1. Creating key-values in Azure App Configuration

In the Azure portal, open the store → **Configuration Explorer** → create three key-values with **Label left empty** (the UI may display “(No Label)”):

| Key in App Configuration | Value | Label |
| --- | --- | --- |
| `/application/catalog.banner` | `Hello from Azure` | *(No Label)* |
| `/application/catalog.timeout` | `PT4S` | *(No Label)* |
| `/application/catalog.max-items` | `25` | *(No Label)* |

Keep the default Content Type for ordinary key-values. Do not create `dev`/`prod` labels at this step so you can verify the basic loading flow first.

**Why is `/application/` required?** The App Configuration provider's default selector reads keys matching the `/application/*` pattern, then maps the trailing part into Spring property names. For example:

~~~text
Azure App Configuration                  Spring Environment
/application/catalog.banner     ----->    catalog.banner
/application/catalog.timeout    ----->    catalog.timeout
/application/catalog.max-items  ----->    catalog.max-items
~~~

If you create a key named `catalog.banner` without the prefix, the default selector will not match it; the value may still exist in the portal but will not appear in the application. You can change `key-filter` if you want a different convention, but you must verify how the corresponding selector maps names.

### 3.2. Granting permissions to the identity

For authentication with Microsoft Entra ID, assign the **App Configuration Data Reader** role at the store scope to the exact principal that will run the application. Resource management permissions in the Azure portal and App Configuration data-read permissions are two separate concepts; a general management role does not necessarily grant data-plane permission.

| Environment | Identity to Check |
| --- | --- |
| Azure App Service / VM with Managed Identity enabled | Principal of the system-assigned or user-assigned managed identity |
| Container/workload using workload identity | Principal/federated identity of the actual workload |
| Personal machine | The identity the provider/credential chain is configured to use, which may differ from the account currently selected in the portal |

The preferred choice when running on Azure is **Managed Identity**, avoiding keeping access keys in source code. When you have just assigned a role, allow time for permission propagation before the next access attempt.

## 4. Adding Dependencies to Spring Boot

For a Spring Boot 3.5.x Maven project that already has a parent or Spring Boot dependency management mechanism, add to `pom.xml`:

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

The BOM ensures Spring Cloud Azure dependencies use the same compatible set of versions, so you do not need to declare a separate `<version>` for `spring-cloud-azure-appconfiguration-config-web`.

There are two commonly used providers:

| Artifact | When to Use |
| --- | --- |
| `spring-cloud-azure-appconfiguration-config` | Spring Boot applications that do not need automatic refresh integration tied to Spring Web |
| `spring-cloud-azure-appconfiguration-config-web` | Spring Web applications; in addition to loading configuration, supports checking for refresh on request activity |

The example uses the `-web` variant. This is not Spring Cloud Config Server; you do not need to stand up a separate config server to load App Configuration.

## 5. Declaring Import and Endpoint

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: catalog-api
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

At runtime, supply the environment variable:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-catalog-config.azconfig.io
~~~

With PowerShell when running on Windows, you can set it **in the current terminal session**:

~~~powershell
$Env:AZURE_APPCONFIG_ENDPOINT = "https://demo-catalog-config.azconfig.io"
~~~

With a Linux/macOS shell:

~~~bash
export AZURE_APPCONFIG_ENDPOINT="https://demo-catalog-config.azconfig.io"
~~~

Properties to remember:

- `spring.config.import=azureAppConfiguration`: enables the import process from the provider during the Spring Config Data processing phase.
- `spring.cloud.azure.appconfiguration.stores[0].endpoint`: URI of the store, **not** a connection string or a Key Vault endpoint.
- `stores` is a list; `[0]` means the first store.
- When `selects` is not declared, the provider uses the default key and label selector. For this example, run **without activating any Spring profile** to read keys with an empty Label.

If the application does not actually import (for example, mistyping `azureAppConfiguration`), merely setting the endpoint will not automatically turn data from Azure into a `PropertySource`.

### 5.1. Endpoint and connection string are two connection methods

**Recommended approach for Azure environments:** use `endpoint` with Managed Identity granted a data-reader role.

**Separate option for local development** if Microsoft Entra ID authentication is not yet configured: use a connection string managed as a secret via an environment variable:

~~~properties
spring.config.import=azureAppConfiguration
spring.cloud.azure.appconfiguration.stores[0].connection-string=${AZURE_APPCONFIG_CONNECTION_STRING}
~~~

The `application.properties` snippet above is an **alternative** to the `endpoint` connection snippet; do not set both properties for the same store. Never put a real connection string into committed files, documentation, issues, or logs.

The `az login` command only creates an Azure CLI login session; the application must still use an appropriate credential provider. If you want to access using a local account and token instead of a connection string, configure the credential chain/credential provider according to your Spring Cloud Azure version and grant store read permission to **the exact selected identity**.

## 6. Binding Configuration into a Java Object

Prefer `@ConfigurationProperties` for a structured group of settings, because Spring handles type conversion and binding structure validation automatically.

Create `src/main/java/com/example/catalog/CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Create `src/main/java/com/example/catalog/CatalogSettings.java`:

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogSettings(
        String banner,
        Duration timeout,
        int maxItems) {
}
~~~

Spring maps:

| Loaded Property | Java Component | Type |
| --- | --- | --- |
| `catalog.banner` | `CatalogSettings.banner()` | `String` |
| `catalog.timeout=PT4S` | `CatalogSettings.timeout()` | `Duration` |
| `catalog.max-items=25` | `CatalogSettings.maxItems()` | `int` |

`PT4S` is ISO-8601 duration syntax meaning **4 seconds**. Spring Binder supports converting this value to `java.time.Duration`. The `max-items` naming is also mapped to `maxItems` by Spring relaxed binding.

Create `src/main/java/com/example/catalog/CatalogController.java`:

~~~java
package com.example.catalog;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {
    private final CatalogSettings settings;

    public CatalogController(CatalogSettings settings) {
        this.settings = settings;
    }

    @GetMapping("/catalog/config")
    public Map<String, Object> showPublicConfig() {
        return Map.of(
                "banner", settings.banner(),
                "timeout", settings.timeout().toString(),
                "maxItems", settings.maxItems());
    }
}
~~~

The demo endpoint only displays three **non-sensitive** parameters; a real application should not expose a generic endpoint that leaks the entire `Environment`.

Besides `@ConfigurationProperties`, you can read individual values:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;

// Example inside a Spring-managed bean
@Value("${catalog.banner}")
private String banner;

// Or inject Environment and read:
String timeout = environment.getProperty("catalog.timeout");
~~~

`@Value` is concise for a single property but easily scatters key strings across many classes. `@ConfigurationProperties` is more convenient for groups of parameters used together; it can also be combined with validation by adding the appropriate Bean Validation dependency.

## 7. Running and Verifying Loaded Data

Once the endpoint is declared, the identity has read permission on the store, and the three keys exist with the right labels, run:

~~~bash
mvn spring-boot:run
~~~

Call the test API:

~~~bash
curl http://localhost:8080/catalog/config
~~~

Expected result (JSON field order may vary):

~~~json
{
  "banner": "Hello from Azure",
  "timeout": "PT4S",
  "maxItems": 25
}
~~~

To prove the data comes from **Azure** rather than a hard-coded value, change `/application/catalog.banner` in Configuration Explorer, then **restart the application** and call the API again. In this basic setup, dynamic refresh is not enabled yet, so portal changes are not necessarily reflected in the currently running application session.

### Quickly checking the configuration source without logging values

When you need to check which source is providing a key, you can temporarily create an `ApplicationRunner` in your development environment to print the **source names** containing that key:

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class ConfigDiagnostic {
    @Bean
    ApplicationRunner checkConfigSource(ConfigurableEnvironment environment) {
        return args -> {
            String key = "catalog.banner";
            System.out.println(key + " present: " + environment.containsProperty(key));
            for (PropertySource<?> source : environment.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("Found in source: " + source.getName());
                }
            }
        };
    }
}
~~~

This example checks the **presence** of the key and the sources containing it, without outputting the value. Spring may see the same key in multiple sources; the `PropertySource` order determines which source is selected. Only use this technique for non-sensitive keys and remove the diagnostic code when no longer needed.

## 8. Selecting Keys and Labels by Spring Profile

App Configuration has two selection dimensions:

- **Key filter** filters by key name.
- **Label filter** filters variants with the corresponding label (for example `dev`, `staging`, `prod`).

According to the provider, the default selector uses `/application/*` and the label matching `spring.profiles.active`; if there is no active profile, it uses **(No Label)**. When `label-filter` is set explicitly, that filter **replaces** the default active-profile-based label selection.

### 8.1. Illustrating two environments

Create additional values for the same keys:

| Key | Label | Value |
| --- | --- | --- |
| `/application/catalog.banner` | *(No Label)* | `Hello from Azure` |
| `/application/catalog.banner` | `dev` | `DEV Environment` |
| `/application/catalog.banner` | `prod` | `PRODUCTION Environment` |
| `/application/catalog.timeout` | `prod` | `PT2S` |
| `/application/catalog.max-items` | `prod` | `50` |

To run with the `prod` label, you can activate the `prod` Spring profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=prod
~~~

If you need **shared values from No Label + overrides from prod**, declare `selects` explicitly in `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: ",prod"
~~~

In this example, the leading comma represents **(No Label)**, and the part after it is `prod`. When two labels provide the same key, the value from the label listed **later** has higher precedence **within the dataset loaded by the provider**. Therefore `catalog.banner` is `PRODUCTION Environment`, while keys that only have No Label can still be loaded.

To avoid hard-coding the environment in the file, you can use:

~~~yaml
label-filter: ",${spring.profiles.active}"
~~~

Only use this variant when there is always a valid active profile. If you want to support running without a profile, design specifically for an empty profile placeholder or configure an appropriate selector.

### 8.2. Configuring multiple key-filters or multiple stores

When you need to select a specific set of keys, for example only the catalog group:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/catalog.*
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=prod
~~~

The value of `key-filter` is a service-side filter pattern; it is not a Java regular expression. Key naming conventions in App Configuration and the selector must align.

The application can also load from multiple stores:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].endpoint=${CATALOG_CONFIG_ENDPOINT}
spring.cloud.azure.appconfiguration.stores[1].endpoint=${SHARED_CONFIG_ENDPOINT}
~~~

According to the provider documentation, when two stores have duplicate keys, the store listed **later** in the list has higher precedence **among the stores**. This only describes precedence among Azure sources; `Environment` still has other sources with their own precedence order.

## 9. Understanding Precedence When Properties Are Overridden

For example, we have the same key in multiple places:

~~~yaml
# application.yml
catalog:
  banner: "Local value"
~~~

~~~text
Azure App Configuration:
/application/catalog.banner = "Azure value"
~~~

When importing via the Spring Config Data API, imported data can override values in the configuration document that declared that import, according to Spring Boot's rules. However, **you must not conclude that Azure always wins over everything**: higher-precedence sources, such as command-line arguments and many environment variables, can determine the final value.

Example test run:

~~~bash
java -jar target/catalog-api.jar --catalog.banner="Value from command line"
~~~

A structured way to diagnose:

1. **Does the key exist in Azure?** Check the right store, key name, and label.
2. **Did the provider select that key?** Check `spring.config.import`, `key-filter`, `label-filter`, and profile.
3. **Did the value enter `Environment`?** Check `environment.containsProperty(...)` and the `PropertySource` list.
4. **Which source is winning?** Check `PropertySource` order, environment variables, command-line arguments, and configuration files.
5. **Was the bean created before or after the configuration changed?** That is a refresh issue, not a startup configuration loading error.

Exposing `/actuator/env` or `/actuator/configprops` to the Internet just for debugging is risky because it can reveal metadata and sensitive configuration; only inspect them through protected tools and authorized access.

## 10. When Configuration Loading Fails at Startup

The provider supports **fail-fast** by default: if the store cannot be read, the application can fail immediately at startup. This is useful when configuration is mandatory for correct operation.

You can change the behavior for a store:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].fail-fast=false
~~~

When `fail-fast=false`, the provider can skip a failing store at startup; in that case, the application will only run properly if valid defaults or mandatory-configuration self-checks are in place. Do not enable this option merely to hide an authentication error or a missing endpoint.

Diagnostic table:

| Symptom | Cause to Check |
| --- | --- |
| Spring reports it does not recognize import `azureAppConfiguration` | Missing the corresponding App Configuration dependency, wrong import name, or incompatible BOM |
| 401/403 error when loading store | Identity used to acquire token, `App Configuration Data Reader` role, role scope, or propagation delay |
| `IllegalArgumentException` about connection method | Both `endpoint` and `connection-string` declared in the same store |
| Key missing even though visible in portal | Key missing `/application/`, wrong `key-filter`, wrong label/profile, or pointing to another store |
| Azure value exists but bean receives local value | Higher-precedence source, or bean was initialized/cached before refresh |
| Connection error despite identity having permission | DNS, firewall, proxy, private endpoint, VNet routing, TLS, or throttling |
| `Duration` or integer fails to bind | Value is not in valid format, e.g., `PT4S` and integer `25` |
| App fails only in cloud environment | Managed Identity principal differs from local identity; cloud network and role config are incomplete |

Avoid printing access tokens, connection strings, sensitive key-values, or the entire `Environment` during error handling. Prefer logging sanitized resource names, key filters, labels, and error types.

## 11. Testing the Application Without Accessing Real Azure

If a test only needs to verify logic that uses configuration, **disable the App Configuration provider** in `@SpringBootTest` and supply dummy values:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.appconfiguration.enabled=false",
    "catalog.banner=Test value",
    "catalog.timeout=PT1S",
    "catalog.max-items=8"
})
class CatalogSettingsTest {

    @Autowired
    CatalogSettings settings;

    @Test
    void bindsLocalTestProperties() {
        assertThat(settings.banner()).isEqualTo("Test value");
        assertThat(settings.timeout().getSeconds()).isEqualTo(1);
        assertThat(settings.maxItems()).isEqualTo(8);
    }
}
~~~

This approach verifies that the application **binds Spring properties into Java objects**. It does not prove that external configuration or Azure RBAC works; those belong in integration tests against a real test store.

A suitable integration test might:

1. Prepare a store and a principal with minimal read permissions in a dev environment.
2. Create `/application/catalog.banner` with the appropriate label.
3. Start the application with the dev endpoint and confirm the banner is read from Azure.
4. Try changing the label or role to make sure the resulting error is diagnosable.
5. Run tests from CI using a dedicated test identity, never using production secrets.

Never hard-code a real connection string in `@SpringBootTest` or commit it to the repo.

## 12. Refresh: Reloading Does Not Mean Immediate Update

The import in the steps above happens **at startup**. For the application to pick up changes without restarting, you must configure provider refresh according to your needs.

Advanced example: create sentinel key `/application/catalog.refresh-sentinel` with an empty Label and Value `1`. Then add:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key=/application/catalog.refresh-sentinel
~~~

Whenever you want to publish a group of new settings atomically, update the keys first, then update the sentinel to signal a change. According to provider documentation, refresh checks typically have a default minimum interval of **30 seconds** and require an appropriate trigger/watch key when monitoring is enabled.

With the `-web` library variant, an automatic check can occur when the application **receives a servlet request** and the check interval has elapsed. If the application receives no requests, merely waiting long enough does not guarantee a refresh has run. Even the request that triggers the check is not guaranteed to use the new values within that same request.

After the provider loads new data, `@ConfigurationProperties` can be updated according to supported refresh mechanisms; other beans that hold values themselves may need `@RefreshScope` or an explicit recreation mechanism. Test against your exact version and bean types before relying on runtime mutability.

**Boundary of this lesson:** startup configuration loading must work correctly first. Refresh, feature management, and Key Vault references are advanced flows that require separate testing, especially when values are secrets or span multiple instances.

## 13. Self-Check Practice Exercise

You manage `catalog-api` for two environments:

- `dev` uses timeout `PT8S` and banner `Testing`;
- `prod` uses timeout `PT2S` and banner `Ready to serve`;
- both environments use `catalog.max-items=20` as a shared default.

Create the Azure data, choose the **No Label + per-environment label** loading approach, bind into `CatalogSettings`, and verify the application with the test API.

**Design hint:**

| Key | Label | Value |
| --- | --- | --- |
| `/application/catalog.max-items` | *(No Label)* | `20` |
| `/application/catalog.timeout` | `dev` | `PT8S` |
| `/application/catalog.timeout` | `prod` | `PT2S` |
| `/application/catalog.banner` | `dev` | `Testing` |
| `/application/catalog.banner` | `prod` | `Ready to serve` |

Enable the corresponding profile and set the label filter with the expression `,${spring.profiles.active}` (taking care to ensure a profile is present).

**Review questions:**

1. Why can a key exist in the portal while `@Value` still reports the property is missing?
2. What different role does `spring.config.import` play compared to `stores[0].endpoint`?
3. What is the difference between `key-filter` and `label-filter`?
4. When the same key exists in Azure and in command-line arguments, what should you check before concluding where the value came from?
5. Why should unit tests not call the Azure store by default, and why does refresh not always happen immediately after changing a key?

**Guided answers:** (1) check import, key name, selector, label, and permissions; (2) import registers the Config Data source, while endpoint only specifies where to connect; (3) key filter selects key names, label filter selects variants; (4) the actual `PropertySource` order; (5) tests should isolate external dependencies, and refresh depends on monitoring, triggers, interval, requests, and bean lifecycle.

## 14. Reference Sources

- [Microsoft Learn – Quickstart: Spring Boot with Azure App Configuration](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-java-spring-app): creating keys, dependencies, Config Data import, and reading data.
- [Microsoft Learn – Spring App Configuration provider reference](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-cloud-azure-starter-appconfiguration-config-readme?view=azure-java-stable): `selects`, labels, stores, fail-fast, monitoring.
- [Microsoft Learn – Dynamic configuration in Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): manual/automatic refresh and trigger conditions.
- [Microsoft Learn – Upgrade App Configuration provider to v6](https://learn.microsoft.com/en-us/azure/azure-app-configuration/howto-convert-to-the-new-spring-boot): `spring.config.import` requirement and migration from bootstrap to application config.
- [Microsoft Learn – Spring Cloud Azure configuration overview](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): configuring credentials and consistency across Azure libraries.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `Environment`, configuration data sources, `spring.config.import`, and precedence order.
- [Azure SDK for Java – Spring Versions Mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): choosing the Spring Cloud Azure version compatible with Spring Boot.

After completing this lesson, you should be able to explain **by what rules values travel from the App Configuration store into the Spring `Environment`** and verify it with a small API or `@ConfigurationProperties`. Only once the startup loading flow is stable should you add advanced label selection, refresh, and Key Vault integration for secrets.
