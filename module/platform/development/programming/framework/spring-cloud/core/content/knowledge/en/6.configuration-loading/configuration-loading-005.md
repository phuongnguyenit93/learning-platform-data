# `spring.config.name`, `location`, and `additional-location`

This lesson belongs to the **Configuration Loading** chapter of the **SPRING_CLOUD_CORE** module. The three properties `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` determine which configuration files Spring Boot looks for, where it looks for them, and how those locations interact with default configuration.

These properties are essential when deploying the same application to a personal machine, server, container, or multiple environments. They are typically passed via command line, system properties, or environment variables right at startup. Misunderstanding the difference between **replacing** and **adding** search locations can cause the application to skip configuration packaged inside the JAR or load the wrong file due to the working directory.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain how Spring Boot Config Data discovers and loads configuration during startup.
2. Use `spring.config.name` to change the base name of the configuration files searched.
3. Use `spring.config.location` to specify configuration locations and understand that this property replaces the default locations.
4. Use `spring.config.additional-location` to add external locations while keeping the default locations.
5. Distinguish directory paths from file paths, and understand trailing `/`, the `optional:` prefix, and precedence order.
6. Combine filename, location, profile, and environment variable settings when running an application from Maven, Gradle, or an executable JAR.
7. Distinguish file-locating properties from `spring.config.import`, especially when integrating Spring Cloud Config Server.
8. Design a test to prove the application loaded the intended configuration source.

## 2. When Does Spring Boot Load Configuration?

During startup, Spring Boot needs to know configuration sources before creating and configuring many beans in the `ApplicationContext`. The Config Data mechanism reads configuration locations, profiles, and imported resources to build property sources for the application environment.

~~~mermaid
flowchart TD
    START["Launch JVM / SpringApplication"] --> EARLY["Read early config discovery properties"]
    EARLY --> NAME["Determine spring.config.name"]
    EARLY --> LOC["Determine location / additional-location"]
    NAME --> SEARCH["Search configuration resources"]
    LOC --> SEARCH
    SEARCH --> PROFILE["Evaluate active profiles"]
    PROFILE --> LOAD["Load config documents and imports"]
    LOAD --> ENV["Environment contains property sources"]
    ENV --> CTX["Create / configure ApplicationContext and beans"]
    CTX --> RUN["Application ready to run"]
~~~

The three properties in this lesson govern **finding configuration resources**. They must be known early enough for Spring Boot to determine where to read from. Therefore, you cannot put `spring.config.location` inside `application.yml` itself and expect Spring Boot to use the value it just read to locate that file: the file must be found first before its contents can be read.

Appropriate sources for passing these properties include:

- Application command-line arguments, placed after the JAR name.
- JVM system properties, placed before `-jar`.
- Process environment variables.
- A launcher or deployment platform capable of supplying the sources above.

Example:

~~~bash
java -jar app.jar --spring.config.name=orders
~~~

Or:

~~~bash
java -Dspring.config.name=orders -jar app.jar
~~~

Both approaches supply the property before Spring Boot loads configuration files. When determining which value wins if multiple sources declare it, evaluate Spring Boot's precedence rules and actual configuration sources.

## 3. Distinguishing the Three Properties

| Property | Question it answers | Primary behavior |
| --- | --- | --- |
| `spring.config.name` | Which base filename should be searched? | Changes the default `application` name to another name, e.g., `orders`. |
| `spring.config.location` | Where should configuration be searched? | Specifies configuration locations, replacing the default location set. |
| `spring.config.additional-location` | Where else should be searched? | Adds locations while preserving the default location set. |

Remember the crucial difference:

- `location` = **replaces** the default locations.
- `additional-location` = **adds** locations to the default locations.

Both location properties can accept multiple locations. Locations are processed in declaration order; configuration in a later location can override matching keys from an earlier location. Exact rules are also influenced by profiles and the type of resource loaded.

## 4. `spring.config.name`: Renaming Configuration Files

### 4.1. Default name and custom name

By default, Spring Boot looks for configuration with the base name `application`, for example:

~~~text
application.properties
application.yml
application.yaml
application-local.properties
application-local.yml
application-prod.yml
~~~

When set:

~~~bash
java -jar app.jar --spring.config.name=orders
~~~

Spring Boot uses the base name `orders` when searching for configuration in directory locations:

~~~text
orders.properties
orders.yml
orders.yaml
orders-local.properties
orders-local.yml
orders-prod.yml
~~~

The base name is the part before the file extension. This property does not rename the JAR, Java package, `spring.application.name`, or service ID in a registry.

**Do not confuse these two properties:**

| Property | Purpose |
| --- | --- |
| `spring.config.name` | Base filename of configuration files, e.g., `orders.yml`. |
| `spring.application.name` | Logical application name, typically used in logs, metrics, discovery, or integration configs. |

An application can have `spring.application.name=order-service` while still using `spring.config.name=orders`. The two values serve two different purposes.

### 4.2. When should you change the name?

Changing the name is useful when:

- A process needs a dedicated named configuration set.
- Multiple applications share the same configuration directory but require separate files.
- You want role-descriptive names such as `gateway.yml`, `worker.yml`, or `scheduler.yml`.
- Deployment conventions distinguish between artifact name and configuration name.

Example directory:

~~~text
deployment/
└── config/
    ├── orders.yml
    ├── orders-prod.yml
    ├── billing.yml
    └── billing-prod.yml
~~~

Launching the orders application:

~~~bash
java -jar orders.jar --spring.config.name=orders --spring.config.additional-location=optional:file:./config/
~~~

The billing application can use the same directory while choosing a different name:

~~~bash
java -jar billing.jar --spring.config.name=billing --spring.config.additional-location=optional:file:./config/
~~~

Neither process needs its artifact renamed to select its matching configuration set.

### 4.3. Config name is not an arbitrary filename at every location

When specifying a **directory**, Spring Boot combines that directory with the base name and active profiles to locate matching configuration documents.

When specifying a **specific file**, that file is loaded directly at the specified path. If you want to cleanly manage a base file plus profile files under the same name, prefer specifying a directory and combining `spring.config.name` with active profiles.

## 5. `spring.config.location`: Specifying Replacement Locations

### 5.1. What does this property do?

`spring.config.location` specifies the configuration locations to use and **replaces the default search location set**. This means default configuration on the classpath or other default locations may no longer be searched as before.

Example:

~~~bash
java -jar app.jar --spring.config.location=file:./runtime-config/
~~~

Because the value ends with `/`, it is a directory location. Spring Boot searches for files with the corresponding base name—for instance `application.yml` if `spring.config.name` is unchanged.

To use the name `orders`:

~~~bash
java -jar app.jar --spring.config.name=orders --spring.config.location=file:./runtime-config/
~~~

Inside `runtime-config`, the matching file is `orders.yml`, along with matching profile variants if profiles are activated.

### 5.2. Example of completely replacing default locations

Suppose the JAR contains:

~~~text
app.jar
  └── BOOT-INF/classes/
      └── application.yml
~~~

And deployment configuration provides:

~~~text
runtime-config/
└── application.yml
~~~

When running:

~~~bash
java -jar app.jar --spring.config.location=file:./runtime-config/
~~~

Spring Boot searches the specified location instead of the default location set. Do not expect `application.yml` packaged inside the JAR to be merged automatically as before. If you want to keep the default file in the JAR and override certain values with external files, consider `spring.config.additional-location`.

### 5.3. Multiple locations

Multiple locations can be specified, separated by commas:

~~~bash
java -jar app.jar --spring.config.location=file:./base-config/,file:./environment-config/
~~~

Locations are processed in declaration order. If the same key appears in both places, the value from the later location can override the value from the earlier location.

Example:

`base-config/application.yml`:

~~~yaml
app:
  region: ap-southeast
  feature-mode: standard
~~~

`environment-config/application.yml`:

~~~yaml
app:
  feature-mode: restricted
~~~

Merged result by property source rules: `app.region` keeps `ap-southeast`, while `app.feature-mode` receives `restricted` from the later location. This is the mental model for overrides; when profiles, imports, or other configuration sources are also present, check the corresponding precedence order as well.

### 5.4. Directory paths vs. file paths

The two location forms behave differently:

| Form | Example | Meaning |
| --- | --- | --- |
| Directory | `file:./config/` | Spring Boot searches for configuration filenames in the directory based on `spring.config.name` and profiles. |
| Specific file | `file:./config/orders-prod.yml` | Loads the specified file resource directly. |
| Classpath directory | `classpath:/config/` | Searches for resources inside the classpath directory. |
| Classpath file | `classpath:/tenant/orders.yml` | Loads a specific resource on the classpath. |
| Absolute directory | `file:/etc/orders/config/` | Searches for configuration in an external directory via an absolute path. |

When specifying a **directory**, end the path with `/`. That tells Config Data to treat the location as a directory and combine it with the config name. Relative paths like `file:./config/` are resolved against the **process working directory**, not automatically against the directory holding the JAR file.

## 6. `spring.config.additional-location`: Adding External Configuration

### 6.1. When to use it?

This is usually the right choice when you want to:

- Keep default configuration packaged inside the application.
- Add server- or environment-specific configuration.
- Allow external configuration to override part of the default values.
- Use the same artifact across multiple environments without rebuilding.

Example:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Spring Boot continues searching default locations while also searching `./config/`. Additional locations are processed with higher precedence than corresponding default locations, so they can override packaged values.

### 6.2. Illustrating configuration merging

Inside the JAR, `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  region: ap-southeast
  feature-mode: standard
~~~

Outside the JAR, `./config/application.yml`:

~~~yaml
server:
  port: 8081

app:
  feature-mode: restricted
~~~

When launched with:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Expected result across property sources:

| Property | Effective Value | Source |
| --- | --- | --- |
| `spring.application.name` | `order-service` | Default file in JAR |
| `server.port` | `8081` | External file |
| `app.region` | `ap-southeast` | Default file in JAR |
| `app.feature-mode` | `restricted` | External file |

External configuration does not need to repeat every key. It only needs to declare values that must change. That is a major benefit of externalized configuration.

### 6.3. Multiple additional locations

Example:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./site-config/,optional:file:/etc/orders/
~~~

Locations are processed in order. If the same key appears in multiple locations, a location processed later can override an earlier one. Standardize ordering across configuration groups so one host does not produce different results simply due to a different location list.

## 7. The `optional:` Prefix and Handling Missing Locations

### 7.1. Mandatory locations

If a location lacks the `optional:` prefix, Spring Boot can halt startup when a required resource is missing.

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/orders/
~~~

This approach fits when an external file is mandatory for safe operation, such as endpoint or environment settings whose absence should fail fast.

### 7.2. Optional locations

Add `optional:` before the location:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

If the directory does not exist, the application can proceed without loading resources from that location. This suits override directories that exist only in certain environments.

Use `optional:` responsibly. If a file contains essential settings, marking it optional can let the application boot with unexpected defaults. For critical configuration, let missing files fail clearly or add validation to stop startup when required values are invalid.

### 7.3. Optional does not mean every error is ignored

`optional:` handles missing locations or resources under Config Data mechanics. It does not suppress YAML syntax errors, wrong data types, content parsing errors, or bean initialization failures caused by bad configuration values. If the application still stops, read the root exception and determine whether it is a missing-resource error or a content-processing error.

## 8. Combining with Profiles

Profiles allow separate configurations per environment or runtime role. Example:

~~~text
config/
├── orders.yml
├── orders-local.yml
├── orders-staging.yml
└── orders-prod.yml
~~~

Activating a profile:

~~~bash
java -jar app.jar --spring.config.name=orders --spring.config.additional-location=optional:file:./config/ --spring.profiles.active=prod
~~~

Spring Boot searches for base configuration `orders` and matching profile configuration `orders-prod` in the location directories. Profile-specific documents are loaded to override base values under Config Data rules.

### 8.1. Example

`orders.yml`:

~~~yaml
server:
  port: 8080

app:
  retry-limit: 2
  payment-mode: sandbox
~~~

`orders-prod.yml`:

~~~yaml
server:
  port: 8080

app:
  retry-limit: 4
  payment-mode: live
~~~

When the `prod` profile is active, keys present in `orders-prod.yml` override corresponding values in `orders.yml`. Keys absent from the profile file inherit base values or other configuration sources according to precedence.

Do not use profiles as the sole place to store secrets. Sensitive information should be supplied via proper secret management with restricted read permissions.

### 8.2. Renaming the file but forgetting the profile filename

A common error is changing `spring.config.name=orders` while leaving `application-prod.yml` in place. When that happens, the expected profile file will not be discovered under the new base name.

Check these in sync:

- Base name: `spring.config.name`.
- Filenames: `orders.yml`, `orders-prod.yml`.
- Active profile: `spring.profiles.active=prod`.
- Containing location: `spring.config.location` or `spring.config.additional-location`.

## 9. Passing Properties from the Launch Environment

### 9.1. Command-line arguments

Arguments after the JAR name are application arguments:

~~~bash
java -jar app.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=optional:file:./config/ \
  --spring.profiles.active=prod
~~~

This style is visible in launch commands and convenient for one-off runs. On Windows shells, line continuation and escaping differ from Bash; you can write the full command on a single line.

### 9.2. JVM system properties

`-D...` options go before `-jar`:

~~~bash
java \
  -Dspring.config.name=orders \
  -Dspring.config.additional-location=optional:file:./config/ \
  -jar app.jar \
  --spring.profiles.active=prod
~~~

Do not place `-Dspring.config.name=orders` after the JAR name and expect the JVM to treat it as a system property; after `-jar app.jar`, arguments are forwarded to the application.

### 9.3. Environment variables

Spring Boot supports relaxed binding from environment variables. Matching names:

| Property | Environment variable |
| --- | --- |
| `spring.config.name` | `SPRING_CONFIG_NAME` |
| `spring.config.location` | `SPRING_CONFIG_LOCATION` |
| `spring.config.additional-location` | `SPRING_CONFIG_ADDITIONALLOCATION` |

Bash:

~~~bash
export SPRING_CONFIG_NAME=orders
export SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./config/
export SPRING_PROFILES_ACTIVE=prod
java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_CONFIG_NAME = "orders"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "optional:file:./config/"
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
~~~

Environment variables belong to the launched process. Changing a variable in a terminal after the application is already running does not update that running process's environment. To change configuration discovery properties, restart the application with the new environment.

### 9.4. Maven and Gradle

With Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.config.name=orders --spring.config.additional-location=optional:file:./config/ --spring.profiles.active=prod"
~~~

With Gradle:

~~~bash
./gradlew bootRun --args='--spring.config.name=orders --spring.config.additional-location=optional:file:./config/ --spring.profiles.active=prod'
~~~

Adjust quoting syntax to match your shell. When running an executable JAR, pass the same arguments after the JAR name to verify configuration in the actual artifact.

## 10. Working Directory and Relative Paths

Locations such as `file:./config/` depend on the process **working directory**. They do not automatically point to where the JAR lives.

Example:

~~~text
/opt/orders/
├── app.jar
└── config/
    └── orders-prod.yml
~~~

If the process starts with `/opt/orders` as its working directory, `file:./config/` resolves to `/opt/orders/config/`. If a service manager sets the working directory to `/`, the exact same location string resolves to `/config/` and fails to find the expected file.

To reduce surprises:

- Set an explicit working directory in systemd, containers, or service managers.
- Use absolute paths when deployment environments require high determinism.
- Document container mount paths clearly and point locations to paths **inside the container**.
- Never depend on the interactive current directory of whichever user happens to be logged in.

Example absolute location:

~~~bash
java -jar /opt/orders/app.jar \
  --spring.config.additional-location=file:/etc/orders/
~~~

On Windows, you can use an absolute file URI with forward slashes, such as `file:///C:/apps/orders/config/`. Verify access permissions for the process running the application.

## 11. Distinguishing Locations from `spring.config.import`

The three properties in this lesson determine **configuration search names and locations**. `spring.config.import` is a mechanism for declaring another configuration resource to import during Config Data loading.

Example with Spring Cloud Config Client in versions supporting Config Data import:

~~~yaml
spring:
  application:
    name: orders
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

The application requires a compatible Config Client dependency and a reachable Config Server. This import configuration is the Config Server integration mechanism; it does not replace `spring.config.additional-location` when you need to add an external file directory.

Comparison:

| Mechanism | Used for | Example |
| --- | --- | --- |
| `spring.config.name` | Changing the base filename searched. | `orders` |
| `spring.config.location` | Replacing the default location set with specified locations. | `file:/etc/orders/` |
| `spring.config.additional-location` | Adding external file locations alongside default locations. | `optional:file:./config/` |
| `spring.config.import` | Importing other Config Data resources, including Config Server integration when a matching resolver/dependency is present. | `optional:configserver:http://config-server:8888` |

Do not lump `spring.config.import` together with renaming files or changing search directories. When integrating Spring Cloud Config, follow the guide for your Spring Cloud release train; legacy setups using the bootstrap context can differ from modern Config Data mechanics.

## 12. Common Deployment Patterns

### 12.1. Keep defaults and add external overrides

Use when the JAR has safe default settings and each environment overrides only a few keys:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/orders/
~~~

This is usually the clearest option for per-host configuration because the file inside the JAR still loads.

### 12.2. Use only the configuration set provided by the environment

Use when you want the specified location to be the primary configuration file source:

~~~bash
java -jar app.jar --spring.config.name=orders --spring.config.location=file:/etc/orders/
~~~

Ensure the directory exists, contains all needed files, and that you understand the default location set is replaced. If you still want to keep some default locations, consider additional configuration or declare each source explicitly.

### 12.3. Sharing a base directory across multiple applications

~~~text
/etc/platform/
├── orders/
│   ├── orders.yml
│   └── orders-prod.yml
├── inventory/
│   ├── inventory.yml
│   └── inventory-prod.yml
└── gateway/
    ├── gateway.yml
    └── gateway-prod.yml
~~~

Each process selects its matching name and directory:

~~~bash
java -jar orders.jar --spring.config.name=orders --spring.config.location=file:/etc/platform/orders/ --spring.profiles.active=prod
java -jar inventory.jar --spring.config.name=inventory --spring.config.location=file:/etc/platform/inventory/ --spring.profiles.active=prod
~~~

This pattern separates permissions and configuration lifecycles per service. Ensure each process has read permission only on its own directory and cannot read another service's config unnecessarily.

### 12.4. Containers and configuration volumes

Illustrative example:

~~~bash
docker run --rm \
  -p 8080:8080 \
  -v "$PWD/config:/run/config:ro" \
  -e SPRING_CONFIG_ADDITIONALLOCATION=optional:file:/run/config/ \
  orders-image:latest
~~~

The application sees the volume at `/run/config/` inside the container. The location must use the path inside the container, not the host path. Read-only mounts allow the application process to read configuration without modifying host files.

Never pass secrets directly on the command line if they risk exposure in process lists or deployment logs. Use platform-supported secret mounts or environment mechanisms with appropriate access control.

## 13. Configuration Verification Matrix

Do not judge solely from startup logs that the right file was loaded. Design a small test with marker keys having distinct values to verify the winning source.

| Test Case | Setup | What to Verify |
| --- | --- | --- |
| L1 | Pass no discovery properties. | Application uses default name and locations for its version. |
| L2 | Set only `spring.config.name=orders`. | `orders.yml` is searched instead of the default name. |
| L3 | Set `spring.config.location=file:./custom/`. | Default locations are replaced; files in `custom` are loaded. |
| L4 | Set `spring.config.additional-location=optional:file:./custom/`. | Default files still load and external values can override them. |
| L5 | Set two additional locations with the same key. | Verify the later location wins in order. |
| L6 | Activate profile `prod`. | `<name>-prod.yml` is applied. |
| L7 | Mandatory location does not exist. | Application stops with a location-not-found error. |
| L8 | Location with `optional:` prefix does not exist. | Application continues if there are no other config errors. |
| L9 | Run from a different working directory. | Verify where relative paths are being resolved. |
| L10 | Set the same key in file and command line. | Verify higher-precedence source wins according to Boot rules. |

### 13.1. Marker-key verification example

Create base configuration:

`application.yml`:

~~~yaml
app:
  config-source: packaged
  retry-limit: 2
~~~

Create external configuration:

`./config/application.yml`:

~~~yaml
app:
  config-source: external
~~~

Create a lab endpoint returning only these two properties, or verify with a Spring Boot test:

- If using `additional-location`, expect `config-source=external`.
- `retry-limit` remains `2` because the external file does not declare this key.
- If using replacement `location` and the external file lacks `retry-limit`, do not assume the value `2` from the packaged file still exists.

Never expose an endpoint echoing the entire `Environment` in production. Only return non-sensitive test values or verify inside test/integration environments.

### 13.2. PASS criteria

A verification run only PASSES when:

1. The exact command and working directory used are known.
2. You confirm the process received the intended configuration discovery properties.
3. Observable values are obtained for marker keys.
4. Values match the winning source predicted by precedence order.
5. Results are reproducible using the same artifact and conditions.

If the outcome differs from expectations, capture full startup logs and exceptions; inspect profiles, file locations, extensions, read permissions, and precedence before drawing conclusions.

## 14. Common Errors and Fixes

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Changed `spring.config.name` but file does not load. | File is still named `application.yml`, or location is not a directory search path as expected. | Rename the file appropriately; check `spring.config.name` and location type. |
| External file exists yet app still uses values from the JAR. | Wrong path, different working directory, or wrong location setting. | Check absolute paths and test with a marker key. |
| After setting `spring.config.location`, default config disappears. | This is the default-location replacement behavior of `location`. | Use `spring.config.additional-location` if defaults must remain. |
| External file fails to override values. | Location was not loaded, declaration order differs from expectation, or keys do not match. | Check path, order, active profiles, and property spelling. |
| Missing file prevents application startup. | Location is mandatory and does not exist. | Create the file at the right path or add `optional:` if genuinely optional. |
| Added `optional:` yet application still fails. | Error may lie in file contents, binding, or bean initialization. | Read the root cause; `optional:` does not ignore all errors. |
| Profile fails to load the expected file. | Wrong profile, wrong base name, or mismatched profile filename. | Check `spring.profiles.active`, `spring.config.name`, and `<name>-<profile>.yml`. |
| Works in IDE but fails under service manager. | Different working directory, environment, or file read permissions. | Set working directory and environment explicitly; verify from the actual deployed process. |
| Put location inside `application.yml` with no effect. | Property must be known before the file is discovered and loaded. | Pass via command line, system property, or environment variable. |
| Expected `additional-location` to contact Config Server. | Confused file locations with Spring Cloud Config's import mechanism. | Use `spring.config.import` and a compatible Config Client. |

## 15. Completion Checklist

- [ ] Can explain the role of Spring Boot Config Data during startup.
- [ ] Can state why `spring.config.name` must be provided before configuration files are searched.
- [ ] Can rename the base config name from `application` to `orders` and create matching files.
- [ ] Can distinguish replacing `spring.config.location` from additive `spring.config.additional-location`.
- [ ] Can use directory and file location syntax properly.
- [ ] Can explain the meaning of a trailing `/` on directory paths.
- [ ] Knows that relative locations depend on the process working directory.
- [ ] Can distinguish mandatory locations from locations with the `optional:` prefix.
- [ ] Can combine config filenames, profiles, and configuration locations.
- [ ] Can pass properties via command line, JVM system properties, and environment variables.
- [ ] Can distinguish location properties from `spring.config.import` for Config Data and Spring Cloud Config.
- [ ] Can run a marker-key test proving which file supplied the final value.
- [ ] Does not place secrets into committed configuration files or logs.

**References to consult during practice:** Spring Boot Reference on Externalized Configuration and Config Data; Spring Cloud Config Client documentation on Config Data imports for your active release train. Verify exact Boot/Cloud versions before applying syntax to deployment environments.
