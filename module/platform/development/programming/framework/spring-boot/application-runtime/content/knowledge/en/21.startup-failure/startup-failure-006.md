# FailureAnalyzer, FailureAnalysis, and Describing Corrective Actions

When **Spring Boot fails to start**, a long stack trace can span dozens of exception layers such as `BeanCreationException`, `BeanInstantiationException`, and the root error deep inside. Operators need faster answers to three questions: **what went wrong**, **why it went wrong**, and **where/how to fix it**. Spring Boot helps turn selected startup errors into clear diagnostic reports via `FailureAnalyzer` and `FailureAnalysis`.

For example, an application cannot open its port because another process already occupies it. Instead of forcing the reader through the whole stack trace, Spring Boot can display:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Web server failed to start because a configured port is already in use.

Action:

Stop the process using that port, or configure another server.port.
~~~

**This is a layout illustration, not a verbatim copy from a specific server version.** Actual messages depend on the cause, analyzer, and Spring Boot version.

This lesson belongs to the **Spring Boot Application Runtime** module, **Startup Failure** group, using **Spring Boot 3.3.x / Spring Framework 6.1 / Java 17+**. It focuses on the **startup failure analysis mechanism**, how to build a **`FailureAnalysis` with concrete corrective actions**, registering analyzers at the right bootstrap stage, and verifying results with a runnable project.

## 1. Problem: a stack trace by itself is not a remediation guide

A Spring error while creating a bean can be wrapped in multiple layers:

~~~text
SpringApplication.run(...)
  |
  +-- ApplicationContext.refresh()
       |
       +-- Creating bean demoGuard
            |
            +-- BeanCreationException
                 |
                 +-- BeanInstantiationException
                      |
                      +-- MissingTargetException
                           "Required setting demo.target is missing"
~~~

Looking only at the top line, a reader might think "Spring failed to create a bean" is enough to act on. Yet the real operational cause is that **the required property `demo.target` was not supplied**.

A useful analysis should answer:

| Field | Example | Question answered |
| --- | --- | --- |
| **Description** | `Required configuration 'demo.target' is missing or blank.` | What is wrong? |
| **Action** | `Set --demo.target=local before restarting the application.` | What must be done to fix it? |
| **Cause** | `MissingTargetException` | Which exception actually led to the analysis? |

The value lies not in "hiding" the stack trace, but in adding a **short, contextual, actionable interpretation layer**. For deep investigation, logs and root causes remain essential.

## 2. Three separate roles: Analyzer, Analysis, Reporter

| Component | Spring Boot 3.3 package | Responsibility |
| --- | --- | --- |
| `FailureAnalyzer` | `org.springframework.boot.diagnostics` | Accepts a startup `Throwable` and decides whether it can analyze it |
| `FailureAnalysis` | `org.springframework.boot.diagnostics` | Carries `description`, `action`, and `cause` data |
| `FailureAnalysisReporter` | `org.springframework.boot.diagnostics` | Displays/records a produced `FailureAnalysis` |
| `LoggingFailureAnalysisReporter` | `org.springframework.boot.diagnostics` | Default reporter that writes the analysis to logs |
| `AbstractFailureAnalyzer<T>` | `org.springframework.boot.diagnostics` | Convenience base class that locates an exception of type `T` in the cause chain |

Layered flow:

~~~text
Startup error
    |
    v
Throwable (may be wrapped across multiple layers)
    |
    v
FailureAnalyzer / AbstractFailureAnalyzer
    |                  |
    | analyzable       | unrecognized
    v                  v
FailureAnalysis       null
    |                  |
    v                  v
FailureAnalysisReporter   Other analyzers / standard error logging
    |
    v
Description + Action in startup log
~~~

`FailureAnalyzer` **is not responsible for fixing the error**. It only identifies and explains. `FailureAnalysis` is **diagnostic data**, not a new exception or a restart command. `FailureAnalysisReporter` is responsible for presenting the data where operators observe it.

## 3. Contract of `FailureAnalyzer`

The core interface looks like:

~~~java
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
~~~

This is an **abbreviated API signature** of `org.springframework.boot.diagnostics.FailureAnalyzer`, not a source file to add to your application.

Key contract rules:

- Return a `FailureAnalysis` when the analyzer **understands the exception and has an appropriate remediation**.
- Return `null` if the failure is **out of scope** or lacks sufficient context for a meaningful analysis.
- **Do not** treat `null` as "the error was handled successfully". Spring Boot may consult other analyzers or fall back to standard error logging.
- Never swallow startup exceptions to let the application keep running in an invalid state.
- Never perform dangerous side effects (deleting files, editing configs, mutating DBs, self-restarting) just to produce a message.

If you implement the interface directly, you may need to walk `Throwable.getCause()` because Spring wraps the real failure. A cleaner approach for most cases is extending `AbstractFailureAnalyzer<T>`.

## 4. `AbstractFailureAnalyzer<T>` finds the right exception type

Spring Boot provides the base class:

~~~java
public abstract class AbstractFailureAnalyzer<T extends Throwable>
        implements FailureAnalyzer {

    protected abstract FailureAnalysis analyze(
            Throwable rootFailure, T cause);
}
~~~

This is an **abbreviated view of the extension point to implement**; the actual class includes additional methods, including analyzing the outer `Throwable` and locating the matching `cause`.

Meaning of the two parameters:

- `rootFailure`: the outermost exception passed by Spring Boot into analysis.
- `cause`: the exception of type `T` found in the cause chain; usually closest to the failure condition the analyzer targets.

Example with a deeply nested root exception:

~~~text
ApplicationContextException
  -> BeanCreationException
       -> BeanInstantiationException
            -> MissingTargetException
~~~

With:

~~~java
public final class MissingTargetFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingTargetException> {
    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, MissingTargetException cause) {
        // ...
    }
}
~~~

Spring Boot invokes your protected method when the chain contains `MissingTargetException`. You do not need to write your own `getCause()` loop in this case.

If you cannot give a reliable recommendation (e.g., matching exception type yet missing necessary details), the analyzer **can return `null`** to give other analyzers a chance. Do not emit a vague or wrong action just to always produce a report.

## 5. What does `FailureAnalysis` contain?

Spring Boot 3.3 provides the constructor:

~~~java
new FailureAnalysis(description, action, cause)
~~~

And the methods:

~~~java
analysis.getDescription();
analysis.getAction();
analysis.getCause();
~~~

Where:

| Field | Meaning | Recommended content |
| --- | --- | --- |
| `description` | Explains the failure condition in terms operators understand | Exact invalid config/bean/condition name with context |
| `action` | Concrete remediation steps | Which property to change, which file to check, which command to run, how to verify |
| `cause` | Exception linked to the analysis | Provides technical context useful for logs and deeper investigation |

A `FailureAnalysis` can be constructed like this:

~~~java
FailureAnalysis analysis = new FailureAnalysis(
        "Required setting 'demo.target' is missing or blank.",
        "Set --demo.target=local and restart the application.",
        cause);
~~~

This snippet lives **inside a Java method** with a `Throwable` variable `cause` and `FailureAnalysis` imported. It is not a standalone program.

**Remediation actions must never simply say** "Check configuration" or "Contact support" in every scenario. Readers already know something failed; they need **the exact location and next step**. Aim for accurate cause descriptions that avoid misdirection and never leak secrets.

### How does Description differ from Action?

Description answers **"what is wrong?"**. Action answers **"what next step fixes it?"**.

Example:

~~~text
Description:
Property 'demo.target' is required but was not supplied.

Action:
Add --demo.target=local to the application arguments,
or define demo.target in application.properties,
then launch the application again.
~~~

Description does not merely repeat the class name `MissingTargetException`. Action does not merely tell the user to re-read the stack trace.

## 6. When does Spring Boot run failure analysis?

On a failing `SpringApplication.run(...)` path, the flow can be summarized as:

~~~text
main()
   |
   v
SpringApplication.run(args)
   |
   +-- Environment / context creation
   |
   +-- Bean definitions / refresh context
   |       |
   |       +-- exception occurs
   |
   v
Failure handling in SpringApplication
   |
   +-- Report error and clean up context when possible
   |
   +-- Load/apply matching FailureAnalyzers
   |       |
   |       +-- FailureAnalysis(description, action, cause)
   |
   +-- FailureAnalysisReporter writes analysis
   |
   v
run(...) does not complete normally; application does not reach ready
~~~

This diagram is a **conceptual model**, not an absolute guarantee of every internal call order across all exceptions. Failures can occur **before the context or BeanFactory is complete**.

Important:

- Failure analysis is a **startup failure diagnostic mechanism**.
- It does **not** automatically turn exceptions occurring hours after startup into `APPLICATION FAILED TO START` banners.
- It does **not** replace `@ControllerAdvice` or `@ExceptionHandler` for HTTP request error responses.
- It does **not** auto-fix configs, retry startup, or keep the application running after a critical failure.
- It does **not** guarantee a matching analyzer always exists; for unfamiliar errors, Spring Boot still supplies logs for investigation.

### Built-in examples provided by Spring Boot

Spring Boot ships built-in failure analyzers for many error classes, including **web server port in use**, certain configuration property binding/validation errors, and context/bean issues. Do not write a custom analyzer for errors that already produce clear descriptions and remediation steps.

Read the **Description/Action that already appears** before adding a custom analyzer. Writing custom analyzers for overly generic Java exceptions easily creates misleading diagnostics.

## 7. Registering custom analyzers via `META-INF/spring.factories`

A common pitfall: analyzers are needed **even when the application context fails to finish creating**. Therefore, per Spring Boot guidelines, **merely annotating a `FailureAnalyzer` class with `@Component` is not a reliable registration path for bootstrap failures**.

The official approach in Spring Boot 3.3 is creating:

~~~text
src/main/resources/META-INF/spring.factories
~~~

with the key:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failure.MissingTargetFailureAnalyzer
~~~

Notes:

- The key must be **`org.springframework.boot.diagnostics.FailureAnalyzer`**, not `FailureAnalysis` or `FailureAnalysisReporter`.
- The value must be the **fully qualified class name**, including package, and the class must be on the runtime classpath.
- The resource path must be **`META-INF/spring.factories`**, distinct from `application.properties` or auto-configuration's `AutoConfiguration.imports`.
- The bootstrap mechanism uses Spring factories loader to discover implementations across JARs and resources on the classpath.
- The analyzer class must be instantiable during failure; the cleanest design is a `public` class with a no-arg constructor and zero dependencies on business beans.
- To declare multiple analyzers in the same `spring.factories` file, use a comma-separated list of fully qualified class names; avoid repeating the same key expecting all values to survive.

A starter library can also bundle an analyzer and `spring.factories` so **applications using the library get targeted diagnostics**, provided the analyzer only matches exceptions scoped to that library rather than hijacking unrelated errors.

### Did Spring Boot 3.x drop `spring.factories`?

**Not for `FailureAnalyzer`.** In Spring Boot 3.3, **auto-configuration** lists moved to `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, while custom `FailureAnalyzer`s are still registered in **`META-INF/spring.factories`**. Do not confuse the two mechanisms.

## 8. Complete example: missing configuration yields Description and Action

We build a **Spring Boot CLI** requiring the `demo.target` property. Leaving it absent or blank prevents the context from starting. A custom analyzer turns `MissingTargetException` into concrete remediation instructions. Passing valid configuration runs the app and prints a success marker.

This example uses **Java 17, Spring Boot 3.3.13, and Gradle**, with no web server or database needed. It illustrates a **bean initialization failure during refresh**, right along the path Spring Boot analyzes.

### 8.1. Project structure

~~~text
failure-analysis-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/failure/
    │   │   ├── FailureAnalysisDemoApplication.java
    │   │   ├── MissingTargetException.java
    │   │   └── MissingTargetFailureAnalyzer.java
    │   └── resources/META-INF/spring.factories
    └── test/java/com/example/failure/
        └── MissingTargetFailureAnalyzerTest.java
~~~

**The three main Java source classes share the same package**; `spring.factories` references the exact analyzer class name.

### 8.2. Gradle configuring dependency versions properly

`settings.gradle`:

~~~groovy
rootProject.name = 'failure-analysis-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    // Use Gradle native BOM to manage Spring Boot starter versions.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Because the starters are declared **without versions**, you need a BOM as shown above or an equivalent dependency management mechanism. The `org.springframework.boot` plugin **alone should not be assumed to replace dependency management declarations**.

Environment: JDK 17+ and a Gradle version compatible with Spring Boot 3.3. The example uses Java 17 for broad compatibility and no web starter dependency.

### 8.3. Dedicated exception with clear semantics

File `src/main/java/com/example/failure/MissingTargetException.java`:

~~~java
package com.example.failure;

public final class MissingTargetException extends IllegalStateException {

    private final String propertyName;

    public MissingTargetException(String propertyName) {
        super("Missing required configuration: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return this.propertyName;
    }
}
~~~

As a custom `IllegalStateException`, it keeps a normal stack trace while providing **the missing property name** to the analyzer. Never embed **secret values** or tokens in the exception message.

In real systems, design a clearly scoped exception type rather than writing one broad analyzer matching every `IllegalStateException`.

### 8.4. Application creating a bean that requires `demo.target`

File `src/main/java/com/example/failure/FailureAnalysisDemoApplication.java`:

~~~java
package com.example.failure;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class FailureAnalysisDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(FailureAnalysisDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }

    @Bean
    DemoTarget demoTarget(Environment environment) {
        String value = environment.getProperty("demo.target");

        if (value == null || value.isBlank()) {
            throw new MissingTargetException("demo.target");
        }

        return new DemoTarget(value);
    }

    @Bean
    ApplicationRunner showTarget(DemoTarget target) {
        return args -> System.out.println("STARTUP_OK target=" + target.value());
    }

    record DemoTarget(String value) {
    }
}
~~~

Explanation:

1. `@SpringBootApplication` enables Spring Boot auto-configuration and component/bean definition processing.
2. `WebApplicationType.NONE` selects console application mode with no web server.
3. `@Bean demoTarget(...)` creates a normal singleton **during context refresh** when global lazy initialization is off.
4. If `demo.target` is blank or absent, the method **throws `MissingTargetException`**. Spring may wrap the exception in one or more bean creation error layers.
5. If valid, the `DemoTarget` bean is created; `ApplicationRunner` prints the success line.
6. There is no `try/catch` in `main` swallowing startup failures or printing a misleading message.
7. `String.isBlank()` and `record` are both available in Java 17.

**Example limitations:** the `demo.target` property is an illustrative key with no real external URL/service integration. In real applications, validate format/connectivity in the appropriate phase and never log secrets.

**Note on lazy:** if `spring.main.lazy-initialization=true` is enabled, a bean might not be created immediately. Here `ApplicationRunner` still depends on `DemoTarget`, so it is usually requested before ready anyway. When testing startup failures, keep global lazy at its `false` default to reliably observe bean failures during refresh.

### 8.5. Analyzer locating the exception in the cause chain

File `src/main/java/com/example/failure/MissingTargetFailureAnalyzer.java`:

~~~java
package com.example.failure;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class MissingTargetFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingTargetException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, MissingTargetException cause) {

        String property = cause.getPropertyName();

        String description =
                "Required configuration '" + property + "' is missing or blank.";

        String action =
                "Set --" + property + "=local when starting the application, "
                + "or add " + property + "=local to application.properties. "
                + "Then restart the application.";

        return new FailureAnalysis(description, action, cause);
    }
}
~~~

**This is a complete class** adhering to `AbstractFailureAnalyzer`'s generic contract:

- Matches only failures containing `MissingTargetException` in the cause chain.
- Uses the property name to build specific output.
- `description` states the exact condition.
- `action` offers **two immediate fixes**: a command-line argument or configuration file entry.
- `cause` preserves the matched domain exception inside `FailureAnalysis`.
- Does not touch `ApplicationContext`, inject beans, or perform I/O inside the analyzer.

Although the signature includes `rootFailure`, the demo does not need it because `cause` suffices. `AbstractFailureAnalyzer` still locates `cause` starting from the outermost exception Spring Boot passes in.

If an analyzer handles a shared exception covering multiple cases, verify specific conditions and return `null` when evidence is insufficient rather than giving wrong advice.

### 8.6. Registration via `spring.factories`

Create `src/main/resources/META-INF/spring.factories` containing **exactly one line**:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failure.MissingTargetFailureAnalyzer
~~~

Ensure the resource sits inside `META-INF` on the runtime classpath. With the standard Gradle Java plugin, files in `src/main/resources` are packaged as resources.

**Do not** replace it with:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=com.example.failure.MissingTargetFailureAnalyzer
~~~

because an analyzer is not an auto-configuration class. Nor should `AutoConfiguration.imports` be used to register analyzers.

### 8.7. Unit testing analyzer behavior

File `src/test/java/com/example/failure/MissingTargetFailureAnalyzerTest.java`:

~~~java
package com.example.failure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MissingTargetFailureAnalyzerTest {

    private final MissingTargetFailureAnalyzer analyzer =
            new MissingTargetFailureAnalyzer();

    @Test
    void recognizesNestedCauseAndSuppliesAction() {
        MissingTargetException cause =
                new MissingTargetException("demo.target");
        Throwable wrapper = new IllegalStateException(
                "Bean creation failed", cause);

        FailureAnalysis analysis = analyzer.analyze(wrapper);

        assertNotNull(analysis);
        assertTrue(analysis.getDescription().contains("demo.target"));
        assertTrue(analysis.getAction().contains("--demo.target=local"));
        assertSame(cause, analysis.getCause());
    }

    @Test
    void ignoresUnrelatedExceptions() {
        FailureAnalysis analysis = analyzer.analyze(
                new IllegalArgumentException("Unrelated failure"));
        assertNull(analysis);
    }
}
~~~

The first test confirms a **nested cause inside a wrapper exception** is still matched; the second confirms the analyzer does not claim unrelated errors. This test invokes the analyzer directly and **does not verify `spring.factories` loading or the full startup banner**. Hence testing the executable JAR is still required.

### 8.8. Build

In a project directory with a compatible Gradle Wrapper:

~~~bash
./gradlew clean test bootJar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

Without a wrapper, using a compatible installed Gradle:

~~~bash
gradle clean test bootJar
~~~

With the example's `rootProject.name` and `version`, the JAR path is normally:

~~~text
build/libs/failure-analysis-demo-1.0.0.jar
~~~

If the project customizes artifact names or classifiers, use the actual built file.

### 8.9. Running the failure branch

Start a new Java process **without passing `demo.target`**:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar
~~~

On the missing-configuration branch when the analyzer is properly loaded, logs should contain **content equivalent to**:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Required configuration 'demo.target' is missing or blank.

Action:

Set --demo.target=local when starting the application, or add
demo.target=local to application.properties. Then restart the application.
~~~

The block above is an **excerpt of expected diagnostic content**, not a promise on exact full stdout/stderr or line wrapping. The reporter may add timestamps, logger names, other log lines, and its own formatting. What to verify is that **Description/Action include the right key and remediation**.

The app **does not print** `STARTUP_OK` on the missing-configuration path. `SpringApplication.run` does not complete normally. Running the executable JAR along a failure path usually yields a **non-zero exit code**, yet verify it directly on the launched JVM rather than reading Gradle wrapper exit codes and assuming they are Java's.

### 8.10. Running the success branch

Start a new Java process with a valid property:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar --demo.target=local
~~~

Markers explicitly printed by **the demo itself**:

~~~text
STARTUP_OK target=local
~~~

There is no `MissingTargetException` here and no reason for the analyzer to emit Description/Action. Spring Boot's logger may print routine lines. In a CLI app without a web server or other non-daemon workers, the JVM may exit after the runner finishes; in long-running web apps, the process keeps running to serve requests.

### 8.11. Testing the blank value case

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar --demo.target=
~~~

The empty `""` value fails `String.isBlank()`, triggering the analyzer. Verify in real configs that no higher-precedence property source supplies a value or that global lazy was not accidentally enabled, shifting bean creation timing.

## 9. Writing valuable Descriptions

A Description should satisfy three criteria:

1. **Accurate symptom:** state the observable condition confirmed by code.
2. **Sufficient context:** include the relevant property, bean, port, file, or config source name.
3. **No over-reaching assumptions:** if you only know a connection failed, do not state with certainty "wrong password".

Comparison:

| Weak | Better |
| --- | --- |
| "Bean creation failed" | "Bean 'paymentClient' could not start because required property 'payment.endpoint' is missing." |
| "Database down" | "Database connection could not be established with the configured endpoint." |
| "Bad value" | "The value of 'worker.parallelism' must be greater than zero." |
| "An error occurred" | "The configured HTTP port could not be bound by the embedded server." |

When code can pinpoint the exact condition, Description should be **clearer than framework exception types**. When external causes are unknown, use cautious phrasing like "could not connect" and let logs retain the technical exception.

### Should you embed raw `Exception.getMessage()` directly in Description?

It can help in well-understood cases, but check for **sensitive data**, unreadable formatting, and stability. Some drivers put connection strings, usernames, file paths, or request details in exception messages. Never write credentials, tokens, or full connection URLs into startup reports just to make them informative.

## 10. Writing truly actionable Actions

A helpful corrective action answers:

- **What to change?** e.g., `demo.target`, `server.port`, secret key, dependency.
- **Where to change it?** `application.properties`, environment variable, CLI argument, ConfigMap/Secret, deployment config.
- **What is a valid value or criterion?** e.g., "non-empty", unused port, valid URL format.
- **How to verify?** restart, inspect readiness/startup logs, verify binding or connection.
- **Where to look if it still fails?** where relevant stack traces or condition reports live.

Property example:

~~~text
Action:
Set demo.target to a non-blank value using
--demo.target=local or application.properties,
then restart and verify the startup succeeds.
~~~

Port-in-use example:

~~~text
Action:
Find the process that occupies the configured server.port,
stop that process if appropriate, or assign an unused port,
then restart the application.
~~~

Missing required file example:

~~~text
Action:
Ensure the specified configuration file exists and is readable
inside the running container; verify its mount path and permissions,
then restart the application.
~~~

**Never** write Actions suggesting dropping databases, loosening permissions arbitrarily, disabling security, or pasting passwords into logs. Diagnostics must lead to safe, properly authorized operations.

## 11. Why doesn't an analyzer sometimes run?

Most common reasons:

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| Only stack trace appears despite analyzer class | `spring.factories` resource not on runtime classpath | Inspect JAR paths and contents |
| Analyzer not instantiated | Wrong fully qualified class name, unsuitable constructor | Check package, class visibility, dependencies |
| Analyzer exists yet does not match | Actual exception lacks type `T` in cause chain | Check root cause and unit tests |
| `analyze(...)` returns `null` | Handling condition unmet or deliberately deferred to others | Inspect logic branches |
| Used `@Component` instead of `spring.factories` | Context failed before bean creation | Register via bootstrap mechanism |
| Used `AutoConfiguration.imports` | Confused auto-configuration key with analyzer | Use key `org.springframework.boot.diagnostics.FailureAnalyzer` |
| Multiple relevant analyzers | Another analyzer ran first | Narrow exception scope and check ordering |
| Failure occurred **after startup** | Bypassed `SpringApplication.run` failure handling | Use logging, `@ControllerAdvice`, proper metrics |
| No Description/Action in logs | Logging/reporting config hides it or no matching analyzer | Check startup logs, reporter, level, and cause |
| Checked only `bootRun` exit status | Gradle may return its own exit code | Run the executable JAR directly |

Do not convert all exceptions into one generic class just so an analyzer "matches" more often. Analyzers should have **narrow responsibility**, match on clear causes, and never produce false diagnoses.

### Verifying packaged resources

After `./gradlew bootJar`:

~~~bash
jar tf build/libs/failure-analysis-demo-1.0.0.jar
~~~

In a Spring Boot executable JAR, application resources normally appear at the logical path:

~~~text
BOOT-INF/classes/META-INF/spring.factories
~~~

If the analyzer lives in a dependency library JAR, the resource sits inside a JAR under `BOOT-INF/lib`. Seeing the resource only proves **it was packaged**, not that the class loads, its constructor succeeds, or the exception matches. Test both failure and success startup paths.

## 12. Real-world verification with shell and CI

### Bash: capturing logs and preserving exit codes

Do not assume "seeing an Action message" guarantees the shell received a failure exit code. Run the executable JAR and read status:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar > fail.log 2>&1
status=$?
printf 'JAVA_EXIT=%s\n' "$status"
~~~

On a startup failure path, status is **normally non-zero**. Cross-check the log:

~~~bash
grep -F "APPLICATION FAILED TO START" fail.log
grep -F "demo.target" fail.log
grep -F "Action:" fail.log
~~~

These `grep` commands are manual checks in a test environment, not a complete error-proof CI script. If `set -e` is enabled, wrap the Java invocation in `if`/`else` so a non-zero exit does not abort the script before recording results.

### PowerShell

~~~powershell
java -jar .\build\libs\failure-analysis-demo-1.0.0.jar
$code = $LASTEXITCODE
Write-Output "JAVA_EXIT=$code"
~~~

`$LASTEXITCODE` holds the native executable's exit code, distinct from PowerShell's Boolean `$?`. When measuring startup failures, inspect console/redirected logs accordingly.

### CI should verify both paths

A solid CI smoke test verifies:

1. **Without `demo.target`** -> JAR exits non-zero and logs contain the expected Description/Action.
2. **With `--demo.target=local`** -> JAR succeeds and outputs `STARTUP_OK target=local`.
3. **`spring.factories`** is actually packaged in the right location.
4. Messages do not print secrets or sensitive data.
5. Code/config changes introducing a new failure do not make the analyzer fall back to a vague generic message.

Do not assert **byte-for-byte identical stdout/stderr**: timestamps, versions, loggers, and stack traces vary. Assert key markers and content while retaining raw logs for investigation.

## 13. When to use `FailureAnalysisReporter`?

`FailureAnalyzer` **analyzes**, whereas `FailureAnalysisReporter` **reports**. Interface:

~~~java
public interface FailureAnalysisReporter {
    void report(FailureAnalysis analysis);
}
~~~

This is an abbreviated signature; Spring Boot ships `LoggingFailureAnalysisReporter` for standard log output.

Normally **you do not need a custom reporter**. Add one only for clear requirements such as:

- Sending a diagnostic event to an independent monitoring system with sanitized data.
- Standardizing format for a container runtime or operational tooling.
- Attaching internal incident codes to controlled messages.

If you genuinely need a custom reporter, remember it executes during a **startup failure**, so it must not rely on a Spring bean, HTTP client, or queue listener that the context may not have built. A reporter should never auto-fix config, instantiate a new app, or throw extra exceptions on the failure path.

### Custom reporter as another extension example

~~~java
package com.example.failure;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalysisReporter;

public final class CompactFailureReporter
        implements FailureAnalysisReporter {

    @Override
    public void report(FailureAnalysis analysis) {
        System.err.println("BOOT_FAILURE: " + analysis.getDescription());
        System.err.println("REMEDIATION: " + analysis.getAction());
    }
}
~~~

This is an **optional illustrative class**, not a required file in Section 8's project. To use it, configure reporter registration per Spring Boot documentation and ensure it leaks no sensitive details; **do not assume creating the class makes Boot auto-discover it**.

Adding a reporter can produce duplicate output if the default logging reporter also runs. Before adding one, evaluate whether clear failure analysis via default logging already meets your needs.

## 14. `FailureAnalyzer` vs `@ControllerAdvice` and `ApplicationFailedEvent`

| Mechanism | Scope | Best suited when |
| --- | --- | --- |
| `FailureAnalyzer` | Analyzes Throwables when `SpringApplication` startup fails | You want helpful Description/Action when the app fails to start |
| `FailureAnalysis` | Analysis payload | Passing description, remediation, and cause to a reporter |
| `FailureAnalysisReporter` | Presents analysis results | Logging or reporting bootstrap errors |
| `ApplicationFailedEvent` | Event Spring Boot publishes on startup failure | Listener needs to observe failure events and clean up bootstrap metadata appropriately |
| `@ControllerAdvice` / `@ExceptionHandler` | HTTP request handling errors in a running context | Returning structured responses to API clients |
| `ConditionEvaluationReport` | Details on why auto-configuration conditions matched/did not match | Investigating auto-configuration and beans |
| `ExitCodeGenerator` / `ExitCodeExceptionMapper` | Defines process exit status when applicable | Shell/Job/CI requires explicit success/failure codes |

An analyzer **is not a retry mechanism**, does not replace normal logging, and does not automatically assign custom shell exit codes for every error. If an app needs specific shell exit codes, that is a **separate contract** handled by the exit-code APIs.

## 15. Investigating when no analyzer recognizes the failure

When no matching analyzer applies, continue **investigating via the exception chain and Spring Boot condition data**.

In a debug environment, you can run:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar --debug
~~~

`--debug` makes Spring Boot print extra **ConditionEvaluationReport** details, including why certain auto-configurations did or did not apply. It does **not** magically synthesize a `FailureAnalyzer` for every error and may not explain bugs in business code.

For applications that started successfully with Actuator and the endpoint exposed, `/actuator/conditions` lets you inspect configuration conditions. When an application **fails to start**, do not expect to query HTTP endpoints on the failed app itself.

Investigation steps:

1. Determine whether the failure occurred before or inside `ApplicationContext.refresh()`.
2. Locate the outermost exception and nested `Caused by` chain.
3. Identify the involved bean, property, port, or resource.
4. Check if a built-in analyzer already printed a helpful Action.
5. If this is a recurring library/application-specific error, create a **narrow** custom exception and analyzer.
6. Verify the corrective action in a test environment and update runbooks.
7. Never discard stack traces/exception causes just because an analysis banner exists.

## 16. Can an analyzer receive `Environment` or `BeanFactory`?

According to Spring Boot documentation on custom failure analyzers, if an implementation needs `Environment` or `BeanFactory`, it can declare them as **constructor arguments** so the analyzer loader supplies them when available.

Keep in mind:

- Failures can happen **before** a `BeanFactory` is complete or the context is active.
- Never assume business beans have been constructed for injection into an analyzer.
- Never open DB connections, call REST APIs, or access secrets inside an analyzer constructor.
- If Description/Action can be built solely from the **exception type and safe exception data**, that solution is simpler and more resilient.

This article's example uses a no-arg constructor so it has zero dependence on context state. That lets the analyzer handle bean creation errors without risking extra bootstrap failures.

## 17. Ordering multiple analyzers and the rule of returning `null`

An application can have Spring Boot's built-in analyzers, starter analyzers, and internal custom analyzers.

If an analyzer matches too broadly, it may give bad advice or steal the chance for a more specific diagnosis from another analyzer. Therefore:

- Target a **specific** exception type, such as `MissingTargetException`, instead of every `RuntimeException`.
- Return `null` when evidence is insufficient for an accurate Action.
- When selection order matters, check ordering mechanisms supported by your API/version rather than relying on classpath JAR order.
- Do not expect all analyzers to "build a chain of Actions" that the framework merges. The goal is producing **one useful analysis** for the active error.
- Unit-test analyzers in isolation and smoke-test **real startup paths** to spot conflicts with other analyzers.

Do not abuse `FailureAnalyzer` as a catch-all handler for generic app exceptions. Diagnostic structures must reflect **proven** error conditions.

## 18. Interaction with lazy initialization

If you configure:

~~~properties
spring.main.lazy-initialization=true
~~~

some beans may only be instantiated on first access **after startup**. When that happens, late bean creation failures **may bypass the `SpringApplication.run` failure path**, so custom failure analyzers will not display the startup banner as they do during refresh.

Hence, if a bean **must be valid before serving traffic**:

- Mark critical beans non-lazy as needed.
- Ensure startup checks/runners touch critical beans before readiness where appropriate architecturally.
- Write integration tests exercising first-use paths, not just context startup.
- Use proper logging and runtime error handling for errors occurring after the app is ready.

Do not treat `FailureAnalyzer` as a guarantee that lazy bean errors will always appear "neatly explained" at any lifecycle point.

## 19. Protecting sensitive information in Description and Action

Startup messages may be collected by:

- Console logs and log aggregators.
- CI/CD pipelines and deployment failure records.
- Docker/Kubernetes logs.
- Monitoring, alerts, and incident tickets.

Therefore, never include in Description/Action:

- Passwords, API tokens, private keys, or full URLs with credentials.
- Raw values of sensitive properties.
- Full request bodies, customer data, or personal payloads.
- Truncated stack traces pasted wholesale into an "Action" field.

Instead of "Password `secret123` is invalid", write "Configured credentials for datasource could not be validated; inspect the secret source and verify permissions." Log only **the property name or resource type to check**, never the secret value.

If internal details are especially sensitive, apply access controls on logs and alerts. Analyzers exist to **aid investigation**, not to bypass log security principles.

## 20. Checklist when adding a FailureAnalyzer to a library

| QA item | What to verify |
| --- | --- |
| Specific exception | Targets concrete error type, does not match everything |
| Description | States the exact failure condition |
| Action | Gives at least one feasible remediation step |
| Cause | Retains relevant exception without swallowing root cause |
| Scope | Handles only appropriate startup failures |
| Registration | `META-INF/spring.factories` uses the right key |
| Classpath | Class and resource both reside in the artifact |
| Constructor | Does not depend on uncreated beans |
| Null behavior | Unrelated exceptions return `null` |
| Build | Spring Boot version, BOM, and Java are compatible |
| Unit tests | Cover nested cause matching and non-matching errors |
| Smoke tests | Run `java -jar` for both fail and success |
| Logs | No leaked secrets, readable text |
| Exit status | Verified via shell, not just reading the banner |
| Rollout | Runbook states where to fix config and required permissions |

**Especially:** test the **actually packaged JAR**, not just the IDE classpath. Many "analyzer didn't run" issues stem from `spring.factories` being dropped during build/shading, or mismatched package/class names.

## 21. Common practical mistakes

**1. Only annotating the analyzer with `@Component`.** The Spring context may fail before the analyzer bean is instantiated. Use `META-INF/spring.factories` for bootstrap paths.

**2. Placing the analyzer in `AutoConfiguration.imports`.** That metadata serves a different purpose; analyzers must use the key `org.springframework.boot.diagnostics.FailureAnalyzer`.

**3. Throwing `FailureAnalysis` like an exception.** It is a data object; throw a specific exception at the failure site and analyze it in the analyzer.

**4. Failing to inspect nested causes.** `BeanCreationException` often wraps the root exception. `AbstractFailureAnalyzer<T>` finds type `T`.

**5. Returning an analysis even without a match.** This can block a more accurate diagnosis; return `null` when evidence is lacking.

**6. Writing an Action that just says "Check logs".** That is not concrete remediation. Name the property, file, endpoint, or command.

**7. Performing fixes inside the analyzer.** Analysis is not a remediation engine. Avoid modifying files, opening connections, or making network calls.

**8. Assuming a banner means the app recovered.** When bootstrap fails, the context is normally unusable; the banner only explains why.

**9. Thinking every runtime exception is handled by an analyzer.** This mechanism applies to `SpringApplication` startup failures, not web exception handlers.

**10. Comparing full log output verbatim.** Timestamps, stack trace paths, loggers, and wrapping change; assert essential content.

**11. Assuming an analyzed failure automatically yields a custom exit code.** Analysis and process exit are separate contracts; verify with the executable JAR.

**12. Trying to fetch `/actuator/conditions` from the failed app itself.** The app may never have opened its server. Use startup debug logs/condition reports instead.

**13. Putting credentials in Description.** Startup logs are often broadly accessible; name only the key/source to inspect.

**14. Skipping tests on the success branch.** A working analyzer with broken app logic still fails valid configs; test both paths.

**15. Missing Gradle dependency management.** Versionless starters without a BOM or dependency-management plugin can break the build before Spring Boot runs, leaving `FailureAnalyzer` no chance to execute.

## 22. Self-check questions

1. **What does `FailureAnalyzer` do?** Receives a startup Throwable and can return a readable `FailureAnalysis`.
2. **What are the three components of `FailureAnalysis`?** Description, Action, and Cause.
3. **What does `FailureAnalysisReporter` do?** Presents/records the analysis output.
4. **What is the role of `LoggingFailureAnalysisReporter`?** Writes failure analysis to the logs.
5. **What does `FailureAnalyzer.analyze(...)` return when it cannot handle an error?** `null`.
6. **Why extend `AbstractFailureAnalyzer<MissingTargetException>`?** To locate a specific exception type in the cause chain.
7. **How does `rootFailure` differ from `cause`?** Root failure is the outermost exception; cause is the matched type `T`.
8. **Where are custom analyzers registered in Spring Boot 3.3?** `META-INF/spring.factories`.
9. **What is the registration key?** `org.springframework.boot.diagnostics.FailureAnalyzer`.
10. **Can `@Component` alone handle failures before refresh?** Not reliably.
11. **Is `AutoConfiguration.imports` used instead of `spring.factories` to register analyzers?** No.
12. **How does Description differ from Action?** Description explains what is wrong; Action explains what to do to fix it.
13. **Is an Action saying "Check your configuration" specific enough?** Usually not; name the property and how to fix it.
14. **Does `FailureAnalyzer` edit config files automatically?** No; it only analyzes.
15. **Does an HTTP `500` request error trigger the startup analysis banner?** No.
16. **Does an analyzer automatically run on lazy beans instantiated after startup?** Not automatically, since they may fall outside `run()`'s failure path.
17. **What helps explain why auto-configuration did not match?** `ConditionEvaluationReport`, typically via `--debug` or Actuator when running.
18. **Does a unit test on the analyzer prove `spring.factories` is packaged properly?** No; smoke-test the executable JAR.
19. **In the example, if `demo.target` is missing, does `STARTUP_OK` print?** No; the bean fails during refresh.
20. **What happens when `--demo.target=local` is supplied?** The bean succeeds and the runner prints the success marker.
21. **Does `FailureAnalysis` imply the shell receives a custom exit code?** No; verify exit status separately.
22. **If an exception message contains a token, should it be copied into Description?** No; protect sensitive data.
23. **When is a custom analyzer unnecessary?** When built-in analyzers already provide adequate description and remediation.
24. **Why keep analyzers simple?** They run after bootstrap has already failed, when the context may be unavailable and errors inside the analyzer worsen diagnostics.

**Conclusion:** In Spring Boot 3.3, `FailureAnalyzer` receives startup errors, `AbstractFailureAnalyzer<T>` locates the target exception in the cause chain, `FailureAnalysis` carries **Description + Action + Cause**, and `FailureAnalysisReporter` presents the result. Register custom analyzers via **`META-INF/spring.factories`**, match specific exceptions, write concrete remediation steps, keep secrets out of logs, and **verify with both unit tests and fail/success executable JAR runs**. A good startup message tells operators **what to fix next**, without obscuring the technical root cause.

### References

- Spring Boot 3.3.13 — **SpringApplication: Startup Failure**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — **How-to: Create Your Own FailureAnalyzer**: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Boot 3.3.13 — **FailureAnalyzer API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html
- Spring Boot 3.3.13 — **AbstractFailureAnalyzer API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html
- Spring Boot 3.3.13 — **FailureAnalysis API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html
- Spring Boot 3.3.13 — **FailureAnalysisReporter API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html
- Spring Boot 3.3.13 — **LoggingFailureAnalysisReporter API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/LoggingFailureAnalysisReporter.html
- Spring Boot 3.3 — **Gradle Plugin Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
