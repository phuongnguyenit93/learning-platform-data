# `application-{profile}` Files and Their Relationship with the Common Configuration File in Spring Boot

## 1. The problem: one application, multiple configuration environments

A Spring Boot application typically uses the same source code and the same JAR artifact to run in development (dev), test, staging, and production (prod) environments. These environments share much of their configuration, yet also have differences:

- Application name, common logging settings, and default values may be identical.
- Server port, external service addresses, connection limits, timeouts, and feature toggle flags may differ.
- Production may need less verbose logs, tighter resource limits, and different infrastructure addresses from dev.

Spring Boot addresses this need by allowing you to combine a **common configuration file** with **profile-specific configuration files**. The familiar naming pattern is:

~~~text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
~~~

Where:

- `application.yml` holds common properties used as defaults across environments.
- `application-dev.yml` supplements or overrides properties for the `dev` profile.
- `application-prod.yml` supplements or overrides properties for the `prod` profile.

The name `application-{profile}` is a **naming pattern**. When the profile is named `prod`, `{profile}` is replaced with `prod`, forming `application-prod.yml`. It is not a filename containing literal curly braces.

The goal of this article is to understand when the files are loaded, how they combine with each other, and why a property ultimately receives a particular value.

## 2. What is a profile?

A **Spring profile** is a name representing a group of configuration conditions. Spring can use profiles to decide which components are created, such as beans annotated with `@Profile("prod")`. For Config Data specifically, Spring Boot also uses profiles to **activate matching configuration files**.

Example:

~~~text
Active profile: dev
→ application.yml
→ application-dev.yml

Active profile: prod
→ application.yml
→ application-prod.yml
~~~

The two lines under each state represent only the files applied within the same configuration location, not every `PropertySource`. Spring Boot can still receive values from environment variables, system properties, and command-line arguments.

An application can activate **multiple profiles at once**, such as `prod,monitoring`. In that case, Spring Boot considers files corresponding to both `prod` and `monitoring`.

Important point: **profiles do not automatically create physical environments**. The name `prod` only carries meaning because the application and deployment system use that name to organize configuration.

## 3. How is the common `application.yml` file loaded?

If an application has the file:

~~~yaml
# src/main/resources/application.yml
spring:
  application:
    name: catalog-service

server:
  port: 8080

app:
  banner: "Hello from Catalog"
  feature:
    recommendation-enabled: false
  request-timeout: 5s
~~~

The corresponding properties are:

~~~properties
spring.application.name=catalog-service
server.port=8080
app.banner=Hello from Catalog
app.feature.recommendation-enabled=false
app.request-timeout=5s
~~~

The `application.yml` file provides **default values**. It is loaded during standard Config Data lookup regardless of which profile is active, unless configuration location/naming has been customized or the file is not in a location Spring Boot searches.

`application.properties` and `application.yaml` are also supported. Stick to one consistent format for clarity; when both `.properties` and YAML exist with the same name in the same location, Spring Boot gives precedence to `.properties`.

A key in the common file does not need to be repeated in every profile-specific file. Unless overridden by a higher-precedence source, the common value remains effective.

## 4. `application-{profile}.yml` files only add or override keys that need to differ

Keeping the common file above, add the file:

~~~yaml
# src/main/resources/application-dev.yml
server:
  port: 8081

app:
  banner: "Running in DEV"
  feature:
    recommendation-enabled: true
~~~

And another file:

~~~yaml
# src/main/resources/application-prod.yml
server:
  port: 9090

app:
  request-timeout: 15s
~~~

When `dev` is activated, the result within these packaged files is:

| Key | Effective value | Source |
| --- | --- | --- |
| `spring.application.name` | `catalog-service` | Common file |
| `server.port` | `8081` | `application-dev.yml` |
| `app.banner` | `Running in DEV` | `application-dev.yml` |
| `app.feature.recommendation-enabled` | `true` | `application-dev.yml` |
| `app.request-timeout` | `5s` | Common file |

When `prod` is activated:

| Key | Effective value | Source |
| --- | --- | --- |
| `spring.application.name` | `catalog-service` | Common file |
| `server.port` | `9090` | `application-prod.yml` |
| `app.banner` | `Hello from Catalog` | Common file |
| `app.feature.recommendation-enabled` | `false` | Common file |
| `app.request-timeout` | `15s` | `application-prod.yml` |

An important point: **Spring Boot does not replace the entire common file with the profile file**. Property sources are layered on top of one another. When multiple sources contain the same key, the higher-precedence source decides the final value for that key; keys not overridden remain.

For example, if `application-prod.yml` does not contain `spring.application.name`, the application still uses `catalog-service` from the common file.

## 5. Activating profiles so Spring Boot selects the corresponding file

Spring Boot needs to know which profiles are active. The most common ways include:

### 5.1. Argument when running the JAR

~~~bash
java -jar catalog-service.jar --spring.profiles.active=dev
~~~

Or:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

The `--spring.profiles.active=...` option is an application argument recognized by Spring Boot at startup.

### 5.2. Environment variables

In a shell environment supporting the following syntax:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar catalog-service.jar
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar catalog-service.jar
~~~

Spring Boot maps environment variable names to properties, so `SPRING_PROFILES_ACTIVE` corresponds to `spring.profiles.active`.

### 5.3. Java system property

~~~bash
java -Dspring.profiles.active=prod -jar catalog-service.jar
~~~

Notice the Java argument order: `-Dspring.profiles.active=prod` goes **before** `-jar`.

### 5.4. Configuration in the common file

You can set a default active profile directly in the **non-profile-specific** configuration:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

However, do not hardcode `prod` or deployment profiles inside a shared JAR if the deployment system is responsible for selecting environments. Using arguments or environment variables at deployment time allows a single artifact to serve multiple environments.

`spring.profiles.active` is a property subject to ordinary precedence across property sources: a value supplied from a higher-precedence source can override the value in the common file.

**Important restriction:** `spring.profiles.active` and `spring.profiles.default` must be declared in **non-profile-specific documents**. Do not place them in `application-prod.yml` or inside a YAML document activated by `spring.config.activate.on-profile`. Spring Boot treats such misplaced declarations as invalid configuration.

## 6. When no profile is activated: common file and default profile

If no active profile is specified, Spring uses the default profile named `default`. With standard configuration, Spring Boot can load:

~~~text
application.yml
application-default.yml
~~~

If `application-default.yml` exists and is valid, properties from it can supplement/override common properties, following the same profile-file mechanism. If the file does not exist, the application can still use `application.yml` and other configuration sources.

Example:

~~~yaml
# application.yml
server:
  port: 8080
app:
  mode: common
~~~

~~~yaml
# application-default.yml
app:
  mode: fallback
~~~

With no other active profile, `app.mode` can receive `fallback` from the file for the default profile. When `prod` is activated, `application-default.yml` is no longer automatically loaded on the grounds of “no active profile”; files for `prod` are considered instead.

You can rename the default profile with `spring.profiles.default` in a non-profile-specific document or through a sufficiently early configuration source. `spring.profiles.default=none` is an option if you do not want a default profile. **You do not need to create `application-default.yml` just because Spring has a default profile concept**.

Distinguish:

- **No active profile:** Spring considers the default profile, typically `default`.
- **Active profile `dev`:** Spring considers `dev` and does not automatically treat `default` as an additional active profile.

## 7. Precedence order: packaged and external matter as much as profiles

This is the most commonly misunderstood part. Common files and profile-specific files can live **inside the JAR** or **outside the JAR**.

In default Config Data lookup, for four typical groups, the order from lowest to highest precedence is:

1. Common `application.*` file **packaged inside the JAR**.
2. `application-{profile}.*` file **packaged inside the JAR**.
3. Common `application.*` file **outside the JAR**.
4. `application-{profile}.*` file **outside the JAR**.

A source appearing later in this list can override same-named keys from an earlier source. This leads to a seemingly surprising result: **an external common `application.yml` can beat a packaged `application-prod.yml` inside the JAR**.

Example:

~~~text
JAR / classpath:
  application.yml          → server.port=8080
  application-prod.yml     → server.port=8081

Working directory:
  ./config/application.yml      → server.port=9080
  ./config/application-prod.yml → server.port=9180
~~~

With profile `prod` enabled:

| Existing files | Final `server.port` |
| --- | --- |
| Only the two files in the JAR | `8081` |
| Add `./config/application.yml` | `9080` |
| All four files present | `9180` |
| Remove external `application-prod.yml`, keep external common | `9080` |

Explanation for the second case: an external **non-profile-specific** file still takes higher precedence than a profile-specific file **packaged inside the JAR**, under standard Config Data ordering.

This is why you cannot look solely at the filename `application-prod.yml` and assert that every value inside it will win.

### Working directory for external files

By default, Spring Boot also searches locations such as `file:./`, `file:./config/`, and immediate subdirectories `file:./config/*/`. The `./` path is resolved relative to the **working directory of the Java process**, not necessarily the directory containing the JAR.

Suppose:

~~~text
/opt/catalog/
  catalog-service.jar
  config/
    application-prod.yml
~~~

When running:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Spring can find `./config/application-prod.yml`. However, when running the same JAR from `/tmp`, `./config/` resolves to `/tmp/config/`.

To avoid depending on the working directory, you can configure an absolute external location using `spring.config.additional-location`:

~~~bash
java -jar /opt/catalog/catalog-service.jar --spring.profiles.active=prod --spring.config.additional-location=optional:file:/etc/catalog/
~~~

`spring.config.additional-location` keeps the default locations and adds new ones. In contrast, `spring.config.location` **replaces** the default location list. Consider carefully if the project still depends on packaged `application.yml`.

## 8. Multiple active profiles: the “later profile wins” rule

An application can enable multiple profiles:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod,observability
~~~

Suppose within the same location group you have:

~~~yaml
# application.yml
app:
  feature-enabled: false
  log-sample-rate: 0.1
~~~

~~~yaml
# application-prod.yml
app:
  feature-enabled: true
  log-sample-rate: 0.2
~~~

~~~yaml
# application-observability.yml
app:
  log-sample-rate: 0.8
~~~

With the order `prod,observability` in this same-location-group example, the later profile file `observability` can override overlapping keys from `prod`. The result is:

~~~properties
app.feature-enabled=true
app.log-sample-rate=0.8
~~~

Change to:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=observability,prod
~~~

Under the same conditions, `app.log-sample-rate` can become `0.2` because `prod` comes later.

This is the **last wins** rule among active profile-specific properties at the same location tier. However, when combining multiple packaged/external locations or configuring `spring.config.location` with location groups, you must also consider **ordering across locations**; never apply the rule “the last profile always wins regardless of where the file lives.”

For instance, a property placed in a higher-precedence external common file can still beat a property in a packaged profile file, even if that profile name is last in the list.

If an application uses multiple profiles with distinct responsibilities, avoid defining the same key in multiple files unless an override is intentionally desired.

## 9. Does a missing profile-specific file cause the application to fail on startup?

Ordinarily, **you do not need to create every `application-{profile}.yml` file**. For example, an application has `application.yml` and `application-prod.yml` but no `application-dev.yml`. When activating `dev` with default search locations, the application can still use common values because the absence of `application-dev.yml` in a default search location is not treated as an error.

This differs from **explicitly specifying a required missing Config Data resource**, such as using `spring.config.import` pointing to a specific file. That situation can cause Spring Boot to fail with a missing-location error unless marked optional.

Do not use `optional:` to “create” profiles or give new configuration files higher priority. That prefix only permits a Config Data location to be absent without treating its absence alone as an error.

Example of a valid optional import when absence is permitted:

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:/etc/catalog/feature-flags.yml"
~~~

This is an explicit resource import mechanism. It differs from Spring automatically looking up `application-prod.yml` when the `prod` profile is activated.

## 10. A multi-document YAML file can replace separate profile files

Spring Boot allows placing multiple YAML documents inside the same `application.yml`, separated by `---`. A document can be activated when a profile matches via `spring.config.activate.on-profile`.

Example:

~~~yaml
# application.yml — common document
app:
  shipping:
    provider: mock
    timeout: 3s

---
# Document activated only when profile prod is active
spring:
  config:
    activate:
      on-profile: prod

app:
  shipping:
    provider: real
    timeout: 10s
~~~

When profile `prod` is not active, the application receives provider `mock` and timeout `3s` from the common document. When `prod` is active, the second document applies and can override them to `real` and `10s`.

Two common organizational approaches:

| Separate-file organization | Multi-document YAML organization |
| --- | --- |
| `application.yml` + `application-prod.yml` | One `application.yml` containing multiple documents separated by `---` |
| Easy to isolate each environment's configuration into independent files | Easy to view common settings and profile branches in the same file |
| Filename determines the applicable profile | `spring.config.activate.on-profile` defines the document activation condition |
| Can have both packaged and external variants | Still subject to Config Data precedence across locations |

A document with a `spring.config.activate.on-profile` condition is a **profile-specific document**. Do not place `spring.profiles.active`, `spring.profiles.default`, or `spring.profiles.include` in that document to try activating additional profiles; profile-selection properties must reside in non-profile-specific documents.

`spring.config.activate.on-profile` accepts profile expressions (such as `prod | staging`); expression syntax follows Spring's profile expression rules, not a list of filenames.

## 11. Reading the final value in Java code

The Config Data mechanism merges sources into lookupable properties. In Spring code, you can use `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DeploymentInfo {
    private final Environment environment;

    public DeploymentInfo(Environment environment) {
        this.environment = environment;
    }

    public String activeProfiles() {
        return String.join(", ", environment.getActiveProfiles());
    }

    public String displayBanner() {
        return environment.getProperty("app.banner", "Default banner");
    }

    public Integer port() {
        return environment.getProperty("server.port", Integer.class);
    }
}
~~~

`getActiveProfiles()` reports explicitly activated profiles. When that list is empty, `getDefaultProfiles()` is the place to inspect default profiles. Calling `getProperty("server.port")` returns **the effective value after resolving precedence** in `Environment`, not a fixed value from one file name.

For groups of properties, `@ConfigurationProperties` is better suited than multiple individual `@Value` fields. Suppose common YAML:

~~~yaml
app:
  client:
    base-url: "https://sandbox.example.org"
    timeout: 3s
~~~

File `application-prod.yml`:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    timeout: 12s
~~~

Declaration:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {}
~~~

And enable scanning:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

The application will bind the **final values** in `Environment` into `ClientProperties`. When `prod` is active and there are no higher-precedence overrides, `baseUrl` and `timeout` are `https://api.example.org` and `12s`, respectively.

## 12. Relationship between profile files and other configuration sources

Profile-specific files are one part of Config Data, not the entire Spring Boot configuration system.

Consider the following example in `application-prod.yml`:

~~~yaml
server:
  port: 9090
~~~

If the deployment environment also sets:

~~~bash
export SERVER_PORT=7070
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Assuming no even higher-precedence source, the final `server.port` is `7070` because OS environment variables outrank Config Data.

Similarly, an application argument:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod --server.port=6060
~~~

can beat both the profile file and standard environment variables.

Keep in mind this common relative order:

~~~text
Config Data (application.yml / application-prod.yml / external files)
         < OS environment variables
         < Java system properties
         < command-line arguments
~~~

This is a **common slice of precedence**, not a complete catalog of every property source. Spring Boot also includes configuration sources for tests and specific runtime environments.

Therefore, if you edit `application-prod.yml` and the application's value does not change, it is not necessarily ignored: another source may be overriding it.

## 13. Not all configuration “deep merges” intuitively

For independent scalar keys, higher-precedence sources override per key. When binding complex structures, however, watch out for lists.

Example common file:

~~~yaml
app:
  upstreams:
    - name: primary
      url: "https://primary.example.org"
    - name: backup
      url: "https://backup.example.org"
~~~

File `application-prod.yml`:

~~~yaml
app:
  upstreams:
    - name: production
      url: "https://prod.example.org"
~~~

When bound to `List<Upstream>`, the list from the higher-precedence profile source usually **replaces the old list** under how the binder handles lists, rather than automatically keeping the `backup` element from the common file.

Therefore, when configuring a list that differs between dev and prod, **declare the full desired list** in the profile file.

By contrast, independent keys such as `app.client.timeout` and `app.client.base-url` can come from different files. Do not equate how a single key is resolved with how an entire collection structure is bound.

## 14. Deployment example with Docker Compose

An application has common configuration inside the JAR:

~~~yaml
# application.yml
spring:
  application:
    name: inventory-service

server:
  port: 8080

app:
  stock:
    refresh-interval: 30s
~~~

Profile file:

~~~yaml
# application-prod.yml
app:
  stock:
    refresh-interval: 5m
~~~

Docker Compose can pass the profile and an external file location outside the JAR:

~~~yaml
services:
  inventory:
    image: example/inventory-service:latest
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SPRING_CONFIG_ADDITIONAL_LOCATION: "optional:file:/etc/inventory/"
    ports:
      - "8080:8080"
    volumes:
      - ./config:/etc/inventory:ro
~~~

In this example, if the container has `/etc/inventory/application-prod.yml`, that source can supplement or override existing Config Data keys. `server.port` can also be changed by deployment configuration if an override is provided. Whenever changing the actual server port, re-check `ports` mappings and container health checks.

This configuration style lets you reuse the same image across multiple environments. Do not package production secrets into committed `application-prod.yml` files; secrets should be supplied via an appropriate secrets management system or deployment environment.

## 15. Profiles in automated testing

In integration tests, you can select profiles using Spring Test's `@ActiveProfiles`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigurationTest {
    @Autowired
    private Environment environment;

    @Test
    void shouldActivateTestProfile() {
        assertThat(environment.getActiveProfiles()).contains("test");
    }
}
~~~

If `src/test/resources/application-test.yml` or an appropriate test configuration source exists, properties from it are evaluated according to Config Data and test precedence rules.

You can place in `src/test/resources/application-test.yml`:

~~~yaml
app:
  external-service:
    url: "http://localhost:18080"
~~~

However, do not assume every test automatically uses the `test` profile merely because `application-test.yml` exists. Tests need the profile activated via `@ActiveProfiles("test")`, environment configuration, or the appropriate test mechanism.

## 16. Common errors and how to diagnose them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `application-prod.yml` is not applied | `prod` profile has not been activated | Check `spring.profiles.active` and `Environment#getActiveProfiles()` |
| `prod` is active, yet common value is still used | Key is absent from profile file, or a higher-precedence source dominates | Verify key names, Config Data order, and other sources |
| External common file overrides packaged profile file | External Config Data has higher precedence than packaged profiles | Identify exact file paths for every file |
| `SPRING_PROFILES_ACTIVE` is set but does not take effect | Environment variable was not passed into the process/container | Check launch configuration, Compose, or runtime environment |
| `application-prod.yml` placed beside JAR is not found | Working directory is not the JAR's directory | Run from the right directory or use an absolute location |
| Error when putting `spring.profiles.active` in `application-prod.yml` | Profile-selection property cannot live in a profile-specific document | Move it to the common file or startup source |
| Activating `dev,prod` yields different values from `prod,dev` | Profile ordering affects overrides within the same location group | Choose profile order intentionally; avoid unnecessary duplicate keys |
| Configuration list is missing elements after enabling a profile | New list replaces old list during binding | Define the complete list elements in the profile file |
| No profile set, yet receiving values outside the common file | `application-default.yml` or another source exists | Check default profile and all actual Config Data sources |
| Edited YAML, yet running process keeps old values | Config Data is typically loaded at startup, without automatic hot reload | Restart or use an explicitly configured refresh mechanism |

When tracking down the cause of a specific value, verify in order:

1. Which profiles are actually active? Is any default profile being considered?
2. Which `application.*` files were found on the classpath and filesystem?
3. Are `spring.config.location`, `additional-location`, or `import` altering file lookup?
4. Which sources define the key, and which source has the highest precedence?
5. Are any environment variables, Java system properties, CLI arguments, or test configurations overriding it?

If using Spring Boot Actuator, the `env` and `configprops` endpoints can help investigate property sources and values when enabled. Restrict access and mask sensitive information.

## 17. Practice exercises

### Exercise 1 — Overriding keys

Inside the JAR you have:

~~~yaml
# application.yml
server:
  port: 8080
app:
  feature-enabled: false
  message: "common"
~~~

~~~yaml
# application-dev.yml
server:
  port: 8082
app:
  feature-enabled: true
~~~

Run with `--spring.profiles.active=dev`, with no other override sources. What are the three final values?

**Answer:** `server.port=8082`, `app.feature-enabled=true`, and `app.message=common`. The `message` key is retained from the common file because the `dev` file does not redeclare it.

### Exercise 2 — External non-profile-specific file

Given:

~~~text
classpath:/application.yml        → app.mode=common
classpath:/application-prod.yml   → app.mode=packaged-prod
file:./config/application.yml     → app.mode=external-common
~~~

Activate `prod` with no other overrides. What does `app.mode` equal?

**Answer:** `external-common`, because external common Config Data has higher precedence than packaged profile-specific Config Data.

### Exercise 3 — Two active profiles

In the same location:

~~~text
application.yml                → app.color=gray
application-prod.yml           → app.color=blue
application-observability.yml  → app.color=green
~~~

Run sequentially with `prod,observability` and `observability,prod`. Determine the results.

**Answer:** with no other overrides and considering only this location group, the first run yields `green` and the second yields `blue`, because the profile appearing later can override the earlier profile.

### Exercise 4 — No active profile

Both `application.yml` and `application-default.yml` exist, with no `spring.profiles.active` configured. Which files are considered?

**Answer:** both the common file and the file for the default profile `default` can be loaded from appropriate search locations. If the default file overrides the same key, its value beats the common file in the same location group.

### Exercise 5 — Choosing how to organize

A service has a common timeout of `3s` and a production timeout of `12s`. Write two YAML files to avoid repeating unnecessary keys.

**Suggested answer:**

~~~yaml
# application.yml
app:
  client:
    base-url: "https://sandbox.example.org"
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    base-url: "https://api.example.org"
    timeout: 12s
~~~

Both files share the same `app.client` prefix. When `prod` is active, matching keys are overridden; any other shared keys remain intact.

## 18. Key takeaways

- `application.yml` is the **common configuration**; `application-{profile}.yml` is considered by Spring Boot when the corresponding profile is active.
- Profile-specific files **add or override individual properties**; they do not delete the entire contents of the common file.
- You can activate profiles via `--spring.profiles.active=...`, `SPRING_PROFILES_ACTIVE`, or another appropriate configuration source.
- With no active profile, Spring uses the default profile, typically `default`; `application-default.yml` can participate if present.
- Across common Config Data groups: **packaged common → packaged profile-specific → external common → external profile-specific**.
- When multiple profiles are enabled, **profile order** can change the final value; you must also account for location groups and external/packaged precedence.
- `spring.config.activate.on-profile` lets you split multiple profile-specific documents inside one YAML file.
- Sources outside Config Data such as environment variables or CLI arguments can override profile files.
- Declare the complete list in the profile source if you want to override a `List`, rather than assuming elements merge automatically.
- To diagnose issues, verify **running profiles, files actually loaded, and the final source owning the key**.

References:

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)