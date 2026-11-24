# `Failed to load ApplicationContext` and the First Cause

`Failed to load ApplicationContext` is a general message indicating that Spring Test could not create or refresh the application context required to run a test. This is usually not the root cause. The actual cause lies in the nested exceptions underneath: a bean failed to be created, a dependency could not be found, a property is invalid, the database could not be reached, a migration failed, or an auto-configuration condition was not satisfied.

When encountering this error, find the first context initialization failure and follow the `Caused by` chain down to the exception that explains why Spring could not create the context. Do not start by randomly editing the test method or increasing timeouts: the test method was usually not even invoked because Spring failed during the bootstrap phase.

## At Which Stage Does This Message Appear?

The Spring TestContext Framework creates the `ApplicationContext` before executing any test that needs that context. The TestContext bootstrapper reads configuration, builds the context, refreshes the bean factory, and initializes the required singletons. If any required step fails, Spring throws an exception and the test stops before entering the test method body.

Common log example:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext

Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService'

Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'orderService':
Unsatisfied dependency expressed through constructor parameter 0

Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.store.PaymentGateway' available
```

The outermost exception is the bootstrap failure reported by Spring Test. The inner exceptions indicate which bean Spring was creating and which dependency was missing. In this example, changing the assertions on `orderService` will not help; the context cannot create the bean because `PaymentGateway` is missing.

Another case:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext

Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'entityManagerFactory'

Caused by: org.hibernate.exception.JDBCConnectionException:
Unable to obtain JDBC Connection

Caused by: org.postgresql.util.PSQLException:
Connection to localhost:5432 refused
```

Here, the initial failure does not lie in the entity mapping or test assertions. The database is not accepting connections at the configured endpoint. You need to check whether the database/container is ready, along with the URL, port mapping, credentials, and lifecycle of the test resources.

## How to Read the Exception Chain

A stack trace often has multiple layers of wrapped exceptions. Read them in the following order:

1. **Outermost message:** identify what the framework or test runner is reporting and which context is being initialized.
2. **`Caused by` exceptions:** find the bean name, constructor parameter, field, property, resource, or first meaningful failed operation.
3. **Low-level root exception:** if present, identify the specific system error such as connection refused, authentication failed, file not found, class not found, or SQL syntax error.
4. **First stack frame belonging to project code:** find the configuration, factory method, constructor, or `@Bean` method that triggered the error.

For example, a chain might go through `IllegalStateException` → `BeanCreationException` → `UnsatisfiedDependencyException` → `NoSuchBeanDefinitionException`. Inspect the entire chain, not just the last line. `BeanCreationException` usually indicates the bean being created; `UnsatisfiedDependencyException` points to the injection point; `NoSuchBeanDefinitionException` indicates the bean type with no matching candidate.

The deepest exception is not always the cause you need to fix first. A low-level exception can be a consequence of a misconfiguration at a higher layer, or a `BeanCreationException` may carry a clearer message than the final exception. Pick the first exception that explains the failed action, then confirm it using the bean name, property key, resource, or stack frame from your project code.

### Distinguishing the Root Cause from Wrapped Errors

Common exception types:

| Exception | Usually indicates |
|---|---|
| `IllegalStateException: Failed to load ApplicationContext` | TestContext could not create the context; this is usually a general wrapper |
| `BeanCreationException` | A bean could not be instantiated or complete lifecycle processing |
| `UnsatisfiedDependencyException` | A dependency could not be injected into a constructor, field, or method |
| `NoSuchBeanDefinitionException` | No bean matches the required type or qualifier |
| `NoUniqueBeanDefinitionException` | Multiple beans match and the injection point could not select a single one |
| `BeanDefinitionOverrideException` | Bean definitions have conflicting names and overriding is not allowed |
| `BeanCurrentlyInCreationException` | There may be a dependency cycle or an attempt to access a bean while it is still being created |
| `BindException` / `ConfigurationPropertiesBindException` | A property could not be bound to the expected configuration type |
| `PlaceholderResolutionException` / unresolved placeholder error | A `${...}` placeholder could not be resolved to a value |
| `DataAccessResourceFailureException` / JDBC exception | The database or data connection encountered an error |
| `FlywayException` / Liquibase exception | Migration or schema validation failed |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing class/dependency at runtime or out-of-sync test classpath |
| `NoSuchMethodError` / `AbstractMethodError` | Libraries are binary-incompatible across versions |

The exception name is a clue, not an automatic conclusion. Read the message, cause, and stack frames to learn where and why the exception was thrown.

## “First Cause” and the Spring Context Failure Threshold

Since Spring Framework 6.1, Spring TestContext includes a *context failure threshold* mechanism. By default, a context cache key is only attempted once. If the first attempt fails, subsequent tests requesting that exact same context key may be skipped without retrying initialization.

Logs on subsequent attempts may look like this:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context
```

This message is not the root cause. It states that Spring already knows the corresponding context initialization failed earlier and avoids repeating an expensive bootstrap attempt. Look for the full exception of the first failure in the test output, CI logs, or test runner report.

The default threshold value is `1`. It can be configured via a system property:

```text
-Dspring.test.context.failure.threshold=1
```

Example of increasing the threshold during diagnosis:

```text
-Dspring.test.context.failure.threshold=3
```

Increasing the threshold only allows Spring to retry more times for the same context cache key. It does not fix broken beans, properties, or infrastructure and is usually not the final solution. If the cause is a database that is not running, retrying multiple times may only produce extra logs and lengthen the test suite.

If the tests run on a Spring Framework version older than 6.1, this failure threshold message may not appear. Check the actual Spring Test version instead of assuming every project has this mechanism.

## Context Caching Causes Errors to Surface in Other Tests

Spring TestContext caches `ApplicationContext` instances so tests with equivalent configurations can share a context. The cache key is built from metadata such as configuration classes, context loader, initializers, active profiles, property sources, context customizers, parent context, and web resource path.

As a result, a single error can be observed across multiple test classes:

```text
OrderControllerTest       -> Failed to load ApplicationContext
OrderServiceIntegrationTest -> ApplicationContext failure threshold exceeded
PaymentFlowTest           -> ApplicationContext failure threshold exceeded
```

These classes may be requesting the same context cache key. The second and third test classes do not necessarily have independent errors; they may simply be receiving the cached failure state from the first attempt.

Identify which test class initialized that context key first. Check shared annotations and configurations, such as `@SpringBootTest`, `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, `@Import`, and nested test configurations. If a class uses a different property or profile, it can produce a different cache key and actually initialize its own context.

Do not rush to add `@DirtiesContext` to every test. That annotation removes the context from the cache at the specified phase, but it does not fix a broken configuration. If a bean is still missing or the database still cannot connect, the new context will fail as well.

## Ordered Diagnostic Workflow

### Step 1: Confirm the First Failure

Find the first occurrence of `Failed to load ApplicationContext` in the full log. Then locate the entire `Caused by` section associated with that occurrence. Do not look only at the summary at the end of Gradle/Maven output or at the failure threshold message from tests that ran later.

In CI, download the test report and raw task logs. A summary such as `Tests failed` or `ApplicationContext failure threshold exceeded` does not contain enough facts to draw a conclusion.

### Step 2: Identify the Context Being Loaded

Record the following metadata from the test class:

- Is it `@SpringBootTest` or `@ContextConfiguration`?
- Is `classes` specified? If not, in which package is the main configuration discovered?
- Are there `@ActiveProfiles`, `@TestPropertySource`, or inline `properties`?
- Are there `@DynamicPropertySource`, `@Import`, `@TestConfiguration`, or custom initializers?
- Is the web environment `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, or `NONE`?
- Does the test use a parent/child context, `@WebAppConfiguration`, or custom servlet configuration?

The context to diagnose is the one built from all of this metadata combined, not just from the test class name.

### Step 3: Find the First Bean or Resource That Failed

If the log reports `Error creating bean with name '...'`, locate that bean in your configuration or components. Check whether the bean is created via component scanning, a `@Bean` factory method, auto-configuration, or test configuration.

If the log names a constructor parameter or field, cross-check the dependency type, qualifier, and profile. If the error occurs inside a factory method, open that exact method to identify the failing operation.

If the log points to a property or resource, find where the property is declared and check its precedence across property sources. If the failure is in a datasource, broker, or HTTP client, verify the endpoint against the actual configuration received by the test context.

### Step 4: Categorize the Root Cause

Grouping the failure helps narrow down where to check first:

| Category | Symptoms | Where to check first |
|---|---|---|
| Main configuration | `@SpringBootConfiguration` not found, multiple candidates | Test package, `classes`, Boot configuration structure |
| Component scan/import | Missing service, repository, or configuration bean | `@SpringBootApplication`, `@ComponentScan`, `@Import`, package boundary |
| Dependency injection | `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException` | Constructor/field injection, `@Qualifier`, `@Primary`, profile |
| Dependency cycle | `BeanCurrentlyInCreationException` | Dependency chain across constructors and factory methods |
| Property binding | Invalid value, unresolved placeholder, bind failure | `application*.yml`, environment, inline properties, `@ConfigurationProperties` |
| Database | Connection refused, authentication failed, SQL/migration error | Container readiness, URL, port, credentials, driver, schema, and migrations |
| Messaging/cache/search | Timeout, connection refused, incompatible protocol | Broker/service lifecycle, mapped port, credentials, client version |
| Web server | Port in use, servlet context initialization failure | `webEnvironment`, `server.port`, filter/servlet registration |
| Classpath/version | `NoClassDefFoundError`, `NoSuchMethodError` | Dependency tree, BOM, and Spring/Boot/library versions |
| Bean initialization side effect | Constructor or `@PostConstruct` calls an external service | Initialization logic, network access, test profile, and readiness |

### Step 5: Change One Cause at a Time and Re-run Related Tests

Once you have a concrete hypothesis, change one configuration setting or dependency at a time. Run the test class that failed first to see whether the context can initialize. Once the context initializes, run the other tests sharing the same context key to confirm the propagated failure is gone.

Do not change profiles, database settings, component scanning, and mock configurations simultaneously. When multiple variables change at once, it is very hard to tell what actually fixed the issue.

## Common Root Cause Categories

### Application Configuration Not Found

With `@SpringBootTest`, Boot typically searches for a `@SpringBootConfiguration` class starting from the test's package and walking up through parent packages. If the test resides outside that package tree or the project contains multiple Boot applications, discovery can fail or pick the wrong configuration.

Specify the application class explicitly:

```java
@SpringBootTest(classes = StoreApplication.class)
class OrderIntegrationTest {
}
```

With plain Spring Test, check `@ContextConfiguration(classes = ...)`, XML resources, or initializers. Do not use `@SpringBootTest` on an application without Boot configuration just to try to start a context.

### Missing Bean or Multiple Beans of the Same Type

Example of a missing bean error:

```text
No qualifying bean of type 'PaymentGateway' available
```

Check whether the bean is scanned/imported, whether the active profile enables the configuration creating the bean, and whether `@ConditionalOnProperty`/`@ConditionalOnClass` conditions are satisfied.

If multiple implementations exist:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2: stripeGateway, mockGateway
```

Select the bean using `@Qualifier`, mark one implementation as `@Primary` if it is genuinely the default, or narrow the test configuration so only the required implementation is present. Do not add a mock bean of the same type without checking for conflicts with production beans.

### Missing or Unbindable Property

A configuration such as:

```java
@ConfigurationProperties(prefix = "payments")
@Validated
public record PaymentProperties(
        @NotBlank String apiUrl,
        @NotBlank String merchantId) {
}
```

can cause the context to fail if `payments.api-url` or `payments.merchant-id` is missing, misnamed, or invalid. Check the active profile and the property sources actually being loaded. `@TestPropertySource`, `@SpringBootTest(properties = ...)`, environment variables, and `@DynamicPropertySource` may supply different values.

Example of declaring test-specific properties:

```java
@SpringBootTest(properties = {
        "payments.api-url=https://payments.test.invalid",
        "payments.merchant-id=test-merchant"
})
class PaymentServiceIntegrationTest {
}
```

If a value must come from a dynamically started container or server, use `@DynamicPropertySource`. Ensure the supplier returns an endpoint that is already alive by the time Spring initializes the bean consuming that property.

### Database Not Ready or Wrong Datasource

With Testcontainers, a created container does not guarantee the database is ready to accept connections. Check the wait strategy, startup timeout, and container logs. Retrieve the JDBC URL from the container API instead of guessing the port.

With `@DataJpaTest`, Spring Boot may replace the datasource with an embedded database if configuration allows. If the test must use a container database, configure `@AutoConfigureTestDatabase(replace = Replace.NONE)` appropriately for the Boot version in use.

If the connection succeeds but the context still fails on `entityManagerFactory`, check the dialect, schema, migrations, entity mappings, and database extensions. A Flyway/Liquibase failure at startup typically prevents the context from refreshing.

### Auto-Configuration Not Activated as Expected

Spring Boot auto-configuration depends on the classpath, properties, and conditions. A missing dependency can prevent a configuration from activating; a changed property can prevent a bean from being created.

Start the application or test in debug mode to inspect the condition evaluation report:

```properties
debug=true
```

Or pass `--debug` to the Spring Boot application. The report shows which auto-configurations matched, which did not match, and which conditions were not satisfied. It is helpful when a bean expected from auto-configuration does not appear.

Avoid leaving debug enabled permanently for the entire suite if the output becomes too large. Enable it temporarily in the test class or task reproducing the issue to gather the needed information.

### Incompatible Dependency Versions or Classpath

Errors such as `NoSuchMethodError`, `AbstractMethodError`, and `NoClassDefFoundError` usually indicate binary incompatibility or a missing dependency. Check the Spring Boot BOM, Spring Framework modules, Hibernate, database drivers, and testing libraries.

Do not patch version errors by adding a standalone JAR to the test runtime without understanding the dependency graph. Use aligned dependency management from Spring Boot or the platform chosen by the project. Compare the test runtime classpath with the running application's classpath.

### Bean Initialization Calling External Services

A constructor, `@PostConstruct`, `InitializingBean#afterPropertiesSet()`, or `@Bean` factory method might make an HTTP call, read a file, connect to a broker, or call a secret manager. When that external service is unavailable in the test environment, the context fails even if the test never exercises that feature.

Prefer keeping constructors and bean initialization limited to creating objects and validating basic configuration. Move network work or side effects into methods explicitly invoked after the context is ready. If startup behavior itself needs testing, provide a compatible test service and verify readiness before creating the context.

## Using the Spring Boot Condition Report and Failure Analysis

Spring Boot provides `FailureAnalyzers` for many common startup failures. Rather than reading only `Failed to load ApplicationContext`, look for the `APPLICATION FAILED TO START` or `Failure Analysis` section in the logs:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Parameter 0 of constructor in ... required a bean of type ...
that could not be found.

Action:

Consider defining a bean of type ... in your configuration.
```

This section can provide a concise description and suggested action. It does not replace the stack trace, but it is a good clue for locating the configuration that needs fixing.

If you suspect auto-configuration, enable `debug=true` to obtain the condition evaluation report. If you suspect bean creation, keep the full stack trace and find the bean name/constructor parameter. If you suspect properties, enable appropriate logging for configuration binding and inspect the property source values used by the `Environment`; avoid printing secrets into logs.

## Reproducing the Failure with a Small Test

When a large suite has many tests failing together, create the smallest possible reproduction using the same context metadata. For example, if the error occurs with a `@SpringBootTest` using the `integration` profile, run the first failing test class in isolation with those exact profile and property sources.

A context smoke test can help validate the configuration:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationContextSmokeTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void createsRequiredInfrastructureBeans() {
        assertThat(context.getBean(OrderService.class)).isNotNull();
        assertThat(context.getBean(OrderRepository.class)).isNotNull();
    }
}
```

A smoke test does not replace behavioral tests, but it separates bootstrap failures from logic failures. When a context fails to initialize, assertions inside the method have not run yet; the bootstrap stack trace is the data you need to analyze.

For custom auto-configuration, `ApplicationContextRunner` can build a lightweight context and test conditions without booting the entire application:

```java
class PaymentAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            PaymentAutoConfiguration.class));

    @Test
    void createsGatewayWhenEnabled() {
        contextRunner
                .withPropertyValues("payments.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                });
    }
}
```

`ApplicationContextRunner` is especially useful when developing auto-configuration or testing bean creation conditions in isolation. It does not prove that the full application context can start; `@SpringBootTest` tests are still required for end-to-end integration behavior.

## Collecting Useful Logs When Running Tests

When a test fails in CI, retain the full test runner output and XML/HTML reports. With Gradle, you can run a specific test and request full stack traces:

```bash
./gradlew test --tests 'com.example.store.OrderIntegrationTest' --stacktrace --info
```

With Maven Surefire:

```bash
mvn -Dtest=OrderIntegrationTest -DtrimStackTrace=false test
```

These are diagnostic command examples; running the build belongs to the workflow of the person executing the task, not to authoring this lesson. Use the syntax appropriate for your project's wrapper and build tool.

In the logs, preserve everything from the first context refresh start through the last exception in the cause chain. If sharing only a log excerpt, do not strip `Caused by` lines, bean names, property keys, or the first stack frame belonging to project code. When logs contain credentials, tokens, or URLs with sensitive information, mask those values before sharing.

## When Should You Use `@DirtiesContext`?

`@DirtiesContext` marks a context as modified so it must be removed from the cache. Spring will close the context according to the selected mode and create a fresh context when a subsequent test needs it.

This annotation is appropriate when a test mutates singleton bean state or context configuration that cannot be safely restored. It is not the default fix for `Failed to load ApplicationContext`.

If the context fails on its very first bootstrap, `@DirtiesContext` cannot supply a missing bean, fix a property, or start a database. Fix the root cause first. Only use `@DirtiesContext` if you have determined the failure stems from context state dirtied by an earlier test, or when you must ensure the context is closed after a test with context-level side effects.

## Quick Diagnostic Checklist

When facing `Failed to load ApplicationContext`, answer these questions in order:

1. Is this the first bootstrap attempt for this context key, or just a failure-threshold skip?
2. What does the outermost exception wrap? Which bean, property, or resource do the first `Caused by` entries point to?
3. Which main configuration, profiles, and web environment is the test loading?
4. Is the failing dependency an internal bean, a property, the classpath, or an external service?
5. If it is an external service, is the endpoint correct and is the service ready?
6. If it is auto-configuration, which condition does the condition report say was not satisfied?
7. After fixing one cause, does the first test class initialize the context successfully?
8. Do the other tests sharing the same context cache key still receive the old error?

## Message and Action Reference Table

| Message in log | Interpretation | First action to take |
|---|---|---|
| `Failed to load ApplicationContext` | Context bootstrap failed | Read the cause chain of the first occurrence |
| `failure threshold exceeded` | Spring skipped a repeated attempt for a context key that already failed | Find the log of the first bootstrap attempt |
| `NoSuchBeanDefinitionException` | Missing matching bean | Check scan/import/profile/conditionals and injection type |
| `NoUniqueBeanDefinitionException` | Multiple candidate beans exist | Check `@Qualifier`, `@Primary`, and test configuration |
| `Could not resolve placeholder` | Missing property | Check active profiles and property sources |
| `Failed to bind properties` | Configuration value could not be bound or validated | Check prefix, key name, data type, and constraints |
| `Connection refused` | Endpoint is not accepting connections | Check service readiness, host, and mapped port |
| `FlywayValidateException` | Migration history, checksum, or schema is invalid | Check migration files and database state |
| `Port already in use` | Web server could not bind to the port | Use `RANDOM_PORT` or free up the test port |
| `NoSuchMethodError` | Binary version incompatibility | Check dependency management and runtime classpath |

`Failed to load ApplicationContext` is only a symptom that Spring could not complete bootstrapping. Effective diagnosis starts from the first failure, identifies the first bean or resource that could not be created, and checks the exact configuration and infrastructure involved. Once you separate the root cause from repeated messages caused by the context cache, you will avoid editing the wrong test method, adding unnecessary `@DirtiesContext` annotations, or raising the threshold without fixing the underlying issue.
