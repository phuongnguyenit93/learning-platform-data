# Distinguishing Declared Configuration from Actual Bound Values

In a Spring Boot application, the line `timeout: 1s` in YAML only indicates one place where configuration was declared. It is not sufficient to conclude what value the Java object holds, and even less sufficient to conclude what timeout the library applies to each request.

To diagnose accurately, trace the path of a property: **declaration location → value selected in the configuration environment → value bound into the Java object → how components use that object**. In this lesson, "binding" is the process by which Spring Boot takes configuration properties and converts them into object data, typically through `@ConfigurationProperties`.

This lesson focuses on using Actuator to distinguish these layers of evidence in Spring Boot 3.3.x. The standalone runnable example uses Java 21 and Spring Boot 3.3.13.

## 1. Four questions to separate

Suppose `application.yml` contains:

```yaml
demo:
  client:
    timeout: 1s
```

At deployment, however, the process is started with:

```text
--demo.client.timeout=5s
```

A configuration class declares a field of type `Duration`. At this point, all of the following statements can be true simultaneously:

| Layer to observe | Question | Result in this scenario |
| --- | --- | --- |
| Source declaration | What was written in the YAML file? | `1s` |
| `Environment` configuration | For that key, what value is the application resolving? | String `5s`, overridden by command-line argument |
| Bound object | What does the `Duration` field hold? | A `Duration` of 5 seconds, which can be represented as `PT5S` |
| Executing component | Is the HTTP client actually using this value? | Must check where the client is built and actual behavior |

The difference between `1s` and `5s` relates to **source and precedence**. The difference between `5s` and `PT5S` relates to **data type and representation**. A client still using an old timeout even though the configuration object is right is an issue of **applying configuration at the point of use**.

Do not lump these three cases into a generic conclusion that "Spring is ignoring configuration".

## 2. Why just opening YAML is not enough

A key can be declared in multiple places: packaged configuration inside the JAR, external files, profile-specific configuration, environment variables, JVM system properties, and command-line arguments.

In a typical run of this example, when the same key appears in all three of the following sources, precedence from highest to lowest is:

```text
Command-line arguments > environment variables > packaged application.yml
```

This is the slice of precedence order needed for the experiment, not Spring Boot's complete list of sources. Test sources or custom mechanisms have their own rules.

A value written in `application-prod.yml` does not take effect just because the file exists: the corresponding profile must be active and the file must be loaded into the right process. Editing the YAML copy in the source tree does not prove the running JAR contains that edit.

For a scalar property like `demo.client.timeout`, Spring selects the input by precedence and converts its type during binding. If the highest-precedence input is a malformed string, do not expect Spring to skip it and fall back to a valid value from a lower-precedence source.

Reference on sources, precedence, and binding: [Externalized Configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

## 3. `env` and `configprops` answer two different questions

### 3.1. `env`: configuration sources and resolved values

Two useful paths:

```text
GET /actuator/env
GET /actuator/env/demo.client.timeout
```

Querying a single key keeps focus on the information needed for diagnostics. For a single-property response:

- `property.value` indicates the resolved value.
- `property.source` indicates the selected source.
- `propertySources` lists sources in precedence order; a source may not contain the queried key.
- `origin`, when provided, helps trace back to the file and declaration location.

A lower-precedence value can still appear in the source list. Seeing `1s` in a YAML source does not mean it is beating the `5s` argument.

`env` does not read the `timeout` field from a Java object. Nor does it prove that any arbitrary property has been used by a bean. Inputs in `Environment` may be strings or types provided by the source; do not treat the entire response as typed configuration objects.

Official structure: [Environment endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

### 3.2. `configprops`: `@ConfigurationProperties` objects

Two corresponding paths:

```text
GET /actuator/configprops
GET /actuator/configprops/demo.client
```

In the response, locate under `contexts → <context-id> → beans → <bean-name>` the object with `prefix = demo.client`. Do not assume context IDs or bean names always match a JSON capture from another application.

Fields to cross-check:

| Field | Meaning during diagnostics |
| --- | --- |
| `prefix` | Configuration prefix of the object |
| `properties` | Values of properties reported on the bean |
| `inputs` | Input values and origins recorded during binding, if available |

For instance, `properties.timeout` may represent a `Duration` value, while `inputs.timeout.value` still shows input `5s`. For a code default, the bean may hold a value with no corresponding external input in `inputs`.

`configprops` is not a list of every variable in the application. A field receiving only `@Value`, a property read solely via `Environment`, or internal library settings do not automatically become `@ConfigurationProperties` beans to appear here. Nor is the response a complete log of all historical configuration changes.

Official structure: [Configuration Properties endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

## 4. Standalone runnable experiment

The experiment has two properties:

- `timeout`: has YAML value `1s`, can be overridden; Java type is `Duration`.
- `maxAttempts`: defaults to `3` on the constructor parameter; YAML declares no corresponding key.

This lets you observe both **an overridden value** and **a value existing on the bean without an external key**.

### 4.1. Project structure

Create a separate directory with this structure:

```text
actuator-binding-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── learning/
        │       └── actuator/
        │           └── DemoApplication.java
        └── resources/
            └── application.yml
```

Use JDK 21 and Maven 3.6.3 or later. The first packaging command needs access to Maven repositories to download dependencies.

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>learning</groupId>
    <artifactId>actuator-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The example omits Spring Security to focus on configuration evidence. The server listens only on loopback in the configuration below.

### 4.3. `src/main/java/learning/actuator/DemoApplication.java`

```java
package learning.actuator;

import java.time.Duration;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(DemoApplication.DemoClientProperties.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printConfiguration(
            Environment environment,
            DemoClientProperties properties) {
        return args -> {
            System.out.println("DEMO env.timeout="
                    + environment.getProperty("demo.client.timeout"));
            System.out.println("DEMO bound.timeout=" + properties.timeout());
            System.out.println("DEMO bound.timeoutMillis="
                    + properties.timeout().toMillis());
            System.out.println("DEMO env.max-attempts="
                    + environment.getProperty("demo.client.max-attempts"));
            System.out.println("DEMO bound.maxAttempts="
                    + properties.maxAttempts());
        };
    }

    @ConfigurationProperties(prefix = "demo.client")
    public record DemoClientProperties(
            @DefaultValue("2s") Duration timeout,
            @DefaultValue("3") int maxAttempts) {
    }
}
```

`@EnableConfigurationProperties` registers the record as a configuration bean. For this single-constructor record, Spring Boot uses constructor binding; there is no need for `@Component`, setters, or `@ConstructorBinding`.

`@DefaultValue` supplies a value when the property to bind is missing. The `2s` default belongs to configuration object creation, not adding the `demo.client.timeout` key into `Environment`. Hence an `Environment` read does not automatically see this default.

`ApplicationRunner` reads both `Environment` and the bean directly to produce easily inspectable evidence. This code prints non-sensitive demo values; do not apply printing full configuration to logs in real systems.

### 4.4. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 18080

spring:
  application:
    name: actuator-binding-demo

demo:
  client:
    timeout: 1s

management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
  endpoint:
    env:
      show-values: always
    configprops:
      show-values: always
```

`exposure.include` makes the endpoints accessible over HTTP; `show-values` controls whether values are shown in responses. The two settings serve different purposes.

Here `always` is used on a personal machine to observe demo data while restricting the server to `127.0.0.1`. On real systems, access must be protected and an appropriate display policy selected. If a custom `SanitizingFunction` exists, values can still be masked.

### 4.5. Compile and run for the first time

In the directory containing `pom.xml`:

```shell
mvn clean package
java -jar target/actuator-binding-demo-1.0.0.jar
```

Ensure no environment variables, JVM properties, or external configuration files override the `demo.client` group. If port `18080` is already in use, pick another port with `--server.port=<port>` and adjust URLs when calling endpoints.

In addition to Spring Boot startup logs, the program prints exactly five lines starting with `DEMO`:

```text
DEMO env.timeout=1s
DEMO bound.timeout=PT1S
DEMO bound.timeoutMillis=1000
DEMO env.max-attempts=null
DEMO bound.maxAttempts=3
```

Meaning:

1. YAML provides `1s`, so reading the environment returns that string.
2. The bean receives a one-second `Duration`; `Duration.toString()` renders it as `PT1S`.
3. `toMillis()` confirms the duration meaning is `1000` milliseconds.
4. The `demo.client.max-attempts` key is absent from the experiment's sources, so reading the environment returns `null`.
5. The record still receives integer `3` from `@DefaultValue`.

The `null` on the fourth line does not prove the bean lacks configuration. It merely indicates that looking up that key in the environment found no value.

## 5. Using Actuator to cross-check against the bean

In a second terminal window:

```shell
curl "http://127.0.0.1:18080/actuator/env/demo.client.timeout"
curl "http://127.0.0.1:18080/actuator/configprops/demo.client"
```

In Windows PowerShell, use `curl.exe` instead of `curl` if `curl` is an alias for a PowerShell cmdlet.

For the default run:

- `env` reports the selected value as `1s`; inspect the origin to see it comes from YAML configuration.
- `configprops` has a bean with `prefix = demo.client`; properties on the bean reflect a one-second timeout and three max attempts.
- `inputs.timeout` helps trace back the input used. For the `maxAttempts` default, do not expect a YAML input containing `3`.

Do not verify JSON by doing a literal string match against logs. One side is the raw source string, while the other is a type-converted value serialized by the endpoint. Duration formatting, bean names, source names, contexts, and line positions depend on the actual response. Match **the right property, the right type, and the same value semantics**.

If the endpoint cannot return clear values, there is insufficient evidence to conclude whether the two sides differ. The string `******` indicates masked data, not a secret bound as six literal asterisks.

## 6. Overriding via command line: YAML stays unchanged, bean changes

Stop the previous process with `Ctrl+C`, then restart:

```shell
java -jar target/actuator-binding-demo-1.0.0.jar --demo.client.timeout=5s
```

The five `DEMO` lines are now:

```text
DEMO env.timeout=5s
DEMO bound.timeout=PT5S
DEMO bound.timeoutMillis=5000
DEMO env.max-attempts=null
DEMO bound.maxAttempts=3
```

Call the two endpoints from the previous section again. When cross-checking:

| Evidence | What to look for |
| --- | --- |
| YAML file | Still declares `1s` |
| `env/demo.client.timeout` | Selected value is `5s`, coming from command-line arguments |
| Source list in `env` | May still show the YAML source containing `1s` at lower precedence |
| `configprops/demo.client` | Bean reflects a five-second timeout |
| Bean-reading logs | `PT5S` and `5000` milliseconds |

This is a proper binding result. YAML was not modified; the higher-precedence input won.

In this run, the object section carrying prefix `demo.client` has the following shape; outer `contexts` and `beans` wrappers are omitted to focus on the data to read:

```json
{
  "prefix": "demo.client",
  "properties": {
    "maxAttempts": 3,
    "timeout": "PT5S"
  },
  "inputs": {
    "maxAttempts": {},
    "timeout": {
      "value": "5s",
      "origin": "\"demo.client.timeout\" from property source \"commandLineArgs\""
    }
  }
}
```

`properties.timeout` is the value on the bean, while `inputs.timeout.value` is the input that was used. The empty object at `inputs.maxAttempts` accompanies the bean value of `3`, because this property uses a code default.

You can change both properties in the same startup:

```shell
java -jar target/actuator-binding-demo-1.0.0.jar --demo.client.timeout=5s --demo.client.max-attempts=7
```

The last two lines will be:

```text
DEMO env.max-attempts=7
DEMO bound.maxAttempts=7
```

The key name `max-attempts` and the record component `maxAttempts` differ in form but bind properly via relaxed binding rules. When writing keys in files or arguments, prefer lowercase kebab-case. Do not assume that every punctuation swap or renaming works across every configuration-reading API.

## 7. Two experiments that prevent false conclusions

### 7.1. Bean holds a value even without an external key

Stop the process. Remove only the block:

```yaml
demo:
  client:
    timeout: 1s
```

Keep the remaining configuration sections, repackage with `mvn clean package`, and run the JAR without passing `demo.client.*` arguments.

The five output lines are:

```text
DEMO env.timeout=null
DEMO bound.timeout=PT2S
DEMO bound.timeoutMillis=2000
DEMO env.max-attempts=null
DEMO bound.maxAttempts=3
```

The object takes the code defaults `2s` and `3`. A key absent from `Environment` can still correspond to a bean property with a valid value. When looking up a nonexistent key via the `env` endpoint, do not expect an entry containing defaults declared only with `@DefaultValue`.

Restore the YAML block and repackage before the next experiment if you want to return to the initial configuration.

### 7.2. Having a key in the environment does not guarantee binding succeeds

Stop the process and run:

```shell
java -jar target/actuator-binding-demo-1.0.0.jar --demo.client.timeout=abc
```

`abc` cannot be converted to the example's `Duration`. Under these default settings, configuration bean creation fails and the application fails to start. None of the five `DEMO` lines from the runner appear because the runner only executes after the context has started successfully.

Do not expect YAML `1s` or `@DefaultValue("2s")` to rescue a higher-precedence malformed input. Defaults for missing inputs do not equate to a mechanism for ignoring invalid data.

When the application fails at this stage, diagnose using startup errors and the nested causes of binding. An Actuator endpoint on an application that failed to start is not a reliable observation source. Exact error message text can vary across versions; identify the key `demo.client.timeout`, target type `Duration`, and offending input.

## 8. Diagnostic workflow in real applications

### Step 1: Identify the right process and property

Record the JAR version, deployment environment, active profiles, canonical key name, prefix, Java type, and target bean expected to receive configuration. If multiple application replicas exist, ensure observations target the same replica.

Using the same URL behind a load balancer does not guarantee two calls hit the same process. Comparing an `env` response from replica A against `configprops` from replica B can produce discrepancies unrelated to binding.

### Step 2: Inspect the environment value and winning source

Call `env/<property.name>`, locate the selected source and origin if available. If it differs from expected YAML, inspect startup arguments, environment variables, profiles, and external files first.

A misspelled key can still exist in the environment without matching any property on the configuration class. The presence of a key does not prove anything consumes it.

### Step 3: Inspect the right configuration bean

Call `configprops/<prefix>`, locate the right context and bean. Compare `properties` against `inputs`, target types, and code defaults.

If the bean is missing, check whether it was registered via `@EnableConfigurationProperties` or scanned via `@ConfigurationPropertiesScan`; then verify the prefix and how the real application receives data. Do not rush to edit YAML values when the issue is that no target bean exists to bind to.

### Step 4: Compare by semantics, not just strings

`5000ms`, `5s`, and `PT5S` can all represent the same `Duration`. For a `Duration` field without `@DurationUnit`, a bare number like `5000` defaults to milliseconds; for an `int` field, that number is simply an integer and carries no inherent time unit.

Always check the target type and unit rules. Do not apply `Duration` rules to every property containing the word "timeout".

### Step 5: Trace to where the configuration is used

The following abbreviated snippet shows a common cause:

```java
// Illustrative snippet at client construction site; not a standalone program.
var client = java.net.http.HttpClient.newBuilder()
        .connectTimeout(java.time.Duration.ofSeconds(1))
        .build();
```

Even when the bean binds to five seconds, the code above still passes one second into the builder. Actuator accurately reflects the bean, yet does not prove the library is using that bean.

Check the value actually passed into the API, when the client is constructed, and the property's semantics. For example, connection timeout is not the same as total request timeout. If multiple instances of a bean exist or a component keeps a copied value, identify the exact object in use.

A single timing measurement is also affected by network, retries, and other limits. Use evidence at component configuration time alongside appropriate behavioral tests, rather than attributing every latency to a single key.

## 9. Limitations to keep in mind when reading evidence

| Symptom | What can be concluded | What needs further investigation |
| --- | --- | --- |
| YAML has key, `env` returns different value | The value in that file is not the one currently resolved | Winning source, profile, JAR, and application replica |
| `env` has value, `configprops` lacks expected bean | Target `@ConfigurationProperties` bean not observed | Bean registration, prefix, context, `@Value`, or direct lookup |
| `env` lacks key, bean still has value | Default may exist on the configuration class | Constructor parameters or field initializers |
| Source shows `5s`, bean shows `PT5S` | May be the same value after type conversion | Data type and units |
| Value displays `******` | Observed data has been masked | Display policy and access permissions |
| Bean is right, behavior is wrong | Binding alone does not prove usage | Point of use, hardcoded values, replicas, component creation timing |
| Endpoint unreachable | Cannot observe data over HTTP | Exposure, base path, management port, auth, and startup status |

Two additional timing limitations:

- Editing a configuration file after the application has started does not automatically reload `Environment`, rebind beans, or recreate clients. Plain Spring Boot in this example provides no mechanism to auto-refresh that entire chain.
- If the application adds a dynamic configuration refresh mechanism, current environment values and previously created beans may reflect different points in time. Check the refresh rules of that specific mechanism. The Actuator `GET` calls used in this lesson are read operations, not commands to reapply configuration.

For library-consumed properties, also check bean creation conditions: valid configuration binding does not guarantee an auto-configuration was applied or that the auto-configured bean was chosen over an application-defined bean.

Per [Actuator value sanitization rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization), values are masked by default; `show-values` and viewing permissions must be evaluated separately from endpoint access authorization. Do not enable broad visibility just to handle a single diagnostic check in a public environment.

## 10. Self-check with evidence

Run the following tests, stopping the previous process before starting the next run:

1. YAML `1s`, no arguments passed: predict `Environment`, `Duration`, and milliseconds.
2. Keep YAML, add `--demo.client.timeout=2500ms`: explain why YAML still says `1s` while the bean holds two and a half seconds.
3. Omit `max-attempts`: explain why the environment log prints `null` while the bean returns `3`.
4. Add `--demo.client.max-attempts=7`: identify which input replaced the default.
5. Pass `--demo.client.timeout=abc`: predict the failure stage and select the appropriate evidence source.

Core answers: run 1 is `1s → PT1S → 1000`; run 2 is `2500ms → PT2.5S → 2500`; run 3 uses the record default; run 4 uses the argument with value `7`; run 5 fails while binding to `Duration`.

After each successful run, reconcile `env`, `configprops`, and bean-reading logs. When stating "the application picked up the configuration", specify whether you are proving **which source was selected**, **which bean received the value**, or **which component actually used that value**.
