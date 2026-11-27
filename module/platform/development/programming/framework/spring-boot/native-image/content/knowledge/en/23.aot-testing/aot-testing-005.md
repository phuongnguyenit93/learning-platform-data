# Verifying Runtime Configuration Does Not Alter the Bean Set Unexpectedly

In a standard JVM Spring Boot application, conditions such as `@Profile` and `@ConditionalOnProperty` are evaluated when the ApplicationContext starts. Therefore, an environment variable or property can decide which beans are registered. When **Spring AOT** is enabled, this decision shifts to **build time**: Spring analyzes the Environment, evaluates conditions, and generates initialization code for the chosen set of beans.

As a consequence, an application AOT-processed with `payment.provider=card` still has the card provider bean at runtime, even when the deployment environment sets `payment.provider=bank`. Runtime property values can still be bound into `@ConfigurationProperties`, but they do not recreate fixed bean definitions on their own. If a service uses a runtime value to look up a bean that differs from the generated set, the application may fail on startup or take the wrong processing path.

This lesson belongs to the **AOT Testing** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module: compiling Spring Boot with Spring AOT into a GraalVM Native Image, verifying compatibility, and operating the executable. This lesson walks through identifying which properties affect bean topology, testing expected bean sets on JVM and AOT, detecting build/runtime configuration drift, and designing safe feature toggles.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why Spring AOT evaluates `@Conditional` at build time.
- Distinguish properties that control bean presence from properties that only control bean behavior.
- Test bean sets across configurations using `ApplicationContextRunner`.
- Write AOT integration tests to confirm generated bean definitions are accurate.
- Detect cases where runtime properties do not match the bean set fixed by AOT.
- Use startup validation to fail fast when deployment configuration is incompatible.
- Configure profiles/properties for Maven `process-aot` and Gradle `processAot`.
- Decide when separate native image variants are needed.

## 2. Why Is the Bean Set Fixed at Build Time?

Spring AOT prepares the ApplicationContext during the build process. The BeanFactory is analyzed and finalized; conditions affecting bean registration are evaluated against the Environment of that AOT run. Spring then generates bean definition registration code and related AOT resources.

When running an AOT application on the JVM (via system property `spring.aot.enabled=true`) or running a native executable, Spring uses the generated output. Decisions about bean topology are not re-evaluated like a standard JVM startup.

~~~mermaid
flowchart TD
    A["Build-time Classpath + Environment"] --> B["Spring AOT creates ApplicationContext"]
    B --> C["Evaluate @Profile / @Conditional"]
    C --> D["Generate bean definition set"]
    D --> E["AOT generated initializer"]
    E --> F["JVM AOT or Native Image runtime"]
    G["Deployment Environment"] --> H["Bind properties into existing beans"]
    G --> I["Does not add/remove fixed bean definitions"]
    F --> H
    F --> I
~~~

Spring Boot and Spring Framework state clearly:

- The classpath is determined at build time.
- `@Profile` and `@Conditional` conditions are evaluated at build time.
- Profiles selected during AOT are automatically applied when running AOT.
- Beans created during AOT will always be created when running the AOT application; you cannot disable such a bean by changing a runtime property.
- Properties that only change configuration values without affecting conditions can still be supplied at runtime.

Therefore, testing must verify the **expected bean set** and **runtime properties permitted to change** as two distinct aspects.

## 3. Classify Properties Before Writing Tests

Not every property needs to be fixed at build time. Identify which kind of decision a property affects:

| Property Type | Example | Can It Change at AOT Runtime? |
|---|---|---|
| Bean topology | `payment.provider` used in `@ConditionalOnProperty` | Does not re-evaluate condition; must match build-time choice |
| Active profile with configurations/conditions | `spring.profiles.active` selecting beans via `@Profile` | Profiles affecting the bean set must be chosen during AOT |
| Configuration values of existing beans | `payment.timeout`, `partner.base-url` | Yes, values are bound at runtime |
| Behavior of registered features | `reporting.enabled` read by a service to toggle processing | Yes, provided the bean remains stably registered |
| Classpath/dependencies | Adding a provider implementation or starter | No; dependencies must exist before AOT/native build |

A single property can be used in two places at once. For instance, `payment.provider` both selects a bean via `@ConditionalOnProperty` and binds into `PaymentSettings`. Then the property plays two roles:

1. Its value during AOT picks which implementation enters the bean set.
2. Its value at runtime declares which provider the application is configured to use.

If those two values differ, the mismatch should be detected and the application stopped early.

## 4. Example: Two Payment Providers Selected by Condition

Suppose the application supports card and bank transfer payments:

~~~java
public interface PaymentGateway {
    String providerId();
    PaymentResult pay(PaymentRequest request);
}
~~~

Two implementations:

~~~java
public class CardPaymentGateway implements PaymentGateway {
    @Override
    public String providerId() {
        return "card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.approved();
    }
}
~~~

~~~java
public class BankTransferGateway implements PaymentGateway {
    @Override
    public String providerId() {
        return "bank";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.pending();
    }
}
~~~

Configuration registering exactly one implementation based on a property:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentSettings.class)
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "payment",
            name = "provider",
            havingValue = "card")
    CardPaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "payment",
            name = "provider",
            havingValue = "bank")
    BankTransferGateway bankGateway() {
        return new BankTransferGateway();
    }
}
~~~

Bound properties:

~~~java
@ConfigurationProperties(prefix = "payment")
public record PaymentSettings(String provider) {
}
~~~

If AOT runs with `payment.provider=card`, the generated bean set contains `cardGateway`. When runtime uses the same value, the configuration is consistent.

If runtime switches to `payment.provider=bank`, Spring AOT does not replace `cardGateway` with `bankGateway`. `PaymentSettings` may receive `bank`, while the bean definitions still reflect the decision made at build time.

## 5. Detecting Configuration Drift Immediately on Startup

Do not wait until the first request to discover that the property-requested provider is missing from the context. You can add a consistency check that runs right after singleton beans are created:

~~~java
@Component
public class PaymentProviderConsistencyCheck
        implements SmartInitializingSingleton {

    private final PaymentSettings settings;
    private final List<PaymentGateway> gateways;

    public PaymentProviderConsistencyCheck(
            PaymentSettings settings,
            List<PaymentGateway> gateways) {
        this.settings = settings;
        this.gateways = gateways;
    }

    @Override
    public void afterSingletonsInstantiated() {
        boolean providerAvailable = this.gateways.stream()
                .anyMatch(gateway ->
                        gateway.providerId().equals(settings.provider()));

        if (!providerAvailable) {
            throw new IllegalStateException(
                    "payment.provider='%s' does not match the AOT bean set. "
                            .formatted(settings.provider())
                    + "Rebuild the AOT/native artifact with the intended provider.");
        }
    }
}
~~~

This check confirms that the runtime provider has a matching implementation in the ApplicationContext. If an artifact was AOT-built for card while runtime declares bank, the application stops during initialization instead of silently running with an incompatible bean set.

In real applications, the error message should name the property, current value, and expected artifact/build variant. Never include secrets or credentials in the message.

## 6. Testing the Condition Matrix on JVM with ApplicationContextRunner

`ApplicationContextRunner` is well-suited for quickly testing auto-configuration and conditions across multiple property sets. It spins up an isolated ApplicationContext per case, making it clear which beans must be present or absent.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            PaymentConfiguration.class,
                            PaymentProviderConsistencyCheck.class);

    @Test
    void cardProviderRegistersOnlyCardGateway() {
        this.contextRunner
                .withPropertyValues("payment.provider=card")
                .run(context -> {
                    assertThat(context).hasSingleBean(CardPaymentGateway.class);
                    assertThat(context).doesNotHaveBean(BankTransferGateway.class);
                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys("cardGateway");
                });
    }

    @Test
    void bankProviderRegistersOnlyBankGateway() {
        this.contextRunner
                .withPropertyValues("payment.provider=bank")
                .run(context -> {
                    assertThat(context).hasSingleBean(BankTransferGateway.class);
                    assertThat(context).doesNotHaveBean(CardPaymentGateway.class);
                    assertThat(context.getBeansOfType(PaymentGateway.class))
                            .containsOnlyKeys("bankGateway");
                });
    }
}
~~~

These two tests confirm that Spring conditions work as expected on the JVM. They are helpful for checking every supported configuration before running AOT.

**Limitation:** `ApplicationContextRunner` builds the context at runtime in the test. It does not prove the generated AOT initializer contains the right bean set. Therefore, add the AOT integration tests covered in the next section.

## 7. Verifying the Exact Bean Inventory

Do not check only that the desired bean exists. Verify that unwanted beans are also absent.

For a group of extension types, you can collect the inventory with:

~~~java
Set<String> gatewayBeanNames =
        Arrays.stream(context.getBeanNamesForType(PaymentGateway.class))
                .collect(Collectors.toUnmodifiableSet());
~~~

Then compare with the expected set:

~~~java
assertThat(gatewayBeanNames).containsExactlyInAnyOrder("cardGateway");
~~~

For the context using the bank provider:

~~~java
assertThat(gatewayBeanNames).containsExactlyInAnyOrder("bankGateway");
~~~

Restrict the inventory to the interface or business bean group under test. Comparing every bean name in the ApplicationContext is brittle across infrastructure beans, auto-configuration, and library version differences.

If the application intentionally supports multiple implementations of the same interface, express the expected set by provider ID or bean name, and clearly identify which bean is the fallback/default.

## 8. AOT Integration Tests with Spring TestContext

Spring Framework has AOT support for integration tests using the TestContext Framework. During the build, test contexts are discovered and each unique context is refreshed for AOT processing. Spring generates an `ApplicationContextInitializer` for the test context; when running in AOT mode, tests use the optimized context.

A test verifying the bean inventory:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "payment.provider=card")
class PaymentAotBeanSetTests {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void generatedContextContainsOnlyTheCardGateway() {
        assertThat(applicationContext.getBeansOfType(PaymentGateway.class))
                .containsOnlyKeys("cardGateway");
        assertThat(applicationContext.getBeansOfType(BankTransferGateway.class))
                .isEmpty();
    }
}
~~~

Properties in the test must match the Environment used to AOT-process the test context. If a test has different property sources, active profiles, or context customizers, those differences can produce a different AOT context or cause runtime to mismatch the generated context.

This test verifies the bean set in the AOT context generated for the card case. To test a runtime deployment override, add a smoke test running the AOT application with a different property and confirm the consistency check detects the mismatch.

## 9. Running Tests in AOT Mode and Native Image

There are two levels of verification:

1. **AOT runtime on the JVM:** verifies the application uses the generated initialization code.
2. **Native integration tests:** verify the test context and code compiled into a native executable.

### Running AOT Tests on the JVM

After AOT-processing the test context, run JVM tests with the system property `spring.aot.enabled=true`. Task or Surefire configuration depends on your project's build plugin/version.

Gradle example:

~~~bash
./gradlew processTestAot
./gradlew test -Dspring.aot.enabled=true
~~~

If the test task forks a JVM and does not forward system properties from the command line, configure it explicitly in the build script:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.aot.enabled", "true"
}
~~~

### Native Tests with Gradle

When the GraalVM Native Image and Spring Boot AOT plugins are configured, the `nativeTest` task uses outputs from `processAot` and `processTestAot`:

~~~bash
./gradlew nativeTest
~~~

### Native Tests with Maven

With a Spring Boot parent/profile configured for `nativeTest`:

~~~bash
./mvnw test -PnativeTest
~~~

This profile triggers `process-test-aot` and native test execution per Native Build Tools configuration. Check the plugins and profiles in your project before running the command; not every Maven project includes this configuration out of the box.

Native tests help confirm the generated test context and native runtime. However, still test the final application artifact with the real deployment Environment, because test contexts may use separate property sources.

## 10. Testing a Runtime Property Different from the Build-Time Property

A direct way to verify this is to build an artifact with the card provider and then run the AOT application with the bank provider.

### Step 1: AOT Build with the Card Provider

The Maven plugin allows configuring properties/profiles on the `process-aot` goal. Example plugin configuration:

~~~xml
<execution>
    <id>process-aot</id>
    <goals>
        <goal>process-aot</goal>
    </goals>
    <configuration>
        <systemPropertyVariables>
            <payment.provider>card</payment.provider>
        </systemPropertyVariables>
    </configuration>
</execution>
~~~

Then build with the configured native profile:

~~~bash
./mvnw -Pnative package
~~~

With Gradle, `ProcessAot` is a `JavaExec` task so you can configure system properties:

~~~groovy
import org.springframework.boot.gradle.tasks.aot.ProcessAot

tasks.withType(ProcessAot).configureEach {
    systemProperty "payment.provider", "card"
}
~~~

Build:

~~~bash
./gradlew nativeCompile
~~~

### Step 2: Run with the Bank Property

On Linux/macOS, with AOT JVM:

~~~bash
PAYMENT_PROVIDER=bank java -Dspring.aot.enabled=true -jar target/orders-service.jar
~~~

With the native executable:

~~~bash
PAYMENT_PROVIDER=bank ./target/orders-service
~~~

Because the bean set created at build time only has the card provider, the consistency check must fail reporting that `payment.provider=bank` does not match the AOT bean set.

### Step 3: Run with Matching Configuration

~~~bash
PAYMENT_PROVIDER=card ./target/orders-service
~~~

The application must start successfully and the inventory must contain only `cardGateway`.

This example is an **intentional negative test**: it proves that runtime properties do not silently alter the bean set. In production, build/runtime configuration must be managed consistently; do not deploy a card artifact with the bank property.

## 11. Testing Profiles and Profile-Specific Configuration

`@Profile` is implemented via a condition. Therefore, profiles affecting bean topology must be selected when AOT processing runs.

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("payment-card")
class CardPaymentConfiguration {
    @Bean
    CardPaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }
}
~~~

If the `payment-card` profile is enabled during AOT, it is applied when running AOT. Changing `spring.profiles.active` at runtime cannot remove beans already generated from that profile or add beans from another profile.

### Selecting Profiles During AOT with Maven

The `process-aot` goal supports a `profiles` configuration:

~~~xml
<execution>
    <id>process-aot</id>
    <goals>
        <goal>process-aot</goal>
    </goals>
    <configuration>
        <profiles>
            <profile>payment-card</profile>
        </profiles>
    </configuration>
</execution>
~~~

### Selecting Profiles During AOT with Gradle

~~~groovy
import org.springframework.boot.gradle.tasks.aot.ProcessAot

tasks.withType(ProcessAot).configureEach {
    args("--spring.profiles.active=payment-card")
}
~~~

Profile-specific files that only change ordinary properties without affecting conditions/bean sets can still be used as runtime configuration sources per Spring's property source rules. Distinguish configuration values from profiles/conditions that select beans.

## 12. Runtime Feature Toggles Should Not Control Bean Topology

If operators need to toggle a feature at runtime without rebuilding the native image, register the service/bean unconditionally and let a property control behavior.

Avoid:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "reporting",
        name = "enabled",
        havingValue = "true")
ReportExporter reportExporter() {
    return new ReportExporter();
}
~~~

If `reporting.enabled` changes after the AOT build, the exporter bean still reflects the build-time condition.

Instead, register the bean unconditionally:

~~~java
@ConfigurationProperties(prefix = "reporting")
public record ReportingSettings(boolean enabled) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportingSettings.class)
class ReportingConfiguration {

    @Bean
    ReportExporter reportExporter() {
        return new ReportExporter();
    }
}
~~~

The service reads the setting to decide whether to perform the work:

~~~java
@Service
public class ReportService {

    private final ReportingSettings settings;
    private final ReportExporter exporter;

    public ReportService(
            ReportingSettings settings,
            ReportExporter exporter) {
        this.settings = settings;
        this.exporter = exporter;
    }

    public ReportResult export(ReportRequest request) {
        if (!settings.enabled()) {
            throw new IllegalStateException("Reporting is disabled");
        }
        return exporter.export(request);
    }
}
~~~

The bean set always includes `ReportExporter`; the runtime property only changes behavior. If you need properties updated while the application is already running, use an appropriate refresh/configuration reload mechanism. Standard `@ConfigurationProperties` do not automatically reload external changes after binding.

## 13. Other Conditions That Also Need Testing

Do not look only for `@ConditionalOnProperty`. The following mechanisms can also alter the bean set:

- `@Profile`.
- `@ConditionalOnClass` and `@ConditionalOnMissingClass`.
- `@ConditionalOnBean` and `@ConditionalOnMissingBean`.
- `@ConditionalOnResource`.
- `@ConditionalOnExpression`.
- Custom `@Conditional`.
- Component scans/imports/registrars depending on Environment or classpath.

For example, `@ConditionalOnClass` depends on the build-time classpath. Adding a dependency into the runtime container will not give the native executable that class. Likewise, `@ConditionalOnResource` is evaluated during AOT; a new file mounted at runtime will not make Spring regenerate bean definitions.

Bean definitions registered via programmatic callbacks must also be reviewed. Spring AOT supports many extension points, but it cannot translate every arbitrary singleton addition or instance supplier into generated code. Check AOT documentation for the exact registry callback type you use.

## 14. Diagnosing Conditions in JVM Tests

When a condition does not behave as expected, inspect the Condition Evaluation Report. In Spring Boot, this report explains which auto-configurations/conditions matched or did not match and why.

You can enable debug logging when running JVM tests or the JVM application:

~~~properties
debug=true
~~~

Or pass the property when launching:

~~~bash
java -Ddebug=true -jar target/orders-service.jar
~~~

For tests using `ApplicationContextRunner`, you can verify whether the context has the expected beans and conditions; when needed, inspect `ConditionEvaluationReport` from the context's bean factory.

Note: the Condition Evaluation Report in a standard JVM run explains conditions evaluated during that run. When a context uses a generated AOT initializer, do not expect it to re-evaluate all conditions like a fresh JVM context. Cross-reference the build-time Environment and the generated bean inventory.

## 15. Organizing Build Variants When Bean Topologies Must Differ

If card and bank require completely different bean definitions, dependencies, or proxies, create two AOT/native variants:

~~~text
payment-card:
  AOT profile = payment-card
  bean set = CardPaymentGateway
  artifact = orders-card-native

payment-bank:
  AOT profile = payment-bank
  bean set = BankTransferGateway
  artifact = orders-bank-native
~~~

Each variant must have:

- Environment/profiles explicitly configured in the AOT process.
- Separate generated AOT sources/resources.
- Separate native image build.
- Corresponding bean inventory tests.
- Runtime configuration validation.

Do not reuse AOT outputs across variants with different bean topologies. With Maven/Gradle, separate output directories or build workspaces per variant to avoid accidentally picking up generated sources from a prior build.

If only endpoints, timeouts, API key references, or feature values differ without changing the bean set, there is no need to create multiple native variants; keep one stable bean topology and supply configuration values at runtime.

## 16. Recommended Test Matrix

| AOT Build Property | Runtime Property | Expected Outcome |
|---|---|---|
| `payment.provider=card` | `payment.provider=card` | Card bean present; startup succeeds |
| `payment.provider=card` | `payment.provider=bank` | Bean set remains card; consistency check fails fast |
| `payment.provider=bank` | `payment.provider=bank` | Bank bean present; startup succeeds |
| `payment.provider=bank` | `payment.provider=card` | Bean set remains bank; consistency check fails fast |
| `payment.provider=card` | `payment.timeout=5s` changed | Card bean still present; timeout bound to runtime value |

Beyond primary properties, also test:

- Active profiles.
- Property source precedence (environment, command line, config files, system properties).
- Optional dependencies affecting `@ConditionalOnClass`.
- Custom conditions.
- Nested configuration properties.
- Runtime flags not used in bean-creating conditions.

## 17. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| JVM tests pass but AOT context is missing a bean | AOT properties/profiles differ from JVM tests | Configure Environment consistently for AOT process and test context |
| Changing runtime property does not change beans | Condition was already evaluated at build time | Rebuild AOT variant or move toggle into runtime logic |
| Runtime settings say provider B but context only has provider A | Build/runtime configuration drift | Add startup consistency check and synchronize configuration |
| `@Profile` does not behave as expected | Profile affecting the bean set was not enabled during AOT | Select the profile in the AOT process |
| Dependency is present in container yet condition still does not match | Classpath was fixed at build time | Add dependency before AOT/native build |
| Native test differs from JVM test | Test context was AOT-processed or native runtime differs | Run `processTestAot`/`nativeTest` and inspect context configuration |
| Bean appears twice | Multiple configurations/auto-configurations registered it | Check conditions, bean names, and `@ConditionalOnMissingBean` |

## 18. Pre-Release Verification Workflow

~~~mermaid
flowchart TD
    A["Classify properties"] --> B["Select build-time profiles/conditions"]
    B --> C["Run JVM ApplicationContextRunner matrix"]
    C --> D["Run processAot / processTestAot"]
    D --> E["Verify AOT bean inventory"]
    E --> F["Build native executable"]
    F --> G["Run matching runtime config"]
    G --> H["Run mismatched runtime config"]
    H --> I{"Mismatch caught early?"}
    I -->|No| J["Fix validation/test"]
    J --> D
    I -->|Yes| K["Container testing and release"]
~~~

Checklist:

- [ ] List every property used in `@Conditional` or `@Profile`.
- [ ] Document values/profiles used for the AOT build.
- [ ] Separate bean-selecting properties from behavior-only properties.
- [ ] Test the condition matrix using `ApplicationContextRunner`.
- [ ] Assert both required-present and required-absent beans.
- [ ] Run AOT integration tests with the generated TestContext initializer.
- [ ] Verify the bean inventory of the AOT context.
- [ ] Add startup validation for runtime properties that can drift from bean topology.
- [ ] Run a negative test with an intentionally mismatched runtime property.
- [ ] Build the native image and run native tests.
- [ ] Verify deployment container config/environment.
- [ ] Create separate build variants if bean topologies must differ.

## 19. Self-Check Exercises

**Question 1.** Why is `@ConditionalOnProperty` evaluated differently between standard JVM and AOT?

**Hint:** Standard JVM evaluates it when the context starts; AOT evaluates it during the build process and generates the corresponding bean definitions.

**Question 2.** If AOT builds with `feature.enabled=true` and runtime changes it to `false`, is the bean removed?

**Hint:** No. Beans already generated in the AOT output remain registered; if a runtime toggle is needed, keep the bean registered and control behavior via properties.

**Question 3.** Why is it necessary to test both present and absent beans?

**Hint:** Asserting only the desired bean can miss another implementation also getting registered, causing ambiguous injection or picking the wrong provider.

**Question 4.** Is `ApplicationContextRunner` enough to prove the generated AOT context is correct?

**Hint:** No. It tests conditions in a JVM context created directly; you also need AOT integration tests using the generated initializer.

**Question 5.** If the build-time provider is card but the runtime provider is bank, how should it be handled?

**Hint:** The bean set remains card. A startup validator should detect the mismatch and stop the application; if bank is needed, build an AOT/native variant for bank.

**Question 6.** Which properties can change at runtime without altering the bean set?

**Hint:** Values such as endpoints, timeouts, request limits, or feature settings read by already registered beans, provided they do not participate in bean-creating conditions.

## 20. References

- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/how-to/aot.html): conditions evaluated at build time, profiles, and properties not affecting conditions.
- [Spring Boot — Ahead-of-Time Processing with Maven](https://docs.spring.io/spring-boot/maven-plugin/aot.html): `process-aot` goal, `profiles`, `systemPropertyVariables`, and `process-test-aot`.
- [Spring Boot — Ahead-of-Time Processing with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/aot.html): `processAot`, `ProcessAot`, `processTestAot`, and `nativeTest` tasks.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): constraints on bean definitions, classpath, and Environment in AOT.
- [Spring Framework — Ahead-of-Time Support for Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/aot.html): processing TestContext at build time and running AOT-optimized contexts in tests.

**Remember:** Spring AOT fixes the bean topology based on the build-time classpath and Environment. Runtime properties can still control values/behavior of existing beans, but they do not cause `@Conditional` to be re-evaluated. Test the condition matrix on the JVM, verify the bean inventory in the AOT context, add startup validation for configuration that could drift, and build separate native variants when bean sets genuinely need to differ.
