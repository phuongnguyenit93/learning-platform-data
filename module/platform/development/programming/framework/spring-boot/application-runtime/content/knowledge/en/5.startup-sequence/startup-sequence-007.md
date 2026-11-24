# Refreshing ApplicationContext and Completing Initialization of Required Components in Spring Boot

**Scope:** Spring Boot Application Runtime → Startup Sequence. This article explains specifically when `SpringApplication` refreshes `ApplicationContext`, how Spring processes bean definitions and instantiates singletons, how the web runtime is initialized, post-refresh milestones, how to read evidence, and how to handle startup failures. The examples run on **Java 17+**, **Spring Boot 3.3.x**, and **Spring MVC**. Event milestones, APIs, and defaults must be cross-checked against the documentation for the version in use if a project runs Spring Boot 4.x or another line.

## 1. Learning Objectives and Key Questions

By the end of this lesson, learners should be able to answer:

1. Which step is `refresh()` inside `SpringApplication.run()` and why is it critical?
2. How does a bean definition differ from a bean instance? At which stage do `BeanFactoryPostProcessor` and `BeanPostProcessor` run?
3. How does Spring instantiate a bean, inject dependencies, invoke `@PostConstruct`, `InitializingBean`, and create proxies before considering the bean ready?
4. What do `finishBeanFactoryInitialization` and `finishRefresh` do? Under what conditions does a bean not yet need to be instantiated when refresh ends?
5. Why are `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationRunner`, and `ApplicationReadyEvent` not synonymous?
6. How do you verify that an application has initialized essential components and can serve HTTP via logs, events, and actual responses?
7. When refresh fails, where should you read the root cause from, and what can you **not** conclude yet about the application's state?

**Main point:** `refresh()` turns a configuration-prepared context into an active container: finalizing bean definitions, registering bean processing mechanisms, instantiating required singletons, starting lifecycle infrastructure, and publishing `ContextRefreshedEvent`. Afterward, Spring Boot still executes steps such as publishing `ApplicationStartedEvent`, running `ApplicationRunner`/`CommandLineRunner`, and publishing `ApplicationReadyEvent`. "Refresh finished" does not mean "every component that could exist has already been created", nor does it by itself prove business APIs return correct data.

## 2. Where Does Refresh Sit in the Startup Sequence?

Diagram for a successful web app run:

~~~text
main(args)
  |
  v
SpringApplication.run(args)
  |
  +-- prepare Environment / configuration / profiles
  +-- select and create ConfigurableApplicationContext
  +-- apply ApplicationContextInitializer
  +-- load source configuration and register initial bean definitions
  +-- ApplicationPreparedEvent (context not yet refreshed)
  |
  +-- refreshContext(context)
  |      |
  |      +-- AbstractApplicationContext.refresh()
  |             +-- finalize bean definitions
  |             +-- register BeanPostProcessors
  |             +-- prepare context infrastructure
  |             +-- instantiate non-lazy singletons
  |             +-- start related lifecycle components
  |             +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent (refresh complete)
  +-- ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
  +-- readiness transitions to ACCEPTING_TRAFFIC (default)
  |
  v
run() completes; app serves requests / processes work
~~~

Method names and internal ordering can vary slightly across versions, yet the high-level contract is quite stable. For Boot 3.3, `ApplicationStartedEvent` is published after the context has refreshed and before runners, whereas `ApplicationReadyEvent` comes after runners finish. A failing runner can keep the app from **ever becoming ready** even though the context already refreshed.

Many servlet applications create and start the embedded web server during the refresh process. Thus, the fact that the HTTP port may open at a point before the ready event **does not** allow assuming all startup tasks have completed. Readiness is interpreted according to application policy and deployment platform; check HTTP status, ready milestones, and health/readiness as needed.

## 3. Core Phases Inside AbstractApplicationContext.refresh()

`AbstractApplicationContext.refresh()` is Spring Framework's template algorithm. The table below links each method to what is finalized:

| Phase | Main work | Typical evidence or failure |
|---|---|---|
| `prepareRefresh()` | Mark context as preparing, validate/initialize property sources | Missing source config, context cannot start |
| `obtainFreshBeanFactory()` | Create/prepare the context's BeanFactory, attach bean definition store | Bean definition configuration issues |
| `prepareBeanFactory(...)` | Configure standard traits such as ClassLoader, infrastructure processors | `Aware` interfaces and infrastructure active |
| `postProcessBeanFactory(...)` | Hook for context subclasses to customize BeanFactory | Registry/factory adjustments at implementation layer |
| `invokeBeanFactoryPostProcessors(...)` | Allow transforming and adding bean definitions before instantiating application singletons | Parsing `@Configuration`, `@Bean`, `@ComponentScan`, `@Import` |
| `registerBeanPostProcessors(...)` | Register processors that handle bean instances as they are created | `@PostConstruct`, autowiring, conditional proxies/AOP |
| `initMessageSource()` | Prepare message/i18n source | `MessageSource` active |
| `initApplicationEventMulticaster()` | Prepare application event multicasting mechanism | Listeners receive context events properly |
| `onRefresh()` | Special extension point per context subclass, e.g., preparing web server | Servlet/reactive server set up depending on context |
| `registerListeners()` | Register listener beans and process early events | Listeners begin participating in dispatch |
| `finishBeanFactoryInitialization(...)` | Finalize BeanFactory and pre-instantiate remaining non-lazy singletons | Constructors, injection, init callbacks; bean creation errors |
| `finishRefresh()` | Activate lifecycle processor, publish `ContextRefreshedEvent`, complete refresh | Context-refreshed marker appears |

This is a conceptual sequence for learning; in practice Boot applies many automatic processors before creating application beans. You should not conclude that each method name maps directly to a dedicated log line, or that every bean can only be created in `finishBeanFactoryInitialization`. Infrastructure beans such as processors may need to initialize **earlier** to process remaining beans.

### 3.1. A Bean Definition Is Not a Bean Instance

A **bean definition** is metadata telling the container how a bean can be created: class/factory method, scope, dependencies, lazy flag, configuration conditions, init/destroy callbacks. It can exist in the registry **before** the Java object is created.

Example:

~~~java
@Configuration
class AppConfig {
    @Bean
    PaymentGateway paymentGateway() {
        return new PaymentGateway();
    }
}
~~~

Once Spring processes configuration, the registry can hold a definition for `paymentGateway`. Only when the container instantiates it does `PaymentGateway` become a bean instance. For non-lazy singletons, this typically occurs during refresh. If the bean is lazy/prototype/request-scoped, an instance may only appear when appropriately requested.

`@SpringBootApplication` combines configuration, component scanning, and auto-configuration semantics. Auto-configuration relies on classpath conditions, properties, existing beans, and other conditions; it must not be understood as the framework automatically instantiating everything on the classpath.

### 3.2. BeanFactoryPostProcessor and BeanPostProcessor

Distinguish two extension points:

- `BeanFactoryPostProcessor` works on metadata/`BeanFactory` **before** ordinary application singletons are instantiated. It is suited for modifying definitions; avoid calling `getBean(...)` indiscriminately and accidentally instantiating beans prematurely.
- `BeanPostProcessor` runs around the creation of each bean instance. It can alter initialization, invoke callbacks, or wrap the object in a proxy. AOP/transactions and many annotation mechanisms rely on post-processing infrastructure.
- `BeanDefinitionRegistryPostProcessor` has a step working directly with the definition registry; Spring uses infrastructure processors to parse Java configuration and expand necessary definitions.

If you define a custom `@Bean` returning `BeanFactoryPostProcessor` or `BeanPostProcessor` inside a `@Configuration` class, consider a `static` factory method and a sufficiently specific return type so the processor is recognized early. Wrong timing causes beans to initialize early and miss full post-processing.

### 3.3. Creation Lifecycle of an Ordinary Singleton

Model for **one** new bean created by the container:

~~~text
read BeanDefinition
    |
    v
select constructor / factory method -> instantiate
    |
    v
inject dependencies / properties, invoke appropriate Aware callbacks
    |
    v
BeanPostProcessor.beforeInitialization(...)
    +-- @PostConstruct (via corresponding processor)
    |
    v
InitializingBean.afterPropertiesSet(), custom init method
    |
    v
BeanPostProcessor.afterInitialization(...)
    +-- may return a proxy
    |
    v
bean ready for consumers to use
~~~

This order is the typical flow; dependency resolution can cause another bean to be initialized first. Proxies, circular dependencies, factory beans, and special configuration methods can make the observed cycle more complex. `@PostConstruct` runs **after dependencies are injected**, yet **before overall application startup completes**. Avoid starting long data-loading workflows or dispatching requests inside that callback.

### 3.4. Finishing Singletons and Lifecycle Infrastructure

`finishBeanFactoryInitialization(...)` instructs the container to pre-instantiate remaining non-lazy singletons. `SmartInitializingSingleton` callbacks run after ordinary singleton pre-instantiation completes. They are useful when you need a check depending on initialized singletons, yet **do not** guarantee all lazy or other-scoped beans already exist.

`finishRefresh()` completes refresh, triggers `LifecycleProcessor`, and publishes `ContextRefreshedEvent`. Beans implementing `SmartLifecycle` can auto-start by phase, which is very useful for container-managed workers, listeners, schedulers, or connection managers. When implementing it yourself, design consistent start/stop behavior and avoid blocking startup indefinitely.

## 4. Complete Example: Observing Refresh Milestones in an App

### 4.1. Creating the Java 17 Project

Create a Maven project with Spring Initializr:

- Group: `com.example`
- Artifact: `refresh-lab`
- Package: `com.example.refreshlab`
- Java: **17**
- Spring Boot: **3.3.x**
- Dependencies: **Spring Web** and **Spring Boot Actuator**.

Keep the starter/plugin versions generated by Initializr. The sample uses the default servlet web runtime from `spring-boot-starter-web`. Code structure to create:

~~~text
refresh-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/refreshlab/
    RefreshLabApplication.java
    ProbeService.java
    DeferredProbe.java
    ProbeController.java
    FailingInitProbe.java
  src/main/resources/application.properties
~~~

This is **a complete packaged Spring Boot application**, where the classes below live in separate files matching their public class names; do not use standalone `javac` because they require Maven dependencies. Actual commands to compile/run use Maven Wrapper (`./mvnw` or `./mvnw.cmd`), then `java -jar` once packaged.

### 4.2. Main Class and Event Markers

`src/main/java/com/example/refreshlab/RefreshLabApplication.java`:

~~~java
package com.example.refreshlab;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RefreshLabApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RefreshLabApplication.class);

        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                        System.out.println("LAB_APPLICATION_FAILED"));

        app.run(args);
    }

    @Bean
    static BeanFactoryPostProcessor definitionProbe() {
        return factory -> System.out.println(
                "LAB_DEFINITIONS_COUNT="
                        + factory.getBeanDefinitionCount());
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> System.out.println("LAB_RUNNER_DONE");
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onRefreshed() {
        System.out.println("LAB_CONTEXT_REFRESHED");
    }

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("LAB_APPLICATION_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LAB_APPLICATION_READY");
    }
}
~~~

**Explanation:**

- `setApplicationStartup(new BufferingApplicationStartup(2048))` records Spring Boot startup steps into a buffer; we will inspect it via Actuator `/actuator/startup`. Do not use an unbounded buffer and do not expose this endpoint to the public internet.
- `definitionProbe()` is a `static @Bean` returning `BeanFactoryPostProcessor`; the `LAB_DEFINITIONS_COUNT` marker prints the number of bean definitions known **at the callback moment**, not the total number of created bean objects. The number varies by dependencies and configuration.
- `ApplicationRunner` only runs after the context has refreshed and Boot has published `ApplicationStartedEvent`. Here the runner does not force lazy beans to be created early.
- `ContextRefreshedEvent` belongs to Spring Framework, while `ApplicationStartedEvent` and `ApplicationReadyEvent` belong to Spring Boot; these are distinct milestones.
- The `ApplicationFailedEvent` listener is registered early directly on `SpringApplication` so it can observe startup failures before context listener beans finish creating. The code only prints a marker; the actual stack trace printed by Boot helps locate the error cause.

### 4.3. Bean With Constructor, PostConstruct, and SmartInitializingSingleton

`src/main/java/com/example/refreshlab/ProbeService.java`:

~~~java
package com.example.refreshlab;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class ProbeService implements SmartInitializingSingleton {
    private final String label;

    public ProbeService(@Value("${lab.label:ready}") String label) {
        this.label = label;
        System.out.println("LAB_PROBE_CONSTRUCTOR");
    }

    @PostConstruct
    public void init() {
        System.out.println("LAB_PROBE_POST_CONSTRUCT");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("LAB_SINGLETONS_INSTANTIATED");
    }

    public String label() {
        return label;
    }
}
~~~

The constructor runs when the bean is instantiated; `@PostConstruct` runs once required dependencies and properties are injected; the `SmartInitializingSingleton` callback runs after the non-lazy singleton initialization phase. Thus the order **within this lab's markers** is:

~~~text
LAB_PROBE_CONSTRUCTOR
LAB_PROBE_POST_CONSTRUCT
LAB_SINGLETONS_INSTANTIATED
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_DONE
LAB_APPLICATION_READY
~~~

Many other logs interleave. `LAB_DEFINITIONS_COUNT=<number>` also appears before ordinary application singletons are created, though the numeric value is not fixed. With a single context like this lab, the refresh milestone occurs once; multi-context hierarchies can produce multiple events, and seeing repeated markers should not be misread as two JVM startups.

### 4.4. An Intentionally Lazy Bean to Illustrate What Is Not Yet Created

`src/main/java/com/example/refreshlab/DeferredProbe.java`:

~~~java
package com.example.refreshlab;

import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public class DeferredProbe {

    @PostConstruct
    public void init() {
        System.out.println("LAB_DEFERRED_INIT");
    }

    public String value() {
        return "deferred";
    }
}
~~~

This bean is defined in the context yet does not need instantiation during refresh because of `@Lazy`; a client must request it before the instance is created. We use `ObjectProvider` to avoid eager injection inside the controller's constructor.

### 4.5. Controller Proving the Runtime Is Ready to Serve

`src/main/java/com/example/refreshlab/ProbeController.java`:

~~~java
package com.example.refreshlab;

import java.util.Map;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    private final ProbeService service;
    private final ObjectProvider<DeferredProbe> deferred;

    public ProbeController(
            ProbeService service,
            ObjectProvider<DeferredProbe> deferred) {
        this.service = service;
        this.deferred = deferred;
    }

    @GetMapping("/probe")
    public Map<String, String> probe() {
        return Map.of("status", service.label());
    }

    @GetMapping("/lazy")
    public Map<String, String> lazy() {
        return Map.of("status", deferred.getObject().value());
    }
}
~~~

`GET /probe` uses the already-initialized `ProbeService` singleton; `GET /lazy` triggers `ObjectProvider` to fetch the `DeferredProbe` instance. Only on the first `GET /lazy` call does the console print `LAB_DEFERRED_INIT`. Subsequent requests reuse the same already-created lazy singleton, so no additional init marker prints if the app has only one context.

### 4.6. Conditional Failing Bean to Test Refresh Failure

`src/main/java/com/example/refreshlab/FailingInitProbe.java`:

~~~java
package com.example.refreshlab;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "lab.fail-on-init", havingValue = "true")
public class FailingInitProbe {

    @PostConstruct
    public void fail() {
        throw new IllegalStateException(
                "LAB_INTENTIONAL_STARTUP_FAILURE");
    }
}
~~~

When `lab.fail-on-init=true` is not passed, this bean is **not registered due to the condition**. When the flag is enabled, the singleton bean is instantiated and its callback throws an intentional exception; the application cannot finish refreshing. This experiment helps distinguish a startup failure from an HTTP request failure.

### 4.7. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=refresh-lab
server.port=8080
lab.label=ready
management.endpoints.web.exposure.include=health,startup
management.endpoint.health.show-details=never
~~~

Enable the `startup` endpoint only for **internal/local labs**. Actuator does not expose all endpoints over HTTP automatically. In real environments, do not expose operational endpoints containing sensitive data without access controls and network restrictions.

## 5. Running, Reading Logs, and Confirming the Initialization Sequence

### 5.1. Startup via Maven Wrapper

On Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

If `mvnw` does not yet have execute permission on Unix, grant execute permission on the project wrapper before running, or use `mvn spring-boot:run` if Maven is installed. Java and Maven must use a JDK version supported by the project.

In the application console, filter only lines containing `LAB_`. Do not expect all Tomcat or Spring logs to appear in a strictly fixed sequence. A successful marker excerpt is:

~~~text
LAB_DEFINITIONS_COUNT=<definition_count>
LAB_PROBE_CONSTRUCTOR
LAB_PROBE_POST_CONSTRUCT
LAB_SINGLETONS_INSTANTIATED
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_DONE
LAB_APPLICATION_READY
~~~

`<definition_count>` is an **illustrative placeholder**, not verbatim stdout; in a real run it is replaced by an integer. The remaining markers are strings printed by Java code, and their relative order above is what to observe. `LAB_DEFERRED_INIT` has not appeared yet if nobody has requested the lazy bean.

**How to read it:** `ContextRefreshedEvent` proves the framework completed the refresh phase; `ApplicationStartedEvent` proves Boot regained control after refresh; the runner finished before the ready event. If you only see `LAB_CONTEXT_REFRESHED` without `LAB_APPLICATION_READY`, do not mark overall startup as successful.

### 5.2. Actual HTTP Requests

Open a second terminal:

~~~bash
curl -i "http://localhost:8080/probe"
curl -i "http://localhost:8080/actuator/health"
~~~

When the lab app is running normally, `GET /probe` returns HTTP 200 with a JSON body equivalent to:

~~~json
{"status":"ready"}
~~~

`GET /actuator/health` normally returns status `UP` in a lab environment without failing dependencies:

~~~json
{"status":"UP"}
~~~

Headers, Content-Length, PID, displayed port in logs, and duration depend on the system; do not treat them as fixed assertions. `UP` is only the result of registered health indicators, not proof that every API returns valid business data.

Now call:

~~~bash
curl -i "http://localhost:8080/lazy"
curl -i "http://localhost:8080/lazy"
~~~

Both calls normally return:

~~~json
{"status":"deferred"}
~~~

The console prints `LAB_DEFERRED_INIT` **once**, when the bean is requested for the first time. This is direct evidence against the assumption that "once context refresh finishes, every bean has been instantiated". If you run the same app with a non-default global lazy mode, some bean creation milestones may shift to request time; note the active option when comparing.

### 5.3. Detailed Evidence From the Startup Endpoint

Because `main` configured `BufferingApplicationStartup` and Actuator exposure, call:

~~~bash
curl -i "http://localhost:8080/actuator/startup"
~~~

A successful response typically contains `timeline.events`, with fields such as `startupStep.name`, `startupStep.id`, `startTime`, `endTime`, `duration`, and `tags`. You may see steps related to `spring.context.refresh`, `spring.beans.instantiate`, bean post-processor handling, or Boot initialization work. **Do not hardcode** event counts, IDs, durations, or exact ordering of every event because they vary by dependencies and versions.

In Boot 3.3, the startup endpoint supports GET to take a snapshot and POST to consume/drain data in the buffer. For this exercise, prefer GET to observe without draining. Data from the startup endpoint is helpful for finding slow steps, yet does not replace profiling, error logs, or HTTP testing.

### 5.4. Running From the JAR File

Stop the Maven session and run:

~~~bash
./mvnw clean package
java -jar target/refresh-lab-0.0.1-SNAPSHOT.jar
~~~

On Windows use `./mvnw.cmd clean package`. The JAR filename applies when the artifact is `refresh-lab` and the default version is `0.0.1-SNAPSHOT`; if the version was changed by Initializr or the project, use the actual filename in `target/`. If you modify code or resources after packaging, rebuild the JAR to include the new version.

## 6. Completing Initialization Does Not Mean Every Bean Exists

By the end of refresh, the container has satisfied the contract for **non-lazy** singletons that need pre-instantiation and essential infrastructure components, within active configuration conditions. However, important exceptions exist:

| Case | Created immediately during refresh? | Meaning when checking |
|---|---|---|
| Default singleton, non-lazy | Normally yes, barring special mechanisms | Constructor/init failure usually fails startup |
| `@Lazy` singleton | Normally deferred until first use | Init error may surface at request time |
| `@Scope("prototype")` | Upon request for an object | Each request can create a new instance |
| `@RequestScope` | Per HTTP request | Cannot expect an instance ready at ready time |
| Bean whose `@ConditionalOnProperty` does not match | Definition may be excluded by condition | Absence of instance is the expected conditional behavior |
| Bean forced eager by a dependent bean | May be created early despite being marked lazy | Inspect the dependency graph before concluding lazy doesn't work |

`spring.main.lazy-initialization=true` can reduce startup time by deferring many beans until needed, yet can delay configuration errors and make the first request slower. Production projects should weigh readiness, early failure alerts, and warmup instead of looking only at shorter startup times.

If a lazy bean plays a **truly essential role before accepting traffic**, decide explicitly on a mechanism to initialize/verify it at the proper stage (e.g., a runner with a timeout or a health/readiness check reflecting the dependency), rather than assuming it has already been created.

## 7. Startup Events, Runners, and Readiness: Distinct Milestones

| Milestone | Timing | What can be concluded | What cannot yet be concluded |
|---|---|---|---|
| `ApplicationPreparedEvent` | Context prepared before refresh | Source bean definitions loaded to prepare refresh | Singleton beans are fully initialized |
| `ContextRefreshedEvent` | Spring Framework completes refresh of a context | Context refreshed and infrastructure lifecycle activated | Boot runners have finished |
| `ApplicationStartedEvent` | Boot after refresh, before runners | `SpringApplication` passed refresh | App is ready |
| `ApplicationRunner` / `CommandLineRunner` | After `ApplicationStartedEvent` | Post-refresh logic is executing | All runners finished if not yet returned |
| `ApplicationReadyEvent` | After runners complete | Boot reached the application's ready milestone | All future requests will succeed |
| `AvailabilityChangeEvent` for `ReadinessState.ACCEPTING_TRAFFIC` | After ready event in default flow | Readiness state published by Boot | External systems have routed traffic and business dependencies are always healthy |

In simple apps, events can be separated by tiny intervals. In real apps, runners performing metadata imports, connections, warmup, or resource checks can take noticeable time. Placing appropriate logic in the right stage enables accurate readiness evaluation.

Spring Boot can publish `LivenessState.CORRECT` after `ApplicationStartedEvent` and `ReadinessState.ACCEPTING_TRAFFIC` after `ApplicationReadyEvent` in the normal flow. In Kubernetes deployments, whether probes observe the state also depends on probe endpoints, ports, configuration, and when kubelet polls; ready logs alone do not replace end-to-end testing.

**Note on listeners:** events emitted before context creation like `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` cannot be listened to by an ordinary `@Bean` because the bean does not exist yet. Register early listeners via `SpringApplication.addListeners(...)` when needed. Event callbacks run synchronously by default; avoid overly long logic blocking startup inside a listener.

## 8. Intentional Experiment: Refresh Failing in PostConstruct

Stop the instance serving on 8080. After building the JAR, start with:

~~~bash
java -jar target/refresh-lab-0.0.1-SNAPSHOT.jar --lab.fail-on-init=true
~~~

`FailingInitProbe`'s condition matches, the bean is instantiated, and `@PostConstruct` throws `IllegalStateException("LAB_INTENTIONAL_STARTUP_FAILURE")`. Expected observations:

- Stack trace contains `LAB_INTENTIONAL_STARTUP_FAILURE`; the outer wrapping exception may be `BeanCreationException` while Spring creates the bean.
- The console may already have printed `LAB_DEFINITIONS_COUNT` and some bean initialization markers before the error occurred.
- `LAB_CONTEXT_REFRESHED`, `LAB_APPLICATION_STARTED`, `LAB_RUNNER_DONE`, and `LAB_APPLICATION_READY` are not reached for this failed run.
- The early listener prints `LAB_APPLICATION_FAILED` when Boot publishes the failure event; the boot process exits with a failure status.
- Even if the servlet server was partially prepared, Spring performs rollback/cleanup per startup failure handling. Do not conclude the server is serving merely from a few Tomcat creation log lines.

**How to diagnose:** start from the final exception and trace `Caused by` clauses to pinpoint the bean, init method, and root message. The intentional message in the example is the root-cause evidence. Recover by re-running the JAR **without passing the flag** or passing `--lab.fail-on-init=false`. Do not delete beans en masse or disable post-processing just to hide stack traces.

**Control check:** after removing the failure flag, the same artifact passes all markers and returns 200 on `/probe`. The difference lies in one property controlling a bean condition, proving refresh failures can depend on the environment.

## 9. Application-Wide Lazy Initialization Experiment

Stop the previous app and run:

~~~bash
java -jar target/refresh-lab-0.0.1-SNAPSHOT.jar --spring.main.lazy-initialization=true
~~~

Capture the markers appearing before requests, after `GET /probe`, and after `GET /lazy`. Do not expect every bean marker to still appear at startup as in eager mode. With global lazy initialization, beans not required by startup infrastructure can shift initialization to first access. Then compare first-request latency, the ready milestone, and exceptions that may be deferred.

**Right conclusion:** reducing initialization work during refresh does not eliminate initialization; it only shifts timing. You must review bean dependencies and pre-ready requirements to decide whether it fits startup and first-response SLOs.

## 10. Observing Required Beans and Avoiding Wrong Initialization Patterns

Three business questions must be answered before choosing an initialization point:

1. Is the component **needed to start the system** or only when a feature is invoked? If missing it renders the app unusable, validate it early in startup or readiness.
2. Does initialization depend on other beans already being ready? Constructors and `@PostConstruct` are only appropriate for compact internal state initialization; for cross-bean operations after all normal singletons are ready, consider `SmartInitializingSingleton` or `ContextRefreshedEvent`.
3. Can the work be slow, involve I/O, or fail transiently? You need timeouts, sensible retries, telemetry, and a readiness policy. Never bury an infinite loop inside `@PostConstruct` that stalls startup.

**Appropriate hook points:**

- **Constructor / dependency injection:** establish simple invariants and receive container-resolved dependencies.
- **`@PostConstruct`:** validate internal configuration, prepare modest data structures. It runs during bean init; avoid calling back into unstable beans or performing long I/O.
- **`SmartInitializingSingleton.afterSingletonsInstantiated()`:** needed when running after non-lazy singletons are pre-instantiated; do not assume it covers lazy/request/prototype beans.
- **`ContextRefreshedEvent`:** needed when reacting to a context finishing refresh. Check the target context in parent/child context hierarchies because events can propagate to parent contexts.
- **`ApplicationRunner` / `CommandLineRunner`:** application-level work after refresh yet before ready; failure here can block the ready milestone even though refresh succeeded.
- **`ApplicationReadyEvent`:** announces the very final stage of startup, suitable for lightweight recording/auditing. Work mandatory before serving traffic belongs in runners/readiness policies rather than hoping a ready listener finishes before requests arrive.

Do not call `context.refresh()` yourself inside `@PostConstruct`, controllers, or runners of a Boot application. `SpringApplication` already orchestrates refresh once during standard startup; calling it again on a context that does not support multiple refreshes can error or break consistency.

## 11. When Refresh Fails: Container Recovery Responsibilities

When `refresh()` throws an exception, Spring Framework attempts to stop already-started lifecycle components, destroy created singletons, cancel the refresh state, and propagate the error to `SpringApplication`. Boot may publish `ApplicationFailedEvent` and end startup unsuccessfully. This is **best-effort cleanup**, and does not mean every external connection or transaction has been rolled back perfectly.

Distinguish common root-cause categories:

| Signal | Suspected phase | Check first |
|---|---|---|
| `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException` | Dependency resolution during bean creation | Component scan, packages, `@Bean`, `@Conditional...`, profiles, bean types |
| `BeanCreationException` + exception from init | Constructor, injection, `@PostConstruct`, init-method | Root `Caused by` line, config, and I/O in callbacks |
| `BeanCurrentlyInCreationException` | Dependency cycle, often among constructor dependencies | Dependency graph, split responsibilities, break cycle |
| `BindException` from Spring Boot configuration binding | Binding `@ConfigurationProperties` | Property names, data types, validation, config sources |
| Port already in use | Web server startup | Effective `server.port` and listener on port |
| `ApplicationStartedEvent` present, `ApplicationReadyEvent` absent | Post-refresh, runner or post-refresh step failed | Exceptions in runners, post-refresh tasks |
| HTTP 404 after ready | Routing/URL | `@RequestMapping`, context path, URL, HTTP method |
| HTTP 500 after ready | Request handling | Controller/service stack trace on request |
| `/actuator/health` returns `UP` yet API is wrong | Business behavior not checked by health indicators | Test response/body and business dependencies |

Do not enable `spring.main.allow-circular-references=true` as a knee-jerk reaction to every dependency cycle; fixing the bean graph addresses the real cause. Similarly, changing ports can resolve port conflicts yet will not fix bean init failures; correlate the stack trace with present/absent milestones.

If you use `--debug` in a run to inspect the condition evaluation report, save the needed report and disable it in normal environments. The condition report only explains why auto-configurations matched/did not match, not proof that all bean instances are working.

## 12. Common Misconceptions

**Misconception 1: "Having a BeanDefinition means the bean is ready."** False. The registry holds metadata before instances are created; lazy, request scope, and conditional config change when or whether objects are instantiated.

**Misconception 2: "BeanFactoryPostProcessor and BeanPostProcessor do the same thing."** False. One intervenes in BeanFactory/definitions, the other in creating bean instances. Both occupy different positions in refresh.

**Misconception 3: "Every bean is created specifically in finishBeanFactoryInitialization."** False. Some processors and infrastructure beans must appear earlier; remaining non-lazy application singletons are pre-instantiated at that stage.

**Misconception 4: "@PostConstruct runs after ApplicationReadyEvent."** False for ordinary eager singletons. It runs during bean init, which typically happens during refresh, before ready. Only lazy beans can init late, including after ready.

**Misconception 5: "ContextRefreshedEvent proves all runners have finished."** False. Boot publishes `ApplicationStartedEvent` after refresh, then invokes runners, and finally publishes `ApplicationReadyEvent`.

**Misconception 6: "Having an HTTP listener means readiness."** Not necessarily. The embedded server can start listening before post-startup tasks complete; decide readiness by system contract and verify with actual requests.

**Misconception 7: "Global lazy is always a safe startup optimization."** It moves cost to first use, can shift exceptions to the first request, and increases latency. Measure startup, first request, readiness, and actual failures.

**Misconception 8: "@PostConstruct should connect to all external systems and loop until success."** Long/hanging callbacks block init; prefer timeouts, bounded retry policies, and proper lifecycle hooks.

**Misconception 9: "Seeing Started Application guarantees requests will succeed."** That line is a framework milestone, not a substitute for testing routes, auth, response bodies, and dependencies.

**Misconception 10: "A startup failure always invokes an ApplicationFailedEvent listener declared as a @Bean."** Listener beans may not exist yet if the context has not refreshed; register early via `SpringApplication.addListeners(...)` when observing errors before the container is ready.

## 13. Hands-on Scenario With Acceptance Criteria

Practice step by step and save an evidence table like below:

| Experiment | Command/trigger | Marker or result to verify | Conclusion |
|---|---|---|---|
| Normal boot | `./mvnw spring-boot:run` | `LAB_CONTEXT_REFRESHED` before `LAB_APPLICATION_STARTED`, runner before ready | Distinguish refresh and post-refresh |
| Eager bean | Default launch | Constructor → PostConstruct → SmartInitializingSingleton | Non-lazy singleton bean lifecycle |
| Working HTTP | `GET /probe` | 200 and `{"status":"ready"}` | Mappings and service actually work |
| Lazy bean | First `GET /lazy` | `LAB_DEFERRED_INIT` appears first time at request | Ready does not mean all beans created |
| Startup timeline | `GET /actuator/startup` | JSON timeline with startup steps | Observe cost/phases with tooling |
| Refresh failure | `--lab.fail-on-init=true` | Root exception; failure marker, no ready | Init error blocks startup completion |
| Global lazy | `--spring.main.lazy-initialization=true` | Some init markers shift to usage time | Startup optimization has trade-offs |
| Post-refresh error | Make runner throw in a controlled test branch | Refresh/started may appear, ready does not | Runner error differs from refresh error |

The final stage is a **self-directed extension exercise**: in a copy of the lab, change `startupRunner()` to:

~~~java
@Bean
ApplicationRunner startupRunner() {
    return args -> {
        System.out.println("LAB_RUNNER_BEGIN");
        throw new IllegalStateException("LAB_RUNNER_FAILURE");
    };
}
~~~

This snippet **replaces the `startupRunner()` method in `RefreshLabApplication`**, not a standalone complete Java file. Rebuild and re-run in a separate test terminal. Expect `LAB_CONTEXT_REFRESHED` and `LAB_APPLICATION_STARTED` to possibly appear; `LAB_APPLICATION_READY` does not appear because the runner failed. Contrast the stack trace from the runner with the `FailingInitProbe` error inside refresh. After the experiment, restore the original runner method before moving to other exercises.

### Acceptance Checklist

- [ ] Built the Java 17 / Spring Boot 3.3.x project and ran it with Maven Wrapper.
- [ ] Accurately described the core order of `AbstractApplicationContext.refresh()` and the role of BeanFactory.
- [ ] Distinguished `BeanFactoryPostProcessor` from `BeanPostProcessor` and the `@PostConstruct` lifecycle.
- [ ] Observed constructor, init callback, SmartInitializingSingleton, and ContextRefreshedEvent in logs.
- [ ] Confirmed `ApplicationStartedEvent` → runner → `ApplicationReadyEvent` via markers.
- [ ] Called `GET /probe` and `GET /lazy` to prove endpoint functionality and lazy initialization.
- [ ] Inspected `/actuator/startup` to find a startup step and explain timestamps/durations in practice.
- [ ] Intentionally triggered a bean init failure and identified the cause via `Caused by`.
- [ ] Distinguished a refresh failure from a post-refresh runner failure.
- [ ] Explained the limits of concluding "startup complete" when lazy beans or external dependencies exist.

## 14. Reference Documentation

- Spring Framework 6.2, `AbstractApplicationContext` Javadoc (`refresh()` lifecycle): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework, Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework, Container extension points: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Framework, Bean scopes: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-scopes.html
- Spring Boot 3.3, SpringApplication and application events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, Actuator startup endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3, Actuator endpoints and availability: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html

For every real-world situation, write **hypothesis → position in startup sequence → verification command → observed marker/stack trace/HTTP → conclusion strictly scoped to the evidence**. That is how you prove the context has finished initializing required components while identifying components still waiting to be used or executed in a later phase.