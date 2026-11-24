# FailureAnalyzer and Actionable Startup Error Messages

When a Spring Boot application fails to start, the cause often lies deep within the ApplicationContext creation chain: a missing bean, failed configuration binding, incompatible dependency, port already in use, or a component unable to connect to a required resource. A stack trace may contain all the technical data, yet operators still have to figure out **what went wrong and what to do next**.

Spring Boot provides the **FailureAnalyzer** mechanism to turn certain startup errors into more readable reports. An analyzer receives the exception, recognizes cases it understands, and returns two key parts:

- **Description:** a clear explanation of what failed and its context.
- **Action:** concrete guidance on how the operator can resolve it.

For example, instead of seeing only a long BeanCreationException, the application can display:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

The application cannot create the tenant client because
the required tenant identifier is missing.

Action:

Set app.tenant.id in the active configuration and restart
the application. For a local run, use:
--app.tenant.id=demo
~~~

This lesson covers Spring Boot's error-handling lifecycle, the roles of **FailureAnalyzer**, **AbstractFailureAnalyzer**, **FailureAnalysis**, and **FailureAnalysisReporter**, how to write custom analyzers, register them for Boot discovery, test both matching and non-matching exception paths, and follow guidelines for crafting helpful guidance without exposing sensitive data.

## 1. Why Are Stack Traces Not Enough?

A stack trace answers the question: **where did the exception occur and what call chain led to the error?** That is essential for developers, but it is not always the best way to guide operations.

For example, a missing configuration error might appear as:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'tenantClient'
...
Caused by: java.lang.IllegalStateException:
tenant id must not be blank
...
~~~

The reader must deduce on their own:

1. Which bean failed to be created?
2. Which value is missing?
3. What is the exact property key?
4. Which file or source needs the value?
5. Can it be fixed with a command-line argument or environment variable?

FailureAnalyzer helps turn those details into a structured report.

### 1.1. Stack Traces and FailureAnalysis Serve Different Purposes

| Information | Purpose |
|---|---|
| Exception type | Categorizes the error at the Java/framework layer. |
| Stack trace | Traces the error location and call chain. |
| Root cause | Explains the deeper reason in the exception chain. |
| FailureAnalysis description | Summarizes the incident in clear, contextual language. |
| FailureAnalysis action | Provides actionable next steps. |

FailureAnalysis **does not replace exceptions**. It adds a friendlier explanation; the exception can still be retained for technical diagnostics.

### 1.2. Examples of Common Startup Failures

An application may fail when:

- A required bean for injection cannot be found.
- Multiple beans of the same type exist and a single candidate cannot be chosen.
- A property cannot be converted to the required type.
- Required configuration is missing or invalid.
- The HTTP port is already in use by another process.
- No suitable web server factory is found.
- DataSource creation or connection to a required service fails.
- A dependency is incompatible with the running library versions.

Spring Boot already includes many built-in FailureAnalyzers for common scenarios. Write a custom analyzer only when you need to add **context specific to your application or library** that default messages do not express clearly enough.

## 2. Where Does FailureAnalyzer Fit in the Startup Lifecycle?

Spring Boot starts the application via SpringApplication. During this process, the framework prepares the Environment, creates the ApplicationContext, registers bean definitions, refreshes the context, and initializes required components.

If startup fails, SpringApplication handles the error and may ask FailureAnalyzers for a suitable interpretation.

~~~text
SpringApplication.run(...)
          │
          ▼
Prepare Environment / Config Data
          │
          ▼
Create ApplicationContext
          │
          ▼
Register bean definitions
          │
          ▼
Refresh context / initialize beans
          │
     ┌────┴─────┐
     │          │
  Success     Failure
     │          │
     ▼          ▼
Application  SpringApplication handles error
ready                │
                      ▼
              FailureAnalyzer(s)
                      │
                      ▼
               FailureAnalysis
                      │
                      ▼
              FailureAnalysisReporter
                      │
                      ▼
             Startup error report
~~~

This is a conceptual diagram. Failure analysis is integrated into Spring Boot's startup failure handling; not every exception thrown during application runtime automatically passes through this mechanism.

### 2.1. Analyzers Must Work Before ApplicationContext Is Ready

FailureAnalyzer runs precisely when the application fails during startup. The ApplicationContext may not have refreshed successfully, some beans may not exist yet, or bootstrap may have failed before a complete context exists.

Therefore, an analyzer should:

- Have self-contained exception recognition logic.
- Avoid depending on application service/repository beans.
- Not call databases or remote APIs to explain errors.
- Not assume `@Autowired` works like in a regular Spring component.
- Not modify configuration files or restart the system itself.

A good analyzer **observes and explains the error**, while the operator or deployment mechanism decides how to fix it.

### 2.2. FailureAnalyzer Is Not @ControllerAdvice

These two mechanisms handle errors at different times:

| Mechanism | Timing | Example |
|---|---|---|
| FailureAnalyzer | When Spring Boot startup fails | Missing property, bean creation failure, port busy. |
| @ControllerAdvice / @ExceptionHandler | When the application is running and handling HTTP requests | Invalid request data, missing resource, business error. |
| Service error handling | During business logic execution | Retry, fallback, exception translation per contract. |

Do not use FailureAnalyzer to format JSON error responses for a REST endpoint. Once the application is ready, request errors belong to runtime error handling.

### 2.3. Not Every Exception Produces a FailureAnalysis

A FailureAnalyzer may not recognize an exception and return **null**. Spring Boot then falls back to general error handling, and stack trace/exception information remains the diagnostic source.

Do not write a catch-all analyzer accepting every Throwable just to always print a message. That can hide critical details or provide misleading advice.

## 3. What Interface Is FailureAnalyzer?

Spring Boot provides:

~~~java
org.springframework.boot.diagnostics.FailureAnalyzer
~~~

The interface has one main method:

~~~java
FailureAnalysis analyze(Throwable failure);
~~~

The analyzer receives the original exception supplied by startup and returns:

- A FailureAnalysis if it recognizes the case.
- **null** if the case is outside the analyzer's responsibility.

Conceptual example:

~~~java
public final class MissingTenantFailureAnalyzer
        implements FailureAnalyzer {

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        if (failure instanceof MissingTenantException) {
            return new FailureAnalysis(
                    "Tenant configuration is missing.",
                    "Set app.tenant.id and restart.",
                    failure);
        }
        return null;
    }
}
~~~

This snippet illustrates the contract without handling exceptions wrapped inside BeanCreationException. In real applications, errors are often wrapped by multiple framework exception layers; later sections use AbstractFailureAnalyzer to locate matching causes.

### 3.1. What Does Returning null Mean?

If an analyzer does not know how to handle an exception, it should return null:

~~~java
@Override
public FailureAnalysis analyze(Throwable failure) {
    if (!isMyFailure(failure)) {
        return null;
    }

    return buildAnalysis(failure);
}
~~~

Returning null tells the failure analysis mechanism that **this analyzer does not provide a report for the current error**. It does not mean the application recovered or that startup can continue.

### 3.2. Do Not Throw New Exceptions from an Analyzer

An analyzer is invoked while handling a startup failure. If the analyzer itself throws another exception due to null dereferencing, file I/O, or remote calls, the original failure becomes harder to observe.

Keep analyzers simple, avoid side effects, and ensure unrecognized cases can always return null.

If message construction logic could fail, handle secondary errors carefully without losing the initial startup exception.

## 4. What Does FailureAnalysis Contain?

Class:

~~~java
org.springframework.boot.diagnostics.FailureAnalysis
~~~

A FailureAnalysis has three main parts:

| Component | Meaning |
|---|---|
| **description** | What failed? |
| **action** | What should the operator do? |
| **cause** | The Throwable associated with the incident. |

Construction:

~~~java
FailureAnalysis analysis = new FailureAnalysis(
        "The tenant identifier is missing.",
        "Set app.tenant.id in the active configuration.",
        exception);
~~~

### 4.1. Description Should Describe the Specific Incident

Weak message:

~~~text
Description:
Configuration error.
~~~

Better message:

~~~text
Description:
The tenant client could not be created because the
required property 'app.tenant.id' is missing.
~~~

The description should help the reader answer:

- Which component failed?
- Which condition was unmet?
- Which property, bean, resource, or dependency is involved?

Avoid repeating the exception class name verbatim if it does not help the operator understand the situation.

### 4.2. Action Must Offer Concrete Steps

Weak message:

~~~text
Action:
Check your configuration.
~~~

More specific message:

~~~text
Action:
Set 'app.tenant.id' in the active configuration source.
For a local run, pass:
--app.tenant.id=demo
~~~

A good Action can specify:

1. The property key or bean that must be supplied.
2. Appropriate configuration sources.
3. Accepted values or formats.
4. Verification commands or next steps.
5. How to restart after fixing.

Do not provide sample values that could accidentally point to production or real external systems.

### 4.3. Cause Preserves Technical Context

~~~java
return new FailureAnalysis(
        description,
        action,
        cause);
~~~

Cause preserves the link to the exception. Depending on the reporter and logging configuration, cause details/stack traces may also be shown.

Do not wrap with a new RuntimeException just to supply a cause if the original exception already carries useful details. Keeping the actual cause makes diagnosis more accurate.

## 5. FailureAnalysisReporter Is Responsible for Displaying Reports

FailureAnalyzer **does not directly decide how to print reports**. Spring Boot separates error recognition from presentation via:

~~~java
org.springframework.boot.diagnostics.FailureAnalysisReporter
~~~

The reporter receives the FailureAnalysis and decides how to deliver it to the operator.

Spring Boot includes a default reporter that writes failure analysis via logging. During a typical startup failure, users usually see a message block like:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

...

Action:

...
~~~

### 5.1. Benefits of Separating Analyzer and Reporter

An analyzer can focus on:

- Recognizing exceptions.
- Extracting meaningful details.
- Crafting description/action text.

The reporter focuses on:

- Printing to console/log.
- Forwarding the report to a suitable observability destination if using a custom integration.
- Deciding output formatting.

Thus, error explanation logic does not depend on a specific terminal, logger, or log collector.

### 5.2. When Do You Need a Custom Reporter?

Most applications only need the default reporter. A custom reporter is justified only for clear requirements, such as a specialized bootstrap environment or custom failure analysis presentation.

Do not send startup failure alerts via email, Slack, or remote services by default: network unavailability may be the exact cause of the startup failure, and external side effects can cause error reporting itself to fail.

### 5.3. Reporters Do Not Replace Recording Exceptions

If a custom reporter prints only description/action and drops the cause, operations teams can lose important technical data.

Consider:

- Retaining the exception type and cause.
- Avoiding printing secrets.
- Avoiding excessive duplicate stack traces.
- Keeping output easy to find in startup logs.

Unless there is a specific requirement, use Spring Boot's default reporter.

## 6. AbstractFailureAnalyzer Helps Match Exceptions in the Cause Chain

In practice, the exception SpringApplication receives is rarely the custom exception directly.

Example:

~~~text
BeanCreationException
  └── IllegalStateException
       └── MissingTenantConfigurationException
~~~

If you only write:

~~~java
if (failure instanceof MissingTenantConfigurationException) {
    // ...
}
~~~

the analyzer will not match when the outermost exception is BeanCreationException.

Spring Boot provides:

~~~java
org.springframework.boot.diagnostics.AbstractFailureAnalyzer
~~~

This class searches for a cause of the desired exception type in the cause chain, then invokes the corresponding analyze method.

~~~java
public abstract class AbstractFailureAnalyzer<T extends Throwable>
        implements FailureAnalyzer {

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        // Find a cause of type T and delegate to the subclass.
    }
}
~~~

This is a simplified conceptual illustration, not an implementation to rewrite yourself.

### 6.1. When Should You Extend AbstractFailureAnalyzer?

Suitable when:

- You have a specific exception defined by your application/library.
- The exception may be wrapped by the framework.
- You want to focus logic on a single cause type.
- You do not want to manually walk `getCause()` and handle cycles.

Example:

~~~java
public final class MissingTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                MissingTenantConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingTenantConfigurationException cause) {

        return new FailureAnalysis(
                "The tenant client cannot start because "
                        + "the tenant identifier is missing.",
                "Set 'app.tenant.id' in the active configuration "
                        + "and restart the application.",
                cause);
    }
}
~~~

**rootFailure** is the original exception the analyzer received; **cause** is the matching exception found in the cause chain.

### 6.2. Distinguishing rootFailure and cause

In the example:

~~~java
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause)
~~~

- **rootFailure** may be a BeanCreationException containing broader Spring context.
- **cause** is the MissingTenantConfigurationException carrying application-specific error details.

If the description only needs the property key and tenant configuration, using `cause` is enough. If you need the bean name or outer exception details, `rootFailure` can be useful.

Do not assume `cause` is the final root cause in every sense. AbstractFailureAnalyzer finds a matching cause by the analyzer's generic type; an exception chain can contain multiple cause types.

### 6.3. Implement FailureAnalyzer Directly for Special Logic

If you need to match multiple exception types or rules that do not fit a single generic type, implement FailureAnalyzer directly and traverse the cause chain in a controlled manner.

Helper example:

~~~java
static <T extends Throwable> T findCause(
        Throwable failure,
        Class<T> type) {

    Throwable current = failure;

    while (current != null) {
        if (type.isInstance(current)) {
            return type.cast(current);
        }
        current = current.getCause();
    }

    return null;
}
~~~

In real code, consider unusual cyclic cause chains; standard Java exceptions do not form such cycles, but general-purpose analyzers should avoid over-assuming.

If handling only one exception type, **AbstractFailureAnalyzer** is usually shorter and clearer.

## 7. Building a Custom Exception for Application Configuration Errors

Suppose a multi-tenant service requires a tenant ID to build its client. Without a tenant ID, the application cannot serve requests safely and should fail immediately at startup.

Define the exception:

~~~java
package com.example.tenant;

public class MissingTenantConfigurationException
        extends RuntimeException {

    public MissingTenantConfigurationException() {
        super("The required tenant identifier is missing");
    }
}
~~~

This exception represents a specific condition with a meaningful name. Avoid using generic IllegalStateException for every error if a library needs tailored guidance per error type.

### 7.1. Throw the Exception Where the Violation Is Detected

Example:

~~~java
package com.example.tenant;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.tenant")
public record TenantProperties(String id) {
}
~~~

Client bean:

~~~java
package com.example.tenant;

public final class TenantClient {

    private final String tenantId;

    public TenantClient(String tenantId) {
        this.tenantId = tenantId;
    }

    public String tenantId() {
        return tenantId;
    }
}
~~~

Configuration:

~~~java
package com.example.tenant;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(TenantProperties.class)
public class TenantClientAutoConfiguration {

    @Bean
    TenantClient tenantClient(TenantProperties properties) {
        if (properties.id() == null
                || properties.id().isBlank()) {
            throw new MissingTenantConfigurationException();
        }

        return new TenantClient(properties.id());
    }
}
~~~

This example illustrates an error proactively detected by the application/library. In a real application, if a missing property is a binding error detectable earlier, **@Validated and Bean Validation** may be better suited to fail right at binding. Custom exceptions are useful when conditions depend on logic or require domain-specific messaging.

### 7.2. Do Not Put Secret Values in Exception Messages

The exception:

~~~java
throw new MissingTenantConfigurationException();
~~~

only describes the missing key/condition. Avoid:

~~~java
throw new IllegalStateException(
        "Tenant secret was invalid: " + secret);
~~~

Exception messages can appear in stack traces, logs, or FailureAnalysis. Never put passwords, tokens, private keys, or personal data in messages.

### 7.3. Distinguish Missing Configuration from Malformed Configuration

You can define separately:

~~~java
public class InvalidTenantConfigurationException
        extends RuntimeException {
    public InvalidTenantConfigurationException(String message) {
        super(message);
    }
}
~~~

When different guidance is needed:

- MissingTenantConfigurationException: tenant ID has not been declared.
- InvalidTenantConfigurationException: tenant ID is present but does not match a supported format.

Separating exceptions by scenario helps analyzers produce accurate Actions. Do not create dozens of exceptions just to tweak minor wording; split only when causes and remedies genuinely differ.

## 8. Writing MissingTenantFailureAnalyzer

Create the class:

~~~java
package com.example.tenant.diagnostics;

import com.example.tenant.MissingTenantConfigurationException;
import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class MissingTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                MissingTenantConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingTenantConfigurationException cause) {

        String description =
                "The tenant client cannot be created because "
                + "the required property 'app.tenant.id' is missing.";

        String action =
                "Set 'app.tenant.id' in the active configuration. "
                + "For a local run, pass "
                + "'--app.tenant.id=demo' and restart the application.";

        return new FailureAnalysis(
                description,
                action,
                cause);
    }
}
~~~

### 8.1. Why Doesn't the Analyzer Need @Component?

FailureAnalyzer is discovered by Spring Boot via the framework's factory discovery mechanism without waiting for ApplicationContext component scanning.

An analyzer can be invoked when the context has not been created successfully. Marking it solely with `@Component` makes it rely on a context that may not have finished scanning/registering beans.

For custom FailureAnalyzers, register them through the **SpringFactoriesLoader** mechanism Boot uses for this extension type.

### 8.2. An Analyzer Should Do Minimal Work

Inside `analyze()`:

- Read information already present on the exception.
- Build the description and action.
- Return the FailureAnalysis.

Do not:

- Create a new ApplicationContext.
- Re-run SpringApplication.
- Query a database to verify configuration.
- Make HTTP requests to external services.
- Modify YAML files or environment variables.
- Restart the process itself.

When startup has already failed, external dependencies may be unavailable. The fewer side effects an analyzer has, the more reliable it is during an incident.

### 8.3. Action Should Point to Valid Configuration Sources

A message like:

~~~text
Set app.tenant.id.
~~~

may not be enough for applications with multiple configuration sources.

You can clarify:

~~~text
Set 'app.tenant.id' in the active Spring Boot configuration.
You can provide it in application.yml, an external Config Data
file, an environment variable, or a command-line argument.
~~~

If an environment follows a specific deployment convention, the guidance should reflect it. There is no need to list every possible configuration source if your organization permits only a single standard source.

## 9. Registering FailureAnalyzer via META-INF/spring.factories

For Spring Boot to discover the custom analyzer, add the file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Content:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer
~~~

This metadata is read by the Spring factories mechanism.

### 9.1. The Path Must Be Exact

The file must reside inside resources:

~~~text
src/main/
└── resources/
    └── META-INF/
        └── spring.factories
~~~

After packaging, the metadata must exist inside the JAR at:

~~~text
META-INF/spring.factories
~~~

If the file is only in `src/test/resources`, the analyzer may appear on the test classpath but will not be packaged into the runtime artifact.

### 9.2. Do Not Confuse with AutoConfiguration.imports

Spring Boot 3 uses the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

to register auto-configuration classes.

That is a different mechanism from registering FailureAnalyzer.

| Extension | Typical Metadata |
|---|---|
| FailureAnalyzer | META-INF/spring.factories |
| FailureAnalysisReporter | META-INF/spring.factories |
| Boot 3 auto-configuration class | META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports |

Do not place MissingTenantFailureAnalyzer into AutoConfiguration.imports as if it were an `@AutoConfiguration`.

### 9.3. If spring.factories Already Exists

A module may already use `spring.factories` to register other extensions. **Append the key/value** for FailureAnalyzer while keeping existing entries intact.

Example:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer

org.springframework.boot.diagnostics.FailureAnalysisReporter=\
com.example.tenant.diagnostics.CustomFailureAnalysisReporter
~~~

This example shows two different extensions. You do not need to create CustomFailureAnalysisReporter if the default reporter meets your needs.

### 9.4. Multiple Analyzers Can Be Registered

If a library has multiple distinct scenarios:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer,\
com.example.tenant.diagnostics.InvalidTenantFailureAnalyzer
~~~

Each analyzer should recognize a clearly bounded error scope and return null for anything outside it.

Avoid letting multiple analyzers match the same exception with conflicting messages. If competing analyzers exist, review how Boot orders/applies them in your version and design sufficiently specific exception types/conditions.

### 9.5. The Analyzer Must Be on the Runtime Classpath

If the analyzer lives in a separate starter, the application's dependencies must pull that artifact onto the runtime classpath.

A class that compiles successfully yet is absent from the runtime artifact/classpath cannot be discovered by Spring Boot.

When diagnosing, check:

- Is the analyzer class packaged?
- Is `META-INF/spring.factories` inside the JAR?
- Is the fully qualified class name exact?
- Can the constructor be instantiated as required by discovery?
- Was there an exception while loading the analyzer?

## 10. Writing an Analyzer for Invalid Configuration Errors

An application can distinguish a missing tenant ID from a malformed tenant ID.

Exception:

~~~java
package com.example.tenant;

public class InvalidTenantConfigurationException
        extends RuntimeException {

    public InvalidTenantConfigurationException() {
        super("The tenant identifier has an unsupported format");
    }
}
~~~

Analyzer:

~~~java
package com.example.tenant.diagnostics;

import com.example.tenant.InvalidTenantConfigurationException;
import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class InvalidTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                InvalidTenantConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            InvalidTenantConfigurationException cause) {

        return new FailureAnalysis(
                "The configured tenant identifier does not match "
                        + "the supported format.",
                "Check 'app.tenant.id'. Use the tenant identifier "
                        + "issued by the platform and follow the "
                        + "documented format.",
                cause);
    }
}
~~~

Register both analyzers in `spring.factories`:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer,\
com.example.tenant.diagnostics.InvalidTenantFailureAnalyzer
~~~

Each analyzer recognizes a distinct exception type. This ensures:

- Descriptions do not have to guess the cause.
- Actions match each error type.
- Unit tests can verify each scenario independently.
- As the library evolves, each error's contract is easier to protect.

### 10.1. When an Exception Has Multiple Causes

A startup error can involve multiple nested exceptions:

~~~text
UnsatisfiedDependencyException
  └── BeanCreationException
       └── IllegalStateException
            └── InvalidTenantConfigurationException
~~~

AbstractFailureAnalyzer locates the matching cause by generic type. There is no need to inspect every Spring wrapper manually when the specific cause is represented by a custom exception.

### 10.2. Do Not Rely on Message Text to Recognize Errors

Fragile example:

~~~java
if (failure.getMessage().contains("tenant id")) {
    // ...
}
~~~

Messages can change across framework versions, locales, or exception wrapping. They can also contain user-supplied data.

Prefer matching by **exception type**:

~~~java
extends AbstractFailureAnalyzer<
        MissingTenantConfigurationException>
~~~

If you do not own the exception type, you may need a direct analyzer or to inspect a specific framework exception type. In that case, narrow the scope, check cause/type, and avoid depending on unstable wording.

## 11. Characteristics of Good Actionable Guidance

FailureAnalysis can be printed prominently on the console when startup fails. Treat it as a message written for the person responsible for restoring the service to working order.

A helpful message typically includes:

1. **Component name:** the bean, integration, or feature that failed to start.
2. **Failure condition:** missing property, invalid format, missing dependency, or unavailable resource.
3. **Specific cause:** relevant key/port/type/location if safe to display.
4. **Concrete action:** configuration step, dependency installation, or resource cleanup.
5. **Applicable scope:** local, test, staging, or production if known with certainty.
6. **Verification step:** how to recheck after fixing.

### 11.1. Description and Action Should Not Repeat Each Other

Weak example:

~~~text
Description:
The tenant id is missing.

Action:
The tenant id is missing. Add the tenant id.
~~~

Better:

~~~text
Description:
The tenant client cannot be initialized because
'app.tenant.id' has no value.

Action:
Provide a non-empty 'app.tenant.id' in the active
configuration source, then restart the application.
~~~

Description states **what happened**. Action states **what the reader should do**.

### 11.2. Guidance Must Match the Cause

If port 8080 is already in use, the message:

~~~text
Set server.port to another value or stop the process
that is already listening on port 8080.
~~~

is more specific than:

~~~text
Check the configuration.
~~~

If the error is a missing database driver, advising to add the proper dependency to the runtime classpath makes more sense than changing `server.port`.

Do not reuse one generic Action across all errors just to reduce the number of analyzers.

### 11.3. State Only Information the Analyzer Can Prove

If the analyzer knows a property is missing, it can say the property is missing.

If the analyzer does not know the exact configuration file used, it should not assert:

~~~text
Edit /etc/order-api/application-prod.yml.
~~~

unless the deployment contract guarantees that location.

General yet accurate guidance:

~~~text
Set 'app.tenant.id' in the active Spring Boot configuration
source, then restart the application.
~~~

### 11.4. Give Command Examples Only When Safe

A local example:

~~~bash
java -jar app.jar --app.tenant.id=demo
~~~

can be helpful if the demo value is non-sensitive and acceptable in local environments.

Never include commands with real passwords, API tokens, or credentials in Actions. Do not recommend demo values for production when an official tenant ID source is required.

## 12. Reporting Port-In-Use Errors

Spring Boot includes built-in analyzers for common failures like a port already being occupied—for example, when a web server attempts to start on port 8080 while another process is listening on it.

Descriptions typically guide operators to:

- Identify the process using the port.
- Stop that process if it is no longer needed.
- Or configure the application to use a different port.

On Linux, system tools can inspect sockets; on Windows, equivalent tools exist. Avoid embedding OS-specific commands for all environments if the analyzer does not know the operator's OS or permissions.

### 12.1. Changing the Port via Spring Boot Configuration

Example:

~~~yaml
server:
  port: 8081
~~~

Or:

~~~bash
java -jar app.jar --server.port=8081
~~~

This illustrates a feasible action. In production, changing the port must also stay in sync with service discovery, ingress, load balancers, and health checks.

### 12.2. Never Free a Port Automatically Inside FailureAnalyzer

An analyzer should not find and kill processes to "fix" a port error. It should only describe the cause and suggest actions.

Automatically terminating another process can cause service outages or disrupt unrelated workloads.

## 13. Spring Boot's Built-in FailureAnalyzers

Spring Boot provides analyzers for many common errors. Exact names and supported cases can change across versions.

Categories that commonly have diagnostic messages:

| Error Category | Guidance an Analyzer Can Provide |
|---|---|
| Missing bean / dependency | Which bean was not found and how to register the required dependency. |
| Multiple beans of same type | Which candidates caused ambiguity and how to use `@Primary`/`@Qualifier` or remove extra beans. |
| Configuration binding | Which property failed to bind and related values/types. |
| Port in use | Which port failed to bind and how to choose another port or free it. |
| Missing web server factory | Dependencies/configuration needed to run a web application. |
| Bean definition conflict | Conflicting bean names and related configuration options. |

These are illustrative categories, not an exhaustive list or guarantee that every case in a category has a dedicated analyzer in every version.

### 13.1. Read Default Messages Before Writing a Custom Analyzer

If Spring Boot already produces a clear enough FailureAnalysis, do not write another analyzer merely to rephrase the same cause.

A custom analyzer may be needed when:

- The exception belongs to an internal library or custom domain.
- Default messages lack application-specific property/bean names.
- Guidance must reflect a specific deployment contract.
- A generic technical error needs interpretation in product context.

### 13.2. Do Not Try to Replace All Built-in Analyzers

An overly broad custom analyzer—for instance catching every BeanCreationException—can compete with built-in analyzers and produce wrong Actions for unrelated failures.

Match a specific cause or let Boot's built-in analyzers handle it. If you only need extra details, improve where the exception originates so it carries a more meaningful cause.

### 13.3. Version Compatibility

When upgrading Spring Boot versions:

- Check the packages/APIs of FailureAnalyzer and FailureAnalysis.
- Verify that `spring.factories` registration is still supported for this extension.
- Run tests against the project's managed dependency versions.
- Inspect actual startup failure output.

Do not assume that because Boot 3 auto-configuration uses `AutoConfiguration.imports`, every other extension factory also moved to that file. FailureAnalyzer remains under Spring Boot's dedicated factory discovery mechanism.

## 14. Distinguishing FailureAnalyzer from ApplicationContextInitializer and Listeners

Several extensions run during bootstrap, but their purposes differ:

| Extension | Role |
|---|---|
| ApplicationContextInitializer | Customizes ApplicationContext before refresh. |
| ApplicationListener | Listens to application events. |
| EnvironmentPostProcessor | Adjusts Environment before context creation/refresh per supported lifecycle. |
| FailureAnalyzer | Translates startup exceptions into FailureAnalysis. |
| FailureAnalysisReporter | Presents/logs FailureAnalysis. |

Do not use FailureAnalyzer to add properties to the Environment. If you need to load property sources before beans are created, look at Config Data or EnvironmentPostProcessor as needed.

### 14.1. Analyzers Are Not for Retrying Startup

If a database is temporarily unavailable, an analyzer can explain the connection failure and note the configured endpoint/timeout (if safe).

However, an analyzer is not the place for infinite retries or waiting for a database to come up. Retries belong to connection/client mechanisms, orchestration, or startup readiness policies.

### 14.2. Do Not Use ApplicationReadyEvent to Catch Startup Failures

ApplicationReadyEvent is only published once the application is ready per its lifecycle. If context refresh fails, this event is not a suitable error-handling mechanism.

FailureAnalyzer integrates into SpringApplication's startup failure handling flow, making it appropriate for explaining why startup failed.

## 15. Unit Testing a FailureAnalyzer

An analyzer should be tested as a standalone Java class. You do not need to start a full web application just to verify description/action output.

### 15.1. Testing Matching Exceptions

~~~java
package com.example.tenant.diagnostics;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.tenant.MissingTenantConfigurationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.BeanCreationException;
import org.springframework.boot.diagnostics.FailureAnalysis;

class MissingTenantFailureAnalyzerTests {

    private final MissingTenantFailureAnalyzer analyzer =
            new MissingTenantFailureAnalyzer();

    @Test
    void createsActionableAnalysisForMissingTenant() {
        Throwable failure = new BeanCreationException(
                "tenantClient",
                new MissingTenantConfigurationException());

        FailureAnalysis analysis = analyzer.analyze(failure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .contains("app.tenant.id");
        assertThat(analysis.getAction())
                .contains("--app.tenant.id=demo");
        assertThat(analysis.getCause())
                .isInstanceOf(
                        MissingTenantConfigurationException.class);
    }
}
~~~

This test proves the analyzer can locate the custom exception nested inside BeanCreationException and return the expected message.

### 15.2. Testing Unrecognized Exceptions

~~~java
@Test
void returnsNullForAnUnrelatedFailure() {
    FailureAnalysis analysis =
            analyzer.analyze(
                    new IllegalArgumentException("unrelated"));

    assertThat(analysis).isNull();
}
~~~

This is an important test. An analyzer must handle only errors within its scope; unrelated exceptions must be left to other analyzers or general handling.

### 15.3. Testing Multiple Exception Types

For InvalidTenantFailureAnalyzer:

~~~java
@Test
void createsAnalysisForInvalidTenant() {
    FailureAnalysis analysis =
            new InvalidTenantFailureAnalyzer().analyze(
                    new InvalidTenantConfigurationException());

    assertThat(analysis).isNotNull();
    assertThat(analysis.getDescription())
            .contains("unsupported format");
    assertThat(analysis.getAction())
            .contains("app.tenant.id");
}
~~~

Splitting tests per analyzer allows messages to evolve independently without breaking other error cases.

### 15.4. Do Not Couple Tests to Full Output Formatting

Avoid locking tests to exact asterisk lines, whitespace, or terminal colors. Those presentation details belong to the reporter and may change across versions.

For analyzer unit tests, verify:

- Does the analyzer recognize the right exception?
- Does the Description contain the required information?
- Does the Action provide executable guidance?
- Is the Cause preserved accurately?
- Do out-of-scope exceptions return null?

## 16. Verifying Real Exceptions in ApplicationContextRunner

Direct unit tests validate the analyzer's logic. You can add a lightweight context test to ensure bean configuration actually throws the expected exception.

~~~java
package com.example.tenant;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class TenantClientStartupTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            TenantClientAutoConfiguration.class));

    @Test
    void startupFailsWhenTenantIdIsMissing() {
        runner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                            MissingTenantConfigurationException.class);
        });
    }

    @Test
    void startupSucceedsWhenTenantIdIsProvided() {
        runner.withPropertyValues(
                    "app.tenant.id=demo")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(TenantClient.class);
                    assertThat(context.getBean(TenantClient.class)
                            .tenantId())
                            .isEqualTo("demo");
                });
    }
}
~~~

This test verifies startup conditions in auto-configuration:

- Without tenant ID → context fails with the expected cause.
- With tenant ID → context creates TenantClient.

### 16.1. ApplicationContextRunner Does Not Run FailureAnalyzer Like SpringApplication

This distinction matters:

- ApplicationContextRunner is useful for testing **context startup** and capturing startup failures.
- It is not a full run through SpringApplication's failure handling/reporting lifecycle.
- Therefore, the context runner test above **does not prove** that the custom analyzer was discovered by Spring Boot from `spring.factories` or printed by the reporter.

You can feed the startup failure from the runner into the analyzer in a combined test:

~~~java
@Test
void analyzesTheActualContextStartupFailure() {
    runner.run(context -> {
        assertThat(context).hasFailed();

        FailureAnalysis analysis =
                new MissingTenantFailureAnalyzer().analyze(
                        context.getStartupFailure());

        assertThat(analysis).isNotNull();
        assertThat(analysis.getAction())
                .contains("app.tenant.id");
    });
}
~~~

This still tests **analyzer logic on a real exception**, not factory discovery or reporting.

### 16.2. Do Not Let Intentionally Failing Contexts Break the Test Suite

ApplicationContextRunner captures startup exceptions inside AssertableApplicationContext and lets callbacks inspect them. Thus, a test intentionally verifying startup failure can still pass.

Do not use `@SpringBootTest` for an application that intentionally fails startup without an appropriate harness, as the test runner may treat context initialization failure as a test error before you can assert on it.

## 17. Integration Testing to Confirm Spring Boot Discovers the Analyzer

Analyzer unit tests do not verify that `spring.factories` is packaged properly. For a starter or library distributed to consumers, artifact/runtime-level verification is necessary.

A smoke test workflow:

1. Build the JAR containing the analyzer and `META-INF/spring.factories`.
2. Verify the metadata actually resides in the artifact.
3. Run a sample application capable of triggering the custom exception at startup.
4. Intentionally omit `app.tenant.id` so startup fails.
5. Capture startup output.
6. Confirm the description/action provided by the analyzer appears.
7. Supply a valid `app.tenant.id` and confirm the application starts.

Example run command:

~~~bash
java -jar tenant-demo.jar
~~~

Without a tenant ID, expected output includes:

~~~text
APPLICATION FAILED TO START

Description:
The tenant client cannot be created because the required
property 'app.tenant.id' is missing.

Action:
Set 'app.tenant.id' in the active configuration...
~~~

Then run:

~~~bash
java -jar tenant-demo.jar --app.tenant.id=demo
~~~

and confirm startup succeeds.

### 17.1. Checking Metadata Inside the JAR

In an environment with JDK tools:

~~~bash
jar tf tenant-starter.jar
~~~

Look for:

~~~text
META-INF/spring.factories
com/example/tenant/diagnostics/MissingTenantFailureAnalyzer.class
~~~

A Spring Boot executable JAR may contain nested dependency JARs inside `BOOT-INF/lib`. Make sure to identify which artifact owns the analyzer and inspect that JAR for the class/metadata, not just the outer executable JAR.

### 17.2. A Small Consumer Test Can Catch Registration Bugs

If the starter is published as a dependency:

~~~text
tenant-starter.jar
       │
       ▼
consumer-demo application
       │
       ▼
SpringApplication.run(...)
       │
       ▼
startup failure triggered intentionally
       │
       ▼
failure report must contain custom description/action
~~~

This provides evidence much closer to real library usage than instantiating the analyzer directly with `new`.

### 17.3. Do Not Assume Only One Way to Test the Reporter

If an application needs to verify exact reporter output, it can launch a child process and capture stdout/stderr. A child process isolates global logging state and startup lifecycle from the JVM running the tests.

Avoid coupling tests to exact formatting characters if the contract only cares about description/action. Define the required output contract and keep tests resilient across versions.

## 18. Testing Registration via SpringFactoriesLoader

FailureAnalyzer is discovered via Spring factories metadata. You can add a test verifying the library declares the analyzer properly on the test/runtime classpath.

Conceptual example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalyzer;
import org.springframework.core.io.support.SpringFactoriesLoader;

class FailureAnalyzerRegistrationTests {

    @Test
    void registersMissingTenantAnalyzer() {
        List<FailureAnalyzer> analyzers =
                SpringFactoriesLoader.loadFactories(
                        FailureAnalyzer.class,
                        getClass().getClassLoader());

        assertThat(analyzers)
                .anyMatch(
                        MissingTenantFailureAnalyzer.class::isInstance);
    }
}
~~~

The snippet illustrates the Spring Framework 6 API using `SpringFactoriesLoader`. If your project uses a different Spring Framework version, check the API signature matching your managed dependencies.

This test only verifies **factory discovery on the test classpath**. It does not prove:

- That metadata was packaged into the release artifact.
- That real consumers have the dependency at runtime.
- That SpringApplication invoked the analyzer for a given startup failure.
- That the reporter formatted output as expected.

Therefore, metadata tests and integration smoke tests serve different goals.

## 19. When You Need a Custom FailureAnalysisReporter

Most applications do not need to replace the default reporter. However, to understand the architecture, a simple reporter can be imagined as:

~~~java
package com.example.tenant.diagnostics;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalysisReporter;

public final class ConsoleFailureAnalysisReporter
        implements FailureAnalysisReporter {

    @Override
    public void report(FailureAnalysis analysis) {
        System.err.println("APPLICATION FAILED TO START");
        System.err.println();
        System.err.println("Description:");
        System.err.println(analysis.getDescription());
        System.err.println();
        System.err.println("Action:");
        System.err.println(analysis.getAction());
    }
}
~~~

Registration:

~~~properties
org.springframework.boot.diagnostics.FailureAnalysisReporter=\
com.example.tenant.diagnostics.ConsoleFailureAnalysisReporter
~~~

This example illustrates the reporter interface, **not a recommendation to replace the default reporter**. A custom reporter can:

- Lose formatting or cause information provided by the default reporter.
- Produce duplicate output if the default reporter remains registered.
- Write to the wrong stream so log collectors miss it.
- Cause new errors while reporting a startup failure.

If you want to customize output, review the existing reporter policy, how Spring Boot discovers multiple reporters in your version, and your exact objective. Do not register a new reporter just to change a header line.

### 19.1. Reporters Must Also Not Depend on Application Beans

Reporters run during the same startup failure phase. Do not require an `@Service` bean or live database connection just to print a message.

If a reporter needs configuration, prefer a simple constructor or data readable safely from the bootstrap environment; never assume ApplicationContext is complete.

## 20. Creating Messages for Configuration Binding Errors

Spring Boot binds properties into `@ConfigurationProperties`. When a value cannot be converted or violates validation, startup can fail with an exception from the binding/validation layer.

Example:

~~~java
package com.example.payment;

import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotNull Duration timeout,
        @Positive int maxAttempts) {
}
~~~

application.yml:

~~~yaml
app:
  payment:
    timeout: not-a-duration
    max-attempts: 3
~~~

The timeout value cannot convert to Duration, so binding fails.

### 20.1. Prefer Clear Validation Before Writing an Analyzer

When an error is an invalid property, it is usually better to:

- Use appropriate data types in `@ConfigurationProperties`.
- Use Jakarta Bean Validation such as `@NotBlank`, `@NotNull`, `@Positive`, `@Min`, `@Max` where appropriate.
- Provide clear validation messages.
- Provide sensible defaults if the property is genuinely optional.

Spring Boot already provides diagnostics for many binding errors. Only add a FailureAnalyzer when you need to translate a generic technical error into domain/deployment guidance.

### 20.2. A Domain Analyzer Can Explain Property Semantics

For example, when a property is present but unsupported by the system:

~~~text
Description:
The configured payment mode 'legacy-x' is not supported
by this version of the application.

Action:
Set 'app.payment.mode' to one of the supported values:
'sandbox' or 'live'. Confirm the selected mode with the
deployment configuration before restarting.
~~~

This is more helpful than a conversion error or IllegalArgumentException if operators need to know the valid values.

### 20.3. Do Not Echo Full Configuration Values in Reports

If a property holds credentials, URLs with query tokens, or sensitive data, do not print the raw value in Description.

You can state:

~~~text
The configured payment credential is invalid or unavailable.
~~~

and:

~~~text
Verify that the required secret is mounted and that the
service account can read it. Do not paste the secret into logs.
~~~

An analyzer should explain how to verify safely rather than dumping secrets into logs for convenience.

## 21. Handling Missing Bean and Multiple Bean Errors

Spring Boot can provide FailureAnalysis for several common dependency injection scenarios.

### 21.1. Missing Bean

Example:

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator calculator;

    public InvoiceService(TaxCalculator calculator) {
        this.calculator = calculator;
    }
}
~~~

If no matching TaxCalculator bean exists, the context cannot create InvoiceService.

Guidance messages can point out:

- Which type needs to be registered.
- Which bean requires that dependency.
- How to declare `@Component`/`@Bean` or add the appropriate auto-configuration/dependency.

### 21.2. Multiple Beans of the Same Type

~~~java
@Bean
TaxCalculator localTaxCalculator() {
    return new LocalTaxCalculator();
}

@Bean
TaxCalculator regionalTaxCalculator() {
    return new RegionalTaxCalculator();
}
~~~

If a service injects TaxCalculator without a qualifier/primary or selection rule, Spring cannot determine a unique candidate.

An Action can guide the user to:

- Mark a default bean with `@Primary` if there is a clear default choice.
- Use `@Qualifier` at the injection point when selecting a specific implementation.
- Remove unnecessary beans.

### 21.3. Do Not Write a Generic Analyzer for All BeanCreationExceptions

BeanCreationException can represent many different causes:

- A constructor threw an exception.
- A dependency does not exist.
- Property binding failed.
- A file resource is unreadable.
- An external system connection failed.
- Third-party library initialization failed.

An analyzer catching every BeanCreationException and always saying "check component scan" will give wrong advice in many cases.

Match specific causes or let Boot's built-in analyzers handle them.

## 22. Analyzing Exception Chains Properly

A startup error is often wrapped multiple times:

~~~text
ApplicationContextException
  └── BeanCreationException
       └── UnsatisfiedDependencyException
            └── IllegalStateException
                 └── MissingTenantConfigurationException
~~~

### 22.1. Do Not Look Only at the Outermost Exception

The outermost exception typically describes failure at the framework layer. Inner root/cause exceptions often carry more important domain context.

AbstractFailureAnalyzer helps locate causes by generic type, avoiding manual inspection of every wrapper layer.

### 22.2. When Multiple Causes Share the Same Type

A cause chain may contain multiple exceptions of the same type. AbstractFailureAnalyzer finds a matching cause according to its mechanism; if messages need to distinguish different locations, you can:

- Use distinct exception subtypes.
- Attach safe contextual metadata to the exception.
- Implement FailureAnalyzer directly with intentional cause lookup logic.

Do not parse stack trace strings to determine beans or properties.

### 22.3. Suppressed Exceptions Are Not Necessarily Causes

Java can attach suppressed exceptions when closing a resource fails in try-with-resources. Suppressed exceptions do not necessarily appear on the `getCause()` chain.

If a startup failure depends on a cleanup error, an analyzer traversing only the cause chain might miss the suppressed exception. Preserve the original exception and use appropriate stack trace/diagnostics; do not assume every related exception is a direct cause.

## 23. Logging and FailureAnalysis

When startup fails, FailureAnalysis is usually passed through the default reporter and logging system. However, an analyzer should not log the full error itself only for the reporter to log it again.

Avoid:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    log.error("Tenant config failed", rootFailure);

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set app.tenant.id.",
            cause);
}
~~~

This can produce duplicate output, especially when the startup framework also logs the exception/analysis.

Prefer:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set 'app.tenant.id' in the active configuration.",
            cause);
}
~~~

Let the reporter handle presentation. If extra logging is needed, define clearly where it is written and avoid repeating stack traces.

### 23.1. Startup Failures Still Require a Non-Zero Exit Code

FailureAnalyzer does not turn a startup failure into startup success. The application still fails, and launchers/orchestrators must recognize that the process failed to start.

In CI/CD or container orchestration:

- Process exit codes must be treated as failures.
- Do not just grep for "APPLICATION FAILED TO START" and treat that as the entire status.
- Use health/readiness checks to monitor status after the application is running.

### 23.2. FailureAnalysis Does Not Replace Readiness/Liveness Probes

FailureAnalyzer handles startup errors. Kubernetes readiness/liveness probes and Actuator health endpoints monitor running processes/containers.

Do not use an analyzer to explain a pod that started successfully and later lost database connectivity. That belongs to runtime monitoring, health checks, and logging.

## 24. Environment-Specific Guidance: Local, Test, and Production

Actions should suit known environments without guessing the environment from hostnames or working directories.

### 24.1. Local Development

Example:

~~~text
Action:
For a local run, add the following property to your
application-local.yml or pass it as a command-line argument:
--app.tenant.id=demo
~~~

The demo value is appropriate only if local systems accept a mock tenant.

### 24.2. Test

~~~text
Action:
Provide app.tenant.id in the test properties or test
configuration before starting the application context.
~~~

Do not recommend using production tenants in tests just to pass startup validation.

### 24.3. Production

~~~text
Action:
Verify that the deployment supplies app.tenant.id through
the approved configuration source. Confirm the mounted
configuration/secret and restart the affected instance.
~~~

Do not instruct operators to edit a file directly inside a container if deployment manages it via ConfigMap, Secret, or a centralized configuration system.

### 24.4. Do Not Guess Active Profiles

An analyzer can inspect an exception without necessarily having a complete Environment. Do not hardcode an Action like "edit application-prod.yml" simply because the app typically runs in production.

If an analyzer is genuinely designed to receive Environment safely during bootstrap, provide it explicitly and test that lifecycle. In simpler designs, guide via property keys and deployment-managed configuration sources.

## 25. Error Messages and Security

Startup errors are often written to consoles, log collectors, CI output, and monitoring systems. An inappropriate FailureAnalysis can leak:

- Passwords or tokens.
- Internal hostnames, IPs, and topology.
- File paths containing usernames or sensitive details.
- Raw configuration contents.
- Request payloads or personal data.

### 25.1. Do Not Include Secrets in Description or Action

Do not:

~~~java
String action = "Use API key " + apiKey
        + " in your deployment environment.";
~~~

Do:

~~~java
String action =
        "Verify that the required API key is available "
        + "from the approved secret source.";
~~~

### 25.2. Do Not Print Full Exception Messages If They May Contain Sensitive Data

If a custom exception is built from user input, the message may hold unsafe content. Analyzers should construct descriptions from controlled fields rather than concatenating `exception.getMessage()` blindly in every case.

### 25.3. Avoid Over-Exposing Internal Infrastructure Details

In production, an Action can say:

~~~text
Verify the configured database endpoint and the service
account's access through the approved deployment tooling.
~~~

instead of printing connection strings, subnets, usernames, and credentials.

Specific information is helpful, but show only data the output reader is authorized to see.

### 25.4. FailureAnalysis Is Not a Place for Automated Remediation Scripts

Do not embed scripts to delete files, kill processes, change permissions, or alter production configs in an Action implying users should run them unverified.

Actions should describe safe, verifiable operations suited to the operator's permissions.

## 26. Investigation Steps When a Custom FailureAnalyzer Does Not Work

Suppose startup fails, yet the console only prints a stack trace or default message. Check layer by layer.

### Step 1 — Confirm the Error Occurs During the Startup Lifecycle

FailureAnalyzer is called by Spring Boot when handling startup failures. If the error happens during an HTTP request after the app is ready, use runtime exception handling, logging, and monitoring.

### Step 2 — Confirm the Analyzer Matches the Right Exception Type

If the analyzer extends:

~~~java
AbstractFailureAnalyzer<MissingTenantConfigurationException>
~~~

then that exception must appear in the startup failure's cause chain.

If there is only an IllegalStateException with a similar message but no custom exception, the analyzer will not match.

### Step 3 — Check Whether the Exception Is Wrapped

If the analyzer implements FailureAnalyzer directly and only checks `instanceof` on the root failure, it may miss an enclosing BeanCreationException.

Extend AbstractFailureAnalyzer for a specific cause type or traverse the cause chain intentionally when justified.

### Step 4 — Check spring.factories Metadata

Exact path:

~~~text
META-INF/spring.factories
~~~

Exact key:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer
~~~

Class names must be fully qualified. If the file has multiple entries, do not overwrite existing registrations.

### Step 5 — Check That the Class Is on the Runtime Classpath

An analyzer may compile within a module yet its dependency might not be packaged into the runtime artifact. Check dependency scopes and JAR contents.

### Step 6 — Check Instantiation Requirements

Spring factories loader must be able to instantiate the analyzer. Use a public, concrete class with a simple constructor; avoid constructors requiring application services that cannot exist yet.

### Step 7 — Check If the Analyzer Throws an Exception

An analyzer failing while creating FailureAnalysis complicates error reporting. Keep logic pure and avoid null dereferences or external resources.

### Step 8 — Confirm the Analyzer Returns FailureAnalysis Rather Than null

If the type matches but the code has additional conditions, verify whether those conditions filter out real cases.

### Step 9 — Check the Reporter

If the analyzer returns an analysis yet output is unexpected, check which reporter is registered and where logging/console output is routed.

### Step 10 — Run a Startup Smoke Test with the Actual Artifact

A unit test invoking the analyzer directly does not test JAR discovery. Run a consumer sample with the same dependencies/artifacts as deployment.

## 27. Common Mistakes and How to Fix Them

### 27.1. Annotating with @Component and the Analyzer Never Runs

**Symptom:** the class has `@Component`, compiles cleanly, yet startup reports lack the custom message.

**Cause:** FailureAnalyzer is not discovered via normal component scanning; it is registered via Spring factories metadata.

**Fix:** add the implementation to `META-INF/spring.factories` under the key `org.springframework.boot.diagnostics.FailureAnalyzer`.

### 27.2. Putting the Analyzer in AutoConfiguration.imports

**Symptom:** the imports file lists the analyzer class, but Boot does not process it as expected.

**Cause:** `AutoConfiguration.imports` registers auto-configuration classes, not FailureAnalyzers.

**Fix:** register analyzers via `spring.factories`; keep auto-configurations in their own imports metadata.

### 27.3. Analyzer Fails to Match Wrapped Exceptions

**Symptom:** the outermost exception is BeanCreationException, but the analyzer only handles the custom exception directly.

**Cause:** checking `instanceof` on the root failure without traversing the cause chain.

**Fix:** extend `AbstractFailureAnalyzer<T>` or implement intentional cause traversal.

### 27.4. Analyzer Always Returns null

**Symptom:** no custom description/action appears.

**Cause:** the cause type is absent from the chain, secondary conditions do not match, or the analyzer targets the wrong exception class.

**Fix:** test the analyzer directly with a real exception chain from startup failure and assert a non-null result.

### 27.5. Analyzer Catches Every BeanCreationException

**Symptom:** database, missing bean, or resource errors all report "tenant configuration missing".

**Cause:** the analyzer matches too broadly and guesses the cause from a generic wrapper.

**Fix:** match a custom exception or specific cause/type. Return null for out-of-scope cases.

### 27.6. Description Only Says "Startup failed"

**Symptom:** operators still have to read the stack trace to understand the problem.

**Cause:** description fails to identify the component/property/condition.

**Fix:** describe the specific incident using facts the analyzer can prove.

### 27.7. Action Only Says "Check configuration"

**Symptom:** readers do not know which key or source needs fixing.

**Cause:** Action is too vague.

**Fix:** specify the property key, valid value/format, configuration sources, or verification steps.

### 27.8. Analyzer Calls a Database or HTTP Service

**Symptom:** error reporting times out or throws a secondary exception.

**Cause:** the analyzer depends on an external system—potentially the very system causing startup failure.

**Fix:** analyze only the exception and available data. Never perform network calls inside an analyzer.

### 27.9. Analyzer Uses @Autowired Services

**Symptom:** the analyzer fails to initialize or dependencies are unavailable.

**Cause:** analyzers run during bootstrap failure lifecycle when ApplicationContext may be incomplete.

**Fix:** design analyzers as standalone, stateless classes with simple constructors; pass needed context via the exception.

### 27.10. spring.factories Only Exists in Test Resources

**Symptom:** the test classpath discovers the analyzer, but the executable JAR lacks it.

**Cause:** metadata sits in `src/test/resources` instead of `src/main/resources`.

**Fix:** place production metadata in `src/main/resources/META-INF/spring.factories` and inspect the built artifact.

### 27.11. Overwriting spring.factories Entries

**Symptom:** after adding FailureAnalyzer, another extension factory disappears.

**Cause:** replacing the entire file or accidentally overwriting an existing key's values.

**Fix:** merge keys/values, preserving existing entries; inspect metadata upon packaging.

### 27.12. Analyzer Constructor Requires an Application Bean

**Symptom:** Spring factories loader cannot instantiate the analyzer.

**Cause:** the constructor requires a service/repository that ApplicationContext has not created.

**Fix:** remove runtime dependencies; use a no-arg constructor or only stable, available data.

### 27.13. Two Analyzers Produce Conflicting Guidance

**Symptom:** one error is interpreted multiple ways, or output becomes unstable after adding a dependency.

**Cause:** overlapping recognition scopes.

**Fix:** narrow exception types/conditions so multiple analyzers do not match the same failure. Check discovery/ordering for your Spring Boot version.

### 27.14. Custom Reporter Loses Default Information

**Symptom:** output shows only description/action while previous stack traces or formatting vanish.

**Cause:** a custom reporter improperly replaces or supplements the default.

**Fix:** use the default reporter unless clearly required. If customized, define the output contract and write integration tests.

### 27.15. Using FailureAnalyzer to Handle Runtime HTTP Errors

**Symptom:** the analyzer is not invoked when a request returns HTTP 500.

**Cause:** FailureAnalyzer is for startup failures, not exception handling after the app is ready.

**Fix:** use `@ControllerAdvice`, `@ExceptionHandler`, service error handling, and runtime observability.

### 27.16. Context Runner Test Shows No Analyzer Output

**Symptom:** context runner reports a startup failure, but no `APPLICATION FAILED TO START` block appears.

**Cause:** ApplicationContextRunner tests context startup; it does not run the full SpringApplication failure analysis/reporting lifecycle.

**Fix:** unit test the analyzer separately, test the exception with context runner, and run a startup smoke test with a real SpringApplication/process when verifying discovery/reporting.

### 27.17. Action Suggests Mock Values for Production

**Symptom:** operators copy example commands and connect to the wrong tenant/database.

**Cause:** local examples are presented as production instructions.

**Fix:** clearly label demo values as local/test only; production must obtain values from official managed sources.

### 27.18. Messages Print Secrets or Unsafe Exception Content

**Symptom:** startup logs contain API keys, credentials, or personal data.

**Cause:** the analyzer concatenates raw exception messages or property values into FailureAnalysis.

**Fix:** build messages from controlled fields, apply redaction, and guide secret verification without printing values.

### 27.19. Expecting the Analyzer to Fix Configuration Automatically

**Symptom:** startup still fails after FailureAnalysis is printed.

**Cause:** mistaking an analyzer for a remediation engine.

**Fix:** FailureAnalyzer only diagnoses and guides. Operators or deployment pipelines must fix configuration and restart.

### 27.20. Upgrading Spring Boot Without Checking Discovery Metadata

**Symptom:** analyzer code compiles, yet running the new version shows no custom report.

**Cause:** dependency graphs, factory metadata, or packaging changed.

**Fix:** run registration tests and startup smoke tests against the exact deployed Spring Boot version.

## 28. Misconceptions to Avoid

**"FailureAnalyzer replaces stack traces."**  
No. It supplements them with description/action; exceptions remain essential for technical diagnostics.

**"FailureAnalyzer handles every runtime exception."**  
No. It is used within Spring Boot's startup failure handling flow.

**"Just adding @Component makes Boot discover the analyzer."**  
No. Register it using Spring factories metadata.

**"AutoConfiguration.imports is where all extensions are registered."**  
No. FailureAnalyzer uses `spring.factories`; `AutoConfiguration.imports` is for auto-configuration classes.

**"An analyzer must manually unwrap every wrapper exception."**  
No. `AbstractFailureAnalyzer<T>` helps find causes of the desired exception type.

**"Unrecognized errors should return a generic FailureAnalysis."**  
No. Return null so other analyzers or general handling can take over.

**"Description and Action can be the same sentence."**  
Avoid this. Description states the problem; Action provides remediation steps.

**"FailureAnalyzer can inject any Spring service."**  
Do not assume this. It runs when the context may still be incomplete.

**"A missing bean error always needs a custom analyzer."**  
No. Spring Boot already provides messages for many common errors. Add one only when custom context is needed.

**"A passing ApplicationContextRunner test means the reporter was called."**  
No. The runner tests context startup, whereas SpringApplication runs its own startup failure handling/reporting flow.

**"FailureAnalysisReporter must be customized to use an analyzer."**  
No. The default reporter is sufficient for most applications.

**"An analyzer can kill port-occupying processes or edit config files."**  
No. It should diagnose and guide; remediation must be controlled separately.

**"The more detail in the message, the better."**  
No. Show only necessary, authorized information; never log secrets or sensitive infrastructure details.

## 29. Workflow for Designing a New FailureAnalyzer

When a startup error belongs to your application's domain and default messages are not helpful enough, follow these steps.

### Step 1 — Confirm the Error Truly Belongs to Startup

If the error occurs after the app is ready, use runtime exception handling and observability. FailureAnalyzer is for startup failures.

### Step 2 — Check the Default Message First

Run the application in an environment reproducing the error and read the existing FailureAnalysis. If Boot already identifies the right cause and action, no custom analyzer is needed.

### Step 3 — Define a Meaningful Exception

Example:

~~~java
MissingTenantConfigurationException
~~~

The exception should represent a specific condition and preserve the cause if wrapping a lower-level error.

### Step 4 — Extend AbstractFailureAnalyzer

~~~java
public final class MissingTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                MissingTenantConfigurationException> {
    // Build FailureAnalysis from the matched cause.
}
~~~

Choose the right exception type to avoid overly broad matching.

### Step 5 — Write Description and Action

Description clearly states the failing component/condition. Action specifies the property key, configuration source, or concrete resolution steps. Never print secrets or guess the environment.

### Step 6 — Register via spring.factories

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer
~~~

Place this in `src/main/resources/META-INF/spring.factories` of the artifact providing the analyzer.

### Step 7 — Unit Test the Analyzer

Verify:

- Matching cause → non-null FailureAnalysis.
- Description/action include required details.
- Cause is preserved accurately.
- Out-of-scope exception → null.

### Step 8 — Context Test the Real Error

Use ApplicationContextRunner to trigger the startup failure and assert the exception chain contains the custom exception. You can pass that failure to the analyzer to test logic against real wrappers.

### Step 9 — Test Discovery/Reporting at Artifact Level

Verify `spring.factories` inside the JAR and run a consumer process with SpringApplication to confirm Boot invokes the analyzer and the reporter emits output.

### Step 10 — Ensure Message Safety

Confirm the Action does not point users to demo credentials in production, does not print secrets, and does not encourage destructive automated actions.

### Decision Diagram

~~~text
Startup failure occurs
          │
          ▼
Is Boot's default message clear enough?
          │
      ┌───┴────┐
      │        │
     Yes       No
      │        │
      ▼        ▼
Use existing  Is there a specific domain exception?
report              │
                ┌───┴────┐
                │        │
               Yes       No
                │        │
                ▼        ▼
        Custom Failure  Improve exception
        Analyzer        or use default analyzer
                │
                ▼
       Unit + context + discovery tests
                │
                ▼
       Startup smoke test with artifact
~~~

## 30. Self-Practice Exercises

### Exercise 1 — Matching a Wrapped Exception

A startup failure has the chain:

~~~text
BeanCreationException
  └── IllegalStateException
       └── MissingTenantConfigurationException
~~~

The analyzer extends `AbstractFailureAnalyzer<MissingTenantConfigurationException>`.

**Question:** Do you need to check for BeanCreationException manually first?

**Suggested Answer:** No. AbstractFailureAnalyzer searches the cause chain for the generic cause type to handle. The subclass receives `rootFailure` and the matched `cause`.

### Exercise 2 — When to Return null?

An analyzer expects MissingTenantConfigurationException, but the startup failure is PortInUseException.

**Question:** What should the analyzer do?

**Answer:** Since it does not recognize this case, it should return null so another analyzer or general handling can process it.

### Exercise 3 — Choosing a Better Message

Message A:

~~~text
Description: Startup failed.
Action: Check configuration.
~~~

Message B:

~~~text
Description:
The tenant client cannot be created because
'app.tenant.id' is missing.

Action:
Set a non-empty 'app.tenant.id' in the active
configuration source, then restart the application.
~~~

**Question:** Why is B more useful?

**Suggested Answer:** B identifies the component, property, and concrete action. A does not help the operator narrow the investigation.

### Exercise 4 — Registering an Analyzer

You place the class in the package:

~~~text
com.example.payment.diagnostics.PaymentFailureAnalyzer
~~~

**Question:** Where should metadata be declared?

**Answer:** In `src/main/resources/META-INF/spring.factories` under the key `org.springframework.boot.diagnostics.FailureAnalyzer` with the fully qualified class name.

### Exercise 5 — Distinguishing Metadata

**Question:** Why should FailureAnalyzer not be registered in `AutoConfiguration.imports`?

**Answer:** `AutoConfiguration.imports` is used to discover auto-configuration classes. FailureAnalyzer is loaded via dedicated Spring factories metadata.

### Exercise 6 — Testing Analyzer Back-Off

A unit test calls:

~~~java
analyzer.analyze(new IllegalArgumentException("other"))
~~~

and receives null.

**Question:** Does that mean the analyzer is broken?

**Answer:** No. This is correct behavior when IllegalArgumentException is outside the analyzer's responsibility.

### Exercise 7 — Distinguishing Context Tests from Startup Reports

ApplicationContextRunner reports context startup failed with a startup exception, yet no `APPLICATION FAILED TO START` block appears.

**Question:** Can you conclude FailureAnalyzer is unregistered?

**Answer:** Not yet. ApplicationContextRunner does not execute the full SpringApplication failure reporting lifecycle. Test the analyzer directly and use a SpringApplication/process smoke test to verify discovery/reporting.

### Exercise 8 — Handling Errors Containing Secrets

A custom exception contains an API key in its message.

**Question:** Should `exception.getMessage()` be placed verbatim into Description?

**Answer:** No. Build the description from controlled details without printing secrets. The Action should guide operators to check the secret source without revealing its value.

## Core Takeaways

**FailureAnalyzer** is Spring Boot's mechanism for turning startup exceptions into clearer **FailureAnalysis** reports. An analyzer identifies the failure and creates two parts: **Description** explaining what failed, and **Action** guiding concrete remediation steps. **AbstractFailureAnalyzer<T>** is especially useful when domain exceptions are wrapped inside BeanCreationException or other wrappers, as it finds the cause matching the desired type.

Custom analyzers must be registered via **META-INF/spring.factories** under the key **org.springframework.boot.diagnostics.FailureAnalyzer**. Do not confuse this metadata with `AutoConfiguration.imports` for auto-configurations. Analyzers should be independent of application beans, make no network/database calls, avoid modifying configuration, and return null when an error is unrecognized. The reporter is responsible for presenting FailureAnalysis; most applications can use the default reporter.

Testing should separate three goals: unit testing analyzer logic, context testing to verify the real exception is thrown, and integration/startup smoke testing to confirm SpringApplication discovers the analyzer from the artifact and reports Description/Action. Good messages must be specific, actionable, faithful to what the analyzer knows, and never leak secrets. That way, when an application fails to start, operators understand the cause and next step instead of guessing from a long stack trace.
## 20. Creating Messages for Configuration Binding Errors

Spring Boot binds properties into `@ConfigurationProperties`. When a value cannot be converted or violates validation, startup can fail with an exception from the binding/validation layer.

Example:

~~~java
package com.example.payment;

import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotNull Duration timeout,
        @Positive int maxAttempts) {
}
~~~

application.yml:

~~~yaml
app:
  payment:
    timeout: not-a-duration
    max-attempts: 3
~~~

The timeout value cannot convert to Duration, so binding fails.

### 20.1. Prefer Clear Validation Before Writing an Analyzer

When an error is an invalid property, it is usually better to:

- Use appropriate data types in `@ConfigurationProperties`.
- Use Jakarta Bean Validation such as `@NotBlank`, `@NotNull`, `@Positive`, `@Min`, `@Max` where appropriate.
- Provide clear validation messages.
- Provide sensible defaults if the property is genuinely optional.

Spring Boot already provides diagnostics for many binding errors. Only add a FailureAnalyzer when you need to translate a generic technical error into domain/deployment guidance.

### 20.2. A Domain Analyzer Can Explain Property Semantics

For example, when a property is present but unsupported by the system:

~~~text
Description:
The configured payment mode 'legacy-x' is not supported
by this version of the application.

Action:
Set 'app.payment.mode' to one of the supported values:
'sandbox' or 'live'. Confirm the selected mode with the
deployment configuration before restarting.
~~~

This is more helpful than a conversion error or IllegalArgumentException if operators need to know the valid values.

### 20.3. Do Not Echo Full Configuration Values in Reports

If a property holds credentials, URLs with query tokens, or sensitive data, do not print the raw value in Description.

You can state:

~~~text
The configured payment credential is invalid or unavailable.
~~~

and:

~~~text
Verify that the required secret is mounted and that the
service account can read it. Do not paste the secret into logs.
~~~

An analyzer should explain **how to verify safely** rather than dumping secrets into logs for convenience.

## 21. Handling Missing Bean and Multiple Bean Errors

Spring Boot can provide FailureAnalysis for several common dependency injection scenarios.

### 21.1. Missing Bean

Example:

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator calculator;

    public InvoiceService(TaxCalculator calculator) {
        this.calculator = calculator;
    }
}
~~~

If no matching TaxCalculator bean exists, the context cannot create InvoiceService.

Guidance messages can point out:

- Which type needs to be registered.
- Which bean requires that dependency.
- How to declare `@Component`/`@Bean` or add the appropriate auto-configuration/dependency.

### 21.2. Multiple Beans of the Same Type

~~~java
@Bean
TaxCalculator localTaxCalculator() {
    return new LocalTaxCalculator();
}

@Bean
TaxCalculator regionalTaxCalculator() {
    return new RegionalTaxCalculator();
}
~~~

If a service injects TaxCalculator without a qualifier/primary or selection rule, Spring cannot determine a unique candidate.

An Action can guide the user to:

- Mark a default bean with `@Primary` if there is a clear default choice.
- Use `@Qualifier` at the injection point when selecting a specific implementation.
- Remove unnecessary beans.

### 21.3. Do Not Write a Generic Analyzer for All BeanCreationExceptions

BeanCreationException can represent many different causes:

- A constructor threw an exception.
- A dependency does not exist.
- Property binding failed.
- A file resource is unreadable.
- An external system connection failed.
- Third-party library initialization failed.

An analyzer catching every BeanCreationException and always saying "check component scan" will give wrong advice in many cases.

Match specific causes or let Boot's built-in analyzers handle them.

## 22. Analyzing Exception Chains Properly

A startup error is often wrapped multiple times:

~~~text
ApplicationContextException
  └── BeanCreationException
       └── UnsatisfiedDependencyException
            └── IllegalStateException
                 └── MissingTenantConfigurationException
~~~

### 22.1. Do Not Look Only at the Outermost Exception

The outermost exception typically describes failure at the framework layer. Inner root/cause exceptions often carry more important domain context.

AbstractFailureAnalyzer helps locate causes by generic type, avoiding manual inspection of every wrapper layer.

### 22.2. When Multiple Causes Share the Same Type

A cause chain may contain multiple exceptions of the same type. AbstractFailureAnalyzer finds a matching cause according to its mechanism; if messages need to distinguish different locations, you can:

- Use distinct exception subtypes.
- Attach safe contextual metadata to the exception.
- Implement FailureAnalyzer directly with intentional cause lookup logic.

Do not parse stack trace strings to determine beans or properties.

### 22.3. Suppressed Exceptions Are Not Necessarily Causes

Java can attach suppressed exceptions when closing a resource fails in try-with-resources. Suppressed exceptions do not necessarily appear on the `getCause()` chain.

If a startup failure depends on a cleanup error, an analyzer traversing only the cause chain might miss the suppressed exception. Preserve the original exception and use appropriate stack trace/diagnostics; do not assume every related exception is a direct cause.

## 23. Logging and FailureAnalysis

When startup fails, FailureAnalysis is usually passed through the default reporter and logging system. However, an analyzer should not log the full error itself only for the reporter to log it again.

Avoid:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    log.error("Tenant config failed", rootFailure);

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set app.tenant.id.",
            cause);
}
~~~

This can produce duplicate output, especially when the startup framework also logs the exception/analysis.

Prefer:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set 'app.tenant.id' in the active configuration.",
            cause);
}
~~~

Let the reporter handle presentation. If extra logging is needed, define clearly where it is written and avoid repeating stack traces.

### 23.1. Startup Failures Still Require a Non-Zero Exit Code

FailureAnalyzer does not turn a startup failure into startup success. The application still fails, and launchers/orchestrators must recognize that the process failed to start.

In CI/CD or container orchestration:

- Process exit codes must be treated as failures.
- Do not just grep for "APPLICATION FAILED TO START" and treat that as the entire status.
- Use health/readiness checks to monitor status after the application is running.

### 23.2. FailureAnalysis Does Not Replace Readiness/Liveness Probes

FailureAnalyzer handles **startup errors**. Kubernetes readiness/liveness probes and Actuator health endpoints monitor running processes/containers.

Do not use an analyzer to explain a pod that started successfully and later lost database connectivity. That belongs to runtime monitoring, health checks, and logging.

## 24. Environment-Specific Guidance: Local, Test, and Production

Actions should suit known environments without guessing the environment from hostnames or working directories.

### 24.1. Local Development

Example:

~~~text
Action:
For a local run, add the following property to your
application-local.yml or pass it as a command-line argument:
--app.tenant.id=demo
~~~

The demo value is appropriate only if local systems accept a mock tenant.

### 24.2. Test

~~~text
Action:
Provide app.tenant.id in the test properties or test
configuration before starting the application context.
~~~

Do not recommend using production tenants in tests just to pass startup validation.

### 24.3. Production

~~~text
Action:
Verify that the deployment supplies app.tenant.id through
the approved configuration source. Confirm the mounted
configuration/secret and restart the affected instance.
~~~

Do not instruct operators to edit a file directly inside a container if deployment manages it via ConfigMap, Secret, or a centralized configuration system.

### 24.4. Do Not Guess Active Profiles

An analyzer can inspect an exception without necessarily having a complete Environment. Do not hardcode an Action like "edit application-prod.yml" simply because the app typically runs in production.

If an analyzer is genuinely designed to receive Environment safely during bootstrap, provide it explicitly and test that lifecycle. In simpler designs, guide via property keys and deployment-managed configuration sources.

## 25. Error Messages and Security

Startup errors are often written to consoles, log collectors, CI output, and monitoring systems. An inappropriate FailureAnalysis can leak:

- Passwords or tokens.
- Internal hostnames, IPs, and topology.
- File paths containing usernames or sensitive details.
- Raw configuration contents.
- Request payloads or personal data.

### 25.1. Do Not Include Secrets in Description or Action

Do not:

~~~java
String action = "Use API key " + apiKey
        + " in your deployment environment.";
~~~

Do:

~~~java
String action =
        "Verify that the required API key is available "
        + "from the approved secret source.";
~~~

### 25.2. Do Not Print Full Exception Messages If They May Contain Sensitive Data

If a custom exception is built from user input, the message may hold unsafe content. Analyzers should construct descriptions from **controlled fields** rather than concatenating `exception.getMessage()` blindly in every case.

### 25.3. Avoid Over-Exposing Internal Infrastructure Details

In production, an Action can say:

~~~text
Verify the configured database endpoint and the service
account's access through the approved deployment tooling.
~~~

instead of printing connection strings, subnets, usernames, and credentials.

Specific information is helpful, but show only data the output reader is authorized to see.

### 25.4. FailureAnalysis Is Not a Place for Automated Remediation Scripts

Do not embed scripts to delete files, kill processes, change permissions, or alter production configs in an Action implying users should run them unverified.

Actions should describe safe, verifiable operations suited to the operator's permissions.
