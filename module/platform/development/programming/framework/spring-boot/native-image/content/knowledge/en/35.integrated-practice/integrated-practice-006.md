# Changing Profiles and Properties to Observe the Build vs. Runtime Boundary

## 1. Why Must Profiles and Properties Be Verified When Using Spring AOT?

Spring Boot commonly uses profiles and properties to vary configuration per environment: toggling integrations, selecting endpoints, tuning timeouts, choosing datasources, or conditionally registering beans. On the JVM, Spring can construct the ApplicationContext at process startup and evaluate conditions against runtime configuration.

With Spring AOT and GraalVM Native Image, the ApplicationContext is analyzed before the executable is created. Decisions that affect context structure—such as which beans exist, which auto-configurations are enabled, or which components are scanned—may already be fixed in the generated AOT code. Consequently, changing a profile after building is not always equivalent to changing a profile when running a JAR on the JVM.

Conversely, many properties merely supply values to already-created beans, such as URLs, timeouts, pool sizes, or feature thresholds. These values can usually be changed at native runtime if the configuration and libraries support runtime binding.

In the **SPRING_BOOT_NATIVE_IMAGE** module, this practice helps distinguish the two property groups, run controlled experiments, and observe the difference between build-time AOT inputs and runtime configuration. The goal is to know which properties must be fixed when AOT runs and which can be changed without rebuilding the executable.

## 2. Two Property Groups to Distinguish

| Group | Impact | Examples |
|---|---|---|
| Structural/build-time | Alters the bean graph or metadata analyzed by AOT | Profiles enabling JPA vs. MongoDB config; properties controlling `@ConditionalOnProperty`; component scan/auto-configuration |
| Runtime/value | Changes values consumed by existing beans | API URL, timeout, log level, pool size, retry delay |
| Mixed/depends-on-usage | Can be structural or value depending on how code uses it | Feature flag, locale, serializer mode, cache enabled |

A property's name does not determine its group on its own. A property named `feature.enabled` can be a value property if it is only read inside a runtime method. If it is used in `@ConditionalOnProperty` to decide whether a bean is created, it is a structural input to AOT.

You must inspect how a property is used in code, configuration classes, and auto-configuration rather than just looking at its name in YAML.

## 3. Spring AOT Analyzes the ApplicationContext at Build Time

During AOT processing, Spring prepares the ApplicationContext based on:
- The application's main configuration.
- Classpath and dependency versions.
- Active profiles supplied to the AOT process.
- Property sources visible to the AOT process.
- Conditions and auto-configuration.
- Component scanning and imports.
- Bean definitions and runtime hints contributions.

The generated code reflects the analyzed context structure. When the native executable runs, Spring still reads runtime configuration and binds properties to applicable beans, but it cannot arbitrarily synthesize a completely different bean graph if the AOT output was not prepared for that structure.

This is why you must distinguish profiles activated during AOT from profiles set at runtime. How multiple profiles/variants are supported depends on the Spring Boot version and AOT workflow; verify against your project version's documentation.

## 4. Profiles Used to Select Environment Configuration

Example configuration:

```yaml
spring:
  profiles:
    active: native-prod
```

Separate files can be used:

```text
application.yml
application-native-prod.yml
application-test.yml
```

A profile can enable beans/configuration:

```java
@Configuration
@Profile("native-prod")
class NativeProductionConfiguration {
    // Beans belonging to native production configuration
}
```

If a profile determines which beans are created, it affects context structure. When AOT analyzes with the `native-prod` profile, the generated output is built for that configuration. Switching to a profile with a different bean graph at runtime may not behave as expected.

Profiles are not automatically build-time in every case. If a profile only alters values on an already-existing bean without changing context structure, it may be handled as runtime configuration. Inspect the actual conditions and bean graph.

## 5. @Profile and @ConditionalOnProperty Create Structural Decisions

Example:

```java
@Configuration
@Profile("payments")
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
```

Or:

```java
@Configuration
@ConditionalOnProperty(
        prefix = "search",
        name = "enabled",
        havingValue = "true")
class SearchConfiguration {

    @Bean
    SearchService searchService() {
        return new SearchService();
    }
}
```

In both cases, the property/profile determines whether the bean definition is registered. This is a structural decision that AOT must know.

If AOT runs with `search.enabled=false`, but runtime starts with `search.enabled=true`, do not expect the `SearchService` bean to appear if the generated context does not contain that configuration. A runtime property cannot regenerate bean definitions omitted during AOT.

## 6. Properties That Only Adjust Runtime Values

Example of an always-registered client whose endpoint changes per environment:

```java
@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout) {
}
```

Configuration:

```yaml
inventory:
  base-url: https://inventory.example.internal
  connect-timeout: 2s
  read-timeout: 5s
```

If the client bean is always created and values are simply bound onto the existing bean, changing the URL or timeout at runtime generally does not alter ApplicationContext structure.

Example environment overrides:

```bash
INVENTORY_BASE_URL=https://inventory.staging.internal
INVENTORY_CONNECT_TIMEOUT=3s
```

Environment variable names must follow Spring Boot's relaxed binding rules. Verify that the bean/client reads properties at runtime and that no condition uses the same property to decide bean registration.

## 7. Mixed Property: Feature Flags Can Belong to Either Group

A feature flag can be used in two different ways.

**Approach A — Structural:**

```java
@Bean
@ConditionalOnProperty(
        name = "invoice.pdf.enabled",
        havingValue = "true")
PdfInvoiceRenderer pdfInvoiceRenderer() {
    return new PdfInvoiceRenderer();
}
```

The value determines whether the bean exists. The value must be fixed when AOT runs, or supported build variants must be prepared.

**Approach B — Runtime behavior:**

```java
@Service
class InvoiceService {

    private final InvoiceProperties properties;

    InvoiceService(InvoiceProperties properties) {
        this.properties = properties;
    }

    byte[] render(Invoice invoice) {
        if (properties.pdfEnabled()) {
            return renderPdf(invoice);
        }
        return renderHtml(invoice);
    }
}
```

The bean always exists; the property only controls the execution branch. The value can be changed at runtime provided both code branches are included in the executable and the required dependencies/resources are packaged.

The same property can be used in both places. In that case, it has a structural impact and must be evaluated according to its structural impact.

## 8. Runtime Profiles Are Not a Mechanism to Add New Code to a Native Executable

Suppose an application has two configurations:

- `application-jpa.yml` enables Spring Data JPA.
- `application-mongo.yml` enables Spring Data MongoDB.

If the native executable was AOT-built with the JPA context, setting `SPRING_PROFILES_ACTIVE=mongo` at runtime does not bring Mongo repository beans and driver classes into the executable. Those classes may not be reachable, metadata may not have been generated, and the generated context may not contain the Mongo configuration.

To support multiple structures, use a strategy supported by your framework/version, such as:
- Creating separate build variants per profile.
- Designing a single context where required beans always exist and only runtime values change.
- Splitting configurations/applications into separate executables.
- Using official AOT/native support mechanisms if your version provides that capability.

Do not treat changing a profile environment variable as a substitute for a build variant.

## 9. Identify Which Properties the AOT Process Actually Sees

A common mistake is setting environment variables in a terminal while the build plugin runs AOT in a different process or an already-running daemon.

Verify:
- Whether the environment variables are present in the Maven/Gradle process.
- Whether the profile is passed to the exact AOT task/goal.
- Which property source has higher precedence.
- Whether a test profile accidentally overrides the production profile.
- Whether the Gradle daemon retains stale environment state.
- Whether the build cache reuses AOT output from a different configuration.

Setting a property in the shell does not guarantee the plugin receives it if the lifecycle/task forks a separate process. Inspect build logs and task configuration to confirm.

## 10. Experiment: Changing a Structural Property Before and After AOT

Create a configuration:

```java
@Configuration
@ConditionalOnProperty(
        prefix = "feature",
        name = "search",
        havingValue = "true")
class SearchFeatureConfiguration {

    @Bean
    SearchFeature searchFeature() {
        return new SearchFeature();
    }
}
```

Produce two variants:

**Build A:** AOT runs with `feature.search=false`.

**Build B:** AOT runs with `feature.search=true`.

Then run each executable with both runtime values:
- `feature.search=false`
- `feature.search=true`

Observe whether the bean exists and how the endpoint behaves. Expected result: each executable reflects the structural configuration analyzed when AOT ran. Runtime overrides cannot guarantee creating a bean that was excluded from the generated context.

Record:
- AOT profile/property inputs.
- Generated output/build ID.
- Runtime profile/property.
- Bean presence.
- Endpoint behavior.
- Native build and test results.

Do not share the same output directory/cache between Build A and Build B if there is a risk of mixing generated outputs.

## 11. Experiment: Changing Value Properties at Runtime

Create a bean that always exists:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration timeout) {
}
```

Build native with a context containing this bean. Then run the exact same executable twice with different endpoints:

```bash
SHIPPING_BASE_URL=https://shipping-a.example.internal \
SHIPPING_TIMEOUT=2s ./orders-service
```

```bash
SHIPPING_BASE_URL=https://shipping-b.example.internal \
SHIPPING_TIMEOUT=5s ./orders-service
```

If the application only binds values onto an existing bean, the same binary can use different runtime values. Use a mock server or sandbox to verify requests actually go to the configured endpoint.

Do not use production endpoints/credentials in experiments. Record the image/binary digest to prove both runs used the exact same executable.

## 12. Profiles for Tests vs. Profiles for Native Production

Tests often use profiles such as `test`, `integration`, or `testcontainers`. Native production may use its own profile. Avoid letting test profiles alter the context in unverified ways.

Examples:
- `test`: uses fake beans or an embedded/test database.
- `native-prod`: uses production adapters and security configuration.
- `staging`: only changes endpoints/credentials/observability values while bean structure stays unchanged.

If AOT/native executable tests use the test profile, passing does not automatically prove the production profile is compatible. Build and test against the production structure or create the corresponding variant.

Keep profile naming clear and record it in the build manifest. Do not let active profiles implicitly depend on a developer's machine.

## 13. Maven: Passing Profiles/Properties to the AOT/Native Build

How properties are passed depends on the Spring Boot and Native Build Tools plugin versions. Example running Maven with environment variables:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./mvnw -Pnative -DskipTests package
```

Some workflows use system properties or dedicated plugin configuration. What matters is that the variables reach the process executing Spring AOT. Check logs and generated output to confirm.

Do not assume `-Dspring.profiles.active=native-prod` always has the same precedence as environment variables or property files. Spring Boot property source ordering and how plugins fork processes can affect it. Use your project version's mechanism and test it.

## 14. Gradle: Passing Profiles/Properties to the AOT Task

Example:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./gradlew clean nativeCompile
```

If using the Gradle daemon, the daemon process may have been started with an earlier environment. When changing toolchain or environment inputs, check daemon/task configuration and caches. You may need to stop the daemon or run the build on a clean runner to eliminate stale environment state.

The `nativeCompile` task may depend on `processAot` depending on plugin configuration. Inspect the task graph rather than assuming. If the project configures a separate AOT task, pass structural properties to that exact task.

## 15. Separate Build Variants for Structural Configurations

If two distinct bean graphs are needed, create two native build variants:

| Variant | AOT inputs | Runtime purpose |
|---|---|---|
| `orders-native-search` | Search enabled | Deployments where search feature is enabled |
| `orders-native-core` | Search disabled | Minimal deployments without search |

Each variant requires:
- Dedicated AOT profiles/properties.
- Dedicated output directory.
- Dedicated artifact/image tag and digest.
- Dedicated native tests.
- A manifest recording structural inputs.
- Corresponding SBOM/provenance.

Do not reuse generated AOT output across variants if structural inputs differ. Also do not change one variant's runtime profile to simulate another variant.

## 16. Property Precedence and Configuration Sources

Spring Boot has multiple property sources: config data, environment variables, system properties, command-line arguments, and others. The final value depends on precedence.

When investigating a mismatch, record:
- Canonical property key.
- Providing source.
- Redacted value.
- Process receiving the property.
- Time of reading/binding.
- Whether the property is used in a condition or only in bean logic.

Actuator `env`/`configprops` endpoints can aid diagnostics, but they are highly sensitive. Expose them only in internal environments, restrict access, and redact secrets. Do not enable environment endpoints publicly in production.

## 17. Properties Read Once vs. Properties Read Dynamically

Not every value property automatically updates when a configuration file changes. For example, `@ConfigurationProperties` is typically bound when the bean is created; modifying a config file after startup does not mean the bean automatically refreshes.

Distinguish:
- Values bound when the ApplicationContext starts.
- Values read directly from `Environment` when a method executes.
- Beans refreshed by Spring Cloud/config mechanisms if the application supports them.
- Properties resolved at AOT/build time.

Native Image does not automatically turn static properties into dynamic configuration. If runtime refresh is needed, use a designed refresh/configuration mechanism and verify native support. Do not expect replacing a mounted file to update an already-bound object without a refresh mechanism.

## 18. AOT Caches and Outputs Must Be Isolated by Structural Inputs

If AOT output is cached, the cache key must reflect every input affecting the context:
- Commit/source revision.
- Dependency graph.
- Spring Boot/plugin versions.
- Active profiles of the AOT process.
- Structural properties.
- Generated sources/resources.
- RuntimeHints/metadata.
- OS/toolchain if output is platform-dependent.

If the cache key relies only on the commit and omits profiles/properties, output from a previous build variant may be wrongly reused. This causes hard-to-explain behavior or non-reproducible builds.

Use separate output directories per variant and save manifests. When suspecting cache issues, run a clean build on a clean runner to compare.

## 19. Diagnosing Profile/Property Mismatch Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Bean missing despite runtime property enabled | AOT evaluated condition as false | Rebuild with the right structural input |
| Bean present despite runtime property disabled | Bean was already created in the AOT context | Move condition into runtime logic if toggling is needed |
| JVM runs profile, native does not | Profile alters the bean graph after AOT | Create a build variant or compatible context |
| Runtime URL does not change | Bean/property bound from another source or precedence | Inspect Environment/property sources |
| AOT outputs mixed across jobs | Cache/output directory not separated by variant | Separate cache keys and output paths |
| Native test passes, production fails | Test profile/context differs from production | Test the structural production configuration |
| Config file changed but behavior unchanged | Bean does not refresh after startup | Use a refresh mechanism or restart |

## 20. Integrated Practice: Two Profiles, One Binary or Two Binaries?

**Context:** An Order API has an optional search feature. When search is enabled, the application must register `SearchRepository` and `SearchService`; the inventory endpoint only changes its URL/timeout per environment.

**Step 1 — Classify properties.** Identify that `search.enabled` is used in `@ConditionalOnProperty`; `inventory.base-url` and `inventory.timeout` are only bound to a client bean.

**Step 2 — Run the JVM baseline.** Start with search enabled/disabled and inventory endpoint A/B; record bean presence and request destination.

**Step 3 — Build the search-off AOT variant.** Run AOT with `search.enabled=false`, saving generated output and manifest.

**Step 4 — Build the search-on AOT variant.** Run AOT with `search.enabled=true` in a separate output directory.

**Step 5 — Build native executables.** Produce the two binaries or workflow variants per structural configuration, recording digests.

**Step 6 — Test runtime overrides.** For each binary, change the inventory URL/timeout without rebuilding; confirm the client uses the new values.

**Step 7 — Attempt changing the search flag after build.** Set the opposite value to the AOT input and observe bean/endpoint behavior. Document the limitation of changing context structure post-build.

**Step 8 — Verify tests and cache.** Run native integration tests for each variant and verify cache keys include structural inputs.

**Step 9 — Choose the design.** Choose a single binary if the feature is purely runtime behavior; use build variants if the bean graphs differ.

Completion criteria: each property is classified by usage; AOT inputs are explicitly recorded; runtime values change properly on the same binary; structural changes are built/tested as appropriate variants; caches and manifests never mix configurations.

## 21. Conclusion

The key boundary in Spring Boot Native Image is distinguishing which properties change ApplicationContext structure when Spring AOT runs from which properties merely supply values to already-created beans. Profiles, `@Profile`, and `@ConditionalOnProperty` commonly make structural decisions; URLs, timeouts, and many operational values can change at runtime. However, actual usage in code is the deciding factor.

Classify properties by impact, pass the right structural inputs into the AOT process, isolate outputs/caches per build variant, and record manifests. Verify by building two AOT variants, running the same executable with different runtime values, and attempting to change a structural flag after build. If the bean graph must change, create a tested build variant; if only values must change, design beans to always exist and bind runtime configuration.
