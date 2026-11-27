# Same Property Has a Different Value Than Expected in Configuration File

## 1. Symptom

A Spring Boot application can read configuration from multiple sources simultaneously: YAML files inside the JAR, files outside the JAR, profile-specific files, environment variables, JVM system properties, command-line arguments, environment JSON, Config Server, or configuration trees mounted by the deployment platform.

Therefore, seeing a value in application.yml is not enough to conclude that it is the value the application is using. For example, the file contains:

```yaml
inventory:
  routing:
    timeout: 2s
```

Yet application logs show the timeout is 8s. This can be the intended behavior according to Spring Boot's precedence rules: a higher-priority PropertySource supplied the same key and overrode the value in the file.

This lesson guides you through finding the exact source of the value being used, identifying why that source wins, and fixing the issue where the override originates. The content belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_CORE** module. The module focuses on core Spring Cloud abstractions, Spring Cloud Context, externalized configuration, Spring Boot compatibility, discovery, service registry, service communication, and testing/operations.

After this lesson, learners can:

- Explain why the same property can be declared in multiple sources.
- Read Spring Boot's PropertySource precedence order.
- Inspect profiles, external files outside the JAR, and spring.config.import.
- Detect overrides from environment variables, system properties, command line, and SPRING_APPLICATION_JSON.
- Trace value origins using Actuator env and configprops.
- Distinguish values in Environment from values bound into beans.
- Diagnose differences between Spring Cloud Config Data import and legacy bootstrap.
- Fix configuration without accidentally dropping other valid overrides.

## 2. Principle: Spring Reads Environment, Not a Single File

Spring Boot loads configuration sources as PropertySources in the Spring Environment. When looking up a key, Spring searches in precedence order; a higher-priority source can override a lower-priority source.

For example, the same key inventory.routing.timeout can appear in:

| Source | Value |
| --- | --- |
| application.yml packaged in the JAR | 2s |
| application-prod.yml packaged in the JAR | 3s |
| ./config/application-prod.yml outside the JAR | 5s |
| Environment variable INVENTORY_ROUTING_TIMEOUT | 8s |
| JVM argument -Dinventory.routing.timeout=9s | 9s |
| Application argument --inventory.routing.timeout=10s | 10s |

If all of the above sources are loaded and declare the key, the final value can be 10s. Having 2s still present in the JAR file is normal; that file is not the highest-priority source.

Separate three questions:

1. **Which sources declare the key?** There may be several.
2. **Which source wins when read from Environment?** This is the highest-priority source containing the key.
3. **Which value does the bean hold?** The bean may have bound at startup or be holding an old value after a refresh.

Good troubleshooting answers all three questions.

## 3. Spring Boot PropertySource Precedence Order

For Spring Boot 4.1.2, the overall documented order from lowest-priority source to highest-priority source is:

| Order | Source | Example |
| --- | --- | --- |
| 1 | Default properties | SpringApplication.setDefaultProperties(...) |
| 2 | @PropertySource | File declared on a @Configuration class |
| 3 | Config Data | application.yml, profile-specific files, imported files |
| 4 | Random value source | random.* |
| 5 | OS environment variables | INVENTORY_ROUTING_TIMEOUT |
| 6 | Java system properties | -Dinventory.routing.timeout=9s |
| 7 | JNDI attributes | java:comp/env |
| 8 | ServletContext init parameters | Context parameters |
| 9 | ServletConfig init parameters | Servlet parameters |
| 10 | SPRING_APPLICATION_JSON | JSON passed via environment/system property |
| 11 | Command-line arguments | --inventory.routing.timeout=10s |
| 12 | Test annotation properties | @SpringBootTest(properties = ...) |
| 13 | @DynamicPropertySource | Dynamic values in tests |
| 14 | @TestPropertySource | Test properties |
| 15 | Devtools global settings | Devtools settings in user directory |

Sources appearing later can override earlier sources. Thus, the command line usually wins over YAML files; test properties can override application configuration during test execution.

@PropertySource has a special characteristic: this property source is only added to the Environment when the ApplicationContext begins refreshing. That timing is too late to configure early-read properties such as logging.* or spring.main.*. If those keys have no effect, check loading timing rather than just checking key names.

Exact ordering can vary by Spring Boot version and application type. When upgrading, consult the Externalized Configuration page for the exact running version.

## 4. Checking Configuration Files and Profiles

Even without environment variable or command-line overrides, another file can still win.

### 4.1. Order of Application Files

Spring Boot searches for configuration files in this general order:

1. application.properties or YAML at the classpath root inside the JAR.
2. Profile-specific files inside the JAR, such as application-prod.yml.
3. application.properties or YAML outside the JAR.
4. Profile-specific files outside the JAR, such as application-prod.yml.

Files discovered later can override earlier ones. For example, if the JAR contains:

```yaml
# src/main/resources/application.yml
inventory:
  routing:
    timeout: 2s
```

and the application's working directory contains:

```yaml
# ./config/application-prod.yml
inventory:
  routing:
    timeout: 5s
```

with the prod profile active, 5s can win over 2s in the JAR.

If the same directory contains both application.properties and application.yml, Spring Boot prefers .properties. To avoid unpredictability, standardize on one format within an application.

### 4.2. Confirming Which Profile Is Actually Active

Check all sources that can activate profiles:

- spring.profiles.active in configuration files.
- Environment variable SPRING_PROFILES_ACTIVE.
- JVM system property -Dspring.profiles.active=prod.
- Command line --spring.profiles.active=prod.
- Profiles activated via SpringApplication or environment APIs.

If multiple profiles are active, a profile evaluated later can override a value from an earlier profile. For example, prod,region-a can let application-region-a.yml override a key declared in application-prod.yml.

Also check spring.profiles.include, profile groups, and multi-document YAML files. A document with spring.config.activate.on-profile is only loaded when the profile expression matches. Documents in a multi-document file are processed top to bottom; later documents can override earlier ones.

### 4.3. Checking Working Directory and Config Paths

Relative paths such as ./config/application.yml are resolved from the process working directory, not necessarily the directory containing the JAR.

These two commands have different meanings:

```bash
# Append external locations to the default locations
java -jar app.jar --spring.config.additional-location=optional:file:./config/

# Replace the default locations with the specified locations
java -jar app.jar --spring.config.location=optional:file:./config/
```

spring.config.location replaces the default locations; spring.config.additional-location adds new locations and allows them to override default configuration. If the application runs in a container, inspect the working directory, volume mounts, and file paths inside the container rather than only looking at files on your development machine.

spring.config.name, spring.config.location, and spring.config.additional-location are used very early to determine which files to load. They must be set in environment properties, system properties, or command-line arguments; they cannot simply be declared inside the very file whose lookup they control.

### 4.4. Checking Imports and Config Data Order

One file can import additional files:

```yaml
spring:
  config:
    import: optional:file:./secrets/local-overrides.yml

inventory:
  routing:
    timeout: 2s
```

Values from an imported file are placed directly beneath the document declaring the import and can override that document. If a document imports multiple locations, locations listed later have higher priority than earlier ones.

Example:

```yaml
spring:
  config:
    import:
      - optional:file:./defaults.yml
      - optional:file:./runtime-overrides.yml
```

If both files declare inventory.routing.timeout, runtime-overrides.yml can beat defaults.yml. Do not search for the key only in application.yml; follow the entire spring.config.import chain.

## 5. Checking Runtime Environment Overrides

### 5.1. Environment Variables

Spring Boot maps canonical property names to environment variable names using these rules:

1. Replace dots `.` with `_`.
2. Remove dashes `-`.
3. Convert to uppercase.

Examples:

| Property name | Environment variable |
| --- | --- |
| inventory.routing.timeout | INVENTORY_ROUTING_TIMEOUT |
| spring.main.log-startup-info | SPRING_MAIN_LOGSTARTUPINFO |
| spring.cloud.loadbalancer.cache.ttl | SPRING_CLOUD_LOADBALANCER_CACHE_TTL |

Do not replace dashes in property names with an extra underscore. For instance, SPRING_MAIN_LOG_STARTUP_INFO is not the standard mapping for spring.main.log-startup-info.

Check environment variables in the exact process/container:

```bash
# Linux/macOS
printenv INVENTORY_ROUTING_TIMEOUT

# Or list related variables
env | grep '^INVENTORY_'
```

On Kubernetes, inspect env, envFrom, ConfigMap, Secret, and Deployment/StatefulSet manifests. Environment variables generated from a ConfigMap/Secret may differ from the YAML file you are viewing in the repository.

### 5.2. JVM System Properties

`-D` arguments passed to the JVM can override file configuration:

```bash
java -Dinventory.routing.timeout=9s -jar app.jar
```

Check start scripts, Docker ENTRYPOINT, JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS, systemd configs, and IDE JVM arguments. A `-D` flag may be injected by a deployment pipeline outside the application repository.

### 5.3. Command-Line Arguments

Spring Boot by default converts arguments starting with `--` into properties:

```bash
java -jar app.jar --inventory.routing.timeout=10s
```

Command-line properties take higher precedence than file configuration sources. Check the actual command executed by the container or process manager, not just a Dockerfile or script from another environment.

### 5.4. SPRING_APPLICATION_JSON

A JSON block can supply multiple properties at once:

```bash
SPRING_APPLICATION_JSON='{"inventory":{"routing":{"timeout":"11s"}}}' java -jar app.jar
```

This JSON source has higher priority than system properties and environment variables in Spring Boot's order, but lower priority than command-line arguments. A JSON null value is treated as a missing property when the resolver looks up a value, so do not use null to clear a value in a lower-priority source.

## 6. Spring Cloud Config May Provide Another Source

If the application uses Spring Cloud Config, determine whether Config Client uses Config Data import or legacy bootstrap.

### 6.1. Config Data Import

This is the modern default approach:

```yaml
spring:
  application:
    name: inventory-service
  config:
    import: optional:configserver:https://config.example.com
```

Config Server serves property sources by application, profile, and label. With shared configuration, the response may contain sources such as:

1. application.yml
2. application-prod.yml
3. inventory-service.yml
4. inventory-service-prod.yml

Property sources returned later can override earlier ones. If spring.cloud.config.name contains multiple names, the order of names in the list also affects precedence.

Config Data import can generate multiple Config Server requests at startup: first using the default profile to discover activated profiles, then requesting additional configuration for active profiles. This is normal behavior and does not necessarily mean Config Client is loading duplicate configuration.

With Config Data, imported data is treated as additional documents right after the document declaring the import and can override values in that document. Thus, if application.yml declares both spring.config.import and inventory.routing.timeout=2s in the same document, 5s from Config Server can beat the local 2s value. Higher-priority sources in Environment, such as environment variables or command line, can still override remote values.

You can call Config Server directly to see which property sources the server returns, e.g., GET /inventory-service/prod. Compare the order of application, application-prod, inventory-service, and inventory-service-prod; sources returned later can override earlier ones.

The URL inside spring.config.import takes precedence over spring.cloud.config.uri. If the two values differ, the client may connect to the server in the import rather than the URI you are checking.

The optional: prefix means the application can still start when Config Server is unreachable. In that case, the application may fall back to local sources only and produce a different value than the remote configuration you expect. If Config Server is a mandatory source, omit optional: or enable fail-fast per Config Client guidelines so connection failures are caught at startup.

### 6.2. Legacy Bootstrap and Remote Property Overrides

Older applications may use bootstrap.yml or spring-cloud-starter-bootstrap. With config-first bootstrap, remote property sources normally do not allow local configuration to override them by default.

Properties controlling this behavior:

| Property | Meaning |
| --- | --- |
| spring.cloud.config.allow-override | Whether remote property sources allow adjusting override behavior. |
| spring.cloud.config.override-none=true | When allowed, remote properties are placed at lowest priority so local sources can override them. |
| spring.cloud.config.override-system-properties=false | Allows system properties, command line, and environment variables to override remote properties, while disallowing local config files from overriding. |

Key point: allow-override must be granted from the **remote property source**. Putting it in local application.yml does not grant override permission to the client.

These flags only take effect with config-first bootstrap. Do not use them to explain Config Data import ordering in a modern application. If the application has already moved to spring.config.import, diagnose according to Config Data and actual PropertySource ordering.

### 6.3. Config Server Overrides

Config Server can declare spring.cloud.config.server.overrides to provide shared values to every client. These values are placed at high priority in Config Client property sources. However, Spring Cloud documentation notes that a configuration system cannot force every application to use a value in every way; for example, legacy bootstrap can set overrideNone=true so server overrides behave more like default values.

If a property consistently appears with the same value across many applications, check:

- Shared application.yml in the config repository.
- Shared config files listed in spring.cloud.config.name.
- spring.cloud.config.server.overrides.
- The branch/label actually requested by the client.
- The remote property override policy if using legacy bootstrap.

## 7. Tracing Value Origins with Actuator

Spring Boot provides two especially helpful endpoints:

- env: shows PropertySources in Environment, the source containing the property, and origin if available.
- configprops: shows @ConfigurationProperties beans after binding.

To use them over HTTP, expose the endpoints and protect them with authentication/authorization. Example configuration for diagnostic environments only:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
```

Do not expose env and configprops on public networks. These endpoints can disclose configuration structure and sensitive information; sensitive values are sanitized by default, yet access must still be restricted.

### 7.1. Inspecting a Specific Property

Call the env endpoint with the canonical property name:

```bash
curl -u "$OPS_USER:$OPS_PASSWORD" \
  http://localhost:8080/actuator/env/inventory.routing.timeout
```

The response can reveal:

- The current value of the property.
- The name of the PropertySource providing the selected value.
- The list of property sources in precedence order.
- The origin of the value, such as file and line number if the source supports origin tracking.

Abbreviated example:

```json
{
  "property": {
    "source": "systemEnvironment",
    "value": "8s"
  },
  "propertySources": [
    {
      "name": "commandLineArgs"
    },
    {
      "name": "systemProperties"
    },
    {
      "name": "systemEnvironment",
      "property": {
        "origin": "System Environment Property \"INVENTORY_ROUTING_TIMEOUT\"",
        "value": "8s"
      }
    }
  ]
}
```

This is an example illustrating structure, not a fixed response across all versions. If commandLineArgs does not contain the key, systemEnvironment can be the winning source. Read the actual property.source and propertySources.

### 7.2. Inspecting Values Bound into Beans

If Environment shows 8s yet the bean still uses 2s, inspect configprops:

```bash
curl -u "$OPS_USER:$OPS_PASSWORD" \
  http://localhost:8080/actuator/configprops
```

Find the prefix of the @ConfigurationProperties class containing the property, e.g., inventory.routing. Compare the bound value with the value in env.

| Result | Investigation Direction |
| --- | --- |
| env and configprops share the same unexpected value | Find the override source in Environment. |
| env is right, configprops differs | Check binding, prefix, data type, validation, and initialization timing. |
| configprops is right, runtime behavior differs | Check another bean, caches, stateful objects, or code overriding after binding. |
| All endpoints look right yet logs are stale | Verify which instance/pod is being inspected and whether logs belong to it. |

Values in env or configprops may be sanitized as `******`. Do not enable showing all secrets just to diagnose a timeout. If viewing raw values is genuinely required, restrict the endpoint and role in a secure environment, then restore security policies afterward.

## 8. Diagnosing in Code

When Actuator cannot be used, you can read the winning value and list every source containing the key.

Example diagnostic component for development environments only:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class PropertyOriginDiagnostics {

    private final ConfigurableEnvironment environment;

    public PropertyOriginDiagnostics(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    public void inspect(String key) {
        String effectiveValue = environment.getProperty(key);
        System.out.println("Effective value for " + key + ": " + effectiveValue);

        for (PropertySource<?> source : environment.getPropertySources()) {
            Object candidate = source.getProperty(key);
            if (candidate != null) {
                System.out.println(
                        "Found in " + source.getName() + ": " + candidate);
            }
        }
    }
}
```

Environment.getProperty(key) returns the effective value. The loop shows which sources also declare the key. PropertySources are iterated in precedence order; the first source where the key is found is the one chosen by the resolver.

Use this snippet only with non-sensitive keys. Do not log passwords, tokens, private keys, connection strings, or the entire Environment in production. After diagnosing, remove or disable the debug component.

## 9. Checking Key Names and Binding

Not every discrepancy is caused by a higher-priority source. A wrong key, wrong prefix, or wrong representation also produces symptoms identical to an ignored property.

### 9.1. Use Canonical kebab-case

Declare properties in lowercase kebab-case:

```yaml
inventory:
  routing:
    read-timeout: 2s
```

In placeholders, also use canonical form:

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RoutingSettings {

    @Value("${inventory.routing.read-timeout}")
    private Duration readTimeout;

    public Duration getReadTimeout() {
        return readTimeout;
    }
}
```

With @ConfigurationProperties, Spring Boot supports relaxed binding for equivalent forms such as kebab-case, camelCase, and uppercase environment variables. However, using one canonical form makes searching, tracing, and comparing easier.

### 9.2. Verify Environment Variable Conversion

The property inventory.routing.read-timeout converts to:

```text
INVENTORY_ROUTING_READTIMEOUT
```

Do not use INVENTORY_ROUTING_READ_TIMEOUT by replacing dashes with underscores. In environment variables, dots become `_`, dashes are removed, and the name is uppercased.

### 9.3. Verify Prefix and Field Names

Example:

```java
@ConfigurationProperties(prefix = "inventory.routing")
public class RoutingProperties {

    private Duration timeout;

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

This class binds the key inventory.routing.timeout. If the file declares inventory.route.timeout or the annotation uses prefix inventory.client, the value will not populate the expected field.

Also verify:

- Is the bean registered via @ConfigurationPropertiesScan or @EnableConfigurationProperties?
- Does the prefix in the annotation match the YAML structure?
- Does the field have appropriate setter/constructor binding?
- Do @Validated, constraints, or custom converters affect it?
- Is the data type parsed properly, such as Duration, DataSize, enum, or list?

### 9.4. Lists Have Their Own Override Rule

When a list is declared in multiple sources, Spring Boot replaces the entire list with the list from the higher-priority source; it does not merge elements from both lists.

Example:

```yaml
# application.yml
inventory:
  routing:
    regions:
      - region-a
      - region-b
```

```yaml
# application-prod.yml
inventory:
  routing:
    regions:
      - region-c
```

Under the prod profile, the effective list can become only region-c, not three elements. If you want to retain common values, declare the full list in the overriding source or use a map structure suited to your purpose.

## 10. Inspecting Values After Application Startup

Another case is when the value in Environment changed, yet the running object still holds the old value.

This can happen when:

- The bean read the property once in a constructor or @PostConstruct.
- Another object copied the value into its own field.
- The bean is not in @RefreshScope and is not rebound.
- Configuration was refreshed, yet a component uses an old reference/state.
- An internal cache or connection pool does not support dynamic updates.

With Spring Cloud Context, @RefreshScope allows beans to be recreated when refresh scope is refreshed:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@RefreshScope
@Component
@ConfigurationProperties(prefix = "inventory.routing")
public class RoutingProperties {

    private Duration timeout = Duration.ofSeconds(2);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

After a refresh, the scope recreates the target bean when accessed. Not every bean in the application is automatically refreshed. For @ConfigurationProperties, Spring Cloud provides a rebinding mechanism; inspect the specific bean and property instead of assuming every object updated.

If env has the new value while the bean has not changed, verify:

1. Is the bean in refresh scope or an appropriate rebinding mechanism?
2. Was the refresh event actually delivered to this instance?
3. Is the bean reading the same key or an alias key?
4. Is a component retaining a copy of the old value?
5. Does the downstream library support post-initialization config updates?

If the component does not support dynamic updates, use rolling restart/redeploy instead of repeatedly triggering refresh.

## 11. Ordered Diagnostic Workflow

When a property differs from the expected file, follow these steps:

1. **Identify the instance:** determine pod/container/host, process ID, active profiles, and startup time.
2. **Choose the canonical key:** normalize the property name to lowercase kebab-case.
3. **Read the effective value:** use Environment.getProperty or Actuator env.
4. **Identify the winning source:** check property.source, PropertySource name, and origin.
5. **List other sources:** search for the same key across classpath, external directories, profile files, imports, environment, system properties, JSON, and command line.
6. **Check profiles:** verify spring.profiles.active, profile includes/groups, and profile order.
7. **Check Config Data:** trace spring.config.import, spring.config.location, spring.config.additional-location, and working directory.
8. **If using Config Server:** check application name, profile, label, response property sources, and bootstrap mode.
9. **Compare with beans:** use configprops or controlled logging to compare bound values against Environment.
10. **Fix the right source:** remove unintended overrides or update the value in the authoritative source.
11. **Restart/refresh:** act according to the bean's update capability.
12. **Verify again:** re-read property sources and runtime behavior on every instance.

## 12. Enabling Logs to See Which Files Are Loaded

If it is unclear which files Spring Boot read, increase logging for the Config Data loader:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

Or pass via command line:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Logs reveal which locations were checked, which files were loaded, which profiles were evaluated, and which imports were processed. logging.* properties are read early, so set them via environment, system properties, or command line if diagnostics are needed from the start.

Once the override source is found, return log levels to normal to avoid excessive logging in production.

## 13. Complete Example

Suppose the application expects inventory.routing.timeout=2s from the file inside the JAR.

File in the JAR:

```yaml
# src/main/resources/application.yml
inventory:
  routing:
    timeout: 2s
```

The deployment manifest contains:

```yaml
env:
  - name: INVENTORY_ROUTING_TIMEOUT
    value: 8s
```

The application runs with the prod profile. When calling:

```bash
curl http://localhost:8080/actuator/env/inventory.routing.timeout
```

if property.source is systemEnvironment and origin is INVENTORY_ROUTING_TIMEOUT, the cause is clear: the deployment manifest is overriding the file in the JAR.

To fix:

1. Update or remove the environment variable in the manifest if the override is no longer needed.
2. Redeploy the workload so the process receives the new environment.
3. Verify env returns 2s or the newly chosen value.
4. Check configprops for the routing bean.
5. Send an actual request and confirm runtime timeout changed.

If the environment variable is an intentional override, update environment documentation and the release manifest so operators do not mistake the value in the JAR for the effective value.

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| File in JAR is right yet runtime value differs | External file or higher-priority source overrides it | Check Actuator env and origin. |
| Differs only in production | Separate profile, ConfigMap, Secret, or deployment env | Verify active profiles and the exact workload's manifest. |
| Works locally, wrong in container | Different working directory, mounted file, or environment inside container | Check paths and environment variables inside the container. |
| Value is always identical across multiple services | Shared Config Server source or server overrides | Check application.yml, spring.cloud.config.name, and server.overrides. |
| Changed spring.cloud.config.uri yet client still hits old server | URL in spring.config.import takes precedence over URI | Fix import location or remove duplicate configuration. |
| Local YAML does not override remote Config Server | Application uses legacy bootstrap and remote source does not allow overrides | Check allow-override from remote and override flags for the right mode. |
| Environment value is right yet bean is wrong | Binding/prefix/refresh issue or object holding stale state | Check configprops, bean registration, and lifecycle. |
| Environment variable is ignored | Incorrectly converted variable name | Replace dots with `_`, drop dashes, uppercase. |
| List lost elements | List from higher-priority source replaces the entire list | Declare the complete list in the overriding source. |
| Actuator env does not display value | Endpoint not exposed or value sanitized | Check exposure, authorization, and sanitization policy. |
| File was edited yet application did not change | External file not imported or app not restarted/refreshed | Check config location, import, and lifecycle. |
| Some pods have different values | Pods started with different env/config revisions or uneven refreshes | Compare revision, manifest, and env on each pod. |

## 15. Practice and Self-Check Questions

1. application.yml contains timeout=2s, while the command line passes --timeout=5s. Which value wins and why?
2. Why can application-prod.yml override application.yml?
3. What is the difference between spring.config.location and spring.config.additional-location?
4. In what way can a file imported via spring.config.import override the document declaring the import?
5. How do you properly convert spring.main.log-startup-info into an environment variable name?
6. Which two distinct questions do Actuator env and configprops answer?
7. Why does setting spring.cloud.config.allow-override=true in a local file have no effect with legacy bootstrap?
8. In which mode does spring.cloud.config.override-none take effect?
9. Why might Environment hold the new value while a bean still holds the old value?
10. When multiple profiles are active, how do you determine which profile wins?
11. Design check steps to determine why one pod uses a different timeout from the remaining pods.

## 16. Official References

- [Spring Boot 4.1 — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot 4.1 — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator — Environment Endpoint API](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Context — Application Context Services and Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

When a property differs from the expected file, find the winning source in Environment first. Only then investigate profiles, imports, Config Server, and binding. This approach pinpoints the true origin of the value and avoids editing the wrong file when it is not the decisive source.
