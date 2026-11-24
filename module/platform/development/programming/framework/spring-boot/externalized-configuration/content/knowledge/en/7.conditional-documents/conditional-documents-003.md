# Processing Order and Overriding Between Documents in the Same File

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Conditional Documents

## 1. Problem to solve

In Spring Boot, an `application.yml` or `application.properties` file can contain **multiple configuration documents**, separated by delimiter markers. Each document describes a group of properties and can have an activation condition, such as a specific profile or cloud platform.

A common question is: if the same key is declared multiple times, where does Spring Boot get the value from? To answer this, you need to determine **which documents are activated**, and then consider **their order of appearance in the same file**.

Core rule:

> Within the same multi-document configuration file, documents are processed in order from top to bottom. When active documents declare the same key, **the document that appears later overrides the value of the document that appeared earlier** within the scope of that file's config data source.

This is a configuration rule for **multiple documents**. It should not be confused with how Java Collections merge, with bean initialization order, or with the precedence order across all different externalized configuration sources.

After this lesson, you can:

- Recognize document boundaries in YAML and properties.
- Distinguish unconditional documents from conditional `spring.config.activate.*` documents.
- Predict the result when earlier and later documents declare the same key.
- Distinguish overrides between documents in the same file from precedence between different configuration **files** or **sources**.
- Verify configuration yourself across profiles, cloud platforms, and duplicate-key scenarios.

## 2. A YAML file with multiple documents

### 2.1. Splitting with `---`

Suppose `src/main/resources/application.yml`:

~~~yaml
app:
  title: "Catalog Service"
  timeout: 10s
  feature-enabled: false

---
app:
  timeout: 20s

---
app:
  feature-enabled: true
~~~

The three sections above are **three YAML documents** in the same file. The `---` line is a document separator. It is not a property name, not a value of `app`, and it does not create three separate files.

When all three documents are active:

| Key | Document 1 | Document 2 | Document 3 | Result |
| --- | --- | --- | --- | --- |
| `app.title` | `Catalog Service` | not declared | not declared | `Catalog Service` |
| `app.timeout` | `10s` | `20s` | not declared | `20s` |
| `app.feature-enabled` | `false` | not declared | `true` | `true` |

A later document overrides **the keys it declares**. Keys not declared in later documents can still retain values from earlier documents.

In this example, the documents do not have `spring.config.activate.*`, so they are evaluated as ordinary configuration documents. The final values can still be overridden by sources outside the file, such as environment variables or command-line arguments.

### 2.2. Not every value overrides the entire object

Example:

~~~yaml
service:
  host: "internal.example"
  port: 8080
---
service:
  port: 9090
~~~

Result when accessing regular properties:

~~~text
service.host = internal.example
service.port = 9090
~~~

The fact that the second document declares `service.port` does not mean `service.host` is automatically deleted just because both sit under `service` in YAML. The processing mechanism flattens simple keys and looks them up by source precedence, rather than replacing a whole Java object while reading YAML.

However, when binding **complex** structures (especially lists), merge rules can differ from scalar properties; a later section distinguishes that case.

## 3. A properties file can also have multiple documents

### 3.1. Boundaries in `application.properties`

Spring Boot supports splitting logical documents in a `.properties` file using a special separator line. Example:

~~~properties
app.title=Catalog Service
app.timeout=10s
app.feature-enabled=false

#---
app.timeout=20s

#---
app.feature-enabled=true
~~~

In the `.properties` example, `#---` is a **separator** recognized by Spring Boot. It is different from an ordinary comment like `# app.timeout=...`.

For the separator to be recognized, use the exact standalone syntax on a single line. In Spring Boot, the separator can use `#---` or `!---`; do not place comment lines using the same prefix right next to the separator in a way that invalidates splitting. For multi-section files, the clearest layout is placing each `#---` on its own line, surrounded by blank lines or data lines as needed.

When all three documents are active, the result is also:

~~~text
app.title = Catalog Service
app.timeout = 20s
app.feature-enabled = true
~~~

**Note:** A multi-document `.properties` file is not the same as repeating the same key within a single logical document. Distinguish between these two situations when reading a file and diagnosing results; this lesson focuses on precedence **between documents**.

### 3.2. YAML and properties share the same precedence idea

| Criterion | YAML | Properties |
| --- | --- | --- |
| Common file extensions | `application.yml`, `application.yaml` | `application.properties` |
| Document separator | `---` | `#---` or `!---` |
| Property declaration | Indented key/value structure | `key=value` |
| Document activation condition | `spring.config.activate.*` | `spring.config.activate.*` |
| Rule when documents are co-active | Later document overrides matching keys from earlier document | Same |

Spring Boot loads multi-document config files through its **Config Data** mechanism. Do not assume all other YAML/properties loading tools implement the same activation mechanism or precedence order. For example, `@PropertySource` and `@TestPropertySource` annotations do not directly support the multi-document property file model the way Spring Boot's config-data loader handles it.

## 4. Default documents and conditional documents

### 4.1. A document activated only for one profile

An application has default configuration, then adds specific values for `dev` and `prod`:

~~~yaml
# application.yml — document 1: unconditional
app:
  display-name: "Catalog"
  log-detail: false
  endpoint: "https://default.example"

---
# document 2: applies only when the dev profile matches
spring:
  config:
    activate:
      on-profile: "dev"

app:
  log-detail: true
  endpoint: "http://localhost:8081"

---
# document 3: applies only when the prod profile matches
spring:
  config:
    activate:
      on-profile: "prod"

app:
  endpoint: "https://catalog.prod.internal"
~~~

When starting up without `dev` or `prod` active, only document 1 contributes the `app.*` properties in the example.

When running:

~~~bash
java -jar catalog.jar --spring.profiles.active=dev
~~~

document 2 is activated, while document 3 does not match. The resulting values are:

~~~text
app.display-name = Catalog
app.log-detail   = true
app.endpoint     = http://localhost:8081
~~~

When running:

~~~bash
java -jar catalog.jar --spring.profiles.active=prod
~~~

document 3 is activated. Result:

~~~text
app.display-name = Catalog
app.log-detail   = false
app.endpoint     = https://catalog.prod.internal
~~~

There are two distinct reasoning steps:

1. **Activation:** which documents satisfy their conditions and are included in the configuration source set?
2. **Precedence:** among active documents in the same file, overlapping keys take the value from the document that appears later.

The `on-profile` condition can be a profile expression, not just a single name. Therefore, do not assume a file with three documents will always apply all three; only documents whose conditions are met in the specific environment are used.

### 4.2. Two documents matching the condition simultaneously

This is the situation that clearly shows the "later document wins" rule:

~~~yaml
app:
  timeout: 5s
  retry-limit: 1

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  timeout: 15s
  retry-limit: 3

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  timeout: 25s
~~~

With the `prod` profile active, both document 2 and 3 satisfy the condition. After evaluating in order of appearance:

~~~text
app.timeout     = 25s
app.retry-limit = 3
~~~

Why? Document 3 overrides `app.timeout` because it shares the key with document 2, but it does not declare `app.retry-limit`, so document 2's value `3` remains usable.

If the `prod` profile is inactive, the two conditional documents do not participate and the application sees the values from document 1 (`5s`, `1`), assuming no higher-precedence configuration source exists.

### 4.3. Multiple profiles active simultaneously

Suppose the document order is as follows:

~~~yaml
app:
  mode: "default"

---
spring:
  config:
    activate:
      on-profile: "team"

app:
  mode: "team"

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  mode: "production"
~~~

If **both `team` and `prod` are active**, both document 2 and document 3 are activated. Within this same file, document 3 appears later, so `app.mode` is `production`.

Do not rely solely on the order profiles are listed on the CLI to explain conflicts **between documents of the same file**. You must look at **whether the condition matches** and **the document's position in the file**. Profile listing order can matter in other situations, such as profile-specific file sources, which is a different precedence layer.

### 4.4. Using compound profile expressions

Example:

~~~yaml
app:
  audit-enabled: false

---
spring:
  config:
    activate:
      on-profile: "prod & !maintenance"

app:
  audit-enabled: true
~~~

The later document only takes effect if the profile expression `prod & !maintenance` is satisfied. Consequently:

- `prod` active, `maintenance` inactive: the later document participates; `app.audit-enabled=true`.
- Both `prod` and `maintenance` active: condition does not match; value from the first document is kept.
- Only `dev` active: condition does not match; value from the first document is kept.

Profile expressions can use negation and combinations according to Spring's supported syntax. Wrap them in YAML quotes so `!` or operators are not misinterpreted as other syntax.

## 5. Conditions based on cloud platform

Besides `spring.config.activate.on-profile`, Spring Boot can activate a document using `spring.config.activate.on-cloud-platform`. Example:

~~~yaml
app:
  storage-path: "./data"
  mode: "local"

---
spring:
  config:
    activate:
      on-cloud-platform: "kubernetes"

app:
  storage-path: "/var/lib/catalog"
  mode: "cluster"
~~~

The second document only takes effect when Spring Boot **detects the environment** as the corresponding cloud platform. Simply putting the value `kubernetes` in YAML does not turn the running environment into Kubernetes.

If the condition matches, the later document can override:

~~~text
app.storage-path = /var/lib/catalog
app.mode         = cluster
~~~

If the condition does not match, the application takes values from the default document, unless another higher-precedence source exists.

A document can declare both a profile condition and a cloud platform condition; in that case, the document's conditions must be met according to their respective activation mechanisms. When diagnosing, inspect **both profile state and cloud environment**, without guessing that a document is active just because one condition matched.

## 6. How Spring Boot decides the final value

You can picture the process in three phases:

~~~text
Read configured config data locations
             |
             v
Split a file into documents in order of appearance
             |
             v
Evaluate activation of each document and related imports
             |
             v
Add active documents to configuration by precedence
             |
             v
Resolve each key when Environment / Binder reads it
~~~

This model helps frame your thinking, though it does **not** mean Boot's entire handling of profiles, imports, and locations is a single simple linear loop; in reality there are multiple configuration sources and distinct config data rules.

Within the scope of one file without complex imports, you can follow this procedure:

1. Split the file by separators into documents 1, 2, 3, ...
2. Record any `on-profile` or `on-cloud-platform` conditions.
3. Determine which documents are active in the startup context.
4. For each key in question, walk through the active documents from top to bottom. Whenever a new declaration of the key is encountered, update the value.
5. After obtaining the value from this file, continue evaluating precedence against **other files, imports, and property sources**.

### 6.1. Prediction table

Consider the file:

~~~yaml
catalog:
  endpoint: "https://base.example"
  timeout: 4s
  feature-a: false

---
spring:
  config:
    activate:
      on-profile: "dev"

catalog:
  endpoint: "http://localhost:9000"
  feature-a: true

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  endpoint: "https://prod.internal"
  timeout: 12s

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  timeout: 20s
~~~

Result table within that file:

| Active profile | `catalog.endpoint` | `catalog.timeout` | `catalog.feature-a` |
| --- | --- | --- | --- |
| Neither `dev` nor `prod` | `https://base.example` | `4s` | `false` |
| `dev` | `http://localhost:9000` | `4s` | `true` |
| `prod` | `https://prod.internal` | `20s` | `false` |
| Both `dev` and `prod` | `https://prod.internal` | `20s` | `true` |

In the last row, the `dev` document still contributes `catalog.feature-a=true` because the later `prod` documents do not redeclare that key. However, `catalog.endpoint` is overridden by the `prod` document, and `catalog.timeout` is overridden once more by the final `prod` document.

The table describes **results within the same file**, without accounting for an external `application-prod.yml`, environment variables, CLI arguments, imports, or custom property sources.

## 7. Do not confuse document precedence with file precedence

Spring Boot has multiple configuration levels:

- Multiple documents within one `application.yml` file.
- Multiple config data files: `application.yml`, `application-prod.yml`, classpath or external filesystem versions.
- Multiple search locations and location groups specified by `spring.config.location` / `spring.config.additional-location`.
- Sources outside config data: OS environment variables, Java system properties, JSON config, command-line arguments, and others.

**Later document beats earlier document** is a rule **within the same file**. It must not be extended to "the last line appearing across all files always wins".

### 7.1. Example of default file and profile-specific file

Suppose:

~~~text
src/main/resources/
├── application.yml
└── application-prod.yml
~~~

`application.yml`:

~~~yaml
catalog:
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  timeout: 10s
~~~

`application-prod.yml`:

~~~yaml
catalog:
  timeout: 30s
~~~

When the `prod` profile is active and both files are loaded under default location order, `application-prod.yml` is a profile-specific source that can take higher precedence than the corresponding data from `application.yml`. The final value in this typical example is `30s`, **not** `10s` just because the conditional document in the first file was written later.

If an external file outside the JAR exists, such as `./config/application-prod.yml`, the result also depends on the order and external/internal location groups along with profile-specific config data rules.

### 7.2. Example where command-line arguments beat all documents in a file

Using the same multi-document `application.yml`:

~~~yaml
catalog:
  timeout: 5s
---
spring:
  config:
    activate:
      on-profile: "prod"
catalog:
  timeout: 10s
~~~

When running:

~~~bash
java -jar catalog.jar \
  --spring.profiles.active=prod \
  --catalog.timeout=60s
~~~

`catalog.timeout` is typically `60s` due to the priority of command-line arguments in Boot's default configuration mechanism. A later document can beat an earlier document **within a file**, but it does not automatically beat higher-precedence sources.

Similarly, Java system properties or environment variables can override config data; the actual winning source depends on the key, environment, and application configuration.

### 7.3. Imports are another precedence layer

A document can declare:

~~~yaml
spring:
  config:
    import: "optional:file:./config/overrides.yml"

catalog:
  timeout: 5s
~~~

Spring Boot treats content brought in by `spring.config.import` as additional configuration documents. Imports have their own precedence rules: an imported document usually takes higher precedence than the document declaring the import, and the order of multiple imports also matters.

You cannot determine the final value solely from a YAML document's position in the original file **when config imports are present**. When handling such cases, identify the imported documents, their locations, and the actual precedence order.

## 8. Overriding scalars, maps, and lists: key distinctions

### 8.1. Scalar values: later key overrides earlier key

~~~yaml
app:
  mode: basic
---
app:
  mode: advanced
~~~

Result: `app.mode=advanced` when both documents are loaded. This is the most direct example of the later-document-wins rule.

### 8.2. Maps: entries can be combined by key name

Example bound via `@ConfigurationProperties`:

~~~yaml
catalog:
  headers:
    source: default
    region: global

---
catalog:
  headers:
    region: asia
    channel: mobile
~~~

With a typical map structure, entries can be merged key-by-key from multiple property sources, and duplicate keys take values according to precedence:

~~~text
catalog.headers.source  = default
catalog.headers.region  = asia
catalog.headers.channel = mobile
~~~

Do not interpret "the later document has `headers`" as "all entries in the earlier map are deleted". Map binding typically has key-merging semantics.

### 8.3. Lists: typically replaced during binding

Lists are a frequent source of confusion:

~~~yaml
catalog:
  servers:
    - "a.internal"
    - "b.internal"

---
catalog:
  servers:
    - "c.internal"
~~~

When binding `catalog.servers` to `List<String>` via `@ConfigurationProperties`, Spring Boot applies list binding rules: **the list from the higher-precedence source replaces the list from the lower-precedence source**, rather than concatenating `a,b` with `c` by default. In this case, the result is typically a list containing `c.internal`.

This differs from reading individual scalar properties. Distinguish **precedence between property sources** from **Binder semantics for data types**. Do not assume all collection types merge the same way.

### 8.4. Empty values and `null`

A later document can declare an empty value or YAML `null`. However, that does not mean every API and binder type will treat it as an operation to "completely delete the key" from lower sources.

In particular, YAML `null` is handled according to configuration source rules; do not rely on it as a guaranteed tool to overwrite values from a lower-precedence property source with null. If you want to disable a feature, design an explicit key such as `feature.enabled=false`; if you want to remove a collection element, examine binder semantics and adjust the higher-precedence configuration accordingly.

## 9. Dedicated example for `application.properties` with conditional documents

Suppose `application.properties` contains:

~~~properties
app.name=Invoices
app.cache.enabled=false
app.worker.threads=2

#---
spring.config.activate.on-profile=dev
app.cache.enabled=false
app.worker.threads=1

#---
spring.config.activate.on-profile=prod
app.cache.enabled=true
app.worker.threads=6

#---
spring.config.activate.on-profile=prod
app.worker.threads=8
~~~

When the `dev` profile is active, document 2 is included alongside the default document, yielding:

~~~text
app.name = Invoices
app.cache.enabled = false
app.worker.threads = 1
~~~

When the `prod` profile is active, documents 3 and 4 are both active:

~~~text
app.name = Invoices
app.cache.enabled = true
app.worker.threads = 8
~~~

Document 4 only contains `app.worker.threads`, so it does not delete or alter `app.name` and `app.cache.enabled`. This example follows the same principles as YAML, differing only in the separator and key declaration syntax.

When editing `.properties` files in an IDE, ensure the serializer or formatter does not rewrite `#---` into another comment syntax that prevents Spring Boot from recognizing the boundary. If a tool processes the file expecting only standard Java Properties, it may not preserve Boot's multi-document semantics.

## 10. Important activation constraints

### 10.1. `spring.config.activate.on-profile` is not `spring.profiles.active`

- `spring.profiles.active` is used to **select which profiles are active**.
- `spring.config.activate.on-profile` is used to **determine whether the current document is included in config data** based on the active profiles.

Conceptually valid example:

~~~yaml
catalog:
  mode: default

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  mode: production
~~~

The `prod` profile can be selected via command-line argument:

~~~bash
java -jar catalog.jar --spring.profiles.active=prod
~~~

Do not write `spring.profiles.active=prod` inside a document activated by `spring.config.activate.on-profile` and rely on that document to activate itself. Spring Boot restricts profile-selection properties such as `spring.profiles.active` / `spring.profiles.default` inside profile-specific documents or documents with `on-profile` conditions to prevent circular, unpredictable activation logic.

### 10.2. Unmatched condition means the document contributes no keys

Example:

~~~yaml
app:
  audit: false

---
spring:
  config:
    activate:
      on-profile: "qa"

app:
  audit: true
  endpoint: "https://qa.internal"
~~~

When `qa` is not active, document 2 contributes neither `app.audit` nor `app.endpoint`. The application might still obtain `app.endpoint` from another source; otherwise, a lookup may return null or fail if a required-key mechanism is used.

An inactive document's contents are not "loaded and waiting to be overridden": it does not contribute its properties into `Environment` for that startup scenario.

### 10.3. Cloud-environment conditional document

~~~yaml
app:
  proxy-required: false

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  proxy-required: true
~~~

If Spring Boot does not detect Kubernetes, the later document has no effect. If it does, the later document can override `app.proxy-required` to `true`. Verify how Spring Boot detects cloud platforms in your specific environment rather than assuming any Docker container counts as Kubernetes.

## 11. Observing resolved values in the application

Inside a Spring Boot application, use `Environment` to read values:

~~~java
package com.example.catalog;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CatalogDiagnostics {

    private final Environment environment;

    public CatalogDiagnostics(Environment environment) {
        this.environment = environment;
    }

    public void printResolvedTimeout() {
        String value = environment.getProperty("catalog.timeout");
        System.out.println("catalog.timeout = " + value);
    }
}
~~~

When typed binding is needed:

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        Duration timeout,
        boolean featureEnabled
) {}
~~~

Enable `@ConfigurationPropertiesScan` on a configuration class or register `CatalogProperties` using an appropriate mechanism, then inject it into services. With the file:

~~~yaml
catalog:
  timeout: 5s
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  timeout: 20s
~~~

under the `prod` profile, the bean typically receives `timeout=20s` and `featureEnabled=false`, assuming no higher-precedence source exists.

### 11.1. Inspecting `PropertySource` order for diagnostics

`ConfigurableEnvironment` exposes `PropertySource` entries in precedence order. With a **non-sensitive test key**, you can observe which source provides the value:

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigOrderProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigOrderProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.timeout";

        System.out.println("Resolved: " + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

This lets you see the relevant document, file, or property source, depending on how Spring Boot represents loaded sources. However, source names or formats can vary across Spring Boot versions and application setups; do not write business logic that depends on `PropertySource` name strings.

Do not run this logging snippet with passwords, tokens, private keys, or sensitive properties. When using Spring Boot Actuator `env` and `configprops`, secure the endpoints and configure safe sanitization because they can contain sensitive environment information.

### 11.2. Do not use `@Value` to infer document order

`@Value("${catalog.timeout}")` only tells you **the final value** after Spring resolves the property. It does not indicate which document supplied the value. To investigate the source, use Spring Boot's origin tracking/diagnostics and inspect the actual loaded sources.

## 12. How to determine results per profile yourself

Given `application.yml`:

~~~yaml
catalog:
  client:
    connect-timeout: 3s
    read-timeout: 10s
  show-details: false

---
spring:
  config:
    activate:
      on-profile: "dev"

catalog:
  client:
    read-timeout: 30s
  show-details: true

---
spring:
  config:
    activate:
      on-profile: "prod"

catalog:
  client:
    connect-timeout: 1s
    read-timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod & blue"

catalog:
  client:
    read-timeout: 7s
~~~

We can deduce:

| Active profiles | connect-timeout | read-timeout | show-details |
| --- | --- | --- | --- |
| `dev` | `3s` | `30s` | `true` |
| `prod` | `1s` | `5s` | `false` |
| `prod,blue` | `1s` | `7s` | `false` |
| `dev,prod` | `1s` | `5s` | `true` |
| None of the above profiles | `3s` | `10s` | `false` |

To explain `prod,blue`, document 2 does not match, document 3 matches, and document 4 also matches and appears after document 3, so `read-timeout` changes from `5s` to `7s`. Meanwhile, `connect-timeout` is still taken from document 3.

With `dev,prod`, documents 2 and 3 are both active; document 3 appears later and overrides `read-timeout` from document 2, while `show-details` is not redeclared so it remains `true`.

This exercise intentionally considers only the documents in the file above. In a real application, profile-specific files, imports, environment variables, or CLI arguments can change the final result.

## 13. Common misconceptions

| Misconception | What to understand |
| --- | --- |
| "The last document always wins every key." | It only overrides **matching keys** and only when that document is **active**; other keys can come from earlier documents |
| "With profile `prod`, every document is active." | Only unconditional documents or those matching their respective conditions are applied |
| "The last document in `application.yml` always beats `application-prod.yml`." | You must account for precedence of **config data files** and profile-specific sources |
| "Putting `spring.profiles.active` in a document waiting for profile activation will enable that document." | Selecting profiles and activating documents are two different steps; this placement is restricted/invalid |
| "If two documents declare a map, the later map deletes all earlier keys." | Map binding can merge entries by key according to precedence |
| "If two documents declare a list, the two lists are concatenated." | List binding typically replaces the entire list from the higher-precedence source |
| "A `---` marker in properties has the same meaning as in YAML." | For Boot properties, use the `#---` or `!---` separator, not a plain YAML `---` line |
| "The `@Value` result tells you the source document." | `@Value` returns the resolved value; to know the source, inspect property sources/origin |
| "An inactive document can still provide a fallback." | An unactivated document does not contribute keys to `Environment` for that startup |

## 14. Practice exercises

### Exercise A: precedence across three YAML documents

Create `application.yml`:

~~~yaml
lesson:
  color: "gray"
  page-size: 10
---
lesson:
  color: "blue"
---
lesson:
  page-size: 50
~~~

Predict `lesson.color` and `lesson.page-size`. Then read them using `Environment`. When all three documents are active, the result is `blue` and `50`.

### Exercise B: conditional profile appearing multiple times

Create the file:

~~~yaml
lesson:
  status: "base"
  timeout: 1s

---
spring:
  config:
    activate:
      on-profile: "prod"

lesson:
  status: "primary"
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod"

lesson:
  timeout: 9s
~~~

Run first without the `prod` profile and then with `--spring.profiles.active=prod`. When `prod` is active, `lesson.status=primary` and `lesson.timeout=9s`. When inactive, `base` and `1s` are used.

### Exercise C: YAML and properties

Convert the example in Exercise B to `application.properties`, using `#---` to separate documents and `spring.config.activate.on-profile=prod` for conditions. Run with both profile states and compare results.

### Exercise D: precedence of another file

Create a separate `application-prod.yml`, setting `lesson.timeout=30s`. Run with the `prod` profile and observe how it interacts with the `prod` document in `application.yml`. Next, run with the extra argument `--lesson.timeout=45s` to observe command-line argument precedence. The goal is to recognize **two decision layers**: order within a file and order across sources.

### Exercise E: lists and maps

Create a multi-document `application.yml` in which:

- The first document has `lesson.tags` with two elements and `lesson.labels.a`, `lesson.labels.b`.
- The second document only has `lesson.tags` with one element and `lesson.labels.b`, `lesson.labels.c`.
- Bind to a `@ConfigurationProperties` class with `List<String> tags` and `Map<String,String> labels`.

Observe that list binding behaves differently from entry-by-entry map merging; two lists are not concatenated by default like merging two sets.

## 15. Checklist for diagnosing duplicate-key configuration

When Spring Boot returns an unexpected value for `some.property`:

1. **Locate the exact config data file.** Is the app loading a classpath file, a file outside the JAR, a profile-specific file, or an imported file?
2. **Split the file into documents.** Read `---` in YAML or `#---`/`!---` in properties accurately.
3. **Inspect activation conditions.** Check `on-profile`, `on-cloud-platform`, and actual environment state.
4. **Trace document order.** Consider only active documents, noting the last declaration of the key in the file.
5. **Check other sources.** Is `application-prod.yml`, an import, an environment variable, a system property, or a CLI argument overriding it?
6. **Check the target data type.** Scalars, maps, and lists have different binding semantics.
7. **Observe at runtime.** Read `Environment`, inspect `PropertySource` names or origin metadata if needed, and ensure secrets are not exposed.

It is important to use **the same startup run, the same profiles, and the same config data order** when comparing predictions with results. Change only one factor at a time to avoid misidentifying the cause.

## 16. Key takeaways

- Multi-document YAML is separated by `---`; multi-document properties use `#---` or `!---`.
- Spring Boot processes documents in order of appearance; **an activated later document overrides matching keys** from an earlier document within the same file.
- A document that does not satisfy `spring.config.activate.on-profile` or `spring.config.activate.on-cloud-platform` does not contribute its keys.
- "Later document wins" is a rule at **one precedence layer**; profile-specific files, locations outside the JAR, imports, and other property sources still affect the final result.
- For scalars/maps/lists, consider both property override mechanics and type-specific binding rules.
- To diagnose, determine active documents first, then evaluate order, and finally inspect higher-precedence configuration sources.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): multi-document YAML/properties, activation, imports, and precedence.
- [Spring Boot Reference — Working With Multi-Document Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.multi-document): separator syntax and document order.
- [Spring Boot Reference — Activation Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.activation-properties): `on-profile` and `on-cloud-platform`.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): how the binder handles structured data.
