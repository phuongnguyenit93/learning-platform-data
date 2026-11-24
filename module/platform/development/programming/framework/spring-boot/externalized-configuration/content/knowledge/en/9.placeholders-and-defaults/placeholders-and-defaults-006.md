# Unresolved Placeholder Errors and Circular References in Spring Boot

Spring Boot supports referencing one configuration value from another using the `${property.name}` placeholder syntax. For example, an application can set a service URL based on a host name or pull a password from an environment variable. This reduces configuration duplication, yet it can also introduce two major categories of errors:

1. **Unresolved placeholder:** Spring cannot find the property requested by the reference expression.
2. **Circular placeholder reference:** a property directly or indirectly references itself, leaving the resolution chain with no terminating point.

Both errors can occur while loading or consuming configuration, especially when creating beans with `@Value` or when Spring Boot binds properties. However, the exact timing of the error also depends on **the access API**, property sources, and whether handling is strict or allows ignoring unresolved placeholders.

This lesson uses Spring Boot 3.3.x and Java 21, progressing from basic syntax to sample applications, diagnostics, and practical fixes.

## 1. What Is a Configuration Placeholder?

A placeholder is a text segment of the form:

~~~text
${property.name}
~~~

When the value is resolved, Spring searches for `property.name` across the `PropertySource`s of `Environment`. If a matching value is found, the reference segment is replaced with that value.

Example in `application.yml`:

~~~yaml
app:
  host: localhost
  port: 8085
  base-url: "http://${app.host}:${app.port}/api"
~~~

If these values are effective and not overridden by a higher-precedence source, the `app.base-url` expression resolves to:

~~~text
http://localhost:8085/api
~~~

In `application.properties`, the equivalent declaration is:

~~~properties
app.host=localhost
app.port=8085
app.base-url=http://${app.host}:${app.port}/api
~~~

Use canonical Spring Boot placeholder names, such as `app.service-url` in lowercase with hyphens. This naming convention enables consistent relaxed binding across configuration sources.

### The Final Value Can Come from Another Source

Suppose `application.yml` contains:

~~~yaml
app:
  host: localhost
  base-url: "http://${app.host}/api"
~~~

When running:

~~~bash
java -jar demo.jar --app.host=service.internal
~~~

`app.base-url` can become `http://service.internal/api` because the CLI argument supplies a higher-precedence effective value for `app.host`. Placeholders reference **property names in Environment**, not necessarily keys in the same YAML file.

## 2. Placeholders with Default Values

Common syntax:

~~~text
${property.name:default-value}
~~~

If the requested property **does not exist**, Spring can use the default portion after the colon.

Example:

~~~yaml
app:
  display-name: "${APP_DISPLAY_NAME:Local Demo}"
  endpoint: "${APP_ENDPOINT:http://localhost:8080}"
  retries: "${APP_RETRIES:3}"
~~~

If the corresponding variables are absent, the resolved values are:

~~~text
app.display-name = Local Demo
app.endpoint     = http://localhost:8080
app.retries      = 3
~~~

For `retries`, the placeholder result normally starts as text; when bound to `int` via `@ConfigurationProperties`, Spring Boot performs appropriate type conversion.

You can write nested placeholders:

~~~yaml
app:
  endpoint: "${APP_ENDPOINT:${APP_FALLBACK_ENDPOINT:http://localhost:8080}}"
~~~

When `APP_ENDPOINT` does not exist, Spring tries `APP_FALLBACK_ENDPOINT`; if both are missing, it uses the final URL. This is a **terminating fallback selection chain**, not a circular reference.

### Empty Values Differ from Non-Existent Values

If `APP_DISPLAY_NAME` exists with an empty string value, the fallback in `${APP_DISPLAY_NAME:Local Demo}` normally **is not triggered just because the value is empty**. Default placeholder syntax is used when a property cannot be resolved, not as a "use default if blank" rule.

If the application requires a non-empty string, validate the value after binding. A placeholder fallback is not a substitute for input validation.

### Not Every Default Is Safe

Suitable fallback values include timeouts, retry counts, local modes, and mock development URLs. For passwords, tokens, or mandatory production endpoints, do not put dummy values to paper over missing configuration; let the application fail with a clear error.

## 3. Unresolved Error: Referencing a Non-Existent Key

Example `application.yml`:

~~~yaml
app:
  payment:
    url: "${PAYMENT_API_URL}"
~~~

If `PAYMENT_API_URL` is not supplied in the environment, a component requiring **mandatory resolution** cannot determine the URL.

Example bean using `@Value`:

~~~java
package com.example.placeholderdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentClient {

    private final String endpoint;

    public PaymentClient(@Value("${app.payment.url}") String endpoint) {
        this.endpoint = endpoint;
    }

    public String endpoint() {
        return endpoint;
    }
}
~~~

If no environment variable or property source provides `PAYMENT_API_URL`, resolution can report an error such as:

~~~text
Could not resolve placeholder 'PAYMENT_API_URL' in value "${PAYMENT_API_URL}"
~~~

In a Spring application, that message may sit deep inside a chain of exceptions during bean creation, such as `BeanCreationException` or `UnsatisfiedDependencyException`. Therefore, look for **the root cause** in the stack trace rather than stopping at the outer wrapper exception.

A direct missing-key case:

~~~java
@Component
public class ReportService {

    public ReportService(@Value("${report.timeout}") String timeout) {
        // ...
    }
}
~~~

If `report.timeout` does not exist and has no suitable default, mandatory placeholder processing at the injection point can fail.

**Note on error timing:** Spring Boot does not necessarily check and throw errors for all placeholder-like text immediately upon reading the YAML file. An expression may only cause an issue when it is accessed, resolved, or bound by a mechanism requiring a valid value.

## 4. Why Do Placeholders Sometimes Stay Literal Without Crashing the App?

Spring Framework supports both ways of resolving placeholders:

- **Allow unresolved:** keep the `${missing.key}` segment if not found.
- **Require resolution:** throw an exception when the key is not found and has no fallback.

You can see the difference using `Environment`:

~~~java
import org.springframework.core.env.Environment;

String nonStrict = environment.resolvePlaceholders(
        "URL=${missing.url}");

String strict = environment.resolveRequiredPlaceholders(
        "URL=${missing.url}");
~~~

If `missing.url` does not exist:

~~~text
nonStrict = "URL=${missing.url}"
strict    = error because missing.url is absent
~~~

These two APIs are defined on `PropertyResolver`/`Environment`. The first is useful when the application intentionally accepts unreplaced strings; the second fits when you need to fail fast.

Do not infer that every property-reading API handles missing placeholders identically. The behavior of `getProperty`, `@Value`, and Binder depends on timing, the resolver, and Spring's integration rules.

### Explicit Java Verification Example

~~~java
package com.example.placeholderdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class PlaceholderInspection {

    @Bean
    ApplicationRunner inspect(Environment environment) {
        return args -> {
            String sample = "Current=${missing.key}";

            System.out.println(environment.resolvePlaceholders(sample));

            try {
                System.out.println(
                        environment.resolveRequiredPlaceholders(sample));
            } catch (IllegalArgumentException ex) {
                System.out.println("Required resolution failed: "
                        + ex.getMessage());
            }
        };
    }
}
~~~

This example illustrates handling errors when **explicitly invoking the resolver**. In production applications, only catch errors where valid recovery is possible; for required configuration, usually report clearly and halt startup instead of silently using incomplete data.

## 5. Missing Property Cases Caused by Misspelled Names

Suppose you have the configuration:

~~~yaml
app:
  external-service:
    base-url: https://service.example.org
~~~

Yet the bean uses:

~~~java
@Value("${app.external.base-url}")
private String endpoint;
~~~

`app.external.base-url` and `app.external-service.base-url` are two different paths. Even though a valid URL exists in YAML, the placeholder is looking up the wrong key.

A similar mistake happens when an environment variable name is wrong:

~~~yaml
app:
  api-key: "${PAYMENT_API_KEY}"
~~~

~~~bash
export PAYMENT_KEY="sample"
~~~

The `PAYMENT_KEY` variable does not automatically satisfy `PAYMENT_API_KEY`. You cannot conclude "the variable was exported" if its name does not match the actual expression.

Other common causes:

- The configuration file is outside the locations Spring Boot is loading.
- The wrong profile name was specified, so `application-prod.yml` is not applied.
- `spring.config.location` replaced the default locations, so the file containing the desired key is no longer loaded.
- A YAML document has `spring.config.activate.on-profile` that does not match the current profile.
- The key name sits at the wrong level due to incorrect YAML indentation.
- A higher-precedence property source overwrote the value with a different placeholder string.

When diagnosing, verify **the property path**, **the property source**, and **the placeholder expression** being processed.

## 6. Direct Circular Reference: A Key Pointing to Itself

The simplest circular error:

~~~properties
app.name=${app.name}
~~~

Or in YAML:

~~~yaml
app:
  name: "${app.name}"
~~~

The intent "pull `app.name` from elsewhere" is not expressed properly, because the current property references itself. If that exact value is chosen by the resolver to resolve `app.name`, logically the process unfolds as:

~~~text
Need to resolve app.name
  → read value: ${app.name}
  → need to resolve app.name again
  → read value: ${app.name} again
  → ...
~~~

Spring detects this situation and reports a circular placeholder reference error instead of entering an infinite loop.

The message typically means:

~~~text
Circular placeholder reference 'app.name' in property definitions
~~~

Wording and wrapper exceptions may vary across framework versions or execution paths, but the cause is **the placeholder substitution chain returning to a property name already on the resolution path**.

### Defaults Do Not Fix Self-References

Example:

~~~properties
app.name=${app.name:my-app}
~~~

If the resolver already finds `app.name` and its value references `app.name` again, the `my-app` part does not automatically break the loop. The fallback after the colon applies when the property **is not found**; here the property exists and self-references.

The proper fix is to use **a different source key**, or remove the self-reference altogether:

~~~properties
app.name=${APP_NAME:my-app}
~~~

In this version, `APP_NAME` is a separate configuration name and `my-app` is the fallback when that source key is absent.

## 7. Indirect Circular References Across Multiple Properties

A cycle does not have to appear on the same line. Example:

~~~yaml
app:
  api-url: "${app.gateway-url}"
  gateway-url: "${app.api-url}"
~~~

Resolution trace:

~~~text
app.api-url
   ↓
app.gateway-url
   ↓
app.api-url
   ↓
circular reference
~~~

Both properties exist, so this is not a "key not found" error. The problem is **there is no final value independent of the remaining placeholders**.

A longer cycle:

~~~properties
service.entrypoint=${service.edge}
service.edge=${service.backend}
service.backend=${service.entrypoint}
~~~

Diagram:

~~~text
service.entrypoint → service.edge
        ↑                  ↓
service.backend ←──────────┘
~~~

To fix it, break at least one reference edge with a concrete value or an independent data source:

~~~properties
service.entrypoint=${service.edge}
service.edge=${service.backend}
service.backend=https://backend.example.org
~~~

Now:

~~~text
service.backend    = https://backend.example.org
service.edge       = https://backend.example.org
service.entrypoint = https://backend.example.org
~~~

All three expressions terminate, so there is no longer a cycle.

## 8. Distinguishing Circular References from Valid Reference Chains

A dependency chain is **not** a cycle if it eventually reaches a concrete value:

~~~yaml
app:
  public-host: gateway.example.org
  base-url: "https://${app.public-host}"
  health-url: "${app.base-url}/health"
~~~

Order:

~~~text
app.health-url
    → app.base-url
    → app.public-host
    → gateway.example.org
~~~

Final value:

~~~text
https://gateway.example.org/health
~~~

One property referencing another is itself a useful feature. Errors only occur when there is an unresolved **cycle** or a **non-existent key** in a reference chain requiring mandatory resolution.

### Nested Defaults Can Still Be Valid

~~~yaml
app:
  host: "${APP_HOST:localhost}"
  url: "http://${app.host}:8080"
~~~

If `APP_HOST` is missing, `app.host` receives `localhost`; then `app.url` receives `http://localhost:8080`. This chain terminates, so it is valid.

## 9. Circular Placeholders Differ from Spring Bean Circular Dependencies

Two errors share the word "circular," yet their causes are completely different.

**Circular placeholder:**

~~~properties
app.a=${app.b}
app.b=${app.a}
~~~

This is an error in **configuration values and property resolution**.

**Bean circular dependency:**

~~~java
@Component
class Alpha {
    Alpha(Beta beta) {}
}

@Component
class Beta {
    Beta(Alpha alpha) {}
}
~~~

This is an error in **the dependency graph between beans**. Spring Boot may report a bean creation or circular dependency error with a different message type.

The `spring.main.allow-circular-references` property applies to certain **bean** circular dependency cases; it is not a fix for `app.a=${app.b}` and `app.b=${app.a}`. Changing that property does not create an actual configuration value to terminate a placeholder cycle.

To resolve a circular placeholder, fix **the reference path among properties**.

## 10. Spring Boot Example with Valid and Invalid Configurations

Create a Spring Boot project with `spring-boot-starter` and a main class:

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

Create a class reading configuration:

~~~java
package com.example.placeholderdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoConfiguration {

    @Bean
    ApplicationRunner showGreeting(
            @Value("${demo.greeting}") String greeting) {

        return args -> System.out.println("Greeting: " + greeting);
    }
}
~~~

### 10.1. Valid Case

In `src/main/resources/application.yml`:

~~~yaml
demo:
  user: "Spring"
  greeting: "Hello, ${demo.user}!"
~~~

Run the application; the printed line is:

~~~text
Greeting: Hello, Spring!
~~~

### 10.2. Missing Placeholder Case

Change the file to:

~~~yaml
demo:
  greeting: "Hello, ${demo.user}!"
~~~

If `demo.user` is not supplied by another source, injecting `@Value("${demo.greeting}")` requires resolving the nested expression but has no value for `demo.user`, so the context can fail to initialize the bean and report a missing placeholder error.

Fix in one of two ways:

~~~yaml
demo:
  user: Spring
  greeting: "Hello, ${demo.user}!"
~~~

Or:

~~~yaml
demo:
  greeting: "Hello, ${demo.user:Guest}!"
~~~

The first approach declares the source; the second supplies a valid default.

### 10.3. Circular Reference Case

~~~yaml
demo:
  user: "${demo.greeting}"
  greeting: "Hello, ${demo.user}!"
~~~

When resolving `demo.greeting`, Spring needs `demo.user`; the value of `demo.user` in turn needs `demo.greeting`. To break the cycle:

~~~yaml
demo:
  user: "Spring"
  greeting: "Hello, ${demo.user}!"
~~~

Then run again; resolution now terminates.

## 11. Errors Can Appear at Different Times

This is especially important when reading Spring Boot logs.

| Usage location | When placeholder is processed | Possible symptoms |
| --- | --- | --- |
| `@Value("${missing}")` | During bean creation/injection | Bean creation failure, root cause unresolved placeholder |
| `Environment.resolveRequiredPlaceholders(...)` | When code explicitly calls the method | `IllegalArgumentException` or corresponding resolution error |
| `Environment.resolvePlaceholders(...)` | When code explicitly calls the method | May keep the missing expression as a string |
| `@ConfigurationProperties` | When the binder reads values for fields | May trigger bind, conversion, validation errors, or unexpected values depending on type |
| Placeholder chain with a cycle | When the resolver traverses the cycle | Circular placeholder reference error |
| YAML file merely holds an unused value | May not trigger strict resolution yet | Not guaranteed to fail immediately while reading the file |

Do not assume that having `${missing}` in `application.yml` always makes Spring Boot stop during YAML parsing. The YAML parser mainly interprets data structure; placeholder processing happens at the property resolution/binding layer. When an error is reported depends on whether that property is used and by which mechanism it is read.

### Do Not Hide Errors at the Bean Layer If Configuration Is Required

Example:

~~~java
@Value("${payment.secret:demo-secret}")
private String secret;
~~~

This may let the application start when the secret is missing, yet use a value unsuitable for real environments. If a secret is required, require supplying it through a trustworthy secrets mechanism and validate configuration explicitly.

For optional settings like `app.batch-size`, a fallback `${app.batch-size:100}` is usually much more reasonable.

## 12. Placeholders in `@ConfigurationProperties`

For groups of properties, Spring Boot recommends binding into a typed structure. Example:

~~~yaml
service:
  base-url: "${SERVICE_BASE_URL:http://localhost:8080}"
  connect-timeout: "${SERVICE_CONNECT_TIMEOUT:3s}"
~~~

Create the record:

~~~java
package com.example.placeholderdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        String baseUrl,
        Duration connectTimeout) {
}
~~~

Wait — let's check line 616 of `006.md`: it uses `~~~`, NOT ```` ``` ````! Let's make sure we keep `~~~` verbatim everywhere in `006.md`! Let's double check our draft for `006.md` before finishing it.
Continuing `006.md`:

In the main application, enable scanning:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class PlaceholderDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PlaceholderDemoApplication.class, args);
    }
}
~~~

Import `org.springframework.boot.context.properties.ConfigurationPropertiesScan` and the Spring Boot classes as in the earlier main example. During binding, `base-url` maps to `baseUrl`; the string `3s` can be converted to `Duration`.

When a **required** property is needed, you can use Bean Validation on `@ConfigurationProperties` if the project adds the validation dependency and proper registration.

Illustrative example:

~~~java
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotBlank String endpoint) {
}
~~~

If `payment.endpoint` is not declared, validation helps report the missing required configuration clearly. This does not mean Bean Validation automatically catches every leftover placeholder string across all processing paths; you still need to ensure proper configuration sources and resolution mechanisms.

### Using Defaults in Java When Appropriate

A record can define defaults via Java constructs or a config class with field initializers; some constructor-binding styles also support Spring Boot default annotations. However, if the need is simply a fallback for a configuration string, `${name:default}` in the file can be easier to understand.

Choose where to put defaults based on configuration management requirements, avoiding conflicting defaults simultaneously in YAML, Java, and CLI.

## 13. Circular References Caused by Multiple Configuration Sources

Placeholders can point from one source to another. Example:

~~~yaml
# application.yml
app:
  public-url: "https://${app.host}"
~~~

And the `app.host` value comes from an environment variable:

~~~bash
export APP_HOST=example.org
~~~

When the resolver finds `app.host`, the expression resolves to a valid URL.

However, if another source returns:

~~~text
app.host=${app.public-url}
~~~

then the two paths can form a cycle:

~~~text
app.public-url → app.host → app.public-url
~~~

The exact outcome depends on which `PropertySource` wins in precedence order. If a higher source provides a concrete value such as `app.host=example.org`, the cycle can disappear on the effective resolution path. Conversely, if the effective source still contains a self-referencing expression, adding a lower-precedence value will not fix the error.

Therefore, when analyzing an issue, do not look at only one file. Determine **the effective value of each key in the reference chain**, checking CLI arguments, system properties, environment variables, profile files, and imported resources.

## 14. Diagnosing Errors by Tracing the Reference Chain

An easy workflow to follow when hitting an error:

1. Identify the placeholder name in the error message, e.g., `PAYMENT_API_URL`, `app.host`, or `app.base-url`.
2. Locate where the reference is declared: YAML, properties, `@Value` annotation, or an imported file.
3. Verify whether the requested key name has the right spelling, nesting level, and profile.
4. Check which source provides the effective value for that key.
5. If the message is a circular reference, trace the chain `A → B → C → A` and pick one point to hold an **independent base value**.
6. After fixing configuration, rerun and observe the target value with an appropriate API.

Example message:

~~~text
Could not resolve placeholder 'app.gateway.host'
~~~

Search for `${app.gateway.host}` expressions and `app.gateway.host` configuration in effective sources. If documentation defines `app.gateway.url` instead of `app.gateway.host`, the issue may simply be using the wrong name.

With the message:

~~~text
Circular placeholder reference 'app.a' in property definitions
~~~

Write down the value of `app.a`, then write the keys it references, continuing until the path repeats. **Do not blindly add defaults to every line** while leaving the cycle intact.

### Manual Trace Example

~~~properties
app.api=${app.edge}
app.edge=${app.internal}
app.internal=${app.api}
~~~

Trace the chain:

~~~text
app.api
  ↳ app.edge
      ↳ app.internal
          ↳ app.api  ← already appeared earlier
~~~

Change one property to:

~~~properties
app.internal=https://internal.example.org
~~~

This change removes the cycle because `app.internal` now has an independent terminating value.

## 15. Inspecting Configuration Sources and Values

### 15.1. Using `Environment`

You can inspect a non-sensitive property:

~~~java
@Bean
ApplicationRunner inspectConfig(Environment env) {
    return args -> {
        System.out.println(
                "app.host=" + env.getProperty("app.host"));

        System.out.println(
                "app.base-url=" + env.getProperty("app.base-url"));
    };
}
~~~

Place this snippet in a `@Configuration` or `@SpringBootApplication` class with imports:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
~~~

If accessing a value causes a resolution error, you will see the exception at that point. Do not blindly catch all exceptions and treat the configuration as valid; for required configuration, errors should surface clearly so they can be fixed.

### 15.2. Checking Environment Variables

Linux/macOS:

~~~bash
printenv PAYMENT_API_URL
~~~

Windows PowerShell:

~~~powershell
Get-Item Env:PAYMENT_API_URL
~~~

Check the variable in the actual environment of the application process. A variable existing in your personal terminal does not prove that a service running under systemd, Docker, or CI/CD received that same variable.

### 15.3. Checking Active Profiles

~~~java
System.out.println(
        java.util.Arrays.toString(env.getActiveProfiles()));
~~~

If only `dev` is active while the value is defined in `application-prod.yml`, check profile selection before editing placeholder expressions.

### 15.4. Actuator and Logs

If the application already uses Spring Boot Actuator, the `env` or `configprops` endpoints can help trace property origins or configuration binding results when properly enabled and secured. Do not publicly expose endpoints containing sensitive configuration details.

Startup logs and stack traces are usually enough to spot missing placeholder names or circular references. For Config Data processing traces, you can enable verbose logging in development to see which files are loaded. Enabling logs does not fix the underlying error; it only helps identify effective configuration sources.

## 16. Additional Cases to Distinguish

### 16.1. Missing Location Is Not the Same as a Missing Placeholder

Example:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

If the required file does not exist, Spring Boot may throw `ConfigDataLocationNotFoundException`. This is a **cannot find config data resource** error. It differs from a resource loading successfully yet containing `${PAYMENT_API_URL}` with no resolvable value.

The `optional:` prefix on `spring.config.import` skips missing locations; it **does not** automatically generate values for placeholders inside loaded resources.

### 16.2. Circular Placeholders Are Not Profile Configuration Cycles

For instance, `spring.profiles.active` activating `prod`, while YAML has a document for `prod`, is not enough to be a placeholder cycle. Only when a `${...}` string loops back to the property currently being resolved is it a placeholder cycle.

Spring Boot has separate rules on where `spring.profiles.active` and `spring.profiles.include` may be placed; those do not replace property cycle detection rules.

### 16.3. Placeholder Defaults Are Not Java Defaults

~~~java
@Value("${app.retry-count:3}")
private int retryCount;
~~~

Here Spring resolves the placeholder and converts the value for the `int` field. By contrast:

~~~java
private int retryCount = 3;
~~~

is Java field initialization. Both can yield the same value in one case, yet their mechanisms differ, especially when configuration sources override them or when beans are instantiated differently.

### 16.4. Key Names Are Syntax-Sensitive

Writing `${app.service-url}` in canonical form ensures strong compatibility with relaxed binding rules. A name like `${app.serviceUrl}` may be handled differently in certain sources. When a placeholder appears to exist yet cannot be found, check the canonical name and how the source supplies the property.

### 16.5. Placeholders in Log Strings or Text Do Not Auto-Resolve

A string containing `${...}` inside business data does not magically turn into configuration unless it passes through an appropriate resolver. For example, static UI text may need to preserve that syntax verbatim. Only use `resolvePlaceholders` when you genuinely intend to interpolate property names.

## 17. Practice Exercises

### Exercise 1 — Missing Key and Fallback

Given:

~~~yaml
demo:
  host: "${DEMO_HOST:localhost}"
  port: "${DEMO_PORT:9090}"
  url: "http://${demo.host}:${demo.port}/api"
~~~

If `DEMO_HOST` and `DEMO_PORT` are absent, what value does `demo.url` receive?

**Answer:** `http://localhost:9090/api`.

### Exercise 2 — Missing Reference Without Default

Given:

~~~yaml
billing:
  endpoint: "${BILLING_ENDPOINT}"
~~~

And bean:

~~~java
@Value("${billing.endpoint}")
private String billingEndpoint;
~~~

`BILLING_ENDPOINT` is absent from the environment. Predict what happens when Spring performs mandatory resolution for the bean and state two ways to fix it.

**Hint:** supply a valid environment variable/property source, or use a fallback only if a fallback endpoint is genuinely safe.

### Exercise 3 — Detecting a Direct Cycle

~~~properties
demo.name=${demo.name:demo-default}
~~~

Why is having `demo-default` not enough to guarantee no error occurs?

**Answer:** `demo.name` exists and references itself. The resolver can pick up `demo.name` again instead of treating it as an absent property and falling back.

### Exercise 4 — Breaking a Three-Key Cycle

~~~yaml
demo:
  a: "${demo.b}"
  b: "${demo.c}"
  c: "${demo.a}"
~~~

Modify one line so `demo.a` ultimately receives `https://api.example.org`, while keeping references between the other two keys.

**One solution:**

~~~yaml
demo:
  a: "${demo.b}"
  b: "${demo.c}"
  c: "https://api.example.org"
~~~

### Exercise 5 — Distinguishing the Two APIs

With the string:

~~~text
Value=${UNDEFINED_KEY}
~~~

Predict the results of:

~~~java
env.resolvePlaceholders("Value=${UNDEFINED_KEY}");
env.resolveRequiredPlaceholders("Value=${UNDEFINED_KEY}");
~~~

**Answer:** the non-strict call can leave the placeholder unchanged; the required call throws an error when there is no key or default.

### Exercise 6 — Source Precedence

Given:

~~~yaml
app:
  host: localhost
  url: "https://${app.host}"
~~~

Run:

~~~bash
java -jar demo.jar --app.host=api.example.org
~~~

What is the resolved value of `app.url`?

**Answer:** `https://api.example.org`, assuming no higher-precedence source overrides `app.url`.

### Exercise 7 — Identifying Cause from Error Messages

One run reports:

~~~text
Could not resolve placeholder 'MAIL_PASSWORD'
~~~

Another run reports:

~~~text
Circular placeholder reference 'app.mail-host' in property definitions
~~~

Explain the difference. **Answer:** the first case requires finding/providing a value for key `MAIL_PASSWORD`; the second requires tracing the properties referencing `app.mail-host` and breaking the cycle. Merely adding a lower-precedence value may not help if the winning source still creates the cycle.

## 18. Configuration Design Principles to Avoid Errors

- Choose clear, consistent key names, preferring canonical kebab-case in placeholder expressions and configuration files.
- Only use placeholders when two properties genuinely depend on each other; avoid unnecessary multi-layer indirection.
- Design reference chains with an **independent root value**: a literal value, a supplied environment variable, or a valid default.
- Provide fallbacks for optional configuration; for required configuration, let errors surface clearly during bootstrap or validation.
- Avoid direct or indirect references back to the property currently being resolved.
- Check profiles and source precedence order; avoid editing files that Spring Boot is not loading.
- Distinguish placeholder errors from missing Config Data locations or bean circular dependencies.
- When troubleshooting, rely on the root cause and reference path, not just the outer wrapper error message.

## References

- [Spring Boot 3.3 — Externalized Configuration: Property Placeholders](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.property-placeholders)
- [Spring Boot 3.3 — Externalized Configuration and Property Source Order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework — Property Placeholder Resolution](https://docs.spring.io/spring-framework/reference/core/beans/factory-placeholderconfigurer.html)