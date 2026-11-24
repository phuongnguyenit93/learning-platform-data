# When Runners Execute Relative to Refresh, Started, and Ready in Spring Boot

## 1. Key Conclusion Before Diving Into Details

In a successful `SpringApplication.run(...)` launch, **`ApplicationRunner.run(...)` and `CommandLineRunner.run(...)` are invoked by Spring Boot after `ApplicationContext.refresh()` completes and after `ApplicationStartedEvent`, yet before `ApplicationReadyEvent`**.

Core sequence:

~~~text
SpringApplication.run(args)
    |
    +-- Prepare Environment, ApplicationContext, bean definitions
    |
    +-- ApplicationContext.refresh()
    |      +-- Create/initialize regular singletons
    |      +-- Create beans of type ApplicationRunner / CommandLineRunner
    |      +-- Run init callbacks (@PostConstruct, initMethod,...)
    |      +-- Finish refresh, publish ContextRefreshedEvent
    |
    +-- Log "Started ..." and publish ApplicationStartedEvent
    +-- LivenessState.CORRECT
    |
    +-- Invoke runners in sorted order
    |      +-- ApplicationRunner.run(ApplicationArguments)
    |      +-- CommandLineRunner.run(String... args)
    |
    +-- Publish ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- SpringApplication.run(...) returns context
~~~

The diagram simplifies internal steps inside `refresh()` and early events. The major milestones above represent the contract documented by Spring Boot for `SpringApplication`. Specifically:

- **Creating a runner bean** does not mean **invoking the runner's `run()` method**. The bean can be created during refresh, while the `run()` callback arrives after `ApplicationStartedEvent`.
- **`ApplicationStartedEvent` is not `ApplicationReadyEvent`**. At Started, runners have not been invoked yet; at Ready, synchronous runners have been invoked and completed successfully.
- **An open web server port** does not by itself prove runners have finished. In a web app, the port may already be listening for connections before Spring Boot publishes readiness.
- `ApplicationReadyEvent` is published **before** Boot publishes `ReadinessState.ACCEPTING_TRAFFIC`; the event does not imply that all custom background tasks have ended.

## 2. Key Terminology

### 2.1. ApplicationContext.refresh()

`refresh()` belongs to the Spring Framework lifecycle. In a typical Spring Boot application context, it prepares the BeanFactory, processes factory post-processors, registers bean post-processors, initializes non-lazy singletons, triggers appropriate lifecycle hooks, and completes context refresh. Runner singleton beans are typically instantiated during this stage, just like many other beans.

Several milestones tied to refresh:

- Spring Boot's `ApplicationPreparedEvent` occurs when the context has been prepared, **before** refresh.
- Spring Framework's `ContextRefreshedEvent` is published when the context finishes refreshing.
- `WebServerInitializedEvent` can appear during the refresh phase of a web application, once the web server has started.
- Spring Boot's `ApplicationStartedEvent` occurs **after** refresh succeeds.

Do not confuse Spring Framework's `ContextRefreshedEvent` with Spring Boot's `ApplicationReadyEvent`. A refreshed context only indicates that the container reached the refresh milestone; it does not state that Spring Boot's runners have executed.

### 2.2. ApplicationStartedEvent

`org.springframework.boot.context.event.ApplicationStartedEvent` is a Spring Boot event published **once the context has refreshed, but before any application or command-line runners have been called**.

This has a practical implication: a listener receiving Started can inspect the context and initialized beans, but cannot rely on side effects from `ApplicationRunner.run()` or `CommandLineRunner.run()`, because those callbacks have not run yet on the normal startup path.

`ApplicationStartedEvent` should not be interpreted as "the entire application is ready to accept traffic." It merely marks the milestone after refresh and before runners.

### 2.3. ApplicationReadyEvent

`org.springframework.boot.context.event.ApplicationReadyEvent` is published after Spring Boot has finished calling runners. On the successful startup path, this event is published very late to signal that the application has completed the Boot-managed startup process.

After `ApplicationReadyEvent`, Spring Boot publishes `ReadinessState.ACCEPTING_TRAFFIC` via a separate `AvailabilityChangeEvent`. Therefore, if you check readiness inside a listener for `ApplicationReadyEvent` itself, remember that **the moment accepting readiness is published comes after that event**. Once `SpringApplication.run(...)` has returned successfully, readiness publication on the normal startup path has taken place.

### 2.4. ApplicationRunner and CommandLineRunner

Both are interfaces in the `org.springframework.boot` package, discovered by Spring Boot as ApplicationContext **beans** and invoked once per SpringApplication run along the successful startup path:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

The two snippets above are **illustrative method signatures**, not interface definitions to copy into your project. Use the interfaces provided by Spring Boot.

The primary difference is how arguments are received:

- `ApplicationRunner`: receives `ApplicationArguments`; you can use `getOptionNames()`, `containsOption(name)`, `getOptionValues(name)`, `getNonOptionArgs()`, `getSourceArgs()`.
- `CommandLineRunner`: receives raw arguments `String... args`, suited for direct CLI handling or code that only needs the input strings.

Regarding **invocation timing**, both belong to the **same runners phase** between Started and Ready. There is no general rule that "every ApplicationRunner must run before every CommandLineRunner"; when multiple runners exist, order depends on the sorting mechanism (`Ordered` / `@Order`), not purely on interface name.

## 3. Detailed Startup Sequence and What Is Ready

| Stage | Regular beans created? | `runner.run()` executed? | What can be concluded? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | No complete context yet | No | The `SpringApplication` run has just begun |
| `ApplicationEnvironmentPreparedEvent` | No main context yet | No | Environment has been prepared |
| `ApplicationContextInitializedEvent` | Context preliminarily initialized | No | Context created and initializers have run |
| `ApplicationPreparedEvent` | Definitions loaded, not refreshed yet | No | About to invoke refresh |
| Inside `refresh()` | Required singletons being created | Not yet called by Boot in runners phase | Container is setting up beans and lifecycle |
| `ContextRefreshedEvent` | Eager singletons completed per refresh | No | Context refresh succeeded |
| `ApplicationStartedEvent` | Context refreshed | **No** | Spring Boot reached the Started milestone |
| In `callRunners(...)` phase | Runner beans exist to invoke | Running sequentially | Startup is still not complete |
| `ApplicationReadyEvent` | Yes | **Executed successfully** | Boot publishes the Ready milestone |
| `ReadinessState.ACCEPTING_TRAFFIC` | Yes | Executed successfully | Boot announces it can accept traffic |
| `SpringApplication.run(...)` returns | Yes | Executed successfully | Caller in `main()` can continue executing |

"Eager singletons" does not include `@Lazy` beans that have not been requested or prototype beans that have not been looked up. Therefore, **do not deduce that every bean across the entire application has already been created** before `ApplicationStartedEvent`; what is guaranteed is that the context has completed refresh under its contract.

### Why Are Runners Created During Refresh Yet run() Is Called Later?

Spring Boot treats a runner as **a bean with a callback intended for the post-container-startup phase**. The BeanFactory must instantiate the runner and inject dependencies like normal beans. Afterward, `SpringApplication` retrieves beans of type `ApplicationRunner`/`CommandLineRunner` from the context and invokes `run(...)` in a dedicated phase. Consequently:

1. Runners can inject services, repositories, `Environment`, or `ApplicationAvailability` already prepared by the container.
2. Runners do not have to instantiate dependencies with `new` or bootstrap a BeanFactory themselves.
3. Work requiring a full context is separated from constructors, `@PostConstruct`, and factory methods.
4. Spring Boot can publish Started before runners execute and Ready after runners finish.

**Crucial distinction:** if a runner's constructor logs `RUNNER_CONSTRUCTED`, that log can appear **during refresh**, whereas a `RUNNER_EXECUTING` log inside `run()` only appears **after ApplicationStartedEvent**.

## 4. Ordering Relative to Other Callbacks

| Callback / event | Typical location | Relationship to runner.run() |
| --- | --- | --- |
| Bean constructor | During bean creation | Before runner if it is an already-created eager bean |
| `@Autowired` / constructor injection | While creating and configuring bean | Before runner |
| `@PostConstruct` | During bean init, in refresh for eager singletons | Usually before runner |
| `InitializingBean.afterPropertiesSet()` | During bean init | Before runner for eager singletons |
| `@Bean(initMethod = "...")` | During bean init | Before runner for eager singletons |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | After eager singletons are created | Before runner in normal refresh |
| `SmartLifecycle.start()` when auto-start | During context lifecycle startup | Usually before runner |
| `ContextRefreshedEvent` | End of refresh | Before runner |
| `ApplicationStartedEvent` | After refresh | Before runner |
| `ApplicationRunner.run()` and `CommandLineRunner.run()` | Boot's runners phase | Primary milestone |
| `ApplicationReadyEvent` | After runners complete | After runner |
| `ReadinessState.ACCEPTING_TRAFFIC` | After Ready event | After runner |
| `ContextClosedEvent` | When context closes | Part of shutdown, not a startup milestone |

Statements about eager beans refer to the **normal startup path**. Lazy beans created for the first time later may execute `@PostConstruct` after runners; that is not a startup ordering violation. Event listeners can be configured asynchronously, or callbacks can spawn threads; therefore, the moment **a callback starts** does not guarantee all asynchronous work has completed.

### Two Easily Misunderstood Log Lines

Example log:

~~~text
Tomcat started on port 8080 (http)
Started DemoApplication in 2.345 seconds
~~~

This is an **illustrative log format**, not a fixed stdout string for a specific Spring Boot version or program.

- The line "Tomcat started ..." indicates the embedded web server reached its startup milestone. The server may already have opened its port during the refresh phase.
- The line "Started ... in ... seconds" typically marks the startup portion after context refresh. It **does not by itself prove runners have finished**; Spring Boot may still need to invoke runners before publishing the Ready event.

If a runner runs for 20 seconds, some server logs and "Started ..." may appear beforehand. Do not use those log strings to decide whether an instance can serve business traffic; use readiness probes or the proper event.

## 5. Complete Java 17+ Example — Observing Refresh, Started, Runner, Ready

The example below uses Spring Boot **3.5.16** and Java 17+. It intentionally runs without a web server (`WebApplicationType.NONE`) so Tomcat logs do not clutter the output. The program prints ordered markers and uses `Ordered` to explicitly control which runner is called first. It uses neither `Thread.sleep` nor a database.

### 5.1. Directory Structure

~~~text
runner-timing-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/runnertiming/
                └── RunnerTimingApplication.java
~~~

**File `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>runner-timing-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

JDK 17+ and a compatible Maven version are required. If your project uses a different Spring Boot branch, choose the matching dependency version and imports. The example uses `spring-boot-starter` and **does not require `spring-boot-starter-web`** because there is no HTTP endpoint.

### 5.2. Compilable Java File

**File `src/main/java/com/example/runnertiming/RunnerTimingApplication.java`:**

~~~java
package com.example.runnertiming;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;

@SpringBootApplication
public class RunnerTimingApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RunnerTimingApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ApplicationAvailability availability = context.getBean(
                    ApplicationAvailability.class);
            System.out.println(
                    "08_RUN_RETURNED readiness="
                            + availability.getReadinessState());
        }
    }

    @Bean(initMethod = "initialize")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    TimelineObserver timelineObserver() {
        return new TimelineObserver();
    }

    @Bean
    FirstRunner firstRunner(DemoResource resource,
                            ApplicationAvailability availability) {
        return new FirstRunner(resource, availability);
    }

    @Bean
    SecondRunner secondRunner() {
        return new SecondRunner();
    }

    public static final class DemoResource {

        public DemoResource() {
            System.out.println("01_RESOURCE_CONSTRUCTOR");
        }

        public void initialize() {
            System.out.println("02_RESOURCE_INITIALIZED");
        }

        public String value() {
            return "ready";
        }
    }

    public static final class TimelineObserver {

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            System.out.println("03_CONTEXT_REFRESHED");
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            System.out.println("04_APPLICATION_STARTED");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("07_APPLICATION_READY");
        }
    }

    public static final class FirstRunner
            implements ApplicationRunner, Ordered {

        private final DemoResource resource;
        private final ApplicationAvailability availability;

        public FirstRunner(DemoResource resource,
                           ApplicationAvailability availability) {
            this.resource = resource;
            this.availability = availability;
        }

        @Override
        public int getOrder() {
            return 10;
        }

        @Override
        public void run(ApplicationArguments args) {
            System.out.println(
                    "05_APPLICATION_RUNNER readiness="
                            + availability.getReadinessState()
                            + " value=" + resource.value()
                            + " args=" + args.getSourceArgs().length);

            if (args.containsOption("fail")) {
                throw new IllegalStateException("runner-failed");
            }
        }
    }

    public static final class SecondRunner
            implements CommandLineRunner, Ordered {

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void run(String... args) {
            System.out.println(
                    "06_COMMAND_LINE_RUNNER args=" + args.length);
        }
    }
}
~~~

**This is a complete program** within the given Maven project, not pseudocode. Helper classes are declared inside one file to minimize configuration. Both `FirstRunner` and `SecondRunner` are beans created by `@Bean` methods. `Ordered.getOrder()` returns 10 and 20; smaller values have higher invocation priority.

The `01_RESOURCE_CONSTRUCTOR` and `02_RESOURCE_INITIALIZED` markers occur when Spring creates/initializes `DemoResource`, **during refresh**, before Spring Boot transitions to the runners phase. `TimelineObserver` is a listener bean: it is registered in the context and observes events occurring after refresh as appropriate.

`FirstRunner` receives `ApplicationAvailability` and `DemoResource` via dependency injection. It reads `ReadinessState` **when `run()` executes**, not in the constructor. While Boot is still executing runners, the default readiness state is `REFUSING_TRAFFIC`. Unless `--fail` is passed, the method simply prints the marker and returns normally.

`main()` uses `try`-with-resources to close the context after printing the final marker; closing the context is cleanup for the CLI example, not part of the runner sequence. Because `TimelineObserver` does not listen for `ContextClosedEvent`, it produces no additional marker lines in the program.

### 5.3. Running and Comparing Output

In the directory containing `pom.xml`, run:

~~~bash
mvn spring-boot:run
~~~

Or package and run the JAR:

~~~bash
mvn package
java -jar target/runner-timing-demo-0.0.1-SNAPSHOT.jar
~~~

On a successful run with **no application arguments**, the eight lines **printed by the program itself** appear in this order:

~~~text
01_RESOURCE_CONSTRUCTOR
02_RESOURCE_INITIALIZED
03_CONTEXT_REFRESHED
04_APPLICATION_STARTED
05_APPLICATION_RUNNER readiness=REFUSING_TRAFFIC value=ready args=0
06_COMMAND_LINE_RUNNER args=0
07_APPLICATION_READY
08_RUN_RETURNED readiness=ACCEPTING_TRAFFIC
~~~

Banners, Spring Boot logs, or Maven messages may be interleaved; compare only **the order of the markers above**, without requiring them to be contiguous across all of stdout. The example uses no web server, so the absence of a `Tomcat started` log is normal.

Line `05` is especially informative: the runner was invoked **after Started**, yet the application still reports `REFUSING_TRAFFIC`. Line `08` is printed after `SpringApplication.run(...)` has returned successfully and readiness has transitioned to `ACCEPTING_TRAFFIC`. These two lines confirm Started and Ready are not the same milestone.

Line `07_APPLICATION_READY` is printed by the `ApplicationReadyEvent` listener **before Boot publishes `ReadinessState.ACCEPTING_TRAFFIC`**. Do not assume the readiness state has already changed at the very start of that listener method.

### 5.4. Passing Arguments and Checking Order

Try:

~~~bash
java -jar target/runner-timing-demo-0.0.1-SNAPSHOT.jar --sample=hello extra
~~~

In this case, `FirstRunner` prints `args=2` (two elements in `getSourceArgs()`); `SecondRunner` prints `args=2` (two `String...` elements). Markers `01`–`08` remain in the same order. To inspect options and non-options further, `ApplicationArguments` also provides `containsOption("sample")`, `getOptionValues("sample")`, and `getNonOptionArgs()`.

**Testing an intentional runner failure**:

~~~bash
java -jar target/runner-timing-demo-0.0.1-SNAPSHOT.jar --fail
~~~

`FirstRunner` throws `IllegalStateException("runner-failed")`. Then `SpringApplication.run(...)` fails; the subsequent `SecondRunner` is not invoked in the normal pipeline, `ApplicationReadyEvent` is not published, and line `08_RUN_RETURNED` does not appear. Spring Boot may publish `ApplicationFailedEvent` and perform appropriate cleanup.

The failure path will include extra exception/stack trace logs depending on the environment, so **do not treat the entire stdout of a failed run as a fixed string**. What matters is that Started occurred without Ready; that proves `ApplicationStartedEvent` does not guarantee all runners succeeded.

## 6. What Happens When There Are Multiple Runners?

An application can declare multiple `ApplicationRunner` and `CommandLineRunner` beans. Spring Boot collects these beans, sorts them using Spring's ordering mechanism, and invokes them sequentially. When order has business significance, use:

1. **`org.springframework.core.Ordered`**: implement `getOrder()` in the runner class.
2. **`org.springframework.core.annotation.Order`**: apply on the appropriate runner type recognized by Spring.
3. **`PriorityOrdered`** if a special priority contract is genuinely required, while understanding how the comparator sorts.

**Lower numeric order values take precedence** within the same sorting mechanism. The example in section 5 uses `Ordered`, so it does not depend on the order in which `@Bean` methods are listed in the file.

One thing to avoid: looking at the names `ApplicationRunner` and `CommandLineRunner` and assuming all beans of one type always run before the other. Both participate in the same runner sorting and invocation mechanism; **for deterministic order, declare order explicitly**. If runners share the same order level, do not rely on the incidental position observed in a single run.

### Should @DependsOn Be Used to Control Runner Order?

No. `@DependsOn` primarily requests that a bean's dependencies be initialized before the dependent bean; it **does not replace** `Ordered` / `@Order` for specifying `run()` invocation order.

For example, `@DependsOn("prepareService")` on a runner can ensure `prepareService` is created early, but it does not prove that another runner's `run()` has finished. Keep the two concepts separate:

- **Dependency graph**: bean creation and dependency injection order.
- **Runner order**: the order in which Spring Boot invokes `run()` callbacks after Started.

If runner B genuinely depends on the output of runner A, make the contract between them explicit. In some systems, it is better to create **a single sequential orchestrating runner** with multiple steps rather than two separate runners communicating via hidden side effects in shared state.

### Do Runners Execute in Parallel by Default?

In the normal startup pipeline, Spring Boot **invokes runners sequentially**, without spawning a separate thread per runner. Runners can start their own threads or async tasks; those tasks **are not automatically awaited by Boot** simply because they originated from a runner. Therefore, distinguish *the runner method returning* from *work spawned by the runner actually completing*.

If runner A spawns a background worker and returns immediately, Spring Boot can invoke runner B and publish Ready even while A's worker is still running. To guarantee true readiness, await essential work completion or reflect its status in readiness health.

## 7. Readiness, Liveness, and Web Server While Runners Execute

Spring Boot provides `ApplicationAvailability` with two distinct state groups:

- **`LivenessState`**: whether the application is alive and needs restarting (`CORRECT` or `BROKEN`).
- **`ReadinessState`**: whether the instance should receive new traffic (`REFUSING_TRAFFIC` or `ACCEPTING_TRAFFIC`).

During normal startup, `ApplicationStartedEvent` is followed by `LivenessState.CORRECT`. After runners succeed, `ApplicationReadyEvent` is followed by `ReadinessState.ACCEPTING_TRAFFIC`.

Hence **liveness can be healthy while readiness is still refusing traffic**, especially while runners are performing mandatory initialization steps.

### A Web Server Can Open Its Port Before Ready

For Servlet or Reactive applications, the web server is created/started during web context refresh. For a period of time, the TCP port may already be open and HTTP endpoints may respond even though runners have not finished. This is why readiness probes are needed in Kubernetes/load-balancer environments rather than inferring readiness solely from a "server started" log.

To use Actuator probes outside Kubernetes (where they might not be enabled automatically), you can configure this in a project with `spring-boot-starter-actuator`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

When applicable, the endpoints are:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

While runners have not completed, Boot's default readiness is typically `REFUSING_TRAFFIC` and readiness health can reflect `OUT_OF_SERVICE` / HTTP 503 under default mapping. Once runners finish and Boot publishes accepting, health can return `UP` / HTTP 200, provided no additional indicator alters the overall status.

**Do not** use an arbitrary endpoint that always returns HTTP 200 as a readiness probe. Likewise, do not put every external dependency into liveness: a transient database outage capable of self-recovery is often better suited to readiness rather than repeatedly restarting the pod.

### Does ApplicationReadyEvent Guarantee All Business Capabilities Are Ready?

Not unconditionally. `ApplicationReadyEvent` reflects that Spring Boot has finished **the runners it invoked** on the startup path; it does not automatically verify every connection and background job the application created on its own.

Conceptually flawed example:

~~~java
@Bean
ApplicationRunner prematureRunner() {
    return args -> {
        new Thread(this::loadRequiredCache).start();
        // run() returns immediately while the cache is still loading.
    };
}
~~~

This is a **non-standalone illustrative snippet** (`loadRequiredCache` is a hypothetical method). Spring Boot only sees that `run()` has returned, so it can publish Ready prematurely if the cache is required for every request.

Better design choices depending on the case:

- If the work is a mandatory precondition before accepting traffic, have the runner **wait with a bounded timeout** before returning; on failure, enforce a clear startup-failure or error-handling policy.
- If it must run asynchronously, feed the status of the mandatory work into readiness health or an appropriate `ApplicationAvailability` controller, ensuring Boot does not open traffic before readiness or maintains readiness state past the Ready milestone.
- If the step is merely non-essential cache warming, it can run in the background and accept traffic early, provided functionality has a proper fallback.

Note: Boot automatically publishes `ACCEPTING_TRAFFIC` after Ready. Publishing `REFUSING_TRAFFIC` too early can be overwritten by that default milestone. If managing custom readiness, explicitly coordinate ordering and state after Ready rather than emitting an event once inside a runner's constructor and hoping the state persists forever.

## 8. What If a Runner Throws an Exception or Blocks?

### 8.1. Runner Throws an Exception

`ApplicationRunner.run(...)` and `CommandLineRunner.run(...)` are permitted to `throws Exception`. If a runner throws an unhandled exception:

- `ApplicationStartedEvent` **may already have been published**, because it precedes runners.
- Subsequent runners in the normal pipeline **do not continue running**.
- `ApplicationReadyEvent` **is not published as on the successful startup path**.
- `SpringApplication.run(...)` fails and Spring Boot handles the startup error, potentially publishing `ApplicationFailedEvent`; closing the context/resources depends on the stage and cleanup mechanism.

**Do not** rely on `ApplicationStartedEvent` as a sign that "startup completed successfully." If you need to judge when startup truly succeeded, use `ApplicationReadyEvent`, readiness, or the return of `SpringApplication.run(...)`.

### 8.2. Runner Runs Too Long

A runner blocking for 60 seconds generally prevents `SpringApplication.run(...)` from completing during that time. The risks:

- Startup timeouts in orchestration environments.
- Readiness kept refusing for a long time, slowing rollouts or keeping pods from receiving traffic.
- Looking only at the "Started ..." log can mislead operators into thinking startup is done while the runner is still blocking.
- Exceptions/timeouts on a dependency can prevent the process from ever reaching Ready.

Design initialization steps with **timeouts, bounded retries, cancellation, and an error policy**. If a task is not mandatory for accepting traffic, do not force startup to wait indefinitely. If long warm-up is required, align startup probes and readiness with reality.

### 8.3. Runner Needs Beans and Wants to Use a Web Server

A runner can inject `ApplicationContext`, services, `WebClient`, `JdbcTemplate`, or other beans, provided those dependencies are defined. However, **do not treat the web server being up as a safe signal to call an internal HTTP endpoint** if that endpoint still depends on state being initialized by the runner. Avoid circular dependencies between a runner and requests that the runner itself is waiting on.

## 9. Choosing a Runner or Which Lifecycle Hook for the Problem?

| Need | Suitable Extension Point | Reason |
| --- | --- | --- |
| Customize bean definitions before beans are created | `BeanFactoryPostProcessor` / `BeanDefinitionRegistryPostProcessor` | Operates on metadata before init |
| Initialize internal state inside a single bean | Constructor, init method, `@PostConstruct` | Belongs to the bean's own lifecycle |
| Observe context refresh completion | `ContextRefreshedEvent` | Milestone when container finishes refresh |
| Perform a startup task able to use injected services | `ApplicationRunner` / `CommandLineRunner` | After refresh, before Ready |
| Observe Boot Started milestone | `ApplicationStartedEvent` | Excludes runners |
| Signal that the application finished Boot-managed startup | `ApplicationReadyEvent` | After runners |
| Determine whether an instance should receive traffic | Readiness probe / `ApplicationAvailability` | Reflects actual serving capability |
| Run periodic work or jobs that must not block startup | `@Scheduled`, queue consumer, managed worker | Do not abuse runners as schedulers |
| Clean up beans when the application closes | `@PreDestroy`, `DisposableBean`, `SmartLifecycle` | Belongs to shutdown, not runners |
| Run a CLI batch job and exit | Runner + proper exit flow | Uses refreshed context for batch processing |

Runners are suited for a task **invoked once when SpringApplication starts**, not as a callback for each HTTP request or for each manual `ApplicationContext.refresh()` call on every type of context. Nor does it mean the runner is re-invoked every time a Kubernetes probe hits an endpoint.

## 10. Common Misconceptions

1. **"Creating the runner bean = the runner has run."** False: constructor/`@PostConstruct` run during refresh, while `run()` runs after Started.
2. **"`ContextRefreshedEvent` = `ApplicationReadyEvent`."** False: refresh is before runners, ready is after runners.
3. **"`ApplicationStartedEvent` indicates runners have finished."** False: this event is published **before** invoking runners.
4. **"Seeing `Started DemoApplication in ...` means ready to accept traffic."** False: runners may still be running or may fail.
5. **"ApplicationRunner always runs before CommandLineRunner."** False: both are sorted by ordering mechanism; use `Ordered` or `@Order`.
6. **"`@DependsOn` guarantees `run()` order across runners."** False: it relates to bean creation, not the runner callback pipeline.
7. **"A runner starts a `CompletableFuture` and returns, so Boot waits for the future."** False: Boot does not automatically await background work outside `run()`.
8. **"Server opening its port means `ApplicationReadyEvent` has been published."** False: the server can come up during refresh before runners.
9. **"Liveness `CORRECT` means readiness `ACCEPTING_TRAFFIC`."** False: liveness and readiness are two distinct states.
10. **"A runner throws an error, yet Ready will still appear on its own."** False on the failed startup path; Spring Boot does not reach successful ready.
11. **"All beans have been initialized at Started."** Not true for lazy or prototype beans; Started reflects refresh completion per contract, not force-creating every bean.
12. **"You can read a runner's output in a Started listener."** No, unless that data was produced by another path; this startup's runners have not run yet.
13. **"Using an `ApplicationReadyEvent` listener for long blocking tasks is always fine."** Do not assume so; listeners are synchronous by default and can delay publishing accepting availability and completing startup.
14. **"The run method executes before every init method."** False for eager singletons; init belongs to refresh, runners execute later.
15. **"Runners finishing means the Internet can definitely reach the application."** Application readiness does not guarantee ingress, DNS, firewalls, or external infrastructure are clear.

## 11. Knowledge Check Questions

**Question 1:** Does `@PostConstruct` on a runner bean normally run before or after `ApplicationStartedEvent`?

**Answer:** For an eager singleton runner created normally during refresh, `@PostConstruct` runs during bean init, which is **before Started**. However, the runner's `run()` method is called by Spring Boot **after Started**.

**Question 2:** `ApplicationStartedEvent` has been published, but a runner is loading data for 10 seconds. Is the application Ready yet?

**Answer:** No, per Spring Boot's lifecycle. `ApplicationReadyEvent` comes after the runner finishes successfully; default readiness still refuses traffic while the runner executes.

**Question 3:** There are two runners, an `ApplicationRunner` with order 100 and a `CommandLineRunner` with order 10. Which runner runs first?

**Answer:** The runner with order 10 runs first in Spring Boot's sorted pipeline; order is not determined solely by interface name.

**Question 4:** A runner spawns a background thread and returns immediately, while the thread is still loading critical data. Is `ApplicationReadyEvent` delayed until the thread finishes?

**Answer:** Not by default. Spring Boot sees that `run()` has returned; if the business logic requires waiting, the runner must synchronize appropriately or manage readiness according to actual status.

**Question 5:** A runner throws `IllegalStateException`. Can you observe `ApplicationStartedEvent` without `ApplicationReadyEvent`?

**Answer:** Yes. Started occurs before runners; Ready is the milestone after runners complete successfully. The failure path typically leads to `ApplicationFailedEvent`.

**Question 6:** A web server is running with liveness 200 and readiness 503 while a runner is working. Is there a contradiction?

**Answer:** No. The server/process can be alive and serving probes while readiness has not yet opened for business traffic. Inspect runner status and health groups rather than restarting the pod simply because readiness is legitimately waiting.

**Question 7:** Why should you not replace `Ordered` with `@DependsOn` to determine runner invocation order?

**Answer:** `@DependsOn` affects bean initialization order, whereas `Ordered`/`@Order` controls `run()` callback invocation order. Those are two different phases.

## 12. Practice Exercises

### Exercise A — Verify the Boundaries

Run the section 5 example and record the eight marker lines in order. Identify which lines occur during refresh, which after Started, and which after Ready. Try adding a log in `FirstRunner`'s constructor to see that **the runner bean is created before `FirstRunner.run()` is called**.

### Exercise B — Reverse Runner Order

Change `FirstRunner.getOrder()` to 30 while keeping `SecondRunner.getOrder()` at 20. Predict the order of markers `05` and `06` and run a check. Note that the numbers printed inside the markers are fixed labels you print yourself, not indices renumbered by Spring Boot. To make output easier to read, update the labels after confirming the result.

### Exercise C — Failure Between Milestones

Run the JAR with `--fail`. Mark which events and runners occurred before the exception. Explain why `ApplicationReadyEvent` and `RUN_RETURNED` are missing. Choose an error-handling policy suited to a real initialization task: fail startup, bounded retry, or ignore when non-essential.

### Exercise D — Experiment with Asynchronous Work

Replace the work in the runner with a `CompletableFuture` launching a background task and returning immediately. Observe that Ready can appear before the task completes. Then try `future.get` or `join` (with a timeout/bound suitable for a real environment) and explain the difference between *the runner method returning* and *business data being ready*.

### Exercise E — Apply to a Web Application

Create a project with `spring-boot-starter-web` and `spring-boot-starter-actuator`, enabling `management.endpoint.health.probes.enabled=true`. In a runner, temporarily add a bounded wait solely for testing. Compare server logs, `/actuator/health/liveness`, and `/actuator/health/readiness` before and after the runner. Do not ship artificial sleep code to production.

## 13. Official Documentation and Takeaways

Read the Spring Boot documentation matching your project's dependency version:

- [Spring Boot 3.5 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): Started → runners → Ready ordering, availability events, and guidance on using runners.
- [Spring Boot 3.5 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationRunner.html): callback contract, `ApplicationArguments`, `Ordered`/`@Order` ordering.
- [Spring Boot 3.5 — CommandLineRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/CommandLineRunner.html): `String...` arguments and callback.
- [Spring Boot 3.5 — ApplicationStartedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html): published after refresh and before runners.
- [Spring Boot 3.5 — ApplicationReadyEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html): published after startup has passed through runners.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability): liveness, readiness, and operational consequences.

**Core Takeaways:**

- **Refresh:** the container prepares, creates, and initializes eager beans, including runner beans; refresh ends with `ContextRefreshedEvent`.
- **Started:** `ApplicationStartedEvent` occurs **after refresh yet before any `runner.run()`**.
- **Runners:** `ApplicationRunner` and `CommandLineRunner` are invoked by Spring Boot in the same phase, with order controlled by `Ordered`/`@Order` when needed.
- **Ready:** `ApplicationReadyEvent` is published after runners finish successfully; Boot then publishes `ReadinessState.ACCEPTING_TRAFFIC`.
- **Do not equate** the Started log or an HTTP server opening its port with the application being ready; use proper readiness and lifecycle milestones.
- **Synchronous runners must complete before Ready**; background tasks spawned by runners are not awaited by default. If a runner throws an exception, startup may have reached Started without reaching Ready successfully.
