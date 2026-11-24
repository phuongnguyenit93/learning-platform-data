# Wildcard Locations and Search Order of External Configuration Directories in Spring Boot

## 1. Why Understand Wildcard Locations?

In a Spring Boot application, the same JAR build can run across multiple environments with different external configuration. Instead of packaging every value in `src/main/resources/application.properties`, operators can place `application.properties` or `application.yml` files in directories outside the JAR.

When an application has multiple independently mounted configuration sets, such as `config/database/`, `config/redis/`, and `config/messaging/`, having to list each path individually makes startup configuration hard to maintain. **Wildcard locations** solve this problem: a single path pattern lets Spring Boot examine direct subdirectories of a parent directory.

For example:

~~~text
/workspace/
├── app.jar
└── config/
    ├── database/
    │   └── application.properties
    ├── messaging/
    │   └── application.yml
    └── redis/
        └── application.properties
~~~

If the application runs with `/workspace` as its working directory, the default location `file:./config/*/` can find `application.*` files in all three subdirectories. This is a feature of **Spring Boot Config Data** in modern Spring Boot versions, not a shell glob and not a feature built into plain Spring Framework automatically.

Two questions must be kept separate:

1. **Which files does Spring Boot find?** This depends on configuration name, locations, wildcards, profiles, and working directory.
2. **If multiple files contain the same key, which value wins?** This depends on location precedence, location groups, profiles, and other configuration sources.

Understanding these two steps prevents assuming that the OS directory listing order or file creation order decides the effective configuration.

## 2. Default Search Locations

When `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are not changed, Spring Boot looks for files with base name `application` in the default Config Data locations. The location groups in ascending precedence order can be represented as:

| Group | Search Location | Meaning |
| --- | --- | --- |
| Classpath | `optional:classpath:/` | Classpath root, usually holding `application.properties` packaged in the JAR |
| Classpath | `optional:classpath:/config/` | The `config` directory on the classpath |
| Outside JAR | `optional:file:./` | The current working directory |
| Outside JAR | `optional:file:./config/` | The `config` directory in the current working directory |
| Outside JAR | `optional:file:./config/*/` | Direct subdirectories inside `./config/` |

In the official documentation, default locations are organized into **groups** (locations in the same group are separated by `;`). They can be summarized as two groups:

~~~text
optional:classpath:/;optional:classpath:/config/
optional:file:./;optional:file:./config/;optional:file:./config/*/
~~~

The group outside the JAR has higher precedence than the classpath group when both define the same property. Beyond location order, Spring Boot also considers profile-specific file variants, such as `application-prod.properties`.

**Practical rule:** `application.properties` packaged inside the JAR normally provides default values; files outside the JAR can override those values. If the same key is declared multiple times across locations with different precedences, the higher-precedence source determines the value used.

Do not read the table above as the complete precedence order of **all** configuration sources. Command-line arguments, Java system properties, environment variables, `@PropertySource`, and other sources have their own precedence order. For example, `--server.port=9090` can normally override `server.port` read from an external file.

### 2.1. `./` depends on the working directory, not the directory containing the JAR

Suppose the JAR sits at `/opt/app/app.jar`:

~~~bash
cd /opt/app
java -jar app.jar
~~~

Here `file:./config/` corresponds to `/opt/app/config/`. But if you run:

~~~bash
cd /tmp
java -jar /opt/app/app.jar
~~~

then `file:./config/` points to `/tmp/config/`. Both commands run the same JAR yet can read different external configuration sets.

In containers, the working directory may be set by `WORKDIR` in a Dockerfile or `workingDir` in a Pod. When unsure where configuration is being searched, check the process's working directory before inspecting file contents.

## 3. What Is a Wildcard Location?

A wildcard location is a Config Data address containing a `*` character in the **appropriate trailing segment of the path**. Spring Boot expands this pattern while loading configuration to inspect direct subdirectories of the parent directory.

For example:

~~~text
file:./config/*/
~~~

This means: find direct subdirectories of `./config/`, then search for matching configuration files inside each of those subdirectories.

With this layout:

~~~text
config/
├── database/
│   └── application.properties
├── cache/
│   └── application.properties
├── nested/
│   └── deep/
│       └── application.properties
└── application.properties
~~~

`file:./config/*/` examines:

- `config/cache/` and `config/cache/application.properties`;
- `config/database/` and `config/database/application.properties`;
- `config/nested/` if a matching configuration file exists directly inside that directory.

This pattern **does not recurse** into `config/nested/deep/application.properties`. The parent directory's `config/application.properties` is handled by `file:./config/`, not by the wildcard in `file:./config/*/`.

### 3.1. Valid syntax

Under Spring Boot Config Data wildcard rules, only **one `*`** may be used in a wildcard location, and it must appear in the valid form at the end of the path:

| Configuration | Interpretation |
| --- | --- |
| `file:./config/*/` | Directory pattern: searches for configuration file names in each direct subdirectory |
| `file:./config/*/application.properties` | File pattern: searches for the named file in each direct subdirectory |
| `file:/etc/myapp/*/` | Directory pattern under an absolute path |
| `file:/etc/myapp/*/application.yml` | YAML file pattern one subdirectory level deep |
| `classpath:/config/*/` | Unsupported: wildcards are only for external locations |
| `file:./config/**/` | Not a supported recursive wildcard syntax here |
| `file:./*/services/*/` | Invalid because there are multiple `*` characters and an unsupported wildcard structure |

For a directory wildcard, the pattern must end with `*/`. For a file wildcard, the pattern has the form `*/<filename>`. Specifically, `file:` indicates a filesystem location; do not replace it with `classpath:` to scan subdirectories inside a JAR.

### 3.2. Do not confuse with shell globs

In the following command, `*` is part of a property value parsed by Spring Boot:

~~~bash
java -jar app.jar "--spring.config.additional-location=optional:file:./config/*/"
~~~

This is not asking the shell to list files before Java runs. Keeping the whole argument in quotes is good practice for readability and avoids unwanted shell expansion when values contain special characters.

Unlike `find`, `ls`, or `**` globs in some tools, Spring Boot applies its own specific Config Data wildcard rules; do not assume all shell glob patterns are supported.

## 4. How Are Wildcards Expanded and Ordered?

### 4.1. Only direct subdirectories are considered

With `file:./config/*/`, Spring Boot lists the direct subdirectories of `./config/` and expands each directory into a concrete location.

For example:

~~~text
/workspace/config/
├── 10-base/
│   └── application.properties
├── 20-database/
│   └── application.properties
└── 30-overrides/
    └── application.properties
~~~

The wildcard pattern expands to locations corresponding to `10-base`, `20-database`, and `30-overrides`. With a directory pattern, Boot uses the base file name specified by `spring.config.name` (defaulting to `application`) and considers appropriate formats and profile variants.

### 4.2. Alphabetical order by absolute path

**Spring Boot sorts expanded wildcard locations alphabetically based on the file's absolute path.**

With the three directories under the same parent directory, the order can be pictured as:

~~~text
/workspace/config/10-base/application.properties
/workspace/config/20-database/application.properties
/workspace/config/30-overrides/application.properties
~~~

If the same property is declared in all three files under the same loading scenario and same profile tier, the value from the source evaluated later can override earlier sources according to **last wins**.

For example:

~~~properties
# config/10-base/application.properties
app.retry-count=1
app.region=ap-southeast-1
~~~

~~~properties
# config/20-database/application.properties
app.retry-count=2
database.pool-size=20
~~~

~~~properties
# config/30-overrides/application.properties
app.retry-count=5
~~~

When no higher-precedence source overrides them:

| Key | Effective Value | Reason |
| --- | --- | --- |
| `app.retry-count` | `5` | Declared last among the corresponding wildcard locations |
| `app.region` | `ap-southeast-1` | Declared only in `10-base` |
| `database.pool-size` | `20` | Declared only in `20-database` |

Note: this last-wins interpretation applies to a straightforward scenario within one location group, without profile or import differences. With complex profile-specific configurations, you must also consider **location groups** before concluding which source wins.

**Alphabetical order is not based on:** directory creation time, file modification time, volume mount order, display order in Explorer, or the order returned by the OS when listing a directory.

### 4.3. Do not base operational precedence solely on directory names

Some teams deliberately use names like `00-defaults`, `50-services`, and `99-overrides` to create predictable ordering with wildcards. This can work in simple configuration sets, but renaming or adding a new directory can alter effective values.

When you need exact control over the order of configuration groups with overlapping keys, list the concrete locations explicitly in the desired order instead of relying solely on wildcard alphabetical sorting.

For example:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/base/,optional:file:/etc/myapp/overrides/"
~~~

Under matching location organization, `overrides/` placed later can override `base/`. If using profile-specific properties, also check the effect of `,` and `;`.

## 5. Differences Between `spring.config.location` and `spring.config.additional-location`

### 5.1. `spring.config.location` replaces default locations

When declared as:

~~~bash
java -jar app.jar \
  "--spring.config.location=optional:file:/etc/myapp/*/"
~~~

Spring Boot uses the configured locations to **replace** the default search locations. As a result, `application.properties` files packaged inside the JAR or in `./config/` are no longer searched via the default list unless included in the new locations appropriately.

This is the right tool when operators want full control over where the application reads configuration from. However, if you only want to add supplementary configuration, replacing all default search paths can drop default values the application relies on.

### 5.2. `spring.config.additional-location` adds locations

When declared as:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/"
~~~

Spring Boot still searches the default locations, then adds the configured location. Values loaded from additional locations can override default values inside the JAR.

This is a common choice when distributing a JAR with default configuration and letting deployers mount extra external configuration directories.

### 5.3. Location-selecting properties must be present very early

`spring.config.location`, `spring.config.additional-location`, and `spring.config.name` are used as soon as Spring Boot determines which files to load. Therefore, place them in sources available at startup:

- command-line arguments, such as `--spring.config.additional-location=...`;
- environment variables, such as `SPRING_CONFIG_ADDITIONAL_LOCATION`;
- Java system properties, such as `-Dspring.config.additional-location=...`.

Do not expect placing `spring.config.location` in a file discovered too late to make Boot go back and search other locations in an unsupported way. Distinguish **choosing where to look for files** from **reading file contents**.

Example with an environment variable on Linux:

~~~bash
export SPRING_CONFIG_ADDITIONAL_LOCATION="optional:file:/etc/myapp/*/"
java -jar app.jar
~~~

Example with a JVM system property:

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/myapp/*/ -jar app.jar
~~~

When running via a shell that interprets special characters, wrap the value in quotes to avoid argument parsing errors.

### 5.4. Directories have a trailing `/`; files have full names

If declaring a **directory** in `spring.config.location` or `spring.config.additional-location`, the location must end with `/`. Spring Boot uses `spring.config.name` to form the file names to search inside that directory.

~~~properties
# Directory: Boot searches for application.properties, application.yml...
spring.config.additional-location=optional:file:./config/custom/
~~~

If declaring a specific **file**, use the full file name:

~~~properties
# Directly specified file
spring.config.additional-location=optional:file:./config/custom/custom.properties
~~~

With wildcards, the corresponding forms are `file:./config/*/` or `file:./config/*/custom.properties`. A location pointing to a specific file does not mean Boot will automatically read every differently named file in the directory.

## 6. `optional:` and Missing-Directory Scenarios

When an explicitly declared location does not exist, Spring Boot can raise `ConfigDataLocationNotFoundException` and halt startup.

To allow skipping a non-existent location, prepend `optional:`:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/"
~~~

This fits environment-optional mounts especially well: an external directory may exist in production while not existing on a developer's laptop.

`optional:` **does not mean** Boot ignores all errors in files that are found. A file that exists with invalid syntax, unconvertible values, or configuration errors can still cause application startup to fail.

Another mechanism is `spring.config.on-not-found=ignore` to ignore missing-location errors more broadly. When possible, prefer `optional:` on each individual location to express clearly which ones are permitted to be absent.

## 7. Location Groups and Override Order Across Profiles

From Config Data's perspective, a **location group** is a set of locations evaluated at the same level. Two important separator characters are:

- Comma `,`: separates locations or location groups to evaluate sequentially; a later location can override an earlier location.
- Semicolon `;`: joins multiple locations into **the same group**, so profile-specific files apply at the same precedence level.

This is not merely string formatting: when an application has multiple active profiles, using `,` versus `;` can change which property wins.

### 7.1. Example not using the same group

Suppose these files exist:

~~~text
cfg/
└── application-live.properties
ext/
└── application-prod.properties
~~~

~~~properties
# cfg/application-live.properties
app.mode=cfg-live
~~~

~~~properties
# ext/application-prod.properties
app.mode=ext-prod
~~~

Two active profiles: `prod,live`.

Launch:

~~~bash
java -jar app.jar \
  "--spring.profiles.active=prod,live" \
  "--spring.config.location=optional:file:./cfg/,optional:file:./ext/"
~~~

With two locations separated by a comma, all matching files in `cfg/` are processed before files in `ext/`. In this example, `ext/application-prod.properties` is evaluated later and can override `app.mode` to `ext-prod`, even though `live` follows `prod` in the profile list.

### 7.2. Example joining into the same location group

If you want both directories at the same precedence tier:

~~~bash
java -jar app.jar \
  "--spring.profiles.active=prod,live" \
  "--spring.config.location=optional:file:./cfg/;optional:file:./ext/"
~~~

The `;` puts `cfg/` and `ext/` in the same group. When profile-specific files are evaluated at the group tier, profile `live` is evaluated after `prod`. In this example, `cfg/application-live.properties` can be the winning source and `app.mode` receives `cfg-live`.

General profile-specific rule: `application-{profile}.properties` files are searched in the same locations as base files; when multiple profiles are active, values belonging to a profile listed later can override an earlier profile **at the location group level**. This is why you must check both group structure and file paths when explaining an effective value.

### 7.3. How do wildcards interact with location groups?

A wildcard such as `file:./config/*/` expands into subdirectories sorted alphabetically. If the system also has other additional locations or multiple profiles, final ordering and precedence depend on where the wildcard sits in the location string and how location groups are defined.

For example:

~~~bash
java -jar app.jar \
  "--spring.profiles.active=prod" \
  "--spring.config.additional-location=optional:file:./config/*/,optional:file:/etc/myapp/overrides/"
~~~

The wildcard pattern reads subdirectories of `./config/`, after which `/etc/myapp/overrides/` is evaluated as an additional location after it according to the configuration. To group sources into the same tier, deliberately use `;` and verify the group's profile rules.

**There is no absolute rule that "the alphabetically last folder always wins in every situation."** That is only a predictable outcome within a simple wildcard location tier when no other source, import, or profile at another precedence level intervenes.

## 8. Real-World Deployment Example with Mounted External Directories

### 8.1. One JAR, multiple configuration directories

Suppose a service is deployed in `/srv/orders`:

~~~text
/srv/orders/
├── orders.jar
└── config/
    ├── inventory/
    │   └── application.properties
    ├── messaging/
    │   └── application.properties
    └── payment/
        └── application-prod.properties
~~~

The files:

~~~properties
# config/inventory/application.properties
orders.inventory.timeout=3s
orders.inventory.max-retries=2
~~~

~~~properties
# config/messaging/application.properties
orders.messaging.topic=orders.events
orders.messaging.enabled=true
~~~

~~~properties
# config/payment/application-prod.properties
orders.payment.endpoint=https://payments.example.test
~~~

Run:

~~~bash
cd /srv/orders
java -jar orders.jar --spring.profiles.active=prod
~~~

Because the default locations include `file:./config/*/`, Spring Boot can examine `inventory`, `messaging`, and `payment`. With the `prod` profile active, `application-prod.properties` inside `payment/` is also evaluated.

Important conditions:

1. The process runs in the right working directory.
2. Subdirectories appear directly under `config/`.
3. Files have valid names, extensions, and formats supported by Config Data.
4. No higher-precedence source overrides the same property.

This example shows that wildcards fit best when configuration sets contain **distinct keys**; if multiple sets declare the same key, clear precedence rules are required.

### 8.2. Absolute paths for container environments

In containers or Kubernetes, ConfigMaps can be mounted into separate subdirectories:

~~~text
/etc/myapp/
├── db/
│   └── application.properties
└── cache/
    └── application.properties
~~~

You can declare:

~~~bash
java -jar /app/app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/"
~~~

Then the configuration location does not depend on the process's working directory. This explicit declaration fits environments with stable mount conventions.

If the application must ensure a critical directory always exists, do not use `optional:` for that directory; missing required configuration should be detected early instead of silently falling back to unintended defaults.

## 9. Distinguishing Wildcard File Locations from `configtree:` Wildcards

Spring Boot has the concept of a **configuration tree** for reading values from individual files where file names typically become configuration keys. It is commonly used with container volume mounts.

Suppose the layout is:

~~~text
/etc/secrets/
├── database/
│   ├── db.username
│   └── db.password
└── messagebroker/
    ├── mq.username
    └── mq.password
~~~

These are **not** `application.properties` files. If you use:

~~~properties
spring.config.import=optional:configtree:/etc/secrets/*/
~~~

Spring Boot can treat the direct subdirectories as configuration trees and create properties corresponding to the file names, such as `db.username` and `mq.password`.

Conversely:

~~~text
file:/etc/secrets/*/
~~~

is a **file location pattern** for finding configuration files named `application.*` (or the configured name). It does not turn arbitrary secret files into properties.

For `configtree:` wildcards, directories are sorted alphabetically when loaded. If you need another precedence order, list each import location explicitly. With real secrets, control file permissions and avoid exposing values in logs or diagnostic endpoints.

## 10. When Multiple Files Contain the Same Key: How to Determine the Winning Value

A practical four-step reasoning process:

### Step 1. Identify the exact location set in use

Is the application using defaults? Is `spring.config.location` declared to replace defaults? Is `spring.config.additional-location` added?

For example:

~~~text
--spring.config.additional-location=optional:file:/etc/myapp/*/
~~~

means the new location is added to the default search locations. Conversely:

~~~text
--spring.config.location=optional:file:/etc/myapp/*/
~~~

means the location list is replaced by that explicit configuration choice.

### Step 2. Expand wildcards and sort

List **direct subdirectories**, then sort by absolute path. Check which files exist in each expanded location.

For example:

~~~text
/etc/myapp/20-db/application.properties
/etc/myapp/40-mq/application.properties
/etc/myapp/90-overrides/application.properties
~~~

Files that do not exist or do not match the configuration name do not contribute properties.

### Step 3. Apply profiles and location groups

Determine `spring.profiles.active`, `application-{profile}.*` files, and the placement of `,` / `;`. A profile-specific file in an appropriate group can override a non-profile file; across profiles, check profile order and group rules.

### Step 4. Compare against sources higher than Config Data

Do not stop at files. The same property may be declared via:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/" \
  "--orders.inventory.timeout=8s"
~~~

In standard startup, `--orders.inventory.timeout=8s` can override `orders.inventory.timeout` from Config Data files. Wildcard directory discovery still ran, yet the final effective value does not necessarily come from any file.

## 11. Diagnosing When Spring Boot Does Not Find or Uses the Wrong File

### 11.1. Check file and directory names

Very common mistakes:

- Writing `config/**/` expecting multi-level recursive search.
- Placing a file under `config/zone/east/application.properties` and expecting `config/*/` to reach `east/`.
- Placing files in the JAR's directory while the process runs with a different working directory.
- Using `classpath:/config/*/` even though wildcards support external directories only.
- Writing `file:./config/*` without the trailing `/` for a wildcard directory location.
- Misspelling `application-prod.properties` or using the wrong active profile.
- Using `spring.config.location`, unintentionally replacing default locations.
- Assuming `optional:` also ignores errors inside a file's contents.

### 11.2. Enable Config Data logging when needed

To inspect configuration processing at startup, try enabling verbose logging for the relevant classes:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

The level of detail and message wording can vary across Spring Boot versions. Only enable verbose logging within an appropriate diagnostic scope; some systems need controls so internal paths or sensitive data are not exposed.

If Spring Boot Actuator is configured and secured, `/actuator/env` can help inspect which property sources contributed the effective value. Maintain authentication, authorization, and masking of sensitive values.

### 11.3. Inspect from the application using `Environment`

A simple check for a non-sensitive property:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationProbe {
    private final Environment environment;

    public ConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    public String inventoryTimeout() {
        return environment.getProperty(
            "orders.inventory.timeout", "not-configured");
    }
}
~~~

This API reveals the value resolved by Spring, though by itself it does not tell you which specific file won. When tracing the source, cross-reference property sources with locations, profiles, and each file's contents. Do not log passwords or tokens just to investigate overrides.

## 12. Common Misconceptions

| Claim | Correct Explanation |
| --- | --- |
| "Wildcards find all files at any depth." | `config/*/` expands direct subdirectories only, without recursive traversal |
| "Wildcards work in `classpath:`." | Config Data wildcard locations support external locations only |
| "The most recently mounted directory is evaluated later." | Wildcards are sorted alphabetically by absolute path, not by mount time |
| "`spring.config.location` just adds a new directory." | This property replaces the default location set; `additional-location` adds to it |
| "Separating two locations with `,` or `;` is the same." | `;` places locations in the same group; the difference can change profile-specific results |
| "Every file in a wildcard directory becomes a property." | File locations search for matching configuration file names/formats; `configtree:` is a separate mechanism |
| "`optional:` ignores syntax errors in files." | `optional:` primarily allows a missing location; malformed files can still fail |
| "The same key in the alphabetically last file always wins." | You must also consider location groups, profiles, imports, and higher-precedence sources |

## 13. Exercise: Deducing Effective Values

Suppose only the following sources exist, with no environment variables, overriding command-line properties, or imports:

~~~text
/workspace/
├── app.jar
└── config/
    ├── 10-core/
    │   └── application.properties
    ├── 20-service/
    │   └── application.properties
    └── 30-local/
        └── application.properties
~~~

~~~properties
# 10-core/application.properties
app.color=blue
app.timeout=2s
app.region=asia
~~~

~~~properties
# 20-service/application.properties
app.color=green
app.timeout=5s
~~~

~~~properties
# 30-local/application.properties
app.timeout=10s
~~~

Run the application from `/workspace` with the default location list and no active profile. Spring Boot finds all three files via `file:./config/*/` and sorts them by absolute path.

Expected output in this scenario:

~~~properties
app.color=green
app.timeout=10s
app.region=asia
~~~

Reason: `app.color` is last declared in `20-service`; `app.timeout` is overridden in `30-local`; and `app.region` exists only in `10-core`.

If you add:

~~~bash
java -jar app.jar --app.timeout=30s
~~~

then the effective value of `app.timeout` normally becomes `30s` because command-line arguments have higher precedence than file data. This does not stop wildcards from working; it just changes which source decides the final value.

## 14. Recommendations for Organizing Configuration

1. **Put default configuration in the JAR** so the build can start in a baseline environment when appropriate.
2. **Use a clear `config/` directory** for external configuration, consistent with the working directory or using absolute paths in containers.
3. **Use `config/*/` when configuration sets are independent** and come from separate mounts, such as database, cache, and messaging.
4. **Minimize duplicate keys across wildcard directories.** Having a property overridden due to directory naming easily creates subtle dependencies.
5. **List locations explicitly when order matters.** Consider `,` and `;` when multiple profiles are active at once.
6. **Use `spring.config.additional-location`** when you want to keep default files in the JAR and add external configuration.
7. **Mark only locations permitted to be absent with `optional:`.** Essential configuration should fail fast when missing.
8. **Distinguish `file:` from `configtree:`.** One loads matching named configuration files, while the other reads values from individual mounted files.
9. **Inspect effective values at runtime** when troubleshooting, and avoid exposing secrets.

## 15. Summary of Rules to Remember

- Spring Boot searches for configuration across default location groups, from the classpath to the working directory and external configuration directories.
- `file:./config/*/` is already part of the default search list: this pattern checks **one level of subdirectories** under `./config/`.
- Wildcard locations allow **only one** `*` in the appropriate `*/` or `*/<filename>` form, and **do not support `classpath:`**.
- Wildcard locations are expanded and **sorted alphabetically by absolute path**.
- Precedence is also affected by **location groups**, profiles, imports, and sources outside Config Data.
- `spring.config.location` **replaces** default locations, while `spring.config.additional-location` **adds** locations; `optional:` allows missing locations.
- With multiple active profiles, `,` and `;` can yield different override results.
- For critical configuration or many overlapping keys, specify location order explicitly and verify the winning property source.

### References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), sections **External Application Properties**, **Optional Locations**, **Wildcard Locations**, **Profile Specific Files**, and **Configuration Trees**.