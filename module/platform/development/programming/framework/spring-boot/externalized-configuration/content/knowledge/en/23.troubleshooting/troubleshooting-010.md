# Distinguishing Auto-Configuration Condition Reports from Actual Property Value Evidence — Spring Boot 3.3

## 1. Problem: A "Matched" Condition Does Not Tell the Whole Configuration Story

When a Spring Boot application starts, you sometimes see:

```text
Positive matches:
    SomeAutoConfiguration matched
Negative matches:
    OtherAutoConfiguration did not match
```

Or call:

```http
GET /actuator/conditions
```

and receive a report showing whether auto-configuration conditions evaluated to true or false.

This information is useful to answer:

> Why did Spring Boot allow or disallow a configuration/bean to be created?

However, it **does not directly answer**:

> What is the final value of `app.payment.timeout`, which file did it come from, did an environment variable override it, and what value did the `@ConfigurationProperties` object receive?

Those are two separate questions. A condition report might mark a class "matched" because `@ConditionalOnClass` found a library, having nothing whatsoever to do with the `timeout` value. Even when the condition is `@ConditionalOnProperty`, a "matched" outcome only means **the condition evaluated to true at evaluation time**, not a dump of all configuration sources and values.

This lesson belongs to the **Troubleshooting** group of **Spring Boot Externalized Configuration**, targeting **Spring Boot 3.3.x and Java 17+**.

### Objectives

- Understand the structure and practical meaning of the **Condition Evaluation Report**.
- Know when to use `--debug` and the `/actuator/conditions` endpoint.
- Understand `positiveMatches`, `negativeMatches`, and `unconditionalClasses`.
- Distinguish `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean`.
- Know why `matchIfMissing=true` can match even when a property does not exist.
- Look up effective values with `Environment#getProperty` and sources with `/actuator/env`.
- Inspect bound beans with `/actuator/configprops`.
- Cross-check a key across `application.yaml`, environment variables, Java system properties, and CLI.
- Distinguish startup snapshots from later `Environment` mutations or business state.
- Use tests to prove **both conditions and source values**, rather than guessing from logs.
- Avoid exposing secrets when enabling diagnostic endpoints.

## 2. Map of Diagnostic Tools

| Tool | Primary question | Does not directly prove |
| --- | --- | --- |
| Spring Boot `--debug` | Why did auto-configurations/conditional configurations match or not match at startup? | Final values of all properties, per-key sources |
| `/actuator/conditions` | Which conditions matched/did not match in reported contexts? | Full `PropertySource`s and precedence order |
| `ConditionEvaluationReport` | Programmatic condition evidence for a Spring context | All bound values or external system state |
| `Environment#getProperty("key")` | Value the property resolver gets from `Environment` at read time | Whether `@ConfigurationProperties` bound/validated properly |
| `/actuator/env` | `PropertySource`s, active profiles, and origins when available | What data every bean received |
| `/actuator/env/{name}` | Effective value, winning source, and candidate sources when supported | Whether a condition successfully created a bean |
| `/actuator/configprops` | `@ConfigurationProperties` beans, bound structure, and inputs/origins when available | Variables read manually via `@Value`/`System.getenv` |
| `/actuator/beans` | Actual beans present in reported contexts | Full reasons for every condition or where values came from |
| Tests using `SpringApplication.run` | Config Data loading and bean creation behavior on real startup | Post-startup changes or production dependencies outside tests |

A logical workflow is usually:

```text
Symptom:
  feature disabled / bean missing / wrong timeout
                 |
                 v
1. conditions:
   was the bean/configuration allowed to be created?
                 |
                 v
2. env:
   what effective value does the key have, and which source wins?
                 |
                 v
3. configprops:
   what did the configuration object receive after binding?
                 |
                 v
4. beans + runtime:
   does the bean actually exist, and does behavior meet requirements?
```

Not every application needs all four endpoints enabled. In sensitive environments, a local test or restricted-access diagnostic mechanism is usually safer.

## 3. What Is the Condition Evaluation Report?

In Spring Boot, many auto-configurations carry conditions:

```java
@ConditionalOnClass(...)
@ConditionalOnBean(...)
@ConditionalOnMissingBean(...)
@ConditionalOnProperty(...)
@ConditionalOnWebApplication
```

They help Spring decide which configurations apply in a particular application.

The Condition Evaluation Report records evaluation outcomes saved by the framework while processing configuration. Example:

```text
ExampleAutoConfiguration matched:
  - @ConditionalOnClass found required class ...

ExampleJdbcAutoConfiguration did not match:
  - @ConditionalOnBean did not find bean ...
```

Because it is a **condition report**, it does not necessarily mention the value of `app.worker.max-retries`, even if that property exists in `application.properties`.

A condition can match because:

- A specific class exists on the classpath.
- No bean of a matching type exists.
- Another bean exists.
- The app is a web application.
- A property is present or meets `havingValue`.
- A resource is present.
- A profile matches.
- A custom condition expression returns true.

**Do not collapse every condition into a property-name check.**

### 3.1. "Matched" Does Not Equal "Bean Actually Exists"

A configuration class whose conditions match may declare beans with **additional method-level conditions**. A bean can still be skipped, replaced by custom configuration, or startup can fail for another reason.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.ExternalClient")
class ExternalClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

`ExternalClientAutoConfiguration` matching `@ConditionalOnClass` does not prove `externalClient()` definitely created a bean. If a matching bean already exists, `@ConditionalOnMissingBean` will not match.

To know whether the final bean exists, inspect the Spring context or `/actuator/beans`. To know why it was not created, inspect conditions at both the configuration class level **and** bean method level.

### 3.2. "Did Not Match" Does Not Equal "Property Does Not Exist"

An auto-configuration can fail to match due to a missing class or missing bean, even though the related property was declared accurately.

For example, the app writes:

```properties
app.cache.enabled=true
```

yet the required cache library is missing from the classpath. `@ConditionalOnClass` can fail, so cache configuration is not applied. That does not mean `app.cache.enabled` was removed from `Environment`.

Separate the two pieces of evidence:

```text
condition:   cache library absent
environment: app.cache.enabled=true
```

Both facts are simultaneously true and together explain the symptom.

## 4. `positiveMatches`, `negativeMatches`, `unconditionalClasses`

Spring Boot 3.3's `/actuator/conditions` endpoint returns a `contexts` object. Each context can contain:

- `positiveMatches`: conditions that matched.
- `negativeMatches`: configurations/methods whose conditions were not fully met.
- `unconditionalClasses`: auto-configuration classes reported without conditions.
- `parentId`: if the context has a parent/child relationship.

Illustrative shortened JSON:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "ExampleAutoConfiguration#enabledBean": [
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty (app.feature.enabled=true) matched"
          }
        ]
      },
      "negativeMatches": {
        "OtherAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnClassCondition",
              "message": "Did not find a required class"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": [
        "ExampleBaseAutoConfiguration"
      ]
    }
  }
}
```

**This is illustrative JSON**, not a capture from a specific application. Exact messages and class lists depend on the classpath, auto-configurations, and Boot version.

### 4.1. Why Does a Negative Match Have Two Lists?

A configuration can have **multiple conditions**. It is not applied if a required condition fails, even while some of its other conditions passed.

Therefore `negativeMatches` can contain:

```text
notMatched: conditions that failed
matched:    conditions that passed
```

If you only glance at a "Negative matches" line, you can miss that the classpath was fine while an additional bean or property was missing.

### 4.2. Multiple Application Contexts

An application can have a management context separate from the main application context or a parent-child hierarchy. The endpoint has a `contexts` field, not one single global condition set.

When investigating endpoints or beans in the management context, inspect **the exact context ID**. Do not apply conclusions from the `application` context onto another context.

### 4.3. Unconditional Does Not Mean "Business Logic Executed Properly"

A class appearing in `unconditionalClasses` means it was reported as an unconditional class under the endpoint schema, **not** a guarantee that a particular bean works properly or external APIs are ready.

## 5. How to Get the Condition Report with `--debug`

When running a Spring Boot app from a JAR:

```bash
java -jar app.jar --debug
```

Spring Boot can print the **Conditions Evaluation Report** into startup logs.

With Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

With Gradle `bootRun`:

```bash
./gradlew bootRun --args='--debug'
```

On PowerShell, Gradle variant:

```powershell
.\gradlew.bat bootRun '--args=--debug'
```

The crucial point is that `--debug` **is passed to the Spring Boot application**, not the command:

```bash
./gradlew bootRun --debug
```

which enables logging on Gradle itself. The two commands are not equivalent.

### 5.1. When the Report Is Emitted

Spring Boot writes the report in relevant startup scenarios; when debug is enabled, it provides auto-configuration condition evaluation info. The report reflects conditions evaluated during startup, not a continuously updated log per request.

If configuration fails before reaching the stage where the relevant condition is evaluated, logs may not contain everything you expect.

### 5.2. Distinguish Debug Logs from the Source of Truth

A log snippet:

```text
FeatureAutoConfiguration matched:
  - @ConditionalOnProperty (app.feature.enabled) matched
```

is evidence that the condition passed when the framework evaluated it. However, to prove `app.feature.enabled` ultimately holds `true` in the running `Environment`, read the property from the exact process/context.

If a property changes after the condition was evaluated, the previously written report does not recompute itself to reflect a dynamically mutated application.

### 5.3. Debug Reports Can Be Very Long

An app with several starters produces hundreds of conditions. Instead of reading every class:

1. Search for the relevant auto-configuration name.
2. See which condition failed or matched.
3. Identify the property name if the condition uses a property.
4. Cross-check the property against real data sources.
5. Inspect the resulting bean.

Do not edit a YAML file simply because an unrelated condition shows up under "Negative matches."

## 6. `@ConditionalOnProperty`: One Annotation with Many Nuances

Spring Boot 3.3 provides:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
```

Example:

```java
@ConditionalOnProperty(
    prefix = "app.notify",
    name = "enabled",
    havingValue = "true"
)
```

This condition inspects the effective property `app.notify.enabled` per the annotation's rules.

However, if `havingValue` is omitted:

```java
@ConditionalOnProperty(
    prefix = "app.notify",
    name = "enabled"
)
```

then **not only `true` matches**. Per Javadoc, by default the property must exist and have a value **not equal to `"false"`**.

### 6.1. Basic Outcome Table

| Present property value | `havingValue=""` (default) | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | --- | --- | --- | --- |
| `"true"` | match | match | no | no |
| `"false"` | no | no | match | no |
| `"foo"` | match | no | no | match |

Example:

```properties
app.notify.enabled=maybe
```

With the default annotation lacking `havingValue`, the condition can **match** even though `maybe` is not a valid boolean for a `boolean` field.

When the exact intent is enabling by boolean, specify:

```java
havingValue = "true"
```

and consider Boolean binding/validation in formal configuration.

### 6.2. `matchIfMissing`

By default:

```java
matchIfMissing = false
```

meaning if the property does not exist, the condition does not match.

However:

```java
@ConditionalOnProperty(
    prefix = "app.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

can match **when `app.notify.enabled` is completely absent**.

Thus, a condition report saying "matched" is not proof that the property exists in `Environment`, let alone proof that it came from `application.yaml`.

Logic table:

| Property `app.notify.enabled` | Annotation with `havingValue="true"`, `matchIfMissing=false` | With `matchIfMissing=true` |
| --- | --- | --- |
| `"true"` | match | match |
| `"false"` | no match | no match |
| Absent | no match | match |

### 6.3. Conditions Do Not Reliably Check Every Collection

Spring Boot 3.3's `@ConditionalOnProperty` Javadoc notes that it is not reliable for checking the presence of collection-style properties.

Example:

```properties
app.notify.channels[0]=email
```

does not guarantee a condition checking:

```java
@ConditionalOnProperty(name = "app.notify.channels")
```

will match. An element key and a collection parent key are not always treated as a scalar value by the property resolver.

For collection-dependent logic, use another condition type or validation suited to bound data, rather than relying on a scalar condition to conclude a list has elements.

## 7. Distinguish `@ConditionalOnProperty` from `@ConfigurationProperties`

Two annotations easily confused because both contain "Property/Properties."

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true")
```

answers the question:

> Should this conditional configuration or bean be enabled/created?

Whereas:

```java
@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout
) {}
```

answers the question:

> How are values under `app.notify.*` converted and bound into a Java object?

Key differences:

| `@ConditionalOnProperty` | `@ConfigurationProperties` |
| --- | --- |
| Used for conditional decisions | Used to bind typed configuration |
| Has `havingValue`, `matchIfMissing` | Has type conversion, nested binding rules |
| Reported via conditions | Inspectable via configprops |
| Not proof a bean has all valid fields | Does not automatically make an auto-configuration match |
| Checked during condition evaluation | Typically bound when creating/initializing the bean |
| Can match when key is missing | Can have defaults/validation making Java values differ from raw sources |

When a bean depends on both:

```text
Condition  -> decides whether the bean participates
Binder     -> binds fields of the configuration bean
Validation -> checks field constraints
```

The three steps are related, not identical.

## 8. Value Sources: `Environment` and Precedence

When you want to know which value a property holds, the direct way is:

```java
environment.getProperty("app.notify.enabled")
```

`Environment` accesses the context's `PropertySource`s. In typical Spring Boot 3.3 setups, common sources from highest to lowest precedence (abbreviated) are:

```text
Spring Boot command-line properties
              |
              v
Java system properties of the application JVM
              |
              v
OS environment variables
              |
              v
Config Data (application.properties/YAML, imports...)
              |
              v
Default properties
```

Spring Boot also has test property sources, devtools, `SPRING_APPLICATION_JSON`, servlet/JNDI parameters, and custom sources. **This diagram is not an exhaustive order** for every deployment.

### 8.1. Example of the Same Property Appearing Three Times

`application.properties`:

```properties
app.notify.enabled=false
```

Java launcher:

```bash
java -Dapp.notify.enabled=false -jar app.jar \
  --app.notify.enabled=true
```

With default command-line properties enabled, the value Spring Environment sees can be:

```text
true
```

even though both the file and Java system property are `false`.

The condition report might state:

```text
@ConditionalOnProperty (app.notify.enabled=true) matched
```

Yet **that report does not tell you CLI was the winning source**. To know that, inspect `Environment`/`/actuator/env`.

### 8.2. `System.getProperty` Differs from `Environment#getProperty`

In the example above:

```java
System.getProperty("app.notify.enabled")
```

returns:

```text
false
```

whereas:

```java
environment.getProperty("app.notify.enabled")
```

can return:

```text
true
```

The two results do not contradict each other. The Java API checks only JVM system properties, whereas Spring Environment evaluates all sources by precedence.

Likewise, `System.getenv("APP_NOTIFY_ENABLED")` reads only OS environment variables and cannot replace `Environment#getProperty`.

### 8.3. Canonical Names and Relaxed Binding

With `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(boolean enabled) {}
```

a normal environment variable:

```text
APP_NOTIFY_ENABLED=true
```

can be picked up by Binder for `app.notify.enabled`.

For a name like:

```text
app.notify.retry-count
```

the canonical environment variable naming rule is:

```text
APP_NOTIFY_RETRYCOUNT
```

replacing dots with `_`, stripping dashes, and uppercasing.

Distinguish `Environment#getProperty("some.key")` from `@ConfigurationProperties` Binder, because key-name flexibility does not align identically across all APIs and name variants.

## 9. What Does `/actuator/conditions` Reveal?

When an app includes Spring Boot Actuator and the endpoint is properly exposed, you can call:

```bash
curl http://localhost:8080/actuator/conditions
```

The endpoint has structures:

```text
contexts
  |
  +-- application
        |
        +-- positiveMatches
        +-- negativeMatches
        +-- unconditionalClasses
```

Example of a matched condition:

```json
{
  "condition": "OnPropertyCondition",
  "message": "@ConditionalOnProperty (app.notify.enabled=true) matched"
}
```

Strings in the report are **descriptions of evaluation reasons**. Do not parse them as an immutable protocol to extract live values. Message formats can change across versions or condition implementations.

### When to Use It?

- A starter should have auto-configured yet did not run.
- A bean Boot was expected to create did not appear.
- Auto-configuration did not activate due to a missing class/bean/property.
- Need to see why `@ConditionalOnMissingBean` backed off.
- An `enabled` property appears not to affect a bean.

### When Is It Insufficient?

- Need to know the effective value of `app.notify.timeout`.
- Need to prove whether a property came from CLI or profile YAML.
- Need to see how many seconds `@ConfigurationProperties` bound for timeout.
- Need to verify an external endpoint actually receives requests.
- Need to know whether a runtime refresh updated an object.

For those questions, switch to `Environment`, `/actuator/env`, `/actuator/configprops`, live bean inspection, and operational tests.

## 10. `/actuator/env` Is Evidence of Configuration Sources

Spring Boot Actuator provides:

```http
GET /actuator/env
```

It describes `ConfigurableEnvironment`, active/default profiles, `PropertySource`s, and values/origins when provided by the endpoint and permitted by access controls.

A narrower request:

```http
GET /actuator/env/app.notify.enabled
```

can return info for **one specific property**, instead of dumping many properties.

Shortened illustrative response:

```json
{
  "activeProfiles": ["qa"],
  "property": {
    "source": "commandLineArgs",
    "value": "true"
  },
  "propertySources": [
    {
      "name": "commandLineArgs",
      "property": {
        "value": "true"
      }
    },
    {
      "name": "systemProperties",
      "property": {
        "value": "false"
      }
    }
  ]
}
```

The example above illustrates possible structure only, **not verbatim JSON from a specific instance**. Spring Boot 3.3 applies sanitization, so `value` is often shown as `******` instead of `true`/`false`.

### 10.1. `property.source` and `origin`

`/actuator/env/{property.name}` can show:

- The source supplying the selected value.
- Which sources contain/do not contain the property.
- Origin if the `PropertySource` carries origin metadata.

An illustrative origin:

```text
class path resource [application.yaml] - 5:18
```

It helps trace **the file location** of a key loaded via Config Data.

However, not every PropertySource has line/column details. CLI, system properties, environment variables, and custom sources may have different descriptions or no detailed origin. Never claim the endpoint always points to a filename and line number for every source.

### 10.2. `property.value` May Be Masked

Under Spring Boot 3.3, endpoints like `/env` and `/configprops` **sanitize by default** to limit disclosing config data.

If the JSON shows:

```json
{
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  }
}
```

then `******` **is not necessarily the application's real value**. It may simply be masked at the management endpoint layer.

Do not change application configuration to `******` just from misreading that response.

### 10.3. Winning Source Is Not Every Transformation Hop

Suppose a property is declared:

```properties
app.notify.timeout=${APP_TIMEOUT:5s}
```

`Environment` can resolve the placeholder and return a `Duration` or String depending on the API called. Origin may point to the file declaring the placeholder, while the referenced variable's value comes from an environment variable.

When placeholders, imports, config trees, or custom PropertySources are involved, separate:

1. Where the key is declared.
2. Sources of variables referenced in the value.
3. Value after resolution/conversion.
4. Java object received after Binder.

A single source name does not describe this entire dependency chain.

## 11. What Does `/actuator/configprops` Prove?

Endpoint:

```http
GET /actuator/configprops
```

describes beans marked with `@ConfigurationProperties`. It can display:

- Configuration prefix.
- Bean and corresponding class.
- Bound properties.
- Binding inputs and origins when available.
- Values sanitized per management policy.

Illustrative shortened response:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "app.notify-example.NotifyProperties": {
          "prefix": "app.notify",
          "properties": {
            "enabled": true,
            "timeout": "PT5S"
          },
          "inputs": {
            "enabled": {
              "value": "true",
              "origin": "command line"
            }
          }
        }
      }
    }
  }
}
```

Bean names, `Duration` display format, and exact structure can vary by Boot version and application. Do not treat the example above as an exact JSON contract.

### 11.1. Why Does `configprops` Differ from `env`?

`/actuator/env` looks at **sources and property resolution**.

`/actuator/configprops` looks at **configuration objects bound by Spring Boot**.

If the bean has:

```java
@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout
) {}
```

and Environment has:

```properties
app.notify.timeout=5s
```

then the bean can receive:

```java
Duration.ofSeconds(5)
```

The `env` layer shows strings/sources; the `configprops` layer shows typed data post-binding.

### 11.2. `configprops` Does Not Cover Every Place Reading Configuration

Code using:

```java
@Value("${app.notify.timeout}")
private String timeout;
```

or:

```java
System.getenv("APP_NOTIFY_TIMEOUT")
```

does not automatically create a `@ConfigurationProperties` bean appearing in `configprops`.

You cannot conclude "the property is unused" just because it is absent from `/actuator/configprops`.

### 11.3. Java Defaults May Not Appear in `Environment`

Example:

```java
@ConfigurationProperties(prefix = "app.notify")
public class NotifyProperties {

    private Duration timeout = Duration.ofSeconds(5);

    // getters/setters...
}
```

If no `app.notify.timeout` key exists in any PropertySource, the bean can still carry a default `5s` timeout from Java.

Then:

```java
environment.getProperty("app.notify.timeout")
```

can be `null`, while:

```java
notifyProperties.getTimeout()
```

equals five seconds.

This is not a bug. It is the difference between **values present in Environment** and **effective values of an initialized configuration object**.

## 12. End-to-End Example: The `app.notify.enabled` Property

Build a small application with:

```text
app.notify.enabled
app.notify.timeout
app.notify.endpoint
```

We want to:

- Create `NotificationSender` only when `app.notify.enabled=true`.
- Bind Java-typed configuration via `@ConfigurationProperties`.
- Print the value seen from `Environment`.
- Observe whether the bean actually exists.
- Compare three layers of evidence against the condition report.

### 12.1. `application.properties`

`src/main/resources/application.properties`:

```properties
spring.application.name=condition-evidence-demo

app.notify.enabled=false
app.notify.timeout=5s
app.notify.endpoint=https://notify.example.test/api
```

This is the starter file. The `.example.test` domain is illustrative only, not a real API to call.

### 12.2. `@ConfigurationProperties` Model

`src/main/java/example/evidence/NotifyProperties.java`:

```java
package example.evidence;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout,
        URI endpoint
) {
}
```

Spring Boot Binder supports standard conversions for `Duration` and `URI`.

### 12.3. Conditional Business Bean

`src/main/java/example/evidence/NotificationSender.java`:

```java
package example.evidence;

public class NotificationSender {

    public String status() {
        return "sender-created";
    }
}
```

Configuration class:

`src/main/java/example/evidence/NotificationConfiguration.java`:

```java
package example.evidence;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notify",
            name = "enabled",
            havingValue = "true"
    )
    NotificationSender notificationSender() {
        return new NotificationSender();
    }
}
```

`NotificationSender` here is a plain Java class; `status()` makes no network calls.

**If the condition does not match**, Spring Boot skips declaring the bean via that `notificationSender()` method. However, a `NotificationSender` bean could still exist from another independent configuration; therefore, to conclude on actual beans, inspect the context.

### 12.4. Application Printing Evidence

`src/main/java/example/evidence/EvidenceApplication.java`:

```java
package example.evidence;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(NotifyProperties.class)
public class EvidenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(EvidenceApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(
            Environment environment,
            NotifyProperties properties,
            ApplicationContext context
    ) {
        return args -> {
            System.out.println(
                    "env enabled="
                    + environment.getProperty("app.notify.enabled"));

            System.out.println(
                    "bound enabled=" + properties.enabled());

            System.out.println(
                    "bound timeout=" + properties.timeout());

            System.out.println(
                    "sender exists="
                    + !context.getBeansOfType(
                            NotificationSender.class).isEmpty());
        };
    }
}
```

Here:

- `Environment` reports the property value when the runner runs.
- `NotifyProperties` shows the bound typed object.
- `ApplicationContext` verifies whether the bean exists.
- `Condition Evaluation Report` explains how `notificationSender()`'s condition was evaluated.

These four pieces of data are related yet distinct.

## 13. Run Scenario A: File Sets `enabled=false`

Keep configuration:

```properties
app.notify.enabled=false
app.notify.timeout=5s
```

Run:

```bash
./mvnw spring-boot:run
```

Assuming no higher-precedence source exists:

```text
env enabled=false
bound enabled=false
bound timeout=PT5S
sender exists=false
```

Here:

- `enabled=false` is the effective Environment value.
- `NotifyProperties.enabled()` binds as `false`.
- The `havingValue="true"` condition does not match.
- The conditional bean method does not create `NotificationSender`.

If `--debug` is enabled, the condition report shows `OnPropertyCondition` on that method did not match.

**A condition not matching does not mean the application failed.** It can be the intended state of a disabled feature.

## 14. Run Scenario B: CLI Overrides to `enabled=true`

Keep `application.properties` as:

```properties
app.notify.enabled=false
```

Yet run:

```bash
java -jar app.jar --app.notify.enabled=true --debug
```

Replace `app.jar` with your project's executable JAR.

With Spring Boot adding command-line properties by default:

```text
env enabled=true
bound enabled=true
sender exists=true
```

The condition report can record `OnPropertyCondition` matched.

**The accurate conclusion is:** the effective property at condition evaluation time satisfied `havingValue=true` and the bean was created per the demo config.

**You cannot conclude from conditions alone that `application.properties` was edited to true.** The file may still hold false; CLI is simply a higher-precedence source.

### 14.1. The Trap of Reading Only the File

An engineer opens:

```properties
app.notify.enabled=false
```

and concludes:

> NotificationSender cannot exist because the file disabled it.

That conclusion is wrong if the container receives:

```text
APP_NOTIFY_ENABLED=true
```

or the Java command passes:

```text
--app.notify.enabled=true
```

Inspect **the exact running process** and **post-precedence values**, not just source files in the repository.

### 14.2. The Trap of Reading Only Conditions

Another engineer sees:

```text
OnPropertyCondition matched
```

and concludes:

> The deployer turned on `enabled=true` in the main YAML.

That also lacks evidence. Conditions do not pinpoint the winning source. You need `Environment`, origins, and `PropertySource`s.

## 15. Run Scenario C: Java System Property and CLI Conflict

Command:

```bash
java -Dapp.notify.enabled=false \
  -jar app.jar \
  --app.notify.enabled=true
```

Inside the application:

```java
System.getProperty("app.notify.enabled")
```

returns `false`, while:

```java
environment.getProperty("app.notify.enabled")
```

can return `true`.

Because command-line properties outrank Java system properties in standard Boot setups, `havingValue=true` can match.

Table:

| Evidence | Expected value |
| --- | --- |
| Config file | `false` |
| Java system property | `false` |
| Spring Environment | `true` |
| Bean `NotifyProperties.enabled()` | `true` |
| Condition for `NotificationSender` | Match |
| `NotificationSender` | Bean exists in demo |

This is why **`System.getProperty` must not be treated as representative of all Spring configuration**.

## 16. Run Scenario D: Property Missing Yet Condition Matches

Change the annotation in an isolated experiment:

```java
@Bean
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
NotificationSender notificationSender() {
    return new NotificationSender();
}
```

Remove `app.notify.enabled` from all configuration sources.

With no other sources present:

```java
environment.getProperty("app.notify.enabled")
```

returns `null`.

`NotifyProperties.enabled()` is primitive `boolean`, which can bind to default `false` when the property is absent.

Yet the condition **can still match** because `matchIfMissing=true`. Then:

```text
Environment key present?        No
Bound boolean enabled?          false
Condition matched?              Yes
NotificationSender created?     Yes, per bean method in demo
```

This is a textbook example proving:

> A matched condition is not proof the property is actually declared or that the configuration bean holds `true`.

If feature activation must match the model's value, align defaults and `matchIfMissing` explicitly. Never let the condition default to true while the Java model defaults to false if business logic cannot tolerate the mismatch.

## 17. Run Scenario E: Condition Matches Because a Class Exists

A configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.SomeClient")
public class SomeClientConfiguration {
    // ...
}
```

If the class is found, the report logs a positive match for `OnClassCondition`.

However, this has no direct connection to:

```properties
app.some-client.connect-timeout=3s
```

From `OnClassCondition matched`, you cannot deduce:

- `connect-timeout` was declared.
- Its value is `3s`.
- The value came from YAML.
- Connecting to the external service succeeded.
- The client bean has the right timeout configured.
- The system meets latency targets.

Each question demands its own evidence: `env`, `configprops`, bean inspection, metrics, or integration tests.

## 18. Run Scenario F: `@ConditionalOnMissingBean` "Matched"

A message:

```text
@ConditionalOnMissingBean (...) did not find any beans
```

can be a **positive match**. It means the "no matching bean exists" condition succeeded, so auto-configuration can create its default bean.

Readers easily misread "did not find any beans" as meaning the whole auto-configuration failed to run. Check **what the condition requires**:

```text
OnMissingBean condition:
  no bean -> matched
  bean    -> not matched
```

Conversely:

```text
@ConditionalOnBean did not find ...
```

can be a negative match.

Both messages mention "bean," yet carry opposite signs.

### Comparison

| Condition | Target bean present | Possible outcome |
| --- | --- | --- |
| `@ConditionalOnBean` | Yes | Match |
| `@ConditionalOnBean` | No | No match |
| `@ConditionalOnMissingBean` | Yes | No match |
| `@ConditionalOnMissingBean` | No | Match |

To know which beans actually exist after startup, inspect the context or `/actuator/beans`, rather than guessing from an isolated message line.

## 19. Enabling Actuator to Observe Three Evidence Layers

To try endpoints over HTTP, add dependencies:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

In projects using Spring Boot 3.3.x dependency management, versions for both starters are typically managed by Boot.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

**Having the Actuator starter does not mean diagnostic endpoints open automatically over HTTP.** Spring Boot 3.3 exposes mainly `health` over HTTP by default; other endpoints require explicit exposure, availability, and security setup.

### 19.1. Enable Only in Isolated Development Environments

Example `application-local.properties`:

```properties
management.endpoints.web.exposure.include=health,conditions,env,configprops,beans
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Run locally with profile `local`:

```bash
java -jar app.jar --spring.profiles.active=local
```

Then access, provided endpoints are exposed and the user is authorized:

```bash
curl http://localhost:8080/actuator/conditions
curl http://localhost:8080/actuator/env/app.notify.enabled
curl http://localhost:8080/actuator/configprops
curl http://localhost:8080/actuator/beans
```

Never set `management.endpoints.web.exposure.include=*` in a public environment just for quick debugging. Restrict network reachability, define security access controls, and check management port configuration if using a separate port.

### 19.2. Endpoint Enabled Yet Returning 404 or 401/403

Distinguish:

- **404:** endpoint may be unavailable, unexposed, on a different base path/port, or missing a required dependency.
- **401/403:** endpoint may be protected by security, missing authentication/permissions.
- **200 with masked values:** sanitization is active, not missing config data.
- **Connection refused:** server not up, different management port, or blocked by firewall.

Never "fix" by opening all endpoints unconditionally in production. Check layer by layer: dependency → enablement → exposure → routing → authentication/authorization.

## 20. Sanitization: Why `******` Is Not the Real Value

Environment data can include:

```properties
spring.datasource.password=...
app.payment.api-token=...
```

`/env` and `/configprops` could disclose this info if configured too broadly.

In Spring Boot 3.3, values on sensitive endpoints are sanitized by default. Value-display properties look like:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Documented options:

| Value | Meaning |
| --- | --- |
| `never` | Always mask values |
| `when-authorized` | Allow authorized users to see values unless custom sanitization applies |
| `always` | Show values to anyone reaching the endpoint unless other sanitization applies |

**Never recommend enabling `always` in production.** `when-authorized` also needs proper authentication/roles and data-risk evaluation.

Authorization example:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=ENDPOINT_ADMIN
```

Setting only these two lines **does not establish a complete Spring Security policy**. Ensure the endpoint is secured, users hold the role, and `SecurityFilterChain` does not inadvertently allow public access.

A custom `SanitizingFunction` can still mask data even when `show-values` is not `never`.

### What to Do When Needing to Prove a Non-Sensitive Value

In local/test environments, assert a chosen key:

```java
String mode = environment.getProperty("app.notify.enabled");
assertThat(mode).isEqualTo("true");
```

instead of opening unsanitized endpoints for all secrets.

Never paste unsanitized `/actuator/env` responses into public tickets, insecure group chats, or widely shared CI artifacts.

## 21. Cross-Checking Three Endpoints in One Scenario

Suppose:

`application.properties`:

```properties
app.notify.enabled=false
app.notify.timeout=5s
```

Runtime passes:

```bash
java -jar app.jar \
  --app.notify.enabled=true \
  --app.notify.timeout=250ms
```

Once startup succeeds, you can collect:

### A — conditions

```text
OnPropertyCondition for NotificationConfiguration#notificationSender:
  matched
```

This explains why the bean method could be applied.

### B — env

```text
app.notify.enabled = true
app.notify.timeout = 250ms
```

With source such as `commandLineArgs` if command line is the winning source.

This proves effective values and can include source/origin, depending on endpoint and sanitization.

### C — configprops

```text
NotifyProperties.enabled = true
NotifyProperties.timeout = PT0.25S
```

This proves the Java model bound the expected values in this case.

### D — beans

```text
notificationSender bean exists
```

This confirms the real bean is in the context.

### E — behavioral test

A `status()` method returning output, or an integration test verifying data dispatch at the right layer. That proves functionality, not merely configuration.

**Never substitute A for B+C+D+E.** Each piece proves a distinct link in the processing chain.

## 22. When Are Conditions Evaluated?

Conditions are typically evaluated while Spring processes configuration classes and bean definitions during startup.

Therefore if:

1. A condition matched at startup because `app.notify.enabled=true`.
2. The application created the bean.
3. Later a component updates Environment to `app.notify.enabled=false`.

Spring **does not by default** destroy the bean or recompute every condition.

Similarly, an already-bound `@ConfigurationProperties` bean does not auto-refresh when Environment changes, unless an explicit update/rebinding mechanism is configured via a library or application logic.

Timeline scenario:

```text
T0: Env enabled=true
T1: OnPropertyCondition matched
T2: NotificationSender bean created
T3: Env mutated to enabled=false
T4: Condition report still reflects outcome at T1
T5: Bean may still exist
```

`/actuator/env` at T4 can show a different value from the condition recorded at T1. **That is not necessarily a bug in the report**; the two tools reflect different states/points in time.

When using Spring Cloud refresh, config reload, `EnvironmentChangeEvent`, dynamic property sources, or custom bean refresh, explicitly check what gets updated and what does not. Never assume core Spring Boot reconfigures the whole application in real time.

## 23. Another Mismatch Example: Defaults in Code

Class:

```java
@ConfigurationProperties(prefix = "app.notify")
public class NotifyProperties {

    private boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

No `app.notify.enabled` exists in Environment.

The bean can receive:

```text
NotifyProperties.enabled = true
```

via the field initializer.

However:

```java
environment.getProperty("app.notify.enabled")
```

can still be `null`.

If a bean method uses:

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true")
```

with `matchIfMissing=false`, the condition does not match.

Outcome:

```text
Bound bean default enabled=true
Environment key absent
Conditional bean not created
```

Three different yet consistent facts.

**Design rule:** if a feature is enabled by default, decide clearly where the default lives and how conditions set `matchIfMissing`. Never leave the model and bean activation with unknowingly conflicting defaults.

## 24. Multiple Sources Writing the Same Key: Precedence Evidence Needed

Suppose you have:

`application.yaml`:

```yaml
app:
  notify:
    enabled: false
    timeout: 5s
```

`application-prod.yaml`:

```yaml
app:
  notify:
    enabled: true
    timeout: 3s
```

Production environment variable:

```text
APP_NOTIFY_ENABLED=false
```

Launch command:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.notify.timeout=1s
```

In an otherwise clean environment:

| Key | Base file | Prod profile | Environment var | CLI | Expected Spring value |
| --- | --- | --- | --- | --- | --- |
| `app.notify.enabled` | false | true | false | None | false |
| `app.notify.timeout` | 5s | 3s | None | 1s | 1s |

Condition:

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true")
```

will not match because the effective key is `false`.

A "did not match" report tells you the `enabled=true` requirement was unmet; it **does not tell you** whether `APP_NOTIFY_ENABLED=false` or a profile file caused it. The effective source must be investigated separately.

### Risk of Inferring from Profiles

Someone reads `application-prod.yaml` and sees `enabled=true`, yet production keeps the feature disabled. The reason may be an environment variable outranking the profile file.

Precedence cannot be deduced from profile names alone. Every source capable of supplying the same key must be evaluated in the current context.

## 25. Diagnosing When `@ConditionalOnProperty` Does Not Match

A practical workflow:

1. **Read the annotation**: which full name do prefix and name form?
2. **Check `havingValue`**: does it require exact true, false, or another value?
3. **Check `matchIfMissing`**: is matching allowed when the key is missing?
4. **Inspect conditions**: did the condition actually match or fail, at the class or bean method level?
5. **Inspect env**: does the key exist in Environment of the exact context/process?
6. **Inspect source**: did the property come from CLI, system property, env, file, or import?
7. **Inspect profiles**: were profile-specific files loaded?
8. **Check environment variable naming**: does it follow relaxed binding rules?
9. **Inspect configprops**: if a model exists, what data did the bean bind?
10. **Inspect beans**: does the final bean exist or did a user bean override defaults?
11. **Retest with an isolated startup test** using fixed values.
12. **Classify other failures**: a missing class/bean might be the real root cause, not the property.

Never edit annotations arbitrarily just to force a positive match before understanding the bean's business requirements.

## 26. Be Careful with Property Names in Conditions

Example:

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "max-retry-count",
        havingValue = "5")
```

Canonical name uses kebab-case. Matching environment variable form:

```text
APP_NOTIFY_MAXRETRYCOUNT=5
```

Avoid mistaking:

```text
APP_NOTIFY_MAX_RETRY_COUNT
```

as preserving dashes as segment separators. Env naming rules typically strip `-` when deriving env names from canonical properties.

When a property-based condition fails to match, do not immediately conclude the value is wrong; **the input key name might not resolve** the way the deployer assumed.

If you need to verify how Binder binds a specific property, use `@ConfigurationProperties` and test with real names, since `@ConditionalOnProperty` does not guarantee all of Binder's relaxed binding behaviors for every complex key.

## 27. Diagnosing Placeholders

File:

```properties
app.notify.enabled=${NOTIFY_ENABLED:false}
```

When OS has:

```text
NOTIFY_ENABLED=true
```

the resolved value can become `"true"` when read from Spring Environment.

A condition report can state match. However, this property involves:

- Key declared in `application.properties`.
- Placeholder referencing `NOTIFY_ENABLED`.
- OS environment supplying the placeholder's value.
- Post-resolution outcome of `true`.

If you only look at "source: application.properties," you can miss that an environment variable influenced it indirectly. Check **both the root key and any placeholders it references**.

If a placeholder has no default and cannot resolve in a context requiring a value, it can fail during binding/bean creation. Do not generalize that missing placeholders always become `null` across all APIs.

## 28. Config Data Sources Commonly Overlooked

When env results differ from the file you are reading, check:

```text
application.properties / application.yaml
application-{profile}.properties / YAML
spring.config.import
spring.config.location
spring.config.additional-location
Spring profile activation and location groups
Config tree
Files outside the JAR
Command-line properties
Java system properties
OS environment variables
SPRING_APPLICATION_JSON
Test property sources
Sources added by EnvironmentPostProcessor
```

File example:

```properties
spring.config.import=optional:file:./external/notify.properties
```

can allow an imported document to override a key declared in the base file under Config Data rules.

Reading only `src/main/resources/application.properties` misses sources imported at runtime. `/actuator/env/{name}` and origins (when present) can reveal the winning source.

**The condition report does not replace investigating Config Data locations/imports.**

## 29. Distinguish Conditions Reports from Configuration Metadata

Similar-sounding names cause confusion:

| Component | Purpose |
| --- | --- |
| `META-INF/spring-configuration-metadata.json` | Describes config properties so IDEs autocomplete names/types/defaults |
| Condition Evaluation Report | Reasons why auto-configuration/conditional configuration matched or did not |
| `Environment` / `/actuator/env` | Effective configuration sources and values |
| `/actuator/configprops` | Objects bound by `@ConfigurationProperties` |
| `/actuator/beans` | List of beans in the context |

Compile-time metadata generated by `spring-boot-configuration-processor` **is not** a condition report, and neither represents all runtime values.

An IDE suggesting `app.notify.enabled` does not prove that property has a value in production. Likewise, a positive condition does not prove metadata descriptions are accurate.

## 30. Writing Small Tests with `ApplicationContextRunner`

For a bean method's condition, `ApplicationContextRunner` can verify presence/absence of the bean and read `Environment` values.

Test scope includes:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Example:

```java
package example.evidence;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

class NotificationConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(OnlyConditionalConfig.class);

    @Configuration(proxyBeanMethods = false)
    static class OnlyConditionalConfig {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.notify",
                name = "enabled",
                havingValue = "true")
        NotificationSender notificationSender() {
            return new NotificationSender();
        }
    }

    @Test
    void trueCreatesBeanAndEnvironmentContainsTrue() {
        runner.withPropertyValues("app.notify.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);

                    assertThat(context.getEnvironment()
                            .getProperty("app.notify.enabled"))
                            .isEqualTo("true");
                });
    }

    @Test
    void falseDoesNotCreateConditionalBean() {
        runner.withPropertyValues("app.notify.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(NotificationSender.class);

                    assertThat(context.getEnvironment()
                            .getProperty("app.notify.enabled"))
                            .isEqualTo("false");
                });
    }

    @Test
    void missingPropertyDoesNotMatchByDefault() {
        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationSender.class);
            assertThat(context.getEnvironment()
                    .getProperty("app.notify.enabled"))
                    .isNull();
        });
    }
}
```

Strengths:

- Each test declares explicit inputs.
- Verifies **both bean outcome and Environment**.
- No web server needed.
- No external file or database dependencies.

Limitation: `withPropertyValues(...)` supplies test values directly. It **does not prove** Config Data found a real YAML file, processed `spring.config.import`, or followed CLI/file precedence during real application startup.

## 31. Real Startup Test to Prove the Winning Source

When needing to prove externalized configuration loaded and conditions applied accordingly, use `SpringApplication.run(...)` with a temporary file.

### 31.1. Test Model

```java
package example.evidence;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout
) {}
```

For this standalone test, this is a two-field record version. If pasting into the demo project above, keep **one consistent definition** of `NotifyProperties`; do not create two classes with the same name/package.

### 31.2. Minimal Application

```java
@SpringBootConfiguration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotifyProperties.class)
static class MinimalApplication {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notify",
            name = "enabled",
            havingValue = "true")
    NotificationSender notificationSender() {
        return new NotificationSender();
    }
}
```

Annotations:

```java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
```

### 31.3. Complete Test with External File and CLI

```java
package example.evidence;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class StartupConfigurationEvidenceTest {

    @TempDir
    Path tempDir;

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotifyProperties.class)
    static class MinimalApplication {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.notify",
                name = "enabled",
                havingValue = "true"
        )
        NotificationSender notificationSender() {
            return new NotificationSender();
        }
    }

    private static ConfigurableApplicationContext start(
            String... args
    ) {
        SpringApplication app =
                new SpringApplication(MinimalApplication.class);

        app.setBannerMode(Banner.Mode.OFF);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setLogStartupInfo(false);

        return app.run(args);
    }

    @Test
    void cliOverridesFileAndConditionalBeanIsCreated()
            throws IOException {

        Path file = tempDir.resolve("application.properties");

        Files.writeString(
                file,
                "app.notify.enabled=false\n"
                + "app.notify.timeout=5s\n"
                + "app.notify.file-marker=external\n",
                StandardCharsets.UTF_8
        );

        try (ConfigurableApplicationContext context = start(
                "--spring.config.location=" + file.toUri(),
                "--app.notify.enabled=true",
                "--app.notify.timeout=2s"
        )) {
            assertThat(context.getEnvironment()
                    .getProperty("app.notify.enabled"))
                    .isEqualTo("true");

            assertThat(context.getEnvironment()
                    .getProperty("app.notify.file-marker"))
                    .isEqualTo("external");

            NotifyProperties props =
                    context.getBean(NotifyProperties.class);

            assertThat(props.enabled()).isTrue();
            assertThat(props.timeout())
                    .isEqualTo(Duration.ofSeconds(2));

            assertThat(context.getBeansOfType(
                    NotificationSender.class))
                    .hasSize(1);
        }
    }

    @Test
    void fileFalseDisablesTheConditionalBean()
            throws IOException {

        Path file = tempDir.resolve("another.properties");

        Files.writeString(
                file,
                "app.notify.enabled=false\n"
                + "app.notify.timeout=5s\n",
                StandardCharsets.UTF_8
        );

        try (ConfigurableApplicationContext context = start(
                "--spring.config.location=" + file.toUri()
        )) {
            assertThat(context.getEnvironment()
                    .getProperty("app.notify.enabled"))
                    .isEqualTo("false");

            assertThat(context.getBean(NotifyProperties.class)
                    .enabled()).isFalse();

            assertThat(context.getBeansOfType(
                    NotificationSender.class))
                    .isEmpty();
        }
    }
}
```

External data is created via `@TempDir`, so the test needs no real repository files or external services. `spring.config.location` is supplied **right at startup**, exactly when Boot needs it.

### 31.4. Why Use an Independent Marker?

In the first test:

```properties
app.notify.file-marker=external
```

does not exist in CLI. Asserting the marker proves the file **was loaded**, while asserting `enabled=true` proves CLI **beat the conflicting key**.

If you only assert `enabled=true`, the test could still pass even if the external file never loaded, because CLI itself supplies true. The marker separates two critical pieces of evidence:

```text
Did the file participate? -> file-marker
Which source won?         -> enabled
```

### 31.5. Scope Limits of the Test

It verifies:

- Config Data startup via `SpringApplication`.
- External file loaded.
- CLI override.
- Binding to `Duration`.
- Conditional bean presence or absence.

It does not prove:

- A production secret loads securely.
- External endpoints are reachable.
- Every profile, location group, and imported document is right.
- A runtime refresh after startup re-evaluates conditions.
- Behavior inside a specific Kubernetes cluster.

Conclude only within what assertions actually verify.

## 32. Inspecting the Report via API in Tests

When needing to inspect the internal report, Spring Boot offers:

```java
org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport
```

The report can be retrieved via the bean factory of a matching context:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());
```

This is an API in Spring Boot's auto-configuration package. It lets you read recorded condition outcomes, such as sources/conditions in:

```java
report.getConditionAndOutcomesBySource()
```

When using it, remember:

- Data reflects conditions recorded by the framework in that context.
- Source names are usually configuration class or method names.
- Each source can have multiple outcomes.
- Use for internal diagnostics/tests; never parse `message` as a stable schema.
- Check bean context and `Environment` separately.
- A runner/test context might not trigger every auto-configuration of the production app.

There is rarely a need to log the entire `ConditionEvaluationReport` structure. For common incidents, `/actuator/conditions` or the startup debug report is easier to read.

## 33. Decision Table: "Which Tool Should I Use First?"

| Symptom | Priority first step | Next step |
| --- | --- | --- |
| Boot fails to create DataSource despite URL | `conditions` for `DataSourceAutoConfiguration` | `env` for `spring.datasource.*`, `beans` |
| Feature `enabled=true` yet bean missing | `conditions` on matching class/method | `env` enabled key, classpath/beans |
| Runtime timeout differs from YAML | `env` for timeout key | `configprops` or check bind code |
| `@ConfigurationProperties` binds wrong Duration | `configprops` and binding logs | `env` and winning property source |
| IDE suggests property yet app skips it | `env` and bean registration | consuming code; metadata alone is insufficient |
| Auto-configuration negative due to missing bean | `conditions` to check `OnBeanCondition` | `beans` to confirm bean |
| Report positive yet feature fails | `beans`, integration test | check dependencies/runtime/network |
| Value from CLI yet `System.getProperty` null | `Environment` | `ApplicationArguments`/sources |
| Endpoint returns `******` | Check sanitization | Authorized local test; never set show-values globally |
| Profile `prod` yet config uses `dev` values | `env` + `activeProfiles` | config data imports/locations/CLI/env |
| Feature stays enabled after runtime property change | Compare condition time and present | refresh/rebinding mechanism if any |

No single tool solves every issue. Pick evidence closest to **the symptom and operating layer**.

## 34. Common Diagnostic Mistakes

### Mistake 1 — "Positive match means YAML contains true"

Wrong. A positive match can come from `matchIfMissing`, another property source, classpath, or bean condition. Identify the condition type and property source.

### Mistake 2 — "Negative match means the file was not read"

Wrong. Auto-configuration can fail due to a missing class/bean even when the file has every key.

### Mistake 3 — "`Environment#getProperty` being right means the bean has the same value"

Not guaranteed. The bean may use defaults, conversion, validation, custom binding from another source, or have been bound before Environment changed.

### Mistake 4 — "`configprops` lists every Spring configuration"

No. It describes `@ConfigurationProperties` beans, excluding standalone `@Value`, `System.getenv`, or manually read properties.

### Mistake 5 — "`/actuator/env` always shows full values"

No. Spring Boot 3.3 sanitizes data by default, and access permissions may restrict it.

### Mistake 6 — "Setting `management.endpoints.web.exposure.include=*` is enough"

That can be a severe risk. Exposure is only part of endpoint availability; there are also access controls, network isolation, sensitive values, and security chains.

### Mistake 7 — "Editing `application.properties` in source updates the running process"

Not by default. Apps usually load configuration at startup. Understand real restart/refresh mechanics, especially with packaged JAR artifacts or built images.

### Mistake 8 — "Conditions re-evaluate when Env changes"

Not by default. A startup report is not a live per-request condition monitor.

### Mistake 9 — "CLI has no effect because YAML already defines the key"

Wrong. Command-line properties normally take higher precedence than config data in default Boot setups.

### Mistake 10 — "`@ConditionalOnProperty` requires true by default"

Wrong. Without `havingValue`, any present property other than `"false"` can match.

### Mistake 11 — "`matchIfMissing=true` proves a default exists in Env"

Wrong. The condition can match precisely because the key does not exist.

### Mistake 12 — "An `OnMissingBean` message containing 'missing' is negative"

Wrong. Finding no beans can be the **matching result** of `@ConditionalOnMissingBean`.

### Mistake 13 — "`/actuator/conditions` lists every bean"

No. The `conditions` endpoint focuses on condition evaluation. Use `/actuator/beans` when you need a list of registered beans.

### Mistake 14 — "Origin always has filename and line number"

No. That depends on PropertySource type and origin-tracking support; not every source has line/column info.

### Mistake 15 — "IDE metadata is the condition report"

No. Metadata is generated at compile time to provide name/type autocomplete. The condition report reflects startup conditions.

## 35. Ask Five Questions When Reading a Report Line

Suppose the report reads:

```text
NotificationConfiguration#notificationSender matched:
  - @ConditionalOnProperty (app.notify.enabled=true) matched
```

Before concluding, ask:

1. **Which condition?** `OnPropertyCondition`, or `OnClassCondition`, `OnBeanCondition`?
2. **Which property?** Full canonical key, and exact `havingValue`/`matchIfMissing`?
3. **Which point in time?** Startup or a recreated context?
4. **How far does the value reach?** `Environment`, `@ConfigurationProperties` Binder, or direct Java API reads?
5. **Final bean and behavior?** Does the bean exist; is it actually being used?

These five questions prevent wrong fixes like:

- Adding a property to YAML when the real cause is a missing dependency.
- Opening all of Actuator when only one local key needs inspection.
- Changing `@ConditionalOnProperty` when a higher-precedence CLI property overrides it.
- Removing validation just because the condition matched.
- Editing timeout in a file overridden by an environment variable.

## 36. Self-Check Exercises

### Exercise 1 — Positive Match Does Not Name the Source

`application.yaml` sets `app.notify.enabled=false`; CLI passes `--app.notify.enabled=true`. Conditions state `OnPropertyCondition` with `havingValue=true` matched.

**Question:** is YAML guaranteed to contain true?

**Answer:** No. CLI can override it to true. Use `Environment` or `/actuator/env/app.notify.enabled` to identify the winning source.

### Exercise 2 — Default Condition

```java
@ConditionalOnProperty(name = "app.mode")
```

`app.mode=experimental`.

**Question:** can it match?

**Answer:** Yes. By default, a present property not equal to `"false"` can match.

### Exercise 3 — matchIfMissing

```java
@ConditionalOnProperty(
    name = "app.notify.enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

No `app.notify.enabled` property exists.

**Question:** can the condition match?

**Answer:** Yes. That is the explicit contract of `matchIfMissing=true`.

### Exercise 4 — JavaBean Default

A bean has `enabled=true` from a field initializer, yet `Environment#getProperty("app.notify.enabled")` is null.

**Question:** is there a contradiction?

**Answer:** No. A default inside a Java object does not mean the property exists in Environment.

### Exercise 5 — System vs. Spring

Command:

```bash
java -Dapp.notify.enabled=false -jar app.jar \
  --app.notify.enabled=true
```

**Question:** how can `System.getProperty` and `Environment#getProperty` differ?

**Answer:** Java system property is false, whereas Spring Environment can select true from CLI.

### Exercise 6 — Missing Class

Config has `app.cache.enabled=true`, yet auto-configuration's `OnClassCondition` fails.

**Question:** can you conclude `app.cache.enabled` does not exist?

**Answer:** No. Classpath condition fails independently of the key; check dependencies and Environment separately.

### Exercise 7 — OnMissingBean

Report states `@ConditionalOnMissingBean did not find any beans`.

**Question:** can this be a positive match?

**Answer:** Yes. The condition requires **no bean present**, so finding no beans can be a match outcome.

### Exercise 8 — Actuator Endpoints

**Question:** which endpoint shows condition outcomes, which shows property sources, and which shows bound beans?

**Answer:** `/actuator/conditions`, `/actuator/env`, and `/actuator/configprops` respectively.

### Exercise 9 — Sanitization

`/actuator/env/app.secret.token` returns `"******"`.

**Question:** is the app definitely using six literal asterisks?

**Answer:** No. The value may have been masked by sanitization. Do not open unrestricted exposure just to verify secrets.

### Exercise 10 — Source Name and Origin

The endpoint shows only source `systemEnvironment` without a line number.

**Question:** is the endpoint broken?

**Answer:** No. Many sources lack file/line metadata like YAML configs.

### Exercise 11 — Test Proving CLI Override

A test calls `SpringApplication.run("--app.notify.enabled=true")` and asserts true.

**Question:** has the test proved an external file was loaded?

**Answer:** Not yet. A marker property existing only in the external file is needed to prove presence.

### Exercise 12 — Condition Report After Refresh

Report logs a condition matched at startup. Later a component changes Environment to false.

**Question:** will the bean automatically be deleted?

**Answer:** Not by default. Conditions are not automatically re-evaluated when a property changes.

### Exercise 13 — Bound Model vs. Runtime Cause

`NotifyProperties.timeout=PT5S`, yet requests take 20 seconds.

**Question:** can you conclude Binder is wrong?

**Answer:** Not yet. The timeout in the model might not be wired to the client properly, or another component has its own timeout. Inspect wiring and runtime measurements.

### Exercise 14 — `@ConditionalOnProperty` on Collections

Config has only `app.notify.channels[0]=email`, condition checks `app.notify.channels`.

**Question:** is it reliable for deciding whether the list has elements?

**Answer:** No. Javadoc warns this condition is unsuitable for checking collections that way. Design an appropriate condition or validate the bound model.

### Exercise 15 — Security

A team wants to enable:

```properties
management.endpoint.env.show-values=always
management.endpoints.web.exposure.include=*
```

on a public host.

**Question:** is it safe?

**Answer:** Do not do this. Restrict exposure, enforce authentication/authorization, and keep sanitization policies to avoid exposing secrets, system details, and sensitive endpoints.

## 37. Configuration Incident Checklist

- [ ] Investigating a condition, a property value, or bean state?
- [ ] Identified the exact running process, profile, and context?
- [ ] Read the **specific** condition on the relevant class/bean method?
- [ ] Distinguished `positiveMatches` from `negativeMatches` and each condition's reason?
- [ ] Read `havingValue` and `matchIfMissing` rather than guessing from property names?
- [ ] Checked sources outranking `application.yaml`?
- [ ] Checked `spring.config.import` and file locations outside the JAR?
- [ ] Retrieved effective values from `Environment#getProperty` or authorized env endpoint?
- [ ] Inspected key origin when supported by the source?
- [ ] Distinguished sanitized values from literal values?
- [ ] Checked `@ConfigurationProperties` is registered and bound to the right type?
- [ ] Checked real beans via context or beans endpoint?
- [ ] Checked binding/validation errors separately from conditions?
- [ ] Distinguished startup timing from later dynamic config changes?
- [ ] Avoided printing secrets or dumping full Environment to logs?
- [ ] Created at least one isolated test reproducing precedence/bean outcome?
- [ ] Verified business behavior with integration tests when needed?
- [ ] Avoided tweaking APIs/configs to force a condition match without knowing the cause?
- [ ] Referenced Spring Boot docs matching the actual application version?
- [ ] Tightened Actuator endpoints and restricted production access?

## 38. Summary

A sound chain of evidence for configuration issues:

```text
Business requirement:
"NotificationSender runs only when enabled"
                |
                v
Condition Evaluation Report
"Were the bean's conditions met?"
                |
                v
Environment / Actuator env
"What is the effective property value, and which source won?"
                |
                v
@ConfigurationProperties / configprops
"How was the value converted and bound?"
                |
                v
ApplicationContext / beans
"Does the actual bean exist?"
                |
                v
Integration test / runtime observation
"Does the feature actually work properly?"
```

Core principles:

1. **Condition reports report on conditions**, not an inventory of all effective configuration.
2. **`@ConditionalOnProperty` has `havingValue` and `matchIfMissing` rules**; matching does not guarantee the key exists or equals boolean true.
3. **`Environment#getProperty` and `/actuator/env`** inspect effective values and `PropertySource`s, factoring in sanitization and origin availability.
4. **`/actuator/configprops`** inspects bound `@ConfigurationProperties` beans, not every place the application reads configuration.
5. **Inspect final beans separately from condition outcomes**, because auto-configuration can back off due to user beans, classpath, method-level conditions, or lifecycle.
6. **Startup evidence does not prove runtime state after Environment changes**; verify timing and refresh mechanisms.
7. **Protect sensitive configuration data** when using diagnostic endpoints; never open all of Actuator to the Internet just to chase one bug.
8. **A good test asserts source markers, effective properties, bound models, and bean outcomes**, each supporting a different conclusion.

When needing to determine "why isn't the feature enabled?", use `conditions` to understand condition decisions, `env` to determine real properties, `configprops` to see bound data, and `beans`/tests to verify behavior. That is layer-accurate diagnosis, avoiding mistaking an auto-configuration report for proof of the property values actually used by the application.

## References

- Spring Boot 3.3 Reference — Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 Reference — Externalized Configuration / PropertySource Order: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Actuator Endpoints, exposure, security, sanitization: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 Actuator REST — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 Actuator REST — Environment: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html
- Spring Boot 3.3 Actuator REST — Configuration Properties: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html
- Spring Boot 3.3 Java API — `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 Java API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
