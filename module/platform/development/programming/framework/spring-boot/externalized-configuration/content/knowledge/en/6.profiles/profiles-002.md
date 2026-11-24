# Activating Profiles with `spring.profiles.active` from Configuration Sources in Spring Boot

## 1. Goals and context

In Spring Boot, **profiles** are a mechanism for selecting components and configuration values suited to the runtime context. An application can use the same build for local, development, test, staging, and production, while each environment needs different HTTP ports, service addresses, connection policies, or component implementations.

The **`spring.profiles.active`** property is the standard way to specify which profiles are active. It can be supplied through multiple sources in the **Externalized Configuration** system: `application.properties` or `application.yml` files, OS environment variables, Java system properties, command-line arguments, and other configuration sources loaded early enough during Spring Boot startup.

Example: an application has a base configuration and two environment-specific files:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
~~~

~~~properties
# application.properties
spring.application.name=order-service
app.client.timeout=5s
~~~

~~~properties
# application-dev.properties
app.client.timeout=2s
~~~

~~~properties
# application-prod.properties
app.client.timeout=10s
~~~

When running with `spring.profiles.active=dev`, Spring Boot can load configuration for `dev`, so `app.client.timeout` receives `2s` unless overridden by a higher-precedence source. When running with `prod`, the value will be `10s` under the same conditions. When neither `dev` nor `prod` is activated, the default value in the base file is `5s`, unless a default profile or another override applies.

Key takeaway: `spring.profiles.active` **selects profiles**, whereas `application-{profile}.properties`, `@Profile`, and `spring.config.activate.on-profile` **consume those profiles** to decide which configuration or beans take effect. These two responsibilities happen at different layers.

## 2. What is a profile and what does Spring Boot use active profiles for?

### 2.1. The active profile concept

Spring Framework provides `Environment` and the profile mechanism. Spring Boot builds on that to apply environment-specific configuration at startup.

Profiles can have names such as:

- `dev`: running on a developer machine with mock services or lightweight configuration.
- `test`: running integration tests with a dedicated database or test data.
- `staging`: a production-like environment for verification before release.
- `prod`: the environment serving real traffic.
- `cloud` or `docker`: an infrastructure characteristic rather than a development stage.

Profile names carry no special intrinsic meaning to Spring. The `prod` profile does not automatically make an application safer or faster; only the files, beans, and configuration conditions attached to `prod` create different behavior.

**Multiple profiles can be active simultaneously**, such as `dev,cloud`. When profile-specific configuration files define overlapping keys, profile order and source locations affect the final value.

### 2.2. Profiles control both beans and configuration values

Example creating different beans per profile:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class PaymentClientConfiguration {

    @Bean
    @Profile("dev")
    PaymentClient fakePaymentClient() {
        return new FakePaymentClient();
    }

    @Bean
    @Profile("prod")
    PaymentClient realPaymentClient() {
        return new RealPaymentClient();
    }
}
~~~

This is an illustrative model only: `PaymentClient`, `FakePaymentClient`, and `RealPaymentClient` must be defined in the project. In real designs, you should clearly decide what happens when neither profile is active or when both are active; if both beans of the same type are created, explicit conditions or another bean-selection strategy may be needed.

The same active profiles are also used by Spring Boot to look up files like `application-dev.yml`, `application-prod.properties`, and conditionally activated documents. Therefore, changing `spring.profiles.active` can affect **both** configuration and initialized components simultaneously.

## 3. Declaring profiles in `application.properties`

Basic approach:

~~~properties
# application.properties
spring.profiles.active=dev

spring.application.name=order-service
app.client.timeout=5s
~~~

When the application starts without a higher-precedence source declaring `spring.profiles.active`, the `dev` profile becomes active. Spring Boot will consider files for `dev` and `@Profile("dev")` conditions.

**Note:** if you package `spring.profiles.active=dev` inside the JAR, every environment will default to `dev` unless overridden. This is convenient for experimental projects but poorly suited for a shared artifact deployed across multiple environments. In real deployment setups, base configuration is usually kept profile-free, or profiles are specified by the runtime environment.

You can declare a list of multiple profiles:

~~~properties
spring.profiles.active=dev,cloud
~~~

This requests activating both `dev` and `cloud`. Listing multiple names in a single property differs from creating multiple `spring.profiles.active` entries in the same file; keep one clear declaration to avoid ambiguity.

### 3.1. How are profile-specific files loaded?

Suppose:

~~~properties
# application.properties
app.endpoint=https://api.example.test
app.timeout=5s
~~~

~~~properties
# application-dev.properties
app.endpoint=http://localhost:8081
app.timeout=1s
~~~

~~~properties
# application-prod.properties
app.timeout=12s
~~~

If `dev` is activated, the corresponding values are:

~~~text
app.endpoint = http://localhost:8081
app.timeout  = 1s
~~~

If `prod` is activated, the values are:

~~~text
app.endpoint = https://api.example.test
app.timeout  = 12s
~~~

`app.endpoint` keeps the base value in `prod` mode because `application-prod.properties` does not redeclare that key. Profile-specific files **supplement and can override** values without requiring every property to be repeated.

This example assumes the files are in the same standard location set, with no external sources, environment variables, or command-line properties of higher precedence.

## 4. Declaring profiles in `application.yml`

YAML represents the same property as a nested structure:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev

app:
  client:
    timeout: 5s
~~~

The configuration above is equivalent to `spring.profiles.active=dev` in `application.properties`.

To activate multiple profiles, you can write:

~~~yaml
spring:
  profiles:
    active: dev,cloud
~~~

A maintainable structure keeps `application.yml` containing only shared values, while `application-dev.yml` and `application-prod.yml` hold differences. Selecting the profile at deployment time can be done with environment variables or launch arguments.

### 4.1. Multi-document YAML and `spring.config.activate.on-profile`

A YAML file can contain multiple documents separated by `---`. Spring Boot allows activating individual documents based on a profile that **has already been selected**:

~~~yaml
# application.yml: common configuration
app:
  display-name: Order Service
  client:
    timeout: 5s
---
spring:
  config:
    activate:
      on-profile: dev

app:
  client:
    timeout: 2s
---
spring:
  config:
    activate:
      on-profile: prod

app:
  client:
    timeout: 10s
~~~

When `dev` is active, the corresponding document can override `app.client.timeout` to `2s`. With `prod`, the value can become `10s`.

Distinguish between:

- `spring.profiles.active`: **selects** active profiles.
- `spring.config.activate.on-profile`: **condition for loading a document** based on already-selected profiles.
- `@Profile("dev")`: **bean registration condition**.
- `application-dev.yml`: **configuration file named after a profile**.

In modern Spring Boot, **do not place `spring.profiles.active` inside a document activated by `spring.config.activate.on-profile`**. That is a circular configuration: the document needs profiles to decide whether it loads, yet tries to change profiles after being selected.

## 5. Activating profiles with environment variables

This is one of the best-suited methods when you want to keep the JAR unchanged and vary only deployment configuration.

The environment variable name corresponding to `spring.profiles.active` is:

~~~text
SPRING_PROFILES_ACTIVE
~~~

Spring Boot supports mapping between property names and environment variable names under its configuration rules. With this key, you can supply `SPRING_PROFILES_ACTIVE=prod` without editing `application.properties`.

### 5.1. Linux or macOS

In a POSIX shell:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar order-service.jar
~~~

Or pass it for a single run:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

To activate multiple profiles:

~~~bash
export SPRING_PROFILES_ACTIVE=prod,cloud
java -jar order-service.jar
~~~

The environment variable value is a comma-separated string of profile names. Using an explicit string makes deployment scripts easy to inspect.

### 5.2. Windows PowerShell

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar order-service.jar
~~~

This command sets the environment variable for the current PowerShell process and child processes launched from it. It does not modify `application.properties` inside the JAR.

You can remove the variable in the PowerShell session when no longer needed:

~~~powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE
~~~

### 5.3. Windows Command Prompt

~~~bat
set SPRING_PROFILES_ACTIVE=dev
java -jar order-service.jar
~~~

The value applies to the corresponding `cmd.exe` session and child processes. The `set` syntax differs from PowerShell, so avoid mixing commands across the two shells.

### 5.4. Docker Compose

You can supply active profiles from container configuration:

~~~yaml
services:
  order-service:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: prod
~~~

The container runs the same image, while Spring Boot receives the `prod` profile from the environment variable. When using multiple profiles:

~~~yaml
services:
  order-service:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: "prod,cloud"
~~~

There is no need to build a separate image just to hardcode `spring.profiles.active` per environment.

### 5.5. Kubernetes

In a Pod or Deployment, configure the environment variable on the container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: example/order-service:1.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod,cloud"
~~~

This illustrates supplying profiles through the environment. In practice, ConfigMaps, deployment systems, or manifest management tools can manage the value. Profiles do not replace authorization policies, secret protection, or infrastructure controls.

## 6. Activating with Java system properties

Java allows setting system properties with the `-D` JVM option:

~~~bash
java -Dspring.profiles.active=prod -jar order-service.jar
~~~

The `-Dspring.profiles.active=prod` option sits **before** `-jar` because it is an argument for the Java launcher. If placed after `-jar`, it is typically passed to the program as an application argument and no longer acts as a Java system property setting.

Multiple profiles:

~~~bash
java -Dspring.profiles.active=prod,cloud -jar order-service.jar
~~~

A Java process can include other configuration system properties:

~~~bash
java \
  -Dspring.profiles.active=prod \
  -Dserver.port=9090 \
  -jar order-service.jar
~~~

This is useful when an application runner provides a dedicated place for JVM options. No files inside the JAR need editing.

**Distinguishing the three input forms:**

| Method | Example | Where is it placed? |
| --- | --- | --- |
| Environment variable | `SPRING_PROFILES_ACTIVE=prod` | Operating system environment |
| Java system property | `-Dspring.profiles.active=prod` | Java system properties |
| Command-line argument | `--spring.profiles.active=prod` | Spring Boot application arguments |

They can express the same intent, yet belong to different `PropertySource`s and can have different precedence.

## 7. Activating with Spring Boot command-line arguments

The startup argument `--spring.profiles.active=...` is a direct way to specify profiles:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Running production:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Multiple profiles:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,cloud
~~~

By default, Spring Boot adds `--key=value` application arguments to `Environment`. Command-line arguments typically take high precedence over configuration files, environment variables, and Java system properties.

Example:

~~~properties
# application.properties
spring.profiles.active=dev
~~~

But running:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

In a default Spring Boot setup, the effective profile from this property is `prod`; `dev` in the file is not automatically appended.

`SpringApplication` can be configured not to add command-line properties to `Environment` (for example `setAddCommandLineProperties(false)`). When doing so, you cannot assume the `--spring.profiles.active` argument precedence described above. Examples here assume standard Spring Boot startup behavior.

### 7.1. Passing arguments when running via Maven or Gradle

When running from a build tool, profiles are typically passed via the corresponding plugin configuration or application arguments. For example, with the Spring Boot Maven Plugin:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
~~~

This is a **Maven plugin parameter**, not directly the `spring.profiles.active` Java system property. The plugin uses that setting to configure profiles for the application at launch. Exact syntax can vary by tool and plugin version.

With Gradle, a common approach is configuring `bootRun` to pass application arguments:

~~~groovy
// build.gradle
tasks.named('bootRun') {
    args '--spring.profiles.active=dev'
}
~~~

Avoid hardcoding development profiles in build scripts used for production packaging unless intentionally required by the project.

## 8. Precedence rules when multiple sources set `spring.profiles.active`

Externalized Configuration allows the same key to appear in multiple sources. `spring.profiles.active` also follows property source precedence rules.

Consider the example:

~~~properties
# application.properties
spring.profiles.active=dev
~~~

OS environment:

~~~bash
export SPRING_PROFILES_ACTIVE=staging
~~~

And the startup command:

~~~bash
java -Dspring.profiles.active=test \
  -jar order-service.jar \
  --spring.profiles.active=prod
~~~

In standard Spring Boot, `--spring.profiles.active=prod` has higher precedence than Java system properties, environment variables, and config files; the profile selected via `spring.profiles.active` will be `prod`.

A commonly remembered subset of order, from lower to higher precedence, is:

~~~text
application.properties / application.yml
                ↓
OS environment variables
                ↓
Java system properties
                ↓
Spring Boot command-line arguments
~~~

This is a **simplified slice of source ordering**, not a complete table: Spring Boot also includes external Config Data, `SPRING_APPLICATION_JSON`, test framework sources, other sources, and startup customization hooks. The Config Data documentation details precedence rules across external files, classpath files, and profile-specific files. When two sources overlap, always inspect **the full actual order**.

### 8.1. The entire profile list is replaced, not automatically merged with lower sources

Suppose:

~~~properties
# application.properties
spring.profiles.active=dev,metrics
~~~

And environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

The `spring.profiles.active` value from the higher-precedence source is `prod`. Spring Boot does not automatically merge lists into `dev,metrics,prod` just because a lower source declared multiple profiles.

This differs from **`spring.profiles.include`** and **profile groups**, which exist to append or group related profiles.

### 8.2. A profile can come from multiple mechanisms

When inspecting active profiles, you may sometimes notice more profiles than appear in the final `spring.profiles.active` list. Reasons can include:

- `spring.profiles.include` adds profiles.
- `spring.profiles.group.<name>` expands a group profile.
- Code uses `SpringApplication.setAdditionalProfiles(...)`.
- The test framework uses `@ActiveProfiles` or supplies profiles while building the context.
- An application extension modifies `Environment` during preparation.

Therefore, **“the effective property value”** and **“the final active profiles set in Environment”** are related pieces of information that do not always match identically.

## 9. Multi-profile configuration and override order

### 9.1. Declaring multiple profiles

~~~bash
java -jar order-service.jar --spring.profiles.active=dev,cloud
~~~

Spring Boot considers both profiles. If the files are:

~~~properties
# application.properties
app.client.timeout=5s
~~~

~~~properties
# application-dev.properties
app.client.timeout=2s
~~~

~~~properties
# application-cloud.properties
app.client.timeout=8s
~~~

In this simple example where files reside in the same location group and no higher-precedence source exists, **a profile appearing later can override a profile appearing earlier**, so `app.client.timeout` can be `8s`.

If changed to:

~~~bash
java -jar order-service.jar --spring.profiles.active=cloud,dev
~~~

the value can become `2s` under the same conditions. That is the **last wins** rule when resolving profile-specific properties at the same location tier.

### 9.2. File locations also have precedence

Profile order is not the only factor. Spring Boot can read files from:

~~~text
classpath:/application.properties
classpath:/config/application.properties
file:./application.properties
file:./config/application.properties
file:./config/*/application.properties
~~~

Locations are ordered according to Config Data precedence order/groups. An external file with higher precedence can override values from a profile-specific file inside the JAR.

With `spring.config.location` or `spring.config.additional-location`, grouping locations with `,` and `;` can also affect results when multiple profiles are active. When explaining the final value, combine property source order, location groups, and profile order.

### 9.3. Do not treat profiles as whole-file merging

When `application.properties` and `application-prod.properties` both exist, Spring Boot does not simply pick one file and discard the other. All property sources can contribute values; any key not overridden can remain from the base source.

Conversely, some list-valued properties have distinct binding rules and do not necessarily merge elements across sources. For `spring.profiles.active`, the higher-precedence source decides the declared list for that property.

## 10. Differences among `spring.profiles.active`, `default`, and `include`

### 10.1. `spring.profiles.default`

Spring Framework has the concept of a **default profile** used when no active profile is explicitly set. In Spring Boot, the usual default profile name is `default`. You can configure:

~~~properties
spring.profiles.default=local
~~~

If no active profile is specified through appropriate mechanisms, `local` becomes the applied default profile. This can allow `application-local.properties` to participate in Config Data.

If `prod` is already activated, the default profile does not replace `prod`.

When you want to avoid using the `default` profile:

~~~properties
spring.profiles.default=none
~~~

This is a configuration supported by Spring Boot to disable the conventional `default` profile; do not create an `application-none.properties` file and treat `none` as a production environment.

### 10.2. `spring.profiles.include`

When a primary profile needs to be accompanied by auxiliary profiles, you can use:

~~~properties
spring.profiles.active=prod
spring.profiles.include=metrics
~~~

Goal: add the `metrics` profile alongside `prod`. Typically, include is used when multiple environments need the same shared components.

Note: `spring.profiles.include` is processed under its own per-`PropertySource` rules rather than simply being replaced like the entire `spring.profiles.active` string. This matters in setups with multiple locations.

### 10.3. Profile groups

Another option is defining profile groups:

~~~properties
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

Then run:

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

The `production` group expands to activate the additional profiles `proddb` and `prodmq`. This lets operators use a short name while individual sub-profiles control specific configuration or beans.

In YAML, a readable syntax is:

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

Both `spring.profiles.include` and `spring.profiles.group.*` definitions must be placed in **non-profile-specific documents** per modern Spring Boot Config Data rules.

## 11. Where NOT to place `spring.profiles.active`

This is an important constraint to remember when using Spring Boot Config Data.

**`spring.profiles.active` and `spring.profiles.default` may only be placed in non-profile-specific documents.** Do not place these properties in:

1. Profile-specific files such as `application-prod.properties`.
2. YAML documents that already have `spring.config.activate.on-profile=prod`.

Incorrect example:

~~~properties
# application-prod.properties — INVALID
spring.profiles.active=prod,cloud
~~~

Similar incorrect example in YAML:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: cloud
~~~

Modern Spring Boot can fail with an error such as `InvalidConfigDataPropertyException` when encountering such configuration. Reason: Boot needs to know active profiles **before** deciding which profile-specific content to load. A conditionally loaded file cannot use this mechanism to alter file-selection conditions mid-way.

**Correct fix:** move profile selection to a non-profile-specific source, for example:

~~~properties
# application.properties
spring.profiles.active=prod,cloud
~~~

Or supply it via environment variables / launch arguments:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,cloud
~~~

If the goal is for `cloud` to always accompany `prod`, consider defining `spring.profiles.group.prod` in a non-profile-specific document.

Similarly, do not place `spring.profiles.include` or `spring.profiles.group` definitions inside profile-specific files or documents with `spring.config.activate.on-profile`.

## 12. Selecting active profiles from Java code

Beyond external properties, Spring Boot provides a programmatic startup API. This mechanism differs from declaring `spring.profiles.active` directly.

Example adding a profile via `SpringApplication`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(OrderApplication.class);
        application.setAdditionalProfiles("local");
        application.run(args);
    }
}
~~~

`setAdditionalProfiles("local")` is used to **add** a profile for this launch. It can coexist with profiles selected via external configuration. Do not assume this API is strictly identical to setting the `spring.profiles.active` property in a specific source.

Spring Framework also provides `ConfigurableEnvironment.setActiveProfiles(...)`, though intervening manually in the environment must occur early enough to align with Config Data loading order. Changing profiles after the application context has already created beans will not automatically rebuild beans or reload all profile-specific configuration files.

**Recommendation:** let the deployment environment choose profiles unless there is a special requirement. If you enforce profiles in Java code, be aware that application behavior may become harder to change through external configuration alone.

## 13. Active profiles in Spring Boot tests

For integration tests, you can use the Spring Test annotation:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTests {

    @Test
    void contextLoads() {
    }
}
~~~

The `@ActiveProfiles("test")` annotation tells the Spring TestContext Framework which profiles should be active when creating the test context. When the project has `application-test.properties`, settings for the `test` profile can be applied.

Example:

~~~properties
# src/test/resources/application-test.properties
app.payment.mode=fake
app.client.timeout=500ms
~~~

This makes the test environment explicit and reduces dependence on CI machine environment variables.

Distinguish `@ActiveProfiles` from putting `spring.profiles.active` inside `application-test.properties`: `application-test.properties` is already a profile-specific file and must not be used to activate more profiles via `spring.profiles.active`. When additional profiles are needed, configure them in a non-profile-specific location or via appropriate test mechanisms.

## 14. A consistent deployment workflow

Suppose a project has the following files:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
~~~

Common configuration:

~~~yaml
# application.yml
spring:
  application:
    name: order-service

app:
  client:
    timeout: 5s
  feature:
    demo-mode: false
~~~

Development environment:

~~~yaml
# application-dev.yml
app:
  client:
    timeout: 2s
  feature:
    demo-mode: true
~~~

Staging environment:

~~~yaml
# application-staging.yml
app:
  client:
    timeout: 4s
~~~

Production environment:

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 10s
~~~

Running on a development machine:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Running in staging:

~~~bash
SPRING_PROFILES_ACTIVE=staging java -jar order-service.jar
~~~

Running in production via Java system property:

~~~bash
java -Dspring.profiles.active=prod -jar order-service.jar
~~~

Expected results assuming no other property sources override them:

| Environment | Active profile | `app.client.timeout` | `app.feature.demo-mode` |
| --- | --- | --- | --- |
| Development | `dev` | `2s` | `true` |
| Staging | `staging` | `4s` | `false` |
| Production | `prod` | `10s` | `false` |

The build and Java code do not need to change across the three environments. All differences are expressed through configuration and the profile selected at startup.

For secrets such as database passwords, API keys, or private keys, do not rely solely on profiles for protection. They must be injected from an appropriate secret source; profiles only select the **configuration set** and applicable beans.

## 15. Observing active profiles inside the application

### 15.1. Reading via `Environment`

Spring Framework provides `Environment.getActiveProfiles()`:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfileInspector {
    private final Environment environment;

    public ActiveProfileInspector(Environment environment) {
        this.environment = environment;
    }

    public String[] activeProfiles() {
        return environment.getActiveProfiles();
    }

    public String describe() {
        return "Active profiles: " + Arrays.toString(activeProfiles());
    }
}
~~~

The result can be `[prod]` or `[prod, cloud]`, depending on startup options and profile-addition mechanisms. If no active profiles are set, `getActiveProfiles()` can return an empty array even when Spring uses a **default profile**; to inspect default profiles, call `getDefaultProfiles()`.

### 15.2. Reading the property vs. the active list separately

The following two reads are not equivalent in all cases:

~~~java
String rawActive = environment.getProperty("spring.profiles.active");
String[] activeProfiles = environment.getActiveProfiles();
~~~

`rawActive` shows the `spring.profiles.active` value resolved from property sources; `activeProfiles` shows the set of profiles the environment considers active, which may include profiles added via include, groups, or startup APIs.

When investigating issues, check **both** if you suspect profiles were added through mechanisms outside the property value.

### 15.3. Startup logs

Spring Boot typically logs a message about active profiles during application startup. The exact message and level of detail depend on the version and logging configuration.

If you need to diagnose loaded files and profile conditions, you can enable verbose logging for the Config Data package:

~~~bash
java -jar order-service.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

This log level is meant for investigation in appropriate environments. Avoid enabling broad verbose logging in production unnecessarily, and do not log sensitive properties.

## 16. Common mistakes

### 16.1. Placing `spring.profiles.active` in `application-prod.properties`

**Wrong:**

~~~properties
# application-prod.properties
spring.profiles.active=prod
~~~

This file requires the `prod` profile to be selected, so it cannot be used to select that profile itself. Place the property in a non-profile-specific `application.properties` or pass it via the runtime environment.

### 16.2. Thinking `application-prod.yml` automatically activates `prod`

Merely placing `application-prod.yml` in the JAR is not enough to make `prod` active. You must declare the profile in an appropriate source, for example:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Or have another mechanism activate `prod` beforehand.

### 16.3. Being overridden by a higher-precedence source unknowingly

~~~properties
# application.properties
spring.profiles.active=dev
~~~

If the process has `SPRING_PROFILES_ACTIVE=prod`, the result will typically be `prod`. Check environment variables, JVM options, and command-line arguments before concluding that the configuration file was not read.

### 16.4. Activating multiple profiles and hitting overlapping keys

~~~bash
java -jar order-service.jar --spring.profiles.active=dev,prod
~~~

When two profiles declare the same key, the result depends on profile order and location groups. Do not enable both `dev` and `prod` if those profiles are designed to be mutually exclusive and have conflicting beans.

### 16.5. Confusing `spring.profiles.default` with `spring.profiles.active`

`spring.profiles.default` only matters when there is no explicit active profile. Setting the default profile to `local` does not mean `local` always stays active alongside `prod`.

### 16.6. Using the wrong environment variable name

For the `spring.profiles.active` property, the standard environment variable name is `SPRING_PROFILES_ACTIVE`. Setting `SPRING_PROFILE_ACTIVE` (missing the `S` in `PROFILES`) does not match the intended property.

### 16.7. Changing environment variables after the application has started

Spring Boot handles profile selection and Config Data loading at startup. Changing `SPRING_PROFILES_ACTIVE` in another terminal while the process is running does not cause the context to reload profile-specific beans or files. Usually you must restart the application, or use a dedicated dynamic configuration mechanism.

### 16.8. Using `@PropertySource` to select profiles too late

Spring Framework's `@PropertySource` is processed while the application context is being built. Decisions related to Config Data and some startup features occur earlier. Therefore, do not rely on `@PropertySource` to provide `spring.profiles.active` for selecting `application-{profile}.*` files. Use one of the startup sources supported by Boot to select profiles from the start.

### 16.9. Treating profiles as a security boundary

Using `@Profile("prod")` does not replace access control, configuration secrets, or authentication. A profile name is a configuration flag; anyone with permission to change environment variables or launch arguments can change the selected profile set. Real security measures must be enforced at the infrastructure and application layers.

## 17. Checklist for diagnosing a profile not working as expected

When a `@Profile("prod")` bean is not created or `application-prod.yml` seems to have no effect, check in order:

1. **Where is the profile activated?** Check non-profile-specific files, environment variables, Java system properties, command line, test configuration, and startup APIs.
2. **Are the property name and profile name exact?** Use `spring.profiles.active` / `SPRING_PROFILES_ACTIVE`; the profile name `prod` must match `@Profile("prod")` and `application-prod.yml`.
3. **Which source has the highest precedence?** If a file declares `dev` while the command line declares `prod`, explain it using source precedence rather than reading only the file.
4. **Are there include/group/additional profile mechanisms?** These can add profiles not visible in the property string.
5. **Is any configuration placed in an invalid location?** `spring.profiles.active` inside a profile-specific file or a document with `spring.config.activate.on-profile` is invalid in modern Config Data.
6. **Are the file path and name exact?** `application-prod.yml` must reside in a location Spring Boot searches; `spring.config.location` and `spring.config.additional-location` can change the search locations.
7. **Do multiple profiles override the same key?** Check profile order and location groups.
8. **Are there duplicate or missing beans when profiles change?** Inspect `@Profile`, bean creation conditions, and dependency injection.
9. **Was the process restarted after changing configuration?** Profiles do not normally update dynamically inside a running context.
10. **What are the actual effective values?** Inspect `Environment.getActiveProfiles()`, `getDefaultProfiles()`, and the property in question; if appropriate Actuator endpoints are available, check config sources with sensitive data masked.

In environments with Spring Boot Actuator and appropriate access control, the `/actuator/env` endpoint can help diagnose property sources. Do not expose configuration endpoints to the public Internet just to view profiles, and do not leak secrets when enabling debugging tools.

## 18. Deployment checklist

| Question | Recommended approach |
| --- | --- |
| Does the application use the same JAR across environments? | Keep common files in the JAR, pass `spring.profiles.active` via the runtime environment |
| How is the local run profile selected? | `--spring.profiles.active=dev` or `SPRING_PROFILES_ACTIVE=dev` |
| How is the production profile selected? | Environment variable, JVM option, or command-line argument from the deployment system |
| Are multiple profiles active together? | Separate with commas; check ordering and overlapping keys |
| Are there auxiliary profiles that must always accompany runs? | Look at `spring.profiles.include` or profile groups in non-profile-specific documents |
| Want to default to local config when no active profile is chosen? | Consider `spring.profiles.default=local` |
| Getting an error declaring profiles inside a profile-specific file? | Move `spring.profiles.active` to a non-profile-specific source |
| Profile-specific file not being loaded? | Check profile name, location, working directory, and Config Data order |
| Unexpected profiles present at runtime? | Compare `Environment.getActiveProfiles()` with properties and include/group mechanisms |
| Changed profile but application behavior didn't change? | Verify restart occurred and check which beans/properties actually depend on the profile |

## 19. Conclusion

**`spring.profiles.active` is the key for selecting active profiles in Spring Boot**, and can be supplied via non-profile-specific configuration files, the `SPRING_PROFILES_ACTIVE` environment variable, the `-Dspring.profiles.active` Java system property, or the `--spring.profiles.active` command-line argument. When multiple sources declare it, Spring Boot applies Externalized Configuration precedence order.

Selecting profiles is only the first step: Boot then uses those profiles to load `application-{profile}.*` files and documents with `spring.config.activate.on-profile`, while Spring Framework uses them to control `@Profile` beans. With multiple profiles, pay attention to ordering, location groups, and include/group mechanisms. Never place `spring.profiles.active` inside the very file or document that already requires that profile to load.

An easy-to-operate design is to **keep common configuration in the artifact, place differences in profile-specific files, and select profiles via the deployment environment's configuration sources**. That approach lets you switch environments without modifying source code or rebuilding the JAR.

### References

- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)