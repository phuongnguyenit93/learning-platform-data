# Loading Extensionless Files Using `[.properties]` or `[.yaml]` Hints in Spring Boot

## 1. Context: configuration files without an extension

Spring Boot supports loading external configuration from Java Properties (`.properties`), YAML (`.yaml` or `.yml`), and other Config Data source types. Normally, a filename's extension tells Spring Boot how to read its content:

~~~text
/etc/my-service/application.properties  → Java Properties
/etc/my-service/application.yaml        → YAML
~~~

However, when running on Docker, Kubernetes, or a cloud platform, configuration content may be mounted as an **extensionless file**, for instance:

~~~text
/etc/config/
└── runtimeconfig
~~~

The `runtimeconfig` file might contain valid YAML:

~~~yaml
app:
  endpoint: https://api.example.test
  timeout: 8s
  enabled: true
~~~

The problem is that the path `/etc/config/runtimeconfig` does not tell Spring Boot whether to use the YAML reader or the Properties reader. When declaring a direct file import, the Config Data mechanism needs to recognize the format to parse property pairs.

Spring Boot solves this with an **extension hint**: a format hint enclosed in square brackets immediately after the import path.

~~~properties
spring.config.import=file:/etc/config/runtimeconfig[.yaml]
~~~

Here the actual file **is still named `runtimeconfig`**. The `[.yaml]` string is an instruction to Spring Boot about content format; it is not part of the filename added on disk.

## 2. What is an extension hint?

An **extension hint** is a `[.extension]` syntax suffix attached to a **config data import location** to tell Spring Boot which format parser to use when the actual file has no extension.

The two most important forms:

| Actual file content | Hint suffix | Import location |
| --- | --- | --- |
| `key=value` or `key: value` lines in Java Properties format | `[.properties]` | `file:/etc/config/settings[.properties]` |
| Hierarchical YAML | `[.yaml]` | `file:/etc/config/settings[.yaml]` |

General syntax:

~~~text
spring.config.import=[optional:]file:<extensionless-file-path>[.properties]
spring.config.import=[optional:]file:<extensionless-file-path>[.yaml]
~~~

Replace `<extensionless-file-path>` with a concrete path, such as `/etc/config/settings` or `./external/runtimeconfig`.

Component breakdown:

- `spring.config.import`: instructs Spring Boot to load an additional configuration document from a location.
- `file:`: specifies a resource on the running process's file system.
- `optional:`: allows the location to be missing without failing startup solely because the location is absent.
- `[.yaml]` or `[.properties]`: hints at the **content format**.
- The bracketed portion is **not** YAML array syntax or notation representing a separate property.

**Common mistake:** creating a file named `settings[.yaml]` on the filesystem to match the import string literally. Do not do this; the real file is named `settings`.

## 3. Example 1: importing an extensionless YAML file

Suppose a Spring Boot project has:

~~~text
src/main/resources/
└── application.yml

# Working directory when running the JAR
./
├── app.jar
└── external/
    └── runtimeconfig          # file without an extension
~~~

### Step 1 — Default configuration inside the JAR

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: config-demo
  config:
    import: "optional:file:./external/runtimeconfig[.yaml]"

server:
  port: 8080

app:
  endpoint: https://sandbox.example.test
  timeout: 3s
  retries: 2
~~~

The import line states: read `./external/runtimeconfig` as YAML if the file exists.

### Step 2 — Create the external extensionless file

Content of **`./external/runtimeconfig`**:

~~~yaml
app:
  endpoint: https://api.example.test
  timeout: 10s
  feature:
    enabled: true
~~~

Save it under the exact name `runtimeconfig`; do **not** rename it to `runtimeconfig.yaml`. On Windows, verify whether your file manager is hiding file extensions.

### Step 3 — Launch

In the working directory containing the JAR and `external/` directory:

~~~bash
java -jar app.jar
~~~

Assuming no other property source overrides them, the effective values are:

| Property | Result | Explanation |
| --- | --- | --- |
| `spring.application.name` | `config-demo` | From the common config file in the JAR |
| `server.port` | `8080` | Not declared in imported file, so default value remains |
| `app.endpoint` | `https://api.example.test` | Value from the imported extensionless YAML file |
| `app.timeout` | `10s` | Imported file overrides `3s` |
| `app.retries` | `2` | Present only in the original file |
| `app.feature.enabled` | `true` | New value added from the imported file |

This is **property-by-property overriding**, not replacing the entire original configuration with the new document. If you remove `./external/runtimeconfig`, the `optional:` prefix lets the application proceed with default values.

If the file exists yet contains invalid YAML syntax, `optional:` does **not** make malformed data valid. Configuration parsing errors must still be resolved.

## 4. Example 2: importing an extensionless Java Properties file

Suppose the platform mounts a file named `/etc/my-service/overrides` containing:

~~~properties
app.endpoint=https://api.example.test
app.timeout=12s
app.retries=4
logging.level.com.example=INFO
~~~

This uses Java Properties syntax, so declare:

~~~properties
# application.properties inside JAR
spring.config.import=optional:file:/etc/my-service/overrides[.properties]
app.timeout=3s
app.retries=2
~~~

Spring Boot uses the Properties reader to load `overrides` even though its physical name does not end with `.properties`.

Equivalent configuration when the main file uses YAML:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/my-service/overrides[.properties]"

app:
  timeout: 3s
  retries: 2
~~~

In both cases, the actual imported source file is `/etc/my-service/overrides`. There is no requirement that the main file and imported file share the same format: a YAML main file can import a Properties file and vice versa.

**Format hint tip:** use `[.properties]` if the content consists of Java Properties lines; use `[.yaml]` if the content is YAML. Changing the hint without changing the content can cause parser errors or unexpected values.

## 5. Where does `[.yaml]` belong in the import statement?

Distinguish the **actual path** from the **location configuration string**:

~~~text
Path on disk:
  /etc/config/runtimeconfig

String declared to Spring Boot:
  file:/etc/config/runtimeconfig[.yaml]
  └file:┘└────── path ──────┘└hint┘
~~~

Correct examples:

~~~properties
spring.config.import=file:/etc/config/runtimeconfig[.yaml]
~~~

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

Semantically wrong examples:

~~~properties
# Real file has no extension; below looks for a different filename:
spring.config.import=file:/etc/config/runtimeconfig.yaml
~~~

~~~properties
# Missing hint if you intend to load YAML from an extensionless file:
spring.config.import=file:/etc/config/runtimeconfig
~~~

Spring Boot does not automatically infer YAML format just because a file has YAML content when the path lacks an extension. The hint in square brackets makes the intended parser explicit.

When declaring in YAML, **wrap the entire location in double quotes** to preserve `:`, `[`, and `]` characters and help readers distinguish it from YAML syntax. When passing directly on the CLI, wrap the location or full argument in shell-appropriate quotes as well, since some shells interpret `[ ]` as pattern matching syntax.

## 6. Fixed imports and relative imports

Spring Boot supports two common location forms:

### 6.1. Fixed location

A location starting with a scheme like `file:` or `classpath:`, or an absolute path under configuration rules, is a **fixed** location. Example:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/config/runtimeconfig[.yaml]"
~~~

It points directly to `/etc/config/runtimeconfig` on the filesystem where the application runs. For containers, that means **the filesystem inside the container**, not directly the host.

A relative path that includes the `file:` scheme is also classified as fixed under Spring Boot's import classification:

~~~yaml
spring:
  config:
    import: "optional:file:./external/runtimeconfig[.yaml]"
~~~

In this example, `./external/` is resolved from **the process's working directory**. It is not automatically relative to the directory containing `application.yml` or the directory containing the JAR.

### 6.2. Import-relative location

If it does not begin with a scheme or `/`, a location can be resolved **relative to the document that declared the import**.

Suppose there are external files:

~~~text
/opt/demo/
├── application.yml
└── extra/
    └── runtimeconfig
~~~

Inside `/opt/demo/application.yml`, you can declare:

~~~yaml
spring:
  config:
    import: "extra/runtimeconfig[.yaml]"
~~~

Then the import-relative location can resolve relative to `/opt/demo/application.yml`, pointing to `/opt/demo/extra/runtimeconfig`.

Note: the `[.yaml]` portion determines only **how to read the file** after the location has been resolved. It does not change relative vs. fixed path resolution rules.

## 7. How it works during Spring Boot startup

Overall flow:

~~~text
application.yml / application.properties
           |
           v
detect spring.config.import
           |
           v
resolve location and optional:
           |
           v
extract extension hint [.yaml] / [.properties]
           |
           v
locate actual resource: /etc/config/runtimeconfig
           |
           v
select YAML / Java Properties loader
           |
           v
load document, add to Config Data / Environment
           |
           v
resolve properties by precedence order
           |
           v
@Value / @ConfigurationProperties / beans consume values
~~~

This mechanism belongs to Spring Boot's **Config Data API**, processed at startup before many application beans are created. Therefore:

- The imported file must exist **before or at startup** if it is mandatory.
- Values from the imported document can override matching keys in **the importing document**.
- If a higher-precedence property source, such as a command-line argument, also declares the same property, the higher-precedence source can still win.
- Editing a mounted file after the application is running **does not guarantee** all beans refresh automatically.

**Extension hints do not invent a new configuration type.** They allow Spring Boot to reuse the same YAML or Properties loaders already supported for files with standard extensions.

## 8. Import order and override rules

Root configuration example:

~~~yaml
spring:
  config:
    import: "optional:file:./runtimeconfig[.yaml]"

app:
  timeout: 3s
  region: vn
  retries: 2
~~~

File `./runtimeconfig`:

~~~yaml
app:
  timeout: 10s
  region: apac
~~~

`app.timeout` becomes `10s` and `app.region` becomes `apac`; `app.retries` remains `2`.

If run with:

~~~bash
java -jar app.jar --app.timeout=20s
~~~

then `app.timeout=20s` because command-line arguments have higher precedence than Config Data sources in normal setups.

One document can declare multiple imports. Example:

~~~yaml
spring:
  config:
    import:
      - "optional:file:./defaults[.properties]"
      - "optional:file:./overrides[.yaml]"
~~~

Suppose both files exist and declare `app.timeout`. With multiple imports in one declaration, Spring Boot processes them in the order listed; **a later import can override an earlier import** when both define the same property.

This differs from whole-file replacement: when `overrides` does not declare `app.region`, the value from `defaults` or the root config file can still be used.

Whether a location has a hint **does not decide precedence**. Precedence arises from the relationship among sources and imports, not from choosing `[.properties]` versus `[.yaml]`.

## 9. Extensionless files with multi-document YAML and profiles

An extensionless YAML file imported with `[.yaml]` can still contain **multiple YAML documents** separated by `---`. Example:

~~~yaml
# /etc/config/runtimeconfig (no extension)
app:
  timeout: 6s
  audit-enabled: false

---
spring:
  config:
    activate:
      on-profile: prod
app:
  timeout: 15s
  audit-enabled: true
~~~

And in `application.yml`:

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

Assuming no higher-precedence property source:

- When the `prod` profile is inactive, `app.timeout=6s` and `app.audit-enabled=false`.
- When the `prod` profile is active, the second YAML document participates and can override with `app.timeout=15s` and `app.audit-enabled=true`.

Activating the profile, for example:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

This is a practical way to maintain a single **extensionless mounted file** that still holds profile-conditional configuration.

Spring Boot also has rules for evaluating **profile-specific variants** when importing matching locations. However, with mount systems that generate custom filenames, verify the exact files actually supplied and how they are imported. Using YAML documents with `spring.config.activate.on-profile` inside one file helps express profile-specific values cleanly when a platform mounts only a single file.

## 10. Distinguishing extensionless file imports from `configtree:`

This distinction is critical when using Kubernetes ConfigMaps, Kubernetes Secrets, or Docker secrets. Platforms can mount data in **two different structural styles**.

### 10.1. One file containing many properties

~~~text
/etc/config/
└── runtimeconfig
~~~

Content:

~~~yaml
app:
  timeout: 10s
  feature:
    enabled: true
~~~

Use **file import with a hint**:

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

One file provides **multiple** properties via the YAML parser.

### 10.2. Many files, each file representing one property

~~~text
/etc/config/
└── app/
    ├── timeout
    └── feature.enabled
~~~

For example, the `timeout` file contains `10s`, and the `feature.enabled` file contains `true`. This is the **configuration tree** style, where the filename can become the property name and the file's content becomes the value.

To read this style, use:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/config/app/"
~~~

If the config tree directory is `/etc/config/app/`, Spring Boot can provide `timeout` and `feature.enabled` respectively. If you want properties to start with `app.`, choose the directory structure and import root appropriately, for instance importing from `/etc/config/` when `app/` sits beneath it.

Selection table:

| Mount style | Example | How to import |
| --- | --- | --- |
| One extensionless file holding full YAML | `/etc/config/runtimeconfig` | `file:/etc/config/runtimeconfig[.yaml]` |
| One extensionless file holding Java Properties | `/etc/config/runtimeconfig` | `file:/etc/config/runtimeconfig[.properties]` |
| A directory holding many files, one property per file | `/etc/config/app/timeout` | `configtree:/etc/config/app/` or suitable root |

Do not try to use `file:/etc/config/app/[.yaml]` to load a **directory** under config tree semantics. Extension hints specify **the content format of a single file**, whereas `configtree:` expresses the convention where each file carries one value.

## 11. Using with ConfigMap, Secret, and containers

### 11.1. ConfigMap example mounting an extensionless YAML file

A ConfigMap can contain a key named `runtimeconfig`, whose value is YAML content:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-runtime-config
data:
  runtimeconfig: |
    app:
      timeout: 12s
      region: apac
~~~

When the ConfigMap is mounted into `/etc/config/` inside the container, the file inside may appear as:

~~~text
/etc/config/runtimeconfig
~~~

If `application.yml` in the JAR declares:

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

the application can read that mounted file as YAML at startup.

For a mount backed by a **Secret**, the technical rules for extension hints remain the same; however, you must properly manage read permissions, distribution, and secret rotation. Moving a secret into an external file outside the JAR does not encrypt the secret, nor does it guarantee the application will not leak it into logs.

### 11.2. In Docker

Suppose the host has `./deploy/runtimeconfig` (no extension). The container is run with a read-only mount:

~~~bash
docker run --rm \
  -v "$PWD/deploy/runtimeconfig:/etc/config/runtimeconfig:ro" \
  my-service:1.0
~~~

This example assumes the image already launches Spring Boot and `application.yml` inside the JAR contains `file:/etc/config/runtimeconfig[.yaml]`.

Key takeaways:

- Spring Boot sees **`/etc/config/runtimeconfig` inside the container**.
- The `[.yaml]` suffix is not part of Docker's mount path.
- `:ro` makes the mount read-only; the application does not need to write changes to that file.
- For locations without `optional:`, a missing mount can cause application startup to fail.

The volume mount syntax above is an example for Unix shells. When using Windows or Docker Desktop, adjust host path syntax according to your shell and environment.

## 12. `optional:`, missing files, and malformed files

These two imports serve different purposes:

~~~properties
# File is mandatory
spring.config.import=file:/etc/config/runtimeconfig[.yaml]
~~~

~~~properties
# File may not exist
spring.config.import=optional:file:/etc/config/runtimeconfig[.yaml]
~~~

If the file **does not exist**:

- With a mandatory location, Spring Boot can halt startup and report a location-not-found error.
- With `optional:`, startup can continue using other configuration sources.

If the file **exists but has invalid format**:

- `optional:` does not turn broken YAML content into valid YAML.
- `[.properties]` does not automatically convert YAML structure into Java Properties.
- If application code requires a mandatory property that the file omits, the application can still fail at binding or validation.

Example `runtimeconfig` file containing invalid YAML:

~~~yaml
app:
  timeout: [unclosed
~~~

When imported with `[.yaml]`, the parsing error still needs to be fixed in the actual file.

Therefore, for production environments where **external configuration is mandatory**, consider omitting `optional:` and validating required values right at startup. `optional:` suits overrides used in dev or environments where the file's absence is legitimate.

## 13. Accessing properties after importing

Values from extensionless files enter `Environment` just like ordinary Config Data. Java code reading properties **does not need to know** whether the original file had an extension or an extension hint.

Example reading via `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigConsumer {
    public ConfigConsumer(Environment environment) {
        String endpoint = environment.getProperty("app.endpoint");
        String timeout = environment.getProperty("app.timeout");
        System.out.println("Endpoint: " + endpoint);
        System.out.println("Timeout: " + timeout);
    }
}
~~~

In real applications, avoid printing or logging sensitive properties such as passwords, tokens, and API keys.

For structured configuration, use `@ConfigurationProperties` to bind to a Java object:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(String endpoint, Duration timeout, int retries) {
}
~~~

Combine with `@ConfigurationPropertiesScan` on the application so Spring Boot registers and binds the record above:

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

If the imported file supplies `app.timeout: 10s`, Spring Boot can convert it to `Duration`. Binding works on **property names and effective values**, regardless of whether the imported resource had a file extension.

## 14. Troubleshooting when import does not work

When configuration in an extensionless file has no effect, check in order:

1. **Does the actual path exist?** Look for the exact `/etc/config/runtimeconfig` on the process's filesystem. With Docker/Kubernetes, check the path **inside the container**.
2. **Was an extension accidentally added when creating the file?** An actual file `runtimeconfig.yaml` differs from `runtimeconfig`. Conversely, never create a physical file named `runtimeconfig[.yaml]`.
3. **Does the hint match the content?** YAML needs `[.yaml]`; Java Properties needs `[.properties]`. Check for tabs, colons, YAML indentation, or equals signs in Properties.
4. **Where is the location declared?** Identify the file or document containing `spring.config.import` and verify Spring Boot loaded it.
5. **Fixed or import-relative?** `file:./...` resolves via the working directory, while locations without a scheme can be relative to the file declaring the import.
6. **Is `optional:` used?** If so, an absent location can be skipped; startup succeeds, yet override values do not appear.
7. **Are profiles or multiple YAML documents involved?** Check `spring.config.activate.on-profile` and activated profiles.
8. **Is the property overridden by another source?** CLI, Java system properties, environment variables, or a higher-precedence Config Data source may supply the final value.
9. **Did you mean to read a config tree instead of a single file?** If each file is a key, look at `configtree:`.
10. **Are you expecting dynamic reload?** Spring Boot normally loads Config Data at startup; editing a mounted file afterward does not automatically update already created beans.

To diagnose Config Data loading, you can enable TRACE logging for the configuration package in a controlled environment:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

If using Spring Boot Actuator with relevant endpoints enabled and properly authenticated, you can inspect `/actuator/env` and `/actuator/configprops` to see effective values. Never publicly expose endpoints that may contain configuration metadata or sensitive data.

## 15. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "`[.yaml]` is part of the real filename." | It is a **format hint** in the import string; the real file can have no extension. |
| "Any extensionless file requires `configtree:`." | Use an extension hint when **one file holds many properties**; use `configtree:` when **filenames are property names**. |
| "A YAML main file can only import YAML." | A YAML document can import a Java Properties file using `[.properties]`. |
| "Importing an extensionless file replaces all of `application.yml`." | It participates in Config Data ordering and overrides property by property; other properties can still come from the original file. |
| "`optional:` ignores syntax errors too." | `optional:` handles **location not found**, not corrupted data or binding errors. |
| "Changing the hint converts formats automatically." | The hint selects the loader; file contents must be valid for that loader. |
| "Mounted files only need to exist on the host." | With containers, they must be mounted at a path readable by **the process inside the container**. |
| "Editing the mounted file automatically updates app configuration." | Changes after startup generally require a restart or a dedicated refresh mechanism. |

## 16. Practice exercise

Suppose `application.properties` inside the JAR has:

~~~properties
spring.config.import=optional:file:./runtime[.properties]
app.name=Demo
app.timeout=3s
app.mode=default
~~~

In the working directory, create a file named **`runtime`** (no extension) containing:

~~~properties
app.timeout=8s
app.feature.enabled=true
~~~

Launch:

~~~bash
java -jar app.jar
~~~

**Question 1:** which values are used for `app.name`, `app.timeout`, `app.mode`, and `app.feature.enabled`?

**Answers:**

- `app.name=Demo` because the imported file does not declare `app.name`.
- `app.timeout=8s` because the imported file overrides `3s` from the importing document.
- `app.mode=default` because it exists only in the original file.
- `app.feature.enabled=true` because it is added from the imported file.

**Question 2:** if you rename the actual file to `runtime.yaml` yet keep the import line unchanged, what happens?

Spring Boot continues looking for **`./runtime`**, not `./runtime.yaml`. Because `optional:` is present, the missing location can be skipped and `app.timeout` reverts to `3s`. If the goal is to load `runtime.yaml`, update the location to match the actual filename.

**Question 3:** what if `runtime` contains YAML while the import still uses `[.properties]`?

Spring Boot still uses the Java Properties loader per the hint. Content that does not follow Java Properties syntax can cause errors or be interpreted differently than intended. Choose `[.yaml]` when the actual data is YAML.

## 17. Takeaways

- **Extensionless files can still be imported** using `spring.config.import` by attaching the `[.properties]` or `[.yaml]` extension hint after the resource name.
- **The hint is a parser hint**; it does not rename files on disk, create new files, or convert syntax.
- **Import and optional** have distinct roles: `spring.config.import` loads Config Data; `optional:` only permits the location to be absent.
- **Precedence rules still apply**: imported properties can override the importing file, while higher-precedence configuration sources can still override them further.
- **Distinguish mount models**: a single file containing YAML/Properties uses an extension hint; a directory of many files where filenames are keys generally uses `configtree:`.

### References

- Spring Boot 3.3 — Externalized Configuration, “Importing Extensionless Files”: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#importing-extensionless-files
- Spring Boot — Externalized Configuration / Config Data: https://docs.spring.io/spring-boot/reference/features/external-config.html
