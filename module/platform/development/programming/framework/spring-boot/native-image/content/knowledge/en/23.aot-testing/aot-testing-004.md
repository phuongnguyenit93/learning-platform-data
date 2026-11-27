# Testing the ApplicationContext After Fixing Profiles and Build Conditions

## 1. Why Must Profiles and Conditions Be Fixed Before AOT Testing?

Spring Boot builds an ApplicationContext based on configuration classes, component scanning, auto-configuration, active profiles, property sources, and conditions such as `@ConditionalOnProperty`, `@ConditionalOnClass`, and `@ConditionalOnBean`. These inputs determine which beans are registered and which dependencies are wired.

In a standard JVM application, each process startup can load different profiles and properties to create the corresponding context. With **Spring AOT and GraalVM Native Image**, Spring analyzes an ApplicationContext at build time and generates initialization code based on the selected structure. The native executable is produced from that result. If a profile or structural property changes after the build, the application cannot implicitly recreate beans that were excluded from the AOT structure.

Therefore, before testing AOT you must clearly fix:

- The profile used to analyze the ApplicationContext.
- Properties participating in bean registration conditions.
- Classpath/dependencies and class/resource conditions.
- The build-time configuration sources that AOT actually receives.
- Expectations for which beans must be present and which beans must be absent.

This lesson guides building reproducible ApplicationContext tests, verifying the bean graph per profile/condition, and then cross-checking against the AOT-generated context and native executable in the **SPRING_BOOT_NATIVE_IMAGE** module.

## 2. Structural Configuration vs. Runtime Values

Not every property needs to be fixed at build time. Classify properties by how they are used.

| Property Type | Example | Impact |
|---|---|---|
| Structural/build-time | `spring.profiles.active` when profiles select configuration classes | Can change the set of beans analyzed by AOT |
| Structural/build-time | `payment.provider` used in `@ConditionalOnProperty` | Determines which implementation is registered |
| Structural/build-time | Classpath/dependency with or without a library | Affects conditions such as `@ConditionalOnClass` |
| Runtime value | API URL injected into a bean that always exists | Changes the endpoint value, does not change the bean graph |
| Runtime value | Timeout/limit read inside a service | Changes business behavior within existing code |
| Runtime value | Token/secret supplied at runtime | Provides credentials for an already existing bean |

For example, `feature.enabled` read only inside an `if` branch of an already registered service can be a runtime value. That same property, if used in `@ConditionalOnProperty` to create or omit a bean, is a structural input.

Misclassification leads to meaningless tests: testing on the JVM with different properties from AOT can produce a different bean graph and cause you to wrongly conclude that native is broken.

## 3. Define a Build Contract Before Writing Tests

Create a build contract configuration that can be recorded in CI:

| Input | Example Value | Source to Control |
|---|---|---|
| Spring profile | `native-prod` | Environment/arguments of the AOT process |
| Payment provider | `stripe` | Property evaluated by AOT |
| Search integration | Search client dependency present | Runtime classpath |
| Metrics bean | `metrics.enabled=true` | Structural property if a condition registers the bean |
| Inventory URL | `https://inventory.internal` | Runtime config if only an injected value |
| Default locale | `vi-VN` | Runtime config if the application allows changing it |
| GraalVM/JDK | Pinned version | CI toolchain |
| Spring Boot plugin | Pinned version | Build configuration |

The values above are examples only. Each project must identify its exact properties and profiles. Record both the property source and how it is passed into the AOT process; a variable present in the shell is not guaranteed to be forwarded by the plugin to the JVM executing AOT.

## 4. Designing Configurations with Explicit Profiles

Suppose an application has different payment adapters per profile:

```java
@Configuration(proxyBeanMethods = false)
@Profile("native-prod")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("local")
class LocalPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new MockPaymentGateway();
    }
}
```

The two profiles create different bean graphs. If AOT runs with `native-prod`, the generated context reflects the production configuration. You should not build native with the `local` profile, then merely set `SPRING_PROFILES_ACTIVE=native-prod` in the container and expect production configuration to appear on its own.

If you need a single native executable to run across multiple environments, design a stable set of beans and turn environment selection into a runtime value. If the bean structure truly differs, build separate artifacts per structural profile.

## 5. Condition Properties Must Be Fixed

Example:

```java
@Configuration(proxyBeanMethods = false)
class SearchConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "search",
            name = "enabled",
            havingValue = "true"
    )
    SearchClient searchClient() {
        return new SearchClient();
    }
}
```

When `search.enabled=true`, the `SearchClient` bean is registered; when false or missing according to the annotation's semantics, the bean may not exist.

If the condition is evaluated during AOT, the structural value must be passed to the AOT process itself. Context tests should assert both the match and non-match cases on the JVM; then run AOT with the selected release variant and confirm that the native context contains the expected bean.

Do not use a test that only asserts the application context "refreshed" as proof that conditions are right. A context can start successfully even when a critical integration bean is missing.

## 6. Testing Active Profiles with Spring Boot Tests

You can create a test context with a fixed profile using `@ActiveProfiles`:

```java
@SpringBootTest
@ActiveProfiles("native-prod")
class ProductionContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersProductionGateway() {
        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(StripePaymentGateway.class);
    }
}
```

This test verifies that the ApplicationContext on the JVM is created with the `native-prod` profile. It does not by itself prove that the Spring AOT build used the same profile. You must ensure the build pipeline passes the corresponding profile to the AOT process and inspect outputs/logs.

If a test uses `@SpringBootTest(properties=...)` together with `@ActiveProfiles`, clearly document which properties are test overrides and which are structural inputs of the release artifact. Avoid letting test overrides mask the CI configuration.

## 7. Testing Condition Properties with ApplicationContextRunner

For auto-configuration or small configuration classes, `ApplicationContextRunner` helps test conditions in isolation:

```java
class SearchConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(SearchConfiguration.class);

    @Test
    void createsSearchClientWhenEnabled() {
        runner.withPropertyValues("search.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(SearchClient.class);
                });
    }

    @Test
    void omitsSearchClientWhenDisabled() {
        runner.withPropertyValues("search.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(SearchClient.class);
                });
    }
}
```

The runner creates a separate context for each case, helping verify condition logic. For configurations with many dependencies, profiles, component scanning, or auto-configuration, add integration tests on the full ApplicationContext to verify interactions between beans.

`ApplicationContextRunner` tests do not run Spring AOT. They are a JVM condition-verification layer before moving to AOT validation.

## 8. Asserting Both Present and Absent Beans

A useful test needs to confirm both sides of the bean graph:

- Required beans must be present.
- Beans disallowed in the current profile/condition must be absent.
- Exactly one bean exists for critical interfaces.
- The injected dependency is the expected implementation.
- Beans are not duplicated because multiple configuration classes matched.

Example:

```java
assertThat(context).hasSingleBean(PaymentGateway.class);
assertThat(context).hasBean("stripePaymentGateway");
assertThat(context).doesNotHaveBean("mockPaymentGateway");
```

Bean names in assertions must match actual naming conventions, or use appropriate type assertions. With multiple implementations, verify qualifier/primary selection and bean injection at the consumer, not just individual beans in isolation.

Asserting absent beans matters because an overly broad configuration can accidentally instantiate both mock and production clients, leading to ambiguity or the risk of calling the wrong system.

## 9. Testing the Dependency Graph and Bean Wiring

After confirming bean registration, verify that services consume the expected implementation:

```java
@SpringBootTest
@ActiveProfiles("native-prod")
class PaymentServiceWiringTest {

    @Autowired
    PaymentService paymentService;

    @Autowired
    ApplicationContext context;

    @Test
    void usesProductionGateway() {
        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(StripePaymentGateway.class);

        assertThat(paymentService).isNotNull();
    }
}
```

If a service receives its dependency via constructor, you can check the bean implementation directly or use behavioral tests to verify calls reach the expected gateway. Avoid asserting only that an object is non-null when the goal is to verify wiring.

For beans with lifecycles such as schedulers, datasources, or message listeners, tests must avoid triggering real side effects. Use test doubles or sandbox configurations so ApplicationContext tests do not connect to production.

## 10. Verifying Profiles/Properties Actually Reach the Spring AOT Step

This is a frequently overlooked point. `@ActiveProfiles` in a test only controls the test context. It does not automatically pass profiles into the Maven/Gradle AOT process.

Check:

1. Which build task/goal executes Spring AOT.
2. Where that JVM process receives active profiles from.
3. Whether the plugin forwards system properties/environment variables.
4. Whether profile-specific config data is loaded during the AOT phase.
5. Whether condition reports/logs show the properties having the expected values.
6. Which context structure the generated AOT output corresponds to.

You can use temporary logging or a safe condition/configuration diagnostic to log active profile names and feature flags (never log secrets). Once verified, remove unnecessary diagnostic logs.

Do not look solely at the outer command line. A plugin may fork a separate process or use its own AOT configuration; confirm that properties are present in the exact JVM processing the context.

## 11. Running AOT Processing After Fixing Structural Inputs

The build workflow should run AOT with the selected profiles and conditions. Illustrative Gradle example:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./gradlew processAot
```

Illustrative Maven example:

```bash
SPRING_PROFILES_ACTIVE=native-prod \
SEARCH_ENABLED=true \
./mvnw -Pnative spring-boot:process-aot
```

This illustrates the intent of passing the environment; exact tasks/goals and how plugins accept properties depend on the Spring Boot version and project configuration. Confirm that the task exists and logs show the AOT process received these properties.

Some projects use Maven profiles or Gradle project properties to configure plugins, but a project property does not automatically equate to a Spring Environment property. Read your existing plugin configuration and use the mechanism supported by that version.

## 12. Cross-Checking the Generated Context Against Expectations

After AOT processing, inspect generated sources/resources at the output location determined by your build tool and plugin version. Do not edit generated files directly; they are build artifacts and will be regenerated.

Questions to verify:

- Which configuration classes were processed?
- Does the bean initialization code use the expected implementations?
- Are conditional beans present/absent as expected?
- Have the relevant proxies/hints been collected?
- Do structural profiles/properties match the build contract?
- Did the build emit warnings about beans or dynamic accesses?

Generated output can vary across Spring Boot versions, so do not write tests tightly coupled to internal file names unless the framework guarantees that API. Use logs, public testing hooks, and executable behavior as primary evidence.

## 13. Distinguishing JVM Context Tests from AOT-Generated Contexts

| Test | Context Checked | Evidence |
|---|---|---|
| `@SpringBootTest` | Context initialized on JVM per test profiles/properties | JVM configuration and wiring are correct |
| `ApplicationContextRunner` | Small context per condition/property test | Condition logic is correct |
| Spring AOT processing | Context analyzed during the build phase | AOT can generate code for the selected structural inputs |
| AOT-generated context test if project supports it | Context initialized via generated initializer | Generated initialization works in test setup |
| Native executable test | Actual context inside the native process | Binary initializes and wires properly at runtime |

Do not call every `@SpringBootTest` an AOT test. It normally runs on the JVM. To confirm native behavior, you must run a plugin-supported native test mode or launch the real native executable.

Some Spring Boot versions include test support for using AOT-generated initializers in JVM tests. How to enable it and the scope of support depend on the version; if used, verify that the test actually loads the generated initializer rather than creating a standard context.

## 14. Verifying Bean Conditions in the Native Executable

After building native with fixed profiles/conditions, run the executable and verify bean behavior via an endpoint or test probe. For example, an internal endpoint dedicated to integration tests can return the name of the implementation currently in use; never expose sensitive configuration details on a public API.

Better yet, invoke real business flows:

- Send a payment request and verify it goes to the expected sandbox gateway.
- Call the search endpoint and confirm the search bean is used.
- Check that a disabled feature does not initialize integrations or trigger outbound calls.
- Verify profiles do not instantiate mock implementations in a production artifact.

If you do not want diagnostic endpoints, use a test harness or structured logs in the test environment. Avoid relying on reflection to list every bean in native runtime solely to inspect the context if the application has no metadata for that operation.

## 15. Multiple Profiles: Multiple Artifacts or One Artifact?

If profiles change the bean structure, there are two strategies:

| Strategy | Implementation | When Suitable |
|---|---|---|
| Separate artifact per profile | Run AOT/native build for each structural profile | Distinct bean sets, strict isolation required |
| One stable bean graph | Register required implementations, select using runtime values | Need a single binary across multiple environments |

For example, if `local` uses a mock datasource and `production` uses a cloud datasource via different configuration classes, an AOT build analyzing only one profile will not automatically contain both structures. You can either build separate artifacts or design an adapter/factory so the required implementations are both in the context and a selector chooses at runtime.

A shared artifact may be larger or carry dependencies unnecessary in some environments. Weigh size, security, dependencies, and build cost.

## 16. Avoiding Skewed Conclusions from Test Profiles

Some common pitfalls:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Test passes but native lacks a bean | Test uses `@ActiveProfiles` different from AOT profile | Sync structural profiles and verify the AOT process |
| Native contains both mock and production beans | Conditions/profiles did not exclude the right implementation | Assert present/absent beans and review conditions |
| Property test passes but AOT differs | Test property applied only to the test context | Pass the property into the AOT process itself |
| Local passes, CI fails | Different environment/profile/plugin | Document build contract and pin toolchain |
| Runtime profile change does not alter beans | Bean graph was determined during AOT | Build another artifact or use a runtime selector |
| AOT build passes but startup fails | Bean wiring/lifecycle/runtime dependency error | Run native context startup and integration tests |
| Search bean is missing | `@ConditionalOnClass` did not match due to missing dependency | Check `runtimeClasspath` and dependency graph |

Do not try to fix the problem by adding a profile in the container if the issue lies in the generated bean graph. Re-evaluate structural inputs or design a stable bean graph.

## 17. Hands-On Exercise: Fixing the Production Profile and Verifying Context

**Scenario:** An Order API has two payment gateways. Local uses a mock, native production uses Stripe. Search integration is controlled by `search.enabled`.

**Step 1 — Declare configuration.** Create profile-specific configurations for the gateway and a condition property for the search client.

**Step 2 — Write JVM context tests.** Use `@ActiveProfiles("local")` and `@ActiveProfiles("native-prod")` to confirm the right gateway; use `ApplicationContextRunner` for `search.enabled=true/false`.

**Step 3 — Create a build contract.** Record profile `native-prod`, `search.enabled=true`, classpath/dependencies, and toolchain versions.

**Step 4 — Pass structural inputs into AOT.** Configure the Maven/Gradle process so Spring AOT receives the exact profile/property; verify via logs and output.

**Step 5 — Build the native executable.** Use the same structural inputs without changing profiles between AOT and native compilation.

**Step 6 — Run native context tests.** Start the executable, invoke payment/search scenarios, and verify the implementations used.

**Step 7 — Try changing a runtime value.** Change a URL or timeout without changing structural properties; confirm the same binary still uses the same bean graph and picks up the new runtime value.

**Step 8 — Try a structural variant.** Build another artifact with `search.enabled=false` if needed; confirm the search bean is absent in that variant.

Completion criteria: profiles/conditions are documented; JVM context tests confirm the bean graph; AOT processes structural inputs accurately; the native executable initializes and uses the right beans; runtime values can change within the designed boundaries.

## 18. Reproducibility Checklist in CI

Each native build should record the following information:

- Git commit and working tree status.
- JDK/GraalVM distribution and version.
- Spring Boot, Native Build Tools, and plugin versions.
- Active profiles during the AOT phase.
- Structural properties and how they were supplied.
- Dependency graph/classpath.
- Relevant build arguments and environment.
- Context assertion results on the JVM.
- AOT processing log/status.
- Native build and native runtime scenario results.
- Container image/base OS/architecture.
- Runtime properties allowed to change after build.

Do not put secrets into artifact logs. You can log property names and whether they were provided instead of their values. If the build needs credentials to resolve dependencies, use CI secrets and do not store them in generated sources or the native image.

## 19. Conclusion

ApplicationContext testing for Spring AOT must begin by fixing **profiles, structural properties, classpath, and build conditions**. JVM context tests confirm conditions and bean wiring for the chosen inputs; AOT processing must receive those exact inputs; the native executable must be run to verify the context and beans actually work.

Distinguish structural configuration from runtime values, assert both required-present and required-absent beans, document the build contract, and verify that profiles/properties reach the AOT process itself. If environments require different bean graphs, build separate artifacts or design a stable context with runtime selection. This practice makes native builds reproducible and avoids mistaking a passing JVM test for proof of correct AOT/native behavior.
