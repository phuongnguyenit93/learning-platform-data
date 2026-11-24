# Referencing Properties with `${key}` Syntax in Spring Boot

## 1. Purpose and Context

In Spring Boot Externalized Configuration, configuration values can come from `application.properties`, `application.yml`, environment variables, Java system properties, command-line arguments, or external configuration files. When multiple properties share a common component such as hostname, port, deployment region, or root directory, repeating the raw value across many keys increases the risk of inconsistency.

**The `${key}` placeholder allows the value of one property to reference another property.** For example:

~~~properties
app.api.host=localhost
app.api.port=8080
app.api.url=http://${app.api.host}:${app.api.port}/api
~~~

In an environment where no higher-precedence source overrides it, `app.api.url` can be resolved to `http://localhost:8080/api`.

The key idea is the relationship between **configuration keys**, rather than manual string concatenation in Java code. If another source provides a new value for `app.api.host`, the referencing URL can pick up the new value when Spring resolves the placeholder.

It is important to distinguish:

- **`${key}`**: property placeholder syntax, referencing a key in `Environment`.
- **`${key:default}`**: references a key and provides a fallback value when the key is missing.
- **`#{...}`**: Spring Expression Language (SpEL), a different expression evaluation mechanism.
- **Shell expansion**: for example `${HOME}` in Bash, processed by the shell before the Java program runs if not properly quoted.
- **Configuration binding**: mapping properties to Java objects, for example using `@ConfigurationProperties`; binding may use values containing placeholders, but it is not the placeholder mechanism itself.

## 2. Basic Syntax

General form:

~~~text
${property.name}
~~~

Example:

~~~properties
spring.application.name=order-service
app.banner.title=Welcome to ${spring.application.name}
~~~

When the effective `spring.application.name` is `order-service`, `app.banner.title` can be resolved to `Welcome to order-service`.

Multiple placeholders can be used in the same value:

~~~properties
db.host=localhost
db.port=5432
db.name=orders
db.url=jdbc:postgresql://${db.host}:${db.port}/${db.name}
~~~

Corresponding result:

~~~text
jdbc:postgresql://localhost:5432/orders
~~~

A placeholder does not have to occupy the entire string. It can appear at the beginning, middle, or end of a string:

~~~properties
app.log.prefix=[${spring.application.name}]
app.storage.path=/srv/${spring.application.name}/data
app.health.url=${app.api.url}/health
~~~

The last example also illustrates **multi-level referencing**: `app.health.url` references `app.api.url`, and the value of `app.api.url` may in turn contain other placeholders.

### 2.1. Line Order in a File Is Not Execution Order

~~~properties
app.url=https://${app.host}/v1
app.host=api.example.test
~~~

Even though `app.host` appears after `app.url`, the placeholder can still resolve when querying configuration. This is not a line-by-line sequential program; the parser reads the property pairs, and Spring looks up keys through `Environment`.

### 2.2. Not Limited to a Single File

Placeholders are not limited to referencing properties declared in the same file. Referenced values can come from `application-prod.properties`, external files, environment variables, Java system properties, or command-line arguments, as long as they have been loaded into `Environment` via the appropriate configuration loading mechanism.

## 3. Resolution Mechanism via `Environment`

Spring Framework provides `Environment`, `PropertyResolver`, and `PropertySource` implementations. Spring Boot adds the Config Data mechanism and common configuration sources to this system.

When a component requests a value:

1. Spring searches for the property by key name across sources, following precedence order.
2. If the selected value contains a placeholder, the resolver can look up the key inside the placeholder.
3. The value of the referenced key is substituted into the string.
4. If nested placeholders remain, the resolver can continue resolving them as supported.
5. The component receives the processed value, which may then pass through type conversion and validation.

Example:

~~~properties
app.region=ap-southeast-1
app.storage.path=/data/${app.region}/orders
~~~

Java reads the value:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StorageSettings {
    private final Environment environment;

    public StorageSettings(Environment environment) {
        this.environment = environment;
    }

    public String storagePath() {
        return environment.getRequiredProperty("app.storage.path");
    }
}
~~~

In the example configuration, `storagePath()` returns `/data/ap-southeast-1/orders`.

**Note:** references are resolved when a component actually uses Spring's mechanism, not as a permanent text replacement in the source file. This explains why a key in a higher-precedence source can affect placeholders in a lower-precedence file.

## 4. Referencing Properties in `application.properties`

Example of organizing shared configuration:

~~~properties
spring.application.name=inventory-service

app.http.scheme=https
app.http.host=localhost
app.http.port=8443

app.http.base-url=${app.http.scheme}://${app.http.host}:${app.http.port}
app.http.health-url=${app.http.base-url}/actuator/health
app.log.prefix=[${spring.application.name}]
~~~

Resolvable values:

| Key | Value |
| --- | --- |
| `app.http.base-url` | `https://localhost:8443` |
| `app.http.health-url` | `https://localhost:8443/actuator/health` |
| `app.log.prefix` | `[inventory-service]` |

There is no need to add quotes to `.properties` values just because they contain placeholders. In Java properties, the first unescaped `=` separates key and value; `:` characters appearing inside a URL value do not necessarily split the property.

If a value contains backslashes or special characters of the file format, you must also understand `.properties` escaping rules. For example, `\n` is a newline, and `\\` represents a backslash. These rules belong to the file format and are applied before a Spring component uses the value.

## 5. Referencing in YAML

In `application.yml`, use nested structure and semantically identical placeholders:

~~~yaml
spring:
  application:
    name: inventory-service

app:
  http:
    scheme: https
    host: localhost
    port: 8443
    base-url: "${app.http.scheme}://${app.http.host}:${app.http.port}"
    health-url: "${app.http.base-url}/actuator/health"
  log:
    prefix: "[${spring.application.name}]"
~~~

The YAML parser processes the key/value structure, and then Spring Boot places the resulting properties into a configuration source. The `${...}` string is processed by Spring's placeholder mechanism when used.

### 5.1. When Should You Use Quotes?

In YAML, strings containing `:`, `#`, `[`, `]`, or other special characters sometimes need quotes to prevent the parser from interpreting them as YAML syntax. Using appropriate double quotes or single quotes makes it clear that a value is a string.

Example:

~~~yaml
app:
  api-url: "https://${app.api.host}:${app.api.port}/v1"
~~~

Do not treat YAML quotes the same as quotes added directly to a `.properties` value. Those are two different format-parsing rules.

### 5.2. Distinguishing YAML Interpolation from Spring Placeholders

Plain YAML does not know that `${app.api.host}` is a Spring property. It is Spring Boot and Spring APIs that use the appropriate resolver mechanism to perform substitution. If the same file is read by a non-Spring application, the placeholder may remain a literal text string.

## 6. Default Values with `${key:default}`

Extended syntax:

~~~text
${property.name:default-value}
~~~

Allows providing a default value if the referenced property does not exist during lookup.

Example:

~~~properties
app.api.host=${APP_API_HOST:localhost}
app.api.port=${APP_API_PORT:8080}
app.api.url=http://${app.api.host}:${app.api.port}/v1
~~~

If `APP_API_HOST` and `APP_API_PORT` are not provided from sources the resolver can find, the result can be `http://localhost:8080/v1`. When both keys are present, the values from those sources are used.

Some common examples:

~~~properties
app.display-name=${spring.application.name:unknown-service}
app.log.level=${APP_LOG_LEVEL:INFO}
app.timeout=${APP_TIMEOUT:3s}
app.features.audit-enabled=${APP_AUDIT_ENABLED:false}
~~~

A placeholder's default value **does not create a new property** in `Environment`. For example, `${APP_TIMEOUT:3s}` lets the current string receive `3s` when `APP_TIMEOUT` is missing, rather than meaning Spring has declared `APP_TIMEOUT=3s` in a property source.

### 6.1. Empty Default Values

~~~properties
app.optional-suffix=${APP_SUFFIX:}
~~~

If `APP_SUFFIX` cannot be found, the value can become an empty string. An empty string is different from a missing key; converting to a number, boolean, URI, or a validated type can produce different results.

You should not set an empty default for required configuration just to avoid a startup error.

### 6.2. Defaults Containing Colons

~~~properties
app.api.url=${APP_API_URL:https://api.example.test:8443/v1}
~~~

The `:` separating the key name from the default value is the first delimiter at the appropriate position in the expression. The `:` characters appearing inside the default URL are part of the default content, not multiple placeholders.

For very complex expressions or strings carrying special syntax for another library, you should verify them with the exact parser and Spring version in use.

### 6.3. Defaults Do Not Replace Validation

~~~properties
app.retry-count=${APP_RETRIES:3}
~~~

If `APP_RETRIES` is declared as `many` and a Java component requires `int`, the placeholder can resolve to `many`, yet type conversion will still fail. Default values primarily handle missing keys; they do not automatically guarantee valid data.

## 7. Nested Placeholders

You can use a placeholder inside the default part of another placeholder:

~~~properties
app.primary.host=${PRIMARY_HOST:${FALLBACK_HOST:localhost}}
~~~

Intended meaning: prefer `PRIMARY_HOST`; when missing, check `FALLBACK_HOST`; when both are missing, use `localhost`.

Or:

~~~properties
app.service.name=order-service
app.service.url=${SERVICE_URL:http://${app.service.name}:8080}
~~~

If `SERVICE_URL` does not exist, the default value references `app.service.name` to build the URL.

Spring Framework has a mechanism to resolve nested placeholders, but deeply nested expressions are often hard to maintain and make source-order issues hard to spot. If there are many per-environment configuration variants, consider profile-specific files, conditional documents, or providing a complete property in the deployment environment.

## 8. Canonical Property Names and Relaxed Binding

Spring Boot recommends using **canonical property names** inside placeholders: lowercase, dot-separated segments, and kebab-case for compound words.

**Recommended example:**

~~~properties
app.client.read-timeout=5s
app.effective-timeout=${app.client.read-timeout}
~~~

Avoid relying on non-canonical variants:

~~~properties
app.client.readTimeout=5s
app.effective-timeout=${app.client.readTimeout}
~~~

The canonical form helps Spring Boot apply lookup rules compatible with externalized configuration, including environment variables following its naming conventions.

For the name `app.client.read-timeout`, the environment variable form under Spring Boot's mapping rules is typically `APP_CLIENT_READTIMEOUT`: replace dots with underscores, remove hyphens, and convert to uppercase. `APP_CLIENT_READ_TIMEOUT` is not automatically equivalent across all lookup mechanisms.

Mapping examples:

| Canonical name | Typical environment variable name |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `app.client.read-timeout` | `APP_CLIENT_READTIMEOUT` |
| `app.connection.pool-size` | `APP_CONNECTION_POOLSIZE` |

Binding rules for lists, maps, and special key types can be more complex. When in doubt, verify the property name and source at runtime rather than guessing based on Java naming habits.

## 9. Source Precedence: Target Key vs. Referenced Key

The same key can appear in multiple `PropertySource` entries. Spring Boot defines precedence rules among Config Data inside the JAR, external Config Data, environment variables, Java system properties, and command-line arguments.

Example in `application.properties`:

~~~properties
app.api.host=localhost
app.api.url=https://${app.api.host}/v1
~~~

When launching:

~~~bash
java -jar app.jar --app.api.host=api.production.example
~~~

In standard Spring Boot, command-line properties have higher precedence than files, so the URL can be resolved as `https://api.production.example/v1`.

However, if you run:

~~~bash
java -jar app.jar --app.api.url=https://override.example/v2
~~~

then the **target key `app.api.url` itself** is overridden by the command line. Spring is not forced to use the placeholder-containing string in the lower-precedence file to build the effective URL.

When analyzing a property with placeholders, ask two separate questions:

1. Which source wins for **the property being read**?
2. If the winning value contains `${...}`, which source wins for **the referenced property**?

This is the most important point when an application behaves differently between local and production.

### 9.1. External File Overriding Configuration in the JAR

Inside the JAR:

~~~properties
# classpath:/application.properties
app.api.host=api.default.example
app.api.url=https://${app.api.host}/v1
~~~

Outside the JAR:

~~~properties
# file:./config/application.properties
app.api.host=api.prod.example
~~~

With standard search rules and no higher-precedence source, the external file can override `app.api.host`; `app.api.url` from the JAR resolves to `https://api.prod.example/v1`. There is no need to duplicate the entire URL in both files.

### 9.2. Properties in Profile-Specific Files

~~~properties
# application.properties
app.scheme=https
app.host=api.example.test
app.url=${app.scheme}://${app.host}/v1
~~~

~~~properties
# application-dev.properties
app.scheme=http
app.host=localhost:8081
~~~

When the `dev` profile is active, `app.url` can become `http://localhost:8081/v1` assuming no other source overrides it. The profile decides which files are loaded, while the placeholder uses the effective values of the keys.

Do not assume that a placeholder only looks inside the file that contains it. Spring resolves references across the existing `Environment`.

## 10. `@Value` in Spring Beans

`@Value` is suitable when a bean needs a small number of individual configuration values:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ClientEndpoint {
    private final String baseUrl;

    public ClientEndpoint(
            @Value("${app.api.url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

With:

~~~properties
app.api.host=api.example.test
app.api.url=https://${app.api.host}/v1
~~~

the constructor receives the resolved URL string.

Default values also work directly in `@Value`:

~~~java
@Component
public class RetryPolicy {
    private final long delayMillis;

    public RetryPolicy(
            @Value("${app.retry.delay-ms:500}") long delayMillis) {
        this.delayMillis = delayMillis;
    }

    public long delayMillis() {
        return delayMillis;
    }
}
~~~

Spring performs type conversion during injection according to the available conversion capabilities. If the property contains characters incompatible with `long`, the bean may fail to be created.

### 10.1. Difference from SpEL

~~~java
@Value("${app.retry-count:3}") // Property placeholder.
private int retryCount;

@Value("#{2 * 3}")              // Spring Expression Language.
private int batchSize;
~~~

`${...}` looks up configuration; `#{...}` evaluates a SpEL expression. Although there are contexts that combine the two mechanisms, they should not be used interchangeably or treated as the same syntax.

### 10.2. Injection Timing

Beans typically receive values when they are created. When modifying `application.properties` on disk after the context has started, `@Value` does not automatically update Java fields. The application may require a restart or a specifically designed refresh mechanism.

## 11. `Environment`: Resolving Placeholders on Demand

If an application has a template string that needs to be resolved directly, you can use `Environment` APIs:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class TemplateResolver {
    private final Environment environment;

    public TemplateResolver(Environment environment) {
        this.environment = environment;
    }

    public String resolve(String template) {
        return environment.resolvePlaceholders(template);
    }

    public String resolveRequired(String template) {
        return environment.resolveRequiredPlaceholders(template);
    }
}
~~~

Assuming `app.region=asia`:

~~~java
String a = resolver.resolve("Region: ${app.region}");
// "Region: asia"

String b = resolver.resolve("Region: ${unknown.region}");
// Missing placeholder may be kept as-is.

String c = resolver.resolveRequired("Region: ${unknown.region}");
// Throws an error if the required key is not found.
~~~

The difference:

- `resolvePlaceholders`: processes placeholders that are found and can leave unresolved placeholders unchanged.
- `resolveRequiredPlaceholders`: requires referenced placeholders to resolve successfully; otherwise, it throws an error.

Therefore, you cannot assume every placeholder with a missing key causes Spring Boot to stop starting, or turns into an empty string. You need to identify the exact API or component reading the configuration.

Example of reading a property directly:

~~~java
String url = environment.getRequiredProperty("app.api.url");
~~~

If that property's value contains placeholders, the standard `PropertyResolver` mechanism can resolve its content when read.

## 12. `@ConfigurationProperties` and Value References

For multiple related properties, `@ConfigurationProperties` helps bind configuration into a typed object:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientSettings(
        String host,
        Duration timeout,
        int maxRetries
) {}
~~~

In `application.properties`:

~~~properties
app.default-host=localhost
app.client.host=${app.default-host}
app.client.timeout=5s
app.client.max-retries=2
~~~

The application needs to register this class using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(ClientSettings.class)`. The Spring Boot Binder can resolve the reference and convert `5s` to `Duration`.

There is no need to create placeholders for every field: `@ConfigurationProperties` already binds the `app.client.*` group directly. Use placeholders when you genuinely need to share a value across multiple properties.

You can add Bean Validation and `@Validated` if you need to check required configuration or value constraints.

## 13. Placeholders and Environment Variables

Configuration file:

~~~properties
app.api.url=https://${app.api.host:localhost}/v1
~~~

Environment variable:

~~~bash
export APP_API_HOST=api.example.test
java -jar app.jar
~~~

With canonical naming and standard lookup rules, the `${app.api.host}` placeholder can receive its value from `APP_API_HOST`.

It can also be configured via a JVM property:

~~~bash
java -Dapp.api.host=api.example.test -jar app.jar
~~~

Or an application argument:

~~~bash
java -jar app.jar --app.api.host=api.example.test
~~~

These are three different property sources. If they coexist and declare different values, Spring Boot's precedence determines which value is used.

### 13.1. Avoiding Shell Processing of Placeholders Before Spring

In Bash, `${HOME}` is shell expansion syntax. If you need to pass a literal `${APP_API_HOST:localhost}` to Spring as a command-line argument, use appropriate quoting:

~~~bash
java -jar app.jar '--app.api.host=${APP_API_HOST:localhost}'
~~~

Single quotes in POSIX shells preserve the placeholder string for Spring to read. PowerShell and Windows CMD have different quoting rules; check the proper syntax for the shell you are using.

When a placeholder sits directly inside `application.properties` or `application.yml`, the shell does not interfere with the file's contents during normal Config Data loading.

## 14. Circular References and Non-Existent Key Names

### 14.1. Circular References

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

Both properties point back to each other with no terminating value. When resolved, Spring may report a circular placeholder error. A cycle can also involve multiple keys:

~~~properties
app.a=${app.b}
app.b=${app.c}
app.c=${app.a}
~~~

Fix this by defining a base value that does not depend on keys referencing back:

~~~properties
app.base=localhost
app.a=${app.base}
app.b=${app.a}
~~~

In environments with profiles or override sources, a reference cycle sometimes only appears in a specific combination of sources; trace the **effective value** of each key.

### 14.2. Missing Keys

~~~properties
app.api.url=https://${app.missing.host}/v1
~~~

When `app.missing.host` does not exist, an unresolved placeholder error can occur in APIs requiring a mandatory value. In more permissive APIs, an unresolved placeholder may remain literal.

If a missing key is a valid case, you can use:

~~~properties
app.api.url=https://${app.api.host:localhost}/v1
~~~

If a missing key is a serious configuration error, do not use an arbitrary default just to make the application start. Detect missing required configuration and fail early.

### 14.3. Present Value with Wrong Type

~~~properties
app.retry-count=not-a-number
app.effective-retries=${app.retry-count}
~~~

The placeholder may complete reference resolution, but `not-a-number` is not a valid `int`. Check binding and conversion, not just placeholder resolution.

### 14.4. Empty Value vs. Missing Property

~~~properties
APP_SUFFIX=
app.suffix=${APP_SUFFIX:default}
~~~

If `APP_SUFFIX` is declared with an empty string, the resolver may treat it as an existing value and not use the default, depending on the actual mechanism and source. Do not assume an empty string behaves like an absent property. When special rules for empty strings are needed, express them through explicit validation or configuration logic.

## 15. Keeping Literal `${...}` When Another Template Engine Is Present

A system might need to store the string:

~~~text
Dear ${customerName}
~~~

for another template engine to process later. If the string passes through Spring's placeholder resolver, Spring may try to look up a property named `customerName`.

How to escape depends on the layer doing the processing:

- In `.properties` files, `\` is the file-format escape character; a single backslash may be stripped by the parser before the value reaches Spring.
- In Java string literals, `\` itself also needs proper escaping.
- In YAML, single-quoted and double-quoted scalars have different escaping rules.
- Across Spring Framework versions, escape characters and placeholder handling may differ depending on resolver configuration.

Therefore, do not assume adding a single backslash before `${...}` will always keep the literal intact across all sources. For templates meant for another system, choose a mechanism supported by that component and verify the string **at the final point of use**.

## 16. Placeholders and Configuration Secrets

Example:

~~~properties
spring.datasource.url=${DATABASE_URL:jdbc:postgresql://localhost:5432/app}
spring.datasource.username=${DATABASE_USER:app}
spring.datasource.password=${DATABASE_PASSWORD}
~~~

This approach allows passing database connection settings from the runtime environment. However:

- Placeholders **do not encrypt** passwords or tokens.
- Do not put real secrets in defaults or in files committed to a repository.
- A missing secret may need to fail startup rather than falling back to a sample password.
- Limit displaying resolved values in logs and diagnostic endpoints.
- Access control over secrets depends on deployment infrastructure, not on `${...}` syntax.

When a secret value contains placeholder-like characters, check how sources and resolvers handle it. A secret string must not be accidentally substituted or logged unmasked.

## 17. Interaction with Profiles and Config Data

Suppose inside the JAR:

~~~properties
# application.properties
app.host=api.default.example
app.url=https://${app.host}/v1
~~~

Profile-specific file:

~~~properties
# application-prod.properties
app.host=api.prod.example
~~~

If the `prod` profile is active and no higher-precedence source overrides it, `app.url` can resolve to `https://api.prod.example/v1`.

In multi-document YAML:

~~~yaml
app:
  host: api.default.example
  url: "https://${app.host}/v1"
---
spring:
  config:
    activate:
      on-profile: prod
app:
  host: api.prod.example
~~~

The second document only participates when the profile matches. Placeholders do not activate profiles themselves and do not decide which documents are loaded.

In particular, certain properties that select Config Data locations, such as `spring.config.location` or `spring.config.name`, need to be available very early in startup. Do not assume they can reference any property loaded later from the very location being selected.

## 18. Testing with Spring Boot Test

You can verify resolution behavior in a test context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "app.api.host=test.example",
    "app.api.url=https://${app.api.host}/v1"
})
class PlaceholderResolutionTest {

    @Autowired
    Environment environment;

    @Test
    void resolvesReference() {
        assertEquals(
            "https://test.example/v1",
            environment.getProperty("app.api.url")
        );
    }
}
~~~

This scenario demonstrates that a property injected into a test context can reference another property. The result assumes no higher-precedence test source overrides those two values.

If you want to test the default of `${app.api.host:localhost}`, make sure `app.api.host` genuinely does not appear in any other test source. Otherwise, the test is checking precedence rather than fallback.

## 19. Diagnosing When a Placeholder Returns the Wrong Value

When the application receives a literal `${key}`, a missing value, or an unexpected URL, you can check step by step:

1. **What is the target key?** Identify the property the application is actually reading, e.g., `app.api.url`.
2. **Which source wins for the target key?** The command line may have overridden the entire placeholder string.
3. **Is the key name inside the placeholder correct?** Prefer canonical form, e.g., `app.client.read-timeout`.
4. **Does the referenced key exist?** Check files, profiles, environment variables, JVM properties, and command line.
5. **Was the file containing the key loaded?** Check file name, location, profile, Config Data imports, and document activation.
6. **Is there a circular reference?** Look for a chain of keys calling each other without a root value.
7. **Is there a default?** If so, is it masking a missing required configuration error?
8. **Did pre-Spring parsing happen?** Shell expansion, YAML quoting, or properties escaping may alter the string.
9. **Did the property resolve, but to the wrong type?** Check binding, conversion, and validation.
10. **Was the application restarted after configuration changed?** Standard mechanisms do not automatically refresh all beans and Config Data.
11. **Does the component actually use the Spring resolver?** A library opening a file with its own parser may not understand `${...}`.
12. **Can it be observed safely?** Use `Environment` or protected diagnostic tools; do not print secrets to logs.

Spring Boot Actuator, if enabled with proper security and masking, can help inspect `Environment` and property sources via `/actuator/env`. However, do not expose management endpoints to the Internet or print all secret values just to find the winning source.

## 20. Effective Value Reasoning Exercise

Suppose `application.properties` contains:

~~~properties
app.region=local
app.host=service.${app.region}.example
app.url=https://${app.host}/api
app.timeout=${APP_TIMEOUT:3s}
~~~

**Scenario A: no override sources.**

Values can be:

~~~text
app.host    = service.local.example
app.url     = https://service.local.example/api
app.timeout = 3s
~~~

**Scenario B: running with a command-line argument.**

~~~bash
java -jar app.jar --app.region=prod
~~~

Then:

~~~text
app.host = service.prod.example
app.url  = https://service.prod.example/api
~~~

**Scenario C: directly overriding the URL.**

~~~bash
java -jar app.jar \
  --app.region=prod \
  --app.url=https://another.example/api
~~~

The effective value of `app.url` is the URL passed directly from the command line; `app.region` being `prod` does not force `app.url` to use the placeholder in the file.

**Scenario D: environment provides timeout.**

~~~bash
APP_TIMEOUT=10s java -jar app.jar
~~~

If no higher-precedence source overrides it, `app.timeout` can receive `10s`.

These four scenarios clarify the distinction between property references, fallbacks, and configuration source precedence.

## 21. Adoption Checklist

- Write `${key}` to reference a property via Spring's mechanism.
- Write `${key:default}` when a fallback value is valid both functionally and operationally.
- Prefer lowercase and kebab-case key names per Spring Boot canonical conventions.
- Remember that placeholders can reference other sources, not just the current file.
- When a value is wrong, identify both the source of the **target key** and the source of the **referenced key**.
- Do not use placeholders as a substitute for validation, type conversion, or profile mechanisms.
- Avoid circular references and overly deep nested placeholder structures.
- Do not confuse `${...}` with SpEL `#{...}` or shell variable substitution.
- For large configuration groups, use `@ConfigurationProperties` for typed binding, and only use placeholders where value reuse is truly needed.
- Do not put passwords, API keys, or tokens into default values.
- Verify behavior at the exact component consuming the property and on the exact Spring Boot/Framework version.

## 22. Key Takeaways

**`${key}` links one configuration value to the value of another key.** It operates through Spring's `Environment` and property sources model; Spring Boot makes this practical by supporting multiple externalized configuration sources, profiles, and binding.

**`${key:default}`** provides a fallback when the referenced key is missing. The final result also depends on property source precedence, lookup timing, how parsers process strings, and the Java component consuming the value.

To keep configuration maintainable, define shared keys clearly, use canonical placeholders, avoid circular references, and verify effective values at runtime.

### References

- [Spring Boot Reference — Externalized Configuration, Property Placeholders](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.property-placeholders)
- [Spring Framework Reference — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Framework API — PropertyResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertyResolver.html)
