# Asserting Single Bean, Missing Bean, Bean Names, and Object Identity

## 1. Goals of Spring ApplicationContext testing

When writing a Spring Boot auto-configuration or application configuration, verifying only that the context starts successfully is not enough. A configuration can start without errors yet still register the wrong number of beans, use the wrong names, create a default bean despite a custom bean being present, or return unexpectedly different instances.

Typical testing questions include:

- Does a bean of a given type exist?
- Is there **exactly one** bean of that type, or are there multiple candidates?
- When a feature is disabled, is the bean genuinely absent?
- Under what name is the bean registered? Are there aliases?
- Do lookup by type and lookup by name return **the same object**?
- Do two `getBean` calls return the same reference or create new instances?
- Does an application-provided bean make the auto-configuration yield?

Spring Test and Spring Boot Test provide several APIs to answer these questions. For isolated auto-configuration testing, the best fit is usually **`ApplicationContextRunner`** paired with **`AssertableApplicationContext`** and AssertJ.

This lesson uses Java 17 and Spring Boot 3.3.13 as an illustrative baseline. Examples can run in a standalone Maven project.

## 2. Distinguishing bean existence, bean definitions, and object instances

These three concepts are related but not synonymous.

### 2.1. Bean existence in ApplicationContext

A bean can be looked up by name or type:

~~~java
context.containsBean("reportClient");
context.getBean("reportClient");
context.getBean(ReportClient.class);
~~~

- `containsBean(name)` answers whether the context can look up a bean under that name.
- `getBean(name)` returns the instance, or throws `NoSuchBeanDefinitionException` if not found.
- `getBean(type)` looks up by type; if no bean exists it throws `NoSuchBeanDefinitionException`, and if multiple indistinguishable candidates exist it throws `NoUniqueBeanDefinitionException`.

When the goal is simply checking presence or absence, do not call `getBean` and catch exceptions. Using dedicated assertions makes test intent clearer.

### 2.2. Bean definitions and registered singletons

Spring manages beans via metadata/definitions and the instances created from them. Different APIs have different scopes:

| API | Meaning |
| --- | --- |
| `containsBean(name)` | Whether a bean can be looked up by name, including aliases and parent context beans |
| `containsLocalBean(name)` | Whether the bean exists in the current context, not just inherited from a parent |
| `containsBeanDefinition(name)` | Whether a bean definition with that name exists in the current bean factory |
| `getBeanDefinition(name)` | Retrieves definition metadata if the definition exists |
| `getSingleton(name)` | Retrieves an already created/registered singleton instance by name, or null if not yet created |

Do not use `containsBeanDefinition` as a complete substitute for checking bean existence. A singleton can be registered directly without a standard bean definition; conversely, a bean definition can exist while its instance has not yet been initialized due to lazy initialization.

For testing an auto-configuration contract, the question is usually whether the application can look up the bean. Therefore, prefer ApplicationContext assertions by name/type; inspect the definition or singleton registry only when that is specifically what needs verification.

### 2.3. Bean name is not object identity

A bean name is a lookup key in the container. Object identity is whether two variables point to **the exact same reference**.

Example:

~~~java
ReportClient byName = context.getBean("reportClient", ReportClient.class);
ReportClient byType = context.getBean(ReportClient.class);
~~~

Two variables can reference the same singleton bean:

~~~java
assertThat(byName).isSameAs(byType);
~~~

This is an identity check. `isEqualTo` only checks equality via `equals()`, which does not prove two variables point to the same object.

## 3. Choosing the right assertion API

With `ApplicationContextRunner`, the callback receives an `AssertableApplicationContext`. Spring Boot provides dedicated assertions:

~~~java
assertThat(context).hasBean("reportClient");
assertThat(context).doesNotHaveBean("reportClient");
assertThat(context).hasSingleBean(ReportClient.class);
assertThat(context).doesNotHaveBean(ReportClient.class);
~~~

Meaning:

| Assertion | What is verified |
| --- | --- |
| `hasBean("name")` | A bean can be looked up by name |
| `doesNotHaveBean("name")` | No bean can be looked up by name |
| `hasSingleBean(Type.class)` | Exactly one bean assignable to the type exists |
| `doesNotHaveBean(Type.class)` | No bean of that type exists |
| `context.getBean(type)` | Retrieves the bean by type after confirming cardinality |
| `context.getBean(name, type)` | Retrieves the bean by name and checks compatible type |

To verify the exact list of bean names, use the bean factory:

~~~java
String[] names =
        context.getBeanFactory().getBeanNamesForType(ReportClient.class);

assertThat(names).containsExactly("reportClient");
~~~

`getBeanNamesForType` returns bean definition/candidate names matching the type, without separate entries for each alias. To verify aliases, use `getAliases` or look up the alias via `getBean(alias)`.

Do not use `hasSingleBean` when the intent is to check a specific bean by name. Multiple valid beans of a type may exist; checking by name and checking cardinality by type are two distinct assertions.

## 4. Asserting exactly one bean by type

Suppose an application expects exactly one `ReportClient`:

~~~java
runner.run(context -> {
    assertThat(context).hasSingleBean(ReportClient.class);

    ReportClient client = context.getBean(ReportClient.class);
    assertThat(client.endpoint()).isEqualTo("https://reports.example.test");
});
~~~

`hasSingleBean` is more informative than merely calling `getBean(ReportClient.class)`. If two beans of the same type exist, `getBean(type)` throws `NoUniqueBeanDefinitionException`; the assertion clearly expresses the cardinality requirement right at the check line.

If multiple beans are allowed, verify the list of names:

~~~java
String[] names =
        context.getBeanFactory().getBeanNamesForType(ReportClient.class);

assertThat(names).contains("primaryReportClient", "archiveReportClient");
assertThat(names).hasSize(2);
~~~

Decide what the test is verifying:

- **At least one bean:** use `hasBean(name)` or assert the names array is non-empty.
- **Exactly one bean:** use `hasSingleBean(type)`.
- **Exact expected beans:** assert the list of names.
- **No bean:** use `doesNotHaveBean`.

Avoid weak assertions such as `assertThat(context.getBeansOfType(ReportClient.class)).isNotNull()`: an empty map is still non-null, so the test can pass even with zero beans.

## 5. Asserting missing beans

When a feature is disabled, an auto-configuration should typically not create the default service bean. Verify by both type and name:

~~~java
runner.withPropertyValues("acme.reports.enabled=false")
        .run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);
            assertThat(context).doesNotHaveBean("reportClient");
        });
~~~

Avoid checking absence solely by writing:

~~~java
assertThat(context.getBeanNamesForType(ReportClient.class)).isEmpty();
~~~

That approach is valid if the primary goal is confirming a type lookup yields nothing, but Spring Boot's assertions express intent more directly and produce clearer failure messages.

Also avoid catching arbitrary exceptions:

~~~java
assertThatThrownBy(() -> context.getBean(ReportClient.class))
        .isInstanceOf(Exception.class);
~~~

An exception could stem from bean initialization failure, broken dependencies, or ambiguity; such a test could pass for the wrong reason. If you must test the lookup API's exception, assert the exact exception type and set up a specific context.

## 6. Checking bean names and aliases

### 6.1. Default name from @Bean

If no name is specified, Spring uses the method name as the bean name:

~~~java
@Bean
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

The default bean name is `reportClient`.

You can specify an explicit name:

~~~java
@Bean("primaryReportClient")
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

In that case, the primary lookup name is `primaryReportClient`, not the method name `reportClient`.

### 6.2. Declaring multiple aliases

The `@Bean` annotation accepts multiple names; the first is the primary bean name, and the rest are aliases:

~~~java
@Bean(name = {"reportClient", "reports"})
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Testing:

~~~java
assertThat(context).hasBean("reportClient");
assertThat(context).hasBean("reports");

ReportClient primary =
        context.getBean("reportClient", ReportClient.class);
ReportClient alias =
        context.getBean("reports", ReportClient.class);

assertThat(alias).isSameAs(primary);
assertThat(context.getBeanFactory().getAliases("reportClient"))
        .contains("reports");
~~~

An alias does not create an extra bean instance. It is an alternative name to look up the same bean. Therefore `getBeanNamesForType(ReportClient.class)` typically lists only the canonical name `reportClient`, while `getAliases("reportClient")` returns the alias `reports`.

### 6.3. Distinguishing @Qualifier, @Primary, and bean names

- `@Qualifier` selects a matching candidate during dependency injection.
- `@Primary` marks a preferred candidate when multiple beans of the same type exist and injection requires a single candidate.
- A bean name is the container key used for lookup.
- An alias is an additional name for the same bean.

`@Primary` does not delete other beans, reduce the bean count, or guarantee `getBean(type)` has only one bean definition. If a test requires strictly one bean, verify the actual count rather than inferring it from successful injection.

## 7. Checking object identity: isSameAs and isNotSameAs

### 7.1. Equality differs from identity

Suppose `ReportClient` is a Java record:

~~~java
public record ReportClient(String endpoint) {
}
~~~

A record generates `equals()` and `hashCode()` based on its components. Two distinct instances with the same endpoint are still equal:

~~~java
ReportClient first = new ReportClient("https://reports.example.test");
ReportClient second = new ReportClient("https://reports.example.test");

assertThat(first).isEqualTo(second);
assertThat(first).isNotSameAs(second);
~~~

If you use `isEqualTo` to prove Spring returns the same singleton, the test can pass even if the container created two separate objects. Use `isSameAs` to test reference identity.

### 7.2. Verifying the same instance across two lookup paths

~~~java
ReportClient byName =
        context.getBean("reportClient", ReportClient.class);
ReportClient byType = context.getBean(ReportClient.class);

assertThat(byName).isSameAs(byType);
~~~

With an alias:

~~~java
ReportClient canonical =
        context.getBean("reportClient", ReportClient.class);
ReportClient alias =
        context.getBean("reports", ReportClient.class);

assertThat(alias).isSameAs(canonical);
~~~

Both assertions confirm that type, name, and alias lookups ultimately resolve to the same instance.

### 7.3. Verifying singleton scope

Spring creates singleton-scoped beans by default within an ApplicationContext. Two lookups of a singleton bean return the same object:

~~~java
ReportClient first = context.getBean(ReportClient.class);
ReportClient second = context.getBean(ReportClient.class);

assertThat(second).isSameAs(first);
~~~

Singleton here means one instance per bean definition per container, not one instance across the entire JVM. Two separate ApplicationContexts can hold two distinct singleton instances.

## 8. Distinguishing singleton and prototype

Prototype scope creates a new instance every time the container is asked for the bean:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Testing:

~~~java
ReportClient first = context.getBean(ReportClient.class);
ReportClient second = context.getBean(ReportClient.class);

assertThat(first).isNotSameAs(second);
assertThat(first).isEqualTo(second);
~~~

The two objects hold identical data so they are equal as records, yet they are two distinct references.

Notes:

- Singleton is Spring's default scope.
- Prototype creates a new object on each container lookup.
- Spring does not manage the full destruction lifecycle of a prototype bean after handing the object to the caller.
- If a prototype is injected directly into a singleton, the prototype is normally resolved only once when the singleton is created. To obtain a fresh instance per usage, use `ObjectProvider<T>`, `ObjectFactory<T>`, or an appropriate scoped proxy.

Example:

~~~java
@Component
class ReportJob {

    private final ObjectProvider<ReportClient> clients;

    ReportJob(ObjectProvider<ReportClient> clients) {
        this.clients = clients;
    }

    ReportClient newClientForJob() {
        return clients.getObject();
    }
}
~~~

If `ReportClient` is prototype-scoped, every call to `newClientForJob()` asks the provider for a new instance.

## 9. Checking beans in a parent context

ApplicationContexts can form a parent–child hierarchy. When looking up a bean by name or type, a child context can see beans inherited from its parent.

This creates a distinction:

- `containsBean(name)` may return true due to a bean in the parent.
- `containsLocalBean(name)` checks only the current context.
- `containsBeanDefinition(name)` checks only bean definitions in the current bean factory.
- `getBean(name)` may return the parent's instance if the child has no bean with that name.

If a test requires a bean to be created by the **child context's** auto-configuration, asserting only `containsBean` is not enough. Check `containsLocalBean`, the bean definition, or bean names in the local bean factory.

When listing types including ancestors, use `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)`. Meanwhile, `getBeanNamesForType` on the local bean factory checks beans owned by the current context.

For most simple auto-configuration tests, no parent context is needed. Add a parent only when the real application uses a hierarchical context structure and inheritance behavior is part of the contract under verification.

## 10. Not creating beans when a feature is disabled: auto-configuration example

Let's use a sample auto-configuration:

~~~java
@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean(name = {"reportClient", "reports"})
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

There are two conditions:

- `@ConditionalOnProperty` enables the default client when `acme.reports.enabled=true`; a missing property also enables it due to `matchIfMissing=true`.
- `@ConditionalOnMissingBean` allows the application to supply its own ReportClient; if that bean already exists, the default method is not applied.

In tests, we want to verify:

1. No property declared: the default bean exists.
2. `enabled=false`: no default bean exists.
3. Application declares a custom bean: the default bean yields.
4. Lookups by alias/name/type return the same singleton instance.
5. A prototype bean yields a new reference on each lookup.

This is the auto-configuration's contract; the tests do not need to launch an HTTP server or database.

## 11. Complete Maven example — Java 17, Spring Boot 3.3.13

### 11.1. Directory structure

~~~text
bean-assertion-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/demo/
            └── ReportsAutoConfigurationTests.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bean-assertion-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 11.3. ReportClient.java

**src/main/java/com/example/demo/ReportClient.java**

~~~java
package com.example.demo;

public record ReportClient(String endpoint) {
}
~~~

A record helps the example distinguish equality from identity: two records with the same endpoint can be `equals` yet remain two distinct instances.

### 11.4. ReportsAutoConfiguration.java

**src/main/java/com/example/demo/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.demo.autoconfigure;

import com.example.demo.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean(name = {"reportClient", "reports"})
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

### 11.5. AutoConfiguration.imports

Create the file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.demo.autoconfigure.ReportsAutoConfiguration
~~~

This resource enables Spring Boot 3.x to discover the auto-configuration. In `ApplicationContextRunner`, we can also load the class directly via `AutoConfigurations.of(...)`; thus the tests can still verify the class without running packaged JAR discovery.

### 11.6. ReportsAutoConfigurationTests.java

**src/test/java/com/example/demo/ReportsAutoConfigurationTests.java**

~~~java
package com.example.demo;

import com.example.demo.autoconfigure.ReportsAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void createsExactlyOneDefaultBeanAndExposesItsAlias() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ReportClient.class);
            assertThat(context).hasBean("reportClient");
            assertThat(context).hasBean("reports");

            String[] names = context.getBeanFactory()
                    .getBeanNamesForType(ReportClient.class);

            assertThat(names).containsExactly("reportClient");

            ReportClient byName =
                    context.getBean("reportClient", ReportClient.class);
            ReportClient byType = context.getBean(ReportClient.class);
            ReportClient byAlias =
                    context.getBean("reports", ReportClient.class);

            assertThat(byName).isSameAs(byType);
            assertThat(byAlias).isSameAs(byName);
            assertThat(context.getBeanFactory().getAliases("reportClient"))
                    .contains("reports");
        });
    }

    @Test
    void disabledFeatureHasNoBeanByTypeOrName() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                    assertThat(context).doesNotHaveBean("reportClient");
                    assertThat(context).doesNotHaveBean("reports");

                    assertThat(context.getBeanFactory()
                            .getBeanNamesForType(ReportClient.class))
                            .isEmpty();
                });
    }

    @Test
    void customBeanMakesAutoConfigurationBackOff() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context).hasBean("customReportClient");
                    assertThat(context).doesNotHaveBean("reportClient");

                    ReportClient customByType =
                            context.getBean(ReportClient.class);
                    ReportClient customByName =
                            context.getBean(
                                    "customReportClient", ReportClient.class);

                    assertThat(customByName).isSameAs(customByType);
                    assertThat(customByType.endpoint())
                            .isEqualTo("https://custom.example.test");
                });
    }

    @Test
    void prototypeBeansAreDifferentReferencesEvenWhenEqual() {
        runner.withUserConfiguration(PrototypeClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);

                    ReportClient first = context.getBean(ReportClient.class);
                    ReportClient second = context.getBean(ReportClient.class);

                    assertThat(first).isEqualTo(second);
                    assertThat(first).isNotSameAs(second);
                });
    }

    @Test
    void singletonLookupReturnsTheSameReferenceEachTime() {
        runner.run(context -> {
            ReportClient first = context.getBean(ReportClient.class);
            ReportClient second = context.getBean("reports", ReportClient.class);

            assertThat(first).isSameAs(second);
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.test");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrototypeClientConfiguration {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        ReportClient prototypeReportClient() {
            return new ReportClient("https://prototype.example.test");
        }
    }
}
~~~

### 11.7. Running the tests

In the directory containing `pom.xml`:

~~~bash
mvn clean test
~~~

Expect **five tests to pass**. Each test creates its own context, so properties and beans from one test never leak into another.

The first test checks for a single bean by type, canonical name, alias, and object identity. The second checks absence by type, name, and bean name list. The third confirms a custom bean makes auto-configuration back off. The fourth distinguishes equality from identity for a prototype bean. The last confirms a singleton returns the same reference across lookups.

## 12. When multiple beans of the same type exist

Suppose the context contains:

~~~java
@Bean
ReportClient primaryReportClient() {
    return new ReportClient("https://primary.example.test");
}

@Bean
ReportClient archiveReportClient() {
    return new ReportClient("https://archive.example.test");
}
~~~

Then:

- `hasBean("primaryReportClient")` and `hasBean("archiveReportClient")` are both true.
- `hasSingleBean(ReportClient.class)` is false because two beans exist.
- `getBean(ReportClient.class)` may throw `NoUniqueBeanDefinitionException` if no suitable preferred candidate exists.
- `getBean("primaryReportClient", ReportClient.class)` still looks up the bean by name.

If the application uses `@Primary`, type-based injection can pick the primary bean. That does not make the other bean disappear. Tests should verify both cardinality and injection selection if both are part of the contract.

Do not use `@Primary` to mask a duplicate bean name error. Two bean definitions with the same name represent a registration issue; primary only resolves selection among differently named candidates.

## 13. Checking bean names safely and avoiding implicit name coupling

Default bean names from `@Bean` methods are convenient, but they can change when refactoring method names. If a bean name is part of the public contract (for example, consumers look it up by name or other configurations reference that name), declare the name explicitly:

~~~java
@Bean("reportClient")
ReportClient createClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

For components:

~~~java
@Component("reportClient")
class ReportClientComponent {
}
~~~

Testing bean names helps catch unintended changes when methods or classes are renamed.

Avoid depending on auto-generated names for nested configurations or unpublished internal names. If you only need injection by type, prefer constructor injection by type and use `@Qualifier` when multiple candidates exist.

## 14. Checking proxied beans and identity

Some beans are wrapped by AOP proxies, transaction proxies, scoped proxies, or infrastructure proxies. In these cases, the injected object may be a proxy rather than the underlying target object.

For example:

- Two dependency injection points receiving the same singleton proxy may still hold the same reference.
- A proxy may differ from the target's concrete class; `instanceof` checks against the implementation may behave unexpectedly.
- A scoped proxy may keep the same proxy reference while resolving a different target per scope/request.
- An AOP proxy should not be tested by direct reference comparison against an object created with `new`.

If the goal is confirming Spring creates a singleton bean, `isSameAs` between two lookups from the same context is appropriate. If the goal is verifying the business target or proxy behavior, use assertions matching the contract, such as checking interfaces, predictable bean types, or behavior invoked through the proxy.

Do not unwrap a proxy just to make a test pass if proxying is part of the application's semantics. Test through the public interface and the behavior consumers actually use.

## 15. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Test calls `getBean(type)` and fails due to multiple beans | Multiple candidates of the same type exist | Check count/names or look up via qualifier/name |
| `isEqualTo` test passes even though two instances exist | Equality is not identity | Use `isSameAs` or `isNotSameAs` |
| Treating an alias as a second bean | Confusing an alias with a bean definition | Check `getAliases`; aliases point to the same bean |
| `getBeanNamesForType` does not return aliases | The API lists canonical bean names | Use `getAliases` to check aliases |
| Bean is in parent, but test thinks child created it | `containsBean` finds beans in ancestors | Use `containsLocalBean` and the local bean factory |
| Absence test throws an unclear exception | Calling `getBean` directly and catching a generic exception | Use `doesNotHaveBean` by type/name |
| Prototype lookup returns the same reference | Test is looking up a singleton or injecting a prototype into a singleton | Query the container/ObjectProvider directly and verify scope |
| Two beans of the same type, yet injection succeeds | `@Primary` or `@Qualifier` is present | Do not infer only one bean exists; assert cardinality separately |
| Bean name changes when method is renamed | Using the default `@Bean` name | Declare an explicit name if the name is part of the contract |
| Auto-configuration does not back off despite custom bean | Custom bean has wrong type or was not registered in time | Check return type, configuration, and conditions |
| Test context retains state from another test | Shared mutable static state or unisolated contexts | Create independent runners/contexts and avoid static mutable objects |

## 16. Assertion selection checklist

Before writing a test, identify the exact requirement:

| Requirement | Assertion/API |
| --- | --- |
| Bean exists by name | `assertThat(context).hasBean("name")` |
| Bean absent by name | `assertThat(context).doesNotHaveBean("name")` |
| Exactly one bean by type | `assertThat(context).hasSingleBean(Type.class)` |
| No bean by type | `assertThat(context).doesNotHaveBean(Type.class)` |
| Verify list of canonical names | `getBeanFactory().getBeanNamesForType(Type.class)` |
| Verify aliases | `getBeanFactory().getAliases("canonicalName")` |
| Two lookups return the same object | `assertThat(a).isSameAs(b)` |
| Confirm two objects have different references | `assertThat(a).isNotSameAs(b)` |
| Confirm same value but different objects | `isEqualTo` combined with `isNotSameAs` |
| Verify bean belongs only to child context | `containsLocalBean(name)` |
| Verify current bean definition | `containsBeanDefinition(name)` |
| Verify singleton/prototype | Look up multiple times and assert identity |

## 17. Self-check questions

**Question 1.** To confirm a context has exactly one bean of type `ReportClient`, which assertion do you use?  
**Answer:** `assertThat(context).hasSingleBean(ReportClient.class)`.

**Question 2.** Why not use `isEqualTo` to prove two lookups return the same singleton?  
**Answer:** Two different instances can be equal under `equals()`. Use `isSameAs` to verify reference identity.

**Question 3.** Does a bean with two aliases mean Spring creates three instances?  
**Answer:** No. Aliases are additional lookup names for the same bean; lookups return the same object according to the bean's scope.

**Question 4.** Does `getBeanNamesForType` list aliases as separate bean names?  
**Answer:** No. That API lists bean names; use `getAliases` to retrieve aliases.

**Question 5.** When a feature is disabled, how do you verify a bean does not exist by both type and name?  
**Answer:** Combine `doesNotHaveBean(ReportClient.class)` and `doesNotHaveBean("reportClient")`.

**Question 6.** Do two lookups of a prototype bean share the same reference?  
**Answer:** No. The container creates a new instance for each prototype lookup; the two objects may still be equal under `equals()`.

**Question 7.** Why can `containsBean(name)` be true even if the bean is not defined in the child context?  
**Answer:** A child context can look up beans inherited from its parent. Use `containsLocalBean(name)` when verifying the bean belongs to the child.

**Question 8.** Does `@Primary` make other beans of the same type disappear?  
**Answer:** No. It only marks the preferred candidate for injection; the number of beans in the context remains unchanged.

**Takeaway:** Testing Spring beans requires distinguishing **existence**, **cardinality**, **name/alias**, and **identity**. Use `hasBean`/`doesNotHaveBean` for names, `hasSingleBean` for cardinality by type, `getBeanNamesForType` and `getAliases` for lookup metadata, and `isSameAs`/`isNotSameAs` for references. For auto-configurations, `ApplicationContextRunner` lets you verify enable/disable branches, custom-bean back-off, and scopes inside small, independent, reproducible contexts.

## 18. References

- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 API — AssertableApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context.assertj/AssertableApplicationContext.html)
- [Spring Framework — BeanFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/BeanFactory.html)
- [Spring Framework — Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
