# Resolving Strings Containing Placeholders via Environment in Spring Boot

## 1. Opening scenario: a string that needs values from configuration

Imagine an application needs to construct a startup message:

~~~text
Catalog application is running at https://api.example.com:8443
~~~

However, the application name, host, and port can all vary across a personal machine, a test environment, and production. If those values are hard-coded in Java, every environment change requires editing code or adding custom logic.

Spring provides a **property placeholder** with the form:

~~~text
${property.name}
~~~

When resolving, Spring looks up the value of `property.name` in `Environment` and replaces the entire `${property.name}` segment with the found value. As a result, a template string can use configuration values that Spring Boot has gathered from files, environment variables, Java system properties, command-line arguments, and other sources.

Example `application.yaml`:

~~~yaml
spring:
  application:
    name: catalog

app:
  public-host: api.example.com
  public-port: 8443
  startup-message: "Application ${spring.application.name} is running at https://${app.public-host}:${app.public-port}"
~~~

If no other configuration source overrides them, the resolved `app.startup-message` string has the value:

~~~text
Application catalog is running at https://api.example.com:8443
~~~

In this lesson, you will learn:

- What a `${...}` placeholder is, where its value comes from, and how it differs from a regular string.
- How to use `Environment.resolvePlaceholders(...)` and `Environment.resolveRequiredPlaceholders(...)`.
- When `Environment.getProperty(...)` also resolves placeholders inside values retrieved from configuration.
- How to declare defaults `${key:default}`, nest placeholders, and replace multiple placeholders in one string.
- How configuration source precedence, profiles, environment variables, and launch arguments affect the substituted value.
- Error cases when keys are missing, circular references occur, key names are wrong, or placeholders contain secrets.

## 2. Three components to distinguish: key, value, and template string

Consider `application.properties`:

~~~properties
app.name=Catalog
app.host=localhost
app.port=8080
app.url=http://${app.host}:${app.port}
~~~

There are three concepts:

1. **Property key**: `app.host`, `app.port`, or `app.url`.
2. **Property value**: `localhost`, `8080`, or a string containing placeholders.
3. **Template string to resolve**: for example `Connect to ${app.url}`, which can live in a file or be constructed directly in Java.

For `app.url`, Spring must substitute two expressions:

~~~text
Before: http://${app.host}:${app.port}
After:  http://localhost:8080
~~~

For another template string:

~~~text
Before: Using service at ${app.url}
After:  Using service at http://localhost:8080
~~~

In the second example, the value of `app.url` itself contains placeholders, so resolution can continue until the final content is obtained. What matters is that the **final value** comes from the properties currently effective in `Environment`.

A placeholder is not a new key created inside `Environment`. It is a **reference syntax** pointing to an existing key, or to a default value if you declare one.

## 3. Where does Environment sit?

`org.springframework.core.env.Environment` provides the interface for reading application properties and inspecting profiles.

Methods directly relevant to this lesson:

~~~java
String getProperty(String key);

String getProperty(String key, String defaultValue);

<T> T getProperty(String key, Class<T> targetType);

String resolvePlaceholders(String text);

String resolveRequiredPlaceholders(String text);
~~~

Specifically:

- `getProperty("app.host")`: gets the effective value of a **key**.
- `getProperty("app.host", "localhost")`: supplies a fallback value if the key has no value.
- `resolvePlaceholders("Address: ${app.host}")`: resolves placeholders inside an **arbitrary string**.
- `resolveRequiredPlaceholders("Address: ${app.host}")`: resolves the string and requires necessary placeholders to have a value or valid default.

Spring Boot aggregates multiple sources into ordered `PropertySource`s inside `Environment`. When a placeholder references `app.host`, the resolver searches via the same property lookup mechanism of the environment.

Conceptual diagram:

~~~text
application.yaml ----------┐
application-prod.yaml -----┤
environment variables -----┤
Java System properties ----┼--> PropertySources --> Environment
--key=value arguments -----┘                           |
                                                     app.host = ?
                                                         |
"Open ${app.host}:${app.port}" -- resolvePlaceholders ---+
                                                         |
                                                         v
                                            "Open api.example.com:8443"
~~~

**There is no special placeholder rule that bypasses source precedence.** If the same key appears in multiple sources, the value `Environment` returns for that key is the value used for substitution.

## 4. resolvePlaceholders: resolving arbitrary strings, allowing missing keys

This is the common method when you have a template string supplied by application code or internal users:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class TemplateService {

    private final Environment environment;

    public TemplateService(Environment environment) {
        this.environment = environment;
    }

    public String renderGreeting() {
        return environment.resolvePlaceholders(
                "Hello from ${spring.application.name}!");
    }
}
~~~

File `application.yaml`:

~~~yaml
spring:
  application:
    name: catalog-service
~~~

Result:

~~~text
Hello from catalog-service!
~~~

### 4.1. Multiple placeholders in one string

~~~java
String message = environment.resolvePlaceholders(
        "Application ${spring.application.name} is running on ${app.host}:${app.port}");
~~~

Configuration file:

~~~properties
spring.application.name=order-service
app.host=localhost
app.port=9090
~~~

Result:

~~~text
Application order-service is running on localhost:9090
~~~

You do not need to call `getProperty(...)` three times and concatenate parts manually. The resolver replaces each reference in the given string.

### 4.2. What if the key has no value?

Suppose `app.region` is absent from configuration sources:

~~~java
String result = environment.resolvePlaceholders(
        "Running in region ${app.region}");
~~~

The result can remain:

~~~text
Running in region ${app.region}
~~~

By contract, `resolvePlaceholders(...)` **does not require every unfound placeholder to fail**; it leaves unresolved placeholders intact. That is why this method is also called **non-strict** (or permissive) resolution.

Do not treat a literal placeholder left behind as a valid value. If you pass this string into a URL or business message, `${app.region}` can appear directly in the output data.

### 4.3. If there are no placeholders in the string

~~~java
String value = environment.resolvePlaceholders(
        "Nothing to replace");
~~~

The result keeps the string unchanged. The resolver only processes segments matching placeholder syntax.

### 4.4. When should it be used?

`resolvePlaceholders(...)` fits when:

- You want to render a text template where all placeholders are not strictly required.
- The string might contain unconfigured references, and the application has separate handling rules afterward.
- A template system allows leaving unresolved placeholders to be processed in another phase.

For URLs, required file paths, system endpoints, or parameters needed for startup, silently leaving placeholders intact is usually **inappropriate**. Consider the strict method instead.

## 5. resolveRequiredPlaceholders: requiring placeholders to resolve

The second method serves the same substitution goal, but has a different policy when encountering a missing placeholder:

~~~java
String endpoint = environment.resolveRequiredPlaceholders(
        "https://${app.api.host}:${app.api.port}/orders");
~~~

If `app.api.host` or `app.api.port` does not exist and has no default, the method throws an `IllegalArgumentException` because the required placeholder cannot be resolved.

Example handling with a clear error message:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class ApiEndpointService {

    private final Environment environment;

    public ApiEndpointService(Environment environment) {
        this.environment = environment;
    }

    public String endpoint() {
        try {
            return environment.resolveRequiredPlaceholders(
                    "https://${app.api.host}:${app.api.port}/orders");
        } catch (IllegalArgumentException error) {
            throw new IllegalStateException(
                    "Missing or invalid API address configuration", error);
        }
    }
}
~~~

The strict method is useful when **the application must refuse to run or refuse to execute an operation** if essential parameters are missing.

Distinguish:

| Question | `resolvePlaceholders` | `resolveRequiredPlaceholders` |
| --- | --- | --- |
| Does it replace placeholders that have values? | Yes | Yes |
| Does it handle multiple placeholders in one string? | Yes | Yes |
| Does it use default values inside placeholders? | Yes | Yes |
| Key has no value and no default? | May keep placeholder as-is | Throws an error when unable to resolve |
| Suitable for required parameters? | Only if calling code checks afterward | More suitable |

### A note on error types

`resolveRequiredPlaceholders(...)` guarantees **no required placeholders remain unresolved according to the resolver's rules**, but it does not guarantee the value has a valid business format.

Example:

~~~properties
app.api.port=not-a-port
~~~

The string:

~~~text
https://localhost:not-a-port/orders
~~~

can still be fully resolved at the placeholder level, even though the port is not a valid number. To verify numeric types, URI syntax, or business rules, you still need **type conversion and validation** in a subsequent step, such as via `@ConfigurationProperties`.

## 6. Default values: `${key:default}` syntax

A placeholder can declare a fallback value right inside the expression:

~~~text
${property.name:default-value}
~~~

Example:

~~~java
String greeting = environment.resolveRequiredPlaceholders(
        "Hello, ${app.user:guest}!");
~~~

If `app.user` exists with value `Minh`:

~~~text
Hello, Minh!
~~~

If `app.user` has no value:

~~~text
Hello, guest!
~~~

Because a default is present, `resolveRequiredPlaceholders(...)` does not throw an error merely because `app.user` is missing.

### 6.1. Defaults used for multiple configuration settings

~~~java
String endpoint = environment.resolveRequiredPlaceholders(
        "http://${app.host:localhost}:${app.port:8080}/health");
~~~

With neither property present, the final string is:

~~~text
http://localhost:8080/health
~~~

If only this is present:

~~~properties
app.port=9090
~~~

the result is:

~~~text
http://localhost:9090/health
~~~

Each placeholder is processed **independently**. All keys do not need to appear together in the same file.

### 6.2. Default in a placeholder vs. default in getProperty

These two approaches can produce the same result in simple scenarios, yet they operate on **different inputs**:

~~~java
String a = environment.getProperty("app.region", "local");

String b = environment.resolvePlaceholders(
        "${app.region:local}");
~~~

`getProperty(...)` starts from **a key name to read**. `resolvePlaceholders(...)` starts from **a template string to substitute**. When the template string contains surrounding text or multiple placeholders, the second method is more convenient.

### 6.3. An empty value is not quite the same as a missing value

If configuration has:

~~~properties
app.user=
~~~

then the `app.user` key can still exist with an **empty string value**. In this case, do not assume `${app.user:guest}` will definitely use the word `guest`. Default values apply when the resolver finds no property value, not as a check for every empty or whitespace-only string.

If business logic requires a **non-empty** value, check that condition separately.

## 7. Nested placeholders and multi-level fallbacks

Spring supports expressions containing placeholders inside other placeholders. A common usage is **choosing a fallback key**.

Example:

~~~java
String host = environment.resolveRequiredPlaceholders(
        "${app.host:${fallback.host:localhost}}");
~~~

Cases:

| Present property | Result |
| --- | --- |
| `app.host=prod.example.com` | `prod.example.com` |
| No `app.host`, `fallback.host=backup.example.com` present | `backup.example.com` |
| Neither present | `localhost` |

The rule reads as:

1. Prefer the value of `app.host`.
2. If not found, use the value of `fallback.host`.
3. If neither is present, use the string `localhost`.

This lets you express fallback ordering without writing separate `if/else` logic in Java.

### 7.1. A key whose value contains other placeholders

Configuration file:

~~~properties
app.host=api.example.com
app.port=8443
app.base-url=https://${app.host}:${app.port}
app.orders-url=${app.base-url}/orders
~~~

In the normal case:

~~~java
String orders = environment.getProperty("app.orders-url");
~~~

can yield:

~~~text
https://api.example.com:8443/orders
~~~

When retrieving a string property value through `Environment`'s `PropertySourcesPropertyResolver`, placeholders nested inside **property values** are also resolved according to the appropriate mechanism. You do not necessarily have to call `resolvePlaceholders(...)` a second time for every key in a reference chain.

However, if **Java code** itself constructs an arbitrary template string:

~~~java
String template = "Connect to ${app.orders-url}";
~~~

then calling `environment.resolvePlaceholders(template)` resolves that string.

### 7.2. Nesting placeholders inside the key name

Another pattern is:

~~~text
${app.${app.target}.url}
~~~

If configuration has:

~~~properties
app.target=orders
app.orders.url=https://orders.example.com
~~~

the inner key can resolve to `orders` to form the key name `app.orders.url`, and then retrieve the URL value.

This pattern can suit configuration layouts with clear naming conventions, though it is harder to read than explicit key names. Use it only when dynamic key selection is genuinely needed; for typed configuration groups, `@ConfigurationProperties` is usually easier to maintain.

### 7.3. Avoiding circular references

Example:

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

There is no independent final value to finish resolution. This is a **circular reference**. The resolver can throw an error due to the circular reference or fail to complete substitution.

Do not use circular placeholder chains to describe defaults between two properties. Choose a key with an actual value or a concrete default as the termination point:

~~~properties
app.b=localhost
app.a=${app.b}
~~~

## 8. How Environment chooses values to substitute

A placeholder does not specify a source file by itself. It states a **property name**, and `Environment` is responsible for looking it up across `PropertySource`s.

Example:

~~~yaml
# application.yaml
app:
  region: local
  message: "Serving in ${app.region}"
~~~

When running:

~~~bash
java -jar app.jar --app.region=asia-east
~~~

under Spring Boot's default precedence order, the command-line property `app.region=asia-east` wins over `local` in YAML.

Therefore:

~~~java
String message = environment.getProperty("app.message");
~~~

can return:

~~~text
Serving in asia-east
~~~

The key point is that `app.message` lives in `application.yaml`, yet the placeholder `${app.region}` **is not pinned** to the `app.region` value in the same file. It uses whatever value `Environment` resolves.

### 8.1. Common source precedence order

In a typical Spring Boot run, notable sources include:

- Config Data: `application.properties`/YAML, profile-specific configuration, external configuration outside the JAR, and imports.
- OS environment variables.
- Java System properties, such as `-Dapp.region=...`.
- Command-line options, such as `--app.region=...`.

Sources have a **precedence order**; normally, command-line options override Java System properties, environment variables, and Config Data. Sources specific to testing or Devtools can change the overall ordering.

Example:

~~~bash
APP_REGION=env-value \
java -Dapp.region=jvm-value -jar app.jar \
  --app.region=cli-value
~~~

When all of these sources are picked up by Spring Boot under default configuration, `${app.region}` resolves to `cli-value`.

If `--app.region=cli-value` is removed, `jvm-value` can win. If `-Dapp.region=jvm-value` is also removed, the value from the environment variable can win.

### 8.2. Profiles determine which documents participate

Base file:

~~~yaml
# application.yaml
app:
  host: localhost
  endpoint: "https://${app.host}/api"
~~~

Production file:

~~~yaml
# application-prod.yaml
app:
  host: api.example.com
~~~

If you run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

then `application-prod.yaml` can provide `app.host` and `app.endpoint` resolves to:

~~~text
https://api.example.com/api
~~~

If a higher-precedence source overrides `app.host`, the placeholder takes the value from that source. Profiles do not create a separate key-name scope solely for placeholders.

## 9. Complete example with Environment and ApplicationRunner

Create a Spring Boot application with configuration:

~~~yaml
# src/main/resources/application.yaml
spring:
  application:
    name: billing-service

app:
  public-host: localhost
  public-port: 8080
  protocol: http
  public-url: "${app.protocol}://${app.public-host}:${app.public-port}"
  welcome-template: "Welcome to ${spring.application.name} at ${app.public-url}"
~~~

Startup class:

~~~java
package com.example.placeholderdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PlaceholderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderDemoApplication.class, args);
    }
}
~~~

Add a runner to observe behavior:

~~~java
package com.example.placeholderdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class PlaceholderDemoRunner implements ApplicationRunner {

    private final Environment environment;

    public PlaceholderDemoRunner(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String direct = environment.getProperty("app.public-url");

        String fromTemplate = environment.resolvePlaceholders(
                "Application is serving at ${app.public-url}");

        String required = environment.resolveRequiredPlaceholders(
                "Application name: ${spring.application.name}");

        System.out.println("Direct URL: " + direct);
        System.out.println("Template: " + fromTemplate);
        System.out.println("Required: " + required);
    }
}
~~~

With default configuration, illustrative output:

~~~text
Direct URL: http://localhost:8080
Template: Application is serving at http://localhost:8080
Required: Application name: billing-service
~~~

Run again with CLI overrides:

~~~bash
java -jar app.jar \
  --app.protocol=https \
  --app.public-host=billing.example.com \
  --app.public-port=443
~~~

Result:

~~~text
Direct URL: https://billing.example.com:443
Template: Application is serving at https://billing.example.com:443
Required: Application name: billing-service
~~~

This example connects two features:

1. Spring Boot merges configuration sources into effective values.
2. Spring Framework resolves placeholders by querying those effective values.

**Note:** the example prints non-sensitive sample values for easy observation. In a real application, never print passwords, secret keys, tokens, or sensitive resolved contents.

## 10. How do resolvePlaceholders and getProperty relate?

The two calls below are typically used for different purposes:

~~~java
String one = environment.getProperty("app.public-url");

String two = environment.resolvePlaceholders(
        "${app.public-url}");
~~~

When the property is present and handling is appropriate, both can return the same URL. However, they are **not the same API**:

- `getProperty(...)` takes a **key name**, looks up its value, and can convert types via corresponding overloads.
- `resolvePlaceholders(...)` takes **an arbitrary string** and searches for placeholder expressions inside it.
- `resolveRequiredPlaceholders(...)` also takes an arbitrary string but enforces a stricter policy when values are missing.

Example:

~~~java
environment.getProperty("Hello ${app.public-host}");
~~~

does not mean "find the host and prepend Hello". It is requesting a property whose **exact name is the entire string** `Hello ${app.public-host}`. If no such key exists, the result is typically `null`.

To substitute into a template string, use:

~~~java
environment.resolvePlaceholders(
        "Hello ${app.public-host}");
~~~

### Default values with getProperty

~~~java
String host = environment.getProperty(
        "app.public-host", "localhost");
~~~

This is a way to specify a default **for a key-lookup call**. It fits when you only need one property, and can easily be combined with target-type conversion.

Whereas:

~~~java
String text = environment.resolvePlaceholders(
        "Current host: ${app.public-host:localhost}");
~~~

places the default **inside the template string's expression**.

### Retrieving typed values

~~~java
Integer port = environment.getProperty(
        "app.public-port", Integer.class, 8080);
~~~

Placeholder resolution methods return a **`String`**. If you need `int`, `Duration`, `URI`, or other types, use a typed read method or `@ConfigurationProperties` so Spring performs the corresponding type conversion.

## 11. How does @Value use placeholders?

In Spring-managed beans, a common approach is using `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AppMessage {

    private final String message;

    public AppMessage(
            @Value("${app.welcome-template:Hello there}") String message) {
        this.message = message;
    }

    public String text() {
        return message;
    }
}
~~~

`@Value("${...}")` asks Spring's mechanism to resolve the placeholder when injecting the value into the bean. The value comes from `Environment` and available configuration sources.

If the YAML file contains:

~~~yaml
app:
  welcome-template: "Welcome to ${spring.application.name}"
~~~

then the injected value can be the resolved string, such as `Welcome to billing-service`.

### Differences between @Value and calling Environment directly

| Characteristic | `@Value("${...}")` | `Environment.resolvePlaceholders(...)` |
| --- | --- | --- |
| Typical usage site | Dependency injection points in Spring beans | Any code with an `Environment` reference |
| When executed | While Spring creates/configures the bean | At the moment code calls the method |
| Input form | Expression in an annotation | `String` supplied by code |
| Multiple placeholders | Supported | Supported |
| Missing-key policy | Depends on the context's placeholder processor; may prevent bean creation | Explicit via `resolvePlaceholders` or `resolveRequiredPlaceholders` |

Do not assume `@Value` is identical in every detail to a hand-written `resolvePlaceholders(...)` call. `@Value` passes through bean processing and can interact with other Spring capabilities.

### Distinguishing placeholders from SpEL

Two syntaxes look similar but have different meanings:

~~~java
@Value("${app.port:8080}")
int port;
~~~

and:

~~~java
@Value("#{2 * 3}")
int number;
~~~

- `${...}`: placeholder for a **configuration property**.
- `#{...}`: **Spring Expression Language (SpEL)** expression.

`Environment.resolvePlaceholders(...)` is not a SpEL evaluator. Do not expect:

~~~java
environment.resolvePlaceholders("#{2 * 3}");
~~~

to perform multiplication automatically. If there is no `${...}` syntax to replace, the method largely returns the string as received.

## 12. @ConfigurationProperties and placeholders inside files

For multiple related properties, `@ConfigurationProperties` usually organizes configuration better than scattered `@Value` annotations.

File `application.yaml`:

~~~yaml
app:
  api:
    protocol: https
    host: localhost
    port: 8443
    base-url: "${app.api.protocol}://${app.api.host}:${app.api.port}"
    timeout: 5s
~~~

A configuration record:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.api")
public record ApiProperties(
        String protocol,
        String host,
        int port,
        URI baseUrl,
        Duration timeout) {
}
~~~

Register with `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(ApiProperties.class)` in configuration.

Then:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ApiClientSettings {

    private final ApiProperties properties;

    public ApiClientSettings(ApiProperties properties) {
        this.properties = properties;
    }

    public URI baseUrl() {
        return properties.baseUrl();
    }
}
~~~

Spring Boot's binder reads effective configuration values, resolves necessary references, and converts them to `URI`, `Duration`, or `int` accordingly. `base-url` maps to the Java field `baseUrl` via *relaxed binding* rules.

**Do not confuse scope:** `@ConfigurationProperties` is a mechanism for binding and converting configuration, while `Environment.resolvePlaceholders(...)` is an API for resolving **template strings**. Both mechanisms can work together, but you should not replace all typed configuration binding with long template strings if the application needs validation and clear structure.

## 13. Key names in placeholders and naming conventions

In Spring Boot, placeholders should be written using the **canonical property form**, typically lowercase, dot-separated, with hyphens between words:

~~~text
${app.api.base-url}
${app.retry-count}
${spring.application.name}
~~~

This style works well with Spring Boot's mapping across different configuration sources.

Example with a configuration group:

~~~yaml
app:
  api:
    base-url: "https://example.com"
~~~

The placeholder:

~~~text
${app.api.base-url}
~~~

matches intent more clearly than arbitrary casing variants.

In deployment environments, environment variable names under standard binding rules typically transform from:

~~~text
app.api.base-url
~~~

to:

~~~text
APP_API_BASEURL
~~~

The rule for `@ConfigurationProperties` is to replace dots with underscores, drop hyphens, and uppercase. `Environment` lookup and name normalization details can vary by `PropertySource` type; therefore, when writing `${...}` in Spring Boot configuration, using canonical key names helps mechanisms interoperate predictably.

### Placeholders do not auto-correct misspelled keys

Suppose configuration has:

~~~properties
app.api.host=api.example.com
~~~

but the template string references:

~~~text
${app.ap1.host}
~~~

where the letter `i` was typed as the digit `1`. The resolver does not guess your intent and fetch `app.api.host`. Strict resolution throws a missing-key error; non-strict resolution can leave the placeholder behind.

This helps explain why typos in placeholders are sometimes caught at startup and other times only show up as unsubstituted strings at runtime.

## 14. Placeholders can span multiple PropertySource layers

A template string contains only a key name, yet that key itself may have definitions in multiple sources.

Example source inside JAR:

~~~yaml
# application.yaml
app:
  endpoint:
    host: localhost
    url: "http://${app.endpoint.host}:8080/api"
~~~

File outside JAR:

~~~yaml
# ./config/application-prod.yaml
app:
  endpoint:
    host: internal-api
~~~

Environment variable:

~~~bash
APP_ENDPOINT_HOST=gateway.example.com
~~~

Command-line argument:

~~~bash
--app.endpoint.host=public.example.com
~~~

If profile `prod` is active and all these sources participate, the effective value of `app.endpoint.host` follows Spring Boot's precedence order. In a standard run, the CLI argument can win over the remaining values, causing:

~~~text
app.endpoint.url = http://public.example.com:8080/api
~~~

Learners should separate two questions:

1. **Which key does the placeholder point to?** Here, `app.endpoint.host`.
2. **Where does that key get its value from?** `Environment` decides across the set of `PropertySource`s and precedence order.

There is no step saying "a placeholder in `application.yaml` may only read `application.yaml`". It queries the combined configuration environment.

## 15. Common errors when resolving placeholders

### 15.1. Forgetting braces or writing invalid syntax

Incorrect:

~~~text
¤app.host
${app.host
¤app.host}
~~~

Correct:

~~~text
${app.host}
~~~

A placeholder must have `$`, an opening brace `{`, and a matching closing brace `}`. If the expression does not match the syntax, the resolver may treat it as plain text or fail to complete substitution.

### 15.2. Confusing a template string with a getProperty key name

~~~java
environment.getProperty("Hello ${app.name}");
~~~

This looks up a key named **the entire string**, rather than assembling a greeting. Use:

~~~java
environment.resolvePlaceholders("Hello ${app.name}");
~~~

### 15.3. Using resolvePlaceholders for required values without checking

~~~java
String url = environment.resolvePlaceholders(
        "https://${app.remote.host}/api");
~~~

If the key is missing, the URL can still contain `${app.remote.host}`. For required configuration, use `resolveRequiredPlaceholders(...)` or validation during configuration binding.

### 15.4. Thinking defaults validate every empty value

~~~text
${app.user:guest}
~~~

If the key has an empty string value, it is not necessarily replaced with `guest`. Verifying non-empty strings is the responsibility of application validation.

### 15.5. Creating circular references

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

There is no termination point. Replace with an actual value or a non-circular default branch.

### 15.6. Using the wrong environment variable name

Suppose you want to read `app.retry-count` but name the environment variable against conventions. This can prevent the placeholder from finding the expected value. With Spring Boot's naming conventions, verify the exact corresponding variable name and write the placeholder in canonical form.

### 15.7. Assuming placeholders automatically pick up new values when files change

Spring Boot typically loads Config Data at application startup. Modifying `application.yaml` on disk does not automatically guarantee `Environment` is reloaded or `@Value` beans are reconfigured. Systems needing dynamic refresh require a dedicated mechanism.

### 15.8. Putting secret values into log strings

~~~java
String text = environment.resolvePlaceholders(
        "Token: ${service.auth.token}");
System.out.println(text);
~~~

This example can leak the token if `service.auth.token` exists. Placeholders do not mask sensitive data automatically. When diagnostics are needed, log the key name or present/absent status, and avoid printing secret values.

### 15.9. Thinking placeholders substitute every kind of expression

`${...}` is property reference syntax. It is not shell expansion, does not call external APIs automatically, does not evaluate SpEL expressions `#{...}`, and does not execute arbitrary business calculations.

If you need to assemble URLs, filenames, or messages from configuration, placeholders fit. If you need complex conditional logic, checking values and building typed objects in Java will be clearer.

### 15.10. Overly complex nested placeholders

A multi-level expression such as:

~~~text
${app.host:${fallback.host:${global.host:localhost}}}
~~~

can be valid under nested resolution, yet hard to read if repeated across many places. When configuration strings turn into long decision trees, consider redesigning the configuration keys for maintainability and testability.

## 16. How to diagnose actual values in an application

When a resolved string does not match expectations, check from **key** to **source** to **template string**.

### Step 1: identify referenced keys

Example:

~~~text
https://${app.api.host}:${app.api.port:8443}
~~~

The keys are `app.api.host` and `app.api.port`. Do not mistake `8443` for a key name; it is a **default value**.

### Step 2: check effective values

In a development environment, with non-sensitive data:

~~~java
String host = environment.getProperty("app.api.host");
String port = environment.getProperty("app.api.port");

System.out.println("Host configured: " + (host != null));
System.out.println("Port configured: " + (port != null));
~~~

This checks only presence, without printing values. If exact inspection is needed, use only safe sample data.

### Step 3: resolve with the appropriate API

~~~java
String permissive = environment.resolvePlaceholders(
        "${app.api.host}:${app.api.port:8443}");

String strict = environment.resolveRequiredPlaceholders(
        "${app.api.host}:${app.api.port:8443}");
~~~

Observe the difference when `app.api.host` is intentionally omitted.

### Step 4: check source ordering

If the result differs from the YAML file you are reading, check whether any environment variable, Java System property, CLI argument, or profile is taking effect.

When you need to list sources without printing secret values:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public void listSources(ConfigurableEnvironment environment) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        System.out.println(source.getName());
    }
}
~~~

`ConfigurableEnvironment` provides access to the ordered `PropertySource`s. Source names can indicate the source type or file location, helping identify where a key might be overridden.

### Step 5: check bean creation timing

If a bean receives a value via `@Value` during initialization, reading `Environment` again later does not necessarily mean the bean's field changed. Verify the application's configuration update mechanism before concluding two places must always reflect the same value.

## 17. Step-by-step practice exercises

### Exercise 1: resolving multiple values

Configuration:

~~~properties
app.name=orders
app.host=localhost
app.port=8181
~~~

Code:

~~~java
String text = environment.resolveRequiredPlaceholders(
        "Service ${app.name}: http://${app.host}:${app.port}");
~~~

**Answer:**

~~~text
Service orders: http://localhost:8181
~~~

### Exercise 2: comparing permissive and strict

Suppose `app.zone` is absent:

~~~java
String a = environment.resolvePlaceholders(
        "Zone = ${app.zone}");

String b = environment.resolveRequiredPlaceholders(
        "Zone = ${app.zone}");
~~~

**Answer:** `a` can remain `Zone = ${app.zone}`. `b` throws an error because the required placeholder cannot be resolved.

### Exercise 3: adding a default value

Without `app.zone`:

~~~java
String text = environment.resolveRequiredPlaceholders(
        "Zone = ${app.zone:local}");
~~~

**Answer:**

~~~text
Zone = local
~~~

### Exercise 4: nested references

Configuration:

~~~properties
service.host=api.internal
service.port=8088
service.base-url=http://${service.host}:${service.port}
service.health-url=${service.base-url}/health
~~~

What does `environment.getProperty("service.health-url")` return in the normal case?

**Answer:**

~~~text
http://api.internal:8088/health
~~~

Explanation: the value of `service.health-url` references `service.base-url`, which in turn references `service.host` and `service.port`.

### Exercise 5: higher-precedence source overriding a referenced value

In `application.yaml`:

~~~yaml
app:
  host: localhost
  endpoint: "https://${app.host}/v1"
~~~

Launch:

~~~bash
java -jar app.jar --app.host=public.example.com
~~~

What does `environment.getProperty("app.endpoint")` return?

**Answer:** `https://public.example.com/v1`, assuming no higher-precedence source replaces `app.endpoint`. Reason: the placeholder references the effective value of `app.host` from `Environment`.

### Exercise 6: distinguishing getProperty and resolvePlaceholders

Configuration:

~~~properties
app.name=billing
~~~

Code:

~~~java
String a = environment.getProperty("app.name");
String b = environment.resolvePlaceholders("Hello ${app.name}");
String c = environment.getProperty("Hello ${app.name}");
~~~

**Answer:**

- `a` is `billing`.
- `b` is `Hello billing`.
- `c` is typically `null` because there is no property named `Hello ${app.name}`.

### Exercise 7: using profiles

File `application.yaml`:

~~~yaml
app:
  host: localhost
  url: "https://${app.host}/v1"
~~~

File `application-prod.yaml`:

~~~yaml
app:
  host: api.production.test
~~~

Run with `--spring.profiles.active=prod`. What is `app.url`?

**Answer:** `https://api.production.test/v1`, assuming no higher-precedence source overrides the related keys.

### Exercise 8: multi-level defaults

Template:

~~~text
${app.host:${fallback.host:localhost}}
~~~

Try three configurations: with `app.host`; with only `fallback.host`; with neither. Respectively, the results come from `app.host`, `fallback.host`, and the default string `localhost`.

### Exercise 9: checking SpEL syntax

Code:

~~~java
String x = environment.resolvePlaceholders("#{4 + 5}");
~~~

Is `x` guaranteed to equal `9`?

**Answer:** No. This method resolves property placeholders of the form `${...}`, not SpEL expressions. `#{4 + 5}` is a different syntax.

### Exercise 10: recognizing risks

Template:

~~~text
Connect with password ${db.password}
~~~

Should you print the result of `resolveRequiredPlaceholders(...)` directly to production logs?

**Answer:** No. Even if resolved properly, the string can contain a secret. Only verify existence or log a masked status.

## 18. Which tool to choose for each purpose?

| Need | Suitable API/mechanism | Reason |
| --- | --- | --- |
| Get a key as a string | `Environment.getProperty("app.name")` | Concise and direct. |
| Get a key with fallback | `getProperty("app.name", "demo")` | Default at the read site. |
| Get a typed key | `getProperty("app.port", Integer.class)` | Converts data type. |
| Resolve placeholders in an arbitrary string | `resolvePlaceholders("URL: ${app.url}")` | Substitutes resolvable references. |
| Require all mandatory placeholders to have values | `resolveRequiredPlaceholders("${app.url}")` | Errors when a required reference is missing. |
| Inject a value into a bean on creation | `@Value("${app.url}")` | Integrates with bean creation. |
| Bind an entire configuration group into a record/POJO | `@ConfigurationProperties` | Clear data types and structure. |
| Inspect profiles, sources, and configuration ordering | `Environment` / `ConfigurableEnvironment` | Understand why a key has the observed value. |

## 19. Summary

- `${property.name}` is a **configuration reference**, not an arithmetic calculation and not a Java variable.
- `Environment` looks up a key's value across effective `PropertySource`s according to precedence order.
- `resolvePlaceholders(...)` processes template strings and can keep unresolved placeholders intact.
- `resolveRequiredPlaceholders(...)` requires placeholders to have values or suitable defaults, otherwise throwing an error.
- `${key:default}` enables fallback values; placeholders can be nested.
- When a property is read from `Environment`, its value can contain other placeholders and be resolved further.
- `@Value` and `@ConfigurationProperties` use Spring's configuration infrastructure but serve different goals: injecting single values or binding an entire configuration group.
- Placeholders do not automatically validate business content, refresh running configuration, or protect secrets.

Make it a habit to identify **the referenced key**, **the effective value of that key**, and **the policy when the key is missing**. These three factors explain most situations where `${...}` strings are substituted properly, left as-is, or fail in a Spring Boot application.

## References

- [Spring Framework — Environment and Property Resolution](https://docs.spring.io/spring-framework/reference/core/beans/environment.html).
- [Spring Framework — PropertyResolver](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/PropertyResolver.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).