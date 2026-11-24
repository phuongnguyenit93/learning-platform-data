# Simulating a Failing Runner and Creating a FailureAnalyzer for Custom Startup Errors in Spring Boot

## 1. Practice Objectives

Spring Boot can finish creating the ApplicationContext and still **fail startup** if an ApplicationRunner or CommandLineRunner throws an exception. This is an important boundary: beans have been instantiated and ApplicationStartedEvent may have already fired, yet ApplicationReadyEvent has not appeared and the application is not ready to serve business work.

When a runner fails due to a custom policy—for instance, an unapproved deployment region—a generic stack trace is often hard for operators to interpret. We will build a **FailureAnalyzer** to turn a business exception into a clear report with **Description** and **Action**, while preserving the failed startup outcome.

Specific objectives:

1. Understand the ordering of ApplicationStartedEvent, ApplicationRunner, ApplicationReadyEvent, and ApplicationFailedEvent.
2. Write two runners with @Order to verify that a subsequent runner does not run when an earlier runner fails.
3. Throw a StartupPolicyException containing structured information instead of a vague exception.
4. Write StartupPolicyFailureAnalyzer accepting a Throwable, finding the root cause, and creating a FailureAnalysis.
5. Register the analyzer via META-INF/spring.factories and prove Spring Boot actually loads it.
6. Test the valid branch, the failure branch, view the user-facing report, and inspect exit status.
7. Write JUnit 5 unit tests for the analyzer with an exception wrapped by SpringApplication.
8. Distinguish a startup FailureAnalyzer from error handlers used after Ready.

Consistent versions: **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, Gradle**. The example uses a **non-web** application so results are easy to see when the CLI exits.

## 2. Runner Position in the Lifecycle

~~~text
SpringApplication.run(args)
       |
       +-- Environment and create ApplicationContext
       +-- Refresh context
       |     +-- Register / instantiate beans
       |     +-- Dependency injection
       |     +-- @PostConstruct, init callbacks
       |     +-- SmartLifecycle.start
       |
       +-- ApplicationStartedEvent
       +-- LivenessState.CORRECT
       |
       +-- ApplicationRunner / CommandLineRunner
       |     +-- First runner
       |     |     +-- If it throws an exception -> failure handling
       |     +-- Next runner if previous succeeds
       |
       +-- ApplicationReadyEvent if runners succeed
       +-- ReadinessState.ACCEPTING_TRAFFIC
       |
       +-- run() returns
~~~

**Started differs from Ready.** ApplicationStartedEvent arrives after refresh but before runners. ApplicationReadyEvent only appears after runners on a successful startup path. When a runner throws an exception, Boot transitions to failure handling, publishes ApplicationFailedEvent to registered listeners, and reports the cause.

| API | Timing | Role |
| --- | --- | --- |
| @PostConstruct | Bean initialization during context refresh | Initialize a single bean's resources |
| ApplicationStartedEvent | After context refresh, before runners | Observe the started milestone |
| ApplicationRunner | After Started, before Ready | Execute controlled startup policies/jobs |
| CommandLineRunner | Same runner phase | Like ApplicationRunner, but receives String... |
| ApplicationReadyEvent | After all runners complete | Observe the ready milestone |
| ApplicationFailedEvent | When SpringApplication.run fails | Observe startup failure |
| FailureAnalyzer | Inside startup failure analysis mechanism | Produce an operator-friendly error report |

**ApplicationRunner** receives ApplicationArguments containing parsed options and non-options. **CommandLineRunner** receives raw String... args. Both can implement Ordered or use @Order to specify order.

Do not confuse a runner with an automatic background worker. SpringApplication normally invokes runners synchronously. If a runner merely submits a task and returns, Boot may proceed to Ready while the async task has not finished.

## 3. What Is a FailureAnalyzer?

In Spring Boot, FailureAnalyzer is an API that analyzes a Throwable from a startup failure and can return a FailureAnalysis:

~~~java
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
~~~

This is an illustrative API signature, not source code you define yourself. The real import is **org.springframework.boot.diagnostics.FailureAnalyzer**.

FailureAnalysis has the constructor:

~~~java
new FailureAnalysis(description, action, cause)
~~~

- **Description**: describes the issue and which configuration/step is invalid.
- **Action**: guidance an operator can act on immediately.
- **Cause**: the root Throwable relevant to the report.

If an analyzer **does not recognize** the error, it must return **null** to yield to other analyzers. A good analyzer never catches every RuntimeException and attaches the same incorrect message.

Spring Boot has a default **FailureAnalysisReporter** to log the result; an analyzer **does not rescue the application**, does not let the runner continue, does not fix config, and does not decide readiness or business exit codes.

~~~text
Runner.run()
   |
   +-- throw StartupPolicyException
   |
SpringApplication runner caller
   |
   +-- May wrap error in IllegalStateException
   |
SpringApplication startup failure handling
   |
   +-- FailureAnalyzers from spring.factories
   |     |
   |     +-- StartupPolicyFailureAnalyzer
   |          |
   |          +-- Find StartupPolicyException in cause chain
   |          +-- FailureAnalysis(description, action, cause)
   |
LoggingFailureAnalysisReporter
   |
APPLICATION FAILED TO START
   |
run() fails and Ready not reached
~~~

### Why Search Deeply Through Causes?

Spring Boot may wrap runner exceptions:

~~~text
IllegalStateException: Failed to execute ApplicationRunner
    Caused by: StartupPolicyException:
      Unsupported startup region: moon-base
~~~

This is an **illustrative pattern**; exact line-by-line stack traces depend on version. If an analyzer only inspects the outermost Throwable object, it may miss StartupPolicyException. There are two approaches:

- Implement FailureAnalyzer and walk Throwable.getCause(), as in this project.
- Extend AbstractFailureAnalyzer<StartupPolicyException> so the base class locates the type in the cause chain.

For user-authored exception packages, custom exceptions should include **non-sensitive key names and values** for accurate reporting. Never place secrets, access tokens, passwords, or connection strings with credentials inside errors.

## 4. Business Scenario of the Lab

The application allows only two values for **demo.startup.region**:

- ap-southeast-1: valid, default.
- ap-northeast-1: second valid option.
- moon-base: invalid, used to trigger an intentional failure.

**RegionValidationRunner** has @Order(10): prints the region and throws StartupPolicyException if not on the allowlist.

**StartupAuditRunner** has @Order(20): prints RUNNER_AUDIT. When the first runner fails, this runner is not invoked on the successful startup path.

**StartupEventLog**: prints EVENT_STARTED and EVENT_READY.

An ApplicationFailedEvent listener is registered directly on SpringApplication **before run** to observe failures even if the context has not finished being created.

**StartupPolicyFailureAnalyzer**: locates the exact business exception across the cause chain; builds Description and Action without catching unrelated errors.

## 5. Project Structure

~~~text
runner-failure-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          RunnerFailureLab.java
          events/
            StartupEventLog.java
          startup/
            StartupPolicyException.java
            RegionValidationRunner.java
            StartupAuditRunner.java
          diagnostics/
            StartupPolicyFailureAnalyzer.java
      resources/
        application.properties
        META-INF/
          spring.factories
    test/
      java/
        demo/
          diagnostics/
            StartupPolicyFailureAnalyzerTest.java
~~~

**Critical point:** the discovery file must sit at exactly **src/main/resources/META-INF/spring.factories**. This is the mechanism Spring Boot uses to find custom FailureAnalyzers. It does not belong in the Java source root, application.properties, or AutoConfiguration.imports.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'runner-failure-lab'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

spring-boot-starter is enough for a CLI running ApplicationRunner. Tomcat or a servlet container is unnecessary, making Ready and failure outcomes clearer. spring-boot-starter-test provides JUnit 5 and AssertJ.

JDK 17+, compatible Gradle, and access to download dependencies/plugins or a populated cache are required. If the project has a wrapper, use gradlew; otherwise, use an installed Gradle.

### 5.3. application.properties

~~~properties
spring.application.name=runner-failure-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false

demo.startup.region=ap-southeast-1
~~~

Command-line options can override the default region. No web server is enabled because the lab verifies runners/failures rather than endpoints. The banner/log-startup-info properties reduce noise, though Gradle, loggers, and the JVM may still print additional logs.

## 6. Main and Event-Observing Application

### 6.1. RunnerFailureLab.java

File **src/main/java/demo/RunnerFailureLab.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class RunnerFailureLab {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(RunnerFailureLab.class);

        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                        System.out.println("EVENT_FAILED"));

        app.run(args);
    }
}
~~~

**Why call addListeners directly?** ApplicationFailedEvent can fire when the context is half-created or has not been refreshed; a @Component listener may not exist early enough. Registering on SpringApplication before run ensures receiving this event during runner failure simulations.

**Do not catch the exception and just log in main.** If a mandatory policy is violated, let run truly fail. When an error escapes a non-web main, the JVM usually returns a non-zero exit status; Gradle bootRun may also report task failure. Do not hard-code a specific status when using wrappers because tools and OSes can vary.

### 6.2. StartupEventLog.java

File **src/main/java/demo/events/StartupEventLog.java**:

~~~java
package demo.events;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventLog {

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("EVENT_STARTED");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("EVENT_READY");
    }
}
~~~

This class is scanned because it sits in a subpackage of demo. It only records two milestones; ApplicationFailedEvent already has a listener attached to SpringApplication. On the runner failure branch, we expect EVENT_STARTED and then EVENT_FAILED, with no EVENT_READY.

## 7. Dedicated Business Exception

File **src/main/java/demo/startup/StartupPolicyException.java**:

~~~java
package demo.startup;

public final class StartupPolicyException extends RuntimeException {

    private final String propertyName;
    private final String rejectedValue;

    public StartupPolicyException(String propertyName,
                                  String rejectedValue) {
        super("Unsupported startup region: " + rejectedValue);
        this.propertyName = propertyName;
        this.rejectedValue = rejectedValue;
    }

    public String getPropertyName() {
        return propertyName;
    }

    public String getRejectedValue() {
        return rejectedValue;
    }
}
~~~

In this lab, rejectedValue is a non-sensitive region. In real applications, if validation involves passwords, API secrets, DB connections, or bearer tokens, do not put raw values in exception messages or FailureAnalysis. Report the configuration key/source and a secure action instead.

**RuntimeException** is appropriate to represent an unrecoverable startup condition. If the exception originates from another error, preserve the original cause when translating to a custom exception rather than discarding the stack trace.

## 8. Ordered ApplicationRunners

### 8.1. RegionValidationRunner.java

File **src/main/java/demo/startup/RegionValidationRunner.java**:

~~~java
package demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class RegionValidationRunner implements ApplicationRunner {

    private final Environment environment;

    public RegionValidationRunner(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String region = environment.getProperty(
                "demo.startup.region", "ap-southeast-1");

        System.out.println("RUNNER_VALIDATE=" + region);

        boolean valid = "ap-southeast-1".equals(region)
                || "ap-northeast-1".equals(region);

        if (!valid) {
            throw new StartupPolicyException(
                    "demo.startup.region", region);
        }

        System.out.println("RUNNER_VALIDATED");
    }
}
~~~

Here **Environment** is used to read from application.properties or command-line arguments per Spring Boot's property source precedence. ApplicationArguments in the method signature is valid though unused for this lab; if you only want command-line options, you can call getOptionValues.

Placing validation inside run instead of the constructor demonstrates failure after Started: beans can be created successfully and ApplicationContext refresh finishes, and only when the runner executes is the invalid region detected.

@Order(10) does not order arbitrary bean constructors or @PostConstruct methods; it applies specifically in the context of sorting runners and other components with Ordered semantics.

### 8.2. StartupAuditRunner.java

File **src/main/java/demo/startup/StartupAuditRunner.java**:

~~~java
package demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class StartupAuditRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RUNNER_AUDIT");
    }
}
~~~

With a valid region, RUNNER_VALIDATED prints followed by RUNNER_AUDIT. If the @Order(10) runner throws an exception, runner execution normally stops at that error and **RUNNER_AUDIT does not appear**.

If a runner submits background tasks, failure does not automatically cancel already-submitted tasks. Design ownership, timeouts, and cleanup for any allocated tasks or connections.


## 9. Custom FailureAnalyzer and Registration

### 9.1. StartupPolicyFailureAnalyzer.java

File **src/main/java/demo/diagnostics/StartupPolicyFailureAnalyzer.java**:

~~~java
package demo.diagnostics;

import demo.startup.StartupPolicyException;
import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalyzer;

public final class StartupPolicyFailureAnalyzer
        implements FailureAnalyzer {

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof StartupPolicyException problem) {
                String description =
                        "Startup policy rejected "
                        + problem.getPropertyName()
                        + "=" + problem.getRejectedValue()
                        + ". Allowed regions: ap-southeast-1, "
                        + "ap-northeast-1.";

                String action =
                        "Set --demo.startup.region=ap-southeast-1 "
                        + "or --demo.startup.region=ap-northeast-1; "
                        + "then restart. Check active profiles "
                        + "and deployment configuration.";

                return new FailureAnalysis(
                        description, action, problem);
            }

            current = current.getCause();
        }

        return null;
    }
}
~~~

**Established technical points:**

1. Spring Boot 3.3's FailureAnalyzer interface has analyze(Throwable) returning FailureAnalysis or null.
2. Constructor FailureAnalysis(String description, String action, Throwable cause) is a real API.
3. Java 17 supports pattern matching instanceof to match StartupPolicyException.
4. The while loop walks the cause chain so it still finds the error wrapped inside SpringApplication's IllegalStateException.
5. Returning null when StartupPolicyException is absent avoids shadowing Boot's built-in analyzers.
6. The analyzer is a public class with a default no-arg constructor, matching factory discovery instantiation.
7. The analyzer does not need @Component/@Bean because it may be invoked when ApplicationContext has not finished refreshing.
8. Descriptions are actionable, yet do not fix the error or set exit status themselves.

If a project has multiple types of startup policies, separate them with an enum/error code or structured exception fields; avoid classifying solely by matching fragile English strings in exception.getMessage().

### 9.2. META-INF/spring.factories

File **src/main/resources/META-INF/spring.factories** must contain exactly:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=demo.diagnostics.StartupPolicyFailureAnalyzer
~~~

The Spring Boot How-to requires registering custom FailureAnalyzers via **spring.factories**. This mechanism lets Boot discover the analyzer when the context does not yet support full component scanning.

Do not replace it with:

- @Component placed on StartupPolicyFailureAnalyzer.
- A @Bean method inside @Configuration.
- A line in application.properties.
- META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports, as that mechanism is for auto-configuration, not custom FailureAnalyzer registration in Boot 3.3.
- A spring.factories file at the project root outside the runtime classpath.

If the class or package name changes, update the fully qualified class name in spring.factories and rebuild so the updated resource is on the classpath.

### 9.3. Why Separate Description and Action?

| Field | Example | Operational Value |
| --- | --- | --- |
| Description | Startup policy rejected demo.startup.region=moon-base | Pinpoints the exact error that occurred |
| Description | Allowed regions: ap-southeast-1, ap-northeast-1 | States the permitted contract |
| Action | Set --demo.startup.region=ap-southeast-1 | Actionable command |
| Action | Check active profiles and deployment configuration | Hints at common misconfiguration sources |
| Cause | StartupPolicyException | Preserves the root Throwable |

Do not use vague messages like "Application error, contact support" when you can name the key and remediation. Never include real secrets in description, action, or Throwable.getMessage().

### 9.4. FailureAnalysisReporter and Logging

Spring Boot uses LoggingFailureAnalysisReporter to print the **APPLICATION FAILED TO START / Description / Action** block. In this lab you do not need to write your own reporter. The analyzer produces **diagnostic data**; the reporter decides how to display it.

Even when the custom report is printed, the JVM/Gradle may still print the raw stack trace to stderr. This does not mean the analyzer was invoked incorrectly; the two reporting channels serve different readers.

## 10. Running Successfully

If the project has a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper but a compatible Gradle is installed:

~~~bash
gradle bootRun
~~~

With default **demo.startup.region=ap-southeast-1**, lines printed by the demo code in order:

~~~text
EVENT_STARTED
RUNNER_VALIDATE=ap-southeast-1
RUNNER_VALIDATED
RUNNER_AUDIT
EVENT_READY
~~~

Gradle, Boot, or JVM logs may interleave; the lines above are the **demo's marker subset**, not all of stdout.

To test the second valid region:

~~~bash
./gradlew bootRun --args="--demo.startup.region=ap-northeast-1"
~~~

Expected markers:

~~~text
EVENT_STARTED
RUNNER_VALIDATE=ap-northeast-1
RUNNER_VALIDATED
RUNNER_AUDIT
EVENT_READY
~~~

Meaning of the markers:

- EVENT_STARTED: SpringApplication passed context.refresh and reached started.
- RUNNER_VALIDATE: first runner started.
- RUNNER_VALIDATED: allowlist check passed.
- RUNNER_AUDIT: second runner actually executed.
- EVENT_READY: all runners completed.

The non-web app does not hold Tomcat open, so it exits naturally after run finishes and no other non-daemon threads remain. Do not add System.exit(0) to the demo, as that could couple test results to process termination behavior.

## 11. Running Startup Failure Caused by Runner

Run:

~~~bash
./gradlew bootRun --args="--demo.startup.region=moon-base"
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun --args="--demo.startup.region=moon-base"
~~~

Markers printed by the demo in order:

~~~text
EVENT_STARTED
RUNNER_VALIDATE=moon-base
EVENT_FAILED
~~~

**Absent** on this failed startup path: RUNNER_VALIDATED, RUNNER_AUDIT, EVENT_READY. The reason is that the @Order(10) runner threw StartupPolicyException, so Boot entered failure handling before invoking the @Order(20) runner.

If spring.factories is packaged and the class is valid, the report block typically contains content equivalent to:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Startup policy rejected demo.startup.region=moon-base.
Allowed regions: ap-southeast-1, ap-northeast-1.

Action:

Set --demo.startup.region=ap-southeast-1
or --demo.startup.region=ap-northeast-1;
then restart. Check active profiles
and deployment configuration.
~~~

**This is an excerpt wrapped for readability**, not fixed full console output. Loggers may wrap lines differently and add ANSI colors, timestamps, stack traces, and Gradle failure notices. QA should check **stable content** in Description/Action and event markers, rather than asserting every console line verbatim.

### What Happens After the Exception?

1. Context refreshed; EVENT_STARTED printed.
2. RegionValidationRunner threw StartupPolicyException.
3. SpringApplication may wrap the error in IllegalStateException with message Failed to execute ApplicationRunner.
4. SpringApplication enters startup failure handling; ApplicationFailedEvent is published to registered listeners, printing EVENT_FAILED.
5. Custom FailureAnalyzer finds StartupPolicyException in the cause chain.
6. LoggingFailureAnalysisReporter outputs Description and Action.
7. SpringApplication.run does not return a successful context; non-web applications typically exit with a non-zero status.

**FailureAnalyzer does not make the exception disappear** and does not produce a specific exit code by itself. If a business exit code is needed, use ExitCodeGenerator or ExitCodeExceptionMapper per your own contract.

### Testing the Executable JAR

~~~bash
./gradlew bootJar
java -jar build/libs/runner-failure-lab-1.0.0.jar --demo.startup.region=moon-base
~~~

To inspect the packaged contents:

~~~bash
jar tf build/libs/runner-failure-lab-1.0.0.jar
~~~

The executable JAR must contain **BOOT-INF/classes/META-INF/spring.factories** and demo/diagnostics/StartupPolicyFailureAnalyzer.class. If the resource is excluded from the build, startup still fails on the runner, but you may only see a generic stack trace without custom Description/Action.

## 12. Hands-On Unit Test

File **src/test/java/demo/diagnostics/StartupPolicyFailureAnalyzerTest.java**:

~~~java
package demo.diagnostics;

import demo.startup.StartupPolicyException;
import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.assertj.core.api.Assertions.assertThat;

class StartupPolicyFailureAnalyzerTest {

    private final StartupPolicyFailureAnalyzer analyzer =
            new StartupPolicyFailureAnalyzer();

    @Test
    void describesWrappedStartupPolicyViolation() {
        StartupPolicyException cause =
                new StartupPolicyException(
                        "demo.startup.region", "moon-base");

        IllegalStateException wrapper =
                new IllegalStateException(
                        "Failed to execute ApplicationRunner", cause);

        FailureAnalysis analysis = analyzer.analyze(wrapper);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .contains("demo.startup.region=moon-base")
                .contains("ap-southeast-1");
        assertThat(analysis.getAction())
                .contains("--demo.startup.region=ap-southeast-1");
        assertThat(analysis.getCause()).isSameAs(cause);
    }

    @Test
    void returnsNullWhenFailureIsNotOurs() {
        FailureAnalysis analysis = analyzer.analyze(
                new IllegalStateException("Unrelated startup failure"));

        assertThat(analysis).isNull();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

These two unit tests verify that the analyzer recognizes **the cause inside a wrapper** and does not claim errors belonging to other modules. JUnit/Gradle output varies by version, so do not assert a single fixed stdout string; only assert that tests pass.

**Unit tests calling the analyzer directly are not enough to prove spring.factories discovery**. Run bootRun or java -jar on the moon-base branch to verify end-to-end failure analysis.

### Integration Test Idea

Use a separate Java process with a timeout, capturing stdout/stderr and exit code:

1. Run with default: marker EVENT_READY and success exit code.
2. Run moon-base: marker EVENT_FAILED, custom Description/Action, no EVENT_READY, non-zero exit code.
3. Run with a test packaging that intentionally omits spring.factories: runner failure still occurs, but without the custom action.
4. Trigger an error unrelated to StartupPolicyException to confirm the custom analyzer returns null.

Do not use ApplicationContextRunner as the **sole** test for ApplicationRunner: ApplicationContextRunner creates/refreshes a context to test configuration and does not necessarily run **SpringApplication.run -> callRunners** like full application startup. Use an end-to-end test that actually runs SpringApplication.



## 13. AbstractFailureAnalyzer Is an Alternative Option

Spring Boot provides **AbstractFailureAnalyzer<T extends Throwable>**, a base class that finds a specific exception in the cause chain before calling analyze(rootFailure, cause). Illustrative pattern:

~~~java
final class AlternativeAnalyzer
        extends AbstractFailureAnalyzer<StartupPolicyException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, StartupPolicyException cause) {
        return new FailureAnalysis(
                "Invalid region: " + cause.getRejectedValue(),
                "Choose ap-southeast-1 or ap-northeast-1.",
                cause);
    }
}
~~~

This is an **illustrative snippet, not a standalone runnable file**: imports, package, StartupPolicyException type, and registration choice are required. Use **one or the other** analyzer for the same exception to avoid inconsistent reporting.

When implementing FailureAnalyzer directly as in the main project, you are responsible for walking the chain or detecting wrappers. When extending AbstractFailureAnalyzer, you can omit the manual while loop. If unable to handle, the base class/implementation should return null so another analyzer can handle it.

## 14. Distinguishing Startup Failure from Runtime Failure

| Error Location | SpringApplication Startup Failure? | FailureAnalyzer Used Automatically? | Additional Approach |
| --- | --- | --- | --- |
| Bean constructor during refresh | Yes | Possibly | Fix bean/config, clean up partial allocations |
| @PostConstruct during refresh | Yes | Possibly | Fix init, timeouts, resources |
| ApplicationRunner before Ready | Yes | Yes, as in lab | Custom type + FailureAnalyzer |
| CommandLineRunner before Ready | Yes | Possibly | Same mechanism |
| ApplicationReadyEvent listener throws exception | Can affect run when synchronous | Depends on failure handling path | Do not put arbitrary mandatory validation in listeners |
| HTTP controller after Ready | Not by default | Not on startup path | @ControllerAdvice, HTTP status |
| @Async task after Ready | Not by default | Not on startup path | Future/error handler/metrics |
| Scheduler after Ready | Not by default | Not on startup path | Scheduler ErrorHandler, retries |
| Kafka/RabbitMQ runtime listener | Not by default | Not on startup path | Container error handler/ack/backoff |

**ApplicationFailedEvent is not an event for every exception**. It represents failure during SpringApplication startup. An error occurring in a request after Ready normally does not stop the entire JVM, does not emit ApplicationFailedEvent, and does not invoke startup FailureAnalyzers.

## 15. Operational Risks and Sound Design

### Runner Fail-Fast or Degraded Mode?

If a policy is mandatory for the application to serve safely, **fail-fast** is more accurate than logging a warning and publishing Ready. However, if a remote service is temporarily unavailable while the app can still serve partially, use readiness degradation, health indicators, circuit breakers, or bounded retries rather than blocking startup indefinitely.

### Do Not Accidentally Use Runners for Non-Idempotent Work

A Pod restarting multiple times can run a runner multiple times. If a runner submits payments, publishes messages, or runs unsafe migrations, side effects can repeat even when FailureAnalyzer reports the error clearly. Use checkpoints, leader election, idempotency, transactions, and outbox patterns per use case.

### Resource Cleanup on Failure

StartupFailure may cause Spring Boot to attempt closing the created ApplicationContext. However, there is no guarantee that every file, socket, or remote resource half-opened in constructors/factories is fully closed. Design explicit try/finally blocks and managed lifecycles. FailureAnalyzer only reports the cause and **does not undo side effects**.

### ExitCodeGenerator Differs from FailureAnalyzer

- **FailureAnalyzer:** operators read Description and Action.
- **ExitCodeGenerator/ExitCodeExceptionMapper:** chooses exit status per application contract.
- **ApplicationFailedEvent:** observes startup failure events.
- **FailureAnalysisReporter:** formats and outputs FailureAnalysis.
- **ReadinessState:** indicates whether the application accepts traffic; not an exception reporter.

These mechanisms can work together, yet must not be treated as interchangeable. An analyzer does not guarantee a particular exit code or handle retries.

### Security of Description/Action

Messages must be actionable without leaking secrets. In the lab, region moon-base is non-sensitive. For credentials, reports should name only the config key/vault source and proper loading method, never printing rejectedValue. Do not dump full production stack traces containing secrets to public logs.

## 16. Symptom-Based Troubleshooting

| Symptom | Suspect | How to Check |
| --- | --- | --- |
| Runner fails yet no custom Action shown | spring.factories wrong path/key | src/main/resources/META-INF/spring.factories and packaged JAR |
| Analyzer unit test passes yet app only prints stack trace | Unit test doesn't verify discovery | Run bootRun moon-base |
| Analyzer always returns null | Custom type not found in getCause | Check wrappers, package, exception type |
| Analyzer class fails to load | Wrong FQCN, no public constructor, or missing dependency | Package/class name and runtime classpath |
| @Component present yet never invoked | Component scan is not reliable registration | spring.factories |
| Only EVENT_STARTED then failed | Failure in runner before Ready | Read RUNNER_VALIDATE and cause |
| No EVENT_FAILED | Listener not registered early enough or failure before event pipeline | app.addListeners before app.run |
| RUNNER_AUDIT runs despite invalid region | Unexpected @Order/config | @Order on classes, active profile, runner beans |
| moon-base does not fail | Overridden by another property or running stale build | Print resolved value from Environment |
| JAR behaves differently from bootRun | Resource/class not packaged or different profile | jar tf, deployment args |
| Lots of stack traces in console | Gradle/JVM printing exception to stderr | Check Description/Action rather than expecting zero stack trace |
| Exit status 0 despite error | Main caught and swallowed exception or wrapper altered status | Avoid silent catch; check OS process status |

### Conditions Report Does Not Replace FailureAnalyzer

Spring Boot can enable a debug conditions report:

~~~bash
./gradlew bootRun --args="--demo.startup.region=moon-base --debug"
~~~

This report helps with auto-configuration, @Conditional, and missing beans, yet **cannot automatically understand the region allowlist policy**. FailureAnalyzer is where this lab's business error is explained.

### Errors in Beans Before Runners

If @PostConstruct or a constructor throws an exception, EVENT_STARTED usually has not appeared on the successful startup path. Do not rush to blame the custom analyzer; it may be a different exception for which the main analyzer returns null by design.

## 17. Self-Test Questions

**1. Does ApplicationRunner run before or after ApplicationStartedEvent?** After Started, before Ready.

**2. If the first runner throws an exception, does the next runner run?** Not on the normal startup path when the exception is not swallowed.

**3. Does ApplicationReadyEvent fire when a runner fails?** Not on the successful startup path.

**4. Why walk getCause?** SpringApplication may wrap the runner's custom exception.

**5. What are the three parts of FailureAnalysis?** Description, Action, Cause.

**6. If an analyzer cannot handle an exception, what should it return?** null, so other analyzers get a chance.

**7. Where is the custom FailureAnalyzer registration file located?** src/main/resources/META-INF/spring.factories.

**8. Can @Component on the analyzer class replace discovery?** No, per Boot 3.3 registration guidance.

**9. Is registering in AutoConfiguration.imports instead of spring.factories valid?** No; the two mechanisms serve different purposes.

**10. Is a passing unit test on analyze() sufficient?** No; a bootRun/java -jar integration test is needed to verify discovery and reporting.

**11. Does FailureAnalyzer change the exit code by itself?** No, exit codes are a separate mechanism.

**12. Does ApplicationFailedEvent fire for every exception after Ready?** No, it belongs to the startup path.

**13. If an exception contains a password, should it be printed in Description?** No; redact secrets.

**14. Does using @PostConstruct instead of a runner make Started fire before validation?** No; @PostConstruct belongs to bean initialization before Started.

**15. When should AbstractFailureAnalyzer be used?** When you want the base class to locate the exception type in the cause chain and reduce boilerplate traversal code.

**16. Why not retry infinitely inside a runner?** It can hang startup, keep the app Not Ready, overload downstreams, and mask the root cause.

## 18. Lab QA Checklist

- [ ] Spring Boot 3.3.13, Java 17+, compatible Gradle.
- [ ] Main @SpringBootApplication resides in package demo to scan subpackages.
- [ ] Both @Order(10) and @Order(20) runners are actually registered.
- [ ] Custom exception stores non-sensitive key name and rejected value.
- [ ] Main registers ApplicationFailedEvent listener before run.
- [ ] StartupEventLog receives Started/Ready and prints markers in the right places.
- [ ] Analyzer implements FailureAnalyzer, walks getCause, returns FailureAnalysis or null.
- [ ] Description states the cause and Action gives concrete remediation steps.
- [ ] spring.factories has exact key, FQCN, and resources path.
- [ ] Unit tests pass for wrapped exceptions and unrelated exceptions.
- [ ] Running default and ap-northeast-1 prints EVENT_READY.
- [ ] Running moon-base prints EVENT_FAILED, custom report, and no EVENT_READY.
- [ ] No RUNNER_AUDIT when validation fails.
- [ ] Packaged JAR contains META-INF/spring.factories under BOOT-INF/classes.
- [ ] Does not assume character-for-character identical stack traces/logs.
- [ ] Does not swallow exceptions and falsely mark the app Ready.
- [ ] Does not log secrets and does not introduce non-idempotent side effects.
- [ ] Distinguishes startup diagnostics, runtime error handling, readiness, and exit status.

## 19. Conclusion

In Spring Boot, **a runner can fail after context refresh and ApplicationStartedEvent have fired, yet before ApplicationReadyEvent**. To turn a runner's business error into an actionable message, throw a **custom exception**, create a **FailureAnalyzer** returning **FailureAnalysis(description, action, cause)**, traverse **the cause chain** because the framework may wrap exceptions, and **register it in META-INF/spring.factories**.

A complete practice lab must demonstrate the success path, the failure path, runner ordering, startup events, analyzer logic, and actual **discovery + reporting**. FailureAnalyzer **only diagnoses startup**; it does not fix errors itself or replace transactions, retries, exit codes, readiness, or runtime/request error handling.

### References

- [Spring Boot 3.3 — SpringApplication and Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot — Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Boot 3.3.13 API — ApplicationRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot 3.3.13 API — FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html)
- [Spring Boot 3.3.13 API — FailureAnalysis](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html)
