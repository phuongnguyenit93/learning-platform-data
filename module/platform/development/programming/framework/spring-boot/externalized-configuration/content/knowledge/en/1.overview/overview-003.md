# Concept Map: Properties, Property Sources, Environment, Profiles, and Type-Safe Binding

In Spring Boot, *externalized configuration* is the practice of moving values that vary by runtime environment out of Java code: service URLs, HTTP ports, timeouts, connection limits, feature flags, and operational settings. The goal of this lesson is to trace **the path of a configuration value** from where it is declared to where the application uses it, while clearly distinguishing five concepts that are often mixed up: *property*, *property source*, *Environment*, *profile*, and *type-safe binding*.

## 1. Overall Map

~~~mermaid
flowchart LR
    A["Configuration sources<br/>application.yml, environment variables,<br/>system properties, command-line..."] --> B["PropertySources<br/>ordered by precedence"]
    P["Active profiles<br/>dev, test, prod..."] --> C["Config Data<br/>selects matching config documents"]
    C --> B
    B --> E["Spring Environment<br/>looks up keys and effective values"]
    E --> V["Environment.getProperty()<br/>@Value"]
    E --> D["Spring Boot Binder<br/>@ConfigurationProperties"]
    D --> O["Typed Java objects<br/>Duration, URI, boolean..."]
    V --> U["Beans / application logic"]
    O --> U
~~~

You can read this diagram in one sentence: **multiple sources supply the same property name; profiles help decide which configuration data is loaded; Environment provides the effective value; the application reads it directly or binds it into a typed object**.

| Concept | What Question Does It Answer? | Example |
| --- | --- | --- |
| Property | What is the setting named? | `app.client.connect-timeout` |
| Property source | Where is the value declared? | `application.yml`, environment variable, `--app.client.connect-timeout=1s` |
| Environment | Given the current startup state, what value does looking up the key return? | `environment.getProperty("app.client.connect-timeout")` |
| Profile | Which configuration/beans are activated for this runtime context? | `dev`, `prod` |
| Binding | How are string keys converted into a Java model? | `@ConfigurationProperties` → `ClientProperties` |

A *property* is not synonymous with a YAML line: the same key can appear in multiple sources. A *profile* is also not an independent configuration store: it helps select configuration documents and beans for the runtime context.

## 2. A Property Is a Logical Name; a Property Source Is Where Values Live

Example of a group of settings for an HTTP client:

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

The corresponding logical keys are `app.client.base-url`, `app.client.connect-timeout`, and `app.client.max-retries`. They express the *meaning* of the settings, without forcing the application to fetch values from a YAML file. The same key can be declared by another source:

~~~bash
java -jar demo.jar --app.client.connect-timeout=200ms
~~~

Spring Boot assembles `PropertySource` instances into a lookup order. When multiple sources contain the same key, **the higher-precedence source determines the effective value**. Under normal execution, a `--key=value` command-line argument can override configuration from `application.yml`. However, do not try to infer the entire precedence order solely from file locations: external configuration, `spring.config.import`, test properties, and how the application is launched can also affect the outcome.

Some common source categories:

- **Config Data:** `application.properties`, `application.yml`, profile-specific documents, external files, or imported documents.
- **OS environment variables:** well suited for deployment, container, and CI/CD configuration.
- **Java system properties:** for example `-Dapp.client.max-retries=4`.
- **Command-line arguments:** for example `--app.client.max-retries=5`.
- **Application/test-supplied sources:** used for dynamic configuration or isolating test scenarios.

For environment variables used in relaxed binding, a canonical name such as `app.client.max-retries` commonly takes the form `APP_CLIENT_MAXRETRIES`: replace dots with `_`, remove hyphens, and convert to uppercase. Do not assume that every arbitrary placement of underscores is equivalent.

## 3. Environment: Where Effective Values Are Looked Up

Spring Framework provides `org.springframework.core.env.Environment`. Spring Boot prepares `Environment` from configuration sources during startup. To application code, this is a unified access point: code does not need to know whether the final value came from YAML, an environment variable, or the command line.

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ClientSettingsReader {
    private final Environment environment;

    public ClientSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public void printNonSensitiveSettings() {
        String url = environment.getProperty("app.client.base-url");
        Duration timeout = environment.getProperty(
            "app.client.connect-timeout", Duration.class);
        String[] profiles = environment.getActiveProfiles();

        System.out.println("URL = " + url);
        System.out.println("Timeout = " + timeout);
        System.out.println("Active profile count = " + profiles.length);
    }
}
~~~

Key points to remember:

1. `getProperty(key)` reads a property as a string; `getProperty(key, Type.class)` requests conversion to the target type when an appropriate converter exists.
2. A missing key can yield `null`; overloads with a default value or `getRequiredProperty` express expectations more clearly.
3. `getActiveProfiles()` reports the currently active profiles; it does not tell you which file a key's value came from.
4. `Environment` reflects the configuration snapshot of the running application. Editing a configuration file on disk after startup **does not automatically re-bind beans**; dynamic reload mechanisms must be designed separately if the application truly needs them.

You can think of `Environment` as answering **"what is the current value?"**. To ask **"what Java type will it become and is it valid?"**, we need the binding layer.

## 4. Profiles Control Configuration Loading Context and Bean Selection

Suppose there are two files:

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

~~~yaml
# application-dev.yml
app:
  client:
    base-url: http://localhost:8081
    connect-timeout: 1s
~~~

When running:

~~~bash
java -jar demo.jar --spring.profiles.active=dev
~~~

Spring Boot can load both the base configuration and the `dev`-specific data. In this example, `app.client.base-url` and `app.client.connect-timeout` take their values from the `dev` configuration, while `app.client.max-retries` continues to use the base value `2`. This is a **per-property override**, not a replacement of the entire `app.client` object.

Besides `application-dev.yml`, a conditional YAML document can also be activated as follows:

~~~yaml
# An additional YAML document inside application.yml
spring:
  config:
    activate:
      on-profile: dev
app:
  client:
    connect-timeout: 1s
~~~

The document above takes effect only when the profile condition matches. Do not place `spring.profiles.active` inside a document that is already gated by `spring.config.activate.on-profile`; deciding active profiles must come from a source permitted to activate profiles.

Distinguish the two roles of profiles:

- **Profiles for Config Data:** select configuration files or documents by environment.
- **Profiles for beans:** `@Profile("dev")` on a configuration class/bean determines whether that bean is registered.

A `@Profile("dev")` bean does not automatically switch every key in `Environment` to a "dev source". Conversely, having `application-dev.yml` does not automatically create or replace beans unless the relevant configuration or bean conditions require it.

When no active profile is specified, Spring has a default profile mechanism. Therefore, check the actual active profiles when diagnosing configuration instead of assuming `dev` or `prod` is always active.

## 5. Value Selection Flow: Three Override Layers in One Example

Keep the files from the previous section, assume the runtime environment defines `APP_CLIENT_CONNECTTIMEOUT=750ms`, and pass an additional argument:

~~~bash
java -jar demo.jar --spring.profiles.active=dev --app.client.connect-timeout=200ms
~~~

| Source | `app.client.connect-timeout` Value | Role |
| --- | --- | --- |
| `application.yml` | `3s` | Base |
| `application-dev.yml` | `1s` | Overrides base when `dev` is active |
| Environment variable | `750ms` | Overrides config data in this scenario |
| Command line | `200ms` | Final effective value in this scenario |

Result: when a bean needs `app.client.connect-timeout`, it receives **200 ms**. If the command-line argument is removed, the result in this example is **750 ms**. If the environment variable is also removed, the result is **1 s** while `dev` remains active.

The main lesson is that profiles only determine **which documents are considered**; source precedence determines **which value wins** when there is a conflict. For imported configuration, external locations, or test-specific rules, verify the exact precedence rather than memorizing a simplified list.

## 6. Type-Safe Binding: From a Group of Keys to a Java Object

When multiple settings belong to the same feature, `@ConfigurationProperties` lets you declare a prefix once and have the Spring Boot Binder construct a strongly typed Java object:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Register it for application component scanning:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

A service can directly inject the bound object:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RemoteClientService {
    private final ClientProperties properties;

    public RemoteClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public void describeTimeout() {
        System.out.println(properties.connectTimeout());
    }
}
~~~

In this example, the Binder retrieves `app.client.base-url`, `app.client.connect-timeout`, and `app.client.max-retries` from the effective configuration and converts them into `URI`, `Duration`, and `int`. For instance, `3s`, `500ms`, and `200ms` can be converted to `Duration` instead of manually parsing strings. `@ConfigurationPropertiesScan` or an equivalent registration such as `@EnableConfigurationProperties(ClientProperties.class)` is required; declaring the record alone does not guarantee a bean is created.

**Relaxed binding** links names by convention. For example, the canonical key `base-url` maps to the Java field `baseUrl`. Similarly `max-retries` ↔ `maxRetries`. Standardize keys declared in files to *kebab-case* to avoid confusion across multiple sources.

Binding also handles nested structures, lists, maps, and specialized types such as `DataSize` when sources are appropriately formatted. For configurations that require input guarantees, you can combine `@Validated` and Jakarta Bean Validation (along with the appropriate validation dependency) to catch invalid values at object creation time rather than waiting for a failure on a later request.

### Reading the Same Key: Environment, @Value, or @ConfigurationProperties?

| Approach | Best Suited When | Points to Note |
| --- | --- | --- |
| `Environment.getProperty(...)` | Dynamic key lookup inside a component | Caller must know the key and handle missing values |
| `@Value("${app.client.connect-timeout:3s}")` | One or a few standalone values | Placeholders and defaults get scattered in code if overused |
| `@ConfigurationProperties(prefix = "app.client")` | A cohesive group of configuration settings | Requires bean registration; supports validation and metadata |

`@Value` also supports placeholders and common type conversions. However, for a group of related settings such as HTTP client configuration, type-safe binding is usually clearer and easier to maintain than scattered individual fields.

## 7. Distinguishing Placeholders, Default Values, and Configuration Sources

There are three easily confused constructs:

~~~yaml
# Value defined in a source
app:
  client:
    connect-timeout: 3s
~~~

~~~java
// Fallback value when the placeholder cannot find the key
@Value("${app.client.connect-timeout:5s}")
private Duration timeout;
~~~

~~~java
// Manual lookup with caller-side fallback
String timeoutText = environment.getProperty(
    "app.client.connect-timeout", "5s");
~~~

If `app.client.connect-timeout` exists in a source with applicable precedence, the value from that source is used; a fallback in a placeholder or API call does not override it. **A fallback is not a high-precedence PropertySource**. With `@ConfigurationProperties`, default choices need to be expressed through the corresponding object design or binding conventions, rather than assuming `@Value` syntax applies verbatim to every field.

Be sure to distinguish between a missing value, an empty string, and a malformed value. They can produce different behaviors depending on the target type, binding mechanism, and validation rules.

## 8. Startup Timeline: Who Runs First?

1. **Application receives startup inputs**: command-line arguments, system properties, environment variables, configuration locations.
2. **Spring Boot prepares Environment and processes Config Data**: resolves locations/imports, profiles, applicable files/documents, and property source order.
3. **Bean conditions are evaluated while building ApplicationContext**: `@Profile` and other configuration conditions can inspect Environment.
4. **Binder or injection mechanisms retrieve effective values**: `@ConfigurationProperties`, `@Value`, and code calling `Environment` receive the required settings.
5. **Application operates with the received configuration**: beans use values established during their initialization lifecycle.

This is a conceptual map of the process, not a guarantee that every property is read only at a single instant: a bean can still query `Environment` later. However, structural decisions made during startup—such as selecting Config Data sources or bean creation conditions—are not automatically recomputed when a file changes at runtime.

## 9. How to Trace When a Value Is Not as Expected

Suppose the expected timeout is `1s`, yet the application uses `200ms`. Trace following the same order as the map:

1. **Identify the canonical key** used by code: for example `app.client.connect-timeout`. Check for typos in the prefix or field name.
2. **Identify active profiles** of the running process. Do not infer them from hostname, directory, or environment variables not loaded into the process.
3. **List sources that could declare the key**: base YAML/properties, profile-specific variants, environment variables, system properties, command line, imported data, and test configuration.
4. **Compare precedence order** at startup time to find the winning source, rather than editing the first file you see.
5. **Inspect the binding step**: does the key map properly to the field, can the target type be converted, and does validation report any error?
6. **Check timing of usage**: when was the bean created; are you expecting dynamic reload even though the application does not support it?

In applications with Spring Boot Actuator, the `env` and `configprops` endpoints (if enabled and authorized) can help observe sources or bindings. Maintain access control and sensitive-value masking; never expose endpoints publicly or print passwords/tokens while debugging. Some values are sanitized and therefore will not appear verbatim in diagnostic output.

## 10. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "The application only reads `application.yml`." | It can aggregate multiple sources and follow precedence order. |
| "Activating `dev` guarantees it beats every other config." | Profiles select config data/beans; higher-precedence sources can still override keys. |
| "Adding `application-prod.yml` automatically activates `prod`." | Profile-specific files apply only when that profile is activated via a valid mechanism. |
| "`Environment` and `@ConfigurationProperties` hold two independent sets of values." | The Binder reads from the effective configuration infrastructure and maps into Java objects. |
| "`@Value` and `@ConfigurationProperties` work identically." | One is convenient for individual values; the other models typed configuration groups. |
| "Editing YAML while the app runs updates beans automatically." | A dedicated refresh/rebind mechanism is needed; editing a file does not guarantee runtime updates. |
| "Secret configuration should be hard-coded in source code." | Secrets should come from secure sources appropriate for the deployment environment and be kept out of logs/endpoints. |

## 11. Self-Check Mini Scenarios

**Scenario A.** `application.yml` sets `app.client.max-retries=2`; `application-dev.yml` sets `4`; the app runs with `dev` and `--app.client.max-retries=6`. The effective value in this example is **6** because the command line overrides Config Data.

**Scenario B.** `app.client.base-url` is absent from all sources. `@Value("${app.client.base-url:https://fallback.example.test}")` has a fallback value, whereas a bound configuration requiring a `URI` with a not-null constraint can cause startup to fail when the value is missing. The outcome depends on each consumer's default and validation declarations.

**Scenario C.** `application-prod.yml` exists, but the active profile is `dev`. Content meant only for `prod` is not loaded merely because the file exists. If expected values are missing, check active profiles and winning sources before suspecting the Binder.

**Scenario D.** In Java, the field is named `connectTimeout`; in YAML, the key is `connect-timeout`. This name pair is supported by relaxed binding. However, that does not fix a misspelled prefix: `@ConfigurationProperties(prefix = "app.client")` will not automatically search keys under a different prefix.

## 12. Mental Model Summary

Answer these five questions in order:

1. **Which key?** — Identify the property name, preferring canonical `kebab-case`.
2. **Which sources?** — Find the files, environment variables, system properties, and arguments declaring the key.
3. **Which profiles?** — Know which profile-specific documents and beans are activated.
4. **Which effective value?** — `Environment` reflects the lookup result across property sources.
5. **How does it enter Java?** — Read via `Environment`/`@Value` or bind a group with `@ConfigurationProperties`, then convert types and validate.

Once you distinguish **property name → sources and precedence → profile → Environment → binding → bean**, explaining a configuration value in Spring Boot becomes a verifiable trace chain rather than guessing by filename.
