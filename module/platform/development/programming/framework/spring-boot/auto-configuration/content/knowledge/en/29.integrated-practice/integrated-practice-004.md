# Adding User Beans and Verifying Back-Off Behavior by Type and by Name

## 1. Goal of This Lab

Auto-configuration typically provides default beans so an application can use a starter immediately after adding its dependency. However, when the application has already declared a corresponding bean itself, the starter must back off so it does not create two competing implementations.

Spring Boot provides **@ConditionalOnMissingBean** to enforce this rule. The annotation can check for absence by **bean type** or by **bean name**. The two checks have different meanings:

- By type: if the context already has a bean assignable to the specified type, the default bean is not registered, regardless of what name the user bean has.
- By name: if the context already has a bean with the specified name, the default bean is not registered, regardless of whether that bean has the type expected by consumers.

This guide walks through creating application-owned beans, observing how auto-configuration backs off, and verifying the behavior using **ApplicationContextRunner**. Examples use Java 17+, Maven, and Spring Boot 3.3.13.

After this lab, you can:

1. Distinguish missing-bean conditions by type and by name.
2. Create user beans with **@Bean** in a separate configuration.
3. Verify whether the default bean is registered.
4. Recognize cases with the same type but different names, and the same name but different types.
5. Choose the check strategy matching the bean contract published by the starter.

## 2. User-Declared Beans and the Back-Off Mechanism

Suppose a starter provides a **CatalogClient** interface along with a default implementation. If the application does not declare a client, the starter creates the default client. If the application provides its own **CatalogClient**, the starter steps aside.

Common pattern:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient() {
    return new DefaultCatalogClient();
}
```

The condition above reads as: register this bean only when no bean compatible with **CatalogClient** exists yet.

### 2.1. Back-off is not overriding or deleting a bean

**@ConditionalOnMissingBean** only decides whether the default bean is registered. It does not:

- Delete an already-registered user bean.
- Replace the user bean's implementation.
- Rename the user bean.
- Make the default bean **@Primary**.
- Automatically resolve all conflicts between beans of the same type.

If the user bean already exists and the condition does not match, the auto-configuration does not create the default bean. The application-owned bean remains untouched.

This is why tests must verify both sides: the default bean does not appear and the user bean is actually used.

### 2.2. Why is the condition usually placed in auto-configuration?

**@ConditionalOnMissingBean** is specifically designed for auto-configuration. The condition can only evaluate bean definitions that have already been processed at the time it runs.

Spring Boot processes application configuration before auto-configurations imported through the standard mechanism. Therefore, application-declared beans are typically already visible when auto-configuration decides whether to create a default bean.

If you write a regular configuration and import it in an arbitrary order, do not assume every user bean is always processed first. When multiple auto-configurations depend on ordering, use ordering mechanisms such as **@AutoConfiguration(after = ...)** or **@AutoConfiguration(before = ...)** when genuinely needed.

## 3. Checking Missing Beans by Type

### 3.1. Syntax

You can specify the type using a class literal:

```java
@ConditionalOnMissingBean(CatalogClient.class)
```

Or using the explicit attribute:

```java
@ConditionalOnMissingBean(value = CatalogClient.class)
```

For types that cannot be referenced directly in source because the dependency is optional, you can use the class name:

```java
@ConditionalOnMissingBean(type = "com.acme.catalog.CatalogClient")
```

**value/type** describes the type to check. If the context already has a bean assignable to that type, the condition does not match and the guarded default bean is not created.

### 3.2. A bean of the same type with a different name still makes the starter back off

For example, the application declares:

```java
@Configuration(proxyBeanMethods = false)
class UserCatalogConfiguration {

    @Bean
    CatalogClient customCatalogClient() {
        return () -> "application-client";
    }
}
```

The default bean name inferred by Spring from the method is **customCatalogClient**. This name differs from **catalogClient**, yet the object still implements **CatalogClient**.

With the condition:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient() {
    return () -> "starter-default";
}
```

Spring Boot detects the user bean by type. The default bean is not registered, even though the two bean methods have different names.

This is usually the desired behavior when the library's contract is "the application may supply a different implementation of this interface".

### 3.3. Type matching relies on predictable types

Spring needs to know the bean type from the bean definition or metadata that it can predict. Therefore, declare the return type of **@Bean** specifically enough:

```java
@Bean
CatalogClient customCatalogClient() {
    return new CustomCatalogClient();
}
```

Do not declare **Object** if the actual contract is **CatalogClient**:

```java
@Bean
Object customCatalogClient() {
    return new CustomCatalogClient();
}
```

When only **Object** is exposed as the return type, Spring may fail to identify the target type from metadata at condition evaluation time. Declaring the return type as the public interface makes type-based conditions predictable and tells consumers which contract the bean provides.

### 3.4. Type is the natural choice for service contracts

Prefer checking by type when:

- The application is allowed to swap the implementation of an interface.
- Consumers inject the bean by type.
- The bean name is merely a configuration naming detail.
- The starter should back off when any compatible implementation is present.
- Users may name beans according to their own application conventions.

Common examples include **DataSource**, **ObjectMapper**, **Clock**, client interfaces, or a service contract published by a starter.

## 4. Checking Missing Beans by Name

### 4.1. Syntax

You can specify one or more bean names:

```java
@ConditionalOnMissingBean(name = "catalogAudit")
```

This condition asks whether a bean named **catalogAudit** already exists. It does not require that bean to have type **CatalogAudit**.

If the specified bean name already exists, the guarded default bean is not registered.

### 4.2. Same name with a different type still makes the starter back off

The application might declare:

```java
@Configuration(proxyBeanMethods = false)
class UserAuditConfiguration {

    @Bean(name = "catalogAudit")
    String catalogAuditMarker() {
        return "owned-by-application";
    }
}
```

The bean is named **catalogAudit** while its actual type is **String**.

With the condition:

```java
@Bean(name = "catalogAudit")
@ConditionalOnMissingBean(name = "catalogAudit")
CatalogAudit catalogAudit() {
    return new CatalogAudit("starter-default");
}
```

The name-based condition sees that the bean name already exists and does not register the default **CatalogAudit**. It does not check whether the bean is a **CatalogAudit**.

This is the core difference between the two checks. If a consumer requires **CatalogAudit** yet an unrelated bean accidentally occupies that name, the application may end up without the needed bean and fail on injection.

### 4.3. Same type with a different name does not make a name-based condition back off

Suppose the application declares:

```java
@Bean
CatalogAudit customCatalogAudit() {
    return new CatalogAudit("application");
}
```

The bean name is **customCatalogAudit**, not **catalogAudit**.

If the auto-configuration uses:

```java
@Bean(name = "catalogAudit")
@ConditionalOnMissingBean(name = "catalogAudit")
CatalogAudit catalogAudit() {
    return new CatalogAudit("starter-default");
}
```

then the name-based condition still matches because no bean named **catalogAudit** exists yet. As a result, the context contains two beans of type **CatalogAudit**:

- **customCatalogAudit**
- **catalogAudit**

If a consumer injects **CatalogAudit** without a qualifier or primary, Spring may throw **NoUniqueBeanDefinitionException**.

Hence, a name-based condition is not a substitute for a type-based condition when the goal is "applications can provide an implementation of the same interface".

### 4.4. When is a name-based condition appropriate?

Checking by name can make sense when the bean name is an intentional part of the contract, for example:

- A marker bean with a fixed name recognized across multiple modules.
- A resource or infrastructure bean whose identity is published by name.
- A library that needs to yield to a bean bearing a documented name, even if the implementation type may differ.
- A system with multiple beans of the same type where selection is managed via names/qualifiers.

If the bean name is not a public contract, do not force users to know the starter's internal method names.

When using a name-based condition, fix the name explicitly in **@Bean(name = "...")** instead of accidentally relying on the method name. Document that name and test that the name stays stable across versions.

## 5. Direct Comparison of Type and Name

| User bean scenario | Type condition CatalogClient.class | Name condition catalogClient |
|---|---|---|
| CatalogClient named customCatalogClient present | Backs off | Does not back off |
| CatalogClient named catalogClient present | Backs off | Backs off |
| String named catalogClient present | Does not back off by type | Backs off by name |
| CatalogAudit named customCatalogAudit present | Unrelated to CatalogClient | Does not back off if condition checks name catalogAudit |
| No matching bean present | Registers default | Registers default |

This table assumes each column checks the exact type/name shown in its header. If an annotation specifies multiple conditions, read all attributes of the annotation rather than inferring from a single attribute alone.

A way to remember:

- **Type condition asks:** "Is there already an implementation of this contract?"
- **Name condition asks:** "Is there already a bean with this identity?"

## 6. Complete Maven Example with Spring Boot 3.3.13

The example uses two independent bean contracts to test both strategies within the same auto-configuration:

- **CatalogClient** has a default bean conditioned by type.
- **CatalogAudit** has a default bean conditioned by name.

The two beans have distinct purposes so tests do not collide on names. In a real starter, choose the strategy according to each bean's contract; do not register two competing default implementations for the same responsibility.

### 6.1. Project structure

```text
bean-backoff-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/catalog/
    │   │   ├── CatalogClient.java
    │   │   └── CatalogAudit.java
    │   ├── java/com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/catalog/autoconfigure/
        └── CatalogAutoConfigurationTests.java
```

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>bean-backoff-demo</artifactId>
    <version>1.0.0</version>

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

### 6.3. CatalogClient.java

```java
package com.acme.catalog;

public interface CatalogClient {

    String source();
}
```

This interface is a contract by type. Applications can provide any implementation as long as it satisfies **CatalogClient**.

### 6.4. CatalogAudit.java

```java
package com.acme.catalog;

public record CatalogAudit(String source) {
}
```

This record is the second type to illustrate a bean whose identity is checked by name.

### 6.5. CatalogAutoConfiguration.java

```java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.CatalogAudit;
import com.acme.catalog.CatalogClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient() {
        return () -> "starter-default-client";
    }

    @Bean(name = "catalogAudit")
    @ConditionalOnMissingBean(name = "catalogAudit")
    CatalogAudit catalogAudit() {
        return new CatalogAudit("starter-default-audit");
    }
}
```

Analysis:

1. **catalogClient()** is created only if no bean compatible with **CatalogClient** exists yet.
2. **catalogAudit()** is created only if the bean name **catalogAudit** does not exist yet.
3. The two conditions are independent; a **CatalogClient** bean does not affect the condition for **CatalogAudit**.
4. The name **catalogAudit** is explicitly declared with **@Bean(name = ...)**, so it does not depend on renaming the Java method.
5. The return type of each bean method expresses the contract that Spring can predict when evaluating conditions.

### 6.6. AutoConfiguration.imports

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Spring Boot uses this file to discover the auto-configuration. In tests, **AutoConfigurations.of(...)** passes the class directly so it does not depend on the imports resource; the resource is still needed when packaging the starter for automatic consumer discovery.

## 7. Testing with ApplicationContextRunner

Each test creates an isolated context. User configuration is supplied via **withUserConfiguration(...)**, while the auto-configuration is added to the runner via **AutoConfigurations.of(...)**.

### 7.1. CatalogAutoConfigurationTests.java

```java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.CatalogAudit;
import com.acme.catalog.CatalogClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void createsDefaultsWhenNoUserBeansExist() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CatalogClient.class);
            assertThat(context).hasSingleBean(CatalogAudit.class);

            assertThat(context.getBean(CatalogClient.class).source())
                    .isEqualTo("starter-default-client");

            assertThat(context.getBean("catalogAudit", CatalogAudit.class)
                    .source())
                    .isEqualTo("starter-default-audit");
        });
    }

    @Test
    void typeConditionBacksOffForUserBeanWithDifferentName() {
        runner.withUserConfiguration(UserCatalogClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context).doesNotHaveBean("catalogClient");

                    assertThat(context.getBean(CatalogClient.class).source())
                            .isEqualTo("application-client");
                });
    }

    @Test
    void nameConditionBacksOffForSameNameEvenWhenTypeIsDifferent() {
        runner.withUserConfiguration(AuditNameCollisionConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CatalogAudit.class);

                    assertThat(context.getBean("catalogAudit"))
                            .isEqualTo("owned-by-application");
                });
    }

    @Test
    void nameConditionDoesNotBackOffForSameTypeWithDifferentName() {
        runner.withUserConfiguration(UserAuditDifferentNameConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    assertThat(context.getBeansOfType(CatalogAudit.class))
                            .hasSize(2);

                    assertThat(context.getBean(
                            "customCatalogAudit",
                            CatalogAudit.class).source())
                            .isEqualTo("application-audit");

                    assertThat(context.getBean(
                            "catalogAudit",
                            CatalogAudit.class).source())
                            .isEqualTo("starter-default-audit");
                });
    }

    @Test
    void nameConditionBacksOffForSameNameAndSameType() {
        runner.withUserConfiguration(UserAuditSameNameConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogAudit.class);

                    assertThat(context.getBean(
                            "catalogAudit",
                            CatalogAudit.class).source())
                            .isEqualTo("application-audit");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogClientConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return () -> "application-client";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AuditNameCollisionConfiguration {

        @Bean(name = "catalogAudit")
        String catalogAuditMarker() {
            return "owned-by-application";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditDifferentNameConfiguration {

        @Bean
        CatalogAudit customCatalogAudit() {
            return new CatalogAudit("application-audit");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditSameNameConfiguration {

        @Bean(name = "catalogAudit")
        CatalogAudit customCatalogAudit() {
            return new CatalogAudit("application-audit");
        }
    }
}
```

### 7.2. Explaining the five tests

| Test | User bean | Condition observed | Result |
|---|---|---|---|
| **createsDefaultsWhenNoUserBeansExist** | None | Type and name | Both defaults are created |
| **typeConditionBacksOffForUserBeanWithDifferentName** | CatalogClient named customCatalogClient | By type | Default client is not created |
| **nameConditionBacksOffForSameNameEvenWhenTypeIsDifferent** | String named catalogAudit | By name | Default audit is not created |
| **nameConditionDoesNotBackOffForSameTypeWithDifferentName** | CatalogAudit named customCatalogAudit | By name | Default audit is still created; two beans of the same type exist |
| **nameConditionBacksOffForSameNameAndSameType** | CatalogAudit named catalogAudit | By name | Default audit is not created |

The third test is the surprising case: the name already exists so the condition backs off, even though the type does not match. The fourth test shows the converse: the type already exists under a different name, so the name-based condition still allows the default.

### 7.3. Running the tests

Using JDK 17+ and Maven in the directory containing **pom.xml**:

```bash
mvn test
```

With the five tests above, the expected result is:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

This is the expected output for the example, not the log of an executed run. The tests only create ApplicationContexts and check beans; they do not start servers or call external services.

## 8. Design Rules When Using the Two Strategies

### 8.1. Prefer type-based conditions for services

For a service contract, interface, or abstraction that consumers inject by type, generally use:

```java
@ConditionalOnMissingBean(CatalogClient.class)
```

Benefits:

- Applications can name beans using their own conventions.
- Any compatible implementation can replace the default.
- The condition directly expresses the intent "does this service exist yet?".
- Readers do not need to know internal bean method names of the starter.

Use the public interface as the checked type when you want to allow different implementations. Checking a concrete implementation class narrows the replacement contract.

### 8.2. Use name-based conditions only when name identity is intentional

Use:

```java
@ConditionalOnMissingBean(name = "catalogAudit")
```

when the bean name **catalogAudit** is documented as a stable identity. You should explain:

- Which resource or role that bean name represents.
- Whether consumers inject it with **@Qualifier("catalogAudit")** or look it up by name.
- Whether a bean of a different type sharing that name is allowed to replace it.
- Whether renaming the bean constitutes a breaking change.

If you do not want a bean of a different type to occupy the slot, a name-only condition may be too broad. Consider checking the type, or combining conditions matching the concrete contract with an appropriate bean-naming design.

### 8.3. Do not confuse back-off with @Primary

**@Primary** affects how Spring selects a candidate when multiple beans of the same type exist for injection. It does not prevent the default bean from being registered.

For instance, if two **CatalogClient** beans exist, marking the user bean **@Primary** can make by-type injection pick it, yet both beans still exist. **@ConditionalOnMissingBean(CatalogClient.class)** solves the problem earlier by not creating the default when the contract is already fulfilled.

### 8.4. Watch out for default @Bean method names

If no explicit name is given, the default bean name is normally derived from the method name:

```java
@Bean
CatalogAudit catalogAudit() {
    return new CatalogAudit("starter");
}
```

The bean name is then **catalogAudit**. Renaming the method can change the bean name.

If a name-based condition relies on that name, declare the name explicitly:

```java
@Bean(name = "catalogAudit")
@ConditionalOnMissingBean(name = "catalogAudit")
CatalogAudit createCatalogAudit() {
    return new CatalogAudit("starter");
}
```

This decouples the bean's identity from the Java method name. However, explicit names are only useful when the library genuinely intends to commit to that name for consumers.

## 9. Ordering and Search Scope

### 9.1. Conditions only see already-processed bean definitions

**@ConditionalOnMissingBean** is not a final query over all future configuration. It evaluates the state of the bean factory at the moment the condition is processed.

Therefore:

- Use it in auto-configuration so user beans have a chance to register first.
- Avoid placing the condition in configurations imported too early if user beans have not yet been processed.
- When two auto-configurations depend on each other, use **before/after** to declare ordering.
- Do not rely on accidental ordering between configuration classes.

### 9.2. Bean definitions and return types

When evaluating type-based conditions, Spring attempts to determine the type from the bean definition, factory method return type, or metadata. Do not hide the contract behind an overly generic return type like **Object** when consumers and conditions need a specific interface.

With a factory method returning an interface, Spring can recognize the contract without instantiating the object just to guess its type. This makes conditions more reliable and avoids eager instantiation of beans with side effects.

### 9.3. Context hierarchy

In applications with parent/child ApplicationContexts, the bean search scope can affect results. **@ConditionalOnMissingBean** provides the **search** attribute with context search strategies. Read the Javadoc for your Spring Boot version and choose a scope suited to your context architecture.

Do not assume that beans in parent and child contexts behave identically in every configuration. If an application has a context hierarchy, add dedicated tests for parent and child beans instead of testing only a flat context.

## 10. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Starter still creates default despite application having an implementation | Name condition used while user bean has a different name | Use a type condition for service contracts |
| Default disappears even though no bean of the right type exists | Name condition collided with a bean of a different type sharing that name | Check bean names; use a type condition if targeting a contract |
| Two beans of the same type after overriding | Name condition failed to detect user bean of the same type with another name | Use **@ConditionalOnMissingBean(TargetType.class)** |
| Context throws **NoUniqueBeanDefinitionException** | Both default and user beans of the same type exist | Fix the condition; use **@Primary** only if multiple candidates are truly desired |
| Type condition fails to recognize user bean | **@Bean** method exposes an overly generic return type | Declare the return type as the actual interface/contract |
| Condition runs before user configuration | Improper ordering or import mechanism | Use proper auto-configuration mechanisms and verify ordering |
| Renaming a method breaks consumer lookup | Bean name inferred from method yet relied on as a contract | Declare **@Bean(name=...)** and document it if the name must be stable |
| Tests only check bean presence without checking bean source | Tests do not prove actual back-off | Assert bean name/type and behavior from the user bean |
| Assuming **@Primary** prevents default creation | Confusing injection preference with bean registration conditions | Use **@ConditionalOnMissingBean** to control registration |
| Name-only condition drops needed injectable bean | A bean of a different type with the same name made the condition back off | Inspect types and names in context; pick the appropriate condition |

## 11. Practice and Verification Workflow

When adding customization to an auto-configuration:

1. Identify the contract the application should replace: an interface/type or a specific bean identity.
2. If replacing a service by interface, use **@ConditionalOnMissingBean(ContractType.class)**.
3. If replacing by identity, use **@ConditionalOnMissingBean(name = "...")** and document the name.
4. Place the condition on the default bean or appropriate configuration group.
5. Ensure user configuration is processed before auto-configuration.
6. Declare the **@Bean** return type as the concrete contract.
7. Write a test with no user bean to verify the default appears.
8. Write a test with the same type and a different name to verify type-based back-off.
9. Write a test with the same name and a different type to observe name-based back-off.
10. Write a test with the same type and a different name for a name-based condition to catch duplicate beans of the same type.
11. Verify the bean actually injected or looked up is the user bean.
12. If using parent/child contexts, test the **search** scope separately.
13. Read the Condition Evaluation Report when conditions match or fail unexpectedly.

## 12. Self-Check Questions

**Question 1.** What does **@ConditionalOnMissingBean(CatalogClient.class)** check?

**Answer:** It checks that no bean compatible with type **CatalogClient** exists yet. A bean of the same type with a different name still makes the default back off.

**Question 2.** What does **@ConditionalOnMissingBean(name = "catalogAudit")** check?

**Answer:** It checks that no bean named **catalogAudit** exists yet. A name-based condition does not require that bean to have type **CatalogAudit**.

**Question 3.** If the user provides a **CatalogClient** named **customCatalogClient**, does the type-based condition back off?

**Answer:** Yes, because a type-compatible bean already exists.

**Question 4.** If the user provides a **String** named **catalogAudit**, does the name-based condition back off?

**Answer:** Yes. The name already exists, even though the type is not **CatalogAudit**.

**Question 5.** If the user provides a **CatalogAudit** named **customCatalogAudit**, does a name-based condition checking **catalogAudit** back off?

**Answer:** No. A bean of the same type with a different name does not satisfy missing name **catalogAudit**; the default is still registered.

**Question 6.** Why declare the return type of a user **@Bean** as the actual interface?

**Answer:** So Spring can predict the type from the bean definition when evaluating conditions and keep the contract clear for consumers.

**Question 7.** Does **@Primary** prevent auto-configuration from creating a default bean?

**Answer:** No. **@Primary** only affects injection selection when multiple candidates exist; **@ConditionalOnMissingBean** controls default registration.

**Question 8.** When should you use a name-based condition?

**Answer:** When the bean name is a stable, published identity that is meaningful independently of type. For typical service contracts, type-based conditions are usually more appropriate.

## 13. Key Takeaways

- **@ConditionalOnMissingBean(CatalogClient.class)** checks by type; beans of the same type with different names still make the default back off.
- **@ConditionalOnMissingBean(name = "catalogAudit")** checks by name; beans of a different type with the same name still make the default back off.
- Name-based conditions do not detect beans of the same type with different names, which can lead to two beans of the same type.
- Type-based conditions suit service/interface contracts where applications can swap implementations.
- Name-based conditions suit cases where the bean name is a published identity that must remain stable.
- Declare **@Bean** return types as concrete contracts so type conditions can predict beans.
- **@ConditionalOnMissingBean** only governs default registration; it never deletes or overwrites user beans.
- **@Primary** controls injection selection, not back-off registration conditions.
- Place conditions in auto-configuration and pay attention to bean definition processing order.
- Test all cases: same type/different name, same name/different type, and no user bean.

### Official References

- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Framework 6.1 — Bean Definition and Factory Methods](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
