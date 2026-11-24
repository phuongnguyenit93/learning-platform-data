# Reading the configprops Endpoint to Inspect @ConfigurationProperties Beans

## 1. From "what the config file says" to "what value the bean holds"

Suppose in YAML we set the connection timeout to `1500ms`, yet the application waits for a shorter duration than expected. Re-reading that file is not enough to draw a conclusion: a startup argument may have overridden the value, a different profile may be active, or the configuration class may not have been registered as a bean.

**The `configprops` endpoint** provides a report on `@ConfigurationProperties` beans in the running application. It helps verify three consecutive questions:

1. Does the target configuration bean appear, and which prefix is it bound to?
2. What values do the bean's reported properties currently hold?
3. Where did the input value used during binding come from, if source information was recorded?

In this lesson, **configuration binding** is the process of taking properties from configuration sources, converting types, and populating a Java object. The **prefix** identifies the configuration namespace, such as `app.catalog`. The **origin** describes where an input was taken from, such as a YAML file and its line/column position.

```text
application.yml / profiles / environment variables / startup arguments
                  ↓ Environment and precedence order
                  ↓ Binder: look up properties, convert types, create/bind bean
           @ConfigurationProperties bean
                  ↓ GET /actuator/configprops
       report grouped by context, bean, properties, and inputs
```

This is an observation tool for diagnostics. A GET operation does not edit YAML files, does not change values, and does not cause beans to be rebound.

### Putting configprops in its proper place in the toolkit

| Tool | Appropriate question |
| --- | --- |
| `configprops` | Which `@ConfigurationProperties` beans are reported, with what values and inputs? |
| `env` | Which properties exist in `Environment`, in which sources, and which source takes precedence? |
| `beans` | Which beans exist in the Spring context? |
| `conditions` | Which auto-configuration conditions matched or did not match? |
| Startup error logs | Why did type conversion, bean creation, or configuration validation fail? |

`configprops` is neither a copy of all configuration files nor a list of every field annotated with `@Value`. The report only shows what the endpoint collects and serializes from configuration properties beans.

## 2. Reading the response structure before drawing conclusions

Two important URLs in Spring Boot 3.3:

```http
GET /actuator/configprops
GET /actuator/configprops/app.catalog
```

The first URL returns the full report. The second filters by the bean's registered prefix while keeping the per-context report structure. You can use a broader prefix, such as `/actuator/configprops/app`. [Spring Boot 3.3 configprops REST contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

| Component | Meaning when reading |
| --- | --- |
| `contexts` | Reported application contexts, keyed by context identifier |
| `contexts.*.parentId` | Parent context identifier, if any |
| `contexts.*.beans` | Configuration beans in each context, keyed by bean name |
| `prefix` | Binding prefix of the bean |
| `properties` | Representation of the reported properties on the bean object |
| `inputs` | Input values and source information recorded during binding |

Do not hardcode `contexts.application` in every tool: context identifiers can vary by application name, configuration, or context hierarchy. Also do not treat the bean name as a configuration property name.

For a class registered with `@EnableConfigurationProperties` in the example below, the conventional bean name is:

```text
app.catalog-example.configprops.CatalogClientProperties
```

This is **a single JSON key containing both dots and a hyphen**, not a nested JSON path. When using a JSON library, access it as a map key or search for the entry with the matching `prefix`; avoid writing dot-separated path queries that split the bean name into multiple segments.

### properties and inputs explain two different sides

If configuration contains `connect-timeout: 1500ms` and the bean uses type `Duration`, you may see:

```json
{
  "properties": {
    "connectTimeout": "PT1.5S"
  },
  "inputs": {
    "connectTimeout": {
      "value": "1500ms"
    }
  }
}
```

This is an excerpt focusing on values; the actual report includes additional fields and source details when available.

- `properties.connectTimeout` shows the value after type conversion, serialized to JSON. `PT1.5S` is a duration of 1.5 seconds in ISO-8601 notation.
- `inputs.connectTimeout.value` is the input value recorded for that property.
- `inputs.connectTimeout.origin` helps locate the input's source; line/column numbers belong to the specific runtime environment.

The difference between `1500ms` and `PT1.5S` does not indicate a misconfiguration. You must compare **meaning and data type**, not just raw strings.

If a property takes a default from Java code or `@DefaultValue`, `properties` may hold a value while the corresponding entry in `inputs` is `{}`. Do not conclude that an empty `inputs` object means the bean has no value.

## 3. Hands-on project: inspecting a catalog client configuration

This standalone example uses Java 21, Spring Boot 3.3.0, and Gradle 8.5, aligned with the Boot 3.3.x baseline of this lesson. No database or remote service is needed: the URL in configuration is sample data only and is never called.

The goal is to observe:

- `baseUrl` converted to `URI`;
- `connectTimeout` converted to `Duration`;
- `maxAttempts` receiving the default `3`;
- input values and origin locations differing from the bean's representation;
- masking affecting only the report without altering the bean.

### 3.1. Build files

`settings.gradle`:

```groovy
rootProject.name = 'configprops-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

These build files are intended for a fresh lab directory. In a repository with shared Gradle conventions, use the module's existing conventions rather than replacing the build with this example.

### 3.2. Configuration bean and application

`src/main/java/example/configprops/CatalogClientProperties.java`:

```java
package example.configprops;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        @DefaultValue("3") int maxAttempts) {
}
```

`src/main/java/example/configprops/ConfigpropsDemoApplication.java`:

```java
package example.configprops;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CatalogClientProperties.class)
public class ConfigpropsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigpropsDemoApplication.class, args);
    }
}
```

`@ConfigurationProperties` describes how to bind; `@EnableConfigurationProperties` registers that type using Boot's configuration mechanism. Placing the annotation on a class alone while leaving it outside any registration mechanism will not create a bean automatically.

You can use `@ConfigurationPropertiesScan` instead of explicit registration. For a constructor-bound record like this example, do not add `@Component` just to force it to become an ordinary bean.

YAML keys use `base-url`, `connect-timeout`, `max-attempts`; record components use `baseUrl`, `connectTimeout`, `maxAttempts`. These corresponding names are supported by relaxed binding. [Typesafe Configuration Properties in Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).

### 3.3. Baseline configuration: report with masked values

`src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: configprops-demo

app:
  catalog:
    base-url: https://catalog.example.test
    connect-timeout: 1500ms

management:
  endpoint:
    configprops:
      enabled: true
      show-values: never
  endpoints:
    web:
      exposure:
        include: health,configprops
```

`max-attempts` is intentionally omitted from YAML to observe the default from `@DefaultValue`.

There are three independent concerns:

1. `enabled` determines whether the endpoint is enabled.
2. `web.exposure.include` includes the endpoint in the set exposed over HTTP.
3. `show-values` determines the policy for displaying values in responses.

The example does not add Spring Security and listens only on loopback. In an application with a security filter chain, exposure does not grant access permission by itself; the application's authentication and authorization mechanisms must be satisfied.

### 3.4. Local diagnostic mode

`src/main/resources/application-diagnostic.yml`:

```yaml
management:
  endpoint:
    configprops:
      show-values: always
```

This profile is for practicing with dummy data on loopback. When enabled, the display policy applies to the entire `configprops` report accessible to the caller, not only the `app.catalog` bean.

The name `diagnostic` carries no special privilege: it is simply a profile name we chose. Do not treat a profile name as a security mechanism.

## 4. Performing a read and explaining the evidence

### 4.1. Starting in baseline mode

In the project directory, with JDK 21 and Gradle 8.5 installed, generate the wrapper:

```shell
gradle wrapper --gradle-version 8.5
```

Then, in PowerShell:

```powershell
.\gradlew.bat bootRun
```

On Linux/macOS use `./gradlew bootRun`. Do not run the classes individually with `javac` without the classpath; the project requires Spring dependencies and YAML resources.

In a second terminal:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/configprops/app.catalog
```

On Windows use `curl.exe` if `curl` is an alias. You can add `-i` to inspect the status and headers. A successful response has HTTP 200; do not hardcode key ordering, context IDs, Content-Length, or line wrapping.

Find the bean whose `prefix` equals `app.catalog`. Its `properties` section in baseline mode looks like:

```json
{
  "baseUrl": "******",
  "connectTimeout": "******",
  "maxAttempts": "******"
}
```

Even values that do not look sensitive are masked. `******` is the result of the display policy, not a default password, raw data, or a sign of failed binding. Do not edit YAML to `******` to "match" the response.

### 4.2. Reading actual values in the lab

Stop the running process, then restart:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=diagnostic"
```

Read the URL above again. If `jq` is available, the following command iterates across all contexts and selects the bean by prefix:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/configprops/app.catalog | jq '.contexts[] | .beans | to_entries[] | select(.value.prefix == "app.catalog") | .value.properties'
```

Result in structure and values:

```json
{
  "baseUrl": "https://catalog.example.test",
  "connectTimeout": "PT1.5S",
  "maxAttempts": 3
}
```

This JSON is formatted for readability; field order is not guaranteed. `jq` is an optional tool, not an application dependency.

Read the input details:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/configprops/app.catalog | jq '.contexts[] | .beans | to_entries[] | select(.value.prefix == "app.catalog") | .value.inputs'
```

Observe and compare:

| Property in report | properties | inputs | Interpretation |
| --- | --- | --- | --- |
| `baseUrl` | URI string representation | Has URL value and YAML origin | Bean received the configured input |
| `connectTimeout` | `PT1.5S` | Value `1500ms` and YAML origin | Duration type conversion occurred |
| `maxAttempts` | Number `3` | `{}` in this example | Default from annotation, not a missed YAML line |

The YAML origin usually points to the `application.yml` resource along with line/column numbers. Do not write tests that rigidly depend on line numbers, because adding comments or reordering declarations changes positions.

### 4.3. Proving a value was overridden

Stop the process and restart with a higher-precedence input:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=diagnostic --app.catalog.connect-timeout=750ms"
```

Read the same bean again. Expected result:

```json
{
  "baseUrl": "https://catalog.example.test",
  "connectTimeout": "PT0.75S",
  "maxAttempts": 3
}
```

`inputs.connectTimeout.value` is now `750ms`; the origin information identifies the input as coming from startup arguments. YAML still says `1500ms`, but it is not the winning source for this property in that run.

Configuration sources have precedence order. With the sample application using default behavior, command-line arguments can override file configuration. Do not generalize a simplified order to every test context, Config Data setup, or custom integration. [Source order and command-line arguments](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.command-line-args).

**Complete diagnostic evidence** consists of three matching points: the right bean/prefix → the typed value in `properties` → the input and origin in `inputs`. Seeing only a YAML line or a single value in `Environment` does not complete this verification chain.

## 5. Filtering by prefix properly

```http
GET /actuator/configprops/app.catalog
GET /actuator/configprops/app
```

Both can select the sample bean because its registered prefix starts with the requested string. The filter uses the **bean's** prefix, not a search over response contents.

The following commonly misunderstood requests do not mean what people assume:

- `/actuator/configprops/catalog`: does not find every prefix containing the word `catalog` in the middle.
- `/actuator/configprops/app.catalog.connect-timeout`: does not select an individual field inside the `app.catalog` bean.
- Passing a class name or bean name as a URL segment: not a bean-identifier filter.
- Appending `?prefix=app.catalog`: does not replace the selector path syntax described above.

In the Boot 3.3.0 example, an HTTP request with a prefix matching no bean returns **404**. This differs from calling the general report successfully and not seeing the desired bean in its contents. When diagnosing a 404 on a prefixed URL, test the general `/actuator/configprops` URL to distinguish an inaccessible endpoint from an empty filter match.

In Boot 3.3.0, filtering uses `bean.getAnnotation().prefix().startsWith(prefix)`. Thus a broad stem can also pull in other prefixes starting with that same string; it does not check segment boundaries and is not an authorization boundary. [ConfigurationPropertiesReportEndpoint source code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/context/properties/ConfigurationPropertiesReportEndpoint.java).

If access permissions allow the full report, a user picking a narrow URL does not prevent them from requesting a broader URL. Choosing a prefix reduces the amount of data to read; authorization must be designed at the access layer.

## 6. Understanding the value-masking policy

In Spring Boot 3.3, `configprops` masks values by default. Use `management.endpoint.configprops.show-values` to select the policy:

| Value | Display policy |
| --- | --- |
| `never` | Mask values for all callers |
| `always` | Allow showing values to everyone who can access the endpoint |
| `when-authorized` | Show only to callers meeting the authorization criteria for viewing values |

Custom `SanitizingFunction` beans can still mask data wherever they apply. Therefore, `always` does not guarantee every field is shown verbatim. [Actuator display and sanitization policy](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#sanitizing).

In an application with authentication, a policy configuration might look like:

```yaml
management:
  endpoint:
    configprops:
      show-values: when-authorized
      roles: CONFIG_READER
```

This YAML snippet only configures the display policy. It does not create accounts, configure login, or protect URLs on its own. For HTTP, viewing values requires an authenticated identity and a role matching the configuration; when no roles list is specified, authenticated users qualify by default under this policy.

Distinguish clearly:

```text
Is access to /actuator/configprops permitted?
             ↓
If accessible, are real values allowed to be shown?
             ↓
Is any custom sanitizer still applying?
```

`401/403` and `200` with `******` values belong to different scenarios. Do not switch to `always` to fix an authentication error.

Value-viewing permissions for HTTP and JMX should not be assumed identical either. When designing for multiple management channels, inspect each channel's policy rather than treating HTTP role settings as a universal protection layer.

## 7. Workflow for diagnosing a configuration bean

### Step 1: Verify the right application and endpoint path

Check the process, port, Actuator base path, and actual context path. The lesson example uses `127.0.0.1:8080/actuator`; other applications may use a separate management port or different paths.

If the general URL returns `404`, check enablement, exposure, and exclusions before modifying configuration classes. For a prefixed URL, 404 can also occur when no bean matches the filter. If it returns `401/403`, resolve according to the authentication/authorization policy.

### Step 2: Locate the right bean via prefix

Start with a sufficiently narrow prefix, then inspect the matching contexts and beans. Record the bean name when multiple objects share a prefix; do not stop at the first match and assume it is the business object actually in use.

If the bean is missing, check:

- Does the class have `@ConfigurationProperties` with the right prefix?
- Is it registered via `@EnableConfigurationProperties`, scanning, or an appropriate `@Bean`?
- Is a profile or bean-creation condition excluding it?
- Are you querying the wrong process, deployment version, or context?

An object instantiated directly by application code via `new` does not automatically become a Spring configuration bean.

### Step 3: Compare properties with Java types and defaults

Read property names as represented on the bean, typically camelCase. Interpret `Duration`, enums, collections, or nested types according to their semantics.

If a property is missing, do not immediately conclude it does not exist in Java: `null` fields, reportability/serialization behavior, or special bean structure can affect the response. In Boot 3.3.0, the endpoint filters reportable properties, avoids circular references, and may return error info when a bean cannot be serialized. Do not treat the report as a reflection snapshot of the entire object graph.

### Step 4: Trace inputs back to sources

For unexpected values, check the corresponding `inputs`. If an origin is present, inspect the exact file/profile, startup argument, or overriding source listed.

`inputs` does not list all overridden candidate values. When you need to analyze existing sources and precedence relationships, use `env` together with startup logs/configurations as complementary tools, within granted permissions.

If `inputs` is `{}`, review defaults in the class/constructor/annotation and source-tracking capability. Do not automatically interpret it as "the property was never configured" across every application.

### Step 5: Verify how the bean is used

A bean having the right values only proves the reported configuration state. An HTTP client may have copied the timeout when it was constructed; changing configuration later does not prove that client received the new value.

Check which bean is injected, whether `@Qualifier` or a manually constructed object is used, and when the configuration is applied. `configprops` does not prove connectivity succeeds to the URL in configuration.

### Step 6: Fix the authoritative source and re-observe

Modify the source actually governing the value, restart, or use an update mechanism supported by the application. Read the same bean again and verify the same set of evidence.

A change in `Environment` does not guarantee every `@ConfigurationProperties` bean updates automatically. The sample application uses startup binding and has no dynamic configuration refresh feature.

## 8. Testing the report: values, sources, and masking

The following tests use MockMvc to read the endpoint inside the Spring context; no real HTTP socket is opened. They assert on the JSON structure by prefix instead of hardcoding context IDs or bean names.

### 8.1. Helper for reading a bean from the report

`src/test/java/example/configprops/ConfigpropsJson.java`:

```java
package example.configprops;

import com.fasterxml.jackson.databind.JsonNode;

final class ConfigpropsJson {

    private ConfigpropsJson() {
    }

    static JsonNode findBean(JsonNode report, String prefix) {
        for (JsonNode context : report.path("contexts")) {
            for (JsonNode bean : context.path("beans")) {
                if (prefix.equals(bean.path("prefix").asText())) {
                    return bean;
                }
            }
        }
        throw new AssertionError("Missing configprops prefix: " + prefix);
    }

}
```

`findBean` suits a sample with only one bean for this prefix. If a design has multiple beans sharing a prefix, return a list or additionally filter by verified context/bean name.

### 8.2. Testing masking mode and the actual bean

`src/test/java/example/configprops/ConfigpropsMaskedTest.java`:

```java
package example.configprops;

import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConfigpropsMaskedTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @Autowired
    private CatalogClientProperties properties;

    @Test
    void masksBothReportedAndInputValues() throws Exception {
        String body = mvc.perform(get("/actuator/configprops/app.catalog"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        var bean = ConfigpropsJson.findBean(
                mapper.readTree(body), "app.catalog");

        assertEquals("******",
                bean.path("properties").path("connectTimeout").asText());
        assertEquals("******",
                bean.path("inputs").path("connectTimeout")
                        .path("value").asText());
    }

    @Test
    void maskingDoesNotModifyTheBoundBean() {
        assertEquals("https://catalog.example.test",
                properties.baseUrl().toString());
        assertEquals(Duration.ofMillis(1500),
                properties.connectTimeout());
        assertEquals(3, properties.maxAttempts());
    }
}
```

The second test clearly separates display from actual data: the bean values remain typed and intact even when the response is masked.

### 8.3. Testing type conversion, override origin, and prefix filtering

`src/test/java/example/configprops/ConfigpropsVisibleTest.java`:

```java
package example.configprops;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoint.configprops.show-values=always",
        "app.catalog.connect-timeout=750ms"
})
@AutoConfigureMockMvc
class ConfigpropsVisibleTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @Test
    void reportsConvertedValueRecordedInputAndCodeDefault() throws Exception {
        String body = mvc.perform(get("/actuator/configprops/app.catalog"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        var bean = ConfigpropsJson.findBean(
                mapper.readTree(body), "app.catalog");
        var values = bean.path("properties");
        var inputs = bean.path("inputs");

        assertEquals("https://catalog.example.test",
                values.path("baseUrl").asText());
        assertEquals("PT0.75S",
                values.path("connectTimeout").asText());
        assertEquals(3, values.path("maxAttempts").asInt());
        assertEquals("750ms",
                inputs.path("connectTimeout").path("value").asText());
        assertTrue(inputs.path("connectTimeout").path("origin")
                .asText().contains("Inlined Test Properties"));
        assertTrue(inputs.path("maxAttempts").isObject());
        assertEquals(0, inputs.path("maxAttempts").size());
    }

    @Test
    void selectsByPrefixStemRatherThanSubstringOrFieldName()
            throws Exception {
        String broadBody = mvc.perform(get("/actuator/configprops/app"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        ConfigpropsJson.findBean(mapper.readTree(broadBody), "app.catalog");

        for (String prefix : new String[]{
                "catalog", "app.catalog.connect-timeout"}) {
            mvc.perform(get("/actuator/configprops/" + prefix))
                    .andExpect(status().isNotFound());
        }
    }
}
```

`@SpringBootTest(properties=...)` creates overrides in the test configuration source, not command-line arguments. Therefore the checked origin is `Inlined Test Properties`, whereas the startup experiment earlier showed the command-line argument source. Both scenarios illustrate that a higher-precedence input overrides YAML.

Run in PowerShell:

```powershell
.\gradlew.bat test
```

The sample suite has four tests. Gradle's report is located at `build/reports/tests/test/index.html`; logs and execution times vary by machine. The tests do not print fixed JSON to stdout.

Do not treat returning HTTP 200 as sufficient testing: assertions verify values, serialization types, origins, defaults, and the set of selected beans.

## 9. Common misreadings

| Symptom | Interpretation to verify |
| --- | --- |
| All values are `******` | Value-masking policy may be functioning normally |
| `properties` has `3`, `inputs` is `{}` | In the sample, the value comes from `@DefaultValue` |
| YAML has `1500ms`, bean reports `PT0.75S` | Check overriding source in `inputs`, rather than just editing YAML |
| Class name not found in response | Search by prefix and inspect all contexts first; verify bean registration |
| `@Value` has a value but no corresponding bean appears | `configprops` is not a report of all `@Value` fields |
| Longer filter prefix returns no results | May have used a field name instead of the bean's prefix |
| URL returns 200 but bean is absent | Success status only proves the read operation was handled |
| Application fails to start due to invalid config data | Read binding/validation errors in logs; endpoint is not ready for diagnostics |
| Bean is right but client still uses another timeout | Check the injected object and when the client copies configuration |
| Report is missing fields or has serialization error | Check data types, reportability, and bean structure |

A type conversion error such as `connect-timeout=abc` can cause bean creation to fail. If the application fails to start, you cannot expect `configprops` on that very process to remain available to explain the failure.

Conversely, a misspelled key may be ignored depending on binding policy. For instance, writing `max-attemps` instead of `max-attempts` can leave the bean using the default `3`. In that case, reading both `properties` and `inputs` helps catch false assumptions; the report is not a tool for detecting every stray key in every file.

## 10. Practice and completion criteria

1. Run without the diagnostic profile; prove the endpoint returns a masked report while the bean still receives a 1.5-second timeout.
2. Enable the `diagnostic` profile; find the bean by prefix and reconcile `1500ms` with `PT1.5S`.
3. Add a `750ms` command-line override; verify `properties`, `inputs.value`, and origin change as expected.
4. Remove the override and add `max-attempts: 5` to YAML; predict how `inputs.maxAttempts` changes before reading again.
5. Try prefixes `app`, `catalog`, and `app.catalog.connect-timeout`; explain the set of beans each request selects.
6. Trigger a type conversion error in the lab environment, observe startup logs, then restore a valid value; distinguish this error from masked data.
7. When finished, disable the value-display profile or stop the lab application. Do not save diagnostic responses containing private details into source code, public docs, or shared logs.

You complete this lesson when you can state a verifiable conclusion: **which bean is bound to which prefix, what values it is reporting, where inputs were recorded from, and how the display policy affected the visible data**. Only then conclude whether to fix a configuration source or inspect how the application uses the bean.
