# Hierarchical Structure and Indentation Rules in YAML

YAML (*YAML Ain't Markup Language*) is a human-readable data format commonly used by Spring Boot in `application.yml` or `application.yaml`. YAML's most important characteristic is that **structure is expressed through indentation**: lines below and indented further than a key belong to that key. Incorrect indentation can cause the application to read a different configuration or fail to parse the file altogether.

This lesson focuses on writing valid hierarchical configuration, reading the meaning of each indentation level, and applying it in Spring Boot 3.3.x with Java 21.

## 1. How does YAML represent structure?

Three common data organization types:

- **Scalar:** a single value such as a string, number, boolean, or `null`.
- **Mapping:** a collection of `key: value` pairs; similar to an object or `Map`.
- **Sequence:** a list of items, usually marked with `-`.

Example:

~~~yaml
app:
  name: order-service
  enabled: true
  retry-count: 3
  tags:
    - backend
    - orders
  database:
    host: localhost
    port: 5432
~~~

In the snippet above:

- `app` is the top-level mapping.
- `name`, `enabled`, `retry-count`, `tags`, and `database` are at the same level, nested under `app` because they are indented by two spaces.
- `database` further contains `host` and `port` at a deeper level.
- `tags` is a list of two items, each starting with `-`.

You can visualize the configuration tree:

~~~text
app
├── name = "order-service"
├── enabled = true
├── retry-count = 3
├── tags
│   ├── [0] = "backend"
│   └── [1] = "orders"
└── database
    ├── host = "localhost"
    └── port = 5432
~~~

This representation groups related properties instead of repeating long key prefixes over and over.

## 2. Indentation rules: use spaces, never Tabs

### 2.1. Indentation level expresses parent–child relationships

Correct example:

~~~yaml
server:
  port: 8081
  servlet:
    context-path: /api
spring:
  application:
    name: config-demo
~~~

Here:

- `server` and `spring` are at the same top level.
- `port` and `servlet` are child keys of `server`.
- `context-path` is a child key of `servlet`.
- `application` is a child key of `spring`, and `name` is a child key of `application`.

If two keys belong to the same mapping, align them at the **same column**. If a child key belongs to a parent key, indent it deeper than the parent key.

A common convention is **two spaces per level**. YAML does not strictly require two spaces, but indentation must be consistent so the structure stays clear. On projects edited by multiple people, standardize on two spaces to avoid readability issues or misplaced levels.

### 2.2. Do not use Tab characters for indentation

**Invalid** example if the indentation character is a Tab:

~~~text
server:
→port: 8081
~~~

The `→` symbol here illustrates **a single Tab character**, not content to type into the file. YAML uses spaces for indentation; using Tabs for indentation causes the parser to report an error. Enable visible whitespace in your IDE or configure your editor to convert Tabs to spaces.

### 2.3. Siblings must align vertically

Correct:

~~~yaml
app:
  database:
    host: db.internal
    port: 5432
    pool-size: 10
~~~

Wrong **structural intent**:

~~~yaml
app:
  database:
    host: db.internal
    port: 5432
  pool-size: 10
~~~

The second snippet can still be valid YAML, but `pool-size` is now at `app.pool-size`, **no longer** at `app.database.pool-size`. This kind of bug is easy to miss because the application may start up successfully yet fail to bind the intended property.

### 2.4. A parent key line may have no direct value

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

`management:` does not assign a scalar on that line itself. The indented lines beneath it define the nested mapping. Similarly, `endpoints:`, `web:`, and `exposure:` are organizational levels, while `include:` holds the value.

If you write:

~~~yaml
app:
  database:
~~~

`database` contains no child keys and is interpreted as an empty/null value depending on how the parser handles it, not as a populated database configuration object. Do not leave a parent key empty when the program expects specific properties underneath it.

## 3. Mapping syntax: key and value pairs

Mappings are written with a colon, followed by a space and then the value:

~~~yaml
app:
  title: "Simple configuration"
  timeout-seconds: 30
  enabled: true
  environment: development
~~~

Note the distinction:

~~~yaml
# Correct: ":" separates key and value
port: 8080

# Avoid: missing space, may become a scalar instead of a mapping
port:8080
~~~

For scalar values containing colons, hash symbols, or special whitespace, wrap them in quotes:

~~~yaml
app:
  message: "Result: success"
  token-placeholder: "abc#123"
  description: "Preserve : and # inside a string"
~~~

A `#` outside a string can start a comment when appearing in the appropriate syntactic context. Use quotes when you want to prevent the parser from interpreting special characters as syntax. URLs like `https://example.org/api` can usually be unquoted, though quoting them still helps readers distinguish strings clearly.

Comment example:

~~~yaml
app:
  # Default retry count
  retry-count: 3
  active: true # enable feature in this environment
~~~

Comments do not become properties when Spring Boot reads the file.

## 4. Expressing hierarchical configuration in `application.yml`

Suppose an application needs one group of properties for an API and another for caching:

~~~yaml
spring:
  application:
    name: catalog-service

server:
  port: 8085

app:
  api:
    base-url: https://api.example.org
    timeout: 5s
    enabled: true
  cache:
    enabled: false
    ttl: 10m
~~~

Conceptually, Spring Boot can use the corresponding property names:

| Configuration path | Value |
| --- | --- |
| `spring.application.name` | `catalog-service` |
| `server.port` | `8085` |
| `app.api.base-url` | `https://api.example.org` |
| `app.api.timeout` | `5s` |
| `app.api.enabled` | `true` |
| `app.cache.enabled` | `false` |
| `app.cache.ttl` | `10m` |

This is the benefit of hierarchical structure: instead of repeating the `app.api.` prefix, the YAML file groups keys by level. Spring Boot loads the YAML file through its configuration mechanism, placing the resolved properties into `Environment` for reading or binding.

Equivalent configuration in `application.properties`:

~~~properties
spring.application.name=catalog-service
server.port=8085

app.api.base-url=https://api.example.org
app.api.timeout=5s
app.api.enabled=true
app.cache.enabled=false
app.cache.ttl=10m
~~~

Both representations can supply the same properties to the application. YAML fits well when many keys share prefixes, whereas properties is convenient when there are only a few keys.

Avoid keeping both `application.properties` and `application.yml` containing the same property in one configuration location unless you have an intentional precedence plan; it is easy to lose track of where the effective value comes from.

## 5. Sequences (lists) and indentation of `-`

### 5.1. Lists of scalars

~~~yaml
app:
  allowed-origins:
    - https://app.example.org
    - https://admin.example.org
  supported-locales:
    - vi
    - en
~~~

`allowed-origins` is a list of two strings, as is `supported-locales`. The hyphens must be aligned consistently among elements of **the same list**.

A compact inline form is also valid:

~~~yaml
app:
  supported-locales: [vi, en]
~~~

However, the multiline form is easier to extend and convenient when adding comments to individual items.

### 5.2. Lists of objects

~~~yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.org
      enabled: true
    - name: fallback
      url: https://fallback.example.org
      enabled: false
~~~

Each `-` starts a new mapping element. `name`, `url`, and `enabled` belong to the same element when aligned at the proper level. The second element begins at the second `-`.

You can visualize the values as:

~~~text
app.endpoints
  [0].name    = primary
  [0].url     = https://primary.example.org
  [0].enabled = true
  [1].name    = fallback
  [1].url     = https://fallback.example.org
  [1].enabled = false
~~~

In Spring Boot, these paths are typically represented as `app.endpoints[0].name` and `app.endpoints[1].url` when flattened. With `@ConfigurationProperties`, they can bind to `List<Endpoint>`.

### 5.3. Lists nested inside lists or objects

~~~yaml
app:
  teams:
    - name: platform
      members:
        - an
        - binh
    - name: backend
      members:
        - chi
~~~

In the example above, each team is a mapping, and each mapping has a `members` list. Each time you descend into a list or mapping level, check the exact column of `-` and the keys.

### 5.4. Misaligned level in a list

Misleading example:

~~~yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.org
  enabled: true
~~~

Here `enabled` is `app.enabled`, not a property of the element `app.endpoints[0]`. To place it inside the list item, align it in the same column as `url`:

~~~yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.org
      enabled: true
~~~

This mistake usually produces no YAML error message, yet the resulting data structure no longer matches what was intended.

## 6. Nested mappings, dynamic maps, and special keys

Beyond fixed property groups, YAML can represent a map with dynamic key names:

~~~yaml
app:
  labels:
    region: southeast-asia
    team: backend
    stage: development
~~~

You can bind the `labels` group into `Map<String, String>`. When keys contain only ordinary characters, this simple style suffices.

For keys **with special characters** such as slashes, or when dots must be preserved literally in a map key name, Spring Boot has dedicated map binding rules. For example:

~~~yaml
app:
  routes:
    "[/internal/health]": "health-route"
    "[api.v1]": "v1-route"
~~~

The square brackets are inside **a quoted YAML key name**. This is Spring Boot's bracket notation to preserve key names when binding to a map; it is not a new YAML mapping level. If special keys are not needed, prefer simple key names to reduce confusion.

If the same mapping key is defined twice in one mapping, handling depends on parser and validation settings; avoid duplicate keys:

~~~yaml
# Avoid this style
app:
  mode: fast
  mode: safe
~~~

Instead, keep only one intentional value, or use profile-specific configuration to describe environment variants.

## 7. Binding YAML to Java objects with `@ConfigurationProperties`

Suppose `src/main/resources/application.yml` contains:

~~~yaml
app:
  api:
    base-url: https://api.example.org
    timeout: 5s
    enabled: true
  endpoints:
    - name: primary
      url: https://primary.example.org
    - name: fallback
      url: https://fallback.example.org
  labels:
    region: asia
    team: platform
~~~

Create a configuration record:

~~~java
package com.example.configdemo;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Api api,
        List<Endpoint> endpoints,
        Map<String, String> labels) {

    public record Api(
            String baseUrl,
            Duration timeout,
            boolean enabled) {
    }

    public record Endpoint(String name, String url) {
    }
}
~~~

In the main class:

~~~java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
~~~

Spring Boot scans `@ConfigurationProperties` and creates an `AppProperties` bean. Once injected, you can access:

~~~java
@Component
class ConfigPrinter implements ApplicationRunner {

    private final AppProperties properties;

    ConfigPrinter(AppProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(properties.api().baseUrl());
        System.out.println(properties.api().timeout());
        System.out.println(properties.endpoints().get(0).name());
        System.out.println(properties.labels().get("team"));
    }
}
~~~

Import `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationArguments`, and `org.springframework.boot.ApplicationRunner`. These expressions produce the following output:

~~~text
https://api.example.org
PT5S
primary
platform
~~~

`PT5S` is how `Duration` displays five seconds in ISO-8601 format. Spring Boot supports binding `5s` to `java.time.Duration`. The YAML key `base-url` binds to the Java property `baseUrl` via *relaxed binding*, allowing YAML to keep kebab-case style.

**Important:** YAML defines the data structure; `@ConfigurationProperties` defines how that structure maps to Java types. If indentation places `api` or `endpoints` at a different level, the binder may fail to populate the expected fields.

## 8. Quoted strings, multiline strings, and special characters

### 8.1. Values that should be quoted to preserve string type

~~~yaml
app:
  build-number: "0012"
  feature-name: "true"
  error-message: "Unable to connect: retry"
  text-with-hash: "code #1"
~~~

Not every scalar is always parsed as a string. For example, `true` can be interpreted as a boolean; `"true"` is intentionally a string. For identifiers with leading zeros, use quotes to preserve string semantics.

### 8.2. Multiline strings with `|` and `>`

~~~yaml
app:
  email-template: |
    Hello,
    Your order has been recorded.
    Thank you.
  summary: >
    This is a long paragraph
    written across multiple lines
    for readability in YAML.
~~~

- `|` (*literal block scalar*) preserves line breaks between content lines.
- `>` (*folded block scalar*) typically folds ordinary line breaks into spaces.
- The content of a block scalar must be indented deeper than the line containing `|` or `>`.

By default, trailing line breaks at the end of a block also follow *chomping* rules; you can use `|-` or `>-` to strip the final trailing line break if your application requires exact string matching.

## 9. Multiple YAML documents in a single file

YAML supports separating multiple documents with `---`. Spring Boot can use this feature to activate groups of settings per profile.

Example:

~~~yaml
app:
  api:
    timeout: 5s
    base-url: https://api.example.org

---
spring:
  config:
    activate:
      on-profile: dev
app:
  api:
    timeout: 20s
    base-url: http://localhost:8089
~~~

The first document provides common configuration. The second document is applied only when the `dev` profile is active; you can run the application with `--spring.profiles.active=dev`. Then the `app.api.timeout` and `app.api.base-url` values in the matching document override the common settings.

`---` must sit at the document-separator position, not indented as a child key. This is document-level YAML syntax, not the value of a key.

For profile-specific configuration, you can also use separate files such as `application-dev.yml`. Choose an organization style suited to your project size and avoid duplicate declarations that are hard to track.

## 10. Common mistakes

### Mistake A: using Tabs in indentation

~~~text
app:
→name: demo
~~~

Replace Tabs with spaces; enable your IDE's whitespace visualization option to spot them.

### Mistake B: placing a key at the wrong level

~~~yaml
# Parseable, but unintended
app:
  database:
    host: localhost
  port: 5432
~~~

If the goal is `app.database.port`, indent `port` to the same level as `host`.

### Mistake C: failing to align keys inside the same list element

~~~yaml
# Illustrates incorrect structure when each endpoint requires a url
app:
  endpoints:
    - name: primary
      url: https://one.example.org
    - name: secondary
  url: https://two.example.org
~~~

The last `url` is `app.url`. Move it under `- name: secondary` and align it in the same column as that item's `name`.

### Mistake D: confusing a string with a mapping

~~~yaml
# Likely to be parsed as a scalar string
server.port:8080

# Recommended
server:
  port: 8080
~~~

When flat keys are desired, `server.port: 8080` is also valid YAML mapping syntax and interpreted by Spring Boot as the corresponding property name; however, in this lesson on hierarchical structure, use the nested form to keep relationships clear.

### Mistake E: whitespace in multiline strings

~~~yaml
app:
  template: |
    First line
    Second line
~~~

Inside a block scalar, spaces and line breaks are significant to the content. Do not arbitrarily alter the indentation of content lines or change `|` to `>` if the program depends on the string formatting.

### Mistake F: treating YAML as appending lists across configuration sources

If a list is redeclared in a higher-precedence configuration source, Spring Boot normally **replaces the list**, rather than merging elements from both sources. This differs from the expectation of "adding an item to the default list".

General example:

~~~yaml
app:
  servers:
    - main.example.org
    - secondary.example.org
~~~

If profile configuration overrides `app.servers` with a new list containing only `dev.example.org`, the effective list will be the one from the active profile. To avoid losing items, declare the full target set in the overriding source.

## 11. How to verify the effective configuration

When there is a mismatch between the expected value and what the application uses, distinguish two cases:

1. **Invalid YAML:** the application cannot load the file; usually there is a parse error message with line/column numbers. Check colons, Tabs, spaces, and quotes.
2. **Valid YAML with wrong structure:** the application may run, but the property is not at the path the program expects. Check indentation and mapping paths, then check which configuration source is effective.

You can observe a value using `Environment`:

~~~java
@Bean
ApplicationRunner inspect(Environment environment) {
    return args -> {
        System.out.println(environment.getProperty("app.api.base-url"));
        System.out.println(environment.getProperty("app.api.timeout"));
        System.out.println(environment.getProperty("app.endpoints[0].name"));
    };
}
~~~

Required imports: `org.springframework.boot.ApplicationRunner`, `org.springframework.context.annotation.Bean`, and `org.springframework.core.env.Environment`. This snippet belongs inside a `@Configuration` or `@SpringBootApplication` class; depending on the effective configuration sources, the output may vary. For complex objects, `@ConfigurationProperties` makes verifying binding easier.

If the project uses Spring Boot Actuator, the `env` or `configprops` endpoints can assist with diagnostics once enabled and properly secured; do not publicly expose sensitive configuration information.

## 12. Practice exercises

**Exercise 1 — Predict property paths.** Given the YAML:

~~~yaml
library:
  name: central
  storage:
    provider: local
    root: /data/books
  categories:
    - java
    - spring
~~~

Determine the values of `library.storage.provider`, `library.storage.root`, and `library.categories[1]`. Answer: `local`, `/data/books`, `spring`.

**Exercise 2 — Fix indentation.** The goal is for each `worker` to have `name` and `concurrency`:

~~~yaml
app:
  workers:
    - name: importer
    concurrency: 2
    - name: exporter
    concurrency: 4
~~~

Fix it to:

~~~yaml
app:
  workers:
    - name: importer
      concurrency: 2
    - name: exporter
      concurrency: 4
~~~

**Exercise 3 — Convert properties to YAML.** Given:

~~~properties
spring.application.name=payment-demo
server.port=9092
app.job.enabled=true
app.job.interval=30s
~~~

An equivalent conversion:

~~~yaml
spring:
  application:
    name: payment-demo
server:
  port: 9092
app:
  job:
    enabled: true
    interval: 30s
~~~

**Exercise 4 — Try profiles.** Create an `application.yml` with a common document setting `app.api.timeout: 5s` and a `dev` document setting `20s`. Run the application once without a profile and once with `--spring.profiles.active=dev`; observe the value from `Environment` or a configuration bean.

## 13. Takeaways when writing `application.yml`

- Use **spaces**, preferring two spaces per level; strictly avoid Tabs for indentation.
- Align siblings in the same column; a more deeply indented line belongs to the nearest parent level per YAML structure.
- `key: value` creates a mapping, `- value` creates a sequence element.
- Lists of objects require aligning the fields of each element accurately.
- Path names like `app.database.host` come from the parsed mapping tree; a wrong level can produce a completely different property.
- Use quotes when you want to preserve strings with special characters or prevent automatic scalar type inference.
- Valid YAML alone is not enough: you must also ensure the right property path and binding outcome in Spring Boot.

## References

- [Spring Boot 3.3 — Externalized Configuration: YAML Mapping to Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.yaml)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [YAML 1.2.2 Specification](https://yaml.org/spec/1.2.2/)
