# Property Has No Effect Due to Wrong Key, Wrong Source, or Wrong Read Timing

## 1. Identifying the True Nature of the Issue

In Spring Boot, a property can be declared with valid syntax yet the application still fails to use the expected value. Usually the bug falls into one of three categories:

1. **Wrong key or binding structure:** the property name, prefix, nested path, or data type does not match where it is read.
2. **Wrong source or priority:** the file was not loaded, the profile is inactive, an environment variable is misnamed, or a higher-priority source overrode the value.
3. **Wrong read timing:** the property was read before the configuration source loaded, read too early in Spring's lifecycle, or an object kept the old value after the Environment changed.

An effective diagnostic separates three questions:

- Does Spring see the exact key in the Environment?
- Does the bean bind or inject the exact value from the Environment?
- Is the executing component actually using that bean/value when needed?

Skipping any of these three questions makes it easy to edit the wrong file or add a duplicate-named property without fixing the root cause.

## 2. Where Does Spring Boot Read Properties From?

Spring Boot supports many configuration sources: `.properties` files, YAML, environment variables, Java system properties, command-line arguments, JSON configuration, JNDI, and test-specific sources.

Values are merged into the Spring Environment as `PropertySource`s. A source appearing later in precedence order can override values from earlier sources.

### 2.1. PropertySource Precedence Order in Spring Boot 3.5

The list below runs from lowest to highest precedence in the Spring Boot 3.5 documentation:

| Order | Source | Notes |
| --- | --- | --- |
| 1 | Default properties | E.g., `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` | Added during context refresh; too late for some startup properties |
| 3 | Config data | `application.properties`, YAML, and imported files |
| 4 | `RandomValuePropertySource` | Supplies only `random.*` keys |
| 5 | OS environment variables | E.g., `APP_REMOTE_CONNECTTIMEOUT` |
| 6 | Java system properties | Values passed via `-Dkey=value` |
| 7 | JNDI attributes | `java:comp/env` |
| 8 | ServletContext init parameters | Only in a matching Servlet environment |
| 9 | ServletConfig init parameters | Only in a matching Servlet environment |
| 10 | `SPRING_APPLICATION_JSON` | JSON in an environment variable or system property |
| 11 | Command-line arguments | E.g., `--app.remote.connect-timeout=8s` |
| 12 | `properties` on test annotations | E.g., `@SpringBootTest(properties = "...")` |
| 13 | `@DynamicPropertySource` | Dynamic source in tests |
| 14 | `@TestPropertySource` | Spring Test property source |
| 15 | Devtools global settings | Only when Devtools is enabled |

Example: a configuration file sets timeout to 3s, an environment variable sets 5s, a system property sets 6s, and the command line sets 8s. When all these sources are loaded together, the final value is 8s.

~~~properties
# application.properties
app.remote.connect-timeout=3s
~~~

~~~bash
# Linux/macOS
APP_REMOTE_CONNECTTIMEOUT=5s java -jar app.jar
~~~

~~~bash
# Java system property
java -Dapp.remote.connect-timeout=6s -jar app.jar
~~~

~~~bash
# Command-line argument has higher precedence than the sources above
java -jar app.jar --app.remote.connect-timeout=8s
~~~

Do not try to memorize every configuration source across every environment. When multiple values exist for the same key, check which source actually wins using Actuator env or by iterating over `PropertySource`s in the Environment.

### 2.2. Locations Where Spring Boot Automatically Searches for application.properties

By default, Spring Boot looks for `application.properties` and `application.yaml` in common locations:

1. Classpath root, e.g., `src/main/resources/application.properties`.
2. The `config/` directory on the classpath.
3. The current working directory where the application runs.
4. The `config/` directory under the current working directory.
5. Direct subdirectories of `config/` in the current working directory.

Locations outside the JAR can override values packaged inside the JAR. Thus, an `application.properties` file in the working directory can prevent the value in `src/main/resources` from being the final one.

A common deployment mistake is inspecting the right file in the IDE, yet when running the JAR from another directory, Spring Boot loads external configuration and replaces values.

### 2.3. spring.config.location and spring.config.additional-location

These two properties have different meanings:

- `spring.config.location` **replaces** the default search locations.
- `spring.config.additional-location` **adds** new locations alongside the default locations.

Example to add an external configuration file:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./deploy-config/
~~~

Example to search only the specified locations:

~~~bash
java -jar app.jar --spring.config.location=optional:file:./deploy-config/
~~~

If you accidentally use `spring.config.location` while still expecting Spring Boot to find all default files, packaged configuration may not load as expected.

`spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are used very early to decide which files to load. Supply them via environment variables, system properties, or command-line arguments; do not place them inside `application.properties` expecting them to govern finding that very file.

### 2.4. Profile-Specific Configuration

If the application activates the `prod` profile, Spring Boot considers files such as:

- `application.properties`
- `application-prod.properties`

Profile-specific files can override non-profile files. If multiple profiles are active, profiles listed later can override values from earlier ones.

~~~properties
# application.properties
app.remote.connect-timeout=3s
~~~

~~~properties
# application-prod.properties
app.remote.connect-timeout=10s
~~~

Activating a profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

If the application still runs under the `default` profile or another profile, `application-prod.properties` is not applied.

`spring.profiles.active` and `spring.profiles.default` must be declared in non-profile-specific documents; do not put them inside a document activated only by a profile.

### 2.5. spring.config.import and Multi-Document Files

You can import other configuration files:

~~~properties
# application.properties
app.remote.connect-timeout=3s
spring.config.import=optional:file:./remote-overrides.properties
~~~

If the imported file contains:

~~~properties
app.remote.connect-timeout=9s
~~~

values from the imported file can override values in the document declaring the import. A file can also import corresponding profile-specific configurations.

Spring Boot also supports multi-document YAML:

~~~yaml
app:
  remote:
    connect-timeout: 3s
---
spring:
  config:
    activate:
      on-profile: prod
app:
  remote:
    connect-timeout: 10s
~~~

The later document is applied only when its activation condition matches. When both `.properties` and YAML exist in the same location, `.properties` has higher precedence; standardize on one format across the application.

## 3. Wrong Key: Property Name and Binding Structure Mismatch

### 3.1. Use a Consistent Prefix

Suppose a configuration bean declares:

~~~java
@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {
    private Duration connectTimeout = Duration.ofSeconds(1);

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Valid key in `application.properties`:

~~~properties
app.remote.connect-timeout=3s
~~~

Common mistakes:

~~~properties
# Wrong prefix
app.remtoe.connect-timeout=3s

# Wrong field name
app.remote.connect-timout=3s

# Wrong structure
app.remote.timeout.connect=3s
~~~

Spring cannot guess that `remtoe` means `remote` or `connect-timout` means `connect-timeout`. If the misspelled key is not consumed, the field retains its default value without raising an obvious error.

To reduce mistakes:

- Choose a short, stable prefix and write it consistently.
- Use lowercase kebab-case in configuration files.
- Match exact camelCase Java field names.
- Create one `@ConfigurationProperties` class for a cohesive group of settings.
- Give properties clear semantic names, such as `connect-timeout` rather than an ambiguous key like `timeout`.

### 3.2. Relaxed Binding Does Not Mean Every Spelling Is Equivalent

Spring Boot supports relaxed binding when binding the Environment to `@ConfigurationProperties`. For example, the Java field `firstName` can bind from:

~~~properties
my.main-project.person.first-name=Lan
my.main-project.person.firstName=Lan
my.main-project.person.first_name=Lan
~~~

Prefixes of `@ConfigurationProperties` should be written in canonical form: lowercase and dashes, e.g., `my.main-project.person`.

Relaxed binding follows rules specific to each `PropertySource`. It supports camelCase, kebab-case, and underscores in properties/YAML files, whereas environment variables use uppercase and underscores according to their own rules.

Do not assume that because a spelling happened to work in a properties file, the exact same string works as an environment variable.

### 3.3. Rules for Converting a Property to an Environment Variable

To convert a canonical property into an environment variable:

1. Replace dots `.` with `_`.
2. Remove dashes `-`.
3. Convert everything to uppercase.

Examples:

| Canonical property | Environment variable |
| --- | --- |
| `app.remote.connect-timeout` | `APP_REMOTE_CONNECTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `my.service[0].other` | `MY_SERVICE_0_OTHER` |

For `app.remote.connect-timeout`, the variable `APP_REMOTE_CONNECT_TIMEOUT` is not the corresponding mapped name under those rules; dashes are removed, not converted into extra underscores.

PowerShell example:

~~~powershell
$env:APP_REMOTE_CONNECTTIMEOUT = "8s"
java -jar .\target\config-diagnostics-1.0.0-SNAPSHOT.jar
Remove-Item Env:APP_REMOTE_CONNECTTIMEOUT
~~~

Linux/macOS example:

~~~bash
APP_REMOTE_CONNECTTIMEOUT=8s java -jar target/config-diagnostics-1.0.0-SNAPSHOT.jar
~~~

The value of an environment variable is preserved as-is; Spring converts only the key name. For instance, `MY_PROPS_VALUES_KEY=VALUE` still binds the value as `VALUE`, without lowercasing it automatically.

### 3.4. `@ConfigurationProperties` and `@Value` Have Different Levels of Support

`@ConfigurationProperties` fits a structured group of settings:

~~~java
@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {
    // endpoint, connectTimeout, enabled...
}
~~~

It supports relaxed binding, IDE metadata, type conversion, and validation when properly configured.

`@Value` is a Spring Core feature, useful for a single value:

~~~java
@Value("${app.remote.connect-timeout:1s}")
private Duration connectTimeout;
~~~

`@Value` does not support full relaxed binding like `@ConfigurationProperties`. When using placeholders, write the key name in canonical form, for example:

~~~java
@Value("${demo.item-price}")
private BigDecimal itemPrice;
~~~

Using `${demo.itemPrice}` may fail to match the kebab-case key `demo.item-price` in a properties file. If configuration involves multiple fields, nested objects, or collections, prefer `@ConfigurationProperties`.

### 3.5. Verify the Configuration Bean Is Registered

Merely annotating a class with `@ConfigurationProperties` does not guarantee a bean exists. You must register the class via one of these approaches:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
~~~

Or:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteProperties.class)
public class RemoteConfiguration {
}
~~~

Or bind a third-party bean directly:

~~~java
@Configuration(proxyBeanMethods = false)
public class ThirdPartyConfiguration {

    @Bean
    @ConfigurationProperties("another")
    AnotherComponent anotherComponent() {
        return new AnotherComponent();
    }
}
~~~

Without scanning, `@EnableConfigurationProperties`, or a suitable bean method, the class may never be registered for the binder to process. Services then cannot inject the bean, or you might be reading an instance created manually with `new` that Spring never bound.

### 3.6. Wrong Data Type or Nested Structure

Even when a property exists, it can fail to bind as intended if the data type is invalid or the structure is wrong.

Example:

~~~properties
app.remote.connect-timeout=3s
app.remote.enabled=true
~~~

`Duration` accepts values with units like `3s`, `500ms`, `2m`. Providing an invalid string causes binding to fail with a conversion error.

In YAML, watch indentation carefully:

~~~yaml
app:
  remote:
    connect-timeout: 3s
    enabled: true
~~~

If `connect-timeout` is indented at the wrong level, the resulting key is no longer `app.remote.connect-timeout`.

When binding collections, maps, or lists, check index syntax. When binding map keys with special characters, bracket notation may be needed to preserve the key verbatim:

~~~properties
my.map[/key1]=value1
~~~

In YAML, bracket keys need to be quoted:

~~~yaml
my:
  map:
    "[/key1]": "value1"
~~~

## 4. Wrong Source: Key Is Right, Yet Source Is Unloaded or Overridden

### 4.1. File Is Not in a Location Spring Boot Searches

Check these questions:

- Is the file in `src/main/resources`?
- Was the file packaged into the JAR?
- When running the JAR, what is the current working directory?
- Is an `application.properties` outside the JAR overriding it?
- Is `spring.config.location` replacing the default location list?
- Was a custom file imported via `spring.config.import`?

You can inspect JAR contents:

~~~bash
jar tf target/app.jar
~~~

Look for `BOOT-INF/classes/application.properties` or the corresponding config file. Note that this command checks only whether the file was packaged; it does not tell you the final value after merging sources.

### 4.2. Profile Is Not Activated

If the property exists only in `application-prod.properties`, confirm the `prod` profile is actually active:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

You can print active profiles:

~~~java
@Component
public class ProfileReporter {

    public ProfileReporter(Environment environment) {
        System.out.println(
                "activeProfiles="
                        + Arrays.toString(environment.getActiveProfiles())
        );
    }
}
~~~

Use this snippet only for local diagnostics. Never print sensitive data into production logs.

### 4.3. Another Source Is Overriding It

Suppose `application-prod.properties` sets `3s`, yet the deployment environment has `APP_REMOTE_CONNECTTIMEOUT=10s`. Environment variables have higher precedence than config data, so the bean receives `10s`.

This is not a broken binder. The binder is receiving the winning value supplied by the Environment.

Do not add a second key in `application.properties` to try to fix a value overridden from the environment or command line. Identify which source is winning and fix it at the source managing that value.

### 4.4. `@PropertySource` Does Not Suit All Types of Configuration

Example:

~~~java
@Configuration
@PropertySource("classpath:custom.properties")
public class CustomPropertiesConfiguration {
}
~~~

`@PropertySource` is added to the Environment when the `ApplicationContext` refreshes. Thus, it is too late to configure certain properties Spring Boot reads prior to refresh, such as:

- `logging.*`
- `spring.main.*`

For properties controlling how Spring Boot boots, place them in Config Data, system properties, environment variables, or appropriate command-line arguments.

In addition, `@PropertySource` does not load YAML automatically and does not support multi-document properties/YAML like Config Data does. If you need to load YAML directly, use an appropriate loader mechanism or move the settings to standard Config Data.

## 5. Wrong Read Timing: Property Is Right, Yet Code Holds Stale Value

### 5.1. Reading a Property Before `SpringApplication` Runs

The following code reads a system property before Spring Boot loads configuration:

~~~java
public class Application {

    private static final String ENDPOINT =
            System.getProperty("app.remote.endpoint");

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

`System.getProperty(...)` reads only Java system properties at class initialization time. It does not read `application.properties`, YAML, or the full Spring Environment.

A better approach is injecting `Environment` or `RemoteProperties` into a Spring-managed bean:

~~~java
@Component
public class RemoteService {

    private final RemoteProperties properties;

    public RemoteService(RemoteProperties properties) {
        this.properties = properties;
    }
}
~~~

Never cache property reads into static fields before `SpringApplication.run(...)` initializes the Environment.

### 5.2. Comparing Read Timing Across Mechanisms

| Mechanism | When value is read | Notes |
| --- | --- | --- |
| `SpringApplication` properties | Application preparation and initialization phase | Some keys must exist before context refresh |
| `@PropertySource` | When configuration is processed during context refresh | Too late for some `spring.main.*` and `logging.*` |
| `@Value` | When the bean is created and placeholders resolve | Singleton fields do not auto-update when Environment changes |
| `@ConfigurationProperties` | When the configuration bean is bound | Requires bean registration and matching field structure |
| `Environment.getProperty(...)` | At method invocation time | Returns the winning value among current `PropertySource`s |
| Static initializer / manual `new` | When class/object is created outside Spring's lifecycle | Easily reads too early or bypasses Spring binding |

### 5.3. Singletons Do Not Auto-Update When Files or Environment Change

Bean example:

~~~java
@Component
public class RemoteService {

    @Value("${app.remote.connect-timeout}")
    private Duration connectTimeout;
}
~~~

The value is resolved when the bean is created. If the config file on disk later changes or a `PropertySource` is modified, the singleton's field does not re-bind automatically.

Likewise, a `@ConfigurationProperties` bean does not refresh itself simply because you edited `application.properties` while the application was running.

If configuration updates without restarting are required, use a refresh/rebind mechanism designed for that environment, such as an appropriate Spring Cloud solution or a controlled application update mechanism. Core Spring Boot does not watch every file and update every singleton automatically.

### 5.4. Reading `Environment` vs. Reading a Config Bean Can Yield Different Results

If `Environment.getProperty("app.remote.connect-timeout")` returns the right value while the bean uses something else, check:

- Is the bean truly the Spring-managed `@ConfigurationProperties` bean?
- Do the prefix and field names match?
- Are setters or constructor binding valid?
- Was an instance created manually via `new RemoteProperties()` instead of injecting the bean?
- Is the service caching the old value in a field or cache?
- Is another `@Value` reading a different key?
- Was the bean created before a custom `PropertySource` was added?

This indicates a binding or lifecycle bug, no longer a simple file-loading issue.

## 6. Runnable Example: Diagnosing Key, Source, and Binding

This example uses Java 17 and Spring Boot 3.5.0. The application binds the `app.remote` group to `RemoteProperties`, then prints the bound values alongside the values present in `Environment`.

### 6.1. Project Structure

~~~text
config-diagnostics/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/
    │   │       ├── ConfigDiagnosticsApplication.java
    │   │       └── RemoteProperties.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── example/
                └── RemotePropertiesBindingTests.java
~~~

### 6.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>config-diagnostics</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 6.3. File `src/main/resources/application.properties`

~~~properties
app.remote.endpoint=https://api.example.test
app.remote.connect-timeout=3s
app.remote.enabled=true
~~~

This is the default configuration packaged inside the application. Values can be overridden by profiles, external files, environment variables, system properties, or command-line arguments according to precedence order.

### 6.4. File `RemoteProperties.java`

~~~java
package example;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {

    private URI endpoint = URI.create("https://fallback.example.test");

    private Duration connectTimeout = Duration.ofSeconds(1);

    private boolean enabled;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Initializers in Java serve as object fallbacks. When Config Data provides matching properties, the binder overrides those values. Prefixes are written in lowercase kebab-case.

### 6.5. File `ConfigDiagnosticsApplication.java`

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDiagnosticsApplication.class, args);
    }

    @Bean
    CommandLineRunner reportEffectiveConfiguration(
            RemoteProperties properties,
            Environment environment) {

        return args -> {
            System.out.println("app.remote.endpoint="
                    + properties.getEndpoint());

            System.out.println("app.remote.connect-timeout="
                    + properties.getConnectTimeout());

            System.out.println("environment.app.remote.connect-timeout="
                    + environment.getProperty(
                            "app.remote.connect-timeout"
                    ));

            System.out.println("app.remote.enabled="
                    + properties.isEnabled());
        };
    }
}
~~~

`@ConfigurationPropertiesScan` registers `RemoteProperties` as a bean for Spring Boot to bind. `CommandLineRunner` runs after the context is built, allowing comparison between the bound object and the winning value in `Environment`.

Never print passwords, tokens, or secrets in production applications. The example prints only a dummy endpoint and timeout for illustration.

### 6.6. File `RemotePropertiesBindingTests.java`

~~~java
package example;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RemotePropertiesBindingTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RemoteProperties.class)
    static class PropertiesConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void javaDefaultRemainsWhenPropertyIsAbsent() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(RemoteProperties.class);

            RemoteProperties properties =
                    context.getBean(RemoteProperties.class);

            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(1));
        });
    }

    @Test
    void canonicalPropertyOverridesTheJavaDefault() {
        runner.withPropertyValues(
                        "app.remote.connect-timeout=7s"
                )
                .run(context -> {
                    RemoteProperties properties =
                            context.getBean(RemoteProperties.class);

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(7));
                });
    }

    @Test
    void misspelledPropertyDoesNotOverrideTheExpectedField() {
        runner.withPropertyValues(
                        "app.remote.connect-timout=9s"
                )
                .run(context -> {
                    RemoteProperties properties =
                            context.getBean(RemoteProperties.class);

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(1));
                });
    }

    @Test
    void environmentAndBoundObjectSeeTheSameCanonicalValue() {
        runner.withPropertyValues(
                        "app.remote.connect-timeout=5s"
                )
                .run(context -> {
                    RemoteProperties properties =
                            context.getBean(RemoteProperties.class);

                    assertThat(context.getEnvironment().getProperty(
                            "app.remote.connect-timeout"
                    )).isEqualTo("5s");

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                });
    }
}

@SpringBootTest(properties = "app.remote.connect-timeout=9s")
class TestPropertyOverrideTests {

    @org.springframework.beans.factory.annotation.Autowired
    RemoteProperties properties;

    @Test
    void testPropertyOverridesThePackagedApplicationProperties() {
        assertThat(properties.getConnectTimeout())
                .isEqualTo(Duration.ofSeconds(9));
    }
}
~~~

The tests use `ApplicationContextRunner` to verify the binder in a minimal context. The final `@SpringBootTest` verifies that test properties override the `3s` value in `src/main/resources/application.properties`.

### 6.7. Running the Program and Checking Results

Use JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn package
java -jar target/config-diagnostics-1.0.0-SNAPSHOT.jar
~~~

With the sample configuration file, the exact business output is:

~~~text
app.remote.endpoint=https://api.example.test
app.remote.connect-timeout=PT3S
environment.app.remote.connect-timeout=3s
app.remote.enabled=true
~~~

`Duration.toString()` formats three seconds as `PT3S`, while `Environment` retains the raw property string `3s`.

Try overriding via the command line:

~~~bash
java -jar target/config-diagnostics-1.0.0-SNAPSHOT.jar --app.remote.connect-timeout=8s
~~~

The relevant lines will be:

~~~text
app.remote.connect-timeout=PT8S
environment.app.remote.connect-timeout=8s
~~~

Try an environment variable:

~~~powershell
$env:APP_REMOTE_CONNECTTIMEOUT = "6s"
java -jar .\target\config-diagnostics-1.0.0-SNAPSHOT.jar
Remove-Item Env:APP_REMOTE_CONNECTTIMEOUT
~~~

The resulting timeout is `PT6S`. If misnamed `APP_REMOTE_CONNECT_TIMEOUT`, that key does not map to the canonical property `app.remote.connect-timeout` under the environment-variable naming rule.

**Distinguish the two test types in the example clearly:** the `ApplicationContextRunner` assertions verify binding and defaults inside an isolated test context; `@SpringBootTest` verifies the real Config Data source alongside test properties. The Maven commands above verify the full example on a machine with JDK and Maven.

## 7. Diagnostic Workflow When a Property Has No Effect

Proceed in order to locate the exact layer causing the fault.

### Step 1: Identify the Canonical Key the Code Actually Reads

Locate every place using the property:

- `@ConfigurationProperties(prefix = "...")`
- `@Value("${...}")`
- `Environment.getProperty("...")`
- `Binder`
- `@ConditionalOnProperty`

Record the full name, e.g., `app.remote.connect-timeout`. Never look only at the Java field name `connectTimeout` and guess the key.

When using `@ConditionalOnProperty`, inspect `prefix`, `name`, `havingValue`, and `matchIfMissing`. The property may exist yet the condition does not match because its value differs.

### Step 2: Check Whether `Environment` Sees the Key

You can do a quick check inside a bean:

~~~java
@Component
public class PropertyProbe {

    public PropertyProbe(Environment environment) {
        String key = "app.remote.connect-timeout";

        System.out.println("present=" + environment.containsProperty(key));
        System.out.println("value=" + environment.getProperty(key));
    }
}
~~~

If `containsProperty` is false, inspect the key, file source, profile, environment variables, and config locations.

If the value is present yet differs from expectations, suspect that a higher-precedence source overrode it.

### Step 3: Check Which Source Supplies the Value

In a local test environment, iterate over `PropertySource`s:

~~~java
for (PropertySource<?> source : environment.getPropertySources()) {
    if (source.containsProperty("app.remote.connect-timeout")) {
        System.out.println(
                source.getName() + " -> "
                        + source.getProperty("app.remote.connect-timeout")
        );
    }
}
~~~

This list reveals multiple sources containing the same key. `Environment.getProperty(...)` returns the winning value according to precedence order.

Use this probe only for non-sensitive keys. Never dump the entire `Environment` or secrets into production logs.

### Step 4: Check Which Config Data Files Were Actually Loaded

Enable detailed logging for configuration loading:

~~~properties
logging.level.org.springframework.boot.context.config=TRACE
~~~

This log shows which files Spring Boot searches and loads, which profiles are considered, and which imports are processed.

If using `spring.config.location`, check whether it replaced the default locations. When you want to add files, consider `spring.config.additional-location`.

### Step 5: Compare `Environment` Values Against the Bound Bean

If `Environment` returns `5s` yet `RemoteProperties` stays at `1s`, check:

- Was the configuration bean registered?
- Is the prefix exact?
- Are fields/getters/setters or constructor binding valid?
- Was an instance constructed manually with `new`?
- Can the data type convert cleanly?
- Was the bean created before a custom config source appeared?

If both `Environment` and the bean are right yet the feature still uses the old value, look for cached fields, static fields, other instances, or code reading a property elsewhere.

### Step 6: Check Overriding Sources

Inspect in real operational order:

- Are there `--app.remote...` command-line arguments?
- Is `SPRING_APPLICATION_JSON` set?
- Does Java have `-Dapp.remote...` arguments?
- Does the container/Kubernetes define environment variables?
- Are there profile-specific files?
- Are there config files outside the JAR?
- Do tests use `properties`, `@DynamicPropertySource`, or `@TestPropertySource`?

Never assume the value in a file is always the final value.

### Step 7: Use Actuator When Production Diagnostics Are Needed

If the application includes Actuator and exposes the relevant endpoints:

- `/actuator/env` or `/actuator/env/{property.name}` shows property sources and `Environment` values.
- `/actuator/configprops` shows bound `@ConfigurationProperties` beans.

The two endpoints answer different questions: `env` shows where values came from; `configprops` shows what values the configuration objects actually received.

These endpoints can expose property names, configuration structure, or sensitive info. Expose them only when needed, restrict access, and protect them according to your system's security policy.

## 8. Common Mistakes

1. **Wrong prefix or typo in the key.** E.g., `app.remtoe` or `connect-timout`; fields retain default values.
2. **Applying wrong environment-variable naming rules.** Dashes are dropped, not replaced with extra underscores.
3. **Assuming every source has equal priority.** Environment variables, system properties, and command-line arguments can override Config Data.
4. **Placing a file outside the JAR while running from a different directory.** Spring Boot may miss the expected file or pick up a different one.
5. **Using `spring.config.location` when only adding a file.** This replaces default locations; use `spring.config.additional-location` to add.
6. **Inactive profile.** `application-prod.properties` is ignored unless the `prod` profile is active.
7. **Putting `spring.config.location` inside `application.properties`.** This property must be provided early via environment, system property, or command line.
8. **Using `@PropertySource` for `logging.*` or `spring.main.*`.** The source is added too late for several startup properties.
9. **Using non-canonical placeholders in `@Value`.** `@Value` lacks full relaxed binding unlike `@ConfigurationProperties`.
10. **Forgetting to register `@ConfigurationProperties`.** The class is not scanned/enabled or registered as a bean.
11. **Constructing objects with `new`.** Manually created instances bypass Spring's binder and dependency injection.
12. **Confusing `Environment` values with bound bean values.** Check both to tell a source error apart from a binder error.
13. **Expecting singletons to update automatically when files change.** `@Value` and `@ConfigurationProperties` do not refresh merely because a file on disk changed.
14. **Reading properties in static initializers.** The class may initialize before the Spring `Environment` is ready.
15. **Wrong type or YAML syntax.** The binder may fail conversion or receive a different key hierarchy than intended.
16. **Ignoring test override precedence.** `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, and `@TestPropertySource` have their own precedence order.
17. **Using both `.properties` and YAML in the same location.** `.properties` wins; having both can make configuration appear ignored.
18. **Not checking property origin.** Looking only at the final value is rarely enough to tell which file or source won.

## 9. Configuration Review Checklist

- [ ] Identified the exact canonical key the code reads.
- [ ] `@ConfigurationProperties` prefix uses lowercase kebab-case.
- [ ] Field names and YAML/properties structure match.
- [ ] Environment variables follow the rule: dots → underscores, drop dashes, uppercase.
- [ ] `@ConfigurationProperties` beans are scanned or enabled.
- [ ] Verified values via `Environment.getProperty(...)`.
- [ ] Verified which source wins when multiple `PropertySource`s exist.
- [ ] Configuration files reside where Spring Boot actually searches or are imported explicitly.
- [ ] Required profiles are active.
- [ ] Distinguished `spring.config.location` from `spring.config.additional-location`.
- [ ] Did not use `@PropertySource` for properties needed before context refresh.
- [ ] Did not read properties in static initializers or before `SpringApplication.run`.
- [ ] Did not expect singletons to auto-update when `Environment`/files change.
- [ ] Compared `Environment` against the bound configuration bean.
- [ ] Added tests covering defaults, valid key overrides, and typos/wrong keys.
- [ ] Actuator `env`/`configprops` are exposed and secured only when genuinely needed.

## 10. Self-Check Questions

**Question 1.** Why can a property exist in `application.properties` while the bean receives a different value?  
**Answer:** A higher-precedence `PropertySource`, such as an environment variable or command-line argument, can override the value in the file.

**Question 2.** Which environment variable does `app.remote.connect-timeout` map to?  
**Answer:** `APP_REMOTE_CONNECTTIMEOUT`; dots become underscores, dashes are dropped, and characters become uppercase.

**Question 3.** How does `spring.config.location` differ from `spring.config.additional-location`?  
**Answer:** `location` replaces default search locations; `additional-location` adds extra locations.

**Question 4.** Why is `@PropertySource` unsuitable for configuring `spring.main.*`?  
**Answer:** Its `PropertySource` is added during context refresh, whereas some `spring.main.*` properties are read earlier than that.

**Question 5.** When should `@ConfigurationProperties` be used over `@Value`?  
**Answer:** When configuring a structured group of settings with multiple fields, nested objects, collections, relaxed binding, or validation.

**Question 6.** If `Environment` returns the right value while the configuration bean is wrong, what should be checked?  
**Answer:** Bean registration, prefix, fields/getters/setters, data types, manual instantiation with `new`, and bean creation timing.

**Question 7.** Does editing `application.properties` while the application is running automatically update `@Value` fields?  
**Answer:** No. Values resolved into singletons do not auto-update; an explicit refresh/rebind mechanism or application restart is required.

**Question 8.** Which Actuator endpoints show where a value came from and what a bean bound?  
**Answer:** `env` inspects `Environment`/property sources; `configprops` inspects bound `@ConfigurationProperties` beans.

## Official References

- Spring Boot 3.5 Reference — Externalized Configuration, PropertySource ordering, Config Data, profiles, imports, placeholders, and relaxed binding: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 How-to — Properties and Configuration: https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html
- Spring Boot 3.5 Reference — Profiles: https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html
- Spring Boot 3.5 Reference — Type-safe Configuration Properties and validation: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 Actuator API — Environment endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/env.html
- Spring Boot 3.5 Actuator API — Configuration Properties endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/configprops.html

**Key takeaway:** When a property has no effect, inspect three layers: whether the key and binding are right, which source wins, and when the property is read. Compare `Environment` with `@ConfigurationProperties` beans, identify the `PropertySource` providing the value, and inspect the bean lifecycle. This separates configuration errors from binding errors and stale-value bugs.
