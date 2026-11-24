# Creating Default Beans with Explicit Back-Off Conditions in Spring Boot

## 1. Goal: Provide Defaults While Respecting Application Choices

A Spring Boot library often wants to provide a ready-made bean so users can get started quickly. For example, a reporting library might provide `DefaultReportService` to handle report generation requests. However, a consuming application might need custom logic: writing audit logs, adding caching, calling another service, or applying custom business policies.

The desired behavior is:

- If the application **has not provided** a report service, the library registers `DefaultReportService`.
- If the application **has provided** a bean implementing `ReportService`, the library backs off and keeps the application's bean.
- Back-off happens during bean definition registration, without creating two beans and picking one at runtime.

Spring Boot provides `@ConditionalOnMissingBean` to express this rule. It is a key bean condition when developing auto-configurations and starters.

## 2. How It Works Basically

Example:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }
}
```

This is a sample configuration. `ReportService` is an interface defined by the library; `DefaultReportService` is the default implementation.

Spring Boot evaluates `@ConditionalOnMissingBean(ReportService.class)` when processing the `@Bean` method:

1. Checks bean definitions already processed within the search scope.
2. Searches for beans matching the `ReportService` criterion.
3. If no matching bean exists, the condition matches and the `defaultReportService` bean definition is registered.
4. If a matching bean already exists, the condition does not match and the default bean is not registered.

The result is **back-off**: the library steps back from supplying the default bean when the application already has its own choice.

The condition does not delete the user's bean, modify their implementation, or create a substitute bean. It only decides whether to register the default bean.

## 3. Why Check the Interface Instead of Only the Default Class?

Suppose the library has an interface:

```java
public interface ReportService {
    String generate();
}
```

The default implementation:

```java
public final class DefaultReportService implements ReportService {

    @Override
    public String generate() {
        return "default report";
    }
}
```

An application can provide its own implementation:

```java
public final class CustomReportService implements ReportService {

    @Override
    public String generate() {
        return "custom report";
    }
}
```

If the goal is that **any implementation of `ReportService` must replace the default**, use:

```java
@Bean
@ConditionalOnMissingBean(ReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

If you only use:

```java
@Bean
@ConditionalOnMissingBean(DefaultReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

then `CustomReportService` is not a `DefaultReportService`. Therefore, the condition can still match and the library registers the default bean as well. The context ends up with two candidates for `ReportService`, causing errors during interface injection if no qualifier or primary is configured.

| Check criterion | Application has `CustomReportService` | Outcome |
|---|---|---|
| `ReportService.class` | Matching bean exists | Default bean backs off |
| `DefaultReportService.class` | No bean of the default class | Default bean may still be registered |
| Name `customReportService` | Default bean has a different name | Name-based condition still matches |
| Name `defaultReportService` | Bean with that exact name exists | Default bean backs off by name |

**Design principle:** check the abstraction that users are allowed to customize. For services, that is usually the library's public interface or base class.

## 4. Bean Identification Attributes to Check

`@ConditionalOnMissingBean` supports several ways to describe the bean that must be absent:

| Attribute | Type | Meaning |
|---|---|---|
| `value` | `Class<?>[]` | Check by Java type |
| `type` | `String[]` | Check by fully qualified class name (FQCN) |
| `name` | `String[]` | Check by bean name |
| `annotation` | `Class<? extends Annotation>[]` | Check whether a bean carries the specified annotation |
| `ignored` | `Class<?>[]` | Ignore specific bean types when searching for matching candidates |
| `ignoredType` | `String[]` | Ignore bean types by fully qualified class name |
| `search` | `SearchStrategy` | Select the context hierarchy scope to search |
| `parameterizedContainer` | `Class<?>[]` | Recognize target bean types inside generic containers |

### 4.1. Checking by Type with `value`

```java
@ConditionalOnMissingBean(ReportService.class)
```

This is the most common way when letting applications provide any implementation of an abstraction.

Multiple types can be checked:

```java
@ConditionalOnMissingBean({
    ReportService.class,
    ReportExporter.class
})
```

The condition matches only when **no bean matches any of the specified criteria**. If the application already provides a bean matching one of the criteria, the missing-bean condition no longer holds and the default bean is not registered.

### 4.2. Checking by Class Name with `type`

When you do not want a direct compile-time reference to a class, you can use the class name:

```java
@Bean
@ConditionalOnMissingBean(
    type = "com.example.report.ReportService"
)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

`type` accepts an FQCN, not a bean name. String names are not checked by the compiler; ensure the package and class name are exact. This approach is useful when writing auto-configurations integrating optional modules.

### 4.3. Checking by Bean Name with `name`

```java
@Bean
@ConditionalOnMissingBean(name = "reportService")
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

The condition only checks whether a bean named `reportService` is absent. Another bean with a different name but the same `ReportService` type does not necessarily make this condition fail.

Use name-based checks when the configuration contract truly depends on a specific bean name. If users are expected to swap implementations by type, prefer `value`.

### 4.4. Checking by Annotation

You can require that no bean carries a specific annotation:

```java
@ConditionalOnMissingBean(annotation = InternalReportAdapter.class)
```

This checks bean annotation metadata. It fits when the library defines a marker annotation to identify a group of components; do not use it in place of a type check when the real contract is an interface.

## 5. Omitting the Target: Spring Boot Infers from the Return Type

When `@ConditionalOnMissingBean` is placed on a `@Bean` method without specifying `value`, `type`, or `name`, the checked bean type defaults to **the method's return type**.

Example:

```java
@Bean
@ConditionalOnMissingBean
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

In this example, Spring Boot checks for beans of type `DefaultReportService`.

This is convenient, but may fail to capture the intended extension contract. If the application supplies `CustomReportService` implementing `ReportService`, defaulting to `DefaultReportService` does not detect that custom bean.

To allow any implementation of the interface to replace the default bean, write it explicitly:

```java
@Bean
@ConditionalOnMissingBean(ReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

### Declare the Most Specific Return Type Possible

Conditions evaluate using the type metadata Spring knows when processing bean definitions. Therefore, `@Bean` methods should expose the most specific return type possible:

```java
// Recommended: Spring knows the concrete implementation
@Bean
@ConditionalOnMissingBean(ReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}

// Avoid without good reason: metadata only shows Object
@Bean
@ConditionalOnMissingBean(ReportService.class)
Object defaultReportService() {
    return new DefaultReportService();
}
```

When specifying `ReportService.class` explicitly, the condition has a clear target; nevertheless, a concrete return type still helps Spring predict the bean type better before instantiation and helps tools and IDEs understand the bean.

## 6. Conditions Only See Already-Processed Bean Definitions

This is the most important limitation when using `@ConditionalOnMissingBean`.

The condition evaluates only the bean definitions that the application context has processed **up to the moment the condition runs**. It does not wait for every configuration in the application to finish and re-evaluate afterward.

That is why Spring Boot recommends using `@ConditionalOnMissingBean` inside **auto-configurations**. Auto-configurations are processed after application-declared bean definitions, so they can see the user's custom beans and back off at the right time.

If a replacement bean might be created by another auto-configuration, ensure the auto-configuration providing the fallback runs after the configuration creating that bean.

Example:

```java
@AutoConfiguration(after = CustomReportProviderAutoConfiguration.class)
public class ReportFallbackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }
}
```

`CustomReportProviderAutoConfiguration` is an illustrative class name. This `after` relationship is only needed if the fallback depends on a bean supplied by that auto-configuration.

### Avoid Arbitrary Bean Conditions in Regular Configuration Classes

If a component-scanned `@Configuration` class has its condition run before the configuration creating a custom bean, results may differ from expectations. Move default beans into auto-configurations so Spring Boot applies them after user configurations.

## 7. Placing the Condition at the Class Level vs. `@Bean` Method Level

`@ConditionalOnMissingBean` can be placed at both the class level and the method level.

### At the Method Level

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }

    @Bean
    ReportMetrics reportMetrics() {
        return new ReportMetrics();
    }
}
```

If the application already has a `ReportService`, only the `defaultReportService` bean is not registered. The `reportMetrics` bean can still be registered.

This is a good choice when each bean has its own condition.

### At the Class Level

```java
@AutoConfiguration
@ConditionalOnMissingBean(ReportService.class)
public class ReportAutoConfiguration {

    @Bean
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }

    @Bean
    ReportMetrics reportMetrics() {
        return new ReportMetrics();
    }
}
```

If the condition does not match, the configuration class is not registered as a configuration bean in the context. A class-level condition has broader scope because it affects all bean methods inside.

Note: `@ConditionalOnBean` and `@ConditionalOnMissingBean` do not mean the JVM will never load/read the configuration class. The main difference is that a class-level condition prevents registering the configuration class when unmatched, whereas a method-level condition governs only the corresponding bean method.

**How to choose:** place the condition on the method when only the default bean needs to back off; place it on the class when the entire group of beans only makes sense while the abstraction has not been provided.

## 8. Context Hierarchy Search Scope with `search`

An application may have parent and child contexts. `@ConditionalOnMissingBean` has a `search` attribute to control the search scope.

| Value | Scope |
|---|---|
| `SearchStrategy.ALL` | Searches the current context and ancestor contexts; this is the default |
| `SearchStrategy.CURRENT` | Searches only the current context |
| `SearchStrategy.ANCESTORS` | Searches only ancestor contexts |

Example:

```java
@Bean
@ConditionalOnMissingBean(
    value = ReportService.class,
    search = SearchStrategy.CURRENT
)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

With `CURRENT`, a `ReportService` in a parent context does not cause the child context's condition to fail. The child context can register its own fallback.

With the default `ALL`, beans in parent contexts are counted during the search. This is usually appropriate when the child context can use shared beans from the parent.

Choose the scope according to the actual context architecture. Changing `search` may introduce extra beans in a child context and create multiple candidates during injection.

## 9. Ignoring Specific Bean Types with `ignored` and `ignoredType`

These two attributes allow ignoring certain types when the condition looks for matching beans.

Example:

```java
@Bean
@ConditionalOnMissingBean(
    value = ReportService.class,
    ignored = HealthReportService.class
)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

Suppose `HealthReportService` also implements `ReportService`, but is used solely for health checks and should not count as a business implementation. The condition then ignores that type during its search.

`ignoredType` does the same thing using a fully qualified class name:

```java
@ConditionalOnMissingBean(
    value = ReportService.class,
    ignoredType = "com.example.health.HealthReportService"
)
```

Important note: **ignoring does not delete the bean**. If the health bean still exists and the fallback is created, the context may contain multiple beans implementing `ReportService`. When injecting by interface, the application needs a qualifier or a separate abstraction design to avoid ambiguity.

Only use `ignored`/`ignoredType` when there is genuinely a bean type that must not count as a replacement for the fallback.

## 10. Generic Containers with `parameterizedContainer`

Some libraries register beans via generic wrappers. For example, a servlet filter might be registered directly or wrapped in a `FilterRegistrationBean<Filter>`.

`parameterizedContainer` lets the condition inspect the target type inside generic containers as well:

```java
@ConditionalOnMissingBean(
    value = AuditFilter.class,
    parameterizedContainer = FilterRegistrationBean.class
)
```

This is an advanced mechanism. Spring Boot also provides `@ConditionalOnMissingFilterBean` to detect filters registered directly or through `FilterRegistrationBean`. For regular beans without generic wrappers, there is no need to declare this attribute.

## 11. Distinguishing from Other Conditions

| Annotation | Question |
|---|---|
| `@ConditionalOnMissingBean` | Create the bean only when no matching bean exists yet |
| `@ConditionalOnBean` | Create the bean only when a matching bean already exists |
| `@ConditionalOnClass` | Apply only when the class is on the classpath |
| `@ConditionalOnMissingClass` | Apply only when the class is not on the classpath |
| `@ConditionalOnProperty` | Apply only when the property matches the condition |
| `@ConditionalOnSingleCandidate` | Apply only when a single suitable bean candidate can be determined |

`@ConditionalOnMissingBean` checks beans in the BeanFactory. It does not replace `@ConditionalOnMissingClass`: a class may exist on the classpath without a bean, or a bean may be created from an existing class.

A practical pattern may combine multiple conditions:

```java
@AutoConfiguration
@ConditionalOnClass(ReportClient.class)
@ConditionalOnProperty(
    prefix = "demo.report",
    name = "enabled",
    havingValue = "true"
)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService(ReportClient client) {
        return new DefaultReportService(client);
    }
}
```

Here, classpath and property conditions decide whether the configuration applies; the bean condition decides whether a fallback is needed or the application already has its own service.

## 12. Testing Example with `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

`ApplicationContextRunner` creates lightweight contexts to test auto-configuration per scenario. The example below verifies:

1. Without a custom service, the default bean is created.
2. With a custom implementation of the interface, the default bean backs off.
3. An unrelated bean does not suppress the fallback.
4. A bean-name condition backs off when that name already exists.

Create file `src/test/java/demo/ConditionalDefaultBeanTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConditionalDefaultBeanTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReportAutoConfiguration.class)
                    );

    private final ApplicationContextRunner namedRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(NamedReportAutoConfiguration.class)
                    );

    @Test
    void createsDefaultWhenNoReportServiceExists() {
        runner.run(context -> {
            assertTrue(context.containsBean("defaultReportService"));
            assertEquals(
                    "default",
                    context.getBean(ReportService.class).generate()
            );
        });
    }

    @Test
    void backsOffWhenApplicationProvidesCustomImplementation() {
        runner.withUserConfiguration(UserReportConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("customReportService"));
                    assertFalse(context.containsBean("defaultReportService"));
                    assertEquals(
                            "custom",
                            context.getBean(ReportService.class).generate()
                    );
                });
    }

    @Test
    void unrelatedBeanDoesNotSuppressDefault() {
        runner.withUserConfiguration(UnrelatedConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("otherService"));
                    assertTrue(context.containsBean("defaultReportService"));
                });
    }

    @Test
    void namedConditionBacksOffWhenThatBeanNameExists() {
        namedRunner.withUserConfiguration(NamedUserReportConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("namedReportService"));
                    assertFalse(context.containsBean("namedFallbackReportService"));
                });
    }

    interface ReportService {
        String generate();
    }

    static final class DefaultReportService implements ReportService {
        @Override
        public String generate() {
            return "default";
        }
    }

    static final class CustomReportService implements ReportService {
        @Override
        public String generate() {
            return "custom";
        }
    }

    @AutoConfiguration
    static class ReportAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        DefaultReportService defaultReportService() {
            return new DefaultReportService();
        }
    }

    @AutoConfiguration
    static class NamedReportAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(name = "namedReportService")
        DefaultReportService namedFallbackReportService() {
            return new DefaultReportService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserReportConfiguration {
        @Bean
        ReportService customReportService() {
            return new CustomReportService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UnrelatedConfiguration {
        @Bean
        String otherService() {
            return "unrelated";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class NamedUserReportConfiguration {
        @Bean("namedReportService")
        ReportService namedReportService() {
            return new CustomReportService();
        }
    }
}
```

### Expected Results

| Test | Outcome |
|---|---|
| `createsDefaultWhenNoReportServiceExists` | `defaultReportService` bean exists; `generate()` returns `default` |
| `backsOffWhenApplicationProvidesCustomImplementation` | `customReportService` exists; `defaultReportService` does not; result is `custom` |
| `unrelatedBeanDoesNotSuppressDefault` | `otherService` exists and fallback still exists |
| `namedConditionBacksOffWhenThatBeanNameExists` | `namedReportService` exists; `namedFallbackReportService` does not |

The tests use bean presence and method results to prove behavior. They do not need an HTTP server or database connection.

### Dependencies and Run Commands

With Gradle configured for Spring Boot 3.3.x and Java 17+:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run:

```bash
./gradlew test --tests demo.ConditionalDefaultBeanTest
```

On Windows PowerShell:

```powershell
.\\gradlew.bat test --tests demo.ConditionalDefaultBeanTest
```

**Expected outcome:** 4 tests pass. This is the expected result based on the code, not actual execution logs. Run it in a project with real dependencies and Spring Boot version to confirm.

## 13. Common Mistakes and How to Fix Them

1. **Checking only the default implementation class.** The application provides another implementation of the interface, yet the fallback is still created. Check the public interface or abstraction.
2. **Not specifying the target when the return type is too broad.** If the method returns `Object` or the wrong interface, the condition may not express the intent. Provide a concrete return type and specify `value` when needed.
3. **Placing conditions in wrongly ordered configurations.** Conditions see only already-processed bean definitions. Use auto-configurations and declare `after` when depending on beans from another auto-configuration.
4. **Confusing bean names with bean types.** `name` checks bean names; `value`/`type` check types. Choose according to the contract you want to protect.
5. **Placing the condition at class level when only one bean should back off.** Other bean methods in the class are also affected. Move the condition down to the fallback method.
6. **Using `ignored` and forgetting the ignored bean still exists.** This can leave multiple candidates for the same interface and cause injection errors.
7. **Misunderstanding context hierarchy.** The default `SearchStrategy.ALL` can see beans from parent contexts. Use `CURRENT` or `ANCESTORS` only when a different scope is genuinely needed.
8. **Assuming `@Primary` replaces a missing-bean condition.** `@Primary` affects candidate selection during injection; `@ConditionalOnMissingBean` decides whether to register a fallback based on matching beans. The two mechanisms solve different problems.
9. **Expecting conditions to re-evaluate at runtime.** Bean conditions are evaluated during context creation. Adding beans or changing properties after startup does not automatically add or remove fallbacks.
10. **Treating back-off as an error.** When a user bean already exists and the fallback is not created, that is usually the intended design behavior.

## 14. Workflow for Designing a Customizable Default Bean

1. Identify the **public abstraction** that applications are allowed to replace, usually an interface.
2. Write the default implementation with a concrete return type.
3. Place `@ConditionalOnMissingBean(Abstraction.class)` directly on the default bean method.
4. Put the method inside an auto-configuration so user bean definitions are processed first.
5. If another auto-configuration may provide a replacement bean, declare an appropriate `after` ordering.
6. Check the context hierarchy and decide whether `search` needs to change from the default `ALL`.
7. Use `ApplicationContextRunner` to test at minimum: no bean, custom implementation, unrelated bean, and bean-name cases if using `name`.
8. Verify the default bean does not appear when a custom bean exists and that the custom bean is used.

## 15. Takeaways

- `@ConditionalOnMissingBean` is the **back-off** mechanism letting auto-configuration yield to application-supplied beans.
- `value`/`type` check types; `name` checks bean names; `annotation` checks annotations on beans.
- When no target is specified on a `@Bean` method, Spring Boot infers the checked type from the method's return type.
- If every implementation of an interface should replace the default, check the **interface**, not just the default class.
- Conditions see only already-processed bean definitions; put bean conditions inside auto-configurations and declare ordering if needed.
- `search` defaults to `ALL`; beans in a parent context can cause a fallback in a child context to back off.
- `ignored`/`ignoredType` only exclude beans from the check; they do not delete beans.
- Class-level conditions have broader scope than conditions on individual bean methods.
- `@Primary` governs injection selection; `@ConditionalOnMissingBean` governs default bean registration.

### Official Documentation

- Spring Boot 3.3 Javadoc — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 Reference — Creating Your Own Auto-configuration, Bean Conditions: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Javadoc — `SearchStrategy`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html
- Spring Boot 3.3 Javadoc — `ConditionalOnBean` (for comparison with present-bean conditions): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
