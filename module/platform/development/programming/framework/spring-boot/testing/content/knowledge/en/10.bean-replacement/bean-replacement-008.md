# `@Primary`, `@Qualifier`, and the Limits of Enabling Bean Definition Overriding in Spring Boot Tests

## Objective

In Spring Boot tests, we often want to replace a production dependency with a test version: a fixed clock, a fake gateway, an in-memory implementation, or a test-specific policy. Three distinct operations are frequently lumped together as "overriding a bean," yet they are **fundamentally different**:

1. **Adding a new bean of the same type** and using `@Primary` to prioritize it when Spring injects dependencies by type.
2. **Specifying the exact bean to receive** with `@Qualifier` at the injection point.
3. **Replacing a bean definition with the same name** when Spring allows overriding—a bean-registry mechanism with its own risks and limits.

After this lesson, you will be able to:

- Explain bean **name**, bean **type**, candidates, and how Spring selects dependencies to inject.
- Use `@Primary` and `@Qualifier` accurately without confusing them with deleting or overwriting a bean definition.
- Distinguish `NoUniqueBeanDefinitionException` from same-name bean definition conflicts.
- Understand why Spring Boot normally **disallows same-name bean definition overriding** by default, and why enabling `spring.main.allow-bean-definition-overriding=true` still fails to fix all DI errors.
- Write JUnit Jupiter/Spring Boot tests using `@TestConfiguration` + `@Import` to add test beans cleanly.
- Verify both business logic and the selected bean, instead of merely asserting "context started successfully."
- Recognize when to use test beans, version-appropriate `@MockBean`/`@MockitoBean`, profile/conditional config, or plain Java unit tests.

The scope of this lesson is **replacing or selecting beans in a test environment**, not a guide to enabling application-wide bean overriding.

## 1. Bean type, bean name, and injection candidates

Every bean in a Spring container has a **bean name** and a set of types used to look up or inject it. For example:

~~~java
@Bean
FeePolicy standardFeePolicy() {
    return amount -> amount >= 500 ? 0 : 30;
}
~~~

Spring registers a bean named `standardFeePolicy` (defaulting to the `@Bean` method name) with type `FeePolicy`. This is only a declaration snippet; `FeePolicy` is defined completely in the runnable example in Section 4.

Suppose a test also registers:

~~~java
@Bean
@Primary
FeePolicy promoFeePolicy() {
    return amount -> amount >= 500 ? 0 : 10;
}
~~~

Now there are **two differently named beans of the same type**:

~~~text
ApplicationContext
  FeePolicy candidates:
    - "standardFeePolicy" : FeePolicy, production
    - "promoFeePolicy"    : FeePolicy, test, @Primary
~~~

Both definitions can coexist. When a constructor accepts `FeePolicy` without a qualifier, Spring prefers the `@Primary` candidate if resolution fits and only one valid primary exists. When a constructor requests `@Qualifier("standardFeePolicy")`, it binds to the specific production bean regardless of whether the test bean is prioritized for unqualified injection.

That differs from a **name collision**:

~~~text
ApplicationContext
  "standardFeePolicy" : definition from ProductionConfig
  "standardFeePolicy" : definition from TestConfig     <-- name conflict
~~~

This is an issue of **two definitions sharing the same name key** in the bean registry, not two candidates sharing a type. `@Primary` does not resolve name collisions.

### Terms to distinguish

| Term | Meaning | Question to answer |
| --- | --- | --- |
| Bean definition | Blueprint describing how Spring creates a bean | Is another definition registered under the same name? |
| Bean name | Identifier used to look up a bean in the container | Do two definitions collide on the same name key? |
| Bean type | Interface/class type used to resolve dependencies | How many matching candidates exist? |
| `@Primary` | Prioritizes one candidate when injection lacks stricter selectors | Which bean is chosen by type? |
| `@Qualifier` | Narrows/specifies a candidate at an injection point | Which bean does this injection point want? |
| Definition overriding | Allows a definition with the same name to replace an existing one | Which definition wins last for that name? |

Mnemonic: **`@Primary` prioritizes, `@Qualifier` specifies, and bean definition overriding replaces a definition by name.** The three mechanisms are not interchangeable.

## 2. `@Primary`: prioritizes a bean without deleting the old bean

`@Primary` comes from `org.springframework.context.annotation.Primary`. It can be placed on a Spring-managed class or a `@Bean` method. When Spring looks for **one bean** for a by-type dependency and finds multiple candidates, the annotation marks the preferred candidate.

~~~java
@Configuration
class PricingConfig {

    @Bean
    FeePolicy standardFeePolicy() {
        return new StandardFeePolicy();
    }

    @Bean
    @Primary
    FeePolicy promotionalFeePolicy() {
        return new PromotionalFeePolicy();
    }
}
~~~

This snippet only illustrates semantics; compiling it requires defining the referenced classes. Both beans are registered under **different names**. If code accepts a plain `FeePolicy`:

~~~java
class CheckoutService {
    CheckoutService(FeePolicy policy) {
        // Spring will prioritize the @Primary bean when multiple candidates exist.
    }
}
~~~

then `promotionalFeePolicy` is preferred when resolving that constructor. Even so:

- `applicationContext.containsBean("standardFeePolicy")` still returns true.
- `applicationContext.getBean("standardFeePolicy")` still returns the old bean; `@Primary` **does not alter by-name lookups**.
- Injecting `List<FeePolicy>`, `Map<String, FeePolicy>`, or arrays still receives **both beans**; `@Primary` does not filter collections down to the primary bean.
- If only **one** matching bean exists, Spring does not need `@Primary`.
- If **two candidates are both marked primary** for one injection type without another disambiguator, ambiguity errors still occur; `@Primary` is not a 1-2-3 ranking system.
- Conditions like `@Qualifier`, scope, autowire-candidate metadata, and other selection rules still participate in final resolution. `@Primary` does not guarantee winning in every situation.

### When does `@Primary` make sense in tests?

A production app defines a `Clock.systemUTC()` bean, while a test needs `Clock.fixed(...)`. To preserve both definitions and verify the production bean still exists, you can import `fixedTestClock` marked `@Primary` and inject an unqualified `Clock` into the SUT. The SUT receives the test clock while the production clock remains accessible by name.

Similarly, a service reading `FeePolicy` via its constructor can receive a test policy in a specific test context. This is far clearer than enabling by-name overriding across the whole context just to swap one dependency.

**Caution:** if a production constructor already uses `@Qualifier("standardFeePolicy")`, adding `@Primary` to `promoFeePolicy` will **not** make that constructor drop its qualifier. Tests must check the actual injection point instead of assuming `@Primary` overrides every dependency.

## 3. `@Qualifier`: explicitly requesting a candidate at the injection site

`@Qualifier` comes from `org.springframework.beans.factory.annotation.Qualifier` and applies to fields, constructor parameters, method parameters, or suitable injection points.

~~~java
@Service
class AuditService {

    private final FeePolicy policy;

    AuditService(@Qualifier("standardFeePolicy") FeePolicy policy) {
        this.policy = policy;
    }
}
~~~

This is a syntax snippet; `FeePolicy` and the sample service are defined completely in Section 4. The annotation **neither creates a new bean** nor modifies existing bean definitions. It directs Spring to pick a candidate matching the qualifier constraint.

In the common form `@Qualifier("standardFeePolicy")`, the qualifier value matches a bean name. Fundamentally, a qualifier is a **candidate-filtering mechanism**; it can also be expressed through custom metadata/specialized annotations rather than always being a simple "bean name lookup." When multiple candidates satisfy the same qualifier, secondary rules such as `@Primary` and bean metadata still matter.

### Comparing three injection points

Suppose the context has `standardFeePolicy` and `promoFeePolicy` marked `@Primary`:

| Injection point | Expected bean | Why |
| --- | --- | --- |
| `CheckoutService(FeePolicy policy)` | `promoFeePolicy` | `@Primary` prioritizes the candidate for by-type injection |
| `AuditService(@Qualifier("standardFeePolicy") FeePolicy policy)` | `standardFeePolicy` | The injection point explicitly specifies the qualifier |
| `@Autowired Map<String, FeePolicy> policies` | Both beans | Collection injection gathers all matching candidates |

In tests, always verify **actual outcomes**: for amount 100, the production policy returns 30 and the test policy returns 10. When both coexist in one application context, the two services receiving different policies must exhibit distinct behavior matching the specification.

### Why not put qualifiers on every constructor?

Binding every service to concrete bean names reduces flexibility to swap implementations in experiments or environment-specific configurations. When an interface needs **one environment-selected implementation**, plain by-type constructor injection stays flexible. When a consumer **deliberately requires one specific provider** (such as a domestic payment channel, primary/replica data source, tenant, or audit policy), a qualifier clarifies the contract. Base the choice on design, not habit.

## 4. Runnable Java 17 + Spring Boot example: two differently named beans, one `@Primary`

### 4.1. Example goals

We test a Spring Boot application containing:

- `FeePolicy` — shipping-fee calculation interface.
- `standardFeePolicy` — production bean: orders of **500 or more are free**, otherwise fee **30**.
- `CheckoutService` — service injecting `FeePolicy` **without a qualifier**.
- `AuditFeeService` — service injecting `@Qualifier("standardFeePolicy")` to always use the standard policy.
- `promoFeePolicy` — **test-only** bean charging **10** when order is under 500; registered via `@TestConfiguration` and `@Import`, annotated `@Primary`.

Two test classes contrast the behaviors:

1. **Without importing test bean:** `CheckoutService` uses `standardFeePolicy` (fee 30).
2. **Importing test bean:** `CheckoutService` uses `promoFeePolicy` (fee 10), while `AuditFeeService` still uses `standardFeePolicy` (fee 30). Both beans remain in the context.

The example deliberately **avoids** bean definition overriding. It demonstrates a clearer, safer approach to test candidate selection.

### 4.2. Directory structure

~~~text
bean-selection-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DemoApplication.java
    │   ├── FeePolicy.java
    │   ├── CheckoutService.java
    │   └── AuditFeeService.java
    └── test/java/com/example/testing/
        ├── PromoFeeTestConfig.java
        ├── ProductionWiringTest.java
        └── ImportedPrimaryWiringTest.java
~~~

Gradle Wrapper scripts/files should be generated by Gradle or already present in the repository; do not hand-author binary `gradle-wrapper.jar` content. They are shown in the layout to clarify the Wrapper commands in Section 4.7.

**`settings.gradle`**

~~~groovy
rootProject.name = 'bean-selection-demo'
~~~

**`build.gradle`** — illustrative versions Spring Boot 3.3.5, Java 17; real projects should use their repository's BOM/Gradle versions:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` provides Boot context and DI; no web server is needed because this project has no HTTP API. `spring-boot-starter-test` supplies JUnit Jupiter, Spring TestContext, and test utilities. `useJUnitPlatform()` tells Gradle to run Jupiter tests. `testRuntimeOnly` adds the launcher per modern convention. The Java toolchain requires an available JDK 17 or configured provisioning.

**`src/main/java/com/example/testing/FeePolicy.java`**

~~~java
package com.example.testing;

@FunctionalInterface
public interface FeePolicy {
    int feeFor(int orderAmount);
}
~~~

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    public FeePolicy standardFeePolicy() {
        return orderAmount -> {
            if (orderAmount < 0) {
                throw new IllegalArgumentException(
                        "orderAmount must not be negative");
            }
            return orderAmount >= 500 ? 0 : 30;
        };
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Production bean named `standardFeePolicy`. For `orderAmount=100`, fee is 30; for `500`, fee is 0; negative values throw `IllegalArgumentException`.

**`src/main/java/com/example/testing/CheckoutService.java`**

~~~java
package com.example.testing;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public final class CheckoutService {

    private final FeePolicy feePolicy;

    public CheckoutService(FeePolicy feePolicy) {
        this.feePolicy = Objects.requireNonNull(feePolicy);
    }

    public int shippingFee(int orderAmount) {
        return feePolicy.feeFor(orderAmount);
    }
}
~~~

The constructor accepts **only type `FeePolicy`**, with no qualifier. Once the context holds two policies, Spring requires a candidate selection rule—here, `@Primary` from the test config.

**`src/main/java/com/example/testing/AuditFeeService.java`**

~~~java
package com.example.testing;

import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public final class AuditFeeService {

    private final FeePolicy standardPolicy;

    public AuditFeeService(
            @Qualifier("standardFeePolicy") FeePolicy standardPolicy) {
        this.standardPolicy = Objects.requireNonNull(standardPolicy);
    }

    public int referenceFee(int orderAmount) {
        return standardPolicy.feeFor(orderAmount);
    }
}
~~~

`AuditFeeService` intentionally requires the **standard policy** as an audit reference, so this dependency carries a qualifier. `@Primary` on the test policy will not switch it over to the promotional policy.

### 4.3. Test-only config: `@TestConfiguration` and `@Import`

**`src/test/java/com/example/testing/PromoFeeTestConfig.java`**

~~~java
package com.example.testing;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class PromoFeeTestConfig {

    @Bean
    @Primary
    public FeePolicy promoFeePolicy() {
        return orderAmount -> {
            if (orderAmount < 0) {
                throw new IllegalArgumentException(
                        "orderAmount must not be negative");
            }
            return orderAmount >= 500 ? 0 : 10;
        };
    }
}
~~~

`@TestConfiguration` is Spring Boot's annotation for test-only configuration. When defined as a **top-level class** in `src/test/java`, Boot's default component scan excludes it from production app contexts; tests needing it **import it explicitly**. `@Bean` registers a new bean named `promoFeePolicy`, and `@Primary` marks it preferred for by-type injection.

**Key point:** `promoFeePolicy` has a **different name** from `standardFeePolicy`, avoiding any bean-definition name collision. Both implement `FeePolicy`, and `@Primary` resolves bean selection for `CheckoutService`.

In projects with customized component scanning, scan rules may vary; keep test-only configurations in the test source set and import deliberately. Never move this class to `src/main/java` just to work around a test setup error.

### 4.4. Test 1 — production context, no test policy imported

**`src/test/java/com/example/testing/ProductionWiringTest.java`**

~~~java
package com.example.testing;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProductionWiringTest {

    @Autowired
    private CheckoutService checkout;

    @Autowired
    private AuditFeeService audit;

    @Autowired
    private Map<String, FeePolicy> policies;

    @Test
    void productionServicesUseStandardPolicy() {
        assertEquals(30, checkout.shippingFee(100));
        assertEquals(30, audit.referenceFee(100));
        assertEquals(0, checkout.shippingFee(500));
    }

    @Test
    void testPolicyIsNotPresentWithoutImport() {
        assertEquals(
                Set.of("standardFeePolicy"),
                policies.keySet());
    }
}
~~~

Without `@Import(PromoFeeTestConfig.class)`, the context loads only the production `standardFeePolicy` bean, giving Spring a single candidate for `CheckoutService`. The two `@Test` methods create **2 invocations** in this class.

### 4.5. Test 2 — importing the `@Primary` test policy

**`src/test/java/com/example/testing/ImportedPrimaryWiringTest.java`**

~~~java
package com.example.testing;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(PromoFeeTestConfig.class)
class ImportedPrimaryWiringTest {

    @Autowired
    private CheckoutService checkout;

    @Autowired
    private AuditFeeService audit;

    @Autowired
    private FeePolicy chosenByType;

    @Autowired
    @Qualifier("standardFeePolicy")
    private FeePolicy explicitlyStandard;

    @Autowired
    private Map<String, FeePolicy> policies;

    @Test
    void unqualifiedConsumerUsesTestPrimary() {
        assertEquals(10, checkout.shippingFee(100));
        assertEquals(0, checkout.shippingFee(500));
    }

    @Test
    void qualifiedConsumerKeepsProductionPolicy() {
        assertEquals(30, audit.referenceFee(100));
        assertEquals(0, audit.referenceFee(500));
    }

    @Test
    void bothNamedDefinitionsRemainRegistered() {
        assertEquals(
                Set.of("standardFeePolicy", "promoFeePolicy"),
                policies.keySet());

        assertEquals(
                30,
                policies.get("standardFeePolicy").feeFor(100));
        assertEquals(
                10,
                policies.get("promoFeePolicy").feeFor(100));
    }

    @Test
    void primaryAndQualifierSelectDifferentInstances() {
        assertSame(policies.get("promoFeePolicy"), chosenByType);
        assertSame(policies.get("standardFeePolicy"),
                explicitlyStandard);
    }

    @Test
    void bothPoliciesRejectNegativeAmounts() {
        assertThrows(IllegalArgumentException.class,
                () -> checkout.shippingFee(-1));

        assertThrows(IllegalArgumentException.class,
                () -> audit.referenceFee(-1));
    }
}
~~~

This is a real Spring Boot test exercising bean wiring and both `FeePolicy` implementations. There is no database, network, or mocking masking logic. Expected values `30`, `10`, and `0` come directly from the specification rather than calling the same implementation to compute expected results.

**What the test proves:**

- `CheckoutService` **has no qualifier**, so it receives the `@Primary` test policy.
- `AuditFeeService` carries qualifier `standardFeePolicy`, so it keeps receiving the production policy.
- `Map<String, FeePolicy>` holds **two entries**, proving `@Primary` did not delete the other bean.
- `chosenByType` points to the same instance as `promoFeePolicy`, and `explicitlyStandard` points to `standardFeePolicy` (default singleton `@Bean` scope).
- Both policies reject negative inputs, verifying boundary behavior rather than just bean names.

This class has **5 invocations**. Combined with the 2 invocations of `ProductionWiringTest`, the sample project runs **7 JUnit tests** across both classes.

### 4.6. Why don't the two test classes interfere with each other?

Spring TestContext **caches `ApplicationContext` instances** based on merged context configuration. `ImportedPrimaryWiringTest` has `@Import(PromoFeeTestConfig.class)`, whereas `ProductionWiringTest` omits it. Because their **configuration sets differ**, these two tests will not share a single context instance.

The test config is a top-level `@TestConfiguration` imported only where needed. There is no shared mutable state, no need for `@DirtiesContext`, and no test-order dependency. If a test config or singleton fake contains mutable state, reset fixtures explicitly or isolate tests; Spring's context cache does not isolate mutable state.

### 4.7. Running via Gradle Wrapper

From the root directory containing `settings.gradle` and the Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run only the imported test class:

~~~bash
./gradlew test --tests 'com.example.testing.ImportedPrimaryWiringTest'
~~~

Run only the production test class:

~~~bash
./gradlew test --tests 'com.example.testing.ProductionWiringTest'
~~~

With the exact example code above, **7 tests are expected to pass**. Because there is no `System.out.println`, **there is no fixed business stdout**. Gradle may print `BUILD SUCCESSFUL` on success, or reuse cached results with `UP-TO-DATE`/`FROM-CACHE` when applicable. Inspect actual test counts in the reports:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ProductionWiringTest.xml
    └── TEST-com.example.testing.ImportedPrimaryWiringTest.xml
~~~

To force re-execution for diagnostics, run `./gradlew test --rerun-tasks`. When setting up a new project without a Wrapper, bootstrap it from a compatible Gradle installation—e.g., `gradle wrapper --gradle-version 8.8 --distribution-type bin` for this demo. In real repositories, match the Gradle version chosen by the project. The Wrapper does not install a JDK; Java 17 must be configured appropriately.

## 5. When does `NoUniqueBeanDefinitionException` occur?

Suppose two beans share the same interface:

~~~java
@Bean
FeePolicy standardFeePolicy() { /* ... */ }

@Bean
FeePolicy promoFeePolicy() { /* ... */ }
~~~

Without `@Primary`, a qualifier, or another disambiguator, constructor `CheckoutService(FeePolicy feePolicy)` can fail with an error like:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
standardFeePolicy,promoFeePolicy
~~~

This illustrates **the general error pattern**, not a guaranteed verbatim stack trace across every Spring version. The problem: **two candidates by type**. Resolution depends on the contract:

1. Mark one implementation `@Primary` if it should be the default when multiple beans share a type.
2. Add `@Qualifier` at the injection point if the consumer requires a specific implementation.
3. Avoid registering both beans in the same context if only one should exist—for instance, separate via `@Profile`, conditional configuration, or narrowed imports.
4. If the consumer truly wants every implementation, change the injection signature to `List<FeePolicy>`/`Map<String, FeePolicy>` and define usage clearly.

**Do not try to solve this with `spring.main.allow-bean-definition-overriding=true`** when the beans have **two different names**. That overriding property governs **same-name** definition conflicts, not multiple same-type candidates.

### Subtle detail: parameter names and bean names

In certain situations, Spring uses injection-point names during resolution when matching metadata, qualifiers, or fallback rules apply. That can make a seemingly "unqualified" test pick a specific bean anyway. For clear, reliable tests, **never rely on coincidental parameter/field names** as a selection policy between implementations. Use `@Primary` or `@Qualifier` intentionally when multiple candidates exist and test actual behavior.

## 6. Same-name bean collisions and bean definition overriding

Now consider **two configurations registering the same name**:

~~~java
// Production config - illustrative snippet:
@Configuration
class ProductionGatewayConfig {

    @Bean("paymentGateway")
    PaymentGateway realGateway() {
        return new RemotePaymentGateway();
    }
}

// Test config - illustrative snippet:
@TestConfiguration
class TestGatewayConfig {

    @Bean("paymentGateway")
    PaymentGateway fakeGateway() {
        return new FakePaymentGateway();
    }
}
~~~

These snippets analyze the error; `PaymentGateway`, `RemotePaymentGateway`, and `FakePaymentGateway` are not defined in Section 4's runnable project. If both configs are loaded into one Boot context and **both define bean name `paymentGateway`**, that is a **bean definition name collision**, not two differently named beans sharing a type.

Spring Boot normally **disables same-name bean-definition overriding by default**. Under that collision, registration can fail with `BeanDefinitionOverrideException` or a related context initialization error; the exact message depends on registration timing/style and library version.

### What does `spring.main.allow-bean-definition-overriding=true` do?

In Spring Boot, the property:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

permits the bean factory to **let a later bean definition with the same name replace an earlier definition** in supported registration paths. It is a **container setting**, not an annotation making a test bean primary.

Enabling it might silence the name-conflict error. However:

- **It does not guarantee the test bean wins** merely because it lives in `src/test/java`; which definition survives depends on configuration processing/registration order. A test config can be overwritten in reverse if order assumptions fail.
- **It does not resolve two differently named beans of the same type.** `NoUniqueBeanDefinitionException` can still occur.
- **It does not automatically replace every reference to the production implementation.** Some dependencies use qualifiers, name bindings, factory methods, conditional configs, or separate lifecycles.
- **It does not prove the production application starts cleanly.** Tests may silently mask duplicate-name bugs that ought to be fixed in production.
- **It does not guarantee context startup succeeds:** missing beans, circular dependencies, property errors, constructor errors, or condition failures can still happen.
- **It can make tests fragile to scan/import ordering**, where refactoring or new imports silently change which definition wins last.

Therefore, **never enable overriding across the entire application or test suite just to "get Spring past startup."** It is a deliberate escape hatch for certain legacy systems, not a default pattern for test dependency replacement.

### When *might* same-name overriding be considered?

When architecture or compatibility truly mandates a fixed bean name that cannot be handled through profiles, conditional config, qualifiers, fake injection, or dedicated test bean overrides, a team might consider enabling overriding **scoped solely to the affected tests**, provided:

- Tests verify **the actual selected bean definition and behavior** after context load, not merely that the context boots.
- Bean configuration sources and import ordering are clearly understood and reviewable.
- Separate tests confirm the **production context still starts without masked collisions**.
- Documentation explains why a clearer mechanism could not be used and restricts scope minimally.

Otherwise, favor **a differently named bean + `@Primary`**, **`@Qualifier`**, profiles/conditional config, or dedicated test bean replacement support.

## 7. What is actually being "replaced"?

Ask yourself: "Is my goal to change **dependency selection**, or replace a **named bean definition**?"

| Goal | Typically appropriate technique | Keeps production bean in same context? |
| --- | --- | --- |
| By-type consumer receives test policy instead of production | `@Import` differently named test bean + `@Primary` | Yes |
| Only one specific consumer receives a fixed policy | `@Qualifier` at the injection point | Yes |
| Only the `test` profile uses a fake adapter | `@ActiveProfiles("test")` + matching `@Profile` | Depends on declarations/profiles |
| Only overriding existing config property values | `@TestPropertySource` or Boot test properties | Usually yes; no extra bean needed |
| Mocking a dependency by type/name in a Boot test | Test mock annotation **supported by your project version** | Defines test replacement via mock mechanism |
| Replacing a bean definition under the same name | Dedicated bean override; if forced, strictly scoped container overriding | Not necessarily, since the same-name definition gets replaced |
| Testing a standalone algorithm without Spring DI | `new` object with fake/`Clock.fixed` | Does not start a context |

**Observation:** a test can speak of "replacing a dependency" while still keeping the production bean alive. In the runnable example, `CheckoutService` receives `promoFeePolicy`, yet `standardFeePolicy` remains intact and `AuditFeeService` continues using it. That is **switching candidate selection** at an injection point, not overwriting the registry.

## 8. `@Profile` and `@ConditionalOnMissingBean` can be a better fit

### 8.1. Using `@Profile` for environment-specific implementations

When an application has implementations that must be **mutually exclusive by environment**, profile-based configuration is clearer than overriding:

~~~java
@Configuration
class GatewayConfiguration {

    @Bean
    @Profile("!test")
    PaymentGateway liveGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Profile("test")
    PaymentGateway fakeGateway() {
        return new InMemoryPaymentGateway();
    }
}
~~~

This is an illustrative snippet; real projects must supply the referenced types/implementations. Under `@ActiveProfiles("test")`, the test context skips registering `liveGateway` from this config, avoiding any need for `@Primary` or name overriding. Under non-`test` production profiles, the live bean is created.

However, **never slip test fake implementations casually into production artifacts**. In larger codebases, keep fakes under `src/test/java` and import test-only configs rather than putting fakes in `main`. Profiles do not replace clean boundary design or dedicated tests for production wiring.

### 8.2. Using conditional config for fallback beans overridden by the app

In Spring Boot, a fallback bean can be declared with `@ConditionalOnMissingBean` so it only registers when no matching candidate exists yet:

~~~java
@Configuration(proxyBeanMethods = false)
class DefaultGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultGateway() {
        return new RemotePaymentGateway();
    }
}
~~~

This snippet illustrates the "default if no implementation exists" pattern. When a consumer or test registers a `PaymentGateway` bean before the condition is evaluated, the fallback can **be skipped**, preventing two candidates. This pattern is especially common in auto-configuration.

**Key limitation:** `@ConditionalOnMissingBean` is not a command to "delete an already registered bean" and **depends on the evaluation order of bean definitions and conditions**. It is designed for auto-configuration and requires knowing configuration ordering; it will not automatically fix arbitrary bean name/type collisions. Never slap this annotation onto colliding beans expecting magic overrides.

### 8.3. With fixed `@Qualifier`, adding `@Primary` may not be enough

If the production constructor is written as:

~~~java
public PaymentService(
        @Qualifier("realGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

then importing a `@Primary` fake named `fakeGateway` **will not alter** the constructor's choice. If a test must plug a fake into this consumer, consider:

- Redesigning the consumer to inject by interface without hardcoding an implementation name when the contract allows.
- Using profiles or conditional config so the right candidate registers under the name/qualifier the consumer expects.
- Using your library version's test mock/bean replacement mechanism supporting name/qualifier targeting.
- Writing a direct constructor unit test `new PaymentService(fakeGateway)` if container wiring is not under test.

Never rely on same-name property overriding as a "quick fix" without checking the full bean resolution outcome.

## 9. Spring Boot 3.3, 3.4+, and test mock/replacement mechanisms

When you truly need a **mock dependency** rather than another real implementation, the specific annotation depends on your Spring Boot/Spring Framework version:

- In **Spring Boot 3.3.x** (like the runnable example), Spring Boot Test's `@MockBean` is a supported test mocking mechanism. It can add/replace beans in the test `ApplicationContext` per its annotation rules, unlike simply putting `@Primary` on another bean.
- In **Spring Framework 6.2+**, Spring Test offers native test bean override support, including `@MockitoBean` and `@TestBean` in supported contexts; newer Spring Boot releases integrate these mechanisms. Spring Boot 3.4 begins moving away from Boot's `@MockBean` toward the new mechanism, yet **never copy `@MockitoBean` into Boot 3.3.x**, as Boot 3.3's Spring Framework 6.1.x lacks that API.
- Dedicated bean override mechanisms carry specific rules around type/name targeting, replace-only vs. create-if-missing, factory methods, and context hierarchies. Read documentation for your **exact dependency version** to pick valid annotations and syntax.

This lesson omits `@MockBean`/`@MockitoBean` from its main program precisely to isolate **candidate selection, qualifiers, and bean-definition overriding**. When avoiding real external gateway logic, mock annotations often fit better than a `@Primary` fake; when testing a policy's own real logic, do not mock the policy under test.

### Avoid enabling overriding just in place of `@MockBean`

Test mock annotations manage lifecycle, target selection, and Spring TestContext integration. Setting `spring.main.allow-bean-definition-overriding=true` is a broad bean-registry toggle, **not equivalent** to a targeted override annotation. Decide based on what is being tested and which beans should be replaced.

## 10. Troubleshooting along two axes: name and type

When a context fails, first separate **duplicate bean name** from **multiple candidates of one type**:

| Symptom | Actual problem | Resolution |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` injecting `FeePolicy` | Multiple candidates of same type; none selected | `@Primary`, `@Qualifier`, profiles, conditional config, or narrower imports |
| `BeanDefinitionOverrideException` registering `paymentGateway` | Multiple definitions with the **same name** in registry; overriding disabled | Rename bean, avoid duplicate imports, or use targeted test replacement |
| `NoSuchBeanDefinitionException` | No matching candidate or mismatched qualifier | Check bean registration, annotations, profiles, imports, and qualifiers |
| Context loads, yet injection uses production policy | Test bean not imported, `@Primary` ineffective, or consumer uses qualifier | Assert candidate by name and output as in the example |
| Context loads with both real and fake policies | `@Primary` only steers selection without removing beans | May be intentional; otherwise separate via profiles/conditions/exact override |
| Ambiguity error persists despite `@Primary` | Multiple primaries or mismatched qualifiers/types | Check primary count within the candidate set and injection point |
| Overriding enabled, yet type error remains | Beans have different names; no name collision existed | Turn off the global toggle and fix candidate selection |
| Test bean unexpectedly appears in other tests | Top-level config scanned broadly or imported globally | Restrict `@TestConfiguration` and import scope |
| Tests pass while production fails at startup | Fake/test config masking broken production wiring | Maintain separate production context tests, like `ProductionWiringTest` |
| Runs pass individually, fail as a suite | Shared singleton state, context cache, or fixtures | Reset state, eliminate order dependency, use context cache deliberately |
| Test uses bean name, yet refactoring renames `@Bean` method | Default bean name changed too | Declare explicit name if it is a contract, or remove unnecessary qualifier |
| JUnit test fails to execute at all | Wrong runner/Gradle/test source set, unrelated to beans | Check `useJUnitPlatform()`, JUnit Jupiter imports, test tasks, and reports |

### Reading the root cause in stack traces

`Failed to load ApplicationContext` is merely the **outer wrapper**. Inspect the nested exception:

- `NoUniqueBeanDefinitionException` → Spring could not select **one candidate**.
- `BeanDefinitionOverrideException` → container rejects **duplicate definition names**.
- `NoSuchBeanDefinitionException` → no candidate matches type/qualifier.
- Exception in a bean constructor/factory → instantiation/config bug, not necessarily overriding.
- Property, external service, or database failure → test context may be importing too broadly or missing environment setup.

With Gradle, run `./gradlew test --stacktrace` or `--info` for details when needed. Never try to fix errors by turning on debug logs and global overriding blindly, as that only obscures the root cause.

## 11. Context caching and test reliability

Spring TestContext caches `ApplicationContext` instances across equivalent configurations—including imports/test customizers, profiles, and property sources. Having every test class import a slightly different group of beans produces **different cache keys**, loading more contexts. That is a tradeoff between isolation and speed.

Consider our two classes:
- `ProductionWiringTest` starts a context from `DemoApplication` without importing the test policy.
- `ImportedPrimaryWiringTest` imports `PromoFeeTestConfig` to add the primary policy.

The suite **must never depend on execution order between these two classes**. With stateless beans like our two lambda policies, caching cannot alter results. With fake repositories holding mutable lists, clear data between tests or use isolated fixtures; never assume context caching resets singletons.

Across suites with dozens of small varied imports, startup overhead grows; sharing explicit configs across related tests reduces context churn, though never cram every fake/config in the system into one `MegaTestConfig` just to share one context. That destroys boundary clarity and increases bean collision risk.

### Does `@DirtiesContext` fix bean overriding?

No. `@DirtiesContext` tells Spring TestContext the context is dirty and evicts it from the cache for reload. It **neither merges two same-type beans into one** nor permits duplicate definition names. If startup fails **while building the context**, dirtying the context will not cure bean registration/selection bugs. Use it only when state/config mutations render a cached context unsafe for reuse—never as a general-purpose reset hammer.

## 12. Design mistakes and better alternatives

### Mistake A: wanting to test a service, yet mocking the service itself

If a test aims to check `CheckoutService.shippingFee(...)` yet mocks `CheckoutService` to return 10, it only proves the mock returns its stub. Run the real service with a real or fake `FeePolicy`, asserting expected outputs from requirements. In our example, `CheckoutService` and both policies execute real code.

### Mistake B: enabling repo-wide overriding for one duplicate bean

This alters bean-registry behavior across many tests, hiding name collisions that ought to be caught. Find the **two classes defining the same bean name**, then rename, scope, profile, or use targeted test bean overrides. When tests need both the real bean and a fake, **give them distinct names** and use `@Primary`/`@Qualifier` instead of trying to overwrite the old bean.

### Mistake C: adding `@Primary` when the consumer has a `@Qualifier`

`@Primary` never erases a hardcoded qualifier. Decide whether **the consumer should pick by configuration or always bind to one provider**. If configurable, refactoring injection to an unqualified interface may be cleaner. If bound to a specific provider, tests should preserve that contract or use targeted replacement.

### Mistake D: using `@Qualifier` to "register" a bean

Putting `@Qualifier("promoFeePolicy")` on a test field or constructor does not create `promoFeePolicy`. Without a matching bean definition, Spring still reports a missing bean. First register via `@Bean`, `@Component`, `@Import`, or an actual override mechanism; only then does the qualifier select the candidate.

### Mistake E: treating every multiple-beans-of-same-type case as a conflict

Multiple beans implementing one interface is normal design: multiple payment strategies, handlers, or notification channels. A conflict occurs only when an injection point demands **a single bean** without a disambiguation rule. If the consumer truly wants **every** strategy, `List<T>`/`Map<String,T>` fits the contract better than `@Primary`.

### Mistake F: wiring tests that skip behavior checks

A test doing only `assertNotNull(context.getBean(CheckoutService.class))` passes even if the wrong policy was injected, since any bean instantiates. Our sample checks **10**, **30**, **0**, and instance selection, proving the chosen policy directly drives outputs.

### Mistake G: leaking test config into production

Putting `@TestConfiguration` or fake gateways in `src/main/java` just so tests compile risks shipping test configs in builds/deployments. Keep test-only classes under `src/test/java` and import explicitly. To share fixtures across Gradle modules, use test fixtures or dedicated test modules rather than bundling fakes inside business runtime artifacts.

## 13. Decision workflow for replacing beans in tests

Follow this sequence starting from the test goal:

1. **Is a Spring context needed?** If testing a single pure Java class, passing collaborators via constructor directly is simpler, faster, and lower risk.
2. **Is the goal changing config values or swapping implementations?** If only changing rates/URLs/flags, use test properties or profiles rather than creating extra beans.
3. **Can the production bean remain?** If yes, create a **differently named** test bean, import locally, and add `@Primary` for by-type injection.
4. **Does the consumer hardcode a qualifier?** If yes, decide whether that is a contract or implementation detail; do not assume primary overrides qualifiers.
5. **Do you need a real mock or a behavioral fake?** To control responses/calls and skip adapters, use your version's test mock mechanism; for deterministic behavior, a fake or real object can be clearer.
6. **Is there a bean name collision?** If yes, locate both registration sources and choose an explicit replacement strategy rather than enabling overriding by default.
7. **Must production still boot cleanly?** Maintain dedicated production-wiring tests rather than running the entire suite solely on fakes.
8. **Are there observable assertions?** Check outputs, exceptions, side effects, or payloads—not just context/bean existence.
9. **Is there context state?** Keep test configs small and singleton fakes stateless/resettable; avoid suite-order dependencies.
10. **When failing, is it a name or type error?** Read the root cause: duplicate definition name, multiple candidates of same type, or missing candidate.

## 14. Hands-on exercises

**Exercise A — observe `@Primary`'s effect:** in `PromoFeeTestConfig`, temporarily remove `@Primary` and run `ImportedPrimaryWiringTest`. With two differently named `FeePolicy` beans and by-type injection on `CheckoutService`, candidate selection turns ambiguous and context startup fails. Restore the annotation and explain why the error is not a duplicate definition name.

**Exercise B — qualifier beats primary:** keep `promoFeePolicy` marked primary. Run `qualifiedConsumerKeepsProductionPolicy` and confirm `AuditFeeService.referenceFee(100)` remains **30**. Temporarily change the constructor qualifier from `standardFeePolicy` to `promoFeePolicy` to see it change to **10**. Revert the change.

**Exercise C — both beans remain registered:** in `bothNamedDefinitionsRemainRegistered`, verify both keys in `Map<String, FeePolicy>`. If either bean were deleted from the context, the test must fail. Explain why having both beans present proves this is **not** bean-definition overriding.

**Exercise D — trigger a deliberate name collision:** on an experimental branch, rename the test bean to `standardFeePolicy` (e.g., `@Bean("standardFeePolicy")`). With Boot's default disallowing same-name overriding, expect context registration to fail. Restore `promoFeePolicy`. Never enable overriding just to pass the exercise.

**Exercise E — test the test oracle:** temporarily alter the standard policy from `orderAmount >= 500` to `orderAmount > 500`. `productionServicesUseStandardPolicy` with subtotal 500 must fail since the spec expects **0**. Revert. That is a business bug that asserting bean existence alone would never catch.

**Exercise F — verify production wiring:** check `ProductionWiringTest` without `@Import` to confirm the application context still supplies the standard policy. If a real app only boots when tests import a fake, add a proper production wiring/integration test to expose the gap.

**Exercise G — choose the replacement strategy:** given a real network `PaymentGateway` and an in-memory `FakePaymentGateway`, choose among (1) constructor-injected unit test without Spring, (2) importing differently named fake + primary, (3) test mock replacement, and (4) profile/conditional config. State what each proves and what still requires integration tests.

## 15. Pre-sign-off test configuration checklist

- [ ] Have I distinguished **two beans of the same type** from **two definitions with the same name**?
- [ ] Am I using `@Primary` to **prioritize**, without claiming it "deletes the production bean"?
- [ ] Does any injection point have a `@Qualifier` that prevents primary selection?
- [ ] When injecting `List<T>`/`Map<String,T>`, do I account for all same-type beans appearing?
- [ ] Are test beans declared in test sources and imported into **only the target test context**, avoiding broad scanning?
- [ ] Have I avoided enabling `spring.main.allow-bean-definition-overriding=true` just to mask config conflicts?
- [ ] When truly replacing a bean definition, did I use the mechanism supported by my Spring Boot/Spring Framework version?
- [ ] Are there tests confirming production boots and wires real beans properly where required?
- [ ] Do assertions verify **behavior**, not just "context loads" or "bean != null"?
- [ ] Are tests free from cached fake state or execution-order dependencies across test classes?
- [ ] Does Gradle/JUnit execute the right test task, with reports accurately reflecting invocation counts and failure causes?

**Remember:** `@Primary` determines the **preferred candidate** during by-type injection; `@Qualifier` clarifies the **candidate requested by an injection point**. Neither **replaces bean definitions in the registry by itself**. Enable bean definition overriding only when you fully understand same-name collisions, registration ordering, scope, and impact; in most Spring Boot tests, a small test config, explicit candidate selection, or targeted test replacement is easier to maintain and far more reliable.
