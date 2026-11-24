# Combining the Condition Report with the Actual Bean Inventory in ApplicationContext

## 1. Why Do You Need to Look at Both Sources Together?

When a Spring Boot bean does not appear as expected, looking only at the **Condition Evaluation Report** is often not enough. The condition report explains why a configuration class or `@Bean` method was evaluated as a match or no-match. Meanwhile, the bean inventory in **ApplicationContext** shows which beans are actually registered in the context, along with their names, types, scopes, and related dependencies.

The two sources answer two different questions:

- **Condition report:** Which conditions did Spring Boot evaluate? Which ones matched, which ones did not match, and what were the specific messages?
- **Bean inventory:** Which beans exist in the context under inspection? What are their names, types, where were they defined, and which beans do they depend on?

Combining them bridges the gap from configuration cause to bean registration result. For example, the report shows `CacheAutoConfiguration#cacheManager` matched; the bean inventory confirms there is a `cacheManager` bean of type `CacheManager`. If the condition matched yet the bean is absent from the inventory, you need to check condition scope, bean name, auto-configuration ordering, bean creation errors, and parent–child contexts.

**Do not conflate the two concepts:** a condition match does not prove an object was instantiated successfully. A bean definition may be registered while the instance is still lazy; instantiation can happen later and fail when used. Conversely, a bean may come from user configuration or a parent context rather than directly from the auto-configuration under inspection.

This article uses **Spring Boot 3.5.x, Spring Framework 6.2, and Java 17+** for illustration. Internal APIs and Actuator formats should be verified against your project's version when upgrading.

## 2. What Does the Condition Evaluation Report Contain?

Spring Boot stores condition evaluation outcomes in the class:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport
~~~

The report records conditions applied to a source such as:
- An auto-configuration class name, e.g., `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`;
- A bean configuration method, e.g., `SomeAutoConfiguration#someService`;
- Individual conditions, e.g., `OnClassCondition`, `OnBeanCondition`, `OnPropertyCondition`, or application-authored conditions.

Important APIs in Spring Boot 3.5:

| API | Meaning |
| --- | --- |
| `ConditionEvaluationReport.find(beanFactory)` | Finds the report already attached to BeanFactory; may return `null` if none exists |
| `ConditionEvaluationReport.get(beanFactory)` | Retrieves the report or creates a new report for BeanFactory |
| `getConditionAndOutcomesBySource()` | Map of condition outcomes grouped by source class/method |
| `ConditionAndOutcomes.isFullMatch()` | `true` when all outcomes in the source matched |
| `ConditionAndOutcome.getOutcome()` | Retrieves the `ConditionOutcome` of a single condition |
| `ConditionOutcome.isMatch()` | Whether that specific condition matched |
| `ConditionOutcome.getMessage()` | Reason provided by the condition |
| `getExclusions()` | List of classes excluded from auto-configuration evaluation |
| `getUnconditionalClasses()` | List of classes evaluated that had no conditions |

One source can have multiple conditions. For instance, an auto-configuration class matches `@ConditionalOnClass`, while a bean method does not match `@ConditionalOnProperty`. Therefore, read **each individual outcome**, not just searching for the word "positive".

### Distinguishing positiveMatches and negativeMatches

The condition report typically has three main groups:

- **Positive matches:** sources whose conditions matched.
- **Negative matches:** sources with at least one unmatched condition. Within each source, `notMatched` describes the failing conditions, while `matched` lists conditions that passed.
- **Unconditional classes:** classes that required no conditions to enter the configuration process.

A source appearing in `negativeMatches` does not mean every condition on that source failed. Some conditions may have matched while only one condition failed.

Abbreviated example:

~~~json
{
  "positiveMatches": {
    "example.CacheAutoConfiguration#cacheManager": [
      {
        "condition": "OnClassCondition",
        "message": "Cache API found"
      },
      {
        "condition": "OnPropertyCondition",
        "message": "Property demo.cache.enabled matched"
      }
    ]
  },
  "negativeMatches": {
    "example.MetricsAutoConfiguration#metricsPublisher": {
      "notMatched": [
        {
          "condition": "OnBeanCondition",
          "message": "did not find any beans of type MeterRegistry"
        }
      ],
      "matched": [
        {
          "condition": "OnClassCondition",
          "message": "required metrics API found"
        }
      ]
    }
  }
}
~~~

This is illustrative JSON to explain the structure; actual messages are generated by specific conditions and can vary by version, classpath, and configuration.

## 3. What Is the Bean Inventory in ApplicationContext?

Spring manages beans in a **BeanFactory**, usually accessed via `ApplicationContext`. You can list beans by name, by type, or read bean definition metadata.

Basic APIs:

| API | Information | Notes |
| --- | --- | --- |
| `getBeanDefinitionNames()` | Names of bean definitions in the current BeanFactory | Does not automatically include parent context; does not include all singletons registered directly outside bean definitions |
| `getBeanDefinition(name)` | Definition metadata: scope, lazy-init, resource, factory method, role | Only works for beans with a definition in the current factory |
| `getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` | Bean names matching type, including subclasses | Can control whether prototypes and eager FactoryBean initialization are considered |
| `getType(name)` | Expected bean type | May fail to determine type and return `null`; FactoryBean introspection may require initializing the factory |
| `getBeansOfType(type)` | Map of names and instances by type | May instantiate lazy/prototype beans and cause side effects |
| `containsBean(name)` | Whether a bean can be looked up by name in the factory/context | Does not prove an instance was already created beforehand |

### Bean Definition vs. Bean Instance

This is a critical diagnostic distinction:

- **Registered bean definition:** Spring knows how to create the bean, though the instance may not exist yet.
- **Initialized singleton:** the singleton instance has been created and stored in the context.
- **Prototype:** each request can create a new instance.
- **Lazy singleton:** only creates an instance upon an appropriate access.
- **FactoryBean:** the factory itself and the object produced by the factory are two distinct concepts.

`getBeanDefinitionNames()` returns definition names, not a list proving every instance exists. If you need to verify an actual instance for a specific type, you can use `getBeanNamesForType(...)` to find names and then deliberately call `getBean(name)`. Calling `getBean` can trigger lazy bean initialization or prototype creation, so avoid casually scanning an entire production context with it.

## 4. How Are the Two Sources Combined?

In Spring Boot Actuator, two endpoints have distinct roles:

| Endpoint | Content | Used to Answer |
| --- | --- | --- |
| `GET /actuator/conditions` | Condition report by application context | Why did an auto-configuration or bean method match or not match? |
| `GET /actuator/beans` | Bean inventory by application context | Which beans are registered, and what are their names/types/scopes/dependencies? |

### 4.1. Enabling the Endpoints

Add the Actuator dependency if the project does not have it yet:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

In `application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info,conditions,beans
~~~

By default, Actuator does not expose all endpoints over HTTP. The configuration above explicitly exposes `conditions` and `beans` alongside common endpoints. If using Spring Security, configure appropriate authorization for management paths.

Send requests in a local environment:

~~~bash
curl http://localhost:8080/actuator/conditions
curl http://localhost:8080/actuator/beans
~~~

If the application changes `management.endpoints.web.base-path`, port, or uses a separate management server, the actual URLs change accordingly.

### 4.2. Reading the conditions Endpoint

The data typically looks like:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "example.CacheAutoConfiguration#cacheManager": [
          {
            "condition": "OnPropertyCondition",
            "message": "Property demo.cache.enabled matched"
          }
        ]
      },
      "negativeMatches": {},
      "unconditionalClasses": [],
      "parentId": null
    }
  }
}
~~~

Parts to observe:
- `contexts`: map of ApplicationContexts by ID.
- `positiveMatches`: sources with matching conditions.
- `negativeMatches`: sources with unmatched conditions, including matched/notMatched details.
- `unconditionalClasses`: unconditional classes.
- `parentId`: parent context ID, if any.

### 4.3. Reading the beans Endpoint

Abbreviated example:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "cacheManager": {
          "aliases": [],
          "scope": "singleton",
          "type": "example.CacheManager",
          "resource": "example.CacheAutoConfiguration",
          "dependencies": []
        }
      },
      "parentId": null
    }
  }
}
~~~

The bean inventory provides:
- `beans`: map keyed by bean name;
- `aliases`: aliases;
- `scope`: scope;
- `type`: fully qualified type name;
- `resource`: definition resource, if available;
- `dependencies`: dependent beans;
- `parentId`: parent context.

The JSON above only illustrates the data shape, not an actual response from a running application.

### 4.4. Matching the Two Reports by Source and Bean Name

With the method:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo.cache",
        name = "enabled",
        havingValue = "true")
CacheService cacheService() {
    return new CacheService();
}
~~~

If the bean name is not customized, the default name is usually `cacheService`, corresponding to source `example.CacheAutoConfiguration#cacheService` in the condition report.

How to cross-reference:
1. Find source `CacheAutoConfiguration#cacheService` in `positiveMatches`.
2. Read each condition's message to see why the method was allowed to register.
3. Find `cacheService` in `beans` of **the same context ID**.
4. Inspect `type`, `scope`, `resource`, and `dependencies`.
5. If the bean name is set explicitly, e.g., `@Bean("primaryCache")`, look up `primaryCache` in the inventory; the method name is no longer the default bean name.
6. If the source is a configuration class name, that does not mean the class itself is the business bean you are looking for. Look for `@Bean` methods inside the class and their corresponding bean names/return types.

**There is no automatic one-to-one join for every case.** One class condition can enable multiple beans; a bean can come from user configuration; a `@Bean` name can be customized; a factory method can return an interface or proxy. Therefore, cross-check source, bean name, type, and context rather than doing mechanical string matching.

## 5. Java Example: Reading Both Condition Report and Bean Definitions in the Same Context

Spring Boot 3.5 provides APIs to access the report directly. The following example creates an `ApplicationRunner` that prints condition outcomes and bean definitions to the console after the ApplicationContext has refreshed.

Create file **`src/main/java/example/AutoConfigurationDiagnostics.java`**:

~~~java
package example;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class AutoConfigurationDiagnostics implements ApplicationRunner {

    private final ConfigurableApplicationContext context;

    public AutoConfigurationDiagnostics(
            ConfigurableApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        ConfigurableListableBeanFactory beanFactory =
                context.getBeanFactory();

        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(beanFactory);

        System.out.println("=== CONDITION REPORT ===");

        if (report == null) {
            System.out.println("No ConditionEvaluationReport found");
        }
        else {
            report.getConditionAndOutcomesBySource()
                    .forEach((source, outcomes) -> {
                        outcomes.forEach(conditionAndOutcome -> {
                            var outcome = conditionAndOutcome.getOutcome();

                            System.out.printf(
                                    "SOURCE=%s | RESULT=%s | MESSAGE=%s%n",
                                    source,
                                    outcome.isMatch() ? "MATCH" : "NO_MATCH",
                                    outcome.getMessage());
                        });
                    });

            System.out.println(
                    "EXCLUDED_AUTO_CONFIGURATIONS="
                            + report.getExclusions());
        }

        System.out.println("=== BEAN DEFINITIONS ===");

        for (String beanName : context.getBeanDefinitionNames()) {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition(beanName);

            Class<?> type = context.getType(beanName);

            String scope = definition.getScope();
            if (scope == null || scope.isBlank()) {
                scope = "singleton";
            }

            System.out.printf(
                    "BEAN=%s | TYPE=%s | SCOPE=%s | RESOURCE=%s | FACTORY_METHOD=%s%n",
                    beanName,
                    type == null ? "<unknown>" : type.getName(),
                    scope,
                    definition.getResourceDescription(),
                    definition.getFactoryMethodName());
        }
    }
}
~~~

**How it works:**

- `ConfigurableApplicationContext.getBeanFactory()` retrieves the BeanFactory of the current context.
- `ConditionEvaluationReport.find(beanFactory)` locates the report recorded by Boot; if not found, it returns `null`.
- `getConditionAndOutcomesBySource()` returns outcomes by class/method.
- `ConditionAndOutcomes` can be iterated in a loop; `ConditionOutcome.isMatch()` and `getMessage()` provide status and reason.
- `getExclusions()` displays excluded auto-configuration classes.
- `context.getBeanDefinitionNames()` lists bean definitions belonging to **the current context**.
- `getBeanDefinition(beanName)` provides scope, resource description, and factory method.
- `context.getType(beanName)` attempts to determine the bean type; if it cannot be inferred, the example prints `<unknown>`.

For example, the console will contain lines such as:

~~~text
=== CONDITION REPORT ===
SOURCE=example.CacheAutoConfiguration#cacheService | RESULT=MATCH | MESSAGE=...
EXCLUDED_AUTO_CONFIGURATIONS=[]
=== BEAN DEFINITIONS ===
BEAN=cacheService | TYPE=example.CacheService | SCOPE=singleton | RESOURCE=... | FACTORY_METHOD=cacheService
~~~

This is an **illustrative format**; messages, ordering, and bean counts depend on the classpath, profiles, conditions, version, and application configuration. Do not expect the entire output of a real application to match the snippet verbatim.

### Limitations of the Code Snippet

1. `getBeanDefinitionNames()` only lists definitions in the current factory; it does not automatically list parent contexts.
2. Singletons registered directly via APIs outside bean definitions may not appear in the definition list.
3. `getType(name)` may not be able to determine the type for some FactoryBeans or factory methods.
4. The code reads metadata without calling `getBean(name)` to deliberately initialize each bean. Thus it does not prove every lazy bean has instantiated successfully.
5. Adding this `ApplicationRunner` to production can print many class names and internal structure; enable only for diagnostic purposes and control log access.

## 6. Inspecting Beans by Type and Context Hierarchy

### 6.1. Finding Beans by Type Without Eager Initialization

Once you know the type to check, you can use:

~~~java
String[] names = context.getBeanNamesForType(
        CacheService.class,
        true,
        false);
~~~

Parameters:
- `includeNonSingletons=true`: includes prototypes and other non-singleton scopes.
- `allowEagerInit=false`: does not require initializing eager FactoryBeans just to determine types.

The result is bean names matching the type, not an instance map. For a FactoryBean whose produced object type cannot be determined without initializing the factory, search results may be incomplete. If you need to confirm a real instance, access the bean deliberately and handle the possibility that bean creation triggers side effects/errors.

### 6.2. BeanFactoryUtils with Parent–Child Contexts

An ApplicationContext can have a parent context. For example, a web application may have a separate management context or an application may create multiple child contexts.

Standard `ListableBeanFactory` methods only check beans in the current factory. To include bean names from ancestor factories, Spring Framework provides:

~~~java
import org.springframework.beans.factory.BeanFactoryUtils;
import org.springframework.context.ConfigurableApplicationContext;

// context is a ConfigurableApplicationContext.
String[] allNames =
        BeanFactoryUtils.beanNamesIncludingAncestors(context);
~~~

If you want to filter by type:

~~~java
String[] cacheNames =
        BeanFactoryUtils.beanNamesForTypeIncludingAncestors(
                context,
                CacheService.class,
                true,
                false);
~~~

This approach inspects beans across the hierarchy. However, during diagnosis you must still note which context owns a bean, since a same-named bean in a child context can shadow a bean in the parent under Spring's resolution rules.

In Condition Evaluation Report, `getParent()` lets you follow reports up to the parent factory. With Actuator, both `/conditions` and `/beans` return a `contexts` map along with `parentId`. **Match reports and bean inventories by exact context ID**, rather than comparing a child context's conditions against a parent context's bean list and concluding a bean is missing.

## 7. Testing with ApplicationContextRunner

`ApplicationContextRunner` lets you create a small context with controlled properties and auto-configurations. It is a great way to verify simultaneously:
- whether the condition outcome matches;
- whether the bean definition is registered;
- whether the expected bean name and type appear in the context.

### 7.1. Sample Auto-Configuration Test Setup

Create file **`src/test/java/example/ConditionAndBeanInventoryTests.java`**:

~~~java
package example;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionAndBeanInventoryTests {

    static class CacheService {
    }

    @AutoConfiguration
    static class CacheAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.cache",
                name = "enabled",
                havingValue = "true")
        CacheService cacheService() {
            return new CacheService();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CacheAutoConfiguration.class));

    private Map.Entry<String,
            ConditionEvaluationReport.ConditionAndOutcomes> cacheOutcome(
                    ConditionEvaluationReport report) {

        return report.getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith("#cacheService"))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void matchingConditionHasCorrespondingBeanDefinition() {
        runner.withPropertyValues("demo.cache.enabled=true")
                .run(context -> {
                    ConditionEvaluationReport report =
                            ConditionEvaluationReport.find(
                                    context.getBeanFactory());

                    assertThat(report).isNotNull();

                    var outcomes = cacheOutcome(report).getValue();
                    assertThat(outcomes.isFullMatch()).isTrue();

                    assertThat(context.getBeanDefinitionNames())
                            .contains("cacheService");

                    assertThat(context.getBeanNamesForType(
                            CacheService.class, true, false))
                            .containsExactly("cacheService");
                });
    }

    @Test
    void nonMatchingConditionDoesNotRegisterBeanDefinition() {
        runner.withPropertyValues("demo.cache.enabled=false")
                .run(context -> {
                    ConditionEvaluationReport report =
                            ConditionEvaluationReport.find(
                                    context.getBeanFactory());

                    assertThat(report).isNotNull();

                    var outcomes = cacheOutcome(report).getValue();
                    assertThat(outcomes.isFullMatch()).isFalse();

                    assertThat(context.getBeanDefinitionNames())
                            .doesNotContain("cacheService");

                    assertThat(context.getBeanNamesForType(
                            CacheService.class, true, false))
                            .isEmpty();
                });
    }
}
~~~

The test project needs `spring-boot-starter-test`; auto-configuration and `ConditionEvaluationReport` belong to the Spring Boot dependencies brought in by the test starter. The example fits Spring Boot 3.5.x as it uses `ConditionAndOutcomes.isFullMatch()`.

Run:

~~~bash
./mvnw test -Dtest=ConditionAndBeanInventoryTests
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=ConditionAndBeanInventoryTests'
~~~

Or using an installed Maven binary:

~~~bash
mvn test -Dtest=ConditionAndBeanInventoryTests
~~~

**Expected result:** two tests PASS:
- When `demo.cache.enabled=true`, the `#cacheService` source report is a full match and bean name `cacheService` exists in the inventory.
- When the property is `false`, the source is not a full match and the bean definition is not registered.

No fixed stdout string is specified because Maven/Surefire output formatting varies by version. The tests verify conditions and the bean list directly with assertions.

### 7.2. Why Not Only Assert hasBean?

An assertion such as:

~~~java
assertThat(context).hasBean("cacheService");
~~~

confirms the bean name exists, but does not explain **why** the bean was registered. Conversely, asserting only `outcomes.isFullMatch()` does not verify that the bean inventory actually contains the definition. Combining both assertions tests the link between the condition decision and the registration result.

## 8. Reading Real-World Cases When the Two Sources Disagree

| Condition Report | Bean Inventory | Interpretation and Next Step |
| --- | --- | --- |
| Method source MATCH | Matching bean exists | Condition passed and bean definition appeared; check scope/instance next if errors occur at usage time |
| Class source MATCH | Business bean missing | Configuration class was accepted, but bean method may have its own condition, not declare the target bean, or use a different bean name |
| Method source MATCH | Same-named bean missing | Check custom `@Bean` name, context ID, FactoryBean type, and overridden bean definitions |
| Method source NO_MATCH | No bean | Usually expected; read messages in `notMatched` to see the failed condition |
| Method source NO_MATCH | Bean of same type still exists | Bean may come from user configuration, another auto-configuration, parent context, or manual registration |
| Method source MATCH | Bean definition present, yet accessing bean fails | Conditions passed; investigate constructor, dependencies, init methods, external services, and stack trace |
| Source missing from report | Bean exists | Bean may be created by user configuration, component scan, manual registration, or a source outside the report section being inspected |
| Source missing from report and bean missing | Insufficient data | Check whether class is an auto-configuration candidate, whether it is excluded, and whether context and version are right |

### Common Root Causes

**1. Class-level and method-level conditions differ**

For example, `CacheAutoConfiguration` satisfies `@ConditionalOnClass`, yet `cacheManager()` also has `@ConditionalOnProperty` and the property fails. Seeing a class-level positive match and concluding the bean must exist is wrong.

**2. Bean name does not match method name**

By default, the `@Bean` method name is usually the bean name. However, declaring:

~~~java
@Bean("primaryCache")
CacheService cacheManager() {
    return new CacheService();
}
~~~

results in `primaryCache` in the inventory, not `cacheManager`.

**3. Condition matched, yet bean instantiation failed**

Conditions are evaluated during configuration/bean definition registration. Constructors, dependencies, `@PostConstruct`, init methods, or external connections can fail when the instance is created. The condition report is not an object health check.

**4. Lazy bean has not been instantiated yet**

A bean definition may be in the inventory while the instance does not exist yet. Only when `getBean` is called does Spring create the instance. This is normal for `@Lazy`, global lazy-init, or prototypes.

**5. Bean lives in a different context**

Actuator returns multiple contexts by ID. A bean may live in the parent context or management context while the condition report being inspected is for a child context. Always cross-check `parentId` and context ID.

**6. Auto-configuration was excluded**

A class listed in `spring.autoconfigure.exclude`, `exclude`, or `excludeName` may bypass normal condition evaluation. In the `ConditionEvaluationReport` API, check `getExclusions()`. Do not expect every excluded class to appear in `positiveMatches` or `negativeMatches`.

**7. Auto-configuration ordering**

`@ConditionalOnBean` and `@ConditionalOnMissingBean` can depend on bean definitions processed earlier. If a configuration depends on a bean from another auto-configuration, configuration ordering can determine the outcome. Check `OnBeanCondition` messages, method sources, and `@AutoConfiguration(before/after)` ordering.

## 9. Recommended Diagnostic Workflow

When an expected bean is absent from the context, follow this sequence:

1. **Identify the context to inspect.** Note the context ID, display name, parent context, and active profiles.
2. **Locate the source in the condition report.** Look up the auto-configuration class and `@Bean` method; check whether the source is in positive or negative matches.
3. **Read all outcomes for the source.** For a negative source, inspect exactly which condition failed and which conditions matched.
4. **Check exclusions.** If the class was not evaluated, check `getExclusions()` or the debug report.
5. **Find the bean in the same context's inventory.** Use bean name, type, resource, factory method, and dependencies.
6. **Verify the actual name.** Check `@Bean("...")`, aliases, and factory method.
7. **Inspect the instance.** If the definition exists yet using the bean fails, capture the initialization stack trace or access the bean deliberately.
8. **Check parent–child contexts.** When needed, use `BeanFactoryUtils` or iterate each context.
9. **Re-test with ApplicationContextRunner.** Isolate properties, classpath, and user beans to reproduce the outcome.

### Enabling the Condition Evaluation Report via Debug

You can start the application with:

~~~bash
java -jar target/my-app.jar --debug
~~~

Spring Boot writes the **Conditions Evaluation Report** to logs, which is helpful when Actuator endpoints are not configured or the application does not start far enough to call an endpoint. On startup failures, read the condition report alongside the stack trace; the condition report explains configuration decisions, whereas the stack trace explains bean creation errors.

In auto-configuration tests, you can use `ConditionEvaluationReportLoggingListener` to log the report:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // Place assertions on beans and conditions here.
        });
~~~

Imports in Boot 3.5:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

This listener is designed as an `ApplicationContextInitializer`; do not share a single initializer instance across multiple context instances.

## 10. Notes When Using Actuator in Real Environments

The `/actuator/conditions` and `/actuator/beans` endpoints are very helpful, yet contain internal details:
- class names, bean names, and library names;
- context structure;
- dependencies between beans;
- resource descriptions that can hint at configuration locations;
- condition details and related properties.

Do not expose these endpoints broadly to the Internet. In production:
1. Expose only necessary endpoints.
2. Restrict via management port/network or firewall when appropriate.
3. Use Spring Security to require administrative privileges.
4. Avoid logging condition messages containing sensitive configuration data.
5. Use diagnostic log levels appropriately and turn them off once investigation finishes.
6. When sharing reports outside the operations team, strip secrets or unnecessary internal names.

Endpoint exposure can be configured via:

~~~properties
management.endpoints.web.exposure.include=health,conditions,beans
~~~

However, exposure configuration only decides whether an endpoint is accessible over the web; it **does not set up authorization**. Protection policies must be configured separately.

## 11. Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| A positive match means the bean is already instantiated | Only indicates conditions matched; bean creation may happen later |
| Every positive class match must produce a business bean of the same name | Class conditions and method conditions have different scopes |
| The bean inventory only contains beans created by auto-configuration | It also includes beans from component scan, user configuration, imports, and manual registration |
| `getBeanDefinitionNames()` includes the parent context | Only the current factory; use `BeanFactoryUtils` or traverse the hierarchy |
| `getBeansOfType()` is a side-effect-free metadata read | It fetches instances, which can initialize lazy/prototype/FactoryBeans |
| `/actuator/conditions` is also a bean list | It is a condition report; the bean list is at `/actuator/beans` |
| A bean appearing in `/beans` means it initialized successfully | The endpoint describes bean metadata; scope/lazy and instantiation timing still matter |
| A negative match means all conditions failed | Possibly only one condition did not match while other conditions matched |
| A bean of the same type must have come from the auto-configuration under inspection | It may be provided by user config or another auto-configuration |

## 12. Self-Check Questions

**Question 1.** The condition report shows `MyAutoConfiguration#myService` as MATCH. Can you conclude the `MyService` instance was created successfully?

**Answer:** No. A match only indicates the conditions for that source passed. Check the bean definition in the inventory and inspect instance creation if the bean fails.

**Question 2.** How do `/actuator/conditions` and `/actuator/beans` differ?

**Answer:** `conditions` explains condition outcomes by class/method; `beans` lists bean metadata such as name, type, scope, resource, and dependencies.

**Question 3.** Where does a source with two matched conditions and one unmatched condition appear?

**Answer:** It belongs in `negativeMatches`; `notMatched` contains the failed condition, while `matched` still lists the two passing conditions.

**Question 4.** Why might `getBeanDefinitionNames()` miss a bean located in a parent context?

**Answer:** Because this API only inspects the current BeanFactory. Use `BeanFactoryUtils.beanNamesIncludingAncestors(...)` or iterate each context in the hierarchy.

**Question 5.** If `@Bean("primaryCache")` is on method `cacheManager()`, which name should you look for in Actuator beans?

**Answer:** Look for `primaryCache`, because the name was explicitly specified in the annotation.

**Question 6.** Why shouldn't you call `getBeansOfType(Object.class)` to inventory all production beans?

**Answer:** Because it retrieves instances, which can initialize lazy beans, prototypes, or FactoryBeans, causing side effects and altering application state during diagnosis.

## 13. Official References

- Spring Boot 3.5 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.5 API — `ConditionOutcome`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- Spring Boot 3.5 Actuator API — Conditions endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/conditions.html
- Spring Boot 3.5 Actuator API — Beans endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/beans.html
- Spring Framework 6.2 API — `ListableBeanFactory`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html
- Spring Framework 6.2 API — `BeanFactoryUtils`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/BeanFactoryUtils.html
- Spring Boot Reference — Creating Your Own Auto-configuration and ApplicationContextRunner: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
