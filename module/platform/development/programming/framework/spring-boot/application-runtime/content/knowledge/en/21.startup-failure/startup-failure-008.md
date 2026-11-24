# The Role of FailureAnalysisReporter in Presenting Startup Failure Results

## 1. Why is a separate presentation step needed for failures?

When Spring Boot fails to start, the root cause may sit deep inside an exception chain: failure to bind a network port, invalid configuration, a missing bean, a circular dependency, or an `ApplicationRunner` throwing an error. Looking only at a huge stack trace, an operator may not know **what to fix first**.

Spring Boot 3.3.x includes a **failure diagnostics** mechanism to turn selected startup failures into readable messages. It comprises three components with distinct responsibilities:

- **`FailureAnalyzer`:** inspects a `Throwable`, recognizes an error type it understands, and builds an analysis, or returns `null` if it cannot analyze it.
- **`FailureAnalysis`:** the data object representing analysis output, holding `description`, `action`, and `cause`.
- **`FailureAnalysisReporter`:** receives a produced `FailureAnalysis` and **presents** it to users/operators—for example, logging an "APPLICATION FAILED TO START" block or emitting a structured diagnostic record.

**`FailureAnalysisReporter` is not where root causes are determined.** It is the **presentation/reporting** step after analysis. This separation lets one analyzer describe the technical condition while different reporters render it for a developer console, log aggregator, or monitoring channel as needed.

Familiar Spring Boot output example:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Embedded web server could not start because a required port was in use.

Action:

Free the port or configure the application to use another port.
```

The lines above are an **illustrative presentation sample**, not a verbatim copy from a specific Tomcat version. They highlight the two-part structure:

1. **Description:** describes what is wrong.
2. **Action:** suggests actionable remediation steps.

The full technical cause still exists in the `Throwable`/stack trace. The reporter helps readers see the concise message first; it **does not make the exception disappear or turn a failed startup into a success**.

This article applies to **Spring Boot 3.3.13 / Spring Framework 6.1.x / Java 17+**. In particular, registering a custom reporter for the startup failure phase is shown using `META-INF/spring.factories`, without assuming the entire `ApplicationContext` finished initializing.

## 2. Three components and exact APIs

### 2.1. FailureAnalyzer: analyzing errors

Interface in `org.springframework.boot.diagnostics`:

```java
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
```

This is an **abbreviated API signature**; do not redeclare this interface in application code. The method may return `null` if the analyzer cannot handle the exception. In some failures, the useful exception sits in `getCause()`, so analyzers may inspect the causal chain.

For example, a `MissingEndpointException` is thrown by `ApplicationRunner`; Spring Boot may wrap it in another exception when reporting runner execution failed. A dedicated analyzer should look for its target exception type **inside the causal chain** rather than checking only the outer Throwable's class.

### 2.2. FailureAnalysis: analyzed payload

Class `org.springframework.boot.diagnostics.FailureAnalysis` has constructor:

```java
new FailureAnalysis(description, action, cause)
```

and accessors:

```java
String description = analysis.getDescription();
String action = analysis.getAction();
Throwable cause = analysis.getCause();
```

These lines are an **illustrative snippet** requiring an `analysis` variable and matching imports. The three fields represent:

| Field | Recommended content | Avoid |
| --- | --- | --- |
| `description` | Describes the failure state and which condition failed | Writing only "Unknown error", dumping the whole stack trace |
| `action` | Specific fix steps: property to set, port to change, dependency to add | Generic advice like "fix code", dangerous instructions |
| `cause` | Real `Throwable` for root-cause tracing | Fabricating fake exceptions that lose context or strip root cause |

`getAction()` may return `null` if there is no specific action. Reporters must handle this cleanly and never assume every analysis has an action.

### 2.3. FailureAnalysisReporter: presenting the analysis

Spring Boot 3.3.13 interface:

```java
package org.springframework.boot.diagnostics;

@FunctionalInterface
public interface FailureAnalysisReporter {
    void report(FailureAnalysis analysis);
}
```

This is an **extracted API definition for explanation**; do not recreate the interface. Its sole method `report` returns `void`: the reporter simply receives the analysis and reports it to the user. It **does not return an exit code**, **does not decide "handled/not handled" via a boolean**, and **must not be used to alter readiness state**.

A reporter can output:

- A human-readable log block with `description` and `action`.
- A structured telemetry event (if logging infrastructure is ready).
- A bounded temporary diagnostic file, subject to security policy.
- A custom format for internal support tooling.

In production, prefer writing via a logger and avoid long or brittle I/O logic on the startup error reporting path.

### 2.4. Responsibility matrix

| Component | Input | Output | Responsibility |
| --- | --- | --- | --- |
| `FailureAnalyzer.analyze(Throwable)` | Startup exception | `FailureAnalysis` or `null` | Recognizes error, explains cause |
| `FailureAnalysis` | Description, action, cause | Diagnostic data | Does not log or fix errors itself |
| `FailureAnalysisReporter.report(...)` | A `FailureAnalysis` | Presentation side effect | Formats/displays the analysis |
| `LoggingFailureAnalysisReporter` | A `FailureAnalysis` | Message via logging | Spring Boot's default reporter |
| `SpringBootExceptionReporter` | `Throwable` from `SpringApplication` startup | `boolean` whether reported | Broader extension point, **distinct from** `FailureAnalysisReporter` |
| `ApplicationFailedEvent` listener | Boot startup failure event | Reacts to event | Event notification, does not create `FailureAnalysis` |

The two interfaces containing "Reporter" are not equivalent. Specifically, the broader `SpringBootExceptionReporter` is instantiated by the loader with `ConfigurableApplicationContext`; **do not copy that constructor requirement onto `FailureAnalysisReporter`**. The reporter in the example below declares a public no-arg constructor so the loader can instantiate it on the diagnostic path.

## 3. Startup failure handling flow

Easy-to-follow diagram:

```text
SpringApplication.run(...)
    |
    +--> failure while preparing/refreshing context or running runners
    |
    +--> SpringApplication handles startup failure
             |
             +--> SpringBootExceptionReporter mechanism
             |      |
             |      +--> FailureAnalyzers (Boot built-in)
             |              |
             |              +--> iterate through FailureAnalyzers
             |              |      +--> unrecognized -> null
             |              |      +--> recognized   -> FailureAnalysis
             |              |
             |              +--> reporter(s) receive FailureAnalysis
             |                     +--> LoggingFailureAnalysisReporter
             |                     +--> custom reporter if registered
             |
             +--> appropriate error reporting/notification/cleanup steps
             +--> exception is not treated as successful startup
```

The diagram shows the **roles** of each block without promising exact relative ordering among all startup failure hooks, shutdown callbacks, and loggers for every error kind. At startup failure time, the context might not fully exist, logging might not be finished configuring, or an exception might be severe enough that not every hook runs.

**Prerequisite for a reporter to receive a `FailureAnalysis`: a matching analyzer must analyze the error.** If no analyzer produces an analysis, reporters expecting a `FailureAnalysis` have nothing to present. In that case, inspect the stack trace and condition evaluation report.

### 3.1. Does it only handle failures during startup?

`FailureAnalysisReporter` belongs to **Spring Boot's startup failure diagnostics** path. It is not a `@ControllerAdvice` and is not automatically invoked when:

- An HTTP request returns 500 after the app is ready.
- A `@Scheduled` method throws an exception during normal runtime.
- A background `@Async` task fails after startup completed.
- A business method reports "customer not found" in a valid request.
- A message consumer fails after running for hours.

Runtime cases need their own exception handling, logging, retries, metrics, circuit breakers, or HTTP exception mapping.

### 3.2. Analyzer returning null vs reporter not logging

If a `FailureAnalyzer` returns `null`, that means **"this analyzer produced no analysis"**. If an analyzer returns an analysis yet the reporter emits no message, the cause may be logging configuration, reporter registration, an exception inside the reporter, or watching the wrong stdout/stderr stream.

These are two separate layers. When debugging, verify each stage:

```text
Actual exception?
    -> Does an analyzer handle that Throwable?
    -> Is FailureAnalysis non-null?
    -> Was the reporter instantiated by the loader?
    -> Was report(analysis) invoked?
    -> Is log output visible at the right level/channel?
```

Do not rush to rewrite the analyzer just because logs did not appear; likewise, do not rush to blame the reporter when the analyzer never produced a result.

## 4. Default reporter: LoggingFailureAnalysisReporter

Spring Boot provides `org.springframework.boot.diagnostics.LoggingFailureAnalysisReporter`, implementing `FailureAnalysisReporter`. This is the reporter normally seen when an app prints:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

<error description text>

Action:

<recommended action>
```

The block above is a **formatting template**; items in angle brackets are placeholders rather than literal text from an actual analyzer. The default reporter uses the logging system to display it. `Description` comes from `FailureAnalysis.getDescription()`; `Action` comes from `getAction()` if non-empty.

In typical implementations, the reporter logs the analysis at **ERROR** level, while detailed exception/cause info may be logged at **DEBUG**. Consequently:

- Too high a log threshold or a disabled logger can hide the expected message.
- The ERROR report may be shorter than the full stack trace, deliberately focusing on remediation.
- Enabling DEBUG adds details for investigation without fixing misconfigurations by itself.
- `description`/`action` content depends on whichever analyzer produced the analysis, not on the reporter name.

**You do not need to write a custom reporter** just to get a clear standard error banner. Most apps rely on the default reporter; custom reporters are useful when you have bespoke **presentation/telemetry** requirements.

### 4.1. How to improve the message?

If the message is vague because **description/action** is unclear, you usually need to improve the **`FailureAnalyzer`**. Swapping the reporter only changes presentation; it adds no domain knowledge to the analysis.

Example:

```text
Description:
A required configuration property for the payment connector is missing.

Action:
Set PAYMENT_ENDPOINT in the deployment environment, then restart.
```

This is a **content example** requiring no custom reporter; an analyzer produces those exact strings and the default reporter prints them.

### 4.2. Does Boot documentation mentioning "FailureAnalyzer beans" mean @Component is required?

Do not take phrasing on overview pages to mean adding `@Component` alone completes startup diagnostic plugin registration. **The officially documented registration for custom FailureAnalyzers** in Boot 3.3 uses `META-INF/spring.factories`. Custom `FailureAnalysisReporter`s should also use `SpringFactoriesLoader`'s extension point, since errors can happen before the context finishes initializing. Section 6 gives a concrete example.

## 5. When is a custom FailureAnalysisReporter needed?

A custom reporter makes sense when **the analysis itself is already right**, yet the consumer needs a different format or channel:

1. An environment needs single-line error messages so a log collector can attach a job ID.
2. A runtime wants a fixed prefix distinguishing library diagnostics from business logs.
3. An internal support platform wants `cause type`, `description`, and `action` packaged into a structured record.
4. A test harness needs to verify the analysis reached presentation, not just test the analyzer in isolation.
5. A starter library needs uniform display conventions for its own configuration failures.

Custom reporters also have limits:

- **Cannot fix port binding, bad config, or missing beans**; it only reports.
- **Should not call `System.exit`, `context.close`, or retry startup** inside `report`. Boot is already handling the failure.
- **Must not depend on request-scoped beans** or mandatory network services, since the context may be uninitialized.
- **Should not open untimed network connections** to send errors; the external system itself may be why startup failed.
- **Must not leak secrets** via `description`, `action`, or `getCause().getMessage()`.
- **Does not guarantee an analysis exists** for every JVM crash, classpath error, or ultra-early failure.

The upcoming lesson uses a reporter writing to `System.err` for clear visual demonstration, **not as a recommendation to abandon loggers in production**. In real apps, prefer bounded-time logging and telemetry systems, tested with the exact launcher you deploy.


## 6. Runnable example: custom analyzer + custom reporter on Spring Boot 3.3.13

Goal: deliberately trigger a missing `demo.remote.endpoint` property inside an `ApplicationRunner`; let Boot run analysis and invoke the registered reporter. This highlights **the difference between analysis (data)** and **reporting (presentation)**.

The example uses **Java 17+**, **Spring Boot 3.3.13**, **Gradle**, and a **non-web application**. It calls no external APIs, needs no database, and opens no network ports. Missing the property causes an intentional startup failure; supplying it succeeds **without invoking the reporter**.

### 6.1. Directory structure

```text
diagnostics-lab/
├── build.gradle
├── settings.gradle
└── src/
    └── main/
        ├── java/com/example/failure/
        │   ├── DiagnosticsDemoApplication.java
        │   ├── MissingEndpointException.java
        │   ├── MissingEndpointFailureAnalyzer.java
        │   └── ConsoleFailureAnalysisReporter.java
        └── resources/
            ├── application.properties
            └── META-INF/
                └── spring.factories
```

Paths and public class names must match **exactly**. `spring.factories` must live in **`src/main/resources/META-INF/`** to be packaged on the classpath, not at the project root.

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'diagnostics-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR

# Intentionally DO NOT declare demo.remote.endpoint here.
```

### 6.3. Application and controlled error source

Create **`src/main/java/com/example/failure/DiagnosticsDemoApplication.java`**:

```java
package com.example.failure;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DiagnosticsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner checkRequiredEndpoint(
            @Value("${demo.remote.endpoint:}") String endpoint) {

        return args -> {
            if (endpoint.isBlank()) {
                throw new MissingEndpointException("demo.remote.endpoint");
            }
            System.out.println("RUNNER OK: endpoint property is present");
        };
    }
}
```

Because `@Value("${demo.remote.endpoint:}")` has an **empty default**, the app builds the bean normally when the property is absent and the runner explicitly throws. This creates an error **after refresh** yet **before `ApplicationReadyEvent`**, simple enough to trace through the causal chain. We intentionally avoid printing credential-bearing URLs to stdout.

Create **`src/main/java/com/example/failure/MissingEndpointException.java`**:

```java
package com.example.failure;

public final class MissingEndpointException extends RuntimeException {

    private final String propertyName;

    public MissingEndpointException(String propertyName) {
        super("Required configuration is missing: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return propertyName;
    }
}
```

This class models only the **configuration domain error**. It implements neither reporter nor analyzer and holds no logging logic.

### 6.4. FailureAnalyzer: producing FailureAnalysis

Create **`src/main/java/com/example/failure/MissingEndpointFailureAnalyzer.java`**:

```java
package com.example.failure;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalyzer;

public final class MissingEndpointFailureAnalyzer
        implements FailureAnalyzer {

    public MissingEndpointFailureAnalyzer() {
    }

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        // SpringApplication may wrap the root exception from the runner.
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {

            if (current instanceof MissingEndpointException missing) {
                String name = missing.getPropertyName();

                return new FailureAnalysis(
                        "Required configuration '" + name
                                + "' is missing or blank.",
                        "Set --" + name
                                + "=https://example.invalid/api"
                                + " (or environment DEMO_REMOTE_ENDPOINT).",
                        missing);
            }
        }

        // Not our error: defer to other analyzers.
        return null;
    }
}
```

**Key points:**

- `analyze(Throwable)` is a method on `FailureAnalyzer`, not on the reporter.
- Walking `current.getCause()` finds the exception even when Spring wraps the exception from `ApplicationRunner`.
- `new FailureAnalysis(description, action, missing)` preserves the underlying domain exception as `cause`.
- `return null` on mismatch is the right choice: it gives other analyzers a chance to handle other errors.
- The reporter **does not duplicate cause-lookup or action-generation logic**; it simply reads the generated analysis.

### 6.5. FailureAnalysisReporter: presenting the analysis

Create **`src/main/java/com/example/failure/ConsoleFailureAnalysisReporter.java`**:

```java
package com.example.failure;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalysisReporter;

public final class ConsoleFailureAnalysisReporter
        implements FailureAnalysisReporter {

    public ConsoleFailureAnalysisReporter() {
    }

    @Override
    public void report(FailureAnalysis analysis) {
        System.err.println(
                "[CUSTOM REPORTER] description=" + analysis.getDescription());

        if (analysis.getAction() != null) {
            System.err.println(
                    "[CUSTOM REPORTER] action=" + analysis.getAction());
        }

        Throwable cause = analysis.getCause();
        System.err.println(
                "[CUSTOM REPORTER] cause="
                        + (cause == null
                                ? "unknown"
                                : cause.getClass().getSimpleName()));
    }
}
```

This reporter **stays strictly within its presentation role**:

- Does not hunt for `MissingEndpointException` or classify business errors.
- Does not throw a new exception when startup has already failed.
- Does not call `SpringApplication.run(...)` again.
- Does not call `System.exit(...)`.
- Does not modify `application.properties`.
- Only reads `description`/`action`/`cause` from `FailureAnalysis` and prints them with a recognizable prefix.

Using `System.err` in the demo clearly demonstrates output on startup failure; real apps should generally use loggers/structured telemetry while accounting for uninitialized loggers.

### 6.6. META-INF/spring.factories: registering both extension points

Create **`src/main/resources/META-INF/spring.factories`** with exact content:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failure.MissingEndpointFailureAnalyzer
org.springframework.boot.diagnostics.FailureAnalysisReporter=com.example.failure.ConsoleFailureAnalysisReporter
```

**Do not place this file inside a Java package folder.** It is classpath metadata for `SpringFactoriesLoader`. Spring Boot ships its own built-in implementations and factory lists inside framework JARs; the application's metadata resource is examined alongside them by the loader.

Practical outcome:

1. On startup failure, Spring Boot can load `MissingEndpointFailureAnalyzer` from the classpath.
2. The analyzer produces a `FailureAnalysis` if the causal chain contains `MissingEndpointException`.
3. `ConsoleFailureAnalysisReporter` is loaded and receives the result.
4. Spring Boot's default `LoggingFailureAnalysisReporter` may also report the same failure analysis through logging.
5. The app needs no `@Component` on either class for discovery; both have public no-arg constructors suitable for the loader.

**Crucial point:** a `FailureAnalysisReporter` in the startup failure phase **must not rely on `@Autowired` injection of existing beans**. Errors can happen before the container finishes preparing. Designing a low-dependency reporter instantiable from classpath metadata lets it work in far more scenarios.

### 6.7. Build the executable JAR

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
```

macOS/Linux:

```bash
./gradlew bootJar
```

With a generated Gradle Wrapper and Java 17 toolchain, output is typically:

```text
build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
```

Use `jar tf build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar` to verify `BOOT-INF/classes/META-INF/spring.factories` is present in the packaged Boot executable JAR. If the metadata is missing from the classpath, custom reporters and analyzers will not load at runtime.

### 6.8. Run the failure path

```bash
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
```

Because `demo.remote.endpoint` is absent from properties, the runner throws `MissingEndpointException`. Boot handles the startup failure and invokes the registered analyzer and reporter.

Lines printed to stderr by the **custom reporter** when invoked by the loader:

```text
[CUSTOM REPORTER] description=Required configuration 'demo.remote.endpoint' is missing or blank.
[CUSTOM REPORTER] action=Set --demo.remote.endpoint=https://example.invalid/api (or environment DEMO_REMOTE_ENDPOINT).
[CUSTOM REPORTER] cause=MissingEndpointException
```

The `[CUSTOM REPORTER]` lines above are **output specific to the demo class**. Spring Boot may also print the `APPLICATION FAILED TO START` block from the default reporter and other error log lines. **Exact ordering between custom reporter stderr and logging output should not be asserted strictly**, because logging config and stdout/stderr buffering differ across launchers, IDEs, and CI.

On this failure path:

- `RUNNER OK: ...` **does not appear**.
- No successful startup path reaches `ApplicationReadyEvent`.
- `SpringApplication.run(...)` does not return a healthy context to `main`.
- The Java process normally exits with a failure status when the exception goes unhandled. Check the **actual exit code** from the launcher rather than assuming the custom reporter sets a specific number.

### 6.9. Run the success path

Supply a valid property (the sample URL performs no network I/O):

```bash
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar --demo.remote.endpoint=https://example.invalid/api
```

With non-web config, root logging at ERROR, and no extra components, the **line explicitly printed by the app** is:

```text
RUNNER OK: endpoint property is present
```

The app throws no exception, so custom failure analyzers/reporters **are not invoked for a startup failure**. For a non-web CLI sample with no other non-daemon resources keeping the JVM alive, the process exits normally once startup completes. The URL serves purely as test input and is never contacted over HTTP.

### 6.10. PowerShell and Bash status checks

Bash:

```bash
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
code=$?
echo "Java process exit status: $code"
```

PowerShell:

```powershell
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
$LASTEXITCODE
```

**Do not hardcode stdout expectations to "1" across all wrappers/launchers.** Failure exit behavior depends on exception handling, configuration, and how shells/Gradle/IDEs wrap the process. To verify exit status, run `java -jar` directly or spawn a child process in tests.

Because `FailureAnalysisReporter.report(...)` returns `void`, a reporter is not the place to map exit codes. If you need custom exit code policies, use `ExitCodeGenerator`, `ExitCodeExceptionMapper`, and shutdown mechanisms separately rather than mixing them into report formatting.


## 7. Designing a good reporter for production systems

### 7.1. Content should focus on whoever fixes the error

Good messages typically answer four questions:

1. **What is wrong?** e.g., missing `demo.remote.endpoint`.
2. **Which phase did it fail in?** Configuration binding, bean construction, context refresh, runner...
3. **What is the impact?** Unable to start application or reach ready.
4. **What to do next?** Set the exact property name, inspect secret manager/ConfigMap, change port, or supply missing bean.

`FailureAnalysisReporter` can format the message, while **`FailureAnalyzer` must supply high-quality description/action**. Never "solve" reporting by forwarding raw exception messages straight to alerting systems, since many lack context and may contain secrets.

### 7.2. Minimal and fault-tolerant

A reporter runs on the **error path of an error path**: startup has already failed. Keep dependencies minimal:

- Use a simple constructor; avoid network calls in the constructor.
- Do not wait on databases, brokers, or failing beans.
- Do not create unbounded schedulers/executors just to report failure.
- Avoid throwing new exceptions from `report` whenever avoidable; catch errors from output channels if needed.
- Bound execution time if flushing logs or telemetry.
- Keep a minimal fallback output channel when logging is not fully initialized.
- Keep messages concise and actionable, adding a non-sensitive correlation ID if available.
- Test on failures **before refresh** and **after refresh** if reporting must cover both.

### 7.3. Security: never dump secrets

`FailureAnalysis` may hold exceptions from binding or config. Raw `Throwable.getMessage()` or nested causes sometimes include:

- URLs containing usernames/passwords.
- Secret tokens, API keys, database credentials.
- Connection strings or queries carrying sensitive payloads.
- Identifiers inappropriate for shared logs.

Never serialize an entire `Throwable` blindly to JSON and ship it out. Write analyzers that generate a **secret-redacted description** naming only the property or resource type, paired with a safe action. Reporters should cap log size, apply redaction policies, and avoid uncontrolled duplication across channels.

A sufficient output:

```text
description=Required property 'demo.remote.endpoint' is missing.
action=Provide demo.remote.endpoint in trusted configuration.
causeType=MissingEndpointException
```

This block tells operators the exact next step without printing endpoint values, tokens, or request payloads.

### 7.4. Aligning with log aggregators and alerts

If routing or alerting is required, design stable fields:

| Suggested field | Example | Purpose |
| --- | --- | --- |
| `eventType` | `startup_failure` | Separate from runtime 500s |
| `application` | `billing-service` | Identify affected component |
| `phase` | `application_runner` | Isolate failing phase |
| `causeType` | `MissingEndpointException` | Group errors of the same kind |
| `description` | Missing required property | Fast human comprehension |
| `action` | Supply valid configuration | Remediation guidance |
| `instanceId` | Non-sensitive ID | Correlate logs |
| `timestamp` | Standard UTC timestamp | Align with deployment events |

This is a **suggested schema table**, not fields automatically passed into `FailureAnalysisReporter` by Spring. The actual interface receives only `FailureAnalysis`. To include environment, instance, and build metadata, the reporter must read from safe available sources without assuming `ApplicationContext` is complete.

### 7.5. Why shouldn't a reporter send HTTP notifications directly?

During a startup failure, the root problem may be broken DNS, bad credentials, or an unreachable downstream API. If the reporter also calls downstream APIs without timeouts, the system can "freeze while reporting an error".

Recommendation: have the reporter emit a structured log to stderr/logger, and let an **external log collector** route alerts to your platform. If direct sending is mandatory, enforce short timeouts, best-effort handling, and never obscure the original startup error.

## 8. Differences from related extension points

### 8.1. FailureAnalysisReporter vs ApplicationFailedEvent

`ApplicationFailedEvent` is published by Spring Boot along the startup failure path so listeners learn startup failed. It does not automatically hold a custom analyzer's `FailureAnalysis` ready for a reporter to render.

`FailureAnalysisReporter` receives `FailureAnalysis`, while an `ApplicationFailedEvent` listener receives the **event containing the failure and context when present**. If you need broader reactions to startup failure, an event listener may fit; if you need **presentation of a generated analysis**, use a reporter.

Ordering note: Do not build correctness logic relying on log ordering between listeners and reporters across every startup phase. When the context has not finished building, context-bean listeners might not even exist yet.

### 8.2. FailureAnalysisReporter vs SpringBootExceptionReporter

`SpringBootExceptionReporter` defines:

```java
boolean reportException(Throwable failure);
```

It is a `SpringApplication`-level callback for startup errors taking `Throwable` and returning whether the failure was reported. `FailureAnalysisReporter`, by contrast, **presents an already analyzed `FailureAnalysis`**:

```java
void report(FailureAnalysis analysis);
```

The two interfaces use different `spring.factories` keys, different input types, and different notions of "handled". Inside Spring Boot, `FailureAnalyzers` acts as a `SpringBootExceptionReporter` driving the analyzer/reporter pipeline.

**Do not implement `FailureAnalysisReporter` with `reportException(Throwable)`**; the exact method to override is `report(FailureAnalysis)`. Likewise, do not require a `ConfigurableApplicationContext` constructor on custom `FailureAnalysisReporter`s as in this example; that requirement belongs to `SpringBootExceptionReporter`.

### 8.3. FailureAnalysisReporter vs ExitCodeGenerator

| API | Role |
| --- | --- |
| `FailureAnalysisReporter` | Displays an analysis result |
| `ExitCodeGenerator` | Proposes an exit code from a bean/exception along that path |
| `ExitCodeExceptionMapper` | Maps exceptions to exit codes |
| `System.exit(int)` | Instructs the JVM to terminate with the given OS status |

A custom reporter does not turn a startup failure into exit 0 or assign exit code 7 just because a message prints "severity=critical". Message presentation and exit-status determination must remain separate responsibilities.

### 8.4. FailureAnalysisReporter vs ControllerAdvice

`@ControllerAdvice`/`@ExceptionHandler` handles exceptions in HTTP request contexts after the app is running. It is not the primary tool for reporting bean creation, binding, or runner failures during startup. Conversely, `FailureAnalysisReporter` does not convert HTTP 500 errors into JSON responses for clients.

### 8.5. FailureAnalysisReporter vs ConditionEvaluationReport

When a startup error lacks a matching analyzer, Spring Boot suggests inspecting the **conditions evaluation report** to understand why auto-configurations were applied or skipped. Enable `--debug` with `java -jar` or configure the `ConditionEvaluationReportLoggingListener` logger appropriately.

`ConditionEvaluationReport` is configuration-condition diagnostic data, not output the default `FailureAnalysisReporter` automatically embeds. Do not expect the reporter to synthesize analyses for every auto-configuration decision. It is a **complementary investigation tool**, not a replacement for analyzers/reporters.

## 9. Practical scenarios

### 9.1. Unable to bind port 8080

- **Cause:** typically an exception when the embedded server tries to bind an occupied port.
- **Analyzer:** Boot includes built-in failure analyzers for common configuration/startup errors.
- **FailureAnalysis:** describes the occupied port and remediation steps.
- **Reporter:** default logging displays the error banner with `Description` and `Action`.

**No custom reporter is needed** when the banner is already clear. If your log aggregator requires explicit `port`/`service` fields, consider custom presentation or external structured logging.

### 9.2. Missing critical bean

- Root failure may involve dependency injection/`NoSuchBeanDefinitionException`.
- A matching analyzer can describe the required bean type and how to add the bean/configuration.
- The reporter displays that description; it **cannot register a new bean to rescue startup**.

For complex injection errors, actions should avoid recklessly advising "enable @ComponentScan everywhere". Ground guidance in proper scope and auto-configuration.

### 9.3. Invalid configuration property

- The analyzer identifies the invalid property, unmet binding constraint, or validation failure.
- Action should name **the key**, expected format/range, and configuration source to update.
- The reporter delivers that text to console/logs.
- Never print credential values in errors; sanitize descriptions in the analyzer.

Section 6's example belongs to this category, using a domain exception and runner to make the causal chain easy to follow.

### 9.4. Error with no analyzer

A third-party library throws a runtime exception unrecognized by any analyzer.

- There is no specific analysis for a custom reporter to format.
- Boot still executes general startup failure logging; inspect the root stack trace and auto-config conditions.
- If the error recurs often with a clear fix, add a dedicated `FailureAnalyzer` before considering a custom reporter.

### 9.5. Misconfigured logging

The analyzer produced a result and the default reporter ran, yet the app did not display what you expected. Check:

- Logger level for `org.springframework.boot.diagnostics.LoggingFailureAnalysisReporter`.
- Log appenders, stdout/stderr routing, ANSI settings, and redirection.
- Whether the log collector reads the right stream.
- Whether a custom reporter duplicated output or threw an exception.
- Whether startup failed so early that logging/loaders were not ready.

Do not conclude "Boot failed to analyze it" merely because a log collector missed the banner lines.

## 10. Testing analyzers and reporters

### 10.1. Unit testing the analyzer with a causal chain

Create **`src/test/java/com/example/failure/MissingEndpointFailureAnalyzerTest.java`**:

```java
package com.example.failure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.junit.jupiter.api.Assertions.*;

class MissingEndpointFailureAnalyzerTest {

    @Test
    void findsCauseEvenWhenRunnerWrapsIt() {
        var analyzer = new MissingEndpointFailureAnalyzer();

        var root = new MissingEndpointException("demo.remote.endpoint");
        var wrapper = new IllegalStateException(
                "Failed to execute ApplicationRunner", root);

        FailureAnalysis analysis = analyzer.analyze(wrapper);

        assertNotNull(analysis);
        assertSame(root, analysis.getCause());
        assertTrue(analysis.getDescription().contains(
                "demo.remote.endpoint"));
        assertTrue(analysis.getAction().contains(
                "--demo.remote.endpoint="));
    }

    @Test
    void ignoresUnrelatedFailures() {
        var analyzer = new MissingEndpointFailureAnalyzer();

        FailureAnalysis analysis = analyzer.analyze(
                new IllegalArgumentException("unrelated"));

        assertNull(analysis);
    }
}
```

This is a **complete JUnit 5 test** using the `spring-boot-starter-test` dependency declared in `build.gradle`. Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

When configured properly, these two unit tests verify:

- The analyzer finds the target exception despite wrappers.
- `cause` retains the root exception instance.
- `description/action` contain the required details.
- Different exception types return `null`.

**They do not prove `spring.factories` was packaged or that the reporter was called during startup.** That requires an integration/process test.

### 10.2. Testing the reporter in isolation

You can construct a sample `FailureAnalysis` and invoke:

```java
var analysis = new FailureAnalysis(
        "Required configuration is missing.",
        "Set a trusted configuration value.",
        new IllegalStateException("sample"));

new ConsoleFailureAnalysisReporter().report(analysis);
```

This is an **experimental snippet** requiring imports for `FailureAnalysis` and the example reporter class. It proves the method formats all three fields, without yet proving the loader or `SpringApplication` startup failure pipeline.

To assert output in a unit test, capture `System.err`, making sure to **restore the stream in `finally`** or use your test framework's output-capture extension to avoid interfering with parallel tests.

### 10.3. Integration testing via a separate process

Run `java -jar` **without the property**; assert:

- Process startup fails under the controlled condition.
- Stderr/logs contain `[CUSTOM REPORTER] description=...`.
- `cause=MissingEndpointException` is present.
- `RUNNER OK` does not appear.
- Exit status reflects failure according to the actual launcher.

Then run with `--demo.remote.endpoint=https://example.invalid/api`; assert:

- Runner prints `RUNNER OK: endpoint property is present`.
- No `[CUSTOM REPORTER]` marker from startup failure appears.
- Process exits normally.

This verifies analysis, reporting, and `META-INF/spring.factories` metadata together. Using Gradle `bootRun` can yield a Gradle wrapper exit code differing from the child process; the most reliable process-status test runs `java -jar` directly or via `ProcessBuilder` on the executable JAR.

### 10.4. When adding a custom reporter, does the default one still run?

Adding the key to the app's `spring.factories` registers an **additional** implementation. Spring Boot's JARs still retain metadata registering `LoggingFailureAnalysisReporter`. Therefore, under default configuration, you may observe **both custom markers and the default banner**.

Do not write tests asserting "there are strictly three lines on stderr": default logging may add banners, timestamps, or stack traces; assert the custom reporter's stable markers instead. If you want to suppress the default or replace the format, design the logging channel intentionally and test the fallback when the reporter fails to load, rather than relying on incidental initialization order.

## 11. Checklist when a custom reporter does not run

1. **Did the failure really happen inside `SpringApplication.run(...)`?** Runtime exceptions after ready use a different mechanism.
2. **Did an analyzer return `FailureAnalysis`?** Without one, the reporter may have nothing to receive.
3. **Is the target exception a wrapper or root cause?** Walk the causal chain, not just the top-level Throwable class.
4. **Did the analyzer return `null` intentionally or by mistake?** For domain errors you want to handle, an accidental `return null` yields to others or leaves no analysis.
5. **Are the registration keys exact?** `org.springframework.boot.diagnostics.FailureAnalyzer` and `org.springframework.boot.diagnostics.FailureAnalysisReporter`.
6. **Is the file path right?** `src/main/resources/META-INF/spring.factories`, not a Java package directory.
7. **Are fully qualified class names exact?** Package, public class name, and spelling.
8. **Is the constructor suitable?** For the demo, a public no-arg constructor; avoid injecting context beans.
9. **Did metadata make it into the JAR?** Check `BOOT-INF/classes/META-INF/spring.factories` inside the executable JAR.
10. **Did the app customize `SpringApplication` or the loader/classpath?** Test with the real launcher and inspect dependencies in the JAR.
11. **Did the reporter log to a different stream?** Check `System.err`, log levels, collectors, and redirects.
12. **Are multiple reporters active?** Do not assume fixed line counts or ordering while the default framework reporter also runs.
13. **Was the exception too early or unrecoverable?** Some failures happen before the pipeline can run.
14. **Do description/action contain secrets?** Sanitize before emitting to shared channels.
15. **Did the reporter block on network I/O or throw?** Reporting paths must be fast, low-dependency, and best-effort.
16. **Are you inspecting an HTTP 500 request error?** Use HTTP exception handling, not startup reporters.
17. **Confusing with ExitCodeGenerator?** Reporters do not set process exit codes.
18. **Used `@Component` and forgot `spring.factories`?** Startup diagnostics act as plugins via classpath metadata in this example.

## 12. Common misconceptions

| Claim or symptom | Why is it wrong? | Correct response |
| --- | --- | --- |
| "Reporters find the root cause themselves" | Analyzer and reporter responsibilities are separated | Analyzer builds result; reporter displays it |
| "FailureAnalysis is a Throwable" | It is a data object holding description/action/cause | Use its accessors properly |
| "report returns true if it handled the error" | `FailureAnalysisReporter.report` returns `void` | Do not confuse with `SpringBootExceptionReporter` |
| "Adding @Component guarantees the reporter runs" | Startup context may be incomplete | Register in `META-INF/spring.factories` |
| "Reporters replace all stack traces" | It is a helpful summary/formatted notice | Inspect root cause and DEBUG logs when needed |
| "Reporters fix occupied ports" | Cannot change config or infrastructure | Operators execute the action |
| "Every startup failure has a FailureAnalysis" | Analyzers may return null or pipeline never ran | Fall back to stack traces and conditions reports |
| "Default reporter only logs at INFO" | `LoggingFailureAnalysisReporter` normally logs banners at ERROR | Check log levels and appenders |
| "Action always has a string" | `FailureAnalysis.getAction()` can be null | Check for null/blank |
| "Just printing cause.getMessage() is enough" | Lacks an action and risks exposing data | Write safe descriptions with remediation steps |
| "Our reporter removes the default reporter" | Factory discovery may load both | Expect additional output |
| "Stderr lines always appear in exact order with logging" | Different streams and flushing behavior | Assert markers, not full global order |
| "ApplicationFailedEvent is FailureAnalysisReporter" | Event notification vs presentation step | Pick the right hook |
| "Runtime @Async failures also invoke the reporter" | This is startup diagnostics | Monitor `Future`/`AsyncUncaughtExceptionHandler` |
| "Reporters set the exit code" | `report` API returns void | Use dedicated exit-code mechanisms |
| "Registering a reporter without an analyzer still prints" | Requires a matching `FailureAnalysis` | Check analyzer and causal chain |
| "Enabling --debug fixes every cause" | Debug only adds diagnostic output | Read conditions and update config |
| "Reporters can call untimed REST APIs" | Startup itself may have failed due to network | Prefer loggers or bounded best-effort |
| "Log all secrets to ease debugging" | Log aggregators spread sensitive data | Log keys/types only, never secret values |

## 13. Self-assessment questions

**Q1.** How do `FailureAnalyzer` and `FailureAnalysisReporter` differ?

**Answer:** The analyzer receives a Throwable and produces a `FailureAnalysis` or null; the reporter receives `FailureAnalysis` and presents the result without deciding error classification.

**Q2.** What components does a `FailureAnalysis` contain?

**Answer:** `description`, an optional (nullable) `action`, and `cause` as the corresponding Throwable.

**Q3.** What is `FailureAnalysisReporter`'s main method and return type?

**Answer:** `void report(FailureAnalysis analysis)`.

**Q4.** What is the default reporter named?

**Answer:** `LoggingFailureAnalysisReporter`, which logs the analysis, typically featuring the `APPLICATION FAILED TO START` block.

**Q5.** What should an analyzer do when it does not understand an exception?

**Answer:** Return `null` to let other analyzers handle it, rather than inventing an action or claiming every Throwable.

**Q6.** Why walk `Throwable.getCause()`?

**Answer:** Spring may wrap bean initialization or runner failures, while the useful domain exception sits one or more levels deeper.

**Q7.** Which file registers custom analyzers/reporters in the example?

**Answer:** `src/main/resources/META-INF/spring.factories` with the two fully qualified keys `FailureAnalyzer` and `FailureAnalysisReporter`.

**Q8.** Why not just place `@Component` on the reporter?

**Answer:** Startup failures can happen before the context is fully built; discovery via classpath factory metadata suits this extension point better.

**Q9.** If an analyzer produces a result yet the app still exits with failure, is the reporter broken?

**Answer:** No. The reporter's job is **reporting an active startup failure**, not making the app start successfully.

**Q10.** If an HTTP request returns 500 after the app is ready, does this reporter run automatically?

**Answer:** No. Use `@ControllerAdvice`/exception handlers, observability, and proper runtime error reporting.

**Q11.** If a reporter writes only to a network alerting API and that API is down, what is the danger?

**Answer:** It can block or obscure the original root cause while startup is already failing. Minimize I/O, apply timeouts, and rely on external log collectors.

**Q12.** Is `ApplicationFailedEvent` the same as `FailureAnalysis`?

**Answer:** No. The event signals a startup failure, while `FailureAnalysis` is the analyzer-generated payload formatted for users.

**Q13.** Should the example's custom reporter contain `System.exit(2)`?

**Answer:** No. It only displays the analysis. Defining exit codes belongs to separate mechanisms verified by the launcher.

**Q14.** When no built-in analyzer helps, how should you debug next?

**Answer:** Inspect the exception/root stack trace, enable `--debug`/condition evaluation report appropriately, check configuration, and write a targeted analyzer if the failure recurs.

## 14. Takeaways and official documentation

### 14.1. Five key takeaways

1. **`FailureAnalyzer` = analyzes Throwable; `FailureAnalysis` = result data; `FailureAnalysisReporter` = presents the data.**
2. The reporter's exact API is **`void report(FailureAnalysis analysis)`**. It fixes nothing, creates no context, and sets no exit code.
3. The default **`LoggingFailureAnalysisReporter`** normally logs a `Description / Action` block headed `APPLICATION FAILED TO START`.
4. Custom startup analyzers/reporters should be registered in **`META-INF/spring.factories`**, with suitable constructors and minimal context dependencies.
5. A good report is **accurate, actionable, and secret-free**; a failed startup still needs real configuration, code, or infrastructure fixes.

### 14.2. Reference links

- [Spring Boot 3.3.13 — FailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html), signature `report(FailureAnalysis)`.
- [Spring Boot 3.3.13 — FailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html), `analyze(Throwable)` and `null`-return contract.
- [Spring Boot 3.3.13 — FailureAnalysis API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html), `description/action/cause`.
- [Spring Boot 3.3.13 — LoggingFailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/LoggingFailureAnalysisReporter.html), default logging reporter.
- [Spring Boot 3.3.13 — SpringApplication / Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), failure analysis and condition evaluation report.
- [Spring Boot 3.3.13 — SpringBootExceptionReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringBootExceptionReporter.html), startup exception-level extension point.
- [Spring Boot 3.3.13 — How-to: Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/how-to/application.html), registration via `META-INF/spring.factories`.

**Conclusion:** When an application fails at startup, `FailureAnalysisReporter` bridges **root-cause analysis output** and **messages humans can read, understand, and act on**. To improve diagnostic quality, clarify causes in the analyzer, clarify steps in the analysis, and use reporters to present safely and consistently without making an already fragile error path worse.
