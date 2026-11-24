# Handling Missing Locations: `optional:` and `spring.config.on-not-found` in Spring Boot

## 1. Context: Not Every Environment Has the Same Configuration Files

A Spring Boot application can run from the same JAR on a laptop, test server, production host, and container. Those environments often differ in configuration:

- The JAR contains `application.yml` with shared defaults.
- A production server may mount `/etc/order-service/` with environment-specific configuration.
- A developer's laptop may not have `/etc/order-service/`.
- Some environments have `feature-flags.yml` or `secrets` as mounted volumes; other environments do not use those resources.

The question is: **if Spring Boot is instructed to load a configuration file or directory, yet that location does not exist, what should the application do?**

Spring Boot follows a **fail-fast** principle for many explicitly declared Config Data locations: if a requested location is not found, the application can stop immediately at startup and report an error. This behavior prevents the application from running with missing or wrong settings.

For locations that genuinely may be absent, Spring Boot provides two mechanisms:

1. The `optional:` prefix — ignores a missing-location error for **one specific Config Data location**.
2. The `spring.config.on-not-found=ignore` property — chooses to **ignore Config Data not-found errors broadly** during configuration loading.

These two mechanisms have different scopes. They do not replace validating properties that business logic truly requires.

## 2. Config Data and "Not Found" Errors

Config Data is Spring Boot's mechanism for reading application configuration files—typically `application.properties`, `application.yml`, or `application.yaml`—from the classpath, filesystem, or additionally declared locations. Beyond default search paths, an application can use:

| Declaration | Role |
| --- | --- |
| `spring.config.location` | Specifies a **replacement list of locations** instead of the default search locations |
| `spring.config.additional-location` | **Adds** locations to the default list |
| `spring.config.import` | **Imports** a configuration resource specified inside a Config Data document |

For example:

~~~bash
java -jar order-service.jar --spring.config.additional-location=file:/etc/order-service/
~~~

If `file:/etc/order-service/` is explicitly declared yet does not exist, Spring Boot can halt with an error such as `ConfigDataLocationNotFoundException`. The message typically names the failing location and suggests adding the `optional:` prefix if the location is permitted to be absent.

Distinguish one easily misunderstood point: Spring Boot has **default search locations**, such as `classpath:/` and `file:./config/`. It is normal for a machine not to have a default configuration directory like `./config/`; it does not mean every application must pre-create that directory. Fail-fast behavior here mainly matters when you **explicitly declare a Config Data location that must be loaded**.

If the file exists but its YAML content has syntax errors, an unsupported format, or another loading error occurs, that is a different issue from "not found."

## 3. The `optional:` Prefix: Allowing a Specific Location to Be Missing

By prepending `optional:` to a location, you tell Spring Boot:

> Try to load the configuration resource here; if the resource does not exist, continue starting up without treating its absence alone as an error.

For example:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

If `/etc/order-service/` contains valid configuration, the application loads it as usual. If the directory is absent, Spring Boot skips this location and continues using other available configuration sources.

Key syntax:

~~~text
optional:<config-data-location>
~~~

Common examples:

~~~text
optional:file:./config/
optional:file:/etc/order-service/
optional:file:/etc/order-service/override.yml
optional:classpath:/custom-settings.yml
optional:configtree:/run/secrets/
~~~

Here:

- `file:` refers to a resource on the filesystem.
- `classpath:` refers to a resource on the classpath.
- `configtree:` supports reading a directory of files where each file name becomes a property name and the file contents become its value.
- `optional:` is neither a directory nor a data type; it is a prefix controlling **missing-resource handling**.

A directory path used with `spring.config.location` or `spring.config.additional-location` normally requires a trailing `/`, so Spring Boot can append the configuration file names to search. For example, `optional:file:/etc/order-service/` denotes a directory, whereas `optional:file:/etc/order-service/custom.yml` denotes a specific file.

### 3.1. `optional:` in `spring.config.additional-location`

This is a practical choice when you want to keep defaults packaged in the JAR and supplement them with environment-optional external configuration.

Suppose the JAR contains `application.yml`:

~~~yaml
server:
  port: 8080
app:
  maintenance-mode: false
~~~

In production there may be `/etc/order-service/application.yml`:

~~~yaml
server:
  port: 9090
app:
  maintenance-mode: true
~~~

Start up:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

Outcome assuming no higher-precedence configuration source:

| Scenario | `server.port` | `app.maintenance-mode` | Application |
| --- | --- | --- | --- |
| External directory and valid file exist | `9090` | `true` | Starts with additional configuration |
| External directory does not exist | `8080` | `false` | Starts with configuration from the JAR |
| External file exists but has invalid YAML | Cannot assume | Cannot assume | Startup may fail due to syntax error |

To retain default values from the JAR, `additional-location` is usually more suitable than `location`.

### 3.2. `optional:` in `spring.config.location`

For example:

~~~bash
java -jar order-service.jar --spring.config.location=optional:file:/etc/order-service/
~~~

This command differs from the previous example: `spring.config.location` **replaces** the default search location list. If the external directory is absent, the application can ignore the not-found error, yet **this does not automatically restore searching for `application.yml` in the JAR via the replaced default locations**.

An application may still fail to run if essential values such as a datasource URL are missing. Therefore:

- Choose `spring.config.location` when you genuinely want to take control of the entire location list.
- Choose `spring.config.additional-location` when you want packaged defaults to remain loaded and only add deployment configuration.

If you want to use `location` while still including the classpath, you must list the needed classpath locations explicitly, for example:

~~~bash
java -jar order-service.jar --spring.config.location=classpath:/,optional:file:/etc/order-service/
~~~

Locations are separated by commas. When a list mixes required and optional locations, `optional:` applies only to the element carrying the prefix; it does not automatically make all remaining elements optional.

### 3.3. `optional:` in `spring.config.import`

A configuration document can import another resource elsewhere:

~~~yaml
# application.yml packaged inside the JAR
spring:
  application:
    name: order-service
  config:
    import: "optional:file:./config/feature-flags.yml"

app:
  checkout:
    enabled: false
~~~

If `./config/feature-flags.yml` exists:

~~~yaml
app:
  checkout:
    enabled: true
~~~

Spring Boot loads the imported document, and imported configuration can override `app.checkout.enabled` from the document declaring the import. If the file does not exist, the application can continue with `false` from the packaged file.

`spring.config.import` fits when a file needs to specify a **particular resource** to import, rather than adding an entire directory to the `application.*` search list.

**Note:** `file:./config/feature-flags.yml` is resolved relative to the process's **working directory**. The directory containing the JAR is not automatically the working directory. If you need a path independent of where the command is invoked, use an absolute path or a consistent deployment strategy.

## 4. `spring.config.on-not-found=ignore`: Ignoring Missing Config Data Broadly

In some situations, you want to configure a policy so any missing Config Data location is ignored. Spring Boot supports:

~~~properties
spring.config.on-not-found=ignore
~~~

Example via program argument:

~~~bash
java -jar order-service.jar --spring.config.on-not-found=ignore
~~~

Or via Java system property:

~~~bash
java -Dspring.config.on-not-found=ignore -jar order-service.jar
~~~

Or setting an environment variable:

~~~bash
export SPRING_CONFIG_ON_NOT_FOUND=ignore
java -jar order-service.jar
~~~

This is a **global policy setting for handling missing Config Data locations**. If a location lacks `optional:` and does not exist, the `ignore` policy can allow configuration loading to continue instead of failing on that kind of missing-location error.

Core difference:

- `optional:` states that **this specific location** may be absent.
- `spring.config.on-not-found=ignore` states that **Config Data location-not-found errors in general** may be ignored.

For example, when there are two locations:

~~~bash
java -jar order-service.jar --spring.config.additional-location=file:/etc/order-service/,file:/mnt/team-config/
~~~

If one of the required locations does not exist, the application can halt. When adding:

~~~bash
java -jar order-service.jar --spring.config.on-not-found=ignore --spring.config.additional-location=file:/etc/order-service/,file:/mnt/team-config/
~~~

Spring Boot is instructed to ignore not-found errors covered by this policy. However, if the application needs a key present only in a skipped location, binding, validation, or bean-creation failures can still occur afterward.

### 4.1. `on-not-found` must be supplied early

`spring.config.on-not-found` governs the **Config Data loading** process. Hence, the clearest approach is to pass it in a source already available at startup: program arguments, Java system properties, or environment variables.

Do not rely on placing `spring.config.on-not-found` inside **the very file that is missing**, because Spring Boot cannot read a non-existent file to retrieve the instruction to ignore its own absence.

### 4.2. Why shouldn't you enable `ignore` everywhere?

Production configuration typically includes mandatory resources: payment endpoints, database host addresses, certificate configurations, or security parameters. If a typo in the path to these files occurs while all "not found" errors are ignored, the application may:

1. Run with default values not meant for production.
2. Start up yet only uncover missing configuration when a user invokes a feature.
3. Raise secondary errors, making the root cause of a missing file harder to identify.

Therefore, prefer `optional:` for truly optional files and preserve **fail-fast** behavior for mandatory files. Use `spring.config.on-not-found=ignore` when there is a clear reason for blanket ignoring, paired with checks for required configuration in subsequent steps.

## 5. Direct Comparison of the Three Declarations

Suppose `/etc/order-service/` **does not exist**. Shared configuration in the JAR is present, and there are no other errors.

| Launch Command | Behavior When External Location Is Missing | Scope |
| --- | --- | --- |
| `--spring.config.additional-location=file:/etc/order-service/` | Usually halts during Config Data discovery | The external location is required |
| `--spring.config.additional-location=optional:file:/etc/order-service/` | Skips the external location, continues with other sources | Only the location prefixed with `optional:` |
| `--spring.config.on-not-found=ignore --spring.config.additional-location=file:/etc/order-service/` | Can ignore this not-found error | Global policy for Config Data |

With two declared locations:

~~~text
file:/etc/order-service/,optional:file:/etc/order-service/local-overrides/
~~~

Only `local-overrides/` has `optional:`. `/etc/order-service/` remains a required location. Pay close attention to the boundaries of each element, especially when the value contains multiple comma-separated locations.

`optional:` does not make a location load earlier or later, does not alter property precedence, and does not turn a missing value into a default value. It only affects **whether startup stops due to a missing resource**.

## 6. Distinguishing "Not Found" from Other Configuration Errors

A dangerous mistake is believing that adding `optional:` makes a broken configuration valid. That is not the case.

| Scenario | Is `optional:` the Right Solution? | How to Handle |
| --- | --- | --- |
| An optional file does not exist at all | Yes | Skip it and use remaining configuration sources |
| An extra directory on a laptop has not been created | Yes, if genuinely optional | Use `optional:file:.../` |
| A mandatory production configuration file does not exist | Should not use | Keep fail-fast; fix the mount, path, or provisioning workflow |
| A YAML file exists but has bad indentation or invalid syntax | No | Fix the YAML content |
| A file sets `app.timeout` but the value cannot convert to `Duration` | No | Fix the value or binding type |
| A file was read yet is missing a mandatory business key | Does not solve it | Provide the required key or configure validation |
| The resource exists yet read permission is denied | Do not expect `optional:` to handle it | Check file permissions and process permissions |
| The resource path has invalid syntax | No | Fix the location/import syntax |

Conceptually, `optional:` is for **valid absence**, not for masking any form of data error. Similarly, `on-not-found=ignore` does not mean "ignore every startup error in a Spring Boot application."

## 7. Real-World Example: One JAR, Three Environments

Suppose a notification service has default configuration in `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: notification-service

app:
  notification:
    enabled: false
    max-attempts: 2
  report:
    format: csv
~~~

In production there may be `/etc/notification-service/application.yml`:

~~~yaml
app:
  notification:
    enabled: true
    max-attempts: 5
~~~

Launch command for both laptop and production:

~~~bash
java -jar notification-service.jar --spring.config.additional-location=optional:file:/etc/notification-service/
~~~

**On a laptop:** `/etc/notification-service/` does not exist. The application proceeds with `notification.enabled=false`, `max-attempts=2`, and `report.format=csv`.

**In production:** the directory and configuration file are present. The application receives `notification.enabled=true`, `max-attempts=5`, while `report.format=csv` continues to come from the JAR.

**In production when the mount is forgotten:** the application can also start using default values from the JAR. This is precisely the risk if the external file is actually **mandatory**. In that case, do not mechanically add `optional:`; use a required location or explicitly verify production configuration before serving requests.

If the requirement is "production must have its own policy file," production can be deployed with a command **without** `optional:`:

~~~bash
java -jar notification-service.jar --spring.config.additional-location=file:/etc/notification-service/
~~~

The proper design is deciding whether a resource is **mandatory or optional by operational semantics** before choosing the syntax.

## 8. Combining with Profiles and Precedence Order

Spring Boot can load both `application.yml` and profile-specific files such as `application-prod.yml`. External configuration has similar variants. For example:

~~~text
classpath:/application.yml
classpath:/application-prod.yml
file:./config/application.yml
file:./config/application-prod.yml
~~~

When the `prod` profile is active, multiple sources can define the same key such as `server.port`. The final value is decided by **precedence order among sources**.

Adding `optional:` to an external directory only allows **that directory to be absent** without triggering a missing-location error. It does **not** give external files lower precedence, nor does it give packaged files higher precedence when the external file exists.

For example:

~~~bash
java -jar service.jar --spring.profiles.active=prod --spring.config.additional-location=optional:file:/etc/service/
~~~

- If `/etc/service/application-prod.yml` is present and valid, it can override values in the identically named packaged file.
- If `/etc/service/` does not exist, remaining configurations are still loaded according to standard rules.
- If another source has higher precedence, such as `--server.port=7070`, that value can beat values from all Config Data files.

Therefore, when analyzing outcomes, answer two questions in order: **which sources were loaded?** and then **which source has higher precedence for the key in question?**

## 9. Config Trees and Deployment Secrets

A common pattern in container environments is mounting files via volumes, such as:

~~~text
/run/secrets/
  payment.username
  payment.password
~~~

Spring Boot can import these values as a configuration tree:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

If the directory is mounted, file names map to property names and file contents are loaded as values. If the directory does not exist, the `optional:` prefix lets startup continue.

However, think carefully about the role of those files:

- For **feature flags** with safe defaults, an absent directory may be acceptable.
- For mandatory **database credentials or signing keys**, allowing the files to be skipped could leave the application running without critical secrets.

If secrets are mandatory, use a path without `optional:` and validate required properties. Do not put real passwords in examples, committed files, or print all configuration values to logs for diagnostics.

## 10. Where to Place Configuration So Spring Boot Sees It in Time

Several properties govern the **Config Data discovery and reading process itself**, including:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`
- `spring.config.on-not-found`

These properties must be available before or during the phase when Spring Boot sets up Config Data reading. Typical sources are command-line arguments, Java system properties, or environment variables.

For example:

~~~bash
java -Dspring.config.on-not-found=ignore -jar service.jar --spring.config.additional-location=file:/opt/service/optional/
~~~

Or in Docker Compose:

~~~yaml
services:
  service:
    image: example/service:latest
    environment:
      SPRING_CONFIG_ADDITIONAL_LOCATION: "optional:file:/etc/service/"
    volumes:
      - ./config:/etc/service:ro
~~~

The Compose example above illustrates passing an optional location. In practice, volume mounting, read permissions, and existence of the source directory depend on deployment setup.

Meanwhile, `spring.config.import` is normally declared inside an already-loaded Config Data document:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/service/feature-flags.yml"
~~~

Do not place the directive to locate a missing document inside that document itself, because a non-existent file cannot supply a value to rescue discovery.

## 11. Diagnosing Failures When the Application Does Not Start

When seeing messages related to Config Data, check sequentially:

1. **Identify the location:** does the log report missing `file:/...`, `classpath:/...`, or `configtree:/...`? Which parameter passed that path?
2. **Determine requirement level:** is this resource an optional default, a developer add-on, or a mandatory production requirement?
3. **Check the working directory:** for `file:./...`, is the process's current directory what you expected?
4. **Check paths and mounts:** did the container or host actually provide the file/directory? Do casing and extension match?
5. **Check location syntax:** directory paths use a trailing `/` where appropriate; `optional:` is attached to the intended element in the list.
6. **Check the declaration source:** is `spring.config.location` replacing default locations, or is `spring.config.additional-location` only adding?
7. **If the file is present yet still errors:** read the parser message, permissions, type conversion, and validation errors. Do not treat it as a missing-file error.

If you want to specifically test `optional:` behavior, use a non-existent file/path in a test environment and confirm the application still has enough required values to start. If you want to test fail-fast behavior, use the same path without `optional:`.

Do not automatically switch everything to `spring.config.on-not-found=ignore` before understanding which resource is missing; doing so can hide useful information about deployment mistakes.

## 12. Common Misconceptions

| Wrong Claim | Correct Explanation |
| --- | --- |
| "If default `./config/` is missing, Spring Boot always errors." | Default locations may be absent; fail-fast behavior matters especially for locations explicitly specified as required to load. |
| "`optional:` ignores YAML errors." | It handles missing Config Data locations/resources; it does not guarantee ignoring syntax errors. |
| "`optional:` gives a file lower precedence." | Property precedence is a separate mechanism; the prefix only affects missing resources. |
| "`spring.config.on-not-found=ignore` applies to only one file." | It is a broad policy for Config Data not-found errors. |
| "`spring.config.location` with `optional:` automatically falls back to all default files in the JAR." | `location` replaces the default location list; `optional:` does not restore the replaced list. |
| "If a mandatory secret file is missing, adding `optional:` fixes it." | Fix the secret provisioning workflow or fail fast; do not mask configuration gaps. |
| "If the application starts, all required values are valid." | Some errors only surface during binding, bean creation, or request handling if validation is missing. |

## 13. Self-Check Exercises

### Exercise 1 — Optional location

An application has configuration inside the JAR:

~~~yaml
app:
  greeting: "Hello"
~~~

Launch command:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/opt/app/overrides/
~~~

`/opt/app/overrides/` does not exist. Assuming no other errors or overrides, what is the result?

**Answer:** the application can continue starting, and `app.greeting` retains the value `Hello` from the JAR. The absence of an optional directory is not an error.

### Exercise 2 — Required location

Using the command:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/opt/app/required/
~~~

`/opt/app/required/` does not exist. Should you add `optional:` if the production application strictly requires this configuration?

**Answer:** normally **no**. Fix the step that provisions the directory/file. Halting immediately when mandatory configuration is missing helps catch deployment mistakes.

### Exercise 3 — Global or per-location?

Given two declarations:

~~~text
A) --spring.config.additional-location=optional:file:/opt/app/overrides/
B) --spring.config.on-not-found=ignore
~~~

Which one allows only the stated location to be missing; which one changes the general policy?

**Answer:** A affects only `/opt/app/overrides/`. B applies a broader policy for Config Data not-found errors.

### Exercise 4 — `location` vs. `additional-location`

A JAR contains `classpath:/application.yml`. Run:

~~~bash
java -jar app.jar --spring.config.location=optional:file:/opt/app/missing/
~~~

The external directory does not exist. Can you conclude that the default file in the JAR is guaranteed to still be loaded?

**Answer:** **no**. `spring.config.location` replaces the default search list, so `optional:` does not automatically restore replaced classpath locations. If you want to retain packaged configuration, choose `additional-location` or explicitly declare the needed classpath locations.

### Exercise 5 — File exists but is invalid

The file `/etc/service/extra.yml` exists yet contains invalid YAML syntax. `application.yml` has:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/service/extra.yml"
~~~

Can you trust that Spring Boot will ignore the file content error because `optional:` is present?

**Answer:** **no**. `optional:` allows a missing resource, while an existing file with invalid syntax is a different error that must be fixed.

## 14. Takeaways

- When a **required Config Data location** does not exist, Spring Boot can halt startup to report the error early.
- Use `optional:` when a **specific file or directory is genuinely permitted to be absent**.
- Use `spring.config.on-not-found=ignore` when you intentionally want to **broadly ignore Config Data not-found errors** and have other safeguards for essential configuration.
- `spring.config.additional-location` adds locations, whereas `spring.config.location` replaces the default search locations.
- `optional:` does not alter precedence order, does not ignore YAML errors, and does not provide default values for required keys.
- For mandatory production configuration, **fail-fast behavior and explicit validation** are generally safer.
- Check the working directory, paths, mounts, file names, and property sources before changing error-handling behavior.

**Reference:** [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).