# Reading Framework Tests to Understand Back-Off Behavior and Edge Cases

## 1. Why Must You Read Spring Boot's Own Tests?

The API documentation explains that `@ConditionalOnMissingBean` allows an auto-configuration to provide a default bean when no matching bean exists yet. Yet when designing a real starter, the questions are often harder:

- If a custom bean has a different name from the default, does the default still back off?
- If two configurations are processed in a different order, does the condition see the bean yet?
- Are beans created via `FactoryBean`, XML imports, generic containers, or scoped proxies recognized?
- When a bean definition with the same name is replaced by a different type, does the condition use the old type or the new type?
- Are beans residing in a parent context counted?
- Under what circumstances can a condition match while dependency injection still fails?

These questions should be answered using **the framework's own tests**, because tests reveal inputs, context setup, expected outcomes, and edge-case boundaries that overview documentation may not fully spell out.

A good framework test usually does more than verify "whether the default bean was created". It creates multiple variants of `ApplicationContext` and asserts **which beans are present, which beans are absent, which conditions match, and whether the context starts successfully**.

## 2. Starting from the Structure of an Auto-Configuration Test

Spring Boot provides `ApplicationContextRunner` in `org.springframework.boot.test.context.runner`. It creates a lightweight context, runs a scenario, lets you execute assertions, and closes the context after the callback completes.

Common pattern:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        GreetingAutoConfiguration.class));

@Test
void defaultBeanIsCreatedWhenMissing() {
    this.contextRunner.run((context) -> {
        assertThat(context).hasSingleBean(GreetingService.class);
    });
}
```

Read a test in this order:

1. **Runner setup:** what kind of context is created? Is it a web context or non-web context? Which auto-configurations are loaded?
2. **Test inputs:** which user configurations, beans, properties, parent contexts, or classloaders does the test add?
3. **Point of variation:** compared to the baseline test, what single thing changed?
4. **Assertions:** does the test check bean count, bean name, bean instance, return value, or startup failure?
5. **Fixtures:** which beans do the nested configuration classes below create, which annotations do they use, and in what order are they declared?

Do not read only the test method name and infer behavior. Trace the entire fixture passed into `withUserConfiguration` or `withConfiguration` to see the exact conditions under test.

### Key Tools in the Runner

| API | Role in Tests |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Loads auto-configurations via the test mechanism dedicated to auto-configuration |
| `withUserConfiguration(...)` | Registers application/user-provided configurations |
| `withBean(...)` | Registers a bean directly in the test context |
| `withPropertyValues(...)` | Modifies `Environment` to test property conditions |
| `withClassLoader(new FilteredClassLoader(...))` | Simulates classes or packages missing from the runtime classpath |
| `withParent(...)` | Creates a context hierarchy to test bean lookup in parent/child |
| `withAllowBeanDefinitionOverriding(...)` | Enables/disables same-name bean definition overriding in tests |
| `run(context -> ...)` | Initializes the context, executes assertions, and closes the context |

`ApplicationContextRunner` creates a standard context without a web server. If an auto-configuration requires a Servlet or Reactive context, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`. This is an important distinction: testing the right condition in the wrong context type can produce results unrepresentative of the real application.

## 3. What Does "Back-Off" Actually Mean?

Suppose a starter provides a default:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return () -> "auto";
}
```

When the application has already registered a matching `GreetingService` bean, the default method's condition does not match. Spring **does not register that default bean**.

This is a yielding mechanism before the default bean definition is created. It is not:

- Creating both default and custom beans and picking one with `@Primary`.
- Creating two beans with the same name and letting the later one overwrite.
- Instantiating the default and then removing it from the context.
- Automatically merging state from two implementations.

A proper test should check simultaneously:

1. The context has only one bean matching the contract.
2. The custom bean remains under its own name.
3. The default bean is not registered.
4. Calling the method returns the value from the custom implementation.

Asserting only `hasSingleBean(GreetingService.class)` is sometimes not enough to be sure which bean was used. Also verify bean names and business outcomes.

### Custom Beans Do Not Need the Same Name as the Default

For example, the application declares:

```java
@Configuration(proxyBeanMethods = false)
class UserConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return () -> "user";
    }
}
```

The bean is named `customGreetingService`, different from `greetingService`. Even so, `@ConditionalOnMissingBean(GreetingService.class)` checks by **type**, so the default still backs off.

This is why back-off tests should use different bean names. If a test declares the same name and enables bean-definition overriding, you might accidentally test name overriding instead of type-based condition behavior.

## 4. Reading Upstream Tests: Inferring Contracts from Assertions

In Spring Boot's upstream test suite, bean condition tests use small configurations to isolate each factor. Notable test groups worth reading:

### 4.1. Type, Name, and Annotation Are Three Distinct Contracts

Tests such as `testNameOnBeanCondition`, `testNameAndTypeOnBeanCondition`, `testClassOnBeanCondition`, and `testAnnotationOnBeanCondition` demonstrate that conditions can check beans by multiple criteria.

- `@ConditionalOnMissingBean(GreetingService.class)`: checks by type.
- `@ConditionalOnMissingBean(name = "greetingService")`: checks by name.
- `@ConditionalOnMissingBean(annotation = CustomQualifier.class)`: checks annotations on beans.
- When both name and type are declared, **all specified criteria participate in the condition**.

For example, if a user declares a bean `customGreetingService` of type `GreetingService` while the default checks only the name `greetingService`, a name-based condition does not infer that the custom bean shares the same type. You can end up with two beans for the same contract.

Therefore, choose criteria based on the extension contract:

- Users may replace the implementation with any bean name → typically check by type.
- Only one specific bean name is treated as the replacement point → check by name.
- Any bean marked with a specific qualifier/annotation must cause the default to back off → check by annotation and verify proxies too.

### 4.2. Configuration Processing Order Is Part of the Input

The `testNameOnBeanConditionReverseOrder` test in the upstream suite intentionally reverses the registration order of two configurations. When the configuration carrying the condition is processed before the configuration creating the bean it searches for, the condition may not see the bean definition yet and fail to match.

This explains Spring Boot's recommendation: place `@ConditionalOnBean` and `@ConditionalOnMissingBean` in **auto-configurations**, because auto-configurations are processed after user bean definitions under Boot's model.

A consumer depending on a bean supplied by another auto-configuration should declare appropriate ordering:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // Conditions need to see bean definitions from FoundationAutoConfiguration.
}
```

Testing with `AutoConfigurations.of(...)` helps simulate the auto-configuration pipeline. Do not treat the argument order passed into a test as proof that bean instances will be instantiated in that same order.

### 4.3. XML Imports Can Change When Bean Definitions Appear

Tests `testOnBeanConditionWithXml` and `testOnBeanConditionWithCombinedXml` show that the test suite also tests Java configurations combined with `@ImportResource`.

What matters when reading is not just whether the XML contains a bean, but **at which stage the bean definition is registered relative to when the condition is evaluated**. If a test fails, inspect the processing order of XML imports, Java configurations, and auto-configurations before concluding the condition is wrong.

This is also why starters should prefer Boot's standard auto-configuration registration path rather than mixing user configurations, XML imports, and conditions in an uncontrolled order.

### 4.4. When a Same-Name Bean Definition Is Replaced by a Different Type

The `conditionEvaluationConsidersChangeInTypeWhenBeanIsOverridden` test creates an initial definition of type `String` and then replaces the same-name definition with type `Integer` when bean-definition overriding is enabled. A consumer configuration with `@ConditionalOnBean(String.class)` is expected **not** to appear after the definition's type has changed.

This test reminds us that type-based conditions depend on **current bean definition metadata**, not simply the bean name or the type of a previously overridden definition.

In Boot applications, bean-definition overriding is normally disabled by default. The test enables it intentionally to verify a container edge case. Do not enable overriding in production just to make a test pass.

### 4.5. `FactoryBean`: Distinguishing the Factory from the Object It Produces

Tests such as `beanProducedByFactoryBeanIsConsideredWhenMatchingOnAnnotation` verify whether a product bean created by a `FactoryBean` is recognized by the condition when checking annotations.

Do not confuse the two objects:

- Factory bean: the object implementing `FactoryBean<T>`, whose name is usually accessed with the `&` prefix.
- Product bean: the object of type `T` returned by `getObject()`.

If a condition checks the product's type/annotation, read the test to see which bean name it registers and asserts. A test checking only that the factory exists does not prove the product is matched properly.

### 4.6. Generics and Parameterized Containers

Tests named `genericWhenTypeArgumentMatches`, `genericWhenTypeArgumentWithValueMatches`, and `parameterizedContainerWhenValueIsOfExistingBeanMatches` check generic information and container types.

For example, a `Store<Customer>` bean is not equivalent to `Store<Order>` if the condition cares about the type argument. Likewise, if the target type is wrapped in a container like `Registration<Customer>`, the condition can declare `parameterizedContainer` to check the inner element.

`@ConditionalOnMissingBean` and `@ConditionalOnBean` support `parameterizedContainer`. When reading tests, pay attention to the factory method's declared type, generic type arguments, and specified container—not just the bean name.

### 4.7. Non-Autowire Candidate Beans

Newer upstream test suites also distinguish type/annotation conditions from name conditions when a bean is declared with `autowireCandidate = false`. Type/annotation matching may ignore a bean disallowed as an autowire candidate, whereas name-based checks may still recognize that bean name.

This is a good example of reading tests by **criterion type** rather than assuming "if a bean is in the registry, every condition sees it identically".

**Version limitation:** newer upstream test suites also include `defaultCandidate = false` cases. This attribute belongs to Spring Framework 6.2 / Spring Boot 3.4 and later; do not backport that example into a Spring Boot 3.3.5 project. When studying test source from a newer branch, always check whether the API exists in your target version.

## 5. Key Edge Case on Spring Boot 3.3.5: Scoped Proxies and Annotation Back-Off

An upstream Spring Boot issue, `#43423`, provides an instructive test because it directly compares behavior between 3.3.5 and 3.4.0.

Problem: an auto-configuration provides a default `Supplier<String>` if no bean annotated with `AnnotationConditionQualifier` is found:

```java
@Bean
@AnnotationConditionQualifier
@ConditionalOnMissingBean(annotation = AnnotationConditionQualifier.class)
public Supplier<String> supplier() {
    return () -> "auto-configuration-string";
}
```

The application has a custom `Supplier<String>` marked with the same annotation. There are two variants:

1. A regular bean.
2. A request-scoped bean using `ScopedProxyMode.INTERFACES`.

The regular test verifies that the `Supplier` bean list contains only `customSupplier`. The scoped test checks both the proxy bean and the target bean name generated by `ScopedProxyUtils.getTargetBeanName("customSupplier")`, and verifies that the auto-configuration's default supplier is absent.

The issue notes clearly: the regular case passes in both 3.3.5 and 3.4.0; the scoped proxy test passes in 3.3.5 but fails in 3.4.0 after a change in how autowire/default candidates are evaluated. The issue has milestone 3.4.1. For 3.3.5, the example in the issue also uses `value = Void.class` alongside the annotation to avoid type-based matching and isolate the annotation criterion cleanly.

Lessons from this test:

- A proxied bean can involve multiple bean names: the proxy and the target.
- Checking beans by annotation can behave differently when proxies/scoped targets are generated.
- Testing only with regular singletons is not enough to prove correct behavior for request/session scopes.
- When upgrading Spring Boot, re-run back-off tests involving proxies instead of assuming conditions did not change.

Do not apply one version's workaround across every version. Keep a reproducible test, run it on the exact Boot/Framework version, and check issues/release notes before changing annotations or proxy settings.

## 6. Minimal Back-Off Test Example on Spring Boot 3.3.5 / Java 17+

This example creates a small auto-configuration and tests default and custom beans. It uses `ApplicationContextRunner` as recommended by Spring Boot for testing auto-configurations.

### 6.1. Project Structure

```text
greeting-autoconfigure-test/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── api/GreetingService.java
    │   └── autoconfigure/GreetingAutoConfiguration.java
    └── test/java/demo/autoconfigure/
        └── GreetingAutoConfigurationTests.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>greeting-autoconfigure-test</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 6.3. `src/main/java/demo/api/GreetingService.java`

```java
package demo.api;

public interface GreetingService {
    String greet();
}
```

### 6.4. `src/main/java/demo/autoconfigure/GreetingAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return () -> "auto";
    }
}
```

Here, the condition explicitly declares the `GreetingService.class` contract. When the user supplies a bean with a different name but the same type, the default still backs off.

### 6.5. `src/test/java/demo/autoconfigure/GreetingAutoConfigurationTests.java`

```java
package demo.autoconfigure;

import demo.api.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenNoUserBeanExists() {
        this.contextRunner.run((context) -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasBean("greetingService");
            assertThat(context.getBean(GreetingService.class).greet())
                    .isEqualTo("auto");
        });
    }

    @Test
    void backsOffWhenUserProvidesBeanWithDifferentName() {
        this.contextRunner
                .withUserConfiguration(UserConfiguration.class)
                .run((context) -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasBean("customGreetingService");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class).greet())
                            .isEqualTo("user");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return () -> "user";
        }
    }
}
```

Run the tests:

```bash
mvn -q test
```

The two tests confirm the two core states:

- No user bean: default is created.
- User bean with a different name but the same type: default is not registered and the user implementation is used.

This is the minimal test to guard the back-off contract. When adding it to a real starter, expand it for the classpaths, properties, annotations, scopes, and context hierarchies supported by the starter.

## 7. Expanding the Test Matrix for Edge Cases

There is no need to cram every case into one giant test. Write a separate test for each varying factor, using method names that express the input and outcome.

| Varying Factor | Required Test Setup | Recommended Assertions |
| --- | --- | --- |
| No custom bean | Auto-configuration only | Exactly one default exists |
| Custom bean with different name, same type | User configuration creates custom bean | Custom exists, default is absent |
| Name-based condition | Bean of same type with different name | Name-based default may still appear; verify multiple beans can be created |
| Annotation-based condition | Custom bean marked with annotation | Default backs off when annotation is recognized |
| Property toggle | `withPropertyValues` | Only beans with that property condition change |
| Classpath present/absent | `FilteredClassLoader` | Class-level auto-configuration is enabled/disabled |
| Bean in parent context | `withParent` and SearchStrategy | Result matches `ALL`, `ANCESTORS`, or `CURRENT` |
| Two configs in reversed order | Flip registration order | Detect whether condition sees bean definition at evaluation time |
| FactoryBean product | Register `FactoryBean<T>` | Check product type/annotation, not only factory |
| Generic/parameterized container | `GenericType` or `parameterizedContainer` | Only matching type argument/container matches |
| Scoped proxy | Request scope and proxy mode | Check proxy + target bean name; default is absent |
| Bean definition changes type | Allow overriding in dedicated test | Condition reflects final definition type |
| Multiple candidates | Two beans of same type, primary/non-primary | Test single-candidate and dependency injection separately |

For each test, verify **both positive and negative assertions**. For instance, if a back-off test asserts only that the custom bean is present without asserting the default is absent, the test might still pass even if the framework unexpectedly created an extra default bean.

## 8. How to Investigate a Failing Framework Test

When upgrading versions or modifying auto-configurations, follow this sequence:

1. **Run a single test:** use Maven Surefire to run only the failing class/method, e.g., `mvn -Dtest=GreetingAutoConfigurationTests#backsOffWhenUserProvidesBeanWithDifferentName test`.
2. **Read the first failing assertion:** did the context fail to start? Is it wrong bean count, wrong bean name, or wrong implementation value?
3. **Read the fixture:** was the user bean registered via `withUserConfiguration` or `withBean`? Are there other class-level or property conditions?
4. **Inspect bean definitions:** retrieve bean names by type, bean definition class, factory method, and role if needed. Do not rely solely on `getBean(Class)` since it may fail due to multiple candidates.
5. **Check processing timing:** do provider/consumer auto-configurations have `before`/`after` relationships? Was user config registered before auto-configuration?
6. **Check bean kind:** singleton or scoped proxy? Product bean from `FactoryBean`? Was generic type lost due to an overly broad return type?
7. **Compare versions:** read test source and implementation at the same tag/version. A newer test on main may use APIs or semantics absent in Boot 3.3.5.
8. **Create a minimal regression test:** keep only the failing inputs, remove unnecessary config, name the test after the bug, and assert exact bean names/outcomes.
9. **Run the full test suite:** once the minimal test passes, run module tests to catch impacts on other auto-configurations.

When you need to inspect the condition report, use `ConditionEvaluationReport` or enable `ConditionEvaluationReportLoggingListener` in the runner. The report helps explain condition matches/non-matches; assertions on the bean registry are still necessary to confirm the final outcome.

## 9. Pitfalls When Reading Tests from Different Framework Branches

**Pitfall 1 — copying newer APIs into Boot 3.3.5.** Newer test suites may use `@Bean(defaultCandidate = false)` or newer semantics. Spring Boot 3.3.5 uses Spring Framework 6.1; do not assume Framework 6.2 attributes exist.

**Pitfall 2 — mistaking a current-branch test for an older version's contract.** Use newer test suites to spot edge-case categories, then verify each case on the exact deployed tag. Issue #43423 is an example: scoped proxy annotation matching differs between 3.3.5 and 3.4.0.

**Pitfall 3 — testing only with a standard context.** A test using `ApplicationContextRunner` does not automatically test Servlet/Reactive scopes, request proxies, or web servers. Use the runner matching the context you need to simulate.

**Pitfall 4 — checking only one bean.** `@ConditionalOnMissingBean` may cause the default to back off while another consumer fails, or another bean of the same type still exists. Assert bean names, counts, selected implementation, and startup state.

**Pitfall 5 — confusing conditions with dependency injection.** `@ConditionalOnBean` can match when a bean exists, yet a single injection point can still be ambiguous if multiple candidates exist. A condition match does not prove the factory method will succeed in creating the bean.

**Pitfall 6 — overlooking already-processed bean definitions.** Bean conditions do not predict every definition that will appear later. Regular configurations in reversed order can yield different results from Boot-sorted auto-configurations.

**Pitfall 7 — failing to distinguish factory from product.** Tests involving `FactoryBean` must check the exact object the condition matches against, especially when checking annotations or generic types.

**Pitfall 8 — asserting only that the context does not fail.** The context can start up even though the default was lost or a consumer was never registered. Assert the required functionality as well.

## 10. Checklist When Reviewing Auto-Configuration Based on Framework Tests

- [ ] Read the relevant test classes in the exact Spring Boot version in use.
- [ ] Identified the runner context type and loaded auto-configurations.
- [ ] Read the entire test fixture, not just the test method.
- [ ] Tested the default when no custom bean is present.
- [ ] Tested a custom bean with a different name from the default and verified the default is absent.
- [ ] Verified type/name/annotation conditions match the intended contract.
- [ ] Tested classpath/property conditions if the auto-configuration has those gates.
- [ ] Verified bean definition registration order.
- [ ] Tested `FactoryBean`, generics/containers, parent contexts, or proxies where relevant.
- [ ] Checked both bean names/counts and the behavior of the selected bean.
- [ ] Ran regression tests on the exact version and the full test module.
- [ ] Explicitly documented differences when referencing tests from a newer Spring Boot branch.

## Recommended Official Docs and Upstream Tests

- [Spring Boot 3.3 — Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): how to use `ApplicationContextRunner`, `AutoConfigurations`, `FilteredClassLoader`, and runners for web contexts.
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): API for creating test contexts and customizations.
- [Upstream test source: `ConditionalOnBeanTests.java`](https://fossies.org/linux/spring-boot/core/spring-boot-autoconfigure/src/test/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBeanTests.java): upstream test suite on a newer branch, useful for seeing how type/name/annotation, ordering, FactoryBean, generics, and candidate filtering tests are organized. Tests using newer APIs must be checked against your version before applying.
- [Spring Boot issue #43423 — OnBeanCondition and scoped proxy](https://github.com/spring-projects/spring-boot/issues/43423): concrete test case comparing 3.3.5 and 3.4.0 behavior when `@ConditionalOnMissingBean(annotation = ...)` encounters a request-scoped proxy.
- [Spring Boot issue #23069 — `@ConditionalOnMissingBean` and `@ImportResource`](https://github.com/spring-projects/spring-framework/issues/23069): historical example showing how XML/Java bean definition order can affect back-off.
