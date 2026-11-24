# `beans`, `conditions`, `env`, and `configprops` for Diagnostics

When a Spring Boot application starts up yet behaves unexpectedly, you often need to answer four questions: **Was the required bean created? Why was an auto-configuration enabled or disabled? Which source did the effective configuration value come from? How did Spring bind those values into an object?**

Spring Boot Actuator provides four very useful endpoints for this investigation sequence:

- **`/actuator/beans`**: inspect Spring beans managed in the application context.
- **`/actuator/conditions`**: view condition evaluation results, especially for auto-configuration.
- **`/actuator/env`**: inspect property sources and configuration value information in the Spring `Environment`.
- **`/actuator/configprops`**: inspect beans bound using `@ConfigurationProperties`.

They are not identical. A property appearing in `env` does not mean the target object bound it properly; a class appearing in `conditions` does not mean it created a specific bean; and a bean appearing in `beans` does not by itself explain why it was created.

This lesson guides you through using these four endpoints as **an ordered diagnostic toolkit**, from simple scenarios on a developer machine to deployment incidents, while explaining limitations and security risks when inspecting internal information.

## 1. Observing an Application Differs From Just Reading Logs

Startup logs usually tell you the application ran, which port opened, or which exception occurred. Yet there are many questions default logs do not fully answer:

- Was a service not injected because it wasn't scanned or because a condition didn't match?
- Why didn't Boot create a `DataSource`, or why did it create a different implementation than expected?
- Is the `staging` profile active?
- Did the runtime value of `app.client.timeout` come from YAML or an environment variable?
- Did the `ClientProperties` object bind `Duration` and boolean fields correctly?
- Why do two environments running the same artifact behave differently?

A useful diagnostic model:

```text
                          Symptom
                             │
                             ▼
                   Does the bean exist?
                             │
                     /actuator/beans
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
             Missing                  Bean exists
                │                         │
                ▼                         ▼
     Why didn't conditions      Does the bean/config have
     create the bean?           the right runtime data?
                │                         │
                ▼                         ▼
     /actuator/conditions      /actuator/env
                │                         │
                └────────────┬────────────┘
                             ▼
                /actuator/configprops
                Values bound to the bean?
                             │
                             ▼
                 Deduce root cause with
                 logs and source code
```

Not every incident requires checking all four endpoints. Pick the endpoint based on your question, then cross-check results against configuration and code for the running version.

## 2. What Is Spring Boot Actuator?

**Spring Boot Actuator** is a set of features providing operational information and management endpoints, such as application health, metrics, logging, beans, conditions, and configuration.

In a Gradle project, the common dependency is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

In Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Use the starter compatible with your project's Spring Boot BOM/plugin and version.

**Having Actuator on the classpath does not mean all endpoints are automatically published over HTTP.** Whether an endpoint exists, is enabled, is web-exposed, and is authorized are separate decisions.

If an application has no web server, endpoints may still support other management mechanisms when appropriately configured, but will not automatically gain `/actuator/...` HTTP URLs without HTTP server infrastructure.

## 3. Four Layers of Conditions to Access an Endpoint

To use an endpoint over HTTP, understand the following factors:

1. **Dependency:** Actuator and required dependencies are present.
2. **Endpoint enabled:** the endpoint is activated in application configuration.
3. **Web exposure:** the endpoint is exposed over HTTP.
4. **Security and network:** the caller is permitted to reach the endpoint.

For example: if `/actuator/beans` returns 404, the endpoint may not be exposed, not enabled, or on a different base path/port. If it returns 401/403, the endpoint likely exists yet the caller lacks authentication/authorization.

If connection is refused, check the server/management port, network binding, or whether the application even started.

Do not lump **404**, **401**, **403**, and **connection refused** together as a single “Actuator isn't working” error.

## 4. Enabling the Right Endpoints for Diagnostics

In common Spring Boot versions, only a very limited set of endpoints—typically including `health`—is exposed over the web by default.

To use the four endpoints in a protected diagnostic environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans,conditions,env,configprops
```

Or `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,beans,conditions,env,configprops
```

The list above specifies endpoints published over HTTP. It is **not security configuration**.

Example URLs when the application runs at `localhost:8080` using the default base path:

```text
http://localhost:8080/actuator/beans
http://localhost:8080/actuator/conditions
http://localhost:8080/actuator/env
http://localhost:8080/actuator/configprops
```

If `management.server.port` or `management.endpoints.web.base-path` differs from default, the URLs change too.

**Operational warning:** do not turn on all four endpoints publicly on the Internet just to debug. They can expose bean names, classes, package structure, property keys, config sources, and other internal details even when sensitive values are masked. Expose only temporarily, restrict network access, and apply proper authentication/authorization.

## 5. Checking Endpoint Discovery

When HTTP Actuator discovery is enabled and appropriately exposed, calling:

```bash
curl http://localhost:8080/actuator
```

may return a document containing links to exposed endpoints.

Illustrative abbreviated example:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://localhost:8080/actuator/health",
      "templated": false
    },
    "beans": {
      "href": "http://localhost:8080/actuator/beans",
      "templated": false
    }
  }
}
```

The actual discovery document depends on version, enabled endpoints, web exposure, security, and discovery page config.

The `curl` command here assumes a local environment allowing access. In a protected environment, receiving `401 Unauthorized` or `403 Forbidden` when unauthenticated is desired behavior, not a bug.

Do not use an unauthenticated local example as a production deployment template.

## 6. What Questions Does `/actuator/beans` Answer?

The **`beans`** endpoint provides information about Spring beans in the application context: bean name, type, scope, aliases, resource, and certain dependency relationships when supplied by the endpoint/backend.

Appropriate questions:

- Was `notificationService` actually registered?
- Which implementation class does the bean belong to?
- Which configuration declared a bean?
- Are there multiple beans of the same type?
- Which context does the bean reside in?
- Is the bean's scope singleton, prototype, or another scope?
- Which dependencies are declared for a bean in reported metadata?

Example call:

```bash
curl http://localhost:8080/actuator/beans
```

An **illustrative response snippet, not a mandatory schema across all versions**:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "orderService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.orders.OrderService",
          "resource": "class path resource [com/example/orders/OrderService.class]",
          "dependencies": ["orderRepository"]
        }
      }
    }
  }
}
```

Specific values such as context ID, resource, type, or dependency list depend on the application and Spring Boot version.

**What the endpoint proves:** the Spring container registered the reported bean definitions/beans in that context.

**What the endpoint does not prove on its own:** that the bean works properly in business terms, that transactions work, that a request definitely passes through a proxy, or that every injection relationship is represented completely like a source-code graph.

## 7. A Simple Bean Example

Suppose we have:

```java
package com.example.orders;

import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@Repository
public class InMemoryOrderRepository {

    public String find(String id) {
        return "order-" + id;
    }
}

@Service
public class OrderService {

    private final InMemoryOrderRepository repository;

    public OrderService(InMemoryOrderRepository repository) {
        this.repository = repository;
    }

    public String findOrder(String id) {
        return repository.find(id);
    }
}
```

If both classes are within component-scan scope, `beans` can contain names like:

```text
inMemoryOrderRepository
orderService
```

From there you can verify the type and context of each bean.

If `orderService` is missing, common causes are:

- The class is outside the package scanned by `@SpringBootApplication`.
- Missing `@Service`, `@Component`, `@Bean`, or another registration mechanism.
- The bean was excluded by `@Profile` or `@Conditional...`.
- A configuration class containing `@Bean` was not imported/scanned.
- You are inspecting the wrong instance/application context.

**Note:** normally a missing constructor dependency causes application startup to fail. When startup succeeded yet a bean is missing from `beans`, specifically check whether the bean was actually expected to register in that context, rather than assuming bean creation failed and silently vanished.

## 8. `beans` and Multiple `ApplicationContext`s

A Spring Boot application can have multiple contexts, such as the main application context and a management context when using a separate management server port.

Thus `beans` can organize the response under keys:

```text
contexts
  ├── application
  │     └── beans
  └── management
        └── beans
```

This is only an illustrative diagram, not a mandatory list of contexts.

If a bean is not in the context you are viewing, verify:

1. Which process/instance the URL belongs to.
2. Whether the port belongs to the application server or management server.
3. Whether there are parent/child contexts or a management child context.
4. Which context the bean was registered in.
5. Which contexts the endpoint is reporting.

If two different applications share a service name in a multi-replica environment, do not rely solely on bean names; verify instance identity, deployment version, and context ID.

## 9. Does `beans` Help Detect Proxies?

A bean can be wrapped in a Spring AOP proxy because of `@Transactional`, `@Async`, caching, or custom aspects.

In `beans`, the `type` field may reflect type information as determined by the endpoint/reporting backend. It is **not a complete tool to prove a bean's interceptor chain**.

To determine whether an injected bean is an AOP proxy, you can use APIs in code or tests:

```java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(orderService);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(orderService);
boolean classProxy = AopUtils.isCglibProxy(orderService);
```

Or verify behavior through integration tests.

Use `beans` for **does the bean exist and what type is it**, then use AOP diagnostics when asking **whether calls go through a proxy**.

## 10. What Questions Does `/actuator/conditions` Answer?

The **`conditions`** endpoint presents evaluation results of auto-configuration conditions and conditional configurations reported by the framework.

This is very helpful when asking:

- Why did Spring Boot create or skip a default bean?
- Why did an auto-configuration not match?
- Is a required class missing from the classpath?
- Was a property condition satisfied?
- Did an existing bean cause `@ConditionalOnMissingBean` not to match?
- Did the application type (Servlet, Reactive, or non-web) affect the condition?

Call:

```bash
curl http://localhost:8080/actuator/conditions
```

The response is typically grouped by application context and sections describing evaluation results, such as:

- `positiveMatches`.
- `negativeMatches`.
- `unconditionalClasses`.

Keys and structure can vary by version.

## 11. Reading an Illustrative Condition Report

An abbreviated mock response snippet:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "ExampleMetricsAutoConfiguration": [
          {
            "condition": "OnClassCondition",
            "message": "Required class was found"
          }
        ]
      },
      "negativeMatches": {
        "ExampleMailAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "Required property condition did not match"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

The configuration names and messages above are **invented examples**, used only to explain how to read the report.

Distinguish:

- **Positive match:** conditions reported as satisfied in the evaluation context.
- **Negative match:** at least one condition was not satisfied; the message may indicate why.
- **Unconditional class:** configuration recorded as requiring no conditional evaluation according to the report's classification.

Do not read a positive match as a guarantee that **every** desired bean was created and works properly. A configuration class can have `@Bean` methods carrying their own conditions; cross-check `beans` as well.

## 12. Common Spring Boot Conditions

| Annotation/condition | General Check | Diagnostic Scenario |
|---|---|---|
| `@ConditionalOnClass` | Class is on classpath | Missing starter/library dependency |
| `@ConditionalOnMissingClass` | Class is not on classpath | A different stack was brought in |
| `@ConditionalOnBean` | Matching bean exists | Infrastructure dependency does not exist |
| `@ConditionalOnMissingBean` | No matching bean exists | User bean overrode the default |
| `@ConditionalOnProperty` | Property matches condition | Flag disabled or different value |
| `@ConditionalOnWebApplication` | Suitable web application context exists | Running as NONE while expecting web configuration |
| `@ConditionalOnNotWebApplication` | Not a web application | Configuration meant for batch/CLI |
| `@ConditionalOnResource` | Suitable resource exists | Resource not packaged in artifact |
| `@ConditionalOnExpression` | Expression per condition contract | Expression evaluated false |
| `@Profile` | Profile expression matches | Bean intended for dev/prod was excluded |

`conditions` helps inspect many conditions, yet **not every condition on every bean is always displayed with equal detail**.

If you need to know whether a component was excluded by `@Profile` or never scanned, check component scanning, active profiles, and source configuration too. The auto-configuration report does not completely replace reading code.

## 13. Example: `@ConditionalOnProperty` Not Matching

Configuration:

```java
package com.example.orders.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "true"
    )
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
```

Runtime configuration:

```properties
app.notification.enabled=false
```

The condition is not satisfied, so `notificationSender` provides no bean.

How to investigate:

1. Search for `notificationSender` in `beans`.
2. If absent, confirm `NotificationConfiguration` was loaded.
3. Check whether `conditions` has information on this condition.
4. Check `env` to see what `app.notification.enabled` currently is.
5. Verify which property source that value came from.
6. Compare the property against business requirements before rushing to change it to true.

If the configuration class was not scanned/imported, the condition may never even get a chance to be evaluated as expected. In that case, the cause does not lie in the property value.

## 14. `@ConditionalOnMissingBean`: Why Did the Default Bean Disappear?

An auto-configuration often supplies a default bean when the application has not provided its own implementation.

Conceptual example:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

If the application already registered another `Clock` bean, `@ConditionalOnMissingBean(Clock.class)` may not match and the default bean is skipped.

User-defined example:

```java
@Configuration(proxyBeanMethods = false)
public class BusinessClockConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

During context initialization, the outcome also depends on configuration/bean definition processing order and other conditions.

Investigation steps:

- In `conditions`, find messages about `OnBeanCondition` or missing-bean conditions.
- In `beans`, identify which `Clock` bean is present.
- Check which configuration created that bean.
- Check scope/type/qualifiers when multiple candidates exist.

A “did not match because bean found” message is usually not an error. It can show that Spring Boot **yielded configuration control** to the application-provided bean.

## 15. When Startup Fails, How Do You Inspect Conditions?

If the application cannot build its context, `/actuator/conditions` over HTTP is usually **unavailable**. This is a practical limitation: Actuator HTTP endpoints are most useful once the application has started enough to serve management requests.

In a startup failure, you can use startup debug mode:

```bash
java -jar app.jar --debug
```

Or Gradle:

```bash
./gradlew bootRun --args="--debug"
```

Or Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--debug"
```

Spring Boot can print an additional **condition evaluation report** to the logs to help diagnose auto-configuration.

**Note:** `--debug` enables specific Spring Boot logging/debug behavior; it does not mean enabling TRACE for every package. Do not assume every exception's full cause appears in the report alone; you still must read stack traces and perform error analysis.

Do not accidentally leave debug mode enabled long-term in production due to log volume and potential disclosure of internal details.

## 16. What Questions Does `/actuator/env` Answer?

The **`env`** endpoint provides information about the Spring `Environment` and the `PropertySource`s composing runtime configuration.

Appropriate questions:

- Which profiles are active?
- How many property sources contribute to application configuration?
- Is the property `app.client.timeout` present?
- Does the effective value come from a file, environment variable, or command line?
- Why was a property in `application.yml` overridden?
- Is a property missing or misspelled?

Example:

```bash
curl http://localhost:8080/actuator/env
```

When needing a specific property, many versions support an endpoint form like:

```bash
curl http://localhost:8080/actuator/env/app.client.timeout
```

Exact URLs depend on web base path, version, and security. For property names with special characters, encode the path properly.

**Important:** the endpoint can return masked/sanitized values to limit exposure of sensitive data. Seeing a key does not mean the caller is permitted to see the plaintext value.

## 17. What Are `Environment` and `PropertySource`?

Spring `Environment` is the abstraction providing configuration and profile information. One `Environment` can aggregate multiple `PropertySource`s.

Example:

```text
Environment
    │
    ├── commandLineArgs
    │     └── app.client.timeout=2s
    │
    ├── systemEnvironment
    │     └── APP_CLIENT_TIMEOUT=5s
    │
    ├── systemProperties
    │     └── user.timezone=UTC
    │
    └── application.yml
          └── app.client.timeout=10s
```

If these property sources are ordered by precedence as simulated above, the effective value of `app.client.timeout` could be `2s`, not `10s` from YAML.

Treat the illustration as a reasoning model. **Spring Boot's actual precedence order** has its own rules and is influenced by profiles, imports, command line, environment, test overrides, or custom property sources.

Thus, when investigating configuration, the right question is not just “what does the YAML file say?” but **“from which source is `Environment` resolving this property?”**

## 18. An Example of Precedence

In `application.yml`:

```yaml
app:
  client:
    timeout: 10s
```

When running:

```bash
java -jar app.jar --app.client.timeout=2s
```

In standard Boot configuration with command-line properties enabled, `2s` takes higher precedence than the value in the YAML file.

If you also set an appropriate environment variable:

```text
APP_CLIENT_TIMEOUT=5s
```

which source wins still depends on property source precedence; in common Boot setups, the command-line property `--app.client.timeout=2s` beats environment variables and application files.

Cases where the application picks up `10s` instead of `2s` could be due to:

- Command-line properties being disabled or arguments not passed to `SpringApplication`.
- You are calling the wrong instance.
- The property name was mistyped.
- Another configuration source was added with unexpected precedence.
- Code reads a different key instead of `app.client.timeout`.

`env` lets you verify sources and effective values; do not guess from a single file.

## 19. How Does Property Origin Help Diagnostics?

Some configuration sources support **origin metadata** showing where a property was defined, such as file and line number or equivalent source.

An illustrative response for a property:

```json
{
  "property": {
    "source": "Config resource 'class path resource [application.yml]'",
    "value": "******"
  },
  "activeProfiles": ["dev"]
}
```

This example only illustrates the idea; field names and how origin is represented are not an exact required schema across every Boot version. In many versions, the endpoint also reports each `propertySource` and `origin` in its own structure.

What to read:

- Is the queried **key** exact?
- Which **source** provides the effective value?
- Does **origin** point to a specific resource/location?
- Is the **value** masked?
- Do **active profiles** match the deployment?

Origin is very useful when an application combines `application.yml`, `application-prod.yml`, environment variables, and config imports.

## 20. Do Not Confuse Environment Variable Names with Property Keys

Spring Boot has relaxed binding / equivalent naming rules for many configuration cases.

Example canonical property:

```properties
app.client.max-retries=4
```

A typically matching environment variable name is:

```text
APP_CLIENT_MAXRETRIES=4
```

Spring Boot's environment variable naming rules for binding typically include: replacing dots with underscores, removing dashes, and uppercasing. Thus you should not assume `APP_CLIENT_MAX_RETRIES` is always equivalent for every type of lookup.

If a property is visible in the OS environment yet the application binds the wrong value:

1. Verify the canonical property name.
2. Check spelling and prefix.
3. Check how the library/property binder interprets the name.
4. Check whether `env` has the source property.
5. Check `configprops` to see how the final object was bound.

For new application properties, writing canonical keys in kebab-case from the start is generally easier to maintain.

## 21. Protecting Configuration Values When Viewing `env`

`env` is a sensitive endpoint because it can list configuration names such as:

```text
spring.datasource.url
spring.datasource.username
spring.datasource.password
external.api.token
security.oauth2.client-secret
```

Even when values are masked, property names can reveal architecture, integrations, or which systems the application uses.

In many modern Spring Boot lines, the `env` endpoint has a default value-masking policy and property:

```properties
management.endpoint.env.show-values=never
```

There are modes to display values for authorized callers, yet **you should not enable plaintext display in shared environments just for debugging convenience**. An endpoint being protected by authentication is not necessarily reason enough to share secrets with every member who has operator access.

A safe policy:

- Prefer inspecting keys, sources, and origins to the extent needed.
- Keep sensitive values sanitized.
- Grant access only to appropriate operations staff/tools.
- Never paste raw `env` responses into public tickets/chats.
- Use a secret manager or dedicated configuration tooling when secrets must be verified, instead of printing plaintext.

## 22. What Questions Does `/actuator/configprops` Answer?

The **`configprops`** endpoint focuses on beans bound via **`@ConfigurationProperties`**.

Appropriate questions:

- Was the properties class registered as a bean?
- Which prefix is used for binding?
- What values did the target object receive after binding?
- Which configuration source did each value come from, when origin/input metadata is supported?
- Were numbers, booleans, or durations converted to the right Java types?
- Why does a property appear in `env` yet the object still uses a default?

Call:

```bash
curl http://localhost:8080/actuator/configprops
```

Some versions support querying by prefix, for example:

```bash
curl http://localhost:8080/actuator/configprops/app.client
```

Do not assume every Boot version shares the exact same filtering path format; check endpoint discovery and docs for your actual version.

`configprops` is **not a duplicate of `env`**. It reports the binding state of `@ConfigurationProperties` beans, not every property key in the environment.

## 23. `@ConfigurationProperties` Example

Suppose the application has configuration:

```yaml
app:
  client:
    base-url: https://example.invalid
    timeout: 5s
    max-retries: 3
    enabled: true
```

Declare a typed properties object:

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration timeout,
        int maxRetries,
        boolean enabled
) {
}
```

Register scanning:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Service usage:

```java
@Service
public class ClientService {

    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration timeout() {
        return properties.timeout();
    }
}
```

In a compatible setup, Spring Boot binds:

- `base-url` to `URI`.
- `timeout: 5s` to a five-second `Duration`.
- `max-retries: 3` to `int`.
- `enabled: true` to `boolean`.

`https://example.invalid` is only a documentation placeholder URL so examples do not accidentally call a real service.

## 24. Reading a `configprops` Response

An abbreviated illustrative response:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "app.client-com.example.orders.config.ClientProperties": {
          "prefix": "app.client",
          "properties": {
            "baseUrl": "******",
            "timeout": "******",
            "maxRetries": "******",
            "enabled": "******"
          },
          "inputs": {
            "timeout": {
              "value": "******",
              "origin": "application.yml"
            }
          }
        }
      }
    }
  }
}
```

**This is not a mandatory schema or print format**: bean names, nested field names, how `Duration` renders, inputs/origin structure, and masking mechanisms differ by Spring Boot version.

What to focus on:

1. Does the `ClientProperties` bean exist?
2. Is the prefix `app.client`?
3. Were the necessary fields bound?
4. Were values sanitized?
5. If origin is present, which source did the input come from?
6. Do actual runtime values match the typed object used by the service?

Do not try to infer plaintext values from `******`. Masking is a protective policy, not a binding error.

## 25. Where Do `env` and `configprops` Differ?

This is the most important comparison between the two configuration endpoints.

| Aspect | `env` | `configprops` |
|---|---|---|
| Observed target | `Environment` and property sources | `@ConfigurationProperties` beans |
| Dataset | Runtime property keys/sources | Configurations bound into typed objects |
| Shows keys unused by any bean? | Possibly | Not necessarily |
| Shows properties bean prefix? | Not the primary goal | Yes |
| Shows binding into Java fields? | Not directly | Possibly |
| Traces property overrides by source? | Very suitable | May have input/origin metadata |
| Diagnoses conversion/defaults | Requires checking code/binder | Better suited |
| May contain sensitive info | Yes | Yes |
| Applies only to `@ConfigurationProperties`? | No | Primarily yes |

**Example:** `env` shows `app.client.timeout` has a value from an environment variable. However, `configprops` helps verify `ClientProperties.timeout` actually received that value as a `Duration`.

If code uses `@Value("${app.client.timeout}")` instead of `@ConfigurationProperties`, `configprops` will not necessarily have a corresponding object. In that case, check the injection point or a dedicated diagnostic test/service.

## 26. Case: `env` Has the Key, Yet `configprops` Lacks the Bean

Suppose `env` shows:

```text
app.client.timeout=5s
```

yet `configprops` has no `ClientProperties` bean.

Possible causes:

1. The class has `@ConfigurationProperties` yet was not registered via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or a suitable factory method.
2. The class lies outside scan scope.
3. The bean was excluded by `@Profile` or a condition.
4. The prefix is wrong, so you are looking for the wrong name.
5. You are querying a different context/instance.
6. The application does not use `@ConfigurationProperties` for that setting.

**A property existing in `Environment` does not make Spring automatically create a properties bean of any name.** Spring needs to know which object to bind.

If the properties bean exists yet fields are wrong, check field names, bindability, constructors/setters, nested structures, and conversion.

## 27. Case: `configprops` Has the Bean, Yet Data Is Wrong

For example, YAML source has:

```yaml
app:
  client:
    max-retries: 5
```

yet the object observed at runtime uses a different default.

Possibilities to check:

- Another property source is overriding the value.
- Prefix or field name does not match the canonical property.
- A default value exists on the constructor/field.
- The class uses a different binding mechanism than expected.
- A custom converter is transforming the data.
- The inspected object belongs to a different context/instance.
- The running application is not executing the artifact/config file you just edited.

**If data cannot be converted to a required type**, Spring Boot usually reports a binding error while creating the bean; an application starting up successfully does not guarantee every value is business-correct, though many severe conversion errors would already prevent startup.

Use `env` to trace the source, then `configprops` to inspect the binding outcome. Both perspectives complement each other.

## 28. Binding to a Data Type Does Not Mean the Value Is Valid

Example:

```yaml
app:
  client:
    max-retries: -3
    timeout: 0s
```

These values convert cleanly into `int` and `Duration` syntactically, yet are invalid if business policy requires non-negative retries and positive timeout.

You can add Bean Validation to the properties object in compatible versions:

```java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(0) int maxRetries,
        boolean enabled
) {
}
```

This snippet is illustrative. It requires appropriate validation imports, a Bean Validation provider/dependency, and constraints matching project needs; for instance, checking a positive timeout requires a suitable constraint or validator beyond `@NotNull`.

`configprops` helps **observe** bound values; validation helps **prevent** invalid configuration states at startup. The two mechanisms have different jobs.

## 29. `configprops` Also Needs Data Protection

A `@ConfigurationProperties` object can contain:

```java
@ConfigurationProperties(prefix = "external.payment")
public record PaymentProperties(
        URI endpoint,
        String username,
        String password,
        String apiToken
) {
}
```

Do not assume that merely residing inside a Java object makes fields safe to expose publicly.

In modern Spring Boot lines, an important setting is:

```properties
management.endpoint.configprops.show-values=never
```

Default masking modes and behavior can vary by version; verify in your running system.

Even when values are masked, the response can reveal integration names, prefixes, config structures, or runtime class names. Authentication, authorization, and network restrictions remain necessary.

Do not set `show-values=always` in production just to debug. That can inadvertently expose secrets to anyone allowed to call the endpoint.

## 30. Comparing `beans`, `conditions`, `env`, and `configprops`

| Question | Primary Endpoint | Cross-Check Endpoint |
|---|---|---|
| Does bean `orderService` exist? | `beans` | `conditions` if bean depends on a condition |
| Auto-configuration did not create a bean? | `conditions` | `beans`, `env` |
| Did another bean suppress a default bean? | `conditions` | `beans` |
| Which profiles are active? | `env` | Startup log |
| Did property come from file or environment? | `env` | `configprops` |
| Has the config object been bound? | `configprops` | `beans` |
| What value did the typed field receive? | `configprops` | `env` |
| Property key exists yet bean is missing? | `env`, `beans` | `conditions` |
| Startup fails before server runs? | Startup log/`--debug` | Code/configuration; do not expect Actuator HTTP |
| A `@Transactional` method has no effect? | No single endpoint suffices | Proxy diagnostics/integration test |
| Request returns 500? | Logs/traces/metrics | Check the four endpoints only if suspecting config/beans |

No single endpoint answers every failure. The key mindset is **asking specific questions and combining the right sources of evidence**.

## 31. Diagnostic Workflow 1: Missing Bean

Scenario: the application should have `NotificationSender`, yet it does not seem to run.

**Step 1 — Confirm the symptom.** Did startup fail with `NoSuchBeanDefinitionException`, or did the app start while notifications never execute? Both cases require different investigation steps.

**Step 2 — Check `beans` while the app is running.**

```bash
curl http://localhost:8080/actuator/beans
```

Find the bean by type/name in the right context.

**Step 3 — Check `conditions`.** If the bean is created via `@ConditionalOnProperty` or auto-configuration, look for match/non-match details.

**Step 4 — Check `env`.** Verify what effective value a property like:

```text
app.notification.enabled
```

currently holds and where it came from.

**Step 5 — Check registration.** If there is no conditional report entry, check component scanning, `@Configuration` imports, `@Bean` definitions, and active profiles.

**Step 6 — Verify with tests or controlled restarts.** Adjust config only after finding the root cause. Do not blindly enable properties to force a bean to appear.

If startup fails before endpoints become available, use stack traces and the condition report via startup debug instead of trying HTTP calls.

## 32. Diagnostic Workflow 2: Auto-Configuration Did Not Match

Scenario: you expected an auto-configured connection pool, yet the app uses another bean or has no datasource as expected.

**Step 1:** locate the relevant section in `conditions`, such as results of `OnClassCondition`, `OnBeanCondition`, or `OnPropertyCondition`.

**Step 2:** verify runtime dependencies and that the classpath has the needed libraries.

**Step 3:** use `beans` to find which corresponding beans exist.

**Step 4:** use `env` to confirm relevant keys, such as datasource URLs or feature flags, within permitted bounds without exposing secrets.

**Step 5:** read configuration source/condition semantics. A negative match may be completely normal if Boot backed off because the application supplied its own bean.

**Step 6:** fix the actual root cause—dependency, property, custom bean config, or module—then verify in an appropriate environment.

**Do not treat every negative match as an error.** A normal application always has many non-matching auto-configurations intended for other technology stacks.

## 33. Diagnostic Workflow 3: Configuration Overridden

Scenario: `application.yml` has:

```yaml
app:
  client:
    timeout: 10s
```

yet the service observes a shorter timeout.

**Step 1:** use `env` to locate `app.client.timeout` and the effective property source.

**Step 2:** check whether there is a command-line property `--app.client.timeout=2s` or an equivalent environment variable.

**Step 3:** check active profiles, config imports, and profile-specific files.

**Step 4:** if code uses `@ConfigurationProperties`, check `configprops` to verify the final `Duration`.

**Step 5:** if code uses `@Value`, check the annotation key, default value, and type conversion.

**Step 6:** compare effective values across replicas. One pod having a different environment variable can explain inconsistent behavior.

The goal is finding the **overriding source** rather than immediately editing a YAML file that runtime isn't even using.

## 34. Diagnostic Workflow 4: Two Instances Behave Differently

Scenario: the same application version, yet instance A has a feature while instance B does not.

Inspect **per instance**, not merely by hitting a shared load balancer:

1. Confirm which artifact version each instance is running.
2. Check active profiles in `env`.
3. Compare effective property keys and origins without leaking secrets.
4. Compare present/absent beans in `beans`.
5. Compare relevant condition matches in `conditions`.
6. Compare `configprops` for typed configuration beans.
7. Inspect deployment rollouts, ConfigMaps, environment variables, restart timing, and secret references.

When accessing through a load balancer, two calls to `/actuator/env` can hit **two different replicas**, making results appear to change randomly. Verify instance identity.

Do not collect full plaintext configurations from replicas into a shared file for diffing. Prefer comparing keys, non-sensitive flags, versions, and origin metadata.

## 35. Endpoint Enabled Differs From Endpoint Exposed

An endpoint can be:

- Present on the classpath.
- Configured as enabled.
- Not exposed over HTTP.
- Available only over another supported management protocol.
- Exposed yet protected by Spring Security.
- Exposed yet bound only on a separate management interface/port.

Depending on the version, there are separate properties controlling enabled state and web exposure.

Example limiting web exposure:

```properties
management.endpoints.web.exposure.include=health,info,beans
```

This does not necessarily mean `conditions` and `env` are disabled for every access method; it only specifies they are not in the designated **web exposure** list.

For security:

- **401:** caller is unauthenticated.
- **403:** caller is authenticated yet lacks permission, or access is denied by security policy.
- **404:** endpoint is not at the called URL, not exposed/enabled, or on a different path.
- **Connection refused:** no listener on the target host/port, check host/port/process.

Inspect actual HTTP responses and network configuration instead of guessing.

## 36. Protecting Actuator Endpoints with Spring Security

If an application uses Spring Security, sensitive endpoints must have explicit authentication and authorization applied. When defining a custom `SecurityFilterChain`, remember that Boot's default security configuration can back off; responsibility for protecting both endpoints and application URLs shifts to the application's config.

An illustrative pattern with two filter chains:

```java
package com.example.orders.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                .permitAll()
                .anyRequest()
                .hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest()
                .authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

This is an example of **path authorization**, not a complete authentication system. Configure a real identity provider or authentication mechanism and grant `ROLE_OPS` appropriately. Do not hardcode admin accounts with static passwords in source just to use Actuator.

If the management server runs on a separate port/context, verify how security filter chains apply in that setup. With WebFlux, the security API differs from Servlet; do not copy `HttpSecurity` verbatim into a reactive application.

Network restrictions remain necessary even with application security. Ideally, management endpoints should only traverse trusted administrative channels.

## 37. Management Port and Base Path

You can separate the management port from the business serving port with appropriate configuration:

```properties
server.port=8080
management.server.port=8081
management.endpoints.web.base-path=/actuator
```

Then, in applications supporting this configuration, management endpoints can be accessed on port 8081:

```text
http://localhost:8081/actuator/beans
```

To restrict the management listener bind to loopback in a setup with a **separate management port**:

```properties
management.server.port=8081
management.server.address=127.0.0.1
```

This helps restrict remote network access in a suitable model, yet does not replace access control, firewalls, and actual deployment controls.

If the main server and management endpoints share one port, do not assume `management.server.address` creates an independent network binding. Separate address binding ties into the management server context/port mechanism of each version.

In containers, binding loopback can block collectors or port-forwarding mechanisms if the design is incompatible. Decide based on network topology rather than copying config blindly.

## 38. Changing the Actuator Path

The default base path is usually `/actuator`, though it can be changed:

```properties
management.endpoints.web.base-path=/manage
```

Then the corresponding URLs can be:

```text
/manage/beans
/manage/conditions
/manage/env
/manage/configprops
```

With a different management port, the base path is usually applied relative to the management root; with certain server/context-path configurations, full URLs can vary.

If you see 404 while the application is running, check `management.endpoints.web.base-path` before concluding the endpoint is disabled.

Do not expose sensitive endpoints on a public API gateway without an operational reason and strong authorization policies.

## 39. What Information Can Be Exposed?

| Endpoint | Information Potentially Revealed | Risk |
|---|---|---|
| `beans` | Bean names, packages, classes, resources, dependencies | Reveals internal architecture and libraries |
| `conditions` | Auto-configurations, classpath indicators, property conditions | Reveals technologies and feature flags |
| `env` | Property keys, sources, origins; values if policy allows | Reveals config and risks exposing secrets |
| `configprops` | Properties classes, prefixes, field structure, bound values if permitted | Reveals typed configuration/secrets |
| `health` | Health components and statuses | Can reveal downstream systems if details are too broad |

A good rule: **expose only needed endpoints, to needed people, for the needed duration**.

If responses must be shared for investigation:

- Redact hostnames, usernames, tokens, credentials, and sensitive paths.
- Do not strip out root-cause evidence like property keys or condition messages when they can be kept safely.
- Do not paste full dumps into public issue trackers.
- Set expiration/retention on exported diagnostic data.
- Check copies residing in log collectors, attachments, and chat.

## 40. Why Do Values Display as `******`?

Configuration endpoints can mask values according to Spring Boot policy.

Example:

```json
{
  "name": "app.client.timeout",
  "value": "******"
}
```

Do not conclude:

- The property equals a string of six asterisks.
- The binder failed.
- The app is actually using a default.
- The value does not exist.

This may simply be a **sanitized representation**.

If you need to verify a non-sensitive value, prefer a test or a diagnostic abstraction exporting only whitelisted data, such as:

```java
@Component
public class TimeoutReporter {

    private final ClientProperties properties;

    public TimeoutReporter(ClientProperties properties) {
        this.properties = properties;
    }

    public String report() {
        return "Timeout configured: " + properties.timeout();
    }
}
```

This snippet is only suitable if timeout is permitted to be displayed. Do not build an endpoint returning an entire properties object in production to bypass Actuator's sanitization mechanism.

## 41. Debugging via Actuator and Debugging via Logs Complement Each Other

Choose the right tool for the type of incident.

| Tool | Best For |
|---|---|
| Startup log | Context creation errors, ports, exceptions, startup lifecycle |
| `--debug` | Condition evaluation report at startup |
| `beans` | Inventory of Spring beans once app is running |
| `conditions` | Why conditional configurations matched or did not match |
| `env` | Property sources, active profiles, effective configuration |
| `configprops` | Typed configuration beans and binding information |
| Metrics/tracing | Latency, error rates, request paths, and performance |
| Heap/thread dump | Memory leaks, deadlocks, thread states |
| Integration tests | Proving behavior in a controlled context |

Do not use `beans` to conclude a thread is deadlocked, nor use `env` to prove which controller an HTTP request entered.

If the symptom is performance or data consistency, the observability toolkit may need metrics, traces, database diagnostics, or thread dumps alongside these four endpoints.

## 42. When an Endpoint Is Unreachable

Practical diagnostic checklist:

1. Has the application started up and begun listening?
2. Is the Actuator starter on the runtime classpath?
3. Are you targeting the right application instance/port?
4. Is there a separate management port?
5. Was the base path changed?
6. Is the endpoint enabled and web-exposed?
7. Is a `SecurityFilterChain` or network rule blocking it?
8. Is an API gateway/proxy rewriting the path?
9. Is a firewall, service mesh, or ingress policy affecting traffic?
10. If returning 401/403, is that authentication/authorization working as designed?

Some typical issues:

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `/actuator/health` works, `/actuator/beans` 404 | `beans` not exposed | Check web exposure |
| All `/actuator` 404 | Missing Actuator, different base path, or wrong port | Check dependencies/path/management config |
| 401 when calling `env` | Endpoint requires authentication | Use valid operational channel and credentials |
| 403 after login | Missing role or authorization policy | Check security rules |
| Connection refused on management port | No listener or different bind address | Check process/port/address |
| `env` shows `******` | Sanitization policy | Do not treat as a binding error |
| `configprops` lacks expected class | Properties bean not registered or doesn't use this binding mechanism | Check scan/enable/prefix |
| `conditions` has many negative matches | Stack doesn't need those auto-configurations | Analyze only entries related to symptom |
| Results vary through load balancer | Requests hitting different replicas | Verify instance identity |

## 43. Low-Risk Usage in Development

A relatively safe workflow:

1. Run the app in an isolated local or development environment.
2. Add the right version of `spring-boot-starter-actuator`.
3. Temporarily expose only the needed `beans`, `conditions`, `env`, and `configprops`.
4. Restrict network access and apply suitable security.
5. Keep config value masking enabled.
6. Use an HTTP client tool to inspect responses.
7. Retain only the snippets needed for the incident.
8. Cross-check with code/configuration and run tests if needed.
9. Remove unnecessary exposure before promoting config to production.
10. Document root cause and prevention rather than leaving broad debug access open.

Do not commit configuration like:

```properties
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
```

into a repository used for shared deployments. Wildcard `*` web exposure combined with showing all values creates a huge exposure surface; this example is **a configuration to avoid**, not a best practice step.

## 44. Complete Investigation Example: Feature Not Enabled

Suppose an application has an email-sending feature.

Configuration:

```java
@Configuration(proxyBeanMethods = false)
public class MailFeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.mail",
        name = "enabled",
        havingValue = "true"
    )
    MailSender mailSender() {
        return new LocalMailSender();
    }
}
```

Properties:

```yaml
app:
  mail:
    enabled: false
```

Scenario: the development team thought mail was enabled because another config file had `enabled: true`.

**Investigation across the four endpoints:**

**1. `beans`**

Search for `mailSender`. If absent, confirm the symptom: the bean was not registered. If present, verify its implementation and context.

**2. `conditions`**

Look for `MailFeatureConfiguration` or the related condition. If the report contains information, look for why the property matched/did not match. Do not assume the report lists every project-authored bean.

**3. `env`**

Query `app.mail.enabled`. Check the key, effective value (if permitted to view), and winning property source. An environment variable or command-line argument might be overriding the file thought to be active.

**4. `configprops`**

If the application has `@ConfigurationProperties(prefix="app.mail")`, check whether the properties bean bound and received the expected flag. If using only `@ConditionalOnProperty`, there does not have to be a properties bean for `configprops` to show.

**5. Evidence-backed conclusion**

Example: “On instance B, `app.mail.enabled` is set to false by an environment variable, so the condition does not match and `mailSender` is not created.”

This is a verifiable conclusion, far better than guessing at Spring container bugs.

## 45. Complete Investigation Example: Wrong Timeout Value

Class:

```java
@ConfigurationProperties(prefix = "integration.catalog")
public record CatalogProperties(
        Duration timeout,
        int maxAttempts
) {
}
```

Configuration:

```yaml
integration:
  catalog:
    timeout: 10s
    max-attempts: 3
```

One deployment sets:

```text
INTEGRATION_CATALOG_TIMEOUT=1s
```

Investigation:

1. `env` helps verify `integration.catalog.timeout` comes from the environment and check the winning value if the caller is authorized.
2. `configprops` shows whether `CatalogProperties` was registered and bound.
3. `beans` confirms both the properties bean and consuming service exist in the context.
4. `conditions` is only helpful if creating the catalog client depends on conditional configuration; not strictly needed for an unconditionally created bean.
5. After identifying the overriding source, update deployment configuration through the proper change process.

If `configprops` returns masked values, do not disable sanitization on a public endpoint. Verify the timeout via unit/integration tests or a whitelisted diagnostic view in a protected environment.

## 46. Hands-On Exercises

### Exercise A — Enabling Actuator

Create a Spring Boot web app with Actuator. Temporarily expose `health` and `beans` in development. Access:

```text
/actuator/health
/actuator/beans
```

Compare the returned data. Explain why an endpoint on the classpath is not necessarily exposed by default.

### Exercise B — Finding a Bean in the Context

Create a `@Service` named `OrderService` and a `@Repository` named `OrderRepository`. Use `beans` to inspect their names, types, and scopes.

Then move the service class outside the scanned package and observe the difference after restarting. Explain why merely having a Java file does not create a Spring bean.

### Exercise C — A Non-Matching Condition

Create a `@Bean` with:

```java
@ConditionalOnProperty(
    prefix = "feature.report",
    name = "enabled",
    havingValue = "true"
)
```

Try `feature.report.enabled=false` and `true`. Compare `beans` with the information in `conditions`, if that condition is reported in your setup.

### Exercise D — Property Source Precedence

Set `app.client.timeout=10s` in YAML, then pass `--app.client.timeout=3s` on the command line. Use `env` to query the key and find the effective source. Do not enable exposing all values.

### Exercise E — Binding a Properties Object

Create `ClientProperties` with `Duration timeout` and `int maxRetries`. Register it via `@ConfigurationPropertiesScan`. Use `configprops` to locate the bean and its prefix.

### Exercise F — `env` Has the Key, No `configprops` Bean

Define property `app.experimental.mode` without declaring a corresponding `@ConfigurationProperties`. Observe `env` and `configprops`. Explain why the results differ.

### Exercise G — Wrong Active Profile

Create `application-dev.yml` and `application-prod.yml` with different non-sensitive properties. Run the app with dev/prod profiles, comparing `env`, origins, and startup logs.

### Exercise H — Startup Failure

Introduce a configuration error that prevents the context from starting. Try calling `/actuator/conditions` and explain why the URL may be unavailable. Then run with `--debug` and read the condition evaluation report in the logs.

### Exercise I — 401, 403, and 404

Enable Actuator and security in a test environment. Call an unexposed endpoint, an exposed endpoint without logging in, and an endpoint requiring a higher role. Distinguish the HTTP outcomes and causes.

### Exercise J — Multi-Instance

Run two instances of the same application where one has `feature.report.enabled=true` and the other has false. Compare `beans`, `conditions`, and `env` by calling each instance directly. Explain why calling through a load balancer can yield changing results across requests.

### Exercise K — Protecting Configuration Data

Put a fake secret in test configuration. Observe the sanitization mechanism of `env` and `configprops` in your version. Explain why you should never paste full responses into public tickets or turn on `show-values=always` in production.

### Exercise L — Writing a Diagnostic Report

Write a short report for the scenario “mail sender was not created” using this structure:

```text
Symptom:
Instance/version:
Bean presence:
Condition result:
Effective property source:
Configuration binding:
Root cause:
Proposed fix:
Evidence retained safely:
```

Record only necessary data, with no credentials.

## 47. Takeaways

1. **`beans`** is used to inspect the Spring bean inventory, types, scopes, resources, and contexts.
2. **`conditions`** helps analyze conditional configuration, especially why auto-configurations matched or did not match.
3. **`env`** helps inspect the Spring `Environment`, active profiles, property sources, precedence, and origins.
4. **`configprops`** is used to inspect `@ConfigurationProperties` beans and binding results.
5. **Having a property in `env` does not mean a properties bean exists; having a properties bean does not guarantee its values satisfy business requirements.**
6. **A positive match** does not prove every bean exists; **a negative match** is not automatically an error.
7. If application startup fails before the HTTP management server is ready, use startup logs and `--debug` rather than expecting `/actuator/conditions`.
8. Actuator dependency, endpoint enabled state, web exposure, and security are separate layers.
9. Web exposure does not imply an endpoint is secured. Authentication, authorization, and network controls must be enforced.
10. `env` and `configprops` may sanitize values; `******` does not mean the property literally holds six asterisks.
11. Avoid using `show-values=always` and avoid exposing `beans`/`conditions`/`env`/`configprops` broadly in production.
12. With multiple replicas, make sure you are inspecting the right instance, version, and context.
13. For a missing bean, go from `beans` to `conditions` and `env`; if typed configuration is involved, also inspect `configprops`.
14. For a wrong property value, go from `env` to find the effective source, then cross-check `configprops`.
15. Property origin and bind results only make sense when you know the exact property name, profile, and configuration class.
16. `@ConditionalOnMissingBean` can intentionally skip a default bean because the application supplied another implementation.
17. Not every `@Profile`, custom condition, or runtime failure is fully detailed in the condition report.
18. Never use Actuator to bypass secret-masking mechanisms; keep only necessary diagnostic evidence.
19. These endpoints complement startup logs, metrics, traces, and integration tests; they do not replace them.
20. Always diagnose from specific questions, document evidence-based conclusions, and narrow exposure once investigation concludes.

**Core mindset:** **`beans` tells you *what* is in the container, `conditions` explains *why* certain configurations were or were not chosen, `env` points to the *effective configuration source*, and `configprops` shows how configuration landed in *typed beans*.** Combining these four views with startup logs and source code lets you diagnose Spring Boot accurately without guesswork.
