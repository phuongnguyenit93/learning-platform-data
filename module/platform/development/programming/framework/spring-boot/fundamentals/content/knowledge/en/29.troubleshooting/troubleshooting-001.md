# Reading Startup Logs and Finding the Root Cause in Exception Chains

When a Spring Boot application fails to start, the logs typically display multiple layers of information: version, active profiles, bean creation, database configuration, web server, stack traces, and nested exceptions. Reading from top to bottom and fixing the first line of code seen in the stack trace often leads to misdiagnosis.

An effective approach is to **read the logs structurally and trace the exception chain from the reported error to the underlying cause**, while cross-referencing the log lines immediately preceding the startup failure. The outermost exception usually indicates which stage Spring failed in; inner exceptions can pinpoint specific causes such as a missing bean, invalid configuration type, unreachable database, or missing class on the runtime classpath.

This lesson explains how to identify startup milestones, distinguish outermost exceptions / causes / root causes / suppressed exceptions, read stack traces, troubleshoot bean / configuration / database / port / classpath errors, use `--debug` and logging levels, and verify the cause with a controlled rerun.

The goal is not to memorize every exception class. The goal is to know how to **ask the right questions at the right layer of the error**.

## 1. What Do Startup Logs Tell You?

When calling:

~~~java
SpringApplication.run(Application.class, args);
~~~

Spring Boot performs several steps before the application is ready to accept requests. Depending on the application, the process may include:

1. Preparing the Environment and property sources.
2. Determining active profiles.
3. Creating and refreshing the ApplicationContext.
4. Registering, instantiating, and injecting beans.
5. Applying bean post-processors, proxies, and lifecycle callbacks.
6. Starting the web server if a web stack is present.
7. Running ApplicationRunner/CommandLineRunner.
8. Signaling that the application is ready.

Not every application goes through the exact same steps. A command-line application does not need a web server; reactive and servlet applications have different lifecycle details.

### 1.1. A Simplified Startup Log

~~~text
 :: Spring Boot ::                (v3.x.x)

2026-11-13 09:00:00.100  INFO 12345 --- [main]
com.example.Application : Starting Application using Java 21

2026-11-13 09:00:00.250  INFO 12345 --- [main]
com.example.Application : The following 1 profile is active: "dev"

2026-11-13 09:00:01.100  INFO 12345 --- [main]
o.s.b.w.embedded.tomcat.TomcatWebServer :
Tomcat initialized with port 8080 (http)

2026-11-13 09:00:01.700  INFO 12345 --- [main]
o.s.b.w.embedded.tomcat.TomcatWebServer :
Tomcat started on port 8080 (http)

2026-11-13 09:00:01.720  INFO 12345 --- [main]
com.example.Application :
Started Application in 1.8 seconds
~~~

Learn to recognize the timestamp, level, process/thread, logger, profile, port, and startup confirmation line. The exact format varies by Spring Boot version and logging configuration; do not rely on fixed column positions.

### 1.2. Startup Logs Are More Than Stack Traces

Logs can also contain warnings about deprecated configuration, profiles/property sources, condition evaluation, database connections, server ports, external services, and lifecycle callbacks.

Lines immediately preceding the first exception often provide vital context. For example, a log showing that the `prod` profile is active can explain why the application uses a different database endpoint when running locally.

### 1.3. Warnings Are Not Necessarily the Cause

A warning can appear near an error without causing the startup failure. For example, Hibernate might warn about a deprecated setting, and then DataSource fails due to an incorrect host. Identify which exception aborted startup before fixing unrelated warnings.

## 2. Recognizing Spring Boot Failure Analysis

Spring Boot often displays an error report block:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Web server failed to start. Port 8080 was already in use.

Action:

Identify and stop the process that's listening on port 8080
or configure this application to listen on another port.
~~~

This block comes from the **Failure Analysis** mechanism. It typically includes:

- **Description:** the condition or operation that failed.
- **Action:** suggested remediation steps.
- **Exception:** a stack trace may also be printed depending on configuration.

### 2.1. Description and Action Are a Starting Point

`Port 8080 was already in use` is quite specific. However, the message:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
~~~

only indicates that the DataSource was not configured successfully. You still need to check JDBC dependencies, profiles, properties, and custom DataSource configuration.

Actions are helpful, but they do not replace verifying within the application itself.

### 2.2. Not Every Exception Has a Failure Analysis

Spring Boot has built-in FailureAnalyzers for many common scenarios. For custom exceptions or unrecognized errors, you may only see a stack trace. The absence of a Description/Action block does not mean there is no root cause.

### 2.3. One Exception May Be Printed Multiple Times

The framework, application logger, launcher, or test runner may all print the same failure. Do not count occurrences and conclude there are multiple independent errors. Compare timestamps, threads, exception types, and cause chains.

## 3. In What Order Should You Read Logs?

A practical sequence:

1. Find `APPLICATION FAILED TO START` or the first error that led to the startup abort.
2. Read the Description/Action if present.
3. Inspect the log lines immediately before the error to see which component the application was initializing.
4. Identify the outermost exception.
5. Follow each `Caused by` entry.
6. Find frames belonging to your application's package in the relevant stack trace.
7. Cross-reference the properties, dependencies, profiles, or environment mentioned.
8. Make one informed change and rerun to verify.

Do not start by reading hundreds of frames before understanding the exception chain. First establish **which exception is being reported**, then locate where it originated.

### 3.1. Preserve Sufficient Log Context

Sending only the line:

~~~text
Caused by: java.net.ConnectException: Connection refused
~~~

leaves the recipient unaware of which component was connecting, which host/port was used, whether the error occurred at startup or during a request, which bean the exception fell under, and which profile was active.

When sharing logs, keep a surrounding context snippet, the full cause chain, and relevant frames. Redact credentials, tokens, session IDs, personal data, and sensitive internal details.

## 4. Outermost Exception, Cause, and Root Cause

Java exceptions can wrap other exceptions. A framework layer catches a lower-level exception, adds context, and throws a new exception with a cause.

~~~text
UnsatisfiedDependencyException:
Error creating bean with name 'orderController'

Caused by: BeanCreationException:
Error creating bean with name 'orderService'

Caused by: IllegalStateException:
Payment endpoint is not configured
~~~

This can be read as:

- Spring could not create `orderController` because a dependency was unavailable.
- That dependency involves `orderService`.
- While creating the service, code or configuration detected that the payment endpoint had not been set.

The outermost exception describes the error at the container boundary; deeper exceptions typically provide more specific details.

### 4.1. getCause()

In Java, an exception can hold an underlying exception via `Throwable.getCause()`:

~~~java
Throwable cause = exception.getCause();
~~~

A cause chain can have multiple levels:

~~~text
Exception A
    |
    +-- cause: Exception B
                 |
                 +-- cause: Exception C
                              |
                              +-- cause: Exception D
~~~

Each `Caused by:` line in a stack trace marks an exception linked as the cause of the exception above it.

### 4.2. The Root Cause Is Often Deepest, but That Is Not an Absolute Rule

In a simple wrapping chain, the deepest exception usually has a specific message. However, simply picking the deepest cause does not always point to what needs fixing:

- A deep `IllegalArgumentException` might stem from invalid input data.
- The deepest `SQLException` may just be a transport error; the operational cause could be that the database is down or the host is wrong.
- An exception during cleanup may appear after the primary error.
- Wrapper exceptions can hold critical details about the bean, property, or resource.

Read the entire chain, messages, stack frames, and log context. The root cause is **the cause with the best evidence explaining the failure**, not simply the last line.

### 4.3. The Outermost Exception Still Matters

Do not ignore `UnsatisfiedDependencyException` just because `IllegalStateException` lies beneath it. The outermost exception typically identifies which bean was being created and which dependency could not be resolved.

## 5. Reading Stack Traces and Finding Application Frames

Example:

~~~text
java.lang.IllegalStateException: Payment endpoint is not configured
    at com.example.payment.PaymentClientProperties.validate(PaymentClientProperties.java:42)
    at com.example.payment.PaymentClient.<init>(PaymentClient.java:27)
    at java.base/jdk.internal.reflect.DirectConstructorHandleAccessor.newInstance(...)
    at java.base/java.lang.reflect.Constructor.newInstance(...)
    at org.springframework.beans.BeanUtils.instantiateClass(...)
    at org.springframework.beans.factory.support.SimpleInstantiationStrategy.instantiate(...)
    ...
~~~

Each `at ...` frame represents a method on the call stack when the exception was created.

### 5.1. Find the First Frame in Application Code

In the example, `PaymentClientProperties.validate(PaymentClientProperties.java:42)` is the first frame belonging to the application package. Open the exact file and line in the running revision and inspect what condition throws the exception.

Subsequent frames belong to reflection and Spring Framework, showing that the error occurred while Spring was instantiating the bean.

### 5.2. The First Frame Is Not Always Where the Fix Belongs

If an exception is thrown from a library:

~~~text
at com.vendor.sdk.HttpTransport.open(HttpTransport.java:88)
~~~

the cause might lie in the URL, credentials, DNS, TLS, or external network rather than library code.

If the first frame is `java.net.Socket.connect`, locate the application caller frame to see which adapter/component requested the connection.

### 5.3. Trailing Frames Are Usually Infrastructure

Deeper frames are typically reflection, dependency injection, servlet containers, or thread runners. They show the path through the framework but rarely pinpoint the business configuration that needs fixing.

However, Spring frames can confirm whether the error occurred during property binding, bean creation, or context refresh.

### 5.4. File Names and Line Numbers

`PaymentClientProperties.java:42` is helpful when your source matches the running revision. If code changed after the log was generated, line numbers may no longer align. Artifacts built without full debug information may also show only class/method names.

## 6. Suppressed Exceptions and Cleanup Errors

Java supports **suppressed exceptions**, commonly seen when another exception occurs while closing resources or cleaning up.

~~~java
try (InputStream input = resource.getInputStream()) {
    parse(input);
}
~~~

If `parse(input)` throws an exception and `close()` also fails, the close error may be attached to the primary exception:

~~~text
java.io.IOException: Failed to parse catalog
    at com.example.catalog.CatalogLoader.load(CatalogLoader.java:51)
    Suppressed: java.io.IOException: Failed to close resource
        at com.example.catalog.CustomResource.close(CustomResource.java:18)
~~~

### 6.1. Suppressed Is Not the Same as Cause

- **Cause:** explains that the current exception was triggered by another exception.
- **Suppressed:** a secondary exception that occurred while another exception was already being handled.

When looking for the primary error, do not mistake a cleanup error for the initial error. Still, suppressed exceptions are worth inspecting if they indicate a resource leak or cleanup failure.

### 6.2. An Exception May Have No Cause

An exception can be constructed without passing a cause. In that case, the message and the throw site in code are the main clues.

### 6.3. Shutdown Errors Can Appear After a Startup Failure

A failed context refresh can trigger cleanup. If closing a bean also fails, the log may contain a second exception. Check timestamps, threads, cause/suppressed relationships, and shutdown messages to distinguish the error that stopped startup from an error triggered during cleanup.

## 7. Example: Reading an Exception Chain from Controller to Property

Suppose the log shows:

~~~text
APPLICATION FAILED TO START

UnsatisfiedDependencyException:
Error creating bean with name 'invoiceController':
Unsatisfied dependency through constructor parameter 0

Caused by: BeanCreationException:
Error creating bean with name 'invoiceService':
Could not resolve placeholder 'app.tax.rate'

Caused by: PlaceholderResolutionException:
Could not resolve placeholder 'app.tax.rate'
~~~

Analysis:

1. The outermost bean is `invoiceController`.
2. The controller requires `invoiceService`.
3. Spring could not create the service.
4. While creating the service, placeholder `app.tax.rate` could not be resolved.
5. Check the property, profile/config source, and spelling.

Do not alter the controller constructor just because the outermost exception mentions the controller. The controller is simply where Spring detected the broken dependency chain.

### 7.1. Checking Configuration

Example YAML:

~~~yaml
app:
  tax:
    rate: 0.08
~~~

Or environment variable:

~~~text
APP_TAX_RATE=0.08
~~~

Verify which property sources are actually loaded in the running environment. Having an `application-dev.yml` file does not guarantee that the `dev` profile is active.

### 7.2. Verifying After the Fix

- Rerun with the same command and profile.
- Confirm the placeholder error disappears.
- Confirm `invoiceService` and `invoiceController` are created.
- If a new error appears, diagnose the new failure next.

A single startup can encounter multiple sequential issues; fixing one error does not guarantee that all subsequent steps will succeed.

## 8. Common Startup Exceptions

| Exception | Usually Indicates |
| --- | --- |
| `UnsatisfiedDependencyException` | Could not resolve a bean's dependency |
| `NoSuchBeanDefinitionException` | No matching bean exists |
| `NoUniqueBeanDefinitionException` | Multiple bean candidates exist; could not select a single one |
| `BeanCreationException` | Bean failed during creation/initialization |
| `BeanCurrentlyInCreationException` | Circular dependency or a bean currently being created was referenced again |
| `ConfigurationPropertiesBindException` | Binding configuration properties failed |
| `BindException` | Data could not be bound to the target |
| `PortInUseException` | Web server could not bind to the port |
| `ApplicationContextException` | Context could not start or complete lifecycle |
| `IllegalStateException` | Inappropriate state; inspect the message and throw site |
| `ClassNotFoundException` | Class loading mechanism could not find the required class |
| `NoClassDefFoundError` | JVM could not find or use the class definition at runtime |
| `NoSuchMethodError` | Bytecode invokes a method missing from the runtime class version |
| `UnsupportedClassVersionError` | Bytecode is newer than the running JVM version |

These are classification hints, not absolute rules of deduction. Always read the message and cause chain.

## 9. Dependency Injection Errors

Example:

~~~text
UnsatisfiedDependencyException:
Error creating bean with name 'orderController':
Unsatisfied dependency expressed through constructor parameter 0
~~~

Spring is creating `orderController` but cannot supply the corresponding argument.

### 9.1. NoSuchBeanDefinitionException

~~~text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentGateway' available
~~~

Check:

- Is there a `PaymentGateway` implementation?
- Is the implementation registered with `@Component`, `@Service`, or `@Bean`?
- Is its package within component scan scope?
- Is the bean excluded from the context by `@Profile` or `@ConditionalOnProperty`?
- Is the dependency on the runtime classpath?
- Is a test using a slice that only loads a subset of beans?

Example:

~~~java
@Component
public class DefaultPaymentGateway implements PaymentGateway {
    // ...
}
~~~

If the class is outside the scanned packages, the annotation alone is not enough for the bean to appear.

### 9.2. NoUniqueBeanDefinitionException

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
stripeGateway, sandboxGateway
~~~

Two beans of the same type match the injection point. You can use `@Primary`, `@Qualifier`, profiles/conditions, or adjust bean definitions. Do not delete a bean just to pass startup if both are needed for different use cases.

### 9.3. Inspect Constructor Parameters

The message may state the parameter index or name. Cross-reference the outermost bean's constructor with the dependency types. The error may originate from a deeper argument in the chain rather than the first dependency you see.

### 9.4. Verify with a Context Test

Unit tests that manually construct services with mocks do not verify component scanning or bean resolution. After fixing wiring, use an appropriate context test to confirm Spring can create the bean.

## 10. BeanCreationException: Identifying the Failing Bean

`BeanCreationException` typically includes the bean name:

~~~text
Error creating bean with name 'dataSource'
~~~

or:

~~~text
Error creating bean with name 'entityManagerFactory'
~~~

Do not stop at the exception class. Locate the cause chain and the specific bean.

### 10.1. Errors in Constructors

~~~java
@Component
public class PaymentClient {

    public PaymentClient(PaymentProperties properties) {
        if (properties.endpoint() == null) {
            throw new IllegalStateException(
                    "Payment endpoint is required"
            );
        }
    }
}
~~~

If a constructor validates configuration and throws an exception, Spring wraps the error during bean creation. Check the property values the bean receives and the source providing those values.

### 10.2. Errors in @PostConstruct

~~~java
@PostConstruct
void initialize() {
    loadRequiredCatalog();
}
~~~

If `loadRequiredCatalog()` fails, the bean cannot complete initialization. Check resources, read permissions, paths, and parser errors. Do not increase timeouts or change bean ordering if the cause is a missing file.

### 10.3. Cascading Errors from Other Beans

`entityManagerFactory` can fail because of DataSource; DataSource can fail because of URL/credentials; connection can fail because the database is not running. Follow the cause chain instead of blindly editing the outermost bean.

## 11. Placeholder and ConfigurationProperties Binding Errors

Two error groups must be distinguished:

- Unresolvable placeholders.
- Properties that exist but fail conversion or violate validation.

### 11.1. Unresolved Placeholders

~~~text
Could not resolve placeholder 'app.mail.endpoint'
~~~

Check the property name, loaded files, active profiles, environment variables, dots/hyphens, and actual configuration sources.

If the property is required, failing fast makes sense. If optional, provide an intentional default rather than swallowing the error.

### 11.2. Invalid Type Binding

~~~text
Failed to bind properties under 'app.payment.timeout'
to java.time.Duration
~~~

Example of invalid configuration:

~~~yaml
app:
  payment:
    timeout: someday
~~~

Java declares `Duration`, so Binder cannot convert `someday` into a duration. A valid value might be:

~~~yaml
app:
  payment:
    timeout: 5s
~~~

Read the property path, target type, and value. Do not change the field to `String` just to make startup pass if business logic requires `Duration`.

### 11.3. Binding Succeeds but Validation Fails

~~~text
Binding validation errors on app.payment
  Field error in object 'app.payment' on field 'maxAttempts':
  rejected value [0]; must be greater than or equal to 1
~~~

The value `0` converts to `int` but violates `@Min(1)`. This is a validation failure, not a conversion failure.

### 11.4. ConfigurationPropertiesBindException

Find the prefix and failing field in the nested cause. Key details include property name, value, Java type, whether it is conversion or validation, and the property source if logged.

### 11.5. Profiles Are Crucial Evidence

If the log shows that the `prod` profile is active when you expect properties from `application-dev.yml`, verify the profile and run configuration before modifying Java code.

## 12. DataSource and Database Connections

A common startup failure:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
~~~

Another scenario:

~~~text
CannotGetJdbcConnectionException:
Failed to obtain JDBC Connection

Caused by: SQLException:
Connection refused
~~~

The first case usually means a suitable DataSource configuration is missing; the second indicates the application attempted to obtain a connection and failed.

### 12.1. Check Layer by Layer

1. Is the JDBC/JPA driver on the runtime classpath?
2. Is `spring.datasource.url` correct?
3. Are username/password passed correctly?
4. Is the database service running?
5. Are the host/port reachable from the environment running the app?
6. Does the database/schema exist?
7. Does the user have permission to connect and access the schema?
8. Are there specific TLS, certificate, or network policy requirements?

### 12.2. Distinguish Connection Error Types

- `Connection refused` usually indicates the TCP connection was not accepted at the host/port.
- `Access denied` or authentication failure usually indicates the server accepted the connection but rejected the credentials/permissions.
- `UnknownHostException` is usually related to DNS/hostname.
- Timeouts may involve network, firewall, unresponsive server, or timeout configuration.

Test from the exact environment where the application runs. A successful connection on your laptop does not prove a container or CI runner can reach it.

### 12.3. Do Not Log Passwords for Debugging

Log only host/database/schema and configuration status if needed; never print passwords, tokens, or connection strings containing secrets.

## 13. Port Already in Use

Example:

~~~text
Web server failed to start. Port 8080 was already in use.
~~~

Another process may be listening on the port, or a previous instance may still be running.

The port may be configured via:

~~~properties
server.port=8080
~~~

or:

~~~yaml
server:
  port: 8080
~~~

It may be overridden by:

~~~text
SERVER_PORT=9090
~~~

or command-line:

~~~bash
java -jar app.jar --server.port=9090
~~~

Check the effective configuration, not just a single `application.yml` file.

If the server fails to bind a port, changing controller mappings will not fix the socket error. For tests requiring a real server, `@SpringBootTest(webEnvironment = RANDOM_PORT)` helps avoid port conflicts between tests, but does not replace configuring the production port properly.

## 14. Classpath and Dependency Compatibility Errors

### 14.1. ClassNotFoundException

~~~text
ClassNotFoundException:
com.vendor.payment.PaymentClient
~~~

Check whether the dependency is on the runtime classpath, whether its scope is only compile/test, whether the artifact was packaged properly, whether package/class names changed, and whether the module was built/published.

### 14.2. NoClassDefFoundError

~~~text
NoClassDefFoundError:
com/vendor/payment/PaymentClient
~~~

This is a linkage/runtime error distinct from `ClassNotFoundException`. It can also occur when a class previously failed initialization, for example due to `ExceptionInInitializerError`. Look for the first occurrence of the initialization error if present.

### 14.3. NoSuchMethodError

~~~text
NoSuchMethodError:
com.vendor.api.ClientBuilder.timeout(...)
~~~

Code was compiled against an API containing that method, but runtime loaded a class version without that method. The cause is usually a dependency version conflict or mismatched compile/runtime classpaths.

Inspect the dependency tree, the actual versions inside the artifact, use the Boot BOM/dependency management consistently, and confirm the right artifact is running.

### 14.4. UnsupportedClassVersionError

The class was compiled for a newer class-file version than the runtime JVM supports. Check the build JDK, runtime JDK, Maven/Gradle toolchain, target/release settings, and runtime image. This error can occur before Spring creates the ApplicationContext.

## 15. Reading Logs Chronologically: First Error vs. Cascading Errors

An initial failure can trigger many subsequent messages:

~~~text
Failed to initialize DataSource
    |
    v
EntityManagerFactory bean cannot be created
    |
    v
OrderRepository cannot be initialized
    |
    v
OrderService dependency cannot be resolved
    |
    v
OrderController dependency cannot be resolved
    |
    v
APPLICATION FAILED TO START
~~~

If you only look at the last line, you might think the controller is the problem. Yet the initiating cause is DataSource.

### 15.1. The First Exception in the File Is Not Necessarily the Root Cause

Logs may contain handled exceptions, failed retries that later succeeded, or warnings from a component that did not abort startup.

Identify the first exception **that led to the startup abort**, not simply the first exception appearing in any context.

### 15.2. Distinguish Startup Errors from Shutdown Errors

A failed context refresh can trigger cleanup. If closing a bean also fails, the log may print a second exception. Check timestamps, threads, cause/suppressed relationships, and shutdown messages to tell them apart.

## 16. Finding Application Frames and Verifying Hypotheses

Example:

~~~text
BeanCreationException:
Error creating bean with name 'paymentClient'

Caused by: IllegalArgumentException:
Invalid endpoint

    at com.example.payment.PaymentProperties.validate(PaymentProperties.java:38)
    at com.example.payment.PaymentClient.<init>(PaymentClient.java:24)
    at java.base/jdk.internal.reflect...
    at org.springframework.beans.factory.support...
~~~

Steps:

1. Open `PaymentProperties.java` at line 38.
2. Identify the condition that throws `Invalid endpoint`.
3. Check where the endpoint value comes from.
4. Confirm the actual property source/profile.
5. Fix code only if the validation or logic is wrong; if configuration is wrong, fix the configuration source.
6. Rerun with the same command/profile to confirm.

### 16.1. Generated Code and Proxies

Stack traces may include proxy classes, reflection, or generated code. If the first frame is not directly in your source, find the nearest caller in your application package. You do not need to understand every CGLIB/JDK frame to diagnose a bad property; only use them when verifying proxy/call paths.

### 16.2. Truncated Stack Traces

Some loggers, test runners, or IDE views truncate stack traces. If the full `Caused by` chain is missing, retrieve the raw logs or enable full stack trace display before drawing conclusions.

Do not guess the cause from a single summary line.
## 17. Using --debug and the Condition Evaluation Report

When you suspect an auto-configuration is not being applied or is backing off, run:

~~~bash
java -jar app.jar --debug
~~~

With Maven development run:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

With Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

`--debug` instructs Spring Boot to generate the **Condition Evaluation Report** with details on which auto-configuration conditions matched or did not match. It is not a switch that sets all logging to DEBUG, nor does it automatically fix missing beans.

### 17.1. Reading Positive Matches and Negative Matches

The condition report is typically grouped into:

- **Positive matches:** configurations/conditions that were applied.
- **Negative matches:** configurations/conditions that were not applied, along with the unsatisfied conditions.
- **Exclusions:** excluded auto-configurations.
- **Unconditional classes:** configurations that do not depend on standard conditions.

Illustrative example:

~~~text
DataSourceAutoConfiguration matched:
   - @ConditionalOnClass found required classes
   - @ConditionalOnMissingBean did not find any beans

DataSourceAutoConfiguration.PooledDataSourceConfiguration did not match:
   - @ConditionalOnProperty (spring.datasource.type) did not find property
~~~

Exact messages depend on version and conditions. Do not expect every report to match these exact example lines.

### 17.2. What Questions Does the Condition Report Answer?

It helps when you need to know:

- Was the auto-configuration considered?
- Were the required classes/dependencies on the classpath?
- Were property conditions satisfied?
- Did a user-defined bean cause Boot to back off?
- Was the configuration excluded?

It does not replace the stack trace of an error inside a registered bean. If the DataSource bean was created but failed to connect, the condition report explains why auto-configuration ran; the cause chain reveals the specific connection failure.

### 17.3. Do Not Leave --debug Enabled Continuously in Every Environment

The condition report generates substantial log volume and can make output harder to read. Enable it when diagnosing auto-configuration, save the output, and return to an appropriate log level.

## 18. Adjusting Logging Levels with the Right Scope

Spring Boot uses the logging system configured by the application. You can adjust levels with properties:

~~~properties
logging.level.root=INFO
logging.level.com.example=DEBUG
logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Or YAML:

~~~yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
    org.springframework.boot.autoconfigure: DEBUG
~~~

### 18.1. Root Level vs. Package Level

- `logging.level.root` sets the default level for loggers unless a more specific configuration exists.
- `logging.level.com.example` increases detail for your application package.
- `logging.level.org.springframework.boot.autoconfigure` is useful when observing auto-configuration.

You rarely need to enable `DEBUG` for all of `org.springframework`. Doing so produces massive logs and obscures the information you need.

### 18.2. TRACE Is Not Always Better Than DEBUG

TRACE can emit extensive internal details. Enable the specific logger for the component under investigation and only for as long as needed.

### 18.3. Logging Levels Do Not Create Missing Exception Causes

If code logs an exception without passing the throwable:

~~~java
log.error("Startup failed: {}", exception.getMessage());
~~~

a stack trace will not appear just by changing the level. To record the throwable:

~~~java
log.error("Startup failed", exception);
~~~

In production code, preserve the exception object when logging diagnosable errors. Avoid logging only `getMessage()` and discarding the cause chain.

### 18.4. Do Not Log the Same Exception at Every Layer

If a lower layer already logged the full exception and higher layers log the same exception repeatedly, logs become duplicated. Pick the layer with sufficient context to log once meaningfully; other layers can add context or rethrow according to contract.

## 19. Checking Active Profiles and Effective Property Sources

When logs mention a property, do not look only at the YAML file in your editor. Spring Boot supports multiple configuration sources and precedence rules.

Common sources:

- Configuration files such as `application.properties` or `application.yml`.
- Profile-specific files such as `application-prod.yml`.
- OS environment variables.
- Java system properties.
- Command-line arguments.
- Config data/imports or property sources added by the application.

### 19.1. Confirming Active Profiles

Startup logs typically show active profiles. You can set profiles via:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

or environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

If a property is only declared under a different profile, Spring will not use it when that profile is inactive.

### 19.2. Command-Line Values Can Override Files

~~~bash
java -jar app.jar --server.port=9090
~~~

can make the application bind port 9090 even if the YAML file specifies 8080. When reading port logs, inspect the actual process command line and environment.

### 19.3. Inspecting Properties Safely

You can log a non-sensitive configuration value in the relevant component or write a test to verify binding. Do not print the entire Environment or all configuration properties if they might contain secrets.

Actuator provides endpoints like `env` and `configprops` in appropriate configurations. They can expose configuration values; only expose them in controlled environments with proper authentication/authorization and masking. Never expose these endpoints publicly just for debugging convenience.

### 19.4. Do Not Confuse a Missing Property with an Overridden Property

If a property exists in a file yet runtime receives another value, a higher-precedence source may have overridden it. Find the effective source instead of duplicating the property across multiple files.

## 20. Enabling Dependency/Configuration Logs When Needed

If the error involves bean scanning or component registration, you can temporarily increase logging:

~~~properties
logging.level.org.springframework.context.annotation=DEBUG
logging.level.org.springframework.beans.factory.support=DEBUG
~~~

If the error involves the web server, choose the logger matching the server/framework in use. If it involves Hibernate/JPA, enable the loggers appropriate to your version, while avoiding logging SQL bind values containing sensitive data in environments with real data.

### 20.1. Logging Must Serve a Hypothesis

Example hypothesis: "The payment adapter bean is not scanned because it lies outside the root package."

You can inspect component scan/bean definitions. You do not need to enable TRACE across all of Spring to verify a single class.

### 20.2. Increasing Logs Can Affect Timing

DEBUG logging can slow startup or alter timing in multithreaded systems. When investigating race conditions, note that enabling logs can influence timing; a single debug run is not definitive proof for all cases.

## 21. Example Analysis: Missing Payment Gateway Bean

Suppose the startup log shows:

~~~text
APPLICATION FAILED TO START

UnsatisfiedDependencyException:
Error creating bean with name 'checkoutController':
Unsatisfied dependency expressed through constructor parameter 0

Caused by: UnsatisfiedDependencyException:
Error creating bean with name 'checkoutService':
Unsatisfied dependency expressed through constructor parameter 1

Caused by: NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentGateway' available
~~~

### 21.1. Reading from Outside In

- `checkoutController` needs `CheckoutService`.
- `CheckoutService` needs a dependency at constructor parameter 1.
- That dependency is `PaymentGateway`.
- The context has no matching bean.

Thus the error is bean registration/selection, not controller request mapping.

### 21.2. Inspecting the Source

Interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
~~~

Implementation:

~~~java
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

The class has no `@Component` and no `@Bean` factory method. Without another registration mechanism, Spring does not automatically create a bean just because a class implements an interface.

You can register it:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
~~~

This example only illustrates bean registration; a real implementation may require an HTTP client, credentials, and dedicated configuration.

### 21.3. Verifying with a Context Test

A context test can assert:

~~~java
assertThat(context).hasSingleBean(PaymentGateway.class);
~~~

Or start the application with test configuration and verify the bean is resolved.

### 21.4. What If There Are Two Implementations?

If the context reports `NoUniqueBeanDefinitionException`, inspect the candidate names. Choose an implementation intentionally using `@Primary`, `@Qualifier`, or conditions/profiles.

## 22. Example Analysis: Unreachable Database

Log:

~~~text
BeanCreationException:
Error creating bean with name 'entityManagerFactory'

Caused by: PersistenceException:
Unable to build Hibernate SessionFactory

Caused by: JDBCConnectionException:
Unable to obtain JDBC Connection

Caused by: ConnectException:
Connection refused
~~~

### 22.1. Reading Error Layers

- `entityManagerFactory` could not be created.
- Hibernate could not build the SessionFactory.
- Hibernate could not obtain a JDBC connection.
- The TCP connection was refused.

The area to investigate first is the database endpoint/network/readiness, not entity mappings.

### 22.2. Checking the Runtime Endpoint

Determine the host/port the process is using. When running inside Docker, `localhost` usually points to the container itself, not automatically to the host or another database container.

Verify DNS/network from the actual runtime container/service. Do not test only from your development machine.

### 22.3. Verifying After the Fix

Once the database is ready or the URL is corrected:

- The `Connection refused` error disappears.
- DataSource can acquire connections.
- Hibernate continues initialization.
- If a subsequent schema/mapping error appears, treat it as a new failure.

Do not alter entity classes to fix a TCP connection failure.

## 23. Example Analysis: Property Binds Successfully but Violates Business Rules

Suppose the log shows:

~~~text
ConfigurationPropertiesBindException:
Error creating bean with name 'paymentProperties'

Caused by: BindValidationException:
Binding validation errors on app.payment

Field error in object 'app.payment'
on field 'maxAttempts':
rejected value [0]
must be greater than or equal to 1
~~~

The value `0` converts to an integer but violates validation.

If policy requires at least one attempt, update the configuration:

~~~yaml
app:
  payment:
    max-attempts: 3
~~~

If the domain genuinely allows `0` to mean no retries, the `@Min(1)` constraint may be wrong and the code/contract needs updating. Do not change configuration just to pass validation if business semantics require another value.

## 24. Example Analysis: Port 8080 Already in Use

Log:

~~~text
APPLICATION FAILED TO START

Web server failed to start. Port 8080 was already in use.
~~~

Check:

1. Is an old instance of the app still running?
2. Is another process using port 8080?
3. Is the run configuration launching two instances?
4. Is there a `server.port` or `SERVER_PORT` override?
5. For tests, can a random port be used?

On Windows, you can use PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
~~~

Then identify the process:

~~~powershell
Get-Process -Id <OwningProcess>
~~~

On Linux/macOS, `lsof` or `ss` can be used if available. Exact commands depend on the operating system.

Do not terminate an unknown process just to free a port. Identify the process and its purpose first.

## 25. Diagnosing Dependency Version Conflicts

Example:

~~~text
NoSuchMethodError:
com.vendor.sdk.ClientBuilder.timeout(...)
~~~

This is typically a sign that code was compiled against one API while runtime loaded a different version.

### 25.1. Inspecting the Dependency Tree

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

You can filter down to a specific dependency to see which module pulled another version into the graph.

### 25.2. Inspecting the Actual Artifact

When running an executable JAR, check the dependencies packaged inside it, not just your IDE's dependency tree. An old artifact or outdated deployment image might still contain an unwanted version.

### 25.3. Using BOM / Dependency Management

With Spring Boot, prefer dependency management compatible with your Boot version. Do not individually override multiple Spring modules or foundational libraries without checking compatibility.

## 26. A Repeatable Diagnostic Workflow

**Step 1 — Record the runtime environment.** Note Java version, Spring Boot version, command, profiles, working directory, and launch method (IDE, Maven, Gradle, executable JAR, container).

**Step 2 — Identify the first failure that aborted startup.** Find `APPLICATION FAILED TO START`, Failure Analysis, or the first exception causing context failure.

**Step 3 — Read the outermost exception.** Note the bean/component and the failing operation.

**Step 4 — Trace the cause chain.** Read every `Caused by`, message, and suppressed exception; do not copy only the final line.

**Step 5 — Find application frames.** Open the source at the running revision and check the indicated method/line.

**Step 6 — Cross-reference environment and configuration.** Verify profiles, property sources, dependency graph, ports, network, and filesystem.

**Step 7 — Formulate a testable hypothesis.** For example, "the staging profile does not provide app.payment.endpoint" instead of "Spring is broken."

**Step 8 — Change one informed variable.** Avoid changing multiple properties, dependencies, and code simultaneously.

**Step 9 — Rerun under identical conditions.** Keep the same command, profiles, and environment as before, except for the factor being tested.

**Step 10 — Confirm with concrete evidence.** The old error disappears, the bean is created, the server binds successfully, or startup completes.

**Step 11 — Run appropriate tests.** Context tests for wiring/configuration, integration tests for database/network, unit tests for logic.

**Step 12 — Document the conclusion and boundaries.** State the cause, evidence, change made, and verification method.

### 26.1. Example of a Good Hypothesis

Vague:

> Spring Boot cannot start.

Testable:

> The context cannot create PaymentClient because property app.payment.endpoint does not resolve in the staging profile. Startup logs confirm the staging profile; the cause chain ends at placeholder resolution. After providing the property in that profile's configuration source, the bean is created and the application starts successfully.

A good hypothesis names the component, condition, evidence, and verification method.

## 27. Using Logs in IDEs and Terminals

### 27.1. IDE

When running from an IDE:

- Save the full console output, not just the final exception.
- Check the run configuration and environment variables.
- Check the active profiles passed in.
- Verify the module/dependency classpath.
- If the console truncates logs, redirect to a file or open full output.
- Note which JDK the IDE uses, not just the default JDK in your terminal.

### 27.2. Maven

~~~bash
mvn spring-boot:run
~~~

Pass the debug argument:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Inspect dependencies:

~~~bash
mvn dependency:tree
~~~

### 27.3. Gradle

~~~bash
./gradlew bootRun --args='--debug'
~~~

Inspect runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

### 27.4. Executable JAR

~~~bash
java -jar app.jar --debug
~~~

Note the exact JAR file and Java runtime. If the error only appears after packaging, inspect the artifact, runtime classpath, external files, and container configuration.

### 27.5. Preserve Conditions When Reproducing

A local run with the `dev` profile does not verify an error in the `prod` profile. An IDE run does not verify an executable JAR. Reproduce under conditions as close as possible to where the error occurred.

## 28. Safe and Useful Logging

Startup logs can contain database URLs, access tokens, API keys, request payloads, personal data, hostnames, and internal topology.

When increasing logging:

1. Enable only the necessary loggers.
2. Never log secrets or raw credentials.
3. Mask sensitive data in configurations/payloads.
4. Do not expose Actuator env/configprops publicly.
5. Turn off verbose logging after diagnosis if no longer needed.
6. Follow your log system's retention and access policies.

### 28.1. Log Exceptions with the Throwable

Prefer:

~~~java
log.error("Could not initialize payment client", exception);
~~~

instead of only:

~~~java
log.error("Could not initialize payment client: {}",
        exception.getMessage());
~~~

The first preserves the stack trace and cause chain in loggers that support throwables. Before logging an exception that could contain URLs/credentials, ensure sensitive information has been handled.

### 28.2. Do Not Swallow Exceptions

Code like:

~~~java
try {
    initialize();
} catch (Exception exception) {
    log.error("Initialization failed");
}
~~~

loses the cause and can allow the application to continue in an invalid state.

If initialization is required, rethrow the exception or wrap it while preserving the cause:

~~~java
throw new IllegalStateException(
        "Could not initialize payment client",
        exception
);
~~~

If the failure is recoverable, define explicit retry/fallback behavior and log the outcome.

## 29. Custom FailureAnalyzer for Starters/Modules

A starter may want to provide clear startup messages for its own configuration errors. Spring Boot offers the `FailureAnalyzer` extension point.

Illustrative example:

~~~java
public class MissingCatalogFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingCatalogException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingCatalogException cause) {

        return new FailureAnalysis(
                "Required catalog resource was not found.",
                "Provide the catalog under the configured classpath location.",
                cause
        );
    }
}
~~~

`MissingCatalogException` is a module-defined exception. How the analyzer is registered depends on the mechanism supported by the project's Spring Boot version.

### 29.1. Analyzers Do Not Replace Exception Chains

FailureAnalyzer produces readable guidance, but should still retain the original exception as the cause for operator investigation.

### 29.2. When Should You Create One?

- The starter has required configuration.
- Domain errors recur and have a concrete remediation action.
- Library consumers frequently encounter confusing setup errors.
- Reliable guidance can be produced from the exception type.

Do not create a generic analyzer for every exception; incorrect guidance can mislead users.

## 30. Common Mistakes When Reading Startup Logs

### 30.1. Reading Only the Outermost Exception

Seeing `UnsatisfiedDependencyException` and editing the controller. Trace the cause chain to locate the deeper bean or property.

### 30.2. Reading Only the Final Caused by Line

Losing bean, property, or operation context from wrapper exceptions. Read the entire chain and cross-reference stack frames.

### 30.3. Fixing the First Frame Without Checking the Message

The frame may belong to a library/framework or merely be a caller. Open the source at the running revision and inspect the throw condition.

### 30.4. Confusing Warnings with Startup Failures

Fixing unrelated deprecated warnings. Identify the exception that actually aborted the context.

### 30.5. Checking Only application.yml

Runtime may use environment variables, command-line args, or a different profile. Confirm active profiles and effective property sources without logging secrets.

### 30.6. Setting All Logging to TRACE

Logs become overwhelming and hide the failure. Enable DEBUG/TRACE for specific packages/components briefly.

### 30.7. Rerunning in a Different Environment

The error occurs in a container, yet testing happens only in a local IDE. Reproduce with matching artifact, Java version, profile, environment, and network boundaries.

### 30.8. Changing Multiple Things at Once

You cannot tell which change fixed the error. Form one hypothesis, change one factor, rerun, and record the outcome.

### 30.9. Swallowing Exceptions or Logging Only Messages

Cause chains and stack traces are lost. Log the throwable at a layer with proper context and rethrow if startup cannot safely continue.

### 30.10. Assuming Root Cause Is Always the Last Line

Suppressed/cleanup exceptions or wrapper context may matter more. Inspect the exception structure and timeline.

### 30.11. Exposing Actuator env/configprops Publicly

This can leak secrets/configuration. Expose only in controlled environments, secure endpoints, and mask properly.

### 30.12. Changing Code When the Error Is Environmental

Modifying services/beans to deal with port conflicts, DNS, or stopped databases. Separate code, configuration, dependency, and infrastructure errors before editing.

## 31. Template for Recording a Startup Failure

~~~text
Context
- Application / module:
- Commit or build:
- Java version:
- Spring Boot version:
- Run command:
- Active profiles:
- Runtime environment:

Observed failure
- Startup phase:
- Outer exception:
- Bean/component:
- First application frame:
- Deepest relevant cause:
- Relevant log lines before failure:

Evidence
- Property/dependency/port/resource involved:
- What was checked:
- What was ruled out:

Hypothesis
- Most likely root cause:
- Evidence supporting it:

Verification
- Change made:
- Same command/profile rerun:
- Old exception gone:
- Application startup result:
- Remaining issue:
~~~

This template prevents missing context. Omit irrelevant fields; never attach credentials or secrets.

## 32. Practice Exercises

### Exercise A: Missing Property

Create a bean requiring `app.payment.endpoint`. Run the application without providing the property and read the exception chain. Add the property to the right profile, rerun with the same command, and confirm the bean is created.

### Exercise B: Missing Bean

Create a controller depending on `PaymentGateway` without registering an implementation. Observe `UnsatisfiedDependencyException` and `NoSuchBeanDefinitionException`. Register the bean via `@Component` or `@Bean` and verify the context.

### Exercise C: Bean Ambiguity

Register two implementations of the same interface. Observe `NoUniqueBeanDefinitionException`. Use `@Primary` or `@Qualifier` to resolve it according to application intent.

### Exercise D: Invalid Type Binding

Declare a `Duration` property and supply an invalid value. Distinguish conversion failure from validation failure caused by `@Min` or a similar constraint.

### Exercise E: Database Unavailable

Configure a JDBC URL pointing to a host/port with no listening database. Read the cause chain and distinguish `Connection refused` from authentication failure.

### Exercise F: Port Conflict

Run two instances using the same port. Identify the listening process and change the configuration intentionally. Never stop an unknown process.

### Exercise G: Dependency Conflict

Create an incompatible runtime classpath scenario in a test environment. Observe `NoSuchMethodError`, inspect the dependency tree, and determine which version is packaged.

### Exercise H: Condition Report

Run the application with `--debug`. Find an auto-configuration in positive/negative matches and explain the condition that caused it to apply or be skipped.

### Exercise I: First Application Frame

Create a constructor that throws `IllegalStateException` with a specific message. Read the stack trace, locate the first file/line in your application package, and trace back the invalid value.

### Exercise J: Suppressed Exception

Create a resource where both parse and close can throw exceptions. Observe the difference between cause and suppressed exceptions.

### Exercise K: Recording Root Cause

Pick a startup failure in a test environment and fill out the template in section 31. State the evidence confirming the cause and how to reverify.

## 33. Self-Check Questions

**1. Why should you not read only the outermost exception?**

Because it usually describes the error at the framework/container boundary; deeper causes often point to the specific property, dependency, or operation that failed.

**2. What does `Caused by` indicate?**

An exception linked as the cause of the current exception.

**3. How does a suppressed exception differ from a cause?**

Suppressed exceptions are secondary errors occurring while handling another exception, commonly during resource cleanup.

**4. Is the root cause always the deepest exception?**

No. You must read the entire chain, timeline, suppressed exceptions, and context.

**5. How is the first frame belonging to your application package useful?**

It usually pinpoints the method/file/line where application code entered the failing call path.

**6. What does `UnsatisfiedDependencyException` require you to check?**

The outermost bean, constructor parameters, bean candidates, component scan, profiles, conditions, and dependency registration.

**7. How does `NoUniqueBeanDefinitionException` differ from `NoSuchBeanDefinitionException`?**

One means no matching candidate was found; the other means multiple matching candidates exist and a single bean could not be chosen.

**8. What does `--debug` help with?**

It instructs Spring Boot to produce the Condition Evaluation Report showing auto-configuration matches, non-matches, and exclusions.

**9. Does `--debug` automatically set all loggers to DEBUG?**

No. It does not replace configuring logging levels for specific loggers.

**10. Why must you check active profiles?**

Profiles determine which configurations/beans are activated; an expected property may reside in an inactive profile.

**11. How does `Connection refused` differ from authentication failure?**

Connection refused typically happens at the TCP step; authentication failure occurs after connecting to the server when credentials/permissions are rejected.

**12. What does `NoSuchMethodError` usually suggest?**

Incompatible compile-time and runtime class versions/APIs, often due to dependency conflicts or stale artifacts.

**13. Why can one startup failure generate multiple subsequent exceptions?**

Beans depend on one another in chains; one failing bean prevents dependent beans from being created.

**14. Should you log the entire Environment when debugging?**

No, not if it could contain secrets. Inspect non-sensitive values and protect/mask configuration sources.

**15. What proves a root cause hypothesis?**

Evidence linking the error to configuration/code/environment, plus a rerun under identical conditions showing the old error disappears after an intentional change.

## 34. Conclusion

Reading startup logs effectively is a process of **separating layers and verifying causes**, not grabbing the first exception line and patching immediately. The outermost exception indicates whether Spring failed to create a bean, bind configuration, or start the server. The cause chain provides deeper reasons; the stack trace reveals the call path and application frames; and log lines before the failure expose profiles, dependencies, and environment state.

When diagnosing, start from Failure Analysis and the exception that aborted startup; read all `Caused by` and suppressed entries; locate application frames and inspect the exact revision; cross-reference active profiles, property sources, runtime dependencies, databases, ports, and runtime environments. Use `--debug` for condition evaluation and enable logging levels selectively. Finally, form a testable hypothesis, change one factor, and rerun under equivalent conditions.

A startup failure is usually the final symptom of a lower-level issue: a missing property, unregistered bean, incompatible dependency, unreadable resource, or unavailable external service. Reading log structure properly and testing hypotheses with evidence helps you reach the root cause faster and avoid editing components that merely appear along the exception chain.

