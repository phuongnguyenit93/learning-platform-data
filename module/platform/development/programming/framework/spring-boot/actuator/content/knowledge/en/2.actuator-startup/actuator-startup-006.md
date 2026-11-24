# Organizing Management Configuration in application.properties or YAML

## 1. What problem does management configuration solve?

After adding Actuator, the application must specify which operational capabilities will be used: which endpoints are exposed over HTTP, how much health information is displayed, which path or port is used, and which environments need different configurations.

Spring Boot reads configuration sources and puts values into the configuration environment and corresponding configuration objects. **Binding values to configuration objects** lets components consume values with the right types, such as an endpoint list or a port number.

Properties and YAML are two ways to represent configuration. They are not two different Actuator mechanisms.

For example, the key:

~~~text
management.endpoints.web.exposure.include
~~~

can be written on one properties line or as a YAML tree. What matters is the **key name, value, and effective configuration source**, not which format looks tidier.

## 2. Recognizing key groups before writing

| Key group | Responsibility | Example |
| --- | --- | --- |
| `management.endpoint.<id>.*` | Configure a single endpoint | `management.endpoint.health.show-details` |
| `management.endpoints.web.*` | How the endpoint set is exposed over HTTP | `management.endpoints.web.exposure.include` |
| `management.endpoints.jmx.*` | Configuration for exposing endpoints over JMX | `management.endpoints.jmx.exposure.include` |
| `management.server.*` | Options for the management server | `management.server.port` |
| `management.metrics.*` | Metrics options in that group | `management.metrics.tags.application` |

Notice singular **endpoint** when configuring an individual endpoint and plural **endpoints** when configuring the set of endpoints. The two names are not interchangeable.

`server.port` is the main application server port; `management.server.port` can set a separate port for management. `logging.level.*` belongs to the logging system and must not be moved under `management` just because logs serve operations.

Cross-check key names with the exact Boot version in use. This lesson uses the Spring Boot 3.3.x contract; look up keys in [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### Web configuration does not govern every endpoint type

`management.endpoints.web` is a dedicated configuration group for web; it has base path, exposure, and path mapping. JMX configuration is a separate group. Exposing an endpoint over HTTP does not automatically expose it over JMX. See [WebEndpointProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.html).

You must also separate three decisions:

1. Whether the endpoint is enabled and meets conditions to be created.
2. Whether the endpoint is exposed on the HTTP interface.
3. Whether a specific request is permitted to access it.

A single `include` line does not replace the other two decisions.

## 3. Writing a base configuration in two equivalent formats

For a typical project, files are placed in `src/main/resources`. Choose **one** of the two options below for the same example.

### 3.1. application.properties

~~~properties
spring.application.name=management-config-demo

management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info

management.endpoint.health.show-details=never
management.endpoint.shutdown.enabled=false
~~~

Organization using blank lines:

- Application identification.
- Web endpoint path and scope.
- Visibility or enable/disable policy for individual endpoints.

Blank lines only help humans read; they do not create a new configuration scope. Each line still needs the full key name.

### 3.2. application.yml

~~~yaml
spring:
  application:
    name: management-config-demo

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
    shutdown:
      enabled: false
~~~

`application.yaml` is also a YAML filename supported by Spring Boot. The examples use `application.yml` for consistent naming.

When reading the tree, join levels with dots:

~~~text
management
  endpoints
    web
      exposure
        include
→ management.endpoints.web.exposure.include
~~~

The YAML list `health`, `info` binds into a list equivalent to the properties value `health,info`.

### 3.3. Understanding the exact meaning of the example

| Key | Meaning in the example |
| --- | --- |
| `spring.application.name` | Sets the application name |
| `management.endpoints.web.base-path` | Sets the management web prefix to /actuator |
| `management.endpoints.web.exposure.include` | Selects health and info to expose over HTTP when available |
| `management.endpoint.health.show-details` | Does not show health details |
| `management.endpoint.shutdown.enabled` | Keeps the shutdown endpoint disabled |

Configuration does not create an HTTP server for a non-web application. Nor does it guarantee `info` will always return build info: endpoint data still depends on actual contributing components.

In Spring Boot 3.3, by default only `health` is exposed over HTTP. Include/exclude select the interface scope; when an endpoint is listed in both, `exclude` takes precedence. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 3.4. Do not keep two base configuration files as a "backup"

Choose one format consistently. If both properties and YAML exist in the same location, Spring Boot gives precedence to properties when keys collide.

Therefore, editing YAML while leaving a different value in properties can cause the result not to change as expected. This is not necessarily an indentation bug; you might simply be reading the wrong winning source. See [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

## 4. Syntax rules that easily cause misconfiguration

### 4.1. YAML uses indentation to represent scope

In YAML, sibling entries at the same level must align vertically. Use spaces for indentation, never tabs.

In the base example, `endpoint` and `endpoints` are siblings under `management`. If you place `endpoint` under `endpoints.web`, the flattened key name will differ from the Actuator key expected.

Inspect the tree from left to right when a property has no effect, rather than checking only the final key like `include` or `show-details`.

### 4.2. Only one management key per YAML document

Do not merge configuration snippets by repeating two root `management:` blocks in the same document. Merge the branches into a single shared block:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Duplicate mapping keys are not a valid way to accumulate configuration. Nor should you rely on a tool happening to pick the last value. Rules on mappings and indentation are described in [YAML Specification](https://yaml.org/spec/1.2.2/).

If you intentionally use multiple YAML documents, they must be separated by `---` and have explicit activation conditions when needed. That is a different mechanism from duplicate keys within a single document.

### 4.3. The asterisk must be written differently

If you genuinely need the wildcard for all endpoints, the syntax is:

~~~properties
management.endpoints.web.exposure.include=*
~~~

or:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

In YAML, an unquoted asterisk has syntactic meaning related to aliases, so quoting is required in the case above.

This is only an illustration of wildcard syntax. The lesson's base configuration still selects `health,info`; there is no need to expose all endpoints to verify reading the file.

### 4.4. Quotes and comments in properties are not shell syntax

For a properties file, write:

~~~properties
management.endpoints.web.base-path=/actuator
# Select web endpoints to use
management.endpoints.web.exposure.include=health,info
~~~

Do not wrap values in double quotes out of shell or YAML habit. In standard properties format, quotes can become part of the value.

Also put comments on their own lines. For instance, appending `# note` at the end of a properties value line does not have the same meaning as a YAML comment. Line format and comments are described in [Java Properties API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html).

### 4.5. A list is not a set of keys that auto-merges

Both YAML list representations below work for `include`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
~~~

When overriding a list in a profile or higher-precedence source, declare the complete desired list. Do not assume adding one item in another file will automatically merge with all items from the base configuration.

The experiment section will directly demonstrate the list being replaced by a command-line value.

## 5. Separating shared parts and per-profile differences

Suggested structure if choosing properties:

~~~text
src/main/resources/
├── application.properties
└── application-local.properties
~~~

If choosing YAML:

~~~text
src/main/resources/
├── application.yml
└── application-local.yml
~~~

The base file holds shared decisions; the `local` file records only what needs to change when testing locally. There is no need to copy the entire `management` block into every profile.

### 5.1. Contents for the local profile

In `application-local.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=always
~~~

Or in `application-local.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: always
~~~

When `local` is active, the example wants to read metrics as well and display health details. This is a choice for testing; the profile name `local` does not automatically guarantee the application can only be accessed locally. If used over HTTP, you must also control the listening address and access permissions.

If needed for multiple environments, you can add `application-prod.yml` or corresponding properties to express differences. Profile names are defined by the project; not every application needs dev/test/staging/prod.

### 5.2. Activating a profile from outside the profile file

With the Gradle wrapper in a project having the `bootRun` task:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
~~~

With the Maven wrapper and Boot Maven plugin:

~~~powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=local"
~~~

Do not put `spring.profiles.active=local` inside `application-local.properties` itself and expect the file to activate itself. Spring Boot only allows configuring active/default profiles in non-profile-specific documents; documents already activated by `spring.config.activate.on-profile` share this constraint. See [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

`--args` is how `bootRun` receives application arguments; `spring-boot.run.profiles` is the corresponding property of the Maven plugin. See [Running with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html) and [Running with Maven](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html).

### 5.3. When using multiple YAML documents in one file

Instead of splitting out `application-local.yml`, a project can intentionally place a local document inside `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
---
spring:
  config:
    activate:
      on-profile: local

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

The two `management` blocks belong to **two different documents**, separated by `---`. The second document participates only when the `local` profile is active.

This is an alternative organizational approach. When first learning, using separate profile files is usually easier to compare; avoid keeping both approaches writing different values without a clear reason.

## 6. Organizing related options without confusing scopes

### 6.1. Management port and web path

Optional configuration snippet for a test HTTP application:

~~~properties
server.port=8080
management.server.port=8081
management.server.address=127.0.0.1
management.endpoints.web.base-path=/manage
~~~

Equivalent YAML:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /manage
~~~

When no other base path is configured and health is available, the corresponding management URL is `http://127.0.0.1:8081/manage/health`. Business APIs remain on the main port.

A separate `management.server.address` is used when the management port differs from the main port. When sharing a port, consider the main server address. When merging this snippet into an existing configuration, merge into the existing `server`/`management` blocks. See [Spring Boot 3.3 — Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 6.2. Metrics tags can reuse a shared value

Example addition in properties:

~~~properties
management.metrics.tags.application=${spring.application.name}
~~~

Or merged into an existing `management` branch:

~~~yaml
management:
  metrics:
    tags:
      application: "${spring.application.name}"
~~~

The placeholder fetches the configured application name. That way, changing the application name does not require editing the same value in multiple places.

This is a common metrics tag under Boot's supported mechanism; it is not a command to open the metrics endpoint or start a Prometheus server. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 6.3. Do not invent keys to replace standard keys

A name like `management.exposure` may look reasonable to an author, yet it does not replace `management.endpoints.web.exposure.include`.

Not every misspelled property stops the application immediately. How unrecognized fields are handled depends on the binding target object and reading mechanism. Thus, "it starts up" does not prove every management key is valid. See [ConfigurationProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).

Use IDE suggestions and dependency-matched metadata to reduce typos; then verify the bound values and actual behavior.

## 7. Verifying both formats and overriding

The following experiment uses a Boot **3.3.0** project, JDK **21**, with the Actuator starter and an appropriate run task. Java code uses syntax compatible with Java 17 and above. No web server is needed: the goal is to see which configuration was read and which list was bound.

### 7.1. Sample project prerequisites

In a Gradle project that already has the Boot plugin and 3.3.0 dependency version management, you need:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

The snippet above is the dependencies portion to merge, not a complete `build.gradle`.

Choose either the properties file set or the YAML file set from sections 3 and 5, and place it in `src/main/resources`. The experiment assumes no environment variables, external files, or other arguments are overriding the printed keys.

### 7.2. A program that reads just three values

Create `src/main/java/example/managementconfig/ManagementConfigApplication.java`:

~~~java
package example.managementconfig;

import java.util.List;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ManagementConfigApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ManagementConfigApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            Environment environment = context.getEnvironment();
            List<String> included = Binder.get(environment)
                    .bind("management.endpoints.web.exposure.include",
                            Bindable.listOf(String.class))
                    .orElse(List.of());

            System.out.println("basePath=" + environment.getProperty(
                    "management.endpoints.web.base-path"));
            System.out.println("include=" + String.join(",", included));
            System.out.println("showDetails=" + environment.getProperty(
                    "management.endpoint.health.show-details"));
        }
    }
}
~~~

The program does three things:

- Starts Spring Boot in non-web mode.
- Uses `Environment` to read two single values and `Binder` to read the list.
- Prints the selected values and closes the context.

`Binder` supports binding configuration from property sources into desired data types. Reading as a list handles both comma-separated strings and YAML lists uniformly. See [Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html).

This code is a small check tool for the lesson; there is no need to add configuration-printing logic to every real application.

### 7.3. Without the local profile enabled

Run:

~~~powershell
.\gradlew.bat bootRun
~~~

With the base configuration set described, the three lines printed by the program are:

~~~text
basePath=/actuator
include=health,info
showDetails=never
~~~

The result is identical for both formats. This is stdout of the check program; any framework logs are not treated as fixed output.

To compare properties and YAML yourself, use two separate test copies or switch formats by keeping exactly one file set. Avoid accidentally testing both while properties is actually shadowing YAML values.

### 7.4. With the local profile enabled

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
~~~

Result:

~~~text
basePath=/actuator
include=health,info,metrics
showDetails=always
~~~

Base path is inherited from the base file because the profile does not redeclare it. The two properties present in the profile carry the new values.

### 7.5. Overriding include with a command-line argument

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local --management.endpoints.web.exposure.include=health"
~~~

Result:

~~~text
basePath=/actuator
include=health
showDetails=always
~~~

Include becomes only `health`. It is not automatically merged into `health,info,metrics` because a higher-precedence value was supplied for this list.

`show-details` remains `always` from the profile because the argument does not override that key. Overriding happens per property; it does not replace the entire `management` block at once.

### 7.6. What the program verifies and does not verify

The three printed lines verify file loading, profile selection, argument precedence, and list conversion. They **do not verify HTTP URLs** or access policies, because the program sets `WebApplicationType.NONE`.

For a real web application, you must call the right URL and verify access permissions separately. Having an endpoint name in `include` does not prove that endpoint meets conditions to exist.

## 8. Checking configuration sources when results differ from expectations

### 8.1. Finding where the same key is set

When you edited a file yet behavior did not change, check in order:

1. Are you launching the right module and has the artifact been rebuilt?
2. Is the file inside a loaded resource location?
3. Which profile is active?
4. Is the same key in another properties/YAML file, an external file, an environment variable, or a launch argument?
5. Is the property spelled properly and used by the corresponding component?

In typical application runs, command-line arguments can override values from configuration files, as the experiment showed. Environment variables are also an input source to inspect.

An example environment variable name for the `include` key is:

~~~text
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE
~~~

Inspect arguments in the IDE Run configuration or deployment environment, not just `application.yml` in source.

### 8.2. Using diagnostic tools within the right scope

In a web application with appropriate access policies, the `env` endpoint helps inspect property sources and value origins; data may be masked according to configuration. See [Spring Boot 3.3 — Environment REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

The `configprops` endpoint helps inspect bound configuration beans and their inputs. It helps distinguish "the key is in Environment" from "which configuration object received the value". See [Spring Boot 3.3 — Configuration Properties REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

There is no need to expose these two endpoints publicly or enable showing all values to complete this lesson. Prefer local inspection and inspect only keys that do not contain secrets.

### 8.3. Notes on filenames and runtime updates

An arbitrary file named `management.yml` is not automatically loaded just because it contains `management` keys. If splitting files for project needs, explicit loading/import configuration is required.

Changing `application.yml` in source also does not automatically update a process already running with an old artifact. After changes, rebuild/restart according to the project's mechanism and re-verify; do not assume every management key supports dynamic reloading.

## 9. Common mistakes

| Symptom | What to check |
| --- | --- |
| Edited YAML yet value stays the same | Is there a properties file in the same location or a higher-precedence source? |
| One key has no effect while application still runs | Right name, right YAML level, and right version line? |
| Local profile is not loaded | Was the profile activated from a valid source? |
| Only wanted to add metrics but lost info | Did you override the entire list with a new value missing info? |
| YAML fails immediately when reading asterisk include | Did you write `"*"` as a quoted string? |
| Merging another management snippet causes config error | Are root keys duplicated within the same document? |
| Changed management port yet still calling main port | Did you recalculate the URL using the actual port and base path? |
| Include is right yet no URL exists | Are web server, endpoint component, exposure, and access permissions in place? |
| Renamed file to management.yml and values disappeared | Is the file configured to be imported/loaded? |
| Runs cleanly so concluded all properties are valid | Did you check bound values and expected behavior? |

### Practice on your own

1. Convert the base configuration from properties to YAML while keeping the exact values and lists.
2. Enable the `local` profile and predict the three output lines before running the program.
3. Override `include` with `health` and explain why `info,metrics` disappear from the output.
4. For a web application with management port 8081 and base path `/manage`, state the health URL when there is no extra base path.
5. Find a key declared in multiple sources in the sample project; determine the winning value using evidence rather than just the file currently open.

**Reference hint:** focus on the flattened key name, the winning configuration source, the bound value type, and the behavior of the consuming component. The two formats are equivalent when representing the same effective configuration; wrong indentation or overrides can make them cease to be equivalent.
