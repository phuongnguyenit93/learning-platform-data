# Distinguishing Missing Properties, Empty Strings, and `false` Values

## 1. Lesson Objectives

In Spring Boot Auto Configuration, a configuration can be enabled or skipped based on `@ConditionalOnProperty`. The three states most easily confused are:

1. **Missing property:** `Environment` cannot resolve a value for the queried key; for example, `demo.feature` does not exist in any effective configuration source.
2. **Present property with an empty string value:** the key `demo.feature` has the value `""`, i.e., a string of length 0. This is still a supplied value.
3. **Property with value `false`:** the key has the string value `"false"` when Spring Boot checks the condition. This is a specific value, **not** "no value".

Practical goal: accurately predict when `@ConditionalOnProperty` matches, understand the roles of `havingValue` and `matchIfMissing`, and know when a custom `Condition` is needed to distinguish **strictly an empty string** from every other value.

This lesson examines **property conditions** in Spring Boot 3.3.x. What is evaluated is the value from `Environment` at configuration-processing time, not a Java boolean variable being injected and not whether another bean exists.

## 2. Same Key, Three Different States

Suppose the application uses the key `demo.feature`.

### 2.1. Missing

In `application.properties`, there is **no** `demo.feature` line; and other configuration sources (startup arguments, environment variables, profiles, etc.) do not supply that key either.

```properties
# demo.feature is not declared
demo.display-name=Example
```

Then:

- `environment.getProperty("demo.feature")` returns `null` if no value is resolved.
- `@ConditionalOnProperty(name = "demo.feature")` **does not match** by default.
- `matchIfMissing = true` is the dedicated parameter to allow the condition to match in this case.

**Note:** omitting the key in *one* file is not enough to conclude "missing". If the command line, an environment variable, or another effective source provides a value, the key is still considered to have a value.

### 2.2. Empty string

In `application.properties`:

```properties
demo.feature=
```

Or in `application.yml`, explicitly write an empty string:

```yaml
demo:
  feature: ""
```

The expected result is the string value `""` with length 0. The key is present in the configuration source and is not treated as missing just because there are no characters after the equals sign. Writing `feature: ""` in YAML helps avoid ambiguity with a YAML `null` value.

With Spring Boot 3.3, `@ConditionalOnProperty(name = "demo.feature")` **matches** when the value is `""`, because the default check only rejects the exact string `"false"` (case-insensitive); `""` differs from `"false"`.

This often causes surprises: a "left blank" configuration can **enable** auto-configuration if only the default condition is used.

### 2.3. Value `false`

In `application.properties`:

```properties
demo.feature=false
```

Or in `application.yml`:

```yaml
demo:
  feature: false
```

The value used for the check corresponds to the string `"false"`. Then:

- Default condition `@ConditionalOnProperty(name = "demo.feature")` **does not match**.
- Condition `@ConditionalOnProperty(name = "demo.feature", havingValue = "false")` **matches**.
- `matchIfMissing = true` does **not** turn `false` into true; that option only takes effect when the value is actually missing.

Do not confuse the three concepts: **missing = no value can be resolved**, **empty = has a string of length 0**, **false = has a string containing "false"**.

## 3. Exact Mechanism of `@ConditionalOnProperty`

Example:

```java
@ConditionalOnProperty(prefix = "demo", name = "feature")
@Configuration(proxyBeanMethods = false)
class FeatureAutoConfiguration {
    // Beans here are only processed when the condition matches.
}
```

Spring Boot forms the full key from `prefix` and `name`: `demo.feature`. In terms of outcome, the decision for one key can be visualized as follows:

```text
                  Read demo.feature from Environment
                                |
                    Is there a resolvable value?
                         /                 \
                       No                  Yes
                        |                   |
             Return matchIfMissing     Check havingValue
                                            |
                            Is havingValue a non-empty string?
                                 /                 \
                                No                 Yes
                                |                   |
                    Value DIFFERS from "false"?  Value EQUALS havingValue?
                                |                   |
                              Result              Result
```

This expresses how `OnPropertyCondition` matches in Spring Boot 3.3: case-insensitive string comparison for `"false"` and `havingValue`.

**Two important defaults:**

- `havingValue = ""`: default. Does **not** mean "only match when the value is an empty string"; its meaning is **value is present and differs from `"false"`**.
- `matchIfMissing = false`: default. When the key is missing, the condition does not match, **regardless** of what value `havingValue` holds.

With `@ConditionalOnProperty(prefix = "demo", name = "feature")`, the questions in order are "is there a value?" and then "does that value differ from `false`?". There is no step converting to boolean in the usual "truthy/falsy" sense.

### 3.1. Truth table to remember

The columns illustrate these five ways of declaring it:

- **Default**: `@ConditionalOnProperty(name = "demo.feature")`.
- **Only true**: `@ConditionalOnProperty(name = "demo.feature", havingValue = "true")`.
- **Only false**: `@ConditionalOnProperty(name = "demo.feature", havingValue = "false")`.
- **Default + allow missing**: `@ConditionalOnProperty(name = "demo.feature", matchIfMissing = true)`.
- **Only true + allow missing**: `@ConditionalOnProperty(name = "demo.feature", havingValue = "true", matchIfMissing = true)`.

| Resolved value | Default | Only true | Only false | Default + allow missing | Only true + allow missing |
| --- | :---: | :---: | :---: | :---: | :---: |
| Missing (`null`) | No | No | No | **Yes** | **Yes** |
| Empty string `""` | **Yes** | No | No | **Yes** | No |
| `"false"` | No | No | **Yes** | No | No |
| `"FALSE"` | No | No | **Yes** | No | No |
| `"true"` | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `"off"` | **Yes** | No | No | **Yes** | No |
| `"0"` | **Yes** | No | No | **Yes** | No |
| `" "` (single space) | **Yes** | No | No | **Yes** | No |

This table is considered in the context of the string value returned by `Environment`. `"off"` and `"0"` do not equal the literal `"false"`, so **the default condition still matches**, even though another boolean binding mechanism might interpret them as false. `" "` is neither an empty string nor equal to `"false"`.

**Rules for `havingValue`:**

- If it is a **non-empty** string, Spring Boot compares the resolved value against that string (case-insensitive).
- If it is `""` (default or explicitly written), it uses the "not `false`" branch, rather than checking "equals empty string".
- If the value is missing, `matchIfMissing` decides first; therefore `havingValue = "true", matchIfMissing = true` **still matches when missing**.

### 3.2. Comparison with boolean conversion

The two statements below are **not equivalent in all cases**:

```java
@ConditionalOnProperty(name = "demo.feature")
```

and:

```java
Boolean enabled = environment.getProperty(
    "demo.feature", Boolean.class
);
```

The first is Spring Boot's own condition: with values `"off"` or `"0"`, the default condition can match because the string differs from `"false"`. The second asks `Environment`'s type converter to interpret a string as boolean, which has different rules; the result can also be `null` when the key is missing.

If `demo.feature` is genuinely an on/off switch, you typically choose:

```java
@ConditionalOnProperty(
    prefix = "demo",
    name = "feature",
    havingValue = "true",
    matchIfMissing = false
)
```

Then only an explicit `true` value enables the feature. Do not use the default condition and implicitly expect `off`, `0`, or an empty value to turn the feature off.

## 4. Choosing the Condition Based on Business Requirements

| Requirement | Declaration / check | Missing | Empty | False |
| --- | --- | --- | --- | --- |
| Enable when key has a value other than literal `false` | `@ConditionalOnProperty(name = "demo.feature")` | Off | **On** | Off |
| Enable only when configuration is `true` | `havingValue = "true"` | Off | Off | Off |
| Run separate branch when configuration is `false` | `havingValue = "false"` | Off | Off | **On** |
| Enabled by default if undeclared, but `false` disables | `matchIfMissing = true` | **On** | **On** | Off |
| Process only when key exists **and is strictly empty** | Custom `Condition` comparing `"".equals(environment.getProperty(key))` | Off | **On** | Off |

**You cannot use `havingValue = ""` to select only the empty string.** In Spring Boot 3.3, that value is the marker for default mode and matches `true`, `yes`, `off`, `0`, etc., if those values are seen as strings other than `false`.

If you need to distinguish "not configured" from "configured but left empty", read the resolved value and check separately: `value == null` for missing and `"".equals(value)` for empty string. If you need to distinguish an explicitly declared `null` value in a specific configuration source type, check the conversion rules and ordering of `PropertySource`s; do not infer from YAML appearance or environment variable names.

## 5. Standalone Runnable Java 17+ Example: Observing All States

The example uses Spring Boot **3.3.5** (a released 3.3.x version) with `AnnotationConfigApplicationContext`. Each run creates a new application context; a simulated configuration source is added before `refresh()`. All conditions are placed on **configuration classes**, so only the corresponding beans are created.

Directory structure:

```text
property-state-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PropertyStatesDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>property-state-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
            <version>3.3.5</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/PropertyStatesDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class PropertyStatesDemo {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(prefix = "demo", name = "feature")
    static class DefaultConfig {
        @Bean("defaultBean")
        String defaultBean() {
            return "default";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
        prefix = "demo", name = "feature", havingValue = "true"
    )
    static class TrueConfig {
        @Bean("trueBean")
        String trueBean() {
            return "true";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
        prefix = "demo", name = "feature", havingValue = "false"
    )
    static class FalseConfig {
        @Bean("falseBean")
        String falseBean() {
            return "false";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
        prefix = "demo", name = "feature", matchIfMissing = true
    )
    static class MissingAllowedConfig {
        @Bean("missingAllowedBean")
        String missingAllowedBean() {
            return "missing-allowed";
        }
    }

    // @ConditionalOnProperty(havingValue = "") does not mean
    // "only when empty", so use a custom Condition if needed.
    static final class ExactEmptyCondition implements Condition {
        @Override
        public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
        ) {
            return "".equals(
                context.getEnvironment().getProperty("demo.feature")
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Conditional(ExactEmptyCondition.class)
    static class ExactEmptyConfig {
        @Bean("exactEmptyBean")
        String exactEmptyBean() {
            return "exact-empty";
        }
    }

    private static void scenario(String label, String value) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            if (value != null) {
                context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                        "scenario",
                        Map.of("demo.feature", value)
                    )
                );
            }
            // value == null represents "do not add this key".
            // Configuration classes are registered after Environment is set.
            context.register(
                DefaultConfig.class,
                TrueConfig.class,
                FalseConfig.class,
                MissingAllowedConfig.class,
                ExactEmptyConfig.class
            );
            context.refresh();

            System.out.printf(
                "%s: default=%s, true=%s, false=%s, " +
                "missingAllowed=%s, exactEmpty=%s%n",
                label,
                context.containsBean("defaultBean"),
                context.containsBean("trueBean"),
                context.containsBean("falseBean"),
                context.containsBean("missingAllowedBean"),
                context.containsBean("exactEmptyBean")
            );
        }
    }

    public static void main(String[] args) {
        scenario("missing", null);
        scenario("empty", "");
        scenario("false", "false");
        scenario("FALSE", "FALSE");
        scenario("true", "true");
        scenario("off", "off");
        scenario("zero", "0");
        scenario("space", " ");
    }
}
```

With **JDK 17+**, **Maven 3.8+**, and permission to download dependencies, run inside the `property-state-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.PropertyStatesDemo
```

Eight lines printed by the program (excluding messages from Maven or the environment):

```text
missing: default=false, true=false, false=false, missingAllowed=true, exactEmpty=false
empty: default=true, true=false, false=false, missingAllowed=true, exactEmpty=true
false: default=false, true=false, false=true, missingAllowed=false, exactEmpty=false
FALSE: default=false, true=false, false=true, missingAllowed=false, exactEmpty=false
true: default=true, true=true, false=false, missingAllowed=true, exactEmpty=false
off: default=true, true=false, false=false, missingAllowed=true, exactEmpty=false
zero: default=true, true=false, false=false, missingAllowed=true, exactEmpty=false
space: default=true, true=false, false=false, missingAllowed=true, exactEmpty=false
```

**Explanation:**

1. `missing`: the method does not add a property source for `demo.feature`. Only the `matchIfMissing = true` condition is accepted.
2. `empty`: the key exists and the value `""` differs from `false`, so both `DefaultConfig` and `MissingAllowedConfig` are activated. The custom condition matches the exact empty string.
3. `false` and `FALSE`: the `havingValue = "false"` condition matches; the default condition does not match, proving case-insensitive comparison.
4. `true`: the default condition, `havingValue = "true"`, and `matchIfMissing = true` all match.
5. `off` and `zero`: the default condition still matches because the string value does not equal `false`. This is **not** boolean conversion as in Java or `Binder`.
6. `space`: the string containing a single space differs from `""`; therefore the custom `ExactEmptyCondition` does not match. It also differs from literal `false`, so the default condition matches.

**Example scope:** this is a plain Spring Context program using Spring Boot conditional annotations to observe the rules. In a real starter/auto-configuration, you can use `@AutoConfiguration` and declare it in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; property matching logic follows the same rules.

## 6. Using in Real Auto-Configuration

Suppose a starter has a notification-sending feature; it must not send unintended notifications if the user leaves configuration blank.

### 6.1. "Enable only when true" design

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "notifications",
    name = "enabled",
    havingValue = "true"
)
public class NotificationAutoConfiguration {
    // @Bean NotificationSender ...
}
```

This is an **illustrative snippet**, assuming related beans and dependencies are already defined. The default value of `matchIfMissing` is `false`, so both missing and empty do not activate. In `application.properties`:

```properties
notifications.enabled=true
```

Setting `false` or leaving blank both disable it. This is safer for a switch requiring the user to explicitly enable it.

### 6.2. "Enabled by default, only false disables" design

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "notifications",
    name = "enabled",
    matchIfMissing = true
)
public class NotificationAutoConfiguration {
    // @Bean NotificationSender ...
}
```

With this design, missing means using the **on** default. However, empty is also **on** because it is an existing value differing from `false`; that can be surprising if operators think a blank entry means off. If the expectation is "missing turns on, but empty turns off", `@ConditionalOnProperty` alone cannot express the entire requirement; define a concrete `Condition` and test all three states.

### 6.3. Combining multiple keys

```java
@ConditionalOnProperty(
    prefix = "notifications",
    name = {"enabled", "remote"},
    havingValue = "true"
)
```

The condition matches when **both** keys `notifications.enabled` and `notifications.remote` resolve to `true`. If one key is missing (with default `matchIfMissing = false`), empty, or false, the condition does not match. Do not interpret `name = {a, b}` as "just one of the two".

### 6.4. Configuration source differences

The same final value can come from `application.properties`, `application.yml`, profiles, environment variables, external config systems, or the command line. `@ConditionalOnProperty` inspects the **final value resolved by `Environment`**, after configuration-source precedence; it does not check whether a literal line exists in a single file.

For example, starting a complete Spring Boot application with:

```bash
java -jar app.jar --notifications.enabled=
```

will set an empty command-line value for the corresponding key if the app uses the default configuration for command-line arguments. Hence "not written in a file" and "set empty via command-line argument" create two different situations. Do not assume all operating systems/CI preserve empty environment variables in the same way; when testing, use `MapPropertySource` as in the example to control states explicitly.

## 7. Diagnosing When Results Are Not as Expected

1. **Identify the full key:** `prefix = "demo"`, `name = "feature"` becomes `demo.feature`; per API recommendations, configuration names should use dashed notation for multiple words (e.g., `my-feature`).
2. **Check the actual value:** read `environment.getProperty("demo.feature")`. `null`, `""`, `"false"`, and `"False"` cannot be accurately inferred just from the display UI of a configuration screen. When values are sensitive, do not log actual contents to logging systems.
3. **Check condition parameters:** is `havingValue` declared, or is the default `""` being used? Is `matchIfMissing` actually true?
4. **Check property sources:** a profile, environment variable, or command line may be overriding the value in `application.yml`. Use an isolated test context to eliminate environment dependencies.
5. **Inspect the Condition Evaluation Report:** with a full Spring Boot app, you can enable `--debug` to see why auto-configuration conditions matched or did not match; Actuator `/actuator/conditions` also helps when the endpoint is installed and configured appropriately.
6. **Test accurately:** separate the three scenarios missing/empty/false instead of only testing true/false. Also test `"off"` and `"0"` if data is received from users or multiple configuration systems.

Do not confuse Spring **binding** a property into a `boolean`/`Boolean` variable in `@ConfigurationProperties` with `@ConditionalOnProperty` matching strings. The two components serve different purposes and do not necessarily share the same semantics for every notation of false.

## 8. Common Mistakes

| Misconception | Reality / fix |
| --- | --- |
| "Undeclared" and "declared `key=`" are the same | Missing yields a resolved value of `null`; `key=` usually produces string `""`. Test each case separately. |
| `havingValue = ""` is used to require empty | In Boot 3.3 it is still default mode: present and different from `"false"`. For **empty only**, use a custom `Condition`. |
| `matchIfMissing = true` makes every value match | It only changes the missing branch; a `false` value still fails with the default condition. |
| `"off"` or `"0"` definitely turns off `@ConditionalOnProperty` | Under default string matching, they differ from `"false"` so they match. For explicit on/off, use `havingValue = "true"`. |
| `havingValue = "false"` means "missing or false" | It only matches when the value is literally `false`; to also match missing, consider `matchIfMissing = true`. |
| Key absent from `application.yml` means condition sees missing | Another source can still provide a value; evaluate the merged `Environment`. |
| Value `" "` is an empty string | That is a one-character whitespace string; if trimming is desired, clarify business rules and check explicitly. |
| Two names in `name` mean OR | They combine via AND: all keys must satisfy the condition. |
| Using one property match to check an array/list | `@ConditionalOnProperty` is unreliable for all indexed collection forms; use a custom condition when needed. |

## 9. Self-Check Questions

**Question 1.** With `@ConditionalOnProperty(name = "demo.feature")`, evaluate in order: `demo.feature` missing, `demo.feature=`, and `demo.feature=false`.  
**Answer:** No match, match, no match. Missing uses `matchIfMissing = false`; empty is a present string different from `false`.

**Question 2.** Does `@ConditionalOnProperty(name = "demo.feature", havingValue = "false")` match if the key does not exist?  
**Answer:** No, because `matchIfMissing` defaults to false. It matches when the key is present with string `false`, including `FALSE`.

**Question 3.** Does `@ConditionalOnProperty(name = "demo.feature", havingValue = "true", matchIfMissing = true)` match when the key is missing?  
**Answer:** Yes. `matchIfMissing = true` applies to the missing branch, even when `havingValue` is declared.

**Question 4.** Why does `havingValue = ""` not help select an empty string?  
**Answer:** The empty string is the special default value of the `havingValue` parameter; Spring Boot interprets it as "value differs from literal `false`", not equality with `""`. A `Condition` checking `"".equals(...)` is needed if exact empty is the goal.

**Question 5.** Why can `demo.feature=off` enable the default auto-configuration?  
**Answer:** Because the default condition checks for a string other than `false`, while `off` does not equal `false`. Use `havingValue = "true"` for a flag that should only be enabled when confirmed true.

## 10. Takeaways and Official Documentation

- **Missing:** no value can be resolved → does not match by default; `matchIfMissing` decides exceptions.
- **Empty:** has value `""` → **matches the default condition**, does not match `havingValue = "true"` or `"false"`.
- **False:** has value `"false"` → does not match by default; matches `havingValue = "false"`.
- **Require enabling only when true:** choose `havingValue = "true"`, explicitly define policy for missing.
- **Require matching only empty strings:** use a `Condition` with an exact check and tests.
- **Source of truth at evaluation time:** the final value resolved by Spring `Environment`, not a single configuration file.

References:

1. Spring Boot 3.3 — [`@ConditionalOnProperty` API and `havingValue` table](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
2. Spring Boot 3.3 — [Creating Your Own Auto-configuration / Property Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
3. Spring Boot 3.3.5 — [official release announcement](https://spring.io/blog/2024/10/24/spring-boot-3-3-5-available-now/).