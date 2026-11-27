# Feature Flags and Boundaries with Regular Configuration

A Spring Boot application may need to change **operational values** (for example increasing a timeout from 3 seconds to 5 seconds) or change **which feature is allowed to execute** (for example allowing only 5% of users to try a new checkout flow). These two decisions are often lumped together under “config”, yet they have different purposes, evaluation mechanisms, and lifecycles.

**Azure App Configuration** supports both **regular key-values** and **feature flags**. With **Spring Cloud Azure**, key-values are loaded into the Spring `Environment` to bind via `@ConfigurationProperties` or `@Value`, while feature flags are evaluated by the **Feature Management** library through `FeatureManager`. A feature flag is not merely a boolean variable: it can contain conditions based on users, groups, rollout percentages, or time windows.

This lesson belongs to the **Azure Configuration** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on hands-on integration of Spring Boot with managed services from AWS, Azure, and Google Cloud, including identities/permissions, data, storage, messaging, secret protection, testing, and comparing cloud providers. Here, the focus is on **knowing when to use a feature flag versus regular configuration**, configuring Spring Cloud Azure properly, and operating feature flags safely.

## 1. One Scenario, Two Types of Decisions

Suppose `checkout-service` has two payment flows:

- **The old flow (v1)** currently serves all users.
- **The new flow (v2)** is already implemented in the codebase but should only be opened gradually to a pilot group.

At the same time, both flows call a partner API and require timeouts, retries, and an endpoint.

| Question | Appropriate Representation | Example |
| --- | --- | --- |
| Is checkout v2 allowed to run? | **Feature flag** | `NewCheckout` on/off |
| Open checkout v2 only for a canary group? | **Feature flag with targeting filter** | Users belonging to group `pilot` |
| Expand from 5% to 25% of users? | **Feature flag with rollout/targeting** | Adjusting exposure percentage |
| How long before timing out when calling the gateway? | **Regular key-value** | `checkout.timeout=PT3S` |
| Maximum number of retries? | **Regular key-value** | `checkout.max-retries=3` |
| Non-sensitive API address in `prod`? | **Key-value by label** | `checkout.endpoint=https://pay.example.com` |
| Partner API key/password? | **Azure Key Vault** | Secret `payment-provider-token` |

**Selection principle:** if you want to *tune a parameter* the system already uses, start with regular configuration. If you want to *decide whether and for whom a new behavior is executed*, consider a feature flag. If it is a secret, put it in Key Vault, even when that secret is used by a flagged feature.

## 2. Comparing Feature Flags and Regular Configuration

| Aspect | Regular Configuration | Feature Flag |
| --- | --- | --- |
| Core question | “Which value is currently used?” | “Is this feature enabled in the current context?” |
| Typical data | Strings, numbers, durations, URLs, collections | On/off state, conditions, filters, variants |
| Examples | `checkout.timeout`, `checkout.max-retries` | `NewCheckout`, `UseNewRiskEngine` |
| Access in Spring | `@ConfigurationProperties`, `@Value`, `Environment` | `FeatureManager.isEnabled("...")` |
| Decision granularity | Application/environment configuration | Can vary per request, user, group, or time |
| Azure tool | **Configuration Explorer** | **Feature Manager** |
| Data selection | `stores[].selects` by key/label | `stores[].feature-flags.selects` by flag name/label |
| Lifecycle | Changed when tuning operations | Typically tied to releases, canaries, experiments, or kill switches |
| Common risks | Type mismatches, unintended source overrides, config drift | Complex branching logic, inconsistent experience, stale flags |

Both data types **are distributed through App Configuration**, but the consuming libraries and APIs differ. Do not create a `new-checkout=true` key in Configuration Explorer and expect `FeatureManager.isEnabled("NewCheckout")` to automatically treat it as a feature flag.

### 2.1. Is a boolean property ever enough?

Yes. If an internal application only needs static per-environment configuration such as `reports.include-archive=false`, with no need for rollouts, targeting, feature lifecycle management, or frequent changes, a boolean property may be the simplest approach.

When you need to toggle a feature **without redeploying**, orchestrate experiments, record which users saw a feature, or roll back quickly to the old flow, feature flags provide a clearer mechanism. Of course, runtime changes still depend on the refresh mechanism and how the application evaluates the flag; do not assume “turned on in the portal” means “every instance updates instantaneously”.

### 2.2. Feature flags are not an authorization mechanism

A flag answers “should this feature be enabled?”; authentication and authorization answer “is the caller **permitted** to access this resource?”. Therefore:

- Do not replace `Spring Security`, `@PreAuthorize`, RBAC, or business-domain permission checks with a feature flag.
- Do not use a feature flag as the sole measure protecting personal data or administrative accounts.
- Users may see a new feature enabled and still have to pass normal authorization checks.
- If a flag is missing, errored, or turned off, the application must have reasonable and safe fallback behavior.

## 3. What Does a Feature Flag Stored in Azure Contain?

When creating a flag in App Configuration's **Feature Manager**, you will encounter these fields:

| Attribute | Purpose |
| --- | --- |
| **Name / ID** | Identifier used by Java code to check, e.g., `NewCheckout` |
| **Enabled** | Top-level switch: currently on or off |
| **Label** | Variant by environment or scope, e.g., `dev`, `staging`, `prod` |
| **Description** | Explains the meaning and ownership of the flag |
| **Client filters / conditions** | Rules determining when a flag is enabled, e.g., percentage or target audience |
| **Variants** | When using variant-type flags, returns different experience options or values |

In the App Configuration store, a feature flag has a **specialized record format** (internal key name following conventions like `.appconfig.featureflag/NewCheckout` along with a dedicated feature-flag content type). Do not manually create a regular key-value with a flag-like name; use **Feature Manager**, Azure CLI, or the feature-flag management SDK/API to ensure the exact format.

Three scenario groups on Azure are commonly presented as:

1. **Switch:** simple feature on/off toggle.
2. **Rollout:** gradually opening a feature by percentage or specific targets.
3. **Experiment:** distributing experience variants and tracking metrics for evaluation.

Specific capabilities such as variant assignment, telemetry, and targeting depend on the Feature Management client version line. In the first hands-on example, we use a **Switch** to clarify the boundary with regular properties; later sections explain rollouts and filters.

## 4. Integration Architecture with Spring Cloud Azure

~~~mermaid
flowchart TD
    Portal["Azure App Configuration store"] -->|Key-value| Provider["Spring Cloud Azure App Configuration provider"]
    Portal -->|Feature flags| Provider
    Provider -->|"PropertySource: checkout.timeout"| Env["Spring Environment"]
    Provider -->|"feature-management"| Flags["Feature Management configuration"]
    Env --> Settings["@ConfigurationProperties / @Value"]
    Flags --> Manager["FeatureManager"]
    Manager --> Decision["isEnabled(NewCheckout)"]
    Settings --> Business["Checkout service"]
    Decision --> Business
    Vault["Azure Key Vault: secret if needed"] -.-> Business
~~~

To complete this flow, the application uses two dependencies with distinct responsibilities:

- **App Configuration provider** loads data from Azure.
- **Feature Management library** reads the feature configuration and evaluates flags at call time.

Important point: **Feature Management does not require Azure**. You can declare feature flags in `application.yml` and still use `FeatureManager`. Adding App Configuration provides centralized flag governance and supports loading/refreshing data from Azure.

## 5. Hands-On: Toggling Checkout v2 from Azure

### 5.1. Preparing the App Configuration store

Assume a `demo-checkout-config` store already exists with endpoint:

~~~text
https://demo-checkout-config.azconfig.io
~~~

Create two different data types on the Azure portal:

**In Configuration Explorer**, create regular key-values:

| Key | Label | Value |
| --- | --- | --- |
| `/application/checkout.timeout` | (No Label) | `PT3S` |
| `/application/checkout.max-retries` | (No Label) | `3` |

**In Feature Manager**, create a **feature flag**:

| Name | Label | Initial State |
| --- | --- | --- |
| `NewCheckout` | (No Label) | Off |

Select the Switch type and leave conditions/filters empty at the initial step. Add a description, for example “Controls checkout v2 flow; owner: team payments”.

At this point Azure holds two **coexisting configuration types**. `checkout.timeout` is not a flag, and `NewCheckout` must be created in the feature flag UI.

### 5.2. Choosing a compatible Spring Cloud Azure version

The example project uses **Spring Boot** and **Maven**. Choose the Spring Cloud Azure BOM according to the support matrix for your Spring Boot version (for example Spring Boot 4.0.x with the Spring Cloud Azure 7.x line). An illustrative Maven configuration:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-azure.version>7.2.0</spring-cloud-azure.version>
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

    <!-- Load key-values and feature flags from App Configuration -->
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-appconfiguration-config</artifactId>
    </dependency>

    <!-- Evaluate feature flags via FeatureManager -->
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-feature-management</artifactId>
    </dependency>
</dependencies>
~~~

`7.2.0` is an illustrative BOM version following the Microsoft quickstart; check the version mapping when implementing in a real project. If you need `@FeatureGate` integrated with Spring MVC, you can choose `spring-cloud-azure-feature-management-web` instead of the core feature management library. Only add `spring-cloud-azure-appconfiguration-config-web` when you want to leverage automatic refresh checks tied to Spring Web; using Spring Web in an application does not automatically require both `-web` variants.

### 5.3. Configuring Spring import and enabling feature flags

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
            feature-flags:
              enabled: true
~~~

Declare the environment variable:

~~~bash
export AZURE_APPCONFIG_ENDPOINT="https://demo-checkout-config.azconfig.io"
~~~

In PowerShell:

~~~powershell
$Env:AZURE_APPCONFIG_ENDPOINT = "https://demo-checkout-config.azconfig.io"
~~~

**Explaining the three decisive lines:**

- `spring.config.import=azureAppConfiguration`: instructs Spring Boot to use the App Configuration provider during Config Data loading.
- `stores[0].endpoint`: identifies the store to read configuration from; this is an endpoint URL, not a secret.
- `stores[0].feature-flags.enabled=true`: instructs the provider to **also load feature flags**, in addition to regular key-values.

If you forget `feature-flags.enabled`, `checkout.timeout` can still appear in the Spring `Environment`, but `FeatureManager` will not receive the `NewCheckout` flag from the store and may return false because the definition is missing.

### 5.4. Identity and read permissions

When using Microsoft Entra ID, the identity the application uses needs the **App Configuration Data Reader** role on the store. For workloads running on Azure, use **Managed Identity** and assign the role to the exact principal. A local machine can use an appropriate credential chain and an authorized developer account.

An account with resource management permissions on the Azure portal does not necessarily have permission to **read data**. Never work around a 403 error by copying a connection string containing an access key into the repository. If using Key Vault references for secrets in an extended scenario, the workload also needs separate secret-read permissions on Key Vault.

## 6. How Spring Code Uses Both Configuration Types

### 6.1. Binding key-values with `@ConfigurationProperties`

~~~java
package com.example.checkout;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutSettings(Duration timeout, int maxRetries) {
}
~~~

Create the application class:

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

When import works, `/application/checkout.timeout=PT3S` is mapped by the provider to `checkout.timeout`, and then Spring Binder creates `Duration.ofSeconds(3)`. This configuration is used as a **parameter**, not as a condition to turn a feature on or off.

### 6.2. Checking flags with `FeatureManager`

~~~java
package com.example.checkout;

import com.azure.spring.cloud.feature.management.FeatureManager;
import org.springframework.stereotype.Service;

@Service
public class CheckoutFlowSelector {
    private final FeatureManager featureManager;
    private final CheckoutSettings settings;

    public CheckoutFlowSelector(
            FeatureManager featureManager,
            CheckoutSettings settings) {
        this.featureManager = featureManager;
        this.settings = settings;
    }

    public String selectFlow() {
        // Evaluate flag at the decision point; do not capture a fixed result at bean initialization
        return featureManager.isEnabled("NewCheckout") ? "checkout-v2" : "checkout-v1";
    }

    public long gatewayTimeoutMillis() {
        // This is still regular configuration
        return settings.timeout().toMillis();
    }
}
~~~

Example REST controller returning only non-sensitive information:

~~~java
package com.example.checkout;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutPreviewController {
    private final CheckoutFlowSelector selector;

    public CheckoutPreviewController(CheckoutFlowSelector selector) {
        this.selector = selector;
    }

    @GetMapping("/checkout/preview")
    public Map<String, Object> preview() {
        return Map.of(
                "flow", selector.selectFlow(),
                "timeoutMillis", selector.gatewayTimeoutMillis());
    }
}
~~~

Run the application and call:

~~~bash
curl http://localhost:8080/checkout/preview
~~~

If `NewCheckout` is Off and timeout is `PT3S`:

~~~json
{"flow":"checkout-v1","timeoutMillis":3000}
~~~

After enabling the flag in Azure Feature Manager and **restarting the application** (the basic example has not enabled refresh yet), expected output:

~~~json
{"flow":"checkout-v2","timeoutMillis":3000}
~~~

The timeout value does not change just because the flag was enabled. The two pieces of data serve two independent decisions.

### 6.3. Placing flag checkpoints appropriately

Typically you should check at a **behavioral decision boundary**, such as choosing a service implementation, selecting a view template, or routing a business flow:

~~~java
if (featureManager.isEnabled("NewCheckout")) {
    // Execute the new flow with v2 rules
} else {
    // Execute the current flow
}
~~~

Do not branch across every layer from controller to service to repository, because a flag change mid-request could produce a half-v1, half-v2 state. For complex requests, **lock in the decision once per request or workflow** and pass that consistent choice down to relevant components.

With Spring Web, the `spring-cloud-azure-feature-management-web` library provides a request-scoped `FeatureManagerSnapshot` to keep evaluation results consistent within a single request; it also provides `@FeatureGate` to block an endpoint when a flag is Off. By default `@FeatureGate` may return **HTTP 404** via a disabled handler. This is a **feature gate** and still requires proper authorization if the endpoint accesses protected data or operations.

## 7. Environment-Specific Flag Configuration and Filters

App Configuration supports **labels** for both key-values and feature flags. However, the two groups use **two different selectors**.

Example of an application with a timeout key-value following the `prod` profile and a flag fixed to `dev`:

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
            feature-flags:
              enabled: true
              selects:
                - key-filter: "*"
                  label-filter: "dev"
~~~

- `stores[].selects` filters **regular key-values**.
- `stores[].feature-flags.selects` filters **feature flags**.
- In the example, flags always pull label `dev`, even when the active profile is `prod`. This is only to show that the two filters are independent, **not a production configuration you should use**.

To make flags follow the active environment, replace the flag selector with:

~~~yaml
feature-flags:
  enabled: true
  selects:
    - key-filter: "*"
      label-filter: "${spring.profiles.active}"
~~~

This assumes exactly one active environment profile (`dev`, `staging`, `prod`). If you only have flags with **(No Label)** as in step 5, omit `feature-flags.selects` to use the default selector, or configure a No Label selector explicitly per your provider version's guide. **Do not automatically assume** that the No Label fallback behavior of key-values always applies identically to feature flags.

### 7.1. A feature can be enabled in dev but disabled in prod

| Flag | Label | Enabled | Behavior |
| --- | --- | --- | --- |
| `NewCheckout` | `dev` | On | For the development team to test |
| `NewCheckout` | `staging` | On | For the QA team to verify |
| `NewCheckout` | `prod` | Off | Production users stay on v1 |

When you want a canary in prod, you do not have to switch it On for everyone: you can attach rollout/targeting conditions on the **prod record**, and roll out in stages. Ensure roles/accounts are scoped to those permitted to modify flags and govern the release process.

### 7.2. Boundary between labels and authorization

Labels are not a **security boundary** by default. Someone with read permissions on an App Configuration store can typically read records across multiple labels according to their granted role. If production requires separate permission boundaries or private networking, consider a dedicated store for production rather than relying on label names to prevent exposure.

## 8. Feature Filters: The Biggest Difference from a Regular Boolean

A key-value `new-checkout.enabled=true` usually has only two states. Feature Management can attach conditions so the final state varies by evaluation context.

| Filter | Use Case | Caution |
| --- | --- | --- |
| **TimeWindowFilter** | Enable a feature within a time window or recurring schedule | Time zones, start/end timestamps, clock synchronization |
| **PercentageFilter** | Randomly enable at a percentage during evaluation | Results may differ across evaluations |
| **TargetingFilter** | Target specific users, groups, or audience percentages | Must supply accurate identity/context; test stickiness |
| **Custom FeatureFilter** | Domain-specific conditions, e.g., tenant or account tier | Rules must be deterministic, tested, and have a fallback path |
| **Variants** | Assign users into one of multiple experience variants | Do not use variants to replace authentication/authorization |

### 8.1. Random percentage vs. stable user-based rollout

Suppose `PercentageFilter` is configured with parameter 10%. According to Spring Cloud Azure documentation, this filter can produce **a different result on each evaluation**. If a request evaluates it multiple times, a user risks experiencing inconsistent state unless a per-request snapshot mechanism is used.

If the goal is that **a selected user continues to see the same version** across requests, you need a targeting/assignment strategy based on a stable identity or an appropriate distribution mechanism, rather than using a random percentage check as a promise of a fixed user cohort.

### 8.2. Example of configuring flags in local YAML

The Feature Management library also understands flag structures defined **directly in Spring configuration**; this is useful for local development or testing without Azure:

~~~yaml
feature-management:
  feature_flags:
    - id: NewCheckout
      enabled: true
    - id: NewRecommendation
      enabled: false
    - id: PartialCheckout
      enabled: true
      conditions:
        client_filters:
          - name: PercentageFilter
            parameters:
              Value: 10
~~~

This is a **dedicated feature-management schema**, different from:

~~~yaml
checkout:
  timeout: PT3S
  max-retries: 3
~~~

Flag data resides under `feature-management` and is evaluated by `FeatureManager`. Regular checkout data resides under `checkout` and is type-converted by Spring Binder.

Syntax, supported filters, and how targeting context is passed can vary across Feature Management lines; when implementing targeting/variants, consult the documentation for the exact dependency version.

### 8.3. Custom feature filters must have clear rules

A custom filter must map the **filter name on Azure** to a Spring bean implementing `FeatureFilter`. Basic skeleton example:

~~~java
import com.azure.spring.cloud.feature.management.filters.FeatureFilter;
import com.azure.spring.cloud.feature.management.models.FeatureFilterEvaluationContext;
import org.springframework.stereotype.Component;

@Component("MaintenanceWindow")
public class MaintenanceWindowFilter implements FeatureFilter {
    @Override
    public boolean evaluate(FeatureFilterEvaluationContext context) {
        // Example only: real logic must account for hours, time zone, and operational policy
        return false;
    }
}
~~~

When a flag references a filter named `MaintenanceWindow`, the library looks up the matching bean. If the filter is missing or throws an exception, behavior depends on `spring.cloud.azure.feature.management.fail-fast`. Design a clear off/fallback branch so the system behaves predictably during incidents.

## 9. Refreshing Flags While the Application Is Running

In the basic example, we **restarted the application** after changing the flag in the portal. That lets you verify startup data loading before introducing refresh.

To enable Spring Cloud Azure App Configuration's refresh check mechanism:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].feature-flags.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.feature-flag-refresh-interval=30s
~~~

According to provider documentation, when **feature flags and monitoring** are both enabled, the provider can periodically check for flag changes; the default interval is about **30 seconds**. That is a **minimum check interval**, not a latency SLA from portal edit to every user.

Using only `spring-cloud-azure-appconfiguration-config` requires an active mechanism to trigger refresh checks via an appropriate API/endpoint. If using `spring-cloud-azure-appconfiguration-config-web`, automatic checks are tied to **Spring Web request activity**. An instance receiving no requests may not have checked even after 30 seconds have passed.

Distinguish the caching layers:

1. **App Configuration provider** holds the loaded data snapshot and tracks refresh.
2. **FeatureManager/FeatureManagerSnapshot** evaluates and may hold results per scope (e.g., per request).
3. **Business code** may cache decisions itself if a developer stores them in a field/bean.

Therefore, even when the provider has refreshed configuration, an **object that captured `isEnabled` at startup** will not update on its own. Always define the **evaluation point and consistency scope** of a feature flag.

### 9.1. Multiple instances and rollback

Suppose there are three instances of `checkout-service` behind a load balancer. When changing `NewCheckout` from Off to On:

- Instances may perform refresh checks at different times.
- During the transition window, the same user may see v1 and v2 on successive requests.
- The release process should tolerate **eventual consistency**, include per-version/per-branch observability, and have a clear rollback plan.

For features that write data or perform transactions, ensure data schemas and protocols remain compatible while both flows are active simultaneously. Do not use a flag to hide a **non-backward-compatible** schema change that has already been applied.

## 10. Fail-Fast and Safety When a Flag Does Not Exist

There are two easily confused error categories:

| Error | Where It Happens | What to Check |
| --- | --- | --- |
| Cannot read App Configuration store (401/403, network, wrong endpoint) | **Config provider** at startup/refresh | `spring.cloud.azure.appconfiguration.stores[0].fail-fast`, identity, role, network |
| Flag loaded, but has a missing/throwing filter | **Feature Management evaluator** | `spring.cloud.azure.feature.management.fail-fast`, filter bean name, parameters |

When a flag **has no definition**, `FeatureManager.isEnabled("...")` returns `false` per documentation. This is helpful when you want safe-by-default behavior for new features. However, if it is a **kill switch to shut off a dangerous behavior**, you must define the meaning of the missing state and fallback carefully: a “missing = off” design could cause the old branch to execute, and the old branch is not necessarily safe in every situation.

If a flag references an unrecognized filter, `FeatureManager` normally throws an error when `spring.cloud.azure.feature.management.fail-fast=true` (the documented default); you can configure `false` so the evaluator returns false instead of throwing. Do not disable fail-fast just to mask a misspelled filter name in production: that can silently turn a feature Off without anyone noticing.

## 11. Testing: Three Levels That Should Not Be Merged

### 11.1. Unit testing branching logic

You do not need to call Azure to test business logic. You can mock `FeatureManager` and supply fake `CheckoutSettings`:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.azure.spring.cloud.feature.management.FeatureManager;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class CheckoutFlowSelectorTest {
    @Test
    void offUsesOldFlow() {
        FeatureManager flags = mock(FeatureManager.class);
        when(flags.isEnabled("NewCheckout")).thenReturn(false);

        CheckoutSettings settings =
                new CheckoutSettings(Duration.ofSeconds(3), 3);
        CheckoutFlowSelector selector =
                new CheckoutFlowSelector(flags, settings);

        assertThat(selector.selectFlow()).isEqualTo("checkout-v1");
        assertThat(selector.gatewayTimeoutMillis()).isEqualTo(3000);
    }

    @Test
    void onUsesNewFlow() {
        FeatureManager flags = mock(FeatureManager.class);
        when(flags.isEnabled("NewCheckout")).thenReturn(true);

        CheckoutFlowSelector selector = new CheckoutFlowSelector(
                flags, new CheckoutSettings(Duration.ofSeconds(3), 3));

        assertThat(selector.selectFlow()).isEqualTo("checkout-v2");
    }
}
~~~

These tests verify **branching logic**; they do not prove Azure loaded the flag or that the evaluator performs targeting correctly. No `SpringApplication` startup is needed in unit tests like this.

### 11.2. Testing feature-management without Azure

In `src/test/resources/application-test.yml`, disable App Configuration and declare local flags:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        enabled: false

feature-management:
  feature_flags:
    - id: NewCheckout
      enabled: true
~~~

With `@SpringBootTest` and `@ActiveProfiles("test")`, you can inject `FeatureManager` and verify `isEnabled("NewCheckout")` returns true. This verifies **flag mapping into Feature Management**, but does not verify loading flags from Azure, RBAC, or refresh.

Note: if production `application.yml` contains `spring.config.import=azureAppConfiguration`, verify that `enabled=false` actually disables the provider before testing; never put real endpoints/credentials into test resources.

### 11.3. Integration testing with App Configuration

An integration test flow can use a dev store and an identity with restricted read permissions:

1. Create flag `NewCheckout` with (No Label), state Off; create the timeout key-value.
2. Start the app with `feature-flags.enabled=true`, verify `isEnabled` returns false.
3. Enable the flag and **restart the app**, verify true; confirm the timeout remains unchanged.
4. Create a flag with different `prod`/`dev` states and verify `feature-flags.selects`.
5. Enable monitoring/refresh; toggle the flag, observe timing and how instances update.
6. Test a missing/broken filter and verify fail-fast behavior; never use production secrets in tests.
7. If implementing audience-based rollout, verify the same user is consistently handled within a workflow.

Do not log tokens, connection strings, the entire `Environment`, or unnecessary user identifiers into test outputs.

## 12. Operational Lifecycle: Create, Roll Out, Clean Up

Feature flags create **technical debt** if left unmanaged. Each flag should track minimal metadata:

| Governance Field | Example |
| --- | --- |
| Stable name | `NewCheckout` |
| Owner | Payments Team |
| Reason | Canary checkout v2 |
| Target state | After release, v2 becomes the default |
| Expiration | Once agreed operational observability thresholds are met |
| Rollback method | Switch Off to return to v1 while still supported |
| Check metrics | Error rate, latency, checkout revenue/completion |
| Cleanup plan | Remove v1 branch and flag once no longer needed |

A suggested lifecycle:

~~~mermaid
flowchart LR
    A["Create flag Off"] --> B["Enable in dev"]
    B --> C["Test in staging"]
    C --> D["Canary in prod"]
    D --> E{"Metrics stable?"}
    E -->|Yes| F["Expand rollout"]
    E -->|No| G["Switch Off, investigate"]
    G --> C
    F --> H["Lock in main branch"]
    H --> I["Remove old code and flag"]
~~~

**Choosing flag types by purpose:**

- **Release flag:** used to launch features; typically removed once rollout completes.
- **Experiment flag:** defines test cohorts and measures outcomes; requires consistent group assignment and appropriate statistics.
- **Operational kill switch:** used to shed load or quickly disable risky functionality; requires accurate health monitoring and a fallback path.
- **Permission/entitlement:** should not be just a feature flag; must have server-side authorization/entitlement checks and an authoritative permission source.

Do not overuse feature flags for almost every configuration value: it multiplies code branches, makes testing all combinations difficult, and leaves dead code paths after release.

## 13. Common Pitfalls When Integrating Spring Cloud Azure

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| Timeout from Azure loads, flag is always false | `feature-flags.enabled` not enabled or flag created as wrong type | Check store config and **Feature Manager**, not just Configuration Explorer |
| Flag visible in portal but Spring does not see it | Wrong label/`feature-flags.selects` or endpoint | Check flag name, label, selectors, connected store |
| `FeatureManager` cannot be injected | Missing `spring-cloud-azure-feature-management` library | Check dependencies and BOM |
| Key `new.checkout=true` does not affect `isEnabled("NewCheckout")` | Regular key-values are not feature flag definitions | Create the flag in Feature Manager or use the local `feature-management` schema |
| After enabling flag only some instances see it | Refresh/cache checks happen at different times | Verify monitoring, interval, request traffic, and per-instance state |
| Rollout percentage fluctuates between two calls | Used random filter for a sticky-assignment use case | Use stable targeting/assignment and per-request consistent results |
| `@FeatureGate` returns 404 when Off | This is the default endpoint-blocking behavior | Design appropriate fallback/status; keep authorization in place |
| 403 error when reading store | Identity lacks `App Configuration Data Reader` | Check principal, RBAC scope, token, and network |
| Feature filter reported not found | Filter name in flag does not match registered bean | Check `@Component` and evaluator `fail-fast` |
| User can open feature but is not permitted to act | Flags control rollout, not permissions | Add Spring Security/business authorization checks |

## 14. Applied Exercise

You deploy a `recommendation-service` with a new recommendation algorithm feature. Requirements:

- Parameter `recommendation.timeout=PT2S` applies to both the old and new algorithms.
- Feature `NewRanker` is On for everyone in `dev`; in `prod` it starts Off.
- Once stable, open it only to a pilot user group in `prod`.
- When error spikes are detected, switch back to the old algorithm quickly.
- Only authorized users may view personalized recommendation data; rollout must never bypass authorization.

**Decide:**

1. Which data is created in Configuration Explorer and which in Feature Manager?
2. Which label filter is used for the `NewRanker` flag when switching between `dev` and `prod`?
3. In code, at what point should `NewRanker` be checked so a single request never mixes old and new algorithms?
4. If using a random `PercentageFilter`, can you guarantee a user always stays in the same group across multiple requests?
5. What kind of test is needed to prove the provider actually loads the flag from Azure rather than only mocking logic?
6. Once rollout finishes, how should the old code branch and the flag be handled?

**Guided answers:** (1) timeout is a key-value, `NewRanker` is a feature flag; (2) `feature-flags.selects[].label-filter` by environment; (3) at the algorithm selection boundary, keeping the decision consistent throughout the workflow; (4) no, stable targeting/assignment is needed; (5) integration tests with a dev store and real identity; (6) finalize the main branch, then delete the flag and obsolete branch after risk assessment.

## 15. Official References

- [Microsoft Learn – Quickstart: Add feature flags to a Spring Boot app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-feature-flag-spring-boot): dependencies, `feature-flags.enabled`, creating flags, and using `FeatureManager`.
- [Microsoft Learn – Tutorial: Use feature flags in a Spring Boot app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-feature-flags-spring-boot): checking flags, filters, controller actions, and `@FeatureGate`.
- [Microsoft Learn – Spring Cloud Azure App Configuration support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): key-values, feature flags, label filters, refresh, and fail-fast.
- [Microsoft Learn – Feature management overview](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-feature-management): feature release, switch, rollout, and experiment.
- [Microsoft Learn – Manage feature flags](https://learn.microsoft.com/en-us/azure/azure-app-configuration/manage-feature-flags): creating/editing flags on the Azure portal.
- [Microsoft Learn – Feature management library capabilities](https://learn.microsoft.com/en-us/azure/azure-app-configuration/feature-management-overview): comparing targeting, variants, and feature gates across platforms.
- [Microsoft Learn – Dynamic configuration for Spring Boot](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): refresh, request activity, and caching.

**Remember:** regular key-values provide **parameters for behavior**, feature flags provide **the decision of whether to execute behavior**, while access control and secrets require their own protective mechanisms. When integrating Spring Cloud Azure, choose the right API (`@ConfigurationProperties` or `FeatureManager`), filters, refresh behavior, and operational policies to release features under control.
