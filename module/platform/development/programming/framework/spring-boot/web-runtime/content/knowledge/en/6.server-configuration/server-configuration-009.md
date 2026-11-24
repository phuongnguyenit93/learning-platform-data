# Passing Configuration via Files, Environment Variables, and Command-Line Arguments in Spring Boot

## 1. Lesson Objectives

In Spring Boot, the same application can run on a developer machine, in testing environments, staging, and production without recompiling whenever HTTP ports, paths, timeouts, or connection parameters change. This mechanism is called **externalized configuration**: configuration values are supplied from multiple sources, merged into an Environment, and used by Spring Boot or application Beans at startup.

This lesson focuses on web-runtime and embedded server configuration across the three most common channels:

1. **Configuration files:** application.properties, application.yml/application.yaml, profile-specific files, and files external to the artifact.
2. **Environment variables:** SERVER_PORT, SPRING_PROFILES_ACTIVE, and application-specific variables.
3. **Command-line arguments:** --server.port=9090, --spring.profiles.active=prod, and other options passed after the JAR.

After this lesson, you will be able to select an appropriate configuration source, explain the final resolved value when multiple sources share a key, run the same JAR with different configurations, use ConfigurationProperties for binding/validation, and diagnose errors when the server fails to bind the expected port.

The Java and Gradle examples are presented for Spring Boot 3.3.x and Java 17 or higher. Externalized configuration principles also apply broadly to newer Spring Boot branches, though always check the documentation of your exact version for starter names, properties, and defaults that may change.

## 2. Distinguishing Application Code, Artifacts, and Runtime Configuration

Source code defines *what* the application does; configuration defines *which values* the application runs with.

For example, the same executable JAR can run as follows:

| Environment | HTTP Port | Application Mode | Common Configuration Sources |
| --- | --- | --- | --- |
| Laptop | 8080 | local | application.yml inside the JAR |
| Staging | 9090 | staging | external files, environment variables |
| Production | 8081 | production | ConfigMap/Secret, environment variables, startup arguments |
| HTTP testing | random port | test | test properties or RANDOM_PORT |

To accept requests, Spring Boot must resolve valid configuration values, create the ApplicationContext, initialize the embedded server, and bind successfully to the port. Invalid configuration can cause startup to fail before any controller is ever invoked.

Important property groups for web-runtime:

- server.port: the port the HTTP server listens on; the common default is 8080.
- server.address: the interface address the server binds to.
- server.servlet.context-path: context path for Servlet/Spring MVC.
- server.compression.enabled: enables/disables suitable HTTP response compression.
- server.shutdown: shutdown policy in branches that support this property.
- spring.lifecycle.timeout-per-shutdown-phase: wait time for each lifecycle shutdown phase.
- spring.profiles.active: specifies active profiles.
- logging.level.root: adjusts root log level.
- app.*: custom namespace for application business configuration.

A property does not necessarily exist in every Spring Boot version or every web stack. For instance, server.servlet.context-path applies to Servlets; for Spring WebFlux, you must configure the base path using the corresponding reactive property. Do not copy an entire MVC configuration block into WebFlux without checking.

## 3. How Do Spring Environment and PropertySource Work?

Spring places configuration sources into an Environment composed of multiple PropertySources. When looking up a key, the lookup mechanism checks precedence and retrieves the winning value. Spring Boot uses that value to configure the server, logging, auto-configuration, and application Beans.

Concepts to distinguish:

- **Property name:** logical key name, e.g., server.port.
- **Property value:** the selected value, e.g., 9090.
- **Property source:** the provider of key/value pairs, such as the OS environment, YAML files, or command line.
- **Binding:** converting text values into Java types such as int, boolean, Duration, URI, or structured objects.
- **Profile:** a mechanism to activate groups of settings per environment or application role.

Some properties are read **very early** during bootstrap. For example, spring.config.name, spring.config.location, and spring.config.additional-location must take effect before Spring Boot decides which configuration files to load. Therefore, supply them via environment variables, system properties, or startup arguments—not inside the very file you are asking Spring Boot to find.

Values from Environment are typically resolved at application startup. Changing an environment variable in another terminal or editing a YAML file on disk **does not automatically update** the port or already-initialized Beans. To apply runtime configuration changes reliably, you normally restart the process or use a purpose-built configuration refresh mechanism.

## 4. Method 1: application.properties and application.yml Files

Spring Boot automatically detects configuration files with basename application in supported locations. The two common formats are Java Properties and YAML. Standardize on one format within a given application to avoid confusion.

Example src/main/resources/application.properties:

~~~properties
spring.application.name=server-config-demo
server.port=8080
server.compression.enabled=true
app.mode=local
app.request-timeout=2s
~~~

Equivalent configuration in src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: server-config-demo

server:
  port: 8080
  compression:
    enabled: true

app:
  mode: local
  request-timeout: 2s
~~~

Both files express the same logical properties such as server.port and app.request-timeout. YAML uses indentation to group attributes; Spring Boot flattens them into hierarchical keys. For example, server.compression.enabled corresponds to server -> compression -> enabled.

**Notes:**

- YAML requires exact indentation; use spaces rather than tabs.
- Values with special characters may need quotes; avoid relying on YAML's implicit type inference.
- Spring automatically converts strings like "2s" to Duration when binding to an appropriate Duration field.
- Never place real passwords/tokens in files committed to Git.
- If the same location contains both application.properties and YAML, Spring Boot documentation gives precedence to .properties; it is best not to keep two files with overlapping keys.
- When files inside resources are packaged into a JAR, changing their values usually requires rebuilding the artifact; use external files for environment-specific changes.

### 4.1. Profile-Specific Configuration

A common structure:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
~~~

application.yml holds shared defaults:

~~~yaml
server:
  port: 8080

app:
  mode: local
  request-timeout: 2s
~~~

application-dev.yml:

~~~yaml
server:
  port: 8085

app:
  mode: development
~~~

application-prod.yml:

~~~yaml
server:
  port: 8081

app:
  mode: production
  request-timeout: 5s
~~~

Activate the prod profile using one of these approaches:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar build/libs/server-config-demo-1.0.0.jar
~~~

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.profiles.active=prod
~~~

When the prod profile is actually active and no higher-precedence source overrides them, server.port becomes 8081, app.mode becomes production, and app.request-timeout becomes 5s.

Do not put spring.profiles.active inside application-prod.yml to activate the prod profile itself. Profiles must be selected from the environment or a valid configuration source before profile-specific files are processed. With multiple active profiles, ordering and config location groups can affect which key wins; do not assume files always merge in one fixed order.

## 5. Where Does Spring Boot Look for Configuration Files?

In Spring Boot 3.3's default configuration, common locations include:

1. Classpath root, usually resources packaged inside the JAR.
2. The config directory on the classpath.
3. The process's current working directory.
4. A config directory directly under the working directory.
5. Direct subdirectories of config outside the artifact.

External files in higher-precedence locations can override files packaged inside the JAR. Thus, two processes running the exact same JAR from two different working directories can receive different configurations.

Example deployment layout:

~~~text
deploy/
  server-config-demo-1.0.0.jar
  config/
    application-prod.yml
~~~

If launched from the deploy directory with active profile prod, Spring Boot can find the external file deploy/config/application-prod.yml. If the same JAR is run from another directory, that relative file may not be found as expected.

Make working directories, absolute/relative paths, profiles, and file permissions explicit. Never assume the JAR's location and the working directory are always the same directory.

### 5.1. spring.config.location

The spring.config.location property specifies locations to search for config data and **replaces the default locations**. Example running with a directory containing application.yml:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.config.location=file:./deployment-config/
~~~

Directory paths in config location require a trailing /; Spring Boot appends the config basename when searching. If you specify a specific file instead of a directory, that file is loaded directly. Using location can also affect which profile-specific files are searched.

Because spring.config.location replaces default locations, using it carelessly can cause the application to lose default settings packaged in the JAR. Use it only when you want complete control over the full set of locations.

### 5.2. spring.config.additional-location

If you want to keep default locations and add external deployment files with higher precedence, use spring.config.additional-location:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.config.additional-location=optional:file:./deployment-config/
~~~

Spring Boot still checks default locations and adds the deployment-config directory. The optional: prefix skips missing locations. If the config is mandatory for safe startup, omit optional: so startup fails early when the file/directory is missing.

Use real environment paths and ensure the service account/process has read permissions. Do not rely on the working directory when deploying via a service manager unless verified.

### 5.3. spring.config.import

Additional configuration resources can be imported from inside an already-loaded file:

~~~yaml
spring:
  config:
    import: "optional:file:./extra-config.yml"
~~~

extra-config.yml can override keys defined in the importing file according to config data rules. When multiple imports or location groups exist, understand the corresponding precedence rules.

Import also supports config trees, convenient when deployment platforms mount many small files such as Secrets or ConfigMaps:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

For example, a file /run/secrets/app.token can produce property app.token for the application. Do not mark genuinely required secrets as optional: and let the application continue running with missing values.

## 6. Method 2: Operating System Environment Variables

Environment variables are a common way to pass configuration into a process without modifying files inside the JAR. When a process is created, it receives a copy of its parent process's environment along with values supplied by the platform.

In Spring Boot, the most memorable mapping pattern is:

| Logical Property | Environment Variable | Meaning |
| --- | --- | --- |
| server.port | SERVER_PORT | Embedded server port |
| server.address | SERVER_ADDRESS | Bind address |
| spring.profiles.active | SPRING_PROFILES_ACTIVE | List of active profiles |
| logging.level.root | LOGGING_LEVEL_ROOT | Root logging level |
| app.mode | APP_MODE | Custom mode |
| app.request-timeout | APP_REQUESTTIMEOUT | Custom timeout duration |

The standard relaxed binding rule to convert a canonical property to an environment variable is: replace dots with underscores, **remove dashes**, and convert to uppercase. Therefore, app.request-timeout becomes APP_REQUESTTIMEOUT. For lists, indices are typically placed between underscores, such as MY_SERVICE_0_OTHER for my.service[0].other.

Documentation and @ConfigurationProperties annotations generally recommend lowercase kebab-case canonical names, such as app.request-timeout. Avoid guessing binding rules by inserting underscores between every word.

### 6.1. Linux/macOS: Passing Temporarily for a Single Process

~~~bash
SERVER_PORT=9090 APP_MODE=staging java -jar build/libs/server-config-demo-1.0.0.jar
~~~

This only provides values to the process launched by that command. It does not edit YAML files or set variables permanently across terminals.

To set variables in the current shell session:

~~~bash
export SERVER_PORT=9090
export APP_MODE=staging
java -jar build/libs/server-config-demo-1.0.0.jar
~~~

To remove variables in the current shell:

~~~bash
unset SERVER_PORT
unset APP_MODE
~~~

### 6.2. Windows PowerShell

~~~powershell
$env:SERVER_PORT = "9090"
$env:APP_MODE = "staging"
java -jar build/libs/server-config-demo-1.0.0.jar
~~~

These variables apply to processes launched from that PowerShell session. To clear them in the current session:

~~~powershell
Remove-Item Env:SERVER_PORT
Remove-Item Env:APP_MODE
~~~

If running via an IDE, Windows Service, container, or CI/CD, environment variables must be supplied to that exact process. Setting a variable in a different terminal does not alter the environment already passed to a running application process.

### 6.3. Environment Variables and Placeholders in Files

You can reference a variable using Spring placeholder syntax:

~~~yaml
server:
  port: ${PORT:8080}

app:
  mode: ${APP_MODE:local}
~~~

This example uses PORT and APP_MODE if defined; otherwise it uses the default value after the colon. This is an intentional way to define an alias PORT for server.port in YAML.

Distinguish the two mechanisms:

- SERVER_PORT maps directly to property server.port from the OS environment.
- PORT is only used for placeholder substitution in the example above; it is not the canonical environment variable name for server.port.

If both SERVER_PORT and PORT exist simultaneously, SERVER_PORT can override the value coming from the YAML file because the OS environment has higher precedence than config data. Do not assume placeholders alter Spring Boot's precedence rules.

### 6.4. Docker Compose

In containers, environment variables are passed via service configuration. Example:

~~~yaml
services:
  web:
    image: example/server-config-demo:1.0
    environment:
      SERVER_PORT: "8080"
      APP_MODE: "production"
      APP_REQUESTTIMEOUT: "5s"
    ports:
      - "8080:8080"
~~~

This is an illustrative snippet for an already-built image with an appropriate startup command. The left side of ports is the host port; the right side is the container port. If you change SERVER_PORT to 9090, synchronize the container port in mappings/Services/health checks, e.g., "8080:9090".

When configurations mismatch, a container may keep running while requests from the host never reach the server. Always check port-binding logs and curl against the actual port.

## 7. Method 3: Spring Boot Command-Line Arguments

By default, SpringApplication reads options formatted as --key=value from main arguments and adds them to the Environment. Example:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9191 --app.mode=cli
~~~

Here --server.port and --app.mode are **Spring Boot application arguments**. When values simultaneously exist from files, environment variables, or JVM system properties, these command-line arguments normally have higher precedence in standard runs.

You can launch with multiple options, including profiles:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --spring.profiles.active=prod --server.port=9191 --logging.level.root=INFO
~~~

The -- prefix is essential. Writing server.port=9191 without -- will not create a property under default syntax. Also do not place --server.port before -jar expecting the JVM to understand it as a Java option.

### 7.1. JVM -D Options and Spring Boot -- Arguments Differ

The two commands below supply the same property via two mechanisms:

~~~bash
java -Dserver.port=9095 -jar build/libs/server-config-demo-1.0.0.jar
~~~

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9095
~~~

The first sets a Java system property before -jar. The second passes an application argument to Spring Boot after the JAR path. When both are present, Spring Boot's --server.port normally takes precedence over -Dserver.port.

JVM options such as -Xmx512m or -Dserver.port=9095 must be placed in the Java launcher position, i.e., before -jar. Moving -Dserver.port=9095 after the JAR name makes it just an application argument string, not processed by the Java launcher as a system property.

### 7.2. Passing Arguments with Gradle bootRun

In a project with the Spring Boot Gradle plugin and a configured bootRun task:

~~~bash
./gradlew bootRun --args='--server.port=9191 --app.mode=cli'
~~~

This is convenient for development. Running java -jar after building an executable JAR tests the artifact closer to how it is deployed.

### 7.3. Can Command-Line Properties Be Disabled?

Yes. When customizing SpringApplication, an application can call setAddCommandLineProperties(false) to prevent --key=value options from being added to the Environment. This is an intentional bootstrap customization and alters precedence rules. If CLI arguments fail to override files as expected, check whether the application has this customization.

Do not disable this mechanism merely to keep a value fixed; establish clear application and deployment configuration policies instead.

## 8. Precedence Order When Multiple Sources Declare the Same Key

Spring Boot 3.3 defines a more detailed PropertySource order than the list below. For a typical production application considering just the sources studied here, the general order **from strongest to weakest** is:

1. Spring Boot application arguments --key=value.
2. SPRING_APPLICATION_JSON.
3. Java system properties passed via -Dkey=value.
4. OS environment variables.
5. Config data from .properties/.yml files (external locations can override packaged config).
6. Default values set by the application.

In unit/integration tests, @TestPropertySource, @DynamicPropertySource, and test properties have their own precedence, which can outrank CLI arguments. Therefore, do not apply this simplified table mechanically to every test setup.

Within config data itself, profile-specific values normally override non-profile values when files are resolved under the same location/group rules. External files usually outrank files inside the JAR. With multiple locations and profiles, detailed resolution order can be subtle; verify using the actual running configuration.

Illustrative conflict example:

| Source | server.port |
| --- | ---: |
| application.yml inside JAR | 8080 |
| external application-prod.yml | 8081 |
| SERVER_PORT | 9090 |
| -Dserver.port | 9190 |
| --server.port | 9290 |

If all of these sources are active in a normal run, the effective port will be **9290** because the Spring Boot --server.port argument has the highest precedence in this group.

If you omit CLI, the port becomes 9190; omit JVM -D as well, and it becomes 9090; omit the environment variable, and it can fall back to 8081. That is an example for learning precedence, not a suggestion that every project should define the same key in five places.

### 8.1. Example Command Demonstrating Conflict Resolution

Suppose the default file contains server.port=8080:

~~~bash
SERVER_PORT=9090 java -Dserver.port=9190 -jar build/libs/server-config-demo-1.0.0.jar --server.port=9290
~~~

Expected result: the server attempts to bind port 9290. This expectation holds provided the port is free, related settings are valid, and the application has not customized command-line property handling.

### 8.2. SPRING_APPLICATION_JSON

Spring Boot also supports passing configuration JSON inside an environment variable:

~~~bash
SPRING_APPLICATION_JSON='{"server":{"port":9090},"app":{"mode":"json"}}' java -jar build/libs/server-config-demo-1.0.0.jar
~~~

The JSON content corresponds to server.port=9090 and app.mode=json. In default precedence, this source outranks OS environment variables but ranks below command-line arguments. It is helpful in environments needing hierarchical config without creating many separate variables.

Do not place secrets in command history or shell commands that may be logged. Null values in JSON should also not be relied upon to delete a property set in a lower-precedence source.

## 9. Java 17+ and Spring Boot 3.3 Practice: One JAR, Three Configuration Sources

This section presents a standalone sample project. Prerequisites: JDK 17+, a Gradle Wrapper version compatible with Spring Boot 3.3, and access to dependency repositories. You do not need to install Tomcat separately because the web starter provides an embedded server.

Structure:

~~~text
server-config-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/web/
        ServerConfigApplication.java
        AppSettings.java
        RuntimeConfigController.java
      resources/
        application.yml
    test/
      java/example/web/
        AppSettingsTest.java
~~~

### 9.1. settings.gradle

~~~groovy
rootProject.name = 'server-config-demo'
~~~

### 9.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In a project that already has Gradle settings or dependency management, preserve the version and plugin conventions managed by the project. The versions in this example merely illustrate a reproducible Spring Boot 3.3 project, not advice to upgrade/downgrade existing modules.

### 9.3. application.yml

~~~yaml
spring:
  application:
    name: server-config-demo

server:
  port: 8080

app:
  mode: local
  request-timeout: 2s
~~~

### 9.4. ServerConfigApplication.java

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ServerConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServerConfigApplication.class, args);
    }
}
~~~

@ConfigurationPropertiesScan discovers suitable configuration classes in the scan scope and registers Beans bound to the Environment.

### 9.5. AppSettings.java

~~~java
package example.web;

import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppSettings(
        @NotBlank String mode,
        @NotNull Duration requestTimeout
) {
}
~~~

A Java record models an immutable group of properties. Property app.mode binds to String mode; app.request-timeout binds to Duration requestTimeout. The validation starter provides Bean Validation checks at binding time.

For instance, omitting app.mode or app.request-timeout from all sources can fail startup instead of letting a null error occur while handling a request. That catches missing configuration early, though only when the configuration Bean is properly registered and validated.

### 9.6. RuntimeConfigController.java

~~~java
package example.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeConfigController {
    private final AppSettings settings;

    public RuntimeConfigController(AppSettings settings) {
        this.settings = settings;
    }

    @GetMapping("/api/runtime-config")
    public Map<String, Object> currentConfig() {
        return Map.of(
                "mode", settings.mode(),
                "requestTimeoutMs", settings.requestTimeout().toMillis()
        );
    }
}
~~~

This is a learning endpoint returning only two non-sensitive values. In real deployments, do not create endpoints that arbitrarily expose configuration, especially secrets and internal network details.

### 9.7. Running with Configuration in the File

On Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Once the application binds port 8080 successfully, run in another terminal:

~~~bash
curl -i http://localhost:8080/api/runtime-config
~~~

Expected HTTP response is 200, with a body containing two fields and values equivalent to:

~~~json
{"mode":"local","requestTimeoutMs":2000}
~~~

JSON key order is not guaranteed; what matters are the values. If the server fails to start, inspect exceptions and logs before calling the endpoint.

### 9.8. Running the Same Artifact with Environment Variables

Build first:

~~~bash
./gradlew test
./gradlew bootJar
~~~

Then run on Linux/macOS:

~~~bash
SERVER_PORT=9090 APP_MODE=staging APP_REQUESTTIMEOUT=5s java -jar build/libs/server-config-demo-1.0.0.jar
~~~

Call:

~~~bash
curl -i http://localhost:9090/api/runtime-config
~~~

Expect HTTP 200 and JSON with mode=staging, requestTimeoutMs=5000. application.yml did not need editing. SERVER_PORT overrode server.port=8080 from inside the JAR.

### 9.9. Running the Same Artifact with Command-Line Arguments

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9191 --app.mode=cli --app.request-timeout=3s
~~~

After the server starts successfully:

~~~bash
curl -i http://localhost:9191/api/runtime-config
~~~

Expect HTTP 200, mode=cli, and requestTimeoutMs=3000. This approach does not rebuild the JAR; it only changes the values supplied at launch.

### 9.10. Combining All Three Sources

Keep the default YAML file as above and export variables:

~~~bash
export SERVER_PORT=9090
export APP_MODE=staging
~~~

Then run:

~~~bash
java -jar build/libs/server-config-demo-1.0.0.jar --server.port=9191
~~~

The effective port is 9191 because CLI overrides the environment variable; app.mode remains staging because CLI did not override that key. requestTimeout still reads 2s from YAML if no higher-precedence source sets it.

This is a **per-key override** mechanism, not a replacement of the entire YAML file by one environment variable. Keys not overridden retain values from lower-precedence sources.

### 9.11. Testing AppSettings Binding

File src/test/java/example/web/AppSettingsTest.java:

~~~java
package example.web;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "app.mode=test",
        "app.request-timeout=7s",
        "server.port=0"
})
class AppSettingsTest {

    @Autowired
    AppSettings settings;

    @Test
    void bindsPropertiesFromTestConfiguration() {
        assertEquals("test", settings.mode());
        assertEquals(Duration.ofSeconds(7), settings.requestTimeout());
    }
}
~~~

This test verifies configuration binding when the Spring ApplicationContext initializes. server.port=0 here is an illustrative setting and does not prove the test opens a real HTTP port because @SpringBootTest uses a mock web environment by default. To test a real HTTP server, use webEnvironment=RANDOM_PORT and an HTTP client in the test.

Run:

~~~bash
./gradlew test
~~~

In CI/CD, consider also running tests for missing/invalid config and startup tests for critical profiles to catch config drift before deployment.

## 10. When to Use @Value, Environment, or @ConfigurationProperties?

### @Value: Injecting an Individual Value

Illustrative code snippet inside a Spring Bean:

~~~java
@Value("${app.mode:local}")
private String mode;
~~~

The colon after the property name sets a fallback value. This is concise, but when many properties are related, they get scattered across classes and validation becomes harder to manage.

### Environment: Querying Directly

Inside a Spring Bean you can inject Environment and call:

~~~java
String port = environment.getProperty("server.port", "8080");
~~~

This illustrates an injected environment variable of type org.springframework.core.env.Environment. It reads a property by key with a fallback; it is not the way to get the actual bound HTTP port when using server.port=0. For random ports, retrieve the actual local server port via the appropriate API.

### @ConfigurationProperties: Structured Configuration Groups

For multiple related fields, @ConfigurationProperties is usually more suitable. Benefits include type-safe binding, support for enums/Duration/DataSize, validation, and easier testing. The AppSettings record in Section 9 shows the app.* group bound once and injected into the controller.

Practical design rules:

- Name groups clearly, e.g., app.http-client or app.features.
- Use meaningful types: Duration for timeouts, DataSize for byte sizes, boolean for flags.
- Define intentional defaults; never set unsafe defaults for mandatory secrets.
- Validate required constraints.
- Avoid scattering hard-coded string lookups for individual properties everywhere.
- Distinguish Spring Boot settings (server.*) from custom application settings (app.*).

## 11. Relaxed Binding and Property Naming Mistakes

Spring Boot allows binding several spelling variants such as kebab-case, camelCase, underscore, and uppercase environment variable names. However, do not assume every variant is equivalent in every situation.

Example canonical property:

~~~properties
app.request-timeout=5s
~~~

Environment variable per official rules:

~~~bash
export APP_REQUESTTIMEOUT=5s
~~~

Common mistakes:

- Manually replacing dashes with underscores and assuming APP_REQUEST_TIMEOUT is definitely the equivalent name; under canonical-to-OS-environment conversion, dashes must be **removed**.
- Confusing app.request-timeout with server.connection-timeout or an HTTP client's timeout; these keys control different components.
- Using keys with dots in Linux shell variable names, making export invalid.
- Using inconsistent variable names across Docker, Kubernetes, CI/CD, and local environments.
- Inventing an alias like PORT while forgetting to configure the corresponding placeholder in the file.
- Passing malformed booleans or Durations, causing startup binding errors.

For map or list properties, environment variable naming rules are more intricate; consult the official documentation when configuring server lists, endpoints, or map keys. For Maps populated from environment variables, keys may be lowercased, so avoid depending on case-sensitive keys when configuring via OS env.

## 12. Types and Units in Server Configuration

Spring Boot uses binding to convert text into Java types. Some embedded server settings are durations or numbers, though not every property uses the same unit or exists on every server.

Example general configuration:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Write explicit units for Duration when a property supports it, such as 500ms, 2s, or 20s. Do not guess that every timeout uses milliseconds; property names, versions, and types can define different default units.

For server.tomcat.*, server.jetty.*, server.undertow.*, or server.netty.*, verify which web stack/server is actually running. Setting a Tomcat property when the app actually runs Jetty does not turn it into a Jetty setting. In Spring Boot 4.x, Undertow is no longer an integrated embedded server in the same way as Boot 3.x; always check your version when relying on server-specific properties.

### 12.1. Changing Port and Bind Address

In container environments, the port Spring Boot binds must match container port, host port, ingress, or Service definitions. For example, SERVER_PORT=9090 makes the app try to bind port 9090; publishing a different port on the host is a Docker/Kubernetes setting independent of this property.

server.address can restrict the listening interface. Binding 127.0.0.1 inside a container usually prevents requests from outside the container from reaching the app even when ports are published. Check the actual address and network topology rather than looking only at server.port.

### 12.2. Port 0 in Testing

server.port=0 asks the operating system to pick a free port when the embedded server actually starts. This is useful to avoid port collisions in integration tests. However, the configured property value remains 0, while the actual port assigned after bind is another number; read the actual server port using the appropriate test/runtime API.

## 13. Using Files, Environment, and CLI in Containers/Kubernetes

At multi-environment scale, keeping a single immutable artifact improves version control and rollback. Configuration should be supplied at runtime.

Common mechanisms:

- Environment variables for simple values like profiles, ports, and feature flags.
- Config files mounted from a ConfigMap or volume when many structured properties are needed.
- Secret stores/Secret volumes for sensitive data like passwords, private keys, and tokens.
- Command-line arguments for intentional overrides in one-off jobs or short-lived operational scenarios.
- spring.config.import or configtree: so Spring Boot loads the mounted files.

Snippet of a Kubernetes manifest setting environment variables, assuming the container image already specifies the app startup command:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: "prod"
  - name: SERVER_PORT
    value: "8080"
  - name: APP_MODE
    value: "production"
ports:
  - name: http
    containerPort: 8080
~~~

This is a snippet of a container spec, not a complete Deployment YAML. A real manifest needs apiVersion, kind, metadata, spec, and other deployment fields. Readiness/liveness probes must also point to the actual port and path.

A mounted application-prod.yml can be located via spring.config.additional-location. If a required file is missing, startup should fail clearly instead of silently falling back to wrong production settings.

On each deployment, record the artifact version, non-sensitive configuration, active profile, and intentional config changes. Avoid editing ConfigMaps/Secrets ad hoc outside controlled processes so runtime state does not drift from deployment definitions.

## 14. Configuration Security

Externalized configuration separates config from artifacts, but does not automatically make every source secure.

- **Never commit real secrets** to application.yml, source code, documentation, or public test fixtures.
- **Avoid placing secrets in CLI arguments** when avoidable, as arguments can appear in command history, process inspection, or deployment logs.
- **Environment variables are not a secret vault.** They can still leak via dumps, logs, admin tools, or overly broad process inspection permissions.
- **Use the platform's secret management mechanism** with least-privilege access and rotation procedures.
- **Never dump the entire Environment over HTTP** or log all configuration at startup.
- **Restrict Actuator env/configprops** according to operational policy, since those endpoints can reveal key names or config metadata even when sensitive values are masked.
- **Validation and fail-fast** on mandatory settings prevent running in an insecure state.
- **Distinguish safe defaults** from convenient defaults; for instance, a missing production token should fail startup rather than filling in a sample token.

Allowing users to override config via --... is also an operational privilege worth controlling. Startup scripts, Helm charts, systemd units, and job definitions should be reviewed as part of infrastructure configuration.

## 15. How to Verify Effective Values at Startup

When configuration does not behave as expected, check in sequence:

1. Identify **which process actually started**: which JAR, exact launch command, and working directory.
2. Identify **active profiles**: prod, dev, test, or default.
3. List **all candidate configuration sources** for that key: packaged files, external files, env, -D, and --.
4. Check **key spelling** and environment mapping, especially names with dashes.
5. Check **paths and read permissions** of files, config location/import settings, and existence of profile-specific files.
6. Look for **binding/validation errors** in the stack trace if the ApplicationContext failed.
7. Read **embedded server logs** to confirm the actual bind address/port.
8. Send a **real HTTP request** to the expected port/path and verify status/body.

Spring Boot Actuator provides env and configprops endpoints for diagnostics when enabled and properly secured. They can show property sources and non-sensitive values depending on version capabilities. Never expose these endpoints publicly just to debug production.

The --debug flag prints the auto-configuration condition evaluation report; it does not necessarily print the exact provenance of every property. To see why a Bean was or wasn't created, read the condition report; to see why server.port has a given value, inspect property sources and effective configuration.

### 15.1. Example: Port Already in Use Error

If SERVER_PORT=9090 and another process is already listening on 9090, the application may fail to start. That is a port-bind error, not proof that Spring Boot ignored the environment variable.

How to tell apart:

- Logs show the application read port 9090 yet binding failed: resolve the port conflict.
- Logs show the server running on port 8080: check whether the env variable reached the process and whether a higher-precedence source exists.
- Server runs on port 9090 yet curl to localhost:9090 fails from another machine/container: check bind address, networking, port mappings, and firewalls.
- Server returns 404: check routes/context path; the connection to the server succeeded, so it is not a port-bind issue.

## 16. Common Troubleshooting Table

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| application-prod.yml has no effect | prod profile not active or file in wrong location | Check SPRING_PROFILES_ACTIVE, working directory, and config locations |
| Set SERVER_PORT yet another port is used | Variable did not reach process, CLI/-D override, or wrong key name | Check launch command, process environment, and precedence |
| spring.config.location drops JAR defaults | location replaces default paths | Use additional-location if you only want to supplement |
| Missing file causes startup failure | Required config missing or lacks read permissions | Supply correct path/permissions; use optional: only when truly optional |
| application.yml fails to parse | Wrong YAML indentation or unquoted special characters | Check YAML syntax and the reported line |
| app.request-timeout binding fails | Value cannot convert to Duration | Use explicit unit like 5s; read cause in stack trace |
| @ConfigurationProperties not injected | Class not registered via scan/enable or package outside scan scope | Check @ConfigurationPropertiesScan, package, and Bean registration |
| Changed env var yet running app keeps old value | Process started with previous environment | Restart properly; do not expect automatic live refresh |
| CLI has --server.port yet does not override | Wrong syntax or app disabled addCommandLineProperties | Check arguments and SpringApplication bootstrap |
| Docker publishes port yet app unreachable | Container port differs from server.port, wrong bind address, or routing bug | Align port mapping and verify actual listener |
| Secret appears in logs | Printing Environment/configprops or sensitive debug logging | Remove log statements; protect secrets and rotate if exposed |
| Profile value differs from expectations | Multiple profiles/locations define the key | Verify effective source and config data order |

## 17. Configuration Design Rules for a Web Application

A maintainable strategy:

1. Put safe, environment-agnostic defaults in application.yml inside the artifact.
2. Group application-specific properties under a clear prefix like app.*.
3. Use @ConfigurationProperties for configuration groups with types, validation, and clear documentation.
4. Use environment variables for simple overrides, consistently across containers/CI/CD.
5. Use external files or ConfigMaps when a config group has many fields or should be managed as a unit.
6. Use secret managers or mounted secrets for credentials; never store secrets in version control.
7. Use CLI overrides intentionally for single-run adjustments; avoid letting ad-hoc manual flags become production standards.
8. Explicitly define profiles, working directories, external config paths, and mandatory keys.
9. Test startup with critical profiles and run HTTP tests for server settings.
10. Record non-sensitive configuration and deployment versions, keeping fast rollback possible.

Team responsibilities stay cleaner when the application owns the schema and validation for app.*, while the deployment system owns environment-specific values. Regardless of where values come from, the application must validate inputs itself and prevent unsafe configurations from reaching runtime.

## 18. Comprehensive Hands-On Exercise

Goal: demonstrate that one Spring Boot JAR can accept configuration from all three channels and explain precedence.

**Step 1:** Build the project from Section 9; run using application.yml. Verify server.port=8080, mode=local, and requestTimeoutMs=2000.

**Step 2:** Set SERVER_PORT=9090 and APP_MODE=staging. Re-run the JAR and verify the URL changes to localhost:9090 and mode=staging.

**Step 3:** Keep the env from Step 2 and add --server.port=9191. Verify port 9191 beats the environment variable while mode stays staging.

**Step 4:** Add -Dapp.mode=jvm before -jar, without passing --app.mode. Verify mode=jvm because JVM system properties outrank OS env.

**Step 5:** Pass --app.mode=cli alongside -Dapp.mode=jvm. Verify mode=cli because command-line arguments outrank JVM system properties.

**Step 6:** Create application-prod.yml, activate the prod profile, and observe that only defined keys change values; remaining keys can still come from application.yml.

**Step 7:** Test spring.config.additional-location with an external config directory. Check whether new keys override defaults as expected, then compare with spring.config.location to explain the difference.

**Step 8:** Remove app.request-timeout from all required config sources in a test run and observe the binding/validation error. Restore it before continuing.

**Step 9:** Test server.port=0 in a real integration test, record the actual allocated port, and compare it against the configured property value.

**Step 10:** Summarize the results in a table showing source, launch command, active profile, actual server.port, app.mode, requestTimeoutMs, HTTP status, and an explanation of precedence.

The exercise is complete when you have log/HTTP evidence for each run, can predict the resolved values from sources, and do not need to edit or rebuild source code to change port/mode.

## 19. Self-Check

1. Why can the same JAR run on multiple ports?
2. How does Spring Environment differ from a single application.yml file?
3. When both a file and SERVER_PORT declare server.port, which source normally has higher precedence?
4. If both --server.port=9191 and -Dserver.port=9095 are passed, which port is normally chosen? Why?
5. Why must -Dserver.port appear before -jar?
6. How does spring.config.location differ from spring.config.additional-location?
7. Why does the working directory matter when searching for files outside the JAR?
8. Under what condition is application-prod.yml loaded?
9. By what rule does app.request-timeout map to an environment variable name?
10. When should you use @Value, Environment, or @ConfigurationProperties?
11. Why does changing an environment variable not automatically change the HTTP port of an already-running process?
12. When receiving a port-bind error, how do you distinguish wrong configuration from an already-occupied port?
13. Why do secrets in CLI arguments or environment variables still require protection policies?
14. Why does a default @SpringBootTest not prove the embedded server is listening on a real port?
15. If a Kubernetes Service targets port 8080 while the application binds 9090, which configurations need inspection?

## Official References

- [Spring Boot 3.3 – Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 – Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)
- [Spring Boot 3.3 – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Boot – Current Externalized Configuration Reference](https://docs.spring.io/spring-boot/reference/features/external-config.html)

Use the documentation matching your running version to confirm source ordering, supported settings, and bootstrap behavior before applying changes to production.