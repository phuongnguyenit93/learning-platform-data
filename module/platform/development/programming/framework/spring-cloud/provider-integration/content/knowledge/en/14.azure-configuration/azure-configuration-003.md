# Keys, Labels, Filters, and Environment-Specific Configuration Mapping

When a Spring Boot application is deployed to `dev`, `staging`, and `prod`, the source code is usually identical, but values such as timeouts, retry counts, or API addresses must differ. **Azure App Configuration** solves this requirement using **key–value** pairs, **labels**, and **selection filters**. Spring Cloud Azure reads the appropriate set of values and maps them into properties in the Spring `Environment`.

This lesson belongs to the **Azure Configuration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: hands-on integration of Spring Boot with managed services of AWS, Azure, and Google Cloud, emphasizing identities/permissions, data and secrets, integration testing, and differences across providers. In this lesson, we focus on Azure's **configuration selection rules and key-name transformations**; the examples use non-sensitive operational configuration.

## 1. Objectives and Real-World Scenario

After studying this lesson, you should be able to explain and perform:

1. The difference between **key**, **label**, **value**, **tag**, and **store**.
2. How `key-filter` and `label-filter` determine which key-values are loaded.
3. Rules for **(No Label)**, `spring.profiles.active`, and precedence order when keys collide.
4. How to remove prefixes (`trim-key-prefix`) to turn an Azure key into a Spring property.
5. How to organize shared configuration + per-environment configuration; when a separate store is needed.
6. How to verify data in `Environment`, bind it into Java, and handle key/label selection errors.

Consider `checkout-service` with the same code across three environments:

| Configuration | dev | staging | prod |
| --- | --- | --- | --- |
| Payment timeout | `PT15S` | `PT8S` | `PT3S` |
| Max retries | `2` (shared default) | `2` (shared default) | `5` |
| API endpoint | `https://sandbox-payments.example.com` | `https://sandbox-payments.example.com` | `https://payments.example.com` |

Instead of maintaining three nearly identical `application.yml` files, we place **variants of the same key** into App Configuration and use labels to select the appropriate configuration.

~~~mermaid
flowchart LR
    A["App Configuration: multiple (key, label, value)"] --> B["key-filter"]
    B --> C["label-filter"]
    C --> D["Select version and resolve duplicate keys"]
    D --> E["trim-key-prefix"]
    E --> F["Spring PropertySource"]
    F --> G["@ConfigurationProperties / Environment"]
~~~

> **Remember the exact conceptual order:** *Filtering* determines which records are fetched; *precedence* determines which value wins on duplicate keys; *trimming* determines under which name the final key appears in Spring.

## 2. Data Model: Key, Label, Value, and Tag

An App Configuration entry has the following common attributes:

| Field | Meaning | Example |
| --- | --- | --- |
| **Key** | Logical name of the parameter, organizable with prefixes/delimiters | `/application/checkout.timeout` |
| **Label** | Variant of the key by environment, version, or scope | `dev`, `staging`, `prod` |
| **Value** | Value of the specific key-label | `PT3S` |
| **Content type** | Content-type hint for the provider, e.g., JSON or reference | `application/json` |
| **Tags** | Name–value metadata to help classify/filter | `team=payments` |
| **Store** | Azure resource containing the key-value set and access settings | `checkout-config` |

**The actual identifying unit is the (key, label) pair.** Within one store, all of these can coexist simultaneously:

~~~text
Key                              Label       Value
/application/checkout.timeout    (No Label)  PT6S
/application/checkout.timeout    dev         PT15S
/application/checkout.timeout    staging     PT8S
/application/checkout.timeout    prod        PT3S
~~~

These are **four different records of the same key**, not four different Java keys. On the Spring side, after selecting a label and stripping the prefix, all of them map to the property name `checkout.timeout`.

### 2.1. (No Label) is not the string "default"

A record with an empty label is usually displayed by the Azure portal as **(No Label)**. At the API layer, this value is represented as null/`\0` depending on context; in the Spring provider's `label-filter` property, an **empty element before a comma** represents (No Label):

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=,prod
~~~

The configuration above means: fetch values **without a label first**, then fetch values with label `prod` to override duplicate keys. It has nothing to do with a label literally named `default`, `null`, or `(No Label)`.

### 2.2. Key naming conventions

Keys in the following form are useful in Spring:

~~~text
/application/checkout.timeout
/application/checkout.max-retries
/application/checkout.endpoint
/application/checkout.feature-message
~~~

- `/application/` is the prefix that the Spring App Configuration provider selects **by default**.
- The part after the prefix uses Spring property syntax, such as `checkout.max-retries`.
- Azure App Configuration is case-sensitive in key names; standardize on lowercase and hyphens to avoid hard-to-spot bugs.
- Prefixes can separate applications or domains, such as `/checkout-service/checkout.timeout`, provided you configure the filter and trim accordingly.

**Do not use labels to hold secrets or assume labels act as a security boundary.** Labels categorize records; read access control in App Configuration is primarily enforced at the store scope. Sensitive data such as API tokens, passwords, and access keys belong in **Azure Key Vault**.

## 3. Default Selector in Spring Cloud Azure

When a project has the App Configuration provider and declares:

~~~properties
spring.config.import=azureAppConfiguration
spring.cloud.azure.appconfiguration.stores[0].endpoint=${AZURE_APPCONFIG_ENDPOINT}
~~~

the provider reads key-values from the store using the default selector:

| Component | When Not Configured Explicitly |
| --- | --- |
| Key filter | `/application/*` |
| Label filter, no active Spring profile | `(No Label)` |
| Label filter, with active Spring profile | Labels matching active profile names according to Spring precedence rules |
| Property name in Spring | Strips the prefix matched by the key filter, typically `/application/` |

For example, having only the key `checkout.timeout` (without `/application/`) will **not be selected** by the default filter. Conversely, `/application/checkout.timeout` with label `prod` will **not be loaded** when the application has no active profile and no explicit `prod` filter is specified.

**Both conditions must hold simultaneously:** the key name matches the key filter **and** the label matches the label filter.

### 3.1. Minimal configuration to test

Assume Spring Boot 3.5.x with a compatible Spring Cloud Azure 6.x line. The BOM in `pom.xml` selects a supported 6.x version, then declares the App Configuration dependency:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-appconfiguration-config</artifactId>
</dependency>
~~~

Example `application.yml`:

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

When using an endpoint and Microsoft Entra ID authentication, the application identity needs the **App Configuration Data Reader** role on the store. On Azure, use Managed Identity; a local machine can use an appropriate credential chain configuration and an authorized account. Example endpoint:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://checkout-config.azconfig.io
~~~

The store name and endpoint must be replaced with real resources. The `spring-cloud-azure-appconfiguration-config` dependency is sufficient for loading configuration; Spring Web applications can use the `-web` variant to add request-driven refresh check support.

## 4. Key Filter: Selecting the Scope of Configuration to Load

`key-filter` specifies a key name or key pattern. With Spring Cloud Azure, the configuration syntax is:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/*
~~~

Some common patterns:

| Key Filter | Meaning | Note |
| --- | --- | --- |
| `/application/*` | Keys starting with `/application/` | Provider default |
| `/application/checkout.*` | Only the key group with prefix `/application/checkout.` | Must check **trim prefix** to preserve `checkout.*` in Spring |
| `/application/checkout.timeout` | Selects one exact key | Does not automatically fetch `checkout.max-retries` |
| `/checkout-service/*` | Only the checkout-service namespace | Useful when sharing a store across multiple applications |

The filter supports prefix wildcard `*` and may support selecting multiple specific keys with commas per provider rules. **Do not combine wildcards and comma-separated lists in the same filter**; if you need two scopes, use multiple `selects` entries.

For example, loading only two distinct configuration groups:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/checkout.*"
                label-filter: "prod"
              - key-filter: "/application/fulfillment.*"
                label-filter: "prod"
            trim-key-prefix:
              - "/application/"
~~~

The `trim-key-prefix` section is declared explicitly so both groups take the form `checkout.*` and `fulfillment.*` on the Spring side. Without understanding the trim rules of narrow filters, `checkout.timeout` could inadvertently become `timeout`.

**Filters are retrieval conditions**, not rules that automatically assign every key to the right Java class. The final result also depends on the trimmed name and Spring's binding mechanism.

## 5. Label Filter: Selecting Variants by Environment

`label-filter` selects label variants of matched keys. When values collide, the provider resolves them according to **label precedence order**.

### 5.1. An explicit single label

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/*
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=prod
~~~

This **selects only** keys with label `prod`; keys that only exist with (No Label) will not appear automatically. That can cause shared defaults to be missing.

### 5.2. Combining (No Label) and environment labels

Create data in Configuration Explorer:

| Key | Label | Value |
| --- | --- | --- |
| `/application/checkout.timeout` | (No Label) | `PT6S` |
| `/application/checkout.timeout` | `dev` | `PT15S` |
| `/application/checkout.timeout` | `staging` | `PT8S` |
| `/application/checkout.timeout` | `prod` | `PT3S` |
| `/application/checkout.max-retries` | (No Label) | `2` |
| `/application/checkout.max-retries` | `prod` | `5` |
| `/application/checkout.endpoint` | (No Label) | `https://sandbox-payments.example.com` |
| `/application/checkout.endpoint` | `prod` | `https://payments.example.com` |

In `application.yml`, select the empty label first and the active-profile label second:

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

YAML uses single quotes around the entire string `',${spring.profiles.active}'` to preserve the comma and placeholder for Spring to process. This example **requires an active profile to be explicitly set**.

Run with the `prod` profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=prod
~~~

Or set the equivalent environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Following the rule that **the label on the right takes precedence**, the expected result is:

| Spring Property | Value Under Profile `prod` | Winning Source |
| --- | --- | --- |
| `checkout.timeout` | `PT3S` | Label `prod` |
| `checkout.max-retries` | `5` | Label `prod` |
| `checkout.endpoint` | `https://payments.example.com` | Label `prod` |

If running with profile `dev`, the expected result is `checkout.timeout=PT15S`, `checkout.max-retries=2` (fallback from No Label), and the sandbox endpoint. Profile `staging` gets timeout `PT8S` and the remaining shared values.

This is the **layered model**:

~~~mermaid
flowchart TB
    A["Shared layer: (No Label)"] --> C["Configuration result in Spring"]
    B["Environment layer: dev / staging / prod"] --> C
    D["If same key, environment layer overrides"] --> C
~~~

When there is no active Spring profile, do not use `',${spring.profiles.active}'` because the placeholder may not resolve as expected. Use the provider's default to fetch **(No Label)** alone, or declare a label independent of profiles, such as `label-filter: ',${DEPLOY_ENV:dev}'`. If using `DEPLOY_ENV`, ensure it accurately reflects the deployment environment.

### 5.3. Multiple simultaneous profiles

An application might enable `dev,observability`, which are **two active profiles**, not necessarily an Azure label named `dev,observability`. The provider supports evaluating multiple profiles in precedence order; load order matters when two labels both define the same key.

To keep environment-specific business configuration consistent, maintain **one primary environment profile** (`dev`, `staging`, `prod`) and separate secondary configurations such as `observability` if needed. Verify the final values of overlapping keys in a real environment, especially when using multiple `selects` or additional environment variables/command-line arguments.

### 5.4. When to use a label wildcard?

Some provider versions support `label-filter=*` to fetch multiple labels. However, if both `dev` and `prod` have the same key, selecting all labels **defeats environment separation** and makes values depend on loading override order. For operations, prefer selecting **explicitly the needed labels**; do not use `*` as a quick fix for missing data.

## 6. Mapping Azure Keys to Spring Properties

Spring Cloud Azure does not necessarily use the **exact Azure key name** as the name in `Environment`. It can **strip prefixes** before creating properties.

### 6.1. Default case

~~~text
App Configuration key                  Spring property
/application/checkout.timeout   ---->  checkout.timeout
/application/checkout.endpoint  ---->  checkout.endpoint
/application/checkout.max-retries ----> checkout.max-retries
~~~

Because `/application/*` is selected by default, the `/application/` prefix is normally removed. Java code uses only `checkout.timeout` rather than `/application/checkout.timeout`.

### 6.2. Checking trimming when changing key-filter

Suppose the store contains:

~~~text
/application/checkout.timeout
/application/checkout.max-retries
/application/catalog.timeout
~~~

To fetch only the checkout group while **preserving** the names `checkout.timeout` and `checkout.max-retries`, proactively declare the prefix to remove:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/checkout.*"
                label-filter: ',${spring.profiles.active}'
            trim-key-prefix:
              - "/application/"
~~~

Trimming `/application/` keeps `checkout.timeout` intact. This is a reliable approach when the key filter is narrower than the shared namespace. If trimming is left entirely to the `/application/checkout.*` key-filter, the `/application/checkout.` prefix may be stripped, leaving the property as `timeout`. Then `@ConfigurationProperties(prefix = "checkout")` will fail to bind properly.

When multiple prefixes need to be stripped in one store, `trim-key-prefix` can be declared as a list; choose specific prefixes and check for colliding keys **after trimming**.

### 6.3. Namespacing by application

You can use a shared store and name keys as:

~~~text
/checkout-service/checkout.timeout
/checkout-service/checkout.max-retries
/catalog-service/catalog.timeout
~~~

So that `checkout-service` only receives data belonging to it:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/checkout-service/*"
                label-filter: ',${spring.profiles.active}'
            trim-key-prefix:
              - "/checkout-service/"
~~~

The target properties in Spring are `checkout.timeout` and `checkout.max-retries`. This namespacing approach uses **key prefix** to select the application and **label** to select the environment; these two dimensions are orthogonal and can be combined.

### 6.4. Java binding and data types

Define the properties:

~~~java
package com.example.checkout;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutSettings(
        Duration timeout,
        int maxRetries,
        URI endpoint) {
}
~~~

Enable scanning in the application:

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

| Spring Property | Record Constructor | Data Example |
| --- | --- | --- |
| `checkout.timeout` | `Duration timeout` | `PT3S` → 3 seconds |
| `checkout.max-retries` | `int maxRetries` | `5` |
| `checkout.endpoint` | `URI endpoint` | `https://payments.example.com` |

Spring Binder supports relaxed binding, so `max-retries` maps to `maxRetries`. However, **do not expect the Binder to recover a mistrimmed prefix**: the property name must have the right structure before binding runs.

## 7. Distinguishing Four Easily Confused Precedence Layers

Many people see `checkout.timeout` receiving an unexpected value and blame “Azure overriding the local file”. In fact, there are four layers to inspect:

| Layer | Rule to Examine |
| --- | --- |
| **Selected key set** | `key-filter` and `label-filter` determine which records enter the provider |
| **Duplicate keys within one store** | With a label list like `,prod`, the label listed later wins; with multiple `selects`, check load order |
| **Across App Configuration stores** | If two stores produce the same property after trimming, the store listed later in the provider list has higher precedence |
| **Entire Spring Environment** | Local files, environment variables, system properties, command-line arguments, and imports have Spring Boot's own precedence order |

Example with two stores:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].endpoint=${SHARED_CONFIG_ENDPOINT}
spring.cloud.azure.appconfiguration.stores[1].endpoint=${CHECKOUT_CONFIG_ENDPOINT}
~~~

If both supply `checkout.timeout` and the filters select them, the provider gives the value from store `[1]` higher precedence than store `[0]`. However, a command-line argument such as:

~~~bash
java -jar checkout-service.jar --checkout.timeout=PT1S
~~~

can override the value loaded from App Configuration due to **Spring Environment–level precedence rules**. Check all property sources before concluding “the prod label isn't working”.

### 7.1. Why can using labels cause authorization issues?

There is no guarantee that an identity authorized to read a store can read only the `dev` label and not the `prod` label. Therefore:

- If `dev`/`staging`/`prod` differ only in non-sensitive parameters and the same operations group is permitted to read them, **one store + labels** can be suitable.
- If the `prod` environment requires isolated access permissions, a **separate store for prod** is a clearer model.
- If a value is a secret (password, token), store it in **Key Vault** and use a reference when needed; do not treat labels or tags as a secret-protection mechanism.

### 7.2. Organizing stores and labels across multiple applications

| Context | Suggested Structure |
| --- | --- |
| One application, several environments with shared permission group | One store; `/application/*` keys, `dev`/`staging`/`prod` labels |
| Multiple applications sharing one store | Per-application key prefix, per-environment labels; trim so Java code stays stable |
| Multiple applications sharing common parameters | Shared store for defaults, application store listed later to override specific keys |
| Production requiring isolated permissions and networking | Separate store per environment, dedicated data reader roles |
| Need to freeze a configuration set for a release | Consider **App Configuration snapshots** instead of relying solely on mutable labels |

## 8. Advanced Filters: Tags and Snapshots

### 8.1. Tag filter when supported by the library

A tag is `name=value` metadata, such as `team=checkout` and `region=apac`. In Spring Cloud Azure versions that support `tags-filter` (for example App Configuration library 7.1 and later), you can restrict records using multiple tags:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: "prod"
                tags-filter:
                  - "team=checkout"
                  - "region=apac"
~~~

Multiple `tags-filter` entries are combined with **AND**: a record must match **all requested tags**. Unlike labels, tags can describe multiple metadata dimensions, but they cannot replace access control.

**Version note:** Do not copy `tags-filter` into a project using Spring Cloud Azure 6.x if that release does not support the property; check the README/changelog of **the exact dependency version in use**. The core part of this lesson only needs key filters and label filters.

### 8.2. Snapshots and the prefix-trimming pitfall

A snapshot is a point-in-time capture of configuration, useful when you need exact control over a release's configuration. When selecting a snapshot via `snapshot-name`, normal `key-filter` auto-trimming rules do not apply; specify the prefix explicitly:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - snapshot-name: "checkout-release-2026-11"
            trim-key-prefix:
              - "/application/"
~~~

The snippet above is only an example **if the snapshot already exists** with a name and composition type supported by the provider. Snapshots are immutable; modifying keys in the store does not alter that snapshot. Do not combine `snapshot-name` with `key-filter`/`label-filter` in **the same select** if your library version requires choosing one selection mode.

## 9. Verifying Loaded Keys, Labels, and Properties

### 9.1. Results before and after selecting a label

Assuming the table in section 5 and configuration `label-filter: ',${spring.profiles.active}'`:

| Active Profile | `checkout.timeout` | `checkout.max-retries` | `checkout.endpoint` |
| --- | --- | --- | --- |
| `dev` | `PT15S` | `2` | Sandbox |
| `staging` | `PT8S` | `2` | Sandbox |
| `prod` | `PT3S` | `5` | Production |

This is the first verification criterion: **a different profile must cause exactly the overridden keys to change**, while shared defaults remain intact.

### 9.2. Printing PropertySource names without logging values

To check which sources contain a key without putting sensitive values into logs, you can use a diagnostic snippet in your **development environment**:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class ConfigSourceDiagnostics {
    @Bean
    ApplicationRunner reportKeySources(ConfigurableEnvironment env) {
        return args -> {
            String key = "checkout.timeout";
            System.out.println("Has property: " + env.containsProperty(key));
            for (PropertySource<?> source : env.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("PropertySource: " + source.getName());
                }
            }
        };
    }
}
~~~

The list may show **multiple sources containing a key**; the highest-precedence source in Spring's current order supplies the effective value. Inspecting source names and trimmed keys is safer than printing `env.getProperty(...)` for every property.

### 9.3. Testing binding without depending on real Azure

For a test that only verifies Java mapping, disable App Configuration and inject test properties into Spring:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.appconfiguration.enabled=false",
    "checkout.timeout=PT2S",
    "checkout.max-retries=9",
    "checkout.endpoint=https://localhost.example.test"
})
class CheckoutSettingsTest {
    @Autowired
    CheckoutSettings settings;

    @Test
    void bindsValues() {
        assertThat(settings.timeout()).isEqualTo(Duration.ofSeconds(2));
        assertThat(settings.maxRetries()).isEqualTo(9);
        assertThat(settings.endpoint().getHost()).isEqualTo("localhost.example.test");
    }
}
~~~

This test verifies the Spring Binder and data types. Only an **integration test** proves that the provider actually selects the right keys and labels in App Configuration, that the identity has read permissions, and that overrides behave properly per environment.

### 9.4. Integration testing checklist

With a test dev store and a principal with minimal read permissions:

1. Create `checkout.timeout` with (No Label) and two labels `dev`/`prod`.
2. Run profile `dev`, verify `checkout.timeout` via a bean or internal endpoint restricted to non-sensitive data.
3. Switch to profile `prod`, restart, and verify the different value.
4. Delete the **dev record** in the test environment and verify fallback to (No Label) when using filter `,dev`.
5. Narrow `key-filter` to `/application/checkout.*`, check `trim-key-prefix` so Java properties still retain the `checkout.*` name.
6. Test behavior when switching stores, using a wrong label, or revoking read permission from the identity; confirm no credentials leak into logs.

## 10. Common Errors and Root Cause Identification

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Key exists in Azure but Spring does not see it | Does not match `key-filter` or `label-filter` | Verify the specific (key, label) pair; do not check key name alone |
| Running profile `prod` but seeing default | Only selecting (No Label), or value overridden by another Spring source | Check `label-filter` and `PropertySource` order |
| Running profile `prod` but missing shared defaults | Filter selects only `prod` | Use `label-filter: ',prod'`, placing (No Label) first |
| `@ConfigurationProperties(prefix="checkout")` fails to bind | `trim-key-prefix` stripped `checkout.` too | Inspect property names in `Environment`, trim `/application/` accurately |
| Key missing even though Java code did not change | Key prefix or naming structure changed | Standardize namespace and provide migration for old keys |
| Two keys overwrite each other after trimming | Different prefixes produce the same Spring property name | Design non-conflicting namespaces and identify winning source |
| Multiple profiles yield unexpected results | Label priority and profile order | Keep environment profiles clear; verify effective config with tests |
| Azure returns 403 | Identity lacks `App Configuration Data Reader` | Assign data role to the actual principal; check scope |
| App works locally, fails in cloud | Cloud store endpoint/profile/role differs | Compare connection metadata, profile, and namespace; never log credentials |
| Using `tags-filter` yields no data | Missing required tag or unsupported provider version | Check AND-ed tags and dependency version |
| Selecting snapshot keeps `/application/` on keys | Snapshots do not auto-trim like normal key filters | Add `trim-key-prefix: ["/application/"]` |

**Distinguish key-selection errors from refresh errors:** changing a value in the store while the application is running does not always update beans immediately. This lesson primarily examines **values loaded at startup**; if runtime updates are needed, configure monitoring/refresh and bean lifecycles separately. Before investigating refresh, verify whether the value received after a **fresh startup** is correct.

## 11. Design Decisions to Establish Proactively

When adopting App Configuration in a real project, agree on:

1. **Namespace convention:** `/application/` for a simple app, or `/<service-name>/` if multiple apps share a store.
2. **Label convention:** `dev`, `staging`, `prod`, or team-defined environment names; avoid multiple synonyms.
3. **Fallback:** whether to fetch shared (No Label) values for all environments; if yes, place (No Label) at the beginning of `label-filter`.
4. **Duplicate values:** verify ordering across multiple labels, multiple selects, and multiple stores with real tests.
5. **Prefix trimming:** explicitly define Spring property names after loading, especially with narrow key filters or snapshots.
6. **Isolation level:** environments requiring different permissions should consider separate stores; secrets belong in Key Vault.
7. **Observability and testing:** never log credentials; inspect property sources and maintain tests for every critical environment.

Aligning on these decisions lets Spring code keep the same property names (`checkout.timeout`, `checkout.endpoint`) across environments, while Azure only changes **which records are selected** and **which value takes precedence**.

## 12. Applied Exercise

An organization deploys `shipping-service` to `dev` and `prod`. A shared store contains:

~~~text
/application/shipping.timeout    (No Label)  PT5S
/application/shipping.timeout    prod        PT2S
/application/shipping.max-batch  (No Label)  50
/application/shipping.max-batch  prod        200
/application/catalog.timeout     prod        PT9S
~~~

Requirements:

1. Load only the `shipping.*` key group.
2. Select (No Label) and then override with `prod` based on the active profile.
3. In Spring, property names must be `shipping.timeout` and `shipping.max-batch`.
4. Do not load `catalog.timeout`.
5. Verify expected results when running `dev` and `prod`.

Suggested configuration (assuming exactly one environment profile is always active):

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
              - key-filter: "/application/shipping.*"
                label-filter: ',${spring.profiles.active}'
            trim-key-prefix:
              - "/application/"
~~~

**Expected results:**

| Profile | `shipping.timeout` | `shipping.max-batch` | `catalog.timeout` |
| --- | --- | --- | --- |
| `dev` | `PT5S` (fallback) | `50` (fallback) | Not loaded |
| `prod` | `PT2S` | `200` | Not loaded |

**Self-assessment questions:**

- If using only `label-filter=prod`, what happens to keys without a `prod` variant?
- Why can `key-filter=/application/shipping.*` turn `shipping.timeout` into `timeout` without explicit trimming?
- Is an `App Configuration Data Reader` prevented from reading the `prod` label in the same store solely by the application's filter?
- Is a key-value with label `dev` loaded when Spring has no active profile and `label-filter` is omitted?
- After changing a value in Azure, why does a test need a restart or a refresh mechanism to observe the change?

Guided answers: (1) keys with only No Label are skipped; (2) the prefix is trimmed by the narrow filter instead of the shared prefix; (3) no, application filters are not an authorization boundary; (4) no, the default uses (No Label); (5) because loaded values may be cached and beans do not automatically update instantaneously.

## 13. Official References

- [Microsoft Learn – Developer Guide for Using Spring Cloud Azure App Configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): `key-filter`, `label-filter`, `trim-key-prefix`, profile selection, and multi-store loading.
- [Azure SDK for Java – App Configuration Spring starter README](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/spring/spring-cloud-azure-starter-appconfiguration-config/README.md): property reference, `selects`, label priority, tag filters, and snapshots.
- [Microsoft Learn – Azure App Configuration FAQ](https://learn.microsoft.com/en-us/azure/azure-app-configuration/faq): (No Label), Spring profiles, separate stores for security isolation.
- [Microsoft Learn – Understand Azure App Configuration key-value store](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-key-value): key/label structure and distinguishing records.
- [Microsoft Learn – App Configuration best practices](https://learn.microsoft.com/en-us/azure/azure-app-configuration/howto-best-practices): key prefix planning, labels, and configuration organization.
- [Microsoft Learn – Manage App Configuration snapshots](https://learn.microsoft.com/en-us/azure/azure-app-configuration/howto-create-snapshots): immutable snapshots and the need for explicit prefix trimming.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Spring `Environment`, `PropertySource`, and configuration precedence rules.

When designing multi-environment configuration, read properties through four questions: **(1) does the key match the filter, (2) which label is selected, (3) what is the property name after trimming, and (4) which source holds final precedence?** Answering these four questions lets you predict and test Spring Cloud Azure configuration systematically.
