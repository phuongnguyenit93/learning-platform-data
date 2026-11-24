# ApplicationFailedEvent in Spring Boot Application Events

## 1. What Is ApplicationFailedEvent?

**ApplicationFailedEvent** is a **Spring Boot application event** published by **SpringApplication** when **application startup** fails due to an exception. Its fully qualified type is **org.springframework.boot.context.event.ApplicationFailedEvent**, extending **SpringApplicationEvent**.

The main purpose of the event is to allow an early-registered component to **observe startup errors**, record diagnostic information, or emit a brief failure signal before the process exits or the startup error is propagated to the caller. Examples: ApplicationContext initialization encounters a bean error, configuration binding fails, the web server port cannot be bound, or a **CommandLineRunner** throws an exception while SpringApplication.run(...) is still performing startup.

Key points to remember:

- **The event is tied to startup orchestrated by SpringApplication**. It is not a general event for every exception occurring at any time in the JVM.
- Listeners can read the cause via **event.getException()**.
- **event.getApplicationContext() may return null** if the error happens before the context is created; when non-null, the context may also **not have refreshed successfully or may be closing**.
- Listeners must be **registered early**, because Spring Boot can fail before beans and **@EventListener** methods are instantiated.
- The event helps observe errors; **it does not automatically restart the application, roll back all side effects, or guarantee durable alert delivery**.

A production system typically already has Spring Boot startup logging and error output. ApplicationFailedEvent is useful when you need a **structured signal** for monitoring, error classification, or a simple cleanup step outside the regular bean mechanism.

## 2. At Which Startup Stage Does ApplicationFailedEvent Appear?

**SpringApplication.run(...)** executes these steps: creating and preparing the environment, creating the ApplicationContext, loading bean definitions, refreshing the context, running runners, and finalizing application readiness. If an exception prevents that process from completing normally, Spring Boot can publish **ApplicationFailedEvent** along the startup failure handling path.

A typical successful startup sequence:

~~~text
SpringApplication.run(...)
    |
    v
ApplicationStartingEvent
    |
    v
ApplicationEnvironmentPreparedEvent
    |
    v
ApplicationContextInitializedEvent
    |
    v
ApplicationPreparedEvent
    |
    v
Context refresh
    |
    v
ApplicationStartedEvent
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
ApplicationReadyEvent
    |
    v
ReadinessState.ACCEPTING_TRAFFIC
~~~

If an error occurs in the relevant startup steps, the failure branch replaces normal completion:

~~~text
SpringApplication.run(...)
    |
    +-- error preparing environment/context
    |       or refreshing beans/server
    |       or invoking runners
    |
    v
SpringApplication handles startup failure
    |
    +-- notify registered listeners with ApplicationFailedEvent
    +-- record/analyze error and clean up context as needed
    +-- rethrow error to caller / startup ends in failure
~~~

**Do not interpret the event list as a promise that ApplicationFailedEvent always happens before ApplicationStartedEvent.** If a **CommandLineRunner** or **ApplicationRunner** throws an error, the context has already refreshed and **ApplicationStartedEvent** may have been published earlier; **ApplicationReadyEvent** has not arrived yet. Conversely, if an error occurs very early, the ApplicationContext does not exist yet.

If the application is already ready to serve and then encounters an exception during an HTTP request, scheduled job, or consumer, **ApplicationFailedEvent is normally not automatically published again by Spring Boot**. Post-startup runtime errors belong to separate exception handling, logging, metrics, health/availability, and monitoring mechanisms.

## 3. Data Readable by the Listener

Important APIs of **ApplicationFailedEvent**:

| API | Meaning | Safe Usage |
| --- | --- | --- |
| **getException()** | **Throwable** causing startup failure | Log exception class, message, controlled cause chain/stack trace; avoid exposing sensitive info |
| **getApplicationContext()** | **ConfigurableApplicationContext** being created, or **null** | Always check for null; do not assume the context has refreshed |
| **getSpringApplication()** | **SpringApplication** associated with the run | Identify startup source in infrastructure tooling if genuinely needed |
| **getArgs()** | Command-line arguments array passed at run | May contain tokens/passwords; do not log verbatim by default |
| **getTimestamp()** | Event creation timestamp from ApplicationEvent | Useful for timestamping, but does not replace standard tracing/metrics |

Example extracting the error with a null check:

~~~java
@Override
public void onApplicationEvent(ApplicationFailedEvent event) {
    Throwable error = event.getException();
    ConfigurableApplicationContext context = event.getApplicationContext();

    String contextId = context != null ? context.getId() : "<not-created>";
    System.err.println("Startup failed in " + contextId
            + " with " + error.getClass().getSimpleName());
}
~~~

This is an **illustrative method** inside a class implementing **ApplicationListener<ApplicationFailedEvent>**, with appropriate Spring imports. Do not arbitrarily call **context.getBean(...)** from a failure listener: the BeanFactory may only be partially initialized or already entering cleanup.

When analyzing the root cause, the outer wrapper exception may be **BeanCreationException**, **UnsatisfiedDependencyException**, a port error, or a runner error. You can inspect nested **getCause()** levels, but do not rely solely on **getMessage()** for classification since messages and wrappers can change across versions/code paths.

## 4. Registering the Listener Early Enough: The Most Important Point

### 4.1. Registering via SpringApplication.addListeners(...)

The clearest approach is creating **SpringApplication** and adding the listener **before calling run(...)**:

~~~java
SpringApplication application = new SpringApplication(MyBootApplication.class);
application.addListeners(new StartupFailureListener());
application.run(args);
~~~

This is an **illustrative snippet**; corresponding classes are required. **StartupFailureListener** should implement **ApplicationListener<ApplicationFailedEvent>** so Spring identifies the event type.

Advantages:

- The listener is available before context creation and bean refresh steps.
- Can observe failures even if **@Component**/**@Bean** instances are never created.
- Does not force the listener to rely on dependency injection inside a failing context.
- Each SpringApplication instance has an explicit listener list.

Some libraries may use **SpringApplicationBuilder.listeners(...)**, or register via framework startup extension mechanisms. What must be preserved is that **the listener is added before run**.

### 4.2. Registering via META-INF/spring.factories

When you want an infrastructure listener automatically applied to applications using a library, Spring Boot supports configuring **META-INF/spring.factories**. Example file contents:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.startup.StartupFailureListener
~~~

**StartupFailureListener** in the library must be an appropriately instantiable class implementing **ApplicationListener<ApplicationFailedEvent>**. The lines above are an illustrative configuration assuming the class exists; not a complete project.

For a small application, **addListeners(...)** is usually easier to observe. For a starter/library wanting to catch very early errors regardless of how users invoke SpringApplication.run(...), **spring.factories** can be suitable. Do not confuse this listener registration mechanism with automatic configuration registration via newer auto-configuration imports.

### 4.3. Why Using Only @EventListener Inside @Component Is Unreliable for Startup Failures?

The following example is valid as a listener method once the bean exists:

~~~java
@Component
class LateFailureObserver {
    @EventListener
    public void on(ApplicationFailedEvent event) {
        // Only has a chance to run if the listener bean was registered in time.
    }
}
~~~

However, **this is not a guaranteed solution for catching all startup errors**. If failure happens before Spring creates the context, loads bean definitions, or finishes registering event listener adapters, the bean cannot receive the event yet. Even when the context once existed, the listener bean may be affected by refresh/cleanup errors.

**Rule:** a listener monitoring startup failures should be registered at the **SpringApplication-level** before **run(...)**. Regular **@EventListener** beans are better suited for events after the context has been successfully established.

## 5. Standalone Runnable Java 17+ Example: Intentionally Failing Startup

The following example uses **Spring Boot 3.5.8** and **Java 17+**. It creates a non-web **SpringApplication**, attaches a listener before **run(...)**, and adds an **ApplicationContextInitializer** that intentionally throws an exception. Failing this way keeps the example deterministic without needing a database or web server.

Structure:

~~~text
startup-failure-demo/
  build.gradle
  src/main/java/demo/FailedStartupDemo.java
~~~

Contents of **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter:3.5.8'
}

application {
    mainClass = 'demo.FailedStartupDemo'
}
~~~

Contents of **src/main/java/demo/FailedStartupDemo.java**:

~~~java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class FailedStartupDemo {

    static final class StartupFailureListener
            implements ApplicationListener<ApplicationFailedEvent> {

        @Override
        public void onApplicationEvent(ApplicationFailedEvent event) {
            Throwable error = event.getException();
            System.out.println("event: " + error.getClass().getSimpleName());
            System.out.println("message: " + error.getMessage());
            System.out.println("context-created: "
                    + (event.getApplicationContext() != null));
        }
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(FailedStartupDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Register listener BEFORE running SpringApplication.
        application.addListeners(new StartupFailureListener());

        // Intentionally fail after the context is created,
        // but before the context finishes refreshing successfully.
        application.addInitializers(context -> {
            throw new IllegalStateException("demo-bootstrap-failed");
        });

        try {
            application.run(args);
        } catch (IllegalStateException ex) {
            System.out.println("caller: " + ex.getMessage());
        }
    }
}
~~~

From the **startup-failure-demo** directory, with JDK 17+ and Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Lines printed by the program itself**, in order (Spring Boot may also log additional errors depending on logging configuration):

~~~text
event: IllegalStateException
message: demo-bootstrap-failed
context-created: true
caller: demo-bootstrap-failed
~~~

Interpretation:

1. **StartupFailureListener** is added to SpringApplication before **run(...)**.
2. SpringApplication creates the context; when invoking **ApplicationContextInitializer**, the initializer throws **IllegalStateException** with message **demo-bootstrap-failed**.
3. SpringApplication enters the startup failure handling path and publishes **ApplicationFailedEvent**; the listener reads **getException()** and sees a **non-null** context in this case because the context had already been created.
4. The original error continues propagating to the caller. The **catch** block in **main(...)** intentionally catches the error to illustrate that the event **does not swallow** the exception; the demo program can exit normally because main caught the exception.
5. In a real application without a similar catch, **run(...)** does not return a ready context after an error. Do not turn a catch block into behavior claiming "startup succeeded."

Important QA point: this example triggers the error in an **initializer**, so with an early-registered listener, **context-present** is true along this specific path. When failure happens earlier than context creation, **getApplicationContext()** can be null. When failure occurs in a runner, exception wrappers and context data can differ; do not hardcode this output to predict all Boot errors.

**Using System.out for production alerts is discouraged.** This is a lifecycle teaching tool. In production, use an early-initialized logger/sink or deployment monitoring mechanism, accompanied by timeouts and error handling within the listener itself.

## 6. Null vs. Non-Null getApplicationContext() Scenarios

| Where Failure Occurs | Does Context Exist Yet? | How to React |
| --- | --- | --- |
| At very early steps before context creation | **May be null** | Rely only on the exception and independent logging infrastructure |
| During context preparation/refresh | Usually created but **not ready** | Can retrieve ID if safe; avoid looking up additional beans |
| When creating beans/datasource or starting web server | Context may exist in a failed state | Use exception/cause chain to find root cause; do not continue using the context |
| When running ApplicationRunner/CommandLineRunner | Context has usually refreshed | Error still belongs to startup; Boot handles failure and cleanup, not "ready" |
| During HTTP requests after app is ready | Not the normal startup failure path | Use runtime error handling, metrics, tracing, and health/availability |

**Nullable does not mean each error type always produces one fixed value.** Many startup steps contain auxiliary processing and extension points; treat the context as potentially null and always check state before accessing it.

## 7. Relationship to ApplicationStartedEvent and ApplicationReadyEvent

A common misconception: seeing **ApplicationStartedEvent** means startup is guaranteed to succeed. That is false.

- **ApplicationStartedEvent** is published **after context refresh**, but **before** runners execute.
- **ApplicationReadyEvent** is published later, **after ApplicationRunner/CommandLineRunner** when normal startup has completed.
- **ApplicationFailedEvent** signals a **failed startup** branch, including runner failures, so it can arrive **after ApplicationStartedEvent** in some scenarios.
- **AvailabilityChangeEvent** and readiness/liveness reflect the application's serving status; they serve a different role from the startup failure event.

Example:

~~~text
context refresh succeeds
    |
    v
ApplicationStartedEvent
    |
    v
CommandLineRunner runs
    |
    +--> throws IllegalStateException
              |
              v
        ApplicationFailedEvent
              |
              v
      no ApplicationReadyEvent
~~~

If you need to mark "the application can accept traffic," do not rely solely on the context being created or **ApplicationStartedEvent**. Observe the platform's official readiness/health and startup failure signals.

## 8. Distinguishing ApplicationFailedEvent from Runtime Errors

**ApplicationFailedEvent** is an observation of **SpringApplication.run(...)**. It is not automatically published for every exception thrown from:

- **@RestController** when the application is already serving requests.
- **@Scheduled** tasks running after the application is ready.
- **@Async** methods reporting exceptions on an executor.
- Kafka/RabbitMQ/JMS listeners consuming messages after startup.
- An application-managed thread encountering an error after SpringApplication.run has completed.

For runtime errors, use layer-appropriate mechanisms: **@ControllerAdvice**, messaging listener error handlers, **AsyncUncaughtExceptionHandler**, retry/dead-letter, logging, tracing, metrics, and health/availability. Attempting to manually publish **new ApplicationFailedEvent(...)** to represent a runtime error corrupts Spring Boot's lifecycle semantics.

**Exceptions occurring inside startup callbacks** such as **ApplicationRunner** or **CommandLineRunner** are still startup failures if they cause **SpringApplication.run(...)** to fail.

## 9. How Do ApplicationFailedEvent and FailureAnalyzer Differ?

Spring Boot provides **FailureAnalyzer** and **FailureAnalysisReporter** mechanisms to translate certain startup exception types into understandable messages like "port already in use" along with suggested fixes.

| Mechanism | Primary Purpose | When to Use? |
| --- | --- | --- |
| **ApplicationFailedEvent listener** | Observe startup failure events and exceptions, integrate telemetry/monitoring | When you need a general hook for startup failures |
| **FailureAnalyzer** | Identify specific exception types, produce clear **description** and **action** | When building a library/starter where users should see remediation guidance |
| **FailureAnalysisReporter** | Present error analysis results | When customizing report output formatting |
| **Logging/exception propagation** | Preserve stack traces and failed startup state | Must be preserved even when custom listeners exist |

Example: If a library configuration is missing a property, **FailureAnalyzer** is usually appropriate to state "property X must be configured" and how to fix it. If you want to emit a **startup.failure** metric tagged with deployment/version, an early-registered listener fits well.

Do not let custom listeners obscure the original error message. Listeners should run quickly, avoid throwing extra exceptions unless there is a clear contract, and avoid depending on beans that may have failed.

## 10. Logging, Security, and Reliability Policies

### 10.1. Log Only Necessary Information

Information that should be recorded:

- Timestamp and deployment environment (from independent logging config, if available).
- Exception class/type and inspected root cause.
- Error codes/categories with bounded label cardinality.
- Build version, instance ID, and appropriate correlation ID.

Avoid logging **all of event.getArgs()** or values of environment properties because command-line arguments may contain passwords, tokens, URLs with credentials, or user data. Stack traces can also contain paths or internal data; apply appropriate redaction policies.

### 10.2. Do Not Arbitrarily Call BeanFactory in a Failing Context

At startup failure, the bean factory may be half-initialized or shutting down. A listener that exists only to log should not call **getBean(...)**, ask a transaction manager to open a new transaction, or publish events depending on the bean that just failed.

If alerts must be emitted, use a dependency independent of ApplicationContext; set short timeouts, avoid infinite retries, and account for the monitoring sink itself failing.

### 10.3. A Listener Cannot Guarantee Alerts Always Arrive

Startup can be interrupted by **SIGKILL**, native crash, very early OOM, or system termination before SpringApplication publishes the event. Even if the listener runs, the application may shut down before an async task finishes sending data.

For SLOs and operations, combine:

- Process/container exit status.
- Startup logs and stderr from the runtime.
- Orchestrator readiness/health probes and restart policies.
- Startup failure metrics/alerts collected by the monitoring platform.
- The listener as an additional signal, not the single source of truth.

### 10.4. Listeners Can Also Fail

If a listener throws an exception while handling an **ApplicationFailedEvent**, Spring Boot is still on the failure branch. Secondary errors can obscure diagnostic information; therefore write simple listeners, catch predictable errors, and preserve the primary exception.

Do not use a listener to decide to "continue startup despite errors" once **SpringApplication.run(...)** has failed. That is a concern of startup mechanics, application configuration, and recovery strategy, not an event listener's decision.

## 11. Registration Options and Limitations

| Option | Available Before Context Creation? | Advantages | Limitations |
| --- | --- | --- | --- |
| **application.addListeners(new FailureListener())** before **run** | Yes | Explicit at entry point, bean-independent | Requires control of entry point |
| **SpringApplicationBuilder.listeners(...)** | Yes if configured before **run** | Suits builders or context hierarchies | Must know exactly which builder owns the listener |
| **META-INF/spring.factories** with **ApplicationListener** key | Loaded early by framework in normal bootstrap | Suits shared libraries/starters | Must manage classpath and avoid duplicate registration |
| **@Bean / @Component + @EventListener** | Cannot be guaranteed | Good for events after context is ready | May not exist when startup fails |
| **@Async @EventListener** | Unguaranteed and carries shutdown risks | Usable for other non-critical work | Unsuitable as a reliable startup failure hook |

In a context hierarchy, an event published from a child can propagate to the parent, risking duplicate handling. When multiple SpringApplications exist, distinguish sources via **event.getSpringApplication()** or a verified context; do not create a global variable recording "already failed" and skip all subsequent distinct runs.

## 12. Valuable Test Scenarios

When testing ApplicationFailedEvent, prefer **using a real SpringApplication** rather than only calling **onApplicationEvent(...)** directly:

1. **Failure in ApplicationContextInitializer:** like the section 5 example. Register listener before run; confirm listener is called, exception matches, and context may exist yet remain unrefreshed.
2. **Very early failure:** trigger an error during environment/context preparation via a controlled extension point; confirm code always handles **getApplicationContext() == null** safely when that extension point precedes context creation.
3. **Bean creation failure:** a bean throws an exception during initialization; confirm a startup-registered listener still receives the failure and does not try to call the failing bean.
4. **CommandLineRunner failure:** runner intentionally throws; confirm **ApplicationStartedEvent** may have been received, followed by failure, while **ApplicationReadyEvent** is not published on the success path.
5. **Successful startup:** failure listener is not called; application can publish **ApplicationReadyEvent** along the normal flow.
6. **Post-startup request error:** runtime exceptions do not automatically create **ApplicationFailedEvent**.
7. **Failure inside the listener:** simulate a failing log/metric sink; confirm secondary errors do not hide the original startup cause.
8. **Sensitive data:** run with simulated token args; confirm the listener does not print raw args verbatim.
9. **Repeated startups in tests:** each SpringApplication has the appropriate listener without unwanted hook duplication.

For integration tests, you can use **SpringApplication** with **WebApplicationType.NONE** to avoid binding ports and reduce environmental variance. For specific failures, assert on the **exception chain** rather than comparing entire logs or messages from an implementation that newer versions might change.

If you want to unit test error-classification logic, construct an **ApplicationFailedEvent** and invoke the listener directly; that **does not replace** integration tests verifying the event is actually published by Spring Boot on startup failure.

## 13. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Declaring only **@EventListener** in a regular bean | Misses errors occurring before the bean is created | Register **ApplicationListener<ApplicationFailedEvent>** before run |
| Assuming **getApplicationContext()** is always non-null | NullPointerException right while recording the error | Check for null before any access |
| Calling beans/repositories when context refresh failed | Causes new errors or depends on invalid resources | Keep listener dependencies minimal; use independent logging |
| Treating ApplicationFailedEvent as a runtime exception handler | Misses post-startup request/job errors | Use proper runtime-layer handlers/telemetry |
| Assuming ApplicationStartedEvent guarantees ready | Runners can still fail | Use ApplicationReadyEvent/readiness appropriately |
| Offloading mandatory alerts to **@Async** | JVM may exit before the task runs | Use independent output or platform-collected telemetry |
| Manually publishing ApplicationFailedEvent for any error | Corrupts startup lifecycle semantics | Reserve event for startup; handle runtime errors separately |
| Swallowing startup exceptions in the listener | Caller does not receive proper failure state | Preserve failure propagation; listener only observes |
| Logging all args/environment | Leaks sensitive information | Redact and allowlist log fields |
| Not distinguishing multiple contexts/applications | Duplicate alerts or metrics | Attach identity and control registration |
| Using listener to immediately retry the entire app | Hard-to-control startup failure loop | Put restart/backoff policies in the orchestration layer |

## 14. Checklist for Designing a Failure Listener

Before writing the listener, answer:

- **Is it registered before SpringApplication.run(...)?**
- **Does it handle both null context and unrefreshed context cases?**
- **Does it read only safe exception/metadata without depending on failing beans?**
- **Does it distinguish startup failures from runtime failures?**
- **Does it avoid logging tokens, passwords, and full command-line args?**
- **Does it have timeouts, fallback logging, and avoid stalling failed startups for too long?**
- **Does the system also have exit codes/probes/logs to detect errors when the event never fires?**
- **Have initializer failure, bean failure, runner failure, and successful startup all been tested?**

**Key takeaway:** **ApplicationFailedEvent** is the signal Spring Boot emits when **SpringApplication cannot complete startup**. Register the listener **before run**, read **getException()**, null-check **getApplicationContext()**, record diagnostic data safely, and let the failure continue through Spring Boot's normal error-handling path.

### Official Documentation

- Spring Boot 3.5 Reference, *SpringApplication — Application Events and Listeners*: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 Javadoc, *ApplicationFailedEvent*: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html
- Spring Boot 3.5 Javadoc, *SpringApplication*: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot Reference, *Application Availability*: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability
- Spring Boot 3.5 Reference, *Startup Failure and FailureAnalyzer*: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.startup-failure
