# Adding Configuration Search Locations with `spring.config.additional-location` in Spring Boot

## 1. Problem to Solve

A Spring Boot application typically has default configuration packaged alongside its source code in `application.properties` or `application.yml`. When deploying to staging, production, Docker, or Kubernetes, the operations team may want to provide **a configuration directory outside the JAR** without editing the original file and without rebuilding the application.

For example, the JAR has this default configuration:

~~~yaml
# src/main/resources/application.yml
server:
  port: 8080

app:
  endpoint: https://sandbox.example.test
  request-timeout: 3s
  retry-count: 2
~~~

In production, we need to change the endpoint and timeout while keeping `server.port` and `app.retry-count`. We can place an `application.yml` in a separate directory and instruct Spring Boot to **add configuration search locations** using the property:

~~~properties
spring.config.additional-location=optional:file:/etc/my-service/
~~~

The most important takeaway: **`spring.config.additional-location` adds new search locations after the default locations**. It does not force the application to ignore the configuration already inside the JAR.

## 2. Concept and Syntax

`spring.config.additional-location` is a Spring Boot startup property used to declare **additional places to search for config data**. Its value is typically a list of directory or file addresses, such as:

~~~text
optional:file:./external/
file:/etc/my-service/
optional:file:./ops/application.yml
optional:classpath:/extra-config/
~~~

Components of a location:

- `file:`: reads from the filesystem of the machine or container running the application.
- `classpath:`: reads resources on the classpath, such as directories packaged inside the JAR.
- `./external/`: relative path resolved against the **working directory**, not automatically against the directory containing the JAR file.
- `/etc/my-service/`: absolute path on a Unix/Linux system.
- `optional:`: allows the location not to exist without causing a missing-location error.
- Trailing `/` on a directory path: tells Spring Boot this is a **directory location** so it automatically searches for matching configuration file names.
- Path ending with a file name, e.g., `file:/etc/my-service/application.yml`: that is a **file location**, handled as a specific file.

For a **directory location**, Spring Boot uses the default configuration name `application` (or another name specified by `spring.config.name`) to search for `.properties`, `.yaml`, and `.yml` files along with profile-specific variants. For a **file location**, Spring Boot references the named file directly; it also considers profile-specific variants when applicable.

`spring.config.additional-location` must be provided **early**, before the config data loader decides where to search. Therefore, the common ways to declare it are **command-line arguments**, **Java system properties**, or **OS environment variables**.

## 3. Where Does Spring Boot Search When Nothing Is Declared?

With typical default configuration, Spring Boot searches for `application.*` files at:

| Group | Location | Example |
| --- | --- | --- |
| Classpath | `classpath:/` | `src/main/resources/application.yml` packaged inside the JAR |
| Classpath | `classpath:/config/` | `src/main/resources/config/application.yml` |
| File system | `file:./` | `./application.yml` outside the JAR |
| File system | `file:./config/` | `./config/application.yml` |
| File system | `file:./config/*/` | `./config/mysql/application.yml`, `./config/redis/application.yml` |

`./` is resolved relative to the **working directory of the process**. When running `cd /srv/my-service && java -jar app.jar`, `file:./config/` is `/srv/my-service/config/`. If the process is launched by systemd or a container with a different working directory, the relative location changes too.

According to Spring Boot's default search order, external locations can override same-named properties from locations inside the JAR. Spring Boot also applies profile-specific file rules: `application-prod.yml` is evaluated when the `prod` profile is active.

So when adding:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/my-service/
~~~

the search list will consist of **the default locations** and **`file:/etc/my-service/` as the addition**. If this directory contains `application.yml`, matching keys in it can override the default values.

## 4. Complete Example: One JAR, One Additional External Directory

Suppose you have this deployment layout:

~~~text
/srv/my-service/
├── app.jar
└── logs/

/etc/my-service/
├── application.yml
└── application-prod.yml
~~~

Inside the JAR is `application.yml`:

~~~yaml
server:
  port: 8080

app:
  endpoint: https://sandbox.example.test
  request-timeout: 3s
  retry-count: 2
  audit-enabled: false
~~~

The external directory contains `/etc/my-service/application.yml`:

~~~yaml
app:
  endpoint: https://api.example.test
  request-timeout: 8s
~~~

And the file `/etc/my-service/application-prod.yml`:

~~~yaml
app:
  request-timeout: 12s
  audit-enabled: true
~~~

Run the application with the `prod` profile:

~~~bash
java -jar /srv/my-service/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/my-service/
~~~

Effective results in the example, assuming no higher-precedence source:

| Property | Effective Value | Source |
| --- | --- | --- |
| `server.port` | `8080` | Shared file inside the JAR: the external directory does not declare this key |
| `app.endpoint` | `https://api.example.test` | `/etc/my-service/application.yml` |
| `app.request-timeout` | `12s` | `/etc/my-service/application-prod.yml` |
| `app.retry-count` | `2` | Shared file inside the JAR: retains default value |
| `app.audit-enabled` | `true` | `/etc/my-service/application-prod.yml` |

This demonstrates three things: **adding a location outside the JAR**, **overriding by precedence**, and **preserving un-overridden keys**. `application-prod.yml` in the additional directory is evaluated because the `prod` profile is active.

If `prod` is **not activated**, `application-prod.yml` in the example will not be used as a normal profile configuration file; `app.request-timeout` will receive `8s`, and `app.audit-enabled` will remain `false` unless changed by another source.

If you also pass at runtime:

~~~bash
java -jar /srv/my-service/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/my-service/ \
  --app.request-timeout=20s
~~~

then `app.request-timeout=20s` because command-line arguments have higher precedence than config data in the example. Adding a location does not give files precedence over **every** type of configuration source.

## 5. Three Ways to Supply `spring.config.additional-location`

### 5.1. Via command-line argument

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./external/
~~~

This is straightforward when testing: the value is right inside the application launch command. The string `optional:file:./external/` is **a single location**, with the `optional:` prefix, `file:` scheme, and `./external/` directory path.

### 5.2. Via environment variable

~~~bash
export SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/my-service/
java -jar app.jar
~~~

Spring Boot recognizes the environment variable `SPRING_CONFIG_ADDITIONAL_LOCATION` as a representation of the `spring.config.additional-location` property. This is convenient when the deployment platform or container injects environment variables.

Example in PowerShell:

~~~powershell
$env:SPRING_CONFIG_ADDITIONAL_LOCATION = "optional:file:./external/"
java -jar app.jar
~~~

Variable assignment syntax belongs to the shell; the value Spring Boot receives is the same location string.

### 5.3. Via Java system property

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/my-service/ -jar app.jar
~~~

`-D...` must be placed **before `-jar`** so that it is treated as a JVM option. Conversely, `--spring.config.additional-location=...` is an application argument and is placed **after the JAR name**.

Some deployment platforms supply these values in service definitions or container manifests. The rule remains that it must be provided before the application loads config data.

### 5.4. Why not place it inside `application.yml` to add a directory?

Spring Boot needs to know `spring.config.additional-location` **at a very early stage** to determine which files to search for. Hence, the reliable way is to pass it via **environment, system properties, or CLI**. Putting this property inside the very `application.yml` you expect Spring Boot to discover may be too late to change the set of locations to load.

If the goal is for an already-loaded configuration document to **import another source**, you can use `spring.config.import` inside the configuration file. That is a different mechanism with its own import rules.

## 6. Difference Between Adding Locations and Replacing Locations

These two properties are easy to confuse:

| Property | Effect on Default Search Paths | Use Case |
| --- | --- | --- |
| `spring.config.additional-location` | **Keeps** default locations and **adds** new locations | Defaults exist in the JAR; deployment provides override files |
| `spring.config.location` | **Replaces** the default location list with the specified list | You want explicit control over where the app is allowed to search |

For example:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/
~~~

Spring Boot still checks the default locations, then checks `/etc/my-service/`. Meanwhile:

~~~bash
java -jar app.jar --spring.config.location=file:/etc/my-service/
~~~

causes the default location list to be **replaced by** the specified location. If you only want to add deployment configuration while still taking advantage of defaults inside the JAR, `additional-location` is usually better suited.

Both properties affect **config data discovery**, not the general precedence order among CLI, Java system properties, environment variables, and config data.

## 7. Adding a Specific File or an Entire Directory?

### 7.1. Adding an entire directory

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/
~~~

Spring Boot searches for files matching the current configuration name, such as:

~~~text
/etc/my-service/application.properties
/etc/my-service/application.yml
/etc/my-service/application-prod.yml   (if prod is enabled)
~~~

The critical detail is the **trailing `/`**. When defining a directory location, use the form `file:/etc/my-service/` or `file:./custom/`. Missing the `/` can cause Spring Boot to interpret the location differently from your intent of searching a directory.

### 7.2. Adding a file with a specific name

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/company-defaults.yml
~~~

Here Spring Boot uses the explicitly named file `company-defaults.yml`. When a matching profile is active, the `company-defaults-{profile}.yml` variant may also be considered under profile-specific file rules.

You do not need to rename every file to `application.yml` when using a **file location**. However, if you provide a **directory location**, Spring Boot relies on `spring.config.name` to look up properly named files; an arbitrary file like `company-defaults.yml` will not be picked up automatically just because its directory is listed.

### 7.3. Changing the base name with `spring.config.name`

By default, the base name is `application`. If launched with:

~~~bash
java -jar app.jar \
  --spring.config.name=my-service \
  --spring.config.additional-location=file:/etc/my-service/
~~~

Spring Boot will look for `my-service.properties` and `my-service.yml` variants at the locations. This name affects file discovery in directory locations, including default locations; therefore, do not change `spring.config.name` arbitrarily if you still want to use default files named `application.*`.

## 8. Adding Multiple Locations and Precedence Order

The value of `spring.config.additional-location` can list multiple locations. For example:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./ops/,optional:file:/etc/my-service/
~~~

Spring Boot processes them in the declared order. For locations in **successive precedence groups**, a location appearing later can override same-named properties from an earlier location. In a simple example:

- The file in the JAR sets `app.timeout=3s`.
- `./ops/application.yml` sets `app.timeout=5s`.
- `/etc/my-service/application.yml` sets `app.timeout=9s`.

If both additional directories exist, `app.timeout` receives `9s`, unless a higher-precedence source, such as CLI, overrides it further.

With complex sets of profile-specific files, you must understand **location groups**:

- A comma `,` separates **location groups** in the declaration; a later group is processed at a later precedence tier.
- A semicolon `;` groups locations **into the same precedence group**, which can make how profile-specific files combine differ from using commas.

For example, these two strings are **not equivalent when multiple profiles are active**:

~~~text
optional:file:./ops/,optional:file:./regional/
optional:file:./ops/;optional:file:./regional/
~~~

With profiles `prod,region-apac`, `application-prod.yml` and `application-region-apac.yml` across multiple locations can be ordered differently by **location group and profile order**. You cannot conclude the outcome merely from "which file sits in the rightmost directory." You must inspect the location list and group rules in effect.

When there is only **one** additional directory, the simplest configuration is a single location; use groups only when you genuinely need to coordinate multiple sets of profile-specific files.

## 9. `optional:` and Missing-Location Errors

By default, an explicitly declared location that does not exist can prevent the application from starting, with an error such as `ConfigDataLocationNotFoundException`.

Example of a required path:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/
~~~

If `/etc/my-service/` does not exist, Spring Boot can halt during config data discovery. This is useful when a deployment **requires** dedicated configuration to run properly.

If the directory may be absent in a development environment:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/my-service/
~~~

Then **not finding the location** will not by itself cause the application to fail. Default values can still be used.

You can add `optional:` individually per location:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./dev-overrides/,file:/etc/my-service/
~~~

In this example, `./dev-overrides/` is allowed to be absent, while `/etc/my-service/` is treated as a required location.

A few limits to remember:

- `optional:` allows a missing **location**; it does not mean syntax errors, type-binding errors, or missing passwords will be ignored.
- If the service genuinely requires values such as a database URL or API key, still validate configuration at startup.
- There is `spring.config.on-not-found=ignore` to ignore missing-location errors more broadly; use it only with a clear reason, as it can hide missing mandatory deployment files.
- A non-existent path caused by a typo will also be silently skipped if marked `optional:`, leaving the application running with unintended defaults. Observe effective configuration values during deployment.

## 10. Profile-Specific Files at Additional Locations

Suppose a deployment has:

~~~text
/etc/my-service/
├── application.yml
├── application-staging.yml
└── application-prod.yml
~~~

And the files contain:

~~~yaml
# application.yml
app:
  endpoint: https://sandbox.example.test
  timeout: 3s
~~~

~~~yaml
# application-staging.yml
app:
  timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  endpoint: https://api.example.test
  timeout: 12s
~~~

The command:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/my-service/
~~~

will consider both the shared file and `application-prod.yml` in the additional directory. The value of `app.timeout` is `12s` unless overridden by another source.

When multiple profiles are active, Spring Boot follows a **last-wins** rule when combining profile-specific config data at the same group level. For example, `--spring.profiles.active=staging,prod` allows `prod` to override same-named properties from `staging` in the appropriate context.

Do not confuse `additional-location` with activating a profile: **adding a directory does not automatically activate `prod`**. Profiles must be enabled through the profile mechanism or resolved from valid configuration before the relevant stage.

## 11. Wildcards and Mounted Configuration Directories

Spring Boot supports wildcard locations for external filesystem directories, such as:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/my-service/*/
~~~

Suppose:

~~~text
/etc/my-service/
├── database/
│   └── application.yml
└── messaging/
    └── application.yml
~~~

With the trailing directory wildcard `*/`, Spring Boot can look for `application.*` files inside **direct subdirectories** such as `database/` and `messaging/`. Wildcards are expanded and sorted by absolute path, so if multiple directories declare the same key, pay attention to the actual order.

Basic structural rules:

- Use **one** `*` in a wildcard location.
- Directory wildcards end with `*/`.
- Wildcards only support **external locations**; do not use wildcards for `classpath:`.
- Only direct subdirectories matching the pattern are scanned; do not treat `*/` as recursive across all levels.

Distinguish this form from `configtree:`. A `file:.../*/` wildcard aims to find **configuration files** in subdirectories; whereas `configtree:` is for layouts where **each file name becomes a property name and the file contents become its value** (common with secret mounts). To use a config tree, typically declare `spring.config.import=optional:configtree:/.../` rather than assuming `additional-location=file:.../` understands that structure automatically.

## 12. Configuration in Docker and Kubernetes

In containers, the idea remains separating the **artifact** from **environment-specific values**. Docker example:

~~~bash
docker run --rm \
  -v /host/my-service-config:/etc/my-service:ro \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/my-service/ \
  my-service:1.0
~~~

Assuming the image already contains the JAR and startup command, the container will receive `application.yml` from the read-only volume mount. Here:

- `/host/my-service-config` is the directory on the host, which must exist and be prepared properly.
- `/etc/my-service/` is the path **inside the container** seen by Spring Boot.
- `:ro` makes the mount read-only; the application only needs file read permissions.
- `SPRING_CONFIG_ADDITIONAL_LOCATION` is provided when the container starts so it can affect config data discovery.

In Kubernetes, you can mount a ConfigMap as YAML configuration files and provide the same environment variable. **Secrets** should be managed using the platform's security mechanisms; placing keys/passwords in a file outside the JAR does not automatically make them secure. Never commit files containing production secrets to Git simply because they live outside Java source code.

Changing an external file while the application is running **does not mean** Spring Boot automatically refreshes every bean or reapplies all properties. Typically, a controlled rollout/restart or a dedicated refresh mechanism is required.

## 13. Distinguishing `additional-location` and `spring.config.import`

Both mechanisms can supplement configuration data, but **where they are declared and how they are processed differ**.

| Characteristic | `spring.config.additional-location` | `spring.config.import` |
| --- | --- | --- |
| Typical declaration site | CLI, JVM system property, OS environment | Inside `application.yml` or another config data document |
| Purpose | Adds locations Spring Boot should search at startup | Imports additional documents from an existing config data document |
| Target | Files or directories (and supported locations) | Files, resources, config trees, or supported resolvers |
| Precedence | Added locations can override config data from default locations | Imported content can override the document that declared the import |
| Example | `--spring.config.additional-location=file:/etc/my-service/` | `spring.config.import=optional:file:/etc/my-service/extras.yml` |

Example declaring an import in `application.yml`:

~~~yaml
spring:
  config:
    import: optional:file:./extras.yml
~~~

This tells an already-loaded document to point to another file. It fits when the import relationship is an intentional part of the configuration suite. In contrast, `additional-location` fits when the **deployment environment** decides to attach a directory containing `application.*` without the source code needing to know that path in advance.

## 14. Diagnosing When Additional Configuration Does Not Take Effect

If you added a directory but the application still uses old values, check in order:

1. **Was the property passed early enough?** Check CLI `--spring.config.additional-location`, `-Dspring.config.additional-location`, or environment variable `SPRING_CONFIG_ADDITIONAL_LOCATION`. Do not put it only in a file Spring Boot does not yet know to load.
2. **Which machine does the path belong to?** When running in a container, `file:/etc/my-service/` points to the **container's** filesystem. With `file:./external/`, verify the process's actual working directory.
3. **Are you pointing to a directory or a file?** Directories must have a trailing `/`. For files, specify the full name and extension.
4. **Does the file name match?** If adding a directory, the file usually must be named `application.yml`, `application.properties`, or match `spring.config.name`.
5. **Is the profile enabled?** `application-prod.yml` participates only when the `prod` profile is active via the proper mechanism.
6. **Does the location exist?** With `optional:`, Spring Boot can continue when the path is not found; typos can therefore be silently ignored.
7. **Are there multiple locations or imports?** Check `,`, `;`, profile ordering, and imported files.
8. **Is the property overridden by a higher source?** Environment variables, Java system properties, or command-line arguments can override values just loaded from a file.
9. **Did the value bind properly?** Wrong types, unresolved placeholders, or validation errors can fail startup or cause unexpected behavior.
10. **Was the application restarted?** Normal config data loads at startup; editing a file on disk does not guarantee running beans update automatically.

When controlled visibility is needed, Spring Boot Actuator can expose configuration environment details via endpoints such as `/actuator/env` and `/actuator/configprops` if enabled and properly secured. Endpoints can involve secrets; restrict access and mask sensitive data.

You can enable diagnostic logging for config data loading in a test environment:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE \
  --spring.config.additional-location=optional:file:./external/
~~~

Enable detailed logging only as needed and do not log sensitive data.

## 15. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`additional-location` stops Spring Boot from searching config inside the JAR." | It **adds** locations, keeping the default locations. |
| "Adding a directory makes Spring Boot read every YAML name in it." | A directory location searches for names derived from `spring.config.name`, defaulting to `application`. |
| "Relative paths are resolved from where the JAR sits." | They are resolved against the process's working directory. |
| "A new file overrides the entire old file." | Overrides work **per property**; keys absent from the new file can still come from lower-precedence sources. |
| "Additional locations beat CLI and environment variables too." | They only participate in config data; higher-precedence sources can still override them. |
| "Having `application-prod.yml` in an additional location enables `prod` automatically." | Profiles must be activated through the proper mechanism. |
| "If a path is missing and has `optional:`, all configuration errors are ignored." | `optional:` only handles an absent location; configuration errors still fail. |
| "Attaching a secret file makes it secure." | File/mount permissions and proper secret management are still required. |
| "Changing a mounted config file automatically updates beans." | There is no guarantee of automatic refresh across the whole context. |

## 16. Applied Exercise

Inside the JAR:

~~~yaml
# application.yml
app:
  title: Demo
  timeout: 2s
  audit-enabled: false
~~~

The `./extra/` directory contains:

~~~yaml
# extra/application.yml
app:
  timeout: 6s
~~~

and:

~~~yaml
# extra/application-prod.yml
app:
  audit-enabled: true
~~~

The application is started from the directory containing `extra/` with the command:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./extra/
~~~

**Question:** What are the values of `app.title`, `app.timeout`, and `app.audit-enabled`?

**Answer:**

- `app.title=Demo`: the additional directory does not declare `title`, so the default in the JAR is kept.
- `app.timeout=6s`: the shared file in the additional location overrides `2s`.
- `app.audit-enabled=true`: `application-prod.yml` in the additional location is applied because the `prod` profile is active.

If `--spring.profiles.active=prod` is removed and no other source activates that profile, `app.audit-enabled` reverts to `false`. If `--app.timeout=9s` is added, timeout becomes `9s` because CLI arguments have higher precedence than configuration files.

## 17. Takeaways

**`spring.config.additional-location` is how a deployment environment expands where Spring Boot searches for config data while still using the default locations.**

Keep four points in mind when using it:

1. **Supply early:** via CLI, Java system properties, or environment variables.
2. **Distinguish paths:** directory locations end with `/`, file locations specify the file name, and `./` paths follow the working directory.
3. **Understand overrides:** additional locations can beat matching keys in default config data, but profiles, location groups, and higher-precedence sources still apply.
4. **Manage in deployment:** use `optional:` when a location may be absent, while required locations should be checked; protect secrets and trigger restarts/rollouts intentionally when new configuration must take effect.

### References

- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html