# Distinguishing Bean Initialization Completion from Spring Boot Application Readiness

## 1. Two different milestones in the same startup process

A Spring Boot application typically consists of dozens to thousands of beans. Each bean has its **own initialization lifecycle**, whereas the entire application has a **shared startup lifecycle**. Consequently, seeing that a bean has run its constructor or **@PostConstruct** does not mean the whole application is ready to handle work.

Distinguish two concepts:

- **Bean initialized:** Spring has created and configured **a specific bean**, resolved its required dependencies, and executed that bean's initialization steps per the container's contract. After the applicable BeanPostProcessors finish, the bean can be used within its scope.
- **Application ready:** Spring Boot has finished starting the ApplicationContext, executed all registered **ApplicationRunner** and **CommandLineRunner** beans, and published **ApplicationReadyEvent**. Boot proceeds to publish **ReadinessState.ACCEPTING_TRAFFIC** right after this event in the default lifecycle.

A bean completing initialization is a **local milestone**; ApplicationReadyEvent is an **application-wide milestone**. Many steps may separate the two: initializing other beans, refreshing the context, publishing startup events, and executing runners.

**Do not equate @PostConstruct, ContextRefreshedEvent, ApplicationStartedEvent, and ApplicationReadyEvent.** They belong to different layers of responsibility and timing.

## 2. Timeline from bean to application ready

~~~text
SpringApplication.run(args)
         |
         v
Prepare Environment, configuration, create ApplicationContext
         |
         v
Load BeanDefinitions and refresh ApplicationContext
         |
         +--> Create bean A
         |       Constructor + dependency injection
         |       @PostConstruct / InitializingBean / init method
         |       Post-initialization BeanPostProcessor
         |       => Bean A initialized
         |
         +--> Create beans B, C and other non-lazy singletons
         |
         +--> SmartInitializingSingleton callbacks
         |       (after pre-instantiating regular singletons)
         |
         +--> Complete context refresh
         |       ContextRefreshedEvent
         |
         v
ApplicationStartedEvent
         |
         +--> AvailabilityChangeEvent(LivenessState.CORRECT)
         |
         v
ApplicationRunner / CommandLineRunner
         |
         v
ApplicationReadyEvent
         |
         +--> AvailabilityChangeEvent(
         |        ReadinessState.ACCEPTING_TRAFFIC)
         |
         v
SpringApplication.run(args) returns to main
         |
         v
Application continues running according to its model
~~~

The diagram depicts Spring Boot 3.5's **default successful startup** flow. Some infrastructure beans and BeanPostProcessors must be created early to support creating other beans. Lazy/prototype beans may be created **after the ready point**. Listeners configured to run asynchronously can make observing order more complex.

The official sequence defined by Spring Boot:

1. **ApplicationStartingEvent**, **ApplicationEnvironmentPreparedEvent**, **ApplicationContextInitializedEvent**, and **ApplicationPreparedEvent** occur before or around context creation/preparation.
2. **ContextRefreshedEvent** is published after the context is refreshed; in a web context, **WebServerInitializedEvent** may also be published during startup.
3. **ApplicationStartedEvent** is published **after refresh**, **before runners**.
4. **AvailabilityChangeEvent** with **LivenessState.CORRECT** is published right after the started event.
5. Boot executes **ApplicationRunner** and **CommandLineRunner** beans.
6. **ApplicationReadyEvent** is published **after runners have finished executing**.
7. **AvailabilityChangeEvent** with **ReadinessState.ACCEPTING_TRAFFIC** is published right after the ready event.

Thus, application ready is neither simply “all constructors finished running” nor merely “the HTTP server bound its port”.

## 3. When is a bean considered finished initializing?

Spring manages beans according to **BeanDefinition**, scope, dependencies, and container extension mechanisms. For a typical **non-lazy singleton**, the representative steps are:

1. **Instance creation:** call constructor or factory method / **@Bean** method.
2. **Populate dependencies and properties:** resolve values/beans the object needs and apply the corresponding injection mechanisms.
3. **Aware callbacks:** interfaces such as **BeanNameAware**, **BeanFactoryAware**, or **ApplicationContextAware** may be called per contract.
4. **Pre-initialization BeanPostProcessors:** processors get a chance to handle the instance before init callbacks.
5. **Initialization callbacks:** may include **@PostConstruct**, **InitializingBean.afterPropertiesSet()**, and a **custom init-method** if declared.
6. **Post-initialization BeanPostProcessors:** processors may apply further handling, including returning wrappers/proxies in mechanisms such as AOP.
7. The bean is exposed by the container according to its **scope**, with lifecycle initialization complete.

Some steps may be executed by post-processors themselves, and detailed ordering depends on bean kind and configured mechanisms. Do not treat the constructor or **@PostConstruct** as always being the final callback before an instance is ready.

When combining all three init callback mechanisms using different methods, the standard order specified by Spring Framework is:

~~~text
@PostConstruct
    -> InitializingBean.afterPropertiesSet()
    -> custom init-method
~~~

However, **BeanPostProcessor**s can run before/after these callbacks. A proxied bean can cause the object returned to clients to differ by reference from the original object, while still honoring Spring's contract.

### What exactly does @PostConstruct mean?

**@PostConstruct** runs after the bean is instantiated and required dependencies are injected, during **that bean's** initialization. It is suited for:

- Validating the bean's local configuration.
- Preparing simple internal data structures.
- Establishing invariants required before the bean is used.

**@PostConstruct does not mean:**

- Every bean in the context has initialized.
- Every data source, message consumer, or external cache is ready.
- Spring Boot runners have finished.
- The application has published **ApplicationReadyEvent**.
- A load balancer or Kubernetes has marked the pod ready to receive traffic.

Spring Framework advises against putting time-consuming work, arbitrary lookups of other beans, or potentially deadlocking operations in init callbacks: initialization runs under container management and may execute while singleton creation locks are held.

## 4. Comparing milestones in a table

| Milestone / callback | Scope | Timing | What it proves | What it does not prove |
| --- | --- | --- | --- | --- |
| **Constructor** | One object | When Spring instantiates | Object is being constructed | Dependency injection / bean initialization finished |
| **@PostConstruct** | One bean | During bean initialization | Bean received dependencies needed to run the callback | Context refreshed or application ready |
| **InitializingBean.afterPropertiesSet()** | One bean | During initialization | One of the bean's init callbacks ran | Other beans are ready |
| **SmartInitializingSingleton.afterSingletonsInstantiated()** | BeanFactory singleton phase | After pre-instantiation of non-lazy singletons | Reached the end of creating regular singletons | All lazy/prototype beans exist or Boot is ready |
| **ContextRefreshedEvent** | ApplicationContext | After context refresh | That context finished refreshing | Runners finished |
| **ApplicationStartedEvent** | SpringApplication | After refresh, before runners | Boot reached the started milestone | Application is ready |
| **ApplicationRunner / CommandLineRunner** | Startup work | After ApplicationStartedEvent, before ready | Post-refresh preparation is running | Other runners finished if current method has not returned |
| **ApplicationReadyEvent** | SpringApplication | After runners complete | Boot reports startup complete at the application level | All external dependencies stay healthy afterward |
| **ReadinessState.ACCEPTING_TRAFFIC** | ApplicationAvailability | Right after ready event in default startup | Boot reports it can accept traffic | Orchestrator has already routed traffic to the instance |
| **@PreDestroy** | One bean | When bean is destroyed/closed normally | Reached the bean's cleanup step | Application once completed startup or all cleanup succeeded |

Two important notes:

- For **lazy** or **prototype** beans, initialization may happen **after ApplicationReadyEvent** when the bean is first requested. Therefore, do not state “ready means every bean in the system has been created”.
- With a context hierarchy, child context events can propagate to the parent. A parent listener may receive multiple **ContextRefreshedEvent**s; distinguish the originating context rather than merely counting callback invocations.

## 5. Runnable Java 17+ example: observing each step

This example uses **Spring Boot 3.5.x** and Java 17+ in a **non-web** application. The goal is to visually observe the order:

- Bean constructor.
- **@PostConstruct**.
- **SmartInitializingSingleton.afterSingletonsInstantiated()**.
- **ContextRefreshedEvent**.
- **ApplicationStartedEvent**.
- **ApplicationRunner**.
- **ApplicationReadyEvent**.
- **SpringApplication.run** returning to main.
- **@PreDestroy** upon normal context close.

### 5.1. Create the project

Using Spring Initializr, select **Maven**, **Java 17 or higher**, **Spring Boot 3.5.x**, group **com.example**, artifact **startup-stages**, package **com.example.demo**, and dependency **Spring Boot Starter**. No starter-web is needed because the application intentionally selects **WebApplicationType.NONE**.

Create the file **src/main/java/com/example/demo/StartupStagesApplication.java** as follows:

~~~java
package com.example.demo;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupStagesApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupStagesApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("08 | run returned; active="
                    + context.isActive());
        }
    }

    @Bean
    StageProbe stageProbe() {
        return new StageProbe();
    }

    @Bean
    ApplicationRunner runAfterStarted(Environment environment) {
        return args -> {
            System.out.println("06 | ApplicationRunner");

            if (environment.getProperty(
                    "demo.fail-runner", Boolean.class, false)) {
                throw new IllegalStateException(
                        "Simulated startup runner failure");
            }
        };
    }

    public static final class StageProbe
            implements SmartInitializingSingleton {

        public StageProbe() {
            System.out.println("01 | constructor");
        }

        @PostConstruct
        public void initialized() {
            System.out.println("02 | @PostConstruct");
        }

        @Override
        public void afterSingletonsInstantiated() {
            System.out.println("03 | SmartInitializingSingleton");
        }

        @EventListener(ContextRefreshedEvent.class)
        public void contextRefreshed() {
            System.out.println("04 | ContextRefreshedEvent");
        }

        @EventListener(ApplicationStartedEvent.class)
        public void applicationStarted() {
            System.out.println("05 | ApplicationStartedEvent");
        }

        @EventListener(ApplicationReadyEvent.class)
        public void applicationReady() {
            System.out.println("07 | ApplicationReadyEvent");
        }

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("09 | @PreDestroy");
        }
    }
}
~~~

**The code above is a complete Java program** when placed in a Spring Boot project with the right dependencies. It cannot be compiled with **`javac StartupStagesApplication.java`** alone without Spring Boot/Spring Framework on the classpath. The project's Maven Wrapper resolves dependencies and selects the appropriate main class.

### 5.2. Run the program

From the project root directory:

~~~bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt:
# .\mvnw.cmd spring-boot:run
~~~

Resulting **lines printed by the program itself**, in order under the default successful startup scenario:

~~~text
01 | constructor
02 | @PostConstruct
03 | SmartInitializingSingleton
04 | ContextRefreshedEvent
05 | ApplicationStartedEvent
06 | ApplicationRunner
07 | ApplicationReadyEvent
08 | run returned; active=true
09 | @PreDestroy
~~~

Maven/Spring Boot may print additional logs interleaved; the block above filters only the numbered lines. Closing the context occurs at the end of **try-with-resources**, because the example is a short-lived non-web program. For a long-running web server, do not close the context immediately after run if it needs to keep serving requests.

### 5.3. Reading each milestone result

**01 | constructor:** only the StageProbe instance exists; we cannot yet conclude bean initialization is complete.

**02 | @PostConstruct:** Spring has brought the bean to an init callback. This is still initialization of **a single bean**, not the application-ready milestone.

**03 | SmartInitializingSingleton:** Spring finished pre-instantiating regular non-lazy singletons in the BeanFactory. This is a better extension point than @PostConstruct if you need lightweight work after regular singletons are created, yet before the context finishes refreshing. It does not guarantee lazy/prototype beans have been created.

**04 | ContextRefreshedEvent:** ApplicationContext finished refreshing. Essential singleton creation and refresh hooks have completed.

**05 | ApplicationStartedEvent:** Spring Boot published the started event, **before running the runners**. In the default lifecycle, Boot subsequently publishes liveness state **CORRECT**.

**06 | ApplicationRunner:** post-refresh code is running. This is the place for short preparation steps that must finish **before ready**.

**07 | ApplicationReadyEvent:** runners completed normally. Immediately after this event, Boot publishes availability state **ReadinessState.ACCEPTING_TRAFFIC** in default startup.

**08 | run returned; active=true:** **application.run(args)** returned the context to main. Because the context is not closed yet, **isActive()** is true.

**09 | @PreDestroy:** the end of the try block calls **close()**. Spring begins closing the context and invokes the bean's destroy callback.

The example shows **a bean initializes very early**, while overall application startup still continues through several more milestones.

### 5.4. Proof: bean init succeeds yet the application may not be ready

The ApplicationRunner in the example intentionally includes an error branch when **demo.fail-runner=true** is set. Package the program:

~~~bash
./mvnw package
~~~

Run the executable JAR (adjust the filename if Initializr generated a different version/artifact):

~~~bash
java -jar target/startup-stages-0.0.1-SNAPSHOT.jar --demo.fail-runner=true
~~~

When this property is enabled:

1. StageProbe's constructor and **@PostConstruct** have run.
2. The context may refresh successfully and Boot has published **ApplicationStartedEvent**.
3. **ApplicationRunner** prints line 06 and then throws **IllegalStateException**.
4. Startup is considered failed; **ApplicationReadyEvent** is not published, and code after **application.run(args)** does not run normally.
5. Spring Boot may log the error, publish **ApplicationFailedEvent**, and close the context/resources along the failure path.

Therefore, a **@PostConstruct success** log or even an **ApplicationStartedEvent** log **does not prove the application completed startup**.

Do not use this error branch in production except for testing purposes. It is a controlled failure mechanism to understand lifecycle boundaries.

## 6. Can a bean initialize after ApplicationReadyEvent?

**Yes.** Two common cases:

### Lazy singleton

~~~java
@Bean
@Lazy
ReportFormatter reportFormatter() {
    return new ReportFormatter();
}
~~~

This is an **illustrative configuration snippet**, requiring the ReportFormatter class and Bean/Lazy imports. If no eager bean forces ReportFormatter injection and nothing accesses it during startup, a lazy singleton may only be created when first requested.

An application can very well have already published **ApplicationReadyEvent** while ReportFormatter has not yet run its constructor or init callbacks. This **does not violate** the Spring lifecycle.

### Prototype bean

~~~java
@Scope("prototype")
@Component
class RequestScratchpad {
}
~~~

This is also an **illustrative snippet** (requiring imports and a consumer). Prototypes are normally created per request from the BeanFactory rather than pre-instantiated in bulk at startup. If a prototype is injected into an eager singleton during creation, one instance may have been created early, yet prototype scope does not turn into singleton.

**Consequence:** do not define readiness by “counting how many beans ran @PostConstruct”. Identify which dependencies are **required** to serve requests and verify them using appropriate mechanisms.

## 7. How do ContextRefreshedEvent, ApplicationStartedEvent, and ApplicationReadyEvent differ?

### ContextRefreshedEvent

This is a **Spring Framework** event when **ApplicationContext.refresh()** completes. It reflects **container** state. In a Boot application, the context may have refreshed successfully while a runner has not yet performed or finished its preparation work.

A system using a context hierarchy can publish multiple ContextRefreshedEvents, one for each context's lifecycle. Check **event.getApplicationContext()** when you need to distinguish the source.

### ApplicationStartedEvent

This is a **Spring Boot** event after the ApplicationContext is refreshed, **before ApplicationRunner and CommandLineRunner**. The name “Started” describes having started the context successfully, **not meaning ready**. If a runner throws an exception after this point, Boot may publish **ApplicationFailedEvent** without ApplicationReadyEvent.

### ApplicationReadyEvent

This is a **Spring Boot** event after runners; it is the milestone where Boot marks startup complete at the application level. By default order, Boot next publishes an AvailabilityChangeEvent with **ReadinessState.ACCEPTING_TRAFFIC**.

**A subtle detail:** a listener handling **ApplicationReadyEvent** itself should not assume **ReadinessState.ACCEPTING_TRAFFIC** has already been published, because that availability change event is published **after** the ready event. To observe the exact state, use the **ApplicationAvailability** API or an **AvailabilityChangeEvent** listener at the appropriate point.

### Should you manually publish ApplicationReadyEvent?

Do not manually publish the event to “force” the application into ready when startup steps are missing. Spring Boot manages these events in its startup sequence. If an application needs to actively pause accepting traffic at runtime, use **ApplicationAvailability** mechanisms or health/readiness probes designed for that purpose rather than faking startup events.

## 8. Readiness differs from liveness and from an open HTTP port

Spring Boot models availability with two primary state types:

| State | Purpose | Examples |
| --- | --- | --- |
| **LivenessState** | Is the application in a valid living state, or does it need a restart? | **CORRECT**, **BROKEN** |
| **ReadinessState** | Should the application receive traffic at this moment? | **ACCEPTING_TRAFFIC**, **REFUSING_TRAFFIC** |

In default startup, liveness **CORRECT** is tied to right after **ApplicationStartedEvent**, while readiness **ACCEPTING_TRAFFIC** is tied to right after **ApplicationReadyEvent**. However, readiness can change later; “once ready” does not mean always ready forever.

For web applications, **the embedded web server may have already bound its port during refresh**. A direct client might connect to the port while runners have not finished, depending on server type and state. This **does not prove readiness**. In orchestrated environments, readiness probes typically determine whether traffic is routed to the instance.

With Spring Boot Actuator, you can configure health probes such as **/actuator/health/liveness** and **/actuator/health/readiness** where appropriate for the version and environment. Those endpoints/probes depend on Actuator, security configuration, and enablement flags; do not assume every project exposes them out of the box.

**Do not casually add databases, external caches, or external APIs into liveness checks.** An external dependency outage could trigger cascading pod restarts. Readiness is better suited to temporarily stop accepting traffic when a required dependency is unavailable, though it must be designed around your actual serving model.

## 9. Choosing the right hook for your need

| Need | Consider using | Why |
| --- | --- | --- |
| Validate a bean's local configuration, simple internal init | **@PostConstruct**, init method | Directly tied to that bean's lifecycle |
| Lightweight action after regular non-lazy singletons are created | **SmartInitializingSingleton** | Avoids arbitrary cross-bean lookups in constructors/@PostConstruct |
| React when ApplicationContext finishes refreshing | **@EventListener(ContextRefreshedEvent.class)** | Context just completed refresh |
| Handle post-refresh work before runners | **@EventListener(ApplicationStartedEvent.class)** | Spring Boot started milestone |
| Run mandatory prep tasks before ready | **ApplicationRunner** / **CommandLineRunner** | Boot waits for runners to finish before ready |
| Log or run lightweight work once startup finishes | **@EventListener(ApplicationReadyEvent.class)** | Final Boot startup milestone |
| Manage a background service with context-bound start/stop | **SmartLifecycle** | Phased start/stop lifecycle management |
| Toggle traffic-acceptance state on runtime changes | **ApplicationAvailability** or readiness health/probes | Expresses capacity to accept work at the right moment |

### Why not put everything in @PostConstruct?

If every bean calls external services, scans large datasets, launches infinite threads, or queries other beans arbitrarily inside **@PostConstruct**, startup easily suffers from:

- Singleton creation locks held for too long, slowing refresh or causing deadlocks.
- Hard-to-understand dependency cycles.
- One bean's initialization failure bringing down the entire ApplicationContext.
- A bean declaring itself ready even though other components are not yet ready.
- Complex cleanup if startup fails halfway through.

Keep initialization callbacks **short and local**. When you need system-wide checks or post-refresh startup tasks, pick the runner or lifecycle hook for that stage.

### Does a runner guarantee background work is finished?

**No, if the runner just spawns an asynchronous task and returns immediately.** Spring Boot only waits for the **run** method to finish; it does not automatically know whether a Future, thread, queue consumer, or self-created async operation has completed. If the work is truly mandatory before readiness, wait/verify with a bounded timeout or control readiness explicitly.

For example, a runner:

~~~java
return args -> {
    backgroundExecutor.submit(this::loadEssentialData);
};
~~~

only illustrates how to **launch** background work (variables `backgroundExecutor` and method `loadEssentialData` are undefined in this snippet). It does not wait for `loadEssentialData` to finish. Thus `ApplicationReadyEvent` can arrive while data loading is still running. Real applications need readiness policies, timeouts, retries, and failure handling.

## 10. Startup failure scenarios

### Bean @PostConstruct throws an exception

For an eager singleton initialized during refresh, an unhandled exception in **@PostConstruct** normally causes bean creation to fail and context refresh to fail. In that case Boot **does not reach ApplicationReadyEvent**; **ApplicationFailedEvent** may be published.

### Runner throws an exception

Beans and context may have initialized/refreshed successfully, and even **ApplicationStartedEvent** has been published. Yet when a runner fails, Boot still considers startup failed; the ready event is not published. This is the exact test branch in Section 5.4.

### Lazy bean fails after ready

A misconfigured lazy bean may only fail when accessed after the application is already ready. The Spring Boot Reference explicitly calls out this lazy-initialization trade-off: reducing startup time shifts error detection until the bean is used.

### External resource disconnects after ready

ApplicationReadyEvent is a milestone in startup history, not a permanent guarantee of dependency health. You still need timeouts, retries, circuit breakers (where appropriate), health/readiness checks, and continuous runtime observability.

## 11. Misconceptions and corrections

| Misconception | Accurate understanding |
| --- | --- |
| **“A service's @PostConstruct ran, so the app is ready.”** | It only confirms one callback of that service; overall startup has more steps |
| **“Constructor finished means the bean completed initialization.”** | Injection, init callbacks, and BeanPostProcessors may still follow |
| **“All singletons finished initializing means every bean exists.”** | Lazy/prototype beans may be created later |
| **“ContextRefreshedEvent equals ApplicationReadyEvent.”** | Context refresh happens before Boot runners and ready |
| **“ApplicationStartedEvent means traffic can be served immediately.”** | Started occurs before runners; the readiness event arrives after ready |
| **“Port 8080 is open means the pod is ready.”** | Port may bind before runners finish; routing depends on readiness |
| **“Runner started an async job and returned, so the async job finished.”** | Runner waits only for what it directly executes/awaits |
| **“ApplicationReadyEvent means dependencies are always healthy.”** | Runtime health can degrade after startup |
| **“Every @EventListener always completes synchronously.”** | Depends on event multicaster configuration and async handling |
| **“If the ready listener runs, ReadinessState is already ACCEPTING.”** | In Boot's lifecycle, that availability change fires right **after** the ready event |
| **“Spring Boot automatically knows external service health.”** | Health/readiness for external dependencies must be designed per context |

## 12. Verification and observation in real systems

1. **Add logs at the right milestones:** do not log only constructors or @PostConstruct; also observe ContextRefreshedEvent, ApplicationStartedEvent, runners, and ApplicationReadyEvent.
2. **Distinguish startup success from healthy operation:** startup events confirm sequence; health, metrics, and traces show subsequent runtime state.
3. **Find slow startup tasks:** measure durations in runners or use **ApplicationStartup / StartupStep** tracking. With Actuator appropriately configured, the **startup** endpoint can help profile initialization.
4. **Check lazy initialization config:** **spring.main.lazy-initialization=true** can defer many beans until first use; do not use @PostConstruct counts as a readiness criterion.
5. **Verify platform readiness probes:** right endpoint, right port, reasonable timeouts, distinguishing liveness from readiness.
6. **Diagnose specific failures:** read the root stack trace of bean creation or runner failures to locate the problem instead of looking only at “Application run failed”.
7. **Audit background tasks:** if a runner launches background jobs, verify the system does not mark itself ready before critical conditions are met.

## 13. Reinforcement exercises

**Question 1.** One bean logged “@PostConstruct OK”, yet another bean failed to connect to the database and caused refresh to fail. Is the application considered ready? Why?

**Question 2.** ContextRefreshedEvent has fired, and then ApplicationRunner runs for 30 seconds to load data. During those 30 seconds, which events have occurred and which have not?

**Question 3.** Why can an application be ready before a @Lazy bean runs its constructor? When that bean fails after ready, how does it affect startup investigation?

**Question 4.** In the sample code, change **demo.fail-runner** to true. Predict which numbered lines definitely belong to the startup path before the error, and why lines 07/08 do not appear normally.

**Question 5.** A runner merely submits a task to an executor and returns. Can ApplicationReadyEvent's timestamp serve as proof the task finished?

**Question 6.** Why shouldn't you automatically add an external database to every microservice's liveness probe? When does database-dependent readiness make sense?

**Suggested answers:** (1) no, a local bean completing does not make the whole context succeed; (2) refresh and started have occurred, ready has not; (3) lazy beans are created on demand so errors may surface late; (4) constructor, @PostConstruct, SmartInitializingSingleton, ContextRefreshed, Started, and runner run before the error branch, whereas Ready and successful run return do not occur; (5) no, a runner does not wait for async work unless coded to wait; (6) a DB outage can trigger cascading restarts, whereas readiness decides whether to pause traffic if the DB is a mandatory dependency.

## 14. Key takeaways and references

**Bean initialization completing is a milestone of a single Spring-managed object. Application ready is the milestone where Spring Boot has refreshed the context and completed startup runners.** Between the two lie creating other beans, context lifecycle events, and application-level preparation steps. A lazy bean can even initialize **after** ready.

Milestones to remember in order:

~~~text
Bean initialization
    -> ContextRefreshedEvent
    -> ApplicationStartedEvent
    -> ApplicationRunner / CommandLineRunner
    -> ApplicationReadyEvent
    -> ReadinessState.ACCEPTING_TRAFFIC
~~~

This is the typical order observed in successful startup with non-lazy singletons. It **does not apply to every lazy/prototype bean**, nor does it replace runtime health monitoring after startup.

Official documentation to verify per version:

1. Spring Framework — Customizing the Nature of a Bean, initialization callbacks and SmartLifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
2. Spring Framework — Container Extension Points (BeanPostProcessor and BeanFactoryPostProcessor): https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
3. Spring Boot 3.5 — SpringApplication, application events, runners, lazy initialization: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
4. Spring Boot 3.5 — ApplicationStartedEvent API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html

Examples are designed for **Spring Boot 3.5.x, Spring Framework 6.x, and Java 17+**. For Spring Boot 4.x or major Framework changes, verify the APIs and lifecycle events in the exact version's documentation before reusing code verbatim.