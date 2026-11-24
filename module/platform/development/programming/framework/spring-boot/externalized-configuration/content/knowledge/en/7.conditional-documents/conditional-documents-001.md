# Distinguishing One Physical File from Multiple Logical Configuration Documents in Spring Boot 3.3

## 1. The problem: does one file necessarily correspond to one configuration set?

When first learning Spring Boot, we often think of an `application.yaml` or `application.properties` file as a single configuration block. That model is sufficient when the file only contains a few shared keys. However, an application often needs the same configuration keys with different values depending on the runtime environment: a developer machine (`dev`), testing (`test`), or production deployment (`prod`).

Spring Boot 3.3 supports **multiple logical configuration documents in the same physical file** (*multi-document configuration files*). Each logical document is a configuration block with its own boundaries; it can be loaded or skipped depending on activation conditions. When multiple documents are activated, Spring Boot evaluates their order to determine the final value for overlapping keys.

Key concepts to understand upfront:

- **Physical file**: a file that actually exists on the filesystem or in the classpath, such as `src/main/resources/application.yaml`.
- **Logical configuration document**: an independent section inside a file, separated by a special marker and processed by Spring Boot as a distinct configuration document.
- **Conditional document**: a logical document that is only activated when a condition such as `spring.config.activate.on-profile` is satisfied.
- **Effective value**: the value of a key after Spring Boot combines active documents with other configuration sources according to precedence rules.

A file can contain one document, two documents, or many documents. Conversely, **a single profile** can also use multiple files or multiple logical documents. Therefore, you should not conflate the concepts of *file*, *document*, *profile*, and *source of the final value*.

This lesson belongs to the **Spring Boot Externalized Configuration** topic and focuses on how to organize conditional documents in Spring Boot 3.3.x. The examples assume Java 17 or later and a standard Spring Boot application.

## 2. Mental model: two structural layers

Imagine the physical file as a **container**, inside which there can be multiple configuration documents:

```text
src/main/resources/application.yaml      <-- one physical file
|
+-- Logical document 1: shared configuration
|
+-- Logical document 2: active only with the dev profile
|
+-- Logical document 3: active only with the prod profile
```

When the application starts with the `dev` profile:

```text
application.yaml
    |
    +-- document 1 (shared) -----------> loaded
    |
    +-- document 2 (on-profile dev) ---> loaded
    |
    +-- document 3 (on-profile prod) --> not activated
                                              |
                                              v
                           Environment only considers valid documents
```

When running with the `prod` profile, document 1 and document 3 are activated, while document 2 is not.

Subtle point: Spring Boot does not simply read the entire file and treat every line inside it as a single flat block. It **splits the documents**, evaluates each document's activation condition, and adds values from the matching documents into the configuration system.

Within a multi-document file, documents located **later** can override matching keys from **earlier** documents, if both are activated. This rule only describes the relationship between documents within the same file; precedence across files, locations outside the JAR, profiles, environment variables, and command-line arguments must still be evaluated separately.

## 3. YAML: multiple documents separated by `---`

YAML natively has syntax for separating documents. In Spring Boot, to create multiple logical documents in `application.yaml` or `application.yml`, place a line containing only:

```yaml
---
```

The separator line must stand on its own. Each block between `---` markers is treated as a separate logical document. The first document starts right at the beginning of the file and does not require a leading `---`.

Example `src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: config-document-demo

app:
  greeting: General hello
  timeout: 5s
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

app:
  greeting: Hello dev environment
  timeout: 1s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  greeting: Hello production environment
  timeout: 10s
  feature-enabled: true
```

The file above has **only one physical path**: `application.yaml`. However, it has **three logical configuration documents**:

| Document | Position | Condition | Representative content |
| --- | --- | --- | --- |
| 1 | Before the first `---` | No activation condition declared | `app.greeting`, `app.timeout`, `app.feature-enabled` |
| 2 | Between the two `---` markers | `spring.config.activate.on-profile: dev` | Overrides greeting and timeout for `dev` |
| 3 | After the second `---` | `spring.config.activate.on-profile: prod` | Overrides greeting, timeout, and feature flag for `prod` |

Each document can use nested YAML structure just like a regular YAML file. Nested keys are converted by Spring Boot into logical property names: `app.greeting`, `app.timeout`, `app.feature-enabled`.

### Results across different startup runs

When neither `dev` nor `prod` is enabled, only the shared document is applied in the example:

```text
app.greeting = General hello
app.timeout = 5s
app.feature-enabled = false
```

Start with:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Expected values:

```text
app.greeting = Hello dev environment
app.timeout = 1s
app.feature-enabled = false
```

The key `app.feature-enabled` is not overridden by the `dev` document, so the value from the shared document is still used.

Start with:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Expected values:

```text
app.greeting = Hello production environment
app.timeout = 10s
app.feature-enabled = true
```

These examples assume there is no other source with higher precedence, such as `--app.timeout=...`, environment variables, or external files.

**There is no need to create three copies of `application.yaml`** just to have three logical documents. One physical path can hold both the shared section and conditionally activated sections.

## 4. `.properties` also supports multiple logical documents

The multi-document feature is not exclusive to YAML. Spring Boot 3.3 supports separating documents in a `.properties` file using a line containing only:

```properties
#---
```

Or:

```properties
!---
```

These are **separators recognized by Spring Boot**, not a new `spring.*` key name. You should place the separator on its own line without trailing whitespace or extra content. To avoid confusing the boundary with `.properties` comments, also keep the separator line isolated, without placing comment lines starting with the same prefix immediately before or after it.

Example `src/main/resources/application.properties`:

```properties
spring.application.name=config-document-demo

app.greeting=General hello
app.timeout=5s
app.feature-enabled=false

#---
spring.config.activate.on-profile=dev

app.greeting=Hello dev environment
app.timeout=1s

#---
spring.config.activate.on-profile=prod

app.greeting=Hello production environment
app.timeout=10s
app.feature-enabled=true
```

The file above serves the same purpose as the YAML example:

```text
application.properties                   <-- one physical file
  |
  +-- document 1: shared configuration
  |
  +-- #---
  +-- document 2: activated when profile dev is active
  |
  +-- #---
  +-- document 3: activated when profile prod is active
```

### Do not confuse comments with document boundaries

The following two lines are **not equivalent**:

```properties
#--- 
```

and:

```properties
# ---- Dev configuration section ----
```

The first line is just an example of how a separator can be malformed if a trailing space is added; use `#---` exactly on its own line. The second line is a regular comment, not a document separator.

A comment like:

```properties
# Configuration for dev
```

also does not create a separate configuration document on its own. Without an actual separator, the keys below it still belong to the same logical document as the keys above it.

**Syntax note:** the `#---` and `!---` lines are how Spring Boot supports multiple documents in properties files. A plain Java `.properties` reader does not necessarily share these multi-document semantics. When explaining behavior, you must distinguish between Spring Boot loading *config data* and reading a file with the standard `java.util.Properties` API.

## 5. Separators create boundaries; conditions decide activation

A logical document does not necessarily need a condition. It can be an additional configuration block that is always active, or a block meant only for one environment.

YAML example **without conditions**:

```yaml
app:
  name: first
  retries: 2

---
app:
  name: second
```

Both documents can be considered at startup. Within this file itself, the later document has higher precedence for matching keys:

```text
app.name    = second
app.retries = 2
```

The key `app.retries` exists only in the first document, so it is not lost. A document boundary does not mean the later document wipes out all keys from the previous document.

YAML example **with a condition**:

```yaml
app:
  retries: 2

---
spring:
  config:
    activate:
      on-profile: dev
app:
  retries: 1
```

- Profile `dev` is inactive: the second document contributes no values; `app.retries=2`.
- Profile `dev` is active: both documents match; the later document overrides `app.retries=1`.

Two questions must be answered in order:

1. **Is this document activated?**
2. **If yes, what is the precedence order between this document and the remaining sources?**

Visually reading a value in a file only answers "is this value declared here?", not "which value does the application ultimately use?".

## 6. The `spring.config.activate.on-profile` condition

In Spring Boot 3.3, the property:

```properties
spring.config.activate.on-profile=dev
```

or in YAML:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

specifies that **the logical document containing this property is only active when the corresponding profile expression is satisfied**.

Some usage examples:

```yaml
# Shared document
app:
  diagnostic: false

---
spring:
  config:
    activate:
      on-profile: dev
app:
  diagnostic: true
```

You can use profile expressions to describe more flexible conditions, for example:

```yaml
spring:
  config:
    activate:
      on-profile: "dev | test"
```

The expression above allows the document to be active when either `dev` **or** `test` matches. For a negated condition:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

The document matches when `prod` is not active. Wrap the expression in YAML quotes if the string contains characters that YAML might interpret as syntax, especially `!`.

Profiles are a **Spring conditional mechanism**, not synonymous with OS environment variables. You can enable a profile via an argument:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Or set the environment property where supported:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

On PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
```

Here, the environment variable name is simply a way to supply the value for the `spring.profiles.active` property. Spring itself determines which profiles are active and then evaluates documents with `on-profile`.

### Configuration without `on-profile` still has a role

A document without an activation condition is the right place to store **shared values** that all environments can use. Conditional documents then only declare **what changes**.

Example:

```yaml
app:
  client:
    timeout: 5s
    max-retries: 3
    enabled: true

---
spring:
  config:
    activate:
      on-profile: dev
app:
  client:
    timeout: 1s
```

In `dev`, `timeout=1s`, while `max-retries=3` and `enabled=true` come from the shared document. This approach reduces repeating the same values across multiple environments and makes the differences between them clear to readers.

## 7. Document order within the same file

In a multi-document file, Spring Boot processes documents in order from top to bottom. **Later documents can override keys declared in earlier documents**.

Example:

```yaml
app:
  mode: first
  retry-count: 1

---
app:
  mode: second

---
app:
  mode: third
```

With all three documents activated:

```text
app.mode        = third
app.retry-count = 1
```

In this file, document 3 overrides `app.mode` from document 2, and document 2 overrides `app.mode` from document 1. No later document changes `app.retry-count`.

### With conditions, filter before evaluating precedence

Example:

```yaml
app:
  mode: common

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: development

---
spring:
  config:
    activate:
      on-profile: prod
app:
  mode: production
```

When only `dev` is enabled, the `prod` document is inactive. You **must not** conclude that `production` wins just because it appears at the end of the file. The value is `development`.

When only `prod` is enabled, the value is `production`.

If both `dev` and `prod` are active at the same time, both documents can match. In this file, the later document (`prod`) can override the same-named key from the earlier document (`dev`). Therefore, you should not use two mutually conflicting profiles such as `dev` and `prod` simultaneously without a clear reason; a profile name does not inherently create a rule that "prod always wins".

### Order within a file differs from order across configuration sources

An easily confused example:

```text
classpath:/application.yaml
    document 1: app.mode=common
    document 2: app.mode=dev (on-profile: dev)

./config/application.yaml
    app.mode=external
```

A file outside the JAR in a default configuration location can take precedence over a classpath file. In that case, `external` can be the final value, even though the `dev` document appears after the shared document inside the classpath file.

Likewise, command-line arguments:

```bash
java -jar app.jar --spring.profiles.active=dev --app.mode=cli
```

typically have higher precedence than configuration in files. **The "later document wins" rule applies only within the context of the document order being evaluated**, and does not replace Spring Boot's entire precedence hierarchy.

## 8. How does one multi-document file differ from multiple profile-specific files?

There are two common ways to organize configuration.

### Approach A — one physical file, multiple logical documents

```text
src/main/resources/
└── application.yaml
```

Inside it:

```yaml
app:
  endpoint: https://api.example.test
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: dev
app:
  endpoint: http://localhost:8081

---
spring:
  config:
    activate:
      on-profile: prod
app:
  timeout: 10s
```

All shared, `dev`, and `prod` settings live in a single file. Readers can look in one place to see all variants; on the downside, the file can grow long and multiple documents can easily end up overriding the same key.

### Approach B — multiple physical files per profile

```text
src/main/resources/
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
```

`application.yaml`:

```yaml
app:
  endpoint: https://api.example.test
  timeout: 5s
```

`application-dev.yaml`:

```yaml
app:
  endpoint: http://localhost:8081
```

`application-prod.yaml`:

```yaml
app:
  timeout: 10s
```

Spring Boot recognizes files named `application-{profile}.yaml` when the corresponding profile is activated.

| Criterion | One multi-document file | Multiple profile-specific files |
| --- | --- | --- |
| Number of physical files | Few, possibly just one | Multiple files |
| Boundary | `---` in YAML or `#---` in properties | File boundaries |
| How profile sections are selected | `spring.config.activate.on-profile` | Filename containing profile suffix |
| Easy to see all variants in one place | Yes | Need to open the related files |
| Easy to separate ownership or package files per environment | Less flexible | Can be more convenient |
| Risk of key duplication | Yes, across documents | Yes, across files |
| How precedence is calculated | Document order and other config data rules | File location, profile, and other sources |

Both approaches are valid; Spring Boot allows using them simultaneously in a project. However, using both without a clear convention makes it hard for maintainers to tell which values are being overridden.

An important point: **an `application-dev.yaml` file can also contain multiple YAML documents**. "Profile-specific files" and "multi-document files" are two orthogonal organizational dimensions, not mutually exclusive features.

### Which approach should you choose?

- If the number of variants is small and conditional documents are short: multiple documents in one `application.yaml` keeps configuration centralized.
- If environment differences are large or there are many dependent files: multiple profile-specific files are usually easier to maintain.
- If configuration is provided by the deployment system: you can still use files outside the JAR or infrastructure-appropriate sources, without forcing every value into `application.yaml`.
- Whichever approach you choose, make **shared values**, **profile-specific values**, and **which sources are allowed to override** explicit.

## 9. Cloud-platform conditional documents

Besides `on-profile`, Spring Boot 3.3 also supports the condition:

```properties
spring.config.activate.on-cloud-platform=kubernetes
```

Or in YAML:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
```

This document only matches when Spring Boot detects the corresponding cloud platform. Example:

```yaml
app:
  discovery:
    mode: static

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  discovery:
    mode: cluster
```

In an environment not detected as Kubernetes, the shared document can provide `app.discovery.mode=static`. In a detected Kubernetes environment, the conditional document can override it to `cluster`.

This mechanism shows that "conditional document" **is not strictly synonymous with "profile-based document"**. Conditions can evaluate deployment context. You should not use cloud conditions arbitrarily if the program needs explicit control via profiles: the behavior depends on how Spring Boot detects the platform.

## 10. Properties that must not be placed in profile-activated documents

Two groups must be distinguished:

- **Declaring a document's condition:** `spring.config.activate.on-profile`.
- **Activating profiles for the entire application:** `spring.profiles.active`, `spring.profiles.include`, and profile-group settings.

In Spring Boot 3.3, `spring.profiles.active` and `spring.profiles.include` should only be placed in matching documents that are not activated by profile. They must not be used inside profile-specific documents or documents activated via `spring.config.activate.on-profile`.

**Invalid** example:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod
```

The snippet above attempts to use a document that only activates under `dev` to switch the active profile to `prod`. Profile selection must be determined from valid sources before Spring Boot decides which documents are activated.

A more **sensible** example if the goal is profile-based configuration:

```yaml
app:
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev
app:
  feature-enabled: true
```

Then select the profile at startup:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Similarly, do not confuse `spring.config.activate.on-profile=dev` with declaring `spring.profiles.active=dev`. One says **"this document is only valid when dev is active"**, while the other says **"select dev as an active profile"**.

## 11. Configuration binding after Spring Boot selects documents

A Java application usually does not need to know which logical document index a value came from. After loading configuration, the application can use `Environment` or `@ConfigurationProperties` as usual.

Suppose `application.yaml` has:

```yaml
app:
  client:
    timeout: 5s
    max-retries: 3

---
spring:
  config:
    activate:
      on-profile: dev

app:
  client:
    timeout: 1s
```

Define the object:

```java
package example.documents;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientSettings(
        Duration timeout,
        int maxRetries
) {
}
```

When the `dev` profile is active, the `ClientSettings` object receives `timeout=1s`, `maxRetries=3` unless another source overrides it.

Note the distinction between:

1. **Logical document**: a block inside `application.yaml`.
2. **Resolved property**: for example, `app.client.timeout=1s`.
3. **Java object**: the `ClientSettings` record, which has `Duration` and `int` fields.
4. **Spring bean**: a configuration object registered so other beans can receive it via Dependency Injection.

A logical document does not automatically correspond to a bean. Spring Boot binds effective values into a typed configuration object after resolving conditions and precedence.

## 12. Hands-on: one YAML file containing three documents, running the same Java code

You can use a Spring Boot **3.3.x** project, Java **17+**, and the `spring-boot-starter` dependency. You do not need to add the Web starter if you only want to run the console example.

### Step 1 — create `application.yaml`

Place it at `src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: logical-documents-lab

demo:
  message: General mode
  threshold: 10
  trace-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

demo:
  message: Development mode
  threshold: 3
  trace-enabled: true

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  message: Production mode
  threshold: 100
```

Here the file contains three logical documents; the last two have conditions.

### Step 2 — write an application to print the configuration

Create `src/main/java/example/documents/DocumentDemoApplication.java`:

```java
package example.documents;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class DocumentDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showValues(Environment env) {
        return args -> {
            System.out.println("profiles="
                    + Arrays.toString(env.getActiveProfiles()));
            System.out.println("message="
                    + env.getProperty("demo.message"));
            System.out.println("threshold="
                    + env.getProperty("demo.threshold"));
            System.out.println("traceEnabled="
                    + env.getProperty("demo.trace-enabled"));
        };
    }
}
```

`Environment` reflects the configuration values resolved by Spring. Calling `getActiveProfiles()` helps identify which profiles were activated in the run.

### Step 3 — run without selecting a profile

If using the Maven wrapper:

```bash
./mvnw spring-boot:run
```

Or package as a JAR and run it. Replace `app.jar` with the actual JAR filename:

```bash
java -jar app.jar
```

Expected key output lines:

```text
profiles=[]
message=General mode
threshold=10
traceEnabled=false
```

`profiles=[]` means no **active profile** was specified; Spring still has the concept of a default profile, but the documents in the example do not set a condition on that default profile.

### Step 4 — activate `dev`

Run:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Expected output:

```text
profiles=[dev]
message=Development mode
threshold=3
traceEnabled=true
```

Now the second logical document is active, and the third document is inactive.

### Step 5 — activate `prod`

```bash
java -jar app.jar --spring.profiles.active=prod
```

Expected output:

```text
profiles=[prod]
message=Production mode
threshold=100
traceEnabled=false
```

`traceEnabled` remains `false` from the shared document because the `prod` document does not override that key.

### Step 6 — observe precedence within the same file

Insert **a fourth document at the end of `application.yaml`** to demonstrate another always-active block:

```yaml
---
demo:
  threshold: 999
```

This document has no `on-profile`; it is evaluated under every profile. Because it appears later, it can override `demo.threshold` in all three cases to `999`, unless a higher-precedence source overrides it.

This experiment shows that a multi-document file can become confusing if an author appends a shared block at the end. If your goal is "shared values as defaults, profile-specific values as overrides", **place the shared document first** and profile-specific documents after it.

After practicing, remove the fourth document to return to the original example.

### Step 7 — test an override source outside the document

Still using the original `application.yaml`, run:

```bash
java -jar app.jar --spring.profiles.active=dev --demo.threshold=77
```

Here, `demo.threshold=77` from the command-line argument can override the value `3` in the `dev` document. This demonstrates that document order within a file does not determine precedence for the **entire** application.

## 13. Equivalent hands-on with `application.properties`

Switch the test application's configuration file to `src/main/resources/application.properties` and use **a single format** for this test:

```properties
spring.application.name=logical-documents-lab

demo.message=General mode
demo.threshold=10
demo.trace-enabled=false

#---
spring.config.activate.on-profile=dev
demo.message=Development mode
demo.threshold=3
demo.trace-enabled=true

#---
spring.config.activate.on-profile=prod
demo.message=Production mode
demo.threshold=100
```

Run the same Java class from the previous section again. The values will show that Spring Boot also supports the multi-logical-document mechanism in `.properties`.

**Avoid keeping both `application.yaml` and `application.properties` with overlapping keys in the same location while experimenting**, because format-precedence rules will also come into play. To study one mechanism in isolation, use one format at a time.

One detail to remember: the separator in properties is `#---` or `!---`, **not** a bare `---` line like in YAML. Using the wrong separator can cause the file to be parsed unexpectedly or trigger an error.

## 14. Combining logical documents with `spring.config.import`

In Spring Boot 3.3, a logical document can include `spring.config.import` to import additional configuration. Example:

```yaml
app:
  source: common

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:classpath:/config/dev-extra.properties"

app:
  source: dev
```

Meaning:

- The first document contains shared configuration.
- The second document has the condition `on-profile: dev`.
- When the second document is activated, Spring Boot also processes the resource declared in `spring.config.import`.
- Values from the imported document are evaluated under the Config Data precedence rules; if the imported resource declares the same key, it can override the value in the document containing the import.

Here there are two kinds of boundaries:

```text
application.yaml (physical file A)
  |
  +-- logical document 1
  |
  +-- logical document 2 (dev condition)
        |
        +-- import -> config/dev-extra.properties (physical file B)
```

**The second logical document is still part of file A**; file B is a separate resource being imported. Do not confuse "document 2" with "file 2".

If the setup involves multiple imports and multiple conditions, first determine which documents are activated, then analyze the import relationships and precedence order. In practice, avoid deep nesting so the origin of values remains easy to trace.

## 15. Limitations and notes on reading files

### 15.1. `@PropertySource` is not equivalent to Config Data

Multi-document files are handled by Spring Boot's configuration mechanism when loading `application.yaml`, `application.properties`, and valid Config Data locations.

You should not assume that:

```java
@PropertySource("classpath:custom.properties")
```

provides the same handling of **multiple logical documents** as Spring Boot's Config Data mechanism. Spring Boot documentation explicitly states that multi-document properties or YAML files **cannot be loaded with `@PropertySource` or `@TestPropertySource` in that way**.

If you want to load a multi-document file as application configuration, use Config Data locations or `spring.config.import` instead of expecting `@PropertySource` to understand all separators.

### 15.2. One physical file does not mean only one value source

When Spring Boot splits logical documents, each document is processed individually by the configuration mechanism. Therefore, the number of files in a directory does not fully reflect the number of configuration documents actually participating.

Example:

```text
application.yaml                1 file, 3 documents
application-dev.yaml            1 file, 2 documents
external-settings.properties    1 file, 2 documents
-----------------------------------------------------
Total                           3 files, 7 documents
```

Seven is only the total number of **declared** documents. How many documents are actually **activated** depends on profiles, cloud conditions, loaded locations, and the configuration sources in use.

### 15.3. Comments do not split documents

Example:

```yaml
app:
  mode: basic

# Configuration for dev
app:
  mode: development
```

A comment line does not create a new document. You need `---` and, if you want a condition, `spring.config.activate.on-profile`.

In YAML, repeating keys at the same level within **one document** can cause parsing errors or unintended behavior, depending on parser rules. Never use comments as an "implicit" way to split documents.

### 15.4. YAML is sensitive to indentation

Correct:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

Structurally wrong in meaning if written as:

```yaml
spring:
  config:
    activate:
  on-profile: dev
```

The `on-profile` line in the second example is not properly nested under `activate`. Use spaces, avoid tabs, and ensure `---` starts at the beginning of the line. If conditional configuration does not work, check both YAML syntax and nesting structure.

### 15.5. Lists are not always merged across documents

If the shared document has:

```yaml
app:
  hosts:
    - a.example.test
    - b.example.test

---
spring:
  config:
    activate:
      on-profile: dev
app:
  hosts:
    - localhost
```

When bound to `List<String>`, the list from the higher-precedence source typically **replaces** the list from the lower-precedence source, rather than appending `localhost` to the end of the two shared items. Distinguish between overriding a scalar key and binding a list structure.

### 15.6. Conditional configuration is not a secret-protection mechanism

A document that only activates for `prod` can still remain inside the JAR or in the repository if you package the entire `application.yaml` file. Therefore, do not put real passwords, API keys, or tokens in a `prod` document just because it is inactive in `dev`. Activation conditions only decide **when values participate**, not encrypt or hide file contents.

## 16. Diagnosing when a conditional document is not applied

When you see a configuration being ignored, follow this sequence:

```text
Identify the key with an unexpected result
           |
           v
Open the exact physical file loaded by the running app
           |
           v
Count and identify logical document boundaries
           |
           v
Check on-profile / on-cloud-platform conditions
           |
           v
Verify active profiles and runtime environment
           |
           v
Check the order of activated documents
           |
           v
Check higher-precedence sources
           |
           v
Read the final value from Spring Environment
```

### Checking active profiles

Inside a bean, you can read:

```java
String[] profiles = environment.getActiveProfiles();
```

Or check Spring Boot's startup logs to see which profiles were selected. Do not infer profiles from the hostname or deployment directory name.

### Reading the effective value

Example at the bean level:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@Bean
ApplicationRunner showConfig(Environment env) {
    return args -> System.out.println(
            "demo.threshold=" + env.getProperty("demo.threshold"));
}
```

This snippet is a **method placed inside a `@Configuration` or `@SpringBootApplication` class**. It shows the final value, though it does not by itself recount the full history of which document won.

### Enabling detailed logging for Config Data

When you genuinely need to diagnose file loading:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Only enable this detailed log level temporarily in an appropriate development environment. Do not expose sensitive configuration contents or internal logs publicly.

### Common issues to distinguish

| Symptom | Possibility | How to verify |
| --- | --- | --- |
| Lines under `#` are not treated as a new document | Used a comment instead of a separator | Check `---` (YAML) or `#---`/`!---` (properties) |
| `dev` values do not appear | Profile `dev` is inactive or condition is wrong | Check `getActiveProfiles()`, inspect `on-profile` |
| `prod` values appear even when `dev` is also enabled | Multiple documents are active and the `prod` document comes later | Check active profiles and document order |
| Changed YAML but running JAR shows no change | JAR does not contain the updated file | Repackage or check external sources |
| Shared document value still wins unexpectedly | A later document or higher-precedence source overrides it | List all sources, check conditions and order |
| Application fails on startup | Invalid YAML structure, misplaced condition property, or profile restriction violated | Read the startup error message and indicated location |
| `@PropertySource` does not understand multi-document | Used a file-reading mechanism other than Config Data | Load the file via an appropriate Boot configuration mechanism |

## 17. Conventions for organizing multiple documents in one file

A readable pattern:

```yaml
# 1. Shared configuration
app:
  service:
    endpoint: https://api.example.test
    timeout: 5s
    max-retries: 3

---
# 2. Development configuration
spring:
  config:
    activate:
      on-profile: dev
app:
  service:
    endpoint: http://localhost:8081
    timeout: 1s

---
# 3. Production configuration
spring:
  config:
    activate:
      on-profile: prod
app:
  service:
    timeout: 10s
```

This organization has several advantages:

1. **Shared values come at the top of the file**, forming the baseline for all environments.
2. **Profile-specific overrides come afterward**, declaring only the keys that truly differ.
3. **Consistent key names** make it easy to see which values are overriding others.
4. **Clear `---` boundaries** help readers see the number of logical documents.
5. **Conditions right at the top of each block** quickly explain why a block is active or inactive.
6. **Avoid placing an accidental overriding shared document at the end** if profiles are meant to customize values.
7. **Do not use conditions to store secrets directly in Git**.

For `.properties` files, apply the same principles using the corresponding separators and flat syntax:

```properties
# Shared section
app.service.endpoint=https://api.example.test
app.service.timeout=5s
app.service.max-retries=3

#---
spring.config.activate.on-profile=dev
app.service.endpoint=http://localhost:8081
app.service.timeout=1s

#---
spring.config.activate.on-profile=prod
app.service.timeout=10s
```

When document size grows too large, splitting into multiple files by profile or feature can make maintenance easier for the development team. There is no requirement that all environment configurations live in a single file.

## 18. Exercises to predict values

### Exercise 1 — one file, two unconditional documents

```yaml
app:
  label: first
  count: 2

---
app:
  label: second
```

**Question:** What are the final values of `app.label` and `app.count`?

**Suggested answer:** `second` and `2`. Both documents are evaluated; the later document overrides overlapping keys without removing keys exclusive to the earlier document.

### Exercise 2 — later document is inactive

```yaml
app:
  label: common

---
spring:
  config:
    activate:
      on-profile: dev
app:
  label: developer
```

Run the application without activating `dev`.

**Question:** What is `app.label`?

**Answer:** `common`, because the second document does not satisfy its condition.

### Exercise 3 — two profiles active at the same time

```yaml
app:
  label: base

---
spring:
  config:
    activate:
      on-profile: dev
app:
  label: dev

---
spring:
  config:
    activate:
      on-profile: test
app:
  label: test
```

Run with:

```bash
java -jar app.jar --spring.profiles.active=dev,test
```

**Question:** Within this file itself, which document overrides the `app.label` key?

**Answer:** Both the `dev` and `test` documents satisfy their conditions. The `test` document appears later, so it can provide `app.label=test`, assuming no other source has higher precedence.

### Exercise 4 — distinguishing file boundaries from document boundaries

Given:

```text
application.yaml
  document 1: app.color=blue
  document 2: app.color=green (on-profile dev)

application-dev.yaml
  document 1: app.color=yellow
```

**Question:** How many physical files and how many logical documents are there? Can you determine the final value solely from YAML line position?

**Answer:** Two physical files, three logical documents. You must not ignore precedence across files and other sources; you must evaluate profile-specific files together with all config data rules.

### Exercise 5 — properties using the wrong marker

```properties
app.name=demo
# Dev section
spring.config.activate.on-profile=dev
app.name=demo-dev
```

**Question:** Why is this not two logical documents?

**Answer:** Because there is no `#---` or `!---` line to create a boundary. The `# Dev section` line is just a comment. You should not place `spring.config.activate.on-profile` in the middle of a document and assume it applies only to the lines below it.

### Exercise 6 — where does the value come from?

`application.yaml`:

```yaml
app:
  retries: 3

---
spring:
  config:
    activate:
      on-profile: dev
app:
  retries: 1
```

Run:

```bash
java -jar app.jar --spring.profiles.active=dev --app.retries=9
```

**Question:** What value of `retries` can the `@ConfigurationProperties` bean receive?

**Answer:** `9`, because command-line arguments can override YAML documents. The `dev` condition is still active, but it is not the source determining the final value for that key.

## 19. Takeaways

A concept map:

```text
One physical file (application.yaml / application.properties)
       |
       +-- Logical document 1
       |
       +-- Logical document 2 -- activation condition?
       |
       +-- Logical document 3 -- activation condition?
                    |
                    v
       Matching documents evaluated in order
                    |
                    v
       Combined with remaining configuration sources
                    |
                    v
       Environment and @ConfigurationProperties
                    |
                    v
       Beans use effective values
```

Key conclusions:

- **One physical file can contain multiple logical configuration documents.**
- **YAML** uses `---`; **`.properties`** uses `#---` or `!---` as boundaries.
- Each logical document can have its own activation condition, typically `spring.config.activate.on-profile`.
- An unconditional document is suited for shared values. When a later document is also activated, overlapping keys from an earlier document can be overridden.
- **Profile-specific documents** and **profile-specific files** are two different ways to organize configuration and can coexist.
- Document order within a file is only one part of the precedence mechanism; external files outside the JAR, environment variables, and command-line arguments can also decide the final value.
- Conditional documents are not a security mechanism and do not automatically create separate Spring beans.

When looking at a long `application.yaml` file, the first step is to locate the `---` markers to see how many logical documents exist. Then check each document's activation condition, actual active profiles, and other configuration sources. This layered reading approach helps you explain Spring Boot 3.3 configuration accurately, even when the entire content is written in a single file.

## References

- Spring Boot 3.3 Reference — Externalized Configuration, *Working With Multi-Document Files*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Externalized Configuration, *Activation Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — *Profile Specific Files* and *Property Ordering*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
