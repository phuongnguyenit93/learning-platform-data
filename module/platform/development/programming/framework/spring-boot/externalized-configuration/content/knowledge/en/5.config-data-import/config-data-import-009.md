# Configtree Configuration Trees: From Directory and Filenames to Keys and Values

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Config Data Import

## 1. Objectives and context

In Spring Boot, not all configuration is stored as `key=value` lines in `application.properties` or as key–value pairs in YAML. When deploying on Kubernetes, Docker, or a centralized operations platform, configuration and secrets are often **mounted as individual files**. For instance, one file holds the username and another holds the password; the filename identifies the property, while the file content is the value.

Spring Boot supports this **configuration tree** source type using the `configtree:` prefix in `spring.config.import`. This mechanism turns a directory and file hierarchy into properties readable via Spring `Environment` or bindable into `@ConfigurationProperties`.

After this lesson, you will understand:

- Which **directory** serves as the root of a `configtree:`, and why choosing the root determines key names.
- How filenames and subdirectories map to property names, including filenames containing dots.
- Why **file contents** become values instead of being parsed as properties/YAML files.
- How to import a config tree, consume values in an application, handle missing directories, handle colliding keys, and deploy secrets via volumes.
- Common operational pitfalls when working with file-based configuration.

## 2. Basic model: one file, one property

Suppose the runtime environment has the layout:

~~~text
/run/secrets/
├── payment.username
├── payment.password
└── payment.endpoint
~~~

The contents of each file are:

~~~text
/run/secrets/payment.username  ->  service-user
/run/secrets/payment.password  ->  <secret value>
/run/secrets/payment.endpoint  ->  https://payment.internal
~~~

In the application's `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

When Spring Boot loads the config tree at startup, files in the tree supply the corresponding keys:

| File in tree | Property name | Property value |
| --- | --- | --- |
| `payment.username` | `payment.username` | File content, e.g., `service-user` |
| `payment.password` | `payment.password` | Secret content inside the file |
| `payment.endpoint` | `payment.endpoint` | `https://payment.internal` |

Application code can access:

~~~java
String username = environment.getProperty("payment.username");
String endpoint = environment.getProperty("payment.endpoint");
~~~

Points to distinguish:

1. Filenames (and subdirectories, if any) determine the **key**.
2. File contents determine the **value**.
3. `configtree:` specifies the **configuration loading mechanism** to Spring Boot.
4. The `application.yml` containing the import declaration remains a separate Config Data source; the tree's configuration enters `Environment` under Config Data precedence rules.

**There is no need** to create a `payment.username.properties` file or insert a `payment.username=service-user` line inside each file. With a config tree, the entire content of the file is the value.

## 3. From paths to property names

### 3.1. Choosing the right import root

Example filesystem layout:

~~~text
/etc/app-config/
└── inventory/
    ├── host
    ├── port
    └── credentials/
        ├── username
        └── password
~~~

Importing from the parent root:

~~~properties
spring.config.import=configtree:/etc/app-config/
~~~

Property names are generated from paths **relative to the root directory**:

| Relative path in tree | Resulting key |
| --- | --- |
| `inventory/host` | `inventory.host` |
| `inventory/port` | `inventory.port` |
| `inventory/credentials/username` | `inventory.credentials.username` |
| `inventory/credentials/password` | `inventory.credentials.password` |

If you change the import root to:

~~~properties
spring.config.import=configtree:/etc/app-config/inventory/
~~~

then the `inventory.` prefix no longer appears in the generated keys. The exact same files above yield `host`, `port`, `credentials.username`, and `credentials.password`. Hence, **choosing the root path is a property-naming design decision**, not merely picking a directory that exists.

In this example, to bind to configuration prefixed with `inventory`, import from `/etc/app-config/`; or reorganize filenames/directories appropriately if choosing a deeper root.

### 3.2. Filenames containing dots

Spring Boot can map dots in filenames to dots in property keys. Example tree:

~~~text
/etc/config/
├── spring.datasource.username
├── spring.datasource.password
└── service/
    └── timeout
~~~

With:

~~~properties
spring.config.import=configtree:/etc/config/
~~~

the properties are named:

~~~text
spring.datasource.username
spring.datasource.password
service.timeout
~~~

This is why Kubernetes Secrets are often mounted using files named directly after Spring properties, such as `spring.datasource.password`. The `spring.datasource.password` file **does not need** to contain `spring.datasource.password=...`; it only needs to hold the password value itself.

### 3.3. Different paths can produce the same key name

An example to avoid within the same configuration area:

~~~text
/etc/config/
├── service.timeout
└── service/
    └── timeout
~~~

Both representations target the name `service.timeout`. Do not rely on an uncontrolled file traversal order to resolve this conflict. Design the tree so **each property has one clear file path**, or clearly define which import location owns that key.

### 3.4. Files are values; directories are key-name structure

Do not confuse a directory name with an independently exported namespace or an automatically created Java object. The tree:

~~~text
/etc/config/
└── mail/
    ├── host
    └── port
~~~

creates `mail.host` and `mail.port`. It does not mean a file or scalar property named `mail` exists. Spring can use the `mail` prefix to bind child properties into an object, yet that is **key binding**, distinct from config tree creating a value for the directory itself.

## 4. Import syntax in Spring Boot

### 4.1. Importing a directory

In `src/main/resources/application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/etc/myapp/config/"
~~~

Or in `application.properties`:

~~~properties
spring.config.import=configtree:/etc/myapp/config/
~~~

Notes on syntax:

- The **`configtree:`** prefix tells Spring Boot to read using the file-tree style.
- The remainder is the directory location containing the configuration files.
- End directory paths with `/` to make clear this is a directory location.
- Paths like `/etc/myapp/config/` are examples for Linux/containers; on developer machines and Windows, substitute corresponding locations.
- Declarations in `application.yml` or `application.properties` must first **be discovered by Spring Boot** before the import can run.

### 4.2. Directory may not exist: `optional:`

If the application can run without a secret volume in development environments, use:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Meaning:

- Valid directory present: Spring Boot imports the config tree keys/values.
- Import location absent: this import can be skipped instead of failing startup for missing Config Data.
- `optional:` **does not make a mandatory secret safe when missing**. If code requires a password, validate required configuration and fail clearly when the value is absent.

If the production environment **must** have secrets mounted, omit `optional:` so a missing configuration location becomes an easily detected startup error:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

When the required item is a specific **key**, even if the directory exists, application validation is still needed to catch a missing key or empty value.

### 4.3. Absolute and relative paths

These two expressions depend on different contexts:

~~~properties
spring.config.import=configtree:/etc/myapp/config/
~~~

~~~properties
spring.config.import=optional:configtree:./config/secret-tree/
~~~

The second example uses a directory relative to the process's working directory. When launched from an IDE, via `java -jar` in another terminal, or from a container with a different `WORKDIR`, `./config/secret-tree/` can point to a different directory. Therefore, for secret volumes in deployment environments, absolute paths are usually easier to inspect and manage.

### 4.4. Importing multiple configuration trees

You can declare multiple config tree locations, for example:

~~~properties
spring.config.import=\
  optional:configtree:/etc/myapp/defaults/,\
  configtree:/run/secrets/
~~~

This uses the Java `.properties` line-continuation backslash `\` to write one property across multiple lines. When multiple import locations define the same key, **Config Data ordering rules decide the winning value**; among multiple imports listed in the same declaration, later imports generally take precedence over earlier imports.

For instance, `/etc/myapp/defaults/api.timeout` contains `10s`, while `/run/secrets/api.timeout` contains `20s`. When imported successfully in the order above and with no higher-precedence source, `api.timeout` receives `20s`. For secrets such as passwords, avoid placing unclear duplicate values across multiple locations so operators can easily verify which configuration the system uses.

## 5. How does config tree differ from importing YAML/properties files?

These two declarations are **not equivalent**:

~~~properties
# Read the file contents as a configuration document.
spring.config.import=file:/etc/myapp/extra.yml
~~~

~~~properties
# Read filenames and the contents of each file inside a directory.
spring.config.import=configtree:/etc/myapp/secrets/
~~~

With `file:/etc/myapp/extra.yml`, Spring Boot reads YAML and parses the key/value structure inside:

~~~yaml
payment:
  username: service-user
  endpoint: https://payment.internal
~~~

With `configtree:/etc/myapp/secrets/`, Spring Boot reads individual files:

~~~text
/etc/myapp/secrets/
├── payment.username   # file contains: service-user
└── payment.endpoint   # file contains: https://payment.internal
~~~

Both approaches can produce properties with **the same names** in `Environment`, yet how configuration is packaged, updated, and mounted is completely different.

If a config tree contains a file named `application.yml` whose content is:

~~~yaml
payment:
  username: service-user
~~~

that file is **not automatically parsed as a YAML document** just because its name ends in `.yml`. Under config tree rules, the file is mapped by its filename and its content becomes the value for the corresponding key. To have Spring load YAML properly, use an appropriate file/Config Data import.

Additionally, Java code calling `Files.readString(...)` to read a file in a directory does not register a property source with Spring. `spring.config.import` feeds the data into Boot's config-data loading pipeline.

## 6. Reading values from Environment

After importing:

~~~text
/run/secrets/
├── warehouse.api-key
├── warehouse.endpoint
└── warehouse.retry-count
~~~

a service can read:

~~~java
package com.example.warehouse;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class WarehouseSettings {

    private final Environment environment;

    public WarehouseSettings(Environment environment) {
        this.environment = environment;
    }

    public String endpoint() {
        return environment.getRequiredProperty("warehouse.endpoint");
    }

    public int retryCount() {
        return environment.getRequiredProperty(
                "warehouse.retry-count", Integer.class);
    }
}
~~~

`Environment` resolves lookups across sources by precedence, so returned values can come from the config tree or from a higher-precedence source. `getRequiredProperty(...)` fails if the property is missing; with `Integer`, Spring performs appropriate conversion and fails if the value cannot be converted.

Direct injection example using `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WarehouseClientSettings {

    private final String endpoint;

    public WarehouseClientSettings(
            @Value("${warehouse.endpoint}") String endpoint) {
        this.endpoint = endpoint;
    }

    public String getEndpoint() {
        return endpoint;
    }
}
~~~

This accesses the value for **a single key**. When configuration has multiple keys sharing a prefix, `@ConfigurationProperties` makes grouping, typing, and validating data easier.

## 7. Binding to objects with `@ConfigurationProperties`

Example tree:

~~~text
/etc/myapp/config/
└── warehouse/
    ├── endpoint
    ├── retry-count
    └── enabled
~~~

Spring Boot generates the properties `warehouse.endpoint`, `warehouse.retry-count`, and `warehouse.enabled`. In a Spring Boot 3 application with Java 17+:

~~~java
package com.example.warehouse;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "warehouse")
public record WarehouseProperties(
        String endpoint,
        int retryCount,
        boolean enabled
) {}
~~~

Enable scanning on the application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WarehouseApplication {
    public static void main(String[] args) {
        SpringApplication.run(WarehouseApplication.class, args);
    }
}
~~~

A service simply injects the bean:

~~~java
import org.springframework.stereotype.Service;

@Service
public class WarehouseService {
    private final WarehouseProperties properties;

    public WarehouseService(WarehouseProperties properties) {
        this.properties = properties;
    }

    public String endpoint() {
        return properties.endpoint();
    }
}
~~~

Spring Boot can convert text values from files into common configuration types such as integers or booleans through binding. For instance, the content of `retry-count` is `3` and `enabled` is `true`.

To enforce required configuration and format constraints, combine Bean Validation with `@Validated`, appropriate constraint annotations, and the corresponding validation dependency. Never rely solely on a volume existing to assume values are valid.

### 7.1. Property names in files vs. Java field names

For example, `warehouse.retry-count` can bind to `retryCount` via Spring Boot's relaxed binding. When designing filenames, use stable, readable conventions compatible with the volume mounting system. Do not rely on relaxed binding to mask inconsistent key naming across environments.

### 7.2. Byte content and value representation

Files in a config tree can contain text or bytes; Spring Boot supports retrieving data as `String` and, where appropriate, as `byte[]`. For example, certificates, keys, or passwords mounted from a Kubernetes Secret might contain newlines or bytes unsuitable for printing to logs.

For text configuration:

- Establish a consistent encoding, usually UTF-8 when creating files.
- Watch file-creation scripts: `echo` typically appends a newline, whereas `printf %s` can write without adding a newline.
- Do not assume Spring Boot will always trim trailing whitespace or newlines the way you expect. Control content at the source and test actual consumer behavior.

For binary data, bind to an appropriate type and handle via matching APIs; do not blindly force it into UTF-8 text without justification.

## 8. Application example using a Kubernetes Secret

A common way to supply credentials without placing values directly inside `application.yml` is mounting a Kubernetes Secret as a volume.

Suppose the Secret has two keys:

~~~text
spring.datasource.username
spring.datasource.password
~~~

Kubernetes can project these keys into two files in the mount:

~~~text
/etc/secrets/db/
├── spring.datasource.username
└── spring.datasource.password
~~~

The Spring Boot application uses:

~~~yaml
spring:
  config:
    import: "configtree:/etc/secrets/db/"
~~~

Once imported, the two filenames become:

~~~properties
spring.datasource.username=<content of username file>
spring.datasource.password=<content of password file>
~~~

The lines above only illustrate property names, **not** the content to write inside each file. Inside the volume, the username file holds only the username, and the password file holds only the password.

Condensed Kubernetes manifest example:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: warehouse-app
spec:
  containers:
    - name: app
      image: registry.example.com/warehouse:1.0
      volumeMounts:
        - name: db-secrets
          mountPath: /etc/secrets/db
          readOnly: true
  volumes:
    - name: db-secrets
      secret:
        secretName: warehouse-db
~~~

The manifest assumes the `warehouse-db` Secret **has already been created** with the required keys. The `image` example is an illustrative placeholder, not a prebuilt deployable image. Mounting this volume only ensures the files appear in place if Kubernetes and the Secret are configured successfully; the application still needs the corresponding `spring.config.import` declaration.

In real environments:

- If there are multiple Secrets or ConfigMaps, use distinct mount paths and import the necessary trees.
- Protect file read permissions inside the container; only components that need access should read secrets.
- Never store real secrets in Git or environment snapshots/logs.
- Do not treat Kubernetes updating a Secret inside a volume as proof that Spring Boot will automatically rebind running beans. Config Data is loaded during startup lifecycle; applying dynamic changes requires a designed and verified refresh/restart mechanism.

## 9. Precedence rules when keys collide

Example in `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"

payment:
  endpoint: "https://default.example"
~~~

And the file:

~~~text
/run/secrets/payment.endpoint
~~~

contains:

~~~text
https://live.payment.internal
~~~

In Boot's Config Data mechanism, imported data can override configuration in the importing document. Thus, without a higher-precedence source, `payment.endpoint` typically receives `https://live.payment.internal` from the config tree.

However, a config tree is only **one Config Data source** in the externalized configuration system. Sources such as environment variables, Java system properties, or command-line arguments can have higher precedence than Config Data. For example, running:

~~~bash
java -jar warehouse-app.jar \
  --payment.endpoint=https://override.example
~~~

means the command-line argument usually wins if the application retains default command-line property handling.

When seeing unexpected values, check:

1. Are the directory/filename and content right?
2. Was `spring.config.import` loaded by Boot?
3. Are additional profile-specific documents or other imports setting the same key?
4. Is an environment variable, system property, command-line argument, or custom `PropertySource` overriding it?
5. Which `Environment` is code reading from, and at what point?

Do not deduce behavior from filenames alone. Spring Boot resolves properties across **all configuration sources** according to precedence order.

## 10. Multiple trees, wildcards, and import ordering

Suppose configuration groups are mounted as:

~~~text
/etc/config/
├── database/
│   ├── spring.datasource.username
│   └── spring.datasource.password
└── messaging/
    ├── messaging.url
    └── messaging.timeout
~~~

You can import each directory individually:

~~~properties
spring.config.import=\
  configtree:/etc/config/database/,\
  configtree:/etc/config/messaging/
~~~

Files in each directory then generate properties **relative to their respective roots**. Because the filenames already carry full prefixes (`spring.datasource.*` and `messaging.*`), selecting child roots makes sense in this example.

When multiple subdirectories are created dynamically, you can use the wildcard pattern supported by Boot, for example:

~~~properties
spring.config.import=optional:configtree:/etc/config/*/
~~~

This pattern targets immediate subdirectories beneath `/etc/config/`. Wildcard imports are generally processed in sorted order of absolute path for deterministic results; if **you need an explicit precedence order among trees that share keys**, list each import explicitly.

Do not use wildcards as a substitute for understanding each directory's namespace: importing `/etc/config/*/` sets each subdirectory as a root, whereas importing `/etc/config/` uses one shared root and can add subdirectory segments to property names. Base your choice on **the desired keys**.

## 11. End-to-end local practice

### 11.1. Create a simulated config tree

On Linux/macOS, run in the project directory:

~~~bash
mkdir -p ./local-secrets/catalog

printf '%s' 'https://catalog.internal' \
  > ./local-secrets/catalog/catalog.endpoint

printf '%s' '5' \
  > ./local-secrets/catalog/catalog.retry-count
~~~

Resulting tree:

~~~text
local-secrets/
└── catalog/
    ├── catalog.endpoint
    └── catalog.retry-count
~~~

The `catalog.endpoint` file holds the URL; `catalog.retry-count` holds the number `5` as text.

### 11.2. Import into Spring Boot

In `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configtree:./local-secrets/catalog/"

catalog:
  endpoint: "https://fallback.invalid"
  retry-count: 1
~~~

With the project root as working directory, when both files exist, the imported properties are used per Config Data precedence. Without the import directory, `optional:` lets Boot continue and use the default values in `application.yml`.

Example component reading configuration:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogSettings(String endpoint, int retryCount) {}
~~~

With `@ConfigurationPropertiesScan` enabled, inject `CatalogSettings` and call `endpoint()` and `retryCount()`. The expected values when the tree above is present are the file's URL and `5`.

### 11.3. Test individual variations

1. Delete or rename `catalog.retry-count` and restart: only this key falls back to `1` from YAML, assuming no other source overrides it.
2. Change the file content to another valid number and restart: the new value binds.
3. Rename `catalog.endpoint` to `endpoint`: with root `./local-secrets/catalog/`, the property name becomes `endpoint` instead of `catalog.endpoint`; the bean with prefix `catalog` will not receive it from this file.
4. Change the import location to `configtree:./local-secrets/`: the directory name `catalog` becomes a key segment; `catalog/catalog.endpoint` then produces `catalog.catalog.endpoint`, no longer `catalog.endpoint`.
5. Try adding `--catalog.retry-count=8` when running the app: verify that CLI has higher precedence than Config Data.

To avoid confusing values supplied by tree files with fallback values, make one change at a time and restart the application between runs.

### 11.4. Test mandatory vs. optional failures

If using `optional:configtree:./local-secrets/catalog/`, rename the directory so the import can no longer be found. The application can still start using fallbacks if every property has a substitute value.

Then remove `optional:` and try starting without the directory. Spring Boot will fail due to a missing mandatory Config Data location. For production secrets, this fail-fast behavior is usually better than silently running with empty credentials.

## 12. Troubleshooting when properties are missing from a config tree

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `Environment.getProperty("catalog.endpoint")` returns `null` | Wrong import root, wrong filename, or missing import location | Compare property name with path relative to root |
| Value remains the default from YAML | Tree was not imported or higher-precedence source overrides it | Check `spring.config.import` declaration and property sources |
| Startup fails due to missing location | Mandatory import yet directory missing or inaccessible | Check mount path, read permissions, consider `optional:` if appropriate |
| Value contains unexpected characters | File content has newline/space or mismatched encoding | Safely inspect actual bytes of the file |
| File contains `foo=bar` yet property `foo` does not appear | Config tree treats entire file content as the value; it does not parse properties | Name the file `foo`, with content `bar` only |
| Key exists yet value differs | Colliding key across multiple imports or CLI/env source | Check import order and higher-precedence sources |
| Secret updated at runtime yet bean keeps old value | No reload/rebind mechanism present | Design controlled restart or refresh |
| Binding `int`/`boolean` fails | File content cannot convert to target type | Check value format and validation |

For **non-sensitive** keys, a simple diagnostic snippet:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigTreeProbe implements ApplicationRunner {

    private final Environment environment;

    public ConfigTreeProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("catalog.retry-count = "
                + environment.getProperty("catalog.retry-count"));
    }
}
~~~

Use only demo keys for observation. Never print `*.password`, tokens, private keys, or the entire contents of `Environment` to logs. If using Actuator `env`/`configprops` for diagnosis, secure the endpoints and configure sensitive-value masking.

On the OS/container side, verify actual mount directories and read permissions with appropriate inspection commands. For example, on Linux, `ls -la /run/secrets` shows filenames and permissions without needing to print secret values into terminals or CI logs. With Kubernetes, cross-check Secret keys against mounted filenames, mount paths, and the exact container where the application runs.

## 13. Operational and security principles

**Separate deployment configuration from build artifacts.** Data such as endpoints, credentials, or key material have a different lifecycle from code. Mounting files or pulling from a secret management system avoids rebuilding the JAR whenever operational info changes.

**Restrict access.** A config tree holding secrets can be read by any process with file read permissions. Configure filesystem permissions, container identities, and access policies properly. Never commit real secret values to Git or output them in build artifacts.

**Do not overuse `optional:`.** Use it for genuinely optional configuration, and validate mandatory properties separately. For production environments requiring secrets to operate, fail clearly when they are absent.

**Control how file content is generated.** Scripts, ConfigMaps, or Secret generators can insert trailing newlines or unsuitable encodings. For strictly formatted values, validate at the source and enforce constraints during binding.

**Define how runtime updates happen.** Importing a config tree via Config Data does not imply automatic detection of all changes or automatic updating of already initialized bean state. Establish clear restart, rollout, or supported reload/refresh procedures in your system.

**Keep naming structures consistent.** When multiple teams share a volume folder, prefix and naming conventions reduce the risk of colliding keys. Name files after the properties they supply and verify the import root in every environment.

## 14. Self-check questions

**Question 1.** Given `/etc/settings/order/timeout` containing `25s`, the application imports `configtree:/etc/settings/`. Which property is created?  
**Answer:** `order.timeout`, with value equal to file content `25s`.

**Question 2.** Same file, yet the application imports `configtree:/etc/settings/order/`. Which property is created?  
**Answer:** `timeout`. The `order.` prefix disappears because `order/` became the root directory.

**Question 3.** File `/run/secrets/db.password` contains the string `db.password=hunter2`. What is the value of property `db.password`?  
**Answer:** The entire string `db.password=hunter2` (potentially with a trailing newline depending on file content), **not** just `hunter2`. Because config tree does not parse properties syntax.

**Question 4.** `application.yml` declares `app.mode=local` and imports `configtree:/run/config/`, where file `app.mode` contains `cluster`. Without a higher-precedence source, which value usually wins?  
**Answer:** `cluster` from the import.

**Question 5.** A Secret file is updated in a Kubernetes volume. Is a service that injected `@ConfigurationProperties` at startup guaranteed to pick up the new value automatically?  
**Answer:** No, it cannot be assumed. You need a properly designed and verified restart/refresh or update mechanism.

## 15. Takeaways

- `configtree:` is a form of **Config Data Import**: each file in the tree is a property, the filename and relative path from the root form the key, and the file content forms the value.
- Choosing the right **root directory** determines whether directory prefixes appear in keys. Filenames containing dots can also express keys like `a.b.c`.
- Use `spring.config.import=configtree:/path/` to load a mandatory tree; add `optional:` when missing the import location is allowed.
- Config tree **differs** from loading a YAML/properties file and differs from reading files directly in code. It participates in Spring Boot precedence and can bind via `Environment`, `@Value`, and `@ConfigurationProperties`.
- Mounted Kubernetes Secrets/ConfigMaps are common use cases. Manage read permissions, bytes/newline formatting, key names, import order, and runtime update policies carefully.

## References

- [Spring Boot Reference — Externalized Configuration, Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree): importing configuration trees, property names, and file contents.
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): `spring.config.import` syntax, `optional:`, and precedence.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): structured configuration binding.
- [Kubernetes Documentation — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret keys exposed via volumes in containers.
