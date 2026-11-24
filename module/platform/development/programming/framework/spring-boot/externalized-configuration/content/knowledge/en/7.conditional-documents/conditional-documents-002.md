# Splitting YAML Documents with `---` and Properties with `#---` or `!---` in Spring Boot

## 1. One physical file can contain multiple configuration documents

Spring Boot lets you split **one physical configuration file** into multiple **logical documents**. Each document is a distinct group of properties and is fed into Spring Boot's Config Data mechanism. At startup, Spring Boot processes documents **from top to bottom**; a later document can override same-named properties from an earlier document if both are activated.

This is a useful way to keep default settings and condition-specific sections in **the same file**:

- First document: shared values for all environments.
- Next document: overrides when the `dev` profile is activated.
- Another document: overrides when the `prod` profile is activated.
- Cloud-platform-specific document: applied only when Spring Boot detects the matching platform, such as Kubernetes.

Key point: **the separator depends on the file format**.

| Format | Marker to start a new document | Example files |
| --- | --- | --- |
| YAML | `---` | `application.yml` or `application.yaml` |
| Java Properties | `#---` or `!---` | `application.properties` |

The two markers in Properties files are **special comment lines** that Spring Boot uses to split documents. This is a **Spring Boot Config Data** mechanism, not plain Java Properties syntax understood by every Properties reader library.

## 2. Splitting YAML documents with `---`

### 2.1. Syntax

YAML supports multi-document structure using a `---` line:

~~~yaml
app:
  name: Demo Service
  timeout: 3s

---
app:
  timeout: 10s
~~~

Logically, the file above contains two documents:

**Document 1**

~~~yaml
app:
  name: Demo Service
  timeout: 3s
~~~

**Document 2**

~~~yaml
app:
  timeout: 10s
~~~

If both documents participate and there is no higher-precedence source, the effective values are:

~~~properties
app.name=Demo Service
app.timeout=10s
~~~

The property `app.name` does not appear in document 2, so it is still taken from document 1. `app.timeout` appears in both, so the value `10s` in document 2 overrides `3s`.

### 2.2. The separator line must be in the right place

Use `---` on **its own line** at the top level of the document:

~~~yaml
app:
  timeout: 3s
---
app:
  timeout: 10s
~~~

Do not place the separator as part of a value:

~~~yaml
# The --- in the following string does not create a new document:
app:
  title: "Version A --- Version B"
~~~

Nor should you indent the separator inside the `app:` structure and expect it to act as a top-level delimiter. The document-splitting mechanism applies to the YAML document stream, not a nested key.

### 2.3. Each document is a configuration unit

Each YAML document can contain its own data tree. Spring Boot flattens hierarchical keys into property names:

~~~yaml
app:
  client:
    endpoint: https://sandbox.example.test
    timeout: 3s
---
app:
  client:
    timeout: 8s
~~~

The final result has `app.client.endpoint=https://sandbox.example.test` and `app.client.timeout=8s`. The `---` line does not force Spring Boot to discard the entire `app.client` block from the previous document; property resolution happens by property name.

However, when binding to a `List` via `@ConfigurationProperties`, a list in a higher-precedence source can **replace the entire list** from a lower-precedence source. Do not assume every structure is concatenated or deep-merged like JSON data structures.

## 3. Splitting Properties documents with `#---` or `!---`

### 3.1. Why not use plain `---` in Properties files?

Java Properties does not use the YAML document separator. For an `application.properties` file, Spring Boot designates the special comment lines `#---` or `!---` to mark the start of the next document.

Example with `#---`:

~~~properties
app.name=Demo Service
app.timeout=3s
#---
app.timeout=10s
~~~

Conceptually equivalent to the two-document YAML example earlier: `app.name` remains `Demo Service`, while `app.timeout` has the value `10s` if no other source overrides it.

You can also use `!---`:

~~~properties
app.name=Demo Service
app.timeout=3s
!---
app.timeout=10s
~~~

In Java Properties, the `#` and `!` characters normally mark comments. **Spring Boot recognizes these exact two special comment patterns as document boundaries** when loading files via Config Data.

### 3.2. Required syntax rules

Properties separator lines have stricter rules than ordinary comments:

1. **No whitespace before `#` or `!`.** The line must start right at column one.
2. **Exactly three consecutive dashes**, not two or four.
3. **No whitespace between the comment prefix and the dashes.** Write `#---` or `!---`, not `# ---` or `! ---`.
4. **The lines immediately before and immediately after the separator must not be comments with the same prefix** as the separator. For example, if using `#---`, avoid placing a `# note` line right above or right below the separator; with `!---`, avoid comment lines starting with `!` adjacent to it.

Examples that are **invalid as separators**:

~~~properties
# Wrong: has a leading space
 #---
app.timeout=10s
~~~

~~~properties
# Wrong: has whitespace between # and ---
# ---
app.timeout=10s
~~~

~~~properties
# Wrong: too few or too many dashes
#--
app.timeout=10s
~~~

~~~properties
#----
app.timeout=10s
~~~

A recommended pattern:

~~~properties
app.name=Demo Service
app.timeout=3s
#---
spring.config.activate.on-profile=prod
app.timeout=10s
~~~

The line immediately before the separator is a property and immediately after the separator is also a property; this layout avoids adjacent same-prefix comments preventing Spring Boot from recognizing the separator as intended.

### 3.3. Can `#---` and `!---` be mixed?

Both are accepted by Spring Boot as document separators in Properties files. However, project teams usually pick **one consistent style** so readers can easily spot boundaries:

~~~properties
app.timeout=3s
#---
spring.config.activate.on-profile=dev
app.timeout=5s
#---
spring.config.activate.on-profile=prod
app.timeout=15s
~~~

If the repository already uses `!---`, apply it consistently. Follow the separator and adjacent-comment rules at each boundary.

## 4. In what order are logical documents processed?

Suppose `application.yml` contains three **unconditional** documents:

~~~yaml
app:
  endpoint: https://one.example.test
  timeout: 3s
  retries: 1

---
app:
  timeout: 5s
  retries: 2

---
app:
  timeout: 8s
~~~

Spring Boot processes documents in top-to-bottom order of appearance. Within this file:

| Property | Document 1 | Document 2 | Document 3 | Final value |
| --- | --- | --- | --- | --- |
| `app.endpoint` | `https://one.example.test` | Not present | Not present | `https://one.example.test` |
| `app.timeout` | `3s` | `5s` | `8s` | `8s` |
| `app.retries` | `1` | `2` | Not present | `2` |

This illustrates the **later document overrides earlier document** rule for same-named properties. A later document does not delete a key declared in an earlier document simply because the later document does not mention that key.

Distinguish between:

- **Document order within the same file:** a lower document can override an upper document when both are activated.
- **Order across different configuration sources:** environment variables, Java system properties, or command-line arguments can have higher precedence than file data, even the last document in the file.
- **Document activation conditions:** a document containing `spring.config.activate.on-profile` or `on-cloud-platform` might **not participate** if its condition is not met.

For example, if the last document sets `app.timeout=8s` but at startup you pass `--app.timeout=20s`, the effective value is typically `20s`. The `---` marker does not make a document win over every other source.

## 5. Conditionally activating documents with `spring.config.activate.on-profile`

The strength of multi-document config files is that each document can declare **the condition under which it is used**.

### 5.1. YAML with a shared document and profile-specific documents

~~~yaml
# application.yml — shared document
app:
  endpoint: https://sandbox.example.test
  timeout: 3s
  cache-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev
app:
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  endpoint: https://api.example.test
  timeout: 12s
  cache-enabled: true
~~~

Assuming no other configuration overrides these:

| Activated profile | `app.endpoint` | `app.timeout` | `app.cache-enabled` |
| --- | --- | --- | --- |
| Neither `dev` nor `prod` | `https://sandbox.example.test` | `3s` | `false` |
| `dev` | `https://sandbox.example.test` | `5s` | `false` |
| `prod` | `https://api.example.test` | `12s` | `true` |

To activate `prod` from the CLI:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

At startup, Spring Boot evaluates each document's `on-profile` condition. The `dev` document does not participate when only `prod` is activated. The final values are determined from the **active** documents, and then remain subject to the precedence rules of other config data sources.

### 5.2. Equivalent with `application.properties`

~~~properties
app.endpoint=https://sandbox.example.test
app.timeout=3s
app.cache-enabled=false
#---
spring.config.activate.on-profile=dev
app.timeout=5s
#---
spring.config.activate.on-profile=prod
app.endpoint=https://api.example.test
app.timeout=12s
app.cache-enabled=true
~~~

This is **one Properties file containing three logical documents**. You do not need to create `application-dev.properties` and `application-prod.properties` just to express these conditions.

However, profile-specific filenames like `application-prod.yml` remain another mechanism supported by Spring Boot. Both approaches can work together in real systems; you must understand the order and effective sources when conflicts occur.

### 5.3. Profile expressions instead of a single name

`spring.config.activate.on-profile` supports profile expressions, for example:

~~~properties
app.timeout=3s
#---
spring.config.activate.on-profile=prod | staging
app.timeout=10s
~~~

The second document will be activated when the condition `prod | staging` matches: **either `prod` or `staging` profile is active**.

In YAML:

~~~yaml
app:
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "prod | staging"
app:
  timeout: 10s
~~~

You can use profile expression operators supported by Spring, such as negation `!dev` and logical combinations following the documented syntax. When using them in YAML, wrap the expression in quotes to prevent characters like `!` from being misinterpreted by the YAML parser.

## 6. Activating documents by platform with `on-cloud-platform`

Spring Boot supports:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

A document containing this condition is activated when Spring Boot **detects the corresponding cloud platform**. Example:

~~~yaml
app:
  storage:
    mode: local
    path: ./data

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  storage:
    mode: mounted
    path: /data
~~~

When running in an environment detected as Kubernetes and with no higher-precedence source overriding it, `app.storage.mode=mounted` and `app.storage.path=/data`. When the cloud platform condition is not met, the application keeps `local` and `./data` from the shared document.

With Properties:

~~~properties
app.storage.mode=local
app.storage.path=./data
!---
spring.config.activate.on-cloud-platform=kubernetes
app.storage.mode=mounted
app.storage.path=/data
~~~

Running a Docker container **does not automatically mean** the `kubernetes` condition evaluates to true. The condition is based on how Spring Boot detects the cloud platform, not simply on profile names or packaging the application in a container image.

## 7. Combining profile and cloud platform conditions

A document can simultaneously require a matching profile **and** a detected cloud platform:

~~~yaml
app:
  timeout: 3s
  endpoint: https://sandbox.example.test

---
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes
app:
  timeout: 15s
~~~

The second document participates only when **both** conditions are satisfied:

1. The profile expression `prod | staging` matches.
2. Spring Boot detects the platform as `kubernetes`.

If only `prod` is enabled but the app is not running in an environment detected as Kubernetes, the second document **does not** contribute `app.timeout=15s`; the value from the shared document may still be used.

Equivalent in Properties:

~~~properties
app.timeout=3s
app.endpoint=https://sandbox.example.test
#---
spring.config.activate.on-profile=prod | staging
spring.config.activate.on-cloud-platform=kubernetes
app.timeout=15s
~~~

This is especially useful when an environment has multiple simultaneous characteristics: the application uses the `prod` profile, but volume settings, paths, or certain operational limits apply only to Kubernetes.

## 8. Practical example: four documents in one file

Suppose a Spring Boot project has a single `src/main/resources/application.yml`:

~~~yaml
# Document 1: default
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  partner-url: https://sandbox.example.test
  timeout: 3s
  retries: 1
  audit-enabled: false

---
# Document 2: dev
spring:
  config:
    activate:
      on-profile: dev

app:
  timeout: 5s
  retries: 0

---
# Document 3: prod
spring:
  config:
    activate:
      on-profile: prod

app:
  partner-url: https://api.example.test
  timeout: 12s
  retries: 3
  audit-enabled: true

---
# Document 4: when detected as Kubernetes and running prod
spring:
  config:
    activate:
      on-profile: prod
      on-cloud-platform: kubernetes

server:
  port: 9090

app:
  timeout: 20s
~~~

Consider the cases in the following table, assuming no other property source overrides them:

| Environment | `server.port` | `app.partner-url` | `app.timeout` | `app.retries` | `app.audit-enabled` |
| --- | --- | --- | --- | --- | --- |
| Neither `dev`/`prod`, no Kubernetes detected | `8080` | Sandbox | `3s` | `1` | `false` |
| Profile `dev`, no Kubernetes detected | `8080` | Sandbox | `5s` | `0` | `false` |
| Profile `prod`, no Kubernetes detected | `8080` | Production | `12s` | `3` | `true` |
| Profile `prod` and Kubernetes detected | `9090` | Production | `20s` | `3` | `true` |

In the last case:

- Document 1 always applies, providing shared values.
- Document 2 does not apply because `dev` is inactive.
- Document 3 applies because `prod` is active.
- Document 4 applies because both `prod` and `kubernetes` match, overriding `server.port` and `app.timeout`.
- `app.partner-url`, `app.retries`, and `app.audit-enabled` are retained from document 3 because document 4 does not declare those properties.

If you run:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.timeout=25s
~~~

`--app.timeout=25s` can still override the `20s` value from the Kubernetes conditional document. Precedence between CLI and config data operates independently of how many documents the file is split into.

**Note:** The endpoints in the examples are illustrative addresses. A real deployment must configure URLs, ports, and timeouts according to its own operational requirements.

## 9. Limitations when using multi-document Properties

Multi-document `application.properties` is a feature of Spring Boot's **Config Data** processor. Two familiar Spring annotations:

- `@PropertySource`
- `@TestPropertySource`

**do not support loading multi-document Properties via this `#---`/`!---` separator mechanism**. If you use those annotations to read a Properties file directly, you cannot assume logical documents and `spring.config.activate.*` rules will be processed the same way as `application.properties` loaded by Spring Boot Config Data.

To use the multi-document feature properly, place documents in configuration that Spring Boot loads automatically, or import them via `spring.config.import` within the Config Data flow.

Example:

~~~properties
# application.properties — loaded by Spring Boot as config data
app.timeout=3s
#---
spring.config.activate.on-profile=prod
app.timeout=12s
~~~

Unlike specifying that file as a `@PropertySource` on a `@Configuration` class, the two documents here are processed through Spring Boot's configuration mechanism.

## 10. Usage in testing and development

A minimal example helps observe the final values.

Configuration `application.yml`:

~~~yaml
app:
  mode: default
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: development
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  mode: production
  timeout: 12s
~~~

A component using `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigReporter {
    public ConfigReporter(Environment environment) {
        String mode = environment.getProperty("app.mode");
        String timeout = environment.getProperty("app.timeout");
        System.out.println("mode=" + mode + ", timeout=" + timeout);
    }
}
~~~

Run the following:

~~~bash
java -jar app.jar
java -jar app.jar --spring.profiles.active=dev
java -jar app.jar --spring.profiles.active=prod
~~~

The values will be `default/3s`, `development/5s`, and `production/12s` respectively, assuming no other source supplies these properties.

When a real application uses typed configuration, you can declare `@ConfigurationProperties(prefix = "app")` to bind `timeout` to `Duration`. Logical documents only determine **the source of the property**; they do not change how configuration is accessed or bound to Java.

Do not print or log tokens, passwords, or secrets when using configuration inspection techniques.

## 11. When should you use multiple documents in the same file?

Splitting documents is a good fit when:

- Some default values are shared, with only a few small changes per profile.
- You want to see at a glance in one file which fields depend on `dev`/`prod`/cloud.
- You have short, tightly related configuration where keeping document order clear is easy.
- A single mounted file needs to hold multiple conditional configuration groups without needing multiple physical files.

When the number of documents grows large, each document becomes long, or different operations teams need independent ownership, consider splitting into profile-specific files like `application-prod.yml`, using `spring.config.import`, or providing config data from sources outside the JAR. Having many documents in one file does not by itself provide governance, security, or dynamic reloading.

The **multi-document** and **profile-specific file** approaches are not mutually exclusive. For instance, `application-prod.yml` can still contain multiple YAML documents with additional conditions, though you must pay attention to restrictions on where profile-related properties are allowed to be declared.

## 12. Rules for profile-management properties

In a conditional document, use:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

or:

~~~properties
spring.config.activate.on-profile=prod
~~~

This is the document selection condition.

**Do not place `spring.profiles.active` or `spring.profiles.include` inside a document already activated by profile**, such as a document with `spring.config.activate.on-profile=prod`. Properties that determine active profiles may only be used in profile-independent documents according to Spring Boot's rules; Spring Boot may report an invalid configuration error if they are placed in profile-specific or profile-activated documents.

An example to avoid:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: staging
~~~

The proper way to enable a profile for a run, when permitted by application design, is to pass it explicitly from an appropriate source:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Or place profile-management configuration in a source/document that is not profile-conditional and adheres to startup rules. Do not create an indirect activation loop inside a document that itself waits for a profile to be enabled.

## 13. Common mistakes and how to recognize them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `application.properties` is not split into documents | Used `---` or `# ---` instead of `#---`/`!---` | Write the exact comment separator with no leading whitespace and exactly three `-` characters |
| Properties separator is not recognized | Adjacent comment line with the same prefix | Place property lines adjacent to the separator or rearrange valid comments |
| YAML is not split into documents | `---` is inside a string or indented under another structure | Use a standalone `---` line at document level |
| `prod` config is not applied | `prod` profile is not active | Check `spring.profiles.active` and the `on-profile` condition |
| Kubernetes config is not applied | Spring Boot does not detect `kubernetes` | Check cloud platform condition and runtime environment |
| Enabled profile but still getting old value | Another property source has higher precedence | Check CLI, system properties, environment, and config data sources |
| App fails to start | Invalid YAML/Properties, unbindable value, misplaced profile configuration | Read startup errors; fix syntax and the corresponding property |
| Used `@PropertySource` but multi-document does not work | Annotation does not support Spring Boot Config Data separators | Move the file into Config Data or `spring.config.import` |
| Edited file while app is running but beans do not change | Values are loaded/bound at startup | Restart or use an intentional dedicated refresh mechanism |

During diagnostics, you can inspect effective values via `Environment` or appropriate Spring Boot Actuator endpoints such as `/actuator/env` and `/actuator/configprops` if enabled and secured. Do not expose secrets in logs or publicly open diagnostic endpoints containing sensitive information.

## 14. Exercise: determining values when multiple documents participate

Given `application.properties`:

~~~properties
app.mode=base
app.timeout=3s
app.retries=1
#---
spring.config.activate.on-profile=staging
app.mode=stage
app.timeout=7s
#---
spring.config.activate.on-profile=prod
app.mode=live
app.timeout=15s
app.retries=3
~~~

**Scenario A:** run:

~~~bash
java -jar app.jar --spring.profiles.active=staging
~~~

Result: `app.mode=stage`, `app.timeout=7s`, `app.retries=1`. The staging document overrides two keys; `retries` is retained from the shared document.

**Scenario B:** run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Result: `app.mode=live`, `app.timeout=15s`, `app.retries=3`.

**Scenario C:** run:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.timeout=30s
~~~

Result: `app.mode=live`, `app.timeout=30s`, `app.retries=3`. The command line overrides `app.timeout` from config data.

**Scenario D:** run without enabling `staging` or `prod`:

~~~bash
java -jar app.jar
~~~

Assuming no other source activates these profiles, only the shared document applies: `app.mode=base`, `app.timeout=3s`, `app.retries=1`.

This exercise shows that **a single multi-document file** can represent both default values and conditional changes, but the final result must be calculated based on which documents are activated and which sources have higher precedence.

## 15. Key takeaways

- YAML uses a `---` line to start the next document; Spring Boot processes documents in a file **from top to bottom**.
- Properties use the special comment separator `#---` or `!---`: **no leading whitespace, exactly three dashes**, and watch out for adjacent comments with the same prefix.
- A later document only overrides **matching property names** from an earlier document when both are active.
- `spring.config.activate.on-profile` and `spring.config.activate.on-cloud-platform` ensure each document is only loaded when the corresponding condition matches.
- Multi-document Properties require the **Config Data** loading flow; `@PropertySource` and `@TestPropertySource` do not support this mechanism.
- Multiple documents in one file still sit within the **overall configuration precedence order**. CLI, environment, and other sources can determine the effective value.

### References

- Spring Boot 3.3 Reference — Externalized Configuration, Working With Multi-Document Files: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.multi-document
- Spring Boot 3.3 Reference — Activation Properties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.activation-properties
- Spring Boot Reference — Profiles: https://docs.spring.io/spring-boot/reference/features/profiles.html
