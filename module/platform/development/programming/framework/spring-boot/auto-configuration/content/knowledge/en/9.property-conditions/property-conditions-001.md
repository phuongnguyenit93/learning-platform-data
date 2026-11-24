# @ConditionalOnProperty with prefix, name, and value

> **Spring Boot Auto Configuration → Property Conditions.** This lesson explains how `@ConditionalOnProperty` computes key names and allowed values, why `value` is an alias for `name`, when `havingValue` or `matchIfMissing` is needed, and how to verify bean registration results in a Spring Boot application using Java 17+.

## 1. The Problem That @ConditionalOnProperty Solves

When writing auto-configuration or bean configuration, there are features that should only be activated if the user sets the corresponding property. For example: an application creates a notification-sending bean only if `demo.mail.enabled=true`, while still running normally when the feature is disabled.

Spring Boot provides the `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty` annotation to check values in `Environment` when building the application context. If the condition **matches**, the configuration class or `@Bean` method is considered for registration. If it **does not match**, the configuration/bean marked with that condition will not be registered.

~~~java
@ConditionalOnProperty(
    prefix = "demo.mail",
    name = "enabled",
    havingValue = "true"
)
~~~

In this case:
- **Full property name:** `demo.mail.enabled`.
- **Value to compare:** `true`.
- When the property is `true` → the condition matches.
- When the property is `false` or the property is missing → the condition does not match (with the default `matchIfMissing=false`).

The annotation controls **configuration registration at context startup time**. It does not automatically change an already-running bean when the property is edited in a configuration file, and it does not by itself guarantee that all dependencies of the bean are valid.

## 2. Distinguishing prefix, name, value, havingValue, and matchIfMissing

General syntax:

~~~java
@ConditionalOnProperty(
    prefix = "app.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

| Attribute | Type | Default | Role |
| --- | --- | --- | --- |
| `prefix` | `String` | `""` | Groups keys, e.g., `app.feature`. |
| `name` | `String[]` | `{}` | One or more **property names** to check, e.g., `enabled`. |
| `value` | `String[]` | `{}` | **Alias for `name`**, also representing property names. Not used to specify the expected value. |
| `havingValue` | `String` | `""` | The value the property must match; empty means using the default rule of not equal to `false`. |
| `matchIfMissing` | `boolean` | `false` | Decides whether to match if the key **does not exist** in `Environment`. |

### 2.1. prefix + name forms the full key

~~~java
@ConditionalOnProperty(
    prefix = "app.payment",
    name = "retry-enabled",
    havingValue = "true"
)
~~~

Spring Boot joins `app.payment` and `retry-enabled` to look up the key **`app.payment.retry-enabled`**. Corresponding YAML configuration:

~~~yaml
app:
  payment:
    retry-enabled: true
~~~

You can write the prefix with or without a trailing dot; Spring Boot automatically adds a separating dot when needed. For multiple words, you should use **lowercase with hyphens**, e.g., `retry-enabled`.

If you do not use `prefix`, you can specify the full name:

~~~java
@ConditionalOnProperty(
    name = "app.payment.retry-enabled",
    havingValue = "true"
)
~~~

This checks the same property as the example above, but using `prefix` makes it easier to group conditions within a module.

### 2.2. value is an alias for name, never confuse it with havingValue

The following two annotations are **equivalent**:

~~~java
@ConditionalOnProperty(
    prefix = "app.payment",
    name = "retry-enabled",
    havingValue = "true"
)
~~~

~~~java
@ConditionalOnProperty(
    prefix = "app.payment",
    value = "retry-enabled",
    havingValue = "true"
)
~~~

Both check whether **key `app.payment.retry-enabled` has the value `true`**.

Conversely, writing:

~~~java
@ConditionalOnProperty(prefix = "app.payment", value = "true")
~~~

does **not** mean "some property must equal true". It requires a **property named `app.payment.true`** under the default rule. This is an easy semantic mistake when inferring from the attribute name `value`.

You should use `name` so readers clearly see the intent, and `value` when you want concise syntax; **do not declare both aliases with conflicting values**. To compare against a value, use `havingValue` properly.

### 2.3. havingValue is the string to match, not the property name

~~~java
@ConditionalOnProperty(
    prefix = "app.delivery",
    name = "mode",
    havingValue = "async"
)
~~~

This condition matches when `app.delivery.mode=async`. `havingValue` can also be `local`, `cloud`, `true`, `false`, or another string state.

**If `havingValue` is omitted**, the default condition **does not mean the property must parse to boolean true**. It only requires that the property **exists and its value is not `false`**. For example, `app.feature.enabled=on` or `app.feature.enabled=unexpected` can still match. For a flag that should only be enabled explicitly, you should declare `havingValue="true"`.

### 2.4. matchIfMissing only takes effect when the key is absent

~~~java
@ConditionalOnProperty(
    prefix = "app.metrics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

- `app.metrics.enabled=true`: matches.
- `app.metrics.enabled=false`: does not match.
- `app.metrics.enabled` **is not declared**: matches because `matchIfMissing=true`.

Therefore, `matchIfMissing=true` is suitable for features **enabled by default** and allowing users to disable them with `false`. If explicit opt-in is required, keep `matchIfMissing=false`.

## 3. Truth Table to Remember

Suppose the condition checks a single property `demo.feature.enabled`; `matchIfMissing=false` as the default.

| Property value | `havingValue=""` | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | :---: | :---: | :---: | :---: |
| `true` | Match | Match | No | No |
| `false` | No | No | Match | No |
| `foo` | Match | No | No | Match |
| **Missing** | No | No | No | No |

Explanation:

1. `havingValue=""` is the default: it only rejects the value **`false`** and requires the property to be present.
2. When `havingValue` is declared, Spring Boot compares the effective property value string against the required string.
3. If the property is absent, `matchIfMissing` decides. Setting it to `true` causes the **missing key** case to match, even when `havingValue="true"` or `havingValue="false"`.
4. A property that is **present with an empty value** is not the same as a missing property. For example, `demo.feature.enabled=` can still match if `havingValue` is not specified, because an empty string differs from the string `false`.
5. `havingValue="false"` only matches a **present `false` value** (unless missing is allowed via `matchIfMissing=true`). Do not assume "not configured" means "configured as false".

This is the behavior matrix described in the Spring Boot Javadoc. Words such as `on`, `yes`, or `1` do not substitute for `true` when you have required **`havingValue="true"`**. When designing boolean flags, explicitly specifying the required value prevents accidentally enabling functionality.

## 4. Multiple name/value entries are AND, not OR

`name` and `value` have type `String[]`. Multiple keys can be checked:

~~~java
@ConditionalOnProperty(
    prefix = "demo.security",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

The condition matches when **both** keys satisfy it:
- `demo.security.enabled=true`
- `demo.security.audit-enabled=true`

| `enabled` | `audit-enabled` | Result |
| --- | --- | --- |
| true | true | Match |
| true | false | No |
| false | true | No |
| true | missing | No, with default `matchIfMissing=false` |
| missing | missing | No, with default `matchIfMissing=false` |

The array `name={"enabled","audit-enabled"}` uses **AND** logic. It does not mean "just one of the two". At the same time, `havingValue` applies **in common** to every key in the array. If you need a mixed condition like `enabled=true` **and** `mode=async`, you can place conditions at both class and method levels (illustrated later) or build a custom `Condition`.

`matchIfMissing=true` with multiple keys makes missing keys accepted; **keys that are present must still satisfy `havingValue`**. You must consider the default policy of each attribute before using it.

## 5. Complete Runnable Example with Spring Boot and Java 17+

The goal is to observe the `mailGateway` bean being created **if and only if** `demo.mail.enabled=true`. The following example uses Maven; it only requires JDK 17+, Maven, and permission to download libraries. This is a Spring Boot project, so it cannot be run with plain `javac` without the library classpath.

Structure:

~~~text
property-condition-demo/
├── pom.xml
└── src/main/java/demo/condition/PropertyConditionDemo.java
~~~

**File `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>demo</groupId>
    <artifactId>property-condition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**File `src/main/java/demo/condition/PropertyConditionDemo.java`:**

~~~java
package demo.condition;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PropertyConditionDemo {

    public static void main(String[] args) {
        SpringApplication.run(PropertyConditionDemo.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.mail",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    String mailGateway() {
        return "MAIL_GATEWAY_ACTIVE";
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> System.out.println(
                "mailGateway bean present: " + context.containsBean("mailGateway")
        );
    }
}
~~~

Here `mailGateway` is a `String` bean to keep the lab concise, **not a real mail-sending adapter**. `ApplicationRunner` runs after the context starts and prints the presence of the bean.

**Compile and package:**

~~~bash
mvn -q -DskipTests package
~~~

**Case A — property equals true:**

~~~bash
java -jar target/property-condition-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.mail.enabled=true
~~~

Line printed by the program itself:

~~~text
mailGateway bean present: true
~~~

**Case B — property equals false:**

~~~bash
java -jar target/property-condition-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.mail.enabled=false
~~~

Line printed by the program:

~~~text
mailGateway bean present: false
~~~

**Case C — property does not exist:**

~~~bash
java -jar target/property-condition-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by the program:

~~~text
mailGateway bean present: false
~~~

The three lines above are **`System.out.println` lines**, without claiming that is the entire log if the environment produces other output.

To try `matchIfMissing=true`, change the value in the annotation, **repackage**, and repeat Case C. Then `mailGateway bean present: true`. Case A remains true, and Case B remains false.

**Mechanism model:**

~~~text
Environment contains demo.mail.enabled?
         |
         +-- Yes: compare value with havingValue="true"
         |       +-- true  -> mailGateway bean is registered
         |       +-- false -> mailGateway bean is skipped
         |
         +-- No: evaluate matchIfMissing=false
                 +-- mailGateway bean is skipped
~~~

Although a property's value can come from many different sources, the condition inspects **the final value provided by Environment** during the bean registration phase.

## 6. Should the Condition Be Placed at Class Level or Method Level?

### 6.1. On a @Bean method: condition for one specific bean

The lab in section 5 places `@ConditionalOnProperty` directly on the `mailGateway()` method, so only this method is governed by the condition. Other `@Bean` methods in the same class are still evaluated according to their own conditions.

Component example:

~~~java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "feature",
        name = "cache-enabled",
        havingValue = "true"
    )
    CacheClient cacheClient() {
        return new CacheClient();
    }

    static final class CacheClient {}
}
~~~

This is a **code snippet to integrate into an application with Spring**, requiring imports for `Configuration`, `Bean`, and `ConditionalOnProperty`. Use the method level when you only want a single bean affected by a configuration flag.

### 6.2. On a @Configuration / @AutoConfiguration class: condition for an entire group of beans

~~~java
package demo.extension;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditAutoConfiguration {

    @Bean
    AuditSink auditSink() {
        return new AuditSink();
    }

    public static final class AuditSink {
        public String name() {
            return "audit";
        }
    }
}
~~~

Here, the entire `AuditAutoConfiguration` class is controlled by `feature.audit.enabled`. If it does not match, the beans declared by that class are not registered through this auto-configuration.

When writing a **starter / external library**, Spring Boot 3.x looks up auto-configurations from the registration file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

With the example class above, the exact content of this file is:

~~~text
demo.extension.AuditAutoConfiguration
~~~

This is **configuration code that can compile in a project with Spring Boot dependencies**, but not a standalone program with a `main` method. For the `@SpringBootApplication` lab in section 5, there is no need to create the imports file manually.

### 6.3. Two different expected values: combining conditions at both levels

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "feature.delivery",
    name = "enabled",
    havingValue = "true"
)
class DeliveryConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "feature.delivery",
        name = "mode",
        havingValue = "async"
    )
    AsyncWorker asyncWorker() {
        return new AsyncWorker();
    }

    static final class AsyncWorker {}
}
~~~

The snippet above is a component example with the corresponding Spring imports. The `AsyncWorker` bean is only declared when **`feature.delivery.enabled=true` and `feature.delivery.mode=async`**. This is clearer than stuffing two property names requiring **two different values** into a single `name` array sharing `havingValue`.

If multiple conditions apply together, all required conditions must be satisfied. A matching `@ConditionalOnProperty` does not guarantee that the bean actually exists if `@ConditionalOnClass`, `@ConditionalOnMissingBean`, the import mechanism, or bean creation fails.

## 7. Where Do Properties Come From and Why Can the Effective Value Differ from the File?

The following configurations express the same intent **`demo.mail.enabled=true`**.

**`application.yml`:**

~~~yaml
demo:
  mail:
    enabled: true
~~~

**`application.properties`:**

~~~properties
demo.mail.enabled=true
~~~

**Command-line arguments:**

~~~bash
java -jar app.jar --demo.mail.enabled=true
~~~

**Environment variables** in an environment supporting Spring Boot externalized configuration:

~~~bash
export DEMO_MAIL_ENABLED=true
~~~

Spring Boot uses multiple property sources, including default files, profile-specific files, environment variables, system properties, and command-line arguments. They have an **order of precedence**; a key set in `application.yml` can be overridden by a value from a higher-precedence source.

For example: `application.yml` has `demo.mail.enabled=false`, but the run command uses `--demo.mail.enabled=true`. In a typical Spring Boot application, command-line arguments take higher precedence than configuration files, so `@ConditionalOnProperty` will see true.

**Distinguish four situations when debugging:**
- The exact key **is absent** → `matchIfMissing`.
- The exact key **is present and equals false** → evaluates `havingValue`, not treated as missing.
- The key is present but **empty** → still an existing value; by default it can match because it differs from false.
- You only declared `demo.mail.enable` while the condition needs `demo.mail.enabled` → the exact key is still missing.

Prefer lowercase kebab-case property naming conventions; when using `@ConfigurationProperties`, Spring Boot supports structured binding and validation, whereas `@ConditionalOnProperty` focuses on **reading properties to decide configuration initialization**. They are two mechanisms with different purposes.

**Important note about collections:** The Javadoc states that `@ConditionalOnProperty` is not reliable for checking list-like properties; for example, having only `demo.targets[0]` does not guarantee `demo.targets` is exposed as a checkable property. If you need to know whether a list has elements, bind the list with `@ConfigurationProperties` or write an appropriate `Condition` instead of using `@ConditionalOnProperty(name="targets")`.

## 8. Testing Conditions Instead of Guessing

For a starter or auto-configuration, test at least four cases: `true`, `false`, **missing**, and an unexpected value. Spring Boot provides `ApplicationContextRunner` to create a lightweight context, set properties for each case, and assert on beans.

Add the test dependency to `pom.xml` (inside `<dependencies>`):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **`src/test/java/demo/condition/ConditionalPropertyTest.java`**:

~~~java
package demo.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalPropertyTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(TestConfiguration.class);

    @Test
    void trueValueCreatesBean() {
        runner.withPropertyValues("demo.mail.enabled=true")
                .run(context -> assertThat(context).hasBean("mailGateway"));
    }

    @Test
    void falseValueSkipsBean() {
        runner.withPropertyValues("demo.mail.enabled=false")
                .run(context -> assertThat(context).doesNotHaveBean("mailGateway"));
    }

    @Test
    void missingPropertySkipsBeanByDefault() {
        runner.run(context -> assertThat(context).doesNotHaveBean("mailGateway"));
    }

    @Test
    void otherValueDoesNotMatchExplicitTrue() {
        runner.withPropertyValues("demo.mail.enabled=on")
                .run(context -> assertThat(context).doesNotHaveBean("mailGateway"));
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "demo.mail",
                name = "enabled",
                havingValue = "true"
        )
        String mailGateway() {
            return "MAIL_GATEWAY_ACTIVE";
        }
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Expected **4 tests PASS**. This test uses a minimal configuration inside the test class and does not depend on the startup timing of a full web server. When changing the default `matchIfMissing` rule or adding multiple `name` entries, **add cases reflecting the actual policy**, especially the case where one key is missing.

## 9. Debugging in Spring Boot Auto Configuration

When an expected bean does not appear, follow this sequence.

**Step 1 — translate the annotation into concrete checks.** For example, `prefix="feature.audit"`, `name="enabled"`, `havingValue="true"`, `matchIfMissing=false` means **`feature.audit.enabled` must be present and have the value true**.

**Step 2 — inspect the condition evaluation report.** Run the application with the `--debug` argument:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot can display a report of matched/unmatched conditions. If the application uses Actuator and the endpoint is properly enabled/exposed, the `/actuator/conditions` endpoint provides a useful report. Control access to this endpoint in deployment environments.

**Step 3 — determine the value `Environment` actually sees.** Inspect property sources, active profiles, environment variables, command-line arguments, and precedence order. Do not conclude from a single `application.yml` file.

**Step 4 — check other conditions.** `@ConditionalOnClass` may block auto-configuration when a library is missing; `@ConditionalOnMissingBean` may skip the bean because the user declared one themselves; import/scan may not have registered the class. If bean creation throws an exception, read the stack trace. `@ConditionalOnProperty` only checks properties; **it does not prove the bean will be created successfully**.

**Step 5 — verify after fixing.** Re-run the `true`, `false`, missing, and edge-value scenarios; when needed, use `ApplicationContextRunner` to verify repeatable behavior.

## 10. Common Mistakes to Avoid

1. **Using `value="true"` to compare against true.** `value` is the property name; compare values using `havingValue="true"`.
2. **Omitting `havingValue` and believing the condition checks a true boolean.** The default rule only rejects the value `false`; other values can match.
3. **Confusing missing with false.** A missing property is governed by `matchIfMissing`; `havingValue="false"` does not automatically match when missing.
4. **Assuming multiple `name` entries mean OR.** All must satisfy the condition; if you want OR, a different condition model is needed.
5. **Assuming `prefix` auto-corrects typos or searches by suffix.** Prefix and name form a specific key; spelling mistakes result in missing.
6. **Using the condition to check whether a list has elements.** For collections, indexed properties can differ from the aggregate property; choose binding/custom condition.
7. **Forgetting configuration source precedence.** Profiles, runtime environment, and command-line can override `application.yml`.
8. **Expecting runtime config changes to automatically alter the bean.** Bean definitions are normally decided during context creation; a separate runtime mechanism is needed for dynamic state toggling.
9. **Checking only the property condition without inspecting other conditions.** The bean also depends on classpath, existing beans, import configuration, and initialization errors.
10. **Not testing the missing-property case.** This is the case directly governed by `matchIfMissing` and is often the difference between "opt-in" and "enabled by default".

## 11. Practice Scenarios and Self-Check Questions

**Scenario A: feature only enabled on opt-in.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

Configuration without the property will **not activate**. Write `feature.audit.enabled=true` to enable, `false` to disable.

**Scenario B: feature enabled by default but allowed to be disabled.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.metrics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

Not declaring the property still activates it; `feature.metrics.enabled=false` explicitly disables it. Choose this approach based on product policy, not merely for concise code.

**Scenario C: configured only in async mode.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.delivery",
    name = "mode",
    havingValue = "async"
)
~~~

`mode=async` activates it; `mode=sync` or undeclared does not activate it.

**Scenario D: two flags both enabled.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.security",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Both `feature.security.enabled` and `feature.security.audit-enabled` must equal true.

**Question 1:** Which property does `@ConditionalOnProperty(prefix="demo", value="enabled", havingValue="true")` read?  
**Answer:** `demo.enabled`; `value` is an alias for `name`.

**Question 2:** Does `@ConditionalOnProperty(prefix="demo", name="enabled")` match when encountering `demo.enabled=foo`?  
**Answer:** Yes; by default it only requires the property to be present and different from `false`.

**Question 3:** `havingValue="false"`, the property does not exist, and `matchIfMissing=false`: does it match?  
**Answer:** No. A missing property differs from a property with the value false.

**Question 4:** `name={"a","b"}`, `havingValue="true"`, and only `a=true`, `b=false`: what is the result?  
**Answer:** Does not match because the names are combined with AND.

**Question 5:** `@ConditionalOnProperty` matches but the bean is still absent—is the annotation definitely buggy?  
**Answer:** Not necessarily. Check other conditions, how the configuration is registered, `Environment` values, and bean creation exceptions.

## 12. Key Takeaways to Remember

- **`prefix + "." + name`** forms the full key name; `prefix + "." + value` does the same because **`value` is an alias for `name`**.
- **`havingValue`** specifies the value to match. Empty by default → property exists and value is **not `false`**.
- **`matchIfMissing`** only controls the case where the **key does not exist**; default false.
- **Multiple properties in `name`** must match **simultaneously** and share the same `havingValue`.
- Whether a bean appears depends on **the effective value of `Environment` when configuration is processed**, and may also depend on other conditions.
- When in doubt, use **Condition Evaluation Report + property source inspection + `ApplicationContextRunner`** to verify.

**Official references:**
- [Spring Boot 3.3 Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot Reference — Creating Your Own Auto-configuration, Property Conditions](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)