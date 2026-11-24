# Passing Structured Configuration via SPRING_APPLICATION_JSON

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Environment Variables

## 1. The problem: passing a whole group of properties with a single string

A Spring Boot application normally receives configuration from `application.yml`, environment variables, Java system properties, and command-line arguments. When you need to declare many related keys—such as endpoints, timeouts, server lists, and feature flags—creating a separate environment variable for each key can become cumbersome. Nested structures are also not always easy to represent using operating system environment variable names.

Spring Boot offers another option: placing **a JSON object** in an environment variable named **`SPRING_APPLICATION_JSON`**. Boot parses the JSON, turns nested values into properties, and exposes them in `Environment` as a configuration source.

Example:

~~~bash
export SPRING_APPLICATION_JSON='{"catalog":{"endpoint":"https://catalog.internal","timeout":"5s","features":{"audit":true}}}'
java -jar catalog.jar
~~~

Semantically, the application receives these keys:

~~~properties
catalog.endpoint=https://catalog.internal
catalog.timeout=5s
catalog.features.audit=true
~~~

The `.properties` snippet above illustrates the generated keys, **not** a file you must generate manually. The values inside the JSON enter Spring Boot's regular externalized configuration mechanism.

### After this lesson, you can

- Write a valid JSON object to supply nested configuration from a single environment variable.
- Explain how a JSON branch like `catalog.features.audit` becomes a property readable via `Environment` or `@ConfigurationProperties`.
- Pass JSON on Linux/macOS, Windows PowerShell, Docker, and Kubernetes without confusing shell quoting with JSON syntax.
- Determine the precedence of `SPRING_APPLICATION_JSON` relative to `application.yml`, regular environment variables, Java system properties, and command-line arguments.
- Understand how arrays, maps, `null` values, and type conversion behave.
- Diagnose JSON errors, binding errors, override errors, and choose how to supply sensitive data.

## 2. How it works

### 2.1. JSON is a transport format, not a business property name

There are two layers to distinguish:

1. The `SPRING_APPLICATION_JSON` environment variable holds a **valid JSON string**.
2. Spring Boot reads that string, parses the JSON object, and exposes the inner keys as properties.

Example environment variable value:

~~~json
{
  "gateway": {
    "endpoint": "https://api.internal",
    "connect-timeout": "2s",
    "retry": {
      "max-attempts": 4,
      "enabled": true
    }
  }
}
~~~

Logical properties include:

| Path in JSON | Spring property | Value |
| --- | --- | --- |
| `gateway.endpoint` | `gateway.endpoint` | `https://api.internal` |
| `gateway.connect-timeout` | `gateway.connect-timeout` | `2s` |
| `gateway.retry.max-attempts` | `gateway.retry.max-attempts` | number `4` |
| `gateway.retry.enabled` | `gateway.retry.enabled` | boolean `true` |

Spring handles type conversion when binding or requesting a specific type. JSON provides raw data, while `Environment` and `Binder` resolve values to match Java code.

Example:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class GatewayOptionsReader {
    private final Environment environment;

    public GatewayOptionsReader(Environment environment) {
        this.environment = environment;
    }

    public String endpoint() {
        return environment.getRequiredProperty("gateway.endpoint");
    }

    public Boolean retryEnabled() {
        return environment.getRequiredProperty(
                "gateway.retry.enabled", Boolean.class);
    }

    public Integer maxAttempts() {
        return environment.getRequiredProperty(
                "gateway.retry.max-attempts", Integer.class);
    }
}
~~~

There is no need to invoke a JSON parser inside your service to re-read the environment variable. Spring Boot has already registered the properties from the JSON into `Environment`.

### 2.2. Nested structures map by path

JSON:

~~~json
{
  "service": {
    "http": {
      "host": "0.0.0.0",
      "port": 8088
    },
    "limits": {
      "requests-per-minute": 120
    }
  }
}
~~~

corresponds to keys such as:

~~~text
service.http.host
service.http.port
service.limits.requests-per-minute
~~~

Nested object branches organize configuration by business domain, while key names remain accessible using dot notation. Key names should generally use **kebab-case** for `@ConfigurationProperties`, such as `requests-per-minute`, since that convention aligns cleanly with Spring Boot relaxed binding.

A JSON object does not create a Java bean automatically. A configuration bean is created when the application defines `@ConfigurationProperties` and has registered or enabled appropriate scanning/enabling.

### 2.3. Can represent scalars, booleans, numbers, and arrays

JSON supports:

~~~json
{
  "demo": {
    "name": "demo-service",
    "enabled": true,
    "attempts": 3,
    "ratio": 0.25,
    "regions": ["ap-southeast-1", "ap-northeast-1"]
  }
}
~~~

Differences to remember:

- `"3"` is a JSON string; `3` is a JSON number.
- `"true"` is a JSON string; `true` is a JSON boolean.
- An array `[...]` represents indexed elements and can bind into Java lists or arrays.
- `null` has special semantics in Spring Boot; do not use it as a way to delete lower-priority properties.
- A field `"limits": {"x": 1}` is a nested object; it differs from `"limits": "{\"x\":1}"`, which contains escaped JSON inside a string.

## 3. Complete example: structured client configuration

Suppose the application has default configuration in `application.yml`:

~~~yaml
catalog:
  client:
    endpoint: "https://default.example"
    connect-timeout: 3s
    retry-count: 2
    enabled: false
    regions:
      - local
    labels:
      source: "file"
      team: "backend"
~~~

For a deployment, we want to override with JSON:

~~~json
{
  "catalog": {
    "client": {
      "endpoint": "https://catalog.internal",
      "connect-timeout": "1500ms",
      "retry-count": 5,
      "enabled": true,
      "regions": ["sg", "jp"],
      "labels": {
        "source": "json",
        "environment": "staging"
      }
    }
  }
}
~~~

When passing this JSON under `SPRING_APPLICATION_JSON`, properties from the JSON source can override matching keys from `application.yml`.

### 3.1. Binding into `@ConfigurationProperties`

Example with Spring Boot 3 and Java 17+:

~~~java
package com.example.catalog;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int retryCount,
        boolean enabled,
        List<String> regions,
        Map<String, String> labels
) {}
~~~

Enable scanning:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

A service can inject it directly:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CatalogClientProperties properties;

    public CatalogService(CatalogClientProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        return properties.endpoint() + " / "
                + properties.connectTimeout()
                + " / retry=" + properties.retryCount();
    }
}
~~~

The values `"1500ms"`, number `5`, and boolean `true` are converted by Spring Boot into `Duration`, `int`, and `boolean` respectively during binding. If contents cannot be converted, the application may report a binding error while initializing configuration.

### 3.2. Result of the example

Assuming no higher-priority source than JSON overrides the keys under consideration:

| Field | Initial value in YAML | Value after applying JSON |
| --- | --- | --- |
| `endpoint` | `https://default.example` | `https://catalog.internal` |
| `connectTimeout` | `3s` | `1500ms` |
| `retryCount` | `2` | `5` |
| `enabled` | `false` | `true` |
| `regions` | `[local]` | `[sg, jp]` |
| `labels.source` | `file` | `json` |
| `labels.team` | `backend` | `backend` |
| `labels.environment` | not present | `staging` |

With `@ConfigurationProperties`, map properties can merge by key, whereas lists are usually **replaced** by the list from the higher-priority source rather than concatenating all elements. Do not assume a universal concatenation rule for every collection.

## 4. Passing via environment variable across platforms

### 4.1. Linux and macOS (Bash or compatible shells)

Wrapping JSON in **shell single quotes** preserves the JSON double quotes:

~~~bash
export SPRING_APPLICATION_JSON='{"catalog":{"client":{"endpoint":"https://catalog.internal","retry-count":5,"enabled":true}}}'
java -jar catalog.jar
~~~

Or apply it for a single run only:

~~~bash
SPRING_APPLICATION_JSON='{"catalog":{"client":{"retry-count":5}}}' \
java -jar catalog.jar
~~~

The `'...'` in the shell is the outer quoting layer; the actual content Spring Boot receives is still JSON starting with `{` and ending with `}`. Do not send the shell's single quotes as part of the variable value.

For large JSON payloads, you can use a tool to generate JSON to avoid quoting bugs, then pass the result through the process environment variable. When doing so, keep environment variable size limits and potential visibility in execution environments/diagnostics in mind.

### 4.2. Windows PowerShell

In PowerShell:

~~~powershell
$env:SPRING_APPLICATION_JSON = '{"catalog":{"client":{"endpoint":"https://catalog.internal","enabled":true}}}'
java -jar catalog.jar
~~~

The environment variable assignment syntax differs from Bash, but the JSON value passed to Boot has the same structure. `$env:SPRING_APPLICATION_JSON` only affects the current PowerShell session environment and child processes started from it; it does not mean a machine-wide environment variable has been set for all runs.

If the application is launched by an IDE or service manager, set the environment variable **on the actual launching process**, not in an unrelated terminal.

### 4.3. Docker

Example running an illustrative image:

~~~bash
docker run --rm \
  -e SPRING_APPLICATION_JSON='{"catalog":{"client":{"endpoint":"https://catalog.internal","enabled":true}}}' \
  example/catalog:1.0
~~~

The image above is only an example. Docker sets the environment variable inside the container; Spring Boot reads it when the Java process starts.

For real applications, you can declare the environment variable in container/deployment configuration. If the JSON string holds sensitive data, evaluate the risk since environment variables or deployment parameters can be inspected through certain administrative tools.

### 4.4. Kubernetes

In a Deployment's Pod template, you can pass JSON in the `env` section:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: example/catalog:1.0
          env:
            - name: SPRING_APPLICATION_JSON
              value: '{"catalog":{"client":{"endpoint":"https://catalog.internal","retry-count":5,"enabled":true}}}'
~~~

The YAML `value` is **a string containing JSON**. Kubernetes does not automatically unpack its contents into separate variables. The container's Spring Boot process receives `SPRING_APPLICATION_JSON` and then parses the JSON.

For multi-line or environment-specific configurations, you can also manage the JSON string in a ConfigMap (if non-sensitive) or use an appropriate secret management method and reference it. A ConfigMap declaring JSON is not loaded automatically unless mounted/injected into the application per deployment config.

### 4.5. Setting JSON via Java system property or command-line argument

Besides the environment variable `SPRING_APPLICATION_JSON`, Spring Boot can also process JSON via the system property named `spring.application.json`:

~~~bash
java -Dspring.application.json='{"catalog":{"client":{"enabled":true}}}' \
  -jar catalog.jar
~~~

With a command-line option:

~~~bash
java -jar catalog.jar \
  --spring.application.json='{"catalog":{"client":{"enabled":true}}}'
~~~

These commands use Unix-style shell quoting; Windows cmd and PowerShell have different rules. Regardless of which channel delivers the JSON, its contents are parsed into Spring Boot's JSON source.

Distinguish two names:

- `SPRING_APPLICATION_JSON`: the environment variable name suitable for process environments.
- `spring.application.json`: the dotted-notation property name usable with Java system properties or command-line arguments.

Also distinguish the **JSON delivery vehicle** from the **properties inside the JSON**: for example, `--spring.application.json=...` creates a source for `catalog.client.enabled`, rather than requiring business keys to begin with `spring.application.json.`.

## 5. Exact JSON syntax: common mistakes

### 5.1. JSON requires standard syntax

Valid example:

~~~json
{
  "app": {
    "name": "orders",
    "enabled": true,
    "port": 8080,
    "servers": ["a.internal", "b.internal"]
  }
}
~~~

Common mistakes:

| Syntax | Problem |
| --- | --- |
| `{app: {enabled: true}}` | JSON requires key names in double quotes |
| `{'app': {'enabled': true}}` | Standard JSON does not use single quotes for keys or strings |
| `{"app":{"enabled":True}}` | JSON booleans are lowercase `true` / `false` |
| `{"app":{"count":3,}}` | Trailing commas at the end of objects are invalid |
| `{"app":{"port":8080} // comment}` | Standard JSON does not support comments |
| `{"app":{"timeout":5s}}` | `5s` must be a string, e.g. `"5s"` |

JSON is neither YAML nor a JavaScript object literal. Use a JSON validator or a JSON library inside configuration-generation tooling when dealing with many braces and escaped strings.

### 5.2. Shell quoting and JSON escaping are two different layers

Suppose a value contains double quotes:

~~~json
{
  "app": {
    "message": "He said \"hello\""
  }
}
~~~

The `\"` inside the JSON string is **JSON escaping**. Wrapping the entire JSON in Bash or PowerShell single quotes prevents the shell from stripping double quotes. When passing through a YAML manifest or CI/CD tool, there is an additional encoding layer of the intermediate format; make sure the final environment variable holds valid JSON with no extra outer quotes around the object.

### 5.3. A JSON string is passed via environment, not a file path

If you assign:

~~~bash
export SPRING_APPLICATION_JSON=/etc/catalog/settings.json
~~~

Spring Boot will not by default treat this as a file path to read; it attempts to interpret the value as JSON. To load a configuration document from a file, use config data locations and `spring.config.import` appropriately, such as YAML/properties or a supported loader type.

Likewise, having a file named `settings.json` on disk does not make Boot load it automatically as `SPRING_APPLICATION_JSON`. Receiving JSON through an environment variable differs from default configuration file discovery.

## 6. Precedence order: when JSON and other sources share keys

### 6.1. JSON normally takes precedence over system properties and OS environment

In default Spring Boot externalized configuration, some sources are ordered from **highest to lowest** as follows (omitting test-specific sources and certain special cases):

| Relative order | Source |
| --- | --- |
| Higher | Command-line arguments, e.g., `--app.mode=from-cli` |
| Next | Properties parsed from `SPRING_APPLICATION_JSON` / `spring.application.json` |
| Next | ServletConfig/ServletContext init params and JNDI if present in a Servlet environment |
| Next | Java system properties, e.g., `-Dapp.mode=from-jvm` |
| Next | Regular environment variables, e.g., `APP_MODE=from-env` |
| Lower | Config data such as `application.yml` / `application.properties` (depending on location and profile) |
| Even lower | `@PropertySource` and default properties |

This is **configuration source lookup order**, not line order within a file. Application code can alter the order with custom property sources or disable command-line properties, so exact outcomes depend on the actual runtime.

### 6.2. Example of multi-layer overriding

`application.yml`:

~~~yaml
app:
  mode: "from-file"
  region: "local"
~~~

Environment variables:

~~~bash
export APP_MODE=from-env
export SPRING_APPLICATION_JSON='{"app":{"mode":"from-json","region":"cluster"}}'
~~~

And run:

~~~bash
java -jar catalog.jar --app.mode=from-cli
~~~

Typical result:

~~~text
app.mode   = from-cli
app.region = cluster
~~~

Explanation: for `app.mode`, the command-line argument beats JSON; for `app.region`, JSON beats the file value because no higher source overrides it.

If `--app.mode=from-cli` is removed, `app.mode` resolves to `from-json` because JSON has higher priority than environment variable `APP_MODE`.

### 6.3. When a key is present in JSON with a null value

Example:

~~~yaml
# application.yml
app:
  name: "catalog"
~~~

And JSON:

~~~json
{
  "app": {
    "name": null
  }
}
~~~

Do not expect JSON `null` to delete or mask `app.name` from a lower-priority source. In Spring Boot's property resolution mechanism, JSON `null` is treated as a missing value, so a lower-priority source can still supply the value. In this example, `app.name` can still resolve to `catalog`.

If you want to actively disable behavior, design an explicit property like `app.enabled=false` instead of using `null` to mean "delete values from lower sources".

### 6.4. Arrays and maps across multiple sources

Suppose `application.yml` declares:

~~~yaml
app:
  servers:
    - "default-a"
    - "default-b"
  labels:
    team: "core"
    region: "local"
~~~

JSON:

~~~json
{
  "app": {
    "servers": ["json-a"],
    "labels": {
      "region": "apac",
      "source": "json"
    }
  }
}
~~~

With standard `@ConfigurationProperties`:

- List `app.servers` from the higher-priority source typically **replaces the entire list**, yielding `[json-a]` instead of concatenating `[default-a, default-b, json-a]`.
- Map `app.labels` can merge entry by entry: `team=core` from file, `region=apac` from JSON, `source=json` from JSON.

Binding complex types follows dedicated rules; do not infer from scalar precedence that every structure deep-merges.

## 7. Nested configuration and property names in Java

### 7.1. Using `@Value` for a few keys

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogFlags {
    private final boolean auditEnabled;

    public CatalogFlags(
            @Value("${catalog.features.audit:false}")
            boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }

    public boolean auditEnabled() {
        return auditEnabled;
    }
}
~~~

The `:false` expression provides a fallback when the property is absent. JSON data participates in the same placeholder resolution mechanism as other sources. However, for multiple related keys or configuration containing lists/maps, `@ConfigurationProperties` is usually easier to manage and test.

### 7.2. Using `@ConfigurationProperties` for groups of many keys

Example:

~~~json
{
  "worker": {
    "pool": {
      "enabled": true,
      "size": 8,
      "shutdown-timeout": "10s"
    }
  }
}
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker.pool")
public record WorkerPoolProperties(
        boolean enabled,
        int size,
        Duration shutdownTimeout
) {}
~~~

Once the bean is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, Spring Boot binds properties into the corresponding fields. The `"10s"` value uses Spring conversion to become a `Duration`.

When validation is needed, add constraints such as positive pool size or non-negative timeout; constraints can be enforced via Bean Validation once the appropriate dependency and annotations are configured.

### 7.3. Key names and relaxed binding

Spring Boot recommends canonical property names in kebab-case, such as:

~~~text
worker.pool.shutdown-timeout
~~~

A Java field `shutdownTimeout` can bind from that key. With JSON, writing keys in kebab-case right at the source keeps `application.yml`, system properties, and JSON consistent. Do not treat uppercase or underscore differences of environment variables as a reason to name every JSON key using environment variable conventions.

## 8. JSON helps solve configurations hard to express with regular environment variables

One difficulty with environment variables is that variable names typically only allow characters like letters, digits, and underscores, and systems have varying case-handling rules. As a result, properties containing dots, map keys, or package names can be hard to preserve cleanly.

Example configuring log levels for packages:

~~~json
{
  "logging": {
    "level": {
      "com.example.catalog": "DEBUG",
      "org.springframework.web": "WARN"
    }
  }
}
~~~

Can be passed via:

~~~bash
export SPRING_APPLICATION_JSON='{"logging":{"level":{"com.example.catalog":"DEBUG","org.springframework.web":"WARN"}}}'
java -jar catalog.jar
~~~

Dotted logging keys are transmitted through JSON object keys without encoding all dots into environment variable names. For package-level logging or case-sensitive class names, JSON is easier to express than standard environment variables. The application must still use valid property names and logging settings supported by the current Spring Boot version.

**Not every JSON structure has to nest by every segment of a property name.** For instance, a JSON key that already contains dots like `"com.example.catalog"` can remain in the property path when Spring flattens the structure. Choose key placement appropriate for the binding or Boot feature in use.

## 9. Limitations and alternatives

### 9.1. Using a large JSON payload can be hard to maintain

A small JSON object is handy for passing a group of settings. But when it grows to hundreds of keys, it becomes hard to diff across environments, hard to edit manually, and prone to syntax errors. Often better options for large configurations include:

- External `application.yml` outside the JAR, loaded via config data.
- `spring.config.import` to import additional configuration files.
- `configtree:` when the deployment platform mounts each key as a file.
- ConfigMaps or an infrastructure-appropriate centralized configuration solution.

Choose an option based on deployment needs: overriding a few keys via one environment variable versus managing multiple files, profiles, change tracking, and sensitive configuration.

### 9.2. Size limits and observability

Environment variables and command-line arguments are subject to limits of the operating system, shell, container runtime, and deployment manager. Overly large JSON can exceed limits, be difficult to debug, or get truncated/mis-escaped in pipelines. Do not rely on a single universal size limit across all environments.

Command-line arguments can show up in process listing tools, CI logs, or monitoring systems. Environment variables can also be exposed through deployment manifests, process diagnostics, or privileged accounts. Therefore, **do not assume it is safe to put passwords or private keys directly in JSON** just because JSON is passed via the environment. For critical secrets, consider a secret manager, restricted-permission file mounts, `configtree:`, or platform-supported mechanisms.

### 9.3. Changes after the application has started

Spring Boot parses configuration during application initialization. Changing environment variables in another shell, updating a Kubernetes manifest, or editing a ConfigMap does not mean configuration beans in a running Java process update automatically. Normally a restart/rollout or a dedicated refresh mechanism is needed.

### 9.4. JSON does not replace profiles and config data

`SPRING_APPLICATION_JSON` contributes a relatively high-priority property source; it does not turn nested objects into YAML documents gated by `spring.config.activate.on-profile`. When organizing configuration by profile, `application-{profile}.yml` files, multi-document YAML, or other config data mechanisms retain their own role.

You can pass a profile-selection property via an appropriate configuration source if the platform and startup phase allow, but do not treat each JSON branch as an activation-conditional document like multi-document YAML.

## 10. Diagnosing when JSON has no effect

### 10.1. Diagnostic checklist

1. **Identify the right Java process.** Is `SPRING_APPLICATION_JSON` set in the environment of the running process, not just in another terminal?
2. **Validate the JSON.** Check double quotes, commas, escaping, data types, and ensure no outer shell quotes leaked into the JSON content.
3. **Check key names.** For example, `"catalog":{"client":{"enabled":true}}` maps to `catalog.client.enabled`; do not misread it as `catalog.enabled`.
4. **Check higher-priority sources.** An argument `--catalog.client.enabled=false` can beat JSON.
5. **Check binding.** A value `"five"` cannot convert to `int` in a bean whose `retryCount` is numeric.
6. **Check collection structure.** Lists may be replaced rather than concatenated across sources.
7. **Check startup state.** Was the application restarted after changing environment/deployment config?
8. **Do not print secrets during investigation.** Only use demo keys to test precedence.

### 10.2. Inspecting a non-sensitive key at runtime

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class JsonConfigProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public JsonConfigProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.client.retry-count";

        System.out.println("Resolved " + key + " = "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

If JSON is contributing a value, the JSON source typically appears in the `PropertySource` list exposed by `ConfigurableEnvironment`. Exact source names may depend on the Spring Boot version; do not write business logic depending on a hardcoded source name string.

You can use Spring Boot Actuator `env` and `configprops` to assist lookups when endpoints are secured and sensitive-value masking is configured. Do not expose full environment details or secret data on public endpoints.

### 10.3. Common symptoms

| Symptom | What to check |
| --- | --- |
| Application reports JSON parse error | Shell/YAML quoting, trailing commas, missing braces, unquoted keys |
| `Environment.getProperty(...)` returns null | Wrong nested key, variable didn't reach process, JSON source not loaded |
| Value still follows CLI despite different JSON | Command-line property has higher precedence |
| Value still comes from `application.yml` | Key absent in JSON, JSON value is `null`, or JSON source not loaded |
| `@ConfigurationProperties` fails to bind | Wrong numeric, boolean, duration, URI, or collection type |
| List loses elements from default file | Higher-priority list binding replaces lower-priority list |
| Works in terminal, fails on Kubernetes | Different manifest/env source, different YAML quoting, new image/pod not rolled out |
| A secret appears in logs | Diagnostic tool, startup script, or logging prints raw env/args |

## 11. Step-by-step practice

### Exercise A: from default YAML to JSON override

Create `application.yml`:

~~~yaml
lesson:
  title: "Default lesson"
  enabled: false
  retries: 1
  timeout: 2s
~~~

Run:

~~~bash
export SPRING_APPLICATION_JSON='{"lesson":{"title":"Environment lesson","enabled":true,"retries":3,"timeout":"6s"}}'
java -jar lesson.jar
~~~

Create a bean reading `lesson.title`, `lesson.enabled`, and `lesson.retries`. Assuming no higher-priority source, expected values are `Environment lesson`, `true`, and `3` respectively. `lesson.timeout` can bind as a 6-second `Duration`.

### Exercise B: observing precedence with CLI

Keep the JSON variable from Exercise A and run:

~~~bash
java -jar lesson.jar --lesson.retries=9
~~~

When the application has default command-line properties, `lesson.retries` from CLI beats `3` in JSON. Removing the CLI argument lets the JSON value beat the YAML value.

### Exercise C: nested objects

Pass:

~~~json
{
  "lesson": {
    "cache": {
      "enabled": true,
      "ttl": "30s"
    }
  }
}
~~~

Create `@ConfigurationProperties(prefix = "lesson.cache")` with two fields `boolean enabled` and `Duration ttl`. Predict the results when the JSON is supplied to the environment and when it is omitted.

### Exercise D: arrays and maps

In `application.yml`:

~~~yaml
lesson:
  regions: ["local", "backup"]
  labels:
    owner: "learning"
    stage: "default"
~~~

JSON:

~~~json
{
  "lesson": {
    "regions": ["apac"],
    "labels": {
      "stage": "staging",
      "source": "json"
    }
  }
}
~~~

Bind `regions` to `List<String>` and `labels` to `Map<String,String>`. Verify the regions list has a single element `apac` and the map keeps `owner`, updates `stage`, and adds `source`.

### Exercise E: JSON null

Put in `application.yml`:

~~~properties
lesson.greeting=Hello
~~~

Then pass:

~~~json
{
  "lesson": {
    "greeting": null
  }
}
~~~

Read `lesson.greeting`. If the value remains `Hello`, this reflects that `null` cannot be used to override-delete a property from a lower source in Spring Boot's lookup mechanism. Replace it with an explicit string, such as `"Hi"`, and observe precedence.

### Exercise F: Docker practice

Start the same image twice: first without `SPRING_APPLICATION_JSON`, then setting this variable to JSON containing `lesson.retries=4`. Compare against the value in `application.yml`. When using Kubernetes, try editing `env.value` and rolling out again to see that only the new process picks up the updated configuration.

## 12. Misconceptions to avoid

**"`SPRING_APPLICATION_JSON` is just a property named `spring.application.json`."** It is a JSON transport channel; Spring Boot parses the inner object and exposes business properties such as `lesson.timeout` and `catalog.endpoint`.

**"Passing JSON makes everything highest priority."** Command-line properties still typically have higher precedence than the JSON source; test property sources or custom configurations can also change the picture.

**"JSON null deletes old values."** Do not rely on that assumption; in Spring Boot property resolution, JSON null is treated as a missing value and can fall back to lower sources.

**"Two lists in two sources automatically concatenate."** With Spring Boot list binding, the higher-priority source usually replaces the list from the lower source.

**"As long as the variable name says JSON, YAML-style content will work too."** The `SPRING_APPLICATION_JSON` value must be a valid JSON string, not YAML or a JavaScript object literal.

**"Setting an environment variable in the current terminal works for every deployment style."** The Java process launched by an IDE, Docker, Kubernetes, or a service manager must actually receive that environment variable.

**"Any secret can go in JSON since it is not committed to Git."** Environment variables and command-line arguments still have their own exposure surfaces; choose a controlled secret management channel.

## 13. Key takeaways

- `SPRING_APPLICATION_JSON` lets you pass **a structured JSON object** via an environment variable. Spring Boot flattens branches into property keys readable from `Environment` and bindable via `@ConfigurationProperties`.
- JSON objects support nesting, booleans, numbers, and arrays; valid JSON syntax and proper shell quoting are required.
- JSON properties typically have **higher** precedence than config data, OS environment variables, and Java system properties; command-line application arguments are typically **higher** than JSON.
- `null` in JSON does not delete properties from lower-priority sources. Lists, maps, and scalars have different binding semantics.
- JSON can be supplied via environment variable `SPRING_APPLICATION_JSON`, system property `spring.application.json`, or command-line option `--spring.application.json=...`.
- For large configurations or sensitive data, consider config data files, config trees/secret mounts, and appropriate configuration lifecycle management.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): source precedence order, JSON application properties, and reading configuration.
- [Spring Boot Reference — JSON Application Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.application-json): `SPRING_APPLICATION_JSON`, `spring.application.json`, and how Spring Boot handles `null`.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding nested objects, collections, and relaxed binding.
- [Spring Boot Reference — Working With Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.java-bean-binding): structured configuration examples via `@ConfigurationProperties`.
