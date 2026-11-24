# SPRING_APPLICATION_JSON and the Position of the JSON Source in Precedence Order

## 1. The Problem to Solve

A Spring Boot application typically receives configuration from multiple places: `application.yml`, operating system environment variables, JVM properties (`-D...`), and command-line arguments (`--...`). The same key can appear in multiple sources—for instance, `server.port` declared in a file yet given a different value at deployment time.

`SPRING_APPLICATION_JSON` lets you pass **multiple configuration properties as a single JSON string** right when launching the application. Spring Boot reads this string, turns the JSON fields into structured configuration keys, and adds them to `Environment` as a `PropertySource`.

Two key questions are: what keys is the JSON converted into, and **do JSON values win or lose against other configuration sources**? Understanding both lets you accurately predict the value the application receives when the same key appears in multiple places.

## 2. What Is SPRING_APPLICATION_JSON?

The following environment variable example contains two configuration groups:

```bash
export SPRING_APPLICATION_JSON='{"server":{"port":9090},"demo":{"message":"hello","retries":4}}'
java -jar app.jar
```

Spring Boot can access the equivalent keys:

| Configuration Key | Received Value |
| --- | --- |
| `server.port` | `9090` |
| `demo.message` | `hello` |
| `demo.retries` | `4` |

Nested JSON objects are flattened into property paths, such as `demo.message`. Values can then be read via `Environment`, `@Value`, or bound into a `@ConfigurationProperties` class. JSON is **a configuration source**, not the name of a file that Spring Boot automatically looks for on disk.

Spring Boot can also accept the JSON string via the `spring.application.json` system property, the `--spring.application.json=...` argument, or a matching JNDI entry in environments with JNDI. Regardless of how the JSON string is supplied, properties extracted from it belong to **the JSON source with its own precedence position**, rather than simply inheriting the precedence of the transport mechanism.

Example using a JVM argument:

```bash
java -Dspring.application.json='{"demo":{"message":"from JSON"}}' -jar app.jar
```

Here `-Dspring.application.json` supplies **the entire JSON string**; the `demo.message` key is produced from the JSON payload. Distinguish that from `-Ddemo.message=...`, which creates a standard JVM property directly.

## 3. Position of JSON in Precedence Order

When multiple `PropertySource` instances contain the same key, the source with **higher precedence** decides the effective value. For common sources when running Spring Boot 3.x, the order from high to low is:

| Precedence Level | Source | Example setting `demo.message` |
| --- | --- | --- |
| 1 — highest in table | Command-line arguments | `--demo.message=cli` |
| 2 | Spring Boot JSON source | `SPRING_APPLICATION_JSON='{"demo":{"message":"json"}}'` |
| 3 | Java system properties | `-Ddemo.message=system` |
| 4 | OS environment variables | `DEMO_MESSAGE=env` |
| 5 — lowest in table | Config data | `demo.message=file` in `application.yml` |

**Relationship to remember:**

```text
Command-line arguments
        > SPRING_APPLICATION_JSON
        > JVM properties (-D...)
        > standard environment variables
        > application.yml / application.properties
```

The `>` symbol means "has higher precedence than". This table focuses only on **five common sources**, not the complete catalog of sources supported by Spring Boot. Web applications or test runs also have other sources such as Servlet init parameters, JNDI, test property sources, and DevTools settings. Profile-specific configuration such as `application-prod.yml` still belongs to the config data group; precedence rules **within the config file group** are a separate topic.

One caveat to note: if an application explicitly disables adding command-line properties to `Environment`, for example via `SpringApplication.setAddCommandLineProperties(false)`, then the precedence line for `--demo.message=...` no longer applies as shown.

## 4. Experiment: Multiple Sources Setting the Same Key

Suppose `src/main/resources/application.yml` contains:

```yaml
demo:
  message: "file"
  retries: 1
```

To observe the values when the application runs, you can add the following demo component:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DemoConfigurationPrinter implements ApplicationRunner {
    private final Environment environment;

    public DemoConfigurationPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("demo.message = "
                + environment.getProperty("demo.message"));
        System.out.println("demo.retries = "
                + environment.getProperty("demo.retries", Integer.class));
    }
}
```

After packaging the application into `app.jar`, run it in Bash or a POSIX-compatible shell:

```bash
DEMO_MESSAGE=env \
SPRING_APPLICATION_JSON='{"demo":{"message":"json","retries":4}}' \
java -Ddemo.message=system -jar app.jar --demo.message=cli
```

Notable output from the configuration printer:

```text
demo.message = cli
demo.retries = 4
```

Key-by-key explanation:

- `demo.message` is present in all five sources. The `--demo.message=cli` argument has the highest precedence in this example, so the value is `cli`.
- `demo.retries` is only declared in the config file and in JSON. The JSON source has higher precedence than the file, so the result is `4`.
- If you omit just `--demo.message=cli`, `demo.message` becomes `json`; it does **not** fall back to `system` or `env` because JSON is still active.
- If you then also omit `SPRING_APPLICATION_JSON`, `-Ddemo.message=system` beats `DEMO_MESSAGE` and the config file.

The trailing `\` in the Bash example continues the command across lines for readability. Everything can be written on one line. When using Windows PowerShell, set the environment variable using PowerShell syntax:

```powershell
$env:SPRING_APPLICATION_JSON = '{"demo":{"message":"json","retries":4}}'
java -jar app.jar
Remove-Item Env:SPRING_APPLICATION_JSON
```

The `Remove-Item` command removes the variable from the current PowerShell session after the experiment. Quoting rules differ among Bash, PowerShell, CMD, Docker, and deployment platform variable editors; ensure that **the actual value reaching the application is a valid JSON string**.

## 5. How Does Spring Boot Read and Bind JSON?

Consider the configuration:

```json
{
  "demo": {
    "message": "hello",
    "retry": {
      "max-attempts": 3
    },
    "servers": ["alpha", "beta"]
  }
}
```

The paths can be represented as `demo.message`, `demo.retry.max-attempts`, `demo.servers[0]`, and `demo.servers[1]`. Spring Boot's configuration binder (`Binder`) can convert them to the appropriate Java types.

Example of a typed configuration:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String message,
        Retry retry
) {
    public record Retry(int maxAttempts) {}
}
```

You can enable scanning for `@ConfigurationProperties` classes via `@ConfigurationPropertiesScan` on the application class. With this example, the JSON field `max-attempts` binds to the Java component `maxAttempts` following Spring Boot's property binding rules.

Importantly: binding and precedence **are two distinct stages**. First Spring Boot chooses the effective value for each key across configuration sources; then the application reads or binds those values into Java objects.

Do not assume lists declared across multiple sources will automatically concatenate elements. For list properties, check the Binder's override rules for the specific case.

## 6. Special Case: JSON Null Values

An easily misunderstood detail is that `null` in JSON **does not erase a value in a lower-precedence source**.

Suppose `application.yml` has:

```yaml
demo:
  message: "from file"
```

And the environment variable is:

```bash
export SPRING_APPLICATION_JSON='{"demo":{"message":null}}'
```

When the application calls `environment.getProperty("demo.message")`, the property can still receive `from file`. Why: the property resolver treats a `null` value from the JSON source as **having no usable value** for that key, so it continues searching lower-precedence sources.

Distinguish three states:

| Case | Meaning during property resolution |
| --- | --- |
| JSON does not contain `demo.message` | Search other sources |
| JSON contains `"message": null` | Can still find a value in a lower-precedence source |
| JSON contains `"message": ""` | Empty string is a supplied value; binding impact depends on target type |

Therefore, do not use `null` in `SPRING_APPLICATION_JSON` to "clear" a setting in `application.yml`. To disable a feature, choose a representation the application actually supports, such as `demo.enabled=false`, and handle that value explicitly in application code.

## 7. When to Use JSON vs. Other Sources?

`SPRING_APPLICATION_JSON` is useful when a deployment environment allows passing only a single configuration variable yet the application needs multiple nested keys. It is also handy for quickly testing a combination of values without editing `application.yml` or creating extra config files.

However, the options serve different roles:

| Configuration Method | Suitable When |
| --- | --- |
| `application.yml` or `application.properties` | Structured default configuration, easy to read and manage with the application |
| Individual environment variables like `SERVER_PORT` | Need to override a few values at deployment time |
| `SPRING_APPLICATION_JSON` | Need to pass a structured group of properties inside a single JSON value |
| `--server.port=...` | Need a direct override for a single launch |
| `spring.config.import` | Need to load additional configuration data sources via the config data mechanism |

Do not confuse `SPRING_APPLICATION_JSON` with `spring.config.import`: one **holds JSON values directly**, while the other **specifies additional configuration sources to load**. Putting a file path into `SPRING_APPLICATION_JSON` does not cause Spring Boot to treat it as the contents of a JSON file.

For passwords, API keys, and sensitive data, consider your deployment platform's secrets management mechanism. Environment variables and startup arguments can still be exposed via process inspection tools, command history, logs, or deployment manifests if managed carelessly. Never print the entire `Environment` just to verify a single property.

## 8. Diagnosing Unexpected Results

When a key receives an unexpected value, check in order:

1. **What key is actually being read?** For example, `demo.message` differs from `demo.messages`; an environment variable `DEMO_MESSAGE` is mapped according to property binding rules.
2. **Is the JSON string valid?** Standard JSON requires double quotes for field names and strings, and disallows trailing commas in objects.
3. **Is there a higher-precedence source?** A `--demo.message=...` argument can mask the JSON value even when JSON loaded successfully.
4. **Is the JSON value `null`?** If so, the key can pick up the value from a lower source.
5. **Did the shell pass the string intact?** Improperly handled quotes can alter the JSON string before it reaches the JVM.
6. **Did the application alter property sources itself?** Startup code can add property sources or disable command-line properties.

In a controlled development environment, Spring Boot Actuator offers the `env` endpoint to inspect property source details if configured to permit access. Restrict access and avoid exposing sensitive configuration data. The simplest check for a small test remains printing **only the key under investigation** via `Environment#getProperty`.

## 9. Self-Check Exercise

Assume all four configuration sources coexist:

```yaml
# application.yml
demo:
  color: blue
  retries: 2
```

```text
Standard env var:      DEMO_COLOR=green
JVM property:          -Ddemo.color=yellow
SPRING_APPLICATION_JSON={"demo":{"color":"red","retries":5}}
Command-line arg:      --demo.color=black
```

Predict the results before running:

| State | `demo.color` | `demo.retries` |
| --- | --- | --- |
| All sources present | `black` | `5` |
| Omit `--demo.color` | `red` | `5` |
| Also omit JSON source | `yellow` | `2` |
| Also omit JVM property | `green` | `2` |
| Also omit env var | `blue` | `2` |

This exercise highlights the principle: **precedence is applied key by key**, rather than selecting one source for the entire configuration object. JSON can win on `demo.retries` while a command-line argument wins on `demo.color`.

## 10. Key Takeaways

- `SPRING_APPLICATION_JSON` holds a **JSON string**, which Spring Boot converts into hierarchically named properties in `Environment`.
- For standard deployment sources in Spring Boot 3.x: **command-line arguments > JSON > JVM properties > environment variables > config data**.
- When supplying JSON via JVM `spring.application.json` or the command line, the extracted keys are still processed in the dedicated **JSON source**.
- Setting a property to JSON `null` does not erase or disable a value from a lower-precedence source.
- To determine the effective configuration, examine **each key**, validate JSON syntax, and check whether any higher-precedence source is overriding it.
