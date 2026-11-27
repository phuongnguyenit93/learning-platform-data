# Checking Effective Configuration via env and configprops

> **Chapter:** Observability  
> **Module:** SPRING_CLOUD_CORE

When a Spring Cloud application runs across multiple environments, the same property can be declared in a YAML file, environment variable, JVM argument, command-line argument, or remote configuration source. Therefore, reading `application.yml` alone is not enough to know which value the application is actually using. We need to observe the `Environment` after Spring Boot has merged the configuration sources and inspect the values bound to configuration beans.

Spring Boot Actuator provides two complementary endpoints for this purpose: **`/actuator/env`** shows the property sources in the `Environment`, the source of a property, and its resolved value; **`/actuator/configprops`** shows `@ConfigurationProperties` beans along with their bound values and binding inputs. Combining both endpoints helps identify which property wins, where it comes from, and whether the configuration bean received the right value.

This lesson uses client and discovery configuration examples in **SPRING_CLOUD_CORE** to guide you through reading the endpoints, tracing property precedence, understanding relaxed binding, handling masked values, securing Actuator, and testing effective configuration.

## 1. Why Check Effective Configuration?

Suppose an application declares:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true

catalog:
  client:
    base-url: https://catalog.internal
    connect-timeout: 2s
~~~

When deployed, the production environment sets the variables:

~~~text
SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED=false
CATALOG_CLIENT_CONNECT_TIMEOUT=750ms
~~~

The application may receive values from environment variables instead of the values in YAML. If an operator only opens the configuration file inside the JAR, they might mistakenly conclude that registration is enabled and the timeout is two seconds.

Common reasons runtime values differ from the configuration file include:

- A different profile is activated.
- An external configuration file overrides the file packaged inside the JAR.
- An environment variable or JVM system property has higher precedence.
- A command-line argument overrides the declared value.
- Config Server or an imported configuration source provides a different value.
- An environment variable name is not mapped as expected.
- A value exists in the Environment but is not bound to the bean due to a wrong prefix, wrong field name, or unregistered bean.
- A bound value undergoes type conversion, default application, or validation before being used by the application.

`env` and `configprops` answer two different questions: “Where is Spring resolving this property from?” and “What value did the configuration bean receive?”.

## 2. Two Endpoints with Different Roles

| Endpoint | Data Source | Main Question |
| --- | --- | --- |
| `/actuator/env` | Spring `Environment` and `PropertySource`s | Which sources contain the property, and which source provides the selected value? |
| `/actuator/configprops` | Beans bound via `@ConfigurationProperties` | Which configuration beans exist, what are their prefixes, and how are their fields bound? |

### 2.1. env: Observing the Environment

The `env` endpoint presents:

- `activeProfiles` and `defaultProfiles`.
- The list of `propertySources` and the name of each source.
- The properties contained in each source.
- The value and origin of a property when source metadata provides it.
- Information about the source providing the effective value when querying a specific property.

This endpoint is useful for properties read via `Environment`, `@Value`, and properties used for binding, as long as they are placed into the Environment.

### 2.2. configprops: Observing ConfigurationProperties Binding

The `configprops` endpoint aggregates beans configured with `@ConfigurationProperties`. Each bean typically includes:

- Bean name and prefix.
- `properties`: the structure of values bound into the bean.
- `inputs`: input information for each property, including value and origin if available.
- The context containing that bean, useful when the application has multiple ApplicationContexts.

This endpoint is ideal when you want to confirm that a structured configuration was bound properly. It is not a complete list of every property in the Environment. A value read only via `@Value` without belonging to a `@ConfigurationProperties` bean may appear in `env` without having a corresponding bean in `configprops`.

## 3. Configuring Actuator to Expose Both Endpoints

The application needs Spring Boot Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

To access them over HTTP, expose the required endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
~~~

By default, Spring Boot only exposes the `health` endpoint over HTTP and JMX. Having the Actuator dependency does not mean `env` and `configprops` are automatically opened over HTTP.

Default addresses:

~~~text
GET /actuator/env
GET /actuator/configprops
~~~

You can change the base path or management port:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
  server:
    port: 9091
~~~

With this configuration, the endpoints will reside under the `/manage` base path on management port `9091`. Check the actual configuration if an endpoint returns 404; the cause could be base path, port, exposure, or access policy.

Do not use `management.endpoints.web.exposure.include=*` in production without a clear need and proper safeguards. Both endpoints can expose property names, profiles, bean names, classes, and internal topology.

## 4. Reading the Entire Environment via /actuator/env

You can view property sources with curl:

~~~bash
curl -u ops:password http://localhost:8080/actuator/env
~~~

Abbreviated example:

~~~json
{
  "activeProfiles": ["production"],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "systemEnvironment",
      "properties": {
        "CATALOG_CLIENT_CONNECT_TIMEOUT": {
          "value": "750ms"
        }
      }
    },
    {
      "name": "Config resource 'class path resource [application.yml]'",
      "properties": {
        "catalog.client.connect-timeout": {
          "value": "2s",
          "origin": "class path resource [application.yml] - 8:23"
        }
      }
    }
  ]
}
~~~

This is illustrative JSON showing the structure, not a fixed response across all versions. Property source names and how variable names are displayed may vary by environment.

`propertySources` are returned in the precedence order provided by Spring Environment. When the same property exists in multiple sources, the source with higher precedence determines the effective value. Query a specific property directly to see the winning source, rather than guessing from the YAML file alone.

### 4.1. Viewing a Specific Property

The endpoint supports querying by property name:

~~~bash
curl -u ops:password   http://localhost:8080/actuator/env/spring.cloud.service-registry.auto-registration.enabled
~~~

The response for a single property may contain:

- `property.source`: the source providing the selected value.
- `property.value`: the effective value, if allowed to be displayed.
- `propertySources`: relevant sources and occurrences.
- `origin`: the location or origin of the property if metadata is available.

Example:

~~~json
{
  "activeProfiles": ["production"],
  "property": {
    "source": "systemEnvironment",
    "value": "false"
  },
  "propertySources": [
    {
      "name": "systemEnvironment",
      "property": {
        "value": "false",
        "origin": "System Environment Property"
      }
    },
    {
      "name": "Config resource 'class path resource [application.yml]'",
      "property": {
        "value": "true",
        "origin": "application.yml - 4:18"
      }
    }
  ]
}
~~~

In the example, the environment variable provides the value `false` and overrides the value `true` in the YAML file. If a value is sanitized, the value field may be replaced with `******`; you can still view the source name and origin if the endpoint returns this metadata.

### 4.2. Understanding Property Precedence

Spring Boot has many configuration sources, for example:

- Default properties.
- `@PropertySource`.
- Config Data such as `application.yml` and profile-specific files.
- OS environment variables.
- JVM system properties.
- JNDI and servlet init parameters in appropriate environments.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- Test property sources when running tests.

This is an illustrative list of common sources; the exact order and additional sources depend on the version, Config Data imports, and runtime environment. The rule to remember is that a higher-precedence property source can override values from lower-precedence sources.

With Config Data files, profile-specific files and files external to the JAR also have their own precedence rules. Do not draw conclusions solely based on the order files are listed in the repository. Query the effective property via `env` to know which source the application is using.

## 5. Mapping Environment Variable Names to Properties

On many operating systems, environment variable names do not conveniently use dots or hyphens. Spring Boot supports relaxed binding to map environment variable forms to canonical property names.

Examples:

| Property | Environment variable |
| --- | --- |
| `spring.cloud.service-registry.auto-registration.enabled` | `SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED` |
| `catalog.client.connect-timeout` | `CATALOG_CLIENT_CONNECT_TIMEOUT` |
| `catalog.client.base-url` | `CATALOG_CLIENT_BASEURL` |

The common rule for environment variable names is to convert letters to uppercase, dots to underscores, and remove hyphens. For map keys, list indices, and complex names, check the specific binding rules instead of inferring from a simple example.

Deployment example:

~~~bash
export SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED=false
export CATALOG_CLIENT_CONNECT_TIMEOUT=750ms
~~~

If `env` does not show the property as expected:

1. Verify that the variable name is actually passed into the process/container.
2. Check spelling and relaxed binding rules.
3. Check the canonical property using the `/actuator/env/{property.name}` endpoint.
4. Check the active profile and the winning property source.
5. Check whether the `@ConfigurationProperties` bean has the corresponding prefix and field.

Not every dotted property name can be mechanically converted to an environment variable name without considering map keys, list indices, or special characters.

## 6. Reading /actuator/configprops

To view all configuration beans:

~~~bash
curl -u ops:password http://localhost:8080/actuator/configprops
~~~

To filter by prefix:

~~~bash
curl -u ops:password   http://localhost:8080/actuator/configprops/catalog.client
~~~

The response is structured by context and bean. An abbreviated entry:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "catalogClientProperties": {
          "prefix": "catalog.client",
          "properties": {
            "baseUrl": "https://catalog.internal",
            "connectTimeout": "PT0.75S"
          },
          "inputs": {
            "baseUrl": {
              "value": "https://catalog.internal",
              "origin": "class path resource [application.yml] - 7:15"
            },
            "connectTimeout": {
              "value": "750ms",
              "origin": "System Environment Property"
            }
          }
        }
      }
    }
  }
}
~~~

This is an abbreviated illustrative response. Bean name, context ID, Duration representation, and nested structure depend on the configuration class and Spring Boot version.

### 6.1. Distinguishing properties and inputs

Two branches in the response help answer two questions:

- `properties`: the values of the configuration object after binding and type conversion.
- `inputs`: the input information used for binding, usually containing value and origin.

For example, `connectTimeout` in `properties` may be represented as a normalized duration, while `inputs.connectTimeout.value` still displays the source string such as `750ms`. This is why the two fields can differ in representation while still being equivalent in meaning.

Origin helps trace the configuration source, such as a YAML file and line number, an environment variable, or another configuration source. Not every PropertySource provides detailed origin metadata.

### 6.2. The Endpoint Only Displays ConfigurationProperties Beans

`configprops` is not a copy of the entire `env`. It focuses on beans bound with `@ConfigurationProperties`.

If a property is in `env` but not found in `configprops`, check:

- Does the application have a corresponding `@ConfigurationProperties` bean?
- Is the bean's prefix correct?
- Is the bean registered with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`?
- Is the field/property recognized by the binder?
- Is the property only read via `@Value` or `Environment`?

Do not conclude that a property is ignored just because it does not appear in `configprops`.

## 7. Creating a Configuration Bean to Observe Binding

Example of a client configured with its own prefix:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private String baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Register the configuration bean via scanning:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
}
~~~

Or register it explicitly:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogPropertiesConfiguration {
}
~~~

YAML file:

~~~yaml
catalog:
  client:
    base-url: https://catalog.internal
    connect-timeout: 2s
~~~

An environment variable can override the timeout:

~~~text
CATALOG_CLIENT_CONNECT_TIMEOUT=750ms
~~~

After the application starts, `env` shows the winning property source; `configprops` shows how the `CatalogClientProperties` bean bound `connectTimeout`. This dual observation separates configuration loading issues from binding issues.

## 8. Diagnostic Workflow When Values Are Incorrect

Suppose the client is timing out after two seconds even though the deployment declares `CATALOG_CLIENT_CONNECT_TIMEOUT=750ms`. You can investigate in order:

1. Call `/actuator/env/catalog.client.connect-timeout` to see if the property is in the Environment.
2. Check `property.source` to identify the winning source.
3. If the winning source is not system environment, check the variable name and precedence order.
4. Call `/actuator/configprops/catalog.client` to see which bean is bound to this prefix.
5. Compare `inputs.connectTimeout` with `properties.connectTimeout`.
6. Check whether the configuration bean is registered and whether the consuming component injects the right bean.
7. If the configuration was updated after startup, determine whether the bean has a refresh/rebind mechanism or requires a restart.
8. Check whether code overrides the value after binding or uses a client built from the old value.

### 8.1. Common Symptoms

| Symptom | Where to Check | How to Handle |
| --- | --- | --- |
| Property does not appear in env | Process environment, profile, Config Data, property name | Check the configuration source and canonical name |
| env has multiple different values | propertySources and property.source | Identify the source with the highest precedence |
| env is right but configprops has no bean | configprops by prefix | Check scan, EnableConfigurationProperties, and prefix |
| configprops has the bean but fields are not as expected | inputs and properties | Check field name, data type, converter, and default |
| Value is masked as ****** | show-values and sanitization | Check role/authorization; do not expose values broadly |
| Origin is unknown | inputs/propertySources | Check if the source supports origin metadata |
| Value is right after restart but wrong before restart | refresh/rebinding and bean lifecycle | Determine if the bean supports refresh or needs a restart |

### 8.2. When a Property Changes but the Bean Still Uses the Old Value

`env` reflects the current Environment; `configprops` helps inspect bound configuration beans. However, a change in a configuration source does not guarantee that every running object is automatically updated.

For standard configuration beans, determine the binding lifecycle of the Spring Boot and Spring Cloud versions you are using. If the application uses Spring Cloud Context, an appropriate refresh/rebind mechanism or bean replacement via a supported workflow may be required. HTTP clients, connection pools, or objects created from the old value may also need to be recreated.

Do not use seeing a new property in `env` as the sole proof that the entire application has adopted that value.

## 9. Protecting Sensitive Values and Access Permissions

Both endpoints can contain sensitive information such as internal URLs, usernames, tokens, passwords, database details, or integration configurations. By default, Spring Boot sanitizes values returned from `env` and `configprops`; responses may replace values with `******`.

You can control value visibility with `show-values`:

| Value | Behavior |
| --- | --- |
| `never` | Always mask values |
| `always` | Show values to everyone who has access to the endpoint |
| `when-authorized` | Only show values to authenticated users who have the role required by the endpoint |

Example allowing only the `ops` role to view unmasked values:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - ops
    configprops:
      show-values: when-authorized
      roles:
        - ops
~~~

With HTTP endpoints, users must authenticate and satisfy the configured role. If no specific role is set, the version's default rule might allow any authenticated user to see values; declare roles explicitly when using `when-authorized`.

A custom `SanitizingFunction` bean can still mask values even when `show-values` is set to `always` or `when-authorized`. Therefore, never assume changing show-values will always reveal every value.

### 9.1. Secure Configuration for Production

Recommendations:

- Only expose `env` and `configprops` on a management network or through an internal gateway.
- Enable Spring Security or an equivalent authentication mechanism.
- Grant dedicated permissions to operators who need to read configuration.
- Keep `show-values: never` if there is no explicit requirement to view values.
- If viewing values is needed, prefer `when-authorized` and a narrow role like `ops`.
- Do not use `always` for endpoints accessible from broad networks.
- Do not expose all Actuator endpoints just to debug a single property.
- Do not share raw responses containing internal URLs or sensitive details in public tickets/chats.
- Use a secret manager for secrets; do not rely on sanitization to turn endpoints into a safe secret store.

## 10. Testing Endpoints and Binding

You can test a configuration bean individually with an ApplicationContext test, then test the Actuator HTTP endpoints in a Spring Boot test. The example below assumes the application has registered `CatalogClientProperties` and uses Spring MVC test support.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "catalog.client.base-url=https://catalog.test",
        "catalog.client.connect-timeout=750ms",
        "management.endpoints.web.exposure.include=env,configprops"
})
@AutoConfigureMockMvc
class ConfigurationActuatorEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesEnvironmentPropertyOrigin() throws Exception {
        mockMvc.perform(get(
                "/actuator/env/catalog.client.connect-timeout"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.property.source").exists());
    }

    @Test
    void exposesCatalogConfigurationPropertiesBean() throws Exception {
        mockMvc.perform(get("/actuator/configprops/catalog.client"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.contexts.*.beans.*.prefix",
                        hasItem("catalog.client")));
    }
}
~~~

The actual response may differ depending on Spring Boot version, context ID, and bean name. Tests should verify the necessary structure and behavior, avoiding reliance on auto-generated bean names if the application does not fix those names.

### 10.1. Testing Sanitization

Do not write tests requiring secrets to be displayed in the response. Instead, test that sensitive values are masked by default or test role authorization when using `when-authorized`.

For security tests, verify:

- Unauthenticated users cannot access the endpoint per security policy.
- Authenticated users lacking the role do not see unmasked values.
- Users with the permitted role only see values according to the configured policy.
- A custom `SanitizingFunction` is still applied.

### 10.2. Testing Overriding Configuration Sources

You can place the same property in a test YAML file and an environment/property source with higher precedence, then verify `env` reports the right winning source. For automated tests, prefer verifying the bound value on the bean with direct assertions; endpoint tests verify observability and response structure.

Do not try to test all of Spring Boot's precedence in a single test. Create small tests for each important source that your deployment actually uses.

## 11. Common Mistakes and How to Avoid Them

1. **Reading application.yml and assuming it is the runtime value:** check `env` to find the winning source.
2. **Confusing env with configprops:** env shows the Environment; configprops shows beans bound with ConfigurationProperties.
3. **Not seeing a property in configprops and thinking it does not exist:** the property might only be read with Value or Environment.
4. **Seeing a value in env while the bean does not receive it:** check prefix, field name, binding, conditions, and bean registration.
5. **Assuming YAML order dictates precedence:** inspect PropertySource and property.source.
6. **Getting environment variable names wrong:** apply relaxed binding and verify in the endpoint.
7. **Misunderstanding Duration values after binding:** compare inputs with properties; they may have different representations.
8. **Concluding a property is empty because its value is masked:** check show-values and sanitization policy.
9. **Enabling show-values always in production:** restrict with when-authorized, roles, and a management network.
10. **Exposing all Actuator endpoints to debug:** only open the needed endpoints.
11. **Seeing env change and assuming the bean refreshed:** verify configprops and the bean's lifecycle/rebinding.
12. **Not checking origin:** use origin to locate the file, line, or providing source when metadata is available.

## 12. Operational Workflow for Tracing Configuration

When a Spring Cloud behavior differs from the expected configuration:

1. Identify the canonical property name and desired value.
2. Check active profiles and the deployment's configuration sources.
3. Query `/actuator/env/{property.name}` to find the effective value and winning source.
4. Cross-check occurrences in propertySources to understand how the value is overridden.
5. Query `/actuator/configprops/{prefix}` if the property belongs to a ConfigurationProperties bean.
6. Compare inputs with properties to distinguish source values from bound values.
7. Check prefix, fields, type conversion, defaults, and validation.
8. Determine whether the bean or client has applied the value at runtime.
9. Check refresh/rebind/restart if the configuration source changed after startup.
10. Record the findings including property, source, origin, and affected bean; mask all sensitive values before sharing.

**Key takeaway:** `env` answers which properties are in the Environment and which source provides the effective value; `configprops` answers which `@ConfigurationProperties` beans received values after binding. When investigating a Spring Cloud configuration, find the winning source with env, confirm the bound value with configprops, and verify that the bean actually uses that value. Always keep endpoints inside a management network, apply authentication/authorization, and mask secrets according to the appropriate policies of **SPRING_CLOUD_CORE**.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Actuator — Endpoints and Sanitization](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator REST API — Environment](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Boot Actuator REST API — Configuration Properties](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html)
- [Spring Boot — Customizing Sanitization](https://docs.spring.io/spring-boot/how-to/actuator.html)
