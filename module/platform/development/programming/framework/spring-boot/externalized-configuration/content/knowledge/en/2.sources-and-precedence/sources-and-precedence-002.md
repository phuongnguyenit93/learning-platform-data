# Full PropertySource Precedence Order in Spring Boot 3.3

## 1. Core Principle

Spring Boot 3.3 builds the `Environment` from multiple `PropertySource` instances: default properties, `application.properties`/`application.yaml` files, environment variables, JVM system properties, command-line arguments, and several sources specific to web/test/devtools. When **the same key** appears in multiple sources, the value from the **highest-precedence** source is used. A source that does not declare that key does not erase the value from a lower source.

**Convention for the table below:** **1 = lowest precedence**, **15 = highest precedence**; sources in lower rows can override sources in upper rows. This is the official order described in the *Externalized Configuration* documentation of **Spring Boot 3.3**, for the default sources configured by Spring Boot. Not every application has all 15 sources: Servlet/JNDI, test, and Devtools sources only exist when the corresponding environment supports them.

> Distinguish two perspectives: the documentation orders from **low → high**, whereas when iterating over `ConfigurableEnvironment#getPropertySources()`, sources are typically listed from **high → low** to find the first matching value. Do not confuse the direction of the two lists.

## 2. All 15 Precedence Levels

| Level (low → high) | PropertySource | Meaning and Applicability |
| ---: | --- | --- |
| **1** | **Default properties** | Map of default values passed by startup code via `SpringApplication.setDefaultProperties(Map)`. This is the final fallback layer. |
| **2** | **`@PropertySource` on `@Configuration` classes** | Loads properties files via Spring's annotation. This source is only added while `ApplicationContext` is refreshing, so it may be **too late** for keys read earlier, such as `logging.*` and `spring.main.*`. |
| **3** | **Config Data** | `application.properties`/`application.yaml`, profile-specific variants, files outside the JAR, data imported via `spring.config.import`, and supported Config Data loaders. Has an **internal precedence order within level 3**, covered in the next section. |
| **4** | **`RandomValuePropertySource`** | Supplies values for `random.*` expressions, such as `random.uuid`, `random.int`; not a general override source for arbitrary application keys. |
| **5** | **OS environment variables** | For example, `SERVER_PORT=8082` corresponds to `server.port` in the typical case. Commonly used in containers/Kubernetes/CI. |
| **6** | **Java System properties** | Keys from `System.getProperties()`, such as `-Dserver.port=8083` passed to the JVM. Higher than OS environment variables in Boot 3.3's default order. |
| **7** | **JNDI attributes** | Values in `java:comp/env` when running in an environment with JNDI support. Absent in many typical executable JAR applications. |
| **8** | **`ServletContext` init parameters** | `ServletContext`-level initialization parameters in a Servlet application. |
| **9** | **`ServletConfig` init parameters** | Servlet-level initialization parameters, higher than `ServletContext` init params. |
| **10** | **`SPRING_APPLICATION_JSON`** | Inline configuration JSON passed via an environment variable, JVM system property, `spring.application.json` command-line argument, or JNDI. JSON is parsed into hierarchical keys. |
| **11** | **Command-line arguments** | `--key=value` options converted into properties by `SpringApplication`. By default, they rank higher than the runtime configuration sources above. |
| **12** | **Test annotation `properties`** | For example, `@SpringBootTest(properties = "...")` or Spring Boot test slice annotations. Only used in a test context. |
| **13** | **`@DynamicPropertySource` in tests** | Dynamic values registered by tests, often used to obtain addresses/ports from Testcontainers. |
| **14** | **`@TestPropertySource` in tests** | Sources or properties specific to Spring Test. According to the Spring Boot 3.3 list, higher than items 12 and 13. |
| **15** | **Devtools global settings** | Global Devtools configuration properties in `$HOME/.config/spring-boot`, **only when Devtools is active**. This is the highest level in the official list. |

A mnemonic for common application runs: **defaults < @PropertySource < Config Data < random.* < OS environment < JVM -D < JNDI < ServletContext < ServletConfig < JSON < --command-line**. When testing or running with Devtools, layers 12–15 must also be accounted for. Here `<` means "lower precedence than".

**Example of programmatically setting default values (level 1):**

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setDefaultProperties(Map.of(
    "server.port", "8080",
    "app.mode", "default"
));
app.run(args);
```

Note: in real-world environments, additional sources may appear from libraries, Spring Cloud, or custom application code inserted into `Environment`. The 15-tier table describes **Spring Boot 3.3's default order**, not a guarantee that every custom `PropertySource` must sit at a fixed position.

## 3. Precedence **Inside Config Data** (Level 3)

### 3.1. Four Groups of Configuration Files, from Low to High

Spring Boot 3.3 evaluates an application's Config Data files in this general order:

1. **Inside JAR, non-profile-specific:** `application.properties` or YAML variants.
2. **Inside JAR, profile-specific:** `application-{profile}.properties` or YAML.
3. **Outside JAR, non-profile-specific:** `application.properties`/YAML files from external locations.
4. **Outside JAR, profile-specific:** `application-{profile}.properties`/YAML files from external locations.

A later group can override an earlier group. For example, if the `prod` profile is active, `./config/application-prod.properties` can override `src/main/resources/application-prod.properties` packaged inside the JAR.

In the **same location**, if both `application.properties` and `application.yaml`/`application.yml` exist simultaneously, **`.properties` takes precedence**. Use one format consistently to avoid unpredictable configuration.

### 3.2. Default Search Locations

When search paths are not overridden, typical configuration locations are evaluated from lowest to highest precedence as follows:

1. `classpath:/` (classpath root).
2. `classpath:/config/`.
3. `file:./` (current working directory).
4. `file:./config/`.
5. `file:./config/*/` (direct subdirectories under `config/`).

`file:./` is resolved relative to the **process working directory**, not by default to the directory containing the JAR file. The `config/*/` wildcard matches only one level of subdirectories; matching wildcard paths are ordered alphabetically based on their absolute paths. With multiple files and profiles, the result is also governed by **location group** rules.

### 3.3. Profiles and Location Groups

- `application-prod.properties` applies when the `prod` profile is active; profile-specific files can override non-profile-specific files.
- If `spring.profiles.active=prod,live`, within the same **location group**, the later profile (`live`) overrides the earlier profile (`prod`) when both files declare the same key.
- With no active profile, Spring Boot uses the default profile group (named `default` by default); `application-default.properties` can be loaded.
- In `spring.config.location`, commas `,` separate **location groups** in precedence order; semicolons `;` group multiple locations at the **same level**. Grouping changes processing order when multiple profiles are active.

For example, `spring.config.location=classpath:/cfg/,classpath:/ext/` lets all configuration from `ext` override `cfg` by location group, whereas `spring.config.location=classpath:/cfg/;classpath:/ext/` processes `cfg` and `ext` as one group and applies profile ordering within that group. Therefore, you cannot conclude "a later profile wins across all locations" without looking at how locations are grouped.

### 3.4. Replacing, Adding, and Importing Configuration Sources

| Mechanism | Impact on Precedence |
| --- | --- |
| `spring.config.name=myapp` | Selects basename `myapp` instead of `application` during default discovery. |
| `spring.config.location=...` | **Replaces** the default locations list. Locations listed later can override earlier locations. |
| `spring.config.additional-location=...` | **Adds** locations after the default locations; data in additional locations can override default Config Data. |
| `spring.config.import=...` | Imports Config Data alongside the declaring document; **imported data takes precedence over the document declaring the import**. With multiple imports, later imports take precedence over earlier imports. |
| `optional:` | Allows a specified location to be missing without causing application startup to fail because of that missing location. |
| Multi-document files | Within an `application.yaml` split by `---`, or `application.properties` split by `#---`, later documents can override earlier documents if both are activated. |

Example of an `application.properties` file:

```properties
app.name=service-default
spring.config.import=optional:file:./local-overrides.properties
```

If `./local-overrides.properties` exists and contains `app.name=service-local`, the final value within Config Data is `service-local`, unless another higher-precedence Config Data overrides it. Whether the import is declared at the top or bottom of the file, it follows the rule above. Imported files can themselves have matching profile-specific variants.

**Timing note:** `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are read **very early** so Boot knows which files to load. Therefore, pass them via OS environment, JVM `-D`, or command line; do not rely on a late-added `@PropertySource` to decide Config Data loading paths.

## 4. Conflict Example: Which Source Wins?

Suppose the application declares `server.port` in all of the following sources:

| Source | Value | Precedence Level |
| --- | ---: | ---: |
| `application.properties` packaged in JAR | `8080` | 3 |
| `./config/application.properties` outside JAR | `8081` | 3, but higher than JAR file |
| OS environment `SERVER_PORT` | `8082` | 5 |
| JVM system property `-Dserver.port` | `8083` | 6 |
| `SPRING_APPLICATION_JSON` with key `server.port` | `8084` | 10 |
| Command-line `--server.port` | `8085` | 11 |

On a Unix-style shell, you can express this scenario with the command:

```bash
SERVER_PORT=8082 \
SPRING_APPLICATION_JSON='{"server":{"port":8084}}' \
java -Dserver.port=8083 -jar myapp.jar --server.port=8085
```

**Result: `server.port=8085`** because the `--server.port` argument has the highest precedence among the **present** sources. If you omit that argument, JSON `8084` wins; if you also omit JSON, JVM `8083` wins; followed by environment `8082`, external file `8081`, and packaged file `8080`. This example assumes no test/devtools or custom source supplies `server.port` at a higher level.

You can disable adding command-line properties with:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
```

Then `--server.port=...` no longer acts as a `PropertySource` via this mechanism.

### JSON and Null Values

All of the following forms can supply `spring.application.json`/`SPRING_APPLICATION_JSON`:

```bash
SPRING_APPLICATION_JSON='{"app":{"mode":"json"}}' java -jar myapp.jar
java -Dspring.application.json='{"app":{"mode":"json"}}' -jar myapp.jar
java -jar myapp.jar --spring.application.json='{"app":{"mode":"json"}}'
```

JSON is flattened, e.g., `{"app":{"mode":"json"}}` becomes `app.mode=json`. **JSON null cannot be used to "delete" lower-precedence configuration**: even if the JSON source contains a key with a null value, `PropertySourcesPropertyResolver` treats null as missing a value.

## 5. Easily Confused Cases

### 5.1. OS Environment and Java System Properties

`SERVER_PORT` (OS environment, level 5) and `-Dserver.port=9000` (JVM, level 6) are **two different sources**. If both are provided, the JVM system property wins for the same key. For names with dots or dashes, `@ConfigurationProperties` relaxed binding rules typically map to uppercase environment variable style with underscores; for example `server.port` → `SERVER_PORT` and `spring.main.log-startup-info` → `SPRING_MAIN_LOGSTARTUPINFO` (dashes removed).

Do not assume every direct lookup expression or arbitrary custom property name maps identically. Prefer naming properties in canonical `lowercase.kebab-case` and verify the received value via `Environment` or `@ConfigurationProperties`.

### 5.2. `@PropertySource` Is Not Config Data

`@PropertySource("classpath:custom.properties")` is at level **2**, lower than `application.properties` at level **3**. Furthermore, it only appears during context refresh; properties configuring the logging system or `SpringApplication` behavior may have already been read earlier. Spring Framework also does not support YAML out of the box via `@PropertySource` by default like Boot's Config Data mechanism does.

### 5.3. `RandomValuePropertySource` Does Not Win Every Key

`random.uuid`, `random.int`, and `random.long` are special keys; `RandomValuePropertySource` sitting at level 4 **does not mean** it supplies or overrides `server.port`/`app.mode`. If the application references `app.token=${random.uuid}` from Config Data, the placeholder value is resolved through `Environment` when used.

### 5.4. Only Tests Have Levels 12–14

According to Spring Boot 3.3's precedence table, in a test context:

```java
@SpringBootTest(properties = "demo.flag=from-boot-test")
@TestPropertySource(properties = "demo.flag=from-test-property-source")
class ExampleTest {

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("demo.flag", () -> "from-dynamic-property-source");
    }
}
```

Following the exact order 12 → 13 → 14 in the Boot 3.3 documentation, `@TestPropertySource` is the source that comes later. These mechanisms **do not appear automatically in production applications**. In real tests, if there is a context hierarchy, custom initializers, or libraries adding other sources, inspect `Environment` directly.

### 5.5. Devtools Global Settings

Level 15 applies to global Devtools properties when Devtools is active, **not** an arbitrary `application.properties` file placed in `$HOME/.config/spring-boot`. These values can cause differences between a developer's machine and the real runtime environment; when investigating a property that is only wrong on a dev machine, check this source as well.

## 6. Inspecting the Actual Order at Runtime

To diagnose a key, you can iterate over `ConfigurableEnvironment#getPropertySources()`. The following example **only prints the names of sources containing the key**, avoiding printing sensitive data from the entire Environment:

```java
@Configuration
class PropertyDiagnostics {

    @Bean
    ApplicationRunner showPropertyOrigin(ConfigurableEnvironment env) {
        return args -> {
            String key = "server.port";
            env.getPropertySources().forEach(source -> {
                if (source.containsProperty(key)) {
                    System.out.println("Contains " + key + ": " + source.getName());
                }
            });
            System.out.println("Effective " + key + ": " + env.getProperty(key));
        };
    }
}
```

Iterated `PropertySource` instances can have different names depending on how files were loaded, and **higher-precedence sources are checked first**. This code inspects the result after the application has initialized; it cannot change settings that were read early, such as logging.

If Spring Boot Actuator is enabled, `/actuator/env` or `/actuator/env/server.port` can help inspect properties, effective values, and origins (depending on configuration). This endpoint **is not exposed publicly over HTTP by default**; only enable and secure it when needed for diagnostics, keeping in mind that many values are masked to prevent leaking secrets.

### Process for Determining a Configuration Value

1. Identify the exact property name and which sources actually declare it, noting environment variable name mapping rules.
2. Rank the present sources according to the **15 tiers** in section 2; the higher-precedence source wins for the same key.
3. If the sources are all Config Data, further evaluate **in-JAR/external files, profiles, location groups, imports, and multi-document files** in section 3.
4. If the result still differs from expectations, inspect the actual `PropertySource` instances in `Environment` and any sources added by libraries or application code.

## 7. References

- Spring Boot **3.3** Reference Guide – **Externalized Configuration**, especially *PropertySource Order*, *Config Data Files*, *External Application Properties*, *Profile Specific Files*, and *Importing Additional Data*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework – `PropertySource`, `Environment`, and `ConfigurableEnvironment`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html

**Key takeaway:** In Spring Boot 3.3, **sources listed later in the 15-level list have higher precedence**, but Config Data also has its own internal sub-order. To explain a specific value, you must consider **which sources are actually present, when they load, and the order within the same group**.
