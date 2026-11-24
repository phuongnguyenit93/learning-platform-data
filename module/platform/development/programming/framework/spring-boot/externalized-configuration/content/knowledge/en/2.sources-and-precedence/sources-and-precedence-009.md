# Distinguishing Source Precedence, Config Data Loading Order, and Key-Level Override in Spring Boot

## 1. Why Distinguish These Three Concepts?

When the same property appears in multiple places, the critical question is: **Which value will Spring Boot use?** To answer accurately, separate three layers of rules that are often lumped together as "configuration order":

1. **Property source precedence:** when different configuration sources supply the same property, which source has the right to override?
2. **Config data loading and processing order:** in what order are `application.yml`, `application-prod.yml`, external files outside the JAR, and `import`ed files brought into the configuration mechanism?
3. **Property-level override:** when a higher-precedence source only declares a few keys, are missing keys still inherited from lower-precedence sources?

The three concepts are related, yet not identical. A file read later does not necessarily outrank **all** other sources; and a source overriding one property does not mean it replaces all prior configuration.

> Core rule: Spring Boot determines **the effective value for each property** based on the participating sources and their respective precedence order. "Later file wins over earlier file" only makes sense within an established file-processing context.

## 2. Processing Model: Sources, Files, and Keys

A simple mental model:

~~~text
Command-line arguments       --app.timeout=20s
Java system properties       -Dapp.timeout=15s
Environment variables        APP_TIMEOUT=10s
Config data                  application*.yml, .properties, import...
Default values               low-precedence default sources
             |
             v
        Spring Environment
   (ordered PropertySource list)
             |
             v
     Look up each property name
       app.timeout  → 20s
       app.region   → value from declaring source
             |
             v
     @ConfigurationProperties / @Value
             |
             v
      Application bean uses the value
~~~

The diagram illustrates commonly used source types and does not list sources that only appear in web containers, testing, or development environments.

- **`PropertySource`** is a source containing name–value pairs. `Environment` retrieves values through this list of sources.
- **Config data** is the mechanism Spring Boot uses to locate, load, and organize the contents of configuration files and sources supported via `spring.config.import`.
- **Binding** is the step that converts resolved values into Java types, such as `Duration`, `boolean`, a record, or a `@ConfigurationProperties` group.

Which file is loaded and which property "wins" are two questions that must be evaluated at the right layer.

## 3. Property Source Precedence

### 3.1. Common Sources

In **a typical Spring Boot application run**, you can remember this approximate order from **highest to lowest precedence**:

| Precedence | Source | Example |
| --- | --- | --- |
| High | Spring Boot command-line arguments | `--server.port=9090` |
| | Spring Boot-supported JSON configuration | `SPRING_APPLICATION_JSON` |
| | Java system properties | `-Dserver.port=8089` |
| | OS environment variables | `SERVER_PORT=8088` |
| | Config data | `application.yml`, profile-specific files, external JAR files, imported files |
| | `@PropertySource` on `@Configuration` classes | Properties files declared by the application |
| Low | Default properties set by the application | `SpringApplication.setDefaultProperties(...)` |

This is an **abridged table** for learning how to resolve conflicts between common sources, not a complete list of every `PropertySource` in Spring Boot. For example, servlet environments, Spring Boot Test, and Devtools can add sources with their own precedence positions. `@PropertySource` precedence also has a limitation because it is added while the application context is refreshing, which is too late for settings that must be read very early, such as `logging.*` or `spring.main.*`.

A direct example:

~~~yaml
# application.yml
server:
  port: 8080
~~~

~~~bash
# Environment variable:
SERVER_PORT=9090

# Application argument:
java -jar demo.jar --server.port=9191
~~~

When all three values coexist, the effective port is **`9191`**. Omit the command-line argument and the value becomes **`9090`**; also omit the environment variable and **`8080`** remains.

From this example, you **cannot** infer that all values in the config file are wiped out by environment variables. Only overlapping property names compete.

### 3.2. Precedence Is a Value-Selection Rule

Suppose:

~~~yaml
# application.yml
app:
  timeout: 3s
  region: vn
  retry-count: 2
~~~

And there is an environment variable `APP_TIMEOUT=10s`. When queried:

| Property | Effective Value | Reason |
| --- | --- | --- |
| `app.timeout` | `10s` | Environment variable outranks config data |
| `app.region` | `vn` | Environment variable does not declare this key |
| `app.retry-count` | `2` | No higher source overrides it |

The same mechanism operates when two config files have different precedence. **The application does not pick a single "winning file" and discard all remaining files.**

## 4. Config Data Loading Order

Inside **config data**, Spring Boot applies specific rules for file locations, profiles, YAML documents, and imported configuration.

### 4.1. Default Order of Configuration Files

With default search locations and the standard config name `application`, common config data groups are ordered from **lowest to highest**:

1. `application.properties` or `application.yml` packaged **inside the JAR**.
2. `application-{profile}.properties` or `application-{profile}.yml` packaged **inside the JAR**.
3. `application.properties` or `application.yml` located **outside the JAR** in a searched location.
4. `application-{profile}.properties` or `application-{profile}.yml` located **outside the JAR**.

For example, `./config/application-prod.yml` is a common external file when the application runs from a directory containing a `config/` subdirectory. Relative paths depend on the process **working directory**.

Two easily missed consequences:

- Configuration outside the JAR can override profile-specific configuration **packaged inside the JAR**. Having a `-prod` suffix does not automatically mean that file beats every non-profile file.
- Within the same location group, profile-specific configuration can override the general configuration at that location.

The order above describes how **config data in default locations** is processed and does not replace the source precedence table in section 3. For instance, an `--app.timeout=20s` argument can still override `app.timeout` in an external `application-prod.yml`.

### 4.2. Multiple Files or Documents at the Same Location

Spring Boot supports `.properties` and YAML. If both formats are used with **the same name at the same location**, `.properties` takes precedence over YAML by Spring Boot's rules; generally pick one format to avoid subtle conflicts.

A single YAML file can also contain multiple documents separated by `---`. Within the same file, a document activated later can override matching properties from an earlier document.

~~~yaml
# application.yml — shared document
app:
  timeout: 3s
  retry-count: 2

---
spring:
  config:
    activate:
      on-profile: prod
app:
  timeout: 5s
~~~

Run the application with:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

Assuming no higher-precedence source, the result is `app.timeout=5s` and `app.retry-count=2`. The profile document only defines `timeout`, so `retry-count` continues coming from the shared document.

### 4.3. Order of Multiple Active Profiles

When activating multiple profiles, profile order matters if they declare the same property. With profile files at the same location:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,region-apac
~~~

Suppose `application-prod.yml` declares `app.timeout=5s` and `application-region-apac.yml` declares `app.timeout=7s`. In this common combination, **the later profile wins** for overlapping properties, so `app.timeout` becomes `7s` if no other higher-precedence source exists.

When configuration has multiple location groups or complex imports, you must evaluate location groups, document order, and profile order together; do not blindly apply "later profile always wins" while ignoring those other factors.

## 5. Complete Example: Four Files, One Result per Key

Suppose CI builds a JAR containing two files:

**File 1 — `classpath:/application.yml`**, general config inside the JAR:

~~~yaml
app:
  region: vn
  timeout: 3s
  retry-count: 2
  banner: welcome
~~~

**File 2 — `classpath:/application-prod.yml`**, profile config inside the JAR:

~~~yaml
app:
  timeout: 5s
  retry-count: 3
~~~

Outside the JAR, the working directory contains:

**File 3 — `./config/application.yml`**, external general config:

~~~yaml
app:
  region: apac
  timeout: 8s
~~~

**File 4 — `./config/application-prod.yml`**, external profile config:

~~~yaml
app:
  retry-count: 5
  feature:
    enabled: true
~~~

Activate the `prod` profile:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

Assuming no other source supplies these keys, the effective values are:

| Key | Final Value | Winning Source and Explanation |
| --- | --- | --- |
| `app.region` | `apac` | File 3 overrides `vn` from File 1 |
| `app.timeout` | `8s` | External File 3 overrides `5s` in File 2 and `3s` in File 1 |
| `app.retry-count` | `5` | File 4 overrides `3` in File 2 and `2` in File 1 |
| `app.banner` | `welcome` | Only File 1 declares it, so that value remains in use |
| `app.feature.enabled` | `true` | File 4 supplies the value for this key |

**Key point of the example:** `app.timeout` comes from an external file **without a profile suffix**, even though `application-prod.yml` exists inside the JAR. Which value wins depends on **config data source precedence**, not just the filename.

Next, set an environment variable:

~~~bash
APP_TIMEOUT=12s java -jar demo.jar --spring.profiles.active=prod
~~~

`app.timeout` becomes `12s`, while `app.region=apac`, `app.retry-count=5`, and the other properties remain unchanged.

Add an argument:

~~~bash
APP_TIMEOUT=12s java -jar demo.jar --spring.profiles.active=prod --app.timeout=15s
~~~

Now `app.timeout=15s`. This is the effect of **precedence among command-line, environment variable, and config data sources**, not a change in the loading order of the four files.

The inline environment variable assignment above uses Unix shell syntax. In PowerShell, you can set `$env:APP_TIMEOUT = "12s"` before running the application.

## 6. What Is Key-Level Override?

### 6.1. A Higher Source Only Replaces Values It Provides

A file that does not declare `app.region` has no reason to remove `app.region` from a lower-precedence file. Conversely, if a higher-precedence file declares `app.region`, that value is used for this key.

~~~text
Lower-precedence source        Higher-precedence source
app.region = vn                app.timeout = 10s
app.timeout = 3s               app.retry-count = 4
app.retry-count = 2
          \                      /
           \                    /
             Effective result
             app.region = vn
             app.timeout = 10s
             app.retry-count = 4
~~~

Properties like `app.timeout` and `app.retry-count` are resolved independently. In standard binding, a nested structured property can also receive fields from multiple sources:

~~~yaml
# Lower source
app:
  client:
    base-url: https://sandbox.example.test
    timeout: 3s
    enabled: false
~~~

~~~yaml
# Higher source
app:
  client:
    timeout: 10s
~~~

The result uses `base-url` and `enabled` from the lower source, but `timeout=10s` from the higher source.

### 6.2. Special Attention When Binding Lists and Maps

The phrase "key-level override" must be understood accurately at the **property lookup** layer. When binding multiple properties into collections via `@ConfigurationProperties`, Spring Boot follows specific rules:

- **List:** a list declared in a higher-precedence source **replaces the list** from a lower-precedence source; elements are not merged automatically.
- **Map:** entries can be aggregated from multiple sources; for the same map key, the value from the higher-precedence source overrides.

Example with a list:

~~~yaml
# Lower source
app:
  servers:
    - alpha
    - beta
~~~

~~~yaml
# Higher source
app:
  servers:
    - gamma
~~~

When binding `app.servers` to `List<String>`, the result is **`[gamma]`**, not `[gamma, beta]` and not `[alpha, beta, gamma]`.

Example with a map:

~~~yaml
# Lower source
app:
  labels:
    region: vn
    owner: team-a
~~~

~~~yaml
# Higher source
app:
  labels:
    owner: team-b
~~~

When bound to `Map<String, String>`, the result can include `region=vn` and `owner=team-b`. Therefore, do not apply a single "merge everything" rule to every Java data structure.

### 6.3. An Absent Key and a Key with an Empty Value Are Not the Same

A property **undeclared** in a higher source allows lookup to continue down to lower sources. A property **declared with an empty string** may be treated as having a value, causing binding to `int`, `Duration`, or a required type to fail. Therefore inspect **what value a source supplied**, not merely whether a file contains or lacks the property name.

Similarly, a placeholder property like `${APP_TIMEOUT:5s}` has substitution logic when evaluated. Do not deduce the final value solely from source text without evaluating actual sources and placeholders.

## 7. How Does `spring.config.import` Relate to Loading Order?

A config data file can declare additional configuration sources:

~~~yaml
# application.yml
spring:
  config:
    import: optional:file:./secrets/extra.yml

app:
  timeout: 3s
~~~

Suppose `./secrets/extra.yml` contains:

~~~yaml
app:
  timeout: 8s
  region: vn
~~~

For config data in this example, the imported document has **higher precedence than the document declaring the import**, so `app.timeout=8s`; `app.region=vn` is also present in the result.

This does not mean the imported file beats sources at other precedence tiers such as command-line arguments. If you add `--app.timeout=20s`, the property's effective value can still be `20s`.

Points to remember:

- `spring.config.import` declares **additional configuration data sources**, not a Java annotation.
- `optional:` allows a location not to exist without causing the application to fail due to a missing location; omitting `optional:` when a required location is missing can fail startup.
- With multiple imports, declaration order matters; later imports can override earlier imports when both declare the same key.
- Import position and active profiles can affect processing order. Do not look only at the timestamp of a "Loaded" log line to conclude which property wins.

## 8. `spring.config.location` and `spring.config.additional-location`

When running in an environment with custom directory layouts, Spring Boot lets you specify where to search for config data:

- `spring.config.location`: specifies locations used to search for config data and **replaces the default search location list**.
- `spring.config.additional-location`: **adds** locations to the default locations; additional locations listed later can override matching keys from earlier ones.

Example:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:/etc/demo/
~~~

If `/etc/demo/application.yml` exists and contains `app.timeout=9s`, this configuration can override `app.timeout` in default config data files; properties not declared there still come from other sources.

A few practical points:

1. When specifying a **directory**, end the path with `/` so Spring Boot searches for `application.*` files by convention.
2. When a required location is not found, startup can fail. Use `optional:` if missing the location is valid.
3. `spring.config.location`, `spring.config.additional-location`, and `spring.config.name` must be known **very early** to determine which files to load. Typically configure them via environment variables, Java system properties, or command-line arguments.
4. When passing multiple locations, **location groups** and separators also matter. Spring Boot uses commas to separate location groups and semicolons to group locations at the same level. Different groups can lead to different profile-specific override orders. In complex setups, inspect the full list of locations/groups used rather than just filenames.

These settings control **finding and processing config data**; they do not invert the overall precedence order of `Environment`.

## 9. How to Determine the Final Value in a Real Scenario

When a property such as `app.timeout` differs from expectations, check in sequence:

1. **Write down the exact property name to look up:** `app.timeout`, not confusing it with `spring.mvc.async.request-timeout` or another similarly named property.
2. **Check high-precedence sources:** `--app.timeout` argument, `SPRING_APPLICATION_JSON`, Java system property `-Dapp.timeout`, environment variable `APP_TIMEOUT`; in tests also check test-only sources.
3. **Identify participating config data files:** files in JAR, files in working directory/`config/`, any `spring.config.location` or `spring.config.additional-location`, active profiles, and imported files.
4. **Evaluate order within config data:** packaged/external, profile-specific, YAML documents, imports, and location groups.
5. **Resolve by exact key:** the highest-precedence source that actually defines the property supplies the value for standard lookups; for `List`/`Map`, also check binding rules.
6. **Verify binding output:** did the property convert to the right Java type, did placeholders or validation affect it, and when was the bean initialized?

If Spring Boot Actuator is enabled with appropriate access control, `/actuator/env` or `/actuator/env/{name}` can help inspect property sources and value origins; `/actuator/configprops` helps inspect bound configuration. These endpoints must be secured and mask sensitive information, especially passwords, tokens, and secrets.

In custom application code, you can read the value via `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigPrinter {
    public ConfigPrinter(Environment environment) {
        String timeout = environment.getProperty("app.timeout");
        System.out.println("Effective app.timeout = " + timeout);
    }
}
~~~

This snippet only illustrates reading a **final value**. In real applications, do not print secrets to stdout or logs. When you need to verify a property's **origin**, inspect the corresponding property source through a controlled observability channel.

## 10. Common Misconceptions

| Incorrect or Incomplete Statement | Accurate Understanding |
| --- | --- |
| "Whichever file loads last wins everything." | You must consider which precedence tier that file belongs to, which profiles and imports participate, and compare per property. |
| "`application-prod.yml` always beats `application.yml`." | Only true within the matching context; a non-profile file **outside the JAR** can beat a profile file **inside the JAR**. |
| "If an environment variable exists, the entire YAML file is ignored." | Only properties supplied by environment variables override; other keys can still come from YAML. |
| "Declaring one field in an object wipes out all other fields." | Standard nested properties are resolved individually per key; collection binding has its own rules. |
| "Both lists and maps automatically merge across sources." | Lists are normally replaced wholesale during binding; maps can aggregate entries and override matching keys. |
| "Just creating `application-prod.yml` automatically activates the `prod` profile." | Profiles must be activated via an appropriate mechanism, such as `--spring.profiles.active=prod`. |
| "`spring.config.location` just adds one directory." | It replaces the default location list; to add locations, use `spring.config.additional-location`. |
| "Editing an external file makes already-running beans immediately pick up the new value." | Most values are bound at startup; a restart or a dedicated refresh mechanism is usually needed. |
| "Calling `Environment.getProperty(...)` tells you the source file." | It returns the effective value; to find the source, inspect the corresponding property source/origin. |

## 11. Reasoning Exercise

Given three configuration layers:

~~~yaml
# Inside JAR: application.yml
app:
  host: local
  timeout: 2s
  retries: 1
~~~

~~~yaml
# Outside JAR: ./config/application.yml
app:
  host: remote
  retries: 3
~~~

~~~bash
APP_TIMEOUT=8s java -jar demo.jar --app.retries=5
~~~

No other source defines these properties. Determine the effective values before checking the solution.

**Solution:**

- `app.host=remote` because the external file outside the JAR supplies `host` at higher precedence than the file inside the JAR.
- `app.timeout=8s` because the environment variable overrides `2s` from the file inside the JAR.
- `app.retries=5` because the command-line argument overrides both `3` in the external file and `1` in the packaged file.

This exercise shows why you must separate three questions: **which source has higher precedence**, **in what order config data files are processed**, and **which keys exist in each source**.

## 12. Key Takeaways

- **Property source precedence** is the rule across `PropertySource` types, e.g., CLI arguments generally override environment variables and config data.
- **Config data loading order** is the rule within the config data system: packaged/external locations, profile-specific files, YAML documents, imports, and location groups.
- **Key-level override** means only properties with values in a higher-precedence source are replaced; undeclared properties can still come from lower-precedence sources. For `List` and `Map`, evaluate how `@ConfigurationProperties` binding works separately.

When troubleshooting, write down **the property name, the sources declaring it, precedence among sources, and the final value**. That is a reliable way to explain why Spring Boot uses a particular configuration.

### References

- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Framework Reference — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
