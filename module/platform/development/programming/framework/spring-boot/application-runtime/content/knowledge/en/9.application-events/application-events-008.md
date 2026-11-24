# ApplicationStartedEvent: Event After Context Refresh, Before Calling Runners

## 1. Understanding the Timing of ApplicationStartedEvent

**ApplicationStartedEvent** is a lifecycle event emitted by **Spring Boot** during **SpringApplication.run(...)**. It indicates that **the ApplicationContext has refreshed successfully**, yet **no ApplicationRunner or CommandLineRunner has been invoked by SpringApplication yet** during the runner phase of that startup.

This is a critical boundary:

- **Context refreshed:** Spring has completed refreshing the ApplicationContext; normal non-lazy singletons have been instantiated and their bean initialization callbacks have executed.
- **Runners have not run yet:** all cache preloading, dependency verification, data initialization, or startup validation implemented in ApplicationRunner/CommandLineRunner still lie ahead.
- **Cannot conclude ready yet:** emitting ApplicationStartedEvent **does not mean** the service has finished all startup tasks and is ready to accept requests.
- **Does not mean every bean has been created:** lazy beans may still be uninitialized. Asynchronous activities, background tasks, or external connections are also not guaranteed to have finished simply because the context refreshed.

This event is designed to **observe the milestone where the context has begun operating**, measure startup duration up to the started milestone, emit lightweight telemetry, or run hooks that require a refreshed context. If mandatory business work must finish **before the application is ready**, Spring Boot recommends using a runner rather than placing heavy work in a listener.

**Rule of thumb:** *ApplicationStartedEvent = context refresh finished; runners not called yet. ApplicationReadyEvent = runners completed successfully; about to announce readiness.*

## 2. Where Does ApplicationStartedEvent Sit in the Startup Sequence?

In a successful Spring Boot startup, the main event order is:

| Order | Event/milestone | Meaning |
| --- | --- | --- |
| 1 | ApplicationStartingEvent | Start of SpringApplication.run, before most bootstrap work |
| 2 | ApplicationEnvironmentPreparedEvent | Environment prepared; context not created yet |
| 3 | ApplicationContextInitializedEvent | Context created and ApplicationContextInitializers have run |
| 4 | ApplicationPreparedEvent | Bean definitions loaded; about to refresh |
| 5 | Refresh ApplicationContext | Spring instantiates beans, resolves dependencies, lifecycles, and appropriate infrastructure |
| 6 | **ApplicationStartedEvent** | **Refresh succeeded; runners not called yet** |
| 7 | AvailabilityChangeEvent: LivenessState.CORRECT | Spring Boot announces the application is considered live |
| 8 | ApplicationRunner and CommandLineRunner | Execute startup tasks registered as runner beans |
| 9 | ApplicationReadyEvent | Runners completed on the success branch |
| 10 | AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC | Spring Boot announces the instance can accept traffic |
| 11 | SpringApplication.run(...) returns | Caller receives the ConfigurableApplicationContext |

Diagram:

~~~text
ApplicationStartingEvent
        |
ApplicationEnvironmentPreparedEvent
        |
ApplicationContextInitializedEvent
        |
ApplicationPreparedEvent
        |
  refresh ApplicationContext
        |
        v
APPLICATION_STARTED_EVENT
        |
LivenessState.CORRECT
        |
ApplicationRunner / CommandLineRunner
        |
APPLICATION_READY_EVENT
        |
ReadinessState.ACCEPTING_TRAFFIC
        |
SpringApplication.run(...) returns
~~~

The diagram is simplified to focus on the started/runner/ready milestones. **ContextRefreshedEvent** and **WebServerInitializedEvent** can occur during refresh, before ApplicationStartedEvent; exact ordering of some internal operations depends on context type and web stack.

**Unchangeable point:** ApplicationStartedEvent fires after refresh and before calling runners. Do not use @Order to move ApplicationReadyEvent before runners or move runners before ApplicationStartedEvent. That is SpringApplication's lifecycle order, not arbitrary bean ordering.

## 3. Comparing ApplicationStartedEvent with Neighboring Milestones

| Milestone | Context refreshed? | Runners executed? | Practical meaning |
| --- | --- | --- | --- |
| @PostConstruct on non-lazy singleton | Not necessarily; usually inside refresh | No | A bean has just been injected and is initializing |
| ContextRefreshedEvent | Yes | No in normal startup flow | Framework notifies that context has refreshed |
| **ApplicationStartedEvent** | **Yes** | **No** | **Spring Boot started milestone** |
| ApplicationRunner/CommandLineRunner | Yes | Currently executing | Application-level tasks that can use context services |
| ApplicationReadyEvent | Yes | Completed on the success branch | SpringApplication ready milestone |
| ReadinessState.ACCEPTING_TRAFFIC | Yes | Completed on the success branch | Spring Boot state serving readiness/health |

**ContextRefreshedEvent** is a Spring Framework event. **ApplicationStartedEvent** is an additional Spring Boot event occurring at the milestone coordinated by SpringApplication after refresh. A single run can have multiple contexts, parent/child hierarchies, or additional refreshes; therefore do not treat event reception count as JVM-wide startup count without checking which context emitted it.

**ApplicationStartedEvent is not synonymous with ApplicationReadyEvent.** For example, the web server has already bound its port and a bean receives ApplicationStartedEvent, yet a runner is still preloading a cache. If a load balancer routes traffic as soon as the TCP port opens without checking readiness, requests can arrive before required data is ready.

## 4. Information Available in ApplicationStartedEvent

In Spring Boot 3.x, the class:

~~~java
org.springframework.boot.context.event.ApplicationStartedEvent
~~~

extends **SpringApplicationEvent**. Useful APIs:

- **event.getApplicationContext()** returns the ConfigurableApplicationContext tied to the startup run. At this milestone the context has refreshed; however, runners have not run yet.
- **event.getTimeTaken()** returns a **Duration** measuring how long SpringApplication took to reach the started milestone, or **null** if unavailable. Check for null when logging.
- **event.getSpringApplication()** and **event.getArgs()** are inherited from SpringApplicationEvent; they reveal the associated SpringApplication and raw arguments.
- **event.getTimestamp()** is Spring's event timestamp; it is not a metric specifically measuring runner duration.

Bean listener example:

~~~java
@Component
class StartedLogger {
    @EventListener
    void whenStarted(ApplicationStartedEvent event) {
        Duration duration = event.getTimeTaken();
        System.out.println("Context refreshed");
        if (duration != null) {
            System.out.println("Startup so far (ms): " + duration.toMillis());
        }
    }
}
~~~

This is an **illustrative snippet**, requiring imports for **java.time.Duration**, **org.springframework.stereotype.Component**, **org.springframework.context.event.EventListener**, **org.springframework.boot.context.event.ApplicationStartedEvent**, and placement inside a Spring Boot project. Do not compare a fixed Duration across different machines, as it varies by environment.

**Important:** timing at ApplicationStartedEvent **does not yet include runner work**. To measure overall startup completion, look at ApplicationReadyEvent and observe end-to-end duration; to measure runner tasks separately, use dedicated Timers/metrics around runners instead of inferring from started duration.

## 5. Registering a Listener to Receive ApplicationStartedEvent

### 5.1. Using @EventListener on a Spring Bean

Because ApplicationStartedEvent occurs **after refresh**, listener beans have generally already been discovered and registered by Spring. This is the cleanest option when the code belongs to the application itself:

~~~java
@Component
class StartupObserver {

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("ApplicationStartedEvent received");
    }
}
~~~

If the method takes an ApplicationStartedEvent parameter, you can write **@EventListener** without specifying the class; Spring infers the event type from the parameter.

Things to keep in mind:

- The class must be component-scanned or properly registered as a bean.
- Import **org.springframework.context.event.EventListener** and **org.springframework.boot.context.event.ApplicationStartedEvent**.
- If writing a method with an event parameter, you can access ApplicationContext/Duration/args.
- Listeners run via the event multicaster. Under default settings, listener invocation is **synchronous** on the publishing thread; avoid placing long network operations or unbounded tasks in the handler.

### 5.2. Registering Early via SpringApplication.addListeners(...)

An application can register **ApplicationListener<ApplicationStartedEvent>** directly on SpringApplication:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationStartedEvent>) event ->
        System.out.println("started"));
app.run(args);
~~~

This is an illustrative snippet placed in main, with **MyApplication** standing in for the actual configuration class. Import ApplicationListener and ApplicationStartedEvent appropriately. This approach is useful for infrastructure libraries or when registering listeners before startup. An **ApplicationListener** can also be registered via **META-INF/spring.factories** under the **org.springframework.context.ApplicationListener** key if a library must auto-load from the classpath.

**Do not confuse ApplicationListener with SpringApplicationRunListener:** SpringApplicationRunListener is a low-level SPI with multiple callbacks starting very early and registered under its own key; ApplicationStartedEvent here is an event handled by Spring's event listener system. For regular business tasks, @EventListener or a runner is easier to maintain.

### 5.3. Early Events Cannot Rely on Bean Listeners

**ApplicationStartingEvent** and **ApplicationEnvironmentPreparedEvent** occur before ApplicationContext beans are ready; listening to those early milestones requires pre-registering listeners via addListeners, SpringApplicationBuilder, or spring.factories. In contrast, **ApplicationStartedEvent is emitted after refresh**, so an **@EventListener bean** works well for this milestone.

## 6. Complete Java 17+/Spring Boot 3.x Example

The following example intentionally combines **@PostConstruct**, **ApplicationStartedEvent**, **ApplicationRunner**, **CommandLineRunner**, and **ApplicationReadyEvent** to show which milestone comes before which. A failure branch is included to prove ready does not appear if a runner fails.

### 6.1. Project Structure

Create a Gradle Spring Boot 3.3.x, Java 17 project with these files:

~~~text
started-event-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          StartedEventDemo.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'started-event-demo'
~~~

File **build.gradle**:

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
}
~~~

The example uses Gradle compatible with Spring Boot 3.3 and JDK 17+. If the project includes a wrapper, use the wrapper; otherwise, a compatible Gradle installation is needed to run **gradle bootRun**. Dependencies/plugins must be available in cache or downloadable from configured repositories.

### 6.2. Complete Java Source

File **src/main/java/demo/StartedEventDemo.java**:

~~~java
package demo;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class StartedEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartedEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_AFTER_RUN");
        }
    }
}

@Component
class StartupState {
    private boolean started;
    private boolean workDone;

    @PostConstruct
    void initialize() {
        System.out.println("BEAN_INIT");
    }

    void markStarted() {
        started = true;
    }

    boolean isStarted() {
        return started;
    }

    void markWorkDone() {
        workDone = true;
    }

    boolean isWorkDone() {
        return workDone;
    }
}

@Component
class LifecycleObserver {
    private final StartupState state;

    LifecycleObserver(StartupState state) {
        this.state = state;
    }

    @EventListener
    public void afterContextRefresh(ApplicationStartedEvent event) {
        if (!event.getApplicationContext().isActive()) {
            throw new IllegalStateException("Context must be active");
        }
        state.markStarted();
        System.out.println("EVENT_STARTED");
    }

    @EventListener
    public void afterRunners(ApplicationReadyEvent event) {
        if (!state.isWorkDone()) {
            throw new IllegalStateException("Startup work must be completed");
        }
        System.out.println("EVENT_READY");
    }
}

@Component
@Order(10)
class WarmupRunner implements ApplicationRunner {
    private final StartupState state;

    WarmupRunner(StartupState state) {
        this.state = state;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!state.isStarted()) {
            throw new IllegalStateException("Started event not observed");
        }

        System.out.println("RUNNER_APPLICATION");

        if (args.containsOption("fail-runner")) {
            throw new IllegalStateException("Demo startup failure");
        }

        state.markWorkDone();
    }
}

@Component
@Order(20)
class FinalRunner implements CommandLineRunner {
    private final StartupState state;

    FinalRunner(StartupState state) {
        this.state = state;
    }

    @Override
    public void run(String... args) {
        if (!state.isWorkDone()) {
            throw new IllegalStateException("Warmup not complete");
        }
        System.out.println("RUNNER_COMMAND_LINE");
    }
}
~~~

**Guaranteed behaviors:**

1. **StartupState** is a standard non-lazy singleton; @PostConstruct prints **BEAN_INIT** when the bean is created during refresh.
2. **LifecycleObserver** receives **ApplicationStartedEvent**, verifies the context is active, sets **started=true**, and prints **EVENT_STARTED**.
3. **WarmupRunner** must see the started flag before working; if the listener had not been called in order, the runner would throw an exception.
4. **@Order(10)** and **@Order(20)** order the two runners; ApplicationRunner and CommandLineRunner participate in the same startup runners phase.
5. **LifecycleObserver** receives **ApplicationReadyEvent** after both runners finish, checks workDone, and prints **EVENT_READY**.
6. Once **app.run(args)** returns successfully, main prints **MAIN_AFTER_RUN**; the try-with-resources block then closes the context.

### 6.3. Run and Observe stdout

With the project's Gradle wrapper, run:

~~~bash
./gradlew bootRun
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

The lines **printed by the example Java source itself**, in order, are:

~~~text
BEAN_INIT
EVENT_STARTED
RUNNER_APPLICATION
RUNNER_COMMAND_LINE
EVENT_READY
MAIN_AFTER_RUN
~~~

Spring Boot and Gradle may print additional logs depending on configuration; this block does not claim total stdout has only six lines. The key point is that **EVENT_STARTED appears before both RUNNER lines**, whereas **EVENT_READY appears after both RUNNER lines**.

**Why is sleep or Thread.sleep not needed for ordering?** Because that is SpringApplication's lifecycle contract. Only after ApplicationStartedEvent is emitted and default synchronous listeners finish handling it does SpringApplication proceed to the runner phase. Execution time of each step may vary, but milestone sequence does not depend on machine speed.

### 6.4. Testing the Runner Failure Branch

Run:

~~~bash
./gradlew bootRun --args="--fail-runner"
~~~

This time, the lines printed by the source before the exception is thrown are:

~~~text
BEAN_INIT
EVENT_STARTED
RUNNER_APPLICATION
~~~

Then WarmupRunner throws **IllegalStateException("Demo startup failure")**. **RUNNER_COMMAND_LINE**, **EVENT_READY**, and **MAIN_AFTER_RUN** do not appear on the success startup path. Spring Boot handles the startup failure; Gradle may print a stack trace and report that bootRun failed.

This proves that a successful **started** milestone **does not guarantee** the entire startup succeeds. It also shows that **ApplicationReadyEvent** carries a different meaning: runners have returned successfully.

## 7. How Does This Event Relate to Liveness and Readiness?

Spring Boot provides **ApplicationAvailability** states for operations and probes.

- **LivenessState.CORRECT:** Spring Boot publishes liveness state right after ApplicationStartedEvent on the normal startup path. It reflects that the context refreshed successfully and the application is considered live.
- **ReadinessState.ACCEPTING_TRAFFIC:** published after ApplicationReadyEvent, i.e., after startup runners are invoked and complete on the success path.
- Before runners finish, **do not infer readiness as ACCEPTING_TRAFFIC** just because ApplicationStartedEvent appeared or the web server is listening on its port.

Compact timeline:

~~~text
Context refreshed
      |
ApplicationStartedEvent
      |
LivenessState.CORRECT
      |
Runners (may take significant time)
      |
ApplicationReadyEvent
      |
ReadinessState.ACCEPTING_TRAFFIC
~~~

**Liveness differs from readiness.** An instance can be "alive" (context active) yet not have enough data/cache ready to serve requests. In Kubernetes, coordinate startup/readiness/liveness probes properly, use Actuator readiness when configured, and ensure the orchestrator does not send traffic too early.

**Do not tie liveness to external dependency status** such as a database or remote API without analyzing the impact: a shared dependency outage can make multiple Pods restart simultaneously, creating a cascading failure. Readiness or health checks can reflect serving capability per application contract.

## 8. What Work Should Be Handled in ApplicationStartedEvent?

### Appropriate

- Logging the context-refreshed milestone.
- Emitting lightweight startup metrics or tracing.
- Inspecting context configuration, bean definitions, or refresh results in a read-only manner.
- Measuring Duration from ApplicationStartedEvent.getTimeTaken() when wanting **time to started**, noting the value can be null.
- Tracking lifecycle milestones in monitoring/diagnostics tools.

### Should Move to a Runner

- Preloading caches mandatory before the application accepts traffic.
- Verifying critical dependencies through injected services.
- Checking/fixing initialization data with transactions and idempotency.
- Processing CLI arguments to decide startup tasks.
- Running operations that may fail and should count as a startup failure before ready.

Spring Boot recommends performing real startup work using **ApplicationRunner or CommandLineRunner**, rather than placing it in bean initialization callbacks or long listeners. Although doing so inside @EventListener(ApplicationStartedEvent.class) is technically possible, it mixes event purpose with business responsibilities and makes ordering and timeouts harder to manage.

### Should Use Another Mechanism

- **@PostConstruct/initMethod** for small state initialization tied to the bean itself.
- **SmartLifecycle** for consumers/background components requiring explicit start/stop.
- **@Scheduled** for periodic jobs after the service is running.
- **ApplicationReadyEvent** for lightweight post-runner event/metric recording, not a mandatory task that must run before ready.
- **Flyway/Liquibase** for versioned schema migrations, rather than writing a custom runner that alters schemas uncontrollably.

## 9. Error Handling When a Listener or Runner Throws an Exception

| Failure origin | Typical consequence |
| --- | --- |
| Bean @PostConstruct throws during refresh | Context refresh fails; never reaches ApplicationStartedEvent |
| Synchronous listener handling ApplicationStartedEvent throws | SpringApplication may branch into startup failure before runners are called |
| ApplicationRunner/CommandLineRunner throws | ApplicationStartedEvent may have already occurred; ApplicationReadyEvent does not fire on the success path |
| ApplicationReadyEvent listener throws | Startup may branch into failure handling right at the ready phase; do not use this listener for heavy business logic |
| An @Async task launched from a listener fails later | Failure does not automatically become a synchronous SpringApplication.run(...) exception; separate monitoring and handling are required |
| HTTP request error after the application is ready | This is a runtime error, not automatically a startup failure |

**Clarification on synchronicity:** by default Spring Framework uses synchronous event publication, so listeners execute on the publishing thread; therefore synchronous listener errors can directly impact startup. If a listener is marked **@Async**, or the multicaster is configured asynchronously, *emitting the event* still happens at the lifecycle milestone, yet **completion of the listener's execution may occur after runners**. In that case, do not rely on an async callback to guarantee runners wait for its work to finish.

**Do not swallow mandatory errors:** if mandatory warmup only catches and logs an error inside a runner, the application may proceed to emit ApplicationReadyEvent even though data is invalid. Conversely, a temporary metric exporter outage should not necessarily fail the entire service; use timeouts and error isolation for observability.

**Cleanup:** when SpringApplication encounters a startup failure, it handles the error and closes the ApplicationContext if one exists; resources registered via bean lifecycles are cleaned up on a best-effort basis by the container. However, external files, messages, API calls, and out-of-context data do not automatically roll back; if a runner has side effects, apply proper transactions, compensation, idempotency, and rollback.

## 10. Notes on Listener Order, Runner Order, and Multiple Contexts

### Listener @Order Does Not Replace Runner @Order

An application may have multiple listeners receiving ApplicationStartedEvent. **@Order/Ordered** can control execution order among listeners for the same event. Meanwhile, **ApplicationRunner** and **CommandLineRunner** are ordered by **@Order/Ordered on the runner beans**. Those two orders are two separate groups:

~~~text
ApplicationStartedEvent
  Listener A (order 10)
  Listener B (order 20)
       |
  Runner X (order 10)
  Runner Y (order 20)
       |
ApplicationReadyEvent
~~~

You cannot put @Order(-1000) on a runner and expect it to run before ApplicationStartedEvent. Lifecycle milestones always follow their sequence. If runners share the same order, avoid relying on bean discovery order or class names for mandatory business logic.

### Parent/Child ApplicationContext and Event Bubbling

Spring Framework can propagate events from a **child context** to **parent contexts**. When an application has multiple SpringApplication instances or a context hierarchy, a listener may receive multiple events of the same type from different contexts. To restrict handling:

~~~java
if (event.getApplicationContext() != myApplicationContext) {
    return;
}
~~~

This is an illustrative snippet inside a listener, requiring **myApplicationContext** to be properly injected/managed. Compare by **context identity** instead of assuming "there is only one ApplicationStartedEvent per JVM." For most single-context Boot apps, this check is unnecessary.

### Do Not Confuse the Event with the "Started ..." Log Line

Spring Boot's "Started ... in ... seconds" log line and ApplicationStartedEvent both relate to the context refresh phase, but do not use log strings as an orchestration API. Log formatting can change across versions, logging configs, and framework timing. To react to lifecycle milestones, use events or runners per contract.

## 11. Common Pitfalls

**1. "ApplicationStartedEvent means all runners have run."** False. It occurs **before** runners.

**2. "ApplicationStartedEvent means the application is ready for HTTP traffic."** False. Runners and ReadinessState.ACCEPTING_TRAFFIC still lie ahead.

**3. "Just because the web server bound its port means business requests can be sent."** Insufficient. Cache preloading, validation, or seeding may still be running inside runners.

**4. "The event occurs before ApplicationContext is created."** False. ApplicationStartedEvent appears **after** refresh; the ultra-early events are ApplicationStartingEvent and ApplicationEnvironmentPreparedEvent.

**5. "All @PostConstruct methods have run when started is emitted."** Not completely. Regular non-lazy singletons are created during refresh, but lazy beans may still be uninitialized.

**6. "started.getTimeTaken() is total startup time until ready."** False. It measures duration up to the started milestone, excluding runner execution; the value can also be null.

**7. "Runner @Order can change the order of started/ready events."** False. It only orders runners relative to each other.

**8. "An @Async listener still finishes before runners because the event is emitted earlier."** Not guaranteed. Emitting an event earlier is different from an async listener finishing execution earlier.

**9. "If the Started listener logged output, startup cannot fail."** False. Subsequent runners can still throw exceptions and prevent the ready branch.

**10. "ApplicationReadyEvent is the same as ApplicationStartedEvent."** False. They guarantee different milestones; only Ready comes after runners.

**11. "A context hierarchy emits strictly one Started event."** Do not assume that. Spring may have parent/child contexts and event propagation; filter by context if needed.

**12. "To run database migrations, put them straight into a Started listener."** Not recommended. Use Flyway/Liquibase or a startup mechanism designed for migrations with transactions, versioning, and multi-instance coordination.

## 12. Design and Operations Checklist

Before using ApplicationStartedEvent, verify:

1. **Goal:** is this observing the started milestone or performing mandatory startup work?
2. **Context:** does the listener need beans? If using @EventListener, is the bean registered with an appropriate scope?
3. **Runners:** which runners may run after the event, and do they need explicit @Order or dependencies?
4. **Readiness:** under what condition does the system accept traffic—does it wait for Ready/appropriate health probes?
5. **Synchronicity:** does the listener run synchronously by default, or is @Async/async multicaster enabled?
6. **Exceptions:** should listener/runner errors fail startup or only log warnings? Are critical errors accidentally being swallowed?
7. **Timing:** does listener work add startup latency? Should you measure Duration for started, ready, or a dedicated runner metric?
8. **Resources:** if a runner or listener opens connections/files/threads, who is responsible for closing them on failure?
9. **Multi-instance:** will the runner re-execute on Pod restart or scale-out, and is it idempotent?
10. **Testing:** have you tested the runner-failure branch and confirmed ApplicationReadyEvent does not occur on the success path?

A sound decision is usually **ApplicationStartedEvent listener for the "refresh complete" signal**, **runners for "mandatory work before ready,"** and **ApplicationReadyEvent/availability for "startup complete and ready to serve."**

## 13. Self-Check Questions

**Question 1. Does ApplicationStartedEvent occur before or after ApplicationContext.refresh()?**  
After the context has refreshed successfully.

**Question 2. Does ApplicationStartedEvent occur before or after ApplicationRunner?**  
Before runners are invoked by SpringApplication.

**Question 3. Why can ApplicationStartedEvent not be treated as readiness?**  
Because runners may still be running, failing, or not yet started; ReadinessState.ACCEPTING_TRAFFIC is published at a later milestone.

**Question 4. Can an @EventListener(ApplicationStartedEvent.class) inject service beans?**  
Yes, if it lives in a Spring-managed bean inside the refreshed context. You still need to account for lazy beans and startup side effects.

**Question 5. If a runner throws an exception after ApplicationStartedEvent, does ApplicationReadyEvent occur?**  
Not on the successful startup branch. SpringApplication handles the startup failure.

**Question 6. If a Started listener starts a CompletableFuture and returns immediately, do runners wait for the Future?**  
Not automatically. You must explicitly await the result/timeout or move mandatory work into a synchronous runner.

**Question 7. Does @Order(10) on a CommandLineRunner make it run before a Started listener with order(20)?**  
No. @Order does not change the order between lifecycle events and runners.

**Question 8. Does getTimeTaken() in ApplicationStartedEvent include runners?**  
No. It describes the time up to the started milestone; it can be null.

**Question 9. If a context has a parent and child, why might a listener receive multiple Started events?**  
Due to multiple contexts/SpringApplication runs and event propagation to the parent; inspect the source context.

**Question 10. What should you use to record a lightweight metric right after refresh?**  
An ApplicationStartedEvent listener with brief, non-blocking work that does not depend on runners having finished.

**Final takeaway:** **ApplicationStartedEvent sits squarely between "context refresh succeeded" and "executing ApplicationRunner/CommandLineRunner"**. It is useful for observing startup, yet **does not guarantee the application is ready**. Choose runners for work that must finish before receiving traffic, and use ApplicationReadyEvent/readiness to signal that the application has passed startup successfully.

### References

- [Spring Boot — SpringApplication: Application Events and Listeners, Availability, Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 API — ApplicationStartedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot 3.3 API — ApplicationReadyEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot 3.3 API — ApplicationRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Framework — Application Events and EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
