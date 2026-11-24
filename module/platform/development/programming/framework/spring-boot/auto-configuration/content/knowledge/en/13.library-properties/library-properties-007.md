# Keeping Toggle Keys Consistent with Generated Configuration

> **Spring Boot Auto Configuration → Library Properties.** This lesson shows how to design a clear `enabled` key for a library/starter, ensuring the exact same key is used across documentation, `@ConditionalOnProperty`, `@ConfigurationProperties`, bean-creating auto-configuration, and tests. Examples use Java 17+ and Spring Boot 3.3.x.

## 1. The Problem: Users Enable One Key While the Library Checks Another

An integration library might publish:

~~~yaml
demo:
  notice:
    enabled: true
    message: "Welcome"
~~~

Users expect: setting `demo.notice.enabled=true` makes Spring Boot create the notification-sending bean; setting `false` prevents the library's default bean from being created.

In practice, **a mismatch between the published key and the condition key** arises very easily, for example:

~~~java
// Documentation guides users: demo.notice.enabled=true
// Yet auto-configuration checks a different prefix.
@ConditionalOnProperty(
    prefix = "demo.notification",
    name = "enabled",
    havingValue = "true"
)
~~~

Then `demo.notice.enabled=true` **does not activate** the configuration because the annotation reads `demo.notification.enabled`. The application may still run, but the expected bean is missing; the bug lies not in YAML syntax, but in an **inconsistent configuration contract**.

Mismatches also happen when:
- `@ConfigurationProperties(prefix="demo.notice")` binds `enabled` while the condition reads `demo.notice.active`.
- Documentation lists `notice.enabled` while code checks `demo.notice.enabled`.
- A Java field defaults to `enabled=true` yet `@ConditionalOnProperty` uses `matchIfMissing=false`, so omitting the key **does not create the bean**.
- The condition checks `enabled=true` while a `@Bean` branch creates the service outside the condition's scope.
- Users set `enabled=false` yet another auto-configuration still creates a bean with the same function.
- Tests only cover `enabled=true` without testing defaults, `false`, and wrong keys.

**Core principle:** a toggle key must have **one stable public name, one clear default policy, and one well-defined scope of effect**. The condition and bean configuration must enforce that exact same contract.

## 2. Before Writing Code: Define the Key's Contract

Suppose a library has a feature named *notice*:

| Contract component | Illustrative decision | Meaning |
| --- | --- | --- |
| Namespace | `demo.notice` | Groups all properties of a single feature |
| Toggle key | `demo.notice.enabled` | The sole key deciding whether to auto-create the notice service |
| Data type | Boolean | Users write `true` or `false` |
| Default | `false` | Feature only turns on when the user explicitly opts in |
| Spring Boot condition | `havingValue="true", matchIfMissing=false` | Must be present and equal to true to create the bean |
| Conditional bean | `NoticeSender` provided by auto-configuration | When disabled, the starter does not create this bean automatically |
| Accompanying property | `demo.notice.message` | Used when the feature is enabled |
| Override contract | User-declared bean takes precedence | `@ConditionalOnMissingBean` avoids creating a duplicate default |
| Minimum tests | missing, false, true, wrong key, custom message | Catches name mismatches, default mismatches, and actual bean behavior |

Not every library has to default to off. You can choose **default on** when a feature is foundational and has no unwanted side effects. In that case, consistent updates must happen **simultaneously** across documentation, the condition, Java default values, and tests—never edit only one place.

### 2.1. A Toggle Key Has Two Meanings to Keep Separate

**Condition meaning:** Should Spring register the starter's default bean? This is the role of `@ConditionalOnProperty`.

**Configuration value meaning:** What value of `enabled` and related properties does the bound bean receive? This is the role of `@ConfigurationProperties`.

Both mechanisms look at the same `Environment` but operate differently. `@ConditionalOnProperty` is typically evaluated when processing bean definitions. `@ConfigurationProperties` binds values into a configuration object. **The Binder does not automatically synchronize a condition's rules with a default value placed on a Java object.**

Example:

~~~java
@ConfigurationProperties(prefix = "demo.notice")
public class NoticeProperties {
    private boolean enabled = true;
}
~~~

If auto-configuration simultaneously uses:

~~~java
@ConditionalOnProperty(
    prefix = "demo.notice",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

then **when the property is absent**:
- The Java field's default is `true` **if the properties object is created**;
- Yet the condition reads `Environment`, sees **no key**, and evaluates to no match;
- The bean gated by the condition will not be registered.

Therefore **defaults on a Java object do not replace `matchIfMissing`**. If the contract requires default-on, set `matchIfMissing=true` and align the `enabled` default to reflect it as well.

## 3. Naming Convention: Keep One Key Name Across Every Layer

Pick a readable canonical name grouped by library:

~~~properties
demo.notice.enabled=true
demo.notice.message=Welcome
~~~

In YAML:

~~~yaml
demo:
  notice:
    enabled: true
    message: Welcome
~~~

Common points of confusion:

| Documentation / user-supplied value | What the annotation actually checks | Result |
| --- | --- | --- |
| `demo.notice.enabled=true` | `demo.notice.enabled` | Matches when `havingValue="true"` |
| `demo.notice.enabled=true` | `demo.notification.enabled` | Does not match due to wrong prefix |
| `demo.notice.active=true` | `demo.notice.enabled` | Does not match due to wrong name |
| `demo.notice.enabled=false` | `demo.notice.enabled` | Does not match, per policy |
| `demo.notice.enabled` omitted | `demo.notice.enabled` | Does not match when `matchIfMissing=false` |

**Use canonical kebab-case property names** for multi-word keys, such as `retry-enabled` or `connection-timeout`. When using `@ConfigurationProperties`, Spring Boot supports *relaxed binding* for several name variants, but do not turn that capability into an excuse to publish multiple inconsistent names. Documentation and code should stick to one canonical spelling.

For environment variables, Spring Boot has a convention mapping names like `DEMO_NOTICE_ENABLED` to the corresponding key when reading from the system environment. With a multi-level property list, a fixed prefix helps prevent collisions with other features.

## 4. Choosing an On/Off Policy: Truth Table

Suppose `@ConditionalOnProperty(prefix="demo.notice", name="enabled", havingValue="true")` with `matchIfMissing=false`.

| `demo.notice.enabled` | Matches? | Auto-config default bean created? |
| --- | --- | --- |
| `true` | Yes | Yes, if other conditions also pass |
| `false` | No | No |
| Absent | No | No |
| `foo` | No | No |
| Misspelled key, e.g., `demo.notice.enable` | No | No, because the exact key is missing |

If you set `matchIfMissing=true`, **only the "Absent" row changes to matching**. A property that is present and equals `false` still does not match.

Why declare `havingValue="true"` explicitly?

~~~java
@ConditionalOnProperty(prefix = "demo.notice", name = "enabled")
~~~

When `havingValue` is omitted, the default rule is **the key exists and its value is anything other than `false`**. An unexpected value such as `on` or `unexpected` could still be treated as a match. For a feature flag genuinely expecting a boolean, use standard `true/false` values and an explicit condition.

**Watch out for two conversion semantics:** `@ConfigurationProperties` has a mechanism converting strings into Java types (e.g., boolean), whereas `@ConditionalOnProperty` compares property values according to the annotation's rules. Do not rely on undocumented boolean aliases; use `true` / `false` in config files and tests to ensure both the condition and binder agree.

## 5. Designing for Consistency in Source Code: Centralize Key Names

When multiple classes in a library depend on the same key, you can declare **compile-time constants** to prevent typos between conditions and properties:

~~~java
package demo.notice;

public final class NoticeKeys {
    public static final String PREFIX = "demo.notice";
    public static final String ENABLED = "enabled";

    private NoticeKeys() {
    }
}
~~~

Both values above are `public static final` String constants, making them valid inside annotation attributes that require compile-time constants:

~~~java
@ConditionalOnProperty(
    prefix = NoticeKeys.PREFIX,
    name = NoticeKeys.ENABLED,
    havingValue = "true"
)
~~~

and:

~~~java
@ConfigurationProperties(prefix = NoticeKeys.PREFIX)
~~~

Both always use **the same prefix**; property naming must also remain consistent between `ENABLED` and the Java field name `enabled`. Write out the full key `demo.notice.enabled` explicitly once in documentation. Constants prevent certain copy/paste mistakes, yet **cannot replace tests**: one side mistakenly using `ACTIVE` instead of `ENABLED` will still break the contract.

There is no need to create a constants class for every small project. If there are few annotations, direct string literals paired with a clear test suite are equally suitable. The goal is to minimize places where the public key name could accidentally diverge.

## 6. Runnable Example: A Notice Starter Controlled by One Single Key

Build a Spring Boot 3.3.13 / Java 17 Maven application to observe:
- When `demo.notice.enabled` is missing → the starter **does not auto-create** the `NoticeSender` bean;
- When `demo.notice.enabled=false` → not created;
- When `demo.notice.enabled=true` → the bean is created and receives `message` from the same `demo.notice` namespace;
- When the prefix or name is wrong → no bean is created.

The project uses `AutoConfiguration.imports` to simulate a proper auto-configuration library. We use no network connections or external resources. Results can be observed via stdout.

### 6.1. Project Structure

~~~text
notice-toggle-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/
    │   │       ├── app/
    │   │       │   └── NoticeDemoApplication.java
    │   │       └── notice/
    │   │           ├── NoticeKeys.java
    │   │           ├── NoticeProperties.java
    │   │           ├── NoticeSender.java
    │   │           └── autoconfigure/
    │   │               └── NoticeAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── demo/
                └── notice/
                    └── NoticeAutoConfigurationTest.java
~~~

`demo.app` and `demo.notice` are sibling packages, so `@SpringBootApplication` in `demo.app` **does not component-scan** configuration in `demo.notice.autoconfigure`. Configuration is loaded via **AutoConfiguration.imports**, as intended by the lab.

### 6.2. pom.xml

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
    <artifactId>notice-toggle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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

### 6.3. src/main/java/demo/notice/NoticeKeys.java

~~~java
package demo.notice;

public final class NoticeKeys {
    public static final String PREFIX = "demo.notice";
    public static final String ENABLED = "enabled";

    private NoticeKeys() {
    }
}
~~~

This class is where canonical names are defined for annotations. We still must keep published documentation and tests aligned with it.

### 6.4. src/main/java/demo/notice/NoticeProperties.java

~~~java
package demo.notice;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = NoticeKeys.PREFIX)
public class NoticeProperties {
    private boolean enabled = false;
    private String message = "default-message";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
~~~

`enabled=false` is the default **of the Java object**. It matches the opt-in policy; the condition in section 6.6 also uses `matchIfMissing=false`. `message` is a supporting property bound under the same prefix. The `enabled` field name corresponds to the `NoticeKeys.ENABLED` suffix.

Do not merely use `@ConfigurationProperties` and expect Spring to discover every configuration class automatically. In the next section, auto-configuration registers binding via `@EnableConfigurationProperties(NoticeProperties.class)`.

### 6.5. src/main/java/demo/notice/NoticeSender.java

~~~java
package demo.notice;

public record NoticeSender(String message) {
}
~~~

This is a simple service bean giving the lab deterministic output. `record` is a Java 17 feature, requiring no Lombok. Real applications can replace it with a publisher, client, processor, or another adapter.

### 6.6. src/main/java/demo/notice/autoconfigure/NoticeAutoConfiguration.java

~~~java
package demo.notice.autoconfigure;

import demo.notice.NoticeKeys;
import demo.notice.NoticeProperties;
import demo.notice.NoticeSender;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(NoticeProperties.class)
@ConditionalOnProperty(
        prefix = NoticeKeys.PREFIX,
        name = NoticeKeys.ENABLED,
        havingValue = "true",
        matchIfMissing = false
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeSender.class)
    NoticeSender noticeSender(NoticeProperties properties) {
        return new NoticeSender(properties.getMessage());
    }
}
~~~

**Three constraints kept consistent:**

1. `@ConditionalOnProperty` checks the exact `demo.notice.enabled`; only when the value is `true` (and other conditions are met) is this auto-configuration processed.
2. `@EnableConfigurationProperties` binds `NoticeProperties` with the same `demo.notice` prefix. The `NoticeSender` bean receives `message` through this exact object.
3. `@ConditionalOnMissingBean(NoticeSender.class)` skips creating the default bean if the application already has a matching bean of the same type.

In this illustrative design, **the condition sits on the entire auto-configuration class**. When the condition does not match, this configuration **registers neither `NoticeProperties` nor `NoticeSender`** through its declarations. If you want `NoticeProperties` always available to read status even when the feature is disabled, you can move the condition onto a nested configuration class or only onto the `@Bean` method; choose and clearly document the scope to guard.

Note that allowing the application to replace the bean via `@ConditionalOnMissingBean` does not mean a **user-registered** bean gets disabled when `demo.notice.enabled=false`. If "disabling the feature" must apply to all providers, a design consistently controlling custom providers as well is required.

### 6.7. src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

File content is **exactly one line**:

~~~text
demo.notice.autoconfigure.NoticeAutoConfiguration
~~~

The path and FQCN must match exactly. In Spring Boot 3.3, this is the auto-configuration registration mechanism for libraries. Missing the file or misspelling the package means `NoticeAutoConfiguration` may **never be applied**, even when `demo.notice.enabled=true`.

### 6.8. src/main/java/demo/app/NoticeDemoApplication.java

~~~java
package demo.app;

import demo.notice.NoticeSender;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NoticeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoticeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ObjectProvider<NoticeSender> senders) {
        return args -> {
            NoticeSender sender = senders.getIfAvailable();
            System.out.println("noticeSender present: " + (sender != null));
            if (sender != null) {
                System.out.println("noticeSender message: " + sender.message());
            }
        };
    }
}
~~~

`ObjectProvider<NoticeSender>` is the way to obtain an **optional** bean. Using mandatory constructor injection for `NoticeSender` in an always-created bean causes startup to fail when the feature is disabled; that is a consumer design issue not respecting the optional contract, **not a bug in the condition**.

### 6.9. Packaging and Verifying Three States

From the `notice-toggle-demo` directory:

~~~bash
mvn -q -DskipTests package
~~~

**Case A — missing key:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by `System.out.println`:

~~~text
noticeSender present: false
~~~

**Case B — right key, disabled:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.enabled=false
~~~

Line to observe:

~~~text
noticeSender present: false
~~~

**Case C — right key and enabled, with custom message:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.enabled=true --demo.notice.message=custom-message
~~~

Two lines printed by the program:

~~~text
noticeSender present: true
noticeSender message: custom-message
~~~

**Case D — user mistypes prefix:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notification.enabled=true
~~~

Line observed:

~~~text
noticeSender present: false
~~~

Case D shows that a `true` value **is not enough**; it must belong to **the exact key checked by the condition**. The outputs above are lines deliberately printed by the program; Maven or startup logs may differ by environment.

In PowerShell and Windows CMD you can run these one-line Java commands verbatim; when using the Maven wrapper, replace `mvn` with `mvnw.cmd` if the project provides it.

## 7. Testing with ApplicationContextRunner: Protecting the Public Key Contract

A starter should include tests for bean selection itself. In Spring Boot, `ApplicationContextRunner` lets you run minimal contexts with varying properties and assert outcomes. This test does not require starting a full web server, while catching mistakes such as accidentally changing `prefix` in an annotation.

**File: `src/test/java/demo/notice/NoticeAutoConfigurationTest.java`**

~~~java
package demo.notice;

import demo.notice.autoconfigure.NoticeAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    NoticeAutoConfiguration.class
            ));

    @Test
    void missingEnabledDoesNotCreateSender() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(NoticeSender.class));
    }

    @Test
    void falseDoesNotCreateSender() {
        runner.withPropertyValues("demo.notice.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeSender.class));
    }

    @Test
    void trueCreatesSenderAndBindsMessage() {
        runner.withPropertyValues(
                "demo.notice.enabled=true",
                "demo.notice.message=custom-message"
        ).run(context -> {
            assertThat(context).hasSingleBean(NoticeSender.class);
            NoticeSender sender = context.getBean(NoticeSender.class);
            assertThat(sender.message()).isEqualTo("custom-message");
            assertThat(context.getBean(NoticeProperties.class).isEnabled())
                    .isTrue();
        });
    }

    @Test
    void wrongPrefixDoesNotEnableSender() {
        runner.withPropertyValues("demo.notification.enabled=true")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeSender.class));
    }

    @Test
    void unknownStringDoesNotEnableSender() {
        runner.withPropertyValues("demo.notice.enabled=unexpected")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeSender.class));
    }
}
~~~

With `spring-boot-starter-test` in the pom, run:

~~~bash
mvn test
~~~

Expected: **5 tests PASS**. The cases provide evidence of **right key, right prefix, right value, right missing-key policy, and message properly bound into the created bean**. The test uses `@ConditionalOnProperty(havingValue="true")`, so the value `unexpected` does not match, avoiding creating `NoticeProperties` which could trigger a binding error for an invalid boolean.

### 7.1. What Does Testing a User-Replaced Bean Mean?

With `@ConditionalOnMissingBean(NoticeSender.class)`, if a user registers their own `NoticeSender` bean before auto-config runs, the starter should yield to the user's bean. You can add the following test to the same class:

~~~java
@Test
void userBeanWinsOverDefaultWhenEnabled() {
    runner.withPropertyValues("demo.notice.enabled=true")
            .withBean(NoticeSender.class,
                    () -> new NoticeSender("user-message"))
            .run(context -> {
                assertThat(context).hasSingleBean(NoticeSender.class);
                assertThat(context.getBean(NoticeSender.class).message())
                        .isEqualTo("user-message");
            });
}
~~~

This is an **additional test method** (placed inside `NoticeAutoConfigurationTest` above), not a standalone Java file. It clarifies the contract boundary: when the feature is enabled, the library **does not overwrite** a bean provided by the user.

If the feature is disabled while the user still registers `NoticeSender`, the context may still contain the user's bean. When describing `enabled=false`, state accurately **"the starter does not create `NoticeSender` itself"**, rather than claiming **"the application is guaranteed to have no `NoticeSender`"**.

## 8. Default-On vs. Default-Off: Update as One Consistent Set

### 8.1. Opt-In Policy: Off When Unconfigured

Condition:

~~~java
@ConditionalOnProperty(
    prefix = NoticeKeys.PREFIX,
    name = NoticeKeys.ENABLED,
    havingValue = "true",
    matchIfMissing = false
)
~~~

Value in `NoticeProperties`:

~~~java
private boolean enabled = false;
~~~

Documentation:
- `demo.notice.enabled` omitted → do not auto-create sender.
- `demo.notice.enabled=true` → create sender if other conditions pass.
- `demo.notice.enabled=false` → do not auto-create sender.

Tests must cover both **missing** and **false** to document this policy.

### 8.2. Default-On Policy: On When Unconfigured

If the product requires the library to operate by default, update **together**:

~~~java
@ConditionalOnProperty(
    prefix = NoticeKeys.PREFIX,
    name = NoticeKeys.ENABLED,
    havingValue = "true",
    matchIfMissing = true
)
~~~

and:

~~~java
private boolean enabled = true;
~~~

Then update documentation to "enabled by default; can be disabled with `demo.notice.enabled=false`", and update the missing test to expect `NoticeSender` to **be present**. The `false` test must still expect no bean to be auto-created.

**Common mistake:** changing only the field default in `NoticeProperties` to `true` while leaving `matchIfMissing=false`. At runtime there is still no bean because the condition never matched.

### 8.3. Properties Object Need Not Exist When the Feature Is Off

In the lab design, both `@EnableConfigurationProperties` and `@ConditionalOnProperty` sit on `NoticeAutoConfiguration`. When disabled, this class does not process its registration declarations and `NoticeProperties` is not created by it.

If another module needs to read `NoticeProperties` even when the feature is disabled, you can keep properties binding on the outer class and place the condition on a **nested configuration class**:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(NoticeProperties.class)
public class NoticeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = NoticeKeys.PREFIX,
            name = NoticeKeys.ENABLED,
            havingValue = "true"
    )
    static class SenderConfiguration {

        @Bean
        @ConditionalOnMissingBean(NoticeSender.class)
        NoticeSender noticeSender(NoticeProperties properties) {
            return new NoticeSender(properties.getMessage());
        }
    }
}
~~~

This is an **alternative snippet** for `NoticeAutoConfiguration.java`, using classes/imports from the lab and requiring an extra import for `org.springframework.context.annotation.Configuration`. It illustrates the difference:
- `NoticeProperties` can be registered/bound even when `enabled=false`;
- Only the `NoticeSender` bean sits inside the condition-guarded nested class.

Thus, **the scope where the condition is attached** is also part of the contract. If a condition is at the method level, other methods in the same auto-config are still evaluated under their own conditions.

## 9. Rules for Writing Configuration Documentation for Starter Users

Library users need at least **key name, type, default, effect, and example**, rather than just reading annotations.

Example configuration table to include in the library's README:

| Property | Type | Default | Effect |
| --- | --- | --- | --- |
| `demo.notice.enabled` | Boolean | `false` | `true` allows the starter to auto-create `NoticeSender`; `false` or absent skips it |
| `demo.notice.message` | String | `default-message` | Content the default sender will use when created |

Recommended standard example:

~~~yaml
demo:
  notice:
    enabled: true
    message: "Welcome"
~~~

The description of `enabled` must be accurate:
- **"Allows auto-configuration to provide the default bean"** matches the example.
- **"Deletes all notice beans, including user-created beans"** is incorrect, because the condition does not block beans created by other configurations.
- **"Changing the value at runtime immediately creates/deletes the bean"** is incorrect: bean definitions are normally decided when the application context initializes.

If renaming a public key, consider backward compatibility. For example, switching from `demo.notice.enabled` to `demo.notifications.enabled` can silently disable old applications. A migration strategy must specify how long the old key is supported, which key wins if both appear, tests for each case, and deprecation warnings when using the old key. Never change a condition's prefix and treat it as an internal refactor.

### 9.1. Configuration Metadata and IDE Suggestions

Spring Boot has a mechanism to generate **configuration metadata** from `@ConfigurationProperties` so tools and IDEs can autocomplete property names. In a library, you can add the annotation processor per your Spring Boot version's guide:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Metadata helps users discover `demo.notice.enabled` and `demo.notice.message` faster. However, metadata **does not enforce** the value of `@ConditionalOnProperty` or force conditions to read the right key name. Bean registration tests are still necessary.

When publishing metadata, make sure actual default descriptions match `NoticeProperties` and `matchIfMissing`. Stale metadata misleads users even when the code works.

## 10. Debugging: User Enabled It Properly, Yet the Bean Does Not Appear

Suppose the config is:

~~~properties
demo.notice.enabled=true
~~~

yet code looking up `NoticeSender` finds nothing. Investigate in order:

1. **Identify the actual condition annotation.** Combine `prefix` and `name` into the FQ property. For example `demo.notice` + `enabled` becomes `demo.notice.enabled`. Inspect the deployed class, not just local source files.
2. **Inspect the effective Environment.** Active profiles, environment variables, and command-line arguments can override `application.yml`. Is the property `true` or overridden to `false` by a higher-precedence source?
3. **Verify auto-configuration is imported.** Spring Boot 3.3 uses `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` for starters. If missing or the FQCN is wrong, the condition is never evaluated.
4. **Use the Condition Evaluation Report.** Run `java -jar app.jar --debug` or inspect Actuator `conditions` (when installed, enabled, and safely exposed). Distinguish *did not find property* and *property has different value* from other conditions.
5. **Check remaining conditions.** `@ConditionalOnClass` may fail due to a missing dependency. `@ConditionalOnMissingBean` may suppress the default bean because the user supplied another bean.
6. **If the condition matches yet the context still fails**, read the `Caused by` chain; the issue may be a missing dependency bean, properties validation failure, an exception thrown by the factory method, or classpath incompatibility.
7. **Test minimally with ApplicationContextRunner.** Pass the exact true/false/missing property set and verify bean registration. If unit tests pass while the deployed app fails, check the real environment, imports, profiles, and application-supplied beans.
8. **Check whether consumers handle the optional feature properly.** A bean that unconditionally injects a required `NoticeSender` even when the feature is disabled will fail; the consumer must be conditionally guarded or use `ObjectProvider` appropriately.

### 10.1. Do Not Confuse Property Binding with Conditions

Example:

~~~java
@ConfigurationProperties(prefix = "demo.notice")
public class NoticeProperties {
    private boolean enabled;
}
~~~

Without `@ConditionalOnProperty` or other logic guarding beans, simply binding `enabled=false` **does not make Spring automatically stop creating beans that use that object**. Conversely, having only `@ConditionalOnProperty` without registering/binding properties does not automatically process `@ConfigurationProperties` either.

Conditions and binding are **two separate actions**, which must be connected by a consistent design.

### 10.2. Do Not Misuse @ConditionalOnMissingBean

`@ConditionalOnMissingBean` exists so **the default bean backs off** when an application-provided bean is present. It is not an on/off switch. A library wanting an opt-in feature still needs an appropriate property condition. Combining both annotations is standard:

~~~java
@Bean
@ConditionalOnMissingBean(NoticeSender.class)
@ConditionalOnProperty(
    prefix = "demo.notice",
    name = "enabled",
    havingValue = "true"
)
NoticeSender noticeSender(NoticeProperties properties) {
    return new NoticeSender(properties.getMessage());
}
~~~

This is an **illustrative method snippet** inside a configuration class with appropriate imports and `NoticeProperties` binding. Placing `@ConditionalOnProperty` on the method guards only `NoticeSender`; placing it on the class guards the entire configuration containing that method.

## 11. Common Design Mistakes

1. **Inconsistent prefix.** Documentation states `demo.notice.enabled` while `@ConditionalOnProperty` reads `demo.notification.enabled`, so enabling per the docs still fails to match.
2. **Confusing `value` with `havingValue`.** In `@ConditionalOnProperty`, `value` is an alias for `name` (the key name), whereas `havingValue` is the value to match against.
3. **Property key and field name differ unintentionally.** Code binds field `enabled` while the condition reads `active`; no clear compatibility strategy exists.
4. **Java default and condition default contradict each other.** `enabled=true` in the object while `matchIfMissing=false` causes an absent key to still create no bean.
5. **Condition placed at the wrong scope.** Condition sits on one bean while remaining feature beans still initialize, even though docs say "turns everything off."
6. **Confusing auto-configured beans with user-created beans.** `enabled=false` does not remove manual beans outside auto-config.
7. **Allowing any value instead of explicit true.** Omitting `havingValue` allows any non-`false` string to accidentally enable the feature.
8. **Forgetting to test both missing and false.** These two states must be tested separately because `matchIfMissing` changes the meaning of missing.
9. **Wrong scope/registration.** Creating the `@AutoConfiguration` class while forgetting the imports file prevents the condition from ever running.
10. **Reading only application.yml.** Effective values may come from profiles, environment variables, system properties, or command-line args.
11. **Consumer unconditionally requiring an optional bean.** Non-optional `@Autowired` breaks the app when the feature is disabled; consumers must honor the contract.
12. **Renaming public keys without migration.** Applications configured with old names can silently lose functionality.
13. **Metadata/README out of sync with code.** IDE suggests one key while the annotation checks another; operational experience breaks.
14. **Treating runtime config changes as dynamic bean toggles.** Conditional bean registration is normally evaluated during context construction, not dynamically created/deleted on file edits.
15. **Overlooking an existing bean.** The condition matched, yet `@ConditionalOnMissingBean` intentionally yielded to a user bean; that can be the right behavior.

## 12. Pre-Release Library Checklist

- [ ] Finalized **a single public name** for the feature flag, e.g., `demo.notice.enabled`.
- [ ] `@ConditionalOnProperty` combines the right `prefix` + `name`; match value is explicitly specified.
- [ ] `@ConfigurationProperties` uses the same namespace and has appropriate fields/validation.
- [ ] `matchIfMissing` accurately reflects the default policy; Java defaults are synchronized.
- [ ] The condition guards **the exact scope** of beans that documentation claims to toggle.
- [ ] User-defined beans are handled cleanly per the override contract.
- [ ] `AutoConfiguration.imports` registers the starter's auto-config class properly.
- [ ] Tests verify **missing**, **false**, **true**, **wrong prefix**, **bound data**, and bean state.
- [ ] README/configuration metadata use the exact same keys, types, defaults, and examples.
- [ ] Behavior verified with higher-precedence property sources, profiles, or key renames.
- [ ] Consumers do not require optional beans in environments where the feature is disabled.
- [ ] Re-ran tests against all Spring Boot and JDK versions supported by the library.

## 13. Self-Check Questions

**Question 1.** Documentation publishes `acme.search.enabled=true`, while the annotation uses `prefix="acme.search"` and `name="active"`. Why does the bean not appear?  
**Answer:** The condition reads `acme.search.active`, not the published key. Names must be unified or a clear migration must be designed.

**Question 2.** `NoticeProperties.enabled` defaults to `true`, while the condition sets `matchIfMissing=false`. When the property is omitted, is the bean created automatically?  
**Answer:** Not through that condition. `matchIfMissing=false` causes the condition not to match when the key is absent, regardless of the Java object's default.

**Question 3.** Is `@ConditionalOnProperty(prefix="demo.notice", value="enabled", havingValue="true")` equivalent to `name="enabled"`?  
**Answer:** Yes. `value` is an alias for `name`; both specify the key name to check.

**Question 4.** If the library skips creating `NoticeSender` because `enabled=false`, is the context guaranteed to have no `NoticeSender` bean?  
**Answer:** No. The application can still declare a bean of the same type itself. The contract must state the condition's scope clearly.

**Question 5.** When releasing a starter, which test directly catches an accidental prefix refactor?  
**Answer:** A test setting **the public key** `demo.notice.enabled=true` and asserting the bean is created, paired with a test setting a wrong prefix and asserting no bean is created. Do not use internal constants for test inputs if you want to catch user-facing contract regressions.

**Question 6.** How do you support default-on consistently?  
**Answer:** Set `matchIfMissing=true`, set sensible properties defaults, update documentation, and update the missing-key test; still allow `false` to disable the feature.

**Question 7.** Why not just put `enabled` in `@ConfigurationProperties` and treat it as an automatic Spring condition?  
**Answer:** Property binding only populates values into an object; controlling bean registration requires a condition or corresponding control mechanism.

## 14. Conclusion and References

To keep toggle keys consistent with generated configuration, treat `enabled` as **the library's public interface**. Key name, default value, controlled bean scope, binding process, and documentation/tests together describe **one single behavior**. When a feature is enabled yet no bean is created, check the effective key name in `Environment`, conditions, and auto-configuration registration before blaming bean or dependency errors.

Official documentation to reference when implementing against specific Spring Boot versions:

1. [Spring Boot Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
2. [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html).
3. [Spring Boot Reference — Externalized Configuration and @ConfigurationProperties](https://docs.spring.io/spring-boot/reference/features/external-config.html).
4. [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/reference/configuration-metadata/index.html).
5. [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).