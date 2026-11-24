# Config Data: Packaged and External Application Configuration

## 1. The Problem to Solve

A Spring Boot application is typically packaged into a single JAR file yet must run across multiple environments: a developer's machine, testing, staging, and production. The source code can stay the same, while the HTTP port, database URL, timeouts, or feature toggles may differ.

Putting every environment's values into Java code or building a separate JAR per environment makes deployment hard to manage. The proper approach is to **package sensible default values inside the application** and **supply environment-specific values externally** at runtime.

Spring Boot calls the mechanism for loading application configuration files such as `application.properties` and `application.yml` **Config Data**. These files are loaded into `Environment`, where Spring looks up properties by key names such as `server.port` or `app.notification.enabled`.

After this lesson, you should be able to:

- Distinguish between configuration **packaged inside the JAR** and **located outside the JAR**.
- Identify the locations where Spring Boot automatically searches for `application.*` files.
- Explain the override order when the same key appears in multiple files, including profile-specific files.
- Use `spring.config.location`, `spring.config.additional-location`, `spring.config.import`, and `optional:` for their intended purposes.
- Analyze on your own the final value an application receives at startup.

## 2. What Is Config Data?

Within the scope of Spring Boot 3.3, **Config Data** mainly refers to data read from `application.properties`, `application.yaml`, or `application.yml` configuration files, along with additional sources imported via `spring.config.import`. Configuration is processed right from startup so components such as the web server, datasource, and beans can use it.

There are two important location groups:

| Group | Example | Characteristics |
| --- | --- | --- |
| **Packaged / classpath** | `src/main/resources/application.yml` bundled into the JAR | Travels with the artifact during build and deployment; suited for shared default values |
| **External / filesystem** | `./config/application.yml` or `/etc/my-service/application.yml` | Supplied outside the JAR; can change per environment without rebuilding |

Example structure during development and after deployment:

~~~text
my-service/
├── src/main/resources/
│   └── application.yml        # Packaged at build time
└── build/libs/my-service.jar

/deploy/my-service/
├── my-service.jar
└── config/
    ├── application.yml        # External configuration outside JAR
    └── application-prod.yml   # Overrides when the prod profile is active
~~~

**Important note:** a relative path such as `./config/` is resolved relative to the **working directory of the Java process** (the current directory when running the command), not by default relative to the directory containing the JAR. If you run `java -jar /opt/apps/my-service.jar` from `/srv/runtime`, Spring looks for `./config/` under `/srv/runtime`.

`Config Data` is only **one group of property sources** in `Environment`; OS environment variables, Java system properties, and command-line arguments are separate sources that can further override values read from files.

## 3. Where Does Spring Boot Automatically Search for Configuration Files?

When no custom locations are specified, Spring Boot looks for files named `application` with supported extensions in the following default locations:

| Search Order | Location | Meaning |
| --- | --- | --- |
| 1 | `classpath:/` | Classpath root, typically `src/main/resources/` after build |
| 2 | `classpath:/config/` | The `config` directory inside the classpath/JAR |
| 3 | `file:./` | Process working directory |
| 4 | `file:./config/` | The `config` directory external to the application |
| 5 | `file:./config/*/` | Direct subdirectories of `./config/` |

Items appearing later can override matching properties from earlier items. `file:` refers to resources on the filesystem; `classpath:` refers to resources on the classpath. The `*/` pattern in the default locations applies to direct subdirectories outside the application and does not scan recursively without limit.

Spring Boot accepts `.properties`, `.yaml`, and `.yml`. If both a `.properties` file and a YAML file exist in the same location for the same application name, **the `.properties` file takes precedence**. To avoid confusion over origin, standardize on a single format for an application.

You do not need to declare `spring.config.location` just for Spring to recognize `./config/application.yml`: that location is already in the default search path.

## 4. Precedence Between Packaged, External, and Profile Files

Within **the Config Data group alone** (setting aside custom import mechanisms), file groups are evaluated from **lowest to highest precedence**:

1. `application.*` files packaged inside the JAR.
2. `application-{profile}.*` files packaged inside the JAR.
3. `application.*` files outside the JAR.
4. `application-{profile}.*` files outside the JAR.

A higher-precedence source overrides **key by key**, rather than replacing the entire configuration file. Keys absent from the external file can still receive their default values from the packaged file.

Consider four files that all define `server.port`:

| Source | Content | Precedence Level |
| --- | --- | --- |
| `classpath:/application.yml` | `server.port: 8080` | Lowest |
| `classpath:/application-prod.yml` | `server.port: 8081` | Higher than packaged default |
| `file:./config/application.yml` | `server.port: 9080` | Higher than all packaged files in this example |
| `file:./config/application-prod.yml` | `server.port: 9180` | Highest among the four files |

When the `prod` profile is active, the result is **9180**. If you delete `./config/application-prod.yml`, the result becomes **9080**, not 8081: the **external** default file still takes precedence over the **packaged** profile-specific file.

If `prod` is not activated, only the non-profile files are used in this example; the result is **9080**.

When multiple profiles are active, such as `prod,live`, profile-specific files follow the rule that **later profiles can override earlier profiles**, evaluated within the same location group. Grouping locations with `;` in `spring.config.location` can affect this order; do not simply assume a file with `prod` in its name always beats every other source.

## 5. Example: Running an Application with Configuration Inside and Outside the JAR

Suppose the project has **`src/main/resources/application.yml`**:

~~~yaml
spring:
  application:
    name: order-service
server:
  port: 8080
app:
  greeting: "Hello from packaged configuration"
  notification:
    enabled: false
  request-timeout: 3s
~~~

Create an external file at **`/deploy/order-service/config/application.yml`**:

~~~yaml
server:
  port: 9090
app:
  notification:
    enabled: true
  request-timeout: 5s
~~~

And **`/deploy/order-service/config/application-prod.yml`**:

~~~yaml
server:
  port: 9191
app:
  request-timeout: 10s
~~~

Suppose `order-service.jar` is at `/deploy/order-service/order-service.jar`. Run from the deployment directory:

~~~bash
cd /deploy/order-service
java -jar order-service.jar --spring.profiles.active=prod
~~~

Then the effective properties are:

| Property | Final Value | Winning Source |
| --- | --- | --- |
| `spring.application.name` | `order-service` | Packaged `application.yml` |
| `app.greeting` | `Hello from packaged configuration` | Packaged `application.yml` |
| `app.notification.enabled` | `true` | `./config/application.yml` |
| `server.port` | `9191` | `./config/application-prod.yml` |
| `app.request-timeout` | `10s` | `./config/application-prod.yml` |

This example demonstrates two behaviors: external values override matching keys from inside the JAR, while keys not redeclared continue coming from the packaged configuration.

If you run from a different working directory, such as `/tmp`, the default `./config/` path points to `/tmp/config/`. To avoid depending on the run directory, use an absolute path with `spring.config.additional-location`.

## 6. Changing How Configuration Is Discovered

### 6.1. `spring.config.name`: Changing the Base File Name

By default, Spring searches for files named `application`. You can change it to `service-config`:

~~~bash
java -jar order-service.jar --spring.config.name=service-config
~~~

Spring then searches for `service-config.properties`, `service-config.yml`, `service-config-prod.yml`, and so on in the corresponding configuration locations.

### 6.2. `spring.config.location`: Replacing the Default Location List

~~~bash
java -jar order-service.jar --spring.config.location=optional:file:/etc/order-service/
~~~

This value tells Spring to search for configuration at the specified location **instead of the default locations**. If you still want to load defaults from the JAR, you must include the needed classpath location in the list or choose `spring.config.additional-location`.

When pointing to a **directory**, the path should end with `/`, because Spring appends the file name from `spring.config.name` to it. When pointing to a **specific file**, Spring reads that file directly.

Multiple locations can be separated by commas. Locations declared later can override earlier ones. A semicolon `;` puts locations into **the same location group** when you need to control profile-specific loading order.

### 6.3. `spring.config.additional-location`: Adding External Locations

This is the common choice when you want to **keep packaged defaults** and allow the deployment environment to override them:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

Spring still searches the default locations, then searches `/etc/order-service/`. Values from the additional location can override values in the default Config Data sources.

Because `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` determine **where** data must be loaded from, they are processed **very early** during startup. Provide them via command-line arguments, environment variables (e.g., `SPRING_CONFIG_ADDITIONAL_LOCATION`), or Java system properties. Do not place `spring.config.location` inside the very file you expect it to help Spring discover.

### 6.4. `optional:`: Locations That May Not Exist

If you configure a mandatory location that Spring cannot find, the application may stop with `ConfigDataLocationNotFoundException`. Add the `optional:` prefix to allow absence:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

This prefix only states that **missing that location is not a startup error**; it does not create default values for required keys. If the application needs a URL or password to run, you must still supply or validate that value.

## 7. Importing Other Configuration with `spring.config.import`

In addition to auto-discovered locations, a configuration file can declare additional imported sources:

~~~yaml
# src/main/resources/application.yml
spring:
  config:
    import: "optional:file:/etc/order-service/feature-flags.yml"
app:
  notification:
    enabled: false
~~~

And `/etc/order-service/feature-flags.yml`:

~~~yaml
app:
  notification:
    enabled: true
~~~

If the imported file exists, `app.notification.enabled` becomes **true**: the imported document takes precedence over the document declaring the import. If that file is absent, `optional:` lets startup continue and the default **false** still applies.

A few rules to know:

- `spring.config.import` can list multiple locations; later imports can override earlier imports.
- Each resource is imported only once, even if referenced repeatedly.
- Locations starting with `file:`, `classpath:`, or `/` are treated as fixed locations; relative paths without these prefixes may be resolved relative to the file declaring the import.
- Spring Boot also checks profile-specific variants of imported files when appropriate.

In environments using volume mounts such as Kubernetes, you can import a **configuration tree**: each file name becomes a configuration key, and the file content becomes its value.

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

For example, `/run/secrets/db.password` can create the property `db.password`. For deployment secrets, restrict volume access permissions and avoid logging secret contents.

**Distinction:** `spring.config.additional-location` adds **places where Spring automatically searches for standard-named config files**; `spring.config.import` is declared **inside a config document** to import specific resources.

## 8. Precedence of Sources Outside Config Data

Not every final value is decided by one of the `application.*` files. In a typical Spring Boot application, the following sources can override values from Config Data:

| Source | Example setting `server.port` | Relative Precedence |
| --- | --- | --- |
| Config Data | `server.port: 9090` in `application.yml` | Lower than the next three sources |
| OS environment variable | `SERVER_PORT=7070` | Higher than Config Data |
| Java system property | `-Dserver.port=6060` | Higher than environment variable |
| Program argument | `--server.port=5050` | Higher than Java system property |

Example:

~~~bash
java -Dserver.port=6060 -jar order-service.jar --server.port=5050
~~~

If this command has no other special higher-precedence source, the final port is **5050** because the `--server.port=5050` argument takes precedence over Config Data files and Java system properties.

The order above is a **common slice** of the `PropertySource` system; Spring Boot also has sources for testing, Devtools, JSON configuration, and Servlet environments. Do not assume an external file outside the JAR overrides everything. A pre-configured environment variable such as `SERVER_PORT` can explain why editing `application.yml` leaves the application using the old port.

## 9. Reading Configuration Values in Java Code

You can retrieve a single property with `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {
    private final String greeting;

    public GreetingService(@Value("${app.greeting}") String greeting) {
        this.greeting = greeting;
    }

    public String message() {
        return greeting;
    }
}
~~~

For a structured group of properties, use `@ConfigurationProperties` to map them to explicit types. For example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String greeting,
        Duration requestTimeout,
        Notification notification
) {
    public record Notification(boolean enabled) {}
}
~~~

Enable scanning for configuration classes in the application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Spring Boot combines sources by precedence and then binds values into `AppProperties`. For instance, `10s` is converted to `Duration`; `app.notification.enabled` becomes a `boolean`. What matters in this lesson is **where the value comes from and why it wins**, while designing/validating typed configuration is a subsequent topic.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Check / Resolve |
| --- | --- | --- |
| Edited `./config/application.yml` but see no change | Running JAR from a different working directory | Print the working directory at startup; use an absolute path via `spring.config.additional-location` |
| Files inside JAR are not loaded | `spring.config.location` was set, replacing default search locations | Use `spring.config.additional-location` or explicitly include classpath in `location` |
| Startup fails with `ConfigDataLocationNotFoundException` | Specified file/directory does not exist | Check path, mount, read permissions; use `optional:` if genuinely optional |
| `application-prod.yml` has no effect | `prod` profile is not active or a higher-precedence source overrides it | Check `spring.profiles.active`, external files, environment variables, and CLI arguments |
| Changed config file but value is still unexpected | A higher-precedence source shares the key, or both `.properties` and YAML exist at the same location | List every place declaring the key and their precedence; choose one file format |
| Updated external file but running app still uses old value | Config Data is normally read at startup | Restart or use a dedicated configuration refresh mechanism if the system supports it |
| Leaked URL/token/password | Committed secret into `application.yml` or logged the entire `Environment` | Supply secrets through an appropriate secrets channel, restrict access, and never log secrets |

When investigating a property, check **its current value** and **the contributing source**. If the project enables Spring Boot Actuator, the `env` and `configprops` endpoints can help diagnose it; use them only with proper access controls and sensitive-data masking configured.

## 11. Self-Check Exercises

**Exercise 1 — Default Values and Overrides**

Inside the JAR:

~~~properties
server.port=8080
app.color=blue
~~~

Outside the JAR at `./config/application.properties`:

~~~properties
server.port=9090
~~~

The application runs from the directory containing `config/`, with no profiles or other overrides. Determine `server.port` and `app.color`.

**Answer:** `server.port=9090` comes from the external file; `app.color=blue` keeps its packaged value because the external file does not declare this key.

**Exercise 2 — Profiles Do Not Guarantee Beating External Defaults**

Inside the JAR: `application-prod.yml` sets `server.port=8081`. External file: `./config/application.yml` sets `server.port=9080`. `prod` is activated and there are no other overrides. Which port is used?

**Answer:** **9080**, because external Config Data outside the JAR (non-profile-specific) has higher precedence than profile-specific Config Data packaged inside the JAR.

**Exercise 3 — Choosing a File-Loading Mechanism**

You want the JAR to always keep `application.yml` as the default set; each environment has an additional directory `/etc/order-service/`. The directory may be absent on a developer's machine. Choose a property and provide the run command.

**Suggested Answer:**

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

This command adds the external path, keeps default locations, and allows the external directory not to exist.

## 12. Deployment Takeaways

- Configuration packaged in the JAR serves as **runnable defaults**; external configuration serves to **vary settings by environment**.
- The order within Config Data alone is **packaged common → packaged profile-specific → external common → external profile-specific**; sources such as environment variables and CLI arguments can rank even higher.
- **Working directory** determines what `./config/` resolves to.
- Use `spring.config.additional-location` to add search locations; `spring.config.location` to replace the default list; `spring.config.import` to load resources declared inside a file.
- Only use `optional:` when absence of the resource is genuinely acceptable; do not use it to hide missing required configuration.
- Keep secrets out of source code and verify which source is overriding before concluding a config file is not working.

**Reference:** [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
