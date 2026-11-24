# Changing dependencies, properties, or beans and verifying configuration changes

Spring Boot automatically configures an application based on what is present on the classpath, active properties, and beans declared by the application. Therefore, when you **change dependencies, modify properties, or provide a custom bean**, the set of applied auto-configurations can change accordingly.

For example:

- Adding the Spring Security starter can cause HTTP requests to be secured under default configuration.
- Changing `server.port` makes the embedded web server listen on a different port.
- Declaring your own `DataSource` can cause the default datasource auto-configuration to back off.
- Removing a library from the classpath can cause auto-configurations depending on that library to no longer match.

However, merely inspecting config files or seeing the application start cleanly is not enough to know a change took effect. You must verify across multiple layers: **whether dependencies resolved, whether effective properties loaded, which conditions matched, which beans were registered, and whether runtime behavior changed as expected**.

## 1. Three common ways to customize auto-configuration

Spring Boot provides defaults so applications start quickly. When you need to alter behavior, you usually start from one of three points:

| Point of change | What do you change? | How can auto-configuration react? |
| --- | --- | --- |
| Dependency | Add, remove, or replace libraries on the classpath | `@ConditionalOnClass`, `@ConditionalOnMissingClass`, and related conditions may match differently |
| Property | Change values in `application.properties`, YAML, environment variables, or run arguments | `@ConditionalOnProperty` and configurations reading `Environment` may take a different branch |
| Bean | Declare a bean yourself in the application context | `@ConditionalOnBean` or `@ConditionalOnMissingBean` may change results; custom bean can replace default role |

```text
                Application change
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Dependency   Property       Bean
          |            |            |
          v            v            v
       Classpath    Environment   Bean registry
          |            |            |
          +------------+------------+
                       |
                       v
              Evaluate conditions
                       |
                       v
            Auto-configuration changes
                       |
                       v
               New bean definitions
                       |
                       v
               New runtime behavior
```

These three points can combine. For instance, adding the Data JPA starter puts JPA libraries onto the classpath, datasource properties supply connection info, and a custom `DataSource` bean can replace default configuration. Each change acts on a different part of the configuration process.

## 2. Changing dependencies: the classpath alters conditions

Spring Boot can check whether a class or library is on the classpath. Auto-configurations commonly use conditions such as:

```java
@ConditionalOnClass(SomeLibrary.class)
@ConditionalOnMissingClass("com.example.legacy.LegacyClient")
```

When adding or removing dependencies, the outcome of classpath conditions can change.

### 2.1. Adding a starter to enable a feature group

For example, an application needs Spring MVC to build a REST API. In a Spring Boot 3.x project using Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Or Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

These examples assume the project already uses Spring Boot dependency management (parent/BOM or matching plugin), so starter versions are managed centrally.

Once the dependency resolves, the classpath contains the required web components. Spring Boot can select MVC and web server configurations suited to the classpath and other conditions.

A simple controller:

```java
package com.example.demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello";
    }
}
```

If the application has Spring MVC, component scan covers the controller package, and the web server starts successfully, the endpoint can be called at:

```text
GET http://localhost:8080/hello
```

Simply adding the starter does not create controllers on its own. The dependency provides infrastructure; the application still has to declare endpoints and start an appropriate context.

### 2.2. Removing a dependency can cause auto-configuration to stop matching

Suppose the application previously had the Web starter. When removing the starter from the build file:

```groovy
dependencies {
    // Removed spring-boot-starter-web
}
```

Spring MVC or embedded servlet server classes may no longer be on the runtime classpath. Auto-configurations depending on them can be skipped.

Consequences to distinguish:

- The application may still start as a non-web application.
- Controller classes may no longer be handled as MVC endpoints.
- Other beans can still be registered if they do not depend on the web stack.
- If code directly references removed classes, compilation may fail before the application runs.

Do not expect removing a dependency to drop only one endpoint while leaving everything else unchanged. Check the dependency tree and condition report to know exactly which configurations are affected.

### 2.3. Swapping the embedded web server

In a Spring Boot 3.x servlet application, `spring-boot-starter-web` usually pulls in Tomcat as the default embedded web server. To use Jetty instead, exclude Tomcat and add the matching Jetty starter:

**Gradle:**

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

**Maven:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

This is an example following common Spring Boot 3.x starter organization. Artifact names and configuration may differ in other release lines; use coordinates supported by your project version's documentation.

After swapping dependencies, verify:

1. The Tomcat starter is no longer in the runtime dependency tree.
2. The Jetty starter and related modules resolved.
3. The application starts with the expected web server.
4. Actual HTTP requests are still handled.

Changing the server does not necessarily change controller code. It swaps the infrastructure component accepting and processing HTTP connections.

### 2.4. Adding Data JPA requires adding a database driver

The Data JPA starter provides Spring Data JPA, Hibernate, and integration components. However, it does not automatically supply every JDBC driver for every database.

Example using PostgreSQL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

You then need connection configuration:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_user
spring.datasource.password=${DB_PASSWORD}
```

If you add Data JPA without a JDBC driver, database server, or connection details, the application may fail to start. Auto-configuration needs satisfied conditions to create a `DataSource`, and the datasource needs to connect to the database.

### 2.5. Inspecting how dependencies changed

**Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To inspect why a specific dependency appears:

```bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
```

**Maven:**

```bash
./mvnw dependency:tree
```

Filter by artifact:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
```

On Windows, use `gradlew.bat` or `mvnw.cmd`; in PowerShell you may need to quote `-D...` arguments:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.boot:spring-boot-starter-tomcat"
```

The dependency tree shows what the build tool resolved. It does not prove auto-configuration matched; that is a separate verification step.

## 3. Changing properties: controlling configuration via the Environment

Many auto-configurations read properties to choose behavior. For example:

- `server.port` selects the web server port.
- `spring.datasource.*` configures the datasource.
- `spring.jpa.*` adjusts JPA/Hibernate behavior.
- `management.endpoints.web.exposure.include` controls which Actuator endpoints are exposed over HTTP.
- Custom application properties can enable/disable a feature.

### 3.1. Changing the web server port

In `application.properties`:

```properties
server.port=8081
```

After restarting the application, the web server will use port 8081 if the configuration applies and that port is available.

Verify:

```bash
curl -i http://localhost:8081/hello
```

If you still call port 8080, you may get a connection error or reach a different process. Check startup logs to confirm the actual port.

### 3.2. Changing properties via the command line

Spring Boot allows passing application arguments at startup:

```bash
java -jar build/libs/demo.jar --server.port=8082
```

Or using Gradle:

```bash
./gradlew bootRun --args='--server.port=8082'
```

With Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=8082
```

Maven argument-passing syntax may need adjustment depending on plugin version and shell; in an IDE, placing `--server.port=8082` in the **Program arguments** field is straightforward.

Command-line properties typically take higher precedence than properties in configuration files. Thus, if `application.properties` specifies 8080 while the command line passes 8082, the effective value can be 8082.

### 3.3. Using environment variables

The `server.port` property can be mapped from the `SERVER_PORT` environment variable.

**Linux/macOS:**

```bash
SERVER_PORT=8083 java -jar build/libs/demo.jar
```

**Windows PowerShell:**

```powershell
$env:SERVER_PORT = "8083"
java -jar build/libs/demo.jar
```

After running, check startup logs and call the right port. Environment variables are useful when the same artifact must run across multiple environments without modifying configuration files inside the JAR.

### 3.4. Profiles change which set of properties is loaded

You can create:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

`application.properties`:

```properties
spring.application.name=shop
server.port=8080
```

`application-dev.properties`:

```properties
server.port=8081
logging.level.com.example.demo=DEBUG
```

`application-prod.properties`:

```properties
server.port=8080
logging.level.root=INFO
```

Activate a profile:

```properties
spring.profiles.active=dev
```

Or via an environment variable:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
```

When the `dev` profile is active, Spring Boot loads the corresponding additional configuration. Specific properties can override shared values per Spring Boot's property source rules.

A profile does not automatically create a bean unless the bean is declared conditionally. For example, `@Profile("dev")` on a configuration class or bean method directly decides that the bean is registered only in that profile.

### 3.5. When do properties take effect?

Most auto-configurations are evaluated during application context startup. Therefore, when changing properties controlling conditions or infrastructure, the simplest and most predictable approach is to **restart the application**.

Some properties can be read at runtime by components querying `Environment` on each execution. However, do not assume every property automatically updates already-created beans when a configuration file changes. Dynamic configuration requires an appropriate refresh/configuration mechanism and knowing which beans support updates.

## 4. Changing beans: letting auto-configuration back off

An important pattern in Spring Boot is auto-configuration providing a default bean while allowing the application to define a replacement bean itself.

For example:

```java
@AutoConfiguration
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

If the application already provides a matching `Clock` bean and that bean is processed before auto-configuration, `@ConditionalOnMissingBean` can prevent the default bean from being registered.

### 4.1. Declaring your own bean to replace the default

In the application:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

When auto-configuration is ordered properly, the `businessClock` bean causes the missing-`Clock` condition to no longer match. Spring Boot yields control to the application configuration.

This is the standard customization approach without needing bean definition overriding enabled. The custom bean can have a different name from the default bean; the condition checks by the `Clock` type in this example.

### 4.2. Distinguishing type-based and name-based conditions

The two annotations below check different things:

```java
@ConditionalOnMissingBean(Clock.class)
```

```java
@ConditionalOnMissingBean(name = "appClock")
```

- The first checks for a matching bean by type `Clock`.
- The second checks for a bean named `appClock`.

If the application has a `Clock` bean named `businessClock`, the type-based condition causes the default configuration to back off; the name-based condition can still match if no bean named `appClock` exists.

Choose conditions matching the exact contract the auto-configuration intends to provide.

### 4.3. Replacing a default bean with `@Primary` or `@Qualifier`?

Suppose the application has two beans with different names:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean
    public Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean
    @Primary
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

If a service injects `Clock` without specifying a qualifier, `businessClock` is the primary candidate in normal scenarios.

To specify explicitly:

```java
public ReportService(@Qualifier("utcClock") Clock clock) {
    this.clock = clock;
}
```

`@Primary` and `@Qualifier` solve **bean selection when multiple candidates exist**. They are not mechanisms for disabling auto-configuration. To prevent a default bean from being registered, use an appropriate condition such as `@ConditionalOnMissingBean`.

### 4.4. Bean overriding is not the default solution

The property:

```properties
spring.main.allow-bean-definition-overriding=true
```

allows a later-registered bean definition to replace a definition with the same name in the registry where applicable. This is not the preferred way to customize auto-configuration.

Prefer in order:

1. Supplying your own bean per the contract supported by auto-configuration.
2. Using `@ConditionalOnMissingBean` in library auto-configurations.
3. Changing bean names if multiple implementations need to coexist.
4. Using `@Primary` or `@Qualifier` when selecting one bean among multiple candidates.
5. Using overriding only when you have explicitly identified the bean name, registration source, and reason for replacing the definition.

## 5. Changing configuration by excluding an auto-configuration

Sometimes an application does not want a specific auto-configuration to apply. Spring Boot supports excluding via `exclude`, `excludeName`, or properties.

### 5.1. Excluding by class

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

This example excludes `DataSourceAutoConfiguration` from the auto-configuration process. If the application still has a service that strictly requires `DataSource`, it may fail to start.

### 5.2. Excluding by class name

```java
@SpringBootApplication(
    excludeName = {
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
    }
)
public class DemoApplication {
}
```

`excludeName` is helpful when specifying a class name without importing that class directly in source code.

### 5.3. Excluding by property

```properties
spring.autoconfigure.exclude=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

When excluding multiple configurations, declare a list of names in the appropriate property format.

### 5.4. When should you exclude?

Exclude only when you know which configuration is being applied and why it does not fit. For example, the application uses no database yet an optional dependency causes datasource configuration to be evaluated; or the application wants to configure a piece of infrastructure manually in its own way.

Excluding an auto-configuration does not automatically delete all beans with the same function. Beans can still come from component scan, `@Import`, another configuration class, or another library.

## 6. Verifying dependency changes

When changing dependencies, check in two steps: the build tool resolves the right libraries, and the application actually runs with the desired runtime classpath.

### 6.1. Gradle

List runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Check why an artifact appears:

```bash
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath
```

Verify a dependency was excluded:

```bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
```

If the dependency is not found, that may be the expected result after exclusion. If the dependency still appears via another transitive path, examine the dependency paths in the output.

### 6.2. Maven

```bash
./mvnw dependency:tree
```

Filter a single artifact:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
```

Inspect conflicted or excluded dependencies:

```bash
./mvnw dependency:tree -Dverbose
```

`-Dverbose` displays dependencies omitted by mediation rules. Do not look at just one artifact line; check versions and dependency paths to see why it is present.

### 6.3. A successful build is not enough

A successful build proves source code and dependencies passed the executed build steps. It does not prove:

- Desired auto-configurations matched.
- Desired beans were registered.
- Databases or external services are reachable.
- HTTP endpoints work.
- The application is running with the right profile/port.

After dependency changes, continue verifying the condition report, application context, and runtime behavior.

## 7. Verifying properties took effect

### 7.1. Inspecting startup logs

For web applications, logs can show which port the server started on:

```text
Tomcat started on port 8081 (http) with context path '/'
Started DemoApplication ...
```

Exact messages depend on the web server and version. With WebFlux, the server may be Netty; with non-web applications, there is no embedded HTTP server.

Startup logs are a useful signal, though combine them with real requests.

### 7.2. Calling endpoints to confirm

If the `/hello` endpoint is declared:

```bash
curl -i http://localhost:8081/hello
```

Check status code and body. If the server started on port 8081 yet the endpoint returns `404`, the port property took effect while component scanning or mapping may be misconfigured.

### 7.3. Checking properties in `Environment`

In a bean created after context startup, you can read the value:

```java
@Component
public class RuntimeConfigurationReporter {

    private final Environment environment;

    public RuntimeConfigurationReporter(Environment environment) {
        this.environment = environment;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void report() {
        Integer port = environment.getProperty(
                "server.port",
                Integer.class
        );
        System.out.println("Configured server.port = " + port);
    }
}
```

This example prints the property supplied by `Environment`. If `server.port` is not explicitly declared, a direct read may return `null` even though the web server uses its default port. To observe the actual port, check web server startup logs or appropriate web server configuration.

`Environment` shows the property value after property sources are combined; it does not by itself prove every bean consumed that value.

## 8. Verifying auto-configuration with the Condition Evaluation Report

Spring Boot can print a report indicating which auto-configurations matched or did not match.

### 8.1. Enabling debug mode

You can pass the argument:

```text
--debug
```

Gradle example:

```bash
./gradlew bootRun --args='--debug'
```

Or configure:

```properties
debug=true
```

Spring Boot can print the **Condition Evaluation Report**, including:

- **Positive matches:** configurations whose conditions matched.
- **Negative matches:** skipped configurations and reasons.
- **Exclusions:** excluded configurations.
- **Unconditional classes:** configurations not governed by ordinary conditions.

The output is diagnostic information about auto-configuration. It is not a list of every bean instance in the application context.

### 8.2. Comparing reports before and after changes

For example, when adding the Spring Security starter:

1. Run the application before the change with `--debug` and save security-related matches.
2. Add the Security starter and sync dependencies.
3. Run again with the same profile and properties.
4. Compare security-related conditions.
5. Try hitting an endpoint to confirm actual protection behavior.

One dependency change can cause multiple conditions to match differently. Do not search for just one auto-configuration name; inspect related classpath and bean conditions.

### 8.3. Distinguishing condition match from bean creation

An auto-configuration class matching does not mean every bean method in the class creates a bean. Each method can have its own conditions:

```java
@AutoConfiguration
@ConditionalOnClass(ReportClient.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "reports",
        name = "enabled",
        havingValue = "true"
    )
    ReportService reportService(ReportClient client) {
        return new ReportService(client);
    }
}
```

The class can be considered when `ReportClient` is present, yet the `ReportService` bean is registered only if the property matches and required dependencies resolve.

## 9. Verifying actual beans in the application context

After the context starts, you can inspect beans by name or type.

### 9.1. Checking beans by type

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

String[] names = context.getBeanNamesForType(Clock.class);
System.out.println(Arrays.toString(names));
```

If the application has one `Clock` bean, the output can be:

```text
[businessClock]
```

If multiple `Clock` beans exist, all matching names may appear. This method helps verify matching bean definitions/beans by type in the context; do not conclude only one bean exists merely because one name appeared in another log.

### 9.2. Checking beans by name and runtime type

```java
Clock clock = context.getBean("businessClock", Clock.class);
System.out.println(clock.getClass().getName());
```

If the bean is wrapped in a proxy, the runtime class may differ from the implementation class. For simple beans like `Clock`, proxies are usually unnecessary; for AOP, transactions, or scoped beans, keep this difference in mind.

### 9.3. Counting beans by type

```java
Map<String, Clock> clocks = context.getBeansOfType(Clock.class);
System.out.println("Clock beans: " + clocks.keySet());
```

`getBeansOfType` can trigger bean instantiation in some situations. Use it once the context is ready for diagnostics, not arbitrarily inside conditions or early configuration registration.

### 9.4. Verifying the replacement bean is actually used

Do not just check that the bean exists; confirm the service receives the intended implementation:

```java
@Service
public class ReportService {
    private final Clock clock;

    public ReportService(@Qualifier("businessClock") Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

If the goal is to use `businessClock`, verify qualifiers and business output. A bean can exist while the service injects a different bean if bean selection is misconfigured.

## 10. Using Spring Boot Actuator to observe runtime

Actuator provides management and observability endpoints for the application. When adding the appropriate Actuator starter, you can use endpoints such as:

- `health`: health indicator status.
- `beans`: list of beans in the application context.
- `conditions`: condition evaluation report.
- `env`: environment/property source details (requires exposure and security configuration).
- `configprops`: beans bound from `@ConfigurationProperties`.

Example dependency in Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Configure HTTP exposure for selected endpoints:

```properties
management.endpoints.web.exposure.include=health,beans,conditions,configprops
```

Then, in an appropriate environment, you can access:

```text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/beans
http://localhost:8080/actuator/conditions
http://localhost:8080/actuator/configprops
```

Available endpoints depend on dependencies, versions, web stack, and exposure settings. Sensitive endpoints may be restricted or require authentication. Do not expose `env`, `configprops`, or sensitive management endpoints publicly in production without proper security and data sanitization.

### 10.1. `/actuator/conditions`

The `conditions` endpoint is helpful for viewing auto-configuration conditions in a running context. It answers:

- Which configurations matched?
- Which configurations did not match?
- Which property or classpath conditions decided?

The endpoint output is structured JSON. It complements `--debug` logs, especially when inspecting an already-started application.

### 10.2. `/actuator/beans`

The `beans` endpoint shows bean definitions/beans Actuator can report in the context. Use it to inspect bean names, types, and dependency relationships at the level provided by the endpoint.

It does not replace debuggers or tests for confirming that a service actually invokes the expected implementation.

## 11. Verifying automatically with tests

Manual checks are helpful while exploring, whereas tests confirm repeatable behavior after every dependency or property change.

### 11.1. `@SpringBootTest` checking the application context

For example:

```java
@SpringBootTest(
    properties = {
        "features.reports.enabled=true"
    }
)
class ReportFeatureEnabledTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void registersReportServiceWhenFeatureIsEnabled() {
        assertThat(context.containsBean("reportService")).isTrue();
    }
}
```

This test assumes `ReportConfiguration` supplies a bean named `reportService` when the property is enabled and all application dependencies can initialize. If the bean has another name, check the actual name or check by type.

### 11.2. Checking when the property is disabled

```java
@SpringBootTest(
    properties = {
        "features.reports.enabled=false"
    }
)
class ReportFeatureDisabledTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void doesNotRegisterReportServiceWhenFeatureIsDisabled() {
        assertThat(context.containsBean("reportService")).isFalse();
    }
}
```

If another bean also carries the name `reportService`, the test needs to narrow the context or use a more specific name/type to avoid false conclusions.

### 11.3. `ApplicationContextRunner` testing standalone auto-configuration

`ApplicationContextRunner` is very useful when developing auto-configurations. It creates a lightweight context, allowing you to set properties and import configurations under test without booting the entire application.

For example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ReportAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportAutoConfiguration.class
                            )
                    );

    @Test
    void createsReportServiceWhenEnabled() {
        contextRunner
                .withPropertyValues("reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportService.class);
                });
    }

    @Test
    void backsOffWhenDisabled() {
        contextRunner
                .withPropertyValues("reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportService.class);
                });
    }
}
```

This is an illustrative example for a standalone auto-configuration with `@ConditionalOnProperty`. `ReportAutoConfiguration` and `ReportService` classes must exist in the project; the test requires Spring Boot Test, JUnit, and AssertJ dependencies.

### 11.4. Checking that a default bean backs off

Suppose auto-configuration creates `SearchClient` if the application does not have one yet:

```java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

Test without a custom bean:

```java
@Test
void createsDefaultClientWhenNoCustomClientExists() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(SearchAutoConfiguration.class)
            )
            .run(context -> {
                assertThat(context).hasSingleBean(SearchClient.class);
                assertThat(context.getBean(SearchClient.class))
                        .isInstanceOf(DefaultSearchClient.class);
            });
}
```

Test when the application supplies its own bean:

```java
@Test
void backsOffWhenApplicationProvidesCustomClient() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(SearchAutoConfiguration.class)
            )
            .withBean(
                    SearchClient.class,
                    () -> new CompanySearchClient()
            )
            .run(context -> {
                assertThat(context).hasSingleBean(SearchClient.class);
                assertThat(context.getBean(SearchClient.class))
                        .isInstanceOf(CompanySearchClient.class);
            });
}
```

The test proves `@ConditionalOnMissingBean` works as intended: auto-configuration supplies the default when needed, and backs off when the context already contains a custom bean.

## 12. Practical workflow: change and then verify

When changing a dependency, property, or bean, you can follow this workflow.

### Step 1 — Define the desired behavior

Write down clearly what must change:

```text
Before: application uses Tomcat, port 8080.
After: application uses Jetty, port 8081.
```

Or:

```text
Before: auto-configuration creates DefaultSearchClient.
After: application uses CompanySearchClient.
```

Without stating the desired outcome, it is difficult to choose the right dependency, property, or bean.

### Step 2 — Identify the layer to change

| Desired outcome | Layer to inspect |
| --- | --- |
| Add a library capability | Dependency |
| Toggle a feature per environment | Property/profile |
| Swap a default implementation | Custom bean and condition |
| Do not use a framework configuration | Auto-configuration exclusion |
| Select one among multiple beans | `@Qualifier` / `@Primary` |

Avoid changing multiple layers simultaneously unless necessary; changing dependencies, properties, and beans all at once makes it hard to tell which change produced the result.

### Step 3 — Make one controlled change

For example, change only the port:

```properties
server.port=8081
```

Or add only one bean:

```java
@Bean
SearchClient searchClient() {
    return new CompanySearchClient();
}
```

Keep other factors steady for easy comparison.

### Step 4 — Confirm the input actually changed

- Dependency: check the dependency tree.
- Property: check `Environment`, active profiles, and property sources.
- Bean: check scanned/imported configurations and bean name/type.

Do not jump to conclusions about auto-configuration before confirming whether the input change took effect.

### Step 5 — Inspect the condition report

Run with `--debug` or inspect `/actuator/conditions` if Actuator is properly configured. Determine which auto-configurations matched, did not match, or were excluded.

### Step 6 — Confirm bean definitions and bean instances

Use `ApplicationContext`, Actuator `/beans`, or tests to verify the intended beans. If multiple beans of the same type exist, verify qualifiers/primary and which bean the service actually receives.

### Step 7 — Verify external behavior

Call HTTP endpoints, run database queries, or execute business operations. Configuration matters only when runtime behavior meets the goal.

### Step 8 — Write tests to lock in the behavior

Create tests for property enabled/disabled, custom bean present/absent, or varying classpath dependencies. Tests prevent a future starter upgrade or property tweak from silently altering configuration.

## 13. Comprehensive example: customizing a search client

Suppose a library provides `SearchAutoConfiguration`:

```java
@AutoConfiguration
@ConditionalOnClass(SearchClient.class)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

There are three ways to alter behavior:

### 13.1. Disabling the feature via property

```properties
search.enabled=false
```

Expected outcome: the default bean is not registered from this configuration method.

Verification: run a context test with the property set to false and confirm no `SearchClient` comes from this configuration.

### 13.2. Removing the dependency containing `SearchClient`

If `SearchClient` is no longer on the classpath, the classpath condition prevents the auto-configuration from applying. However, if application code still directly references `SearchClient`, the build can fail due to the missing class.

Verification: dependency tree and condition report; also confirm source code no longer depends on the removed type.

### 13.3. Providing your own implementation

```java
@Configuration(proxyBeanMethods = false)
public class CompanySearchConfiguration {

    @Bean
    SearchClient searchClient() {
        return new CompanySearchClient();
    }
}
```

When the custom bean is registered before auto-configuration and satisfies the condition type, the default bean method "backs off".

Verification:

```java
assertThat(context).hasSingleBean(SearchClient.class);
assertThat(context.getBean(SearchClient.class))
        .isInstanceOf(CompanySearchClient.class);
```

These three cases yield distinct results: disabling a feature, removing integration capability from the classpath, and swapping an implementation. Distinguish them when diagnosing.

## 14. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Adding a starter makes features run automatically." | Starters supply dependencies; matching conditions, config, and app components are still needed |
| "Removing a dependency deletes only one bean." | It can cause multiple auto-configuration conditions to stop matching and break compilation |
| "Editing a property in a file updates running beans automatically." | Many configurations evaluate at startup; usually a restart or dedicated refresh mechanism is needed |
| "`@Primary` replaces auto-configuration." | It picks a candidate during injection; it does not stop default bean definitions from being registered |
| "`@ConditionalOnMissingBean` and overriding are the same." | The condition skips registering the default when a matching bean exists; overriding replaces same-name definitions when allowed |
| "The condition report lists every bean instance." | It explains auto-configuration conditional decisions |
| "The dependency tree proves auto-configuration matched." | It only shows resolved dependencies; the condition report is needed to verify configuration |
| "Application starting cleanly means properties took effect." | You must inspect effective values and runtime behavior |
| "Excluding an auto-configuration deletes every similar bean." | Beans can still be registered from other configurations or imports |
| "A custom bean always replaces every default bean." | It must match the type/name/condition and be registered at the right time |

## 15. Practice exercises

### Exercise 1 — Changing the port via property

Run a Spring Boot Web application on the default port. Change:

```properties
server.port=8081
```

Restart, check logs, and call the endpoint on port 8081. Then pass `--server.port=8082` via the command line.

**Question:** why can a command-line value beat a value in a configuration file?

### Exercise 2 — Adding and removing the Web starter

Create an application with a `/hello` controller. Inspect the dependency tree before and after adding the Spring Web starter. Then remove the starter and observe build/startup.

**Question:** what on the classpath relates to web auto-configuration being applied?

### Exercise 3 — Swapping the embedded server

In a Spring Boot 3.x project, exclude Tomcat and add Jetty following the example. Check the dependency tree to confirm the runtime server dependency. Start and send an HTTP request.

**Question:** why does the controller not need to change just because the web server changed?

### Exercise 4 — Default bean backing off

Create an auto-configuration providing a default `SearchClient` with `@ConditionalOnMissingBean`. Run the context without a custom bean, then add `CompanySearchClient`.

**Requirement:** write tests proving the default is registered in the first case and skipped in the second case.

### Exercise 5 — Disabling a feature via property

Create a `ReportService` bean registered only when `reports.enabled=true`. Write two context tests with true and false.

**Question:** if another service strictly injects `ReportService`, what happens when the feature is turned off? How can that dependency be made optional?

### Exercise 6 — Inspecting the Condition Evaluation Report

Run the application with `--debug` before and after adding a starter. Find one positive match and one negative match related to the new dependency.

**Requirement:** record the classpath/property/bean condition that decided the outcome.

### Exercise 7 — Using Actuator to inspect beans

Add Actuator and expose the `beans` and `conditions` endpoints in a local environment. Check whether the custom bean appears and whether default auto-configuration matched.

**Note:** expose only necessary endpoints in a learning environment; do not expose sensitive management info publicly.

## 16. Key takeaways

To customize Spring Boot auto-configuration, determine whether you need to change **the classpath, the Environment, or the bean registry**. Changing dependencies alters classpath conditions; changing properties affects configuration and `@ConditionalOnProperty`; declaring your own bean can cause default configuration to back off via `@ConditionalOnMissingBean`.

After making changes, verify layer by layer: the dependency tree confirms libraries, Environment confirms properties, the Condition Evaluation Report explains auto-configuration, the application context confirms beans, and tests/requests confirm behavior. Do not draw conclusions solely from the application starting without errors.

When you cleanly separate inputs, conditions, bean definitions, and runtime behavior, swapping starters, switching environments, or customizing implementations becomes much more predictable and controllable.
