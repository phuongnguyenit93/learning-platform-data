# Meaning of null in JSON When Overriding Values

In Spring Boot, one way to pass multiple properties into an application via environment variables is using **`SPRING_APPLICATION_JSON`**. This variable contains a JSON string; Spring Boot reads the JSON and adds the values to the **externalized configuration** system. This approach is helpful when a deployment needs to supply a structured group of settings without creating many individual environment variables.

However, there is a surprising rule: **a JSON `null` value cannot be used as a command to "delete" or "mask" a matching key coming from a lower-priority configuration source**. Spring Boot may place an entry with a null value into the property source built from JSON, yet during property resolution `PropertySourcesPropertyResolver` treats `null` as **no value found** and continues checking other sources. Therefore, if `application.yml` already defines a value, setting that key to `null` in `SPRING_APPLICATION_JSON` does not make the value disappear.

This lesson focuses on what `null` means when overriding configuration with JSON, how to distinguish it from the string `"null"` and an empty string, how to observe effective values in an application, and the right options when you genuinely want to remove or disable a setting.

## 1. What is SPRING_APPLICATION_JSON?

Suppose an application has `application.yml`:

~~~yaml
app:
  display-name: "Order Service"
  feature:
    enabled: true
  request:
    timeout: 5s
~~~

A deployment can supply an environment variable:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"feature":{"enabled":false},"request":{"timeout":"2s"}}}'
java -jar order-service.jar
~~~

In the POSIX shell example above, the value of `SPRING_APPLICATION_JSON` is **one complete JSON string**. Spring Boot reads the JSON content and introduces flattened keys into the property system, such as:

~~~text
app.feature.enabled = false
app.request.timeout = 2s
~~~

Provided no higher-priority source overrides them, configuration supplied from JSON can win over matching values in `application.yml`. The application receives flag `false` and duration `2s` instead of `true` and `5s`.

Key points to understand:

- `SPRING_APPLICATION_JSON` is **the name of an environment variable**, while the variable's content is **JSON text**.
- Spring Boot also supports supplying the same kind of data via Java system property `spring.application.json` or corresponding command-line arguments in appropriate launch setups.
- JSON can express nested objects; Spring Boot creates dotted property names, such as `app.feature.enabled`.
- JSON is processed while preparing the configuration environment at startup; it is not a place to store per-request business data.
- JSON must be syntactically valid, and the final value must also fit the target Java type during binding.

Do not confuse `SPRING_APPLICATION_JSON` with an arbitrary JSON file sitting on disk. This mechanism specifically relates to the property named `spring.application.json` or its corresponding environment variable.

## 2. Core rule: JSON null does not mean "delete configuration"

Consider `application.yml`:

~~~yaml
app:
  mode: "normal"
  retry-count: 3
~~~

The deployment wants to remove the `app.mode` value by writing JSON:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":null}}'
java -jar order-service.jar
~~~

Many people predict:

~~~text
app.mode = null
~~~

However, when the application queries the value via Spring `Environment`, the typical result is:

~~~text
app.mode = normal
~~~

Because `app.mode` from JSON has a null value, the property resolver treats it as absent, continues searching the next configuration source, and finds `app.mode=normal` from `application.yml`.

You can visualize it as:

~~~text
Lookup: app.mode
        |
        v
SPRING_APPLICATION_JSON
  app.mode -> null
        |
        | null is treated as having no usable value
        v
application.yml
  app.mode -> "normal"
        |
        v
Effective value: "normal"
~~~

**This is a property resolution mechanism, not a JSON Merge Patch operation.** In some patch specifications, `null` means deleting a field. Spring Boot's `SPRING_APPLICATION_JSON` has no such "tombstone" (deletion marker) semantics.

If lower-priority sources also lack that key, the result may be property not found. If another source has a value, Spring can use that value. Typing `null` into JSON does not guarantee a Java field receives null.

## 3. Why doesn't a higher-priority source with null win?

When resolving a configuration key, Spring Boot relies on a prioritized list of `PropertySource` instances. The general idea is finding the first source with a usable value for that key, from highest priority down to lowest.

Example:

| Source | Value of `app.mode` |
| --- | --- |
| JSON from `SPRING_APPLICATION_JSON` | `null` |
| `application-prod.yml` | `"safe"` |
| `application.yml` | `"normal"` |

Suppose profile `prod` is active and no higher source provides `app.mode`. Because JSON holds null, it does not block the lookup; the next source holds `"safe"`, so the effective value is `"safe"`.

If the JSON changes to:

~~~json
{
  "app": {
    "mode": "maintenance"
  }
}
~~~

then `"maintenance"` is a non-null value and can override `"safe"` according to normal precedence.

Important takeaways:

- **Precedence determines which source is checked first.**
- **Null means "no value" to the property resolver.**
- **A null entry in a higher-priority source does not stop searching for a value in lower-priority sources.**

Overall precedence can also include command-line arguments, Java system properties, OS environment variables, Config Data, and more. For example, if the command line supplies `--app.mode=forced`, that value can take precedence over JSON. When diagnosing issues, examine the actual list of sources for the active run.

## 4. Comparing null, "null", empty string, false, and 0

The following values **differ** right at the JSON level:

~~~json
{
  "app": {
    "nullable": null,
    "literalNull": "null",
    "emptyText": "",
    "feature": {
      "enabled": false
    },
    "retryCount": 0
  }
}
~~~

| Representation in JSON | JSON value type | Effect during property resolution |
| --- | --- | --- |
| `null` | JSON null | Cannot mask values in lower-priority sources |
| `"null"` | Four-character string | Real string value; can override text |
| `""` | Empty string | Non-null value; can override strings |
| `false` | Boolean false | Present value; can override a true flag |
| `0` | Number zero | Present value; can override non-zero numbers |
| Key omitted | Property absent from JSON source | Spring continues searching other sources |

Suppose `application.yml` contains:

~~~yaml
demo:
  nullable: "fallback"
  literal-null: "fallback"
  empty-text: "fallback"
  feature:
    enabled: true
  retry-count: 5
~~~

When the deployment supplies the corresponding JSON, the intended results will be:

~~~text
demo.nullable        -> "fallback"  # JSON null cannot mask it
demo.literal-null    -> "null"      # literal string
demo.empty-text      -> ""          # empty string
demo.feature.enabled -> false       # boolean false
demo.retry-count     -> 0           # number 0
~~~

The final outcome in a Java bean still depends on the **conversion/binding** step. For instance, an empty string can be preserved when the field is `String`, but do not use an empty string pretending to "clear" an `int`, `Duration`, or `URI`: converters or validation may fail or apply target-type-specific handling.

**Do not replace JSON `null` with `"null"` just to force an override** if the field is actually a boolean, number, URL, or duration. A string `"null"` may trigger a binding failure, and it does not mean "no value".

## 5. Quotes in JSON and data types

In JSON, data types are explicitly expressed by syntax:

~~~json
{
  "name": "api-service",
  "attempts": 3,
  "enabled": true,
  "missing": null
}
~~~

- `"api-service"` is a string.
- `3` is a number.
- `true` is a boolean.
- `null` is a null value.
- `"true"`, `"3"`, `"null"` are strings, not their corresponding literals.

Do not assume the `SPRING_APPLICATION_JSON` environment variable value itself is an OS-level JSON object: at the OS layer, an environment variable value is still **plain text**. Spring Boot parses that string as JSON at startup.

In shells, beyond JSON rules, **shell quoting rules** also apply. For example, on Linux/macOS with a POSIX shell:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":null,"enabled":false}}'
java -jar app.jar
~~~

In PowerShell:

~~~powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"mode":null,"enabled":false}}'
java -jar .\app.jar
~~~

In these examples, the outer single quotes simply help the shell preserve a single JSON string. The inner double quotes are **JSON syntax** for key names. The unquoted `null` inside is the true JSON null.

If you write:

~~~json
{"app":{"mode":"null"}}
~~~

then Spring Boot receives the text `"null"`, not null.

## 6. Example observable through Spring Environment

Base configuration:

~~~yaml
# application.yml
app:
  mode: "normal"
  feature:
    enabled: true
  retry-count: 3
~~~

A minimal application to print **non-sensitive values**:

~~~java
package example.configdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ConfigDemoApplication implements CommandLineRunner {

    private final Environment environment;

    public ConfigDemoApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
            "app.mode=" + environment.getProperty("app.mode"));
        System.out.println(
            "app.feature.enabled=" +
                environment.getProperty("app.feature.enabled"));
        System.out.println(
            "app.retry-count=" +
                environment.getProperty("app.retry-count"));
    }
}
~~~

This is an example for observing properties, not a recommendation to print all application configuration to stdout; strictly avoid printing secrets, tokens, and sensitive data.

Run with JSON null:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":null}}'
java -jar app.jar
~~~

Expected output (if no higher-priority source):

~~~text
app.mode=normal
app.feature.enabled=true
app.retry-count=3
~~~

Run with JSON containing concrete values:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":"maintenance","feature":{"enabled":false},"retry-count":0}}'
java -jar app.jar
~~~

Expected output:

~~~text
app.mode=maintenance
app.feature.enabled=false
app.retry-count=0
~~~

Takeaway: `null` does not erase `normal`, whereas `"maintenance"`, `false`, and `0` are valid values to override, depending on key and Java type.

In real projects, keys should follow a consistent convention (e.g., kebab-case), and tests can read effective values directly from `Environment` without logging in production.

## 7. Implications for @Value and @ConfigurationProperties

Spring Boot has multiple ways to inject configuration into Java. Two familiar approaches:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class ModePrinter {

    private final String mode;

    ModePrinter(@Value("${app.mode:normal}") String mode) {
        this.mode = mode;
    }
}
~~~

And grouped binding:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppSettings(String mode) {}
~~~

If the JSON source returns null for `app.mode` while `application.yml` has `app.mode=normal`, property resolution still finds `normal` in the lower source. Therefore:

- With `@Value`, the placeholder may receive `normal` instead of treating JSON null as a deletion command.
- With `@ConfigurationProperties`, the Binder also operates on effective configuration sources and does not automatically turn JSON null into "clear existing value".
- If no source supplies a usable value, the outcome depends on field type, defaults, constructor, and validation; you cannot generally assume every field receives `null` or that startup will succeed.

Note on `@Value("${app.mode:normal}")`: the `:normal` part is the **placeholder's fallback value** when no matching property is found. It is completely distinct from JSON `null` and is not a deletion directive.

A primitive field such as `boolean` cannot hold Java null; conversely, `Boolean` can represent null, though binding and validation must be explicitly designed. Do not use JSON null as a shortcut to switch field types.

## 8. Null on a parent object does not delete child properties

Another misconception is thinking JSON null on an entire object removes all nested keys beneath it.

Suppose base configuration:

~~~yaml
app:
  remote:
    url: "https://api.example.invalid"
    timeout: 3s
    enabled: true
~~~

The deployment supplies:

~~~json
{
  "app": {
    "remote": null
  }
}
~~~

Do not expect the effective configuration to become `app.remote=null` hiding `app.remote.url`, `app.remote.timeout`, and `app.remote.enabled`. Spring's property system operates on keys after sources are read/flattened; a null value is not a marker deleting an entire property tree. Those child keys from `application.yml` can still be resolved and bound.

Similarly:

~~~json
{
  "app": {
    "remote": {
      "url": null
    }
  }
}
~~~

does not erase the URL already present in a lower-priority source. To change the URL, provide a specific, valid URL; to disable remote integration, use a flag with clear semantics or restructure configuration.

Principle: **do not apply intuition from JSON Merge Patch or JavaScript object merging to Spring property sources**. They are different models.

## 9. What should you do if you want to remove or disable a value?

Before choosing an approach, distinguish **removing a value** from **disabling a feature**.

### 9.1. Wanting a feature disabled

Use a meaningful boolean property:

~~~yaml
# application.yml
notifications:
  enabled: true
  destination: "https://notify.example.invalid"
~~~

In a deployment where you want it off:

~~~json
{
  "notifications": {
    "enabled": false
  }
}
~~~

The `false` flag is a real value and can override `true`. The application must use this flag to decide whether to create integration beans or execute the feature:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "notifications",
        name = "enabled",
        havingValue = "true"
    )
    NotificationClient notificationClient(
            NotificationProperties properties) {
        return new NotificationClient(properties.destination());
    }
}
~~~

`NotificationClient` and `NotificationProperties` are illustrative module types. When `enabled=false`, the conditional bean is not registered; any dependent beans must be designed to handle a disabled integration.

The key point is that `enabled=false` expresses behavior far more clearly than `destination=null`.

### 9.2. Wanting to replace a defined value

Supply a valid replacement value:

~~~json
{
  "notifications": {
    "destination": "https://notify-staging.example.invalid"
  }
}
~~~

When a non-null value is present, source precedence rules select the new value. If you want to swap the URL for a mock server address, use a concrete mock URL instead of null.

### 9.3. Wanting the default property genuinely absent

If the goal is for an environment **not to have** the property, the cleanest approach is **not declaring that property in lower-priority configuration sources that are always loaded**. You can:

- Move production-only properties into configuration activated specifically for production.
- Remove obsolete defaults from base configuration.
- Only include an integration configuration in imported/deployment sources when that feature needs to run.
- Design conditional beans and validation so that property absence is a supported state.

For example, instead of keeping a production endpoint in the base file:

~~~yaml
# application.yml — base configuration
notifications:
  enabled: false
~~~

Only production supplies:

~~~yaml
# application-prod.yml
notifications:
  enabled: true
~~~

And sensitive or deployment-varying endpoints are supplied via external configuration sources. Then environments not needing the integration will not inherit a production endpoint from the base file.

### 9.4. Wanting to represent an "unselected" state

You can use an explicit sentinel value, such as `provider: "none"`, if **the application defines and checks** that state:

~~~yaml
storage:
  provider: "none"
~~~

In Java, an enum like `NONE`, `S3`, `AZURE` makes the state clearer. This is application configuration domain design; Spring Boot does not automatically treat every `"none"` string as a disable command.

### 9.5. Wanting an empty string

For a property that is genuinely a string where an empty value makes sense, you can write:

~~~json
{
  "app": {
    "display-name": ""
  }
}
~~~

An empty string is not null; when the target is `String`, it can override the display name. However, **do not use empty strings to clear arbitrary property types**: fields validated with `@NotBlank` will reject it; numeric, boolean, duration, or URI types have their own conversion rules. Design and test according to the actual target type.

## 10. Security case: null can leave old values in use

Suppose base configuration or a lower-priority source accidentally contains:

~~~yaml
external:
  api:
    endpoint: "https://legacy.example.invalid"
~~~

In a new deployment, an operator thinks writing:

~~~json
{
  "external": {
    "api": {
      "endpoint": null
    }
  }
}
~~~

will prevent the application from using the old endpoint. Instead, Spring can continue reading `endpoint` from the lower configuration, resulting in **still connecting to the legacy endpoint**.

This is why `null` should never be used as a security or operational "reset". If an old endpoint is no longer valid, remove it from the base source, supply a new endpoint, or explicitly disable the integration. The same applies to secrets: JSON null is not a method for clearing inherited credentials; secrets must be managed at the infrastructure layer and never stored in committed base configuration files.

Recommended safeguards:

- Do not place sensitive default credentials in `application.yml`.
- Validate required properties before serving traffic.
- Use a disable flag or dedicated profile when an integration must not run.
- Verify effective values after deployment changes, without leaking tokens/passwords in logs.

## 11. Diagnostics: knowing which source a property comes from

When JSON null "has no effect", first verify:

1. **Is the property name correct?** `app.remote.url` differs from `app.remote-url` in organization, and nested JSON must match the queried key.
2. **Is the environment variable named correctly and containing valid JSON?** `SPRING_APPLICATION_JSON` must reach the exact Java process being configured.
3. **Does the JSON use a literal null or string `"null"`?** The two behave differently.
4. **Does a lower-priority source still supply a value?** Check `application.yml`, profile files, config imports, and other defaults.
5. **Is a higher-priority source overriding it?** For instance, command-line arguments can beat JSON.
6. **What type does Java expect?** Separate property resolution issues from conversion/validation failures.
7. **Was the application restarted to read the new configuration?** Environment variables of a running process do not update automatically just from editing a manifest or external shell.

Spring Boot Actuator `/actuator/env` or `/actuator/configprops` can be used in controlled environments if properly enabled, configured, and secured. They help trace properties and configuration sources, yet **must never be exposed publicly or used to print sensitive data**.

In tests or internal debugging tools, querying a non-sensitive key via `Environment` is a simple way to distinguish "JSON null treated as absent" from "value overridden by another source".

## 12. Three common points of confusion

### 12.1. "I passed null, yet @Value still gets the default value"

Example:

~~~yaml
# application.yml
mail:
  sender-name: "Default Sender"
~~~

JSON:

~~~json
{"mail":{"sender-name":null}}
~~~

When resolving the property, Spring can continue taking `Default Sender` from the YAML file. This aligns with `PropertySourcesPropertyResolver`'s handling of null.

If the goal is clearing the sender name, check whether an empty string is valid for business logic. If the goal is disabling email, use `mail.enabled=false` and corresponding application conditions.

### 12.2. "I switched to "null", the property got overridden, and now the app crashes"

JSON:

~~~json
{"mail":{"timeout":"null"}}
~~~

If Java expects a `Duration`, `"null"` is not a valid duration. Overriding with a string does not mean the binding step will accept it. Provide a valid duration like `"3s"` or disable the feature with a dedicated property.

### 12.3. "I set the parent object to null to clear all child settings"

JSON:

~~~json
{"datasourceSettings":null}
~~~

If child keys are supplied by another configuration source, there is no mechanism to delete the whole property tree merely by setting the parent object to null. For settings that must vary by environment, reorganize configuration sources and avoid placing unwanted values in always-loaded sources.

## 13. A set of self-test scenarios

Start with:

~~~yaml
# application.yml
demo:
  mode: "base"
  label: "base-label"
  enabled: true
  retries: 5
~~~

You can use `Environment#getProperty` to read non-sensitive keys. Try each JSON value in a separate startup:

| JSON supplied | Expected value if no higher source |
| --- | --- |
| `{"demo":{"mode":null}}` | `demo.mode=base` |
| `{"demo":{"mode":"null"}}` | `demo.mode=null` as text |
| `{"demo":{"mode":""}}` | `demo.mode` is an empty string |
| `{"demo":{"enabled":false}}` | `demo.enabled=false` |
| `{"demo":{"retries":0}}` | `demo.retries=0` |
| `{"demo":{"label":"override"}}` | `demo.label=override` |
| `{"demo":{}}` | Original keys can still be found from YAML |

Also test **omitting the key from JSON altogether**. You will see that when a lower source holds a value, the lookup result matches setting the key to null: Spring still uses the lower source.

To make it even clearer, remove `demo.mode` from `application.yml` and run with JSON null. When no other source supplies the key, `Environment#getProperty("demo.mode")` may return null meaning **property not found**. That is not a null value capable of masking other sources.

## 14. JSON null in API payloads is not the same as configuration JSON null

In applications, you may also encounter JSON null in HTTP requests/responses:

~~~json
{
  "customerId": "C-001",
  "phoneNumber": null
}
~~~

Depending on API and DTO design, `phoneNumber: null` in a request can carry specific meaning, such as wanting to clear a customer's phone number during an update operation. That meaning is defined by the **API contract**, serializer, validation, and business logic.

However, JSON in `SPRING_APPLICATION_JSON` is used by Spring Boot to create a property source. Here null does not mean "delete property". Do not carry semantics of an HTTP PATCH API or update DTO convention over to externalized configuration.

Both are JSON text, yet **the contracts of the systems processing the JSON differ**:

| Context | Who defines the meaning of null? |
| --- | --- |
| `SPRING_APPLICATION_JSON` | Spring Boot Config Data / property source resolution |
| HTTP JSON request | API contract, serializer, and business logic |
| JSON Merge Patch | Patch specification and server implementation |
| JSON data stored in database | Schema and application data access layer |

Therefore, when asking "does null delete it?", always establish the **context** first.

## 15. Design conventions to prevent mistakes

An easily operated system should follow these conventions:

- **Do not use null as a delete command** in `SPRING_APPLICATION_JSON`. When disabling a feature, express it with a meaningful property like `enabled=false`.
- **Choose default values responsibly.** Production endpoints or credentials should not sit in shared base configuration just so every environment "has something".
- **Distinguish absence from emptiness.** An empty string `""` is a value, suitable only when the application accepts empty strings.
- **Keep types consistent.** Do not replace numbers, booleans, URLs, or durations with `"null"` hoping the Binder treats it as no data.
- **Do not treat a null object as deleting an entire property tree.** Child keys can continue arriving from lower-priority sources.
- **Verify effective configuration in the actual environment.** Source precedence, profiles, and command-line arguments can make runtime values differ from intuition.
- **Design validation around usage conditions.** When a feature is enabled, required properties must exist and be valid; when disabled, avoid initializing unnecessary dependencies.
- **Separate deployment configuration from business data.** JSON in environment variables serves startup configuration, not updating orders or customer profiles.

## 16. Summary in one rule

If `application.yml` has:

~~~yaml
app:
  mode: "normal"
~~~

then:

~~~json
{"app":{"mode":null}}
~~~

**does not delete** `app.mode` and does not guarantee `@ConfigurationProperties` receives null. The property resolver continues searching for a source with a value and can receive `"normal"` from YAML.

Conversely:

~~~json
{"app":{"mode":"maintenance"}}
~~~

provides a real value to override it. If you want a component not to run, use a flag such as `app.feature.enabled=false` and implement matching logic. If you want a property genuinely absent, adjust your configuration source design so active sources do not supply it.

**Remember the formula: JSON `null` is an unusable value for masking lower-priority sources; JSON `"null"` is a string; `false`, `0`, and `""` are non-null values that can override depending on target type.**
