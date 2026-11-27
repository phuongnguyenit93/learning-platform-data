# Experimenting with One Property Across Multiple Sources

In a Spring Boot application, the same property can be declared in multiple places: `application.yml`, profile-specific files, external configuration files outside the JAR, host/container environment variables, Java system properties, command-line arguments, or Config Server. When those values differ, which one will the application use?

Spring Boot registers configuration sources in `Environment` in a defined precedence order. A higher-precedence source can override a value from a lower-precedence source. Understanding this order helps development teams explain why an application is running with a different value than the one visible in the repository.

This lesson belongs to the **Configuration Loading** chapter of the **SPRING_CLOUD_CORE** module. We will use a non-sensitive property, `app.banner`, assign different values across sources, launch the application multiple times, and observe which value wins. After the experiment, the lesson extends to profiles, `spring.config.import`, Spring Cloud Config Client, and runtime refresh.

## 1. Learning Objectives

After this lesson, you can:

- Explain the concepts of `PropertySource`, `Environment`, and the rule that higher-precedence sources override lower-precedence ones.
- Distinguish overall precedence across configuration source groups from file discovery ordering inside Config Data.
- Experiment with a key appearing in classpath files, profile files, external files outside the JAR, environment variables, system properties, and command-line arguments.
- Read values via `Environment` or `@ConfigurationProperties` and inspect which source supplied the value.
- Use `spring.config.import`, `spring.config.additional-location`, and profiles for their intended purposes.
- Distinguish selecting values at startup from refreshing configuration while the application is running.
- Identify common reasons why a configuration value gets overridden unexpectedly.

## 2. Core Concepts to Know

### 2.1. Property and PropertySource

A **property** is a name-value pair, for example:

~~~properties
app.banner=Hello from application
~~~

A **PropertySource** is a source supplying properties to Spring `Environment`. YAML files, `.properties` files, environment variables, Java system properties, and command-line arguments can each be represented as separate sources.

`Environment` aggregates these sources. When calling `environment.getProperty("app.banner")`, Spring searches properties in precedence order and returns the first value found. If the same key appears in multiple sources, the value from the higher-precedence source is used.

~~~mermaid
flowchart TD
    A[application.yml] --> E[Spring Environment]
    B[application-lab.yml] --> E
    C[External config files] --> E
    D[OS environment variables] --> E
    F[Java system properties] --> E
    G[Command-line arguments] --> E
    E --> R[Resolve app.banner]
    R --> V[Effective value]
    V --> BIND[@ConfigurationProperties / @Value]
~~~

This diagram shows sources contributing together into `Environment`. When a key collides, precedence order determines the effective value.

### 2.2. Default value, override value, and effective value

- **Default value:** a value set so the application can run when the environment has not supplied a dedicated override.
- **Override value:** a value from a higher-precedence source used in place of a lower-precedence source's value.
- **Effective value:** the result the application actually reads from `Environment` at query time.

Example:

| Source | `app.banner` Value |
| --- | --- |
| `application.yml` inside JAR | `classpath-default` |
| `application-lab.yml` inside JAR | `profile-lab` |
| `./config/application.yml` | `external-default` |
| `./config/application-lab.yml` | `external-profile` |
| Environment variable `APP_BANNER` | `from-env` |
| Java system property `-Dapp.banner` | `from-system` |
| Argument `--app.banner` | `from-cli` |

Not all sources live on the same tier. First Spring Boot orders files belonging to Config Data; then Config Data itself sits within the overall precedence order alongside other sources.

## 3. PropertySource Precedence Order

Current Spring Boot documentation describes order from lowest to highest precedence. A source appearing later in the list can override an earlier source. The table below follows Spring Boot **3.5.x and 4.1.x** documentation; if your project uses a different Boot line, consult that exact version before drawing conclusions about fine-grained ordering.

| Order low → high | Source | Example |
| ---: | --- | --- |
| 1 | Default properties | `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` on `@Configuration` classes | File declared via annotation |
| 3 | Config Data | `application.yml`, profile files, external files outside JAR, imported files |
| 4 | `RandomValuePropertySource` | `random.*` keys |
| 5 | OS environment variables | `APP_BANNER=from-env` |
| 6 | Java System properties | `-Dapp.banner=from-system` |
| 7 | JNDI attributes | `java:comp/env/...` |
| 8 | `ServletContext` init parameters | Servlet context initialization parameters |
| 9 | `ServletConfig` init parameters | Servlet initialization parameters |
| 10 | `SPRING_APPLICATION_JSON` | Inline JSON in environment variable or system property |
| 11 | Command-line arguments | `--app.banner=from-cli` |
| 12 | `properties` on `@SpringBootTest` or test slices | `@SpringBootTest(properties = "...")` |
| 13 | `@DynamicPropertySource` | Dynamic properties in tests |
| 14 | `@TestPropertySource` | Property source declared on test |
| 15 | Devtools global settings | Devtools config in user home directory when Devtools is active |

Sources such as JNDI and Servlet init parameters only apply to their corresponding deployment styles. In a standalone Spring Boot application, experiments typically focus on Config Data, environment variables, system properties, and command line.

### 3.1. Two easy-to-confuse points

**Environment variables and Java system properties are two distinct sources.** Under the Spring Boot 3.5.x/4.1.x order above, Java system properties take higher precedence than OS environment variables. Therefore, if both `APP_BANNER=from-env` and `-Dapp.banner=from-system` are present, the effective value is `from-system`.

**Command-line arguments take higher precedence than ordinary configuration sources.** When running:

~~~bash
java -jar app.jar --app.banner=from-cli
~~~

the value `from-cli` overrides values from configuration files, environment variables, and system properties for the same key. Adding command-line properties to `Environment` can be disabled with `SpringApplication.setAddCommandLineProperties(false)`, though normal applications keep the default.

### 3.2. Ordering inside Config Data is a separate layer

For configuration files, Spring Boot evaluates groups in the following order, from lowest to highest:

1. `application.properties` or YAML packaged inside the JAR.
2. Profile-specific files packaged inside the JAR, such as `application-lab.yml`.
3. `application.properties` or YAML outside the JAR.
4. Profile-specific files outside the JAR.

Consequently, `./config/application-lab.yml` can override `application.yml` inside the JAR. Once Config Data resolves, higher-precedence sources such as environment variables, system properties, and command-line arguments can still override values from files.

Within the same directory, if both `application.properties` and `application.yml` exist, Spring Boot prioritizes `.properties`. To avoid confusion, standardize on one configuration format in a given location.

## 4. Preparing the `app.banner` Experiment

The experiment uses a Spring Boot application with an `ApplicationRunner` to print the effective value. No real Config Server is needed in the initial steps; the goal is to observe how Spring Boot resolves multiple local and runtime sources.

### 4.1. File structure

Create the following files:

~~~text
config-precedence-demo/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/configdemo/
│       │       ├── ConfigDemoApplication.java
│       │       ├── AppProperties.java
│       │       └── ConfigReportRunner.java
│       └── resources/
│           ├── application.yml
│           └── application-lab.yml
├── config/
│   ├── application.yml
│   └── application-lab.yml
└── pom.xml
~~~

The `config/` folder sits next to where the application is launched. When using Maven `spring-boot:run`, execute the command from the project root directory so `./config/` is discovered. When running the JAR, place `config/` beside the JAR and set the working directory to that folder.

### 4.2. Declaring values in classpath files

`src/main/resources/application.yml`:

~~~yaml
app:
  banner: "classpath-default"
~~~

`src/main/resources/application-lab.yml`:

~~~yaml
app:
  banner: "classpath-profile-lab"
~~~

The second file loads only when the `lab` profile is active.

### 4.3. Declaring values in external files outside the JAR

`config/application.yml`:

~~~yaml
app:
  banner: "external-default"
~~~

`config/application-lab.yml`:

~~~yaml
app:
  banner: "external-profile-lab"
~~~

These files sit in default external configuration locations. They do not need to be packaged inside the JAR. When running from the directory containing `config/`, Spring Boot finds them automatically under external application properties rules.

## 5. Reading the Effective Value in the Application

The same property can be accessed in several ways. In this experiment, we use `@ConfigurationProperties` for structured binding and `Environment` to inspect resolved values.

### 5.1. Configuration properties class

`AppProperties.java`:

~~~java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String banner = "code-default";

    public String getBanner() {
        return banner;
    }

    public void setBanner(String banner) {
        this.banner = banner;
    }
}
~~~

`code-default` is the initial Java default value. If `app.banner` is found in `Environment`, the binder injects the configured value into the bean.

### 5.2. Application class

`ConfigDemoApplication.java`:

~~~java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` discovers `@ConfigurationProperties` classes in the application's package and subpackages.

### 5.3. Printing the value and sources containing the key

`ConfigReportRunner.java`:

~~~java
package com.example.configdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class ConfigReportRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ConfigReportRunner.class);

    private final ConfigurableEnvironment environment;
    private final AppProperties appProperties;

    public ConfigReportRunner(
            ConfigurableEnvironment environment,
            AppProperties appProperties) {
        this.environment = environment;
        this.appProperties = appProperties;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Effective app.banner from Environment: {}",
                environment.getProperty("app.banner"));
        log.info("Bound app.banner from AppProperties: {}",
                appProperties.getBanner());
        log.info("Active profiles: {}",
                String.join(",", environment.getActiveProfiles()));

        log.info("Property sources containing app.banner (high priority first):");
        for (PropertySource<?> source : environment.getPropertySources()) {
            Object candidate = source.getProperty("app.banner");
            if (candidate != null) {
                log.info("  {} -> {}", source.getName(), candidate);
            }
        }
    }
}
~~~

The loop reveals multiple sources holding the key. `Environment.getProperty()` returns the value according to precedence order; `PropertySource` entries are traversed in `Environment` precedence order, so the first source containing the key is the winner during standard resolution.

This is diagnostic code for an illustrative property, not a template for logging all production configuration. Never log passwords, tokens, connection strings, or all property sources in real environments.

## 6. Running the Experiment Step by Step

### 6.1. Step 1 — Default configuration only

Run the application from the project root directory:

To observe the two classpath files alone in Steps 1 and 2, temporarily rename or move the external `config/` directory outside the JAR. Restore that directory before Step 3 to observe external file precedence.

~~~bash
./mvnw spring-boot:run
~~~

The `lab` profile is not active yet, and there are no overrides from environment, system properties, or command line. Without external files outside the JAR, the result is `classpath-default`.

If the external file `config/application.yml` already exists as structured above, the result will be `external-default`, because external files take higher precedence than classpath files.

### 6.2. Step 2 — Activate the `lab` profile

Run:

~~~bash
./mvnw -Dspring-boot.run.arguments="--spring.profiles.active=lab" spring-boot:run
~~~

Or run the JAR:

~~~bash
java -jar target/config-precedence-demo.jar --spring.profiles.active=lab
~~~

The result is `external-profile-lab` when all four example files exist. Profile-specific files outside the JAR take higher precedence than profile-specific files inside the JAR and non-profile files.

### 6.3. Step 3 — Add an environment variable

On Windows PowerShell:

~~~powershell
$env:APP_BANNER = "from-env"
java -jar target/config-precedence-demo.jar --spring.profiles.active=lab
Remove-Item Env:APP_BANNER
~~~

On Linux/macOS:

~~~bash
APP_BANNER=from-env java -jar target/config-precedence-demo.jar --spring.profiles.active=lab
~~~

The result is `from-env`. Spring Boot supports relaxed binding for environment variable names. For the property `app.banner`, the corresponding environment variable form is `APP_BANNER`: uppercase with dots replaced by underscores.

### 6.4. Step 4 — Add a Java system property

Run:

~~~bash
APP_BANNER=from-env java -Dapp.banner=from-system -jar target/config-precedence-demo.jar --spring.profiles.active=lab
~~~

In PowerShell, set the variable first and then run the command:

~~~powershell
$env:APP_BANNER = "from-env"
java -Dapp.banner=from-system -jar target/config-precedence-demo.jar --spring.profiles.active=lab
Remove-Item Env:APP_BANNER
~~~

The result is `from-system` according to Spring Boot 3.5.x/4.1.x `PropertySource` ordering: Java system properties have higher precedence than OS environment variables. Note that `-Dapp.banner=...` must be placed before `-jar` in the `java` command so the JVM recognizes it as a system property.

### 6.5. Step 5 — Add a command-line argument

Run:

~~~bash
APP_BANNER=from-env java -Dapp.banner=from-system -jar target/config-precedence-demo.jar --spring.profiles.active=lab --app.banner=from-cli
~~~

The final result is `from-cli`, because command-line arguments have higher precedence than environment variables, Java system properties, and Config Data.

### 6.6. Expected results table

| Run | Highest source holding `app.banner` | Effective Value |
| --- | --- | --- |
| 1. No profile, no overrides, no external files | Classpath `application.yml` | `classpath-default` |
| 2. Profile `lab`, no external files | Classpath `application-lab.yml` | `classpath-profile-lab` |
| 3. With external files, profile `lab` | `./config/application-lab.yml` | `external-profile-lab` |
| 4. With `APP_BANNER` | OS environment variable | `from-env` |
| 5. Plus `-Dapp.banner` | Java system property | `from-system` |
| 6. Plus `--app.banner` | Command-line argument | `from-cli` |

If your output differs from this table, do not randomly edit multiple files. Inspect active profiles, the working directory, configuration file paths, and the `PropertySource` list printed by the runner.

## 7. Changing Configuration File Search Locations

Spring Boot automatically searches for `application.properties` or `application.yaml` in default locations:

- Classpath root.
- The `config/` directory on the classpath.
- Current working directory.
- The `config/` directory inside the working directory.
- Immediate subdirectories of `config/` inside the working directory.

These locations are evaluated in order; higher-precedence locations can override locations evaluated earlier.

### 7.1. `spring.config.additional-location`

Use `additional-location` when you want to **add** locations alongside the default locations:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./tenant-config/
~~~

Additional directories are evaluated after the default locations, so they can override values from default files.

### 7.2. `spring.config.location`

Use `location` when you want to **replace** the default location list:

~~~bash
java -jar app.jar --spring.config.location=optional:file:./config-base/,optional:file:./config-prod/
~~~

When `spring.config.location` is set, default locations are no longer searched automatically as before. This easily causes classpath or external defaults that the application still relies on to disappear. If your goal is simply adding environment-specific override files, `spring.config.additional-location` is usually the right choice.

`spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are used very early to decide where to search for files. Therefore, supply them via environment variables, system properties, or command line; do not put them inside the very file they are meant to locate.

## 8. Profiles and Multiple Configuration Files

Profiles allow the same application to use different configurations per environment:

~~~yaml
# application.yml
app:
  banner: "default"
~~~

~~~yaml
# application-dev.yml
app:
  banner: "development"
~~~

~~~yaml
# application-prod.yml
app:
  banner: "production"
~~~

Activate a profile with:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

When multiple profiles are active, last-wins applies within the same location group: a profile evaluated later can override duplicate values from an earlier profile, depending on location and location group.

Never declare `spring.profiles.active` or `spring.profiles.default` inside a configuration document activated conditionally by a profile. Properties selecting profiles must live in profile-independent sources or be passed from the launch environment.

### 8.1. Multiple locations and location groups

When specifying multiple entries in `spring.config.location`, commas and semicolons carry different meanings:

- Commas separate location groups, which are processed in group order.
- Semicolons place multiple locations into the same group so profile rules apply at the same tier.

For example, `classpath:/cfg/,classpath:/ext/` does not mean the same thing as `classpath:/cfg/;classpath:/ext/` when multiple profile-specific files exist. Use location groups only once you understand the exact ordering required; otherwise, simpler configuration stays more predictable.

## 9. Loading Additional Sources with `spring.config.import`

`spring.config.import` allows a configuration file to import data from another file or supported configuration source. Values in the imported file can override values in the document declaring the import.

For example, `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./shared-config.yml"

app:
  banner: "from-application"
~~~

`shared-config.yml`:

~~~yaml
app:
  banner: "from-import"
~~~

When the imported file exists, the effective value in Config Data is `from-import`. The `optional:` prefix lets startup continue if the file does not exist. Omitting `optional:` makes the application fail when a mandatory location is missing.

If multiple locations appear in a single import declaration, they are processed in declaration order; later imports have higher precedence than earlier imports. A given location is imported only once even if declared in multiple places.

### 9.1. Distinguishing `import` and `additional-location`

| Mechanism | Where Declared? | Effect |
| --- | --- | --- |
| `spring.config.import` | Inside a Config Data document | Imports extra files/sources; imports sit right below the declaring document and can override it |
| `spring.config.additional-location` | Environment, system property, or command line | Adds search locations to the default configuration location set |
| `spring.config.location` | Environment, system property, or command line | Replaces the default search locations |

Do not treat these three mechanisms as different names for the same feature. They affect Config Data loading at different steps.

## 10. Relationship with Spring Cloud Config Client

Spring Cloud Config Client brings configuration from Config Server into a Spring Boot application. With modern Config Data, the client uses `spring.config.import`; `bootstrap.yml` is not needed for this import approach.

Example Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Dependency versions are managed by the Spring Cloud BOM compatible with your project's Spring Boot version.

In `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

With `optional:`, the application can continue starting when Config Server is unreachable. Without this prefix, Config Client requires fetching configuration from the server; the application halts startup if mandatory configuration cannot be loaded.

### 10.1. Ordering of property sources returned by Config Server

Config Server can serve shared configuration alongside application- and profile-specific configuration. For example, when a client has name `order-service`, profile `prod`, and also requests name `shared-db`, Config Server may return property sources in this order:

1. `application.properties`
2. `application-prod.properties`
3. `order-service.properties`
4. `order-service-prod.properties`
5. `shared-db.properties`
6. `shared-db-prod.properties`

Later property sources can override overlapping keys from earlier ones. Exact ordering also depends on `spring.cloud.config.name`, profiles, and label requested by the client.

### 10.2. Do not apply legacy bootstrap rules mechanically

Spring Cloud Config documentation includes properties controlling overrides of remote property sources such as:

- `spring.cloud.config.allow-override`
- `spring.cloud.config.override-none`
- `spring.cloud.config.override-system-properties`

These rules are tied to the legacy bootstrap mechanism and how Config Client places remote property sources. In particular, override permission must be granted from server/repository-side configuration; arbitrarily setting `allow-override` in local config does not automatically grant the client permission to override remote sources. Do not copy these flags into an application using `spring.config.import` without consulting documentation for your exact Spring Cloud Config version and bootstrap mode.

When using Config Data import, inspect actual property sources via `Environment` or diagnostic tools. Never collapse classpath files, external files outside the JAR, remote Config Server, and legacy bootstrap into a single universal precedence table for all configurations.

## 11. Identifying Which Source Supplied a Value

### 11.1. Using `Environment`

In code, you can read the value:

~~~java
String banner = environment.getProperty("app.banner");
~~~

To see which sources hold a key, iterate through `environment.getPropertySources()` as shown in `ConfigReportRunner`. Source names identify files, system properties, environment variables, or command-line flags. This is very useful when debugging locally.

### 11.2. Using Actuator `env` and `configprops`

Actuator provides `env` and `configprops` endpoints to help diagnose property sources and bindings. They can reveal which source supplied a property and which value was bound.

If you need to expose the `env` endpoint in a development environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
  endpoint:
    env:
      show-values: "never"
~~~

Enable this only temporarily in local environments or secured management networks. When viewing values is necessary, use controlled `show-values` and authentication suited to your Boot version. Never expose `env` or `configprops` publicly, as they can reveal configuration structure and sensitive details.

### 11.3. Enabling Config Data loading logs

When you do not understand why a file failed to load, increase logging for the config processor:

~~~yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
~~~

TRACE logs help pinpoint which locations were checked and which files were loaded. Do not leave TRACE logging enabled for config processing in production unless actively diagnosing an issue.

## 12. Startup Values and Runtime Refresh Are Two Different Things

The `app.banner` experiment in earlier sections restarted the application whenever changing environment variables, system properties, or command-line arguments. Those sources are normally read while constructing `Environment` and booting the context.

Editing a file on disk or updating a value in Config Server **does not automatically mean every running bean receives the new value immediately**. Distinguish clearly:

- **Startup configuration loading:** Spring Boot builds `Environment`, resolves property sources, and binds values into beans.
- **Configuration refresh:** a runtime mechanism updates `Environment`/emits events, after which supported beans or scopes can reflect new values.
- **Restart/rollout:** creates new processes or instances to reload configuration from scratch.

In Spring Cloud, `@RefreshScope` can recreate beans managed in the refresh scope after a refresh workflow is triggered. However, not every bean is refreshable, and you must never assume changing a file automatically sends a refresh event to every instance.

For settings affecting database connections, security, pools, threads, or one-time initialized beans, evaluate whether runtime refresh is safe or whether a restart/rollout is required. For sensitive settings or changes affecting business behavior, enforce versioning, auditing, and rollback plans.

## 13. Common Errors During Experiments

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Edited `application.yml` yet value stays unchanged | External file outside JAR or another source overrides it | Print `PropertySource` list; check `./config/` |
| `application-lab.yml` is not loaded | `lab` profile is inactive or wrong filename/location | Print `Environment.getActiveProfiles()` and enable TRACE on config loader |
| Environment variable fails to override | Wrong variable name, wrong process/container, or higher-precedence system property/CLI | Check `APP_BANNER`, command line, and `-Dapp.banner` |
| `-Dapp.banner` has no effect | Placed `-D` after `-jar` or passed mistakenly as an application argument | Move `-D...` before `-jar` |
| `--app.banner` flag has no effect | Wrapper/build tool did not forward arguments properly to JVM/application | Inspect exact launch command and `ApplicationArguments` |
| `application.properties` and `application.yml` give surprising results | Both exist in the same location; `.properties` wins | Keep only one format or inspect property sources |
| `spring.config.location` drops old configuration | This property replaces default locations | Switch to `spring.config.additional-location` if goal is additive |
| `spring.config.import` cannot find file | Mandatory location does not exist or wrong relative path | Check working directory; use `optional:` only when truly optional |
| Config Server overrides local unexpectedly | Different Config Data/bootstrap mode or override flags | Inspect property sources, versions, and remote repository settings |
| Edited file yet bean keeps old value | Bean bound at startup and no refresh/restart occurred | Check refresh scope/events or perform a rollout |

## 14. Practice Exercises

### Exercise 1 — Predict before running

Suppose these values exist simultaneously:

~~~text
application.yml                       = file
./config/application.yml              = external
APP_BANNER                            = env
-Dapp.banner                          = system
--app.banner                          = cli
~~~

Predict what `Environment.getProperty("app.banner")` will return. Then run the application and compare against the result.

### Exercise 2 — Change source ordering

1. Remove the `--app.banner` argument.
2. Keep `APP_BANNER=env` and `-Dapp.banner=system`.
3. Predict the value before running.
4. Remove `-Dapp.banner` and run again.
5. Record the winning source for each run.

### Exercise 3 — Compare profiles

Create `application-region-a.yml` and `application-region-b.yml`, each with a different value. Run with:

~~~bash
java -jar app.jar --spring.profiles.active=region-a,region-b
~~~

Then reverse the profile order. Observe the last-wins strategy and explain why an external file outside the JAR can still override a file inside the JAR.

### Exercise 4 — Import shared configuration

Create `shared-config.yml`, declare it in `spring.config.import`, and put the same `app.banner` key in both files. Run the application when the imported file exists and when it is renamed. Test both with and without the `optional:` prefix.

### Exercise 5 — Relate to Config Server

Read the Spring Cloud Config Client documentation and describe:

- Where Config Server obtains `application`, `profile`, and `label`.
- Why Config Data import can call Config Server multiple times when a profile is activated during configuration loading.
- When an application should fail startup if Config Server is unavailable.
- Why legacy bootstrap override flags cannot be applied arbitrarily to every modern configuration.

**Completion criteria:** you can explain an effective value by pointing to the exact winning property source, reproduce the result with a launch command, and recognize when a restart or bean refresh is required.

## 15. Summary

Spring Boot does not pick a value at random when the same property appears in multiple places. `Environment` aggregates `PropertySource` entries in a deterministic order; higher-precedence sources supply the effective value. In a typical application, profile-specific files and external files outside the JAR can override default configuration, while environment variables, Java system properties, and command-line arguments have their own precedence tiers.

To troubleshoot an overridden setting, check in order: active profiles, loaded Config Data locations and files, imports, environment variables, system properties, command line, and finally the property sources in `Environment`. When using Spring Cloud Config, account for server-returned property source ordering and distinguish Config Data imports from legacy bootstrap. Once an application is running, changing configuration sources also requires an appropriate refresh or restart workflow.

## References

- [Spring Boot 4.1 — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `PropertySource` precedence, Config Data, profiles, imports, and environment variables.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): checking property source order on the Boot 3.5 line.
- [Spring Boot — Properties and Configuration How-to](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html): file locations, `spring.config.location`, and `spring.config.additional-location`.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, profiles, property sources from Config Server, and behavior when the server is unavailable.
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html): server-side override mechanics.

Exact ordering and behavior of configuration properties can change across versions. When working on real projects, verify against documentation for your exact Spring Boot and Spring Cloud release train.
