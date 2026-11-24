# @ConditionalOnMissingBean: Choosing a Default Bean When No Candidate Exists

## Learning Objectives

After this lesson, you will be able to explain why Spring Boot provides a default bean while still prioritizing beans declared by the application; accurately determine when `@ConditionalOnMissingBean` matches or does not match; build auto-configurations that can back off in favor of user configuration; and test both branches using `ApplicationContextRunner`.

## 1. The Problem: Providing a Default While Allowing Replacement

A library or starter may want to provide a ready-to-use `GreetingService` so the application can run right away. However, an application using the library may want to define its own `GreetingService`. If the library always registers the default bean, the context can end up with two beans of the same type; a type-based dependency injection point can encounter `NoUniqueBeanDefinitionException`.

`@ConditionalOnMissingBean` is a condition provided by **Spring Boot Auto-configuration**. When the condition is evaluated, Spring Boot registers the conditional bean only if **no bean matching the check criteria is found** in the `BeanFactory` within the search scope.

Examples of design intent:

- The application **does not declare** `GreetingService`: auto-configuration registers `defaultGreetingService`.
- The application **already declares** `GreetingService`: auto-configuration skips the default bean so the application uses its custom version.
- The application **already has multiple** `GreetingService` beans: the "missing bean" condition still does not match; the annotation does not automatically resolve choosing a single bean for injection.

This is a mechanism that decides **whether to register a bean definition while building the application context**. It is not a Java variable `null` check, does not monitor whether a bean is removed after startup, and is not a mechanism for dynamically swapping beans at method invocation time.

## 2. Basic Declaration

A common pattern in auto-configuration (the snippet below illustrates how to declare it and is not a standalone Java file):

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return name -> "Hello, " + name;
    }
}
~~~

Suppose `GreetingService` is an interface with the method `String greet(String name)`. The condition asks: "In the inspected scope, is there already a bean of type `GreetingService`?" If not, Spring registers the default bean. If one already exists, the `defaultGreetingService()` method is not used to create that bean.

You can omit the type argument when the annotation is placed **directly on a `@Bean` method**:

~~~java
@Bean
@ConditionalOnMissingBean
GreetingService defaultGreetingService() {
    return name -> "Hello, " + name;
}
~~~

Here, if `value`, `type`, or `name` is not specified, the type to check is inferred from the **declared return type** of the method (`GreetingService`). You should declare a sufficiently specific return type. Declaring `Object` or an overly general type can prevent Spring Boot from recognizing the right bean type to check at condition evaluation time.

**Important distinction:** the method name `defaultGreetingService` usually becomes the bean name, but `@ConditionalOnMissingBean(GreetingService.class)` checks by **type**, not merely whether that bean name already exists. A bean named `myGreetingService` of the same type will still cause the fallback to be skipped.

## 3. How Does Spring Boot Decide?

Simplified flow when an application uses auto-configuration:

1. Spring processes bean definitions from the application configuration (`@Configuration`, `@Bean`, component scan, etc.).
2. When processing bean definitions in auto-configuration, `OnBeanCondition` evaluates `@ConditionalOnMissingBean` based on **the bean definitions that have been processed up to that point**.
3. Spring Boot looks up beans according to the specified criteria: type, name, or annotation, taking into account the parent–child context hierarchy per `search`.
4. If **no bean satisfies any of the specified presence criteria**, the condition matches and the default bean definition is added to the context.
5. If a matching bean already exists, the default branch is not registered. Singleton instantiation and dependency injection then follow the normal bean lifecycle afterward.

| Situation when evaluating the condition for type `GreetingService` | Register fallback? | Reason |
| --- | --- | --- |
| No `GreetingService` bean yet | Yes | Missing candidate of the right type |
| One `customGreetingService` bean of the right type exists | No | Custom bean already satisfies the criterion |
| Two beans of the same type exist, one marked `@Primary` | No | Count is greater than 0; `@Primary` does not make beans "non-existent" |
| Only a bean named `defaultGreetingService` of a **different type** exists | Yes if checking by type | Matching name alone is not enough to satisfy a type check |
| A bean of the same type exists in the parent context, default `search` | No | Default searches the parent context as well |

The condition can inspect multiple criteria, and **does not require a single bean to satisfy all criteria**: finding a bean that satisfies even one presence requirement can cause the "missing" condition to be rejected. Therefore, keep criteria minimal, explicit, and intentional.

## 4. Practical Verification Example with Java 17+ and Spring Boot 3.x

`ApplicationContextRunner` creates small, isolated application contexts, allowing you to test auto-configuration without starting a web server. The following example is **a complete Java test file**, using JUnit Jupiter and AssertJ from `spring-boot-starter-test`.

Save it at `src/test/java/example/boot/condition/MissingBeanFallbackTest.java`:

~~~java
package example.boot.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class MissingBeanFallbackTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenNoUserBeanExists() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("An"))
                    .isEqualTo("Hello, An");
            assertThat(context.containsBean("defaultGreetingService")).isTrue();
        });
    }

    @Test
    void backsOffWhenUserProvidesAService() {
        contextRunner
                .withUserConfiguration(CustomGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class).greet("An"))
                            .isEqualTo("Xin chào, An");
                    assertThat(context.containsBean("defaultGreetingService")).isFalse();
                });
    }

    @Test
    void doesNotAddDefaultWhenTwoUserServicesExist() {
        contextRunner
                .withUserConfiguration(TwoGreetingServicesConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(GreetingService.class))
                            .hasSize(2);
                    assertThat(context.containsBean("defaultGreetingService")).isFalse();
                });
    }

    interface GreetingService {
        String greet(String name);
    }

    @AutoConfiguration
    static class GreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        GreetingService defaultGreetingService() {
            return name -> "Hello, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "Xin chào, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoGreetingServicesConfiguration {

        @Bean
        GreetingService englishGreetingService() {
            return name -> "Hello, " + name;
        }

        @Bean
        GreetingService vietnameseGreetingService() {
            return name -> "Xin chào, " + name;
        }
    }
}
~~~

**Prerequisites to run:** a Spring Boot project with `spring-boot-autoconfigure` on the classpath and the test dependency `org.springframework.boot:spring-boot-starter-test`. With Gradle (Groovy DSL), the test dependency section can be written as:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

When the project manages versions through the Spring Boot plugin or BOM, you do not need to manually specify the starter version above. Run the test in the corresponding project:

~~~text
# Linux/macOS
./gradlew test --tests "example.boot.condition.MissingBeanFallbackTest"

# Windows
gradlew.bat test --tests "example.boot.condition.MissingBeanFallbackTest"
~~~

**Results to verify:** all three tests pass. The first test proves the fallback is created and returns `Hello, An`; the second test proves the user bean is selected and returns `Xin chào, An`; the third test proves that having two user beans also prevents the fallback from being created. The example uses assertions and **does not print those strings to stdout**, so the exact Gradle output depends on logging and test report configuration.

The configuration classes in the test are declared as nested classes to keep the example in a single file and are loaded explicitly by `ApplicationContextRunner`. When writing a real starter, separate the auto-configuration into an appropriate production class and register it for Spring Boot auto-discovery.

## 5. Adding Auto-Configuration to a Library/Starter

In Spring Boot 3.x, the library's `@AutoConfiguration` classes are listed, one fully qualified name per line, in the resource:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example file content after creating a production class `example.boot.autoconfigure.GreetingAutoConfiguration`:

~~~text
example.boot.autoconfigure.GreetingAutoConfiguration
~~~

`@AutoConfiguration` is intended to be loaded through the imports file, and must not be accidentally loaded again via component scan. Spring Boot processes auto-configurations after beans defined by the user application, giving the fallback a chance to see custom configuration before deciding whether to register.

If another auto-configuration also provides a related bean type, you must specify the bean definition registration order. For example, `@AutoConfiguration(after = OtherAutoConfiguration.class)` lets you place the fallback after the configuration providing that other bean. **Auto-configuration ordering is the processing order of bean definitions, not a guarantee of bean object initialization order.**

## 6. Parameters and Check Scopes to Know

| Syntax / Attribute | Meaning | When to Use |
| --- | --- | --- |
| `@ConditionalOnMissingBean(MyService.class)` / `value` | Missing bean by class/type | Common fallback; usually the preferred choice |
| `@ConditionalOnMissingBean(type = "com.example.MyService")` | Missing bean by class name string | When you need to reference a type by name |
| `@ConditionalOnMissingBean(name = "myService")` | Missing bean with the specified name | When the intent truly depends on the bean name |
| `annotation = SomeMarker.class` | Missing bean carrying the corresponding annotation | Specialized configuration by marker |
| `search = SearchStrategy.CURRENT` | Check only the current context | Parent–child context setups where a child needs its own fallback |
| `search = SearchStrategy.ALL` | Check both the current context and parent contexts | Default behavior, avoids duplicates when the parent already provides the bean |
| `ignored` / `ignoredType` | Ignore certain bean types during lookup | Advanced cases, require a clear reason |
| `parameterizedContainer` | Recognize types wrapped in a specified generic container | E.g., treating `NameRegistration<Name>` as a candidate for `Name` when configured |

In typical applications, checking by **the service type that consumers need** is easiest to understand. Checking by name can cause the fallback to still appear even if the user registered a bean of the same type under a different name; type-based injection points can then become ambiguous.

If you combine `value`, `name`, or other criteria, remember that the condition only matches when all "missing" requirements are satisfied. Do not assume a bean must match both the name and the type to count as "already existing."

### Parent–Child Context Scope

The default is `search = SearchStrategy.ALL`. In an application with a parent context, a `GreetingService` in the parent can prevent the fallback in the child from **being registered**. Only use `SearchStrategy.CURRENT` when each context truly needs its own instance and that behavior is explicitly designed. Do not change the search strategy to mask a bean structure bug.

## 7. Distinguishing from Other Annotations and Bean Selection Mechanisms

- `@ConditionalOnBean(Foo.class)`: registers the configuration piece only when a matching `Foo` bean **already exists**.
- `@ConditionalOnMissingBean(Foo.class)`: registers the fallback only when a matching `Foo` bean **does not exist yet**.
- `@Primary`: prioritizes **one bean among existing beans** when type-based injection encounters multiple candidates; it does not decide whether to create a fallback.
- `@Qualifier`: specifies a dependency injection candidate; it does not replace checking whether a bean already exists.
- `@ConditionalOnProperty`: depends on configuration properties; can be combined with `@ConditionalOnMissingBean` when you want both a feature toggle and a mechanism allowing users to replace the bean.
- `spring.main.allow-bean-definition-overriding`: controls overriding **definitions with duplicate names**; it is not a fallback design pattern and should not be used to work around having multiple beans of the same type.

Example requiring both "feature is enabled" and "no custom service exists yet" (illustrative snippet inside auto-configuration):

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return name -> "Hello, " + name;
}
~~~

If `app.greeting.enabled=false`, the fallback is disabled even when there is no `GreetingService`; if the property allows it but the user has already provided a service, the fallback is also skipped.

## 8. Common Mistakes and Troubleshooting

1. **Placing the condition in user configuration and assuming all other beans are already present.** The condition only sees bean definitions processed **up to evaluation time**. For reusable fallbacks, prefer placing them in auto-configuration. If depending on another auto-configuration, declare the appropriate ordering.
2. **Writing a condition by name when the requirement is to check by type.** A different name can still produce a second bean implementing the same interface. Fix by using `@ConditionalOnMissingBean(MyService.class)` when the goal is a default implementation for a service type.
3. **Declaring a `@Bean` returning `Object` or an overly generic interface.** Spring Boot inspects type information declared/known at processing time. Declare a meaningful return type and test the branch with a custom bean.
4. **Assuming `@Primary` makes the "missing" condition match.** Having any matching bean still counts as "already present"; `@Primary` only affects how candidates are chosen during injection.
5. **Confusing a bean condition with whether the bean has been instantiated.** A matching bean definition can block the fallback before the corresponding object is ever created.
6. **Overlooking a bean in the parent context.** Check `search` and the context hierarchy if the expected fallback is not registered.
7. **Forgetting to register the library's auto-configuration in the imports file.** In that case the class may not be auto-loaded by Boot; do not misdiagnose this as the "missing" condition failing to work.

To investigate, run the application with the `--debug` option and check the **Condition Evaluation Report**: the matched/unmatched conditions section usually shows which bean caused `OnBeanCondition` not to match. In tests, you can use `ConditionEvaluationReportLoggingListener` with `ApplicationContextRunner` to print the report when needed. Check the recorded bean names and types, then compare them against the timing and scope of auto-configuration processing.

## 9. Knowledge Self-Check

**Question 1.** An auto-configuration declares `@ConditionalOnMissingBean(PaymentGateway.class)`. The application defines a `stripeGateway` bean of type `PaymentGateway`. Will the default bean be created?

**Answer:** No. The condition checks by **type**, so the name `stripeGateway` does not cause that bean to be ignored.

**Question 2.** There are two `PaymentGateway` beans, one of which is `@Primary`. Will the missing-bean annotation register a fallback to "provide one more option"?

**Answer:** No. Two beans already exist. `@Primary` only helps select a bean when injecting by type.

**Question 3.** Why should you write tests both when no user bean exists and when a user bean exists?

**Answer:** The first branch verifies that the default is provided; the second verifies that the library actually **backs off** so user configuration wins. Testing only one branch can miss processing-order bugs or wrong check criteria.

## 10. Key Takeaways When Applying

`@ConditionalOnMissingBean` helps auto-configuration provide a default **only when no matching bean exists yet**. Clearly identify the service type to check, ensure application beans are processed before the fallback, declare ordering if depending on another auto-configuration, and verify both branches with `ApplicationContextRunner`. When multiple beans of the same type exist, solve candidate selection with an appropriate injection model; do not expect the "missing" annotation to pick one for you.

### Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — @ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
